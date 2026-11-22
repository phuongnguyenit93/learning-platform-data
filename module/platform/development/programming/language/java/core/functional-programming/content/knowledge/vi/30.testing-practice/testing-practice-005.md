# Tách thân lambda phức tạp thành phương thức để kiểm thử trong Java

## 1. Vì sao cần tách lambda phức tạp?

Một lambda ngắn giúp Java Stream diễn đạt trực tiếp luồng dữ liệu:

```java
List<String> activeNames = employees.stream()
        .filter(Employee::active)
        .map(Employee::name)
        .toList();
```

Đây là đoạn minh họa trong một phương thức có `employees` và record/class `Employee` phù hợp.

Nhưng không phải lambda nào cũng ngắn. Một lambda có nhiều `if/else`, kiểm tra `null`, business rule, chuyển đổi định dạng hoặc lời gọi service sẽ khiến đoạn `filter`/`map` khó hiểu, khó debug và khó kiểm thử một cách độc lập.

Ví dụ dưới đây mô tả chính sách chiết khấu:

```java
List<Integer> totals = orders.stream()
        .map(order -> {
            if (order == null) {
                throw new IllegalArgumentException("order is null");
            }
            int subtotal = order.subtotal();
            if (subtotal < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }
            int percent;
            if (order.member()) {
                percent = 20;
            } else if (subtotal >= 100) {
                percent = 10;
            } else {
                percent = 0;
            }
            return subtotal * (100 - percent) / 100;
        })
        .toList();
```

Đoạn minh họa giả định mỗi `Order` có `subtotal()` và `member()`. Nó có thể chạy đúng, nhưng test một trường hợp như subtotal bằng 100 lại phải đi qua Stream. Nội dung nghiệp vụ cũng che mất ý định chính của pipeline là “chuyển mỗi order thành số tiền cuối”.

Sau khi **extract method**:

```java
List<Integer> totals = orders.stream()
        .map(PricingRules::calculateNetAmount)
        .toList();
```

Phương thức `calculateNetAmount(Order)` mang tên ý nghĩa; có thể gọi riêng trong test để xác nhận mọi nhánh và exception. Pipeline trở nên dễ đọc vì mô tả **làm gì**, còn method mô tả **làm như thế nào**.

**Lợi ích trọng tâm là khả năng kiểm thử**: tách một đơn vị logic có input/output rõ ràng để test trực tiếp, thay vì kiểm tra quy tắc chỉ thông qua terminal operation của Stream. Không cần tách mọi lambda; việc tách phải làm code dễ hiểu hơn và logic có thể được kiểm chứng độc lập.

## 2. Khi nào một lambda đáng được tách?

Cân nhắc tách khi:

1. Có nhiều nhánh `if`, `switch` hoặc tổ hợp điều kiện khó theo dõi.
2. Chứa quy tắc nghiệp vụ có tên, như “đủ điều kiện hoàn tiền”, “giá sau giảm”.
3. Có nhiều case biên: null, rỗng, âm, đúng ngưỡng, lớn hơn ngưỡng.
4. Cần dùng lại cùng logic trong Stream, Optional, một service khác hoặc code imperative.
5. Muốn viết unit test kiểm tra từng nhánh, ngoại lệ, kết quả mà không dựng cả pipeline.
6. Có dependency bên ngoài (repository, clock, HTTP) cần bóc riêng khỏi tính toán.
7. Lambda dài khiến pipeline không còn biểu đạt cấu trúc dữ liệu.
8. Có yêu cầu debug hoặc đặt breakpoint tại quy tắc cụ thể.
9. Cần chính sách rõ ràng cho việc làm tròn, case sensitivity hoặc null.
10. Tên method mới giúp người đọc hiểu ý nghĩa mà không cần giải mã điều kiện.

Không nên tách vô điều kiện:

- `n -> n * 2` thường đủ rõ.
- `String::trim` vốn đã là tên một thao tác.
- `p -> p.active()` có thể dùng `Person::active`.
- Một helper chỉ bọc một phép toán quá tầm thường mà tên không tăng nghĩa sẽ làm tăng indirection.

Hãy xem xét **cấu trúc trách nhiệm**, không chỉ số dòng. Một lambda một dòng `x -> service.save(x)` có side effect vẫn có thể rất khó test, trong khi một biểu thức boolean dài nhưng thuần túy có thể dễ test sau khi đưa vào method tên rõ ràng.

## 3. Cách refactor từng bước mà không thay đổi behavior

Phương pháp thực tế:

1. Xác định input của lambda, kiểu kết quả và exception có thể xảy ra.
2. Liệt kê nhánh logic và các ví dụ đầu vào/đầu ra hiện tại.
3. Đặt tên phương thức theo mục đích nghiệp vụ.
4. Chuyển phần thân sang phương thức, giữ thứ tự điều kiện và quy tắc exception.
5. Thay lambda ban đầu bằng method reference hoặc lambda mỏng.
6. Viết unit tests cho method mới, gồm biên và lỗi.
7. Kiểm thử một pipeline nhỏ để xác nhận wiring `filter/map/collect`.
8. Chỉ tối ưu/đơn giản hóa logic sau khi behavior đã được xác minh.

Sơ đồ:

```text
Trước:
Stream<Order> ── map(lambda: validate + calculate) ──> Stream<Integer>

Sau:
Stream<Order> ── map(PricingRules::calculateNetAmount) ──> Stream<Integer>
                            │
                            └── unit tests trực tiếp:
                                null, -1, 0, 99, 100, member
```

**Refactor không tự cho phép đổi nghiệp vụ.** Nếu phương thức mới làm tròn ở vị trí khác, đổi thứ tự các điều kiện có side effect hoặc nuốt exception từng được ném, đó là một thay đổi hành vi, phải được review và test như một thay đổi chức năng.

## 4. Ví dụ chạy độc lập: tách quy tắc tính tiền

Tạo file `PricingRefactorDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class PricingRefactorDemo {
    record Order(String id, int subtotal, boolean member) {}

    static final class PricingRules {
        private PricingRules() {}

        static int calculateNetAmount(Order order) {
            Objects.requireNonNull(order, "order");

            int subtotal = order.subtotal();
            if (subtotal < 0) {
                throw new IllegalArgumentException("negative subtotal");
            }

            int discountPercent;
            if (order.member()) {
                discountPercent = 20;
            } else if (subtotal >= 100) {
                discountPercent = 10;
            } else {
                discountPercent = 0;
            }

            return subtotal * (100 - discountPercent) / 100;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 120, true),
                new Order("B", 80, false),
                new Order("C", 200, false),
                new Order("D", 150, true)
        );

        List<Integer> nets = orders.stream()
                .map(PricingRules::calculateNetAmount)
                .toList();

        System.out.println("nets=" + nets);
        System.out.println("A=" +
                PricingRules.calculateNetAmount(orders.get(0)));
        System.out.println("C=" +
                PricingRules.calculateNetAmount(orders.get(2)));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac PricingRefactorDemo.java
java PricingRefactorDemo
```

Output:

```text
nets=[96, 80, 180, 120]
A=96
C=180
```

Giải thích: A và D được giảm 20% vì là thành viên; B không giảm vì subtotal dưới 100 và không là thành viên; C không là thành viên nhưng đạt ngưỡng 100 nên được giảm 10%.

Pipeline chỉ có `map(PricingRules::calculateNetAmount)`. Hàm `calculateNetAmount` tự chịu trách nhiệm validate và tính toán. Nó nhận một `Order`, trả một số nguyên, có thể được kiểm tra bằng câu lệnh gọi bình thường mà không cần tạo Stream.

**Giới hạn của ví dụ**: đây là toán học trên số nguyên nhỏ để minh họa refactor; với số tiền thực cần thiết kế đơn vị tiền, xử lý tràn số, phép chia có làm tròn và có thể sử dụng `BigDecimal` theo chính sách nghiệp vụ. Không lấy công thức integer trên làm giải pháp tiền tệ tổng quát.

## 5. Kiểm thử method trực tiếp: branch, boundary, exception

Bảng ca test cơ bản:

| Input | Nhánh được kiểm tra | Expected |
| --- | --- | --- |
| (120, member=true) | Nhánh thành viên 20% | 96 |
| (80, member=false) | Không giảm | 80 |
| (100, member=false) | Đúng ngưỡng 10% | 90 |
| (99, member=false) | Ngay dưới ngưỡng | 99 |
| (0, member=true) | Số tiền bằng 0 | 0 |
| (-1, member=false) | Giá trị không hợp lệ | `IllegalArgumentException` |
| null Order | Thiếu đầu vào | `NullPointerException` |

Test 99 và 100 quan trọng vì đó là **ranh giới điều kiện**. Chỉ kiểm tra 200 chưa chứng minh toán tử `>=` được sử dụng đúng thay vì `>`.

Tạo file `PricingRulesTestDemo.java` — chạy độc lập mà không cần JUnit:

```java
import java.util.Objects;

public class PricingRulesTestDemo {
    record Order(int subtotal, boolean member) {}

    static int calculateNetAmount(Order order) {
        Objects.requireNonNull(order, "order");
        if (order.subtotal() < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        int rate = order.member()
                ? 20
                : (order.subtotal() >= 100 ? 10 : 0);

        return order.subtotal() * (100 - rate) / 100;
    }

    static void check(String title, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(title +
                    ": expected " + expected + ", got " + actual);
        }
        System.out.println("PASS " + title);
    }

    static void expectException(String title,
            Class<? extends Throwable> expected,
            Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(title + ": no exception");
        } catch (Throwable error) {
            if (!expected.isInstance(error)) {
                throw new AssertionError(
                        title + ": unexpected exception", error);
            }
            System.out.println("PASS " + title);
        }
    }

    public static void main(String[] args) {
        check("member", 96,
                calculateNetAmount(new Order(120, true)));
        check("regular", 80,
                calculateNetAmount(new Order(80, false)));
        check("threshold", 90,
                calculateNetAmount(new Order(100, false)));
        check("below threshold", 99,
                calculateNetAmount(new Order(99, false)));
        check("zero", 0,
                calculateNetAmount(new Order(0, true)));

        expectException("negative",
                IllegalArgumentException.class,
                () -> calculateNetAmount(new Order(-1, false)));
        expectException("null",
                NullPointerException.class,
                () -> calculateNetAmount(null));
    }
}
```

Biên dịch/chạy:

```bash
javac PricingRulesTestDemo.java
java PricingRulesTestDemo
```

Stdout:

```text
PASS member
PASS regular
PASS threshold
PASS below threshold
PASS zero
PASS negative
PASS null
```

Đây là bài demo tự chạy: để các file ví dụ độc lập, nó định nghĩa một phiên bản hàm trong file test. Trong **dự án thật**, phải test **chính class production `PricingRules`**, không sao chép công thức qua test. Nếu sao chép, code production và test có thể cùng chứa một lỗi nên kiểm tra vô nghĩa. Nên đặt class production ở package có API test được và sử dụng nó từ test class.

## 6. Tách Predicate dài trong `Stream.filter`

Lambda trong `filter` có kiểu `Predicate<T>`: mỗi lần gọi `test(T)` trả boolean.

Ví dụ một điều kiện:

```java
orders.stream()
        .filter(o -> o != null
                && o.approved()
                && o.quantity() > 0
                && o.unitPrice() > 0
                && (long) o.quantity() * o.unitPrice() >= 100)
        .toList();
```

Đây là đoạn minh họa trong phương thức với record Order có các accessor phù hợp. Đọc đoạn này, người khác phải tự suy luận “điều kiện đủ điều kiện”. Tách thành:

```java
static boolean isEligible(Order order) {
    if (order == null || !order.approved()) {
        return false;
    }
    if (order.quantity() <= 0 || order.unitPrice() <= 0) {
        return false;
    }
    return (long) order.quantity() * order.unitPrice() >= 100;
}
```

Sau đó gọi `filter(OrderRules::isEligible)` khi phương thức nằm trong class `OrderRules`.

Phần cast sang `long` trước phép nhân tránh tràn số `int` trong phép nhân hai giá trị `int` dương thông thường; tuy nhiên nếu dữ liệu có giá trị cực lớn hoặc cần tổng tiền lớn, vẫn cần kiểm soát miền giá trị rõ ràng.

### Chương trình kiểm tra Predicate độc lập

Lưu `PredicateExtractionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class PredicateExtractionDemo {
    record Order(String code, int quantity,
                 int unitPrice, boolean approved) {}

    static boolean isEligible(Order order) {
        if (order == null || !order.approved()) {
            return false;
        }
        if (order.quantity() <= 0 || order.unitPrice() <= 0) {
            return false;
        }
        return (long) order.quantity() * order.unitPrice() >= 100;
    }

    static void check(String name, boolean expected, boolean actual) {
        if (expected != actual) {
            throw new AssertionError(name);
        }
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        List<Order> orders = new ArrayList<>();
        orders.add(new Order("A", 2, 60, true));
        orders.add(new Order("B", 1, 80, true));
        orders.add(new Order("C", 1, 200, false));
        orders.add(new Order("D", 5, 20, true));
        orders.add(null);

        check("approved enough",
                true, isEligible(orders.get(0)));
        check("below threshold",
                false, isEligible(orders.get(1)));
        check("not approved",
                false, isEligible(orders.get(2)));
        check("boundary",
                true, isEligible(orders.get(3)));
        check("null",
                false, isEligible(null));

        List<String> accepted = orders.stream()
                .filter(PredicateExtractionDemo::isEligible)
                .map(Order::code)
                .toList();

        System.out.println("accepted=" + accepted);
    }
}
```

Chạy:

```bash
javac PredicateExtractionDemo.java
java PredicateExtractionDemo
```

Kết quả:

```text
PASS approved enough
PASS below threshold
PASS not approved
PASS boundary
PASS null
accepted=[A, D]
```

Hàm `isEligible` được test độc lập với năm tình huống. Phần pipeline test xác minh `filter` giữ đúng A, D rồi `map(Order::code)` lấy mã. Vì nguồn có null nên ví dụ dùng `ArrayList`; `List.of(...)` không nhận phần tử null.

Với ứng dụng thật, phải quyết định rõ `null` là “không đủ điều kiện” hay “dữ liệu lỗi phải báo”. Cả hai chính sách đều có thể hợp lệ trong bối cảnh khác nhau; không tự loại null nếu nghiệp vụ cần phát hiện lỗi nhập.

## 7. Tách Function phức tạp trong `Stream.map`

`map` nhận `Function<T,R>`, nghĩa là một giá trị đầu vào T được chuyển thành R. Nếu logic chuẩn hóa chuỗi gồm null, trim, case conversion, hãy tách thành method riêng thay vì đặt nhiều câu lệnh trong lambda.

Ví dụ method:

```java
static String normalizeName(String rawName) {
    if (rawName == null) {
        return "";
    }
    String trimmed = rawName.trim();
    return trimmed.isEmpty()
            ? ""
            : trimmed.toUpperCase(Locale.ROOT);
}
```

Đoạn code trong class có import `Locale`. Khi sử dụng:

```java
List<String> normalized = names.stream()
        .map(NameRules::normalizeName)
        .toList();
```

Đây là ví dụ trong ngữ cảnh class `NameRules` và biến `names`. Mapper giờ mang tên giải thích, có thể test với null, blank, mixed-case, leading/trailing spaces. `Locale.ROOT` giúp phép chuyển hoa không phụ thuộc locale của máy, nhưng `trim()` không giải quyết mọi kiểu Unicode whitespace. Quy tắc normalize thực tế phải ghi rõ.

### Demo chạy độc lập cho method normalize

Tạo `NormalizeNameTestDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NormalizeNameTestDemo {
    static String normalizeName(String rawName) {
        if (rawName == null) {
            return "";
        }
        String trimmed = rawName.trim();
        return trimmed.isEmpty()
                ? ""
                : trimmed.toUpperCase(Locale.ROOT);
    }

    static void check(String title, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(title + ": " + actual);
        }
        System.out.println("PASS " + title);
    }

    public static void main(String[] args) {
        check("null", "", normalizeName(null));
        check("blank", "", normalizeName("   "));
        check("trim", "LAN", normalizeName(" lan "));
        check("already uppercase", "AN", normalizeName("AN"));

        List<String> inputs = new ArrayList<>();
        inputs.add("  minh ");
        inputs.add(null);
        inputs.add(" an ");
        inputs.add("   ");

        List<String> result = inputs.stream()
                .map(NormalizeNameTestDemo::normalizeName)
                .toList();

        System.out.println("mapped=" + result);
    }
}
```

Chạy:

```bash
javac NormalizeNameTestDemo.java
java NormalizeNameTestDemo
```

Output:

```text
PASS null
PASS blank
PASS trim
PASS already uppercase
mapped=[MINH, , AN, ]
```

`map` không tự loại chuỗi rỗng; hai phần tử được normalize thành `""` vẫn nằm trong kết quả. Nếu bài toán yêu cầu chỉ giữ tên có nội dung, hãy chọn thêm điều kiện `filter(s -> !s.isEmpty())` sau khi normalize, hoặc thay policy. Đừng cho rằng phương thức “normalize” có nghĩa tự lọc dữ liệu.

## 8. Method reference là cú pháp giúp pipeline mạch lạc

Các dạng thường gặp:

| Lambda | Method reference | Ý nghĩa |
| --- | --- | --- |
| `x -> Rules.isValid(x)` | `Rules::isValid` | Static method |
| `x -> x.name()` | `Person::name` | Method gọi trên chính đầu vào |
| `x -> service.normalize(x)` | `service::normalize` | Bound instance method |
| `() -> Factory.empty()` | `Factory::empty` | Supplier static |
| `x -> new Result(x)` | `Result::new` | Constructor |
| `(a, b) -> a.compareTo(b)` | `String::compareTo` | Unbound instance method hai tham số |

Method reference không khiến lambda chạy sớm. Ví dụ `map(Rules::transform)` vẫn là intermediate operation, chưa chạy body của `transform` chỉ vì pipeline được dựng.

Không phải lúc nào cũng đổi được sang method reference: nếu phương thức có thêm tham số ngưỡng, pipeline có thể giữ một lambda ngắn:

```java
int minPoints = 100;
customers.stream()
        .filter(c -> CustomerRules.isEligible(c, minPoints))
        .toList();
```

Đoạn minh họa với biến và class thích hợp. `minPoints` cần là final hoặc effectively final. Không cố viết `filter(CustomerRules::isEligible)` nếu method cần hai tham số mà `Predicate<Customer>` chỉ cung cấp một tham số.

Có thể tạo factory:

```java
static Predicate<Customer> atLeast(int threshold) {
    return c -> c != null && c.points() >= threshold;
}
```

và `stream.filter(atLeast(100))` nếu cần tái sử dụng cấu hình. Đây là dạng phương thức trong class có `Customer.points()` và import `Predicate`.

## 9. Các functional interface định hình phương thức mới

| API sử dụng | Hợp đồng callback | Chữ ký method có thể tách |
| --- | --- | --- |
| `Stream.filter` | `Predicate<T>` | `boolean isEligible(T value)` |
| `Stream.map` | `Function<T,R>` | `R toResult(T value)` |
| `Stream.flatMap` | `Function<T,Stream<R>>` | `Stream<R> expand(T value)` |
| `Stream.forEach` | `Consumer<T>` | `void handle(T value)` |
| `Optional.map` | `Function<T,R>` | `R transform(T value)` |
| `Stream.reduce` | `BinaryOperator<T>` | `T combine(T a,T b)` |
| `IntStream.filter` | `IntPredicate` | `boolean test(int value)` |
| `IntStream.map` | `IntUnaryOperator` | `int transform(int value)` |
| `Comparator.comparing` | `Function<T,U>` | `U extractKey(T value)` |

Tách method phải giữ đúng **kiểu tham số, kiểu trả về, nullability và checked exception**. Chẳng hạn `Predicate<T>` trả `boolean`, không trả `Optional<T>`. `Function<T,R>` nhận một phần tử và trả kết quả chuyển đổi, không có chức năng phát nhiều phần tử: nếu cần một đầu vào thành nhiều đầu ra, thường cần `flatMap` với method trả `Stream<R>`.

Không dùng raw type `Function` hay `Predicate` chỉ để compiler chấp nhận; khai báo generic rõ giúp test chính xác và IDE refactor an toàn hơn.

## 10. Unit test trực tiếp khác pipeline test như thế nào?

**Unit test** hàm quy tắc trả lời: “Với một đầu vào cụ thể, rule có trả đúng kết quả hoặc lỗi mong đợi không?”

**Pipeline test** trả lời: “Rule được lắp vào đúng stage, đúng thứ tự và đúng kiểu không?”

Ví dụ muốn lọc những tên đã chuẩn hóa có độ dài ít nhất ba ký tự:

```java
List<String> selected = names.stream()
        .map(NameRules::normalizeName)
        .filter(s -> s.length() >= 3)
        .toList();
```

Pipeline test cần kiểm tra cả thứ tự `map` trước `filter`; nếu viết `filter(s -> s.length() >= 3)` trước `map`, null có thể gây `NullPointerException` và độ dài có thể được tính trên chuỗi chưa trim. Method `normalizeName` đúng riêng lẻ **không bảo đảm pipeline được nối đúng**.

Một chiến lược tốt:

1. Kiểm thử kỹ logic rule ở mức phương thức: từng nhánh, null, biên, exception.
2. Chỉ dùng vài dữ liệu đại diện ở mức pipeline để kiểm tra stage order và cấu trúc kết quả.
3. Nếu có I/O ngoài, bổ sung integration tests phù hợp; không nhồi toàn bộ kiểm thử dependency vào unit test của hàm tính toán.

Điều này làm test nhanh, rõ lý do thất bại và tránh lặp lại cùng nhiều trường hợp ở mọi lớp.

## 11. Pure function và khả năng test ổn định

Một **pure function** không làm thay đổi trạng thái bên ngoài và cho cùng kết quả với cùng input (trong các điều kiện xác định). Các rule thuần túy dễ test:

- Không cần database, network hay thời gian hệ thống.
- Không phụ thuộc vào biến toàn cục có thể thay đổi giữa các test.
- Không cần mock cho phép tính, validation hoặc format đơn giản.
- Có thể gọi nhiều lần và so sánh output.
- Thường an toàn hơn khi sử dụng trong parallel stream, miễn đối tượng được xử lý cũng không bị sửa đồng thời.

Ví dụ:

```java
static boolean isAdult(int age) {
    return age >= 18;
}
```

hoặc:

```java
static int pointsAfterBonus(int points, int bonus) {
    return Math.addExact(points, bonus);
}
```

Đây là những đoạn code trong class, không có I/O. `Math.addExact` ném `ArithmeticException` nếu phép cộng tràn int — một behavior có thể kiểm thử.

Trái lại, một phương thức `calculatePrice(order)` tự đọc tỷ giá từ web, đọc đồng hồ và cập nhật database không còn là tính toán thuần túy. Chỉ chuyển nó ra khỏi lambda chưa làm test đơn giản. Hãy tách lấy dữ liệu (effect) khỏi phần tính toán thuần túy và truyền dependency/cấu hình cần thiết qua tham số hoặc constructor.

## 12. Tách side effect để tránh lỗi ngầm trong Stream

Lambda của `map` và `filter` nên **stateless, non-interfering** theo quy tắc của Java Stream. Đưa side effect vào lambda có thể dẫn tới vấn đề:

```java
List<String> audit = new ArrayList<>();
List<Order> selected = orders.parallelStream()
        .filter(order -> {
            audit.add(order.id());
            return order.approved();
        })
        .toList();
```

Đây là **phản ví dụ**, giả sử có `orders`, `Order`, `ArrayList`. `audit` là mutable shared state không thread-safe; xử lý song song có thể làm race hoặc mất phần tử. Kể cả khi chuyển thân lambda sang `Rules::auditAndCheck`, side effect vẫn tồn tại và nguy cơ không biến mất.

Ngoài ra, một số pipeline dùng short-circuit như `findFirst` hoặc tối ưu như `count` có thể **không gọi mọi callback**. Không dùng log/audit trong `peek` hoặc `map` như một bảo đảm nghiệp vụ.

Nếu muốn:

- **lọc**: dùng `filter(Rules::isEligible)` với predicate thuần túy;
- **đếm**: dùng `count()`, collector hoặc bước thống kê tương ứng;
- **audit bắt buộc**: thiết kế thao tác audit riêng với contract chính xác về thứ tự, lỗi và idempotency;
- **ghi DB**: thực hiện ở boundary rõ ràng, có transaction/error handling theo yêu cầu.

Refactor tốt làm các side effect **hiện ra ở ranh giới rõ ràng**, không chỉ giấu chúng dưới một method reference.

## 13. Exception và null: giữ nguyên hợp đồng khi tách

Một thay đổi thường vô tình xảy ra khi refactor: từ `throw` thành `return null`, hoặc từ “báo lỗi ngay khi gặp dữ liệu sai” thành “im lặng loại dữ liệu”. Hai hành vi này khác nhau.

Ví dụ:

```java
static int parseQuantity(String raw) {
    Objects.requireNonNull(raw, "raw");
    int value = Integer.parseInt(raw);
    if (value < 0) {
        throw new IllegalArgumentException("negative quantity");
    }
    return value;
}
```

Đây là method trong class đã import `Objects`. Unit test nên kiểm tra:

- `"12"` → 12.
- `"0"` → 0.
- `"-1"` → `IllegalArgumentException`.
- `"abc"` → `NumberFormatException`.
- `null` → `NullPointerException`.

Nếu sử dụng trong `stream.map(Rules::parseQuantity)`, exception phát sinh khi mapper được gọi trong quá trình terminal operation tiêu thụ Stream. Việc tách method **không** làm phép parse chạy ngay khi mới dựng pipeline.

Với checked exceptions, các functional interfaces phổ biến như `Function.apply` và `Predicate.test` không khai báo checked exception. Nếu method gọi API ném `IOException`, cần thiết kế xử lý hoặc abstraction thích hợp; không thể chỉ dùng method reference để bỏ qua ràng buộc của compiler.

## 14. JUnit 5: ví dụ về test framework thực tế

Nếu dự án đã cài JUnit Jupiter, có thể dùng `@Test`, `assertEquals` và `assertThrows`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class PricingRulesTest {
    @Test
    void thresholdIsInclusive() {
        assertEquals(90,
                PricingRules.calculateNetAmount(
                        new Order("X", 100, false)));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> PricingRules.calculateNetAmount(
                        new Order("X", -1, false)));
    }
}
```

**Đây là mã minh họa dành cho dự án có JUnit 5**, có class `Order` và `PricingRules` với phạm vi truy cập phù hợp. JUnit **không có sẵn trong JDK chuẩn**, nên không thể lấy một file trên và chạy bằng `javac`/`java` với classpath trống. Những chương trình `*Demo.java` của bài này là ví dụ tự chạy bằng Java 17.

Test production code thực sự thay vì copy công thức vào class test. Nếu một method là `private`, không bắt buộc biến nó thành `public` chỉ để test: có thể test qua contract public hoặc đặt business rule thành component riêng với quyền truy cập hợp lý. Encapsulation vẫn là một yêu cầu thiết kế.

## 15. Static method, instance method hay service method?

Việc tách logic không buộc phương thức phải là static.

**Static method** phù hợp với phép tính, validation hoặc format thuần túy không phụ thuộc state.

**Instance method** phù hợp khi hành vi phụ thuộc vào cấu hình bất biến hoặc collaborator được inject:

```java
PriceService service = new PriceService(policy);

List<Result> mapped = orders.stream()
        .map(service::calculate)
        .toList();
```

Đoạn minh họa này giả định `PriceService`, `policy`, `Result` và `orders` được định nghĩa phù hợp; `service::calculate` là bound instance method reference. Để test, inject fake policy hoặc dependency có hành vi xác định.

**Domain method** phù hợp với hành vi tự nhiên của một object, ví dụ `Order::isExpired` nếu việc tính expiration thật sự thuộc về Order và các tham số cần thiết đã có.

**Service method** hợp lý khi cần phối hợp nhiều dependency, nhưng vẫn nên phân biệt code gọi service với core logic có thể kiểm thử độc lập.

Không tạo một “utils” class quá lớn chứa mọi rule không liên quan. Phương thức nên sống ở nơi có ý nghĩa với trách nhiệm của domain/module.

## 16. Method nhiều tham số: lambda mỏng vẫn là refactor tốt

Giả sử hàm kiểm tra nhận thêm ngưỡng:

```java
static boolean isEligible(Order order, int minimumAmount) {
    return order != null && order.total() >= minimumAmount;
}
```

Dùng trong `filter`:

```java
int minimumAmount = 100;
List<Order> accepted = orders.stream()
        .filter(order -> isEligible(order, minimumAmount))
        .toList();
```

Hai đoạn này là minh họa trong class có record `Order` và biến `orders` phù hợp; `minimumAmount` là effectively final.

Không thể tự đổi thành `filter(Rules::isEligible)` nếu `isEligible` cần hai tham số còn `Predicate<Order>` chỉ cung cấp một. Một lambda mỏng như trên vẫn đạt mục tiêu: business rule ở trong method có tên, pipeline chỉ truyền cấu hình.

Khi dùng nhiều lần, factory trả Predicate có thể rõ hơn:

```java
static Predicate<Order> atLeast(int threshold) {
    return order ->
            order != null && order.total() >= threshold;
}
```

Lúc đó gọi `orders.stream().filter(atLeast(100))`. Factory có thể unit test bằng `atLeast(100).test(order)`.

## 17. Kiểm thử theo cấp độ: method, pipeline, integration

Một chiến lược có thể áp dụng trong dự án:

**Cấp 1 — Method-level tests:** giá trị bình thường, ranh giới, null, dữ liệu thiếu, exception. Đây là phần nhiều nhất khi logic phức tạp.

**Cấp 2 — Pipeline-level tests:** xác nhận stage order, kiểu dữ liệu, nhóm/sắp, thứ tự kết quả, trường hợp empty hoặc trùng lặp. Không cần lặp mọi nhánh nghiệp vụ ở cấp này khi đã test riêng method.

**Cấp 3 — Integration tests:** chỉ cho dependency thật (DB, network, file, clock) khi hệ thống cần. Có thể dùng fake/mock để unit test service, nhưng một số hợp đồng tài nguyên/transaction cần kiểm tra với môi trường tích hợp.

Ví dụ một pipeline chuyển tên:

```java
List<String> result = names.stream()
        .map(NameRules::normalizeName)
        .filter(s -> !s.isEmpty())
        .toList();
```

Method test trả lời normalize có đúng. Pipeline test trả lời null có được normalize **trước** khi lọc hay không, và tên có được giữ theo encounter order hay không. Hai cấp test phục vụ hai loại lỗi khác nhau.

## 18. Không ngộ nhận về lazy evaluation khi test

Tách method không làm đổi tính lazy của Stream:

```java
Stream<Order> pipeline = orders.stream()
        .filter(Rules::isEligible)
        .map(Rules::toDto);
```

Ở dòng trên, các method reference đã được liên kết vào pipeline nhưng body `isEligible`/`toDto` thường chưa được gọi cho từng phần tử. Khi gọi terminal operation `toList()`, các stage mới được đánh giá theo nhu cầu.

Với short-circuit, một số phần tử không đến được mapper. Với `count()` trên sized source và stage không đổi số lượng, framework có thể bỏ qua một số lời gọi mapper. Vì vậy:

- **Unit test logic** bằng cách gọi method trực tiếp.
- **Pipeline test** bằng cách so sánh output có ý nghĩa.
- Không kiểm tra “method phải in log đúng n lần” như một contract chung của intermediate operations.
- Không dùng lại một Stream đã bị terminal operation tiêu thụ.
- Với parallel stream, không suy thứ tự callback từ thứ tự kết quả.

Đây cũng là lý do tách method làm test đáng tin: nó không phụ thuộc vào chiến lược tối ưu của Stream để kích hoạt một nhánh logic.

## 19. Bài tập tự thực hành

Cho record `Customer(String name, int points, boolean active)` và danh sách `customers`. Yêu cầu giữ khách hàng đang hoạt động, có điểm từ 100 trở lên và tên không null/blank.

Lambda ban đầu:

```java
List<Customer> selected = customers.stream()
        .filter(c -> c != null
                && c.active()
                && c.points() >= 100
                && c.name() != null
                && !c.name().isBlank())
        .toList();
```

Đoạn code trong phương thức có `customers` phù hợp.

Bài tập:

1. Tách thành `static boolean isEligibleCustomer(Customer c)`.
2. Dùng method reference trong `filter`.
3. Test điểm đúng 100 và ngay dưới 99.
4. Test object null, name null, name blank và active false.
5. Test một pipeline chứa ba customer, chỉ một người hợp lệ.
6. Giải thích tại sao `map(Customer::name)` nên đặt sau `filter` nếu Predicate cần các trường `active` và `points`.
7. Nếu phải đổi tên sang chữ hoa hoặc trim, tách thêm phương thức nào để test?

Lời giải minh họa trong class `CustomerRules`:

```java
static boolean isEligibleCustomer(Customer c) {
    return c != null
            && c.active()
            && c.points() >= 100
            && c.name() != null
            && !c.name().isBlank();
}
```

Sử dụng:

```java
List<String> names = customers.stream()
        .filter(CustomerRules::isEligibleCustomer)
        .map(Customer::name)
        .toList();
```

Ở đây `CustomerRules` là class chứa method, các đoạn không phải chương trình độc lập. Test đề xuất:

- `new Customer("Lan", 100, true)` → true.
- `new Customer("Lan", 99, true)` → false.
- `new Customer("Lan", 120, false)` → false.
- `new Customer(null, 120, true)` → false.
- `new Customer("   ", 120, true)` → false.
- `null` → false.

Nếu cần normalize, có thể viết `normalizeCustomerName(String name)` và gọi sau `map(Customer::name)`, với chính sách null/whitespace/locale rõ. Đừng ép validate, chuẩn hóa, ghi DB và audit vào một helper chỉ vì muốn pipeline còn một dòng.

## 20. Các lỗi thường gặp

1. **Tách chỉ để giảm số dòng lambda** nhưng tạo method tên chung chung `doIt`; nên đặt tên theo quy tắc.
2. **Giữ nguyên 100 dòng trong method mới** gồm I/O, validation, calculation và persistence; chưa thật sự giảm coupling.
3. **Chép công thức vào test** thay vì gọi code production, khiến hai bản có thể cùng lỗi.
4. **Chỉ test happy path** mà bỏ ngưỡng 99/100, input rỗng, null và exception.
5. **Thay đổi điều kiện khi refactor** nhưng không xem đó là thay đổi behavior.
6. **Giấu side effect trong method reference**; parallel stream có thể xảy ra race, short-circuit có thể bỏ qua callback.
7. **Đổi phương thức sang static dù cần state/dependency rõ ràng**; hãy chọn thiết kế phù hợp.
8. **Biến private method thành public bằng mọi giá** để gọi từ test, làm yếu encapsulation không cần thiết.
9. **Tìm method reference cho hàm hai tham số** trong `filter` một tham số; dùng lambda mỏng hoặc factory.
10. **Không giữ chính sách exception/null**; nuốt lỗi bằng `return null` có thể che giấu vấn đề.
11. **Không test lại pipeline sau khi tách**; stage order hoặc kiểu generic có thể sai.
12. **Test thứ tự log** thay vì kết quả materialize của parallel stream.
13. **Dùng lại Stream đã tiêu thụ** để chạy nhiều phép kiểm tra; tạo stream mới từ collection.
14. **Cho rằng method reference luôn nhanh hơn lambda**; mục đích chính là rõ nghĩa, hiệu năng cần đo.
15. **Tách một phép tính quá đơn giản thành nhiều lớp helper** khiến code khó điều hướng.
16. **Làm mất tham số nghiệp vụ** do chỉ truyền object đầu vào, rồi đọc giá trị từ biến toàn cục mutable.
17. **Không phân biệt Predicate và Function**; `filter` yêu cầu boolean còn `map` yêu cầu giá trị chuyển đổi.
18. **Gọi I/O từ rule tưởng thuần túy** rồi unit test phụ thuộc máy/dữ liệu ngoài.
19. **Thay đổi làm tròn và xử lý overflow** khi chuyển phần tính toán, khiến kết quả số không còn như trước.
20. **Dùng method riêng làm thước đo duy nhất cho code tốt**; khả năng đọc, test và tính đúng đắn mới là tiêu chí.

## 21. Checklist áp dụng

Trước khi kết thúc refactor, tự kiểm tra:

- Lambda ban đầu đang nhận kiểu nào và phải trả kiểu nào?
- Method mới có tên thể hiện một quy tắc độc lập không?
- Các nhánh, null, exception và boundary đã được ghi rõ chưa?
- Nếu có I/O hoặc mutable state, đã xác định responsibility và thread safety chưa?
- Method reference có khớp kiểu không, hay cần lambda mỏng?
- Unit tests có gọi **production method** thật không?
- Pipeline test có xác nhận stage order và output không?
- Có tình huống source empty, duplicate hoặc ordered/unordered ảnh hưởng output không?
- Có side effect nào phụ thuộc số lần callback bị Stream framework gọi không?
- Refactor có làm tổng thể mã dễ hiểu hơn không?

**Kết luận:** một lambda phức tạp nên được tách thành **phương thức có tên, input/output và hợp đồng rõ ràng** khi điều đó giúp kiểm thử độc lập và làm pipeline tập trung mô tả luồng dữ liệu. Với các lambda đơn giản, giữ inline thường tốt hơn. Mục tiêu là cải thiện khả năng bảo trì và xác minh logic, không chỉ đổi `x -> f(x)` thành `Class::f`.

**Tham khảo:** Java SE 17 API `java.util.function.Predicate`, `Function`, `Consumer`, `java.util.stream.Stream.map`, `Stream.filter`, Java Language Specification về lambda/method reference, JUnit 5 User Guide về tests và assertions.