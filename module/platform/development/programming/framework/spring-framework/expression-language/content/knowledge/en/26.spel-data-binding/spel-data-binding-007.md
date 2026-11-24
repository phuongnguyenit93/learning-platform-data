# Bind, Conversion, and Validation Errors Must Be Kept Separate

## 1. Three Distinct Stages

In a Spring application, input data typically passes through three related stages that serve different purposes:

1. **Binding (assigning data):** locating the target property on an object and placing the input value into that property.
2. **Conversion (type conversion):** converting the value from the source type to the type required by the property or caller.
3. **Validation (validity checking):** checking whether the value, after binding and conversion, satisfies data or business rules.

All three stages can occur within the same request, yet they do not replace one another. A string may convert to an Integer successfully and still be invalid under business rules. Conversely, a value may be valid from a business perspective yet fail to bind because the property does not exist or is not writable.

Example with a registration form:

- Binding: placing the value `"18"` into the `age` property.
- Conversion: converting String `"18"` into Integer `18`.
- Validation: checking whether the age meets the minimum threshold.

If `age = "abc"`, the error is in conversion. If `age = "15"` is converted to Integer 15 but the rule requires at least 18, the error is in validation. If the `age` property does not exist or cannot be written, the error is in binding/property access.

## 2. Binding in SpEL

SpEL can read or write properties on the root object through a PropertyAccessor. When `setValue()` is called, the expression identifies the target property and assigns the supplied value:

```java
ExpressionParser parser = new SpelExpressionParser();

RegistrationForm form = new RegistrationForm();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withRootObject(form)
                .build();

parser.parseExpression("email")
        .setValue(context, "ada@example.com");

String email = form.getEmail();
```

In this example, `email` is the property path and `setValue()` performs the write operation. The property must be accessible and writable by the configured PropertyAccessor. With a data binding context, Spring supports public properties according to data binding rules.

If the expression references a nonexistent property, or a property is not writable, SpEL cannot complete the binding operation. This is a property path/access issue, not a validation error on the value.

For example:

```java
parser.parseExpression("unknownField")
        .setValue(context, "value");
```

If `RegistrationForm` has no `unknownField` property, the expression cannot write the value into the object. Do not handle this error by relaxing validation; check the property name, getter/setter, and PropertyAccessor.

### 2.1. Binding with DataBinder

At the Spring data binding layer, `DataBinder` accepts property values and binds them into a target object. This is the API commonly used for form objects and application-controlled binding flows:

```java
RegistrationForm form = new RegistrationForm();

DataBinder binder = new DataBinder(form, "registrationForm");

MutablePropertyValues values = new MutablePropertyValues();
values.add("email", "ada@example.com");
values.add("age", "18");

binder.bind(values);

BindingResult result = binder.getBindingResult();
```

`DataBinder` locates the target property and performs the steps needed to place the value into the object. This process can include conversion. Binding/conversion errors are recorded in BindingResult rather than treating all errors as validation errors.

You can restrict which properties are allowed to be bound:

```java
binder.setAllowedFields("email", "age", "displayName");
```

A property allow-list helps prevent mass assignment, such as a requester trying to bind into `role`, `admin`, or internal properties that should not be modified.

## 3. Conversion: Converting a Value to the Target Type

Data from HTTP forms, query parameters, or configuration often arrives as Strings. Java properties may require Integer, Long, BigDecimal, Boolean, enums, date/time, or other domain types.

SpEL uses `TypeConverter` in EvaluationContext to convert results to the target type. In a standard configuration, `StandardTypeConverter` integrates with Spring's `ConversionService`.

Example requesting a target type during evaluation:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Integer age = parser.parseExpression("'18'")
        .getValue(context, Integer.class);

BigDecimal amount = parser.parseExpression("'125.50'")
        .getValue(context, BigDecimal.class);
```

Example assigning a string to a numeric property:

```java
RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

parser.parseExpression("age").setValue(context, "18");

Integer age = form.getAge();
// 18
```

In `setValue()`, SpEL knows the target property type and asks TypeConverter to convert the String to that type before assigning. If the string does not represent a valid target value, conversion fails.

### 3.1. Conversion Does Not Confirm Business Validity

Suppose the `age` property has type Integer:

| Input | Conversion | Validation if age >= 18 is required |
|---|---|---|
| `"18"` | Succeeded: Integer 18. | Valid. |
| `"15"` | Succeeded: Integer 15. | Invalid. |
| `"abc"` | Failed: cannot convert to Integer. | No Integer from input yet to check the age rule. |
| `""` | May become null depending on converter and target type. | Depends on null/required rules. |

Conversion only answers the question "can this value be represented by the target type?". It does not answer "is this value acceptable to the business logic?".

### 3.2. Configuring ConversionService

You can use the default ConversionService or register custom converters:

```java
DefaultConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

If the application needs custom formats, such as dates in a specific pattern or aliases for an enum, register the appropriate converter in ConversionService. Converters should handle input formats explicitly and report errors when data is malformed.

Do not turn a conversion error into an arbitrary default value if doing so could cause bad data to be saved as valid data.

## 4. Validation: Checking Rules After Binding

Validation checks whether already-typed data satisfies rules. Rules might be:

- Required fields must not be null or blank.
- Email must match a valid format.
- Age must be within an allowed range.
- End date must be after start date.
- Order status must be compatible with the current state.

Example using Jakarta Bean Validation:

```java
public class RegistrationForm {

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // getters and setters
}
```

The annotations describe constraints. They do not convert strings to Integer themselves; conversion belongs to the binding/conversion layer. A Validator checks the object after values have been bound.

With Spring Validator, you can add a validator to DataBinder and then invoke validation:

```java
RegistrationForm form = new RegistrationForm();

DataBinder binder = new DataBinder(form, "registrationForm");
binder.addValidators(registrationFormValidator);

MutablePropertyValues values = new MutablePropertyValues();
values.add("email", "ada@example.com");
values.add("age", "15");

binder.bind(values);
binder.validate();

BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Read and handle errors in result.
}
```

If using Jakarta Bean Validation in Spring, `LocalValidatorFactoryBean` can be registered as a Spring Validator. In Spring-managed applications, validators are usually configured via dependency injection rather than instantiated per request.

## 5. BindingResult Can Contain Multiple Kinds of Errors

`BindingResult` collects errors arising during binding and validation. A single request can have multiple errors at once, and the source of each error must be distinguished.

With `FieldError`, the `isBindingFailure()` method helps identify errors tied to binding/conversion:

- `true`: binding or conversion failure for the field.
- `false`: validation error recorded for the field.

Example reading errors:

```java
for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    Object rejectedValue = error.getRejectedValue();
    String message = error.getDefaultMessage();
    boolean bindingFailure = error.isBindingFailure();

    if (bindingFailure) {
        // Value could not be bound/converted to the property.
    }
    else {
        // Value was bound but failed constraint/validation.
    }
}
```

Useful properties for diagnosis:

| Property | Meaning |
|---|---|
| `getField()` | Name of the field with the error. |
| `getRejectedValue()` | Rejected value or input value associated with the error. |
| `getCodes()` | Message codes for resolving messages according to Spring conventions. |
| `getDefaultMessage()` | Default error message. |
| `isBindingFailure()` | Distinguishes a binding/conversion failure from a regular validation error. |

Do not merely check `hasErrors()` and return a generic message. Inspect the field, error codes, and bindingFailure to know whether to fix input data, property mapping, or business rules.

## 6. Example: Same Field, Two Different Error Types

Suppose a form has `age` of type Integer and constraint `@Min(18)`.

### Case A: Conversion fails

Input:

```text
age = "abc"
```

Spring cannot convert `"abc"` to Integer. The property does not receive a valid Integer value from the input. In DataBinder, the error is recorded in BindingResult as a binding failure.

### Case B: Conversion succeeds, validation fails

Input:

```text
age = "15"
```

Spring converts it to Integer 15 successfully. Then the validator checks `@Min(18)` and records a validation error because age is less than 18.

The two cases require different handling:

| Case | Error | How to Fix |
|---|---|---|
| `"abc"` | Not a valid integer. | Ask the user to enter a properly formatted number. |
| `"15"` | Is an integer but violates the age limit. | Require a value that satisfies the business rule. |

If only a message like "age is invalid" is shown, the user does not know whether to fix the format or fix the value.

## 7. Validation in Spring MVC

For a form object bound from a request, Spring MVC can perform binding, conversion, and validation within controller request handling.

For example:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "registration-form";
    }

    registrationService.register(form);
    return "redirect:/registration/success";
}
```

`@ModelAttribute` instructs Spring to bind request parameters to the form object. ConversionService assists with converting values to property types. `@Valid` requests validation on the object after binding.

If errors need to be handled inside the controller, `BindingResult` must be placed immediately after the corresponding model attribute parameter. When BindingResult is in that position, the controller can inspect errors and return the form. Without a matching BindingResult parameter, Spring MVC may throw an exception for validation/binding errors depending on the argument type and configuration.

Do not confuse `@Valid` with conversion: `@Valid` triggers constraint checking, not converting `"15"` into Integer 15.

## 8. SpEL Errors and DataBinder Errors at Different Layers

Exception names depend on the API and layer performing the work. Some common groups:

| Layer | Common Symptom/Error | Meaning |
|---|---|---|
| Expression parsing | `ParseException` or `SpelParseException` | Invalid SpEL syntax. |
| SpEL property/method evaluation | `SpelEvaluationException` | Expression cannot be evaluated, e.g. wrong property path or invalid method call. |
| Spring property binding | `NotWritablePropertyException`, `NotReadablePropertyException`, or corresponding access error | Property does not exist, cannot be read, or cannot be written. |
| Type conversion | `TypeMismatchException`, `ConversionFailedException`, or conversion error wrapped in an upper-layer exception | Value cannot be converted to the target type. |
| Validation | `ObjectError` / `FieldError` in BindingResult or `ConstraintViolation` | Value was checked and violated a constraint. |

In DataBinder and Spring MVC, binding/conversion errors are usually kept in BindingResult rather than always throwing exceptions out of the controller. When invoking SpEL directly, evaluation/conversion errors can be thrown to the caller. Therefore, diagnose according to the API in use rather than relying only on exception names from a different example.

When calling Jakarta Bean Validation directly via `Validator.validate(object)`, it returns a set of `ConstraintViolation` instances. It does not automatically throw `ConstraintViolationException` for every data error. `ConstraintViolationException` usually appears in mechanisms such as method validation when constraints on parameters/return values are violated.

## 9. SpEL setValue Does Not Automatically Run Bean Validation

A common misconception is that a successful `setValue()` call means the object is valid.

For example:

```java
RegistrationForm form = new RegistrationForm();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withRootObject(form)
                .build();

parser.parseExpression("age").setValue(context, "15");

// age has been converted to Integer 15.
// SpEL does not automatically run @Min(18) here.
```

After this operation, if constraints must be checked, the application must invoke a Validator or pass the object into a Spring MVC/DataBinder flow with validation configured.

Similarly, `getValue()` with a target type only performs evaluation and conversion to the target type. It does not automatically invoke Bean Validation.

## 10. How to Handle Each Error Group

### 10.1. Binding/property access failure

Check:

- Is the property path name correct?
- Does the property exist on the target object?
- Are the getter/setter appropriate for the read/write operation?
- Does the current PropertyAccessor support that object type?
- Does DataBinder permit that field via allowed fields?

Do not fix a binding error by changing validation constraints.

### 10.2. Conversion failure

Check:

- What is the actual source type?
- What is the target type of the property or `getValue()`?
- Is the string properly formatted?
- Do the locale/format match the converter?
- Has the context's ConversionService registered the needed converter?

If the format is valid per business rules but the default converter does not understand it, register a custom converter. If the data is malformed, return a clear conversion message.

### 10.3. Validation failure

Check:

- Which constraint was violated?
- What is the value after conversion?
- Is the business rule accurate?
- Is cross-field checking needed?
- Do the message code and displayed message explain how to fix it?

Do not relax constraints just to make a conversion error disappear. The two error types have different causes.

## 11. Safe Request Handling Workflow

A workflow that is easy to diagnose usually includes:

1. Define the list of properties allowed to be bound.
2. Bind input data into the target object.
3. Convert each value to its target property type using ConversionService.
4. Collect binding/conversion errors into BindingResult.
5. Run Validator on the bound object.
6. Collect validation errors into the same BindingResult or a separate validation result.
7. Classify FieldErrors using field, error code, and `isBindingFailure()`.
8. Only invoke business logic when no errors remain according to the handling policy.
9. Display messages matching the true cause: invalid property, invalid format, or rule violation.
10. Log necessary error codes and fields; avoid logging sensitive data/rejected values unnecessarily.

If using SpEL directly to assign properties, treat it as a property access and conversion operation. Invoke Validator as a separate step afterward if the application needs to guarantee the object satisfies constraints.

## 12. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `setValue()` succeeds yet the object is still invalid | SpEL bound/converted without running validation. | Call Validator or DataBinder.validate() after binding. |
| Numeric string produces an error | Value does not match the target type format. | Check format and ConversionService. |
| Value converts yet is still rejected | Business constraint is not satisfied. | Inspect FieldError/ConstraintViolation and fix the value. |
| FieldError is hard to classify | Only checking `hasErrors()`. | Check `isBindingFailure()`, field, codes, and rejectedValue. |
| Property cannot be written | Wrong path, missing setter, or unsupported accessor. | Check the target object and PropertyAccessor. |
| Validator does not run | validate not called or validator not configured in MVC/DataBinder. | Register a Spring Validator and enable validation. |
| Using @Valid yet conversion fails | @Valid only checks constraints after binding. | Handle binding/conversion errors separately in BindingResult. |
| All errors are turned into "invalid input" | Not distinguishing binding, conversion, and validation. | Use error codes and error sources to produce specific messages. |
| Validation runs on old value after conversion failure | Field did not receive the new value because conversion failed. | Check binding failures first; do not assume target holds the rejected value. |
| Allowing all fields of an object to be bound | No restriction on input properties. | Use a dedicated form DTO and allowed fields. |

## 13. Takeaways

- Binding locates the target property and assigns data onto the object.
- Conversion transforms a value from the source type to the target type; SpEL uses TypeConverter and Spring ConversionService.
- Validation checks whether values after binding/conversion satisfy constraints and business rules.
- `setValue()` can bind and convert, but does not automatically run Bean Validation.
- DataBinder performs binding and records errors in BindingResult; `validate()` can be called to run validators.
- `FieldError.isBindingFailure()` helps distinguish binding/conversion errors from validation errors.
- Successful conversion does not mean valid data; `"15"` can convert to Integer yet still violate `@Min(18)`.
- SpEL parse/evaluation errors differ from binding errors, conversion errors, and validation errors.
- Use property allow-lists, form DTOs, and root-cause-accurate error messages to handle data safely.

## References

- [Spring Framework Reference — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework Reference — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html)
- [FieldError Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html)
- [DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)
