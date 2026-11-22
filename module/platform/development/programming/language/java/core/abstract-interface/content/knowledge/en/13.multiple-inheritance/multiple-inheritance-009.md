# Resolving Conflicts by Overriding and Choosing a Valid super Call

When you need to resolve a default conflict, first declare an appropriate override. Then choose a new body, call a specific default, or combine multiple defaults if the contract requires it.

## Two Different Syntaxes

- super.method() calls the corresponding method from the superclass.
- InterfaceName.super.method() calls the default from an appropriate direct superinterface in a valid instance context.

~~~java
interface Root {
    default String id() { return "root"; }
}
interface Specific extends Root {
    @Override
    default String id() { return "specific"; }
}
final class Item implements Root, Specific {
    @Override
    public String id() {
        return Specific.super.id();
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new Item().id());
    }
}
~~~

Output:

~~~text
specific
~~~

Specific is a direct superinterface and provides a more specific default. You cannot use Root.super.id() to bypass Specific; a qualified-super call is subject to rules on direct superinterfaces and specificity.

| Expression | Meaning |
| --- | --- |
| super.label() | Method from the superclass |
| Left.super.label() | Default from the direct superinterface Left, if valid |
| Left.label() | Calls a static method if Left declares it static; does not call a default |
| ((Left) this).label() | Polymorphic instance call, does not force Left's default to run |

Do not use InterfaceName.super for abstract, static, or inaccessible private methods. This is not a reflection mechanism for arbitrarily calling ancestors.

## Choosing Behavior According to the Contract

1. Choose one default if it properly satisfies the contract.
2. Combine two defaults only when they complement each other and side effects are not repeated.
3. Write a new body if a custom policy is needed.
4. Redeclare it as abstract in the subinterface if you want each class to decide for itself.

When investigating, check the signature, return type, visibility, checked exceptions, superclass, and extends relationships. Use @Override, compile, and test through both class and interface references.

## Self-Check

Why is casting ((Left) this) not the same as Left.super? When should you use super.method()? Why should you not always call both defaults?

**Answer:** casting still dispatches polymorphically; super.method() is for the superclass; two defaults may have side effects or incompatible semantics.
