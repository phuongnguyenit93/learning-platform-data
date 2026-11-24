# Equality and Inequality in SpEL

Spring Expression Language (SpEL) provides two equality and inequality comparison operators to test the relationship between two values:

- **==**: equal to.
- **!=**: not equal to.

They are commonly used in conditions, data selection expressions, status checks, and business rules. However, it is necessary to understand how SpEL compares numbers, strings, objects, and null values to avoid unexpected results.

An important point is that SpEL's equality operator should not be understood simply as Java's reference comparison. For numeric values, SpEL has its own numeric comparison handling; for ordinary objects, the comparison is based on the object's equals rules.

## 1. Syntax of Equality and Inequality Operators

### 1.1. Equality Operator (==)

The **==** operator returns true when two operands are considered equal:

~~~java
1 == 1
'Spring' == 'Spring'
true == true
~~~

Example with the parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Boolean result = parser
        .parseExpression("10 == 10")
        .getValue(Boolean.class);
~~~

The result is **true**.

This operator can be used in complex conditions:

~~~java
order.status == 'PAID'
~~~

or:

~~~java
customer.age == 18
~~~

The result of the comparison is a Boolean and can be used in logical operators, conditional expressions, or APIs that accept Boolean values.

### 1.2. Inequality Operator (!=)

The **!=** operator is the negation of equality:

~~~java
10 != 20
'Spring' != 'Spring Boot'
true != false
~~~

Example:

~~~java
Boolean result = parser
        .parseExpression("10 != 20")
        .getValue(Boolean.class);
~~~

The result is **true**.

It can check that a status does not belong to an unwanted value:

~~~java
order.status != 'CANCELLED'
~~~

Note that this condition is true for every status other than CANCELLED, even when status is null. If the business rule requires status to have a value before checking, add an explicit null check.

### 1.3. Precedence and Parentheses

Equality and inequality operators are often combined with logical operators:

~~~java
order.status == 'PAID' && order.total != null
~~~

When an expression has multiple operators, parentheses should be used to clearly express condition grouping:

~~~java
(order.status == 'PAID' || order.status == 'SHIPPED')
        && order.total != null
~~~

Parentheses help readers recognize the business intent even when they already know operator precedence.

## 2. Comparing Data Types

### 2.1. Comparing Numbers

SpEL handles numeric operands by their numeric values, even when they have different Number types:

~~~java
1 == 1
1 == 1.0
10 != 9
~~~

Example:

~~~java
parser.parseExpression("1 == 1.0")
        .getValue(Boolean.class);
~~~

A numeric comparison can return true even though the two literals are represented by different numeric types. Therefore, do not use the result of numeric equality to infer that the two operands have the same Java type.

If the business logic needs to distinguish data types, check the type separately or normalize the types before comparing.

### 2.2. Comparing Strings

For strings, equality is case-sensitive:

~~~java
'Spring' == 'Spring'
'Spring' != 'spring'
~~~

The result of the first expression is true; the second expression is also true because the two strings differ in letter case.

If a case-insensitive comparison is needed, a String method can be called:

~~~java
name != null && name.equalsIgnoreCase('spring')
~~~

The null check at the beginning ensures the method is not called on a null reference. If the application has locale-specific string normalization rules, perform normalization according to the business policy instead of defaulting to one case-conversion approach for all languages.

### 2.3. Comparing Booleans

Two Boolean values are compared by value:

~~~java
true == true
true != false
~~~

In conditions, it is usually unnecessary to write a comparison with true:

~~~java
order.confirmed
~~~

The expression above already returns a Boolean if the confirmed property has an appropriate boolean or Boolean type.

Writing **order.confirmed == true** can still be readable in some contexts, but is usually more verbose than necessary. For a nullable Boolean, clearly define whether null means undefined, not applicable, or false.

### 2.4. Comparing Objects

For ordinary objects, SpEL equality uses the object's equals rules. Therefore, the result depends on how the class implements equals.

For example, a Java record automatically provides equals based on its data components:

~~~java
public record CustomerId(String value) {
}
~~~

Two CustomerId objects created separately but having the same value are considered equal:

~~~java
new CustomerId('C-100') == new CustomerId('C-100')
~~~

In real expressions, objects retrieved from the root object or variables can be compared:

~~~java
order.customerId == currentCustomer.id
~~~

If a domain type does not implement equals properly according to the business definition, equality may produce unexpected results. Check the class's equals/hashCode before relying on object comparison.

### 2.5. List and Map

Standard Java List and Map have their own equals rules:

- Two Lists are equal when they have the same number of elements and corresponding elements are equal in order.
- Two Maps are equal when they contain the same key-value mappings, regardless of entry iteration order.
- Nested comparisons continue to depend on the equals of each element, key, and value.

Example:

~~~java
{1, 2, 3} == {1, 2, 3}
~~~

Do not rely solely on literal syntax to conclude that every collection structure produces the same result. The result depends on the collection type and how that type implements equals. For custom collections, check the equals contract of the implementation.

### 2.6. Java Arrays

Java arrays inherit equals from Object and do not compare element contents the way List.equals does. Two different array instances are generally not equal just because they contain the same data:

~~~java
new int[2] == new int[2]
~~~

In this example, two arrays are allocated independently. If array contents need to be compared, use an appropriate method in Java such as Arrays.equals or convert the data to a collection with suitable equals rules before evaluation.

Do not confuse SpEL's equality with deep content comparison of every data structure.

## 3. Comparing with null

### 3.1. null Equals null

In SpEL, two null values are considered equal:

~~~java
null == null
~~~

A null value and a non-null value are not equal:

~~~java
null != 'Spring'
'Spring' == null
~~~

Therefore, null comparison can be used to check whether a property does not yet have a value:

~~~java
order.note == null
~~~

### 3.2. Distinguishing null from Empty String

An empty string is a String of length 0, not null:

~~~java
'' == null
'' != null
~~~

If you need to check whether a string has no content, clearly determine whether whitespace-only strings are included:

~~~java
name == null || name.trim().isEmpty()
~~~

If name can be null, the first branch ensures the trim method is only called when name is non-null thanks to the short-circuit evaluation mechanism of the OR operator.

For applications using Java 11 or later, the isBlank method can be used if whitespace-only strings should be treated as empty:

~~~java
name == null || name.isBlank()
~~~

### 3.3. Null in Property Chains

An intermediate property can be null:

~~~java
order.customer.address.city
~~~

If customer or address is null, subsequent access may cause an error during evaluation. Each step can be checked:

~~~java
order.customer != null
        && order.customer.address != null
        && order.customer.address.city == 'Hanoi'
~~~

The AND operator evaluates with short-circuiting, so later operands are only evaluated when earlier operands are true. This is a way to guard an access chain when not using safe navigation.

If the Spring version and syntax in use support safe navigation, it can be written concisely:

~~~java
order.customer?.address?.city == 'Hanoi'
~~~

Choose the clearest expression for the project's Spring version and the domain's null rules.

## 4. Object Comparison by equals and by Identity

### 4.1. == Is Not a Reference-Identity Check for All Objects

In Java, the **==** operator on two object references checks whether they share the same reference. SpEL has its own comparison semantics: for ordinary objects, equality is based on equals.

For example, two strings created from two different String objects but with the same content can still be considered equal:

~~~java
new String('Spring') == new String('Spring')
~~~

Therefore, do not use **==** in SpEL to check whether two variables point to the exact same object in memory.

In most business rules, value-based comparison is desirable. If the business logic truly depends on object identity, provide a method or property with a clear meaning in the model, such as comparing a stable identifier.

### 4.2. Designing equals for Domain Types

For types such as CustomerId, Money, OrderNumber, or EmailAddress, equals should reflect the domain's definition of equality.

Example:

~~~java
public record OrderNumber(String value) {
}
~~~

When two OrderNumber instances have the same value, SpEL comparison will use the equals rules generated for the record.

For ordinary classes, equals and hashCode must be implemented consistently. If equals only compares a subset of data, make sure that subset is the exact equality criterion that business expressions need to use.

Do not write complex business logic inside equals. If a condition requires multiple rules, create a clearly named method and call that method in SpEL.

## 5. Using Equality in Business Conditions

### 5.1. Status Check

~~~java
order.status == 'PAID'
~~~

This is the basic condition to check whether an order has been paid.

If multiple statuses are accepted:

~~~java
order.status == 'PAID' || order.status == 'SETTLED'
~~~

Conditions with the same intent can be grouped:

~~~java
(order.status == 'PAID' || order.status == 'SETTLED')
        && order.total > 0
~~~

Parentheses separate the valid status group from the total amount condition.

### 5.2. Identifier Check

~~~java
order.customerId == currentCustomer.id
~~~

This is how to compare two identifiers if their types have proper equals. If the two sides have different types, normalize or convert explicitly rather than relying on implicit type conversion.

### 5.3. Combining Equality and Inequality with Logic

~~~java
order.status != 'CANCELLED'
        && order.customerId == currentCustomer.id
~~~

The condition is true only when the order is not cancelled and belongs to the current customer.

When expressions become long, separate condition groups with parentheses or move a group of rules into a clearly named method. This helps readers understand the business intent instead of having to parse a chain of operators.

## 6. Using equalsIgnoreCase and Specialized Comparison Methods

The **==** operator compares Strings case-sensitively. If the business logic is case-insensitive, call the corresponding method:

~~~java
username != null && username.equalsIgnoreCase('admin')
~~~

If whitespace normalization is needed:

~~~java
username != null
        && username.trim().equalsIgnoreCase('admin')
~~~

If the data has more complex normalization rules, handle it in the domain layer or create a controlled utility method. Avoid repeating long normalization chains across multiple expressions.

For monetary amounts, dates/times, or business codes, choose a comparison suited to the data type. For example, comparing time intervals may require before/after comparisons instead of exact equality; comparing case-insensitive codes may require a normalized value object type.

## 7. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Two objects with the same data return false | The class does not implement value-based equals | Check equals/hashCode or use an identifier |
| Two arrays with the same content return false | Array.equals does not compare contents | Use Arrays.equals in Java or convert to an appropriate collection |
| Strings with different letter case are not equal | String equality is case-sensitive | Use equalsIgnoreCase if required by business logic |
| null causes an error when calling a method | Calling a method directly on a null value | Check null first or use safe navigation where appropriate |
| Condition status != CANCELLED accepts null | null is not equal to CANCELLED | Add a status != null check if a status is required |
| Numbers with different types are misinterpreted | Confusing value comparison result with having the same Java type | Check types separately if required by business logic |
| Expression is long and hard to understand | Mixing many equality/inequality conditions | Use parentheses, group conditions, or use a clearly named method |

## 8. Testing Equality and Inequality Expressions

Both true, false, and boundary data cases should be tested. Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("10 == 10").getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("10 != 20").getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("null == null").getValue(Boolean.class)
);

assertEquals(
        Boolean.FALSE,
        parser.parseExpression("'' == null").getValue(Boolean.class)
);
~~~

For domain objects, test equals independently first and then test the SpEL expression. For collections and arrays, add cases with two different instances having the same content to confirm the type's exact semantics.

When testing expressions that read data from the root object, prepare cases for:

- Property with a normal value.
- Property that is null.
- Two objects with the same identifier but different instances.
- Strings with case differences.
- Empty collections and collections with elements.
- Arrays allocated separately but containing the same values.

## 9. Summary

SpEL uses **==** to check equality and **!=** to check inequality. How comparison works depends on operand types: numeric values are compared numerically; ordinary objects rely on equals; Strings are case-sensitive; Java arrays do not automatically compare contents.

When writing business expressions, clearly define what null means, how domain types define equals, and whether case-insensitive comparison is needed. Use parentheses to clarify condition groups, and move complex logic into specifically named methods when expressions start becoming hard to read.