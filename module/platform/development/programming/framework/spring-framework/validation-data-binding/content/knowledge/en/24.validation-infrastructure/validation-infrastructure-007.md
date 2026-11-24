# Constraint Metadata API and ConstraintDescriptor in Jakarta Validation and Spring Framework

When running Bean Validation, we commonly see `@NotBlank`, `@Size`, or a custom constraint, and then call `Validator.validate(bean)` to obtain errors. However, libraries, frameworks, and tools also need to answer questions **before an object exists to validate**:

- Which properties of `OrderForm` have constraints attached?
- What constraints does the `code` property have, including `min`/`max`, raw message template, and validation groups?
- Is a property annotated only with `@Valid` considered a site requiring inspection?
- Is a constraint placed on a field, getter, method parameter, return value, or `List` element?
- What sub-constraints make up a composed constraint?

Jakarta Validation's **Constraint Metadata API** provides these answers through *descriptors* built by the validation provider from the active constraint configuration. `ConstraintDescriptor` describes **a specific constraint declaration**; it does not hold errors produced on a concrete input value.

This article uses the `jakarta.validation` API of Spring Framework 6 / Spring Boot 3 and Java 17+. Clearly distinguish **reading metadata** from **executing validation**:

~~~text
                        jakarta.validation.Validator
                                   |
                  +----------------+----------------+
                  |                                 |
        getConstraintsForClass(...)               validate(bean)
                  |                                 |
              BeanDescriptor               Set<ConstraintViolation<T>>
                  |                                 |
        PropertyDescriptor, ...            which data failed?
                  |
          ConstraintDescriptor
                  |
   annotation, attributes, groups,
   message template, composition...
                  |
      which constraints ARE DECLARED?
~~~

Metadata helps tools understand rules without running `isValid`. Conversely, calling `validate` checks an actual value and produces `ConstraintViolation`s.

## 1. Entry point: `Validator.getConstraintsForClass`

The standard API is in `jakarta.validation.Validator`:

~~~java
import jakarta.validation.Validator;
import jakarta.validation.metadata.BeanDescriptor;

BeanDescriptor beanDescriptor =
    validator.getConstraintsForClass(OrderForm.class);
~~~

This snippet illustrates code **inside a component that already holds a `validator` variable**. `getConstraintsForClass(Class<?>)` returns a `BeanDescriptor` describing the class's metadata; no `new OrderForm(...)` is needed. It does not validate data and does not return `Set<ConstraintViolation<?>>`.

`BeanDescriptor` exists even when the class has no constraints. Key points:

- `beanDescriptor.isBeanConstrained()` asks whether the class or its properties have any constraints/cascades; **does not count method/constructor constraints on its own**.
- `beanDescriptor.hasConstraints()`, inherited from `ElementDescriptor`, only reflects constraints placed on **the object itself at the class level**; it does not mean all properties have no constraints.
- `beanDescriptor.getConstraintDescriptors()` returns constraints placed directly at the **class level**, without automatically aggregating field constraints.
- `beanDescriptor.getConstrainedProperties()` returns properties that have constraints or are marked for cascading.
- `beanDescriptor.getConstraintsForProperty("code")` navigates to a specific property; it can return `null` if the property does not exist, or has no constraints/cascading.

For example, a class with only `@NotBlank private String code;` typically has `isBeanConstrained() == true`, yet `beanDescriptor.hasConstraints() == false` and `beanDescriptor.getConstraintDescriptors().isEmpty() == true`, because the constraint lives on the **property**, not as a class-level annotation.

## 2. The descriptor tree: each level has its own responsibility

The primary interfaces live in the `jakarta.validation.metadata` package.

| API | Described element | Notable APIs |
|---|---|---|
| `ElementDescriptor` | Common node: class, property, parameter, return value... | `hasConstraints()`, `getConstraintDescriptors()`, `getElementClass()`, `findConstraints()` |
| `BeanDescriptor` | A Java Bean | `getConstrainedProperties()`, `getConstraintsForProperty()`, `getConstraintsForMethod()`, `getConstrainedMethods()` |
| `PropertyDescriptor` | A constrained/cascaded property, including field/getter | `getPropertyName()`, `isCascaded()`, `getConstrainedContainerElementTypes()` |
| `MethodDescriptor` | A method with constraints on parameters/return value or cascading | `getParameterDescriptors()`, `getReturnValueDescriptor()`, `getCrossParameterDescriptor()` |
| `ConstructorDescriptor` | A constructor with corresponding validation sites | `getParameterDescriptors()`, `getReturnValueDescriptor()` |
| `ParameterDescriptor` | An executable parameter | `getIndex()`, `getName()`, `getConstraintDescriptors()` |
| `ReturnValueDescriptor` | Return value of a method/constructor | `getConstraintDescriptors()`, `isCascaded()` |
| `ContainerElementTypeDescriptor` | A validated type argument, like `String` in `List<@NotBlank String>` | `getContainerClass()`, `getTypeArgumentIndex()`, `getConstraintDescriptors()` |
| `ConstraintDescriptor<T>` | **A constraint declaration** | `getAnnotation()`, `getAttributes()`, `getGroups()`, `getComposingConstraints()` |

Descriptors involved in cascading and containers also implement `CascadableDescriptor` and `ContainerDescriptor`. Hence you must inspect the right level: `PropertyDescriptor.getConstraintDescriptors()` can be empty when a property only has `@Valid`, while `isCascaded()` is still `true`; constraints on **type arguments** are found on `ContainerElementTypeDescriptor`.

Navigation model:

~~~text
BeanDescriptor<OrderForm>
├─ PropertyDescriptor("code")
│  ├─ ConstraintDescriptor<NotBlank>
│  ├─ ConstraintDescriptor<Size>
│  └─ ConstraintDescriptor<Pattern>
├─ PropertyDescriptor("customer")
│  └─ isCascaded() = true  (@Valid)
├─ PropertyDescriptor("tags")
│  └─ ContainerElementTypeDescriptor(List argument #0: String)
│     └─ ConstraintDescriptor<NotBlank>
└─ MethodDescriptor("submit", String.class)
   └─ ParameterDescriptor(index=0)
      └─ ConstraintDescriptor<NotBlank>
~~~

This tree is **not** a source code AST. The provider accounts for valid declarations on supertypes, constraint composition, and Jakarta Validation's own mapping sources.

## 3. What does `ConstraintDescriptor` actually contain?

`ConstraintDescriptor<T extends Annotation>` describes **one application of an annotation** to an element, including the attributes of that application. For `@Size(min=4, max=12)`, the descriptor contains `min=4` and `max=12`; these are not necessarily the defaults in the annotation definition.

| Method | Value/meaning | Pitfalls to avoid |
|---|---|---|
| `getAnnotation()` | The annotation instance (or corresponding representation) | Do not equate with direct reflection on a field |
| `getAttributes()` | `Map<String,Object>` of annotation elements such as `min`, `max`, `regexp`, `message`, `groups` | Values keep their Java types; `min` is `Integer`, not a JSON string |
| `getMessageTemplate()` | **Uninterpolated** message, e.g. `{jakarta.validation.constraints.Size.message}` | Not the resolved/localized message of an actual violation |
| `getGroups()` | `Set<Class<?>>` of applicable groups | Constraints with no explicit groups belong to `Default` |
| `getPayload()` | Set of declared payload classes | Payload is not a validation group |
| `getConstraintValidatorClasses()` | Validator classes declared for the constraint | For some built-in constraints this list may be empty; **do not** infer the constraint cannot validate |
| `getComposingConstraints()` | Descriptors of sub-constraints in a composed constraint | This is a composition relationship, not a list of violations |
| `isReportAsSingleViolation()` | Whether `@ReportAsSingleViolation` is present on a composed constraint | Does not erase metadata of child constraints |
| `getValidationAppliesTo()` | `ConstraintTarget` if annotation has `validationAppliesTo`, or `null` | Do not use to guess Java `@Target` sites |
| `getValueUnwrapping()` | Unwrapping policy determined by relevant payloads | Different from `@Valid` cascading |
| `unwrap(Type.class)` | Accesses provider extensions if supported | Not portable; may throw `ValidationException` |

Example reading attributes of `@Size`:

~~~java
ConstraintDescriptor<?> sizeDescriptor =
    codeDescriptor.getConstraintDescriptors().stream()
        .filter(d -> d.getAnnotation()
            .annotationType() == Size.class)
        .findFirst()
        .orElseThrow();

int min = (Integer) sizeDescriptor.getAttributes().get("min");
int max = (Integer) sizeDescriptor.getAttributes().get("max");

System.out.println(min + ".." + max); // 4..12
~~~

This snippet is **placed in the context** where `PropertyDescriptor codeDescriptor` from the complete example in section 5 exists and `jakarta.validation.metadata.ConstraintDescriptor`, `jakarta.validation.constraints.Size` are imported. Using `getAttributes()` is especially useful for schema generators, form builders, and documentation tooling, because it reads the **effective** configuration, including attributes overridden in constraint composition.

`ConstraintDescriptor.getMessageTemplate()` is configuration metadata. `ConstraintViolation.getMessage()` is the interpolated message for a specific violation, which may depend on `MessageInterpolator` and locale. Distinguish the two APIs so you never show raw `{...}` keys to end users.

## 4. `ElementDescriptor.findConstraints()` and lookup scope

From a `PropertyDescriptor` (or another descriptor extending `ElementDescriptor`), you can create a `ConstraintFinder` to filter metadata:

~~~java
var defaults = codeDescriptor.findConstraints()
    .unorderedAndMatchingGroups(
        jakarta.validation.groups.Default.class)
    .getConstraintDescriptors();

var fieldConstraints = codeDescriptor.findConstraints()
    .declaredOn(java.lang.annotation.ElementType.FIELD)
    .getConstraintDescriptors();
~~~

Three key filters:

- `unorderedAndMatchingGroups(G1.class, G2.class, ...)`: selects only constraints applying to the requested groups, accounting for group inheritance and group sequences per metadata rules. **Does not** simulate group sequence execution order or short-circuiting when a group fails.
- `declaredOn(ElementType.FIELD, ElementType.METHOD, ...)`: selects the *declaration* site (for example, field vs getter), not the data type.
- `lookingAt(Scope.LOCAL_ELEMENT)` or `lookingAt(Scope.HIERARCHY)`: selects only locally declared constraints or includes the full hierarchy. The default scope is hierarchy.

Note: `ConstraintFinder` is **stateful as filters are applied** and is **not thread-safe**; create a fresh finder for each independent query. Do not call `findConstraints()` once and accumulate filters across different questions unintentionally. The returned set of `ConstraintDescriptor`s has no guaranteed order; sort by annotation name/attributes before printing or using in snapshot tests.

## 5. Complete Spring Boot example: printing the metadata tree

This example runs in a **Spring Boot 3.x + Java 17+ project** with the validation starter installed. All Java code below resides in a single file:

`src/main/java/com/example/metadata/MetadataDemoApplication.java`

The model classes are nested as `static` classes inside the application class so the demo project needs only **one Java file**, with no controller or database. The Spring component receives the `jakarta.validation.Validator` provided by auto-configuration.

In the Spring Boot project's `build.gradle` with appropriate dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

If creating a new project, you can use Spring Initializr with Java 17+, Gradle, and the **Validation** dependency. In a project with the Spring Boot plugin, run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Do not run plain `javac` with only the JDK classpath because the code imports Spring and Jakarta Validation.

### 5.1. Full source code

~~~java
package com.example.metadata;

import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import jakarta.validation.metadata.BeanDescriptor;
import jakarta.validation.metadata.ConstraintDescriptor;
import jakarta.validation.metadata.PropertyDescriptor;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataDemoApplication implements CommandLineRunner {

    private final Validator validator;

    public MetadataDemoApplication(Validator validator) {
        this.validator = validator;
    }

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    public interface Strict {}

    public static class Customer {
        @NotBlank
        private final String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static class OrderForm {
        @NotBlank
        @Size(min = 4, max = 12)
        @Pattern(
            regexp = "ORD-[A-Z0-9]+",
            groups = Strict.class
        )
        private final String code;

        @Valid
        private final Customer customer;

        private final List<@NotBlank String> tags;

        public OrderForm(
                String code,
                Customer customer,
                List<String> tags) {
            this.code = code;
            this.customer = customer;
            this.tags = tags;
        }

        public String getCode() {
            return code;
        }

        public Customer getCustomer() {
            return customer;
        }

        public List<String> getTags() {
            return tags;
        }

        public void submit(@NotBlank String requestId) {
            // Used only to illustrate method parameter metadata.
        }
    }

    @Override
    public void run(String... args) {
        BeanDescriptor bean =
            validator.getConstraintsForClass(OrderForm.class);

        PropertyDescriptor code =
            bean.getConstraintsForProperty("code");

        ConstraintDescriptor<?> size =
            code.getConstraintDescriptors().stream()
                .filter(d ->
                    d.getAnnotation().annotationType()
                        == Size.class)
                .findFirst()
                .orElseThrow();

        int defaultCount = code.findConstraints()
            .unorderedAndMatchingGroups(Default.class)
            .getConstraintDescriptors().size();

        int strictCount = code.findConstraints()
            .unorderedAndMatchingGroups(Strict.class)
            .getConstraintDescriptors().size();

        PropertyDescriptor customer =
            bean.getConstraintsForProperty("customer");

        PropertyDescriptor tags =
            bean.getConstraintsForProperty("tags");

        int tagConstraintCount = tags
            .getConstrainedContainerElementTypes().stream()
            .mapToInt(d -> d.getConstraintDescriptors().size())
            .sum();

        var submit = bean.getConstraintsForMethod(
            "submit", String.class);

        var invalid = new OrderForm(
            "",
            new Customer(""),
            List.of("")
        );

        System.out.println(
            "Bean constrained: " + bean.isBeanConstrained());
        System.out.println(
            "Class-level constraints: "
                + bean.getConstraintDescriptors().size());
        System.out.println(
            "Code constraints: "
                + code.getConstraintDescriptors().size());
        System.out.println(
            "Size min/max: "
                + size.getAttributes().get("min") + "/"
                + size.getAttributes().get("max"));
        System.out.println(
            "Size template: " + size.getMessageTemplate());
        System.out.println(
            "Code Default group: " + defaultCount);
        System.out.println(
            "Code Strict group: " + strictCount);
        System.out.println(
            "Customer cascaded: " + customer.isCascaded());
        System.out.println(
            "Tag element constraints: " + tagConstraintCount);
        System.out.println(
            "Submit parameter constraints: "
                + submit.getParameterDescriptors().get(0)
                    .getConstraintDescriptors().size());
        System.out.println(
            "Default violations: "
                + validator.validate(invalid).size());
        System.out.println(
            "Strict violations: "
                + validator.validate(invalid, Strict.class).size());
    }
}
~~~

### 5.2. Observed output

Run with the wrapper:

~~~bash
./gradlew bootRun
~~~

Aside from Spring Boot startup logs, the lines printed by `CommandLineRunner` are:

~~~text
Bean constrained: true
Class-level constraints: 0
Code constraints: 3
Size min/max: 4/12
Size template: {jakarta.validation.constraints.Size.message}
Code Default group: 2
Code Strict group: 1
Customer cascaded: true
Tag element constraints: 1
Submit parameter constraints: 1
Default violations: 4
Strict violations: 1
~~~

Explanation:

1. `OrderForm` has property-level validation so `isBeanConstrained()` is `true`. There are no **class-level** constraints, hence `Class-level constraints: 0`.
2. `code` has three declarations: `@NotBlank`, `@Size`, and `@Pattern`. The `min`/`max` attributes of `@Size` are retrieved directly without needing a form instance.
3. `Default` selects `@NotBlank` and `@Size`; `Strict` selects only `@Pattern`. The `Strict` interface in the example does not extend any other group.
4. `customer` uses `@Valid` for cascading, so `isCascaded()` returns `true` even though that property has no direct constraints.
5. `tags` has a constraint on the `String` **type argument** of `List`, not on the `List` itself.
6. `submit` has one `@NotBlank` on its first parameter. Finding method metadata **does not** mean an ordinary Java call automatically gets method validation.
7. The empty sample data violates `code`'s `@NotBlank` and `@Size`, `customer.name`'s `@NotBlank` via cascading, and `tags[0]`'s `@NotBlank`: a total of **4 violations in Default**.
8. When invoking only the `Strict` group, `code` violates `@Pattern`: **1 violation**. `Default` constraints are not automatically applied alongside `Strict`.

On Windows, you can use `gradlew.bat bootRun`. The program is a Spring Boot application; the metric lines above are only the demo output, not the full Spring Boot stdout.

**Note on example scope:** the code places constraints on fields, reads metadata via Spring's provider, and calls `jakarta.validation.Validator` directly. It does not require HTTP endpoints, does not use `@Validated` for methods, and does not write a custom `ConstraintValidator` to explain `ConstraintDescriptor`.

## 6. Reading property metadata correctly

### 6.1. Listing every constrained property

~~~java
var propertyNames = bean.getConstrainedProperties().stream()
    .map(PropertyDescriptor::getPropertyName)
    .sorted()
    .toList();

System.out.println(propertyNames);
~~~

For `OrderForm` in the example, the lexicographically sorted list contains `code`, `customer`, and `tags`. Note that a property is listed if it has a **constraint**, **cascade**, or **container element constraint**; `property.getConstraintDescriptors()` does not have to be non-empty.

For a property with no constraints/cascades, `bean.getConstraintsForProperty("missing")` returns `null`. Do not chain `getConstraintsForProperty(...).getConstraintDescriptors()` without a null check when property names come from untrusted input.

### 6.2. Field and getter contributing to one property

If `@NotBlank` is placed on field `name` and `@Size` is placed on getter `getName()`, the metadata of logical property `name` can contain both constraints. Use:

~~~java
var fieldRules = code.findConstraints()
    .declaredOn(java.lang.annotation.ElementType.FIELD)
    .getConstraintDescriptors();
~~~

`declaredOn(FIELD)` filters by **declaration site**, without turning `code` into a separate field descriptor. This is why the metadata API is more suitable than simply calling `OrderForm.class.getDeclaredField("code").getAnnotations()`. Plain reflection does not aggregate fields, getters, inheritance, and XML constraint mappings the way the provider does.

Avoid declaring the exact same rule on both the field and the getter just to “be sure” — the Bean Validation provider may treat them as two separate constraint declarations and report duplicate errors.

### 6.3. Cascading is not a direct constraint

~~~java
PropertyDescriptor customer =
    bean.getConstraintsForProperty("customer");

System.out.println(customer.isCascaded()); // true
System.out.println(customer.hasConstraints()); // false
~~~

Explanation: `@Valid` tells the provider to enter the `Customer` bean during validation, but `@Valid` itself is not a `ConstraintDescriptor` on the property. To inspect constraints on `Customer.name`, query the metadata of `Customer`:

~~~java
BeanDescriptor customerBean =
    validator.getConstraintsForClass(Customer.class);

var nameRules = customerBean
    .getConstraintsForProperty("name")
    .getConstraintDescriptors();
~~~

The metadata API also exposes `getGroupConversions()` on descriptors supporting cascading to inspect group conversions declared via `@ConvertGroup`. When exporting documentation, remember to separate “cascade/group conversion” from “direct constraint” so you neither miss nor duplicate logic.

### 6.4. Container element constraints

Given the property:

~~~java
private List<@NotBlank String> tags;
~~~

`@NotBlank` attaches to the **string element** because the annotation supports `TYPE_USE`. Read it with:

~~~java
PropertyDescriptor tags =
    bean.getConstraintsForProperty("tags");

for (var element :
        tags.getConstrainedContainerElementTypes()) {
    System.out.println(
        element.getContainerClass().getSimpleName());
    System.out.println(element.getTypeArgumentIndex());
    System.out.println(element.getConstraintDescriptors().size());
}
~~~

The output for the type argument above is:

~~~text
List
0
1
~~~

Index `0` is the first type argument position of `List<E>`, not the runtime element index. With nested containers, such as `List<Map<String, @NotBlank String>>`, container element descriptors can be **nested**: call `getConstrainedContainerElementTypes()` recursively when building a metadata tree.

`ContainerElementTypeDescriptor` also has `isCascaded()` if the corresponding element carries `@Valid`; do not confuse it with a constraint like `@NotNull` or `@NotBlank`.

## 7. Metadata for methods and constructors

`BeanDescriptor` lets you inspect **executable** constraints without invoking the method or constructor:

~~~java
var method = bean.getConstraintsForMethod(
    "submit", String.class);

var parameter = method.getParameterDescriptors().get(0);

System.out.println(parameter.getIndex()); // 0
System.out.println(
    parameter.getConstraintDescriptors().size()); // 1
~~~

For methods, parameters, and return values:

- `getConstraintsForMethod("name", ParamType.class, ...)` requires the **exact method name and parameter signature**; a method without matching constraints/cascades may return `null`.
- `MethodDescriptor.getParameterDescriptors()` returns descriptors for each parameter; `getIndex()` is the parameter index, not a validation group order.
- `MethodDescriptor.getReturnValueDescriptor()` describes constraints/cascades applied to the return value.
- `getCrossParameterDescriptor()` describes constraints checking **relationships across multiple parameters** of the same executable, distinct from per-parameter constraints.
- `getConstrainedMethods(MethodType.GETTER, MethodType.NON_GETTER)` helps list methods by category.
- `getConstraintsForConstructor(ParamType.class, ...)` and `getConstrainedConstructors()` work similarly for constructors.

`BeanDescriptor.isBeanConstrained()` does not count method/constructor constraints on their own. A class having only `void submit(@NotNull String code)` can return `false` for `isBeanConstrained()` while still having a constrained `MethodDescriptor`. If building a dashboard checking “does this class have validation?”, inspect executables as well.

**Metadata != method call interception:** finding `@NotBlank` on a parameter only proves the declaration exists. For Spring to automatically validate a method call, an appropriate method validation mechanism must be active (for example, Spring `@Validated` and AOP configuration where applicable). Self-invocations within the same bean can bypass proxies. Calling `ExecutableValidator` directly is a separate path from interception.

## 8. Groups, hierarchy, and filter semantics

Constraints declared without explicit `groups` apply to `Default`. With:

~~~java
@NotBlank
@Size(min = 4, max = 12)
@Pattern(
    regexp = "ORD-[A-Z0-9]+",
    groups = Strict.class)
private String code;
~~~

the metadata query:

~~~java
int strictCount = code.findConstraints()
    .unorderedAndMatchingGroups(Strict.class)
    .getConstraintDescriptors()
    .size(); // 1
~~~

is not equivalent to `validator.validate(bean, Strict.class)` because:

1. A metadata query only selects *declarations* matching the filter; it **does not evaluate the bean**.
2. Validation execution also depends on values, cascading, group conversions, group sequences, and validator resolution rules.
3. By API contract, `unorderedAndMatchingGroups(...)` does not guarantee group sequence order; do not use descriptor order to infer “which rule runs first”.

`Scope.LOCAL_ELEMENT` and `Scope.HIERARCHY` differ when a subclass inherits declarations from a superclass. By default the finder examines the hierarchy; if you need to describe “constraints declared solely by the current class”, apply local scope. Do not use `getDeclaredAnnotations()` as a full replacement because constraint sources can come from mappings beyond plain reflection.

## 9. Constraint composition and `getComposingConstraints()`

A custom constraint can **compose** existing constraints. Illustrative definition:

~~~java
@jakarta.validation.constraints.NotBlank
@jakarta.validation.constraints.Size(min = 4, max = 12)
@jakarta.validation.Constraint(validatedBy = {})
@jakarta.validation.ReportAsSingleViolation
@java.lang.annotation.Target({
    java.lang.annotation.ElementType.FIELD,
    java.lang.annotation.ElementType.METHOD,
    java.lang.annotation.ElementType.PARAMETER,
    java.lang.annotation.ElementType.ANNOTATION_TYPE
})
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.RUNTIME)
public @interface StrongCode {
    String message() default "Invalid code";
    Class<?>[] groups() default {};
    Class<? extends jakarta.validation.Payload>[] payload()
        default {};
}
~~~

This is a **condensed illustrative annotation definition** to place in `StrongCode.java` in an appropriate package. The `@NotBlank` and `@Size` annotations placed **on the annotation definition** are composing constraints; `@Constraint(validatedBy = {})` declares no dedicated validator because composition performs the checks.

If `@StrongCode` is placed on a field and has a corresponding `ConstraintDescriptor`:

~~~java
ConstraintDescriptor<?> strong = /* descriptor of @StrongCode */;

System.out.println(
    strong.getComposingConstraints().size()); // 2
System.out.println(
    strong.isReportAsSingleViolation()); // true
~~~

The two child descriptors indicate that `@NotBlank` and `@Size` both participate. `@ReportAsSingleViolation` allows error reporting to be collapsed into **a single violation for the composite constraint** per Jakarta Validation rules; composing metadata remains intact for tooling analysis. Inside composing constraint metadata, attributes overridden via `@OverridesAttribute` must also be reflected accurately by `getAttributes()` and `getAnnotation()`.

For a custom constraint that implements `ConstraintValidator<StrongCode, String>` rather than pure composition, `getConstraintValidatorClasses()` lists the validators specified by the annotation. However, do not infer the number of `isValid` executions from the number of classes in metadata: the provider selects the validator by data type/target and may cache instances.

### Repeatable constraints

If the same constraint type is applied multiple times (for example, two `@Pattern` rules via the `@Pattern.List` container), each declaration represents a separate constraint. The metadata provider is expected to expose the contained constraints via the multi-valued constraint annotation mechanism, rather than requiring tools to unwrap every `List` container manually via reflection. Whether direct repeatable syntax can be written also depends on whether the annotation has a valid `@Repeatable`.

Easily confused distinctions:

- **Composition:** one constraint **includes** sub-constraints; read `getComposingConstraints()`.
- **Repeatable:** multiple **declarations of the same type** on one site; read the set of `ConstraintDescriptor`s applying at that site.
- **Cascade:** `@Valid` enters another object/element; read `isCascaded()`.
- **Groups:** selects constraint subsets by validation purpose; read `getGroups()` or use `ConstraintFinder`.

## 10. Connecting with Spring Framework and real applications

In Spring Boot with `spring-boot-starter-validation`, there is usually a `LocalValidatorFactoryBean` integrating the Jakarta Validation provider. When injecting `jakarta.validation.Validator`, that object provides `getConstraintsForClass`, while Spring provides the bean/configuration system and validation trigger points. The standard metadata API is **not** part of `org.springframework.validation.Errors` or `BindingResult`.

| Task | Appropriate API |
|---|---|
| Discover constraints without data | `Validator.getConstraintsForClass(...)` + descriptors |
| Validate a populated bean | `Validator.validate(bean)` |
| Validate a single property on an existing bean | `Validator.validateProperty(bean, "field")` |
| Validate a hypothetical value before creating a bean | `Validator.validateValue(MyType.class, "field", value)` |
| Validate executable parameters/return values via API | `Validator.forExecutables()` |
| Present errors after Spring MVC binding | `BindingResult` / appropriate exception handling |
| Inspect the constraint that caused a specific violation | `ConstraintViolation.getConstraintDescriptor()` |

### From `ConstraintViolation` back to metadata

A violation can provide the descriptor of the constraint that failed:

~~~java
var violations = validator.validate(invalid);

var sizeViolation = violations.stream()
    .filter(v -> v.getConstraintDescriptor()
        .getAnnotation().annotationType() == Size.class)
    .findFirst()
    .orElseThrow();

System.out.println(
    sizeViolation.getConstraintDescriptor()
        .getAttributes().get("min")); // 4

System.out.println(
    sizeViolation.getPropertyPath()); // code
~~~

This snippet sits inside `run(...)` of the complete example after `invalid` is declared, and requires `import jakarta.validation.constraints.Size;` already present in the file. It illustrates the bridge between **static metadata** and **violations on actual values**: the descriptor carries the `@Size` attributes, while `ConstraintViolation` adds the error path, invalid value, interpolated message, root bean, and so on.

A form/schema generator should use the metadata API to recognize standard constraints, but **cannot automatically infer every business rule of a custom `ConstraintValidator`** from the annotation name alone. For instance, `@RegisteredInDatabase` may need a DB query and current context; metadata only reveals the declaration/attributes, without turning it into a complete static schema.

### Serializing metadata for UI or API docs

An application can build documentation JSON from `ConstraintDescriptor`, for instance for `@Size(min=4,max=12)`:

~~~json
{
  "property": "code",
  "constraint": "Size",
  "attributes": { "min": 4, "max": 12 },
  "groups": ["Default"]
}
~~~

This is an **illustrative export model**, not direct output of the Jakarta Validation API. When serializing descriptors yourself, handle special types (`Class`, `Class[]`, enums, annotations, nested descriptors), filter out metadata unsuitable for public exposure, and guard against cycles/recursion in composition if your tool walks the tree.

Never treat static metadata output as proof that a request will be valid. `validate` still depends on runtime data, provider, groups/cascades, and validator logic.

## 11. Immutability, caching, and key limitations

- **Descriptors are read-only metadata.** Jakarta Validation specifies descriptor objects as immutable; do not call `getAttributes().put(...)` to “edit” constraints. To change rules, update the declaration/mapping or provider configuration and rebuild the corresponding metadata.
- **Metadata is not the result of running `isValid`.** Descriptors exist even without a bean instance; errors only arise when invalid values exist and validation runs.
- **Providers may cache metadata.** Best practice is to use the Spring-managed `Validator`/`ValidatorFactory` instead of manually bootstrapping and closing a factory per request.
- **Metadata sources go beyond direct reflection.** They include field/getter declarations, inheritance, container elements, groups/cascades, and external mappings when supported by the provider. Do not assume `getDeclaredAnnotations` reflects everything.
- **Sets have no stable order.** `getConstraintDescriptors()`, `getConstrainedProperties()`, and other descriptor sets may iterate in varying orders. When exporting reports or writing snapshot tests, sort explicitly by deterministic criteria.
- **Provider-specific extensions are not portable.** `unwrap(...)` is for provider-specific capabilities; tools targeting multiple providers should prefer standard `jakarta.validation.metadata` APIs.
- **Do not mechanically derive SQL, regex, or HTML attributes.** A custom annotation can express complex checks; metadata only exposes declared parameters, not the algorithm inside `isValid`.
- **Do not build security logic from metadata alone.** Server-side validation must still execute; constraint metadata exposed to clients is a UX hint, not a security boundary.

## 12. Common errors and diagnostics

| Symptom | Common cause | Resolution |
|---|---|---|
| `bean.hasConstraints()` returns `false` despite `@NotBlank` field | Asking for **class-level** constraints, not property constraints | Check `isBeanConstrained()`, `getConstrainedProperties()`, and property descriptors |
| `getConstraintsForProperty("code")` returns `null` | Wrong property name, property has no constraint/cascade, or mapping not loaded by provider | Check JavaBean/property name and the active validator |
| `getConstraintDescriptors()` is empty on `@Valid` property | Cascade is not a direct constraint | Check `isCascaded()` and metadata of the referenced bean type |
| `@NotBlank` not visible on `List<@NotBlank String>` | Constraint is on the **type argument**, not directly on the property | Inspect `getConstrainedContainerElementTypes()` |
| Metadata differs from Java reflection annotations | Constraints come from getter, inheritance, composition, or external mapping | Read through the active Jakarta provider instead of reflection alone |
| `@Pattern` missing when filtering `Default` | Constraint declares `groups = Strict.class` | Check `getGroups()` and query the right group |
| Result order changes | Descriptor `Set` guarantees no iteration order | Sort by annotation type/attributes when displaying |
| `getMessageTemplate()` shows `{...}` | It is the uninterpolated template | Use `ConstraintViolation.getMessage()` for actual violation messages |
| `getConstraintValidatorClasses()` is empty for built-in constraint | Built-in provider may supply validators via internal mechanisms | Do not treat an empty list as missing validation |
| `getConstraintsForMethod(...)` returns `null` | Wrong overload signature or method has no executable constraints/cascades | Supply exact name and parameter types, verify annotations |
| Method descriptor has constraints but calling method reports no errors | Metadata does not configure interception by itself | Configure method validation or call `ExecutableValidator` |
| Switched annotations to `javax.validation.*` but Boot 3 ignores them | Namespace mismatch between `javax` and `jakarta` | Align namespaces with Spring 6/Boot 3 and the provider |
| Violation count differs from descriptor count | Some constraints pass; cascade/group/sequence and composition affect results | Separate declarations from runtime evaluation, inspect actual `ConstraintViolation`s |
| Calling `findConstraints()` and reusing finder across threads | `ConstraintFinder` is not thread-safe and filters accumulate | Create a new finder per query, store immutable results if needed |
| Reading metadata throws configuration error | Provider detects invalid constraint/mapping when building metadata | Inspect the exception and fix the source constraint configuration |

## 13. Checklist and self-check exercises

**Checklist when building a constraint-reading tool:**

1. Obtain the actual `jakarta.validation.Validator` used in the Spring context.
2. Enter `BeanDescriptor` via `getConstraintsForClass`; inspect class constraints, properties, and executable constraints if your tool's scope requires them.
3. For each property, read `getConstraintDescriptors()`, `isCascaded()`, and `getConstrainedContainerElementTypes()` together; do not skip nested type arguments.
4. For each `ConstraintDescriptor`, inspect annotation type, attributes, message template, groups, payload, composition, and reporting policy when relevant.
5. Only use `ConstraintFinder` when filtering by group, source element, or hierarchy; create a fresh finder per query.
6. Sort results before exporting/testing and distinguish constraint declarations from runtime violations.
7. Use `ConstraintViolation.getConstraintDescriptor()` when linking a declared rule to a runtime error.
8. Test metadata under the actual Spring/Jakarta provider and real application configuration.

**Exercise 1 — Add a group:** Attach `groups = Strict.class` to `@Size` on `code`, then re-run the metadata demo. Predict that `Default` keeps one descriptor (`@NotBlank`), `Strict` has two (`@Pattern`, `@Size`); run validation on the empty sample and compare the corresponding violation counts.

**Exercise 2 — Remove cascade:** Remove `@Valid` from `customer`. Predict `isCascaded()` changes and the `Default` violation count no longer includes `Customer.name`. If the `customer` property has no other constraints, `getConstraintsForProperty("customer")` may return `null`: handle this safely.

**Exercise 3 — Move declaration site:** Move `@Size` from the `code` field to the `getCode()` getter. Query `getConstraintDescriptors()` on property `code` and `findConstraints().declaredOn(ElementType.FIELD)`; explain why the two sets differ while the constraint on the logical property remains active.

**Exercise 4 — Nested elements:** Change `List<@NotBlank String> tags` to `List<List<@NotBlank String>> tags`. Write a recursive traversal of `ContainerElementTypeDescriptor.getConstrainedContainerElementTypes()` to locate the constraint at the deeper container layer.

**Exercise 5 — Composition:** Add `@StrongCode` to a new property. Use `getComposingConstraints()` and `isReportAsSingleViolation()` to explain the difference between metadata structure and runtime violation count.

**Key takeaway:** `Validator.getConstraintsForClass` opens the metadata repository, `BeanDescriptor` navigates to declaration sites, `ConstraintDescriptor` describes **one rule with its effective parameters**, and `ConstraintViolation` describes **one failed rule application on concrete data**. Reading the right descriptor level is the foundation for building documentation, testing, and validation-integration tools in Spring.

## Official references

- [Jakarta Validation 3.1 — Specification, Constraint metadata request APIs section](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintmetadata)
- [Jakarta Validation API — package jakarta.validation.metadata](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/package-summary.html)
- [Jakarta Validation API — BeanDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/BeanDescriptor.html)
- [Jakarta Validation API — ConstraintDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html)
- [Jakarta Validation API — ElementDescriptor.ConstraintFinder](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ElementDescriptor.ConstraintFinder.html)
- [Jakarta Validation API — ContainerElementTypeDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ContainerElementTypeDescriptor.html)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
