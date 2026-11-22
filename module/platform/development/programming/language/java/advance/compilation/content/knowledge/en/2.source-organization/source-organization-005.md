# Binary Names of Nested Classes and Generated `.class` Files

## 1. Why Understand Binary Names?

A single Java source file can declare multiple types: a *top-level class*, *member class*, `static` nested class, *local class*, and *anonymous class*. When compiling, `javac` typically generates **one `.class` file for each class or type that needs representation**, rather than one file per `.java` by default. The file name depends on the type's **binary name** and the package name.

This matters when:
- Inspecting build directories, JAR contents, and `javap` output; determining which declaration a `.class` file comes from.
- Using reflection, `Class.forName(...)`, class-loading configuration, or handling `ClassNotFoundException`.
- Distinguishing the name used in source code from the name the JVM uses to link compiled classes.
- Packaging, deploying, and debugging when one of the generated `.class` files is missing.

You should distinguish **binary name** from **canonical name**, **simple name**, and **JVM internal name**. The `$` sign in a binary name does not mean every class containing `$` is necessarily a nested class: `$` is also a valid character in Java identifiers.

## 2. Naming Rules

Suppose we have package `demo` and top-level class `Outer`:

| Declaration kind | Written/seen in source code | Typical binary name | Class file in `out/demo/` |
| --- | --- | --- | --- |
| Top-level class | `Outer` | `demo.Outer` | `Outer.class` |
| Non-`static` member class | `Outer.Inner` | `demo.Outer$Inner` | `Outer$Inner.class` |
| `static` member class | `Outer.Nested` | `demo.Outer$Nested` | `Outer$Nested.class` |
| Deeper member class | `Outer.Middle.Leaf` | `demo.Outer$Middle$Leaf` | `Outer$Middle$Leaf.class` |
| Local class named `Local` | `Local` inside a block | e.g. `demo.Outer$1Local` | e.g. `Outer$1Local.class` |
| Anonymous class | `new Runnable() { ... }` | e.g. `demo.Outer$1` | e.g. `Outer$1.class` |

**Core rules:**
1. A top-level type's binary name is the package name, a dot, then the type name: `demo.Outer`. In the *default package*, there is no package prefix.
2. A member type has the binary name `<enclosing type's binary name>$<member name>`. This rule applies to both `static` classes and non-`static` member classes; the `static` keyword does **not** change the separator.
3. A local class has a suffix containing one or more digits before its simple name; an anonymous class has a numeric suffix without a simple name. The number `1` in the table is an example output you may see from `javac`, **not a stable number to rely on in code**. Numbering order, placement, and the number of generated files can change depending on the source code or compiler.
4. The dot in `demo.Outer.Inner` is how a member type name is written in Java and is also its canonical name. The corresponding binary name uses `$`: `demo.Outer$Inner`. Local classes and anonymous classes **have no canonical name**.

A Java package can have multiple non-`public` top-level classes in a single source file; each such class also gets its own binary name and `.class` file. For `public class Outer`, the source file name ordinarily must be `Outer.java`.

## 3. Runnable Experiment on Java 17+

Create file `src/demo/Outer.java` with the following full contents:

~~~java
package demo;

public class Outer {
    private final String label;

    public Outer(String label) {
        this.label = label;
    }

    public class Inner {
        public String text() { return label + "/Inner"; }
    }

    public static class Nested {
        public String text() { return "Nested"; }
    }

    public void run() {
        class Local {
            String text() { return "Local"; }
        }

        Runnable anonymous = new Runnable() {
            @Override public void run() {
                System.out.println("Anonymous");
            }
        };

        System.out.println(new Inner().text());
        System.out.println(new Nested().text());
        System.out.println(new Local().text());
        anonymous.run();

        System.out.println(Inner.class.getName());
        System.out.println(Inner.class.getCanonicalName());
        System.out.println(Nested.class.getName());
        System.out.println(Local.class.getName());
        System.out.println(Local.class.getCanonicalName());
        System.out.println(anonymous.getClass().getName());
        System.out.println(anonymous.getClass().getCanonicalName());
    }

    public static void main(String[] args) {
        new Outer("Outer").run();
    }
}
~~~

In the project directory containing `src`, create the `out` directory (for example with `mkdir out`), then run:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Outer.java
java -cp out demo.Outer
~~~

Standard output of the program above when compiled with `javac`:

~~~text
Outer/Inner
Nested
Local
Anonymous
demo.Outer$Inner
demo.Outer.Inner
demo.Outer$Nested
demo.Outer$1Local
null
demo.Outer$1
null
~~~

In a test run with `javac --release 17`, the generated files include:

~~~text
out/
└── demo/
    ├── Outer.class
    ├── Outer$Inner.class
    ├── Outer$Nested.class
    ├── Outer$1Local.class
    └── Outer$1.class
~~~

File listing order on your machine may differ. The two numbered names are **specific examples from this program and `javac`**; if you add local classes, anonymous classes, or switch compilers, do not treat the numbers as a compatibility guarantee. The `-d out` option tells `javac` to output classes following the package structure into the `out` directory. The command `java -cp out demo.Outer` runs using the **binary name** of the class containing `main`, not the path `out/demo/Outer.class`.

### Breakdown of Each Kind

**`Outer.class`.** This is the top-level class `demo.Outer`. In `Outer`'s bytecode there are references to the nested classes, yet each nested class itself still has an independent class file.

**`Outer$Inner.class`.** This is a **non-`static`** member class. It can access `Outer`'s instance field `label`. Instantiating it from outside in a method explicitly shows the enclosing object:

~~~java
Outer outer = new Outer("A");
Outer.Inner inner = outer.new Inner();
System.out.println(inner.text()); // A/Inner
~~~

The snippet above is a usage example inside a runnable method, **not a standalone Java file**. In the full example, `new Inner()` is called directly inside an instance method of `Outer`, so the compiler uses the current `this` object as the enclosing object. The constructor in bytecode typically has an extra first parameter of type `Outer` to pass this reference; therefore, reflection looking up a constructor with only the parameters written in source may fail.

**`Outer$Nested.class`.** This is a `static` member class. It can be instantiated with `new Outer.Nested()` without an instance of `Outer`. It still uses `$` in its binary name. The difference between `static` and non-`static` concerns enclosing-object semantics and access scope, **not whether `$` is present**.

**`Outer$1Local.class`.** `Local` is declared and used only inside `run()`. It has the simple name `Local` but no canonical name, so `Local.class.getCanonicalName()` returns `null`. It can capture *final/effectively final* local variables or parameters of the enclosing block, following Java rules.

**`Outer$1.class`.** This is an anonymous class type created by `new Runnable() { ... }`. The class is still a real class in bytecode, assigned a binary name for the JVM to load. It has neither a simple name nor a canonical name; `anonymous.getClass().getCanonicalName()` returns `null`. Do not confuse this anonymous type with a lambda expression: modern JVM versions may implement lambdas via *hidden classes* at runtime and do not necessarily create `Outer$$Lambda$...class` files in the build directory.

## 4. Comparing Class Name Retrieval APIs

For `Outer.Inner.class` in the example:

| Expression | Result |
| --- | --- |
| `getName()` | `demo.Outer$Inner` |
| `getCanonicalName()` | `demo.Outer.Inner` |
| `getSimpleName()` | `Inner` |
| `getTypeName()` | `demo.Outer$Inner` |
| `getDeclaringClass().getName()` | `demo.Outer` |

For `Local.class`, `getSimpleName()` is `Local`, `getCanonicalName()` is `null`, `getDeclaringClass()` is `null`, and `getEnclosingMethod()` can identify the `run` method. For the anonymous class, `getSimpleName()` is the empty string and `getCanonicalName()` is `null`. `getEnclosingClass()` finds the lexically enclosing class for local/anonymous types; `getDeclaringClass()` is only for **member** types declared directly inside a class or interface. Therefore, these two APIs are not interchangeable.

**Note on `Class.forName`.** For member classes, the API accepts the binary name:

~~~java
Class<?> type = Class.forName("demo.Outer$Inner");
System.out.println(type.getName()); // demo.Outer$Inner
~~~

This snippet is used inside a method declaring `throws ClassNotFoundException` (or handling the exception), when `demo.Outer$Inner` is on the classpath. Calling `Class.forName("demo.Outer.Inner")` will not find this class: the dot there is the canonical name syntax used in Java source. Some libraries or configuration tools have their own syntax; check clearly whether they expect a *binary name*, *canonical name*, or a tool-defined notation.

**The array case.** `getName()` for an array class is not simply the binary name followed by `[]`. For example, `Outer.Inner[].class.getName()` is `[Ldemo.Outer$Inner;`, whereas `getCanonicalName()` is `demo.Outer.Inner[]`. The `[L...;` notation is how the JVM represents reference arrays in `Class` names.

## 5. Binary Names, JVM Internal Names, and Descriptors

In source code, the author writes `demo.Outer.Inner`; `Class.getName()` for the member type returns `demo.Outer$Inner`. Inside a *class file*, the JVM also uses the **internal name**: changing the dots separating packages to `/`, while keeping the `$` in the class-name portion.

| Form | Example and context |
| --- | --- |
| Source / canonical name | `demo.Outer.Inner` |
| Binary name | `demo.Outer$Inner` |
| Internal name | `demo/Outer$Inner` |
| Reference field/type descriptor | `Ldemo/Outer$Inner;` |
| One-dimensional array descriptor | `[Ldemo/Outer$Inner;` |
| Path in output/JAR | `demo/Outer$Inner.class` |

At the class-file level, `L...;` wraps an internal name to form a descriptor for a reference type; `[` denotes one array dimension. Do not replace `$` with `/` to represent nesting; `/` in an internal name separates **packages**.

## 6. What Is Stored in Bytecode?

The `.class` file name helps locate the type, while attributes inside the class file supplement information about nesting relationships:

- **`InnerClasses`** describes member types and corresponding information about nested types. Do not conclude a type is `static` solely from the `$` in its file name; inspect the class metadata.
- **`EnclosingMethod`** can record the enclosing class/method for a local or anonymous class. Reflection relies on the appropriate metadata to answer queries about the enclosing method or constructor.
- **`NestHost` / `NestMembers`** (nestmates, since Java 11) allow classes in the same nest to access `private` members under JVM access-checking rules. They do not merge multiple `.class` files into a single file.
- **Synthetic members** may be generated by the compiler to hold a reference to the enclosing object, capture data, or support compilation mechanisms. A commonly seen field is `this$0`, for instance, yet **the field's name and existence are not a stable API**. The compiler may omit the enclosing reference if unneeded or alter its implementation across versions.

You can use the following commands to inspect the member class after running `javac` in section 3:

~~~text
javap -classpath out -private 'demo.Outer$Inner'
javap -classpath out -v 'demo.Outer$Inner'
~~~

Single quotes preserve `$` literally in Bash and PowerShell; on Windows `cmd.exe`, wrap the class name in double quotes. `-private` shows non-public members, while `-v` shows class file structure, constant pool, and attributes. Depending on the `javac`/JDK version, the exact contents of synthetic fields and attributes may vary; rely on the actual bytecode rather than inferring from file names.

## 7. Implications for Building, Packaging, and Class Loading

**Compilation and classpath.** `javac` writes output following the package structure under `-d`. The JVM needs to locate all referenced class files on the classpath/module path. Copying only `Outer.class` and omitting `Outer$Inner.class` can cause the program to fail once the code begins using `Inner` (for instance, `NoClassDefFoundError`). When the failure surfaces depends on loading, linking, and execution; it does not necessarily blow up immediately at startup.

**JAR.** When packaging the entire output directory, the corresponding entries are typically `demo/Outer.class`, `demo/Outer$Inner.class`, `demo/Outer$Nested.class`, etc. You can inspect them with `jar tf ten-file.jar`. Avoid name-based exclude rules that ignore the meaning of `$`, as they may omit member/local/anonymous classes.

**Reflection.** When loading by name from a database, plugin, or configuration file, you must know whether it expects a binary name or another form. When instantiating a non-`static` inner class via reflection, the constructor may require an instance of the enclosing class. Do not deduce bytecode constructor parameters solely from the parameter count visible in source.

**Renaming/refactoring.** Renaming `Outer` or `Inner` changes the member type's binary name and `.class` path. Compiled clients, serialized data, or configurations storing the old name may break even if the new source compiles cleanly. For public APIs, the binary name is part of type identity at the linkage level. Local/anonymous class names, especially their numeric portions, are even more unsuitable for persistent storage or integration contracts.

**Using `$` in actual names.** A top-level class can be named with `$` under Java identifier syntax; thus you cannot rely on the substring `$Inner` alone to confirm it is a member class. Combine declaration information or metadata (`InnerClasses`, reflection) when exact identification is needed.

## 8. Common Misconceptions

1. **"One `.java` file produces exactly one `.class` file."** False: source with multiple type declarations, local classes, or anonymous classes can generate multiple files.
2. **"Only `static` nested classes have `$`."** False: both `static` and non-`static` member classes use the binary naming rule with `$`.
3. **"`Outer.Inner` can be passed directly to `Class.forName`."** False in this example: the API requires `demo.Outer$Inner`.
4. **"`Outer$1Local` will always be the local class's name."** False: the sequence number is a detail that can change after source edits or when using a different compiler.
5. **"`getCanonicalName()` always returns a string."** False: for local/anonymous classes it returns `null`; choose `getName()` when you need binary name identification.
6. **"Deploying only `Outer.class` is enough."** False if the program also needs the generated classes. Package the complete build output.
7. **"Every name starting with `Outer$$Lambda` is a file emitted by `javac`."** False: lambdas have their own runtime implementation mechanism; do not assume corresponding files exist in the output.

## 9. Knowledge Self-Check

- Given `package p; class A { static class B { class C {} } }`, the binary name of `C` is **`p.A$B$C`**; whether `B` is `static` does not change the name-joining rule.
- `Outer.Inner.class.getName()` in the example returns **`demo.Outer$Inner`**; `getCanonicalName()` returns **`demo.Outer.Inner`**.
- When adding a new anonymous class to `run()`, recompile and list `out/demo/`. The numbered files may change; the right answer must be based on the actual compilation output rather than hardcoding `$1`.
- If a JAR contains `Outer.class` but lacks `Outer$Nested.class`, check the packaging step and JAR entries before suspecting imports in source.

**Key takeaway:** Member names are written with dots in source, use `$` in binary names, and are emitted as separate `.class` files organized by package. For local/anonymous classes, read compiler-generated names for diagnostics, but do not use their numeric indices as a stable contract.