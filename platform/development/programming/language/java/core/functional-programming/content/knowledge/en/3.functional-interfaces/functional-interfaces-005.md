# Interface Inheritance and Merged Signatures in Java

## 1. Why Can Inheriting Multiple `abstract` Methods Still Produce a Functional Interface?

Usually, a **functional interface** is introduced as an interface with exactly one abstract method (*single abstract method*, SAM). That phrasing is helpful to start with, but the word **one** must be understood in terms of the **method contract after considering inheritance**, not simply by counting `abstract` declaration lines in parent interfaces.

An interface can `extends` multiple interfaces. If the inherited abstract methods have **override-equivalent signatures** and compatible return types, Java treats them as **one logical functional contract**. The subinterface can still be a functional interface and serve as a target type for a matching lambda or method reference.

Illustrative example:

~~~java
interface First {
    void execute();
}

interface Second {
    void execute();
}

@FunctionalInterface
interface Combined extends First, Second {
}
~~~

`Combined` inherits two `execute()` declarations, yet a single `execute()` method suffices to fulfill both contracts. Therefore, `Combined` is validly a functional interface:

~~~java
Combined task = () -> System.out.println("Executed");
task.execute();
~~~

The two snippets above are **illustrative code** placed in the same compilation unit. A complete runnable program is in section 6.

**There is no mechanism that “merges execution bodies” from two abstract methods:** they have no bodies to merge. Java checks whether all contracts can be satisfied by a single method. The lambda supplies the implementation for that functional contract.

## 2. How Java Determines the Functional Contract After Inheritance

According to the Java Language Specification (JLS) §9.8, consider the set `M` of `abstract` methods that are members of the interface, **excluding methods whose signatures match `public` instance methods of `Object`**. A normal, non-`sealed` interface is a functional interface if there exists a method `m` in `M` that satisfies **both**:

1. The signature of `m` is a **subsignature** of the signature of **every** method in `M`.
2. The return type of `m` is **return-type-substitutable** for the return type of **every** method in `M`.

If `M` has no methods left after exclusion, the interface is **not** a functional interface. If there are multiple methods that cannot be merged under the conditions above, the interface is also not a functional interface; in some cases, the interface declaration itself is not even valid to compile.

The Java specification distinguishes three important terms:

- **Method signature:** includes the method name, the method's type parameters (if any), and the formal parameter types after accounting for correspondence rules. **The return type and `throws` clause are not part of distinguishing overloads by signature**.
- **Override-equivalent:** two signatures are override-equivalent when at least one signature is a *subsignature* of the other. From Java's perspective, they can represent the same overriding contract.
- **Subsignature:** includes identical signatures as well as compatible cases accounting for **erasure** to support compatibility between generic code and legacy code using raw types. **Sharing only the same name or the same erasure is not enough** to conclude that two methods merge validly.

The return-type condition explains why `String` can satisfy a contract returning `CharSequence` (a subtype can substitute for a supertype), whereas `int` and `long` cannot arbitrarily merge even when their names and parameters match.

JLS §9.9 also describes the **function type** (also called *function descriptor*) used to check lambda compatibility: it determines the parameters, return type, and allowed checked exceptions after considering the entire inherited contract.

> **Takeaway:** Asking “how many `abstract` lines?” is not enough. You must ask “is there one signature compatible with all remaining signatures, and is its return type substitutable?”.

## 3. Cases That Merge Successfully

### 3.1. Inheriting Two Declarations with Identical Signatures

~~~java
interface LeftAction {
    void run();
}

interface RightAction {
    void run();
}

@FunctionalInterface
interface OneAction extends LeftAction, RightAction {
}
~~~

Both parents declare `void run()`. The child does not need to declare `run()` a third time. `OneAction` has one functional contract `() -> void`; a lambda `() -> ...` can implement it.

This is the easiest case to observe: **same name, same parameter list, same return type**.

### 3.2. Covariant Return Types

~~~java
interface GeneralText {
    CharSequence read();
}

interface SpecificText {
    String read();
}

@FunctionalInterface
interface TextReader extends GeneralText, SpecificText {
}
~~~

`String` implements `CharSequence`, so `String read()` can substitute for the contract returning `CharSequence`. A lambda returning `String` satisfies both:

~~~java
TextReader reader = () -> "Java";
String value = reader.read();
~~~

The usage snippet above assumes the interfaces have already been declared. Java can select the compatible concrete return type for the call; there is no need to force the lambda into two separate methods.

**Distinction:** return-type covariance applies to **reference types** with an appropriate substitutability relationship. You cannot rely on ordinary integer conversions to make `int read()` and `long read()` into a single compatible contract.

### 3.3. Inheriting a Generic Method and Fixing the Type Argument

~~~java
interface Source<T> {
    T get();
}

interface StringSource extends Source<String> {
}

@FunctionalInterface
interface ConfigSource extends StringSource {
}
~~~

When `T` is replaced by `String`, the abstract contract that `ConfigSource` receives is `String get()`. It remains a SAM:

~~~java
ConfigSource config = () -> "production";
System.out.println(config.get()); // production
~~~

This point is especially useful when building generic APIs: a subinterface can specialize the data type without introducing an additional independent abstract contract.

Multiple inheritance branches can converge on one compatible contract; Java checks the types after applying generic type arguments under inheritance rules. However, **if different branches fix different types and cause a signature conflict**, do not assume the compiler can pick one branch automatically.

### 3.4. Public Methods of Object Do Not Increase the SAM Count

~~~java
@FunctionalInterface
interface NamedCheck {
    boolean test(String name);
    boolean equals(Object other);
}
~~~

`equals(Object)` has the same signature as a `public` instance method of `Object`, so it is not counted as a new functional method. `NamedCheck` still has one true SAM, `test(String)`.

Similarly, signatures matching `Object`'s `hashCode()` or `toString()` are not counted under this rule.

**Important limitation:** `Object`'s `clone()` is `protected`, not a `public` method excluded by the SAM rule. If an interface declares `public Object clone();` alongside another abstract method, those are two distinct abstract obligations. Do not extend the exception to *every* method whose name resembles a method in `Object`.

### 3.5. `default`, `static`, and `private` Are Not Second Abstract Methods

~~~java
@FunctionalInterface
interface Validator {
    boolean isValid(String text);

    default boolean isInvalid(String text) {
        return !isValid(text);
    }

    static Validator notBlank() {
        return text -> text != null && !text.isBlank();
    }

    private static String label() {
        return "validation";
    }
}
~~~

`isValid` is the abstract contract. `isInvalid` is a `default` method with a body; `notBlank` is a `static` method; `label` is a private helper method (Java 9+). They do not add abstract obligations, so `Validator` remains a functional interface.

Interface `static` methods are not inherited as instance methods; a lambda does not “implement” them either. When inheriting multiple `default` methods with conflicting signatures, you must handle them according to `default` conflict resolution rules, rather than treating them as merged abstract methods.

## 4. Cases That Cannot Be Merged

### 4.1. Two Independent Abstract Methods

~~~java
interface Startable {
    void start();
}
interface Stoppable {
    void stop();
}

// Valid interface, but NOT a functional interface:
interface Lifecycle extends Startable, Stoppable {}
~~~

`start()` and `stop()` are two different contracts. Implementing classes must implement both; a lambda cannot represent `Lifecycle`.

The following snippet **intentionally does not compile**, solely to illustrate the error:

~~~java
// @FunctionalInterface
// interface BadLifecycle extends Startable, Stoppable {}
// -> the annotation will report that the interface does not have exactly one SAM contract.

// Lifecycle obj = () -> System.out.println("start");
// -> the lambda has no single compatible function descriptor.
~~~

### 4.2. Overloads Do Not Become One Signature

~~~java
interface CountByNumber {
    int count(int number);
}
interface CountByText {
    int count(String text);
}
interface BothCounts extends CountByNumber, CountByText {}
~~~

`count(int)` and `count(String)` share the same name but have different parameter lists. This is **overloading**: `BothCounts` has two abstract methods, remains a valid interface, yet is **not** a functional interface.

### 4.3. Same Parameters but Incompatible Return Types

Example that **does not compile** if uncommented:

~~~java
// interface A {
//     int value();
// }
// interface B {
//     long value();
// }
// interface Invalid extends A, B {}
~~~

The signature `value()` is identical, but `int` is not return-type-substitutable for `long` or vice versa. Therefore, the `Invalid` declaration is invalid. This is an **interface inheritance** error, not merely a valid interface that cannot be used with lambdas.

Similarly, two contracts returning reference types without an appropriate substitutability relationship can conflict. You must check the return-type-substitutable rules rather than inferring solely from type names.

### 4.4. Same Erasure When Signatures Are Not Subsignatures of Each Other

Java generics use **type erasure**. Two different declarations can become the same JVM form after erasing type parameters, but that does not mean they can automatically merge into one SAM.

The following example **intentionally does not compile**:

~~~java
// interface ForStrings {
//     void accept(java.util.List<String> values);
// }
// interface ForIntegers {
//     void accept(java.util.List<Integer> values);
// }
// interface Invalid extends ForStrings, ForIntegers {}
~~~

The two declarations `accept(List<String>)` and `accept(List<Integer>)` have the same erasure `accept(List)` but have no valid subsignature relationship between them. They create a name/erasure clash, so `Invalid` is not a valid interface.

**Do not confuse:** a case with a raw `Iterable` declaration and an `Iterable<String>` declaration can be valid under subsignature rules in appropriate structures. However, two incompatible parameterizations, such as `List<String>` vs. `List<Integer>`, are not treated as the same contract.

## 5. `throws` Rules When Merging

Differences in `throws` clauses **do not by themselves create a new overloaded signature** and do not necessarily prevent two abstract methods from being inherited together. However, the checked exceptions permitted by the *function descriptor* depend on **the set of `throws` clauses of all constituent methods**.

Illustrative example:

~~~java
import java.io.IOException;
import java.sql.SQLException;

interface FileJob {
    void execute() throws IOException;
}
interface DatabaseJob {
    void execute() throws SQLException;
}
@FunctionalInterface
interface UnifiedJob extends FileJob, DatabaseJob {}
~~~

`UnifiedJob` still has one `execute()` contract. However, a lambda implementing `UnifiedJob` cannot arbitrarily throw checked `IOException` or `SQLException`: they are not within the common checked-exception allowance permitted by both branches. A lambda that throws no checked exceptions is compatible:

~~~java
UnifiedJob job = () -> System.out.println("OK");
~~~

**Error example when uncommented (does not compile):**

~~~java
// UnifiedJob bad = () -> {
//     throw new IOException("failed");
// };
~~~

In another scenario, when both contracts permit a common checked exception or an appropriate subtype, the function descriptor may allow that checked exception. Combining them must also obey `throws` declaration rules for overriding. Unchecked exceptions (`RuntimeException` and its subclasses) are not constrained by checked `throws` clauses in this way.

## 6. Complete Verified Java 17 Program

Create the file **InterfaceInheritanceDemo.java**. All interfaces are declared nested inside the class so that it is a single standalone file requiring no extra sources. The program verifies three cases: covariant return type, two identical abstract signatures with `Object`'s `equals` method, and generic specialization.

~~~java
public class InterfaceInheritanceDemo {
    interface TextA { CharSequence get(); }
    interface TextB { String get(); }

    @FunctionalInterface
    interface MergedText extends TextA, TextB {
        default String boxed() { return "[" + get() + "]"; }
        static String description() { return "merged"; }
    }

    interface ActionA { void run(); }
    interface ActionB { void run(); }

    @FunctionalInterface
    interface MergedAction extends ActionA, ActionB {
        boolean equals(Object obj);
    }

    interface Data<T> { T data(); }
    interface FixedData extends Data<String> {}

    @FunctionalInterface
    interface DataView extends FixedData {
        default int length() { return data().length(); }
    }

    public static void main(String[] args) {
        MergedText text = () -> "Java";
        MergedAction action = () -> System.out.println("run once");
        DataView data = () -> "SAM";

        System.out.println(text.boxed());
        System.out.println(MergedText.description());
        action.run();
        System.out.println(data.data() + ": " + data.length());
    }
}
~~~

Compile with Java 17 or a newer JDK supporting `--release 17`:

~~~bash
javac --release 17 InterfaceInheritanceDemo.java
java InterfaceInheritanceDemo
~~~

**Stdout:**

~~~text
[Java]
merged
run once
SAM: 3
~~~

Line-by-line explanation:

1. `MergedText` inherits `CharSequence get()` and `String get()`; `String` can substitute for `CharSequence`. `text.boxed()` calls `get()` via a `default` method, returning `[Java]`.
2. `MergedText.description()` is a `static` method on the interface itself, returning `merged`. It is not the lambda's responsibility.
3. `MergedAction` inherits two `void run()` declarations, treated as one contract. `equals(Object)` has the signature of a public method in `Object`, not increasing the SAM count. Calling `action.run()` executes the lambda body once.
4. `DataView` receives `String data()` via `Data<String>`; `length()` is `default`, not increasing the abstract method count. `"SAM".length()` returns 3.

The example was tested with the compiler using `--release 17` and executed; the output matches what is shown above.

## 7. Some Advanced Cases with Generics and Method Signatures

### 7.1. Method Type Parameters with Different Names Can Still Be Equivalent

Two generic methods can use different type-variable names and still have override-equivalent signatures in declaration terms. Illustrative example:

~~~java
interface FirstGeneric {
    <T> T copy(T source);
}
interface SecondGeneric {
    <U> U copy(U source);
}
@FunctionalInterface
interface GenericCopy extends FirstGeneric, SecondGeneric {}
~~~

`T` and `U` here are just different names for corresponding type parameters; the rule for comparing generic signatures evaluates structure after alpha-renaming type variables, rather than mechanically comparing letters.

**Note:** a generic SAM like `<T> T copy(T)` has a function descriptor with its own type parameter. It is a functional interface by definition, but a normal lambda cannot express such a generic function descriptor. When an implementation is needed, you can use a class or anonymous class implementing the generic method:

~~~java
GenericCopy copier = new GenericCopy() {
    @Override
    public <T> T copy(T source) {
        return source;
    }
};
~~~

This is an illustrative snippet assuming the three interfaces above already exist. Do not infer that every interface annotated with `@FunctionalInterface` can be implemented directly by any lambda.

### 7.2. Valid Raw-Type Cases Do Not Apply to Every Erasure Collision

An advanced example following the JLS:

~~~java
interface ParameterizedView {
    Iterable view(Iterable<String> values);
}
interface RawView {
    Iterable<String> view(Iterable values);
}
@FunctionalInterface
interface UnifiedView extends ParameterizedView, RawView {}
~~~

`RawView.view(Iterable)` has a subsignature compatible with `ParameterizedView.view(Iterable<String>)`; the return type `Iterable<String>` is compatible with `Iterable` under the return-type-substitutable rule. This example uses raw types intentionally to explain compatibility rules with legacy code; in new applications, prefer consistent generic design and avoid raw types because they can lose type checking.

**Important distinction:** raw-vs-parameterized can be valid when both subsignature and return-type-substitutable conditions are met; whereas two parameterizations `List<String>` and `List<Integer>` only look the same after erasure without meeting those conditions, causing a conflict.

## 8. Relationship to `default` Method Inheritance and Conflict Resolution

`abstract` methods can form a single contract without implementation bodies. For `default` methods, the issue is different: they carry **actual method bodies**.

Example that **does not compile** due to inheriting two `default` methods with the same signature:

~~~java
// interface Friendly {
//     default String greet() { return "Hi"; }
// }
// interface Formal {
//     default String greet() { return "Hello"; }
// }
// interface Conflicted extends Friendly, Formal {}
~~~

The subinterface must resolve the conflict explicitly, for example by overriding `greet()` and choosing the desired behavior. Do not apply the “two identical signatures merge automatically” reasoning of abstract methods to two default bodies.

Conversely, when a subinterface adds new `default` methods with their own bodies that do not conflict, they do not break the SAM property. This is how APIs commonly provide a single abstract extension point accompanied by convenience operations:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String text);

    default String formatNonNull(String text) {
        return format(text == null ? "" : text);
    }
}
~~~

The `format(...)` behavior is supplied by the lambda; `formatNonNull(...)` is reusable behavior inside the interface.

## 9. Self-Check Process When Designing an Inheriting Functional Interface

| Question to ask | If the answer is... | Consequence |
| --- | --- | --- |
| How many actual abstract methods does the subinterface inherit? | Only one after excluding public Object signatures | Likely a SAM |
| Are there multiple abstract declarations? | Identical signatures or a valid subsignature | Can merge |
| Are the return types compatible? | A common return-type-substitutable type exists | Inheritance may be valid |
| Are there overloads with different parameter lists? | Multiple independent contracts | Not a SAM |
| Do they share erasure with incompatible parameterizations? | Name clash exists | Interface declaration may fail to compile |
| Are there conflicting default methods? | Yes | Must resolve implementation body conflict |
| Are there multiple checked `throws`? | Yes | Check the function descriptor and allowed checked exceptions |
| Is `@FunctionalInterface` present? | Yes | Compiler verifies the interface is truly a SAM; the annotation does not make an invalid contract valid |

When designing, run `javac` with `@FunctionalInterface` on the intended interface to get early error feedback if adding an abstract method breaks the contract. Removing the annotation **does not make** a non-SAM interface usable with lambdas; the annotation is merely a way to confirm intent at compile time.

Do not rely on *counting parent interfaces*. A subinterface can extend multiple interfaces and still have exactly one functional contract, or extend one parent interface and have multiple unmergeable abstract methods.

## 10. Self-Check Exercises

**Exercise 1.** Given:

~~~java
interface A { Number get(); }
interface B { Integer get(); }
@FunctionalInterface interface C extends A, B {}
~~~

Is `C` a SAM? **Yes.** `Integer` is a subtype of `Number`, so an `Integer` result satisfies both contracts.

**Exercise 2.** Given:

~~~java
interface A { void run(String text); }
interface B { void run(int count); }
interface C extends A, B {}
~~~

Is `C` valid and is it a SAM? **Yes, it is a valid interface; no, it is not a SAM.** The two different signatures are overloads, requiring two implementations.

**Exercise 3.** Given:

~~~java
interface A { void run(); }
interface B { void run(); }
@FunctionalInterface interface C extends A, B {
    default String name() { return "C"; }
}
~~~

Can `C` accept `C action = () -> {};`? **Yes.** The two `run()` declarations share the same contract; `name()` is a default method.

**Exercise 4.** If two interfaces declare `List<String> save(List<String>)` and `List<Integer> save(List<Integer>)`, can we say they are equivalent just because their erasure is the same `save(List)`? **No.** Having the same erasure is not enough for a subsignature, and it can cause a name clash.

**Exercise 5.** Why is `@FunctionalInterface` useful in API design? **Because** the compiler verifies that the interface still satisfies the functional contract when methods are added or the inheritance hierarchy changes. It is a verification measure, not an automatic method-merging mechanism.

## References

- [Java Language Specification 17, §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8).
- [JLS 17, §9.4.1.3 — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3).
- [JLS 17, §9.9 — Function Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.9).
- [JLS 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).

**Conclusion:** **Inheriting multiple abstract declarations does not imply having multiple functional contracts.** Java evaluates signatures after inheritance, subsignatures, return-type substitutability, and the exception for public `Object` methods. When all abstract obligations reduce to one valid contract, the subinterface can still be a functional interface; when there are independent overloads, return-type conflicts, or erasure name clashes, fix the design rather than expecting lambdas to resolve it.