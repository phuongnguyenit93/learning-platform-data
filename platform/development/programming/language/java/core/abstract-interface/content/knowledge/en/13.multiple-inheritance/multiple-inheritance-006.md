# Default method conflict from two unrelated interfaces in Java

When two interfaces with no inheritance relationship establishing precedence both provide a default method with the same signature, Java does not automatically choose one body. The combining class or subinterface must define the behavior.

~~~java
interface AuditLog {
    default String format(String event) {
        return "AUDIT:" + event;
    }
}
interface ConsoleLog {
    default String format(String event) {
        return "CONSOLE:" + event;
    }
}
final class UnifiedLog implements AuditLog, ConsoleLog {
    @Override
    public String format(String event) {
        return AuditLog.super.format(event)
                + " | " + ConsoleLog.super.format(event);
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new UnifiedLog().format("LOGIN"));
    }
}
~~~

Output:

~~~text
AUDIT:LOGIN | CONSOLE:LOGIN
~~~

UnifiedLog.format() is the single public override. The calls AuditLog.super.format() and ConsoleLog.super.format() explicitly select the default from the appropriate direct superinterface.

## Three strategies

- **Choose one default** if one source properly satisfies the contract.
- **Combine both defaults** if they complement each other and side effects are not duplicated.
- **Write a new body** if neither default is appropriate.

Do not call both just to clear the compile error; they may log, emit events, or update state twice.

## Conflict in a subinterface

~~~java
interface Left {
    default String name() { return "left"; }
}
interface Right {
    default String name() { return "right"; }
}
interface Combined extends Left, Right {
    @Override
    default String name() {
        return Left.super.name() + "/" + Right.super.name();
    }
}
~~~

Combined provides a new default, so a class implementing Combined can inherit this body. Another option is to declare name() abstract to push the responsibility down to concrete classes.

Do not confuse this with two branches both inheriting a single default from an ancestor, or two compatible abstract methods. Two methods with the same name but different parameters are overloads. If the return types are incompatible, an override cannot fix the type contract.

Reference: [JLS §9.4.1.3 — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3).

## Self-check

Two independent interfaces have default name(); what happens if a class does not override it? Why does Java not compare bodies to choose one? When is InterfaceName.super.method() useful?

**Answer:** compilation error; rules are based on types and inheritance; when an override needs to call the appropriate default.
