# Field Reference Restrictions and Declaration Order in Java Interfaces

## 1. Two Issues to Distinguish

In an interface field initializer, Java restricts referencing the field itself or a field declared later by **simple name**. This is a compile-time rule. Another case is a qualified name reference that is syntactically valid but reads a runtime field before it is assigned; in that case, the result can be the default value.

Interface fields are always public static final and must have an initializer. To distinguish a constant variable from a field computed at runtime, see the article on compile-time constants.

## 2. Simple-Name Forward Reference and Self-Reference

The following example does not compile:

~~~java
interface BadOrder {
    int FIRST = SECOND + 1;
    int SECOND = 5;
}
~~~

SECOND is used by simple name in the initializer of FIRST before the declaration of SECOND. The fact that SECOND is a compile-time constant does not make this reference valid.

Direct self-reference is also invalid:

~~~java
interface BadSelfReference {
    int COUNT = COUNT + 1;
}
~~~

Declarators on the same line also follow left-to-right order:

~~~java
interface ValidOrder {
    int BASE = 5, NEXT = BASE + 1;
}
~~~

BASE is already declared before NEXT, so the NEXT expression is valid. This rule targets field initializers; method bodies can use fields declared later.

## 3. Qualified Names Can Be Valid Yet Dangerous at Runtime

A qualified name such as RuntimeOrder.LATER avoids the simple-name forward reference error. However, it does not automatically order runtime initialization.

~~~java
interface RuntimeOrder {
    int EARLY = RuntimeOrder.LATER;
    int LATER = supply();

    static int supply() {
        return 42;
    }
}
~~~

During interface initialization, EARLY is assigned before the initializer of LATER runs. At that point, LATER still has the default value 0, so EARLY receives 0; afterward, LATER receives 42.

In contrast, if the later field is a constant variable, the constant value can be known at compile time:

~~~java
interface QualifiedConstant {
    int FIRST = QualifiedConstant.SECOND;
    int SECOND = 7;
}
~~~

FIRST receives 7. The two cases have nearly identical syntax, but different behavior because one field is a constant variable while the other requires a runtime initializer.

## 4. Complete Java 17+ Example

Save to **Main.java**:

~~~java
interface RuntimeOrder {
    int EARLY = RuntimeOrder.LATER;
    int LATER = supply();

    static int supply() {
        return 42;
    }
}

interface QualifiedConstant {
    int FIRST = QualifiedConstant.SECOND;
    int SECOND = 7;
}

public class Main {
    public static void main(String[] args) {
        System.out.println(RuntimeOrder.EARLY);
        System.out.println(RuntimeOrder.LATER);
        System.out.println(QualifiedConstant.FIRST);
    }
}
~~~

Compile and run:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
0
42
7
~~~

During RuntimeOrder initialization, static fields are prepared with default values, and then the initializers are executed in declaration order. EARLY reads LATER before the call to supply assigns the value 42. QualifiedConstant.SECOND is a constant variable, so FIRST receives 7.

## 5. Method Calls, Inherited Fields, and Duplicate Names

A method call in an initializer is not a simple-name field reference, so this syntax is valid:

~~~java
interface Computed {
    int PORT = defaultPort();

    static int defaultPort() {
        return 8080;
    }
}
~~~

PORT is not a constant variable because the initializer calls a method. However, if the called method indirectly reads an unassigned runtime field, the initialization order can still produce an unexpected value.

Fields inherited from a parent interface can also be used in a child interface initializer:

~~~java
interface ParentLimits {
    int MAX = 20;
}

interface ChildLimits extends ParentLimits {
    int WARNING = MAX - 5;
}
~~~

If two independent parent interfaces both declare TIMEOUT, the simple name TIMEOUT can be ambiguous. This is a name resolution error, distinct from a forward reference caused by declaration position. Use East.TIMEOUT or West.TIMEOUT depending on the intended meaning.

## 6. How to Organize Declarations Safely

- Declare base fields before dependent fields.
- For runtime fields, avoid reverse or circular dependencies between initializers.
- When the compiler reports an illegal forward reference, check whether the initializer uses the simple name of a field declared later or a self-reference.
- Do not prepend the interface name to a field just to silence the compiler error without considering the runtime order.
- Move complex configuration or configuration with side effects to a factory/service if initialization timing needs to be controlled.
- When multiple parent interfaces share the same field name, use the qualifier of the interface that defines the field to be read.

### Self-Check

1. FIRST uses SECOND by simple name when SECOND is declared later: **compilation error**.
2. FIRST uses QualifiedConstant.SECOND, with SECOND = 7: **valid and receives 7**.
3. EARLY uses RuntimeOrder.LATER, with LATER = supply(): **EARLY can receive 0** because the runtime initializer of LATER has not run yet.
4. Can a static method be declared after the field that calls it? **Yes**, but you need to check which runtime fields it depends on.

Read according to three questions: whether the reference is a simple name or a qualified name; whether the target field has already been declared earlier; and whether the value is a constant variable or is only computed when the interface initializes.
