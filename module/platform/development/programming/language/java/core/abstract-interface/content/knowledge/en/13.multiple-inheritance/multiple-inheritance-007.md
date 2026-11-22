# Conflict Between a Default Method and an Independent Abstract Method in Java

A default method with a body does not automatically satisfy an override-equivalent abstract declaration from an independent interface. Both a class and a subinterface combining these two sources must resolve this explicitly.

## Class Combining Two Interfaces

~~~java
interface DefaultTask {
    default String run() { return "default"; }
}
interface RequiredTask {
    String run();
}
// Invalid if not overridden:
// class BrokenTask implements DefaultTask, RequiredTask {}

final class Task implements DefaultTask, RequiredTask {
    @Override
    public String run() {
        return DefaultTask.super.run() + " + verified";
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new Task().run());
    }
}
~~~

Output:

~~~text
default + verified
~~~

Task.run() provides an explicit implementation and intentionally delegates to the default. If the override is omitted, the compiler reports that the class has not implemented RequiredTask's abstract method.

## Subinterface Combining Two Interfaces

~~~java
interface DefaultTask {
    default String run() { return "default"; }
}
interface RequiredTask {
    String run();
}
interface Combined extends DefaultTask, RequiredTask {
    @Override
    default String run() {
        return DefaultTask.super.run() + " via Combined";
    }
}
final class Worker implements Combined {}
~~~

Combined resolves the conflict at the interface level. If it declares run() as abstract instead of default, a concrete class must implement it itself.

| Method source | Result |
| --- | --- |
| Two independent, compatible abstract methods | One implementation can satisfy both |
| One default and one abstract from independent interfaces | Requires an explicit declaration to resolve |
| Two independent defaults | Requires resolving the default conflict |
| Subinterface overrides a parent interface method | Override/specificity rules apply |
| Superclass has an abstract method | A concrete subclass must still fulfill the class obligation |

Do not infer solely from the fact that a method has a body. Java examines the signatures and relationships between the sources; it does not decide based on the business semantics of the default.

References: [JLS §9.4.1.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3) and [JLS §8.4.8.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.4).

## Self-Check

Why can't a subinterface be left empty when inheriting an independent default and abstract method? How can you intentionally reuse the default? Do two compatible abstract methods always cause an error?

**Answer:** it must redeclare to resolve it; override and then call DefaultTask.super.run(); no.
