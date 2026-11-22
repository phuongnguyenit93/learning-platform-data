# Limits of Cramming Too Much Logic into an Expression

## 1. The Problem: A Short Expression Is Not Necessarily Easy to Understand

Pattern matching allows Java to check data types and extract information within a single expression. Since Java 21, you can use `instanceof` with a record pattern, or place a pattern in a `switch` `case`. As a result, code that previously required repeated casts and accessor calls can become more concise.

However, **combining more checks into a single expression does not mean the code is better**. When one expression simultaneously checks structure, handles `null`, applies a series of business rules, constructs messages, and performs side effects, it becomes hard for a reader to answer:

- Which condition must be true before another?
- Can a variable bound by a pattern be used at this position?
- Which branch will execute when data is missing or a condition fails?
- Can each rule be tested independently?

In this article, "limits" means **limits on readability, modifiability, testability, and understanding the exact behavior**, rather than Java imposing a fixed number on expression length or how many `&&` operators are allowed.

## 2. Example: An Expression with Too Many Responsibilities

Suppose an order has customer and address information:

```java
record Address(String city) {}
record Customer(String name, Address address, boolean active) {}
record Order(String id, Customer customer, int total) {}
```

Rules for an order to be considered prioritized:

1. `Order` must have a `Customer` and an `Address` with a valid structure.
2. The customer must be active.
3. The order ID and customer name must not be blank.
4. The order total must be `100` or greater.
5. The city must be `Hà Nội` or `Đà Nẵng`.

You could write one long boolean expression:

```java
static boolean eligibleInline(Object input) {
    return input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total)
            && active
            && !id.isBlank()
            && !name.isBlank()
            && total >= 100
            && ("Hà Nội".equals(city) || "Đà Nẵng".equals(city));
}
```

This is **valid Java 21 code**, assuming the three records are declared in the same scope. It has the advantage that conditions are evaluated sequentially; however, to change the location rule, the amount threshold, or the definition of a valid customer, the reader has to reopen the entire expression.

As the list of rules grows, maintenance often becomes harder because three layers of meaning are mixed together:

- **Data structure:** Is `input` an `Order` containing a `Customer` and an `Address`?
- **Business rules:** Is the customer active, are the identifiers valid, does the total meet the threshold, is the city supported?
- **Handling decision:** If eligible, what should be returned; if not, what reason needs to be explained?

Short and stable conditions can still be kept as-is. You should split them up when rules change independently, multiple branches appear, or readers have to repeatedly count parentheses and deduce evaluation order.

## 3. Pattern First, Dependent Conditions After

In the example above, the part:

```java
input instanceof Order(
        String id,
        Customer(String name, Address(String city), boolean active),
        int total)
```

does two things: it checks that the value belongs to the corresponding record type and **deconstructs** the components. The variables `id`, `name`, `city`, `active`, and `total` are only bound when the entire pattern matches.

After that, the checks are chained with `&&`. This operator uses *short-circuit* evaluation: if the left-hand side is `false`, Java does not evaluate the right-hand side. This is why pattern variables can be used in subsequent `&&` operands after the pattern has matched.

Illustrative example:

```java
if (input instanceof Order(
        String id, var customer, int total)
        && total >= 100) {
    System.out.println(id);
}
```

Here, `total` is only checked once the record pattern has matched. If `input` is not an `Order` or is `null`, the `instanceof` condition returns `false` and the `total >= 100` part does not run.

**Do not arbitrarily replace `&&` with `||` or `&`:**

```java
// Does not compile: the right-hand side of || can run when the pattern does not match,
// so the variable total is not guaranteed to be bound.
// if (input instanceof Order(String id, var customer, int total)
//         || total >= 100) {
//     System.out.println(id);
// }
```

This is an intentional error example, commented out to avoid being mistaken for a complete runnable program. With `||`, the right-hand side is evaluated when the left-hand side is false; with `&` on booleans, both sides are evaluated, losing short-circuiting. When the second condition **depends** on a variable from the pattern, express that dependency with `&&` or split the control flow into separate steps.

In addition, the parentheses in:

```java
&& ("Hà Nội".equals(city) || "Đà Nẵng".equals(city))
```

make it clear that the city selection is **a sub-group of conditions**. If you remove the parentheses and alter the `&&`/`||` structure, operator precedence can change the entire business meaning.

## 4. Extract Rules into Named Functions

Keep the record pattern at the structural check, and move business rules into small functions. For example:

```java
static boolean hasIdentity(String id, String name) {
    return id != null && !id.isBlank()
            && name != null && !name.isBlank();
}

static boolean isSupportedCity(String city) {
    return "Hà Nội".equals(city) || "Đà Nẵng".equals(city);
}

static boolean eligibleReadable(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total))) {
        return false;
    }

    return active
            && hasIdentity(id, name)
            && total >= 100
            && isSupportedCity(city);
}
```

This snippet assumes the `Address`, `Customer`, and `Order` types are available. The `hasIdentity` and `isSupportedCity` functions state clearly **which rule** is being applied; the `eligibleReadable` method states clearly **when** the rules are applied.

Negating the pattern in the first guard has the form:

```java
if (!(input instanceof Order(...))) {
    return false;
}
```

The key point is that the non-matching branch **terminates immediately with `return`**. After that branch, every continuing path has matched the pattern, so the variables `id`, `name`, `city`, `active`, and `total` can be used under Java's *flow scoping* rules. If the non-matching branch does not exit the control flow, the compiler does not necessarily allow using those variables below.

This extraction brings three clear benefits: function names convey business meaning, each condition can be unit-tested separately, and a change to supported cities does not require rewriting the entire pattern.

You should also not go to the extreme of extracting every single comparison into its own function. `total >= 100` is still easy to read; only create a function or a `MINIMUM_TOTAL` constant if that threshold carries domain significance, is reused, or needs to be configurable.

## 5. When Reasons Need to Be Reported: Use Guard Clauses

A boolean expression only answers **true or false**. If you need to distinguish *missing address*, *inactive customer*, or *order below threshold*, stuffing messages into nested `?:` ternary expressions makes the code hard to test.

You can use a sequence of guard clauses:

```java
static String explain(Object input) {
    if (!(input instanceof Order(
            String id,
            Customer(String name, Address(String city), boolean active),
            int total))) {
        return "Thiếu cấu trúc đơn hàng";
    }
    if (!active) {
        return "Khách hàng không hoạt động";
    }
    if (!hasIdentity(id, name)) {
        return "Thiếu mã đơn hoặc tên khách";
    }
    if (total < 100) {
        return "Giá trị đơn thấp";
    }
    if (!isSupportedCity(city)) {
        return "Chưa hỗ trợ thành phố";
    }
    return "Đủ điều kiện";
}
```

The conditions are ordered so a reader can follow them: **structural check → customer → identity → amount → location → result**. Each branch returns early, so there is no need for multiple levels of nested `if` statements.

Note that the order of guard clauses **determines the first reported message** when data violates multiple rules. If you want to collect all errors at once, you need a different design, such as a list of validation results; in that case, changing from "return the first error" to "collect multiple errors" is a change in business behavior, not merely a syntactic cleanup.

## 6. When There Are Multiple Cases: Switch Expressions with Concise Guards

Java 21 allows using patterns in `case` labels and adding `when` conditions:

```java
static String describe(Object input) {
    return switch (input) {
        case Order order when eligibleReadable(order) ->
                "Đủ điều kiện: " + order.id();
        case Order order ->
                "Cần kiểm tra: " + order.id();
        case null ->
                "Không có dữ liệu";
        default ->
                "Không phải đơn hàng";
    };
}
```

This style keeps the `switch` structure easy to read: **match type → call named condition → return result**. The guard `when eligibleReadable(order)` is only evaluated after `case Order order` matches, so `order` is ready to be passed into the function.

Place the general `case Order order` **after** the branch with `when`. If placed before it, the more specific branch later on can become dominated (*dominated case*) and cause a compilation error.

With a selector of type `Object`, other types must also be handled; here `default` takes care of that. `case null` separates the case where the selector has no data. Arrow branches `->` do not *fall through* to the next branch.

A `switch expression` can contain a block and `yield`:

```java
String result = switch (input) {
    case Order order when eligibleReadable(order) -> {
        String message = "Đủ điều kiện: " + order.id();
        yield message;
    }
    case Order order -> "Cần kiểm tra: " + order.id();
    case null -> "Không có dữ liệu";
    default -> "Không phải đơn hàng";
};
```

This is **an illustrative snippet assuming the variable `input` and declarations already exist**, avoiding packing every message-building step into a ternary operator. However, if a branch's block grows to dozens of lines, has multiple `try/catch` blocks, updates state, or calls services, move that logic into a named method. The goal is for `switch` to show **the choice**, while a separate method expresses **how it is handled**.

## 7. Complete Runnable Java 21 Program

Create the file **`ReadablePatternExpressionsDemo.java`**:

```java
public class ReadablePatternExpressionsDemo {
    record Address(String city) {}
    record Customer(String name, Address address, boolean active) {}
    record Order(String id, Customer customer, int total) {}

    static boolean eligibleInline(Object input) {
        return input instanceof Order(
                String id,
                Customer(String name, Address(String city), boolean active),
                int total)
                && active
                && !id.isBlank()
                && !name.isBlank()
                && total >= 100
                && ("Hà Nội".equals(city) || "Đà Nẵng".equals(city));
    }

    static boolean hasIdentity(String id, String name) {
        return id != null && !id.isBlank()
                && name != null && !name.isBlank();
    }

    static boolean isSupportedCity(String city) {
        return "Hà Nội".equals(city) || "Đà Nẵng".equals(city);
    }

    static boolean eligibleReadable(Object input) {
        if (!(input instanceof Order(
                String id,
                Customer(String name, Address(String city), boolean active),
                int total))) {
            return false;
        }

        return active
                && hasIdentity(id, name)
                && total >= 100
                && isSupportedCity(city);
    }

    static String describe(Object input) {
        return switch (input) {
            case Order order when eligibleReadable(order) ->
                    "Đủ điều kiện: " + order.id();
            case Order order ->
                    "Cần kiểm tra: " + order.id();
            case null ->
                    "Không có dữ liệu";
            default ->
                    "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        Object good = new Order("O-1",
                new Customer("Lan", new Address("Hà Nội"), true),
                150);
        Object inactive = new Order("O-2",
                new Customer("Minh", new Address("Đà Nẵng"), false),
                250);
        Object lowTotal = new Order("O-3",
                new Customer("An", new Address("Hà Nội"), true),
                80);
        Object missingAddress = new Order("O-4",
                new Customer("Bình", null, true),
                300);

        System.out.println(eligibleInline(good));
        System.out.println(eligibleReadable(good));
        System.out.println(describe(good));
        System.out.println(describe(inactive));
        System.out.println(describe(lowTotal));
        System.out.println(describe(missingAddress));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Use **JDK 21 or later** and run:

```bash
javac ReadablePatternExpressionsDemo.java
java ReadablePatternExpressionsDemo
```

Expected output:

```text
true
true
Đủ điều kiện: O-1
Cần kiểm tra: O-2
Cần kiểm tra: O-3
Cần kiểm tra: O-4
Không phải đơn hàng
Không có dữ liệu
```

Explanation:

- `good` has a complete structure, an active customer, valid ID and name, total `150`, and city `Hà Nội`. Both `eligibleInline` and `eligibleReadable` return `true`; `describe` selects the `when` branch.
- `inactive` has complete data, but `active == false`, so it is ineligible. `describe` selects the general `Order` branch.
- `lowTotal` has total `80`, below the `100` threshold, so it is ineligible.
- `missingAddress` has `address == null`. The nested pattern `Address(String city)` does not match; `eligibleReadable` returns `false` at the very first guard. `describe` still receives the whole `Order` and prints “Cần kiểm tra”.
- The string `"khác"` goes to `default`, while the `null` selector goes to `case null`.

The condition methods in the example only compute and return values without mutating external data. As a result, comparing the two versions and testing them becomes straightforward.

## 8. Risks of Cramming Too Much Logic into an Expression

### 8.1. Hard to Find Why a Condition Evaluates to False

A long expression using many `&&` operators returns `false` at the first failing condition. This is Java's correct short-circuiting behavior, but **if you need to know why it failed**, a single boolean value is not enough. Use guard clauses with specific reasons or an explicit validation result model.

### 8.2. Overusing the Ternary Operator

Hard-to-read example:

```java
// Illustrative snippet, assuming the variables have already been declared:
String label = active
        ? total >= 100
            ? isSupportedCity(city) ? "Ưu tiên" : "Sai địa điểm"
            : "Giá trị thấp"
        : "Ngừng hoạt động";
```

This expression may be valid, but it forces the reader to trace nested `?:` levels. When there are multiple reasons and business priorities, a method with early-return `if` statements or a simple `switch` usually expresses the intent better. Any syntactic refactoring must preserve the check order and the result for each case.

### 8.3. Forgetting Pattern Variable Scoping Rules

Variables bound by a pattern only exist where the compiler knows the pattern has matched. You cannot assume those variables can be used in the `else` branch, on the right-hand side of `||`, in other `case` branches, or outside the method. Once a condition becomes complex, extract the pattern into an initial guard like `eligibleReadable` so it is clear where the variables become valid.

### 8.4. Introducing Side Effects in Conditions

Avoid putting operations such as database writes, sending notifications, or updating counters inside `&&` or `when` if the meaning of the action does not depend entirely on the preceding condition being true. Due to short-circuiting, some expressions might **never be evaluated**. Check the conditions first, then perform state-changing actions in an explicit handling block.

### 8.5. Using Deeper Patterns Than Necessary

A deeply nested record pattern is only appropriate if the handling code genuinely needs the deeply nested components. If a `switch` only needs to classify an `Order`, `case Order order` combined with a named function is usually easier to read than a `case Order(String id, Customer(String name, Address(String city), boolean active), int total) when ...` spanning multiple lines.

### 8.6. Confusing Readability with Performance

Splitting an expression into multiple functions does not automatically make a program noticeably slower or faster; the compiler and JVM have many optimization mechanisms. First ensure the code is **correct and maintainable**; if performance is truly a critical requirement, use appropriate measurements rather than guessing based solely on line count.

## 9. Practical Criteria for Deciding Whether to Split an Expression

| Sign | How to Improve |
| --- | --- |
| An expression both checks types and handles many business rules | Keep the pattern for structure; extract rules into named functions. |
| Multiple nested `?:` levels with different messages | Use guard clauses or a `switch` with easily recognizable branches. |
| A `case ... when ...` that is too long and repeated across branches | Move pure conditions into an `isEligible(...)` method or a similarly named one. |
| Easy to confuse variable scope across `&&` and `||` | Put the pattern in an initial guard; use variables where the match is proven. |
| Need to distinguish multiple rejection reasons | Return a result with a reason, instead of a single boolean. |
| Very deeply nested pattern when only the whole record is needed | Use a type pattern to keep the record variable and call a separate handling function. |
| Condition contains side effects depending on evaluation order | Separate checks from actions and make execution order explicit. |

There is no rule saying "more than three conditions is wrong" or "any nested pattern must be split." Choose a style that lets others read top-to-bottom and explain **when each branch runs**, **why a value qualifies**, and **what happens when it does not match**.

## 10. Self-Check

Suppose you have:

```java
record Score(String subject, int points) {}
Object input = new Score("Java", 85);
```

A concise, clearly structured expression is still very appropriate:

```java
boolean passed = input instanceof Score(String subject, int points)
        && "Java".equals(subject)
        && points >= 80;
System.out.println(passed);
```

The result is `true`. If this evolves into an application with different thresholds per subject, needing to check whether the student is allowed to take the exam and report the reason for failing, you should extract the business conditions into functions or guard clauses. Doing so gives every change a clear place and prevents one expression from becoming a dumping ground for all rules.

**Key takeaway:** Pattern matching makes Java expressions shorter and more accurate when checking types and structure. Keep expressions **simple enough to clearly read the match conditions, variable scopes, and outcomes**. When too many business conditions, messages, side effects, or nested branches appear, move to named methods, guard clauses, or `switch` statements with short guards; preserve the evaluation order and behavior when refactoring.
