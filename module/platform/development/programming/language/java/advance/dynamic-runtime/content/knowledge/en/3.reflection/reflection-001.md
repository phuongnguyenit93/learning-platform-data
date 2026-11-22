# 3.1 Distinguishing `getMethods`, `getFields`, `getConstructors` from the `getDeclared` variants

## 1. Learning Objectives

After this lesson, you will be able to:

- Choose the right Reflection API to list methods, fields, or constructors on a `Class<?>`.
- Explain two independent criteria: **inheritance scope** and **access level** (`public`, `protected`, package-private, `private`).
- Understand why `getDeclaredXxx()` can see `private` members but cannot see inherited members; and why constructors are an important exception.
- Look up a member by name and parameter type list, then check `getDeclaringClass()` before using it.
- Distinguish between **finding metadata** and **being allowed to access/invoke** a member, especially from Java 9+ when modules are present.

> Key point: **There is no generic `getDeclared()`.** `Declared` is part of the names of specific APIs: `getDeclaredMethods()`, `getDeclaredFields()`, `getDeclaredConstructors()` (and the single-member lookup versions). `Declared` means **declared by the type itself**, not "get private only".

## 2. Comparison Matrix of the Six APIs

The input to these APIs is a `Class<?>` object, such as `Child.class` or `object.getClass()`. They return metadata from `java.lang.reflect`; they do not invoke methods, read fields, or instantiate objects themselves.

| API | Metadata type | Access levels listed | Considers inherited members? |
| --- | --- | --- | --- |
| `getMethods()` | `Method[]` | `public` methods | **Yes**: of the class and inherited from superclasses/superinterfaces |
| `getDeclaredMethods()` | `Method[]` | `public`, `protected`, package-private, `private` | **No**: only methods declared on the current type |
| `getFields()` | `Field[]` | `public` fields | **Yes**: of the class and inherited from superclasses/superinterfaces |
| `getDeclaredFields()` | `Field[]` | `public`, `protected`, package-private, `private` | **No**: only fields declared on the current type |
| `getConstructors()` | `Constructor<?>[]` | `public` constructors of the class itself | **No**: constructors are not inherited |
| `getDeclaredConstructors()` | `Constructor<?>[]` | All constructors declared on the class itself | **No**: constructors are not inherited |

Two questions help choose the API:

1. **Need to see public members in the API set visible through the type, including inherited ones?** Choose `getMethods()` or `getFields()`.
2. **Need to inspect members declared by the type itself, including private ones?** Choose `getDeclaredMethods()` or `getDeclaredFields()`.

For constructors, you only need to ask **public or all access levels**; there are no inherited constructors to look up.

### 2.1. `getMethods()` and `getDeclaredMethods()`

- `getMethods()` returns `public` methods exposed on the class/interface and from the hierarchy that this API considers. For a **class**, the result usually includes public methods from `Object`; for an **interface**, implicit `Object` methods are not automatically added.
- `getDeclaredMethods()` lists methods actually declared in that type: it can contain `private`, `protected`, package-private, and `public`, but **does not traverse up to the superclass**. Inherited `public` methods still do not appear if the subclass does not declare/override them itself.
- A `private` method in the parent class is not "inherited" in the usual sense; if you need to observe it, you must call `Parent.class.getDeclaredMethods()`.
- Compiler-generated methods, such as **bridge methods** for generics/covariant return types, may also appear. Do not assume each element corresponds to a method written directly in the source code.

### 2.2. `getFields()` and `getDeclaredFields()`

- `getFields()` returns `public` fields of the type and inherited `public` fields. Constants declared in an interface are `public static final` by default, so they can appear through a class implementing that interface.
- `getDeclaredFields()` returns all fields **declared on the type itself** regardless of modifier; it does not include fields from parent classes or interfaces that the type merely inherits.
- Fields and methods have different "hiding"/"overriding" rules: fields **do not override** via the polymorphic dispatch mechanism of methods. Therefore, you should not infer that "same name" means the same member; read `Field.getDeclaringClass()` to identify the owner.

### 2.3. `getConstructors()` and `getDeclaredConstructors()`

- `getConstructors()` only returns `public` constructors of the **current class**.
- `getDeclaredConstructors()` returns all constructors of the **current class**, including `private`, `protected`, package-private, and `public` constructors.
- **Constructors are not inherited**; `Child.class.getConstructors()` never lists `Parent`'s constructors just because `Child extends Parent`.
- The default constructor provided by the compiler (when a class declares no constructors) can still be reflected as a constructor of that class. Interfaces, primitives, `void`, and arrays have no constructors listed through these APIs.
- `getConstructors()` returns an empty array if the class has no public constructor; that **does not** prove the class cannot have a private constructor.

## 3. Standalone Runnable Java 17+ Example

The example has a superclass, an interface with a default method and a constant, inherited public method/field, private members of the subclass, along with two constructors at different access levels.

Save all of the following code as **`ReflectionInventoryDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

interface Tagged {
    int CODE = 7; // implicitly public static final
    default String tag() {
        return "tag";
    }
}

class Parent {
    public String inheritedField = "parent";
    protected int protectedField;
    private int privateField;

    public Parent() {}

    public void inheritedMethod() {}
    protected void protectedMethod() {}
    private void privateMethod() {}
}

class Child extends Parent implements Tagged {
    public int ownField;
    private int secret;

    public Child() {}
    private Child(int id) {}

    public void ownMethod() {}
    private void hiddenMethod() {}
}

public class ReflectionInventoryDemo {
    private static boolean hasMethod(Method[] methods, String name) {
        return Arrays.stream(methods)
                .anyMatch(method -> method.getName().equals(name));
    }

    private static boolean hasField(Field[] fields, String name) {
        return Arrays.stream(fields)
                .anyMatch(field -> field.getName().equals(name));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Class<Child> type = Child.class;

        System.out.println("inheritedMethod / getMethods: "
                + hasMethod(type.getMethods(), "inheritedMethod"));
        System.out.println("inheritedMethod / getDeclaredMethods: "
                + hasMethod(type.getDeclaredMethods(), "inheritedMethod"));
        System.out.println("tag / getMethods: "
                + hasMethod(type.getMethods(), "tag"));
        System.out.println("hiddenMethod / getMethods: "
                + hasMethod(type.getMethods(), "hiddenMethod"));
        System.out.println("hiddenMethod / getDeclaredMethods: "
                + hasMethod(type.getDeclaredMethods(), "hiddenMethod"));

        System.out.println("inheritedField / getFields: "
                + hasField(type.getFields(), "inheritedField"));
        System.out.println("CODE / getFields: "
                + hasField(type.getFields(), "CODE"));
        System.out.println("inheritedField / getDeclaredFields: "
                + hasField(type.getDeclaredFields(), "inheritedField"));
        System.out.println("secret / getFields: "
                + hasField(type.getFields(), "secret"));
        System.out.println("secret / getDeclaredFields: "
                + hasField(type.getDeclaredFields(), "secret"));

        System.out.println("constructors / getConstructors: "
                + type.getConstructors().length);
        System.out.println("constructors / getDeclaredConstructors: "
                + type.getDeclaredConstructors().length);

        System.out.println("inheritedMethod owner: "
                + type.getMethod("inheritedMethod")
                        .getDeclaringClass().getSimpleName());
        System.out.println("private ctor owner: "
                + type.getDeclaredConstructor(int.class)
                        .getDeclaringClass().getSimpleName());
    }
}
```

Run from the directory containing the file using JDK 17 or higher:

```bash
javac ReflectionInventoryDemo.java
java ReflectionInventoryDemo
```

Expected output of the example:

```text
inheritedMethod / getMethods: true
inheritedMethod / getDeclaredMethods: false
tag / getMethods: true
hiddenMethod / getMethods: false
hiddenMethod / getDeclaredMethods: true
inheritedField / getFields: true
CODE / getFields: true
inheritedField / getDeclaredFields: false
secret / getFields: false
secret / getDeclaredFields: true
constructors / getConstructors: 1
constructors / getDeclaredConstructors: 2
inheritedMethod owner: Parent
private ctor owner: Child
```

**Explanation based on the output:**

- `inheritedMethod` is a public method declared in `Parent` and inherited by `Child`. Therefore `Child.class.getMethods()` sees it, whereas `Child`'s `getDeclaredMethods()` does not.
- `tag` is a default method from interface `Tagged`, present in the public method set of `Child`.
- `hiddenMethod` and field `secret` are private members declared by `Child`: only the corresponding `getDeclared...` variants can list them.
- `inheritedField` is a public field of `Parent`, and `CODE` is a public constant of `Tagged`; `Child`'s `getFields()` can see both.
- `Child` declares one no-arg public constructor and one private constructor taking `int`: the results are **1** and **2**, respectively. The `Parent()` constructor is not in `Child`'s results.
- `getDeclaringClass()` identifies the **actual declaring class**, not just the class we are using to query.

The code checks **presence/absence** instead of printing the entire array directly: the order of elements returned by Reflection is **not guaranteed**, and the number of public methods from the platform library can make the list long and hard to compare.

## 4. Looking Up a Single Member by Name

When the name or signature is known in advance, use the singular form to avoid looping through an array yourself:

| Search in public API, with inheritance when applicable | Search for a member declared directly on the type |
| --- | --- |
| `getMethod("name", parameterTypes...)` | `getDeclaredMethod("name", parameterTypes...)` |
| `getField("fieldName")` | `getDeclaredField("fieldName")` |
| `getConstructor(parameterTypes...)` | `getDeclaredConstructor(parameterTypes...)` |

For example, given `Class<Child> type = Child.class`:

```java
// These lines are an illustrative snippet, used in the context of the example above.
Method fromParent = type.getMethod("inheritedMethod");
Method ownPrivate = type.getDeclaredMethod("hiddenMethod");
Field inherited = type.getField("inheritedField");
Field ownPrivateField = type.getDeclaredField("secret");
var publicCtor = type.getConstructor();
var privateCtor = type.getDeclaredConstructor(int.class);
```

Points to remember:

- For methods, the `Class<?>...` parameters represent **parameter types in exact order**, not argument values: `getMethod("setAge", int.class)` differs from `getMethod("setAge", Integer.class)`. A no-arg method uses `getMethod("run")`.
- The return type is **not** in the argument list of `getMethod`/`getDeclaredMethod`. If you need to distinguish bridge/covariant variants, also check `getReturnType()`, `isBridge()`, and `isSynthetic()`.
- `getMethod` searches for public methods according to Reflection's member lookup rules; `getDeclaredMethod` only searches within the declarations of that exact type. The corresponding constructor APIs only consider the class itself.
- If not found, it throws `NoSuchMethodException` (method/constructor) or `NoSuchFieldException` (field); **it does not return `null`**. Many programs need `try/catch` or a `throws` declaration.
- `getDeclaringClass()` on `Method`, `Field`, `Constructor` helps verify which class/interface the retrieved member belongs to.

## 5. `getDeclaredXxx` Does Not Mean Access Is Granted

**Two separate steps:** (1) finding the member's metadata, (2) operating on the member via `Method.invoke`, `Field.get/set`, or `Constructor.newInstance`.

For example: `Child.class.getDeclaredMethod("hiddenMethod")` finds the private method; calling `invoke` from a class without access rights can still be rejected. If the application has a valid reason for needing reflective access, you can check:

```java
// Snippet: assuming we already have Child child and Method hidden retrieved above.
if (hidden.trySetAccessible()) {
    hidden.invoke(child);
} else {
    // Access cannot be opened; choose a public API or another integration approach.
}
```

- `trySetAccessible()` returns `false` when deep access cannot be enabled; `setAccessible(true)` can throw `InaccessibleObjectException` if the module does not open the package to the caller.
- On Java 9+ (especially when using named modules), **exports** and **opens** are different: `exports` supports normal type/public API access, whereas reflective access to non-public members of another module usually requires the package to be appropriately `opens`.
- A member with the `public` modifier may still not be callable from everywhere if the declaring type or module boundary is not accessible. Appearing in `getMethods()` or `getFields()` is not a license to bypass access control.
- Only open access when there is a clear intent; prefer public APIs. Do not add `--add-opens` by default to fix every error, because it changes encapsulation configuration and impacts maintainability.

Note: the `trySetAccessible` snippet is **illustrative code**, not a standalone Java program. It may require handling additional checked exceptions from `invoke` in real code.

## 6. Confusing Corner Cases

### 6.1. `getDeclaredMethods()` does not walk up the inheritance tree

Suppose `GrandParent -> Parent -> Child`. Calling `Child.class.getDeclaredMethods()` only considers methods declared by `Child`; calling `Parent.class.getDeclaredMethods()` considers methods declared in `Parent`. If you need all access levels across multiple classes, you can **traverse superclasses yourself**:

```java
// Illustrative snippet, requires importing java.lang.reflect.Method, java.util.*.
List<Method> declaredOnClassChain = new ArrayList<>();
for (Class<?> current = Child.class;
        current != null;
        current = current.getSuperclass()) {
    declaredOnClassChain.addAll(Arrays.asList(current.getDeclaredMethods()));
}
```

The snippet above intentionally traverses only the **superclass chain**, not interfaces. If requirements include members declared in parent interfaces, you must traverse `getInterfaces()` recursively separately, with a `visited` set to avoid revisiting and handle duplicate signatures when needed. Manual traversal also does not automatically allow invoking private members.

### 6.2. `getMethods()` does not mean "every possible method"

- It only lists **public** methods according to the API's rules; `protected`, package-private, and `private` are not included just because they appear somewhere in the hierarchy.
- For classes, public methods inherited from `Object` (e.g., `toString`) can also be present. For interfaces, implicit `Object` methods are not automatically added to `getMethods()`.
- `static` methods of an interface are not inherited by implementing classes like default methods, so do not assume `Child.class.getMethods()` must see every static method of `Tagged`.
- Overriding, multiple interface inheritance, bridge methods, and covariant return types can make the result more complex than naively concatenating parent/child arrays.

### 6.3. Do not rely on order or exact count

The Javadoc does not guarantee the order of the returned arrays. If building documentation generation UIs, snapshot tests, or reports, **sort explicitly** by appropriate criteria: name, parameter type list, `getDeclaringClass()`, and return type for methods. Also do not infer that "having two elements with the same name means the API is buggy": overloaded methods and bridge methods are valid cases.

### 6.4. "Declared" means declared at the bytecode/class level, not necessarily having a corresponding source line

The compiler can generate synthetic fields/methods, bridge methods, or constructor parameters to support language constructs. The `getDeclared...` APIs can reflect them. When using Reflection to generate schemas/JSON or list user-facing APIs, consider `Member.isSynthetic()`, `Method.isBridge()`, modifiers, and business requirements; do not blindly filter out all synthetic members.

### 6.5. Special classes

- For `String[].class`, the APIs listing declared methods/fields do not behave like a regular source class; arrays have no listed constructors of their own. `getMethods()` on an array returns public methods inherited from `Object` but does not list `clone()`.
- For `int.class` or `void.class`, there are no constructors/methods/fields declared like a regular Java class.
- Interfaces have no constructors; `getDeclaredMethods()` on an interface can list methods declared by the interface itself, including default, static, and private methods (depending on the Java version).

## 7. Choosing an API in Practical Scenarios

| Need | Recommended starting API | Reason |
| --- | --- | --- |
| List public methods that callers can find through a class, including inherited ones | `getMethods()` | Covers public methods in the hierarchy |
| Generate documentation for methods *directly declared* in a class | `getDeclaredMethods()` | Excludes inherited methods; filter modifiers/bridges if needed |
| Scan annotations on fields owned by the class itself, including private ones | `getDeclaredFields()` | Does not miss non-public fields declared by the class |
| List public constants from a class/interface and inherited ones | `getFields()` | Includes public fields from the relevant hierarchy |
| Find a public no-arg constructor | `getConstructor()` | Only public constructors of the current class |
| Analyze or find a private constructor | `getDeclaredConstructors()` / `getDeclaredConstructor(...)` | Sees all access levels, though invocation is still access-controlled |
| Collect private and protected fields from multiple superclasses | Traverse `getSuperclass()` + `getDeclaredFields()` per class | There is no single `getDeclaredFields()` call that automatically traverses the entire hierarchy |

For frameworks like DI, serializers, or ORMs, **the criteria of "where it is declared" and "which access level" must be decided upfront**. Choosing `getFields()` for an entity with private fields will easily lead to missing data; conversely, using `getDeclaredMethods()` to find inherited public handlers can miss handlers located in the parent.

## 8. Self-Check Exercises

1. `Parent` has `protected void audit()`, and `Child` does not override it. Do `Child.class.getMethods()` and `Child.class.getDeclaredMethods()` contain `audit`? **Answer:** neither does. `Parent.class.getDeclaredMethods()` does.
2. `Child` has `public void run()` and `private void reset()`. To see both without considering inherited methods, what should you use? **Answer:** `Child.class.getDeclaredMethods()`.
3. `Parent` has `public Parent(String id)`, and `Child` only declares `public Child()`. Does `Child.class.getConstructors()` have `Parent`'s constructor taking `String`? **Answer:** no, constructors are not inherited.
4. `Child` has `private int count`. If `Child.class.getDeclaredField("count")` runs successfully, does it guarantee `field.get(child)` will succeed from another class? **Answer:** no; access rights and module boundaries must be checked.
5. A `Method[]` array from `getDeclaredMethods()` contains a bridge method. Should you assume by default that it is a Reflection bug? **Answer:** no; this can be valid compiler-generated metadata, and you should check `isBridge()`/`isSynthetic()` depending on your processing purpose.

## 9. Quick Summary and References

**Public + inherited (methods/fields)** → `getMethods()` / `getFields()`. **Declared on the exact type + all access levels** → `getDeclaredMethods()` / `getDeclaredFields()`. **Constructors are not inherited** → `getConstructors()` only gets public ones, `getDeclaredConstructors()` gets all access levels of the class itself.

When in doubt, check `getDeclaringClass()`, `getModifiers()`, `isSynthetic()`, `isBridge()` (for methods) and handle access control separately from the lookup process.

- [Oracle Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): contract of `getMethods`, `getFields`, `getConstructors`, and all `getDeclared` variants.
- [Oracle Java SE 17 — `java.lang.reflect.AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible`, and the scope of reflective access control.
- [Oracle Java SE 17 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): package `exports` and `opens` model when using modules.
