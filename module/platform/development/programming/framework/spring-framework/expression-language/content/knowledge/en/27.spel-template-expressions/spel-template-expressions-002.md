# ParserContext and Template Delimiters in Spring Expression Language

Spring Expression Language (SpEL) can evaluate a standalone expression, yet applications also often need to construct strings consisting of fixed text interspersed with dynamic values. For example, a notification might contain a customer's name and the order's total amount:

~~~text
Hello Linh, your order has a total amount of 750000.
~~~

To handle this kind of string, SpEL supports **template expressions**. A template contains ordinary text and SpEL segments placed between delimiters. **ParserContext** tells the parser whether the input is a template and which delimiter pair marks the expression parts.

ParserContext belongs to the parsing phase. It specifies how to separate fixed text from SpEL segments; the data used to evaluate expressions is still provided by EvaluationContext.

## 1. What Is a Template Expression?

A template expression is a string consisting of two types of content:

- **Fixed text:** preserved as-is in the result.
- **SpEL segments:** located between the prefix and suffix, parsed and then evaluated.

With default delimiters, a template looks like:

~~~text
Hello #{'Linh'}, today is #{T(java.time.LocalDate).now()}.
~~~

Where:

- The part before the first expression segment is fixed text.
- The content between #{ and } is a SpEL expression.
- The text after the expression continues to be preserved.
- The value of each expression is inserted at the corresponding position.

When evaluated, the result is a complete string. Templates are useful for messages, display labels, configuration content, and strings requiring data interpolation.

## 2. Why Is ParserContext Needed?

If you only need to evaluate a standalone SpEL expression, you can call the parseExpression overload that takes only the string:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("10 + 5");

Integer result = expression.getValue(Integer.class);
~~~

The result is 15. The entire string 10 + 5 is interpreted as SpEL syntax.

However, if the input is a sentence containing free-form text:

~~~text
Order total amount: #{#total}
~~~

the parser needs to know which part is text and which part is an expression. Without passing a ParserContext, the parser does not automatically infer that a string containing delimiters is a template.

You can specify the parsing mode explicitly using the overload accepting ParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Order total amount: #{#total}",
    new TemplateParserContext()
);
~~~

ParserContext tells the parser which rules to use to split the template. It does not supply values for the total variable, nor does it evaluate expressions in place of EvaluationContext.

## 3. What Interface Is ParserContext?

ParserContext belongs to the org.springframework.expression package. This interface provides three pieces of information to ExpressionParser:

- isTemplate(): indicates whether the input should be processed as a template.
- getExpressionPrefix(): returns the string that opens an expression segment.
- getExpressionSuffix(): returns the string that closes an expression segment.

Its responsibilities can be described as:

| Method | Responsibility |
|---|---|
| isTemplate() | Chooses template parsing mode or normal expression mode |
| getExpressionPrefix() | Identifies the start of a SpEL segment |
| getExpressionSuffix() | Identifies the end of a SpEL segment |

ParserContext does not hold a root object, variables, bean resolver, or type converter. Those components belong to EvaluationContext and are used when the expression is evaluated.

## 4. TemplateParserContext and Default Delimiters

Spring provides the TemplateParserContext class in the org.springframework.expression.common package. This is a built-in implementation of ParserContext for template expressions.

The default constructor uses:

- Prefix: #{
- Suffix: }

Example:

~~~java
ParserContext parserContext =
    new TemplateParserContext();

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Hello #{'Linh'}!",
    parserContext
);

String result = template.getValue(String.class);
~~~

Result:

~~~text
Hello Linh!
~~~

You can use the default constructor when the #{ ... } syntax fits the application's template format.

Within a template, each expression segment is parsed according to standard SpEL syntax. Parts outside the delimiters are kept as literal text.

## 5. Customizing Prefix and Suffix

If the default delimiters conflict with another text format, you can specify a custom delimiter pair via the TemplateParserContext constructor:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Hello [['Linh']], total amount is [[100 + 50]].",
    parserContext
);

String result = template.getValue(String.class);
~~~

Result:

~~~text
Hello Linh, total amount is 150.
~~~

In the example:

- The prefix is [[.
- The suffix is ]].
- The segment [['Linh']] contains a string literal expression.
- The segment [[100 + 50]] contains a SpEL arithmetic operation.
- The rest is fixed text.

Changing delimiters does not alter the syntax inside the expression segments. Content between the prefix and suffix still follows SpEL syntax.

## 6. How a Template Is Split and Evaluated

Suppose we have the template:

~~~text
Order #{#orderNumber} for #{#customerName} has total #{#total}.
~~~

The parser uses the delimiters to split the content into segments:

| Order | Content | Processing |
|---:|---|---|
| 1 | Order | Keep text as-is |
| 2 | #orderNumber | Parse and evaluate with SpEL |
| 3 | for | Keep text as-is |
| 4 | #customerName | Parse and evaluate with SpEL |
| 5 | has total | Keep text as-is |
| 6 | #total | Parse and evaluate with SpEL |
| 7 | . | Keep text as-is |

When getValue is called, the expression segments are evaluated within the same EvaluationContext environment, and the results are concatenated with the literal text segments in exact order.

You can visualize it as:

~~~text
Template string
      |
      v
ParserContext provides prefix/suffix
      |
      v
ExpressionParser splits segments
      |
      +--> Literal text
      |
      +--> SpEL expression
                 |
                 v
          EvaluationContext
                 |
                 v
          Runtime value
      |
      v
Concatenate segments in order
      |
      v
Result string
~~~

ParserContext determines the boundaries of expression segments. EvaluationContext determines how those segments read data and perform operations.

## 7. Combining Templates with EvaluationContext

Template expressions often need data from Java. Register values in EvaluationContext and reference them using the #name variable syntax.

Example:

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

ParserContext parserContext =
    new TemplateParserContext();

Expression template = parser.parseExpression(
    "Hello #{#customerName}, order #{#orderNumber} has total #{#total} VND.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");
context.setVariable("orderNumber", "ORD-100");
context.setVariable("total", new BigDecimal("750000"));

String message =
    template.getValue(context, String.class);

System.out.println(message);
~~~

Result:

~~~text
Hello Linh, order ORD-100 has total 750000 VND.
~~~

In the example:

- ParserContext defines #{ and } as delimiters.
- The parser splits the template into text and three expression segments.
- EvaluationContext provides the variables customerName, orderNumber, and total.
- getValue evaluates each SpEL segment and concatenates the results into a String.

If a variable has not been registered or has a null value, the corresponding expression segment may return null or throw an error depending on the operation performed on that value.

## 8. Root Objects Can Also Be Used in Templates

Templates are not required to reference only variables. SpEL segments can read properties on the root object just like regular expressions.

Suppose there is a Customer class:

~~~java
public class Customer {
    private final String name;
    private final String membershipLevel;

    public Customer(String name, String membershipLevel) {
        this.name = name;
        this.membershipLevel = membershipLevel;
    }

    public String getName() {
        return name;
    }

    public String getMembershipLevel() {
        return membershipLevel;
    }
}
~~~

Evaluating a template with a root object:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Customer #{name} has tier #{membershipLevel}.",
    new TemplateParserContext()
);

String message =
    template.getValue(context, String.class);
~~~

Result:

~~~text
Customer Linh has tier GOLD.
~~~

The names name and membershipLevel are read on the root object. If you want to specify the source explicitly, you can write #root.name and #root.membershipLevel.

## 9. Templates with Multiple Expressions and Nested Expressions

A template can contain multiple independent SpEL segments:

~~~text
#{#firstName} #{#lastName}: #{#price * #quantity}
~~~

Each segment is parsed and evaluated according to SpEL syntax. Inside a segment, parentheses can be used to group expressions:

~~~text
Amount after discount: #{(#price * #quantity) * (1 - #discountRate)}
~~~

The parentheses here belong to expression syntax inside the delimiters. The prefix and suffix only determine the boundaries of the SpEL segment within the template.

If an expression segment has invalid syntax, the error occurs during parsing. If the expression parses but a variable or property is invalid at runtime, the error occurs during evaluation.

## 10. Using Templates with Operators, Properties, and Method Calls

Content inside delimiters can use standard SpEL capabilities.

Example:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable("quantity", 2);

ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Product: #{name.toUpperCase()}, quantity: #{#quantity}, subtotal: #{price * #quantity}.",
    new TemplateParserContext()
);

String message =
    template.getValue(context, String.class);
~~~

Result:

~~~text
Product: KEYBOARD, quantity: 2, subtotal: 1500000.
~~~

The expression segments respectively:

- Read the name property and call toUpperCase().
- Read the quantity variable.
- Read the price property and multiply by quantity.

Templates only add a text-concatenation layer. They do not restrict inner expressions to a different set of operators.

## 11. TemplateParserContext and Custom ParserContext

If the delimiter pair is not flexible enough, an application can implement ParserContext itself.

A minimal implementation can provide:

~~~java
public class CustomParserContext implements ParserContext {

    @Override
    public boolean isTemplate() {
        return true;
    }

    @Override
    public String getExpressionPrefix() {
        return "[[";
    }

    @Override
    public String getExpressionSuffix() {
        return "]]";
    }
}
~~~

Then use it:

~~~java
Expression template = parser.parseExpression(
    "Value: [[#value]]",
    new CustomParserContext()
);
~~~

In practice, if you only need to change the prefix and suffix, TemplateParserContext already meets the requirement and reduces custom code.

A custom ParserContext is appropriate when the application needs a delimiter policy encapsulated in its own class or needs to implement a specific template convention.

## 12. Choosing Suitable Delimiters

Delimiters are part of the template format, so you should choose character pairs that are easy to recognize and rarely appear in ordinary text.

Some notes:

- Use the same prefix and suffix across the entire template creation and evaluation system.
- Avoid choosing delimiters that frequently appear in literal content.
- Keep opening and closing delimiters easy to distinguish.
- When changing delimiters, update both the template data and the ParserContext used for parsing.
- Verify that the template has enough closing delimiters for every expression segment.
- Do not confuse template delimiters with variable, property, or operator syntax inside SpEL.

For example, prefix #{ and suffix } fit common SpEL templates. If content frequently contains similar syntax, the pair [[ and ]] may be easier to distinguish.

Delimiters are not a security mechanism. Changing delimiters does not restrict which methods, beans, or types an expression can access.

## 13. Common Errors When Parsing Templates

### Missing Suffix

If a template opens an expression segment without a corresponding closing delimiter, the parser cannot determine the boundary of that segment and may throw a parsing error.

Incomplete example:

~~~text
Total amount: #{#price * #quantity
~~~

Add the proper suffix matching ParserContext:

~~~text
Total amount: #{#price * #quantity}
~~~

### Using the Wrong ParserContext

If a template uses [[ and ]] but the parser is configured with the default TemplateParserContext, the parser will look for #{ and } instead of the actual delimiters.

Ensure the parser receives the right context:

~~~java
new TemplateParserContext("[[", "]]")
~~~

### Invalid Inner SpEL Syntax

The delimiters may be correct while the expression content still has invalid syntax:

~~~text
Total amount: #{#price * }
~~~

The error lies in the inner expression, not in the delimiters themselves.

### Evaluation Errors After Parsing

A template may parse successfully yet encounter issues when getValue is called, such as a missing variable, nonexistent property, unsuitable method, or failed type conversion.

When debugging, determine whether the error occurs in parseExpression or getValue before inspecting the corresponding content.

## 14. Distinguishing ParserContext and EvaluationContext

These two contexts have similar names but serve two different phases:

| Component | Phase | Responsibility |
|---|---|---|
| ParserContext | Parsing | Indicates the input is a template and defines prefix/suffix |
| EvaluationContext | Evaluation | Provides root object, variables, resolvers, accessors, and converters |
| Expression | After parsing | Represents the parsed expression or template |
| getValue | Evaluation | Evaluates the expression and returns the result |

Example:

~~~java
ParserContext parserContext =
    new TemplateParserContext();

StandardEvaluationContext evaluationContext =
    new StandardEvaluationContext();

evaluationContext.setVariable("name", "Linh");

Expression template = parser.parseExpression(
    "Hello #{#name}!",
    parserContext
);

String result =
    template.getValue(evaluationContext, String.class);
~~~

ParserContext does not know that name is Linh. EvaluationContext does not decide the template delimiters. Each component supplies the right information for its phase.

## 15. Reusing Parsed Templates

If a template is used multiple times, you can parse it once and reuse the Expression with different EvaluationContexts or variable values.

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Hello #{#customerName}, order code #{#orderNumber}.",
    new TemplateParserContext()
);

StandardEvaluationContext firstContext =
    new StandardEvaluationContext();

firstContext.setVariable("customerName", "Linh");
firstContext.setVariable("orderNumber", "ORD-100");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();

secondContext.setVariable("customerName", "Minh");
secondContext.setVariable("orderNumber", "ORD-101");

String firstMessage =
    template.getValue(firstContext, String.class);

String secondMessage =
    template.getValue(secondContext, String.class);
~~~

Result:

~~~text
Hello Linh, order code ORD-100.
Hello Minh, order code ORD-101.
~~~

Expression retains the parsed template structure. Runtime data comes from the context of each evaluation.

If using a context with mutable variables, manage the context lifecycle appropriately to avoid one update affecting another evaluation.

## 16. Template Expressions in Spring Configuration

Template expressions often appear in the @Value annotation:

~~~java
@Component
public class GreetingSettings {

    @Value("#{systemProperties['user.language']}")
    private String language;

    public String getLanguage() {
        return language;
    }
}
~~~

In a Spring environment, the expression mechanism integrated with the container processes expressions in annotations. The #{...} part marks the SpEL segment to evaluate.

Two cases should be distinguished:

- A template string actively parsed by the application using ExpressionParser needs ParserContext passed in.
- Expressions in @Value are processed by Spring's built-in integration mechanism according to annotation conventions.

Do not assume every string containing #{...} is automatically parsed as a template when calling ExpressionParser directly.

## 17. Common Misconceptions

**Misconception 1: ParserContext supplies variables for expressions.**  
ParserContext specifies template mode and delimiters. Variables, root object, and resolvers belong to EvaluationContext.

**Misconception 2: Default TemplateParserContext uses any delimiters.**  
The default constructor uses prefix #{ and suffix }. To use another pair, pass both strings explicitly to the constructor.

**Misconception 3: Changing delimiters alters the inner SpEL syntax.**  
Delimiters only mark boundaries. Content inside still uses standard SpEL syntax.

**Misconception 4: Without passing ParserContext, the parser automatically detects templates.**  
The parseExpression overload taking only a string treats the entire input as a regular expression.

**Misconception 5: Successful parsing means evaluation is guaranteed to succeed.**  
Variables, properties, methods, and data types are only processed against the runtime environment during evaluation.

**Misconception 6: Custom delimiters restrict access privileges.**  
Delimiters are not a security mechanism. Access privileges depend on EvaluationContext and the configured resolvers/accessors.

## 18. Key Takeaways

- Template expressions combine literal text with SpEL segments marked by delimiters.
- ParserContext tells the parser whether the input is a template and defines prefix/suffix.
- TemplateParserContext defaults to prefix #{ and suffix }.
- Delimiters can be customized using the TemplateParserContext(prefix, suffix) constructor.
- The parseExpression(expressionString, parserContext) overload uses ParserContext to parse templates.
- Content inside delimiters still follows standard SpEL syntax.
- EvaluationContext provides the root object, variables, and necessary mechanisms during evaluation.
- A template can contain multiple expression segments and results are concatenated in order with fixed text.
- Parse errors differ from evaluation errors; identify the right phase when debugging.
- Delimiters should be consistent and easy to distinguish, though they do not create a security boundary.

When building template expressions, define the fixed text, choose a clear delimiter pair, pass an appropriate ParserContext during parseExpression, and supply runtime data through EvaluationContext when calling getValue.
