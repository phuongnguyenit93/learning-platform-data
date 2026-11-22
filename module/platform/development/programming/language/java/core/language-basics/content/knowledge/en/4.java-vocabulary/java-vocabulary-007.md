# Single-Line, Multi-Line, and Documentation Comments in Java

## 1. Three types of comments to distinguish

A **comment** is text intended for human readers of source code. In Java 17+, you will encounter three main forms:

| Form | Syntax | Scope | Common purpose |
|---|---|---|---|
| Single-line comment | `// content` | From `//` to the end of the line | Explain a brief decision, warn about a case |
| Block comment | `/* content */` | From `/*` to `*/`, may span multiple lines | Short multi-line explanation, internal notes |
| Documentation comment | `/** content */` | A special block recognized by the Javadoc tool | Document APIs: classes, methods, parameters, return values, exceptions |

In regular Java programs, **comment content is not a statement for the JVM to execute**. The compiler processes comment markers while parsing source code; their content does not become runtime program logic. The **`javadoc`** tool can read documentation comments to generate HTML pages.

Visual comparison example:

~~~java
int price = 100; // Explanation right after the statement

/* This is a block comment
   spanning multiple lines. */

/**
 * This is a documentation comment.
 * Usually placed before the declaration to be described.
 */
class Product {
}
~~~

**Core rule:** use comments to explain **why** the code is written that way, conditions, or API contracts; do not restate every assignment or every semicolon that the code already makes obvious.

## 2. Single-line comments: `//`

Starting from two consecutive slashes outside a character/string literal, the remainder of the **source line** is treated as a comment.

~~~java
int minimumAge = 18;
int userAge = 17;

// Business rule: people under 18 are not allowed to register.
boolean eligible = userAge >= minimumAge;
System.out.println(eligible); // false
~~~

If a line has a statement before `//`, the statement **is still executed**; only the part after `//` is a comment. Two appropriate ways to use it:

- Place the comment on **its own line above** the code block when explaining a rule.
- Place the comment at the **end of the line** when it is genuinely brief and does not hurt readability.

Example of a redundant comment to avoid:

~~~java
int total = 10; // Assign value 10 to total
~~~

The value is already clear from the code. More useful information would be the reason for using 10, problem constraints, or the unit of measurement.

**A `//` comment does not extend to the next line**:

~~~java
int a = 1; // this line only
int b = 2; // statement on the next line still runs
~~~

## 3. Multi-line comments: `/* ... */`

A block comment begins at `/*` and ends at the **first matching `*/` pair** during Java's character scanning. It can fit on a single line or span multiple lines.

~~~java
/*
 * Demo formula:
 * subtotal = quantity × unit price.
 * All data are non-negative integers.
 */
int quantity = 3;
long unitPrice = 120_000L;
long subtotal = unitPrice * quantity;
System.out.println(subtotal); // 360000
~~~

A block comment can also be placed between certain tokens where syntax allows:

~~~java
int result = 2 /* keep illustrative multiplication */ * 3;
System.out.println(result); // 6
~~~

Inserting comments inside expressions too often makes code hard to read. In practice, block comments are usually written as a separate paragraph.

### Block comments **do not nest**

This is a common mistake:

~~~java
/* Outer block
   /* Inner block */
   the rest here is not a comment
*/
~~~

The first `*/` closes the outer block. The remaining text will be treated by Java as source code and may cause a compile error. Java **does not support nested block comments**. When you need two independent explanations, use two separate blocks or `//` lines.

A block missing `*/` also causes a compile error, such as an *unclosed comment* message. If the editor highlights the entire rest of the file as a comment, check for the closing delimiter.

## 4. Documentation comments: `/** ... */`

A **Javadoc comment** starts with `/**` and ends with `*/`. The content inside typically describes **the declaration immediately following the comment**, such as a public class or public method.

~~~java
/**
 * Simple calculations used in examples.
 */
public class Calculator {

    /**
     * Adds two integers and detects overflow.
     *
     * @param a the first addend
     * @param b the second addend
     * @return the sum of a and b
     * @throws ArithmeticException if the addition overflows the int range
     */
    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

The opening section is the **description**. Lines starting with `@` in a documentation comment are **Javadoc block tags**, such as `@param`, `@return`, and `@throws`.

The leading `*` on each content line is a **familiar formatting style**, not Java multiplication; `javadoc` understands the structure of documentation comment blocks.

### Commonly used tags

| Tag | Meaning | When to use |
|---|---|---|
| `@param name` | Meaning of a parameter; `name` must match the parameter name | Methods/constructors with parameters |
| `@return` | Return value/result | Methods that return a value; do not use to describe a `void` method's result |
| `@throws Type` | Condition under which an exception can be thrown | APIs with error behaviors that need explanation |
| `@since` | Version since the API has existed | Stable APIs or versioned libraries |
| `@see` | Reference to related documentation | Readers need to inspect another type/method |
| `@deprecated` | Explains an API that should no longer be used | Usually paired with the `@Deprecated` annotation |
| `{@code ...}` | Displays a code snippet inside a description | E.g. `{@code count > 0}` |
| `{@link Type}` | Creates a link to a recognized documentation element | When pointing to a related API |

The two forms with `{@...}` are **inline tags**, which can appear mid-sentence; `@param` and `@return` are **block tags**, each usually starting on its own line in the Javadoc comment.

**A documentation comment is not an annotation.** `@Deprecated` placed **in code** is an annotation; `@deprecated` **inside Javadoc** is a descriptive tag. Merely adding `@deprecated` text in Javadoc does not automatically replace all effects of the `@Deprecated` annotation.

## 5. Complete Java 17 example: code, comments, and Javadoc

Create a file named **`CommentDemo.java`**, saved as UTF-8:

~~~java
/**
 * Demonstrates the three forms of comments in Java.
 *
 * <p>Example calculating an order total in whole VND units.
 *
 * @since 1.0
 */
public final class CommentDemo {
    private CommentDemo() {
        // Do not instantiate a utility-only class.
    }

    /**
     * Calculates the order total using overflow-checked multiplication.
     *
     * @param quantity item count, must be non-negative
     * @param unitPrice unit price in whole VND, must be non-negative
     * @return total amount in VND
     * @throws IllegalArgumentException if inputs are negative
     * @throws ArithmeticException if multiplication overflows long
     */
    public static long total(int quantity, long unitPrice) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("Gia tri am");
        }

        /*
         * Use multiplyExact so we do not silently return
         * an incorrect amount due to integer overflow.
         */
        return Math.multiplyExact((long) quantity, unitPrice);
    }

    /**
     * Program entry point.
     *
     * @param args command-line arguments; unused by demo
     */
    public static void main(String[] args) {
        long result = total(3, 120_000L);
        System.out.println("Tong: " + result); // 360000

        // Comment-like markers inside strings are still string content.
        String url = "https://example.com/items";
        String marker = "/* khong phai comment */";
        System.out.println("URL: " + url);
        System.out.println("Marker: " + marker);
    }
}
~~~

### Compiling and running on JDK 17+

Open a terminal in the directory containing `CommentDemo.java`.

**Bash (Linux/macOS):**

~~~bash
javac -version
javac --release 17 -encoding UTF-8 CommentDemo.java
java -cp . CommentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac -version
javac --release 17 -encoding UTF-8 .\CommentDemo.java
java -cp . CommentDemo
~~~

Output of the `java` command:

~~~text
Tong: 360000
URL: https://example.com/items
Marker: /* khong phai comment */
~~~

Single-line, block, and Javadoc comments **are not printed**. The `//`, `/*`, and `*/` characters inside **string literals** are printed as ordinary characters because they are inside strings.

**What to recognize:** the comment explains the intent behind using `Math.multiplyExact`, yet it is **the method call itself** that detects overflow. Writing a comment "overflow handled" while the code only multiplies with ordinary `*` will not make the program any safer.

## 6. Generating HTML documentation with the javadoc tool

The JDK includes not only `javac` and `java`, but also **`javadoc`**. This tool reads documentation comments and declaration information to generate API pages.

From the directory containing the sample file, run:

**Bash:**

~~~bash
javadoc -quiet -encoding UTF-8 -docencoding UTF-8 \
  -charset UTF-8 -d docs CommentDemo.java
~~~

**PowerShell (single line):**

~~~powershell
javadoc -quiet -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs .\CommentDemo.java
~~~

A **`docs`** folder is created to store the HTML files. For a public class in the default package as in this example, the class's documentation file is usually:

~~~text
docs/CommentDemo.html
~~~

You can verify the file exists:

**Bash:**

~~~bash
ls docs/CommentDemo.html
~~~

**PowerShell:**

~~~powershell
Test-Path .\docs\CommentDemo.html
~~~

`Test-Path` returns **`True`** if the file exists. You can open the HTML file in a browser to inspect the class description, the `total` method, its parameters, return value, and the exceptions documented in Javadoc.

**Do not rely on exact verbatim output from the `javadoc` command**, because message line counts, DocLint warnings, and generated file lists can vary by JDK/options. The main verification criteria are that the command exits successfully and the HTML documentation is generated properly.

If the public API documentation omits a method or field, check the element's **visibility** and `javadoc` options. By default, the tool does not necessarily list every private member. You can use `javadoc -private ...` if you genuinely need documentation for private members for internal purposes.

## 7. Comments in the right place and for the right goal

### Documentation comments for APIs; regular comments for local explanations

A documentation comment should be placed **immediately before the declaration it describes**:

~~~java
/**
 * Calculates the area of a rectangle.
 *
 * @param width non-negative width
 * @param height non-negative height
 * @return area in square units
 */
static long area(long width, long height) {
    if (width < 0 || height < 0) {
        throw new IllegalArgumentException("Negative size");
    }
    return Math.multiplyExact(width, height);
}
~~~

If a piece of code only needs to explain a local decision, such as why an algorithm was chosen or a performance constraint, `//` or `/* ... */` is usually more appropriate.

**Javadoc does not enforce contracts.** `@param width non-negative width` does not make the JVM reject negative numbers; the method needs proper validation or the caller must guarantee preconditions by design. Documentation must **match actual behavior**.

### Describe *why*, do not duplicate *what*

Less useful:

~~~java
quantity++; // Increment quantity by 1.
~~~

More useful when there is a clear rule:

~~~java
// Only increment after checking there is sufficient stock in inventory.
quantity++;
~~~

The example above still needs **actual inventory-checking code** in the right place; a comment does not substitute for enforcing a rule.

## 8. Lexical traps related to comment markers

### 8.1. Comment markers in strings/chars/text blocks are not comments

~~~java
String website = "https://example.org";  // Contains // inside the string
String marker = "/* sample */";          // Contains /* */ inside the string
char slash = '/';
~~~

Content inside a string literal or character literal is recognized as **literal characters**, not comment openers. For Java 17 **text blocks** (`"""`), the same rule applies: `//` or `/* ... */` inside a text block's content do not create comments.

### 8.2. Do not rely on comments to "disable" code long-term

Snippets like:

~~~java
// sendEmail(customer);
~~~

can be helpful during brief testing, yet keeping commented-out code long-term makes programs hard to read and creates ambiguity about functionality. It is better to delete unused code (version control preserves history), or use explicit conditions/configuration if behavior genuinely needs toggling.

### 8.3. Watch out for Unicode escapes in Java source

Java processes **Unicode escapes** at a very early stage of reading source code, **before lexically identifying comments and string literals**. Thus, character sequences that look like comments containing special escape forms might not be parsed the way you expect. Do not rely on comments to hide syntactically meaningful Unicode escapes; when in doubt, inspect the actual source code and test-compile with the target JDK.

### 8.4. Comments can hide errors when deleting/expanding code

An unclosed `/*` can put many subsequent lines inside a comment or trigger an `unclosed comment` error. A stray `*/` outside a comment usually causes a syntax error. Watch your editor's syntax highlighting and verify matching delimiters.

## 9. Javadoc: common documentation mistakes

| Issue | Why it is bad | How to fix |
|---|---|---|
| Writing `@param name` when the method has parameter `userName` | Tag does not match declaration | Use the exact parameter name |
| Method returns `int` but `@return` describes the wrong unit | API callers easily misunderstand | State the exact result and unit |
| Method can throw an exception but docs omit the condition | Hard to use the API safely | Add `@throws` with the specific condition |
| Writing `<` directly in doc text meant to display as code | May be parsed as HTML markup | Use `{@code x < 10}` or appropriate escaping |
| Writing only `/** TODO */` on every method | Fails to describe the actual contract | Write useful content or remove unnecessary comments |
| Changing a method signature without updating Javadoc | Stale docs, may trigger warnings | Update tags and examples together |
| Treating Javadoc as a validation mechanism | Comments are not executed | Write checks in code and tests |

**Do not confuse** `/** ... */` with `/* ... */`: both are block comments, yet `/**` placed before a declaration is processed by the Javadoc tool as API documentation. A Javadoc comment without a matching declaration right after it does not attach documentation to the intended element.

## 10. Practice distinguishing the three types

Consider this code:

~~~java
/**
 * Converts a length from meters to centimeters.
 *
 * @param meters non-negative number of meters
 * @return number of centimeters
 * @throws IllegalArgumentException if input is negative
 */
static long toCentimeters(long meters) {
    if (meters < 0) {
        throw new IllegalArgumentException("Negative meters");
    }
    // 1 meter = 100 centimeters.
    return Math.multiplyExact(meters, 100L);
}

/* Used in a simple runnable example:
   toCentimeters(3) => 300 */
~~~

Answer on your own:

1. Which part is a single-line comment?
2. Which part generates documentation content for the method?
3. Which part is a regular block comment?
4. When calling `toCentimeters(3)`, are any comments printed?

**Answer:** the line `// 1 meter...` is a single-line comment; the `/** ... */` block is the Javadoc for `toCentimeters`; the `/* Used ... */` block is a regular block comment. No comments are printed by calling the method; the method returns the number `300`.

## 11. Exercises with answers

### Exercise A — choose the right comment style

You want to write a brief explanation for a rule on the next line; write a multi-line internal note; and publish the contract of a method taking two parameters.

**Answer:** respectively use `//`, `/* ... */`, and `/** ... */` with `@param`, `@return` (if returning a value), and `@throws` (when needed).

### Exercise B — fix an unclosed comment

Snippet:

~~~java
int a = 1;
/* explanation
int b = 2;
~~~

**Answer:** add `*/` at the proper end of the comment. If `int b = 2;` needs to execute, place it **after** `*/`.

### Exercise C — predict the output

~~~java
int x = 3 /* still inside the calculation */ + 2;
String s = "http://localhost";
System.out.println(x);
System.out.println(s);
~~~

**Answer:**

~~~text
5
http://localhost
~~~

`/* ... */` does not remove the `+` operator outside the comment; `//` inside the URL string does not start a comment.

### Exercise D — write a complete Javadoc contract

Given:

~~~java
static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("Zero denominator");
    }
    return numerator / denominator;
}
~~~

Write a documentation comment stating both parameters, the result, and the error condition.

**Suggested answer:**

~~~java
/**
 * Divides two integers according to Java integer division rules.
 *
 * @param numerator the dividend
 * @param denominator the divisor, must be non-zero
 * @return integer quotient, truncated toward 0
 * @throws IllegalArgumentException if denominator is 0
 */
~~~

Note: `Integer.MIN_VALUE / -1` is a special case yielding `Integer.MIN_VALUE` per int overflow rules; more detailed docs should mention this if the application contract requires different handling.

### Exercise E — generate and inspect HTML

Using `CommentDemo.java` from section 5, run `javadoc`, then open `docs/CommentDemo.html`. Locate the documentation for `total`, and verify the descriptions for `quantity`, `unitPrice`, `@return`, and `@throws`.

**Expected answer:** the API page contains the method description and corresponding Parameters/Returns/Throws sections (layout varies by JDK). If the file is not generated, check the command output, current working path, and DocLint warnings before concluding the source content is wrong.

## 12. Self-assessment checklist

- [ ] Identify the three syntaxes `//`, `/* ... */`, and `/** ... */`.
- [ ] Understand that `//` ends at the end of the line and block comments must be closed with `*/`.
- [ ] Know that block comments **do not nest**.
- [ ] Understand that `//` and `/* ... */` inside strings do not become comments.
- [ ] Know that Javadoc comments are for API documentation, not executable statements.
- [ ] Write `@param`, `@return`, and `@throws` matching the method signature/contract.
- [ ] Distinguish the Javadoc `@deprecated` tag from the `@Deprecated` annotation.
- [ ] Compile/run `CommentDemo.java` with `javac`/`java` and verify the output.
- [ ] Use `javadoc -d docs` to generate and inspect HTML documentation.
- [ ] Write comments explaining decisions, rules, and constraints, rather than repeating what the code already says.

**Conclusion:** `//` fits brief comments; `/* ... */` fits block comments; `/** ... */` fits API documentation generated with `javadoc`. Comments help readers understand code yet **do not alter JVM behavior**. A good comment must match the current code, state intent clearly, and be updated whenever behavior changes.