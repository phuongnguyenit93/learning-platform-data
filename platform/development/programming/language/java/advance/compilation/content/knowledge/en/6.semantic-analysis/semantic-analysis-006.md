# Raw types, unchecked conversion, and the meaning of javac warnings

In Java, generics such as **List<String>**, **Map<String, Integer>**, or **Box<T>** help the compiler verify type compatibility right when writing code. However, Java still allows using a **raw type** such as **List** or **Box** without type parameters for compatibility with legacy libraries. It is precisely this compatibility path that can lose evidence of element types and generate **rawtypes**, **unchecked conversion**, **unchecked call**, or **unchecked cast** warnings.

The most important thing to understand: **an unchecked warning indicates an operation whose type safety the compiler cannot prove at compile time**. It does not assert that the program is definitely wrong, but it cannot be treated merely as a decorative message. The code may compile and run for a stretch before throwing a **ClassCastException**, or cause a collection to hold an element contrary to the type that the program trusts.

## 1. What do generics guarantee when not using raw types?

Consider this Java 17+ snippet:

~~~java
import java.util.ArrayList;
import java.util.List;

public class TypedList {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println(names.get(0));
    }
}
~~~

Here **List<String>** represents a list whose elements are treated as **String**. When calling **names.add("Lan")**, javac matches the argument type against the type parameter **String**. If replaced with **names.add(42)**, the compiler reports a type error because **Integer** cannot be converted to **String** in this **add** call.

Compile and run:

~~~bash
javac -d out TypedList.java
java -cp out TypedList
~~~

Output:

~~~text
Lan
~~~

The protection from generics is largely **static checking**. Because of **type erasure**, at runtime the JVM does not maintain each **ArrayList<String>** object as a distinct class from **ArrayList<Integer>**. The compiler typically inserts an appropriate cast when reading from a parameterized type to satisfy the type of the receiving variable. Therefore, a path that breaks type safety can leave behind an error that only surfaces on a later read.

## 2. What is a raw type?

### 2.1. Definition and examples

Given a generic declaration **G<T>**, writing the class or interface name **G** while omitting the type argument list produces a **raw type**. For example:

| Declaration | Category | Notes |
| --- | --- | --- |
| **List<String>** | Parameterized type | Elements have type String |
| **List<Integer>** | Parameterized type | Elements have type Integer |
| **List<?>** | Parameterized type with wildcard | Can be read as Object; exact element type is unknown |
| **List** | Raw type | All generic parameter information is omitted at the use site |
| **Map<String, Integer>** | Parameterized type | Has key/value information |
| **Map** | Raw type | No longer has K, V type arguments |
| **String** | Non-generic type | Not a raw type because String does not declare type parameters |

With a custom generic class:

~~~java
final class Box<T> {
    private T value;

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

**Box<String>** is a parameterized type; **Box** is the raw type of the same generic class. A raw type does not create a separate class on its own, does not alter the source declaration **Box<T>**, and is not a synonym for **Object**. **Box** is still Box at the class level, but the usage of members that depend on the parameter **T** is viewed through erasure rules.

According to JLS §4.8, the concept of raw type also includes the case of an array whose element type is a raw type and certain inner member class types belonging to a raw outer type. For an introductory lesson, the most common case is writing **List** instead of **List<E>**.

### 2.2. Why do raw types exist?

Generics were introduced in Java 5, after many libraries such as the Collections Framework already had users. If the compiler had required all pre-Java 5 code to be immediately rewritten into **List<E>**, source compatibility with legacy code would have been severely impacted.

Raw types allow:

- Legacy code to pass **List** to a new generic API in certain cases.
- Generified APIs to still provide a path for legacy callers.
- A project to migrate gradually from APIs lacking generics to parameterized APIs.

**This is an intentional compatibility mechanism, not the default choice for new code.** When the element type is known, use **List<String>**, **List<Integer>**, **Map<Key, Value>**, or an appropriate generic type. When the element type is genuinely unknown and only reading is needed, **List<?>** is typically used instead of raw **List**.

## 3. Distinguishing rawtypes warnings and unchecked warnings

These two warning groups are related but **not identical**.

### 3.1. The rawtypes warning: detecting use of a raw generic type

For example:

~~~java
List names = new ArrayList();
~~~

If **-Xlint:rawtypes** is enabled, javac warns that **List** and **ArrayList** are used as raw types. This is a reminder that the code is losing generic information. Merely declaring a raw type variable can trigger a **rawtypes** warning, even before any mistyped data exists.

### 3.2. Unchecked call: invoking a member through a raw type

For example:

~~~java
List values = new ArrayList();
values.add(42);
~~~

In the generic interface **List<E>**, the method is **boolean add(E e)**. When called through raw **List**, the parameter **E** has been erased to **Object**. javac can no longer verify that the call is compatible with the element type expected by another generic reference. The statement **values.add(42)** produces an **unchecked call to add(E)** warning when **-Xlint:unchecked** is enabled.

**Not every call on a raw type generates an unchecked warning.** According to JLS §4.8, the unchecked warning of a raw member invocation depends on whether erasure changes the parameter types of the method/constructor. For example, reading **values.size()** does not automatically produce an unchecked invocation merely because the receiver is raw **List**.

### 3.3. Unchecked conversion: from a raw type to a parameterized type

For example:

~~~java
List raw = new ArrayList();
List<String> strings = raw;
~~~

In the second assignment, javac accepts **List → List<String>** under the **unchecked conversion** rule (JLS §5.1.9), but cannot prove that the elements are actually **String**. Therefore, it emits an **unchecked conversion** warning.

This is a directional rule:

- **List<String> → List**: assignable via raw compatibility, usually does not cause an **unchecked conversion** warning on the assignment itself; the raw declaration can still trigger **rawtypes** if lint is enabled.
- **List → List<String>**: allowed via unchecked conversion and produces an unchecked warning.
- **List<String> → List<Object>**: **invalid** solely because String is a subtype of Object; generic types here are invariant.
- **List<String> → List<?>**: valid, preserving type checking within wildcard bounds.

According to JLS §5.1.9, converting from raw **G** to **G<?>** (where all arguments are unbounded wildcards) does not require an unchecked conversion warning like converting to **G<String>** does. Therefore, **List<?> view = raw;** is a safer direction when only inspecting a list whose element type is unknown.

### 3.4. Unchecked cast: casting that the runtime cannot sufficiently verify

~~~java
Object unknown = new ArrayList<Integer>();
List<String> strings = (List<String>) unknown;
~~~

This cast can be accepted by javac with an **unchecked cast warning**, yet the JVM only checks whether the object belongs to the appropriate raw class/interface **List**. The runtime cannot verify the element type argument **String** through that cast. If an **Integer** element is read out via the **List<String>** reference, the program can encounter a **ClassCastException**.

Distinguish carefully:

- **Unchecked conversion** usually appears when the compiler automatically allows converting a raw type to a parameterized type in an assignment/argument-passing/return context.
- **Unchecked cast** is an explicit cast written by the programmer, where the runtime lacks complete generic information to verify the contents.
- **Unchecked method invocation** usually occurs at a method call on a raw receiver when the signature has undergone erasure.
- **rawtypes** warns immediately on using a generic name without type arguments; by itself it does not mean an unchecked conversion just occurred.

Besides the examples above, certain cases of generic varargs, narrowing conversions, or overriding can also carry unchecked warnings; the **unchecked** label should not be understood as applying only to Collections.

## 4. Example 1: raw List breaks the type promise

Create the file **RawRisk.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawRisk {
    static void addLegacy(List items) {
        items.add(42);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        List legacy = names;
        addLegacy(legacy);

        System.out.println(names.size());
        System.out.println(names.get(0));

        try {
            String value = names.get(1);
            System.out.println(value);
        } catch (ClassCastException exception) {
            System.out.println("ClassCastException");
        }
    }
}
~~~

Compile and run using **JDK 17+**:

~~~bash
javac -Xlint:rawtypes,unchecked -d out RawRisk.java
java -cp out RawRisk
~~~

**Exact standard output** of the program:

~~~text
2
Lan
ClassCastException
~~~

Example verified on JDK 21: the compilation step succeeds with **3 warnings** when both lint groups are enabled; the run produces stdout exactly as above. The wording/line numbers of the diagnostics may vary by JDK, so do not treat them as stable stdout.

Sequence of events in order:

1. **names** is a **List<String>**: **"Lan"** is added via a statically checked call.
2. **legacy** is a raw-typed alias to the **same list object**. This assignment neither creates a copy nor removes existing elements.
3. **addLegacy(legacy)** takes raw **List** and calls **add(42)**. The call produces an unchecked warning because generic checking for **E** is no longer guaranteed.
4. An Integer object is inserted into the list while **names** is still viewed as **List<String>**.
5. **names.size()** is still **2**, **names.get(0)** is still **"Lan"**. However, when assigning **names.get(1)** to **String**, the runtime needs to cast the Integer element to String and throws **ClassCastException**.

This is an illustration of **heap pollution**: the actual state of an object contains a value incompatible with the parameterized type that a reference claims. A compile-time warning is a signal of **a path that can break type safety**, even when the exception occurs very far from the warned code location.

**Why does it not fail at the add statement immediately at runtime?** In bytecode, generic type arguments have mostly been erased. The add method of raw List takes Object; the JVM does not automatically know that the ArrayList object is being viewed by another caller as List<String>. The cast check appears when the program uses the result with a concrete type.

## 5. Example 2: direct unchecked conversion

Create **UncheckedConversion.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class UncheckedConversion {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add(7);

        List<String> strings = raw;

        System.out.println(strings.size());
        try {
            String first = strings.get(0);
            System.out.println(first);
        } catch (ClassCastException exception) {
            System.out.println("ClassCastException");
        }
    }
}
~~~

Run:

~~~bash
javac -Xlint:rawtypes,unchecked -d out UncheckedConversion.java
java -cp out UncheckedConversion
~~~

**Standard output:**

~~~text
1
ClassCastException
~~~

The example has been run on JDK 21. With the two lint groups above, javac reports **4 warnings**, including **unchecked call** for **raw.add(7)** and **unchecked conversion** at the assignment **List<String> strings = raw**; the remaining two warnings belong to **rawtypes** for writing raw **List** and **ArrayList**.

Analysis at the points checked by the compiler:

~~~text
List raw = new ArrayList();
              |
              +-- No type argument: rawtypes warning when lint is enabled

raw.add(7);
    |
    +-- Parameter type of add(E) cannot be checked like a List<String>:
        unchecked invocation warning

List<String> strings = raw;
                       |
                       +-- Compiler cannot prove raw actually contains String:
                           unchecked conversion warning

String first = strings.get(0);
                         |
                         +-- Runtime cast from Object to String:
                             ClassCastException when the element is an Integer
~~~

**It is not the case that the compiler checked every element first before allowing the assignment.** If there were a mechanism checking the entire contents at assignment time, Java would need a runtime check against erased type arguments, which is not provided here. The warning indicates that the compiler bypasses the static barrier to support compatibility with legacy code.

## 6. Relationship to type erasure and runtime checks

Java generics use **type erasure**: type parameters are used by javac during static analysis, after which many generic traces do not appear as a separate runtime class. For example, generic **List<String>** and **List<Integer>** both rely on the runtime type **List** / corresponding implementation. Generic declaration information may remain in metadata such as bytecode signatures for the compiler/reflection to read; that **does not make the runtime check each element automatically**.

Three points need to be separated:

| Operation | Can the compiler check it? | What does the runtime check? |
| --- | --- | --- |
| **List<String> xs; xs.add("ok")** | Yes, argument is String | Generic element type is usually not re-checked at add |
| **List raw = xs; raw.add(42)** | Type argument not guaranteed; unchecked call | add takes Object after erasure |
| **String s = xs.get(1)** | Trusts static type List<String> | Cast to String may fail if the list has been polluted |
| **(List<String>) object** | Type argument not proven | Cast checks raw List, does not iterate over all elements |
| **List<?> view = xs** | Valid, assumes no specific element type | Reads elements as Object |

**Do not infer that every operation on generics lacks runtime checks.** For example, Java arrays have runtime element type checking and can throw **ArrayStoreException**; that is a different mechanism from generic List. The focus of this lesson is the raw/unchecked path in generics.

## 7. Differences between List, List<Object>, and List<?>

Many people fix a raw type to **List<Object>** thinking the two types are equivalent. They are not equivalent:

~~~java
List<String> names = new ArrayList<>();
List<?> view = names;         // Valid: exact element type is unknown
Object item = view.get(0);    // Valid: read as Object

// List<Object> objects = names; // Compile error: invariant generic types
// view.add("X");                // Compile error: capture of ? is unknown
// view.add(42);                 // Compile error
~~~

**List<?>** means “a List with some unknown element type”, still maintaining a static barrier when adding elements. Only **null** can be added to a **List<?>**-typed list under the general contract, although the implementation itself may not support adding elements. **List<Object>** means a list that accepts Object per the generic API; it does not substitute for every **List<T>**.

For an API that only prints or counts elements:

~~~java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

Writing **List<?>** expresses the intent more accurately than **List** and avoids unchecked **add** call paths.

When needing to accept any specific subtype of Number for reading, **List<? extends Number>** can be used; when needing to add Number into a compatible collection, **List<? super Number>** can be considered. Wildcards are a tool for expressing type-safe constraints, not a cast that suppresses warnings.

## 8. How to handle raw data from legacy APIs safely

If a legacy library returns a raw **List**, do not assign it directly to **List<String>** and hope the elements are always right. If a guarantee is needed, accept the input using a wildcard, check each element, and **copy into a new List<String>**.

Create **SafeBoundary.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeBoundary {
    static List<String> validateAndCopy(List<?> values) {
        List<String> result = new ArrayList<>();
        for (Object element : values) {
            if (!(element instanceof String name)) {
                throw new IllegalArgumentException("Expected String");
            }
            result.add(name);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(validateAndCopy(List.of("An", "Binh")));
        try {
            validateAndCopy(List.of("An", 42));
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -Xlint:rawtypes,unchecked -d out SafeBoundary.java
java -cp out SafeBoundary
~~~

**Standard output verified on JDK 21:**

~~~text
[An, Binh]
Expected String
~~~

This example has no raw types or unchecked conversions. If receiving a raw reference from a legacy API, you can assign it to **List<?>** and pass it to **validateAndCopy**. Each element is checked with **instanceof String** before being added to the new list. **List.copyOf** creates a list that cannot be modified via ordinary mutators; copying also detaches from the source list, which might continue to be modified by legacy code.

In a real program, you should design the handling of **null**, malformed data, and memory size according to the contract. In the example above, **null** is rejected because it fails **instanceof String**, so it fits the constraint of **List.copyOf**.

### 8.1. What if copying is not possible?

Some systems need to keep a shared alias with legacy data because an API mutates it directly. In that case, isolate the raw type at an adapter layer, establish the contract of the legacy API, validate data before use, and avoid propagating the cast type throughout the application. Checking the current data **does not automatically guarantee** that the collection will not have a mistyped element inserted later by another raw alias.

If the contract permits, creating a read-only wrapper, limiting mutation capabilities, or converting to a data type with an explicit validator will be easier to control than casting raw once and assuming the problem has disappeared.

### 8.2. Why not simply cast?

~~~java
Object unknown = new ArrayList<Integer>();
@SuppressWarnings("unchecked")
List<String> strings = (List<String>) unknown;
~~~

This snippet **only illustrates syntax, not a safe solution**. The annotation silences the unchecked warning at that location; it does not verify elements, does not change the runtime object, and does not protect against a ClassCastException if an Integer element is later read as String.

If you can inspect each element and copy as in **SafeBoundary**, use that approach instead of an unchecked cast.

## 9. Reading and classifying javac diagnostics

To view warnings more clearly when compiling a file, use:

~~~bash
javac -Xlint:rawtypes,unchecked -d out RawRisk.java
~~~

If the source of warnings in a project is not yet known, you can use:

~~~bash
javac -Xlint:all -d out RawRisk.java
~~~

Important categories:

| Tag | Practical meaning | How to handle |
| --- | --- | --- |
| **[rawtypes]** | Code references a generic class/interface while omitting type arguments | Declare an appropriate type argument or wildcard |
| **[unchecked] unchecked call** | Calls a method/constructor where the compiler cannot fully check parameter types | Remove the raw receiver, create a typed adapter, or review the API |
| **[unchecked] unchecked conversion** | Converts a raw type to a parameterized generic type without proving type arguments | Keep a wildcard, validate data then copy, or fix the method signature |
| **[unchecked] unchecked cast** | Cast involving type arguments that cannot be sufficiently checked at runtime | Avoid casting; prove the contract and limit scope if unavoidable |
| **[unchecked]** from other sources | For example generic varargs or certain other conversions | Read the location, method signature, and specific rules |

**javac** normally prints only a general note such as “uses unchecked or unsafe operations” if detailed lint is not enabled; that does not mean the issue has been resolved. Use **-Xlint:unchecked** to see unchecked operations, **-Xlint:rawtypes** to see raw type usage, or use both.

**-Werror** tells the compiler to treat warnings as errors that fail the compilation step. It is useful when a project wants to prevent new warnings from slipping into CI:

~~~bash
javac -Xlint:rawtypes,unchecked -Werror -d out RawRisk.java
~~~

With **RawRisk.java**, this command fails due to warnings; this does not mean the program contains invalid syntax, but rather that the build policy chooses to reject warnings. In a large project, only enable **-Werror** after understanding and resolving existing warnings, because some warnings may come from generated code or external APIs.

**Priority approach when fixing:** start from the source of the raw declaration or raw API boundary, then trace forward to the add/cast/conversion sites. Do not simply suppress the warning on the last line while ignoring where data loses control.

## 10. @SuppressWarnings: using it accurately and with justification

Java supports:

~~~java
@SuppressWarnings("unchecked")
~~~

and for raw type usage:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
~~~

The strings **"rawtypes"** and **"unchecked"** are also the keys used by javac with **-Xlint**. The annotation can be attached to a method, constructor, type, field, or local variable where valid, in order to limit the scope of suppression.

If interacting with a legacy API that cannot yet be changed is unavoidable:

1. Place the raw/unchecked part inside the smallest possible adapter method.
2. Explain with a comment **why the contract guarantees the type** or what condition has been checked.
3. If possible, check element types and then copy into a typed structure.
4. Write tests for valid data, mistyped data, and unintended mutation paths.
5. Suppress only the exact warning groups truly needed; avoid disabling warnings for an entire module.

**SuppressWarnings is not a runtime cast and does not turn unchecked code into checked code.** The annotation only affects whether the compiler emits diagnostics within the appropriate scope. Disappearing warnings do not prove the logic is safe; the responsibility for proving the contract shifts to the code author.

For generic varargs, **@SafeVarargs** is a different promise regarding the safety of an eligible method/constructor; use it only when the contract is truly met, and do not treat it as a default solution for raw types or unchecked conversions.

## 11. Distinguishing warnings and compile-time errors

Code with raw types usually still compiles:

~~~java
List raw = new ArrayList();
List<String> typed = raw; // Unchecked conversion warning
~~~

However, the following snippets produce a **compile-time error**, not merely a warning:

~~~java
List<String> names = new ArrayList<>();
// names.add(42);                  // Error: Integer is not String
// List<Object> objects = names;   // Error: generic List is invariant
// List<String> xs = new ArrayList<Integer>(); // Error: incompatible type arguments
~~~

A warning is a notice where the compiler detects a path whose safety cannot be proven, yet the language still allows it for compatibility. A compile error is where language rules reject the code. There is no rule that “a warning is a minor error that needs no handling”: its severity at runtime can be greater than a compile error caught early.

### 11.1. Why doesn't the code break immediately?

Common situations:

- A List has a wrong element inserted, yet the program only calls **size()**, so no mistyped cast occurs yet.
- The wrong element sits at a rarely accessed position; the error only occurs when real requests or data pass through.
- A legacy library returns a collection with the right element types in sample tests, yet has no guaranteed contract for all inputs.
- Another raw alias mutates the collection after one side has already checked the elements.

Therefore, an unchecked warning can be a signal of a **hard-to-reproduce latent bug**, especially at data boundaries received from frameworks, serialization, or legacy APIs.

## 12. Workflow for reviewing a real-world warning

When CI or an IDE displays a warning, you can answer step by step:

1. **Is this a raw type declaration or a specific unchecked operation?** Enable the appropriate **-Xlint** group and inspect the pointed line.
2. **Who owns the generic declaration?** If it is in the project's source, fix the signature to **List<T>**, **List<?>**, or an appropriate type. If it is a legacy library, consider an adapter.
3. **Is there a write operation into a collection with unknown elements?** If read-only, use a wildcard to avoid losing type safety.
4. **Who else holds an alias to the same object?** Casting to **List<String>** does not prevent another raw alias from inserting an Integer.
5. **Can we validate and copy?** This is often the way to eliminate both the cast and the warning using a truly meaningful runtime check.
6. **If suppression is needed, how is the invariant proven?** Document the contract clearly and limit the suppression scope; add failure tests if needed.
7. **What is the compilation result with -Werror enabled?** Resolve real warnings before enabling a pipeline policy that rejects all warnings.

For public APIs, prefer returning explicit type parameters such as **List<Customer>** or **Collection<? extends Number>** instead of **List**. For boundaries with unknown types, **List<?>** expresses uncertainty as a type-safe constraint.

## 13. Practice exercises

**Exercise 1 — Classify warnings**

Consider:

~~~java
List raw = new ArrayList();
raw.add("A");
List<String> names = raw;
~~~

Predict which positions get **rawtypes**, which get **unchecked call**, and which get **unchecked conversion** when compiling with **-Xlint:rawtypes,unchecked**. Then run javac yourself to compare against the diagnostics.

**Exercise 2 — Find the runtime error**

From **RawRisk.java**, replace **addLegacy(legacy)** with **legacy.add("Binh")**. Predict stdout and explain why there is no longer a ClassCastException even though the call on raw List is still unchecked. This shows that **a warning is an unproven risk**, not proof that every run will fail.

**Exercise 3 — Fix a read-only API**

Replace:

~~~java
static int length(List values) {
    return values.size();
}
~~~

with a signature that does not use raw types while still accepting **List<String>**, **List<Integer>**, and other generic lists. Hint: use **List<?>**. Explain why **List<Object>** is not an equivalent substitute.

**Exercise 4 — Build an adapter**

Suppose a legacy API returns a raw **List** containing externally sent data. Write a method that accepts **List<?>**, verifies each element is a **String**, copies them into a **List<String>**, and throws an exception with a clear message if invalid. Test with **["A", "B"]** and **["A", 7]**.

**Exercise 5 — Observe build policies**

Try in order:

~~~bash
javac -d out UncheckedConversion.java
javac -Xlint:unchecked -d out UncheckedConversion.java
javac -Xlint:rawtypes,unchecked -d out UncheckedConversion.java
javac -Xlint:rawtypes,unchecked -Werror -d out UncheckedConversion.java
~~~

Compare the level of diagnostic detail and the compilation exit code. Do **not** assume the first command staying silent means the code is already type-safe.

## 14. Self-check questions

- How do raw **List** and **List<?>** differ in their ability to call **add**?
- Why is **List<String> → List<Object>** an error, whereas **List<String> → List<?>** is valid?
- Which statement is an unchecked conversion and which statement is an unchecked invocation in **UncheckedConversion.java**?
- Why can the JVM allow an Integer to reside inside an object pointed to by a **List<String>** variable?
- Why does the error only appear when reading the element out into a **String**?
- Why is **@SuppressWarnings("unchecked")** not a type-safe fix?
- When should **validate-and-copy** be chosen instead of casting?
- What is the difference between **-Xlint:rawtypes**, **-Xlint:unchecked**, and **-Werror**?
- Why do unchecked warnings exist in a language that already supports generics?

## 15. References

- **Java Language Specification 21, §4.8 – Raw Types:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8
- **JLS 21, §4.6 – Type Erasure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- **JLS 21, §5.1.9 – Unchecked Conversion:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9
- **JLS 21, §4.12.2 – Heap Pollution:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.2
- **Oracle Java 21, javac command / -Xlint:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java Tutorials, Raw Types:** https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html

**Takeaway:** A **raw type** omits type parameters when using a generic declaration; **unchecked conversion/call/cast** is where the compiler must allow an operation without sufficient information to prove type safety. Warnings signal boundaries where the responsibility for checking has shifted to the programmer. Prefer type arguments, wildcards, and explicit validation; keep raw/unchecked only in legacy compatibility sections that are truly necessary and controlled.