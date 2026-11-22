# Practicing Optional for Operation Chains That May Lack Data in Java

## 1. Practice Goal

In a Java application, a lookup operation may **fail to return a value**: a customer does not exist, a profile has no address yet, a code is invalid, a manager has not been assigned, or a search result is empty. If you simply chain ordinary method calls, it is easy to hit `NullPointerException`:

~~~java
// INTENTIONALLY DANGEROUS when an intermediate step may return null.
String city = repository.findUser(id).getProfile()
        .getAddress().getCity().strip();
~~~

This is illustrative code, not a standalone program. Any step returning `null` can cause the next step to dereference an absent value.

`Optional<T>` in `java.util` explicitly represents **either a value of type `T` or no value**. When used properly, a chain of steps can be expressed as continuous transformations, and **the empty branch propagates** without dereferencing `null` at each step.

After this lesson, you will know how to:

1. Identify where to create an `Optional` from nullable data.
2. Chain **`T → U`** transformations using `map()`.
3. Chain **`T → Optional<U>`** lookups using `flatMap()`, avoiding `Optional<Optional<T>>`.
4. Use `filter()` to exclude values that do not meet a condition.
5. Choose `orElse()`, `orElseGet()`, `or()`, `orElseThrow()`, or `ifPresentOrElse()` based on output requirements.
6. Thoroughly test present data, missing data at each layer, blank values, parse errors, and fallbacks.
7. Distinguish **“no data”** from **“invalid data that needs to be reported”**.
8. Avoid unchecked `get()`, hidden side effects, using Optional as a collection, or unnecessary return types.

This lesson uses **Java 17+**. Programs with specific filenames all contain `main` and can be saved, compiled with `javac`, and run with `java`. Other snippets are explicitly noted as **illustrative code within a context where variables/methods are already declared**, not standalone runnable code.

## 2. Mental Model: An Operation Chain That Can Break at Any Layer

Suppose you need to get a city name from a profile:

~~~text
customerId
   │
   ▼ find customer (may be absent)
Customer
   │
   ▼ get address (may be absent)
Address
   │
   ▼ get city (may be absent)
String
   │
   ▼ trim/strip then check non-empty
Valid String
   │
   ▼ convert to uppercase
Result String
~~~

If any layer has no data, the final result should be `Optional.empty()` instead of trying to invoke methods on `null`. A suitable pipeline:

~~~java
Optional<String> city = Optional.ofNullable(customers.get(id))
        .map(Customer::address)
        .map(Address::city)
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .map(name -> name.toUpperCase(Locale.ROOT));
~~~

This is **illustrative code**, requiring `customers` as a map with `Customer` values, the `Customer`/`Address` records/classes, and imports for `Optional` and `Locale`. The focus is on **the order of data types** and stopping cleanly when a value is absent.

At each step:

- `Optional.ofNullable(customers.get(id))` converts a nullable value into `Optional<Customer>`.
- `map(Customer::address)` goes from `Optional<Customer>` to `Optional<Address>`. If `address()` returns `null`, the result becomes `Optional.empty()`.
- `map(Address::city)` converts the address into the city name when present.
- `map(String::strip)` normalizes the string.
- `filter(...)` discards empty results after normalization.
- `map(...toUpperCase...)` runs only when all prior steps produced a value and the filter passed.
- Finally, the caller can choose a fallback, throw an exception, or perform an action as required.

**Important:** Optional does not guarantee that source data will not be modified concurrently by others; nor does it automatically catch all exceptions. It only models the **presence/absence** of a value across steps represented with Optional.

## 3. Rule for Choosing `map` vs. `flatMap`

For `Optional<T>`:

~~~java
<U> Optional<U> map(Function<? super T, ? extends U> mapper);

<U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper);
~~~

These are abbreviated signatures from the Java SE API, not a custom redefinition of `Optional`.

**Ask just one question:** what type does the method called by the mapper return?

| Mapper return type | API to use | Type after transformation |
|---|---|---|
| `U` | `map` | `Optional<U>` |
| `Optional<U>` | `flatMap` | `Optional<U>` |
| `boolean` to keep/discard value | `filter` | `Optional<T>` |
| Want to perform an action with value if present | `ifPresent` | `void` |
| Want to pick a default value of type `T` | `orElse`/`orElseGet` | `T` |

Example:

~~~java
// Assume findUser(id) returns Optional<User>.
Optional<String> name = findUser(id).map(User::name);

// Assume findAddress(user) returns Optional<Address>.
Optional<Address> address = findUser(id)
        .flatMap(this::findAddress);
~~~

These two snippets are **illustrative inside a class with the corresponding methods and types**. Using `map` with a function that already returns `Optional<Address>` produces **`Optional<Optional<Address>>`**, which is inconvenient for chaining further transformations.

### 3.1. How Empty State Propagates

For an `Optional.empty()`:

- `map` does not call the mapper and returns an empty Optional.
- `flatMap` does not call the mapper and returns an empty Optional.
- `filter` does not call the predicate and preserves the empty state.
- `ifPresent` does not call the action.
- `ifPresentOrElse` calls the `Runnable` branch for the empty state.
- `orElseGet` calls the fallback supplier.

This removes the need to write `if (value != null)` at every step. However, if a mapper is called on a present value and throws an exception, Optional **does not turn the exception into empty**.

### 3.2. When a Mapper Returns `null`

`Optional.map()` uses `ofNullable`-equivalent semantics on the mapper's return value: if the mapper returns `null`, the result is `Optional.empty()`.

Conversely, the mapper for `Optional.flatMap()` must return **a non-null `Optional` object**. If it returns `null`, Java throws `NullPointerException`. Return `Optional.empty()` to express “not found”.

~~~java
// Valid for a normal function that may return null:
Optional.of("abc").map(s -> null);        // Optional.empty()

// INTENTIONALLY WRONG for flatMap contract:
Optional.of("abc").flatMap(s -> null);    // NullPointerException
~~~

These lines are illustrative; you should not write mappers returning `null` merely to control flow when an explicit empty state is available.

## 4. Practice 1: Customer → Address → City Lookup

### 4.1. Requirements

A simple data store holds profiles by ID. A profile may lack an address; an address may have a blank city. Write a method:

~~~java
static Optional<String> findNormalizedCity(
        Map<String, Customer> customers,
        String id)
~~~

The method must return the city `strip()`ped and uppercased with `Locale.ROOT` when valid data exists; if the customer is missing, the address is missing, or the city is whitespace-only, return `Optional.empty()`.

### 4.2. Complete Java 17 Program

Save **`OptionalCityChainDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

public class OptionalCityChainDemo {
    record Address(String city, String postalCode) {}
    record Customer(String name, Address address) {}

    static Optional<String> findNormalizedCity(
            Map<String, Customer> customers,
            String id) {
        return Optional.ofNullable(customers.get(id))
                .map(Customer::address)
                .map(Address::city)
                .map(String::strip)
                .filter(city -> !city.isEmpty())
                .map(city -> city.toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Map<String, Customer> customers = Map.of(
                "c1", new Customer("An",
                        new Address("  Ha Noi  ", "100000")),
                "c2", new Customer("Binh", null),
                "c3", new Customer("Chi",
                        new Address("   ", "200000"))
        );

        System.out.println("c1=" +
                findNormalizedCity(customers, "c1"));
        System.out.println("c2=" +
                findNormalizedCity(customers, "c2"));
        System.out.println("c3=" +
                findNormalizedCity(customers, "c3"));
        System.out.println("unknown=" +
                findNormalizedCity(customers, "missing"));

        String visible = findNormalizedCity(customers, "c2")
                .orElse("CHUA CO DIA CHI");
        System.out.println("visible=" + visible);
    }
}
~~~

Compile and run:

~~~bash
javac OptionalCityChainDemo.java
java OptionalCityChainDemo
~~~

Stdout:

~~~text
c1=Optional[HA NOI]
c2=Optional.empty
c3=Optional.empty
unknown=Optional.empty
visible=CHUA CO DIA CHI
~~~

### 4.3. Explaining Each Branch

**Customer `c1`:**

1. `customers.get("c1")` returns a `Customer`.
2. `Customer::address` returns an `Address` with city `"  Ha Noi  "`.
3. `Address::city` returns a `String`.
4. `String::strip` removes leading/trailing whitespace to `"Ha Noi"`.
5. `filter` keeps the non-empty value.
6. `toUpperCase(Locale.ROOT)` returns `"HA NOI"`; the result is `Optional[HA NOI]`.

**Customer `c2`:** `address()` is `null`, so `map(Customer::address)` turns the result into `Optional.empty()`. Subsequent mappers **are not called**. There is no `NullPointerException` due to the missing address.

**Customer `c3`:** the address exists, but the city is whitespace. After `strip()`, the string becomes `""`; `filter` discards it, yielding empty.

**ID `missing`:** `Map.get` returns `null`; `ofNullable` creates an empty Optional from the start.

At the end, `orElse("CHUA CO DIA CHI")` returns a **default string** only when the Optional is empty. If you need to know **why** there is no city (customer does not exist, missing address, or blank city), `Optional.empty()` **does not carry enough error information**; you need a result type containing the reason instead of trying to “reverse-infer” the cause from empty.

### 4.4. Extension Exercise

Add a customer with address `new Address("  Da Nang ", "550000")` and verify the result is `Optional[DA NANG]`. Also try `new Address(null, "...")`: `map(Address::city)` can turn `null` into an empty state. If an `Address` having `city == null` is a **data error**, do not silently treat it as “not found”; add validation at the input boundary.

## 5. Practice 2: Chaining Two Optional-Returning Lookups with `flatMap`

### 5.1. Requirements

The system has a user directory and manager IDs. `findUser(id)` returns `Optional<User>`. To look up a user's manager, we also have a method returning `Optional<User>` because a manager may not exist.

Contract shape:

~~~java
Optional<User> findUser(String id)
Optional<User> findManager(User user)
Optional<String> findManagerId(String employeeId)
~~~

To chain `employeeId → user → manager → managerId`, use `flatMap` at the manager lookup step because `findManager` **already returns an Optional**.

### 5.2. Standalone Runnable Program

Save **`OptionalManagerDemo.java`**:

~~~java
import java.util.Map;
import java.util.Optional;

public class OptionalManagerDemo {
    record User(String id, String managerId) {}

    private final Map<String, User> users;

    OptionalManagerDemo(Map<String, User> users) {
        this.users = users;
    }

    Optional<User> findUser(String id) {
        return Optional.ofNullable(users.get(id));
    }

    Optional<User> findManager(User user) {
        return Optional.ofNullable(user.managerId())
                .flatMap(this::findUser);
    }

    Optional<String> findManagerId(String employeeId) {
        return findUser(employeeId)
                .flatMap(this::findManager)
                .map(User::id);
    }

    public static void main(String[] args) {
        Map<String, User> data = Map.of(
                "u1", new User("u1", "u2"),
                "u2", new User("u2", null),
                "u3", new User("u3", "missing")
        );
        OptionalManagerDemo directory = new OptionalManagerDemo(data);

        System.out.println("u1=" + directory.findManagerId("u1"));
        System.out.println("u2=" + directory.findManagerId("u2"));
        System.out.println("u3=" + directory.findManagerId("u3"));
        System.out.println("absent=" +
                directory.findManagerId("unknown"));
    }
}
~~~

Compile/run:

~~~bash
javac OptionalManagerDemo.java
java OptionalManagerDemo
~~~

Stdout:

~~~text
u1=Optional[u2]
u2=Optional.empty
u3=Optional.empty
absent=Optional.empty
~~~

**Reading the output:**

- `u1` has `managerId="u2"`, and `u2` exists. `flatMap(this::findManager)` chains the lookup into a single Optional, then `map(User::id)` extracts the manager ID.
- `u2` has no manager ID, so `Optional.ofNullable(null)` returns empty.
- `u3` has `managerId="missing"` but that user is not found; `findUser` returns empty.
- `unknown` has no starting user, so the very first `findUser` call is empty.

**Key takeaway:** the code of `findManagerId` needs no `if (obj != null)` checks because each function returns an Optional modeling absence.

### 5.3. Why is `map` not suitable at the lookup step?

If you write:

~~~java
Optional<Optional<User>> nested =
        directory.findUser("u1").map(directory::findManager);
~~~

you get **two layers of Optional**: outer for whether the employee was found; inner for the manager lookup result. To call `User::id`, you would have to unwrap the inner Optional.

With `flatMap`:

~~~java
Optional<User> flat =
        directory.findUser("u1").flatMap(directory::findManager);
~~~

the result is a single `Optional<User>`. This is a key distinction when chaining lookups that may lack data.

Both snippets above **are illustrative only** and must be placed in a scope with `directory` of type `OptionalManagerDemo` and `Optional` imported.

## 6. Practice 3: Normalizing, Validating, and Parsing Input

### 6.1. Requirements

A request parameter might be:

- `null`.
- Containing leading/trailing whitespace.
- Empty or whitespace-only.
- Not an integer.
- `0` or negative, invalid per business rules.
- Positive, but overflowing `int` range.

We need to write:

~~~java
static Optional<Integer> parsePositiveInt(String raw)
~~~

Return `Optional.of(n)` if `raw` represents a valid positive integer; otherwise return empty. In a real application, collapsing all errors into empty might not suffice to report the cause; this example uses Optional because the goal is **practicing chains that may lack data**.

### 6.2. Complete Java 17 Program

Save **`OptionalParseDemo.java`**:

~~~java
import java.util.Optional;

public class OptionalParseDemo {
    static Optional<Integer> parsePositiveInt(String raw) {
        return Optional.ofNullable(raw)
                .map(String::strip)
                .filter(text -> !text.isEmpty())
                .flatMap(text -> {
                    try {
                        int parsed = Integer.parseInt(text);
                        return parsed > 0
                                ? Optional.of(parsed)
                                : Optional.empty();
                    } catch (NumberFormatException ex) {
                        return Optional.empty();
                    }
                });
    }

    public static void main(String[] args) {
        System.out.println("valid=" + parsePositiveInt(" 12 "));
        System.out.println("zero=" + parsePositiveInt("0"));
        System.out.println("negative=" + parsePositiveInt("-3"));
        System.out.println("text=" + parsePositiveInt("abc"));
        System.out.println("blank=" + parsePositiveInt("  "));
        System.out.println("null=" + parsePositiveInt(null));
        System.out.println("overflow=" +
                parsePositiveInt("999999999999999999999"));
    }
}
~~~

Compile/run:

~~~bash
javac OptionalParseDemo.java
java OptionalParseDemo
~~~

Stdout:

~~~text
valid=Optional[12]
zero=Optional.empty
negative=Optional.empty
text=Optional.empty
blank=Optional.empty
null=Optional.empty
overflow=Optional.empty
~~~

### 6.3. Why does the parse step use `flatMap`?

`Integer.parseInt(text)` returns `int` or throws `NumberFormatException`. We **deliberately** convert parse failures accepted by this business rule into `Optional.empty()`, so the lambda has a `try/catch` and returns `Optional<Integer>` in both success and failure branches.

Because the lambda returns `Optional<Integer>`, we must use `flatMap` to avoid `Optional<Optional<Integer>>`. When `raw == null` or the stripped string is empty, the parse lambda **never runs**.

**Current guarantees:**

- `parsePositiveInt(" 12 ")` → `Optional[12]`.
- `parsePositiveInt("-3")` → empty because it is not positive.
- `parsePositiveInt("abc")` → empty due to `NumberFormatException`.
- Numeric string exceeding `int` range → empty when parsing fails.
- `null` input → empty at the `ofNullable` step.

**What is not guaranteed:** the caller does not know the exact reason for failure. If you need to return specific errors like `MISSING`, `NOT_INTEGER`, `OUT_OF_RANGE`, or `NOT_POSITIVE`, design a dedicated result type (e.g., sealed interface/record/enum) rather than overusing `Optional.empty()`.

### 6.4. Avoid Catching Every Exception

Do not write `catch (Exception ex) { return Optional.empty(); }` to hide all errors in a mapper. If an unexpected bug, I/O error, or programming error occurs, turning everything into “absent data” makes debugging difficult. In the example above, only **`NumberFormatException`** is treated as an expected parse failure.

## 7. When Does `filter` Fit Business Conditions?

`filter(Predicate<? super T>)` keeps a value only if the predicate returns true:

~~~java
Optional<String> nonBlank = Optional.of("  Java  ")
        .map(String::strip)
        .filter(s -> !s.isBlank());
// Optional[Java]
//
~~~

Use `filter` when a condition does not need to **transform** the value, only **keep or discard** it. If the condition represents a serious error whose cause the caller needs to know, filtering into empty can lose information.

Illustrative examples:

~~~java
Optional<Integer> age = Optional.of(20)
        .filter(n -> n >= 18);

Optional<String> validCode = Optional.ofNullable(rawCode)
        .map(String::strip)
        .filter(code -> code.matches("[A-Z0-9]+"));
~~~

The second snippet requires `rawCode` declared in outer scope and a code policy allowing only uppercase A–Z and digits 0–9. Lowercase strings are discarded: that is a business decision, not a property of Optional.

**Do not replace `filter` with `get` + `if` when it can be expressed directly.** However, when conditions are complex or must produce a structured set of errors, extract a `validate` function with an appropriate result type.

## 8. Choosing How to Terminate an Optional Chain

An Optional can be handled in several ways. Determine whether **the caller needs a value, wants to keep the Optional, needs an error, or needs to perform an action**.

| Need | API | Returns | Key difference |
|---|---|---|---|
| Take value if present, else use a predetermined value | `orElse(T other)` | `T` | Argument expression `other` is evaluated before the call |
| Take value if present, else compute fallback | `orElseGet(Supplier<? extends T>)` | `T` | Supplier is called **only when Optional is empty** |
| Use value if present, else return backup Optional | `or(Supplier<? extends Optional<? extends T>>)` | `Optional<T>` | Keeps Optional type; fallback must return non-null Optional |
| Take value if present, throw error if absent | `orElseThrow()` or supplier overload | `T` | Absence becomes an exception |
| Perform action if value is present | `ifPresent(Consumer)` | `void` | Does nothing when empty |
| Perform different actions for present vs. empty | `ifPresentOrElse(Consumer,Runnable)` | `void` | Empty branch receives no value |
| Preserve present/empty state for caller to decide | Do not unwrap | `Optional<T>` | Suitable when absence is normal |

### 8.1. `orElse` vs. `orElseGet`: difference in when fallback is evaluated

This is a common mistake:

~~~java
String result = optional.orElse(expensiveDefault());
~~~

If `expensiveDefault()` is costly or has side effects, Java **evaluates the argument first** before calling `orElse`, even if `optional` already has a value. If you do not want to compute the fallback when data is already present:

~~~java
String result = optional.orElseGet(() -> expensiveDefault());
~~~

These are two illustrative snippets inside a method with `optional` of type `Optional<String>` and `expensiveDefault()` returning `String`.

### 8.2. Java 17 Program: Measuring Exact Fallback Timing

Save **`OptionalFallbackDemo.java`**:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackDemo {
    static String expensiveDefault(AtomicInteger calls) {
        int number = calls.incrementAndGet();
        return "fallback-" + number;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        Optional<String> ready = Optional.of("ready");
        String eager = ready.orElse(expensiveDefault(calls));
        System.out.println("eager=" + eager);
        System.out.println("afterEager=" + calls.get());

        String lazy = ready.orElseGet(
                () -> expensiveDefault(calls));
        System.out.println("lazy=" + lazy);
        System.out.println("afterLazy=" + calls.get());

        String missing = Optional.<String>empty()
                .orElseGet(() -> expensiveDefault(calls));
        System.out.println("missing=" + missing);
        System.out.println("afterMissing=" + calls.get());

        Optional<String> backup = Optional.<String>empty()
                .or(() -> Optional.of("backup"));
        System.out.println("backup=" + backup);
    }
}
~~~

Compile/run:

~~~bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Stdout:

~~~text
eager=ready
afterEager=1
lazy=ready
afterLazy=1
missing=fallback-2
afterMissing=2
backup=Optional[backup]
~~~

**Explanation:**

1. `orElse(expensiveDefault(calls))` returns `"ready"` yet still calls `expensiveDefault` to build the argument, so the counter increments to `1`.
2. `orElseGet(() -> expensiveDefault(calls))` also returns `"ready"`, **without calling** the supplier because the Optional already has a value.
3. For an empty Optional, `orElseGet` calls the supplier once and returns `"fallback-2"`.
4. `or(...)` differs from the two APIs above: it returns **an `Optional<String>`**, not a `String` directly. If the source is empty, the supplier is invoked to obtain a backup Optional.
5. `AtomicInteger` is only used as an illustrative counter; it does not mean every fallback must use atomics or run in parallel.

### 8.3. `orElseThrow` when absence is an error

~~~java
User user = findUser(id).orElseThrow(
        () -> new IllegalArgumentException("Unknown user: " + id));
~~~

This is illustrative code in a class where `findUser` returns `Optional<User>`. When there is no user, the supplier creates the exception. When a user exists, the exception supplier is not called.

If absence is a valid state, you **should not** throw an exception just to avoid returning `Optional`. Which API fits depends on the business contract.

### 8.4. `ifPresentOrElse` when an action is needed, not a return value

~~~java
findUser(id).ifPresentOrElse(
        user -> renderUser(user),
        () -> renderNotFound(id)
);
~~~

`Consumer<User>` receives the user when present; `Runnable` takes no arguments in the absent branch. Both `ifPresent` and `ifPresentOrElse` return `void` and **should not be used** expecting a `String` or new object from the expression.

## 9. Optional and On-Demand Data Creation with Supplier

An Optional chain is not merely a set of null-safe functions. It also helps describe **when** a new fallback value needs to be created.

Suppose:

~~~java
Optional<Config> config = findConfig(id);

Config chosen = config.orElseGet(() -> loadDefaultConfig());
~~~

This is illustrative code. If `findConfig(id)` has a value, `loadDefaultConfig()` is not called. However, **the call `findConfig(id)` itself already occurred** before `orElseGet`. The supplier only defers the **fallback**, not every preceding operation.

If you want the fallback to remain an Optional to keep chaining steps:

~~~java
Optional<Config> selected = findConfig(id)
        .or(() -> findSystemConfig())
        .filter(Config::enabled);
~~~

Here `or` (Java 9+) is used, and the supplier returns `Optional<Config>`. If the user config is present, the system config is not tried, even if the user config is filtered out **at the later step**. Order matters:

~~~java
findConfig(id).filter(Config::enabled)
        .or(() -> findSystemConfig())
~~~

The second form tries the system config when the user config does not exist **or is filtered out because it is not enabled**. Those are **two different business rules**.

**Practice:** Before choosing the order of `filter` and `or`, state in plain language whether “config exists but is disabled” should trigger fallback to the system config or be treated as a stopping decision.

## 10. Combining Optional with Stream

When you have a collection containing multiple Optionals, sometimes you want to extract **only the present values**. Since Java 9, `Optional.stream()` returns a stream of **0 or 1 element**.

~~~java
List<Optional<String>> maybes = List.of(
        Optional.of("a"),
        Optional.empty(),
        Optional.of("b")
);

List<String> values = maybes.stream()
        .flatMap(Optional::stream)
        .toList();
// values = [a, b]
~~~

This is an illustrative snippet requiring `List` and `Optional`. `flatMap(Optional::stream)` turns `Stream<Optional<String>>` into `Stream<String>` and skips empty Optionals.

**Do not confuse `Optional.flatMap` with `Stream.flatMap`.** Both avoid nested containers, but one operates on `Optional<T>` and the other on `Stream<T>`.

Example with multiple IDs:

~~~java
List<User> existing = ids.stream()
        .map(this::findUser)
        .flatMap(Optional::stream)
        .toList();
~~~

This illustrative snippet sits in a class with `ids` of type `List<String>` and `findUser` returning `Optional<User>`. This is how to retrieve existing users. However, if business logic needs to **report an error for each missing ID**, skipping empties is not enough: you must keep the original ID in a result or return a structure holding the status of each lookup.

## 11. Testing Optional Chains with Case Tables

When testing a chain that can be missing at multiple layers, do not test only one success case and one leading-null case. Build a **decision table**.

### 11.1. Case table for Customer → Address → City

| Input | Customer | Address | City | Expected |
|---|---|---|---|---|
| `c1` | Present | Present | `"  Ha Noi  "` | `Optional[HA NOI]` |
| `c2` | Present | `null` | — | `Optional.empty` |
| `c3` | Present | Present | `"   "` | `Optional.empty` |
| `missing` | Absent | — | — | `Optional.empty` |
| Null city | Present | Present | `null` | `Optional.empty` if policy allows |
| City `"Da Nang"` | Present | Present | Valid | `Optional[DA NANG]` |

The key point is that **each cause of absence at every layer is tested**. If you only test a non-existent ID, you will miss bugs when address is null or city is blank.

### 11.2. Case table for positive integer parsing

| Input | Result |
|---|---|
| `"12"` | `Optional[12]` |
| `" 12 "` | `Optional[12]` |
| `"0"` | Empty |
| `"-3"` | Empty |
| `"abc"` | Empty |
| `""` or whitespace | Empty |
| `null` | Empty |
| Number exceeding `int` limit | Empty |

If the rule changes to allow `0`, you only update the predicate/positive-int policy; the test table will catch the difference.

### 11.3. Testing fallback invocation timing

Do not test only the **return value**; also verify **whether the fallback supplier is called only when needed**. One way is using `AtomicInteger` like `OptionalFallbackDemo`. However, in production code, do not rely on callback side effects to compute results; testing side effects here is solely to verify **the lazy contract of `orElseGet`**.

### 11.4. Unit testing without a real database

If lookup functions have a separated interface, you can pass a fake map or repository test double. Normalization functions like `String::strip`, `filter`, and `map` can be tested with immutable data and boundary cases, without a server or network.

## 12. Common Mistakes in Optional Chains

### Mistake 1: Calling `get` before checking

~~~java
// UNSAFE when Optional may be empty:
String name = findUser(id).get().name();
~~~

`Optional.get()` throws `NoSuchElementException` if empty. Replace with:

~~~java
Optional<String> name = findUser(id).map(User::name);
~~~

Or if a missing user is a business error:

~~~java
User user = findUser(id).orElseThrow(
        () -> new IllegalArgumentException("User not found"));
~~~

These illustrative snippets require the corresponding types/methods.

### Mistake 2: Using `map` for a function returning `Optional`

~~~java
// Easily creates Optional<Optional<Address>>.
Optional<Optional<Address>> nested =
        findUser(id).map(this::findAddress);
~~~

If `findAddress` returns `Optional<Address>`, use:

~~~java
Optional<Address> address =
        findUser(id).flatMap(this::findAddress);
~~~

### Mistake 3: Returning `null` from `flatMap`

~~~java
// INTENTIONALLY WRONG:
Optional.of("abc").flatMap(value -> null);
~~~

If the mapper is called and returns `null`, `Optional.flatMap` throws `NullPointerException`. Return `Optional.empty()` when there is no result.

### Mistake 4: Assuming `map` catches all exceptions

~~~java
Optional<String> text = Optional.of("abc");
Optional<Integer> number = text.map(Integer::parseInt);
~~~

This code throws `NumberFormatException`, not empty. Optional only handles **absence**, and does not automatically turn exceptions into empty. If parse failure is an expected state, write an explicit error-handling function like `parsePositiveInt`.

### Mistake 5: Calling `orElse` with an expensive fallback

`orElse(expensive())` **evaluates its argument eagerly**. Use `orElseGet(() -> expensive())` when the fallback should only run when the Optional is empty. For cheap constant values like `"UNKNOWN"`, `orElse("UNKNOWN")` is completely appropriate.

### Mistake 6: Using `ifPresent` to try to return a value

`ifPresent` and `ifPresentOrElse` return `void`; they are for actions. If you want to obtain a string, use `map` then `orElse`/`orElseGet`, or return `Optional<String>` to the caller.

### Mistake 7: Overusing `Optional` for every field and parameter

`Optional` is most useful as the **return type** of a method that may have no result. Not every field should be `Optional<T>`, and using `Optional` as a parameter can make APIs verbose when domain types or overloads are clearer.

In the record example with a nullable `Address` field, we used `Optional.ofNullable` at the **processing boundary**. In production, it is better to define non-null rules, validation, or appropriate value types right on the model depending on requirements.

### Mistake 8: Using `empty` to hide errors that need to be distinguished

If the product must distinguish “no profile”, “no address yet”, “blank city”, or “access denied”, a single `Optional.empty()` **loses information**. Use a result type with a reason enum/record, or an appropriate exception, instead of confusing error states with normal absence.

### Mistake 9: Overly long chains hiding business meaning

~~~java
Optional<String> result = find(id)
        .flatMap(this::fetchSomething)
        .map(this::convert)
        .filter(this::check)
        .flatMap(this::lookupOther)
        .map(this::render);
~~~

This is illustrative. If readers struggle to tell what each step does, name intermediate functions/variables, or create helpers with clear contracts. **Shorter does not automatically mean easier to understand.** Optional is a tool to clarify potentially absent data, not an end in itself.

### Mistake 10: Ignoring `null` inside a mapper

`map(String::strip)` is only safe when the Optional holds a non-null `String`. `Optional` cannot hold a null value; if an earlier step returns `null`, `map` turns it into empty. However, if a mapper invokes a method on **another unprotected nullable component**, it can still throw `NullPointerException`. For example, `map(user -> user.profile().city())` will dereference `null` if `profile()` returns `null`. Split into `map(User::profile).map(Profile::city)` when semantically appropriate.

## 13. Optional, Mutable Data, and Side Effects

Transformations on Optional are often used in a functional style. However, `Optional.map()` does not turn a mapper into a pure function and does not clone existing objects.

~~~java
Optional<StringBuilder> builder =
        Optional.of(new StringBuilder("a"));

Optional<StringBuilder> same = builder.map(x -> x);
same.ifPresent(x -> x.append("b"));
~~~

This is an illustrative example. `builder` and `same` can hold the **same `StringBuilder` reference**; `append` mutates the mutable object. If you need an isolated value, convert to `String` or a new DTO/value object.

**Keep value logic and effects separate:**

- `map`, `flatMap`, and `filter` are primarily for computation/lookup.
- `ifPresent` and `ifPresentOrElse` are for when the caller genuinely needs an **action**.
- For database transactions, sending emails, or mandatory event writes, a service/orchestrator with a clear contract makes error control easier than stuffing side effects into a mapper.
- In concurrent environments, Optional does not provide synchronization or snapshots; contained objects may still be mutable and must be shared according to the Java Memory Model.

## 14. Notes on `null` and API Boundaries

### 14.1. `of`, `ofNullable`, and `empty`

| Method | When to use | Behavior |
|---|---|---|
| `Optional.of(value)` | Certain that `value != null` | Passing null → `NullPointerException` |
| `Optional.ofNullable(value)` | `value` may be null | Null → `Optional.empty()` |
| `Optional.empty()` | Intentionally represent no value | Does not contain `null` as an element |
| `Optional.map(f)` | Mapper returns ordinary value `U` | Mapper returns null → empty Optional |
| `Optional.flatMap(f)` | Mapper returns `Optional<U>` | Mapper returns null → `NullPointerException` |

A method declared to return `Optional<T>` **should never return `null`**. If the result may be empty, return `Optional.empty()`. Returning `null` breaks the contract callers rely on to chain `map`/`flatMap`.

### 14.2. Do not use Optional to hide invalid preconditions

For example, an API requires ID to be non-null. If a caller passes `null`, it may be reasonable for the API to throw `IllegalArgumentException`/`NullPointerException` instead of treating it as “not found”. That is a contract decision, not a rule that every `null` must become `Optional.empty`.

Distinguish between:

- **Contract-violating input:** API usage error or precondition violation.
- **Valid input but not found:** `Optional.empty`.
- **Business state with multiple error causes:** result type carrying error info.
- **Failed I/O operation:** well-defined exception or error result.

## 15. Comprehensive Exercises and Solution Guide

### Exercise A — City and postal code

Data is `Optional<Customer>`. If Customer, Address, and non-empty `postalCode` exist, return the normalized postal code:

~~~java
Optional<String> postal = maybeCustomer
        .map(Customer::address)
        .map(Address::postalCode)
        .map(String::strip)
        .filter(code -> !code.isEmpty());
~~~

If any layer is missing, the result is empty. This is an illustrative snippet in a context with `Customer`/`Address` like Practice 1.

**Self-extension:** add `filter(code -> code.matches("[0-9]{6}"))` if the postal code contract is exactly six ASCII digits. If you need to report “malformed code” clearly, use validation results instead of just empty.

### Exercise B — Get manager ID if present, otherwise fallback

~~~java
String managerId = directory.findManagerId("u1")
        .orElse("NO_MANAGER");
~~~

Result is `"u2"` with the dataset in `OptionalManagerDemo`. If changed to `"u3"`, result is `"NO_MANAGER"`. Although both a missing manager ID and pointing to a non-existent manager ID yield empty, they have **different causes** that the current API does not distinguish.

### Exercise C — Create a message only when parsing succeeds

~~~java
Optional<String> message = parsePositiveInt(" 8 ")
        .map(n -> "quantity=" + n);
~~~

Result is `Optional[quantity=8]`. With `parsePositiveInt("-1")`, the message-building mapper does not run and the result is empty.

### Exercise D — Choosing the right API after obtaining an Optional

You want to:

- Display the user if found, otherwise display an error: `ifPresentOrElse`.
- Compute an expensive default config value when absent: `orElseGet`.
- Pick a second Optional source if the first is empty: `or`.
- Require the profile to exist to continue: `orElseThrow`.
- Convert `Optional<User>` to `Optional<String>` via name: `map`.
- From `Optional<User>`, look up `Optional<Address>`: `flatMap`.

**Note:** If the default is a simple constant, `orElse` has no significant performance issue; avoid turning every fallback into an unnecessarily verbose supplier.

### Exercise E — Write additional test cases yourself

Write tests for `parsePositiveInt` with:

- `"001"` (parses to `1`, returns present Optional).
- `"+2"` (Java `Integer.parseInt` accepts a plus sign, returns `2`).
- `"2.5"` (not an integer, empty).
- `"2147483648"` (exceeds `Integer.MAX_VALUE`, empty).
- `"-2147483648"` (not positive, empty).

**Point to think about:** If the product forbids `+` signs or leading zeros, `Integer.parseInt` still accepts them. In that case, add a **format rule** with a predicate before the parse step; do not assume all syntax that parses successfully is valid by business rules.

## 16. Testing Checklist Before Using Optional in a Project

1. **Which values can be missing?** Identify each layer that may be null or not found.
2. **Should Optional be returned at the API boundary?** Is absence a normal case?
3. **Which steps return ordinary objects and which return Optional?** Choose `map` or `flatMap` matching the type.
4. **Is a mapper allowed to return null?** `map` converts it to empty; `flatMap` rejects it.
5. **Does an empty result after `filter` lose important error causes?**
6. **When is the fallback evaluated?** Distinguish `orElse` from `orElseGet`.
7. **Does the caller need a value, an Optional, an error, or an action?** Choose `orElse...`, `or`, `orElseThrow`, or `ifPresentOrElse`.
8. **Is unchecked `get()` used anywhere?** If so, review the contract.
9. **Are all missing-data layers tested?** Missing at start, missing in middle, blank data, invalid format.
10. **Are there unexpected exceptions?** Optional does not swallow `NullPointerException` in a mapper or `NumberFormatException` during parsing.
11. **Are there side effects in `map`/`filter`?** Limit mutation and external state dependencies.
12. **Does the result share mutable objects with the input?** Optional does not deep-copy.
13. **Is the chain readable?** Extract named methods if needed.
14. **Are there business data/format restrictions?** For example, `parseInt` accepts `+` while a form might forbid it.
15. **Do you need to distinguish absence from failure?** If yes, use a stronger result type than Optional.

## 17. Self-Check Questions

**Question 1.** What does `Optional.ofNullable(null).map(String::strip)` return?

**Question 2.** Why is `findUser(id).flatMap(this::findManager)` more appropriate than `map` if `findManager` returns `Optional<User>`?

**Question 3.** For the string `"   "`, why does `map(String::strip).filter(s -> !s.isEmpty())` return empty?

**Question 4.** How do `Optional.of("x").map(s -> null)` and `Optional.of("x").flatMap(s -> null)` differ?

**Question 5.** Does `Optional.of("ready").orElse(expensive())` always skip `expensive()`?

**Question 6.** When does `orElseGet` invoke its supplier?

**Question 7.** Does `or(Supplier<Optional<T>>)` return `T` or `Optional<T>`?

**Question 8.** What does `parsePositiveInt("abc")` in the example return? Does it report the error cause to the caller?

**Question 9.** Is `ifPresentOrElse` suitable for producing a `String` return value?

**Question 10.** If `Optional<User>` has a user but `map(user -> user.profile().city())` throws NPE, does Optional turn the exception into empty?

**Question 11.** To collect present values from `List<Optional<T>>` using Stream, which method do you use?

**Question 12.** Should `Optional.empty` be used for an “access denied” error if the API must distinguish it from “not found”?

**Answers:**

1. `Optional.empty`; the mapper is not called.
2. Because `flatMap` flattens the Optional returned by the mapper, avoiding `Optional<Optional<User>>`.
3. `strip()` produces `""`, and `filter` discards empty strings.
4. `map` returns empty; `flatMap` throws `NullPointerException`.
5. No. The expression `expensive()` is evaluated before calling `orElse`.
6. Only when the Optional is empty.
7. `Optional<T>`.
8. `Optional.empty`; this API does not preserve the error cause.
9. No; it returns `void`. Use `map`/`orElse` or a value-returning API.
10. No; the exception thrown by the mapper propagates out.
11. `stream().flatMap(Optional::stream)`.
12. No, if they must be distinguished; use an appropriate result/error type.

## 18. Official Reference Documentation

- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `ofNullable`, `map`, `flatMap`, `filter`, `or`, `orElseGet`, `orElseThrow`, `ifPresentOrElse`, and `stream`.
- [Java SE 17 — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): mapping function contract.
- [Java SE 17 — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): zero-argument supplier for fallbacks.
- [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `flatMap`, `toList`, and handling multiple Optionals.
- [Java SE 17 — Integer.parseInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String)): integer syntax and `NumberFormatException`.

**Key takeaway:** In an operation chain that may lack data, use `Optional.ofNullable` at nullable boundaries, `map` for transformations returning **ordinary values**, `flatMap` for steps **already returning Optional**, and `filter` for keep/discard conditions; choose `orElseGet`, `orElseThrow`, `or`, or `ifPresentOrElse` according to output needs. Test every missing layer, do not let `Optional.empty` hide important business errors, and do not confuse Optional with exception catching or mutable-object protection.
