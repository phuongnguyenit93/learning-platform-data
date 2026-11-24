# Whitespace and How Tokens Are Read in SpEL

Spring Expression Language (SpEL) takes input in the form of an expression string. Before an expression is executed, the parser must recognize that string into **tokens** and then check whether the tokens form a valid structure. Therefore, when reading or editing a SpEL expression, you need to distinguish three things: characters in the source string, tokens recognized by the lexer, and the meaning the parser builds from those tokens.

Whitespace usually serves only to separate tokens. It makes expressions easier to read, though it is not always part of the value. The most obvious exception is whitespace inside a string literal: that part belongs to the string's data and is preserved as-is.

## 1. From Expression String to Evaluation Result

SpEL processing can be pictured in three steps:

1. **Tokenize:** the lexer reads the source string and recognizes identifiers, literals, delimiters, operators, and special symbols.
2. **Parse:** the parser checks the token order against SpEL's grammar and builds the expression structure, often represented as an expression tree or abstract syntax tree.
3. **Evaluate:** the expression is executed within a specific EvaluationContext. Only at this step does SpEL resolve variables, properties, methods, bean references, and actual values.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= 1000");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

When calling **parseExpression(...)**, the parser checks syntax and builds the expression. When calling **getValue(...)**, SpEL looks up the **order** variable, reads the **total** property, and compares it against the number **1000**.

This distinction helps diagnose errors:

- **ParseException:** the string does not form a valid expression, usually due to a missing operand, parenthesis, or misplaced operator.
- **EvaluationException:** the syntax was accepted, but evaluation runs into a problem, such as a nonexistent variable, unreadable property, or uncallable method in the current context.

An expression that parses successfully does not necessarily run in every EvaluationContext.

## 2. What Is a Token?

A token is a syntactic unit recognized by the lexer. A single token can consist of multiple characters. For example, **>=** is an operator, **customer** is an identifier, and **'READY FOR PICKUP'** is a single string literal even though it contains spaces.

Common token categories in SpEL:

| Category | Example | Role |
| --- | --- | --- |
| Identifier | **order**, **customer**, **total** | Property name, method name, or identifier component |
| Variable reference | **#order**, **#root**, **#this** | Access a variable in EvaluationContext or the current object |
| Bean reference | **@policyService** | Reference a bean in the application context |
| Type reference | **T(java.lang.Math)** | Reference a Java type |
| String literal | **'READY'**, **'Hello SpEL'** | String value |
| Numeric literal | **42**, **3.14**, **0x2A** | Numeric value |
| Boolean / null | **true**, **false**, **null** | Logical value and null value |
| Punctuation | **.**, **,**, **(**, **)**, **[**, **]** | Grouping, property access, passing arguments, or indexing elements |
| Operator | **+**, **>=**, **and**, **matches** | Perform an arithmetic operation or comparison |

Not every token has standalone meaning. The dot in **order.total** joins a property access; the parentheses in **max(3, 7)** group the argument list of a method call; the **#** symbol introduces a variable reference.

## 3. How Is Whitespace Handled?

### 3.1. Whitespace Between Tokens Usually Does Not Change Meaning

SpEL ignores whitespace used to separate complete tokens. Therefore, the following two expressions have the same meaning:

~~~text
#order.total >= 1000
#order.total>=1000
~~~

Similarly, you can add line breaks to make long expressions easier to read, as long as you break between tokens:

~~~text
#order.status == 'READY'
    and #order.total >= 1000
~~~

In the expression above, the line break and spaces around **and** do not change the condition. The lexer still receives the same sequence of tokens in the same order.

The recommended style is to put spaces around binary operators, after commas, and between logical branches. This is a formatting convention to help readers clearly see each part, not a mandatory requirement of the parser in every position.

### 3.2. Do Not Insert Whitespace Inside a Token

Whitespace cannot stand in for part of a token. Example:

| Written | How the lexer/parser interprets it |
| --- | --- |
| **total >= 1000** | One identifier, one comparison operator, and one number |
| **total > = 1000** | The **>** and **=** symbols are separated; no longer the **>=** operator |
| **#order.total** | Variable reference **order**, then property access **total** |
| **#ord er.total** | Identifier split into two parts; no longer the variable **order** |
| **1000** | One numeric literal |
| **1 000** | Two separate numeric parts; not the number one thousand |

Certain symbol pairs must also stay adjacent because they form a distinct operator:

- **?.** is the safe-navigation operator.
- **?:** is the Elvis operator.
- **>=** and **<=** are comparison operators.
- **!=** is the not-equal operator.

For example, **#customer?.address** uses safe navigation to access **address** when **customer** is non-null. If the symbols are split into **? .**, the token sequence is different and is no longer the safe-navigation operator syntax.

### 3.3. Whitespace Inside a String Literal Is Data

String literals are enclosed in quotes. Spaces inside the string are preserved:

~~~text
'READY FOR PICKUP'
'Hello    Spring'
~~~

The two strings above contain whitespace in their actual values. They are not equivalent to **'READY FOR PICKUP'** and **'Hello Spring'** if the application performs exact string comparison.

SpEL allows single quotes or double quotes for string literals. When you need to represent a single quote inside a string enclosed in single quotes, you can double the quote:

~~~text
'O''Reilly'
~~~

The resulting string value is **O'Reilly**. Do not place arbitrary spaces between the opening and closing quotes of a literal because characters inside are content, not syntactic whitespace.

### 3.4. Word-Form Operators Must Be Recognized as Separate Tokens

SpEL has operators written as words, for example:

- Comparison: **lt**, **le**, **gt**, **ge**, **eq**, **ne**.
- Logical: **and**, **or**, **not**.
- Arithmetic: **div**, **mod**.

These words act as operators when the lexer recognizes them as separate tokens. Do not merge them into another identifier. Example:

~~~text
#order.total gt 1000
#order.total >= 1000
~~~

Both expressions above express the greater-than comparison. However, **totalgt** is a single identifier, not the identifier **total** followed by the operator **gt**.

Word-form operators are useful in XML configuration, where the **<** and **>** characters have special meaning in XML syntax. Example:

~~~xml
<int:filter
    input-channel="orders"
    expression="payload.total gt 1000" />
~~~

If you write symbolic operators in XML, you must escape the characters according to XML rules, such as **&lt;** and **&gt;**.

## 4. Reading an Expression in Token Order

Consider the expression:

~~~text
#order.status == 'READY FOR PICKUP' and #order.total >= 1000
~~~

It can be broken down into tokens in order:

| Order | Token | Meaning |
| --- | --- | --- |
| 1 | **#** | Starts variable reference |
| 2 | **order** | Variable name |
| 3 | **.** | Property access operator |
| 4 | **status** | Property of the order object |
| 5 | **==** | Equality operator |
| 6 | **'READY FOR PICKUP'** | String literal; spaces inside are preserved |
| 7 | **and** | Logical AND operator |
| 8 | **#order** | Reference to the same order variable |
| 9 | **.** | Property access |
| 10 | **total** | total property |
| 11 | **>=** | Greater-than-or-equal operator |
| 12 | **1000** | Numeric literal |

The parser groups the tokens into the equivalent structure:

~~~text
(#order.status == 'READY FOR PICKUP')
and
(#order.total >= 1000)
~~~

During evaluation, SpEL retrieves the **order** variable from the context, reads **status** and **total**, then performs the two comparisons and combines the results with **and**.

Noticeably, the lexer does not understand the business meaning of **READY FOR PICKUP** or **total**. It only recognizes literals and identifiers. Whether **status** exists or **total** has a comparable data type belongs to the evaluation phase and the object model.

## 5. Recognizing Delimiters and Operators in Compound Expressions

### 5.1. Property, Method, and Indexer

The symbols **.**, **()**, and **[]** help the parser recognize the operation being performed:

~~~text
#order.customer.name
#name.toUpperCase()
#orders[0]
#headers['tenantId']
~~~

- **.** accesses the next property or method.
- **()** groups the arguments of a method call.
- **[]** accesses an element of a collection, array, or map by index/key.

Commas separate arguments or elements:

~~~text
T(java.lang.Math).max(3, 7)
{1, 2, 3}
~~~

In the first example, **3** and **7** are two separate arguments. In the second example, commas separate the elements of an inline list.

### 5.2. Parentheses and Expression Grouping Order

Parentheses clarify which part of an expression should be grouped:

~~~text
(#order.total + #order.shippingFee) >= 1000
~~~

Do not rely on memory for precedence when an expression has multiple operations. Using parentheses helps readers immediately see which part is evaluated first and reduces the risk of misunderstanding when modifying a condition.

### 5.3. Ternary and Elvis Operators

The ternary operator has the form **condition ? valueIfTrue : valueIfFalse**:

~~~text
#order.total >= 1000 ? 'FREE_SHIPPING' : 'STANDARD_SHIPPING'
~~~

The Elvis operator **?:** provides a fallback value when the left-hand side is null or treated as having no value according to SpEL rules:

~~~text
#customer.nickname ?: #customer.name
~~~

The **?** and **:** symbols in ternary are structural delimiter tokens. In the Elvis operator, the pair **?:** must be written together for the lexer to recognize the operator properly.

### 5.4. Selection and Projection

For collections, SpEL uses dot-prefixed symbols to select or transform elements:

~~~text
#orders.?[total >= 1000]
#orders.![customer.name]
#orders.^[total >= 1000]
#orders.$[total >= 1000]
~~~

- **.?[ ... ]** selects elements satisfying the condition.
- **.![ ... ]** projection: creates a new collection from an expression applied to each element.
- **.^[ ... ]** retrieves the first element satisfying the condition.
- **.$[ ... ]** retrieves the last element satisfying the condition.

These symbols are distinct syntactic constructs. When reading, recognize the entire **.?[**, **.![**, **.^[**, or **.$[** sequence before analyzing the condition inside.

## 6. Distinguishing Important Prefix Symbols

Several symbols appear at the beginning of an expression or before an identifier, each with a different function:

| Syntax | Meaning | Example |
| --- | --- | --- |
| **#name** | Variable in the evaluation context | **#order**, **#root** |
| **@name** | Bean in the application context | **@permissionService** |
| **T(Type)** | Java type reference | **T(java.time.LocalDate)** |
| **${{...}** | Spring property placeholder, not SpEL syntax | **${{app.region}** |
| **#{...}** | SpEL embedding delimiter in places supporting templates/expressions | **#{T(java.lang.Math).PI}** |

Remember that not every annotation requires writing the expression inside **#{...}**. Some attributes accept SpEL content directly, for example:

~~~java
@Cacheable(key = "#isbn")
@PreAuthorize("hasAuthority('invoice:read')")
~~~

Meanwhile, **@Value** typically uses placeholders or expressions with the appropriate delimiter:

~~~java
@Value("${{app.region:ap-southeast-1}")
private String region;

@Value("#{T(java.lang.Math).PI}")
private double pi;
~~~

**${{...}** retrieves configuration values; **#{...}** requests SpEL expression evaluation at supported integration points. Both mechanisms can appear together in some configurations, but they are not interchangeable ways of writing the same thing.

## 7. Rules for Formatting Readable Expressions

When writing SpEL in annotations, XML, or Java configuration, apply several conventions:

1. Put spaces around binary operators such as **+**, **==**, **>=**, **and**, **or**.
2. Break lines at token boundaries or between long logical branches; do not split an identifier, literal, or compound operator in two.
3. Use parentheses to make grouping order explicit when there are multiple operations.
4. Keep multi-character operators such as **?.**, **?:**, **>=**, **!=** together.
5. Preserve intentional whitespace inside string literals.
6. Use word-form operators such as **lt**, **gt**, **le**, **ge** when the expression is inside XML and special characters need to be avoided.
7. Clearly distinguish variable **#order**, bean **@orderService**, and root object property **order**.
8. When an expression is long or contains many business rules, move the logic into a bean method and call that method from SpEL.

An expression can be written on one line or multiple lines. What matters is that token boundaries are not broken and the structure remains readable.

## 8. How to Diagnose Token and Whitespace Errors

When the parser reports an error, check in order:

1. **Check compound operators:** did you accidentally write **> =** instead of **>=**, or **? :** instead of **?:**?
2. **Check identifiers:** does a variable/property/method name have an inserted space or a casing typo?
3. **Check literals:** are opening/closing quotes balanced; are quotes inside strings properly escaped?
4. **Check brackets and delimiters:** do **()**, **[]**, commas, and colons have matching pairs in the right positions?
5. **Check word-form operators:** are **and**, **or**, **not**, **gt**, **lt** separated from adjacent identifiers?
6. **Separate parse errors from evaluation errors:** if parsing succeeds, check EvaluationContext, variables, properties, methods, and actual data types.

You can reduce the expression to a small example to test the parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= 1000");

System.out.println(expression.getExpressionString());
~~~

This snippet lets you test separately whether the expression string is accepted by the parser. To test execution results, you need to provide an EvaluationContext with an **order** variable and an object with a suitable **total** property.

Do not fix errors by randomly adding or removing whitespace. Identify which token is being split or merged incorrectly, then fix the exact syntactic boundary.

## 9. Quick Takeaways

- The lexer recognizes tokens; the parser assembles tokens into an expression structure; the evaluator runs that structure in an EvaluationContext.
- Whitespace between complete tokens usually does not affect the result.
- Whitespace inside string literals is data and is preserved.
- Do not insert whitespace inside identifiers, numeric literals, or multi-character operators.
- **#** introduces a variable, **@** references a bean, **T(...)** references a Java type.
- **.**, **()**, **[]** serve property access, method invocation, and element access, respectively.
- **?.**, **?:**, **>=**, **!=** must be kept intact as compound operators.
- Successful parsing only confirms syntax; variables and properties must still exist during evaluation.
- Use conventional whitespace to keep expressions concise, consistent, and easy to review.

## 10. Official References

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Expression Language Basics](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework — Operators in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework — Parser Configuration](https://docs.spring.io/spring-framework/reference/core/expressions/parser.html)
- [Spring Framework — Expression Templating](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html)
