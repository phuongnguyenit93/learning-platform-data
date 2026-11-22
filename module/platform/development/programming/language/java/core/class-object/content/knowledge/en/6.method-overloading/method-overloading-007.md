# Distinguishing Overloading, Overriding, and Hiding in Java

## 1. Three Mechanisms with the Same Method Name but Different Meanings

In Java, when encountering two declarations with the same name, you cannot immediately conclude whether they are **overloading** or **overriding**. You must examine the **parameter list**, the **parent–child class relationship**, whether they are **instance or static methods**, and sometimes even the **type of the calling expression**. In addition, duplicate field names between a parent class and a child class, or a local variable sharing a field's name, can lead to forms of **hiding/shadowing** with rules that differ from those for methods.

- **Overloading:** multiple methods with the **same name** and **validly different parameter lists**. The compiler selects the applicable signature based on the **static types of the arguments**, the number of parameters, conversions, and the *most-specific* rule. Overloading can occur within the same class or between inherited methods and newly declared ones.
- **Overriding:** a subclass provides an implementation for an **instance method** with a corresponding signature from a parent type according to Java rules. When calling an overridable method, the **actual type of the receiver object** determines which implementation runs at runtime (*dynamic dispatch*).
- **Hiding:** a declaration in a specific scope causes a member of the same name in another scope to no longer resolve as before. The case commonly studied alongside the two mechanisms above is **static method hiding**: a subclass declares a static method with a signature corresponding to a static method of the superclass. With **field hiding**, a field with the same name in a subclass also hides the superclass field when accessed under static-type rules; fields do not have dynamic dispatch.

> **Key takeaway:** *overloading selects the signature for a call at compile time; overriding selects the instance method implementation at runtime; static method hiding does not use dynamic dispatch*. Field hiding and local-variable shadowing are distinct forms of name hiding and must be distinguished from static method hiding.

## 2. Overall Comparison Table

| Criterion | Overloading | Overriding | Static method hiding |
| --- | --- | --- | --- |
| Do the methods have the same name? | Yes | Yes | Yes |
| Parameter list | Validly **different** | **Corresponding** per override rules | **Corresponding** per hiding rules |
| Inheritance relationship | Not required; can be in the same class | Appropriate supertype/subtype relationship | Typically between a subclass and a superclass |
| Method kind | Can be instance or static | **Instance method**, not static | **Static method** |
| Primary resolution | Compile time based on argument types and available overloads | Runtime based on the actual receiver, after the signature has been selected | Compile time based on the type at the reference site |
| `@Override` | Not used for methods that only overload | Should be used to verify overriding | Not used; static methods do not override |
| Return type | May differ, though **not sufficient** to overload | Must be compatible; reference types may be covariant | Must satisfy compatibility requirements per hiding rules |
| `final` | Can still be overloaded with a different signature | Cannot override a final instance method | Cannot hide a final static method |
| Runtime effect | Depends on the selected method; that instance method can still be overridden | Dispatches to the concrete implementation based on the object | Does not change target to the subclass static method just because the runtime object is a subclass |

The table covers **methods**. For **fields**, there is no overloading or overriding in the method sense. A field in a subclass with the same name as a field in the superclass can **hide the field**, even though both still exist in the object or class structure.

## 3. Standalone Runnable Example: Seeing All Three Mechanisms in the Same Hierarchy

Create the file **`PolymorphismComparisonDemo.java`** with the following complete Java 17+ code:

```java
class Parent {
    String label = "Parent.field";

    String describe() {
        return "Parent.instance";
    }

    static String category() {
        return "Parent.static";
    }

    String print(Object value) {
        return "Parent.print(Object)";
    }
}

class Child extends Parent {
    String label = "Child.field";

    @Override
    String describe() {
        return "Child.instance";
    }

    static String category() {
        return "Child.static";
    }

    String print(String value) {
        return "Child.print(String)";
    }
}

public class PolymorphismComparisonDemo {
    public static void main(String[] args) {
        Parent parentRef = new Child();
        Child childRef = new Child();

        System.out.println(parentRef.describe());
        System.out.println(childRef.describe());

        System.out.println(Parent.category());
        System.out.println(Child.category());
        System.out.println(parentRef.category());
        System.out.println(childRef.category());

        System.out.println(parentRef.print("Java"));
        System.out.println(childRef.print("Java"));
        System.out.println(childRef.print((Object) "Java"));

        System.out.println(parentRef.label);
        System.out.println(childRef.label);
        System.out.println(((Parent) childRef).label);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac PolymorphismComparisonDemo.java
java PolymorphismComparisonDemo
```

**Exact standard output:**

```text
Child.instance
Child.instance
Parent.static
Child.static
Parent.static
Child.static
Parent.print(Object)
Child.print(String)
Parent.print(Object)
Parent.field
Child.field
Parent.field
```

Four notable parts:

**A. Instance method overriding:** `parentRef` has **static type `Parent`** but points to a **`Child` object**. `parentRef.describe()` runs `Child.describe()` because it is an overridden instance method. `childRef.describe()` also runs that implementation.

**B. Static method hiding:** `Child.category()` declares a static method corresponding to `Parent.category()`. `Parent.category()` returns `Parent.static`, while `Child.category()` returns `Child.static`. Although Java allows the expression `parentRef.category()`, the result is still `Parent.static` based on the expression's **static type `Parent`**; `childRef.category()` returns `Child.static` based on **static type `Child`**. In real code, static methods should be called through the **class name**.

**C. Overloading:** `Parent.print(Object)` and `Child.print(String)` are two overloads (different parameters). Through the variable `Parent parentRef`, the compiler only finds `print(Object)` as applicable on type `Parent`, so `parentRef.print("Java")` returns `Parent.print(Object)`. Through the variable `Child childRef`, both signatures are visible and `print(String)` is more specific for a `String` argument. Casting the argument to `(Object) "Java"` causes `childRef.print((Object) "Java")` to select `print(Object)`. In this program, `Child` **does not override `print(Object)`**, so the method inherited from `Parent` executes.

**D. Field hiding:** `Parent.label` and `Child.label` are **two different fields** with the same name. Field access is resolved according to the **static type of the expression**: `parentRef.label` returns `Parent.field`, `childRef.label` returns `Child.field`, and casting `childRef` to `Parent` causes the field access to select `Parent.label`. The fact that the actual object is `Child` does not cause field dynamic dispatch.

**Observed conclusion:** the same `new Child()` can invoke an overridden method of `Child`, a static method selected by type `Parent`, an overload dependent on the argument type, and a field that shares a name yet is still selected by static type. You cannot use solely "what class is the actual object?" to answer all of them.

## 4. Overloading: Same Name, Different Parameter Lists

Two declarations create an overload when they have **validly different signatures**: differing in number of parameters, parameter types, type order, or signature relationships permitted by the JLS. In the non-generic case, you can remember **name + ordered list of parameter types** as the core factor. Parameter names and return types cannot be used to distinguish two methods with the same signature.

```java
class Converter {
    String convert(int number) {
        return "int=" + number;
    }

    String convert(long number) {
        return "long=" + number;
    }

    String convert(String text, boolean uppercase) {
        return uppercase ? text.toUpperCase() : text;
    }

    String convert(boolean uppercase, String text) {
        return convert(text, uppercase);
    }
}
```

This is a **valid class declaration**, though it has no `main`. There are four overloads named `convert` with different parameter lists. The last two differ in the order of `String, boolean` and `boolean, String`.

Example that **intentionally does not compile**:

```java
// class Invalid {
//     int parse(String text) {
//         return Integer.parseInt(text);
//     }
//
//     long parse(String text) {
//         return Long.parseLong(text);
//     }
// }
```

The two `parse(String)` methods differ only in **return type**, so they are treated as duplicate declarations. Writing `public` instead of `private`, renaming the parameter `text` to `value`, changing `throws`, or adding `final` is also not sufficient to create an overload.

### Overloads Are Selected at Compile Time

Overload resolution examines:

1. The set of methods with the same name that are **discoverable and accessible** from the static type of the receiver/current scope.
2. The number of arguments, the static type of each argument, and the method conversions allowed by Java.
3. The applicability phases: matching without boxing/varargs first; next considering boxing/unboxing; and finally considering **variable arity** if needed.
4. The **most specific** overloads in the applicable phase; if there is no unique choice, the compiler reports it as **ambiguous**.

Even though the variable `Object value = "hello";` holds a `String` object, when calling `process(value)` the compiler sees an argument of type **`Object`** and does not automatically switch to the `process(String)` overload. This is a fundamental difference from override dispatch.

### Boxing, Widening, and Varargs

Create the file **`OverloadingRulesDemo.java`**:

```java
class Choice {
    static String choose(long n) {
        return "long";
    }

    static String choose(Integer n) {
        return "Integer";
    }

    static String choose(int... numbers) {
        return "varargs=" + numbers.length;
    }
}

public class OverloadingRulesDemo {
    public static void main(String[] args) {
        System.out.println(Choice.choose(7));
        System.out.println(Choice.choose(Integer.valueOf(7)));
        System.out.println(Choice.choose());
        System.out.println(Choice.choose(1, 2));
    }
}
```

```bash
javac OverloadingRulesDemo.java
java OverloadingRulesDemo
```

```text
long
Integer
varargs=0
varargs=2
```

- `choose(7)`: `7` has type `int`. Primitive widening `int → long` is considered before boxing `int → Integer`, so `choose(long)` is selected.
- `choose(Integer.valueOf(7))`: the expression type is `Integer`, matching `choose(Integer)` before the unboxing step.
- `choose()`: the `int...` variant accepts 0 elements.
- `choose(1, 2)`: the `int...` variant accepts two elements.

Each new overload can affect calls **upon recompilation**; for example, adding `convert(String)` to an API that previously only had `convert(Object)` can cause `convert("a")` to select the new version.

### `null` and Reference Parameters

`null` can apply to multiple reference types; if neither type is more specific than the other, the call can be ambiguous:

```java
class Logger {
    static void log(String text) { }
    static void log(Integer number) { }

    static void sample() {
        // log(null);           // Ambiguous error: String or Integer?
        log((String) null);     // Selects log(String).
        log((Integer) null);    // Selects log(Integer).
    }
}
```

The two methods above coexist validly; **only the commented-out `log(null)` line is an error**. With the `log(Object)` and `log(String)` overloads, `log(null)` typically selects `log(String)` because `String` is more specific than `Object`. The cast here **does not create an object**: the value remains `null`, and only the static type of the expression changes.

### Generics and Erasure

`void consume(List<String>)` and `void consume(List<Integer>)` cannot form two overloads in the same class, because both generic type arguments are erased to `List` at erasure, leading to a **name clash**.

```java
// import java.util.List;
//
// class InvalidGenerics {
//     void consume(List<String> names) { }
//     void consume(List<Integer> numbers) { }
//     // Compile error because both have the same erasure.
// }
```

Similarly, `void send(int... values)` and `void send(int[] values)` cannot be two separate overloads; the varargs parameter in the signature corresponds to the array type `int[]`. The rules for generic signatures and *override-equivalent signatures* have more detail than the simple rule of thumb "different declaration characters".

## 5. Overriding: Subclass Instance Method Replaces Inherited Implementation

**Overriding** occurs when a subtype provides an instance method that satisfies the signature, accessibility, and return-type rules corresponding to an instance method of the supertype. The **`@Override`** annotation is commonly used to have the compiler verify this intent.

```java
class Notification {
    String send() {
        return "generic";
    }
}

class EmailNotification extends Notification {
    @Override
    String send() {
        return "email";
    }
}
```

These are compilable class declarations, though without `main`. With `Notification n = new EmailNotification();`, the expression `n.send()` executes `EmailNotification.send()`. Selecting the implementation based on the **actual receiver object** is called **dynamic dispatch**.

### Signature and Return Type When Overriding

For ordinary non-generic methods, the overriding method has the same **name and list of parameter types**. The return type must be compatible:

- For primitive types or `void`, it cannot arbitrarily be changed to another type.
- For reference types, Java allows **covariant return**: a subclass may return a narrower reference type that is compatible with the return type of the overridden method.
- `throws` checked exceptions in the subclass must not be broader than what Java permits from the superclass method; they may be omitted or narrowed to compatible checked exceptions.
- You must not **reduce accessibility**: a `public` method of the superclass must remain `public` in the overriding method; a `protected` method may be overridden as `protected` or `public`, but not reduced to `private`.
- A `final` method cannot be overridden. A `private` method of the superclass is not inherited to be overridden under the normal mechanism; a method with the same name in a subclass can be a new declaration.
- A static method does not override an instance method; nor can an instance method override a static method with a valid corresponding signature.
- A package-private method in a superclass in a different package **is not necessarily inherited/overridden**; analysis must consider access privileges and packages, not just the shape of the signature.

Create the file **`CovariantOverrideDemo.java`**:

```java
class Food {
    String name() {
        return "food";
    }
}

class Bread extends Food {
    @Override
    String name() {
        return "bread";
    }
}

class Kitchen {
    Food prepare() {
        return new Food();
    }
}

class Bakery extends Kitchen {
    @Override
    Bread prepare() {
        return new Bread();
    }
}

public class CovariantOverrideDemo {
    public static void main(String[] args) {
        Kitchen kitchen = new Bakery();
        Food item = kitchen.prepare();

        System.out.println(item.name());
        System.out.println(item instanceof Bread);
    }
}
```

Run:

```bash
javac CovariantOverrideDemo.java
java CovariantOverrideDemo
```

```text
bread
true
```

`Bakery.prepare()` has return type `Bread`, which is a subtype of `Food`. This is a valid **covariant return** when overriding `Kitchen.prepare()`. The variable `kitchen` has static type `Kitchen` but runtime type `Bakery`, so it calls the subclass implementation and creates a `Bread`. The variable `item` has type `Food`, yet the receiver of `item.name()` is `Bread`, so the result is `bread`.

### `@Override` Helps Catch Typos

```java
class ParentService {
    void start(int retries) { }
}

class ChildService extends ParentService {
    @Override
    void start(int retries) { } // Valid.

    // @Override
    // void start(long retries) { }
    // If @Override is added on start(long) and there is no
    // corresponding method in the superclass/interface: compile error.
}
```

`start(long)` is an **overload** of `start(int)` (different parameter), not an override. The `@Override` annotation helps prevent accidentally creating an overload due to mistyping parameter types or parameter count when overriding was intended.

### An Abstract Method Can Be Overridden

`abstract` simply describes a method that does not yet have an implementation in the declaring type. A concrete subclass implements it with a corresponding method, which is an override/implementation relationship under Java rules. For example, `Runnable.run()` is a contract; the implementing class must provide `public void run()`, rather than creating an overload `run(String)` and treating that as sufficient.

### Overriding Does Not Require a Direct `extends` Declaration

A class can override a method **inherited indirectly** across multiple superclass levels, or implement a contract inherited from an interface. Eligibility depends on the type hierarchy relationship and Java rules. You should not check by merely opening the immediate superclass file and concluding the method is missing.

## 6. Static Method Hiding: Same Name and Signature, but Static Binding

When a superclass has a static method and a subclass declares a static method with a valid corresponding signature, the subclass method **hides** the superclass method. This is **not overriding**.

Create the file **`StaticHidingDemo.java`**:

```java
class BaseConfig {
    static String source() {
        return "base";
    }
}

class AppConfig extends BaseConfig {
    static String source() {
        return "app";
    }
}

public class StaticHidingDemo {
    public static void main(String[] args) {
        BaseConfig base = new AppConfig();
        AppConfig app = new AppConfig();

        System.out.println(BaseConfig.source());
        System.out.println(AppConfig.source());
        System.out.println(base.source());
        System.out.println(app.source());
    }
}
```

```bash
javac StaticHidingDemo.java
java StaticHidingDemo
```

```text
base
app
base
app
```

Both `base` and `app` point to runtime objects of type `AppConfig`. However, `base.source()` is statically resolved based on the variable's type `BaseConfig`, returning `base`. `app.source()` is resolved based on the type `AppConfig`, returning `app`.

Some IDEs/compilers may warn about calling a static method through a reference variable because this syntax is easily confused with dynamic dispatch. **A better way to write it** is `BaseConfig.source()` and `AppConfig.source()`, explicitly stating which class the method belongs to. The two calls through variables in the example are solely for observing static binding.

### `@Override` Is Invalid on Static Method Hiding

```java
class ParentUtil {
    static void reset() { }
}

class ChildUtil extends ParentUtil {
    // @Override             // If used -> compile error.
    static void reset() { }   // Valid static method hiding.
}
```

An `@Override` annotation on `ChildUtil.reset()` would be invalid, because static methods do not participate in instance method overriding.

### Constraints with `final` and Visibility

If a superclass static method is `final`, a subclass cannot declare a static method with a corresponding signature to hide it. The hiding declaration must also satisfy appropriate requirements for visibility, return type, and `throws`. Specifically, a static method cannot hide an instance method with the same signature in the superclass, and an instance method cannot override a static method with the same signature.

`static` relates only to the method declaration. Do not say "this method is static, so the runtime object determines the appropriate static version": that is precisely what static hiding does **not** do.

### Are Interface Static Methods Inherited Like Class Static Methods?

A static method declared in an **interface** is not inherited by classes implementing the interface in the way ordinary instance methods are inherited. For example:

```java
interface Tools {
    static String version() {
        return "v1";
    }
}

class ToolImpl implements Tools {
}
```

Calling `Tools.version()` is valid; calling `ToolImpl.version()` is not valid merely because `ToolImpl implements Tools`. If `ToolImpl` declares its own static method `version()`, it is that class's own method, **not an override of `Tools.version()`**. Static hiding analysis should follow the actual declaration relationships in the class hierarchy and the corresponding rules.

## 7. Field Hiding: Field Names Have No Runtime Polymorphism

A subclass is allowed to declare a field with the same name as an inherited field; Java **does not treat this as field overriding**. Each field still has its own location/state in the object or class structure.

Create the file **`FieldHidingDemo.java`**:

```java
class BaseUser {
    String role = "base";

    String baseRole() {
        return role;
    }
}

class AdminUser extends BaseUser {
    String role = "admin";

    String adminRole() {
        return role;
    }

    String inheritedRole() {
        return super.role;
    }
}

public class FieldHidingDemo {
    public static void main(String[] args) {
        AdminUser admin = new AdminUser();
        BaseUser base = admin;

        System.out.println(admin.role);
        System.out.println(base.role);
        System.out.println(admin.adminRole());
        System.out.println(admin.baseRole());
        System.out.println(admin.inheritedRole());
    }
}
```

Run command:

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

```text
admin
base
admin
base
base
```

Explanation:

- `AdminUser.role` and `BaseUser.role` **coexist**; they do not automatically synchronize with each other.
- `admin.role` uses the field declared in `AdminUser`; `base.role` uses the field of `BaseUser` based on the variable's static type `BaseUser`.
- `admin.adminRole()` reads `role` inside the method body of `AdminUser`, so it reads the subclass field.
- `admin.baseRole()` executes the method inherited from `BaseUser` and returns `BaseUser.role`. This is not field dynamic dispatch.
- `admin.inheritedRole()` uses `super.role` to **explicitly specify the superclass field**.

In practice, instance fields should be made `private` and accessed through methods with clear contracts. If `base.role` is replaced with `base.getRole()` and `getRole()` is overridden in the subclass, the behavior can **change to method dynamic dispatch**, but that is polymorphism of the **method**, not the field.

### Static Fields Can Also Be Hidden

`static` does not make a field polymorphic:

```java
class ParentFlags {
    static String mode = "parent";
}

class ChildFlags extends ParentFlags {
    static String mode = "child";
}
```

`ParentFlags.mode` and `ChildFlags.mode` are **two distinct static fields**. They can be accessed explicitly via the class name. If you use a reference variable `ParentFlags ref = new ChildFlags();` and write `ref.mode`, Java resolves the field based on the **static type `ParentFlags`**, without switching to `ChildFlags.mode` based on the runtime object.

## 8. Shadowing: A Local Variable or Parameter Shadows a Field Name

In an instance method/constructor, a parameter or local variable can have the same name as a field. In that case, the simple name `name` within the local variable's scope normally refers to the **local variable/parameter**, whereas `this.name` explicitly refers to the object's field.

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String getName() {
        return name;
    }
}
```

`this.name = name;` has two different sides:

- **Left-hand side `this.name`**: the field of the current instance.
- **Right-hand side `name`**: the parameter with the same name, shadowing the field within its scope.

If you write `name = name;`, the assignment only affects the parameter variable (essentially self-assignment) and **does not change the field**. This is **variable shadowing**, not overriding or overloading.

Another example:

```java
class Counter {
    private int count = 5;

    int compute() {
        int count = 10;          // Local variable shadows the field.
        return count + this.count;
    }
}
```

`new Counter().compute()` returns `15`: local `count == 10`, field `this.count == 5`. No method is overridden or hidden in this example.

### Are Shadowing and Hiding Interchangeable?

In Vietnamese, "che khuất" is sometimes used for both *hiding* and *shadowing*. To diagnose accurately:

- **Method hiding:** a static method in a subclass hides a superclass static method with a corresponding signature.
- **Field hiding:** a field in a subclass hides a superclass field with the same name.
- **Variable shadowing:** a local/parameter name shadows a field name or an outer name within its syntactic scope.

All three cases involve the phenomenon where a **name resolves differently**, but their rules and fixes are not the same. You should use the specific terminology when discussing code.

## 9. Can a Subclass Method Both Override and Participate in Overloading?

Yes. Whether something is **overriding or overloading is a relationship between specific pairs of declarations**, not a fixed label for every method of the same name in a class.

Create the file **`MixedMethodsDemo.java`**:

```java
class ParentParser {
    String parse(Object value) {
        return "Parent:Object";
    }

    String parse(int value) {
        return "Parent:int";
    }
}

class ChildParser extends ParentParser {
    @Override
    String parse(Object value) {
        return "Child:Object";
    }

    String parse(String value) {
        return "Child:String";
    }
}

public class MixedMethodsDemo {
    public static void main(String[] args) {
        ParentParser parent = new ChildParser();
        ChildParser child = new ChildParser();

        System.out.println(parent.parse("Java"));
        System.out.println(parent.parse(5));
        System.out.println(child.parse("Java"));
        System.out.println(child.parse((Object) "Java"));
        System.out.println(child.parse(5));
    }
}
```

Run:

```bash
javac MixedMethodsDemo.java
java MixedMethodsDemo
```

```text
Child:Object
Parent:int
Child:String
Child:Object
Parent:int
```

Analysis:

1. `ChildParser.parse(Object)` **overrides** `ParentParser.parse(Object)`.
2. `ChildParser.parse(String)` is another overload differing in parameter type, and **does not override** `parse(Object)`.
3. With `ParentParser parent`, `parent.parse("Java")` selects the `parse(Object)` signature at compile time because type `ParentParser` does not declare a `parse(String)` overload. At runtime, it calls the overriding implementation `ChildParser.parse(Object)`, so it prints `Child:Object`.
4. `parent.parse(5)` selects `parse(int)` because the literal `5` has type `int` and matches exactly. `ChildParser` does not override this signature, so it returns `Parent:int`.
5. With `ChildParser child`, `child.parse("Java")` selects the more specific `parse(String)` overload and returns `Child:String`.
6. `child.parse((Object) "Java")` selects `parse(Object)`; at runtime, it uses the overriding implementation in `ChildParser`.
7. `child.parse(5)` selects the inherited `parse(int)` version, returning `Parent:int`.

Therefore, a project can use both **compile-time overload resolution** and **runtime overriding dispatch** in the **same call**. Answer two questions in order: "Which signature is selected?" and then "Which implementation of that signature is executed?".

## 10. Constructors: Can Be Overloaded, Not Overridden

Constructors are not ordinary methods; Java allows **multiple constructors with different parameter lists** in the same class (constructor overloading). Constructors are **not inherited**, so they **do not override** or hide superclass constructors.

```java
class Job {
    private final String name;
    private final int priority;

    Job(String name) {
        this(name, 1);
    }

    Job(String name, int priority) {
        this.name = name;
        this.priority = priority;
    }

    String summary() {
        return name + ":" + priority;
    }
}
```

`new Job("daily")` and `new Job("daily", 3)` select **two constructor overloads**. Inside the one-parameter constructor, `this(name, 1)` calls the other constructor on the **same instance**, without creating a second object. `@Override` is not used on constructors.

If a subclass does not declare any constructor, the compiler may generate a default constructor depending on the superclass conditions. However, that is a **constructor of the subclass**, not an inherited superclass constructor.

## 11. Further Distinction: Same Name Without Overriding Due to `private` or `static`

### Private Methods in a Superclass

```java
class Base {
    private String detail() {
        return "base";
    }

    String summary() {
        return detail();
    }
}

class Derived extends Base {
    String detail() {
        return "derived";
    }
}
```

These are valid class declarations. `Derived.detail()` **does not override** `Base.detail()` because a `private` method of a superclass is not inherited to be overridden. `new Derived().summary()` returns `base`: the body of `Base.summary()` calls `Base.detail()` of class `Base` itself. Meanwhile, `new Derived().detail()` returns `derived`.

Do not infer overriding solely from two methods having the same name and parameters; you must consider the **access modifier** and the actual inheritance relationship.

### Static Methods Do Not Participate in Overriding

```java
// class A {
//     static void work() { }
// }
// class B extends A {
//     @Override
//     static void work() { } // Error because static methods do not override.
// }
```

Removing `@Override` makes `B.work()` valid **hiding** if the remaining constraints are met. You cannot drop the `static` keyword in the subclass to turn it into an instance override of a superclass static method: an instance/static combination with the same signature between a subclass and a superclass is a conflict disallowed by Java.

### Final Methods

```java
// class Parent {
//     final void save() { }
// }
// class Child extends Parent {
//     void save() { } // Error: overriding a final method.
// }
```

However, `void save(String path) { }` in the subclass can **overload** `Parent.save()` because the parameter list differs. `final` prevents **overriding** (or hiding when applied to the corresponding static method), rather than automatically blocking all overloads.

## 12. The Question "Which Method Runs?" Has Two Independent Steps

When encountering a call `receiver.method(args)`:

**Step 1 — Compile time:** the static types of `receiver` and `args` determine which method declarations are visible/applicable and which overload signature is selected. The compiler also checks accessibility, varargs, generic inference, and various other constraints.

**Step 2 — Runtime:** for an **overridable instance method**, the actual receiver object determines the implementation of the selected signature. For a **static method**, there is no dynamic dispatch based on the runtime object; for **field access**, the field is also resolved based on the static type.

Reasoning example:

```java
class Vehicle {
    String drive(Object mode) {
        return "Vehicle:Object";
    }
}

class Car extends Vehicle {
    @Override
    String drive(Object mode) {
        return "Car:Object";
    }

    String drive(String mode) {
        return "Car:String";
    }
}
```

If `Vehicle v = new Car();`:

- `v.drive("eco")`: the selected signature is `drive(Object)` based on the static type `Vehicle`; at runtime it runs `Car.drive(Object)` and returns `Car:Object`.
- `((Car) v).drive("eco")`: the static type after the cast is `Car`, so the compiler selects the `drive(String)` overload; the result is `Car:String`.
- `v.drive((Object) "eco")`: the argument is cast to `Object`, selecting `drive(Object)`; at runtime it still runs `Car.drive(Object)`.

These are **illustrative class declarations**, without `main`. They clarify one point: **casting a reference** can change the **set of overloads** the compiler considers, while the actual object does not change. The cast itself does not create a new object.

## 13. Hiding Differs from Being Able to Access the Original Member

A name being hidden **does not mean the superclass implementation or field is deleted**.

- For fields, `super.fieldName` or accessing through a reference of an appropriate superclass type can target the superclass field, if access permissions allow.
- For overridden instance methods, inside a subclass instance method, `super.method()` can invoke the superclass implementation according to `super` rules, even though a normal call `this.method()` dispatches to the overriding method.
- For static method hiding, explicitly calling `Superclass.staticMethod()` still uses the superclass method.
- For shadowing by a local variable, `this.fieldName` distinguishes the field from the local variable.

Example:

```java
class BaseCounter {
    int value = 2;

    String describe() {
        return "Base:" + value;
    }

    static String category() {
        return "Base";
    }
}

class DetailedCounter extends BaseCounter {
    int value = 5;

    @Override
    String describe() {
        return super.describe() + ", Child:" + this.value;
    }

    static String category() {
        return "Child";
    }
}
```

In an appropriate context:

- `new DetailedCounter().describe()` returns `Base:2, Child:5` because `super.describe()` runs the superclass method (in which `value` is `BaseCounter`'s field).
- `BaseCounter.category()` and `DetailedCounter.category()` are two static methods that resolve clearly by class name.
- Both `value` fields coexist and do not automatically update in sync merely because they share the same name.

Using `super` to reuse an implementation can be useful, but a design with many fields sharing the same name is often hard to read and prone to inconsistent state. Prefer encapsulation with `private` fields and clear APIs.

## 14. Access Privileges and Override/Hiding Constraints

For a subclass declaration to actually override/hide a superclass member, you must consider **valid inheritance** and **access rules**:

| Scenario | What to check |
| --- | --- |
| Superclass method `public` | The corresponding overriding/hiding declaration must not reduce visibility. |
| Superclass method `protected` | A valid overriding method may keep `protected` or widen to `public`. |
| Superclass method package-private | The package relationship determines inheritance/overriding capability; different packages require careful inspection. |
| Superclass method `private` | Not an inherited method to be overridden/hidden in the normal way. |
| Superclass method `final` | Cannot override a final instance method; cannot hide a final static method with a corresponding signature. |
| Superclass method `static` | Cannot have an instance override with the same signature; a static declaration in the subclass can hide it when valid. |
| Interface method | Default/abstract methods have implementation/override rules; static interface methods are not inherited like static class methods. |
| Checked exception | An overriding/hiding declaration under the relevant rules cannot arbitrarily broaden checked throws. |
| Return type | Must be return-type-substitutable when required by the override/hide relationship, and not arbitrarily changed to an incompatible type. |

These rules explain why merely looking at two lines of `void run()` in two files may not be enough to judge "override": you must inspect modifiers, packages, the superclass/interface, and the actual signature.

### Package-Private Overriding Across Package Boundaries

If the superclass is in a different package and declares a method without an access modifier, the subclass generally **does not inherit that method as an overridable method**. A method with the same name/signature declared in the subclass in this case can be a new method. For this reason, `@Override` is very valuable: the compiler reports an error if the intended override does not actually occur.

### Covariant Return Is Not Overloading by Return Type

`Food prepare()` in a superclass and `Bread prepare()` in a subclass (with `Bread extends Food`) can be a **valid override with a covariant return**. However, two declarations with the same name, same parameters, and different return types **within the same class** do not create an overload.

## 15. Common Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "Same name means override" | You must check the parameter list and inheritance relationship. Different parameters may be an overload. |
| "Java selects an overload based on the runtime object" | Overload resolution uses static types. Runtime dispatch only selects the implementation of an already chosen instance method. |
| "A static method in a subclass overrides a superclass static method" | That is **method hiding**, not dynamic overriding. |
| "A field with the same name is overridden" | Fields have **hiding**, not field dynamic dispatch. |
| "A different return type creates an overload" | Not sufficient; the parameter signature must differ validly. |
| "Different parameter names create an overload" | No; parameter names do not distinguish signatures. |
| "`@Override` can be placed on static method hiding" | No; the compiler will reject that annotation. |
| "`final` forbids all methods with the same name in a subclass" | It forbids overriding/hiding with a corresponding signature; overloads with different parameters can be valid. |
| "A superclass `private` method can be overridden normally" | No; private methods are not inherited for overriding. |
| "`super.method()` creates a new parent object" | No; it calls the superclass implementation on the same current instance. |
| "`List<String>` and `List<Integer>` always create an overload" | They can cause a name clash due to generic erasure. |
| "Using a superclass-typed variable makes all members follow the runtime subclass" | Instance overrides have runtime dispatch; static methods and fields do not. |
| "Casting `(Parent) child` turns a Child object into a Parent" | A cast only changes the static type of the reference expression; the runtime object remains Child. |
| "Constructors can be overridden" | Constructors can be overloaded, but **not inherited/overridden**. |
| "For a pair of methods with the same name, only one concept applies across the whole hierarchy" | Each pair of signatures/declarations must be examined separately: one name can have both overloads and distinct overrides. |

## 16. Self-Check Questions and Answers

**Question 1.** Class `A` has `void show(int x)`, and class `B extends A` declares `void show(String x)`. What is that?

**Answer:** **Overloading**: same name but different parameter type. `show(String)` does not override `show(int)`.

**Question 2.** Class `A` has instance method `String greet()`, and class `B extends A` has `@Override String greet()`. With `A value = new B();`, which method does `value.greet()` execute?

**Answer:** The `B.greet()` implementation, because the method is an overridable instance method and the runtime receiver is `B`.

**Question 3.** If both `A` and `B extends A` declare `static String id()`, which method does `A a = new B(); a.id()` select?

**Answer:** `A.id()`, because a static method is resolved based on the expression's static type `A`, without using runtime polymorphism.

**Question 4.** If `A` has field `String label = "A"`, `B` has field `String label = "B"`, and `A a = new B();`, what is `a.label`?

**Answer:** `"A"`, according to the static type `A`; this is field hiding, not method overriding.

**Question 5.** Within one class, can `int read(String s)` and `long read(String s)` be declared as two overloads?

**Answer:** No, because the return type is not sufficient to distinguish signatures.

**Question 6.** Can a superclass's `final void execute()` be overridden? Can the subclass declare `execute(int retries)`?

**Answer:** `execute()` cannot be overridden; `execute(int)` has a different parameter list, so it can be a valid overload.

**Question 7.** What is the effect of `@Override` on a method with the same name as, but different parameters from, every superclass method?

**Answer:** If it does not actually override/implement any method from an appropriate supertype, the compiler reports an error. This helps catch cases where an overload was accidentally written when overriding was intended.

**Question 8.** In `MixedMethodsDemo`, why does `parent.parse("Java")` print `Child:Object`?

**Answer:** The compiler selects the `parse(Object)` signature from the static type `ParentParser`. However, the runtime receiver is `ChildParser`, so the overriding implementation `ChildParser.parse(Object)` runs.

**Question 9.** Is `this.name = name;` inside a constructor method hiding?

**Answer:** No. This is a case where the parameter `name` shadows the field of the same name; `this.name` explicitly specifies the field.

**Question 10.** Why is `ToolImpl.version()` not automatically valid even though `ToolImpl implements Tools` and `Tools` has a static method `version()`?

**Answer:** Static methods in an interface are not inherited by implementing classes in that way; call `Tools.version()`.

**Question 11.** Is `super.describe()` in an overriding method called on a separate superclass object?

**Answer:** No. It invokes the superclass implementation on the **same current object**, using `super` syntax.

**Question 12.** Given `Parent p = new Child();`, does casting `((Child) p)` change the class of the object?

**Answer:** No. It changes the static type of the expression if the cast is valid; the runtime object remains `Child`. This can change the set of overloads visible to the compiler.

## 17. Diagnostic Process in Real Code

When you want to determine whether two declarations with the same name are overloading, overriding, or hiding, proceed step by step:

1. **Read both declarations in full:** name, ordered list of parameter types, generic type parameters/erasure, `static`, `private`, and `final` modifiers, access level, and return type.
2. **Determine the class/type relationship:** are the two methods in the same class, a subclass/superclass, or an interface? Is the superclass declaration validly inherited?
3. **Different parameter lists?** If so and the declarations do not clash in erasure/signature, it may be an **overload**.
4. **Same signature and both are instance methods?** If the inheritance relationship and override conditions are valid, it is **overriding**.
5. **Same signature and both are static methods?** Within a valid class hierarchy relationship, it is **static method hiding**.
6. **Duplicate name, but it is a field?** Check for **field hiding**; fields are selected by static type, without runtime dispatch.
7. **Duplicate name between a local/parameter and a field?** Check for **shadowing**; use `this.field` to explicitly reference the field.
8. **At a specific call site:** note the static type of the receiver and the static type of each argument; resolve overloading first, then consider runtime overriding (if applicable).
9. **Use `@Override` on implementations that genuinely override**, and when you need to observe actual behavior, run a small program with deterministic output rather than guessing from variable names.

---

**Key points to remember:** **Overloading** differs in *parameter signature* and is resolved at compile time; **overriding** replaces the implementation of an *instance method* on the runtime object; **hiding** for a static method or field causes the subclass name to hide the corresponding superclass name, yet **does not create runtime polymorphism**. Local-variable **shadowing**, in turn, is a name-scoping issue. By determining the **member kind, signature, static type, and inheritance relationship** in the right order, you can explain which method executes and which field is read in Java programs that appear contradictory.
