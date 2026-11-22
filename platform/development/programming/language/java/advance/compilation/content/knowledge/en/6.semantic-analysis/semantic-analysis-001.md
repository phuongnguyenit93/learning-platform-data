# Access Control and Type Reference Validity Checking in Java

## 1. Semantic checking occurs after code is syntactically valid

A program can be written with valid Java syntax and still be rejected by the compiler. For example, the statement `new Hidden()` can be syntactically valid, yet the class `Hidden` is not present or cannot be accessed from the call site. Similarly, a variable of type `List<String>` is syntactically valid, but the declaration `List<int>` is invalid because a generic type argument must be a reference type.

During the semantic analysis phase, `javac` needs to resolve a chain of issues:

1. **Name resolution:** which declaration does the identifier `User`, `api.User`, or `List` refer to? Is the declaration within the visible scope and on the source/classpath/module path?
2. **Accessibility checking:** is the class, interface, constructor, field, or method declaration permitted to be used from the current context according to `public`, `protected`, package-private, `private`, and module boundaries?
3. **Type correctness checking:** does the reference have the right kind of type, number/bounds of generic arguments, assignment compatibility, cast compatibility, method parameter compatibility, and `static` context compatibility?
4. **Compile-time behavior selection:** which overloaded method applies, which member can be invoked, and do `null`/lambda/method reference values match the target type?

Only when the necessary conditions are satisfied does the compiler generate bytecode. **A type that can be found is not necessarily accessible; an accessible type is not necessarily used correctly with respect to type checking.**

Examples of errors with different natures:

~~~java
// Illustrates errors, not a standalone Java program.
UnknownType a;             // Cannot resolve the type name.
java.util.List<int> b;     // Generic argument cannot be a primitive.
String s = 42;             // Incompatible types.
~~~

You should not "fix" these errors by adding arbitrary casts or widening all access scopes to `public`. You need to find the exact failing step in the chain: name resolution → access checking → type checking.

## 2. Access control table: types and members

Java has four familiar access levels for **class members**. The level without an access keyword is commonly called *package-private*.

| Modifier | Same class | Same package | Subclass in different package | Non-subclass code in different package |
| --- | --- | --- | --- | --- |
| `public` | Yes | Yes | Yes | Yes, if type/module permits |
| `protected` | Yes | Yes | Yes, with specific conditions | No |
| No modifier (package-private) | Yes | Yes | No | No |
| `private` | Yes | No, except nestmate rules | No, except nestmate rules | No |

The table is a summary of **source-level access control checks**. There are accompanying details to keep in mind:

- A **top-level class/interface** can only be declared `public` or package-private; top-level `private` or `protected` declarations are not allowed.
- A **nested class/interface** can have modifiers appropriate to where it is declared; to use `Outer.Inner`, the accessibility of both `Outer` and `Inner` must be considered.
- `private` members of two nested classes in the same *nest* may access one another under Java's rules, so it cannot be oversimplified as "no other class is allowed." This is nestmate scope, and it does not mean all classes in the same package can access private members.
- `protected` in another package is **not equivalent** to "any object of the base class type is accessible"; there are additional conditions regarding the subclass and the type of the qualifier expression.
- A class being `public` is not enough when using the Java Platform Module System (JPMS): the package must also be exported and the dependent module must read the providing module.
- **The accessibility of the enclosing type** must also be valid: a public method does not make an inaccessible enclosing class accessible.

You can remember this along two axes: *which declaration is being accessed* (top-level type, nested type, constructor, field, method) and *the context performing the access* (package, subclass, qualifier, module).

## 3. Public, package-private, and private through package examples

Consider the following three illustrative declarations, each in the indicated file.

File `src/api/java/api/PublicApi.java`:

~~~java
package api;

public class PublicApi {
    private int secret = 13;
    int packageCode = 5;

    public int getSecret() {
        return secret;
    }
}
~~~

File `src/api/java/api/Helper.java`:

~~~java
package api;

class Helper {
    static String label() {
        return "internal";
    }
}
~~~

File `src/client/java/client/Client.java`:

~~~java
package client;

import api.PublicApi;

public class Client {
    public static void main(String[] args) {
        PublicApi api = new PublicApi();
        System.out.println(api.getSecret());
    }
}
~~~

The call `api.getSecret()` is valid: `PublicApi` and the method are both `public`, and `getSecret()` is allowed to read the `private` field inside its owning class. No statement in `client.Client` directly touches `secret`, `packageCode`, or `Helper`.

The lines below are **intentionally invalid**, used only for analysis, and must not be added to the files being compiled:

~~~java
// In client.Client (different package from api):
System.out.println(api.secret);       // secret is private.
System.out.println(api.packageCode);  // packageCode is package-private.
api.Helper h;                         // api.Helper is top-level package-private.
~~~

Importing a name does not grant additional access rights. `import api.Helper;` still does not allow the `client` package to use `api.Helper`. Two classes declared in the same package can access each other's package-private members under package rules, even if they reside in two different source roots; directory paths are just a way to organize source code, while **the package declaration** defines package membership in the Java language (combined with module boundaries when applicable).

For `private`, the containing class can provide a controlled public accessor instead of exposing the field. There is no need to automatically generate getters for every field; provide an API that aligns with the class's invariants.

## 4. An important case: protected across packages

`protected` allows access within the same package; outside the package, a subclass may only access a protected member under the additional conditions of the Java Language Specification.

Create the exact files below in a standalone example. Use three source directories, with outputs described using actual paths; no external libraries are needed.

### 4.1. `src/api/java/api/Parent.java`

~~~java
package api;

public class Parent {
    protected int number = 7;
    private int secret = 13;

    public int readSecret() {
        return secret;
    }
}
~~~

`Parent` is public. `number` is a protected instance field; `secret` is private. Because no constructor is explicitly declared, the class has a public default constructor matching the access level of the top-level public class.

### 4.2. `src/client/java/client/Child.java`

~~~java
package client;

import api.Parent;

public class Child extends Parent {
    public int total(Child peer) {
        return this.number + peer.number;
    }
}
~~~

`Child` is allowed to read `this.number` because it is a subclass of `Parent`. In another package, `peer.number` is also valid inside a method of `Child` because the static type of the qualifier `peer` is `Child`, an appropriate subtype.

Conversely, the following snippet **cannot compile** when placed in `Child`:

~~~java
// Invalid: illustrative definition, do not insert into the runnable class.
public int invalid(Parent other) {
    return other.number;
}
~~~

Although `Child` is a subclass, the static type of the expression `other` is still `Parent`. When accessing a `protected` instance field/method of a superclass through an expression in another package, the qualifier type must be the subclass performing the access (or an appropriate subtype of that subclass); an expression of type `Parent` does not satisfy this condition. This rule protects access through superclass objects that do not belong to the current subclass domain.

Another class in the `client` package that does **not** extend `Parent` also cannot use `child.number` merely because it is in the same package as `Child`: the package owning the declaration of `number` is `api`.

For a `protected` constructor, the access rules differ from fields/methods: in a subclass in a different package, you can call the superclass constructor via `super(...)` according to constructor invocation rules, but you must not assume that you can call `new Parent(...)` everywhere.

### 4.3. `src/client/java/client/Main.java`

~~~java
package client;

import api.Parent;

public class Main {
    public static void main(String[] args) {
        Parent parent = new Parent();
        Child child = new Child();

        System.out.println(parent.readSecret());
        System.out.println(child.total(new Child()));
    }
}
~~~

To run on Java 17+, open a terminal in the root directory containing `src/`. With Bash on Linux/macOS/Git Bash:

~~~bash
mkdir -p out/api out/client
javac --release 17 -encoding UTF-8 -d out/api src/api/java/api/Parent.java
javac --release 17 -encoding UTF-8 -cp out/api -d out/client src/client/java/client/Child.java src/client/java/client/Main.java
java -cp out/api:out/client client.Main
~~~

Exact expected stdout:

~~~text
13
14
~~~

On Windows/PowerShell, create the two output directories with the appropriate command (for example `New-Item -ItemType Directory -Force out/api, out/client`) and use `;` to separate the classpath:

~~~powershell
java -cp 'out/api;out/client' client.Main
~~~

This is an example with all classes declared, matching file/class names, and a compilation boundary separating two packages. The `javac` command produces no output on success. The error snippets noted above are **non-standalone illustrations** and are not included in the three files of the runnable example.

## 5. Access control for constructors, nested types, and interfaces

Access checks do not apply only to fields:

- **Constructor:** to execute `new T(...)`, both class `T` and an appropriate constructor must be accessible. A public class with a private constructor still cannot be instantiated from an external class in the normal way.
- **Method:** a method can be `public` or `protected`, but the receiver type, chosen overloaded method, and call context must still be valid. `import` does not open member access.
- **Nested type:** `Outer.Inner` must satisfy access rules at each level. A `private static class Inner` cannot be used directly from outside the nest, even when `Outer` is public.
- **Interface:** fields in an interface are implicitly `public static final`; nested types in an interface are implicitly `public static`; interface methods have their own modifier rules, including public abstract/default/static and private helper methods since Java 9. Do not mechanically apply the class modifier table to every interface position.
- **Top-level type:** a `public class Account` in a normal source file must be placed in `Account.java`, and a compilation unit cannot have multiple public top-level types whose names require different file names.

Example using a factory with a private constructor, a standalone Java program named `TokenDemo.java`:

~~~java
public class TokenDemo {
    public static void main(String[] args) {
        Token token = Token.of("abc");
        System.out.println(token.value());
    }
}

final class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        return new Token(value);
    }

    public String value() {
        return value;
    }
}
~~~

Run:

~~~bash
javac --release 17 TokenDemo.java
java TokenDemo
~~~

Stdout:

~~~text
abc
~~~

`TokenDemo` can access the top-level package-private class `Token` because both are in the unnamed package of the same source file, and it can call the public static factory. However, if you replace `Token.of("abc")` with `new Token("abc")` in `TokenDemo`, `javac` rejects it because the constructor of `Token` is private. The existence of a public method does not make a private constructor public.

Note that the default-package example is only suitable for learning with a single file. In real project code, you should declare packages explicitly.

## 6. Type name resolution: simple names, qualified names, scope, and imports

When seeing `List`, `Outer.Inner`, or `api.PublicApi`, the compiler must know that they refer to exactly one valid declaration. Distinguish between:

- **Qualified name:** `java.util.List` explicitly specifies the package and type name, helping avoid name collisions in code.
- **Single-type import:** `import java.util.List;` allows using the simple name `List` when there is no conflict under Java's rules.
- **Import-on-demand:** `import java.util.*;` makes eligible public types available for consideration; it does **not** import any subpackages such as `java.util.concurrent`.
- **Member/nested type import:** `import java.util.Map.Entry;` allows using `Entry` directly if valid; static imports are used for static members or static nested types with their own syntax.
- **Scope and shadowing:** a type variable, local class, member type, or same-package type can change what a simple name resolves to. Importing two types with conflicting simple names can cause an ambiguity error.
- **Missing / not on the lookup path:** a missing dependency on the classpath/module path or an incorrect source root leads to symbol/package errors, even when the identifier is spelled correctly.

Illustrative ambiguity example:

~~~java
// Invalid if the name List is not uniquely resolved.
import java.awt.*;
import java.util.*;

class Ambiguous {
    List names;
}
~~~

Both `java.awt.List` and `java.util.List` can be considered when using import-on-demand, so the name `List` is ambiguous. Resolve this with `import java.util.List;` or by using the fully qualified `java.util.List`. **Adding an import does not bypass access modifiers**: if a type is blocked due to private/package-private/module exports, you must fix the usage or the API.

A type name can also lie outside the **scope** of a type parameter: for example, `T` declared on a generic method only exists within that declaration's scope and cannot be used arbitrarily in another method.

## 7. Validity of type references: generic arguments and bounds

A valid type name cannot necessarily be used with arbitrary type arguments. Java checks *arity* (number of type parameters), *bounds*, and whether a parameterized type can be formed.

Valid example:

~~~java
import java.util.List;

public class GenericDemo {
    static <T extends Number> T first(List<T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 5);
        Number firstNumber = first(numbers);
        System.out.println(firstNumber);
    }
}
~~~

Save the file `GenericDemo.java` and run:

~~~bash
javac --release 17 GenericDemo.java
java GenericDemo
~~~

Stdout:

~~~text
4
~~~

`List<Integer>` is valid because `List` takes one type argument, `Integer` is a reference type, and `Integer` satisfies the bound `T extends Number` of method `first`. The return value is assigned to `Number` through the subtype relationship.

The following snippets are intentionally **invalid** (illustrative, do not add to the runnable `GenericDemo.java`):

~~~java
java.util.List<int> values;           // int is a primitive, not a type argument.
java.util.Map<String> index;          // Map requires two type arguments.
java.util.List<String> words = java.util.List.of("a");
Number n = first(words);              // T must extend Number; String does not satisfy this.
java.util.List<String> names = java.util.List.of(1); // Incompatible element type.
~~~

Autoboxing supports passing primitive values in appropriate contexts (for instance, `List.of(1)` infers `Integer`), but **does not** make `List<int>` a valid declaration. Java generics are invariant with respect to type arguments: `List<Integer>` is not a subtype of `List<Number>`, even though `Integer` is a subtype of `Number`.

Wildcards also have usage restrictions:

~~~java
java.util.List<? extends Number> readable = java.util.List.of(1, 2);
Number firstValue = readable.get(0);       // Valid.
~~~

With `List<? extends Number>`, you cannot arbitrarily add an `Integer` to the list: the actual element type could be another subtype of `Number`. Use `List<? super Integer>` when you need to add `Integer` in a consumer role. This is a **compile-time type safety check**, not an access control check.

Type references must also respect generic limitations at runtime; for example, `new java.util.ArrayList<String>[2]` is prohibited due to generic array creation, and `instanceof java.util.List<String>` is invalid because that parameterized type is not reifiable to allow such a check. `instanceof java.util.List<?>` is a usable form of check.

## 8. Compatibility in assignments, method calls, and casts

Semantic analysis does not stop at accessibility:

- **Assignment:** is the right-hand expression assignment-compatible with the left-hand type? `Object obj = "text";` is valid; `String text = new Object();` is invalid.
- **Method parameters:** are the argument types compatible with the selected method? For example, `Integer.parseInt("12")` is valid, whereas `Integer.parseInt(12)` does not match the overload taking a String.
- **Overloads:** the compiler determines applicable methods and selects the most specific method according to the rules; there are cases where multiple overloads are equally applicable, causing ambiguity, such as calling `m(null)` when both `m(String)` and `m(Integer)` exist.
- **Casts:** a cast is only accepted when the language permits the type conversion under the corresponding rules. A cast that compiles **does not guarantee** the conversion will succeed at runtime; a `ClassCastException` may occur.
- **Generic types:** the compiler checks bounds, inference, wildcard capture, and unchecked conversions. Raw types may only produce a warning instead of an error, but lose part of the type guarantees.
- **Context:** an instance member cannot be referenced as a static member from a static context lacking an instance; `new` cannot instantiate an abstract class/interface directly; `void` cannot be the type of a variable.

Valid example in the file `TypeCheckDemo.java`:

~~~java
public class TypeCheckDemo {
    static String twice(String value) {
        return value + value;
    }

    public static void main(String[] args) {
        Object value = "java";
        String text = (String) value;
        System.out.println(twice(text));
    }
}
~~~

Run:

~~~bash
javac --release 17 TypeCheckDemo.java
java TypeCheckDemo
~~~

Stdout:

~~~text
javajava
~~~

If `value` is actually an `Integer`, casting to `String` in an equivalent example can **compile** because the static type `Object` allows a runtime type check, yet it will throw `ClassCastException`. That differs from the case where the compiler proves two types are unrelated and forbids the conversion.

## 9. JPMS adds readability and exports checks

In applications without a named module (unnamed module/classpath), many people are used to thinking "if a class in a JAR is public, other classes can use it." With the Java Platform Module System since Java 9, the **module graph** must also be checked.

When a named module wants to use a public type in another module, typically:

1. The consuming module must **read** the providing module; for example, declaring `requires api.module;` in `module-info.java`.
2. The package containing the public type must be **exported** by the providing module to the consuming module: `exports api;` or a qualified export `exports api to client.module;`.
3. The type/member itself must still be accessible according to Java modifiers.

`opens` is a mechanism serving deep reflection in the module system; merely `opens`-ing a package is not equivalent to `exports` for normal Java access at compile time.

Standalone example, laid out as follows:

~~~text
modulesrc/
├── api.module/
│   ├── module-info.java
│   └── api/Message.java
└── client.module/
    ├── module-info.java
    └── client/Main.java
~~~

File `modulesrc/api.module/module-info.java`:

~~~java
module api.module {
    exports api;
}
~~~

File `modulesrc/api.module/api/Message.java`:

~~~java
package api;

public final class Message {
    public static String text() {
        return "MODULE OK";
    }
}
~~~

File `modulesrc/client.module/module-info.java`:

~~~java
module client.module {
    requires api.module;
}
~~~

File `modulesrc/client.module/client/Main.java`:

~~~java
package client;

import api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

On Bash from the directory containing `modulesrc/`:

~~~bash
mkdir -p out/modules
javac --release 17 --module-source-path modulesrc -d out/modules -m api.module,client.module
java --module-path out/modules -m client.module/client.Main
~~~

Stdout:

~~~text
MODULE OK
~~~

If you remove `exports api;` while keeping `requires api.module;`, package `api` cannot be accessed by the client module from Java source code; the public modifier of `Message` does not break through the module boundary on its own. If you remove `requires api.module;`, the client module lacks readability even if the API module exports the package. These are two different errors. With options like `--add-reads` or `--add-exports`, the compiler/runtime can extend relationships in a specific environment, but standard modular code should declare the exact contract via `module-info.java`.

## 10. Error diagnosis: categorize rather than reading a single error string

`javac` messages can vary depending on the JDK and error location. Identify the error category rather than relying on always receiving the exact same wording.

| Symptom | Common semantic meaning | What to check |
| --- | --- | --- |
| `cannot find symbol` | Cannot resolve declaration name | Spelling, package, import, source/class/module path, scope |
| `package ... does not exist` | Cannot find package on the compile path | Dependencies, source roots, and module configuration |
| `... is not public ...; cannot be accessed from outside package` | Package-private type or member referenced from the wrong package | Does the API really need to be public, or is the caller in the wrong place? |
| `... has private access` | Caller accesses a private member/constructor | Use an appropriate public API or redesign the scope |
| `... has protected access` | Caller fails protected access rules | Declaring package, subclass, qualifier type |
| `incompatible types` | Assignment/cast/argument has the wrong type | Expected type and actual type, generic arguments |
| `type argument ... is not within bounds` | Generic bound is violated | `extends` declaration, concrete type passed in |
| `wrong number of type arguments` | Incorrect generic arity | Number of type parameters in the declaration |
| `reference to ... is ambiguous` | Multiple matching overloads/names cannot be disambiguated | Imports, overload declarations, static type of arguments |
| `non-static ... cannot be referenced from a static context` | Using an instance member without an appropriate instance | Create/receive an instance, or fix the static design |
| `package ... is not visible` in named modules | Module is not read or package is not exported | `requires` and `exports` in module-info |

Not every access error has the same message; the compiler may report the error at the `import` line, at a type in a signature, at `new`, or at a call. An initial dependency error can also cascade into many other symbol errors. Fix the root error first and rebuild.

A practical investigation workflow:

1. Identify the **fully qualified name** of the type to use and where it is declared, including package/module.
2. Check whether the compiler found the definition: is the source file in the source set or is the class/JAR on the compile classpath/module path?
3. If found, determine the **access context**: which package is the calling class in, what is it a subclass of, what is the static type of the qualifier, and does the module read/export properly?
4. Check the types of each **receiver, argument, return, generic bound, cast**, and `static`/constructor constraints.
5. Re-run compilation into a clean output directory to eliminate stale `.class` files; if needed, use `javac -verbose` to see where the compiler loads files/classes from. Verbose output is JDK-dependent and has no fixed stdout.

## 11. Common misconceptions that lead to "fixing the wrong place"

**Misconception 1 — `import` grants access rights.** Import only helps reference a name; access control is determined by modifiers and the module system. You cannot import a top-level package-private class from another package to make it public.

**Misconception 2 — Any subclass can touch protected fields of any base class instance.** For protected instance members in another package, the qualifier type is restricted. `Child` can use `this.number` or `peer.number` when `peer` is `Child`; it cannot read `other.number` when `other` is `Parent` as in the example.

**Misconception 3 — Making everything public will "cure" type checking issues.** Access rights and type compatibility are separate conditions. A public `List` still does not accept `List<int>` or `Map<String>`.

**Misconception 4 — `ClassCastException` is a compiler error.** The compiler blocks conversions that are invalid in the language, but a statically permitted cast may still fail at runtime; you need to check the actual type when casting.

**Misconception 5 — Passing the compiler means the API can be used across any module.** Named modules require readability and exports. A public API in an unexported package is still blocked when compiling a client module.

**Misconception 6 — A public member can be accessed through any containing type.** Before checking the member, you must check the containing type, enclosing types, package/module, and only then the member's modifier and the call's correctness.

**Misconception 7 — Unchecked warnings are the same as compile errors.** Using a raw generic type may only report a warning. You should not suppress warnings to hide risks, nor claim that every raw conversion is rejected by the compiler.

## 12. Knowledge self-check checklist

For a reference `x.method(arg)`, `new T(...)`, `Outer.Inner`, or `List<T>`, answer in order:

- Which declaration does the type/member name resolve to? Do imports, package, and scope cause confusion or ambiguity?
- Is the containing type accessible? Is a top-level type package-private? Does a nested type have its own modifier?
- Is the member/constructor accessible from the call site? For cross-package protected access, does the qualifier have a valid static type?
- If JPMS is used, does the client module have readability and does the provider package have the appropriate export?
- Do type arguments have the right arity, reference type, and bounds? Are generic inference/wildcards compatible?
- Does the expression match the required type in assignments, overloaded calls, returns, or casts?
- Is the program using an instance member in a context that has an appropriate instance?
- Are the required classes/JARs actually on the compilation path, and is the result reproducible from a clean output directory?

**Practice exercise:** compile the `Parent`/`Child`/`Main` example in section 4; record stdout `13` and `14`. Try adding the `invalid(Parent other)` method to `Child` to observe the protected access error, then remove that method. Next, try `java.util.List<int>` in a test file and compare the generic error with the access error. Finally, using the named modules example, remove `exports api;` to observe the module visibility error. Change only **one cause** per trial to help clearly distinguish between an unresolved symbol, blocked access, and an invalid type reference.