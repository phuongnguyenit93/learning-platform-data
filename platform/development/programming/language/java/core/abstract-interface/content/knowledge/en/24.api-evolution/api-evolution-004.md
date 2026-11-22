# Distinguishing Source, Binary, and Behavioral Compatibility

When a Java library is upgraded, the question “Is the new API compatible?” has at least three different answers. A change may still allow old source code to compile and still allow old bytecode to link with the new library, yet cause the program to run differently than before. Therefore, evaluate **source compatibility**, **binary compatibility**, and **behavioral compatibility** separately.

## 1. Three Types of Compatibility

### Source Compatibility

A change is source-compatible when client source code that was valid against the old API version can still compile against the new API version under the same compiler and appropriate dependency conditions.

This is a test that involves recompiling the client. The outcome can change because the compiler resolves overloads, generic types, or return types based on the new API. Consequently, “still compiles” does not necessarily mean the program will invoke the same overload as before.

### Binary Compatibility

A change is binary-compatible when class files already compiled against the old API can still link with the new library version without recompiling the client. The JVM locates methods and fields using information such as the class name, member name, and binary descriptor.

Binary compatibility is useful when a library is upgraded independently of the application. However, it does not guarantee that every execution path will succeed: a new call might encounter `AbstractMethodError`, a removed member might cause `NoSuchMethodError` or `NoSuchFieldError`, and behavioral changes can still break application logic.

### Behavioral Compatibility

A change is behaviorally compatible when the program continues to satisfy the contract that clients are entitled to rely on. The contract may include return values, exceptions, side effects, element ordering, `null`-handling rules, result immutability, thread safety, or the timing of operations.

Not every implementation detail is part of the contract. If the API does not guarantee element ordering, clients should not rely on an order observed by coincidence. However, when the documentation commits to an ordering, changing that order can break behavioral compatibility even if the method signature remains unchanged.

| Type | Check Question | Primary Verification Method |
|---|---|---|
| Source | Does old source code compile against the new API? | Recompile representative clients |
| Binary | Do old class files run against the new library? | Run already-compiled clients without recompiling |
| Behavioral | Do the observed results and contract remain correct? | Contract, regression, and integration testing |

## 2. Why Can a Change Have Different Effects?

Consider a library containing a `Printer` class. Version 1 only has the `print(Object)` method. A client calls the method with `null`:

~~~java
new Printer().print(null);
~~~

In version 2, the library adds a `print(String)` overload. The old client source code can still compile, but upon recompilation, the compiler selects the `print(String)` overload because `String` is more specific than `Object`. Meanwhile, client bytecode compiled against version 1 still contains a call to the descriptor of `print(Object)`.

This is an important example: **adding an overload usually preserves old binary linkage, but can change which overload is selected when source code is recompiled**. If the two overloads behave differently, the outcome can even vary depending on whether the client has been recompiled.

### Runnable Experiment

Create the following file structure:

~~~text
v1/Printer.java
v2/Printer.java
Client.java
~~~

`v1/Printer.java`:

~~~java
public class Printer {
    public void print(Object value) {
        System.out.println("Object overload");
    }
}
~~~

`v2/Printer.java` keeps the old method and adds an overload:

~~~java
public class Printer {
    public void print(Object value) {
        System.out.println("Object overload");
    }

    public void print(String value) {
        System.out.println("String overload");
    }
}
~~~

`Client.java`:

~~~java
public class Client {
    public static void main(String[] args) {
        new Printer().print(null);
    }
}
~~~

Compile the client against version 1, then replace the library class with version 2 without recompiling the client:

~~~text
javac -d out v1/Printer.java Client.java
javac -d out v2/Printer.java
java -cp out Client
~~~

Output:

~~~text
Object overload
~~~

Now recompile the client against version 2 of the API:

~~~text
javac -cp out -d out Client.java
java -cp out Client
~~~

Output:

~~~text
String overload
~~~

The experiment uses standard Java syntax and runs on JDK 17 and above. The two different outputs do not happen because the JVM picks an overload at runtime: **overloads are selected at compile time**, and then the name and descriptor of the call are recorded in the bytecode.

## 3. Interface Evolution: Adding Abstract and Default Methods

Interface changes must be considered carefully because many classes outside the library may already implement that interface.

### Adding an Abstract Method

Suppose the initial version has:

~~~java
public interface TextCodec {
    String encode(String input);
}
~~~

A client has provided a class `LegacyCodec implements TextCodec`. If the new version adds an abstract method `String id()`, the `LegacyCodec` source code will fail to compile upon recompilation until it implements `id()` or inherits a valid implementation.

Old class files may still load and link on execution paths that do not invoke the new method. However, if a new client calls `id()` on an old `LegacyCodec` instance that lacks a corresponding implementation, the JVM can throw `AbstractMethodError`. Thus, adding an abstract method can preserve certain aspects of binary linkage while still breaking old source code and new execution paths.

~~~java
public interface TextCodec {
    String encode(String input);

    // Added in the new API version:
    String id();
}
~~~

The snippet above illustrates the signature in the new version; it is not a standalone example that can compile alongside every old implementing class.

### Adding a Default Method

Java allows interfaces to provide a default implementation:

~~~java
public interface TextCodec {
    String encode(String input);

    default String normalize(String input) {
        return input.trim();
    }
}
~~~

A precompiled class that only implements `encode` can usually continue working with the new version of the interface and receive the default implementation of `normalize`. New clients compiled against the new interface can call that method on instances of old implementations.

Even so, adding a `default` method is not always harmless:

- If a class implements two interfaces with conflicting default methods of the same signature, the class may have to override the method to resolve the conflict.
- If the class already has a method matching the new signature, the class's method may be used instead of the default one, producing different behavior not intended by the library author.
- If the return type, access level, or type relationships cause the new signature to conflict with existing code, recompilation may fail.

When designing an interface API, consider default methods for functionality that has a sensible default implementation; document its contract clearly and test against representative implementation types. Do not treat `default` as an absolute guarantee for every client.

## 4. Behavioral Changes Despite an Unchanged Signature

Suppose an API exposes the method:

~~~java
List<String> names();
~~~

This signature may remain unchanged across many versions, so client source code and bytecode still compile/link. However, a new version can break behavior if it alters a previous commitment, for example:

- Results that were previously ordered by name now return an unspecified order.
- A list that used to be modifiable now becomes a read-only list.
- A `null` input that used to be supported now throws `NullPointerException`.
- A not-found case that previously returned `Optional.empty()` now throws an exception.
- A method that previously did not modify its input object now mutates it.
- An operation that used to be safe for concurrent calls now uses unprotected shared state.
- A method that used to execute quickly and synchronously now performs I/O or invokes unexpected callbacks.

Some examples only constitute breaking changes if the old contract committed to that behavior. When a behavior was unspecified, distinguish clearly between an actual library bug and a private assumption that a client built on top of unguaranteed implementation details.

When a behavioral change is necessary, update the documentation, release notes, and tests. If the change is likely to affect clients, consider introducing a new method or an opt-in mechanism so users can migrate intentionally.

## 5. Reference Table for API Evolution

| Change | Source | Binary | Behavioral Risks / Notes |
|---|---|---|---|
| Adding a new utility method with a different name | Usually compatible | Usually compatible | Check overloads, shared state, and contract |
| Adding an overload to an existing method | May change resolution or cause ambiguity | Usually preserves old calls if the old member remains intact | Recompiled clients may call a different overload |
| Adding an abstract method to an interface | May prevent old implementing classes from compiling | Old class files may link, but calls to the new method may fail | Risk of `AbstractMethodError` |
| Adding a default method to an interface | Usually compatible, though conflicts may arise | Usually compatible | Inherited or overridden implementations may change the result |
| Removing or renaming a public method | Incompatible if source code uses that method | Incompatible if bytecode still references it | May encounter `NoSuchMethodError` |
| Changing a method's parameter type | Usually incompatible | Old descriptor no longer matches | Check all clients calling the method |
| Changing the return type of a public method | May cause old source code to fail | Usually breaks the binary descriptor | Do not confuse with compiler-generated bridge methods for covariant overrides |
| Changing only the implementation while keeping the signature | Usually compilation-compatible | Usually linkage-compatible | May break the behavioral contract |
| Tightening input preconditions or changing exceptions | May force clients to modify code | Usually does not change the descriptor | Previously valid clients may fail at runtime |

This table is an initial assessment guide and does not replace detailed inspection of signatures, inheritance, generic types, modules, and actual execution paths. “Usually compatible” does not mean exempt from testing.

## 6. How to Evaluate a Change Before Release

1. **Define the public contract.** List signatures, return types, exceptions, `null` rules, mutability of results, ordering, and other guarantees that clients are allowed to rely on.
2. **Check source compatibility.** Recompile a representative set of clients against the new library. Include cases involving overloads, lambdas, method references, generic types, and custom classes implementing interfaces.
3. **Check binary compatibility.** Run already-compiled class files against the new library without recompiling the client. Test execution paths that invoke changed members, especially new methods on instances of old implementations.
4. **Check behavioral compatibility.** Use contract and regression tests to compare outputs, exceptions, side effects, ordering, mutability, and properties guaranteed by the documentation.
5. **Read runtime errors carefully.** `NoSuchMethodError` and `NoSuchFieldError` usually indicate that bytecode is looking for a member that no longer exists with the expected descriptor. `AbstractMethodError` can occur when a call cannot find a concrete implementation. These errors differ from source compilation errors.
6. **Communicate changes clearly.** Release notes should state the changed behavior, affected clients, migration path, and required version. If needed, provide a transition period or new methods before removing the old API.

Binary compatibility analysis tools can detect many signature and structural changes, but they cannot prove behavioral compatibility. Integration testing also does not replace recompiling old clients; each type of check answers a different question.

## 7. Common Evaluation Mistakes

- **Testing compilation only:** source code may compile yet call a different overload or receive new behavior.
- **Running tests only after rebuilding everything:** this overlooks risks to old class files still deployed in the field.
- **Assuming APIs with identical signatures are compatible:** behavior, exceptions, and input preconditions are also part of the contract.
- **Assuming adding a default method is always safe:** conflicts between interfaces and existing methods can still occur.
- **Assuming a client failure proves the library is incompatible:** first determine whether the client relied on documented, guaranteed behavior or on unguaranteed implementation details.
- **Making multiple changes at once:** when a release changes signatures and behavior simultaneously, it is very hard to pinpoint the cause of regressions. Breaking changes down and documenting the before/after contracts makes evaluation easier.

When reviewing a Java upgrade, record separate conclusions along all three axes: source, binary, and behavioral. Only conclude “compatible” after clearly stating which clients it is compatible with, under what conditions, and by which methods it was verified.
