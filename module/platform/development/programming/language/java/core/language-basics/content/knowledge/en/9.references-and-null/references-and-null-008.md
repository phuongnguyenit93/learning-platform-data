# Recognizing `NullPointerException` and Placing Checks at the Right Point

> **Java core — language-basics / References and null**  
> **Environment:** JDK 17+; single standalone Java file, no external dependencies.  
> **Goal:** Recognize operations that can produce `NullPointerException` (NPE), trace the error location, choose between **checking `null` / default values / rejecting input**, and place checks **before operations requiring an object** instead of catching errors indiscriminately.

## 1. What Is NPE and Where Does It Occur?

`null` is a special value of **reference types**, meaning the variable currently does not reference any object. `NullPointerException` typically occurs when the program performs an operation that **requires an object** while the relevant reference is `null`.

Example:

~~~java
String text = null;
// int n = text.length(); // If executed: NullPointerException.
~~~

Common situations:

| Operation | Risky example | Reference that may be `null` |
| --- | --- | --- |
| Calling an instance method | `name.trim()` | `name` |
| Reading/writing an instance field | `user.status` | `user` |
| Reading array `length` or element | `items.length`, `items[0]` | **The `items` array**, if there is no array object yet |
| Using a reference array **element** | `items[0].length()` | `items[0]`, even when the array exists |
| Auto-unboxing a wrapper | `int n = boxed;` | `boxed` of type `Integer` |
| Iterating with enhanced `for` over an array | `for (String s : items) { ... }` | `items` if the array is `null` |

**Distinguish errors:** `items[10]` on an existing array lacking that index causes `ArrayIndexOutOfBoundsException`, **not** NPE. An empty `String` `""` is a valid object, different from a `null` reference.

## 2. Pinpointing the Exact Failure Point Before Adding Checks

When encountering an NPE, read the **stack trace**:

1. Find the `java.lang.NullPointerException` line and the first frame belonging to your code (for example, `Service.java:42`).
2. Open the exact line indicated; list every reference that could be `null` on that line, especially chained calls like `order.getCustomer().getName()`.
3. Trace back the source that created or received the value: method parameter, API result, uninitialized field, array element, repository return value, etc.
4. Check the **data contract**: is `null` a valid state or an invalid input?

Java 17 can print **detailed NPE messages** depending on JVM configuration, but do not hardcode entire stack traces or automatic messages into test cases: variable names and explanations can depend on environment/compilation. Use **line number + root cause + contract** to decide how to fix it.

Example of a multi-step call:

~~~java
// If customer can be null, check here before calling the method:
// Customer customer = order.getCustomer();
// if (customer == null) { /* handle missing customer branch */ }
// String name = customer.getName();
~~~

Do not automatically add `try { ... } catch (NullPointerException e) { }` to ignore the error: that approach can hide programming bugs and make subsequent corrupted data hard to detect.

## 3. Choosing Handling Based on the Meaning of `null`

There are **three main strategies**, not mutually interchangeable:

| Business situation | Appropriate check location | Solution |
| --- | --- | --- |
| `null` is **valid**, needs a default | Before reading optional data | `if (x == null) return fallback;` |
| `null` is **invalid** | Right at the input boundary, constructor, or public API | `Objects.requireNonNull(x, "x required")` |
| `null` is valid, but operations only happen when an object exists | Right before the dereference operation | `x != null && x.isReady()` |

Example of a safe conditional guard:

~~~java
String input = null;
boolean hasText = input != null && !input.isBlank();
System.out.println(hasText); // false, does not call input.isBlank().
~~~

`&&` performs **short-circuiting**: when the left-hand side is false, Java does not evaluate the right-hand side. **Order matters**; reversing it to `!input.isBlank() && input != null` will cause NPE if `input` is null. The boolean `&` operator **does not short-circuit**, so it is not an equivalent substitute when guarding a method call.

For comparing with a literal:

~~~java
String command = null;
System.out.println("START".equals(command)); // false, null-safe.
~~~

You can use `Objects.equals(a, b)` when **both** variables can be `null`. Be aware that `Objects.equals(null, null)` returns **true**; if simultaneously absent values must not be treated as equal, define an explicit rule.

## 4. Runnable Java 17+: NPE Scenarios and Handling

Create the file **`NullCheckDemo.java`**:

~~~java
import java.util.Objects;

public final class NullCheckDemo {
    private static final class Account {
        private final String label;

        Account(String label) {
            this.label = Objects.requireNonNull(label, "label required");
        }

        String label() {
            return label;
        }
    }

    private static String displayLabel(Account account) {
        if (account == null) {
            return "Guest"; // Null is a valid state for this API.
        }
        return account.label();
    }

    private static int requiredLength(Account account) {
        Objects.requireNonNull(account, "account required");
        return account.label().length();
    }

    public static void main(String[] args) {
        Account valid = new Account("Linh");
        Account missing = null;

        System.out.println("valid=" + displayLabel(valid));
        System.out.println("fallback=" + displayLabel(missing));
        System.out.println("guard="
                + (missing != null && missing.label().length() > 0));
        System.out.println("literalEquals=" + "Linh".equals(null));
        System.out.println("bothNullEquals=" + Objects.equals(null, null));
        System.out.println("requiredLength=" + requiredLength(valid));

        try {
            requiredLength(missing);
        } catch (NullPointerException e) {
            System.out.println("requiredError=" + e.getMessage());
        }

        String receiver = null;
        try {
            receiver.length();
        } catch (NullPointerException e) {
            System.out.println("receiverNpe=true");
        }

        String[] words = {null, "ok"};
        try {
            System.out.println(words[0].length());
        } catch (NullPointerException e) {
            System.out.println("elementNpe=true");
        }

        Integer boxed = null;
        try {
            int number = boxed;
            System.out.println("number=" + number);
        } catch (NullPointerException e) {
            System.out.println("unboxingNpe=true");
        }

        try {
            new Account(null);
        } catch (NullPointerException e) {
            System.out.println("constructorError=" + e.getMessage());
        }

        System.out.println("safeLength="
                + (words[1] != null ? words[1].length() : 0));
    }
}
~~~

Compile and run in the directory containing the file using Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 NullCheckDemo.java
java NullCheckDemo
~~~

**Exact expected output:**

~~~text
valid=Linh
fallback=Guest
guard=false
literalEquals=false
bothNullEquals=true
requiredLength=4
requiredError=account required
receiverNpe=true
elementNpe=true
unboxingNpe=true
constructorError=label required
safeLength=2
~~~

**Explanation:**

- `displayLabel(null)` returns `"Guest"` because the API **allows** an absent account; `requiredLength(null)` intentionally rejects it with the message `"account required"`.
- `missing != null && ...` stops before reading `label()`. The literal `"Linh".equals(null)` returns false. `Objects.equals(null, null)` returns true according to its contract.
- `receiver.length()` throws NPE because the receiver is null. The `words` array **is not null**, yet element `words[0]` is null so calling `length()` still throws NPE.
- The wrapper variable `Integer boxed` can be null; auto-converting to `int` (*auto-unboxing*) throws NPE.
- The `Account` constructor checks `label` **right where the object's invariant is established**, ensuring any successfully constructed `Account` always has a non-null `label`.
- The `catch` blocks are used to demonstrate certain errors in a controlled manner; in real applications, **fix the data contract / check at the right place**, rather than swallowing NPE and continuing as if nothing happened.

## 5. Where Should You Check for `null`?

**Principle:** Place checks where there is **enough context to decide how to handle it**, and before accessing the object. Not every variable needs repeated `if (x == null)` checks on every line.

- **Public API or constructor boundary:** If a value is required, use `Objects.requireNonNull` to catch bad input **early**, with a clear name/message. Internal code after that can rely on the established invariant.
- **Input boundary or potentially missing source:** If `null` is a valid state, decide to return a default, skip, ask the user to supply it, or report a business error before operating.
- **Before multi-level access chains:** Split into intermediate variables and check exactly which part can be null, rather than chaining calls and merely catching exceptions.
- **Each collection/array element:** Check both the **container** and the **element** if the data source can contain nulls.
- **Numeric wrappers:** Before operations that unbox `Integer`/`Long`/`Boolean`, confirm they are non-null or have a clear default rule.

`Objects.requireNonNull(x, "...")` still produces an **NPE**, yet it is a **deliberate contract-boundary check**, unlike accidentally dereferencing null deep inside. If a public API needs a different exception type (such as `IllegalArgumentException` for invalid input values), design it intentionally and consistently rather than changing it arbitrarily.

## 6. Common Mistakes

| Mistake | Consequence / fix |
| --- | --- |
| `name.equals("OK")` when `name` may be null | Can throw NPE; use `"OK".equals(name)` or check first |
| `input.isBlank() && input != null` | Wrong order: calls method before the guard |
| `input != null & input.isBlank()` | `&` evaluates both sides; use `&&` |
| Checking only `array != null` and then calling `array[0].length()` | Element `array[0]` can still be null |
| Auto-unboxing `Integer count = null` | NPE; define a fallback or require count to be non-null |
| Catching and ignoring every `NullPointerException` | Hides contract bugs; subsequent results may be wrong |
| Replacing every missing value with `""` or `0` | Can violate business logic; only use defaults if defined |
| Assigning `x = null` and thinking the object was deleted | Only variable x changed its reference; other aliases may still point to the object |

**Note:** `Optional` can represent optional results when an API suits it, but it is not a tool for wrapping every field and does not replace understanding whether `null` is valid data or an error. Avoid calling `Optional.get()` without checking because that introduces another error.

## 7. Short Exercises

**Exercise 1.** Given `String value = null;`. Predict the behavior of `value.length()`, `"OK".equals(value)`, and `value != null && value.length() > 0`. Point out which statement throws NPE and which ones are safe.

**Exercise 2.** Given `String[] list = new String[2];`. Why is `list.length` valid while `list[0].length()` throws NPE? Where should the guard be placed?

**Exercise 3.** Write a function taking a required non-null `String requiredCode`. Place `Objects.requireNonNull(requiredCode, "code required")` right at the start of the function, then use the variable safely in the rest.

**Exercise 4.** An API returns `null` when an account is not found. Choose between (a) returning the label `"Guest"`, (b) reporting "not found", (c) detecting invalid input — and explain how their contracts differ.

**Exercise 5.** Why does `Integer quantity = null; int total = quantity * 2;` fail? Write two intentional ways to handle it: requiring quantity or using a business-agreed default value.

### Remember

**An NPE usually signals that code tried to use a `null` reference as an object.** Read the stack trace carefully to find the failing operation; decide whether `null` is valid, and **place checks at the data boundary or right before dereferencing**. Use `&&` to guard, `Objects.requireNonNull` for required values, and null-safe comparisons when needed. Avoid hiding NPEs with empty `catch` blocks or scattering meaningless defaults.
