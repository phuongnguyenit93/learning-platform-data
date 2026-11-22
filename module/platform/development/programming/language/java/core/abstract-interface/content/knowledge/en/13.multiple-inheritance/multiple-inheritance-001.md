# The diamond problem in Java interface hierarchies

The diamond problem occurs when a type receives a contract or behavior through multiple interface branches. Java does not allow a class to directly inherit from multiple classes, but an interface can extend multiple interfaces and a class can implement multiple interfaces.

~~~text
Root -> Left -> Child
Root -> Right -> Child
~~~

| Hierarchy | Result | Reason |
| --- | --- | --- |
| Two branches inherit the same abstract method from the root | Usually valid | One compatible implementation satisfies the shared contract. |
| Two branches inherit the same default from the root, without overriding | Valid | There is only one default implementation. |
| Two independent interfaces provide defaults with the same signature | Requires resolution | Java does not automatically choose between two peer bodies. |

~~~java
interface Root {
    void run();
    default String label() { return "root"; }
}
interface Read extends Root {}
interface Write extends Root {}
interface ReadWrite extends Read, Write {}

final class Worker implements ReadWrite {
    @Override
    public void run() {
        System.out.println("run once");
    }
}
public class Main {
    public static void main(String[] args) {
        Worker worker = new Worker();
        Root root = worker;
        ReadWrite combined = worker;
        root.run();
        combined.run();
        System.out.println(combined.label());
    }
}
~~~

Output:

~~~text
run once
run once
root
~~~

Worker.run() is one implementation called twice through two reference types. label() is inherited from Root through both branches without creating a conflict.

When analyzing, find the actual declaration site of each method; compare the name, parameters, return type, visibility, and throws; check the superclass; then decide whether an override is needed in the subclass or subinterface.

Fields in an interface are public static final constants; an interface has no instance fields to copy across branches.

## Self-check

How many implementations do two branches inheriting the same abstract method need? Do two branches inheriting the same default from the root conflict on their own? What needs to be done when two independent interfaces have defaults with the same signature?

**Answer:** One; no; an override or an appropriate resolution declaration is needed.
