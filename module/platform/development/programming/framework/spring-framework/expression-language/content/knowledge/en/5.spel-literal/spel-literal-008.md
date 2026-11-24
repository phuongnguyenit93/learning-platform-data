# Atomic Expressions and Return Values in Spring Expression Language

Spring Expression Language (SpEL) uses an expression syntax to access data and perform calculations on Java objects. An expression can be just a simple value like `42`, but it can also combine properties, variables, method calls, and operators into a complex calculation.

To read SpEL syntax accurately, two concepts must be distinguished:

- **Atomic expression:** a basic component that can provide a value or an object as input to another expression, such as a literal, variable reference, property, method call, or type reference.
- **Evaluation result (return value):** the value that SpEL produces when evaluating an expression in a specific context. The value can be a number, string, Boolean, object, collection, map, or null.

Atomic components are often combined with operators and parentheses to form larger expressions. When the application calls `getValue(...)`, SpEL evaluates that structure and returns the final value.

## 1. What Components Make Up a SpEL Expression?

Basic syntax can be divided into three groups:

1. **Values and references:** literals, property names, variables, root object, type references, and bean references.
2. **Access and invocation:** property access, indexer, method calls, and object instantiation.
3. **Combination and transformation:** arithmetic, comparison, logical, conditional operators, selection, projection, and collection operations.

Example:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

The expression above combines multiple components: property access, selection, variables, comparison, projection, and multiplication. The return value is a collection created from the orders satisfying the condition.

## 2. Literals: Values Written Directly

A literal is the simplest component. Its value is determined directly in the expression string, without needing to look up from the root object or variables.

### 2.1. Numeric Literals

~~~spel
42
3.14
0x2A
42L
3.14F
3.14D
3.14M
~~~

SpEL supports integers, real numbers, and hexadecimal numbers. Some common suffixes:

- `L`: specifies a long-type literal.
- `F`: specifies a float-type literal.
- `D`: specifies a double-type literal.
- `M`: specifies a BigDecimal-type literal.

For example, `42L` is a long literal, while `3.14M` is a BigDecimal literal. The specific numeric type matters when an expression combines multiple operand types or when the application requests a specific result type.

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

The results are `Spring Expression` and `SPRING`, respectively.

### 2.3. Boolean and null Literals

~~~spel
true
false
null
~~~

The first two literals create Boolean values. The `null` literal creates an empty reference value. A null result is valid and should be distinguished from errors occurring during evaluation.

## 3. Property References and the Root Object

An identifier name without a `#` prefix is usually interpreted as a property or member of the current object.

Suppose there is a class:

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

The `name` property can be evaluated on the root object:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(product, String.class);
~~~

The result is `Keyboard`.

Property expressions can be chained with dots:

~~~spel
customer.name
customer.address.city
product.category.name
~~~

SpEL reads the first part on the current object, then continues accessing properties of the returned object.

Two special references help identify the current object:

- `#root` always references the root object of the evaluation.
- `#this` references the object that is the current evaluation target. Inside collection selection or projection, this object can change per element.

Example:

~~~spel
#root.customer.name
~~~

The expression above specifies that name is read from customer belonging to the root object.

## 4. Variables: Referencing Values from EvaluationContext

Variables have a `#` prefix. The application registers variables on EvaluationContext and the expression references those variable names.

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

The result is the BigDecimal value registered for the `minimum` variable.

Variables can be combined with other components:

~~~spel
#minimum * 2
#customerName.toUpperCase()
price >= #minimum
~~~

Distinguish `minimum` and `#minimum`:

- `minimum` is a property name looked up on the current object.
- `#minimum` is a variable looked up in EvaluationContext.

If a variable has not been registered or the variable name does not match, the expression may not evaluate as expected.

## 5. Property Access, Indexer, and Method Calls

In addition to direct references, SpEL allows continuing operations on the value returned from an atomic component.

### 5.1. Property Access

~~~spel
customer.name
customer.address.city
~~~

Each dot moves to the object returned from the previous part. Reading properties is performed through a suitable PropertyAccessor in EvaluationContext.

### 5.2. Indexer

The indexer uses square brackets to access elements by index or key:

~~~spel
items[0]
customerMap['primary']
'Spring'[0]
~~~

Depending on the object, the indexer can access elements of an array, list, map, or string. For example, `'Spring'[0]` retrieves the first character via SpEL's indexer mechanism.

For maps, the expression inside square brackets is used as the key. For lists or arrays, the index specifies the element to read.

### 5.3. Method Calls

The method name is followed by parentheses and an argument list:

~~~spel
'Spring'.toUpperCase()
'Spring'.substring(0, 3)
customer.isActive()
~~~

The value of a method call expression is the value returned by the Java method. If the method returns String, the expression can produce String; if it returns Boolean, the result can be Boolean.

SpEL uses MethodResolver in the context to find a matching method. A successful call depends on the current object, method name, number and types of arguments, as well as configured accessibility.

## 6. Type References, Static Members, and Object Instantiation

SpEL can reference Java types using the `T(...)` operator:

~~~spel
T(java.lang.Math)
~~~

Type references are often used to call static members:

~~~spel
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 25)
~~~

The results are `10` and `25`, respectively.

The `new` operator allows object instantiation:

~~~spel
new java.lang.String('Spring')
~~~

The expression creates a String object with the content Spring.

Type references and object instantiation depend on TypeLocator, ConstructorResolver, and the capabilities allowed by EvaluationContext. Not every context enables all of these features.

## 7. Bean References

In a Spring environment with a configured BeanResolver, expressions can reference beans by name using the `@` symbol:

~~~spel
@systemProperties
~~~

Properties can be accessed or methods called on the resolved bean:

~~~spel
@environment.getProperty('app.name')
~~~

This syntax is useful when an expression needs to use a Spring-managed component. However, bean resolution must be supported and configured in EvaluationContext. Simply writing `@beanName` does not automatically cause every context to find the bean.

## 8. Operators Combining Atomic Components

Atomic components are often operands for operators. An operator's result can in turn become a subexpression in a larger calculation.

| Group | Example | Common Result Type |
|---|---|---|
| Arithmetic | `10 + 5`, `10 * 2` | Number |
| Comparison | `10 >= 5`, `'A' == 'A'` | Boolean |
| Logical | `true && false` | Boolean |
| String concatenation | `'Spring' + ' EL'` | String |
| Conditional | `true ? 'YES' : 'NO'` | Type of the selected branch |
| Elvis | `name ?: 'Unknown'` | Value of name or default value |
| Type check | `'text' instanceof T(String)` | Boolean |
| Regular expression | `'abc' matches 'a.*'` | Boolean |

For example, the expression:

~~~spel
(price * quantity) >= #minimum
~~~

is built from two references, multiplication, and comparison. Multiplication produces a numeric value; comparison uses that value to produce a Boolean.

Parentheses help group subexpressions and clarify execution order. When there are multiple operators, SpEL's operator precedence determines how it is parsed if parentheses are absent.

## 9. Inline Collections, Maps, Selection, and Projection

SpEL can create data structures directly in an expression.

### 9.1. Inline Lists

~~~spel
{1, 2, 3}
~~~

The expression creates a list. Elements can be accessed with an indexer:

~~~spel
{'Java', 'Spring', 'SpEL'}[1]
~~~

The result is `Spring`.

### 9.2. Inline Maps

~~~spel
{'name': 'Linh', 'active': true}
~~~

The expression creates a map containing key-value pairs. Values can be accessed by key:

~~~spel
{'name': 'Linh', 'active': true}['name']
~~~

The result is `Linh`.

### 9.3. Selection

Selection filters collection elements by condition:

~~~spel
{1, 2, 3, 4, 5}.?[#this > 3]
~~~

The result is a collection consisting of elements 4 and 5. In the selection condition, `#this` references the element currently being examined.

SpEL also has selection forms that take the first or last element matching the condition, using the `.^[...]` and `.$[...]` operators.

### 9.4. Projection

Projection creates a new collection by evaluating an expression on each element:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

The result is a collection consisting of 10, 20, and 30.

The return value of selection or projection is a collection or a corresponding value depending on the operation form used.

## 10. Null, Null-Safe Navigation, and Elvis

SpEL can return null when the expression is the null literal or when a property has a null value:

~~~spel
null
customer.nickname
~~~

Further accessing on a null object can cause an error. The null-safe navigation operator `?.` stops access when the object on the left is null:

~~~spel
customer?.address?.city
~~~

If customer or address is null, the expression returns null at the corresponding access position.

The Elvis operator `?:` provides a fallback value when the expression on the left is null:

~~~spel
customer.nickname ?: 'Unknown'
~~~

If nickname has a value, the result is nickname; if null, the result is the string Unknown.

Null is a valid returnable value. It differs from an evaluation error caused by being unable to perform an operation.

## 11. Return Value of Expression in Java

Expression provides getValue overloads to retrieve the result in an appropriate way.

### 11.1. Retrieving the Result as Object

~~~java
Object value = expression.getValue(context);
~~~

This approach is suitable when the result type is not known in advance. The return value can be an object of any type the expression produces, or null.

### 11.2. Requesting a Result Type

~~~java
Boolean result =
    expression.getValue(context, Boolean.class);
~~~

The target-type overload allows the application to specify the desired type. SpEL can use the context's TypeConverter to convert if possible.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("10 + 5");

Integer result = expression.getValue(Integer.class);
~~~

The result is an Integer with value 15.

If the value cannot be converted to the target type, evaluation may throw an error. Therefore, choose a target type matching the expected result.

### 11.3. Passing the Root Object Directly

When no separate context configuration is needed, the root object can be passed directly:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

Here product is the root object of the evaluation.

## 12. What Types Can an Expression Return?

| Expression Form | Example | Result |
|---|---|---|
| Numeric literal | `42` | Number |
| String literal | `'Spring'` | String |
| Boolean literal | `true` | Boolean |
| Null literal | `null` | null |
| Property | `product.price` | Type of the property |
| Variable | `#minimum` | Type of the variable value |
| Comparison | `price > 100` | Boolean |
| Arithmetic | `price * 2` | Appropriate numeric type |
| Method call | `name.toUpperCase()` | Type returned by the method |
| Inline list | `{1, 2, 3}` | List |
| Inline map | `{'a': 1}` | Map |
| Selection / Projection | `items.?[active]` | Collection or result according to the selection operation |

The return type is not determined solely by the expression form. It also depends on the actual types of objects, variable values, called methods, and conversions in the context.

## 13. Comprehensive Example: From Atomic Components to Final Value

Suppose there is a Product class with name and price properties. The application wants to check whether a product price meets a minimum threshold and generate a corresponding message.

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

Output:

~~~text
KEYBOARD
~~~

The expression can be decomposed as follows:

1. `price` is a property reference on the root object.
2. `#minimum` is a variable retrieved from EvaluationContext.
3. `price >= #minimum` is a comparison expression producing a Boolean.
4. The conditional operator `?:` selects one of the two branches based on the Boolean.
5. `name.toUpperCase()` reads the name property and then calls a method on the string.
6. The selected branch produces the string KEYBOARD.
7. `getValue(context, String.class)` returns the result in the String type requested by the application.

If minimum increases to 900000, the first branch is not selected and the result becomes BELOW LIMIT. The Expression remains unchanged; data in the context determines the branch and final value.

## 14. Distinguishing a Null Result from an Error

When working with return values, distinguish three situations:

- **Normal value:** the expression evaluates successfully and returns a number, string, Boolean, object, or collection.
- **Null value:** the expression evaluates successfully but its value is null.
- **Error:** SpEL cannot parse or execute the expression, such as invalid syntax, non-existent variable, inaccessible property, or inability to convert types.

Parsing errors usually occur when calling parseExpression. Evaluation errors usually appear when calling getValue.

If the application needs null handling, it can check the return value or use constructs such as null-safe navigation and Elvis suited to the expression's purpose.

## 15. Common Confusions

**Confusion 1: Every name without `#` is a variable.**  
Names like price are usually looked up as properties on the current object. Variables are referenced using #price.

**Confusion 2: Literals and runtime values are the same.**  
Literals are written directly in the expression. The runtime value of a property or variable is only determined when evaluation occurs.

**Confusion 3: An expression always returns a type known at parsing time.**  
The actual result type may depend on runtime data and the called method.

**Confusion 4: null means parsing failed.**  
null can be a valid result of an expression that has been parsed and evaluated successfully.

**Confusion 5: The target type of getValue changes the calculation.**  
The target type specifies the form of the result the application wants to receive. The expression logic is still determined by SpEL syntax.

## 16. Key Takeaways

- Literals, properties, variables, method calls, and type references are fundamental components that can provide values to an expression.
- Property names are usually looked up on the root object or current object; variable names have a `#` prefix and are retrieved from EvaluationContext.
- Indexers, method calls, and operators allow combining components into complex expressions.
- Expressions can return Number, String, Boolean, object, collection, map, or null.
- getValue() returns the result as Object; target-type overloads help the application request the desired type.
- The context's TypeConverter can support type conversion when compatible.
- null is a valid return value and differs from parsing or evaluation errors.

When analyzing a SpEL expression, identify each basic component, see where each component gets its value from, trace how operators combine them, and finally check the type and value returned by getValue.
