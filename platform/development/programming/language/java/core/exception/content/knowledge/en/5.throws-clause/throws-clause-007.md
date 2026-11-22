# Declaring Unchecked Exceptions and Their Documentation Role in Java

An **unchecked exception** is an exception belonging to the `RuntimeException` or `Error` branch, including their subclasses. Java **does not require** a method or constructor to list these exceptions in a `throws` clause, nor does it **require** calling code to catch or declare them. Nevertheless, an API can still write `throws IllegalArgumentException`, `throws IllegalStateException`, or Javadoc `@throws` documentation to express failure cases that API users need to know about.

This lesson focuses on the question: **when should unchecked exceptions be declared in `throws`, when should they be described via Javadoc and the API contract, and what does the compiler actually check?** Key topics include how to write method/constructor signatures, distinguishing language rules from documentation recommendations, publishing failure conditions, handling overrides, and API design risks.

## 1. Identifying Unchecked Exceptions Accurately

In Java, `Throwable` has two major branches: `Exception` and `Error`. `RuntimeException` is a subclass of `Exception` but is classified as **unchecked**; `Error` and its subclasses are also unchecked.

~~~text
Throwable
├── Error                                   unchecked
│   ├── AssertionError                      unchecked
│   ├── LinkageError                        unchecked
│   └── ...
└── Exception
    ├── IOException                         checked
    ├── SQLException                        checked
    ├── InterruptedException                checked
    └── RuntimeException                    unchecked
        ├── IllegalArgumentException        unchecked
        │   └── NumberFormatException       unchecked
        ├── IllegalStateException           unchecked
        ├── NullPointerException            unchecked
        ├── IndexOutOfBoundsException       unchecked
        └── ...
~~~

**Classification condition:** every subclass of `RuntimeException` and `Error` is unchecked. All other `Throwable` types are checked. Not every subclass of `Exception` is checked; `RuntimeException` is the exception to remember.

Examples of the meanings of commonly seen unchecked exceptions:

| Type | Common situation | What the API user should understand |
| --- | --- | --- |
| `IllegalArgumentException` | An argument violates contract rules, such as an invalid negative value | Fix the input before calling |
| `IllegalStateException` | The object is not yet initialized, is already closed, or is in a state that does not permit the operation | Check the usage lifecycle/state |
| `NullPointerException` | A `null` reference is used where a non-`null` object is required | Follow the API's nullability conventions |
| `IndexOutOfBoundsException` | An index is outside the data range | Constrain the index to valid bounds |
| `NumberFormatException` | A string cannot be parsed into a number according to the required syntax | Validate or handle the input data |
| `UnsupportedOperationException` | An operation is represented in the API, but the implementation does not support it | Choose an appropriate call or implementation |
| `Error` and its subclasses | For example, certain serious runtime environment or class linkage errors | Typically not used as a recoverable business error mechanism |

The checked/unchecked classification is a property **of the exception type**, independent of the exception's name, specific severity, whether `throws` appears in the signature, or whether it is actually thrown during a particular run.

## 2. `throws` with Unchecked Exceptions Is Completely Valid

The syntax of the `throws` clause is the same for checked and unchecked exceptions:

~~~java
// Illustrative snippet of declarations placed in a class.
public static int parseAge(String raw)
        throws NumberFormatException {
    return Integer.parseInt(raw);
}

public static int parseAgeWithoutDeclaration(String raw) {
    return Integer.parseInt(raw);
}
~~~

Both methods can throw `NumberFormatException`. They differ only in that the first method **explicitly states the exception type in its signature**. Because `NumberFormatException` is unchecked, both calls can be written **without `try/catch` or `throws` on the caller side**.

~~~java
// Illustrative snippet inside a method.
int a = parseAge("17");
int b = parseAgeWithoutDeclaration("25");
System.out.println(a + b); // 42
~~~

If `"mười bảy"` is passed to either call, `Integer.parseInt` may throw `NumberFormatException`. Java still performs the runtime mechanism of finding the nearest `catch` and propagating the exception just like any other `Throwable` type.

Constructors are also allowed to declare unchecked exceptions:

~~~java
class UserAge {
    private final int value;

    UserAge(int value) throws IllegalArgumentException {
        if (value < 0) {
            throw new IllegalArgumentException("tuổi âm");
        }
        this.value = value;
    }
}
~~~

Calling `new UserAge(-1)` can throw `IllegalArgumentException`; however, calling code such as `new UserAge(20)` **is not required by the compiler to catch** this exception type. Declaring `throws IllegalArgumentException` on a constructor mainly serves as a signal to human readers and tools inspecting the API signature.

There is no requirement to "register" every unchecked exception that might occur; Java also does not automatically insert them into the `throws` clause.

## 3. Core Differences from Checked Exceptions

Consider two cases:

~~~java
import java.io.IOException;

// Two illustrative methods placed in a class.
static void readFile() throws IOException {
    throw new IOException("không đọc được");
}

static void validate() throws IllegalArgumentException {
    throw new IllegalArgumentException("dữ liệu sai");
}
~~~

Rules at the call site:

- **Calling `readFile()`:** because `IOException` is checked, the call must be inside a matching `catch` handling path or the enclosing method must declare `throws IOException` (or a valid supertype), unless the context handles it otherwise according to Java rules.
- **Calling `validate()`:** because `IllegalArgumentException` is unchecked, the calling code needs neither `catch` nor `throws IllegalArgumentException`, even though the `validate` method declared it.
- **At runtime:** both kinds go through the same mechanism of `throw`, searching for `catch`, running `finally`, and propagating if unhandled.

This example does not create categories such as "unchecked, but if declared becomes checked". Adding `throws RuntimeException` does not change the compiler's checking mechanism.

| Aspect | Checked exception | Unchecked exception |
| --- | --- | --- |
| Examples | `IOException`, `SQLException` | `IllegalArgumentException`, `IllegalStateException` |
| Does the compiler require `catch` or `throws` when it can escape? | Yes, per exception-checking rules | No |
| Can it be listed in `throws`? | Yes | Yes |
| Can it be described with Javadoc `@throws`? | Yes | Yes |
| Does calling a method with `throws` automatically throw an error? | No | No |
| Does it propagate up the call stack if actually thrown? | Yes | Yes |

## 4. Why Still Document Unchecked Exceptions?

When an API publishes the conditions that cause `IllegalArgumentException` or `IllegalStateException`, callers know how to **use the API properly**, prevent errors, validate/handle inputs, and diagnose runtime failures.

For example, the declaration `void transfer(int amount)` does not specify which values are permitted. Good documentation should clarify:

- **Triggering conditions:** is `amount <= 0` valid? What happens when transferring while the account is closed?
- **Exception type:** does an argument error throw `IllegalArgumentException` or does a state error throw `IllegalStateException`?
- **State on failure:** is data partially modified, or does the operation fail before any mutation?
- **Proper usage:** the values, state, or preparation steps the caller must guarantee.

The goal of documentation is to turn important expectations into a **readable and testable contract**. It does not replace input validation in code, nor does it make the compiler verify that Javadoc messages are always accurate.

For libraries used by external consumers, Javadoc describing intentional failure scenarios is often more important than mechanically listing every `RuntimeException` from dependencies or unexpected bugs. An API cannot promise that no other unchecked exception will ever occur; there is no need to create an endless list.

## 5. Two Ways to Publish: The `throws` Clause and Javadoc `@throws`

You can write **both**, or write Javadoc only.

### 5.1. Declaring in the Signature

~~~java
public void deposit(int amount)
        throws IllegalArgumentException, IllegalStateException {
    // Implementation of an API.
}
~~~

This `throws` part is visible in the source signature and the method's reflection metadata. However, it **only lists types**, without explaining which situations cause the error. Because they are unchecked exceptions, it does not force callers to catch or declare them.

### 5.2. Describing Conditions with Javadoc

~~~java
/**
 * Deposits a positive amount into an active account.
 *
 * @param amount the amount to deposit; must be greater than 0
 * @throws IllegalArgumentException if amount is less than or equal to 0
 * @throws IllegalStateException if the account is closed
 */
public void deposit(int amount) {
    // Implementation of an API.
}
~~~

**`@throws` is a Javadoc documentation tag**, not a Java keyword in the signature. It can describe an unchecked exception **even when no `throws` clause appears**. The `@exception` tag is a historical alias for `@throws`, but `@throws` should be used consistently.

Typically, when documenting an unchecked exception, the most valuable information is the **specific condition** that causes the exception. Writing only `@throws IllegalArgumentException may throw IllegalArgumentException` is of almost no help to users.

### 5.3. Combining Both

~~~java
/**
 * Updates the amount according to the API rules.
 *
 * @param amount a positive amount
 * @throws IllegalArgumentException if amount is not positive
 * @throws IllegalStateException if the account is locked
 */
public void deposit(int amount)
        throws IllegalArgumentException, IllegalStateException {
    // Implementation of an API.
}
~~~

Using `throws` in the signature is optional for unchecked exceptions; choose whether to include it based on a consistent API style. **The `@throws` tag should still clearly state important failure conditions**, whether or not the types are listed in the signature.

Note the different language rule: for checked exceptions, Javadoc `@throws IOException` **does not substitute for** the `throws IOException` declaration required for the source code to compile. Javadoc does not turn a checked type into an unchecked one, and a `throws` clause does not replace the condition explanation in documentation.

## 6. Complete Java 17+ Example: An API with a Clear Error Contract

Save the following code as `UncheckedDocumentationDemo.java`:

~~~java
public class UncheckedDocumentationDemo {
    static final class Counter {
        private int value;
        private boolean closed;

        Counter(int initialValue) {
            if (initialValue < 0) {
                throw new IllegalArgumentException("giá trị đầu âm");
            }
            value = initialValue;
        }

        /**
         * Increments the value while the counter is open.
         *
         * @param delta positive integer to add
         * @throws IllegalArgumentException if delta is not positive or causes overflow
         * @throws IllegalStateException if the counter is closed
         */
        void add(int delta) throws IllegalArgumentException, IllegalStateException {
            if (delta <= 0) {
                throw new IllegalArgumentException("delta phải dương");
            }
            if (closed) {
                throw new IllegalStateException("bộ đếm đã đóng");
            }
            if (value > Integer.MAX_VALUE - delta) {
                throw new IllegalArgumentException("tăng gây tràn số");
            }
            value += delta;
        }

        int value() {
            return value;
        }

        void close() {
            closed = true;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(2);
        counter.add(3);
        System.out.println("Giá trị: " + counter.value());

        try {
            counter.add(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Đối số: " + ex.getMessage());
        }

        counter.close();
        try {
            counter.add(1);
        } catch (IllegalStateException ex) {
            System.out.println("Trạng thái: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 UncheckedDocumentationDemo.java
java UncheckedDocumentationDemo
~~~

Exact stdout:

~~~text
Giá trị: 5
Đối số: delta phải dương
Trạng thái: bộ đếm đã đóng
~~~

**Key points to understand from the program:**

1. The constructor `Counter(int initialValue)` checks a precondition on the initial value. It does not write `throws IllegalArgumentException`, yet it is still allowed to throw an unchecked exception when the argument is invalid.
2. `add(int delta)` declares two unchecked exceptions in its `throws` clause while explaining each condition with Javadoc `@throws`.
3. `main` calls `counter.add(3)` **without `try/catch`**; the compiler accepts it because all declared types are unchecked.
4. The next two `try/catch` blocks are an intentional handling choice to demonstrate the failure branches, not a requirement enforced by the compiler.
5. Input and state checks occur before updating `value`, so the errors checked here do not partially increment the value. This is a useful design property that can be stated in the API contract.
6. `value > Integer.MAX_VALUE - delta` avoids integer overflow on the update path after confirming `delta > 0`; the overflow condition is published with the same `IllegalArgumentException`.

To test the constructor case separately, you can write inside a method:

~~~java
// Illustrative snippet in calling code that has access to the Counter class.
try {
    new UncheckedDocumentationDemo.Counter(-1);
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // giá trị đầu âm
}
~~~

This snippet shows that a constructor does not need to declare `throws IllegalArgumentException` to actually throw it. In library code, constructors should also be documented with `@throws` if input conditions are an important part of the API.

## 7. Generating Documentation from `@throws` Tags

The `javadoc` tool in the JDK converts `/** ... */` doc comments into API documentation. The `@throws` tag contributes the exception description, typically appearing in the **Throws** section of the method/constructor when that element is included in the documentation.

For the file from Section 6, documentation can be generated with:

~~~bash
javadoc -private -encoding UTF-8 -charset UTF-8 -d docs UncheckedDocumentationDemo.java
~~~

The `-private` flag includes nested classes and non-public members from the example in the output; when documenting a real library, choose the visibility scope appropriate for the API users need. HTML files are generated in the `docs` directory; the output can include class/member pages and the exception description section for `add(int)`.

In real projects, build plugins (Gradle/Maven) are typically used to generate Javadoc consistently, but the rules for writing `@throws` remain the same. The `javadoc` tool **does not modify code** to enforce documented conditions; the checks inside the method must match the described conditions.

Checklist before releasing an API:

- Each `@throws` describes **a specific triggering condition**, rather than merely repeating the type name.
- The documented list reflects exceptions callers can anticipate from the contract, rather than every runtime error that could occur due to bugs or the environment.
- If failure conditions change during refactoring, update Javadoc and tests alongside the implementation code.
- Documentation on an interface/superclass should align with the commitments of implementing classes, avoiding guarantees that not all implementations can uphold.

## 8. Should You Write `throws RuntimeException` or `throws Exception` Just to Be Safe?

Generally, it is **unnecessary and unhelpful** if the goal is merely to say "the method may encounter some runtime error."

~~~java
// Valid, but fails to describe the specific kind of failure.
static void process(String input) throws RuntimeException {
    // ...
}
~~~

`RuntimeException` is a broad supertype of many unchecked exceptions, so declaring it as above neither forces callers to handle it nor reveals specific contract conditions. Instead, if there is a clear input rule, writing Javadoc for the specific exception is much more valuable.

`throws Exception` is even broader: it is a checked exception in Java's hierarchy, so if an API publishes `throws Exception`, call sites are generally checked against this checked type. You should not add `throws Exception` just to "cover all unchecked exceptions" because it alters compile-time obligations and degrades contract readability.

Nor should you write `throws Throwable` or `throws Error` as a habit. A `throws Error` clause is valid because `Error` is unchecked, but `Error` is not an appropriate type to represent normal input or business-state errors.

**Practical rule:** if an unchecked exception has a clear condition that matters to users, document the error type and condition in Javadoc; repeating the type name in the `throws` clause is a choice of style and signature visibility.

## 9. Overriding, Interfaces, and `throws` with Unchecked Exceptions

For **checked exceptions**, an overriding method must not add new or broader checked types than the superclass/interface method. For **unchecked exceptions**, this restriction **does not apply**: an override may declare or throw additional `RuntimeException` and subclasses, even if the interface does not list them.

Runnable program `UncheckedOverrideDemo.java`:

~~~java
import java.util.Locale;

interface TextTransformer {
    /**
     * Transforms the input text.
     * @throws IllegalArgumentException if the text is blank
     */
    String transform(String raw);
}

class StrictTransformer implements TextTransformer {
    @Override
    public String transform(String raw) throws IllegalArgumentException {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("văn bản trống");
        }
        return raw.trim().toUpperCase(Locale.ROOT);
    }
}

public class UncheckedOverrideDemo {
    public static void main(String[] args) {
        TextTransformer transformer = new StrictTransformer();
        System.out.println(transformer.transform("  java  "));
        try {
            transformer.transform(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 UncheckedOverrideDemo.java
java UncheckedOverrideDemo
~~~

Exact stdout:

~~~text
JAVA
Lỗi: văn bản trống
~~~

`TextTransformer.transform` does not declare `throws`, but has an `@throws IllegalArgumentException` tag describing the precondition. `StrictTransformer.transform` validly adds `throws IllegalArgumentException` because it is an unchecked exception. The object is used through the `TextTransformer` interface type; the compiler still does not force callers to handle this type.

Regarding **API policy**, the fact that an override is allowed to throw unchecked exceptions **does not mean it should arbitrarily raise errors that violate the contract**. An implementation should respect the supertype method's semantics, documentation, and caller expectations. If an interface method accepts any string including empty ones, an implementation that arbitrarily rejects empty strings can break substitutability even though Java still allows it to compile.

If the same exception is published on both the interface and the implementation, you can use Javadoc's documentation inheritance mechanism according to the tool's rules, though you should inspect the actual generated documentation page. For implementation-specific conditions, document them on the implementation so users know the difference.

## 10. API Contracts: Documenting Preconditions, Postconditions, and State

For unchecked exceptions, the focus is usually on **API misuse or inappropriate state**, rather than an external failure condition that forces the caller to recover.

Suppose you design:

~~~java
/**
 * Sends a request while the client is open.
 *
 * @param request a non-null request
 * @throws NullPointerException if request is null
 * @throws IllegalStateException if the client is closed
 */
void send(Request request);
~~~

This is an **illustrative signature** (requiring `Request` and an enclosing class context). Callers understand they must ensure `request != null` and that the client's lifecycle is still valid. In the implementation, you can use `Objects.requireNonNull(request, "request")` to proactively check for `null` and throw a clear `NullPointerException`:

~~~java
// Illustrative snippet in a method with a request parameter.
java.util.Objects.requireNonNull(request, "request");
~~~

For non-`null` inputs with an invalid value domain, `IllegalArgumentException` is usually more suitable; for an object not in a state that permits the operation, `IllegalStateException` is usually clearer. However, type names do not replace **explicitly specifying the condition**. Different APIs may choose different types as long as they are consistent and documented.

Some principles for writing contracts:

1. State the operation and success conditions concisely in `@param` and the main description.
2. Use `@throws` for intentional failure conditions that callers genuinely need to avoid or may handle.
3. If a method must guarantee "no state change on invalid input", implement it so that guarantee holds and test it with failure cases.
4. If an API can fail due to the environment (I/O, connectivity, permissions), consider checked exceptions or a result model suited to the specific API design; do not automatically wrap every checked exception into an unchecked one.
5. Keep error types and message conventions consistent so logs are easier for users to read, but do not rely on comparing message strings to drive control flow.

## 11. Does Listing in `throws` Help Reflection or IDEs Recognize It?

Yes. The `throws` clause is part of a method/constructor's declared exception metadata and can be read via reflection APIs, for example:

~~~java
// Illustrative snippet, placed in a method with throws ReflectiveOperationException.
Class<?>[] declared =
        UncheckedDocumentationDemo.Counter.class
                .getDeclaredMethod("add", int.class)
                .getExceptionTypes();
~~~

With the `Counter.add` code in Section 6, `getExceptionTypes()` includes `IllegalArgumentException` and `IllegalStateException` as declared in the signature. It **does not mean a list of all runtime exceptions that could possibly occur**, and it **does not directly read the text of Javadoc `@throws` tags**.

IDEs and code-analysis tools can use both the signature and source documentation to display the contract. However, `throws` does not provide detailed conditions, while Javadoc typically lives in source code or generated documentation. Thus, the two information channels complement each other:

- **`throws`**: exception types declared in the signature, inspectable via reflection.
- **`@throws`**: condition descriptions for humans and API docs, without becoming new compile-time constraints.

If your API only writes `@throws IllegalArgumentException` without a `throws` clause, `getExceptionTypes()` cannot infer that type from Javadoc.

## 12. Impact on Compatibility and API Changes

Because unchecked exceptions are not bound by catch-or-declare, **adding `throws IllegalStateException` to a signature does not force callers to add `catch`**. However, changing actual behavior—for example, a new version starting to reject arguments that were previously accepted—can still break applications using the library.

Examples requiring caution:

- Previously `send(null)` meant "do nothing", but a later version throws `NullPointerException`: this is a behavioral contract change even though old code still compiles.
- `read()` previously allowed calls after `close()`, and now throws `IllegalStateException`: compatibility impact must be evaluated and documentation/tests updated.
- A class replaces `IllegalArgumentException` with `IllegalStateException` for the same case: callers may be catching one of the two specifically to recover; consider keeping exception semantics stable.
- Adding `throws IOException` (checked) to an API is different: existing callers may get compile errors if they do not yet handle the new checked type.

Do not confuse "no compile errors" with "no significant change for API users." The documented contract is an important part of public design.

## 13. Common Mistakes

| Misconception/mistake | Why it is incorrect | How to improve |
| --- | --- | --- |
| Thinking unchecked exceptions cannot be declared in `throws` | Java allows declaring subtypes of `RuntimeException`/`Error`. | You may list them when helpful; the compiler still does not require callers to catch them. |
| Thinking simply adding `throws IllegalArgumentException` forces callers to `catch` | This is an unchecked exception; the catch-or-declare obligation does not apply. | Write `@throws` conditions and handle at the call site when an appropriate strategy exists. |
| Thinking `@throws` must correspond to a `throws` clause | For unchecked exceptions, Javadoc can document them even when the signature omits them. | Distinguish Javadoc from language syntax. |
| Writing `@throws RuntimeException if an error occurs` | The condition is too vague to help write correct code. | Specify the exact type and situation, such as `delta <= 0`. |
| Listing every exception the JVM and dependencies might throw | Noisy documentation, hard to maintain, and easy to make false promises. | Only publish exceptions that belong to the contract and are valuable to callers. |
| Using `throws Exception` just to "warn that runtime errors exist" | Imposes checked `Exception` handling obligations and makes the signature overly broad. | Remove the broad declaration; use specific `@throws` if needed. |
| Adding an unchecked exception in an override and assuming it always satisfies the contract | The language allows it, but the behavior may break interface commitments. | Keep preconditions and postconditions consistent with the published contract. |
| Documentation states one condition, while code throws under a different condition | API users cannot rely on the documentation. | Keep code, Javadoc, and boundary-condition tests in sync. |
| Using `Error` as a normal business error | `Error` usually indicates an extraordinarily serious condition, not for input validation requests. | Prefer an exception suited to the API's semantics. |
| Logging, swallowing, or wrapping every unchecked exception indiscriminately | Can hide bugs or lose the cause chain. | Handle where a real resolution exists; when wrapping, preserve `cause`. |

## 14. Self-Check

1. **Is `NumberFormatException` checked or unchecked?** — Unchecked, because it belongs to the `IllegalArgumentException → RuntimeException` branch.
2. **Does calling `void save() throws IllegalStateException` require adding `try/catch`?** — No; this is an unchecked exception.
3. **If an API does not write `throws IllegalArgumentException`, can it still `throw new IllegalArgumentException(...)`?** — Yes.
4. **Does Javadoc `@throws IllegalArgumentException` affect the compiler's exception checking?** — No; it describes the API contract for human readers.
5. **Is it valid to write `@throws` for an unchecked exception while omitting it from the `throws` signature?** — Yes.
6. **Can an overriding method add `throws IllegalArgumentException` even if the interface does not declare it?** — Yes, at the language level; the behavioral contract must still be preserved.
7. **Why is `throws Exception` not a good way to document an `IllegalArgumentException`?** — `Exception` is checked and too broad, imposing compile-time obligations and obscuring the contract.
8. **When is `@throws IllegalStateException` useful?** — When there is a specific state condition, such as calling a method after the object has been closed.
9. **Does reflection `getExceptionTypes()` infer `@throws` tags?** — No; it reads the types declared in the signature, not Javadoc text.
10. **Can adding a new unchecked exception to API behavior break compatibility?** — Yes, behaviorally, even though caller source code may still compile.

## Reference Documentation

- [Java Language Specification 17 — §11.1.1, The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.1.1): classification of checked and unchecked exceptions.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): exception types required by the compiler to be caught or declared.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): the `throws` clause in methods.
- [Java Language Specification 17 — §8.4.8.3, Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding.
- [Javadoc Tool — `@throws` and `@exception` Tags](https://docs.oracle.com/en/java/javase/17/javadoc/javadoc.html): documentation syntax for describing exceptions.
- [Java SE 17 API — `Executable.getExceptionTypes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getExceptionTypes()): exception types declared in the signature.

**Remember:** for unchecked exceptions, the `throws` clause is optional under Java rules; the Javadoc `@throws` tag explains **when and why** an error occurs. A good API uses them purposefully to publish usage conditions while enforcing the contract accurately in source code.
