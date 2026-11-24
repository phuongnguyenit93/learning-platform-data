# Limits of Annotations Before Data Is Converted to the Right Type

## 1. The Problem: Annotations Cannot Validate a Value the System Cannot Yet Read as the Target Type

In Spring Framework, HTTP input typically arrives as strings (form, query, path) or JSON. Before constraints like **@NotNull**, **@Min**, **@Past**, **@Email**, **@Valid**, or **@Validated** become meaningful, Spring must first instantiate the object and produce the required Java values. Type conversion and constraint validation are **two distinct responsibilities**.

For example, a registration application requires a minimum age of 18:

~~~java
public class RegistrationForm {
    @NotNull
    @Min(18)
    private Integer age;

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
}
~~~

With age = "17", Spring can convert the string into **Integer(17)** and Bean Validation detects a **@Min(18)** violation. With age = "abc", no **Integer** can be created from the user's input; **@Min** has no hidden integer inside "abc" to compare against. This is first and foremost a **type-conversion/binding** error (or JSON deserialization error), not a "less than 18" error.

Three false inferences to avoid:

- **@Valid is not a type converter**: it triggers validation at Spring-supported points after data has been bound onto an object.
- **@Min does not parse arbitrary malformed numeric strings**: target types and conversion mechanisms are defined separately; if conversion fails, you cannot pretend the input is a valid number to continue threshold checks.
- **@NotNull does not replace input-format checks**: if a value fails to convert, the Java field may remain null or keep a default value. Depending on how binding/validation is triggered, a null error may appear alongside the conversion error; never ignore the root cause because of that.

This lesson sits within **Input Objects** in Spring MVC. The goal is to clarify which annotation handles which responsibility, what happens when conversion fails, and how to design DTOs and error responses accurately.

## 2. Separating the Processing Phases

A common **@ModelAttribute** (form/query) flow:

~~~text
HTTP: age=abc
   │
   ▼
Spring creates/retrieves form object
   │
   ▼
WebDataBinder reads property and converts String → Integer
   ├── FAILURE → BindingResult records binding/typeMismatch error
   └── SUCCESS → assigns Integer to age property
   │
   ▼
If @Valid/@Validated applies: run validator on bound object
   │
   ▼
Controller receives object + BindingResult (if declared in right position)
   │
   ▼
Return response or execute business logic
~~~

**Note on the failure branch:** with **@ModelAttribute**, Spring may continue validating the partially bound object, yet the validator only sees its actual Java state; it cannot apply numeric constraints to the raw string "abc" as if it were an integer. A single field can carry both binding errors and related validation errors; classify them clearly.

The **@RequestBody JSON** flow differs:

~~~text
HTTP body: {"age":"abc"}
   │
   ▼
HttpMessageConverter (e.g., Jackson) reads JSON → DTO
   ├── FAILURE → HttpMessageNotReadableException; no valid DTO exists
   └── SUCCESS → DTO holds Java values
   │
   ▼
@Valid/@Validated (when present) → constraint errors may become
MethodArgumentNotValidException
   │
   ▼
Controller handles if no error halts invocation
~~~

Do not treat the exceptions above as a single category. JSON serializer coercion rules can also allow a numeric-looking string to succeed; outcomes depend on configuration. For the default examples below, the string **"abc"** cannot become an integer.

## 3. What Do Common Annotations Do, and Where Are Their Limits?

| Component | Proper Role | Limit Before Type Conversion |
| --- | --- | --- |
| **@Valid** (Jakarta Validation) | Requests validation for an object/argument at framework-supported points; triggers nested constraint checks | Does not turn "abc" into Integer, nor fix malformed JSON |
| **@Validated** (Spring) | Triggers validation and can select constraint groups (validation groups) | Still requires an instantiated object/matching input type |
| **@NotNull** | Rejects Java null values when the validator runs | Does not verify whether a raw input string has valid numeric/date syntax |
| **@Min**, **@Max**, **@Positive** | Checks numeric bounds/values on validator-supported types | Does not replace the numeric parser of the binder/Jackson |
| **@NotBlank**, **@Size**, **@Pattern** | Checks strings or types supported by each constraint | Cannot be arbitrarily applied to Integer/LocalDate; mismatched types can cause validator configuration errors |
| **@DateTimeFormat**, **@NumberFormat** | Guides formatting/parsing at Spring-supported conversion points | Conversion helpers, not constraints guaranteeing all inputs are valid |
| **@JsonFormat** | Instructs Jackson how to deserialize/serialize a JSON type in supported contexts | Does not run Bean Validation and does not repair broken JSON |
| **@ModelAttribute** | Marks data binding into a model attribute | Does not guarantee every property binds successfully |
| **@RequestBody** | Reads the request body via HttpMessageConverter into an object | Does not guarantee the body yields a validly typed object |

Modern Spring MVC also supports **method validation** for constraints placed directly on handler parameters. Depending on method signature and version, constraint errors may surface as **HandlerMethodValidationException** instead of **MethodArgumentNotValidException**. Still, a **@RequestParam Integer** parameter failing to convert from "abc" remains a type-conversion problem before numeric constraints run.

### Example Distinguishing Three Scenarios

For an **Integer age** property with **@NotNull @Min(18)**:

| HTTP Value | Conversion Result to Integer | Primary Issue |
| --- | --- | --- |
| "20" | 20 | Can proceed; satisfies constraints |
| "17" | 17 | Conversion succeeds; violates **@Min(18)** |
| "abc" | Cannot convert | Conversion/binding or JSON deserialization error |
| Empty or omitted | May become null / missing parameter depending on intake path | Check null or missing per endpoint contract |
| "18.5" | Incompatible with Integer under default converters | Conversion error; cannot explain using **@Min** alone |

Do not assume every blank input automatically triggers **@NotNull**. With **@RequestParam(required=true)**, Spring can report a missing parameter before calling the handler; with **@ModelAttribute**, the flow differs and depends on target type, editors/converters, and defaults.

## 4. Runnable Spring Boot Example: One DTO, Two Different Error Branches

This example uses **Java 17+**, **Spring Boot 3.3.5**, **Spring MVC**, and **Jakarta Bean Validation**. Versions are pinned to reproduce learning output; production applications should use supported versions and review security updates.

Create directory:

~~~text
annotation-conversion-demo/
├── pom.xml
└── src/main/java/demo/validation/ValidationLimitsApplication.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>annotation-conversion-demo</artifactId>
    <version>1.0.0</version>

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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/validation/ValidationLimitsApplication.java**:

~~~java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;

@SpringBootApplication
public class ValidationLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationLimitsApplication.class, args);
    }

    // Input DTO for both form and JSON.
    public static class AgeInput {
        @NotNull
        @Min(18)
        private Integer age;

        public AgeInput() {
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    @RestController
    public static class DemoController {

        @PostMapping(value = "/form",
                     consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                     produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> form(
                @Valid @ModelAttribute("ageInput") AgeInput input,
                BindingResult errors) {

            // Prioritize identifying type-conversion errors ahead of validation errors
            // that may accompany a partially bound object.
            boolean typeMismatch = errors.getFieldErrors("age")
                    .stream()
                    .anyMatch(FieldError::isBindingFailure);

            if (typeMismatch) {
                return ResponseEntity.badRequest().body("FORM:TYPE_MISMATCH");
            }
            if (errors.hasErrors()) {
                return ResponseEntity.badRequest().body("FORM:CONSTRAINT");
            }
            return ResponseEntity.ok("FORM:OK age=" + input.getAge());
        }

        @PostMapping(value = "/json",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.TEXT_PLAIN_VALUE)
        public String json(@Valid @RequestBody AgeInput input) {
            return "JSON:OK age=" + input.getAge();
        }
    }

    @RestControllerAdvice
    public static class DemoErrors {

        @ExceptionHandler(HttpMessageNotReadableException.class)
        public ResponseEntity<String> unreadableBody(
                HttpMessageNotReadableException ignored) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body("JSON:UNREADABLE_BODY");
        }

        @ExceptionHandler(MethodArgumentNotValidException.class)
        public ResponseEntity<String> invalidBody(
                MethodArgumentNotValidException ignored) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body("JSON:CONSTRAINT");
        }
    }
}
~~~

This is a complete application with a **main** method, not isolated snippets. **AgeInput** is a JavaBean DTO with an empty constructor and getter/setter so Spring can bind forms and Jackson can read JSON. **@NotNull** and **@Min** only take effect during the validation step.

Run from the directory containing **pom.xml** (requires JDK 17+ and Maven; first run downloads dependencies):

~~~bash
mvn spring-boot:run
~~~

Open a second terminal and run the requests below; example commands use Bash shell syntax. On PowerShell, use **curl.exe** and adjust JSON quoting for your shell.

**A. Form with wrong age type:**

~~~bash
curl -sS -X POST -d 'age=abc' http://localhost:8080/form
~~~

Expected response body and status code:

~~~text
HTTP 400
FORM:TYPE_MISMATCH
~~~

Here the binder attempts to convert **"abc"** into **Integer** and fails. **BindingResult** holds at least the corresponding binding error; the program explicitly checks **FieldError.isBindingFailure()** before other validation errors.

**B. Form with valid age type but under 18:**

~~~bash
curl -sS -X POST -d 'age=17' http://localhost:8080/form
~~~

~~~text
HTTP 400
FORM:CONSTRAINT
~~~

This time **Integer(17)** was created, and **@Min(18)** flags the invalid value.

**C. Valid form:**

~~~bash
curl -sS -X POST -d 'age=20' http://localhost:8080/form
~~~

~~~text
HTTP 200
FORM:OK age=20
~~~

**D. JSON with wrong age type:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":"abc"}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 400
JSON:UNREADABLE_BODY
~~~

Jackson cannot construct **Integer age** from that string. Spring throws **HttpMessageNotReadableException**, and the handler responds before the controller method ever receives a valid DTO to validate.

**E. JSON with valid type but underage:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":17}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 400
JSON:CONSTRAINT
~~~

The DTO was deserialized successfully; **@Valid** triggered validation and **@Min(18)** failed. In this example, Spring throws **MethodArgumentNotValidException**, which **DemoErrors** turns into a recognizable response.

**F. Valid JSON:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":20}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 200
JSON:OK age=20
~~~

The **HTTP 400/200** lines in the blocks above denote **status codes**, not body output printed by curl with **-sS**. To see actual headers/status, add **-i**; the body lines are fixed strings from the source. If the server uses a different port or Jackson configuration, adjust commands and expectations accordingly.

## 5. Why Must BindingResult Be in the Right Position?

On the form branch, the data-receiving parameter and error-receiving parameter must sit next to each other:

~~~java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

This is an **illustrative snippet inside an MVC controller with views**, requiring **RegistrationForm** and matching views; it is not a standalone program.

If **BindingResult** is not placed immediately after **@ModelAttribute**, Spring MVC may throw an exception instead of passing errors to the controller to handle. Conversely, with **BindingResult** present, you can inspect structured errors:

~~~java
for (FieldError fieldError : result.getFieldErrors()) {
    String field = fieldError.getField();
    boolean conversionFailed = fieldError.isBindingFailure();
    String code = fieldError.getCode();

    // "typeMismatch" is a common binding error code.
    // Constraint codes may be "Min", "NotNull", ...
    // Never return verbatim internal errors or sensitive values to the client.
}
~~~

**getFieldError("age")**, **getFieldErrors("age")**, **hasFieldErrors("age")**, and **isBindingFailure()** clearly distinguish:
- binding errors: data could not be assigned to the property; typically coded **typeMismatch**;
- validation errors: the object/value already has its Java type but violates a constraint, such as **Min**.

Do not assume there is only one error per field. After binding fails, validation can still flag issues on the remaining Java state (e.g., null), so prioritize reporting syntax/conversion errors first if that is the root cause. Use **getDefaultMessage()** directly only in appropriate internal logs after checking for sensitive content; public APIs should expose stable error codes and user-friendly messages.

## 6. `@RequestParam` and `@PathVariable` Have Different Error Paths

A direct parameter without a DTO:

~~~java
@GetMapping("/adult")
public String adult(@RequestParam @Min(18) Integer age) {
    return "accepted";
}
~~~

The snippet above illustrates a handler signature, requiring matching imports and method-context validation configuration. When a user sends **?age=abc**, Spring must convert **String** to **Integer** to invoke the method. If conversion fails, **MethodArgumentTypeMismatchException** typically occurs, with Spring Boot's default body depending on configuration. The **@Min(18)** constraint never gets a chance to compare age against 18 when the Java argument cannot even be created. If **?age=17** is sent, threshold checking depends on whether method validation is enabled and how Spring MVC is configured; in Spring Framework 6.1+, built-in support can use **HandlerMethodValidationException** for constraints directly on handler parameters.

Likewise, a **@PathVariable UUID id** receiving a malformed UUID string fails during conversion before the controller runs. Do not apply a single error-catching assumption across form objects, JSON bodies, query parameters, and path variables.

## 7. To Check Formatting Before Type Conversion, Preserve Raw Input

If the product truly needs specialized messages for **"abc"**, **"1.5"**, strings with separators, or non-matching date formats, there are two clear paths:

**Option 1 — Let the framework convert types and handle conversion errors.** The DTO uses **Integer**, **LocalDate**, or a domain type, configures appropriate Converters/Formatters, and handles binding/deserialization errors with accurate messages. This fits when input formats are simple, standard, and preserving exact user representation is unnecessary.

**Option 2 — Accept raw strings and validate syntax before parsing.** The input DTO declares a **String rawAge** field, places String-compatible constraints or an object-level validator on it, and only parses into **Integer**/domain type in the processing layer after format validation passes. This helps when there are many granular error cases or custom domain formats. The standalone **Java 17** example below illustrates the sequence without depending on Spring:

~~~java
public class ParseAfterCheck {
    static int parseAge(String raw) {
        if (raw == null || !raw.matches("[0-9]{1,3}")) {
            throw new IllegalArgumentException("age must be 1-3 digits");
        }
        int age = Integer.parseInt(raw);
        if (age < 18) {
            throw new IllegalArgumentException("age must be at least 18");
        }
        return age;
    }

    public static void main(String[] args) {
        for (String input : new String[] {"abc", "17", "20"}) {
            try {
                System.out.println(input + " -> " + parseAge(input));
            } catch (IllegalArgumentException exception) {
                System.out.println(input + " -> " + exception.getMessage());
            }
        }
    }
}
~~~

Save as **ParseAfterCheck.java**, then run:

~~~bash
javac ParseAfterCheck.java
java ParseAfterCheck
~~~

Exact output:

~~~text
abc -> age must be 1-3 digits
17 -> age must be at least 18
20 -> 20
~~~

This program separates **checking the String representation** from **Integer.parseInt**, and separates threshold checks after parsing. In Spring MVC, you can apply the same idea using a String DTO + Bean Validation such as **@Pattern** (if regex fits the contract) followed by mapping to domain types; there is no need to force **@Pattern** onto an Integer property.

Note on example scope: the regex accepts only 1–3 ASCII digits per the hypothetical contract; real systems must explicitly decide whitespace, negative numbers, Unicode digits, length, bounds, and error formatting. Increasing input length or loosening the regex can lead to numbers exceeding Integer limits, which still require parse error handling. Raw input is untrusted: enforce request length limits and never log sensitive values.

## 8. Choosing the Right Tool for Each Responsibility

| Need | Suggested Mechanism | Reason |
| --- | --- | --- |
| Form/query needs String → number, date, or domain type conversion | **ConversionService**, **Converter**, **Formatter**, **PropertyEditor** at appropriate scope | Handles representation and target type at the binding point |
| Declare date/time format for Spring binding | **@DateTimeFormat** and matching formatter | Supports parsing date types at the right conversion point |
| Read JSON into DTO | **HttpMessageConverter/Jackson**, custom deserializer when needed | Resolves JSON structural and data-type errors |
| Verify an existing Integer is ≥ 18 | **@Min(18)**, **@Valid** | Validates values once the proper type exists |
| Check non-blank string or pattern match | **@NotBlank**, **@Pattern** on supported types | Appropriate when data stays as String for inspection |
| Check cross-field/domain rules | Class-level validator, custom constraint, business layer | Requires multi-field context or application state |
| Report per-field form errors | **BindingResult** after **@ModelAttribute** | Retains both binding and validation errors |
| Report unreadable JSON body | Handle **HttpMessageNotReadableException** | No properly typed DTO exists to validate constraints against |
| Report unconvertible URL parameter | Handle **MethodArgumentTypeMismatchException** and variants | Handler argument never received a Java value |

A **Converter<String, SomeType>** can include its own normalization and parsing per target type contract. However, never expect **@Valid** or **@Min** to invoke an arbitrary converter to rescue an invalid input string.

## 9. Designing API Errors by Phase Rather Than by Annotation

An application should help callers distinguish:

- **INPUT_MALFORMED**: JSON body has invalid syntax or cannot be read/deserialized.
- **TYPE_MISMATCH**: parameter/field value cannot convert to the declared type.
- **CONSTRAINT_VIOLATION**: data has the right type but violates a constraint.
- **BUSINESS_RULE**: value is syntactically valid yet conflicts with context-dependent business rules.

Example response design for form age="abc" (illustrative JSON, not output of the sample app):

~~~json
{
  "code": "TYPE_MISMATCH",
  "field": "age",
  "message": "Age must be an integer.",
  "status": 400
}
~~~

With age="17" after conversion to Integer:

~~~json
{
  "code": "CONSTRAINT_VIOLATION",
  "field": "age",
  "message": "Age must be at least 18.",
  "status": 400
}
~~~

Keep error formats consistent with your API contract and test each branch; **HTTP 400** is often suitable for client input errors, while applications must follow their published error conventions. Never return stack traces, internal class names, entire raw payloads, or password values. For structurally broken JSON, a reliable field name may not even exist; do not guess a field name when the parser could not identify one.

## 10. Common Mistakes

1. **"Adding @Valid will fix age=abc."** Wrong: **@Valid** triggers validation; it does not convert strings into numbers.
2. **"Using @Min(18) is enough to catch every invalid age input."** Wrong: there are still conversion errors, missing data, and raw formatting issues; phase ordering determines error kind.
3. **"No @Min error means age is valid."** Wrong: an Integer may never have been created, validation may not have run, or a binding error occurred earlier.
4. **"@NotNull always produces one single error when parsing fails."** Wrong: null is a Java state; Spring can record separate binding and validation errors, or fail immediately during deserialization.
5. **"Putting @Pattern on Integer to validate digits."** Wrong target data type. Place compatible constraints on a raw **String**, or let converters report parse errors.
6. **"Form and JSON using the same @Valid produce the same exception."** Wrong: WebDataBinder and Jackson fail at different points; behavior also depends on handler signatures.
7. **"Catching every exception and returning 'underage'."** Wrong: misleading messages mask real bugs. Separate unreadable payloads, unconvertible types, and constraint violations.
8. **"Lenient type coercion is always helpful."** Wrong: silently stripping extra characters, rounding, or altering formats can turn bad input into unintended values. Normalize only according to a published contract.
9. **"Using domain entities directly for all requests is most convenient."** Risk: binding attributes the application never wanted clients to edit. Use tightly scoped input DTOs and map to business models only after checks pass.

## 11. Practical Checklist and Exercise

When an annotation seems "not to work", walk through step by step:

1. **Trace where data arrives**: **@ModelAttribute**, **@RequestBody**, **@RequestParam**, **@PathVariable**, or a manual binder call?
2. **Check the declared type** of the Java field, the raw input, and registered converters/deserializers.
3. **Identify which phase failed**: body reading, conversion/binding, Bean Validation, or business rules?
4. **Verify validation activation**: **@Valid/@Validated**, validator provider, constraints placed on compatible types, and method validation if constraints are directly on handler parameters.
5. **Check the right error channel**: **BindingResult** right after the bound argument, or exception handlers for JSON/query/path.
6. **Test at least three input groups**: wrong type (age=abc), right type violating constraint (age=17), valid for both (age=20).
7. **Classify and expose stable errors**; keep sensitive raw values out of responses and public logs.

Extension exercise: add a **LocalDate birthday** field with birth-date rules, then send **birthday=hello**, a validly formatted date in the future, and a valid date. Predict for each case whether the error occurs in the **conversion phase** or the **validation phase**, then verify with **@ModelAttribute** followed by JSON **@RequestBody**. Configure formatting for each branch before drawing conclusions; do not assume Jackson and Spring Formatters share the same policy.

## References

- Spring Framework Reference – [Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html).
- Spring Framework Reference – [Java Bean Validation and DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
- Spring Framework Reference – [@ModelAttribute in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).
- Spring Framework Reference – [@RequestBody in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- Spring Framework Reference – [Type Conversion for Handler Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- Spring Framework Reference – [Validation on Controller Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).

**Principle to remember:** annotations check constraints on data that the framework has already represented in the appropriate type; when type conversion or body reading fails, diagnose and handle that exact phase. Never turn a format error into a business error simply because an annotation never received the value it needed.