# Looking Up Public or Declared Constructors in Java Reflection

## 1. Why Look Up Constructors?

In Java, `Constructor` is the component used to create an instance of a class. Java Reflection provides `java.lang.reflect.Constructor<T>` to find, list, and read constructor information at runtime. As a result, dependency injection libraries, serializers, ORMs, test frameworks, and diagnostic tools can select constructors based on a class received at runtime.

For example, when only `Class<?> type` is available, a program cannot always write `new SomeClass(...)` directly because the class name or constructor signature is not known ahead of time. Reflection allows discovering constructors via `type.getConstructor(...)`, `type.getDeclaredConstructor(...)`, and their listing variants. However, **looking up metadata** is different from **being allowed to invoke the constructor**: finding a `private` constructor does not automatically grant permission to create objects.

This lesson focuses on the difference between the two API families **public** and **declared**, how to choose the right overload, access scope, and special cases that easily cause `NoSuchMethodException` or `IllegalAccessException`. Examples use Java 17 or later.

## 2. The Four Most Important APIs

| Purpose | API in `Class<T>` | Result | Scope |
| --- | --- | --- | --- |
| Find a public constructor | `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | `public` constructor with exact parameter type list |
| List public constructors | `getConstructors()` | `Constructor<?>[]` | All `public` constructors declared in the class |
| Find a directly declared constructor | `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor matching signature, regardless of `public`, `protected`, package-private, or `private` |
| List all directly declared constructors | `getDeclaredConstructors()` | `Constructor<?>[]` | Every constructor of the class, regardless of access modifier |

Single-lookup methods typically throw `NoSuchMethodException` if no matching constructor is found; listing methods return an array (possibly empty) and **do not guarantee element order**.

**Core difference:** the word `Declared` here means *declared in the current class*, not "private-only constructors" or "disable access checks". For example, `getDeclaredConstructor()` still finds a `public` constructor if the class declares that no-arg constructor.

### Constructors Are Not Inherited

Unlike methods or fields, **constructors are not inherited** from a superclass. Therefore, `Child.class.getConstructors()` never lists constructors of `Parent`. Both API families always examine the constructors of the exact class represented by the `Class` object.

In other words, the contrast between `getConstructor()` and `getDeclaredConstructor()` is primarily **public modifier scope** versus **any modifier**, not a choice between "inherited" and "non-inherited".

## 3. Looking Up the Exact Signature: Constructor Name Is Not Passed

There is no name parameter when looking up a constructor. The `Class` already identifies the owning type name; the method only takes the **parameter type list in exact order**.

```java
Constructor<User> noArgs = User.class.getConstructor();
Constructor<User> byName =
        User.class.getDeclaredConstructor(String.class);
Constructor<User> byNameAndAge =
        User.class.getDeclaredConstructor(String.class, int.class);
```

This is an illustrative snippet inside a method that handles or declares `NoSuchMethodException`; it assumes `User` actually declares the corresponding constructors, and `java.lang.reflect.Constructor` has been imported.

Signature selection rules:

- Calling `getConstructor()` or `getDeclaredConstructor()` with no arguments requests a **no-arg** constructor.
- `String.class, int.class` **differs from** `int.class, String.class`. Parameter order must match.
- `int.class` differs from `Integer.class`, and `long.class` differs from `int.class`. Reflection **does not perform automatic boxing/unboxing or primitive widening during signature lookup**.
- For `String... args`, the runtime signature uses `String[]`; look it up with `String[].class`.
- For generic types like `List<String>`, signature metadata after **type erasure** uses `List.class`. There is no valid `List<String>.class` expression.
- Parameter types are `Class<?>` objects; do not pass strings like `"String"` or `"int"` into `getConstructor`.

These two overloaded constructors have different signatures:

```java
public User(String name) { /* ... */ }
public User(String name, int age) { /* ... */ }
```

Do not assume "Java automatically chooses the best-matching constructor" for lookup methods: this is an **exact signature** search, not overload resolution performed when the compiler compiles `new User(...)`.

## 4. Complete Java 17 Example: public vs declared

The following example intentionally has four constructors: two `public`, one `protected`, and one `private`. A `Child` class is also included to demonstrate that constructors are not inherited.

Save the **entire** code to the file `ConstructorLookupDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class ConstructorLookupDemo {
    private static String signature(Constructor<?> ctor) {
        return "(" + Arrays.stream(ctor.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ")) + ")";
    }

    private static String signatures(Constructor<?>[] ctors) {
        return Arrays.stream(ctors).map(ConstructorLookupDemo::signature)
                .sorted().collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        Class<Account> type = Account.class;
        System.out.println("public: " + signatures(type.getConstructors()));
        System.out.println("declared: " + signatures(type.getDeclaredConstructors()));

        Constructor<Account> protectedOne =
                type.getDeclaredConstructor(String.class);
        System.out.println("declared String: "
                + Modifier.toString(protectedOne.getModifiers()));

        Constructor<Account> privateTwo =
                type.getDeclaredConstructor(String.class, int.class);
        System.out.println("private accessible: " + privateTwo.canAccess(null));
        try {
            privateTwo.newInstance("Ada", 3);
        } catch (IllegalAccessException expected) {
            System.out.println("private call: IllegalAccessException");
        }

        Constructor<Account> publicVarargs = type.getConstructor(int[].class);
        System.out.println("varargs marker: " + publicVarargs.isVarArgs());
        Account account = type.getConstructor().newInstance();
        System.out.println("created: " + account.label());

        try {
            type.getConstructor(String.class);
        } catch (NoSuchMethodException expected) {
            System.out.println("public String lookup: NoSuchMethodException");
        }

        System.out.println("child public: "
                + signatures(Child.class.getConstructors()));
    }
}

class Account {
    private final String owner;
    private final int level;

    public Account() { this("guest", 0); }
    protected Account(String owner) { this(owner, 1); }
    private Account(String owner, int level) {
        this.owner = owner;
        this.level = level;
    }
    public Account(int... levels) { this("levels", levels.length); }

    public String label() { return owner + ":" + level; }
}

class Parent {
    public Parent(int value) {}
}

class Child extends Parent {
    public Child() { super(0); }
}
```

Compile and run with JDK 17 or later:

```bash
javac ConstructorLookupDemo.java
java ConstructorLookupDemo
```

Standard output, verified on JDK 21 with `javac --release 17`:

```text
public: [(), (int[])]
declared: [(), (String), (String, int), (int[])]
declared String: protected
private accessible: false
private call: IllegalAccessException
varargs marker: true
created: guest:0
public String lookup: NoSuchMethodException
child public: [()]
```

### 4.1. Why Do the public and declared Lists Differ?

`Account.class.getConstructors()` sees exactly two `public` constructors: `Account()` and `Account(int... levels)`. At the bytecode level, varargs is represented by an `int[]` array, so the program prints the signature `(int[])`.

`Account.class.getDeclaredConstructors()` sees **all four** constructors declared directly in `Account`: two `public`, one `protected`, one `private`. Each member is returned as a `Constructor<?>` object.

To make the output readable and testable, the `signatures` method uses `sorted()`. **Do not use the array order returned by Reflection as a priority order**, for example do not pick `getDeclaredConstructors()[0]` and assume it is the no-arg constructor.

### 4.2. Why Does getDeclaredConstructor Succeed Yet Cannot Be Invoked?

`getDeclaredConstructor(String.class, int.class)` finds the `private` constructor. However, the `ConstructorLookupDemo` program is an **independent top-level class** separate from `Account`, so it does not have normal permission to invoke the `private` constructor.

- `privateTwo.canAccess(null)` returns `false`.
- `privateTwo.newInstance("Ada", 3)` throws `IllegalAccessException`.
- There is no `setAccessible(true)` call in the program.

This illustrates two independent aspects: **looking up metadata** and **permission to use metadata to create objects**. If the caller is placed inside a valid nestmate of the declaring class, or has a different access configuration, the check result may differ.

### 4.3. Why Does getConstructor(String.class) Report No Constructor Found?

`Account` has `protected Account(String owner)`, so the `getDeclaredConstructor(String.class)` version succeeds. `getConstructor(String.class)` only searches for `public` constructors and throws `NoSuchMethodException`, even though the signature exists. This is a mistake in choosing the **lookup API**, not Java failing to recognize `String.class`.

### 4.4. Why Does Parent's Constructor Not Appear on Child?

`Parent` declares `public Parent(int value)`; `Child` only declares `public Child()`. `Child.class.getConstructors()` therefore only has `Child()`. Each constructor initializes a specific class; the `super(0)` statement inside `Child()` calls the parent constructor through normal object initialization mechanics, **without turning the parent constructor into an inherited member**.

## 5. Reading Metadata from Constructor<?>

After finding a `Constructor<?>` object, you can inspect the following information:

| API | Meaning |
| --- | --- |
| `getDeclaringClass()` | Class that declares and owns the constructor |
| `getParameterCount()` | Number of parameters in the runtime signature |
| `getParameterTypes()` | Array of parameter types as `Class<?>[]` in order |
| `getGenericParameterTypes()` | Parameter types as `Type[]`, supporting generic signature analysis when present |
| `getParameters()` | `Parameter[]` array to inspect parameter names/annotations/modifiers |
| `getExceptionTypes()` | Checked/unchecked exception types declared in `throws` |
| `getModifiers()` | Constructor modifiers, combined with `Modifier.isPublic`, `isPrivate`, `isProtected` |
| `isVarArgs()` | Whether the constructor declares a variable argument `...` |
| `isSynthetic()` | Whether the constructor was generated by the compiler as synthetic |
| `isAnnotationPresent(...)` | Check runtime annotations on the constructor |

For example, the following snippet is placed **inside a method**, assuming `Account` is the same as in the previous section:

```java
Constructor<Account> ctor =
        Account.class.getDeclaredConstructor(String.class, int.class);

System.out.println(ctor.getDeclaringClass().getSimpleName()); // Account
System.out.println(ctor.getParameterCount());                 // 2
System.out.println(Modifier.isPrivate(ctor.getModifiers())); // true
```

If using `getParameters()[i].getName()` to generate API documentation, remember that **actual parameter names are not always preserved in the class file**. In plain Java examples, add the flag `javac -parameters ...` if parameter names need to be stored; otherwise you may get synthesized names like `arg0`, `arg1`. To analyze annotations or actual generic types, prefer the corresponding metadata APIs rather than inferring from `toString()`.

You can use `Constructor.toGenericString()` to view a human-readable representation; however, if you need stable output across environments, extract metadata fields structurally and format them yourself.

## 6. Metadata Lookup Differs from Object Creation

`getConstructor(...)` and `getDeclaredConstructor(...)` only look up the signature; they do not execute initialization code yet. After lookup, `ctor.newInstance(args)` checks access, arguments, and creates the instance. For example, from the `Account` example above: `Account.class.getConstructor().newInstance().label()` returns `guest:0`.

A constructor declared with varargs such as `Account(int... levels)` has a runtime signature of `int[]`. To pass an array as a single argument, use `getConstructor(int[].class).newInstance((Object) new int[]{1, 2, 3})`. Arguments must match the chosen signature; Reflection does not perform overload resolution during lookup.

## 7. Constructor Found but Cannot Be Invoked

`getDeclaredConstructor` sees `private` constructors as well; it does not bypass Java access checks. `canAccess(null)` checks the current access status against `Constructor`. If a framework needs deep reflection, `trySetAccessible()` may return `false` due to JPMS: packages in a named module typically must be appropriately `opens`. Therefore, check the accessibility of the declaring class as well, not just the constructor modifier.

Prefer public APIs/factories when possible. If you must open access, check the result and handle `IllegalAccessException` or `InaccessibleObjectException` transparently.

## 8. Signatures That Differ from Ordinary Java Syntax

- No `getConstructor()` call will succeed if a class only declares parameterized constructors; the compiler does not auto-generate a no-arg constructor in this case.
- Non-static inner classes have an extra enclosing instance parameter at the start, unlike static nested classes.
- Generic `List<String>` undergoes erasure to `List.class` on lookup; varargs `String...` becomes `String[].class`.
- Abstract classes can have constructors but cannot be instantiated directly; interfaces, arrays, and primitives do not have ordinary class constructors. Enum constructors have their own instantiation restrictions.
- Superclass constructors do not appear in a subclass's constructor list, even though subclass code calls `super(...)`.

Those cases do not change the main rule: `Class.get[Declared]Constructor` matches the **exact count, order, and runtime type** of each parameter.

## 9. Diagnosing the Exact Failing Step

| Result | First thing to check |
| --- | --- |
| `NoSuchMethodException` | Signature and public/declared scope of the lookup API |
| `IllegalAccessException` | Caller, declaring class, visibility, and module |
| `IllegalArgumentException` | Count and actual types of arguments passed to `newInstance` |
| `InstantiationException` | Whether the class is abstract |
| `InvocationTargetException` | `getCause()` to find the throwable thrown while running the constructor |
| `ExceptionInInitializerError` | Static initialization occurring before the constructor |

Do not `catch (Exception ignored)` and assume every error is a lookup failure. Distinguishing lookup, access, class initialization, and instance initialization helps fix the right root cause.

## 10. Choosing a Lookup Strategy in Applications

If a framework wants to create objects from metadata, it should define a transparent **constructor selection rule**:

1. Know the target `Class<?>`, the supported constructor scope, and whether non-public constructors are needed.
2. If a specific signature is known, prefer `getConstructor(types...)` or `getDeclaredConstructor(types...)` according to the permission policy.
3. If discovering multiple constructors is needed, get the list with `getConstructors()` or `getDeclaredConstructors()`; **filter by parameter types/annotations** and sort according to application criteria.
4. Before creating an object, verify parameter types, accessibility, module, and business semantics; do not use a random constructor just because `array[0]` appears first.
5. When running `newInstance`, distinguish exceptions from the Reflection mechanism from errors originating inside the constructor.

For example, if looking for a `public` constructor taking a string, you can call:

```java
Constructor<?> selected =
        type.getConstructor(String.class);
```

This snippet is suitable when the exact signature is known; there is no need to iterate through the entire list. Conversely, if a framework supports multi-parameter injection by annotations and has overload selection rules, read all relevant metadata and define a deterministic selection strategy, rather than trying each constructor until one does not throw an error.

With a class being a runtime type that can be created dynamically, remember that the existence of a matching constructor proves only a **necessary** condition, not the full **sufficient** condition: the constructor may be access-restricted, class initialization may fail, or the body may have side effects.

## 11. Self-Check

**Question 1.** Why can't `Account.class.getConstructor(String.class)` find the constructor even though the class declares `Account(String)`?

**Answer:** That constructor is `protected`. `getConstructor` only finds `public` constructors; `getDeclaredConstructor(String.class)` finds it because it considers all modifiers.

**Question 2.** What is the difference between `Account.class.getConstructors()` and `Account.class.getDeclaredConstructors()`?

**Answer:** The first lists `public` constructors; the second lists all constructors declared directly in `Account`, including non-public ones.

**Question 3.** Can you get the `Account(int... values)` constructor using `getConstructor(int.class)`?

**Answer:** No. The runtime signature uses `int[]`, so you must call `getConstructor(int[].class)`.

**Question 4.** Does `Child.class.getConstructors()` contain `Parent(int)`?

**Answer:** No. Constructors are not inherited; `Child` only has its own constructors.

**Question 5.** Why does finding a `private` constructor not guarantee `ctor.newInstance()` will succeed?

**Answer:** Metadata lookup and execution permission checks are two independent things. Callers outside normal access scope may get `IllegalAccessException`, or be restricted by modules when trying to bypass checks.

**Question 6.** Why might `getDeclaredConstructor(int.class)` fail on `Outer.Inner` even though the source is written `Inner(int)`?

**Answer:** A non-static inner class has an implicit outer-instance parameter in its runtime signature, typically requiring lookup with `(Outer.class, int.class)`.

**Question 7.** Can `Constructor.newInstance` be used to create a new enum constant?

**Answer:** No. Reflection does not allow creating new enums via constructors in this way.

**Key takeaway:** `getConstructor(s)` looks up **public constructors of the class itself**, while `getDeclaredConstructor(s)` looks up **all constructors declared directly in the class**. Both rely on the **exact list of parameter types**; having metadata does not imply having permission to invoke. For flexible runtime code, check modifiers, declaring class, varargs/generic signatures, and `newInstance` limitations before instantiating objects.
