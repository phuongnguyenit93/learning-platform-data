# Tokens in Java: Identifiers, Keywords, Literals, Operators, and Separators

> **Java core — language-basics / Java Vocabulary**  
> **Applies to:** Java 17 and later, using the JDK to compile and run.  
> **Objective:** Recognize the five basic token types in Java source code; distinguish identifiers from keywords, literals from operators, and separators from grammatically meaningful content. Read a line of Java from the perspective of a lexical analyzer (*lexer*), predict naming errors, and run a minimal program.

## 1. What is a token and why does it matter?

When looking at this line of code:

~~~java
int total = quantity * price;
~~~

a reader understands it as a calculation. Before analyzing statement structure, Java processes source code into lexical units called **tokens**. The line above can be split into:

| Order | Token | Type | Role |
| ---: | --- | --- | --- |
| 1 | `int` | Keyword | Primitive integer type |
| 2 | `total` | Identifier | Variable name receiving the result |
| 3 | `=` | Operator | Assignment operation |
| 4 | `quantity` | Identifier | Input variable name |
| 5 | `*` | Operator | Multiplication operation |
| 6 | `price` | Identifier | Input variable name |
| 7 | `;` | Separator | Ends the declaration statement |

**A token is not synonymous with a meaningful English word.** For example, `total` is not a Java keyword; it is a name chosen by the programmer. The `;` character is also a token even though it is only one character long.

Conceptual diagram:

~~~mermaid
flowchart LR
    A["Java source characters"] --> B["Lexical processing"]
    B --> C["Token sequence"]
    C --> D["Syntax parsing"]
    D --> E["Program structure"]
~~~

**Whitespace, line breaks, and comments** help separate or explain source code, but are not counted as Java tokens in the five categories studied here. However, spaces **inside** a string literal are part of that literal's content.

## 2. The five token categories in Java

| Category | Examples | How to identify |
| --- | --- | --- |
| **Identifier** | `studentCount`, `totalPrice`, `println` | Name of a variable, class, method, package, etc. being declared or referenced |
| **Keyword** | `class`, `public`, `int`, `if`, `return` | Words reserved by the language according to syntax rules |
| **Literal** | `42`, `12_000L`, `3.14`, `'A'`, `"Java"`, `true`, `null` | Direct representation of a value in code |
| **Operator** | `+`, `=`, `==`, `&&`, `++`, `->` | Performs arithmetic, comparison, assignment, or represents an operation in an expression |
| **Separator** | `( )`, `{ }`, `[ ]`, `;`, `,`, `.`, `@`, `::` | Delimits components, lists, blocks, member access, or related syntax |

Terms like "identifier" or "operator" are **lexical-level token types**. Combining tokens into declarations, expressions, statements, or classes is the **syntax parsing** step; a valid token does not guarantee the entire line of code is valid.

For example, `int = ;` consists of recognizable Java tokens, but it is not a valid declaration statement because it is missing a variable name and an appropriate value/expression.

## 3. Identifiers: rules and naming conventions

Identifiers are used for classes, methods, variables, fields, packages, and many other elements. Java is **case-sensitive**:

~~~java
int count = 2;
int Count = 5;
System.out.println(count + Count); // 7
~~~

`count` and `Count` are **two different names**.

### Naming rules in Java 17

- The first character must be valid for starting an identifier according to Java's Unicode rules; subsequent characters may include digits. ASCII letters, `_`, and `$` can participate in names according to those rules.
- **Do not** start an ASCII identifier with a digit: `2items` is not a valid name.
- **Do not** use reserved keywords such as `class`, `int`, or `return` as regular identifier names.
- A standalone underscore `_` **cannot be used as an identifier** in Java 17 (since Java 9, it is a reserved keyword).
- Java supports many Unicode letters in identifiers, such as `soLuong` and `sốLượng`, though writing stable, readable names keeps code more consistent.

| Example | Valid as a Java 17 variable name? | Explanation |
| --- | --- | --- |
| `studentCount` | Yes | Starts with a letter, subsequent characters are valid |
| `_count` | Yes | `_` combined with other characters, not standing alone |
| `$cache` | Yes | `$` is allowed, though best avoided in hand-written names if unnecessary |
| `sốLượng` | Yes | Java supports appropriate Unicode identifiers |
| `2ndValue` | No | Starts with a digit |
| `item-count` | Not a single identifier | Java reads `item`, operator `-`, and `count` |
| `class` | No | Reserved keyword |
| `_` | No | Standalone underscore has been reserved since Java 9 |

**Recommended conventions:** variable/method names use `lowerCamelCase` (`itemCount`), class names use `UpperCamelCase` (`InvoiceCalculator`), and `static final` constants usually follow `UPPER_SNAKE_CASE` (`MAX_ITEMS`). These are **naming conventions**, not separate lexer rule sets.

### Identifiers are not necessarily keywords

`String` is the name of a standard Java class; `System` is the name of a class; `println` is a method name; `main` and `args` are identifiers. Being "special" or "frequently used by Java" does not turn them into language keywords.

## 4. Keywords and contextually restricted words

Keywords have roles defined by the Java language. Common examples:

| Semantic group | Some Java 17 keywords | Usage example |
| --- | --- | --- |
| Class/type declaration | `class`, `interface`, `enum` | `class Person { }` |
| Access and member modifiers | `public`, `private`, `protected`, `static`, `final` | `private int age;` |
| Control flow | `if`, `else`, `switch`, `for`, `while`, `return`, `break` | `if (ready) { ... }` |
| Primitive types | `int`, `long`, `double`, `boolean`, `char`, `void` | `double rate = 1.5;` |
| Objects and exceptions | `new`, `this`, `super`, `try`, `catch`, `throw` | `new Object()` |

**Some easily confused cases:**

- `true` and `false` are **boolean literals**; `null` is the **null literal**. They are not in the list of Java keywords, even though they cannot be used as regular variable names either.
- `const` and `goto` are **reserved as keywords** by Java, even though Java has no normal functioning statements bearing those two names.
- Java 17 has **restricted/contextual identifiers or keywords** such as `var`, `record`, `yield`, `sealed`, `permits`, and `non-sealed`. They are governed by specific rules depending on syntactic position; **do not treat every occurrence of them like an always-prohibited keyword such as `class`**.

Java 17 example:

~~~java
var message = "Hello";   // var is used in local variable declarations with an initializer.
System.out.println(message);
~~~

`var` is not a class type name that can be used anywhere; the compiler infers the variable's type in contexts permitted by the language. This lesson only aims to identify lexical roles, without diving deep into type inference yet.

## 5. Literals: values written directly in code

A **literal** is a way of placing a specific value directly in source code, without referencing a variable.

| Literal type | Valid examples | Notes |
| --- | --- | --- |
| Decimal integer | `0`, `42`, `1_000` | `_` between digits improves readability |
| Other radix integers | `0b1010`, `0xFF`, `077` | Binary, hexadecimal, and octal |
| `long` integer | `12_000L` | `L` suffix; uppercase `L` is easier to distinguish from digit 1 |
| Floating-point | `3.14`, `2.5e3`, `1.5f` | Defaults to `double`; `f` creates `float` |
| `char` character | `'A'`, `'\n'` | Uses single quotes, escapes allowed |
| `String` | `"Java 17"`, `"A\nB"` | Uses double quotes |
| Boolean | `true`, `false` | Two logical values |
| Null | `null` | Null reference value |

In Java 17, a **text block** is also a literal syntax for writing multi-line strings:

~~~java
String message = """
        Xin chào
        Java 17
        """;
~~~

The opening `"""` of a text block must be followed by a line terminator; line contents and indentation processing follow Java text block rules. Do not confuse `"""` with three empty strings concatenated together.

### Three common lexical/literal mistakes

**1. A minus sign is a separate operator.** In the expression `int temperature = -5;`, the lexer recognizes the `-` token and the integer literal `5` separately. `-5` is not a single "negative literal" under this token classification.

**2. Underscores in numbers must be placed properly.** `1_000` is valid, but `_1000` is not an integer literal with an underscore: the lexer may recognize it as an identifier; using it as a numeric value causes a syntax/semantic error. The form `1000_` is also not a valid integer literal.

**3. Single quotes and double quotes are not interchangeable.** `'A'` is a char literal; `"A"` is a String literal. `'AB'` is not a valid char literal.

The words `true`, `false`, and `null` must be understood as **literals**, even when they appear in positions where Java syntax does not allow them.

## 6. Operators: read the tokens right before understanding the operation

Operators take values or objects according to Java's rules:

| Group | Representative tokens | Example |
| --- | --- | --- |
| Arithmetic | `+`, `-`, `*`, `/`, `%` | `amount * count` |
| Assignment | `=`, `+=`, `-=`, `*=`, `/=` | `total += 10` |
| Comparison | `==`, `!=`, `<`, `<=`, `>`, `>=` | `count >= 2` |
| Short-circuit logical | `&&`, `\|\|`, `!` | `ready && enabled` |
| Increment/decrement | `++`, `--` | `count++` |
| Bitwise and bit shift | `&`, `\|`, `^`, `~`, `<<`, `>>`, `>>>` | `flags & 0xFF` |
| Conditional and lambda | `?`, `:`, `->` | `ok ? 1 : 0`; `x -> x + 1` |

**Do not confuse `=` with `==`:** `=` performs assignment, while `==` compares according to type rules. In particular, for object references, `==` compares references rather than automatically checking contents with `equals`.

### Prefer matching longer tokens when possible

Java uses the longest valid token recognition rule during lexical analysis (*maximal munch*). For example:

~~~java
count++;         // ++ is a single operator, not two adjacent + tokens.
total += 3;      // += is a compound assignment operator.
boolean ok = a >= b && b != 0;
~~~

In the last line, `>=`, `&&`, and `!=` are all complete operator tokens. Whitespace helps code readability but must not be used to arbitrarily "split" a fixed operator in half. Conversely, `a + +b` uses **two different plus operators** in two syntactic positions.

**Tokenizing differs from analyzing evaluation order.** Recognizing `+`, `*`, and `=` as tokens is only the first step; operator precedence, data types, and expression evaluation rules determine the computational meaning.

## 7. Separators: boundaries of structure

Common separators in Java 17:

| Token | Familiar function | Example |
| --- | --- | --- |
| `(`, `)` | Groups conditions, parameters, expressions | `if (ready)`, `print(x)` |
| `{`, `}` | Body of a class/method/block or initializer | `class App { ... }` |
| `[`, `]` | Array declaration or access | `int[] a`, `a[0]` |
| `;` | Terminates a declaration/statement per grammar | `int x = 1;` |
| `,` | Separates elements, parameters, or matching declarations | `print(a, b)` |
| `.` | Accesses separated member names/identifiers | `System.out.println` |
| `...` | Variable-arity parameter (*varargs*) notation | `String... args` |
| `@` | Begins an annotation | `@Override` |
| `::` | Method reference | `String::valueOf` |

In `System.out.println("OK");`, the lexer sees the identifiers `System`, `out`, `println`, the tokens `.`, `(`, `)`, `;`, and the string literal `"OK"`. There is no single token named `System.out.println`.

**Note:** `::` is a separator in Java's lexical token classification, whereas `->` is an operator. They are often mentioned together when learning lambdas/method references, but they do not belong to the same lexical category.

## 8. Java 17+ program demonstrating the five token groups

Create a file **TokenDemo.java**:

~~~java
public class TokenDemo {
    public static void main(String[] args) {
        int quantity = 3;
        long unitPrice = 12_000L;
        long total = quantity * unitPrice;

        boolean qualified = total >= 30_000L && quantity > 0;
        String productName = "Java";
        char grade = 'A';

        System.out.println(productName + ": " + total);
        System.out.println("qualified=" + qualified + ", grade=" + grade);
    }
}
~~~

Run in a terminal (Bash, PowerShell, or Command Prompt) in the directory containing the file:

~~~bash
javac -encoding UTF-8 TokenDemo.java
java TokenDemo
~~~

**Exact** output:

~~~text
Java: 36000
qualified=true, grade=A
~~~

In the code:

- `public`, `class`, `static`, `void`, `int`, `long`, `boolean`, and `char` are **keywords**.
- `TokenDemo`, `main`, `args`, `quantity`, `unitPrice`, `total`, `qualified`, `String`, `productName`, and `grade` are **identifiers** (where `String` is a class name).
- `3`, `12_000L`, `30_000L`, `0`, `"Java"`, `'A'`, and the strings passed to `println` are **literals**.
- `=`, `*`, `>=`, `&&`, `>`, `+` are **operators**.
- `{ }`, `( )`, `[ ]`, `;`, `,`, and `.` are **separators**.

The example contains spaces and blank lines for readability; they do not alter token types. The program uses familiar class and `main` syntax and requires no external libraries beyond the JDK.

## 9. Common traps: valid tokens yet the program still fails

| Code snippet or case | Diagnosis | Fix |
| --- | --- | --- |
| `int class = 1;` | `class` is a keyword and cannot be used as an identifier | Change to `classCount` or an appropriate name |
| `int 2items = 3;` | A digit cannot start a variable name like this | Use `items2` |
| `int item-count = 3;` | `-` is an operator, not a connecting character in an identifier | Use `itemCount` or `item_count` |
| `int _ = 1;` | Standalone `_` is a reserved keyword in Java 17 | Choose a specific name like `unusedCount` |
| `int value = "7";` | A string literal cannot be assigned directly to an `int` variable | Use `7` or convert the string with `Integer.parseInt` when appropriate |
| `char c = "A";` | `"A"` is a String, not a char | Use `'A'` |
| `boolean ok = True;` | `True` is not the boolean literal `true`; Java is case-sensitive | Use `true` |
| `int v = 1__000;` | **Valid**: multiple consecutive underscores between digits are accepted by Java | Do not assume every `__` is invalid |
| `int x = -5;` | The minus sign is a separate operator, not part of literal `5` | Read tokens as `=`, `-`, `5`, `;` |
| `int n = 8 / 0;` | Valid tokens, but the integer operation throws an error at runtime | Check the denominator; lexical syntax does not guarantee a safe operation |

**A technical note:** some errors in the table can be detected by the compiler immediately during syntax parsing or type checking; others only occur at runtime. Knowing tokens does not replace checking **types**, **variable scope**, and **program semantics**.

## 10. Practice analyzing token sequences

Try classifying the following line without running it first:

~~~java
boolean accepted = total >= 100 && quantity != 0;
~~~

| Group | Tokens present |
| --- | --- |
| Keywords | `boolean` |
| Identifiers | `accepted`, `total`, `quantity` |
| Literals | `100`, `0` |
| Operators | `=`, `>=`, `&&`, `!=` |
| Separators | `;` |

Next, replace `>=` with `> =` and try compiling inside a program with full variable declarations: the two tokens `>` and `=` **cannot substitute for** the single `>=` operator in that comparison expression.

Another analysis exercise:

~~~java
System.out.println("Hi");
~~~

Count them: identifier `System`, separator `.`, identifier `out`, separator `.`, identifier `println`, separator `(`, string literal `"Hi"`, separator `)`, separator `;`. **9 tokens** in total.

**Comments do not become tokens:** in `int x = 1; // note`, the tokens still end at `;`; the `// note` part is a comment. In `String s = "a b";`, the space **lies inside the literal** and is therefore part of the string value.

## 11. Self-practice exercises and guided answers

**Exercise 1 — Identification.** Given `long distance = 10_000L;`, identify the keyword, identifier, operator, literal, and separator.

*Answer:* `long`; `distance`; `=`; `10_000L`; `;`.

**Exercise 2 — Naming.** Among `price2`, `2price`, `price_total`, `total-price`, `_`, and `$cache`, which can be Java 17 identifiers? Why should `$` still be limited in self-written names?

*Guidance:* `price2`, `price_total`, and `$cache` are valid; `2price`, `total-price`, and `_` are not valid single identifiers. `$` is permitted, but fits poorly with standard naming conventions.

**Exercise 3 — Keyword or literal?** Distinguish `boolean` from `true`; distinguish `String` from `class`; explain why `null` is not an identifier.

**Exercise 4 — Longest operator.** Break `i++;` down into tokens. Why is it not read as `i`, `+`, `+`, `;`? Next, analyze `total += 1;`.

**Exercise 5 — Error fixing.** Fix `int class = 3;` and `char unit = "A";`. Identify the error category of each line instead of just giving the answer.

**Exercise 6 — Run it yourself.** Compile `TokenDemo.java`, change literal `12_000L` to `15_000L`, and predict both output lines; then try using `'A'` instead of `"Java"` for the `String` variable to observe the type error.

## 12. End-of-lesson checklist

- [ ] Know that a **token is a lexical unit**, distinct from a valid statement/program.
- [ ] Distinguish identifier, keyword, literal, operator, and separator directly within a line of Java.
- [ ] Remember that `String`, `System`, `println` are not keywords; `true`, `false`, `null` are literals.
- [ ] Know that Java 17 variable names are case-sensitive, cannot start with a digit, and standalone `_` is not a valid identifier.
- [ ] Recognize that `-5` consists of operator `-` and literal `5`; `++` is a single operator token.
- [ ] Explain the roles of `;`, `.`, `( )`, and `{ }` without confusing them with operators.
- [ ] Independently compile `TokenDemo.java` with `javac`, run it with `java`, and compare the output.

**Summary:** Understanding Java's vocabulary helps you read code accurately symbol by symbol, choose valid names, and distinguish token errors from syntax/type/semantic errors. Tokens are the **input building blocks** that the language assembles into meaningful program structures.
