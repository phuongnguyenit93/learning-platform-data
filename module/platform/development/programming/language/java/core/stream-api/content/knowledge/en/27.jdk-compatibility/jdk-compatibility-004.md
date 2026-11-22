# Kết hợp Collector bằng teeing từ Java 12

Trong Java Stream API, ta thường kết thúc pipeline bằng một phép thu thập: đếm số bản ghi, tính tổng tiền, tìm giá trị lớn nhất hoặc gom phần tử theo nhóm. Nhưng nhiều báo cáo cần **hai kết quả khác nhau trên cùng một tập phần tử**, chẳng hạn vừa đếm giao dịch vừa tính tổng doanh thu, vừa tìm giá trị nhỏ nhất vừa tìm giá trị lớn nhất, hoặc vừa đếm số bản ghi hợp lệ vừa đếm số bản ghi không hợp lệ.

Từ **Java 12**, `Collectors.teeing(...)` giúp kết hợp **hai Collector downstream** và một hàm **merger** thành **một Collector mới**. Mỗi phần tử đi vào hai nhánh thu thập; khi cả hai hoàn thành, merger kết hợp hai kết quả thành kiểu đầu ra cuối cùng. Nhờ vậy, ta có thể biểu diễn báo cáo hai chiều trong **một terminal `collect`** thay vì duyệt lại nguồn hoặc xây một accumulator tùy chỉnh cho mọi tình huống.

Bài học thuộc chương **Khả năng tương thích JDK** của module `JAVA_STREAM_API`. Ngoài cú pháp, ta sẽ phân tích yêu cầu phiên bản, kiểu dữ liệu, nguồn rỗng, `Optional`, tương tác với `groupingBy`/`mapping`/`filtering`, đặc tính Collector, xử lý song song, độ chính xác số học, nguồn I/O và cách thay thế trên Java 8–11. Các ví dụ dựa trên pipeline lazy có `filter`, `map`, `reduce` và `collect`.

> **Mốc tương thích:** `Collectors.teeing` là API chính thức có từ **Java 12**, không có trong Java 8–11. Những phần dùng `teeing` phải biên dịch với API từ Java 12 trở lên và chạy trên runtime tương thích. Ví dụ sử dụng lớp thông thường thay cho `record` để không vô tình yêu cầu Java 16.

## 1. Vì sao phải kết hợp hai Collector?

Giả sử có các điểm:

```text
80, 65, 90, 50
```

Ta muốn báo cáo **tổng số điểm** và **điểm trung bình**. Cách dễ nghĩ tới là duyệt hai lần:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

long count = scores.stream().count();
double average = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0);

System.out.println(count);   // 4
System.out.println(average); // 71.25
```

Với `List` trong bộ nhớ, tạo hai Stream mới có thể chấp nhận được. Tuy nhiên, khi nguồn là tệp, một Iterator chỉ duyệt được một lần, hoặc quá trình xử lý trước `collect` tốn tài nguyên, việc lặp lại pipeline có thể bất tiện hay không khả thi.

Điều **không được làm** là gọi hai terminal operation trên **cùng một instance Stream**:

```java
// SAI: cùng một Stream không thể tiêu thụ hai lần.
java.util.stream.Stream<Integer> stream = scores.stream();

long numberOfScores = stream.count();
// Lời gọi sau sẽ không hợp lệ vì stream đã bị tiêu thụ.
long sum = stream.mapToLong(Integer::longValue).sum();
```

`teeing` giải quyết bài toán khi muốn tạo **một kết quả tổ hợp** từ hai Collector cùng đọc luồng phần tử logic.

## 2. Chữ ký API và ba tham số

Chữ ký tổng quát của phương thức:

```java
public static <T, R1, R2, R> Collector<T, ?, R> teeing(
        Collector<? super T, ?, R1> downstream1,
        Collector<? super T, ?, R2> downstream2,
        BiFunction<? super R1, ? super R2, R> merger
)
```

Ý nghĩa:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử đầu vào của Stream |
| `R1` | Kết quả cuối của Collector thứ nhất |
| `R2` | Kết quả cuối của Collector thứ hai |
| `R` | Kiểu kết quả chung do merger tạo |
| `downstream1` | Thu thập kết quả độc lập thứ nhất |
| `downstream2` | Thu thập kết quả độc lập thứ hai |
| `merger` | Nhận kết quả `R1`, `R2` và tạo `R` |

Sơ đồ tư duy:

```text
                         Stream<T>
                             |
                      filter / map / ...
                             |
                     collect(teeing)
                             |
                    mỗi phần tử đầu vào
                     /               \
                    v                 v
             downstream1         downstream2
               T -> R1             T -> R2
                    \                 /
                     \               /
                           merger
                        (R1,R2) -> R
                             |
                         kết quả R
```

**Mỗi phần tử đi qua Collector mới sẽ được tích lũy vào cả hai downstream.** Nhưng merger **không chạy trên từng phần tử**: nó chỉ nhận **hai kết quả đã hoàn tất** để tạo kết quả cuối.

`teeing` là **factory tạo Collector**, còn `stream.collect(...)` mới là terminal operation kích hoạt xử lý. `teeing` không biến thành một thao tác intermediate mới như `map` hoặc `filter`.

### Ví dụ đầu tiên: đếm và lấy trung bình

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

Map.Entry<Long, Double> result = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                Map::entry
        ));

System.out.println(result.getKey());   // 4
System.out.println(result.getValue()); // 71.25
```

Ở đây:

- `Collectors.counting()` trả `Long`.
- `Collectors.averagingInt(...)` trả `Double`.
- `Map::entry` kết hợp hai giá trị thành `Map.Entry<Long,Double>`.

`Map.entry(k,v)` là factory có từ **Java 9**, nên phù hợp cho ví dụ Java 12. Entry này không hỗ trợ `setValue`. Đừng chọn nó nếu cần một đối tượng báo cáo có các trường được đặt tên rõ hơn; `Map.Entry` chủ yếu phù hợp cho minh họa ngắn.

Điều cốt lõi là `Map.Entry` biểu diễn cặp kết quả còn `Collectors.teeing` thực hiện hai phép thu thập trong một lần tiêu thụ nguồn.

## 3. Một lượt duyệt nguồn không có nghĩa một phép tính

Mỗi phần tử đầu vào được chuyển tới **hai bộ tích lũy downstream**:

```text
Phần tử "A" --+--> collector 1: tăng số đếm
              |
              +--> collector 2: cập nhật tổng độ dài
```

Vì vậy `teeing` giúp tránh **hai lần tiêu thụ nguồn**, nhưng **không miễn phí**: cả hai Collector đều làm công việc của mình. Nếu chúng cùng tính một biểu thức đắt đỏ từ `T`, biểu thức đó có thể bị tính hai lần.

Ví dụ không cần tính hai lần phép chuẩn hóa:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> rawNames = Arrays.asList(
        "  An  ", "Binh ", "  Chi"
);

Map.Entry<Long, Long> overview = rawNames.stream()
        .map(String::trim) // chuẩn hóa chung, trước teeing
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(String::length),
                Map::entry
        ));

System.out.println(overview.getKey());   // 3
System.out.println(overview.getValue()); // 9
```

Với các tên sau trim là `"An"`, `"Binh"`, `"Chi"`, tổng độ dài là `2 + 4 + 3 = 9`. `map(String::trim)` đặt **trước** teeing nên phép chuẩn hóa xảy ra trong pipeline dùng chung, thay vì lặp lại trong mỗi Collector.

**Tư duy lựa chọn:** đặt những phép biến đổi và lọc **mà cả hai nhánh đều cần** ở phía trước `teeing`. Những phép biến đổi **chỉ một nhánh cần** thì đặt trong downstream qua `mapping` hoặc `filtering`.

## 4. Trả về DTO báo cáo thay vì cặp giá trị vô danh

Trong ứng dụng thật, các trường `getKey()` và `getValue()` không mô tả rõ nghiệp vụ. Nên tạo một kiểu báo cáo có tên trường tường minh:

```java
public final class ScoreReport {
    private final long count;
    private final double average;

    public ScoreReport(long count, double average) {
        this.count = count;
        this.average = average;
    }

    public long count() {
        return count;
    }

    public double average() {
        return average;
    }

    @Override
    public String toString() {
        return "ScoreReport{count=" + count
                + ", average=" + average + "}";
    }
}
```

Dùng constructor reference làm merger:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

ScoreReport report = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(report);
// ScoreReport{count=4, average=71.25}
```

`ScoreReport::new` nhận `Long` và `Double` được Java tự unboxing thành `long` và `double` theo chữ ký constructor.

Đây là ưu điểm nổi bật của `teeing`: hai kết quả `R1` và `R2` không cần cùng kiểu, và merger có thể trả bất kỳ kiểu `R` phù hợp nào.

**Lưu ý về Java 12:** `record ScoreReport(long count, double average)` chưa phải cú pháp chính thức ở Java 12. Khi muốn giữ source tương thích với Java 12, hãy dùng class thông thường như trên.

## 5. Nguồn rỗng: đừng hiểu 0.0 là có dữ liệu

Một điểm dễ sai khi thiết kế báo cáo:

```java
import java.util.Collections;
import java.util.stream.Collectors;

ScoreReport emptyReport = Collections.<Integer>emptyList()
        .stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(emptyReport.count());   // 0
System.out.println(emptyReport.average()); // 0.0
```

`Collectors.counting()` cho `0L` với nguồn rỗng. `Collectors.averagingInt(...)` cũng trả `0.0` cho nguồn rỗng. Nhưng **`0.0` là giá trị được quy định của Collector**, không nhất thiết có nghĩa “trung bình thực sự bằng 0” theo nghiệp vụ.

Nếu cần phân biệt “không có điểm” và “trung bình bằng 0 trên dữ liệu có thật”, dùng `OptionalDouble`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

OptionalDouble average = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Integer::longValue),
                (count, total) -> count == 0L
                        ? OptionalDouble.empty()
                        : OptionalDouble.of(
                                (double) total / count
                        )
        ));

System.out.println(average.getAsDouble()); // 71.25
```

Với nguồn rỗng, merger trả `OptionalDouble.empty()`. Mẫu này biểu diễn **giá trị trung bình có thể vắng mặt** rõ ràng hơn.

Bộ cộng `summingLong` vẫn có giới hạn của `long` và có thể tràn trên dữ liệu cực lớn; nó chỉ là ví dụ cho các điểm trong miền nhỏ. Nếu nghiệp vụ cần số thập phân chính xác hoặc tổng vượt `long`, chọn kiểu dữ liệu và phép cộng khác, không tự động coi `teeing` giải quyết được bài toán số học.

### Quy tắc xử lý dữ liệu thiếu

Một `List<Integer>` có thể chứa `null`. Cả `Integer::intValue` và `Integer::longValue` đều không chấp nhận null như giá trị số, nên hãy xác định chính sách:

```java
import java.util.Arrays;
import java.util.Objects;

List<Integer> raw = Arrays.asList(80, null, 65, 90);

ScoreReport validOnly = raw.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(validOnly.count()); // 3
```

Ở đây `count` là **số điểm hợp lệ**, không phải tổng số bản ghi đầu vào. Nếu báo cáo cần số lượng dữ liệu thiếu, thêm một phép thống kê riêng hoặc thiết kế collector tổ hợp có đủ thông tin. Không nên âm thầm dùng `0` thay thế điểm null nếu điều đó làm sai ý nghĩa trung bình.

## 6. Kết hợp minBy và maxBy trong một Collector

Một trường hợp `teeing` khác là tìm **giá trị nhỏ nhất** và **giá trị lớn nhất** mà vẫn phân biệt nguồn rỗng.

Định nghĩa kết quả:

```java
public final class IntRange {
    private final int min;
    private final int max;

    public IntRange(int min, int max) {
        this.min = min;
        this.max = max;
    }

    public int min() {
        return min;
    }

    public int max() {
        return max;
    }

    @Override
    public String toString() {
        return "[" + min + ", " + max + "]";
    }
}
```

Tính kết quả:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> values = Arrays.asList(-2, 11, 7, 20, 4);

Optional<IntRange> range = values.stream()
        .collect(Collectors.teeing(
                Collectors.minBy(Comparator.naturalOrder()),
                Collectors.maxBy(Comparator.naturalOrder()),
                (min, max) -> min.flatMap(
                        low -> max.map(high ->
                                new IntRange(low, high))
                )
        ));

System.out.println(range); // Optional[[-2, 20]]
```

`minBy` và `maxBy` đều trả `Optional<Integer>`. Nếu không có phần tử, cả hai Optional đều rỗng và merger tạo `Optional.empty()`.

Đừng chọn `0` làm “giá trị lớn nhất ban đầu” khi nguồn có thể chứa số âm; cách làm đó có thể tạo giá trị không hề xuất hiện trong nguồn.

**Lựa chọn đơn giản hơn:** nếu chỉ cần min và max của `int`, `IntStream.summaryStatistics()` (Java 8) đã cung cấp cả `count`, `sum`, `min`, `max` và `average`. `teeing` không bắt buộc là lựa chọn tối ưu khi một API chuyên dụng đã trả đủ thống kê.

## 7. Kết hợp counting và reducing với BigDecimal

Một tình huống nghiệp vụ: thống kê **số giao dịch đã thanh toán** và **tổng số tiền**. Dữ liệu tiền tệ cần độ chính xác thập phân, nên dùng `BigDecimal` thay vì cộng dồn các giá trị `double`.

Lớp giao dịch:

```java
import java.math.BigDecimal;

public final class Payment {
    private final String orderId;
    private final BigDecimal amount;
    private final boolean paid;

    public Payment(String orderId, String amount, boolean paid) {
        this.orderId = orderId;
        this.amount = new BigDecimal(amount);
        this.paid = paid;
    }

    public String orderId() {
        return orderId;
    }

    public BigDecimal amount() {
        return amount;
    }

    public boolean isPaid() {
        return paid;
    }
}
```

Lớp kết quả:

```java
import java.math.BigDecimal;

public final class PaymentReport {
    private final long paidCount;
    private final BigDecimal paidTotal;

    public PaymentReport(long paidCount, BigDecimal paidTotal) {
        this.paidCount = paidCount;
        this.paidTotal = paidTotal;
    }

    public long paidCount() {
        return paidCount;
    }

    public BigDecimal paidTotal() {
        return paidTotal;
    }
}
```

Áp dụng `teeing`:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Payment> payments = Arrays.asList(
        new Payment("O01", "12.50", true),
        new Payment("O02", "7.25", false),
        new Payment("O03", "3.75", true)
);

PaymentReport paid = payments.stream()
        .filter(Payment::isPaid)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.mapping(
                        Payment::amount,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                BigDecimal::add
                        )
                ),
                PaymentReport::new
        ));

System.out.println(paid.paidCount()); // 2
System.out.println(paid.paidTotal()); // 16.25
```

Điểm thiết kế:

1. `filter(Payment::isPaid)` đặt trước `teeing` vì **hai nhánh** đều chỉ cần giao dịch đã thanh toán.
2. `counting()` đếm số giao dịch hợp lệ qua bộ lọc.
3. `mapping(Payment::amount, reducing(...))` chọn số tiền và cộng trên `BigDecimal`.
4. `PaymentReport::new` kết hợp hai kết quả thành DTO.

Nếu giao dịch có `amount == null`, `BigDecimal::add` sẽ không xử lý được. Hãy xác định chính sách bỏ qua, báo lỗi hoặc mô hình hóa giá trị vắng mặt **trước khi** thu thập.

### Vì sao có thể dùng reducing ở đây?

`Collectors.reducing(identity, operator)` là một downstream Collector hợp lệ. Với phép cộng `BigDecimal`, `BigDecimal.ZERO` là phần tử đồng nhất, còn `BigDecimal::add` trả một giá trị mới, không sửa đối tượng cũ. Vì thế thao tác phù hợp để kết hợp các kết quả riêng của nhiều nhánh khi pipeline parallel.

Điều này khác với việc dùng `reduce` để chỉnh sửa một `ArrayList` chia sẻ. Với bộ chứa mutable, `collect` và Collector phù hợp mới là lựa chọn an toàn.

## 8. Hai điều kiện khác nhau: dùng filtering trong từng nhánh

Đôi khi cả hai nhánh cần nhìn **cùng một nguồn**, nhưng mỗi nhánh đếm **một loại bản ghi**. Ví dụ muốn đếm số điểm đạt và chưa đạt ngưỡng 60.

`Collectors.filtering(predicate, downstream)` được giới thiệu từ **Java 9**, nên sẵn có khi ta dùng `teeing` trên Java 12.

Định nghĩa kiểu kết quả:

```java
public final class PassFail {
    private final long passed;
    private final long failed;

    public PassFail(long passed, long failed) {
        this.passed = passed;
        this.failed = failed;
    }

    public long passed() {
        return passed;
    }

    public long failed() {
        return failed;
    }
}
```

Pipeline:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> results = Arrays.asList(90, 45, 70, 60, 10);

PassFail summary = results.stream()
        .collect(Collectors.teeing(
                Collectors.filtering(
                        score -> score >= 60,
                        Collectors.counting()
                ),
                Collectors.filtering(
                        score -> score < 60,
                        Collectors.counting()
                ),
                PassFail::new
        ));

System.out.println(summary.passed()); // 3
System.out.println(summary.failed()); // 2
```

Ở đây **không thể** đặt `filter(score -> score >= 60)` trước `teeing` vì như vậy nhánh đếm số không đạt sẽ **không còn thấy** điểm dưới 60.

Sơ đồ:

```text
            90 45 70 60 10
                    |
                  teeing
                 /      \
       >= 60 + count    < 60 + count
             |                |
          passed=3         failed=2
                 \          /
                   PassFail
```

Nếu có thêm điểm không hợp lệ như `-1` hoặc `null`, hai điều kiện `>=60` và `<60` không còn là toàn bộ quy tắc dữ liệu. Cần đặt một bước lọc dữ liệu chung theo miền trước teeing, hoặc thiết kế một nhánh thống kê lỗi riêng. `teeing` chỉ kết hợp **hai** downstream trực tiếp; nếu có nhiều chỉ số, có thể lồng `teeing`, nhưng đừng để cấu trúc lồng nhau trở nên khó đọc.

## 9. teeing làm downstream của groupingBy

Điểm mạnh của `teeing` là nó **trả về một Collector**. Vì vậy có thể dùng Collector này làm downstream của `groupingBy`.

Bài toán: với mỗi phòng ban, trả **số nhân viên** và **tổng lương**.

### Mô hình dữ liệu

```java
public final class Employee {
    private final String department;
    private final long salary;

    public Employee(String department, long salary) {
        this.department = department;
        this.salary = salary;
    }

    public String department() {
        return department;
    }

    public long salary() {
        return salary;
    }
}
```

Kết quả nhóm:

```java
public final class DepartmentReport {
    private final long headcount;
    private final long payroll;

    public DepartmentReport(long headcount, long payroll) {
        this.headcount = headcount;
        this.payroll = payroll;
    }

    public long headcount() {
        return headcount;
    }

    public long payroll() {
        return payroll;
    }
}
```

### Thu thập theo phòng ban

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Employee> employees = Arrays.asList(
        new Employee("Engineering", 100),
        new Employee("Support", 80),
        new Employee("Engineering", 150)
);

Map<String, DepartmentReport> reports = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Employee::salary),
                        DepartmentReport::new
                )
        ));

System.out.println(reports.get("Engineering").headcount()); // 2
System.out.println(reports.get("Engineering").payroll());   // 250
System.out.println(reports.get("Support").payroll());       // 80
```

Mỗi nhóm có một bộ tích lũy downstream gồm hai thành phần. Khi một nhân viên được phân vào `Engineering`, **cả hai nhánh của teeing trong nhóm đó** đều thấy nhân viên ấy.

**Trường hợp nhóm rỗng:** `groupingBy` chỉ tạo khóa cho những phòng ban xuất hiện trong dữ liệu. Nếu không có nhân viên `QA`, Map không tự thêm `QA → DepartmentReport(0,0)`. Muốn hiển thị đủ phòng ban dự kiến, hãy bổ sung khóa từ danh mục phòng ban khi tạo báo cáo.

**Khóa null:** `groupingBy(Employee::department)` không cho phép classifier trả `null`. Nếu có phòng ban chưa xác định, cần lọc, chuẩn hóa bằng khóa đại diện không trùng giá trị thật, hoặc dùng một kiểu khóa như `Optional<String>`. `teeing` không thay đổi hợp đồng phân nhóm này.

## 10. teeing với hai downstream trả kiểu khác nhau

Hai Collector không cần trả cùng một kiểu. Có thể lấy một tập các trạng thái duy nhất và đồng thời tính số bản ghi:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

List<String> states = Arrays.asList(
        "NEW", "PAID", "NEW", "FAILED"
);

Map.Entry<Long, Set<String>> info = states.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.toSet(),
                Map::entry
        ));

System.out.println(info.getKey());              // 4
System.out.println(info.getValue().size());     // 3
System.out.println(info.getValue().contains("PAID")); // true
```

Ở đây `R1 = Long`, `R2 = Set<String>`, `R = Map.Entry<Long,Set<String>>`. Nhưng không được mặc định tập kết quả có thứ tự duyệt ổn định: `Collectors.toSet()` là unordered collector.

Nếu cần **tập được sắp xếp**, chọn `toCollection(TreeSet::new)`; nếu cần **danh sách gồm cả các giá trị trùng theo encounter order**, dùng `toList()` thay vì `toSet()`.

`Map.Entry` ở ví dụ chỉ bất biến ở cấp phép thay đổi ánh xạ qua `setValue`; nó không tự biến giá trị `Set` bên trong thành bất biến. Đừng suy luận tính bất biến lan xuyên qua object được chứa.

## 11. Characteristics của Collector teeing

Mỗi `Collector` có một tập `characteristics()`, gồm:

- `CONCURRENT`: accumulator có thể nhận lời gọi đồng thời trên cùng bộ chứa theo hợp đồng.
- `UNORDERED`: Collector không cam kết giữ encounter order.
- `IDENTITY_FINISH`: có thể dùng kết quả tích lũy trực tiếp thay cho việc chạy finisher.

Đối với `teeing`, các đặc tính có ý nghĩa như sau:

| Đặc tính | Khi nào Collector teeing có? | Lý do |
| --- | --- | --- |
| `CONCURRENT` | **Cả hai downstream** đều có `CONCURRENT` | Bộ chứa kết hợp chỉ an toàn khi cả hai nhánh đều cho phép cập nhật chung |
| `UNORDERED` | **Cả hai downstream** đều có `UNORDERED` | Kết quả tổ hợp chỉ không cần thứ tự nếu cả hai nhánh đều không cần |
| `IDENTITY_FINISH` | **Không được công bố** | Vẫn phải hoàn tất hai downstream và gọi merger |

Có thể hiểu là **giao của các đặc tính downstream, trừ `IDENTITY_FINISH`**.

Ví dụ:

```java
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Long> combined =
        Collectors.teeing(
                Collectors.counting(),
                Collectors.counting(),
                Long::sum
        );

Set<Collector.Characteristics> characteristics =
        combined.characteristics();

System.out.println(
        characteristics.contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
); // false

System.out.println(
        characteristics.contains(
                Collector.Characteristics.CONCURRENT
        )
); // false
```

Ngay cả nếu merger “chỉ trả cặp” hoặc không tính toán thêm, `teeing` vẫn không phải identity-finisher collector theo hợp đồng API.

### Tương tác với parallel stream

`teeing` vẫn có thể chạy trên `parallelStream()` khi không có `CONCURRENT`. Framework có thể tạo nhiều bộ tích lũy kết hợp cho các nhánh, rồi gộp **từng cặp trạng thái downstream** bằng combiner của chúng.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

Map.Entry<Long, Integer> summary = numbers.parallelStream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Integer::intValue),
                Map::entry
        ));

System.out.println(summary.getKey());   // 5
System.out.println(summary.getValue()); // 15
```

Kết quả cộng và đếm ở đây phù hợp với cách kết hợp theo nhiều nhánh. Nhưng parallel stream **không tự động nhanh hơn**; việc cấp bộ chứa, chia dữ liệu, combiner và thực hiện merger có chi phí.

Đặc biệt, một downstream có `CONCURRENT` không đủ để toàn `teeing` là concurrent. Nếu chỉ nhánh thứ nhất thread-safe nhưng nhánh thứ hai dùng `ArrayList` thường, việc khai báo concurrent cho bộ chứa kết hợp là sai.

## 12. Hàm merger phải làm gì và tránh điều gì?

`merger` là `BiFunction<R1,R2,R>`. Nó chạy ở bước hoàn tất để kết hợp kết quả của hai Collector; không nên thiết kế nó như một bộ tích lũy để cập nhật sau mỗi phần tử.

Một merger tốt nên:

1. Chấp nhận hai kiểu kết quả đúng như Collector downstream đã hứa.
2. Tạo một kết quả có ý nghĩa nghiệp vụ rõ ràng.
3. Xác định chính sách cho nguồn rỗng hoặc Optional rỗng.
4. Tránh ghi vào biến toàn cục, file hoặc collection bên ngoài vì đây là phần của phép tính dữ liệu.
5. Không làm mất hoặc sửa dữ liệu của downstream theo cách caller không mong đợi.
6. Đủ nhẹ; nếu chỉ cần tạo DTO, hãy làm ngay trong constructor reference.

### Ví dụ merger có tính toán bổ sung

Cần thống kê tỷ lệ điểm đạt:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> points = Arrays.asList(90, 45, 70, 60, 10);

double passRate = points.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.filtering(
                        score -> score >= 60,
                        Collectors.counting()
                ),
                (total, passed) -> total == 0L
                        ? Double.NaN
                        : 100.0 * passed / total
        ));

System.out.println(passRate); // 60.0
```

Vì có 3 điểm đạt trên 5 điểm, tỷ lệ là 60%.

Ở đây chọn `Double.NaN` cho tập rỗng để biểu diễn “không có mẫu tính tỷ lệ”; trong sản phẩm thật có thể trả `OptionalDouble` hoặc một DTO có cờ xác định rõ.

Với nguồn dữ liệu có điểm không hợp lệ, cần xác định mẫu số: nếu mẫu số chỉ tính điểm hợp lệ, hãy lọc chúng **trước** teeing; nếu muốn tính cả tỷ lệ lỗi nhập liệu, cần thêm thống kê tương ứng.

## 13. Khi nào không nên dùng teeing?

`teeing` rất hữu ích nhưng không phải API phù hợp nhất cho mọi trường hợp.

### Chỉ cần một con số

Nếu chỉ muốn tổng số phần tử, `count()` ngắn hơn:

```java
long count = scores.stream().count();
```

Nếu chỉ muốn tổng số nguyên:

```java
int sum = scores.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Không nên tạo teeing chỉ để “trông hiện đại”.

### Cùng một tập thống kê số nguyên chuẩn

`IntSummaryStatistics` trên `IntStream` đã trả count, sum, min, max và average trong một terminal operation từ Java 8:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 285
System.out.println(stats.getAverage()); // 71.25
```

Khi mọi kết quả cần thiết nằm trong kiểu thống kê chuẩn, `summaryStatistics()` đơn giản hơn `teeing`. Lưu ý `getMin()`/`getMax()` trên thống kê rỗng có giá trị quy ước riêng; kiểm tra `getCount()` trước khi dùng như cực trị thực.

### Kết quả cần hơn hai nhánh độc lập

Có thể lồng `teeing`:

```java
// Mã minh họa ý tưởng; nhiều lớp teeing làm code khó đọc.
Collectors.teeing(
        Collectors.counting(),
        Collectors.teeing(
                Collectors.summingInt(Integer::intValue),
                Collectors.averagingInt(Integer::intValue),
                Map::entry
        ),
        Map::entry
)
```

Nhưng kết quả lồng `Map.Entry<Long,Map.Entry<Integer,Double>>` khó đọc và dễ nhầm ý nghĩa trường. Với nhiều hơn hai chỉ số hoặc nhiều trạng thái phụ thuộc nhau, một **Collector tùy chỉnh** trả DTO có tên rõ ràng thường dễ bảo trì hơn.

### Hai nhánh cần chia nguồn theo cách rất khác

`teeing` đưa **mọi phần tử** vào **cả hai downstream**. Nó không phải cơ chế tách thành hai Stream độc lập có vòng đời riêng. Khi hai nhánh chỉ cần những phần tử khác nhau, `Collectors.filtering` có thể giải quyết, nhưng nếu logic phức tạp hoặc chi phí của mỗi nhánh cao, hãy cân nhắc Collector tùy chỉnh hoặc kiến trúc xử lý khác.

## 14. Java 8–11: phương án thay thế khi không có teeing

Đối với JDK thấp hơn Java 12, không thể chỉ thêm import hay thay tên gói để có `Collectors.teeing`. Nếu dự án phải giữ source/runtime ở Java 8–11, có một số phương án tùy dạng dữ liệu.

### 14.1. Dùng summaryStatistics khi đủ yêu cầu

Với `count + average` như ví dụ đầu, Java 8 đã có:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics summary = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

long count = summary.getCount();
double average = summary.getAverage();
```

Cách này không yêu cầu teeing, tránh boxing sau bước `mapToInt` và chỉ tiêu thụ nguồn một lần.

### 14.2. Dùng collect ba tham số với accumulator tự định nghĩa

Nếu cần hai phép đếm độc lập như số điểm đạt/chưa đạt, có thể tạo accumulator mutable có combiner tương thích với parallel stream:

```java
final class PassCounter {
    private long passed;
    private long failed;

    void add(Integer value) {
        if (value >= 60) {
            passed++;
        } else {
            failed++;
        }
    }

    void merge(PassCounter other) {
        passed += other.passed;
        failed += other.failed;
    }

    long passed() {
        return passed;
    }

    long failed() {
        return failed;
    }
}
```

Thu thập:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> points = Arrays.asList(90, 45, 70, 60, 10);

PassCounter result = points.stream()
        .collect(
                PassCounter::new,
                PassCounter::add,
                PassCounter::merge
        );

System.out.println(result.passed()); // 3
System.out.println(result.failed()); // 2
```

Đây là overload `Stream.collect(supplier, accumulator, combiner)` có từ Java 8. Mỗi bộ tích lũy do Supplier cấp nên độc lập; combiner gộp hai phần kết quả. Không dùng một `PassCounter` tạo ở ngoài rồi chia sẻ cho mọi nhánh.

Ví dụ giả định `points` không chứa `null` và các điểm âm vẫn được phân là chưa đạt. Nếu miền điểm bắt buộc là 0–100, hãy thêm bước xác thực phù hợp.

### 14.3. Duyệt hai lần chỉ khi nguồn có thể tạo lại

Với `List`, việc tạo hai Stream mới đơn giản và đôi khi đủ tốt. Nhưng nếu nguồn là tệp, socket hoặc Iterator chỉ dùng một lần, **không được tái sử dụng cùng Stream** sau khi terminal operation đã tiêu thụ.

Nếu cần tính hai kết quả trong một lượt mà không có teeing, chọn một trong các chiến lược:

- `summaryStatistics` nếu có thể biểu diễn bài toán bằng thống kê chuẩn;
- `collect` ba tham số với container tùy chỉnh;
- Collector tự viết bằng `Collector.of` nếu cần finisher, characteristics hoặc tái sử dụng;
- Một vòng lặp tuần tự rõ ràng khi logic quá đặc thù.

Việc tách thành hai `List` trung gian chỉ để thu thập lại có thể làm tăng bộ nhớ không cần thiết.

## 15. Khả năng tương thích source, bytecode và runtime

Khi nâng cấp Java Stream API, cần tách ba khái niệm:

| Yếu tố | Câu hỏi cần trả lời | Với teeing |
| --- | --- | --- |
| **Compiler JDK** | Trình biên dịch đang chạy phiên bản nào? | Cần `javac` đủ mới để biết API Java 12 |
| **API level (`--release`)** | Source được phép gọi những thư viện chuẩn nào? | `--release 11` không cho gọi `teeing` |
| **Runtime JDK** | JVM chạy chương trình phiên bản nào? | Runtime phải hỗ trợ API/bytecode tương ứng |

Ví dụ:

```text
javac -version
java -version
```

Để biên dịch source dùng `Collectors.teeing` với một JDK hiện đại có hỗ trợ target Java 12:

```text
javac --release 12 Example.java
```

Nếu cùng source đó được biên dịch với:

```text
javac --release 11 Example.java
```

thì compiler sẽ báo không tìm được `Collectors.teeing` (hoặc lỗi không tương thích API khác) vì API này không có trong Java 11. **`--release` không chỉ chỉnh phiên bản bytecode**; nó giới hạn tập API chuẩn mà code được phép sử dụng.

Chạy một chương trình đã biên dịch cho Java 12 trên runtime Java 11 **không được bảo đảm** và thường bị từ chối do phiên bản class file mới hơn hoặc thiếu API. Ngay cả khi ai đó cố biên dịch với target bytecode cũ nhưng vẫn liên kết tới API mới, runtime cũ cũng không cung cấp `Collectors.teeing`.

**Lưu ý môi trường:** lệnh `--release 12` cần một phiên bản `javac` hỗ trợ target release 12. Các JDK tương lai có thể không duy trì mọi target rất cũ; hãy xem danh sách release được compiler thực tế hỗ trợ thay vì mặc định mọi JDK mới luôn chấp nhận mọi target.

### Bảng phiên bản các API liên quan

| API hoặc cú pháp | Xuất hiện trong bản Java chính thức |
| --- | --- |
| `Stream`, `Collectors.groupingBy`, `reducing`, `mapping`, `counting`, `summaryStatistics` | Java 8 |
| `Collectors.filtering`, `flatMapping`, `Stream.takeWhile`/`dropWhile`, `Map.entry` | Java 9 |
| `Collectors.teeing` | **Java 12** |
| `Stream.toList()` | Java 16 |
| `record` (cú pháp ngôn ngữ chính thức) | Java 16 |
| `Stream.gather` và `Gatherers` (API chính thức) | Java 24 |

Vì bài tập hướng Java 12, các ví dụ dùng `collect(Collectors.toList())` thay cho `Stream.toList()`, và sử dụng class thông thường thay cho `record`. Không nên sao chép `Stream.gather(...)` vào codebase nhắm tới Java 12 vì đó là API phiên bản mới hơn.

Để chọn chính sách cho một module có nhiều mục tiêu JDK, có thể đặt một lớp tương thích riêng: triển khai bằng `teeing` ở nhánh yêu cầu Java 12+, còn nhánh Java 8–11 dùng accumulator riêng với **cùng một kiểu DTO đầu ra**. Điều này giữ API nghiệp vụ ổn định giữa các phiên bản.

## 16. Đọc nguồn I/O và trả báo cáo từ một lượt xử lý

Khi nguồn là tệp, `teeing` đặc biệt thuận tiện vì có thể lấy hai chỉ số mà chỉ xây **một pipeline đọc dòng**.

Ví dụ đếm số dòng không rỗng và tổng số ký tự của các dòng đó:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map.Entry<Long, Long> inspectText(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(String::length),
                        Map::entry
                ));
    }
}
```

Nếu tệp chứa:

```text
Java

Stream
API
```

và không có dòng dữ liệu khác, sau khi bỏ dòng rỗng sẽ có `3` dòng, tổng số ký tự là `4 + 6 + 3 = 13`.

`Files.lines` là nguồn I/O lazy và **giữ tài nguyên**. `collect`, dù có teeing, **không tự đóng Stream**. `try-with-resources` bảo đảm đóng nguồn sau khi báo cáo hoàn tất hoặc có ngoại lệ.

Lỗi đọc trong khi duyệt Stream có thể được bọc thành `UncheckedIOException`. Hàm `String::trim` và `filter` không thay thế bước kiểm tra mã hóa hoặc định dạng tệp. Nếu cần tính chiều dài theo số **code point Unicode** thay cho số đơn vị UTF-16, `String.length()` chưa đủ; phải dùng quy tắc đếm khác.

### Một lượt duyệt logic và giới hạn tài nguyên

`teeing` giúp không phải viết:

```java
// Không nên mở/đọc lại tệp chỉ để lấy một thống kê khác,
// nếu có thể tổng hợp cả hai trong một lượt.
long lines = ...;
long characters = ...;
```

Tuy nhiên, “một lượt” không có nghĩa “đọc đúng một byte một lần”: buffering của Reader và hệ thống file quyết định chi tiết I/O. Nó cũng không có nghĩa teeing sẽ tự bảo vệ việc đọc tệp bị sửa trong lúc xử lý; đây là vấn đề nhất quán của nguồn dữ liệu.

## 17. Hiệu năng và an toàn khi dùng teeing

Điểm mạnh của `teeing` là **tổ chức hai phép tích lũy trong một Collector**, không phải bảo đảm nhanh hơn mọi giải pháp.

### Nguồn nhỏ và việc tính toán nhẹ

Nếu chỉ có vài chục số nguyên trong `List`, việc tạo hai Stream có thể đủ nhanh và đơn giản; `IntSummaryStatistics` còn gọn hơn nếu cần những chỉ số chuẩn. Không nên tối ưu chỉ dựa vào độ mới của API.

### Hai downstream có chi phí riêng

Một phần tử sẽ đi tới **cả hai** accumulator downstream. Nếu mỗi bên phải hash, parse hoặc truy cập cấu trúc mutable, cả hai chi phí vẫn tồn tại. Đặt những phép biến đổi chung trước teeing để tránh tính lại không cần thiết.

### Parallel stream và thứ tự

`teeing` không tự động là concurrent collector. Với `parallelStream()`, Java có thể tạo nhiều bộ chứa rồi combiner kết hợp. Nếu một downstream cần thứ tự, không tự ý đánh dấu toàn pipeline `unordered()` chỉ để tăng tốc.

Ví dụ `teeing(toList(), counting(), ...)` chứa một nhánh cần encounter order. Vì `counting()` không làm `toList()` trở thành unordered, kết quả tổ hợp vẫn cần tôn trọng yêu cầu thứ tự của nhánh danh sách.

### Side effect và tính đúng đắn

Tránh các lambda trong downstream hoặc merger tự sửa một biến ngoài:

```java
// SAI về thiết kế: side effect ngoài pipeline không phải kết quả thu thập.
long[] externalCount = {0};

scores.parallelStream()
        .peek(x -> externalCount[0]++)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Integer::intValue),
                Map::entry
        ));
```

`externalCount[0]++` không an toàn dưới parallel stream, và `peek` không phải cách xác định số lượng mà nghiệp vụ nên phụ thuộc. Hãy sử dụng kết quả `counting()` đã có trong teeing.

### Tài nguyên và bộ nhớ

Nếu downstream thứ nhất là `toList()`, toàn bộ phần tử đã đi tới Collector có thể được giữ trong bộ nhớ, dù downstream thứ hai chỉ đếm. `teeing` không tự biến một Collector lưu danh sách thành một phép tổng hợp `O(1)` bộ nhớ.

Nếu chỉ cần số lượng, tổng hoặc cực trị, chọn downstream có trạng thái nhỏ; với dữ liệu cực lớn, cân nhắc giới hạn miền số, số phần tử và đặc tính nguồn trước khi chạy parallel.

## 18. Những lỗi thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `Collectors.teeing` khi biên dịch `--release 11` | Compiler không tìm thấy API | Nâng target lên Java 12+ hoặc dùng giải pháp Java 8 |
| Nghĩ `teeing` có từ Java 8 như `groupingBy` | Sai phiên bản | Ghi rõ Java 12 |
| Dùng `Stream.toList()` trong bài bắt buộc tương thích Java 12 | `Stream.toList` xuất hiện từ Java 16 | Dùng `collect(Collectors.toList())` |
| Dùng `record` trong source Java 12 | Cú pháp record chưa chính thức ở Java 12 | Dùng class/DTO thông thường |
| Gọi `count()` rồi `collect()` trên cùng Stream | Stream đã bị tiêu thụ | Dùng teeing hoặc tạo Stream mới từ nguồn có thể tạo lại |
| Cho rằng merger chạy trên từng phần tử | Thiết kế sai accumulator | Merger chỉ ghép hai kết quả downstream đã hoàn tất |
| Quên xử lý nguồn rỗng | `averagingInt` trả 0.0 khiến báo cáo dễ hiểu nhầm | Kiểm tra count hoặc dùng `OptionalDouble` |
| Đặt `filter(passed)` trước teeing khi nhánh khác cần failed | Nhánh failed không còn nhìn thấy dữ liệu | Dùng `Collectors.filtering` trong từng nhánh |
| Suy ra teeing luôn `CONCURRENT` khi một nhánh concurrent | Sai hợp đồng thread-safety | Cả hai downstream phải concurrent |
| Suy ra teeing luôn `UNORDERED` nếu một nhánh unordered | Nhánh còn lại có thể yêu cầu encounter order | Chỉ unordered khi cả hai đều unordered |
| Cho rằng teeing là `IDENTITY_FINISH` nếu merger tạo cặp | Có finisher của hai nhánh và merger | Không khai báo `IDENTITY_FINISH` |
| Kết hợp hai `toList()` rồi nghĩ bộ nhớ ít vì một lượt nguồn | Cả hai danh sách vẫn chiếm bộ nhớ | Chỉ lưu đúng chỉ số cần thiết |
| Dùng `groupingBy(...,teeing(...))` rồi mong nhóm chưa xuất hiện có mặt | groupingBy chỉ tạo nhóm đã gặp | Bổ sung từ danh mục nhóm dự kiến |
| Dùng `groupingBy` với classifier null | `NullPointerException` | Chuẩn hóa khóa/loại bản ghi không hợp lệ |
| Ghi side effect vào biến ngoài từ `peek` trong parallel | Race và kết quả không tin cậy | Đưa phép đếm vào Collector |
| Dùng `Files.lines` mà không đóng vì nghĩ teeing tự đóng | Rò rỉ tài nguyên I/O | `try-with-resources` |
| Không xem xét overflow của `summingInt`/`summingLong` | Sai kết quả với dữ liệu cực lớn | Chọn miền số/chiến lược phát hiện tràn phù hợp |

## 19. Quy trình chọn Collector cho báo cáo hai chỉ số

Khi nhận yêu cầu tổng hợp, hãy xác định lần lượt:

1. **Runtime và target JDK nào?** Nếu thấp hơn Java 12, không chọn `teeing` làm API bắt buộc.
2. **Cả hai chỉ số dùng cùng tập phần tử hay không?** Nếu có, đặt bộ lọc/biến đổi chung trước teeing.
3. **Chỉ số nào phụ thuộc điều kiện riêng?** Dùng downstream `filtering`/`mapping` thay vì loại dữ liệu mà nhánh khác cần.
4. **Kết quả rỗng phải biểu diễn thế nào?** Phân biệt `0`, `0.0` và “không có dữ liệu”.
5. **Có một collector chuyên dụng đủ dùng không?** Với count/min/max/sum/average chuẩn, thử `summaryStatistics` trước.
6. **Đầu ra nên là gì?** `Map.Entry` cho ví dụ nhanh; DTO có tên trường khi dùng trong nghiệp vụ.
7. **Có gom theo nhóm không?** Kết hợp `groupingBy(classifier, teeing(...))` nhưng nhớ các nhóm vắng mặt.
8. **Có cần song song và encounter order không?** Kiểm tra characteristics của cả hai downstream.
9. **Có giới hạn bộ nhớ và tài nguyên không?** Chọn collector chỉ giữ thống kê cần thiết, đóng nguồn I/O.
10. **Đã kiểm tra kết quả với đầu vào rỗng, một phần tử, nhiều phần tử, null, số âm và dữ liệu lớn chưa?**

## 20. Bài tập thực hành

### Bài tập A: thống kê đơn hàng theo trạng thái

Dữ liệu gồm đơn hàng `paid` và `unpaid`. Dùng `teeing` để trả `PaymentReport` gồm `paidCount` và `paidTotal`, nhưng không được tính đơn chưa thanh toán vào tổng. Kiểm thử nguồn rỗng và nhiều đơn cùng số tiền.

**Gợi ý:** đặt `filter(Payment::isPaid)` trước teeing. Khi cần đếm cả đơn chưa thanh toán, dùng `filtering` riêng hoặc một Collector có nhiều trạng thái.

### Bài tập B: min–max trong một terminal operation

Viết `Collectors.teeing(minBy(...), maxBy(...), merger)` và trả `Optional<IntRange>`. Thử các nguồn:

```text
[]
[7]
[-10, -1, -5]
[100, 2, 100]
```

Kết quả mong đợi lần lượt:

```text
Optional.empty
Optional[7,7]
Optional[-10,-1]
Optional[2,100]
```

Chuỗi hiển thị trên là mô tả logic; `toString()` chính xác của `Optional<IntRange>` phụ thuộc `IntRange.toString()`.

### Bài tập C: thống kê theo phòng ban

Từ `List<Employee>`, xây `Map<String, DepartmentReport>` với `headcount` và `payroll`, sau đó bổ sung phòng ban `QA` nếu hệ thống yêu cầu một báo cáo đầy đủ danh mục.

**Tiêu chí:** không duyệt lại danh sách nhân viên cho từng phòng ban; khóa phân nhóm không được null; nhóm chưa thấy được xử lý tường minh.

### Bài tập D: tương thích Java 8–11

Viết `PassCounter` có `add` và `merge` cho hai giá trị passed/failed, không sử dụng `teeing`. So sánh kết quả với bản Java 12 dùng `teeing(filtering(...), filtering(...), ...)` trên cùng dữ liệu.

**Tiêu chí:** kết quả giống nhau khi chạy tuần tự và song song, không chia sẻ một accumulator mutable ngoài Supplier.

### Bài tập E: kiểm tra compile target

Trong một môi trường phát triển có JDK phù hợp, biên dịch một lớp gọi `Collectors.teeing` với `--release 12` và với `--release 11`. Giải thích vì sao trường hợp thứ hai không thể truy cập API.

**Lưu ý:** không cần dùng record, `Stream.toList()` hay API mới hơn khi viết source Java 12.

## 21. Câu hỏi tự kiểm tra

1. `Collectors.teeing` xuất hiện chính thức từ Java nào? **Java 12**.
2. `teeing` nhận bao nhiêu tham số? **Ba: downstream1, downstream2, merger**.
3. Hai downstream có cần trả về cùng kiểu không? **Không**, chúng có thể trả `R1` và `R2` khác nhau.
4. Merger chạy trên từng phần tử hay trên hai kết quả đã hoàn tất? **Trên hai kết quả downstream đã hoàn tất**.
5. `teeing` có phải terminal operation không? **Không**, nó tạo Collector; `stream.collect(...)` mới là terminal.
6. Với `counting` và `averagingInt` trên nguồn rỗng, kết quả là gì? **0L và 0.0**.
7. Vì sao `0.0` của `averagingInt` trên nguồn rỗng có thể cần xử lý riêng? **Vì không có mẫu, khác với trung bình 0 của dữ liệu thật**.
8. `Collectors.filtering` dùng trong một nhánh teeing nhằm làm gì? **Chọn phần tử cho riêng nhánh đó mà không loại chúng khỏi nhánh kia**.
9. `teeing` có thể làm downstream của `groupingBy` không? **Có**, vì nó trả về Collector.
10. `groupingBy(..., teeing(...))` có tự tạo nhóm chưa từng xuất hiện không? **Không**.
11. Nếu chỉ một downstream concurrent, teeing có đặc tính `CONCURRENT` không? **Không**.
12. Nếu cả hai downstream unordered, teeing có thể có `UNORDERED` không? **Có**.
13. Tee Collector có `IDENTITY_FINISH` không? **Không**, vì phải hoàn tất hai downstream rồi chạy merger.
14. Có thể dùng `summaryStatistics` trên Java 8 để thay teeing trong bài đếm và trung bình không? **Có**, nếu thống kê chuẩn đã đủ.
15. Gọi `collect(teeing(...))` trên Stream từ `Files.lines` có tự đóng tệp không? **Không**, phải đóng Stream bằng `try-with-resources`.
16. Tee Collector có khiến hai accumulator không tốn chi phí tính toán nữa không? **Không**, nó chỉ tổ chức hai phép tổng hợp trong một lượt nguồn.
17. `record` có dùng được như cú pháp chính thức khi source phải tương thích Java 12 không? **Không**, nên dùng class.
18. Nếu dùng `javac --release 11`, `Collectors.teeing` có được biên dịch không? **Không**, API không thuộc Java 11.
19. Khi cần hơn hai chỉ số, có bắt buộc lồng teeing vô hạn không? **Không**, có thể tạo Collector tùy chỉnh hoặc dùng thống kê chuyên dụng.
20. Vì sao cần kiểm tra merge/combiner khi dùng teeing với parallel stream? **Vì mỗi downstream có thể gộp các bộ tích lũy từ nhiều nhánh và phải giữ đúng hợp đồng**.

**Nguyên tắc áp dụng:** `Collectors.teeing` từ Java 12 phù hợp khi cần **hai kết quả tổng hợp khác nhau từ cùng một Stream** rồi ghép thành một DTO hoặc cấu trúc báo cáo. Hãy đặt thao tác chung trước teeing, đặt điều kiện riêng trong downstream, xử lý nguồn rỗng tường minh và chọn cách biểu diễn kết quả dễ đọc. Đừng dùng teeing chỉ vì nó mới: `summaryStatistics`, `count`, `sum` hoặc Collector tùy chỉnh có thể đơn giản hơn. Cuối cùng, kiểm tra đúng mục tiêu JDK, an toàn khi parallel, giới hạn bộ nhớ và vòng đời nguồn I/O trước khi đưa bài toán vào ứng dụng.
