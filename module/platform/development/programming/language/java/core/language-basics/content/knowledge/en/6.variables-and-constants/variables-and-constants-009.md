# Naming Conventions for Variables, Parameters, and Constants in Java 17+

## 1. Why Naming Conventions Matter

Variable, parameter, and constant names are part of how a program expresses its meaning. Java **checks whether names are syntactically valid**, while **naming conventions** help others understand the data, reduce confusion, and make searching easier during maintenance.

~~~java
int x = 3;                   // Valid but hard to know what x is
int itemCount = 3;           // Same data type, clearer meaning

int p = 120_000;             // Unit or role is not visible
int unitPriceDong = 120_000; // Indicates this is the unit price in dong
~~~

Three practical principles:

1. **Syntactically valid in Java**: names cannot be keywords or reserved literals, cannot start with a digit, and must follow identifier rules.
2. **Clear role**: names state the data or business intent instead of merely repeating the type name.
3. **Consistent across the entire project**: the same concept should be named uniformly, avoiding switching between `amount`, `value`, and `money` without a reason.

A "standard-compliant" name does not guarantee the program's business logic is right; however, unclear names can hide bugs even when the program compiles.

## 2. Table of Commonly Used Conventions

| Element | Common style | Recommended examples | Avoid without good reason |
|---|---|---|---|
| Local variable | `lowerCamelCase` | `itemCount`, `totalPriceDong` | `ItemCount`, `item_count` |
| Method parameter | `lowerCamelCase` | `unitPriceDong`, `discountPercent` | `UnitPrice`, `arg1` |
| Instance field | `lowerCamelCase` | `customerName`, `isActive` | `CUSTOMER_NAME` for ordinary fields |
| Mutable static field | `lowerCamelCase` | `requestCount` | `REQUEST_COUNT` if not a constant |
| Named constant | `UPPER_SNAKE_CASE` | `MAX_ITEMS`, `DEFAULT_TIMEOUT_MS` | `max_items`, `DefaultTimeoutMs` |
| `final` local variable | Usually still `lowerCamelCase` | `final int maxAllowed = 5;` | Converting every final local to `MAX_ALLOWED` by default |
| Enum constant | Usually `UPPER_SNAKE_CASE` | `PENDING`, `IN_PROGRESS` | Mixing naming styles across values |

These are **conventions**, not rules enforced by `javac`. For instance, `int ItemCount = 3;` can compile while breaking standard style. Lint/style tools may enforce stricter project-specific rules.

**`lowerCamelCase`**: the first word is lowercase, and subsequent words start with an uppercase letter: `maxRetryCount`.

**`UPPER_SNAKE_CASE`**: words are all uppercase, separated by `_`: `MAX_RETRY_COUNT`.

## 3. Distinguishing Valid Names from Recommended Names

Java is case-sensitive, so `count`, `Count`, and `COUNT` are **three distinct identifiers**. Yet using all three in the same scope is very confusing.

~~~java
int count = 3;
// int Count = 4; // May be valid, but avoid creating overly similar pairs
~~~

Cases worth remembering:

| Identifier | Valid as a variable name? | Assessment |
|---|---|---|
| `itemCount` | Yes | Follows convention and clear |
| `_itemCount` | Yes | Leading `_` is usually unnecessary |
| `$itemCount` | Yes | Java allows `$`, but avoid using arbitrarily |
| `sốLượng` | Yes | Java supports Unicode; projects need a consistent convention |
| `2items` | No | Starts with a digit |
| `item-count` | Not a single identifier | `-` is an operator |
| `item count` | No | Contains whitespace |
| `class` | No | Java keyword |
| `true` | No | Reserved boolean literal |
| `_` | No in Java 17 | Single underscore is reserved |

A valid name still must be placed in the **proper scope** and **not redeclared illegally**. Two local variables with the same name cannot be declared in the same block.

`String` and `string` are not the same identifier; when naming, avoid forcing readers to "guess" casing.

## 4. Naming Variables by Meaning, Unit, and State

A variable name should answer "what does this value represent?":

~~~java
int itemCount = 3;
long totalPriceDong = 360_000L;
int timeoutMillis = 2_500;
double distanceKilometers = 12.5;
String customerEmail = "lan@example.com";
~~~

If two values share a type but have different **units**, the names should indicate the units:

~~~java
long timeoutMillis = 500;
long timeoutSeconds = 2;

// Do not treat 500 and 2 as the same unit just because both are long.
~~~

For important domains like time and currency, dedicated types (such as `Duration`, `BigDecimal`) can be used instead of raw numbers. Still, when using primitives, unit-bearing names help reduce errors.

**Avoid content-free names**: `data`, `value`, `obj`, `temp`, `str` when a more specific noun can be used. A short loop variable `i` can be acceptable in a very clear 2–3 line context; for longer loops, `itemIndex` or `orderIndex` is easier to follow.

### Boolean Names as True/False Questions

`boolean` variables should generally read like a predicate:

~~~java
boolean isActive = true;
boolean hasPermission = false;
boolean canSubmit = isActive && hasPermission;
boolean isEmpty = itemCount == 0;
~~~

Prefixes like `is`, `has`, `can`, `should` help readers understand the check:

~~~java
if (hasPermission && isActive) {
    System.out.println("ALLOW");
}
~~~

Do not name a count or string variable `isActive`; the name must match the type and actual meaning.

Not every boolean has to start with `is`. Natural names like `enabled` or `valid` can still be clear when used consistently in the codebase.

## 5. Parameter Names: Expressing the Method's Contract

Parameters help callers understand a method's **inputs**. Choose names that reveal role, value domain, and unit:

~~~java
static long calculateTotalDong(
        int unitPriceDong,
        int itemCount,
        int discountPercent) {
    if (unitPriceDong < 0 || itemCount < 0
            || discountPercent < 0 || discountPercent > 100) {
        throw new IllegalArgumentException("Invalid input");
    }

    long subtotalDong = (long) unitPriceDong * itemCount;
    return subtotalDong * (100 - discountPercent) / 100;
}
~~~

`unitPriceDong`, `itemCount`, and `discountPercent` help readers distinguish **unit price**, **quantity**, and **discount percentage**, even though all are `int`.

If parameters are named `a`, `b`, `c`, the signature may still compile, but callers must open the method body to understand what they mean.

### Avoid Unintentional Shadowing of Fields by Parameter Names

A valid situation:

~~~java
class Order {
    private int itemCount;

    Order(int itemCount) {
        this.itemCount = itemCount;
    }
}
~~~

Sharing the same name between parameter and field is common; `this.itemCount` specifies the field, while `itemCount` refers to the parameter. There is no need to rename to `theItemCount` or `pItemCount` just to avoid using `this`.

However, outside intentional cases like constructors/setters, avoid name shadowing that makes code hard to understand.

## 6. Constants: Uppercase Names and Underscores

When a meaningful fixed value is reused, naming a constant helps avoid **magic numbers**:

~~~java
private static final int MAX_ITEMS = 5;
private static final int DEFAULT_DISCOUNT_PERCENT = 10;
private static final String CURRENCY_CODE = "VND";
~~~

Example:

~~~java
if (itemCount > MAX_ITEMS) {
    throw new IllegalArgumentException("Too many items");
}
~~~

`MAX_ITEMS` describes the role of the number `5`; `DEFAULT_DISCOUNT_PERCENT` reminds readers that `10` is a **percentage**, not a currency amount.

### `final` Does Not Mean Every Variable Must Be Uppercase

~~~java
final int selectedItemCount = 3;   // final local: lowerCamelCase
private static final int MAX_ITEMS = 5; // named constant: UPPER_SNAKE_CASE
~~~

`final` is a **language rule** restricting variable reassignment; whereas `UPPER_SNAKE_CASE` is a **naming convention** for named constants.

For a `static final` reference to a mutable object, preventing variable reassignment **does not** make the object's state immutable. Therefore, do not judge data immutability solely by seeing an uppercase name.

Frameworks or teams may have exceptions (e.g., `static final Logger logger` in `lowerCamelCase`). Follow the agreed style rather than applying a table mechanically.

### Unit-Related Constants

Unit-explicit names help readers self-check when using APIs:

~~~java
private static final long REQUEST_TIMEOUT_MILLIS = 3_000L;
private static final int MAX_RETRY_COUNT = 3;
~~~

Avoid naming something `TIMEOUT` when it is unclear whether it is seconds or milliseconds. Use the same term for the same concept across the system.

## 7. Runnable Java 17 Program

Save all the code below into **`NamingConventionDemo.java`**:

~~~java
public final class NamingConventionDemo {
    private static final int MAX_ITEMS = 5;
    private static final int DEFAULT_DISCOUNT_PERCENT = 10;
    private static final String CURRENCY_CODE = "VND";

    private NamingConventionDemo() {}

    static long calculateTotalDong(
            int unitPriceDong, int itemCount, int discountPercent) {
        if (unitPriceDong < 0 || itemCount < 0 || itemCount > MAX_ITEMS) {
            throw new IllegalArgumentException("Invalid item count or price");
        }
        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("Invalid discount percent");
        }
        long subtotalDong = (long) unitPriceDong * itemCount;
        return subtotalDong * (100 - discountPercent) / 100;
    }

    static boolean canCheckout(boolean isActive, boolean hasPermission) {
        return isActive && hasPermission;
    }

    public static void main(String[] args) {
        int unitPriceDong = 120_000;
        int itemCount = 3;
        int discountPercent = DEFAULT_DISCOUNT_PERCENT;
        boolean isExpressDelivery = false;

        long totalDong = calculateTotalDong(
                unitPriceDong, itemCount, discountPercent);
        boolean isActive = true;
        boolean hasPermission = true;

        System.out.println("itemCount=" + itemCount);
        System.out.println("unitPriceDong=" + unitPriceDong);
        System.out.println("discountPercent=" + discountPercent);
        System.out.println("totalDong=" + totalDong);
        System.out.println("currency=" + CURRENCY_CODE);
        System.out.println("isExpressDelivery=" + isExpressDelivery);
        System.out.println("canCheckout=" +
                canCheckout(isActive, hasPermission));
        System.out.println("maxItems=" + MAX_ITEMS);
    }
}
~~~

Open a terminal in the directory containing the file and use **JDK 17 or newer**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NamingConventionDemo.java
java -cp . NamingConventionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NamingConventionDemo.java
java -cp . NamingConventionDemo
~~~

**Expected output:**

~~~text
itemCount=3
unitPriceDong=120000
discountPercent=10
totalDong=324000
currency=VND
isExpressDelivery=false
canCheckout=true
maxItems=5
~~~

Explanation:

- `itemCount`, `unitPriceDong`, `discountPercent`, `totalDong` are meaningful `lowerCamelCase` variable names.
- The parameters of `calculateTotalDong` also use `lowerCamelCase`.
- `MAX_ITEMS`, `DEFAULT_DISCOUNT_PERCENT`, `CURRENCY_CODE` are constants named in `UPPER_SNAKE_CASE`.
- `isActive`, `hasPermission`, `canCheckout` express boolean states/conditions.
- `totalDong = 120000 × 3 × (100 - 10) / 100 = 324000` is computed in `long` before division.

This example focuses on naming conventions. In a real application, also test boundary data and define currency rounding rules per the business contract.

## 8. Name Consistency Across APIs and When Renaming

Suppose multiple methods share the concept "number of items":

~~~java
int itemCount = 3;
void updateItemCount(int itemCount) { /* ... */ }
int getItemCount() { return itemCount; }
~~~

The snippet above only illustrates naming: methods need to be placed in a valid class with appropriate fields if used as complete code.

Consistently using `itemCount` is better than mixing `num`, `qty`, `size`, and `count` when they all refer to item quantity. However, `itemCount` and `cartSize` can be two distinct concepts if the business model actually differs.

### When Renaming

- Rename local variables and parameters using your IDE's **Rename Refactor** feature when possible.
- If renaming a constant like `MAX_ITEMS`, update every corresponding reference.
- If renaming a public method/field in an API, check impacts on callers, tests, reflection, serialization, and documentation.
- Java is case-sensitive so `maxItems` does not automatically become `MAX_ITEMS`; changing a single letter's case changes the identifier.

Names do not need to be perfect on the first try, but should be improved once the data meaning is accurately understood and before the name becomes a widely depended-upon API.

## 9. Confusing Names and Better Alternatives

| Unclear name | Better name | What is clarified |
|---|---|---|
| `n` | `itemCount` | Quantity being counted |
| `p` | `unitPriceDong` | Unit price and currency unit |
| `t` | `timeoutMillis` | Duration and time unit |
| `flag` | `isActive` | Boolean state |
| `x1` | `discountPercent` | Role in the calculation |
| `MAX` | `MAX_ITEMS` | Limit on what |
| `DEFAULT` | `DEFAULT_DISCOUNT_PERCENT` | Default value of which field |
| `list` | `customerEmails` | Business-level content/type |
| `result` | `totalDong` | What the result means |

Short names are not always wrong. A loop variable `i` in a two-line loop can be clear enough. However, a public API parameter named `x` deserves closer scrutiny because callers need to understand the contract when invoking the method.

**Avoid names that mislead readers about type or behavior**: do not name an `int` variable `isReady`, and do not name a millisecond timeout `timeoutSeconds`.

## 10. Naming Convention Errors to Distinguish

| Symptom | Compiler error or convention issue? | How to handle |
|---|---|---|
| `int 2count = 3;` | Syntax error | `int count2 = 3;` |
| `int class = 1;` | Syntax error due to keyword | `int classCount = 1;` |
| `int count_value = 3;` | Compiles, breaks standard style | `int countValue = 3;` |
| `int Count = 3;` | Compiles, variable name breaks convention | `int count = 3;` |
| `static final int maxItems = 5;` | Compiles, inconsistent constant naming | `MAX_ITEMS` if truly a named constant |
| Mixing `MAX_ITEMS` and `maxItems` | Two distinct identifiers | Unify meaning and rename accurately |
| Naming an `int` as `isEnabled` | Compiles, but misleads readers | Name like `enabledItemCount` |
| `TIMEOUT_MS` with a value in seconds | Semantic bug, hard for compiler to catch | Synchronize the unit/value and name |

**Compiler errors like "cannot find symbol"** can stem from casing typos when referencing a name, not because Java requires `lowerCamelCase`.

## 11. Exercises with Answers

### Exercise A — rename to lowerCamelCase

Rename `Total_Price`, `customer_name`, and `numberOf_Items` according to convention, assuming their corresponding meanings stay unchanged.

**Suggested answer:** `totalPrice`, `customerName`, `numberOfItems`. If the price has a specific unit, even better: `totalPriceDong`.

### Exercise B — distinguishing final local and named constant

~~~java
final int retryCount = 3;
static final int MAX_RETRIES = 3;
~~~

**Answer:** `retryCount` in `lowerCamelCase` fits a `final` local; `MAX_RETRIES` in `UPPER_SNAKE_CASE` fits a `static final` class constant. The second line must be placed in a valid field declaration location, not `static` inside a method block.

### Exercise C — boolean names

Choose clear names for three states: user is logged in, account is locked, order can be submitted.

**Suggested answer:** `isLoggedIn`, `isAccountLocked`, `canSubmitOrder`; use type `boolean`.

### Exercise D — units must not be omitted

A parameter receiving a timeout in milliseconds is named `timeout`. Which name is clearer?

**Answer:** `timeoutMillis` or `timeoutMilliseconds`, consistent with project conventions. If using `Duration`, `timeout` can be clear enough because the type already conveys duration.

### Exercise E — valid but hard-to-read names

~~~java
int a = 3;
int b = 120000;
long c = (long) a * b;
~~~

Rename them so readers understand the units and roles.

**Suggested answer:**

~~~java
int itemCount = 3;
int unitPriceDong = 120000;
long subtotalDong = (long) itemCount * unitPriceDong;
~~~

Do not change the formula; only use names to explain what is being calculated.

## 12. Checklist and Conclusion

- [ ] Distinguish mandatory syntax rules from naming conventions.
- [ ] Consistently use `lowerCamelCase` for variables and parameters.
- [ ] Use `UPPER_SNAKE_CASE` for named constants when matching team style.
- [ ] Understand that `final` does not force every variable name to be uppercase.
- [ ] Choose names that express quantity, unit, and boolean state.
- [ ] Avoid overly similar names differing only by letter case.
- [ ] Intentionally distinguish parameter and field names using `this`.
- [ ] Avoid magic numbers using meaningful constant names.
- [ ] Compile and run `NamingConventionDemo.java` on JDK 17+, matching the output.
- [ ] Use rename refactoring to update names consistently and check API impact.

**Conclusion:** Variable and parameter names should describe **data or role** in `lowerCamelCase`; named constants usually use `UPPER_SNAKE_CASE`. These are conventions that keep code clear and consistent, not magic that makes a program automatically correct. Combine readable names with appropriate types, transparent units, and real behavior testing.