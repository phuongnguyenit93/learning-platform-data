# Method Type Variables vs. Class Type Variables in Java Reflection

## 1. Goal and distinction to make

Java Generics allow declaring **type variables** on a **class/interface** or on a **method/constructor**. Two type variables can share the **same name**, such as both being `T`, yet remain two independent declarations with different scopes and constraints.

```java
class Box<T extends Number> {
    T value;

    // This is Box's T.
    T get() {
        return value;
    }

    // This is a NEW T belonging only to echo, shadowing the class's T.
    <T extends CharSequence> T echo(T input) {
        return input;
    }

    // U belongs to the method; T in the first parameter belongs to the class.
    <U> String describe(T item, U extra) {
        return item + ":" + extra;
    }
}
```

The code above illustrates syntax inside a class; it is not a standalone application (a complete example is in section 4).

In `Box<Integer>`, the class type variable `T` is bound to `Integer` at the parameterized type usage site. However, `<T extends CharSequence> T echo(T input)` **declares a new `T`** scoped solely to the method, so calling `box.echo("hello")` is still valid. You must not infer that `echo` must accept `Integer` merely because `Box` uses `Integer`.

In Java Reflection, this distinction appears directly in `TypeVariable<?>` and its `GenericDeclaration` owner. This lesson explains how to observe, identify the origin of, resolve, and avoid confusing **class type variables** with **method type variables**, even when both are named `T`.

### Expected outcomes

After this lesson, you will:

- Determine whether `T` belongs to a class or a method by its **declaration site**, not just by name.
- Distinguish `Class.getTypeParameters()` from `Method.getTypeParameters()` and `Constructor.getTypeParameters()`.
- Use `TypeVariable.getGenericDeclaration()` to identify the true owner.
- Read `getGenericReturnType()`, `getGenericParameterTypes()`, `getBounds()`, and recognize type erasure.
- Explain **shadowing** when a method type variable has the same name as a class type variable.
- Distinguish Reflection seeing a generic signature from knowing concrete runtime types like `Integer` or `String`.

## 2. Where are type variables declared?

### 2.1. Class type variables

```java
class Holder<T> {
    private T item;

    Holder(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}
```

In `Holder<T>`, the name `T` is declared in the type parameter list **right after the class name**. In positions using the class's `T` (where not shadowed), an instance whose source type is `Holder<String>` lets the compiler check `T` as `String`.

For example, `Holder<String>` and `Holder<Integer>` are two different usages of the generic class; at runtime, they typically point to **a single `Holder.class` definition** due to type erasure. The `Class` object of `Holder` reflects the **declaration** of `T`, and does not automatically know whether a specific instance was created with `String` or `Integer`.

### 2.2. Method type variables

```java
class Converter {
    public static <T> T identity(T input) {
        return input;
    }

    public <U extends Number> U keep(U number) {
        return number;
    }
}
```

Method type variables are declared **before the return type** in the method declaration: `<T>`, `<U extends Number>`. They belong specifically to that method, whether or not the enclosing class is generic.

A non-generic class can contain generic methods, and a generic class can contain non-generic methods or generic methods with their own type variables.

A **static method** cannot directly reference an instance-level type variable of a generic class, yet it can freely **declare** its own type variables:

```java
class Factory<T> {
    // Cannot directly use class T in a static context.
    static <S> S identity(S value) {
        return value;
    }
}
```

Here `S` belongs to the `identity` method, not `Factory`'s type variable `T`. You cannot write a static method that uses the class's `T` in its signature without an appropriate `<T>` declaration of its own.

### 2.3. Constructor type variables

Constructors can also declare their own type variables:

```java
class Sample<T> {
    <U> Sample(U input) {
        System.out.println(input);
    }
}
```

`T` belongs to the class, while `U` belongs to the constructor. Reflection provides `Constructor.getTypeParameters()` to retrieve `U`. Likewise, `U.getGenericDeclaration()` returns a `Constructor<?>` object, not `Class<?>`.

The examples in section 2 are isolated Java syntax snippets; section 4 provides a runnable program with `main`.

## 3. Reflection APIs to use

| Question | API | Return value / meaning |
| --- | --- | --- |
| Which type variables does a class declare? | `Class.getTypeParameters()` | Array `TypeVariable<Class<T>>[]` (often with wildcard in shared code) of the class/interface itself |
| Which type variables does a method declare? | `Method.getTypeParameters()` | `TypeVariable<Method>[]` of the method itself |
| Which type variables does a constructor declare? | `Constructor.getTypeParameters()` | `TypeVariable<Constructor<T>>[]` of the constructor |
| Which declaration owns a type variable? | `TypeVariable.getGenericDeclaration()` | `GenericDeclaration`: typically `Class`, `Method`, or `Constructor` |
| Name and upper bounds of a type variable? | `TypeVariable.getName()`, `getBounds()` | Name such as `T`; upper bound `Type`s |
| Generic return type of a method? | `Method.getGenericReturnType()` | `Type`; may be `TypeVariable`, `ParameterizedType`, `Class`... |
| Generic parameter types? | `Method.getGenericParameterTypes()` | `Type[]` array of the generic declaration |
| Erased return type? | `Method.getReturnType()` | `Class<?>` representing the erased runtime type |
| Erased runtime parameter types? | `Method.getParameterTypes()` | `Class<?>[]`, used to look up signatures via `getDeclaredMethod` |
| Generic superclass of a class? | `Class.getGenericSuperclass()` | `Type`, possibly a `ParameterizedType` like `Box<Integer>` |

**Distinguishing the two "parameters" methods:**

- `getTypeParameters()`: type variables **newly declared** on the class or method (e.g., `<T, U>`).
- `getGenericParameterTypes()`: the **types of parameters passed into** a method (e.g., `List<T> input, U extra`). A method that does not declare `<T>` itself can still use the class's type variable `T` in its parameter list and thus return an empty `getTypeParameters()` array while `getGenericParameterTypes()` is non-empty.

Special `Type` subtypes in `java.lang.reflect` include `TypeVariable<?>`, `ParameterizedType`, `WildcardType`, and `GenericArrayType`. Not every `Type` is a `Class<?>`; use `instanceof` before casting to a specific branch.

### GenericDeclaration and type variable identity

`TypeVariable.getGenericDeclaration()` is the key. In Reflection, two variables with the same name represent the same type variable only when they **correspond to the same generic declaration**; name alone is insufficient.

For example, in `Box<T>` and `<T> T echo(T)`:

- Both `classT.getName()` and `methodT.getName()` are `"T"`.
- `classT.getGenericDeclaration()` is `Box.class`.
- `methodT.getGenericDeclaration()` is the `Method` representing `echo`.
- Because their declarations differ, `classT.equals(methodT)` is `false`.

Use `getGenericDeclaration()` along with the declaring site/object when implementing a resolver; **do not** use a map keyed solely by the name `"T"`, because that name can be reused across multiple scopes.

## 4. Complete Java 17+ program: two `T`s, two distinct type variables

Save all of the following code to **`TypeVariableScopeDemo.java`**:

```java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.TypeVariable;

public class TypeVariableScopeDemo {
    static class Box<T extends Number> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }

        // Method-local T, shadowing Box's T.
        public <T extends CharSequence> T echo(T input) {
            return input;
        }

        // Method-local U; T in the first parameter belongs to Box.
        public <U> String describe(T item, U extra) {
            return item + ":" + extra;
        }

        // Static method may declare its own type variable S.
        public static <S extends CharSequence> S identity(S value) {
            return value;
        }
    }

    static class IntegerBox extends Box<Integer> {
        IntegerBox(Integer value) {
            super(value);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> cls = Box.class;
        TypeVariable<?> classT = cls.getTypeParameters()[0];
        Method echo = cls.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodT = echo.getTypeParameters()[0];
        Method get = cls.getDeclaredMethod("get");
        Method describe = cls.getDeclaredMethod(
                "describe", Number.class, Object.class);
        Method identity = cls.getDeclaredMethod(
                "identity", CharSequence.class);
        TypeVariable<?> methodU = describe.getTypeParameters()[0];

        System.out.println("class name: " + classT.getName());
        System.out.println("method name: " + methodT.getName());
        System.out.println("same name: "
                + classT.getName().equals(methodT.getName()));
        System.out.println("same variable: " + classT.equals(methodT));

        System.out.println("class owner Class: "
                + (classT.getGenericDeclaration() == cls));
        System.out.println("method owner Method: "
                + methodT.getGenericDeclaration().equals(echo));

        System.out.println("class bound: "
                + classT.getBounds()[0].getTypeName());
        System.out.println("method bound: "
                + methodT.getBounds()[0].getTypeName());

        System.out.println("get return is class T: "
                + get.getGenericReturnType().equals(classT));
        System.out.println("echo return is method T: "
                + echo.getGenericReturnType().equals(methodT));

        System.out.println("echo erased param: "
                + echo.getParameterTypes()[0].getSimpleName());
        System.out.println("echo erased return: "
                + echo.getReturnType().getSimpleName());

        System.out.println("describe owns U: " + methodU.getName());
        System.out.println("describe first param is class T: "
                + describe.getGenericParameterTypes()[0].equals(classT));
        System.out.println("describe second param is method U: "
                + describe.getGenericParameterTypes()[1].equals(methodU));

        System.out.println("static method variable: "
                + identity.getTypeParameters()[0].getName());

        ParameterizedType parent = (ParameterizedType)
                IntegerBox.class.getGenericSuperclass();
        System.out.println("subclass argument: "
                + parent.getActualTypeArguments()[0].getTypeName());

        Box<Integer> box = new Box<>(10);
        System.out.println("box get: " + box.get());
        System.out.println("echo: " + box.echo("hello"));
    }
}
```

Compile/run commands:

```bash
javac TypeVariableScopeDemo.java
java TypeVariableScopeDemo
```

**Output** (verified against Java Reflection behavior on the JVM):

```text
class name: T
method name: T
same name: true
same variable: false
class owner Class: true
method owner Method: true
class bound: java.lang.Number
method bound: java.lang.CharSequence
get return is class T: true
echo return is method T: true
echo erased param: CharSequence
echo erased return: CharSequence
describe owns U: U
describe first param is class T: true
describe second param is method U: true
static method variable: S
subclass argument: java.lang.Integer
box get: 10
echo: hello
```

### Explaining the core results

**1. Same name but different identity.** Both `Box<T>` and `echo<T>` have `getName() == "T"`, yet `classT.equals(methodT)` is `false`. Therefore a resolver must identify the **declaration owner** instead of mapping every variable named `T` to a single concrete type.

**2. Different bounds.** The class's `T` has bound `Number`; `echo`'s `T` has bound `CharSequence`. Thus `Box<Integer>` accepts a Number as the class parameter, while a call `echo("hello")` accepts String because String implements CharSequence. The two constraints apply to two independent type variables.

**3. Generic return type differs from erased return type.** `get.getGenericReturnType()` is the class type variable `T`. `echo.getGenericReturnType()` is the method type variable `T`. Yet `echo.getReturnType()` is `CharSequence.class` because erasure uses the method type variable's upper bound.

**4. Method lookup uses erased signatures.** `Box.class.getDeclaredMethod("echo", CharSequence.class)` succeeds. Using `Object.class` or `Number.class` instead of `CharSequence.class` will fail to find the method because the erased parameter type of this method is `CharSequence`.

**5. A method can use both class and method type variables.** `describe` declares `U` itself; its first parameter `T item` still refers to `Box<T>`. Thus `describe.getTypeParameters()` contains only `U`, while `getGenericParameterTypes()` shows both the class's `T` and the method's `U`.

**6. Static methods have their own type variables.** `identity` is a static generic method with `S` declared by itself; it is not the class's `T`.

**7. Generic superclass reveals the binding in a concrete branch.** `IntegerBox extends Box<Integer>` explicitly declares `Integer` in its generic superclass, so `IntegerBox.class.getGenericSuperclass()` returns a `ParameterizedType` containing the `Integer` type argument. Yet `Box.class.getTypeParameters()[0]` still represents **the declaration `T`**, without automatically becoming `Integer`.

## 5. Shadowing: a method can declare a `T` with the same name as the class's `T`

Suppose:

```java
class Repository<T> {
    T current;

    T load() {
        return current; // Repository's T
    }

    <T> T transform(T input) {
        return input;   // transform's new T
    }

    <U> T update(U source) {
        return current; // update's U; Repository's T
    }
}
```

This is an illustrative snippet about name scoping; it does not need to be run separately. **Shadowing** occurs when the method's `<T>` declaration hides the class's `T` name within that method's scope. By distinguishing owners, Reflection can observe two variables with the same name without ambiguity.

| Member | Type variable declared directly on that member | Meaning of `T` appearing in the signature |
| --- | --- | --- |
| `Repository<T>` | Class's `T` | Class-level type variable |
| `load()` | None | Return `T` belongs to the class |
| `<T> T transform(T)` | Method's `T` | `T` in return and parameter belongs to the method |
| `<U> T update(U)` | Method's `U` | Return `T` belongs to the class, parameter `U` belongs to the method |

When writing a resolver, model data by both the **declaration scope** and the type variable:

```text
Repository<T>              : key = (Repository.class, "T")
Repository.transform<T>(T)  : key = (Method transform, "T")
Repository.update<U>(U)     : key = (Method update, "U")
```

This is an **illustrative model**, not runnable Java code. It is the `getGenericDeclaration()` API and `TypeVariable` equality that distinguish these cases.

A common bug is storing mappings in a `Map<String, Type>` keyed only by `"T"`. When the resolver inspects the `transform` method, the new mapping can **overwrite** the class's `T` binding. Generic resolution results then become wrong even though the code compiles.

## 6. TypeVariable.getBounds() and erasure

Given:

```java
class Container<T extends Number> {
    <U extends CharSequence> U use(U text) {
        return text;
    }
}
```

The class's `T.getBounds()` returns bound `Number`; the method's `U.getBounds()` returns bound `CharSequence`. For a type variable with no explicit bound such as `<T>`, the implicit bound is `Object`.

### Multiple bounds

```java
class MultiBound<T extends Number & Comparable<T>> {
    T value;
}
```

`getBounds()` can return a `Type[]` array of multiple bounds in declaration order. When performing erasure of a type variable, the **leftmost bound** determines the erased type; in this example it is `Number`.

Do not read only `getBounds()[0]` if the task needs to preserve **all constraints**. The runnable example in section 4 uses a single bound for clear output; a real resolver must handle intersection bounds, generic references inside bounds, and cases where a type variable references itself (such as `Comparable<T>`).

### Generic metadata vs. runtime class

Two different APIs can yield different views:

```java
Method method = Box.class.getDeclaredMethod(
        "echo", CharSequence.class);

System.out.println(method.getReturnType());        // interface java.lang.CharSequence
System.out.println(method.getGenericReturnType()); // T
```

The snippet above must be placed in a method handling `NoSuchMethodException`, importing `Method` and using `Box` as in the example. `getReturnType()` views the **erased** return type as a `Class<?>`; `getGenericReturnType()` preserves the method's `TypeVariable` `T`. For the same method, both views are accurate.

For generic types using parameterized types, such as `List<T>`, `getGenericReturnType()` may be a `ParameterizedType`. When handling it, use `instanceof ParameterizedType` to obtain `getRawType()` and `getActualTypeArguments()`; a type argument may be a class `TypeVariable`, a method `TypeVariable`, a wildcard, or another complex structure. Never blindly cast `Type` to `Class<?>`.

## 7. Why doesn't Class.getTypeParameters() return method type variables?

`Class.getTypeParameters()` only lists type variables **declared by the class/interface itself**. It does not aggregate `T` or `U` from member methods.

For example:

```java
class Plain {
    <X> X echo(X input) { return input; }
}
```

`Plain.class.getTypeParameters()` is an **empty** array, because `Plain` is not a generic class. Conversely:

```java
Method m = Plain.class.getDeclaredMethod("echo", Object.class);
TypeVariable<?>[] vars = m.getTypeParameters();
```

This snippet belongs inside a method with exception handling. `vars.length` is `1`, and the variable at `vars[0]` is named `X`. The method's erased signature uses `Object` because `X` has no explicit bound.

Likewise, `Method.getTypeParameters()` returns an **empty array** for an ordinary method that uses a class-level type variable without declaring any new type variables:

```java
class GenericService<T> {
    T fetch() { return null; }
}
```

When inspecting `fetch()`, `getTypeParameters()` is empty even though `getGenericReturnType()` is the class's `T`. To find the owner of this `T`, check `TypeVariable.getGenericDeclaration()`.

## 8. Generic resolution in subclasses and limits to know

Suppose:

```java
class Parent<T> {
    T get() { return null; }
}

class Child extends Parent<String> {
}
```

On `Child`, the generic superclass holds the binding `Parent<String>`. Yet the `Method` object declared on `Parent` with return type `T` still retains **Parent's** `T` metadata. Reflection **does not automatically replace that type variable with String** merely because the caller obtained the method through `Child.class`.

A resolver aiming to resolve the return type properly in the context of `Child` must:

1. Determine which class/interface declared the method via `getDeclaringClass()`.
2. Traverse `getGenericSuperclass()` and `getGenericInterfaces()` along the hierarchy.
3. Collect mappings from type variables **of each declaration** to concrete type arguments, such as `Parent<T> → String`.
4. Substitute type variables using the mapping of the matching owner, handling `ParameterizedType`, `WildcardType`, `GenericArrayType`, and intermediate type variables as needed.

**Key rule:** the mapping `Parent.T → String` **must not** be applied automatically to another `T` declared by a `<T>` method inside `Parent`. Those two `T`s are not the same type variable, even though they share the same name.

### Method type arguments inferred at compile time

Example:

```java
class Tools {
    static <T> T identity(T value) {
        return value;
    }
}

String text = Tools.identity("hello");
Integer count = Tools.identity(123);
```

These two statements call the generic method with two different compile-time type inferences. Yet Reflection on `Tools.identity` only sees **a single declaration `<T> T identity(T)`**. It does not store a fixed method-T binding of String or Integer on the `Method` object.

When calling `Method.invoke(...)`, the caller must supply appropriate runtime types; compile-time inferred type argument information does not become metadata such as "this method call used T = String" inside `Method`.

If an application API needs to track bindings from a generic method in a specific context, it must receive sufficient additional information (parameter types/expected return type/resolver rules) and not over-infer from `Method.getTypeParameters()`.

## 9. Constructor type variables differ from class type variables

`Constructor<?>` also implements `GenericDeclaration`. That allows distinguishing constructor type variables from class type variables:

```java
class Factory<T> {
    <U extends CharSequence> Factory(U name) {
    }
}
```

Illustrative snippet:

```java
Class<?> type = Factory.class;
TypeVariable<?> classT = type.getTypeParameters()[0];

Constructor<?> ctor =
        type.getDeclaredConstructor(CharSequence.class);
TypeVariable<?> ctorU = ctor.getTypeParameters()[0];
```

This code is placed inside a method declaring/handling `NoSuchMethodException` and importing `java.lang.reflect.Constructor` and `java.lang.reflect.TypeVariable`.

- `classT.getGenericDeclaration() == Factory.class` is `true`.
- `ctorU.getGenericDeclaration().equals(ctor)` is `true`.
- `ctorU.getName()` is `"U"`, and `getBounds()[0]` is `CharSequence`.
- `getDeclaredConstructor(CharSequence.class)` looks up by the **erasure of the bound**, not by an inferred type argument such as `String.class`.

For non-static inner classes, the runtime constructor can also include a compiler-generated outer-instance parameter. That is a matter of the constructor signature, **separate** from whether the constructor declares `<U>`.

## 10. Common mistakes when building a generic resolver

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Comparing two `TypeVariable`s solely via `getName()` | Class-T and method-T can share the same name | Compare identity/declaration owner |
| Assuming a generic class means every method returns class-T | A method can declare a new T that shadows class-T | Inspect `Method.getTypeParameters()` and `getGenericReturnType()` |
| Thinking `Class.getTypeParameters()` includes generic methods | The API only returns type variables declared on the class | Query on each `Method` |
| Thinking `Method.getTypeParameters()` returns runtime parameter types | It returns type variables declared by the method, not parameter types | Use `getGenericParameterTypes()` or `getParameterTypes()` |
| Using `getReturnType()` to understand full generics | Erasure discards generic expressions | Use `getGenericReturnType()` |
| Looking up `echo(T)` with `Object.class` when `T extends CharSequence` | The erased parameter is CharSequence | Look up with `CharSequence.class` |
| Replacing every T with Integer because of `Box<Integer>` | Only class-T is bound; method-T is independent | Map by `GenericDeclaration` |
| Believing each call `identity("x")` stores method-T = String in `Method` | Compile-time type inference is not stored that way | Use separate context/type contracts |
| Casting every `Type` to `Class<?>` | `TypeVariable` and `ParameterizedType` are not `Class` | Branch with `instanceof` |
| Ignoring multi-bounds and nested parameterized types | Resolver may pick the wrong erasure or constraint | Handle all `Type` kinds and all bounds |
| Relying on variable names to infer runtime object types | Erasure and polymorphism make inference insufficient | Inspect actual objects if needed |

### Safe substitution map design

A resolver should use keys with explicit declaration identity, such as `TypeVariable<?>` directly:

```java
Map<TypeVariable<?>, java.lang.reflect.Type> bindings =
        new java.util.HashMap<>();
```

This is a snippet inside a class/method importing `java.util.Map` and `java.lang.reflect.TypeVariable`; the snippet does not provide a complete resolver algorithm. `TypeVariable.equals` is defined by its corresponding generic declaration, preventing two identically named variables from overwriting each other.

Even so, full binding resolution remains complex with multi-level generic superclasses, wildcards, captures, interfaces, owner types, and self-referential type variables. Do not use `getName()` and perform text replacement on `Type.getTypeName()`; work directly with the `Type` structure.

## 11. Short practice exercises

**Exercise 1.** Given:

```java
class Service<T> {
    T read() { return null; }
    <T> T convert(T value) { return value; }
    <U> T combine(U input) { return null; }
}
```

Answer:

1. How many elements does `Service.class.getTypeParameters()` have?
2. How many elements does `read.getTypeParameters()` have?
3. How many elements does `convert.getTypeParameters()` have?
4. Does `combine.getGenericReturnType()` belong to the class or the method?
5. Are the two `T`s of `Service<T>` and `convert<T>` the same type variable?

**Answer:** respectively **1, 0, 1, class, no**. `combine` declares `U` itself, but its return type `T` is the class's type variable.

**Exercise 2.** Given:

```java
class Numeric<T extends Number> {
    <T extends CharSequence> T text(T input) {
        return input;
    }
}
```

**Question:** Which API retrieves the method's type variable, and which parameter class must Reflection use to look up `text`?

**Answer:** `Numeric.class.getDeclaredMethod("text", CharSequence.class)` then call `method.getTypeParameters()`. Use `CharSequence.class` because the method-T bound is CharSequence; the class-T bound Number is unrelated to this method's signature.

**Exercise 3.** Given `class Child extends Parent<String>`, where `Parent<T>` has `T read()` and `<T> T echo(T input)`. Can a generic resolver replace both `T`s with String?

**Answer:** No. The binding from the inheritance relationship applies only to **Parent.class-T**. `echo` has an independent method-T, so it must not be inferred to equal String.

**Exercise 4.** If `Method.getTypeParameters()` returns an empty array, can we conclude the method does not use generics in its return/parameters?

**Answer:** No. The method can use a type variable declared on the class, such as `T read()`, or a `List<T>` parameter. Check `getGenericReturnType()` and `getGenericParameterTypes()`.

## 12. Self-check questions

**Question 1.** Do two type variables both named `T` necessarily have the same identity?

**Answer:** No. You must check their `GenericDeclaration` site. Class-T and method-T are two independent variables.

**Question 2.** Which API returns type variables declared by the method itself, such as `<U>`?

**Answer:** `Method.getTypeParameters()`. `getGenericParameterTypes()` instead returns the types of the parameters accepted by the method.

**Question 3.** How do `Method.getReturnType()` and `getGenericReturnType()` differ for `<T extends CharSequence> T echo(T x)`?

**Answer:** `getReturnType()` returns `CharSequence.class` after erasure; `getGenericReturnType()` returns the `TypeVariable` belonging to the method (named T).

**Question 4.** Why does `<T>` on a static method not depend on the type argument of the generic class?

**Answer:** It is declared by the method itself; a static context does not use instance type variables of the generic class.

**Question 5.** Does `Box<Integer>` automatically cause `<T extends CharSequence> T echo(T)` to return Integer?

**Answer:** No. Method-T shadows class-T, and method-T's bound is CharSequence, so it can return String.

**Question 6.** What kinds of objects does `TypeVariable.getGenericDeclaration()` return?

**Answer:** A declaration such as `Class`, `Method`, or `Constructor` corresponding to where the type variable was declared.

**Question 7.** When resolving `Parent<T>` in `Child extends Parent<String>`, why should you use `TypeVariable<?>` as the key instead of the string `"T"`?

**Answer:** So that the String binding applies only to Parent-T and does not overwrite type variables named T on methods or other classes.

**Remember:** **Class** type variables and **method** type variables are independent declarations. Sharing the name `T` does not create shared identity; Reflection reveals the owner via `TypeVariable.getGenericDeclaration()`. Use `Class.getTypeParameters()` to inspect class type variables, `Method.getTypeParameters()` to inspect method type variables, and `getGeneric...` APIs to preserve pre-erasure information. When resolving generics, always tie bindings to the **exact declaration**, especially when a method declares a new `T` shadowing the class's `T`.