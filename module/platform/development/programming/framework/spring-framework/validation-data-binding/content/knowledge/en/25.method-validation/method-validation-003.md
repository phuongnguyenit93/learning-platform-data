# ExecutableValidator and Direct Validation Calls

## 1. Why Is Direct Method Validation Needed?

Jakarta Validation (Bean Validation) supports constraints not only on fields and DTOs, but also on **method parameters**, **return values**, **constructor parameters**, and **objects created by constructors**. Consider an example in a service:

```java
public class InventoryService {

    @NotBlank(message = "Result must have an id")
    public String reserve(
            @NotBlank(message = "Code is required") String productCode,
            @Min(value = 1, message = "Quantity must be positive") int quantity) {
        return "RES-1";
    }
}
```

Annotations such as `@NotBlank` and `@Min` only declare constraint metadata. Calling `new InventoryService().reserve("", 0)` in plain Java **does not automatically validate** those annotations. You need an integration layer (interceptor, proxy, framework) or an explicit validation call before/after invocation.

`jakarta.validation.executable.ExecutableValidator` is the standard API for explicitly validating **the contract of an invocation** without needing Spring AOP or HTTP requests. It is useful when:

- Writing unit tests for input and output conditions of a public API.
- Building your own job scheduler, command handler, RPC dispatcher, or reflection-based method invocation mechanism.
- Validating constructor arguments before creating an instance, or the instance's state right after creation.
- Pinpointing whether a violation belongs to a parameter, return value, cross-parameter rule, or cascade of an executable.

After this lesson, you will know how to obtain `ExecutableValidator`, call all four methods, prepare `Method`/`Constructor`/`Object[]` accurately, inspect `ConstraintViolation`, use groups and `@Valid`, and understand how this mechanism relates to Spring MVC and proxy-based method validation.

## 2. Two Different APIs: `Validator` and `ExecutableValidator`

Initialize a Jakarta Validation provider (such as Hibernate Validator) and obtain both APIs:

```java
try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();

    // Bean/property-level validation:
    Set<ConstraintViolation<Customer>> beanErrors =
            validator.validate(customer);

    // Method/constructor-level validation:
    ExecutableValidator executable = validator.forExecutables();
}
```

This is an illustrative snippet, assuming class `Customer` and variable `customer` exist. Meaning:

- `validator.validate(bean)` checks constraints on an object: fields, JavaBeans getters, class-level constraints, and cascades from those locations.
- `validator.validateProperty(bean, "name")` checks constraints on property `name`; it **does not** validate a method parameter named `name`.
- `validator.forExecutables()` provides the entry point for validating constraints on executables (methods and constructors).

Passing `service` alone to `validator.validate(service)` **does not** cause the provider to pick a method and validate its arguments. `ExecutableValidator` needs the invocation context: the reflection object and the values passed in or returned.

## 3. Four Core Methods

| API | Validates | Inputs |
| --- | --- | --- |
| `validateParameters(object, method, parameterValues, groups...)` | Individual parameter constraints and **cross-parameter** constraints on an instance method | Target object, `Method`, arguments array |
| `validateReturnValue(object, method, returnValue, groups...)` | Constraints and cascades applied to the **method return value** | Object, `Method`, return value |
| `validateConstructorParameters(constructor, parameterValues, groups...)` | Parameter and cross-parameter constraints of a constructor | `Constructor`, arguments array |
| `validateConstructorReturnValue(constructor, createdObject, groups...)` | Constraints/cascades on the **object created by the constructor** | `Constructor` and new instance |

All methods return `Set<ConstraintViolation<T>>`; when there are no errors, the set is empty, **not `null`**. The `Class<?>... groups` parameter is optional; when omitted, the `jakarta.validation.groups.Default` group runs. The direct API itself does not throw `ConstraintViolationException` to report ordinary validation errors, leaving it up to calling code to decide how to handle the violation set.

**Key characteristic:** `validateParameters` does not execute the method; `validateReturnValue` does not invoke the method to fetch a result itself. Neither constructor method instantiates the object automatically. The caller controls the order and decides when to abort if conditions are not met.

## 4. Standard Sequence for Manual Validation

### 4.1. For Instance Methods

```text
Method + object + Object[] arguments
               |
               v
      validateParameters(...)
               |
          violations?
           /       \
         yes        no
         |           |
       reject    invoke method
                     |
                  returnValue
                     |
                     v
       validateReturnValue(...)
                     |
               violations?
                 /       \
               yes        no
               |           |
           report error  accept
```

Skeleton code example (requires `service`, provider, and corresponding service method):

```java
Method method = InventoryService.class.getMethod(
        "reserve", String.class, int.class);

Object[] inputs = {"P100", 2};
var before = executable.validateParameters(
        service, method, inputs);

if (!before.isEmpty()) {
    throw new ConstraintViolationException(before);
}

String actualResult =
        service.reserve((String) inputs[0], (Integer) inputs[1]);

var after = executable.validateReturnValue(
        service, method, actualResult);

if (!after.isEmpty()) {
    throw new ConstraintViolationException(after);
}
```

`ConstraintViolationException` belongs to `jakarta.validation.ConstraintViolationException`, and is **explicitly thrown by the caller** here. Because `validateReturnValue` receives the actual result, it can verify the postcondition the method promised.

If the goal is to reject an invalid call before causing side effects, you **must** intercept before invoking the method. Validating afterward after writing data or calling external systems cannot undo side effects that already occurred.

### 4.2. For Constructors

```java
Constructor<Order> constructor =
        Order.class.getConstructor(String.class);

Object[] inputs = {"ORD-1"};
var before = executable.validateConstructorParameters(
        constructor, inputs);

// Instantiate only when before.isEmpty().
Order created = constructor.newInstance(inputs);

var after = executable.validateConstructorReturnValue(
        constructor, created);
```

This is an illustrative snippet, assuming `Order` has a public constructor accepting `String`. `validateConstructorParameters` does not run the constructor; `validateConstructorReturnValue` receives the already-created object. For a constructor, the "return value" in Jakarta Validation terms is the **newly created object**, not a return type declared in Java source code.

## 5. Complete Runnable Example: All Four Core Checks

The example uses **Java 17+**, **Jakarta Validation 3.0** via **Hibernate Validator 8.0.6.Final**. Spring is not required to run it. We design two classes:
- `ReceiptService.issue` has constraints on two parameters and one return value.
- `Invoice` has a constraint on a constructor parameter and a constraint on a field; `@Valid` on the constructor triggers cascading on the created instance.

For deterministic stdout, messages use fixed codes and are sorted with `TreeSet`. Do not rely on the iteration order of `Set<ConstraintViolation<?>>`.

Structure:

```text
executable-demo/
├── pom.xml
└── src/main/java/demo/
    └── ExecutableDemo.java
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executable-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` provides the provider and Jakarta Validation API dependency. `expressly` provides Jakarta Expression Language for message interpolation. When using Spring Boot, you typically declare `spring-boot-starter-validation` so Boot manages compatible versions.

### 5.2. `src/main/java/demo/ExecutableDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.executable.ExecutableValidator;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Set;
import java.util.TreeSet;

public class ExecutableDemo {

    public static final class ReceiptService {

        // Constraint on METHOD: applies to the return value.
        @NotBlank(message = "receipt.blank")
        public String issue(
                @NotBlank(message = "code.blank") String code,
                @Min(value = 1, message = "quantity.too.small")
                int quantity) {
            return "REC-" + code + "-" + quantity;
        }
    }

    public static final class Invoice {

        // Constraint on FIELD: evaluated when cascading to the object.
        @NotBlank(message = "invoice.number.blank")
        private final String number;

        // @Valid on CONSTRUCTOR: cascades to the created instance.
        @Valid
        public Invoice(
                @NotBlank(message = "invoice.argument.blank")
                String number) {
            this.number = number;
        }

        public String getNumber() {
            return number;
        }
    }

    private static <T> void print(
            String label, Set<ConstraintViolation<T>> violations) {
        TreeSet<String> messages = new TreeSet<>();

        for (ConstraintViolation<T> violation : violations) {
            messages.add(violation.getMessage());
        }

        System.out.println(label + " -> " + messages);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            ExecutableValidator executable = validator.forExecutables();

            ReceiptService service = new ReceiptService();
            Method method = ReceiptService.class.getMethod(
                    "issue", String.class, int.class);

            // 1. Two invalid method arguments.
            print("method-params-invalid",
                    executable.validateParameters(
                            service, method, new Object[] {"", 0}));

            // 2. One invalid method return value.
            print("method-return-invalid",
                    executable.validateReturnValue(
                            service, method, ""));

            Constructor<Invoice> constructor =
                    Invoice.class.getConstructor(String.class);

            // 3. One invalid constructor argument.
            print("constructor-params-invalid",
                    executable.validateConstructorParameters(
                            constructor, new Object[] {""}));

            // 4. Invalid state of the new instance; @Valid enables cascading.
            Invoice invalidInvoice = new Invoice("");
            print("constructor-return-invalid",
                    executable.validateConstructorReturnValue(
                            constructor, invalidInvoice));

            // 5. Four corresponding valid branches.
            print("method-params-valid",
                    executable.validateParameters(
                            service, method, new Object[] {"P1", 2}));

            print("method-return-valid",
                    executable.validateReturnValue(
                            service, method, "REC-P1-2"));

            print("constructor-params-valid",
                    executable.validateConstructorParameters(
                            constructor, new Object[] {"INV-7"}));

            print("constructor-return-valid",
                    executable.validateConstructorReturnValue(
                            constructor, new Invoice("INV-7")));
        }
    }
}
```

Run in the `executable-demo` directory (JDK 17+, Maven, and access to Maven Central dependencies):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExecutableDemo
```

Lines printed by `ExecutableDemo`'s `System.out` (excluding Maven/provider logs if any):

```text
method-params-invalid -> [code.blank, quantity.too.small]
method-return-invalid -> [receipt.blank]
constructor-params-invalid -> [invoice.argument.blank]
constructor-return-invalid -> [invoice.number.blank]
method-params-valid -> []
method-return-valid -> []
constructor-params-valid -> []
constructor-return-valid -> []
```

### 5.3. Why Are These Results Expected?

- `validateParameters(service, method, {"", 0})` checks both `@NotBlank` on `code` and `@Min(1)` on `quantity`. Two errors are reported without executing `issue`.
- `validateReturnValue(service, method, "")` takes the empty string supplied by the test, applies `@NotBlank` from the method declaration, and gets `receipt.blank`. It **does not call `issue` itself**.
- `validateConstructorParameters(constructor, {""})` validates `@NotBlank` on the constructor parameter: `invoice.argument.blank`.
- `validateConstructorReturnValue(constructor, new Invoice(""))` sees `@Valid` on the constructor, cascades to field `number`, and finds `invoice.number.blank`. If you remove `@Valid` from the constructor, constructor return validation **does not automatically scan fields** merely because the field has a constraint.
- The remaining four calls are all valid, returning empty sets `[]`.

In production, pass the **actual return value** to `validateReturnValue`; the example intentionally uses `""` to test the API independently. Notably, if you call `new Invoice("")` directly in plain Java, the constructor still executes; Jakarta Validation only reports an error when code calls `validateConstructorReturnValue` or an integration layer enforces the rule.

## 6. Reading and Handling `ConstraintViolation`

`ConstraintViolation` exposes more information than just a message. Inside `main` of section 5:

```java
Set<ConstraintViolation<ReceiptService>> errors =
        executable.validateParameters(
                service, method, new Object[] {"", 0});

for (ConstraintViolation<ReceiptService> v : errors) {
    System.out.println("path=" + v.getPropertyPath());
    System.out.println("message=" + v.getMessage());
    System.out.println("invalid=" + v.getInvalidValue());
    System.out.println("rootClass=" + v.getRootBeanClass().getName());
    System.out.println("arguments=" +
            java.util.Arrays.toString(v.getExecutableParameters()));
}
```

This is an **additional code snippet**, not a standalone Java file. A `ConstraintViolation` offers these APIs:

| API | Meaning |
| --- | --- |
| `getPropertyPath()` | Path from method/constructor to the offending parameter, return value, cascaded property, or container element |
| `getMessage()`, `getMessageTemplate()` | Interpolated message and raw message template |
| `getInvalidValue()` | The value received by the validator for checking; for cross-parameter this may be `Object[]` |
| `getRootBean()`, `getRootBeanClass()` | Root instance and class; for constructor parameter validation, root bean may be `null` |
| `getExecutableParameters()` | Arguments array for errors from **parameter** validation; `null` outside that branch |
| `getExecutableReturnValue()` | Return object/value for errors from **return value** validation; `null` outside that branch |
| `getConstraintDescriptor()` | Annotation metadata and attributes such as `min`, `max`, `groups`, and `message` |

A parameter path may look like `issue.arg0` if parameter names are unavailable, or `issue.code` when the provider knows the name. Return paths have a `<return value>` node; constructor cascades can end at `Invoice.<return value>.number`. **Do not hardcode `arg0`** as a business key: names depend on `ParameterNameProvider` and the `-parameters` compiler flag. If you need to classify errors, traverse `Path.Node` and inspect `getKind()` (for example `METHOD`, `CONSTRUCTOR`, `PARAMETER`, `RETURN_VALUE`, `PROPERTY`, `CROSS_PARAMETER`).

`Set<ConstraintViolation>` has no fixed iteration order. When returning JSON errors or logging, sort by property path and code if deterministic output is required. Also never blindly expose `getInvalidValue()` in responses: it may contain sensitive data.

## 7. Cascading on Parameters and Return Values

### 7.1. Parameter Is a DTO

```java
public record Customer(
        @NotBlank String name,
        @NotBlank String email) {}

public void register(@NotNull @Valid Customer customer) {
    // ...
}
```

These are two **illustrative** declarations that must be placed in an appropriate class with Jakarta Validation imports. When `validateParameters` receives `new Customer("", "a@b")` at the `customer` position, `@Valid` triggers deep validation down to `Customer.name`. `@NotNull` applies to the **`customer` parameter itself** to catch a null customer.

`@Valid` and `@NotNull` serve different purposes: one descends into the object graph, while the other checks for null at the current level. If the input is `null` and only `@Valid` is present, cascaded validation typically ignores the null value.

### 7.2. Return Value Is a DTO or Container

```java
@NotNull
@Valid
public Customer findCustomer(String id) {
    // ...
}

public List<@NotBlank String> listCodes() {
    // ...
}
```

`validateReturnValue` can validate `@NotNull` on the return value, cascade `@Valid` through the object, and enforce constraints on **container elements** such as each `String` in a `List`. For `List<@NotBlank String>`, the provider uses the built-in value extractor for `List` to check each element and report its index where appropriate.

For methods returning `void`, there is no useful return value to validate; those cases typically focus on parameters or cross-parameter rules.

### 7.3. Constructor Return and `@Valid`

With `@Valid public Invoice(...)` in section 5, the provider is instructed to cascade over the **instance after construction**. If you want to validate fields of an object without relying on constructor metadata, you can also use `validator.validate(invoice)`; however, that is a separate bean validation API rather than constructor contract validation. The two should not be assumed to be automatically equivalent.

## 8. Cross-Parameter Constraints: Inspecting Multiple Arguments Together

Many business rules do not belong to a single argument: for example, start date must not be later than end date.

```java
@ValidDateRange
public void schedule(LocalDate startDate, LocalDate endDate) {
    // ...
}
```

`@ValidDateRange` here is a **custom cross-parameter constraint**, not built into Jakarta Validation. The annotation needs `METHOD`/`CONSTRUCTOR` targets, a `@Constraint` declaration, and a `ConstraintValidator` targeting the parameter array.

An illustrative validator core:

```java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, Object[]> {

    @Override
    public boolean isValid(
            Object[] values, ConstraintValidatorContext context) {
        if (values == null || values.length != 2) {
            return false;
        }

        LocalDate start = (LocalDate) values[0];
        LocalDate end = (LocalDate) values[1];

        return start == null || end == null || !start.isAfter(end);
    }
}
```

The snippet above **is not a standalone program** because it requires declaring `@ValidDateRange` and importing `java.time.LocalDate`, `jakarta.validation.*`, and `jakarta.validation.constraintvalidation.*`. When an annotation supports both generic constraints and cross-parameter validation, you may need `validationAppliesTo = ConstraintTarget.PARAMETERS` to disambiguate per the specification.

Both `validateParameters` and `validateConstructorParameters` evaluate cross-parameter constraints. This kind of violation usually has a `<cross-parameter>` node and `getInvalidValue()` as `Object[]`. Placing two `@NotNull` annotations on the parameters alone does not enforce a comparison rule between the two dates.

## 9. Groups in Manual Validation

Every `ExecutableValidator` method accepts `Class<?>... groups` varargs. If omitted, the provider runs the `Default` group. A constraint assigned to a custom group **does not run automatically with Default** unless you request that group or have relevant group inheritance/group sequences.

Illustrative example:

```java
public interface StrictCheck {}

public void publish(
        @NotBlank String title,
        @Size(min = 8, groups = StrictCheck.class)
        String content) {
    // ...
}
```

Assuming you have already obtained the matching `publishMethod` and `service` for the declaration above:

```java
executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"});
// Default: does not check @Size belonging to StrictCheck.

executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"},
        StrictCheck.class);
// StrictCheck: @Size is violated. Default @NotBlank
// is not automatically evaluated when only StrictCheck is requested.

executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"},
        jakarta.validation.groups.Default.class,
        StrictCheck.class);
// Requests both Default and StrictCheck.
```

The code above is an **API illustration**, not part of `ExecutableDemo.java` from section 5. When you need ordered stages that stop on failure, check `@GroupSequence` rather than assuming varargs ordering forces sequential execution.

## 10. How Does Spring Framework Invoke Method Validation?

### 10.1. Spring AOP for Services

A common way to automatically trigger method validation at the service layer is:
- Having a Jakarta Validation provider on the classpath.
- Having `MethodValidationPostProcessor` (in many Spring Boot applications with the validation starter, Boot auto-configures it).
- Placing Spring's `@Validated` on the **bean class** and invoking methods through the **Spring proxy**.

The following snippet is for a configured Spring application, **not the standalone Java file** from section 5:

```java
@Service
@Validated
public class PriceService {

    @NotNull
    public BigDecimal calculate(
            @NotBlank String sku,
            @Positive int quantity) {

        return BigDecimal.TEN;
    }
}
```

If using plain Spring Framework and declaring the post-processor manually:

```java
@Configuration
class ValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

You need imports for Spring `@Service`, `@Validated`, `@Configuration`, `@Bean`, `MethodValidationPostProcessor`, Jakarta `@NotNull`/`@NotBlank`/`@Positive`, and `java.math.BigDecimal`.

With the default `MethodValidationPostProcessor` configuration, violations may be thrown as `jakarta.validation.ConstraintViolationException`. Spring also provides `setAdaptConstraintViolations(true)` to throw `MethodValidationException` with results adapted via `MessageSourceResolvable`.

**Proxy limitations:** If you call `this.calculate(...)` inside `PriceService` itself, or create an instance with `new PriceService()` outside Spring, the invocation bypasses the proxy so AOP method validation may not run. Direct `ExecutableValidator` is an option when you want explicit validation at a specific code point without relying on AOP.

### 10.2. Spring MVC 6.1+ Has Built-In Method Validation

Starting in Spring Framework 6.1, MVC natively supports handler method validation when constraints are placed **directly** on method parameters or the return value. Example (illustrative controller snippet):

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping("/{code}")
    public String lookup(
            @PathVariable @NotBlank String code) {

        return code;
    }
}
```

- If MVC runs **method validation** because there is a direct `@Constraint` on a parameter/return value, the error is typically `HandlerMethodValidationException`.
- If it only validates a `@Valid @RequestBody` or `@ModelAttribute` DTO via standard argument validation, the error is typically `MethodArgumentNotValidException`.
- `@Valid` itself is not a constraint and does not by itself make MVC select the method validation branch; it marks cascading.
- For controllers that had class-level `@Validated` to trigger legacy AOP-style validation, Spring MVC 6.1+ documentation advises removing class-level `@Validated` to use the new built-in branch.

Because exception types and HTTP handling differ by handler signature, do not hardcode a single exception for all cases in `@ControllerAdvice`.

### 10.3. Calling the API Manually Inside a Spring Bean

You can inject the Spring-configured `jakarta.validation.Validator` and obtain the executable API:

```java
@Component
public class ManualMethodChecker {

    private final Validator validator;

    public ManualMethodChecker(Validator validator) {
        this.validator = validator;
    }

    public <T> Set<ConstraintViolation<T>> check(
            T target, Method method, Object[] values) {
        return validator.forExecutables()
                .validateParameters(target, method, values);
    }
}
```

This is an illustrative snippet requiring Spring, Jakarta Validation, reflection, and collections imports. This approach fits custom framework integrations or dynamic method-invocation workflows. If a normal call is already validated by a Spring proxy, adding manual checks along the same path can cause **double validation** without strengthening contract guarantees.

## 11. Reflection: Preparing Input Data Accurately

### 11.1. Method Overloads

`Class.getMethod(name, parameterTypes...)` accepts **exact parameter types**. With two overloads:

```java
public void save(String id, int amount) { /* ... */ }
public void save(String id, long amount) { /* ... */ }
```

Two distinct `Method` objects:

```java
Method a = Target.class.getMethod("save", String.class, int.class);
Method b = Target.class.getMethod("save", String.class, long.class);
```

This is an illustrative snippet assuming the methods are in `Target`. `Object[]` must match the count, order, and types of the arguments. Primitives such as `int` are passed as boxed `Integer` in the array. Never pick the first method arbitrarily by name alone.

### 11.2. Zero Arguments, Varargs, and Null

- For a no-argument method, pass `new Object[0]`. Do not pass `parameterValues = null` itself.
- Individual **elements** inside `Object[]` may be `null` where appropriate so `@NotNull` catches them. However, passing `null` for the arguments array itself is an invalid API call.
- Varargs such as `String... values` appear in reflection as a final parameter of type `String[]`. When building `Object[]`, pass **a single element containing the `String[]` array** in the last slot.
- `validateReturnValue` takes a return value matching the method's type; calling the API with a `Method` that does not belong to the target object or an incompatible data type can raise `IllegalArgumentException`.
- `getMethod` only finds public methods; for nonpublic methods, `getDeclaredMethod` is a different reflection API, and accessibility/interceptability depends on the environment.

### 11.3. Method Inheritance and Static Methods

Under Jakarta Validation, method constraints follow Liskov-style contract rules: subclasses may not arbitrarily **strengthen parameter preconditions** on overridden methods; return constraints may strengthen postconditions within specification limits. Invalid declarations in a hierarchy can lead to `ConstraintDeclarationException`. Do not mark cascaded returns repeatedly in an invalid way along the same inheritance branch.

**Static methods** are not guaranteed by portable Jakarta Validation method validation. Do not rely on constraints on static methods as business guards without a dedicated validation mechanism.

## 12. Direct API Calls and `@ValidateOnExecution`

`jakarta.validation.executable.ValidateOnExecution` and executable validation configuration in `validation.xml` guide **automatic integration layers** on which executables to intercept. According to the Jakarta Validation specification, the four `ExecutableValidator` methods called **explicitly** still perform their checks even when automatic executable validation configuration excludes that executable. This is an important distinction when debugging "direct calls fail validation, but normal service calls produce no exception."

Do not assume `@ValidateOnExecution` disables `Validator.forExecutables()`; it is not an off switch for the manual validation API.

## 13. Exceptions and Handling Violations

| Situation | Outcome |
| --- | --- |
| `@NotBlank`, `@Min`, or cascade evaluates to false | Non-empty `ConstraintViolation` set; direct API does not throw business validation exceptions itself |
| Incompatible object/Method/Constructor, wrong argument count/types, null in required API parameter | `IllegalArgumentException` |
| No validator supports the type targeted by the constraint (e.g., `@NotBlank` on `int`) | `UnexpectedTypeException`, a subtype of `ValidationException` |
| Invalid constraint declaration or method inheritance constraint rule violation | `ConstraintDeclarationException` or related configuration error |
| Spring AOP automatically intercepts invocation | Typically `ConstraintViolationException`, possibly `MethodValidationException` if adapted |
| Spring MVC method validation on handler | Potentially `HandlerMethodValidationException` (especially with direct constraints on parameters/return) |

If you orchestrate invocation yourself:

```java
var violations = executable.validateParameters(
        service, method, new Object[] {"", 0});

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

This snippet uses variables from section 5 and assumes `jakarta.validation.ConstraintViolationException` is imported. It shows that the exception is **thrown by the application itself**. Never use `catch (ValidationException ignored)` to swallow provider configuration errors. When returning errors over the network, include only controlled path/message/code fields, and never automatically expose raw `getInvalidValue()`.

## 14. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Calling a Java method directly and expecting constraints to block it | Annotations are only metadata | Configure appropriate Spring integration or call `ExecutableValidator` |
| Using `validator.validate(service)` to check method arguments | Lacks `Method` and parameter values | Use `validateParameters` |
| Forgetting to validate the return value | Checked precondition only, skipped postcondition | Call `validateReturnValue` on the actual return value |
| Calling validation with `Object[]` in the wrong order | Reflection argument mapping mismatch | Match the exact signature and pass indexes accurately |
| Passing `null` instead of `new Object[0]` | API requires a valid arguments array | Pass an empty array for zero-argument methods |
| Forgetting `@Valid` on constructor while expecting instance fields to be scanned | No cascade from constructor return | Put `@Valid` on the constructor or invoke bean validation separately |
| Assuming `Set<ConstraintViolation>` has a fixed order | No ordering guarantee | Sort by path/code if deterministic output is needed |
| Assuming parameter names are always `arg0` | Names depend on ParameterNameProvider/compiler | Inspect node kind; use `-parameters` if real names are needed |
| Method validation missing on `this.serviceMethod()` | Self-invocation bypasses Spring proxy | Route calls through the proper bean proxy or validate manually |
| Mixing `javax.validation` with Spring Boot 3+'s Jakarta Validation | Different namespace/API generation | Consistently use `jakarta.validation` and compatible dependencies |

## 15. Testing Strategy

For each method with a validation contract, cover these independent scenarios:

1. **Precondition:** `null`, blank, min/max, DTO cascade, list/container elements.
2. **Cross-parameter:** individual values may be valid, yet the relationship between two parameters is invalid.
3. **Postcondition:** method returns `null`, blank, a DTO with invalid fields, or a collection containing invalid elements.
4. **Constructor:** invalid argument before construction; invalid state after construction.
5. **Groups:** `Default` and each custom group, plus group sequences if any.
6. **Integration:** run the same rules through the real service proxy or MVC layer as in production, rather than extrapolating from `validator.validate(bean)`.

Verify `getPropertyPath()` (via node kind where possible), `getMessageTemplate()`, and violation counts. In the `Invoice` example, constructor parameter and constructor return may carry similar "blank" message meanings, yet they represent **two distinct phases**, reflected in their error paths.

## 16. Practice Exercises

1. Change `@Min(1)` in `ReceiptService.issue` to `@Min(3)`. Re-test `{"P1", 2}` with `validateParameters` and predict the outcome.
2. Try calling `service.issue("", 0)` in plain Java and inspect the return value. Explain why the call still executes when no interceptor is present.
3. Remove `@Valid` from the `Invoice` constructor. Compare `validateConstructorReturnValue(constructor, new Invoice(""))` with `validator.validate(new Invoice(""))` to see the difference between constructor contracts and bean validation.
4. Add a `@Valid Customer` method parameter, leave one field blank intentionally, and observe the violation path.
5. Add a `StrictCheck` group to a constraint; call `validateParameters` with Default, StrictCheck, and both.
6. Turn `ReceiptService` into a `@Validated` Spring bean, test calling from another bean through the proxy and from `this.issue(...)`, and explain the results.

**Takeaway:** `ExecutableValidator` lets you explicitly validate "which method/constructor, which arguments/return value, and which groups." The API **returns violations**; aborting calls, throwing exceptions, or returning HTTP errors belongs to the integration layer. In Spring, automatic method validation is simply an orchestration mechanism running these checks around an invocation when properly configured and invoked through the right path.

## References

- [Jakarta Bean Validation 3.0 specification — Method/constructor constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Jakarta Bean Validation 3.0 specification — `ExecutableValidator`](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#validationapi)
- [Jakarta Validation API 3.0 — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator)
- [Hibernate Validator 8 — Method/constructor constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-method-constraints)
- [Spring Framework — Method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)