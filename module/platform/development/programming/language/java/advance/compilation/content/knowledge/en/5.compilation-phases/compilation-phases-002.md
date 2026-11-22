# From Source Characters to Tokens and Abstract Syntax Trees in Java

When reading a **.java** file, the compiler does not understand the whole program by looking at each line immediately the way humans do. It moves through increasingly structured levels of representation: **source characters → lexical units (tokens) → syntactic structure → abstract syntax tree (AST)**. Only then does the compiler continue with tasks such as name resolution, type checking, flow analysis, and bytecode generation.

Understanding this initial stage helps explain why code that looks "almost right" causes the compiler to report completely different character errors, syntax errors, or type errors; why whitespace sometimes changes meaning; and why the AST represents expression structure rather than simply being a copy of each character.

## 1. Overview of the Source Code Path

Example file **Expressions.java**:

~~~java
public class Expressions {
    public static void main(String[] args) {
        int result = 2 + 3 * 4;
        System.out.println(result);
    }
}
~~~

The path can be pictured as:

~~~text
.java file (bytes, by charset)
       |
       v
Decode into source code Unicode characters
       |
       v
Translate Unicode escapes, recognize line terminators
       |
       v
Lexical analysis / scanning
       |  Skip whitespace and comments when building token stream
       v
Token stream: int | result | = | 2 | + | 3 | * | 4 | ;
       |
       v
Parsing according to Java grammar
       |
       v
AST: variable declaration
       └── initializer: add
           ├── 2
           └── multiply
               ├── 3
               └── 4
       |
       v
Semantic and code generation steps (outside the main scope of this article)
~~~

**The core idea:** the lexer identifies *"what token is this?"*; the parser determines *"what valid structure do these tokens combine into?"*. The AST is a result of the parser step. **The AST does not yet prove the program is well-typed or runnable.**

Three data levels that should not be confused:

| Level | Example | Primary information |
| --- | --- | --- |
| Source characters | Characters of the string "result = 2 + 3 * 4;" | Text, position, spaces, quotes |
| Token | IDENTIFIER(result), ASSIGN(=), INT_LITERAL(2), PLUS(+), ... | Token kind, content, and usually source position |
| AST | VariableDecl(result, Binary(+,...)) | Parent–child relationships, operator precedence, syntactic construct kind |

In a real compiler, phases may collaborate and include internal optimizations; the diagram is a **conceptual model**, not a claim that every compiler must store three separate intermediate copies in memory.

## 2. Input: Bytes, Unicode Characters, and Lexical Rules

### 2.1. Source files have an encoding; the language processes characters

A file on disk consists of **bytes**. The compiler tool must decode the bytes according to the chosen character encoding (for example, UTF-8) before working with source characters. When using **javac**, you can specify the encoding with the **-encoding** option:

~~~bash
javac -encoding UTF-8 -d out Expressions.java
~~~

This option determines how bytes in the file are read; it is **different** from the Unicode escape syntax written inside the source. If the file's encoding does not match the encoding used by the compiler, Unicode content may be misread or cause errors even before token recognition takes place.

The Java language uses Unicode, so identifiers can contain non-ASCII letters if they satisfy Java's identifier rules, for example **tổngSố**. However, whether the lexer treats a character as part of an identifier, whitespace, or an invalid character is still determined by the Java Language Specification (JLS); not every character that looks like a letter or whitespace is treated identically.

### 2.2. Three lexical translation steps per the JLS

The JLS describes the character translation process prior to tokens in this order:

1. **Unicode escapes** in the input character stream are translated into their corresponding characters.
2. The character stream after the step above is divided into **input characters** and **line terminators**.
3. From those, **input elements** are recognized, consisting of whitespace, comments, and tokens. Whitespace/comments do not become tokens used by the syntactic grammar.

The order matters. For example, the source sequence below contains a Unicode escape for the character **a**:

~~~java
public cl\u0061ss Demo {
}
~~~

After translating the Unicode escape, **cl\u0061ss** becomes **class**. The lexer therefore recognizes **class** as a keyword. This is an example that compiles when saved as **Demo.java**:

~~~bash
javac Demo.java
~~~

A Unicode escape uses a backslash, one or more **u** characters, and exactly four hexadecimal digits for a UTF-16 code unit. For characters outside the Basic Multilingual Plane, a UTF-16 surrogate pair can be represented by two Unicode escapes according to JLS rules.

**Do not confuse Unicode escapes and string escapes.** The two processing layers occur at different times:

- **\u000a** in source code is processed before the lexer classifies quotes and strings: it produces an actual newline character.
- **\n** inside a Java string literal is an escape sequence interpreted within the context of the literal.

Therefore, the following snippet is **intentionally invalid**:

~~~java
// Invalid: Unicode escape turns into a newline right inside the literal.
String text = "\u000a";
~~~

Whereas the following snippet is valid:

~~~java
String text = "\n";
~~~

This early rule also means **Unicode escapes can produce backslashes, quotes, or newlines before comments/strings are identified**. When reviewing source code containing unusual escapes in comments, do not assume every character visible after **//** remains comment content. Details on conditions for recognizing **\\** and consecutive escapes must follow JLS §3.3; do not guess "whenever backslash-u is seen, replace it in all cases."

### 2.3. Line terminators are not just formatting

The JLS recognizes line terminators as **LF**, **CR**, or the **CRLF** pair. They help the compiler track error locations and determine where **//** comments end. A newline generated from a Unicode escape can change where a comment ends. Tab width or how an IDE wraps lines affects how humans see the file, whereas Java grammar relies on input characters normalized according to language rules.

## 3. Lexer (scanner): Splitting Characters into Tokens

**Lexical analysis**, or scanning, converts the character stream after translation steps into tokens with defined kinds. A token typically carries:

- **Kind/type**: identifier, keyword, literal, separator, or operator.
- **Lexeme**: the corresponding character sequence, such as **result** or **+=**.
- **Source position**: offset/line/column used for error reporting or tool support. The specific format depends on the compiler.

The JLS classifies tokens into **identifier, keyword, literal, separator, operator**. Whitespace and comments are other input elements, typically omitted from the token stream for parsing.

### 3.1. Token kinds by example

| Kind | Example | Role |
| --- | --- | --- |
| Keyword | **class**, **public**, **int**, **if**, **return** | Has syntactic meaning defined by the language |
| Identifier | **Expressions**, **result**, **main**, **println** | Name chosen by the programmer or API, interpreted by context |
| Literal | **42**, **3.5**, **'A'**, **"Hello"**, **true**, **null** | Represents a value directly in source |
| Separator | **(**, **)**, **{**, **}**, **[**, **]**, **;**, **,**, **.** | Delimits syntactic parts |
| Operator | **=**, **+**, **\***, **==**, **&&**, **++**, **->** | Assignment, computation, comparison, lambda expressions... |

**Version-specific language note:** Java has **contextual keywords** and restricted identifiers in certain contexts such as **var**, **yield**, **record**, or **sealed**. Do not build a modern Java lexer with a simple table saying "all of these strings are always keywords"; interpreting certain words depends on syntactic context and source version. **true**, **false**, and **null** are literals per the JLS, not merely user-defined identifiers.

### 3.2. Concrete breakdown of a statement

Given the source:

~~~java
int result = 2 + 3 * 4;
~~~

The token stream can be represented in a table:

| Order | Lexeme | Token category |
| ---: | --- | --- |
| 1 | **int** | Keyword |
| 2 | **result** | Identifier |
| 3 | **=** | Operator |
| 4 | **2** | Integer literal |
| 5 | **+** | Operator |
| 6 | **3** | Integer literal |
| 7 | **\*** | Operator |
| 8 | **4** | Integer literal |
| 9 | **;** | Separator |

Spaces between them are not listed because they are not syntactic tokens. Conversely, **whitespace can still determine token boundaries**: **int result** contains keyword **int** followed by identifier **result**; whereas **intresult** is a single separate identifier, not two tokens.

### 3.3. String literals and comments are recognized by lexer rules

Consider:

~~~java
int result /* add values */ = 2 + 3; // note
String message = "2 + 3";
~~~

In the first statement, comments contribute no tokens to the expression. In the second statement, **"2 + 3"** is recognized as **a single string literal token**, not split into the operators and numbers inside the quotes.

Distinguish these points:

- **/** and **\*** individually are operators; **/* ... */** is a multi-line comment according to the lexical grammar.
- **//** starts an end-of-line comment and extends to the line terminator.
- **/**, **\***, or **+** inside a valid string literal is literal content, not lexed as operators outside the string.
- **/***\* ... \*/** is a special Javadoc documentation form for documentation tools, yet when parsing a Java program it is still a comment; the compiler/tools may keep comment metadata in a separate processing path to serve Javadoc.

Comments and whitespace are typically discarded when building an AST; therefore a basic AST is not a faithful representation of every space/comment in the source. Formatters and IDEs that want to preserve comment positions will need additional source data or syntactic structures richer than a pure AST.

### 3.4. The "longest possible match" (maximal munch) rule

The lexer usually matches **the longest possible token** according to JLS rules rather than splitting it up to form a seemingly sensible expression. Example:

~~~text
Source:   a--b
Tokens:   IDENTIFIER(a)  --  IDENTIFIER(b)
Not:      IDENTIFIER(a)  -  -  IDENTIFIER(b)
~~~

If a programmer wants to subtract a negative number, clear boundaries must be written:

~~~java
int a = 5;
int b = 2;
int c = a - -b;
System.out.println(c);
~~~

The result is **7**. Meanwhile, **a--b** is not an alternative syntax for **a - -b**: the lexer matches **--**, forcing the parser to process it under decrement operator and operand position rules, resulting in a syntax error when written like that.

**Contextual exceptions:** Modern Java has special rules for **consecutive > symbols in generic type arguments** and certain contextual keywords. For example, **List<List<String>>** can close two type arguments with **>>**, while **a >> 1** is a bit-shift expression. The lexer/parser cannot be accurately explained solely by a rule of thumb "always take the longest operator without considering context" for every case.

### 3.5. Literals are not always just digits or punctuation

**1_000**, **0xFF**, **3.14** are valid literals (depending on context and type). The lexer must understand the structure of each kind of literal, rather than just grouping every sequence of digits. For example, **"hello world"** contains whitespace yet is a single string literal token; **'A'** is a character literal. The text block syntax **"""..."""** is supported in Java 17+, with its own rules for delimiters and newlines. Invalid characters or escapes in a literal can cause the lexer/compiler to report errors before a complete AST exists.

## 4. Parser: From Tokens to Syntactic Structure

Once the token stream is produced, the **parser** applies production rules in the Java grammar to recognize compilation units, class/interface declarations, fields, methods, statements, expressions, and nested constructs. A lexically valid sequence of tokens can still be **syntactically invalid**.

For example, the lexer can tokenize all of the following:

~~~java
int result = ;
~~~

However, the parser cannot form a valid expression after **=** because it encounters **;** too early. This is a **syntax error**. By contrast:

~~~java
int result = "hello";
~~~

has a valid syntactic structure (a variable declaration with an initializer), yet **cannot assign String to int**. This error belongs to the later semantic analysis/type checking step, not a scanner error.

### 4.1. AST represents structure, not a flat token stream

In the statement:

~~~java
int result = 2 + 3 * 4;
~~~

the **\*** operator has higher precedence than **+**. The parser builds an equivalent structure:

~~~text
Variable declaration: result
├── Type: int
└── Initializer: PLUS
    ├── Left:  INTEGER_LITERAL(2)
    └── Right: MULTIPLY
        ├── Left:  INTEGER_LITERAL(3)
        └── Right: INTEGER_LITERAL(4)
~~~

Thus the result of the computation is **14**, even though reading left to right beginners sometimes mistake it for **(2 + 3) * 4 = 20**.

If parentheses are added:

~~~java
int result = (2 + 3) * 4;
~~~

then the initializer's AST will have **MULTIPLY** at the outer level, and **PLUS** inside (the parser or AST API may additionally keep a **PARENTHESIZED** node for the parenthesized part). The value becomes **20**.

**Recognizing grammar ≠ evaluating values:** the AST describes the expression and order of operations; the compiler may perform constant folding or optimization in a later phase, but having a PLUS node in an AST does not mean the parser executed addition.

### 4.2. A small program illustrating AST differences

Create **Expressions.java**:

~~~java
public class Expressions {
    public static void main(String[] args) {
        int first = 2 + 3 * 4;
        int second = (2 + 3) * 4;
        System.out.println(first);
        System.out.println(second);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -d out Expressions.java
java -cp out Expressions
~~~

**Exact standard output:**

~~~text
14
20
~~~

From the lexer, both statements contain tokens **2**, **+**, **3**, **\***, **4** (the second statement additionally has **(**, **)**). From the parser, they have different AST shapes according to precedence and parentheses grammar. This example is enough to distinguish **tokenization** and **parsing** without writing a compiler from scratch.

### 4.3. Concrete syntax tree (CST/parse tree) vs. AST

A **parse tree/CST** (by common compiler theory terminology) may retain nearly all grammar components: intermediate nodes, parentheses, separators, and terminals. An **AST** selects the useful nodes to represent the structural meaning of the program such as classes, methods, statements, and expressions.

| Criterion | Conceptual CST / parse tree | AST |
| --- | --- | --- |
| Focus | How the token stream matches grammar rules | Program structure for analysis |
| Semicolons, parentheses, separators | Usually explicitly present | May be omitted or represented indirectly |
| Intermediate grammar nodes | Usually many | Usually fewer, closer to language concepts |
| Uses | Parsers, formatters that need to retain syntax details | Static analysis, IDEs, semantic checking, code transformation |

**There is no single AST shape applicable to every compiler**. For example, in the Java Compiler Tree API, nodes have enum kinds such as **CLASS**, **VARIABLE**, **PLUS**, **MULTIPLY**, and there is a **PARENTHESIZED** node. Another parser library may use different intermediate names/nodes while still representing the same Java structure.

## 5. Inspecting a Real AST Using the Java Compiler Tree API

Java provides the syntax tree analysis API in **jdk.compiler**, notably **com.sun.source.tree** and **com.sun.source.util.JavacTask**. This is a published compiler/tree API for tools, unlike accessing unstable internal implementation classes in **com.sun.tools.javac.***.

The following example creates a Java source **in memory**, calls **parse()**, walks the class declaration, and finds the initializer of variable **answer**. It helps verify the AST in practice.

Create file **InspectAst.java** (entirely a standalone program):

~~~java
import com.sun.source.tree.BinaryTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class InspectAst {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(
                URI.create("string:///Example.java"),
                JavaFileObject.Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        String code = "class Example { int answer = 2 + 3 * 4; }";
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        JavacTask task = (JavacTask) compiler.getTask(
            null, null, null, List.of("-proc:none"), null,
            List.of(new Source(code))
        );

        for (CompilationUnitTree unit : task.parse()) {
            for (Tree declaration : unit.getTypeDecls()) {
                System.out.println(declaration.getKind());
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitVariable(
                    VariableTree variable, Void unused
                ) {
                    if (variable.getName().contentEquals("answer")) {
                        Tree initializer = variable.getInitializer();
                        BinaryTree addition = (BinaryTree) initializer;
                        System.out.println(initializer.getKind());
                        System.out.println(
                            addition.getRightOperand().getKind()
                        );
                    }
                    return super.visitVariable(variable, unused);
                }
            }.scan(unit, null);
        }
    }
}
~~~

From the directory containing the file, run with **JDK 17+** (requires a JDK with the **jdk.compiler** module, not merely a runtime image stripped of the compiler):

~~~bash
javac -d out InspectAst.java
java -cp out InspectAst
~~~

**Standard output verified on JDK 21:**

~~~text
CLASS
PLUS
MULTIPLY
~~~

How to read it:

1. **CLASS**: the AST contains a top-level class **Example**.
2. **PLUS**: the initializer of variable **answer** has addition at the outer level.
3. **MULTIPLY**: the right branch of the addition is the multiplication **3 * 4**.

Calling **JavacTask.parse()** retrieves the syntax tree without calling **analyze()** or generate() in this example. Thus the program illustrates the exact boundary of **the parser creating the AST**, without claiming to have checked all names or types in the source string. A runtime image without the Java compiler may cause **ToolProvider.getSystemJavaCompiler()** to return **null**; use a full JDK.

**Separate note on the API:** **com.sun.source.tree** reflects the tree per the Java Compiler API, not the raw token set and does not necessarily store comments/whitespace. If you need to manipulate every character/formatting detail, use parser tooling designed to be source-preserving or supplement with source positions. Do not use internal **com.sun.tools.javac.parser.*** classes as a stable public API for applications.

## 6. Identifying Three Error Categories by Phase

The three snippets below **illustrate errors**; they are not three complete runnable programs.

### 6.1. Lexical-level error

~~~java
String value = "chưa đóng;
~~~

A double quote opens a string without a valid closing quote. The scanner cannot construct a complete string literal and the compiler reports an error related to the literal/string. Similarly, malformed Unicode escapes or disallowed characters can cause early-phase errors.

### 6.2. Syntax-level error

~~~java
int count = ;
~~~

All characters tokenize into normal tokens, yet the grammar requires an expression after **=**; the parser cannot build a complete valid variable declaration.

### 6.3. Semantic/type-checking error

~~~java
int count = "five";
~~~

Tokens are valid, the variable declaration syntax is valid, and the AST has a string literal initializer. However, type **String** cannot be assigned to **int**. The error appears when the compiler analyzes the meaning of the tree (type attribution/type checking).

| Symptom | Likely processing area | How to reason |
| --- | --- | --- |
| Illegal character, unclosed literal | Character reading/scanning | Check encoding, quotes, escapes |
| Expected ';', expected expression | Parsing | Check token order, separators |
| Incompatible types, cannot find symbol | Semantic analysis | Check types, scope, imports, declarations |

**Error messages are not absolute boundaries between phases**: a real compiler has error detection and recovery strategies, and an early error can trigger multiple subsequent diagnostics. When debugging, start from **the first error with a clear cause** and inspect the source code right at the reported position.

## 7. Source Positions, Error Recovery, and Benefits for IDEs

While the parser's token stream typically strips whitespace/comments, the compiler still needs **source positions** (offset/line/column) to report errors accurately. The AST API can coordinate with utilities like **Trees** and **SourcePositions** to trace a node's position back to the source file. For IDEs, that is the foundation for highlighting, go-to-declaration, find-references, and refactoring.

When tokens are missing or invalid, the parser usually **attempts error recovery** to find more issues in the same compilation run; some AST nodes are produced in an incomplete or error-marked state. Therefore:

- "Having an AST" does not mean the source code is valid.
- The AST of erroneous source should not be analyzed as a complete tree if the tool does not handle error states.
- A formatter wishing to preserve comments/spaces needs additional information beyond the basic structural AST.
- Recognition of contextual keywords and new syntax depends on the **source level**; for example, Java 21 code may fail to parse when instructing the compiler to use Java 17 source if the syntax only exists in Java 21.

In large programs, compilation phases also include collecting symbols, resolving types, and generating lower-level representations. Do not treat the lexer, parser, and AST as the entire compilation process.

## 8. Common Misconceptions

1. **"Spaces have no meaning in Java."** Whitespace usually does not become a token, yet can separate two lexemes: **int value** differs from **intvalue**. Inside a string literal, spaces are also data of the literal.
2. **"Every space-separated word is a token."** Operators such as **>=**, **++** can be one token; the string **"hello world"** contains a space yet is a single literal token.
3. **"The lexer knows which expression must multiply first."** The lexer only recognizes the **+**, **\*** tokens; the parser applies precedence/associativity to build the tree.
4. **"The AST preserves the original source code."** The AST describes structure; it does not guarantee preserving spaces, comments, parenthesization choices, or all formatting details.
5. **"As long as an AST is built, the Java code is valid."** Name resolution, type checking, accessibility, definite assignment, and other constraints still remain.
6. **"Unicode escapes only work inside strings."** They are processed very early in the source character stream, including regions that look like comments or keywords.
7. **"The longest token always explains every context."** The JLS has exceptions to handle contextual keywords and **>** characters in generic types.
8. **"Any Unicode whitespace-like character is ignored by the Java lexer."** The JLS specifies exact white-space input elements; do not substitute editor rules or general-purpose whitespace-checking functions.
9. **"Tokens and ASTs are the same because both are compiler objects."** Tokens are linear lexical units; the AST is a structural tree.
10. **"com.sun.tools.javac.* can be used as a long-term public API."** This is an internal implementation group; distinguish it from the Java Compiler Tree API provided through **com.sun.source.tree**.

## 9. Self-Practice Exercises

**Exercise 1 — Count and classify tokens.** Given the statement:

~~~java
boolean ready = value >= 10 && value != 20;
~~~

Label each **keyword**, **identifier**, **literal**, **operator**, and **separator** yourself. Note that **>=**, **&&**, and **!=** are each a single operator token, not separate tokens.

**Exercise 2 — Build ASTs by hand.** Draw two trees for:

~~~java
int a = 5 + 2 * 3;
int b = (5 + 2) * 3;
~~~

Then run a valid Java program to confirm **a = 11**, **b = 21**. Explain which operation node sits at the root of each initializer.

**Exercise 3 — Find the phase causing the error.** Classify the three code fragments:

~~~java
String a = "missing;
int b = ;
int c = "ok";
~~~

Identify respectively the literal error, grammar error, and type error. These lines are intentionally invalid; do not combine them into a runnable example.

**Exercise 4 — Explore the Tree API.** Change the source string in **InspectAst.java** to:

~~~java
class Example { int answer = (2 + 3) * 4; }
~~~

Predict **initializer.getKind()** before running. Then try printing child nodes to see how the parser retains parentheses using the **PARENTHESIZED** structure. Do not force-cast initializer to an addition BinaryTree as in the original example if the new structure differs; check the kind before casting.

**Exercise 5 — Check token boundaries.** Explain why **a - -b** differs from **a--b** and why **int number** differs from **intnumber**, even though very few characters changed.

## 10. Check Your Knowledge

- Why does the compiler need to read the file's encoding before processing Unicode escapes?
- In what order do the three lexical input translation steps in the JLS take place?
- Do whitespace/comments become tokens participating in the grammar? When does whitespace affect token boundaries?
- Why does the **+** in **"2 + 3"** not become an operator token?
- What does the maximal munch rule explain in **a--b**?
- When do errors occur in lexical analysis, parsing, or semantic analysis?
- Why does the AST of **2 + 3 * 4** have addition outside multiplication?
- Why do source code formatting tools usually need to keep additional information alongside the AST?
- What does **JavacTask.parse()** allow observing, and why does that not mean type checking is complete?

## 11. Standard References

- **Java Language Specification (JLS) – Chapter 3, Lexical Structure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html
- **JLS – Chapter 19, Syntax:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-19.html
- **Java SE 21 – Compiler Tree API (com.sun.source.tree):** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- **Java SE 21 – JavacTask:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- **Java SE 21 – javac tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Remember:** Source code begins as decoded characters; Java applies specific character translation rules, the lexer recognizes tokens, and the parser combines them according to the grammar into an AST. **Tokens answer "what components appear?"; the AST answers "what program structure do they form?"** Both are the foundation for subsequent semantic checks and bytecode generation.