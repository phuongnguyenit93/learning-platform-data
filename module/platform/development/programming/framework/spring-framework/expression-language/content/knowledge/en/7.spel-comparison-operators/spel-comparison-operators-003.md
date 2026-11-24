# Atomic Expressions and Return Values in Spring Expression Language

Spring Expression Language (SpEL) provides an expression language for accessing data and performing operations on Java objects. An expression can be a simple literal such as the number 42, a property reference, or a combination of multiple elements such as method calls, comparisons, and collection operations.

To read SpEL syntax, two concepts need to be understood:

- **Atomic expression:** a way to refer to basic building blocks that can stand alone or serve as operands for other expressions, such as literals, variables, properties, method calls, and type references.
- **Evaluation result (return value):** the value SpEL produces when evaluating an expression in a specific context. The result can be a number, string, Boolean, object, collection, map, or null.

In this article, "atomic" is used in a pedagogical sense to group basic syntactic components. When analyzing an expression, identify where each component gets its value from, and then trace how operators combine them to produce the final result.

## 1. What Components Make Up a SpEL Expression?

Common components can be grouped into three categories:

1. **Values and references:** literals, property names, variables, root object, type references, and bean references.
2. **Access and invocation:** property access, indexers, method calls, and object instantiation.
3. **Combination and transformation:** arithmetic, comparison, logical, and conditional operators, selection, projection, and collection operations.

Example:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

This expression combines property access, selection, variables, comparison, projection, and multiplication. The result is a new collection created from the orders that satisfy the condition.

## 2. Literals: Values Written Directly

A literal is the simplest component. Its value is determined directly in the expression string without looking up from the root object or variables.

### 2.1. Numeric Literals

~~~spel
42
3.14
0x2A
42L
3.14D
3.14M
~~~

SpEL supports integer, floating-point, and hexadecimal literals. Some common suffixes:

- L: specifies a long literal.
- D: specifies a double literal.
- M: specifies a BigDecimal literal.

For example, 42L is a long literal, while 3.14M is a BigDecimal literal. Numeric types matter when an expression combines multiple operand types or when the application requires a specific result type.

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

The results are Spring Expression and SPRING, respectively.

### 2.3. Boolean and null Literals

~~~spel
true
false
null
~~~

The first two literals produce Boolean values. The null literal produces a null reference value. A null result is valid and should be distinguished from an error occurring during evaluation.

## 3. Property References and the Root Object

An identifier without a # prefix is generally interpreted as a property or member of the current object.

Suppose we have a Product class:

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

Property expressions can be chained together with dots:

~~~spel
customer.name
customer.address.city
product.category.name
~~~

Each dot switches access to the object returned by the preceding part. Reading properties is performed through the appropriate PropertyAccessor in the EvaluationContext.

Two special references help identify the current object:

- #root always references the root object of the evaluation.
- #this references the current evaluation target object. In collection selection or projection, this object can change for each element.

Example:

~~~spel
#root.customer.name
~~~

The expression above explicitly specifies that name is read from customer on the root object.

## 4. Variables: Referencing Values from EvaluationContext

Variables have a # prefix. The application registers a variable on the EvaluationContext and the expression references that variable name.

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

Distinguish between minimum and #minimum:

- minimum is a property name looked up on the current object.
- #minimum is a variable looked up in the EvaluationContext.

If the variable has not been registered or the variable name does not match, the expression may not evaluate as expected.

## 5. Property Access, Indexers, and Method Calls

Besides direct references, SpEL allows further operations on the value returned from a basic component.

### 5.1. Property Access

~~~spel
customer.name
customer.address.city
~~~

Each dot moves to the object returned by the previous part. If an intermediate element is null, further access can raise an error. Null-safe navigation can be used where appropriate:

~~~spel
customer?.address?.city
~~~

When the object on the left of the null-safe operator is null, the corresponding access returns null instead of continuing to access on a null object.

### 5.2. Indexers

Indexers use square brackets to access elements by index or key:

~~~spel
items[0]
customerMap['primary']
'Spring'[0]
~~~

Depending on the object, an indexer can access an element of an array, list, map, or string. For a map, the expression in square brackets is used as the key. For a list or array, the index specifies the element to read.

### 5.3. Method Calls

A method name is followed by parentheses and an argument list:

~~~spel
'Spring'.toUpperCase()
'Spring'.substring(0, 3)
customer.isActive()
~~~

The value of a method call expression is the value returned by the Java method. If the method returns a String, the expression can produce a String; if it returns a Boolean, the result can be a Boolean.

SpEL uses a MethodResolver in the context to find the matching method. A successful call depends on the current object, method name, number and types of arguments, as well as configured accessibility.

## 6. Type References, Static Members, and Object Instantiation

SpEL can reference a Java type using the T(...) operator:

~~~spel
T(java.lang.Math)
~~~

Type references are commonly used to invoke static members:

~~~spel
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 25)
~~~

The results are 10 and 25, respectively.

The new operator allows instantiating objects:

~~~spel
new java.lang.String('Spring')
~~~

The expression creates a String object with the content Spring.

Type references and object instantiation depend on TypeLocator, ConstructorResolver, and the capabilities allowed by the EvaluationContext. Not every context enables all of these features.

## 7. Bean References

In a Spring environment configured with a BeanResolver, expressions can reference beans by name using the @ symbol:

~~~spel
@systemProperties
~~~

Properties can be accessed or methods invoked on the resolved bean:

~~~spel
@environment.getProperty('app.name')
~~~

This syntax is useful when an expression needs to use a Spring-managed component. Bean resolution must be supported and configured in the EvaluationContext. Simply writing @beanName does not automatically make every context locate the bean.

## 8. Operators Combining Basic Components

Basic components often serve as operands for operators. An operator's result can in turn become a sub-expression in a larger calculation.

| Category | Example | Common Result Type |
|---|---|---|
| Arithmetic | 10 + 5, 10 * 2 | Number |
| Comparison | 10 >= 5, 'A' == 'A' | Boolean |
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

Parentheses help group sub-expressions and clarify evaluation order. When there are multiple operators, SpEL's operator precedence determines how it is parsed if parentheses are absent.

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

The result is a collection consisting of elements 4 and 5. Inside the selection condition, #this references the element currently being evaluated.

SpEL also has selection forms that retrieve the first or last element matching a condition, using the .^[...] and .$[...] operators.

### 9.4. Projection

Projection creates a new collection by evaluating an expression on each element:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

The result is a collection containing 10, 20, and 30.

The return value of selection or projection is a collection or the corresponding value according to the operation form used.

## 10. Expression Return Values in Java

Expression provides getValue overloads to obtain results in the appropriate way.

### 10.1. Retrieving the Result as Object

~~~java
Object value = expression.getValue(context);
~~~

This approach is suitable when the result type is not known in advance. The returned value can be an object of any type produced by the expression, or null.

### 10.2. Requesting a Result Type

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

If the value cannot be converted to the target type, evaluation may raise an error. Therefore, choose a target type suited to the expected result.

### 10.3. Passing the Root Object Directly

When a custom context configuration is not needed, the root object can be passed directly:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

Here product is the root object of the evaluation.

## 11. What Types Can an Expression Return?

| Expression Form | Example | Result |
|---|---|---|
| Numeric literal | 42 | Number |
| String literal | 'Spring' | String |
| Boolean literal | true | Boolean |
| null literal | null | null |
| Property | product.price | Type of the property |
| Variable | #minimum | Type of the variable's value |
| Comparison | price > 100 | Boolean |
| Calculation | price * 2 | Appropriate numeric type |
| Method call | name.toUpperCase() | Return type of the method |
| Inline list | {1, 2, 3} | List |
| Inline map | {'a': 1} | Map |
| Selection / Projection | items.?[active] | Collection or selection result |

The return type is not determined solely by the expression name. It also depends on the actual runtime type of the object, variable values, invoked methods, and conversions in the context.

## 12. Comprehensive Example: From Basic Components to Final Value

Suppose we have a Product class with name and price properties. The application wants to check whether the product price meets a minimum threshold and produce a corresponding message.

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
2. #minimum is a variable retrieved from the EvaluationContext.
3. price >= #minimum is a comparison expression producing a Boolean.
4. The conditional operator ?: selects one of the two branches based on the Boolean.
5. name.toUpperCase() reads the name property and calls a method on the string.
6. The selected branch produces the string KEYBOARD.
7. getValue(context, String.class) returns the result as the String type requested by the application.

If minimum increases to 900000, the first branch is not selected and the result becomes BELOW LIMIT. The Expression remains unchanged; the data in the context determines the branch and final value.

## 13. Distinguishing null Results from Errors

When working with return values, three situations must be distinguished:

- **Normal value:** the expression evaluates successfully and returns a number, string, Boolean, object, or collection.
- **null value:** the expression evaluates successfully, but the obtained value is null.
- **Error:** SpEL cannot parse or execute the expression, such as invalid syntax, a nonexistent variable, an inaccessible property, or an unconvertible type.

Parsing errors usually occur when calling parseExpression. Evaluation errors usually occur when calling getValue.

If the application needs to handle null, it can check the returned value or use constructs such as null-safe navigation and Elvis appropriate for the expression's purpose.

## 14. Common Misconceptions

**Misconception 1: Every name without # is a variable.**  
A name like price is usually looked up as a property on the current object. Variables are referenced with #price.

**Misconception 2: Literals and runtime values are the same.**  
A literal is written directly in the expression. The runtime value of a property or variable is only determined when evaluation takes place.

**Misconception 3: An expression always returns a type known at parse time.**  
The actual result type can depend on runtime data and invoked methods.

**Misconception 4: null means parsing failed.**  
null can be a valid result of an expression that was parsed and evaluated successfully.

**Misconception 5: The target type of getValue changes the calculation.**  
The target type specifies the form of the result the application wants to receive. The expression logic is still determined by SpEL syntax.

## 15. Key Takeaways

- Literals, properties, variables, method calls, and type references are basic components that can supply values to an expression.
- Property names are usually looked up on the root object or current object; variable names have a # prefix and are retrieved from the EvaluationContext.
- Indexers, method calls, and operators allow combining components into complex expressions.
- An expression can return a Number, String, Boolean, object, collection, map, or null.
- getValue() returns the result as an Object; overloads with a target type help the application request the desired type.
- The context's TypeConverter can support type conversion when compatible.
- null is a valid result and is different from a parsing or evaluation error.

When analyzing a SpEL expression, identify each basic component, see where each component gets its value, trace how operators combine them, and finally check both the type and value returned by getValue.
