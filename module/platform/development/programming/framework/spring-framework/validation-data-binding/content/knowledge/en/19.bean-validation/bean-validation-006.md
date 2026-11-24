# ConstraintViolation and Violation Sets in Bean Validation

## 1. What Problem Does ConstraintViolation Solve?

In **Jakarta Bean Validation** (integrated by Spring Framework), an object can violate multiple constraints at once: a blank name, a malformed email, an age below the limit, and an address missing its city. `jakarta.validation.Validator.validate(bean)` does not just return a single "invalid data" message; it returns **a `Set<ConstraintViolation<T>>`**, where each `ConstraintViolation<T>` describes one failed constraint, the relevant location, and metadata about that constraint.

For example, a registration form can simultaneously return violations such as:

| Path (`propertyPath`) | Constraint | Illustrative Error Content |
| --- | --- | --- |
| `name` | `@NotBlank` | `name is required` |
| `email` | `@Email` | `email is invalid` |
| `age` | `@Min(18)` | `age must be 18 or older` |
| `address.city` | `@NotBlank` in a nested object | `city is required` |

**Key points:**

- **No violations** → empty result set: `violations.isEmpty() == true`. This is the condition typically used to decide whether data is valid with respect to **the constraints and groups requested for evaluation**.
- **One or more violations** → the set contains `ConstraintViolation<T>` objects. Each object can provide `getPropertyPath()`, `getMessage()`, `getInvalidValue()`, `getConstraintDescriptor()`, etc.
- `Validator.validate(...)` **normally returns a violation set and does not automatically throw `ConstraintViolationException` simply because data is invalid**. That exception may appear at another caller layer (such as AOP method validation or when explicitly thrown by the application).
- The `Set` **does not guarantee ordering**. If you need stable error JSON, comparable logs, or deterministic tests, sort the elements after reading them.
- The result reflects **that specific validation pass**; it is not a single immutable error list for the object at all times. When the object changes values, validation groups change, or configuration/provider changes, the result can differ.

Reading the violation set lets you return clear feedback on which fields failed, support forms with multiple simultaneous errors, write accurate tests, and avoid conflating input errors with infrastructure errors.

## 2. Three Main Components and Their Relationships

~~~text
Java object + constraint annotations
    @NotBlank  @Email  @Min  @Valid ...
                  |
                  v
    jakarta.validation.Validator
       validate(bean, groups...)
                  |
                  v
  Set<ConstraintViolation<T>>
           /             \
        empty          non-empty
          |                 |
    Valid for          Read propertyPath,
    this check         message, descriptor...
                           |
                    Application decides how
                    to handle / record errors
~~~

Distinguish commonly confused concepts:

| Component | Role |
| --- | --- |
| `jakarta.validation.Validator` | API for running Bean Validation; `validate`, `validateProperty`, and `validateValue` all return a `Set<ConstraintViolation<T>>`. |
| `jakarta.validation.ConstraintViolation<T>` | One **single violation** result accompanied by path, message, invalid value, and constraint data. |
| `Set<ConstraintViolation<T>>` | The set of violations belonging to one call. Do not convert to strings prematurely or important metadata will be lost. |
| `jakarta.validation.ConstraintViolationException` | Exception that can carry a violation set via `getConstraintViolations()`; not the same as the return type of `Validator.validate`. |
| `jakarta.validation.ValidationException` | Unrecoverable error in validation infrastructure, configuration, or provider; not a "wrong field" in the usual sense. |
| `org.springframework.validation.Errors` / `BindingResult` | Error model at the Spring binding/validation layer; may include `FieldError`s and type conversion errors, not directly a `Set<ConstraintViolation<?>>`. |
| `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Bridge between Jakarta Validator and Spring Validator; when used via the Spring interface, violations are adapted into Spring errors. |

Starting with Spring Framework 6 / Spring Boot 3, the standard API belongs to the `jakarta.validation.*` namespace. Older Spring 5/Boot 2 projects may use `javax.validation.*`. Do not arbitrarily mix `javax` annotations with a provider that only supports `jakarta`.

## 3. Three Ways to Obtain Violation Sets from Validator

### 3.1. validate(bean, groups...) — validate an object

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validate(orderForm);
~~~

`validate(bean)` evaluates constraints applied to the object, its properties, and **branches marked for `@Valid` cascading** within the active groups. For non-null input, the method may return an empty set or multiple violations. If `null` is passed directly as the source object to `validator.validate(null)`, the API throws `IllegalArgumentException`; this is not the way to validate a nullable field. Place `@NotNull` on the corresponding property/parameter and then validate the containing object or parameter.

### 3.2. validateProperty(bean, "propertyName", groups...)

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validateProperty(orderForm, "customerName");
~~~

Evaluates only constraints declared on the specified property. The name must be a valid JavaBeans property name, **not an arbitrary path expression**. By the Bean Validation contract, `@Valid` **is not executed for cascading** from `validateProperty`. To check the whole object tree, use `validate(bean)`.

### 3.3. validateValue(BeanType.class, "propertyName", value, groups...)

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validateValue(OrderForm.class, "customerName", "");
~~~

Simulates validating a property value **without creating an instance** of the bean. This is useful when checking a single form field before saving. Because there is no root instance, violations from `validateValue` have `getRootBean() == null` and `getLeafBean() == null`. `@Valid` does not cascade in this mode. `getRootBeanClass()` still identifies the relevant bean class.

Comparison:

| Method | Real instance? | Scope | `@Valid` cascade | `getRootBean()` |
| --- | --- | --- | --- | --- |
| `validate(bean)` | Yes | Bean and cascaded branches | Yes | Root bean |
| `validateProperty(bean, "x")` | Yes | Constraints on property `x` | No | Root bean |
| `validateValue(Type.class, "x", value)` | No | Constraints on hypothetical value for `x` | No | `null` |

All three APIs accept varargs `Class<?>... groups`. When no group is passed, Bean Validation uses `jakarta.validation.groups.Default`.

### 3.4. Method/constructor validation

For constraints on parameters or return values of methods/constructors, Jakarta Bean Validation has `ExecutableValidator` obtained via `validator.forExecutables()`. Methods like `validateParameters(...)` and `validateReturnValue(...)` also return a `Set<ConstraintViolation<T>>`, though `propertyPath` may include **method nodes, parameter nodes, and return value nodes**. Spring has its own method validation integration, covered in section 11.

## 4. Reading a ConstraintViolation Properly

Suppose:

~~~java
for (ConstraintViolation<OrderForm> violation : violations) {
    String path = violation.getPropertyPath().toString();
    String message = violation.getMessage();
    System.out.println(path + ": " + message);
}
~~~

This is an illustrative snippet requiring a `violations` variable; iteration order of `Set` is not guaranteed. Key methods:

| API | Return Value | Practical Meaning |
| --- | --- | --- |
| `getMessage()` | `String` | Message after interpolation, e.g., `"must not be blank"` or a custom message. |
| `getMessageTemplate()` | `String` | Original template, e.g., `"{jakarta.validation.constraints.NotBlank.message}"`; useful to distinguish template from rendered text. |
| `getPropertyPath()` | `jakarta.validation.Path` | Path to the violating element from the root: property, collection element, method parameter... |
| `getInvalidValue()` | `Object` | The value **passed to the constraint validator that failed**; may be `null`, an object, or a collection element. |
| `getRootBean()` | `T` or `null` in special contexts | Root instance being validated; `validateValue` has no instance so it returns null. |
| `getRootBeanClass()` | `Class<T>` | Root bean class; still useful when `getRootBean()` is unavailable. |
| `getLeafBean()` | `Object` or `null` | Closest bean to the constraint, e.g., the `Address` bean when `address.city` fails; `validateValue` returns null. |
| `getConstraintDescriptor()` | `ConstraintDescriptor<?>` | Metadata of the violated constraint, annotation, `min`/`max` attributes, groups, payload... |
| `getExecutableParameters()` | `Object[]` or `null` | Invocation arguments when the violation belongs to executable validation. |
| `getExecutableReturnValue()` | `Object` or `null` | Method/constructor return value when applicable; may be null if the method returned null. |
| `unwrap(SomeProviderClass.class)` | Provider-dependent | Exposes provider-specific APIs; may throw `ValidationException` when unsupported. |

**Do not treat `getMessage()` as a stable error identifier**: the message can vary by locale or message bundle. If an API needs a stable `code`, use the annotation type (e.g., `NotBlank`), a dedicated business code, or defined metadata. Likewise, do not directly expose `getInvalidValue()` to clients; it can contain passwords, emails, tokens, or entire object graphs.

### getMessage() vs getMessageTemplate()

~~~java
String rendered = violation.getMessage();
String template = violation.getMessageTemplate();
~~~

For example, using `@Size(min = 2, max = 10)` with the default message: the template may be a message key, while rendered in a given locale may be `size must be between 2 and 10`. If the annotation declares `message = "age must be 18 or older"`, both may match since no interpolation is needed.

The locale is determined by the message interpolator configuration and invocation context. Spring can integrate `MessageSource`, so tests should choose appropriate assertions; avoid hardcoding the provider's English messages into APIs without controlling the locale.

### Metadata from ConstraintDescriptor

~~~java
String annotationName = violation
    .getConstraintDescriptor()
    .getAnnotation()
    .annotationType()
    .getSimpleName();

Map<String, Object> attributes =
    violation.getConstraintDescriptor().getAttributes();
~~~

For instance, `@Min(18)` has attribute `value = 18`. `getAttributes()` may also include `message`, `groups`, `payload`, or custom attributes. Metadata is suitable for internal logging or building controlled return codes; you should not serialize the entire descriptor directly to JSON, as it may contain `Class<?>`, annotations, and unnecessary details.

## 5. Understanding propertyPath: From Simple Fields to Nested Collections

`getPropertyPath()` returns a `Path` object, not a plain JavaBeans string. Converting to String via `toString()` is convenient for messages, but for accurate structural handling you can iterate each `Path.Node`.

| Context | Illustrative Path | What to Understand |
| --- | --- | --- |
| Direct property | `email` | One property node. |
| Nested bean via `@Valid` | `address.city` | The violation sits in the `Address` bean while the root remains its parent bean. |
| Constrained list element | `tags[1].<list element>` | Element at index 1 of `tags` is invalid; exact String form depends on container type and provider. |
| Map value | `labels[HOME].<map value>` | The Map key can appear in the path. |
| Class-level constraint | Empty path for root bean | You cannot assume every error has a field name. |
| Method parameter | `submit.arg0` or real parameter name | Parameter names depend on metadata/parameter name provider; do not treat `arg0` as a stable API contract. |

Node traversal example:

~~~java
import jakarta.validation.Path;

for (Path.Node node : violation.getPropertyPath()) {
    System.out.println(
        "kind=" + node.getKind()
        + ", name=" + node.getName()
        + ", inIterable=" + node.isInIterable()
        + ", index=" + node.getIndex()
        + ", key=" + node.getKey());
}
~~~

This is an illustrative snippet using an existing `violation` variable. Nodes can have kinds `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT`, `METHOD`, `PARAMETER`, `RETURN_VALUE`, etc. For list elements, `getIndex()` helps identify position; Maps can use `getKey()`. Do not use `String.split("\\.")` to parse every path: collection paths have index/key notation and special node names.

### Misconceptions about root, leaf, and invalid value

For `OrderForm.address.city` failing `@NotBlank`:

- `getRootBean()` is the `OrderForm` instance passed to `validate`.
- `getLeafBean()` is typically the `Address` instance containing the `city` property.
- `getInvalidValue()` is the checked `city` value, such as `" "`; it is not the entire `Address` by default.
- `getRootBeanClass()` is `OrderForm.class`.

For a class-level constraint `@ValidOrder` on the root, `getPropertyPath()` may be empty and `getInvalidValue()` may be the entire validated object. With `validateValue(...)`, root/leaf instances do not exist so both are null. With method/constructor validation, root/leaf definitions depend on constraint placement; do not apply a single field-only rule to every case.

## 6. Runnable Java 17 Example: Collecting Four Violations and Processing the Set

This example runs with **Java 17 + Maven + Hibernate Validator 8.0.6.Final (Jakarta Validation 3.0)**. Hibernate Validator is an *implementation/provider* of Jakarta Bean Validation. The `jakarta.validation-api` dependency alone only contains the API and does not supply an execution engine.

Project structure:

~~~text
bean-validation-violations/
├── pom.xml
└── src/
    ├── main/java/demo/ViolationsDemo.java
    └── test/java/demo/ViolationsDemoTest.java
~~~

`pom.xml` file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-validation-violations</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `org.glassfish.expressly:expressly` dependency provides Jakarta Expression Language for message interpolation when running standalone Java SE. When running in an environment that already supplies EL, dependency policies may differ.

`src/main/java/demo/ViolationsDemo.java` file:

~~~java
package demo;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ViolationsDemo {

    static final class Address {
        @NotBlank(message = "city is required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Account {
        @NotBlank(message = "name is required")
        private final String name;

        @Email(message = "email is invalid")
        @NotBlank(message = "email is required")
        private final String email;

        @Min(value = 18, message = "age must be 18 or older")
        private final int age;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        Account(String name, String email, int age, Address address) {
            this.name = name;
            this.email = email;
            this.age = age;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Account invalid = new Account(
                " ", "not-an-email", 16, new Address(" "));

            Set<ConstraintViolation<Account>> violations =
                validator.validate(invalid);

            System.out.println("violations=" + violations.size());

            // Set does not guarantee order; sort for stable output.
            violations.stream()
                .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
                .sorted()
                .forEach(System.out::println);

            Account valid = new Account(
                "An", "an@example.com", 21, new Address("Ha Noi"));
            System.out.println(
                "valid=" + validator.validate(valid).size());

            System.out.println(
                "property(name)=" +
                validator.validateProperty(invalid, "name").size());

            Set<ConstraintViolation<Account>> hypothetical =
                validator.validateValue(Account.class, "age", 16);

            System.out.println(
                "value(age)=" + hypothetical.size());
            System.out.println(
                "value-root-null=" +
                (hypothetical.iterator().next().getRootBean() == null));
        }
    }
}
~~~

Run command from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ViolationsDemo
~~~

Stdout produced by the program (Maven and the provider may print additional environment logs):

~~~text
violations=4
address.city -> city is required
age -> age must be 18 or older
email -> email is invalid
name -> name is required
valid=0
property(name)=1
value(age)=1
value-root-null=true
~~~

**Analyzing why there are exactly four violations:**

1. `name = " "` is rejected by `@NotBlank` (a String containing whitespace still lacks non-whitespace text).
2. `email = "not-an-email"` is not a valid email address per `@Email`; `@NotBlank` passes because the string is not empty.
3. `age = 16` is less than `@Min(18)`.
4. `address.city = " "` violates `@NotBlank`. The constraint is found because `address` has `@Valid` requesting cascading into `Address`.
5. `@NotNull` on `address` is not violated in this example because an `Address` object is present.

Two extra prints confirm that `validateProperty(invalid, "name")` checks only `name`, and `validateValue(Account.class, "age", 16)` checks a hypothetical property without a root instance.

The violation set is converted to strings and `sorted()` **only for deterministic display**. Do not rely on the provider's actual iteration order or assume the "first violation" is the most important error. If more constraints are added or data changes later, both count and post-sort order may change accordingly.

## 7. Real Tests Actually Inspect the Result Set

`src/test/java/demo/ViolationsDemoTest.java` file:

~~~java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ViolationsDemoTest {

    @Test
    void collectsAllExpectedPaths() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                " ", "not-an-email", 16,
                new ViolationsDemo.Address(" "));

            Set<ConstraintViolation<ViolationsDemo.Account>> errors =
                validator.validate(bean);

            assertEquals(4, errors.size());
            Set<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertEquals(
                Set.of("name", "email", "age", "address.city"),
                paths);
        }
    }

    @Test
    void validBeanReturnsEmptySet() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                "An", "an@example.com", 22,
                new ViolationsDemo.Address("Ha Noi"));

            assertTrue(validator.validate(bean).isEmpty());
        }
    }

    @Test
    void validateValueHasNoRootBean() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var errors = validator.validateValue(
                ViolationsDemo.Account.class, "age", 17);

            assertEquals(1, errors.size());
            assertNull(errors.iterator().next().getRootBean());
            assertEquals("age",
                errors.iterator().next().getPropertyPath().toString());
        }
    }

    @Test
    void validatePropertyDoesNotCascade() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                "An", "an@example.com", 22,
                new ViolationsDemo.Address(" "));

            // address itself is non-null; validateProperty does not
            // follow @Valid to check address.city.
            assertTrue(
                validator.validateProperty(bean, "address").isEmpty());

            // validate(bean) does cascade.
            assertEquals(1, validator.validate(bean).size());
        }
    }
}
~~~

Command:

~~~bash
mvn test
~~~

With the dependencies listed above, **4 passing tests** are expected. The tests are far more reliable than merely asserting `!violations.isEmpty()`, because they assert the exact property paths and semantics of each validation method. Avoid writing tests that rely on `violations.iterator().next()` when multiple elements exist and you do not know which element comes first.

In real projects, each scenario should also test metadata contents, validation groups, null fields, and nested collections if required by the application. Localized user-facing messages should be tested with an explicit locale.

## 8. From Set<ConstraintViolation<T>> to an API Error List

An interface usually needs JSON containing `field`, `code`, and `message`, rather than the entire complex `ConstraintViolation` object.

Example DTO and mapping function. This is an **illustrative standalone mapping snippet**, placed in a utility class with the required imports:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import jakarta.validation.ConstraintViolation;

record ValidationError(String field, String code, String message) {}

static <T> List<ValidationError> toErrors(
        Set<ConstraintViolation<T>> violations) {
    return violations.stream()
        .map(v -> new ValidationError(
            v.getPropertyPath().toString(),
            v.getConstraintDescriptor().getAnnotation()
                .annotationType().getSimpleName(),
            v.getMessage()))
        .sorted(Comparator
            .comparing(ValidationError::field)
            .thenComparing(ValidationError::code))
        .toList();
}
~~~

Given the violation set from the section 6 example, the represented data would look like:

~~~json
[
  {"field":"address.city","code":"NotBlank","message":"city is required"},
  {"field":"age","code":"Min","message":"age must be 18 or older"},
  {"field":"email","code":"Email","message":"email is invalid"},
  {"field":"name","code":"NotBlank","message":"name is required"}
]
~~~

The `code` strings in the example use annotation names for illustration; for a public API that must remain stable across provider/annotation changes, define a dedicated catalog of **business error codes** and map explicitly. `getMessage()` is for display; `getMessageTemplate()` and descriptors help identify the message source. Do not turn translated messages into logic-branching keys.

A single field can violate **multiple constraints** simultaneously, such as `@NotBlank` and `@Size(min=8)`. Therefore JSON should use **an array of errors**, rather than carelessly converting straight to `Map<String,String>` which keeps only the last message per field. If clients want grouping by field, use `Map<String,List<ValidationError>>` or `Map<String,List<String>>`.

The result set may contain object/class-level errors with an empty `propertyPath`. Do not drop them; present them under a `"_global"` key or an agreed object-level error type in the API.

## 9. ConstraintViolationException: Distinct from the Set Returned by validate()

The following two snippets have different meanings:

~~~java
Set<ConstraintViolation<ViolationsDemo.Account>> errors =
    validator.validate(account);

// Only returns a Set; does not automatically throw for an invalid bean.
~~~

~~~java
if (!errors.isEmpty()) {
    throw new jakarta.validation.ConstraintViolationException(
        "Account validation failed", errors);
}
~~~

This is an **illustrative snippet** assuming `validator` and `account` from the section 6 example. `validate(...)` itself returns a set. The `throw` part is an application decision and alters control flow.

Catching the exception when it is actually thrown:

~~~java
try {
    // Execute an operation that may throw ConstraintViolationException.
} catch (jakarta.validation.ConstraintViolationException ex) {
    for (var violation : ex.getConstraintViolations()) {
        System.out.println(
            violation.getPropertyPath() + ": " + violation.getMessage());
    }
}
~~~

`ConstraintViolationException.getConstraintViolations()` provides the violation set for handling just like `Validator.validate`. It may come from method validation or application code. Do not assume a failing Spring MVC request always throws this exact exception; Spring uses other adapted exceptions on its respective execution paths (see section 11).

**Error classification:** `ConstraintViolationException` reports failed constraints; `ValidationException` in general can indicate configuration/provider/metadata failures and should not all be treated automatically as user input errors. For instance, declaring the wrong constraint on a Java type can throw `UnexpectedTypeException`, a subtype of `ValidationException`. Log/monitor programming errors separately and return an appropriate system status.

## 10. Constraint Groups, Cascading, and Why the Result Set Changes

### 10.1. Groups control scope

By default, `validator.validate(bean)` checks the `Default` group. Example:

~~~java
interface RegistrationChecks {}

class RegistrationForm {
    @NotBlank
    String username;

    @NotBlank(groups = RegistrationChecks.class)
    String referralCode;
}
~~~

This is an **illustrative declaration snippet**, requiring the `jakarta.validation.constraints.NotBlank` import. For a `RegistrationForm` with both fields blank:

~~~java
validator.validate(form);                          // Default: username
validator.validate(form, RegistrationChecks.class); // Only referralCode
validator.validate(form, jakarta.validation.groups.Default.class,
                    RegistrationChecks.class);     // Both groups
~~~

`violations.isEmpty()` must not be read as "the object is always valid for all groups". It is only valid for the groups and configuration requested in **that invocation**.

If a specific validation order is needed, use `@GroupSequence`. When an earlier group has violations, subsequent groups in the sequence are not evaluated per group-sequence rules. Requesting multiple groups without a sequence **does not guarantee evaluation order**.

### 10.2. @Valid causes nested paths to appear

In the runnable example, `@Valid` on `Account.address` causes `Address.city`'s `@NotBlank` to be evaluated. Removing `@Valid` makes `validate(account)` check only `address`'s `@NotNull` without descending into `city`. Then the violation set is smaller, even though data inside `Address` has not changed.

For lists, constraints can be declared directly on elements:

~~~java
import java.util.List;
import jakarta.validation.constraints.NotBlank;

class RequestData {
    List<@NotBlank String> tags;
}
~~~

This is an **illustrative snippet** needing a bean holding the field. If `tags` contains `"ok"` and `""`, the provider may produce a violation with a path like `tags[1].<list element>`. The returned path is a `Path` object with an index; the exact string representation depends on container, metadata, and provider. To validate properties **inside a child object** of a list, use `List<@Valid Child>`; `List<@NotBlank String>` validates the String element itself.

### 10.3. Do you always receive "all errors"?

You should never unconditionally promise that every constraint across every group will appear in a single call. Results also depend on:

- Only constraints belonging to the requested groups are evaluated.
- `@Valid` determines cascade scope; `validateProperty`/`validateValue` do not cascade.
- Group sequences can short-circuit after a group with violations.
- Hibernate Validator has a **fail-fast** option (not a portable default of the Jakarta API) to stop early upon finding a violation; in that case, do not expect the full list.
- An application-written class-level constraint can produce multiple violations with custom paths via `ConstraintValidatorContext`.
- Method/constructor validation has a different scope from object validation.

**If the goal is to display all form errors**, verify groups, cascading, and fail-fast in your actual configuration, then write tests for cases with multiple simultaneous errors.

## 11. ConstraintViolation in Spring Framework: Seeing Each Processing Path Clearly

### 11.1. Using jakarta.validation.Validator directly in services

Spring Framework can create a `LocalValidatorFactoryBean`, a bridge implementing both `jakarta.validation.Validator` and `org.springframework.validation.Validator`. For a service that only wants `Set<ConstraintViolation<T>>`, inject the Jakarta interface directly.

Example **integration snippet** in a Spring application with a Bean Validation provider:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
    private final Validator validator;

    public AccountService(Validator validator) {
        this.validator = validator;
    }

    public void register(AccountRequest request) {
        Set<ConstraintViolation<AccountRequest>> errors =
            validator.validate(request);
        if (!errors.isEmpty()) {
            throw new ConstraintViolationException(
                "Account request invalid", errors);
        }
        // Save account after business logic confirms validity.
    }
}
~~~

This is an integration snippet, not standalone: it requires `AccountRequest` as a constrained DTO, importing `java.util.Set`, Spring beans, and application persistence infrastructure. The key point is that Spring injects `jakarta.validation.Validator`, while the application decides how to handle the Set. Do not treat Spring's `LocalValidatorFactoryBean` as a `ConstraintViolation`; it is the execution engine.

If code uses `org.springframework.validation.Validator` instead of Jakarta Validator, results are obtained via `Errors` / `BindingResult`, not the `Set<ConstraintViolation<T>> validate(T)` signature. Import carefully since both packages use the name `Validator`.

### 11.2. @Valid + @RequestBody/@ModelAttribute in Spring MVC

~~~java
@PostMapping("/accounts")
public ResponseEntity<Void> create(
        @Valid @RequestBody AccountRequest request) {
    accountService.register(request);
    return ResponseEntity.noContent().build();
}
~~~

This is an **illustrative controller snippet** with appropriate Spring Web MVC imports, not a standalone runnable class.

When Spring MVC validates a single command object with `@Valid` and no `BindingResult`/`Errors` appears immediately after the parameter (and method-level validation is not triggered for the method), Spring typically reports the failure via `MethodArgumentNotValidException`. This exception provides `BindingResult` and `FieldError`/`ObjectError`. The Jakarta-layer result set has been adapted for Spring's infrastructure; **do not cast `FieldError` to `ConstraintViolation<?>`**.

To return a response directly inside the controller on binding errors, add a `BindingResult` parameter immediately after the object:

~~~java
@PostMapping("/accounts/check")
public ResponseEntity<?> check(
        @Valid @RequestBody AccountRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest()
            .body(bindingResult.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .toList());
    }
    return ResponseEntity.ok("valid");
}
~~~

This is also an **illustrative snippet** needing imports and `AccountRequest` in the application; it merely shows how `BindingResult` is used. For production APIs, use a stable error DTO and control response contents instead of passing raw strings.

### 11.3. Controller method validation in Spring MVC 6.1+

If a controller parameter directly carries a constraint such as `@Min`/`@NotBlank`, or a return value carries a constraint, Spring MVC 6.1+ supports method validation and errors may be raised as **`HandlerMethodValidationException`**. This is a separate mechanism carrying per-parameter data; it is not identical to `MethodArgumentNotValidException` for individual objects.

Example direct parameter declaration:

~~~java
@GetMapping("/accounts/{id}")
public String find(@PathVariable @Min(1) long id) {
    return "account=" + id;
}
~~~

With `id=0`, the direct `@Min(1)` constraint requires method validation. In Spring MVC 6.1+ with the built-in mechanism enabled, the handler can throw `HandlerMethodValidationException`. In projects with class-level `@Validated` or special method-proxy configurations, the error flow can differ; verify your version and registration setup.

### 11.4. Service method validation via AOP

For a Spring bean using `@Validated` and `MethodValidationPostProcessor` (typically configured by Spring Boot with the validation starter), a **proxied** call to a constrained method throws `jakarta.validation.ConstraintViolationException` by default. When configured with `MethodValidationPostProcessor.setAdaptConstraintViolations(true)`, Spring uses `MethodValidationException` with the `MethodValidationResult`/`ParameterValidationResult` model instead.

Do not assume AOP proxy errors always match built-in controller method validation, or that internal self-calls on the same instance (`this.someMethod()`) pass through the proxy. When automatic enforcement is needed, test calling through the actual Spring bean.

### 11.5. Table for Picking the Right Error API

| Where It Occurs | Common Result Handling |
| --- | --- |
| Java code calling `validator.validate(bean)` | `Set<ConstraintViolation<T>>`; application checks `isEmpty()`. |
| Code manually throwing `ConstraintViolationException` after `validate` | Catch exception and call `getConstraintViolations()`. |
| Spring MVC `@Valid @RequestBody` validating a single object | `MethodArgumentNotValidException` or `BindingResult` depending on controller signature. |
| Spring MVC direct method constraint, built-in 6.1+ | `HandlerMethodValidationException`. |
| `@Validated` service via method-validation AOP | `ConstraintViolationException` by default, or `MethodValidationException` if adapted. |
| Spring DataBinder/Spring Validator | `Errors`/`BindingResult`, `FieldError`/`ObjectError`. |

Reading the exact exception type and actual payload at the boundary helps build a unified API error format regardless of whether errors come from Bean Validation, binding, or method validation.

## 12. Safe and Clear Error Handling in REST APIs

When converting violations into client-facing messages, follow this workflow:

1. **Classify the source**: Bean Validation, conversion/type mismatch, business rule errors, and infrastructure errors do not necessarily share the same handling.
2. **Preserve every violation**: multiple errors on the same field remain intact; you can sort by path/code.
3. **Choose the right field path**: nested paths, collection indices, Map keys, and class-level errors should be represented in a controlled manner.
4. **Return friendly messages**: apply the configured locale or message bundle, avoiding reliance on the host's default language.
5. **Do not leak sensitive data**: avoid returning `getInvalidValue()`, `rootBean`, stack traces, internal class names, or unnecessary metadata.
6. **Pick HTTP status at the boundary**: invalid request data normally maps to HTTP 400, whereas validation configuration/infrastructure errors must not be masked as 400. Exact status routing is decided by the application's exception handler.
7. **Test multiple simultaneous errors**: verify results as a set, not by an arbitrary element index.

For instance, a `@RestControllerAdvice` can handle `MethodArgumentNotValidException` and build a DTO from `BindingResult.getFieldErrors()`, alongside a separate handler for `HandlerMethodValidationException`. If services throw `ConstraintViolationException`, handle that exception as well, returning only a DTO stripped of sensitive data. Do not write a catch-all handler for `ValidationException` and treat every instance as bad user input.

## 13. Common Real-World Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Calling `validator.validate(bean);` and ignoring the result | Invalid data continues processing as if valid. | Capture `Set<ConstraintViolation<T>>`, check `isEmpty()`, return errors/block per business logic. |
| Thinking `validate(bean)` always throws an exception | The method contract returns a `Set`. | Separate violation results from exception handling. |
| Treating `violations.iterator().next()` as the "first error" | `Set` does not guarantee ordering. | Sort by field/code or apply an explicit priority rule. |
| Building `Map<String,String>` and overwriting messages | One property can violate multiple constraints. | Use a list of errors or `Map<String,List<...>>`. |
| Comparing `getMessage()` as a fixed error code | Messages depend on locale/template. | Use an explicit code, descriptor, or controlled message template. |
| Including `getInvalidValue()` in responses/logs | Can leak email, password, token, or internal objects. | Filter logs and return safe field/code/message values. |
| Omitting `@Valid` with nested objects | Deep violations may go undetected. | Place cascade on references that need validation; test nested properties. |
| Using `validateProperty` and expecting cascade | This API does not trigger `@Valid` cascading. | Use `validate(bean)` to inspect the entire graph. |
| Calling `validateValue` and reading `getRootBean()` | No bean instance exists, so root/leaf return null. | Use `getRootBeanClass()` and `getPropertyPath()`. |
| Using `String.split("\\.")` to parse all paths | Collections/Maps have indices/keys and special nodes. | Traverse `Path.Node` when exact structure is needed. |
| Assuming `isEmpty()` proves every group passed | Only the requested groups are checked. | Specify groups/sequences and write tests. |
| Enabling fail-fast and promising to display all errors | The provider can stop early. | Disable fail-fast if the UI requires all errors. |
| Casting `BindingResult` to `ConstraintViolation` | They are two different data models. | Use dedicated adapters/mappers for Spring Errors. |
| Catching only `ConstraintViolationException` in MVC | Spring MVC uses other exception types too. | Distinguish `MethodArgumentNotValidException` and `HandlerMethodValidationException`. |
| Lumping provider config errors with form errors | `ValidationException` can indicate a server bug. | Classify and monitor infrastructure errors separately. |
| Mixing `javax` annotations with a `jakarta` provider | Incompatible in upgraded projects. | Align namespaces with your Spring/Boot and provider versions. |

## 14. Self-Check Checklist

- [ ] Project has a working **Bean Validation provider** (not just the API/annotations).
- [ ] Constraints are placed on the right fields, properties, classes, or methods, with proper groups.
- [ ] Objects/lists needing nested validation declare `@Valid` or appropriate container element constraints.
- [ ] `validate`, `validateProperty`, and `validateValue` are clearly distinguished.
- [ ] Logic checks `violations.isEmpty()` rather than ignoring the return value.
- [ ] Code does not depend on `Set` ordering; API results are sorted when needed.
- [ ] Errors are not overwritten when multiple constraints fail on the same property.
- [ ] `getInvalidValue()` and raw root objects are not returned in responses.
- [ ] Tests exist for valid data, multiple simultaneous errors, nested paths, and groups if used.
- [ ] Appropriate handlers exist for `ConstraintViolationException`, `MethodArgumentNotValidException`, and `HandlerMethodValidationException` matching actual paths.
- [ ] Display messages and error codes are separated; system errors are not disguised as input errors.

**Knowledge self-check**

1. Why does `validator.validate(bean)` return a `Set` instead of a single String?
2. When all constraints in the requested groups pass, what does the returned set contain?
3. Why is `getRootBean()` null on a violation from `validateValue`?
4. For `address.city`, what two instances can `getRootBean()` and `getLeafBean()` represent?
5. Why should two iterations over the same `Set` not be treated as error priority order?
6. For `@Valid @RequestBody` in Spring MVC, why do you typically receive `MethodArgumentNotValidException` instead of the Set directly?
7. Does enabling provider fail-fast help display **all errors** at once?

**Answers:** (1) each failed constraint can produce its own metadata, and an object can have multiple errors; (2) an empty set; (3) there is no bean instance in hypothetical validation; (4) the root bean containing `address` and the `Address` bean containing `city`; (5) `Set` does not guarantee order; (6) Spring adapts errors into `BindingResult` in the MVC pipeline; (7) no, fail-fast can stop after the first violation.

## 15. Official References

- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolationException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolationException.html
- Jakarta Bean Validation 3.0 specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8.0 Reference Guide, *Validating constraints*, *ConstraintViolation*, and *Group*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework Reference, *Java Bean Validation*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework Reference, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
