# Access Scope of Nested Types and How to Reference Them in Java

A **nested type** is a type declared inside another type, such as a class, interface, enum, or record located within a class. Nested declarations help group closely related types, control where they can be used, and clearly show which type belongs to the enclosing type.

To use nested types properly, you need to distinguish between two questions: **where the type is visible** (scope and access rights) and **what syntax is used to create an object or refer to the type** (referencing a static nested type or a nested type tied to an outer object).

## 1. Kinds of Nested Types

Java provides several ways to declare a type inside another type or block:

- **Member nested class:** a class declared directly inside another class or type. It can be `static` or non-static (inner class).
- **Local class:** a class declared inside the body of a method, constructor, or block. The type name is in scope only from the declaration point to the end of its enclosing block.
- **Anonymous class:** an unnamed class declared and instantiated in a single expression; commonly used to implement an interface or extend a class inline.
- **Nested interface, enum, and record:** these types can be declared inside another type. Nested interfaces, enums, and records are semantically static nested types, so no object of the enclosing type is needed to create or reference that type.

Not every type declared inside a class requires an instance of the outer class. The most important distinction is between a `static` member class and a non-static member class.

## 2. Access Scope of Member Nested Types

For a nested type declared directly inside another type, you can use the `public`, `protected`, package-private (no modifier specified), or `private` access levels. These modifiers control where other code is allowed to reference the **nested type name**.

| Modifier | Typical Usage Scope |
| --- | --- |
| `public` | Can be referenced from places where the enclosing type and the nested type are visible. |
| `protected` | Within the same package; outside the package according to `protected` access rules, typically through inheritance. |
| No modifier specified | Within the same package only. |
| `private` | Within the scope of the enclosing type that declares that nested type. |

Declaration example:

```java
public class Library {
    public static class PublicEntry { }
    protected static class ProtectedEntry { }
    static class PackageEntry { }
    private static class PrivateEntry { }
}
```

External classes can reference `Library.PublicEntry` when other access conditions are also met. `Library.PrivateEntry` can only be used within the scope of `Library`; the fact that an external class holds a `Library` object does not give it access to the private type.

A top-level type can only be declared `public` or package-private; `private` and `protected` are not valid for a top-level class/interface. Local classes and anonymous classes also do not declare these access modifiers.

## 3. How Do a `static` Nested Class and an Inner Class Differ?

### `static` Nested Class

A `static` nested class is associated with the enclosing type name, not with a specific instance of that type. When creating it, you do not need to create an enclosing object first.

```java
Library.Helper helper = new Library.Helper();
```

The example above applies if `Helper` is a nested class with appropriate access rights and a constructor that can be called from the location where the code is written. From inside `Library`, you can usually use the short name `Helper` if there is no other name causing ambiguity.

A `static` nested class has no implicit reference to an enclosing object. Therefore, it cannot directly use the instance fields or methods of `Library` as if they belonged to itself. If instance data is needed, pass the object in via a constructor or method:

```java
Library.Helper helper = new Library.Helper(library);
```

This illustrative constructor and signature must be declared accordingly in `Helper`. A static nested class can still access `private` members of the enclosing type when it has an appropriate object reference; `private` controls access under the language rules and does not require being the same object.

### Non-static Member Class (Inner Class)

An inner class is tied to a specific instance of the enclosing type. To create it from outside the instance scope of the enclosing type, you first need an enclosing object and then use the `outer.new InnerType()` syntax.

```java
Library library = new Library();
Library.Worker worker = library.new Worker();
```

This snippet applies if `Worker` is an accessible member inner class and an appropriate constructor can be called from that location. Each `Worker` object created this way is associated with the specific `library` instance.

Inside an inner class, you can directly use the instance fields and methods of the enclosing object. When you need to explicitly specify that object, use `Library.this` (the enclosing type name from the example) to obtain a reference to the enclosing instance.

```java
System.out.println(Library.this.toString());
```

`Outer.this` can only be used within an appropriate inner class context of `Outer`; it cannot be used in a static nested class, a static method, or code without a corresponding enclosing instance.

## 4. Accessing `private` Members Between Enclosing and Nested Types

A nested type can access the `private` members of its enclosing type. Conversely, the enclosing type can also access the `private` members of its nested type. This is access among types belonging to the same nest, supported by Java under the language rules.

This does not make private members public. Unrelated external code is still not permitted to access them directly. Furthermore, access rights and instance availability are two separate issues:

- A `static` nested class can read `Outer.privateStatic` directly within valid scope.
- To use `Outer.privateInstance` from a static nested class, you must have an appropriate `Outer` reference, for example `outer.privateInstance`.
- An inner class can access the instance fields or methods of the enclosing object it is associated with.
- `private` on the nested type itself still restricts where else that type name can be written, even if the type's constructor or members have a broader modifier.

## 5. Local Classes and Anonymous Classes

### Local Class

A local class is declared inside a block and can only be used within that block after its declaration point. It does not have access modifiers such as `public` or `private` because its scope is already defined by the block.

A local class can access local variables and parameters of the enclosing block if they are `final` or **effectively final** (their value is not reassigned after initialization). If declared inside an instance method, it can also access instance members of the enclosing object.

```java
void printPrefix(String prefix) {
    class Printer {
        void print(String value) {
            System.out.println(prefix + value);
        }
    }
    new Printer().print("Java");
}
```

In the example, `prefix` is read but not reassigned, so it is effectively final. If you try to reassign `prefix` after using it in `Printer`, the code will not compile.

### Anonymous Class

An anonymous class has no name with which to declare a variable of that specific class type. An anonymous class expression simultaneously creates an instance, typically via an interface or a superclass:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
task.run();
```

You cannot declare a named constructor for an anonymous class because it has no class name. New methods defined only in the body of the anonymous class also cannot be called through a variable of type `Runnable` without a type or interface declaring them.

## 6. Complete Java Example

The program below shows a static nested class receiving a reference to the enclosing object, an inner class accessing the enclosing instance, along with a local class and an anonymous class used within method scope.

```java
public class NestedTypeAccessDemo {
    private final String name;
    private int visits;
    private static final String APPLICATION = "AccessDemo";

    public NestedTypeAccessDemo(String name) {
        this.name = name;
    }

    private void mark(String from) {
        visits++;
        System.out.println(from + " -> " + name + ", visits=" + visits);
    }

    private static class StaticNested {
        void show(NestedTypeAccessDemo outer) {
            System.out.println("static -> " + outer.name);
            outer.mark("static");
            System.out.println("app -> " + APPLICATION);
        }
    }

    private class Inner {
        void show() {
            System.out.println("inner -> " + name + " / " + NestedTypeAccessDemo.this.name);
            mark("inner");
        }
    }

    private void demonstrateScopedTypes() {
        class Local {
            void show() {
                System.out.println("local -> " + name);
            }
        }
        new Local().show();

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous -> " + name);
            }
        };
        anonymous.run();
    }

    public static void main(String[] args) {
        NestedTypeAccessDemo outer = new NestedTypeAccessDemo("Ada");

        StaticNested nested = new StaticNested();
        nested.show(outer);

        Inner inner = outer.new Inner();
        inner.show();

        outer.demonstrateScopedTypes();
    }
}
```

Save the code to `NestedTypeAccessDemo.java`, then compile and run it using JDK 17 or later:

```bash
javac NestedTypeAccessDemo.java
java NestedTypeAccessDemo
```

Exact stdout:

```text
static -> Ada
static -> Ada, visits=1
app -> AccessDemo
inner -> Ada / Ada
inner -> Ada, visits=2
local -> Ada
anonymous -> Ada
```

In `StaticNested.show`, the nested class reads the private field via `outer.name` and calls `outer.mark(...)` using the passed-in reference. It does not need an implicit enclosing instance. `Inner.show` can use `name` and `mark` through the enclosing instance; `NestedTypeAccessDemo.this.name` explicitly refers to that instance. `Local` and the anonymous class are created and used inside their containing method.

The `StaticNested` and `Inner` types are declared private so the example demonstrates access within `NestedTypeAccessDemo`. If you need to use them from another class, you must choose an appropriate modifier and keep the constructor/referenced type accessible.

## 7. Referencing Rules to Remember

| Case | Common Syntax |
| --- | --- |
| Referencing a static nested type from outside | `Outer.Nested` |
| Creating an object of a static nested type | `new Outer.Nested()` |
| Referencing an inner class from outside | `Outer.Inner` |
| Creating an inner class tied to an object | `outer.new Inner()` |
| Getting the enclosing instance from an inner class | `Outer.this` |
| Referencing a local class | Class name only within the declaring block |
| Anonymous class | Created directly via the expression `new Type() { ... }` |

The syntaxes in the table are only valid when the type and constructor are accessible at the call site, and when the type is declared as the right kind. For example, `outer.new Inner()` does not apply to a static nested class.

## 8. Common Mistakes

1. **Using `new Outer.Inner()` for an inner class:** this syntax lacks an enclosing instance. Use `outer.new Inner()`.
2. **Creating `Outer.StaticNested` with the `outer.new StaticNested()` syntax:** a static nested class does not require an enclosing instance; use `new Outer.StaticNested()` when the type is accessible.
3. **Using `Outer.this` in a static nested class:** a static nested class has no implicit enclosing instance reference. Pass the enclosing object in if instance data is needed.
4. **Assuming a nested class cannot access private members:** nested types in the same nest have private access rights under Java rules. This does not grant access to unrelated code.
5. **Confusing type accessibility with constructor accessibility:** to create an instance, both the type name and the constructor must be accessible from the usage site.
6. **Assuming any local variable can be captured:** a local variable or parameter used by a local/anonymous class must be `final` or effectively final.
7. **Declaring a top-level class as `private` or `protected`:** these modifiers are only valid for member nested types in the appropriate context, not for top-level types.

## Conclusion

Access rights determine where a nested type can be referenced; whether it is `static` or non-static determines whether that type requires an instance of the enclosing type. Use `Outer.Nested` for a static nested type name, `outer.new Inner()` for an inner class, and `Outer.this` when an explicit reference to the enclosing instance is needed. Local and anonymous classes have a narrower scope and are suitable when a type only needs to serve a single piece of logic.
