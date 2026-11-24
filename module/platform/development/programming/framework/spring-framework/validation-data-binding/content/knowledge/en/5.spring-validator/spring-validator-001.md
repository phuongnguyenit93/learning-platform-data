# The org.springframework.validation.Validator Contract in Spring Framework

**org.springframework.validation.Validator** is the contract for validating a Java object against application-defined rules. It is independent of HTTP: the same validator can be invoked in Spring MVC, in a service, in a batch job, or in plain Java code. Instead of returning **true/false**, the validator records violations in an **Errors** object provided by the caller.

At the core of the contract are two questions: **"What type of object does this validator support?"** and **"Which rules does the target object violate?"**. The two methods **supports(Class<?>)** and **validate(Object, Errors)** answer these respectively. This is what distinguishes it from Data Binding: binding converts data into an object; a validator validates the object and records errors.

## 1. Contract Signatures and Semantics

Two abstract methods must be implemented:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);

    // Spring Framework 6.1+ also includes the default method validateObject(Object).
}
~~~

The snippet above shows the **two required methods**, not a full copy of the interface source. Starting from Spring Framework 6.1, there is also the default method **validateObject(Object)** to validate an object standalone; older applications can still use **validate(Object, Errors)**.

| Component | Input | Result | Meaning |
| --- | --- | --- | --- |
| **supports(Class<?> clazz)** | Candidate class to check | **boolean** | **true** if the validator can validate instances of that class |
| **validate(Object target, Errors errors)** | Target object and error collector | **void** | Validates and registers errors in **Errors**, without returning a boolean result |
| **Errors** | Validation state, object name, property path, and existing errors | Can inspect **hasErrors()**, field/global errors | Destination for storing validation results |
| **validateObject(Object target)**, since Spring 6.1 | Object to validate | **Errors** | Default convenience method for validating outside a DataBinder |

**supports(...)** is typically written as follows:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return EventPeriod.class.isAssignableFrom(clazz);
}
~~~

The expression above evaluates to true when **clazz** is **EventPeriod** or one of its subclasses. For **String.class** or an incompatible type, the result is **false**. If the validator should only allow one exact class and intentionally reject subclasses, **EventPeriod.class.equals(clazz)** can be used. Choose an approach consistent with the cast and the actual scope of the rules.

**validate(...)** has important responsibilities:

1. Accept a **target** of a type accepted by **supports(...)**; the caller must ensure the type is appropriate. If called directly with the wrong type, the cast in the implementation may cause a **ClassCastException**. The utility **ValidationUtils.invokeValidator(...)** checks **supports** before invoking.
2. Evaluate all relevant rules; record errors using **errors.rejectValue(...)** (property errors) or **errors.reject(...)** (object-wide errors).
3. Preserve error information already in **Errors**. In a binding flow, **Errors** may already contain **typeMismatch** before the validator runs. Do not create a new **Errors** instance and lose those errors.
4. Do not treat ordinary invalid values as program exceptions. Invalid input values should become **ObjectError/FieldError** entries so the calling layer can decide how to respond. Exceptions should be reserved for actual programming, configuration, or system errors.
5. Avoid mutating **target**, and avoid database updates, API calls, or side effects inside the validation method. Validators are often reused, so avoid storing request state in validator fields.

**The contract does not run automatically** just because a class implements **Validator**. Something must invoke **validate(...)**, **validateObject(...)**, or a configured mechanism must instruct Spring to call it.

## 2. Understanding Errors, FieldError, and ObjectError

The **Errors** interface is the channel for exchanging results between a validator and its caller. It can carry both errors from the binding step and errors explicitly added by the validator.

- **errors.rejectValue("title", "title.required", "Title is required")**: adds an error for the **title** property, with an error code and a default message.
- **errors.reject("period.invalid", "Start date must not follow end date")**: adds an object-wide error; used when a constraint involves multiple properties or does not belong to a single field.
- **errors.hasErrors()** and **errors.getErrorCount()**: determine whether there are errors and the total error count.
- **errors.getFieldErrors()**, **errors.getGlobalErrors()**, **errors.getFieldError("title")**: retrieve the needed kinds of errors.
- **errors.getObjectName()**: logical name of the object being validated, for example **eventPeriod**.

**FieldError** represents an error on a single property and can carry the field name, rejected value, error codes, and binding-failure flag. **ObjectError** represents an object-level error; **FieldError** is a specialized form of **ObjectError**. **BindingResult** extends **Errors** and adds target/binding information so Spring MVC can render forms, inspect raw values, or track suppressed fields.

For example, with an event period whose **title** is a blank string and **startDate** is later than **endDate**:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "title", "title.required", "Title is required");

errors.reject(
        "period.invalid", "Start date must not follow end date");
~~~

The **title.required** error is a **field error**. The **period.invalid** error is a **global error**. An object can have both at the same time. **ValidationUtils.rejectIfEmptyOrWhitespace** checks for **null**, empty strings, or whitespace-only strings through **Errors**; it does not replace type checks or other logic.

**Error codes** such as **title.required** are message keys so the application can internationalize messages via **MessageSource** and **messages*.properties** files. Spring can generate more specific codes prefixed with the object/field name and then fall back to general codes, depending on the **MessageCodesResolver**. **defaultMessage** is a fallback option; avoid hard-coding full Vietnamese/English sentences everywhere if the product needs multi-language support.

Example **messages_vi.properties** file in an application:

~~~properties
title.required=Vui lòng nhập tiêu đề.
period.invalid=Ngày bắt đầu không được muộn hơn ngày kết thúc.
~~~

Each presentation/API layer can map error codes to messages according to the locale. **validate(...)** only registers errors; it does not decide the HTML template, JSON response, or HTTP status.

## 3. Standalone Java 17+ Example Without Spring MVC

Example validating an **EventPeriod** consisting of a title, start date, and end date. Rules:

- Title must not be missing or contain only whitespace.
- Both dates must have values.
- Start date must not be after end date; this is an object-level error because it involves both properties.

The program calls **ValidationUtils.invokeValidator** directly to demonstrate the contract without starting a web server. Create the structure:

~~~text
spring-validator-contract/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ContractDemo.java
~~~

**pom.xml** (Spring Framework 6.2.10, JDK 17 or later):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-validator-contract</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ContractDemo.java**:

~~~java
package demo;

import java.time.LocalDate;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class ContractDemo {

    public static void main(String[] args) {
        Validator validator = new EventPeriodValidator();

        EventPeriod invalid = new EventPeriod(
                "   ",
                LocalDate.of(2026, 11, 20),
                LocalDate.of(2026, 11, 10));

        Errors errors = new BeanPropertyBindingResult(invalid, "eventPeriod");
        ValidationUtils.invokeValidator(validator, invalid, errors);

        System.out.println("supports(EventPeriod) = "
                + validator.supports(EventPeriod.class));
        System.out.println("supports(String) = "
                + validator.supports(String.class));
        System.out.println("invalid.hasErrors = " + errors.hasErrors());
        System.out.println("invalid.fieldErrorCount = "
                + errors.getFieldErrorCount());
        System.out.println("invalid.globalErrorCount = "
                + errors.getGlobalErrorCount());

        EventPeriod valid = new EventPeriod(
                "Workshop",
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 20));
        Errors validErrors = new BeanPropertyBindingResult(valid, "eventPeriod");
        ValidationUtils.invokeValidator(validator, valid, validErrors);
        System.out.println("valid.hasErrors = " + validErrors.hasErrors());
    }

    public static final class EventPeriod {
        private String title;
        private LocalDate startDate;
        private LocalDate endDate;

        public EventPeriod() {
        }

        public EventPeriod(String title, LocalDate startDate, LocalDate endDate) {
            this.title = title;
            this.startDate = startDate;
            this.endDate = endDate;
        }

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }

        public LocalDate getEndDate() {
            return endDate;
        }

        public void setEndDate(LocalDate endDate) {
            this.endDate = endDate;
        }
    }

    public static final class EventPeriodValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return EventPeriod.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            EventPeriod period = (EventPeriod) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "title", "title.required", "Title is required");

            if (period.getStartDate() == null) {
                errors.rejectValue(
                        "startDate", "start.required", "Start date is required");
            }
            if (period.getEndDate() == null) {
                errors.rejectValue(
                        "endDate", "end.required", "End date is required");
            }

            if (period.getStartDate() != null
                    && period.getEndDate() != null
                    && period.getStartDate().isAfter(period.getEndDate())) {
                errors.reject(
                        "period.invalid",
                        "Start date must not follow end date");
            }
        }
    }
}
~~~

In the directory containing **pom.xml**, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContractDemo
~~~

Six lines produced by **System.out.println** in the program, in order:

~~~text
supports(EventPeriod) = true
supports(String) = false
invalid.hasErrors = true
invalid.fieldErrorCount = 1
invalid.globalErrorCount = 1
valid.hasErrors = false
~~~

Explanation: the **invalid** object violates two independent rules: whitespace-only **title** produces one field error; **startDate > endDate** produces one global error. The **valid** object produces no errors. The **validate(...)** method does not return **false** or throw an exception for these two normal violations; the caller inspects **Errors**. Note that the stdout lines are the output of the example code, excluding environment-dependent Maven messages.

You can call **validator.validate(invalid, errors)** directly instead of **ValidationUtils.invokeValidator(...)** when you have already ensured the target has a suitable type. However, **invokeValidator** checks compatibility via **supports(...)** and is a convenient choice when an application has multiple validators.

### Concise Invocation with validateObject(...) in Spring 6.1+

Starting with Spring Framework 6.1, the **Validator** interface provides a **default method**:

~~~java
Errors result = new ContractDemo.EventPeriodValidator()
        .validateObject(new ContractDemo.EventPeriod(
                "Workshop",
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 20)));

System.out.println(result.hasErrors()); // false
~~~

This snippet is used inside a Java method that imports **Errors** and **LocalDate**. This approach is useful when you do not need to attach the validator to a DataBinder; Spring codebases older than 6.1 must continue providing an **Errors** object per the two-parameter contract.

## 4. How Is a Validator Triggered by DataBinder?

**DataBinder** is responsible for mapping values from a data source onto a target and can invoke registered validators. Distinguish the two steps:

~~~text
Data source (form / property Map / HTTP request)
    |
    v
DataBinder.bind(...)              --> converts/populates properties, may produce binding errors
    |
    v
DataBinder.validate(...)          --> runs configured validators
    |
    v
BindingResult / Errors            --> stores both binding and validation errors
    |
    v
Caller checks hasErrors()         --> decides response or further processing
~~~

If you only call **bind(...)** without calling **validate(...)** or using an MVC mechanism that triggers validation, you cannot assume the custom validator has run.

Example invocation without HTTP, assuming **period** is an **EventPeriod** instance from the example above:

~~~java
DataBinder binder = new DataBinder(period, "eventPeriod");
binder.addValidators(new EventPeriodValidator());
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    result.getAllErrors().forEach(System.out::println);
}
~~~

This is an **illustrative snippet placed inside application code**; you need to import **DataBinder**, **BindingResult**, and the example classes. **setValidator(...)** sets the primary validator, whereas **addValidators(...)** appends validators. When a global validator exists (for example, the Bean Validation adapter), using **addValidators(...)** at controller scope is usually appropriate if you want to combine it with existing checks; avoid accidentally replacing an already-configured validator.

**BindingResult** is an interface extending **Errors**, so custom **validate(...)** receives a compatible object and can append errors to the same result that the controller handles. Type conversion errors—for instance, a form submitting text for a numeric property—may already exist in **BindingResult** before the custom validator step runs.

## 5. Integrating Spring Validator in Spring MVC

In Spring MVC, one way to register a validator for **@ModelAttribute** is using **@InitBinder**. Below is an **illustrative snippet within an existing Spring MVC application**, reusing **EventPeriod** and **EventPeriodValidator** from the previous example; this is not a standalone web server:

~~~java
@Controller
class PeriodController {

    @InitBinder("eventPeriod")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(new ContractDemo.EventPeriodValidator());
    }

    @PostMapping("/periods")
    String create(
            @Valid @ModelAttribute("eventPeriod")
                    ContractDemo.EventPeriod input,
            BindingResult result) {

        if (result.hasErrors()) {
            return "period-form";
        }

        // Once validation passes, delegate to the service for business processing.
        return "redirect:/periods";
    }
}
~~~

In a real project you need the imports **jakarta.validation.Valid**, **org.springframework.stereotype.Controller**, **org.springframework.web.bind.annotation.InitBinder**, **PostMapping**, **ModelAttribute**, **org.springframework.web.bind.WebDataBinder**, **org.springframework.validation.BindingResult**; add MVC and Bean Validation dependencies if using the corresponding components.

- **@InitBinder("eventPeriod")** restricts registration to the model attribute named **eventPeriod**. **binder.addValidators(...)** attaches the custom validator to that attribute's binder.
- **@Valid** marks the bound object for validation. Spring MVC uses the validators configured on the binder, including the registered custom Spring Validator; if Bean Validation is present and configured, constraint annotations can also be evaluated.
- **BindingResult** must appear immediately after the parameter being validated to receive the corresponding errors. **hasErrors()** may represent either binding or validation errors, so do not name the variable **bindingFailed** and assume a single cause.
- If there is no matching **BindingResult/Errors** parameter for the controller to handle directly, Spring MVC may report validation failure via the corresponding exception mechanism, typically **MethodArgumentNotValidException** for object validation in standard cases.

With **@RequestBody** JSON, the body is read by an **HttpMessageConverter** before the DTO is validated. Malformed JSON or a deserialization failure may raise **HttpMessageNotReadableException** before any custom validator runs. Configuring binders and validators for **@RequestBody** differs from binding form parameters into **@ModelAttribute**; inspect how the application actually registers validators and handler signatures rather than assuming JSON parse errors enter the same **BindingResult** branch.

If both Bean Validation and Spring Validator are present, distinguish each mechanism's scope: **@NotBlank** and **@Min** are Jakarta Bean Validation constraints; **supports/validate** belong to Spring; **LocalValidatorFactoryBean** is the adapter that lets Bean Validation participate in Spring's mechanism. This does not turn **org.springframework.validation.Validator** into **jakarta.validation.Validator**.

## 6. Validators for Nested Objects and Property Paths

Suppose **Customer** has an **address** property with fields **street** and **zipCode**. You can reuse **AddressValidator**, but you need to maintain the **address** path so generated errors carry the right field names: **address.street** or **address.zipCode**.

~~~java
// Illustrative snippet inside validate(Object target, Errors errors)
// of CustomerValidator; Customer/AddressValidator are application classes.
Customer customer = (Customer) target;
if (customer.getAddress() == null) {
    errors.rejectValue("address", "address.required");
} else {
    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, customer.getAddress(), errors);
    } finally {
        errors.popNestedPath();
    }
}
~~~

**pushNestedPath(...)** switches the error context for the child validator; **popNestedPath()** restores the original context. Use **try/finally** to guarantee the path is always restored even if the code throws an unexpected exception. Check whether the nested object is null before invoking the child validator; **supports(...)** must match the child type. With Jakarta Bean Validation, nested objects typically use **@Valid** on the nested field, which is a separate corresponding mechanism and does not mean Spring automatically traverses every nested object for a custom Validator.

## 7. Differences from SmartValidator and Jakarta Bean Validation

| Mechanism | Key Characteristics | When to Use |
| --- | --- | --- |
| **Spring Validator** | Two core methods **supports** and **validate(Object, Errors)**; write custom logic and record errors via **Errors** | Custom rules, cross-field checks, reusable logic in Spring |
| **Spring SmartValidator** | Extends Spring Validator, supports **validate(target, errors, Object... validationHints)** | Need to pass hints/validation groups into the validation mechanism |
| **Jakarta Bean Validation** | Annotations such as **@NotNull**, **@NotBlank**, **@Size**; **jakarta.validation.Validator** API returns a set of **ConstraintViolation** | Declarative constraints using a provider such as Hibernate Validator |
| **LocalValidatorFactoryBean** | Adapter between Jakarta Bean Validation and the Spring contract | Integrating constraint annotations into Spring MVC/DataBinder |

**SmartValidator** still belongs to the **org.springframework.validation** family, but passes additional **validationHints** to the implementer. If you need Bean Validation groups from **@Validated(Group.class)**, check the group support of the corresponding adapter. An implementation with only the two basic Spring Validator methods does not automatically understand business groups or hints.

**validateObject(Object)** is not equivalent to **jakarta.validation.Validator.validate(...)**: the returned object is **org.springframework.validation.Errors**, whereas Jakarta Bean Validation returns a set of constraint violations. Check the package carefully when importing two interfaces with the same name.

## 8. Error Design and Business Responsibilities

A well-designed validator should be clear about what it checks:

**Suitable for a Spring Validator:** required title, date ordering, length limits, and cross-field conditions determinable from the input object. These rules run fast, are reproducible, are easy to unit test, and usually require no database access.

**Consider placing in a service/domain layer:** whether the user owns the resource; whether a course slot still has capacity; whether a code has already been used; whether a state transition is valid against current persisted data. Placing validation on a DTO does not replace contextual checks and transactional invariants. If uniqueness must be enforced, you still need concurrency protection in the database rather than relying solely on a query inside a validator.

**Clear rule pattern:** if **startDate == null**, add the corresponding field error; if both dates are present and **startDate.isAfter(endDate)**, add an object error. Check for null before comparing dates so you do not trigger a **NullPointerException** and turn ordinary invalid input into a system error.

Do not let a validator decide the HTTP status or render the response directly. In MVC, the controller and error-handling layer decide whether to re-render the form with messages or return an API response; in a service, the caller decides whether to proceed. **Errors** is a violation-collection contract, not a business-execution contract.

## 9. Common Implementation Mistakes

**Writing isAssignableFrom backwards in supports(...).** To accept **EventPeriod** and its subclasses, you must write **EventPeriod.class.isAssignableFrom(clazz)**. Reversing it produces wrong results when inheritance is involved.

**Throwing IllegalArgumentException in validate(...) on empty data.** That bypasses the error-recording contract and prevents reporting multiple errors at once. Use **rejectValue** or **reject** for invalid input data.

**Recording global errors for everything.** If only **title** is missing, use **rejectValue("title", ...)** so the UI can associate the message with the right field. Use **reject(...)** for object-wide conditions.

**Calling validate but ignoring Errors.** Because **validate(...)** returns **void**, the caller must inspect **hasErrors()** or the error list. Never infer "no exception means valid".

**Declaring a Validator bean and expecting @Valid to use it everywhere automatically.** Validator discovery depends on MVC configuration, DataBinder, and registration scope. Confirm the validator is attached to the binder or invoked explicitly; having a bean in the ApplicationContext does not mean every DTO runs that validator automatically.

**Using setValidator instead of addValidators without checking existing configuration.** This can overwrite a global validator that processes annotations; when combining multiple rule sets, inspect the binder's validator list before choosing a registration method.

**Accessing nested fields when null or forgetting popNestedPath.** The former can throw an exception, while the latter corrupts the path of subsequent errors. Check for null and use **try/finally**.

**Using a singleton validator with mutable fields holding the current request.** Validators may be invoked concurrently by multiple requests. Keep implementations stateless and pass all per-invocation data through **target/Errors** or an appropriate design.

**Conflating binding errors with validation errors.** **BindingResult** can contain **FieldError.isBindingFailure() == true** from a failed type conversion. Treating all errors merely as format validation makes diagnosis harder.

## 10. Testing the Contract

Unit test the validator class on its own before wiring it into a controller:

| Test | Input Data | Expected Result |
| --- | --- | --- |
| Type support | **EventPeriod.class** and **String.class** | **true** and **false** respectively |
| Missing title | **title = "   "**; valid dates | 1 **FieldError** on **title** |
| Missing start date | **startDate = null** | 1 **FieldError** on **startDate** |
| Inverted dates | **startDate > endDate**, valid title | 1 object-level **ObjectError** |
| Multiple violations | Blank title, inverted dates | 1 field error and 1 global error |
| Valid data | Non-blank title, both dates present, start not after end | **hasErrors() == false** |
| Reusability | Invoke the same validator instance on different objects | No leaked errors or state across calls |

For Spring MVC integration, you can use **MockMvc** to verify that the custom validator is actually registered via **@InitBinder**; a request violating constraints must cause the controller to receive errors and skip calling the persistence service. For forms with type-conversion errors, verify that binding errors remain present in **BindingResult** alongside any validation errors.

Self-check questions:

1. Why is **supports(Class<?>)** needed even though **validate(Object, Errors)** already accepts a target? Because the framework or calling code needs to determine whether a validator is compatible with an object type before using it.
2. When title is empty and the date range is invalid, what should **validate(...)** return? Nothing (**void**); it records two errors in **Errors**.
3. When should you use **rejectValue** instead of **reject**? When the error belongs to a specific field rather than the entire object.
4. Can **@Valid** be invoked without creating a custom Spring Validator? You can use Jakarta Bean Validation constraints when the system has the corresponding provider and configuration; if you want custom logic from a Spring Validator, that implementation must be registered or called.
5. Does validation via DataBinder guarantee that saving to the database will succeed? No; business rules, consistency, and concurrency still belong to subsequent layers.

## Official References to Consult

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework API — Validator, the two contract methods and validateObject (6.2.10)](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/Validator.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — Configuring Validators in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
