# Implementing an Interface with a Concrete Type Argument or Preserving the Type Parameter in Java

## 1. Two Options When Implementing

Suppose an interface declares a generic contract:

~~~java
interface Processor<T> {
    T process(T value);
}
~~~

When implementing an interface, a class typically chooses one of two approaches:

- **Fixing the type:** using a concrete type argument, such as implements Processor&lt;String&gt;. The class commits to supporting the contract for String.
- **Preserving genericity:** declaring the type parameter on the class itself, such as class IdentityProcessor&lt;T&gt; implements Processor&lt;T&gt;. The class preserves the type relationship and can be used with multiple type arguments.

Which approach to choose depends on the responsibility of the implementation. A string normalizer can be specialized for String; a value forwarder can preserve T as is.

## 2. Fixing the Type Parameter

~~~java
interface Processor<T> {
    T process(T value);
}

final class TrimProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
~~~

In the **implements Processor&lt;String&gt;** clause, T is replaced with String. Therefore, the signature must accept String and return String. **TrimProcessor** does not need to declare its own type parameter, because the supported type is already determined.

~~~java
Processor<String> processor = new TrimProcessor();
String result = processor.process("  Java  ");
~~~

The compiler accepts calls with String and rejects incompatible values such as Integer. This approach fits a specialized adapter, a string normalizer, or a repository that manages only one entity type.

## 3. Preserving the Interface's Type Parameter

~~~java
interface Processor<T> {
    T process(T value);
}

final class IdentityProcessor<T> implements Processor<T> {
    @Override
    public T process(T value) {
        return value;
    }
}
~~~

**IdentityProcessor&lt;T&gt;** declares T at the class level and passes that same parameter to **Processor&lt;T&gt;**. T is not fixed at the class declaration:

~~~java
Processor<String> textProcessor = new IdentityProcessor<>();
Processor<Integer> numberProcessor = new IdentityProcessor<>();

String text = textProcessor.process("hello");
Integer number = numberProcessor.process(42);
~~~

The diamond operator <> allows the compiler to infer the type argument in the appropriate context. With a Processor&lt;String&gt; reference, the signature visible at the call site accepts String and returns String; with Processor&lt;Integer&gt;, it accepts Integer and returns Integer. A generic implementation is still only valid within the limits that T allows. If the algorithm needs specific capabilities such as comparison or calling doubleValue(), declare the corresponding type bound instead of assuming every T has that behavior.

## 4. Mapping Multiple Type Parameters

When an interface has multiple parameters, the implementation must provide a corresponding type argument for each position:

~~~java
interface Converter<S, T> {
    T convert(S source);
}

final class StringLengthConverter implements Converter<String, Integer> {
    @Override
    public Integer convert(String source) {
        return source.length();
    }
}

final class IdentityConverter<U> implements Converter<U, U> {
    @Override
    public U convert(U source) {
        return source;
    }
}
~~~

**StringLengthConverter** fixes the source type to String and the target type to Integer. **IdentityConverter&lt;U&gt;** keeps a single parameter U for both source and target. The parameter name in the implementing class does not need to match the name in the interface; what matters is that the position and type relationship are correct.

A type argument can be a parameterized type, for example **Holder<List&lt;String&gt;>**, as long as that type is valid. Java does not allow primitives as type arguments; use wrappers such as Integer and rely on boxing/unboxing when appropriate.

## 5. Preserving the Type Through Inheritance

An abstract class can preserve the type parameter and let a subclass fix it:

~~~java
interface Repository<T> {
    T findById(long id);
}

abstract class BaseRepository<T> implements Repository<T> {
    // An abstract class is allowed to defer findById.
}

final class User {
    private final long id;

    User(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}

final class UserRepository extends BaseRepository<User> {
    @Override
    public User findById(long id) {
        return new User(id);
    }
}
~~~

**BaseRepository&lt;T&gt;** forwards T to the interface and can defer the implementation because it is abstract. **UserRepository** fixes T to User, so the implemented method must return User. If a subclass has not implemented the abstract method and also does not inherit a suitable implementation, that class must remain abstract.

## 6. Typical Compilation Errors

### Using T Without Declaring T

~~~java
interface Processor<T> {
    T process(T value);
}

// Invalid: T is not in scope for BrokenProcessor.
class BrokenProcessor implements Processor<T> {
}
~~~

If you want the class to be generic, declare **BrokenProcessor&lt;T&gt; implements Processor&lt;T&gt;**. If the class only processes strings, use **Processor&lt;String&gt;** and declare the signature to accept/return String.

### Preserving T but Implementing a Specialized Signature

~~~java
interface Processor<T> {
    T process(T value);
}

// Invalid: the class claims to support any T but only accepts String.
class BadProcessor<T> implements Processor<T> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
~~~

**BadProcessor&lt;T&gt;** promises to fulfill Processor for any T, but process(String) cannot handle Integer or other T types. Fix T to String if the implementation only supports strings, or implement process(T) if the class is truly generic.

### Fixing T but Using the Wrong Signature

~~~java
interface Processor<T> {
    T process(T value);
}

class WrongProcessor implements Processor<String> {
    // Fails to override process(String).
    public Object process(Object value) {
        return value;
    }
}
~~~

After replacing T with String, the contract requires process(String) to return String. process(Object) is a different method; the @Override annotation will help the compiler catch the error when placed on an incompatible signature.

## 7. Choosing a Design by Responsibility

| Need | Suggested Declaration | Reason |
| --- | --- | --- |
| Only processes strings | implements Processor&lt;String&gt; | Concrete contract, easy to use |
| Same algorithm for multiple types | class ProcessorImpl&lt;T&gt; implements Processor&lt;T&gt; | Preserves the type across input and result |
| Converting between two different types | implements Converter&lt;String, Integer&gt; | Clear source and target |
| Base class defers implementation | abstract class BaseRepository&lt;T&gt; implements Repository&lt;T&gt; | Subclass decides the type later |
| Needs capabilities specific to a group of types | Use an appropriate type bound | The compiler checks the condition before calling |

Do not add a type parameter just to make a class look more generic. Conversely, do not fix the type too early if the implementation genuinely supports multiple types.

**Scope of this article:** invariance and wildcards affect generic types at API boundaries; type erasure and bridge methods explain signatures at runtime. Those two topics have their own articles in the chapter. When implementing, the first thing to check is whether each type parameter has been consistently fixed or forwarded across all signatures.
