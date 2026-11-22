# Declaring Generic Interfaces and Generic Abstract Classes in Java

## 1. What problem do generics solve?

Generics allow an interface or class to represent type relationships without having to write multiple versions that differ only in data types. Type parameters such as **T**, **S**, **K**, and **V** are declared on a type; when using it, the caller provides type arguments such as **String**, **Integer**, or **User**.

~~~java
interface Converter<S, T> {
    T convert(S source);
}

abstract class Repository<T, ID> {
    public abstract T findById(ID id);
}
~~~

In **Converter&lt;S, T&gt;**, S is the input type and T is the result type. In **Repository&lt;T, ID&gt;**, T is the type of the managed object and ID is the key type. These types are preserved throughout the signatures, so the compiler can detect mismatched calls before runtime.

## 2. Declaring a generic interface

One type parameter:

~~~java
interface Box<T> {
    T get();
}
~~~

Multiple type parameters:

~~~java
interface Pair<K, V> {
    K key();
    V value();
}
~~~

The names T, K, and V are only conventions, not keywords. Descriptive names such as Source, Result, or ID can be used if that makes the contract easier to read.

When a class implements `Box<String>`, the `get()` contract has a return type of `String`; if the class keeps `T` and implements `Box<T>`, the contract remains generic. How to choose and fully implement this is analyzed in the next lesson.

An interface can also extend a generic interface and forward or fix the parameters:

~~~java
interface Source<T> {
    T read();
}

interface NamedSource extends Source<String> {
    String name();
}

interface TransformSource<S, T> extends Source<T> {
    S original();
}
~~~

**NamedSource** inherits a contract that has already chosen T = String, so read() returns String. **TransformSource&lt;S, T&gt;** keeps both parameters and passes T to Source&lt;T&gt;. An interface can extend multiple interfaces; the inherited signatures must still be compatible with standard Java rules.

## 3. Declaring a generic abstract class

A generic abstract class can use type parameters in fields, constructors, regular methods, and abstract methods:

~~~java
abstract class Holder<T> {
    private final T value;

    protected Holder(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }

    public abstract String describe();
}
~~~

With **Holder&lt;String&gt;**, getValue() has a return type of String. The constructor accepts T to initialize state, while describe() lets a concrete class provide its own behavior. An abstract class cannot be instantiated directly with new.

A class can declare multiple type parameters:

~~~java
abstract class Repository<T, ID> {
    public abstract T findById(ID id);
    public abstract void save(T entity);
}
~~~

**Repository&lt;User, Long&gt;** therefore accepts a Long key and returns a User. In the `Holder<T>` example above, the `Holder(T value)` constructor uses the T declared at the class level, rather than declaring a new type parameter. Java also allows a generic constructor to have its own type parameter, independent of the class's T.

## 4. Connecting an interface with an abstract class

An abstract class can implement an interface and share a common implementation for subclasses:

~~~java
interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
    private final ID id;

    protected Entity(ID id) {
        this.id = id;
    }

    @Override
    public final ID id() {
        return id;
    }
}

final class User extends Entity<Long> {
    private final String name;

    User(Long id, String name) {
        super(id);
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

**Entity&lt;ID&gt;** forwards ID to the interface and provides a shared way to store the ID. **User** fixes ID to Long. An abstract class can implement part of the contract and leave the rest to subclasses; a concrete class must complete any unimplemented abstract methods. Java allows a class to extend one parent class and implement multiple interfaces.

## 5. Runnable example

Save the following program to **GenericDeclarationDemo.java**:

~~~java
interface Mapper<S, T> {
    T map(S source);
}

interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
    private final ID id;

    protected Entity(ID id) {
        this.id = id;
    }

    @Override
    public final ID id() {
        return id;
    }
}

final class User extends Entity<Long> {
    private final String name;

    User(Long id, String name) {
        super(id);
        this.name = name;
    }

    String name() {
        return name;
    }
}

abstract class Repository<T, ID> {
    public abstract T findById(ID id);
}

final class UserRepository extends Repository<User, Long> {
    @Override
    public User findById(Long id) {
        return new User(id, "Lan");
    }
}

public class GenericDeclarationDemo {
    public static void main(String[] args) {
        Mapper<String, Integer> length = String::length;
        System.out.println("length=" + length.map("Java"));

        Repository<User, Long> repository = new UserRepository();
        User user = repository.findById(7L);
        System.out.println("user=" + user.name() + ", id=" + user.id());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac GenericDeclarationDemo.java
java GenericDeclarationDemo
~~~

Output:

~~~text
length=4
user=Lan, id=7
~~~

In this example, Mapper links an input String to an output Integer; Entity holds a typed ID; Repository links the entity type to the key type. Those relationships are shown directly in the declarations and require no casts at the call site.

## 6. Declaration mistakes to avoid

- **Using a primitive as a type argument:** List<int> is invalid; use List&lt;Integer&gt;.
- **Using a type parameter out of scope:** T is valid only if it is declared on the current class, interface, or method.
- **Using a class's instance T in a static member:** a static member is not tied to an object with a specific T. A static generic method must declare its own type parameter if it needs to use a generic type.
- **Confusing extends with implements:** a class uses extends to inherit from a class and implements to implement an interface. In type parameter bounds, extends is used for both classes and interfaces.
- **Using a raw type unnecessarily:** declaring Box instead of Box&lt;String&gt; loses part of the type checking.

The following lessons go deeper into fixing or keeping type parameters when implementing, the scope of generic methods, type bounds, wildcards, and type erasure. In this lesson on declarations, focus on identifying which type parameter belongs to which type and how it is passed through signatures.
