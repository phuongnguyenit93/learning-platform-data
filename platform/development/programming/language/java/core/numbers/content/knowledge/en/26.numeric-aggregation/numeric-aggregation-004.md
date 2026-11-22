# average và yêu cầu xử lý tập rỗng trong Java

## 1. Vì sao tập rỗng là trường hợp riêng?

Trung bình cộng (arithmetic mean) của `n` số là tổng của chúng chia cho số lượng phần tử:

```text
average = (x1 + x2 + ... + xn) / n
Điều kiện: n > 0
```

Ví dụ, dãy `[10, 20, 30]` có tổng 60, số lượng 3, trung bình 20.0. Nhưng một tập rỗng không chứa số hạng nào: tổng quy ước bằng 0, số lượng bằng 0, và `0 / 0` **không xác định trung bình cộng**.

Trong Java, **các API khác nhau chọn cách biểu diễn trường hợp rỗng khác nhau**:

| API | Trên tập không rỗng | Trên tập rỗng |
| --- | --- | --- |
| `IntStream.average()` | `OptionalDouble` chứa giá trị | `OptionalDouble.empty()` |
| `LongStream.average()` | `OptionalDouble` chứa giá trị | `OptionalDouble.empty()` |
| `DoubleStream.average()` | `OptionalDouble` chứa giá trị | `OptionalDouble.empty()` |
| `Collectors.averagingInt/Long/Double` | `Double` chứa trung bình | `0.0` |
| `IntSummaryStatistics.getAverage()` | `double` chứa trung bình | `0.0` |
| `LongSummaryStatistics.getAverage()` | `double` chứa trung bình | `0.0` |
| `DoubleSummaryStatistics.getAverage()` | `double` chứa trung bình | `0.0` |

Điểm cốt lõi: **0.0 là một kết quả số hợp lệ**, ví dụ trung bình của `[-10, 10]`; vì vậy không thể nhìn riêng số `0.0` để biết có dữ liệu hay không. Nếu xử lý sai tập rỗng, chương trình có thể báo điểm trung bình 0 cho lớp chưa có điểm, hoặc báo thời gian phản hồi trung bình 0 ms dù chưa ghi nhận yêu cầu nào.

## 2. average() của primitive stream trả OptionalDouble

Java cung cấp `average()` trên ba primitive stream: `IntStream`, `LongStream` và `DoubleStream`. Mỗi phương thức trả `java.util.OptionalDouble`, thay vì trả trực tiếp `double`.

```java
OptionalDouble present = IntStream.of(2, 4, 6).average();
OptionalDouble absent = IntStream.empty().average();

// present.isPresent() == true, present.orElseThrow() == 4.0
// absent.isEmpty() == true
```

Khối trên chỉ minh họa API trong một phương thức; muốn dùng riêng cần import `java.util.OptionalDouble` và `java.util.stream.IntStream`.

`OptionalDouble` là kiểu mang hai trạng thái:

- **Có giá trị:** ví dụ `OptionalDouble.of(0.0)` vẫn là kết quả có mặt, dù giá trị là số không.
- **Không có giá trị:** `OptionalDouble.empty()` biểu thị phép tổng hợp không có trung bình vì thiếu phần tử.

Các phương thức xử lý thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isPresent()` | Có kết quả không? |
| `isEmpty()` | Không có kết quả không? (Java 11+) |
| `ifPresent(action)` | Chỉ thực hiện hành động khi có kết quả |
| `orElse(defaultValue)` | Trả giá trị thật hoặc giá trị mặc định do caller quy định |
| `orElseGet(supplier)` | Tính giá trị mặc định khi không có kết quả |
| `orElseThrow()` | Bắt buộc phải có giá trị; nếu không có thì ném `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Rỗng thì ném ngoại lệ do nghiệp vụ chỉ định |
| `getAsDouble()` | Đọc giá trị hiện có; rỗng sẽ ném `NoSuchElementException` |
| `stream()` | Chuyển thành `DoubleStream` có 0 hoặc 1 phần tử (Java 9+) |

Việc gọi `average()` trên một primitive stream rỗng **không tự ném ngoại lệ**; ngoại lệ xuất hiện khi người gọi cố lấy giá trị không có sẵn bằng `getAsDouble()` hoặc `orElseThrow()`.

## 3. Chương trình Java 17+ đầu tiên: kết quả có mặt, vắng mặt và mặc định

Lưu mã sau thành `AverageEmptyDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class AverageEmptyDemo {
    public static void main(String[] args) {
        OptionalDouble normal = IntStream.of(10, 20, 30).average();
        OptionalDouble zeroMean = IntStream.of(-5, 5).average();
        OptionalDouble missing = IntStream.empty().average();

        System.out.println("Normal: " + normal.orElseThrow());
        System.out.println("Zero mean present: " + zeroMean.isPresent());
        System.out.println("Zero mean value: " + zeroMean.orElseThrow());
        System.out.println("Empty present: " + missing.isPresent());
        System.out.println("Empty fallback: " + missing.orElse(0.0));

        double collectorEmpty = Stream.<Integer>empty()
                .collect(Collectors.averagingInt(Integer::intValue));
        IntSummaryStatistics stats = IntStream.empty().summaryStatistics();

        System.out.println("Collector empty: " + collectorEmpty);
        System.out.println("Summary count: " + stats.getCount());
        System.out.println("Summary average: " + stats.getAverage());
    }
}
```

Biên dịch và chạy:

```bash
javac AverageEmptyDemo.java
java AverageEmptyDemo
```

Stdout chính xác:

```text
Normal: 20.0
Zero mean present: true
Zero mean value: 0.0
Empty present: false
Empty fallback: 0.0
Collector empty: 0.0
Summary count: 0
Summary average: 0.0
```

Các dòng `Zero mean value: 0.0` và `Empty fallback: 0.0` trùng số nhưng **khác ý nghĩa**: một phép tính đã có hai số, còn phép tính kia không có giá trị và được người gọi *thay thế* bằng số 0. Dòng `Collector empty: 0.0` là quy ước của collector, không biến trung bình cộng của tập rỗng thành kết quả toán học 0.

## 4. Ba chính sách khi gặp tập rỗng

### 4.1. Cho phép thiếu kết quả: giữ OptionalDouble

Đối với báo cáo có thể chưa có giao dịch, chưa có điểm thi hoặc chưa có mẫu cảm biến, việc **không có trung bình** là trạng thái bình thường.

```java
OptionalDouble average = scores.stream()
        .mapToInt(Integer::intValue)
        .average();
```

Đoạn minh họa giả sử `scores` là `Collection<Integer>` không chứa `null` và nằm trong một phương thức. Trả nguyên `OptionalDouble` từ service giúp tầng hiển thị chọn “Chưa có dữ liệu” thay vì vô tình hiển thị `0`.

### 4.2. Không được phép rỗng: ném lỗi nghiệp vụ

Nếu ít nhất một giá trị là điều kiện bắt buộc, hãy kiểm tra và báo rõ nguyên nhân:

```java
double mean = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow(() ->
                new IllegalArgumentException("At least one score is required"));
```

`orElseThrow(Supplier)` cung cấp ngoại lệ rõ ngữ cảnh. Cách này dễ chẩn đoán hơn việc gọi `getAsDouble()` không kiểm tra rồi để `NoSuchElementException` lan ra.

### 4.3. Có chính sách mặc định: dùng orElse

Nếu thiết kế báo cáo quy định “không có mẫu thì hiển thị 0”, có thể dùng:

```java
double displayAverage = values.stream()
        .mapToDouble(Double::doubleValue)
        .average()
        .orElse(0.0);
```

Nhưng phải hiểu: đây là **giá trị thay thế theo nghiệp vụ**, không phải trung bình được tính từ tập rỗng. Khi cần phân biệt “rỗng” và “trung bình thật bằng 0”, hãy lưu thêm số lượng phần tử hoặc trạng thái tồn tại.

Không dùng `-1`, `NaN` hay `0` làm dấu hiệu “thiếu” tùy tiện: domain có thể có giá trị đó; xử lý JSON/database hoặc toán học tiếp theo cũng có thể thay đổi ý nghĩa. `OptionalDouble` hoặc kết quả có trường `count` thể hiện sự thiếu dữ liệu rõ ràng hơn.

## 5. Phân biệt Stream.average và Collectors.averaging*

`Stream<T>` của đối tượng **không** có `average()` trực tiếp. Nếu có `List<Integer>`, thường chuyển sang primitive stream:

```java
OptionalDouble average = numbers.stream()
        .mapToInt(Integer::intValue)
        .average();
```

Hoặc dùng collector:

```java
double average = numbers.stream()
        .collect(Collectors.averagingInt(Integer::intValue));
```

Hai khối trên giả định `numbers` là một `List<Integer>` hợp lệ ở phạm vi gọi; chúng không phải chương trình Java độc lập. Trong trường hợp đầu, rỗng cho `OptionalDouble.empty()`. Trong trường hợp sau, rỗng cho `0.0` vì `Collectors.averagingInt` trả `Double` và được định nghĩa như vậy.

`Collectors.averagingLong`, `Collectors.averagingDouble` có chính sách tương tự trên tập rỗng. Sự khác biệt kiểu trả về quyết định lượng thông tin còn giữ lại: collector chỉ chứa số thì **không giữ được** trạng thái “không có phần tử”.

Nếu đang dùng `groupingBy`, mỗi nhóm xuất hiện trong kết quả khi có ít nhất một phần tử thuộc nhóm ấy; một nhóm không xuất hiện trong map **không phải** là một entry có average 0.0. Phải xác định danh sách nhóm bắt buộc từ nghiệp vụ nếu muốn biểu diễn cả nhóm rỗng.

## 6. SummaryStatistics: kiểm tra count trước khi diễn giải average

`summaryStatistics()` tính nhiều đại lượng trong một terminal operation. Ví dụ:

```java
IntSummaryStatistics statistics = numbers.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

long count = statistics.getCount();
if (count == 0) {
    System.out.println("No observations");
} else {
    System.out.println("Average = " + statistics.getAverage());
}
```

Đoạn trên giả định đã import `java.util.IntSummaryStatistics`, `numbers` là collection không chứa `null`.

Với `IntSummaryStatistics` rỗng:

- `getCount()` trả `0`.
- `getSum()` trả `0`.
- `getAverage()` trả `0.0`.
- `getMin()` trả `Integer.MAX_VALUE`.
- `getMax()` trả `Integer.MIN_VALUE`.

Vì vậy phải kiểm tra `count` trước khi trình bày average, min và max như số thống kê của mẫu thật. `LongSummaryStatistics` và `DoubleSummaryStatistics` cũng có khái niệm count và giá trị mặc định cho tập rỗng, dù kiểu và ranh giới số của min/max khác nhau.

`summaryStatistics()` phù hợp khi cần vừa count vừa mean, min, max. Nếu chỉ quan tâm trung bình và trạng thái có/không có, `average()` trả `OptionalDouble` trực tiếp thường đơn giản hơn.

## 7. Thiết kế API để bảo toàn ý nghĩa tập rỗng

Một utility trả `OptionalDouble` giúp người gọi tự áp quy tắc nghiệp vụ:

```java
import java.util.Collection;
import java.util.Objects;
import java.util.OptionalDouble;

public class AverageService {
    public static OptionalDouble ofIntegers(Collection<Integer> values) {
        Objects.requireNonNull(values, "values");
        return values.stream()
                .mapToInt(Integer::intValue)
                .average();
    }
}
```

Class này biên dịch được nhưng không có `main`; nó cung cấp hàm tiện ích để gọi từ code khác.

Ví dụ:

```java
OptionalDouble x = AverageService.ofIntegers(java.util.List.of(4, 6));
// x.orElseThrow() == 5.0

OptionalDouble y = AverageService.ofIntegers(java.util.List.of());
// y.isEmpty() == true
```

Lưu ý: `Objects.requireNonNull` chỉ kiểm tra **collection** khác `null`, không tự kiểm tra các phần tử. Nếu một phần tử `Integer` là `null`, unboxing từ `Integer::intValue` sẽ ném `NullPointerException`. Phải xác định dữ liệu `null` là lỗi nhập, giá trị thiếu cần ghi nhận, hay bản ghi được phép bỏ qua, rồi triển khai đúng chính sách đó.

Với API JSON, có thể dùng DTO biểu thị `count` và `average` có thể thiếu, thay vì kỳ vọng mọi thư viện serialization đều hiểu `OptionalDouble` như một trường dữ liệu tiêu chuẩn. Khi đó tên trường và quy tắc vắng mặt nên được mô tả rõ.

## 8. Chương trình minh họa nhóm dữ liệu

Với thống kê theo lớp, nhóm không có bản ghi thường **không có khóa** trong kết quả `groupingBy`. Lưu `GroupAverageDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupAverageDemo {
    record Score(String group, int points) {}

    public static void main(String[] args) {
        List<Score> data = List.of(
                new Score("A", 10),
                new Score("A", 20));

        Map<String, Double> result = data.stream().collect(
                Collectors.groupingBy(
                        Score::group,
                        Collectors.averagingInt(Score::points)));

        System.out.println("A average: " + result.get("A"));
        System.out.println("Has B: " + result.containsKey("B"));
        System.out.println("Group count: " + result.size());
    }
}
```

Chạy:

```bash
javac GroupAverageDemo.java
java GroupAverageDemo
```

Stdout:

```text
A average: 15.0
Has B: false
Group count: 1
```

Không có khóa B vì dữ liệu ban đầu không chứa Score của B. Nếu báo cáo bắt buộc phải hiển thị B, hãy lấy danh sách lớp từ nguồn domain, rồi đối chiếu với kết quả thống kê; không thể tự suy ra các lớp vắng mặt từ một stream đầu vào.

## 9. Độ chính xác và lỗi số học khi tính average

Việc xử lý tập rỗng khác với việc chọn độ chính xác. `average()` trả `double`, kể cả khi dữ liệu đầu vào là `int` hay `long`. `double` có độ chính xác hữu hạn, nên phép tính có thể bị làm tròn, đặc biệt khi dữ liệu lớn. Với `DoubleStream`, kết quả có thể là `NaN` hoặc vô cực tùy dữ liệu.

Các lưu ý:

1. `OptionalDouble.of(Double.NaN)` **không giống** `OptionalDouble.empty()`. Nếu ứng dụng chỉ chấp nhận số hữu hạn, sau khi kiểm tra có giá trị hãy dùng `Double.isFinite(value)`.
2. Nếu tự triển khai bằng `int sum` và `int count`, biểu thức `sum / count` là **phép chia nguyên**. Ví dụ tổng 5 và count 2 cho kết quả nguyên 2 trước khi gán sang `double`. Cần đổi sang `double` trước phép chia: `((double) sum) / count`.
3. Khi tự tính bằng integer, tổng `int` hoặc `long` có thể tràn số. Đừng giả định dữ liệu đầu vào nhỏ chỉ vì một phần tử có kiểu `int`.
4. Thứ tự cộng các `double` có thể ảnh hưởng sai số. Một số phép tổng hợp trong Java dùng kỹ thuật bù sai số, nhưng điều đó không đảm bảo kết quả chính xác tuyệt đối như số thực toán học.
5. Không dùng `==` để so trung bình dấu phẩy động tính từ các luồng thuật toán khác nhau một cách thiếu cân nhắc; thiết kế ngưỡng sai số và xử lý `NaN`, vô cực tùy bài toán.
6. Với dữ liệu tiền tệ cần decimal chính xác và rounding rõ ràng, cân nhắc `BigDecimal`.

Ngoài ra, `Stream` là luồng tiêu thụ **một lần**. Nếu gọi `count()` rồi `average()` trên cùng một primitive stream sẽ không hợp lệ; hai terminal operation không được chạy trên cùng stream đã tiêu thụ. Hãy tạo stream mới từ collection, hoặc dùng `summaryStatistics()` để lấy count và average trong cùng lần duyệt.

## 10. BigDecimal: kiểm tra rỗng và khai báo rounding

Với số thập phân cần kiểm soát độ chính xác và làm tròn, có thể tính tổng bằng `BigDecimal` rồi chia theo số phần tử. Nhưng cần kiểm tra tập rỗng trước khi chia để tránh mẫu số bằng 0.

Lưu `DecimalAverageDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class DecimalAverageDemo {
    static Optional<BigDecimal> average(List<BigDecimal> values) {
        Objects.requireNonNull(values, "values");
        if (values.isEmpty()) {
            return Optional.empty();
        }

        BigDecimal sum = BigDecimal.ZERO;
        for (BigDecimal item : values) {
            sum = sum.add(Objects.requireNonNull(item, "item"));
        }

        BigDecimal mean = sum.divide(
                BigDecimal.valueOf(values.size()),
                2,
                RoundingMode.HALF_UP);

        return Optional.of(mean);
    }

    public static void main(String[] args) {
        System.out.println("Mean: " + average(List.of(
                new BigDecimal("1.00"),
                new BigDecimal("2.00"),
                new BigDecimal("2.00"))).orElseThrow());
        System.out.println("Empty: " + average(List.of()).isEmpty());
        System.out.println("Zero mean: " + average(List.of(
                new BigDecimal("-1.00"),
                new BigDecimal("1.00"))).orElseThrow());
    }
}
```

Chạy:

```bash
javac DecimalAverageDemo.java
java DecimalAverageDemo
```

Stdout:

```text
Mean: 1.67
Empty: true
Zero mean: 0.00
```

`5.00 / 3` có khai triển thập phân vô hạn, nên `divide(divisor)` *không chỉ rõ chế độ làm tròn* sẽ ném `ArithmeticException`. Ví dụ đã chọn scale 2, `HALF_UP` nên kết quả là `1.67`. Scale và chế độ rounding phải đến từ yêu cầu nghiệp vụ, **không mặc định mọi giá trị tiền tệ cần hai chữ số lẻ**.

Khi không có phần tử, hàm trả `Optional.empty()`; không thực hiện phép chia. Khi có phần tử và trung bình thật bằng 0, hàm trả `Optional.of(new BigDecimal("0.00"))` về mặt giá trị và scale của kết quả đã tính.

## 11. average theo nhóm và trung bình có trọng số

Không phải mọi nhu cầu gọi là “average” đều tương đương nhau:

- **Trung bình cộng thông thường:** `sum(values) / count`, chỉ xác định khi count > 0.
- **Trung bình có trọng số:** `sum(value × weight) / sum(weight)`; phải kiểm tra tổng trọng số theo hợp đồng trước khi chia.
- **Trung bình các trung bình nhóm:** khác với trung bình mọi phần tử nếu nhóm có số lượng không bằng nhau.
- **Trung bình theo thời lượng:** nếu khoảng thời gian lấy mẫu khác nhau, có thể phải dùng trọng số theo thời gian thay vì coi mọi quan sát là một đơn vị.

Ví dụ nhóm A có một điểm 10, nhóm B có ba điểm 20, 20, 20. Trung bình các nhóm `(10 + 20) / 2 = 15`; trung bình trên bốn học sinh `(10 + 20 + 20 + 20) / 4 = 17.5`. Phép nào phù hợp tùy vào câu hỏi báo cáo.

Tập rỗng, nhóm rỗng, và tổng trọng số bằng 0 đều cần được quy định rõ. Không tự đồng nhất `Collectors.averagingInt` trả 0.0 với một trung bình có trọng số hợp lệ.

## 12. Gợi ý kiểm thử các trường hợp quan trọng

Đối với utility tính trung bình, nên có những trường hợp:

| Đầu vào | Điều cần kiểm tra |
| --- | --- |
| `[]` | Chính sách rỗng: Optional empty, lỗi, hay mặc định |
| `[0]` | Trung bình thực sự bằng `0.0` nhưng có một phần tử |
| `[-5, 5]` | Trung bình `0.0` từ hai phần tử, không phải tập rỗng |
| `[1, 2]` | Trung bình `1.5`; tránh lỗi chia nguyên |
| `[1, 2, 2]` với BigDecimal | Có chính sách rounding hợp lệ, ví dụ scale 2 cho `1.67` |
| Dữ liệu chứa `null` | Chính sách chấp nhận, từ chối hay bỏ qua rõ ràng |
| Dữ liệu chứa `Double.NaN` hoặc vô cực | Không nhầm số không hữu hạn với Optional rỗng |
| Chỉ có nhóm A | Không giả định nhóm B có average thật 0 |
| Danh sách rất lớn | Chú ý tràn tổng nguyên, mất precision khi dùng double |

Có thể unit test hàm `OptionalDouble` bằng `isEmpty()` cho trường hợp rỗng và `orElseThrow()` cho trường hợp có dữ liệu; không nhất thiết xây dựng stream ẩn bên trong test.

## 13. Các lỗi phổ biến

| Lỗi | Tác hại | Hướng sửa |
| --- | --- | --- |
| Gọi `average().getAsDouble()` khi rỗng | `NoSuchElementException` | Kiểm tra Optional hoặc `orElseThrow` có ngữ cảnh |
| Dùng `orElse(0.0)` mọi nơi | Nhầm “chưa có mẫu” với “trung bình 0” | Giữ Optional/count trừ khi nghiệp vụ có mặc định |
| Cho rằng `Collectors.averagingInt` trả Optional | Hiểu sai hợp đồng API | Kiểm tra count hoặc dùng primitive stream |
| Đọc `summaryStatistics.getAverage()` khi count=0 như giá trị đo được | Báo cáo sai | Kiểm tra `getCount()` |
| Viết `sum / count` bằng số nguyên | Mất chữ số thập phân | Ép kiểu trước phép chia |
| Dùng lại một stream sau terminal operation | Stream đã tiêu thụ | Tạo stream mới hoặc summary một lượt |
| Đưa danh sách rỗng vào phép chia BigDecimal | Chia cho 0 | Guard count > 0 trước khi divide |
| Không xác định scale/rounding cho BigDecimal | Có thể ném `ArithmeticException` vì thương vô hạn | Khai báo chính sách decimal |
| Coi `Double.NaN` là thiếu dữ liệu | Sai trạng thái | Phân biệt `isPresent` với `Double.isFinite` |
| Lấy trung bình các trung bình mà quên count từng nhóm | Kết quả toàn bộ sai | Tính tổng và count có trọng số |

## 14. Tự kiểm tra

1. **`IntStream.empty().average()` trả gì?** `OptionalDouble.empty()`; `average()` không tự ném lỗi.
2. **Có phân biệt `OptionalDouble.empty()` và `OptionalDouble.of(0.0)` không?** Có; một bên thiếu dữ liệu, bên kia có giá trị 0.0.
3. **`Stream.<Integer>empty().collect(Collectors.averagingInt(Integer::intValue))` trả gì?** `0.0` theo hợp đồng collector.
4. **`IntStream.empty().summaryStatistics().getAverage()` trả gì?** `0.0`; cần kiểm tra `getCount() == 0` trước khi diễn giải.
5. **Nếu phải có ít nhất một điểm, nên xử lý ra sao?** Chọn `average().orElseThrow(() -> new IllegalArgumentException(...))` hoặc kiểm tra dữ liệu đầu vào.
6. **Nếu chưa có điểm là trạng thái hợp lệ?** Trả Optional hoặc cấu trúc có count; hiển thị “Chưa có dữ liệu”.
7. **Có dùng cùng một stream để `count()` rồi `average()` được không?** Không; terminal operation tiêu thụ stream.
8. **Kết quả average là NaN có phải nghĩa là Optional rỗng?** Không; Optional có thể chứa giá trị NaN.
9. **Vì sao `BigDecimal` chia trung bình có thể cần rounding?** Vì thương như 5/3 có vô hạn chữ số thập phân, nên phải quyết định scale/rounding nếu cho phép làm tròn.

## 15. Kết luận

Khi dùng `average` trong Java, vấn đề quan trọng không chỉ là chia tổng cho số lượng, mà còn là **định nghĩa hành vi khi không có phần tử**. `IntStream`, `LongStream` và `DoubleStream` trả `OptionalDouble` để giữ trạng thái thiếu; `Collectors.averaging*` và `SummaryStatistics.getAverage()` trả `0.0` khi rỗng, vì đó là hợp đồng API, không phải khẳng định trung bình toán học của tập rỗng là 0.

Hãy chọn chính sách cụ thể: giữ Optional khi thiếu dữ liệu là bình thường, ném lỗi có ngữ cảnh nếu input bắt buộc không rỗng, hoặc dùng mặc định chỉ khi có quy tắc nghiệp vụ rõ ràng. Với dữ liệu thực tế, kiểm tra thêm `count`, độ chính xác `double`, giá trị không hữu hạn, và rounding của `BigDecimal` để kết quả có ý nghĩa và đáng tin.
