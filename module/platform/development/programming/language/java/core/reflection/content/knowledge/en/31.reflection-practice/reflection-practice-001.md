# Practice: Building a Stable-Order Class Structure Printer with Java Reflection

## 1. Problem Statement and Completion Criteria

Write a Java 17+ program that accepts a `Class<?>` object and outputs the class structure in a **deterministic and repeatable** order, sufficient for reading, diffing, or saving as structural documentation. The program will print:

1. The full name and modifiers of the class.
2. The direct superclass (if any).
3. The list of directly declared interfaces, sorted by name.
4. Directly declared fields: modifiers, type, and name; sorted by an explicit key.
5. Constructors declared in the class: modifiers and parameter type list; sorted by signature.
6. Directly declared methods: modifiers, return type, name, parameter type list; sorted by signature and tie-breaking keys when needed.

**Core point:** According to the Java Reflection API, **the order of elements in the arrays returned by `getDeclaredFields()`, `getDeclaredConstructors()`, and `getDeclaredMethods()` is not guaranteed**. Therefore, you must not simply iterate and print the raw array order and call it "stable". You need to **sort the data before printing** and explicitly specify the sorting keys.

A stable result here means: given the same class structure, the same display rules, and the same metadata visible to Reflection, the program produces the exact same output string, regardless of the element order in Reflection arrays. This is not a promise that bytecode produced by different compilers, JDK versions, or instrumentation mechanisms will always yield the **same metadata structure**; synthetic/bridge elements can vary across compilation processes.

## 2. Choosing the Scope: "declared" vs. "inherited"

There are two groups of Reflection APIs that are commonly confused:

| Information | Chosen API | Scope |
|---|---|---|
| Fields in the current class itself | `getDeclaredFields()` | Includes public, protected, package-private, private; does not automatically fetch inherited fields |
| Visible public fields | `getFields()` | May include inherited public fields |
| Methods in the current class itself | `getDeclaredMethods()` | Does not automatically fetch inherited methods; may include bridge/synthetic methods |
| Visible public methods | `getMethods()` | Includes inherited public methods, e.g., from superclasses/interfaces |
| Constructors of the class | `getDeclaredConstructors()` | Includes declared public and non-public constructors |
| Public constructors | `getConstructors()` | Only public constructors; constructors are not inherited |
| Direct superclass | `getSuperclass()` | May be `null` for `Object`, interfaces, primitives, `void` |
| Direct interfaces | `getInterfaces()` | Interfaces directly declared by the class; does not automatically mix in indirectly inherited interfaces |

**Design decision for this exercise:** Use the `getDeclared...` family to print a structural slice **owned by the class**, and print the superclass and interfaces separately. This avoids making an inherited method appear as if it were directly declared by the current class. Real-world tools may add a "public API including inherited" mode, but must define its scope and override-handling rules separately; **do not mix the two modes in a single printout**.

In the sample program, `Sample` extends `Base` and implements `Runnable, AutoCloseable`. The `run()` and `close()` methods are directly declared in `Sample`, so they appear in the `METHODS` section. Methods inherited from `Object` such as `wait` and `hashCode` are not included in the `getDeclaredMethods()` list.

## 3. Designing Sort Keys for Each Group

A key must capture all necessary distinctions and be built from data with a stable ordering:

| Group | Primary and secondary keys in this exercise |
|---|---|
| Interfaces | Display type name normalized via `typeName`, lexicographical order |
| Fields | Field name → field type → modifiers |
| Constructors | Parameter type list → modifiers |
| Methods | Method name → parameter type list → return type → modifiers → `isBridge` → `isSynthetic` |

Example of overloaded methods:

~~~text
describe(int)
describe(java.lang.String)
~~~

If you only sort by method name, two elements named `describe` may still keep their relative order from the initial Reflection array; they could swap places. Therefore, **overloads require adding the parameter type list to the sort key**. The return type should also have its own key: the JVM may contain bridge methods or methods with different bytecode signatures despite sharing the same name and parameter list.

**Do not use `Method.toString()` or `Class.toString()` as the sole sort key** when designing tools: the display string is not a "sort key" contract guaranteed by the API; it is better to choose the exact attributes you want to compare. This exercise builds the parameter string from `getParameterTypes()` in declared parameter order, then uses an explicit comparator.

**Order at the metadata layer is not "source order".** Reflection does not guarantee that fields/methods preserve the order written in the Java file, so the printer does not promise to reconstruct the source code verbatim. The comparators here intentionally establish a *new* and explainable order.

### Normalizing Type Names

`Class.getSimpleName()` is too short when multiple `User` types exist in different packages. `Class.getName()` uses binary notation with `$` for nested types, e.g., `StableClassPrinter$Sample`. `Class.getCanonicalName()` is more readable for ordinary nested classes, e.g., `StableClassPrinter.Sample`, but may return `null` for local/anonymous classes and certain other types.

Helper used in this exercise:

~~~java
private static String typeName(Class<?> type) {
    String canonical = type.getCanonicalName();
    return canonical != null ? canonical : type.getTypeName();
}
~~~

This is an **excerpt located inside the `StableClassPrinter` class** in Section 4. `getTypeName()` provides a fallback when no canonical name exists, such as for anonymous classes. Array and primitive types are also rendered meaningfully by the Java API, such as `int[]` and `java.lang.String[]`. Choose a single rule for **both sort keys and text output** to avoid having one representation when sorting and a different one when printing.

## 4. Complete, Runnable Java 17+ Program

Save the exact content below to a file named **`StableClassPrinter.java`**. The program defines the sample class `Sample`, sorts all lists, and prints the result. The code requires no dependencies outside the JDK.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class StableClassPrinter {
    public static class Base {}

    public static final class Sample extends Base
            implements Runnable, AutoCloseable {
        public String name;
        private final int id;

        public Sample(int id) {
            this.id = id;
        }

        public Sample(String name, int id) {
            this.name = name;
            this.id = id;
        }

        public String describe(String text) {
            return text;
        }

        public String describe(int number) {
            return Integer.toString(number);
        }

        @Override
        public void run() {}

        @Override
        public void close() {}
    }

    private static String typeName(Class<?> type) {
        String canonical = type.getCanonicalName();
        return canonical != null ? canonical : type.getTypeName();
    }

    private static String parameterTypes(Class<?>[] types) {
        return Arrays.stream(types)
                .map(StableClassPrinter::typeName)
                .collect(Collectors.joining(", "));
    }

    private static String modifiers(int value) {
        String text = Modifier.toString(value);
        return text.isEmpty() ? "" : text + " ";
    }

    public static String describe(Class<?> type) {
        StringBuilder result = new StringBuilder();
        result.append("CLASS ")
                .append(modifiers(type.getModifiers()))
                .append(typeName(type)).append('\n');

        Class<?> parent = type.getSuperclass();
        result.append("SUPER ")
                .append(parent == null ? "<none>" : typeName(parent))
                .append('\n');

        String interfaces = Arrays.stream(type.getInterfaces())
                .map(StableClassPrinter::typeName)
                .sorted()
                .collect(Collectors.joining(", "));
        result.append("INTERFACES ")
                .append(interfaces.isEmpty() ? "<none>" : interfaces)
                .append('\n');

        Field[] fields = type.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName)
                .thenComparing(f -> typeName(f.getType()))
                .thenComparingInt(Field::getModifiers));
        result.append("FIELDS\n");
        for (Field field : fields) {
            result.append("  ")
                    .append(modifiers(field.getModifiers()))
                    .append(typeName(field.getType())).append(' ')
                    .append(field.getName()).append('\n');
        }

        Constructor<?>[] constructors = type.getDeclaredConstructors();
        Arrays.sort(constructors,
                Comparator.comparing((Constructor<?> c) ->
                        parameterTypes(c.getParameterTypes()))
                        .thenComparingInt(Constructor::getModifiers));
        result.append("CONSTRUCTORS\n");
        for (Constructor<?> constructor : constructors) {
            result.append("  ")
                    .append(modifiers(constructor.getModifiers()))
                    .append(typeName(type)).append('(')
                    .append(parameterTypes(constructor.getParameterTypes()))
                    .append(")\n");
        }

        Method[] methods = type.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName)
                .thenComparing(m -> parameterTypes(m.getParameterTypes()))
                .thenComparing(m -> typeName(m.getReturnType()))
                .thenComparingInt(Method::getModifiers)
                .thenComparing(Method::isBridge)
                .thenComparing(Method::isSynthetic));
        result.append("METHODS\n");
        for (Method method : methods) {
            result.append("  ")
                    .append(modifiers(method.getModifiers()))
                    .append(typeName(method.getReturnType())).append(' ')
                    .append(method.getName()).append('(')
                    .append(parameterTypes(method.getParameterTypes()))
                    .append(')');
            if (method.isBridge()) {
                result.append(" [bridge]");
            }
            if (method.isSynthetic()) {
                result.append(" [synthetic]");
            }
            result.append('\n');
        }
        return result.toString();
    }

    public static void main(String[] args) {
        System.out.print(describe(Sample.class));
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac --release 17 -encoding UTF-8 StableClassPrinter.java
java StableClassPrinter
~~~

**Exact stdout verified by compiling and running the program:**

~~~text
CLASS public static final StableClassPrinter.Sample
SUPER StableClassPrinter.Base
INTERFACES java.lang.AutoCloseable, java.lang.Runnable
FIELDS
  private final int id
  public java.lang.String name
CONSTRUCTORS
  public StableClassPrinter.Sample(int)
  public StableClassPrinter.Sample(java.lang.String, int)
METHODS
  public void close()
  public java.lang.String describe(int)
  public java.lang.String describe(java.lang.String)
  public void run()
~~~

Observations:

- `AutoCloseable` appears before `Runnable` because interface names are sorted; the order written after `implements` is not used as the display order.
- `id` appears before `name` because fields are sorted by name; the field position in source does not dictate the output.
- The constructor taking `int` appears before the constructor taking `String, int` because constructors are sorted by the parameter type string.
- The method `describe(int)` appears before `describe(String)` because the parameter key `int` comes before `java.lang.String`.
- `close()`, `describe(...)`, and `run()` appear in alphabetical order of method names. The program does not print methods inherited from `Object`.
- `Modifier.toString(...)` converts the modifier bitmask into a string following Java rules, such as `private final` or `public static final`. When there are no modifiers, the `modifiers` helper returns an empty string to avoid adding an extra space.

In the main example, every element has keys sufficient to produce a deterministic order. For more complex types that may have metadata with colliding keys, see Section 7 on completing a canonical fingerprint and handling special metadata.

## 5. Breakdown of Each Part of the Printer

### 5.1. Class header, superclass, and interfaces

~~~java
result.append("CLASS ")
        .append(modifiers(type.getModifiers()))
        .append(typeName(type)).append('\n');
Class<?> parent = type.getSuperclass();
~~~

`getModifiers()` returns a bitmask; `Modifier.toString` formats standard modifiers. `getSuperclass()` returns the direct superclass or `null` in cases where no corresponding superclass exists. Rather than assuming every `Class<?>` describes an ordinary class, the code displays `<none>` when there is no superclass.

`getInterfaces()` returns an array; Java does not guarantee it is the optimal order for producing canonical output. Therefore, use:

~~~java
Arrays.stream(type.getInterfaces())
        .map(StableClassPrinter::typeName)
        .sorted()
        .collect(Collectors.joining(", "));
~~~

This is an **excerpt** from the complete program. `sorted()` orders the name strings using natural ordering (`String` comparison), independent of the operating system's default locale. Tools may choose a custom comparator for export requirements, provided it is consistent and documented.

### 5.2. Fields

~~~java
Field[] fields = type.getDeclaredFields();
Arrays.sort(fields, Comparator.comparing(Field::getName)
        .thenComparing(f -> typeName(f.getType()))
        .thenComparingInt(Field::getModifiers));
~~~

This snippet is extracted from the `describe` method. The comparator ensures fields with different names are always ordered by name. The secondary keys clarify the rule if metadata entries share the same name but differ by type or modifiers. When printing, calling `field.getType()` returns the `Class<?>` for the declared type, **without accessing the field's value**. `setAccessible(true)` is not needed because only metadata is read.

`getDeclaredFields()` may contain synthetic fields generated by the compiler. If the goal is a **complete Reflection-level printout**, keep and mark synthetic fields so their presence is visible. If the goal is to describe the user-written API, you may skip `field.isSynthetic()`, but you must state clearly that it is a **filtered projection** rather than all declared fields. The sample code keeps all fields and does not create special synthetic fields in the example.

### 5.3. Constructors

Constructors have no return type and are not inherited. `Constructor.getParameterTypes()` returns the parameter type list in declared order, while the returned array of constructors must be sorted:

~~~java
Arrays.sort(constructors,
        Comparator.comparing((Constructor<?> c) ->
                parameterTypes(c.getParameterTypes()))
                .thenComparingInt(Constructor::getModifiers));
~~~

This snippet is extracted from the program. `getDeclaredConstructors()` may include private/protected/package-private constructors. **Reading metadata** does not mean **being allowed to invoke the constructor**; if invoking via `newInstance(...)`, you must handle accessibility and exceptions thrown by the target code.

For non-static inner classes, the compiler may add a receiver/enclosing instance parameter to the bytecode constructor; for enums or certain compiler-generated types, the Reflection signature may also differ from the signature shown in source. This printer intentionally displays the parameter types actually reported by Reflection, without trying to reconstruct the Java source constructor verbatim.

### 5.4. Methods and overloads

`Method.getName()` alone is not sufficient as a sort key. The comparator uses:

~~~java
Comparator.comparing(Method::getName)
        .thenComparing(m -> parameterTypes(m.getParameterTypes()))
        .thenComparing(m -> typeName(m.getReturnType()))
        .thenComparingInt(Method::getModifiers)
        .thenComparing(Method::isBridge)
        .thenComparing(Method::isSynthetic)
~~~

This is an **expression snippet** inside `Arrays.sort` in the example. The parameter list forms the signature for overloads. The return type separates variants that the compiler may generate (such as bridge methods). `isBridge()` and `isSynthetic()` also serve to attach labels in the output so tools do not silently omit compiler-generated methods.

These flags **do not mean that bridge/synthetic methods must always be removed from the printout**. Choosing to keep or filter them depends on the purpose. If keeping them, print clear labels; if filtering, do so before sorting and document the reason. For user-written API documentation, many tools filter out synthetic/bridge methods; for bytecode analysis or runtime dispatch diagnostics, keeping them can be important.

## 6. Verifying Stability with Tests, Not Just One-Off Visual Inspection

A printout that "looks sorted" is not sufficient proof. Test **multiple runs with the same input** and test the sort keys.

### Test 1: The function output is a side-effect-free string

The `describe(Class<?>)` method returns a `String`. Thus tests can compare the output directly without capturing `System.out`:

~~~java
String first = StableClassPrinter.describe(
        StableClassPrinter.Sample.class);
String second = StableClassPrinter.describe(
        StableClassPrinter.Sample.class);

if (!first.equals(second)) {
    throw new AssertionError("Unstable class description");
}
~~~

This is an **illustrative test snippet** for the same project, not a standalone Java file. Calling it twice and comparing strings helps catch internal discrepancies within a single process; however, if the JVM happens to return arrays in the same order, the test could still pass even if you forgot to sort. Therefore, you must inspect the comparators and test with data containing multiple overloaded methods / multiple fields like `Sample`.

### Test 2: Snapshot / golden output matching

Run the program, save the output to `expected.txt`, and then compare byte-for-byte or as a Unicode string against the current result. The snapshot file must be updated **intentionally** when the display contract changes. To produce a UTF-8 baseline file in a shell supporting redirection:

~~~bash
java StableClassPrinter > actual.txt
~~~

Then use your project's diff/test tool to compare `actual.txt` with `expected.txt`. Note that encoding and line endings (LF/CRLF) differ across operating systems; if the snapshot needs to be cross-platform, you can normalize newlines before comparing, **without changing the sort rules**.

### Test 3: Adding data to exercise the comparators

- Swap the declaration order of `name` and `id` in the source code, then recompile. The order of fields in stdout must still be based on name.
- Swap the positions of the two `describe` methods in source. The method order must still follow name + parameter types.
- Change `implements Runnable, AutoCloseable` to `implements AutoCloseable, Runnable`. The output order must still keep `java.lang.AutoCloseable` before `java.lang.Runnable`.
- Add an overload `describe(long)`. The comparator must place it in the proper lexicographical position by parameter type name, independent of code order.

Do not claim that every change will produce identical bytecode: testing here verifies the **display ordering rules**, not that the compiler emits the same raw metadata order.

## 7. Limitations to State Before Production Use

### 7.1. Reflection metadata is not source syntax

The printer does not reconstruct generics/annotations/`throws` exactly like Java source. `Field.getType()` and `Method.getReturnType()` return erased types in generic scenarios; to preserve generic information stored in the classfile, see `Field.getGenericType()`, `Method.getGenericReturnType()`, and `Executable.getGenericParameterTypes()`. These APIs return `Type`, not always `Class<?>`, and require dedicated formatters for `ParameterizedType`, `TypeVariable`, `GenericArrayType`, and `WildcardType`. Sorting and serialization of those type expressions must be specified if the goal is a relatively complete API signature.

The program does not display class/member annotations, exception types (`throws`), generic type parameters, record components, nested classes, enum constants as a separate section, or the inherited public API. To extend it, add **each section separately** with an appropriate sort strategy; do not promise that the output above represents the entire Java class file model.

### 7.2. Not every `Class<?>` is a normal class

For `int.class`, `void.class`, array types, interfaces, annotation types, enums, records, local/anonymous classes, hidden classes, or dynamic proxy classes, metadata may differ from "ordinary class" assumptions. For example, `getCanonicalName()` may return `null` and `getDeclaredConstructors()` may return an empty array.

The `describe(Class<?>)` code in this exercise has fallbacks for type names and superclasses, avoiding certain NPEs; however, the current output format writes a generic `CLASS` label and **does not fully distinguish categories** (interface/enum/record/annotation). When building a production tool, check `isInterface()`, `isAnnotation()`, `isEnum()`, `isRecord()`, `isArray()`, `isPrimitive()`, `isHidden()` and format each kind clearly.

### 7.3. Some metadata may be generated by the compiler or instrumentation

Bridge/synthetic methods, helper fields, hidden classes, and bytecode instrumentation can change metadata across compilers or build setups. Therefore, stable output is a function of **actual class metadata + sort rules**, not a snapshot guaranteed to be identical across every JDK/build.

An advanced concern: a good comparator must handle cases where **keys are completely equal yet elements still differ in an aspect you want to print**, such as when adding annotations, generic signatures, `throws`, or synthetic information. In those cases, add tie-breakers based on the exact (normalized) fields to be printed. If two entries are identical across all exported content, swapping them will not change the output string. Do not use `hashCode()` of a reflection object as a tie-breaker because it is not a meaningful, stable canonical key.

### 7.4. Access rights and security

The `getDeclared...` methods in the example only **list metadata**; they do not read private field values and do not invoke private methods. The printer therefore **does not use `setAccessible(true)`**. However, under a security policy or special environment, metadata queries may still be restricted. If expanded into a tool that "prints an object's field values", that is a different task requiring privacy policies, redaction, access control, and reference-cycle handling. **Never log passwords, tokens, or sensitive data simply because Reflection can see the field.**

### 7.5. Different definitions of "stable"

You can sort by:

- Field/method name + signature as in this exercise: readable, stable, and suitable for documentation.
- JVM descriptor signature: suitable for bytecode analysis, though less human-friendly.
- Grouping by access modifier first, then name/signature: suitable for user-facing API documentation.
- Full canonical name with versioned normalization: needed when used as a hash or interchange data between toolchains.

What matters is not having only one "correct" comparator, but **publishing the contract, sorting every collection without a guaranteed order, testing with multiple overloads, and keeping the contract consistent**.

## 8. Common Mistakes

| Mistake | Why it is unstable | Fix |
|---|---|---|
| Printing the `getDeclaredMethods()` array directly | Javadoc does not guarantee order | `Arrays.sort` or `stream.sorted` with a deterministic comparator |
| Sorting only by `Method::getName` | Does not distinguish overloads | Add parameter type signature and return type |
| Using `getMethods()` while labeling "declared methods" | Includes inherited public methods | Choose `getDeclaredMethods()` or change the scope label |
| Printing `getInterfaces()` in its given order | Canonical output requires a defined sort | Map to type names and sort |
| Calling `getSimpleName()` for everything | Can collide across packages, empty for anonymous types | Prefer canonical name with fallback |
| Treating Reflection as a source parser | Lacks source order, comments, and some generic details | Use an AST/compiler model if source information is needed |
| Dropping all `synthetic`/`bridge` items without explanation | Omits part of the runtime structure | Provide a documented filter mode; keep/label by default for diagnostics |
| Using `setAccessible(true)` just to print signatures | Unnecessary, increases risk, and may be blocked by JPMS | Only read metadata via Reflection |
| Including object identity/hash in output | Not a stable structural property across runs | Print type names, signatures, flags |
| Visually checking stdout once | Misses missing tie-breakers | Snapshot test / compare with overloads and source reordering |

## 9. Practice Extensions

1. Add a `private boolean enabled` field and a `protected int score(double multiplier)` method. Determine their exact positions in the output before running.
2. Write a `describe(Class<?> type, boolean includeInherited)` method. When `includeInherited=true`, use the appropriate API group and define how overrides are handled. Do not label it as the same scope as `getDeclaredMethods()`.
3. Add the `java.io.Serializable` interface to `Sample`. Verify that the interfaces list remains sorted even when the order in `implements` is reversed.
4. Create a generic base class so the compiler generates a bridge method. Observe `isBridge()`/`isSynthetic()` and adjust printing if a "source-like view" mode is desired.
5. Add a `throws` column using `getExceptionTypes()`. Choose an exception list ordering suited to a "signature view" goal without arbitrarily altering the meaning of method parameter order.
6. Add a `RECORD_COMPONENTS` section using `Class.getRecordComponents()` for `record` types; explicitly decide whether output uses **declared component order** or a **tool-sorted canonical order**.
7. Write a unit test comparing `describe(Sample.class)` against golden text and repeat it 100 times; then swap method declaration order in source to prove the output does not depend on the order returned by Reflection.
8. Create a CLI wrapper taking a class name via `args[0]`, calling `Class.forName(...)`, and printing its structure; add `ClassNotFoundException` handling along with a policy accepting only trusted class names. Be cautious because loading and initializing a class can cause side effects.

**Key takeaway:** Reflection provides metadata, **not a default canonical order** for fields, constructors, and methods. To print a stable class structure, clearly decide the scope (`declared` vs. `inherited`), define a comparator with sufficient keys for each collection, normalize type names, avoid relying on object identity, and test with overloads/bridge/synthetic elements. When source-level representation is needed instead of runtime structure, consider a compiler model or AST rather than trying to reverse-engineer source from Reflection.

### References (Java 17)

- [`Class.getDeclaredFields`, `getDeclaredMethods`, and `getDeclaredConstructors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [`Method` and bridge/synthetic metadata](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [`Modifier.toString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html#toString(int))
- [`Comparator`, `thenComparing`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
