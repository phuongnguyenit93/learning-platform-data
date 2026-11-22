# Same-Module or Same-Package Requirement in an Unnamed Module

## Objectives

This lesson explains the location boundaries that Java applies to types listed in `permits` in a sealed hierarchy: when the sealed type belongs to a **named module**, the permitted subtypes must belong to the same module; when it belongs to an **unnamed module**, the permitted subtypes must reside in the same package. You will learn how to declare `sealed` and `permits`, choose `final`/ `sealed`/ `non-sealed` for subclasses, and recognize common compilation errors.

## 1. What Does a Sealed Type Check at Compile Time?

~~~java
public sealed interface Shape permits Circle, Rectangle {}
~~~

`permits` only lists **direct** subtypes. `Circle` and `Rectangle` must actually declare `implements Shape` and also satisfy the branch policy: classes declare `final`, `sealed`, or `non-sealed`; records are implicitly `final`. Subinterfaces only use `sealed` or `non-sealed`.

Enums can also directly implement a sealed interface. An enum **without** a constant that has its own class body is implicitly `final`; an enum **with** a constant that has its own class body is implicitly `sealed`. An enum cannot use `extends` on an arbitrary sealed class. The location of the permitted subtypes is the next rule to check.

## 2. Named Module: Permitted Types Must Be in the Same Module

A **named module** is a module declared with a `module-info.java` file. If a sealed type resides in a named module, all direct subtypes listed in `permits` must belong to that same named module. They **can reside in different packages** within the module.

Example structure:

~~~text
src/
└── com.example.shapes/
    ├── module-info.java
    ├── com/example/api/Shape.java
    └── com/example/impl/Circle.java
~~~

`module-info.java`:

~~~java
module com.example.shapes {
    exports com.example.api;
}
~~~

`com/example/api/Shape.java`:

~~~java
package com.example.api;

public sealed interface Shape permits com.example.impl.Circle {
}
~~~

`com/example/impl/Circle.java`:

~~~java
package com.example.impl;

public final class Circle implements com.example.api.Shape {
}
~~~

In this example, `Shape` and `Circle` are in two different packages but both belong to the `com.example.shapes` module, because both are compiled and packaged in the same module. This is valid under the location rule of a sealed hierarchy. The example illustrates the module structure; to run it in practice, compile the module using the module-source-path directory structure or your project's build tool.

If `Circle` is moved to another named module, the declaration `permits com.example.impl.Circle` will be invalid even if the type name is written correctly and that type directly implements `Shape`. The enforced boundary is the module, not merely whether packages have the same name.

## 3. Unnamed Module: Permitted Types Must Be in the Same Package

If a sealed type is loaded in an **unnamed module** (which commonly occurs when running an application from the classpath without a module declaration), all permitted direct subtypes must be in the **same package** as the sealed type.

This example runs on the classpath and uses the `demo` package for all types:

`src/demo/Transport.java`

~~~java
package demo;

public sealed interface Transport permits Car, Bike {
}
~~~

`src/demo/Car.java`

~~~java
package demo;

public final class Car implements Transport {
}
~~~

`src/demo/Bike.java`

~~~java
package demo;

public final class Bike implements Transport {
}
~~~

`src/demo/SealedDemo.java`

~~~java
package demo;

public class SealedDemo {
    public static void main(String[] args) {
        Transport transport = new Car();
        System.out.println(transport instanceof Car ? "car" : "other");
    }
}
~~~

Compile from the root directory containing `src`:

~~~text
javac -d out src/demo/Transport.java src/demo/Car.java src/demo/Bike.java src/demo/SealedDemo.java
java -cp out demo.SealedDemo
~~~

Stdout output:

~~~text
car
~~~

There is no `module-info.java`, so the classes in the example are run from the classpath and belong to the unnamed module. All of them declare `package demo;`, so `Car` and `Bike` are in the same package as `Transport`, satisfying the unnamed module rule.

If `Car` is changed to `package demo.impl;`, merely placing the file in the `demo/impl` subdirectory is not enough to make it in the same package as `Transport`. A package is determined by the `package` declaration and the package identity in the compilation/class-loading environment, not solely by file location. When using an unnamed module, a permitted direct subtype in a different package causes a compilation error.

## 4. Do Not Confuse an Unnamed Module with an Unnamed Package

These two concepts are different:

- **Unnamed module:** code that does not belong to a named module. Traditional Java applications run from the classpath typically reside in the unnamed module.
- **Unnamed package:** a type without a `package` declaration at the top of the source file.

An unnamed module can still contain multiple named packages, such as `demo`, `demo.model`, and `demo.service`. For a sealed type in an unnamed module, the permitted direct subtypes must be in the same specific package as the parent type; having both belong to the unnamed module is not enough.

Conversely, when using a named module, the location rule allows direct subtypes to be in different packages as long as all of them reside in the same module. Therefore, identify the module first, and then apply the right boundary: **same module if it is a named module; same package if it is an unnamed module**.

## 5. When Do You Need to Write permits?

If the permitted direct subtypes are declared in the same compilation unit as the sealed type, Java can infer the list of permitted subclasses and the `permits` clause can be omitted. If the subtypes are declared in other compilation units, the `permits` list needs to be declared explicitly.

Example declared in the same source file:

~~~java
sealed interface Message {
}

final class TextMessage implements Message {
}

final class BinaryMessage implements Message {
}
~~~

In this case, the two subtypes are declared in the same compilation unit as `Message`, so the list of permitted subclasses can be inferred. Whether you write `permits` explicitly or let the compiler infer it, the rules regarding module/package and subtype modifiers still apply in the same way.

## 6. Common Errors and How to Diagnose Them

1. **Same module but different packages in an unnamed module:** invalid. In an unnamed module, a direct subtype must be in the same package as the sealed type.
2. **Same package name but belonging to a different module:** invalid for a sealed type in a named module. Direct subtypes must belong to the same named module.
3. **Relying solely on directory paths:** similar-looking directories do not prove that the package/module is valid. Check the `package` declaration, `module-info.java`, and how the code is compiled.
4. **Forgetting to declare a subtype in permits:** when a subtype is in a different compilation unit, add it to the sealed type's `permits` clause.
5. **Subtype does not directly extend/implement the sealed type:** `permits` only lists direct subtypes, not grandchildren or deeper descendants in the inheritance tree.
6. **Subtype lacks an appropriate modifier:** a direct subclass must be `final`, `sealed`, or `non-sealed` (records are implicitly final).
7. **Misunderstanding the scope of the rule:** the same-package/same-module constraint applies to permitted direct subclasses. If a permitted subclass is `non-sealed`, classes that further extend it follow normal inheritance rules and do not automatically have to be in the same package/module as the sealed ancestor.

When you encounter an error, check in order: whether the sealed type has the correct `permits` list; whether each name points to a direct subtype; whether the parent type and subtypes belong to a named module or an unnamed module; whether the package/module location follows the rule; and whether each subtype's modifier is valid.

## 7. Design Checklist

- Determine whether the sealed type is compiled in a named module or an unnamed module.
- For a named module, keep all permitted direct subtypes in the same module; their packages may differ.
- For an unnamed module, place all permitted direct subtypes in the same package as the sealed type.
- Declare `permits` when the subtypes are not in the same compilation unit or when you need to show the permitted list explicitly.
- Choose `final`, `sealed`, or `non-sealed` for each subtype according to the extension policy.
- Compile using the project's actual module/classpath configuration to catch mismatches between packages and modules.

## Conclusion

The location rule of a sealed hierarchy depends on the kind of module containing the sealed type. In a named module, permitted direct subclasses must belong to the same module but may be in different packages. In an unnamed module, they must reside in the same package as the sealed type. Properly distinguishing these two cases helps organize sealed code clearly and avoid compilation errors when splitting types across multiple files or packages.
