# Checked exceptions when overriding methods in Java

A checked exception is part of the contract checked at compile time. When overriding or implementing a method, a subclass must not force the caller to handle a checked exception that is new or broader than what the parent contract allows.

## 1. Rules

If the parent method declares checked exceptions, the child method can keep those types, choose an appropriate subtype, omit some types, or declare no checked exceptions. If the parent does not declare a checked exception, the child cannot add a new checked exception. Unchecked exceptions are not subject to this restriction; the next lesson specifically covers caller behavior and responsibilities.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

abstract class DataSource {
    abstract String load(String key) throws IOException;
}

final class CacheSource extends DataSource {
    @Override
    String load(String key) throws FileNotFoundException {
        return "cached:" + key;
    }
}
~~~

FileNotFoundException is a subtype of IOException, so this is a valid override.

| throws in parent | throws in child | Valid? |
| --- | --- | --- |
| IOException | IOException | Yes |
| IOException | FileNotFoundException | Yes |
| IOException | No throws | Yes |
| IOException | Exception | No: broader |
| IOException | SQLException | No: incompatible checked type |
| No checked exception | IOException | No |
| No checked exception | IllegalStateException | Yes: unchecked |

The rule evaluates the throws declaration, not whether the current method body actually throws an exception.

## 2. Why can't checked exceptions be broadened?

~~~java
import java.io.IOException;

class Parent {
    void read() throws IOException { }
}

class Child extends Parent {
    @Override
    void read() throws Exception { } // Invalid
}
~~~

A caller using a variable of type Parent may have caught or declared IOException. If Child.read() were allowed to declare Exception, a polymorphic call could raise multiple types of checked exceptions that the caller has not been required to handle. The compiler blocks that case.

Similarly, if an interface declares void run() with no checked exceptions, an implementation cannot add throws IOException. It must handle the exception in its body, convert it to an appropriate error, or change the contract where API design authority exists.

## 3. Caller obligations still follow the static type

~~~java
import java.io.IOException;

interface Worker {
    void work() throws IOException;
}

final class LocalWorker implements Worker {
    @Override
    public void work() {
        System.out.println("done");
    }
}

class UseWorker {
    void run() throws IOException {
        Worker polymorphic = new LocalWorker();
        polymorphic.work(); // Handle/declare IOException according to Worker

        LocalWorker concrete = new LocalWorker();
        concrete.work();    // IOException not required according to LocalWorker
    }
}
~~~

The fact that LocalWorker.work() does not declare a checked exception does not remove the obligation at a call through a Worker variable, because the compiler checks against the declaration visible through the static type.

## 4. Multiple contracts at once

If a class implements two interfaces that have the same method but declare throws IOException and throws SQLException respectively, a common implementation must satisfy **both**. It is not possible to simply choose the more convenient contract; the usual solution is to handle checked exceptions internally and not declare them on the implementation.

In an inheritance chain, each override must be compatible with the nearest contract it overrides. If GrandParent allows Exception, and Parent narrows it to IOException, then Child can only narrow it further according to Parent's rules; it cannot use SQLException just because it is also a subclass of Exception.

## 5. throws does not distinguish overloads

It is not possible to declare two methods with the same name and the same parameters that differ only in throws. The throws list is not a component that distinguishes overload signatures, but it is checked by the compiler when a method actually overrides another. A constructor also does not override a parent constructor; however, a child constructor must still handle checked exceptions arising from a super(...) call according to the usual rules.

When encountering a compiler error about exceptions, correctly identify the overridden method, classify the exception, check the subtype relationship against each parent/interface contract, and inspect the static type at the call site. Do not remove @Override to work around the error: the annotation does not cause the throws restriction; it only helps the compiler confirm the override relationship.
