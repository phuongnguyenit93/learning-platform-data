# Testing Binding with Missing, Null, and Wrong-Type Data in SpEL

## 1. Purpose of Testing Data Binding

Data binding transfers input data into object properties. In a Spring application, data can come from requests, configuration, forms, or an intermediate object. Scenarios that must be tested include not only valid data, but also omitted fields, null values, empty strings, and values that cannot be converted to the target type.

SpEL can write properties via expressions and EvaluationContext. When an expression assigns a value to a property whose type differs from the input value, SpEL uses the context's TypeConverter to convert when possible.

For example, an expression writing a String to an Integer property:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("quantity");
expression.setValue(context, target, "12");
~~~

A binding test should verify three things:

- The target object receives the expected value when data is valid.
- The object retains an appropriate state when data is omitted or its value is null.
- Wrong-type data reports an error per contract rather than silently producing an invalid business value.

Distinguish SpEL property binding from Spring DataBinder. SpEL evaluates a specific expression and performs the operation described by that expression. DataBinder binds a set of property values onto an object and provides BindingResult to report binding errors. Both mechanisms may share Spring's conversion infrastructure, yet error observation and operational scope differ.

## 2. Preparing the Target Object for Tests

Fixtures should be small, have clear property getters/setters, and include the data types needing verification. Use wrappers like Integer or Boolean when a property can receive null; primitive types like int and boolean cannot store null.

~~~java
public class BindingTarget {
    private String name = "Existing";
    private Integer quantity = 5;
    private Boolean enabled = true;
    private int retryCount = 2;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

The initial values are intentional:

- name already has a value to verify an omitted field remains unchanged.
- quantity is Integer so valid numbers, null, and non-numeric strings can all be tested.
- enabled is a Boolean wrapper to distinguish false from null.
- retryCount is primitive int to illustrate the limitation when null data is assigned to a primitive.

Do not use one overly large object for every test. Small fixtures make clear which property is being bound and which state must be verified.

## 3. Creating SimpleEvaluationContext for Data Binding

When an expression only needs to read or write properties, SimpleEvaluationContext is a more restricted choice than StandardEvaluationContext. Data binding builders configure suitable property accessors:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

For tests that only read properties:

~~~java
SimpleEvaluationContext readOnlyContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

SimpleEvaluationContext does not enable full SpEL capabilities such as type references or broad method resolution by default. It is the right choice when the goal is property data binding and restricting expression capabilities.

If a test needs a custom ConversionService, attach the service to the builder:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Create the context with the exact permissions the expression needs. If only testing property binding, there is no need to grant extra type access or method execution.

## 4. Testing Binding with Valid Data

Start with valid data to confirm the expression can write properties and convert values when needed:

~~~java
@Test
void bindsStringValueToIntegerProperty() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    expression.setValue(context, target, "12");

    assertEquals(Integer.valueOf(12), target.getQuantity());
}
~~~

The expression targets the quantity property of type Integer. The input value is String "12"; the default conversion service can convert String to Integer.

You can test a String property that needs no conversion:

~~~java
@Test
void bindsStringProperty() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    new SpelExpressionParser()
            .parseExpression("name")
            .setValue(context, target, "Lan");

    assertEquals("Lan", target.getName());
}
~~~

These tests confirm the baseline path before testing missing, null, or wrong-type data.

## 5. Missing Data Differs from Null Values

Missing data means the input does not contain that property. With no bind operation on the property, the target object's current value is usually preserved.

A null value means the input contains the property, yet its value is null. If the binder performs a null assignment and the target property permits null, the previous value can be replaced with null.

These two cases should not be conflated:

| Input | Expected Binding Behavior |
|---|---|
| Missing key name | No assignment to name; keep current value |
| Key name present with value null | Perform null assignment if binder/target allows |
| Key name present with empty string | Assign empty string or apply separate empty-value rules |
| Key name present with valid string | Convert and assign the corresponding value |

In tests, construct inputs omitting the property to simulate an omitted field. Do not substitute null for missing data in fixtures, because that tests a different scenario.

## 6. Testing Missing Properties with Spring DataBinder

DataBinder accepts property values and binds them into the target object. If a property does not appear in MutablePropertyValues, the binder has no value to assign to that property.

~~~java
@Test
void missingPropertyKeepsExistingValue() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("enabled", "false");

    binder.bind(values);

    assertEquals("Existing", target.getName());
    assertEquals(Boolean.FALSE, target.getEnabled());
    assertFalse(binder.getBindingResult().hasFieldErrors("name"));
}
~~~

This test only sends enabled. The name property does not appear in the input, so the initial value "Existing" is preserved.

This is usually the desired behavior for partial updates: clients only send the fields they want to change. If the application needs to distinguish a field absent from the request from a field present as null, preserve presence information from the request mapping or binding layer instead of only inspecting values after binding.

## 7. Testing Null with Wrapper Properties

Properties using wrappers like Integer, Boolean, or a reference type can receive null if setters and business rules permit it.

With DataBinder:

~~~java
@Test
void explicitNullClearsNullableProperty() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", null);

    binder.bind(values);

    assertNull(target.getQuantity());
    assertFalse(binder.getBindingResult().hasFieldErrors("quantity"));
}
~~~

Here quantity is present in the input and its value is null. The binder binds onto the wrapper property, clearing the previous value unless constraints or setter logic reject null.

Null can be tested directly through SpEL:

~~~java
@Test
void spelCanSetNullablePropertyToNull() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    expression.setValue(context, target, null);

    assertNull(target.getQuantity());
}
~~~

This test verifies the expression can write null into a reference-type property. If the application forbids null, test validation or setter contracts separately. Being able to assign null at the binding layer does not mean that value is business-valid.

## 8. Testing Null with Primitive Properties

Primitives like int and boolean cannot represent null. If the input has the key with a null value, converting/assigning to a primitive may fail or require an explicit policy in the binding layer.

Do not assume a primitive automatically becomes zero or false without checking the exact API behavior in use. Write tests against the actual Spring version and configuration:

~~~java
@Test
void reportsNullForPrimitivePropertyAccordingToBindingPolicy() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("retryCount", null);

    binder.bind(values);

    // Assert BindingResult and target value according to the application's policy.
    // If null is not allowed, expect a field error or validation error.
}
~~~

For request models that must distinguish omitted fields from explicitly sent null, wrappers are usually more suitable than primitives. For example, Integer can represent both "no value yet" and the number 0. Validation or business logic then decides whether null is accepted.

If the application needs a default of 0 when a field is missing, apply the default in the DTO, binding, or service layer under explicit rules. Do not let a primitive's default accidentally mask that the client sent null.

## 9. Testing Empty Strings and Whitespace

An empty string is not the same as null. For String properties, an empty string is usually bound as the empty string itself. For numeric, Boolean, or business domain properties, empty strings may be handled by a conversion service, property editor, or binder configuration.

Example with String:

~~~java
@Test
void bindsEmptyStringAsEmptyString() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("name", "");

    binder.bind(values);

    assertEquals("", target.getName());
}
~~~

Whitespace also needs separate testing if the application trims data:

~~~java
MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "   ");

DataBinder binder = new DataBinder(new BindingTarget());
binder.bind(values);
~~~

DataBinder should not be assumed to automatically trim every String. If business requirements call for stripping whitespace, configure StringTrimmerEditor or handle normalization intentionally, then test the post-binding result.

Example registering an editor for String:

~~~java
binder.registerCustomEditor(
        String.class,
        new StringTrimmerEditor(true));
~~~

The true parameter requests that an empty string after trimming be converted to null. Therefore, the outcome of whitespace can differ from an empty string when no editor is registered. Document this policy clearly in tests.

## 10. Testing Wrong-Type Data with SpEL

When an expression assigns a String that cannot convert to the target property type, SpEL may throw EvaluationException, usually a SpelEvaluationException containing conversion failure details.

For example, quantity is Integer while the input is non-numeric:

~~~java
@Test
void rejectsInvalidNumberInSpelBinding() {
    BindingTarget target = new BindingTarget();

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding().build();

    Expression expression =
            new SpelExpressionParser().parseExpression("quantity");

    assertThrows(
            EvaluationException.class,
            () -> expression.setValue(context, target, "twelve"));

    assertEquals(Integer.valueOf(5), target.getQuantity());
}
~~~

The test verifies invalid data is not written as a new value. The old value stays intact if conversion fails before the setter is invoked.

In error-handling code, more specific exceptions can be checked if the application depends on SpEL error codes. Avoid depending on full message text because message wording can vary across versions or locales.

## 11. Testing Wrong Types with DataBinder and BindingResult

DataBinder usually collects conversion errors into BindingResult instead of requiring tests to catch exceptions directly. When a String cannot convert to Integer, the field error usually has the code typeMismatch.

~~~java
@Test
void recordsTypeMismatchForInvalidInteger() {
    BindingTarget target = new BindingTarget();
    DataBinder binder = new DataBinder(target);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", "twelve");

    binder.bind(values);

    BindingResult result = binder.getBindingResult();

    assertTrue(result.hasFieldErrors("quantity"));
    assertEquals("typeMismatch", result.getFieldError("quantity").getCode());
    assertEquals(Integer.valueOf(5), target.getQuantity());
}
~~~

Important outcomes to verify:

- BindingResult has a field error on quantity.
- The error code reflects a type mismatch.
- The property is not overwritten with a wrong value.
- The old value remains intact if conversion fails before assignment.

DataBinder lets the application display errors per field and return appropriate form/request validation responses. With direct SpEL setValue, errors usually surface as exceptions during evaluation. Therefore, do not use the same assertions for both APIs.

## 12. Integrating ConversionService in Binding Tests

When the application registers custom converters, tests should use the exact ConversionService that production configuration provides:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToMoneyConverter());
~~~

With SpEL:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();

Expression expression =
        new SpelExpressionParser().parseExpression("amount");

expression.setValue(context, invoice, "125.50");
~~~

With DataBinder:

~~~java
DataBinder binder = new DataBinder(invoice);
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("amount", "125.50");

binder.bind(values);
~~~

Using the same ConversionService gives both flows shared conversion rules, yet each API still needs separate tests. SpEL tests confirm EvaluationContext's TypeConverter uses the service; DataBinder tests confirm the binder is configured with that service and reports errors through BindingResult.

## 13. Testing Validation After Binding

Binding and validation are two distinct steps. Binding transfers data into the object; validation checks whether the object satisfies business rules.

For example, the quantity property can bind to a type-valid Integer that is invalid for its value range:

~~~java
public class QuantityForm {
    @Min(1)
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

A test can bind the value 0 and then run the validator:

~~~java
@Test
void validatesBoundValueAfterConversion() {
    QuantityForm form = new QuantityForm();
    DataBinder binder = new DataBinder(form);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("quantity", "0");

    binder.bind(values);
    binder.validate();

    assertEquals(Integer.valueOf(0), form.getQuantity());
    assertTrue(binder.getBindingResult().hasFieldErrors("quantity"));
}
~~~

The value "0" converts to Integer successfully, yet violates @Min(1). This is a validation error, distinct from a type mismatch when a string cannot convert to Integer.

If using JSR-303/Bean Validation, the application needs a matching validator on the classpath configured in the binder. In integration tests, use the same validator configuration as the real application.

## 14. Building a Test Matrix for Missing, Null, and Wrong Types

A compact matrix helps avoid missing critical cases:

| Case | Input | Outcome to Verify |
|---|---|---|
| Missing | Property absent | Existing value preserved |
| Explicit null | Property present, value null | Wrapper property receives null if permitted |
| Empty String | Property present, value is empty string | Follows property type and editor/converter |
| Whitespace | Property present, whitespace only | Follows trim/normalization policy |
| Valid type text | E.g. "12" for Integer | Conversion succeeds |
| Invalid type text | E.g. "twelve" for Integer | EvaluationException in SpEL or field error in DataBinder |
| Valid but rejected by validation | E.g. 0 for @Min(1) | Binding succeeds, validation error |
| Null to primitive | Null for int/boolean | Follows binding policy; verify error or explicitly configured default |

Not every property needs every test case. Choose from the matrix based on data type, DTO contract, and actual binding policy. For nullable properties, test null; for numeric properties, test valid and invalid strings; for Strings, test empty and whitespace if normalization applies.

## 15. Testing Without Confusing Missing Data with Null

A common mistake is building request fixtures by initializing every key with a null value. That simulates "key present with null value", not "missing key".

For example:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("name", null);
~~~

The map above contains the key name. If you want to simulate a missing field, do not add the key:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("quantity", "12");
~~~

When converting a Map to MutablePropertyValues, only properties present in the map are sent to the binder. If a request parser or framework instantiates a DTO before binding, check how it preserves field presence information; a DTO pre-initialized with nulls may not suffice to distinguish missing from explicit null.

For PATCH APIs, this distinction is especially important. Missing usually means "do not change"; explicit null can mean "clear the value". Test at the actual request-receiving layer to confirm those semantics are not lost before the binder runs.

## 16. Restricting Properties Allowed to Be Bound

Data binding can mutate object state. Clients should not be allowed to arbitrarily bind every property of a domain object, especially sensitive fields such as role, owner, internal status, or audit metadata.

DataBinder supports restricting properties via allowed fields:

~~~java
DataBinder binder = new DataBinder(target);

binder.setAllowedFields("name", "quantity", "enabled");
~~~

Afterward, only properties on the allowed list are bound. Test both permitted fields and fields excluded from binding scope according to application policy.

With SpEL, restrict expressions and EvaluationContext appropriately for the intended purpose. Use SimpleEvaluationContext with suitable property access when only data binding is needed; do not evaluate untrusted expressions with a context holding broader permissions than necessary.

## 17. Comprehensive Example with JUnit 5

The following example tests missing field, explicit null, and type mismatch with DataBinder:

~~~java
class BindingInputTest {

    @Test
    void missingFieldLeavesTargetUnchanged() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("enabled", "false");

        binder.bind(values);

        assertEquals("Existing", target.getName());
        assertEquals(Boolean.FALSE, target.getEnabled());
        assertFalse(binder.getBindingResult().hasFieldErrors());
    }

    @Test
    void explicitNullClearsNullableField() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", null);

        binder.bind(values);

        assertNull(target.getQuantity());
        assertFalse(binder.getBindingResult().hasFieldErrors());
    }

    @Test
    void invalidNumberProducesFieldError() {
        BindingTarget target = new BindingTarget();
        DataBinder binder = new DataBinder(target);

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", "twelve");

        binder.bind(values);

        assertEquals(Integer.valueOf(5), target.getQuantity());
        assertTrue(binder.getBindingResult().hasFieldErrors("quantity"));
    }
}
~~~

All three tests use the same fixture yet construct separate inputs for each state. The missing test omits name; the null test adds quantity with value null; the wrong-type test adds quantity with an unconvertible string.

For direct SpEL usage, separate tests can be added for setValue with SimpleEvaluationContext to confirm expressions use the right property path and conversion service. Do not infer SpEL's exception behavior from DataBinder's BindingResult.

## 18. Common Errors

**Treating missing and explicit null as the same**

Omitting a key means the binder has no property value to assign. Having a key with null means a null bind operation occurs. Create separate inputs for the two situations.

**Using primitives for properties that must represent null**

int and boolean cannot store null. Use Integer or Boolean when null must be distinguished from 0 or false.

**Assuming wrong types always fail the request immediately**

DataBinder usually records errors in BindingResult; SpEL setValue usually throws EvaluationException. Check the exact mechanism being used.

**Checking only errors without checking the target object**

When conversion fails, verify the old value is not overwritten with bad data. When null is accepted, verify the property is actually cleared.

**Confusing conversion errors with validation errors**

The string "twelve" failing to convert to Integer is a type mismatch. The number 0 converting to Integer successfully yet violating @Min(1) is a different case requiring different assertions.

**Assuming an empty string is always null**

An empty String is a distinct value. Only when a converter, property editor, or normalization policy exists is it converted to null.

**Not checking ConversionService configuration**

A context or binder using a different service may produce different conversion results. In integration tests, use the exact converter configuration deployed by the application.

## 19. Takeaways

- Test binding with at least three states: missing property, property with null value, and property with wrong-type value.
- Missing fields usually produce no assignment, so the existing value is preserved.
- Explicit null can clear a reference-type property's value if the binding policy allows it.
- Primitives cannot represent null; use wrappers when nullable state is required.
- SpEL writes properties via Expression.setValue and EvaluationContext's TypeConverter.
- SimpleEvaluationContext.forReadWriteDataBinding suits expressions needing only property data binding.
- DataBinder binds MutablePropertyValues and reports conversion errors via BindingResult.
- With SpEL, check exceptions when conversion fails; with DataBinder, check field errors and object state.
- Distinguish type mismatch from validation errors after successful conversion.
- Test empty String, whitespace, and custom ConversionService according to application policy.
- Restrict properties allowed to be bound and do not evaluate untrusted expressions with an overly permissive context.
