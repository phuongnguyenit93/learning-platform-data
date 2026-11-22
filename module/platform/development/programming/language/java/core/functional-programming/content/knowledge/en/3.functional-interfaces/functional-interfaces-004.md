# Methods Matching `public` Methods of `Object` in Functional Interfaces

## 1. The Question: How Are Abstract Methods Counted?

A **functional interface** has a **single abstract method** (SAM): that is the contract a lambda expression or method reference must implement. This rule is not simply “count every `abstract` declaration line in the interface”.

According to the Java Language Specification (JLS) §9.8, when determining the SAM, abstract methods whose signatures correspond to **`public` instance methods of `java.lang.Object`** are excluded from the set of methods used to determine a functional interface. Therefore, an interface can declare `equals(Object)`, `hashCode()`, and `toString()` and still be a functional interface if, aside from those methods, only one domain abstract method remains.

This rule distinguishes **the inherent contract of every Java object** from **the new behavior** that a lambda must provide. It also explains why `java.util.Comparator<T>` can still be instantiated with a lambda even though that interface declares `equals(Object)` alongside `compare(T, T)`.

Lesson goals: read potentially confusing declarations accurately, recognize the `Object` exception, verify `@FunctionalInterface`, and write working lambdas.

## 2. Which Methods Are Excluded from the SAM Count?

For the three familiar methods, the valid signatures and return types when redeclared in an interface are as follows:

| Abstract declaration in interface | Corresponding `public` method of `Object` | Counted as a new SAM? |
| --- | --- | --- |
| `boolean equals(Object other);` | `Object.equals(Object)` | No |
| `int hashCode();` | `Object.hashCode()` | No |
| `String toString();` | `Object.toString()` | No |
| `boolean equals(String text);` | **Does not match** `equals(Object)`: different parameter type | Yes |
| `Object clone();` | `Object.clone()` is `protected`, not `public` | Yes |
| `void run();` | No corresponding method in `Object` | Yes |

**The condition is in the signature, not just the name.** `equals(Object)` is excluded; `equals(String)` is a different *overload*, so it is still counted as a separate abstract method. Matching the name `toString` while declaring the wrong return type is also invalid: it does not become a new SAM method.

The scope of the rule is **`public` non-`static` methods of `Object`**. `Object`'s `clone()` and `finalize()` have `protected` visibility, so if an interface declares methods with matching signatures as `public abstract`, they **are not exempt from counting**. `final` methods such as `getClass()`, `wait()`, and `notify()` cannot be validly redeclared as overrides in an interface in the first place; do not infer that you can freely add such declarations to form a functional interface.

“Not counted toward the SAM” only means that the lambda **does not have to provide a separate body for them**. The object implementing the interface still has the normal `Object` behaviors. `Object.equals` itself also has reflexivity, symmetry, transitivity, and consistency contracts; the SAM rule does not alter those contracts.

## 3. Complete Example: Multiple Declarations Yet Still One SAM

Create the file `ObjectMethodSamDemo.java` with the entire content below:

```java
import java.util.Comparator;

@FunctionalInterface
interface Job {
    boolean equals(Object other);
    int hashCode();
    String toString();
    void run(String text);
}

interface IdentityRule {
    boolean equals(Object other);
}

@FunctionalInterface
interface Normalizer extends IdentityRule {
    String normalize(String text);
}

public class ObjectMethodSamDemo {
    public static void main(String[] args) {
        Job job = text -> System.out.println("Xu ly: " + text);
        job.run("Java");
        System.out.println(job.equals(job));

        Normalizer normalizer = String::trim;
        System.out.println("[" + normalizer.normalize("  functional  ") + "]");

        Comparator<String> byLength =
                (a, b) -> Integer.compare(a.length(), b.length());
        System.out.println(byLength.compare("Go", "Java"));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 -encoding UTF-8 ObjectMethodSamDemo.java
java ObjectMethodSamDemo
```

Output:

```text
Xu ly: Java
true
[functional]
-1
```

Explanation:

1. `Job` declares four abstract methods, but the three methods `equals(Object)`, `hashCode()`, and `toString()` match `public` methods of `Object`, so **only `run(String)` is the SAM**. The expression `text -> ...` provides the implementation of `run`.
2. `job.run("Java")` executes the lambda body. `job.equals(job)` calls the object comparison method, not `run`. The result is `true` because the object is compared to itself.
3. `IdentityRule` only declares `equals(Object)`, so by itself it is **not** a functional interface (it has no new SAM). `Normalizer` extends this interface and adds exactly `normalize(String)`; therefore `Normalizer` **is** a functional interface. `String::trim` is a method reference compatible with `normalize`.
4. `Comparator<String>` is a real Java example: `compare(T, T)` is the functional method, while the `equals(Object)` declaration does not increase the SAM count. The lambda comparing the lengths of `"Go"` (2) and `"Java"` (4) returns `-1`.

The output and validity of the program were verified with `javac --release 17` and `java`. The auxiliary interfaces reside in the same file and are not declared `public` so that the filename matches the `public class ObjectMethodSamDemo`.

## 4. Why Are `equals`, `hashCode`, and `toString` Treated Specially?

Every instance of a Java class inherits from `Object` (directly or indirectly). A class implementing an interface already has the appropriate `public` methods from `Object`, or can override them according to the class's contract. Therefore, an interface restating `equals(Object)` does not create an independent domain behavior that a lambda needs to define.

Compare:

```java
@FunctionalInterface
interface TextOperation {
    String transform(String text);   // Single functional method

    boolean equals(Object other);   // Not counted toward SAM
    int hashCode();                 // Not counted toward SAM
    String toString();              // Not counted toward SAM
}
```

The declaration above is valid. A lambda such as `TextOperation upper = String::toUpperCase;` implements `transform`. It does not define how `equals`, `hashCode`, or `toString` behave; how `Object` methods behave on a lambda object belongs to the object's implementation. You should not build business logic on the generated class name, the `toString()` string, or whether two evaluations of a lambda yield the same object identity.

**Distinguish “methods already provided by the class” from “abstract methods that the lambda must implement”:** this exception belongs to Java's SAM determination rules, not a mechanism that removes `Object` methods from the object at runtime.

## 5. Two Most Common Confusing Cases

### 5.1. An Interface Declaring Only `equals(Object)`

```text
@FunctionalInterface
interface OnlyEquality {
    boolean equals(Object other);
}
```

This snippet is **intentionally invalid with `@FunctionalInterface`**. `equals(Object)` is excluded from the count, so the interface has no abstract method left to serve as a SAM. If the annotation is removed, the interface declaration itself is valid; however, you cannot use a lambda to create an `OnlyEquality`. The compiler catches the error at the annotation rather than waiting until a lambda is used.

### 5.2. An Interface with `equals(String)` and `run()`

```text
@FunctionalInterface
interface TwoAbstractMethods {
    void run();
    boolean equals(String text);
}
```

This snippet is also **intentionally invalid**: `equals(String)` is a different method from `Object.equals(Object)` and is counted in the set of abstract methods. Together with `run()`, the interface has **two** non-equivalent abstract behaviors, so it is no longer a functional interface.

Rule to remember: **same name does not mean same signature**. You must check the name, parameter types, and valid override relationships. Only `equals(Object)` with the exact signature belongs to the exception in this case.

## 6. Distinguishing from `default`, `static`, and `private`

Besides the `Object` exception, an interface can have `default`, `static`, or `private` methods alongside the SAM. These methods have implementation bodies or distinct roles, so they do not create a second domain abstract method.

```java
@FunctionalInterface
interface LabeledAction {
    void execute(); // Single SAM

    boolean equals(Object other); // Redeclaring Object method

    default String label() {
        return "action";
    }

    static LabeledAction of(Runnable runnable) {
        return runnable::run;
    }

    private String prefix() {
        return "label";
    }

    default String decoratedLabel() {
        return prefix() + ":" + label();
    }
}
```

This is a valid interface declaration in Java 17+, used as an example inside a source file (not a program with `main`). `execute` remains the SAM; `label`, `decoratedLabel`, `of`, and `prefix` are not counted as abstract methods.

**Important note:** you cannot provide a `default` body to directly override a `public` method of `Object` in an interface. For example:

```text
interface InvalidDefault {
    default String toString() {
        return "x";
    }
}
```

This is an **intentionally non-compiling example**, because `default toString()` overrides a method of `Object`. To customize `toString`, the implementing class must override it under class rules; you cannot use a `default` method like this.

## 7. `clone()` Is an Exception to… the Exception

`Object.clone()` has `protected` visibility, unlike `equals`, `hashCode`, and `toString`. Therefore, if an interface declares `Object clone();`, that method **is counted** in the set of abstract methods when checking for a SAM.

Consider two cases:

```text
@FunctionalInterface
interface CloneOnly {
    Object clone();
}
// Valid: clone() is a new SAM because Object.clone() is not public.

@FunctionalInterface
interface CloneAndRun {
    Object clone();
    void run();
}
// Invalid: there are two abstract methods to implement.
```

The code is presented to classify valid vs. invalid cases; it is not a single compilable program because `CloneAndRun` is intentionally wrong. Both conclusions were verified with `javac --release 17`.

You should avoid using `clone` as a routine teaching API unless copying behavior is genuinely needed: it has its own requirements and limitations related to `Cloneable`, access rights, and return types. The key takeaway here is that **`protected` is not exempt from counting**, even though the method exists on `Object`.

## 8. How to Determine Whether an Interface Is a Functional Interface Yourself

1. Gather the **abstract** methods declared directly or inherited from parent interfaces. `default`, `static`, and `private` methods are not abstract requirements that a lambda must implement.
2. Exclude abstract methods whose signatures correspond to **`public` instance methods of `Object`**, which in common examples are `equals(Object)`, `hashCode()`, and `toString()`.
3. For the remaining abstract methods, check whether the signatures can be **override-equivalent** to represent a single contract, and whether the return types are compatible under the *return-type-substitutable* rules. Do not just count lines when the interface uses inheritance.
4. If exactly one functional contract is identified, the interface can serve as a target type for lambdas/method references. If there is no contract, or there are multiple independent contracts, the interface is not a functional interface.
5. Add `@FunctionalInterface` so the compiler verifies the design intent. This annotation **does not turn** a multi-SAM interface into a valid one, and a qualifying interface remains a functional interface even when the annotation is missing.

An inheritance case with two abstract methods having equivalent signatures can still form a single functional contract if the return-type compatibility condition is met. Do not generalize that “every interface with more than one `abstract` declaration is wrong”: the `Object` exception is one reason, and override-equivalent abstract methods are another.

## 9. Real-World Example: `Comparator<T>`

`java.util.Comparator<T>` is a widely used functional interface. Its domain contract is comparing two values via `int compare(T a, T b)`. The interface also declares `boolean equals(Object obj)`, but that declaration does not increase the SAM count.

```java
Comparator<String> comparator =
        (left, right) -> Integer.compare(left.length(), right.length());
```

This is an illustrative snippet placed inside a method, after `import java.util.Comparator;`; this same comparison appeared in the full runnable program in section 3. The reason the lambda is valid is not that Java “ignores every method other than `compare`”, but because `equals(Object)` belongs to a **clearly defined exception** in the JLS.

When using `Comparator` in `sort`, `TreeSet`, or `TreeMap`, remember the consistency conditions of comparison. The existence of the `Object` exception in SAM counting does not determine sorting logic or how collections use the result of `compare`.

## 10. Common Mistakes and How to Fix Them

| Incorrect statement or code | Why it is wrong | Correct understanding |
| --- | --- | --- |
| “Declaring `equals(Object)` gives the interface two SAMs.” | `equals(Object)` matches a `public` method of `Object`. | Exclude it from the SAM count. |
| “Having only `equals(Object)` is enough to make a functional interface.” | No domain method remains after excluding the exception. | An interface with 0 SAMs cannot be used as a lambda target type. |
| “`equals(String)` is also excluded because it has the same name.” | The parameter type differs, so it is a separate overloaded method. | `equals(String)` is still counted. |
| “Any method of `Object` is not counted.” | `clone()` is `protected`. | The exception applies only to `public` instance methods. |
| “You can write `default toString()` in an interface.” | Java forbids `default` methods from overriding `Object` methods. | Only declare the corresponding abstract signature, or let implementing classes override it. |
| “Adding `@FunctionalInterface` is enough.” | The annotation only checks the constraint; it does not relax it. | Identify the SAM accurately before adding the annotation. |
| “You must implement both `equals` and `run` in the lambda.” | A lambda describes only one functional method. | The lambda provides the body for `run`; `Object` methods have their own object mechanism. |

## 11. Self-Check

**Exercise 1.** Is the interface below a functional interface? Why?

```java
interface A {
    String toString();
    int hashCode();
    int compute(int x);
}
```

Answer: **Yes**. The first two methods match `public` methods of `Object`; only `compute(int)` is the SAM.

**Exercise 2.** Classify the interface:

```java
interface B {
    boolean equals(String text);
    int hashCode();
}
```

Answer: **Yes**. `hashCode()` is excluded; `equals(String)` differs from `equals(Object)`, so it is a valid SAM. If `void run();` is added, the interface will have two independent abstract methods and will no longer be a functional interface.

**Exercise 3.** If a parent interface only declares `boolean equals(Object)`, can a subinterface adding `void execute()` accept a lambda?

Answer: **Yes**. The inherited `equals(Object)` is not counted as a SAM; `execute()` is the single functional method of the subinterface, just like the `IdentityRule` → `Normalizer` pattern in section 3's example.

**Exercise 4.** Distinguish the two lines:

```text
boolean equals(Object other);  // Not counted toward SAM
boolean equals(String other);  // Counted toward SAM
```

Answer: the parameter type determines two different signatures. Do not reduce the rule to “anything named `equals` is not counted”.

## 12. Takeaways and Official Reference

- The exception applies when counting abstract methods of a **functional interface**: methods whose signatures correspond to **`public` instance methods of `Object`** are not counted.
- `equals(Object)`, `hashCode()`, and `toString()` are the three important practical cases; `equals(String)` and `clone()` are **not** covered by this exception.
- A functional interface needs **a single functional contract** after applying the exception rule and override-equivalence rules. A lambda implements only that contract.
- `@FunctionalInterface` helps catch mistakes right at the declaration. `Comparator<T>` is a built-in example of declaring `equals(Object)` while still supporting lambdas.

Rule source: [Java Language Specification — §9.8 Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8), combined with interface member and method rules in JLS §9.2 and §9.4.