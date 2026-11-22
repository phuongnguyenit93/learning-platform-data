# Registering Declarations and Building the Symbol Table in the Java Compiler

When reading a Java program, the compiler cannot simply replace each name in source code with an address or a piece of bytecode. First, it needs to know **which entities have been declared**: packages, classes, interfaces, records, enums, fields, methods, constructors, parameters, and local variables. It also needs to store ownership relationships and the visibility scope of each declaration, so later steps can determine which entity a name such as `count` or `process` refers to.

In compiler architecture, this task is commonly called **entering declarations** and building the **symbol table**. With `javac`, "Enter" is the name of a group of internal operations; exact descriptions of internal classes may vary across JDKs. The goal of this article is to understand the processing flow and stable language rules, and to distinguish between a declaration being registered and a reference being resolved and type-checked.

## 1. From Source Code to the Symbol Environment

Consider:

```java
class Invoice {
    private int total;

    int add(int amount) {
        total += amount;
        return total;
    }
}
```

The parser first builds an abstract syntax tree (AST) representing a class declaration `Invoice`, a field `total`, a method `add`, parameter `amount`, and expressions in the method body. However, the AST alone is not enough to determine which field `total` in `total += amount` refers to or whether the addition is valid.

The compiler needs to create/store conceptual information such as:

| Symbol | Declaration kind | Owner | Essential information |
| --- | --- | --- | --- |
| `Invoice` | Type/class | Current package | Name, modifiers, type, members |
| `total` | Field | `Invoice` | `private`, type `int` |
| `add(int)` | Method | `Invoice` | Return type `int`, parameter `int` |
| `amount` | Parameter | Method `add` | Type `int`, method body scope |

The example only illustrates important attributes; how the compiler organizes objects, scopes, and when it creates them are implementation details.

A **symbol** is a structured representation of a declared entity. A **scope** is the lookup environment for names currently available in a code region. **Symbol table** is a general term for the system that stores, classifies, and looks up those symbols across multiple scopes; it is not necessarily a single flat table for the entire program.

```text
.java bytes
   |
   v
Lexing / Parsing --> AST (syntactic structure)
                         |
                         v
                 Enter / register declarations
                         |
                +--------+--------+
                |                 |
           Type symbol        Member symbols
           and environment    and class scope
                |                 |
                +--------+--------+
                         |
                         v
             Attribution / name resolution,
             type assignment and type checking
                         |
                         v
             Flow checks, lower, generate
```

This is a learning model, not a claim that every compiler/JDK always scans the tree in exactly one linear pass. `javac` has an on-demand symbol completion mechanism (*lazy completion*), reads additional classes/sources from the classpath/module path, and interacts with annotation processing.

## 2. How Does "Registering Declarations" Differ from "Resolving References"?

Two related operations with different responsibilities:

1. **Registering declarations:** upon seeing `class Invoice`, register the existence of `Invoice` in the package environment; when completing the class declaration, register fields/methods/constructors in the class's member environment.
2. **Name resolution and type checking:** upon encountering `invoice.add(5)`, look up `invoice`, determine the variable's type, find available `add` methods, apply access and overload rules, and then verify that argument `5` is valid.

The reference `invoice.add(5)` is not a new declaration. It needs to be **associated with the already declared symbol**, along with the expression's type information at that location.

A declaration can already be registered while the program is still invalid. Example:

```java
class Price {
    int value() {
        return "not an int";
    }
}
```

The compiler can register the symbol for class `Price` and method `value(): int`, yet when analyzing the method body, it discovers that `String` cannot be returned where `int` is required. Do not interpret "having a symbol" as "having passed type checking."

Similarly, the symbol for a method is registered before every call to that method is checked for overloads and before the compiler generates bytecode. Steps may interleave as needed, yet they are distinct logical responsibilities.

## 3. Kinds of Symbols and Ownership Relationships

A symbol system must answer at least four questions: **what name, what kind, in which environment, and what type/signature?**

### Package and type

The qualified name `com.example.order.Invoice` identifies a type belonging to package `com.example.order`. Within the same package, multiple compilation units (`.java`) can contribute top-level declarations. `javac` needs to link them when resolving cross-file references.

Type symbols include classes, interfaces, enums, annotation interfaces, and records; nested types have an ownership relationship with their enclosing type. A file can contain multiple valid top-level declarations, though the filename rule for a top-level `public` type must still be obeyed.

### Members of a type

Fields, methods, constructors, and nested types reside in the type's member structure. Methods can share the same **name** through overloading; the compiler must distinguish methods by valid signature rather than using the name as a unique key.

Example:

```java
class Formatter {
    String format(int number) {
        return Integer.toString(number);
    }

    String format(String text) {
        return text.strip();
    }
}
```

The two `format` methods have the same name but different parameter type lists. Upon encountering `format(10)` or `format(" abc ")`, call resolution selects the appropriate overload based on Java rules, not merely on the existence of a `format` name in the symbol table.

### Parameters, local variables, and type parameters

Method parameters, variables in blocks, loop variables, lambda parameters, pattern variables, and type parameters have different scopes and rules. They are not simply registered into the class member scope. In `javac`, local scope information is attached to the method body analysis environment and structures used during attribution/flow.

Example:

```java
class Box<T> {
    private T value;

    T get() {
        return value;
    }
}
```

`T` is a type parameter of `Box`; `value` is a field of type `T`; `get` is a method returning `T`. Do not interpret `T` as a class existing at runtime or a field of `Box`: it is a type variable at compile time, subject to generics and type erasure rules later on.

## 4. Scope: Symbol Lookup Depends on Code Location

The *scope* of a declaration is the region in which its name can be used under Java rules, provided it is not shadowed by another declaration. A reference can search the nearest scope, then examine members, nested types, types in the package, imports, and contextually available names. **Scope, name shadowing, accessibility, and validity of a reference are distinct questions.**

The following example is permitted:

```java
public class ScopeDemo {
    private static final int VALUE = 100;

    public static void main(String[] args) {
        int VALUE = 5;

        System.out.println(VALUE);
        System.out.println(ScopeDemo.VALUE);
    }
}
```

Compile and run in the directory containing `ScopeDemo.java`:

```bash
mkdir out
javac -encoding UTF-8 -d out ScopeDemo.java
java -cp out ScopeDemo
```

Stdout:

```text
5
100
```

Here the local variable `VALUE` shadows the simple name of field `VALUE` inside the method body; `ScopeDemo.VALUE` accesses the field through the class name. The compiler must distinguish **two different symbols with the same name** based on lookup context.

By contrast, the following program is **invalid**:

```java
class InvalidScope {
    void run() {
        int count = 1;
        {
            int count = 2; // error: duplicate local variable name in enclosing scope
        }
    }
}
```

In Java, a nested block cannot freely redeclare a local variable that is already in scope in an enclosing block. This differs from a local variable shadowing a field as in the previous example. Do not apply the "an inner scope is always allowed to redefine any name" rule found in some other languages.

## 5. Registering Declarations Enables Referencing Members Written Later

An important characteristic of Java: a method can usually be called on a line appearing **before** the line where that method is declared.

```java
public class ForwardMethodDemo {
    public static void main(String[] args) {
        System.out.println(greeting());
    }

    static String greeting() {
        return "registered";
    }
}
```

Commands:

```bash
javac -encoding UTF-8 ForwardMethodDemo.java
java ForwardMethodDemo
```

Stdout:

```text
registered
```

The compiler does not interpret a program as "read top-down and only know what appeared above." Method declarations are collected so that valid reference sites can be resolved even when the definition appears after the call.

However, **do not conclude that every forward reference before a declaration is valid**. Per JLS `8.3.3, certain simple-name references to fields in field initializers or initializer blocks are restricted:

```java
class InvalidForwardField {
    int first = second; // illegal forward reference
    int second = 10;
}
```

Even though the compiler knows that field `second` is declared, that form of reference is still invalid under language rules. In other words, **"the symbol already exists" does not eliminate checks on initialization order and usage context**.

Methods, local variables, field initializers, enum constants, and static initialization each have their own rules. When diagnosing, separate "cannot find symbol" errors from "symbol exists but used in an invalid context" errors.

## 6. Comprehensive Java 17+ Example: Classes, Members, Overloads, Scope, and Overrides

Save file `SymbolTableDemo.java` with the following complete contents:

```java
public class SymbolTableDemo {
    private static final int VALUE = 100;

    static class Greeter {
        static String message() {
            return "ready";
        }
    }

    static class Base {
        String label() {
            return "base";
        }
    }

    static class Derived extends Base {
        @Override
        String label() {
            return "derived";
        }
    }

    static int combine(int left, int right) {
        return left + right;
    }

    static String combine(String left, String right) {
        return left + right;
    }

    public static void main(String[] args) {
        int VALUE = 5;
        Base item = new Derived();

        System.out.println("field=" + SymbolTableDemo.VALUE);
        System.out.println("local=" + VALUE);
        System.out.println("nested=" + Greeter.message());
        System.out.println("overloadInt=" + combine(2, 3));
        System.out.println("overloadString=" + combine("a", "b"));
        System.out.println("dispatch=" + item.label());
    }
}
```

Run from the directory containing the file:

```bash
mkdir out
javac -encoding UTF-8 -d out SymbolTableDemo.java
java -cp out SymbolTableDemo
```

Exact stdout:

```text
field=100
local=5
nested=ready
overloadInt=5
overloadString=ab
dispatch=derived
```

How this relates to the symbol table:

| Expression | What the compiler must process |
| --- | --- |
| `SymbolTableDemo.VALUE` | Look up class `SymbolTableDemo` and static field `VALUE` |
| `VALUE` in `main` | Look up local variable `VALUE` in the nearest scope |
| `Greeter.message()` | Look up nested type `Greeter` and static method `message` |
| `combine(2, 3)` | Set of methods named `combine`; select overload taking `int, int` |
| `combine("a", "b")` | Select overload taking `String, String` |
| `Base item = new Derived()` | Check subtype relationship and valid assignment |
| `item.label()` | At compile time, check member against static type `Base`; at runtime, dispatch to `Derived`'s override |

Pay special attention to the last row: **compile-time symbol resolution does not mean runtime implementation selection**. The compiler confirms that the `label()` call has a valid signature via the static type; the Java Virtual Machine can select the overriding implementation based on the actual object type.

After compilation, in addition to `SymbolTableDemo.class`, there are class files for the nested classes, typically named `SymbolTableDemo$Greeter.class`, `SymbolTableDemo$Base.class`, and `SymbolTableDemo$Derived.class`. Class file naming/format is a separate layer from the compiler's internal symbol table.

## 7. Inside \`javac\`: Enter and Completing Declarations

The following names help learners locate responsibilities in OpenJDK source code; **these are internal APIs of `jdk.compiler`**, not a stable interface for applications to depend on directly:

| Concept/unit in `javac` | General function |
| --- | --- |
| `JCTree`, `JCCompilationUnit`, `JCClassDecl` | AST nodes for compilation units and declarations |
| `Enter` | Registers class symbols and related environments |
| `TypeEnter` | Completes type info, inheritance relationships, type parameters, and members as needed |
| `Symbol` and class/method/variable symbol variants | Represents identifiers, owners, types, modifiers, and metadata |
| `Scope` | Supports collecting and looking up symbols in an environment |
| `Attr`, `Resolve` | Name/semantic resolution, assigning types to expressions, checking calls and accessibility |
| `Flow` | Analyzes control flow constraints such as definite assignment and reachability |

Do not equate internal class names with **a single mandatory step** in the Java Language Specification. The JLS specifies the semantic outcome to obey; `javac` is one implementation with a specific architecture.

In modern `javac` design, *enter* can be understood in two layers of responsibility:

**Layer 1 — creating class representations.** When scanning a compilation unit, the compiler sets up the class symbol, attaches it to its enclosing environment, recognizes nested classes, and stores the environment for further processing.

**Layer 2 — completing class information.** When a class's members or type are needed, the compiler completes type parameters, supertypes, interfaces, fields/methods/constructors, and related information. Part of the work can be **deferred** until needed (*on-demand completion*). Therefore, do not assume the compiler always finishes recording 100% of every field and method of every class in file order before beginning type checking.

This characteristic helps explain why the compiler can discover types from related sources or class files, can analyze class A before completing class B, and still allow valid cross-declaration references.

Older versions of `javac` used the name `MemberEnter` for many responsibilities that newer versions place in `TypeEnter`; diagrams and articles on internals should be cross-referenced with the exact JDK version. Do not write application code directly against `com.sun.tools.javac.*` unless genuinely building a compiler-dependent tool and accepting that internal APIs change.

## 8. From AST to Symbol, and Then to Type: Reading Compilation Errors Correctly

Consider three separate scenarios.

### Name does not exist in scope

```java
class MissingName {
    void run() {
        System.out.println(unknownValue);
    }
}
```

The compiler cannot find a valid symbol for `unknownValue`. The typical message has the form `cannot find symbol` and points to variable `unknownValue`. Check declarations, typos, imports, packages, classpath, module visibility, and scope.

### Name exists but used with wrong type

```java
class WrongType {
    int count = 3;

    void run() {
        count = "three";
    }
}
```

Symbol `count` exists; the problem is that `String` cannot be assigned to `int`. This is a type-checking error, usually reported as `incompatible types`. Adding imports or declaring another field will not address the actual cause.

### Multiple declarations with an invalid duplicate signature

```java
class DuplicateMethod {
    void save(int value) { }

    void save(int number) { } // error: duplicate signature save(int)
}
```

Parameter names `value` or `number` do not make the two methods different overloads. The compiler must verify declaration validity/uniqueness based on the Java signature. This case differs from the `combine(int, int)` and `combine(String, String)` example above.

The three snippets in section 8 **intentionally do not compile**, serving to identify error types; do not combine them with the runnable program in section 6.

## 9. How Imports, Packages, and Classpath Affect Building the Name Environment

A `cannot find symbol` error does not necessarily mean the parser could not read a declaration. Example:

```java
package demo.app;

import demo.model.Invoice;

public class App {
    Invoice current;
}
```

The compiler must find `demo.model.Invoice` in simultaneously compiled sources, the source path, or a valid class/module path. If the class is absent, an import does not create that entity. **An import is a mechanism to bring the name of an existing declaration into lookup scope**, not a command to "download libraries from the Internet" or automatically compile every similarly named file.

Points to distinguish:

- `package demo.app;` specifies the namespace of the compilation unit, without creating physical folders for the code. File paths in normal build workflows need to match the package.
- `import demo.model.Invoice;` allows using the simple name `Invoice` per import rules; it does not replace providing the corresponding source/class.
- Two types with the same simple name in different packages are still two different symbols, such as `java.util.Date` and `java.sql.Date`. Imports do not resolve every conflict automatically; sometimes the fully qualified name must be used.
- `-classpath`/`--class-path`, `-sourcepath`/`--source-path`, and module path options govern which definitions the compiler can find. Searching for an additional source to retrieve a declaration may also trigger implicit compilation.
- Accessibility under `public`, `protected`, package access, and `private` is checked by context; **finding a symbol** does not guarantee permission to use it.

When building multiple JPMS modules, *readability* and package exports also affect type visibility. Do not apply a scope diagram meant solely for classpath projects to every module while ignoring module boundaries.

## 10. Symbol Table Differs from Constant Pool, Local Variable Table, and Reflection

Various "table" terms in the Java ecosystem are easily confused:

| Concept | Time/scope | Meaning |
| --- | --- | --- |
| Compiler symbol table | When analyzing and compiling source/classes | Stores declared entities, scopes, types, and relationships needed for resolution |
| Class file constant pool | In `.class` bytecode | Stores constants, names, and symbolic references per the JVM class file format |
| LocalVariableTable attribute | *Optional* debug info in `.class` | Can describe names/slots/lifetimes of local variables when debug info is present |
| Reflection | Runtime | Inspects the class/member info that the JVM exposes through APIs |
| Debugger/IDE symbol table | Tool-dependent | May build its own name model for search, refactoring, breakpoints |

There is no rule that "the compiler copies the symbol table verbatim into the class file." Many compile-time structures are discarded or transformed during bytecode generation. For example, local variable names may be absent from the class file if appropriate debug attributes are not generated; type parameters are subject to erasure and signature metadata limits.

The command:

```bash
javap -p SymbolTableDemo
```

allows viewing class/member info from the compiled class file (with `-p`, including non-public members). This is an **artifact inspection window**, not a way to print the entire symbol table existing inside `javac` during the Enter phase.

## 11. Public Tools for Observing Declarations and Symbols

If building an annotation processor or source code analysis tool, prefer JDK-supported APIs:

- `javax.lang.model.element.Element` along with `TypeElement`, `ExecutableElement`, `VariableElement` to inspect declarations and member relationships;
- `javax.lang.model.type.TypeMirror` to represent types at the language-model level;
- `javax.lang.model.util.Elements` and `Types` to find types, compare types, and find members;
- `javax.annotation.processing.AbstractProcessor` and `RoundEnvironment` to process declarations provided by the compiler across annotation processing rounds;
- `com.sun.source.tree.*` and `com.sun.source.util.Trees`/`TreePath` to associate an AST position with the corresponding `Element`, when using supported compiler/tree APIs.

Code example **illustrated inside an annotation processor**, not a standalone Java file:

```java
TypeElement type = processingEnv.getElementUtils()
        .getTypeElement("demo.model.Invoice");

if (type != null) {
    for (Element member : type.getEnclosedElements()) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                member.getKind() + " " + member.getSimpleName()
        );
    }
}
```

To actually use this, declare the processor, import the `javax.lang.model.element.*` and `javax.tools.Diagnostic` classes, configure the build's processor path/annotation processing, and ensure type `demo.model.Invoice` is present in the compilation environment. Not every name the compiler can resolve is visible at every point/round; `getTypeElement` may return `null`.

Calling `getEnclosedElements()` lets you observe declared members associated with the type; it is not a snapshot of every local variable in each method body, nor is it a copy of `com.sun.tools.javac.code.Scope`.

## 12. Common Misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| "The parser knows name `x` exists so the call must be valid" | The AST stores syntax; name resolution, access permissions, and type checking still have to run |
| "The symbol table is a single `Map<String, Object>`" | The compiler needs multiple environments/scopes, symbol kinds, overloads, owners, and types |
| "Any local variable can be redeclared in a child block" | Java restricts redeclaration when a local of the same name is still in an enclosing scope |
| "Since fields are registered, using them before declaration is valid everywhere" | The JLS has specific restrictions on forward field references in initializers |
| "Methods with the same name are always duplicates" | Overloads are valid if their signatures differ under Java rules |
| "The compiler selects overrides at build time" | The compiler resolves the call/type; runtime dispatch can select the overriding implementation |
| "Imports generate missing classes" | Imports only adjust lookup scope; the class/source must still exist in the build |
| "`javap` prints `javac`'s symbol table" | `javap` reads the class file after compilation, without accessing full compiler state |
| "Enter always finishes all members before any other step" | Type/member completion can happen on demand and interleave with compiler activities |
| "`com.sun.tools.javac.*` is a stable application API" | It is internal implementation; prefer `javax.lang.model`, `javax.tools`, and `com.sun.source` when appropriate |

## 13. Practical Diagnostic Workflow

When a compilation error involves names, declarations, or symbols, you can follow this order:

1. **Identify the error category:** did the parser report invalid syntax, `cannot find symbol`, ambiguous reference, duplicate declaration, illegal forward reference, incompatible types, or an access error? Each category points to a different layer.
2. **Locate the root declaration:** what is the fully qualified name, which package/class/block does the symbol belong to, and was it actually included in the compilation unit or classpath/module path?
3. **Check scope at the usage site:** does a local/parameter shadow a field; is there an import conflict; is a static context calling an instance member?
4. **Check signatures and types:** which overload applies, how do generic type parameters and inference behave, are there any conversions or access restrictions?
5. **Check special rules:** forward references, definite assignment, inheritance/overriding, duplicate methods, and module visibility.
6. **Reproduce with the project's exact compiler/JDK:** run `javac` with explicit sources and paths; do not rely on stale classes left in old output as evidence.
7. **Distinguish compile-time from runtime:** bytecode, reflection, or runtime errors are consequences at a different stage, insufficient to deduce exact internal Enter operations.

For example, a `cannot find symbol: variable count` error inside a lambda may stem from the name being out of scope; a `variable count might not have been initialized` error shows the compiler already knows variable `count` yet definite assignment analysis is unsatisfied. The two errors require two different fixes.

## 14. Self-Check Exercises

**Exercise A — predict output.** In `ScopeDemo`, which variable is printed by `System.out.println(VALUE)`, and which is printed by `System.out.println(ScopeDemo.VALUE)`? The answers are local `5` and static field `100` respectively; they share the same name yet belong to different scopes/owners.

**Exercise B — distinguish "does not exist" from "wrong type."** Try compiling the two programs `MissingName` and `WrongType` (in section 8, one file at a time). One error occurs because the name cannot be resolved, while the other occurs because the symbol has an incompatible type. Record the actual messages from the `javac` version you run.

**Exercise C — declaration order.** Swap the positions of `greeting()` and `main()` in `ForwardMethodDemo`: the program still compiles/runs. Try the `InvalidForwardField` example: an error occurs even though field `second` exists as a declaration. Explain using the difference between scope and forward reference rules.

**Exercise D — overload and override.** In `SymbolTableDemo`, predict which member `combine("a","b")` selects and which implementation `item.label()` runs. Answer: the `combine(String,String)` overload is selected at compile time; `Derived.label()` runs via dynamic dispatch. These are two decisions occurring at two different times.

## 15. Summary and Reference Documentation

Registering declarations enables the compiler to build a model of **entities, types, signatures, owners, and scopes**. This model is the foundation for resolving name usages, checking overloads, access permissions, inheritance relationships, and program validity. In `javac`, class symbols are registered and type contents can be completed on demand; attribution, flow checking, and code generation steps continue using those results.

When reading or debugging the compiler, always separate three questions: **"has the declaration been seen yet?", "which declaration does this reference bind to and is it valid?", "what class file was generated?"** Answering them in order will help pinpoint where the error originates.

Further reading:

- [Java Language Specification, Chapter 6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html): scope, shadowing, name resolution, access control.
- [Java Language Specification, `8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.3): forward field reference rules.
- [OpenJDK `Enter.java`](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/classes/com/sun/tools/javac/comp/Enter.java): current implementation reference source; cross-reference with the JDK tag in use because internals may change.
- [`javax.lang.model.element` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/package-summary.html): public declaration model for tooling/annotation processing.