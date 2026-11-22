# UnaryOperator<T> and BinaryOperator<T> in Java

## 1. Two forms of operations that preserve the data type

In the **java.util.function** package, **UnaryOperator<T>** and **BinaryOperator<T>** represent functions whose output type matches their input type. They are specialized versions of **Function** and **BiFunction**, very useful when you need to describe **transforming one value** or **combining two values of the same type**.

- **UnaryOperator<T>**: takes **one T**, returns **one T**. You can read it as **T → T**. Examples: normalizing a string, updating immutable state, rounding a value.
- **BinaryOperator<T>**: takes **two T values**, returns **one T**. You can read it as **(T, T) → T**. Examples: adding two numbers, choosing the larger value, merging two configurations of the same type according to clear rules.

Both are **functional interfaces**, so you can create implementations with lambdas or method references. They do not require the operation to be mathematical; the name "operator" describes the **function shape**.

~~~text
UnaryOperator<T>:
      T ──────► [ operation ] ──────► T

BinaryOperator<T>:
      T ──┐
          ├──► [ operation ] ──────► T
      T ──┘
~~~

Example:

~~~java
UnaryOperator<String> trim = String::strip;
BinaryOperator<Integer> add = Integer::sum;
~~~

These are **illustrative snippets**, assuming imports of **java.util.function.UnaryOperator** and **java.util.function.BinaryOperator**. **trim.apply("  Java  ")** yields **"Java"**; **add.apply(4, 6)** yields **10**.

Note the distinction: having a result type equal to the parameter type **does not mean** the returned object must be the same instance. A UnaryOperator can return a new object, return the original object, or mutate a mutable object and return it. The Java signature does not automatically guarantee immutability, pure functions, or thread safety.

## 2. Relationship with Function and BiFunction

The core declarations of the two interfaces in Java can be understood as follows:

~~~java
@FunctionalInterface
public interface UnaryOperator<T> extends Function<T, T> {
    static <T> UnaryOperator<T> identity() { /* implementation */ }
}

@FunctionalInterface
public interface BinaryOperator<T> extends BiFunction<T, T, T> {
    static <T> BinaryOperator<T> minBy(Comparator<? super T> comparator)
        { /* implementation */ }

    static <T> BinaryOperator<T> maxBy(Comparator<? super T> comparator)
        { /* implementation */ }
}
~~~

The snippet above is an **API signature diagram** with method bodies and imports intentionally omitted; it is **not a standalone Java file to compile**. Both actual interfaces are provided by the JDK.

Comparison:

| Interface | Functional signature | SAM method | When to use |
| --- | --- | --- | --- |
| **Function<T,R>** | T → R | **R apply(T)** | May change type during transformation |
| **UnaryOperator<T>** | T → T | **T apply(T)** | Transforms while keeping the same type |
| **BiFunction<T,U,R>** | (T,U) → R | **R apply(T,U)** | Two parameters may have different types |
| **BinaryOperator<T>** | (T,T) → T | **T apply(T,T)** | Combines two values of the same type |

**UnaryOperator<T> extends Function<T,T>** means a UnaryOperator can still be used wherever **Function<T,T>** is expected. Similarly, **BinaryOperator<T> extends BiFunction<T,T,T>**. Both use the **apply** method name inherited from their parent interface.

**There is no automatic reverse conversion** from a **Function<T,T>** variable to UnaryOperator or from **BiFunction<T,T,T>** to BinaryOperator. Even though they have the same shape, they are still distinct interface types; to obtain a UnaryOperator, you need a lambda/method reference with the corresponding **target type** or a proper adapter.

For example:

~~~java
Function<String, String> transform = String::strip;
UnaryOperator<String> operator = transform::apply;
~~~

This illustrative snippet is valid when both interfaces are imported. Assigning **UnaryOperator<String> operator = transform;** directly does not compile, because the variable **transform** has static type **Function<String,String>**, which is not necessarily a UnaryOperator.

## 3. UnaryOperator<T>: transforming a value while keeping its type

**UnaryOperator<T>** fits well when a value passes through multiple normalization steps. For example, an input item code may need whitespace stripped, uppercasing, and then a prefix attached.

Usage with a lambda:

~~~java
UnaryOperator<String> normalize =
        value -> value.strip().toUpperCase(Locale.ROOT);
~~~

This snippet is placed inside a method with **java.util.Locale** and **java.util.function.UnaryOperator** imported. It returns a normalized String; String is immutable, so the source data is not modified in place.

**Method references** keep things concise when the transformation is already encapsulated in a matching method:

~~~java
UnaryOperator<String> removeEdgeSpace = String::strip;
UnaryOperator<String> unchanged = UnaryOperator.identity();
~~~

**identity()** creates the identity operator: **identity.apply(x)** returns **x** (the same reference if x is an object). It is useful as a default value for an optional transformation step or a neutral element in function composition, but it **does not copy the object**.

### 3.1. Composing with compose() and andThen()

Because UnaryOperator extends **Function<T,T>**, it can use **compose** and **andThen**:

- **f.andThen(g)** means apply **f first**, then **g**: **g(f(x))**.
- **f.compose(g)** means apply **g first**, then **f**: **f(g(x))**.

**Note on return type:** the inherited signatures of **Function.andThen** and **Function.compose** return **Function**. Therefore, even when both operators share type T, you cannot directly assign the result of **f.andThen(g)** to a **UnaryOperator<T>** variable.

~~~java
UnaryOperator<String> strip = String::strip;
UnaryOperator<String> upper =
        s -> s.toUpperCase(Locale.ROOT);

Function<String, String> pipeline = strip.andThen(upper);
// If you genuinely need a variable of type UnaryOperator<String>:
UnaryOperator<String> chained =
        s -> upper.apply(strip.apply(s));
~~~

This is an illustrative snippet in a context with **Function**, **UnaryOperator**, and **Locale** imported. Given input **"  java  "**, both **pipeline** and **chained** return **"JAVA"**.

Distinguishing **Function<T,T>** from **UnaryOperator<T>** here is a matter of **static type contract**, not a difference in runtime output. You should also consider transformation order: **strip → upper** can differ from **upper → strip** in real pipelines with interdependent rules.

## 4. BinaryOperator<T>: combining two values of the same type

**BinaryOperator<T>** is usable when an operation takes two values **of the same type T** and produces a result that is also **T**.

~~~java
BinaryOperator<Integer> sum = Integer::sum;
BinaryOperator<String> join = (left, right) -> left + "-" + right;
BinaryOperator<Integer> larger = Integer::max;
~~~

These illustrative snippets require importing **java.util.function.BinaryOperator**. Their usage:

~~~text
sum.apply(7, 5)      → 12
join.apply("A", "B") → "A-B"
larger.apply(7, 5)  → 7
~~~

**BinaryOperator<T> does not require the operation to be commutative or associative.** With **Integer::sum**, integer addition is mathematically commutative and associative, though **int** still has overflow behavior. With **(a,b) -> a-b**, parameter order matters greatly; subtraction is not associative. With **String** concatenation, order also matters even though concatenation is associative with respect to String content.

If you need to combine **two different types** or return a **different type**, using **BiFunction<T,U,R>** is more appropriate. For example, combining an **Order** and a tax rate to produce an **Invoice** is not a BinaryOperator<Order>, because the output is not an Order.

### 4.1. minBy() and maxBy()

**BinaryOperator.minBy(comparator)** returns an operator that selects the smaller value according to the Comparator; **maxBy** selects the larger value.

~~~java
BinaryOperator<Integer> min =
        BinaryOperator.minBy(Comparator.naturalOrder());
BinaryOperator<Integer> max =
        BinaryOperator.maxBy(Comparator.naturalOrder());
~~~

This is an illustrative snippet with **java.util.Comparator** and **java.util.function.BinaryOperator** imported. **min.apply(8, 3)** yields **3**, and **max.apply(8, 3)** yields **8**.

For types with multiple attributes, a Comparator helps clearly define the selection criterion; for instance, selecting the most expensive product or the latest order. If two elements compare equal according to the Comparator yet are distinct objects, the "min/max by Comparator" contract does not mean the objects are business-equivalent. If tie-breaking matters, include it in the Comparator.

If the Comparator is inconsistent, changes over time, or is affected by shared state, the min/max selection result may be unstable.

## 5. Complete Java 17 program: UnaryOperator and BinaryOperator

Create the file **OperatorBasics.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.function.UnaryOperator;

public class OperatorBasics {
    public static void main(String[] args) {
        UnaryOperator<String> normalize =
                s -> s.strip().toLowerCase(Locale.ROOT);

        UnaryOperator<String> addPrefix =
                s -> "item:" + s;

        Function<String, String> normalizeAndPrefix =
                normalize.andThen(addPrefix);

        UnaryOperator<String> unchanged =
                UnaryOperator.identity();

        BinaryOperator<Integer> total = Integer::sum;
        BinaryOperator<Integer> greatest =
                BinaryOperator.maxBy(Comparator.naturalOrder());

        List<Integer> numbers = List.of(3, 6, 9);

        System.out.println(normalize.apply("  JAVA  "));
        System.out.println(normalizeAndPrefix.apply("  JAVA  "));
        System.out.println(unchanged.apply("hello"));
        System.out.println(total.apply(7, 5));
        System.out.println(greatest.apply(7, 5));
        System.out.println(numbers.stream().reduce(0, total));
        System.out.println(numbers.stream()
                .reduce(greatest)
                .orElse(-1));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 OperatorBasics.java
java OperatorBasics
~~~

Stdout:

~~~text
java
item:java
hello
12
7
18
9
~~~

Explanation:

1. **normalize** takes a String and returns a String with leading/trailing whitespace stripped and converted to lowercase using **Locale.ROOT** to avoid depending on the environment's default locale.
2. **normalize.andThen(addPrefix)** creates a **Function<String,String>**; the input **"  JAVA  "** goes through **normalize** first and then receives the prefix **"item:"**.
3. **UnaryOperator.identity()** does not alter the input content.
4. **total** and **greatest** both take two Integers and return one Integer; BinaryOperator expresses two different behaviors with the same signature.
5. **reduce(0, total)** sums starting from initial value **0** across the three elements: **3 + 6 + 9 = 18**.
6. **reduce(greatest)** returns **Optional<Integer>** because the stream could be empty; with this data the maximum is **9**, and **orElse(-1)** is just the example's fallback.

The operations above use Integer, so there is **boxing/unboxing** when running through object APIs. At large processing scale or in performance-sensitive tasks, consider primitive streams and primitive operators.

## 6. Why does BinaryOperator often appear with Stream.reduce()?

**Stream.reduce** folds multiple elements into one value by repeatedly applying a combining operation. The signatures of two common overloads are:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator);
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

These are **simplified API signatures for explanation**, not standalone code. Other overloads of reduce include a three-parameter form for folding into a result type different from the element type.

### 6.1. reduce(operator): without an identity

~~~java
Optional<Integer> maybeTotal =
        List.of(2, 4, 6).stream().reduce(Integer::sum);
~~~

If the stream has elements, Java combines them and returns an **Optional** containing the result. If the stream is empty, the result is **Optional.empty()**. Do not assume that "the sum of an empty stream must be 0" when calling the overload **without an identity**. This is an **illustrative snippet** requiring imports of **List** and **Optional**.

### 6.2. reduce(identity, operator): with a neutral value

~~~java
int total = List.of(2, 4, 6).stream()
        .reduce(0, Integer::sum);
~~~

Here **0** is the identity for addition: for all x, **0 + x = x** and **x + 0 = x**. For an empty stream, this overload returns **0**.

Using the wrong identity value produces the wrong result. For example, to find the maximum from a list containing negative numbers, **reduce(0, Integer::max)** is wrong if all elements are negative: **0** is introduced as a candidate not present in the data. You can use **reduce(Integer.MIN_VALUE, Integer::max)** for int when context permits, or **reduce(Integer::max)** to preserve "possibly no elements" semantics via Optional.

### 6.3. Associativity and parallel processing

In Stream reductions, the accumulator must be **associative**: parenthesization must not change the result.

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

For example, **Integer::sum** is associative under int modular arithmetic, even though the result can overflow compared to mathematical integer addition. **Integer::max** is associative. Conversely, **(a,b) -> a-b** is not associative:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

If you use subtraction as an accumulator, the result can depend on how operations are grouped, especially in a **parallel stream**. Do not use a non-associative operation with reduce and assume parallel execution always gives the same result as a sequential loop.

For **double**, even addition can yield slightly different final numbers if grouping changes, due to floating-point rounding error. If the problem requires exact precision or a deterministic summation order, design accordingly rather than assuming parallel execution is bit-for-bit identical.

A BinaryOperator used for reduce should **have no side effects, not mutate shared mutable state**, and in parallel pipelines must satisfy the associativity contract along with a true identity. If the result is computed by mutating an accumulator object, revisit using a collector or an appropriate loop.

## 7. Practical program: computing order amount with BigDecimal

Problem statement: each cart line has a **unit price in the smallest currency unit** and a quantity. Sum the lines, apply a **10%** discount, and then add a **fixed delivery fee of 15,000**.

Here:
- A **BinaryOperator<BigDecimal>** handles **adding two amounts** of the same type.
- **UnaryOperator<BigDecimal>** instances handle **applying the discount** and **adding the fee** from one amount to a new amount.
- We do not need a separate custom interface for each simple transformation if the meaning is already clear from variable/method names.

Create the file **OrderAmountDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.UnaryOperator;

record CartLine(String sku, long unitPrice, int quantity) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must be non-negative");
        }
    }

    long subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

public class OrderAmountDemo {
    public static void main(String[] args) {
        List<CartLine> lines = List.of(
                new CartLine("BOOK", 50_000L, 2),
                new CartLine("PEN", 40_000L, 1)
        );

        BinaryOperator<BigDecimal> add = BigDecimal::add;

        UnaryOperator<BigDecimal> discount10 =
                amount -> amount.multiply(new BigDecimal("0.90"));
        UnaryOperator<BigDecimal> deliveryFee =
                amount -> amount.add(new BigDecimal("15000"));

        BigDecimal subtotal = lines.stream()
                .map(line -> BigDecimal.valueOf(line.subtotal()))
                .reduce(BigDecimal.ZERO, add);

        BigDecimal afterDiscount = discount10.apply(subtotal);
        BigDecimal finalAmount = deliveryFee.apply(afterDiscount);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Discounted: " + afterDiscount);
        System.out.println("Payable: " + finalAmount);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OrderAmountDemo.java
java OrderAmountDemo
~~~

Stdout:

~~~text
Subtotal: 140000
Discounted: 126000.00
Payable: 141000.00
~~~

Arithmetic explanation:

- **BOOK** line: **50,000 × 2 = 100,000**.
- **PEN** line: **40,000 × 1 = 40,000**.
- **subtotal = 140,000**; a 10% discount by multiplying by **0.90** gives **126,000.00**; adding **15,000** gives **141,000.00**.
- **BigDecimal** preserves exact decimal values for the specified calculations. **new BigDecimal("0.90")** keeps scale 2, so multiplication and addition show **.00** when printed with **toString()**.

This is a **learning example** and does not yet model tax rules, voucher caps, specific currencies, or rounding rules when division occurs. In a payment system, you must formally define **currency unit, rounding policy, and the order of discounts and fees**. **Math.multiplyExact** catches overflow when multiplying unit price by quantity before converting to BigDecimal; if a numeric range larger than long is needed, storage design must change.

**Key point on types:** **discount10** is UnaryOperator<BigDecimal> because both input and output are BigDecimal; **add** is BinaryOperator<BigDecimal> because two amounts of the same type are combined into one amount of the same type.

## 8. Primitive specialization: avoiding boxing when appropriate

**UnaryOperator<Integer>** and **BinaryOperator<Integer>** work with the reference type **Integer**. When processing many primitive **int** values, Java provides specialized versions:

| Specialized type | SAM method | Meaning |
| --- | --- | --- |
| **IntUnaryOperator** | **int applyAsInt(int)** | int → int |
| **LongUnaryOperator** | **long applyAsLong(long)** | long → long |
| **DoubleUnaryOperator** | **double applyAsDouble(double)** | double → double |
| **IntBinaryOperator** | **int applyAsInt(int,int)** | (int,int) → int |
| **LongBinaryOperator** | **long applyAsLong(long,long)** | (long,long) → long |
| **DoubleBinaryOperator** | **double applyAsDouble(double,double)** | (double,double) → double |

Example inside a method with **java.util.function.IntUnaryOperator** and **java.util.function.IntBinaryOperator** imported:

~~~java
IntUnaryOperator twice = x -> x * 2;
IntBinaryOperator sum = Integer::sum;

System.out.println(twice.applyAsInt(6));  // 12
System.out.println(sum.applyAsInt(6, 7)); // 13
~~~

This is an illustrative snippet, not a standalone program. With **IntStream**, you can directly use **IntUnaryOperator** in **map** and **IntBinaryOperator** in **reduce**:

~~~java
int total = IntStream.of(1, 2, 3)
        .map(x -> x * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 12
~~~

This illustrative snippet requires importing **java.util.stream.IntStream**. Using primitive streams reduces boxing in primitive data processing; however, actual performance still depends on the algorithm, JVM, data, and workload. Do not switch to primitive interfaces when business logic needs **BigDecimal** or a structured object to accurately model the domain.

## 9. Common confusions when combining operators

### 9.1. Do not use UnaryOperator when the type changes

~~~java
Function<String, Integer> length = String::length;
~~~

This illustrative snippet requires importing **Function**. This operation is **String → Integer**, so it is not a UnaryOperator<String>. Likewise, converting **String → BigDecimal** requires Function<String,BigDecimal> or a dedicated domain type.

### 9.2. Do not use BinaryOperator when the two inputs have different types

~~~java
BiFunction<String, Integer, String> repeat =
        String::repeat;
~~~

This illustrative snippet requires importing **BiFunction**; **String.repeat(int)** matches **(String,Integer) → String** via unboxing Integer to int. Because the two inputs do not share the same type, BinaryOperator<String> is not suitable.

### 9.3. Do not equate "same type" with "same object"

~~~java
UnaryOperator<StringBuilder> appendBang = b -> b.append("!");
~~~

This is an illustrative snippet requiring importing **UnaryOperator**. It mutates the passed-in **StringBuilder** object; the function is not pure and can cause side effects if the object is shared. If you want an immutable transformation, choose an appropriate data type and create a new value.

### 9.4. Do not use operators with null without a policy

**String::strip**, **Integer::sum**, and **BigDecimal::add** all have cases that reject null; a null can throw **NullPointerException**. The type **UnaryOperator<String>** does not by itself express whether the input may be null.

For pipelines processing external data, decide whether null must be filtered out, replaced with a default, or reported as an error. For example, **Stream.filter(Objects::nonNull)** can strip nulls before applying an operation, but only when business policy permits dropping that data.

### 9.5. Do not assume every BinaryOperator works well with reduce

An operator can be completely valid when called directly yet unsuitable for parallel reduction. To use reduce reliably, check associativity, identity, side effects, and data types. For example, subtraction is a valid BinaryOperator<Integer> but is **not associative**.

### 9.6. Do not assume Function.andThen returns a UnaryOperator

This is a common static-typing trap. Even when both operations are UnaryOperator<T>, **andThen** inherited from **Function** returns **Function<T,T>**. If you specifically need a UnaryOperator<T>, wrap it in a lambda:

~~~java
UnaryOperator<String> first = String::strip;
UnaryOperator<String> second = String::toUpperCase;

UnaryOperator<String> combined =
        value -> second.apply(first.apply(value));
~~~

This is an illustrative snippet with **UnaryOperator** imported. If uppercasing needs to be locale-independent, use a lambda calling **toUpperCase(Locale.ROOT)** as in the complete programs above.

## 10. When to choose an operator, Function, or a custom domain interface?

**Choose UnaryOperator<T>** when behavior takes one value and returns the same type, such as normalized strings, updated immutable state, or adjusted monetary amounts.

**Choose BinaryOperator<T>** when behavior combines two values of the same type into one value of the same type, such as addition, min/max, or merging two configurations by a defined policy. If used with reduce, verify the algebraic properties match.

**Choose Function<T,R>/BiFunction<T,U,R>** when input and output types differ. Using the general types expresses the exact contract without forcing everything into one data type.

**Create a custom functional interface** when the behavior has an important business name, needs domain-specific documentation/exceptions/rules, and serves as an API contract. A **UnaryOperator<T>** inside a local helper is fine for normalization; however, a public contract like **ExchangeRatePolicy.convert(amount)** may deserve a dedicated type if semantics, currency, rate source, and errors must be explicitly defined.

There is no single "always best" choice. Prioritize **the right signature, clear intent, and verifiable behavior**.

## 11. Practice exercises

1. Write a **UnaryOperator<String>** that normalizes a customer code: strip leading/trailing whitespace and convert to uppercase using Locale.ROOT; test with **"  ab-12  "**.
2. Write a **BinaryOperator<Integer>** that picks the smaller value, comparing the result of lambda **(a,b) -> Math.min(a,b)** with **BinaryOperator.minBy(Comparator.naturalOrder())**.
3. Create two UnaryOperator<String> instances **first** and **second**, and compose them with **andThen**. Check the result type by assigning it to **Function<String,String>**; explain why it cannot be assigned directly to **UnaryOperator<String>**.
4. Given the list **[-7, -3, -10]**, compare **reduce(0, Integer::max)** and **reduce(Integer::max)**. Explain why the first result can misrepresent "the max of the data".
5. Write a **BinaryOperator<Integer>** for subtraction, then check **(10 - 3) - 2** versus **10 - (3 - 2)**. Derive the condition that must be checked before using an operator in parallel reduction.
6. Convert a calculation using **UnaryOperator<Integer>** on **Stream<Integer>** to **IntUnaryOperator** and **IntStream**; distinguish the goal of reducing boxing from business correctness.
7. Extend the amount problem with explicit rounding and tax policies; evaluate whether a chain of UnaryOperator<BigDecimal> still expresses the contract well enough or needs a dedicated domain type.

## 12. Key takeaways

**UnaryOperator<T>** is **Function<T,T>** with the intent "one value in, one value of the same type out". **BinaryOperator<T>** is **BiFunction<T,T,T>** with the intent "two values of the same type in, one value of the same type out". Both use lambdas, method references, and the **apply** method.

The most important practical points are **choosing the right type for the contract**, distinguishing function composition from value combination, understanding **identity/associativity** when applying BinaryOperator to **Stream.reduce**, and controlling nulls, side effects, overflow, and performance limits. When processing large volumes of primitives, consider **Int/Long/DoubleUnaryOperator** and **Int/Long/DoubleBinaryOperator**.
