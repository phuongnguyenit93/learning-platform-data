# Inspecting the Actual Selector Type When Debugging Java Pattern Matching

## 1. The Problem: Why Didn't the Case Run as Expected?

With pattern matching in Java, many debugging errors stem from confusing the **static type** of the expression after `switch (...)` with the **actual runtime type** of that expression's value.

For example, a parameter declared as `Object selector` might hold a `String`, `Integer`, `Long`, business record, proxy, or `null`. A `case Integer n` branch does not match `Long` even though both represent whole numbers, and `case String s` does not match `StringBuilder` even though both contain characters. Looking only at `Object` in the method signature does not tell you which branch will be selected.

The skill of **“Inspecting the actual selector type”** combines observing the runtime value/type with analyzing **patterns, guards, case order, null handling, and record structure** to explain accurately why a `switch` or `instanceof` branch matches or fails to match.

After this lesson, you will be able to:

- Distinguish between the `static type` and `runtime class` of a selector, and know when to use `getClass()`, `getName()`, and `getSimpleName()`.
- Interpret debugging output for `Integer`, `Long`, `Double`, `String`, `CharSequence`, records, null components, and a null selector.
- Distinguish between a **type pattern that does not match** and a **type pattern that matched but whose `when` guard evaluated to false**.
- Inspect the exact value actually passed into `switch`, avoiding mixing up an outer object with an inner component.
- Use logs and breakpoints safely without causing the selector to be re-evaluated with side effects.
- Write tests that verify the right branch based on specific runtime types.

**Version:** Type patterns with `instanceof` were standardized in Java 16 (JEP 394). Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) became official in **Java 21**. The complete runnable program in Section 8 is compatible with **JDK 21+** and does not require `--enable-preview`.

## 2. How Does Static Type Differ from Runtime Type?

Consider the following snippet:

```java
Object selector = 7L;

System.out.println(selector.getClass().getName());       // java.lang.Long
System.out.println(selector.getClass().getSimpleName()); // Long
System.out.println(selector instanceof Integer);         // false
System.out.println(selector instanceof Long);            // true
System.out.println(selector instanceof Number);          // true
```

The variable `selector` is declared with type **`Object`**, but the expression `7L` has primitive type `long` and is **autoboxed** into a `Long` object when assigned to `Object`. Therefore, the runtime class is `java.lang.Long`.

Three levels of information must be kept distinct:

| Concept | Example | Role When Debugging |
| --- | --- | --- |
| Static type of the selector | `Object` | Used by the compiler to check whether patterns are valid and whether the switch is exhaustive. |
| Runtime type of the value | `java.lang.Long` | Explains why `case Long l` matches and `case Integer i` does not. |
| Additional condition after matching | `when n > 0` | Determines whether the branch continues to be selected; the right runtime class alone is not enough. |

Do not use the static type to infer the runtime type. A `Number n` parameter may point to an `Integer`, `Long`, `Double`, `BigDecimal`, or another implementation of `Number`. An interface parameter may point to any valid implementation.

**Important:** `getClass()` only reflects the **class of the actual object**. It does not by itself prove which branch an object will match if branches also have `when` guards or nested record patterns.

## 3. How to Observe the Runtime Type Without Causing a NullPointerException

### 3.1. A Null-Safe Helper

```java
static String runtimeType(Object value) {
    return value == null ? "null" : value.getClass().getName();
}
```

If `value` is non-null, `value.getClass()` returns the `Class<?>` object representing the runtime class. `getName()` is often useful when you need the fully qualified name to distinguish two classes with the same short name in different packages.

Example:

```java
Object a = "java";
Object b = 12;
Object c = 12L;
Object d = null;

System.out.println(runtimeType(a)); // java.lang.String
System.out.println(runtimeType(b)); // java.lang.Integer
System.out.println(runtimeType(c)); // java.lang.Long
System.out.println(runtimeType(d)); // null
```

A **common mistake** is writing `selector.getClass().getName()` before checking for `null`. If `selector` is null, this debugging statement itself throws a `NullPointerException` and hides the root cause. Always check for null or use a helper.

### 3.2. Choosing getName or getSimpleName?

- `getClass().getSimpleName()`: short name such as `Integer`, `Ready`, `StringBuilder`; easy to read in demos, but **not unique** across packages and can be empty for some anonymous classes.
- `getClass().getName()`: binary/runtime name, such as `java.lang.Integer` or `com.acme.dto.Ready`; nested classes may contain `$`.
- `getClass().getCanonicalName()`: canonical name if available; may return `null` for local/anonymous classes and certain other class forms, so it is not suitable by default for all logs.
- `getClass().getTypeName()`: type name intended for display purposes, useful when you already have a `Class<?>` object.

In the program in Section 8, the helper uses **`getSimpleName()`** so the output is short and easy to compare; when debugging real projects, prefer the fully qualified name and add request/branch context if needed.

### 3.3. Arrays, Wrappers, and Primitive Types

If you assign `int x = 7; Object o = x;`, the variable `o` holds an `Integer` due to boxing. There is no “runtime `int` object” that `getClass()` returns in this case.

For arrays, `getName()` uses binary representations such as `[Ljava.lang.String;` (`String[]`) or `[I` (`int[]`); do not confuse these with ordinary package names. If you need to debug an array:

```java
static String arrayInfo(Object value) {
    if (value == null) return "null";
    Class<?> c = value.getClass();
    if (!c.isArray()) return "not-array:" + c.getName();
    return "array-component:" + c.getComponentType().getTypeName();
}
```

This snippet illustrates querying `Class.isArray()` and `getComponentType()`; it is not intended to replace pattern matching with reflection.

## 4. Placing Logs in the Right Spot: Which Expression Is the Switch Selector?

Suppose a record holds data of varying types:

```java
record Envelope(Object payload) {}

static String route(Envelope envelope) {
    Object selector = envelope.payload();
    return switch (selector) {
        case String s -> "text:" + s;
        case Integer n -> "integer:" + n;
        case null -> "missing payload";
        default -> "other payload";
    };
}
```

If you debug `envelope.getClass()`, you only get `Envelope`, which does not explain why `case String` or `case Integer` in this snippet was selected. **The switch selector is `envelope.payload()`**, not `envelope` itself.

Observe the exact value:

```java
Object selector = envelope.payload();
String actualType = selector == null
        ? "null"
        : selector.getClass().getName();

// Use actualType for safe logging (no need to log raw payload).
return switch (selector) {
    case String s -> "text:" + s;
    case Integer n -> "integer:" + n;
    case null -> "missing payload";
    default -> "other payload";
};
```

In addition, **do not call a getter or method with side effects again just for debugging**. For example:

```java
// Avoid this when source.next() can return a different element on each call.
System.out.println(source.next().getClass().getName());
return switch (source.next()) {
    // Cases...
};
```

This is only a counterexample snippet (`source` and the cases are not declared), not a complete Java file. Two calls to `source.next()` can return two different values: the printed type is not the actual type of the selector that entered the switch.

Instead:

```java
// Illustration when source.next() returns Object.
Object selector = source.next();
System.out.println(selector == null ? "null" : selector.getClass().getName());
return switch (selector) {
    case String s -> "text:" + s;
    case null -> "missing";
    default -> "other";
};
```

In practice, you do not have to print to stdout; you can use a logger or debugger. The core rule is to **evaluate the selector once and use that same value for both observation and branching**.

## 5. Correct Runtime Type, Yet the Case Still Doesn't Run: Check Branch Order

When there are multiple type patterns related by inheritance, a broader branch and a narrower branch can match the same object.

Safe example (Java 21):

```java
static String numberKind(Object selector) {
    return switch (selector) {
        case Integer n -> "integer:" + n;
        case Number n -> "number:" + n;
        case null -> "missing";
        default -> "other";
    };
}
```

If the runtime class is `Integer`, both the `Integer` and `Number` patterns are type-compatible, but the **`Integer` branch comes first** and is selected. If the runtime class is `Long`, the `Integer` branch does not match, and the `Number` branch matches.

If you swap the two branches:

```java
// Does not compile: case Integer is dominated by the preceding case Number.
return switch (selector) {
    case Number n -> "number:" + n;
    case Integer n -> "integer:" + n;
    default -> "other";
};
```

The Java 21 compiler detects that the `Integer` branch is **dominated** by the broader `Number` branch. This is a compile-time error, **not** a runtime situation where the wrong `case` executed.

With an `if / else if` chain, a broad condition placed earlier can simply prevent a specific branch from being chosen; with a pattern switch, the compiler adds static checks that catch many shadowed cases.

### Do Not Confuse String with CharSequence

A `StringBuilder` implements `CharSequence`, but it is not a `String`:

```java
Object selector = new StringBuilder("abc");
System.out.println(selector instanceof String);       // false
System.out.println(selector instanceof CharSequence); // true
```

If the code only has `case String s`, a runtime class of `StringBuilder` will fall through to the fallback branch or a broader `CharSequence` branch, depending on how you wrote the `switch`.

**Debugging tip:** Record the **actual runtime class**, then ask: is that class a subtype/implementation of the pattern type being tested? Only after that should you inspect guards and inner data.

## 6. Case Type Matches, but the when Guard Is False

A `when` clause adds a condition **after the pattern matches**. Therefore, the runtime class does not change when the guard is false; Java simply continues checking the remaining matching branches.

```java
static String classifyText(Object selector) {
    return switch (selector) {
        case String text when text.isBlank() -> "String:blank";
        case String text -> "String:text=" + text.strip();
        case null -> "null";
        default -> "other";
    };
}
```

Both inputs `"  "` and `"java"` have the runtime class `String`, yet they enter different branches. To explain why, you must inspect **the value and the expression `text.isBlank()`**, not just the class name.

During a debugging session, you can safely log the type and the guard result:

```java
if (selector instanceof String text) {
    boolean blank = text.isBlank();
    System.out.println("runtimeType=String, blank=" + blank);
}
```

This is an illustrative snippet using the already-captured selector. Avoid logging the full raw text if it is sensitive or very large; in that case, log only `blank`, the length, or redacted metrics.

**Distinguish three states:**

1. **Pattern does not match:** for example, the selector is `Integer`; the guard `text.isBlank()` is not evaluated.
2. **Pattern matches, guard is false:** the selector is a non-blank `String`, so the branch with `when` is skipped.
3. **Pattern matches, guard is true:** the selector is a blank `String`, so that branch is selected.

Place a specific branch with `when` before an unguarded branch of the same type; if the unguarded branch is placed first, the compiler may report `dominated case label` on the specific branch.

## 7. Record Patterns: Inspect Both the Selector Type and Inner Components

In Java 21:

```java
record Ready(String id, Object payload) {}
```

The following branch:

```java
// Snippet in a switch expression with an Object selector.
case Ready(var id, var payload) when payload instanceof String text
        -> "Ready:" + id + ":string=" + text;
```

has two layers of checks:

- The selector must be a non-null `Ready` record instance.
- The `payload` component must be a non-null `String` for the guard `payload instanceof String text` to be true.

If the selector is `new Ready("R2", 42)`, **the selector's type is still `Ready`**, but `payload` has runtime class `Integer`. The pattern `Ready(var id, var payload)` matches; the guard `payload instanceof String text` does not. When an unguarded `case Ready(var id, var payload)` branch follows, it will be selected.

If the selector is `new Ready("R3", null)`, the outer record still matches and `var payload` can bind `null`; however, the guard `payload instanceof String text` is false. This is **different** from a nested pattern:

```java
record Message(String text) {}
record Box(Object item) {}

// Snippet with an Object selector:
case Box(Message(var text)) -> "message:" + text;
```

Here `Box(Message(...))` does not match if the `item` component is null or is not a `Message` record. Conversely, when `Message` exists but its `text` component is null, `Message(var text)` can still match and bind `text` to null. Set breakpoints or logs at the right layer:

- **Outer selector layer:** `typeName(selector)`.
- **Component layer:** `typeName(payload)` or `typeName(item)`.
- **Guard layer:** expressions like `payload instanceof String`, `text != null`, `!text.isBlank()`, and business conditions.

Do not assume “if the selector is `Ready`, then payload is definitely a String” when the component is declared as `Object`. The type system does not guarantee that. If the business contract requires stricter guarantees, use a specific component type and appropriate validation.

## 8. Complete Java 21 Program: Printing the Actual Type and Selected Branch

Create the file **`SelectorRuntimeTypeDemo.java`**:

```java
public class SelectorRuntimeTypeDemo {
    sealed interface Signal permits Ready, Failed {}
    record Ready(String id, Object payload) implements Signal {}
    record Failed(int code) implements Signal {}
    record Box(Object item) {}

    static String typeName(Object value) {
        return value == null ? "null" : value.getClass().getSimpleName();
    }

    static String route(Object selector) {
        return switch (selector) {
            case null -> "selector:null";
            case String text when text.isBlank() -> "String:blank";
            case String text -> "String:text=" + text.strip();
            case Integer number -> "Integer:" + number;
            case Number number -> "Number:" + typeName(number) + "=" + number;
            case Ready(var id, var payload) when payload instanceof String text
                    -> "Ready:" + id + ":string=" + text;
            case Ready(var id, var payload)
                    -> "Ready:" + id + ":payload=" + typeName(payload);
            case Failed(var code) -> "Failed:" + code;
            case Box(var item) -> "Box:item=" + typeName(item);
            default -> "other:" + typeName(selector);
        };
    }

    static String inspect(Object selector) {
        return "type=" + typeName(selector) + " | branch=" + route(selector);
    }

    public static void main(String[] args) {
        Object[] samples = {
            "  java  ", "  ", 7, 7L, 3.5,
            new Ready("R1", "ok"), new Ready("R2", 42),
            new Ready("R3", null), new Failed(404),
            new Box(null), new Box(new StringBuilder("x")),
            new StringBuilder("text"), new Object(), null
        };
        for (Object sample : samples) {
            System.out.println(inspect(sample));
        }
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 SelectorRuntimeTypeDemo.java
java SelectorRuntimeTypeDemo
```

**Expected output:**

```text
type=String | branch=String:text=java
type=String | branch=String:blank
type=Integer | branch=Integer:7
type=Long | branch=Number:Long=7
type=Double | branch=Number:Double=3.5
type=Ready | branch=Ready:R1:string=ok
type=Ready | branch=Ready:R2:payload=Integer
type=Ready | branch=Ready:R3:payload=null
type=Failed | branch=Failed:404
type=Box | branch=Box:item=null
type=Box | branch=Box:item=StringBuilder
type=StringBuilder | branch=other:StringBuilder
type=Object | branch=other:Object
type=null | branch=selector:null
```

**Explanation by group:**

1. `"  java  "` and `"  "` are both `String`. The second satisfies `isBlank()` so it enters `String:blank`; the first is not blank so the next branch strips whitespace and returns `String:text=java`.
2. `7` is boxed into `Integer` and enters `case Integer number`. `7L` is boxed into `Long`, **does not match Integer**, but matches `Number`. `3.5` is `Double`, which also matches `Number`.
3. `Ready("R1", "ok")`: the selector is `Ready`; `payload` is `String`, so the guard `payload instanceof String text` is true.
4. `Ready("R2", 42)`: the selector is still `Ready`; `payload` is `Integer`, so the guard fails and it enters the unguarded `Ready` branch.
5. `Ready("R3", null)`: the selector is non-null, but **the `payload` component is null**; the unguarded `Ready` branch returns `payload=null`.
6. `Failed(404)` and `Box(...)` are handled by their corresponding record patterns. `Box(null)` demonstrates that the outer record matches even when a `var` component is null.
7. `StringBuilder` can be used as a `CharSequence`, but it is not a `String`. Because the example has no `CharSequence` branch, it falls into `default`.
8. `new Object()` does not belong to any supported type, so it falls into `default`.
9. A null selector enters `case null`, and the `typeName` helper avoids calling `getClass()` on null.

**Note:** The `typeName` helper uses `getSimpleName()` for concise illustration and stable stdout. In real systems, use `getName()` to distinguish classes with the same name from different packages; add class loader/module details when investigating complex loading issues.

## 9. Debugging Workflow When a Switch Branch Is Not Selected

When a case that “should have matched” does not run, follow this sequence:

### Step 1: Identify the actual selector expression

Read the entire expression after `switch (...)`. If the selector is `message.payload()`, observe **the result of `payload()`**, not the class of `message`. If it is a call with side effects, assign it to a local variable first so you do not accidentally evaluate it twice.

### Step 2: Log the runtime class in a null-safe way

```java
Object selector = obtainSelector();
String runtimeClass = selector == null
        ? "null"
        : selector.getClass().getName();
System.out.println("selector type: " + runtimeClass);
```

This is an illustrative snippet; `obtainSelector()` represents an application method and is not declared in the runnable file in Section 8. In real debugging, avoid printing full sensitive data, large objects, or data whose `toString()` contains personal information.

### Step 3: Compare the type against each case in order

Take the observed runtime class and determine whether it is a subtype/implementation of the type in the case. For `Long`, `case Integer` does not match even though both are `Number`. For `StringBuilder`, `case String` does not match, whereas `CharSequence` can match.

### Step 4: Separate type checking from the guard

When the type matches but `when` is false, Java continues checking other cases. Set a breakpoint on the guard or evaluate the guard expression written in code separately. Do not confuse a false guard with the wrong runtime class.

### Step 5: Inspect components of nested record patterns

The outer selector may be the right record, but a component in a position requiring another record may be null or the wrong type, causing the entire pattern not to match. If a component is bound with `var`, check null and the value separately to understand the guard.

### Step 6: Check `case null`, `default`, and exceptions

If the selector is null, confirm whether there is a `case null` branch or an appropriate null-precheck policy. Do not assume `default` always catches null: a pattern switch without null handling can throw `NullPointerException`. For an `Object` selector, `default` covers unlisted types.

### Step 7: Add a regression test for the offending runtime type

After finding a real input that caused a different branch to be chosen than expected, save a representative input as a test: `Long` instead of `Integer`, `StringBuilder` instead of `String`, a null inner record, or a false guard. The test should assert the **public output** and appropriate error, not just `getClass()`.

## 10. Special Cases When Debugging Types

### 10.1. Generics Are Not Fully Visible via getClass()

For example, `new ArrayList<String>()` and `new ArrayList<Integer>()` both have the runtime class `java.util.ArrayList`. `getClass()` cannot tell you the exact type argument of each instance due to **type erasure**.

Do not write:

```java
// Does not compile when raw is Object: List<String> is not reifiable.
if (raw instanceof java.util.List<String> strings) {
    System.out.println(strings.size());
}
```

If you need to inspect runtime data:

```java
if (raw instanceof java.util.List<?> values) {
    for (Object element : values) {
        if (element instanceof String text) {
            System.out.println("String element length=" + text.length());
        }
    }
}
```

These are standalone conceptual snippets that must be placed inside a class/method with a `raw` variable. When debugging a `List<?>` case, distinguish between the **container type** and the **element type**.

### 10.2. Proxies and Framework-Generated Classes

An object passed under an interface or base class type may be a framework-generated proxy. In that case, `getClass().getName()` may print a dynamically generated class name rather than the business interface name you expect.

This does **not automatically** make `instanceof MyInterface` false: if the proxy actually implements the interface, a type pattern for that interface can still match. Check the actual type relationship and wrapper/proxy structure rather than comparing class name strings alone.

If you need to diagnose a class loader or duplicate class name issue across modules, you can inspect `selector.getClass().getClassLoader()` and `selector.getClass().getModule()`, but do not flood logs or jump to a class-loader error conclusion without evidence.

### 10.3. getClass() vs. instanceof

Do not replace a type pattern with an exact class comparison just because you are debugging:

```java
Object selector = new StringBuilder("abc");

System.out.println(selector.getClass() == CharSequence.class); // false
System.out.println(selector instanceof CharSequence);          // true
```

Comparing classes with `==` requires **the exact same `Class` object**, whereas `instanceof` uses the **assignability/implementation relationship**. For interfaces and subtypes, the two checks can produce different results. When explaining a case match, the `instanceof` result (or the case's pattern rules) is what aligns with the behavior under investigation.

### 10.4. Sealed Hierarchies and Static Types

If a selector has the static type `Signal`, which is a sealed interface, and all permitted implementations are covered by cases, the compiler can prove a `switch expression` is exhaustive without a `default`. That relies on the **static type system and permitted subtypes**, and does not mean the data inside each subtype is valid.

In the example program, `route(Object selector)` accepts the open type `Object` and therefore has a `default`. Even though the `Ready`/`Failed` records implement `Signal`, the selector's static type is still `Object`, and Java cannot use that sealed hierarchy alone to treat the entire switch as exhaustive.

### 10.5. ClassCastException, MatchException, and Business Logic Errors

If legacy code performed `(SomeType) selector`, a type mismatch could throw `ClassCastException`. Type patterns in `switch` often let you express non-matching branches instead of casting directly, though not every conversion automatically preserves the exact error behavior.

With record patterns and sealed switches, if no branch can be selected in a switch that was previously compiled as exhaustive—under unusual scenarios such as binary incompatibility—the runtime can throw `MatchException`. This is not a normal fallback behavior you should intentionally manufacture in an application.

If the runtime type is right but the business data is wrong (for example, `Ready` contains an empty payload), the bug may lie in the guard/validation rather than in the `instanceof` mechanism. Before adding a cast or a broad `default`, determine the exact intended semantics.

## 11. Test Matrix to Preserve Debugging Results

From the cases in the runnable example, you can write tests using this matrix:

| Selector | Runtime type | Expected case/guard | Notable result |
| --- | --- | --- | --- |
| `"  java  "` | `String` | Guard `isBlank()` false, next String branch | `String:text=java` |
| `"  "` | `String` | Guard `isBlank()` true | `String:blank` |
| `7` | `Integer` | `case Integer` | `Integer:7` |
| `7L` | `Long` | `case Number` | `Number:Long=7` |
| `3.5` | `Double` | `case Number` | `Number:Double=3.5` |
| `Ready("R1", "ok")` | `Ready` | Guard payload is String true | `Ready:R1:string=ok` |
| `Ready("R2", 42)` | `Ready` | Guard false; unguarded Ready | `Ready:R2:payload=Integer` |
| `Ready("R3", null)` | `Ready` | Guard false due to null payload | `Ready:R3:payload=null` |
| `Failed(404)` | `Failed` | `case Failed` | `Failed:404` |
| `Box(null)` | `Box` | `case Box`, null item | `Box:item=null` |
| `StringBuilder("text")` | `StringBuilder` | No compatible case in the example | `other:StringBuilder` |
| `new Object()` | `Object` | `default` | `other:Object` |
| `null` | No runtime class | `case null` | `selector:null` |

**Do not test only the logs.** Tests should call the actual routing function and verify meaningful results. When a `when` condition is modified, a regression test such as `Ready("R2", 42)` or a blank string will catch unintended branch changes.

If using JUnit 5 (in a project with the JUnit Jupiter dependency), you can verify with `assertEquals`:

```java
// JUnit 5 snippet; requires SelectorRuntimeTypeDemo and JUnit Jupiter on the test classpath.
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SelectorRuntimeTypeTest {
    @Test
    void longUsesNumberCaseNotIntegerCase() {
        assertEquals(
            "Number:Long=7",
            SelectorRuntimeTypeDemo.route(7L)
        );
    }

    @Test
    void nullRecordComponentDoesNotCrash() {
        assertEquals(
            "Ready:R3:payload=null",
            SelectorRuntimeTypeDemo.route(
                new SelectorRuntimeTypeDemo.Ready("R3", null)
            )
        );
    }

    @Test
    void wrongTypeUsesFallback() {
        assertEquals(
            "other:StringBuilder",
            SelectorRuntimeTypeDemo.route(new StringBuilder("x"))
        );
    }
}
```

These JUnit tests are extended examples requiring a test runner configuration and dependencies; they are not part of the standalone program that only needs `javac/java` in Section 8. Place the test file in the same package as the demo class because the methods and records here have package-private access.

## 12. Common Debugging Mistakes

| Symptom or Misconception | Possible Cause | How to Investigate |
| --- | --- | --- |
| “Selector is Object, so no case knows the type” | Confusing static type with runtime type. | Log the runtime class of the actual selector; type patterns can still match. |
| `case Integer` does not run for `7L` | `7L` is boxed as `Long`, not `Integer`. | Print `getName()` and test `case Long`/`Number` per contract. |
| `case String` does not run for `StringBuilder` | `StringBuilder` does not extend `String`. | Check `instanceof CharSequence` if you want to support that type. |
| Logged class is `Envelope`, but switch cases check `payload` | Logging the outer object instead of the inner selector. | Assign the accessor result to a variable and log that variable. |
| Selector is `String`, but the `when` branch does not run | Guard is false. | Inspect the value/guard; add boundary tests. |
| Selector is `Ready`, but the guarded `String` payload branch does not run | The `payload` component has another type or is null. | Log the type of `payload` separately and check `instanceof String`. |
| Nested record pattern does not match even though outer record has the right type | Inner record may be null or the wrong type. | Inspect each component in the record tree. |
| Logging `selector.getClass()` throws NPE | Selector is null; log ran before checking. | Use a null-safe helper and handle `case null`. |
| `case Number` before `case Integer` causes a compile error | Narrower case is dominated. | Place `case Integer` before `case Number`. |
| `getClass() == Interface.class` is false even though interface pattern matches | Exact-class equality differs from `instanceof`. | Use type relationships and the proper runtime class. |
| Two `List` instances with different generics have the same `getClass()` | Type erasure. | Inspect elements or appropriate metadata/schema. |
| Runtime type prints differently across environments | Proxy/class loader/class name differs at runtime. | Check full name, interfaces, and loader/module when needed. |
| Adding logs changes which branch executes | Selector or accessor is called again with side effects. | Capture the selector once and observe that same value. |
| Logging the raw selector leaks information | Logs contain sensitive data or custom `toString()`. | Log only the type, guard state, and masked/reduced details. |

## 13. Self-Check Exercises

### Exercise A — Predict the Case from the Runtime Class

Given this Java 21 snippet:

```java
static String choose(Object selector) {
    return switch (selector) {
        case null -> "missing";
        case Integer n -> "int:" + n;
        case Number n -> "number:" + n.getClass().getSimpleName();
        case CharSequence s -> "chars:" + s.length();
        default -> "other";
    };
}
```

Predict the output:

1. `choose(2)` → `int:2` (boxed as Integer).
2. `choose(2L)` → `number:Long`.
3. `choose(2.5)` → `number:Double`.
4. `choose("abc")` → `chars:3`.
5. `choose(new StringBuilder("hi"))` → `chars:2`.
6. `choose(null)` → `missing`.
7. `choose(new Object())` → `other`.

Explanation: `Number` covers the numeric wrappers here but not `String`; `CharSequence` accepts both `String` and `StringBuilder`. Moving `case Number` before `case Integer` will cause the compiler to reject it due to domination.

### Exercise B — Debugging the Wrong Selector

A service does:

```java
record Request(Object body) {}

// Snippet inside a method receiving Request request:
switch (request.body()) {
    case String text -> System.out.println("text");
    default -> System.out.println("other");
}
```

A developer logs `request.getClass().getName()` and gets `Request`, then concludes the `String` branch never runs. Where is the conclusion wrong?

**Answer:** The selector is **`request.body()`**, not `request`. You must observe the runtime type of `body`. If `body` is a `String`, `case String` can still match; if `body` is null, this switch needs explicit null handling per contract, such as `case null`. When debugging, capture `Object selector = request.body();` first so both the log and the switch use the exact same value.

### Exercise C — Same Runtime Class, Different Branch

In `classifyText` from Section 6, explain why selectors `" "` and `"Java"` both have `java.lang.String` yet produce different results.

**Answer:** The `String` pattern matches both. Then the guard `text.isBlank()` is true for the blank string and false for `"Java"`. When the guard is false, the unguarded `String` branch handles it. Therefore, **runtime type is only part of the answer** and does not replace checking the data and guards.

## 14. Checklist for Investigating Pattern Matching Bugs

1. **Right selector?** Distinguish `switch (value)` from `switch (value.component())`.
2. **Evaluated once?** Do not log by calling a getter again if it can mutate state.
3. **Null selector?** Use null-safe logging and check `case null` or the NPE contract.
4. **What is the specific runtime type?** Use `getName()` for the fully qualified name; avoid looking only at the static type.
5. **Boxing/subtype/interface/proxy involved?** Check type relationships rather than comparing class names as strings.
6. **Broader or narrower pattern first?** Check for domination and branch ordering.
7. **Is the `when` guard false?** Record the actual condition and test both sides of the boundary.
8. **Null or wrong-type inner layer in a record pattern?** Check the runtime type of the component at the right position.
9. **Type erasure or arrays?** `getClass()` only gives the runtime class, not generic type arguments.
10. **Reproducible test?** Save the failing input and expected result to prevent regressions.
11. **Safe logging?** Do not print raw tokens, sensitive payloads, personal data, or uncontrolled `toString()` output.

**Remember:** When a pattern switch branch does not run as expected, start from the **actual selector value** and **runtime type**, then check **type relationships, guards, nested record components, case order, and null handling** in turn. Runtime type is a key diagnostic fact, but it is not the sole decider of the entire pattern-matching outcome.

**References:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Java SE 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Java SE 21 JLS — switch expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28), [Class API (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).
