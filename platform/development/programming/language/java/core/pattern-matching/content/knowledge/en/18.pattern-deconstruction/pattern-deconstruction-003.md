# Deconstructing Flat Records in Java 21

**Deconstruction** of a flat record is a way to match a record object and extract its components directly into separate variables. In Java 21+, we do this using a **record pattern**, such as `Item(String sku, int quantity, double unitPrice)` or `Item(var sku, var quantity, var unitPrice)`.

This lesson focuses on **flat records**: the record components are ordinary values such as `String`, `int`, and `double`; we deconstruct exactly **one level** and do not yet need nested record patterns. Record patterns became a standard feature in **Java 21** (JEP 440). They can be combined with `instanceof` and `switch`; the `--enable-preview` option is not required when compiling with Java 21.

## 1. From regular records to deconstruction

Define a record to store an item line:

```java
record Item(String sku, int quantity, double unitPrice) {}
```

This record has **three components in the exact order of declaration**:

| Position | Component | Type | Meaning |
| --- | --- | --- | --- |
| 1 | `sku` | `String` | Item code |
| 2 | `quantity` | `int` | Quantity |
| 3 | `unitPrice` | `double` | Unit price |

Create data using the constructor:

```java
Item item = new Item("PEN", 2, 12.5);
```

When reading values, the usual way is to call accessors:

```java
String sku = item.sku();
int quantity = item.quantity();
double price = item.unitPrice();
```

With a **record pattern**, in an appropriate matching context, we can check and extract immediately:

```java
Object candidate = item;

if (candidate instanceof Item(String sku, int quantity, double price)) {
    System.out.println(sku);      // PEN
    System.out.println(quantity); // 2
    System.out.println(price);    // 12.5
}
```

In the expression `candidate instanceof Item(String sku, int quantity, double price)`:

1. `candidate` is the object being tested.
2. `Item` is the **record type** to match.
3. `(String sku, int quantity, double price)` are the **component patterns** in the order of `Item`'s components.
4. If it matches, `sku`, `quantity`, and `price` are declared and receive the corresponding values. We use them inside the `if` branch where the compiler knows the match succeeded.

The syntax `Item(String sku, int quantity, double price)` is a **pattern**, not a constructor call or record creation syntax. `new Item("PEN", 2, 12.5)` is the object creation expression.

## 2. Flat record pattern syntax

The general form when matching a record with no nested levels:

```text
RecordType(ComponentPattern1, ComponentPattern2, ...)
```

The `ComponentPattern`s in this basic lesson are usually **type patterns** with an explicit type or `var`:

```java
// Explicitly declare the type of each component.
if (candidate instanceof Item(String s, int q, double p)) {
    System.out.println(s + ": " + q * p);
}

// Let the compiler infer the type of each component.
if (candidate instanceof Item(var s, var q, var p)) {
    System.out.println(s + ": " + q * p);
}
```

Both approaches above extract the same three components. In the `var` version, the compiler infers **`s` has type `String`, `q` has type `int`, and `p` has type `double`** from the declaration `record Item(String sku, int quantity, double unitPrice)`. `var` does not create dynamically typed variables.

Variable names in the pattern **do not have to match** the record component names. For example, `p` still receives `unitPrice` because it stands in the **third position**. However, choose clear names when writing real code.

### The number and types of component patterns must match

The `Item` record has three components, so it requires three component patterns. The following ways of writing it are invalid:

```java
// Wrong: missing the third component.
// candidate instanceof Item(String sku, int quantity)

// Wrong: type order is incompatible with the record declaration.
// candidate instanceof Item(int quantity, String sku, double price)

// Wrong: variables are not declared with a type or var.
// candidate instanceof Item(sku, quantity, unitPrice)
```

The three lines above **only illustrate invalid code**, placed in comments, not examples to run. A regular pattern deconstructs based on the order and types of record components; it does not map variables by name.

## 3. Using record patterns with instanceof

`instanceof` is suitable when the initial value has a broader type, such as `Object`, and we only want to operate when the data is actually an `Item`:

```java
static double calculateTotal(Object candidate) {
    if (candidate instanceof Item(var sku, var quantity, var price)) {
        return quantity * price;
    }
    return 0.0;
}
```

Here `sku` is extracted but unused; that is a valid variable, though you should only declare the variables you need in more complex designs. For flat records, a record pattern requires providing a component pattern for every component (Java 21 does not yet have a standard `_` syntax to ignore components as a regular pattern). If you only need a single accessor, writing `candidate instanceof Item item` and then calling `item.quantity()` can be easier to read.

It can be combined with an `&&` condition for additional checks:

```java
if (candidate instanceof Item(var sku, var quantity, var price)
        && quantity > 0) {
    System.out.println(sku + " total=" + (quantity * price));
}
```

The right-hand side of `&&` is only evaluated after the record pattern matches, so `quantity` is in a valid scope for use. Conversely, record pattern variables are not automatically in scope throughout the entire method.

### When it does not match

- If `candidate` is an `Item`, the record pattern is checked and matching components are extracted.
- If `candidate` is another type, such as `String`, `instanceof` returns `false`.
- If `candidate == null`, `instanceof` with a record pattern also returns `false`. It does not invoke accessors on a `null` object.

**Deconstruction does not modify the record**, does not create a new copy, and does not convert the object to another type. It checks, reads the components using the record's accessor mechanism, and binds the results into the new pattern variables.

## 4. Using record patterns in switch

A record pattern can also appear in a `case` branch of a `switch` starting in Java 21:

```java
static String stockLabel(Object candidate) {
    return switch (candidate) {
        case null -> "null input";
        case Item(var sku, var quantity, var price) when quantity == 0 ->
                "Empty: " + sku;
        case Item(var sku, var quantity, var price) ->
                "Available: " + sku + " x" + quantity;
        default -> "Other type";
    };
}
```

Explanation:

- `case Item(var sku, var quantity, var price)` both identifies `Item` and extracts the three components; the variables are used in the expression after `->`.
- `when quantity == 0` is a **guard**: the first branch is only chosen when the record matches **and** the quantity is 0.
- The unguarded `Item(...)` branch receives the remaining `Item`s.
- `case null` handles the case where the `switch` input itself is `null`. `default` is not a default substitute for `case null`.
- `default` handles other value types.

Within the same `switch`, placing a broad unconditional pattern **before** a more specific pattern can make the later case unreachable (a *dominance* error). In this example, the guarded branch comes before the general `Item(...)` branch.

When the logic is short, `instanceof` is usually enough; when you want to classify multiple cases based on component values, `switch` helps organize the branches more clearly.

## 5. Special note on null in flat records

**A flat record can still contain a `null` reference component.** Without validation rules in the constructor, we are allowed to create:

```java
Item item = new Item(null, 1, 3.0);
```

Here `Item` is a non-`null` object; only `sku` (of type `String`) is `null`. With:

```java
Object candidate = item;

if (candidate instanceof Item(var sku, var quantity, var price)) {
    System.out.println(sku == null); // true
}
```

The record pattern **matches successfully** and `sku` receives `null`. This does not contradict the rule that a record pattern does not match a `null` **record object**. Component patterns such as `var` are individual patterns inside the record pattern.

Specifically, when a component type pattern is **unconditional** for the declared type of the component, it can match a `null` component. For `Item`, both `String sku` (on a component declared as `String`) and `var sku` can extract that component when it is `null`. After extraction, you need to check `sku == null` before calling `sku.length()` or other methods.

Conversely, the case:

```java
Object candidate = null;
boolean matched = candidate instanceof Item(var sku, var q, var p);
// matched == false
```

still returns `false` because the **outer object** does not match `Item(...)`.

The `quantity` and `unitPrice` components have primitive types `int` and `double`, so they **cannot contain `null`**. If business rules do not allow `sku == null`, place a constraint in the record's constructor instead of expecting deconstruction to reject it automatically:

```java
record StrictItem(String sku, int quantity, double unitPrice) {
    StrictItem {
        java.util.Objects.requireNonNull(sku, "sku");
    }
}
```

The snippet above is a standalone example of a **record declaration**, not part of the runnable class in Section 7. `new StrictItem(null, 1, 3.0)` throws a `NullPointerException` upon object creation. Constructor rules enforce data invariants; record patterns only check and extract existing data.

## 6. Comparing three ways to access data

Suppose we have `Object candidate` expected to be an `Item`:

| Approach | Example | Suitable when |
| --- | --- | --- |
| Type pattern | `candidate instanceof Item item`, then `item.sku()` | You want to keep the object, read only a few components, or call multiple record methods |
| Explicit-type record pattern | `candidate instanceof Item(String sku, int quantity, double price)` | You want to see the type of every component right at the deconstruction site |
| Record pattern with `var` | `candidate instanceof Item(var sku, var quantity, var price)` | You want to reduce type repetition while still having statically inferred component variables |

There is no Java 21 syntax like `var (sku, quantity, price) = item;` or `(sku, quantity, price) = item;` to deconstruct as a standalone assignment statement. **A record pattern appears in a pattern matching context** such as `instanceof` or a `switch` `case`.

The variables `sku`, `quantity`, and `price` are local variables bound by the match. Modifying a local variable (when reassignment is allowed) **does not change the record's component**; record components are immutable at the reference/component level, though a reference value pointing to an object can mutate internally if that object is mutable.

## 7. Complete compilable and runnable Java 21 example

Save this entire snippet to **`FlatRecordDeconstruction.java`**:

```java
public class FlatRecordDeconstruction {
    record Item(String sku, int quantity, double unitPrice) {}

    static String describe(Object candidate) {
        if (candidate instanceof Item(String sku, int quantity, double unitPrice)) {
            return "Item " + sku + ": qty=" + quantity + ", price=" + unitPrice;
        }
        return "Not an Item";
    }

    static double total(Object candidate) {
        if (candidate instanceof Item(var sku, var quantity, var unitPrice)
                && quantity > 0) {
            return quantity * unitPrice;
        }
        return 0.0;
    }

    static String stockLabel(Object candidate) {
        return switch (candidate) {
            case null -> "null input";
            case Item(var sku, var quantity, var unitPrice) when quantity == 0 ->
                    "Empty: " + sku;
            case Item(var sku, var quantity, var unitPrice) ->
                    "Available: " + sku + " x" + quantity;
            default -> "Other type";
        };
    }

    public static void main(String[] args) {
        Item item = new Item("PEN", 2, 12.5);
        System.out.println(describe(item));
        System.out.println("Total: " + total(item));
        System.out.println(stockLabel(item));
        System.out.println(stockLabel(new Item("NOTE", 0, 7.0)));
        System.out.println(describe("hello"));
        System.out.println(stockLabel(null));
        Object missingSku = new Item(null, 1, 3.0);
        if (missingSku instanceof Item(var sku, var quantity, var unitPrice)) {
            System.out.println("sku null: " + (sku == null));
        }
        System.out.println("Accessor: " + item.sku());
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 FlatRecordDeconstruction.java
java FlatRecordDeconstruction
```

**Expected output:**

```text
Item PEN: qty=2, price=12.5
Total: 25.0
Available: PEN x2
Empty: NOTE
Not an Item
null input
sku null: true
Accessor: PEN
```

Output explanation:

1. `describe(item)` uses an explicit-type record pattern to extract `sku="PEN"`, `quantity=2`, `unitPrice=12.5`.
2. `total(item)` uses `var` to extract the components and computes `2 * 12.5 = 25.0`. The condition `quantity > 0` in the same `if` check verifies the matching branch.
3. `stockLabel(item)` selects the general `Item(...)` branch, while `Item("NOTE", 0, 7.0)` selects the guarded branch because `quantity == 0`.
4. `describe("hello")` does not match `Item` and returns `Not an Item`.
5. `stockLabel(null)` enters `case null`.
6. The last record has `sku == null`, yet deconstruction with `var sku` still succeeds; the accessor `item.sku()` on the first record returns `PEN`.

The example uses only standard Java 21 features and has been verified with `javac --release 21`.

## 8. Common mistakes

1. **Writing too few or too many component patterns.** With three components, you must match exactly three positions in `Item(...)`. If the record structure changes, update the pattern accordingly.
2. **Confusing variable names with a mapping mechanism.** `Item(var price, var amount, var code)` still binds the first variable to `sku`, the second to `quantity`, and the third to `unitPrice`. Misleading names cause confusion even though the code compiles.
3. **Reading pattern variables when a match is not guaranteed.** Do not use `sku` outside places where the compiler guarantees the record pattern succeeded. In `if`, use it in the matching branch; in `switch`, use it in the corresponding case body.
4. **Confusing a record pattern with a constructor call.** A pattern describes the structure to deconstruct; a constructor creates a new object. Do not write `new Item(var sku, var quantity, var price)`.
5. **Assuming all reference components are non-null.** `Item(var sku, ...)` can still extract `sku == null`, so check before calling methods on `sku`.
6. **Using record pattern syntax with regular classes.** `RecordType(...)` only applies to record types declared with `record`; for regular classes, use a type pattern or appropriate accessors.
7. **Using a Java version without stable support.** This lesson uses standard Java 21 `record patterns` and `switch` pattern matching. On JDK 17, the program above will not compile with this syntax.
8. **Assuming `switch default` automatically catches null.** For a `null` selector in this kind of `switch`, you must handle `case null`; otherwise, a `NullPointerException` can occur.

## 9. Self-check exercises

**Exercise 1.** Given `Object c = new Item("BOOK", 4, 6.0);`, if deconstructed with `Item(var code, var q, var p)`, what is the value of `q * p`?

*Answer:* `24.0`. `q` is `4` and `p` is `6.0`; the inferred types are `int` and `double`, respectively.

**Exercise 2.** Does the pattern `Item(var price, var qty, var sku)` extract values according to the meaning of the variable names?

*Answer:* No. Java extracts **by position**, so `price` receives the item code (`String`), `qty` receives the quantity (`int`), and `sku` receives the unit price (`double`). Choose names that match the actual meaning.

**Exercise 3.** Can `new Item(null, 1, 3.0)` match `Item(var sku, var quantity, var unitPrice)`?

*Answer:* Yes. The outer `Item` object is non-`null` and `var sku` can receive the `sku == null` component. However, calling `sku.length()` at that point will still throw a `NullPointerException`.

**Exercise 4.** If you only need `item.sku()`, do you always have to use a record pattern?

*Answer:* No. Using a regular accessor, or a type pattern `Item item` when checking an `Object`, can be simpler and clearer.

**References:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).