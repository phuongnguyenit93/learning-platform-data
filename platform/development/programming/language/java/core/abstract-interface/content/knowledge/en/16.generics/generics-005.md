# Multiple Type Bounds and Intersection Types in Java Generics

## 1. Multiple bounds express the “all” condition

An algorithm may require an object to satisfy multiple contracts at the same time: having an ID, a name, and a measurable value. Java allows declaring multiple bounds for the same type parameter using the **&** symbol:

~~~java
<T extends Number>
<T extends Comparable<T>>
<T extends Number & Comparable<T> & java.io.Serializable>
~~~

A valid type must satisfy every bound. If there is a class bound, it must appear first, and there can be at most one class bound; subsequent bounds are interfaces. When there is no class bound, multiple interfaces can be listed.

## 2. Complete example

~~~java
interface Named {
    String name();
}

interface Measurable {
    double measure();
}

abstract class RecordBase {
    private final String id;

    protected RecordBase(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}

final class MetricRecord extends RecordBase
        implements Named, Measurable, Comparable<MetricRecord> {
    private final String name;
    private final double score;

    MetricRecord(String id, String name, double score) {
        super(id);
        this.name = name;
        this.score = score;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public double measure() {
        return score;
    }

    @Override
    public int compareTo(MetricRecord other) {
        return Double.compare(score, other.score);
    }
}

public class IntersectionTypeDemo {
    static <T extends RecordBase & Named & Measurable>
    String describe(T item) {
        return item.id() + ": " + item.name()
                + " (" + item.measure() + ")";
    }

    static <T extends RecordBase & Named & Measurable & Comparable<T>>
    T chooseLarger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        MetricRecord alpha = new MetricRecord("alpha", "Alpha", 7.0);
        MetricRecord beta = new MetricRecord("beta", "Beta", 12.0);

        System.out.println(describe(alpha));
        System.out.println("winner=" + chooseLarger(alpha, beta).name());

        Object unknown = alpha;
        System.out.println("intersection="
                + ((Named & Measurable) unknown).name()
                + "/" + ((Named & Measurable) unknown).measure());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac IntersectionTypeDemo.java
java IntersectionTypeDemo
~~~

Output:

~~~text
alpha: Alpha (7.0)
winner=Beta
intersection=Alpha/7.0
~~~

**describe** requires the base class RecordBase along with both interfaces; the compiler allows calling id(), name(), and measure() directly. **chooseLarger** adds Comparable\<T>, so it can compare two objects of the same type and return T. MetricRecord satisfies all bounds.

## 3. Bounds and intersection casts differ

A bound such as **T extends RecordBase & Named & Measurable** constrains the input type at compile time. If the type does not satisfy every bound, the call is rejected.

An intersection cast such as **(Named & Measurable) unknown** checks the actual object at runtime. If the object does not implement both interfaces, the cast can throw ClassCastException. Use a cast when you need to check a value with a broad static type; if an API always requires multiple capabilities, express them in the bound to detect errors earlier.

## 4. Common mistakes

- Placing an interface before the class bound, for example **\<T extends Named & RecordBase>** when RecordBase is a class.
- Declaring two class bounds for one type parameter.
- Using a comma instead of &: a comma separates different type parameters, whereas & combines multiple bounds of the same parameter.
- Assuming that only one bound needs to be satisfied: **T extends Named & Measurable** requires both.
- Adding bounds that do not serve the actual operations of the algorithm, causing the API to exclude types that could be used.

Identify the methods the algorithm needs to call, map each method to the class/interface that provides the contract, and then declare the fewest bounds that are still sufficient.
