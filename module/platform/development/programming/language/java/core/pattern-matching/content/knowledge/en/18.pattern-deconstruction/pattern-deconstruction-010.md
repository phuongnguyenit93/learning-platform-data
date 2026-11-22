# Comparing Deconstruction with Manual Mapping in Java

## 1. Distinguishing the two concepts before comparing

In Java, **deconstruction using a record pattern** is the operation of checking whether a value matches a `record`, and then **extracting the record components into local variables**. For example, `Order(var id, Money(var cents, var currency))` checks both the outer `Order` and the nested `Money`, while extracting `id`, `cents`, and `currency`.

**Manual mapping** is when the developer explicitly accesses the source data, checks conditions, and **transforms it into a target representation**, such as an `OrderRow` used for reporting or returning from an API. When the source is a record, the manual approach typically calls accessors such as `order.total()` and `total.currency()`; if a DTO is needed, the developer also calls the target object's constructor or builder directly.

The two operations do not completely replace each other:

- Deconstruction **extracts data** from a record; it **does not automatically create** a new DTO, nor does it rename or reformat fields.
- Mapping **creates the target representation**; obtaining the source data can be done **using manual accessors or using deconstruction**.
- Therefore, the most realistic comparison is between **"manually accessing components and then mapping"** and **"using a record pattern to extract components and then mapping"**.

Record patterns were standardized in **Java 21** (JEP 440). The examples below require **JDK 21+**, without `--enable-preview`. Java 17 has `record` but does not yet support record pattern syntax.

## 2. The same business requirement

Suppose the source data consists of an order and a monetary amount, and the target data is a flat report row:

```java
record Money(long cents, String currency) {}
record Order(String id, Money total) {}
record OrderRow(String id, String currency, long cents) {}
```

We need to convert an input value of type `Object` into an `OrderRow` when:

1. The input is actually an `Order`.
2. `Order.total` is not `null`.
3. `Money.currency` is not `null`.

If any of the three conditions is not met, the mapping returns `null` by **the convention of this example**. In a real application, you might choose `Optional<OrderRow>`, an error object, or an exception depending on the API contract.

A valid output, for example with `new Order("O-17", new Money(1299, "USD"))`, is:

```text
OrderRow[id=O-17, currency=USD, cents=1299]
```

Here `cents` is the smallest unit of USD: `1299` corresponds to 12.99 USD. This article keeps the integer representation to focus on data extraction and mapping.

## 3. Approach A — manual mapping with accessors

After checking the `Order` type, we retrieve each component in turn and check for `null` manually:

```java
static OrderRow manual(Object source) {
    if (!(source instanceof Order order)) return null;

    Money total = order.total();
    if (total == null) return null;

    String currency = total.currency();
    if (currency == null) return null;

    return new OrderRow(order.id(), currency, total.cents());
}
```

**Explanation:**

- `source instanceof Order order` is a **type pattern**, which checks and binds the **entire `Order` object**. This is not record deconstruction yet.
- `order.total()` retrieves the `total` component; it must be checked for `null` before calling `total.currency()` or `total.cents()`.
- `new OrderRow(...)` is the actual step of **mapping to the target object**; in this example, the `currency` field is promoted to the same level as `id` and `cents`.
- Each check branch is explicit, making it easy to add specific error messages for "missing total" or "missing currency".

This approach makes intermediate processing steps easy to control, but when data structures are deeply nested, the code can become verbose due to repeated accessor calls and `null` checks.

## 4. Approach B — deconstruction first, mapping second

A record pattern extracts two levels of data directly inside `instanceof`:

```java
static OrderRow deconstructAndMap(Object source) {
    if (source instanceof Order(var id, Money(var cents, var currency))
            && currency != null) {
        return new OrderRow(id, currency, cents);
    }
    return null;
}
```

**Step-by-step explanation:**

- `Order(...)` requires the source value to match the `Order` record and accesses its two components in **declaration order**: `id` then `total`.
- `var id` receives the `id` component; `Money(var cents, var currency)` requires the `total` component to match the `Money` record and further extracts `cents` and `currency`.
- `var` is inferred from the static type of each component: `id` and `currency` are `String`, and `cents` is `long`. These are not dynamically typed variables.
- If `source` is `null`, is not an `Order`, or `total` is `null`, the record pattern expression does not match and `instanceof` evaluates to `false`.
- A reference-type component captured with `var` **can still be `null`**. Therefore, the condition `&& currency != null` is still necessary; deconstruction **does not automatically validate** all values.
- The variables `id`, `cents`, and `currency` only exist where the compiler can prove the pattern matched; they are in scope on the right-hand side of `&&` and inside the corresponding `if` branch.
- `new OrderRow(id, currency, cents)` **is still a manual mapping step**. The record pattern does not create the report row on its own.

Thus, both methods share the same **result contract** for the normal cases in this model. They differ in syntax, checking strategy, and how easily error messages can be attached.

## 5. Complete runnable program

Create a file named **`DeconstructionVsMappingDemo.java`** with the following full contents:

```java
public class DeconstructionVsMappingDemo {
    record Money(long cents, String currency) {}
    record Order(String id, Money total) {}
    record OrderRow(String id, String currency, long cents) {}

    static OrderRow manual(Object source) {
        if (!(source instanceof Order order)) return null;

        Money total = order.total();
        if (total == null) return null;

        String currency = total.currency();
        if (currency == null) return null;

        return new OrderRow(order.id(), currency, total.cents());
    }

    static OrderRow deconstructAndMap(Object source) {
        if (source instanceof Order(var id, Money(var cents, var currency))
                && currency != null) {
            return new OrderRow(id, currency, cents);
        }
        return null;
    }

    static void verify(String label, Object source) {
        OrderRow first = manual(source);
        OrderRow second = deconstructAndMap(source);

        if (!java.util.Objects.equals(first, second)) {
            throw new AssertionError(label + ": " + first + " != " + second);
        }
        System.out.println(label + " -> " + second);
    }

    public static void main(String[] args) {
        verify("valid", new Order("O-17", new Money(1299, "USD")));
        verify("missing-total", new Order("O-18", null));
        verify("missing-currency", new Order("O-19", new Money(2000, null)));
        verify("wrong-type", "not an order");
        verify("null-input", null);
        System.out.println("5 cases passed");
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 DeconstructionVsMappingDemo.java
java DeconstructionVsMappingDemo
```

**Exact stdout:**

```text
valid -> OrderRow[id=O-17, currency=USD, cents=1299]
missing-total -> null
missing-currency -> null
wrong-type -> null
null-input -> null
5 cases passed
```

The `verify` method compares results using `Objects.equals`. Because `OrderRow` is a record, two record values are compared component-by-component via the generated `equals` method. If the two approaches produce different results, the program throws an `AssertionError`. The output above was verified on JDK 24 using Java 21 syntax.

**What the test cases demonstrate:**

| Input data | Accessor mapping | Deconstruction + mapping | Reason |
| --- | --- | --- | --- |
| Valid `Order` and `Money` with currency | Creates `OrderRow` | Creates `OrderRow` from extracted variables | All conditions met |
| `Order.total == null` | Stops at `total` check | `Money(...)` does not match | Both return `null` |
| `Money.currency == null` | Stops at `currency` check | Pattern still extracts `currency`, but `&&` condition fails | Both return `null` |
| Not an `Order` | Type pattern does not match | Outer record pattern does not match | Both return `null` |
| Input is `null` | Type pattern does not match | Record pattern does not match | Both return `null` |

## 6. Comparison by design criteria

| Criterion | Accessor + manual mapping | Deconstruction + mapping |
| --- | --- | --- |
| Source type check | Uses `instanceof Order order` or explicit check/cast | Uses `instanceof Order(...)` |
| Component extraction | Calls individual accessors like `order.id()`, `order.total()` | Declares subpatterns matching the `record` structure |
| Nested data | Manually retrieves each object at each level | Extracts multiple levels with `Order(..., Money(...))` |
| `null` checks | Written explicitly at each level | Nested record pattern does not match `null`; components bound with `var` still need a guard if they must be non-`null` |
| Target DTO/record creation | Writes `new`, builder, or mapping method | **Still must write** `new`, builder, or mapping; deconstruction only replaces data extraction |
| Type conversion/formatting/calculation | Writes transformation logic | Writes transformation logic after extracting variables |
| Variable scope | Regular local variables or type pattern variables | Pattern variables follow **flow scoping** |
| Specific error feedback | Separate `if` steps can pinpoint the cause | Nested pattern usually only indicates "match/no match"; extra checks are needed to classify errors |
| Source type requirements | Can read from records, regular classes, JavaBeans, `Map`, other APIs | Record pattern `R(...)` only deconstructs the corresponding **record** |
| Readability | Good for long transformation logic with many branches | Concise for nested records and short conditional logic |
| Performance | Depends on accessor calls, checks, and target allocation | Still accesses components and allocates DTO if `new` is called; must be measured, not assumed faster |

**Do not choose based solely on line count.** When mapping only transfers a few record components and handles mismatch cases simply, record patterns are often easier to read. When the workflow requires many transformations, per-error checks, intermediate values, or reading from non-record classes, manual accessors or a dedicated mapper can be clearer.

## 7. Differences that easily cause bugs

### 7.1. Deconstruction does not automatically create a new object

The following expression only extracts data and uses it directly:

```java
if (source instanceof Order(var id, Money(var cents, var currency))) {
    System.out.println(id + " " + cents + " " + currency);
}
```

It **does not create** an `OrderRow`. In contrast, `return new OrderRow(id, currency, cents);` is the mapping operation and can appear in either approach.

### 7.2. `var` and `null` are not automatic "null validation"

`Order(var id, Money(var cents, var currency))` requires the `total` component to be a non-`null` `Money`, but `currency` is captured with `var` so it can be `null`. If you replace the entire subpattern with:

```java
if (source instanceof Order(var id, var total)) {
    // total can be null because this pattern does not require Money(...).
}
```

then an `Order` with `total == null` can still match. Therefore, data requirements must be specified accurately at each level. Manual mapping must also define `null` rules explicitly rather than relying on accessors themselves for validation.

### 7.3. Record patterns depend on component declaration, not arbitrary getters

A record pattern follows the **number, order, and types of components** declared in the `record`. For example, `Money(var cents, var currency)` extracts `cents` before `currency` according to the declaration. If variable names are swapped while types remain compatible, the code may compile but assign the wrong business meaning in records with multiple components of the same type. Whenever component order changes, all related patterns must be checked.

For a regular class with `getTotal()`, you cannot write `OrderLike(var id, var total)` if `OrderLike` is not a record. Accessor-based mapping continues to work with regular classes and non-record data sources.

### 7.4. Scope of pattern variables differs from regular local variables

Valid code:

```java
if (source instanceof Order(var id, Money(var cents, var currency))
        && currency != null) {
    System.out.println(id + ": " + cents);
}
```

Invalid code:

```java
// Wrong: the right-hand side of || can run when the record pattern has not matched.
if (source instanceof Order(var id, Money(var cents, var currency))
        || cents > 0) {
    System.out.println("checking");
}
```

You cannot use `cents` along a path where the pattern may have failed. When using manual accessors, you must likewise respect the scope of variables declared within each branch.

### 7.5. Deconstruction does not deep-copy data

A record is a data carrier with final components, but a component can hold a reference to a mutable object such as a `List`. Neither accessor-based extraction nor deconstruction automatically creates a **deep copy**. If the target DTO must be isolated from the source data, the mapping step must explicitly copy any required mutable structures.

### 7.6. Custom accessors can affect behavior

A record pattern retrieves component values through the record's accessor methods. When a developer-defined custom accessor can throw an exception, matching a record pattern may throw a `MatchException` wrapping the exception from the accessor. When calling accessors directly in manual mapping, how the exception propagates can differ. Therefore, you should not assume the two code snippets are **always strictly equivalent** when a record has non-standard accessors or side effects. The runnable example in Section 5 uses default accessors and does not exhibit these behaviors.

## 8. When to combine both?

In real-world code, a balanced option is to use deconstruction to extract data and keep mapping inside a dedicated method:

```java
static OrderRow toRow(Object source) {
    if (!(source instanceof Order(var id, Money(var cents, var currency)))) {
        return null;
    }
    if (currency == null) {
        return null;
    }
    return new OrderRow(id, currency, cents);
}
```

This snippet is an **illustrative method** using the same three records declared in Section 2, not a standalone Java file. The failing `if` branch returns immediately, so `id`, `cents`, and `currency` remain usable after the `if` statement under Java's flow-scoping rules.

If the mapping step grows to require currency conversion, field renaming, validation rules, specific error messages, or combining data from multiple sources, split those responsibilities into small conversion methods for easier testing. Record patterns remain useful for structural extraction, while **business mapping** should be described and tested separately.

## 9. Practice exercise and evaluation criteria

Given:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record CustomerRow(String name, String city) {}
```

Requirement: from `Object input`, create a `CustomerRow` if `input` is a `Customer`, `address` is not `null`, and `city` is non-empty; in all other cases, return `null`.

Write two methods: (a) using manual accessors; (b) using `Customer(var name, Address(var city, var street))`, then calling the target constructor. Ensure both handle the following cases identically: valid address; `null` address; `null` city; empty string city; wrong input type.

**Hint for the right condition:** `city != null && !city.isEmpty()`. If the application requires stripping whitespace, consider `city.isBlank()` (Java 11+) according to the data contract; this is an **additional** business rule, not something record patterns enforce automatically.

## 10. Key takeaways

**Record pattern deconstruction** helps identify and extract record components, especially for nested records; **mapping** defines the target model and how data is transformed. When both are needed, use deconstruction to reduce accessor boilerplate and continue constructing the DTO according to business rules. Verify equivalence with tests covering valid data, `null`, wrong types, and edge cases, rather than judging only by more concise syntax.

**Official documentation:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Java `Record` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).
