# `permits` Syntax and When the Permitted List Is Inferred

In Java, `sealed` restricts which types are allowed to directly extend a class or directly implement an interface. The `permits` clause lists the permitted direct subtypes. If all subtypes are declared in the same compilation unit, Java can automatically infer this list when `permits` is omitted.

These rules are compile-time checks. They help model a hierarchy with a controlled set of branches, such as kinds of expressions, results, or events that the program knows in advance.

## 1. Explicit `permits` List

Basic syntax:

```java
sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}
```

Here, `Circle` and `Rectangle` are the two direct implementing types of `Shape`, so both appear in `permits`. `Circle` is a record and is therefore `final` by default; `Rectangle` explicitly declares `final`.

The list can contain multiple names separated by commas. The listed types must actually be direct subtypes of the sealed type. They can be placed in different source files if the package/module rules below are followed.

## 2. When Does Java Automatically Infer the List?

If the `permits` clause is omitted, the compiler looks for direct subtype declarations located in the **same compilation unit** as the sealed type. A compilation unit usually corresponds to a Java source file. For example:

```java
sealed interface Command {
    String describe();
}

record Start(String name) implements Command {
    @Override
    public String describe() {
        return "start " + name;
    }
}

record Stop() implements Command {
    @Override
    public String describe() {
        return "stop";
    }
}
```

The inferred list here is `Start` and `Stop`, because both records directly implement `Command` and are declared in the same compilation unit. Records are automatically `final`, so there is no need to write that keyword.

Inference has a clear scope: Java does not arbitrarily search all files in the package. If a subtype is in another source file, declare an explicit `permits` list. When `permits` is omitted and no direct subtype is declared in the same compilation unit, the sealed declaration is invalid.

## 3. Complete Runnable Example with Java 17+

Save the following content in the file `PermitsDemo.java`. The example demonstrates both an explicit list (`Shape`) and an inferred list (`Command`).

```java
public class PermitsDemo {
    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape rectangle = new Rectangle(3.0, 4.0);
        System.out.printf("circle area = %.2f%n", circle.area());
        System.out.printf("rectangle area = %.2f%n", rectangle.area());

        Command command = new Start("worker");
        System.out.println(command.describe());
    }
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    Circle {
        if (radius < 0) {
            throw new IllegalArgumentException("radius must be non-negative");
        }
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("dimensions must be non-negative");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}

sealed interface Command {
    String describe();
}

record Start(String name) implements Command {
    @Override
    public String describe() {
        return "start " + name;
    }
}

record Stop() implements Command {
    @Override
    public String describe() {
        return "stop";
    }
}
```

Compile and run:

```bash
javac --release 17 PermitsDemo.java
java PermitsDemo
```

Exact output:

```text
circle area = 12.57
rectangle area = 12.00
start worker
```

Note: `--release 17` instructs the compiler to generate code compatible with Java 17. A JDK that supports this option must be installed.

## 4. Mandatory Rules

- **List only direct subtypes.** If `C` implements `B`, and `B` implements `A`, then `A` only permits `B`; `C` belongs to `B`'s branch and must not be listed directly in `A`'s `permits` clause.
- **Every direct subtype must be permitted.** With an explicit list, an omitted direct subtype causes a compilation error.
- **A direct subtype must be closed or declare how it can be extended.** It must be `final`, `sealed`, or `non-sealed`. Records are `final` by default, so there is no need to write `final record`.
- **Package/module rules must be satisfied.** In an unnamed module, the sealed type and its permitted subtypes must be in the same package. In a named module, they must belong to the same module; they may reside in different packages within that module.
- **List inference relies only on the same compilation unit.** Subtypes in other files are not automatically added to the list when `permits` is omitted.
- **`permits` is used only on `sealed` declarations.** It is not a list of every class that can appear in the program, nor does it replace normal inheritance rules.

If a direct subtype is `sealed`, it can further define its own list of subtypes. If it is `non-sealed`, that branch is open for other types to extend further. If it is `final`, the branch stops at that type.

## 5. Distinguishing Direct and Indirect Subtypes

In the example below, `Expr` permits `Literal` and `Binary`. `Add` and `Multiply` are direct subtypes of `Binary`, so they belong in `Binary`'s list, not `Expr`'s.

```java
sealed interface Expr permits Literal, Binary {}

record Literal(int value) implements Expr {}

sealed interface Binary extends Expr permits Add, Multiply {}

record Add(Expr left, Expr right) implements Binary {}

record Multiply(Expr left, Expr right) implements Binary {}
```

Each record is a leaf subtype. This structure clearly shows two levels: `Expr` determines the first-level branches, while `Binary` determines the permitted binary operations.

## 6. Sealed Types with Type Parameters

For generic types, the names in `permits` are type names, and type arguments are not written in the list:

```java
sealed interface Result<T> permits Success, Failure {}

record Success<T>(T value) implements Result<T> {}

record Failure<T>(String message) implements Result<T> {}
```

`Success<T>` and `Failure<T>` directly implement `Result<T>`; the records are implicitly `final`. The list inference rule also applies to generic types if the direct subtypes are declared in the same compilation unit.

## 7. Common Errors and How to Find the Cause

| Situation | Cause and Fix |
|---|---|
| `permits` is omitted, but a subtype is in another file | Add an explicit `permits` list and list the direct subtypes. |
| A direct subtype is not in the list | Add that type to `permits`, or adjust the inheritance relationship to match the design. |
| Listing a type that does not directly extend/implement the sealed type | Fix the list so that it contains only direct subtypes. |
| A direct subtype is not `final`, `sealed`, or `non-sealed` | Choose one of these modifiers; records are already implicitly `final`. |
| Types are in the wrong package or module | Move them to the same package in an unnamed module or the same module in a named module. |
| `permits` is omitted, but there is no direct subtype in the same file | Declare at least one direct subtype in the compilation unit or use an explicit `permits` clause. |

When reading error messages, check in this order: which type declares `sealed`, which `extends`/`implements` relationships are direct, what the `permits` list currently declares, and only then check the package/module and the subtype's keyword.

## 8. Choosing an Explicit or Inferred List?

Use an explicit list when the subtypes are placed in multiple files, when you want to see the hierarchy's contract right at the declaration, or when the permitted list needs to be clearly inspected during code review.

You can omit `permits` when all direct subtypes are grouped in the same compilation unit and inference makes the code more concise. In that case, adding a new direct subtype to the same file also changes the inferred list, so consider whether this implicit change aligns with the purpose of the hierarchy.

Before finalizing a declaration, do a quick check:

1. Has the supertype been declared `sealed`?
2. Does the list contain only direct subtypes?
3. Are all direct subtypes permitted?
4. If `permits` is omitted, are all direct subtypes in the same compilation unit?
5. Is each direct subtype `final`, `sealed`, `non-sealed`, or a record?
6. Are the package/module rules satisfied?

## References

- [Java Language Specification 17: Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 17: Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
