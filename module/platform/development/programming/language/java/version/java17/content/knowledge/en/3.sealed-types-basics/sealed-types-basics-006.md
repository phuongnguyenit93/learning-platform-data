# Inferring `permits` When Subtypes Are in the Same Source File in Java 17

## 1. The problem: how does `sealed` control subtypes?

In Java 17, `sealed class` and `sealed interface` let a supertype **restrict precisely which types may directly inherit or implement it**. Typically, you will see a declaration with `permits`:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

`Result` permits only `Success` and `Failure` as **direct subtypes**. Any other class arbitrarily writing `implements Result` will not be accepted.

However, when the two subtypes are declared **in the same source file** as `Result`, Java 17 allows omitting the `permits Success, Failure` clause altogether:

~~~java
sealed interface Result {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

Both ways of writing this carry the exact same meaning for the list of direct subtypes in the example above. In the second form, the compiler **automatically infers `permits` from the direct subtype declarations located in the same compilation unit** (in typical cases, a single `.java` file). This is an official, standard feature in Java 17; you do not need to enable preview features.

> **Key point:** Omitting `permits` does not mean anyone is allowed to extend the `sealed` type. It simply shifts listing the direct subtypes from the developer to the compiler, based on eligible declarations **in the same source file**.

## 2. Rules for inferring `permits`

Suppose a `sealed` type does not declare `permits`. Java 17 determines the permitted set as follows:

1. Search for **valid named class or interface declarations** in the same compilation unit as the `sealed` type.
2. Select those that **directly** use `extends` or `implements` to inherit/implement that `sealed` type.
3. The resulting set becomes the list of permitted direct subtypes (*permitted direct subclasses/subinterfaces*).
4. If no direct subtypes can be found to infer, declaring `sealed` without `permits` causes a **compile-time error**.

For a `sealed class`, the compiler inspects classes whose **direct superclass** is the `sealed` class. For a `sealed interface`, the compiler inspects classes/records and interfaces that include that `sealed` type in their **direct superinterfaces** list. Eligible top-level declarations and member types (*member types*) can both participate in inference.

| Case | Automatically inferred into `permits`? | Reason |
|---|---|---|
| `final class B extends A` in the same file as `sealed class A` | Yes | `B` directly inherits from `A`. |
| `record R(...) implements I` in the same file as `sealed interface I` | Yes | `R` directly implements `I`; records are implicitly `final`. |
| `non-sealed interface J extends I` in the same file as `sealed interface I` | Yes | `J` is a direct subinterface of `I`. |
| `class C extends B`, where `B extends A` | Not part of `A`'s `permits` | `C` is only an **indirect** subtype of `A`. |
| `class D` in the same file without `extends/implements A` | No | Merely being in the same file is not enough. |
| `class B extends A` in a separate file `B.java` | Not inferred | Same compilation unit condition is not met, even in the same folder or package. |
| Local class inside a method or anonymous class | No | Has no canonical name to serve as a permitted subtype. |

In addition to being in the permitted set, every direct subtype must specify how its inheritance branch continues:

- `final`: disallows further subclasses.
- `sealed`: continues controlling the direct subtypes of that branch.
- `non-sealed`: reopens the branch for further subclasses/subinterfaces under standard Java rules.

**Common syntax exception:** `record` is implicitly `final`, so you neither need nor can write `final` before `record`. Examples in this lesson use records to represent immutable results.

## 3. Runnable example: two `record` types in the same file as a `sealed interface`

Create the project folder and `src/demo/Demo.java` as follows:

~~~text
sealed-inference/
└── src/
    └── demo/
        └── Demo.java
~~~

**Entire** contents of `src/demo/Demo.java`:

~~~java
package demo;

public class Demo {
    public static void main(String[] args) {
        Result first = new Success("saved");
        Result second = new Failure("disk is full");

        System.out.println(describe(first));
        System.out.println(describe(second));
    }

    private static String describe(Result result) {
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.reason();
        }
        throw new IllegalStateException("Unknown result");
    }
}

// No need to write: permits Success, Failure
sealed interface Result {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

### What gets inferred?

In `Demo.java`, the three declarations `Result`, `Success`, and `Failure` belong to the **same compilation unit**. `Success` and `Failure` both declare `implements Result` directly. Therefore, the compiler treats the permitted list as equivalent to:

~~~java
sealed interface Result permits Success, Failure {
}
~~~

The `permits` snippet above only illustrates the equivalence; **do not add it** to the original example. `Demo` in the same file is not included in the permitted set because `Demo` does not implement `Result`.

Both records still have to write `implements Result`: `permits` inference **does not create** inheritance relationships automatically. The compiler only reads declared inheritance relationships. The fact that records are implicitly `final` satisfies the requirement for direct subtypes of a `sealed` type.

The `describe` method uses **pattern matching for `instanceof`**, a feature standard since before Java 17. This lesson avoids pattern matching for `switch` because that feature is still in preview in Java 17.

### Compiling and running from the command line

From the `sealed-inference` root directory, create `src/demo`, then save `Demo.java` at the path above.

On PowerShell (Windows), you can create the directory with:

~~~powershell
New-Item -ItemType Directory -Force -Path src/demo | Out-Null
~~~

On Bash/Zsh (Linux/macOS):

~~~bash
mkdir -p src/demo
~~~

After saving the source code, use the exact same commands on both platforms:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Demo.java
java -cp out demo.Demo
~~~

Output:

~~~text
Success: saved
Failure: disk is full
~~~

`javac` compiles all top-level types declared in `Demo.java`; besides `Demo.class`, `out/demo` also contains `Result.class`, `Success.class`, and `Failure.class`. Even though there is only one `.java` file, there are **multiple Java types**, which produce multiple `.class` files.

The file is named `Demo.java` because `Demo` is the only `public` top-level type. The remaining types have no `public` modifier and are package-private. In practice, grouping them like this works well when a small family of types serves only code in the same package.

## 4. Inference with `sealed class`: distinguishing direct and indirect subtypes

The inference rule also applies to **`sealed` classes**, not just interfaces. Consider a standalone `Vehicle.java` file:

~~~java
public sealed abstract class Vehicle {
}

final class Bicycle extends Vehicle {
}

non-sealed class MotorVehicle extends Vehicle {
}

final class Taxi extends MotorVehicle {
}
~~~

Even though all four classes are in the same file, the inferred list for `Vehicle` is only:

~~~java
public sealed abstract class Vehicle permits Bicycle, MotorVehicle {
}
~~~

Relationship diagram:

~~~text
Vehicle (sealed)
├── Bicycle (final)           [direct, inferred]
└── MotorVehicle (non-sealed) [direct, inferred]
    └── Taxi (final)          [indirect, not in Vehicle's permits]
~~~

`Taxi` is not in `Vehicle`'s `permits` because it inherits from `MotorVehicle`, **not directly `extends Vehicle`**. Declaring `MotorVehicle` as `non-sealed` opens this branch for further subtypes. The `sealed` rule governs **direct inheritance edges**; it does not necessarily seal the entire inheritance tree at every depth.

If `MotorVehicle` were changed to a `sealed` class, that class itself would need its own list of permitted subtypes, either explicit or inferred under the same-file rule. Conversely, when using `final`, no subclasses of the `final` class can be declared.

## 5. Nested types can also be inferred

"Same source file" does not only mean placing multiple top-level types one after another. **Member types** declared inside a `sealed` type also belong to the same compilation unit. Example `Outcome.java`:

~~~java
public sealed interface Outcome {
    record Ok(int value) implements Outcome {
    }

    record Error(String message) implements Outcome {
    }
}
~~~

This is a valid `sealed interface`, equivalent to declaring:

~~~java
public sealed interface Outcome permits Outcome.Ok, Outcome.Error {
    record Ok(int value) implements Outcome {
    }

    record Error(String message) implements Outcome {
    }
}
~~~

`Outcome.Ok` and `Outcome.Error` are **member records** with canonical names (*canonical name*) that directly `implements Outcome`, so they can be inferred. In Java, member types declared inside an interface are implicitly `public static`; callers can construct them with:

~~~java
Outcome result = new Outcome.Ok(42);
~~~

Nesting records inside an interface keeps a small family of results right next to the contract definition. If subtypes grow into a large public API with many components or need independent maintenance, splitting them into separate files and declaring `permits` explicitly is usually easier to manage.

**Important limitation:** Inference does not apply to *local classes* inside method bodies or *anonymous classes*, because neither has a canonical name. Use named top-level types or member types when designing a `sealed` family.

## 6. What changes when moving a subtype to another file

This is one of the easiest pitfalls to hit. Suppose `Result`, `Success`, and `Failure` initially lived together in `Demo.java` and compiled cleanly. Later, you reorganize the code into:

~~~text
src/demo/
├── Result.java
├── Success.java
└── Failure.java
~~~

If `Result.java` still reads:

~~~java
package demo;

public sealed interface Result {
}
~~~

while `Success.java` contains:

~~~java
package demo;

public record Success(String value) implements Result {
}
~~~

and `Failure.java` contains:

~~~java
package demo;

public record Failure(String reason) implements Result {
}
~~~

then **you can no longer rely on `permits` inference**. `Success` and `Failure` reside in different compilation units from `Result`, even though all three files share package `demo`. The compiler will report errors about the `sealed` type having no inferred permitted subclasses and/or types directly implementing it without being permitted.

To fix it, declare it explicitly in **`Result.java`**:

~~~java
package demo;

public sealed interface Result permits Success, Failure {
}
~~~

Keep `Success.java` and `Failure.java` as shown above. You can compile the files with:

~~~text
javac --release 17 -encoding UTF-8 -d out src/demo/Result.java src/demo/Success.java src/demo/Failure.java
~~~

Now, `permits` explicitly names the permitted subtypes even though the types are in **different source files**. If you add `record Pending() implements Result` in a fourth file, you must also add `Pending` to `permits`. Once `permits` is written explicitly, the compiler **will not automatically infer additional subtypes**, even if they are in the same file.

### Are same package, same module, and same file the same thing?

No. They are three distinct scopes:

| Concept | Description | Sufficient to infer `permits` when omitted? |
|---|---|---|
| Same package | Multiple types declaring `package demo;`. | **No**, if they are in different `.java` files. |
| Same named module | Multiple packages/files belonging to one module. | **No**, if in different compilation units. |
| Same compilation unit | Type declarations in a single compilation unit, usually one `.java` file. | **Yes**, when also satisfying direct subtype and canonical name rules. |

When using explicit `permits`, permitted direct subtypes must still satisfy Java 17's organizational constraints: if the `sealed` type belongs to a **named module**, permitted types must belong to the **same module**; if it belongs to an **unnamed module**, they must belong to the **same package**. This rule is independent of whether `permits` can be omitted.

## 7. Common conceptual and compilation errors

### 7.1. Forgetting `final`, `sealed`, or `non-sealed` on a subtype

~~~java
sealed class Animal {
}

class Dog extends Animal {
}
~~~

`Dog` is in the same file and is a direct subclass, so it can be inferred into the permitted set. However, **it still fails to compile** because `Dog` does not specify how its inheritance branch is controlled. Fix it to `final class Dog extends Animal`, or choose `sealed`/`non-sealed` to match the design.

With a `record` like `record Dog(String name) implements AnimalView` (where `AnimalView` is a `sealed interface`), the record itself is already implicitly `final`, so no extra modifier is needed.

### 7.2. Having no direct subtypes in the same file

~~~java
sealed interface EmptyResult {
}
~~~

This declaration has no `permits` and no subtypes to infer, so it is invalid. A `sealed` type must identify at least one permitted direct subtype, via explicit `permits` or inference.

### 7.3. Having a type in the same file that does not directly inherit

~~~java
sealed interface Response {
}

final class Helper {
}
~~~

`Helper` does not `implements Response`, so it is not inferred. Simply "being in the same file" does not create a subtype relationship. The example still fails because `Response` has no permitted direct subtypes.

### 7.4. Confusing indirect subtypes with direct subtypes

~~~java
sealed class Base {
}

non-sealed class Child extends Base {
}

final class Grandchild extends Child {
}
~~~

`Base` only infers `Child`; `Grandchild` is an indirect subtype. You neither need to nor may add `Grandchild` to `Base`'s `permits` because `Grandchild` does not directly `extends Base`.

### 7.5. Assuming omitting `permits` allows extension from another file

~~~java
// File Base.java
public sealed class Base {
}

// File External.java
public final class External extends Base {
}
~~~

This snippet shows two **separate files**; the compiler does not infer `External` as a valid subtype of `Base`. To split two classes into separate files, declare `public sealed class Base permits External` (and satisfy the package/module constraints). Even when there is only one subtype, `permits` is required if that subtype is in another file.

### 7.6. Duplicate or invalid entries in `permits`

When writing `permits` explicitly, each type name may appear only once and must be an accessible **direct** subtype. For instance, if `C extends B` and `B extends A`, `sealed class A permits B, C` is invalid for `C`. Writing `permits` also requires the supertype to actually have the `sealed` modifier.

### 7.7. Misunderstanding what is stored in `.class` files

`permits` inference is a **compile-time source-code** rule. After compilation, the subtype restriction is stored in bytecode metadata, specifically the `PermittedSubclasses` attribute. The JVM enforces that restriction when loading/linking classes; it is not merely a source-only convention.

You can inspect the compiled type's metadata with the JDK's `javap` tool, for example:

~~~text
javap -v -classpath out demo.Result
~~~

In the verbose output, look for the `PermittedSubclasses` attribute to see the restriction recorded by the compiler. Not seeing the word `permits` in the `.java` file does **not** remove this restriction.

## 8. When should you rely on inference vs. write `permits`?

**Rely on inference** when a type family is small, subtypes are defined right next to each other in the same file, and adding a direct subtype is a localized, deliberate change. Good examples include:

- A `sealed interface` modeling two or three outcomes, each a small record.
- Member records inside a single `sealed interface`.
- A `sealed` class and a few small sub-branches maintained in the same file.

**Write `permits` explicitly** when subtypes are split across multiple files, when building a more complex API structure, or when you want readers to see the list of subtypes right on the parent declaration. Remember that automatic inference depends on **source-file placement**, so moving a subtype to a new file requires updating `permits`.

| Comparison point | Omitting `permits` (inferred) | Writing `permits` explicitly |
|---|---|---|
| Source of permitted list | Valid named direct subtypes in the **same compilation unit**. | Names listed in the `permits` clause. |
| Adding a subtype in the same file | Automatically included in the permitted set if eligible. | Must update the `permits` list. |
| Moving a subtype to another file | No longer inferred; must declare explicitly. | Remains valid if module/package rules are satisfied. |
| Subtype modifier requirement | Still requires `final`, `sealed`, or `non-sealed` as applicable; records are implicitly `final`. | Identical. |
| Runtime meaning | Still a `sealed` type with a permitted subtype set. | Identical. |

## 9. Practice exercises

**Exercise 1 — Predict the inferred set**

Consider these declarations in the same `Status.java` file:

~~~java
sealed interface Status {
}

record Active(int code) implements Status {
}

record Disabled(String reason) implements Status {
}

final class Printer {
}
~~~

Determine the equivalent `permits` list for `Status`. Explain why `Printer` does not appear.

**Exercise 2 — Identify the error when splitting files**

Move `Active` into `Active.java` in the same package as `Status.java`, keeping `Disabled` alongside `Status`. If `Status` still reads `sealed interface Status {}`, what happens when compiling `Active.java`? How must `Status`'s declaration change to accept both subtypes?

**Exercise 3 — Find direct subtypes**

~~~java
sealed class Document {
}

final class TextDocument extends Document {
}

non-sealed class MediaDocument extends Document {
}

final class ImageDocument extends MediaDocument {
}
~~~

Draw the inheritance tree, list the inferred `permits` of `Document`, and explain whether an `AudioDocument extends MediaDocument` can be added.

**Exercise 4 — Design nested types**

Create a `sealed interface ApiResponse` with two member records `Ok(String data)` and `Error(int code, String message)` in the same `ApiResponse.java` file. Do not write `permits`; instantiate both types as `ApiResponse.Ok` and `ApiResponse.Error` from a runner class.

### Self-check hints

- Exercise 1: The direct set is `Active` and `Disabled`. `Printer` does not `implements Status`.
- Exercise 2: `Active` is in a different compilation unit so it is not inferred; `Status` must declare `permits Active, Disabled`, even though `Disabled` remains in the same file.
- Exercise 3: `Document`'s set contains only `TextDocument` and `MediaDocument`. `ImageDocument` is an indirect subtype. Because `MediaDocument` is `non-sealed`, `AudioDocument extends MediaDocument` can be created.
- Exercise 4: Both member records have canonical names and directly implement `ApiResponse`, so they are inferred; records are implicitly `final`.

## 10. Rule to remember

An accurate rule of thumb for Java 17:

> **`sealed` without `permits` → takes *direct* subtypes, with a *canonical name*, declared in the *same compilation unit*.** Direct subtypes must still declare an appropriate `final`, `sealed`, or `non-sealed` modifier.

The three conditions—**same file, direct inheritance relationship, and valid named type**—form the core of inference. Whether the list is written manually or inferred by the compiler, `sealed` still restricts which types can directly extend the contract.

### References

- [Java SE 17 Language Specification — Section 8.1.6: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [Java SE 17 Language Specification — Section 9.1.4: Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
- [Oracle Java 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html).
