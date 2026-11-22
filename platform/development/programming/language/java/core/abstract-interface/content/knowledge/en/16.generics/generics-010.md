# Raw types, unchecked warnings, and limits on recognizing type parameters at runtime

## 1. Three concepts to distinguish

- A **raw type** is a generic type used without specifying a type argument, for example List instead of List&lt;String&gt;.
- An **unchecked warning** indicates that the compiler cannot fully verify the type safety of an operation.
- **Type erasure** is the implementation mechanism of generics: type arguments help check source code, but do not create a separate runtime class for each type argument.

Example:

~~~java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
String name = names.get(1); // May throw ClassCastException.
~~~

raw points to the same object as names. The line raw.add(42) usually compiles with a warning; when reading element 42 through List&lt;String&gt;, the compiler inserts a cast to String and the cast fails. Therefore, the error can appear where the wrongly typed data is read, far from where the data was added.

## 2. How raw types differ from List<?> and List&lt;Object&gt;

| Declaration | Meaning | Can add String? | Type safety |
| --- | --- | --- | --- |
| List raw | Omits type argument | Yes, usually with a warning | Low |
| List<?> | Unknown element type | Cannot add arbitrary values, except null | Compiler still protects types |
| List&lt;Object&gt; | List with elements of type Object | Yes | Type checking at compile time |

Use List<?> when you only need to read/print elements regardless of type. List&lt;String&gt; is not a subtype of List&lt;Object&gt; because generics are invariant. Raw types mainly exist for compatibility with legacy Java libraries; in new code, prefer complete type arguments or an appropriate wildcard.

## 3. Runnable example: warnings and error when reading

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        List raw = names;
        raw.add(42);

        System.out.println("first=" + names.get(0));
        try {
            String second = names.get(1);
            System.out.println("second=" + second);
        } catch (ClassCastException ex) {
            System.out.println("read failed=" + ex.getClass().getSimpleName());
        }

        List<Integer> numbers = new ArrayList<>();
        System.out.println("same runtime class="
                + (names.getClass() == numbers.getClass()));
        System.out.println("instanceof List<?>=" + (names instanceof List<?>));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -Xlint:rawtypes,unchecked RawTypeDemo.java
java RawTypeDemo
~~~

Stdout output:

~~~text
first=An
read failed=ClassCastException
same runtime class=true
instanceof List<?>=true
~~~

When compiling, javac emits warnings about raw types and unchecked invocations on the lines declaring/calling through raw. Specific line numbers depend on the source code location. Two ArrayLists with different type arguments still have the same runtime class; instanceof List<?> only confirms that the object is a List, and does not prove that the list contains String.

## 4. Type erasure and reifiable types

For an unbounded type parameter, the erasure is typically Object; for T extends Number, the erasure is Number. List&lt;String&gt; and List&lt;Integer&gt; both have the runtime class List/ArrayList, not two separate classes.

Because the runtime does not retain type arguments as separate types that can be checked directly, the following expressions are invalid:

~~~java
// Invalid:
if (value instanceof List<String>) { }
Class<?> type = List<String>.class;
List<String>[] values = new List<String>[10];
~~~

You can check **instanceof List<?>** and then validate each element if the application needs to be sure the data is String. Reflection can read generic metadata of field/method declarations if the class file stores that metadata; this does not mean each ArrayList object retains its actual type argument.

If the application needs type information at runtime, pass an explicit Class&lt;T&gt;, schema, or validator. Do not assume that generic type arguments always exist on each object.

## 5. How to handle warnings

1. Change raw types to parameterized types such as List&lt;String&gt; if the element type is known.
2. Use List<?> if you only need to read without depending on the element type.
3. Check the data source before an unchecked conversion/cast; if necessary, validate each element.
4. If you must integrate with a legacy API, isolate raw types at the compatibility boundary and convert data to safe types as early as possible.
5. Only use @SuppressWarnings("unchecked") when there is evidence for the type assumption, and restrict the annotation to the smallest scope. The annotation only suppresses the warning; it does not add a runtime check.

Raw types and unchecked casts can break compile-time guarantees, while type erasure explains why errors sometimes appear only when reading. Do not use suppression to hide an unverified type assumption.

## 6. Self-check

- How does a raw type differ from List&lt;Object&gt;? A raw type omits the type argument; List&lt;Object&gt; is still checked by the compiler.
- Why can't List&lt;String&gt; be verified with instanceof? The runtime does not check specific type arguments.
- Does an unchecked warning mean the program is definitely broken? No; it means the compiler cannot guarantee type safety.
- Why can an error appear at get() instead of add()? The cast to the declared type inserted at the read site can fail.
- When you need to verify data at runtime, what should you do? Check each element or use an explicit schema/type token.

Official references: JLS Java SE 17 §4.6 Type Erasure, §4.7 Reifiable Types, §4.8 Raw Types, §5.1.9 Unchecked Conversion, and §5.5.2 Checked and Unchecked Casts.
