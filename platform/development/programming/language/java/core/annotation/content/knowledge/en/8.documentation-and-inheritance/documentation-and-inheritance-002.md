# Documenting Annotations: Meaning, Elements, and Default Values in Java

An annotation is truly easy to use only when the reader understands **what it expresses, where it is applied, what each element means, and what happens when an element with a default value is omitted**. The `@interface` syntax describes the shape of the data; Javadoc explains the *contract* of that metadata.

Short example:

```java
/**
 * Declares a retry policy when an operation encounters a retryable error.
 *
 * <p>This annotation only carries configuration; the policy processor must read
 * the metadata and decide how to execute it.</p>
 *
 * @since 1.0
 */
@interface RetryPolicy {
    /**
     * Maximum number of retry attempts after the initial call.
     *
     * @return the number of retry attempts, non-negative
     */
    int maxRetries() default 2;
}
```

With this definition, `@RetryPolicy` or `@RetryPolicy(maxRetries = 2)` expresses the same **element value**. However, **there is no automatic retry mechanism** merely because the annotation exists. Only the code or framework that consumes it can perform that behavior.

This lesson focuses on how to **write and maintain annotation API documentation**, along with the differences among Javadoc, the `default` syntax, and `@Documented`.

## 1. What Annotation Documentation Needs to Clarify

When designing a custom annotation, treat it as a small configuration interface for a compiler, analysis tool, or framework.

Good documentation typically answers six questions:

1. **Meaning:** What rule or fact does the annotation represent? For example, "marks a method that can be retried," rather than simply "retry annotation."
2. **Applicable scope:** Should it be placed on a class, field, method, constructor, parameter, or type-use? Which restrictions are enforced by `@Target`?
3. **Processing entity:** Who reads the annotation and when? Only at compile time, during configuration generation, or at runtime?
4. **Per-element contract:** What does the value represent, what units or constraints apply, and how does it relate to other elements?
5. **Default value:** When the user omits an element, which value takes effect? Is the default value safe for most cases?
6. **Compatibility and evolution:** What happens if a default value is changed, an element is added, or the annotation is replaced across library versions?

These are the questions that matter to users of the annotation. Do not merely restate the code; document the assumptions that callers **cannot reliably infer** from Java names and types alone.

## 2. Javadoc on the Annotation Type Itself

The Javadoc for an annotation type is written **immediately before the `@interface` declaration**, just like documentation for a class or interface:

```java
/**
 * Marks a method that may be re-executed by a retry processor
 * when encountering a transient error.
 *
 * <p>Only takes effect if the application has configured a processor that reads this annotation.
 * Do not use for operations with side effects that cannot be safely repeated.</p>
 *
 * @since 1.0
 * @see java.lang.annotation.Target
 */
@interface Retryable {
    int attempts() default 2;
}
```

This snippet **illustrates an annotation type**; it compiles when placed in an appropriate Java file. Valuable parts of the documentation:

- **The first sentence** summarizes the meaning: it is used as the summary in the API Javadoc.
- **The following paragraph** describes constraints and limitations, especially those not automatically guaranteed by Java.
- **`@since` in Javadoc** specifies the API version in which it was introduced.
- **`@see`** links to related documentation; when there is a replacement type or a processing tool, it should point directly to that target.
- You can use `{@link SomeType}`, `{@code retry}`, and other inline tags to create links or formatting on the documentation page.

The `@since`, `@see`, and `{@link ...}` tags are **Javadoc syntax**, not Java annotations read by reflection.

**Naming guideline:** the name `Retryable` indicates the general intent; the Javadoc must clarify which errors "retry" applies to, how attempts are counted, and who handles it. A good name cannot replace the actual contract.

## 3. Writing Javadoc for Each Annotation Element

Inside the `@interface` body, each declaration of the form `Type name();` is an **annotation element**, which may include a `default ...` clause. Each element deserves to be documented individually as part of the API.

Example:

```java
/**
 * Configures the retry policy for a method.
 */
@interface RetryPolicy {
    /**
     * Maximum number of re-invocations after the first attempt.
     *
     * <p>0 means call only once with no retries.</p>
     *
     * @return the number of retries; valid values are from 0 to 5
     */
    int retries() default 2;

    /**
     * Wait time between two retry attempts, in milliseconds.
     *
     * @return non-negative wait duration, in milliseconds
     */
    long delayMillis() default 100L;

    /**
     * Policy identifier, used to match against the application configuration.
     *
     * @return non-empty identifier provided by the caller
     */
    String policyId();
}
```

This snippet is only an **example declaration**. Each `@return` in Javadoc explains **the value returned by the annotation's accessor**; it does not enforce validation. Java allows specifying `retries = -1` because the `int` type accepts negative numbers. If the `0..5` limit is actually required, an annotation processor or runtime consumer must validate and reject invalid values.

You should explicitly document:

| Information Type | Example in Javadoc | Why It Matters |
| --- | --- | --- |
| Meaning | "Number of retries **after** the initial call" | Prevents confusing total calls with retry attempts |
| Unit | "milliseconds" instead of "wait duration" | Prevents passing seconds into a value measured in ms |
| Value domain | "non-negative; 0 disables retries" | Helps users avoid meaningless configurations |
| Default case | "Defaults to 2 retry attempts" | Users understand what happens when omitted |
| System effect | "Only works when RetryProcessor is present" | Avoids creating the expectation that the annotation runs by itself |
| Compatibility impact | "Changing this value may change runtime behavior" | Helps maintain the library safely |

For a `Class<?>` element, describe what kind of type this class token denotes and whether it will be instantiated or only inspected. For an enum element, explain the meaning of each option. For an array, clearly state whether order matters, what an empty array means, and whether duplicates are accepted. One cannot rely on `String[]` alone to know these rules.

### Do Not Use @param for Parameterless Elements

An annotation element must have an empty parameter list: `String name();`. Therefore, there is normally **no `@param`** to describe element inputs. Use the description body and `@return` to explain the value. This differs from a regular method such as `void execute(String name)`.

An annotation element is **not an interface default method**: in `int retries() default 2;`, the `default` keyword declares a **default annotation value**, rather than attaching an implementation body to a method.

## 4. What Is the Semantics of Default Values?

Elements **without `default`** are required to have a value in every annotation usage (except in cases where the annotation type does not require declaring that element). Elements **with `default`** may be omitted at the usage site; when accessed, the default value is applied.

```java
@interface RequestConfig {
    String path();                     // Required.
    int timeoutMillis() default 1000;  // Optional.
    boolean audit() default false;     // Optional.
}

@RequestConfig(path = "/orders")
class OrderResource {}

@RequestConfig(path = "/payments", timeoutMillis = 2500, audit = true)
class PaymentResource {}
```

These are **illustrative declarations**, not a standalone program. `OrderResource` has `timeoutMillis() == 1000` and `audit() == false` when the annotation is read. `PaymentResource` provides explicit values.

Using `@RequestConfig` without passing `path` is a **compile-time error**, because `path()` has no default. Java does not infer `""` for every `String` or `0` for every `int` when the annotation author has not declared a default.

### default Resides in the Annotation Type, Not at the Usage Site

```java
@interface Threshold {
    int value() default 10;
}

// 10 is the effective value from the annotation type.
@Threshold
class DefaultThreshold {}

// 50 is written explicitly at the usage site.
@Threshold(50)
class ExplicitThreshold {}
```

Using the `@Threshold(50)` syntax is a valid shorthand for `@Threshold(value = 50)`. The element name must be `value`, and all remaining elements (if any) must have appropriate defaults to use this shorthand.

### A default Value Cannot Be null

Annotation values in Java are restricted by the JLS: primitives, `String`, `Class`, enums, annotations, or one-dimensional arrays of valid types. `null` **is not a valid value** for an annotation element, even for elements of type `String` or `Class<?>`.

An **intentionally invalid** example:

```java
@interface InvalidName {
    String name() default null; // Compile-time error.
}
```

If you need to express "unspecified," design a meaningful value and document it, such as `String description() default "";`, an `UNKNOWN` enum constant, `Class<?> type() default Void.class;`, or an empty array `String[] tags() default {};`. This is an API contract choice; **there is no single sentinel suitable for every application**.

### Default Values Are Applied When the Annotation Is Read

JLS §9.6.2 specifies that a default resides in the definition of the **annotation type** and is applied dynamically when the annotation value is read. It is not "copied" as an explicit value into each usage site.

Important compatibility consequences:

- Version 1.0: `int retries() default 2;`, and the consuming class writes `@RetryPolicy` without declaring `retries`.
- Version 2.0: the definition is changed to `int retries() default 5;`.
- If the program runs with the new annotation type and the consuming class still relies on the default, code reading the annotation can see **5**, even if the consuming class was compiled earlier, provided other compatibility/classpath conditions are met.
- If the consuming class explicitly writes `@RetryPolicy(retries = 2)`, changing the default on the annotation type does not alter that declared value.

Therefore, changing a default can be a **behavioral change** even though the API still compiles. For annotations controlling security, transactions, retries, timeouts, authorization, or logging, you need to evaluate compatibility before changing a default value.

## 5. What Is @Documented Used For?

Javadoc can describe the **annotation type definition** and each element, yet another question is: *when generating documentation for a class or method that uses the annotation, will the tool display the annotation itself as part of that element's public contract?*

The meta-annotation `java.lang.annotation.Documented` serves this purpose:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Declares the stability level of an API.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Stability {
    /** @return the stability level code */
    String value();
}

/** An API currently recommended for use. */
@Stability("stable")
class PublicService {}
```

These are **illustrative declarations**, without a `main` method. When generating Javadoc, a tool such as `javadoc` typically displays the presence and value of `@Stability("stable")` in the documentation of `PublicService` because the annotation type is marked with `@Documented`.

If `@Documented` is omitted, the presence of the annotation in source code **does not mean** that a default tool must display it as part of the documented contract of `PublicService`. Specialized tools may follow different rules.

### Distinguishing Three Responsibilities

| Component | Role |
| --- | --- |
| `/** ... */` on `@interface Stability` | Explains **what Stability is** |
| `/** ... */` on `String value();` | Explains **what the element value expresses** |
| `@Documented` on `Stability` | Marks **the presence and value of @Stability at the usage site** as information belonging to the public documentation contract |

`@Documented` does not write Javadoc comments on behalf of the author, nor does it turn an element into validation logic. `@Documented` has no class inheritance behavior, is not synonymous with `@Inherited`, and does not make the annotation visible to runtime reflection if the retention policy is unsuitable.

## 6. Combining @Target, @Retention, and @Documented When Publishing an API

An annotation used as runtime configuration should clearly declare where it can be applied, how long it is retained, and its visibility in documentation:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface ApiContract {
    String owner();
    boolean experimental() default false;
}
```

This is an **illustrative snippet** that requires importing the corresponding meta-annotations. Understand each line:

- `@Target({TYPE, METHOD})`: the compiler restricts the annotation to class/interface/type and method declarations (according to the specified targets), disallowing arbitrary placement on fields.
- `@Retention(RUNTIME)`: the annotation can be retrieved by reflection at runtime through the corresponding declaration object.
- `@Documented`: the presence of the annotation on an API is included in the documented contract by standard documentation tools according to the rules of `@Documented`.
- The Javadoc on `ApiContract` and each element must still explain the meaning of `owner` and `experimental` along with any constraints.

For annotations intended only for the compiler, `SOURCE` or `CLASS` retention may be more appropriate. Do not enable `RUNTIME` just to make Javadoc look nice; those are two separate goals.

### Regarding Inheritance

`@Inherited` controls how reflection searches for an **annotation placed on a class** along the superclass hierarchy under appropriate conditions. It does not replace `@Documented`, does not automatically copy method annotations to overriding methods, and does not cause an API's Javadoc to automatically generate missing element descriptions.

If a configuration annotation is inherited, the documentation should clearly state **the inheritance rules and how subclasses override values**. If the annotation does not have `@Inherited`, you should not claim it automatically propagates to subclasses unless a framework explicitly implements its own rules.

## 7. Standalone Java 17+ Example: Meaning, Defaults, and @Documented

Create a single file named **`AnnotationDocsDemo.java`** with the complete content below. The Javadoc comments illustrate how to document **the annotation type and each element**, while `main` demonstrates that defaults are read through reflection.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

/** Priority levels for executing tasks. */
enum Priority {
    NORMAL, HIGH
}

/**
 * Configures a task that can be executed by a job processor.
 *
 * <p>This annotation only provides metadata. The processor must read
 * the values and implement the corresponding execution policy.</p>
 *
 * @since 1.0
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobPolicy {

    /**
     * Logical name of the task in the system.
     *
     * @return non-empty name provided by the application
     */
    String name();

    /**
     * Maximum number of retry attempts after the first execution.
     *
     * <p>0 means do not retry.</p>
     *
     * @return number of retries, non-negative; defaults to 2
     */
    int retries() default 2;

    /**
     * Priority level of the task.
     *
     * @return the priority level, defaults to NORMAL
     */
    Priority priority() default Priority.NORMAL;

    /**
     * Descriptive labels looked up by the system for grouping.
     *
     * @return the labels; an empty array means no labels
     */
    String[] tags() default {};
}

/** Task that uses all default values except the name. */
@JobPolicy(name = "invoice", tags = {"finance", "daily"})
class InvoiceJob {}

/** Task that overrides default values according to the application contract. */
@JobPolicy(name = "alert", retries = 0, priority = Priority.HIGH)
class AlertJob {}

public class AnnotationDocsDemo {

    private static void describe(Class<?> type) {
        JobPolicy config = type.getAnnotation(JobPolicy.class);
        System.out.println(type.getSimpleName()
                + ": name=" + config.name()
                + ", retries=" + config.retries()
                + ", priority=" + config.priority()
                + ", tags=" + String.join(",", config.tags()));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        describe(InvoiceJob.class);
        describe(AlertJob.class);

        Method retriesElement = JobPolicy.class.getDeclaredMethod("retries");
        System.out.println("element-default=" + retriesElement.getDefaultValue());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 AnnotationDocsDemo.java
java AnnotationDocsDemo
```

Exact stdout:

```text
InvoiceJob: name=invoice, retries=2, priority=NORMAL, tags=finance,daily
AlertJob: name=alert, retries=0, priority=HIGH, tags=
element-default=2
```

Explanation:

1. `InvoiceJob` provides the required `name` along with tags; it omits `retries` and `priority`, so reading them yields the defaults `2` and `NORMAL`.
2. `AlertJob` specifies `retries = 0` and `Priority.HIGH`. The `tags()` array defaults to empty, so `String.join(",", ...)` returns an empty string; the output line ends with `tags=`.
3. `JobPolicy.class.getDeclaredMethod("retries").getDefaultValue()` returns **the default defined on the annotation element**, rather than retrieving a value from a class using the annotation.
4. `@Documented` does not cause those four output lines. The `describe` method and reflection generate the output; `@Documented` is meant for documentation tools such as `javadoc`.

The program does not execute retries or priority scheduling. If those behaviors are needed, the application must build a consumer that receives and interprets `JobPolicy`.

### Generating HTML Documentation

Run separately:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs AnnotationDocsDemo.java
```

`-private` helps this example include package-private annotation types and classes in the documentation. After the command succeeds, open the HTML documentation generated in the `docs` directory to inspect:

- The `JobPolicy` page describes the meaning of the annotation and each element.
- The `retries()` element shows its `@return` Javadoc and the declared default value.
- The documentation for `InvoiceJob` / `AlertJob` can display `@JobPolicy(...)` in the declaration section because the annotation type has `@Documented`.

Any notices or warnings emitted by the `javadoc` command are **output from the documentation generator tool**, not part of the stdout of `java AnnotationDocsDemo`.

### An Experiment with Defaults

If you change `int retries() default 2;` to `int retries() default 4;` and recompile/re-run:

- `InvoiceJob` will see `retries=4` because it does not write an explicit retry count.
- `AlertJob` will still see `retries=0` because an explicit value was specified.
- `getDefaultValue()` on the element will return `4`.

This experiment illustrates the behavior of default values. In a multi-version library system, changing a default requires careful review because clients relying on the implicit value may experience altered behavior.

## 8. How to Write Better Documentation for Real-World Annotations

Consider a data-access configuration annotation:

```java
/**
 * Maps a property to a storage column.
 *
 * <p>Used only by mapper X for fields that the mapper
 * has permission to read. Does not automatically create columns in the database.</p>
 *
 * @since 1.0
 */
@interface StoredColumn {
    /**
     * Column name according to the current schema.
     *
     * @return non-empty column name, case-sensitive
     *         according to the rules of mapper X
     */
    String name();

    /**
     * Allows the mapper to ignore a value that has not been provided.
     *
     * @return true if the value may be absent; defaults to false
     */
    boolean optional() default false;
}
```

This is a **design illustration**, not a reference to any specific library X. Descriptions mentioning "mapper X" are meaningful only if a consumer with that contract actually exists; when implementing, replace it with the real name and mechanism.

Compared to a brief description like `/** Column. */`, the reader gains additional information:

- Where it is used and which processing mechanism reads the metadata.
- Which rules the column name follows.
- What the default `optional = false` means.
- What the annotation **does not do on its own**: it does not update the schema or guarantee data integrity.

When behavior changes, update the Javadoc **together with** the consumer and tests. Documentation describes a commitment, not a mechanism that enforces that commitment automatically.

## 9. Common Mistakes

### Mistake 1: Only Commenting the Annotation Name and Skipping Meaning

Declaring `/** Policy. */ @interface Policy {...}` fails to tell users what policy it is, who processes it, or whether defaults apply. Describe the behavior expected from the consumer and the limitations of the annotation.

### Mistake 2: Not Documenting Individual Elements

`int timeout();` leaves readers unsure whether the unit is seconds or milliseconds, whether 0 or negative numbers are permitted, and whether omitting it is valid. Name and type alone are not a substitute for a contract.

### Mistake 3: Confusing default with Javadoc Description

Writing "defaults to 3" in Javadoc **does not make Java choose 3**. You must declare `int retries() default 3;` if you truly want the element to have a default value. Update Javadoc whenever changing defaults.

### Mistake 4: Assuming Default Values Are Baked Into Every Annotation Usage

According to the JLS, defaults are applied when the annotation is read. Changing a default on the annotation type can change the effective value for clients that do not pass the element explicitly, even in situations using older bytecode with a newer annotation definition.

### Mistake 5: Using null as a default

`String description() default null;` is a compile-time error. Choose a clear sentinel such as an empty string, an enum constant, or an empty array, and document it in Javadoc.

### Mistake 6: Thinking @Documented Automatically Generates Element Documentation

`@Documented` controls the display of **the annotation at its usage site** in public documentation. It does not write the `@interface` description or `@return` explanations for elements on your behalf.

### Mistake 7: Thinking @Documented Is Equivalent to @Inherited

`@Documented` relates to documentation tools; `@Inherited` relates to how annotations on classes are looked up via superclasses. The two meta-annotations have separate responsibilities.

### Mistake 8: Claiming the Annotation Executes Behavior on Its Own

Declaring `@RetryPolicy` does not automatically perform retries; `@Audit` does not automatically write logs. Documentation must identify the consumer and the conditions under which that mechanism operates.

### Mistake 9: Documenting Values/Constraints That Do Not Match the Implementation

If Javadoc states that `retries` only accepts 0 to 5, yet the consumer does not check it, users may configure `-1` and encounter unpredictable behavior. Keep the contract, validation, and tests synchronized.

### Mistake 10: Changing a default Without Considering Compatibility

Changing `enabled() default false` to `true` can affect clients that do not pass an explicit value. Changes related to security or side effects require impact assessment and clear version documentation.

## 10. Self-Review Checklist Before Publishing an Annotation

| Question | Passing Criterion |
| --- | --- |
| Does the reader understand what the annotation expresses? | Opening Javadoc accurately explains the domain meaning |
| Is it clear where to apply it? | `@Target` and documentation are consistent |
| Is it clear who consumes the metadata? | Describes the annotation processor, framework, or runtime consumer |
| Is every element understood? | Individual Javadoc, `@return` where appropriate, clear units/constraints |
| Is it clear which elements are required? | Elements without defaults are clearly indicated and explained |
| Are defaults understood? | `default` in code matches Javadoc |
| Are arrays/enums/sentinels understood? | Empty values, ordering, and special cases are explained |
| Should it appear in the Javadoc of usage sites? | `@Documented` has been considered |
| Is runtime reflection needed? | `@Retention(RUNTIME)` and corresponding consumer |
| Are changes compatible? | Evaluate clients relying on defaults and published contracts |

## 11. Self-Check Questions

**Question 1.** An element `int retries() default 2;` is documented in Javadoc as "defaults to 5". What is the effective value when using `@RetryPolicy`?

**Answer:** `2` according to Java syntax. The Javadoc is outdated and needs to be fixed.

**Question 2.** If you write `String name();` and use `@Config` without filling in `name`, is that valid?

**Answer:** No, if `name()` is an element without a default and no value is provided in the annotation usage.

**Question 3.** When `@Documented` is added to an annotation type, does Java automatically invoke code to process the metadata?

**Answer:** No. `@Documented` pertains to the documentation contract and how tools like `javadoc` display the annotation.

**Question 4.** How do `@return` placed on an annotation element and `default` following the element declaration differ?

**Answer:** `@return` describes the meaning of the value for readers; `default` specifies the value Java provides when an annotation usage omits the element.

**Question 5.** When changing `default 2` to `default 4`, does a client using `@Policy(retries = 1)` automatically become 4?

**Answer:** No. The value `1` was explicitly declared. Only usages that omit the element receive the new default when read under the current annotation definition.

**Question 6.** If an annotation has `@Documented` and `@Retention(CLASS)`, must Javadoc reject it just because runtime reflection cannot read it?

**Answer:** No. Documentation generation tools and runtime reflection serve different roles; retention determines persistence, while `@Documented` indicates the requirement to appear in public documentation.

## Official References

- [JLS 17 §9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1).
- [JLS 17 §9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
- [JLS 17 §9.7.1 — Element-value pairs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java SE 17 API — Documented](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Documented.html).
- [Java SE 17 API — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).

When writing annotations for others to use, start with **the meaning and contract**, then clearly express each element and its default value in both code and Javadoc. The more strongly the metadata influences consumer behavior, the more specific the documentation and validation mechanisms must be.
