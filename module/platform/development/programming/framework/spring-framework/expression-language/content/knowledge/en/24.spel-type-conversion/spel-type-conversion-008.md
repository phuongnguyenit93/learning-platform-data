# Distinguishing Conversion from Validation

## Objectives

After this lesson, you will be able to distinguish data type conversion (conversion) from validity checking (validation) when working with Spring Expression Language (SpEL); identify when SpEL requests conversion automatically; configure TypeConverter or ConversionService; and design data checking steps after conversion. You will also learn how to handle null values, conversion errors, numeric bounds, formats, and business rules that conversion cannot guarantee on its own.

## 1. Conversion and Validation Solve Two Different Problems

**Conversion** changes the representation or data type of a value so it fits where it is used. For example, converting the string "42" into an Integer or converting a value into the date/time type the application needs.

**Validation** checks whether data meets required conditions. For example, age must be greater than or equal to 18, an email must have an accepted format, end date must be after start date, or total amount must stay within a limit.

These two tasks are related, yet they do not replace each other:

| Scenario | Conversion | Validation |
|---|---|---|
| String "42" to Integer | Converts if converter supports it | Checks whether 42 falls within the valid age range |
| String "abc" to Integer | Usually fails because it cannot represent an integer | Reports invalid input data |
| String "999" to Integer | Can convert successfully | May be invalid if maximum limit is 120 |
| Date "2026-02-30" | Date conversion may fail because the date does not exist | Checks whether the date falls within the business window |
| Amount -10.00 to BigDecimal | Converts successfully | May be invalid if amount must be non-negative |

Conversion answers the question: "Can this value be represented in the target type?" Validation answers: "Once understood properly, is this value allowed to be used?"

## 2. At What Points Does SpEL Convert Types?

SpEL uses the EvaluationContext's TypeConverter when an operation needs a value in a different type. Some common situations:

- When requesting a specific result type via getValue with a target type.
- When assigning a value to a property whose type differs from the source expression.
- When passing arguments to a method and conversion to parameter types is needed.
- When performing other operations where evaluation needs to convert a value to a target type.

Example requesting an Integer result:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("'42'");

Integer value = expression.getValue(Integer.class);
~~~

The literal expression produces a String. When the application requests an Integer result, SpEL uses the context's TypeConverter to try converting the value to the target type.

Example passing an argument to a method:

~~~text
#accountService.findById('42')
~~~

If the selected method accepts a numeric type such as Long and the converter supports String to Long, SpEL can convert the argument before calling the method.

Conversion only happens when an operation needs it. Do not assume every value in the context is normalized immediately upon registering variables or parsing expressions.

## 3. TypeConverter in EvaluationContext

EvaluationContext supplies TypeConverter for SpEL to perform conversion. StandardEvaluationContext uses StandardTypeConverter under its default configuration.

You can obtain the converter from the context:

~~~java
TypeConverter converter = context.getTypeConverter();
~~~

And check whether a type pair can be converted:

~~~java
boolean canConvert =
    converter.canConvert(sourceTypeDescriptor, targetTypeDescriptor);
~~~

When customization is needed, the application can supply another TypeConverter to the context. For example, StandardTypeConverter can be constructed from a Spring ConversionService:

~~~java
ConversionService conversionService = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

As a result, SpEL uses converters and formatters registered in ConversionService when conversion is needed.

Configure converters consistently with the rest of the application. If the same value is converted in a controller, service, and SpEL yet each place uses different rules, results can become unpredictable.

## 4. ConversionService and Custom Converters

Spring ConversionService provides a centralized type conversion mechanism. An application can register converters for specific type pairs, such as String to a business code type or a custom value type.

Example code type:

~~~java
public record CustomerCode(String value) {
}
~~~

Converter:

~~~java
public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null) {
            return null;
        }
        return new CustomerCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

After the converter is registered in ConversionService and ConversionService is passed to StandardTypeConverter, SpEL can use that rule whenever String needs to be converted to CustomerCode.

A converter should focus on converting and normalizing representations. The example above trims whitespace and normalizes to uppercase. If CustomerCode also must satisfy rules like a valid prefix, active status, or usage permissions, those conditions belong in validation or separate business logic.

Do not place all business rules inside a converter. A converter called automatically in many places should have simple, deterministic behavior and no side effects.

## 5. Example: getValue with a Target Result Type

Suppose an application receives a string variable yet wants to retrieve an Integer result:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("quantityText", "25");

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#quantityText");

Integer quantity =
    expression.getValue(context, Integer.class);
~~~

If the default converter supports String-to-Integer conversion and the string has a valid numeric format, the result is 25.

However, obtaining an Integer does not prove quantity is valid under business rules. For instance, the system only allows quantities from 1 to 10. The value 25 converts successfully yet still must be rejected by validation.

You can validate after conversion:

~~~java
if (quantity == null || quantity < 1 || quantity > 10) {
    throw new IllegalArgumentException(
        "Quantity must be between 1 and 10"
    );
}
~~~

Keep the two steps distinct: convert types first, then check value bounds. If user-friendly errors are needed, translate technical conversion errors and business validation errors into appropriate messages at the application layer.

## 6. Property Assignment and Value Conversion

SpEL can assign values to properties on the root object:

~~~text
quantity = '25'
~~~

Suppose the quantity property has type Integer while the right-hand expression produces a String. If EvaluationContext has a TypeConverter supporting that type pair and the property is writable, SpEL can convert the value before calling the setter or performing the write.

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("quantity = '25'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

OrderDraft draft = new OrderDraft();

expression.getValue(context, draft);
~~~

After the assignment, the quantity property can receive the Integer value 25.

Conversion does not verify conditions such as quantity being greater than 0 or not exceeding inventory. If a property receives an integer that is type-valid yet business-invalid, the application still needs validation.

Additionally, writing properties depends on the PropertyAccessor and write permissions of the EvaluationContext. A TypeConverter can convert a value, yet it does not grant write access to a read-only property.

## 7. Conversion When Calling Methods

SpEL can convert arguments when invoking a method if TypeConverter supports the target type and method resolution finds a matching method.

For example, a service has a method:

~~~java
public Account findById(Long id) {
    // Find account by ID.
}
~~~

Expression:

~~~text
#accountService.findById('42')
~~~

can convert the string '42' to Long before invoking the method if the context and converter support it.

This is convenient for short expressions, yet implicit conversion should not be used to mask unvalidated input data. If the ID comes from a request, verify it has the right format and falls within accessible scope before calling the service.

A method can throw an error because the account is not found, locked, or the caller lacks permission. Those are not conversion errors. Distinguish argument conversion errors from business errors thrown by the method itself.

## 8. Conversion Does Not Check Value Bounds

A value can convert successfully and still be invalid.

For example:

~~~java
Integer age = Integer.valueOf("150");
~~~

Conversion succeeds because 150 is a valid integer. However, if the system enforces a maximum user age of 120, this value must be rejected by validation.

Similarly:

- -5 converts to Integer yet may be invalid if quantity must be non-negative.
- 999999.99 converts to BigDecimal yet may exceed transaction limits.
- A string may convert to an enum yet that state may not be allowed in the current workflow.
- A date may convert to LocalDate yet fall outside the permitted registration window.
- A code may convert to CustomerCode yet not exist in the system.

Do not use canConvert as a business validity check. It only tells whether a converter can handle the type pair per configuration; it does not confirm that a specific value is allowed.

## 9. What Should Validation Check?

Validation typically consists of multiple layers of conditions:

**Structural and data type checks**

- Can it convert to the desired type?
- Does the string match the required format?
- Is the value null when the field is required?

**Value range checks**

- Is the number within minimum and maximum limits?
- Is the string length within allowed bounds?
- Is the date within a valid time range?

**Cross-field relationship checks**

- Is the end date after the start date?
- Is quantity consistent with unit price and total amount?
- Is the shipping address compatible with the shipping method?

**Business and state checks**

- Does the customer code exist and is it active?
- Does the account have permission to perform the operation?
- Is the order in a state that permits updating?
- Is the current limit sufficient for the transaction?

A converter typically takes a single source value and produces a single target value. Business validation may require multiple fields, repository data, or current system state; place it in the appropriate layer instead of forcing it into conversion.

## 10. Using Bean Validation or Spring Validator

Java Bean Validation (Jakarta Validation) provides annotations to describe many data constraints:

~~~java
public class RegistrationRequest {

    @NotBlank
    private String username;

    @Min(18)
    @Max(120)
    private Integer age;

    @Email
    private String email;

    // getters and setters
}
~~~

After data is bound and converted to field types, the application can run a Validator to verify constraints.

With Spring Validator, you can implement custom rules for an object:

~~~java
public class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationRequest.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationRequest request =
            (RegistrationRequest) target;

        if (request.getAge() != null && request.getAge() < 18) {
            errors.rejectValue(
                "age",
                "registration.age.tooYoung"
            );
        }
    }
}
~~~

SpEL does not automatically execute all Bean Validation or Spring Validators just because a value was converted. The application must invoke the validator at the right step in the processing flow.

You can use SpEL to express a simple condition, yet request or object validation should generally be structured using dedicated validation mechanisms to obtain field errors, message codes, and reusability.

## 11. Handling Null and Empty Strings

Null and empty strings are two distinct states:

- null means there is no object value.
- "" is an existing String with zero characters.
- A whitespace-only string is still a String containing whitespace characters.

Converters can handle these cases according to their own rules. Some Spring converters may treat an empty or whitespace-only string as null in certain conversions; exact behavior depends on the converter and target type.

Do not rely on a blanket assumption that every empty string becomes null or every null value is rejected.

For example, if username must have content:

~~~java
if (username == null || username.isBlank()) {
    throw new IllegalArgumentException(
        "Username is required"
    );
}
~~~

If a field is optional, the application may allow null yet still must define how empty strings are handled. Normalize inputs according to the API contract before converting or validating, especially when whitespace is meaningful in the data.

## 12. Conversion, Parsing, and Formatting

Conversion and parsing are related yet not strictly synonymous in application design.

- Parsing typically interprets text according to a specific syntax or format.
- Conversion transforms a value from a source type to a target type.
- Formatting turns a value into a text representation for display or parses it from input.
- Validation confirms the value satisfies required rules.

For example, the date 31/12/2026 can be parsed in day-month-year format. Using month-day-year format by mistake can yield wrong results or fail to parse.

For currency or date/time, explicitly configure locale, timezone, and format. Do not rely on the server or runtime environment's default formatting, as the same string can be interpreted differently across locales.

Even after successful parsing, validation is still needed: is the date within the allowed period, does the amount use the right unit, and does the value fit the business state?

## 13. Using TypeDescriptor When Type Metadata Is Needed

Spring uses TypeDescriptor to describe a data type along with related metadata, such as collection element types, Map key/value types, or annotations on a property.

This matters when converting collections with generic types. For example, a List<String> needs to be converted into List<Integer>; knowing only the outer target type List.class is insufficient to fully describe the element type.

TypeDescriptor helps converters understand source and target types in finer detail. When writing custom converters for collections or properties with metadata, inspect TypeDescriptor instead of relying solely on Class<?>.

However, type metadata does not replace content validation. A List<Integer> can still contain values outside business limits; TypeDescriptor only assists conversion according to the described types.

## 14. Handling Conversion and Validation Errors Separately

Conversion can fail because:

- String cannot be parsed into the target type.
- Source type is not supported by any converter.
- Value cannot be represented in the target type.
- Custom converter throws an error.
- Date, number, or enum format is invalid.

Validation can fail because:

- Value is null on a required field.
- Value is outside min/max bounds.
- Two fields are inconsistent.
- State transition is not allowed.
- User lacks permission to perform the operation.
- Data violates business rules.

Keep these two error categories separate in the processing flow. Conversion errors generally indicate data could not be converted to the target type; validation errors indicate the value was understood yet is not permitted for use.

When catching errors in Java, preserve the root cause and map it to an appropriate message. Do not return an arbitrary default value when conversion fails, as that can turn invalid input into data that appears valid.

## 15. A Typical Processing Flow

A clean workflow may consist of these steps:

1. Receive input data from a request or configuration source.
2. Check basic format requirements if needed.
3. Convert to the model's data types.
4. Run structural and value-range validation.
5. Run cross-field or business validation.
6. Only when valid, perform writes or invoke services with side effects.

For example:

~~~java
String quantityText = request.getParameter("quantity");

Integer quantity;
try {
    quantity = conversionService.convert(
        quantityText,
        Integer.class
    );
}
catch (ConversionException ex) {
    throw new BadRequestException("Quantity must be an integer", ex);
}

if (quantity == null || quantity < 1 || quantity > 10) {
    throw new BadRequestException("Quantity must be between 1 and 10");
}

orderService.updateQuantity(orderId, quantity);
~~~

In practice, calling ConversionService may require supplying both source and target types depending on the API used. The example above illustrates processing order; use the exact overload matching your project's Spring version.

Do not use SpEL as the sole place to validate input data. SpEL can express conditions, yet the application still needs an explicit validation pipeline before performing actions.

## 16. Conversion in SimpleEvaluationContext and StandardEvaluationContext

Both EvaluationContext types supply a TypeConverter for evaluation, though their feature scopes differ.

**StandardEvaluationContext** offers broader SpEL capabilities and allows configuring TypeConverter, PropertyAccessor, MethodResolver, BeanResolver, and other mechanisms.

**SimpleEvaluationContext** restricts certain language capabilities and access permissions, yet can still use TypeConverter to support conversion in permitted operations. Converters can be configured via the builder appropriate for the Spring version in use.

Do not assume a restricted context automatically validates data better. Reducing access permissions and validating values are two distinct concerns. Choose the context based on required expression capabilities, then design validation in the application layer.

## 17. Testing Conversion and Validation

Test both parts separately to pinpoint exactly where errors occur.

| Input Data | Conversion | Validation Example |
|---|---|---|
| "5" | Succeeds to Integer 5 | Valid if range is 1–10 |
| "25" | Succeeds to Integer 25 | Invalid if range is 1–10 |
| "abc" | Fails converting to Integer | Does not reach numeric range validation |
| null | Depends on converter and target type | May be invalid if field is required |
| "" | Depends on converter | May be invalid if value is required |
| "-1" | Succeeds to Integer -1 | Invalid if quantity must be positive |
| "2026-02-30" | Date parsing may fail | Does not reach deadline check |
| Valid date yet already expired | Succeeds | Invalid by business rule |
| BigDecimal "999999.99" | Succeeds | May exceed limit |

Test groups should cover:

- Supported source and target types.
- Unsupported types or malformed data.
- Null, empty strings, and whitespace-only strings.
- Values exactly on min/max boundaries and just outside boundaries.
- Values that convert yet violate business rules.
- Custom converters.
- Locale, timezone, and date/number formats.
- Generic-typed collections.
- Conversion in getValue, property assignment, and method invocation.
- Validation errors returned with the right fields and messages.

## 18. Key Takeaways

Conversion changes the type or representation of data. Validation checks whether data satisfies structural requirements, value ranges, cross-field relationships, and business rules. A value that converts successfully can still be invalid.

SpEL uses the EvaluationContext's TypeConverter when it needs to convert results, property assignments, or method arguments to target types. StandardTypeConverter can work with Spring ConversionService; custom converters help normalize custom business types. TypeDescriptor supplies additional metadata when converting collections, Maps, or properties.

Do not use canConvert as a validity check. Separate conversion errors from validation errors, explicitly define how null and empty strings are handled, and run validation after data has been interpreted as the desired type. For cross-field rules, access control, and business state, use Bean Validation, Spring Validator, or appropriate Java services.

SpEL should support conversions and short expression conditions. Validating input data, authorizing access, and deciding whether to execute an action remain the application's responsibility.

## References

- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [TypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeConverter.html)
- [StandardTypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeConverter.html)