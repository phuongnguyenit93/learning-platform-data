# Covariant Return Types and Primitive Type Limitations When Overriding in Java

**Covariant return** allows an override to return a more specific reference type than the type declared in the parent. For example, if the parent returns Number, the child can return Integer. This does not allow changing a primitive to another primitive or to a wrapper.

## 1. Key Rules

| Return type in parent | Return type in child | Result |
| --- | --- | --- |
| Object | String | Valid: String is a subtype of Object |
| Number | Integer | Valid |
| CharSequence | String | Valid |
| Object | int[] | Valid: an array is a reference type |
| String | Object | Invalid: the child's return type is broader |
| int | int | Valid |
| int | long or Integer | Invalid |
| void | void | Valid |
| void | String | Invalid |

Primitive types must remain exact. Boxing, unboxing, or primitive widening in an expression does not make two return types covariant.

## 2. Runnable Example

~~~java
public class CovariantDemo {
    public static void main(String[] args) {
        Item general = new Note("Java");
        Note specific = new Note("Java");

        Number size = general.size();
        Integer exactSize = specific.size();

        System.out.println(general.label() + ":" + size);
        System.out.println(specific.label() + ":" + exactSize);
        System.out.println(general.copy().getClass().getSimpleName());
    }
}

abstract class Item {
    public abstract CharSequence label();
    public abstract Number size();
    public abstract Item copy();
}

final class Note extends Item {
    private final String text;

    Note(String text) { this.text = text; }

    @Override public String label() { return text; }
    @Override public Integer size() { return text.length(); }
    @Override public Note copy() { return new Note(text); }
}
~~~

~~~bash
javac CovariantDemo.java
java CovariantDemo
~~~

~~~text
Java:4
Java:4
Note
~~~

Integer size() is valid because Integer is a subtype of Number; text.length() is boxed into Integer in the return expression. This is different from changing the parent signature from int to Integer. Through an Item variable, the compiler still treats the result of size() as Number, even though Note.size() runs at runtime.

## 3. Generics and Arrays Require Checking the Full Type

Generics are generally invariant: List&lt;Integer&gt; is not a subtype of List&lt;Number&gt;. Therefore, if the parent returns List&lt;Number&gt;, the child cannot override it with List&lt;Integer&gt;. The List<? extends Number> contract is more flexible and can be implemented with List&lt;Integer&gt;.

Arrays are reference types: Object data() can be overridden with int[] data(), because int[] is a subtype of Object. However, int data() cannot be changed to long data().

~~~java
import java.util.List;

abstract class NumberReader {
    abstract List<? extends Number> read();
}

final class IntegerReader extends NumberReader {
    @Override
    List<Integer> read() {
        return List.of(2, 5, 7);
    }
}
~~~

This is an example of return type relationships; it is not a standalone program with main.

## 4. Bridge Methods Are a Compilation Detail

Java uses type erasure for generics. The compiler can generate a *bridge method* so that calls through the parent type still dispatch to the concrete implementation after erasure or when the return type is covariant. For example, Box&lt;T&gt;.get() can be implemented by TextBox extends Box&lt;String&gt; with String get(). You do not need to declare a bridge method yourself; write a valid override and use @Override.

## 5. Distinguishing Return Types from Parameters

Covariant return is only about the **return type**. If the parent has Number convert(Number value) and the child declares Integer convert(Integer value), the parameter has changed; that is an overload, not an override of convert(Number). To override, keep the corresponding parameters and you can narrow the return type.

**Remember:** check the subtype relationship of the entire returned reference type; for primitives and void, keep the type unchanged. Return types are not used to create overloads and do not determine which overload is selected.
