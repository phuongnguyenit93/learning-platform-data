# Type Information from a Subclass with a Parameterized Superclass

When a class extends a generic superclass and supplies concrete type arguments, Java can store **type information of the inheritance relationship** in class-file metadata. Reflection lets you read this information via `Class.getGenericSuperclass()` and inspect the `java.lang.reflect.Type` object. As a result, a framework can tell that `StringRepository extends Repository<String>` declared `String` as the type argument for `Repository<T>`, even though type argument information is usually erased from object types at runtime by **type erasure**.

However, the result is not always a `Class<?>`: it may be a `ParameterizedType`, which in turn contains `TypeVariable`, `WildcardType`, or `GenericArrayType`. When there are multiple levels of inheritance, Reflection **does not automatically substitute** all type variables from intermediate classes; inferring the final type requires walking the inheritance chain and performing type variable mapping.

## 1. The problem: reading back type arguments on an extends relationship

Consider two declarations:

```java
class Repository<T> {
}

class StringRepository extends Repository<String> {
}
```

In source code, `StringRepository` fixes the superclass argument `T` to `String`. Thus we want to know:

- What is the raw superclass of `StringRepository`?
- Which type arguments does the inheritance relationship contain?
- Is that argument already a concrete class, or still a type variable?
- Can we infer the type at the `Repository<T>` level if there are several intermediate classes?

Two `Class` APIs serve different purposes:

```java
Class<?> raw = StringRepository.class.getSuperclass();
java.lang.reflect.Type generic =
        StringRepository.class.getGenericSuperclass();
```

Meaning of the results:

- `getSuperclass()` returns `Repository.class`, the `Class<?>` object for the direct superclass; it **does not preserve the `String` argument**.
- `getGenericSuperclass()` returns a `Type` representing `Repository<String>`; in this case it is a `ParameterizedType`.
- Both approaches inspect only the **direct superclass** and do not automatically search for generic types deeper across all levels of the inheritance tree.
- If the class is `Object.class` or an interface without a corresponding superclass, `getGenericSuperclass()` returns `null`. If the superclass is used in raw form, the result may be a `Class<?>` instead of a `ParameterizedType`.

Generic information exists on a **declaration** such as the `extends Repository<String>` relationship. This differs from asking an object `new Repository<String>()` at runtime what its `T` argument is: for an ordinary generic class, `new Repository<String>().getClass()` still only returns `Repository.class`, and there is no `String` argument inside that `Class` object.

## 2. Variants of Type to distinguish

`java.lang.reflect.Type` is the common interface for type metadata. When reading `getGenericSuperclass()`, the result should be checked with `instanceof` before casting.

| `Type` variant | Example | Meaning |
| --- | --- | --- |
| `Class<?>` | `Object`, `String`, raw superclass | A type represented directly by a `Class` object, without parameterized arguments at this exact position |
| `ParameterizedType` | `Repository<String>`, `List<Integer>` | A raw type plus type arguments, and possibly an owner type |
| `TypeVariable<?>` | `T` in `Repository<T>` or `U` from an intermediate class | A reference to a type variable declared by a class, interface, or method/constructor |
| `WildcardType` | `? extends Number`, `? super Integer` | A wildcard type argument with upper/lower bounds |
| `GenericArrayType` | `U[]` in a generic declaration | An array type whose component is a generic type that cannot be represented by an ordinary `Class<?>` |

A `ParameterizedType` provides:

```java
ParameterizedType p = (ParameterizedType) generic;

Type rawType = p.getRawType();
Type[] arguments = p.getActualTypeArguments();
Type owner = p.getOwnerType();
```

This is an illustrative snippet assuming the variable `generic` has already been verified to be a `ParameterizedType` and `java.lang.reflect.*` has been imported.

- `getRawType()` is typically a `Class<?>`, such as `Repository.class`.
- `getActualTypeArguments()` returns the type arguments of the parameterized relationship, e.g., `String.class` for `Repository<String>`. Arguments may be nested `Type` forms, so **do not cast every element to `Class<?>`**.
- `getOwnerType()` can matter for a member type nested inside an enclosing type; typical top-level/static nested examples do not need to rely on owner.
- The number of arguments of a `ParameterizedType` can be 0 in certain owner/nested type structures; do not assume every `ParameterizedType` has exactly one argument.

For a `TypeVariable<?> v`, `v.getName()` gives the variable name; `v.getBounds()` gives the declared upper bounds. However, **bounds are not the concrete type value supplied by a subclass**. For example, `T extends Number` only states a constraint and does not allow concluding `T = Integer`.

## 3. Complete Java 17+ program

Create the file `GenericSuperclassDemo.java` as follows:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class GenericSuperclassDemo {
    static class Box<T> {
    }

    static class StringBox extends Box<String> {
    }

    static class Layer<U> extends Box<List<U>> {
    }

    static class IntegerLayer extends Layer<Integer> {
    }

    @SuppressWarnings("rawtypes")
    static class RawBox extends Box {
    }

    static class ArrayBox extends Box<String[]> {
    }

    static class GenericArrayBox<U> extends Box<U[]> {
    }

    static class NumberListBox extends Box<List<? extends Number>> {
    }

    static class Plain {
    }

    static String kind(Type type) {
        if (type instanceof Class<?>) {
            return "Class";
        }
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        if (type instanceof WildcardType) {
            return "WildcardType";
        }
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        return "Other";
    }

    static String render(Type type) {
        if (type == null) {
            return "null";
        }
        if (type instanceof Class<?> c) {
            if (c.isArray()) {
                return render(c.getComponentType()) + "[]";
            }
            return c.getSimpleName();
        }
        if (type instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(GenericSuperclassDemo::render)
                    .collect(Collectors.joining(", "));
            return render(p.getRawType()) + "<" + args + ">";
        }
        if (type instanceof TypeVariable<?> variable) {
            return variable.getName();
        }
        if (type instanceof GenericArrayType array) {
            return render(array.getGenericComponentType()) + "[]";
        }
        if (type instanceof WildcardType wildcard) {
            if (wildcard.getLowerBounds().length > 0) {
                return "? super " + render(wildcard.getLowerBounds()[0]);
            }
            Type[] upper = wildcard.getUpperBounds();
            if (upper.length == 1 && upper[0] == Object.class) {
                return "?";
            }
            return "? extends " + render(upper[0]);
        }
        return type.getTypeName();
    }

    static void inspect(Class<?> child) {
        Class<?> rawSuperclass = child.getSuperclass();
        Type genericSuperclass = child.getGenericSuperclass();

        String rawName = rawSuperclass == null
                ? "null" : rawSuperclass.getSimpleName();

        System.out.println(child.getSimpleName() + ": raw=" + rawName
                + ", generic=" + render(genericSuperclass));

        if (genericSuperclass instanceof ParameterizedType p) {
            Type[] args = p.getActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                System.out.println("  arg[" + i + "]="
                        + render(args[i]) + " (" + kind(args[i]) + ")");
            }
        }
    }

    public static void main(String[] args) {
        inspect(StringBox.class);
        inspect(Layer.class);
        inspect(IntegerLayer.class);
        inspect(RawBox.class);
        inspect(ArrayBox.class);
        inspect(GenericArrayBox.class);
        inspect(NumberListBox.class);
        inspect(Plain.class);
        inspect(Object.class);

        ParameterizedType first = (ParameterizedType)
                IntegerLayer.class.getGenericSuperclass();
        Type supplied = first.getActualTypeArguments()[0];

        ParameterizedType second = (ParameterizedType)
                Layer.class.getGenericSuperclass();
        ParameterizedType list = (ParameterizedType)
                second.getActualTypeArguments()[0];
        TypeVariable<?> variable = (TypeVariable<?>)
                list.getActualTypeArguments()[0];

        System.out.println("mapping: " + variable.getName()
                + " -> " + render(supplied));
        System.out.println("resolved Box argument: List<"
                + render(supplied) + ">");
    }
}
```

Run with JDK 17 or higher:

```bash
javac GenericSuperclassDemo.java
java GenericSuperclassDemo
```

Stdout output:

```text
StringBox: raw=Box, generic=Box<String>
  arg[0]=String (Class)
Layer: raw=Box, generic=Box<List<U>>
  arg[0]=List<U> (ParameterizedType)
IntegerLayer: raw=Layer, generic=Layer<Integer>
  arg[0]=Integer (Class)
RawBox: raw=Box, generic=Box
ArrayBox: raw=Box, generic=Box<String[]>
  arg[0]=String[] (Class)
GenericArrayBox: raw=Box, generic=Box<U[]>
  arg[0]=U[] (GenericArrayType)
NumberListBox: raw=Box, generic=Box<List<? extends Number>>
  arg[0]=List<? extends Number> (ParameterizedType)
Plain: raw=Object, generic=Object
Object: raw=null, generic=null
mapping: U -> Integer
resolved Box argument: List<Integer>
```

The program formats `Type` itself to display short names, avoiding reliance on JDK internal class names used to implement `ParameterizedType` and avoiding printing unguaranteed Reflection array ordering. In real applications, keep the `Type` intact for structural analysis and only convert to strings for display.

## 4. Detailed output analysis

### Case of a concretely parameterized superclass

`StringBox extends Box<String>`, so:

```java
Type type = StringBox.class.getGenericSuperclass();
boolean hasTypeArguments = type instanceof ParameterizedType; // true
```

Here `((ParameterizedType) type).getRawType() == Box.class` and `getActualTypeArguments()[0] == String.class`. The argument kind is `Class<?>`.

### Case where an intermediate class is still generic

`Layer<U> extends Box<List<U>>` yields `Box<List<U>>` from `getGenericSuperclass()`, but the first argument is not `Class<List>`. It is a **`ParameterizedType` representing `List<U>`**. Inside the argument of `List<U>`, `U` is a **`TypeVariable<?>`**.

Casting as:

```java
Class<?> wrong =
        (Class<?>) ((ParameterizedType)
                Layer.class.getGenericSuperclass())
                .getActualTypeArguments()[0];
```

is **wrong at runtime**: the element at that position is a `ParameterizedType`, so it will throw `ClassCastException`. You must check with `instanceof` and traverse nested `Type` layers.

### Case of a raw superclass

`RawBox extends Box` intentionally uses a raw type. `getGenericSuperclass()` returns `Box.class` — a `Class<?>`, which has no `getActualTypeArguments()` to trace back the type `T`.

Do not assume `T = Object` is "the type argument declared by the subclass". When using a raw type, type argument information was never recorded on the `extends` relationship. The bounds of `T` may hint at type validity, but they do not recover a generic value that was omitted.

### Generic arrays and concrete-type arrays

`ArrayBox extends Box<String[]>` has argument `String[].class`, which is itself a `Class<?>` of an array type.

`GenericArrayBox<U> extends Box<U[]>` instead has a `GenericArrayType` argument, whose component type is the type variable `U`. This distinction matters when writing serializers or type resolvers for generic arrays. You cannot cast `U[]` to `Class<?>` while `U` is still unbound.

### Nested wildcards

`NumberListBox extends Box<List<? extends Number>>` has an outer argument that is a `ParameterizedType` describing `List<? extends Number>`. The element inside `List` is a `WildcardType`. Use `getUpperBounds()` and `getLowerBounds()` to inspect bounds; do not treat a wildcard as a `Class<?>` or a single concrete type.

## 5. Across multiple inheritance levels: mapping TypeVariable manually

This is the most confusing part:

```java
class Box<T> {
}

class Layer<U> extends Box<List<U>> {
}

class IntegerLayer extends Layer<Integer> {
}
```

Calling:

```java
Type type = IntegerLayer.class.getGenericSuperclass();
```

only receives **`Layer<Integer>`**, because `IntegerLayer`'s direct superclass is `Layer`. Calling next:

```java
Type type2 = Layer.class.getGenericSuperclass();
```

receives **`Box<List<U>>`**, where `U` is still a type variable rather than automatically becoming `Box<List<Integer>>`. Those are two separate declarations, and Reflection does not substitute variables of the second declaration using mappings discovered in the first.

To infer the final argument of `Box<T>`, perform:

1. Read `IntegerLayer extends Layer<Integer>`: the argument of `Layer<U>` is `Integer`, so establish the mapping **`U → Integer`**.
2. Read `Layer<U> extends Box<List<U>>`: the argument of `Box<T>` is the type expression **`List<U>`**.
3. Substitute `U` with `Integer` in the expression above: **`List<Integer>`**.
4. Conclude that the argument `T` of `Box<T>` in the inheritance relationship resolves to **`List<Integer>`**.

In the runnable program in section 3, the example only resolves one simple mapping level. For a general-purpose tool, multiple variables and multiple levels must be handled, for instance:

```java
class Pair<A, B> {
}

class Intermediate<X, Y> extends Pair<Y, List<X>> {
}

class FinalPair extends Intermediate<String, Integer> {
}
```

This is an illustrative snippet. The initial mappings are `X → String` and `Y → Integer`, so `FinalPair` viewed from `Pair<A,B>` corresponds to `Pair<Integer, List<String>>`.

To build a correct resolver for an arbitrary class, maintain a `Map<TypeVariable<?>, Type>` instead of relying solely on variable names like `"T"`. Two different classes may both declare a variable `T`, yet those are **two distinct `TypeVariable`s belonging to two different `GenericDeclaration`s**. Mapping by name string alone easily substitutes the wrong variable.

A general algorithm:

- Start from the subclass `Class<?>`.
- At each step, call `getGenericSuperclass()`. If it is a `ParameterizedType`, obtain the raw superclass and pair `rawClass.getTypeParameters()` with `getActualTypeArguments()` by position.
- Before storing new mappings, **recursively substitute** any `TypeVariable`s already mapped from child levels inside each argument.
- Continue to the next superclass until reaching the target generic class or `Object`.
- When encountering nested `ParameterizedType`, `GenericArrayType`, or `WildcardType`, substitute inside their sub-structures as well; do not substitute only when an argument is directly a `TypeVariable`.
- If you hit a raw edge, an unmapped variable, or an inheritance chain that does not reach the target, **preserve the unresolved state** rather than guessing a concrete `Class<?>`.

If a tool needs to output a complete `Type` object after substitution, use an appropriate `Type` representation or a proven resolver library, and check compatibility with the JDK/module path. Constructing a string `"List<Integer>"` solely for demo printing **is not equivalent** to building a semantically valid `ParameterizedType`.

## 6. Distinguishing TypeVariable, bounds, and actual arguments

Consider:

```java
class NumericBox<T extends Number> {
}

class LongBox extends NumericBox<Long> {
}

class StillGeneric<N extends Number> extends NumericBox<N> {
}
```

Cases:

- `LongBox.class.getGenericSuperclass()` is `NumericBox<Long>`; the argument is `Long.class`, already concrete.
- `StillGeneric.class.getGenericSuperclass()` is `NumericBox<N>`; the argument is `TypeVariable<N>`, without choosing `Integer`, `Long`, or any specific numeric type.
- `N.getBounds()` only reports the upper bound `Number`. It **does not say** the subclass chose `Number` as the actual type argument.
- For `NumericBox<T>`, `NumericBox.class.getTypeParameters()` returns the list of type variables declared by `NumericBox`, e.g., `T`. This is the **type parameter declaration**, distinct from `getActualTypeArguments()` of the `extends NumericBox<Long>` relationship.

In multi-level generic code, a type variable may remain unresolved. In that case, a valid resolver result can be a `TypeVariable<?>`, not necessarily a `Class<?>`. Only narrow to a class when you are certain a concrete `Class<?>` type has been reached.

## 7. Anonymous subclasses and the type token technique

Direct object instantiation:

```java
Box<String> value = new Box<String>();
Type generic = value.getClass().getGenericSuperclass();
```

cannot recover the `String` argument: the runtime class of `value` is still `Box.class`, and `Box`'s superclass is `Object`.

However, if you create an **anonymous subclass** with a concrete generic superclass:

```java
Box<String> value = new Box<String>() {};

Type generic = value.getClass().getGenericSuperclass();
boolean captured = generic instanceof ParameterizedType; // true
```

this is an illustrative snippet using the `Box<T>` class from the earlier example. The anonymous class actually **extends `Box<String>`**, so the generic superclass signature of the anonymous class itself can contain `String`. This technique is the foundation for **type tokens**:

```java
abstract class TypeToken<T> {
    protected final Type capturedType;

    protected TypeToken() {
        Type parent = getClass().getGenericSuperclass();
        if (!(parent instanceof ParameterizedType p)) {
            throw new IllegalStateException(
                    "Subclass must provide a concrete type argument");
        }
        this.capturedType = p.getActualTypeArguments()[0];
    }

    public Type type() {
        return capturedType;
    }
}
```

This is an **illustrative** class requiring `import java.lang.reflect.Type` and `ParameterizedType`. Usage example:

```java
TypeToken<List<String>> token = new TypeToken<List<String>>() {};
Type captured = token.type(); // Metadata of List<String>
```

**Important limitation to understand:** this type token reads the **direct superclass of the anonymous subclass**, matching the shown instantiation pattern. If you add an intermediate class between the anonymous class and `TypeToken<T>`, a multi-level resolver is required. A type token like this also cannot turn an unbound type variable at the call site into a concrete type; for example, if the enclosing code is still generic in `<U>`, the token may contain `TypeVariable<U>`.

Type erasure still exists. A type token only leverages metadata from a **concrete generic superclass declaration**; it does not make every generic instance automatically carry runtime type arguments.

## 8. Superclasses differ from generic interfaces

`getGenericSuperclass()` follows the **class extends branch** and does not replace reading `implements` or interface `extends` relationships.

```java
interface Handler<T> {
}

class TextHandler implements Handler<String> {
}
```

This is an illustrative snippet. `TextHandler.class.getGenericSuperclass()` returns `Object.class` because the class's direct superclass is `Object`. To inspect `Handler<String>`, use:

```java
Type[] interfaces = TextHandler.class.getGenericInterfaces();
```

The result contains a `ParameterizedType` corresponding to `Handler<String>`. When an interface extends multiple other interfaces, you must traverse the superinterface tree separately and map type variables along those edges.

If the goal is to find a generic supertype regardless of whether it lies on an `extends class` path or an `implements interface` path, the resolver must inspect **both `getGenericSuperclass()` and `getGenericInterfaces()`**, and avoid infinite loops or redundant work when an interface appears through multiple paths.

## 9. Checks before retrieving actual type arguments

A common mistake:

```java
ParameterizedType p = (ParameterizedType)
        child.getGenericSuperclass();
Class<?> argument = (Class<?>)
        p.getActualTypeArguments()[0];
```

This is an illustrative snippet; it only runs safely if:

1. `getGenericSuperclass()` actually returns a `ParameterizedType`, not `Class<?>` or `null`.
2. The actual type arguments array is long enough to access index 0.
3. The first argument is a `Class<?>`, not a nested `ParameterizedType`, `TypeVariable<?>`, or `GenericArrayType`.

Write checked code:

```java
Type parent = child.getGenericSuperclass();

if (parent instanceof ParameterizedType p) {
    Type[] args = p.getActualTypeArguments();
    if (args.length == 1) {
        Type argument = args[0];
        if (argument instanceof Class<?> concreteClass) {
            System.out.println("Concrete: " + concreteClass.getName());
        } else {
            System.out.println("Needs resolution: " + argument.getTypeName());
        }
    }
}
```

This is an **illustrative snippet**; `child` must be a valid `Class<?>` and `java.lang.reflect.Type` and `ParameterizedType` must be imported. When a library requires a concrete type, it should not silently fall back to `Object.class` for an unresolved `TypeVariable`; it should report a clear error or preserve the `Type` for the calling layer to decide.

When reading generic signatures from bytecode, Reflection can encounter `GenericSignatureFormatError` if the signature is invalid, `TypeNotPresentException` if the metadata references an unavailable type, or `MalformedParameterizedTypeException` for a parameterized structure that cannot be instantiated. Therefore, tools processing external classes or plugins must have metadata error-reporting paths instead of assuming every class file always has a valid and complete signature.

## 10. Distinguishing type erasure from stored metadata

Type erasure does not mean *all* generic information is wiped out. The JVM usually executes on raw classes, yet the compiler can store **generic signatures** in the class file for Reflection to read back:

| Situation | What can Reflection know? |
| --- | --- |
| `new Box<String>()` | Runtime class is `Box.class`; cannot know the `String` argument from the instance itself |
| `class StringBox extends Box<String>` | Can read `Box<String>` from `StringBox.class.getGenericSuperclass()` |
| `class Layer<U> extends Box<List<U>>` | Reads `Box<List<U>>`, though `U` remains a type variable |
| `class IntegerLayer extends Layer<Integer>` | Reads `Layer<Integer>`; going deeper requires substituting `U` along the next edge |
| `class RawBox extends Box` | No actual type argument is declared on the raw edge |
| `class StringHandler implements Handler<String>` | Must be read via `getGenericInterfaces()` |

For serializer/ORM/DI frameworks, the design problem is usually **preserving the exact `Type` expression** before attempting to extract `Class<?>`. Types such as `List<String>` and `List<Integer>` share the same raw type `List.class` yet differ in type arguments, which can affect deserialization and validation rules.

## 11. Common misconceptions

| Misconception | Fact |
| --- | --- |
| `getSuperclass()` returns the generic arguments of the superclass | It returns the raw `Class<?>`; to keep the signature use `getGenericSuperclass()` |
| `getGenericSuperclass()` is always a `ParameterizedType` | It can be `Class<?>` or `null` |
| Every `getActualTypeArguments()[i]` is a `Class<?>` | It may be `ParameterizedType`, `TypeVariable`, `GenericArrayType`, or `WildcardType` |
| `Layer<U> extends Box<List<U>>` has argument `List.class` | The actual argument is the expression `List<U>`, i.e. a `ParameterizedType` |
| `IntegerLayer extends Layer<Integer>` makes `Layer.class.getGenericSuperclass()` automatically become `Box<List<Integer>>` | `Layer.class` metadata is still `Box<List<U>>`; you must map `U → Integer` |
| Bound `T extends Number` means the actual type is `Number` | Bounds are constraints on the type variable, not the type argument chosen by the subclass |
| A raw `extends Box` class can infer the exact argument from `Box.class` | A raw edge records no actual type argument |
| `new Box<String>().getClass()` remembers `String` | The runtime class is still `Box.class`; unlike an anonymous subclass type token |
| `getGenericSuperclass()` automatically handles `implements Handler<String>` | To read interfaces use `getGenericInterfaces()` |
| Using variable name `"T"` as the resolver key | Variable `T` in two different generic declarations can be two distinct variables |
| A `Type.getTypeName()` suffices as a runtime class | A Type may hold unresolved generic structure; do not treat the display string as `Class<?>` |
| Class files always contain valid generic metadata | Metadata may be missing/corrupt or reference a missing type; error handling is needed |

## 12. Self-check questions

Based on the classes in section 3:

1. **What does `StringBox.class.getSuperclass()` return?** `Box.class`, with no type arguments.
2. **What kind is `StringBox.class.getGenericSuperclass()`?** A `ParameterizedType` representing `Box<String>`.
3. **What is the first argument of `Layer.class.getGenericSuperclass()`?** A `ParameterizedType` representing `List<U>`; inside it is `TypeVariable<U>`.
4. **Is `IntegerLayer.class.getGenericSuperclass()` equal to `Box<List<Integer>>`?** No; it is only the direct superclass `Layer<Integer>`.
5. **To infer the argument of `Box<T>` viewed from `IntegerLayer`, what must you do?** Follow `IntegerLayer → Layer → Box` and substitute `U → Integer` to obtain the expression `List<Integer>`.
6. **Does `RawBox.class.getGenericSuperclass()` have `getActualTypeArguments()`?** No, the result is a `Class<?>` representing `Box`.
7. **Must the argument of `Box<U[]>` be a `Class<?>`?** No; `U[]` is described by a `GenericArrayType` when `U` is still unbound.
8. **Where do `new Box<String>()` and `new Box<String>() {}` differ?** The second creates an anonymous subclass declaring `extends Box<String>`; the generic superclass metadata of the anonymous class can retain `String`.
9. **If a class `implements Handler<String>` without extending a generic class, where do you read the type information?** `getGenericInterfaces()`.

**Remember:** `getGenericSuperclass()` gives you the **generic expression of the direct superclass**. When that expression is parameterized, `ParameterizedType.getActualTypeArguments()` gives its component `Type`s. Across multiple inheritance levels, preserve the `Type` structure and map `TypeVariable`s across each edge; only conclude a concrete `Class<?>` when the metadata truly justifies it.

### References

- [Java SE 17 — Class.getGenericSuperclass()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getGenericSuperclass())
- [Java SE 17 — ParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 17 — GenericArrayType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html)