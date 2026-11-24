# Do Not Confuse SpEL Templates with Thymeleaf or JSP EL

## 1. Why Are Expression Types Easy to Confuse?

Spring Expression Language (SpEL), Thymeleaf, and JSP Expression Language (JSP EL) all use expression syntax enclosed in delimiters. At a glance, some syntaxes look identical, especially ${...} and #{...}.

However, the exact same pair of characters can carry different meanings depending on the engine:

- SpEL templates use #{...} to mark a SpEL segment inside fixed text.
- Thymeleaf uses #{...} for message expressions, commonly for i18n; ${...} is a variable expression.
- JSP EL uses ${...} for immediate evaluation and #{...} for deferred evaluation in places that support deferred expressions.

You cannot determine the engine merely by looking at the brackets. You need to know which component processes the string, which syntax is configured, and when the expression is evaluated.

## 2. Regular SpEL Expressions Do Not Need Delimiters

When using the ExpressionParser API, if you call parseExpression(String) without passing a ParserContext, the entire string is treated as a SpEL expression.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#customer.name");

    String name =
        expression.getValue(context, String.class);

In this example, #customer.name is a complete SpEL expression. There is no need to wrap it in #{...}.

If you want to build a string containing both fixed text and an expression result, use template parsing:

    Expression template = parser.parseExpression(
        "Hello #{#customer.name}!",
        new TemplateParserContext()
    );

    String message =
        template.getValue(context, String.class);

If customer.name is Lan, the result is:

    Hello Lan!

Here:

- "Hello " is fixed text.
- #{#customer.name} is the evaluated SpEL segment.
- "!" is fixed text.

TemplateParserContext defaults to prefix #{ and suffix }. The parser concatenates text segments with the result of each expression block when the expression is evaluated.

## 3. ParserContext and TemplateParserContext Belong to the SpEL API

TemplateParserContext is a ParserContext implementation in Spring Expression Language. It tells the parser that the input string is a template and specifies the delimiters used to recognize expression blocks.

Example:

    Expression template = parser.parseExpression(
        "Total amount: #{#order.total}",
        new TemplateParserContext()
    );

You can change delimiters by instantiating TemplateParserContext with custom prefix and suffix:

    ParserContext parserContext =
        new TemplateParserContext("[[", "]]");

    Expression template = parser.parseExpression(
        "Total amount: [[#order.total]]",
        parserContext
    );

In this case, [[ and ]] are application-configured delimiters. SpEL recognizes them as template boundaries only because the parser was passed the corresponding ParserContext.

This differs from a template engine defining its own syntax. Thymeleaf and JSP do not automatically use TemplateParserContext just because content contains #{...}.

Distinguish two calls:

    parser.parseExpression("#order.total")

This is a standalone SpEL expression.

    parser.parseExpression(
        "Total amount: #{#order.total}",
        new TemplateParserContext()
    )

This is a SpEL template consisting of text and an expression block.

## 4. Thymeleaf Has Its Own Standard Expression System

Thymeleaf is a template engine that processes HTML, XML, JavaScript, CSS, or text templates according to its configuration and dialect. Standard Dialect defines several distinct expression types:

| Thymeleaf syntax | Meaning |
| --- | --- |
| ${...} | Variable expression |
| *{...} | Selection expression |
| #{...} | Message expression, commonly used for i18n |
| @{...} | Link/URL expression |
| ~{...} | Fragment expression |

Example:

    <span th:text="${customer.name}">Customer</span>

Thymeleaf retrieves customer from the template context and reads its name property.

Message example:

    <h1 th:text="#{home.title}">Welcome</h1>

Thymeleaf looks up the message with key home.title from the message source for the current locale.

Link example:

    <a th:href="@{/orders}">Orders</a>

Thymeleaf builds a URL suited to the application's context.

Fragment example:

    <div th:replace="~{fragments/header :: main}"></div>

Thymeleaf fetches the specified fragment and inserts it into the template being processed.

Therefore, in Thymeleaf, #{home.title} typically means a message lookup, not a SpEL expression block embedded in text like with TemplateParserContext.

## 5. ${...} in Thymeleaf Is a Variable Expression

Variable expressions access data in the Thymeleaf context. In Spring MVC applications, data usually comes from model attributes or variables placed into the context.

Example of a controller adding customer to the model:

    model.addAttribute("customer", customer);

Template:

    <span th:text="${customer.name}">Name</span>

Thymeleaf reads the customer variable and then accesses its name property.

In the default Standard Dialect, expression evaluation uses OGNL. When integrated with Spring, SpringStandard Dialect replaces OGNL with Spring Expression Language for evaluating variable and selection expressions.

That means the variable expression syntax still belongs to Thymeleaf Standard Expression syntax, while the engine performing evaluation may be OGNL or SpEL depending on the dialect in use.

Do not assume every Thymeleaf template uses SpEL. Determine whether the application uses Standard Dialect or SpringStandard Dialect.

## 6. *{...} in Thymeleaf Is a Selection Expression

Selection expressions are similar to variable expressions, except they are evaluated on an object pre-selected with th:object.

Example:

    <div th:object="${customer}">
        <span th:text="*{name}">Name</span>
        <span th:text="*{address.city}">City</span>
    </div>

th:object selects customer as the selection target. Inside the block, *{name} reads the name property on the selected object.

Semantically, this is equivalent to accessing customer.name, though selection expressions keep templates shorter when many fields belong to the same object.

This is Thymeleaf syntax. SpEL TemplateParserContext does not define *{...} as a default selection expression.

## 7. #{...} in Thymeleaf Is a Message Expression

In Thymeleaf Standard Dialect, #{...} is used to look up messages by key. It is commonly used for multilingual content.

Example messages.properties file:

    home.title=Welcome to the application
    order.created=Order {0} has been created

Template:

    <h1 th:text="#{home.title}">Welcome</h1>

Parameters can be passed to messages:

    <p th:text="#{order.created(${order.id})}">
        Order created
    </p>

Thymeleaf uses MessageSource or the corresponding message resolution mechanism to find content for the locale.

In SpringStandard Dialect, using Spring EL for variable/selection expressions does not change the meaning of #{...} message expressions. It remains Thymeleaf message syntax.

This is the easiest point to confuse with SpEL templates:

- SpEL TemplateParserContext: #{...} contains a SpEL expression segment.
- Thymeleaf Standard Expression: #{...} is a message key or message expression.

Same delimiters, yet different parser, context, and processing result.

## 8. JSP EL Has ${} and #{} Syntaxes

JSP uses Jakarta Expression Language to access data and execute expressions in JSP pages.

JSP EL has two delimiter forms:

- ${...}: immediate evaluation.
- #{...}: deferred evaluation.

Immediate evaluation runs when JSP processes the page to generate a response. Deferred evaluation lets the technology consuming the expression decide when to evaluate it later, typically tied to tag attributes supporting deferred values or deferred methods.

Immediate expression example:

    <c:out value="${customer.name}" />

JSP EL evaluates customer.name and puts the value into the tag's output.

Deferred expression example in an attribute supporting deferred values:

    <h:inputText value="#{customer.name}" />

This example is common in Jakarta Faces. The component framework can hold the expression to read or write the property at appropriate lifecycle phases.

Not every tag attribute supports deferred expressions. Whether #{...} can be used depends on the attribute type and tag metadata.

## 9. Specific Rules of JSP Template Text

In JSP, expressions can appear in standard/custom action attributes and in template text. However, delimiter rules depend on position.

For ordinary template text, JSP allows ${...} syntax for immediate evaluation. The #{...} syntax is reserved for deferred expressions in attributes that support them; using it directly in template text can cause a translation error.

Template text example:

    <p>Hello ${customer.name}</p>

This is an immediate JSP EL expression in page content.

Example of an attribute on a component supporting deferred expressions:

    <h:inputText value="#{customer.name}" />

Do not copy deferred expression syntax from Jakarta Faces into ordinary JSP template text and expect it to behave like a SpEL template.

JSP EL is Jakarta EE's own language. Even though bean property access syntax looks similar to SpEL, it has its own resolvers, expression types, and lifecycle.

## 10. Comparison Table of the Three Mechanisms

| Criterion | SpEL template | Thymeleaf Standard/SpringStandard | JSP EL |
| --- | --- | --- | --- |
| Processing component | Spring ExpressionParser with ParserContext | Thymeleaf Template Engine and Dialect | JSP engine with Jakarta EL |
| Template/text delimiters | Default #{...} for expression blocks | Standard Expressions depending on purpose | ${...} in template text |
| Meaning of #{...} | SpEL block in template parsing | Message/i18n expression | Deferred expression at supported positions |
| Meaning of ${...} | Not a default delimiter of TemplateParserContext | Variable expression | Immediate EL expression |
| Selection expression | Uses object/root/variables per SpEL | *{...} | Depends on EL syntax and tag/framework |
| URL expression | No built-in default URL expression type | @{...} | Depends on tag or library |
| Fragment expression | No built-in default fragment type | ~{...} | JSP has its own include/action/tag mechanism |
| Evaluation timing | When calling getValue on Expression | When template engine processes template | Per immediate/deferred rules and JSP lifecycle |

This table compares the primary meanings in each environment. Do not treat expressions sharing the same symbols as interchangeable.

## 11. Example of the Same Content Processed Differently

Suppose you want to display a customer's name.

### SpEL template

    Expression template = parser.parseExpression(
        "Hello #{#customer.name}",
        new TemplateParserContext()
    );

    String output =
        template.getValue(context, String.class);

The application explicitly invokes the SpEL parser and supplies an EvaluationContext. #{#customer.name} is an expression block.

### Thymeleaf

    <span th:text="#{home.greeting}">Greeting</span>
    <span th:text="${customer.name}">Name</span>

The first line looks up the home.greeting message. The second line reads the name property from the customer variable.

If using a parameterized message:

    <span th:text="#{home.greeting(${customer.name})}">
        Greeting
    </span>

Thymeleaf resolves the message and passes the customer's name as an argument.

### JSP

    <p>Hello ${customer.name}</p>

JSP EL evaluates customer.name immediately when the page is rendered.

In an attribute supporting deferred evaluation, a framework might use:

    <h:inputText value="#{customer.name}" />

This is a Jakarta EL deferred value expression, not a SpEL template block.

## 12. Distinguishing Spring @Value from Thymeleaf and JSP

In Spring applications, the @Value annotation often uses expressions of the form:

    @Value("#{systemProperties['user.name']}")
    private String userName;

This is a Spring container integration point with SpEL. Spring processes the expression when creating or configuring the bean.

It is not a Thymeleaf message expression, even though both use #{...}.

Similarly, an ordinary Java string:

    String source = "Hello #{#customer.name}";

is not automatically processed by Thymeleaf, JSP, or SpEL. Only a component that actively parses or processes templates interprets the delimiters.

When you see #{...} in source code, determine whether it resides in:

- A Spring annotation such as @Value.
- A SpEL TemplateParserContext call.
- A Thymeleaf attribute such as th:text.
- A JSP tag attribute supporting deferred EL.
- An unprocessed Java string.

Location and engine determine meaning.

## 13. How to Identify the Expression Engine When Debugging

When an expression does not work as expected, identify the processing component before editing syntax.

1. Check the file or API containing the expression: Java code, annotation, Thymeleaf HTML, or JSP.
2. Identify the engine: SpEL parser, Thymeleaf Standard/SpringStandard Dialect, or JSP EL.
3. Identify the context: EvaluationContext, Thymeleaf Context/Model, or JSP ELContext.
4. Check delimiters and allowed positions.
5. Determine evaluation timing: when getValue is called, when the template renders, or per deferred lifecycle.
6. Inspect errors from the right engine rather than troubleshooting the wrong parser.

An expression may be valid in SpEL yet invalid in a Thymeleaf message expression or JSP EL. Likewise, Thymeleaf's @{...} syntax has no default URL expression meaning in SpEL.

## 14. Common Mistakes

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| #{...} is always SpEL | Thymeleaf uses it for messages; JSP EL uses it for deferred evaluation | Identify the engine and location |
| ${...} is always a Spring placeholder | Thymeleaf uses variable expressions; JSP uses immediate EL | Same symbols have multiple semantics |
| SpringStandard Dialect turns #{...} into a SpEL block | #{...} remains a message expression in Thymeleaf | SpringStandard swaps the evaluator for variable/selection, not message syntax |
| JSP EL and SpEL are the same language | They have separate grammars, resolvers, and lifecycles | JSP EL belongs to Jakarta EL; SpEL belongs to Spring |
| TemplateParserContext automatically processes all HTML files | It is only a ParserContext for Spring ExpressionParser | Thymeleaf/JSP require their respective template engines |
| @{...} can be used in SpEL to build URLs | @{...} is Thymeleaf's link expression | Use appropriate URI/URL APIs in Java or the template engine |
| #{...} can be used anywhere in JSP | JSP restricts deferred syntax to supporting tag attributes | Ordinary template text uses ${...} |

## 15. Escaping and Displaying Content Safely

Delimiters affect not only expression evaluation but also how content is output to HTML.

In Thymeleaf, th:text processes expressions and outputs text escaped according to HTML rules. th:utext outputs unescaped content, so only use it when HTML content is trusted or properly sanitized.

In JSP, JSTL c:out supports XML escaping by default, suitable for displaying untrusted data as text.

With SpEL templates, the getValue result is merely a Java value, typically a String. SpEL does not HTML-escape results automatically. If placing that string into HTML, the application must apply output encoding appropriate to the context.

Do not confuse safe expression parsing with safe HTML rendering. These are two separate concerns.

## 16. Key Takeaways

- SpEL parseExpression(String) treats the entire string as an expression; no #{...} is needed unless using template parsing.
- SpEL TemplateParserContext defaults to #{...} to separate expression blocks from literal text.
- Thymeleaf Standard Expressions include ${...}, *{...}, #{...}, @{...}, and ~{...}.
- In Thymeleaf, #{...} is a message/i18n expression; ${...} is a variable expression.
- Thymeleaf Standard Dialect uses OGNL by default; SpringStandard integrates Spring EL for variable and selection expressions.
- JSP EL uses ${...} for immediate evaluation and #{...} for deferred evaluation at supported positions.
- Ordinary JSP template text only uses ${...}; deferred #{...} is not allowed in plain text by default.
- JSP EL is Jakarta EE's own language, not SpEL.
- Spring @Value can use #{...} for SpEL, which is a Spring container integration point.
- Identical delimiters do not imply identical parser, context, or lifecycle.
- When debugging, identify the engine and processing location before modifying expressions.
- Output encoding/HTML escaping is a separate responsibility not guaranteed by SpEL parsing.

When working with templates in a Spring application, clearly identify what is processing the string: the SpEL parser, a Thymeleaf dialect, or JSP EL. This distinction helps avoid using the wrong delimiters, confusing message expressions with expression blocks, and misunderstanding evaluation timing.

## References

- Spring Framework Reference — Expression Templating: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html
- Spring Framework Javadoc — TemplateParserContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/common/TemplateParserContext.html
- Thymeleaf Tutorial — Standard Expression Syntax: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html
- Thymeleaf — Standard Dialects in 5 Minutes: https://www.thymeleaf.org/doc/articles/standarddialect5minutes.html
- Jakarta Server Pages Specification — Expression Language in JSP: https://jakarta.ee/specifications/pages/4.1/jakarta-server-pages-spec-4.1.html
- Jakarta Expression Language Specification: https://jakarta.ee/specifications/expression-language/6.1/
