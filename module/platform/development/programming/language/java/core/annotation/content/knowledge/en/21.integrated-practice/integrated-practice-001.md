# Practice: Creating an Annotation Describing Document Information with enum, Class, and Default Values

This practice exercise builds a Java annotation named `@DocInfo` to describe **document or API metadata**, including title, publication state, rendering type, related type, revision number, and keyword tags. Instead of stuffing all information into a hard-to-validate string, we use the proper **valid element types** of Java annotations: `String`, `enum`, `Class<?>`, `Class<? extends Renderer>`, `int`, and `String[]`. Some elements will have `default` values so users only need to specify what differs from the default.

Desired result:

```java
@DocInfo(title = "Quick start")
class QuickStart {}
```

With a concise declaration, the metadata reader still retrieves `state = DRAFT`, `renderer = PlainRenderer.class`, `related = Void.class`, `revision = 1`, and the array `tags = {}`. These values are not additionally declared by `QuickStart`, but are **provided as defaults by the annotation definition**.

If another class needs to record complete information:

```java
@DocInfo(
    title = "API guide",
    state = DocState.PUBLISHED,
    renderer = HtmlRenderer.class,
    related = String.class,
    revision = 2,
    tags = {"java", "api"}
)
class ApiGuide {}
```

**Important:** An annotation only carries descriptive data; it does not publish documentation on its own, invoke a renderer on its own, or validate the title on its own. Business behavior must live in the code that consumes the annotation: reflection, an annotation processor, or a framework designed to read it.

## 1. Requirements of the Document Model

We want to represent the following properties:

| Element | Java Type | Required When Applying Annotation? | Meaning |
|---|---|---|---|
| `title()` | `String` | Yes, because there is no `default` | Document name |
| `state()` | `DocState` | No | State `DRAFT`, `REVIEW`, `PUBLISHED` |
| `renderer()` | `Class<? extends Renderer>` | No | Selected class implementing `Renderer` |
| `related()` | `Class<?>` | No | A class referred to by the document |
| `revision()` | `int` | No | Logical version number |
| `tags()` | `String[]` | No | Multiple keywords, in declaration order |

For example, need to choose between the `DRAFT` and `PUBLISHED` states? Use an **enum**, not a free-form string, so the compiler recognizes the valid constants. For example, need to specify the class that performs rendering? Use the **class token** `HtmlRenderer.class`, rather than writing the class name as a string `"HtmlRenderer"` and parsing it yourself.

Things that Java can check right at compile time:

- The `state` value must be a constant of the **exact `DocState` enum**.
- The `renderer` value must be a **class token compatible with `Class<? extends Renderer>`**.
- `related` accepts class tokens such as `String.class`, `Integer.class`, or `Void.class`.
- `tags` only holds `String` values; you cannot write integer values inside a `String[]` array.
- If `title` is omitted, the compiler reports a missing required element; if `revision` is omitted, the compiler uses `default 1`.

Things Java **does not automatically check according to business requirements**:

- `title` must not be empty or all whitespace.
- `revision` must be a positive number.
- `PUBLISHED` must have a minimum set of tags.
- The renderer has a public no-arg constructor and actually renders correctly.
- `related` must point to a class belonging to a domain accepted by the project.

That is the difference between **validity according to the annotation's types** and **validity according to the application contract**.

## 2. Which Element Types Are Allowed in an Annotation Interface?

According to Java Language Specification §9.6.1, the return type of an annotation element must belong to one of the categories permitted by Java:

1. A primitive type such as `int`, `long`, `boolean`, `double`.
2. `String`.
3. `Class` or a usage of `Class` with a valid type argument.
4. An enum type.
5. An annotation interface type.
6. A **one-dimensional** array whose component type belongs to the categories above.

Valid example:

```java
@interface SampleMetadata {
    String title();
    int version() default 1;
    boolean archived() default false;
    Class<?> related() default Void.class;
    String[] keywords() default {};
}
```

Some invalid declarations:

```java
// Invalid according to annotation element rules:
// @interface Invalid {
//     java.util.List<String> tags();        // List is not accepted
//     java.util.Map<String, String> data(); // Map is not accepted
//     String[][] matrix();                  // Multi-dimensional arrays are invalid
//     Object value();                       // Object is not a valid element type
// }
```

An annotation interface cannot freely become a generic interface carrying a type parameter like `@interface DocInfo<T>`. If you need to restrict the class type, use a **bounded class token element**: `Class<? extends Renderer>`, where `Renderer` is a concrete Java type, not a type parameter of the annotation.

`null` cannot be used as an annotation element value, even when the element has a reference type such as `String`, `Class`, or a nested annotation. Therefore, a clearly defined sentinel value, such as `Void.class`, can be used to mean "no related class".

## 3. Using an enum to Lock the List of Valid States

We declare:

```java
enum DocState {
    DRAFT,
    REVIEW,
    PUBLISHED
}
```

Then the annotation:

```java
@interface DocInfo {
    DocState state() default DocState.DRAFT;
}
```

At the usage site:

```java
@DocInfo(state = DocState.PUBLISHED)
class FinalGuide {}
```

The compiler ensures `state` receives a compatible enum constant. If you type the non-existent `DocState.PUBLISH`, the error is caught at compile time; if you type the string `"PUBLISHED"`, the type does not match so that also fails.

**Do not confuse this with automatic workflow validation.** An enum does not automatically transition a document `DRAFT -> REVIEW -> PUBLISHED`, nor does it guarantee that the document has a reviewer or has been uploaded. An enum only gives the set of states clear names and types.

When should you use an enum?

- There is a finite set that can be named clearly.
- You want `switch` branches on the state to be easy to read.
- You want the compiler to prevent typos in annotation values.
- You want reflection to return `DocState` directly instead of a string that needs parsing.

If states tend to be added by administrators at runtime without rebuilding the code, a fixed enum may not be appropriate. However, for a compile-time annotation contract like in this exercise, an enum is the natural choice.

## 4. How Do Class<?> and Class<? extends Renderer> Differ?

`Class<?>` can hold class tokens of many kinds:

```java
String.class
Integer.class
Void.class
int.class
String[].class
```

Because the type argument is an unbounded wildcard, it does not force the chosen class to belong to a specific hierarchy.

`Class<? extends Renderer>` restricts the chosen value to the `Renderer` type or a compatible subclass/implementation. For example:

```java
interface Renderer {
    String render(String title);
}

class PlainRenderer implements Renderer {
    public String render(String title) {
        return "PLAIN: " + title;
    }
}

class HtmlRenderer implements Renderer {
    public String render(String title) {
        return "<h1>" + title + "</h1>";
    }
}
```

When the element is declared:

```java
@interface DocInfo {
    Class<? extends Renderer> renderer() default PlainRenderer.class;
}
```

the following two examples are valid:

```java
@DocInfo(renderer = HtmlRenderer.class)
class HtmlDocument {}

@DocInfo(renderer = PlainRenderer.class)
class PlainDocument {}
```

This example is **invalid**, because `String` does not implement `Renderer`:

```java
// @DocInfo(renderer = String.class)
// class InvalidRenderer {}
```

This is a major advantage compared to the string `renderer = "com.example.HtmlRenderer"`: the compiler detects a class token that does not match the bound when the author applies the annotation.

However, **the bound is only a constraint on type relationships**; it does not guarantee that the class has a no-argument constructor, is not abstract, is not inaccessible, or does not throw an exception during instantiation. When you want to actually create an instance, you must do so in code and handle reflection errors. The full example will call `getDeclaredConstructor().newInstance()` with the two public/no-arg renderers by design.

## 5. Default Values: Declare Once, Use in Many Places

Java uses the syntax:

```java
@interface Versioned {
    int revision() default 1;
    String[] tags() default {};
    Class<?> related() default Void.class;
}
```

Meaning:

- If the author does not specify `revision`, the accessor returns `1`.
- If the author does not specify `tags`, the accessor returns an empty array.
- If the author does not specify `related`, the accessor returns `Void.class`.

A default must be a valid annotation element value for the declared type; it cannot be an arbitrary runtime Java expression. For primitive/`String`, an appropriate constant expression is required; for `Class`, a class literal is typically used; for an enum, the constant name is used directly; and for an array, valid `{...}` syntax is used.

Invalid choices:

```java
// @interface InvalidDefaults {
//     String now() default java.time.Instant.now().toString();
//     Class<?> current() default Class.forName("java.lang.String");
//     String optional() default null;
// }
```

None of the three are valid ways to provide annotation defaults. Configurations that depend on time, external data, or runtime variables must be left for the **consumer** to compute during processing.

### Default Values Are Not Copied Into Every Usage

JLS §9.6.2 specifies that the default of an annotation element resides in the **annotation interface declaration**, and when reading an annotation, the default value is applied dynamically if the usage does not write it explicitly. This has maintenance consequences:

- `@DocInfo(title="Quick start")` does not contain a copy of every default element like the attributes written by the author.
- If a library changes `state() default DRAFT` to `state() default REVIEW`, existing annotation usages that do not specify `state` can be reflected with the new default when using the corresponding annotation definition.
- Therefore, **changing a default is a contract change** that can affect system behavior even without modifying the source of the annotated classes.

In real-world applications, be cautious when changing a default that many modules depend on. If a default carries important business meaning, there must be tests to detect its impact.

## 6. @Retention, @Target, and @Documented for DocInfo

When you want to inspect metadata using Java reflection while the program is running:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface DocInfo { /* elements... */ }
```

- `@Retention(RUNTIME)` allows metadata from an annotation usage to be retained and reflected at runtime.
- `@Target(TYPE)` allows placement on corresponding class/interface declarations.
- `@Target(METHOD)` allows describing API methods.
- `@Documented` can be added to the **annotation definition** when you want standard Javadoc tools to record the annotation usage in the documentation of the corresponding element.

Do not confuse `@Documented` with automatically generating a website or validating content. It only affects how the annotation is included in Java documentation according to the contract.

If `@Retention` is omitted, the default is `RetentionPolicy.CLASS`, in which case `SomeClass.class.getAnnotation(DocInfo.class)` in standard Java reflection can return `null`. If using a compile-time annotation processor instead of runtime reflection, SOURCE/CLASS can also be appropriate depending on the architecture. This exercise needs to read metadata **at runtime**, so RUNTIME is chosen.

If you only want to attach metadata to classes, you can narrow it to `@Target(ElementType.TYPE)`; allowing more targets than needed can cause data to appear outside the places the consumer scans.

## 7. Complete, Runnable Java 17+ Example

Create a single file **DocumentInfoDemo.java**:

```java
import java.lang.annotation.*;
import java.util.*;

enum DocState { DRAFT, REVIEW, PUBLISHED }

interface Renderer {
    String render(String title);
}

class PlainRenderer implements Renderer {
    public String render(String title) {
        return "PLAIN: " + title;
    }
}

class HtmlRenderer implements Renderer {
    public String render(String title) {
        return "<h1>" + title + "</h1>";
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface DocInfo {
    String title();
    DocState state() default DocState.DRAFT;
    Class<? extends Renderer> renderer() default PlainRenderer.class;
    Class<?> related() default Void.class;
    int revision() default 1;
    String[] tags() default {};
}

@DocInfo(
    title = "API guide",
    state = DocState.PUBLISHED,
    renderer = HtmlRenderer.class,
    related = String.class,
    revision = 2,
    tags = {"java", "api"}
)
class ApiGuide {}

@DocInfo(title = "Quick start")
class QuickStart {}

public class DocumentInfoDemo {
    static void print(Class<?> type) throws ReflectiveOperationException {
        DocInfo info = type.getAnnotation(DocInfo.class);
        if (info == null) {
            System.out.println("No metadata");
            return;
        }

        Renderer renderer =
                info.renderer().getDeclaredConstructor().newInstance();

        System.out.println(type.getSimpleName() + ": "
                + info.title() + ", " + info.state()
                + ", revision=" + info.revision());
        System.out.println("renderer=" + renderer.render(info.title()));
        System.out.println("related=" + info.related().getSimpleName());
        System.out.println("tags=" + Arrays.toString(info.tags()));
    }

    public static void main(String[] args) throws Exception {
        print(ApiGuide.class);
        print(QuickStart.class);

        System.out.println("default state="
                + DocInfo.class.getMethod("state").getDefaultValue());
        System.out.println("default related="
                + (DocInfo.class.getMethod("related").getDefaultValue()
                    == Void.class));
    }
}
```

Compile with JDK 17+ and run:

```bash
javac --release 17 -Xlint:all DocumentInfoDemo.java
java DocumentInfoDemo
```

**Exact output:**

```text
ApiGuide: API guide, PUBLISHED, revision=2
renderer=<h1>API guide</h1>
related=String
tags=[java, api]
QuickStart: Quick start, DRAFT, revision=1
renderer=PLAIN: Quick start
related=Void
tags=[]
default state=DRAFT
default related=true
```

Notable observations:

1. `ApiGuide` specifies all elements; the chosen renderer is `HtmlRenderer`, so the output contains HTML tags.
2. `QuickStart` only specifies `title`; all remaining elements have defaults, so the state is `DRAFT`, the renderer is `PlainRenderer`, the revision number is `1`, and tags are empty.
3. `related=Void` is the sentinel we established by convention, **not** a "class being referenced by the document". If the consumer wants to display user-friendly information, it can convert the sentinel into the string `"(none)"`.
4. `DocInfo.class.getMethod("state").getDefaultValue()` reads the exact default directly from the annotation element declaration; the returned value is `DocState.DRAFT`.
5. `renderer()` returns a **Class token**, not a pre-built renderer object. The `getDeclaredConstructor().newInstance()` call is what actually creates the instance. For a class without a suitable constructor or with restricted access, the consumer must report an error or handle the exception.
6. `Arrays.toString(info.tags())` prints the array in order; you should not call `info.tags().toString()` directly expecting to see the array elements.

The example has used `String`, an enum, a bounded class token, an unbounded class token, a primitive, an array, and defaults — right within the scope of a document-describing annotation.

## 8. Reading Metadata of Methods, Not Just Classes

Because `DocInfo`'s `@Target` also allows `METHOD`, you can write:

```java
class DocumentApi {
    @DocInfo(title = "Find document", state = DocState.PUBLISHED)
    public String find(int id) {
        return "doc-" + id;
    }
}
```

This snippet relies on the `DocInfo`/`DocState` types already declared in the example, rather than being a standalone file. How to read it:

```java
var method = DocumentApi.class.getDeclaredMethod("find", int.class);
DocInfo doc = method.getAnnotation(DocInfo.class);
System.out.println(doc.title());
```

Accordingly, it will print `Find document`. Placing `@DocInfo` on a method **does not automatically create an API endpoint**, does not make an HTTP framework auto-discover routes, and does not generate complete JavaDoc. The consumer needs to actively scan the methods it cares about.

Note that the method name and parameter types must match when calling `getDeclaredMethod`; otherwise you will encounter `NoSuchMethodException`. If the metadata belongs to an inherited method, `getDeclaredMethod` and `getMethod` have different search scopes. `@Inherited` also does not automatically propagate across method overrides. These are Java reflection rules separate from defining annotation elements.

## 9. Using a Class Token to Select a Renderer: What Is Safe and What Is Not?

The declaration:

```java
Class<? extends Renderer> renderer()
        default PlainRenderer.class;
```

ensures that the attached class token satisfies the type relationship. This is better than declaring `String rendererClassName()` in many situations because the compiler checks the baseline: whether the class name exists and whether the class is compatible with `Renderer`.

However, Java does not infer additional guarantees on its own:

| Desired Property | Guaranteed by Class Bound? | What Else Is Needed? |
|---|---|---|
| Implementation has a type relationship with `Renderer` | Yes, per class token typing rules | No basic manual type checking needed |
| Has a no-argument constructor | No | Reflection validation or convention/build-time processor |
| Constructor is accessible | No | Public/accessibility rules; error handling |
| Renderer is not abstract/an interface | No | Check `Modifier.isAbstract` and instantiability |
| Output of `render(...)` is safe to insert into HTML | No | Appropriate escaping/encoding when used |
| Renderer is thread-safe | No | Separate component/lifecycle design |
| Class can be loaded in the actual runtime environment | Not unconditionally | Ensure valid runtime dependencies and packaging |

In this experiment, `PlainRenderer` and `HtmlRenderer` have no-argument constructors accessible to code in the same scope. In a large framework, reflection can be replaced by a registry or a dependency injection container to control lifecycle, caching, and access permissions.

For example, if a user chooses `Renderer.class` (the interface itself), the value is **valid according to the bound**, but `getDeclaredConstructor().newInstance()` will fail to instantiate it. Therefore, the consumer needs validation if runtime behavior requires a concrete class.

## 10. Compile-Time Errors Worth Recognizing

Several erroneous examples are **commented out** so that the main program section of the entire lesson still compiles:

### Omitting a Required Element

```java
// @DocInfo
// class MissingTitle {}
```

`DocInfo.title()` has no default, so it must be provided when using the annotation.

### Wrong Enum Type or Wrong Constant

```java
// @DocInfo(title = "Guide", state = "PUBLISHED")
// class WrongStateType {}
//
// @DocInfo(title = "Guide", state = DocState.PUBLISH)
// class UnknownEnumConstant {}
```

The correct way is `DocState.PUBLISHED`.

### Class That Does Not Satisfy the Bound

```java
// @DocInfo(title = "Guide", renderer = String.class)
// class WrongRenderer {}
```

`String` does not implement `Renderer`, so it does not fit `Class<? extends Renderer>`.

### Element Value Is Not an Accepted Constant

```java
// @DocInfo(title = System.getenv("DOC_TITLE"))
// class RuntimeTitle {}
```

The `title` value must be a suitable compile-time constant expression; you cannot call `System.getenv` to compute the document name right at the annotation usage site.

### Null, Collections, and Wrongly Typed Arrays

```java
// @DocInfo(title = null)
// class NullTitle {}
//
// @DocInfo(title = "Guide", tags = {1, 2})
// class IntegerTags {}
```

Java does not accept `null` as an annotation value and does not allow `int` values in a `String[]` element.

### Confusing Single-Element Array Syntax and Empty Arrays

```java
@DocInfo(title = "One tag", tags = {"java"})
class OneTag {}

@DocInfo(title = "One tag shorthand", tags = "java")
class OneTagShorthand {}

@DocInfo(title = "No tags", tags = {})
class NoTags {}
```

When an annotation element has an array type, the single-element syntax can omit the curly braces, such as `tags = "java"`; however, it **is still a single-element array** when read. An empty array `{}` is a different value.

## 11. Default Differs from "Missing Value" and Differs from Sentinel

With `DocInfo`, we have:

```java
Class<?> related() default Void.class;
```

This is a convention meaning **no related class**. It is not a general equivalent of `null`, nor does it cause the accessor to return `null` from a valid annotation. The consumer should define a clear predicate:

```java
boolean hasRelatedClass = info.related() != Void.class;
```

If a project has a real use case that wants to describe `Void.class` as a domain value, this sentinel will cause ambiguity and should be replaced with an enum or another annotation structure. There is no single sentinel that works well for every application.

With an array element:

```java
String[] tags() default {};
```

the empty set can be interpreted as "uncategorized". If you need to distinguish between "the user explicitly set an empty array" and "the user did not specify tags", **the read annotation value does not provide a general provenance flag**. Both writing `tags={}` and omitting `tags` resolve to an empty array and have the same meaning under `Annotation.equals`. To distinguish this level of meaning, you must change the data design or tool contract.

## 12. Should Annotations Replace All Configuration Files?

Annotations are suitable for **metadata attached to a declaration that changes along with the source code**. Use them when:

- Readers need a direct description of the class/method/API.
- The value types allowed in annotations are sufficient to model the data.
- The metadata is valuable at compile time or runtime depending on retention.
- You want the IDE/compiler to help detect type-related typos.

Do not force annotations to hold **long document content, translations, dynamic HTML, sensitive URLs, secret keys, or runtime environment state**. Such data may fit better in resource files, databases, configuration services, or separate documentation files. Annotations also do not update automatically when external state changes.

A combined approach: `@DocInfo` records basic metadata, while the consumer looks up the actual document store by `title` or ID. If building a generator, an annotation processor can use the metadata to generate a docs index during compilation; if building a runtime UI, reflection can read the metadata and render it with the code you wrote.

## 13. Testing Annotations: What Should Be Tested?

For an integrated practice exercise, tests should include at least:

1. **Annotation presence:** `type.getAnnotation(DocInfo.class) != null` where the annotation is applied.
2. **Required value:** `title()` matches the provided content.
3. **Enum default:** `QuickStart.state() == DocState.DRAFT`.
4. **Class bound:** `renderer()` is a class compatible with `Renderer`; with specific data, verify it yields the expected renderer.
5. **Class token sentinel:** `related() == Void.class` when omitted.
6. **Primitive default:** `revision() == 1`.
7. **Array:** `Arrays.equals(tags, expectedTags)` instead of calling `tags.equals(...) `.
8. **Runtime consumer:** instantiate the renderer and verify the expected output or a clearly reported error.
9. **Missing metadata:** the consumer has a handling policy when `getAnnotation` returns `null`.
10. **Negative compile samples:** missing title, wrong enum, wrong class bound, and non-constant expression must fail for the right reasons.

You can write tests directly without JUnit:

```java
DocInfo quick = QuickStart.class.getAnnotation(DocInfo.class);
if (quick == null || quick.state() != DocState.DRAFT) {
    throw new AssertionError("Incorrect default state");
}
if (!Arrays.equals(quick.tags(), new String[0])) {
    throw new AssertionError("Incorrect default tags");
}
```

The snippet above uses the types already declared in the main program and is placed inside a valid method/test. With Maven/Gradle, important assertions should be placed in `src/test/java` and run by the corresponding test runner so they are not skipped on CI.

### When Should You Write an Annotation Processor for DocInfo?

If you need to **reject a class** when `title` is empty or `revision <= 0`, you can write a processor:

```java
for (Element e : roundEnv.getElementsAnnotatedWith(DocInfo.class)) {
    DocInfo doc = e.getAnnotation(DocInfo.class);
    if (doc.title().isBlank() || doc.revision() <= 0) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR, "Invalid document metadata", e);
    }
}
```

This is an **illustrative snippet inside the processor's process method**, requiring imports, processor setup, and the annotation API. The plain Java compiler does not have that condition built in. The processor will execute at compilation time **if configured to run**; choose SOURCE/CLASS/RUNTIME for DocInfo according to actual consumption requirements.

## 14. Annotation Equality, hashCode, and Arrays When Checking Metadata

Java defines annotation equality by **the same annotation interface and each element value**, including elements using default values.

Two usages:

```java
@DocInfo(title="A")
class A {}

@DocInfo(
    title="A",
    state=DocState.DRAFT,
    renderer=PlainRenderer.class,
    related=Void.class,
    revision=1,
    tags={}
)
class B {}
```

are equivalent in terms of `Annotation.equals`: the same `DocInfo` type and the same resolved values throughout. Explicitly writing out all defaults does not change the result.

The `tags` array is compared **by content and order** using `Arrays.equals`, not by reference. Therefore, `{"java","api"}` and `{"api","java"}` are not equal in an array-typed annotation element.

An annotation's `hashCode` is also specified to be consistent with `equals`. However, do not use `annotation.toString()` as a stable data format for writing to files; the exact string format can differ across implementations.

## 15. Ways to Extend the Model While Staying Compliant with Java

**Adding author metadata:** you can add `String author() default "unknown";`. Changing defaults should only be done after understanding the impact on existing usages.

**Adding a renderer type:** implement another class `MarkdownRenderer implements Renderer`, then use `renderer = MarkdownRenderer.class`. There is no need to change the annotation interface because the bound already allows new implementations.

**Adding multiple related classes:** use `Class<?>[] relatedTypes() default {};`, with the syntax `relatedTypes = {String.class, Number.class}`. Do not create `List<Class<?>>` as an annotation element because it is invalid.

**Adding nested metadata:** define a separate annotation:

```java
@interface Author {
    String name();
    String team() default "docs";
}
```

then add an element:

```java
// Inside the @interface DocInfo definition:
Author author() default @Author(name = "unknown");
```

`Author` is a valid annotation type to serve as an element; `@Author(...)` is an annotation value, not an object instantiated with `new`. If using nested annotations to build complex structures, you must still respect element type and default restrictions, without arbitrary collections.

**Changing scope:** if you need to describe a package or module, consider `ElementType.PACKAGE`/`MODULE` and how the annotation is declared accordingly. You should not silently over-expand `@Target` if the consumer does not support it.

## 16. Common Misconceptions

- **"A class token already creates an object."** False. `HtmlRenderer.class` is only a class token; creating an object requires code and access permissions.
- **"An enum automatically enforces the publication workflow."** False. An enum only defines the list of allowed values; it does not implement transitions on its own.
- **"The default is null when omitted."** False. There must be an explicit default or a value must be required; `null` is not a valid annotation element value.
- **"Omitting revision means the annotation is missing an element."** False. `default 1` is applied when read.
- **"Class<? extends Renderer> guarantees a public constructor."** False. The bound is a type relationship; instantiation has its own conditions.
- **"Having @DocInfo makes Javadoc automatically become a complete documentation page."** False. `@Documented` only supports Javadoc's mechanism for recording annotations.
- **"@Retention(CLASS) can be read via getAnnotation at runtime."** False in standard reflection; the runnable example requires RUNTIME.
- **"If a title is present, it can never be empty."** False. `title=""` is still type-valid; separate validation is required if disallowed.
- **"tags is an unordered Set."** False. `String[]` preserves element order; `Arrays.equals` also considers order.
- **"Changing a default is harmless for already-compiled classes."** Not necessarily: the default is read from the current annotation declaration, so it can change the resolved value.

## 17. Practice Exercises

### Exercise 1 — Enum Type

Add the `DEPRECATED` state to `DocState`. Write `@DocInfo(title="Old API", state=DocState.DEPRECATED)`. Why does the compiler notify you immediately if you mistype the constant?

**Answer hint:** `state()` is of enum `DocState`, so the compiler must locate a matching compatible enum constant. An arbitrary string is not accepted.

### Exercise 2 — Default

Apply `@DocInfo(title="Intro")` to another class. What are the results of `revision()`, `tags()`, and `renderer()`?

**Answer:** `1`, an empty array, and `PlainRenderer.class`. These are the defaults of the annotation interface.

### Exercise 3 — Class Bound

Suppose you have `class PdfRenderer implements Renderer`. Can you use `renderer=PdfRenderer.class`? What about `renderer=String.class`?

**Answer:** `PdfRenderer.class` is valid; `String.class` does not implement `Renderer`, so it does not satisfy the bound.

### Exercise 4 — Sentinel

Why is `Void.class` used to represent "no related class" instead of `null`?

**Answer:** Java does not allow `null` as an annotation value; `Void.class` is a valid class literal. The sentinel is a custom convention that the consumer must understand.

### Exercise 5 — Runtime Consumer

If `getAnnotation(DocInfo.class)` returns `null`, how does the `print` method in the example handle it?

**Answer:** It prints `No metadata` and returns, without dereferencing `null`.

### Exercise 6 — Uninstantiable Renderer

If `renderer()` points to an abstract class implementing `Renderer`, does the annotation compile? Does reflection create an instance?

**Answer:** The class token can satisfy the bound at compile time, but an abstract class cannot be instantiated via constructor reflection as in the demo, so the consumer must detect/handle it.

### Exercise 7 — Single-Element Array

Does writing `tags="java"` instead of `tags={"java"}` change the return type of `tags()`?

**Answer:** No. The accessor always returns `String[]`; that is shorthand syntax for a single element.

### Exercise 8 — Use in CI

If you want to forbid titles consisting only of whitespace, what must be changed?

**Answer:** Add validation logic to the appropriate consumer/processor, such as `title().isBlank()` and emitting `Diagnostic.Kind.ERROR` at compile time or throwing a clear exception when the runtime consumer reads metadata.

### Exercise 9 — Changing Defaults

If `revision() default 1` is changed to `default 2`, how can `@DocInfo(title="Quick start")` read the new revision?

**Answer:** If revision is not explicitly written, the default value from the new annotation definition can be applied when read. This is a contract change that requires review and testing.

### Exercise 10 — Nested Metadata

Is designing `@Author(name="Alice", team="docs")` as an element of type `Author` on `@DocInfo` valid?

**Answer:** Yes, because Java allows an annotation interface type as an element's type. You simply need to declare `Author` and use syntactically valid `default`/values.

## 18. Practice Completion Checklist

- [ ] Have an `enum DocState` with clearly meaningful states.
- [ ] Have a `Renderer` interface and at least two implementations.
- [ ] `DocInfo` uses `Class<?> ` for the unbounded class and `Class<? extends Renderer>` for the renderer.
- [ ] The `title()` element is required; the remaining elements have defaults.
- [ ] `@Retention(RUNTIME)` because the example reads via runtime reflection.
- [ ] `@Target` only allows the locations that the consumer supports.
- [ ] `ApiGuide` applies explicit values; `QuickStart` applies minimal values.
- [ ] `javac --release 17 -Xlint:all` compiles successfully.
- [ ] The output of `DocumentInfoDemo` matches the example.
- [ ] Negative tests exist for missing title, wrong enum, and wrong class bound.
- [ ] Do not assume the annotation generates documentation on its own or enforces business validation.

### References

- [JLS Java SE 17 — §9.6 Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): element types permitted in annotations.
- [JLS Java SE 17 — §9.6.2 Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): default semantics, including application when read.
- [JLS Java SE 17 — §9.7.1 Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): requirement to provide a value if an element has no default.
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): how long annotations are retained.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class tokens and reflection operations.
- [Java SE 17 — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): common interface and contracts for `annotationType`, `equals`, and `hashCode`.

**Conclusion:** When describing document information with an annotation, an **enum** represents finite choices, a **Class token** represents a type known to the compiler, and **defaults** keep usage sites concise. The consumer determines behavior based on the metadata. Annotation type restrictions and class bounds are compile-time conditions; deeper business rules must be checked actively.
