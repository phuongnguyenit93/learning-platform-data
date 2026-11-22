# Checking Overriding, Return Types, and Declared Exceptions in Java

When a subclass declares a method related to a method already present in a superclass or interface, the Java compiler must determine **whether it is truly an override**, and then check **the method signature, access rights, return type, and checked exceptions in `throws`**. These semantic checks ensure that a subclass object can be used through a supertype while still respecting the published method contract.

Three core questions:

1. **Is there an override relationship?** Does the subclass method have an appropriate signature and actually override an overridable instance method?
2. **Is the return value substitutable?** The return type of the new method must be *return-type-substitutable* for the overridden return type, typically **the same type or a subtype**.
3. **Are the declared exceptions valid?** An overriding method **must not widen the set of checked exceptions** compared to the parent method contract; it may narrow or remove them.

This article focuses on `javac` compile-time checks, using Java 17 and runnable or intentionally erroneous scenarios to identify the rules.

## 1. What is overriding and how does the compiler recognize it?

**Overriding** is when an instance method of a subclass or subinterface provides an alternative declaration/implementation for a corresponding instance method already present in a supertype. When called through a supertype reference, the method selected to **execute at runtime** may be the overriding version of the actual object's class (dynamic dispatch). However, **determining whether the call is valid, the result type, and the checked exceptions to handle** are checked by `javac` before runtime, based on compile-time types.

Java 17 example:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Example {
    public static void main(String[] args) {
        Animal animal = new Dog();
        System.out.println(animal.sound());
    }
}
```

Save the three classes above to `Example.java`, then run:

```sh
javac --release 17 Example.java
java Example
```

**Exact stdout:**

```text
woof
```

`javac` recognizes that `Dog.sound()` overrides `Animal.sound()`: the name and parameter list match, both are instance methods, and the return type `String` is valid. The JVM invokes `Dog`'s version because the actual object is a `Dog`.

### Signatures do not include the return type or `throws`

In Java, a **method signature** is determined by the method name, type parameters (under equivalence rules), and the parameter type list; it **does not include** the return type, `throws`, or parameter variable names.

This has two consequences:

- `print(String)` and `print(Object)` are two overloads because their parameters differ; they do not automatically override each other.
- Two methods in the same class cannot be declared differing only in return type or `throws`. If they already have the same signature, override, name clash, or duplicate declaration rules may apply; you cannot use return type to "distinguish" two overloads.

For generic methods and inheritance, the standard uses the concept of **subsignature/override-equivalent** rather than merely comparing the text of names/parameter types. There are cases compatible with legacy raw types that are permitted, sometimes emitting an unchecked warning. Therefore, the rule of thumb "same name and same parameters" is an initial way to recognize it, while JLS `8.4.2` and `8.4.8` are the complete rules.

### What does `@Override` check?

`@Override` asks the compiler to verify that the method actually overrides or implements a method allowed by Java's rules. If a name or parameter is misspelled, `javac` reports an error instead of silently creating a different method:

```java
class Parent {
    void save(String value) {
    }
}

class Child extends Parent {
    @Override
    void save(Object value) {
    }
}
```

This snippet **intentionally does not compile**: `save(Object)` is an overload with a different signature, not an override of `save(String)`. If `@Override` is omitted, the compiler may allow both methods to exist, yet polymorphic behavior will not work as the author expected. Keep `@Override` on overriding methods: it is a cheap and useful semantic check.

`@Override` **does not** replace constraints on return type, `throws`, or visibility. A method with a properly placed annotation can still be rejected for violating those rules.

## 2. Conditions for a method to override

| Condition | Practical rule | If violated |
| --- | --- | --- |
| Type relationship | The method resides in a subtype with a valid inheritance/implementation relationship | Declaring the same name in two unrelated classes is not an override |
| Signature | Has a subsignature/override-equivalence relationship per the JLS | May become an overload or cause a name clash error |
| Instance nature | An instance method overrides an instance method | `static` and instance methods cannot be swapped when override-equivalent |
| Not `final` | `final` methods forbid overriding | Compile-time error |
| Not `private` in the inheritance sense | A `private` method in the superclass is not overridden | A same-named method in the subclass may be a new method, not an override |
| Sufficiently wide access | Must not lower the visibility of the overridden method | Compile-time error such as "attempting to assign weaker access privileges" |
| Return type | Must be return-type-substitutable | Compile-time error or unchecked warning in some legacy generic cases |
| Checked exceptions | `throws` must not be widened against the parent contract | Compile-time error |
| Abstract/interface | A concrete class must provide implementations for unsatisfied abstract methods | The class must be `abstract` or have a suitable implementing method |

### Access rights must not be narrowed

When overriding:

- `public` in parent → must be `public` in child.
- `protected` in parent → `protected` or `public` in child.
- Package-private in parent → for a valid override in the same package, must not be reduced to `private`; can stay package-private or be widened.
- `private` methods are not inherited in a way that an instance method can override.

An **intentionally erroneous** snippet:

```java
class Base {
    protected void run() {
    }
}

class Sub extends Base {
    @Override
    private void run() {
    }
}
```

`javac` does not allow an overriding method to reduce access from `protected` to `private`. Across different packages, accessibility/inheritability must also be checked; do not assume every parent method without an explicit modifier can be overridden from another package.

### `static`, `private`, `final`, and constructors are not like instance overrides

- **`static` method:** can be *hidden* by a static method in a subclass; method selection is based on the reference type at compile time, unlike dynamic dispatch of instance methods.
- **`private` method:** a subclass does not override a parent's private method. If the subclass declares the same name/signature, it is a separate method when valid.
- **`final` instance method:** a subclass cannot override it; a `final` class cannot even be extended.
- **Constructor:** is not inherited and does not override. `throws` rules for subclass constructors belong to constructor chaining/exception checking, not instance method override restrictions.

Example contrasting hiding and overriding (file `Dispatch.java`):

```java
class Parent {
    static String kind() {
        return "parent-static";
    }

    String name() {
        return "parent-instance";
    }
}

class Child extends Parent {
    static String kind() {
        return "child-static";
    }

    @Override
    String name() {
        return "child-instance";
    }
}

public class Dispatch {
    public static void main(String[] args) {
        Parent object = new Child();
        System.out.println(object.kind());
        System.out.println(object.name());
    }
}
```

Compile/run:

```sh
javac --release 17 Dispatch.java
java Dispatch
```

**Stdout:**

```text
parent-static
child-instance
```

Calling a static method through an object variable is accepted syntax, but it can be confusing and emit a lint warning when relevant checks are enabled. In production code, write `Parent.kind()` or `Child.kind()` explicitly; the example uses `object.kind()` solely to illustrate the difference in call selection.

## 3. Return types: the covariant return rule

If the parent method returns a **reference type**, the overriding method is usually allowed to return **the same type or a subtype**. This rule is called **covariant return**, supported by Java so a subtype can provide a more specific value while still satisfying the parent return type.

Example:

```java
class Producer {
    Number result() {
        return 1;
    }
}

class IntegerProducer extends Producer {
    @Override
    Integer result() {
        return 42;
    }
}
```

Valid because `Integer` is a subtype of `Number`. When using `Producer p = new IntegerProducer();`, the expression `p.result()` has **static type `Number`**, while the object returned at runtime is `Integer`. When using a variable of type `IntegerProducer`, the expression `result()` has static type `Integer`.

### Valid and invalid return types

| Parent method | Overriding method | Result |
| --- | --- | --- |
| `Number get()` | `Integer get()` | Valid: `Integer` is a subtype of `Number` |
| `Object create()` | `String create()` | Valid: reference subtype |
| `CharSequence text()` | `String text()` | Valid |
| `int count()` | `int count()` | Valid |
| `int count()` | `long count()` | **Error:** primitives cannot be substituted just because widening conversion exists |
| `void reset()` | `void reset()` | Valid |
| `void reset()` | `boolean reset()` | **Error:** `void` must remain `void` |
| `String label()` | `Object label()` | **Error:** attempting to widen from `String` to `Object` |
| `List<String> list()` | `ArrayList<String> list()` | Valid: subtype of `List<String>` |
| `List<String> list()` | `List<Object> list()` | **Error in the normal case:** generic `List` is invariant |

**Do not treat autoboxing as a return override substitution.** `int` and `Integer` are different; the fact that Java autoboxes in expressions does not make `Integer get()` valid to override `int get()`.

### The full concept: return-type-substitutability

JLS `8.4.5` defines *return-type-substitutable*. For reference types, the subtype relationship is the common case, yet the standard also permits certain compatibilities with legacy generic/raw source code and **requires an unchecked warning** when the return type is not a strict subtype. Therefore, stating "the return type must always be a strict subtype, with absolutely no exceptions" is incomplete for pre-generics Java libraries.

For new code: prefer the same return type or a clear subtype, and do not use raw types to "bypass" type checking. When the compiler emits a warning about return-type substitution, understand it as a signal of missing type safety that can manifest at runtime.

### Intentionally erroneous example due to return type

```java
class Parent {
    Number value() {
        return 1;
    }
}

class BadChild extends Parent {
    @Override
    String value() {
        return "x";
    }
}
```

This is a **negative test example and must not compile successfully**. `String` is not a subtype substitutable for `Number`; rename the method, change the parameters (if you truly want to overload), or choose a return type compatible with the parent contract.

## 4. `throws`: checked and unchecked exceptions

Before checking `throws` on an override, distinguish:

- **Checked exception:** a subtype of `Throwable` not belonging to `RuntimeException` or `Error`. Examples: `IOException`, `FileNotFoundException`, `SQLException`. The compiler requires handling or declaring it when an operation can throw a checked exception according to exception analysis rules.
- **Unchecked exception:** `RuntimeException` and its subclasses, `Error` and its subclasses. Examples: `IllegalArgumentException`, `NullPointerException`. Not required to be caught/declared in `throws` under the checked exception mechanism.

From **a method declaration**, `throws` is part of the exception-checking contract for calling code; `throws` is **not** a component used to distinguish overloads. A method can declare a checked exception without throwing that exception on every execution path; similarly, a method that does not declare unchecked exceptions can still throw unchecked types at execution time.

## 5. Checked exception rules when overriding

**An overriding method must not declare new or broader checked exceptions than what the overridden method allows.** Common cases:

| Parent method | Child method | Valid? |
| --- | --- | --- |
| `void load() throws IOException` | `void load() throws IOException` | Yes: same type |
| `void load() throws IOException` | `void load() throws FileNotFoundException` | Yes: narrower checked exception |
| `void load() throws IOException` | `void load()` | Yes: removes checked exception completely |
| `void load()` | `void load() throws IOException` | **No:** adds a checked exception |
| `void load() throws FileNotFoundException` | `void load() throws IOException` | **No:** widens checked exception |
| `void load() throws IOException` | `void load() throws Exception` | **No:** widens |
| `void load()` | `void load() throws IllegalStateException` | Yes: unchecked exceptions are not subject to this restriction |
| `void load() throws IOException` | `void load() throws IOException, IllegalArgumentException` | Yes: adding unchecked is allowed |

`FileNotFoundException extends IOException`, so if the parent allows `IOException`, declaring `FileNotFoundException` in the child is a valid narrowing. Conversely, if the parent only allows `FileNotFoundException`, the child cannot declare `IOException` because it also has other subclasses.

If the parent method declares **multiple checked exceptions**, each checked exception on the child method must have a valid relationship with at least one exception permitted by the parent method, per the exact rules of JLS `8.4.8.3`, and must also satisfy every corresponding method overridden/hidden in the inheritance hierarchy. For generic `throws T`, type variables and erasure also involve additional details; do not substitute a simple subtype diagram for the entire standard.

### Error example: widening `throws`

```java
import java.io.IOException;

class Parent {
    void read() throws IOException {
    }
}

class BadChild extends Parent {
    @Override
    void read() throws Exception {
    }
}
```

**The snippet above intentionally causes a compile-time error.** `Exception` is broader than `IOException`, so code calling through `Parent` may only be prepared to handle `IOException` without knowing about other checked exceptions from the override. Change `throws Exception` to `throws IOException`, a subtype such as `FileNotFoundException`, or remove the declaration if the body does not throw checked exceptions.

### What if it is not declared, yet the method body throws a checked exception?

The parent's `throws` may permit a kind of checked exception, yet **the child method body must still obey its own `throws` declaration**:

```java
import java.io.IOException;

class Parent {
    void load() throws IOException {
    }
}

class BadChild extends Parent {
    @Override
    void load() {
        throw new IOException("failed");
    }
}
```

Also **intentionally fails to compile**: the child method neither declares `throws IOException` nor catches that exception in its body. To make it valid, add `throws IOException` to the override (permitted because the parent declared it) or handle the exception with `try/catch`.

Do not infer that the parent's `throws` is automatically "inherited into the child method body." Which exception types the compiler checks at a declaration depends on the `throws` of **the declared method itself**, along with body exception analysis rules.

## 6. End-to-end example: covariant return + narrowing `throws` + dynamic dispatch

Create the source structure:

```text
project/
└── src/
    └── demo/
        └── Main.java
```

Full content of `src/demo/Main.java`:

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;

public class Main {
    static class Parent {
        public Number read() throws IOException {
            return -1;
        }
    }

    static final class Child extends Parent {
        @Override
        public Integer read() throws FileNotFoundException {
            return 42;
        }
    }

    public static void main(String[] args) throws IOException {
        Parent parentRef = new Child();
        Child childRef = new Child();

        System.out.println(parentRef.read());
        System.out.println(childRef.read().getClass().getSimpleName());
    }
}
```

From the `project` directory, using a JDK supporting Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
java -cp out demo.Main
```

**Exact stdout:**

```text
42
Integer
```

Explanation:

1. `Child.read()` is a valid override of `Parent.read()`. `@Override` confirms that relationship.
2. The return type narrows from `Number` to `Integer`, which is a valid **covariant return**.
3. The parent's `throws IOException` narrows to `throws FileNotFoundException` in the child, which is also valid. No actual exception is thrown in the example body.
4. `Parent parentRef = new Child();` has **static type** `Parent` but points to a `Child` object. Calling `parentRef.read()` uses the `Child.read()` implementation at runtime, so it prints `42`.
5. `childRef.read()` has static return type `Integer`; `getClass().getSimpleName()` on the return value yields the string `Integer`.
6. Because the call `parentRef.read()` is checked against type `Parent`, declaring `main throws IOException` here satisfies the compiler's checked exception requirement, even though the `Child` implementation throws nothing at runtime.

**Key takeaway:** Checked exception rules depend on the **compile-time type** of the call, while the method body dispatched depends on **the actual object**. You cannot conclude that code calling through `Parent` doesn't need to handle `IOException` just because it happens to hold a `Child`.

### You can omit `throws` in the child completely

Replace just the `Child.read()` method in the example with:

```java
@Override
public Integer read() {
    return 42;
}
```

The override remains valid because it both returns covariantly and completely drops the checked exception. If accessed via a variable of type `Parent`, the call is still checked by the compiler according to `Parent.read() throws IOException`.

## 7. Implementing an interface must also satisfy the same contract

Interface methods are normally `public`; the implementing class must declare the implementation with visibility at least `public`, a substitutable return type, and `throws` no broader. Similar rules apply to an abstract superclass and overridden default methods.

Valid example with **two interfaces**:

```java
import java.io.IOException;
import java.sql.SQLException;

interface Left {
    CharSequence report() throws IOException;
}

interface Right {
    String report() throws SQLException;
}

final class Reporter implements Left, Right {
    @Override
    public String report() {
        return "ready";
    }
}

class InterfaceExample {
    public static void main(String[] args) {
        Reporter reporter = new Reporter();
        System.out.println(reporter.report());
    }
}
```

Place this snippet in `InterfaceExample.java` (with no public top-level class) and run:

```sh
javac --release 17 InterfaceExample.java
java InterfaceExample
```

**Stdout:**

```text
ready
```

`String` is a subtype of `CharSequence` and is also the exact return type of `Right.report()`; the implementation **declares no checked exceptions**, so it does not violate either `IOException` or `SQLException` of the two interfaces. Note that if the implementation declared `throws IOException`, it would **fail to satisfy** the contract of `Right.report()`, because `IOException` is not a subtype allowed by `SQLException`. When one method must satisfy multiple superinterfaces, you must not check only the most convenient interface.

When calling through `Left` or `Right`, the compiler still checks the `throws` corresponding to each **static type**:

```java
Left left = new Reporter();
// left.report(); // Needs catch/throws IOException, even though Reporter.report() declares none.

Right right = new Reporter();
// right.report(); // Needs catch/throws SQLException.
```

This is only an **illustrative fragment**; the two call lines are commented out so they do not alter the complete runnable program.

### Default methods and conflicts

If two interfaces provide default methods with matching signatures and a class inherits both, the class normally must explicitly override to resolve the conflict. When writing your own override, it must still adhere to return-type substitutability and checked `throws` for the overridden contracts. Even when two abstract methods with the same signature are inherited from multiple interfaces, combining return types may be valid or produce a compile error if no suitable substitutable return type exists.

**Do not use default methods to arbitrarily redefine `public` methods of `Object`** such as `toString()`; the JLS has specific restrictions against default methods having signatures equivalent to `Object` methods.

## 8. Generics, erasure, and bridge methods: details related to override checking

With generic inheritance:

```java
class Box<T> {
    T get() {
        return null;
    }
}

class StringBox extends Box<String> {
    @Override
    String get() {
        return "text";
    }
}
```

`StringBox.get()` overrides `Box<String>.get()` validly. When type erasure occurs, the JVM method descriptor does not preserve all generic information as in source code; the compiler may generate a **synthetic bridge method** to preserve compatible dispatch. A bridge is a bytecode detail; it **does not** allow declaring two source methods differing only in return type.

You can use `javap -p -c` and, if needed, `javap -v` to study the bytecode generated by a JDK version. When working at the source level, rely on Java's override rules rather than manually writing bridge names or relying on implementation details.

### Generics are not covariant in type arguments

`List<String>` is **not** a subtype of `List<Object>`. Therefore, the following case is a **negative test**:

```java
import java.util.List;

class Base {
    List<Object> items() {
        return List.of();
    }
}

class BadChild extends Base {
    @Override
    List<String> items() {
        return List.of("a");
    }
}
```

The two return types have incompatible type arguments, so it is not a valid override. If the parent contract needs to allow flexibility, design the API carefully with general types or appropriate wildcards, rather than relying on raw types and ignoring warnings.

### Name clash due to erasure

Two methods `process(List<String>)` and `process(List<Integer>)` **cannot coexist to form two overloads distinguishable at runtime**, because after erasure the signatures may collide. `javac` detects name clash situations. This is a semantic error related to generic signatures, distinct from whether an override's return type/`throws` is valid.

## 9. Step-by-step compilation and reading diagnostics

When `javac` determines an overriding method is invalid, the message usually points out **the child method**, **the overridden method**, and the issue such as an incompatible return type, broader checked exception, reduced visibility, or not actually overriding.

Some common diagnostic forms (wording, caret positions, and order may vary by JDK):

| Error content | What to check |
| --- | --- |
| `method does not override or implement a method from a supertype` | Did you misspell the name, get parameter types wrong, use `@Override` for an overload, or try to override an un-overridable method? |
| `return type ... is not compatible with ...` | Did it violate covariant return, primitive/void rules, or generic invariance? |
| `overridden method does not throw ...` | Is the child method adding a checked exception that the parent does not permit? |
| `... is overridden method ... throws ...` | Is the checked exception in the child broader than the contract? |
| `attempting to assign weaker access privileges` | Was `public`/`protected` narrowed? |
| `overridden method is final` | Are you overriding a `final` method? |
| `name clash: ... have the same erasure` | Is there a generic signature conflict after erasure? |
| `... is not abstract and does not override abstract method ...` | Is a concrete class missing implementations for abstract/interface methods? |

Investigation workflow:

1. Confirm the **name, parameter types, and modifiers** of the parent and child methods; for generics, check the types after substituting type arguments of the superclass/interface.
2. Check whether the parent method can be inherited/overridden: `static`, `private`, `final`, package accessibility, module visibility.
3. Compare **return types**: same type, subtype, primitive/void, generic invariant, or a legacy case with an unchecked warning?
4. Compare **checked exceptions** in `throws`: each type in the child must be valid against **every** overridden contract.
5. Ensure the **body** catches or declares checked exceptions it may throw; this is a different check from the validity of the override itself.
6. Recompile with the target compiler and release. If more diagnostics are needed, `-Xdiags:verbose` can be used; read the first error with a clear cause instead of only reading the last error line.
7. Only after compilation succeeds, run tests for dispatch behavior and exception handling.

The snippets explicitly marked **intentionally erroneous** above are negative tests; they should not be merged into the same file as a runnable example. When compiling erroneous examples, do not expect an exact full stderr match because diagnostic formatting depends on the JDK.

## 10. Common misconceptions

**"If the child method has the same name, it is an override."** No. You must compare signatures, inheritance relationships, and instance method conditions. Changing parameter types can make it an overload. The `@Override` annotation helps catch mistakes.

**"Return types can differ arbitrarily as long as they can be cast."** No. Covariant return for reference types and the return-type-substitutability rule are the standard. Primitive widening/boxing does not make an override valid.

**"The child can declare `throws Exception` because Exception is the parent of IOException."** Wrong: widening checked exceptions breaks the contract from the caller's side. `IOException` in the parent does not allow the child to arbitrarily declare `Exception`.

**"Omitting `throws` in the child means no caller has to catch."** Wrong: callers using the static parent type must still satisfy checked exceptions in the parent declaration.

**"Unchecked exceptions cannot be declared in the child."** Wrong. You can add `RuntimeException` or its subclasses in `throws` without violating checked exception restrictions, though the API should still consider its behavioral contract.

**"`static` methods are overridden just like instance methods."** No. Static methods can be hidden; selection is based on the reference type at compile time, not dispatched by the object.

**"`private` in the parent can be overridden if `@Override` is used."** No. Annotations do not change inheritability/overridability.

**"All methods implementing an interface can be made package-private."** No. Implementations need `public` to match interface methods.

**"A class implementing two interfaces only needs to satisfy `throws` of one interface."** No. The implementation must satisfy all relevant declarations; if the checked exception sets do not overlap, dropping checked exceptions is often the simplest option.

**"If compilation succeeds, the method cannot throw other exceptions."** No. Unchecked exceptions can still appear at runtime, and checked/unchecked failures must be analyzed according to actual semantics; compile-time checking does not prove a program is error-free at runtime.

## 11. Checklist for reading or writing an override

- [ ] Is there a valid extends/implements relationship? Is the parent method overridable?
- [ ] Do the name and parameter list form a matching subsignature, including generics/erasure?
- [ ] Is `@Override` present so the compiler checks the override?
- [ ] Does the method avoid overriding `final`/`private` or confusing with `static` hiding?
- [ ] Is the child's visibility at least as wide as the parent's?
- [ ] Is the return type the same or return-type-substitutable (reference subtype, appropriate primitive/void)?
- [ ] Does `throws` avoid adding or widening checked exceptions compared to all overridden methods?
- [ ] Does the method body handle/declare checked exceptions that it throws itself?
- [ ] Has a concrete class implemented all required abstract/interface methods?
- [ ] When calling via a parent type, has the caller code handled checked exceptions of the **static type**, and has runtime dispatch been verified?

**Core takeaway:** The compiler protects the inheritance contract by checking **override relationship → access rights and return type → checked exception scope**. Covariant return helps subclasses specialize results; narrowing `throws` avoids forcing callers to handle new exceptions; `@Override` turns overriding intent into a direct `javac` check.

### Authoritative reference documentation

- *Java Language Specification 17*, `8.4.2 — Method Signature; `8.4.5 — Method Result; `8.4.6 — Method Throws; `8.4.8 — Inheritance, Overriding, and Hiding: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- *Java Language Specification 17*, `9.4.1 — Interface Methods, Overriding: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
- *Java Language Specification 17*, `11.1 and `11.2 — Checked/Unchecked Exceptions and Compile-Time Checking: https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html