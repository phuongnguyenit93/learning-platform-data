# When Deconstruction Loses Context in Java Record Patterns

## 1. Mental model: structured data also carries meaning

**Deconstruction** is the act of breaking down a record into the components declared in that record. Starting with Java 21+, record patterns let you deconstruct right at the point of a structural check, such as in `instanceof` or `switch`.

Suppose an order has a customer and a shipping address; the customer in turn has a contact address:

```text
Order(orderId, customer, shippingAddress)
  ├── Customer(customerId, contactAddress)
  │     └── Address(city, country)     ← contact address
  └── Address(city, country)           ← shipping address
```

The two leaf nodes both have type `Address`, yet they serve **different roles**. The city of the contact address is not necessarily the shipping city; the customer ID is not the order ID. The record structure tells us **which object** a piece of data belongs to, **what it is used for**, and how the parts relate to one another.

We can extract all values in a single expression:

```java
if (source instanceof Order(
        var orderId,
        Customer(var customerId, Address(var contactCity, var contactCountry)),
        Address(var shippingCity, var shippingCountry))) {
    // Six component variables are available to process.
}
```

This syntax is valid when `Order`, `Customer`, and `Address` are records with the corresponding component counts and order. However, once only six standalone variables are used, the reader has to remember on their own that `contactCity` belongs to `customer.contactAddress()` and `shippingCity` belongs to `order.shippingAddress()`.

**"Losing context" here is a risk in code design and readability:** we deconstruct too early or too deeply and carry disconnected values into downstream logic, making parent–child relationships, business roles, and data provenance hard to see. Java itself **does not delete the original object or strip metadata** when executing a record pattern; if you still hold a reference to the record, you can still use that record. The problem happens when the code that follows no longer keeps or uses those semantically meaningful references.

## 2. How record patterns work and their limits

Consider these records:

```java
record Address(String city, String country) {}
record Customer(String customerId, Address contactAddress) {}
record Order(String orderId, Customer customer, Address shippingAddress) {}
```

The pattern `Order(var id, var customer, var destination)` checks that the outermost object is an `Order` and binds its components in **exact declaration order**. The inferred type of `customer` is `Customer`, and `destination` is `Address`. The pattern only describes structure and binding; it **does not understand** that "destination" means the delivery location or that "contact" is the contact address. Those meanings are established by component names, domain types, and the program's processing logic.

If we go deeper:

```java
if (source instanceof Order(
        var id,
        Customer(var customerId, Address(var homeCity, var homeCountry)),
        Address(var deliveryCity, var deliveryCountry))) {
    // Cities and countries can be processed directly.
}
```

Several important facts apply:

- A deep pattern only matches when the outermost record and all required nested records actually match; if `Customer` or `Address` is `null`, the corresponding record pattern does not match.
- A component like `var city` **can still be `null`** if the `Address` object exists but `city` is `null`. Record patterns do not replace data validation.
- Variable names like `homeCity` and `deliveryCity` are chosen by the author; the compiler extracts components by **position**, not by inferring meaning from variable names.
- Pattern-bound variables are in scope according to Java's flow-scoping rules. You cannot use them arbitrarily in every branch, especially after a branch where the pattern might fail.
- Once intermediate nodes are omitted from the processing block—for example, by not binding a `Customer customer` variable—you have to rely on variable names or keep the input reference if you want to recover the relationships between values.

Record patterns are a standard feature as of **Java 21 (JEP 440)**. They are well-suited for extracting the components you need, not a reason to flatten the entire object graph everywhere.

## 3. Five situations where context is easily lost

### 3.1. Losing provenance: a value is no longer tied to the record that produced it

The following code uses fairly clear variable names, but the `sendReport` method only accepts individual strings:

```java
// Conceptual illustration: sendReport is an application method.
if (source instanceof Order(var orderId,
        Customer(var customerId, var contactAddress),
        var shippingAddress)) {
    sendReport(orderId, customerId,
            contactAddress.city(), shippingAddress.city());
}
```

Across the method boundary, both cities have type `String`. If the receiver no longer has the `Address` objects or sufficiently clear parameter names, it is easy to swap the contact location and the shipping location. Moreover, the pattern above allows `contactAddress == null` or `shippingAddress == null`: calling `.city()` can throw a `NullPointerException`. The outermost pattern matching **does not prove** that every child record is non-`null`.

A clearer approach for business logic that needs to distinguish the roles of the two addresses is to pass the whole records with meaningful parameter names—for example, `sendReport(Order order)` or `sendReport(Address contactAddress, Address shippingAddress)`—and then validate the needed data in the appropriate place. This is an API design decision; Java does not prevent you from passing raw strings.

### 3.2. Losing group boundaries: values belonging to the same concept are separated

Suppose `Price(amount, currency)` represents a monetary price. If you deconstruct two `Price` instances (the original price and the sale price) into `originalAmount`, `originalCurrency`, `saleAmount`, and `saleCurrency`, Java still allows mixing up `saleAmount` with `originalCurrency` in operations that only work with `BigDecimal` and `String`. The mismatched pair is still type-valid, yet wrong for the domain.

```java
// Suppose Offer has two Price components: original and sale.
if (source instanceof Offer(
        Price(var originalAmount, var originalCurrency),
        Price(var saleAmount, var saleCurrency))) {
    // Warning: pairing saleAmount with originalCurrency mixes up roles.
    // Not a type error if both currencies are String.
}
```

If the business logic needs to forward **a complete price**, you should keep `Price` as a unified value:

```java
if (source instanceof Offer(var originalPrice, var salePrice)) {
    // Illustrative example: pass salePrice as a Price,
    // instead of passing amount and currency separately.
}
```

The two blocks above are **illustrative snippets**, not standalone programs: declarations for `Price`, `Offer`, and `source` are required. The key idea is that data such as an amount and its currency should travel together across API boundaries, especially when validation or formatting rules are tied to the domain type.

### 3.3. Losing role distinction when two branches share the same shape

Both `contactAddress` and `shippingAddress` have the shape `Address(String city, String country)`. If you write:

```java
if (source instanceof Order(var id,
        Customer(var customerId, Address(var cityA, var countryA)),
        Address(var cityB, var countryB))) {
    System.out.println(cityA + " / " + cityB);
}
```

You are forced to remember that `A` is contact and `B` is shipping. The issue gets worse if component order changes during a refactoring: components of the same type can swap meanings while the code still compiles. Role-revealing names (`contactCity`, `shippingCity`) reduce the risk, while keeping `Address contactAddress` and `Address shippingAddress` also keeps the relationship visible when reading the code.

### 3.4. Losing the ability to distinguish why a match failed

A deeply nested pattern can fail to match for several reasons: the input is not an `Order`; the order is missing a customer; the customer is missing a contact address; or the order is missing a shipping address. If you only write:

```java
if (source instanceof Order(
        var id,
        Customer(var customerId, Address(var contactCity, var contactCountry)),
        Address(var shipCity, var shipCountry))) {
    // Process complete data.
} else {
    // All non-matching causes end up here.
}
```

The `else` branch does not tell you which record was missing. When business logic needs to report an exact error or accept partial data, deconstructing everything at once can **hide the ability to branch level by level**. One solution is to check `Order` first, keep `order`, and then check `customer`, `contactAddress`, and `shippingAddress` separately.

### 3.5. Losing domain semantics when data travels far

A record can be a *value object* carrying invariants in its constructor and its own methods: `Money` ensures a valid currency unit, `DateRange` ensures the start is not after the end, and `Address` may provide a formatting method. After deconstruction, detached values like `amount`, `currency`, or `start`, `end` do not carry along the API and semantics attached to the original record.

**It is not that validated invariants are erased from the object**, but rather that the receiver of detached values may lack the types and APIs needed to maintain or apply those rules. If an operation works with the whole concept, pass the record instead of a list of same-typed parameters that are easy to confuse.

## 4. Complete example: comparing deep deconstruction and preserving context

Save the following program to **`DeconstructionContextDemo.java`**. The code and printed data use ASCII characters so output renders consistently across terminals; the explanations are in English.

```java
public class DeconstructionContextDemo {
    record Address(String city, String country) {}
    record Customer(String customerId, Address contactAddress) {}
    record Order(String orderId, Customer customer, Address shippingAddress) {}

    // Extract all components three levels deep in a single pattern.
    static String allAtOnce(Object source) {
        if (source instanceof Order(
                var id,
                Customer(var customerId, Address(var contactCity, var contactCountry)),
                Address(var shipCity, var shipCountry))) {
            return id + ": customer=" + customerId
                    + " contact=" + contactCity + "/" + contactCountry
                    + " ship=" + shipCity + "/" + shipCountry;
        }
        return "No complete structure";
    }

    // Keep Order, Customer, and Address to make parent-child relationships clear.
    static String preserveLinks(Object source) {
        if (!(source instanceof Order order)) {
            return "Not an order";
        }
        Customer customer = order.customer();
        Address destination = order.shippingAddress();
        if (customer == null) {
            return order.orderId() + ": missing customer";
        }
        if (destination == null) {
            return order.orderId() + ": missing shipping address";
        }
        Address contact = customer.contactAddress();
        if (contact == null) {
            return order.orderId() + ": missing contact address";
        }
        return order.orderId() + ": ship=" + destination.city()
                + " / contact=" + contact.city();
    }

    // Deconstruct only the outer level; the two child records keep their roles.
    static String selective(Object source) {
        if (source instanceof Order(var id, var customer, var destination)
                && customer != null && destination != null) {
            return id + ": customer=" + customer.customerId()
                    + ", ship=" + destination.city();
        }
        return "Insufficient data";
    }

    public static void main(String[] args) {
        Order full = new Order("O-101",
                new Customer("C-9", new Address("Ha Noi", "VN")),
                new Address("Da Nang", "VN"));
        Order missingContact = new Order("O-102",
                new Customer("C-9", null),
                new Address("Da Nang", "VN"));

        System.out.println(allAtOnce(full));
        System.out.println(preserveLinks(full));
        System.out.println(selective(full));

        System.out.println(allAtOnce(missingContact));
        System.out.println(preserveLinks(missingContact));
        System.out.println(selective(missingContact));

        System.out.println(preserveLinks("other"));
        System.out.println(selective(new Order("O-103", null,
                new Address("Hue", "VN"))));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 DeconstructionContextDemo.java
java DeconstructionContextDemo
```

Exact output:

```text
O-101: customer=C-9 contact=Ha Noi/VN ship=Da Nang/VN
O-101: ship=Da Nang / contact=Ha Noi
O-101: customer=C-9, ship=Da Nang
No complete structure
O-102: missing contact address
O-102: customer=C-9, ship=Da Nang
Not an order
Insufficient data
```

### Explaining each approach

**`allAtOnce`** introduces six variables in a single pattern. It is very concise when the exact requirement is to display both addresses, but when the contact address is `null`, the deep pattern fails; the message `No complete structure` does not indicate which node is missing. There is also no `customer` or `destination` variable bound directly for further record-level handling, so the body easily drifts into working only with strings.

**`preserveLinks`** checks only `Order` in the first step, then keeps the variables `Customer customer`, `Address destination`, and `Address contact`. This lets you place `null` checks at the exact link in the chain and explain which data is missing. Values continue to flow through role-named accessors: `order.shippingAddress()` and `customer.contactAddress()`.

**`selective`** deconstructs `Order` one level deep, keeping the two child records intact. When only the customer ID and shipping address are needed, it can still process order `O-102` even though the customer has no contact address. As a result, the method's data requirements are clearer: it only requires `customer` and `destination`, not `customer.contactAddress`.

No single approach is always best: choose the deconstruction depth based on **the operation you actually need to perform** and the level of context you need to retain. Objects do not "disappear" from the heap because of `allAtOnce`; we simply did not bind intermediate variables in that pattern.

## 5. How to preserve context while still using pattern matching

### 5.1. Stop at the right level

If you only need the shipping address, do not extract the contact address:

```java
if (source instanceof Order(var orderId, var customer, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(orderId + ": " + shippingAddress.city());
}
```

This is an illustrative snippet based on the records in Section 4. It keeps `Customer` as a separate node and does not require a contact address to exist.

### 5.2. Name by role, not by generic type

The names `city1` and `city2` share the same type and lack information about where they are used. `contactCity` and `shippingCity` communicate much more. Similarly, for `Price`, use `originalPrice` and `salePrice`; for `DateRange`, use `startDate` and `endDate` instead of `first` and `second`.

Clear variable names are one layer of protection, but when multiple fields of the same type are passed across methods or classes, **domain types** are usually more reliable than a list of primitive parameters.

### 5.3. Keep the parent or child record in branches that still need it

```java
if (source instanceof Order order) {
    Customer customer = order.customer();
    Address destination = order.shippingAddress();

    if (customer != null && destination != null) {
        // Order, Customer, and Address are all available for further processing.
    }
}
```

With this style, `order.orderId()`, `customer.customerId()`, and `destination.country()` always show the relationship between the data and its owning object. You can also extract one level with `Order(var id, var customer, var destination)` if you prefer record pattern syntax.

Java 21 does not provide a general `as` syntax to **both bind the record itself at that node and deconstruct all its components within the same record pattern**. Therefore, when you need to keep the parent record for multiple operations, declaring a record variable via a type pattern (`source instanceof Order order`) is a readable approach.

### 5.4. Validate business conditions after deconstruction

A matching pattern does not prove that a string has content, that a country is on an allowlist, or that an address is deliverable. For example:

```java
if (source instanceof Order(
        var id, var customer, Address(var city, var country))
        && city != null && !city.isBlank()
        && "VN".equals(country)) {
    System.out.println("Ship to " + city + " for order " + id);
}
```

Here, `Address(...)` requires the shipping address to be a matching record; the conditions after `&&` validate the data for business rules. If an address is only used for display, you can keep `Address shippingAddress` intact and call a validation or formatting method on that type.

### 5.5. Keep value groups together across method boundaries

Consider methods that accept `Price` or `Address` if the processing needs the whole concept, especially when validation is required and values pass through multiple layers. Passing individual fields like `String city`, `String country`, `BigDecimal amount`, and `String currency` is more appropriate when the API truly only uses individual fields and parameter names are already unambiguous.

Choose the minimum level that carries **enough meaning**; there is no need to pass an entire `Order` into a method that only formats an `Address`. Keeping the smallest record that holds the related data is a useful balance.

## 6. Decision table: how deep should you deconstruct?

| Problem | Approach | Reason |
| --- | --- | --- |
| Print a single deep field when all data is required | Nested record pattern | Concisely expresses the required structure |
| Handle contact and shipping addresses together | Keep two `Address` variables by role or use very clear variable names | Avoids confusing two branches of the same type |
| Need to report the specific reason for missing data | Check level by level, keeping intermediate record variables | Distinguishes a missing `Customer` from a missing `Address` |
| Need to pass a price through multiple processing layers | Keep `Price/Money` as a value object | Preserves the amount/currency grouping and associated API |
| Need only the order ID and shipping address | Deconstruct `Order` one level, keeping `Address` | Does not require the contact address to exist |
| Deep graph, multiple optional branches, or changing rules | Split into clearly named steps/methods | Easier to check conditions and maintain |

A simple rule of thumb: if a pattern introduces multiple variables of the same type (`id1`/`id2`, `cityA`/`cityB`, `amount1`/`amount2`) and the body passes them through several methods, ask yourself whether the original records would communicate the meaning better.

## 7. Common misconceptions and pitfalls

1. **"Deconstruction makes the object disappear."** False. A record pattern matches structure and binds components; it does not delete the object. Context is lost when downstream code uses only detached components and drops relationships at the code design level.
2. **"Deep deconstruction is always better because it takes fewer lines."** False. A short pattern can make required data conditions overly strict or lump many different failure causes into a single `else` branch.
3. **"Two records of the same type can be safely swapped."** False in business terms, even if the compiler does not catch it. `contactAddress` and `shippingAddress` share the `Address` type but have different roles.
4. **"Record patterns validate that values are valid."** No. They do not automatically check for blank strings, country rules, amount-currency consistency, or custom business constraints.
5. **"A `var` pattern is always non-`null` when it matches."** No. If the enclosing record exists, a reference-type component can be `null`, whereas a `null` child record itself will not match a nested record pattern.
6. **"Using a deep pattern means you don't need to check child fields."** No. If you use `Order(var id, var customer, var destination)`, `customer` and `destination` can still be `null`. Calling accessors must be guarded according to the input data.
7. **"Variable names determine component positions."** No. The order inside `RecordName(...)` must match the record's component order. Be careful when multiple components share the same type: renaming variables does not make Java swap roles automatically.
8. **"To keep the parent record, you must give up pattern matching."** False. You can use `instanceof Order order` to keep the record itself, or use `Order(var id, var customer, var destination)` to keep the child records instead of going deeper immediately.

## 8. Self-check exercises

**Exercise 1 — Reading structure.** Given `Order("O-102", Customer("C-9", null), Address("Da Nang", "VN"))`, why does the pattern `Order(var id, Customer(var cid, Address(var city, var country)), var destination)` fail to match? **Answer:** `Customer`'s `contactAddress` is `null`, so it does not match `Address(...)`, even though `shippingAddress` exists.

**Exercise 2 — Choosing deconstruction depth.** A feature only needs `orderId` and `shippingAddress.country()` to select a shipping region. Should it also deconstruct `Customer.contactAddress`? **Answer:** No; checking `Order` and the shipping address is enough. Requiring a contact address would reject orders that the feature is otherwise capable of handling.

**Exercise 3 — Spotting role mix-ups.** A method receives both `contactCity` and `shippingCity` as `String`. A shipping fee check accidentally uses `contactCity`. Will the compiler necessarily report an error? **Answer:** No. The bug is in business semantics; keeping or passing a parameter named `shippingAddress` makes it much easier to spot.

**Exercise 4 — Keeping data groups together.** Given `record Price(BigDecimal amount, String currency)`, which choice is better if a method needs to calculate and display a complete price: passing `Price` or passing two separate parameters? **Suggested answer:** Pass `Price` when you need to preserve the amount/currency relationship, validation, and price API; pass individual fields only if the API truly needs each value separately and the method contract is already clear.

**Exercise 5 — Distinguishing missing data.** In the Section 4 program, why does `selective(missingContact)` still produce a valid result while `allAtOnce(missingContact)` does not? **Answer:** `selective` does not require `Customer.contactAddress` to exist; `allAtOnce` requires a nested `Address` inside `Customer` in order to deconstruct it.

## 9. Key takeaways

Deconstruction helps **clearly express the shape to match** and extract data right where it is used. It starts to **lose context in code design** when we deconstruct too deeply or too early, keeping only same-typed values while dropping parent–child relationships, roles, and domain data groups. Deconstruct only as far as the operation requires, choose names that reflect provenance, keep intermediate records when needed, check `null` at the right level, and pass whole value objects across API boundaries when the relationship between components matters.

**References:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
