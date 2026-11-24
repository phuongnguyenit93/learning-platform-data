# Limiting Implicit Conversion to Avoid Unexpected Results in SpEL

Spring Expression Language (SpEL) can automatically convert types when an operation needs a value in a type different from the data's runtime type. This mechanism is called implicit conversion: the application supplies a value, and SpEL uses the EvaluationContext's TypeConverter to convert it when a matching converter exists.

Implicit conversion makes expressions flexible, yet it can also hide data errors. A string can be converted to a number, or a value can be converted to a method parameter type or target property type. If the conversion does not match the business meaning, the expression may still execute yet produce wrong or hard-to-explain results.

This lesson focuses on where SpEL performs implicit conversion, how TypeConverter and Spring ConversionService collaborate, the risks of allowing too many conversions, and how to limit conversion rules so data types remain explicit.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Explain implicit conversion in SpEL.
- Distinguish runtime data types from types requested by target expressions or methods.
- Recognize the roles of TypeConverter and ConversionService.
- Identify places where automatic conversion commonly occurs: property assignment, method arguments, and result types.
- Understand why overloads and overly broad converters can make behavior unpredictable.
- Keep input data types stable and validate before evaluating.
- Configure narrowly scoped converters for EvaluationContext.
- Test successful conversion, failing conversion, and cases that are type-valid yet business-invalid.

You should know how to create SpelExpressionParser, Expression, EvaluationContext, JavaBean properties, method overloads, and Spring ConversionService.

## 2. What Is Implicit Conversion?

Suppose a Java property has type boolean, yet the application supplies a String value:

~~~java
public class FeatureConfig {
    private boolean enabled;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

It can be assigned with SpEL:

~~~java
FeatureConfig config = new FeatureConfig();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("enabled");

expression.setValue(config, "true");
~~~

If the active TypeConverter supports String-to-Boolean conversion, the string value is converted to boolean before invoking the setter. Afterward, config.isEnabled() returns true.

The caller did not invoke Boolean.parseBoolean directly; the conversion was performed through SpEL's conversion mechanism.

Implicit conversion can occur whenever an operation has an explicit target type. For example:

- Property assignment needs a value matching the property type.
- Method invocation needs arguments compatible with parameter types.
- getValue(context, TargetType.class) requests the result in a target type.
- Certain data binding or collection operations need element conversion according to TypeDescriptor.

Do not assume every SpEL operator automatically converts any type to any other type. Exact rules depend on the operator, source type, target type, and available converters.

## 3. TypeConverter and ConversionService

EvaluationContext supplies TypeConverter so SpEL can ask whether a value can be converted from a source type to a target type and perform the conversion.

In Spring, StandardTypeConverter is the adapter connecting SpEL to Spring ConversionService. StandardEvaluationContext has a standard TypeConverter by default; applications can replace it if a different conversion policy is needed.

Each component has a distinct role:

| Component | Responsibility |
|---|---|
| TypeConverter | The API SpEL uses to check and perform conversions |
| ConversionService | Spring mechanism managing converters and conversion rules |
| Converter | Converts one specific source type to one target type |
| ConverterFactory | Creates converters for a family of target types |
| GenericConverter | Supports multiple type pairs and can use TypeDescriptor |
| TypeDescriptor | Carries type information, including generic metadata of a property or collection |

SpEL works with the TypeConverter inside EvaluationContext. Applications can use Spring's ConversionService to register standard or domain-specific converters.

## 4. Conversion During Property Assignment

A common place is Expression.setValue(...). The property type determines the target type SpEL needs to write.

~~~java
public class Account {
    private int retryCount;

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

For example:

~~~java
Account account = new Account();

Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(account, "5");
~~~

If the default converter supports String to Integer, the setter receives the numeric value 5. If the string cannot be converted to a number, the write operation fails during conversion.

A writable property does not mean every value can be assigned. Distinguish:

1. Whether PropertyAccessor has permission to write the property.
2. Whether TypeConverter can convert the value to the property type.
3. Whether the setter or business layer accepts the converted value.

For example, the string "-1" can convert to int successfully, yet the setter or business validation may still reject a negative retryCount.

## 5. Argument Conversion When Calling Methods

SpEL can use TypeConverter to convert arguments to method parameter types once the resolver finds a matching invocation.

Example method accepting BigDecimal:

~~~java
public class PriceCalculator {
    public BigDecimal applyRate(BigDecimal rate) {
        return rate.multiply(new BigDecimal("100"));
    }
}
~~~

If the rate variable is supplied as a String and the context has a matching converter, the call can be converted:

~~~java
context.setVariable("rate", "0.15");

Expression expression =
    parser.parseExpression("#calculator.applyRate(#rate)");
~~~

For this example to work, calculator must be provided in the context and TypeConverter must support String to BigDecimal. In real applications, it is better to pass BigDecimal from Java if the data already has that type.

### 5.1. Overloads Increase Complexity

Suppose a class has multiple methods with the same name:

~~~java
public String format(Integer value) { ... }

public String format(BigDecimal value) { ... }

public String format(String value) { ... }
~~~

When an expression calls format with a value of another type, the method resolver and conversion can both participate in selecting a matching call. The outcome may differ from what a reader infers purely from the string contents.

To reduce surprises:

- Avoid excessive overloading on methods exposed to SpEL.
- Use distinct method names for each purpose if types carry different meanings.
- Pass variables with the right runtime types rather than relying on conversion.
- Test every signature and supported input type.
- Do not use overly broad converters that make every call appear valid.

## 6. Converting Result Types

An expression can be asked to return a specific type:

~~~java
Expression expression =
    parser.parseExpression("#quantity");

context.setVariable("quantity", 12);

String result =
    expression.getValue(context, String.class);
~~~

SpEL can use TypeConverter to convert the result to String if the conversion service supports it.

This differs from the expression itself producing a string internally. The expression returns a value in its runtime type; the getValue(context, TargetType.class) overload requests converting the result to the target type.

Choose explicit result types so Java code reflects the intended contract. If conversion is unsupported or fails, handle the error at the application boundary instead of assuming the result always matches the expected type.

## 7. Conversion in Collections and Generic Properties

TypeDescriptor helps Spring preserve property type information, including generic element types in certain data binding scenarios.

Example property:

~~~java
public class Preferences {
    private List<Boolean> flags;

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

When writing a List element, the target type can be identified as Boolean:

~~~text
flags[0]
~~~

If the application assigns the string "true" to that element and the conversion service supports it, the value can be converted to Boolean.

However, do not rely on generic metadata when the model declares raw collections or overly general element types. If the property is declared only as List or List<Object>, target type information may be insufficient to apply the intended conversion.

For collections receiving external data, validate each element and the collection size. Successful conversion does not mean the collection contents are business-valid.

## 8. Risks of Overly Broad Implicit Conversion

### 8.1. Strings Can Hide Invalid Data

A data field may arrive as a String when business logic expects a number, date, or enum. If a converter manages to convert it, data contract errors may go undetected at the receiving end.

For example, the string "0012" can convert to the number 12. If leading zeros are meaningful as an identifier, converting to Number loses information.

Distinguish quantitative data from identifier data. Account numbers, postal codes, or product codes should usually remain Strings even when they contain only digits.

### 8.2. Type-Valid Conversion That Is Semantically Wrong

Converting the string "false" to Boolean false is type-valid. Yet if the system treats an empty string or "unknown" as meaning undetermined, automatically turning it into false can alter logic.

Similarly, converting decimals to integers can lose fractional parts or clash with business rounding rules. Do not use default conversion to decide rounding policies, currency rules, or measurement units.

### 8.3. Locale, Timezone, and Format

Conversions of dates, times, and decimal numbers can depend on configured formatters, locales, or timezones. A date string can be interpreted differently if day/month formats are inconsistent.

For date and time data:

- Choose an explicit input format, preferably following an appropriate ISO standard.
- Determine the timezone at the application boundary.
- Do not rely on the server's default locale.
- Test ambiguous values such as dates readable as either dd/MM or MM/dd.

### 8.4. Custom Converters Can Perform Unexpected Behavior

A converter is Java code. If a converter queries a database, calls a network service, or mutates state, a seemingly simple evaluation can trigger side effects.

Prefer pure converters: receive a value, validate it, and return a new value. Do not use converters to perform business workflows, I/O, or external resource queries.

### 8.5. Overloads and Conversion Together Affect Outcomes

A String value can convert to multiple different parameter types. If a method has multiple overloads, the final selection can become hard to predict as APIs evolve.

Keep methods exposed to SpEL small and clearly typed. If complex logic is needed, move processing into a facade with a single method taking specific parameter types.

## 9. Limiting Conversion by Passing Properly Typed Data

The simplest and easiest-to-control approach is converting data in the Java layer before putting it into EvaluationContext.

Instead of:

~~~java
context.setVariable("amount", request.getParameter("amount"));
~~~

parse and validate beforehand:

~~~java
BigDecimal amount =
    new BigDecimal(request.getParameter("amount"));

context.setVariable("amount", amount);
~~~

The example above only illustrates valid numeric strings; production code must catch parse errors and enforce business limits.

Once the variable has type BigDecimal, expressions can perform arithmetic without relying on runtime String-to-Number conversion.

Principles:

- Parse data at the input boundary.
- Validate type, value range, and units before evaluating.
- Pass validated DTOs into the context.
- Keep variable types stable across evaluations.
- Use String for identifiers and Number for quantities used in calculations.
- Do not rely on implicit conversion to fix input data that violates the contract.

## 10. Configuring ConversionService Explicitly

StandardTypeConverter can be configured with a specific ConversionService:

~~~java
ConversionService conversionService =
    new DefaultConversionService();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

This ensures the context uses the conversion policy chosen by the application. If custom converters are needed, register them in ConversionService before using it with StandardTypeConverter.

Example domain converter:

~~~java
public final class CurrencyCode {
    private final String value;

    public CurrencyCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Registering String-to-CurrencyCode conversion:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    source -> new CurrencyCode(source.trim().toUpperCase(Locale.ROOT))
);
~~~

Then create a TypeConverter from that conversion service and attach it to EvaluationContext.

The converter above only illustrates normalizing a currency code. Real applications must verify the code belongs to the set of supported values; case conversion does not replace validation.

## 11. Building a Restricted Conversion Policy

If expressions are only permitted to convert certain type pairs, you can use a dedicated ConversionService registering only required converters, or wrap TypeConverter to reject type pairs outside an allowlist.

A restricted policy should define:

- Which source types are accepted.
- Which target types are allowed.
- Whether collection and nested element conversions are permitted.
- Whether String-to-Number, Boolean, or enum conversions are permitted.
- Whether specific date/time formats are required.
- Whether string lengths and value bounds are restricted.
- Which conversions are only for binding versus permitted inside expressions.

There is no universal toggle switch that replaces defining a policy per use case. If strict behavior is desired, supply a narrow TypeConverter/ConversionService and pass accurately typed data.

With SimpleEvaluationContext, the builder can accept a specific ConversionService:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withConversionService(conversionService)
        .build();
~~~

Choose the context and conversion service according to exact requirements. Read-only restricts property writing; it does not automatically ensure every conversion is valid in business terms.

## 12. Handling Conversion Errors

Conversion can fail because:

- No converter exists for the source/target type pair.
- String format is invalid.
- Value exceeds the target type's range.
- Collection contains an unconvertible element.
- Custom converter rejects the data.
- Setter or method continues validation and throws an exception.

Handle errors at the application boundary:

1. Identify the input data and target type.
2. Check whether the conversion service supports that type pair if needed.
3. Catch conversion errors and translate them into appropriate validation errors.
4. Do not silently proceed with a default value when business logic requires reporting an error.
5. Do not return stack traces or internal details to clients.
6. Log in a controlled manner, avoiding logging sensitive data.

Do not catch every exception and return null or 0. That hides data errors and makes the system hard to diagnose.

## 13. Testing Implicit Conversion

A test suite should include:

| Case | Input | What to Verify |
|---|---|---|
| String to Boolean | "true" | Converts properly if converter is configured |
| String to integer | "12" | Converts properly to the target type |
| Invalid numeric string | "twelve" | Conversion fails clearly |
| String to BigDecimal | "12.50" | Preserves exact decimal value per converter |
| Property assignment value | String for boolean/int property | Setter receives the right type after conversion |
| Method argument | String for BigDecimal parameter | Converts only when resolver and converter support it |
| Expression result | Number requesting String | Result converts according to TypeConverter |
| Generic collection | String for Boolean element | Verify generic TypeDescriptor is used properly |
| Identifier with leading zeros | "0012" | Not accidentally converted to a number if identifier must be preserved |
| Ambiguous date | Date strings across multiple formats | Format/locale is clearly defined |
| Custom converter rejection | Invalid code | Validation error propagates properly |
| Overload | Multiple methods with the same name | Right method is selected or rejected per policy |

In addition to return values, check runtime types and object state after assignment. For normalizing converters, test both valid and invalid inputs.

## 14. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| Property assignment fails | No converter to property type | Provide properly typed data or required converter |
| Method is not called | Incompatible argument or unclear overload | Check signatures and variable types |
| Value changes unexpectedly | Conversion is type-valid yet semantically wrong | Validate per domain before putting into context |
| Leading zeros lost | Identifier converted to Number | Keep identifiers as String |
| Wrong date or decimal number | Inconsistent locale/format | Configure format and timezone explicitly |
| Conversion works in one context but not another | Two contexts use different TypeConverters | Inspect EvaluationContext configuration |
| Converter causes side effects | Converter contains I/O or business logic | Keep converters pure and move business logic to services |
| Error occurs only with collections | Missing generic metadata or invalid element | Inspect TypeDescriptor and collection types |

## 15. Practice Exercises

1. Create a boolean property and assign a String value via Expression.setValue; observe conversion.
2. Create an int property and test both a valid numeric string and an invalid string.
3. Call a method taking BigDecimal with a String variable, then change the variable to BigDecimal.
4. Create two overloads with the same name and observe behavior when input has type String.
5. Request getValue(context, String.class) for an expression returning Number.
6. Create a custom ConversionService with a domain converter.
7. Test an identifier with leading zeros and confirm it is not converted to a number.
8. Create a context using a narrow converter and verify type pairs outside the allowlist are rejected.
9. Write tests for dates, locales, and out-of-range values.
10. Verify converters perform no I/O or external state mutation.

## 16. Checklist Before Allowing Implicit Conversion

- [ ] Have runtime types of each variable been identified?
- [ ] Have target types of properties, methods, or results been identified?
- [ ] Can properly typed data be passed directly from Java?
- [ ] Is the context's TypeConverter explicitly configured?
- [ ] Does ConversionService contain converters broader than needed?
- [ ] Are there overloads making method selection with conversion unpredictable?
- [ ] Could identifiers be mistakenly converted to Numbers?
- [ ] Are locale, timezone, format, and rounding defined?
- [ ] Are custom converters pure and side-effect-free?
- [ ] Have successful conversions, failures, and business-invalid cases been tested?
- [ ] Are conversion errors handled at the application boundary?
- [ ] Does the context permit only the necessary conversions?

## 17. Conclusion

Implicit conversion allows SpEL to convert values to the types required by properties, methods, or result consumers when TypeConverter has matching rules. StandardTypeConverter connects SpEL to Spring ConversionService, where applications can manage standard and custom converters. Overly broad conversion can hide bad data, lose identifier information, cause overload ambiguity, or depend on locale. Prefer passing already-typed data, validating at the application boundary, configuring ConversionService on an allowlist basis when needed, and testing both result types and business meaning.