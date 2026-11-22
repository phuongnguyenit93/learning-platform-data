# Learning Scope of the Java Core Pattern Matching Module

**Knowledge group:** Introduction to pattern matching  
**Audience:** Learners with a Java Core foundation who want to read, write, and maintain type-checking code more clearly.

## 1. What problem does this module solve?

In Java, a program often receives a value with a broad declared type (such as `Object`, an interface, or a superclass) and must determine its actual runtime type to process it. The traditional approach uses `instanceof`, manual casting, and multiple `if/else` branches. As data structures grow more complex, these operations easily lead to repetitive code, missed cases, or variables declared in the wrong scope.

**Pattern matching** lets you match a value against a *pattern*. When the value matches, Java can simultaneously provide type-checked variables for use within the valid scope. With *record patterns*, matching can also deconstruct the components of a `record`. Pattern matching makes intent clearer, but it does not replace every form of polymorphism or every conditional construct.

**Module goal:** understand the stabilized patterns in Java, choose the right construct, handle non-matching branches safely, and apply them to practical Java Core problems.

## 2. Prerequisites and Java versions

Learners should know variable declarations, classes/interfaces, inheritance, `instanceof`, casting, `if/else`, `switch`, methods, and how to compile a `.java` file. Basic knowledge of `record` and `sealed` helps when reading the advanced parts; the module will explain their role in pattern matching.

| Platform | Features in scope | Notes |
| --- | --- | --- |
| Java 17 or later | Pattern matching for `instanceof` | This feature became standard in Java 16; Java 17 is sufficient for learning this part. |
| Java 21 or later | Pattern matching for `switch`, record patterns, `when` guarded branches | The core features covered here are standard in Java 21, without needing `--enable-preview`. |

**Recommended environment:** JDK 21 or newer to run all examples. If you only have JDK 17, study and run the `instanceof` section first; the `switch` examples with type patterns or record patterns below require Java 21. When compiling, use `javac` of the matching version, not just a JRE to run the program.

## 3. What the module covers

### 3.1. Type patterns and `instanceof`

- Distinguish a type check from binding a *pattern variable*: `if (value instanceof String text)` both checks the type and creates the variable `text` of type `String` where valid.
- Understand *flow scoping*: a pattern variable can only be used in places where the compiler knows for certain that the match succeeded. It is not automatically available after every `if` block, in a non-matching branch, or after carelessly combined conditions.
- Compare the pattern-based syntax with `instanceof` followed by an explicit cast; choose the expression that is concise and easy to verify.

### 3.2. Pattern matching for `switch`

- Use type patterns in `case` labels to classify a value by its actual type; understand the difference between a `switch` statement and a `switch` expression.
- Know when `case null` is needed and when `default` is needed; do not assume `default` always handles `null`.
- Use `when` to add a condition to a matched pattern, such as distinguishing a blank string from a string with content.
- Understand **dominance**: placing a general branch first can make a more specific branch after it unreachable and cause a compilation error.
- Understand **exhaustiveness**: a `switch` expression must handle all cases according to the compiler's check; with a closed set of types such as a `sealed` hierarchy, you can list the specific cases instead of an overly broad `default` branch.

### 3.3. Record patterns

- Distinguish declaring a `record` from using a *record pattern* to test and extract its components.
- Read and write examples like `case Point(int x, int y)` to extract the components of `Point` upon matching.
- Recognize basic nested patterns when a record contains another record; weigh readability before nesting too many levels.
- Remember that record patterns target `record` structures and do not automatically deconstruct arbitrary regular Java classes.

### 3.4. Design, limitations, and code quality

- Choose among `if/else`, `instanceof`, `switch`, and polymorphic method calls based on the number of branches, data structure, and extensibility.
- Check for `null` cases, unexpected types, dominated patterns, missing branches, and guard ordering.
- Understand type-checking limitations caused by *type erasure*: you cannot use `instanceof List<String>` to check exact generic element types at runtime; `List<?>` is an example of a pattern that can be checked as a reifiable type.
- Refactor legacy code while preserving business behavior, avoiding the use of pattern matching just to make code look modern.

## 4. Orientation example: a runnable Java 21 program

This example introduces the four main ideas of the module: `instanceof` with a pattern variable, type-based `switch`, `when` guards, and record patterns. It serves as a conceptual map; each mechanism will be studied in detail in dedicated lessons.

Create the file **`PatternMatchingScope.java`**:

```java
public class PatternMatchingScope {
    record Point(int x, int y) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "NULL";
            case String s when s.isBlank() -> "Blank String";
            case String s -> "String: " + s;
            case Point(int x, int y) -> "Point=(" + x + "," + y + ")";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        Object item = "Java";

        if (item instanceof String text) {
            System.out.println("Length=" + text.length());
        }

        System.out.println(describe(new Point(3, 5)));
        System.out.println(describe("   "));
        System.out.println(describe(null));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 PatternMatchingScope.java
java PatternMatchingScope
```

Output:

```text
Length=4
Point=(3,5)
Blank String
NULL
```

Explanation:

1. `item instanceof String text` only allows `text` to be used in the matched branch; the program prints the length of `"Java"`, which is `4`.
2. `case Point(int x, int y)` matches the record `Point(3, 5)` and extracts the two components to produce `Point=(3,5)`.
3. The guard `case String s when s.isBlank()` is checked before the general `case String s`, so a string of three spaces is described as `Blank String`.
4. `case null` handles `null` specifically; `default` handles other values not covered by the patterns.

Try changing the argument to `42`, `"Hello"`, or `new Point(0, 0)` to observe which branch is selected. If you move `case String s` before the `String` branch with `when`, the compiler will detect that the later branch is dominated (unreachable).

## 5. Content boundaries of the module

Within this learning scope, the term **pattern** refers to *the Java language's pattern matching mechanism*. It is **not** synonymous with:

- **Regular expressions:** `java.util.regex.Pattern` and `Matcher` are used to search/match character patterns in strings, which is a different topic.
- **Java Platform Module System (JPMS):** `module-info.java`, `requires`, and `exports` deal with module encapsulation and dependencies, not pattern matching.
- **Reflection, annotation processing, or parsers:** mechanisms for inspecting or transforming program structure at runtime or compile time are outside the introductory goal here.
- **Unstable preview proposals or syntax from other languages:** no preview features need to be enabled to complete the standard Java 21 exercises.

The module also does not aim to replace all object-oriented design with chains of type checks. If behavior belongs to the responsibility of each class and can be solved cleanly with polymorphism, that remains a viable option to consider.

## 6. Learning path and expected level of practice

1. **Identify the problem:** find code that checks a type and then manually casts; explain the duplication and risks.
2. **Master `instanceof` patterns:** rewrite a simple branch, understand the scope of the pattern variable and the non-matching case.
3. **Move to `switch` patterns:** classify multiple types, add `null`/`default`, and recognize dominated branches and missing cases.
4. **Work with `record`:** declare records, match and extract components, and read simple nested patterns.
5. **Apply with verification:** add `when` guards, write test cases for matching/non-matching types and `null`, and compare with polymorphic or traditional conditional solutions.

An exercise is considered complete when the learner can explain **why a branch is selected**, **which variables are in scope at which locations**, and **what happens when a value does not match**, while also compiling and verifying the output.

## 7. Misconceptions to avoid

- Assuming pattern matching eliminates the need to check for `null`. An `instanceof` type pattern does not match `null`; when using `switch`, handle `null` explicitly.
- Thinking that a variable declared in a pattern exists in every branch. Variable scope is governed by Java's flow-scoping analysis.
- Placing a broad pattern before a narrow pattern and being surprised when the compiler reports an unreachable branch.
- Confusing record patterns with arbitrary deconstruction on regular classes, or assuming generic type arguments can always be determined at runtime.
- Copying a Java 21 example into a project using a Java 17 compiler and concluding that Java syntax is broken; always check the JDK version and build configuration.
- Converting `if/else` to `switch` without preserving branch logic, `null` behavior, and return values.

## 8. Self-assessment and further reading

After this orientation lesson, learners should be able to answer: how an `instanceof` pattern differs from manual casting; why `when` must be placed before a broad pattern; what data a record pattern extracts; how exhaustive a `switch` expression must be; and when pattern matching should not be used.

Specification documents for syntax and version boundaries:

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).

**Expected outcome of the module:** read, understand, and write common patterns in Java Core, know how to handle edge cases, and make design choices based on correctness, clarity, and maintainability.