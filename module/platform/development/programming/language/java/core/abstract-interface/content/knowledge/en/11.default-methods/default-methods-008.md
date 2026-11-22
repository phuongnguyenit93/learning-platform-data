# Restrictions on Calling super via a Direct Interface in Java

The `I.super.method()` syntax has restrictions regarding inheritance relationships. The interface name before `.super` must be an appropriate direct superinterface of **the exact class or interface containing the call**, and the call cannot be used to bypass a more specific interface branch.

## 1. Direct and Indirect Are Not the Same

```java
interface Base {
    default String label() {
        return "Base";
    }
}

interface Extended extends Base {
}

final class Item implements Extended {
    @Override
    public String label() {
        return Extended.super.label() + " -> Item";
    }
}
```

`Extended.super.label()` is valid because `Extended` is listed directly in the `implements` clause of `Item`. Even though the body was originally declared in `Base`, `Extended` inherits that default and is an appropriate qualifier at the call site.

Conversely, `Base.super.label()` inside `Item` is invalid: `Base` is only an indirect superinterface. A qualified super call cannot be used to jump arbitrarily to a more distant ancestor.

## 2. Cannot Bypass a More Specific Subinterface

Consider `A` with a default method and `B extends A` overriding that method. If a class directly declares `implements A, B`, Java does not allow calling `A.super.method()` to bypass the more specific implementation from `B`.

```java
interface A {
    default String name() { return "A"; }
}

interface B extends A {
    @Override
    default String name() { return "B"; }
}

class C implements A, B {
    @Override
    public String name() {
        return B.super.name();
    }
}
```

`B.super.name()` selects the more specialized branch. Changing it to `A.super.name()` is a compile-time error because `B` is also a direct superinterface of `C` and is a subtype of `A`. Listing both the parent and the child in `implements` does not grant the right to bypass the child's override.

## 3. Respect Decisions at Intermediate Levels

```java
interface Root {
    default String format() {
        return "Root";
    }
}

interface Middle extends Root {
    @Override
    default String format() {
        return "Middle(" + Root.super.format() + ")";
    }
}

class Bottom implements Middle {
    @Override
    public String format() {
        return Middle.super.format() + " -> Bottom";
    }
}
```

The valid call chain is `Middle` calling `Root.super.format()` where `Root` is directly inherited; `Bottom` calls `Middle.super.format()`. The result of `new Bottom().format()` is `Middle(Root) -> Bottom`. There is no general syntax to jump across multiple levels and force an older body to run; each level needs to respect its own inheritance relationship.

## 4. Cases Where Qualified super Cannot Be Used

- **No default body:** an abstract method has no implementation to call.
- **Static or private:** a static method is called using the interface name; a private helper can only be called from places with access according to Java rules.
- **Static context:** a default method is an instance method, so a qualified super call is invalid inside a static method.
- **Inherited only through a superclass:** if `Parent implements Labelled` and `Child extends Parent`, `Labelled` does not automatically become a direct superinterface of `Child`. Child can use the inherited method via a normal instance call or through `super` when appropriate.
- **A more specific direct branch exists:** an ancestor qualifier cannot be chosen to bypass a child superinterface's override.

| Situation | How to Handle |
| --- | --- |
| `C implements B` and `B extends A` | Consider `B.super.m()`; do not call `A.super.m()` from C. |
| `C implements A, B` and `B extends A` | Respect the more specific branch `B`. |
| `C implements Left, Right`, two independent conflicting defaults | Override in C and explicitly choose `Left.super.m()`/`Right.super.m()` if needed. |
| Target method is abstract/static/private | Do not call using qualified super; use the mechanism appropriate for the method type. |

**Remember:** it is not only the interface names written in `implements` that matter; the inheritance structure and overrides also determine whether a call is valid. If behavior needs to be reused across multiple levels, let each intermediate interface decide how to expose or extend the ancestor's behavior.
