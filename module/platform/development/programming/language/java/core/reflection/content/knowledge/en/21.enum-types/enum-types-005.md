# Enums with constant-specific class bodies: getClass and getDeclaringClass

## 1. One enum type can have multiple runtime classes

An enum can declare shared behavior and let some constants override behavior using a **constant-specific class body**. For example, a default transformation leaves a number unchanged, while other constants double or triple it.

Those constants still belong to the same enum type. However, a constant with a constant-specific class body is implemented by an anonymous subclass of the enum. Therefore, the **runtime class of the object** and the **enum class declaring the constant** can differ.

Java provides two APIs that answer those two questions:

| Call on an enum constant | Question answered |
| --- | --- |
| `constant.getClass()` | Which runtime class does this constant object have? |
| `constant.getDeclaringClass()` | Which declared enum does this constant belong to? |

`getClass()` is inherited from `Object`. `getDeclaringClass()` in the table is the method on `Enum`. Both are `final` methods; enum authors do not override them to change the result.

This distinction is valuable when a converter, data validator, or configuration store uses `Class` as a key. If rules are registered for the common enum type, using each constant's specific class for lookup can miss the configuration.

## 2. A constant-specific body creates a subclass, while the constant still belongs to the original enum

Consider the structure:

~~~java
enum Transform {
    IDENTITY,
    DOUBLE {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    };

    public int apply(int value) {
        return value;
    }
}
~~~

This is a complete enum declaration that can be placed inside a class or an appropriate source file; it is not yet a program with `main`.

- `IDENTITY` has no constant-specific body, so it uses the `apply` implementation in `Transform`.
- `DOUBLE` has a constant-specific body and overrides `apply`.
- The runtime class of `IDENTITY` is `Transform`.
- The runtime class of `DOUBLE` is an anonymous subclass of `Transform`.
- Both have `getDeclaringClass() == Transform.class`.

An overriding method is not required for a constant-specific body to create a subclass: even an empty `{}` body on a constant carries the same class semantics.

This is a Java mechanism reserved for enum constant declarations. It does not allow application code to arbitrarily write another class `extends Transform` to add constants. The constants remain the declared value set of the enum.

On Java 17, an enum without constant-specific bodies is implicitly `final`; an enum with at least one such body is implicitly `sealed`. Therefore, a Reflection tool should not rely on the assumption "every enum class has the final modifier" to recognize enums; use the purpose-built API such as `Class.isEnum()`.

## 3. Runnable example: same enum type, different runtime classes

Save as `EnumBodyIdentityDemo.java`:

~~~java
public class EnumBodyIdentityDemo {
    enum Transform {
        IDENTITY,
        DOUBLE {
            @Override
            public int apply(int value) {
                return value * 2;
            }
        },
        TRIPLE {
            @Override
            public int apply(int value) {
                return value * 3;
            }
        };

        public int apply(int value) {
            return value;
        }
    }

    private static void inspect(Transform transform) {
        System.out.println(
                transform.name()
                + " value=" + transform.apply(4)
                + " exact=" + (transform.getClass() == Transform.class)
                + " enumClass=" + transform.getClass().isEnum());
    }

    public static void main(String[] args) {
        for (Transform transform : Transform.values()) {
            inspect(transform);
        }

        System.out.println("DOUBLE.superIsTransform="
                + (Transform.DOUBLE.getClass().getSuperclass()
                   == Transform.class));
        System.out.println("IDENTITY.superIsEnum="
                + (Transform.IDENTITY.getClass().getSuperclass()
                   == Enum.class));
        System.out.println("DOUBLE.anonymous="
                + Transform.DOUBLE.getClass().isAnonymousClass());
        System.out.println("sameRuntime="
                + (Transform.DOUBLE.getClass()
                   == Transform.TRIPLE.getClass()));
        System.out.println("sameDeclaring="
                + (Transform.DOUBLE.getDeclaringClass()
                   == Transform.TRIPLE.getDeclaringClass()));
        System.out.println("sameConstant="
                + (Transform.DOUBLE == Transform.TRIPLE));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 EnumBodyIdentityDemo.java
java EnumBodyIdentityDemo
~~~

Output:

~~~text
IDENTITY value=4 exact=true enumClass=true
DOUBLE value=8 exact=false enumClass=false
TRIPLE value=12 exact=false enumClass=false
DOUBLE.superIsTransform=true
IDENTITY.superIsEnum=true
DOUBLE.anonymous=true
sameRuntime=false
sameDeclaring=true
sameConstant=false
~~~

Read the output in three layers of information:

1. **Behavior:** the same `apply(4)` call selects the implementation corresponding to the constant. That is standard polymorphism.
2. **Runtime class:** `DOUBLE` and `TRIPLE` have two different specific classes; `IDENTITY` uses the `Transform` class directly.
3. **Enum type:** all three are constants of `Transform`. Having the same declaring enum class does not mean two constants are equal.

The program does not print the binary names of the anonymous classes. Compiler-generated names often contain `$` and numbers, yet are not stable business data. Comparing `Class` objects and calling the right APIs keeps the example independent of those names.

## 4. Why can getClass().isEnum() return false?

`Class.isEnum()` identifies a class declared as an enum. A constant's own class is an anonymous subclass; it is not the original enum declaration itself.

Therefore, in the example just run:

~~~java
Transform.DOUBLE.getClass().isEnum()          // false
Transform.DOUBLE.getDeclaringClass().isEnum() // true
~~~

The two expressions above are illustrative lines within the scope of the `EnumBodyIdentityDemo` class.

The `false` result on the first line does not cause `DOUBLE` to lose its status as an enum constant. It simply describes the exact class being queried.

When receiving an arbitrary object, you can check:

~~~java
if (value instanceof Enum<?> constant) {
    Class<?> enumType = constant.getDeclaringClass();
    System.out.println(enumType.isEnum());
}
~~~

This is a snippet inside a method with parameter `Object value`. `instanceof` checks whether the object belongs to the `Enum` type hierarchy, so it includes constants with their own classes. For `null`, the condition is `false`.

Do not use `value.getClass().isEnum()` in place of the condition above if the goal is to recognize all enum constant objects. Also do not use `Enum.class.isAssignableFrom(type)` alone to assert that `type` is an enum declaration: the inheritance relationship is broader than the `isEnum()` condition, and `Enum.class` itself satisfies the relation with itself.

## 5. Application: normalizing configuration keys by enum type

Suppose configuration is registered once for the `Shipping` enum. Every constant, including constants with their own bodies, must locate that same configuration.

Save as `EnumTypeRegistryDemo.java`:

~~~java
import java.util.Map;
import java.util.Objects;

public class EnumTypeRegistryDemo {
    enum Shipping {
        BASIC,
        PRIORITY {
            @Override
            public String label() {
                return "Priority delivery";
            }
        };

        public String label() {
            return "Basic delivery";
        }
    }

    static Class<?> enumTypeOf(Object value) {
        Objects.requireNonNull(value, "value");
        if (value instanceof Enum<?> constant) {
            return constant.getDeclaringClass();
        }
        throw new IllegalArgumentException("Expected an enum constant");
    }

    public static void main(String[] args) {
        Map<Class<?>, String> configuration =
                Map.of(Shipping.class, "shipping-config");

        Enum<?> value = Shipping.PRIORITY;

        System.out.println("wrong="
                + configuration.get(value.getClass()));
        System.out.println("right="
                + configuration.get(value.getDeclaringClass()));
        System.out.println("sameLogicalType="
                + (enumTypeOf(Shipping.BASIC)
                   == enumTypeOf(Shipping.PRIORITY)));
        System.out.println("expectedExactClass="
                + (value.getClass() == Shipping.class));
        System.out.println("expectedIsInstance="
                + Shipping.class.isInstance(value));
        System.out.println("enumAccessor="
                + (value.getDeclaringClass() == Shipping.class));
        System.out.println("classAccessor.owner="
                + (Shipping.class.getDeclaringClass()
                   == EnumTypeRegistryDemo.class));
        System.out.println("anonymousClassAccessor="
                + value.getClass().getDeclaringClass());
        System.out.println("knownName=" + value.name());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 EnumTypeRegistryDemo.java
java EnumTypeRegistryDemo
~~~

Output:

~~~text
wrong=null
right=shipping-config
sameLogicalType=true
expectedExactClass=false
expectedIsInstance=true
enumAccessor=true
classAccessor.owner=true
anonymousClassAccessor=null
knownName=PRIORITY
~~~

The `Shipping.class` key and `PRIORITY`'s own class are two distinct `Class` objects. Therefore, the first lookup returns `null`. Calling `getDeclaringClass()` yields the exact enum key that was registered.

A bug like this can be hard to spot when testing only constants without their own bodies: for `BASIC`, `getClass()` happens to return `Shipping.class` itself, so the lookup appears to work.

The `enumTypeOf` method defines a clear contract: accept only an enum constant object, rejecting `null` and other objects. Do not silently take an arbitrary superclass for non-enum inputs.

If the goal is to check whether an object is assignable to the target type, `Shipping.class.isInstance(value)` reflects the appropriate type relationship, including a constant's subclass. Checking `value.getClass() == Shipping.class` requires the runtime class to match strictly and will reject constants with their own bodies.

## 6. Two methods named getDeclaringClass do not have the same semantics

This is an easy spot to misread when writing chained Reflection calls:

| Expression in the Shipping example | Receiver object | Meaning |
| --- | --- | --- |
| `value.getDeclaringClass()` | A constant of type `Enum<?>` | Gets the enum class `Shipping` |
| `Shipping.class.getDeclaringClass()` | A `Class` object | Gets the class enclosing the member class declaration `Shipping` |
| `value.getClass().getDeclaringClass()` | A `Class` object of the runtime class | Queries the declaring class of that runtime class |

In the program, `Shipping` is a member enum of `EnumTypeRegistryDemo`, so `Shipping.class.getDeclaringClass()` returns the enclosing class `EnumTypeRegistryDemo`.

Conversely, the anonymous class of `PRIORITY` is not a named member class; `Class.getDeclaringClass()` returns `null` for an anonymous class. Therefore, inserting `getClass()` before the call changed the API and changed the question.

When reading code, look at the type of the object before the dot:

- `Enum.getDeclaringClass()` determines the **enum type of the constant**.
- `Class.getDeclaringClass()` determines the **class declaring a member class**.

Do not substitute these two APIs for each other even though their method names are identical. For a top-level enum in a file, `Class.getDeclaringClass()` is also not a way to find that enum again; it returns `null` because there is no enclosing class declaring a member.

## 7. Which class to choose when reading metadata?

Choose the `Class` according to the information actually needed:

**To process the common enum type:** take `constant.getDeclaringClass()`. This is the proper starting point for getting the constant list via `getEnumConstants()`, looking up type-keyed configuration, or finding shared declarations of the enum.

**To investigate a constant's own implementation:** use `constant.getClass()`. In that case, seeing an anonymous class and overridden methods is the expected data.

The two directions cannot be swapped arbitrarily. For example, `getDeclaredMethods()` queries methods declared directly in the class being inspected. Querying `DOUBLE`'s own class looks at the constant's specific declarations; querying `Transform.class` looks at the shared enum declaration.

A method added only inside a constant's own body does not automatically become a shared method callable through any enum-typed variable. When designing polymorphic behavior, declare the method in the enum and override it in the constants that need to change, like `apply` in the example.

If an enum declares an `abstract` method, every constant must provide an implementation according to enum rules. When all constants have their own bodies, there may be no constant whose runtime class is the enum itself. Therefore, picking an arbitrary constant as a "sample" and calling `getClass()` still fails to identify the common enum type.

There is no need for `setAccessible(true)`, modifying internal fields, or looking up constructors to distinguish these two kinds of classes. Public APIs already provide the necessary relationships.

## 8. Error-prone assumptions

| Approach | Why it is error-prone | Suitable approach |
| --- | --- | --- |
| `constant.getClass() == ExpectedEnum.class` to accept all constants of the enum | Fails to recognize constants with their own class bodies | Compare `getDeclaringClass()` or use `ExpectedEnum.class.isInstance` as appropriate |
| Calling `getSuperclass()` exactly once for every constant | Regular constants have `Enum` as superclass; constants with bodies have the specific enum | Use `Enum.getDeclaringClass()` |
| Splitting the class name at `$` | `$` also appears in nested class names; anonymous class names are not business keys | Keep the `Class` object returned by the API |
| Relying on one constant to guess the class of all constants | An enum can mix constants with and without custom bodies | Normalize each constant to the enum class when needed |
| Thinking two constants with different runtime classes are different enum types | Confuses implementation class with declaring enum type | Check `getDeclaringClass()` |
| Thinking same enum class means same constant | Different constants belong to the same enum | Compare constants or use `name()` per contract |
| Calling `getClass().getDeclaringClass()` instead of `getDeclaringClass()` | Switches to the API on `Class` | Call the method directly on `Enum` |

In addition, identical class names do not guarantee the same type if they are loaded by different class loaders. When storing metadata within a JVM, using `Class` objects as keys preserves the exact type identity returned by the APIs; do not simplify down to simple names and assume all matching names are the same type.

## 9. Self-check

1. If both `RED` and `BLUE` have constant-specific bodies in enum `Color`, is `RED.getClass() == BLUE.getClass()` true?
2. Do those two constants have the same `getDeclaringClass()`?
3. If a constant has no custom body, why is calling `getSuperclass()` once not a general normalization method?
4. Is `value.getClass().getDeclaringClass()` equivalent to `value.getDeclaringClass()`?
5. Which API should a configuration store keyed by `Color.class` use to get the key from a constant?
6. Is it necessary to print or parse class names containing `$` to answer the questions above?

Answers:

1. No. Each constant-specific body corresponds to its own anonymous subclass.
2. Yes; both return `Color.class`.
3. A regular constant's runtime class is the enum itself, so its superclass is `Enum`, not the enum being sought.
4. No. One call queries the declaring relationship of a `Class`; the other queries the enum type of the constant.
5. `constant.getDeclaringClass()`.
6. No. `Class` objects and type-relationship APIs answer directly.

When writing Reflection code that processes enums, decide clearly whether you need the class implementing one constant's behavior or the common enum type. That decision determines the choice between `getClass()` and `Enum.getDeclaringClass()`.

## Reference documentation

- [Java 17 — Object.getClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#getClass()).
- [Java 17 — Enum.getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()).
- [Java 17 — Class.getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaringClass()).
- [JLS 17 — Enum declarations and constant-specific class bodies](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
