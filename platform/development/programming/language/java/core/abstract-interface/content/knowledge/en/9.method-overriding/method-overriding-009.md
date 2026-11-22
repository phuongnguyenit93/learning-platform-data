# Varargs Parameters, Arrays, and Confusions When Overriding Methods in Java

In method declarations, **T...** is a convenience syntax for the array parameter **T[]**. Therefore, replacing varargs with an array or vice versa does not by itself create a new signature: the two declarations can override each other if all other conditions are valid.

## 1. Same Parameter Type, Different Call Syntax

~~~java
class ParentVarargs {
    void print(String... words) {
        System.out.println(java.util.Arrays.toString(words));
    }
}

class ChildArray extends ParentVarargs {
    @Override
    void print(String[] words) {
        System.out.println("child: " + java.util.Arrays.toString(words));
    }
}
~~~

With ParentVarargs parent = new ChildArray(), the call parent.print("A", "B") is valid because the declaration visible at compile time is varargs. The compiler packs the two strings into a String[], and then runtime dispatch invokes ChildArray.print(String[]).

Conversely, with ChildArray child = new ChildArray(), the call child.print("A", "B") is invalid: the declaration visible through the ChildArray type uses String[], so it must be called as child.print(new String[]{"A", "B"}).

The reverse direction also holds: a parent class declaring print(String[]) and a child class overriding it with print(String...) still have the same parameter type; however, calling through a variable of the parent type still requires passing an array if the declaration in the parent is not varargs.

## 2. Demonstration Program

~~~java
public class VarargsOverrideDemo {
    public static void main(String[] args) {
        ParentVarargs ref = new ChildArray();
        ref.print("Java", "17");
        ref.print(new String[]{"A", "B"});

        ChildArray direct = new ChildArray();
        direct.print(new String[]{"C"});
        ref.print((String) null);
        direct.print((String[]) null);
    }
}
~~~

Combined with the two classes in Section 1, the output is:

~~~text
child: [Java, 17]
child: [A, B]
child: [C]
child: [null]
child: null
~~~

(String) null is a null argument packed into a single-element array. (String[]) null passes the null array reference itself. You should not rely on print(null) to express intent because the compiler may interpret it as a null array and emit a warning; an explicit type cast is easier to read.

## 3. Signature Constraints

- Varargs must be the last parameter, and each method can have at most one varargs parameter.
- int... is equivalent to int[]; String[]... is equivalent to String[][].
- Two overloads cannot be declared in the same class differing only in f(String...) and f(String[]); those are duplicate signatures.
- Object[] and String[] are different parameter types, even though a String[] array can be assigned to Object[].
- Autoboxing at the call site does not convert int[] to Integer[] and does not create an override relationship between two signatures of different types.

## 4. Reflection and Generic Varargs

Method.isVarArgs() indicates whether **the method is declared** with varargs syntax. The compiler can allow Parent.print(String...) and Child.print(String[]) to override each other even though isVarArgs() returns different values. When using reflection, look up the parameter using String[].class.

Generic varargs such as List&lt;String&gt;... can cause warnings due to non-reifiable array types and the risk of heap pollution. @SafeVarargs may only be used in places permitted by Java; it is not a way to arbitrarily suppress warnings.

**Remember:** compile time determines whether varargs syntax is valid at the call site; runtime dispatch selects the overriding body. When debugging, check both the static type of the receiver and the varargs/array declaration form.
