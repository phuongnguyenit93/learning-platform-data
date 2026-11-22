# Generic Signature Information Retained in Class Files

## 1. Type erasure does not mean all traces of generics vanish

Java Generics primarily provide **compile-time type checking**. After checking, the compiler uses *type erasure* to produce type descriptions the JVM can execute. For example, `List<String>` and `List<Integer>` both use the same runtime class `java.util.ArrayList`; the JVM does not generate a separate version of `ArrayList` for each type argument.

However, the claim that "after compilation no generic information remains anywhere" is **incorrect**. A class file can store the **declared generic signature** using the `Signature` attribute. As a result, tools such as `javap` and the reflection API can read back declarations such as:

- Names and bounds of type parameters, e.g., `<T extends Number & Comparable<T>>`.
- Superclasses/interfaces with type arguments, e.g., `extends Base<String>`.
- Field types declared as `List<String>`.
- Generic types in parameters, return types, and certain parts of method/constructor signatures.
- Wildcards `? extends`, `? super`, generic arrays, and type variables when they appear in the stored signature.

The key point is to distinguish two layers of information:

1. **Erased descriptor**: the JVM type used to identify fields/methods, invoke methods, and verify bytecode, e.g., `Ljava/util/List;`.
2. **Generic signature**: supplemental metadata describing the generic declaration, e.g., `Ljava/util/List<Ljava/lang/String;>;`.

`Signature` does not make every object remember all type arguments used at a `new` expression. It lets tools recover **declaration-site information** that the compiler recorded in the class file.

## 2. Reading three concepts accurately: source type, descriptor, and `Signature`

Consider the declaration:

```java
class Catalog {
    java.util.List<String> names;
}
```

This is a valid Java class, without a `main` program yet.

In source code, `names` has type `List<String>`. After erasure, the **field descriptor** is:

```text
Ljava/util/List;
```

If the compiler emits a generic `Signature` for the field, the corresponding metadata string is:

```text
Ljava/util/List<Ljava/lang/String;>;
```

These two strings describe the same field from two different perspectives:

| Perspective | Representation | Primary purpose |
|---|---|---|
| Java source type | `List<String>` | Compiler checks types when writing and using `names` |
| JVM field descriptor | `Ljava/util/List;` | Erased bytecode format used for the field |
| Generic `Signature` attribute | `Ljava/util/List<Ljava/lang/String;>;` | Preserves type argument `String` in declaration metadata |

The symbols in both strings are **not** Java source syntax:

- `L...;` denotes a reference class/interface type in a descriptor or signature.
- `/` separates JVM internal name components, e.g., `java/util/List`.
- `<...>` inside a signature encodes type arguments when present.
- This signature is stored as a string following the JVM class-file grammar, rather than storing a pre-instantiated Java `ParameterizedType` object. Reflection can read and parse that string when the application requests it.

A class file can also contain other attributes such as `Code`, `Exceptions`, `RuntimeVisibleAnnotations`, `LocalVariableTable`, or `LocalVariableTypeTable`. They each serve their own roles; **do not equate all of them with `Signature`**.

## 3. Where does the `Signature` attribute live?

According to the Java class file format, `Signature` is an attribute attached to constructs that can carry generic declarations, specifically:

- **Class/interface**: stores the class/interface's type parameters and generic representations of its superclass/superinterfaces.
- **Field**: stores the field's generic type.
- **Method** (including constructors, represented as methods in class files): stores generic signature parts concerning type parameters, parameter types, return type, and throws signatures where applicable.

A combined example:

```java
import java.io.Serializable;
import java.util.List;

class Box<T extends Number & Comparable<T>> implements Serializable {
    private T value;
    private List<? extends T> history;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void replace(T next) {
        value = next;
    }

    List<? extends T> history() {
        return history;
    }
}
```

This is a class for analysis, with no `main`. Positions containing generic traces:

| Member | Type in Java source | Erased type/descriptor | Information that may remain in `Signature` |
|---|---|---|---|
| Type parameter `T` | `T extends Number & Comparable<T>` | Erasure of `T` is `Number` | Name `T`, bounds `Number`, `Comparable<T>` |
| `value` | `T` | `Number` | Field has type variable `T` |
| `history` | `List<? extends T>` | `List` | `List` with wildcard upper bound `T` |
| `Box(T)` | Parameter `T` | `(Number)void` at descriptor level | Constructor taking `T` |
| `get()` | Returns `T` | Returns `Number` | Method returning `T` |
| `replace(T)` | Accepts `T` | Accepts `Number` | Method taking `T` |
| `history()` | Returns `List<? extends T>` | Returns `List` | Method returning generic type with wildcard |

A class file only needs `Signature` attributes for declarations that actually require generic representation. A completely non-generic member may **not have** this attribute. Do not assume every field or every method has a `Signature` attached.

### `Signature` is supplemental metadata

The JVM identifies methods by name and descriptor; `Signature` does not replace the descriptor, is not an extra component in method invocation, and does not automatically enforce at runtime that an `ArrayList` contains only `String`.

When executing bytecode, the JVM still relies on erased types, normal runtime type checks, and compiler-generated cast instructions. Generic signatures serve declaration representation and tools capable of understanding generics.

## 4. Hands-on example: `javap` sees both descriptors and generic signatures

Create the file **`SignatureClassFileDemo.java`** with the full content:

```java
import java.util.List;

public class SignatureClassFileDemo<T extends Number & Comparable<T>> {
    private T value;
    private List<? extends T> history;

    public SignatureClassFileDemo(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T next) {
        value = next;
    }

    public List<? extends T> history() {
        return history;
    }

    public static void main(String[] args) {
        SignatureClassFileDemo<Integer> box =
                new SignatureClassFileDemo<>(7);
        System.out.println(box.get());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SignatureClassFileDemo.java
java SignatureClassFileDemo
```

Stdout:

```text
7
```

Use the tool bundled with the JDK:

```bash
javap -p -s SignatureClassFileDemo
```

Focus on the meaningful sections below (this is a **shortened excerpt**, not the entire command output):

```text
private T value;
  descriptor: Ljava/lang/Number;

private java.util.List<? extends T> history;
  descriptor: Ljava/util/List;

public T get();
  descriptor: ()Ljava/lang/Number;

public void set(T);
  descriptor: (Ljava/lang/Number;)V

public java.util.List<? extends T> history();
  descriptor: ()Ljava/util/List;
```

Meaning:

- `T` has **leftmost bound `Number`**, so wherever `T` is used, the descriptor uses `Number`.
- `List<? extends T>` is erased to `List`; the wildcard does not appear in the descriptor.
- `get()` returns `Number` in its descriptor, yet `javap` can still display the `T` declaration by reading generic metadata.
- `V` denotes the `void` return type in a method descriptor.

To inspect the attributes stored in the class file clearly:

```bash
javap -p -v SignatureClassFileDemo
```

Look for lines labeled `Signature:`. Constant pool references `#...` may vary across compilations, while the signature strings to note include:

```text
TT;
Ljava/util/List<+TT;>;
()TT;
(TT;)V
<T:Ljava/lang/Number;:Ljava/lang/Comparable<TT;>;>Ljava/lang/Object;
```

These are **relevant signature string examples**, not a verbatim output block in the exact order printed by `javap -v`. `TT;` refers to the type variable named `T`. The `+TT;` part represents a `? extends T` wildcard. The last signature stores the declaration of type parameter `T` along with its two bounds and the class's superclass `Object`.

If you also want to see casts inside method bodies produced by erasure, run:

```bash
javap -p -c SignatureClassFileDemo
```

`-c` displays bytecode; `-s` displays descriptors; `-v` provides extended class-file information, including `Signature` attributes. Reading all three views together helps avoid confusing metadata with runtime logic.

## 5. Basic syntax of generic `Signature` strings

Generic signatures use a dedicated grammar defined by the JVM Specification. You do not need to memorize the entire grammar for application programming, but recognizing a few symbols helps when reading `javap -v` and analyzing libraries.

| Pattern | Illustrative meaning |
|---|---|
| `Ljava/lang/String;` | A class type `String` |
| `Ljava/util/List<Ljava/lang/String;>;` | `List<String>` |
| `TT;` | Type variable named `T` |
| `Ljava/util/List<TT;>;` | `List<T>` |
| `Ljava/util/List<+Ljava/lang/Number;>;` | `List<? extends Number>` |
| `Ljava/util/List<-Ljava/lang/Integer;>;` | `List<? super Integer>` |
| `Ljava/util/List<*>;` | `List<?>` |
| `[TT;` | Array `T[]` in signature syntax |
| `(TT;)TT;` | Method taking `T`, returning `T` |
| `<E:Ljava/lang/Object;>(TE;)TE;` | Method declaring `<E>`, taking `E`, returning `E` |

Important symbols:

- A leading `T` denotes a *type variable signature*, and the type variable's name precedes `;`. Hence `TT;` means "type variable `T`", not a class named `TT`.
- `+` represents an upper-bounded wildcard (`? extends`).
- `-` represents a lower-bounded wildcard (`? super`).
- `*` represents an unbounded wildcard (`?`).
- `[` represents an array.
- Parentheses `(...)` contain method parameter types.
- In type parameter declarations, `:` encodes class/interface bounds; with multiple bounds, multiple `:` markers can appear.

The generic signature of **a concrete class** can contain additional parts such as superclass, superinterfaces, and return/throws signatures. The table only explains basic patterns and does not replace the full grammar specified in the JVMS.

### `List<?>` does not mean the same thing as raw `List`

Although both typically share the descriptor `Ljava/util/List;`, the source type `List<?>` has a wildcard with specific type checks, whereas raw `List` deliberately drops type argument information and can trigger unchecked warnings.

If a declaration has `List<?>`, the generic signature can record the `*` wildcard. If a declaration uses raw `List`, there is no type argument to encode at that position. They should not be equated merely because their descriptors match.

## 6. Reflection can read generics at declarations

Java Reflection provides two API groups that must be distinguished:

- Methods returning `Class<?>` generally report the corresponding **erased or runtime type**.
- Methods returning `java.lang.reflect.Type` whose names contain `Generic` generally report the **generic declared type**, provided the necessary metadata is present and valid.

Create the file **`GenericSignatureReflectionDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class GenericSignatureReflectionDemo {

    static class Box<T extends Number & Comparable<T>> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void accept(List<? extends T> input) {
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Box.class;

        TypeVariable<?> variable = type.getTypeParameters()[0];
        System.out.println("variable: " + variable.getName());

        for (Type bound : variable.getBounds()) {
            System.out.println("bound: " + bound.getTypeName());
        }

        Field field = type.getDeclaredField("value");
        System.out.println("field raw: " + field.getType().getTypeName());
        System.out.println("field generic: " + field.getGenericType().getTypeName());

        Method get = type.getDeclaredMethod("get");
        System.out.println("return raw: " + get.getReturnType().getTypeName());
        System.out.println("return generic: "
                + get.getGenericReturnType().getTypeName());

        Method accept = type.getDeclaredMethod("accept", List.class);
        Type parameter = accept.getGenericParameterTypes()[0];

        ParameterizedType listType = (ParameterizedType) parameter;
        WildcardType wildcard = (WildcardType)
                listType.getActualTypeArguments()[0];

        System.out.println("parameter raw: "
                + accept.getParameterTypes()[0].getTypeName());
        System.out.println("parameter generic raw: "
                + listType.getRawType().getTypeName());
        System.out.println("wildcard upper: "
                + wildcard.getUpperBounds()[0].getTypeName());
    }
}
```

Run:

```bash
javac GenericSignatureReflectionDemo.java
java GenericSignatureReflectionDemo
```

Stdout:

```text
variable: T
bound: java.lang.Number
bound: java.lang.Comparable<T>
field raw: java.lang.Number
field generic: T
return raw: java.lang.Number
return generic: T
parameter raw: java.util.List
parameter generic raw: java.util.List
wildcard upper: T
```

Explaining the output:

1. `Class.getTypeParameters()` reads the type parameters declared by `Box`; the variable name is `T`.
2. `TypeVariable.getBounds()` returns the declared bounds: `Number`, `Comparable<T>`. Erasure does not force reflection to see only `Number`.
3. `Field.getType()` gives the erased field type `Number`, whereas `Field.getGenericType()` knows the field was declared with variable `T`.
4. `Method.getReturnType()` gives the erased return type `Number`, whereas `getGenericReturnType()` gives `T`.
5. `getDeclaredMethod("accept", List.class)` looks up the method by its erased parameter `List` because overload lookup uses `Class<?>` of runtime parameters.
6. `getGenericParameterTypes()[0]` is a `ParameterizedType` representing `List<? extends T>`; its inner argument is a `WildcardType` with upper bound `T`.

The program casts to `ParameterizedType` and `WildcardType` because **we know the exact declaration of the method ahead of time**. When building general-purpose reflection tools, always check with `instanceof` before casting: a `Type` object can belong to several different kinds.

## 7. `Type` kinds that reflection can return

`java.lang.reflect.Type` is the common interface for multiple forms of type descriptions. Here is a practical map:

| Reflected form | Source example | Reflection interface/class |
|---|---|---|
| Non-parameterized class type | `String` | `Class<?>` |
| Parameterized type | `List<String>` | `ParameterizedType` |
| Type variable | `T` in `class Box<T>` | `TypeVariable<?>` |
| Wildcard | `? extends Number` | `WildcardType` |
| Array with generic component type | `T[]`, `List<String>[]` | Can be `GenericArrayType` |
| Array with concrete class component | `String[]` | `Class<?>` |

Key points to remember:

- `ParameterizedType.getRawType()` gives the underlying type of the parameterization, e.g., `List.class`.
- `ParameterizedType.getActualTypeArguments()` gives the declared arguments, e.g., `String.class` for `List<String>`.
- `TypeVariable.getBounds()` and `WildcardType.getUpperBounds()/getLowerBounds()` read constraints represented in the generic signature.
- `GenericArrayType.getGenericComponentType()` inspects the array's component when the component is a suitable generic type.
- `Type.getTypeName()` is convenient for displaying type names in many learning tools, yet do not parse signatures by arbitrarily splitting strings when you already have structured `Type` objects.

An API that accepts multiple `Type` forms should branch by interface rather than casting everything to `ParameterizedType`.

Beyond the demonstrated APIs, there are `Class.getGenericSuperclass()`, `Class.getGenericInterfaces()`, `Method.getGenericExceptionTypes()`, `Constructor.getGenericParameterTypes()`, and similar APIs. They return *declared information* rather than magically discovering type arguments that only existed in compiler inference at a call site.

## 8. Why does `getClass()` not recover `List<String>` from an object?

A common misconception is:

> "If the class file still has `Signature`, calling `list.getClass()` will surely know this list is `List<String>`."

That is **false** for ordinary generic objects. Try the standalone program in **`GenericCaptureDemo.java`**:

```java
public class GenericCaptureDemo {

    static class Container<X> {
    }

    static class IntContainer extends Container<Integer> {
    }

    public static void main(String[] args) {
        Container<String> words = new Container<>();
        Container<Integer> numbers = new Container<>();

        System.out.println(words.getClass().equals(numbers.getClass()));
        System.out.println(Container.class.getTypeParameters()[0].getName());

        System.out.println(IntContainer.class.getSuperclass().getTypeName());
        System.out.println(
                IntContainer.class.getGenericSuperclass().getTypeName());

        Container<String> anonymous = new Container<String>() {};
        System.out.println(
                anonymous.getClass().getGenericSuperclass().getTypeName());
    }
}
```

Compile and run:

```bash
javac GenericCaptureDemo.java
java GenericCaptureDemo
```

Stdout:

```text
true
X
GenericCaptureDemo$Container
GenericCaptureDemo$Container<java.lang.Integer>
GenericCaptureDemo$Container<java.lang.String>
```

Analysis:

- Ordinary `new Container<String>()` and `new Container<Integer>()` are both instances of **one runtime class**, `Container`.
- `Container.class.getTypeParameters()` only says the class declares type variable `X`; it does not tell you which type argument each instance was created with.
- `IntContainer extends Container<Integer>` declares **a concrete inheritance relationship**. `IntContainer`'s class file can store the generic supertype `Container<Integer>`; `getGenericSuperclass()` reads that relationship.
- `new Container<String>() {}` creates **a separate anonymous subclass** at compile time. Its generic superclass is recorded in that subclass's class file, so reflection can see `String`.

The last two lines do not mean generics are *reified* for every instance; that is information from **a subclass that already has a declaration or inheritance structure carrying concrete type arguments**.

### Case where a generic subclass still does not know the concrete type

Example:

```java
class Child<U> extends java.util.ArrayList<U> {
}
```

`Child.class.getGenericSuperclass()` can report the `ArrayList<U>` relationship, yet cannot know on its own that a `Child<String>` instance was created with `U = String`. Here `U` remains a type variable of `Child`.

To capture a concrete type at runtime, APIs typically require callers to pass a **type token** (`Class<T>` for non-parameterized classes, or an appropriate `Type`/type-reference pattern to describe parameterized types), or use a subclass with concretely declared metadata as above. A type token is not proof that data inside a collection actually satisfies all generic constraints.

## 9. Generic methods also have their own `Signature`

`Signature` is not only for classes or fields. A method declaring its own type parameters can also be fully reflected.

Create the file **`GenericMethodSignatureDemo.java`**:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;

public class GenericMethodSignatureDemo {

    static <T extends Runnable & AutoCloseable> T pass(T input) {
        return input;
    }

    public static void main(String[] args) throws Exception {
        Method method = GenericMethodSignatureDemo.class
                .getDeclaredMethod("pass", Runnable.class);

        System.out.println("parameter raw: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("parameter generic: "
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("return generic: "
                + method.getGenericReturnType().getTypeName());

        TypeVariable<Method> variable = method.getTypeParameters()[0];
        for (Type bound : variable.getBounds()) {
            System.out.println("bound: " + bound.getTypeName());
        }
    }
}
```

Run:

```bash
javac GenericMethodSignatureDemo.java
java GenericMethodSignatureDemo
```

Stdout:

```text
parameter raw: java.lang.Runnable
parameter generic: T
return generic: T
bound: java.lang.Runnable
bound: java.lang.AutoCloseable
```

`T` has first bound `Runnable`, so the method descriptor uses `Runnable` in the parameter and return positions. Yet the method-level generic `Signature` preserves the name `T` along with both bounds, allowing reflection to distinguish them.

This is also why you must look at the right **declaration site**: a method's type variable is not necessarily the enclosing class's type variable. `Method.getTypeParameters()` reads the **method's** type parameters, while `Class.getTypeParameters()` reads the **class's** type parameters.

For generic constructors, the corresponding reflection methods are `Constructor.getTypeParameters()` and `Constructor.getGenericParameterTypes()`. Constructors do not have a return type like ordinary methods.

## 10. `Signature` and descriptors affect runtime differently

Consider:

```java
import java.util.List;

class Report {
    List<String> labels;
}
```

The `Report` class has field `labels`, yet the `List` object at runtime does not automatically check every inserted value to guarantee it only contains `String`. If some code misuses a raw type or unchecked cast, an error can surface later when reading elements as `String`.

The field's generic signature can tell a framework that **this field is declared as `List<String>`**. For instance, a JSON mapping library can use that information to choose how to convert elements. However, metadata does not verify by itself that actual data is already safe.

### What the JVM uses during linking and execution

- **Field/method descriptors** represent the erased types used by bytecode.
- **Runtime instructions** such as `checkcast` and array type checks enforce the necessary runtime rules.
- **Synthetic bridge methods** can be generated by the compiler when generic overriding needs compatibility with erased signatures.
- **`Signature`** helps tools and reflection understand generic declarations; it does not create extra overloads at runtime for each type argument.

For example, a `Processor<T>` interface declaring `T process(T input)` with an implementing class using `String` can cause the compiler to generate a bridge method so calls through `Processor` continue dispatching properly after erasure. Reflection tools can see the bridge method; that method can be marked `isBridge()` and `isSynthetic()`.

A bridge method is **executable code** generated by the compiler to preserve overriding behavior, whereas `Signature` is **declaration metadata**. They relate to the same type erasure problem but are not the same thing.

### Generic signatures do not replace binary descriptors

If a public library changes the first bound of a type parameter, the erased type in field/method descriptors can change. That change can impact binary compatibility, even if the Java types look similar conceptually.

Conversely, two declarations with the same descriptor can still carry different generic signatures. The JVM does not use generic signatures to distinguish two overloads colliding under erasure; the Java compiler has rules blocking certain declarations that cause name clashes.

## 11. Is `Signature` always present?

You cannot assume any arbitrary class file always carries complete generic metadata.

**Standard modern Java compilation:** `javac` writes `Signature` when needed to represent generics on classes/fields/methods. That is the case for the examples studied here.

**Source or bytecode without generic declarations:** There may be no corresponding `Signature`; reflection then provides non-generic or erased type information.

**Bytecode-transforming tools:** Some obfuscation, bytecode-weaving, optimization, or manual class-file generation pipelines may strip or alter `Signature`. Since the attribute is generic metadata, tools relying on reflection must be configured to retain necessary attributes.

**Invalid metadata or missing referenced types:** Reflection APIs parsing generics can throw errors such as `GenericSignatureFormatError`, `TypeNotPresentException`, or `MalformedParameterizedTypeException` depending on the situation. Do not treat `Signature` as unconditionally trustworthy data when loading class files from uncontrolled sources.

### `javac -g:none` and `LocalVariableTypeTable` are separate matters

`javac -g:none` disables generating **debug** information controlled by the `-g` flag. It does not require deleting class, field, and method generic `Signature` attributes. Generic signatures are not just a debug table.

Conversely, `LocalVariableTypeTable` is an **optional** attribute, typically tied to debug information for local variables with generic types, and may be absent. Standard reflection via `Field` and `Method` does not retrieve generics for every local variable inside a method body.

Try comparing:

```bash
javac -g:none SignatureClassFileDemo.java
javap -p -v SignatureClassFileDemo
```

You can still find `Signature` for the example's generic declarations, while local-variable/debug information has been stripped. This is a good test to avoid confusing **generic declaration metadata** with **debug metadata**.

### Metadata distinction table

| Attribute/structure | What does it contain? | Does it replace `Signature`? |
|---|---|---|
| Descriptor | Erased JVM type for a field/method | No; descriptors are required for bytecode description |
| `Signature` | Generic declaration of a class/field/method when applicable | This is where generic signatures are stored |
| `LocalVariableTable` | Name, scope, and descriptor info of local variables for debugging | No |
| `LocalVariableTypeTable` | Generic info for local variables if emitted by compiler/tool | No; serves local variables |
| `RuntimeVisibleAnnotations` | Annotations with runtime retention at appropriate positions | No |
| `RuntimeVisibleTypeAnnotations` | Type-use annotations with runtime retention at appropriate positions | No |
| `Code` | Method body bytecode and related structures | No |

Some class files also store method parameters, exceptions, or additional attributes; the purpose of each part should be viewed independently.

## 12. Type-use annotations and `Signature` are two mechanisms

Java allows annotations to appear in type positions when the annotation has an appropriate target, such as `List<@Nonnull String>` in an ecosystem defining suitable type-use annotations.

Generic `Signature` describes generic structure such as `List<String>`. Information about annotations attached to a type position is stored via the **type annotations** mechanism, rather than simply encoding annotation names inside the `Signature` string.

Therefore:

- `Field.getGenericType()` returns the generic type structure.
- `Field.getAnnotatedType()` inspects annotations on the type at the field declaration site when annotations and metadata apply.
- Whether runtime annotations exist depends on `@Retention`, `@Target`, and how the class file was built.

When writing a framework needing both generic structure and type-use annotations, you may need **both** API groups. Do not deduce that parsing `Signature` alone reveals every annotation or all business constraints.

## 13. Distinguishing declaration metadata from actual data types

Consider three scenarios:

**Scenario A — field with fixed generics**

```java
class Registry {
    java.util.List<String> names;
}
```

Reflection on `Registry.names` can see `List<String>`, because the `String` argument is written **right in the field declaration**.

**Scenario B — local variable via type inference**

```java
var names = new java.util.ArrayList<String>();
```

This is a Java statement inside a valid method, not a standalone runnable program. `var` lets the compiler infer the local variable's static type; a local variable being inferred as `ArrayList<String>` does not make every `ArrayList` instance at runtime carry a `String` argument, nor does it mean standard reflection has an API to directly read arbitrary local-variable generic info from an object.

**Scenario C — subclass declaring a concrete superclass type**

```java
class StringQueue extends java.util.ArrayDeque<String> {
}
```

`StringQueue`'s class file can record the generic relationship to `ArrayDeque<String>`. Reflection on **class `StringQueue`** can retrieve the parameterized supertype. That differs from calling `new ArrayDeque<String>()` directly: an ordinary `ArrayDeque` instance does not keep `String` as a runtime property of the object itself.

These differences explain why JSON, ORM, dependency injection, or schema-analysis libraries can read very useful generic information in some places, yet still require explicit type tokens or configuration in others. Metadata reflects **existing declaration signatures**, not the type-inference history of every call.

## 14. Practical applications and API design notes

### Writing reflection-based libraries

When reading field types, method parameters, or generic supertypes, prefer APIs containing `Generic` and handle all `Type` kinds properly. If you only use `getType()`/`getReturnType()`, you typically see erasure and can lose structures such as `List<Invoice>`.

Example snippet inspecting a field's type (must be placed in a class with an appropriate `Field field`):

```java
Type type = field.getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    // Inspect raw and each argument according to the framework contract.
}
```

This is only a reflection API illustration, not a standalone program. Outside the example, handle `TypeVariable`, `WildcardType`, generic arrays, nested/owner types, and incomplete metadata before treating the info as a concrete class.

### Designing libraries published for others

- If changing the order of generic bounds, check both the **erased descriptor** and **`Signature`**.
- If a framework relies on generic metadata, configure build/shrink/obfuscation pipelines to preserve required attributes.
- Use `javap -p -s` and `javap -p -v` to verify actual class-file output rather than inferring solely from Java source.
- For APIs taking `Class<T>`, remember that `Class<List<String>>` cannot be supplied directly via a class literal `List<String>.class`. `List.class` is only the class literal for raw `List`; a parameterized type structure must be represented using `Type` or a suitable type-reference mechanism.
- Do not use `Signature` to certify that collection data is clean or completely safe. Data validation and runtime type guarantees remain the application's responsibility.

### Relationship with bytecode tools

Tools reading/generating bytecode can see raw descriptors alongside generic `Signature` attributes. When generating new class files, ensure they are **semantically consistent**: a field declared `List<String>` needs a corresponding `List` descriptor while `Signature` describes the `String` argument. If metadata mismatches bytecode, downstream tools and reflection can misinterpret or fail.

Do not write a hand-rolled `Signature` parser using just `split("<")` or string replacements: the grammar supports nested parameterized types, owner types, bounds, arrays, and wildcards. If genuinely manipulating bytecode, use a tool with a `Signature` parser matching the target classfile version.

## 15. Common misunderstandings

**Mistake 1: "Type erasure wipes out all generic information."** Incorrect. Generic declarations can remain in `Signature` even though descriptors use erased types.

**Mistake 2: "The JVM uses `Signature` to know the exact element type of every `ArrayList`."** Incorrect. Generic elements of ordinary instances are not reified via `Signature`; runtime type checking still follows erased type rules.

**Mistake 3: "`getType()` and `getGenericType()` are always identical."** Incorrect. For a field `T value` bounded by `Number`, `getType()` can be `Number.class`, whereas `getGenericType()` is a `TypeVariable` named `T`.

**Mistake 4: "`Signature` only stores field type arguments."** Incorrect. It is also used for class-level and method-level generic declarations when needed.

**Mistake 5: "If reflection sees `<T>`, it knows what `T` is for every object."** Incorrect. `Class.getTypeParameters()` lists type variables declared by the class, without knowing arguments of every instantiation.

**Mistake 6: "Changing bounds has no effect because generics are erased."** Incorrect. The leftmost bound determines the erasure of a type variable; changes can affect descriptors and binary compatibility.

**Mistake 7: "`-g:none` deletes generic `Signature`."** Incorrect under `javac`'s normal behavior: declaration `Signature` is generic metadata, separate from debug tables.

**Mistake 8: "`List<?>` is just raw `List`."** Incorrect. Both types can share the same raw descriptor, yet their generic signatures and source-level type checks differ.

**Mistake 9: "A `Type` object returned by reflection is always a `ParameterizedType`."** Incorrect. You must distinguish `Class`, `TypeVariable`, `WildcardType`, `GenericArrayType`, and `ParameterizedType`.

**Mistake 10: "You can trust every generic signature read from any class file."** Advisable not to. Class files transformed by tools, missing dependencies, or containing malformed signatures can cause reflection/tools to fail; applications handling untrusted data must guard parsing flows.

## 16. Self-check knowledge quiz

1. For `List<String> values;`, does the field descriptor still contain `<String>`? **Answer:** no, the descriptor uses `Ljava/util/List;`; generic `Signature` can retain the `String` argument.
2. For `<T extends Number & Comparable<T>>`, what is the erasure of `T`? **Answer:** `Number`, because `Number` is the first bound. `Comparable<T>` can still appear in the declaration's `Signature`.
3. Why does `Container.class.getTypeParameters()` not infer that a `Container<Integer>` instance holds `Integer`? **Answer:** this API reflects type variables **declared** on the class, not the arguments of every instance.
4. When is `Class.getGenericSuperclass()` useful? **Answer:** when a class has a superclass relationship declared with parameterized types, such as `IntContainer extends Container<Integer>`.
5. How do `Method.getReturnType()` and `Method.getGenericReturnType()` differ? **Answer:** the former returns `Class<?>` representing the erased type; the latter returns `Type` expressing the generic type in the declaration if present.
6. Is `LocalVariableTypeTable` the `Signature` attribute of a field? **Answer:** no; it is a separate attribute for generic info of local variables, typically tied to debug metadata.
7. Can `new ArrayList<String>().getClass()` be used to discover `String`? **Answer:** not in general; the runtime class of `ArrayList<String>` and `ArrayList<Integer>` is the same `ArrayList.class`.
8. Does `getGenericType()` allow skipping validation of JSON data fed into `List<String>`? **Answer:** no; metadata describes the declaration, not the quality or actual type of individual input values.

### Mini practice exercise

Create a class with three fields:

```java
class WildcardFields {
    java.util.List<?> unknown;
    java.util.List<? extends Number> upper;
    java.util.List<? super Integer> lower;
}
```

Compile and run `javap -p -s WildcardFields`, then `javap -p -v WildcardFields`. Predict beforehand:

- All three descriptors are `Ljava/util/List;`.
- The first signature has `*` for the wildcard.
- The second signature has `+` before `Number`.
- The third signature has `-` before `Integer`.

The goal of the exercise is to see **the same raw descriptor** alongside **three different generic signatures**. If you continue inspecting with reflection, examine the arguments of `ParameterizedType` as `WildcardType` instead of trying to cast directly to `Class<?>`.

## 17. Summary and reference documentation

**Generic `Signature` is the structured trace of generic declarations stored in a class file.** The JVM still uses erased descriptors to represent fields/methods, while tools and reflection can read `Signature` metadata to learn type parameters, bounds, parameterized types, and wildcards when recorded.

Remember two facts simultaneously: **erasure still governs the execution model**, and **part of generic declarations remains retrievable at runtime via class metadata**. That retrievability does not make generics reified for every object and does not replace data validation.

Standard references:

- [JVM Specification, §4.7.9 — The `Signature` Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9): structure, locations, and conditions of the `Signature` attribute.
- [JVM Specification, §4.7.9.1 — Signatures](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9.1): grammar of class, method, and field type signatures.
- [Java Language Specification, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): definition of erased types.
- [Java SE 17 — `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): API hierarchy representing generic types.
- [Java SE 17 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `getType()` and `getGenericType()`.
- [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): type parameters, generic superclass, and generic interfaces.