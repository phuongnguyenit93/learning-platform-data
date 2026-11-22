# Avoiding `new T()` and Passing `Supplier<T>` in Java Generics

## 1. Why does this problem arise?

You are writing a generic class to manage or instantiate multiple different data types:

```java
class Box<T> {
    T create() {
        // Wants to create a new object of exact type T.
        return new T(); // Does not compile.
    }
}
```

The intent seems reasonable: a caller using `Box<Customer>` expects `create()` to create a `Customer`, while `Box<Order>` creates an `Order`. However, Java **does not allow `new T()`** when `T` is a type variable. The diagnostic from `javac` typically looks like:

```text
error: unexpected type
  required: class
  found:    type parameter T
```

Even when attaching a bound to the type variable, such as `<T extends Number>`, the compiler still cannot allocate directly via `new T()`. Java has no bound syntax meaning "`T` must have a public no-argument constructor" as some other languages do.

The cleanest and most testable solution is usually to **let the caller provide the object-creation strategy** via `Supplier<T>`:

```java
import java.util.function.Supplier;

class Box<T> {
    private final Supplier<T> factory;

    Box(Supplier<T> factory) {
        this.factory = factory;
    }

    T create() {
        return factory.get();
    }
}
```

The caller decides how instances are created:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);
StringBuilder builder = box.create();
```

Here `StringBuilder::new` is a **constructor reference**, converted into an implementation of `Supplier<StringBuilder>`. When `create()` calls `factory.get()`, the object-creation logic runs in the place where the concrete class is already known.

This lesson explains the cause from type erasure, how to use `Supplier<T>` and `Supplier<? extends T>`, constructor references, lambdas with parameters, factory design, null/freshness checks, checked exceptions, and common mistakes. The main examples use Java 17 and have been compiled and tested.

## 2. `T` is a type variable, not the name of a concrete class

A generic class:

```java
class Repository<T> {
    T value;
}
```

defines **a type variable `T`** so the compiler can check assignments and type relationships at the source level. For example:

```java
Repository<String> strings = new Repository<>();
Repository<Integer> numbers = new Repository<>();
```

`String` and `Integer` are different type arguments when using `Repository<T>`. Yet they do not cause the JVM to generate separate `Repository<String>` and `Repository<Integer>` classes for each argument.

Most generic type argument information is removed from method/field descriptors in bytecode by **type erasure**. For a type variable without an explicit bound, its erasure usually becomes `Object`.

That creates a limitation: inside a generic class, the compiler has no `new` expression that can automatically determine which runtime class will be instantiated when the caller chooses `T`.

### 2.1. Distinguishing between using `T` and instantiating `T`

You **can** write:

```java
class Holder<T> {
    private T value;

    void put(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Because the code only stores and returns objects that were already created externally, the compiler checks type `T` through the generic contract.

You **cannot** write:

```java
class Holder<T> {
    T make() {
        return new T(); // Compilation error.
    }
}
```

`new` requires an instantiable class type and its corresponding constructor in source. `T` is only a type variable: it does not identify a concrete constructor that this method is allowed to invoke.

**Remember:** `T` is useful for linking *the type of values* across parameters, fields, and return values. It is **not a "dynamic constructor"**.

### 2.2. A bound does not make `new T()` valid

Consider:

```java
class Factory<T extends Number> {
    T make() {
        return new T(); // Still invalid.
    }
}
```

`T extends Number` only requires the type argument to be `Number` or an appropriate subtype. The caller could choose `Integer`, `Double`, a custom `Number`, and so on. Those classes do not share a public no-argument constructor.

Even when the bound is a class that has a public no-argument constructor:

```java
class Base {
    public Base() {
    }
}

class Generic<T extends Base> {
    // T make() { return new T(); } // Still invalid.
}
```

The compiler cannot infer that **every subtype `T`** will have a matching constructor. Constructors are not polymorphic members inherited like instance methods; a subclass may only have parameterized constructors or different access modifiers.

### 2.3. Why can't we use `T.class`?

```java
class Holder<T> {
    // Class<T> type() { return T.class; } // Invalid.
}
```

`T.class` is not a valid class literal because `T` is a type variable, not the name of a concrete class present at runtime. When a class token is genuinely needed, the caller must supply `Class<T>` as a separate value.

```java
static <T> String className(Class<T> type) {
    return type.getName();
}

// className(String.class) -> "java.lang.String"
```

`Class<T>` is a different tool from `Supplier<T>`: a class token describes a runtime class, whereas a Supplier describes **the action of providing a value**. Supplier is usually better suited when the goal is object creation, especially with parameterized constructors, dependency injection, or custom factories.

## 3. What is `Supplier<T>`?

`java.util.function.Supplier<T>` is a standard Java functional interface:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

It has a single abstract method that **takes no parameters** and returns a value of type `T`.

You can think of Supplier as a promise:

> "When `get()` is called, I will provide a value compatible with `T`."

It **does not promise**:

- Returning a new object on every call.
- That the result is always non-null.
- That computation is always fast or side-effect-free.
- Safe concurrent invocation across multiple threads.
- That `get()` will never throw an unchecked exception.

Those properties must be specified further in the application's contract or guaranteed by the concrete implementation.

### 3.1. How Supplier differs from `Consumer`, `Function`, and `Callable`

| Interface | Abstract method | Common use case |
| --- | --- | --- |
| `Supplier<T>` | `T get()` | Supplying/creating a value with no input at call time. |
| `Function<A,R>` | `R apply(A input)` | Creating/transforming a result with one input. |
| `BiFunction<A,B,R>` | `R apply(A a, B b)` | Creating/transforming with two inputs. |
| `Consumer<T>` | `void accept(T value)` | Consuming or processing a value; returns no result. |
| `Callable<T>` | `T call() throws Exception` | A value-returning task with a signature allowing checked exceptions. |

`Supplier<T>` fits best when an object can be created **without needing arguments passed to `get()`**. That does not mean the real constructor must take no parameters: a lambda can **capture** configuration values provided beforehand.

## 4. Basic solution: passing a Supplier into a generic class

Design:

```java
import java.util.Objects;
import java.util.function.Supplier;

final class Box<T> {
    private final Supplier<? extends T> factory;

    Box(Supplier<? extends T> factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    T newValue() {
        return Objects.requireNonNull(
                factory.get(), "factory returned null");
    }
}
```

Benefits:

1. Class `Box<T>` **does not need to know** which class `T` is.
2. The caller supplies the object-creation mechanism, which can be swapped with a constructor reference, lambda, or method reference.
3. `newValue()` returns `T`, so the caller needs no cast.
4. A Supplier can be replaced with a fake factory in unit tests.
5. You can explicitly check whether the passed factory is null or whether the factory returns null.

Usage:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);

StringBuilder first = box.newValue();
StringBuilder second = box.newValue();

System.out.println(first != second); // true with this constructor reference
```

`StringBuilder::new` creates a new builder each time it is called, because the no-argument constructor executes on every Supplier invocation.

### 4.1. Why use `Supplier<? extends T>`?

A simple declaration:

```java
Supplier<T> factory;
```

is enough for many cases. However, when the factory may return a subtype of `T`, declaring:

```java
Supplier<? extends T> factory;
```

is often more flexible. For example, an API wants to return the general type `Number`, while the actual factory creates `Integer`:

```java
Supplier<Integer> integers = () -> Integer.valueOf(7);
Supplier<? extends Number> numbers = integers;

Number value = numbers.get();
```

`Supplier<? extends T>` is appropriate because `Supplier` is a **producer**: you read a value out of the factory. This is a direct application of the PECS rule (*Producer Extends, Consumer Super*).

You should not switch to `Supplier<? super T>` when the goal is to obtain a `T`, because a factory of type `Supplier<? super T>` may return a broader supertype than `T`, and the compiler cannot guarantee the result is a `T`.

### 4.2. Why check `Objects.requireNonNull`?

```java
Objects.requireNonNull(factory, "factory");
```

makes the failure appear when creating `Box`, rather than waiting until `newValue()` and accidentally calling `.get()` on a null reference.

```java
Objects.requireNonNull(factory.get(), "factory returned null");
```

expresses a specific contract: the `newValue()` method **does not accept a null result**. If the application allows null as a meaningful value, remove or replace this check with an API that describes it clearly, such as `Optional<T>` when appropriate.

Do not add a non-null constraint while ignoring the contract: sometimes a Supplier is designed to return null to represent "no data".

## 5. Providing a Supplier via a constructor reference

A no-argument constructor can match `Supplier<T>`:

```java
class Customer {
    Customer() {
    }
}

Supplier<Customer> factory = Customer::new;
Customer customer = factory.get();
```

`Customer::new` does not instantiate an object immediately when the expression is written. It creates a function object whose behavior invokes the constructor when `get()` is called.

### 5.1. The constructor must be accessible at the reference site

A constructor reference like:

```java
Supplier<Customer> factory = Customer::new;
```

is valid only if the compiler can access the corresponding constructor from the expression's location and overload resolution selects a constructor matching the functional interface.

A class with a `private` constructor cannot be arbitrarily referenced from outside code. However, you can create the Supplier **inside the class** or in a factory method that has access, and then pass it outward without exposing the constructor.

### 5.2. The no-argument constructor may be implicit or explicit

For example:

```java
class Empty {
}
```

If no constructor is declared at all, the compiler may generate a default constructor according to Java's rules; `Empty::new` is valid when that constructor is accessible from the call site.

If the class already declares a parameterized constructor:

```java
class User {
    User(String name) {
    }
}
```

Java **does not automatically add** a no-argument constructor. In that case `User::new` cannot match `Supplier<User>` if only `User(String)` exists; you need a capturing lambda or `Function<String,User>`.

### 5.3. `Class<T>` is not a constructor reference

You cannot write a general `T::new` inside a generic class:

```java
class Box<T> {
    // Supplier<T> factory = T::new; // Invalid.
}
```

`T` is not yet a class name with a known constructor. The caller needs to supply `ActualClass::new` at the site where the concrete class is known.

## 6. Parameterized constructors: capturing lambdas

Given the class:

```java
class Config {
    private final String region;

    Config(String region) {
        this.region = region;
    }

    String region() {
        return region;
    }
}
```

You cannot use `Config::new` as a `Supplier<Config>` if only the `Config(String)` constructor exists:

```java
// Invalid for Supplier<Config>:
// Supplier<Config> factory = Config::new;
```

However, you can **capture the region value**:

```java
String region = "ap-southeast";

Supplier<Config> factory = () -> new Config(region);
Config first = factory.get();
```

The lambda here takes no parameters when `.get()` is called; it has already "captured" the `region` value from the environment where the Supplier was created.

In Java, captured local variables must be `final` or **effectively final** — not reassigned after being captured by the lambda according to language rules.

### 6.1. Capturing differs from always creating an object immediately

```java
Config existing = new Config("ap-southeast");

Supplier<Config> reused = () -> existing;
Supplier<Config> fresh = () -> new Config("ap-southeast");
```

Both Suppliers return type `Config`, but they behave differently:

- `reused.get()` returns the same `existing` instance on every call.
- `fresh.get()` executes `new Config(...)` on every call.

Do not infer from **the type `Supplier<Config>`** that each `.get()` call definitely allocates a new object. That distinction must be defined in the contract.

### 6.2. Dependency injection via lambda

An object may require multiple dependencies:

```java
class Service {
    Service(String endpoint, int timeoutMillis) {
    }
}
```

The caller can provide:

```java
String endpoint = "https://example.invalid";
int timeoutMillis = 1000;

Supplier<Service> serviceFactory =
        () -> new Service(endpoint, timeoutMillis);
```

The example URL is an illustrative configuration string; no network access occurs. What matters is that the dependencies are available at **the site constructing the Supplier**. A generic class receiving `Supplier<Service>` does not have to know that the constructor takes two parameters or how they are configured.

When dependencies vary per call, `Function`/`BiFunction` is usually preferable to a Supplier that captures fixed parameters.

## 7. When to use `Function` or `BiFunction` instead of Supplier?

`Supplier<T>` has a `.get()` method that takes no arguments. If instantiation requires input **on each call**, you can use `Function<A,T>` or `BiFunction<A,B,T>`.

For example, a `record` with two components:

```java
record Ticket(int id, String title) {
}
```

A ticket can be created from a title in a function:

```java
import java.util.function.Function;

Function<String, Ticket> createTicket =
        title -> new Ticket(7, title);

Ticket t = createTicket.apply("Java");
```

If both `id` and `title` are inputs:

```java
import java.util.function.BiFunction;

BiFunction<Integer, String, Ticket> ticketFactory =
        Ticket::new;

Ticket t = ticketFactory.apply(7, "Java");
```

Here `Ticket::new` matches `BiFunction<Integer,String,Ticket>` because the record constructor has two parameters `int` and `String`; the compiler can apply unboxing from `Integer` as needed under compatibility rules.

### 7.1. Generic factory function

```java
static <A, T> T createFrom(
        A input,
        java.util.function.Function<? super A, ? extends T> factory) {
    return java.util.Objects.requireNonNull(
            factory, "factory").apply(input);
}
```

`? super A` on the Function's input allows the factory to accept a broader type than `A`. `? extends T` on the output allows returning a subtype of `T`. This is a flexible design when a factory acts by taking an input and producing an output.

The version above does not check for a null result; if the contract requires non-null, add `Objects.requireNonNull(factory.apply(input), ...)` similarly to the Box example.

### 7.2. When a constructor throws a checked exception

`Supplier<T>.get()` **does not declare `throws` for any checked exception**. If the constructor you want to call throws `IOException` or another checked exception, you cannot directly write a method reference or lambda throwing that checked exception and assign it to a standard Supplier unless you handle the exception inside the lambda.

Illustrative snippet, requiring appropriate imports:

```java
Supplier<String> fromFile = () -> {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("input.txt"));
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
```

This is an **illustrative snippet** and does not read a real file in the main runnable program. It wraps `IOException` into an unchecked exception; that is an API choice, not an approach you should always take.

If checked exceptions are a key part of the contract, define a custom functional interface with `throws`, or consider `Callable<T>` (`call() throws Exception`), depending on your goal. Never silently swallow an exception inside a Supplier and return null when callers need to know about failures.

## 8. Complete Java 17 example

Create the file **`SupplierFactoryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    static final class Resource {
        private static int nextId;
        private final int id = ++nextId;

        int id() {
            return id;
        }
    }

    static final class Config {
        private final String region;

        Config(String region) {
            this.region = region;
        }

        String region() {
            return region;
        }
    }

    record Ticket(int id, String title) {}

    static final class Box<T> {
        private final Supplier<? extends T> factory;

        Box(Supplier<? extends T> factory) {
            this.factory = Objects.requireNonNull(factory, "factory");
        }

        T newValue() {
            return Objects.requireNonNull(
                    factory.get(), "factory returned null");
        }
    }

    static <T> List<T> createMany(
            int count, Supplier<? extends T> factory) {
        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
        Objects.requireNonNull(factory, "factory");

        List<T> values = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            values.add(Objects.requireNonNull(
                    factory.get(), "factory returned null"));
        }
        return values;
    }

    static <A, T> T createFrom(
            A input, Function<? super A, ? extends T> factory) {
        return Objects.requireNonNull(factory, "factory").apply(input);
    }

    public static void main(String[] args) {
        Box<Resource> box = new Box<>(Resource::new);

        Resource a = box.newValue();
        Resource b = box.newValue();
        System.out.println("ids=" + a.id() + "," + b.id());
        System.out.println("distinct=" + (a != b));

        List<Resource> resources = createMany(2, Resource::new);
        System.out.println("batch=" + resources.size());
        System.out.println("batch-ids=" + resources.get(0).id()
                + "," + resources.get(1).id());

        Box<Config> config = new Box<>(
                () -> new Config("ap-southeast"));
        System.out.println("region=" + config.newValue().region());

        Ticket ticket = createFrom(
                "Java", title -> new Ticket(7, title));
        System.out.println("ticket=" + ticket.id()
                + ":" + ticket.title());

        Resource singleton = new Resource();
        Box<Resource> reused = new Box<>(() -> singleton);
        System.out.println("reused="
                + (reused.newValue() == reused.newValue()));

        try {
            new Box<String>(() -> null).newValue();
        } catch (NullPointerException e) {
            System.out.println("null-error=" + e.getMessage());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 -Xlint:all SupplierFactoryDemo.java
java SupplierFactoryDemo
```

The example compiled cleanly with no warnings and produced stdout:

```text
ids=1,2
distinct=true
batch=2
batch-ids=3,4
region=ap-southeast
ticket=7:Java
reused=true
null-error=factory returned null
```

### 8.1. Explaining `ids=1,2` and `distinct=true`

`Resource::new` is a factory that calls `Resource`'s constructor. In this sequential run, each invocation creates a new object and increments `nextId`, yielding two IDs `1` and `2` and references `a != b`.

**Not every Supplier guarantees this.** Evidence of a new object comes from the specific implementation `Resource::new`, not from the type `Supplier<Resource>`.

The static counter `nextId` is used simply for illustration and is **not thread-safe** if the code is called concurrently. Real applications needing unique IDs in multithreaded environments must use proper synchronization or an appropriate ID generator.

### 8.2. Explaining `batch=2` and `batch-ids=3,4`

`createMany` invokes `factory.get()` in a loop. Because the caller passed `Resource::new`, the next two calls create resources with IDs `3` and `4`.

For `count = 0`, the method returns an empty list; it still checks that the factory is non-null. For `count < 0`, the method throws `IllegalArgumentException`. If the factory throws an exception on the `k`-th call, the method does not complete and the exception propagates — this example **does not** automatically roll back previously created objects.

### 8.3. Explaining `region=ap-southeast`

`Config` only has a constructor taking a `String`. The caller uses:

```java
() -> new Config("ap-southeast")
```

to create a `Supplier<Config>` with a parameterless `get()`. The factory captures the configuration, and each invocation calls the `Config(String)` constructor.

### 8.4. Explaining `ticket=7:Java`

`createFrom` takes a `String` input and a `Function` that uses it to create a `Ticket`. If `id` also needs to be supplied per call, `BiFunction<Integer,String,Ticket>` and `Ticket::new` are a more direct choice.

### 8.5. Explaining `reused=true`

`new Box<>(() -> singleton)` returns **the same object** on every `.get()` call. This proves that `Supplier<T>` is a *value-providing* interface, not a contract that *always creates a new instance*. If an API's `newValue()` method name requires a fresh object, document that invariant and design the factory/tests to enforce it.

### 8.6. Explaining `null-error=...`

The example explicitly calls `Objects.requireNonNull(factory.get(), "factory returned null")`. A Supplier is allowed to return null under the general `Supplier` contract, yet `Box` adds a contract **disallowing null** and fails immediately at the boundary.

If "unable to create an object" is a normal business state, consider `Supplier<Optional<T>>` or a dedicated result type instead of throwing `NullPointerException` when that violates the desired contract.

## 9. Intentionally non-compiling example: `new T()` and `T.class`

Create a separate file **`InvalidNewT.java`**:

```java
class InvalidNewT<T extends Number> {
    T create() {
        return new T();
    }

    Class<T> token() {
        return T.class;
    }
}
```

Compile:

```bash
javac --release 17 InvalidNewT.java
```

This is an **intentionally invalid** program. `javac --release 17` returned two diagnostics:

```text
error: unexpected type
  required: class
  found:    type parameter T
```

and:

```text
error: cannot select from a type variable
```

The first error comes from `new T()`. The second error comes from `T.class`.

Fix it properly by changing the design:

```java
final class GenericCreator<T> {
    private final Supplier<? extends T> factory;

    GenericCreator(Supplier<? extends T> factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    T create() {
        return factory.get();
    }
}
```

This is an illustrative class requiring imports for `java.util.function.Supplier` and `java.util.Objects` if placed in its own file. The caller must supply `SomeConcreteType::new` or a lambda when instantiating `GenericCreator<SomeConcreteType>`.

Do not try removing the `<T extends Number>` bound to fix the `new T()` error; removing the bound does not give the compiler a constructor for `T`.

## 10. Why not automatically use Reflection to call a constructor?

Another approach is to accept a **class token**:

```java
static <T> T createWithNoArgs(Class<T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
```

In this example, `Class<T>` carries the concrete runtime class so Reflection can look up a no-argument constructor. It has major differences from Supplier:

| Criterion | `Supplier<T>` | `Class<T>` + Reflection |
| --- | --- | --- |
| Who decides how to create the object? | The caller provides any behavior | Generic code attempts to find a constructor from the class token |
| Is a no-argument constructor required? | No; a lambda can capture arguments | Yes if code calls parameterless `getDeclaredConstructor()` |
| Can a static factory/singleton/pool be used? | Yes | Not automatically, unless designed separately |
| Checked exceptions from reflection | None on `Supplier.get()` | Possible `NoSuchMethodException`, `IllegalAccessException`, `InvocationTargetException`, `InstantiationException` |
| Access scope | Compiler checks method reference/lambda at the creation site | Reflection is subject to access/module rules; `getDeclaredConstructor()` does not mean invocation is always allowed |
| Unit testing with stubs/fakes | Easy to pass a fake Supplier | Needs a real class or additional abstraction |
| API complexity | Usually little boilerplate | Requires handling reflection errors and access policies |

Reflection is useful if you are writing a container, serializer, or framework that needs to instantiate classes chosen dynamically. But for creating `T` when the caller already knows the constructor or construction strategy, `Supplier<T>` is usually simpler and more transparent.

### 10.1. `Class<T>` does not guarantee a constructor exists

```java
Class<T> type;
```

does not prove there is a public no-argument constructor, nor does it prove the type is a concrete class rather than an interface or abstract class. Reflection can fail due to a missing constructor, inaccessible constructor, abstract class, or an exception thrown by the constructor.

You should not use `Class.newInstance()` as a default solution: that API is deprecated; generally prefer `getDeclaredConstructor().newInstance()` when actually choosing reflection.

### 10.2. Parameterized constructors are hard to infer purely with reflection

If `T` only has a constructor taking a `String`, a generic method needs to know parameter names, counts, types, and values, plus overload-selection policy. This is why passing a factory/lambda is usually better:

```java
Supplier<Config> creator = () -> new Config("ap-southeast");
```

The constructor is checked by the compiler in source; the generic class does not have to resolve reflective overloads or access itself.

## 11. Passing Supplier to a generic method instead of storing it in a class

Not every design needs to store the factory in a field. You can ask for the factory directly at the call site:

```java
static <T> T make(Supplier<? extends T> supplier) {
    return Objects.requireNonNull(supplier, "supplier").get();
}
```

Usage:

```java
StringBuilder value = make(StringBuilder::new);
```

Or a method that creates multiple elements:

```java
static <T> List<T> createMany(
        int count, Supplier<? extends T> supplier) {
    if (count < 0) {
        throw new IllegalArgumentException("negative count");
    }
    Objects.requireNonNull(supplier, "supplier");

    List<T> values = new ArrayList<>();
    for (int i = 0; i < count; i++) {
        values.add(supplier.get());
    }
    return values;
}
```

The snippet above is an illustrative method requiring imports for `java.util.List`, `java.util.ArrayList`, `java.util.Objects`, and `java.util.function.Supplier`. If you want to disallow null, add a check on the result of `get()` as in the complete program.

### 11.1. When should you inject via constructor?

Keep `Supplier<? extends T>` in a field when the class needs to create multiple `T` instances across several methods or repeated uses. The advantages are:

- Configure the factory once, use it many times.
- Easy to swap implementations in unit tests.
- The generic class has low coupling to concrete classes.
- Fits simple inversion of control or dependency injection.

If the factory is only needed once, passing it directly to a method can be cleaner.

### 11.2. Should a static `Supplier<T>` be stored in a generic class?

A `static` field cannot simply "carry an instance's `T`":

```java
class Registry<T> {
    // static Supplier<T> factory; // Invalid:
    // cannot reference non-static type variable T.
}
```

`T` belongs to a **class instance's** type parameter, not a separate parameter of a static field. You should store the factory in an **instance field**, or design a static generic method with its own type parameter:

```java
static <T> T create(Supplier<T> factory) {
    return factory.get();
}
```

This avoids confusing class-level and method-level type variables.

## 12. Designing a clear Supplier contract

When you write an API such as:

```java
T create();
```

make clear what "create" entails. A generic Supplier can be type-valid yet fail to satisfy application expectations.

### 12.1. Must it return a new object every time?

```java
Supplier<StringBuilder> fresh = StringBuilder::new;

StringBuilder shared = new StringBuilder();
Supplier<StringBuilder> cached = () -> shared;
```

`fresh.get()` creates a new builder; `cached.get()` returns the same builder again. Both share the type `Supplier<StringBuilder>`.

If the API requires a *fresh instance per call*, state that explicitly in Javadoc/contracts and write tests for it. Simply accepting a Supplier does not prove freshness.

### 12.2. A Supplier can have side effects

```java
AtomicInteger sequence = new AtomicInteger();

Supplier<Integer> nextId = sequence::incrementAndGet;
```

This example requires importing `java.util.concurrent.atomic.AtomicInteger`. Each `get()` call mutates state outside the Supplier. Results depend on invocation count and call order.

Do not assume that calling `.get()` twice will yield equal results or leave state unchanged.

### 12.3. A Supplier can be expensive or fail

A factory may open files, establish sockets, call a service, or initialize expensive resources. If `createMany(1000, factory)` calls `get()` 1000 times, that can be costly.

If the Supplier throws an exception on the fifth call, objects created in the first four calls may need cleanup. Generic factory code does not automatically provide transactions or rollback just because it returns `List<T>`.

### 12.4. A Supplier is not thread-safe by default

A Supplier holding unsynchronized mutable state can suffer data races when multiple threads call `.get()` concurrently. Thread safety depends on the factory implementation and the objects it captures.

When using multiple threads, check:

- Are captured dependencies mutable?
- Are counters or caches synchronized?
- Is a mutable singleton shared across callers?
- Is the object-creation logic allowed to run concurrently?

A simple constructor reference does not automatically guarantee the whole object-creation process is safe in every application.

### 12.5. Nullable factory results

`Supplier<T>` is allowed to return null. If your API forbids null, validate at the boundary:

```java
T value = Objects.requireNonNull(
        supplier.get(), "factory returned null");
```

If null represents a normal state, you can use an `Optional<T>` return type or an application-defined `Result<T,Error>`. Do not overuse `Optional` for every field; distinguish "no result" from "broken factory".

## 13. How do constructor references, lambdas, and method references differ?

All three Suppliers below can provide an object of type `T` in appropriate contexts:

```java
Supplier<StringBuilder> a = StringBuilder::new;
Supplier<StringBuilder> b = () -> new StringBuilder();
Supplier<StringBuilder> c = FactoryMethods::newBuilder;
```

With a helper class:

```java
class FactoryMethods {
    static StringBuilder newBuilder() {
        return new StringBuilder();
    }
}
```

- `StringBuilder::new` is a **constructor reference**.
- `() -> new StringBuilder()` is a **lambda** calling the constructor.
- `FactoryMethods::newBuilder` is a **method reference** to a static factory method.

All of them can match `Supplier<StringBuilder>` because the target method takes no inputs and returns `StringBuilder`.

### 13.1. Which one should you prefer?

Use `SomeClass::new` when the constructor has a matching signature and no extra processing is needed.

Use a lambda when:

- The constructor needs captured arguments.
- You need validation or logic adjustments before or after instantiation.
- You need to pick one of several implementations based on configuration.
- You need to intentionally translate a checked exception into another error contract.

Use a method reference such as `Factories::create` when a well-named static factory already exists or complex creation logic is encapsulated in a standalone method.

### 13.2. Method references are resolved at compile time

`SomeClass::new` does not search for a constructor via reflection at call time. The compiler uses the functional interface's **target type** to select the appropriate constructor overload. Therefore:

```java
Supplier<StringBuilder> supplier = StringBuilder::new;
Function<Integer, StringBuilder> sized = StringBuilder::new;
```

can select different constructors of `StringBuilder`, taking no arguments or taking a capacity, respectively.

If you merely write:

```java
// var creator = StringBuilder::new; // No suitable target type.
```

a method/constructor reference has no standalone functional type to infer from `var` alone; it needs an appropriate **target functional interface**. Assign it to `Supplier<StringBuilder>` or pass it to a method parameter expecting a Supplier.

## 14. Alternatives in object-oriented design

### 14.1. Passing an existing object instead of a factory

If the code only needs an object to store or process:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

There is no need for a Supplier when there is no requirement to create objects in the future.

### 14.2. Using a domain factory interface

If initialization logic involves multiple steps or custom checked exceptions:

```java
interface ConnectionFactory<T> {
    T open(String endpoint) throws Exception;
}
```

An interface with a domain name and parameterized method can be clearer than `Supplier<T>`. Do not force every factory into `Supplier<T>` when the real contract involves endpoints, timeouts, validation, resource cleanup, or complex error handling.

### 14.3. Template method via an abstract class

A generic class can delegate object creation to a subclass:

```java
abstract class Creator<T> {
    protected abstract T create();

    T make() {
        return create();
    }
}
```

The concrete subclass knows `T`:

```java
class StringCreator extends Creator<String> {
    @Override
    protected String create() {
        return "Java";
    }
}
```

This is valid because the subclass implements creating a concrete `String`. However, it requires inheritance to change behavior. `Supplier<T>` is usually more flexible because it uses **composition** and lambdas/constructor references.

## 15. Common misconceptions and fixes

### Misconception 1 — "Since `<T>` is declared, you can use `new T()`"

**False.** `<T>` does not mean the compiler knows the runtime class or constructor to call. Pass `Supplier<T>`/`Supplier<? extends T>` from the caller or design a different factory.

### Misconception 2 — "`T extends SomeClass` guarantees every subtype has a no-argument constructor"

**False.** Constructors are not inherited instance members; a subclass might only have parameterized constructors or not be instantiable. A bound does not solve this problem.

### Misconception 3 — "`Supplier<T>` always creates a new object"

**False.** `() -> existing` returns the same object. If a fresh object is required each time, document and test that condition; use a constructor reference or a factory with the corresponding invariant.

### Misconception 4 — "Constructor references automatically work with every constructor"

**False.** `Supplier<T>` takes no parameters. `User(String)` does not directly match `Supplier<User>`; use `() -> new User("name")` or `Function<String,User>`.

### Misconception 5 — "Storing `Class<T>` is enough to instantiate any `T`"

**False.** `Class<T>` does not guarantee a concrete class, nor an accessible or parameterless constructor, and it does not determine which dependencies need injection. Reflection requires extra error and access handling.

### Misconception 6 — "Supplier cannot be used with interfaces or abstract types"

**False.** A Supplier can return any subtype compatible with `T`. For example, `Supplier<? extends Animal>` can create a `Dog`, even though you cannot `new Animal()` when `Animal` is abstract. The concrete factory decides the implementation.

### Misconception 7 — "Just using `Supplier<T>` means there can never be null"

**False.** A Supplier can return null. You need a contract and a boundary check if non-null is required.

### Misconception 8 — "Because Supplier takes no parameters, it cannot call parameterized constructors"

**False.** A lambda can capture arguments already available at the site creating the Supplier:

```java
Supplier<Config> factory = () -> new Config("ap-southeast");
```

If values must vary on every call, choose an appropriate `Function` or `BiFunction`.

### Misconception 9 — "`Supplier.get()` can declare any checked exception"

**False.** `get()` has no checked `throws`. A lambda assigned to Supplier must handle checked exceptions or use another functional API with `throws`.

### Misconception 10 — "Factory injection is automatically thread-safe"

**False.** A Supplier may capture mutable state, hold caches, or use unsynchronized counters. Thread safety must be designed into the actual factory.

### Misconception 11 — "`Supplier<? super T>` still returns `T`"

**False.** When a producer returns a supertype, the compiler cannot assert the result is `T`. If you only **read `T` values**, use `Supplier<? extends T>` or `Supplier<T>`.

### Misconception 12 — "Suppress the `new T()` error with an annotation"

**Impossible.** This is a **compilation error**, not an unchecked warning. `@SuppressWarnings` does not make `new T()` valid. You must change the API to provide an object-creation strategy.

## 16. Project implementation checklist

| Question | Suitable design |
| --- | --- |
| Does generic code actually need to create objects? | If only storing an existing value, accept `T` directly instead of a Supplier. |
| Does the caller know a concrete class and no-arg constructor? | Pass `Concrete::new`. |
| Does the constructor need fixed configuration from the caller? | Pass `() -> new Concrete(config)`. |
| Do initialization arguments vary per call? | Use `Function`/`BiFunction` or a domain-specific factory. |
| Should the factory be allowed to return a subtype of `T`? | Consider `Supplier<? extends T>`. |
| Is `get()` allowed to return null? | Write a clear contract and validate or encode absence. |
| Must it return a new object every time? | Document and test freshness; do not infer it from the word `Supplier`. |
| Are there checked exceptions in creation logic? | Wrap intentionally or choose a functional interface with `throws`. |
| Do created resources need closing or rollback? | Design ownership, cleanup, and partial-failure handling. |
| Will the factory be called from multiple threads? | Check captured state, singletons, synchronization, and thread safety. |
| Is Reflection genuinely required? | Only when classes are chosen dynamically and constructor/access/exception handling is acceptable. |
| How will unit tests supply objects? | Pass `() -> fake`, `FakeType::new`, or a factory that counts invocations. |

A workflow for refactoring away from `new T()` can be:

1. Identify why the generic code wants to instantiate `T` and when creation happens.
2. Identify which caller knows the concrete type and dependencies.
3. Design the constructor/method to accept `Supplier<? extends T>` or a factory with appropriate inputs.
4. Move `new Concrete(...)` logic to the caller side via a constructor reference or lambda.
5. Define contracts for nullability, freshness, exceptions, ownership, and concurrency.
6. Write tests covering both normal factories and failing/null/reusing factories.
7. Compile with `javac --release 17 -Xlint:all` and test runtime behavior.
8. Ensure no unchecked casts or unnecessary reflection remain just to instantiate `T`.

## 17. Self-check questions

**Question 1.** Why does the following generic class fail to compile?

```java
class Maker<T> {
    T make() {
        return new T();
    }
}
```

<details>
<summary>Answer</summary>

`T` is a type variable, not a concrete class with a constructor known in source. Java does not support a generic constructor bound requiring every subtype to have a no-argument constructor. Pass a factory such as `Supplier<T>` from the caller.

</details>

**Question 2.** If the caller has a no-argument constructor for `Invoice`, how can it supply a factory to `Box<Invoice>`?

<details>
<summary>Answer</summary>

You can write `new Box<>(Invoice::new)` when the constructor is accessible and type inference/target typing applies. `Invoice::new` acts as a Supplier creating an `Invoice` when `.get()` is called.

</details>

**Question 3.** A class only has the constructor `User(String name)`. What kind of factory is needed?

<details>
<summary>Answer</summary>

If the name is fixed upfront, use `() -> new User("Lan")` as a `Supplier<User>`. If the name varies on each creation, use `Function<String,User>` with `User::new` and `.apply(name)`.

</details>

**Question 4.** Does `Supplier<Resource>` guarantee that every `get()` call returns a new object?

<details>
<summary>Answer</summary>

No. `Resource::new` invokes the constructor every time, whereas `() -> existingResource` can always return the same object. Freshness is an additional invariant of the implementation, not part of the `Supplier` interface.

</details>

**Question 5.** Why can a `Supplier<? extends Number>` accept a `Supplier<Integer>`?

<details>
<summary>Answer</summary>

Supplier is a producer: each `get()` returns an `Integer`, and `Integer` is a subtype of `Number`, so the result can be read as a `Number`. `? extends Number` expresses that compatibility without requiring `Supplier<Integer>` to be a subtype of `Supplier<Number>`.

</details>

**Question 6.** Does `Supplier<T>` automatically reject a factory returning null?

<details>
<summary>Answer</summary>

No. The interface does not forbid null. An API using Supplier must decide how to handle it: accept null, fail explicitly with `Objects.requireNonNull`, or represent absence with an appropriate result type.

</details>

**Question 7.** How do `Class<T>` and `Supplier<T>` differ?

<details>
<summary>Answer</summary>

`Class<T>` represents a runtime class for introspection/casting and can be used with reflection to locate constructors; it does not itself guarantee a usable constructor. `Supplier<T>` represents the behavior of providing a value, which can call a constructor, static factory, cache, or other logic. When you simply need the caller to create values, Supplier is usually easier to use and test.

</details>

## 18. Conclusion

**Java does not support `new T()` because `T` is a type variable, not a class name with a known constructor at compile time.** Type erasure explains why a generic class has no separate runtime specialization per type argument, while Java's constructor rules do not guarantee that every subtype `T` shares the same constructors.

The common design pattern is **passing object-creation behavior from the caller into generic code via `Supplier<T>` or `Supplier<? extends T>`**:

```java
Box<StringBuilder> box = new Box<>(StringBuilder::new);
StringBuilder item = box.newValue();
```

For constructors requiring fixed parameters, use a capturing lambda; when parameters vary per call, use `Function`/`BiFunction` or a domain-specific factory. When designing APIs, remember that `Supplier.get()` can return null, return the same object, have side effects, or throw unchecked exceptions. Generic factories are only truly effective when creation contracts, data validation, and object lifecycles are clearly specified.