# Reading compiler-added methods and fields without relying on internal names

## 1. Reflection sees the compiled class

An enum's source code can be very short, yet the compiled class contains additional members to implement Java rules and support the JVM. Therefore, the list returned by `getDeclaredFields()` or `getDeclaredMethods()` is not a verbatim copy of what the programmer typed in the source file.

When building a tool to read enum structure, distinguish three groups:

1. **Explicitly declared members:** fields and methods declared by the code author.
2. **Language-implicitly declared members:** such as fields representing enum constants and the two methods `values()` and `valueOf(String)`.
3. **Compiler-generated helper members:** which may include fields storing internal data, helper methods, and `bridge method`s.

Not every compiler-added member is identified by `isSynthetic()`. In particular, the implicit enum APIs have a distinct place in the language contract.

The goal of this lesson is to read and classify metadata accurately. Invoking methods, reading field values, or modifying data inside an enum are separate operations.

## 2. What is guaranteed by Java, and what belongs to the compilation strategy?

For an enum `E`, Java specifies:

- Each enum constant corresponds to a `public static final` field bearing the constant's name and having type `E`.
- There is a method `public static E[] values()`.
- There is a method `public static E valueOf(String name)`.

These are members with a language contract. Using the names `values` or `valueOf` with the exact parameters to find the corresponding API is not relying on an arbitrary internal name.

Conversely, how the compiler stores the constants array or splits initialization steps may vary. Names such as `$VALUES` or `$values` may appear when inspecting a compiler's output, yet they are not public APIs that applications should look up to obtain the list of constants.

Do not write algorithms like "find a field with that exact internal name and read it". Also do not infer roles solely from name shape such as starting with `$`, being uppercase, or containing the word `values`.

| Need | Appropriate basis |
| --- | --- |
| Identify fields representing enum constants | `Field.isEnumConstant()` |
| Recognize fields/methods marked synthetic | `isSynthetic()` on the member |
| Recognize bridge methods | `Method.isBridge()` |
| Identify implicit enum APIs | Declaring class, API name, parameters, return type, and modifiers |
| Retrieve constant objects in declaration order | `Class.getEnumConstants()` |
| Find the entire implementation for bytecode diagnostics | Keep metadata and record roles explicitly rather than dropping by default |

Metadata flags answer technical questions. A tool's display policy must decide which groups are included in documentation or inspection screens.

## 3. Example: classifying fields and methods of an enum

Save as `EnumCompilerMembersDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class EnumCompilerMembersDemo {
    enum TaskState {
        WAITING(10),
        RUNNING(20);

        private final int code;
        public static final TaskState DEFAULT = WAITING;
        public static final String VERSION = "v1";

        TaskState(int code) {
            this.code = code;
        }

        public int code() {
            return code;
        }
    }

    private static String methodLabel(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
        return method.getName() + "(" + parameters + ")->"
                + method.getReturnType().getSimpleName();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<TaskState> type = TaskState.class;

        String constantFields = Arrays.stream(type.getDeclaredFields())
                .filter(Field::isEnumConstant)
                .map(Field::getName)
                .sorted()
                .collect(Collectors.joining(","));

        String otherFields = Arrays.stream(type.getDeclaredFields())
                .filter(field -> !field.isEnumConstant())
                .filter(field -> !field.isSynthetic())
                .map(Field::getName)
                .sorted()
                .collect(Collectors.joining(","));

        String methods = Arrays.stream(type.getDeclaredMethods())
                .filter(method -> !method.isSynthetic())
                .filter(method -> !method.isBridge())
                .map(EnumCompilerMembersDemo::methodLabel)
                .sorted()
                .collect(Collectors.joining("; "));

        System.out.println("constantFields=" + constantFields);
        System.out.println("otherFields=" + otherFields);
        System.out.println("methods=" + methods);
        System.out.println("DEFAULT.enumConstant="
                + type.getDeclaredField("DEFAULT").isEnumConstant());
        System.out.println("values.synthetic="
                + type.getDeclaredMethod("values").isSynthetic());
        System.out.println("valueOf.synthetic="
                + type.getDeclaredMethod("valueOf", String.class)
                      .isSynthetic());
        System.out.println("declarationOrder="
                + Arrays.toString(type.getEnumConstants()));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 EnumCompilerMembersDemo.java
java EnumCompilerMembersDemo
~~~

Output with JDK 17 `javac`:

~~~text
constantFields=RUNNING,WAITING
otherFields=DEFAULT,VERSION,code
methods=code()->int; valueOf(String)->TaskState; values()->TaskState[]
DEFAULT.enumConstant=false
values.synthetic=false
valueOf.synthetic=false
declarationOrder=[WAITING, RUNNING]
~~~

The example proactively sorts field names and method labels so printed output is stable. Do not rely on the array order of metadata returned by Reflection.

You must distinguish **sorted display order** from **constant order in the declaration**. The field list is sorted by name so `RUNNING` appears before `WAITING`; `getEnumConstants()` still keeps `WAITING` before `RUNNING`.

The `DEFAULT` field is an author-declared field, even though it is also `public static final` and has type `TaskState`. `isEnumConstant()` still returns `false`. Thus, checking only the field type and modifiers is not enough to identify enum constants.

The two methods `values()` and `valueOf(String)` appear even though the author did not write their declarations. In the output observed here, they do not carry the synthetic flag. Filtering out all synthetic members still retains these two APIs.

The program does not print the names or counts of internal helper members. When switching compilers or compilation strategies, helper details can change without altering the purpose of the classification.

## 4. isSynthetic does not mean "not author-written"

`Field.isSynthetic()` and `Method.isSynthetic()` read a member's synthetic marker. This marker is useful for recognizing technical scaffolding, yet does not fully reconstruct source code authorship history.

There are two directions of inference to avoid:

- A compiler-added member may correspond to an implicit Java declaration, like the enum APIs just seen.
- A synthetic member can still be important to a tool analyzing compiled classes, even if it is unsuitable for display as a business API.

Therefore, name policies accurately. The filter `!method.isSynthetic()` means "exclude methods marked synthetic", not "keep only methods explicitly written in source".

If you need to determine precisely which parts were written by an author in a source file, Reflection metadata alone is not a complete source map. Reading the source or additional metadata may be needed for that goal. Do not label every non-synthetic method "user-written" without accounting for implicit members.

Similarly, do not hide every `static` field or every array-typed field by default to exclude helper data: an enum can certainly declare application fields of those forms.

## 5. If you want to hide implicit APIs, check the exact contract

One documentation tool may want to keep standard enum APIs; another may only want to list author-defined extensions. That is a presentation decision that must be separated from the metadata-reading mechanism.

If policy requires hiding `values()` and `valueOf(String)`, do not exclude every method just because its name is `values` or `valueOf`. An enum can have a valid overload such as `valueOf(int)` written by the author.

Save as `EnumApiFilterDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class EnumApiFilterDemo {
    enum Tier {
        BASIC, PREMIUM;

        public static Tier valueOf(int code) {
            return switch (code) {
                case 1 -> BASIC;
                case 2 -> PREMIUM;
                default -> throw new IllegalArgumentException("Unknown code");
            };
        }
    }

    static boolean isImplicitEnumApi(Class<?> enumType, Method method) {
        if (!enumType.isEnum()
                || method.getDeclaringClass() != enumType) {
            return false;
        }

        int modifiers = method.getModifiers();
        if (!Modifier.isPublic(modifiers)
                || !Modifier.isStatic(modifiers)) {
            return false;
        }

        if (method.getName().equals("values")) {
            return method.getParameterCount() == 0
                    && method.getReturnType().isArray()
                    && method.getReturnType().getComponentType() == enumType;
        }

        if (method.getName().equals("valueOf")) {
            return method.getParameterCount() == 1
                    && method.getParameterTypes()[0] == String.class
                    && method.getReturnType() == enumType;
        }

        return false;
    }

    private static String methodLabel(Method method) {
        return method.getName() + "("
                + Arrays.stream(method.getParameterTypes())
                      .map(Class::getSimpleName)
                      .collect(Collectors.joining(","))
                + ")";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Tier> type = Tier.class;

        Method values = type.getDeclaredMethod("values");
        Method textLookup = type.getDeclaredMethod("valueOf", String.class);
        Method numericLookup = type.getDeclaredMethod("valueOf", int.class);

        System.out.println("values(): implicit="
                + isImplicitEnumApi(type, values));
        System.out.println("valueOf(String): implicit="
                + isImplicitEnumApi(type, textLookup));
        System.out.println("valueOf(int): implicit="
                + isImplicitEnumApi(type, numericLookup));

        String kept = Arrays.stream(type.getDeclaredMethods())
                .filter(method -> !method.isSynthetic())
                .filter(method -> !method.isBridge())
                .filter(method -> !isImplicitEnumApi(type, method))
                .map(EnumApiFilterDemo::methodLabel)
                .sorted()
                .collect(Collectors.joining("; "));
        System.out.println("kept=" + kept);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 EnumApiFilterDemo.java
java EnumApiFilterDemo
~~~

Output:

~~~text
values(): implicit=true
valueOf(String): implicit=true
valueOf(int): implicit=false
kept=valueOf(int)
~~~

The detector uses `Class` objects to check the return type and parameter types, rather than comparing shortened type name strings. Simple names in `methodLabel` serve only the example's printout.

Filtering by this contract applies to a valid Java enum class. It is not a detector for every member that every bytecode generator might produce.

The modifier and declaring-class checks also prevent confusing a method with the same name but a different role. The hiding policy removes only the two identified APIs; the `valueOf(int)` overload is still kept.

## 6. Bridge methods: two methods can still be seen with the same name and parameters

An enum can also implement a generic interface. When bridging an erased contract to an implementation with a more specific return type, the compiler may generate a bridge method.

This is not a new enum API. It is scaffolding so calls through the interface type still reach the right implementation.

Save as `EnumBridgeMetadataDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class EnumBridgeMetadataDemo {
    interface CodeSupplier<T> {
        T code();
    }

    enum Signal implements CodeSupplier<String> {
        ON;

        @Override
        public String code() {
            return "on";
        }
    }

    public static void main(String[] args) {
        Arrays.stream(Signal.class.getDeclaredMethods())
                .filter(method -> method.getName().equals("code"))
                .sorted(Comparator.comparing(
                        method -> method.getReturnType().getName()))
                .forEach(method -> System.out.println(
                        method.getName() + " -> "
                        + method.getReturnType().getSimpleName()
                        + " synthetic=" + method.isSynthetic()
                        + " bridge=" + method.isBridge()));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 EnumBridgeMetadataDemo.java
java EnumBridgeMetadataDemo
~~~

Output with JDK 17 `javac`:

~~~text
code -> Object synthetic=true bridge=true
code -> String synthetic=false bridge=false
~~~

The author wrote only one `String code()` method. The method returning `Object` is a bridge generated by the compiler to fulfill the `CodeSupplier<T>` contract after type erasure.

If a documentation tool displays both as two separate business operations, users may see duplicated APIs. A typical documentation policy can exclude bridge methods. A bytecode diagnostic tool should keep them and display the corresponding flags.

Do not merge or exclude methods solely by name. At the Reflection/JVM level, methods with identical names and parameter types yet different return types can be observed, as in this example. When creating metadata keys, keep the declaring class, name, parameters, and return type information appropriate to the tool's goal.

`isBridge()` answers the specific bridge role. `isSynthetic()` answers the broader synthetic marker. A bridge method is a synthetic case; not every synthetic method is a bridge.

## 7. Choose the right reading scope before filtering

`getDeclaredFields()` and `getDeclaredMethods()` retrieve members declared directly in the class being inspected, including non-public members. They do not automatically include inherited members.

This explains why `values()` and `valueOf(String)` appear in the enum's direct metadata, whereas methods like `name()` and `ordinal()` come from the `Enum` base class.

If the goal is the public API including inherited parts, `getMethods()` has a different scope. Determine the scope first, and only then apply synthetic/bridge/enum API policies. Otherwise, a tool can appear "missing" or "extra" methods because it chose the wrong scope from the start.

When starting from an enum constant object with its own body, the constant's runtime class may even be an anonymous subclass. If you want to inspect the shared enum class, normalize with `constant.getDeclaringClass()`; if you want to inspect the constant's own part, use its runtime class.

Do not treat the field/method array order from Reflection as source order. Sort presentation output when stable output is needed; retrieve the constant list via the enum API when the declaration order of constants is needed.

## 8. Observing metadata does not require reading internal data

The examples use names, types, modifiers, and member flags to classify. There is no need to call `setAccessible(true)` or read private fields to know whether a field is an enum constant or synthetic.

If only constant values are needed, use `getEnumConstants()`. If the enum type is known in source, use `values()`. Both keep code free from depending on how the compiler stores helper data.

Reading an internal field does not establish a stable contract for an application. Modifying the backing storage array, if found and accessible, can also break assumptions of the enum or other libraries. Metadata visibility is no reason to mutate that state.

Execution boundaries must also be kept clear: obtaining a `Method` only describes the method; calling `invoke` performs the call. Reading static field values or retrieving constant objects can involve class initialization. A metadata viewer should not speculatively invoke methods just to decide which group a member belongs to.

## 9. Common mistakes and how to check

| Mistake | What to double-check |
| --- | --- |
| Looking up a field with a fixed internal name to get constants | Use the enum API instead of helper data |
| Identifying constants solely by public/static/final and field type | Use `Field.isEnumConstant()`; an alias field can have the same type and modifiers |
| Treating every non-synthetic method as author-written | Account for implicitly declared APIs |
| Excluding every method named `valueOf` | Check parameters, return type, modifiers, and declaring class |
| Displaying a bridge as a second business operation | Decide `isBridge()` policy by purpose |
| Discarding synthetic members on read without leaving a trace | Diagnostic tools may need those very members |
| Comparing metadata snapshots in the order returned by the JVM | Sort keys/labels before comparing |
| Treating the count of internal fields/methods as a guarantee | Check only the necessary contracts; do not hardcode compiler details |
| Calling private value-reading APIs just to classify | Use public metadata and role flags |

A clean organization is: collect metadata, classify roles, then choose a presentation policy. That way, one reader can serve both an API view and a diagnostic mode without guessing roles from member names.

## 10. Self-check

1. Why can the `!method.isSynthetic()` filter still retain `values()` and `valueOf(String)`?
2. Is a `public static final MyEnum DEFAULT` field guaranteed to be an enum constant?
3. If an enum additionally declares `valueOf(int)`, should it be excluded solely because the method name is `valueOf`?
4. In the generic example, why are both `Object code()` and `String code()` seen?
5. To list constants in source order, should you sort fields or use which API?
6. Should the name or count of internal storage fields be hardcoded in a test checking application correctness?

Answers:

1. They are APIs implicitly declared by Java; "compiler-added" cannot be equated with "synthetic".
2. No. Use `Field.isEnumConstant()` to distinguish enum constant fields from regular fields.
3. No. That can be an author-written overload; check the exact contract to filter.
4. The compiler generates a bridge to connect the erased generic contract to the implementation returning `String`.
5. Use `Class.getEnumConstants()`, or `values()` when the concrete type is known.
6. No. Verify required behavior/contracts and avoid depending on helper details that may change.

## Reference documentation

- [JLS 17 — Implicitly declared members of enums](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.3).
- [JLS 17 — Binary form, synthetic, and implicitly declared](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1).
- [Java 17 — Field.isEnumConstant and isSynthetic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#isEnumConstant()).
- [Java 17 — Method.isBridge and isSynthetic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isBridge()).
