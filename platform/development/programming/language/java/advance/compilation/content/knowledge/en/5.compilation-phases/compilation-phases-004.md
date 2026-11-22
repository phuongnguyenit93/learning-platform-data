# Name Resolution, Scope, and Binding to Declarations During Java Compilation

In Java code, names such as `count`, `Account`, `List`, `println`, or `com.example.app.Main` are merely character sequences until the compiler performs **name resolution**: determining which variable, field, type, method, package, or declaration they refer to in a specific context. The result depends on **visibility scope**, imports, inheritance, expression types, overloading rules, and access permissions.

This is an important part of `javac`'s semantic processing. The compiler must determine which declaration a name refers to and check types before generating bytecode. Distinguish this step from the JVM finding, verifying, and linking classes at **runtime**.

## 1. Four Terms to Distinguish

| Term | Question it answers | Example |
| --- | --- | --- |
| Declaration | Where is the name introduced? | `int size = 3;` declares variable `size` |
| Scope | In which region of code can the name be used as a visible name? | A local variable is typically in scope for the remainder of its enclosing block |
| Name resolution | At this usage site, which declaration does the name refer to? | `size` in `println(size)` refers to a specific variable |
| Binding (binding name to declaration) | Which symbol/declaration did the compiler attach the reference to, and with what type/signature? | The call `sum(1, 2)` binds to the overload taking two `int`s |

**Scope does not mean valid accessibility in every situation.** A member can exist in lookup scope yet still be blocked by `private`, `protected`, or module `exports` rules. A local variable whose name is in scope but has not been **definitely assigned** cannot be read either.

Three layers of issues are often conflated:

1. **Is there any declaration matching this name?** If not, the compiler typically reports `cannot find symbol` or `package ... does not exist`.
2. **Can the found declaration be used here?** Check access permissions, assignability, types, and static/instance context.
3. **If there are multiple candidates, which one is selected?** For example, method overloading based on argument types at **compile time**; an ambiguous call may report `reference to ... is ambiguous`.

A note on terminology: Java also has the JVM's concept of **linking** (verification, preparation, and resolution of symbolic references). That is a different step from the compiler binding source code names to declarations. The two processes are related, yet the same meaning should not be used for every occurrence of the word "linking/binding."

## 2. Where Does Name Resolution Sit in the javac Process?

Overview of a common compilation flow:

~~~text
.java source code
    |
    v
Lexing / Parsing
  - Tokenize and build syntax tree
    |
    v
Collect declarations, build symbol table and environment
  - Packages, imports, top-level types, members
    |
    v
Semantic analysis
  - Resolve names, determine types
  - Check scope, accessibility, overloads
  - Check definite assignment, type conversions, etc.
    |
    v
Transform AST / generate bytecode
    |
    v
.class files (carrying symbolic references)
    |
    v
JVM loads, links, and executes when needed
~~~

This is a **conceptual diagram**, not a guarantee of the exact order of every internal pass in every `javac` version. In actual enter/attribute/analyze/generate operations, type and method resolution may interleave with syntax tree traversals.

For example, the compiler reads:

~~~java
import java.util.List;

List<String> names = List.of("A", "B");
~~~

To check this snippet, the compiler must understand `List` as type `java.util.List`, `String` as `java.lang.String`, `List.of` as a static method matching the arguments, and the assignment as type-compatible with `List<String>`. When the type declaration or dependency library cannot be found, the compiler cannot proceed to verify valid semantics.

The compiler can reference types from specified source files, from the source path, classpath, or module path per configuration. **Imports only assist with naming in source code; imports do not load dependencies.**

## 3. Kinds of Names and How to Read Them in Context

| Kind of name | Example | Meaning in context |
| --- | --- | --- |
| Local variable / parameter name | `total`, `customer` | A variable declaration in scope of a block/method |
| Field name | `this.total`, `Counter.count` | Member of a type accessed through an appropriate receiver |
| Type name | `String`, `Map.Entry` | Class, interface, enum, record, or type variable |
| Package name | `java.util` | Namespace containing types/other packages |
| Method name | `println`, `sum` | An invocation that must be evaluated by receiver and argument types |
| Qualified name | `java.util.ArrayList` | Specifies a type along with its package path or enclosing type |
| Name with receiver qualifier | `account.owner()` | Finds method `owner` on the compile-time type of `account` and matching inherited members |

The syntax `x.y` does not always mean "variable x has field y." Depending on context, `x` may be a package name, a type name, a variable name, or part of a qualified name. Java has rules for name classification and reclassification in the language specification.

For example:

~~~java
java.util.List<String> words = java.util.List.of("alpha");
System.out.println(words.size());
~~~

In the first line, `java.util.List` is a fully qualified **type name**; in the second line, `System` is a **type name**, `out` is a static field, and `println(...)` is a method call on the `PrintStream` object. The dot syntax looks the same, yet the resolution outcomes differ.

## 4. Runnable Example: One Name Can Have Multiple Candidate Declarations

Use Java 17 or later. Create the project:

~~~text
resolution-lab/
└── src/
    └── com/
        └── example/
            ├── domain/
            │   └── Account.java
            └── app/
                └── ResolutionDemo.java
~~~

**File `src/com/example/domain/Account.java`:**

~~~java
package com.example.domain;

public final class Account {
    private final String owner;

    public Account(String owner) {
        this.owner = owner;
    }

    public String label() {
        return "Account:" + owner;
    }
}
~~~

**File `src/com/example/app/ResolutionDemo.java`:**

~~~java
package com.example.app;

import java.util.List;
import com.example.domain.Account;

public final class ResolutionDemo {
    private static String label = "field";

    private static String pick(int value) {
        return "int:" + value;
    }

    private static String pick(long value) {
        return "long:" + value;
    }

    public static void main(String[] args) {
        String label = "local";
        Account account = new Account("Mai");

        System.out.println(label);
        System.out.println(ResolutionDemo.label);
        System.out.println(account.label());
        System.out.println(List.of("one", "two").size());
        System.out.println(pick(3));
        System.out.println(pick(3L));
    }
}
~~~

From the `resolution-lab` directory:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/domain/Account.java src/com/example/app/ResolutionDemo.java
java -cp out com.example.app.ResolutionDemo
~~~

If `out` already exists, there is no need to run `mkdir out` again. The path structure in the command uses `/`, suitable for Linux/macOS and also accepted by the Java CLI in many Windows contexts. You can use `\` in CMD/PowerShell if preferred.

**Exact stdout:**

~~~text
local
field
Account:Mai
2
int:3
long:3
~~~

Key resolution decisions:

1. `String label = "local"` declares a **local** variable with the same name as static field `label`. The unqualified reference `label` in `main` refers to the local variable because it shadows the field.
2. `ResolutionDemo.label` uses the type name to refer to the **static field**, bypassing the shadowing of the local name.
3. `Account` is found from `import com.example.domain.Account;`, while member `label()` is resolved through the `Account` type of variable `account`.
4. `List` comes from `import java.util.List;`, and `List.of(...)` selects the appropriate factory method from valid overloads. `size()` is looked up on the result type.
5. `pick(3)` selects overload `pick(int)`; `pick(3L)` selects `pick(long)`. Selection relies on the argument expression types, without waiting until runtime to pick an overload.

This example intentionally uses no dependencies outside the JDK so learners can compile it themselves, read the output, and experiment with renaming.

## 5. Scope of Declarations: Local, Parameter, Field, Type

In Java, each kind of declaration has its own scope. For common cases:

| Declaration | Typical visibility scope |
| --- | --- |
| Local variable in a block | From its declaration point in the block to the end of its enclosing block, subject to definite assignment rules |
| Method/constructor parameter | The method/constructor body and regions within the corresponding scope |
| Class field | Within the class scope and places where member access is valid per access permissions/inheritance |
| Member type | Within the enclosing type's scope and places where it can be validly referenced |
| Top-level type | Named in the package; outside the package it can be referenced via import or fully qualified name when accessible |
| Local class | The region following its declaration within the appropriate block |
| Type parameter | Within the scope of the type/method/constructor in which that type parameter is declared |
| Pattern variable | Within the program region where the pattern match is definitely known to succeed |

### Block scope and fields

**Standalone file `ScopeDemo.java`:**

~~~java
public final class ScopeDemo {
    private String name = "field";

    private void show(String name) {
        System.out.println(name);
        System.out.println(this.name);
        {
            int count = 2;
            System.out.println(count);
        }
        // count can no longer be used here.
    }

    public static void main(String[] args) {
        new ScopeDemo().show("parameter");
    }
}
~~~

Compile and run:

~~~bash
javac ScopeDemo.java
java ScopeDemo
~~~

Output:

~~~text
parameter
field
2
~~~

In `show`, parameter `name` shadows field `name`; `this.name` explicitly refers to the instance field. `count` is only in scope inside the inner block. If you uncomment and write `System.out.println(count);` after the block, the compiler will report an error because the name is no longer in scope.

**Shadowing does not mean the two variables are merged into one.** The field still exists, retains its value, and can be accessed via `this` if context permits.

### Cannot redeclare a local in a nested block with overlapping scope

Snippet **intentionally invalid, does not compile**:

~~~java
void wrong() {
    int value = 1;
    {
        int value = 2; // Error: value is already declared in enclosing scope.
    }
}
~~~

Java does not allow declaring a local variable with the same name as a local variable already in an overlapping scope as shown above. However, **a local variable is allowed to shadow a field**, like `label` in `ResolutionDemo`. These are two different situations.

### Scope differs from definite assignment

The following snippet is also **intentionally invalid**:

~~~java
void wrong(boolean condition) {
    int score;
    if (condition) {
        score = 10;
    }
    System.out.println(score); // Error: score might not have been assigned.
}
~~~

`score` is in scope at `println`, yet the compiler cannot prove it has been assigned on **all** paths reaching the read statement. That is a definite assignment error, not a missing declaration error.

## 6. Precedence Rules When Multiple Declarations Share a Name

To read code, you can use these questions in practical order:

1. **Which syntactic form is the name in?** Name of a type, variable, member, or method call? Is there a receiver `this`, a type name, or an expression to the left of a dot?
2. **Is there a matching local/parameter/type parameter declaration in the nearest scope?** If so, check shadowing rules and validity.
3. **Is it a member of the current class or a superclass?** Check field hiding, inheritance, access permissions, and static/instance context.
4. **Is there an import or a type name in the same package?** Check single-type imports, import-on-demand, `java.lang`, same package, and qualified names.
5. **If it is a method, how many overloads are applicable?** Check the compile-time type of the receiver, argument types, conversions, varargs, and specificity.
6. **Are there any access, module, or type-checking constraints blocking the reference?**

This is a **diagnostic checklist**, not a single formal precedence order for every kind of name. The Java specification has different rules for type names, variables, methods, members, and imports. For instance, a local variable can shadow a field name, yet you cannot rely on that same rule to resolve every conflict between type imports.

### Shadowing, hiding, and overriding are not the same

| Mechanism | What happens? | Timing/rules |
| --- | --- | --- |
| Shadowing | A closer declaration prevents a name in an outer scope from being referenced by its simple name | Resolved by scope at compile time |
| Field hiding | A field in a subclass can hide a field with the same name in a superclass | Field access is based on the compile-time type of the expression |
| Method hiding | A static method in a subclass can hide a corresponding static method in a superclass | Does not use virtual dispatch of instance methods |
| Method overriding | An instance method in a subclass re-implements an overridable method | Signature/call is determined at compile time; implementation is chosen by runtime receiver via virtual dispatch |

Avoid calling every case with the same name overriding. Two overloads with different parameters are also not overriding.

## 7. Imports and Type Name Resolution

Consider three types with the same simple name:

~~~java
java.util.Date utilDate = new java.util.Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Both share the short name `Date` yet are two different classes. If using two import-on-demand declarations:

~~~java
import java.util.*;
import java.sql.*;

// Inside a method body:
Date today = new Date(); // Intentionally invalid: Date is ambiguous.
~~~

The compiler cannot arbitrarily pick either type; `Date` from the two on-demand imported packages is an ambiguous candidate.

One valid approach is to import the type used more often and use an FQN for the remaining type:

~~~java
import java.util.Date;

// Inside a method body:
Date utilDate = new Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Or use fully qualified names for both for clarity. There is no alias syntax for type imports such as `import java.util.Date as UtilDate;` in Java.

Some rules worth remembering:

- `import java.util.List;` (single-type import) allows using the simple name `List` in appropriate places.
- `import java.util.*;` is an import-on-demand of **types in that exact package**, not automatically expanding to `java.util.concurrent.*`.
- `java.lang` is implicitly imported on demand; `String` and `System` do not require explicit imports.
- Code in the current package can use accessible top-level types of the same package without importing them.
- `import static java.lang.Math.PI;` provides the simple name of the static member; it does not import the entire class like a normal type import.
- Imports do not search for or download JARs from the Internet. If `javac` does not see the corresponding class on the classpath/module path or source path, the name still cannot be resolved.
- Package names sharing a common prefix have no special scope relationship: `com.example` and `com.example.impl` are two distinct packages.

### Nested type names

Consider the type:

~~~java
package com.example.model;

public final class Container {
    public static final class Item {
    }
}
~~~

In Java source, the canonical name of the nested type is `com.example.model.Container.Item`. Its binary name is `com.example.model.Container$Item` and the corresponding class file is typically `Container$Item.class`. This is a difference between **how the type is named in source code** and its **binary name in the JVM**, not two different classes.

## 8. Member Names and Receivers: Field, Static, Instance

Look at the standalone program:

**File `MemberDemo.java`:**

~~~java
class Parent {
    String code = "parent";

    String describe() {
        return "Parent method";
    }
}

class Child extends Parent {
    String code = "child";

    @Override
    String describe() {
        return "Child method";
    }
}

public final class MemberDemo {
    public static void main(String[] args) {
        Parent item = new Child();
        System.out.println(item.code);
        System.out.println(item.describe());
        System.out.println(((Child) item).code);
    }
}
~~~

Run:

~~~bash
javac MemberDemo.java
java MemberDemo
~~~

Output:

~~~text
parent
Child method
child
~~~

Explanation:

- `item.code` selects the **field** based on the compile-time type of variable `item`, which is `Parent`. Fields are not virtually dispatched.
- `item.describe()` is checked by the compiler against type `Parent`; because `Child` overrides this instance method, virtual dispatch at runtime invokes the implementation in `Child`.
- `((Child) item).code` uses the compile-time type of the cast expression, `Child`, so it selects field `Child.code`. In the example the cast is valid because the object is actually a `Child`.

Static methods also do not have instance-style overriding. Static method selection follows compile-time rules (hiding) and should be invoked explicitly through the type name to avoid creating the impression of dynamic dispatch.

## 9. Method Overloading: Selecting a Declaration at Compile Time

Overloading means multiple methods sharing the same name yet **having different parameter lists**. The compiler must find applicable candidates and select the most suitable method according to Java's overload resolution rules. Factors include:

- The number and compile-time types of the arguments.
- Type conversion possibilities: widening primitive/reference, boxing/unboxing, and varargs across applicability check phases.
- Generic type inference when invoking generic methods.
- The rule for selecting the "most specific" method among remaining candidates.
- Visibility and accessibility of the declarations.

Example **`OverloadDemo.java`**:

~~~java
public final class OverloadDemo {
    static String choose(int value) {
        return "int";
    }

    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        System.out.println(choose(5));
        System.out.println(choose(5L));
        Integer boxed = 5;
        System.out.println(choose(boxed));
    }
}
~~~

Run:

~~~bash
javac OverloadDemo.java
java OverloadDemo
~~~

Output:

~~~text
int
long
Integer
~~~

`5` has type `int`, so it selects `choose(int)`; `5L` has type `long`; variable `boxed` has reference type `Integer`, so it selects the exact match `choose(Integer)`. Changing the **declared** type of a variable can change which overload is selected even when the numeric value is mathematically identical.

### Overloads are not selected by a variable's runtime type

**File `OverloadVsOverride.java`:**

~~~java
class Base {
    String action() {
        return "Base action";
    }
}

class Derived extends Base {
    @Override
    String action() {
        return "Derived action";
    }
}

public final class OverloadVsOverride {
    static void execute(Base value) {
        System.out.println("Base overload -> " + value.action());
    }

    static void execute(Derived value) {
        System.out.println("Derived overload -> " + value.action());
    }

    public static void main(String[] args) {
        Base reference = new Derived();
        execute(reference);
        execute((Derived) reference);
    }
}
~~~

Run:

~~~bash
javac OverloadVsOverride.java
java OverloadVsOverride
~~~

Output:

~~~text
Base overload -> Derived action
Derived overload -> Derived action
~~~

Reasons:

1. The call `execute(reference)` selects **`execute(Base)`** at compile time because the variable has declared type `Base`. Java does not select the `Derived` overload by waiting to inspect the runtime object.
2. Inside `execute(Base)`, the instance method call `value.action()` dispatches to `Derived.action()` because the actual object is `Derived`.
3. The call `execute((Derived) reference)` has an argument expression with compile-time type `Derived`, so it selects overload `execute(Derived)`.

### Ambiguity with a null argument

The following two methods are both valid if declared separately:

~~~java
static void show(String value) { }
static void show(Integer value) { }
~~~

However, the call `show(null);` is **intentionally invalid**: both `String` and `Integer` are compatible reference types; neither type is more specific than the other by subtype relation, so the compiler reports the call as ambiguous. You can write `show((String) null);` or `show((Integer) null);` to specify the overload explicitly.

Cannot overload solely by return type:

~~~java
int total() { return 1; }
long total() { return 2L; } // Intentionally invalid: same parameter list.
~~~

Overload resolution does not use the return type to make two declarations with the same method signature valid as shown above.

## 10. Declarations in Lambdas, Nested Types, and Pattern Variables

### Lambdas and captured variables

**File `CaptureDemo.java`:**

~~~java
import java.util.function.Supplier;

public final class CaptureDemo {
    public static void main(String[] args) {
        String prefix = "Hello";
        Supplier<String> greeting = () -> prefix + " Java";
        System.out.println(greeting.get());
    }
}
~~~

Run:

~~~bash
javac CaptureDemo.java
java CaptureDemo
~~~

Output:

~~~text
Hello Java
~~~

The lambda references `prefix` in the enclosing scope. To capture a local variable, Java requires the variable to be `final` or **effectively final** (not reassigned after initialization according to language rules). Adding `prefix = "Hi";` after the declaration causes a compile error because the variable is no longer effectively final when captured.

A lambda does not create a new `this`: `this` inside a lambda (in an instance context) is the `this` of the enclosing type. An anonymous class, by contrast, has its own `this` instance. This is an important detail when the same member name appears across nested scopes.

### Pattern variables with instanceof (Java 17)

**File `PatternDemo.java`:**

~~~java
public final class PatternDemo {
    static void printIfString(Object input) {
        if (input instanceof String text) {
            System.out.println(text.length());
        }
    }

    public static void main(String[] args) {
        printIfString("Java");
        printIfString(123);
    }
}
~~~

Run:

~~~bash
javac PatternDemo.java
java PatternDemo
~~~

Output:

~~~text
4
~~~

`text` can only be used in the region where the pattern match result is determined to be true. If `text` is referenced after the entire `if` in this example, the compiler reports that the name is not in scope there. Pattern variable scope is based on flow analysis, making it more complex than ordinary block scope.

### Type parameters and type names

In `class Box<T> { T value; }`, `T` is a type parameter scoped to the generic declaration. It is resolved by the compiler as a **type name**, not a runtime variable. When compiling Java generics, type information is generally processed via **type erasure**, which affects bytecode signatures and the ability to declare overloads.

The following example **does not compile** due to a clash after erasure:

~~~java
void process(java.util.List<String> values) { }
void process(java.util.List<Integer> values) { } // Intentionally invalid: name clash.
~~~

Both parameter lists have the same erased type `List`; two valid JVM overloads differing only in generic type arguments cannot be created this way.

## 11. Valid Accessibility and Dependencies Also Participate in Resolution

A symbol can be found yet still be inaccessible:

~~~java
package com.example.domain;

class InternalAccount {
}
~~~

In code belonging to package `com.example.app`, `com.example.domain.InternalAccount` cannot be used because that top-level class has **package-private** access. Writing the fully qualified name does not bypass access rules. Similarly, a `private` member cannot be used from code lacking corresponding access permission.

Cases to check separately:

- **Package**: `com.example.domain` and `com.example.domain.internal` are two independent packages; they do not share package-private access due to having a common name prefix.
- **Inheritance**: `protected` has rules depending on package, subclass relationship, and access form; it does not mean "public to every subclass through every receiver."
- **Static context**: an instance field cannot be used directly from a static method without a valid instance receiver. For example, inside `static void main`, `this.field` is invalid.
- **JPMS**: when compiling with the module path, code in another module may need `requires` and the package to be `exports`-ed. A class existing on the module path is not enough for every public type to be visible.
- **Dependencies**: the compiler must find type information from source code or the corresponding classes/JARs/modules. A correctly written `import` with an incorrect classpath can still report errors.

Distinguish **symbol exists**, **symbol is looked up**, **symbol is visible/accessible**, and **call satisfies type checking**. These are distinct conditions.

## 12. Names Are Bound to Declarations at Compile Time, Yet the JVM Must Still Link Classes at Runtime

Once `javac` has resolved `com.example.domain.Account` and selected a matching method, bytecode may contain symbolic references to the class name, member name, and descriptor. It does not pre-write memory addresses of every method into the `.class` file.

Illustrative example (read as a diagram, not verbatim disassembly):

~~~text
Java source:
    Account account = new Account("Mai");
    account.label();

Compiler:
    Resolve type     -> com.example.domain.Account
    Resolve method   -> Account.label(): String
    Check access and types
    Emit .class with symbolic references

JVM:
    Load relevant classes as needed
    Verify/prepare/link and resolve symbolic references
    Execute instructions and dispatch suitable instance methods
~~~

**The result of source name resolution** is reflected in bytecode, whereas **JVM resolution** is the step of linking symbolic references with actual classes/fields/methods and can occur on demand at runtime. Java permits certain linking/resolution activities to occur earlier or later within specification bounds.

Some practical consequences:

| Symptom | Phase typically detected | Meaning |
| --- | --- | --- |
| `cannot find symbol` | Compile | The name cannot be resolved to a valid symbol |
| `reference to ... is ambiguous` | Compile | Multiple candidates, no unique selection possible |
| `... has private access` | Compile | Symbol may exist, yet access is forbidden |
| `NoClassDefFoundError` | Runtime | Class needed during linking/executing, but JVM could not obtain a valid definition (or prior initialization failed) |
| `NoSuchMethodError` | Runtime | Bytecode references a method that no longer has a matching definition in runtime classes, often due to compile/runtime version mismatch |
| `IncompatibleClassChangeError` | Runtime | Change to class/interface/member is incompatible with compiled bytecode |
| `ClassNotFoundException` | Runtime via API | Typically arises from class-loading operations by name such as `Class.forName(...)` when the class cannot be found |

Do not attempt to fix `NoSuchMethodError` merely by adding an import to source: imports affect names at **compile time**, whereas this error usually relates to library versions and the classpath at **runtime**.

## 13. Hands-on Practice with javac: Breaking Name Resolution

Starting from the `resolution-lab` project in section 4, perform each small modification in turn, recompile after each change, then revert to continue. The cases below are **intentionally broken**, not code meant to run.

### Experiment A: remove the import of Account

In `ResolutionDemo.java`, remove:

~~~java
import com.example.domain.Account;
~~~

In package `com.example.app`, the simple name `Account` is no longer known through an import. The compiler typically reports `cannot find symbol` where `Account` is used. Fix by restoring the import or writing the fully qualified name `com.example.domain.Account` for both type and constructor.

### Experiment B: rename field without updating reference

Change the declaration `private static String label = "field";` to `private static String title = "field";` while keeping `ResolutionDemo.label`. The compiler reports that field `label` of type `ResolutionDemo` cannot be found, even though a local variable named `label` still exists. Looking up `ResolutionDemo.label` does not fall back to the local variable, because the receiver explicitly specifies member access on the type.

### Experiment C: change argument type

Change `pick(3L)` to `pick("3")` while only overloads `pick(int)` and `pick(long)` remain. The compiler reports no suitable method for a `String` argument. A declaration with the same **method name** is not enough; the parameter list must match.

### Experiment D: omit dependent class from compile inputs

Keep both source files as before, but run the command specifying `Main`:

~~~bash
javac -encoding UTF-8 -d out src/com/example/app/ResolutionDemo.java
~~~

The command may **fail** if the compiler cannot find `Account` from the active source path/classpath; it may also **succeed** if `Account.class` already exists on an appropriate search path. Therefore, for a clean test, use a fresh output directory and configure search paths explicitly. To compile reliably from the example, list both files as in section 4:

~~~bash
javac -encoding UTF-8 -d out src/com/example/domain/Account.java src/com/example/app/ResolutionDemo.java
~~~

This experiment demonstrates that source path, compile classpath, and input source files determine **which declarations the compiler can see**. Java file paths and symbol names are two related layers of information, not identical.

## 14. Checklist for Reading Name Resolution Errors

When `javac` fails to find or picks the wrong declaration, go in this order:

1. **Identify the name at the error site.** Is it a variable name, type name, method name, or member after a dot? Is there a receiver?
2. **Find the actual declaration.** Are spelling, capitalization, package, and parameter list correct?
3. **Check scope.** Is it outside a block, outside a pattern variable's region, or shadowed by another declaration?
4. **Check imports.** Which package does the type belong to? Are there two candidates with the same simple name? Try writing the FQN to eliminate ambiguity.
5. **Check types.** What is the compile-time type of the receiver? Is the call static or instance? Which overloads apply to the argument types?
6. **Check access permissions.** Are there `private`, package-private, `protected`, or module `exports`/`requires` restrictions?
7. **Check dependencies and compiler flags.** Is the source file included in the `javac` command? Are compile classpath/source path/module path accurate?
8. **If compilation succeeds yet running fails**, check the runtime classpath/module path and library versions; distinguish linking/runtime dispatch from source name resolution.

### Misconceptions to avoid

- "If a variable name is in scope, it can be read immediately": false if not definitely assigned.
- "Same simple name means same type": false if belonging to different packages/enclosing types.
- "Imports solve every missing class error": false if the dependency is not on the compile path.
- "Subclasses override fields": false; fields follow hiding rules, not virtual dispatch.
- "The compiler selects overloads based on the runtime object": false; overload resolution relies on expression types at compile time.
- "Once compilation succeeds, the JVM will never fail linking": false if runtime lacks classes or libraries are incompatible.
- "Fully qualified names always bypass access permissions": false; access checking still applies.
- "Every name after a dot is a field": false; it may be part of a package/type name or a method invocation.

## 15. Self-Check Questions

**1.** A class has field `int size`; a method has parameter `int size`. Inside the method, what does `size` refer to, and what does `this.size` refer to?

**Answer:** `size` is the closer parameter in scope; `this.size` is the object's instance field.

**2.** Given `execute(Base)` and `execute(Derived)`; variable `Base value = new Derived();`. Which overload does `execute(value)` select?

**Answer:** `execute(Base)` at compile time. If there is an overridden instance method call inside, the implementation can be selected by the runtime class when executed.

**3.** Two import-on-demand declarations from different packages both contain type `Date`. Why does `Date d;` fail, while `java.util.Date d;` can be valid?

**Answer:** The simple name is not unique in context; the FQN explicitly indicates the type to reference, provided the type is available/accessible.

**4.** Variable `int n;` is in scope yet only assigned inside an `if (condition)` branch. Why can reading `n` after `if` fail?

**Answer:** The compiler cannot prove that a value is always assigned before use; this is definite assignment, not a missing declaration.

**5.** Why can `NoSuchMethodError` appear after source has compiled successfully?

**Answer:** Names and signatures are bound at compile time, yet the runtime class may be a different version, causing the JVM to fail to resolve the corresponding method reference.

## Key Takeaways

- **Declarations** create symbols; **scope** determines where names can be used; **name resolution** determines which declaration a reference points to; **type/access checking** verifies that usage is valid.
- **Shadowing** affects simple names; a receiver or qualified name can disambiguate the intended name when access permissions still hold.
- **Overloading** is selected based on compile-time types; **overriding** of instance methods can dispatch to implementations at runtime.
- Imports only support naming in source; source path/classpath/module path determine whether the compiler sees dependent types.
- Bytecode uses symbolic references; the JVM has its own linking/resolution process, so compile errors and runtime linking errors must be diagnosed differently.