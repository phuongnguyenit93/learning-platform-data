# setVariable and #variable Syntax in Spring Expression Language

Spring Expression Language (SpEL) allows an expression to use data supplied from outside the expression string. A common approach is to register a variable in \`EvaluationContext\` and then reference that variable using the \`#variableName\` syntax.

In Java, with \`StandardEvaluationContext\`, an application can use \`setVariable(name, value)\` to register a value. When writing an expression, the variable name has the \`#\` prefix. For example, register \`minimum\` with \`context.setVariable("minimum", ...)\`, then reference it with \`#minimum\`.

Both sides must use the same variable name. Once this convention is clearly understood, you can pass data, objects, collections, or configuration values into SpEL without embedding data directly in the expression string.

## 1. What Is a Variable in SpEL?

A variable is a value stored in EvaluationContext and accessed by an expression using a name prefixed with \`#\`.

Examples:

~~~spel
#minimum
#customerName
#order.total
~~~

Where:

- \`#minimum\` references the variable named minimum.
- \`#customerName\` references the variable customerName.
- \`#order.total\` retrieves the order variable and then reads the total property on that object.

A variable can hold many data types:

- String, Boolean, and numeric types.
- Domain objects such as Customer, Order, or Product.
- Collections, arrays, and Maps.
- Service objects or utility objects if the application proactively provides them.

SpEL does not need to know the concrete type of every variable in advance when parsing an expression. The actual value is looked up in the context at evaluation time.

## 2. Registering Variables with setVariable

With \`StandardEvaluationContext\`, the \`setVariable(String name, Object value)\` method registers or updates a variable.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", 500);
context.setVariable("customerName", "Linh");
context.setVariable("active", true);
~~~

The name passed to \`setVariable\` does not have the \`#\` prefix. The prefix only appears when referencing the variable inside the SpEL string.

For example, after registering:

~~~java
context.setVariable("minimum", 500);
~~~

the expression uses:

~~~spel
#minimum
~~~

Do not write the variable name as \`"#minimum"\` in the setVariable call. The registered name is \`"minimum"\`; the \`#minimum\` syntax belongs to the expression.

## 3. Reading Variables with #variable Syntax

After a variable is registered, SpEL can read its value using the \`#\`-prefixed name.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#customerName");

String name =
    expression.getValue(context, String.class);
~~~

Result:

~~~text
Linh
~~~

The process consists of three steps:

1. Create an EvaluationContext.
2. Register the value under the name customerName.
3. Parse the expression referencing #customerName and evaluate it with the context.

If the context is not passed into the evaluation call, the expression does not have the variable data from the created context. Therefore, make sure the getValue call uses the right EvaluationContext containing the required variables.

## 4. Using Multiple Variables in One Expression

An expression can reference multiple variables at the same time:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);
context.setVariable("taxRate", new BigDecimal("0.10"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#price * #quantity * (1 + #taxRate)"
);

BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Result:

~~~text
825000.00
~~~

Each variable supplies one operand to the expression:

- #price supplies the unit price.
- #quantity supplies the quantity.
- #taxRate supplies the tax rate.
- Arithmetic operators combine these values into the result.

This approach keeps logic in the expression and data in the context. When data changes, the application can update variables without creating a new expression string.

## 5. Updating Variable Values

Calling \`setVariable\` again with the same name updates the variable value in the context:

~~~java
context.setVariable("minimum", 500);

Expression expression =
    parser.parseExpression("#minimum * 2");

Integer first =
    expression.getValue(context, Integer.class);

// Update the variable value.
context.setVariable("minimum", 900);

Integer second =
    expression.getValue(context, Integer.class);
~~~

Result:

~~~text
first = 1000
second = 1800
~~~

The Expression can be reused. On the next getValue call, SpEL looks up the current variable value in the context.

This is useful when the same rule needs to be evaluated against multiple sets of input data. The application can retain the parsed Expression and change the variables on each processing pass.

## 6. Registering Multiple Variables at Once

Besides \`setVariable\`, \`StandardEvaluationContext\` provides \`setVariables(Map<String, Object>)\` to register a group of variables:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("minimum", new BigDecimal("500000"));
variables.put("customerName", "Linh");
variables.put("quantity", 3);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariables(variables);
~~~

Then the expression can reference each variable:

~~~spel
#minimum
#customerName
#quantity
~~~

Map-based registration is convenient when data has already been grouped into a structure before evaluation.

Key names in the Map are variable names and do not include the \`#\` symbol. For example, the key \`"quantity"\` is referenced using \`#quantity\`.

## 7. Variables Can Hold Objects

A variable does not only hold primitive types or String. It can hold a complete Java object.

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

Registering the object:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("product", product);
~~~

The expression can read properties on the object variable:

~~~spel
#product.name
#product.price
#product.price * 2
~~~

Example:

~~~java
Expression expression =
    parser.parseExpression("#product.name");

String name =
    expression.getValue(context, String.class);
~~~

The result is Keyboard.

The syntax \`#product.name\` performs two operations: looking up the product variable in the context, and then reading the name property on the returned object.

## 8. Distinguishing Variables from the Root Object

The root object is the base object of an evaluation. A variable is a value registered separately in EvaluationContext.

Suppose Product is the root object and there is a minimum variable:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Expression:

~~~spel
price >= #minimum
~~~

Where:

- \`price\` is read on the current object, which initially is the root object product.
- \`#minimum\` is retrieved from the context's variable set.

You can explicitly reference the root object with \`#root\`:

~~~spel
#root.price >= #minimum
~~~

Both ways express comparing the root object's price against the minimum variable.

## 9. Distinguishing Variables from #root and #this

SpEL has two special variables:

- \`#root\` references the root object of the evaluation.
- \`#this\` references the object currently targeted for evaluation.

They are not ordinary business variables registered via setVariable.

Example:

~~~spel
#root.customer.name
~~~

The expression reads customer.name from the root object.

In selection or projection on a collection:

~~~spel
#orders.?[#this.total >= #minimum]
~~~

\`#this\` is the order currently being inspected; \`#minimum\` is an application-registered variable. The initial root object is still referenced by \`#root\`.

Distinguishing these names helps avoid confusion between application-supplied data and SpEL's special references.

## 10. Nonexistent Variables and Null-Valued Variables

A variable may not be registered or may be registered with a null value. In both cases, when an expression reads the variable, the received value is null.

Example:

~~~java
context.setVariable("nickname", null);
~~~

Expression:

~~~spel
#nickname
~~~

returns null.

If a variable has not been registered, the lookup also yields no value and the expression receives null. Therefore, you should not rely solely on the result of #variable to distinguish an unregistered variable from a registered variable whose value is null.

If the application needs to know whether a variable was provided, manage key presence in the data Map or check in Java code before evaluating.

You can use Elvis to provide a default value:

~~~spel
#nickname ?: 'Anonymous'
~~~

If nickname is null, the result is Anonymous. If it has a value, the expression returns the nickname value.

## 11. Variable Names Are Case-Sensitive

Variable names must be referenced consistently. Example:

~~~java
context.setVariable("customerName", "Linh");
~~~

Correct expression:

~~~spel
#customerName
~~~

An expression using a different casing:

~~~spel
#customername
~~~

does not reference the same variable name. Use a consistent naming convention, typically lower camel case in Java style.

When troubleshooting errors, compare the exact name passed into setVariable with the name after the # symbol in the expression.

## 12. Variables and Bean References Are Two Different Mechanisms

SpEL uses two different symbols:

| Syntax | Mechanism | How Provided |
|---|---|---|
| #customer | Variable reference | Registered in EvaluationContext |
| @customerService | Bean reference | BeanResolver looks up bean in Spring container |

Example:

~~~java
context.setVariable("customer", customer);
~~~

The expression uses:

~~~spel
#customer.name
~~~

Meanwhile:

~~~spel
@customerService.findById(#customerId)
~~~

references a Spring-managed bean and passes the customerId variable as an argument.

Registering a variable named customerService does not automatically turn #customerService into @customerService. These two namespaces are independent.

## 13. Registering Functions via Variables

SpEL can also invoke functions registered in the context. In StandardEvaluationContext, a function is registered using a Method object associated with a variable name.

For example, create a static method:

~~~java
public class TextFunctions {
    public static String upper(String value) {
        return value.toUpperCase();
    }
}
~~~

Register the Method:

~~~java
Method upperMethod =
    TextFunctions.class.getDeclaredMethod(
        "upper",
        String.class
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("upper", upperMethod);
~~~

Invoke the function in an expression:

~~~spel
#upper('spring')
~~~

Result:

~~~text
SPRING
~~~

The function name is registered without the # symbol in setVariable; the function call syntax in SpEL uses #name(...).

Register public methods with clear signatures matching the argument types passed by the expression. Function reference is a distinct capability from storing an ordinary value in a variable, even though both are looked up in the context's variable namespace.

## 14. Variables Can Be Used in Template Expressions

Variables also work in SpEL segments inside a template:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Hello #{#customerName}, total is #{#total}.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");
context.setVariable("total", new BigDecimal("750000"));

String message =
    template.getValue(context, String.class);
~~~

Result:

~~~text
Hello Linh, total is 750000.
~~~

ParserContext determines how the template is parsed. EvaluationContext supplies the variables used when evaluating the SpEL segments.

## 15. Managing Context and Data Across Evaluations

EvaluationContext stores the variables registered by the application. If multiple processing runs use the same context, updating a variable can affect subsequent evaluations.

Example:

~~~java
context.setVariable("customerName", "Linh");
String first =
    expression.getValue(context, String.class);

context.setVariable("customerName", "Minh");
String second =
    expression.getValue(context, String.class);
~~~

The same Expression can produce different results because the variable value changed.

In an application handling multiple concurrent requests, manage the context according to the appropriate data scope. Avoid accidentally sharing a context with mutable variables across independent requests, because one update can affect another evaluation.

A clear approach is to create a context for each processing pass or unit of work, register the required variables, and then evaluate the expression.

## 16. Complete Example: Passing Business Data via Variables

Suppose an application needs to calculate an order's total amount and check whether the order exceeds a threshold.

~~~java
BigDecimal price = new BigDecimal("250000");
int quantity = 3;
BigDecimal minimum = new BigDecimal("700000");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", price);
context.setVariable("quantity", quantity);
context.setVariable("minimum", minimum);

ExpressionParser parser = new SpelExpressionParser();

Expression totalExpression =
    parser.parseExpression("#price * #quantity");

Expression eligibleExpression =
    parser.parseExpression("#price * #quantity >= #minimum");

BigDecimal total =
    totalExpression.getValue(context, BigDecimal.class);

Boolean eligible =
    eligibleExpression.getValue(context, Boolean.class);

System.out.println(total);
System.out.println(eligible);
~~~

Result:

~~~text
750000
true
~~~

This organization separates three parts:

1. Java prepares the data and registers the variables.
2. SpEL describes the calculation rules using #variable.
3. getValue evaluates the rules on the current data and returns the results.

If quantity or minimum changes, the application only needs to update the variable in the context and re-evaluate the expression.

## 17. Common Misconceptions

**Misconception 1: Passing a variable name to setVariable must include the # symbol.**  
The registered name is \`"minimum"\`; only the expression uses \`#minimum\`.

**Misconception 2: Variables and properties on the root object are the same.**  
\`#minimum\` looks up a variable in the context; \`minimum\` usually looks up a property on the current object.

**Misconception 3: A variable is a Spring bean.**  
Variables are registered in EvaluationContext; bean references use @ and require a BeanResolver.

**Misconception 4: Parsing an expression fixes the variable values.**  
Values are looked up at evaluation time. Updating a variable can cause the same Expression to return a different result.

**Misconception 5: Null variables and unregistered variables can always be distinguished inside an expression.**  
Both can read as null. If you need to distinguish them, manage key presence on the Java side.

**Misconception 6: A stateful context can be shared across all requests without management.**  
Variables updated in a context can affect other evaluations. Choose an appropriate context lifecycle.

## 18. Key Takeaways

- \`StandardEvaluationContext.setVariable(name, value)\` registers or updates a variable.
- The name in setVariable has no # prefix; expressions reference the variable with \`#variableName\`.
- \`setVariables(Map<String, Object>)\` allows registering multiple variables at once.
- Variables can hold simple values, objects, collections, or arrays.
- Properties on an object variable can be read using syntax like \`#product.price\`.
- Variables differ from root properties, #root, #this, and @ bean references.
- Variables are looked up at evaluation time, so the same Expression can produce different results after updating the context.
- Null values and unregistered variables can both evaluate to null.
- Functions can be registered via Method in the variable namespace and invoked using #function(...) syntax.
- Manage the EvaluationContext lifecycle to avoid unintended sharing of variable state.

When using variables in SpEL, keep names consistent between setVariable and #variable, register the proper data types, pass the right EvaluationContext when calling getValue, and manage the context according to the scope of the data being evaluated.
