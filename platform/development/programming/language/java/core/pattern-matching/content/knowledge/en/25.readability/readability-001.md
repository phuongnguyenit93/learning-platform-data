# Domain-Driven Naming for Pattern Variables in Java Pattern Matching

## 1. Why Do Variable Names in Patterns Matter?

Pattern matching lets Java check an object's type and extract its components directly inside a condition. However, concise syntax **does not automatically make code readable**: readers still need to know which business concept each variable represents, where it comes from, and what it is used for.

Consider an object representing a shipping update event:

```java
record Address(String city, String countryCode) {}
record ShippingUpdated(String orderId, Address shippingAddress) {}
```

The same destructuring can be written in two ways:

```java
// Too generic: the reader has to trace back the record structure.
if (candidate instanceof ShippingUpdated(var x, Address(var a, var b))) {
    System.out.println(x + " -> " + a + "/" + b);
}
```

```java
// Names reflect the business role of each value.
if (candidate instanceof ShippingUpdated(
        var orderId,
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(orderId + " -> "
            + shippingCity + "/" + shippingCountryCode);
}
```

Both snippets have the **same matching mechanism** and can produce the exact same output. However, the second version clearly shows: `orderId` is the order identifier, `shippingCity` is the delivery city, and `shippingCountryCode` is the country code of the shipping address.

**Domain-driven naming for pattern variables** means naming pattern-bound variables according to the **role, origin, and meaning of the data in the business domain**. Do not name them merely after Java types (`String`, `Address`) or positions (`a`, `b`), and do not add overly long adjectives that carry no useful information.

This lesson belongs to the **Readability** group in Java Core Pattern Matching. The examples use Java 21+ because record patterns and pattern matching for `switch` were standardized in Java 21 (JEP 440, JEP 441). Type patterns in `instanceof` have been standard since Java 16.

## 2. What Is a Pattern Variable? Does the Variable Name Change How Matching Works?

A **type pattern** declares a typed variable after a type check succeeds:

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    System.out.println(shippingEvent.orderId());
}
```

Here:
- `ShippingUpdated` is the **type to test against**.
- `shippingEvent` is the **pattern variable**, usable only in regions where the compiler knows the pattern has matched.
- The name `shippingEvent` indicates that this is an **event**, not an address or an order entity itself.

A **record pattern** can destructure each component declared in a record:

```java
if (candidate instanceof ShippingUpdated(
        var orderId, var shippingAddress)) {
    // orderId is inferred as String.
    // shippingAddress is inferred as Address.
}
```

In the expression above, `orderId` and `shippingAddress` are variables bound by `var` component patterns. Java infers their types from the declaration `record ShippingUpdated(String orderId, Address shippingAddress)`.

**Core rule:** a record pattern matches subpatterns against record components by **declaration order**, not by variable name. Renaming `orderId` to `foo` does not make the compiler extract a different component; it only makes the meaning harder to read. Conversely, writing a name that looks role-appropriate **does not fix the position** if components of the same type are swapped.

```java
record Transfer(String senderAccountId, String receiverAccountId) {}

// WRONG in terms of naming semantics: two String variables are still valid at the type level.
if (candidate instanceof Transfer(
        var receiverAccountId, var senderAccountId)) {
    // receiverAccountId actually comes from the senderAccountId component!
}
```

This is an illustrative snippet, assuming `candidate` is already declared. Because both components are `String`, the compiler will not necessarily catch a role-swapping bug. Reading the record declaration carefully and verifying business logic is more important than relying solely on type checking.

## 3. From "Type-Based Names" to "Domain-Role Names"

A practical rule: **the type tells you what the data is technically; the variable name tells you what role the data plays in the case being handled**.

| Static type / position | Low-information name | Domain-contextual name | Meaning |
| --- | --- | --- | --- |
| `String` in order component | `s`, `id` | `orderId` | Distinguishes order ID from customer ID |
| `String` in customer component | `x`, `id2` | `customerId` | Avoids confusion with `orderId` |
| `Address` in customer | `address`, `a` | `contactAddress` | Data used for contact |
| `Address` in shipping | `address`, `a2` | `shippingAddress` | Delivery destination |
| `String` contact city | `city1` | `contactCity` | City of the contact address |
| `String` shipping city | `city2` | `shippingCity` | City of the shipping address |
| `long` money in cents | `amount`, `n` | `amountInCents` | Clarifies the unit, avoiding confusion between cents and major currency units |
| `String` currency code | `code`, `c` | `currencyCode` | Distinguishes from country code or status code |
| `String` cancellation reason | `reason`, `r` | `cancellationReason` | Reason belonging to a cancellation event |
| `String` request ID | `id`, `x` | `requestId` | Avoids confusion with `orderId` |

**The level of detail depends on scope.** If a method has only one `Address` and the entire method handles the shipping address, `shippingAddress` is very clear; if the method handles two addresses at the same time, you must distinguish `contactAddress` and `shippingAddress`. On the other hand, a name like `shippingAddressCityStringValue` is redundant because it over-explains and repeats the technical type.

Names should:
- Use nouns/noun phrases that match the concept: `orderId`, `placedEvent`, `customerId`.
- Express the role in branches with the same type: `contactCity` vs. `shippingCity`.
- Include the unit or scale when unit errors have consequences: `amountInCents`, `durationMillis`.
- Not "lie" about the structure: a `ShippingUpdated` variable is an event, so do not name it `order` if it is not an `Order` record.
- Follow Java `lowerCamelCase` naming conventions, consistent with the codebase and domain terminology.
- Stay short enough within local scope, yet distinct enough that readers do not have to trace back through multiple pattern levels.

## 4. When Multiple Records Share the Same Type: Add Origin to the Name

One of the hardest situations to read is **nested record patterns containing components of the same type**.

Suppose:

```java
record Address(String city, String countryCode) {}
record Customer(String customerId, Address contactAddress) {}
record DeliveryRequest(String requestId, Customer customer, Address shippingAddress) {}
```

Nested pattern:

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId,
                Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(requestId
            + ": contact=" + contactCity
            + ", ship=" + shippingCity);
}
```

The variables are named along the **path through the model**:

```text
DeliveryRequest
  ├── requestId
  ├── customer: Customer
  │   ├── customerId
  │   └── contactAddress: Address
  │        ├── contactCity
  │        └── contactCountryCode
  └── shippingAddress: Address
       ├── shippingCity
       └── shippingCountryCode
```

With a single glance at the `if` body, the reader understands why `contactCity` and `shippingCity` can differ. Both variables are `String`, but their names show the origin and role of each value. Type checking cannot replace this semantic clarity.

An overly abbreviated pattern:

```java
if (candidate instanceof DeliveryRequest(
        var id1, Customer(var id2, Address(var c1, var cc1)),
        Address(var c2, var cc2))) {
    // Reading further requires remembering which branch c1 belongs to.
}
```

The code is syntactically valid, but cognitive load increases when adding logic: calculating shipping fees using `c1` instead of `c2` will still compile if both are strings. Domain names do not eliminate all bugs, but they help code reviews and tests focus on the actual meaning.

## 5. Domain Naming and Destructuring Depth: Do Not Lose the Original Object Too Early

Not every problem requires extracting every component in a single pattern. When business logic still uses the API or rules of a child record, you can **keep the child record** instead of extracting only primitive fields.

### Over-destructuring

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId, Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    // 6 separate variables. Calling a method on Address requires an extra reference.
}
```

### Keeping Objects by Their Roles

```java
if (candidate instanceof DeliveryRequest(
        var requestId, var customer, var shippingAddress)) {
    // customer: Customer; shippingAddress: Address.
    if (customer != null && shippingAddress != null) {
        System.out.println(requestId + " -> " + shippingAddress.city());
    }
}
```

These are illustrative snippets based on the records defined in the previous section. Naming `shippingAddress` instead of `address` allows the body to continue accessing `shippingAddress.countryCode()` and passing this record to a shipping API; `customer` remains an entity that can hold `contactAddress`.

When you only need the entire record of a subtype, a **type pattern** is even more concise:

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    Address shippingAddress = shippingEvent.shippingAddress();
    // Both the event and the address are available, both named according to their roles.
}
```

You cannot rely solely on variable naming to "attach" the entire parent object if the pattern only binds its components. Java 21 has no general record pattern syntax that simultaneously binds a name to the parent record at that node and destructures all components like an `as` clause. When you need to keep the parent record, use a type pattern such as `instanceof ShippingUpdated shippingEvent`, or keep an appropriately typed input reference.

**Rule:** only destructure to the depth where the data is actually used; domain names for components **and** domain names for intermediate records are both valuable.

## 6. Complete Java 21 Example: Naming Variables by Business Semantics

The following program demonstrates type patterns, record patterns, nested patterns, `switch` with `when`, role-based naming, and missing-data branches. Save it to **`DomainPatternNamesDemo.java`**.

```java
public class DomainPatternNamesDemo {
    record Address(String city, String countryCode) {}
    record Customer(String customerId, Address contactAddress) {}
    record Money(long amountInCents, String currencyCode) {}
    record DeliveryRequest(String requestId, Customer customer, Address shippingAddress) {}

    sealed interface OrderEvent permits OrderPlaced, ShippingUpdated, OrderCancelled {}
    record OrderPlaced(String orderId, Customer customer, Money total) implements OrderEvent {}
    record ShippingUpdated(String orderId, Address shippingAddress) implements OrderEvent {}
    record OrderCancelled(String orderId, String cancellationReason) implements OrderEvent {}

    static String describe(Object candidate) {
        return switch (candidate) {
            case null -> "unknown:null";

            // Variables express the order, customer, and currency unit.
            case OrderPlaced(
                    var orderId,
                    Customer(var customerId, var contactAddress),
                    Money(var amountInCents, var currencyCode))
                    when amountInCents >= 0 ->
                    "order=" + orderId + " customer=" + customerId
                    + " totalCents=" + amountInCents + " " + currencyCode;

            // Keep customer and total if the deeper pattern does not match.
            case OrderPlaced(var orderId, var customer, var total) ->
                    "placed:incomplete:" + orderId;

            // Shipping address: do not confuse with contact address.
            case ShippingUpdated(
                    var orderId, Address(var shippingCity, var shippingCountryCode)) ->
                    "shipping:" + orderId + " to "
                    + shippingCity + "/" + shippingCountryCode;

            case ShippingUpdated(var orderId, var shippingAddress) ->
                    "shipping:missing:" + orderId;

            case OrderCancelled(var orderId, var cancellationReason) ->
                    "cancelled:" + orderId + " reason=" + cancellationReason;

            default -> "unknown:type";
        };
    }

    static String addresses(Object candidate) {
        if (candidate instanceof DeliveryRequest(
                var requestId,
                Customer(var customerId,
                        Address(var contactCity, var contactCountryCode)),
                Address(var shippingCity, var shippingCountryCode))) {
            return requestId + " customer=" + customerId
                    + " contact=" + contactCity + "/" + contactCountryCode
                    + " ship=" + shippingCity + "/" + shippingCountryCode;
        }
        return "missing route";
    }

    static String shippingLabel(Object candidate) {
        if (candidate instanceof ShippingUpdated(
                var orderId,
                Address(var shippingCity, var shippingCountryCode))) {
            return orderId + " -> " + shippingCity + " (" + shippingCountryCode + ")";
        }
        return "not-shippable";
    }

    public static void main(String[] args) {
        Customer customer = new Customer("C-11", new Address("Ha Noi", "VN"));

        System.out.println(describe(new OrderPlaced(
                "O-501", customer, new Money(125000, "USD"))));
        System.out.println(describe(new ShippingUpdated(
                "O-501", new Address("Da Nang", "VN"))));
        System.out.println(describe(new ShippingUpdated("O-502", null)));
        System.out.println(describe(new OrderPlaced(
                "O-503", null, new Money(20, "USD"))));
        System.out.println(describe(new OrderPlaced(
                "O-504", new Customer("C-12", null), new Money(-100, "USD"))));
        System.out.println(describe(new OrderCancelled("O-501", "user-request")));

        System.out.println(addresses(new DeliveryRequest(
                "D-1", customer, new Address("Da Nang", "VN"))));
        System.out.println(addresses(new DeliveryRequest(
                "D-2", new Customer("C-12", null), new Address("Hue", "VN"))));

        System.out.println(shippingLabel(new ShippingUpdated(
                "O-511", new Address("Hue", "VN"))));
        System.out.println(shippingLabel(new ShippingUpdated("O-512", null)));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 DomainPatternNamesDemo.java
java DomainPatternNamesDemo
```

**Exact output:**

```text
order=O-501 customer=C-11 totalCents=125000 USD
shipping:O-501 to Da Nang/VN
shipping:missing:O-502
placed:incomplete:O-503
placed:incomplete:O-504
cancelled:O-501 reason=user-request
D-1 customer=C-11 contact=Ha Noi/VN ship=Da Nang/VN
missing route
O-511 -> Hue (VN)
not-shippable
```

### Semantics and Variable Naming Breakdown

**Order placed event:** `OrderPlaced` contains `orderId`, `customer`, and `total`. The first pattern deeply destructures the needed components: `customerId`, `contactAddress`, `amountInCents`, and `currencyCode`. `contactAddress` is still bound as an `Address` without destructuring city/country because `describe` does not use them; this is an intentional choice to avoid creating unused variables.

**Money and units:** `amountInCents` is the integer declared in `Money`—for example, `125000` is 125000 cents of `USD`, not 125000 dollars. The unit-indicating name prevents readers from making mistakes during calculation or display. The example does not automatically convert cents to dollars; it simply prints the stored value.

**Branch ordering:** the `OrderPlaced` pattern with the guard `amountInCents >= 0` comes before the broader `OrderPlaced(var orderId, var customer, var total)` pattern. Cases where `customer == null`, `total == null`, or the amount is negative do not match the guarded deep branch and fall into the fallback branch. The names `customer` and `total` in the fallback branch show readers which records were not deeply destructured, even though the example only returns a short message.

**Shipping:** `shippingCity` and `shippingCountryCode` clearly identify the shipping address. If `shippingAddress == null`, the `Address(...)` record pattern does not match; the subsequent `ShippingUpdated(var orderId, var shippingAddress)` branch handles the remaining case. `shippingAddress` can be `null` in that branch, yet the pattern variable is still bound.

**Order cancellation:** `cancellationReason` expresses the reason for the cancellation action, avoiding confusion with a `reason` from another event type if the model expands later.

**Two addresses:** the `addresses` method uses `contactCity`/`contactCountryCode` and `shippingCity`/`shippingCountryCode` because there are two `Address` values of the same type. When the customer's contact address is `null`, the nested pattern fails and returns `"missing route"`.

**Types and syntax:** the `var amountInCents` pattern in `Money(long amountInCents, ...)` is inferred by Java as `long`. The variable name does not affect type inference; it only communicates the meaning of that `long` to the reader.

## 7. Naming in `switch`: Clear Roles, No Need to Be Unique Across the Whole Method

A pattern variable in a `case` is scoped to that switch branch. Therefore, you can reuse the name `orderId` across multiple cases when they **carry the same business meaning**:

```java
return switch (event) {
    case OrderPlaced(var orderId, var customer, var total) ->
            "placed:" + orderId;
    case ShippingUpdated(var orderId, var shippingAddress) ->
            "shipping:" + orderId;
    case OrderCancelled(var orderId, var cancellationReason) ->
            "cancelled:" + orderId;
};
```

This is an **illustrative snippet** using `OrderEvent event` and the records from the program in section 6. Each `orderId` is a pattern variable local to its branch, yet all share the same meaning of an order identifier. There is no need to use `placedOrderId`, `shippedOrderId`, `cancelledOrderId` just to make them unique if they refer to the same concept.

Conversely, if both `customerId` and `orderId` appear in **the same branch**, you must not name both `id`. If values in two branches have different meanings, reusing the name `id` may be syntactically valid but can mislead readers.

When using `when`, name variables clearly enough so the condition reads naturally without reverse-translating:

```java
case OrderPlaced(
        var orderId, var customer, Money(var amountInCents, var currencyCode))
        when amountInCents >= 0 -> "non-negative amount";
```

This is an illustrative `case` label, not a standalone statement. The `amountInCents` variable is in scope within `when`, so it can be used directly. A condition like `n >= 0` makes the monetary meaning much less clear.

**Note:** the name `amountInCents` does not make Java automatically validate that the data is in cents or that the currency code is valid; that remains the responsibility of `Money` design and business validation.

## 8. Flow Scoping: Good Naming Still Must Follow Scoping Rules

With `instanceof`, a pattern variable is only available where control flow proves the check has matched.

```java
if (candidate instanceof ShippingUpdated shippingEvent) {
    System.out.println(shippingEvent.orderId());
}
// shippingEvent is not automatically in scope after the if.
```

Combining additional checks with `&&`:

```java
if (candidate instanceof ShippingUpdated(
        var orderId, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(orderId + " -> " + shippingAddress.city());
}
```

The right-hand side of `&&` is only evaluated when the record pattern has matched, so `shippingAddress` can be used. The `null` check is necessary: a `var shippingAddress` component pattern can bind a `null` value even when the outer `ShippingUpdated` is valid.

Do not use a pattern variable where it might not be bound:

```java
// INTENTIONALLY WRONG: the right-hand side of || does not guarantee shippingEvent exists.
if (candidate instanceof ShippingUpdated shippingEvent
        || shippingEvent.shippingAddress() != null) {
    System.out.println("check");
}
```

The compiler will reject this because `shippingEvent` is not definitely assigned on the right-hand side of `||`. This is a scoping and flow-control rule, **not** a consequence of the variable name. For "is of the right type *and* has an address" logic, write `&&` instead of `||`.

In `switch`, a pattern variable's scope includes the `when` guard and the corresponding case expression/block. Do not use the variable name in another `case` or outside the `switch` unless it is validly redeclared.

## 9. Domain Names Must Be Consistent with Record Components and APIs

A pattern variable name may differ from a record component name to express the **usage context** clearly, but it must not create a false meaning.

Example of a record using generic names:

```java
record Contact(String name, String phone) {}
record Parcel(String id, Contact contact) {}

if (candidate instanceof Parcel(
        var parcelId, Contact(var recipientName, var recipientPhone))) {
    System.out.println(parcelId + " -> " + recipientName);
}
```

Here, `id` is named `parcelId`; `Contact.name` is named `recipientName` because in this context the contact is the recipient. If the contact actually represents the sender, then `recipientName` is **domain-incorrect** even though the syntax is valid.

When the domain has near-synonymous terms, choose the canonical term:
- `buyer` vs. `recipient`: the buyer may differ from the recipient.
- `billingAddress` vs. `shippingAddress`: billing may differ from shipping.
- `createdAt` vs. `paidAt`: both are timestamps, but they represent two different events.
- `totalAmount` vs. `paidAmount`: order total differs from the amount paid.
- `customerId` vs. `userId`: only merge if the model genuinely unifies both concepts.
- `amountInCents` vs. `amountInDollars`: same numeric type but different units; must be explicit before conversion.

If the domain has value objects (such as `Money`, `Address`, `OrderId`), consider keeping the object itself within the appropriate scope. Domain types communicate constraints better than a group of same-typed variables that differ only by name.

## 10. Common Mistakes When Naming Pattern Variables

### 10.1. Overly Generic Names That Lose Origin

`if (candidate instanceof ShippingUpdated(var id, var a))` is very short, but it hides the fact that `id` belongs to the order and `a` is the shipping address. Rename them to `orderId` and `shippingAddress` when the branch body handles them in those roles.

### 10.2. Naming After Type Instead of Meaning

`Address address` is not wrong, but when multiple addresses exist, `contactAddress` or `shippingAddress` is better. Conversely, `String stringValue` tells you nothing about whether the string is an order ID, country, or customer name.

### 10.3. "Nice Names" Placed at the Wrong Component Position

`record Transfer(String senderAccountId, String receiverAccountId)` is destructured by position. `Transfer(var receiverAccountId, var senderAccountId)` can still compile because both are strings, but the values have been misnamed. Read the component declaration and write tests for branches with multiple fields of the same type.

### 10.4. Using Different Domain Terms for the Same Concept

Using `orderId` in one file and `purchaseKey` or `saleRef` in another for the same identifier with no real distinction wastes time guessing. Prefer the terminology defined in the domain model, APIs, and business documentation.

### 10.5. Naming Based on Unverified Assumptions

`approvedPayment` is inappropriate if the pattern only proves the object is a `Payment` without checking its approval status. Only use `approvedPayment` when there is a clear guarantee via the data type or a checked condition. Pattern matching **does not automatically enforce** all business rules.

### 10.6. Adding Overly Long Names at Every Nested Node

`customerContactAddressCityNameString` is redundant and hard to scan in a long `case`. Choose `contactCity` if the scope contains only one contact and one shipping address; choose `customerContactCity` if there are multiple distinct contacts.

### 10.7. Forgetting Units, Time Zones, and Code Types

`amount` could be cents or dollars; `timestamp` could be UTC or local; `code` could be currency, status, or country. When the risk of confusion is high, add `amountInCents`, `createdAtUtc`, `currencyCode`, or `countryCode` according to the actual contract.

### 10.8. Causing Name Collisions or Ignoring Flow Scoping

A pattern variable name cannot collide with another variable in a scope where Java forbids duplicate declarations. Pattern variables are also not automatically available in every branch. Fix the naming and control-flow structure validly; do not add redundant casts to work around the compiler.

### 10.9. Treating Good Names as a Substitute for Validation

`shippingCity` can still be `null` or an empty string; `amountInCents` can still be negative; `currencyCode` can still be invalid. Accurate names help code readability; they **do not constrain runtime values**.

### 10.10. Turning Renaming into a Behavior-Changing Refactor

Simply renaming `id` to `orderId` does not change data when all references are updated properly. However, simultaneously reordering record patterns, changing guards, converting `if` to `switch`, or changing accessor calls can alter behavior. Separate renaming from logic-structure changes if the goal is a readability improvement that is easy to review.

## 11. Checklist When Reviewing Code Using Record/Type Patterns

| Question when reading a diff | Good sign | Sign needing a fix |
| --- | --- | --- |
| What does the variable represent? | `orderId`, `customerId`, `shippingAddress` | `id1`, `id2`, `x` |
| Are there two values of the same type? | `contactCity` and `shippingCity` | `city1` and `city2` |
| Does the domain have units of measurement? | `amountInCents`, `durationMillis` | `amount`, `time` in sensitive calculations |
| Does the variable represent an object or an event? | `shippingEvent` for `ShippingUpdated` | `order` when it is actually an event |
| Do names match record component positions? | Order matches record declaration | Good names but swapped positions |
| Are intermediate records kept when needed? | `customer`, `shippingAddress` | Deeply destructuring everything into loose strings |
| Are there unused variables? | Only bind data that needs processing | Creating many useless `var`s and ignoring them |
| Is the guard easy to understand? | `amountInCents >= 0` | `n >= 0` when `n` is unclear |
| Does it depend on `null` or scope limits? | Proper checks before use | Calling accessors on a possibly `null` variable |
| Is the right business terminology used? | Consistent with the model and API | Named based on the editor's guesswork |

Code reviews can focus on **data flow**: "which component does this value come from, what role does it represent, and where is it used?". For multi-level patterns, answering these questions quickly is a good indicator of solid variable naming.

## 12. Before/After Renaming Practice

### Before: Valid Code, Hard to Guess

```java
if (candidate instanceof DeliveryRequest(
        var a, Customer(var b, Address(var c, var d)),
        Address(var e, var f))) {
    System.out.println(a + ":" + c + ":" + e);
}
```

### After: Same Structure, Meaning Immediately Visible

```java
if (candidate instanceof DeliveryRequest(
        var requestId,
        Customer(var customerId,
                Address(var contactCity, var contactCountryCode)),
        Address(var shippingCity, var shippingCountryCode))) {
    System.out.println(requestId + ":" + contactCity + ":" + shippingCity);
}
```

These snippets are illustrative examples in a context where the records and `candidate` are already declared. When the same records are used and variables are replaced consistently in their exact positions, matching does not change; the body still prints the same three components in order. The difference is that the reader knows where the two cities come from.

If the code body only needs the shipping city, an even shorter and clearer way to write it may be **less destructuring**:

```java
if (candidate instanceof DeliveryRequest(
        var requestId, var customer, var shippingAddress)
        && shippingAddress != null) {
    System.out.println(requestId + ":" + shippingAddress.city());
}
```

Do not force the pattern to match `contactAddress` when business logic does not need it; an overly deep pattern may fail to match because `contactAddress == null` even though the shipping address is still valid.

## 13. Exercises and Answers

**Exercise 1 — Two IDs.** Given `record Order(String orderId, String customerId)`, why is `Order(var id1, var id2)` unclear? Rewrite the variable names.

**Answer:** `Order(var orderId, var customerId)`. The `String` type does not distinguish the two identifiers, whereas the variable names help verify the exact role of each component.

**Exercise 2 — Two Addresses.** Given `Customer(contactAddress)` and `Order(shippingAddress)` both using `Address`, should you choose `city1/city2` or `contactCity/shippingCity`?

**Answer:** `contactCity` and `shippingCity` when both appear in the same code block; labels expressing origin and purpose are better than positional ones.

**Exercise 3 — Money Units.** Why is `Money(var amount, var currency)` sometimes not clear enough if the API stores cents?

**Answer:** `amountInCents` and `currencyCode` help distinguish integer cent units from amounts in major currency units. However, names do not validate values; the `Money` contract and calculations must still be correct.

**Exercise 4 — Record Position.** Given `record Transfer(String senderAccountId, String receiverAccountId)`, does `Transfer(var receiverAccountId, var senderAccountId)` compile? Is it business-correct?

**Answer:** It compiles because both components are `String`, but the names have swapped roles. Variables must be named according to the record's declaration order.

**Exercise 5 — Pattern Needing Only One Level.** A feature only prints the shipping city and does not use the contact address. Should you deeply destructure all of `Customer.contactAddress`?

**Answer:** No. Keep `shippingAddress`, check for `null`, and then call `shippingAddress.city()`. Forcing the pattern to match the contact address could exclude data that is still usable.

**Exercise 6 — `when` and Variable Names.** What benefit does the name `amountInCents` provide in `when amountInCents >= 0`? Does it guarantee the amount is non-negative?

**Answer:** It makes it immediately clear that the condition checks the number of cents; the non-negative constraint is enforced by the comparison in the guard, not by the variable name.

**Exercise 7 — Scope.** Can `shippingEvent` be used on the right-hand side of `if (candidate instanceof ShippingUpdated shippingEvent || shippingEvent.shippingAddress() != null)`?

**Answer:** No; when the left-hand side is `false`, the variable is not bound. If you want "is of the right type and has an address", use `&&`.

**Exercise 8 — Choosing a Domain Name.** In `OrderCancelled(var orderId, var x)`, the second component is a string cancellation reason. Which name should you choose?

**Answer:** `cancellationReason` (or `cancelReason` if the project uses that term consistently), not `x` or a vague `message`.

## 14. Key Takeaways

- **Pattern variable names should express business meaning**, not just the Java type or position in the component list.
- For multiple components of the same type, add **role/origin**: `customerId` vs. `orderId`, `contactCity` vs. `shippingCity`.
- For numbers and codes, add **unit or code type** when it matters: `amountInCents`, `currencyCode`, `countryCode`.
- **Record patterns match by component order**, not by variable name; misnamed variables still compile if types match.
- Keep intermediate records or objects when context needs to be preserved; do not destructure deeply just because syntax allows it.
- Handle `null` checks, guards, and flow scoping according to Java rules: good names do **not** replace data validation or compiler guarantees.
- Prefer naming consistent with the project's domain model and APIs; concise enough, yet clear enough to avoid role confusion.

**Official references:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
