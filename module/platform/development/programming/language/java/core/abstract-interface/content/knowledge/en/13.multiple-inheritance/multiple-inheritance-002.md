# Inheriting the Same Abstract Declaration Through Multiple Paths in Java

Two intermediate interfaces can both inherit the same abstract declaration from a root interface. Two paths propagating the contract do not create two separate obligations.

~~~java
interface Task { void run(); }
interface Read extends Task {}
interface Write extends Task {}
interface ReadWrite extends Read, Write {}

final class Worker implements ReadWrite {
    @Override
    public void run() {
        System.out.println("running");
    }
}
~~~

Task.run() is a single abstract declaration inherited through both Read and Write. One public void run() method is enough to fulfill the contract.

## Two Independent Declarations Can Also Be Compatible

~~~java
interface Printable { void print(); }
interface Exportable { void print(); }

final class Report implements Printable, Exportable {
    @Override
    public void print() {
        System.out.println("report");
    }
}
~~~

Printable.print() and Exportable.print() are two different declarations, but one method satisfies both because their signatures are compatible.

| Scenario | Result |
| --- | --- |
| Same abstract declaration through two branches | One implementation |
| Two independent abstract declarations with compatible signatures | One implementation |
| Same name but different parameters | Two overloads, considered separately |
| Same signature but incompatible return types | Type contract error |

An ordinary abstract method of an interface is public. With different throws clauses, the implementation must not declare a checked exception broader than what every contract allows. With generics, check the type arguments across each branch; do not arbitrarily inherit both Source&lt;String&gt; and Source&lt;Integer&gt;.

Do not write two identical methods in one class to “serve” each interface. Changing parameters to create an overload also does not implement the original abstract method. Use @Override so the compiler detects signature mismatches.

## Self-Check

How many methods do two interfaces declaring void execute() require? Can the two declarations execute(String) and execute(int) be merged? Why does the implementation need to be public?

**Answer:** One; no, these are two overloads; because an abstract method of an interface is public.
