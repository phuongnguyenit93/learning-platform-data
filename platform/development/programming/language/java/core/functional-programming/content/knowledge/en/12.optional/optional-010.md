# The Primary Role of Optional as a Return Value and Limits on Overuse

## 1. What Problem Does Optional Solve?

In Java, **java.util.Optional<T>** is a container object that **may or may not contain a reference value of type T**. It is typically used as a **method return type** when not finding data is a normal, expected outcome and the caller needs to decide how to handle it.

For example, a method that finds a customer by ID:

~~~java
Optional<Customer> findCustomerById(String customerId);
~~~

This is an **illustrative API signature**, not a standalone program. It expresses two possibilities: returning a Customer, or having no corresponding Customer. The caller receives a clear signal in the signature that **having no value** is a state that must be considered. This is often easier to read than returning **Customer** with a convention that "null means not found" documented only in comments or docs.

Optional **does not** guarantee that every error turns into an empty state, nor does it replace validation, exceptions, domain models, or collections. It is a small tool for expressing an **optional result**; overusing it everywhere will make the API complex and sometimes obscure business meaning.

Core mindset:

~~~text
findById(id)
   |
   +-- Valid object found ---> Optional.of(value)
   |
   +-- No matching object ---> Optional.empty()
   |
   +-- System error (I/O, DB, access permission...) ---> handle/report error
                                                         per contract,
                                                         do not treat as "absent"
~~~

**Optional<T> is not synonymous with nullable T:** with a nullable T, the caller can forget to check for null; with Optional<T>, the API explicitly states absence. Even so, the data type does not force the caller to handle it properly in business terms: one can still call **get()** without checking and cause an error.

## 2. When Is Optional a Good Choice for a Return Value?

Some suitable situations:

| Method | When a value is present | When no value is present |
| --- | --- | --- |
| **findUserById(id)** | User found | No user with that ID |
| **findHeader(name)** | Header value exists | Header is absent |
| **lookupCache(key)** | Cache contains the value | Normal cache miss |
| **firstMatching(items)** | Element satisfies condition | No element matches |
| **parseKnownCode(text)** | Recognized code | String not in known catalog |

The examples above are only **contract ideas**, not a guarantee that every implementation uses Optional. When a method may fail to find data and **missing data is not an error**, returning **Optional<T>** helps the caller see this outcome directly in the API.

Conversely, if **a value must exist** according to a business invariant, a method such as **loadRequiredUser(id)** can return User directly and throw an appropriate exception when the data is missing. Returning Optional only for the caller to always write **orElseThrow** sometimes makes the contract less clear.

A useful design question: **"Is an absent object a valid outcome that the caller is entitled to handle differently?"** If yes, Optional is a good candidate. If not, choose a more suitable contract.

### 2.1. Distinguishing Three States

In real systems, it is necessary to distinguish:

1. **Found:** return the value.
2. **Validly not found:** return Optional.empty().
3. **Unable to search due to error:** throw an exception, return a Result type containing an error, or apply a published failure policy.

For example, a data store that loses connection should **not** silently return Optional.empty() as if there were definitely no customer. Doing so hides operational errors and can cause the caller to make wrong decisions.

Optional only represents **two value states**: present or absent. If the business logic needs to distinguish "deleted", "no access permission", "not yet synced", or "pending approval", a single Optional may **not carry enough information**.

## 3. Three Ways to Create Optional: of, ofNullable, empty

### 3.1. Optional.of(value)

**Optional.of(value)** is for a value that is **guaranteed non-null**.

~~~java
Optional<String> city = Optional.of("Hà Nội");
~~~

The snippet requires importing **java.util.Optional**. The inner value is **"Hà Nội"**. If **null** is passed, **of(null)** immediately throws **NullPointerException**. This can be useful when you want to fail fast to detect a violated invariant.

### 3.2. Optional.ofNullable(value)

**Optional.ofNullable(value)** creates an Optional containing the value if the argument is non-null, or Optional.empty() if the argument is null.

~~~java
String nickname = null;
Optional<String> nicknameResult = Optional.ofNullable(nickname);
~~~

This is an illustrative snippet. **nicknameResult.isEmpty()** returns true. This approach is commonly used at **conversion boundaries from legacy nullable-returning APIs** to newer Optional-returning APIs, for example from **Map.get(key)** when null is defined as "not found".

**Do not use ofNullable mechanically** to mask a required non-null value. If a required field is null due to a bug, returning empty() will hide the bug signal.

### 3.3. Optional.empty()

**Optional.empty()** explicitly represents the absence of a value:

~~~java
Optional<String> noNickname = Optional.empty();
~~~

If a method returns **Optional<User>**, it should return **Optional.empty()** when there is no User; **do not** return **null** instead of an empty Optional.

**A convention to uphold:** a method declared to return Optional must return **a non-null Optional** in normal return cases. Returning **null** from an Optional-returning method defeats its design purpose and causes NullPointerException when the caller uses **map**, **orElse**, **isPresent**, and so on.

### 3.4. Quick Comparison

| Factory | Non-null argument | Null argument |
| --- | --- | --- |
| **Optional.of(value)** | Optional containing value | Throws NullPointerException |
| **Optional.ofNullable(value)** | Optional containing value | Optional.empty() |
| **Optional.empty()** | Takes no argument | Always empty |

**Do not accidentally nest Optional:** if a method already returns Optional<T>, wrapping it with **Optional.ofNullable(...)** creates **Optional<Optional<T>>**, which usually makes caller handling more complicated. To combine two Optional lookups, use **flatMap** when appropriate.

## 4. Complete Java 17 Example: Finding Data and Returning Optional

Problem: find a user by ID in a simple repository. Not having the ID is normal, whereas a null ID is considered invalid input. A user may not have declared an email.

Create file **OptionalReturnDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record User(String id, String name, String email) {}

public class OptionalReturnDemo {
    static final Map<String, User> USERS = Map.of(
            "u1", new User("u1", "Lan", "lan@example.test"),
            "u2", new User("u2", "Minh", null)
    );

    static Optional<User> findUser(String id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(USERS.get(id));
    }

    static String displayName(String id) {
        return findUser(id)
                .map(User::name)
                .orElse("Khách");
    }

    static String emailOrDefault(String id) {
        return findUser(id)
                .map(User::email)
                .filter(email -> !email.isBlank())
                .orElse("(chưa có)");
    }

    public static void main(String[] args) {
        System.out.println("find u1: "
                + (findUser("u1").isPresent() ? "Có" : "Không"));
        System.out.println("find ux: "
                + (findUser("ux").isPresent() ? "Có" : "Không"));
        System.out.println("name u1: " + displayName("u1"));
        System.out.println("name ux: " + displayName("ux"));
        System.out.println("mail u1: " + emailOrDefault("u1"));
        System.out.println("mail u2: " + emailOrDefault("u2"));

        List<String> names = List.of("u1", "ux", "u2").stream()
                .map(OptionalReturnDemo::findUser)
                .flatMap(Optional::stream)
                .map(User::name)
                .toList();
        System.out.println("names: " + names);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 OptionalReturnDemo.java
java OptionalReturnDemo
~~~

Stdout:

~~~text
find u1: Có
find ux: Không
name u1: Lan
name ux: Khách
mail u1: lan@example.test
mail u2: (chưa có)
names: [Lan, Minh]
~~~

**Explanation:**

1. **findUser(id)** is the API boundary returning Optional. **Map.get** returns null if the key is absent; **ofNullable** converts this convention into Optional.empty().
2. **Objects.requireNonNull(id)** clearly distinguishes **null input as a contract violation** from **an ID not existing in the data store as a normal outcome**.
3. **displayName** does not need to call **get()**. **map(User::name)** produces Optional<String> if User is found, and **orElse("Khách")** sets the fallback.
4. **emailOrDefault** illustrates that a User can have **email == null**. **map(User::email)** turns a null result into Optional.empty(); **filter** only checks isBlank when a String is present.
5. **Optional::stream** creates a Stream with **0 or 1 element**. **flatMap(Optional::stream)** discards empty lookups and flattens the ones that have a User.
6. The input list has **u1**, **ux** (non-existent), and **u2**, so the final result is **[Lan, Minh]** in the encounter order of the sequential Stream.

**Important:** the **User** class here is an illustrative model. In real applications, an optional email might be modeled using domain rules, validation, or a dedicated object. This example intentionally uses a nullable field in sample data to show how Optional works at the **return boundary**; it **does not recommend** turning every field into Optional.

## 5. Using Optional by Consuming the Value

When receiving **Optional<T>**, the caller typically has these options:

- **map(...)**: transform the value if present.
- **flatMap(...)**: continue with another operation that also returns Optional, avoiding nested Optionals.
- **filter(...)**: keep the value if it satisfies a condition.
- **orElse(...)**: get the value or a pre-evaluated fallback.
- **orElseGet(...)**: lazily produce a fallback using a Supplier.
- **orElseThrow(...)**: turn a missing state into a specified exception.
- **ifPresent(...) / ifPresentOrElse(...)**: perform an action with side effects.
- **stream()**: represent Optional as a 0/1-element Stream.

### 5.1. map(): Transform When Data Is Present

~~~java
Optional<User> maybeUser = findUser("u1");
Optional<String> name = maybeUser.map(User::name);
~~~

This is an illustrative snippet assuming **User** and **findUser** from the example above. If maybeUser is empty, **User::name** is not called. If the mapper returns **null**, **Optional.map** returns Optional.empty(), rather than an Optional containing null.

When you need to convert **User → String** from the same Optional, this is often more readable than:

~~~java
String label = maybeUser.isPresent()
        ? maybeUser.get().name()
        : "Khách";
~~~

This snippet is valid when maybeUser is present, but writing it with **map(...).orElse(...)** expresses the processing chain better and avoids relying on **get()**.

### 5.2. filter(): Check a Condition When a Value Is Present

~~~java
Optional<String> approvedCode = Optional.of("AB-12")
        .filter(code -> code.startsWith("AB-"));
~~~

This is an illustrative snippet. The result contains **"AB-12"**. If the condition is false, the result is empty. If the input Optional is already empty, the Predicate is not called.

Use filter to decide whether to **keep or discard an optional value**, not to replace a full validation workflow with multiple error messages. If an invalid code needs to return a **reason**, using only Optional.empty() will lose that reason.

### 5.3. flatMap(): Avoid Optional<Optional<T>>

Suppose **UserSettingsRepository.findSettings(user)** returns Optional<Settings>. When the user might not exist:

~~~java
Optional<Settings> settings = findUser(id)
        .flatMap(settingsRepository::findSettings);
~~~

This is an **illustrative API snippet**, assuming Settings, repository, and id are already defined. **flatMap** takes a mapper returning **Optional<Settings>** and produces a single Optional<Settings>. If **map** were used, the result type would be **Optional<Optional<Settings>>**.

**Note:** A mapper passed to **Optional.flatMap** must return a **non-null Optional**; if it returns null, Java throws NullPointerException. Unlike **Optional.map**, returning null from an Optional mapper is a contract violation.

### 5.4. ifPresent and ifPresentOrElse

~~~java
findUser("u1")
        .ifPresent(user -> System.out.println(user.name()));
~~~

This is an illustrative snippet: if User is present, run the Consumer; otherwise, do nothing. **ifPresent** returns **void**, not a new Optional for chaining further transformations. Use it when the goal is genuinely an action, such as logging, notifying, or updating UI.

Since Java 9, **ifPresentOrElse(action, emptyAction)** is available:

~~~java
findUser("ux").ifPresentOrElse(
        user -> System.out.println(user.name()),
        () -> System.out.println("Không có người dùng")
);
~~~

This is an illustrative snippet. The program prints **Không có người dùng** in the case where ID ux does not exist. If you need to return a String to the caller instead of performing a side effect, **map(...).orElse(...)** or **orElseGet(...)** is usually more appropriate.

## 6. Distinguishing orElse and orElseGet: Eager vs Lazy

This is an area prone to performance bugs and unintended side effects.

**orElse(fallbackExpression)** takes **a value of type T**. Before the orElse method is called, Java must **evaluate the fallback expression** to compute the argument, even when Optional already has a value. If the fallback is just a cheap literal, this is not a concern.

**orElseGet(supplier)** takes **Supplier<? extends T>**. Java only calls **supplier.get()** when Optional is empty. For expensive fallbacks such as another query, creating a large object, or logging, this is usually the better choice.

Create file **OptionalFallbackDemo.java**:

~~~java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String makeFallback() {
        System.out.println("build fallback");
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> absent = Optional.empty();

        System.out.println("orElse: "
                + present.orElse(makeFallback()));

        System.out.println("orElseGet: "
                + present.orElseGet(OptionalFallbackDemo::makeFallback));

        System.out.println("absent: "
                + absent.orElseGet(OptionalFallbackDemo::makeFallback));

        System.out.println("literal: "
                + present.orElse("constant"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OptionalFallbackDemo.java
java OptionalFallbackDemo
~~~

Stdout:

~~~text
build fallback
orElse: ready
orElseGet: ready
build fallback
absent: fallback
literal: ready
~~~

**Exact interpretation:**

- In **present.orElse(makeFallback())**, makeFallback is called **before** orElse receives its argument, so it prints **build fallback** even though the final returned result is still **ready**.
- In **present.orElseGet(...::makeFallback)**, the supplier is not called because Optional has a value; no second log line appears before **orElseGet: ready**.
- In **absent.orElseGet(...)**, Optional is empty so makeFallback is called and the result **fallback** is used.
- With **orElse("constant")**, evaluating a literal is cheap and simple; there is no need to turn every orElse into orElseGet.

**Common mistake:** using **orElse(database.loadDefault())** and assuming the database is only called when Optional is empty. If the fallback has side effects, that operation still happens even when a value was already found.

### 6.1. or(Supplier<Optional<T>>): A Fallback That Can Still Be Empty

Java 9 added **Optional.or(...)** to choose another Optional **when the first Optional is empty**:

~~~java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.of("backup"));
~~~

This is an illustrative snippet. The result contains **backup**. Unlike **orElseGet**, the supplier for **or** must return an **Optional**, not T directly. It is suitable when you want to try a **secondary lookup source** that might also not find anything:

~~~java
Optional<User> found = findPrimary(id)
        .or(() -> findSecondary(id));
~~~

This is an illustrative API snippet, assuming both functions return Optional<User>. **findSecondary** is only called when **findPrimary** is empty. If the supplier of **or** returns null, Java throws NullPointerException; do not use null as an empty Optional.

## 7. orElseThrow(): Turning Absence into an Error When the Contract Requires It

If the caller **must** have a value, Optional.empty() can be turned into a clear exception:

~~~java
User required = findUser(id)
        .orElseThrow(() ->
                new IllegalArgumentException("Unknown user: " + id));
~~~

This is an illustrative API snippet. The exception is created by the Supplier only when Optional is empty. Use **orElseThrow(Supplier<? extends X>)** if you want an exception with a message/type suited to the caller.

There is also the no-argument **orElseThrow()** (Java 10+), which throws **NoSuchElementException** if Optional is empty. The **get()** method also throws **NoSuchElementException** when empty; however, **get()** is often a sign that the caller has not designed a clear handling strategy.

For example:

~~~java
Optional<String> maybe = Optional.empty();
// maybe.get()             -> NoSuchElementException at runtime.
// maybe.orElseThrow()     -> NoSuchElementException at runtime.
~~~

The snippet above has no compile errors; the two comment lines describe the **runtime** error if uncommented.

**Do not treat orElseThrow as mandatory in every use case:** an API returns Optional so the caller can decide—some callers want a fallback, some want to ignore it, and some want to report an error. Do not turn "not found" into an unnecessary exception if it is simply a normal outcome.

### 7.1. Different from the Question "Is Optional Completely Safer Than null?"

No. Optional helps clarify the contract, but callers can still misuse **get()**, **orElse(null)**, or skip checking. Real safety requires **API design**, **data modeling**, **testing**, **error-handling conventions**, and sometimes nullability analysis together.

## 8. Java 17 Program: map, flatMap, and Modeling Optional Relationships

An order may exist without a shipping address yet. Those are two layers of outcomes: whether the order exists; and if the order exists, whether the address exists. **flatMap** helps avoid nested Optionals.

Create file **OptionalCompositionDemo.java**:

~~~java
import java.util.Map;
import java.util.Optional;

record Address(String city, String postalCode) {}
record Order(String id, Address shippingAddress) {}

public class OptionalCompositionDemo {
    static final Map<String, Order> ORDERS = Map.of(
            "a", new Order("a", new Address("Hà Nội", "10000")),
            "b", new Order("b", null)
    );

    static Optional<Order> findOrder(String id) {
        return Optional.ofNullable(ORDERS.get(id));
    }

    static Optional<Address> shippingAddress(Order order) {
        return Optional.ofNullable(order.shippingAddress());
    }

    static Optional<String> shippingCity(String id) {
        return findOrder(id)
                .flatMap(OptionalCompositionDemo::shippingAddress)
                .map(Address::city);
    }

    public static void main(String[] args) {
        System.out.println("a: "
                + shippingCity("a").orElse("unknown"));
        System.out.println("b: "
                + shippingCity("b").orElse("unknown"));
        System.out.println("x: "
                + shippingCity("x").orElse("unknown"));

        Optional<Optional<Address>> nested = findOrder("a")
                .map(OptionalCompositionDemo::shippingAddress);

        System.out.println("nested present: " + nested.isPresent());

        Optional<Address> flattened = findOrder("a")
                .flatMap(OptionalCompositionDemo::shippingAddress);

        System.out.println("flattened present: "
                + flattened.isPresent());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OptionalCompositionDemo.java
java OptionalCompositionDemo
~~~

Stdout:

~~~text
a: Hà Nội
b: unknown
x: unknown
nested present: true
flattened present: true
~~~

**Meaning:**

1. **findOrder("a")** finds an Order, **shippingAddress** returns an Optional containing Address, and **map(Address::city)** extracts the city.
2. **findOrder("b")** finds an Order without an address; **flatMap** yields Optional.empty().
3. **findOrder("x")** finds no Order; **flatMap** does not call shippingAddress on a non-existent Order.
4. Calling **map** with a method that already returns Optional produces **Optional<Optional<Address>>**, forcing the caller to deal with two layers of Optional.
5. **flatMap** directly produces **Optional<Address>**, matching the intent of "perform the next lookup step if the first value is present".

**A limitation of the illustrative model:** the code uses a nullable **Address** field in the Order record to construct input data and convert it at the method boundary. In real applications, clearly define which fields are allowed to be absent and enforce invariants; do not assume every record that can hold null is a good domain model.

## 9. Optional.stream(): Connecting to Stream Without Manual Checks

Since Java 9, **Optional.stream()** returns:

- A Stream with exactly **one element** if Optional has a value;
- An **empty** Stream if Optional.empty().

Therefore, given a Stream of multiple Optional<T> values, write:

~~~java
List<T> values = optionals
        .flatMap(Optional::stream)
        .toList();
~~~

This is an **illustrative snippet**, assuming **optionals** is a **Stream<Optional<T>>** with an appropriate type T, and List and Optional are imported. It avoids verbose patterns such as **filter(Optional::isPresent).map(Optional::get)**.

When a method itself returns **Stream<T>**, an empty stream is the natural representation when there are no elements; **there is no need** to turn every collection result into Optional<List<T>>. If a method returns **List<T>**, it should usually return an **empty list** (non-null) when there are no elements.

### 9.1. Optional and Stream Are Not the Same

Optional represents **0 or 1 value**, whereas Stream can have **0, 1, or many values** and is typically processed in a pipeline. Do not use Optional<List<T>> just to say "the list may be empty" if an **empty list** already expresses that state. Only use Optional<List<T>> when **"no list / list not provided"** differs in meaning from **"a list exists and it is empty"**; in that case, document both states clearly.

## 10. Limits on Overusing Optional

### 10.1. Do Not Default to Using Optional for Entity/DTO/Record Fields

A data type like the following often complicates initialization, serialization, persistence, and mapping without a clear reason:

~~~java
class PersonDto {
    Optional<String> nickname;
}
~~~

This is a **design example for discussion**, not recommended to copy directly into production code. For a storage DTO or plain data object, it is usually more convenient to use **String nickname** with clear nullability/validation rules, or an appropriate domain type, and return Optional from the accessor method:

~~~java
class Person {
    private final String nickname; // May be null per contract.

    Person(String nickname) {
        this.nickname = nickname;
    }

    Optional<String> nickname() {
        return Optional.ofNullable(nickname);
    }
}
~~~

This is an **illustrative class** requiring an Optional import. This design keeps Optional primarily at the **return boundary**. It also avoids storing **Optional** as mutable field state that could itself be assigned null.

**Do not claim every framework forbids Optional fields.** Some serializers/binders have modules supporting Optional; others do not or handle them differently. The issue is **contract and tooling compatibility**, not a compiler rule that every Optional field is wrong.

**Regarding Java serialization:** java.util.Optional does not implement **java.io.Serializable** in the standard JDK. Therefore, placing Optional directly in an object that requires default Java serialization can cause **NotSerializableException** if that field is serialized. JSON serialization is a separate mechanism, depending on the library and configuration.

### 10.2. Do Not Default to Accepting Optional as a Parameter

For example:

~~~java
void sendMessage(String message, Optional<String> label)
~~~

This is an **illustrative signature**. If the caller always has to create **Optional.of(label)** or **Optional.empty()** just to call it, the API can become verbose and awkward. For an optional parameter, consider **overloading**, a **builder**, an **options object**, or a contract that permits null at an internal boundary when appropriate and well-managed.

For example:

~~~java
void sendMessage(String message);
void sendMessage(String message, String label);
~~~

These are two illustrative signatures. Overloading is not always best: if there are many optional parameters, a builder/options object is usually easier to extend. If the API's true purpose is to **accept an optional result as input**, an Optional parameter can be reasonable; just do not use it out of habit.

### 10.3. Do Not Redundantly Wrap Collections

Compare:

~~~java
List<User> searchUsers(String query);
Optional<List<User>> searchUsersWrapped(String query);
~~~

The two lines above are illustrative signatures. When **no users are found**, returning an empty list with **List.of()** is usually sufficient. Optional<List<User>> pushes an extra handling branch onto the caller without conveying new information.

A case where Optional<List<T>> can be valid is when "**query not yet executed**" differs from "**queried and no results found**". If you need to represent additional states like loading, error, or access permission, a dedicated result type is usually more expressive.

### 10.4. Do Not Use Optional to Replace Every Exception

Do not swallow data-source errors:

~~~java
// Anti-pattern illustration:
try {
    return Optional.of(loadFromDatabase());
} catch (Exception ignored) {
    return Optional.empty();
}
~~~

This is an **intentionally incomplete snippet**, without an enclosing class/method. It is dangerous because it treats every exception as "not found". In addition, **Optional.of(...)** will throw NullPointerException if loadFromDatabase returns null. The caller loses the ability to distinguish **database connection lost**, **corrupted data**, and **ID does not exist**.

Only return empty when there truly is no value. Abnormal errors must be handled according to system policy—appropriate exceptions, retries, error results, and controlled logging/metrics.

### 10.5. Avoid get() After a Verbose Check Chain

Code like the following is often hard to scale:

~~~java
Optional<User> found = findUser(id);
if (found.isPresent()) {
    return found.get().name();
}
return "Khách";
~~~

This is an **illustrative snippet inside a method returning String**. For simple logic, you can write:

~~~java
return findUser(id)
        .map(User::name)
        .orElse("Khách");
~~~

It expresses conditional transformation and fallback while avoiding **get()**. However, an explicit **if/else** is still fine when multiple actions, logging, or complex error handling are needed. There is no rule forcing an entire program to be turned into Optional chains.

### 10.6. Do Not Use Optional for Every Local Expression

The following snippet often creates unnecessary objects/branches:

~~~java
Optional<Integer> sum = Optional.of(a + b);
int result = sum.orElse(0);
~~~

This is an illustrative snippet assuming a and b are ints. If **a + b** always produces an int and there is no concept of absence, keep **int result = a + b;**. Optional is suitable when a return type needs to express absence; it is not a default wrapper for every value.

## 11. Value-Based Class: Do Not Rely on Optional Identity

According to the JDK, **Optional is a value-based class**. Therefore, avoid relying on the **object identity** of Optional instances as part of a contract:

- Do not compare Optionals using **==** to check whether they have the same contents. Use **equals(...)** when comparing values, or better yet, process the contents directly.
- Do not synchronize on **synchronized(optional)**. Java warns that using a value-based object as a monitor may have unreliable behavior in future versions/JVMs.
- Do not rely on **System.identityHashCode(optional)** or on **Optional.empty()** always being one single unique object. The JDK makes no such identity guarantees.

Example:

~~~java
Optional<String> first = Optional.of("A");
Optional<String> second = Optional.of("A");

System.out.println(first.equals(second)); // true
~~~

This is an illustrative snippet requiring an Optional import. **equals** compares contents and returns true for two Optionals containing equal Strings. Using **first == second** is not a semantically valid way to check content equality.

**Another distinction:** Optional itself has no setter to change its present/absent state after creation; however, **the inner value T may be a mutable object**. Holding a mutable List inside Optional **does not** make that List immutable or thread-safe.

## 12. Primitive Optionals and Boxing Cost

When working with primitive values, the JDK provides:

- **OptionalInt** — an int may or may not be present.
- **OptionalLong** — a long may or may not be present.
- **OptionalDouble** — a double may or may not be present.

Example:

~~~java
OptionalInt maybeMax = IntStream.of(2, 5, 1).max();
System.out.println(maybeMax.orElse(-1)); // 5
~~~

This is an illustrative snippet importing **java.util.OptionalInt** and **java.util.stream.IntStream**. If the stream is empty, **max()** returns an empty OptionalInt. **orElse(-1)** is the example's fallback and must be chosen intentionally: if -1 is also valid data, that fallback can be misleading.

Primitive Optional types avoid boxing **Integer**, **Long**, and **Double** in the corresponding APIs. However, **the API of OptionalInt/Long/Double is not identical to Optional<T>**, so do not assume they have all the same **map/flatMap** methods as Optional<T>.

**Do not optimize before measuring:** choose a representation that is both semantically accurate and data-compatible; only consider boxing/performance when the workload genuinely requires it.

## 13. Interaction Boundaries: Frameworks, Libraries, and Public Contracts

When introducing Optional into an API used across multiple modules, consider:

1. **Caller readability:** Optional expresses absence; documentation must clearly state what "absent" means.
2. **Java and libraries:** some frameworks support Optional as a return type (such as repository APIs), while some binders, ORMs, serializers, or schema generators require special configuration. Do not assume uniform support for fields, setters, constructor parameters, and DTOs.
3. **Compatibility:** changing a method from **T get(...)** to **Optional<T> get(...)** is a signature change that affects callers; manage migration/versioning carefully.
4. **Interacting with null:** many legacy Java APIs and third-party libraries still return null; **ofNullable** is useful at boundaries, but preserve the exact meaning of "absent".
5. **Object allocation cost:** avoid creating Optionals in hot loops where there is no meaning of absence; more importantly, choose a clear API and measure before optimizing.
6. **Domain modeling:** if data has more than two business states, consider **enum/record/sealed hierarchy/Result** instead of forcing everything into Optional.

**Do not use Optional where data can legitimately hold null** and treat Optional as a container for a meaningful null: Optional cannot hold null. **Optional.ofNullable(null)** is always empty. If you need to distinguish "not provided" from "explicitly provided as null", those two states require a different data model.

## 14. Comparing API Choices

| Need | Usually suitable choice | Why |
| --- | --- | --- |
| Look up an entity that may not exist | **Optional<User> findById(...)** | Valid absence is stated in the return type |
| Entity must always exist; missing is a violation | **User requireById(...)** + exception | Mandatory contract is clearer |
| Find multiple elements | **List<User> findAll(...)** | An empty list expresses no elements |
| Return a possibly missing numeric value | **OptionalInt/Long/Double** if the API fits | Avoids boxing for primitives |
| Know success/failure with a reason | **Result/record/sealed type** | Optional does not carry error details |
| Data stored in an entity/DTO | Field following domain/framework conventions | Optional fields can increase integration complexity |
| An optional parameter | Overload, options/builder, or appropriate contract | Avoids forcing every caller to wrap in Optional |
| Transform an existing Optional | **map/flatMap/filter** | Avoids repeated get/check |
| Need an expensive fallback | **orElseGet** | Computes fallback only when empty |
| Need a clear error when a value is required | **orElseThrow(supplier)** | Reports violation at the right boundary |

These are **guiding principles**, not absolute prohibitions. Concrete decisions must be based on the contract, framework, and API maintenance cost.

## 15. Testing Optional According to Contract

A small test suite for a method returning Optional should cover **three groups**:

**Value present:**
- For an existing ID, **isPresent()** is true.
- **map(...)** returns the expected content.
- **orElseGet(...)** does not invoke an expensive fallback.

**Value absent:**
- For a non-existent ID, **isEmpty()** is true.
- **orElse(...)** or **orElseGet(...)** returns the expected fallback.
- **orElseThrow(...)** throws the expected exception type and message if the caller requires mandatory data.

**Abnormal data and system states:**
- Null input is handled according to the published precondition (in the findUser example, throws NullPointerException via requireNonNull).
- Database errors are not mistakenly converted into Optional.empty().
- If a mapper or predicate throws an error, Optional does not automatically "swallow" it.
- A method declared to return Optional never returns null upon normal completion.

Example of testing fallback behavior:

~~~java
AtomicInteger calls = new AtomicInteger();
Optional<String> present = Optional.of("value");

String result = present.orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});

System.out.println(result);      // value
System.out.println(calls.get()); // 0
~~~

This is an **illustrative snippet** importing **java.util.Optional** and **java.util.concurrent.atomic.AtomicInteger**. It shows that the supplier is not called when Optional has a value. In real unit tests, use assertions to verify these conditions automatically.

### 15.1. Questions to Distinguish Optional from Validation

Suppose an API accepts `age` or an ID string:

- **No user for a valid ID:** Optional.empty() may be appropriate.
- **Null or malformed ID:** requires separate validation rules; do not turn every input error into empty() by default.
- **User data exists but email is missing:** can represent the missing email in an appropriate API returning Optional<String>.
- **Unable to access repository:** must report a connection/authorization error per contract; not "not found".

A good API helps callers distinguish these states, avoiding treating an empty return as a solution for every failure case.

## 16. Exercises

### Exercise 1: Designing Return Types

For three methods—finding a user by ID, getting all users in a group, and getting a required user for a transaction—choose among **Optional<User>**, **List<User>**, and **User + exception**. Explain whether absence is a valid outcome for each method.

### Exercise 2: Removing Unnecessary get()

Convert:

~~~java
Optional<User> user = findUser(id);
if (user.isPresent()) {
    return user.get().name();
}
return "Khách";
~~~

This is an illustrative snippet inside a method returning String. Use **map** and **orElse** to express the same logic more concisely, then test both an existing ID and a non-existent ID.

### Exercise 3: Predicting orElse and orElseGet

Create **Optional.of("ok")**, pass a call that logs to **orElse**, and then pass the corresponding Supplier to **orElseGet**. Which one invokes the fallback? When changed to Optional.empty(), how does the behavior differ?

### Exercise 4: map or flatMap?

Given **Optional<Customer>** and a function **Optional<Address> addressOf(Customer)**, write both approaches using map and flatMap and identify the result type of each. Why is flatMap usually more convenient when you want to continue by getting **Address.city()**?

### Exercise 5: Avoiding Overuse of Optional<List<T>>

An API **searchProducts(query)** returns **Optional<List<Product>>** but always uses Optional.empty() when no products are found. Redesign it with **List<Product>**, returning **List.of()** when nothing is found, and only use Optional if there is genuinely a need to distinguish two kinds of absence.

### Exercise 6: Modeling Errors

A product price lookup API may encounter **product not found**, **no read permission**, or **connection lost**. Identify which state can return Optional.empty() and which states require an exception or a richer Result type. Do not confuse "not found" with "unable to query".

## 17. Checklist Before Introducing Optional into an API

1. **Is there a return value that can validly be absent?** If not, Optional may not be needed.
2. **Is "not found" distinct from system errors?** Preserve error information.
3. **Can an empty collection be returned instead of Optional<Collection>?** If the two states do not differ in meaning, use an empty collection.
4. **Are you placing Optional on a return type, or unconsciously putting it into fields/parameters?** Consider compatibility with serializers, ORMs, and callers.
5. **Are you using unchecked get() or orElse(null)?** Review the caller's contract.
6. **Does the fallback have side effects or high cost?** Consider orElseGet instead of orElse.
7. **Does the mapper already return Optional?** Use flatMap to avoid nested Optionals.
8. **Do you need to explain why something failed?** Optional only represents present/absent; another data type may be needed.
9. **Are you relying on Optional's identity or monitor?** Avoid this because it is a value-based class.
10. **Have you tested present, empty, and error branches?** Do not use only the success case to conclude the API is correct.

## 18. Key Takeaways

**Optional<T> should be understood primarily as a tool for describing valid absence in a method's return value.** It helps callers choose how to proceed: map, flatMap, filter, fallback, ignore, or explicitly throw an exception. The factories **of**, **ofNullable**, and **empty** help distinguish present values, nullable values from external sources, and no value.

**Do not treat Optional as a default wrapper for fields, parameters, every collection result, or every local variable.** Those places can increase integration cost, cause serialization/ORM issues, and obscure data invariants. An empty Optional is also not a way to represent every kind of error.

A question to self-check your design: **"If the method cannot return T, is that a valid absence that the caller has the right to handle, or an error/business state that needs to be described more clearly?"** Answering this question will help you use Optional where it belongs and avoid overuse.
