# Atomic Expressions and Return Values in Spring Expression Language

Spring Expression Language (SpEL) provides syntax to access data and compute on Java objects. An expression can be just a simple value like the number 42, or it can combine properties, variables, method calls, and operators into a complex calculation.

To understand the basic syntax, two concepts should be distinguished:

- **Atomic expression:** a basic building block that can provide a value or an object as input to another expression, such as a literal, variable reference, property, method call, or type reference.
- **Evaluation result:** the value SpEL produces when evaluating an expression in a specific context. The value can be a number, string, Boolean, object, collection, map, or null.

"Atomic expression" in this article is a way of grouping basic syntax elements for learning and reading expressions. What matters is knowing where each component gets its value from, and then tracing how operators combine them to produce the final result.

## 1. What Components Make Up a SpEL Expression?

Basic syntax can be divided into three groups:

1. **Values and references:** literals, property names, variables, root object, type references, and bean references.
2. **Access and invocation:** property access, indexers, method calls, and object instantiation.
3. **Combination and transformation:** arithmetic, relational, logical, conditional, selection, projection, and collection manipulation operations.

Example:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

The expression above combines multiple components: property access, selection, variables, comparison, projection, and multiplication. The return value is a collection built from the orders that satisfy the condition.

## 2. Literals: Values Written Directly

A literal is the simplest component. Its value is determined right inside the expression string, without needing to look it up from the root object or variables.

### 2.1. Numeric Literals

~~~spel
42
3.14
0x2A
42L
3.14D
3.14M
~~~

SpEL supports integers, floating-point numbers, and hexadecimal numbers. Some common suffixes:

- L: specifies a long literal.
- D: specifies a double literal.
- M: specifies a BigDecimal literal.

For example, 42L is a long literal, while 3.14M is a BigDecimal literal. Specific numeric types matter when an expression combines multiple operand types or when the application requests a specific result type.

### 2.2. String Literals

Strings are enclosed in single quotes:

~~~spel
'Spring'
'Expression Language'
'Hello, SpEL!'
~~~

Strings can be used directly or combined with operators and method calls:

~~~spel
'Spring' + ' Expression'
'Spring'.toUpperCase()
~~~

The results are Spring Expression and SPRING respectively.

### 2.3. Boolean and Null Literals

~~~spel
true
false
null
~~~

The first two literals create Boolean values. The null literal produces an empty reference value. A null result is valid and should be distinguished from an error occurring during evaluation.

## 3. Property References and the Root Object

An identifier without a # prefix is normally interpreted as a property or member of the current object.

Suppose we have a class:

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

The name property can be evaluated on the root object:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(product, String.class);
~~~

The result is Keyboard.

Property expressions can be chained using dots:

~~~spel
customer.name
customer.address.city
product.category.name
~~~

Each dot shifts access to the object returned by the preceding part.

Two special references help identify the current object:

- #root always references the root object of the evaluation.
- #this references the object that is the current evaluation target. Inside collection selection or projection, this object can change for each element.

Example:

~~~spel
#root.customer.name
~~~

The expression above explicitly states that name is read from customer on the root object.

## 4. Variables: Referencing Values from EvaluationContext

Variables have the # prefix. The application registers variables on EvaluationContext and the expression references those variable names.

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

The result is the BigDecimal value registered for the minimum variable.

Variables can be combined with other components:

~~~spel
#minimum * 2
#customerName.toUpperCase()
price >= #minimum
~~~

Distinguish minimum and #minimum:

- minimum is a property name looked up on the current object.
- #minimum is a variable looked up in EvaluationContext.

If a variable has not been registered or the variable name does not match, the expression may fail to evaluate as expected.

## 5. Property Access, Indexers, and Method Calls

Beyond direct references, SpEL allows continuing to operate on the value returned from an atomic component.

### 5.1. Property Access

~~~spel
customer.name
customer.address.city
~~~

Each dot moves to the object returned from the previous part. Reading properties is performed through an appropriate PropertyAccessor in EvaluationContext.

### 5.2. Indexer

An indexer uses square brackets to access an element by index or key:

~~~spel
items[0]
customerMap['primary']
'Spring'[0]
~~~

Depending on the object, an indexer can access an element of an array, list, map, or string. For a map, the expression inside square brackets is used as the key. For a list or array, the index identifies the element to read.

### 5.3. Method Calls

A method name is followed by parentheses and an argument list:

~~~spel
'Spring'.toUpperCase()
'Spring'.substring(0, 3)
customer.isActive()
~~~

The value of a method call expression is the value returned by the Java method. If the method returns String, the expression can produce String; if it returns Boolean, the result can be Boolean.

SpEL uses MethodResolver in the context to find a matching method. Successful invocation depends on the current object, method name, number and types of arguments, as well as configured access permissions.

## 6. Type References, Static Members, and Object Instantiation

SpEL can reference a Java type using the T(...) operator:

~~~spel
T(java.lang.Math)
~~~

Type references are often used to call static members:

~~~spel
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 25)
~~~

The results are 10 and 25 respectively.

The new operator allows instantiating objects:

~~~spel
new java.lang.String('Spring')
~~~

The expression creates a String object with the content Spring.

Type references and object instantiation depend on TypeLocator, ConstructorResolver, and the capabilities allowed by EvaluationContext. Not every context enables all of these features.

## 7. Bean References

In a Spring environment configured with a BeanResolver, expressions can reference beans by name using the @ symbol:

~~~spel
@systemProperties
~~~

Properties can be accessed or methods called on the resolved bean:

~~~spel
@environment.getProperty('app.name')
~~~

This syntax is useful when an expression needs to use a Spring-managed component. However, bean resolution must be supported and configured in EvaluationContext. Simply writing @beanName does not automatically make every context find the bean.

## 8. Operators Combining Atomic Components

Atomic components are often operands for operators. An operator's result can in turn become a sub-expression in a larger calculation.

| Group | Example | Typical Result Type |
|---|---|---|
| Arithmetic | 10 + 5, 10 * 2 | Number |
| Relational | 10 >= 5, 'A' == 'A' | Boolean |
| Logical | true && false | Boolean |
| String concatenation | 'Spring' + ' EL' | String |
| Conditional | true ? 'YES' : 'NO' | Type of the selected branch |
| Elvis | name ?: 'Unknown' | Value of name or default value |
| Type check | 'text' instanceof T(String) | Boolean |
| Regular expression | 'abc' matches 'a.*' | Boolean |

Example:

~~~spel
(price * quantity) >= #minimum
~~~

Multiplication produces a numeric value; comparison uses that value to produce a Boolean.

Parentheses help group sub-expressions and clarify the order of execution. When multiple operators are present, SpEL's precedence rules determine how the expression is parsed if parentheses are omitted.

## 9. Inline Collections, Maps, Selection, and Projection

SpEL can construct data structures directly inside an expression.

### 9.1. Inline List

~~~spel
{1, 2, 3}
~~~

The expression creates a list. Elements can be accessed with an indexer:

~~~spel
{'Java', 'Spring', 'SpEL'}[1]
~~~

The result is Spring.

### 9.2. Inline Map

~~~spel
{'name': 'Linh', 'active': true}
~~~

The expression creates a map containing key-value pairs. Values can be accessed by key:

~~~spel
{'name': 'Linh', 'active': true}['name']
~~~

The result is Linh.

### 9.3. Selection

Selection filters collection elements according to a condition:

~~~spel
{1, 2, 3, 4, 5}.?[#this > 3]
~~~

The result is a collection containing elements 4 and 5. Inside the selection condition, #this references the element currently being evaluated.

SpEL also has selection forms that retrieve the first or last element matching a condition, using the .^[...] and .$[...] operators.

### 9.4. Projection

Projection creates a new collection by evaluating an expression on each element:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

The result is a collection containing 10, 20, and 30.

The return value of selection or projection is a collection or corresponding value according to the operation form used.

## 10. Null, Null-Safe Navigation, and Elvis

SpEL can return null when an expression is the null literal or when a property has a null value:

~~~spel
null
customer.nickname
~~~

Further access on a null object can cause an error. The null-safe navigation operator ?. stops access when the object on the left is null:

~~~spel
customer?.address?.city
~~~

If customer or address is null, the expression returns null at the corresponding access point.

The Elvis operator ?: provides a fallback value when the left expression is null:

~~~spel
customer.nickname ?: 'Unknown'
~~~

If nickname has a value, the result is nickname; if null, the result is the string Unknown.

Null is a valid returnable value. It differs from an evaluation error caused by an operation that cannot be executed.

## 11. Return Values of Expression in Java

Expression provides getValue overloads to retrieve results appropriately.

### 11.1. Retrieving the Result as Object

~~~java
Object value = expression.getValue(context);
~~~

This approach is suitable when the result type is not known in advance. The return value can be an object of any type produced by the expression, or null.

### 11.2. Requesting a Result Type

~~~java
Boolean result =
    expression.getValue(context, Boolean.class);
~~~

The overload with a target type allows the application to specify the desired type. SpEL can use the context's TypeConverter to convert if possible.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("10 + 5");

Integer result = expression.getValue(Integer.class);
~~~

The result is an Integer with value 15.

If the value cannot be converted to the target type, evaluation may throw an error. Therefore, choose a target type appropriate for the expected result.

### 11.3. Passing the Root Object Directly

When no separate context configuration is needed, the root object can be passed directly:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

Here product is the root object for the evaluation.

## 12. What Types Can an Expression Return?

| Expression Form | Example | Result |
|---|---|---|
| Numeric literal | 42 | Number |
| String literal | 'Spring' | String |
| Boolean literal | true | Boolean |
| Null literal | null | null |
| Property | product.price | Type of the property |
| Variable | #minimum | Type of the variable's value |
| Comparison | price > 100 | Boolean |
| Calculation | price * 2 | Appropriate numeric type |
| Method call | name.toUpperCase() | Type returned by the method |
| Inline list | {1, 2, 3} | List |
| Inline map | {'a': 1} | Map |
| Selection / Projection | items.?[active] | Collection or result per selection form |

The return type is not determined solely by the expression syntax. It also depends on the actual types of objects, variable values, methods called, and conversions in the context.

## 13. Comprehensive Example: From Atomic Components to Final Value

Suppose there is a Product class with properties name and price. The application wants to check whether the product price meets a minimum threshold and generate a corresponding message.

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "price >= #minimum ? name.toUpperCase() : 'BELOW LIMIT'"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

String result = expression.getValue(context, String.class);
~~~

Result:

~~~text
KEYBOARD
~~~

The expression can be broken down as follows:

1. price is a property reference on the root object.
2. #minimum is a variable retrieved from EvaluationContext.
3. price >= #minimum is a comparison expression producing a Boolean.
4. The conditional operator ?: chooses one of the two branches based on the Boolean.
5. name.toUpperCase() reads the name property and then calls a method on the string.
6. The selected branch produces the string KEYBOARD.
7. getValue(context, String.class) returns the result in the String type requested by the application.

If minimum increases to 900000, the first branch is not chosen and the result becomes BELOW LIMIT. The Expression stays the same; data in the context determines the branch and the final value.

## 14. Distinguishing a Null Result from an Error

When working with return values, distinguish three situations:

- **Normal value:** the expression evaluates successfully and returns a number, string, Boolean, object, or collection.
- **Null value:** the expression evaluates successfully, but the obtained value is null.
- **Error:** SpEL cannot parse or execute the expression, e.g., syntax error, missing variable, inaccessible property, or failed type conversion.

Parsing errors usually occur when calling parseExpression. Evaluation errors usually appear when calling getValue.

If the application needs to handle null, it can check the returned value or use constructs such as null-safe navigation and Elvis suited to the expression's purpose.

## 15. Common Misconceptions

**Misconception 1: Any name without a # sign is a variable.**  
A name like price is normally looked up as a property on the current object. Variables are referenced with #price.

**Misconception 2: Literals and runtime values are the same.**  
Literals are written directly inside the expression. Runtime values of properties or variables are only determined when evaluation occurs.

**Misconception 3: An expression always returns a type known at parse time.**  
The actual result type can depend on runtime data and methods called.

**Misconception 4: null means parsing failed.**  
null can be the valid result of an expression that was parsed and evaluated successfully.

**Misconception 5: The target type of getValue changes the calculation.**  
The target type specifies the form of result the application wants to receive. Expression logic is still determined by SpEL syntax.

## 16. Key Takeaways

- Literals, properties, variables, method calls, and type references are basic components that can supply values to an expression.
- Property names are normally looked up on the root object or current object; variable names have the # prefix and are retrieved from EvaluationContext.
- Indexers, method calls, and operators allow combining components into complex expressions.
- Expressions can return Number, String, Boolean, object, collection, map, or null.
- getValue() returns the result as Object; target-typed overloads allow the application to request a desired type.
- The context's TypeConverter can assist with type conversion when compatible.
- null is a valid result and differs from a parsing or evaluation error.

When analyzing a SpEL expression, identify each basic component, see where each component gets its value from, trace how operators combine them, and finally check the type and value returned by getValue.
