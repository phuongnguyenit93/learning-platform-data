# Distinguishing remove(int) from remove(Object)

## 1. One method name, two different removal intents

A `List` stores elements by position. Therefore, there are two distinct questions when you want to remove an element:

- “Remove the element at which position?”: use `remove(int index)`.
- “Remove the element whose value is equal to which object?”: use `remove(Object o)`.

These are two overloaded methods: they share the name `remove` but have different parameter types. Java does not inspect the list contents and guess the author's intent. The compiler selects the method from the type of the invocation receiver expression and the type of the argument.

For example, the integer list `[10, 20, 10, 30]` can be viewed as two rows of information:

| Index | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Value | 10 | 20 | 10 | 30 |

`remove(1)` removes the element at index 1, which is the value 20. To remove the first value 10, write `remove(Integer.valueOf(10))`. These two calls differ even when operating on the same `ArrayList<Integer>` instance.

The greatest risk appears with `List<Integer>`: both indices and values look like integers, so a call still compiles successfully while performing something different from what the author intended.

## 2. Contract of each method

| Attribute | `E remove(int index)` | `boolean remove(Object o)` |
|---|---|---|
| Argument meaning | Index of the element to remove | Object used to find an equal element |
| How the element is identified | 0-based position | First position satisfying the equality condition |
| Return value | The removed element itself, of type `E` | `true` if an element was removed; `false` if not found |
| Number of elements removed in one successful call | One | One, even if there are multiple equal values |
| When target is missing | Out-of-range index causes `IndexOutOfBoundsException` | Typically returns `false` when the object is valid but not present in the list |
| Impact on remaining positions | Elements after the removed position shift to an index one lower | Same, after finding and removing the first matching element |

For removal by index, the valid condition is `0 <= index && index < list.size()`. An index equal to `size()` is invalid. Do not mistakenly apply the insertion rule of `add(index, element)`, which allows inserting at the end.

For removal by object, the `List` contract describes removing the element with the lowest index satisfying `Objects.equals(o, get(i))`, if present. It uses equality, not “the same object in memory,” as the general criterion. `remove(Object)` also does not mean removing all elements with duplicate values.

Both are optional modification operations. Lists that do not support removal may throw `UnsupportedOperationException`. With `remove(Object)`, some implementations may also reject an incompatible argument type or `null` with an exception according to the API contract. Do not generalize the behavior of an `ArrayList` to every `List` implementation. [List.remove contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#remove(int)), [List.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#remove(java.lang.Object)).

## 3. Why do int and Integer select two different overloads?

### 3.1. An int argument selects removal by index

The following snippet illustrates inside a method:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

Integer removed = numbers.remove(1);

// removed = 20
// numbers = [10, 30]
```

The literal `1` has type `int`. With this argument, `remove(int)` matches directly. Although Java can box an integer into `Integer` to pass to an `Object` parameter, the compiler does not need that conversion when a matching method is already available in an earlier phase.

Do not read `numbers.remove(1)` as “remove the number 1” just because `numbers` contains `Integer`. In this call, the number 1 is the index.

### 3.2. An Integer argument selects removal by object

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
Integer value = 20;

boolean removed = numbers.remove(value);

// removed = true
// numbers = [10, 30]
```

The argument `value` has type `Integer`. It can undergo widening reference conversion to `Object` without unboxing. The method `remove(Object)` therefore matches during the strict invocation phase. The option of unboxing `Integer` to `int` belongs to a phase that permits additional conversions; Java does not proceed to that phase when it has already found a matching method earlier.

The accurate explanation is neither “Java always prefers primitives” nor “Java always prefers wrapper types.” You must look at the argument type and the phases for determining applicable methods. [JLS 15.12.2 on method selection](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2), [JLS 5.3 on invocation contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3).

### 3.3. Expressing intent clearly with List<Integer>

If the value to look up is currently an `int`, use `Integer.valueOf(value)` to remove by value:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
int valueToDelete = 20;

boolean found = numbers.remove(Integer.valueOf(valueToDelete));
```

`Integer.valueOf` creates or supplies a wrapper instance carrying that value. Whether it reuses a cached instance does not affect the removal outcome; `remove(Object)` relies on equality comparison.

If an `Integer` variable genuinely represents an index, you can convert it explicitly to `int`:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
Integer index = 1;

Integer deleted = numbers.remove(index.intValue());
```

Do this only when the variable genuinely carries positional meaning, and handle the possibility of `index == null` if the input allows `null`. Changing types to force an overload is not a substitute for correctly identifying the meaning of the data. [Integer.valueOf(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

### 3.4. Quick reference table for arguments

The table below assumes the receiver variable has declared type `List<Integer>`, the runtime object is an `ArrayList<Integer>`, and variables are non-`null` except where explicitly stated:

| Call expression | Argument type | Selected overload | Meaning |
|---|---|---|---|
| `list.remove(1)` | `int` | `remove(int)` | Remove index 1 |
| `list.remove(intValue)` | `int` | `remove(int)` | Remove the index held in the variable |
| `list.remove(Integer.valueOf(1))` | `Integer` | `remove(Object)` | Remove the first `Integer` value equal to 1 |
| `list.remove(integerValue)` | `Integer` | `remove(Object)` | Search by the object's value |
| `list.remove(integerValue.intValue())` | `int` | `remove(int)` | Remove by index after explicit unboxing |
| `list.remove((int) integerValue)` | `int` | `remove(int)` | Also removal by index; can fail if the variable is `null` |
| `list.remove((Object) 1)` | `Object` | `remove(Object)` | The number 1 is boxed into `Integer`, then used as the search value |
| `list.remove(1L)` | `long` | `remove(Object)` | Boxed into `Long`; does not remove an `Integer` equal to 1 in `ArrayList<Integer>` |
| `list.remove(null)` | Null type | `remove(Object)` | Search for a `null` element, if the implementation allows it |
| `list.remove((Integer) null)` | `Integer` | `remove(Object)` | Also search by object; does not unbox at this call site |

Arguments of type `byte`, `short`, and `char` can undergo widening primitive conversion to `int`, so when called through `List`, they select `remove(int)`. For example, a `char` with value `'A'` will be treated as numeric index 65, not as a character to search for. With `List<Character>`, to remove a character, pass a `Character`, such as `Character.valueOf('A')`.

Conversely, `long` is not automatically narrowed to `int` in this call. `remove(1L)` still compiles because `Long` is an `Object`. `Integer.valueOf(1).equals(Long.valueOf(1L))` is `false`, even though the two numbers have the same mathematical value. Having a parameter type of `Object` also means that the type parameter `E = Integer` does not guarantee that every argument passed to `remove(Object)` is an `Integer`.

With `var`, the type is still inferred at compile time: `var x = 1;` creates an `int` variable, while `var x = Integer.valueOf(1);` creates an `Integer` variable. `var` does not erase the distinction between the two cases.

## 4. The declared type of the receiver variable also matters

`List` adds positional removal operations; the `Collection` interface has `remove(Object)` but does not have `remove(int)`.

Illustrative snippet:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
Collection<Integer> view = numbers;

boolean removed = view.remove(1);

// removed = true
// numbers = [2, 3]
```

Through the variable `view` of type `Collection<Integer>`, the compiler sees only the removal-by-object method. The `int` argument is boxed into `Integer`, then used as the search object. The result is removing the value 1.

If `numbers.remove(1)` were called on another initial list also containing `[1, 2, 3]`, the selected method would be removal by index and the result would be `[1, 3]`.

`view` and `numbers` in the example refer to the same object; no copy of the list is created when assigning `view = numbers`. The difference lies in the set of methods visible at the call site. Once the overload is selected at compile time, dynamic method dispatch on the runtime object executes the corresponding method. The actual runtime type `ArrayList` does not re-select between “index” and “value” at runtime. [Collection.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

Do not change a variable's type to `Collection` just to hide an overload in a confusing piece of code. Choose the interface according to the API's needs, and express value removal explicitly when working with `List<Integer>`.

## 5. The target return type does not fix an unintended call

The snippet below intentionally fails to compile:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

boolean removed = numbers.remove(1);
```

`remove(1)` is still selected as `remove(int)` and returns `Integer`. Java does not look at the target `boolean` variable and go back to select `remove(Object)`.

Fix it according to the actual intent:

```java
// To remove the value 1:
boolean found = numbers.remove(Integer.valueOf(1));

// To remove the element at index 1:
Integer deleted = numbers.remove(1);
```

In the first case, `false` means the value 1 was not found. In the second case, the result is the removed element, not a success flag. Distinguishing the two return forms also helps readers spot mistakenly written removal operations.

If the return value is ignored, the risk of a silent bug is even higher: `numbers.remove(1);` may compile and run normally while removing the wrong position. Therefore, do not use “no compiler error” as proof that the removal intent was expressed properly.

## 6. Complete runnable program: verifying overload selection

The short examples above illustrate a method body and require the appropriate imports. The following program is a standalone file using APIs available in Java 17.

Save as `RemoveOverloadDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class RemoveOverloadDemo {
    private static ArrayList<Integer> numbers() {
        return new ArrayList<>(List.of(10, 20, 10, 30));
    }

    public static void main(String[] args) {
        ArrayList<Integer> byIndex = numbers();
        Integer removedElement = byIndex.remove(1);
        System.out.println("remove(1) -> " + removedElement);
        System.out.println("byIndex = " + byIndex);

        ArrayList<Integer> byValue = numbers();
        boolean removedValue = byValue.remove(Integer.valueOf(10));
        System.out.println("remove(Integer.valueOf(10)) -> " + removedValue);
        System.out.println("byValue = " + byValue);

        ArrayList<Integer> primitiveArgument =
                new ArrayList<>(List.of(1, 2, 3));
        int index = 1;
        System.out.println("int argument -> " + primitiveArgument.remove(index));
        System.out.println("primitiveArgument = " + primitiveArgument);

        ArrayList<Integer> wrapperArgument =
                new ArrayList<>(List.of(1, 2, 3));
        Integer value = 1;
        System.out.println("Integer argument -> " + wrapperArgument.remove(value));
        System.out.println("wrapperArgument = " + wrapperArgument);

        ArrayList<Integer> differentWrapper =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("long argument -> " + differentWrapper.remove(1L));
        System.out.println("differentWrapper = " + differentWrapper);

        List<Integer> backingList = new ArrayList<>(List.of(1, 2, 3));
        Collection<Integer> collectionView = backingList;
        System.out.println("Collection receiver -> " + collectionView.remove(1));
        System.out.println("backingList = " + backingList);

        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        System.out.println("String list, int argument -> " + words.remove(1));
        System.out.println("words = " + words);
        System.out.println("String list, String argument -> " + words.remove("C"));
        System.out.println("words = " + words);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RemoveOverloadDemo.java
java RemoveOverloadDemo
```

Expected output:

```text
remove(1) -> 20
byIndex = [10, 10, 30]
remove(Integer.valueOf(10)) -> true
byValue = [20, 10, 30]
int argument -> 2
primitiveArgument = [1, 3]
Integer argument -> true
wrapperArgument = [2, 3]
long argument -> false
differentWrapper = [1, 2, 3]
Collection receiver -> true
backingList = [2, 3]
String list, int argument -> B
words = [A, C]
String list, String argument -> true
words = [A]
```

Reading the results decision by decision:

- `remove(1)` on `[10, 20, 10, 30]` returns the element 20; both 10 values remain.
- `remove(Integer.valueOf(10))` returns `true` and removes only the first 10; the remaining 10 preserves its relative order with the other elements.
- Two variables both representing the number 1, but having types `int` and `Integer`, cause the calls to remove two different elements from `[1, 2, 3]`.
- The argument `1L` is treated as a `Long` object; the `ArrayList<Integer>` in the example finds no element equal to it and returns `false`.
- The call through `Collection<Integer>` removes the value 1 from the underlying list itself.
- Even `List<String>` still has both methods: passing `1` removes the element at index 1, while passing `"C"` searches for a string equal to `"C"`. The trap does not exist solely because a list holds numbers; a list of numbers merely makes it harder to spot.

## 7. Equality, duplicate elements, and positions after removal

### 7.1. Removal by object is not removal by memory identity

For classes with content-based `equals` such as `String` and `Integer`, a distinct but equal instance can still serve as the removal argument.

Illustrative snippet:

```java
List<String> labels = new ArrayList<>(List.of("java", "sql", "java"));

boolean changed = labels.remove(new String("java"));

// changed = true
// labels = [sql, java]
```

`new String("java")` is not the exact `String` reference stored at the first position, but it equals that string according to `equals`. Creating `new String` here is only to clarify the mechanism; in normal code, using the literal `"java"` is sufficient.

For custom domain types, you must know that type's `equals` contract. If a class retains the reference comparison inherited from `Object`, a new instance containing identical-looking fields may not equal the instance currently in the list. Switching from `remove(int)` to `remove(Object)` does not automatically create a “same ID means equal” rule.

### 7.2. Only the first matching element is removed

From `[10, 20, 10, 30]`, removing by value 10 once yields `[20, 10, 30]`. If the business goal is “remove every 10,” a single `remove(Object)` call does not meet that goal. `removeIf` is a separate API for conditional removal; review its own contract before using it rather than attributing that meaning to `remove(Object)`.

After a removal, the relative order of the remaining elements is preserved, but their indices change. For example, from `[A, B, C, D]`, `remove(1)` produces `[A, C, D]`. If you then call `remove(2)`, the removed element is `D`, because `C` has shifted to index 1. A former index is not a stable identity of an element.

Do not fix bugs by mechanically replacing `remove(index)` with `remove(Integer.valueOf(index))`. Those two lines express two different intents; you must determine whether you are holding a position or a value.

## 8. null: distinguishing a null argument from a null result

`ArrayList` permits `null` elements. Consequently, the following situations can occur:

1. `list.remove(null)` or `list.remove(nullableInteger)`, where `nullableInteger` has type `Integer`, selects `remove(Object)`. If the list contains `null`, it removes the first occurrence and returns `true`; this call does not require unboxing the argument.
2. `list.remove(index)` selects removal by index. If the element at that position is `null`, the method removes it successfully and returns `null`.
3. If that `null` result is assigned to an `int` variable, unboxing causes a `NullPointerException` after the list has already been modified.
4. If `nullableIndex.intValue()` is called when the index variable is `null`, the error occurs while evaluating the argument, before `remove` is invoked. The list is not modified by that call.

The two `NullPointerException` errors in items 3 and 4 share the same name but happen at different times and leave the list in different states afterward. Catching the exception does not automatically roll back a removal that has already taken place. [ArrayList and null support](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [JLS 5.1.8 on unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

The standalone program below also tests invalid indices and unmodifiable lists. Save as `RemoveNullAndBoundaryDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RemoveNullAndBoundaryDemo {
    public static void main(String[] args) {
        List<Integer> byValue =
                new ArrayList<>(Arrays.asList(7, null, 9, null));
        Integer nullableValue = null;
        System.out.println("remove nullable value -> " + byValue.remove(nullableValue));
        System.out.println("byValue = " + byValue);

        List<Integer> nullableResult =
                new ArrayList<>(Arrays.asList((Integer) null, 7));
        Integer removed = nullableResult.remove(0);
        System.out.println("removed element = " + removed);
        System.out.println("nullableResult = " + nullableResult);

        List<Integer> unboxAfter =
                new ArrayList<>(Arrays.asList(7, null, 9));
        try {
            int result = unboxAfter.remove(1);
            System.out.println("result = " + result);
        } catch (NullPointerException ex) {
            System.out.println("unbox returned null -> NullPointerException");
        }
        System.out.println("unboxAfter = " + unboxAfter);

        List<Integer> unboxBefore =
                new ArrayList<>(Arrays.asList(7, null, 9));
        Integer nullableIndex = null;
        try {
            unboxBefore.remove(nullableIndex.intValue());
        } catch (NullPointerException ex) {
            System.out.println("unbox argument null -> NullPointerException");
        }
        System.out.println("unboxBefore = " + unboxBefore);

        List<Integer> boundaries = new ArrayList<>(List.of(4, 5));
        System.out.println("missing value -> "
                + boundaries.remove(Integer.valueOf(-1)));
        try {
            boundaries.remove(-1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("negative index -> IndexOutOfBoundsException");
        }
        try {
            boundaries.remove(boundaries.size());
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("index equal to size -> IndexOutOfBoundsException");
        }
        System.out.println("boundaries = " + boundaries);

        List<Integer> fixed = List.of(1, 2, 3);
        try {
            fixed.remove(Integer.valueOf(1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable list -> UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RemoveNullAndBoundaryDemo.java
java RemoveNullAndBoundaryDemo
```

Expected output:

```text
remove nullable value -> true
byValue = [7, 9, null]
removed element = null
nullableResult = [7]
unbox returned null -> NullPointerException
unboxAfter = [7, 9]
unbox argument null -> NullPointerException
unboxBefore = [7, null, 9]
missing value -> false
negative index -> IndexOutOfBoundsException
index equal to size -> IndexOutOfBoundsException
boundaries = [4, 5]
unmodifiable list -> UnsupportedOperationException
```

Key points to read from the post-operation states:

- `byValue` initially has two `null` elements; after `remove(nullableValue)`, one `null` remains.
- `nullableResult.remove(0)` returns a valid `null` when assigned to an `Integer` variable.
- `unboxAfter` loses its `null` element even though assigning the return value to `int` ends with an exception.
- `unboxBefore` remains unchanged because `nullableIndex.intValue()` failed before `remove` was called.
- `Integer.valueOf(-1)` is a search object; when not found, it returns `false`. An `int` argument of -1, by contrast, is an invalid index and throws an exception.
- An index equal to `size()` lies immediately past the last element, so there is no element to remove.
- `List.of` creates an unmodifiable list. Even though the right remove-by-value overload was selected, removing an existing element still throws `UnsupportedOperationException`. Selecting the right overload and having permission to mutate the list are two separate requirements.

A fixed-size list created by `Arrays.asList` also does not support element removal. In the program, `Arrays.asList` is wrapped with `new ArrayList<>(...)` to obtain a list that allows removal while also permitting initialization with `null` elements.

## 9. Applying this in real-world code

### 9.1. Separate “element ID” meaning from “display position”

Suppose a system maintains `List<Integer> userIds`. The variable `selectedUserId` holds a user ID, not a row number in the UI.

Illustrative snippet inside a method:

```java
List<Integer> userIds = new ArrayList<>(List.of(101, 205, 309));
int selectedUserId = 205;

boolean deleted = userIds.remove(Integer.valueOf(selectedUserId));
```

If you write `userIds.remove(selectedUserId)`, Java treats 205 as an index and typically throws `IndexOutOfBoundsException`. Worse yet, with a small ID like 1 on a sufficiently long list, the operation can silently remove the wrong user without throwing an error.

Conversely, if the UI supplies the index of the selected row, use `remove(selectedIndex)` after validating the input and confirming the state of the list at the time of removal. Do not box an index and accidentally turn it into a lookup by value.

Variable names should express meaning—such as `index`, `position`, `userId`, or `valueToDelete`—rather than a generic numeric name. When fixing code, inspect where the variable originates, not just its type at the call site.

### 9.2. Internal APIs can use clearer names

When a utility class genuinely needs to provide both intents for a numeric list, give them two distinct names instead of introducing yet another hard-to-read overload pair. These are illustrative methods to place inside a class, not a standalone program:

```java
static Integer removeAt(List<Integer> numbers, int index) {
    return numbers.remove(index);
}

static boolean removeValue(List<Integer> numbers, int value) {
    return numbers.remove(Integer.valueOf(value));
}
```

`removeAt(numbers, 1)` and `removeValue(numbers, 1)` force the meaning to appear right at the call site. There is no need to create a utility class for every isolated call; the goal is to keep semantics clear when designing APIs prone to confusion.

### 9.3. Do not infer performance purely from the overload name

`remove(Object)` typically has to search for a matching element before removing it. `remove(int)` is already given the position, but the cost of reaching that position and updating the structure depends on the implementation.

With `ArrayList`, removing by position may still require shifting many subsequent elements; having the index upfront does not make every removal constant-time. With a linked list, traversing to a position also carries a cost. Choose the operation with the right semantics first, then evaluate performance against the specific data structure and workload. Do not switch to removal by index just to skip the search step if you do not actually know the right position.

## 10. Common mistakes and self-check checklist

| Symptom | Common cause | Fix according to intent |
|---|---|---|
| Wanted to remove the number 1, but the second element disappeared | Passed an `int` literal to `List.remove` | Use `Integer.valueOf(1)` if 1 is the value to search for |
| Wanted to remove the index held in an `Integer` variable, but the list did not change | `remove(Object)` was selected and found no value equal to that variable | Use type `int` for indices, or convert explicitly after handling `null` |
| `boolean ok = list.remove(1)` fails to compile | The selected method returns an `Integer` element | Fix the argument or return type according to intent; do not rely on the target variable to select an overload |
| `remove(1L)` returns `false` on `ArrayList<Integer>` | Searching for a `Long`, not an `Integer` | Normalize to the proper value type before removing; do not apply arbitrary narrowing casts |
| A duplicate value still remains | `remove(Object)` removes only the first occurrence | Determine whether you need to remove one element or all matching elements |
| Got a `null` exception, yet the element still disappeared | A `null` `Integer` return value was unboxed after removal by index | Receive the result as `Integer` and handle `null` appropriately |
| Argument is right, but `UnsupportedOperationException` is thrown | The list does not support removal | Choose a modifiable collection when business requirements call for removal |
| Same data, but calling through `Collection` produces a different result | The overload set at the call site differs from `List` | Check the declared type of the receiver variable |

When reading a `remove` call, check in this order:

1. Is the receiver variable declared as `List`, `Collection`, or another type?
2. What is the argument type after the expression is evaluated: `int`, `Integer`, `Object`, `long`, or something else?
3. Does the selected overload express a position or a value?
4. Is the expected return value the removed element or a found flag?
5. Does the list allow removal, and can it contain `null`?
6. How do the indices and list state change after the removal?

## 11. Predict before running

Each question uses a fresh list, independent of the others:

```java
List<Integer> values = new ArrayList<>(List.of(2, 0, 2, 4));
```

| Question | Call | What to predict |
|---|---|---|
| A | `values.remove(2)` | Return value and remaining list |
| B | `values.remove(Integer.valueOf(2))` | Returned flag and which 2 element is removed |
| C | `values.remove(2L)` | Is the number 2 removed? |
| D | `Integer target = 0; values.remove(target);` | Does it remove index 0 or value 0? |
| E | `Collection<Integer> view = values; view.remove(2);` | Which object is modified? |

Answers and explanations:

- A: returns the `Integer` equal to 2 at index 2; remaining list is `[2, 0, 4]`.
- B: returns `true`; removes the number 2 at index 0; remaining list is `[0, 2, 4]`.
- C: on this `ArrayList<Integer>`, returns `false`; remains `[2, 0, 2, 4]`, because the argument is a `Long`.
- D: selects `remove(Object)`, returns `true`, removes the value 0; remaining list is `[2, 2, 4]`. The `Integer` type of `target` is the deciding factor.
- E: through `Collection`, the number 2 is boxed and used to search by value; returns `true`, and the `values` list becomes `[0, 2, 4]`. `view` is another reference to the same object.

The skill to build is reading the exact intent from the call's types: `remove(int)` returns the element at a position, whereas `remove(Object)` reports whether the first occurrence equal to a search object was removed. With numeric lists, write the required conversion explicitly at the call site so a value is never mistaken for an index.
