# Distinguishing Annotations, Source Code Comments, and Javadoc in Java

In Java source code, three constructs can appear right next to a class or method:

\`\`\`java
// Explains intent to the reader.
/** Describes the API for Javadoc documentation. */
@Override
public String toString() {
    return "Example";
}
\`\`\`

All three provide additional information, but **they differ in syntax, who uses them, when they are processed, and their ability to affect tools/the program**. Understanding the distinction properly helps you choose the appropriate form of expression and avoid expecting a comment line to check or alter Java behavior on its own.

## 1. The Big Picture

| Criterion | Annotation | Source code comment | Javadoc |
| --- | --- | --- | --- |
| Typical syntax | \`@Override\`, \`@Deprecated\`, \`@MyTag(...)\` | \`// ...\`, \`/* ... */\` | \`/** ... */\` |
| Nature | Structured metadata attached to a Java element or valid type location | Explanatory text in source code | A form of comment with documentation conventions that can contain Javadoc tags |
| Who uses it? | The compiler, annotation processors, frameworks, or reflection-reading code, depending on the annotation type | Human readers and source analysis tools | Human readers, the \`javadoc\` tool, and doc-comment reading tools |
| Executes logic on its own? | No. Only takes effect when a compiler/tool/framework/code knows how to process it | No | No |
| Present in \`.class\`? | Depends on \`@Retention\` and annotation type; not every annotation is present at runtime | No | Regular doc comment content is not included in \`.class\` |
| Retrievable via reflection? | Only when matching \`RUNTIME\` retention and the API/target being read | No | Not through standard reflection APIs |
| Primary purpose | Attach machine-readable and processable information | Explain intent, rationale, and implementation context | Describe the API usage contract for library consumers |

**Key takeaway:** annotations are structured data for programs/tools; comments are explanations in source code; Javadoc is a standardized comment format for building API documentation. Javadoc is still a comment, but it has specialized syntax and processing tools.

## 2. Source Code Comments: Explaining to the Reader

Java has two regular forms of comments:

\`\`\`java
// Single-line comment.

 /*
  * Multi-line comment.
  * Often used to explain a decision or an algorithm section.
  */
\`\`\`

These two forms do not declare Java metadata and do not generate executable code. The compiler ignores comment content when determining the meaning of Java expressions, statements, and declarations. Source analysis tools can still read comments, for example to check conventions or display them in an IDE.

Example:

\`\`\`java
// Disallow negative numbers due to the current business rule.
if (amount < 0) {
    throw new IllegalArgumentException("amount must be non-negative");
}
\`\`\`

The program rejects negative numbers **because of the \`if\` condition and \`throw\` statement**, not because of the comment. If you remove the comment, the logic still runs the same; if you remove the \`if\` condition and keep only the comment, negative numbers are no longer checked.

Comments are most useful when they answer **why** a decision or rule exists, describe a non-obvious invariant, or state a technical limitation worth knowing. You should not write comments that merely repeat exactly what the code already expresses:

\`\`\`java
// Increment i by 1.
i++;
\`\`\`

An outdated comment can be more misleading than having no comment at all. When changing logic, you also need to check the related comments.

## 3. Javadoc: Documentation for the API Contract

Javadoc uses a comment form starting with \`/**\` and is usually placed immediately before a class, interface, constructor, method, or field declaration. The \`javadoc\` tool reads these comments to generate API documentation, typically in HTML format.

\`\`\`java
/**
 * Calculates the remaining amount after subtracting the paid portion.
 *
 * @param total the total amount due
 * @param paid the amount already paid
 * @return the remaining amount, which may be negative if overpaid
 * @throws IllegalArgumentException if total or paid is negative
 */
public static long remaining(long total, long paid) {
    if (total < 0 || paid < 0) {
        throw new IllegalArgumentException("amount must be non-negative");
    }
    return total - paid;
}
\`\`\`

This structure clearly documents **how to use the API**, parameter meanings, return value, and exceptions. It is important to distinguish:

- \`@param\`, \`@return\`, \`@throws\` **inside \`/** ... */\`** are *Javadoc tags*, not Java annotations.
- \`@Override\` or \`@Deprecated\` **outside a comment** are annotations of the Java language.
- \`{@code ...}\` and \`{@link ...}\` are inline Javadoc tags, for example \`{@code null}\` or \`{@link java.util.List}\`.
- Merely writing \`@throws\` does not make a method actually throw an exception; merely writing \`@return\` does not determine the return value. Rules and behavior must be implemented in Java code.

Javadoc can display descriptions when an IDE supports reading source code or attached documentation bundles. To generate HTML, run \`javadoc\` on the corresponding source files; simply typing \`/** ... */\` in code does not automatically generate HTML pages.

### How Does \`@deprecated\` Differ from \`@Deprecated\`?

This is an easy case to confuse because it differs only in capitalization:

\`\`\`java
/**
 * @deprecated Use newApi() instead.
 */
@Deprecated
public void oldApi() {
}
\`\`\`

\`@deprecated\` (lowercase) **is a Javadoc tag** that explains the reason/replacement guidance in documentation. \`@Deprecated\` (uppercase) **is a Java annotation** so tools and the compiler recognize that an element is obsolete; the compiler can emit a warning when users call that API. When declaring a deprecated API, you should combine both so that both tools and readers receive useful information.

## 4. Annotations: Metadata Recognized by Java and Tools

An annotation appears at a syntactic location permitted by Java and must correspond to a declared **annotation type**. Annotations can be attached to classes, methods, fields, parameters, constructors, packages, modules, or type-use locations depending on the annotation's definition.

Example:

\`\`\`java
@Override
public String toString() {
    return "Customer";
}
\`\`\`

\`@Override\` tells the compiler to verify that the method actually overrides/implements a matching method from a supertype. If you mistype the method name, the compiler reports an error.

\`\`\`java
class Parent {
    void process() {}
}

class Child extends Parent {
    @Override
    void proccess() {} // Compile error: no matching method to override.
}
\`\`\`

The snippet above is **an intentionally erroneous example**, not a program expected to compile successfully. If you remove \`@Override\`, the new \`proccess()\` method can be treated as a separate method; however, the logic bug from the misspelled name remains. The annotation helps the compiler catch the problem early.

A custom annotation looks like this:

\`\`\`java
@interface ReviewedBy {
    String value();
}
\`\`\`

Usage:

\`\`\`java
@ReviewedBy("team-a")
class InvoiceService {
}
\`\`\`

The string \`"team-a"\` is a metadata value. **Simply declaring or applying \`@ReviewedBy\` does not create any approval check.** For it to take effect, some party must read and process it: an annotation processor at compile time, a framework during configuration, or reflection code at runtime.

### Retention: Until What Stage Does an Annotation Exist?

Java lets you declare a retention policy via \`@Retention\`:

| Policy | Meaning | Runtime Reflection |
| --- | --- | --- |
| \`RetentionPolicy.SOURCE\` | Needed only in source code; the compiler does not keep the annotation in the class file | No |
| \`RetentionPolicy.CLASS\` | Written to the class file, though the JVM is not required to retain it for runtime reflection access; this is the default retention when unspecified | Not via standard reflection |
| \`RetentionPolicy.RUNTIME\` | Written to the class file and accessible via reflection at runtime | Yes, through the appropriate API |

You should not infer retention solely from an annotation's name. Check the \`@Retention\` definition of the specific annotation; for an annotation type that omits \`@Retention\`, the default is \`CLASS\`.

\`@Target\` restricts where an annotation can be used, such as \`ElementType.METHOD\` for methods. \`@Documented\` instructs tools like \`javadoc\` to include that annotation in the documentation of the annotated element. \`@Inherited\` has specific inheritance rules for annotations on classes and does not mean every annotation on a method is automatically inherited.

Annotations are also used in frameworks. For example, \`@Override\` is understood directly by the compiler; annotations like Spring's \`@Transactional\` only carry transactional semantics when the corresponding Spring mechanism is actually enabled and applied. There is no general rule that simply attaching \`@Something\` makes the JVM automatically execute some behavior.

## 5. Java 17+ Example: Placing All Three Side by Side and Observing Runtime

Create **a single file \`DocDemo.java\`** with the complete content below (this is a self-contained example that can be compiled and run):

\`\`\`java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

/**
 * Example-defined annotation to label a method.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {
    String value();
}

/**
 * Demonstrates the difference between annotations, comments, and Javadoc.
 */
public class DocDemo {

    /**
     * Creates a greeting for a person.
     *
     * @param name the name of the person to greet
     * @return a greeting containing the received name
     */
    @Traced("greeting")
    public String welcome(String name) {
        // This line explains intent; it does not exist as runtime metadata.
        return "Xin chào, " + name;
    }

    public static void main(String[] args) throws Exception {
        Method method = DocDemo.class.getDeclaredMethod("welcome", String.class);

        // Reflection reads the annotation because Traced has RUNTIME retention.
        System.out.println(method.isAnnotationPresent(Traced.class));
        System.out.println(method.getAnnotation(Traced.class).value());

        System.out.println(new DocDemo().welcome("An"));
    }
}
\`\`\`

Compile and run with JDK 17 or later:

\`\`\`bash
javac -encoding UTF-8 DocDemo.java
java DocDemo
\`\`\`

Stdout of \`java DocDemo\`:

\`\`\`text
true
greeting
Xin chào, An
\`\`\`

Explanation of the output:

1. \`@Traced("greeting")\` stores a structured value. Thanks to \`@Retention(RetentionPolicy.RUNTIME)\`, reflection finds the annotation on the method and can read \`value()\`.
2. The comment starting with \`//\` describes intent. It does not create an annotation for reflection to query.
3. \`/** ... */\` on the class/method describes the API. That content is not retrieved by \`Method.getAnnotation(...)\`; this is an API for reading annotations, not doc comments.
4. \`@Documented\` on the \`Traced\` type makes Javadoc display annotation information on the annotated element. It **does not turn the Javadoc prose into a runtime annotation**.

Try generating the HTML documentation yourself (this is a separate step from compiling/running):

\`\`\`bash
javadoc -encoding UTF-8 -docencoding UTF-8 -d docs DocDemo.java
\`\`\`

After the command succeeds, you can open \`docs/DocDemo.html\` to view the class/method documentation. The tool may print messages or warnings while generating the pages, depending on the JDK and how complete the documentation is; those lines are **not the stdout of the \`DocDemo\` program**.

### Try Making Changes to Understand the Limits

- Change \`RetentionPolicy.RUNTIME\` to \`RetentionPolicy.SOURCE\`: the Java code can still compile, but \`method.isAnnotationPresent(Traced.class)\` will be \`false\`, and the subsequent call \`method.getAnnotation(Traced.class).value()\` will cause a \`NullPointerException\` because \`getAnnotation\` returns \`null\`. To test safely, check for \`null\` before reading \`value()\`.
- Delete both the \`//\` and \`/** ... */\` comments in the example: the Java program still handles the greeting the same way, but loses the explanation and API documentation.
- Delete \`@Traced("greeting")\`: reflection no longer finds that annotation on the method. This is a metadata change, even though the \`welcome\` method body has not changed.

These experiments clearly show the limits of each mechanism: **comments/Javadoc serve as descriptions; annotations can be read and interpreted by programs/tools according to a specific definition**.

## 6. Why Is an Annotation Not a Special Kind of Comment?

Two constructs can sit next to each other yet be handled very differently by Java:

\`\`\`java
// @Deprecated
public void oldA() {}

/** @deprecated Use another API instead. */
public void oldB() {}

@Deprecated
public void oldC() {}
\`\`\`

- On \`oldA\`, \`@Deprecated\` is just a sequence of characters inside \`//\`; the compiler does not treat the method as deprecated because of this line.
- On \`oldB\`, the Javadoc tag \`@deprecated\` describes the deprecated status in documentation. It is not equivalent to the method having the \`@Deprecated\` annotation attached.
- On \`oldC\`, the compiler sees an actual \`@Deprecated\` annotation; this information can be used by tools to emit warnings.

These are **illustrative methods**, not a standalone complete program. In practice, you should attach \`@Deprecated\` and write a \`@deprecated\` Javadoc tag with replacement guidance for the same API.

Similarly, writing \`// @Override\` or \`/** @Override */\` has no effect on override checking. To have the compiler check it, you must write \`@Override\` outside a comment and in the proper syntactic position.

## 7. Choosing Which to Use in a Project

**Use regular comments** when you want maintainers to understand the implementation rationale, a business constraint hard to infer from code, or a warning about an algorithm's limitation. Keep the content aligned with the current logic; avoid using comments to mask confusing code that could simply be named more clearly.

**Use Javadoc** for APIs that others need to call or inherit from: input/output contracts, side effects, nullability, exceptions, thread-safety when relevant, and preconditions. Focus on describing what API consumers must know rather than narrating each line of implementation. For public APIs, documentation needs to be updated when the contract changes.

**Use annotations** when you need machine-readable metadata, want the compiler to perform checks, want an annotation processor to generate/validate code, or want a framework/reflection to process a convention. Before using a custom or library annotation, ask: *Who will read this annotation? At what stage? What are its retention and target? What happens when the processing mechanism is missing?*

A single method may need all three:

\`\`\`java
/**
 * Sends a request with the configured timeout.
 *
 * @throws IllegalStateException if the client is not ready
 */
@Override
public void send() {
    // Keep the check here because state may change before sending.
    ensureReady();
    dispatch();
}
\`\`\`

In the **non-standalone illustration** above, Javadoc describes the API contract, \`@Override\` checks the inheritance relationship, and the comment explains the decision on where to place the check. The \`ensureReady()\` and \`dispatch()\` methods must be defined by the actual class.

## 8. Common Misconceptions

1. **“Anything with an \`@\` sign is an annotation.”** False. \`@param\` inside Javadoc is a documentation tag; \`@Override\` outside a comment is an annotation.
2. **“Writing Javadoc makes the compiler check \`@param\`/\`@return\` like a contract.”** No. The \`javadoc\` tool can detect or warn about certain documentation issues, but input/behavior checks must come from code or a separate checking mechanism.
3. **“Every annotation is available at runtime.”** No. It depends on retention, attachment location, and how it is read. \`CLASS\` retention is not exposed by standard reflection APIs.
4. **“Attaching any annotation automatically changes application behavior.”** No. A custom annotation has no business effect unless a consumer processes it.
5. **“\`@Documented\` turns Javadoc into reflection data.”** No. It controls how documentation tools present the annotation and does not store the doc comment verbatim in the \`Method\` object.
6. **“Javadoc is a type of data completely separate from comments.”** No. Javadoc is a special, structured form of comment for tools to read; Javadoc content does not become Java statements.
7. **“Describing something in a comment is enough to keep code correct.”** No. When logic changes, comments must be re-checked; conditions that need to be guaranteed must be implemented or tested.

## 9. Self-Check

**Question 1.** Does writing \`// @Override\` right above a method make the compiler check the override?  
**Answer:** No. That is a comment. You must use the actual \`@Override\` annotation.

**Question 2.** Can a program retrieve a Javadoc \`@return\` using \`Method.getAnnotation()\`?  
**Answer:** No. \`@return\` is a Javadoc tag, not a Java annotation.

**Question 3.** Can an annotation with \`@Retention(SOURCE)\` be read via reflection at runtime?  
**Answer:** No; this annotation is not retained in the class file.

**Question 4.** Why does a custom \`@MyRule\` not automatically reject invalid data?  
**Answer:** A compiler plugin, annotation processor, framework, or runtime code must read it and perform the corresponding check.

**Question 5.** How should a deprecated public API be documented?  
**Answer:** Attach \`@Deprecated\` so tools recognize it, and include a \`@deprecated\` Javadoc tag explaining the reason and replacement API.

If you want to observe this firsthand, compile the \`DocDemo.java\` sample, inspect the reflection output, generate the Javadoc HTML, and try changing the retention. Those three observations show the difference between **Java metadata, explanations in source code, and API documentation**.
