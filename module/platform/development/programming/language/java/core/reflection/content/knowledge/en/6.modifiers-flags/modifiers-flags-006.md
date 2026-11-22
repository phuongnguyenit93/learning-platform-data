# `isSynthetic()` and Compiler-Generated Structures in Java Reflection

## 1. What does `synthetic` mean?

When compiling Java, the compiler sometimes has to generate additional classes, fields, methods, or other elements to implement Java semantics properly on the JVM. Some of these elements do not correspond to direct or implicit declarations in source code: they are called **synthetic** and are marked in the class file's data.

Through Reflection, `isSynthetic()` helps distinguish structures marked *synthetic* from ordinary structures. The method returns a `boolean`:

- `true`: the structure is reflected by the class file/JVM as synthetic.
- `false`: there is no corresponding synthetic marker; **this is not synonymous** with "definitely typed manually by the programmer." Java has generated elements that are valid at the language level and are not marked synthetic.

A classic example: to ensure an overriding method continues to be called properly after **type erasure**, `javac` may generate a *bridge method* not written in source code. Conversely, the default constructor provided by the compiler when a class declares no constructor is usually **not synthetic**. Therefore, `isSynthetic()` cannot be used as an absolute detector for everything compiler-generated.

**Important scope:** `isSynthetic()` reflects a **binary/runtime**-level property; it does not inspect source-code text and does not analyze a method's body. A name containing `$` is also not sufficient proof that an element is synthetic.

## 2. Where can `isSynthetic()` be called?

| Reflection element | API | Used to ask |
| --- | --- | --- |
| Type (class/interface) | `Class<?>.isSynthetic()` | Does the type itself have the synthetic modifier? |
| Data field | `Field.isSynthetic()` | Is that field marked synthetic? |
| Method | `Method.isSynthetic()` | Is that method marked synthetic? |
| Constructor | `Constructor<?>.isSynthetic()` | Is that constructor marked synthetic? |
| Parameter described via Reflection | `Parameter.isSynthetic()` | Is the parameter a synthetic element? |

`Field`, `Method`, and `Constructor` all implement the `java.lang.reflect.Member` interface, which provides `isSynthetic()`; `Class` and `Parameter` provide their own methods. For methods, `Method.isBridge()` checks another property: whether the method is a *bridge method*.

To observe elements the compiler may add, use the **declared** APIs:

~~~java
Class<?> type = SomeType.class;
var methods = type.getDeclaredMethods();
var fields = type.getDeclaredFields();
var constructors = type.getDeclaredConstructors();

for (var m : methods) {
    System.out.println(m.getName() + ": " + m.isSynthetic());
}
~~~

This snippet only illustrates how to use Reflection (`SomeType` is a placeholder class name that must be replaced by a real class); it is **not a standalone program**. `getDeclaredMethods()` sees methods declared in the binary of the class itself, including private and synthetic ones if present. `getMethods()` only considers public methods of the type and inherited public methods, so it can miss non-public synthetic methods. Similarly, `getDeclaredFields()` is more useful than `getFields()` when inspecting compiler-generated fields.

## 3. Complete example: bridge method, default constructor, anonymous class

Save the Java 17+ program below as `SyntheticReflectionDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class SyntheticReflectionDemo {
    static class Box<T> {
        T value() {
            return null;
        }
    }

    static class TextBox extends Box<String> {
        @Override
        String value() {
            return "hello";
        }
    }

    static class Outer {
        private int seed = 7;

        class Inner {
            int read() {
                return seed;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Arrays.stream(TextBox.class.getDeclaredMethods())
                .filter(m -> m.getName().equals("value"))
                .sorted(Comparator.comparing(
                        m -> m.getReturnType().getSimpleName()))
                .forEach(m -> System.out.printf(
                        "return=%s, bridge=%s, synthetic=%s%n",
                        m.getReturnType().getSimpleName(),
                        m.isBridge(), m.isSynthetic()));

        System.out.println("default constructor synthetic: "
                + TextBox.class.getDeclaredConstructor().isSynthetic());

        Class<?> anonymous = new Runnable() {
            @Override
            public void run() { }
        }.getClass();

        System.out.println("anonymous: " + anonymous.isAnonymousClass()
                + ", synthetic: " + anonymous.isSynthetic());

        for (Field field : Outer.Inner.class.getDeclaredFields()) {
            if (field.isSynthetic()) {
                System.out.println("synthetic inner field: " + field.getName());
            }
        }
    }
}
~~~

Compile with `javac` and run:

~~~bash
javac --release 17 SyntheticReflectionDemo.java
java SyntheticReflectionDemo
~~~

Observed output with `javac` and a JDK supporting Java 17 or later (the compiler-generated field name is an implementation detail, see below):

~~~text
return=Object, bridge=true, synthetic=true
return=String, bridge=false, synthetic=false
default constructor synthetic: false
anonymous: true, synthetic: false
synthetic inner field: this$0
~~~

### Analyzing the bridge method

`Box<T>.value()` after generic type erasure has a JVM descriptor corresponding to `Object value()`. In `TextBox`, the overriding method written by the programmer is `String value()`. To preserve polymorphic invocation behavior compatible with the erased signature, `javac` also emits a forwarding method roughly equivalent in concept to:

~~~java
// Conceptual description at bytecode level; NOT valid Java source code
// to declare in the same class as String value().
Object value() {
    return value(); // delegates to the method returning String
}
~~~

The illustration above **cannot be pasted as a second method in Java source**: the Java language does not allow two methods with the same name and parameter list differing only in return type. The JVM distinguishes method descriptors including return type, and the compiler can generate a bridge. In the binary, the method returning `Object` carries the `ACC_BRIDGE` and `ACC_SYNTHETIC` flags. Therefore Reflection reports `isBridge() == true` and `isSynthetic() == true` for the forwarding method; the `String value()` method declared in source has both results `false`.

**Practical impact:** When searching for methods usable as endpoints, handlers, or API descriptions, do not blindly treat all methods from `getDeclaredMethods()` as independent declarations in source. A bridge can produce two `Method` objects with the same name and parameters but different return types. Choose the right business method and consider excluding bridge/synthetic methods if your problem requires user-written declarations.

### Analyzing constructors and anonymous classes

- `TextBox` declares no constructor, yet the compiler generates a default constructor; `getDeclaredConstructor().isSynthetic()` returns `false` in the example. This shows **compiler-generated does not always mean synthetic**.
- The syntax `new Runnable() { ... }` actually declares an anonymous class in source code. Reflection recognizes `isAnonymousClass() == true`, while `isSynthetic() == false` under this `javac` compilation. `isAnonymousClass()`, `isLocalClass()`, `isMemberClass()`, and `isSynthetic()` answer different questions.
- `Outer.Inner` reads `seed` of the outer object, so `javac` in the example stores the outer reference in a synthetic field usually named `this$0`. The name and implementation of this field **are not a language contract**; other compilers/JDKs may generate different structures. In modern Java versions, the compiler can even omit the outer field when retaining the reference is unnecessary. Always check `Field.isSynthetic()` rather than guessing from the name.

## 4. Common synthetic structures

| Situation | Structure that may appear | How to check and notes |
| --- | --- | --- |
| Overriding a generic method after type erasure | Bridge method | `Method.isBridge()` and `Method.isSynthetic()`; verified example above. |
| Overriding with a covariant return type | Bridge method when binary needs to preserve original descriptor | Check `isBridge()`; not every override needs a bridge. |
| Inner/local class using outer state or captured local variables | Field holding captured reference/value | `Field.isSynthetic()`; field existence and name depend on the compiler. |
| Lambda expression | Support structure generated by compiler/JVM, e.g., helper method or runtime class | Do not rely on `lambda$...` names, method counts, or class shapes as a stable contract. |
| Private access between nested classes | Older compilers could add synthetic accessors | Since Java 11 there is nest-based access control; do not assume `access$...` methods will appear. |
| Enum and record | Certain implicit members, along with other implementation details | Implicit members valid at language level are not necessarily synthetic; inspect each member individually rather than labeling all of them. |

Distinguish **language rules** from **compiler implementation strategies**. Names like `this$0`, `val$...`, `lambda$...`, and `$VALUES` are common in `javac`-generated bytecode, yet there is no guarantee every JDK or compiler uses those exact names.

### For constructor/method parameters

`Executable.getParameters()` returns `Parameter` objects. Three kinds must be distinguished:

1. **Explicit:** parameters explicitly written in the source declaration, e.g., `void send(String text)`.
2. **Implicit (mandated):** parameters implicit per language rules; check `Parameter.isImplicit()`.
3. **Synthetic:** parameters neither explicitly nor implicitly declared at source level; check `Parameter.isSynthetic()`.

For example, a non-static inner class usually needs a reference to the outer object passed upon instantiation. That extra parameter is a constructor element at the binary level, while whether Reflection records `isImplicit()`/`isSynthetic()` depends on metadata and how the compiler emits the class file. When you need to inspect parameter information, consider compiling with `javac -parameters` to retain `MethodParameters` metadata; do not assume every extra parameter is synthetic, nor treat `false` when metadata is missing as proof about source code.

## 5. Relationship to class file flags and `Modifier`

The JVM class file has the `ACC_SYNTHETIC` flag (hex value `0x1000`) for classes/fields/methods respectively, and the `ACC_BRIDGE` flag (`0x0040`) for methods. A class file can also represent synthetic via the `Synthetic` attribute per class-file version rules.

These are concepts from the **class file format**, not simply keywords writable in Java source. `java.lang.reflect.Modifier` primarily interprets ordinary modifiers (public/private/static/final...); the Reflection API provides dedicated `isSynthetic()` and `isBridge()`, so use those methods instead of interpreting magic bits from `getModifiers()` to draw conclusions about synthetic elements.

You can cross-check with the bytecode of the example program:

~~~bash
javap -v 'SyntheticReflectionDemo$TextBox'
~~~

Quote names containing `$` to prevent the shell from expanding this character (especially in Bash). In the output, look for the two methods named `value`:

- The method returning `java.lang.String` was written in source code.
- The bridge returning `java.lang.Object` has a flags line containing `ACC_BRIDGE, ACC_SYNTHETIC`.

When inspecting an actual class file, `javap -v` helps verify flag markers and descriptors, while Reflection handles metadata of classes loaded at runtime. Do not use `getName().contains("$")` as a substitute for `isSynthetic()`: names are not a reliable classifier.

## 6. Using `isSynthetic()` when building frameworks/tools

A common scenario is collecting developer-declared methods to build metadata. You can start with the following filter:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

static List<Method> userFacingMethods(Class<?> type) {
    return Arrays.stream(type.getDeclaredMethods())
            .filter(m -> !m.isSynthetic())
            .filter(m -> !m.isBridge())
            .toList();
}
~~~

This is a **utility method snippet**, which must be placed inside a Java class with the corresponding imports; `toList()` is available since Java 16. It returns methods declared in the class binary that pass two filter criteria, rather than **exactly reconstructing the set of methods present in source code**. Compiler-generated non-synthetic methods can still slip through; synthetic methods genuinely needed by bytecode analysis tools would be excluded.

Selection workflow depending on goal:

- **Building a business API list:** filter or handle bridge/synthetic separately, then evaluate visibility, annotations, overrides, and inheritance relationships per actual requirements. Do not rely solely on `isSynthetic()`.
- **Bytecode analysis, debugging, profiling, low-level serialization:** you may **need to keep** synthetic members because they represent existing runtime structures.
- **Matching methods after type erasure:** inspect `getDeclaredMethods()`, `isBridge()`, `getReturnType()`, and signatures together; do not assume one Reflection `Method` always corresponds to one Java source declaration.

## 7. Common mistakes and self-check exercise

1. **"Everything compiler-generated is synthetic."** False: default constructors, certain implicit enum/record members, and classes created by language syntax are key counterexamples.
2. **"Synthetic means uncallable."** False: synthetic bridges still have an execution role and can be invoked when the JVM dispatches calls.
3. **"A name containing `$` is definitely synthetic."** False: `$` can appear in valid Java identifiers and compilers are not required to preserve internal naming conventions.
4. **"One source method = one Reflection method."** Not always true: bridges create an extra element in `getDeclaredMethods()`.
5. **"`getMethods()` is enough to inspect compiler-generated elements."** Not always true: private/package elements usually require `getDeclaredMethods()` or `getDeclaredFields()`.
6. **"Every `javac` version generates the same accessor/field/lambda methods."** No guarantee: nestmates architecture, class-file versions, and compiler optimizations can vary the output.
7. **"`isSynthetic() == false` confirms the member appeared explicitly in source."** False: it is only the absence of the synthetic marker, not proof of origin.

**Self-check:** Change `TextBox extends Box<String>` to `TextBox extends Box<Integer>` and override `Integer value()`; predict what return types the reflective `value()` methods will have and which method is the bridge. Then try removing `isBridge()` from the filter to see `Object value()` reappear in the list.

**Standard references:**
- [Java SE 17 — `Class.isSynthetic()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSynthetic())
- [Java SE 17 — `Method.isBridge()` and `Method.isSynthetic()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [JLS 17 §13.1 — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1)
- [JVMS 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
