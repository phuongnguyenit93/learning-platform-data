# Generic invariance and wildcards at API boundaries in Java

## 1. Why are generics invariant?

If Integer is a subtype of Number, a Number variable can refer to an Integer. However, that relationship does not extend to List\<Integer> being a subtype of List\<Number>:

~~~java
Number number = Integer.valueOf(10);
List<Integer> integers = new ArrayList<>();

// Does not compile:
// List<Number> numbers = integers;
~~~

If the assignment above were valid, a recipient could add a Double to a list intended only for Integer. Java rejects the assignment to preserve type safety at compile time.

## 2. Choosing a wildcard by operation

| Parameter type | Safely read as | Adding non-null values | Use when |
| --- | --- | --- | --- |
| List\<T> | T | Can add T | You need to read and write the same known type |
| List<?> | Object | Cannot add arbitrary values | Only iterating over/printing elements |
| List<? extends Number> | Number | Cannot add an arbitrary Number | Reading numeric types |
| List<? super Integer> | Object | Can add Integer | Writing Integer to a list of that type or a supertype |

### Upper bound: Producer Extends

~~~java
static double sum(List<? extends Number> values) {
    double total = 0.0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

You can pass List\<Integer>, List\<Double>, or List\<Number>. When reading, each element can be used as a Number. You cannot add an arbitrary Integer because the actual list might be a List\<Double>.

### Lower bound: Consumer Super

~~~java
static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
~~~

You can pass List\<Integer>, List\<Number>, or List\<Object>. Adding an Integer is safe; when reading, the safest common type is Object because the actual list may contain other types.

**PECS** is a mnemonic: Producer Extends for a source providing data; Consumer Super for a destination receiving data. This is a design guideline, not a mandatory rule for every signature.

## 3. Complete example

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericVarianceDemo {
    static double sum(List<? extends Number> values) {
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    static void addIntegers(List<? super Integer> destination, int... values) {
        for (int value : values) {
            destination.add(value);
        }
    }

    static <T> void copyAll(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    static void printAll(List<?> values) {
        for (Object value : values) {
            System.out.println(value);
        }
    }

    static <T> void swap(List<T> values, int left, int right) {
        T temporary = values.get(left);
        values.set(left, values.get(right));
        values.set(right, temporary);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        System.out.println(sum(integers));

        List<Number> numbers = new ArrayList<>();
        numbers.add(1.5);
        addIntegers(numbers, 7, 8);
        System.out.println(numbers);

        copyAll(numbers, integers);
        System.out.println(numbers);

        swap(integers, 0, 2);
        printAll(integers);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac GenericVarianceDemo.java
java GenericVarianceDemo
~~~

Output:

~~~text
6.0
[1.5, 7, 8]
[1.5, 7, 8, 1, 2, 3]
3
2
1
~~~

**copyAll** uses T to link the source type with the destination type, while using wildcards to allow the source to produce T and the destination to consume T. **swap** uses List\<T> because it must read and write back the same element type.

## 4. When to use T instead of a wildcard?

~~~java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}

static Object firstUnknown(List<?> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
~~~

For List\<String>, the first method returns String; the second method only returns Object. Use a named T when you need to preserve a type relationship between parameters, multiple positions, or the result. Use List<?> when you do not need to know the element type.

A wildcard does not change the subtype relationship between concrete generic types. It only allows a variable or parameter with a wildcard to accept matching type arguments. Type erasure, raw types, and unchecked casts are related topics, but they have their own rules.

## 5. Common mistakes

- Assigning List\<Child> to List\<Parent> just because Child extends Parent.
- Using ? extends T and then trying to add an arbitrary T value.
- Using ? super T and then assuming the element read out is T instead of Object.
- Adding wildcards to every signature even when List\<T> already expresses the right read/write relationship.
- Forgetting that wildcards do not guarantee a collection is mutable; an immutable list can still throw UnsupportedOperationException.

Design signatures based on actual operations. For a read source, consider ? extends T; for a write destination, consider ? super T; when you need to read and write the same known type, List\<T> is usually clearer.
