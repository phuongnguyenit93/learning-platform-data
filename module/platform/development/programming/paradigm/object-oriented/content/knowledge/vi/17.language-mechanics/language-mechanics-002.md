# Ràng buộc tham số kiểu (Bounded Type Parameters) trong Java Generics

**Chủ đề:** OOP → Cơ chế ngôn ngữ → Ràng buộc tham số kiểu.  
**Mục tiêu:** hiểu cách giới hạn tập kiểu có thể truyền cho một lớp hoặc phương thức generic; sử dụng đúng `extends`, nhiều ràng buộc với `&`, tự viết thuật toán với `Comparable`, phân biệt type parameter với wildcard và nhận biết giới hạn do type erasure.

## 1. Tại sao generic cần ràng buộc?

Generics cho phép viết một cấu trúc hoặc thuật toán hoạt động với nhiều kiểu mà vẫn được kiểm tra ở thời điểm biên dịch:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`Box<String>` và `Box<Integer>` đều hợp lệ. Nhưng nếu muốn viết `value.doubleValue()` trong `Box<T>`, trình biên dịch không chấp nhận: `T` có thể là bất cứ kiểu tham chiếu nào, chưa chắc có phương thức `doubleValue()`.

**Bounded type parameter** giới hạn các kiểu hợp lệ và cho phép code generic sử dụng những thành viên được bảo đảm bởi ràng buộc:

```java
final class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() {
        return value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}

NumberBox<Integer> a = new NumberBox<>(42);
NumberBox<java.math.BigDecimal> b =
        new NumberBox<>(new java.math.BigDecimal("12.50"));

// Lỗi biên dịch: String không phải subtype của Number.
// NumberBox<String> wrong = new NumberBox<>("42");
```

Dấu `extends` ở đây mang nghĩa **phải tương thích với upper bound**. Nó dùng được khi ràng buộc là **class** hoặc **interface**, kể cả khi quan hệ giữa các interface về mặt Java được gọi là `implements`.

Ví dụ `<T extends Number>` nhận `Integer`, `Long`, `Double`, `BigDecimal` và các subtype `Number` khác. Nó không cho phép `String`.

**Lưu ý:** `T extends Number` không hứa mọi toán tử số học đều dùng được với `T`. Java không cho viết `a + b` khi `a`, `b` có kiểu `T`; bạn chỉ gọi được các phương thức bảo đảm bởi `Number` (như `doubleValue()`) hoặc dịch vụ số học được truyền vào. Việc chuyển sang `double` có thể mất độ chính xác, đặc biệt với tiền tệ.

## 2. Cú pháp và vị trí khai báo

| Mục đích | Cú pháp Java | Điều được bảo đảm |
| --- | --- | --- |
| Class generic không ràng buộc | `class Box<T>` | `T` mặc định có upper bound `Object` |
| Class generic có upper bound | `class NumberBox<T extends Number>` | `T` là subtype của `Number` |
| Ràng buộc bằng interface | `<T extends Comparable<T>>` | Có `compareTo(T)` thông qua interface |
| Phương thức generic | `static <T extends Number> double value(T x)` | Bound chỉ thuộc type parameter của phương thức |
| Nhiều ràng buộc | `<T extends Number & Comparable<T>>` | Phải tương thích cả hai ràng buộc |
| Wildcard upper bound | `List<? extends Number>` | Danh sách có phần tử thuộc subtype nào đó của `Number` |
| Wildcard lower bound | `List<? super Integer>` | Danh sách có kiểu phần tử `Integer` hoặc supertype của nó |

Với phương thức, **khai báo tham số kiểu nằm trước kiểu trả về**:

```java
static <T extends Number> double twiceAsDouble(T value) {
    return value.doubleValue() * 2;
}
```

Trong đoạn trên, `T` là kiểu generic **của phương thức**, không đòi hỏi lớp chứa phương thức cũng phải là generic.

Với class generic, có thể sử dụng `T` ở trường, constructor, tham số, kiểu trả về và phương thức instance:

```java
final class Pair<T extends CharSequence> {
    private final T first;
    private final T second;

    Pair(T first, T second) {
        this.first = first;
        this.second = second;
    }

    int totalLength() {
        return first.length() + second.length();
    }

    T first() {
        return first;
    }
}
```

`String`, `StringBuilder` đều triển khai `CharSequence`, nhưng **StringBuilder có thể thay đổi** nên một `Pair<StringBuilder>` không tự động bất biến chỉ vì các field là `final`.

## 3. Nhiều ràng buộc: intersection types

Một thuật toán đôi khi cần **nhiều khả năng cùng lúc**. Ví dụ muốn một giá trị vừa là số (`Number`) vừa so sánh được (`Comparable`):

```java
static <T extends Number & Comparable<? super T>>
T greater(T first, T second) {
    java.util.Objects.requireNonNull(first);
    java.util.Objects.requireNonNull(second);
    return first.compareTo(second) >= 0 ? first : second;
}
```

Ở đây:

- `Number` là upper bound ở dạng class, chứng minh `T` có API của `Number`.
- `Comparable<? super T>` yêu cầu `T` hỗ trợ phép so sánh với `T` hoặc một supertype phù hợp.
- Dấu **`&`** diễn đạt **đồng thời thỏa nhiều bound**, không phải chọn một trong các bound.
- Khi có class bound và interface bound, **class phải đứng đầu**; các phần sau là interface. Java không cho đưa hai class độc lập vào chuỗi bounds.

Hợp lệ:

```java
<T extends Number & Comparable<T>>
<T extends java.io.Serializable & Comparable<T>>
<T extends Number & java.io.Serializable & Comparable<T>>
```

Không hợp lệ:

```java
// Class Number phải đứng trước các interface.
// <T extends Comparable<T> & Number>

// Không được có hai class bound.
// <T extends Number & java.util.ArrayList<String>>

// Không dùng dấu phẩy để mô tả nhiều bound của một T.
// <T extends Number, Comparable<T>>
```

Dấu phẩy trong `<T, U>` dùng để **khai báo các tham số kiểu khác nhau**, chẳng hạn `<T extends Number, U extends CharSequence>`. Nếu nhiều ràng buộc thuộc **cùng một T**, dùng `&`.

### Vì sao nên dùng `Comparable<? super T>`?

Viết `<T extends Comparable<T>>` là đúng cho các kiểu như `String` hoặc `Integer`, nhưng có thể hạn chế subtype.

Giả sử `Person implements Comparable<Person>` và `Employee extends Person`. Một `Employee` kế thừa khả năng so sánh của `Person`, **không nhất thiết triển khai `Comparable<Employee>`**. Vì vậy:

```java
<T extends Comparable<? super T>>
```

linh hoạt hơn:

- `Employee` có thể so sánh với một `Person`.
- `Person` là supertype của `Employee`.
- `Comparable<Person>` phù hợp với `Comparable<? super Employee>`.

Đây là cách khai báo rất hữu ích cho hàm tìm phần tử lớn nhất hoặc sắp xếp theo **natural ordering**.

## 4. Ví dụ Java 17 chạy độc lập

Tạo file **BoundedGenericsDemo.java**. Ví dụ có ba tác vụ: tìm phần tử lớn nhất với `Comparable`, giữ một khoảng giá trị số hợp lệ và xử lý enum với ràng buộc đệ quy. Cả ba dùng cùng ý tưởng: chỉ cho phép những kiểu có các khả năng thuật toán cần.

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class BoundedGenericsDemo {

    // Comparable<? super T> chấp nhận cả kiểu so sánh với supertype.
    public static <T extends Comparable<? super T>>
    T max(List<? extends T> values) {
        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            throw new IllegalArgumentException(
                    "Danh sách không được rỗng");
        }

        T best = Objects.requireNonNull(values.get(0), "element");
        for (T item : values) {
            Objects.requireNonNull(item, "element");
            if (item.compareTo(best) > 0) {
                best = item;
            }
        }
        return best;
    }

    // T phải là Number VÀ có khả năng so sánh tự nhiên.
    public record NumericRange<T extends Number & Comparable<? super T>>(
            T lower, T upper) {

        public NumericRange {
            Objects.requireNonNull(lower, "lower");
            Objects.requireNonNull(upper, "upper");
            if (lower.compareTo(upper) > 0) {
                throw new IllegalArgumentException(
                        "Giới hạn dưới lớn hơn giới hạn trên");
            }
        }

        public boolean contains(T value) {
            Objects.requireNonNull(value, "value");
            return lower.compareTo(value) <= 0
                    && upper.compareTo(value) >= 0;
        }
    }

    // Lớp cha so sánh theo level.
    public static class Person implements Comparable<Person> {
        private final int level;

        public Person(int level) {
            this.level = level;
        }

        public int level() {
            return level;
        }

        @Override
        public int compareTo(Person other) {
            Objects.requireNonNull(other, "other");
            return Integer.compare(this.level, other.level);
        }
    }

    // Employee thừa hưởng Comparable<Person>, không khai báo
    // Comparable<Employee>.
    public static final class Employee extends Person {
        public Employee(int level) {
            super(level);
        }
    }

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    // Bound đệ quy như cấu trúc Enum<E extends Enum<E>> trong JDK.
    public static <E extends Enum<E>> E parseEnum(
            Class<E> enumClass, String constantName) {
        Objects.requireNonNull(enumClass, "enumClass");
        Objects.requireNonNull(constantName, "constantName");
        return Enum.valueOf(enumClass, constantName);
    }

    public static void main(String[] args) {
        System.out.println("Max score: " + max(List.of(10, 25, 14)));

        System.out.println("Max date: " + max(List.of(
                LocalDate.of(2026, 1, 10),
                LocalDate.of(2026, 8, 20)
        )));

        Employee senior = max(List.of(
                new Employee(3),
                new Employee(9)
        ));
        System.out.println("Max employee level: " + senior.level());

        NumericRange<BigDecimal> range = new NumericRange<>(
                new BigDecimal("1.00"),
                new BigDecimal("2.00")
        );
        System.out.println("In range: " +
                range.contains(new BigDecimal("1.25")));

        System.out.println("Priority: " +
                parseEnum(Priority.class, "HIGH"));
    }
}
```

Chạy:

```bash
javac BoundedGenericsDemo.java
java BoundedGenericsDemo
```

Kết quả:

```text
Max score: 25
Max date: 2026-08-20
Max employee level: 9
In range: true
Priority: HIGH
```

**Đọc kết quả theo từng bound:**

1. `max(List.of(10, 25, 14))`: `Integer` cung cấp `Comparable<Integer>`, đáp ứng upper bound.
2. `max(List<LocalDate>)`: `LocalDate` có natural ordering thông qua `ChronoLocalDate`, một superinterface phù hợp với `Comparable<? super LocalDate>`.
3. `max(List<Employee>)`: lớp con so sánh được qua `Comparable<Person>`; ràng buộc `<? super T>` giúp loại trường hợp hợp lệ này không bị loại bỏ.
4. `NumericRange<BigDecimal>`: `BigDecimal` vừa mở rộng `Number` vừa triển khai `Comparable<BigDecimal>`, nên thỏa intersection bound.
5. `parseEnum(Priority.class, "HIGH")`: `Priority` là enum và tương thích ràng buộc `<E extends Enum<E>>`.

`BigDecimal.compareTo` so sánh **giá trị số**, khác `equals` có xét scale (ví dụ `1.0` và `1.00`). Để xét thuộc khoảng số, `compareTo` là lựa chọn phù hợp với quy tắc giá trị được giả định; với miền khác cần định nghĩa comparator và logic biên theo nghiệp vụ.

Ví dụ cố ý không trộn `Double` và `BigDecimal` vào cùng một `NumericRange<T>`: thuật toán so sánh dùng một hợp đồng so sánh chung của **một T**, thay vì tự chuyển đổi và so sánh lẫn các biểu diễn có ngữ nghĩa hoặc độ chính xác khác nhau.

## 5. Bound giúp trình biên dịch kiểm tra được gì?

Xét phương thức:

```java
static <T extends CharSequence> int countChars(T text) {
    return text.length();
}
```

Hợp lệ:

```java
countChars("Java");                  // String implements CharSequence
countChars(new StringBuilder("OOP")); // StringBuilder cũng vậy
```

Không hợp lệ:

```java
// Integer không triển khai CharSequence.
// countChars(123);
```

Khi gọi một phương thức generic, Java suy luận `T` từ đối số, kiểu đích trong một số ngữ cảnh và ràng buộc. Nếu không có cách suy luận một `T` thỏa tất cả điều kiện, chương trình bị từ chối khi biên dịch.

**Điều upper bound không làm được:**

- Không chặn truyền `null` ở thời điểm biên dịch. Ràng buộc về subtype không phải annotation non-null hoặc hệ thống null safety.
- Không xác thực quy tắc nghiệp vụ, ví dụ “số phải dương” hay “ngày bắt đầu trước ngày kết thúc”; cần điều kiện runtime.
- Không tự khiến `T` trở nên bất biến hoặc thread-safe.
- Không giúp dùng mọi toán tử nguyên thủy như `+`, `<` với biến kiểu `T`.
- Không bảo đảm một kết quả `doubleValue()` chính xác cho mọi subtype `Number`.

Nhờ bound, code bên trong có thể gọi API đã được định nghĩa bởi upper bound. Mọi ràng buộc nghiệp vụ ngoài hệ thống kiểu vẫn phải được xử lý rõ ràng.

## 6. Phân biệt bounded type parameter và bounded wildcard

Hai hình thức cùng dùng từ khóa `extends`, nhưng chúng phục vụ mục đích khác nhau:

**Tham số kiểu có tên (`T extends Number`):** đặt tên cho kiểu để dùng **lại nhất quán** trong chữ ký.

```java
static <T extends Number> T firstOf(List<T> values) {
    return values.get(0);
}
```

Kết quả có kiểu `T`: truyền `List<Integer>` thì lời gọi có thể nhận lại `Integer`. Nhờ tên `T`, ta diễn đạt mối quan hệ giữa kiểu phần tử đầu vào và kiểu trả về.

**Wildcard (`? extends Number`):** nhận một kiểu phần tử chưa biết, nhưng biết nó thỏa một upper bound.

```java
static double sumAsDouble(List<? extends Number> values) {
    double sum = 0.0;
    for (Number value : values) {
        sum += value.doubleValue();
    }
    return sum;
}
```

`sumAsDouble(List.of(1, 2, 3))` nhận `List<Integer>`, nhưng phương thức **không cần biết** kiểu phần tử chính xác để giữ lại hay trả về. Nó chỉ cần đọc các giá trị như `Number`.

**Không thể suy ra rằng `List<Integer>` là subtype của `List<Number>`**. Generics Java **invariant** đối với tham số kiểu cụ thể:

```java
List<Integer> integers = List.of(1, 2, 3);

// Lỗi biên dịch dù Integer extends Number.
// List<Number> numbers = integers;

List<? extends Number> readableNumbers = integers;
Number n = readableNumbers.get(0);
```

Với `List<? extends Number>`, ta không thể thêm một `Integer` hoặc `Double` thông thường, vì kiểu phần tử thực sự có thể là một subtype khác của `Number`. Vẫn có thể thêm `null` nếu danh sách cho phép, nhưng điều đó không đem lại giá trị cho một API chỉ đọc.

**Lower-bounded wildcard** dùng `super` để diễn đạt đích ghi chấp nhận một kiểu và các subtype của kiểu đó:

```java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
    Object first = target.get(0);
}
```

Lời gọi có thể truyền một `List<Integer>`, `List<Number>` hoặc `List<Object>` có thể sửa được. Vì kiểu phần tử cụ thể của `target` chưa rõ, khi lấy ra chỉ có thể coi an toàn là `Object` (nếu không biết thêm gì).

| Công cụ | Dùng khi | Có thể đọc an toàn là | Có thể thêm gì? |
| --- | --- | --- | --- |
| `<T extends Number>` | Cần tên kiểu `T` dùng chung trong chữ ký | `T` hoặc `Number` | Theo API của cấu trúc mang `T` |
| `List<? extends Number>` | Chủ yếu **đọc** giá trị số | `Number` | Không thêm giá trị khác `null` qua reference này |
| `List<? super Integer>` | Chủ yếu **ghi** `Integer` | `Object` | `Integer` (và subtype, nếu có) |
| `List<Number>` | Chính xác danh sách có element type `Number` | `Number` | Các subtype `Number` hợp lệ |

Gợi nhớ **PECS — Producer Extends, Consumer Super**: nơi **sản sinh/cấp giá trị** cho ta đọc thường dùng `extends`; nơi **tiêu thụ/nhận giá trị** để ghi thường dùng `super`. Đây là quy tắc chọn API, không phải một quy tắc áp dụng máy móc cho mọi phương thức.

### `super` không dùng để ràng buộc tham số kiểu có tên

Không hợp lệ:

```java
// Java không cho khai báo lower bound trực tiếp cho T.
// class Box<T super Integer> {}
```

Hợp lệ:

```java
static void putInteger(List<? super Integer> output) {
    output.add(100);
}
```

Một điểm dễ nhầm: `Comparable<? super T>` **vẫn nằm trong một upper bound của `T`**, nhưng bản thân đối số kiểu của `Comparable` là lower-bounded wildcard. Chúng là hai cấp cú pháp khác nhau.

## 7. Thiết kế API: lúc nào nên dùng T, lúc nào nên dùng wildcard?

Giả sử đọc một danh sách số:

```java
static double average(List<? extends Number> numbers) {
    if (numbers.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    double total = 0;
    for (Number number : numbers) {
        total += number.doubleValue();
    }
    return total / numbers.size();
}
```

Ở đây **không cần T** vì phương thức không tạo mối quan hệ kiểu giữa các giá trị được đọc và kết quả. Wildcard làm hợp đồng gọn hơn.

Ngược lại, khi kết quả cần **cùng kiểu cụ thể** với phần tử của collection:

```java
static <T extends Comparable<? super T>> T chooseMax(
        List<? extends T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

Tên `T` diễn đạt giá trị trả về có quan hệ chặt chẽ với element type của danh sách. Trong một API công khai, hãy ưu tiên wildcard khi nó tăng tính linh hoạt mà không làm mất mối quan hệ kiểu cần thiết.

**Tránh overengineering:** không thêm generic type parameter chỉ để thay một `Number` bằng ký hiệu `T`, khi nó không cung cấp thông tin kiểu hữu ích nào cho client.

## 8. Ràng buộc đệ quy (recursive hoặc F-bounded types)

Một bound có thể nhắc tới chính type parameter đang được khai báo:

```java
interface SelfComparable<T extends SelfComparable<T>>
        extends Comparable<T> {
}
```

Ý tưởng là các implementation tự biểu diễn khả năng thao tác với kiểu phù hợp của chính chúng. Đây được gọi là **F-bounded polymorphism**. Cách này xuất hiện trong những API muốn giữ quan hệ kiểu qua inheritance hoặc builder nhiều cấp.

Ví dụ quen thuộc của JDK:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Phần triển khai thật của JDK có thêm chi tiết nội bộ.
}
```

Khi khai báo:

```java
enum Status { NEW, DONE }
```

`Status` là một kiểu enum tương thích với bound `<E extends Enum<E>>`. Vì vậy helper sau có thể nhận đúng loại enum:

```java
static <E extends Enum<E>> E parseEnum(
        Class<E> enumType, String name) {
    return Enum.valueOf(enumType, name);
}
```

`parseEnum(Status.class, "DONE")` trả giá trị kiểu `Status`, không cần ép kiểu thủ công. Chuỗi sai tên hằng khiến `Enum.valueOf` ném `IllegalArgumentException`; đó là lỗi runtime về dữ liệu đầu vào, không phải lỗi suy luận kiểu.

**Không tự áp F-bounds cho mọi interface**. Chúng có thể tạo ra chữ ký khó đọc, đặc biệt nếu dùng nhiều cấp kế thừa, wildcard và recursive generics. Chỉ sử dụng khi mối liên hệ “kiểu này dùng chính kiểu cụ thể của nó” mang lại lợi ích rõ ràng.

## 9. Type erasure và những giới hạn cần biết

Generics Java chủ yếu được kiểm tra ở **compile time**. Trong mã thực thi, nhiều thông tin tham số kiểu bị **erase** thành bound tương ứng; trình biên dịch có thể chèn phép ép kiểu và sinh **bridge method** để giữ tính đa hình khi cần.

Ví dụ:

```java
final class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Về mặt ý tưởng sau erasure, `T` có upper bound đầu tiên là `Number`, nên field/method tương ứng dùng `Number` ở mức bytecode. Đây là **mô hình giải thích**, không phải mã Java do compiler xuất chính xác từng dòng.

Với nhiều bounds:

```java
class Store<T extends Number & Comparable<T>> {
    T value;
}
```

**Erasure của T là bound bên trái**, tức `Number`. Vì thứ tự bounds có ý nghĩa đối với erasure, Java yêu cầu class bound đứng trước những interface còn lại. Bất cứ method nào trên các bound khác đều được trình biên dịch xử lý để giữ hợp đồng kiểu ở compile time.

### Những việc không thể làm trực tiếp với T

```java
class Example<T extends Number> {
    // Không thể tạo mới đối tượng chỉ từ một type variable:
    // T value = new T();

    // Không thể tạo generic array:
    // T[] values = new T[10];

    // Không thể kiểm tra kiểu thực tế của T theo cách này:
    // boolean exact = obj instanceof T;

    // Không thể dùng type parameter của class trong static field:
    // static T shared;
}
```

Giải pháp tùy mục đích:

- Muốn tạo instance của `T`: truyền `Supplier<T>`, factory hoặc `Class<T>` cùng cơ chế tạo được kiểm soát.
- Muốn chứa nhiều `T`: ưu tiên `List<T>` thay vì generic array nếu hợp lý.
- Muốn kiểm tra kiểu lúc chạy: truyền `Class<T>` và dùng `Class.isInstance/cast`, nhưng không giả định `Class<List<String>>` sẽ giữ được `String` của danh sách tại runtime.
- Muốn giữ logic dùng `T` trong context static: dùng **static generic method** với type parameter riêng.

```java
static <T extends Number> T requireNumber(T value) {
    return java.util.Objects.requireNonNull(value);
}
```

Hai kiểu tham số hóa cùng **raw class** thường không phân biệt bằng `instanceof`:

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size());
}

// Không hợp lệ:
// if (value instanceof java.util.List<String> strings) { ... }
```

Erasure cũng khiến hai phương thức chỉ khác nhau ở tham số kiểu của cùng một raw collection có thể đụng chữ ký:

```java
// Không thể cùng khai báo trong một class:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
// Sau erasure cả hai đều nhận List.
```

**Quan trọng:** type erasure không có nghĩa generics “vô dụng ở runtime”. Việc kiểm tra tại compile time là điểm mạnh chính; một số thông tin generic declaration vẫn có thể quan sát qua reflection trên những chữ ký nhất định. Nhưng JVM không gắn nhãn `List<String>` riêng cho mỗi instance `ArrayList`.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai / khó bảo trì | Cách tiếp cận |
| --- | --- | --- |
| `<T extends Number>` rồi viết `a + b` | Toán tử số học không định nghĩa trên type variable tham chiếu | Dùng `Number` API có ý thức độ chính xác hoặc truyền chiến lược cộng |
| Dùng `<T extends Comparable<T>>` khắp nơi | Có thể loại subtype chỉ comparable theo supertype | Cân nhắc `Comparable<? super T>` |
| Thử `<T super Number>` | Java không hỗ trợ lower bound trực tiếp cho type parameter | Dùng `? super ...` ở vị trí wildcard |
| `List<Number> x = new ArrayList<Integer>()` | Generic parameter invariant | Dùng `List<? extends Number>` nếu chủ yếu đọc |
| Ghi giá trị cụ thể vào `List<? extends Number>` | Element type thực tế chưa biết | Dùng `List<? super Integer>` nếu cần ghi Integer |
| Đặt interface trước class trong intersection bound | Class bound nếu có phải đứng đầu | `<T extends Number & Comparable<T>>` |
| Giả định upper bound loại trừ null | `null` vẫn có thể đi qua reference generic | `Objects.requireNonNull` và validation |
| Dùng `doubleValue()` để xử lý tiền chính xác | Có thể mất precision và scale | Dùng `BigDecimal` với policy làm tròn rõ |
| Dùng raw type `Comparable` để “dễ hơn” | Mất type safety, có thể dẫn tới lỗi ép kiểu khi chạy | Dùng tham số hóa `Comparable<T>` hoặc `Comparable<? super T>` |
| Tạo generic API quá phức tạp chỉ có một kiểu sử dụng | Chi phí hiểu/duy trì lớn hơn khả năng tái sử dụng | Dùng kiểu cụ thể hoặc abstraction nhỏ phù hợp |

### Có thể ràng buộc T với primitive không?

Không: Java generics chỉ nhận **reference type** làm type argument. Các kiểu `int`, `double` không thể dùng thành `List<int>` hoặc `Box<int>`. Dùng wrapper `Integer`, `Double` (autoboxing) hoặc các kiểu chuyên biệt cho primitive như `IntStream`, `int[]` khi hiệu năng/bộ nhớ là yếu tố quan trọng.

### Bound nhiều interface có phải implements tất cả ở lớp đích không?

Một kiểu có thể đáp ứng ràng buộc qua **thừa kế** và **các interface được triển khai gián tiếp**, không bắt buộc viết trực tiếp tất cả tên interface trong câu lệnh `implements`. Java kiểm tra quan hệ kiểu thực tế theo hệ thống phân cấp.

### Upper bound là giao diện hay điều kiện giá trị?

Bound là **ràng buộc kiểu**, không phải điều kiện trên **giá trị**. `T extends Number` không diễn đạt `T > 0`. Muốn số dương, phải kiểm tra giá trị runtime. `T extends Comparable<T>` cũng không tự chứng minh phép `compareTo` là đúng, bắc cầu hoặc nhất quán với `equals`; implementation phải tuân thủ hợp đồng `Comparable`.

## 11. Bài tập: kho dữ liệu có giá trị đo

Xây dựng một mô hình lưu phép đo cảm biến. Mỗi phép đo có **mã cảm biến**, **giá trị** và **thời gian ghi nhận**.

1. Viết `Measurement<T extends Number & Comparable<? super T>>` bằng `record`; không chấp nhận cảm biến rỗng hoặc giá trị null.
2. Viết `maxMeasurement(List<Measurement<T>>)` trả về phép đo có giá trị lớn nhất, với type parameter được bound thích hợp. Danh sách rỗng phải báo lỗi rõ.
3. Tạo ví dụ với `Integer` và `BigDecimal`. Giải thích vì sao hai kiểu phải được so sánh trong một hợp đồng nhất quán thay vì tự động trộn mọi `Number`.
4. Viết phương thức chỉ **đọc** danh sách `List<? extends Number>` và tính tổng gần đúng bằng `double`; nêu giới hạn khi dùng với dữ liệu tài chính.
5. Viết phương thức thêm giá trị mặc định vào `List<? super Integer>`, rồi thử gọi với `List<Integer>`, `List<Number>` và `List<Object>`.
6. Viết test JUnit 5 cho null, danh sách rỗng, trường hợp hai giá trị bằng nhau, giá trị âm và subtype kế thừa `Comparable` của supertype.

**Tự kiểm tra:** biến nào thật sự phải cùng kiểu `T`? Đâu là chỗ chỉ cần wildcard? Những điều kiện nào được compiler bảo đảm, điều kiện nào cần kiểm tra lúc chạy? Tác động của `Comparable<? super T>` khi kiểu con kế thừa cách so sánh từ lớp cha là gì?

## 12. Ghi nhớ để áp dụng đúng

- `<T extends Bound>` là **upper-bounded type parameter**: giới hạn kiểu có thể dùng và những thành viên có thể gọi an toàn.
- Một `T` có thể có **nhiều bound với `&`**; nếu có class bound thì đặt nó đầu tiên.
- `Comparable<? super T>` thường phù hợp hơn `Comparable<T>` khi muốn hỗ trợ kiểu con so sánh qua supertype.
- `T` có tên khi cần **nối quan hệ kiểu** giữa tham số, trường và kết quả; wildcard phù hợp khi không cần đặt tên mối quan hệ đó.
- `? extends` hỗ trợ đọc phần tử ở upper bound, `? super` hỗ trợ ghi kiểu cụ thể theo quy tắc PECS.
- **Type erasure** giới hạn một số thao tác runtime; generic bounds giúp kiểm tra kiểu khi biên dịch chứ không thay thế xác thực dữ liệu hoặc test.
- Hãy chọn bound nhỏ nhất đáp ứng đúng thuật toán. Ràng buộc quá chặt loại bỏ những kiểu vẫn có thể xử lý hợp lệ, còn ràng buộc quá lỏng buộc code phải ép kiểu nguy hiểm.

**Kết luận:** ràng buộc tham số kiểu là cách diễn đạt **những năng lực mà thuật toán đòi hỏi** ngay trong API Java. Dùng đúng bound giúp mã tái sử dụng được, an toàn kiểu và dễ hiểu; hiểu thêm wildcard, erasure và điều kiện runtime sẽ tránh được các giới hạn thường gây nhầm lẫn khi học Generics.