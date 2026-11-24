# Binding String Data into Objects via Conversion and Validation in SpEL

Spring Expression Language (SpEL) can assign values to object properties using `Expression.setValue(...)`. When an input value is a string while the target property has a different type, the EvaluationContext's TypeConverter can convert the value before writing it. After the binding step, the application can run Bean Validation or a Spring Validator to check data constraints.

Two responsibilities must be clearly separated: **conversion** transforms the data representation into the Java type required by the property; **validation** checks whether the converted value satisfies object and business constraints. SpEL supports property access and assignment, but the `setValue` operation itself does not automatically run Bean Validation.

## 1. Data binding workflow

A basic workflow consists of these steps:

1. Create a DTO or target object with appropriate properties and setters.
2. Create an EvaluationContext with property write permissions within the needed scope.
3. Configure a ConversionService/TypeConverter to convert strings into target types.
4. Use controlled expressions to assign input values.
5. Collect conversion or binding errors.
6. Run a Validator on the object after binding succeeds.
7. Only pass the valid object to the business layer after checking permissions and relevant rules.

For example, form data may arrive as:

    Map<String, String> input = Map.of(
            "fullName", "Lan Nguyen",
            "email", "lan@example.com",
            "age", "25"
    );

The target object can declare `fullName` and `email` as String, and `age` as Integer. SpEL can assign a string directly to the age property if the context's TypeConverter supports String to Integer.

Do not treat successful conversion as proof of valid data. The string `"-5"` can be converted into an Integer yet still violate a minimum age rule.

## 2. Preparing a DTO with clear properties

Using a DTO dedicated to input data helps restrict which fields are allowed to be bound and avoids exposing entire entities or high-privilege objects.

For example:

    public class RegistrationForm {

        private String fullName;
        private String email;
        private Integer age;

        public String getFullName() {
            return fullName;
        }

        public void setFullName(String fullName) {
            this.fullName = fullName;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

Reflective/data-binding PropertyAccessors can read and write the corresponding JavaBean properties. A property to be written must have a setter or be otherwise supported by the accessor.

Keep the DTO small, with concrete data types, containing only the fields the use case needs to receive. Do not bind directly into entities with deep relationships, administrative fields, payment statuses, or ownership attributes if the request sender is not allowed to modify them.

## 3. Using SimpleEvaluationContext for data binding

For use cases that only need to read/write JavaBean properties, you can use SimpleEvaluationContext in data binding mode:

    RegistrationForm form = new RegistrationForm();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("fullName")
            .setValue(context, "Lan Nguyen");

    parser.parseExpression("age")
            .setValue(context, "25");

In the example, the root object is form. The expressions `fullName` and `age` are resolved on the root object, and SpEL then writes the values through the property accessor. For age, the context's TypeConverter converts the string `"25"` to Integer if conversion is supported.

SimpleEvaluationContext is designed with a more limited feature set than StandardEvaluationContext. The read-write data binding builder allows property access for binding purposes, without enabling full capabilities such as bean references, type references, or constructor invocations.

If only binding data from strings is needed, there is no need to put ApplicationContext or services into the EvaluationContext.

## 4. Configuring ConversionService for target types

StandardEvaluationContext and SimpleEvaluationContext have a TypeConverter. StandardTypeConverter can use a Spring ConversionService to convert values.

Example configuring a converter for LocalDate in ISO format:

    DefaultFormattingConversionService conversionService =
            new DefaultFormattingConversionService();

    conversionService.addConverter(
            String.class,
            LocalDate.class,
            source -> LocalDate.parse(
                    source,
                    DateTimeFormatter.ISO_LOCAL_DATE
            )
    );

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .withConversionService(conversionService)
                    .build();

Then you can assign:

    parser.parseExpression("startDate")
            .setValue(context, "2026-11-12");

ConversionService finds a matching converter for source type String and target type LocalDate. If the string does not follow the configured ISO format, conversion fails and the property does not receive a valid LocalDate value.

Spring provides common converters and formatters via implementations such as DefaultConversionService and DefaultFormattingConversionService. For application-specific date/time formats, register an explicit Converter or Formatter instead of relying on implicit environment formats.

## 5. Conversion vs. validation

Conversion answers the question: "Can the input value be represented as the target Java type?"

Validation answers the question: "Does the typed Java value satisfy the constraints?"

For example:

| Input string | Conversion to Integer | Validation with `@Min(18)` |
|---|---|---|
| `"25"` | Succeeds, value 25 | Valid |
| `"abc"` | Fails | No Integer yet to check |
| `"15"` | Succeeds, value 15 | Invalid |
| `"-1"` | Succeeds, value -1 | Invalid |

A value can be convertible yet still violate business rules. Conversely, if conversion fails, the validation step cannot properly check the target-typed value the user intended to supply.

Keep binding/conversion errors separate from validation errors to return accurate messages. For example, `"abc"` for the age field is a numeric format error; `"15"` is a type-valid number that violates the age limit.

## 6. Declaring constraints with Bean Validation

A DTO can use Jakarta Bean Validation annotations:

    public class RegistrationForm {

        @NotBlank
        private String fullName;

        @NotBlank
        @Email
        private String email;

        @NotNull
        @Min(18)
        @Max(120)
        private Integer age;

        // getters and setters
    }

After binding data, run the validator:

    ValidatorFactory factory =
            Validation.buildDefaultValidatorFactory();

    Validator validator = factory.getValidator();

    Set<ConstraintViolation<RegistrationForm>> violations =
            validator.validate(form);

    if (!violations.isEmpty()) {
        // Convert violations into display errors or API errors.
    }

In a Spring application, it is usually best to configure and reuse `LocalValidatorFactoryBean` or inject a Spring-managed Jakarta Validator, rather than creating a new ValidatorFactory on every request. Ensure the project has the Jakarta Bean Validation API and a compatible provider, such as Hibernate Validator.

SpEL does not automatically call `validator.validate(form)` after `setValue`. The application must explicitly run validation at the appropriate step.

## 7. Complete example: bind, convert, then validate

The following example binds several known fields into a DTO, converts age from String to Integer, and then checks constraints:

    RegistrationForm form = new RegistrationForm();

    DefaultFormattingConversionService conversionService =
            new DefaultFormattingConversionService();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(form)
                    .withConversionService(conversionService)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("fullName")
            .setValue(context, input.get("fullName"));

    parser.parseExpression("email")
            .setValue(context, input.get("email"));

    parser.parseExpression("age")
            .setValue(context, input.get("age"));

    Set<ConstraintViolation<RegistrationForm>> violations =
            validator.validate(form);

If `input.get("age")` is a valid numeric string, the TypeConverter can convert it to Integer before the setter is invoked. If it cannot be converted, `setValue` raises an evaluation/conversion error; the application must catch that error and record an error for the age field.

In production code, isolate each field into an operation with its own error handling so one malformed field does not lose error information for the remaining fields. Only run validation on the object after binding status is determined; if you still validate an object with unbound fields due to failed conversion, clearly distinguish violations caused by missing data from the initial conversion error.

## 8. Collecting binding errors separately from validation errors

You can create a helper that accepts expressions predefined by the application:

    void bindValue(
            Expression expression,
            EvaluationContext context,
            Object rawValue,
            String field,
            List<String> bindingErrors) {

        try {
            expression.setValue(context, rawValue);
        }
        catch (EvaluationException ex) {
            bindingErrors.add(
                    "Cannot convert or assign field: " + field
            );
        }
    }

Expressions passed to the helper should be parsed from fixed field names in code or taken from an allowlist. Do not accept arbitrary SpEL expressions or property paths directly from a request.

After binding fields:

    if (bindingErrors.isEmpty()) {
        Set<ConstraintViolation<RegistrationForm>> violations =
                validator.validate(form);
    }

The application can convert each ConstraintViolation into an error attached to the corresponding property path. Do not return stack traces or internal converter details to clients; keep the cause chain in controlled internal logs.

In practice, use structured error types such as field, error code, and message rather than only collecting strings. This helps APIs or UIs display errors per input.

## 9. Binding only allowlisted fields

Do not use client-supplied property names directly as SpEL:

    parser.parseExpression(userSuppliedField)
            .setValue(context, userSuppliedValue);

If the field contains SpEL syntax or an unexpected property path, the sender could attempt to access or write out-of-scope attributes. SimpleEvaluationContext restricts many capabilities, but does not replace the application's field allowlist.

Instead, map input names to fixed expressions:

    Map<String, Expression> writableFields = Map.of(
            "fullName", parser.parseExpression("fullName"),
            "email", parser.parseExpression("email"),
            "age", parser.parseExpression("age")
    );

    Expression expression = writableFields.get(inputField);

    if (expression == null) {
        throw new IllegalArgumentException(
                "Field is not writable"
        );
    }

    expression.setValue(context, inputValue);

This allowlist only illustrates allowed fields. The application still needs to verify the caller has permission to update the target object and corresponding field. Do not include properties such as `id`, `owner`, `tenantId`, `role`, `approved`, or administrative statuses in the allowlist if the client is not allowed to control them.

## 10. Binding nested paths

SpEL supports assigning nested properties:

    parser.parseExpression("address.city")
            .setValue(context, "Da Nang");

For this operation to succeed, the intermediate object `address` must exist and the accessor must have permission to write the `city` property. SpEL does not automatically instantiate Address if the address property is currently null.

You can initialize the intermediate object beforehand:

    form.setAddress(new AddressForm());

    parser.parseExpression("address.city")
            .setValue(context, "Da Nang");

If the nested object also has validation constraints, declare `@Valid` on the property:

    public class RegistrationForm {
        @Valid
        @NotNull
        private AddressForm address;
    }

The Validator will check the nested object when performing cascaded validation. If address is null, `@NotNull` detects an error; if address exists, constraints inside AddressForm are evaluated.

With nested paths, allowlist the exact writable paths and avoid letting clients construct arbitrary paths. Check null, target type, and update permissions before assigning.

## 11. Custom Converters for domain types

If a field uses a custom type, you can register an explicit Converter. For example, converting a string to an enum:

    public enum DeliveryMode {
        STANDARD,
        EXPRESS
    }

    conversionService.addConverter(
            String.class,
            DeliveryMode.class,
            source -> DeliveryMode.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            )
    );

When the DTO has a `deliveryMode` property of type DeliveryMode, the expression can assign a string:

    parser.parseExpression("deliveryMode")
            .setValue(context, "express");

The Converter normalizes casing before converting. If the string does not match the enum, conversion fails; the application should return a clear field error.

A Converter should perform pure data representation conversion. It should not call databases, check permissions, send messages, or mutate state inside the converter. Rules requiring business data should be checked in a service or dedicated Validator.

## 12. Validation groups and cross-field rules

Bean Validation supports validation groups to apply different constraints for create or update operations:

    interface Create {}
    interface Update {}

    public class ProfileForm {

        @NotBlank(groups = Create.class)
        private String username;

        @Email(groups = {Create.class, Update.class})
        private String email;
    }

    validator.validate(form, Create.class);

This is useful when a field is required on creation but may be omitted in a partial update request.

For cross-field rules, you can use a class-level constraint or a dedicated Spring Validator. For example, `startDate` must be before `endDate`; checking each field individually is insufficient to verify the relationship between them.

Conversion still happens before validation. Only once both dates have been converted to LocalDate can the validator compare them according to domain rules.

## 13. When to use DataBinder instead of SpEL?

SpEL can assign properties and leverage TypeConverter, but it is not a general-purpose form binding framework. If you need to bind many fields from requests, manage field errors, allowed fields, nested objects, and validation following the standard Spring MVC workflow, `DataBinder` or `WebDataBinder` is usually more appropriate.

DataBinder provides dedicated mechanisms such as:

- Binding property values onto a target object.
- Configuring allowed fields and disallowed fields.
- Using ConversionService and PropertyEditors.
- Collecting binding errors in BindingResult.
- Integrating with Spring Validator or Jakarta Bean Validation.

Use SpEL when the application genuinely needs expressions to select or assign a few controlled properties. Use DataBinder for standard form/request binding flows to take advantage of binding and error-reporting mechanisms designed specifically for that job.

Regardless of the tool used, you must still verify authorization on the object and fields allowed to be updated. Allowed fields and validation do not replace authorization.

## 14. Common errors

- **Assuming setValue auto-validates:** SpEL only performs access/assignment and conversion; the application must invoke Validator separately.
- **Confusing conversion with validation:** a string can convert to a number yet still violate `@Min`, `@Max`, or domain rules.
- **Using a read-only context for writing:** choose `forReadWriteDataBinding()` when the use case needs to update properties.
- **Property missing a setter:** check the accessor and target JavaBean property.
- **Null nested object:** initialize the intermediate object before assigning a deep path.
- **Converter does not support format:** register an appropriate Converter/Formatter and test invalid inputs.
- **Binding by client-supplied property path:** use a field allowlist and fixed expressions.
- **Binding directly into an entity:** use a field-restricted DTO to prevent mass assignment.
- **Ignoring conversion errors:** record errors per field and do not treat an incompletely bound object as valid.
- **Creating ValidatorFactory per request:** configure and reuse a Spring-managed validator.

## 15. Key takeaways

SpEL can bind values using `Expression.setValue(...)`; the EvaluationContext's TypeConverter converts string data into target property types when an appropriate converter exists. Use `SimpleEvaluationContext.forReadWriteDataBinding()` for scoped property binding and configure ConversionService for domain types or custom formats. After conversion, the application must explicitly run Jakarta Bean Validation or a Spring Validator; `setValue` does not automatically validate the object. Separate conversion errors from constraint violations, initialize nested objects before writing, bind only allowlisted fields, and verify update permissions. For multi-field form/request binding, consider DataBinder/WebDataBinder because they provide dedicated binding and error-reporting workflows.
