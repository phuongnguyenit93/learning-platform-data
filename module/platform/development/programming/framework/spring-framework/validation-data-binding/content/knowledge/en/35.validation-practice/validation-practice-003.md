# Building Immutable DTOs with Constructor Binding in Spring MVC

## 1. Hands-On Problem and Expected Outcome

An endpoint receives booking information via `application/x-www-form-urlencoded`:

```http
POST /api/bookings
Content-Type: application/x-www-form-urlencoded

guest-name=Mai&
guest-count=2&
arrival=2026-11-20&
contact.email=mai@example.com
```

We want Spring MVC to construct an **immutable request DTO** without needing:
- A no-arg constructor.
- Public setters for every field.
- Calling `new` on the DTO inside the controller.
- Copying a bunch of properties from the form onto a domain entity.
- Allowing the client to modify `ownerId`, `approved`, or other server-determined properties.

Example target DTO:

```java
public record BookingForm(
        String guestName,
        Integer guestCount,
        LocalDate arrival,
        Contact contact) {

    public record Contact(String email) {}
}
```

**Expected output:** Spring uses the input names corresponding to the constructor parameters to instantiate `BookingForm` and `Contact`; `guestCount` is converted from String to Integer, and `arrival` to LocalDate. Afterward, Jakarta Validation checks the constraints. All public state of the record is read through accessors, never modified through setters.

**However, immutability does not equal absolute safety.** A record can hold a mutable `List`/`Map`; constructor binding still accepts every declared parameter; `@BindParam` only maps names and does not automatically forbid dangerous fields; without `BindingResult`, errors may flow through global advice. This lesson addresses all of those nuances.

**Objectives:**

1. Understand the difference between **constructor binding** and **property/setter binding** in Spring MVC.
2. Use a Java 17 `record` or a class with one public constructor and `final` fields.
3. Map form field names with `@BindParam`, including names containing hyphens.
4. Use `@InitBinder` and `WebDataBinder#setDeclarativeBinding(true)` to prevent unintended property binding.
5. Bind nested DTOs, parse dates, and validate `@NotBlank`/`@NotNull`/`@Min`/`@Max`/`@Email` with `@Valid`.
6. Separate **binding/conversion errors** from **Bean Validation violations** via `BindingResult`.
7. Understand why constructor binding does not by default **reject unknown HTTP parameters**.
8. Distinguish form/query `@ModelAttribute` from JSON `@RequestBody` via Jackson.
9. Build a complete Java 17 + Spring Boot 3.5.6 project with MockMvc tests for the happy path, error cases, and security.
10. Know when dedicated DTOs, defensive copies, authorization checks, and collection limits are needed.

**Context:** module *Spring Framework - validation-data-binding*, group *Practice*. The direct topic is **building immutable DTOs with constructor binding**, not a general tutorial on JPA or Jackson. The main examples run on the Spring MVC Servlet stack, Spring Framework 6.2.x, Jakarta Validation, and Java 17.

## 2. Two Ways for DataBinder to Create/Populate an Object

### 2.1. Traditional Property Binding

Mutable JavaBean DTO:

```java
public class BookingBean {
    private String guestName;
    private Integer guestCount;

    public BookingBean() {}

    public void setGuestName(String guestName) {
        this.guestName = guestName;
    }

    public void setGuestCount(Integer guestCount) {
        this.guestCount = guestCount;
    }

    public String getGuestName() { return guestName; }
    public Integer getGuestCount() { return guestCount; }
}
```

Spring can:
1. Instantiate the object using the default constructor.
2. Match request field names against bean properties.
3. Convert String values.
4. Invoke setters.
5. Run validators when `@Valid`/`@Validated` is present.

The drawback of using a domain entity directly: the client can send property names that the UI does not display, such as `approved`, `role`, `ownerId`, nested objects, or indexed collections. If matching setters exist and no policy blocks them, this results in **mass assignment/over-posting**.

### 2.2. Constructor Binding

With an immutable DTO:

```java
public record BookingForm(String guestName, Integer guestCount) {}
```

Spring MVC can:
1. Determine the primary/data constructor.
2. Look up request values by **constructor parameter names**.
3. Convert each value into the constructor argument type.
4. Invoke the constructor to build a complete instance (if construction is feasible).
5. Validate the object after binding.

There is no step requiring setter calls for a record.

**Exact note:** Spring MVC by default can perform **both constructor binding and property binding**. Simply having a constructor on a model does not mean Spring automatically disables setter binding for other objects. Spring Framework 6.1+ supports `setDeclarativeBinding(true)` to restrict binding to constructor arguments and explicitly allowlisted property fields. <Cite ref="turn890037search0"/>

### 2.3. Comparison Table

| Criterion | Constructor binding | Property binding |
| --- | --- | --- |
| Input mapped by | Constructor parameters | Bean properties/setters |
| Does object need no-arg constructor? | No; needs an appropriate data constructor | Usually yes |
| Can DTO use a Java `record`? | Yes | Records do not provide standard setters |
| When is state set? | When constructing the object | After the object already exists |
| Supports nested objects? | Yes, recursive constructor binding | Yes, nested paths/getters/setters |
| Supports List/Map? | Yes, via constructor arguments/indexed keys | Yes, via bean property paths |
| Does `@BindParam` rename input? | Yes, used for constructor argument/field | Does not automatically turn into setter property mapping |
| What does `allowedFields` restrict? | Not an allowlist for constructor args | Restricts property binding |
| Security priority | DTO constructor contains only public fields | Must set a strict allowlist for permitted fields |
| Error diagnostics | BindingResult + validation | BindingResult + validation |

**Subtle but critical point:** Restricting setter binding cannot block a sensitive parameter that you declared in the constructor. To avoid accepting `role` or `approved` from the client, **do not put them in the request constructor**.

## 3. Java 17 Record — a Reference-Level Immutable DTO

```java
public record BookingForm(
        String guestName,
        Integer guestCount) {}
```

The compiler provides:
- `private final` fields for the record components.
- A canonical constructor with the exact components.
- Accessors `guestName()` and `guestCount()`.
- `equals`, `hashCode`, and `toString` based on the components.

Usage:

```java
BookingForm input = new BookingForm("Mai", 2);

System.out.println(input.guestName());
System.out.println(input.guestCount());
```

Stdout:

```text
Mai
2
```

There is no `setGuestName(...)`. To “change” a value you must create a new instance:

```java
BookingForm updated =
        new BookingForm(input.guestName(), 3);
```

This gives **immutability** semantics at the record fields. However:
- A record does not automatically validate values; `new BookingForm("", -1)` can still instantiate an object if the constructor does not check.
- If the record contains a mutable `List<String>`, the underlying list can still be mutated afterward.
- A record can hold mutable beans, byte arrays, Maps, or collections; **deep immutability** must be designed when needed.
- A record does not authenticate caller permissions.
- Simply having fewer fields with setters does not by itself prevent all JSON deserialization issues.

### 3.1. When a Record Cannot Be Used

A standard immutable class:

```java
public final class GuestInput {

    private final String displayName;

    public GuestInput(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

For Spring constructor binding, the class should have one unambiguous data constructor and parameter names retained at runtime, typically via javac `-parameters`. If there are multiple overloaded constructors or a no-arg constructor, the framework may take a different path depending on the version's rules. With Java records, canonical components are clearer and usually the most convenient choice for short request DTOs.

This is an illustrative **fragment**; the runnable files are in section 12.

## 4. Constructor Argument Names and `@BindParam`

A web form has legacy/kebab-case names:

```text
guest-name=Mai
guest-count=2
```

In Java, the record components are `guestName` and `guestCount`. You can use:

```java
import org.springframework.web.bind.annotation.BindParam;

public record BookingForm(
        @BindParam("guest-name") String guestName,
        @BindParam("guest-count") Integer guestCount) {}
```

Spring MVC 6.1+ supports `@BindParam` on a constructor parameter or corresponding field to map the input name. For a Java record, the annotation has `PARAMETER`/`FIELD` targets and can be placed on the component in source, after which the compiler propagates it to the supported program elements. <Cite ref="turn129063view0"/>

**Result:**
- `guest-name` from the form maps to constructor argument `guestName`.
- `guest-count` maps to `guestCount`.
- It does not mean both `guestName` and `guest-name` are accepted simultaneously.
- It does not mean Jackson will treat `@BindParam` as `@JsonProperty`.

### 4.1. Compiler Parameter Metadata

For ordinary immutable classes, add configuration:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

This option preserves runtime method/constructor parameter names (`-parameters`). If metadata is missing, the framework may fail to determine the proper input names during constructor binding. Test the build with Java 17 and the proper Maven compiler configuration.

### 4.2. `DataBinder.NameResolver` for Custom Naming Schemes

Spring supports setting a `DataBinder.NameResolver` for custom mappings more complex than `@BindParam`. This is an advanced mechanism and is not needed for the demo project. Use it only if an entire module shares a field-naming convention that needs consistent resolution; you must carefully account for nested paths, aliases, canonicalization, and security. Never write a resolver that reads the whole request and silently maps every unknown field.

## 5. `setDeclarativeBinding(true)` — Bind Only What Is Declared

Controller configuration:

```java
@InitBinder("bookingForm")
void bindConstructorOnly(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Spring Framework 6.1+:
- `false` (default): can bind constructor and property fields.
- `true`: constructor binding still runs; setter/property binding **does not run unless** `allowedFields` is configured.

For example, a legacy model has a public constructor taking `email` and a setter `setApproved(boolean)`. With `setDeclarativeBinding(true)` and without adding `allowedFields("approved")`, a client sending `approved=true` **will not trigger that setter via property binding**.

This complements records, though it does not replace input model design: a request DTO should **not** include privileged properties in its constructor. <Cite ref="turn890037search0"/>

### 5.1. Pitfall: Configuring `setAllowedFields` Can Re-Enable Property Binding

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");
```

In declarative mode, setter binding can still happen **for allowlisted properties**. Do not use `setAllowedFields("*")` because it defeats most of the protection for the setter surface.

For a constructor-only DTO, the simplest configuration is:

```java
binder.setDeclarativeBinding(true);
```

and **do not** declare `allowedFields` if setter binding is not needed.

### 5.2. `allowedFields` Does Not Filter Constructor Arguments

Suppose you declare:

```java
public record UnsafeForm(
        String displayName,
        boolean approved,
        String ownerId) {}
```

Even if you use:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName");
```

that **does not automatically ensure** constructor arguments `approved` and `ownerId` are ignored. They are part of the data constructor, whereas `allowedFields` controls **property binding**. The right fix is removing them from the request constructor and letting the server determine owner/approval.

### 5.3. Is `setIgnoreUnknownFields(false)` the Solution for Unknown Input?

No. `DataBinder#setIgnoreUnknownFields(boolean)` applies primarily to **property binding** via `bind(PropertyValues)`; it does not turn `construct(ValueResolver)` into a filter over all HTTP keys. The constructor binder picks the values it needs to supply constructor arguments; out-of-list inputs may simply go unused without generating `FieldError` or `suppressedFields`. <Cite ref="turn890037search8"/>

If the API requires **rejecting all unknown parameters**, design a check over raw parameter names/schema before touching the domain, or use a boundary parser with an explicit policy. The demo includes a strict endpoint illustrating this.

## 6. Nested Records: Recursive Constructor Binding

DTO:

```java
public record BookingForm(
        String guestName,
        Contact contact) {

    public record Contact(String email) {}
}
```

Request:

```text
guestName=Mai
contact.email=mai@example.com
```

With Spring MVC constructor binding, if the `contact` constructor argument is an object and nested path values are present, the framework can construct `Contact` through its constructor. The resulting data:

```java
booking.contact().email()
```

**No setter needed** such as `setContact` or `setEmail`. Still, place `@Valid`/`@NotNull` appropriately when you need to ensure nested data is actually valid.

### 6.1. Jakarta Validation on Record Components

```java
public record BookingForm(
        @NotBlank String guestName,
        @NotNull @Valid Contact contact) {

    public record Contact(
            @NotBlank @Email String email) {}
}
```

- `@NotBlank` rejects null/empty/blank on `guestName`.
- `@NotNull` rejects a missing `contact`.
- `@Valid` triggers cascade validation into `Contact`.
- `@Email` checks email format but does not guarantee non-null/non-blank; combine with `@NotBlank`.
- `@Valid` **does not forbid null by itself**: `@NotNull` is required when the child object is mandatory.

Do not confuse binding with validation. When `contact.email` is missing or malformed, Spring may construct `Contact` with `email=null` and then the validator catches `@NotBlank`; when pre-constructor conversion fails, `BindingResult` can contain a type mismatch.

## 7. Type Conversion When Invoking Constructors

Form requests are all text:
- `guest-count=2`: `String` → `Integer`.
- `arrival=2026-11-20`: `String` → `LocalDate`.
- `contact.email=mai@example.com`: `String` → `String`.

The full record in the demo includes:

```java
@NotNull
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate arrival
```

This is a **Spring formatting annotation**, not a Jakarta Validation constraint. It requests ISO date parsing on the `@ModelAttribute`/Spring `ConversionService` path. A request `arrival=20/11/2026` does not match ISO, so it is a **binding/conversion problem**, not a failure of `@NotNull` or `@Past`.

### 7.1. Why Use Wrapper `Integer` Instead of `int`?

`Integer` can represent null when input is missing, allowing `@NotNull` to detect a missing `guest-count`. Primitive `int` cannot represent null; if a constructor takes a primitive and the converter has no value, the framework must decide how to handle the missing argument and exceptions may differ.

To distinguish a **missing field** from **numeric 0**, use `Integer` with `@NotNull` and `@Min(1)`.

### 7.2. Distinguishing Wrong Type Input from Constraint Violations

For `guest-count`:
- `2`: parses into Integer 2; constraints pass.
- `0`: parses into Integer 0; `@Min(1)` fails.
- `abc`: String→Integer conversion fails; binder reports `typeMismatch`.
- Omitted: value can be null; `@NotNull` fails if the object is constructed.

A test asserting only HTTP 400 does not indicate which kind of error occurred. Tests should distinguish `BINDING_ERROR`/`VALIDATION_ERROR` codes and specific field issues.

## 8. `BindingResult` and Preserving Errors from Constructors

The controller can handle errors inline:

```java
@PostMapping("/bookings")
public ResponseEntity<?> book(
        @Valid @ModelAttribute("bookingForm") BookingForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(ApiError.fromBindingResult(errors));
    }

    // Proceed only when the object is valid.
}
```

**`BindingResult` must be placed immediately after** the bound/validated argument. Without it, Spring MVC normally throws `MethodArgumentNotValidException` for binding/validation errors, and a global `@RestControllerAdvice` must handle it.

`BindingResult` provides:
- `getFieldErrors()`: field-level problems.
- `FieldError.getField()`: field path.
- `FieldError.isBindingFailure()`: true for conversion/binding errors.
- `getGlobalErrors()`: object-level validation.
- `getSuppressedFields()`: fields suppressed by property binding policy, not a global unknown-key detector.

**Constructor binding caveat:** If a constructor cannot instantiate the target due to a severe construction failure (an exception thrown by the constructor itself, no matching constructor selected, or metadata issues), the request may fail before the handler with a different exception. `BindingResult` does not promise to turn **every runtime exception** into field errors. Avoid placing I/O logic or throwing unnecessary business exceptions inside DTO constructors.

### 8.1. There May Not Be Only One Error per Field

With `guest-count=abc`, the binder records a type mismatch. Depending on the handling mechanism, the validator might also see null or another error. Do not hardcode tests asserting `issues.length==1` for every kind of conversion failure unless the contract guarantees it.

Instead:
- Assert `code=="BINDING_ERROR"` when `isBindingFailure()==true` is present.
- Assert the list contains the relevant field issue and issue code `typeMismatch`.
- When multiple errors must be reported, keep all issues rather than a single trailing String.

### 8.2. Example Error Contract

```json
{
  "code": "BINDING_ERROR",
  "issues": [
    {
      "field": "guestCount",
      "code": "typeMismatch",
      "category": "binding"
    }
  ]
}
```

This is the **application schema** in the demo project, not Spring MVC's default body. With the `guest-count` alias, the field path in `BindingResult` may be recorded under the constructor argument or binding name depending on the processing path; therefore tests focus on the `typeMismatch` code and semantics rather than guessing exact field path spelling across versions.

## 9. Constructor Binding with List, Map, and Array

Spring supports List/Map/array constructor arguments via single values (e.g., delimited strings) or indexed paths such as `rooms[0].code`, `labels[color]`. <Cite ref="turn615564search0"/>

**Illustrative** record example:

```java
public record BatchInput(
        @Size(min = 1, max = 3)
        List<@Valid RoomInput> rooms,
        Map<String, String> labels) {}

public record RoomInput(
        @NotBlank String code) {}
```

Request:

```text
rooms[0].code=A101
rooms[1].code=A102
labels[color]=blue
```

Spring can construct nested collection objects via constructor binding; however, design concerns remain:
1. **Overly large or sparse indices**: do not allow input to inflate the object graph arbitrarily.
2. **Arbitrary Map keys**: `labels[role]` can introduce policy-violating metadata if a constructor accepts a Map.
3. **Mutable collection references**: a record holding a List/Map does not automatically make the elements or the collection immutable.
4. **`@Size(max=3)` after binding**: does not replace early request size limits, parser depth limits, or resource caps.
5. **Duplicate field names**: define an explicit policy when the same input name appears multiple times.
6. **Nested `@Valid`**: cascade per element when needed, and add `@NotNull` on the element type when null elements are forbidden.
7. **Security ownership**: never use Map keys in place of caller authorization.

**Do not run this snippet directly inside the project in section 12**; it is an extension exercise for practice. The code requires importing `java.util.List`/`Map`, `jakarta.validation.Valid`/`constraints`, and choosing limits suited to your domain.

### 9.1. Shallow Immutability and Defensive Copying

A record:

```java
public record Names(List<String> values) {}
```

does not protect the passed-in list:

```java
List<String> input = new ArrayList<>();
input.add("Mai");
Names names = new Names(input);
input.add("Lan");
System.out.println(names.values().size()); // 2
```

To prevent mutating the collection through an external reference:

```java
public record Names(List<String> values) {
    public Names {
        if (values != null) {
            values = List.copyOf(values);
        }
    }
}
```

When `values` is non-null and all elements are non-null, `List.copyOf` creates an unmodifiable snapshot list. If the input contains null elements, `List.copyOf` throws `NullPointerException` **before validation**. Do not apply this blindly with form binders that may temporarily create sparse lists/null elements: design an early null/size policy and test it. If temporary nulls must be kept so the validator can detect them, choose a copy strategy that allows nulls without exposing mutable state.

**The difference:** defensive copying protects **immutability after the object exists**. It does not replace input allowlists, bound/size limits, or service authorization.

## 10. Comparing JSON `@RequestBody`: Jackson Does Not Use `@BindParam`

Two endpoints can accept the same record:

```java
@PostMapping(path="/bookings/form",
             consumes="application/x-www-form-urlencoded")
public void fromForm(@ModelAttribute BookingForm form) {}

@PostMapping(path="/bookings/json",
             consumes="application/json")
public void fromJson(@RequestBody BookingForm form) {}
```

In form binding:
- Spring MVC/WebDataBinder uses constructor metadata.
- `@BindParam("guest-name")` specifies the request form field name.

In JSON:
- Jackson/`HttpMessageConverter` deserializes JSON according to Jackson's schema.
- The record's default property name is `guestName`, not `guest-name`.
- `@BindParam` does not replace `@JsonProperty("guest-name")`.
- `WebDataBinder#setDeclarativeBinding(true)` does not control Jackson JSON deserialization directly, though Spring may use a binder to run validation after decoding.

Matching JSON:

```json
{
  "guestName": "Mai",
  "guestCount": 2,
  "arrival": "2026-11-20",
  "contact": {"email": "mai@example.com"}
}
```

Equivalent form:

```text
guest-name=Mai
guest-count=2
arrival=2026-11-20
contact.email=mai@example.com
```

**Recommendation:** If the JSON and form contracts differ or evolve independently, create **separate request DTOs for each content type**. Do not make the entire API depend on a single record carrying both Spring form annotations and Jackson annotations if doing so makes naming and backward compatibility confusing.

## 11. Security Practice: Keep Privileged Fields Out of Input Constructors

Suppose the domain model has:

```java
public class Booking {
    private UUID id;
    private UUID ownerId;
    private boolean approved;
    private String guestName;
    // ...
}
```

This is a **domain fragment** not included in the runnable project. Never bind a request into an entity and save it simply because it has a constructor:

```java
// Anti-pattern:
repository.save(boundEntity);
```

Better:

```java
BookingForm input = ...;          // only public input fields
UUID owner = currentPrincipalId(); // from authenticated context

Booking entity = new Booking(
        generatedId(), owner, false,
        input.guestName(), input.guestCount());
```

The above is a **pseudo-flow** without full definitions. Key point: the server determines `ownerId`, `approved`, and business state itself, checks caller permissions, and maps only the permitted fields explicitly.

### 11.1. Why Not Rely Solely on `getSuppressedFields()`?

With property binding using allowed/disallowed fields, `BindingResult.getSuppressedFields()` reports names that were blocked. With constructor binding, the binder only grabs the constructor arguments it needs; an unknown parameter like `approved=true` may simply be **ignored** rather than recorded in suppressed fields. `hasErrors()==false` does not prove the request contained no unknown names.

If the contract requires returning 400 for unknown form fields, implement a **schema-aware raw parameter name check** and test it separately. Be sure to use the exact aliases `guest-name`, `guest-count`, nested `contact.email`, rather than mixing them up with JSON property names.

### 11.2. “Strict” Is Only an Endpoint Policy

The sample project offers two options:
- `POST /api/bookings`: constructor-only, **ignores** unknown request fields because they are not constructor arguments; does not assign them to the DTO/domain.
- `POST /api/bookings/strict`: explicitly checks `HttpServletRequest.getParameterMap().keySet()` against an allowlist of **form parameters** and returns `UNEXPECTED_FIELD` if any other key is present.

**Limitation:** Checking raw form/query parameter keys does not replace policies for other sources `@ModelAttribute` can read (URI variables, MVC-normalized header names). For strict endpoints serving external clients, validate the schema of **all input sources** per the endpoint contract or use a request decoding layer with an explicit policy. Do not infer “checking the param map alone is enough to block every path”.

## 12. Complete Java 17 + Spring Boot 3.5.6 Project

The example below focuses on hands-on practice with two models:
- `BookingForm`: a **record**, with `@BindParam`, nested record, type conversion, and validation.
- `AccessChangeForm`: a **mutable class with a public constructor + hypothetically dangerous setter**. `setDeclarativeBinding(true)` proves the `approved` setter is not bound.

No database, credentials, or network outside localhost is used. `BookingController` only builds response views without persisting. Real production APIs need service/domain/authorization layers beyond the binding step.

### 12.1. Directory Structure

```text
immutable-constructor-demo/
├── pom.xml
├── src/main/java/demo/immutable/
│   ├── ImmutableDtoApplication.java
│   ├── BookingForm.java
│   ├── AccessChangeForm.java
│   ├── ApiError.java
│   ├── BookingController.java
│   └── ApiExceptionHandler.java
└── src/test/java/demo/immutable/
    ├── BookingFormMvcTest.java
    ├── BookingSecurityMvcTest.java
    ├── BookingJsonMvcTest.java
    └── ImmutableRecordTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>immutable-constructor-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>maven-compiler-plugin</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Dependencies:**
- `spring-boot-starter-web`: MVC + Jackson.
- `spring-boot-starter-validation`: Jakarta Validation provider.
- `spring-boot-starter-test`: Spring Test MockMvc and JUnit Jupiter.
- Compiler `-parameters`: retains parameter names for ordinary constructors; still useful when the demo includes classes rather than records alone.

Pay attention to the Maven plugin configuration above: the `groupId` of `maven-compiler-plugin` must be **`org.apache.maven.plugins`**, not `maven-compiler-plugin`. The complete `pom.xml` file must use the corrected snippet as follows:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

This standard snippet **replaces** the compiler plugin block in the POM listing above when creating the actual file. Do not keep two plugin entries for the same artifact. Keep this in mind when copying the code into a project: the POM must use the standard groupId for consistent Maven resolution.

### 12.3. `ImmutableDtoApplication.java`

```java
package demo.immutable;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImmutableDtoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImmutableDtoApplication.class, args);
    }
}
```

### 12.4. `BookingForm.java`

```java
package demo.immutable;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.BindParam;

import java.time.LocalDate;

public record BookingForm(

        @BindParam("guest-name")
        @NotBlank(message = "guestName.required")
        String guestName,

        @BindParam("guest-count")
        @NotNull(message = "guestCount.required")
        @Min(value = 1, message = "guestCount.min")
        @Max(value = 8, message = "guestCount.max")
        Integer guestCount,

        @NotNull(message = "arrival.required")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate arrival,

        @NotNull(message = "contact.required")
        @Valid
        Contact contact) {

    public record Contact(
            @NotBlank(message = "contact.email.required")
            @Email(message = "contact.email.invalid")
            String email) {
    }
}
```

The code focuses on the data clients are allowed to submit. There is no `ownerId`, `admin`, or `approved`.

**Why does `@BindParam` appear on record components?** The Java compiler can emit annotations targeting `PARAMETER`/`FIELD` onto the corresponding record members; Spring resolves the binding name from the constructor parameter/field. This avoids relying on browser/client naming conventions for hyphenated fields.

### 12.5. `AccessChangeForm.java` — Demonstrating Declarative Binding

```java
package demo.immutable;

public final class AccessChangeForm {

    private final String displayName;

    // Hypothetical setter that could be over-posted if property binding were enabled.
    private boolean approved;

    public AccessChangeForm(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
```

**This DTO intentionally includes a sensitive setter for testing**, not as a recommended design for a real system. Production DTOs should not expose an `approved` setter on the input model; enabling declarative constructor-only binding adds an extra defensive layer when a legacy class still retains such a setter.

### 12.6. `ApiError.java`

```java
package demo.immutable;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record ApiError(
        String code,
        List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String category) {
    }

    public static ApiError simple(String code) {
        return new ApiError(code, List.of());
    }

    public static ApiError fromBindingResult(BindingResult errors) {
        List<Issue> issues = errors.getFieldErrors().stream()
                .map(e -> new Issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.toString(e.getCode(), "invalid"),
                        e.isBindingFailure()
                                ? "binding" : "constraint"))
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code)
                        .thenComparing(Issue::category))
                .toList();

        boolean hasBinding = errors.getFieldErrors().stream()
                .anyMatch(FieldError::isBindingFailure);

        return new ApiError(
                hasBinding ? "BINDING_ERROR" : "VALIDATION_ERROR",
                issues);
    }
}
```

The application uses stable error codes:
- `BINDING_ERROR` when at least one `FieldError.isBindingFailure()==true` exists.
- `VALIDATION_ERROR` when only validator violations exist.
- `UNEXPECTED_FIELD` if the strict endpoint detects a disallowed parameter name.
- `BODY_UNREADABLE` when Jackson cannot read the JSON body.

In production, add object-level errors from `getGlobalErrors()` if custom cross-field/class-level validators exist. The demo defines no object-level constraints, so `getFieldErrors()` suffices for the existing tests. Never return raw rejected values or exception internals to the client.

### 12.7. `BookingController.java`

```java
package demo.immutable;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Set;

@RestController
@RequestMapping("/api")
public class BookingController {

    // Declare only public input names, including @BindParam aliases.
    private static final Set<String> FORM_FIELDS = Set.of(
            "guest-name", "guest-count",
            "arrival", "contact.email");

    @InitBinder({"bookingForm", "accessChangeForm"})
    void constructorOnly(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    public record BookingView(
            String guestName,
            Integer guestCount,
            String arrival,
            String email) {
    }

    public record AccessView(
            String displayName,
            boolean approved) {
    }

    private static BookingView view(BookingForm form) {
        return new BookingView(
                form.guestName(),
                form.guestCount(),
                form.arrival().toString(),
                form.contact().email());
    }

    @PostMapping(path = "/bookings",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> createForm(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/strict",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> createStrictForm(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form,
            BindingResult errors,
            HttpServletRequest request) {

        // Boundary rule for this form/query endpoint, not an
        // automatic feature of constructor binding.
        boolean unknownInput =
                request.getParameterMap().keySet().stream()
                        .anyMatch(key -> !FORM_FIELDS.contains(key));

        if (unknownInput) {
            return ResponseEntity.badRequest()
                    .body(ApiError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/advice",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<BookingView> createWithAdvice(
            @Valid @ModelAttribute("bookingForm")
            BookingForm form) {

        // No BindingResult: global advice will handle
        // binding/validation errors via MethodArgumentNotValidException.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/bookings/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookingView> createJson(
            @Valid @RequestBody BookingForm form) {

        // Jackson constructs the record from JSON; @BindParam belongs to MVC form
        // constructor binding, not JSON property names.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view(form));
    }

    @PostMapping(path = "/access",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<AccessView> access(
            @ModelAttribute("accessChangeForm")
            AccessChangeForm form) {

        return ResponseEntity.ok(
                new AccessView(
                        form.getDisplayName(),
                        form.isApproved()));
    }
}
```

**Detailed explanation of each route:**
- `/bookings`: uses constructor binding + local `BindingResult`; unknown names may be ignored without mutating state.
- `/bookings/strict`: adds an allowlist for request form/query names, explicitly rejecting unknowns.
- `/bookings/advice`: no `BindingResult`; exceptions pass through the global handler.
- `/bookings/json`: Jackson record deserialization; JSON uses camelCase properties.
- `/access`: proves `setDeclarativeBinding(true)` blocks the `setApproved` setter in property binding for a legacy class.

**Security limitation of `/bookings/strict`:** This example checks the `HttpServletRequest` parameter map of the form endpoint, rather than acting as a generic firewall for all headers/paths/session attributes. Production must protect all input sources and enforce authorization at the service layer.

### 12.8. `ApiExceptionHandler.java`

```java
package demo.immutable;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                ApiError.fromBindingResult(ex.getBindingResult()),
                headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return new ResponseEntity<>(
                ApiError.simple("BODY_UNREADABLE"),
                headers, status);
    }
}
```

This is the **global error contract** for routes without `BindingResult` and for Jackson errors in the demo. Do not add a separate `@ExceptionHandler(MethodArgumentNotValidException.class)` when the superclass already handles this type; override the protected method to avoid ambiguous mappings.

If the application has direct `@Min` on handler parameters or constraints on return values (Spring MVC 6.1+ built-in method validation), also override `handleHandlerMethodValidationException` accordingly, preserving the 400/500 status decided by the framework. The demo avoids direct method constraints to stay focused on DTO constructor binding.

## 13. Testing MVC: How Is a Record Constructed from a Form?

All files below live under `src/test/java/demo/immutable`.

### 13.1. `BookingFormMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingFormMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder valid(String path) {
        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("guest-name", "Mai")
                .param("guest-count", "2")
                .param("arrival", "2026-11-20")
                .param("contact.email", "mai@example.com");
    }

    @Test
    void recordIsConstructedFromFormFields() throws Exception {
        mvc.perform(valid("/api/bookings"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.guestCount").value(2))
                .andExpect(jsonPath("$.arrival")
                        .value("2026-11-20"))
                .andExpect(jsonPath("$.email")
                        .value("mai@example.com"));
    }

    @Test
    void bindParamAliasesUseKebabCaseNames() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guestName", "IgnoredValue"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"));
    }

    @Test
    void missingGuestNameViolatesNotBlank() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-count", "2")
                        .param("arrival", "2026-11-20")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void blankGuestNameViolatesNotBlank() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guest-name", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void missingGuestCountIsNotNullViolation() throws Exception {
        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-name", "Mai")
                        .param("arrival", "2026-11-20")
                        .param("contact.email", "mai@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }

    @Test
    void zeroGuestCountIsMinViolationNotTypeMismatch()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Min")));
    }

    @Test
    void nineGuestsExceedsMax() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "9"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Max")));
    }

    @Test
    void nonNumericGuestCountIsBindingError()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("guest-count", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void wrongDatePatternIsBindingError() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("arrival", "20/11/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")));
    }

    @Test
    void missingNestedContactViolatesNotNull()
            throws Exception {

        mvc.perform(post("/api/bookings")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("guest-name", "Mai")
                        .param("guest-count", "2")
                        .param("arrival", "2026-11-20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }

    @Test
    void invalidNestedEmailFailsCascadeValidation()
            throws Exception {

        mvc.perform(valid("/api/bookings")
                        .param("contact.email", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("contact.email")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Email")));
    }

    @Test
    void blankNestedEmailViolatesNotBlank() throws Exception {
        mvc.perform(valid("/api/bookings")
                        .param("contact.email", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void noBindingResultUsesGlobalAdvice() throws Exception {
        mvc.perform(valid("/api/bookings/advice")
                        .param("guest-count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void noBindingResultSuccessStillReturns201()
            throws Exception {

        mvc.perform(valid("/api/bookings/advice"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestCount").value(2));
    }
}
```

**Meaning of the 14 tests:**
- Spring constructs the record from constructor arguments (no setters).
- `@BindParam` handles kebab-case form names.
- Nested `Contact` constructor is invoked and `@Valid` cascades to email.
- `Integer` and `LocalDate` are converted.
- Missing/blank/out-of-range values produce Bean Validation field violations.
- Unconvertible text produces binding failures.
- Presence vs absence of `BindingResult` leads to two different error-handling paths.

Cases with multiple errors do not assert a single exact issue count. Use `hasItem` to verify the expected issue is present. `@Valid` does not guarantee input construction always completes under every runtime failure; these tests scope the malformed data to what Spring binder can reflect through `BindingResult`.

## 14. Testing Out-of-Contract Input and Setter Binding

### 14.1. `BookingSecurityMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingSecurityMvcTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request
            .MockHttpServletRequestBuilder form(String path) {

        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("guest-name", "Mai")
                .param("guest-count", "2")
                .param("arrival", "2026-11-20")
                .param("contact.email", "mai@example.com");
    }

    @Test
    void constructorBindingDoesNotSetUnknownApprovedField()
            throws Exception {

        mvc.perform(form("/api/bookings")
                        .param("approved", "true"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.approved").doesNotExist());
    }

    @Test
    void unknownFieldIsRejectedByExplicitStrictPolicy()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void strictEndpointAcceptsOnlyDeclaredFormKeys()
            throws Exception {

        mvc.perform(form("/api/bookings/strict"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"));
    }

    @Test
    void strictEndpointRejectsUnmappedCamelCaseAlias()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("guestName", "Extra"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void strictEndpointRejectsUnexpectedNestedProperty()
            throws Exception {

        mvc.perform(form("/api/bookings/strict")
                        .param("contact.admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"));
    }

    @Test
    void legacySetterIsNotInvokedInDeclarativeMode()
            throws Exception {

        mvc.perform(post("/api/access")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Mai")
                        .param("approved", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName")
                        .value("Mai"))
                .andExpect(jsonPath("$.approved").value(false));
    }

    @Test
    void constructorArgumentStillWorksInDeclarativeMode()
            throws Exception {

        mvc.perform(post("/api/access")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Lan"))
                .andExpect(jsonPath("$.approved").value(false));
    }
}
```

This test suite demonstrates **two distinct policies**: constructor binding **does not use unknown fields**, while the strict endpoint **rejects unknown fields**. The two concepts are not identical. It also verifies that the dangerous setter in `AccessChangeForm` is not invoked when `setDeclarativeBinding(true)` is enabled.

Note: asserting `$.approved` `doesNotExist()` on `BookingView` **only proves the response does not expose that field**, not that no side effects occurred. Because the demo controller does not persist and the DTO does not contain `approved`, this suffices for the example; real systems must test service/database authorization.

## 15. Testing JSON: Record Is Immutable, but Not MVC `@BindParam`

### 15.1. `BookingJsonMvcTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingJsonMvcTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID = """
            {
              "guestName":"Mai",
              "guestCount":2,
              "arrival":"2026-11-20",
              "contact":{"email":"mai@example.com"}
            }
            """;

    @Test
    void jacksonCreatesRecordUsingJsonPropertyNames()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.guestName").value("Mai"))
                .andExpect(jsonPath("$.guestCount").value(2));
    }

    @Test
    void jsonValidationStillChecksRecordConstraints()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"",
                                  "guestCount":0,
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"bad-email"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Min")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("Email")));
    }

    @Test
    void malformedJsonIsBodyUnreadable() throws Exception {
        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"guestName\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void wrongJavaTypeInJsonIsUnReadable() throws Exception {
        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"Mai",
                                  "guestCount":{"wrong":true},
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"mai@example.com"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void jsonMissingGuestCountIsConstraintViolation()
            throws Exception {

        mvc.perform(post("/api/bookings/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "guestName":"Mai",
                                  "arrival":"2026-11-20",
                                  "contact":{"email":"mai@example.com"}
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotNull")));
    }
}
```

**JSON takeaway:** Jackson constructs the record and Jakarta Validation still runs afterward, but that **does not prove Spring WebDataBinder constructor binding**. JSON and form tests should be kept separate, especially when input names/parser settings differ.

## 16. Unit Tests: Record Is Truly Immutable in Public State

### 16.1. `ImmutableRecordTest.java`

```java
package demo.immutable;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Modifier;
import java.time.LocalDate;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ImmutableRecordTest {

    @Test
    void bookingFormIsAJavaRecord() {
        assertTrue(BookingForm.class.isRecord());
        assertTrue(Modifier.isFinal(
                BookingForm.class.getModifiers()));
    }

    @Test
    void recordHasNoPublicSetter() {
        boolean publicSetter = Arrays.stream(
                BookingForm.class.getMethods())
                .anyMatch(method ->
                        method.getName().startsWith("set")
                                && method.getParameterCount() == 1);

        assertFalse(publicSetter);
    }

    @Test
    void sameComponentsHaveValueSemantics() {
        var one = new BookingForm(
                "Mai", 2,
                LocalDate.of(2026, 11, 20),
                new BookingForm.Contact("mai@example.com"));

        var two = new BookingForm(
                "Mai", 2,
                LocalDate.of(2026, 11, 20),
                new BookingForm.Contact("mai@example.com"));

        assertEquals(one, two);
        assertEquals(one.hashCode(), two.hashCode());
    }

    @Test
    void directNewDoesNotAutomaticallyRunBeanValidation() {
        var input = new BookingForm("", 0, null, null);

        // @NotBlank/@Min/@NotNull are checked when Validator runs.
        // The default record constructor does not invoke Validator itself.
        assertEquals("", input.guestName());
        assertEquals(0, input.guestCount());
    }
}
```

These are tests **without a Spring context**, verifying the Java record:
- `isRecord()` and `final`.
- No public `setX` methods.
- Two records with identical components have value equality.
- Jakarta Validation **does not run automatically just by calling `new`**. For other APIs creating objects directly, invoke the validator or enforce dedicated domain invariants.

**Do not assume lacking setters = deep immutability.** The test in section 9.1 showed that a record can still hold a mutable List and require defensive copying.

## 17. Running the Project and Verifying Results

The illustrative project has:
- `BookingFormMvcTest`: 14 tests.
- `BookingSecurityMvcTest`: 7 tests.
- `BookingJsonMvcTest`: 5 tests.
- `ImmutableRecordTest`: 4 tests.

**Total: 30 `@Test` methods** according to the listings. This is a **static expectation from the code listings**, not an executed Maven report.

In the `immutable-constructor-demo` directory:

```bash
mvn test
```

Run each class individually:

```bash
mvn -Dtest=BookingFormMvcTest test
mvn -Dtest=BookingSecurityMvcTest test
mvn -Dtest=BookingJsonMvcTest test
mvn -Dtest=ImmutableRecordTest test
```

Run the server:

```bash
mvn spring-boot:run
```

The unit tests need no service or database. The MockMvc tests use `@SpringBootTest + @AutoConfigureMockMvc` to exercise actual Spring MVC argument resolution/constructors/formatter/validator/advice inside a mock servlet environment; these are **not HTTP network tests**. Actual Maven/Surefire reports can be inspected in `target/surefire-reports` after running.

## 18. Trying with curl

### 18.1. Valid Form

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Expected HTTP **201 Created**:

```json
{
  "guestName": "Mai",
  "guestCount": 2,
  "arrival": "2026-11-20",
  "email": "mai@example.com"
}
```

### 18.2. Misspelled `@BindParam` Alias

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guestName=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

The field `guestName` in the raw form does not substitute for `guest-name` declared by the constructor alias. The DTO may receive `guestName=null`, and then `@NotBlank` reports an error. On the strict route, `guestName` is also rejected by the **unknown parameter check**.

### 18.3. Wrong Numeric Type

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=abc' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Expected HTTP 400, response category `BINDING_ERROR` with issue `typeMismatch`.

### 18.4. Constraint Violation

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=0' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com'
```

Expected HTTP 400, category `VALIDATION_ERROR` with issue `Min`.

### 18.5. Extra Field Ignored or Rejected Depending on Endpoint

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'guest-name=Mai' \
  --data-urlencode 'guest-count=2' \
  --data-urlencode 'arrival=2026-11-20' \
  --data-urlencode 'contact.email=mai@example.com' \
  --data-urlencode 'approved=true'
```

Route `/bookings`: the extra form parameter is not in the DTO constructor so it never becomes privileged state; in the demo it is ignored and the request can still return 201.

Change the path to:

```text
http://localhost:8080/api/bookings/strict
```

and the application's policy detects the unknown name and returns HTTP 400:

```json
{"code":"UNEXPECTED_FIELD","issues":[]}
```

This is an **API contract** choice, not an automatic feature of `@BindParam`.

### 18.6. JSON Record via Jackson

```bash
curl -i -X POST \
  'http://localhost:8080/api/bookings/json' \
  -H 'Content-Type: application/json' \
  --data-binary '{
    "guestName":"Mai",
    "guestCount":2,
    "arrival":"2026-11-20",
    "contact":{"email":"mai@example.com"}
  }'
```

Expected HTTP 201 and the same `BookingView` as the form. JSON uses the **camelCase** names of the record components; do not send `guest-name` just because the form constructor has `@BindParam`.

## 19. Diagnosing Common Errors

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `@ModelAttribute` record is all null | Constructor parameter names/`@BindParam` aliases do not match | Check `-parameters` metadata and request keys |
| Spring does not pick the desired constructor | Multiple constructors or unsuitable no-arg constructor | Simplify DTO, keep one clear data constructor |
| `guest-count=abc` returns 400 | Type conversion failed, not `@Min` yet | Check `FieldError.isBindingFailure()` |
| `guest-count=0` returns 400 | Conversion passed, `@Min(1)` failed | Assert issue `Min` |
| Nested `contact.email` not validated | Missing `@Valid` on the contact component | Add `@NotNull @Valid` |
| `@Valid` does not catch null contact | `@Valid` skips null | Add `@NotNull` |
| `arrival=20/11/2026` fails | Form expects ISO.DATE | Define `@DateTimeFormat`/format contract |
| `setDeclarativeBinding(true)` still accepts sensitive field | That field may be declared in the constructor itself, or property binding allowed via allowedFields | Remove from input constructor, inspect binder policy |
| Unknown field produces no error | Constructor only reads needed args, unknowns may be ignored | Add strict input name check if rejection is required |
| `getSuppressedFields()` empty despite extra param sent | Suppression belongs primarily to property binding policy | Do not use suppressed fields as a universal unknown-field detector |
| Record's List mutated externally | Shallow immutability | Defensive copy and mutation tests |
| JSON `guest-name` not recognized | `@BindParam` is not a Jackson property annotation | Send `guestName` or design Jackson schema with `@JsonProperty` |
| `@Valid` annotation present but no error emitted | Missing provider, missing `@Valid` on argument, or validator setup | Check starter validation and MockMvc |
| `BindingResult` not populated | Placed in wrong position; different method validation path | Place immediately after model attribute, check handler signature |
| Every validation error treated as 400 client error | Return-value constraint may be a server error | Preserve HTTP status semantics |
| DTO record binds fine, but domain gets over-posted | Using `BeanUtils.copyProperties` or blindly mapping Map keys to entity | Map fields explicitly, enforce authorization in service |
| MockMvc test passes, real HTTP fails | Container/encoding/security filters differ from mock | Add real-server path tests where needed |
| Native image binding fails | Missing AOT hints for implicit model attrs | Use explicit `@ModelAttribute`, check native image hints |

## 20. Design Limitations to Remember

### 20.1. Constructor Binding Is Not Authorization

Having a valid immutable DTO does not prove the user is authorized to create a booking for a given `ownerId` or tenant. Use the authenticated principal, service policies, and domain rules. Never infer permissions from a client-supplied `role` field or enum.

### 20.2. Validation Differs from Invariants

`@Min`/`@Max` validate data at the boundary. Domain invariants such as “arrival must be before departure”, “room belongs to the same hotel”, or “guest is allowed to book this room” require dedicated business logic. If you want an invariant that cannot be violated when objects are constructed via other paths, consider checking it in a domain constructor/factory; however, throwing exceptions from a web DTO constructor can shift error handling onto an unexpected path. Separate web input parsing/validation from the domain model.

### 20.3. Data Immutability Does Not Mean Thread-Safe for Every Member

A record containing String/Integer/LocalDate and immutable nested records is safer for concurrent reads. However, a record holding a mutable List or mutable bean is not automatically thread-safe. If you need to cache or share objects across threads, carefully examine mutable fields and copy semantics.

### 20.4. Be Careful with Shared `@ModelAttribute` from Model/Session

Spring MVC can look up an existing model attribute from the model or session before constructing a new instance via constructor. If a bean was already placed in the model by a `@ModelAttribute` method or `@SessionAttributes`, the binding path may differ from always instantiating a fresh object. Test scenarios when using session/model lifecycles; do not claim every request always invokes the canonical constructor.

### 20.5. Kotlin Data Classes and Plain Java Classes

Kotlin data classes also support constructor binding, but nullability, default parameters, value classes, and validation placement follow their own rules. This lesson chose Java 17 records to keep runnable code consistent. For an ordinary Java `final` class, runtime parameter names and unambiguous constructor selection are required.

### 20.6. Native Image and Reflection

Spring MVC can handle implicit `@ModelAttribute` on the JVM, but Spring AOT/native images need hints for data binding/reflection. Using an explicit `@ModelAttribute("bookingForm")` helps the framework infer the input model better. Do not treat JVM tests as proof that a native image works; run dedicated native tests if deploying on GraalVM.

## 21. Pre-Merge Review Checklist

1. Does the request DTO contain only the required **public input fields**, with no client-supplied owner/role/approval?
2. Does the DTO use a record or a single clear data constructor?
3. Are `-parameters`/constructor parameter name metadata enabled for ordinary classes?
4. Do request field names match constructor argument names or `@BindParam`?
5. Are there nested fields? Have paths like `contact.email` been tested?
6. Is `@Valid` placed on nested objects, plus `@NotNull` if required to be present?
7. Is `@NotNull` used on wrapper types where missing must be distinguished from 0?
8. Are `@DateTimeFormat`/formatters aligned with the form's date/number contract?
9. Does the controller use an explicit `@ModelAttribute` to clarify the binding path?
10. Does `@InitBinder` target the exact attribute name?
11. If constructor-only, is `setDeclarativeBinding(true)` configured?
12. Have you avoided `setAllowedFields("*")`, which inadvertently re-enables property binding?
13. Is it understood that `allowedFields` does not restrict constructor args?
14. Are there tests with extra fields such as `approved=true` verifying whether they are ignored or rejected?
15. If the API requires rejecting unknown names, is explicit schema validation implemented?
16. Is `BindingResult` placed immediately after the model attribute if local handling is desired?
17. Is there global advice for controllers that do not accept `BindingResult`?
18. Are `FieldError.isBindingFailure()` and constraint errors distinguished?
19. Are success, missing, malformed type, constraint, and nested invalid cases tested?
20. Is the difference between Jackson JSON and form constructor binding accounted for?
21. Are request size, nested depth, List indices, and Map keys bounded?
22. Is defensive copying applied to mutable components inside records when needed?
23. Are business authorization and selective domain mapping implemented?
24. Are raw rejected values and stack traces kept out of API responses?
25. Are HTTP status codes and stable error codes asserted, not just 400?
26. Are Maven/JDK 17 compilation and exact package/file paths tested during practice?
27. Are service/database side effects tested if the API actually persists data?
28. Are demo-specific outputs distinguished from Spring's default behavior?

## 22. Extension Exercises

1. Replace the `BookingForm` record with a `final` class having only a one-arg constructor, then test `-parameters`.
2. Remove `@BindParam("guest-name")`, send both `guest-name` and `guestName` to understand the mapping.
3. Change DTO `Integer guestCount` to `int` and send a request missing that field; diagnose the result.
4. Add `@Future` on `arrival`; use a fixed clock/Validation `ClockProvider` so tests do not depend on the current date.
5. Add a nested record `Address(String city, String postalCode)`; bind `address.city`.
6. Remove `@Valid` from `contact` and prove invalid emails do not cascade.
7. Add `List<@Valid Room> rooms` and send `rooms[0].code`/`rooms[1].code`.
8. Add index and request-size limits for List; test a large index without allocating huge lists.
9. Add `Map<String,String> labels`, verify `labels[color]` is accepted while `labels[role]` cannot alter entity permissions.
10. Write a record containing a mutable List, then add defensive copying and test mutation.
11. Write `@JsonProperty("guest-name")` on a separate JSON DTO; do not assume form `@BindParam` covers it.
12. Enable class-level `@Validated` on a separate test controller to see how AOP method validation differs from MVC handler validation.
13. Create a global `@ControllerAdvice @InitBinder` applying `setDeclarativeBinding(true)`, verifying it does not break legacy property-binding forms.
14. Add a custom `DataBinder.NameResolver` for a custom naming convention and write negative tests for unexpected aliases.
15. Add an update endpoint whose model attribute comes from session to observe how its lifecycle differs from fresh construction.
16. Use `@WebMvcTest` instead of whole-context tests and import the proper binder/advice to compare against `@SpringBootTest`.
17. Add an error envelope following RFC 9457 `ProblemDetail`, keeping stable machine codes.
18. Test two violations on the same field, comparing the issue set rather than relying on provider ordering.
19. Add a custom cross-field validator for `arrival` and `departure`; preserve mapping of object-level errors.
20. Refactor the controller to pure input mapping plus a service layer, using `@MockitoBean` to assert invalid requests never invoke the service.
21. Write an integration test on a real servlet container with a UTF-8 form containing Vietnamese names.
22. Build a multi-tenant API: user from authentication, `ownerId` absent from DTO, test against over-posting.
23. Test invalid numeric types in JSON vs forms: same 400 status, different causes/exceptions.
24. Create a sample immutable class with overloaded constructors and verify which constructor Spring picks in the current version.
25. Create a native image/AOT test if deploying to GraalVM.

**Conclusion:** Spring MVC constructor binding allows building immutable DTOs without setters. With Java 17, `record` and `@BindParam` clearly define the input contract; `setDeclarativeBinding(true)` curbs unintended setter binding. However, to keep an API secure, you must **exclude privileged fields from constructors**, distinguish **binding vs validation**, check unknown inputs when the contract requires it, defensively copy mutable collections, and map DTOs to the domain behind authorization. The lesson's MockMvc/JUnit test suite verifies those behaviors directly rather than taking annotations on faith.

## 23. Official References

- [Spring Framework 6.2 — @ModelAttribute constructor binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder, declarative binding, allowedFields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — Data Binding: constructor vs property](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindParam API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)
- [Spring Framework 6.2 — MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — DateTimeFormat API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html)
- [Spring Framework 6.2 — MVC @RequestBody JSON](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Model design, security and allowed fields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Boot 3.5 — Testing MVC applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Oracle Java 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html)