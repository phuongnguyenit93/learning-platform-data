# Distinguishing Constructor Validation with Standard APIs from Spring AOP

## 1. Why Is Constructor Validation Easily Misunderstood?

When reading a Java class with constraints on its constructor, it is tempting to assume invalid data will be rejected as soon as `new` is called:

```java
public class Booking {
    private final String code;

    public Booking(@NotBlank String code) {
        this.code = code;
    }
}
```

However, in **plain Java**, calling `new Booking("")` still executes the constructor normally. `@NotBlank` is Jakarta Validation *metadata*, not an `if` statement automatically injected by the JVM. Enforcing a constructor's contract requires **an explicit validation trigger**, such as code calling `ExecutableValidator` or a dedicated integration layer.

Spring Framework provides `@Validated` and `MethodValidationPostProcessor`, yet standard Spring AOP uses **proxies for method calls on Spring beans**. Those proxies **do not intercept constructor invocations**. Therefore you cannot assume that "Spring method validation is enabled" means all `@NotBlank` constructor parameters are checked automatically.

This lesson distinguishes three operations:

1. **Constructor parameter validation:** checking arguments before instantiation.
2. **Constructor return value validation:** checking the *already-created object* against constraints/cascades declared on the constructor.
3. **Spring AOP method validation:** checking *method* parameters and return values when calls pass through a properly configured proxy.

The goal is choosing the right mechanism, avoiding confusing constructors with methods, practicing the standard APIs, and understanding the timing boundaries for preventing side effects.

## 2. Quick Comparison: Standard API vs. Spring AOP

| Aspect | Jakarta Validation: `ExecutableValidator` for constructors | Spring `MethodValidationPostProcessor` / AOP |
| --- | --- | --- |
| Target checked | Specific `java.lang.reflect.Constructor<?>` | `Method` invoked through a Spring proxy |
| Pre-phase | `validateConstructorParameters(constructor, args)` | Interceptor's method parameter validation |
| Post-phase | `validateConstructorReturnValue(constructor, createdObject)` | Interceptor's method return-value validation |
| Who triggers it? | Application/integration code explicitly calling the API | Spring proxy automatically triggers when an invocation passes through it |
| Automatically executes constructor/method? | **No**: API only validates passed-in values | Proxy wraps the real method call and can reject before/after |
| Depends on Spring? | No; part of Jakarta Validation, requires a provider | Yes, requires Spring beans/proxies and method validation infrastructure |
| Plain `new SomeClass(...)`? | Not validated automatically; must invoke API separately | Not intercepted by Spring AOP |
| Class-level `@Validated`? | Not needed; does not control these two constructor APIs | Typically the marker selecting beans for method validation |
| Error output | `Set<ConstraintViolation<T>>`; caller decides handling | Typically throws `ConstraintViolationException`, or Spring-adapted error types |
| Where used | Custom factories, testing, dynamic construction | Service/business methods called through bean proxies |

Some other containers/frameworks offer automatic constructor validation, yet **that is a feature of that specific integration**. Never treat it as default JVM or Spring AOP proxy behavior.

**Key rule:** `@Valid` on a constructor **is not equivalent** to `@Validated` on a class. `@Valid` on a constructor marks the *constructor return value* so a provider can cascade into the created object **when the corresponding validation API is invoked**.

## 3. The Two Constructor APIs on `ExecutableValidator`

From `jakarta.validation.Validator`, obtain:

```java
Validator validator = factory.getValidator();
ExecutableValidator executables = validator.forExecutables();
```

`ExecutableValidator` belongs to `jakarta.validation.executable`, the standard Jakarta Validation (Bean Validation) interface, independent of how Spring constructs beans.

### 3.1. `validateConstructorParameters` — Checking Before `new`

General signature:

```java
<T> Set<ConstraintViolation<T>> validateConstructorParameters(
        Constructor<? extends T> constructor,
        Object[] parameterValues,
        Class<?>... groups);
```

Inputs:

- `constructor`: reflection object pointing to the **exact** constructor to validate.
- `parameterValues`: argument array matching exact count, positions, and types; primitives like `int` are boxed as `Integer` inside `Object[]`.
- `groups`: validation groups to run; omit to run `Default`.

The provider evaluates constraints placed on individual parameters (`@NotBlank`, `@Min`, `@Valid`, etc.) as well as **cross-parameter** constraints if present. The method **does not execute the constructor**. On violations, it returns a non-empty `Set`; proceeding or aborting is the application's decision.

```java
Constructor<Booking> ctor =
        Booking.class.getConstructor(String.class, int.class);

Object[] args = {"", 0};

Set<ConstraintViolation<Booking>> problems =
        executables.validateConstructorParameters(ctor, args);
```

The snippet above illustrates the syntax and requires `Booking` to have a public `(String, int)` constructor along with Jakarta Validation/reflection imports. You can use the returned set to reject invalid requests **before** running any work inside the constructor.

### 3.2. `validateConstructorReturnValue` — Checking After `new`

General signature:

```java
<T> Set<ConstraintViolation<T>> validateConstructorReturnValue(
        Constructor<? extends T> constructor,
        T createdObject,
        Class<?>... groups);
```

`createdObject` must be an instance created by the corresponding constructor. Here "return value" means **the object produced by the constructor**, even though Java constructors do not declare a return type in source code.

A common pattern is placing `@Valid` on the constructor:

```java
public class Booking {

    @NotBlank
    private final String code;

    @Valid
    public Booking(String code) {
        this.code = code;
    }
}
```

When `executables.validateConstructorReturnValue(ctor, booking)` is called, the provider sees `@Valid` and cascades into constraints on `Booking.code`. If `@Valid` is removed from the constructor with no other return constraints, constructor return validation **does not automatically scan all properties**.

**Important limitation:** Because `createdObject` already exists, return validation cannot "prevent the constructor from running." If the constructor wrote files, sent network requests, or mutated shared state, a postcondition violation does not undo them. Keep constructors simple, avoid side effects, and validate parameters **before** instantiation whenever you control creation flow.

## 4. Standalone Runnable Java 17 Example: Seeing Every Phase Clearly

This complete example uses Java 17, Hibernate Validator 8.x, and Jakarta Validation. It demonstrates:

- Two constructor parameter constraints.
- Two constraints on instance fields.
- `@Valid` on the constructor to enable post-construction cascading.
- Plain bean validation for comparison.
- A method validated via the manual API, proving the same provider also supports method contracts.
- Plain Java `new` and method calls still executing despite metadata constraints.

Structure:

```text
constructor-validation-demo/
├── pom.xml
└── src/main/java/demo/
    └── ConstructorVsAopDemo.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-validation-demo</artifactId>
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

Hibernate Validator is the provider, pulling in the Jakarta Validation API transitively. `expressly` provides Jakarta Expression Language for message interpolation. This application **does not need Spring** to run.

### 4.2. `ConstructorVsAopDemo.java`

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

public class ConstructorVsAopDemo {

    public static final class Booking {

        @NotBlank(message = "state.code.required")
        private final String code;

        @Min(value = 1, message = "state.seats.too.small")
        private final int seats;

        // Only used to illustrate when the constructor runs.
        private static int constructions = 0;

        // @Valid belongs to the constructor return CONTRACT.
        @Valid
        public Booking(
                @NotBlank(message = "arg.code.required") String code,
                @Min(value = 1, message = "arg.seats.too.small")
                int seats) {
            constructions++;
            this.code = code;
            this.seats = seats;
        }

        public static int constructions() {
            return constructions;
        }
    }

    public static final class BookingService {

        @NotBlank(message = "method.result.blank")
        public String reserve(
                @NotBlank(message = "method.code.blank") String code) {
            return code;
        }
    }

    private static <T> void report(
            String label, Set<ConstraintViolation<T>> violations) {

        TreeSet<String> messages = new TreeSet<>();
        for (ConstraintViolation<T> v : violations) {
            messages.add(v.getMessage());
        }

        System.out.println(label + " -> " + messages);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            ExecutableValidator executable = validator.forExecutables();

            Constructor<Booking> constructor =
                    Booking.class.getConstructor(
                            String.class, int.class);

            Object[] invalidArgs = {"", 0};

            // PRE: does not run the constructor.
            report("ctor-params-invalid",
                    executable.validateConstructorParameters(
                            constructor, invalidArgs));

            System.out.println(
                    "constructions-before-new -> " +
                    Booking.constructions());

            // Plain Java new call still executes.
            Booking invalid = new Booking("", 0);
            System.out.println(
                    "constructions-after-new -> " +
                    Booking.constructions());

            // POST: cascades thanks to @Valid on the constructor.
            report("ctor-return-invalid",
                    executable.validateConstructorReturnValue(
                            constructor, invalid));

            // Compare with validation of the bean itself.
            report("bean-invalid",
                    validator.validate(invalid));

            Object[] validArgs = {"BOOK-1", 2};
            report("ctor-params-valid",
                    executable.validateConstructorParameters(
                            constructor, validArgs));

            Booking valid = new Booking("BOOK-1", 2);
            report("ctor-return-valid",
                    executable.validateConstructorReturnValue(
                            constructor, valid));

            BookingService service = new BookingService();
            Method method = BookingService.class.getMethod(
                    "reserve", String.class);

            report("method-params-invalid",
                    executable.validateParameters(
                            service, method, new Object[] {""}));

            report("method-return-invalid",
                    executable.validateReturnValue(
                            service, method, ""));

            // No proxy or interceptor, so it can still be called.
            System.out.println(
                    "direct-method-return-empty -> " +
                    service.reserve("").isEmpty());
        }
    }
}
```

Run in the `constructor-validation-demo` directory, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConstructorVsAopDemo
```

Lines printed to `stdout` (excluding Maven/provider logs if any):

```text
ctor-params-invalid -> [arg.code.required, arg.seats.too.small]
constructions-before-new -> 0
constructions-after-new -> 1
ctor-return-invalid -> [state.code.required, state.seats.too.small]
bean-invalid -> [state.code.required, state.seats.too.small]
ctor-params-valid -> []
ctor-return-valid -> []
method-params-invalid -> [method.code.blank]
method-return-invalid -> [method.result.blank]
direct-method-return-empty -> true
```

**Explanation:**

1. `validateConstructorParameters(...)` sees both blank `code` and `seats == 0`, returning two violations while `constructions` stays 0. The API does not instantiate the object.
2. `new Booking("", 0)` runs the constructor and increments the counter to 1, even though the same data violates the parameter contract. Nothing blocks `new` automatically.
3. `@Valid` on the constructor makes `validateConstructorReturnValue(...)` cascade into the new object and detect two invalid fields. This does not mutate the instance or roll back the counter.
4. `validator.validate(invalid)` also finds the two invalid fields, yet that is **independent bean validation**, not checking `@NotBlank`/`@Min` placed on constructor parameters.
5. Valid cases return zero violations. Because `report(...)` sorts messages with `TreeSet`, stdout order is deterministic.
6. For `BookingService`, the method validation API detects invalid parameter/return values when **called explicitly**. Still, calling `service.reserve("")` returns an empty string because the program has no Spring proxy.

The example uses empty data for illustration. In real applications, do not instantiate invalid objects **after** `validateConstructorParameters` has already failed; stop at the precondition step.

## 5. Implementing a Factory That Validates Constructors in the Right Order

To turn the contract into a real guard, wrap both validation calls around instantiation. This is **additional illustrative code** using `Booking` from section 4, suitable for a dedicated factory class in an application:

```java
public final class BookingFactory {

    private final ExecutableValidator executable;

    public BookingFactory(Validator validator) {
        this.executable = validator.forExecutables();
    }

    public Booking create(String code, int seats)
            throws NoSuchMethodException {

        Constructor<Booking> constructor =
                Booking.class.getConstructor(String.class, int.class);
        Object[] inputs = {code, seats};

        var inputErrors =
                executable.validateConstructorParameters(
                        constructor, inputs);

        if (!inputErrors.isEmpty()) {
            throw new ConstraintViolationException(inputErrors);
        }

        // Only runs after precondition is valid.
        Booking result = new Booking(code, seats);

        var resultErrors =
                executable.validateConstructorReturnValue(
                        constructor, result);

        if (!resultErrors.isEmpty()) {
            throw new ConstraintViolationException(resultErrors);
        }

        return result;
    }
}
```

To compile this in its own file, import `jakarta.validation.Validator`, `ConstraintViolationException`, `jakarta.validation.executable.ExecutableValidator`, `java.lang.reflect.Constructor`, and qualify `ConstructorVsAopDemo.Booking` for `Booking`. This class is not auto-generated by Spring; the application must explicitly use the factory instead of scattered `new` calls.

Important design decisions:
- **Use one actual argument array.** If you validate `inputs` and then modify values before invoking the constructor, the preflight check no longer protects that call.
- If the constructor has side effects, postcondition validation only reports errors **after the side effects happen**. Avoid writing to a DB or publishing events inside constructors; perform side effects only after both phases pass, or use proper transactions/compensation.
- You can keep `ValidatorFactory` as a Spring-managed singleton and share `Validator`/`ExecutableValidator`, as the APIs are designed for reuse. Avoid building a new factory on every request.
- The application layer can convert violations into exceptions or structured error lists. Merely **calling the API** does not throw an exception by itself.

## 6. What Does Spring AOP Method Validation Actually Intercept?

### 6.1. A `@Validated` Service

In a Spring Boot 3.x application configured with Jakarta Validation and AOP, dependencies typically look like:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

This is an illustrative `build.gradle` snippet inside a Spring Boot project that already has plugins and repositories; it does not run standalone like section 4's `pom.xml`.

A bean:

```java
@Service
@Validated
public class BookingService {

    @NotNull
    public Booking book(
            @NotBlank String code,
            @Min(1) int seats) {
        return new Booking(code, seats);
    }
}
```

Assume `Booking` is the class from section 4 and Spring/Jakarta imports are present. `MethodValidationPostProcessor` sets up an interceptor for Spring beans annotated with `@Validated`. When another bean obtains the **proxy** and calls `bookingService.book("", 0)`, the interceptor validates the parameters of **method `book`** before the method body runs, and afterward validates constraints on the **method return value**.

Important detail: the interceptor validates the **method contract** received by the Spring proxy, rather than calling `validateConstructorParameters` for `new Booking(code, seats)` inside. In the snippet above, we placed `@NotBlank`/`@Min` right on **method parameters**, so the proxy catches violations **before** running the body that constructs the object.

If you change the method to:

```java
public Booking book(String code, int seats) {
    return new Booking(code, seats);
}
```

and leave `@NotBlank`/`@Min` only on `Booking`'s **constructor**, Spring AOP does not know to validate constructor arguments; `new Booking("", 0)` inside still executes.

### 6.2. Why Can't Proxies Replace Constructor Interception?

Spring AOP supports **method-execution join points**. It can use JDK dynamic proxies on interfaces or CGLIB subclass proxies depending on the target bean; both revolve around invoking methods through a proxy. Construction is **object instantiation**, not a method invocation through a proxy of an existing instance.

Therefore:
- `@Validated` on a class marks it for Spring method validation; it does not turn constructors into methods.
- `@Valid` on a constructor takes effect only when an API/integration validating constructor returns is called.
- Even with CGLIB subclass proxies, **do not infer** that Spring AOP advice will automatically validate constructor arguments.
- Direct `new` calls, factories calling `new`, and Spring creating beans via constructor injection are **not automatically** checked against constructor contracts by `MethodValidationPostProcessor`.
- `@PostConstruct` and lifecycle callbacks do not turn into constructor prevalidation. Post-creation bean validation (if separate infrastructure exists) is still not *constructor parameter validation before `new`*.

If a project uses **AspectJ weaving** with constructor join points, or **CDI/Jakarta EE** executable validation integration, those are distinct mechanisms covering additional contexts. Do not extrapolate their capabilities to standard Spring AOP proxies.

### 6.3. Proxy Limitations That Cause Missed Method Validation

Even for **methods**, keep in mind:
- The bean must be Spring-managed and calls must **go through the proxy**.
- `this.book(...)` inside the target bean itself generally bypasses the proxy (*self-invocation*).
- With JDK dynamic proxies, calls go through the interface; with CGLIB, `final`/`private` methods cannot be overridden/advised like compatible public methods.
- Validation groups may be chosen by `@Validated(Group.class)`. Having `@Valid` alone does not mean all groups run.
- Placing constraints on a method declaration while instantiating `new SomeService()` outside the container yields no interceptor.

Tests must invoke from another bean through the real container to prove Spring enforces method contracts.

## 7. Can You Replace Constructor APIs with a Proxied Factory Method?

You can design a **public factory method** so Spring validates the *method's contract* before and after constructing the object. Illustrative example:

```java
@Service
@Validated
public class BookingFactoryService {

    @Valid // Cascades into properties of the returned Booking.
    public Booking create(
            @NotBlank String code,
            @Min(1) int seats) {

        return new Booking(code, seats);
    }
}
```

When another bean calls `create(...)` through the proxy:
1. The interceptor validates **method parameters** (`code` and `seats`) before entering the body.
2. If valid, the body runs the constructor.
3. When the method returns, `@Valid` on the **method** enables cascading to validate the returned object.

This protects a **controlled creation path**, yet important differences remain:
- Input checks come from **annotations on the factory method**, not automatically inherited from constructor parameter annotations.
- Cascaded return is part of the **factory method's contract**, not an invocation of `validateConstructorReturnValue`.
- Any object creation outside the factory bypasses this mechanism.
- The constructor already ran before the provider checks the method return, so constructor side effects can still occur.
- Without `@Valid` on the method return, the proxy does not scan `Booking`'s fields merely because fields carry constraints.

If the requirement is **enforcing annotations declared directly on constructors** without duplicating contracts onto methods, use `ExecutableValidator` or an integration that explicitly validates constructor signatures.

## 8. Spring Constructor Injection Is Not Constructor Validation

In Spring, "constructor injection" and "constructor validation" are easily conflated:

```java
@Service
public class PaymentService {

    private final GatewayClient gateway;

    public PaymentService(GatewayClient gateway) {
        this.gateway = gateway;
    }
}
```

Spring IoC **resolves the `GatewayClient` dependency**, invokes the constructor, and manages the bean lifecycle. That is **dependency injection**, not calling `ExecutableValidator.validateConstructorParameters`.

If you add:

```java
public PaymentService(@NotNull GatewayClient gateway) {
    this.gateway = gateway;
}
```

`@NotNull` is Jakarta Validation metadata on the parameter. It does not make standard Spring AOP proxies intercept the constructor. Spring may fail during bean creation if it **cannot resolve the dependency** or if the constructor throws; that differs from `@NotNull` being evaluated by a validation provider.

Similarly, Spring Boot's `@ConfigurationProperties` can be bound and validated via a separate mechanism (depending on version/configuration). Do not treat configuration property validation or `@Valid` on DTOs as proof that every custom constructor in the application is checked automatically.

## 9. Differences from `Validator.validate(bean)` and Bean Lifecycle Validation

Suppose `Booking` has:
- `@NotBlank` on constructor parameter `code` with message `arg.code.required`.
- `@NotBlank` on field `code` with message `state.code.required`.
- `@Valid` on the constructor to cascade into the instance.

Outcome of each call:

| Call | Validation scope |
| --- | --- |
| `validator.validate(booking)` | Field/getter/class constraints on **booking** |
| `executables.validateConstructorParameters(ctor, args)` | Parameter and cross-parameter constraints of **ctor** |
| `executables.validateConstructorReturnValue(ctor, booking)` | Constraints/cascades on **constructor return**, potentially reaching fields |
| `executables.validateParameters(service, method, args)` | Parameters of a specific method |
| `executables.validateReturnValue(service, method, result)` | Constraints/cascades on the return of a specific method |
| Spring AOP method validation | Conceptually equivalent to method checks, executed on calls through proxy |

`Validator.validate(bean)` never receives the argument array used before construction and cannot validate **constructor parameter** contracts solely from current object state. Two different inputs might produce identical state; conversely, a constructor might transform input into a different state. That is why both metadata layers exist separately.

Some applications use `BeanValidationPostProcessor`, a custom `BeanPostProcessor`, or init hooks to verify *bean state after Spring instantiates the object*. Even so, those steps happen **after the constructor**, not as default interceptors for constructor arguments. Never use them to promise an invalid constructor will have no side effects.

## 10. When Is Constructor Return Validation Needed?

If a constructor simply stores already-validated arguments verbatim, constructor parameter validation is sufficient in many situations. Constructor return validation still adds value when:

- Invariants span the **complete object**, such as multiple interrelated fields.
- The constructor transforms, normalizes, or chooses default values and risks producing invalid state.
- A class-level constraint validates relationships across properties.
- Child object state must be validated through cascades declared on the object.
- A factory needs to enforce **preconditions and postconditions** as two independent contracts.

Example of a class-level constraint (conceptual snippet, not a full annotation):

```java
@ConsistentBooking
public class Booking {
    // code, startDate, endDate, ...
}
```

With the constructor marked `@Valid`, `validateConstructorReturnValue` can cascade and evaluate `@ConsistentBooking` on the object after construction. `@ConsistentBooking` here is assumed to be a custom constraint with a matching `ConstraintValidator`.

**Design best practice:** Keep constructors side-effect free (especially for immutable objects/records). When a postcondition fails, you can discard the object without having to undo I/O.

## 11. Cross-Parameter Constraints and Groups in Constructor Validation

A constructor can have constraints **across multiple parameters** that cannot be expressed with `@NotNull` on each parameter individually. For instance, a constructor accepting `start` and `end` requiring `start <= end`.

Illustrative annotation:

```java
@ValidDateRange
public Schedule(LocalDate start, LocalDate end) {
    // ...
}
```

`@ValidDateRange` is assumed to be a custom cross-parameter constraint, whose validator accepts `Object[]` and is annotated:

```java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, Object[]> {

    @Override
    public boolean isValid(
            Object[] args, ConstraintValidatorContext ctx) {
        if (args == null || args.length != 2) {
            return false;
        }

        LocalDate start = (LocalDate) args[0];
        LocalDate end = (LocalDate) args[1];
        return start == null || end == null || !start.isAfter(end);
    }
}
```

These illustrative snippets are **incomplete for standalone compilation**: you need `@ValidDateRange` declared with constructor target plus imports for `java.time.LocalDate`, `jakarta.validation.*`, and `jakarta.validation.constraintvalidation.*`. When `validateConstructorParameters` is called, the provider evaluates these valid cross-parameter constraints as well.

Both constructor APIs accept `groups`. Example:

```java
public interface StrictCheck {}

public Schedule(
        @NotNull LocalDate start,
        @Future(groups = StrictCheck.class) LocalDate end) {
    // ...
}
```

By default, `validateConstructorParameters(ctor, args)` checks the `Default` group. To run constraints in `StrictCheck`, pass `StrictCheck.class`. To check both:

```java
executables.validateConstructorParameters(
        ctor, args,
        jakarta.validation.groups.Default.class,
        StrictCheck.class);
```

These snippets only illustrate group selection. Do not confuse `@Validated(StrictCheck.class)` on a Spring bean with the `groups` varargs on constructor APIs: the former belongs to Spring method validation, while the latter is chosen by the **caller of the constructor API**.

## 12. Reflection, Records, and Constructor Overloads

### 12.1. Getting the Exact Signature

`getConstructor` looks up a **public constructor** with the exact parameter type list:

```java
Constructor<Booking> ctor =
        Booking.class.getConstructor(String.class, int.class);
```

If a class has both `Booking(String, int)` and `Booking(String, long)`, those are two distinct constructors. The `Object[]` passed must match the chosen constructor's count, order, and types. For `int`, the element in the array is a boxed `Integer`.

For a no-argument constructor, pass `new Object[0]`. **Never** pass `null` instead of an empty array: that is an invalid API argument. An element inside the array may be `null` if its type allows it; `@NotNull` will catch that case.

### 12.2. Constructor Visibility

If a constructor is non-public, `Class.getDeclaredConstructor(...)` returns its reflection descriptor. **Invoking** the constructor via reflection may require appropriate access rights. However, `validateConstructorParameters` only needs the descriptor and does not have to invoke the constructor via `newInstance`; calling regular `new` after preflight is valid wherever source code has access.

### 12.3. Java Records

Example with a record:

```java
public record Account(
        @NotBlank String code,
        @Min(1) int level) {}
```

Constraints declared on record components can be propagated by Java to corresponding elements (fields, accessors, or canonical constructor parameters depending on each annotation's `@Target`). For `@NotBlank` and `@Min`, metadata on the canonical constructor's parameters can be populated accordingly. **Do not assume**, however, that `new Account("", 0)` runs Bean Validation automatically; record construction still requires an integration if you want to block invalid inputs.

Test the exact bytecode/metadata of record types and compiler/provider versions when depending on annotation propagation. For mandatory domain invariants on a record, a compact constructor with `if`/`throw` is **direct Java logic** executed upon creation, distinct from annotations evaluated by a Jakarta Validation provider.

## 13. APIs Do Not Throw Validation Exceptions Themselves

A valid violation is reported via a `ConstraintViolation` set:

```java
var problems =
        executables.validateConstructorParameters(
                constructor, new Object[] {"", 0});

if (!problems.isEmpty()) {
    throw new ConstraintViolationException(problems);
}
```

This is a supplement to section 4; import `jakarta.validation.ConstraintViolationException`. Throwing is the **caller's decision**, not automatic behavior of `validateConstructorParameters`.

| Case | What can happen |
| --- | --- |
| Arguments violate `@NotBlank`/`@Min` | API returns a non-empty `Set<ConstraintViolation<?>>` |
| Caller throws manually when `Set` is non-empty | `ConstraintViolationException` |
| `constructor` or `createdObject` mismatch; wrong argument types/count | `IllegalArgumentException` |
| Misconfigured constraint/provider | `ValidationException` or specific subtype |
| Call via Spring method validation proxy fails | `ConstraintViolationException` or adapted exception, per configuration |
| Spring lacks dependency bean during constructor injection | Spring bean creation failure, **not** necessarily a Jakarta Validation violation |

Each `ConstraintViolation` contains a path, message, invalid value, and constraint descriptor. For constructors, the property path starts with a `CONSTRUCTOR` node; parameter errors pass through a `PARAMETER` node, and postcondition errors pass through `RETURN_VALUE` and then potentially `PROPERTY` via cascading. `getRootBean()` on a constructor violation is `null` per specification; `getRootBeanClass()` is the class declaring the constructor. This differs from validating a method on an existing object.

Do not depend on iteration order in the `Set`. If stable API error output is needed, sort by path/message; never automatically return `getInvalidValue()` in HTTP responses because it can contain private data.

## 14. Self-Check: Choosing the Technique for Each Scenario

| Requirement | Appropriate approach | Reason |
| --- | --- | --- |
| Reject bad arguments **before** instantiating an object via a constrained constructor | `ExecutableValidator.validateConstructorParameters` in a controlled factory | Inspects exact constructor metadata and can abort before `new` |
| Check object invariants **after** construction using constructor metadata | `validateConstructorReturnValue`, typically with `@Valid` | Has `createdObject` for cascading/state checks |
| Check current state of any existing bean | `Validator.validate(bean)` | Does not need to know which arguments called the constructor |
| Enforce input/output on a public Spring service method | `@Validated` and method validation proxy | Interceptor wraps method invocations |
| Reject input to a Spring factory method before its body runs | Constraints directly on method parameters + proxy | Method contract is validated before `new` inside the body |
| Validate a DTO received via HTTP in Spring MVC | `@Valid`/`@Validated` on controller argument and proper provider | Request binding/validation, distinct from constructor interception |
| Automatically intercept **every** constructor of arbitrary Java objects | Outside Spring AOP proxy scope; requires different design/integration | Spring AOP has no constructor join points |
| Validate **both methods and constructors** in a custom framework | Use the corresponding `ExecutableValidator` methods | Standard API provides both executable types |

Notably, a single Spring Boot application can simultaneously contain:
- Beans created via constructor injection.
- Services validated with `@Validated` method validation.
- DTOs validated during HTTP binding.
- Objects instantiated with `new` inside services.

These four paths **do not mean** every constructor argument is checked by a single universal validator. Clearly identify **which boundary** is responsible for guarding each invariant.

## 15. Common Mistakes and Fixes

1. **Placing `@NotBlank` on a constructor and assuming Spring `@Validated` catches it at bean creation.** Spring AOP proxies only wrap method invocations. To enforce constructor metadata, use standard APIs in a factory or a specialized integration.
2. **Calling only `Validator.validate(createdObject)` and assuming constructor parameters were checked.** Bean validation only sees current state, not the initial argument array. Use `validateConstructorParameters` if the constructor parameter contract matters.
3. **Calling `validateConstructorReturnValue` before `new`.** The API requires an already-created `createdObject`; the right sequence is preflight → new → post-check.
4. **Putting `@Valid` on a constructor without calling any API.** Metadata does not block Java constructors automatically. Explicit validation or integration is required.
5. **Using a proxied factory method while putting constraints only on the constructor.** Method interceptors do not automatically copy metadata from constructors to methods. Declare the factory method's contract or call constructor APIs explicitly.
6. **Using a factory method with return `@Valid` and expecting constructor rollback.** Return validation runs after the body; it cannot undo side effects that already occurred.
7. **Relying on self-invocation on a `@Validated` bean.** `this.someMethod(...)` can bypass the proxy. Call through the Spring bean proxy from another bean or restructure call paths.
8. **Fetching the wrong `Method`/`Constructor` reflection signature for overloads.** Primitive vs. wrapper mismatches or wrong order cause mismatches. Use exact signatures and test them.
9. **Assuming Spring Boot always throws `ConstraintViolationException` for every validation type.** MVC has its own error types; `MethodValidationPostProcessor` also has an adaptation mode. Verify the execution branch and configuration.
10. **Using the same constraint and accidentally validating twice.** If a factory method is already proxy-validated, calling `ExecutableValidator.validateParameters` on the same method wastes work and can duplicate errors. Choose one intentional enforcement point.

## 16. Practice Exercises

1. In section 4, remove `@Valid` from `Booking`'s constructor and re-run `validateConstructorReturnValue` and `validator.validate(invalid)`. Why do the results differ?
2. Replace `new Booking("", 0)` with a factory that checks `validateConstructorParameters` first. Print the counter again and prove the constructor never runs on the invalid-input branch.
3. Modify the constructor into a buggy version: valid input yet stores `seats = 0`. Prove parameter validation passes while return validation catches the invalid state.
4. Create a Spring `@Service @Validated` with method `book(@NotBlank String, @Min(1) int)` and invoke it from another bean through the proxy. Then move constraints solely onto `Booking`'s constructor and verify the difference.
5. Write a test for a record with component constraints; inspect `getConstraintsForConstructor(...)` and try calling `validateConstructorParameters` with invalid values before `new`.
6. Explain why a bean created via Spring constructor injection is Spring-managed yet does not prove `ExecutableValidator.validateConstructorParameters` ever ran.
7. Extend the factory to map violations into exceptions or error objects containing `path`, `message`, and `code`, without exposing raw `getInvalidValue()`.

**Takeaway:** Jakarta Validation **defines** constraints and provides `ExecutableValidator` for explicitly validating constructors. Spring AOP **automatically enforces** method contracts on calls through proxies. To enforce constructor contracts, you must place a validation step in the right spot—before calling the constructor, or after object creation depending on the contract—and control instantiation paths yourself.

## Standard References

- [Jakarta Validation 3.1 Specification — Method and constructor constraints](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Jakarta Validation 3.1 Specification — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#validationapi-triggeringmethodvalidation)
- [Jakarta Validation API — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta.validation/jakarta/validation/executable/ExecutableValidator.html)
- [Hibernate Validator 8 — Method and constructor constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-method-constraints)
- [Spring Framework — AOP proxying mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Spring-driven method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation of handler methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)