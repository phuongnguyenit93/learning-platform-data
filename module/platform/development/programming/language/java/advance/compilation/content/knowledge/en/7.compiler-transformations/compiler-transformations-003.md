# Compiling nested classes, local classes, and anonymous classes in Java

## 1. Objectives and big picture

Java allows writing classes inside other class declarations or inside blocks. Source looks like a nested structure, yet the JVM works with **standalone classes in bytecode form**, each having its own identity and capable of being loaded on demand. Therefore, `javac` must translate scoping relationships in source code into relationships representable by class files: references to the enclosing object, *captured* data, constructors, class metadata, and corresponding call instructions.

In Java, **nested classes** include common kinds:

| Kind | Where declared | Requires an outer class object when instantiated? | Typical compilation mechanism |
| --- | --- | --- | --- |
| **Static nested class** | `static class Nested` member of another class | No | A separate class file; no enclosing instance reference merely because it is declared nested |
| **Inner member class** | Non-`static` `class Inner` member | Yes in normal instantiation contexts | A separate class file, usually with a constructor taking the enclosing instance and a field holding the reference |
| **Local class** | Named declaration inside a block, such as a method body | Depends on static/non-static context and how it is declared | Separate class file; can hold captured local variables and enclosing instance |
| **Anonymous class** | `new SuperType(...) { ... }` expression | Depends on context | Separate class file for the anonymous declaration, can hold captured values; has no simple name in source |

According to the Java Language Specification, an **inner class** is a nested class that is not explicitly or implicitly declared `static`. Thus a static nested class is still a *nested class*, but not an *inner class*. Nested enums, records, and member interfaces have their own implicit `static` rules; inner class capture behavior should not be mechanically applied to them.

This lesson focuses on **code transformations during compilation**: what extra artifacts the compiler must generate, how data is passed, and how the JVM views those types. The `.class` file names are only part of the result.

## 2. How do nested classes go through the compilation pipeline?

One can visualize how `javac` processes source as follows:

~~~text
CompilationDemo.java
      |
      v
Parse: recognize top-level class, member class, local class,
       anonymous class expression; build syntactic structure
      |
      v
Resolve / attribute / validate:
       name scope, types, access, enclosing instance,
       supertype, final / effectively final of captures
      |
      v
Lowering / transform representation:
       prepare standalone classes, enclosing instance passing path,
       captured values and required constructors/fields
      |
      v
Generate bytecode + metadata:
       CompilationDemo.class
       CompilationDemo$StaticNested.class
       CompilationDemo$Inner.class
       CompilationDemo$1Local.class
       CompilationDemo$1.class
~~~

This is a **conceptual diagram**, not a guarantee that all internal steps of `javac` always occur exactly once in this linear order. The compiler may combine symbol processing, attribution, annotation processing, lowering, and generation across multiple phases; however, from the perspective of Java source, these class forms must be semantically checked and converted into runnable JVM structures.

Things to distinguish:

- **Lexical scope**: where source code is permitted to refer to `Inner`, `Local`, method variables, and enclosing class fields.
- **Enclosing instance**: the instance associated with an inner class to access the instance state of the enclosing class.
- **Captured variable**: the value of a local variable or parameter used from inside a local/anonymous class across Java source scope boundaries.
- **Binary names and class files**: mechanisms for class identification and loading; nesting relationships do not mean multiple declarations are merged into a single `.class`.

## 3. Complete, runnable Java 17+ example

Create the file **`src/demo/CompilationDemo.java`** with the exact contents below, saved as UTF-8:

~~~java
package demo;

public class CompilationDemo {
    private final String owner;
    private int secret = 7;

    public CompilationDemo(String owner) {
        this.owner = owner;
    }

    public static class StaticNested {
        public String label() { return "static"; }
    }

    public class Inner {
        public String label() { return owner + ":" + secret; }
    }

    public void work(int offset) {
        String suffix = "!";

        class Local {
            String label() { return "local:" + (secret + offset) + suffix; }
        }

        Runnable anonymous = new Runnable() {
            @Override public void run() {
                System.out.println("anonymous:" + owner + ":" + offset + suffix);
            }
        };

        System.out.println(new StaticNested().label());
        System.out.println(new Inner().label());
        System.out.println(new Local().label());
        anonymous.run();

        System.out.println("inner declaring: "
                + (Inner.class.getDeclaringClass() == CompilationDemo.class));
        System.out.println("local enclosing: "
                + Local.class.getEnclosingMethod().getName());
        System.out.println("anon anonymous: "
                + anonymous.getClass().isAnonymousClass());
    }

    public static void main(String[] args) {
        new CompilationDemo("A").work(5);
    }
}
~~~

In Bash, from the directory containing `src`, run:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/CompilationDemo.java
java -cp out demo.CompilationDemo
~~~

In PowerShell, you can use `New-Item -ItemType Directory -Force out` to create the directory. The same `javac` and `java` commands work if the JDK is on `PATH`.

**Exact stdout** of the example when run successfully:

~~~text
static
A:7
local:12!
anonymous:A:5!
inner declaring: true
local enclosing: work
anon anonymous: true
~~~

Explanation:
- `StaticNested` is a standalone class that does not require a `CompilationDemo` instance.
- `Inner` reads `owner` and `secret` of the current `CompilationDemo` object.
- `Local` reads field `secret`, parameter `offset=5`, and local `suffix="!"`; thus computing `7+5=12`.
- The anonymous class implements `Runnable` and also references `owner`, `offset`, and `suffix`.
- Reflection distinguishes member classes, the enclosing method of a local class, and anonymous classes.

With this exact source and `javac --release 17`, the `out/demo/` directory contains the files:

~~~text
out/
└── demo/
    ├── CompilationDemo.class
    ├── CompilationDemo$StaticNested.class
    ├── CompilationDemo$Inner.class
    ├── CompilationDemo$1Local.class
    └── CompilationDemo$1.class
~~~

The listing order on the operating system is not fixed. Numbered names like `$1Local` or `$1` are details of a specific compilation output, not a contract to rely on in code. When inserting additional anonymous/local declarations or switching compilers, those numbers can change.

**One source file produces multiple class files** because each class declaration has its own representation in the JVM. At runtime, executing `work()` multiple times creates **multiple objects** of `Local` and the anonymous class, rather than compiling or defining a new class per invocation.

## 4. Static nested class: nested by name but holds no enclosing instance

In source:

~~~java
public static class StaticNested {
    public String label() { return "static"; }
}
~~~

This class is placed inside `CompilationDemo` in terms of declaration, but **does not require a `CompilationDemo` object to instantiate**:

~~~java
CompilationDemo.StaticNested value = new CompilationDemo.StaticNested();
System.out.println(value.label()); // static
~~~

This is a snippet used inside a method or program that has already declared `CompilationDemo`, not standalone source.

When compiled, the JVM receives a separate class `demo.CompilationDemo$StaticNested`. It has its own constructor; the sample snippet does not require the constructor to accept a `CompilationDemo` parameter. The `$` symbol in the binary name indicates member naming and **cannot be used to infer that the class has an enclosing object**.

A static nested class can access eligible `static` members of the outer class. It **cannot directly read `owner` or `secret`**, because those are instance fields; a specific `CompilationDemo` object and appropriate access permissions are required.

## 5. Inner member class: the compiler turns the enclosing instance relationship into data

In source:

~~~java
public class Inner {
    public String label() { return owner + ":" + secret; }
}
~~~

In `work()` (an instance method of `CompilationDemo`), `new Inner()` implicitly uses `CompilationDemo`'s `this` as its **enclosing instance**.

Placed outside class `CompilationDemo`, the corresponding instantiation is:

~~~java
CompilationDemo outer = new CompilationDemo("B");
CompilationDemo.Inner inner = outer.new Inner();
System.out.println(inner.label()); // B:7
~~~

The snippet above is also a **usage excerpt inside a method**, not a standalone Java file.

At the bytecode level, an inner member class is typically implemented by the compiler roughly equivalent to this idea:

~~~java
// Pseudocode illustrating the structure the compiler may generate;
// not valid replacement source code for the original declaration.
final class InnerLowered {
    private final CompilationDemo enclosing;

    InnerLowered(CompilationDemo enclosing) {
        this.enclosing = enclosing;
    }

    String label() {
        return enclosing.owner + ":" + enclosing.secret;
    }
}
~~~

The pseudocode above is only meant to explain **why an outer reference is needed**. The actual class has its own binary name, nesting metadata, and access rules determined by the JVM. One should not manually write `InnerLowered` or replace `new Inner()` with an artificial constructor in source.

When running `javap -p` on the compiled example, you can see:

~~~text
public class demo.CompilationDemo$Inner {
  final demo.CompilationDemo this$0;
  public demo.CompilationDemo$Inner(demo.CompilationDemo);
  public java.lang.String label();
}
~~~

In the verified `javac --release 17` output, the `this$0` field holds the outer reference; the actual constructor takes `CompilationDemo`. **The field name/field generation strategy is a compiler implementation detail**, not a public property to program against. Starting in newer JDKs, the compiler can even optimize away holding the outer reference when unnecessary; Java's semantic rules are what to rely on.

The outer object also affects **lifetime**: if an inner object holds a strong reference to the outer object, the garbage collector cannot reclaim the outer object while this reference relationship remains. This is why care is needed when retaining instances of non-static inner classes longer than intended.

## 6. Local class: lifting local variables into object state

The local class in the example is declared inside the body of method `work`:

~~~java
String suffix = "!";
class Local {
    String label() { return "local:" + (secret + offset) + suffix; }
}
~~~

Source allows `Local` to read `offset` (method parameter) and `suffix` (local variable), even though the JVM method stack frame for `work` is not where state lives permanently with the `Local` object. The compiler must **capture the required values** into data accessible by the local class object, typically via synthetic constructor parameters and fields.

With `javac` in this test, `javap -p` for class `demo.CompilationDemo$1Local` shows the fields:

~~~text
final int val$offset;
final java.lang.String val$suffix;
final demo.CompilationDemo this$0;
~~~

`val$offset`, `val$suffix`, and `this$0` are **compiler-generated names**; Java source is not permitted to rely on these names. How values are passed to the constructor should be inspected using `javap -c -p` or the descriptor in `javap -v`; some `javap` views may display the local class constructor in an abbreviated form or differently from its actual descriptor.

### Final and effectively final

A local variable/parameter used by a local or anonymous class must be `final` or **effectively final**: after being properly assigned a value, it is not reassigned in a way that causes it to lose effective finality.

The following example **does not compile**:

~~~java
void broken() {
    int count = 1;
    class Local {
        int read() { return count; }
    }
    count++; // makes count no longer effectively final
}
~~~

This is an excerpt inside a class, intentionally a **compile error**. `javac` will report that variables referenced from an inner class must be final/effectively final. Reason: if a local object stored a snapshot of a variable that the method kept mutating, a programmer could easily mistake it for a live-updated shared variable.

**Capturing a reference variable does not mean the referenced object is immutable.** If a local variable `final List<String> items` is captured, code can still call `items.add(...)`; only reassigning the variable `items = ...` is forbidden. Be careful with concurrent mutation and state visibility across threads; a captured reference by itself does not replace synchronization mechanisms.

A local class has a **name scope restricted** to where it is declared. The compiler still generates a separate `.class` with a binary name containing a numeric part and the class name; this does not mean class `Local` can be referenced by its Java source name from outside the method.

## 7. Anonymous class: an expression creating an object while simultaneously declaring a class

The snippet:

~~~java
Runnable anonymous = new Runnable() {
    @Override public void run() {
        System.out.println("anonymous:" + owner + ":" + offset + suffix);
    }
};
~~~

declares an unnamed subclass/implementation in source, right inside the instantiation expression. The compiler creates a separate class type, in this example `demo.CompilationDemo$1`, implementing `Runnable` and defining `run()`. The `javap -p` output from the example may contain:

~~~text
class demo.CompilationDemo$1 implements java.lang.Runnable {
  final int val$offset;
  final java.lang.String val$suffix;
  final demo.CompilationDemo this$0;
  demo.CompilationDemo$1();
  public void run();
}
~~~

Note that `javap` may display an abbreviated constructor signature; read the bytecode descriptor to check implicitly passed parameters. Captured fields may be renamed or eliminated depending on compiler version and optimizations, but Java source behavior must remain intact.

An anonymous class can:
- **Extend a class**, or **implement an interface** specified in the `new` expression.
- Override methods, and add valid fields or instance initializers.
- Capture final or effectively final local variables/parameters; in an instance context it can also associate with an enclosing instance.

An anonymous class **has no simple name in source and cannot declare named constructors**, so for complex initialization you can use an instance initializer or the supertype's constructor, and you cannot call `new AnonymousName()` from elsewhere.

Unlike a **lambda expression**: `Runnable r = () -> ...` has different semantics from `new Runnable() { ... }`, especially in how `this` is interpreted; lambdas are typically lowered by the compiler via `invokedynamic` and the runtime creates an appropriate implementation class, without necessarily generating `CompilationDemo$$Lambda$....class` at compile time. The anonymous class in the example has an actual `CompilationDemo$1.class`.

## 8. Private access and nestmates

An inner class is permitted to access private fields of its outer class in Java source, for example `Inner.label()` reads `owner` and `secret`, even though the bytecode resides in a **different class file**.

In modern class files (Java 11+), the JVM supports **nestmate** relationships: classes within the same nest are allowed to access each other's private members when the corresponding metadata and runtime rules are valid. Important attributes:

- `NestMembers` on the *nest host*, usually the top-level class.
- `NestHost` on a nest member, such as the corresponding member/local/anonymous class.
- `InnerClasses` describes nested type declaration information; it is not the sole mechanism for checking private access.
- `EnclosingMethod` describes the enclosing method or constructor for local/anonymous classes.

When compiling for an older bytecode target that does not support nestmates, the compiler may have to generate **synthetic access methods** to route private accesses through auxiliary methods. With `--release 17`, inspect `NestHost`/`NestMembers` and direct access instructions; do not implicitly assume every compiler must generate `access$000` or any specific synthetic method name.

In a class file, nesting declaration metadata and nest access metadata are **related but distinct** concepts. A binary name containing `$` is not enough to prove a nestmate relationship or private access rights; inspect class metadata and verify the runtime package/nest host when investigating.

## 9. Reading class files with javap

After a successful build in section 3, run:

~~~bash
javap -classpath out -p 'demo.CompilationDemo$StaticNested'
javap -classpath out -p 'demo.CompilationDemo$Inner'
javap -classpath out -p 'demo.CompilationDemo$1Local'
javap -classpath out -p 'demo.CompilationDemo$1'
~~~

Single quotes keep `$` intact in Bash/PowerShell. In Windows `cmd.exe`, use double quotes instead of single quotes.

To inspect deeper:

~~~bash
javap -classpath out -c -p 'demo.CompilationDemo$Inner'
javap -classpath out -v 'demo.CompilationDemo$1Local'
javap -classpath out -v demo.CompilationDemo
~~~

- `-p` displays non-public members as well, including compiler-generated fields shown by the tool.
- `-c` prints JVM instructions, helping locate `new`, `dup`, `invokespecial`, `getfield`, `putfield`, and other access instructions.
- `-v` prints the constant pool, descriptors, and class-file attributes such as `InnerClasses`, `EnclosingMethod`, `NestHost`, and `NestMembers`.

When inspecting the **constructor of an inner member class**, distinguish the signature declared in Java source from the actual constructor descriptor; the compiler passes the enclosing object even though source writes `new Inner()`. For local/anonymous classes, captured variables may be passed through constructor parameters and assigned to fields. This is equivalent logic generated by the compiler, not the JVM runtime automatically searching local variables of a finished stack frame.

Since Java 9+, string concatenation can be implemented using `invokedynamic` and `StringConcatFactory`; do not expect to always see `new StringBuilder` in bytecode. Lowering details depend not only on whether a class is nested, but also on the target version and compiler version.

### Cross-checking with reflection

Several APIs reflect relationships between declarations:

| API | For the corresponding class kind |
| --- | --- |
| `Class.getName()` | Binary name, such as `demo.CompilationDemo$Inner`. |
| `Class.getCanonicalName()` | Member class: `demo.CompilationDemo.Inner`; local/anonymous: `null`. |
| `Class.getSimpleName()` | Member `Inner`, local `Local`, anonymous is an empty string. |
| `Class.getDeclaringClass()` | Member class returns directly declaring class; local/anonymous returns `null`. |
| `Class.getEnclosingClass()` | Can indicate the lexically enclosing class, including for local/anonymous. |
| `Class.getEnclosingMethod()` | Local/anonymous declared inside a method: reflects the enclosing method; member class may be `null`. |
| `Class.isMemberClass()` / `isLocalClass()` / `isAnonymousClass()` | Determines the class kind according to JVM metadata. |

Do not parse `$` manually instead of using these APIs: Java identifiers also allow `$` in programmer-chosen names, and the numeric parts of local/anonymous classes are unstable.

## 10. Java source rules that affect the lowering step

### 10.1. Must have a valid enclosing instance

Creating a non-static inner class inside a static context without an outer object is a compile error:

~~~java
public class WrongOuter {
    class Inner {}

    static void bad() {
        // new Inner(); // error if uncommented: missing enclosing instance
        WrongOuter outer = new WrongOuter();
        Inner ok = outer.new Inner();
    }
}
~~~

The `WrongOuter.java` file above compiles because the erroneous line is commented out. If you uncomment `new Inner()`, javac reports an error about non-static context; the fix is to pass an object via `outer.new Inner()` or change the member class to static nested if it does not need outer state.

### 10.2. Local/anonymous capture requires final/effectively final

Reassigning `offset` or `suffix` in `CompilationDemo.work` (where they are used by local/anonymous classes) will render the source invalid. The compiler does not "track live mutations" instead of capturing. If mutable state is intentionally needed, use a state-holding object and consider thread safety, rather than expecting a local primitive to be updated inside the captured object.

### 10.3. Rules for `this` differ between anonymous classes and lambdas

In an anonymous class, `this` inside `run()` is the **anonymous class instance**. In a lambda, `this` refers to the enclosing instance according to the lexical context. When converting an anonymous class to a lambda to make it "shorter", you must check `this`, `super`, scope, and serialization references; do not treat the two forms as always semantically equivalent.

### 10.4. The number of class files does not always equal the number of `class` keywords

An anonymous class does not contain a `class` declaration keyword yet still typically has a class file. A lambda does not necessarily have its own class file in `javac`'s output. Nested records, enums, synthetic helpers, or compiler choices also make outputs vary. Therefore, inspect the actual build output rather than counting manually from source tokens.

## 11. Testing and packaging after compilation

When building JARs or copying artifacts, include all actually needed classes in the output. Keeping only `CompilationDemo.class` and omitting the `CompilationDemo$*.class` files can cause the program to fail when an execution path requires a missing class, typically leading to `NoClassDefFoundError` or a corresponding linkage error.

Example of creating a JAR after building:

~~~bash
jar --create --file compilation-demo.jar -C out .
jar --list --file compilation-demo.jar
java -cp compilation-demo.jar demo.CompilationDemo
~~~

These commands use the JDK 17+ JAR tool. The JAR contents will include entries under the `demo/` package; entry ordering depends on the tool. If there is a script excluding files containing `$`, verify the exclude rule does not accidentally delete member/local/anonymous classes.

When debugging:
- **`NoClassDefFoundError` in production:** check that the output and JAR contain all corresponding `$...` classes; compare the classpath/module path.
- **`ClassNotFoundException` during reflection:** check that the correct **binary name** is passed for a member class, such as `demo.CompilationDemo$Inner`.
- **`cannot find symbol` for `Local`:** check whether the local class is being referenced outside its lexical scope.
- **`local variables ... must be final or effectively final`:** check where the captured variable was reassigned.
- **Inner class retaining outer object too long:** consider designing a static nested class or extracting a top-level class if an enclosing instance is not needed.
- **Differences across JDK versions:** do not hardcode field names `this$0`, `val$...`, local/anonymous indices, or bytecode instructions; check source semantics and class-file version.

## 12. Comparison table for memorization

| Question | Static nested | Inner member | Local | Anonymous |
| --- | --- | --- | --- | --- |
| Has a declared Java name? | Yes | Yes | Yes, only within scope | No |
| Where it appears | Body of a type | Body of a type | Block | `new` expression |
| Typical generated class name form | `Outer$Nested` | `Outer$Inner` | `Outer$1Local` | `Outer$1` |
| Requires an enclosing instance? | No | Yes in normal instance initialization | Depends on declaration context and semantics | Depends on context |
| Can capture effectively final locals? | Not merely by being nested in a type | Not in the sense of method lexical local capture; uses outer fields | Yes | Yes |
| Can have a named constructor in source? | Can declare | Can declare | Can declare | No |
| Separate class file? | Yes | Yes | Yes | Yes |
| Has a canonical name? | Yes | Yes | No | No |

Cases involving generics, static context, enum/record, or a compiler other than `javac` may alter representation details; the table highlights the core differences from Java source to bytecode.

## 13. Self-check exercises

**Exercise 1.** In the example, why does `StaticNested` not need `CompilationDemo` passed, whereas `Inner` may need it?  
**Answer:** a static nested class is not associated with an enclosing object; an inner member class has semantics tied to an enclosing instance, and `javac` must preserve that relationship when generating class files.

**Exercise 2.** Why can `offset` appear as a field in `CompilationDemo$1Local.class`?  
**Answer:** the local object needs to use the value of `offset` when executing its method; the compiler passes the capture via constructor/field so it does not depend on the outer method's stack frame.

**Exercise 3.** If `new CompilationDemo("A").work(5)` is called a thousand times, are there a thousand different `$1Local` classes?  
**Answer:** No. One class declaration is compiled into a class; each invocation may create another **instance** of that class.

**Exercise 4.** Does adding `suffix = "?";` before the statement creating `Local` cause an error?  
**Answer:** Yes, because the captured variable `suffix` is no longer effectively final according to Java rules.

**Exercise 5.** When compiling with Java 17, must the compiler always generate an `access$000` method for an inner class reading a private outer field?  
**Answer:** No. Class-file nestmates since Java 11 allow valid private access without forcing old-style bridge/accessor generation.

**Exercise 6.** Does `Class.getDeclaringClass()` for a local class return the enclosing class or `null`?  
**Answer:** `null`; `getEnclosingClass()` and `getEnclosingMethod()` are the appropriate APIs to find the lexical context.

**Exercise 7.** If `CompilationDemo$1.class` becomes `CompilationDemo$2.class` after editing the source, is that necessarily an error?  
**Answer:** No. The numbering of anonymous/local classes is a generated detail; do not put it into configuration or public contracts.

## 14. Official reference documentation

- [Java Language Specification 17 — §8.1.3 Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3)
- [Java Language Specification 17 — §14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3)
- [Java Language Specification 17 — §15.9.5 Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5)
- [Java Virtual Machine Specification 17 — Class-file attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7)

**Knowledge summary:** `javac` must turn nested declarations in source into separate JVM class files, preserving lexical scope, enclosing instances, captured values, and access rules. Use source-level semantics when designing programs; use `javap`, class-file metadata, and actual compilation outputs to understand lowering details, while avoiding dependence on synthetic names or compiler-generated numbering.