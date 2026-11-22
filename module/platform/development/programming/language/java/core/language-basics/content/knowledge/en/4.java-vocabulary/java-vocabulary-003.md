# Reserved Keywords and Contextual Keywords in Java 17

In Java, not every English-looking word can be used as a variable or class name. Some words have a **fixed** meaning in the language; others only have a special role in **specific syntactic constructs**.

For example, `class` is always a reserved keyword, whereas `module` can be a normal variable name outside module syntax. Distinguishing these two groups accurately helps you choose valid names, read Java 17 code, and understand `javac` error messages.

**Objective:** identify reserved keywords, contextual keywords, literals, and regular identifiers; write/run an example combining `var`, `record`, `yield`, and `sealed`; and fix naming errors.

## 1. Four easily confused categories

| Category | Java 17 examples | Important rule |
| --- | --- | --- |
| **Reserved keyword** | `class`, `int`, `public`, `return`, `if`, `switch` | Cannot be used as a regular identifier, regardless of position |
| **Contextual/restricted keyword** | `var`, `record`, `yield`, `sealed`, `permits`, `non-sealed`, `module`, `requires` | Only carry special meaning in contexts defined by Java; each word has its own restrictions |
| **Literal** | `true`, `false`, `null` | **Not keywords**, yet still cannot be used as variable/class names |
| **Regular identifier** | `score`, `main`, `String`, `System` | Programmer-declared names or API names, subject to naming rules and scope |

`String` is a **class**, not a primitive type keyword like `int`. `main` is a method name by entry-point convention, also not a keyword. Java is case-sensitive: `Class` is not the `class` token, though choosing the name `Class` easily causes confusion and is usually not worth doing.

## 2. Reserved keywords: prohibited as names in any identifier context

Common groups:

| Group | Keywords | Example usage |
| --- | --- | --- |
| Declaration and access | `class`, `interface`, `enum`, `public`, `private`, `protected` | Define types, specify access scope |
| Control flow | `if`, `else`, `for`, `while`, `switch`, `case`, `break`, `continue`, `return` | Branching, looping, terminating |
| Primitive types | `boolean`, `byte`, `short`, `int`, `long`, `char`, `float`, `double` | Declare primitive data |
| Objects and inheritance | `new`, `this`, `super`, `extends`, `implements`, `instanceof` | Object creation, access, type relationships |
| Exceptions | `try`, `catch`, `finally`, `throw`, `throws` | Handle and declare exceptions |
| Other member/behavior modifiers | `static`, `final`, `abstract`, `void`, `synchronized`, `volatile`, `transient`, `native`, `strictfp` | Define how members and types are used |
| Code organization | `package`, `import`, `default`, `do`, `assert` | Packages, type imports, corresponding syntax |

These are **illustrative example groups**, not a list ordered as they appear in the Java specification. The two words `const` and `goto` are also **reserved** even though Java does not use them as statements. A standalone underscore `_` **cannot** serve as an identifier since Java 9; however, `_value` remains a valid identifier in Java 17.

The following lines **intentionally do not compile**:

~~~java
int class = 3;       // Invalid: class is a reserved keyword.
int return = 5;      // Invalid: return is a reserved keyword.
int _ = 1;           // Invalid in Java 17: _ is reserved.
int true = 2;        // Invalid: true is a literal, not an identifier.
~~~

Rename them to express the value's meaning:

~~~java
int classSize = 3;
int returnCount = 5;
int _value = 1;
boolean enabled = true;
~~~

**Note:** `true`, `false`, and `null` are literals (`boolean`/null literals) and *do not belong to the keyword group*, yet using them as identifiers is still invalid. "Not a keyword" does not mean "usable as a name".

## 3. Contextual keywords: syntactic position determines meaning

Java 17 has words that are only treated as special syntactic elements in the appropriate context:

| Word | When it has special meaning | Outside that context |
| --- | --- | --- |
| `var` | Infers the type of a local variable from its initializer expression | Can use `var` as a **variable name**, but not as a type name because it is a *restricted type name* |
| `record` | Declares a record, e.g., `record Point(int x, int y) {}` | Can use `record` as a regular variable name |
| `yield` | Returns a value from a block inside a `switch` expression | Can be a variable name; certain uses as an unqualified method call name are restricted |
| `sealed`, `permits` | Declares a sealed type and the types permitted to extend/implement it | Not automatically banned as variable names everywhere |
| `non-sealed` | Allows a direct subtype of a sealed type to reopen inheritance | This is a special hyphenated form; **not** a regular identifier |
| `module`, `open`, `requires`, `exports`, `opens`, `to`, `uses`, `provides`, `with`, `transitive` | Module declaration syntax in `module-info.java` | Many of these can still be used as identifiers in regular Java code |

Some Java specification terminology distinguishes *contextual keywords*, *restricted keywords*, and *restricted identifiers/type names*. When learning, the key takeaway is not that they share one identical prohibition rule, but that **each word has its own allowed and restricted positions**.

### Example 1: `var` does not make Java a dynamically typed language

~~~java
var total = 12;       // The compiler infers total has type int.
total = 15;           // Valid.
// total = "muoi lam"; // Invalid: String cannot be assigned to int.

int var = 7;          // Valid in Java 17: var is a variable name.
~~~

`var` is used for **local variable type inference**, not a "hold-any-value" type. The following snippets are invalid:

~~~java
// var x = null;     // Cannot infer type from null.
// var x;            // No initializer to infer type.
// class var {}      // Invalid: var is a restricted type name.
~~~

Naming a variable `var` is valid, though it easily misleads readers; you should choose names based on data meaning.

### Example 2: `record` and `yield` are only special when used in their syntax

~~~java
record Point(int x, int y) {} // Java 17: record type declaration.

int record = 5;                // Valid: regular variable name.
~~~

A `switch` expression can use `yield` inside a block to supply a value:

~~~java
int score = 8;
String result = switch (score) {
    case 0 -> "Chua hoc";
    default -> {
        yield score > 0 ? "Da hoc" : "Khong hop le";
    }
};
~~~

Here, `switch`, `case`, and `default` are reserved keywords; `yield` carries special meaning inside the block of a `switch` expression. Do not treat `yield` like `return` for the whole method: it returns a value for the **switch expression**, without automatically terminating the enclosing method.

### Example 3: `sealed` controls subtypes

~~~java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}

record Failure(int code) implements Result {}
~~~

`Result` is a sealed interface; only the permitted subtypes may directly implement it. Both records above are implicitly `final`, satisfying the requirement for directly permitted subtypes. When a branch needs to allow further inheritance, Java also provides the `non-sealed` modifier for an appropriate direct subtype.

Do not try to use `non-sealed` as a variable name with a `-`: the hyphen here is part of a special syntax, not an arbitrary valid character in an identifier.

## 4. Runnable Java 17+ program: compare directly in code

Create a file **`KeywordContextDemo.java`**:

~~~java
public class KeywordContextDemo {
    record Session(String title, int minutes) {}

    sealed interface Outcome permits Good, Bad {}

    record Good(String message) implements Outcome {}

    record Bad(int code) implements Outcome {}

    static String label(int minutes) {
        return switch (minutes) {
            case 0 -> "chua hoc";
            default -> {
                yield minutes > 0 ? "da hoc" : "gia tri am";
            }
        };
    }

    public static void main(String[] args) {
        int module = 2;  // module is a valid variable name here.
        int record = 3;  // record is a valid variable name here.

        var session = new Session("Java", 45);
        Outcome outcome = new Good("ok");

        System.out.println("module=" + module);
        System.out.println("record=" + record);
        System.out.println(
                "session=" + session.title() + ":" + session.minutes());
        System.out.println("label(0)=" + label(0));
        System.out.println("label(3)=" + label(record));
        System.out.println(
                "outcome=" + outcome.getClass().getSimpleName());
    }
}
~~~

**Explanation:** `record Session` declares a record; `int record = 3` uses the same character sequence as a variable name in a different context. `var session` infers type `Session`. `yield` supplies a value for the `switch` expression. `sealed` and `permits` set boundaries on the subtypes of `Outcome`. `module` is a variable name, not a module declaration.

### Compiling and running (Windows PowerShell or Linux/Bash)

Save source as UTF-8, open a terminal in the file's directory, and verify JDK 17+:

~~~bash
java -version
javac -version
~~~

Then use the same commands in both environments:

~~~bash
javac --release 17 -encoding UTF-8 KeywordContextDemo.java
java KeywordContextDemo
~~~

**Expected output:**

~~~text
module=2
record=3
session=Java:45
label(0)=chua hoc
label(3)=da hoc
outcome=Good
~~~

`--release 17` instructs the compiler to support Java 17 syntax and platform APIs. If you are already using JDK 17, `javac -encoding UTF-8 KeywordContextDemo.java` alone is also sufficient for this example.

One benefit of this program is that it **requires no custom packages, modules, or external libraries** to observe the difference between contexts.

## 5. Why do words in `module-info.java` look like keywords?

Java's module system has dedicated syntax for the module declaration file. Example **illustrating syntax**, not a complete project:

~~~java
module learning.demo {
    requires java.logging;
}
~~~

Inside `module-info.java`, `module` and `requires` are syntactic elements of a module declaration. Yet in regular programs, `int module = 2;` remains valid. Do not put this module snippet inside the `KeywordContextDemo` class: that is a **different syntactic position** and requires a correspondingly structured module project.

This example is only meant to recognize *context*. Organizing the module path, packaging modules, and `requires` are outside the scope of this lesson on Java vocabulary.

## 6. Common compile errors and fixes

| Code snippet / situation | Error category or confusion | How to resolve |
| --- | --- | --- |
| `int class = 1;` | `class` is a reserved keyword | Rename to `classCount` |
| `int _ = 1;` | `_` is reserved in Java 17 | Rename to `_count` or `count` |
| `int true = 1;` | `true` is a literal, not an identifier | Use `boolean enabled = true;` |
| `class record {}` | `record` is restricted as a type name | Rename the class, e.g., `RecordExample` |
| `var value = null;` | Cannot infer type | Use an explicit type if null is a valid value |
| `var number;` | No initializer | Initialize at declaration or choose an explicit type |
| `yield 1;` outside an allowed context | `yield` is not a general value-returning statement | Use `return` in a method or `yield` in a proper switch expression |
| `non-sealed` on a class unrelated to a sealed hierarchy | Invalid modifier in that position | Only use on a direct subtype of a sealed type when rules are met |

**Distinction:** a misplaced keyword can lead to a **syntax error**; a restricted type name can lead to a **declaration error**; `var` failing type inference usually leads to a **type error**. Specific `javac` messages vary by version, so focus on code structure and context.

## 7. Practice exercises

**Exercise 1 — Classification:** Among `class`, `record`, `main`, `true`, `var`, `int`, `String`, and `null`, group them into reserved keywords, contextual/restricted keywords, literals, and regular identifiers/API names.

*Answer:* Reserved: `class`, `int`. Contextual/restricted: `record`, `var`. Literals: `true`, `null`. Regular/API names: `main`, `String`.

**Exercise 2 — Prediction:** Why does `int module = 2;` run while `int class = 2;` fails to compile?

*Answer:* `module` has special meaning in the context of a module declaration, whereas `class` is always a reserved keyword.

**Exercise 3 — Triggering an error:** In `KeywordContextDemo.java`, temporarily add `int return = 1;` inside `main`, compile, read the message, and then remove the invalid line. Can `returnCount` be used instead?

*Answer:* Yes, `returnCount` is a valid identifier; `return` is not.

**Exercise 4 — Modifying switch:** Also call `label(-1)` and predict the result. Explain why `yield` in the `default` branch can return a result to the variable/call enclosing the `switch` expression.

*Answer:* Returns the string `gia tri am`. `yield` supplies the value of the `switch` expression.

**Exercise 5 — Do not confuse keywords with API names:** Why are `String`, `System`, `println`, and `main` not keywords, even though they appear frequently in Java programs?

*Answer:* They are library or convention-based type/method names, not reserved syntactic tokens of the language. Using them must respect declarations, scope, and types.

## Memory checklist

- [ ] Identify reserved keywords such as `class`, `if`, `return`, and `int`.
- [ ] Do not use `true`, `false`, `null`, or `_` as identifiers.
- [ ] Explain why `var` only infers types in permitted positions while variables remain statically typed.
- [ ] Distinguish `record` used for a type declaration from `record` as a variable name.
- [ ] Know that `yield` has special meaning inside a `switch` expression.
- [ ] Recognize `sealed`, `permits`, and `non-sealed` without mistaking them for unrestricted names.
- [ ] Know that `module`, `requires`, and related words belong to module declaration context.
- [ ] Compile and run the example using `javac --release 17` and `java`.

**Key takeaway:** **Reserved** keywords are locked out of every identifier position; **contextual** keywords only carry special syntactic meaning in appropriate constructs and have specific restrictions. `true`/`false`/`null` are literals, not keywords, yet are not valid names either. When unsure, examine the **syntactic context** and test-compile a minimal Java 17 example.
