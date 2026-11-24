# Testing Conversion, Binding, and Type Errors

When using SpEL in an application, an expression can parse successfully yet still fail during evaluation because the actual value has the wrong type, cannot be converted, or the target property is not writable. Therefore, SpEL testing needs to confirm both valid outcomes and how the system responds to invalid data.

Three scopes to distinguish are conversion of the result value, conversion of arguments during method invocation, and conversion when assigning a property via setValue. Each operation passes through TypeConverter and EvaluationContext, yet execution paths and errors can differ. A good test suite verifies each boundary separately, and only then tests how they work together in real Spring configuration.

## 1. What needs to be tested

An expression typically goes through these steps:

1. Parse the expression string.
2. Evaluate properties, variables, methods, or collection operations.
3. Convert arguments if the method requires different types.
4. Invoke the method or read the value.
5. Convert the result if the caller requests a target type.
6. Write the property if using setValue.

Tests should cover:

- Valid syntax and invalid syntax.
- Runtime values of the right type.
- Conversion from source type to target type.
- Application custom converters.
- Binding to JavaBean properties.
- Binding to nested properties, Maps, or Lists.
- Read-only properties and null intermediate objects.
- Invalid values, nulls, and primitives.
- Exceptions when methods or setters reject data.

Do not only test that the expression returns a value in the ideal case. Type errors often only surface when real data differs from ordinary test data.

## 2. Creating the parser and EvaluationContext in unit tests

For pure unit tests, SpelExpressionParser and EvaluationContext can be created directly:

~~~java
class SpelBindingTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();
}
~~~

SimpleEvaluationContext.forReadWriteDataBinding() is suitable when tests need to read and write JavaBean properties for data binding. If tests need functions, type references, bean references, or other features of StandardEvaluationContext, create the corresponding context and explicitly configure the required resolvers.

Keep the parser and context within a test scope or fixture with a clear lifecycle. Avoid sharing a mutable EvaluationContext across tests running in parallel if root objects and variables are modified.

## 3. Testing parse success and parse failure

Parse tests confirm the string has valid SpEL syntax and the parser produces an Expression.

~~~java
@Test
void parsesValidExpression() {
    Expression expression =
            parser.parseExpression("age >= 18");

    assertNotNull(expression);
}
~~~

Syntax errors can be checked:

~~~java
@Test
void rejectsInvalidExpression() {
    assertThrows(
            ParseException.class,
            () -> parser.parseExpression("age >")
    );
}
~~~

ParseException belongs to the Spring Expression exception hierarchy; SpelParseException is the specific form for SpEL parse errors. This test only checks syntax, not proving that the age property exists or can be converted during evaluation.

Keep parse tests separate from evaluation tests to know which phase an error occurred in.

## 4. Testing result types with typed getValue

Expression.getValue(context, TargetType.class) asks SpEL to return a value compatible with the target type and uses TypeConverter when conversion is needed.

Example:

~~~java
@Test
void convertsEvaluatedStringToInteger() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "42");

    Expression expression =
            parser.parseExpression("#raw");

    Integer result = expression.getValue(
            context,
            Integer.class
    );

    assertEquals(42, result);
}
~~~

This test confirms the string "42" can be converted into an Integer in the context in use.

Verify both type and value. If comparing only string representations, tests can miss cases where the actual result is a different type that produces the same content on toString().

For null values, verify behavior by target type. Reference types can represent null; primitives like int or boolean cannot. If an expression returns null while the caller requests a primitive, retrieving the result may fail.

## 5. Testing conversion success and failure

A conversion test should have at least one valid input and one malformed input:

~~~java
@Test
void convertsValidNumber() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "125");

    Integer result = parser.parseExpression("#raw")
            .getValue(context, Integer.class);

    assertEquals(125, result);
}

@Test
void rejectsInvalidNumber() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", "twelve");

    Expression expression = parser.parseExpression("#raw");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(context, Integer.class)
    );
}
~~~

Do not rely on a specific message text if the application has no contract on message content. Verify the exception belongs to the appropriate hierarchy and, when needed, inspect the cause or specific error code per the Spring version in use.

If the application configures a custom TypeConverter, write tests using that exact converter. Testing with the default converter does not prove the production converter is working.

## 6. Testing binding to a JavaBean property

To test setValue, create an object with getters and setters:

~~~java
public class Profile {

    private String displayName;
    private Integer age;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Test updating the property:

~~~java
@Test
void writesBeanProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression expression =
            parser.parseExpression("displayName");

    expression.setValue(context, profile, "Lan");

    assertEquals("Lan", profile.getDisplayName());
}
~~~

This test confirms the property accessor can locate and write the displayName property on the root object.

Check the object's state after setValue, instead of only confirming the call throws no exception. A write operation without an exception is not enough to prove the right property was updated.

## 7. Testing conversion when writing properties

The target property may be Integer while the value passed to setValue is a String:

~~~java
@Test
void convertsValueWhenWritingProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression age = parser.parseExpression("age");

    age.setValue(context, profile, "30");

    assertEquals(Integer.valueOf(30), profile.getAge());
}
~~~

This test verifies conversion occurring on the property-writing path.

Invalid data also needs testing:

~~~java
@Test
void rejectsInvalidValueWhenWritingProperty() {
    Profile profile = new Profile();

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression age = parser.parseExpression("age");

    assertThrows(
            EvaluationException.class,
            () -> age.setValue(context, profile, "thirty")
    );
}
~~~

The specific exception depends on the converter and accessor. Tests should verify the operation fails and the object is not left in an invalid state. If a setter could mutate state before throwing an error, verify object invariants or use a setter with appropriate atomicity.

## 8. Testing read-only properties

A property with only a getter can be read but cannot be updated via standard JavaBean data binding.

~~~java
public class ImmutableProfile {

    private final String name;

    public ImmutableProfile(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Failed write test:

~~~java
@Test
void cannotWriteReadOnlyProperty() {
    ImmutableProfile profile =
            new ImmutableProfile("Lan");

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression name = parser.parseExpression("name");

    assertThrows(
            EvaluationException.class,
            () -> name.setValue(context, profile, "Minh")
    );

    assertEquals("Lan", profile.getName());
}
~~~

This test helps distinguish readable properties from writable properties. For immutable objects, create a new instance via constructor or factory rather than using setValue.

## 9. Testing nested properties

A property path can traverse multiple objects:

~~~java
public class Address {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class CustomerProfile {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Test updating a child property:

~~~java
@Test
void writesNestedProperty() {
    CustomerProfile profile = new CustomerProfile();
    profile.setAddress(new Address());

    EvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .build();

    Expression city =
            parser.parseExpression("address.city");

    city.setValue(context, profile, "Da Nang");

    assertEquals(
            "Da Nang",
            profile.getAddress().getCity()
    );
}
~~~

The intermediate object must exist and be accessible. Do not assume SpEL will automatically instantiate Address when profile.address is null. Have a separate test for a null intermediate object and verify the error or auto-grow behavior matches the application's actual configuration.

## 10. Testing Map and List binding

An indexer can update a Map entry or collection element if the target is mutable and the accessor supports it.

Map example:

~~~java
@Test
void writesMapEntry() {
    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "light");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("settings", settings);

    Expression theme =
            parser.parseExpression("#settings['theme']");

    theme.setValue(context, "dark");

    assertEquals("dark", settings.get("theme"));
}
~~~

List of objects example:

~~~java
@Test
void writesPropertyOfListElement() {
    List<Profile> profiles = new ArrayList<>();
    profiles.add(new Profile());

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("profiles", profiles);

    Expression name =
            parser.parseExpression("#profiles[0].displayName");

    name.setValue(context, "Minh");

    assertEquals("Minh", profiles.get(0).getDisplayName());
}
~~~

Also test out-of-bounds indices, immutable Maps, or wrong key types if those scenarios can occur in the application. Do not use an immutable collection in tests expected to write successfully.

## 11. Testing custom Converters

If the application has custom domain types, verify the registered converter is used by EvaluationContext.

AccountCode type example:

~~~java
public record AccountCode(String value) {
}
~~~

Creating ConversionService and context:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        AccountCode.class,
        AccountCode::new
);

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withTypeConverter(
                        new StandardTypeConverter(conversionService)
                )
                .build();
~~~

Test:

~~~java
@Test
void usesCustomConverterForTypedResult() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(
            String.class,
            AccountCode.class,
            AccountCode::new
    );

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

    context.setVariable("rawCode", "AC-100");

    AccountCode result = parser.parseExpression("#rawCode")
            .getValue(context, AccountCode.class);

    assertEquals(new AccountCode("AC-100"), result);
}
~~~

In real tests, use the exact context type the use case requires. The example above uses StandardEvaluationContext to illustrate direct TypeConverter configuration; for restricted data binding, the converter can be configured via SimpleEvaluationContext's builder.

In addition to valid cases, test that the converter rejects empty strings or invalid formats if the domain type has formatting rules. A converter should not silently create invalid objects.

## 12. Testing conversion of method arguments

SpEL can convert arguments before calling a method if TypeConverter supports it.

~~~java
public class NumberOperations {

    public Integer doubleValue(Integer value) {
        return value * 2;
    }
}
~~~

Test:

~~~java
@Test
void convertsArgumentBeforeMethodInvocation() {
    NumberOperations operations = new NumberOperations();

    StandardEvaluationContext context =
            new StandardEvaluationContext(operations);

    Expression expression =
            parser.parseExpression("doubleValue('21')");

    Integer result = expression.getValue(
            context,
            Integer.class
    );

    assertEquals(42, result);
}
~~~

This test checks both method resolution and argument conversion. If it fails, determine whether the error belongs to the method not being found or conversion failing to execute.

When a method has multiple parameters of the same type, tests must confirm argument order. A call can execute without type errors yet still pass parameters with swapped meanings.

## 13. Testing nulls and primitives

Null is an important case because reference types can hold null while primitives cannot.

Scenarios to verify:

- Expression returns null and caller requests String.
- Expression returns null and caller requests Integer.
- Expression returns null but caller requests int.
- Wrapper property is null and then used in an operation.
- Setter receives null and whether it accepts it or not.

Example checking typed result:

~~~java
@Test
void preservesNullForReferenceType() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("value", null);

    String result = parser.parseExpression("#value")
            .getValue(context, String.class);

    assertNull(result);
}
~~~

If a primitive cannot represent a null result, the test should verify the error appropriate for the framework version. Do not implicitly convert null to 0 or false unless business logic defines that default.

## 14. Distinguishing parse errors from conversion/binding errors

A syntactically invalid expression fails before an EvaluationContext is even involved:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("age >")
);
~~~

A valid expression with an unconvertible value will fail during evaluation:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("raw", "not-a-number");

Expression expression = parser.parseExpression("#raw");

assertThrows(
        EvaluationException.class,
        () -> expression.getValue(context, Integer.class)
);
~~~

Binding can also fail during evaluation if the property is not writable or conversion does not succeed.

Tests should confirm the right phase and error type. Do not use a single generic assertion for all exceptions if the application needs to distinguish configuration errors from data errors.

## 15. Testing validation separately from conversion

Successful conversion does not mean the value is valid per business rules. For example, the string "-5" can convert to Integer -5, yet quantity may have to be greater than 0.

~~~java
public class QuantityForm {

    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

After binding:

~~~java
quantityExpression.setValue(context, form, "5");
~~~

the application still needs validation:

~~~java
assertTrue(form.getQuantity() > 0);
~~~

In a real project, use Jakarta Bean Validation or an appropriate domain validator. Conversion tests focus on source/target types; validation tests focus on business invariants.

Do not merge the two responsibilities into a custom converter. Converters should transform data; validators decide whether that data is allowed in the domain.

## 16. Testing Spring integration for @Value and bean binding

Direct Expression unit tests do not verify Spring's full @Value injection or bean initialization mechanism. For configurations with annotations, create a test ApplicationContext with a dedicated property set.

Configuration example:

~~~java
@Component
public class LimitSettings {

    private final int limit;

    public LimitSettings(
            @Value("${app.limit:10}") int limit) {
        this.limit = limit;
    }

    public int getLimit() {
        return limit;
    }
}
~~~

Spring's test context or ApplicationContextRunner in Spring Boot can be used to verify:

- Properties are resolved properly.
- Defaults are applied when properties are missing.
- Conversion to the field/constructor type is accurate.
- Malformed values cause context startup to fail as expected.
- Conditional beans are registered or omitted based on properties.

SpEL unit tests and Spring integration tests complement each other. There is no need to initialize the entire application for every simple conversion case; use context tests when wiring, placeholders, or annotation processing must be confirmed.

## 17. Using parameterized tests for multiple values

If a converter or expression needs to handle many inputs, JUnit 5 parameterized tests help avoid code duplication.

Example:

~~~java
@ParameterizedTest
@CsvSource({
        "10, 10",
        "25, 25",
        "100, 100"
})
void convertsValidIntegers(String raw, Integer expected) {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("raw", raw);

    Integer actual = parser.parseExpression("#raw")
            .getValue(context, Integer.class);

    assertEquals(expected, actual);
}
~~~

@MethodSource can be used for complex inputs or domain objects. For invalid data, write a separate parameterized test to confirm each value is rejected.

Name tests to describe behavior, such as convertsValidInteger or rejectsMalformedAccountCode. Clear names help test reports show which contract was violated.

## 18. Checking objects after failed operations

When setValue or a setter throws an exception, verify the object remains in a valid state.

For example, if a setter validates values before assigning:

~~~java
public void setAge(Integer age) {
    if (age != null && age < 0) {
        throw new IllegalArgumentException("Age must be non-negative");
    }
    this.age = age;
}
~~~

Tests should check:

- The exception is propagated or wrapped according to the expected contract.
- The old value is still preserved if the operation is rejected.
- Related properties are not partially updated.
- There are no unintended side effects.

If a setter updates multiple fields before failing, redesign the operation to validate before mutating or perform atomic updates at the domain layer.

SpEL does not provide transactions for multi-property assignments. If multiple fields must be updated as a single business unit, use a transaction-controlled domain/service method instead of multiple independent setValue calls.

## 19. Test helpers to reduce duplication

Small helpers can be created in tests to build contexts or evaluate expressions:

~~~java
private EvaluationContext readWriteContext() {
    return SimpleEvaluationContext
            .forReadWriteDataBinding()
            .build();
}

private <T> T evaluate(
        String source,
        Object root,
        Class<T> targetType) {

    Expression expression = parser.parseExpression(source);

    return expression.getValue(
            readWriteContext(),
            root,
            targetType
    );
}
~~~

Helpers should only eliminate boilerplate. Do not swallow exceptions or automatically return defaults that prevent tests from verifying actual behavior.

For tests needing a custom TypeConverter, MethodResolver, or variables, create a separate context in that test so the configuration clearly expresses the objective.

## 20. Conversion and binding test matrix

A short matrix helps verify full coverage of data paths:

| Operation | Valid input | Invalid input |
|---|---|---|
| Typed getValue | String converts to Integer | Non-numeric string |
| Method argument | Argument converts to parameter type | No suitable converter |
| setValue property | Writes to setter and conversion succeeds | Read-only property or conversion error |
| Nested property | Intermediate object exists | Null intermediate object |
| Map/List indexer | Valid key/index, mutable collection | Missing key, out-of-bounds index, or immutable collection |
| Custom converter | Input matches domain format | Malformed input |
| Null | Reference type accepts null | Primitive or logic rejecting null |

Not every application needs every row in the matrix. Select cases matching the objects, converters, and expressions actually used.

## 21. Common testing errors

| Symptom | Common cause | How to handle |
|---|---|---|
| Parse tests pass but runtime fails | Not evaluated with realistic root object and context | Add evaluation tests |
| Conversion test uses different context from production | Converters are not configured identically | Use a fixture creating a production-like context |
| Assertion only checks toString() | Does not confirm runtime type | Assert target type and value |
| Binding test misses read-only property | Only tests getter | Add setValue tests |
| Nested property test is flaky | Intermediate object is not explicitly initialized | Build complete fixtures |
| Error test depends on message text | Messages change across versions | Assert exception type, cause, or message code |
| Test ignores state after error | Setter may mutate before throwing exception | Assert object still holds invariants |
| Unit test passes but @Value fails | Spring placeholder/annotation processing untested | Add ApplicationContext integration tests |

## 22. Key takeaways

SpEL testing needs to separate parsing, evaluation, conversion, and binding. Typed getValue tests result conversion; method invocation tests argument conversion; setValue tests property accessors, setters, and conversion to the target type. Custom TypeConverter or ConversionService must be configured identically to the real use case.

Test valid data, malformed data, nulls, read-only properties, null nested objects, invalid indices, and immutable collections. After write operations, verify object state; after failed operations, confirm invariants are still preserved.

Use unit tests for expressions and converters, parameterized tests for multiple inputs, and Spring integration tests for @Value or bean configuration. Conversion does not replace validation; data-type tests and business-rule tests must have distinct goals.