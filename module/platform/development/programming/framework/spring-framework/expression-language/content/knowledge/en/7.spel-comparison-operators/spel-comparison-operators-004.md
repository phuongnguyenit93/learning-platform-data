# Comparing Strings, Numbers, and Convertible Types in SpEL

## 1. Overview of Comparisons

Spring Expression Language (SpEL) supports relational operators to compare two values and return a Boolean result:

| Operator | Name | Example | Result |
|---|---|---|---|
| `==` | Equal | `2 == 2` | `true` |
| `!=` | Not equal | `2 != 3` | `true` |
| `<` | Less than | `2 < 5` | `true` |
| `>` | Greater than | `8 > 5` | `true` |
| `<=` | Less than or equal to | `5 <= 5` | `true` |
| `>=` | Greater than or equal to | `8 >= 9` | `false` |

Relational operators work with values of type `Number` and types implementing `Comparable`. Thus, numbers, strings, and objects with natural ordering defined by `compareTo` can be compared.

Example using the parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean numberCheck =
        parser.parseExpression("10 > 5").getValue(Boolean.class);

Boolean stringCheck =
        parser.parseExpression("'black' < 'block'").getValue(Boolean.class);

System.out.println(numberCheck); // true
System.out.println(stringCheck); // true
~~~

The result of a comparison expression is `Boolean`. Expressions can be evaluated directly on literals, on a root object, or on variables in an `EvaluationContext`.

## 2. Comparing Numeric Values

With two numeric operands, SpEL performs comparison by numerical value. Expressions can use integers, decimals, and different numeric types:

~~~java
Boolean first = parser.parseExpression("10 > 5").getValue(Boolean.class);
Boolean second = parser.parseExpression("2 < 10.0").getValue(Boolean.class);
Boolean third = parser.parseExpression("2 == 2.0").getValue(Boolean.class);

System.out.println(first);  // true
System.out.println(second); // true
System.out.println(third);  // true
~~~

Numeric comparison is not a comparison of the string representations of numbers. The integer value `2` and the decimal value `2.0` have the same numerical value, so they can be considered equal in numeric comparison.

Variables can be used instead of literals:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 100);
context.setVariable("actual", 125.5);

Expression expression =
        parser.parseExpression("#actual >= #minimum");

Boolean accepted = expression.getValue(context, Boolean.class);
System.out.println(accepted); // true
~~~

This approach is useful when thresholds and data come from configuration or runtime objects. The Expression stays the same while variable values can change.

## 3. Comparing Strings in Lexicographic Order

In SpEL, `String` implements `Comparable`, so the `<`, `>`, `<=`, and `>=` operators can compare strings according to the lexicographic order of `String.compareTo` in Java.

~~~java
Boolean result = parser.parseExpression("'black' < 'block'")
        .getValue(Boolean.class);

System.out.println(result); // true
~~~

Comparison proceeds from the first character. When the first differing pair of characters is encountered, the order of that pair determines the result. If one string is a prefix of the other, the shorter string comes first.

Example:

~~~java
Boolean a = parser.parseExpression("'ant' < 'bat'").getValue(Boolean.class);
Boolean b = parser.parseExpression("'app' < 'apple'").getValue(Boolean.class);
Boolean c = parser.parseExpression("'zebra' > 'apple'").getValue(Boolean.class);

System.out.println(a); // true
System.out.println(b); // true
System.out.println(c); // true
~~~

Default string comparison is case-sensitive. It does not automatically apply natural-language sorting rules, locales, or database collation rules. Therefore, `<` or `>` should not be used as a substitute for locale-aware sorting of personal names, addresses, or multilingual content.

For example, `'Spring'` and `'spring'` differ in exact comparison:

~~~java
Boolean sameCase = parser.parseExpression("'Spring' == 'Spring'")
        .getValue(Boolean.class);

Boolean differentCase = parser.parseExpression("'Spring' == 'spring'")
        .getValue(Boolean.class);

System.out.println(sameCase);      // true
System.out.println(differentCase); // false
~~~

If the business logic requires case-insensitive comparison, normalize the data using an explicit rule, such as calling `toLowerCase()` on both sides or using a dedicated Java method. For languages requiring locale handling, use `Collator` or an appropriate comparison mechanism rather than assuming `String.compareTo` is natural-language comparison.

## 4. Equality and Inequality Comparison

The `==` operator tests whether two values are equal according to SpEL semantics; `!=` is its corresponding negation.

~~~java
Boolean sameNumber =
        parser.parseExpression("100 == 100").getValue(Boolean.class);

Boolean differentNumber =
        parser.parseExpression("100 != 99").getValue(Boolean.class);

Boolean sameText =
        parser.parseExpression("'paid' == 'paid'").getValue(Boolean.class);

System.out.println(sameNumber);     // true
System.out.println(differentNumber); // true
System.out.println(sameText);       // true
~~~

For strings, equality is case-sensitive and compares content. For numbers, SpEL compares by numerical value; do not confuse this with comparing how literals are written.

If checking for the same object instance is required, distinguish equality from reference identity. In Java, `equals()` and `==` can have different meanings for objects; when business logic needs an identity check, call an appropriate Java method or design an explicit expression. Do not infer that two objects equal in content are necessarily the same instance.

## 5. Comparing Objects Implementing Comparable

In addition to `Number` and `String`, SpEL can compare objects that implement `java.lang.Comparable`. The result depends on the `compareTo` rules defined by that type.

For example, a version type can compare by version number:

~~~java
public final class Version implements Comparable<Version> {
    private final int major;

    public Version(int major) {
        this.major = major;
    }

    @Override
    public int compareTo(Version other) {
        return Integer.compare(this.major, other.major);
    }
}
~~~

If the root object contains two `Version` values, an expression can compare them using relational operators:

~~~java
Expression expression = parser.parseExpression("currentVersion < requiredVersion");

Boolean needsUpgrade =
        expression.getValue(versionInfo, Boolean.class);
~~~

This example requires `versionInfo` to have `currentVersion` and `requiredVersion` properties, and the two values to have compatibly comparable types. Design `compareTo` so that the ordering is consistent with business meaning; SpEL uses the ordering provided by the Java type rather than inferring comparison rules for custom objects.

If two objects cannot be compared with each other, or `compareTo` rejects the input type, evaluation may raise an error. Do not assume every object has a natural ordering.

## 6. Comparing Strings with Numbers: Explicit Conversion

A string containing digits is still a `String`, and does not automatically become a numeric value simply because its content looks like a number.

For example, `'10'` and `'2'` are two string literals. Comparing them in string order yields a different result than comparing two numbers:

~~~java
Boolean lexical = parser.parseExpression("'10' < '2'")
        .getValue(Boolean.class);

Boolean numeric = parser.parseExpression("10 < 2")
        .getValue(Boolean.class);

System.out.println(lexical); // true
System.out.println(numeric); // false
~~~

In string comparison, the first character `'1'` comes before `'2'`, so `'10' < '2'` is true. In numeric comparison, ten is greater than two, so `10 < 2` is false.

When numeric data comes from a form, configuration file, or JSON as a string, convert it to a numeric type before comparing. Conversion can be done in Java:

~~~java
String rawValue = "42";
Integer value = Integer.valueOf(rawValue);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", value);

Boolean result = parser.parseExpression("#value >= 40")
        .getValue(context, Boolean.class);
~~~

Or perform explicit conversion directly inside the expression using a type reference and an appropriate method:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("rawValue", "42");

Expression expression =
        parser.parseExpression("T(java.lang.Integer).valueOf(#rawValue) >= 40");

Boolean result = expression.getValue(context, Boolean.class);
System.out.println(result); // true
~~~

This clearly shows the string data is parsed into an Integer before the `>=` operator performs the comparison. If the content is not a valid number, such as `"42x"`, the conversion will fail and throw an evaluation error. Validate the input or handle conversion errors at the appropriate layer.

## 7. ConversionService and Expression Result Types

SpEL integrates Spring Core's type conversion system. By default, SpEL uses a conversion service to convert values in situations requiring a target type, such as when retrieving the result with a desired type or assigning a value to a strongly typed property.

For example, an expression returns a string literal while the application requests an Integer:

~~~java
Expression expression = parser.parseExpression("'42'");

Integer value = expression.getValue(Integer.class);
System.out.println(value); // 42
~~~

The `getValue(Integer.class)` overload requests the result to be of type `Integer`. If the expression value is not an Integer but can be converted by the registered `TypeConverter`, SpEL can perform the conversion. If it cannot be converted, the call throws an `EvaluationException`.

Two things must be distinguished:

- **Result type conversion:** the expression has already been evaluated, and then the result is converted to the type requested by `getValue(TargetType.class)`.
- **Comparing two operands:** relational operators require values comparable according to `Number` or `Comparable` rules. Do not assume that every pair of different types is automatically converted before comparison.

Therefore, the fact that `getValue(Integer.class)` can convert `'42'` to `42` does not mean every expression such as `'42' > 10` is automatically treated as a numeric comparison. When comparing data of different types, convert explicitly beforehand.

## 8. Conversion When Setting Typed Properties

ConversionService is also useful when SpEL writes a value to a typed property. For example, a bean with a Boolean property:

~~~java
public class Preferences {
    private Boolean enabled;

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

An evaluation context supporting data binding can be used to assign a string value to a Boolean property:

~~~java
Preferences preferences = new Preferences();

EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();

parser.parseExpression("enabled")
        .setValue(context, preferences, "true");

System.out.println(preferences.getEnabled()); // true
~~~

SpEL knows the target type of the `enabled` property is `Boolean`, so the conversion service can convert the string `"true"` into a Boolean value before assigning it.

Conversion can also apply to collections with generic types. For instance, when assigning to `List<Boolean>`, Spring can convert each element to Boolean to maintain the correct element type. This is an important feature of the conversion service: it not only converts single values but can also preserve generic type constraints when working with properties.

## 9. Registering Custom Converters

Spring Core allows extending the conversion service with custom converters when the application has specialized data types. After registering a converter, the evaluation context's `StandardTypeConverter` can be configured to use that conversion service.

~~~java
ConversionService conversionService = new DefaultConversionService();

// Register a Converter<String, CustomCode> suitable for the application's domain.
conversionService.addConverter(new StringToCustomCodeConverter());

StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeConverter(new StandardTypeConverter(conversionService));
~~~

`StringToCustomCodeConverter` here is an application-defined converter implementing `Converter<String, CustomCode>`. The converter should validate the string content and construct a valid domain object; it should not arbitrarily convert invalid data into a default value that masks errors.

Custom converters are particularly useful when:

- The target property uses a custom value object type.
- Input values come from configuration or data binding as strings.
- The application has custom normalization or validation rules during conversion.
- Multiple expressions or Spring components need to share a single conversion rule.

Registering a converter does not mean every comparison automatically uses the converter to transform both operands. Clearly identify where conversion is needed: before comparing, when retrieving the result type, or when writing a property.

## 10. Comparing with null

In SpEL, `null` is treated as "no value", not the number 0. With less-than and greater-than operators, the rules for comparing with null have specific behavior:

- `X > null` is true when X is non-null.
- `X < null` is false when X is non-null.
- Do not use comparison with null as a substitute for comparing a number with 0.

Example:

~~~java
Boolean greater = parser.parseExpression("10 > null")
        .getValue(Boolean.class);

Boolean less = parser.parseExpression("10 < null")
        .getValue(Boolean.class);

System.out.println(greater); // true
System.out.println(less);    // false
~~~

If the goal is to check for a positive or negative number, compare against 0:

~~~java
Boolean positive = parser.parseExpression("#amount > 0")
        .getValue(context, Boolean.class);
~~~

If the goal is to check whether data exists, use an explicit null condition, such as `#value != null`. When accessing a nullable property, handle null before calling methods or accessing deep into the object graph.

## 11. Textual Operators and Extended Operators

In some configuration formats, `<` or `>` characters have special meaning, such as in XML. SpEL supports textual equivalents for relational operators:

| Symbolic Operator | Textual Equivalent |
|---|---|
| `<` | `lt` |
| `>` | `gt` |
| `<=` | `le` |
| `>=` | `ge` |
| `==` | `eq` |
| `!=` | `ne` |

These keywords are case-insensitive.

~~~java
Boolean result = parser.parseExpression("10 gt 5")
        .getValue(Boolean.class);
~~~

SpEL also supports comparison-related operators:

**between**

~~~java
Boolean inRange = parser.parseExpression("5 between {1, 10}")
        .getValue(Boolean.class);
~~~

`between` is shorthand for checking whether a value lies within a range, inclusive of both endpoints: the value is greater than or equal to the lower bound and less than or equal to the upper bound. If the two bounds are reversed, the expression does not automatically reorder the range.

**instanceof**

~~~java
Boolean isInteger = parser.parseExpression("123 instanceof T(Integer)")
        .getValue(Boolean.class);
~~~

This operator checks the runtime type. Integer literals in SpEL are boxed into `Integer`; therefore, wrapper types like `Integer` must be distinguished from primitive types like `int`.

**matches**

~~~java
Boolean validAmount = parser.parseExpression(
        "'125.50' matches '^-?\\d+(\\.\\d{2})?$'")
        .getValue(Boolean.class);
~~~

`matches` checks whether a string matches a regular expression. This is a string format check, not a numeric comparison; a string matching the regex still needs to be converted and range-checked if the business logic requires a valid number.

## 12. Common Mistakes

- **Comparing strings as numbers:** `'10' < '2'` is a lexicographic comparison and evaluates to true. Convert both values to numeric types before numeric comparison.
- **Assuming all types are convertible:** the conversion service only performs conversions for which a suitable converter exists. Invalid strings or unsupported types will cause errors.
- **Confusing result conversion with operand conversion:** `getValue(Integer.class)` converts the result to Integer if possible; that does not mean operands of different types in a comparison are automatically converted.
- **Case-insensitive string comparison:** `'PAID'` and `'paid'` differ. Normalize according to business rules if needed.
- **Using string ordering for natural language:** `String.compareTo` does not replace locale-based collation.
- **Treating null like 0:** `null` has its own rules. Check for null or compare with 0 depending on your intent.
- **Comparing incompatible objects:** custom types must implement `Comparable` with clear rules, or convert data to a comparable type.
- **Ignoring conversion errors:** input data should be validated beforehand or evaluation errors should be handled at an appropriate boundary.

## 13. Choosing the Right Comparison Approach

You can choose based on data type and business meaning:

1. **Number with number:** use relational operators directly. Choose a numeric type suited to the required precision.
2. **String with string:** use `==` for content equality or `<`/`>` for lexicographic order. Normalize if case-insensitivity is needed.
3. **Ordered objects:** implement `Comparable` with consistent rules and then use relational operators.
4. **Numeric string with number:** convert the string to a numeric type explicitly before comparing.
5. **Expression result needing another type:** use the `getValue(TargetType.class)` overload and ensure the conversion service has an appropriate converter.
6. **Assigning data to a typed property:** use an evaluation context suited for data binding; Spring's conversion service can convert the value before assignment.
7. **Custom domain types:** register a custom converter when needed and validate data inside the converter.

## 14. Key Takeaways

- Relational operators in SpEL support `Number` and types implementing `Comparable`.
- Numbers are compared by numerical value; strings are compared in lexicographic order and are case-sensitive.
- Comparing strings representing numbers differs from comparing numeric values: `'10' < '2'` is true in string ordering.
- Do not assume every pair of different types is converted before comparison.
- Use explicit conversion or normalize data before comparison when the input type differs from the target type.
- ConversionService supports result type conversion and data binding; it can be extended with custom converters.
- `null` is not 0; check for null and compare numbers according to your exact intent.
- `lt`, `gt`, `le`, `ge`, `eq`, and `ne` are the textual equivalents of relational operators.
- Use `between`, `instanceof`, and `matches` for range checks, runtime type checks, and string format checks.
- Keep comparison rules short, clear, and matched to the actual data types.
