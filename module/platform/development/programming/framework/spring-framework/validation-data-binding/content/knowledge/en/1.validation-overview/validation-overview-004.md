# Vocabulary map: target, property, binder, converter, and validator

In Spring Framework, **data binding** is the process of populating input data (typically strings from a form/request) into a strongly typed Java object. To read source code accurately and handle errors properly, you need to distinguish five roles: **target** is the object receiving data; **property** is the destination slot for data; **binder** coordinates value assignment; **converter** converts types; **validator** checks validity rules. `BindingResult` stores errors arising from binding/type conversion and from validation.

## 1. Overall diagram and a running example

Suppose a registration form submits these name–value pairs:

```text
name  = "An"
age   = "16"
level = "advanced"
```

The intended receiving object is `SignupForm`, with `name: String`, `age: int`, and `level: Level`. Conceptual flow:

```text
Input (property name -> raw value)
                |
                v
       DataBinder / WebDataBinder ----------------------+
                |                                      |
      locate property on target                        |
                |                                      |
       convert type if needed                          |
                |                                      |
    ConversionService / Converter / Formatter          |
                |                                      |
                v                                      |
         assign to target                              |
                |                                      |
      call validate() or @Valid/@Validated             |
                |                                      |
       Validator / Bean Validation                     |
                |                                      |
                v                                      v
       target holds bound values              BindingResult holds errors
```

This is a **responsibility map**, not a claim that every request always runs sequentially through every box. For example, validation must be requested/triggered; type conversion may not be needed if the input already has the right type; a conversion error may leave a property unassigned. In Spring MVC, creating/obtaining the target may happen via constructor binding or property binding depending on the case.

| Term | Essence | Example with the form | Question it answers |
| --- | --- | --- | --- |
| **Target** | The Java object receiving binding results | An instance of `SignupForm` | "Which object does the data go into?" |
| **Property** | An attribute accessible/assignable by path | `name`, `age`, `level` | "Where on the object does this value belong?" |
| **Binder** | Component coordinating mapping, assignment, and error recording | `DataBinder`; on the web, `WebDataBinder` | "Who performs putting inputs into the target?" |
| **Converter** | Component converting a value from source type to target type | `String -> Level`, `String -> Integer` | "How does the input value become the right Java type?" |
| **Validator** | Component evaluating validity conditions | `age >= 18`, `name` non-empty | "Does the existing value satisfy the rules?" |

**Quick distinction:** converter answers "can `"16"` be turned into the number 16?"; validator answers "does 16 meet the minimum age of 18?". A value can be **the right type yet fail validation rules**.

## 2. Target: destination object, not synonymous with entity

`Target` is the instance the binder is processing, e.g., `new SignupForm()`. It can be a form object, DTO, command object, or an object used in another layer; it does not have to be a JPA entity, is not a database table name, and is not an HTTP request.

```java
public class SignupForm {
    private String name;
    private int age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
```

This is a **class definition snippet**, not a self-running program. For a mutable JavaBean like the one above, the binder normally performs property binding via property accessors. In constructor binding, Spring creates the target via a matching constructor and passes values to constructor parameters; a `record` can also serve as a form object.

**Safe design:** for untrusted HTTP data, prefer DTOs containing only permitted input fields or immutable objects with an explicitly designed constructor. Avoid binding directly onto an entire entity containing sensitive fields such as `role`, `isAdmin`, `price`, or `ownerId`. Validation alone does not prevent unintended assignment (*mass assignment*).

## 3. Property: path name for the binder to locate a value

A property is a data-receiving point on the target, usually following JavaBeans conventions: `getX()/setX(...)` or `isX()` for booleans. For instance, `age` corresponds to `getAge()/setAge(int)`. A `private` field does not automatically mean a bindable property; the binder needs an appropriate access path. Spring also supports direct field access when explicitly configured, such as via `DataBinder.initDirectFieldAccess()`.

Some input names:

| Input name | Meaning |
| --- | --- |
| `name` | Simple property on the root object |
| `address.city` | Nested property: `target.getAddress().getCity()/setCity(...)` via the appropriate access mechanism |
| `items[0].quantity` | Property of the list element at index 0 |
| `settings[theme]` | Map entry under key `theme`, if the target structure supports it |

Spring supports nested/indexed paths, but instantiating intermediate objects and growing collections depends on the target structure and binder configuration. **A property is not a database column, not an annotation, and not an "arbitrary attribute" that clients are free to invent.**

It helps to distinguish three more terms:

- **Input name**: the incoming key, e.g., `age` in the request.
- **Property name/path**: the path the binder understands on the target, e.g., `age` or `address.city`.
- **Property value**: the actual value after type conversion, e.g., `int 16`.

The input name may match the property name, yet not every input name is valid or allowed to be bound.

## 4. Binder: coordinator, not converter/validator

`org.springframework.validation.DataBinder` takes a target and `PropertyValues` input, identifies bindable properties, assigns them with type conversion when needed, and collects errors via `BindingResult`. `org.springframework.web.bind.WebDataBinder` extends this mechanism for web contexts. In Spring MVC, the framework uses a binder per request and allows configuring it via `@InitBinder`.

Programmatically, the typical sequence is:

```java
DataBinder binder = new DataBinder(target, "signupForm");
binder.setConversionService(conversionService);
binder.setValidator(validator);

binder.bind(inputValues);     // Bind + convert types + binding errors if any.
binder.validate();            // Explicitly run configured validators.
BindingResult result = binder.getBindingResult();
```

This snippet illustrates **API call order**; `target`, `conversionService`, `validator`, and `inputValues` must be declared. Section 7 has a complete program.

Key points:

1. `bind(...)` and `validate()` are two distinct operations in the `DataBinder` API. Merely creating a binder or calling only `bind` does not mean validators have run.
2. If a value cannot be converted to the property type, the binder can record a `FieldError` (commonly with code `typeMismatch`); that property is not necessarily updated. Do not assume every error throws an exception immediately.
3. `BindingResult` is the **result** holding binding/validation errors, not a component that performs conversion or checks rules itself.
4. A binder has settings such as `setAllowedFields(...)` and `setDisallowedFields(...)` for **property binding**. For web input, restrict allowed fields; an allowed-fields list does not replace designing appropriate DTOs/constructor binding.
5. `@InitBinder` configures the binder per controller/applicable scope; it is not the place to put all business validation.

## 5. Converter: converts data types, does not judge business validity

`org.springframework.core.convert.converter.Converter<S, T>` is an interface for converting from `S` to `T`, e.g., `String` to enum `Level`. Converters are registered in a `ConversionService`; Spring already provides many common conversions (strings to numbers, enums, etc.).

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

enum Level { BASIC, ADVANCED }

class LevelConverter implements Converter<String, Level> {
    @Override
    public Level convert(String value) {
        return Level.valueOf(value.trim().toUpperCase(Locale.ROOT));
    }
}
```

This is an **illustrative class snippet in a Spring project**, not a complete standalone Java file. `"advanced"` becomes `Level.ADVANCED`. The value `"unknown"` does not map to this enum and causes a type conversion error; handling binding failures is the responsibility of the binder/`BindingResult`. A converter does not decide whether that level is permitted for the current user.

| Converter-related concept | When to use |
| --- | --- |
| `Converter<S,T>` | A deterministic type conversion, not tied directly to business rules |
| `ConversionService` | Central entry point to look up/run converters and related conversion mechanisms |
| `Formatter<T>` | Parse/print values for UI, often involving `Locale` such as dates or currency |
| `PropertyEditor` | Older JavaBeans mechanism that Spring still supports; for new code, usually prefer `ConversionService`/`Formatter` |

For example, whether `"2,5"` means 2.5 or a parse error depends on locale conventions and formatters—do not assume the default converter understands every format. Also avoid using converters to query databases or check access permissions when a service/validator belongs there.

## 6. Validator: checks rules after values exist

Spring provides the `org.springframework.validation.Validator` interface:

- `supports(Class<?> clazz)` determines whether the validator supports the target type.
- `validate(Object target, Errors errors)` checks rules and records errors via `errors.rejectValue(...)` or `errors.reject(...)`.

Common error categories:

| Situation | Where detected | Example |
| --- | --- | --- |
| Cannot convert type | Binding/conversion stage | `age="abc"` cannot become `int`; typically records `typeMismatch` |
| Right type, violates field constraint | Validator/Bean Validation | `age=16` on a form requiring minimum 18 |
| Violates cross-field rule | Appropriate validator/service | `startDate` must precede `endDate` |
| Property name disallowed | Binder configuration / DTO design | Client sends extra `isAdmin=true` |
| Business operation fails | Business layer, not inherently a bind error | Out of stock, duplicate transaction, insufficient permissions |

Besides Spring `Validator`, applications commonly use **Jakarta Bean Validation** such as `@NotBlank`, `@Min`, `@Email`, triggered via `@Valid` or `@Validated` with a compatible provider (in Spring Boot, typically adding `spring-boot-starter-validation`). `@Valid` does not perform type conversion; it triggers validation in supported contexts. Constraint annotations do not replace authorization checks, transactions, or domain-layer invariants.

## 7. Runnable Java 17+ example: all five components

The following example uses Spring Framework **6.2.12** to clearly show the binder, converter, validator, and errors. This is a minimal Maven project; no web server is needed.

Create the structure:

```text
binding-vocabulary/
├── pom.xml
└── src/main/java/BindingVocabularyDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>binding-vocabulary</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/BindingVocabularyDemo.java`:

```java
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BindingVocabularyDemo {
    enum Level { BASIC, ADVANCED }

    public static class SignupForm {
        private String name;
        private int age;
        private Level level;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public Level getLevel() { return level; }
        public void setLevel(Level level) { this.level = level; }
    }

    public static class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return SignupForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            SignupForm form = (SignupForm) target;
            if (form.getName() == null || form.getName().isBlank()) {
                errors.rejectValue("name", "name.required", "Name must not be blank");
            }
            if (form.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung", "Age must be at least 18");
            }
        }
    }

    public static void main(String[] args) {
        SignupForm target = new SignupForm();
        DataBinder binder = new DataBinder(target, "signupForm");

        DefaultConversionService conversions = new DefaultConversionService();
        conversions.addConverter(String.class, Level.class,
                raw -> Level.valueOf(raw.trim().toUpperCase(Locale.ROOT)));
        binder.setConversionService(conversions);
        binder.setValidator(new SignupValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "An");
        input.add("age", "16");
        input.add("level", "advanced");

        binder.bind(input);
        binder.validate();
        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + target.getName());
        System.out.println("age=" + target.getAge());
        System.out.println("level=" + target.getLevel());
        System.out.println("errorCount=" + result.getErrorCount());
        System.out.println("ageError=" + (result.getFieldError("age") != null));
    }
}
```

Run from the `binding-vocabulary` directory (requires JDK 17+ and Maven; downloads dependencies on first run):

```bash
mvn -q compile exec:java -Dexec.mainClass=BindingVocabularyDemo
```

Expected stdout:

```text
name=An
age=16
level=ADVANCED
errorCount=1
ageError=true
```

**Explanation across the five terms:**

1. `target` is the `SignupForm` instance created before binding.
2. `property` refers to `name`, `age`, `level`; the JavaBeans setters provide the assignment paths.
3. `binder` is `DataBinder`; `bind(input)` populates data into the target.
4. `converter` for `String -> Level` turns `"advanced"` into `ADVANCED`; `"16"` is converted by the default type conversion mechanism into `int 16`.
5. `validator` rejects age 16. `BindingResult` records a `FieldError` for `age` even though the number 16 was successfully bound.

Changing `input.add("age", "16")` to `"20"` makes the age error disappear (keeping the other inputs unchanged). Changing it to `"abc"` can produce a `typeMismatch` error during binding; do not extrapolate the error count or post-failure field value from the `"16"` example.

## 8. Connection to Spring MVC: who creates the binder and when does validation run?

In a controller using `@ModelAttribute`, Spring MVC can create or retrieve the model attribute, bind request data into the object, and trigger validation when `@Valid`/`@Validated` is present. Placing `BindingResult` **immediately after** the model attribute parameter lets the controller handle errors.

```java
// Snippet placed in a Spring MVC application with Bean Validation dependency.
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

record RegisterRequest(@NotBlank String name, @Min(18) int age) {}

@Controller
class RegisterController {
    @PostMapping("/register")
    String submit(@Valid @ModelAttribute("form") RegisterRequest form,
                  BindingResult errors) {
        if (errors.hasErrors()) {
            return "register-form";
        }
        return "register-success";
    }
}
```

This is a **Spring MVC integration snippet**, not the standalone program from Section 7; the view names assume the project has configured the corresponding view resolver/templates. With a `record`, Spring can use constructor binding. If `BindingResult` is omitted when validation fails, the exception and response depend on the Spring MVC handling branch (e.g., `MethodArgumentNotValidException` for argument validation, or `HandlerMethodValidationException` in method validation scenarios); do not assume every error produces one single exception type.

Distinguish:

- `@ModelAttribute`: suitable for binding parameters/forms into a model object; directly involves `WebDataBinder`.
- `@RequestBody`: JSON data is typically deserialized into an object by a message converter (e.g., Jackson) first; validation with `@Valid` can run, but **do not equate JSON deserialization with `@ModelAttribute` property binding**.
- `@InitBinder`: configures the binder for controller/advice scope, e.g., registering validators or restricting fields on mutable forms.
- `BindingResult`/`Errors`: holds error information and must be placed in the proper position in the method signature when handling errors for that argument.

Configuration example for a mutable form (unlike the record above):

```java
@InitBinder("signupForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "level");
}
```

This is an **illustrative method snippet inside a controller**: it requires importing `org.springframework.web.bind.annotation.InitBinder` and `org.springframework.web.bind.WebDataBinder`. `setAllowedFields` restricts **property binding**; do not treat it as the sole way to control constructor binding or a substitute for DTOs/authorization checks.

## 9. Common confusions and how to diagnose them

| Symptom | Check first | How to verify |
| --- | --- | --- |
| Property does not receive a value | Input name, getter/setter, nested path, allowed fields | Confirm the path is right and the target has an appropriate access path |
| `age="abc"` fails to bind to a number | Conversion + `BindingResult` | Inspect `FieldError`, `typeMismatch` code, and rejected value |
| `age=16` binds but is rejected | Validator/constraints | Look for `@Min`, `rejectValue`, and related rules |
| `"advanced"` does not become enum | Converter/ConversionService | Verify the converter is registered, parse rules, and casing |
| Validation errors do not appear | Validation trigger mechanism | Check `binder.validate()` or `@Valid`/`@Validated` and provider |
| Client can modify unwanted fields | Target design and property binding scope | Use proper DTOs, constructor binding, or allowed fields |
| Controller does not see errors in `BindingResult` | Method signature | Place `BindingResult` immediately after the corresponding argument, check binding type |

A systematic debugging path goes from **input name/raw value → property path → target type → conversion → assignment → validation → BindingResult**. For example, on `typeMismatch`, fix the converter/input format; on `@Min`, fix the data or validation rule; on unintended bound fields, fix the target contract and field restrictions rather than "patching" it in a converter.

## 10. Self-check

**Scenario A:** `age="twenty"`, target declares `int age`. Which component should be examined first? **Conversion/binding**. You cannot conclude an "under 18" error from this string alone.

**Scenario B:** `age="17"` converts to `int 17`, while the application requires users to be at least 18. Which component is responsible? **Validator**. Type conversion has already succeeded.

**Scenario C:** A client sends `isAdmin=true` even though the screen only has `name` and `age`. What issue is this? **Allowed bindable property scope and target design**, which should be constrained via appropriate DTOs/constructors/allowed fields; `@NotNull` or converters are not access-control measures.

**Scenario D:** A `DataBinder` has a converter and validator configured, but only `binder.bind(values)` is called. Is validation guaranteed to have run? **No**; with direct API usage, you must call `binder.validate()` to run the configured validator.

**Final takeaway:** *target* is "who receives", *property* is "where it is received", *binder* is "who coordinates", *converter* is "what type to convert to", *validator* is "is it valid"; *BindingResult* is "where errors are recorded".

## Official references

- [Spring Framework – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework – Java Bean Validation / DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework – MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
