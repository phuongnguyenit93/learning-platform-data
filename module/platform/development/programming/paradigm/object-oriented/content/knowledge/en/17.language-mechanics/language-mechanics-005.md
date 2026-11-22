# Operators, properties, and conventions in Java

**Topic:** OOP → Language Mechanics.  
**Goal:** Use operator groups correctly; understand expression precedence and result types; distinguish data *fields* from JavaBeans-style properties, getters/setters, and `record` components; apply Java conventions for clear, safe, maintainable code.

Java has fairly strict syntax and type rules. An expression that compiles can still yield wrong results due to integer division, overflow, mistaken reference comparison, side effects, or misunderstood evaluation order. Likewise, a field being accessible externally does not mean all object state should be `public`.

## 1. Operator groups at a glance

| Group | Common symbols | Purpose | Caution |
| --- | --- | --- | --- |
| Arithmetic | `+`, `-`, `*`, `/`, `%` | Computation; `+` also concatenates strings | `int/int` uses integer division; `%` yields a remainder |
| Increment/decrement | `++`, `--` | Increase/decrease a variable by one | Prefix and postfix differ in when a value is read |
| Sign and negation | `+x`, `-x`, `!flag`, `~bits` | Negate a number, Boolean, or individual bits | `!` is for Booleans; `~` operates on integral types |
| Comparison | `<`, `<=`, `>`, `>=` | Compare numbers or types with supported operators | You cannot compare two `String` values using `<` |
| Equality | `==`, `!=` | Compare primitives by value and references by identity | Object contents usually use `equals()` |
| Logical | `&&`, `\|\|`, `!` | Combine Boolean conditions | `&&` / `\|\|` short-circuit |
| Bitwise | `&`, `\|`, `^`, `~` | Operate on bits of integral types; `&`/`\|`/`^` also accept Boolean values | Boolean `&` and `\|` evaluate both sides |
| Bit shifting | `<<`, `>>`, `>>>` | Left, signed right, and 0-fill right shifts | Shift counts are masked by type width |
| Assignment | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, … | Update variables | Compound assignments can narrow implicitly to the left-side type |
| Ternary | `condition ? x : y` | Select one of two expressions | Only the selected branch executes |
| Type testing | `instanceof` | Check whether an object is a type at runtime | For `null`, the result is `false` |
| Access/call | `.`, `[]`, `()`, `new` | Access members/elements, call methods, construct objects | Behavior depends on visibility and expression types |

Lambda `->` and method-reference `::` syntax are also important, but they are not ordinary arithmetic operators. They describe functions/method references compatible with functional interfaces.

### Small example: operator results

```java
int a = 7;
int b = 3;

System.out.println(a + b); // 10
System.out.println(a / b); // 2: chia nguyên
System.out.println(a % b); // 1
System.out.println((double) a / b); // 2.3333333333333335

int count = 5;
System.out.println(count++); // 5: dùng giá trị cũ rồi tăng
System.out.println(++count); // 7: tăng trước rồi dùng

System.out.println(-7 % 3); // -1: dấu của phần dư theo số bị chia
```

In Java, **the remainder operator `%` is not the same as always-nonnegative modulo**. For a nonnegative result with a positive divisor, use `Math.floorMod(a, b)` rather than assuming `a % b >= 0`. For example, `Math.floorMod(-7, 3) == 2`.

## 2. Precedence, associativity, and evaluation order

Read expressions using three distinct concepts:

- **Precedence** determines how expressions are grouped when parentheses are omitted.
- **Associativity** determines grouping among operators at **the same precedence**; most binary operators group left to right, while assignments and conditionals group right to left.
- **Evaluation order** describes when operands are computed and side effects occur. Java generally evaluates operands from left to right according to expression rules; this does not mean “every operator executes left to right.”

A shortened Java precedence table (top to bottom, highest to lowest):

| Level | Group | Example |
| --- | --- | --- |
| Highest in this table | Member access, calls, indexing, postfix | `object.field`, `f()`, `array[i]`, `x++` |
| | Unary, casts, prefixes | `!ok`, `~mask`, `(long) x`, `++x` |
| | Multiplication/division/remainder | `*`, `/`, `%` |
| | Addition/subtraction | `+`, `-` |
| | Bit shifts | `<<`, `>>`, `>>>` |
| | Relational/type tests | `<`, `<=`, `>`, `>=`, `instanceof` |
| | Equality | `==`, `!=` |
| | Bitwise or Boolean AND, XOR, OR | `&` then `^` then `\|` |
| | Logical AND | `&&` |
| | Logical OR | `\|\|` |
| | Conditional | `?:` |
| Lowest | Assignment and compound assignment | `=`, `+=`, `-=`, … |

For example:

```java
int result = 2 + 3 * 4;       // 14
int explicit = (2 + 3) * 4;   // 20

boolean allowed = true || false && false; // true
boolean clear = true || (false && false); // true

int x = 1, y = 2, z = 3;
x = y = z; // Tương đương x = (y = z)
```

**Use parentheses when they clarify intent**, particularly for mixed bitwise/logical operators, long conditions, and numerical conversions. Avoid cramming multiple `++` operations, assignments, or side-effecting calls into one line.

A common pitfall:

```java
System.out.println("Tổng: " + 1 + 2);     // Tổng: 12
System.out.println("Tổng: " + (1 + 2));   // Tổng: 3
```

Addition and string concatenation have the same precedence and associate left to right; once the left operand becomes a string, subsequent `+` operations concatenate. Java will not infer that you intended numeric addition first.

## 3. Result types, numeric promotion, and overflow

### 3.1. Division and numeric promotion

```java
int total = 5;
int portions = 2;

double wrong = total / portions;           // 2.0
double correct = (double) total / portions; // 2.5
```

On the first line, `total / portions` is evaluated using `int` arithmetic **before** assignment to `double`, so the fractional part is lost. Casting one operand before division changes the arithmetic type.

For ordinary arithmetic on `byte`, `short`, and `char`, Java applies **binary numeric promotion**: types smaller than `int` are usually promoted to `int`:

```java
byte first = 10;
byte second = 20;

// Lỗi biên dịch: kết quả của first + second là int.
// byte sum = first + second;

int sum = first + second; // 30
```

`short` and `char` follow similar rules. If an operand is `long`, `float`, or `double`, promotion usually follows the wider type under binary numeric-promotion rules. Exact details depend on the operator.

### 3.2. Compound assignments can narrow types

```java
byte value = 127;
value += 1;
System.out.println(value); // -128
```

Compound assignment `E1 op= E2` is equivalent in value to `E1 = (T) ((E1) op (E2))`, where `T` is the type of `E1`, **except that `E1` is evaluated only once**. Thus `byte += int` can implicitly narrow back to `byte` and overflow unnoticed.

For financial operations, large counters, data versions, and other critical calculations, validate ranges and consider `Math.addExact`, `Math.subtractExact`, and `Math.multiplyExact` with `int`/`long`:

```java
try {
    int next = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(next);
} catch (ArithmeticException overflow) {
    System.out.println("Tràn miền giá trị int");
}
```

Ordinary primitive integer addition/subtraction/multiplication **do not throw on overflow**; values wrap according to type width. Integer division by 0 throws `ArithmeticException`.

### 3.3. Floating-point numbers and currency

```java
System.out.println(0.1 + 0.2 == 0.3); // false (IEEE 754)
```

`float`/`double` use binary floating-point representations; some decimals cannot be represented exactly. Do not compare computed floating-point results with `==` if the problem requires a tolerance or specific rounding policy.

For money, use **integer minor units** (for example, `long` VND when the domain range permits) or `BigDecimal` with explicit rounding rules:

```java
java.math.BigDecimal price =
        new java.math.BigDecimal("0.10");
java.math.BigDecimal tax =
        new java.math.BigDecimal("0.20");

System.out.println(price.add(tax).toPlainString()); // 0.30
```

Avoid `new BigDecimal(0.1)` when exact representation of decimal `0.1` is required; favor string-based constructors or `BigDecimal.valueOf(double)` when the input is already a `double` and conversion semantics are understood.

## 4. Comparing `==`, `equals()`, and value types

For **primitives**, `==` compares values after applicable numeric conversions:

```java
int a = 42, b = 42;
System.out.println(a == b); // true
```

For **reference types**, `==` tests **whether references point to the same object**:

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
```

`new String` creates distinct objects in this example. Two literals `"Java" == "Java"` may compare `true` due to string interning, but **do not use `==` to compare String contents**.

For null-safe content comparison where values may be `null`, use:

```java
java.util.Objects.equals(first, second);
```

`Objects.equals(null, null)` is `true`, while `Objects.equals(null, "x")` is `false`. Custom `equals()` implementations must be reflexive, symmetric, transitive, consistent, and false for `null`. When overriding `equals()`, also override `hashCode()` so equal objects share a hash code.

For arrays:

```java
int[] left = {1, 2};
int[] right = {1, 2};

System.out.println(left == right); // false
System.out.println(java.util.Arrays.equals(left, right)); // true
```

`Arrays.equals` compares corresponding elements of one-dimensional arrays; nested arrays may need `Arrays.deepEquals`. `record` generates `equals/hashCode/toString` based on components, but **array components still use array equality semantics**; records do not automatically compare nested array contents deeply.

For `BigDecimal`, `equals()` considers **scale**, whereas `compareTo()` compares numeric values:

```java
var x = new java.math.BigDecimal("1.0");
var y = new java.math.BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

Choose comparison semantics appropriate to the domain, such as monetary values, input formatting, or collection uniqueness.

## 5. Short-circuit logic, bitwise operations, and conditionals

### 5.1. `&&` and `||` short-circuit

```java
String input = null;

boolean valid = input != null && !input.isBlank();
System.out.println(valid); // false; vế phải không chạy
```

When the left side of `&&` is false, Java skips the right side. When the left side of `||` is true, Java also skips the right side. Short-circuiting makes guards safe and avoids unnecessary work.

In contrast, `&` and `|` also work on Booleans but **evaluate both operands**:

```java
boolean firstCheck = false;
boolean secondCheck = true;

System.out.println(firstCheck && secondCheck); // false
System.out.println(firstCheck & secondCheck);  // false
```

Results may match, but `&` still evaluates its right operand. For example, `input != null & !input.isBlank()` throws `NullPointerException` when input is null. Use `&&`/`||` for ordinary control-flow conditions, and `&`/`|` for bits or when evaluation of both sides is intentional.

### 5.2. Bitwise operations and bit shifts

```java
int mask = 0b1010;
mask |= 0b0100;                  // 0b1110
boolean enabled = (mask & 0b0100) != 0; // true

System.out.println(1 << 3);         // 8
System.out.println(-8 >> 1);        // -4: mở rộng bit dấu
System.out.println(-8 >>> 1);       // 2147483644: dịch phải điền 0
System.out.println(1L << 32);       // 4294967296
```

`>>` is a sign-preserving right shift; `>>>` shifts right, filling with 0. For `int`, Java uses only the **lowest 5 bits** of the shift distance; for `long`, only the **lowest 6 bits**. Thus `1 << 32` evaluates to `1`, not `4294967296`; to shift by 32 bits on long, use `1L << 32`.

Avoid bitwise operators as a supposed “optimization” when they obscure arithmetic intent; the JVM/JIT performs many optimizations already, while readable code is easier to verify.

### 5.3. Ternary operator

```java
long goodsTotalVnd = 600_000L;
long deliveryFeeVnd = goodsTotalVnd >= 500_000L
        ? 0L
        : 30_000L;
```

`?:` evaluates one of two branches; the unselected branch does not run. It works well for concise choices with compatible types. Prefer `if/else` for complex conditions, side effects, or detailed error handling.

**Ternary expression types:** Java has specific rules for selecting a result type based on branch types and context; mixing primitives with wrappers can trigger **unboxing** and `NullPointerException` unexpectedly. Do not assume the broadest common type always wins; use explicit `if/else` when nulls or mixed types make semantics unclear.

## 6. `instanceof`, casts, and pattern matching

In Java 17, you can use **pattern matching for `instanceof`**:

```java
static int normalizedTextLength(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.trim().length();
    }
    return 0;
}
```

When `instanceof String text` succeeds, `text` has type `String` and is in scope where Java can prove the pattern matched. If `value == null`, `instanceof` evaluates to `false` without throwing.

The traditional approach:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Distinguish **reference casting** (which may throw `ClassCastException` at runtime) from **primitive numeric conversions** (which may truncate fractions or overflow their range):

```java
double original = 12.9;
int truncated = (int) original; // 12: bỏ phần thập phân
```

Casting is not a way to “repair” generic API design. If code repeatedly casts between classes, consider expressing its contract using more precise types.

## 7. Properties in Java: fields, accessors, and properties

In OOP, an object's “properties” often refer to state-defining data, but Java distinguishes several concepts:

| Concept | Example | Meaning |
| --- | --- | --- |
| **Field** | `private String email;` | A variable declared in a class, belonging to an instance or the class |
| **Instance field** | `private boolean active;` | Each object has its own state |
| **Static field** | `private static int count;` | Value belongs to the class and is shared among instances |
| **Accessor/getter** | `getEmail()`, `isActive()` | Method that exposes readable state through an API |
| **Mutator/setter** | `setActive(boolean)` | Method updating state, possibly with validation |
| **JavaBeans property** | Property `email` inferred from `getEmail()`/`setEmail(...)` | Getter/setter convention used by frameworks and tools |
| **Record component** | `record User(String email)` | Record component generating a private final field and `email()` accessor |
| **Local variable** | `int total = 0;` inside a method | Variable with local scope, not an object field |

**Java has no built-in property declaration syntax like C#** `public string Name { get; set; }`. In Java libraries, “property” often means a convention recognized through methods or framework metadata. Accessing `user.email` accesses a visible field; it **does not automatically invoke** `getEmail()`.

Example of an encapsulated data class:

```java
public final class UserProfile {
    private final String email;
    private boolean active;

    public UserProfile(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        this.email = email.trim();
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

`email` is assigned only during construction; `active` can change. Not every field needs a setter. Real business operations may deserve more expressive names:

```java
public void activate() {
    if (active) {
        return;
    }
    active = true;
}
```

Domain-specific methods are often better at enforcing invariants than generic setters. If activation requires approvals or permissions, checks belong at appropriate responsibility boundaries.

### 7.1. Access modifiers and encapsulation

| Modifier | Where is it accessible? | Intended use |
| --- | --- | --- |
| `private` | Inside the class/related nested structures according to Java rules | Internal fields, invariants, helpers |
| No modifier (*package-private*) | Within the same package | Package-scoped implementation components |
| `protected` | Same package; also subclasses in other packages under `protected` access rules | Deliberate subclass extension APIs |
| `public` | Where the enclosing type is visible | Stable public APIs |

Prefer **the narrowest visibility that meets actual needs**. A public getter does not entitle callers to passwords, tokens, sensitive values, or mutable internal state.

If a field holds a mutable collection, returning it directly allows callers to change internal data:

```java
private final java.util.List<String> tags =
        new java.util.ArrayList<>();

public java.util.List<String> getTags() {
    return java.util.List.copyOf(tags); // snapshot không sửa qua getter
}
```

`List.copyOf` creates an unmodifiable list separate from the source list's structure but **does not deep-copy mutable elements**. The example uses `String` elements, so this is safe. Mutable objects with setters may require immutable Value Objects or defensive copies of each element.

### 7.2. `static`, `final`, `var`, and `record`

- `static` marks class-level members; `static final` is commonly used for constants. **Not every `static final` value is a compile-time constant**.
- `final` prevents **reassignment of a variable/field reference or value once initialized**, but does not make its referenced object immutable.
- `var` (Java 10+) infers **local variables with initializers**, certain loop variables, and lambda parameters in permitted situations; it cannot declare fields or method return types. `var x = null;` is invalid.
- `record` (stable since Java 16) fits data modeled as values. Records **do not provide deep immutability** for array/list/mutable object components.

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("Java"); // Hợp lệ: sửa object mà names trỏ tới

// names = new java.util.ArrayList<>(); // Lỗi: gán lại biến final
```

`volatile` governs **visibility and memory ordering between threads**; it does not make operations like `count++` atomic. Do not use `volatile` instead of locking or `AtomicInteger` when atomic read-modify-write is required.

## 8. JavaBeans and records: choosing data contracts

### 8.1. Conventional getters/setters

JavaBeans conventions typically use:

```java
String getName()
void setName(String value)
boolean isEnabled()
```

JavaBeans tooling and many frameworks derive property names from methods. However, **not every class with getters/setters is a full JavaBean under the specification**, which also describes conventions for construction, events, introspection, and sometimes serializability.

Arbitrary entity setters can break invariants; do not generate getters/setters for every field automatically. An API such as `changeEmail(...)` with data, state, and permission validation may be preferable to a logic-free setter.

### 8.2. Records do not generate `getX()` accessors by default

```java
record Product(String sku, long unitPriceVnd) {
    Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("Đơn giá âm");
        }
        sku = sku.trim();
    }
}

Product product = new Product(" P-01 ", 125_000L);
System.out.println(product.sku());          // P-01
System.out.println(product.unitPriceVnd()); // 125000
```

Records generate `sku()` and `unitPriceVnd()`, not `getSku()` and `getUnitPriceVnd()` by default. They also generate `equals`, `hashCode`, and `toString` from components. Check each serialization/binding framework's conventions when replacing JavaBeans with records.

### 8.3. When should properties be mutable?

A UI form may require incremental edits to several fields. A valid shipping-address domain Value Object is often better immutable. ORM entities may have special construction, hydration, or proxy requirements.

Decide **who may modify state, when, and under what valid conditions** before introducing public setters, builders, constructors, records, or domain-specific operations.

## 9. Java naming and code organization conventions

Common Java conventions improve consistency and comprehension; not all are compiler-enforced rules.

| Element | Convention | Example |
| --- | --- | --- |
| Package | Lowercase, often reverse-domain | `com.example.order` |
| Class/record/interface/enum | `UpperCamelCase` | `OrderService`, `Money`, `PaymentStatus` |
| Methods and fields | `lowerCamelCase` | `calculateTotal()`, `totalPrice` |
| Local variables | `lowerCamelCase`, meaningful name | `deliveryFeeVnd`, `isExpired` |
| Constants that really are constant `static final` | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Generic type parameters | Short role-based names when clear | `T` = Type, `E` = Element, `K` = Key, `V` = Value |
| Test names | Describe behavior or conditions | `rejectsNegativePrice` |
| Java files with public top-level types | Filename matches public type | `OrderService.java` |

Helpful code-reading practices:

1. A method needs **an action-oriented name**, not just `process()` without context; Boolean predicates may use `isActive()`, `hasAccess()`, or `canRetry()`.
2. Use `@Override` when overriding methods so the compiler detects mismatched signatures.
3. Apply `final` deliberately for references that should not be reassigned; merely adding `final` does not make data immutable.
4. Convey units in names or Value Objects: `timeoutMillis` and `priceVnd` help distinguish milliseconds from seconds and currencies.
5. Do not hide failures with `catch (Exception ignored)`; handle only errors owned by the current layer.
6. Keep classes, packages, and public APIs focused on responsibilities; getter/setter counts are not a measure of “being OOP.”

**IDE formatters can standardize syntax**, but naming depends on business vocabulary. Clear names matter more than arbitrary fixed character counts or line limits.

## 10. Java 17 program combining operators and properties

Save the complete example as **LanguageMechanicsDemo.java**. It runs on JDK 17+ without external libraries.

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Objects;

public class LanguageMechanicsDemo {

    // Giá trị nghiệp vụ bất biến, record có compact constructor.
    public record Product(String sku, long unitPriceVnd) {
        public Product {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU không hợp lệ");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException("Đơn giá âm");
            }
            sku = sku.trim();
        }
    }

    // Đối tượng có encapsulation và method thay đổi trạng thái rõ nghĩa.
    public static final class CartLine {
        private final Product product;
        private int quantity;

        public CartLine(Product product, int quantity) {
            this.product = Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải dương");
            }
            this.quantity = quantity;
        }

        public Product getProduct() {
            return product;
        }

        public int getQuantity() {
            return quantity;
        }

        public void increaseQuantity(int delta) {
            if (delta <= 0) {
                throw new IllegalArgumentException(
                        "Giá trị tăng phải dương");
            }
            quantity = Math.addExact(quantity, delta);
        }

        public long goodsTotalVnd() {
            return Math.multiplyExact(
                    product.unitPriceVnd(), (long) quantity);
        }
    }

    public static long checkoutTotalVnd(
            CartLine line, boolean vipCustomer) {
        Objects.requireNonNull(line, "line");
        long goodsTotalVnd = line.goodsTotalVnd();

        // VIP được miễn phí vận chuyển, khách khác miễn khi đủ ngưỡng.
        long shippingFeeVnd =
                vipCustomer || goodsTotalVnd >= 500_000L
                        ? 0L : 30_000L;

        return Math.addExact(goodsTotalVnd, shippingFeeVnd);
    }

    public static String normalizeText(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.trim();
        }
        return "";
    }

    public static void main(String[] args) {
        Product product = new Product(" P-01 ", 125_000L);
        CartLine line = new CartLine(product, 2);

        line.increaseQuantity(1);

        System.out.println(product.sku());               // P-01
        System.out.println(line.getQuantity());           // 3
        System.out.println(line.goodsTotalVnd());         // 375000
        System.out.println(checkoutTotalVnd(line, false)); // 405000
        System.out.println(checkoutTotalVnd(line, true));  // 375000

        System.out.println(normalizeText("  Java  "));    // Java

        Product sameValue = new Product("P-01", 125_000L);
        System.out.println(product.equals(sameValue));   // true
        System.out.println(product == sameValue);        // false

        System.out.println(Arrays.equals(
                new int[]{1, 2}, new int[]{1, 2}));      // true

        BigDecimal sum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println(sum.toPlainString());          // 0.3
    }
}
```

Run:

```bash
javac LanguageMechanicsDemo.java
java LanguageMechanicsDemo
```

Output:

```text
P-01
3
375000
405000
375000
Java
true
false
true
0.3
```

In this example:

- **Arithmetic operators** calculate item totals; `Math.multiplyExact` and `Math.addExact` make integer-overflow behavior explicit.
- **`||` and `?:`** implement shipping-fee choices with short-circuiting.
- **`instanceof String text`** filters input before string processing.
- The **Product record** is a Value Object; two separate instances may have equal contents, so `equals()` and `==` differ.
- **CartLine** encapsulates mutable state and changes quantities only through validated `increaseQuantity()`.
- **Accessors** let clients read without directly changing `quantity`; the conventional `getQuantity()` differs from a record's `product.sku()` accessor.

Using `long` VND amounts is an exercise assumption. Real applications must specify currency, tax, discounts, rounding, and valid ranges; do not blindly switch to `double` for money.

## 11. Test behavior rather than operator tricks

Example **JUnit Jupiter 5** tests (in **LanguageMechanicsDemoTest.java**; JUnit must be configured in the project):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LanguageMechanicsDemoTest {

    @Test
    void khachThuongChuaDuNguongPhaiTraPhiGiao() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertEquals(280_000L,
                LanguageMechanicsDemo.checkoutTotalVnd(line, false));
    }

    @Test
    void khachVipDuocMienPhiGiao() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertEquals(250_000L,
                LanguageMechanicsDemo.checkoutTotalVnd(line, true));
    }

    @Test
    void khongChoGiamSoLuongBangSoAm() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 1);

        assertThrows(IllegalArgumentException.class,
                () -> line.increaseQuantity(-1));
        assertEquals(1, line.getQuantity());
    }

    @Test
    void phatHienTranSo() {
        var product =
                new LanguageMechanicsDemo.Product("P01", Long.MAX_VALUE);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertThrows(ArithmeticException.class, line::goodsTotalVnd);
    }

    @Test
    void recordSoSanhTheoGiaTri() {
        var a =
                new LanguageMechanicsDemo.Product(" P01 ", 100L);
        var b =
                new LanguageMechanicsDemo.Product("P01", 100L);

        assertEquals(a, b);
        assertNotSame(a, b);
    }

    @Test
    void patternMatchingXuLyNull() {
        assertEquals("",
                LanguageMechanicsDemo.normalizeText(null));
        assertEquals("Java",
                LanguageMechanicsDemo.normalizeText(" Java "));
    }
}
```

A strong test suite focuses on **input constraints, ranges, business results, boundary cases, and exceptions**. Avoid constructing needlessly convoluted expressions just to test the compiler. When using `BigDecimal` for money, verify division, scale, rounding mode, and numeric comparisons explicitly.

## 12. Common Java mistakes involving conventions

| Scenario | Problem | Remedy |
| --- | --- | --- |
| `if (name == "admin")` | Compares identity rather than guaranteed content | Use `"admin".equals(name)` or `Objects.equals` |
| `double rate = 5 / 2;` | Performs integer division before converting to double | Use `5.0 / 2` or `(double) 5 / 2` |
| `int result = a * b;` with large values | May overflow silently | Use `Math.multiplyExact` or a suitable type/algorithm |
| `x != null & x.isReady()` | Right operand runs even if `x == null` | Use `&&` when short-circuiting is required |
| Returning a `List` directly from a getter | Callers can mutate internal state | Provide snapshots/immutable views and enforce invariants |
| All fields are `public` | State changes cannot be controlled | Use `private`, constructors, and domain methods |
| Generating setters for every state | Callers can bypass lifecycle rules | Expose only allowed operations |
| Treating a `final List` as immutable | `final` only prohibits reference reassignment | Use immutable collections/defensive copies |
| Using a `record` with an `int[]` component and assuming `equals()` compares arrays by contents | Arrays use reference equality | Design suitable value objects or implement equality/hash codes |
| `volatile int count; count++` | `++` is not atomic | `AtomicInteger`, locks, or suitable concurrency control |
| Naming a `timeout` without units | Seconds/milliseconds become ambiguous | Use `timeoutMillis` or `Duration` |
| Putting many side effects in one expression | Difficult evaluation-order reasoning and debugging | Split steps into named intermediate variables |

## 13. Practical exercise

Build `InvoiceLine` with `unitPriceVnd` and `quantity`, and `Invoice` containing multiple invoice lines.

**Requirements:**

1. Use a `record` or immutable class for unit prices and item codes; reject negative prices and nonpositive quantities.
2. Implement `goodsTotalVnd()` with overflow protection. Shipping is free for orders of at least **1.000.000 VND** or VIP members; otherwise it costs 25.000 VND.
3. Prevent callers from directly appending to the `Invoice` collection. Use `List.copyOf` or defensive copies.
4. Compare `==` and `equals()` for two separately created but equal Value Objects.
5. Write the `String coupon != null && !coupon.isBlank()` condition; explain what happens if `&&` becomes `&` when null is possible.
6. Test the free-shipping threshold, increased quantities, values of 0, overflow, nulls, and invalid data.
7. Review whether names, fields, methods, classes, constants, monetary units, visibility, and immutability accurately express the domain.

**Acceptance criteria:** Code compiles and runs on Java 17+, does not use reference identity for content equality, does not unintentionally lose fractional values, prevents silent overflow in critical calculations, encapsulates internal data, and follows clear Java conventions.

**Remember:** Operators determine **how expressions are evaluated**; the type system determines **which operations are permitted**; and Java fields/properties and conventions determine **how state is exposed and controlled**. Understanding all three produces correct, readable, maintainable OOP code.
