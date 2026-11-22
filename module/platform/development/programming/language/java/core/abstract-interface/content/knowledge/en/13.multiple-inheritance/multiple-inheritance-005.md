# Precedence of a More Specific Interface's Default Method in Java

When a subinterface overrides a default method from a superinterface, the declaration in the more specific subinterface takes precedence. “More specific” depends on the extends relationship, not on the order in which names are written in implements.

~~~java
interface BaseFormatter {
    default String format() { return "base"; }
}
interface DetailedFormatter extends BaseFormatter {
    @Override
    default String format() { return "detailed"; }
}
final class Report implements DetailedFormatter {}

public class Main {
    public static void main(String[] args) {
        Report report = new Report();
        BaseFormatter view = report;
        System.out.println(report.format());
        System.out.println(view.format());
    }
}
~~~

The output is detailed twice. Both normal calls use the more specific default, even when the reference variable has the parent type.

## Diamond with a More Specific Branch

~~~java
interface Root { default String message() { return "root"; } }
interface Left extends Root {}
interface Right extends Root {
    @Override
    default String message() { return "right"; }
}
final class Result implements Left, Right {}
~~~

Result receives the default from Right: the Right branch overrides the original default, while Left only inherits it. If Left and Right each declare their own default without a subtype relationship, see the article on conflicts between two unrelated defaults.

A subinterface can also override a default with an abstract declaration to force a concrete class to provide the body itself.

## Key Takeaways

- The extends relationship determines which interface is more specific.
- Reversing the order from implements A, B to implements B, A does not change the result.
- Two independent defaults need to be resolved explicitly.
- Concrete methods from a superclass have their own precedence rule.
- InterfaceName.super.method() has limitations; it is not used to arbitrarily bypass a more specific subinterface.

## Self-Check

Child extends Parent and overrides the default run(). Which default does a class that only implements Child use? If the subinterface redeclares run() as abstract, what does a concrete class need to do?

**Answer:** Child's default; the concrete class must provide an implementation.
