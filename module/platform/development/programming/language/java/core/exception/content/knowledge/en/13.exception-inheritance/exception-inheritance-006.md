# Overloading, Declared Reference Types, and the Set of Exceptions to Handle in Java

When a Java class has multiple methods with the same name but different parameter lists (*method overloading*), developers often assume the JVM will select the version based on the **actual runtime type of the object** and thereby determine which exceptions must be caught. In reality, Java has two separate steps:

1. **At compile time:** the compiler selects the applicable and most specific **overload** based on the method name, the methods visible from the **static type of the receiver expression** (*receiver*), and the number and **compile-time types** of the arguments. Whether the selected method declares `throws IOException` or `throws SQLException` is **not a criterion for overload resolution**.
2. **After selecting the overload:** the compiler determines **the checked exceptions that can be thrown by the call** according to the contract of the selected method, and requires catching or declaring `throws` for any unhandled checked types. At runtime, **overriding** can dispatch to a subclass method body, but it does not automatically switch the call to a different overload.

That is why the exact same `String` object can enter two different overloads depending on whether it is held in a variable of type `String` or `Object`, and why the same subclass object can be checked for `throws IOException` differently depending on whether the reference is declared with the parent or child class type.

This article explains, with runnable Java 17+ examples: overload resolution, static vs. runtime types, overriding, checked exception checking, `null` and ambiguous overloads, primitive widening/boxing, generics, constructor overloading, overriding limits, and how to design easy-to-use exception APIs.

## 1. Distinguishing Overloading and Overriding

Both concepts can appear in the same program, but they solve two different problems:

| Criterion | Overload | Override |
| --- | --- | --- |
| Nature | Multiple methods with the same name but **different parameter signatures** | A subclass redefines an inherited method with an override-compatible signature |
| Signature selection time | **Compile-time** | The call signature is still determined at compile-time |
| Execution body selection | The body of the selected overload, which may still undergo dispatch if that overload is overridden | **Runtime dispatch** for instance methods can select the implementation in the subclass |
| Role of `throws` | Does not distinguish two overloads | An override **must not broaden checked exceptions** beyond the parent method's contract |
| Role of reference static type | Determines the visible set of candidate methods | Determines the compile-time contract at the call site |
| Role of object runtime type | Does not automatically select another overload | Can determine the actual implementation of the selected signature |

Example overload declaration:

```java
void load(Object value) throws java.io.IOException { /* ... */ }

void load(String value) throws java.text.ParseException { /* ... */ }
```

The two methods above have different parameter type lists: `Object` versus `String`, so Java allows them to have different `throws` clauses. Conversely, two methods that **differ only in `throws`** with identical parameter lists **do not form a valid overload**.

In a Java program, `throws` serves to describe the **checked exception contract of the method**, not as a component that makes an overload signature unique.

## 2. Complete Example: Same `String` Object, Two Argument Reference Types

Save as `OverloadCheckedDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class OverloadCheckedDemo {
    static void inspect(Object value) throws IOException {
        System.out.println("selected=Object");
        throw new IOException("object-path");
    }

    static void inspect(String value) throws ParseException {
        System.out.println("selected=String");
        throw new ParseException("string-path", 0);
    }

    public static void main(String[] args) {
        String narrow = "hello";
        Object broad = narrow;

        try {
            inspect(narrow);
        } catch (ParseException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        try {
            inspect(broad);
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        try {
            inspect((String) broad);
        } catch (ParseException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 OverloadCheckedDemo.java
java OverloadCheckedDemo
```

Output:

```text
selected=String
caught=string-path
selected=Object
caught=object-path
selected=String
caught=string-path
```

The three calls clearly illustrate:

1. `inspect(narrow)`: the argument expression has static type `String`. Both `inspect(Object)` and `inspect(String)` are applicable, but `String` is more specific, so the compiler selects the `String` version and `ParseException` must be handled.
2. `inspect(broad)`: the same runtime object, but the argument expression has static type `Object`. `inspect(String)` is not applicable to an argument of type `Object` without a cast; the compiler selects `inspect(Object)` and `IOException` must be handled.
3. `inspect((String) broad)`: casting gives the argument expression static type `String`. The call again selects the `inspect(String)` overload and `ParseException` must be handled. Casting is only safe when the actual object is compatible; for a non-`String` object, the cast can throw `ClassCastException`.

**Conclusion:** checked exceptions at the call site are determined from **the overload selected by the compiler**. Do not decide `catch` blocks based on `broad.getClass()` or on knowing that the runtime object holds text.

## 3. What Steps Does the Compiler Follow to Select an Overload?

According to JLS §15.12, processing a method invocation consists of the following major steps:

1. Determine the **type to search for the method** and the method name. For a call `receiver.method(...)`, the declared type of `receiver` limits the set of methods visible at the call site.
2. Identify methods with a matching name, argument count, and applicability based on the **static types of the argument expressions**, generic type inference, and valid conversion rules.
3. Prioritize applicability phases: strict invocation (*strict invocation*), invocation allowing wider conversions (*loose invocation*, including boxing/unboxing), and then variable-arity (varargs) invocation when needed.
4. Choose the **most specific** method among the applicable candidates in the phase used. If there is no single suitable choice, the call may be ambiguous and fail to compile.
5. Once a declaration is selected, check the invocation's requirements, including checking for potential checked exceptions.
6. At runtime, evaluate the receiver object and arguments; if it is an instance method subject to overriding, the JVM locates the appropriate implementation body for the **selected signature**.

The `throws` clause is not used to "vote" on which overload is safer. For example, even if the caller has already written `catch (IOException)`, the compiler **will not for that reason** prefer `inspect(Object)` over `inspect(String)`.

**Note:** overload specificity is not always just "subclass beats superclass." Java also has generic methods, boxing/unboxing, varargs, and target typing. When a call is complex, you must apply the exact phases of JLS §15.12 rather than guessing from variable names or runtime types.

## 4. `throws` Does Not Participate in Distinguishing Overload Signatures

The following code **intentionally does not compile**:

```java
import java.io.IOException;
import java.sql.SQLException;

class InvalidOverloadByThrows {
    void work(String input) throws IOException { }

    void work(String input) throws SQLException { }
    // Error: same name and same parameter list.
}
```

The two declarations have the same signature; they differ only in their checked exception lists. Java does not consider them two valid overloads. Similarly, changing only the **return type** also does not create a different overload:

```java
class InvalidOverloadByReturnType {
    String convert(int value) { return "text"; }

    int convert(int value) { return value; }
    // Error: cannot distinguish by return type.
}
```

The fix is to choose different parameters (if they are genuinely two different operations) or give the methods different names that express their different semantics:

```java
void readFromFile(String path) throws IOException { }

void readFromDatabase(String query) throws SQLException { }
```

The three snippets in this section are meant to **illustrate declaration rules**; to compile the third snippet standalone, it must be placed inside a class with appropriate imports.

Remember: **for overloads, parameters distinguish methods; `throws` describes the error-handling obligation after the method has been selected**.

## 5. The Static Type of the Receiver Limits Which Overloads Are Visible

Not only the type of the **arguments**, but also the static type of the **receiver object** matters greatly.

Save as `ReceiverTypeDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class ReceiverTypeDemo {
    static class Parent {
        void send(Object value) throws IOException {
            System.out.println("Parent.send(Object)");
        }
    }

    static class Child extends Parent {
        @Override
        void send(Object value) throws IOException {
            System.out.println("Child.send(Object)");
        }

        void send(String value) throws SQLException {
            System.out.println("Child.send(String)");
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        try {
            parentView.send("abc");
        } catch (IOException ex) {
            System.out.println("parent-view error");
        }

        try {
            childView.send("abc");
        } catch (SQLException ex) {
            System.out.println("child-view error");
        }
    }
}
```

```bash
javac -encoding UTF-8 ReceiverTypeDemo.java
java ReceiverTypeDemo
```

Output:

```text
Child.send(Object)
Child.send(String)
```

Detailed explanation:

- `parentView` has the **declared type `Parent`**, even though the object is created with `new Child()`. The compiler searches `Parent`'s API and sees only `send(Object)`. Therefore `parentView.send("abc")` selects the signature `send(Object)` and must handle `IOException`.
- At runtime, the runtime object is `Child`, so the **overridden body `Child.send(Object)`** is executed. It prints `Child.send(Object)`; Java **does not switch to `Child.send(String)`**.
- `childView` has the declared type `Child`, so the compiler sees both `send(Object)` and `send(String)`. With the literal argument `"abc"`, it selects the more specific `send(String)` overload. At the call site, the checked exception obligation is `SQLException`.

This is a key example of the **two roles of static types**: the receiver type determines which overloads are visible, while the argument types determine which overload is selected. Runtime dispatch only affects the implementation of the already-selected method when it is overridden.

## 6. Overriding: Why Can a Parent Reference Require `catch` Even When the Subclass Throws No Checked Exception?

Consider a parent class that declares `throws IOException`, while the subclass implementation narrows the contract and throws no checked exception.

Save as `OverrideThrowsDemo.java`:

```java
import java.io.IOException;

public class OverrideThrowsDemo {
    static class Parent {
        void fetch() throws IOException {
            System.out.println("parent fetch");
        }
    }

    static class Child extends Parent {
        @Override
        void fetch() {
            System.out.println("child fetch");
        }
    }

    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = new Child();

        try {
            asParent.fetch();
        } catch (IOException ex) {
            System.out.println("caught I/O");
        }

        asChild.fetch();
    }
}
```

```bash
javac -encoding UTF-8 OverrideThrowsDemo.java
java OverrideThrowsDemo
```

Output:

```text
child fetch
child fetch
```

Both calls execute the `Child.fetch()` body, because the runtime object is `Child` and the `fetch()` method is overridden. However:

- `asParent.fetch()` is checked against the **declaration `Parent.fetch() throws IOException`**. Therefore, the caller must still handle or declare `IOException`, even if you know the object is `Child` this time.
- `asChild.fetch()` is checked against the **declaration `Child.fetch()`**, which has no checked exceptions, so `catch (IOException)` is not required.

**The checked exception obligation at the call site does not change depending on the runtime class of the object.** The static type contract allows substituting implementations while ensuring that caller code is properly verified.

Conversely, a subclass cannot override a method and declare a **broader** checked exception than the parent method. For example, if the parent declares `throws IOException`, the subclass cannot override the same signature with `throws Exception` or add an unrelated `SQLException`.

## 7. Overriding Boundary: Same Signature, No Broadening of Checked Exceptions

Code that **intentionally does not compile**:

```java
import java.io.IOException;
import java.sql.SQLException;

class ParentService {
    void execute() throws IOException { }
}

class InvalidChildService extends ParentService {
    @Override
    void execute() throws IOException, SQLException { }
    // SQLException is not declared by ParentService.execute().
}
```

When overriding a method with `throws IOException`, the implementation can:

- Keep `throws IOException`.
- Declare a narrower type, such as `throws FileNotFoundException`.
- Declare no checked exceptions at all.
- Still throw unchecked `RuntimeException`s, which are not restricted in the same way as checked exceptions.

However, it cannot add `SQLException` (which is not a subtype of `IOException`) or `Exception`, which is broader than the parent contract. This rule applies similarly when implementing interface methods.

**Unlike overloading:** two overloads with different parameter signatures can declare completely different checked exceptions. The restriction to narrow checked exceptions is a rule of **overriding**, not a general rule for all methods sharing a name.

## 8. How Is the Set of Checked Exceptions Required by the Compiler Determined?

When the compiler sees the call:

```java
service.load(argument);
```

it analyzes the parts in order:

1. Determine the static types of `service` and `argument`.
2. Select the overload declaration according to JLS §15.12.
3. Determine **the checked exceptions that this call can throw** from the selected invocation/declaration according to JLS §11.2.1.
4. Analyze enclosing `try-catch` blocks, the enclosing method's `throws` clause, exception supertype/subtype relationships, and unreachable checked `catch` rules.
5. If a checked exception can escape without being handled or properly declared, report a compile-time error.

Example with two overloads:

```java
void load(Object source) throws IOException { /* ... */ }

void load(String source) throws SQLException { /* ... */ }
```

When calling `load("abc")`, the `String` overload is selected. The fact that the caller has `catch (IOException)` **does not make Java select `load(Object)`**.

This snippet **intentionally does not compile** when placed in a class with the two overloads above:

```java
try {
    load("abc");  // Overload String: declares SQLException.
} catch (IOException ex) {
    System.out.println("caught I/O");
}
```

One issue is that the checked `SQLException` is neither caught nor declared. At the same time, for a `try` block that cannot throw the checked `IOException` according to Java's analysis, the `catch (IOException)` branch is invalid and will be rejected by the compiler with a "never thrown" diagnostic.

The correct approach is to catch or declare **`SQLException`** from the `String` overload:

```java
try {
    load("abc");
} catch (SQLException ex) {
    System.out.println("caught SQL");
}
```

This is a method-body pattern assuming the imports and the two overload signatures are already present; replacing `IOException` with `SQLException` **does not change the selected overload**, it simply satisfies the exception contract.

## 9. Not Every `catch` Is Needed and Not Every `catch` Is Valid

The compiler does not require catching every exception listed across all overloads with the same name. It examines the exceptions that can arise from **the call path being compiled**.

A few principles:

| Situation | Obligation |
| --- | --- |
| Selected overload `load(String) throws SQLException` | Catch or declare `SQLException`, if it can escape |
| Another overload `load(Object) throws IOException` is not selected | Does not create an `IOException` obligation from the `String` call |
| Selected method only declares `RuntimeException` | No corresponding checked exception obligation |
| A `catch` catches a supertype such as `Exception` | Can cover multiple checked exceptions, but the contract is broader and less specific |
| An overload declares `throws IOException` even if the current implementation does not throw it | The caller must still rely on the compile-time contract |
| A `try` block contains multiple calls to different overloads | The set of exceptions to handle can be the union of checked types from all those calls |

Example with two calls:

```java
try {
    load((Object) "file");
    load("database");
} catch (IOException ex) {
    handleIo(ex);
} catch (SQLException ex) {
    handleDatabase(ex);
}
```

This is an illustrative snippet, assuming the overloads and handler methods are already declared. The first call selects `load(Object)` and can throw `IOException`; if it completes normally, the second call selects `load(String)` and can throw `SQLException`. Both `catch` branches are valid because **both types can arise from the `try` body**.

**Do not test checked exceptions by running a single data branch.** The compiler analyzes the possible contract, not just the event observed during that run.

## 10. `null`: Selecting the Most Specific Overload or Encountering Ambiguity

The value `null` has no runtime class for the JVM to use like an ordinary object. In overload resolution, it can be compatible with multiple reference types, and the compiler selects the most specific version when possible.

### With an Inheritance Relationship: `String` Is More Specific Than `Object`

```java
static void show(Object x) throws IOException { /* ... */ }

static void show(String x) throws SQLException { /* ... */ }

show(null); // Selects show(String), because String is more specific than Object.
```

This is an illustrative snippet inside a class with appropriate imports, not a complete program. If called in a regular method, the caller must handle or declare `SQLException`. The fact that the `null` expression is not an existing `String` instance does not make Java choose `Object`.

### Without a Unique Most Specific Relationship: Ambiguous Call

```java
import java.io.IOException;
import java.sql.SQLException;

class AmbiguousNullExample {
    static void show(String value) throws IOException { }

    static void show(Integer value) throws SQLException { }

    static void demo() {
        show(null); // Compile error: ambiguous method call.
    }
}
```

This example **intentionally does not compile**. `String` and `Integer` have no subtype/supertype relationship with each other; both overloads apply to `null`, but there is no unique most specific choice.

Two ways to fix this:

```java
show((String) null);  // Selects the String overload.
show((Integer) null); // Selects the Integer overload.
```

These are illustrative lines inside the example class above, and the enclosing method must handle/declare `IOException` or `SQLException` respectively.

**You cannot fix an ambiguous call by adding `catch (SQLException)` or `throws IOException` outside.** The selected signature must be resolved first, and only then are checked exceptions verified.

## 11. Distinguishing Widening, Boxing, and Varargs in Overloading

Overload selection also depends on the **applicability phase**, not just proximity in the class hierarchy. For an `int` integer argument, an overload accepting `long` can be selected in the strict invocation phase before an overload accepting `Integer` that requires boxing.

Save as `WideningVsBoxingDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class WideningVsBoxingDemo {
    static void process(long value) throws IOException {
        System.out.println("selected=long");
    }

    static void process(Integer value) throws SQLException {
        System.out.println("selected=Integer");
    }

    public static void main(String[] args) {
        try {
            process(7); // int -> long (primitive widening)
        } catch (IOException ex) {
            System.out.println("I/O");
        }

        Integer boxed = 7;
        try {
            process(boxed); // Integer overload is an exact match
        } catch (SQLException ex) {
            System.out.println("SQL");
        }
    }
}
```

```bash
javac -encoding UTF-8 WideningVsBoxingDemo.java
java WideningVsBoxingDemo
```

Output:

```text
selected=long
selected=Integer
```

Mechanism:

- `process(7)`: the numeric literal has type `int`; primitive widening to `long` is valid in the strict phase, so Java does not need to move to the boxing phase to select `process(Integer)`. The corresponding checked obligation is `IOException`.
- `process(boxed)`: the expression has type `Integer`, so the `Integer` overload is an exact match and carries the `SQLException` obligation.

Varargs (`Type...`) are evaluated according to the JLS applicability rules, typically after the two phases that do not require variable arity. Do not see a method with `...` and assume it always beats a version taking a regular parameter.

**Do not use the `throws` list to predict widening or boxing.** Only after the overload is chosen do you inspect the exception contract.

## 12. `var` and Inferred Static Types Still Determine Overloads

Since Java 10, `var` lets the compiler infer a local variable's type from its initializer expression. This is **not dynamic typing**: the variable still has a fixed static type.

Example:

```java
var name = "alpha";   // compiler infers String
Object broad = name;  // declared type Object

inspect(name);        // uses the inspect(String) overload
inspect(broad);       // uses the inspect(Object) overload
```

This is a snippet inside a method, assuming the two overloads from Section 2 are declared and checked exceptions are handled appropriately.

To select a different overload, you change **the type of the expression** via its declaration or an explicit cast, rather than merely changing the variable's runtime value.

### Generic Methods Also Rely on the Bound at the Inner Call Site

A common point of confusion: a generic method receives `T` and calls a method name that has `Object` and `String` overloads. Inside the generic body, `T` with the default bound `Object` **does not automatically become `String`** just because a caller happens to pass a `String`.

Save as `GenericOverloadDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class GenericOverloadDemo {
    static void print(Object value) throws IOException {
        System.out.println("overload=Object");
    }

    static void print(String value) throws ParseException {
        System.out.println("overload=String");
    }

    static <T> void forward(T value) throws IOException {
        print(value);
    }

    public static void main(String[] args) {
        try {
            print("hello");
        } catch (ParseException ex) {
            System.out.println("parse failure");
        }

        try {
            forward("hello");
        } catch (IOException ex) {
            System.out.println("I/O failure");
        }
    }
}
```

```bash
javac -encoding UTF-8 GenericOverloadDemo.java
java GenericOverloadDemo
```

Output:

```text
overload=String
overload=Object
```

In `forward(T value)`, the compiler analyzes `print(value)` using the type `T` bounded by default by `Object`. It does not specialize bytecode into `print(String)` for each generic argument passed. Therefore `forward` declares `throws IOException`, not `throws ParseException`.

If the business requirement is to handle each data type separately, pass a processing strategy (callback/interface) or use overloading at a layer that has the specific type information, rather than expecting a generic call to pick an overload by runtime class.

## 13. Constructor Overloading Follows Similar Rules

Constructors can be overloaded by parameter list; the compiler selects the constructor at **compile-time** based on the types of the passed expressions. Each constructor can declare different checked exceptions.

Save as `ConstructorOverloadDemo.java`:

```java
import java.io.IOException;
import java.text.ParseException;

public class ConstructorOverloadDemo {
    static class Parser {
        Parser(Object source) throws IOException {
            System.out.println("constructor=Object");
        }

        Parser(String source) throws ParseException {
            System.out.println("constructor=String");
        }
    }

    public static void main(String[] args) {
        Object broad = "input";
        String narrow = "input";

        try {
            new Parser(broad);
        } catch (IOException ex) {
            System.out.println("I/O");
        }

        try {
            new Parser(narrow);
        } catch (ParseException ex) {
            System.out.println("parse");
        }
    }
}
```

```bash
javac -encoding UTF-8 ConstructorOverloadDemo.java
java ConstructorOverloadDemo
```

Output:

```text
constructor=Object
constructor=String
```

Constructors are not overridden like instance methods, but the principle of **selecting the version with matching parameters before checking checked exceptions** is similar. If multiple constructor overloads are ambiguous (for example, accepting `String` and `Integer` with a `null` argument), the compiler must also resolve the ambiguity rather than relying on the `throws` list to choose.

## 14. Interfaces and Polymorphism: Selecting the Contract From the Declared Type

An interface is typically where a service's contract is described:

```java
import java.io.IOException;

interface ResourceService {
    void load(String key) throws IOException;
}
```

An implementation can narrow the checked exception:

```java
class CachedResourceService implements ResourceService {
    @Override
    public void load(String key) {
        System.out.println("cache=" + key);
    }
}
```

These are illustrative declarations in the same package with appropriate imports. At the call layer:

```java
ResourceService service = new CachedResourceService();

try {
    service.load("user-42");
} catch (IOException ex) {
    System.out.println("I/O failure");
}
```

The caller must adhere to the `ResourceService.load(String) throws IOException` contract according to the declared type of the `service` variable, even though the current implementation throws no checked exception. If the variable is declared directly with type `CachedResourceService`, the compiler can rely on the narrower overridden signature.

This allows the system to swap implementations: another implementation can perform real I/O and throw `IOException`, while caller code written against the interface already has valid handling in place.

**Be careful with interface APIs that have multiple overloads:** which overloads the caller sees also depends on the interface, not all methods existing on the runtime implementation.

## 15. Where to Catch Errors in a Call Chain With Overloads?

A service layer may call overloads depending on the meaning of the data. Each call branch can bring its own checked exceptions:

```java
static void route(boolean fromFile) throws IOException, SQLException {
    if (fromFile) {
        load((Object) "file");
    } else {
        load("database");
    }
}
```

This is an illustrative method, assuming the overloads `load(Object) throws IOException` and `load(String) throws SQLException` are already declared in the appropriate class. Because both branches can execute, `route` declares both `IOException` and `SQLException` if it does not catch them internally.

In the caller, you can write:

```java
try {
    route(sourceIsFile);
} catch (IOException ex) {
    handleIo(ex);
} catch (SQLException ex) {
    handleSql(ex);
}
```

The names `sourceIsFile`, `handleIo`, and `handleSql` above are **contextual placeholders in an illustrative snippet**, not a standalone runnable Java class. The goal is to recognize that **the set of checked exceptions for the entire method** can be the union of multiple control paths; the caller does not catch only one exception based on a single run's data.

If both errors share the same recovery strategy, you can use `catch (IOException | SQLException ex)` following multi-catch rules, provided the shared action makes business sense. If separate handling is needed, keep the two corresponding `catch` blocks.

Avoid declaring `throws Exception` just to avoid tracking which exception types each overload can throw. It is valid in many cases, but it makes the contract unclear and makes it harder for callers to decide on a handling policy.

## 16. Common Pitfalls That Cause Compile Errors

| Situation | Why is it wrong? | How to fix |
| --- | --- | --- |
| Writing two methods differing only by `throws` | `throws` is not a factor that distinguishes overloads | Change parameter signatures or split into separate method names |
| Assuming a runtime `String` in an `Object` variable selects `load(String)` | Overloads are selected by the static type of the expression | Use the right type, a checked cast, or change the API |
| Using `Parent ref = new Child(); ref.childOnlyOverload(...)` | Methods only on `Child` are not visible through `Parent` | Use an appropriate contract or an intentional `Child` reference |
| `catch (IOException)` when the selected overload only declares checked `SQLException` | The compiler does not change overloads based on `catch` | Catch or declare `SQLException` |
| `Child.override() throws Exception` when `Parent` only has `throws IOException` | Overriding broadens the checked exception | Narrow or remove the new checked type |
| `show(null)` when both `show(String)` and `show(Integer)` exist | There is no unique most specific overload | Cast intentionally or change the signature |
| Assuming `var` is a dynamic runtime type | `var` infers a static type | Check the inferred type |
| Assuming a generic `T` will pick an overload by runtime data | The compiler processes `T` by its type bound | Use overloading at a layer with concrete types or use a strategy |
| Choosing an overload based on the `catch` type the caller wrote | `throws`/`catch` do not participate in overload resolution | Select the method first, check exceptions second |
| Catching all `Exception`s to hide overload design flaws | Can catch too broadly and mask bugs | Catch the specific checked exceptions per the contract |
| Using `instanceof` assuming the compiler will pick a different overload | Runtime `instanceof` does not rewrite an already-compiled call | Branch explicitly and call the appropriate overload if needed |
| Expecting an override to change the required checked exceptions on a `Parent`-typed caller | The caller is checked against the `Parent` static type | Use a stable public API or narrow the reference type when appropriate |

## 17. Checklist for Analyzing a Call Reporting a Checked Exception Error

When encountering `unreported exception ... must be caught or declared to be thrown`:

1. **Write down the exact method name** being called and the overloads visible from the declared type of the receiver.
2. **Note the static type of each argument** — including literals, variables of type `Object`, `String`, cast expressions, `var`, or generic type variables.
3. **Determine the selected overload** by applicability and specificity; if ambiguous, resolve the ambiguity first.
4. **Read only the `throws` of that overload**, not all `throws` across every method with the same name.
5. **If overriding is involved**, separate the signature's contract under the static type from the execution body under the runtime object.
6. **Consider other calls** in the same `try` block or method that may contribute other checked exception types.
7. **Check exception class relationships**: `IOException` can cover `FileNotFoundException`; independent types like `IOException` and `SQLException` need separate handling or a suitable supertype.
8. **Choose the handling layer**: if recovery is possible here, `catch`; otherwise, declare `throws` or translate into a domain exception with a clear cause.
9. **Check interface/override contracts**: do not declare a new checked exception that exceeds what the parent class allows.
10. **Write separate compile-time and runtime tests**: running a test only shows the overload/implementation and failures for the test data; it does not replace how the compiler determines checked obligations.

## 18. Self-Check Questions

**1.** `void read(Object) throws IOException` and `void read(String) throws SQLException`. For `Object x = "abc"; read(x);`, what must be handled?  
**`IOException`**, because the static type of `x` is `Object`, so the `Object` overload is selected.

**2.** With the two overloads above, what must `read("abc")` handle?  
**`SQLException`**, because `String` is a more specific applicable type.

**3.** Does wrapping `read("abc")` in `catch (IOException)` make the compiler choose the `Object` overload?  
**No.** The overload is selected first; the selected `SQLException` contract must be handled.

**4.** `Parent p = new Child();`, where `Parent` only declares `execute(Object) throws IOException`, and `Child` overrides it and overloads `execute(String) throws SQLException`. What does `p.execute("abc")` select?  
**It selects the `execute(Object)` signature** from `Parent`, and can run the overridden `Child.execute(Object)` body. The caller must handle `IOException`.

**5.** What about `Child c = new Child(); c.execute("abc")`?  
**It selects the `execute(String)` overload** because it is visible and the most specific applicable one; the caller must handle `SQLException`.

**6.** Can you write two overloads that differ only by `throws IOException` and `throws SQLException`?  
**No**, if their parameter lists are identical.

**7.** Given `show(String)` and `show(Integer)`, does calling `show(null)` automatically pick the type with the smaller `throws`?  
**No.** The call is ambiguous; `throws` does not resolve ambiguity.

**8.** `Parent.fetch() throws IOException`, and `Child` overrides `fetch()` without declaring checked exceptions. Does a caller with a `Parent` variable pointing to `Child` still have to handle `IOException`?  
**Yes.** The compiler checks against `Parent.fetch()`.

**9.** If a generic method accepts an unbounded `T` and calls `process(T)`, will it automatically choose the `process(String)` overload when passed a `String` at runtime?  
**No.** The body is compiled against `T`'s type bound (by default `Object`).

**10.** If a method has two call paths to two overloads declaring `throws IOException` and `throws SQLException` respectively, what should the enclosing method declare if it does not catch them?  
Typically **`throws IOException, SQLException`** or an appropriate supertype. If the handling policies differ, use `catch` at the appropriate layer.

## Official References

- [Java Language Specification, Java SE 21 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): compile-time overload selection and runtime invocation.
- [JLS 21 — §15.12.2 Choosing Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2): applicability phases and most specific method.
- [JLS 21 — §11.2.1 Exception Analysis of Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.1): the set of exceptions a method invocation expression can throw.
- [JLS 21 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3): obligation to catch or declare checked exceptions.
- [JLS 21 — §8.4.9 Overloading](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.9): overloading and the role of compile-time argument types.
- [JLS 21 — §8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding.
- [JLS 21 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9): constructor overload selection.

**Key takeaway:** Java **selects overloads using the static types** of the receiver/arguments and method signatures at compile time; **checks checked exceptions against the selected overload**; and only then can runtime dispatch select an overridden body. `throws` does not help select an overload, and runtime types never silently redirect a call to a different overload.
