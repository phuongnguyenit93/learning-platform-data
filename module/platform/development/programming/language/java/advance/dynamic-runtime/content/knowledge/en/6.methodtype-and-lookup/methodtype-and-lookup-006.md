# 6.6 findVirtual, findStatic, findSpecial and findConstructor

`MethodHandles.Lookup` provides four methods to create a `MethodHandle` for four different invocation needs: calling an instance method with polymorphic dispatch (`findVirtual`), calling a static method (`findStatic`), calling an instance method with special semantics similar to `super`/`invokespecial` (`findSpecial`), and creating an object via a constructor (`findConstructor`). All four take type information through `MethodType` and check access permissions from a `Lookup`.

Common point of confusion: the `MethodType` passed to the factory describes the **declared signature of the method**, without a receiver; the handle created by `findVirtual`/`findSpecial` will have an added receiver. A constructor is the opposite: the descriptor requires `void`, but the created handle **returns an object**. This lesson explains in detail how to choose the API, how access works, how to invoke with the right type, and a Java 17+ runnable example.

## 1. Decision table

| Factory | Member kind | Receiver parameter of handle | `MethodType` during lookup | Created handle (typical) |
| --- | --- | --- | --- | --- |
| `findVirtual(refc, name, type)` | Instance method | Yes, at the beginning | `(args...)Return` | `(refc,args...)Return` |
| `findStatic(refc, name, type)` | Static method | No | `(args...)Return` | `(args...)Return` |
| `findSpecial(refc, name, type, specialCaller)` | Instance method per `invokespecial` | Yes, restricted by `specialCaller` | `(args...)Return` | `(specialCaller,args...)Return` (may be narrower) |
| `findConstructor(refc, type)` | Constructor | No | `(args...)void` | `(args...)refc` |

`refc` is the class/interface used to resolve the method or the class containing the constructor. `name` is the method name. `type` is the `MethodType` consisting of the return type and the list of declared parameter types. `specialCaller` only exists for `findSpecial` and determines the special call context allowed by the JVM.

~~~text
Lookup + Class + MethodType + (name, specialCaller depending on API)
                    |
         +----------+-----------+---------------------+
         |          |           |                     |
   findVirtual  findStatic  findSpecial        findConstructor
         |          |           |                     |
  receiver+args    args   receiver+args             args
         |          |           |                     |
 virtual dispatch  static  invokespecial rules   create object
~~~

This is a **semantic** comparison, not a guarantee that the compiler will directly emit `invokevirtual`, `invokestatic`, or `invokespecial` instructions right at the `handle.invokeExact` source call.

## 2. Input `MethodType` differs from `MethodHandle.type()`

Suppose class `Counter` declares:

~~~java
public int increment(int value) { return value + 1; }
public static int doubleIt(int value) { return value * 2; }
public Counter(String label) { /* constructor */ }
~~~

These three lines only illustrate members **inside class Counter**, not a standalone runnable file.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle virtual = lookup.findVirtual(
        Counter.class, "increment", MethodType.methodType(int.class, int.class));
// Lookup MethodType: (int)int
// virtual.type()   : (Counter,int)int

MethodHandle statik = lookup.findStatic(
        Counter.class, "doubleIt", MethodType.methodType(int.class, int.class));
// Lookup MethodType: (int)int
// statik.type()    : (int)int

MethodHandle create = lookup.findConstructor(
        Counter.class, MethodType.methodType(void.class, String.class));
// Lookup MethodType: (String)void
// create.type()    : (String)Counter
~~~

The snippet above requires `java.lang.invoke.*` and a context that handles checked exceptions. With `findVirtual`, the instance receiving the call is parameter 0 of the **handle**, not included in the `MethodType` used to look up the member. With `findStatic`, the method has no receiver so the handle keeps the same signature. With `findConstructor`, `void.class` describes the JVM descriptor of the constructor; the handle used to allocate the object returns the reference type `Counter`.

`MethodType.methodType(String.class, int.class, long.class)` means a function returning `String` and taking `int, long`. It **does not describe the class type containing the method**, nor does it describe generic parameters such as `List<String>`: descriptors running on the JVM use erased runtime types.

## 3. Lookup and access checking

`MethodHandles.lookup()` returns a `MethodHandles.Lookup` bound to **the class actually calling** the `lookup()` factory, not bound to a class name string entered by the user. At the time of `findVirtual`/`findStatic`/`findSpecial`/`findConstructor`, the JVM/JDK checks the class, member, signature, and access modes of the lookup.

- `MethodHandles.lookup()`: uses permissions according to the current caller context. Can find public or appropriately accessible members, including private/nestmate in valid situations.
- `MethodHandles.publicLookup()`: suitable when only public APIs accessible under module rules are needed; does not carry private privileges.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)`: attempts to create a lookup with private privileges in `Target` if all access/module conditions are satisfied. Not a command to bypass JPMS.
- `lookup.in(Other.class)` can change the lookup class but reduces access modes. One must not assume that a converted lookup still retains enough privileges to call `findSpecial`.
- A successfully created handle becomes a capability to invoke the member. Because access is typically checked when **creating the handle**, care should be taken when passing a handle that accesses private members to untrusted code.

Lookup typically throws `NoSuchMethodException` if the member is not found by name/signature, and `IllegalAccessException` if access is denied or the wrong kind is chosen (for example, looking up an instance method with `findStatic`). Distinguish errors at lookup time from `WrongMethodTypeException` when calling `invokeExact`.

## 4. `findVirtual`: calling an instance method with virtual dispatch

Signature:

~~~java
MethodHandle findVirtual(Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

With `public String greet(String name)` in class `Parent`:

~~~java
MethodHandle greet = lookup.findVirtual(
        Parent.class, "greet",
        MethodType.methodType(String.class, String.class));
// greet.type() is typically (Parent,String)String

Parent receiver = new Child();
String result = (String) greet.invokeExact(receiver, "An");
~~~

This is an **illustrative snippet** with `Child extends Parent` and overriding `greet`, so the call can execute `Child.greet("An")`. `findVirtual` creates a handle with a leading receiver argument, and for a non-private virtual method, the implementation is chosen according to the runtime class of the receiver.

Explanation:

1. The `Parent.class` parameter is the type that lookup uses to resolve; `new Child()` is still valid because this object is an instance of `Parent`.
2. `MethodType.methodType(String.class, String.class)` only describes `greet(String):String`, **not containing the Parent receiver**.
3. `invokeExact` checks the compile-time receiver type `Parent` and the expected return type `String`. Using a `Child child` variable directly may generate a non-matching `Child` receiver descriptor, unless cast to `Parent`.
4. For non-private instance methods, overrides on the receiver are respected; for a validly looked-up private method, there is no virtual override dispatch because private methods do not override.
5. For `protected` in a different package, the handle's receiver may be narrowed beyond `refc` according to access rules, so check the actual `handle.type()` when handling complex cases.
6. Can be used with interface instance methods; the handle has dispatch semantics corresponding to `invokeinterface` when appropriate.

**Do not use `findVirtual` for static methods.** When a specific instance is needed as a callback, `greet.bindTo(receiver)` fixes the receiver and returns a new handle without the first receiver parameter; dynamic dispatch still depends on the runtime type of that object.

## 5. `findStatic`: calling a static method without a receiver

Signature:

~~~java
MethodHandle findStatic(Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

Example with the JDK:

~~~java
MethodHandle parse = lookup.findStatic(
        Integer.class, "parseInt",
        MethodType.methodType(int.class, String.class));
int value = (int) parse.invokeExact("123");
~~~

`parse.type()` is `(String)int`. No `Integer` or any receiver is passed. The illustrative lines assume a `lookup` variable with valid access privileges and an enclosing method with `throws Throwable`.

Key characteristics:

- Static methods have no dispatch by runtime receiver; there is no receiver to select an override.
- A subclass can *hide* a static method with the same name/signature, but a handle already resolved to a specific static target does not re-select an implementation.
- When **invoking** the handle, the class declaring the static method may be initialized if it was not initialized previously. Do not infer that merely creating the handle triggers all static initializer logic.
- Lookup requires an actual static method. `findStatic(Foo.class,"run", methodType(...))` will fail if `run` is an instance method.
- Do not add `Foo.class` to `MethodType` as a dummy parameter; that is a signature error.

If the target returns `void`, `MethodType` and `MethodHandle.type()` both have return type `void.class`. With `invokeExact`, the call site's result type must also be `void`, for example an expression statement discarding the result.

## 6. `findSpecial`: calling with `invokespecial` semantics

Signature:

~~~java
MethodHandle findSpecial(Class<?> refc, String name,
                         MethodType type, Class<?> specialCaller)
        throws NoSuchMethodException, IllegalAccessException
~~~

`findSpecial` creates a handle for an `invokespecial`-style call. Unlike `findVirtual`, it **does not run normal override dispatch** according to the runtime class of the receiver. Common cases are `super.method(...)` calls inside a subclass, or interface default methods with the `InterfaceName.super.method(...)` calling mechanism when JVM/Java conditions are met.

Parameters:

| Variable | Role |
| --- | --- |
| `refc` | Class/interface used as the reference point when resolving the method |
| `name` | Instance method name; does not accept `"<init>"` to create a constructor |
| `type` | Declared signature of the instance method (without receiver) |
| `specialCaller` | Class whose context corresponds to containing the `invokespecial` instruction, governing permissions and body selection |

**Key access constraint:** According to the Java SE 21 Javadoc, `specialCaller` must **match the exact lookup class** of the `Lookup` used at the time of `findSpecial`, and the lookup must have **private access privileges**. Otherwise, `IllegalAccessException` may occur even before the method is resolved. Therefore, one cannot take `publicLookup()` and set `specialCaller` to any arbitrary class to call its parent method.

Illustrative class example:

~~~java
class Parent {
    public String greet() { return "Parent"; }
}

class Child extends Parent {
    @Override public String greet() { return "Child"; }

    static MethodHandle parentHandle() throws ReflectiveOperationException {
        // Child itself calls lookup(): lookup class = Child
        MethodHandles.Lookup own = MethodHandles.lookup();
        return own.findSpecial(
                Parent.class, "greet",
                MethodType.methodType(String.class),
                Child.class);
    }
}
~~~

This snippet requires `import java.lang.invoke.*;` and placing the classes in an appropriate Java context. The handle typically has type `(Child)String`; invoking with a `Child` receiver executes the `Parent.greet()` body like a `super.greet()` call, regardless of `Child` overriding the method.

Advanced note: `invokespecial` rules also specify how a method is selected when `refc` is a **distant ancestor** of `specialCaller`. If `C extends B extends A`, `findSpecial(A.class, "m", ..., C.class)` may execute the implementation in `B` according to selection rules related to the direct superclass. Therefore, do not describe `findSpecial` as "calling the exact body of any arbitrary class".

Constructors in the JVM are also related to the `invokespecial` opcode, but `findSpecial` **is not used for `"<init>"`**. Object creation has a dedicated API, `findConstructor`.

## 7. `findConstructor`: `void` descriptor, yet handle returns an object

Signature:

~~~java
MethodHandle findConstructor(Class<?> refc, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

If `Ticket` has constructor `public Ticket(long id)`:

~~~java
MethodHandle ctor = lookup.findConstructor(
        Ticket.class, MethodType.methodType(void.class, long.class));
Ticket ticket = (Ticket) ctor.invokeExact(42L);
~~~

This is an illustrative snippet requiring `Ticket`/`lookup` and a method with `throws Throwable`. The lookup takes `(long)void`, while `ctor.type()` is `(long)Ticket`. Why? A JVM constructor is an instance initialization method with a `void`-returning descriptor; this API's handle both allocates the object and runs the constructor, so the handle **returns the created object**.

Remember these points:

- `findConstructor` does not take a string name and does not take a receiver; invoke the handle with the constructor parameters in the exact order.
- `refc` is the class containing the constructor; constructors are not inherited like instance methods. `Child.class` does not automatically inherit constructors from its superclass.
- Do not use `MethodType.methodType(Ticket.class, long.class)` to look up a constructor, even though the handle after lookup has return type `Ticket`.
- You must choose the exact constructor overload by parameter types. `findConstructor(Ticket.class, methodType(void.class,int.class))` does not automatically find the `Ticket(long)` constructor via widening during the lookup phase.
- A `private` constructor requires a `Lookup` with sufficient privileges; `publicLookup` cannot automatically access every private constructor.
- **Invoking** the object-creation handle may trigger class initialization. Exceptions thrown by the constructor typically propagate directly through the method handle, without being automatically wrapped in `InvocationTargetException`.

## 8. Complete Java 17+ example: verifying the four factories

Create the file `LookupMethodsDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupMethodsDemo {
    public static class Parent {
        public String greet(String name) {
            return "Parent: " + name;
        }
    }

    public static class Child extends Parent {
        @Override
        public String greet(String name) {
            return "Child: " + name;
        }

        public static MethodHandle parentGreetHandle()
                throws ReflectiveOperationException {
            // This method is in Child: the lookup class is Child.
            MethodHandles.Lookup ownLookup = MethodHandles.lookup();
            return ownLookup.findSpecial(
                    Parent.class,
                    "greet",
                    MethodType.methodType(String.class, String.class),
                    Child.class);
        }
    }

    public static class Message {
        private final String content;

        public Message(String content) {
            this.content = content;
        }

        public String show() {
            return "Message(" + content + ")";
        }

        public static Message normalized(String input) {
            return new Message(input.trim().toUpperCase());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType greetType =
                MethodType.methodType(String.class, String.class);

        // Virtual: look up method from Parent, actual receiver is Child.
        MethodHandle virtual = lookup.findVirtual(
                Parent.class, "greet", greetType);
        Parent asParent = new Child();
        String virtualResult = (String) virtual.invokeExact(asParent, "An");
        System.out.println("virtual = " + virtualResult);
        System.out.println("virtual type ok = " + virtual.type().equals(
                MethodType.methodType(String.class, Parent.class, String.class)));

        // Static: no receiver.
        MethodHandle statik = lookup.findStatic(
                Message.class,
                "normalized",
                MethodType.methodType(Message.class, String.class));
        Message normalized = (Message) statik.invokeExact("  hello  ");
        System.out.println("static = " + normalized.show());
        System.out.println("static type ok = " + statik.type().equals(
                MethodType.methodType(Message.class, String.class)));

        // Special: create lookup inside Child to execute Parent.greet body.
        MethodHandle special = Child.parentGreetHandle();
        Child child = new Child();
        String specialResult = (String) special.invokeExact(child, "An");
        System.out.println("special = " + specialResult);
        System.out.println("special type ok = " + special.type().equals(
                MethodType.methodType(String.class, Child.class, String.class)));

        // Constructor: lookup requires (String)void, handle returns (String)Message.
        MethodHandle constructor = lookup.findConstructor(
                Message.class, MethodType.methodType(void.class, String.class));
        Message created = (Message) constructor.invokeExact("raw");
        System.out.println("constructor = " + created.show());
        System.out.println("constructor type ok = " + constructor.type().equals(
                MethodType.methodType(Message.class, String.class)));

        // bindTo binds the receiver of the virtual handle and drops the first receiver parameter.
        MethodHandle bound = virtual.bindTo(asParent);
        String boundResult = (String) bound.invokeExact("Bình");
        System.out.println("bound = " + boundResult);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 LookupMethodsDemo.java
java LookupMethodsDemo
~~~

Expected `stdout`:

~~~text
virtual = Child: An
virtual type ok = true
static = Message(HELLO)
static type ok = true
special = Parent: An
special type ok = true
constructor = Message(raw)
constructor type ok = true
bound = Child: Bình
~~~

Analysis:

1. `virtual.type()` is `(Parent,String)String`. The runtime instance is `Child`, so the result is `Child: An`.
2. `statik.type()` is `(String)Message`; the target `Message.normalized` takes no receiver. `trim()` removes whitespace and `toUpperCase()` converts `hello` to `HELLO`.
3. `Child.parentGreetHandle()` calls `lookup()` right inside `Child`; `findSpecial` receives `specialCaller=Child.class` and returns a handle `(Child,String)String`. The executed body is `Parent.greet`, resulting in `Parent: An`.
4. `findConstructor` receives a `void`-returning `MethodType` and creates a `Message`-returning handle; `new Message("raw")` is executed through the handle.
5. `bound` drops the receiver from the virtual handle, but the bound receiver is still the `Child` object, so the result is `Child: Bình`.

The program does not need `--add-opens` module flags because the members in the example are properly accessible from the `Lookup` context used. `main` declares `throws Throwable` because the signature of `MethodHandle.invokeExact` allows the target to throw `Throwable`.

## 9. `invokeExact`, `invoke`, and type adaptation

A handle has a **fixed** signature; `invokeExact` requires the **descriptor at the call site**, including parameter types and **return type**, to match `handle.type()` exactly. With `virtual.type() = (Parent,String)String`:

~~~java
Parent parent = new Child();
String ok = (String) virtual.invokeExact(parent, "A"); // Correct

Child child = new Child();
// String wrong = (String) virtual.invokeExact(child, "B");
// Wrong because the compiler builds the descriptor (Child,String)String.
~~~

This is an illustrative snippet inside a method with classes/variables already declared. A `Child` receiver *is* still a `Parent` in Java, but `invokeExact` looks at the **compile-time type at the call site**. Cast `(Parent) child` or assign to a `Parent`-typed variable to match. Similarly, if the handle returns `Message` while the call site expects `Object`, `invokeExact` may throw `WrongMethodTypeException`.

- `invoke(...)` allows certain compatible conversions according to `asType`; it does not mean automatically converting every value.
- `asType(newType)` creates an adapter handle according to supported type conversion rules. It does not change the underlying member or inherent access permissions.
- `bindTo(receiver)` binds the first reference-typed argument, reducing the handle's parameter count by one.
- `handle.type()` and `MethodType.methodType(...)` help verify exactness before invoking.
- When using `invokeExact` in an expression statement with a `void`-returning method, the call site must expect `void`; when receiving a primitive `int`, there must be an `int` result context.

Example with constructor handle `(String)Message`:

~~~java
Message a = (Message) constructor.invokeExact("A");
// Object b = constructor.invokeExact("B"); // Wrong expected type.
Object c = constructor.invoke("C");          // invoke can adapt return Message -> Object.
~~~

`Object c` is an illustrative call to distinguish `invoke` from `invokeExact`; both require code with `throws Throwable`.

## 10. Comparing virtual dispatch, static hiding, and special invocation

Given the relationship:

~~~java
class A {
    String name() { return "A"; }
    static String kind() { return "A"; }
}
class B extends A {
    @Override String name() { return "B"; }
    static String kind() { return "B"; }
}
class C extends B {
    @Override String name() { return "C"; }
}
~~~

These are illustrative classes, not a standalone file. Distinguish:

- The handle `findVirtual(A.class, "name", methodType(String.class))` with an actual receiver of `C` can run `C.name()` via virtual dispatch.
- The handle `findStatic(A.class, "kind", methodType(String.class))` runs the exact static target resolved from `A`; it does not query the runtime object and does not dispatch to `B.kind()`.
- `findSpecial(A.class, "name", methodType(String.class), C.class)` (if created with a valid lookup inside `C`) has `invokespecial` semantics, **not guaranteed to call the A.name() body**. The JVM also applies direct superclass selection; in the corresponding hierarchy, it may choose `B.name()`. This differs from the assumption that "findSpecial forces selecting any passed ancestor".
- Constructors do not participate in virtual dispatch or static hiding; they select an overload of a specific class.

If there is an interface default method, `findSpecial` in a valid implementing class can emulate `InterfaceName.super.method()` semantics when caller/access conditions are met; use `findVirtual` when you need normal dispatch behavior.

## 11. Overloads, varargs, generics, and constructors

**Overloads:** lookup selects by the declared `MethodType`, without running Java overload resolution from runtime call argument values. `findVirtual(Foo.class,"set",methodType(void.class,int.class))` differs from `methodType(void.class,Integer.class)`. The same applies to constructors: `findConstructor(Foo.class,methodType(void.class,int.class))` does not automatically find a constructor that only accepts `long`.

**Generics:** `MethodType` uses runtime `Class<?>` after type erasure. A method declared `List<String> values()` has return type descriptor `List.class`, not `List<String>.class`. Generic metadata is a separate matter, which can be read via reflection if needed.

**Varargs:** A method/constructor declared with `String... pieces` actually has final parameter type `String[].class` in the lookup step. The handle may have the variable-arity collector property, allowing certain `invoke` calls to gather arguments into an array; `asFixedArity()` is used when you want a fixed arity. Do not look up with `String.class` just because the source declares `String...`.

**Constructors:** When instantiating an object with `new` via a handle, the constructor returns `void` per the JVM descriptor, while the new object is the return value of the handle. Do not write `methodType(Foo.class, ...)` in `findConstructor`.

## 12. Common errors and how to fix them

| When? | Error / symptom | Typical cause | How to handle |
| --- | --- | --- | --- |
| At lookup | `NoSuchMethodException` | Wrong name/method type, overload does not exist | Check exact name, return, and parameter types |
| At lookup | `IllegalAccessException` | Member not accessible, wrong kind, `findSpecial` missing private access/wrong `specialCaller` | Verify `lookup.lookupClass()`, access modes, JPMS, method kind |
| At lookup | `NullPointerException` | Passing `null` for required refc/name/type/specialCaller | Validate input |
| At invoke | `WrongMethodTypeException` | Call-site descriptor of `invokeExact` differs from `handle.type()` | Check receiver compile-time type, args, return type |
| At invoke | `ClassCastException` or conversion error | `invoke`/`asType` cannot convert types | Choose compatible adapter/type |
| At invoke | `NullPointerException` | Receiver instance is `null` or target throws it | Check receiver and stack trace |
| At invoke | Exception/error from target method | Bug in business logic/constructor | Catch actual exception type, distinguish from lookup failure |
| At invoke | `ExceptionInInitializerError` | Static method/constructor triggers failing initializer | Check class initialization error and cause |

### Three subtle mistakes

1. **Manually adding the receiver to the `MethodType` for `findVirtual`**: causes lookup to search for a non-existent signature. The receiver only appears in the returned handle.
2. **Passing a `specialCaller` different from the lookup class**: fails access even if the method is public. With `findSpecial`, private access and the caller relation are part of the contract.
3. **Using the class as return type in `findConstructor`**: for example `methodType(Foo.class,String.class)` is wrong; you must look up `methodType(void.class,String.class)` and receive a handle with result `Foo`.

With `MethodHandle`, exceptions thrown by the target typically propagate directly rather than being wrapped by default like `InvocationTargetException` in `java.lang.reflect.Method.invoke`. Do not catch `InvocationTargetException` out of habit when not using reflection `Method.invoke`.

## 13. Practical workflow

1. Identify the goal: polymorphic instance, static, super/default-special, or constructor. The four factories are not interchangeable.
2. Create a `Lookup` from code with appropriate privileges. If `findSpecial` is needed, place the `Lookup` creation point in the right caller class or use an authorized approach per API rules; do not assume private access across modules.
3. Determine the `MethodType` matching the declared descriptor; constructors have return type `void` and instance methods do not include the receiver.
4. Look up the handle and distinguish `NoSuchMethodException` / `IllegalAccessException` at the resolve step from runtime errors of the target.
5. Check `handle.type()` when wiring a dynamic dispatcher; use `invokeExact` only when the call-site type matches completely. Use `invoke`, `asType`, or `bindTo` when there is a clear reason.
6. If calling the same method repeatedly, you can cache the handle to avoid repeated lookups, while considering class loader lifecycle and access.
7. For performance, benchmark the actual workload with JMH if needed; `MethodHandle` can be optimized by the JVM, but is not guaranteed to always be faster than reflection or direct calls.

## 14. Self-check

**Question 1.** What type does the handle returned by `findVirtual(Foo.class,"run",methodType(void.class,int.class))` typically have?

**Answer:** `(Foo,int)void`; the receiver is prepended after lookup.

**Question 2.** Does `findStatic` need a receiver at invocation time?

**Answer:** No. The target is a resolved static method; the handle takes the exact declared parameters.

**Question 3.** Why does `findVirtual(Parent.class,"greet",...)` with a runtime `Child` instance execute `Child`'s override?

**Answer:** Virtual dispatch selects the implementation by the receiver's runtime class for overridable methods.

**Question 4.** Can `findSpecial` set `specialCaller` arbitrarily?

**Answer:** No. `specialCaller` must match the lookup class and the lookup needs private access; the JVM also checks valid relations/targets.

**Question 5.** Why does `findConstructor(Foo.class, methodType(void.class,String.class))` create a handle returning `Foo`?

**Answer:** The JVM constructor is described as `(String)void`, but the handle performs allocation and initialization and then returns the new `Foo` object.

**Question 6.** Can `findSpecial(Foo.class,"<init>",...)` be used to call a constructor?

**Answer:** No; use `findConstructor`.

**Question 7.** Is `invokeExact` guaranteed to run when receiving a `Child child` variable for a handle with receiver type `Parent`?

**Answer:** No. The call site's descriptor carries the compile-time type `Child`, so it must be cast/assigned to `Parent` or use a valid adapter.

**Question 8.** How does `NoSuchMethodException` differ from `WrongMethodTypeException`?

**Answer:** The first typically occurs when looking up a member without a matching signature; the latter occurs when invoking a handle with a mismatched signature.

**Question 9.** Does invoking a method via a handle automatically wrap business exceptions in `InvocationTargetException`?

**Answer:** Not by default; the target exception is propagated directly according to `MethodHandle` semantics.

## Authoritative references

- [Java SE 21 — MethodHandles.Lookup and the four factories](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 21 — MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 21 — MethodHandle: invokeExact, invoke, asType, bindTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup))
- [Java Virtual Machine Specification SE 21 — Method Invocation Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html)
