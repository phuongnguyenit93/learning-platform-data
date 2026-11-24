# Expression object and getValue calls in Spring Expression Language (SpEL)

In SpEL, evaluating an expression typically consists of two stages: parsing the expression string to create an **Expression** object, and then calling **getValue()** on that object to obtain the result. Separating these two stages allows an application to parse an expression once, reuse the parsed result, and supply a different context or root object for each evaluation.

This lesson focuses on the Expression object, the forms of calling getValue(), the role of the root object, and EvaluationContext.

## 1. Position of Expression in the SpEL workflow

The three commonly encountered components are:

- **ExpressionParser**: accepts a SpEL string and parses its syntax. The common implementation class is **SpelExpressionParser**.
- **Expression**: represents the parsed expression. This object provides methods to evaluate the expression, obtain the result type, or assign a value when the expression supports writing.
- **EvaluationContext**: provides the environment during evaluation, such as the root object, variables, functions, property accessors, method resolvers, and type converters.

Basic flow:

1. Create an ExpressionParser.
2. Call parseExpression(...) to convert the string into an Expression.
3. Call getValue(...) on the Expression, passing a root object or EvaluationContext if the expression needs them.
4. Receive the result and convert it to the desired type if needed.

Minimal example:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("1 + 2 * 3");
Integer result = expression.getValue(Integer.class);

// result = 7
~~~

parseExpression(...) performs syntax parsing; getValue(...) is what actually evaluates the expression. Therefore, syntax errors usually appear at the parse step, while errors caused by data or evaluation operations usually appear at the getValue step.

## 2. Expression is the object representing the parsed expression

Expression is an interface in the org.springframework.expression package. It is neither the original expression string nor the parser. The parser creates an Expression so the application can evaluate the same expression multiple times.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("'Hello ' + 'Spring'");

String message = expression.getValue(String.class);
~~~

In the example above:

- The string passed to parseExpression(...) is SpEL syntax.
- The return value of parseExpression(...) is stored in the expression variable.
- getValue(String.class) evaluates the expression and requests a result of type String.
- message receives the value Hello Spring.

You can keep the Expression in a field or configuration structure for reuse. When the same expression needs to run on multiple data objects, the application can reuse the Expression and pass the corresponding root object into each getValue() call.

Parsing once and evaluating many times avoids repeating syntax parsing work in iterative processing flows. The root object and EvaluationContext can still vary between evaluations.

## 3. Common forms of calling getValue()

getValue() has multiple overloads to choose how input data and the result type are provided.

| Call form | Meaning |
|---|---|
| getValue() | Evaluates using the default context without explicitly passing a root object; returns Object. |
| getValue(Class<T>) | Evaluates using the default context and requests a result of type T. |
| getValue(Object rootObject) | Evaluates with the passed root object; returns Object. |
| getValue(Object rootObject, Class<T>) | Evaluates with the root object and requests a result of type T. |
| getValue(EvaluationContext context) | Evaluates using the configured EvaluationContext. |
| getValue(EvaluationContext context, Class<T>) | Uses the EvaluationContext and requests result type T. |
| getValue(EvaluationContext context, Object rootObject, Class<T>) | Specifies the EvaluationContext, the root object for the call, and result type T. |

Example using a result type:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("10 * 5");

Integer number = expression.getValue(Integer.class);
~~~

If you use the zero-argument getValue(), the result has type Object and usually requires casting before use. The getValue(Class<T>) form clearly expresses the type the code expects, while also allowing the system to convert types through the context's TypeConverter when a suitable converter exists.

Not every expression can be evaluated without root data. Arithmetic or literal expressions can evaluate on their own, whereas an expression referencing a property such as name needs a root object with the corresponding property.

## 4. Root object: the object where the expression starts accessing

The root object is the object used as the starting point when SpEL resolves properties and methods without a variable prefix. For example, with the expression name, SpEL looks for the property name on the root object.

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }
}
~~~

Evaluating an expression on a Customer object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = new Customer("Lan", 25);

Expression greeting =
        parser.parseExpression("'Hello ' + name");

String message = greeting.getValue(customer, String.class);

// message = "Hello Lan"
~~~

In this call, customer is the root object. The property name `name` in the expression is resolved from the customer object. SpEL can access Java properties via the property accessor mechanism; for standard JavaBeans, public getters are the clear and common way to expose them.

The root object can be provided directly to getValue(...), or placed inside the EvaluationContext. If the expression only uses literals or standalone operations, passing a root object is not necessary.

## 5. EvaluationContext: the expression evaluation environment

EvaluationContext contains the rules and data that SpEL needs during evaluation. Depending on the expression type, the context can provide:

- A root object used for unprefixed property and method references.
- Variables referenced with the #variableName syntax.
- Functions registered in the context.
- PropertyAccessor and MethodResolver to control how properties are accessed or methods are invoked.
- TypeConverter and TypeLocator for type conversion and lookup.
- BeanResolver to resolve bean references with the @beanName syntax.

Example combining a root object and a variable:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

Customer customer = new Customer("Lan", 25);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);

Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible = eligibility.getValue(context, Boolean.class);

// eligible = true
~~~

In the example:

- customer is set as the context's root object.
- minimumAge is registered as a variable.
- age is a property of the root object.
- #minimumAge is a variable in the EvaluationContext.
- getValue(context, Boolean.class) evaluates the expression in the context and requests a Boolean result.

You can create an EvaluationContext without a root object and then pass the root object separately for each call:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimumAge", 18);

Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

Boolean eligible =
        eligibility.getValue(context, customer, Boolean.class);
~~~

This approach is useful when you want to keep the evaluation configuration, such as variables or converters, separate from the data of each evaluation.

### 5.1. StandardEvaluationContext

StandardEvaluationContext provides a fuller set of evaluation features. It is suitable when expressions need to access properties, invoke methods, or use advanced SpEL capabilities. Applications can register variables, functions, property accessors, method resolvers, type converters, and bean resolvers.

For example, when integrating with a Spring BeanFactory, you can configure BeanFactoryResolver as the BeanResolver:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Once a BeanResolver is configured, expressions can reference beans using the @pricingService syntax. Without configuring an appropriate bean resolver, bean references do not work automatically just because the application uses Spring.

### 5.2. SimpleEvaluationContext

SimpleEvaluationContext is designed for situations where SpEL's capabilities need to be restricted, especially data binding. Applications explicitly choose the capabilities to allow instead of enabling all features by default as StandardEvaluationContext does.

Example using read-only property access:

~~~java
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

String name = parser.parseExpression("name")
        .getValue(context, customer, String.class);
~~~

SimpleEvaluationContext is suitable when you only need to read data from an object. If the expression needs to call methods or use other advanced features, you must choose the corresponding builder configuration and carefully consider the access scope.

## 6. Requesting the result type and type conversion

The overloads accepting Class<T> allow declaring the type the application expects:

~~~java
Expression expression = parser.parseExpression("1 + 2");
Integer result = expression.getValue(Integer.class);
~~~

SpEL uses the TypeConverter attached to the EvaluationContext to convert the result to the requested type when a matching conversion rule exists. Therefore, requesting a type is not merely a regular Java cast. If conversion is not possible, evaluation may throw an EvaluationException.

You should choose a specific result type when the application knows it needs Boolean, String, Integer, or a business domain type. This clarifies the contract between the expression and Java code, while avoiding casting Object in many places.

If the expression returns a complex type, request that exact type or receive Object and check the type intentionally. Do not assume every expression returns a fixed type if the expression content can change.

## 7. Errors at the parse step and the getValue step

The two stages have different error groups:

- **ParseException**: the expression is syntactically invalid or the parser cannot parse the input string.
- **EvaluationException**: the expression has been parsed, but cannot be evaluated in the current context. Examples: a property does not exist, no matching method exists, a variable is unregistered, or the result type cannot be converted.

For example, the expression name may parse successfully and still fail during getValue() if the root object lacks the name property or the context lacks a suitable access mechanism.

~~~java
try {
    Expression expression = parser.parseExpression("age >= #minimumAge");
    Boolean result = expression.getValue(context, Boolean.class);
} catch (ParseException ex) {
    // Handle expression syntax error.
} catch (EvaluationException ex) {
    // Handle error during expression evaluation.
}
~~~

When diagnosing an error, determine whether it occurred in parseExpression(...) or getValue(...). Then inspect the expression string, root object, context variables, property/method accessibility, and the requested result type.

## 8. Design and usage notes

1. **Parse once, evaluate many times:** keep the Expression if the same expression is used repeatedly. There is no need to create a parser and re-parse the string on every invocation if the expression does not change.
2. **Choose the right root object:** unprefixed property names are resolved from the current root object. Pass the root object or set it in the EvaluationContext.
3. **Distinguish properties from variables:** name is usually a property on the root object; #name is a variable registered in the EvaluationContext.
4. **Use an explicit result type:** prefer getValue(Class<T>) or the corresponding overload when the desired result type is known.
5. **Choose the context based on feature scope:** use StandardEvaluationContext when full capabilities are needed; use SimpleEvaluationContext with a restricted configuration when only data access is required.
6. **Do not arbitrarily evaluate untrusted expressions:** StandardEvaluationContext can allow property access and method invocation via reflection. SpEL also supports advanced syntax such as type references, object creation, and bean references when the environment permits. If users can enter expressions themselves, restrict the allowed features, data, and accessible objects; do not treat SpEL strings as harmless data.
7. **Separate syntax errors from data errors:** parse first to catch invalid syntax, then handle EvaluationException at the evaluation boundary.

## 9. Summary

- parseExpression(String) turns a SpEL string into an Expression object.
- Expression represents the parsed expression and provides getValue(...) for evaluation.
- getValue() returns Object; overloads with Class<T> specify the desired result type.
- The root object is the starting point for resolving properties and methods.
- EvaluationContext provides the root object, variables, functions, accessors, resolvers, and type conversion.
- StandardEvaluationContext supports rich features; SimpleEvaluationContext helps limit the evaluation surface.
- An Expression can be reused with different data or contexts, but access permissions must be controlled when expressions come from untrusted sources.
