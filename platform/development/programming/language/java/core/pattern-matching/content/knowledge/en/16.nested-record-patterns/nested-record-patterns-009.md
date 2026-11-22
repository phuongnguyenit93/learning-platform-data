# Limiting Depth to Preserve Readability

**Topic:** Nested record patterns in Java Core Pattern Matching. **Version:** Java 21 and later (record patterns were standardized in Java 21, JEP 440; no preview flag required).

A record pattern checks whether a value has the exact record type and immediately extracts that record's components. When a record contains another record, you can nest patterns inside one another. This syntax is very concise when the shape of the data is an important condition, but if nested too deeply, readers must trace through many parentheses and variable names before seeing the processing intent.

**Core principle:** Nest only to the extent that the structure still helps explain the condition. When deep levels begin to obscure the business logic, stop deconstructing, keep an intermediate record variable, and continue processing on a clearly named line or method.

## 1. What does the depth of a nested record pattern mean?

Suppose we have three records:

~~~java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer, int totalCents) {}
~~~

A full pattern traversing all three records:

~~~java
if (value instanceof Order(
        var id,
        Customer(
                var name,
                Address(var city, var street)),
        var totalCents)) {
    // id, name, city, street, and totalCents are now available.
}
~~~

Counting record layers from the outside in, **Order is level 1**, **Customer is level 2**, and **Address is level 3**. The pattern specifies that the entire path Order → Customer → Address must match. Only then do the variables in the true branch take effect.

Java does not enforce a "maximum of two levels" threshold to guarantee readability. The depth limit in this article is a **design convention**, not a syntax rule or a compiler constraint. A short three-level pattern can be good, whereas a two-level pattern with many branches and tangled conditions can still be hard to understand.

The number of levels is merely a signal to review the code. Evaluate **expression length**, **number of extracted variables**, **accompanying conditions**, **null handling**, and **business goal** together.

## 2. Why do deeply nested patterns reduce readability?

With the pattern Order(Customer(Address(...))), readers typically have to perform these steps: identify the input object type; determine which component of Order holds Customer; find Address inside Customer; check the variable names to be used; and only then read the condition or action that follows.

Deep nesting easily causes several problems:

- **Loss of focus:** important logic, such as checking whether an order is eligible, gets pushed behind a long data-extraction structure.
- **Hard to identify non-matching cases:** if even a single nested child record required by the pattern is null, the entire pattern fails to match; a generic fallback branch can hide the specific reason.
- **Many live variable names in the same scope:** it is easy to confuse customerName with receiverName, sourceCity with destinationCity, or amounts from different levels.
- **Structural changes cause widespread edits:** when changing how components are organized, many branches with deeply nested patterns must be updated at once.
- **Hard to review conditions:** expressions combining multi-level patterns with comparisons, logical operators, or long **when** clauses become very difficult to read.

A short expression is not automatically easy to understand. When components are well-named and indented by level, a two- or three-level pattern can still be clearer than chaining multiple accessor calls. Choose based on the responsibility of the code block.

## 3. Before-and-after example: two ways to process the same data

Requirement: if the input is an Order with a structurally valid Customer and Address, output a summary containing the order ID, customer name, city, street, and amount. If any record along that nested path is missing, return **Missing nested data**.

### Approach A — deconstruct three levels in a single pattern

~~~java
static String deep(Object value) {
    if (value instanceof Order(
            var id,
            Customer(var name, Address(var city, var street)),
            var totalCents)) {
        return render(id, name, city, street, totalCents);
    }
    return "Missing nested data";
}
~~~

Pros: very concise; a single condition expresses the required shape. Suitable when all components need to be read immediately and the action branch is simple.

Cons: if more nested records or more business rules are added, the expression's complexity grows rapidly. You cannot immediately tell whether the non-matching branch was caused by a missing Customer or a missing Address without adding another branch.

### Approach B — stop at each record boundary and process step by step

~~~java
static String stepwise(Object value) {
    if (!(value instanceof Order(var id, var customer, var totalCents))) {
        return "Missing nested data";
    }
    if (!(customer instanceof Customer(var name, var address))) {
        return "Missing nested data";
    }
    if (!(address instanceof Address(var city, var street))) {
        return "Missing nested data";
    }
    return render(id, name, city, street, totalCents);
}
~~~

Here, at each reading step you only have to understand **one record pattern**. The names customer and address expose the business boundaries: order, customer, address. If you need to add checks on customer or address at each layer, you can place them right where the data becomes available.

Thanks to Java's **flow scoping**, variables bound by a pattern in a negated condition can still be used in subsequent statements if the non-matching branch performs a **return**. In the example, id, customer, and totalCents are in scope after the first if; name and address are in scope after the second if.

Note: a **var** variable in a record pattern can hold a null value for a reference component; therefore, Approach B must check the child record with instanceof in the next step. In Approach A, a nested Customer(...) or Address(...) pattern will not match if that child record itself is null.

Both approaches can produce **the same business result** if the conditions and fallback branches are preserved. Splitting a pattern does not automatically change the data acceptance requirements.

## 4. Complete, runnable Java 21 program

Save the following code as **PatternDepthDemo.java**. The program uses both analyzed approaches and prints the same output for the corresponding cases.

~~~java
public class PatternDepthDemo {
    record Address(String city, String street) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, int totalCents) {}

    private static String render(String id, String name, String city,
                                 String street, int totalCents) {
        return "%s | %s | %s/%s | %d".formatted(
                id, name, city, street, totalCents);
    }

    static String deep(Object value) {
        if (value instanceof Order(
                var id,
                Customer(var name, Address(var city, var street)),
                var totalCents)) {
            return render(id, name, city, street, totalCents);
        }
        return "Missing nested data";
    }

    static String stepwise(Object value) {
        if (!(value instanceof Order(var id, var customer, var totalCents))) {
            return "Missing nested data";
        }
        if (!(customer instanceof Customer(var name, var address))) {
            return "Missing nested data";
        }
        if (!(address instanceof Address(var city, var street))) {
            return "Missing nested data";
        }
        return render(id, name, city, street, totalCents);
    }

    public static void main(String[] args) {
        Object good = new Order(
                "ORD-17", new Customer(
                        "An", new Address("Da Nang", "Bach Dang")), 99000);
        Object missing = new Order(
                "ORD-18", new Customer("Binh", null), 50000);

        System.out.println(deep(good));
        System.out.println(stepwise(good));
        System.out.println(deep(missing));
        System.out.println(stepwise(missing));
        System.out.println(stepwise(null));
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac PatternDepthDemo.java
java PatternDepthDemo
~~~

Exact output:

~~~text
ORD-17 | An | Da Nang/Bach Dang | 99000
ORD-17 | An | Da Nang/Bach Dang | 99000
Missing nested data
Missing nested data
Missing nested data
~~~

**Explanation:** good has complete Order, Customer, and Address instances, so both approaches return the same string. For missing, the address component is null: Approach A fails when attempting to match Address(...), while Approach B passes Order and Customer but fails at the address instanceof Address(...) check. A null selector in instanceof returns false, so stepwise(null) also reaches the fallback branch. The example uses a generic message for easy comparison; a real program can separate the causes for a missing customer and a missing address.

String types using **var** at the leaves can hold null; the formatted method may print the literal text **null** in that case. Matching a record pattern **does not mean** every data field inside satisfies business constraints. If name, city, or street must be non-empty, check explicitly in the appropriate place.

## 5. Where to draw the nesting boundary?

A practical guideline: **prefer one or two levels when the meaning remains clear**; when reaching three levels or deeper, proactively consider splitting into steps. This is a reminder to check readability, not a mandatory rule. Use the table below to decide.

| Signal in the problem | Usually clearer style | Reason |
| --- | --- | --- |
| Need to extract a few components directly from one record | A single record pattern | Clearly shows the type and values needed |
| Two nested records, simple processing branch | Two-level nested record pattern | The data shape helps read the condition quickly |
| Three levels, but short pattern, clear variable names, few branches | Can keep the nested pattern | Fewer intermediate steps while still easy to follow |
| Three or more levels accompanied by many business conditions | Split level by level | Separates structural checks from business rules |
| Need to return different errors when Customer or Address is missing | Split into multiple ifs/branches | Easy to pinpoint which data failed |
| The same structure is read in multiple branches/methods | Extract a well-named method | Reduces duplication and centralizes rules |
| Only a single value is needed | Type pattern or accessor | Deconstructing the entire record may be unnecessary |
| Need to use the child object itself in multiple operations | Keep the child record variable | Avoids reassembling information from leaf variables |

Ask yourself: can a reader understand this block in a single glance without counting parentheses or reading component names backward? If not, split it.

## 6. Clarifying business conditions when patterns grow long

Suppose we only process orders with a positive amount and an address in a supported city. There is no need to put every rule into the same deconstruction condition:

~~~java
// Illustrative snippet: uses the previously declared Order, Customer, and Address records.
static boolean supportedCity(String city) {
    return "Da Nang".equals(city) || "Ha Noi".equals(city);
}

static boolean eligible(Object value) {
    if (!(value instanceof Order(var id, var customer, var totalCents))) {
        return false;
    }
    if (!(customer instanceof Customer(var name, var address))) {
        return false;
    }
    if (!(address instanceof Address(var city, var street))) {
        return false;
    }

    return totalCents > 0 && supportedCity(city);
}
~~~

In this version, **the first three steps** check the required record shape; the final return line expresses the business rule. The supportedCity method has a name describing its intent and uses a null-safe comparison when city is null. The variables id, name, and street are currently unused in the function; if extracting those components is truly unnecessary, you can choose to use a type pattern with accessors or use shorter-named variables. Do not force record patterns for every case.

When using **switch** with record patterns and **when** guards, apply the same principle. A short guard like **when totalCents > 0** can aid quick reading; long guards combining multiple operations, method calls, and multi-level record patterns should usually be extracted into a method whose name expresses the rule. Also remember to order specific branches before general ones so they are not dominated by a broader pattern.

## 7. Preserving behavior when refactoring from deep to shallow patterns

Splitting a pattern is a change in code organization; you still need to check edge cases:

1. **Wrong outermost type:** An Object that is not an Order must take the correct rejection branch.
2. **Null child record:** An Order with customer = null or a Customer with address = null must take the corresponding branch. A nested child record pattern does not match null.
3. **Null leaf components:** Depending on whether you use **var** or a typed pattern and accompanying validation rules, preserve the meaning of null; do not assume a record implies non-null for every component.
4. **Guards and branch order:** With switch, specific conditions and case ordering must preserve the original meaning.
5. **Return values and error paths:** Do not turn a previously rejected input into an accepted one simply because a check step was moved.
6. **Variable scope:** Pattern variables can only be used where the compiler proves the pattern matched; variables after a return branch in the example are a valid case.

Do not turn a deeply nested pattern into a chain of accessors while forgetting null checks:

~~~java
// Must ensure customer() and address() are non-null before chaining further calls.
String city = order.customer().address().city();
~~~

The line above can throw a **NullPointerException** if customer or address is null. A deeply nested pattern in instanceof will not match when the corresponding child record is null; the two approaches are equivalent only when null branches are properly handled.

## 8. Code review checklist

Before finalizing a nested record pattern, check:

- **Intent:** does the pattern express the data structure needed for the decision, or is it obscuring the business logic?
- **Depth:** can the parent record → child record path be understood immediately without tracing through many layers?
- **Variable names:** can the names be read independently, such as billingCity, shippingCity, customerName?
- **Conditions:** can the pattern and guard be read in one breath, or should a method be extracted?
- **Nulls:** are null child records and null leaf components handled as required?
- **Duplication:** is the same deconstruction structure copied across multiple places?
- **Equivalence:** after splitting, do success and failure cases retain the exact same results?

If a nested pattern immediately expresses the required data and the action branch is short, keep it. If the depth forces readers to decode the structure before understanding the business logic, **stop the pattern at a clearly named record**, check further step by step, and place the business condition on a separate line or in a separate method. That is a depth limit serving readability in Java, not a rigid syntax threshold.