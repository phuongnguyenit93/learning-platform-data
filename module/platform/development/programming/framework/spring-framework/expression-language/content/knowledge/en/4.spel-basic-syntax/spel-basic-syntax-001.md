# Atomic Expressions and Return Values in Spring Expression Language

Spring Expression Language (SpEL) lets you describe a value or computation using an expression string. Some expressions are very simple, such as a number or a string literal; others read properties, access variables, invoke methods, or combine multiple operators.

To understand how SpEL processes basic syntax, two ideas are essential:

- **Atomic expressions** are the basic units that form larger expressions, such as literals, variables, property references, or method invocations.
- **Return values** are the results SpEL produces when evaluating an expression in a specific context. The actual type and value depend on the expression, data, and EvaluationContext.

In this lesson, "atomic" is used in a pedagogical sense to refer to basic components that can stand alone or combine into more complex expressions.

## 1. SpEL Expressions Always Evaluate to a Value

A SpEL expression is parsed into an Expression object. When the application calls getValue(...), SpEL evaluates the expression and returns a Java value.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("10 + 5");

Object result = expression.getValue();
~~~

The return value is the number 15. In this example, the expression does not need a root object or external variables because all data is already inside the expression's literals.

Some other basic expressions:

| Expression | Return Value | Common Type |
|---|---|---|
| 42 | 42 | Integer |
| 3.14 | 3.14 | Double |
| 'Spring' | Spring | String |
| true | true | Boolean |
| null | null | No value object |
| 10 > 5 | true | Boolean |
| 'Spring'.toUpperCase() | SPRING | String |

The specific type of an expression also depends on how the literal is written, the data type of the property, and the return value of the invoked method.

## 2. Literals — Values Written Directly

A literal is a value written directly in the expression text. SpEL does not need to look up application variables or properties to obtain these values.

### 2.1. Numeric Literals

Example:

~~~spel
42
3.14
0x2A
~~~

SpEL supports integer, floating-point, and hexadecimal literals. The numeric type is inferred from the literal syntax and can be specified with a suffix in supported cases.

~~~spel
42L
3.14F
3.14D
~~~

- 42L represents a long literal.
- 3.14F represents a float literal.
- 3.14D represents a double literal.

When using numeric literals in operations, pay attention to data types and conversion rules. Do not assume that every numeric literal has the same Java type.

### 2.2. String Literals

Strings in SpEL are enclosed in single quotes:

~~~spel
'Hello Spring'
'Expression Language'
~~~

Strings can be used as operands for concatenation or method invocations:

~~~spel
'Spring' + ' Expression'
'Spring'.toUpperCase()
~~~

The results are the strings Spring Expression and SPRING, respectively.

### 2.3. Boolean and null Literals

SpEL supports two logical literals:

~~~spel
true
false
~~~

They produce the corresponding Boolean values.

The null literal represents the absence of a reference value:

~~~spel
null
~~~

When evaluating the null expression, the result is null. This is a valid result, distinct from a parsing error or an evaluation error.

## 3. Property References and the Current Object

A property name without the # prefix is typically looked up on the current object. Unless another context is active, the initial current object is the root object.

Suppose there is a Product class:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

The name property can be evaluated as follows:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(product, String.class);
~~~

The result is Keyboard.

The name expression is looked up on the root object product. With nested access syntax, you can write:

~~~spel
customer.name
customer.address.city
~~~

Each dot shifts access to the object returned by the preceding part. If an intermediate element is null, subsequent access may cause an evaluation error. You can use the null-safe navigation operator ?. in appropriate cases to avoid further access on a null object.

Example:

~~~spel
customer?.address?.city
~~~

When customer or address is null, the corresponding null-safe access returns null instead of continuing to dereference a null object.

## 4. Variables and Special References

Variables in SpEL are written with the # prefix. Variable values must be provided in the EvaluationContext.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", new BigDecimal("500000"));
context.setVariable("customerName", "Linh");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#minimum");

Object result = expression.getValue(context);
~~~

The result is a BigDecimal object with the value 500000.

Variables can be combined with literals, properties, and operators:

~~~spel
#minimum * 2
#customerName.toUpperCase()
price >= #minimum
~~~

SpEL also has two special variables:

- #root references the root object of the evaluation.
- #this references the object currently being evaluated at the current position. In collection operations such as selection or projection, #this can change for each element.

For example, if the root object is Product, the following expression explicitly reads the property from the root object:

~~~spel
#root.name
~~~

## 5. Method Invocations and Return Values

An expression can invoke a method on an accessed object or value. The value of a method invocation expression is the value returned by the Java method.

Example:

~~~spel
'Spring'.toUpperCase()
'Spring'.length()
~~~

The results are the string SPRING and the number 6, respectively.

With a root object:

~~~java
Expression expression =
    parser.parseExpression("name.toUpperCase()");

String result = expression.getValue(product, String.class);
~~~

SpEL reads the name property on product, then calls toUpperCase() on the resulting string.

Finding the appropriate method is supported by the MethodResolver in EvaluationContext. If the method does not exist, is inaccessible, or has incompatible arguments, evaluation may fail.

## 6. Type References and Object Instantiation

SpEL can reference a Java type using the T(...) operator. This is an expression that produces a reference to the corresponding Class object.

~~~spel
T(java.lang.Math)
~~~

You can combine a type reference with a static method call:

~~~spel
T(java.lang.Math).abs(-10)
~~~

The return value is the number 10.

SpEL also supports creating objects with the new operator:

~~~spel
new java.lang.String('Spring')
~~~

The result is a String object with the content Spring.

These operations depend on TypeLocator and ConstructorResolver along with the access rules of EvaluationContext. A restricted context may not allow every type reference or object instantiation capability.

## 7. Arithmetic and Logical Expressions Producing New Values

Operators combine atomic expressions into larger expressions. The return value depends on the type of operator.

| Category | Example | Return Value |
|---|---|---|
| Arithmetic | 10 + 5 | Numeric value 15 |
| Comparison | 10 >= 5 | Boolean true |
| Logical | true && false | Boolean false |
| String concatenation | 'Spring' + ' EL' | String Spring EL |
| Conditional | true ? 'YES' : 'NO' | String YES |
| Elvis | name ?: 'Unknown' | name if it has a value, otherwise Unknown |

Example:

~~~spel
(10 + 5) * 2
~~~

The result is 30.

~~~spel
total >= #minimum && status == 'PAID'
~~~

The result is a Boolean. SpEL needs to read total, minimum, and status and then evaluate the comparisons before combining them with &&.

When an expression has multiple operators, operator precedence and parentheses determine how operations are grouped. Use parentheses when you want to clarify intent or change the evaluation order.

## 8. Collections, Inline Lists, and Inline Maps

SpEL can create collections directly inside an expression. These are expressions whose result is a data structure rather than a single value.

### 8.1. Inline List

~~~spel
{1, 2, 3}
~~~

The expression creates a list of values. You can access an element by index:

~~~spel
{ 'Java', 'Spring', 'SpEL' }[1]
~~~

The result is Spring.

### 8.2. Inline Map

~~~spel
{ 'name': 'Linh', 'active': true }
~~~

The expression creates a map consisting of key-value pairs. You can retrieve a value by key using an indexer:

~~~spel
{ 'name': 'Linh', 'active': true }['name']
~~~

The result is Linh.

### 8.3. Selection and Projection

Selection filters collection elements by a condition:

~~~spel
{1, 2, 3, 4, 5}.?[#this > 3]
~~~

The result is a collection containing the elements 4 and 5.

Projection creates a new collection from the evaluation result on each element:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

The result is a collection containing 10, 20, and 30.

Therefore, the return value of a collection expression can be a list or a map, and subsequent expressions can continue operating on that collection.

## 9. Return Value Types and Receiving Results in Java

Expression provides multiple getValue overloads to suit how the application needs to evaluate it.

### 9.1. Receiving the Result as Object

~~~java
Object result = expression.getValue(context);
~~~

This approach is flexible when the result type is not known in advance. The application needs to check or cast appropriately before using it.

### 9.2. Requesting a Target Result Type

~~~java
Boolean result =
    expression.getValue(context, Boolean.class);
~~~

The overload with a Class<T> parameter specifies the type the application expects to receive. SpEL can use the context's TypeConverter to convert the value when conversion is supported.

For example, a numeric expression can be requested to return a compatible numeric type:

~~~java
Integer result =
    parser.parseExpression("10 + 5")
          .getValue(Integer.class);
~~~

The result is an Integer with the value 15.

If the result cannot be converted to the requested type, the call may throw an error. Therefore, the target type should match the value the expression actually produces.

### 9.3. Passing the Root Object Directly

If you do not need to configure a separate context, you can pass the root object directly:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

In this case, product is used as the root object of the evaluation.

### 9.4. Distinguishing Declared Type, Runtime Type, and Target Type

These three concepts should not be confused:

- **Declared type:** the type defined in the Java class, for example the getPrice() getter returning BigDecimal.
- **Runtime type:** the actual type of the object or value that the expression produces during evaluation.
- **Target type:** the type the application requests via the getValue(..., Class<T>) overload.

The three types may be the same, but it is not required. SpEL's conversion mechanism can help convert when compatible.

## 10. Null Values and Cases Without a Normal Result

null is a valid value in SpEL. Example:

~~~spel
null
~~~

Or a property can return null:

~~~spel
customer.nickname
~~~

If nickname has the value null, the expression can return null. That is different from the case where the property is not found or the operation cannot be performed.

It is important to distinguish:

- **Null result:** the expression is evaluated and the resulting value is null.
- **Evaluation error:** SpEL cannot complete the operation, for example dereferencing null in an unprotected position, a nonexistent variable, or not finding a matching method.
- **Parsing error:** the text cannot form a valid expression structure.

For property accesses that may be null, the null-safe navigation operator can help the expression return null instead of raising an error due to further access on a null object.

## 11. Comprehensive Example of Return Value Types

The following examples illustrate that SpEL does not only return Boolean:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object number = parser.parseExpression("10 + 5").getValue();
Object text = parser.parseExpression("'Spring'").getValue();
Object flag = parser.parseExpression("10 > 5").getValue();
Object list = parser.parseExpression("{1, 2, 3}").getValue();
Object map = parser.parseExpression(
    "{'name': 'Linh', 'active': true}"
).getValue();
Object empty = parser.parseExpression("null").getValue();
~~~

The results can be described as:

| Java Variable | Value Type | Illustrative Value |
|---|---|---|
| number | Number | 15 |
| text | String | Spring |
| flag | Boolean | true |
| list | List | [1, 2, 3] |
| map | Map | {name=Linh, active=true} |
| empty | null | null |

The specific type of number depends on the literal type and operation rules. When the application needs a specific type, use the getValue overload with a target type.

## 12. How to Read an Expression from Left to Right

Suppose there is an expression:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

It can be read part by part:

1. customer.orders: retrieve the orders collection from customer.
2. ?[total >= #minimum]: filter orders whose total meets the minimum threshold.
3. ![total * #taxRate]: create a new collection where each element is total multiplied by taxRate.
4. The entire expression returns a collection containing the calculation results on the filtered orders.

During this process, #this changes according to the element currently being examined in selection or projection. #root still holds the root object of the evaluation.

The example shows that an expression can combine multiple basic units. The return value of one part becomes the input for the next part.

## 13. Common Misconceptions

**Misconception 1: Literals and variables retrieve values the same way.**  
Literals are right inside the expression; variables of the form #name are looked up in EvaluationContext.

**Misconception 2: A property name is always a variable.**  
total is usually read from the current object; #minimum is read from the context's variable set.

**Misconception 3: Parsing already produces the business result.**  
Parsing creates the Expression structure. The result is only computed when getValue is called in an evaluation environment.

**Misconception 4: Every expression returns a String or Boolean.**  
The result can be a number, string, boolean, object, collection, map, or null.

**Misconception 5: getValue(context, String.class) only performs a Java cast.**  
SpEL can use TypeConverter to convert values when supported. If conversion is not possible, evaluation may fail.

**Misconception 6: null always means an error.**  
null can be a valid return value. An error only occurs when the expression cannot perform the required operation.

## 14. Key Takeaways

- Literals, properties, variables, and method invocations are basic components that can combine into larger expressions.
- Every evaluated expression produces a value, with a type depending on syntax and runtime data.
- Operators can produce new values, especially Boolean in comparison and logical operations.
- Inline lists, inline maps, selection, and projection can return collections or maps.
- Expression.getValue() returns Object; overloads with a target type help the application request the desired type.
- EvaluationContext provides variables, the root object, and the necessary access or conversion mechanisms.
- null is a valid result and must be distinguished from parsing or evaluation errors.
- When analyzing an error, determine whether the error occurred during parseExpression or getValue before checking syntax or runtime data.

When reading a SpEL expression, identify the basic components, track the value of each part during evaluation, and then determine the type and value returned by the outermost expression node. That is how to accurately understand the relationship between basic syntax and the final result.
