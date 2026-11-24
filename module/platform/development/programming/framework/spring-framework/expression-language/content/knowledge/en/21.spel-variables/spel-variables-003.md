# Null-Valued Variables in SpEL

## 1. Null in SpEL Expressions

Spring Expression Language (SpEL) can read variables from `EvaluationContext`, properties from the root object, and results from method calls. These values may be null because the data has not been provided, a property has not been initialized, or a method found no result.

In SpEL, the `null` keyword represents a reference with no value. It differs from the character string `"null"` and from the empty string `''`.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object nullValue = parser.parseExpression("null").getValue();
String textValue = parser.parseExpression("'null'").getValue(String.class);
String emptyValue = parser.parseExpression("''").getValue(String.class);

System.out.println(nullValue);  // null
System.out.println(textValue);  // null
System.out.println(emptyValue); // empty string
~~~

The first line returns an actual null value. The second line returns a `String` object containing the four characters `null`. The third line returns a `String` of length 0. When handling optional data, distinguish these three cases because default comparisons and conditions can yield different results.

## 2. Putting Variables into EvaluationContext

Variables in SpEL are referenced with the `#` prefix. For example, `#nickname` is the variable named `nickname` in the evaluation context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", "Lan");

Expression expression = parser.parseExpression("#nickname");
String nickname = expression.getValue(context, String.class);

System.out.println(nickname); // Lan
~~~

If the passed Java value is null, `StandardEvaluationContext.setVariable(name, null)` removes that variable binding from the context. When an expression references a variable without a bound value, the lookup result is null:

~~~java
context.setVariable("nickname", null);

Expression expression = parser.parseExpression("#nickname");
Object nickname = expression.getValue(context);

System.out.println(nickname); // null
~~~

Therefore, when a business variable might have no value, understand its state at evaluation time. `#nickname` may evaluate to null because the binding was never set or was removed; the expression alone does not indicate which occurred.

If you need to distinguish "no binding" from "data provided with a null value", pass an additional status variable, such as `#nicknameProvided`, or represent the state using a non-null object/wrapper. Do not rely on a single `#nickname == null` comparison to infer the origin of null.

## 3. Checking for Null with Comparison Operators

You can check whether a variable or property is null using `== null` and `!= null`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression isNullExpression =
        parser.parseExpression("#nickname == null");

Expression hasValueExpression =
        parser.parseExpression("#nickname != null");

Boolean isNull = isNullExpression.getValue(context, Boolean.class);
Boolean hasValue = hasValueExpression.getValue(context, Boolean.class);

System.out.println(isNull);   // true
System.out.println(hasValue); // false
~~~

The same check can be used with a property of the root object:

~~~java
Expression expression = parser.parseExpression("email == null");

Boolean emailMissing = expression.getValue(customer, Boolean.class);
~~~

In this example, `email` is read from the root object `customer`. There is no `#` prefix because it is a property of the root object, not a variable in the context.

When writing conditions, check for null before invoking methods or accessing properties that depend on that value. The `== null` comparison expresses intent clearly and is easier to read than attempting to call a method on a potentially null value.

## 4. Choosing an Alternative Value with the Ternary Operator

The ternary operator allows choosing one result when a variable has a value and another result when the variable is null:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression expression = parser.parseExpression(
        "#nickname != null ? #nickname : 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

When `#nickname != null` is true, SpEL picks the branch between `?` and `:`. When the condition is false, SpEL picks the branch after `:`. Only the chosen branch is evaluated to produce the result.

The fallback value can be a number, a Boolean, or another expression:

~~~java
Expression retryExpression = parser.parseExpression(
        "#retryCount != null ? #retryCount : 3");

Expression enabledExpression = parser.parseExpression(
        "#featureEnabled != null ? #featureEnabled : false");
~~~

When the two branches return different types, check the result type expected by the application and use the appropriate `getValue(..., TargetType.class)` overload. For expressions used in multiple places, keeping the result type consistent helps avoid runtime conversion errors.

## 5. Using the Elvis Operator for Concise Default Values

The Elvis operator `?:` is a shorthand for providing a fallback value when the left-hand side is null:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("nickname", null);

Expression expression =
        parser.parseExpression("#nickname ?: 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

For simple cases, Elvis is equivalent to checking for null with the ternary operator. It keeps the expression shorter when only a default value is needed.

In SpEL, the Elvis operator also treats an empty string as a case requiring the default value:

~~~java
context.setVariable("nickname", "");

Expression expression =
        parser.parseExpression("#nickname ?: 'Guest'");

String displayName = expression.getValue(context, String.class);
System.out.println(displayName); // Guest
~~~

Elvis does not treat every "empty-like" value as null. Boolean `false` and numeric `0` are still non-null values; they are preserved rather than switching to the default branch. If you want to handle strings containing only whitespace, you can trim first:

~~~java
Expression expression =
        parser.parseExpression("#nickname?.trim() ?: 'Guest'");
~~~

In this example, `?.` avoids calling `trim()` when `#nickname` is null. If the string becomes empty after trimming, Elvis returns `Guest`.

## 6. Distinguishing Null, Empty String, and Default Values

Common cases:

| Value | `#value == null` | `#value ?: 'default'` |
|---|---:|---|
| null | true | `default` |
| `''` | false | `default` |
| `'Lan'` | false | `Lan` |
| `false` | false | `false` |
| `0` | false | `0` |

This matters when the variable is a Boolean or a number. Do not use Elvis under the assumption that false or zero also means missing data.

For example, if `#enabled` has the value false, the following expression still returns false:

~~~java
Expression expression =
        parser.parseExpression("#enabled ?: true");
~~~

If business logic requires false to be replaced with true, write an explicit condition for that case. Elvis suits null and empty strings; it is not a replacement for a Boolean or numeric check rule.

## 7. Accessing Properties or Calling Methods When an Object May Be Null

A variable can reference a null object. If a property or method is accessed directly on that object, SpEL may raise an evaluation error:

~~~text
#customer.name
#customer.getName()
~~~

Use null-safe navigation `?.` when the target may be null:

~~~java
Expression nameExpression =
        parser.parseExpression("#customer?.name");

Expression methodExpression =
        parser.parseExpression("#customer?.getName()");
~~~

If `#customer` is null, null-safe expressions return null. If the object exists, SpEL proceeds to read the corresponding property or invoke the method.

With multi-level paths, every intermediate object that may be null needs to be guarded at the appropriate position:

~~~text
#customer?.address?.city
~~~

Only write `#customer?.address.city` if you have guaranteed that `address` cannot be null. The null-safe operator protects the operation immediately following it; it does not automatically make the rest of the path safe.

## 8. Combining Null-Safe Navigation with Default Values

You can combine `?.` and Elvis `?:` to read an optional property and supply a fallback value:

~~~java
Expression expression = parser.parseExpression(
        "#customer?.address?.city ?: 'Unknown city'");

String city = expression.getValue(context, String.class);
~~~

Processing steps:

1. SpEL reads the `#customer` variable.
2. If customer is null, the null-safe part returns null.
3. If customer exists, SpEL reads address; if address is null, the result remains null.
4. If city has a valid value, the result is city.
5. If the left-hand result is null or an empty string, Elvis returns `Unknown city`.

This style suits short optional data paths. If there are multiple fallback branches or many business rules, extract the logic into a Java method for easier naming and testing.

## 9. Handling Null in Collection Variables

A variable pointing to a collection can also be null. Calling selection or projection on a null target with regular syntax can cause the expression to fail. With Spring Framework versions supporting null-safe collection operators, you can use `?.?` and `?.!`:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("items", null);

Expression selection = parser.parseExpression("#items?.?[active]");
Expression projection = parser.parseExpression("#items?.![name]");

Object activeItems = selection.getValue(context);
Object itemNames = projection.getValue(context);

System.out.println(activeItems); // null
System.out.println(itemNames);   // null
~~~

Null-safe collection selection and projection were added in Spring Framework 6.2. With older versions, check for null in Java before evaluating the expression or use constructs supported by that version.

Distinguish a null target from an empty collection. A null target yields null when using the null-safe operator; a non-null empty collection produces an empty collection result. These two states can carry different business meanings, such as "data not loaded" versus "loaded with no elements".

## 10. Filtering Null Elements in a Collection

A collection may exist yet contain one or more null elements. A null-safe operator on the root collection does not automatically guard individual elements.

For example, filtering elements that are non-null and have a non-null `name` property:

~~~java
List<Item> items = Arrays.asList(
        new Item("A"),
        null,
        new Item(null));

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("items", items);

Expression expression = parser.parseExpression(
        "#items?.?[#this != null and #this.name != null]");

List<?> namedItems = expression.getValue(context, List.class);
~~~

In the predicate, `#this` represents the element currently under evaluation. The first condition checks that the element is not null; only then does the next condition read the `name` property.

You can use null-safe property access if you want to keep all elements while retrieving a potentially null property:

~~~text
#items?.![#this?.name]
~~~

Selection filters elements by condition; projection builds a new collection of values. Choose the operation based on the desired result and guard both the collection and the element if both levels can be null.

## 11. Using a Status Variable to Distinguish Missing Data from Null

A `#value == null` check only tells you that the current result is null. It does not indicate whether the data was never provided, was removed from the context, or the property holds a null value.

If business logic needs to distinguish those states, pass an explicit status variable:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

String nickname = loadNickname();
boolean nicknameWasProvided = wasNicknameProvided();

context.setVariable("nickname", nickname);
context.setVariable("nicknameWasProvided", nicknameWasProvided);

Expression expression = parser.parseExpression(
        "#nicknameWasProvided ? (#nickname ?: 'Unnamed') : 'Not provided'");
~~~

`#nicknameWasProvided` indicates whether the data was provided. `#nickname` holds the actual value if present. If nickname is null or an empty string, Elvis can supply `Unnamed`; if the data was not provided, the expression returns `Not provided`.

You can use a request object or a wrapper with status properties instead of scattered separate variables if this status is used across multiple expressions. Status names should clearly convey business meaning, not just be a generic technical flag.

## 12. Null in Method Calls and Computed Results

A method invoked from an expression can return null even when the target object is non-null. For example, a lookup method might find no match:

~~~java
public class CustomerDirectory {
    public Customer findByCode(String code) {
        // May return null if not found.
        return lookup(code);
    }
}
~~~

If the evaluation context permits accessing that bean or object, the method call result can still be null. Handle the result before continuing to access properties:

~~~text
@customerDirectory.findByCode(#code)?.name ?: 'Unknown'
~~~

Similarly, a calculation or method call can produce null from input data depending on how the class is designed. Do not assume every property and method always returns a valid object; identify the data contract and supply default values at appropriate boundaries.

## 13. Common Mistakes When Handling Null

**Using the string 'null' instead of the null value**

`'null'` is a string literal. Use the `null` keyword when representing a null reference.

**Accessing a property on a null object**

`#customer.name` can error if `#customer` is null. Use `#customer?.name` or check the condition beforehand.

**Thinking setVariable(name, null) keeps a null binding**

With `StandardEvaluationContext`, passing null to `setVariable` removes the variable from the context. If state needs to be represented, use an additional flag or a non-null wrapper.

**Confusing null with an empty string**

`''` does not equal null. Elvis handles both null and empty strings; `== null` comparison only recognizes null.

**Thinking false or zero triggers Elvis**

False and zero are non-null values, so Elvis preserves them. Write a separate condition if business logic treats false or zero as special cases.

**Guarding only the first object in a path**

`#customer?.address.city` can still fail if address is null. Place the null-safe operator at every link that could be null.

**Assuming a null collection is the same as an empty collection**

Null-safe selection on a null target returns null; selection on an empty collection returns an empty collection. Preserve the distinction if business logic needs it.

## 14. Comprehensive Example

The following example reads optional variables, handles a null customer, picks a default name, and filters a collection containing null elements:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("customer", null);
context.setVariable("nickname", "");
context.setVariable("items", Arrays.asList(
        new Item("A"),
        null,
        new Item(null),
        new Item("B")));

Expression displayExpression = parser.parseExpression(
        "#customer?.name ?: (#nickname ?: 'Guest')");

Expression namedItemsExpression = parser.parseExpression(
        "#items?.?[#this != null and #this.name != null]");

String displayName =
        displayExpression.getValue(context, String.class);

List<?> namedItems =
        namedItemsExpression.getValue(context, List.class);

System.out.println(displayName); // Guest
System.out.println(namedItems.size()); // 2
~~~

In this example, a null customer causes `#customer?.name` to return null. Nickname is an empty string, so Elvis proceeds to pick `Guest`. The items collection is non-null; selection retains the two elements with non-null name and discards the null element and the element with a null name.

## 15. Key Takeaways

- The `null` keyword represents a null value; `'null'` is a string literal and `''` is an empty string.
- Variables are referenced using `#name`; root object properties are referenced directly by property name.
- `StandardEvaluationContext.setVariable(name, null)` unbinds a variable; looking up an unbound variable returns null.
- Use `#value == null` and `#value != null` to check for null.
- Use ternary or Elvis `?:` to provide fallback values; Elvis handles null and empty strings, but keeps false and zero.
- Use `?.` for property or method calls on objects that may be null; guard each link in a multi-level path.
- Null-safe collection selection/projection requires Spring Framework 6.2 or later.
- A null collection differs from an empty collection; a collection can also contain null elements.
- If you need to distinguish unprovided data from a null value, pass an explicit status or use a wrapper.
- Check the contract of methods and properties because they can also return null.
