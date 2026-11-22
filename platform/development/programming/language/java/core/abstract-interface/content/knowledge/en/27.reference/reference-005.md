# Looking Up the Java Language Specification and Javadoc by Topic

When you need to verify a Java rule, start by determining whether the question pertains to the **Java language** or **a specific API**. The Java Language Specification (JLS) describes the syntax and semantics of the language; the Java SE API Javadoc describes the usage contract of library classes, interfaces, constructors, fields, and methods. The two sources complement each other but answer different kinds of questions.

## 1. Choosing the Right Source

| Question to answer | Source to check first | Example topics |
| --- | --- | --- |
| Is the source code valid in syntax and types? | JLS | generic types, type conversions, variable scope, method overloading |
| Which method is selected at compile time? | JLS | overload resolution, method invocation, type inference |
| Which instance method is invoked at runtime? | JLS | overriding, dynamic dispatch, class initialization |
| What parameters does a library method accept, what does it return, and what exceptions does it throw? | API Javadoc | `List.get`, `Map.get`, `Files.readString` |
| Is the return value mutable? What happens with `null`? | Javadoc of the specific API | `List.of`, `Optional.of`, `Map.copyOf` |
| How are thread, lock, and memory ordering behaviors specified? | JLS and relevant Javadoc | memory model, `synchronized`, `volatile`, concurrency utilities |
| Which constructors or methods does a class have? | Javadoc of that class | `StringBuilder`, `Path`, `CompletableFuture` |

Language rules and library contracts can appear together in a single issue. For example, the JLS specifies how Java resolves a method call; the Javadoc specifies what the selected library method does, along with the input conditions and exceptions documented in the contract.

## 2. Official Sources to Bookmark

- **Java SE 17 JLS:** https://docs.oracle.com/javase/specs/jls/se17/html/index.html
- **Java SE Specifications Index Page:** https://docs.oracle.com/javase/specs/
- **Java SE 17 API Specification:** https://docs.oracle.com/en/java/javase/17/docs/api/index.html
- **Javadoc for `java.util.List`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html

The links above use Java SE 17 as a reference example. When a project runs Java 21, 25, or another version, open the JLS/API docs corresponding to the version you need to verify. Do not infer that an API present in a newer version also exists in an older version.

## 3. Looking Up the JLS by Topic

The JLS is divided into chapters with specific topics. If you already know the kind of rule you are looking for, open the relevant chapter first and then search for terms on that page.

| Topic | Typically relevant JLS chapter |
| --- | --- |
| Types, values, variables, and generic types | Chapter 4 — Types, Values, and Variables |
| Type conversions, boxing/unboxing, and conversions in contexts | Chapter 5 — Conversions and Contexts |
| Names, scope, access, and name resolution | Chapter 6 — Names |
| Packages and modules | Chapter 7 — Packages and Modules |
| Classes, constructors, methods, overriding, and hiding | Chapter 8 — Classes |
| Interface declarations and members | Chapter 9 — Interfaces |
| Arrays | Chapter 10 — Arrays |
| Exceptions and checked exceptions | Chapter 11 — Exceptions |
| Execution and class/interface initialization | Chapter 12 — Execution |
| Binary compatibility | Chapter 13 — Binary Compatibility |
| Statements, blocks, and control flow | Chapter 14 — Blocks, Statements, and Patterns (depending on version) |
| Expressions, method invocation, lambdas, and operators | Chapter 15 — Expressions |
| Definite assignment | Chapter 16 — Definite Assignment |
| Threads, monitors, synchronization, and memory model | Chapter 17 — Threads and Locks |
| Type inference | Chapter 18 — Type Inference |
| Syntactic grammar | Chapter 19 — Syntax |

Chapter titles and detailed contents may vary across JLS versions. Use the table of contents for the exact version; if you search by a section number such as `15.12`, verify that section number in the version you are reading.

### How to Find a Rule in the JLS

1. Phrase the question as a specific behavior: "Why does this call choose overload A instead of overload B?" or "When does a static initializer run?".
2. Translate the question into language terminology: `method invocation`, `overload resolution`, `class initialization`, `type inference`, or `definite assignment`.
3. Open the appropriate chapter in the JLS and look up the term using in-page search (`Ctrl+F`).
4. Read the entire section containing the definition, the applicable conditions, and any referenced sections; do not rely solely on a single sentence quoted out of context.
5. Compare against a small compilable code snippet. If you are explaining a compile-time error, clearly distinguish conclusions derived from language rules from the specific message reported by the compiler.

Example web queries you can use:

```text
site:docs.oracle.com/javase/specs/jls/se17/html/ "method invocation"
site:docs.oracle.com/javase/specs/jls/se17/html/ "class initialization"
site:docs.oracle.com/javase/specs/jls/se17/html/ "type inference"
```

## 4. Looking Up Javadoc by Class or Method

The Javadoc of an API typically provides:

- **Declaration/signature:** class name, parameter types, return type, modifiers, and generic types.
- **Description:** what the method does and the meaning of its result.
- **Parameters:** conditions or meaning of each argument.
- **Returns:** the return value, including any special cases described.
- **Throws:** which exceptions may or are specified to be thrown and under what conditions.
- **API notes, implementation requirements, or implementation notes:** additional guidance and requirements, if present.
- **Since:** the Java SE version in which the API was added, if the documentation page provides this information.
- **See Also / inherited methods:** links to related concepts or APIs.

When inspecting a method, do not read only the summary description at the top of the page. Find the exact overload by parameter types and read the `Returns`, `Throws`, and related notes sections. Two overloads with the same name can have different conditions or results.

Example queries:

```text
site:docs.oracle.com/en/java/javase/17/docs/api/ "java.util.List" "unmodifiable"
site:docs.oracle.com/en/java/javase/17/docs/api/ "Files.readString"
site:docs.oracle.com/en/java/javase/17/docs/api/ "Optional.of" "NullPointerException"
```

When using a search engine, prioritize results from the official Oracle documentation or the official documentation of the JDK you are using. Blog posts and forum answers are useful for finding keywords or examples, but you should return to the specification/Javadoc to confirm the contract.

## 5. A Repeatable Lookup Workflow

### Step 1 — Narrow Down the Question

Record the minimal code snippet, Java version, observed result, and what needs to be verified. Avoid broad questions like "How does Java work?"; replace them with a verifiable question, for example, "Does `List.of` allow adding elements after creation?".

### Step 2 — Identify the Source Category

- If the question is about code validity, which method is selected, scope, types, or initialization order, start with the JLS.
- If the question is about library behavior, start with the Javadoc of the class/method.
- If both are involved, read both sources and clearly note which source supports which conclusion.

### Step 3 — Lock the Version

Check the source/target version, the JDK used to compile, and the JDK running the program. Open documentation for the same version to avoid relying on APIs or rules added later. If you are investigating version differences, compare two clearly versioned copies of the documentation instead of mixing them.

### Step 4 — Read the Contract, Not Just Examples

Look for conditional terms such as "must", "may", "throws", "unless", "if", "not supported", and edge cases. An example may only illustrate a single case; it is the specification or Javadoc that defines the guaranteed scope of behavior.

### Step 5 — Verify with a Small Program

Compile and run a minimal example when the question can be verified empirically. The execution result helps confirm that the example reproduces the phenomenon, but a single run does not replace the specification: behavior may depend on the version, environment, or parts not guaranteed by the API.

### Step 6 — Record the Conclusion and Basis

Note the source name, version, JLS chapter/section or Javadoc class/method, the relevant rule, and the minimal example. When sharing results in a review or internal documentation, link directly to the exact section rather than simply writing "according to Java documentation".

## 6. Example: Verifying Whether `List.of` Is Modifiable

Question: does a list created with `List.of("Ada", "Lin")` allow calling `add`?

**Source to read:** Javadoc for `java.util.List`, the `of` method section. This is library API behavior, so Javadoc is the direct source for checking the contract. The JLS can explain how the generic call is resolved, but it does not define the specific contract of `List.of`.

A complete Java 17+ example:

```java
import java.util.List;

public class ListOfLookupDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Ada", "Lin");

        try {
            names.add("Grace");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List.of result is unmodifiable");
        }
    }
}
```

Compile and run:

```shell
javac ListOfLookupDemo.java
java ListOfLookupDemo
```

Exact stdout:

```text
List.of result is unmodifiable
```

This example illustrates the expected behavior under the API contract: lists created by `List.of` are unmodifiable, so mutating operations such as `add` throw `UnsupportedOperationException`. Do not generalize that every object implementing `List` is unmodifiable; check how it is created and the contract of each API. In real programs, there is no need to try calling `add` to "test" it if you have already read the documentation and know the contract clearly.

## 7. Distinguishing What Is Guaranteed from What Is Incidentally Observed

When reading a source, classify your conclusions:

- **Specified/guaranteed:** behavior described in the applicable JLS rule or API contract.
- **Unspecified:** the documentation does not commit to a single outcome; avoid depending on that outcome.
- **Implementation-specific:** behavior that comes from a specific compiler/JVM but should not be treated as a general Java rule.
- **Observed from an example:** the actual output of a single run, useful for reproduction but needing cross-checking against the normative source.

Pay special attention to the phrases "unspecified", "implementation-dependent", and "implementation-specific" if they appear in the documentation. They have different meanings; do not interpret all of them as "Java always does this".

## 8. Common Lookup Mistakes

| Mistake | How to avoid |
| --- | --- |
| Using a blog post as the final authority | Use articles to find terminology, then verify in the official JLS or Javadoc. |
| Reading documentation from a different version | Check the JDK version and open the matching documentation version; compare versions intentionally if needed. |
| Looking up the JLS for a library method's contract | Open the Javadoc for the exact class and overload first. |
| Looking up Javadoc to explain general compilation rules | Find the corresponding rule in the JLS, such as overload resolution or conversion. |
| Reading only the method name or short summary | Read the declaration, parameters, returns, throws, and related notes. |
| Mistaking the result of a single compiler for a language rule | Distinguish compiler messages from normative rules in the JLS. |
| Generalizing a single example to an entire API | Identify the exact overload, input conditions, and guaranteed cases. |
| Citing a documentation page generically | Record the version and link to the exact chapter/section or method. |

## 9. Checklist Before Concluding

- [ ] The question has been written as a specific behavior to verify.
- [ ] Language rules have been distinguished from API contracts.
- [ ] Official documentation has been opened and the relevant Java version checked.
- [ ] The main section along with its conditions, exceptions, and related references have been read.
- [ ] If an example is present, the minimal code has been compiled/run or it has been clearly noted why it cannot run standalone.
- [ ] Empirical results have been distinguished from what the documentation guarantees.
- [ ] The conclusion includes a link to the exact JLS section or Javadoc entry so others can verify it.

The most important habit is finding the right source for the right question: **the JLS to verify language rules; Javadoc to verify API contracts**. Pin the version, read the conditions and exceptions, and then verify with a small example when appropriate.
