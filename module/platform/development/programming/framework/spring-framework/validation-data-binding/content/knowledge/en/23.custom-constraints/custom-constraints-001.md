# Defining Annotations with @Constraint in Jakarta Validation and Spring Framework

> **Module:** Spring Framework – validation-data-binding  
> **Knowledge group:** Custom constraints  
> **Focus:** Defining a Java annotation recognized by Jakarta Validation via `@Constraint`, linking a validator, designing the `message`/`groups`/`payload` elements, applicability scopes, reuse, and Spring integration.

## 1. Learning objectives

After completing this lesson, you can:

1. Explain why `@Constraint` is the core metadata that turns an annotation into a **Jakarta Validation constraint** rather than a decorative Java annotation.
2. Write an annotation with `@Target`, `@Retention(RUNTIME)`, `@Documented`, `@Constraint(validatedBy=...)`, and the three **required** elements `message()`, `groups()`, `payload()` with the correct data types.
3. Distinguish **constraint declaration** (annotation attached to data), **constraint definition** (annotation definition + validator), **constraint validator** (logic), and **validation provider** (execution engine).
4. Design configuration attributes such as `prefix` and `digits` without confusing them with specification-reserved elements.
5. Attach annotations to fields, getters, parameters, classes, or container elements **only when `@Target` and validator types allow it**.
6. Create a runnable custom annotation + `ConstraintValidator` with Java 17, Maven, and Hibernate Validator; test null handling, invalid input, and error messages.
7. Understand constraint composition, `@ReportAsSingleViolation`, repeatable constraints, groups, payload, message interpolation, and the metadata API.
8. Integrate custom constraints into Spring MVC/Boot, handle valid dependency injection, and distinguish configuration errors from data errors.
9. Recognize when to write a custom constraint instead of using built-in constraints or business logic in a service.

## 2. Where does `@Constraint` sit in the architecture?

Jakarta Validation is an **API specification**: the application places constraints on data and asks a `Validator` to check them. Hibernate Validator is a popular **implementation/provider**. Spring Framework integrates the provider at points such as `@Valid @RequestBody`, `@Validated`, `LocalValidatorFactoryBean`, or method validation.

A custom constraint typically consists of the following components:

~~~text
   ANNOTATION DEFINITION (Java)
   @Constraint(validatedBy = SkuCodeValidator.class)
   @Target(...)
   @Retention(RUNTIME)
   public @interface SkuCode { message/groups/payload/... }
                 |
                 | is used
                 v
   @SkuCode(prefix="SKU", digits=3)
   private String sku;                   [constraint declaration]
                 |
                 | Validator.validate(bean)
                 v
   Jakarta Validation provider
     - reads annotation metadata and groups
     - selects ConstraintValidator compatible with String
     - calls initialize(annotation), isValid(value, context)
                 |
        +--------+---------+
        |                  |
      true                false
     valid          ConstraintViolation
                     propertyPath/message/descriptor...
~~~

**Having only `@Constraint` is not enough for validation to run automatically.** You need a provider and a validation trigger point. Calling `new Product("bad")` or a normal setter does not produce errors just because a field has an annotation.

A Java annotation like the following **is not yet a Jakarta Validation constraint**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface SkuHint {
    String format() default "SKU-###";
}
~~~

It can be read via reflection, but the Jakarta Validation provider **does not treat it as a constraint**, because it lacks `@Constraint` and the required element contract. Do not name an annotation starting with `Valid...` and assume the framework will automatically recognize it.

## 3. Minimal structure of a custom constraint annotation

Example annotation validating a product code string with a fixed format:

~~~java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = SkuCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface SkuCode {

    String message() default "{example.validation.SkuCode.message}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String prefix() default "SKU";

    int digits() default 3;
}
~~~

This is an **actual source file** from the sample project in section 8; it requires the `SkuCodeValidator` class and the appropriate Jakarta Validation dependency to compile. Notable points:

- `public @interface SkuCode` declares an **annotation type** in Java.
- `@Constraint(validatedBy = SkuCodeValidator.class)` declares this as a custom Jakarta constraint and names its implementation.
- `@Retention(RUNTIME)` preserves metadata at runtime so the provider can read it.
- `@Target(...)` specifies where the annotation is allowed to be attached.
- `@Documented` makes the annotation appear in Javadoc; useful, though it does not affect validation logic.
- `message()`, `groups()`, and `payload()` are the mandatory standard elements with the prescribed types and defaults.
- `prefix()` and `digits()` are **user-defined** attributes read from the annotation when the validator initializes.

### 3.1. Why is `@Retention(RUNTIME)` mandatory?

Java supports `SOURCE`, `CLASS`, and `RUNTIME`:

| Retention | How long does metadata survive? | Suitable for custom Jakarta constraint? |
| --- | --- | --- |
| `SOURCE` | Source code / compile time only | No |
| `CLASS` | In the class file, but not as a standard runtime annotation | No |
| `RUNTIME` | Readable at runtime | **Yes – mandatory** |

A constraint lacking the appropriate retention may not be recognized by the provider. Per the specification, a constraint definition annotation must have `RUNTIME` and `@Constraint`. Do not assume adding `@Constraint` alone while omitting `@Retention` is sufficient.

### 3.2. `@Constraint(validatedBy = ...)` is the implementation link

`validatedBy` accepts an **array of classes** implementing `jakarta.validation.ConstraintValidator`:

~~~java
@Constraint(validatedBy = SkuCodeValidator.class)
~~~

or:

~~~java
@Constraint(validatedBy = {
        StringCodeValidator.class,
        CharSequenceCodeValidator.class
})
~~~

The second snippet only illustrates syntax, **not a requirement to add two classes with the same functionality**. If multiple validators are listed, the provider selects the best-matching implementation for the data type according to the specification's type resolution rules. Duplicate or unresolvable definitions can cause a validation exception; do not register multiple validators just to "try both in order".

`@Constraint(validatedBy = {})` is also valid in a **composed constraint** that only combines other constraints; see section 11. It does **not** mean the provider will guess how to validate a custom annotation with custom logic on its own.

### 3.3. The three mandatory elements: exact names, types, and default values

| Element | Required signature | Role |
| --- | --- | --- |
| `message` | `String message() default "...";` | Message template upon violation |
| `groups` | `Class<?>[] groups() default {};` | Set of validation groups |
| `payload` | `Class<? extends Payload>[] payload() default {};` | Extension metadata attached to the constraint |

**The names are fixed** and the defaults for `groups`/`payload` must be empty arrays. This is a **specification contract**, not a style suggestion.

Incorrect example:

~~~java
public @interface BadConstraint {
    String error();              // cannot replace message()
    Class<?> groups();           // wrong type: must be Class<?>[]
    String[] payload() default {}; // wrong payload type
}
~~~

The snippet above is an **illustration of a design error**, not a valid custom constraint. When an annotation carries `@Constraint` but has invalid mandatory element definitions, the provider may throw `ConstraintDefinitionException` when accessing metadata or validating.

The names `message`, `groups`, `payload`, and `validationAppliesTo` have reserved roles. Additionally, the specification forbids custom attribute names **starting with `valid`**; avoid `validValue()` or `validDigits()`. Use `prefix()`, `digits()`, `minLength()`, etc. to express constraint configuration.

## 4. Choosing `@Target` based on where data is checked

`java.lang.annotation.Target` restricts valid placement locations in the Java language. There is no single mandatory target list for all custom constraints; choose based on the use case.

| `ElementType` | Allowed location | Example |
| --- | --- | --- |
| `FIELD` | Class field / record backing field | `@SkuCode private String sku;` |
| `METHOD` | Getter or method return value | `@SkuCode public String getSku()` |
| `PARAMETER` | Method/constructor parameter | `void save(@SkuCode String sku)` |
| `TYPE` | Class/interface/record declaration | `@ValidDateRange class Booking { ... }` |
| `ANNOTATION_TYPE` | Another annotation | Enables **constraint composition** |
| `TYPE_USE` | A type-use site, especially generic container elements | `List<@SkuCode String> codes` |
| `CONSTRUCTOR` | Suitable constructor/return value declaration | Constraint applied to a constructor when required by the use case |

Annotations can be attached to properties, classes, or cross-parameter targets depending on the target types and validator. **`@Target(TYPE)` is not `@Target(TYPE_USE)`**: a class-level constraint evaluates the whole bean, whereas a constraint on a type argument evaluates each element of a container (when the provider has a value extractor).

### 4.1. If applied to a getter

~~~java
public class Product {
    private String sku;

    @SkuCode
    public String getSku() {
        return sku;
    }
}
~~~

This is an **illustrative class** using the defined annotation. The provider may treat an annotation on a getter as a property constraint. Do not accidentally place the same constraint on both the field and the getter of the same property, as this can lead to duplicate checks/violations.

### 4.2. If applied to a class

A rule that needs to compare two fields, such as `startDate <= endDate`, must receive the object containing both properties:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface DateRange {
    String message() default "{example.validation.DateRange.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is an **illustrative declaration fragment**, requiring appropriate imports and a `DateRangeValidator` class. A validator of the form `ConstraintValidator<DateRange, Booking>` can evaluate both start and end. Do not attach this type of constraint to a `String` and expect it to automatically check a relationship between two different fields.

### 4.3. If applied to list elements

~~~java
import java.util.List;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public class ProductBatch {
    @NotEmpty
    private List<@NotNull @SkuCode String> skus;
}
~~~

This is a **model fragment**. Each layer has its own responsibility:

- `@NotEmpty` outside the list: the list is neither null nor empty.
- `@NotNull` inside `<...>`: each element must not be null.
- `@SkuCode` inside `<...>`: each string element must match the format.
- If only `@SkuCode` is used and the validator is designed to allow null, a null element is considered valid with respect to this constraint alone.

`@Target(TYPE_USE)` makes Java syntax allow the annotation at that site; whether it executes also depends on the provider having a **`ValueExtractor`** compatible with the container. `List` is a standard container supported by Hibernate Validator.

## 5. Custom attributes: design the annotation API before writing the validator

A constraint annotation is an **API used directly by others**. Configuration attributes should:

- Have clear descriptive names, such as `prefix`, `digits` instead of `value1`, `flag`.
- Have sensible defaults if most cases share the same rule.
- Use annotation element types supported by Java: primitives, `String`, `Class`, enums, annotations, or arrays of these types.
- Not use dynamic runtime objects like `Clock`, `Service`, or `Pattern` as annotation elements: Java does not allow arbitrary object types as annotation elements.
- Document null, empty, whitespace, case sensitivity, and format behavior.
- Not contain sensitive data or values known only when a request arrives.

Example:

~~~java
@SkuCode(prefix = "SKU", digits = 3)
private String primarySku;

@SkuCode(prefix = "PART", digits = 5)
private String partNumber;
~~~

Both sites share the same **annotation definition** and validator, yet have distinct configurations. Inside the validator, use `initialize(SkuCode annotation)` to read the configuration and prepare the regex.

In Java, annotation attributes are effectively immutable metadata at runtime; if a constraint depends on the current date/time, inventory, or database, you cannot pass a service instance into an annotation attribute. Use a `ConstraintValidator` with appropriate dependency injection or move the logic to the service/domain layer.

### 5.1. Distinguishing `value()` and `message()`

Java allows an annotation to have an element named `value` to use shorthand syntax:

~~~java
public @interface AllowedPrefix {
    String value();
}
~~~

~~~java
@AllowedPrefix("SKU")
private String code;
~~~

This example **only illustrates Java syntax**; it is not yet a Jakarta constraint because it lacks `@Constraint` and the mandatory contract. `value()` is an ordinary attribute name, whereas `message()` is the Jakarta Validation element used as the error message. Do not rename `message()` to `value()`.

## 6. Designing a `ConstraintValidator` matching the annotation

With `@SkuCode` attached to a `String`, the implementation must be compatible:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class SkuCodeValidator
        implements ConstraintValidator<SkuCode, String> {
    // initialize(...) and isValid(...)
}
~~~

- The first generic parameter is the **annotation type** `SkuCode`.
- The second generic parameter is the **data type being validated**, here `String`.
- `initialize(SkuCode annotation)` reads the configuration attributes for each annotation descriptor.
- `isValid(String value, ConstraintValidatorContext context)` returns `true` if valid; `false` if invalid.
- The default message comes from the annotation's `message()` element and is interpolated by the provider on failure.

Usually, a custom validator should only check **format**, treating null as valid, while using `@NotNull` or `@NotBlank` alongside it when the field is required:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    return value == null || compiledPattern.matcher(value).matches();
}
~~~

This choice is intentional: "missing code" and "malformed code" are two distinct error causes. Not every constraint is required to treat null as valid; the designer must define this explicitly.

**Thread safety:** The provider may retain and invoke a validator multiple times, potentially concurrently. Do not store the request value currently being validated in a mutable field of the validator; preparing a `Pattern` configuration in `initialize` and reading it in `isValid` is a safe design pattern. Do not share a mutable `StringBuilder` across invocations.

## 7. The lifecycle of how Jakarta Validation processes `@Constraint`

When calling:

~~~java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    var violations = validator.validate(product);
}
~~~

The snippet above is a **method fragment** requiring the proper classes and imports. Conceptual steps:

1. The provider builds constraint metadata for the bean type.
2. The provider determines the active groups (`Default` or requested groups) and relevant properties/cascades.
3. For each constraint to check, it finds a `ConstraintValidator` compatible with the actual data type.
4. The provider creates and initializes the validator via `ConstraintValidatorFactory`; it may cache/reuse it per the implementation's strategy.
5. Calls `isValid(value, context)` to evaluate.
6. If `false`, creates a `ConstraintViolation` with message, path, invalid value, and descriptor metadata.
7. Returns `Set<ConstraintViolation<T>>`; **iteration order is not guaranteed**.

Do not write logic assuming "the first annotation on a field is guaranteed to run before the second annotation". If **group** ordering is needed, use `@GroupSequence`. `isValid` should avoid mutating input or accessing uncontrolled external sources.

## 8. Complete Maven/Java 17+ example: `@SkuCode`

The following example includes all files and compiles with Maven and Hibernate Validator. It demonstrates **annotation definition**, validator implementation, resource-bundle messages, optional null checking, and combined `@NotBlank` constraints.

### 8.1. Directory structure

~~~text
sku-constraint-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── validation/
        │           ├── SkuCode.java
        │           ├── SkuCodeValidator.java
        │           ├── ProductInput.java
        │           └── Demo.java
        └── resources/
            └── ValidationMessages.properties
~~~

### 8.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>sku-constraint-demo</artifactId>
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
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
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
~~~

Hibernate Validator 8 is a provider implementing Jakarta Validation 3.0, matching the Spring Boot 3 generation. `jakarta.el` here supplies the EL implementation for message interpolation. These versions are **pinned for example reproducibility**; in a real Spring Boot project, let the BOM/parent manage compatible dependencies.

### 8.3. `SkuCode.java`: annotation definition

~~~java
package example.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = SkuCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface SkuCode {
    String message() default "{example.validation.SkuCode.message}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    String prefix() default "SKU";
    int digits() default 3;
}
~~~

This is the main definition. `message` points to a key in `ValidationMessages.properties`; `prefix` and `digits` are parameters customizable at each usage site.

### 8.4. `SkuCodeValidator.java`: logic execution

~~~java
package example.validation;

import java.util.regex.Pattern;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class SkuCodeValidator
        implements ConstraintValidator<SkuCode, String> {

    private Pattern pattern;

    @Override
    public void initialize(SkuCode constraint) {
        int digits = constraint.digits();
        if (digits < 1) {
            throw new IllegalArgumentException(
                    "SkuCode.digits must be positive");
        }

        String expression = Pattern.quote(constraint.prefix())
                + "-[0-9]{" + digits + "}";
        pattern = Pattern.compile(expression);
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || pattern.matcher(value).matches();
    }
}
~~~

Key points:

- `Pattern.quote(prefix)` prevents a prefix containing special regex characters from being interpreted as a regular expression.
- `[0-9]` requires ASCII digits; if `\\d` were used, Unicode flag semantics might vary by regex configuration, which is unsuitable for fixed machine-readable codes.
- `matcher(value).matches()` requires the **entire string** to match the format, not just a substring.
- `initialize(...)` only reads the annotation configuration and prepares the `Pattern`; `isValid(...)` does not mutate state.
- Null **is accepted by `@SkuCode` alone**, because the requirement to have a code is handled by `@NotBlank`.
- Do not add `@Component` just for the provider to instantiate a simple validator; when Spring injection is needed, use a compatible factory infrastructure (section 14).

If you want to guard against invalid annotation configurations (`digits <= 0`), verify it with tests and choose a clear configuration error reporting strategy. This **is not** a user-input error case, since the configuration resides in annotation source code.

### 8.5. `ProductInput.java`: applying the annotation

~~~java
package example.validation;

import jakarta.validation.constraints.NotBlank;

public final class ProductInput {

    @NotBlank
    @SkuCode(prefix = "SKU", digits = 3)
    private final String sku;

    @NotBlank
    private final String title;

    @SkuCode
    private final String optionalAlternateSku;

    public ProductInput(
            String sku, String title, String optionalAlternateSku) {
        this.sku = sku;
        this.title = title;
        this.optionalAlternateSku = optionalAlternateSku;
    }
}
~~~

A getter is not required for Hibernate Validator to read **field-level constraints**; the provider can inspect fields via reflection per JavaBean validation rules. `optionalAlternateSku` does not have `@NotNull`/`@NotBlank`, so null is allowed under the contract above.

### 8.6. `ValidationMessages.properties`: message template

~~~properties
example.validation.SkuCode.message=Expected {prefix}-{digits} ASCII digits
~~~

With `@SkuCode(prefix = "SKU", digits = 3)`, the provider can interpolate the message to **`Expected SKU-3 ASCII digits`**. The `prefix` and `digits` annotation attributes are used in message interpolation; this is a message about the **format**, not a full example string representation. If you want a more intuitive message such as `Expected SKU- followed by exactly 3 digits`, you can rewrite the key in your product's language.

In this exercise, the program output below **does not depend on message text**, avoiding differences due to locale and provider.

### 8.7. `Demo.java`: running validation

~~~java
package example.validation;

import java.util.stream.Collectors;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class Demo {

    private static String invalidFields(
            Validator validator, ProductInput input) {
        return validator.validate(input).stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            ProductInput valid =
                    new ProductInput("SKU-007", "Coffee", null);

            ProductInput invalid =
                    new ProductInput("BAD-007", " ", null);

            ProductInput missingSku =
                    new ProductInput(null, "Coffee", null);

            ProductInput badOptional =
                    new ProductInput("SKU-007", "Coffee", "ALT-123");

            System.out.println("valid="
                    + validator.validate(valid).size());
            System.out.println("invalid="
                    + validator.validate(invalid).size());
            System.out.println("invalid-fields="
                    + invalidFields(validator, invalid));
            System.out.println("missing-sku="
                    + validator.validate(missingSku).size());
            System.out.println("bad-optional="
                    + validator.validate(badOptional).size());
        }
    }
}
~~~

Run from the project directory:

~~~bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.validation.Demo
~~~

**Stdout printed by the program** (excluding Maven, provider, or JVM notices):

~~~text
valid=0
invalid=2
invalid-fields=sku,title
missing-sku=1
bad-optional=1
~~~

Explanation:

1. `valid`: SKU `SKU-007` has the right prefix and three digits; title is valid; null optional code is allowed => **0** errors.
2. `invalid`: `BAD-007` violates `@SkuCode`, `title=" "` violates `@NotBlank` => **2** errors. Field names are sorted for deterministic ordering.
3. `missingSku`: `sku=null` violates `@NotBlank`, while `@SkuCode` **accepts null** => **1** error.
4. `badOptional`: `optionalAlternateSku="ALT-123"` is non-null and has the wrong prefix compared to the default `SKU` annotation => **1** error.
5. `validator.validate(...)` returns `Set<ConstraintViolation<ProductInput>>`; the error count is produced by the provider, not checked automatically by getters or constructors.

If you remove the Hibernate Validator dependency while keeping the annotation API, bootstrapping may fail to find a provider. If you run only `javac Demo.java` without a classpath, it will report a missing `jakarta.validation` package. Therefore this example **runs via Maven with dependencies**; do not claim it runs with plain Java without JARs.

### 8.8. Modification scenarios for self-testing

Try changing the values one by one:

- `SKU-123` => valid.
- `SKU-12` => invalid because there are only two digits.
- `SKU-1234` => invalid because there are four digits.
- `SKU-ABC` => invalid because they are not ASCII digits.
- `sku=""` => both `@NotBlank` and `@SkuCode` fail (there may be **2** violations on the same property).
- `sku=null` => only `@NotBlank` fails (**1** violation).
- `optionalAlternateSku=null` => `@SkuCode` accepts it.
- Change the annotation to `@SkuCode(prefix="PART", digits=5)` and test `PART-00125` => valid for the new configuration.
- Set `digits=0` => this is an **annotation configuration error**, not an input data error; the validator has a guard during initialization.

If you want to return **one** error when both `@NotBlank` and `@SkuCode` fail, do not force two constraints into one error automatically. You can choose a composition mechanism (`@ReportAsSingleViolation`) when designing a dedicated composed constraint, or handle field errors according to your API contract.

## 9. Customizing messages and internationalization

The standard element:

~~~java
String message() default "{example.validation.SkuCode.message}";
~~~

uses curly braces to reference a key in `ValidationMessages.properties`. Another usage:

~~~java
@SkuCode(
    prefix = "SKU",
    digits = 3,
    message = "Product code must match the SKU-### format")
private String sku;
~~~

This is a **field declaration fragment**. Writing the message inline at the usage site can be reasonable for a small case, but when i18n is needed, using a resource bundle key is usually clearer.

Message interpolation can use:

- `{prefix}` and `{digits}` for annotation attributes.
- Keys in `ValidationMessages.properties`.
- Locale from the validation provider/framework locale mechanism.
- Additional Jakarta Validation syntaxes, including expression language in supported contexts; avoid concatenating user-supplied content into message templates that might be evaluated.

**Do not confuse:** `message()` defines the **message template**; `ConstraintViolation#getMessage()` returns the **interpolated message**; `getMessageTemplate()` retrieves the **original template**. For public APIs, it is best to have stable error codes rather than classifying errors based on interpolated Vietnamese/English sentences.

In Spring, `MessageSource` can be used together with `LocalValidatorFactoryBean` to integrate messages; check how resource bundles and locales are configured to avoid losing the provider's default messages.

## 10. `groups()`, `Default`, and custom annotations

Every Jakarta Validation constraint can belong to one or more groups. Syntax in the annotation:

~~~java
Class<?>[] groups() default {};
~~~

Example using a custom constraint on publish:

~~~java
interface OnPublish {}

class DraftDocument {
    @SkuCode(groups = OnPublish.class)
    private String externalCode;
}
~~~

This is a **model fragment**. If `OnPublish` is an independent marker interface:

~~~java
validator.validate(document);                  // Default
validator.validate(document, OnPublish.class); // OnPublish
~~~

- The `Default` pass does **not** evaluate `@SkuCode` belonging solely to `OnPublish`.
- The `OnPublish` pass evaluates this constraint.
- Constraints without declared groups belong to `jakarta.validation.groups.Default`.
- Calling `validate(document, OnPublish.class)` does not automatically include `Default` unless inheritance or a sequence is designed.

In Spring:

~~~java
@Validated({Default.class, OnPublish.class})
@RequestBody DraftDocument body
~~~

This is an **illustrative controller parameter**, requiring imports for `org.springframework.validation.annotation.Validated`, `jakarta.validation.groups.Default`, and a suitable handler method. `@Validated` is Spring's annotation for **group selection**, distinct from Jakarta's standard `@Valid` for cascade/validation; the custom annotation's `groups` remain Jakarta groups.

Do not turn `Admin` or `Trusted` groups into an authorization mechanism. A DTO passing a validation group does not prove the caller has permission to perform the action.

## 11. Constraint composition: an annotation containing other constraints

Some rules need no custom Java logic. For instance, a display label must be non-blank and at most 20 characters long. You can create a **composed constraint** wrapping built-in ones:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.ReportAsSingleViolation;

@NotBlank
@Size(max = 20)
@ReportAsSingleViolation
@Documented
@Constraint(validatedBy = {})
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface ShortLabel {
    String message() default "Label must be nonblank and at most 20 chars";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is a **standalone illustrative annotation file** (choose a suitable package and filename `ShortLabel.java` in a project with Jakarta Validation). No `ShortLabelValidator` is needed because:

- `@NotBlank` and `@Size(max=20)` already define all the logic.
- `@Constraint(validatedBy={})` states there is no separate additional validator.
- The provider checks the composing constraints using standard **AND** combination semantics: every sub-rule must pass.
- `@ReportAsSingleViolation` requests representing one or more failing composing constraints as **a single violation on the composite constraint**, avoiding returning multiple child messages for the same annotation.
- If `@ReportAsSingleViolation` is omitted, violations from the respective composing constraints may be returned.

**Important:** In Jakarta Validation, composition defaults to **AND**. A Hibernate Validator extension allows other logical combination modes, but that is **not a standard portable API**. Do not attach two constraints to an annotation and assume they mean "A or B".

### 11.1. `@OverridesAttribute` when a composite attribute must control a child constraint

For example, to use `@ShortLabel(max=32)`, a custom annotation that merely has `int max()` **does not automatically forward** that value to the inner `@Size(max=20)`. Jakarta Validation provides `@OverridesAttribute(constraint=Size.class, name="max")` to reconfigure a composing constraint's attribute:

~~~java
import jakarta.validation.OverridesAttribute;
import jakarta.validation.constraints.Size;

@Size(max = 20)
public @interface LabelSize {
    @OverridesAttribute(constraint = Size.class, name = "max")
    int max() default 20;

    // When used as a complete @Constraint, you still must declare
    // @Constraint, @Target, @Retention, and message/groups/payload.
}
~~~

This snippet is a **syntax fragment to explain `@OverridesAttribute`**, not a complete annotation ready for production as-is. With repeated constraints, specify the index of the overridden constraint when necessary.

### 11.2. When to use composition instead of writing a validator

- Use composition if **all rules already exist** and their combination is equivalent to AND.
- Write a dedicated validator if the rule needs an algorithm, auxiliary data, or relationships across multiple fields.
- Avoid creating an annotation just to rename a built-in annotation without adding domain semantics; this makes the API harder to understand.
- If errors need a single aggregate message, consider `@ReportAsSingleViolation`.
- If you need to preserve individual constraint error codes, do not automatically merge all errors into one message.

## 12. Repeatable annotations: `@Repeatable` and nested `List`

Sometimes you want to apply **multiple instances of the same constraint type** on one element with different parameters. Java supports `@Repeatable`. A definition can add:

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(SkuCode.List.class)
public @interface SkuCode {
    // message/groups/payload/prefix/digits as in the standard definition

    @Target({
        ElementType.FIELD, ElementType.METHOD,
        ElementType.PARAMETER, ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    public @interface List {
        SkuCode[] value();
    }
}
~~~

This is an **add-on description fragment**, not a complete replacement file: keep `@Constraint`, `@Retention`, `@Target`, and the mandatory elements on the outer annotation. The `List` container must have compatible target and retention.

Two things to consider:

1. **Repeated constraints combine with AND by default**, not OR. If you write two `@SkuCode` annotations with completely different prefixes on one field, data may never satisfy both simultaneously.
2. `@Repeatable` is a Java syntactic declaration mechanism; the provider still evaluates each constraint instance with its own configuration. If business rules require "one of two formats", you usually need a combined validator or suitable composition mechanism, not simply repeating the same annotation.

Some standard Jakarta constraints provide a nested `List` to support multiple declarations; when creating a custom constraint, add repeatability only if there is a clear use case.

## 13. `payload()` for carrying extension metadata

Standard signature:

~~~java
Class<? extends Payload>[] payload() default {};
~~~

`Payload` is a Jakarta Validation marker interface; applications can use implementing types to attach metadata, such as warning display severity:

~~~java
import jakarta.validation.Payload;

public final class Severity {
    private Severity() {}

    public static final class Warning implements Payload {}
    public static final class Error implements Payload {}
}
~~~

Used at declaration:

~~~java
@SkuCode(payload = {Severity.Error.class})
private String sku;
~~~

This is a **field fragment** requiring `Severity` and `SkuCode` already defined. Metadata can be retrieved via:

~~~java
violation.getConstraintDescriptor().getPayload();
~~~

`payload` by itself **does not make the provider change HTTP status, severity, or UI rendering**. If the application wants to act on it, it must read the metadata and enforce its own policy. If unneeded, keep an empty array; do not design a "warning" system assuming the provider will automatically ignore violations.

## 14. Integrating into Spring Framework / Spring Boot

In Spring Boot 3.x, typical dependencies:

~~~xml
<!-- Dependency fragment in a project with Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

The snippet above **is not a complete pom.xml**. Spring 6 / Boot 3 uses the **`jakarta.validation`** namespace; older codebases typically used `javax.validation` and require compatible dependency/import migration.

### 14.1. Spring MVC triggering a custom constraint

When `ProductRequest` has a field:

~~~java
public record ProductRequest(
        @jakarta.validation.constraints.NotBlank
        @SkuCode String sku) {}
~~~

and a controller has:

~~~java
@PostMapping("/products")
public Map<String, String> create(
        @Valid @RequestBody ProductRequest request) {
    return Map.of("sku", request.sku());
}
~~~

These two snippets are **code fragments from a Spring MVC application**; they require imports, `@RestController`, Boot dependencies, and the `SkuCode` annotation in the same project. Spring MVC typically:

1. Uses Jackson to deserialize JSON from the request body into `ProductRequest`.
2. Triggers Jakarta Validation because of `@Valid`/`@Validated` on the parameter.
3. The provider reads `@SkuCode`, selects `SkuCodeValidator`, and calls `isValid`.
4. If invalid, on the standard argument validation path, Spring MVC may throw `MethodArgumentNotValidException` and return HTTP **400** by default.
5. If valid, the controller method proceeds with business logic.

Example JSON:

~~~json
{"sku":"BAD-001"}
~~~

If the DTO binds successfully and the validator is active, this SKU has the wrong prefix, so it fails the constraint. The actual HTTP error payload depends on `@ControllerAdvice`, Problem Details configuration, and Spring Boot; do not assert a single fixed error JSON shape everywhere.

If `@SkuCode` is placed on a field without a validation trigger point, the annotation is merely metadata. If `"sku":123` is sent and Jackson cannot convert it to String under the current configuration, a conversion error may occur **before** the custom validator runs.

### 14.2. Injection into validators in Spring

Some constraints need a service, such as checking whether a code is registered in a configuration table. Spring provides `LocalValidatorFactoryBean`, which normally configures `SpringConstraintValidatorFactory` to create validators and support Spring dependency injection.

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.springframework.beans.factory.annotation.Autowired;

public class RegisteredCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    private final CodeRegistry registry;

    @Autowired
    public RegisteredCodeValidator(CodeRegistry registry) {
        this.registry = registry;
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || registry.isRegistered(value);
    }
}
~~~

This is a **design fragment**, requiring `RegisteredCode`, `CodeRegistry`, and appropriate bean configuration, not a standalone runnable file. If bootstrapping a Jakarta Validator **plainly** via `Validation.buildDefaultValidatorFactory()` outside Spring without registering a custom factory, do not assume `@Autowired` will be processed.

**Architectural note:** Verifying codes against a DB on every validation call can cause N+1 queries, increase latency, and does not guarantee consistency at commit time. If uniqueness/existence is a critical data invariant, DB constraints, transactions, and service policies are still required; a custom constraint does not replace them.

### 14.3. Child beans and container elements in Spring

Custom constraints can be combined with `@Valid`:

~~~java
public class PurchaseRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private ProductRequest product;
}
~~~

If `product == null`, `@Valid` **skips cascading**; `@NotNull` enforces that the object is present. If the object is present, the provider validates `@SkuCode` on the field of `ProductRequest`. For `List<@SkuCode String>`, the constraint validates each string; add `@NotNull` on the type argument if you want to forbid null elements when the custom validator itself allows null.

## 15. Metadata API: introspecting constraint definitions

Beyond validation, Jakarta Validation has a **metadata API**. You can query the provider for declared constraints:

~~~java
var beanDescriptor =
        validator.getConstraintsForClass(ProductInput.class);

var propertyDescriptor =
        beanDescriptor.getConstraintsForProperty("sku");

if (propertyDescriptor != null) {
    for (var descriptor :
            propertyDescriptor.getConstraintDescriptors()) {
        System.out.println(
                descriptor.getAnnotation()
                          .annotationType().getSimpleName());
    }
}
~~~

The snippet above is a **fragment running inside a method that already has `validator` and class `ProductInput`**. On the `sku` property, for example, there are both `NotBlank` and `SkuCode`. The iteration order of descriptors is not guaranteed.

Metadata can help:
- Identify annotation types and groups.
- Access `getAttributes()` to inspect `prefix`/`digits`.
- Retrieve `getPayload()` to read marker metadata.
- Inspect the list of `ConstraintValidator` implementations recognized by the provider.
- Build tooling for documentation or project convention tests.

**Do not treat plain reflection as a validate call**: `ProductInput.class.getDeclaredField("sku").getAnnotation(SkuCode.class)` only reads the annotation; it does not run `isValid` and does not produce `ConstraintViolation`s. The Metadata API is a different facet of the same contract.

## 16. Reporting errors per property with `ConstraintValidatorContext`

By default, a validator attached to a field returning `false` produces a violation attached to that field. For a **class-level constraint** checking multiple fields, you sometimes want to attach the error to a specific property instead of the root object:

~~~java
@Override
public boolean isValid(Booking value,
                       ConstraintValidatorContext context) {
    if (value == null
            || value.getStart() == null
            || value.getEnd() == null) {
        return true;
    }

    boolean valid = !value.getEnd().isBefore(value.getStart());
    if (!valid) {
        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                "{example.validation.DateRange.message}")
               .addPropertyNode("end")
               .addConstraintViolation();
    }
    return valid;
}
~~~

This is a **method fragment** inside `ConstraintValidator<DateRange, Booking>`, requiring the `Booking` class and corresponding imports.

- `disableDefaultConstraintViolation()` suppresses the default violation for this constraint.
- `buildConstraintViolationWithTemplate(...)` creates a violation with the chosen message template.
- `addPropertyNode("end")` attaches the error to the `end` property.
- `addConstraintViolation()` is **mandatory** to complete the custom violation definition.
- `isValid` must still return `false` for the invalid case.

If you disable the default without building a replacement violation when returning false, the implementation may throw an error. Do not invoke the builder just for decoration when the method returns true.

**Scope limit:** Building constraint violations per property node is a validator task; the annotation definition still needs `@Constraint`/`@Target(TYPE)`/mandatory members as shown in the sections above.

## 17. Method and cross-parameter constraints: advanced cases

Most custom annotations validate **a single value** (field/parameter/property). If you need to compare **multiple parameters of the same method**, such as a method receiving `start` and `end`, you must create a *cross-parameter constraint*.

Per Jakarta Validation, a cross-parameter validator typically needs:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;

@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ConsistentDatesValidator
        implements ConstraintValidator<ConsistentDates, Object[]> {

    @Override
    public boolean isValid(
            Object[] values, ConstraintValidatorContext context) {
        // Check relationships across parameters.
        return true;
    }
}
~~~

This is an **illustrative fragment**, lacking real validation logic and `@ConsistentDates`; do not copy it as a complete business validator.

- Cross-parameter annotations typically target `METHOD`/`CONSTRUCTOR`.
- The validator receives `Object[]` containing the method parameters and is marked with `@SupportedValidationTarget(PARAMETERS)`.
- If an annotation supports **both** generic/return-value and cross-parameter targets, the specification requires an appropriate `validationAppliesTo()` attribute to disambiguate when target inference is ambiguous.
- Declaring a constraint on a method does **not** make an ordinary Java call validate automatically. You need `ExecutableValidator` or active Spring method validation integration (proxy/AOP or the appropriate MVC mechanism).

Do not add cross-parameter logic to every simple custom constraint; `@SkuCode` on `String` is a **generic constraint** and does not need `validationAppliesTo()`.

## 18. Exceptions: data errors vs annotation definition errors

When a user enters malformed data, a proper custom constraint returns `false` and the provider creates a `ConstraintViolation`. However, when the **constraint definition is broken**, the behavior is an **infrastructure/configuration** exception:

| Issue | Typical behavior/symptom | How to resolve |
| --- | --- | --- |
| Annotation missing `@Constraint` | Provider does not recognize it as a custom constraint | Add the proper meta-annotation |
| Missing `@Retention(RUNTIME)` | Metadata is not recognized properly | Use `RUNTIME` |
| Missing `message`/`groups`/`payload` or wrong types | `ConstraintDefinitionException` | Fix the annotation contract |
| `validatedBy` points to an incompatible validator | `UnexpectedTypeException` or validator resolution error | Check generic types and `@Target` |
| Two target validators overlap/cannot be resolved | `ConstraintDefinitionException`/`UnexpectedTypeException` depending on setup | Fix the `validatedBy` list |
| Annotation supports only String but placed on Long | `UnexpectedTypeException` | Change data type or add a compatible validator |
| Validator uses an uninjected service | Injection failure / null dependency | Use SpringConstraintValidatorFactory or proper wiring |
| `isValid` throws due to buggy code | `ValidationException` or provider-wrapped exception | Fix the validator; do not treat as normal invalid data |
| No provider on bootstrap | `NoProviderFoundException` | Add Hibernate Validator or a compatible provider |
| `@SkuCode` allows null on a required field | null does not produce a violation from the custom constraint | Combine with `@NotNull` or `@NotBlank` |
| Spring missing `@Valid` on request DTO | Custom constraint is not triggered at that point | Place the appropriate validation trigger annotation |
| Mixing `javax.validation` with `jakarta.validation` in Spring 6+ | Incompatible annotations/providers | Align namespaces and dependencies |

Do not automatically translate every `ValidationException` into HTTP 400 "bad user input". Configuration exceptions must be handled as programming/operational errors with proper logging/monitoring, without leaking stack traces to clients.

## 19. What should testing a custom annotation cover?

Beyond the happy path in the example, include the following tests:

| Test | Expectation |
| --- | --- |
| `"SKU-007"` with digits=3 | Valid |
| `"SKU-7"` with digits=3 | Violates `@SkuCode` |
| `"sku-007"` | Violates if policy is case-sensitive |
| `"SKU-ABC"` | Violates because not digits |
| `"SKU-1234"` | Violates because one extra digit |
| `"BAD-007"` | Violates prefix |
| `null` on field with only `@SkuCode` | Valid per designed contract |
| `null` on field with `@NotBlank @SkuCode` | Violates `@NotBlank` |
| `""` on field with both annotations | May produce two violations on the same property |
| `@SkuCode(prefix="PART",digits=5)` | Uses custom configuration properly |
| `List<@SkuCode String>` | Each element validated, with a provider supporting extractors |
| `groups=Publish.class` | Runs only on Publish or related groups |
| Reading constraint descriptor | Has expected annotation and attributes |
| Wrong type, e.g. Long | Detects configuration error `UnexpectedTypeException` |
| `digits=0` | Guard reports configuration error rather than silently accepting bad strings |

Best practices:

- Use standalone `ValidatorFactory` tests for pure algorithms.
- Use Spring integration tests if the validator has Spring dependency injection.
- Use MockMvc/WebMvcTest when checking HTTP status, binding, locale, and controller error mapping.
- Compare **property path / constraint annotation type / violation count**, without relying on `Set` iteration order or fixed interpolated messages when tests do not control locale.
- Test configuration attribute boundaries, including prefixes with regex metacharacters, Unicode digits, whitespace, null, and very long strings.
- If DB or network calls exist, test timeouts and dependency failures separately from invalid-input scenarios.

### 19.1. Testing logic without mocking Spring when there is no DI

The example in section 8 can be tested directly via Jakarta `Validator`, since the validator uses only `Pattern` and annotation attributes. That is a **unit/integration test at the validation provider layer**.

If validator logic relies on a Spring-managed collaborator, spin up an `ApplicationContext`/Spring Boot test to prove the collaborator is injected. Do not use a plain Jakarta test setup and assume it reflects the Spring environment.

## 20. When should you create a new annotation?

**Create a custom constraint** when:
- The rule is a **reusable** data property across multiple DTOs/properties.
- It has a concise, stable meaning like `@SkuCode`, `@ValidPhoneNumber`, `@ValidDateRange`.
- Semantics, null behavior, groups, and messages can be described independently.
- You want Spring/Jakarta Validation components to handle errors through the same mechanism.

**Prefer built-ins or composition** when:
- You only need `@NotBlank`, `@Size`, `@Pattern`, `@Email`, `@Positive`, etc.
- The rule is merely an AND combination of existing constraints.
- A custom annotation would just hide a simple regex without improving readability.

**Prefer service/domain validation** when:
- It needs DB data, transaction state, authorization, or race-condition handling.
- Validity depends on the logged-in user, roles, entity existence, or workflow state.
- The rule calls external systems or has side effects.
- Uniqueness/integrity constraints must be enforced by the DB even under concurrent requests.

A custom annotation is not a security boundary; data that "passed `@Valid`" must still be checked for business policies and access control.

## 21. Checklist for defining a standard-compliant constraint

Before using in production, verify:

- [ ] Annotation has `@Constraint(validatedBy=...)` pointing to an implementation or `{}` appropriately for composition.
- [ ] Has `@Retention(RUNTIME)`.
- [ ] `@Target` allows the exact intended placement sites.
- [ ] Has `String message() default ...`.
- [ ] Has `Class<?>[] groups() default {}`.
- [ ] Has `Class<? extends Payload>[] payload() default {}`.
- [ ] Custom attributes do not use reserved names or forbidden prefixes.
- [ ] Every `ConstraintValidator<A,T>` is genuinely compatible with the annotated type.
- [ ] `initialize` reads configuration; `isValid` holds no shared per-request state.
- [ ] Null behavior is explicitly documented and tested; add `@NotNull`/`@NotBlank` if needed.
- [ ] Message keys in `ValidationMessages.properties` are valid, and locales are tested if needed.
- [ ] A Bean Validation provider is on the classpath and used by the framework.
- [ ] Spring dependency injection is expected only when the factory supports it.
- [ ] Tests cover happy path, negative paths, invalid configuration, groups, and container/nested cases when applicable.
- [ ] Does not rely on configuration exceptions to report invalid input, and does not use constraints to replace security/service/DB checks.

## 22. Review questions

**Q1.** Why is a Java annotation with `@Retention(RUNTIME)` but missing `@Constraint` still not a Jakarta Validation constraint?

**A:** Because the provider only treats an annotation as a constraint when it defines the Jakarta contract, including `@Constraint` and standard elements; retention only keeps metadata alive at runtime.

**Q2.** What are the three mandatory elements?

**A:**

~~~java
String message() default "{my.Constraint.message}";
Class<?>[] groups() default {};
Class<? extends jakarta.validation.Payload>[] payload() default {};
~~~

**Q3.** Is `@Constraint(validatedBy={})` always wrong?

**A:** No. It is appropriate for a **composed constraint** that only uses other existing constraints and has no custom validator class.

**Q4.** To place `@SkuCode` on `List<@SkuCode String>`, which target is needed?

**A:** `TYPE_USE` allows the annotation on the type argument, and the provider needs a list-compatible extractor; avoid confusing it with `TYPE` (class-level constraint).

**Q5.** Why does `@SkuCode` in the example accept null?

**A:** The validator is designed to check format when a value is present; to make the field required, add `@NotBlank`/`@NotNull`.

**Q6.** What is the purpose of `String prefix() default "SKU"`?

**A:** It is a designer-created annotation attribute. It is passed to `initialize` via the annotation instance, allowing the validator to be reused with different prefixes.

**Q7.** When is `@ReportAsSingleViolation` used?

**A:** With composed constraints, it instructs reporting one aggregate violation when composing constraints fail, instead of multiple child violations.

**Q8.** Does placing a custom constraint directly on a service parameter run automatically during an ordinary Java method call?

**A:** No. You need `ExecutableValidator` or active method validation integration; in Spring AOP, the call must pass through the appropriate proxy.

**Q9.** A custom validator needs a Spring service via its constructor. Why is the `Validation.buildDefaultValidatorFactory()` demo insufficient?

**A:** Plain Jakarta bootstrapping does not use `SpringConstraintValidatorFactory` by default. You need Spring's `LocalValidatorFactoryBean` or a suitable factory infrastructure to handle dependency injection.

**Q10.** When an annotation is placed on a `Long` but only `ConstraintValidator<SkuCode,String>` exists, how should it be fixed?

**A:** Do not force the provider to convert Long to String automatically. Choose the right data type or write a compatible implementation if the requirement truly demands it; the usual error is `UnexpectedTypeException`.

## 23. Summary

- **`@Constraint` turns a Java annotation into a Jakarta Validation constraint definition** and binds it to an implementation via `validatedBy`.
- The annotation must have `RUNTIME` retention and the three standard elements `message`, `groups`, `payload` with exact signatures.
- `@Target` determines where it can be attached; `ConstraintValidator<A,T>` determines which data types can be validated and how they are evaluated.
- Attributes like `prefix`/`digits` make annotations reusable; `initialize` reads configuration and `isValid` executes logic.
- **Constraint composition** with `validatedBy={}` fits when combining existing constraints; `@ReportAsSingleViolation` controls aggregate error reporting.
- Null policy, groups, metadata, message bundles, and Spring injection are integral parts of annotation design, not minor details.
- In Spring MVC, `@Valid`/`@Validated` triggers validation after binding; annotation configuration errors differ from data errors.
- Create custom constraints only when they improve rule expressiveness and reusability. Do not use annotations to replace authorization checks, transactions, or database integrity.

### Official reference documentation

- Jakarta Validation 3.1 Specification – Constraint definition, annotation properties, implementation, and composition: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 API – `@Constraint`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint
- Jakarta Validation 3.1 API – `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraintvalidator
- Jakarta Validation 3.1 API – `@ReportAsSingleViolation`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/reportassingleviolation
- Hibernate Validator 8 Reference Guide – Custom constraints, constraint composition, and messages: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework – Configure Custom Constraints/LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework – Validation in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
