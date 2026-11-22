# Evaluating Nested Pattern Depth: A Record Case Study in Java 21+

## 1. Problem Statement

**Nested record patterns** allow you to check and extract data from a record containing other records, instead of writing multiple manual `instanceof` checks, casts, and accessor calls. For example, purchase order data is structured as follows:

```text
Purchase
├── reference: String
├── customer: Customer
│   ├── id: String
│   └── address: Address
│       ├── city: City
│       │   └── name: String
│       └── street: String
└── cents: long
```

To extract `City.name`, Java 21 allows writing:

```java
// Illustrative snippet inside a method taking Object value.
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(City(var name), var street)),
        var cents)) {
    System.out.println(ref + ":" + id + ":" + name);
}
```

This syntax is more concise than multi-step accessors, but **fewer lines of code do not automatically mean better maintainability**. As the model grows deeper, a single expression takes on multiple responsibilities at once:

- Verifying that each level has the expected record type.
- Binding components to variables.
- Handling `null` in the root record, child records, and component values.
- Evaluating business guards.
- Depending on the count, order, and types of components across multiple records.
- Helping readers identify which level caused a `non-match` when debugging.

**Goal:** learn how to **evaluate nested pattern depth using measurable criteria**, experiment with the same data at depths 1, 2, 3, and 4; compare against staged access, and determine when to split a deep pattern.

This article uses **finalized record patterns from Java 21** (JEP 440) and type patterns/flow scoping of `instanceof` (JEP 394). `record` declarations have been final since Java 16 (JEP 395). The main code runs on **JDK 21+** without `--enable-preview`.

## 2. Depth Measurement Conventions: Define Clearly Before Comparing

There is no universal "best depth" metric mandated by the Java Language Specification for source code quality. Therefore, we need to **define a consistent set of conventions for this evaluation**.

In this article:

- **D — Max record nesting depth:** the number of record patterns on the deepest nesting path; the outermost record counts as **1**. A type pattern `City c` does not count as a record pattern `City(...)`.
- **R — Record-pattern nodes:** the total number of occurrences of `RecordType(...)` constructs in the expression.
- **V — Bound variables:** the number of variables bound via `var name` or a type pattern, regardless of whether the variable is used afterward.
- **N — Required nested-record links:** the number of child-record links that must exist and match to traverse the deepest nesting path. For a linear chain of records like the example, `N = D - 1`.
- **G — Guard predicates:** the number of independent Boolean conditions intentionally written outside the record pattern to check business values.
- **S — Schema coupling points:** locations where the source directly depends on a record's components and must be reviewed if the record changes; in this article, determined by each record-pattern node and extracted variable, without inferring the number of files to modify.

**Example:**

```java
Purchase(var ref,
    Customer(var id,
        Address(
            City(var name),
            var street)),
    var cents)
```

Counting with the conventions above:

- `D = 4` because of the chain `Purchase → Customer → Address → City`.
- `R = 4` record-pattern nodes.
- `V = 5` variables: `ref`, `id`, `name`, `street`, `cents`.
- `N = 3` required links: `Purchase.customer`, `Customer.address`, and `Address.city`.
- `G = 0` when considering only the record pattern; **`G = 3`** when combined with the guard `name != null && !name.isBlank() && cents > 0`.

`String name` is a **regular component**, not an additional record pattern, because `City(var name)` is already the final record node; no extra level is counted for `var name`.

**Important:** for a pattern tree with multiple nested branches, `R` can be greater than `D`. Do not assume the two metrics are equal; in this case study there is only one deep nesting path, so they happen to match.

## 3. Four Depths on the Same Record Model

Data type declarations:

```java
record City(String name) {}
record Address(City city, String street) {}
record Customer(String id, Address address) {}
record Purchase(String reference, Customer customer, long cents) {}
```

These are **illustrative records**; the full runnable program is in Section 7. To compare null and non-match cases, the sample model **does not enforce validation in constructors**; thus it intentionally allows null components or blank strings. For a production domain model, enforce invariants in the appropriate constructor/factory.

Defining a valid object:

```java
Object ok = new Purchase("P-1",
        new Customer("C-1", new Address(new City("Hue"), "Main")),
        2500);
```

### 3.1. Depth 1: Deconstructing Only Purchase

```java
if (value instanceof Purchase(var ref, var customer, var cents)) {
    // D = 1, R = 1; customer can be null.
}
```

Here we check the root record `Purchase` and extract **the entire `customer` component** without requiring it to be non-null. If `new Purchase("P-2", null, 2500)`, the pattern **still matches** because `var customer` can bind null.

Suitable when the code only needs `reference` or `cents` without needing to understand the customer structure. Nesting more records just because it is possible adds unnecessary coupling.

### 3.2. Depth 2: Purchase → Customer

```java
if (value instanceof Purchase(
        var ref, Customer(var id, var address), var cents)) {
    // D = 2; Customer(...) must match.
}
```

Key difference: `customer == null` now causes the entire record pattern **not to match**, because `Customer(...)` is a nested pattern requiring an actual `Customer` object.

`address` can be null because it is extracted with `var address`, not `Address(...)`. If only the customer ID is needed, this depth is sufficient.

### 3.3. Depth 3: Purchase → Customer → Address

```java
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(var city, var street)),
        var cents)) {
    // D = 3; Address(...) must exist.
}
```

`Customer.address == null` causes the pattern not to match. However, **`Address.city == null` can still match** because `var city` is used rather than `City(...)`.

Here the logic depends on the component order of three records. If a `City` value is needed as a value object with its own behavior, you can keep `var city` instead of nesting further.

### 3.4. Depth 4: Purchase → Customer → Address → City

```java
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(City(var name), var street)),
        var cents)
        && name != null && !name.isBlank() && cents > 0) {
    // D = 4, R = 4, V = 5, N = 3, G = 3.
}
```

This case requires **all three child records to exist**, then checks two additional business requirements: `City.name` must not be blank and the amount `cents` must be positive.

`City(var name)` **can still match `new City(null)`**, because `var name` accepts null; however, the condition `name != null` rejects it after deconstruction succeeds. Do not conclude that every `false` result of `instanceof ... && guard` means the pattern failed structurally.

The `&&` operators use short-circuit evaluation: `!name.isBlank()` is only called when `name != null`, avoiding a `NullPointerException`.

### 3.5. Metrics Table for the Four Versions

| Level | Pattern path | D | R | V | N | G |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `Purchase(...)` | 1 | 1 | 3 | 0 | 0 |
| 2 | `Purchase(...Customer(...))` | 2 | 2 | 4 | 1 | 0 |
| 3 | `Purchase(...Customer(...Address(...)))` | 3 | 3 | 5 | 2 | 0 |
| 4 | `Purchase(...Customer(...Address(City(...))))` with guard | 4 | 4 | 5 | 3 | 3 |

This table applies to **one specific code sample per level**, not a universal Java quality score. In another domain, two patterns with the same `D=4` can still differ greatly in branch count, type name clarity, guard length, data access cost, and how much must change as the model evolves.

## 4. Why Increasing Depth Changes Null Behavior

In record patterns, you must distinguish **null at the selector**, **null at a position with a nested record pattern**, and **null in a component bound by `var`**.

Example data:

```java
Object noCustomer = new Purchase("P-2", null, 2500);
Object noCity = new Purchase("P-4",
        new Customer("C-4", new Address(null, "Main")), 2500);
```

Results by level:

| Input | Level 1 pattern | Level 2 | Level 3 | Level 4 |
| --- | --- | --- | --- | --- |
| Complete `Purchase` | Match | Match | Match | Match if guard passes |
| `Purchase.customer == null` | **Match**, `var customer = null` | No match | No match | No match |
| `Customer.address == null` | Match | **Match**, `var address = null` | No match | No match |
| `Address.city == null` | Match | Match | **Match**, `var city = null` | No match |
| `City.name == null` | Match | Match | Match | **Pattern matches**, guard fails |
| `City.name == " "` | Match | Match | Match | Pattern matches, `isBlank` guard fails |
| `cents == 0` | Match | Match | Match | Pattern matches, `cents > 0` guard fails |
| Root `value == null` | No match | No match | No match | No match |

**Takeaway:** each time you replace `var component` with `RecordType(...)`, you add a **structural condition**. Increasing depth is not merely adding syntax to extract fields; it can change which inputs are accepted and which are rejected.

In a real application, decide explicitly **which objects are allowed to be missing**. If a missing address is valid data, do not use a pattern nested down to `Address(...)` in a branch that still intends to accept missing addresses. You can split branches or use a model that intentionally represents missing state.

## 5. When Is High Depth Beneficial?

A nested record pattern is worth using when it **matches the exact structure required by the business branch**:

- The set of records is clearly designed and relatively stable.
- The branch needs deep components and processes them immediately within a short scope.
- A non-match at any level **carries the same meaning**, such as "not an order with a complete shipping address".
- There are few guards, few bound variables, and type/component names carry domain meaning.
- Data has already been normalized at the boundary, so detailed per-level errors do not need to be reported at the match site.

For example, a small data transformation function can directly use level 4 to extract `City.name` if missing any level leads to a single `"NO_MATCH"` outcome.

Conversely, if the business logic requires **distinct messages** for "missing customer", "missing address", "missing city", and "empty city name", a level-4 expression returning a Boolean provides **too little information** for debugging/validation. Split the steps or use a validation result type that carries reasons.

## 6. Evaluation Criteria Beyond D

### 6.1. Structure: D, R, V, N, G

Use the table in Section 3 as a baseline. When `D` increases without `V` increasing, readability can still drop due to extra parentheses and potential failure points. When `G` increases, check whether the logic is still "structural matching" or has mixed many **business rules** into the expression.

In the level-4 example, `R=4` and `N=3`: three child records are required to exist. `G=3` by counting atomic conditions (not counting parentheses, nor treating every `&&` as an extra level).

### 6.2. Readability: How Long Does It Take a Reader to Explain It?

Show a reviewer the level-4 expression and ask:

1. If `customer == null`, what does the expression evaluate to?
2. How does `city == null` (the `City` object) differ from `city.name() == null`?
3. Does `street == null` cause the expression not to match?
4. Is `cents <= 0` a structural failure or a guard failure?
5. Where can the variable `name` be used under flow scoping?
6. Reordering which components could cause a variable to receive the wrong meaning?

If answers are inconsistent, consider splitting the pattern, renaming variables, or moving part of the validation into a factory/constructor.

### 6.3. Schema Coupling: When a Record Changes Shape

Record patterns are written according to **component count, order, and types**, not accessor names. If you change:

```java
record Address(City city, String street) {}
```

to:

```java
record Address(City city, String street, String postalCode) {}
```

then the old pattern `Address(City(var name), var street)` **no longer has the right number of components**. The compiler reports an error and forces an update. This is a benefit for detecting changes, and also a **maintenance cost** of deconstructing multiple levels directly.

If you only need `City.name`, consider a meaningful domain method such as `customer.cityName()` or staged access, instead of forcing every caller to know the exact components of `Address`.

**Note:** When two components of the same type `String` are swapped in order, the code may sometimes **still compile** with wrong logic. The compiler does not replace unit tests and schema migration reviews.

### 6.4. Debuggability: Distinguishing Non-Match Causes

A level-4 `instanceof` returns only one Boolean for the entire structure. It does not tell you which child record was null or which guard failed.

Split it into clearly named steps that record a reason, or use a `switch` with specific cases and fallbacks:

```java
// Illustrative method inside a class with records Purchase, Customer, Address, City.
static String classify(Object value) {
    return switch (value) {
        case Purchase(var ref,
                Customer(var id, Address(City(var name), var street)),
                var cents)
                when name != null && !name.isBlank() && cents > 0 ->
                "complete:" + ref;
        case Purchase p -> "incomplete-purchase";
        case null -> "missing-root";
        default -> "wrong-type";
    };
}
```

Case order is intentional: the specific case with `when` comes before the general `case Purchase p`. If reversed, the specific case could be **dominated**.

This method still only gives the general reason `incomplete-purchase`. To diagnose the exact level, see `diagnose` in the complete program.

### 6.5. Testability: Same Inputs, Two Implementations

Do not measure only line count. A good experiment writes:

- **Nested implementation:** using depth 4 directly.
- **Staged implementation:** checking `Purchase`, `Customer`, `Address`, `City` step by step, then handling `name` and `cents`.

Run the same input suite and compare **semantic results**. If the two implementations return different results, resolve differences in guards, null policy, or evaluation order before concluding which one is easier to read.

## 7. Complete Java 21 Program: Depths 1–4 and Staged Comparison

Create the file **`NestedPatternDepthDemo.java`**:

```java
public class NestedPatternDepthDemo {
    record City(String name) {}
    record Address(City city, String street) {}
    record Customer(String id, Address address) {}
    record Purchase(String reference, Customer customer, long cents) {}

    static String depth1(Object value) {
        if (value instanceof Purchase(var ref, var customer, var cents)) {
            return "d1:" + ref + ":"
                    + (customer == null ? "missing" : "present");
        }
        return "d1:no-match";
    }

    static String depth2(Object value) {
        if (value instanceof Purchase(
                var ref, Customer(var id, var address), var cents)) {
            return "d2:" + ref + ":" + id;
        }
        return "d2:no-match";
    }

    static String depth3(Object value) {
        if (value instanceof Purchase(var ref,
                Customer(var id, Address(var city, var street)), var cents)) {
            return "d3:" + ref + ":" + id + ":"
                    + (city == null ? "missing" : "present");
        }
        return "d3:no-match";
    }

    static String depth4(Object value) {
        if (value instanceof Purchase(var ref,
                Customer(var id, Address(City(var name), var street)), var cents)
                && name != null && !name.isBlank() && cents > 0) {
            return "d4:" + ref + ":" + id + ":" + name + ":" + cents;
        }
        return "d4:no-match";
    }

    static String staged(Object value) {
        if (!(value instanceof Purchase p)) return "step:no-match";

        Customer customer = p.customer();
        if (customer == null) return "step:no-match";

        Address address = customer.address();
        if (address == null) return "step:no-match";

        City city = address.city();
        if (city == null) return "step:no-match";

        String name = city.name();
        if (name == null || name.isBlank() || p.cents() <= 0)
            return "step:no-match";

        return "step:" + p.reference() + ":" + customer.id()
                + ":" + name + ":" + p.cents();
    }

    static String diagnose(Object value) {
        if (value == null) return "root-null";
        if (!(value instanceof Purchase p)) return "wrong-root";
        if (p.customer() == null) return "customer-null";
        if (p.customer().address() == null) return "address-null";
        if (p.customer().address().city() == null) return "city-null";

        String name = p.customer().address().city().name();
        if (name == null) return "city-name-null";
        if (name.isBlank()) return "city-name-blank";
        if (p.cents() <= 0) return "cents-nonpositive";
        return "ok";
    }

    static void check(String label, Object value,
                      String expected, String reason) {
        String nested = depth4(value);
        String step = staged(value);
        String diagnosis = diagnose(value);
        String normalized = nested.replace("d4:", "step:");

        if (!nested.equals(expected) || !step.equals(normalized)
                || !reason.equals(diagnosis)) {
            throw new AssertionError(label + " nested=" + nested
                    + ", step=" + step + ", diagnose=" + diagnosis);
        }
        System.out.println(label + " -> " + nested + " [" + diagnosis + "]");
    }

    public static void main(String[] args) {
        Object ok = new Purchase("P-1",
                new Customer("C-1",
                        new Address(new City("Hue"), "Main")), 2500);

        System.out.println(depth1(ok));
        System.out.println(depth2(ok));
        System.out.println(depth3(ok));
        System.out.println(depth4(ok));

        Object noCustomer = new Purchase("P-2", null, 2500);
        System.out.println(depth1(noCustomer));
        System.out.println(depth2(noCustomer));

        Object noCity = new Purchase("P-4",
                new Customer("C-4", new Address(null, "Main")), 2500);
        System.out.println(depth3(noCity));
        System.out.println(depth4(noCity));

        check("valid", ok, "d4:P-1:C-1:Hue:2500", "ok");
        check("street-null", new Purchase("P-5",
                new Customer("C-5",
                        new Address(new City("Da Nang"), null)), 10),
                "d4:P-5:C-5:Da Nang:10", "ok");
        check("customer-null", noCustomer,
                "d4:no-match", "customer-null");
        check("address-null", new Purchase("P-3",
                new Customer("C-3", null), 2500),
                "d4:no-match", "address-null");
        check("city-null", noCity, "d4:no-match", "city-null");
        check("name-null", new Purchase("P-6",
                new Customer("C-6",
                        new Address(new City(null), "Main")), 2500),
                "d4:no-match", "city-name-null");
        check("name-blank", new Purchase("P-7",
                new Customer("C-7",
                        new Address(new City(" "), "Main")), 2500),
                "d4:no-match", "city-name-blank");
        check("cents-zero", new Purchase("P-8",
                new Customer("C-8",
                        new Address(new City("Hue"), "Main")), 0),
                "d4:no-match", "cents-nonpositive");
        check("wrong-root", "not-purchase",
                "d4:no-match", "wrong-root");
        check("root-null", null, "d4:no-match", "root-null");

        System.out.println("10/10 comparisons passed");
    }
}
```

### 7.1. Compile and Run

With JDK 21 or later:

```bash
javac --release 21 NestedPatternDepthDemo.java
java NestedPatternDepthDemo
```

**Verified stdout:**

```text
d1:P-1:present
d2:P-1:C-1
d3:P-1:C-1:present
d4:P-1:C-1:Hue:2500
d1:P-2:missing
d2:no-match
d3:P-4:C-4:missing
d4:no-match
valid -> d4:P-1:C-1:Hue:2500 [ok]
street-null -> d4:P-5:C-5:Da Nang:10 [ok]
customer-null -> d4:no-match [customer-null]
address-null -> d4:no-match [address-null]
city-null -> d4:no-match [city-null]
name-null -> d4:no-match [city-name-null]
name-blank -> d4:no-match [city-name-blank]
cents-zero -> d4:no-match [cents-nonpositive]
wrong-root -> d4:no-match [wrong-root]
root-null -> d4:no-match [root-null]
10/10 comparisons passed
```

The program was run on **JDK 24/JShell** and confirmed the exact 19 lines above, using syntax finalized in Java 21. `check` compares **all three results**: the nested output, the staged output after normalizing the prefix, and the reason. If any result differs from expected, the program throws `AssertionError` rather than only printing success.

**Purpose of `diagnose`:** Reports **the first reason** in the order checked. It is not an aggregating validator for all errors; if a `Purchase` has both a null customer and non-positive cents, it returns `customer-null` first. With default record accessors, repeating getters in the example is stable; in production code, store intermediate references in local variables to reduce repetition and make breakpoints easier to place, especially when accessors are customized.

## 8. Analyzing the 10-Comparison Suite

| Test | Level-4 result | Reason from diagnosis | Meaning |
| --- | --- | --- | --- |
| `valid` | `d4:P-1:C-1:Hue:2500` | `ok` | Happy path, all four levels exist and guards pass |
| `street-null` | `d4:P-5:C-5:Da Nang:10` | `ok` | `var street` can bind null, and the sample domain allows it |
| `customer-null` | `d4:no-match` | `customer-null` | `Customer(...)` must be non-null |
| `address-null` | `d4:no-match` | `address-null` | `Address(...)` must be non-null |
| `city-null` | `d4:no-match` | `city-null` | `City(...)` must be non-null |
| `name-null` | `d4:no-match` | `city-name-null` | Record matches, but guard `name != null` fails |
| `name-blank` | `d4:no-match` | `city-name-blank` | Record matches, but guard `!name.isBlank()` fails |
| `cents-zero` | `d4:no-match` | `cents-nonpositive` | Record matches, but guard `cents > 0` fails |
| `wrong-root` | `d4:no-match` | `wrong-root` | Selector is not of type `Purchase` |
| `root-null` | `d4:no-match` | `root-null` | `instanceof` on null returns false |

The table shows that **depth 4 shortens the syntax of the valid path**, but all failures collapse to `d4:no-match` if you only look at the direct result. Only by adding a separate reason check can failures at each level be distinguished.

**Changing depth can change the data acceptance policy**: level 1 accepts a `Purchase` with a null customer; level 2 rejects it; level 3 accepts an address with a null city; level 4 rejects it. Therefore, when refactoring an expression from `var city` to `City(var name)`, write a test for `city == null` even when all valid cases still pass.

## 9. Why Is There No Universal "Maximum Depth"?

Java allows nested record patterns to a depth bounded by syntax, practical structure, and resource/compiler limits; there is no rule in the JLS such as **"Java should only nest at most two records"**. A code review threshold is a **team convention**, not a language requirement.

A useful heuristic for discussion:

| Depth | Initial assessment | When to consider changing? |
| --- | --- | --- |
| D=1 | Usually easy to read | When the record has very many components/guards or deconstruction is unnecessary |
| D=2 | Relatively clear if the model is good | When null policy/business conditions become complex |
| D=3 | Review variable count and schema coupling | When there are many branches or depth exceeds what the logic actually uses |
| D≥4 | Consider staged extraction or a domain helper | When debugging failures is hard, components change often, guards are long, or reviewers struggle to explain it |

**This is a heuristic, not a hard limit.** A short, clearly typed, well-tested level-4 pattern can be **easier to understand** than a function full of complex `if`/cast blocks. Conversely, a level-2 pattern with 15 binding variables can be harder to read than a small level-4 pattern.

A good evaluation uses **multiple criteria together** and stays aligned with the branch's purpose, rather than labeling a pattern good or bad based solely on `D`.

## 10. Comparing Nested Patterns and Staged Extraction

| Criterion | Level-4 nested record pattern | Step-by-step access (`staged`) |
| --- | --- | --- |
| Best fit | Checking an entire specific structure and using the data immediately | Diagnosing each level, applying different rules per failure type |
| Record-pattern nodes | 4 | 0 nested record patterns; uses one root type pattern and accessors |
| Explicit null-check branches | Few, because record patterns naturally do not match null child records | Many, explicitly named in code |
| Failure reason table | Not built-in if using only a Boolean `instanceof` | Easy to extend to return specific error codes |
| Coupling to component order | High on the deconstructed record-pattern nodes | Depends on corresponding accessor/property names |
| Line count | Can be shorter | Usually longer |
| Behavior on null components | Distinguishes `var` from nested record patterns | Controlled via step-by-step null checks |
| Testing | Needs thorough edge cases to verify the path | Can test each branch/diagnosis specifically |
| Performance | No guarantee of always being faster | No guarantee of always being slower |

**Do not infer speed from this table.** The JIT can optimize both forms; if performance is a real goal, use a proper benchmarking tool (such as JMH), warmup, statistical results, and representative data. Calling `System.nanoTime()` a few times on a small example is not enough to claim deeper nested patterns are slower.

The core trade-off here is **expressing an entire structure in a single branch** versus **managing steps and failure reasons separately**.

## 11. Common Compile Errors When Nesting Multiple Records

The following snippets are **intentionally wrong**; do not insert them into the runnable file in Section 7.

### 11.1. Wrong Component Count at the Deepest Record

`City` has only one component `name`. Writing:

```java
// INTENTIONALLY WRONG: City has only one component.
static boolean badDepth(Object value) {
    return value instanceof Purchase(
            var ref,
            Customer(var id,
                    Address(City(var name, var extra), var street)),
            var cents);
}
```

The JDK 24 compiler rejects this with **`incorrect number of nested patterns`**. This shows that nested patterns depend on record **arity**. Fix it to `City(var name)` or adjust the model appropriately; do not add meaningless variables to guess component counts.

### 11.2. Pattern Variable Outside Flow Scope

```java
// INTENTIONALLY WRONG: name does not exist after if if the pattern fails.
static void badScope(Object value) {
    if (value instanceof Purchase(
            var ref,
            Customer(var id,
                    Address(City(var name), var street)),
            var cents)) {
        System.out.println(name);
    }
    System.out.println(name); // Compile error.
}
```

Java applies **flow scoping**: a pattern variable is in scope where the compiler knows the pattern has matched. It can be used in the true branch of `if` or on the right-hand side of `&&` when the pattern expression is on the left-hand side, but cannot be used freely after the `if` in this example. This case was tested in JShell and rejected because `name` is not guaranteed to be valid.

### 11.3. Inferred Variable Type Incompatible with Operation

`Purchase.cents` is a primitive `long`. This snippet is wrong:

```java
// INTENTIONALLY WRONG: cents is long, has no toUpperCase().
static String wrongType(Purchase purchase) {
    return switch (purchase) {
        case Purchase(var ref,
                Customer(var id,
                        Address(City(var name), var street)),
                var cents) -> cents.toUpperCase();
    };
}
```

The JDK 24 compiler rejects this with **`long cannot be dereferenced`**. `var` in a pattern does not mean dynamic typing or always `Object`. It is inferred from the component type. When deconstructing deeply across multiple levels, reviewers must check what type and meaning each variable carries.

## 12. Behavioral Bugs Not Caught by the Compiler

Not all bugs appear at compile time.

**Swapping components of the same type:**

```java
record Address(City city, String street) {}
record City(String name) {}
```

If there is a record like `record Person(String firstName, String lastName) {}`, the pattern `Person(var lastName, var firstName)` still compiles but **assigns the wrong meaning** because variable names are chosen by the programmer. With multiple nested records, misnaming or swapping same-typed components can be harder to spot.

**Assuming a component is non-null:** `City(var name)` can match when `name == null`. Calling `name.isBlank()` without a null check can throw `NullPointerException`.

**Using an overly deep pattern for a simple classification:** If you only need to know `value instanceof Purchase`, you do not need `Purchase(...Customer(...Address(...)))`. A deep pattern can cause a valid `Purchase` missing an address to be skipped into an unintended branch.

**Multiple calls to custom accessors:** In records, accessors can be custom-defined. If an accessor throws an exception during deconstruction, the behavior can be a `MatchException` rather than a normal non-match. The `diagnose` method in this program uses default accessors. With custom accessors that have side effects, control the number of invocations, keep data consistent, and inspect stack traces when debugging.

**Mixing validation with matching:** Sometimes it is better to separate validation at the boundary, construct value objects with checked invariants, and then use short patterns on the normalized model. This is better than repeating guards like `name != null && !name.isBlank()` in many places without a shared contract.

## 13. Process for Evaluating Nested Patterns in a Codebase

Use this process on a real expression instead of relying on gut feeling:

1. **Pick a case to measure:** identify a pattern expression and its business goal, e.g. "read the order's city name".
2. **Draw the data tree:** list each record, component, static type, and null policy.
3. **Count D/R/V/N/G:** use the same conventions as in Section 2; document how they are counted, especially with multiple nested record branches.
4. **Check the purpose of each level:** is this level matched because the logic genuinely needs it, or only to avoid calling accessors?
5. **List failure paths:** null root, wrong type, each null child record, null/blank component, failed guard.
6. **Measure coupling under schema change:** test a component change in an experimental branch; record which patterns fail to compile and which logic must be re-tested.
7. **Write an equivalent staged version:** same inputs and business policy, differing only in code structure.
8. **Run comparative unit tests:** especially null cases at each level and guard conditions.
9. **Review readability/debuggability:** can others explain the variables, ordering, and failure reasons? How well do IDE breakpoints isolate failures?
10. **Choose the clearest form:** keep nested when short, purposeful, and low-risk; split when there are many responsibilities/validations, or move logic into a named domain method.
11. **Benchmark separately if needed:** do not treat depth or line count as performance metrics.

An evaluation record can take the form:

| Metric | Current nested | Staged alternative | Notes |
| --- | --- | --- | --- |
| D | 4 | No nested record pattern | Defined per the article's syntax rules |
| R | 4 | 0 | Staged uses only a root type pattern |
| V | 5 | A few named local variables | Do not compare `var` counts directly across different code structures |
| N | 3 | Three explicit non-null child checks | Equivalent data acceptance policy |
| G | 3 | Three `if` conditions on `name`/`cents` | Equivalent business checks |
| Readability | Reading one long expression | Reading several short steps | Evaluated by review, not inferred from D |
| Failure reason | `d4:no-match` | Can return specific reasons | `diagnose` adds reasons in the demo |
| Regression tests | 10 verified cases | Same 10 cases | Equivalence checked on the same input suite |

## 14. Practice Exercises

### Exercise 1 — Measure Depth of Another Structure

Given:

```java
record Coordinates(double lat, double lon) {}
record Location(String label, Coordinates coordinates) {}
record Delivery(String code, Location destination) {}
```

Write a record pattern to extract `lat` and `lon` from `Object input`. By Section 2's conventions, using `Delivery(...Location(...Coordinates(...)))` gives **`D=3` and `R=3`**. Count `V` for the pattern you wrote, then add guards checking:

- Latitude between `-90` and `90`.
- Longitude between `-180` and `180`.
- Both numbers finite: `Double.isFinite`.

### Exercise 2 — Distinguish Null Child Records from Null Components

With the structure from Exercise 1, create inputs: `Delivery(null)` (assuming the constructor allows it), `Location.coordinates == null`, invalid `Coordinates.lat`, and null root. Observe which levels cause the record pattern not to match and which are only rejected by guards. Note that `Coordinates` holds primitive `double`, so `lat` cannot be null; instead of a null case, test `NaN` or infinity.

### Exercise 3 — Change the Schema

Add `String postalCode` to `Location`. Inspect record patterns deconstructing `Location(...)`; update the component order and count accordingly. Compare with a staged version using `location.coordinates()` to observe the coupling of both approaches.

### Exercise 4 — Evaluate Both Approaches

Write two ways to extract `delivery.destination.coordinates.lat`: one nested expression and one staged function. Add tests for all null/wrong-type cases and boundary values. Choose the option easiest to explain in a mock code review; report D/R/V/N/G and your rationale, rather than simply saying "deeply nested is bad".

## 15. Conclusion and References

**Evaluating nested pattern depth means evaluating how much structure is encoded in a single expression, along with its impact on null semantics, readability, schema coupling, debugging, and testing.** In the example:

- `D=1` deconstructs only `Purchase` and can accept a null customer.
- `D=2` requires `Customer` to exist.
- `D=3` requires `Address` to exist but can still bind `city == null` via `var`.
- `D=4` requires `City` to exist, and only then do guards check the city name and amount.
- Across the same 10 inputs, nested depth 4 and staged produced equivalent results; the diagnostic method explained the reasons.
- **Java does not prescribe an "ideal" depth limit**; use D/R/V/N/G and domain requirements to decide. Greater depth does not automatically mean slower, safer, or harder to maintain in every case.

Official references:

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
