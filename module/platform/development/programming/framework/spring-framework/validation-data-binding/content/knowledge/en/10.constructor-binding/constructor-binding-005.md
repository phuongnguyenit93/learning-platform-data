# Constructor Selection and Parameter Name Metadata in Spring Constructor Binding

## 1. Goal

**Constructor binding** is the mechanism by which Spring creates an input object by selecting a constructor, looking up source values by **parameter name**, converting types, and then invoking the constructor. This mechanism is very useful for request DTOs, immutable form objects, and Java records.

Example submitted input:

```text
attendee=Lan
seats=2
```

Target object:

```java
public record BookingForm(String attendee, int seats) {}
```

Spring must resolve three separate questions: **which constructor**, **what each parameter is named**, and **how input strings convert to parameter types**. If it selects the right constructor but cannot recognize the names `attendee` and `seats`, the framework still lacks enough information to match the data.

Two other mechanisms are often confused with this topic:

- **Dependency injection:** Spring creates `@Service` and `@Component` beans from dependencies via constructors (often involving `@Autowired`). The data source is the container, not HTTP input.
- **JSON deserialization:** `@RequestBody` typically uses Jackson, which has its own constructor/creator selection rules and annotations like `@JsonCreator` and `@JsonProperty`. Do not apply those rules by default to `@ModelAttribute`.
- **Constructor data binding:** `DataBinder.construct(...)` or MVC's `@ModelAttribute` mechanism reads values from requests or a `ValueResolver`, rather than pulling services from the IoC container.

The practical goal is to choose one clear data constructor, preserve parameter names in bytecode, use `@ConstructorProperties` or `@BindParam` when source names differ from Java names, and recognize common pitfalls from overloads or unintended setter binding.

## 2. Processing Flow: Select Constructor First, Resolve Names Next

```text
HTTP form / ValueResolver source:
    attendee="Lan"
    seats="2"
          |
          v
DataBinder determines target type
          |
          v
Select valid constructor
    (String attendee, int seats)
          |
          v
Read each parameter name
    ["attendee", "seats"]
          |
          v
Look up values by name
    "Lan", "2"
          |
          v
ConversionService / PropertyEditor
    String "2" -> int 2
          |
          v
new BookingForm("Lan", 2)
          |
          v
BindingResult: errors if binding fails
          |
          v
Validator (if triggered)
          |
          v
Controller / use case
```

Key point: property names accepted through a constructor **do not have to match** class fields or setters. Spring needs metadata about **constructor parameters**. Conversely, property binding uses property names/paths and setters or field access mechanisms.

| Question | Constructor binding | Property binding |
| --- | --- | --- |
| Does the object already exist? | Usually not; needs to be created | Already exists |
| Where values are assigned | Constructor arguments | Setters / fields |
| Names looked up | Parameter names or mapped names | Property names |
| Suitable classes | Records, immutable DTOs, data constructors | JavaBeans with setters |
| Sources of error | Constructor selection, parameter names, conversion | Setter/property paths, conversion |
| Input safety | Good when only permitted input parameters are declared | Should restrict `allowedFields` |

In Spring MVC, by default the framework can perform **both constructor binding and property binding**. Therefore, merely defining a constructor does not disable all setters outside the constructor. To restrict setter binding, see section 9 on `declarativeBinding`.

## 3. Constructor Selection Rules

### 3.1. Single Parameterized Constructor: The Preferred Case

```java
public final class CreateOrderForm {
    private final String customer;
    private final int quantity;

    public CreateOrderForm(String customer, int quantity) {
        this.customer = customer;
        this.quantity = quantity;
    }

    public String getCustomer() { return customer; }
    public int getQuantity() { return quantity; }
}
```

When a class has **one public data constructor**, Spring has an unambiguous target for constructor binding. The infrastructure can also accept a **single non-public parameterized constructor** if reflection/access allows. However, for API clarity and to avoid Java module/native-image complications, typical web DTOs should have one clear public data constructor.

Unlike setter binding, a no-arg constructor is not required. Fields can be `final`, with no setters.

### 3.2. Multiple Constructors and the Default Constructor

```java
public class OrderForm {
    private String customer;

    public OrderForm() {}

    public OrderForm(String customer) {
        this.customer = customer;
    }

    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }
}
```

If there are **multiple constructors**, Spring constructor resolution may select the **default/no-args constructor** if one exists. Consequences:

- The object may be created via the empty constructor.
- If property binding remains allowed, setters may populate `customer`.
- If configured for **constructor binding only** with no property binding, `customer` may remain `null`.

Do not assume "the constructor with the most parameters wins." Having multiple parameterized constructors without a clear primary/single/default choice leads to ambiguity or errors. Using a record or a DTO with a single data constructor yields far fewer surprises.

### 3.3. Java Records and the Canonical Constructor

```java
public record OrderForm(String customer, int quantity) {}
```

A record declares components `customer` and `quantity` along with its corresponding **canonical constructor**. Spring can use this constructor for input data; no setters are needed. Records may have secondary constructors or compact constructors, yet the cleanest DTO design remains one clear canonical contract.

For Kotlin data classes, Spring also supports the primary constructor; pay attention to Kotlin metadata, reflection, and library version configuration. Do not mechanically apply JavaBean getter/setter rules to records or Kotlin data classes.

### 3.4. Distinguishing DI Bean Constructors

```java
// Illustrative snippet for dependency injection, not a complete class.
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

This constructor receives an `OrderRepository` supplied by the Spring container. It does **not** bind a request parameter `repository=...` like `DataBinder.construct(...)`. `@Autowired`/constructor injection rules and data constructor rules belong to two different contexts.

## 4. Why Are Constructor Parameter Names Important?

The following Java code clearly shows parameter names in source:

```java
public CreateOrderForm(String customer, int quantity) {
    // ...
}
```

However, the JVM does not necessarily preserve those names in the bytecode of **regular Java classes**. If only the types `String`, `int` and parameter positions remain, Spring cannot tell which parameter matches the request key `customer` without reliable name metadata.

Java Reflection provides:

- `Constructor.getParameters()`: the array of `Parameter` objects.
- `Parameter.getName()`: the name visible to reflection.
- `Parameter.isNamePresent()`: whether real names were stored in metadata.

Without metadata, reflection may return synthetic names like `arg0`, `arg1`, and `isNamePresent() == false`. These are **not** meaningful input contracts. Never ask clients to send a field named `arg0` to "fix" missing names.

## 5. Preserving Parameter Names with -parameters

With `javac`:

```bash
javac -parameters CreateOrderForm.java
```

When using Maven and Java 17, you can configure the compiler plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

This is only a **Maven plugin snippet**, which must be placed inside `project/build/plugins` in an actual POM.

Code to inspect metadata:

```java
// Snippet; requires importing java.lang.reflect.Constructor, Parameter
Constructor<?> c = CreateOrderForm.class.getDeclaredConstructors()[0];
for (Parameter p : c.getParameters()) {
    System.out.println(p.getName() + ": " + p.isNamePresent());
}
```

With bytecode compiled using `-parameters`, expected output is:

```text
customer: true
quantity: true
```

**Notes:**

- Enable the option on **the module that actually compiles the DTO**, not only the module running Spring MVC. If the DTO lives in a separately built JAR, recompile that JAR.
- `-g` (debug info) is not a reliable substitute for `-parameters` in modern Spring.
- IDEs may run bytecode that differs from the packaged artifact; inspect Maven/Gradle configuration and run `mvn clean compile` rather than only reading source.
- `javap -v` lets you inspect the `MethodParameters` attribute when diagnosing issues.
- Records preserve canonical component names per record specifications, yet enabling the option codebase-wide remains helpful for regular classes.

## 6. @ConstructorProperties: Logical Names Differing from Java Variable Names

The JDK provides `java.beans.ConstructorProperties`. Spring's `BeanUtils.getParameterNames(Constructor<?>)` checks this annotation when present:

```java
import java.beans.ConstructorProperties;

public final class LegacyOrderForm {
    private final String customer;
    private final int quantity;

    @ConstructorProperties({"customer", "quantity"})
    public LegacyOrderForm(String buyer, int count) {
        this.customer = buyer;
        this.quantity = count;
    }

    public String getCustomer() { return customer; }
    public int getQuantity() { return quantity; }
}
```

The variable names in Java source are `buyer` and `count`, while the annotation declares logical names `customer` and `quantity` for the constructor arguments **in order**. If the input map has those two keys, Spring can match values accurately even when Java parameter names differ.

Important conditions:

1. The number of names in the annotation must equal the number of constructor parameters.
2. The order of names must match the order of parameters.
3. Names form a data contract; renaming or reordering without updating requests/tests can break binding.
4. This annotation provides no validation, conversion, authentication, or authorization.
5. In a class with multiple constructors, adding a naming annotation **does not mean** the framework will definitely pick the constructor you want; constructor resolution rules still apply.

For example, having two parameters `(String buyer, int count)` while declaring `{"quantity", "customer"}` has the wrong order: Spring may try converting an email/name into a number or assign wrong data.

## 7. @BindParam and DataBinder.NameResolver in Spring MVC

When external input names differ from Java conventions, for example:

```text
attendee-name=Lan
quantity=2
```

Spring MVC and WebFlux support `@BindParam` to map the request parameter name:

```java
import org.springframework.web.bind.annotation.BindParam;

public record BookingForm(
        @BindParam("attendee-name") String attendeeName,
        int quantity) {}
```

For a model attribute, key `attendee-name` maps to the Java constructor parameter `attendeeName`. `@BindParam` can be placed on the constructor parameter or corresponding field per framework rules.

**Important limitation:** `@BindParam` is constructor-binding name mapping in Spring MVC/WebFlux. When creating a plain standalone `DataBinder` outside the web layer, do not assume the annotation will automatically work just like MVC. `DataBinder` lets you install a custom `NameResolver` when needed:

```java
// Illustrative snippet; binder is an already-created DataBinder.
binder.setNameResolver(parameter -> {
    // Can inspect annotations on MethodParameter.
    // Return null so Spring continues using the default name lookup.
    return null;
});
```

Here the lambda only illustrates the resolver signature without transforming any names. A real resolver needs clear renaming rules, collision handling, and nested path behavior.

| Need | Common solution |
| --- | --- |
| Java record whose component names match input | Canonical constructor |
| Regular class whose Java names match input | `-parameters` |
| Constructor from legacy code with different Java names | `@ConstructorProperties` when appropriate |
| HTTP form uses `first-name` while Java uses `firstName` | `@BindParam("first-name")` in MVC |
| Custom standalone binder with custom naming conventions | `DataBinder.NameResolver` |
| JSON `@RequestBody` needing custom creator/property names | Configure Jackson, do not substitute `@BindParam` |

Carefully distinguish **parameter names used for binding** from database column names, JSON property names, and Java variable names during debugging.

## 8. Runnable Example: Spring DataBinder.construct and Constructor Metadata

The following example uses **Java 17**, **Spring Framework 6.2.6**, and Maven, without needing a web server or database. It demonstrates a record, a class with `@ConstructorProperties`, and a class with two constructors in one program.

### 8.1. Structure

```text
constructor-binding-demo/
├── pom.xml
└── src/main/java/demo/ConstructorBindingDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>constructor-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConstructorBindingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. src/main/java/demo/ConstructorBindingDemo.java

```java
package demo;

import java.beans.ConstructorProperties;
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.BeanUtils;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ConstructorBindingDemo {

    public record MemberRequest(String name, int seats) {
    }

    public static final class LegacyRequest {
        private final String email;
        private final int seats;

        @ConstructorProperties({"contact-email", "seats"})
        public LegacyRequest(String email, int seats) {
            this.email = email;
            this.seats = seats;
        }

        public String getEmail() {
            return email;
        }

        public int getSeats() {
            return seats;
        }
    }

    public static final class HybridRequest {
        public HybridRequest() {
        }

        public HybridRequest(String name) {
        }
    }

    private static <T> T construct(
            Class<T> targetType, Map<String, String> values) {

        DataBinder binder = new DataBinder(null, "request");
        binder.setTargetType(ResolvableType.forClass(targetType));
        binder.setDeclarativeBinding(true);

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return values.get(name);
            }

            @Override
            public Set<String> getNames() {
                return values.keySet();
            }
        });

        BindingResult result = binder.getBindingResult();
        if (result.hasErrors() || binder.getTarget() == null) {
            throw new IllegalStateException(
                    "Cannot construct " + targetType.getSimpleName());
        }

        return targetType.cast(binder.getTarget());
    }

    private static String[] reflectionNames(Constructor<?> constructor) {
        return Arrays.stream(constructor.getParameters())
                .map(Parameter::getName)
                .toArray(String[]::new);
    }

    public static void main(String[] args) {
        Constructor<?> recordCtor =
                BeanUtils.getResolvableConstructor(MemberRequest.class);
        System.out.println("record.parameters=" +
                recordCtor.getParameterCount());
        System.out.println("record.names=" +
                Arrays.toString(BeanUtils.getParameterNames(recordCtor)));

        MemberRequest member = construct(
                MemberRequest.class,
                Map.of("name", "Lan", "seats", "3"));

        System.out.println("member.name=" + member.name());
        System.out.println("member.seats=" + member.seats());

        Constructor<?> legacyCtor =
                BeanUtils.getResolvableConstructor(LegacyRequest.class);
        System.out.println("legacy.reflect.names=" +
                Arrays.toString(reflectionNames(legacyCtor)));
        System.out.println("legacy.spring.names=" +
                Arrays.toString(BeanUtils.getParameterNames(legacyCtor)));
        System.out.println("legacy.namesPresent=" +
                legacyCtor.getParameters()[0].isNamePresent());

        LegacyRequest legacy = construct(
                LegacyRequest.class,
                Map.of("contact-email", "lan@example.com", "seats", "2"));

        System.out.println("legacy.email=" + legacy.getEmail());
        System.out.println("legacy.seats=" + legacy.getSeats());

        Constructor<?> hybridCtor =
                BeanUtils.getResolvableConstructor(HybridRequest.class);
        System.out.println("hybrid.parameters=" +
                hybridCtor.getParameterCount());
    }
}
```

This code uses `DataBinder.ValueResolver`, with its two methods in Spring 6.2:

- `resolveValue(String name, Class<?> type)` retrieves a value from the source. Here it returns strings from the `Map`.
- `getNames()` returns the list of source keys so the binder can recognize structure, especially when nested paths exist.

`setTargetType(...)` specifies the class to create because `DataBinder(null, ...)` has no target yet. `construct(...)` picks the constructor, matches parameter names, and converts strings like `"3"` to `int 3`. Afterward `getBindingResult()` tells whether binding errors occurred. Setting `setDeclarativeBinding(true)` does not stop constructor binding; this flag helps if a property binding step follows in MVC.

### 8.4. Running

In `constructor-binding-demo`, with JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

**Expected program stdout:**

```text
record.parameters=2
record.names=[name, seats]
member.name=Lan
member.seats=3
legacy.reflect.names=[email, seats]
legacy.spring.names=[contact-email, seats]
legacy.namesPresent=true
legacy.email=lan@example.com
legacy.seats=2
hybrid.parameters=0
```

Explanation:

1. `MemberRequest` is a record with a canonical constructor taking two parameters `name` and `seats`.
2. `LegacyRequest` is compiled with `-parameters`, so Java reflection sees `email` and `seats`; however `BeanUtils.getParameterNames` prioritizes `@ConstructorProperties({"contact-email", "seats"})`.
3. The input map uses `contact-email` instead of `email`. `getEmail()` still returns the proper internal value.
4. `HybridRequest` has two public constructors, including a no-args constructor. `getResolvableConstructor` selects the no-args constructor.
5. Spring converts the seat count from string to `int`; user code never calls `Integer.parseInt` in the program.

The stdout above is derived from the code and API rules; verify when running directly. This article does not claim to have compiled or run tests in a project environment.

### 8.5. If Type Conversion Fails

Try replacing the `MemberRequest` map with:

```java
Map.of("name", "Lan", "seats", "abc")
```

This is only a value-replacement snippet within the program. `"abc"` is not an integer, so the binder records a conversion error, typically with base code `typeMismatch`. The illustrative `construct` helper sees `result.hasErrors()` and throws `IllegalStateException`. Once the input is changed to an error case, **the valid stdout in section 8.4 no longer applies**.

In real applications, return input errors to users via `BindingResult` or an exception handler rather than exposing internal stack traces.

## 9. Integrating with Spring MVC @ModelAttribute

Spring MVC pulls values from form/query/path/header sources via `@ModelAttribute`, instantiates objects via constructors when appropriate, and can then continue with property binding.

The example below is a **controller snippet**, not a standalone class:

```java
// Needs Spring MVC, a Bean Validation provider, and corresponding imports.
public record BookingForm(
        @BindParam("attendee-name")
        @jakarta.validation.constraints.NotBlank String attendeeName,
        @jakarta.validation.constraints.Min(1) int seats) {
}

@PostMapping(path = "/bookings",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<?> create(
        @Valid @ModelAttribute("bookingForm") BookingForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid booking form"));
    }

    return ResponseEntity.ok(Map.of(
            "attendee", form.attendeeName(),
            "seats", form.seats()));
}
```

Illustrative request structure:

```http
POST /bookings HTTP/1.1
Content-Type: application/x-www-form-urlencoded

attendee-name=Lan&seats=2
```

For valid data, logical JSON body:

```json
{"attendee":"Lan","seats":2}
```

`@BindParam("attendee-name")` bridges the difference between input name `attendee-name` and Java parameter `attendeeName`. `BindingResult` must appear **immediately after** the corresponding `@Valid @ModelAttribute` parameter if the controller handles conversion and validation errors itself. Validation requires a suitable Bean Validation provider at runtime.

Do not confuse `@ModelAttribute` with `@RequestBody`:

| `@ModelAttribute` | `@RequestBody` |
| --- | --- |
| Binds form/query and MVC sources into a model attribute | Reads body via HttpMessageConverter, usually Jackson for JSON |
| Supports MVC constructor/property binding | Jackson has its own creator rules |
| `@BindParam` can remap request parameter names | Does not automatically apply `@BindParam` to JSON keys |
| `BindingResult` can follow the attribute | JSON syntax/deserialization errors occur before validation and need separate handling |

## 10. Allowing Only Constructor Binding When Needed

Creating an object via a constructor **does not automatically lock down all setters**. Consider the class:

```java
public class CreateUserForm {
    private final String email;
    private String role;

    public CreateUserForm(String email) {
        this.email = email;
    }

    public String getEmail() { return email; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
}
```

If property binding still runs, a request sending `role=ADMIN` **could** invoke `setRole` even though the constructor only takes `email`. To configure declarative binding in MVC:

```java
// Snippet inside @Controller or @ControllerAdvice.
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

This flag always permits constructor binding, and only allows property binding when `allowedFields` is configured appropriately. If setter binding is needed for specific fields, declare them explicitly:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("comment");
}
```

The final snippet is a policy example, assuming the actual object has a valid `comment` property. `allowedFields` primarily restricts **property binding**; it is not a filter for all constructor parameters. Thus a form constructor containing a sensitive `role` parameter is still unsafe if clients can supply `role`. Use task-specific DTOs, design constructors containing only valid inputs, and enforce permissions in services.

Security principle: **"Having a constructor parameter or setter" does not mean "the client has permission to update that field."** IDs, statuses, prices, roles, and audit fields usually must be loaded or computed server-side.

## 11. Troubleshooting Sequence When Constructor Binding Fails

1. **Selected constructor:** Is there one clear data constructor? Is an empty constructor getting in the way? Are overloads causing ambiguity?
2. **Name metadata:** What names does `Constructor.getParameters()` return? Is `Parameter.isNamePresent()` true? What does `BeanUtils.getParameterNames` return?
3. **Build configuration:** Is `-parameters` enabled on the module containing the DTO? Have you cleaned/rebuilt the JAR?
4. **Name annotations:** Does `@ConstructorProperties` have the exact count and order of elements? Does `@BindParam` match the actual request key?
5. **Conversion:** Can numeric/date strings convert to the Java types? Is the necessary `ConversionService`/formatter registered?
6. **Missing fields:** Are parameters primitive or reference types? What are the null/required rules? Is validation configured after binding?
7. **Nested objects:** Does the nested target have a valid data constructor? Does the source name follow `address.city` format?
8. **Setter binding after constructor:** Are unintended fields being assigned? Do you need `setDeclarativeBinding(true)` or `allowedFields`?
9. **HTTP vs. JSON:** Is the failure really in `@ModelAttribute` or in Jackson handling `@RequestBody`?
10. **Boundary limits:** Are request sizes, nested depth, list element counts, and server-side permissions enforced?

### Common Errors and Fixes

| Situation | Common Cause | How to Fix |
| --- | --- | --- |
| Unable to resolve parameter `customer` | Missing names in bytecode | Enable `-parameters` or add appropriate naming metadata |
| Seeing `arg0` and `arg1` | Java reflection lacks real names | Rebuild and inspect metadata |
| Empty constructor chosen | Multiple constructors exist and no-args is selected | Use a single data constructor or a record |
| Request key `first-name` does not map to `firstName` | Input naming contract differs | Use `@BindParam` in MVC |
| Numeric value fails to parse | Type mismatch | Check `BindingResult`, configure converter/formatter |
| `Integer` parameter is null | Client omitted it or lookup name mismatches | Check input key and `@NotNull` |
| Constructor parameter order changed in source | `@ConstructorProperties` was not updated | Fix the exact order and add tests |
| DTO with `role` setter gets bound | Property binding is still running | Dedicated DTO + declarative binding |
| `@Autowired` fails to bind HTTP form | Wrong mechanism | Separate dependency injection from data binding |
| `@JsonProperty` has no effect on @ModelAttribute | Annotation is for Jackson | Use constructor binder metadata |
| Validation does not run | Validator not enabled/registered | Use `@Valid` with a Bean Validation provider or call `binder.validate()` |
| Legacy class uses Lombok/codegen | Actual constructor differs from visible source | Inspect compiled bytecode/runtime reflection and build config |

## 12. Nested Objects and Collections

Spring constructor binding can also recursively construct nested objects:

```java
public record AddressForm(String city, String zipCode) {}

public record CheckoutForm(
        String customer,
        AddressForm address) {}
```

Data source:

```text
customer=Lan
address.city=Hue
address.zipCode=530000
```

Given sufficient metadata and valid types, the binder can create `AddressForm` and pass it to `CheckoutForm`'s constructor. Similarly, lists/maps/arrays can accept keys using indexed/mapped syntax such as `items[0].sku` or `accounts[KEY].name`.

However, distinguish **syntax support** from **a guarantee that every input constructs an object**. Nested constructors may be invalid, inputs may miss data, conversions can fail, or structures may grow too large. For client-supplied data, cap element counts, nesting depth, and request size; never permit arbitrary object graph construction.

## 13. Testing and Self-Assessment

Your test suite should cover at least these cases:

- Regular class with one public constructor compiled with `-parameters`; verify name matching.
- Record canonical constructor with matching component names.
- Class with `@ConstructorProperties` where logical names differ from Java variable names.
- Class with both no-args and data constructors; verify actual selection.
- Missing parameter, `null`, and type mismatch (e.g., `seats=abc`).
- HTTP form using `@BindParam("attendee-name")` and exact input `attendee-name`.
- Nested objects and size-bounded lists.
- Valid constructor data that fails Bean Validation constraints.
- Requests adding unauthorized `role` or `price` fields.
- Changing compiler flags/annotations and regression-testing parameter names.

**Question 1:** Why isn't constructor selection based on parameter count? Because Spring uses primary/single/default rules; "longest constructor" is not a universal contract.

**Question 2:** If parameter names are already in Java source, do we still need `-parameters`? For regular Java classes, you usually need this compiler option or an alternative metadata source so Spring can read names reliably at runtime.

**Question 3:** What does `@ConstructorProperties` do? It maps **logical names in order to constructor parameters**; it does not choose constructors, convert types, or validate.

**Question 4:** Does `@BindParam` apply to every JSON `@RequestBody`? No. It supports name mapping for MVC/WebFlux constructor binding; JSON generally belongs to Jackson.

**Question 5:** Does using a record completely eliminate mass assignment? No. Records only protect structure against ordinary setter binding; if the constructor includes sensitive fields that clients are allowed to pass, security is still broken at the contract level.

**Question 6:** When `@ModelAttribute` has a `BindingResult`, where must it be placed? Immediately after the corresponding model attribute parameter.

## 14. Adoption Checklist

1. Identify the operation and the exact fields clients are permitted to send.
2. Choose a record or a single clear data constructor.
3. Decide on name metadata: record, `-parameters`, `@ConstructorProperties`, or `@BindParam` as appropriate.
4. Align input names, parameter types, optional/required semantics, and nested paths.
5. If calling `DataBinder.construct(...)` manually: initialize with a `null` target, set `targetType`, provide `ValueResolver`, inspect `BindingResult`.
6. In Spring MVC: use `@ModelAttribute`, proper validation, and error handling; consider enabling `declarativeBinding`.
7. Restrict property binding and never accept roles/prices/statuses from requests unless business rules allow it.
8. Test actual compiled bytecode metadata, constructor selection, type mismatches, missing fields, over-posting, and contract changes.

**Conclusion:** Constructor binding works accurately when Spring **selects the right constructor** and **reads each parameter name** to look up input values. Compiling with `-parameters`, using clear name metadata, and designing task-specific DTOs prevents most hard-to-spot errors.

## 15. Official Documentation

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor selection, parameter names, and nested constructor binding.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): model attribute constructors, `@BindParam`, and `BindingResult`.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): constructor/property binding, `declarativeBinding`, `allowedFields`.
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): configuring WebDataBinder in controllers.
- [Spring Javadoc — BeanUtils](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/beans/BeanUtils.html): `getResolvableConstructor` and `getParameterNames`.
- [Spring Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html): `construct`, `ValueResolver`, `NameResolver`.
- [JDK 17 — java.lang.reflect.Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): runtime names and `isNamePresent()`.
- [JDK 17 — java.beans.ConstructorProperties](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/ConstructorProperties.html): positional parameter name annotations.
