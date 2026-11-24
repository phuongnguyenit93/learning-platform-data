# Null Properties in the Middle of an Access Path

## Objectives

After this lesson, you can recognize errors when a property in the middle of an access path has a null value; use the safe navigation operator (?.) properly at each step that may be null; distinguish skipping access from supplying a default value; and test null cases in SpEL expressions before using them in an application.

## 1. Nested property paths

In Spring Expression Language (SpEL), an expression can read properties along a chain from a root object to child objects.

For example, an order has a customer, the customer has an address, and the address has a city:

~~~text
customer.address.city
~~~

SpEL performs the operations sequentially:

1. Read the customer property on the root object.
2. Read the address property on the customer object.
3. Read the city property on the address object.
4. Return the city value.

This notation is concise when all intermediate objects exist. However, in real data, a customer may not have an address yet or an order may not have a customer attached yet. When an intermediate property returns null, SpEL cannot continue reading the next property on that reference.

Therefore, the error often does not lie in the final property. It can occur at any link in the path.

## 2. What happens when a property in the middle is null?

Suppose the expression is:

~~~text
customer.address.city
~~~

The following data states can occur:

| customer | address | city | Result with a standard path |
|---|---|---|---|
| Object present | Object present | Value present | Reads city |
| null | Cannot access | Cannot access | Error reading address on null customer |
| Object present | null | Cannot access | Error reading city on null address |
| Object present | Object present | null | Reads result null |
| Object present | Object present | Value present | Reads value |

The important difference is between a final property whose value is null and a null intermediate object.

If city is null while address still exists, SpEL can return null because it succeeded in reading the final property. If address is null, accessing city cannot proceed and evaluation can fail.

In Java, this is similar to calling a method or reading a field on a null reference. SpEL can report a property evaluation error, usually accompanied by information about the expression position that caused the error.

## 3. Using the safe navigation operator

SpEL provides the safe navigation operator, written as ?. . This operator checks the object on the left before performing the next property access or method call.

Example:

~~~text
customer?.address
~~~

If customer is null, reading address is skipped and the result of that expression part is null. If customer exists, SpEL continues reading address normally.

For a path with multiple links that may be null, use safe navigation at each corresponding link:

~~~text
customer?.address?.city
~~~

Result:

- If customer is null, the expression returns null.
- If customer exists but address is null, the expression returns null.
- If both objects exist, the expression reads city.
- If city has the value null, the final result is still null.

This operator helps the expression tolerate missing data at expected positions. It does not create a replacement object and does not automatically pick a default value.

## 4. Why place ?. at every position that can be null?

A common mistake is placing safe navigation only at the beginning of the path:

~~~text
customer?.address.city
~~~

This syntax only protects reading address on customer. If customer is null, the address access is skipped. However, if customer exists and address returns null, the subsequent .city access can still fail.

If address can also be null, protect the city read step as well:

~~~text
customer?.address?.city
~~~

Practical rules:

- Use ?. before a property whose receiving object can be null.
- If the result of an intermediate property can also be null, use ?. at the next access step.
- Do not mechanically use ?. for every property if the data model guarantees that object always exists.
- Check data contracts and Java annotations or validation rules to determine which links can genuinely be null.

Example with a deeper path:

~~~text
order?.customer?.profile?.displayName
~~~

Each ?. protects one access step. If a link returns null, the next protected access will return null instead of trying to read a property on a null reference.

## 5. Safe navigation only handles null references

The ?. operator has a clear scope: it skips the next operation when the receiving object is null. It does not handle every type of error that can occur in an expression.

For example, the following cases still need separate handling:

- The property name does not exist on the object type.
- The property exists, but the getter throws an exception.
- The object is incompatible with the access operation.
- The returned value cannot be converted to the target type.
- An array or collection index is out of range.
- An invoked method has an error in its implementation.

Example:

~~~text
customer?.unknownProperty
~~~

If customer exists but its type has no unknownProperty property, safe navigation does not turn a nonexistent property into null. It only protects the case where customer is null.

Similarly, if the address getter has an internal bug, ?. does not catch and swallow that exception. Handle errors in the Java layer calling the expression and fix the corresponding data or source code cause.

## 6. Combining safe navigation with default values

Safe navigation often returns null when a link does not exist. If the application needs to display a fallback value, combine it with the Elvis operator (?:).

Example:

~~~text
customer?.address?.city ?: 'Not updated'
~~~

How to read it:

1. Try to retrieve city from customer and address.
2. If the safe path returns null, use the string Not updated.
3. If a city is present, return that city name.

You can use default values matching the data type:

~~~text
customer?.loyaltyPoints ?: 0
~~~

~~~text
customer?.active ?: false
~~~

Elvis is the step that chooses a replacement value. It does not replace safe navigation at intermediate positions that can be null. For example, writing only customer.address.city ?: 'Unknown' can still fail before Elvis is evaluated if customer or address is null.

In SpEL, Elvis also treats an empty string as an absent value where appropriate. If you need to distinguish an empty string from null, write an explicit condition according to business requirements. The values false and 0 are still meaningful values; do not treat them as null when setting defaults.

## 7. Using explicit conditions when null must be distinguished

Sometimes an application needs to know whether a property actually exists, rather than merely wanting a replacement display value.

You can compare directly against null:

~~~text
customer?.address?.city != null
~~~

Or use the ternary operator:

~~~text
customer?.address?.city != null
    ? customer.address.city
    : 'No city'
~~~

In this example, the branch that retrieves city is chosen only when the checked path has a non-null value. However, if there are many repeated accesses, consider placing the normalized value into a context variable to avoid repeating long paths.

If only a default value is needed, Elvis is usually shorter:

~~~text
customer?.address?.city ?: 'No city'
~~~

If you need to distinguish null, empty strings, invalid states, or multiple business cases, use an explicit condition or a clearly named Java method.

## 8. Using in EvaluationContext and Java

You can evaluate a safe path from a root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("customer?.address?.city");

String city = expression.getValue(order, String.class);
~~~

In this example, order is the root object. If customer or address is null, the city result is null.

If you want to pass the object as a variable:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order?.customer?.address?.city");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);

String city = expression.getValue(context, String.class);
~~~

Both approaches use the same safe navigation syntax. The difference lies in where the object is supplied: the root object or a variable in the EvaluationContext.

If you need to supply a default value from the expression:

~~~java
Expression expression = parser.parseExpression(
    "#order?.customer?.address?.city ?: 'Not updated'"
);

String city = expression.getValue(context, String.class);
~~~

Make sure the context contains only the objects and access permissions the expression needs. Safe navigation helps handle null in the path; it does not replace designing an appropriate root object or EvaluationContext.

## 9. Null properties in collections and indexes

A path can combine collection access with nested properties:

~~~text
orders[0]?.customer?.address?.city
~~~

If the first element exists but customer or address is null, safe navigation handles those links.

However, the expression above does not automatically handle the case where orders is null or an empty list. Accessing orders[0] happens before ?. on the element can be applied. Therefore, check the collection and index first:

~~~text
#orders != null and
#orders.size() > 0 and
#orders[0]?.customer?.address?.city == #targetCity
~~~

This condition checks that the collection is non-null and has elements before reading the first element. When using the expression in a specific environment, methods like size() must be allowed by the EvaluationContext.

With selection, you can use safe navigation for element properties:

~~~text
#orders.?[customer?.address?.city == #targetCity]
~~~

Here, each element is checked along the customer, address, and city path. If customer or address is null, the subexpression returns null; comparing against targetCity does not treat null as a matching city name.

## 10. Safe navigation with Boolean conditions

A Boolean property can also be null, especially when using the Boolean wrapper type instead of primitive boolean.

Example:

~~~text
customer?.preferences?.emailEnabled == true
~~~

The expression explicitly checks that the value must be true. If customer, preferences, or emailEnabled is null, the condition is not considered enabled.

You can use Elvis to choose a default of false:

~~~text
customer?.preferences?.emailEnabled ?: false
~~~

This notation is useful when null means not yet enabled or not allowed. If null carries a separate meaning such as undetermined, preserve that distinction instead of automatically converting it to false.

Do not assume every Boolean property can be safely unboxed to boolean. When converting a null result to a primitive type in Java, the application can encounter a NullPointerException. Choose a nullable return type or supply a default intentionally.

## 11. Testing paths with null properties

When testing expressions, vary each link to verify the exact positions that can be null.

For the expression:

~~~text
customer?.address?.city
~~~

You can use the following cases:

| Data state | Expected result |
|---|---|
| customer is null | null |
| customer exists, address is null | null |
| customer and address exist, city is null | null |
| customer, address, and city all have values | City name |
| customer exists but has no address property | Property access error |
| address getter throws an exception | Evaluation error from getter |

In addition, test:

- Root object is null.
- An intermediate property returns null at different levels.
- Empty strings and default values.
- Boolean properties with values null, false, and true.
- Null collection, empty collection, and out-of-range index.
- Getters or accessors that can throw exceptions.

You should test both standard paths and safe navigation paths to confirm the application relies on the right data contract. When a property is mandatory, validation in Java may be more appropriate than silently skipping null in SpEL.

## 12. When should safe navigation be used?

Use safe navigation when null is a valid data state or can occur in the processing flow, such as:

- A profile without an address yet.
- An order not yet linked to a customer.
- A user who has not configured preferences yet.
- Input data from an external source with optional fields.
- A collection element whose nested relationship has not been set.

Do not use safe navigation to mask mandatory-data violations. If business rules require customer and address to always exist, validate that at the time data is received or saved. Turning every error into null can cause the application to overlook invalid data and produce hard-to-detect outcomes.

If an expression begins having many default branches, conditions, and deep nested accesses, move the complex rules into Java. SpEL should keep the role of reading data and expressing short conditions in configuration.

## 13. Key takeaways

A nested property path can fail when any intermediate object is null. The safe navigation operator ?. skips the next access operation if the receiving object is null and returns null for that part.

For multi-level paths, place ?. at every step that can receive a null value, such as customer?.address?.city. Placing safe navigation only at the start of the path does not protect child objects that may be null in later steps.

Safe navigation does not handle nonexistent properties, errors inside getters, type mismatches, or invalid collection indexes. Combine it with Elvis when a default value is needed, or use an explicit condition when null must be distinguished from other states.

Clearly identify which properties are allowed to be null, test every link, and keep validation of mandatory data in the Java layer.