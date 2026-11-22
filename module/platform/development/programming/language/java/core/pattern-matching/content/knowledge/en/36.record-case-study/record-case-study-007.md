# Refactoring Long Accessor Chains with Record Patterns in Java 21

In Java, a domain model with multiple data layers often produces expressions like:

```java
String city = purchase.customer().profile().address().city();
```

This single-line expression contains **many implicit assumptions**: `purchase`, `customer`, `profile`, `address`, and `city` must all exist. If even one reference component is `null`, the next access can throw a `NullPointerException` (NPE). When you have to guard every level, `if` statements and intermediate variables grow long.

**Record patterns** — a finalized feature in **Java 21** — allow you to *deconstruct* a record and nested records directly inside `instanceof` or `switch`. Instead of writing multiple accessor/cast chains, you can describe the **shape of the data to match**, and then process the bound values.

This article belongs to the **Record Case Study** group, with a practical goal: converting a long accessor chain into readable code that is safe against `null` at each level, while **not changing business behavior**. The hands-on examples use Java 21+ with `record`, nested record patterns, `&&`, `when` guards, and `switch` expressions; `--enable-preview` is not required.

## 1. The Data Model That Creates Accessor Chains

Suppose an order-processing application needs to retrieve the shipping city. A purchase has a customer, a customer has a profile, a profile has an address, and an address has a city:

```text
Purchase
 ├─ orderId : String
 ├─ customer : Customer
 │   ├─ id : String
 │   └─ profile : Profile
 │       ├─ address : Address
 │       │   ├─ city : String
 │       │   └─ street : String
 │       └─ email : String
 └─ quantity : int
```

Minimal model declarations:

```java
record Address(String city, String street) {}
record Profile(Address address, String email) {}
record Customer(String id, Profile profile) {}
record Purchase(String orderId, Customer customer, int quantity) {}
```

The declarations above are **component snippets** placed in the same class in the complete program in Section 9.

With complete data, you can call:

```java
Purchase purchase = new Purchase(
        "O-7",
        new Customer(
                "C-1",
                new Profile(
                        new Address("  Ha Noi  ", "Main St"),
                        "user@example.com")),
        2);
String city = purchase.customer().profile().address().city();
System.out.println(city.strip()); // Ha Noi
```

### Does a Record Automatically Guarantee Non-Null Components?

**No.** A `record` primarily describes a data structure and automatically provides a constructor, accessors, and `equals/hashCode/toString`. Without adding validation to the constructor, the following values can still be created:

```java
new Purchase("O-1", null, 1);
new Customer("C-1", null);
new Profile(null, "mail");
new Address(null, "street");
```

This creates at least **five points to watch** when debugging: `Purchase` itself is `null`, `customer` is `null`, `profile` is `null`, `address` is `null`, and `city` is `null`. An empty string or a whitespace-only string is a different case from `null`.

**Note on immutability:** record components are `final` fields, but records are only *shallowly immutable*. For a reference-type component pointing to a mutable object, deep state can still change. In this example, nested records and `String` have no setters, so the state is simpler.

## 2. The Problem with Single-Line Accessor Chains

The shortest function, but unsafe:

```java
static String unsafeCity(Purchase purchase) {
    return purchase.customer().profile().address().city().strip();
}
```

Paths that cause an NPE:

| Abnormal Value | Access Likely to Cause NPE |
| --- | --- |
| `purchase == null` | `purchase.customer()` |
| `purchase.customer() == null` | calling `.profile()` on null customer |
| `customer.profile() == null` | calling `.address()` on null profile |
| `profile.address() == null` | calling `.city()` on null address |
| `address.city() == null` | calling `.strip()` on null city |

This is not a flaw specific to records; any method-call chain carries a similar risk when an intermediate value can be `null`.

### Do Not Simply Wrap the Entire Chain in a Catch NPE

```java
// Not recommended:
try {
    return purchase.customer().profile().address().city().strip();
} catch (NullPointerException ex) {
    return "UNKNOWN";
}
```

The code above does not explain **which level** is missing and can hide programming bugs inside user-defined accessors. You should handle known conditions with guards or invariants rather than using a broad `catch` to mask all NPEs.

## 3. First Safe Refactoring Step: Extract Variables and Check Each Layer

Before switching to record patterns, clarify the semantics of the legacy code. This example intentionally returns `"UNKNOWN"` if **any required data level is missing**, or if the city is empty/blank:

```java
static String legacyCity(Purchase purchase) {
    if (purchase == null) return "UNKNOWN";

    Customer customer = purchase.customer();
    if (customer == null) return "UNKNOWN";

    Profile profile = customer.profile();
    if (profile == null) return "UNKNOWN";

    Address address = profile.address();
    if (address == null) return "UNKNOWN";

    String city = address.city();
    if (city == null || city.isBlank()) return "UNKNOWN";

    return city.strip();
}
```

This is a **step-by-step refactoring with intermediate variables** (*snapshot variables*). It is longer than one line, but has several advantages:

1. Each access has a specific location, making it easy to set breakpoints.
2. Every `null` level is handled intentionally.
3. During each normal execution of the success path, the code calls each accessor in the chain only once.
4. The business rule for `city == null` and `city.isBlank()` is expressed explicitly.
5. If you later need to return specific messages for missing customer/profile/address, you know where to add branches.

**Important:** before comparing with the record pattern version, lock down the contract: a missing city returns `UNKNOWN`, and a city with content returns `city.strip()`. Do not accidentally turn a missing customer into an exception, or treat `"   "` as a valid city.

## 4. Replacing Deconstruction Steps with Nested Record Patterns

A record pattern can deconstruct an entire multi-layer structure:

```java
static String patternCity(Purchase purchase) {
    if (purchase instanceof Purchase(
            var orderId,
            Customer(var customerId,
                    Profile(Address(var city, var street), var email)),
            var quantity)
            && city != null && !city.isBlank()) {
        return city.strip();
    }
    return "UNKNOWN";
}
```

How to read it from outside in:

- `purchase instanceof Purchase(...)`: the selector must be a non-`null` `Purchase` object.
- The `customer` component must match `Customer(...)`; if it is `null`, the nested record pattern does not match.
- The `profile` component must match `Profile(...)`; if it is `null`, the pattern does not match.
- The `address` component must match `Address(...)`; if it is `null`, the pattern does not match.
- Upon reaching `Address(var city, var street)`, `city` and `street` are bound from the components. **`var city` can receive `null`**, so `city != null` is still needed before calling `isBlank()`.
- `&&` uses short-circuit evaluation: `!city.isBlank()` only runs if the entire nested pattern matches and `city != null`.
- If all conditions are true, it returns the city with leading and trailing whitespace stripped. All other cases return `UNKNOWN`.

Examples:

```java
patternCity(new Purchase("O", null, 1)); // UNKNOWN
patternCity(new Purchase("O",
        new Customer("C", new Profile(new Address(null, "Main"), "m")),
        1));                             // UNKNOWN
patternCity(new Purchase("O",
        new Customer("C", new Profile(new Address("  Hue  ", "Main"), "m")),
        1));                             // Hue
```

The pattern above does not require type casts like `(Customer)` or `(Profile)`. The compiler checks the record patterns, component types, and the scope of pattern variables.

### `var` in a Component Does Not Mean Dynamic Typing

In `Address(var city, var street)`, the compiler infers that `city` and `street` have type `String` from the record declaration. In `Purchase(..., var quantity)`, `quantity` has type `int`.

This does not mean `city` is guaranteed to be non-null. **Static type and nullability are two different things** for Java references.

### Why Is the Version Above Syntactically Long Yet Still Useful?

An accessor chain inherently has **four record levels**, so a corresponding nested pattern is also deep. The benefit is not necessarily fewer characters, but that **the data structure to match is described in one place**, instead of repeated access expressions. When the structure is very deep or only a single field is needed, sometimes the intermediate-variable version in Section 3 is **more readable**; do not force every chain into one large pattern.

## 5. Null Selector, Null Child Record, and Null Component: Three Different Rules

| Input/pattern | Matches? | Explanation |
| --- | --- | --- |
| `null instanceof Purchase(...)` | No | Outer record pattern does not match null |
| `Purchase("O", null, 1)` with nested `Customer(...)` | No | Child record customer is null |
| `Customer("C", null)` with nested `Profile(...)` | No | Child record profile is null |
| `Profile(null, "m")` with nested `Address(...)` | No | Child record address is null |
| `Address(null, "Main")` with `Address(var city, var street)` | Yes | `var city` is a component pattern, which can bind null |
| `Address("  ", "Main")` with `Address(var city, var street)` | Yes | Blank is a type-valid `String` |
| `switch (purchase)` missing `case null` when selector is null | Throws NPE | Pattern switch by default does not route null into `default` |

**Important distinction:** The nested record pattern `Customer(...)` requires **an existing Customer instance**. In contrast, the component pattern `var city` reads a `String` component inside an already-matched `Address`, so it can still receive `null`. Do not infer that both a record pattern and all components nested inside it are non-null.

A record pattern with an unconditional component type pattern for its declared type can also bind null under specific conditions according to the Java 21 JLS. However, in this case study, `var` and the `city != null` guard are used to express intent most clearly.

### Where Should Null Checks Be Placed?

If the goal is **only needing a city with content**, an `instanceof` nested record pattern combined with `&& city != null` is sufficient.

If the goal is **knowing why data is missing**, you must distinguish each level—such as returning `MISSING_CUSTOMER`, `MISSING_PROFILE`, or `MISSING_ADDRESS`—using specialized cases as shown in the next section.

## 6. Using Pattern Switch to Diagnose and Classify Deeply Nested Data

An application may need **specific error codes** instead of `UNKNOWN` for all missing data. A `switch expression` with record patterns and `when` helps express the checking order clearly:

```java
static String routingDecision(Purchase purchase) {
    return switch (purchase) {
        case null -> "MISSING_PURCHASE";

        case Purchase(var id, var customer, var qty)
                when id == null || id.isBlank() -> "INVALID_ORDER_ID";

        case Purchase(var id, var customer, var qty)
                when customer == null -> "MISSING_CUSTOMER";

        case Purchase(var id, Customer(var cid, var profile), var qty)
                when profile == null -> "MISSING_PROFILE";

        case Purchase(var id,
                      Customer(var cid, Profile(var address, var email)),
                      var qty)
                when address == null -> "MISSING_ADDRESS";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when city == null -> "MISSING_CITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when city.isBlank() -> "BLANK_CITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when qty <= 0 -> "INVALID_QUANTITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty) ->
                "ROUTE " + id + " -> " + city.strip() + " qty=" + qty;

        case Purchase(var id, var customer, var qty) ->
                "UNSUPPORTED_STRUCTURE";
    };
}
```

This is a member method in the same class containing the article's records; the full program is in Section 9.

### Explaining the Order

1. `case null` handles a null **Purchase selector**. It does not handle components inside a real Purchase.
2. `INVALID_ORDER_ID` checks `id == null || id.isBlank()`; thanks to short-circuiting, `isBlank()` does not run if the ID is null.
3. `MISSING_CUSTOMER` captures the component with `var customer` so it can detect a null customer.
4. `MISSING_PROFILE` requires Customer to exist, then checks for a null profile component.
5. `MISSING_ADDRESS` requires Customer and Profile to exist, then checks for a null address.
6. `MISSING_CITY` requires the three nested records to exist, then checks for a null city component.
7. `BLANK_CITY` uses `city.isBlank()`. The code is safe in this order because `city == null` cases have already been handled by the preceding case. If these two cases were swapped, an input with a null city could throw an NPE in the guard.
8. `INVALID_QUANTITY` is only evaluated after both the address and city have passed the previous steps. This is the **error reporting priority order** chosen by the example.
9. The `ROUTE` case matches complete data, has no guard, and produces the result string.
10. The `UNSUPPORTED_STRUCTURE` case is a structural fallback branch at the end. Specified scenarios already have dedicated cases; this branch protects if the structure changes beyond assumptions. It must **not** be used to skip testing null levels that need to be handled.

**Do not turn every case into an overly long nested structure in production:** the example intentionally shows depth to teach the mechanism. When business logic grows large, consider functions that validate each level and then `switch` on a **normalized result type**.

### When Multiple Conditions Fail Together, Which Error Takes Priority?

With `new Purchase(null, null, 0)`, the dispatcher returns `INVALID_ORDER_ID` because that case comes first. If the product wants to return `MISSING_CUSTOMER` or aggregate multiple errors, the validation logic must be redesigned. Java does not automatically pick the "most severe error."

On the other hand, `legacyCity` and `patternCity` **only extract the city**; they do not check `orderId` or `quantity`. Therefore, when `orderId == null` but the address is complete, both extraction functions can still return the city, while `routingDecision` returns `INVALID_ORDER_ID`. These are **two different responsibilities**, not conflicting results.

## 7. Dominance and Flow Scoping When Using Nested Patterns

### A General Case Can Shadow a Deeper Case

Intentionally invalid pattern:

```java
// Does not compile: the preceding case Purchase(var customer) is too broad.
return switch (purchase) {
    case null -> "null";
    case Purchase(var id, var customer, var qty) -> "general";
    case Purchase(var id, Customer(var cid, var profile), var qty)
            when profile == null -> "missing profile";
};
```

The unguarded `Purchase(var id, var customer, var qty)` case matches every non-null Purchase, including values that the specialized case after it could handle. The Java 21 compiler reports an error:

```text
error: this case label is dominated by a preceding case label
```

**Fix:** place cases with specific guards/structures first, followed by broad unguarded cases, as in `routingDecision`.

`when` guards do not guarantee that all business conditions are proven by the compiler. When reordering cases, you must run regression tests with null and blank values at every level; a switch that compiles can still throw an NPE inside a guard if the null-check order is wrong.

### Flow Scoping Allows Using Pattern Variables on the Right-Hand Side of `&&`

```java
static boolean deliverable(Purchase purchase) {
    return purchase instanceof Purchase(
            var orderId,
            Customer(var customerId,
                    Profile(Address(var city, var street), var email)),
            var quantity)
            && city != null && !city.isBlank() && quantity > 0;
}
```

- Only when the `instanceof` part matches is the right-hand side of `&&` evaluated.
- `city` and `quantity` are bound within the scope permitted by the compiler.
- `city != null` guards `city.isBlank()`.
- `quantity` is an `int`; its value can be 0 or negative if the constructor does not validate it.

Pattern variables **do not automatically appear in every branch** of the program. Writing `input instanceof ... || city.isBlank()` to use the variable when the match fails is a scoping/definite-matching error. Always reason according to the short-circuit evaluation direction of `&&`/`||`.

## 8. When Should You Not Replace an Accessor Chain with a Record Pattern?

Nested record patterns provide great value when:

- The domain is genuinely represented by nested records.
- You need to inspect a **multi-layer structure** to decide a branch.
- You want to **extract multiple components** in a single match.
- The code uses Java 21+ and does not need lower source-level compatibility.
- The accessors are simple or their behavior is well understood.

However, do not refactor mechanically in the following situations.

### 8.1. Depth Hurts Readability

`Purchase(Customer(Profile(Address(...))))` easily becomes parenthesis-heavy with many layers and components. When the goal is only to get a single city, the snapshot variables version in Section 3 can be **clearer**, especially when breakpoints or specific error messages are needed. You can create a projection function like `shippingCity(Purchase purchase)` and reuse it rather than copying a deep pattern across multiple services.

### 8.2. Non-Record Classes

Record patterns are deconstruction syntax for matching **record classes**; Java 21 does not automatically provide record deconstruction for arbitrary POJOs/beans. If the model uses traditional classes with `getCustomer()`, you can refactor to intermediate variables and null checks or convert the model to records when there is a sound reason to do so. Do not convert all ORM entities into records just to shorten one accessor chain.

### 8.3. Accessors with Side Effects or That May Throw Exceptions

Records allow **explicit accessor declarations**. When a record pattern deconstructs components, the relevant accessors are invoked to retrieve the data; an accessor may execute custom logic. Consequently, refactoring can change the **number of calls or call order**, especially when a `switch` tests multiple cases with similar structures.

A standalone example run on Java 21:

```java
public class RecordAccessorEffectsDemo {
    record Box(String value) {
        static int accesses;

        @Override
        public String value() {
            accesses++;
            return value;
        }
    }

    record Wrapper(Box box) {}

    public static void main(String[] args) {
        Object input = new Wrapper(new Box("ready"));
        if (input instanceof Wrapper(Box(var value))) {
            System.out.println("matched=" + value);
        }
        System.out.println("accesses=" + Box.accesses);
    }
}
```

Run with:

```bash
javac --release 21 -Xlint:all -Werror RecordAccessorEffectsDemo.java
java RecordAccessorEffectsDemo
```

**Verified stdout:**

```text
matched=ready
accesses=1
```

This example proves that deconstruction invoked the **customized `Box.value()` accessor**. You should not infer from this single run that every nested pattern with multiple cases always calls each accessor exactly once. If an accessor has side effects or depends on external state, you must verify behavior before and after refactoring with targeted tests.

### 8.4. APIs That Need to Distinguish Missing Data from Invalid Data

`patternCity` returns `UNKNOWN` when any level is missing. If an API needs to distinguish a missing customer from a blank city, it should return a **structured result type** (e.g., a sealed result with each error kind) or use `routingDecision`, rather than collapsing all errors into a single string.

### 8.5. Java Compatibility

`record` declarations became final in Java 16, whereas **record patterns** became final in Java 21 (JEP 440). The code in this article does not run under `--release 17`. If you must support Java 17, you can still keep records and use snapshot accessors with `instanceof` type patterns; there is no need to use preview syntax from intermediate releases.

## 9. Complete Java 21 Program: Comparing Before and After Refactoring

Save the file as **`RecordAccessorRefactorDemo.java`**. The program tests 14 cases, including null at each level, empty/blank city, invalid ID, boundary quantities, and valid data. Three functions are verified: `legacyCity` (level-by-level reads), `patternCity` (nested record pattern), and `routingDecision` (pattern switch with guards).

```java
public class RecordAccessorRefactorDemo {
    record Address(String city, String street) {}
    record Profile(Address address, String email) {}
    record Customer(String id, Profile profile) {}
    record Purchase(String orderId, Customer customer, int quantity) {}
    record Sample(String label, Purchase input, String city, String route) {}

    private static int checks;

    static Purchase sample(String orderId, String city, int quantity) {
        return new Purchase(orderId,
                new Customer("C-1",
                        new Profile(new Address(city, "Main St"), "user@example.com")),
                quantity);
    }

    static String legacyCity(Purchase purchase) {
        if (purchase == null) return "UNKNOWN";
        Customer customer = purchase.customer();
        if (customer == null) return "UNKNOWN";
        Profile profile = customer.profile();
        if (profile == null) return "UNKNOWN";
        Address address = profile.address();
        if (address == null) return "UNKNOWN";
        String city = address.city();
        if (city == null || city.isBlank()) return "UNKNOWN";
        return city.strip();
    }

    static String patternCity(Purchase purchase) {
        if (purchase instanceof Purchase(
                var orderId,
                Customer(var customerId,
                        Profile(Address(var city, var street), var email)),
                var quantity)
                && city != null && !city.isBlank()) {
            return city.strip();
        }
        return "UNKNOWN";
    }

    static String routingDecision(Purchase purchase) {
        return switch (purchase) {
            case null -> "MISSING_PURCHASE";
            case Purchase(var id, var customer, var qty)
                    when id == null || id.isBlank() -> "INVALID_ORDER_ID";
            case Purchase(var id, var customer, var qty)
                    when customer == null -> "MISSING_CUSTOMER";
            case Purchase(var id, Customer(var cid, var profile), var qty)
                    when profile == null -> "MISSING_PROFILE";
            case Purchase(var id,
                          Customer(var cid, Profile(var address, var email)),
                          var qty)
                    when address == null -> "MISSING_ADDRESS";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when city == null -> "MISSING_CITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when city.isBlank() -> "BLANK_CITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when qty <= 0 -> "INVALID_QUANTITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty) ->
                    "ROUTE " + id + " -> " + city.strip() + " qty=" + qty;
            case Purchase(var id, var customer, var qty) -> "UNSUPPORTED_STRUCTURE";
        };
    }

    static String unsafeCity(Purchase purchase) {
        return purchase.customer().profile().address().city().strip();
    }

    private static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        Sample[] cases = {
            new Sample("null-selector", null, "UNKNOWN", "MISSING_PURCHASE"),
            new Sample("null-id", sample(null, "Hue", 1), "Hue", "INVALID_ORDER_ID"),
            new Sample("blank-id", sample("  ", "Hue", 1), "Hue", "INVALID_ORDER_ID"),
            new Sample("null-customer", new Purchase("O-1", null, 1),
                    "UNKNOWN", "MISSING_CUSTOMER"),
            new Sample("null-profile", new Purchase("O-2", new Customer("C", null), 1),
                    "UNKNOWN", "MISSING_PROFILE"),
            new Sample("null-address", new Purchase("O-3",
                    new Customer("C", new Profile(null, "mail")), 1),
                    "UNKNOWN", "MISSING_ADDRESS"),
            new Sample("null-city", sample("O-4", null, 1),
                    "UNKNOWN", "MISSING_CITY"),
            new Sample("empty-city", sample("O-5", "", 1),
                    "UNKNOWN", "BLANK_CITY"),
            new Sample("blank-city", sample("O-6", " \t ", 1),
                    "UNKNOWN", "BLANK_CITY"),
            new Sample("valid-city", sample("O-7", "  Ha Noi  ", 2),
                    "Ha Noi", "ROUTE O-7 -> Ha Noi qty=2"),
            new Sample("valid-other-city", sample("O-8", "Da Nang", 1),
                    "Da Nang", "ROUTE O-8 -> Da Nang qty=1"),
            new Sample("qty-zero", sample("O-9", "Hue", 0),
                    "Hue", "INVALID_QUANTITY"),
            new Sample("qty-negative", sample("O-10", "Hue", -1),
                    "Hue", "INVALID_QUANTITY"),
            new Sample("qty-one", sample("O-11", "Hue", 1),
                    "Hue", "ROUTE O-11 -> Hue qty=1")
        };

        for (Sample test : cases) {
            expect("legacy-" + test.label(), test.city(), legacyCity(test.input()));
            expect("pattern-" + test.label(), test.city(), patternCity(test.input()));
            expect("route-" + test.label(), test.route(), routingDecision(test.input()));
        }

        System.out.println("PASS cases=" + cases.length);
        System.out.println("PASS assertions=" + checks);
        System.out.println("city=" + patternCity(sample("O-7", "  Ha Noi  ", 2)));
        System.out.println("route=" + routingDecision(sample("O-7", "  Ha Noi  ", 2)));
        System.out.println("nested-null=" + routingDecision(new Purchase(
                "O-2", new Customer("C", null), 1)));
        System.out.println("selector-null=" + routingDecision(null));

        try {
            unsafeCity(new Purchase("NPE", null, 1));
            throw new AssertionError("Expected NPE on null customer");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-chain=NPE");
        }
        try {
            unsafeCity(sample("NPE", null, 1));
            throw new AssertionError("Expected NPE on null leaf city");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-leaf=NPE");
        }
    }
}
```

Compile and run on JDK 21 or a newer compiler supporting `--release 21`:

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 RecordAccessorRefactorDemo.java
java RecordAccessorRefactorDemo
```

**Verified exact stdout:**

```text
PASS cases=14
PASS assertions=42
city=Ha Noi
route=ROUTE O-7 -> Ha Noi qty=2
nested-null=MISSING_PROFILE
selector-null=MISSING_PURCHASE
unsafe-chain=NPE
unsafe-leaf=NPE
```

### Why Does It Print PASS?

Each `Sample` has three independently defined expected outcomes:

1. `legacyCity(test.input())` must equal `test.city()`.
2. `patternCity(test.input())` must also equal `test.city()`.
3. `routingDecision(test.input())` must equal `test.route()`.

The `expect` function throws an `AssertionError` if any actual result differs from the oracle. There are **14 Samples × 3 assertions = 42 assertions**. The PASS lines only appear after all of them succeed.

The code also intentionally calls `unsafeCity` in two different failure cases: a missing customer record and a missing city component. The two NPEs are caught to demonstrate the cause; **broadly catching NPEs in production code is not recommended**.

### Some Notable Cases

| Case | Expected from Both City Functions | Expected from routingDecision |
| --- | --- | --- |
| `purchase == null` | `UNKNOWN` | `MISSING_PURCHASE` |
| `orderId == null`, valid address | City name | `INVALID_ORDER_ID` |
| `customer == null` | `UNKNOWN` | `MISSING_CUSTOMER` |
| `profile == null` | `UNKNOWN` | `MISSING_PROFILE` |
| `address == null` | `UNKNOWN` | `MISSING_ADDRESS` |
| `city == null` | `UNKNOWN` | `MISSING_CITY` |
| `city == ""` or blank | `UNKNOWN` | `BLANK_CITY` |
| `city == "  Ha Noi  "` | `Ha Noi` | `ROUTE O-7 -> Ha Noi qty=2` |
| `quantity == 0`, valid city | City name | `INVALID_QUANTITY` |

The table shows why it is necessary to distinguish **data extraction** from **full request validation** when refactoring. Two methods can use the same record patterns while serving two different contracts.

## 10. When Should You Put Null Checks in the Record Constructor?

If the business domain **never allows** a `Purchase` without a customer, profile, or address, you can place invariants at data creation time:

```java
record StrictCustomer(String id, Profile profile) {
    StrictCustomer {
        java.util.Objects.requireNonNull(profile, "profile");
    }
}

record StrictPurchase(String orderId, StrictCustomer customer, int quantity) {
    StrictPurchase {
        java.util.Objects.requireNonNull(customer, "customer");
    }
}
```

This is a **structural example to be placed in a class that already defines `Profile`**, not a standalone Java file. For models that allow null such as "unfilled" data, adding `requireNonNull` can **change the contract**, so do not apply it before understanding the data source.

There are two valid choices:

- **Nullable domain:** null is a meaningful state; keep records nullable and handle it in the parser/dispatcher/service.
- **Validated domain:** a missing component is an input error; reject immediately in the constructor/factory, giving downstream layers stronger invariants.

Do not simultaneously assume null is valid in stored data while assuming every nested pattern will match and every accessor is always safe.

## 11. Practical Refactoring Workflow

When encountering a long accessor chain in live code, you can follow this sequence:

1. **Determine the business outcome.** Is the chain used for display, routing, logging, or validation? Should a null city return a default, throw an error, or be skipped?
2. **Diagram each level.** Note the static types `Purchase → Customer → Profile → Address → String` and which levels can be null.
3. **Split the expression with intermediate variables** like `legacyCity` in Section 3. This makes the dereference order clear and creates an easily testable baseline.
4. **Write oracle tests first.** At a minimum, test a null selector, each child record as null, a null leaf component, a blank string, and valid data.
5. **Check the Java version.** Nested record patterns are final as of Java 21; for source 17, stop at intermediate variables or accessor helpers.
6. **Replace with a record pattern if it genuinely improves readability.** Deconstruct records where appropriate; do not force-deconstruct unnecessary components just to use new syntax.
7. **Add guards for nullable components.** `var city` does not guarantee non-null; use `city != null && !city.isBlank()` in the right order.
8. **Keep validation rules outside the accessor chain separate.** Empty IDs, non-positive quantities, and shipping permissions should not be accidentally merged into a null guard if they have different error codes.
9. **Check accessor behavior.** If an accessor is overridden, has side effects, throws, or depends on state, compare the call count and call order before and after.
10. **Run the compiler and regression tests.** Check `when` dominance, null selectors, null components, extraction results, and routing results. In larger projects, also use JUnit and a coverage tool.
11. **Review readability.** If the nested pattern is much larger than the old code, you can keep snapshot accessors or create a domain projection method instead of shortening at all costs.

A good refactoring must **reduce the risk of bugs and make intent clearer**. Switching from an accessor chain to a pattern is not an end in itself.

## 12. Common Mistakes When Refactoring Accessor Chains

1. **Assuming `instanceof` means every level is non-null.** Only the record object matched at that level must be non-null; a component like `var city` can still be null.
2. **Confusing null at the selector with null at a component.** `null instanceof Purchase(...)` is false, whereas `Purchase(..., Address(null,...),...)` can match the pattern and bind a null city.
3. **Removing the leaf null check.** `city.strip()` will throw an NPE if city is null, regardless of whether parent records exist.
4. **Placing the `city.isBlank()` guard before `city == null`.** In a `switch`, a guard can throw an NPE before Java evaluates the next case.
5. **Using `||` in the wrong direction with pattern variables.** `input instanceof Purchase(...) || city.isBlank()` does not guarantee city is bound when the right-hand side runs; review flow-scoping rules.
6. **Placing a broad case before a deep case with `when`.** An unguarded broad case can shadow a specialized case, causing a compiler dominated-case error.
7. **Keeping overly deep, hard-to-read pattern syntax.** Nested layers of parentheses make maintenance difficult if only one field is needed. Use snapshot variables or a projection function instead.
8. **Using record patterns with non-record POJOs.** Java 21 does not automatically deconstruct arbitrary classes; use accessors or a suitable model.
9. **Assuming record accessors are always pure.** Accessors can be overridden to add code; changing match structure can change behavior when an accessor has side effects.
10. **Changing error-reporting policy during refactoring.** Returning `UNKNOWN` for all missing data differs from separate `MISSING_PROFILE`/`MISSING_ADDRESS` codes.
11. **Assuming the default record constructor forbids null.** A record can hold null reference components if there are no invariants.
12. **Using `catch NullPointerException` to mask any failing chain.** This easily swallows programming bugs unrelated to missing data.
13. **Overusing `Optional` just to avoid null without a clear contract.** `Optional.ofNullable` can help represent absence, but long `map` chains do not automatically solve the need to distinguish multiple missing causes.
14. **Running Java 21 record patterns under `--release 17`.** `record` can be used in Java 17, but record patterns require Java 21 as a finalized feature.

## 13. Self-Practice Exercises

**Exercise 1.** Given `new Purchase("O", null, 1)`, why does the pattern `Purchase(var id, Customer(...), var quantity)` not match?

*Answer:* The customer component is null, and the nested record pattern `Customer(...)` requires a non-null Customer instance to deconstruct. The pattern `Purchase(var id, var customer, var quantity)` can still match and bind `customer == null`.

**Exercise 2.** Given `new Address(null, "Main")`, can `Address(var city, var street)` match?

*Answer:* Yes. `var city` is a component pattern that receives the value of the declared component type and can bind null. If you subsequently call `city.isBlank()`, you must check for null first.

**Exercise 3.** Why does `patternCity` use `&& city != null && !city.isBlank()` instead of calling `city.isBlank()` right after the record pattern?

*Answer:* Because the pattern can succeed when the city component is null; `&&` ensures `isBlank()` only runs after `city != null` is true.

**Exercise 4.** If both `orderId == null` and `customer == null`, what does `routingDecision` return?

*Answer:* `INVALID_ORDER_ID`, because the ID-checking case comes before the customer-checking case. This is the error-priority rule chosen by the author; if the API wants a different priority, reorder the cases and tests.

**Exercise 5.** Should you use `Purchase(Customer(Profile(Address(var city,...))))` in every function that retrieves the city?

*Answer:* No. If the pattern is too deep or the code only needs one value, using snapshot variables or a domain projection helper is often easier to maintain. Patterns are suitable when you want to express structure and match conditions clearly.

**Exercise 6.** Why can a refactoring change behavior if a record accessor is overridden?

*Answer:* Deconstruction invokes accessors to retrieve components. If an accessor has side effects, performs I/O, or returns state-dependent values, the call count/order in a pattern switch may differ from the old accessor chain. You must test and review those places.

**Exercise 7.** When a project builds with `--release 17`, what approach for refactoring an accessor chain is feasible without enabling preview?

*Answer:* Keep `record` and use accessors with intermediate variables/null checks, or create a helper/composite accessor according to the contract. Record patterns became final in Java 21, so they cannot be used directly at source level 17.

**Exercise 8.** If you need to return both the city and the customer ID, what advantage does a record pattern have?

*Answer:* It can bind `customerId` and `city` in the same pattern after the nested records match, without calling multiple accessors again; you still need to check nullable components and business rules. When there are many fields/complex branches, consider a dedicated result record rather than an overly long pattern.

## 14. Official Documentation

- [JEP 395 – Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 – Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 – Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 – Patterns `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 – Records `8.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java Language Specification 21 – Scope of pattern variables `6.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
