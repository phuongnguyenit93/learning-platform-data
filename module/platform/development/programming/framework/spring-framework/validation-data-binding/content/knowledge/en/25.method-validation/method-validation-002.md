# @Valid with Parameters and Results Containing Nested Objects in Method Validation

## Lesson Objectives

A method may accept a DTO containing multiple layers of objects while returning a DTO that contains other objects. For example, `BookingCommand` contains `Customer` and `Address`; the returned `BookingReceipt` contains `Delivery`, which in turn contains `Address`. When constraints reside inside child objects, placing constraints only on the method itself is not enough: you need to understand **cascaded validation** with `@Valid`.

After this lesson, you will be able to:

- Explain what `jakarta.validation.Valid` does on **method parameters**, **return values**, and each link to nested objects.
- Distinguish `@Valid` from direct constraints such as `@NotNull`, `@NotBlank`, `@Min`, and `@NotEmpty`.
- Manually validate inputs with `ExecutableValidator.validateParameters()` and outputs with `validateReturnValue()`.
- Read error locations in `ConstraintViolation.getPropertyPath()` in both directions.
- Integrate into services via Spring method validation, into controllers via Spring MVC, and know when different validation mechanisms are triggered.
- Properly handle `null`, collections, validation groups, method inheritance, and common pitfalls.

## 1. Why Is @Valid Important for Nested Objects?

Consider the data structure:

~~~text
BookingCommand (parameter of place)
├── customer: Customer
│   ├── name: String             @NotBlank
│   └── address: Address         @Valid
│       └── city: String         @NotBlank
└── seats: int                   @Min(1)

BookingReceipt (return value of place)
├── id: String                   @NotBlank
└── delivery: Delivery           @Valid
    └── address: Address         @Valid
        └── city: String         @NotBlank
~~~

If you only validate `BookingCommand` at the outer level and do not permit traversing the `customer` association, Bean Validation will not automatically validate every arbitrary object reachable from the root object. `@Valid` marks **the link that traversal must follow**.

Declaration example:

~~~java
public final class BookingCommand {
    @NotNull
    @Valid
    private Customer customer;
}
~~~

Here:

- `@NotNull` checks whether the **`customer` reference itself** is present.
- `@Valid` instructs the provider to **enter the `Customer` object** to validate the constraints inside it.
- If `Customer.address` is also a child object, that field/getter needs `@Valid` to continue to `Address.city`.
- `@Valid` **does not** impose data conditions on its own; it is a **cascade marker**, not a constraint annotation like `@NotNull`.

This distinction explains why `@Valid` is often paired with `@NotNull` at important boundaries. An association may be valid in format whenever it is non-`null`, yet business rules still require it to exist.

## 2. Three Places to Use @Valid in Method Validation

Suppose a service has the method:

~~~java
@NotNull
@Valid
public BookingReceipt place(@NotNull @Valid BookingCommand command) {
    // ...
}
~~~

Meaning of each position:

| Position | Annotation | Effect |
| --- | --- | --- |
| On parameter `command` | `@NotNull` | Disallows passing `null` |
| On parameter `command` | `@Valid` | Cascades validation into constraints inside `BookingCommand` |
| On method returning `BookingReceipt` | `@NotNull` | Disallows a `null` return value |
| On method returning `BookingReceipt` | `@Valid` | Cascades validation into constraints inside the result |
| On DTO fields `customer` and `delivery` | `@Valid` | Continues traversing child objects, potentially across multiple levels |

### 2.1. Validation Before Calling the Method

A method validation integration can validate parameters **before executing the method body**:

~~~text
caller
  -> interceptor / AOP / framework
  -> validateParameters(target, method, arguments)
  -> on error: reject call or throw exception
  -> on no error: execute method body
~~~

As a result, invalid input can be blocked before the service mutates data or executes business logic. However, the Jakarta Validation API itself **does not automatically intercept** a regular Java call: the trigger point must be configured or invoked explicitly.

### 2.2. Validation After the Method Returns

The result can also be validated:

~~~text
method body returns BookingReceipt
  -> validateReturnValue(target, method, receipt)
  -> on error: validation integration reports postcondition error
  -> on no error: return result to caller
~~~

This is a **postcondition** check: it helps detect when a service produces output that breaks its contract. Return value errors are typically application errors or server-side data issues, and should not automatically be treated as HTTP 400 client input errors.

### 2.3. Recursive Traversal Is Not Limited to One Level

Constraints on `Address.city` are discovered only when each necessary link is annotated:

~~~text
@Valid on method parameter
    ↓
BookingCommand.customer has @Valid
    ↓
Customer.address has @Valid
    ↓
Address.city has @NotBlank
~~~

If you omit `@Valid` on `Customer.address`, checking `Address.city` along that branch stops, even though `Address.city` still has `@NotBlank`.

Similarly, for the return value:

~~~text
@Valid on method return
    ↓
BookingReceipt.delivery has @Valid
    ↓
Delivery.address has @Valid
    ↓
Address.city has @NotBlank
~~~

Do not assume that merely adding `@Valid` on the `Address` class or declaring `@NotBlank` on the `city` field causes every method returning it to be validated automatically.

## 3. How Does @Valid Differ from validator.validate(bean)?

There are two entry points into Bean Validation that developers easily confuse:

**Path 1 — bean validation:** `Validator.validate(bean)` starts at an existing object. It validates constraints on the bean and follows `@Valid` fields/properties. For example, `validator.validate(new BookingCommand(...))` validates `customer`, `address`, and `seats` if the metadata is declared properly.

**Path 2 — method validation:** `Validator.forExecutables()` provides `ExecutableValidator`. It checks constraints/cascades declared **on parameters** or **return values** of a method/constructor. Core API:

~~~java
ExecutableValidator executable = validator.forExecutables();

Set<ConstraintViolation<ServiceType>> inputErrors =
        executable.validateParameters(
                service, method, methodArguments);

Set<ConstraintViolation<ServiceType>> outputErrors =
        executable.validateReturnValue(
                service, method, returnedObject);
~~~

This is illustrative code using generic variables, not a standalone Java file. These two APIs **do not invoke the method** for you; `validateParameters()` accepts arguments, while `validateReturnValue()` accepts an already-produced result. You must pass the appropriate `Method` and target object.

`validator.validate(service)` does not scan and execute every method on the service to validate hypothetical parameters/return values. Conversely, `validateReturnValue(...)` does not re-validate parameters from the earlier call. Each step has a clear role.

## 4. Standalone Runnable Java 17+ Example: Multi-Level Nested Input and Output

The sample project has the file `src/main/java/com/example/validation/Demo.java`. It runs using the Jakarta Validation API with a provider such as Hibernate Validator. Constraints placed on private fields are read from metadata by Bean Validation; getters are not required just to make this example work.

### 4.1. Complete Source Code

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.lang.reflect.Method;
import java.util.Set;

public final class Demo {

    public static final class Address {
        @NotBlank
        private final String city;

        public Address(String city) {
            this.city = city;
        }
    }

    public static final class Customer {
        @NotBlank
        private final String name;

        @NotNull
        @Valid
        private final Address address;

        public Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    public static final class BookingCommand {
        @NotNull
        @Valid
        private final Customer customer;

        @Min(1)
        private final int seats;

        public BookingCommand(Customer customer, int seats) {
            this.customer = customer;
            this.seats = seats;
        }
    }

    public static final class Delivery {
        @NotNull
        @Valid
        private final Address address;

        public Delivery(Address address) {
            this.address = address;
        }
    }

    public static final class BookingReceipt {
        @NotBlank
        private final String id;

        @NotNull
        @Valid
        private final Delivery delivery;

        public BookingReceipt(String id, Delivery delivery) {
            this.id = id;
            this.delivery = delivery;
        }
    }

    public static final class BookingService {

        @NotNull
        @Valid
        public BookingReceipt place(
                @NotNull @Valid BookingCommand command) {

            // Result intentionally has an empty city to illustrate
            // postcondition (return value) validation.
            return new BookingReceipt(
                    "R-1",
                    new Delivery(new Address("")));
        }
    }

    private static void report(
            String label,
            Set<? extends ConstraintViolation<?>> violations) {
        System.out.println(label + ": " + violations.size());
    }

    public static void main(String[] args) throws Exception {

        BookingService service = new BookingService();
        Method place = BookingService.class.getMethod(
                "place", BookingCommand.class);

        BookingCommand invalidCommand = new BookingCommand(
                new Customer("", new Address("")),
                0);

        BookingCommand validCommand = new BookingCommand(
                new Customer("An", new Address("Ha Noi")),
                2);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var executable = validator.forExecutables();

            var invalidInput = executable.validateParameters(
                    service, place,
                    new Object[] { invalidCommand });

            var validInput = executable.validateParameters(
                    service, place,
                    new Object[] { validCommand });

            report("invalid input", invalidInput);
            report("valid input", validInput);

            // Only execute business logic with valid input.
            BookingReceipt receipt = service.place(validCommand);

            var invalidOutput = executable.validateReturnValue(
                    service, place, receipt);

            report("invalid output", invalidOutput);
        }
    }
}
~~~

Why are there three input errors? `BookingCommand.seats == 0` violates `@Min(1)`, `Customer.name == ""` violates `@NotBlank`, and `Customer.address.city == ""` violates `@NotBlank`. Both deep branches are reachable through `@Valid` links.

Why is there one output error? `BookingService.place(...)` returns a `BookingReceipt` with `Delivery.address.city == ""`. Thanks to `@Valid` on the method return value and the two links in the result, Bean Validation reaches `Address.city` and detects `@NotBlank`.

Important: the `place(...)` method **does not validate itself** inside the method body. In the demo, we explicitly invoke the two steps of `ExecutableValidator`, and only then call the method with valid input.

### 4.2. Build and Run

Create `pom.xml` in the project directory:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>cascaded-method-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
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
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Using JDK 17+ and Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

**Exactly three lines printed by the `Demo` program**, excluding Maven or provider logs:

~~~text
invalid input: 3
valid input: 0
invalid output: 1
~~~

`<parameters>true</parameters>` makes the compiler store Java parameter names in class files; this helps when reading paths. Without real name metadata, paths may use `arg0` instead of `command`, though the violation counts in the demo remain unchanged.

Hibernate Validator 8.x is a Jakarta Validation 3.0 provider suited for the Java 17 example. The example provides the provider and Jakarta EL implementation directly so it runs outside Spring. In a Spring Boot 3 application that already has `spring-boot-starter-validation`, use the project's dependency management rather than copying these fixed Maven versions verbatim.

### 4.3. Reading Error Paths Accurately

`ConstraintViolation.getPropertyPath()` is a sequence of **typed nodes**, not merely a character string. When displaying or debugging, you can use:

~~~java
for (ConstraintViolation<?> violation : invalidInput) {
    System.out.println(
            violation.getPropertyPath() + " -> "
            + violation.getMessage());
}
~~~

This is a **snippet meant to go inside the `main` method** while the `invalidInput` variable is in scope; it is not a complete class. Because `Set` does not guarantee iteration order, do not rely on a specific line order from this loop.

With Java classes compiled with `-parameters` and a typical provider, the paths look like:

~~~text
place.command.customer.name
place.command.customer.address.city
place.command.seats

place.<return value>.delivery.address.city
~~~

The first three lines are input paths (in no particular order); the last line is the return value path. Names like `place` and `command` come from the method signature; `customer`, `address`, and `city` are property names from bean metadata.

Node model:

~~~text
Input:
METHOD(place)
  -> PARAMETER(command, index=0)
     -> PROPERTY(customer)
        -> PROPERTY(address)
           -> PROPERTY(city)

Return:
METHOD(place)
  -> RETURN_VALUE(<return value>)
     -> PROPERTY(delivery)
        -> PROPERTY(address)
           -> PROPERTY(city)
~~~

You can read nodes via the API instead of splitting strings:

~~~java
for (ConstraintViolation<?> violation : invalidInput) {
    for (jakarta.validation.Path.Node node
            : violation.getPropertyPath()) {

        System.out.println(
                node.getKind() + " : " + node.getName());

        if (node.getKind()
                == jakarta.validation.ElementKind.PARAMETER) {

            var p = node.as(
                    jakarta.validation.Path.ParameterNode.class);

            System.out.println(
                    "parameterIndex=" + p.getParameterIndex());
        }
    }
}
~~~

This is also a snippet to insert inside `main`. If you need to return errors by parameter name or position, `Path.ParameterNode.getParameterIndex()` is more reliable than parsing dot-separated paths manually; the structure may also include container element nodes and indexes/keys.

## 5. What Happens with null?

Core rule: **cascaded validation ignores `null` references**. `@Valid` by itself does not mean a value is required.

| Declaration | Value | Result |
| --- | --- | --- |
| `@Valid BookingCommand command` | `null` | No error from `@Valid` alone |
| `@NotNull @Valid BookingCommand command` | `null` | `@NotNull` error |
| `@Valid BookingCommand command` | instance with `customer == null` | Error only if `customer` property has its own constraint like `@NotNull` |
| `@NotNull @Valid Customer customer` | `null` | `@NotNull` error, does not descend into child fields |
| `@Valid` on method return | `null` | `@Valid` alone produces no error |
| `@NotNull @Valid` on method return | `null` | Violates `@NotNull` constraint on the return value |

For example, when both the parameter and the result must be present:

~~~java
@NotNull
@Valid
public BookingReceipt place(
        @NotNull @Valid BookingCommand command) {
    // ...
}
~~~

That is why `@NotNull` and `@Valid` are combined in the demo.

Note that `@NotBlank` only suits `CharSequence` values; `@NotEmpty` is for string/collection/map/array types supported by the constraint; `@Min` validates numeric values, not collection sizes. Choose constraints matching the data type being validated.

## 6. @Valid on Collections and Container Elements

Many methods accept or return `List`/`Map` containing DTOs inside. Jakarta Bean Validation supports **container element validation** with `@Valid` placed on the type argument.

Example:

~~~java
public void placeBatch(
        @NotEmpty java.util.List<@Valid BookingCommand> commands) {
    // ...
}
~~~

Two meanings:

- `@NotEmpty` checks that **the list is not empty**.
- `@Valid` in `List<@Valid BookingCommand>` marks **each DTO element** to cascade into its internal constraints.

If `commands` contains a `null` element, `@Valid` on that element ignores it. To forbid `null` elements, add a constraint to the type argument:

~~~java
public void placeBatch(
        @NotEmpty java.util.List<
                @NotNull @Valid BookingCommand> commands) {
    // ...
}
~~~

Example of a return value containing a list of receipts:

~~~java
@NotNull
public java.util.List<@Valid BookingReceipt> listReceipts() {
    // ...
}
~~~

When **return-value validation is enabled**, the provider can cascade into each `BookingReceipt`, and then follow `@Valid` on `delivery`/`address`. To forbid an empty list, use `@NotEmpty`; to forbid null elements, add `@NotNull` on the type argument.

With a map:

~~~java
public void accept(
        java.util.Map<@NotBlank String, @Valid BookingCommand> items) {
    // ...
}
~~~

A constraint on the key (such as `@NotBlank`) and cascading into the value (`@Valid`) are two separate checks. Container elements with a matching value extractor are validated according to the element type; paths may include indexes/keys and `CONTAINER_ELEMENT` nodes.

### Nested Containers

Example with data shaped like `List<List<BookingCommand>>`:

~~~java
public void acceptGroups(
        java.util.List<java.util.List<@Valid BookingCommand>> groups) {
    // ...
}
~~~

`@Valid` is placed on the type argument of the innermost container to validate. When designing complex structures, ensure paths and value extractors match rather than assuming the validator traverses every container level automatically. According to Jakarta Validation, you should not simultaneously place `@Valid` on **a container itself and its corresponding type argument** just to force double cascading; choose a clear placement for each element to traverse.

## 7. Spring Framework: Service Method Validation

In Spring, Bean Validation is often triggered automatically at certain boundaries via integration. For Spring-managed **service methods**, the typical approach is proxy-based method validation.

Abbreviated example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingApplicationService {

    @NotNull
    @Valid
    public BookingReceipt place(
            @NotNull @Valid BookingCommand command) {

        // Return a valid receipt according to business rules.
        return createReceipt(command);
    }

    private BookingReceipt createReceipt(BookingCommand command) {
        // Illustrative helper, needs to be implemented in a real application.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

The Spring snippet above only illustrates **where to place annotations** and assumes the DTOs are already defined; it is not a standalone runnable program. In a real application, you must implement `createReceipt` and configure method validation (for example, Spring Boot with the validation starter and an appropriate `MethodValidationPostProcessor` bean).

When **another** component calls `place(...)` through the Spring-managed proxy, the validation interceptor can:

1. Validate `command` and nested objects using `validateParameters()`.
2. Execute the method if there are no violations.
3. Validate the returned `BookingReceipt` using `validateReturnValue()`, including child objects.
4. Report errors if constraints on parameters or the result are violated.

With standard Spring AOP method validation configuration, errors may be reported via `ConstraintViolationException`; some configuration modes use different exceptions/adapted results. Do not write error handling assuming the entire application uses only one exception type without checking the Spring version and configuration.

### Proxy Limitations to Understand

- **Self-invocation:** a method in the same bean calling `this.place(...)` generally bypasses the Spring AOP proxy, so interceptor validation may not run.
- **Not every object is a Spring bean:** manually instantiating `new BookingApplicationService()` does not give it a proxy.
- **Method visibility / final / proxy type:** Spring's proxy rules affect which methods are intercepted; verify calls actually go through the proxy.
- **Asynchronous branches:** future/reactive container return types require understanding how the active framework performs validation; do not infer that `@Valid` automatically validates an object emitted in the future the same way as a synchronous return value.
- **Exception-throwing branches:** if a method does not produce a normal return value, there is no ordinary result object to validate at the return step.

In other words, annotations describe **validation metadata**; the framework mechanism decides **when** and **where** to call the APIs that enforce it.

## 8. Spring MVC: @Valid @RequestBody and Return Value Validation

In REST controllers, `@Valid @RequestBody` is commonly used to validate a DTO parsed from an HTTP request:

~~~java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class BookingController {

    @PostMapping("/bookings")
    BookingReceipt create(
            @Valid @RequestBody BookingCommand command) {
        // Call the actual service.
        throw new UnsupportedOperationException("Illustration only");
    }
}
~~~

This snippet illustrates controller configuration; when implementing, replace the body with real business logic.

**When only `@Valid` is on a DTO parameter:** Spring MVC can validate the individual object at the argument resolution step, typically reporting `MethodArgumentNotValidException` on errors when no matching `BindingResult` handles them. `@Valid` is not itself a constraint and **alone does not necessarily trigger method validation** across the entire controller signature.

**When the method itself needs validation:** starting in Spring Framework 6.1, Spring MVC supports native method validation for controllers when there are direct constraints on parameters or the return value. Example:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StrictBookingController {

    @PostMapping("/strict-bookings")
    @NotNull
    @Valid
    BookingReceipt create(
            @NotNull @Valid @RequestBody BookingCommand command) {
        // Call the service and return a valid BookingReceipt.
        throw new UnsupportedOperationException("Illustration only");
    }
}
~~~

In this case `@NotNull` is a direct constraint, so Spring MVC method validation can cover nested constraints via `@Valid` as well. When method validation handles errors, Spring MVC 6.1+ uses `HandlerMethodValidationException`; standalone argument-level validation typically uses `MethodArgumentNotValidException`.

API design notes:

- For **input**, the controller may convert DTO errors into HTTP 400; handle the exact exception type and follow the application's API policy.
- For **return values**, errors usually indicate a server-side issue, so do not present them as client input errors. `HandlerMethodValidationException` for return-value validation is handled by Spring MVC with different semantics than parameter errors.
- If a controller has `@Validated` at the **class level**, method validation may route through an AOP proxy. To use the native method validation introduced in Spring MVC 6.1, Spring documentation recommends removing class-level `@Validated` from controllers where appropriate.
- `@Valid` on `@RequestBody` and `@Valid` on the return result have **two different trigger points**; validating the request body does not prove the return value is being validated.
- When `Errors`/`BindingResult` is placed in the right position, Spring MVC can pass certain input errors to the controller to handle instead of throwing an exception immediately. Behavior also depends on whether the method has direct constraints on other parameters.

### Avoiding Component Name Confusion

| Component | Role |
| --- | --- |
| `jakarta.validation.Valid` | Marker for cascading into child objects |
| `jakarta.validation.constraints.NotNull` | Direct constraint forbidding null |
| `jakarta.validation.Validator` | API for validating a bean; provides `forExecutables()` |
| `jakarta.validation.executable.ExecutableValidator` | API for validating method/constructor parameters and return values |
| `org.springframework.validation.annotation.Validated` | Spring annotation supporting groups and method validation integration in appropriate contexts |
| `@RequestBody` | Spring MVC binds the HTTP body into an argument |
| `@ControllerAdvice` / `@ExceptionHandler` | Where the application customizes HTTP error responses |

When writing an exception handler, inspect the source of each `ConstraintViolation` and return error paths matching the API contract, rather than lumping every error together as "field invalid" without distinguishing parameters, nested properties, or return values.

## 9. Validation Groups Flowing Through Nested Objects

Bean Validation supports **groups** to select which set of constraints to apply. By default, when cascading via `@Valid`, the active group continues to propagate down to child objects (accounting for group/group sequence rules).

Example:

~~~java
interface DetailedChecks { }

final class Address {
    @jakarta.validation.constraints.NotBlank(
            groups = DetailedChecks.class)
    String city;
}
~~~

The snippet above only illustrates group metadata and does not stand alone from the classes in the demo. If a method parameter is validated under `Default` while `city` belongs only to `DetailedChecks`, that constraint will not run just because `@Valid` is present.

You can use `@ConvertGroup` on a cascade edge to switch groups:

~~~java
@jakarta.validation.Valid
@jakarta.validation.groups.ConvertGroup(
        from = jakarta.validation.groups.Default.class,
        to = DetailedChecks.class)
private Address address;
~~~

This means that when reaching the `address` link under the `Default` group, the group for the cascaded object switches to `DetailedChecks`. Design this carefully: group conversion applies **at the site of `@Valid`**; it is not a global filter changing constraints across the entire application. In Spring, `@Validated(SomeGroup.class)` can select the entry group depending on the integration point. When method validation runs, which group executes depends on the integration/caller configuration.

## 10. Method Inheritance Rules: Avoiding Incompatible Contracts

Bean Validation protects precondition and postcondition principles in inheritance:

- **Parameter constraints** (including cascade `@Valid` on parameters) generally may not be added on overriding/implementing methods to **strengthen preconditions** relative to the parent method/interface; a standard provider may throw `ConstraintDeclarationException` on invalid declarations.
- **Return-value constraints** may appear on subtype methods according to standard rules, because adding postconditions does not weaken the method's promise.
- However, **a return value must not be marked with cascade `@Valid` repeatedly along the same inheritance branch** if it is already marked on the parent/interface.

Example where the interface already has:

~~~java
interface BookingApi {
    @Valid
    BookingReceipt place(BookingCommand command);
}
~~~

The implementation should not re-add `@Valid` to the return value of the same method or add `@Valid` to parameters if the interface did not declare it, as this can violate Jakarta Validation rules. If constraints are part of the public contract, declare them consistently starting at the interface.

Some providers offer non-standard extensions, but portable applications should follow the general rules. When encountering `ConstraintDeclarationException`, first inspect overridden methods, interfaces, bridge methods, and annotation locations rather than stripping all constraints.

## 11. Validation Cycles and Common Pitfalls

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Parent DTO is valid even though child field is invalid | Missing `@Valid` on a link in the graph | Place `@Valid` on the reference edge leading to the object to check |
| `null` slips through unexpectedly | `@Valid` only cascades; it does not require data | Add `@NotNull` on the corresponding parameter/return/field |
| Input validation runs but bad output escapes | Missing `@Valid` on return value or no post-invocation validation | Configure return-value validation and check `validateReturnValue()` |
| Direct service call produces no error | Annotations without a method validation trigger | Call `ExecutableValidator` or configure an appropriate proxy/interceptor |
| In Spring, same-bean call does not trigger | Self-invocation bypasses the proxy | Call through a Spring-managed bean/proxy or redesign service boundaries |
| Unexpected exception type in controller | Spring MVC argument validation and method validation are two mechanisms | Distinguish `MethodArgumentNotValidException` and `HandlerMethodValidationException` |
| List contains an invalid item with no error | Not cascading into elements or missing value extractor | Use `List<@Valid Item>` and check metadata and integration |
| `null` element in list is accepted | `@Valid` does not forbid null | Use `List<@NotNull @Valid Item>` |
| No errors when validating via `validate(service)` | Field validation is not executable validation | Use `validator.forExecutables()` for methods/constructors |
| Duplicate cascade markers in override | Inheritance metadata rule violation | Review declarations across interface/parent/implementation |
| Tests fail on message ordering | `Set<ConstraintViolation>` has no guaranteed order | Assert using `propertyPath`/constraint descriptor; sort if needed |
| Violation path has multiple levels | Graph has property/container element nodes | Traverse each `Path.Node`; avoid blind string splitting |

### Notes on Cycles, Performance, and Safety

Cascaded validation traverses object graphs that may have many levels and many elements. A Jakarta Validation-compliant provider must prevent infinite loops when the object graph contains cycles (for instance, `Person.manager` pointing back to `Person`). Even so, very large graphs increase validation work: design DTOs and `@Valid` edges intentionally.

An object can have multiple paths leading to the same instance; providers may create violations associated with paths according to graph traversal rules. Do not rely on how many times a `ConstraintValidator.isValid()` is called to represent the number of requests or business operations.

Do not use Bean Validation to mutate input or perform important side effects. Validators should focus on returning validity state; modifying data, normalizing values, or calling databases with side effects belongs in the appropriate layer.

Do not reflect raw `getInvalidValue()` into logs or API responses for sensitive data. The path and message are sufficient to identify the error type in most use cases.

## 12. How to Test Input and Output Validation

At minimum, split tests into the following cases:

1. **Valid input:** `validateParameters()` returns an empty set; use a `BookingCommand` with valid `Customer.name`, `Address.city`, and `seats >= 1`.
2. **Invalid nested input on one branch:** set `Customer.address.city = ""` and check that the violation path contains property `city` under parameter `command`.
3. **Invalid nested input on multiple branches:** as in the demo, three errors on `seats`, `customer.name`, and `customer.address.city`.
4. **Null input:** test `command == null` to see `@NotNull` report an error. Then test removing `@NotNull` (in a separate test fixture) to confirm `@Valid` alone ignores null.
5. **Valid output:** return a `BookingReceipt` with a valid `delivery.address.city`, then call `validateReturnValue()`; the error set is empty.
6. **Invalid nested output:** return a `BookingReceipt` with a blank city and verify a return-value node appears in the path.
7. **Missing `@Valid` edge:** test a fixture omitting `@Valid` on `Delivery.address`; the nested city is not cascaded through that edge.
8. **Spring integration:** invoke the method from another bean via the proxy and verify the actual exception; controllers should be tested with `MockMvc` or an appropriate HTTP tool for error responses.

When testing method validation, obtain `Method` via `Class.getMethod(name, parameterTypes...)` with the exact signature; use `ValidatorFactory` with a real provider to verify metadata and cascading. Do not assume violation order in the `Set`; assert using `Path.Node`, constraint names, and error counts per fixture.

Example for isolating errors from the return value:

~~~java
var outputErrors = validator.forExecutables()
        .validateReturnValue(service, place, receipt);

boolean nestedCityViolation = outputErrors.stream()
        .map(v -> v.getPropertyPath().toString())
        .anyMatch(path -> path.endsWith("delivery.address.city"));
~~~

This is a snippet assuming `validator`, `service`, `place`, and `receipt` are already created; it does not run standalone. In production applications, you can inspect `Path.Node` by kind to handle paths containing containers/indexes rather than assuming every path ends with a fixed string.

## 13. Self-Check Summary

Try explaining these scenarios in your own words:

**Question 1.** Why is `@Valid` on the `BookingCommand` parameter not enough if `Customer.address` lacks `@Valid`?  
Because cascading only follows marked edges; it stops before `Address.city`.

**Question 2.** Why might `@Valid` on the return value fail to detect a completely missing object?  
Because null is ignored during cascading; requiring the return value to be present requires `@NotNull`.

**Question 3.** Can `validator.validate(service)` replace `validateReturnValue(service, method, result)`?  
No. The two APIs have different roots/metadata: bean fields versus executable constraints.

**Question 4.** In Spring MVC, do `@Valid @RequestBody` and method validation always throw the same exception?  
No. Depending on the method signature and direct constraints, Spring MVC may use standalone argument validation or method validation.

**Question 5.** Where should `@Valid` be placed if a method returns `List<BookingReceipt>`?  
You can use the type argument `List<@Valid BookingReceipt>` to cascade each element and continue into nested fields declared with `@Valid`; add `@NotNull`/`@NotEmpty` in the appropriate positions if business rules require them.

**Mental model:** `@Valid` specifies **the graph traversal path**, constraints like `@NotNull`/`@NotBlank` define **validity conditions**, and `ExecutableValidator` or Spring integration decides **when validation runs before/after method invocation**. Only by placing sufficient markers on parameters/return values and each child-object edge will you validate the entire intended data graph.

## References

- [Jakarta Bean Validation 3.0 specification — Object graph validation and method/constructor validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation — Valid annotation](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html)
- [Jakarta Validation — ExecutableValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/ExecutableValidator.html)
- [Hibernate Validator 8 Reference Guide — Cascaded validation and method constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework Reference — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework Reference — Method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
