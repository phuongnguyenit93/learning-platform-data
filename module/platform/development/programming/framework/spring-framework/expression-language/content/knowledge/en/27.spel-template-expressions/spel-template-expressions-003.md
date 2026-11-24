# Mixing Fixed Text with Dynamic Expressions in SpEL

## 1. What Is a Template Expression?

Spring Expression Language (SpEL) supports template expressions to combine fixed text with the results of expressions evaluated at runtime. Text outside the delimiter pair is preserved as-is; the part inside the delimiters is processed by the parser as a SpEL expression.

With the default template context, the dynamic part is placed inside `#{...}`:

~~~text
Hello #{customer.name}, your order is #{orderCode}.
~~~

If customer.name is Lan and orderCode is ORD-1001, the result looks like:

~~~text
Hello Lan, your order is ORD-1001.
~~~

Template expressions are useful when generating labels, messages, descriptions, configuration content, or display strings that contain both fixed parts and changing data. Instead of concatenating multiple strings in Java, you can place the text and dynamic expressions side by side in a readable template.

## 2. Using TemplateParserContext When Parsing Templates

When parsing a template directly with SpEL, pass a ParserContext so the parser knows the input string is a template. Spring provides TemplateParserContext with the default delimiter pair `#{` and `}`:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Hello #{name}!",
        new TemplateParserContext());

String result = template.getValue(customer, String.class);

System.out.println(result); // Hello Lan!
~~~

In this example:

- `Hello ` and `!` are fixed text.
- `name` is a SpEL expression evaluated against the root object customer.
- TemplateParserContext tells the parser that the content between `#{` and `}` is the dynamic part.
- The result of the entire template is a String.

If you call `parseExpression(source)` without passing a template ParserContext, the parser does not automatically understand `#{...}` segments as parts to interpolate. When using a template with fixed and dynamic parts, specify the appropriate context.

## 3. Mixing Multiple Text Segments and Expressions

A template can contain multiple dynamic parts. Each `#{...}` segment is evaluated and combined with the surrounding text segments:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Order #{code} | Customer #{customer.name} | Total #{total}",
        new TemplateParserContext());

String description = template.getValue(order, String.class);

System.out.println(description);
// Order ORD-1001 | Customer Lan | Total 150
~~~

You can place punctuation, spaces, separators, and labels outside the expression parts. This helps readers recognize the result structure directly from the template.

Each dynamic part is an independent SpEL expression within the same template. You can use property access, operations, comparisons, method calls, variables, or ternary conditions inside each delimiter pair.

## 4. Evaluating Templates with a Root Object

When passing a root object to getValue, direct properties inside the dynamic part are resolved from that object:

~~~java
public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

public class Order {
    private final String code;
    private final Customer customer;
    private final int total;

    public Order(String code, Customer customer, int total) {
        this.code = code;
        this.customer = customer;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public Customer getCustomer() {
        return customer;
    }

    public int getTotal() {
        return total;
    }
}

Order order = new Order(
        "ORD-1001",
        new Customer("Lan"),
        150);

Expression template = parser.parseExpression(
        "Order #{code} belongs to #{customer.name}. Total: #{total}",
        new TemplateParserContext());

String message = template.getValue(order, String.class);
~~~

In the template, `code`, `customer.name`, and `total` are all read from the root object order. No `#` prefix is needed when referencing properties of the root object.

If you want to use a variable in EvaluationContext, you need to add the `#` prefix and provide the variable before evaluation.

## 5. Combining Root Object with Variables

A template can combine properties of the root object and variables passed through StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("currency", "VND");
context.setVariable("operator", "Web");

Expression template = parser.parseExpression(
        "Order #{code} | Total: #{total} #{#currency} | Source: #{#operator}",
        new TemplateParserContext());

String result = template.getValue(context, String.class);
~~~

In this example:

- `code` and `total` are read from the root object order.
- `#currency` and `#operator` are read from variables in the context.
- The text `Order`, `Total:`, and `Source:` are preserved as-is.

Passing variables allows reusing the same template with different data without recreating the expression source.

## 6. Using Conditional Expressions in Templates

Dynamic parts can contain ternary operators or Boolean expressions to generate content that varies by state:

~~~java
Expression template = parser.parseExpression(
        "Payment: #{paid ? 'received' : 'pending'}",
        new TemplateParserContext());

String message = template.getValue(order, String.class);
~~~

If the paid property is true, the result contains the text received; if false, the result contains pending.

You can combine conditions with properties and arithmetic operations:

~~~java
Expression template = parser.parseExpression(
        "Shipping: #{total >= 1000 ? 'free' : 'calculated at checkout'}",
        new TemplateParserContext());
~~~

Keep dynamic parts short and focused on a single decision. If a condition has multiple levels or contains lengthy business rules, move the rules into a clearly named Java method and call the method or read the resulting property in the template.

## 7. Using Null-Safe Navigation and Default Values

Nested properties can be null. You can use null-safe navigation in the dynamic part to avoid accessing a property on a null object, and then use the Elvis operator to provide a default value:

~~~java
Expression template = parser.parseExpression(
        "Customer: #{customer?.name ?: 'Guest'}",
        new TemplateParserContext());

String result = template.getValue(order, String.class);
~~~

If customer or name has no suitable value, the template uses Guest according to the rules of the Elvis operator. The fixed text is still concatenated normally.

With multiple object levels:

~~~text
Delivery city: #{customer?.address?.city ?: 'Unknown'}
~~~

Place the null-safe operator at each step that can be null. Do not assume a single `?.` at the beginning of the path protects every subsequent property.

If you need to distinguish a null object from an empty string, choose an appropriate default expression. Elvis in SpEL substitutes for both null and empty strings; if you only want to replace null, use an explicit `== null` condition.

## 8. Dynamic Results Can Be Multiple Data Types

The dynamic part is not required to return a String. It can return a number, Boolean, enum, or object. The result of the template is combined into a single string:

~~~java
Expression template = parser.parseExpression(
        "Quantity: #{quantity}, active: #{enabled}, level: #{level}",
        new TemplateParserContext());

String summary = template.getValue(product, String.class);
~~~

The values of quantity, enabled, and level are represented in the resulting string. For custom objects, the representation depends on how the object provides its string form, usually toString.

For stable display content, select specific properties rather than inserting an entire object:

~~~text
Customer: #{customer.name}
Address: #{customer.address.city}
~~~

Do not rely on the default toString of a complex object because the output may not suit the user interface or may change when the class is edited.

## 9. Creating a Template Once and Evaluating Multiple Times

If the template source does not change, you can parse it once and evaluate it with multiple root objects or contexts:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
        "Hello #{customer.name}, order #{code}",
        new TemplateParserContext());

Order firstOrder = TestData.order("Lan", "ORD-1001");
Order secondOrder = TestData.order("Minh", "ORD-1002");

String firstMessage =
        template.getValue(firstOrder, String.class);

String secondMessage =
        template.getValue(secondOrder, String.class);
~~~

The same Expression is reused; only the root object data changes. This avoids re-parsing the source each time a message is generated.

If the template needs variables, create a context per evaluation or update variables following a clear lifecycle. Avoid sharing a context with mutable variables across concurrent requests if changes could cause cross-request interference.

## 10. Using Templates in Spring's @Value

In a Spring application managed by BeanFactory, Spring supports SpEL templates in integration points such as the @Value annotation. You can mix fixed text with dynamic expressions:

~~~java
@Component
public class ApplicationDescription {

    @Value("Service: #{T(java.lang.Math).max(2, 5)}")
    private String description;

    public String getDescription() {
        return description;
    }
}
~~~

Spring processes the template part and evaluates the expression in the context provided by BeanFactory. Expressions can access objects and capabilities allowed by the configured expression resolver.

Another example using a system property:

~~~java
@Component
public class GreetingConfiguration {

    @Value("Running as #{systemProperties['user.name']}")
    private String greeting;

    public String getGreeting() {
        return greeting;
    }
}
~~~

With @Value, Spring already provides the expression template processing mechanism. When creating a SpelExpressionParser yourself in Java, pass TemplateParserContext as in the previous examples.

## 11. Using Custom Delimiters

TemplateParserContext allows specifying a different delimiter pair if the application needs a custom template syntax:

~~~java
ParserContext context = new TemplateParserContext("%{", "}");

Expression template = parser.parseExpression(
        "Order %{code} | Total %{total}",
        context);

String result = template.getValue(order, String.class);
~~~

In this example, the dynamic part is placed between `%{` and `}` instead of `#{` and `}`.

Custom delimiters are useful when template strings frequently contain characters overlapping with the default delimiters or when a configuration system already specifies another syntax. Use a consistent delimiter pair within the same template type and document the convention for maintainers.

Changing delimiters only changes how the parser recognizes template segments. The content inside must still be a valid SpEL expression.

## 12. Template Expressions vs. Standard SpEL String Concatenation

There are two common ways to construct a string with dynamic parts.

Template expression:

~~~java
Expression template = parser.parseExpression(
        "Order #{code} for #{customer.name}",
        new TemplateParserContext());
~~~

Concatenation using a standard SpEL expression:

~~~java
Expression expression = parser.parseExpression(
        "'Order ' + code + ' for ' + customer.name");
~~~

Templates fit well when fixed text makes up most of the content and the dynamic segments should remain clearly visible. Concatenation fits well when the entire result is a computed expression or when string operations are part of the logic.

You do not need to force every case into a single style. Choose the approach that makes the boundary between fixed content and dynamic data clearest.

## 13. Avoid Concatenating Untrusted Data into Template Source

Do not take user-supplied data and concatenate it directly into the template source. The data might contain delimiters, quotes, or content that alters SpEL syntax.

Keep the template fixed and pass data via variables:

~~~java
Expression template = parser.parseExpression(
        "Hello #{#displayName}!",
        new TemplateParserContext());

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("displayName", userSuppliedName);

String greeting = template.getValue(context, String.class);
~~~

Here userSuppliedName is only a variable value. It is not re-parsed as part of the expression source.

This prevents display data from accidentally becoming SpEL syntax. However, if the template source itself is provided by an untrusted user, the template can still perform actions allowed by EvaluationContext. Restrict template sources and context capabilities strictly as needed.

## 14. Common Mistakes

**Forgetting to pass TemplateParserContext**

When parsing a string with fixed text and `#{...}` delimiters, you must provide a template ParserContext. Otherwise, the parser does not process dynamic segments according to template rules.

**Confusing fixed text with expressions**

Content outside the delimiters is preserved as-is. Only content inside the delimiter pair is parsed as SpEL.

**Missing closing delimiter or mistyped delimiters**

A template missing a `}` or using inconsistent delimiters may throw a parse error. Check the configured prefix/suffix pair.

**Using the wrong data source**

Root object properties are written directly like `customer.name`. Variables in EvaluationContext must have the `#` prefix, for example `#displayName`.

**Assuming every dynamic value is already a String**

The dynamic part can return a number, Boolean, or object. When combined into the template, the value is represented as a string; select specific properties for stable output.

**Not handling null in nested properties**

Use `?.` at steps that can be null and provide defaults with Elvis or explicit conditions when needed.

**Concatenating input data into template source**

Pass data through variables or the root object. Do not let user content become part of SpEL syntax.

**Evaluating untrusted templates with an overly broad context**

SpEL can access properties and methods according to context configuration. Restrict the template source and evaluation context permissions when data is not completely controlled by the application.

## 15. Testing Template Expressions

You can test a template like any normal Expression. Tests should verify fixed text, dynamic values, and cases where data changes:

~~~java
@Test
void combinesLiteralTextAndDynamicProperties() {
    Order order = TestData.order("Lan", "ORD-1001");

    Expression template = new SpelExpressionParser().parseExpression(
            "Hello #{customer.name}, order #{code}!",
            new TemplateParserContext());

    String result = template.getValue(order, String.class);

    assertEquals("Hello Lan, order ORD-1001!", result);
}
~~~

Test with multiple root objects to verify the same template can be reused:

~~~java
@Test
void reusesTemplateWithDifferentRootObjects() {
    Expression template = new SpelExpressionParser().parseExpression(
            "Order #{code} for #{customer.name}",
            new TemplateParserContext());

    assertEquals(
            "Order ORD-1001 for Lan",
            template.getValue(TestData.order("Lan", "ORD-1001"), String.class));

    assertEquals(
            "Order ORD-1002 for Minh",
            template.getValue(TestData.order("Minh", "ORD-1002"), String.class));
}
~~~

If the template uses variables, create a StandardEvaluationContext and test both variable values and root object properties. If there are nullable properties, check default outcomes. If the template source comes from external configuration, test parse errors separately from evaluation errors to determine whether an issue lies in delimiters/syntax or runtime data.

## 16. Key Takeaways

- Template expressions mix fixed text with dynamic SpEL expressions.
- With default delimiters, dynamic parts reside inside `#{...}`.
- When parsing templates manually, use `new TemplateParserContext()`.
- Text outside delimiters is preserved; content inside is evaluated as SpEL.
- Multiple dynamic segments can be placed in the same template.
- Root object properties use direct names; variables use the `#` prefix.
- Dynamic parts can use properties, methods, operations, conditions, and null-safe navigation.
- Template output is a string; prefer specific properties over relying on an object's default string representation.
- Custom delimiters can be used with TemplateParserContext(prefix, suffix).
- Spring supports template expressions in integration points like @Value; manually created parsers require an explicit ParserContext.
- Pass input data via the root object or variables, and never concatenate untrusted data into the template source.
- Parse once and evaluate multiple times when the template source does not change.
