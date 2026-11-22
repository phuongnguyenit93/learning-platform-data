# Generic invariance: `List<Integer>` and `List<Number>`

`Integer` is a subtype of `Number`, so an `Integer` value can be used wherever a `Number` is expected. However, it does not follow that `List<Integer>` is a subtype of `List<Number>`.

This is the **invariance in type relationships (invariance)** of generic type parameters. The term "invariance" here does not refer to whether elements can be added to or removed from the list. An `ArrayList<Integer>` can still have its contents modified; what is restricted is the assignment relationship between list types with different type arguments.

This article explains the rule through practical needs: reading numbers from various kinds of lists, adding integers into a destination, or creating a new list of numbers from a list of integers. The examples use Java 17 or later.

## 1. Two levels of types must be considered separately

### 1.1. Relationship between element types

The following snippet is valid:

```java
Integer integer = 7;
Number number = integer;
```

An `Integer` is a `Number`. Through the `number` reference, we can invoke methods declared by `Number`, such as `doubleValue()`.

`Double` is also a subtype of `Number`. Therefore, a location that accepts `Number` can hold either an `Integer` or a `Double`.

### 1.2. Relationship between list types

The following snippet **does not compile**:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // Type error.
```

`List<Integer>` and `List<Number>` are two distinct parameterized types. The `Integer`–`Number` relationship is not automatically lifted into the same relationship between the two lists.

In Java, a generic type such as `List<E>` is not declared covariant in `E`. Wildcards are the tool for expressing an appropriate relationship at the use site when we truly need to accept multiple list types. [Oracle: generics, inheritance, and subtypes](https://docs.oracle.com/javase/tutorial/java/generics/inheritance.html)

### Quick comparison table

| Assignment | Valid? | Reason |
| --- | --- | --- |
| `Integer` to `Number` | Yes | Ordinary subtype relationship |
| `ArrayList<Integer>` to `List<Integer>` | Yes | `ArrayList<E>` implements `List<E>` |
| `List<Integer>` to `Collection<Integer>` | Yes | `List<E>` extends `Collection<E>` |
| `List<Integer>` to `List<Number>` | No | Changing the generic type argument does not automatically create a subtype relationship |
| `List<Integer>` to `List<Object>` | No | Same reason, even though `Integer` is an `Object` |
| `List<Integer>` to `List<? extends Number>` | Yes | A wildcard allows an unknown element type that is `Number` or a subtype |

The key point is to distinguish changing the **container type along an inheritance hierarchy** from changing the **element type argument**.

## 2. Why must Java reject assigning `List<Integer>` to `List<Number>`?

Suppose Java allowed that assignment:

```java
// Hypothetical code to illustrate the hazard; Java does not allow the second assignment line.
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers;

numbers.add(3.5);
Integer first = integers.get(0);
```

Both `integers` and `numbers` would point to the same list. Through the type `List<Number>`, the call `add(3.5)` is valid because `3.5` is boxed into a `Double`, a subtype of `Number`.

However, the original reference still has the type `List<Integer>`. When reading from it, the caller expects the element to be an `Integer`, whereas the data just inserted is a `Double`. The type guarantee of the list has been broken.

Java blocks the assignment right away so that this dangerous write path cannot be created.

The argument does not depend on whether the list is currently empty or contains only integers. `List<Number>` is a contract that allows working with elements of type `Number`; it does not merely mean "a list that we intend to read as numbers".

### Why is the reverse direction also invalid?

```java
List<Number> numbers = new ArrayList<>();
numbers.add(3.5);

// Does not compile:
List<Integer> integers = numbers;
```

A `List<Number>` may contain `Double`, `Long`, or other `Number` types. There is no guarantee that every element is an `Integer`.

Therefore, `List<Integer>` is not a subtype of `List<Number>`, and `List<Number>` is not a subtype of `List<Integer>` either. [Java Language Specification 17: subtyping among reference types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2)

## 3. Invariance is not immutability

The two concepts answer two different questions:

| Concept | Question |
| --- | --- |
| Invariance | Can types like `List<Integer>` and `List<Number>` be assigned interchangeably? |
| Unmodifiable / data immutability | Can the list object or the state of its elements be changed? |

For example:

```java
List<Integer> editable = new ArrayList<>();
editable.add(1);
editable.add(2);
editable.remove(Integer.valueOf(1));
```

This list is modifiable, yet `List<Integer>` still cannot be assigned to `List<Number>`.

Conversely:

```java
List<Integer> fixed = List.of(1, 2, 3);

// Still does not compile:
List<Number> numbers = fixed;
```

Even though the object created by `List.of` does not allow modification, the type relationship rule still applies. The compiler does not alter the relationship between `List<Integer>` and `List<Number>` just because it knows the current way the list was created does not support `add`.

It is also unrelated to the `final` keyword:

```java
final List<Integer> values = new ArrayList<>();
values.add(1); // Valid.
```

`final` prevents reassigning the variable `values`; it does not convert generic types and does not automatically freeze the list's contents.

## 4. Only need to read numbers: use `List<? extends Number>`

If a method only needs to retrieve elements as `Number`, requiring `List<Number>` is usually too restrictive.

A more suitable signature:

```java
static double sum(List<? extends Number> source) {
    double result = 0;
    for (Number value : source) {
        result += value.doubleValue();
    }
    return result;
}
```

This is an illustrative method that should be placed inside a class with `List` imported. It assumes the elements are non-`null`.

The method accepts:

```java
sum(List.of(1, 2, 3));
sum(List.of(1.5, 2.5));
sum(List.<Number>of(1, 2.5));
```

`List<? extends Number>` can be understood as:

> A list whose specific element type is unknown; that type is `Number` or a subtype of `Number`.

We do not know whether the actual list is `List<Integer>`, `List<Double>`, or `List<Number>`, but when reading an element, we can safely view it as a `Number`. [Oracle: upper-bounded wildcard](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

### 4.1. Why can't an Integer be added?

```java
List<? extends Number> source = new ArrayList<Double>();

// Does not compile:
source.add(1);
```

The value 1 is an `Integer`. However, the object assigned to `source` in this example is a list of `Double`. Adding an `Integer` would violate the rules of the actual list.

Similarly, you cannot add an arbitrary `Double`, because `source` might be pointing to a `List<Integer>`.

The rule does not change even in this case:

```java
List<? extends Number> source =
        new ArrayList<Integer>();

// Still does not compile:
source.add(1);
```

When accessed through the variable `source`, the element type is treated as an unknown type bounded by `Number`. The compiler does not allow external assumptions to bypass that restriction.

### 4.2. Extends does not create a read-only list

`List<? extends Number>` restricts write operations that depend on knowing the element type; it does not create a new wrapper and does not automatically forbid every modification.

For example:

```java
List<Integer> original =
        new ArrayList<>(List.of(8, 9));

List<? extends Number> reference = original;
reference.clear();

System.out.println(original); // []
```

`clear()` does not insert a value of unknown type into the list. It is permitted from a type-checking standpoint; whether it succeeds depends on the mutability of the underlying object.

Additionally, `null` can be passed from a type-checking perspective to `add` on this wildcard, though the concrete class may reject `null` or not support additions. Do not use this as a way to work around the rule or as a basis for data design.

If you truly need to prevent modification through a reference, use an API with an appropriate unmodifiable contract. Wildcards only govern which operations are expressible in terms of types. [Oracle: guidelines for wildcard use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

## 5. Need to add Integers: use `List<? super Integer>`

Suppose a method needs to put integers into a receiving list. `List<? super Integer>` expresses:

> A list whose specific element type is `Integer` or a supertype of `Integer`.

For example:

```java
static void appendIntegers(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

You can pass:

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendIntegers(integers);
appendIntegers(numbers);
appendIntegers(objects);
```

All three list types can accept `Integer` without violating their element types. `List<Double>` is not eligible. [Oracle: lower-bounded wildcard](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

### 5.1. Reading back only guarantees Object

```java
List<Object> objects = new ArrayList<>();
objects.add("label");

List<? super Integer> target = objects;
target.add(10);

Object first = target.get(0);
```

`target` might be pointing to a `List<Object>` that already contains strings. Therefore, we cannot conclude that `get(0)` is always an `Integer` or even always a `Number`.

The following snippet does not compile:

```java
Integer first = target.get(0);
```

If your logic requires reading with a stronger type, design an appropriate method signature rather than adding a cast just to silence the error.

### 5.2. Not every Number can be added

```java
List<? super Integer> target = new ArrayList<Integer>();

// Does not compile:
target.add(2.5);
```

The `super Integer` wildcard guarantees that `Integer` is accepted, not that every `Number` is accepted. A `Double` is not an `Integer`.

You can remember this by the data role: a source that provides numbers to be read uses `extends`; a destination that receives integers being added uses `super`. This rule is commonly called PECS: Producer Extends, Consumer Super. Clearly identify which type is being produced or consumed rather than applying the slogan mechanically based on variable names.

## 6. When you truly need `List<Number>`, create a new structure

There are cases where an application needs a list capable of holding multiple kinds of `Number`, starting from integer data.

The safe approach:

```java
List<Integer> integers =
        new ArrayList<>(List.of(1, 2, 3));

List<Number> numbers = new ArrayList<>(integers);
numbers.add(4.5);

System.out.println(integers); // [1, 2, 3]
System.out.println(numbers);  // [1, 2, 3, 4.5]
```

There is no type conversion of an entire `List<Integer>` object into a `List<Number>` here. The program creates **a new list object** with element type `Number`, and then populates it with the valid `Integer` elements.

The constructor accepts a source of type `Collection<? extends E>`, so when `E` is `Number`, a `Collection<Integer>` source is accepted. [Java 17: ArrayList(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection))

If you already have a destination list:

```java
List<Number> destination = new ArrayList<>();
destination.addAll(integers);
```

This likewise copies elements into a compatible structure, rather than assigning two variables to point to the same list under conflicting element guarantees.

### Structural copying is not deep copying

The new list holds element references taken from the source. With immutable `Integer` objects, this is usually straightforward to reason about. With mutable objects, the two lists may still reference the same element instances.

Copying the list resolves adding or removing elements across two independent structures; it does not automatically clone the entire object graph.

## 7. `List<?>` is different from `List<Object>`

These two types are very easy to confuse:

| Type | Meaning | Can an arbitrary string be added from a type-checking standpoint? |
| --- | --- | --- |
| `List<Object>` | A list whose element type is `Object` | Yes |
| `List<?>` | A list whose specific element type is unknown | No |
| `List<? extends Number>` | Unknown element type within the `Number` hierarchy | No |
| `List<? super Integer>` | Element type is `Integer` or a compatible supertype | No; only guaranteed to accept `Integer` |

The last column refers to compile-time type checking. The actual list instance at runtime might still not support `add`.

A function that only wants to print arbitrary elements can accept:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

The function accepts both `List<Integer>` and `List<String>` without requiring them to be turned into `List<Object>`.

Therefore, if the compiler refuses to pass `List<Integer>` into a method expecting `List<Object>`, ask whether the method actually needs to add arbitrary `Object` instances. If it only reads elements as `Object`, `List<?>` may be the right contract. [Oracle: wildcards and subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html)

## 8. Type inference does not change the invariance rule

This snippet is valid:

```java
List<Number> numbers = List.of(1, 2);
```

It does not prove that `List<Integer>` is assignable to `List<Number>`. `List.of` is a generic method; the target type participates in type argument inference. In the context above, the compiler can choose the element type `Number` right at the factory call.

The intent can be written more explicitly:

```java
List<Number> numbers = List.<Number>of(1, 2);
```

Meanwhile:

```java
List<Integer> integers = List.of(1, 2);

// Does not compile:
List<Number> numbers = integers;
```

Here the source variable already has the type `List<Integer>`; there is no longer a factory call being inferred against a target type to alter the meaning.

Similarly, `var` does not make the type flexible:

```java
var integers = List.of(1, 2);

// Does not compile:
List<Number> numbers = integers;
```

The type of the `integers` variable is inferred at declaration time. `var` does not mean "a variable that accepts a list with any element type".

Separate note: lists returned by `List.of` are unmodifiable. The mutability of the factory result and the rules of generic type inference are two independent matters.

## 9. Why do arrays allow Number[] = Integer[]?

Java allows:

```java
Number[] numbers = new Integer[]{1, 2};
```

Reference arrays are covariant. However, the array object at runtime still knows that its actual component type is `Integer`.

Therefore:

```java
numbers[0] = 3.5; // Compiles, but throws ArrayStoreException.
```

The assignment is viewed through the type `Number[]`, but at runtime the array rejects storing a `Double` into storage allocated for `Integer`. [Java Language Specification 17: array store check](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5)

Comparison:

| Construct | Upcast under consideration | How invalid writes are prevented |
| --- | --- | --- |
| Array | `Integer[]` to `Number[]` is allowed | Runtime check on array component type |
| Generic List | `List<Integer>` to `List<Number>` is not allowed | Assignment relationship rejected at compile time |

Do not extrapolate generic rules from array rules. The two mechanisms are designed and checked differently.

## 10. Do not work around this with raw types or unchecked casts

A raw type such as `List` strips the type argument from generic checking. Casts through `List<?>` or raw types can make the compiler accept an assignment with an unchecked warning, but they do not create a new list and do not safely convert every element into a `Number` under a sound contract.

If an alias allows adding a `Double` into an object that another reference still holds as `List<Integer>`, the data suffers from heap pollution. The failure may only surface later when some code reads an element and casts it to `Integer`.

Do not use `@SuppressWarnings("unchecked")` as a default fix. It only silences the warning; it does not make an invalid assumption true.

Choose one of the appropriate approaches instead:

- Only need to read numbers: use a `? extends Number` parameter.
- Only need to add integers: use a `? super Integer` parameter.
- Need to preserve a single element type across multiple places: design a generic method with a type parameter.
- Need an independent `Number` list: copy the elements into a new structure.
- Do not need to know the element type: consider `List<?>`.

Generic types are checked at compile time; there is no automatic operation that "upgrades" an object just because a programmer writes a cast.

## 11. Complete runnable example on Java 17+

Save as `GenericInvarianceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericInvarianceDemo {
    private static double sum(List<? extends Number> source) {
        double result = 0;
        for (Number value : source) {
            result += value.doubleValue();
        }
        return result;
    }

    private static void appendIntegers(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        Integer integer = 7;
        Number number = integer;
        System.out.println("number = " + number);

        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<? extends Number> source = integers;
        Number first = source.get(0);
        System.out.println("first = " + first);
        System.out.println("integer sum = " + sum(integers));
        System.out.println("double sum = " + sum(List.of(1.5, 2.5)));

        List<Number> mixed = new ArrayList<>();
        mixed.add(2.5);
        List<? super Integer> sink = mixed;
        appendIntegers(sink);
        Object firstFromSink = sink.get(0);
        System.out.println("mixed = " + mixed);
        System.out.println("first sink value = " + firstFromSink);

        List<Number> copy = new ArrayList<>(integers);
        copy.add(4.5);
        System.out.println("original integers = " + integers);
        System.out.println("independent list structure = " + copy);

        List<Integer> removable = new ArrayList<>(List.of(8, 9));
        List<? extends Number> restricted = removable;
        restricted.clear();
        System.out.println("extends view after clear = " + removable);

        List<Number> targetTyped = List.of(1, 2);
        System.out.println("target-typed list = " + targetTyped);

        Number[] covariantArray = new Integer[]{1, 2};
        try {
            covariantArray[0] = 3.5;
        } catch (ArrayStoreException expected) {
            System.out.println("array rejects Double at runtime");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 GenericInvarianceDemo.java
java GenericInvarianceDemo
```

Stdout:

```text
number = 7
first = 1
integer sum = 6.0
double sum = 4.0
mixed = [2.5, 10, 20]
first sink value = 2.5
original integers = [1, 2, 3]
independent list structure = [1, 2, 3, 4.5]
extends view after clear = []
target-typed list = [1, 2]
array rejects Double at runtime
```

How to read the output:

1. An `Integer` value is used under the type `Number`.
2. A `? extends Number` source allows reading elements as `Number`, so the same summation function handles both lists of integers and lists of floating-point numbers.
3. A `? super Integer` destination accepts adding integers into a `Number` list that already holds a `Double`; when reading through the wildcard reference, the only guaranteed common type is `Object`.
4. The `List<Number>` copy can have `4.5` added without modifying the structure of the original integer list.
5. A `? extends Number` reference can still call `clear` on an object that supports modification, proving that a wildcard does not make data immutable.
6. The target type participates in type inference at the `List.of` call.
7. A covariant array allows the reference assignment but blocks an element of the wrong type with a runtime exception.

The `sum` function in the example only illustrates reading `Number` elements; it uses `double` and is not designed for financial calculations or exact precision across all numeric types.

## 12. Deliberate non-compiling test case

A type rule should be verified with both valid code and rejected code.

Save separately as `InvarianceMustFail.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InvarianceMustFail {
    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = integers;
    }
}
```

Run:

```shell
javac --release 17 -encoding UTF-8 InvarianceMustFail.java
```

**Expected:** compilation fails at the assignment from `List<Integer>` to `List<Number>`.

The message will report an incompatible types error; the exact wording or formatting may vary across compiler versions. Do not include this deliberately failing file in an application source set that must build cleanly.

If you change the assignment line to `List<? extends Number> numbers = integers;`, the declaration becomes valid. After that, try adding `numbers.add(3.5)` to see how the type system continues to block the unsafe write path.

## 13. Choose the signature according to the data role

| What the method needs to do | Type to consider first |
| --- | --- |
| Read elements as `Number` | `List<? extends Number>` |
| Add `Integer` elements into a destination | `List<? super Integer>` |
| Read and write a type `E` that must correlate with another parameter or return value | Generic type parameter `E` |
| Only iterate to display arbitrary values | `List<?>` |
| Add `Integer`, `Double`, and other `Number` subtypes | A genuine `List<Number>` |
| Convert integer data into an extensible list of numbers | Create a new `List<Number>` and copy the elements |

Do not use wildcards merely to make compiler errors go away. First determine what the callee will read, what it will write, and whether it needs to maintain a type relationship with another value. The signature should accurately describe that responsibility.

## 14. Common mistakes

| Misconception | Correction |
| --- | --- |
| `Integer` is a `Number`, so `List<Integer>` is a `List<Number>` | Element subtype relationships do not automatically carry over through generics |
| Invariance means the list cannot be modified | It is a rule about type relationships, distinct from data mutability |
| `? extends Number` accepts any `Number` for insertion | It allows reading as `Number`, not inserting arbitrary numbers |
| `? super Integer` always reads back as `Integer` | It could be a `List<Object>` containing other values; only `Object` is guaranteed |
| `List<?>` is synonymous with `List<Object>` | One has an unknown element type; the other has `Object` as its element type |
| If a list is unmodifiable, the type relationship can change | Assignment compatibility is still determined by static types |
| `new ArrayList<>(integers)` is just a cast | It creates a new structure and populates it with valid elements |
| An unchecked cast or suppressed warning converts the data | No; it only bypasses or silences part of the type check |
| `var` allows changing the element type later | The type is still fixed at declaration time |
| Arrays are covariant, so List must be too | Arrays and generics have different mechanisms |

## 15. Self-practice

1. Can a `List<Double>` be passed to a method that expects `List<Number>`?  
   **Answer:** no. If the method only reads elements as numbers, consider `List<? extends Number>`.

2. Why can't `1` be added to a `List<? extends Number>` variable?  
   **Answer:** the actual list might be a `List<Double>`; the specific element type is unknown.

3. Can a `List<Object>` be passed to a method that expects `List<? super Integer>`?  
   **Answer:** yes, because it can accept `Integer` elements. When reading through that wildcard, only `Object` is guaranteed.

4. If you want to start from a `List<Integer>` and later add a `Double` without affecting the original list, what should you do?  
   **Answer:** create `List<Number> copy = new ArrayList<>(integers)`, then add to the new copy.

5. Why is `List<Number> values = List.of(1, 2)` valid whereas assigning a `List<Integer>` variable to `List<Number>` is not?  
   **Answer:** the first case is type inference for a generic method call based on the target context; the second case is an assignment relationship between two already-determined types.

Generic invariance ensures that every list reference upholds its commitment regarding its element type. When you need flexibility, relax the contract appropriately according to the read or write role rather than sacrificing type checking.
