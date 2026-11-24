# ParserContext for Template Expressions in Spring Expression Language

Spring Expression Language (SpEL) is often used to evaluate standalone expressions, such as total >= #minimum. However, in many situations an application needs to produce a text string containing both fixed parts and dynamic values. For example: “Hello Linh, your order has a total amount of 125000”.

To handle this type of input, SpEL supports **template expressions**. A template contains ordinary text and SpEL segments placed between delimiter pairs. **ParserContext** tells the parser how to recognize the expression segments inside the template.

ParserContext belongs to the parsing stage. It defines how to read the input string, while EvaluationContext provides the data and environment for evaluating the expressions after parsing.

## 1. What is ParserContext?

ParserContext is an interface in Spring Expression that provides three pieces of information to ExpressionParser:

- **isTemplate():** indicates whether the input string is a template.
- **getExpressionPrefix():** returns the character sequence that starts an expression segment.
- **getExpressionSuffix():** returns the character sequence that ends an expression segment.

ParserContext helps the parser distinguish ordinary text from parts that need to be parsed as SpEL expressions.

Spring provides the TemplateParserContext class to implement common template parsing. The default constructor uses:

- Prefix: `#{`
- Suffix: `}`

For example, in the string:

~~~text
Hello #{'Linh'}!
~~~

the “Hello ” part and the exclamation mark are fixed text. The #{'Linh'} segment is a SpEL expression and is evaluated to the string Linh.

## 2. Why is ParserContext needed?

If the application only needs to evaluate a standalone expression, the parser can accept the expression string directly:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("100 + 25");

Integer result = expression.getValue(Integer.class);
~~~

In this case, the entire string 100 + 25 is SpEL syntax. The result is the number 125.

But if the input is a complete sentence with text and expressions interspersed:

~~~text
Hello #{'Linh'}, you have #{3 + 2} new notifications.
~~~

the parser needs to know which parts are text to keep as-is and which parts are expressions to evaluate. This is why the application passes an additional ParserContext into the parseExpression overload:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Hello #{'Linh'}, you have #{3 + 2} new notifications.",
    parserContext
);

String message = expression.getValue(String.class);
~~~

Result:

~~~text
Hello Linh, you have 5 new notifications.
~~~

ParserContext defines the template splitting rules. It does not evaluate expressions itself, nor does it supply values for variables referenced inside the template.

## 3. How a template expression is parsed

A template expression can consist of multiple consecutive segments:

1. Fixed text before the first expression segment.
2. An expression segment between the prefix and suffix.
3. Fixed text between two expression segments.
4. Subsequent expression segments.
5. Fixed text at the end of the string.

Example:

~~~text
Order #{#orderId} of #{#customerName} has a total amount of #{#amount}.
~~~

The string can be divided into parts:

| Part | Content | How it is handled |
|---|---|---|
| Text 1 | Order | Kept as-is |
| Expression 1 | #orderId | Parsed and evaluated by SpEL |
| Text 2 | of | Kept as-is |
| Expression 2 | #customerName | Parsed and evaluated by SpEL |
| Text 3 | has a total amount of | Kept as-is |
| Expression 3 | #amount | Parsed and evaluated by SpEL |
| Text 4 | . | Kept as-is |

During parsing, the parser identifies the prefix and suffix, separates the text segments from the expression segments, and parses SpEL syntax for each expression segment. The returned Expression object can combine multiple parts so that upon evaluation, the dynamic values are concatenated with the fixed text into a complete string.

The key distinction is that text outside the delimiters is not treated as a SpEL expression. Only content inside an expression segment is processed by the parser according to SpEL syntax.

## 4. Using TemplateParserContext with default delimiters

This is the most common usage:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParserContext;
import org.springframework.expression.common.TemplateParserContext;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public class TemplateExample {
    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();

        ParserContext parserContext = new TemplateParserContext();

        Expression expression = parser.parseExpression(
            "Hello #{'Linh'}!",
            parserContext
        );

        String result = expression.getValue(String.class);

        System.out.println(result);
    }
}
~~~

Result:

~~~text
Hello Linh!
~~~

Each component has its own role:

- SpelExpressionParser receives the input string and performs parsing.
- TemplateParserContext indicates that this is a template and uses the #{ ... } delimiter pair.
- parseExpression creates an Expression from the template.
- getValue requests evaluation of the SpEL segments and returns the concatenated string.

You can use the default constructor of TemplateParserContext when standard SpEL template syntax is acceptable.

## 5. Customizing the prefix and suffix

Applications do not always want to use #{ and }. TemplateParserContext allows specifying a different delimiter pair using the two-string constructor:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression expression = parser.parseExpression(
    "Hello [[ 'Linh' ]]!",
    parserContext
);

String result = expression.getValue(String.class);
~~~

In this example:

- The prefix is [[.
- The suffix is ]].
- The “Hello ” text and the ! mark are kept as-is.
- The content between [[ and ]] is parsed as a SpEL expression.

The result is still:

~~~text
Hello Linh!
~~~

Custom delimiter pairs are useful when the default syntax conflicts with text formats or another template language in the application.

Choose a prefix and suffix that are easy to recognize and rarely appear in ordinary text. If multiple systems process the same string, agree on the delimiter pair so one component does not misinterpret another component's content.

## 6. Expressions inside a template still use SpEL syntax

ParserContext only defines the boundaries of expression segments. Content inside those segments still follows standard SpEL syntax.

Therefore, a template can contain:

| SpEL feature | Example in template | Meaning |
|---|---|---|
| Variable | `#{#customerName}` | Retrieve variable from EvaluationContext |
| Root property | `#{name}` | Read property on the current object |
| Operator | `#{#amount >= #minimum}` | Perform comparison |
| Calculation | `#{#price * #quantity}` | Compute value |
| Method call | `#{#customerName.toUpperCase()}` | Call method on a value |
| Collection access | `#{#items.size()}` | Retrieve information from a collection |

These capabilities remain governed by EvaluationContext. If the context lacks the referenced variable or does not support the required operation, evaluation may raise an error even though the template was parsed successfully.

## 7. Combining ParserContext with EvaluationContext

ParserContext and EvaluationContext are often used together, yet they solve two different problems:

| Component | When used | Responsibility |
|---|---|---|
| ParserContext | When calling parseExpression | Tells the parser whether the string is a template and what the expression delimiters are |
| EvaluationContext | When calling getValue | Provides the root object, variables, accessors, resolvers, and conversion mechanism |
| Expression | After successful parsing | Represents the parsed expression or template |
| Evaluation Result | After evaluation completes | Final value of the evaluation |

Complete example:

~~~java
import java.math.BigDecimal;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.ParserContext;
import org.springframework.expression.spel.SpelEvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.common.TemplateParserContext;

public class OrderMessageExample {
    public static void main(String[] args) {
        // 1. Initialize parser and ParserContext.
        ExpressionParser parser = new SpelExpressionParser();
        ParserContext parserContext = new TemplateParserContext();

        // 2. Parse the template.
        Expression template = parser.parseExpression(
            "Order of #{#customerName} has a total amount of #{#amount} VND.",
            parserContext
        );

        // 3. Supply data at evaluation time.
        StandardEvaluationContext evaluationContext =
            new StandardEvaluationContext();

        evaluationContext.setVariable("customerName", "Linh");
        evaluationContext.setVariable(
            "amount",
            new BigDecimal("125000")
        );

        // 4. Evaluate the template and get the string.
        String message =
            template.getValue(evaluationContext, String.class);

        System.out.println(message);
    }
}
~~~

Result:

~~~text
Order of Linh has a total amount of 125000 VND.
~~~

In this example, ParserContext does not know that customerName is Linh or amount is 125000. Those values are only provided in StandardEvaluationContext. When getValue is called, the SpEL segments are evaluated using the data in the context, and the results are concatenated with the fixed text.

## 8. Using a template with a root object

Besides variables, a template can reference properties on the root object. For example, suppose there is a Customer class with getters getName() and getMembershipLevel():

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

You can create a template as follows:

~~~java
Customer customer = new Customer("Linh", "GOLD");

ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Customer #{name} has tier #{membershipLevel}.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

String message = template.getValue(context, String.class);
~~~

Result:

~~~text
Customer Linh has tier GOLD.
~~~

Here, name and membershipLevel are read from the root object customer. If you want to refer to the root object explicitly, you can use #root.name and #root.membershipLevel.

## 9. Multiple expression segments in the same template

A template can have multiple SpEL segments. Each segment is evaluated in the same evaluation environment of the getValue call, unless the expression itself changes the current object in a construct such as selection or projection.

Example:

~~~java
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Code: #{#code}; quantity: #{#quantity}; total price: #{#price * #quantity}",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("code", "SP-100");
context.setVariable("quantity", 3);
context.setVariable("price", 25000);

String message = template.getValue(context, String.class);
~~~

Result:

~~~text
Code: SP-100; quantity: 3; total price: 75000
~~~

The expression segments can share registered variables and the root object. Fixed text is preserved, while dynamic segments are replaced by their corresponding evaluated values.

## 10. What happens if ParserContext is not passed?

If you call the single-parameter overload:

~~~java
Expression expression =
    parser.parseExpression("Hello #{'Linh'}!");
~~~

the parser treats the entire string as a regular SpEL expression. It does not automatically understand that “Hello ” is template text and #{'Linh'} is a segment to interpolate.

When the input contains both free text and expressions enclosed by delimiters, pass ParserContext:

~~~java
Expression expression = parser.parseExpression(
    "Hello #{'Linh'}!",
    new TemplateParserContext()
);
~~~

This is an important difference between parsing a single expression and parsing a template.

## 11. Errors in template expressions

Errors can occur at two stages.

**Parsing errors:**

- Content inside an expression segment has invalid SpEL syntax.
- Template delimiter structure is invalid.
- A sub-expression has incomplete operators or structure.

Parsing errors occur when calling parseExpression.

**Evaluation errors:**

- A referenced variable is not present in the context.
- The root object or property is incompatible.
- A called method does not exist or cannot be invoked with the given arguments.
- The context does not support the operation requested by the expression.
- Type conversion cannot be performed.

Evaluation errors occur when calling getValue.

When handling errors, determine whether the error occurred before or after the Expression was successfully created. Then inspect the corresponding part: the template string and delimiters for parsing; data, context, and operations for evaluation.

## 12. Notes for application usage

### Reusing Expression

If the same template is used many times, the application can parse it once and reuse the Expression. On each execution, supply a context matching the data for that run.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Hello #{#name}!",
    new TemplateParserContext()
);

StandardEvaluationContext firstContext =
    new StandardEvaluationContext();
firstContext.setVariable("name", "Linh");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();
secondContext.setVariable("name", "Minh");

String firstMessage =
    template.getValue(firstContext, String.class);

String secondMessage =
    template.getValue(secondContext, String.class);
~~~

Result:

~~~text
Hello Linh!
Hello Minh!
~~~

### Choosing an appropriate context

Templates do not restrict expressions inside them to reading variables only. SpEL segments can call methods or perform other operations that the context permits. If a template comes from an untrusted source, control which features are allowed and which data can be accessed. SimpleEvaluationContext may be suitable for cases where evaluation capabilities need to be restricted.

ParserContext only specifies how to parse the template. It is not a security mechanism and does not itself limit the privileges that a SpEL segment can use.

### Choosing clear delimiters

Custom delimiters should be easily distinguishable from surrounding text. If a system has multiple template processors, standardize the prefix and suffix convention so a single string is not interpreted in multiple ways.

## 13. Key takeaways

- ParserContext is an interface describing the parsing rules of the input.
- TemplateParserContext is a built-in implementation for template expressions, using prefix #{ and suffix } by default.
- parseExpression(expressionString, parserContext) tells the parser how to separate fixed text and SpEL segments.
- Text outside delimiters is kept as literal parts; content inside is parsed according to SpEL syntax.
- Prefix and suffix can be changed via the TemplateParserContext constructor.
- ParserContext serves parsing; EvaluationContext provides data and the environment at evaluation time.
- An Expression can be reused with multiple EvaluationContext instances to produce different results.
- Successful template parsing does not guarantee evaluation will succeed: variables, root object, methods, and data types must still match.

When building a template expression, clearly identify the fixed text, the dynamic expression parts, and the delimiter pair, then supply the appropriate context when calling getValue. In this way, ParserContext properly fulfills its role of connecting template strings with SpEL syntax.
