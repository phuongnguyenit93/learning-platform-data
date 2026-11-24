# Elvis Operator for Default Values

In Spring Expression Language (SpEL), the **Elvis** operator has the syntax **?:** and is used to provide a fallback value when the left-hand expression does not have a suitable value. This is a concise way of writing: if a value is available, use it; otherwise, use a default value.

Example:

~~~text
#customerName ?: 'Guest'
~~~

If customerName has a value, SpEL returns that value. If the variable is null or an empty string, SpEL returns Guest. Elvis is useful when reading data that may be missing, generating display names, retrieving fallback configuration, or building part of a cache key.

## 1. Syntax and How It Works

General syntax:

~~~text
expression ?: defaultExpression
~~~

SpEL evaluates the left-hand expression first:

1. If the left-hand result is not null and not an empty string, that result is returned.
2. If the left-hand result is null or an empty string, SpEL evaluates and returns the default expression on the right.

Example:

~~~text
#nickname ?: 'Anonymous'
~~~

This can be read as: if nickname has a value, return nickname; otherwise, return Anonymous. The default expression only needs to be evaluated when the left-hand branch needs a fallback.

## 2. Which Values Trigger the Fallback?

Elvis in SpEL has two important cases that cause the right-hand side to be selected:

- The left-hand value is **null**.
- The left-hand value is an **empty string** (empty String, length equal to 0).

All other cases are usually preserved, even when the application might consider them "missing data" under another business convention.

| Left-hand value | Expression | Result |
| --- | --- | --- |
| null | **#value ?: 'default'** | 'default' |
| empty string | **#value ?: 'default'** | 'default' |
| 'Spring' | **#value ?: 'default'** | 'Spring' |
| '   ' | **#value ?: 'default'** | String consisting of spaces |
| 0 | **#value ?: 100** | 0 |
| false | **#value ?: true** | false |
| Empty list | **#items ?: #fallbackItems** | Original empty list |
| Optional.empty() | **#optional ?: #fallback** | Optional.empty() |

The easiest mistake to make is that **a string containing only spaces is not an empty string**. Elvis does not trim strings automatically and does not check for whitespace-only in the sense of "blank".

Similarly, the number 0, boolean false, an empty collection, and an empty Optional are all non-null. They do not automatically trigger a fallback just because the application might consider them "missing data".

## 3. Example with Variables in EvaluationContext

You can test Elvis standalone using the SpEL parser and an EvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("nickname", null);

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Guest
~~~

Changing the variable value:

~~~java
context.setVariable("nickname", "Linh");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Linh
~~~

With an empty string:

~~~java
context.setVariable("nickname", "");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println(result); // Guest
~~~

With a string containing only spaces:

~~~java
context.setVariable("nickname", "   ");

String result = parser
        .parseExpression("#nickname ?: 'Guest'")
        .getValue(context, String.class);

System.out.println("[" + result + "]"); // [   ]
~~~

These examples show that Elvis checks for null and empty String according to SpEL rules. If you want to treat whitespace-only strings as missing data as well, you need to add a separate blank check.

## 4. Comparing Elvis with the Ternary Operator

The ternary operator has the syntax:

~~~text
condition ? valueIfTrue : valueIfFalse
~~~

Example using ternary to provide a default name:

~~~text
#nickname != null ? #nickname : 'Guest'
~~~

Elvis is shorter to write:

~~~text
#nickname ?: 'Guest'
~~~

| Criterion | Ternary | Elvis |
| --- | --- | --- |
| Syntax | condition ? A : B | A ?: B |
| Condition | The conditional expression must return a boolean | Based on the result of A |
| Common use case | Choosing between two branches based on any condition | Using a fallback value when the left-hand side is null or an empty string |
| Repeating left-hand expression | Often requires repeating the expression | Writes the left-hand expression only once |
| Checking empty string | Must add an extra condition | Directly supported |

Ternary is suitable when the condition is not just null/empty:

~~~text
#score >= 50 ? 'PASS' : 'FAIL'
~~~

Elvis is suitable when the goal is to take an existing value or use a default value:

~~~text
#displayName ?: 'Anonymous'
~~~

Do not replace ternary with Elvis if the condition is actually a business rule, such as classifying by score, status, or access permissions.

## 5. Combining Elvis with Safe Navigation

The safe-navigation operator **?.** allows accessing a property or calling a method without causing an error just because the target object is null. When the object on the left is null, that access evaluates to null.

Elvis can receive this null result and provide a fallback value:

~~~text
#customer?.nickname ?: 'Guest'
~~~

How to read it:

1. Get the customer variable.
2. If customer is not null, read nickname.
3. If customer is null, the result of the safe navigation part is null.
4. If nickname is null or an empty string, return Guest.

For nested objects, use safe navigation at each step that can be null:

~~~text
#order?.shippingAddress?.city ?: 'Unknown'
~~~

This avoids errors when order or shippingAddress is null, while providing Unknown if city has no value or is an empty string.

An example with a display name:

~~~text
#profile?.nickname ?: #profile?.fullName ?: 'Anonymous'
~~~

SpEL prioritizes nickname first, then fullName, and finally uses Anonymous. You can add parentheses when the fallback expression is long so readers can clearly see the selection order:

~~~text
#profile?.nickname ?: (#profile?.fullName ?: 'Anonymous')
~~~

Safe navigation and Elvis solve two different problems:

- **?.** guards the access operation when the target object might be null.
- **?:** provides a fallback value when the left-hand result is null or an empty string.

Do not use one operator to replace the role of the other.

## 6. Using Elvis for Configuration Values and @Value

An application may need a fallback value if a system property is not set. With @Value, a SpEL expression can read a system property and then use Elvis:

~~~java
@Component
class RuntimeSettings {

    @Value("#{systemProperties['app.region'] ?: 'ap-southeast-1'}")
    private String region;
}
~~~

If the app.region system property does not exist or is an empty string, region receives the value ap-southeast-1. If the property has a value, that value is used.

A similar approach can be used to provide a default label:

~~~java
@Value("#{systemProperties['app.display-name'] ?: 'Spring Application'}")
private String displayName;
~~~

It is necessary to distinguish Elvis from property placeholder default values:

~~~java
@Value("${{app.region:ap-southeast-1}")
private String region;
~~~

Both mechanisms can produce default values, but they operate at different layers:

- **Property placeholder** retrieves values from Spring's configuration sources and allows declaring a fallback directly in the placeholder syntax.
- **SpEL Elvis** evaluates an expression. The left-hand side can be a property, variable, object access, or method call permitted by the EvaluationContext.

If you only need to read a property and set a default value, a placeholder is usually simpler. Use Elvis when you need to combine multiple values or process the result of an expression.

## 7. Using Elvis with Maps, Requests, and Cache Keys

### 7.1. Getting a Default Value from a Map

When reading a key that may not exist:

~~~text
#settings['locale'] ?: 'vi-VN'
~~~

If the map does not have the locale key, the access returns null and Elvis selects vi-VN. If the key has an empty string value, Elvis also selects vi-VN.

It can be combined with other values:

~~~text
#settings['locale'] ?: #user?.preferredLocale ?: 'vi-VN'
~~~

The priority order is locale in settings, preferredLocale of user, and then vi-VN.

### 7.2. Creating a Cache Key with a Default Value

In a cache annotation, Elvis can help prevent part of a key from being null:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#request?.tenantId ?: 'public'"
)
public Product findProduct(ProductRequest request) {
    // ...
}
~~~

If tenantId is missing or an empty string, the expression uses public as the tenant part of the key.

When using this pattern, ensure the default value genuinely represents a valid public tenant or namespace. If multiple tenants are grouped under the public key, data could be shared unintentionally. For multi-tenant caches, choose the fallback according to the proper data partitioning rules.

### 7.3. Combining with Business Conditions

Elvis only selects a default value; it does not replace business checks. For example:

~~~text
(#request?.tenantId ?: 'public') == 'public'
~~~

The expression above takes tenantId or public, then compares the result with public. If you need to check whether the user has permission to access the tenant, you must perform the appropriate authorization check as well.

## 8. When Is Elvis Not Enough to Handle Blank Strings?

Elvis only treats null and empty strings as missing data. In many applications, strings containing only spaces, tabs, or newlines also need to be treated as blank.

Example:

~~~text
#name ?: 'Guest'
~~~

With name equal to three spaces, the expression returns three spaces. If the requirement is that null, empty, or whitespace-only must all use Guest, use a helper whose name clearly expresses the rule:

~~~java
@Component("stringPolicy")
class StringPolicy {

    public String defaultIfBlank(String value, String fallback) {
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value;
    }
}
~~~

Expression:

~~~text
@stringPolicy.defaultIfBlank(#name, 'Guest')
~~~

In a Spring application, the bean must be named stringPolicy and the EvaluationContext must allow bean references. If you want full support for Unicode whitespace as defined by your application, choose the blank-checking API appropriate for your Java version and project data conventions.

Do not write a long expression to simulate an entire string normalization policy if that logic is used in multiple places. Moving the rule into a Java helper makes it easier to reuse and test.

## 9. Cases Requiring Caution

### 9.1. The Left-Hand Side Can Throw an Error Before Elvis Is Applied

Elvis only processes the result of the left-hand expression after that expression has been evaluated. If property access or a method call on the left throws an exception, Elvis cannot automatically turn that exception into the default value.

Unsafe:

~~~text
#customer.address.city ?: 'Unknown'
~~~

If customer is null, accessing address may fail before Elvis receives a result.

Safer:

~~~text
#customer?.address?.city ?: 'Unknown'
~~~

### 9.2. Do Not Use Elvis to Hide Data Errors

If a required property must exist, silently substituting a default value can hide configuration or data errors. Use fallbacks for missing data that is acceptable in business logic; for required data, validate and report errors clearly.

### 9.3. Return Types of Both Branches Should Be Compatible

An Elvis expression can return either the left-hand value or the right-hand value. When retrieving the result as a specific Java type, the two branches need to have compatible types or be convertible by SpEL's conversion mechanism.

Example:

~~~java
Integer limit = parser
        .parseExpression("#configuredLimit ?: 100")
        .getValue(context, Integer.class);
~~~

If configuredLimit has a type incompatible with Integer, conversion may fail. Keep the data type of the default value consistent with the desired result type.

### 9.4. An Empty Optional Is Not Equivalent to Null

An Optional.empty() is still a non-null Optional object. Therefore:

~~~text
#optional ?: #fallback
~~~

does not automatically take the fallback just because the Optional contains no value. Unwrap the Optional first or call a helper that handles Optional according to the business rule.

## 10. Testing Elvis Expressions

You can write small unit tests to verify the fallback cases:

~~~java
class ElvisExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final StandardEvaluationContext context =
            new StandardEvaluationContext();

    @Test
    void returnsFallbackForNull() {
        context.setVariable("name", null);

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Guest", result);
    }

    @Test
    void returnsFallbackForEmptyString() {
        context.setVariable("name", "");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Guest", result);
    }

    @Test
    void preservesNonEmptyString() {
        context.setVariable("name", "Spring");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("Spring", result);
    }

    @Test
    void preservesWhitespaceOnlyString() {
        context.setVariable("name", "   ");

        String result = parser
                .parseExpression("#name ?: 'Guest'")
                .getValue(context, String.class);

        assertEquals("   ", result);
    }
}
~~~

The tests above verify the parser and expression behavior in a standalone EvaluationContext. If Elvis is used in @Value, @Cacheable, or another integration point, there should be tests at that exact component to confirm the context and evaluation timing.

## 11. Quick Takeaways

- Elvis has the syntax **A ?: B**: take A if A has a value, otherwise take B.
- In SpEL, the fallback is used when the left-hand side is null or an empty string.
- Whitespace-only strings are not automatically considered empty.
- The number 0, boolean false, empty collections, and Optional.empty() do not automatically trigger the fallback.
- Ternary **condition ? A : B** uses a boolean condition; Elvis is concise for selecting a fallback value.
- Combine **?.** with **?:** to safely access a potentially null object and then provide a default value.
- Elvis does not catch exceptions thrown while evaluating the left-hand side.
- Use property placeholders when you only need a configuration default; use SpEL Elvis when you need a fallback for an expression result.
- For blank rules or complex business logic, call a clearly named Java helper.
- Test null, empty string, whitespace-only, and valid values.

## 12. Official References

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-ternary.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — @Value Annotation](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
