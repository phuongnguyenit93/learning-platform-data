# Keeping Pattern Conditions Linear

## 1. What Does “Linear” Mean in Pattern Conditions?

In Java processing, a branch often needs to answer three questions in order: **does the value have the right structure, does the inner data satisfy the condition, and if so, what needs to be done?** With pattern matching, we can express those steps in an easy-to-follow, single-direction flow:

1. **Match the pattern** to confirm the type/structure and bind variables.
2. **Check additional conditions** using the variables that were just bound.
3. **Process the result** or move on to the next branch.

“Linear” here refers to organizing **a clear reading flow and control flow**, not a promise that the algorithm has `O(n)` time complexity. A condition can be very short yet still hard to understand if it mixes multiple negations, `||` branches, and accesses to unverified data.

For example, with the following records:

```java
record Address(String city) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer, int amount) {}
```

We want to identify an order that has a complete customer and address, an amount of 100 or more, and a city of Hà Nội.

A multi-level `if` approach, assuming the `input` variable is already declared:

```java
if (input instanceof Order order) {
    if (order.customer() != null) {
        Customer customer = order.customer();
        if (customer.address() != null) {
            Address address = customer.address();
            if (order.amount() >= 100) {
                if ("Hà Nội".equals(address.city())) {
                    System.out.println("Đơn ưu tiên: " + order.id());
                }
            }
        }
    }
}
```

This snippet works with the sample data, but the reader has to follow multiple levels of braces and intermediate variables. If the problem only requires taking action when **all** conditions are true, the chain of checks can be arranged in a more natural order.

## 2. Combining Record Patterns and the && Operator

In Java 21, record patterns can be nested and combined with `&&`:

```java
if (input instanceof Order(
        String id,
        Customer(String name, Address(String city)),
        int amount)
        && amount >= 100
        && "Hà Nội".equals(city)) {
    System.out.println("Đơn ưu tiên: " + id);
}
```

Read in exact order:

- `input instanceof Order(...)` checks that the value is an `Order`, deconstructs `customer` into `Customer`, and then further deconstructs `address` into `Address`. If the nested patterns do not match, the `instanceof` condition is `false`.
- Only after the pattern matches can the variables `id`, `name`, `city`, and `amount` be used in the `&&` parts that follow.
- `amount >= 100` is a business check on the `int` variable just extracted from the record.
- `"Hà Nội".equals(city)` checks the location. Placing the string literal on the left is also safe if `city` could be `null`; with the `String city` pattern here, a `null` value already causes the corresponding pattern not to match.
- When all three parts are true, the `if` body runs.

**The `&&` operator uses short-circuit evaluation:** if the left-hand side is false, Java does not evaluate the right-hand side. Therefore, the program never accesses unbound pattern variables when the structure does not match. The relationship “match the pattern first, check the data after” is both easy to read and aligned with Java's variable scoping rules (*flow scoping*).

For readability, put a line break after each major condition. There is no need to cram the entire nested record pattern, business guards, and action onto a single line.

## 3. When Conditions Have Multiple Steps: Use Guard Clauses to Reduce Nesting

A long condition with many `&&` operators can still be hard to maintain. When there are multiple different rejection reasons, let the program **return early** (*guard clause*) and continue processing at the same indentation level:

```java
static String classify(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city)),
            int amount))) {
        return "Không đủ cấu trúc đơn hàng";
    }

    if (amount < 100) {
        return "Đơn nhỏ: " + id;
    }

    if (!"Hà Nội".equals(city)) {
        return "Ngoài Hà Nội: " + id;
    }

    return "Đơn ưu tiên: " + id + " - " + name;
}
```

The steps still proceed in one direction:

1. First, filter out values that do not match the required structure.
2. Next, filter out orders below the amount threshold.
3. Then, filter out orders outside the service area.
4. Finally, handle the case that meets all requirements.

This is an illustrative example inside a class where the records are already declared. The key point about **flow scoping**: the condition `!(input instanceof Order(...))` means “does not match the pattern.” If execution enters the `if` branch, the method immediately `return`s. Therefore, on the execution path continuing after the `if`, the compiler knows the pattern matched and allows using `id`, `name`, `city`, and `amount`.

Negating `instanceof` does not automatically make pattern variables usable afterward in every case. The deciding condition is that **every path reaching the variable usage has proven that the pattern matched**. If the negated branch does not terminate the control flow, the variables are not guaranteed to be bound and Java will reject the out-of-scope usage.

## 4. Distinguishing && from || in Flow Scoping

Compare the two forms:

```java
// Valid: the part after && is only evaluated when the pattern has matched.
if (input instanceof Order(var id, var customer, var amount)
        && amount >= 100) {
    System.out.println(id);
}
```

```java
// DOES NOT COMPILE: if the pattern on the left does not match,
// the right branch of || is still evaluated, but amount is not bound yet.
// if (input instanceof Order(var id, var customer, var amount)
//         || amount >= 100) {
//     System.out.println(id);
// }
```

The second snippet is completely commented out because it is an **intentional error example**, not runnable code. With `||`, the right-hand branch is evaluated when the left-hand side is **false**; therefore, you cannot use a variable there that is only declared when the left-hand pattern is **true**.

The `||` form is sometimes valid when the two conditions are independent, for example:

```java
if (input == null || input instanceof String) {
    System.out.println("Trống hoặc là chuỗi");
}
```

However, when conditions depend on data bound by a pattern, prefer a `&&` chain or split them into guard clauses to express the dependency clearly. Do not replace `&&` with `&`: the boolean `&` operator evaluates both sides, lacks short-circuiting, and does not allow the same pattern-variable usage that depends on the first condition.

## 5. Combining Patterns with switch and when

When **multiple outcomes** are needed for the same structure, `switch` can make the classification flow clearer. Since Java 21, you can place a record pattern in a `case` and add `when` for business conditions:

```java
static String classifySwitch(Object input) {
    return switch (input) {
        case Order(String id, Customer(String name, Address(String city)),
                   int amount)
                when amount >= 100 && "Hà Nội".equals(city) ->
                "Ưu tiên theo switch: " + id;

        case Order order ->
                "Đơn khác: " + order.id();

        case null ->
                "Không có dữ liệu";

        default ->
                "Không phải đơn hàng";
    };
}
```

Each `case` is read as **pattern → guard (if any) → action**. `when` is only evaluated when the preceding record pattern has matched, so variables bound by the pattern are allowed to appear in the guard. In the example above, `amount` and `city` belong to the exact `Order` being inspected.

**Branch order matters:** place `case Order order` after the detailed branch. If you place the catch-all `Order` branch first, the more specific branch behind it can never be selected and the compiler may report a *dominated case* error. Similarly, if there are multiple `Order(...) when ...` branches, place specific rules before general ones and avoid unintended overlapping conditions.

The `case null` branch handles a `null` selector. `default` handles data that is not an `Order`; you should not assume `default` is a substitute for handling `null`.

## 6. Complete Java 21 Example and Exact Output

Create the file **`LinearPatternConditionsDemo.java`**:

```java
public class LinearPatternConditionsDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer, int amount) {}

    static boolean isPriority(Object input) {
        return input instanceof Order(
                String id,
                Customer(String name, Address(String city)),
                int amount)
                && amount >= 100
                && "Hà Nội".equals(city);
    }

    static String classify(Object input) {
        if (!(input instanceof Order(
                String id,
                Customer(String name, Address(String city)),
                int amount))) {
            return "Không đủ cấu trúc đơn hàng";
        }

        if (amount < 100) {
            return "Đơn nhỏ: " + id;
        }

        if (!"Hà Nội".equals(city)) {
            return "Ngoài Hà Nội: " + id;
        }

        return "Đơn ưu tiên: " + id + " - " + name;
    }

    static String classifySwitch(Object input) {
        return switch (input) {
            case Order(String id,
                    Customer(String name, Address(String city)),
                    int amount)
                    when amount >= 100 && "Hà Nội".equals(city) ->
                    "Ưu tiên theo switch: " + id;
            case Order order ->
                    "Đơn khác: " + order.id();
            case null ->
                    "Không có dữ liệu";
            default ->
                    "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Object priority = new Order(
                "O-1", new Customer("Lan", new Address("Hà Nội")), 150);
        Object small = new Order(
                "O-2", new Customer("Minh", new Address("Hà Nội")), 50);
        Object elsewhere = new Order(
                "O-3", new Customer("An", new Address("Đà Nẵng")), 200);
        Object missingAddress = new Order(
                "O-4", new Customer("Bình", null), 500);

        System.out.println(classify(priority));
        System.out.println(isPriority(priority));
        System.out.println(classify(small));
        System.out.println(classify(elsewhere));
        System.out.println(classify(missingAddress));
        System.out.println(classifySwitch(priority));
        System.out.println(classifySwitch(missingAddress));
        System.out.println(classifySwitch(null));
        System.out.println(classifySwitch("khác"));
    }
}
```

Compile and run with **JDK 21 or later**, without enabling preview features:

```bash
javac LinearPatternConditionsDemo.java
java LinearPatternConditionsDemo
```

Output:

```text
Đơn ưu tiên: O-1 - Lan
true
Đơn nhỏ: O-2
Ngoài Hà Nội: O-3
Không đủ cấu trúc đơn hàng
Ưu tiên theo switch: O-1
Đơn khác: O-4
Không có dữ liệu
Không phải đơn hàng
```

Why does it produce this output?

- `priority` has all three records present, `amount = 150`, and `city = "Hà Nội"`: the pattern matches and the guards hold, so `classify` returns the priority order and `isPriority` is `true`.
- `small` matches the structure, but `amount = 50`, so it hits the guard clause returning “Đơn nhỏ”.
- `elsewhere` matches the structure and amount, but `city` is “Đà Nẵng”, so it returns “Ngoài Hà Nội”.
- `missingAddress` has a `customer` but `address == null`. The nested pattern `Address(String city)` does not match, so `classify` returns “Không đủ cấu trúc đơn hàng”.
- In `switch`, `missingAddress` does not match the nested record pattern branch with `when`, yet it is still an `Order`, so the `case Order order` branch returns “Đơn khác: O-4”.
- `null` selects `case null`; the string `"khác"` selects `default`.

The program demonstrates all three ways of expressing the same idea: **a boolean expression with `&&`**, **a sequence of guard clauses**, and **a switch with patterns and `when`**. They serve different purposes: a single true/false condition, a workflow with multiple early-exit reasons, and multiple classification branches.

## 7. Handling null Without Breaking Linearity

With nested record patterns, each inner record must match. If `customer == null` or `address == null`, the pattern `Order(String id, Customer(...), int amount)` does not match, and Java does not evaluate the `&&` checks that follow.

However, **record patterns do not automatically prove every reference is non-null in every way they can be written**. For instance, if you use `var city` to bind a component of type `String`, you still need to consider the possibility that `city` is `null` before calling a method on it. Writing `"Hà Nội".equals(city)` is safer than `city.equals("Hà Nội")` when data may be missing.

Do not automatically infer from `Order` matching an outer pattern that both `customer` and `address` exist. A shallower pattern, such as `Order(var id, var customer, var amount)`, can still bind `customer` when its value is `null`. Choose the deconstruction depth that matches the conditions you actually need to check.

## 8. Rules for Keeping Conditions Readable

| Rule | Reason | Example |
| --- | --- | --- |
| Match type and structure first | Avoid using a value before confirming the right data type. | `input instanceof Order(...)` |
| Place dependent conditions after `&&` | Ensure they are only evaluated when pattern variables are bound. | `&& amount >= 100` |
| Use meaningful variable names | Reduce confusion with deeply nested records. | `city`, `amount`, `id` |
| Split branches when there are multiple rejection reasons | Avoid deep `if` nesting and vague error messages. | `if (amount < 100) return ...;` |
| In `switch`, check specific patterns first | Avoid being shadowed by a general branch. | `case Order(...) when ...` then `case Order order` |
| Handle potentially null data | Distinguish a null selector from a null component. | `case null`; check nested patterns |
| Avoid unnecessary side effects in guards | Conditional expressions short-circuit, so side effects may be skipped. | Separate logging/state updates from `&&` |

No single pattern fits every situation. A simple classification should use `&&`; when each rejected case needs its own explanation, guard clauses are clearer; when there are multiple record types or multiple handling branches, `switch` with `case` and `when` helps group logic by data structure.

## 9. Common Mistakes

1. **Using a pattern variable before the pattern matches.** For example, using `amount` on the right side of `||` when `amount` is only declared in the pattern on the left will not be accepted by Java's flow scoping.
2. **Replacing `&&` with `&`.** Boolean `&` does not short-circuit, causing the second part to be evaluated even when the first part is false; this is both error-prone and fails to express the dependency between pattern and guard.
3. **Cramming a long condition with many negations.** `if (!... || (... && !...))` is harder to verify than the sequence “match pattern → business condition → action”. Use guard clauses and give business concepts clear names.
4. **Putting a general `case` before a specific `case`.** A broad branch can cause the specific branch to be *dominated*, resulting in a compile error. Order specialized branches first.
5. **Assuming `default` handles a null selector.** With pattern matching for switch, `null` handling is a separate case; use `case null` when an explicit result is needed.
6. **Confusing “linear” with algorithmic complexity.** Organizing conditions step by step does not guarantee faster execution. The goal is to accurately express dependencies and reduce complexity when reading code.
7. **Using the wrong Java version.** Record patterns and pattern matching for `switch` became standard features in Java 21. The examples with `when` and record deconstruction in this lesson require JDK 21 or later.

## 10. Self-Check

Suppose the data is:

```java
record Score(String subject, int value) {}
Object candidate = new Score("Java", 85);
```

Write a condition that prints the subject when the value is a `Score` with `value >= 80` and the subject is `"Java"`:

```java
if (candidate instanceof Score(String subject, int value)
        && value >= 80
        && "Java".equals(subject)) {
    System.out.println(subject + ": đạt");
}
```

The output is:

```text
Java: đạt
```

Then try replacing `candidate` with `"Java"` or `null`: the `instanceof Score(...)` part does not match, so Java does not evaluate the remaining conditions; the `if` body does not run. Try changing `value` to `70`: the record pattern still matches, but the first guard is false, so the branch does not run.

**Remember:** Organize pattern conditions in the order **match structure → check bound data → perform action**. Use `&&` for short-circuiting dependent chains, guard clauses for multiple exclusionary conditions, and `switch case ... when ...` for multiple classification branches. This keeps conditions compliant with Java 21 variable scoping rules while remaining readable and maintainable.
