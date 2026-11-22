# Xử lý tổng và trung bình trên nguồn rỗng

Trong Java Stream API, một pipeline có thể không tạo ra phần tử nào: danh sách đầu vào vốn rỗng, `filter` loại toàn bộ bản ghi, hoặc bước biến đổi chỉ giữ những giá trị hợp lệ nhưng không tìm được giá trị phù hợp. Khi đó, **tổng** và **trung bình** không có cùng ý nghĩa hay kiểu kết quả. Với các Stream số nguyên thủy, `sum()` trả giá trị **0** trên nguồn rỗng, còn `average()` trả **`OptionalDouble.empty()`**. Biết rõ sự khác biệt này giúp tránh phép chia cho 0 và tránh hiểu nhầm “không có dữ liệu” thành “trung bình thực sự bằng 0”.

Bài thuộc chương **Độ chính xác khi tổng hợp số** của module **JAVA_STREAM_API**. Kiến thức này nối tiếp các pipeline khai báo, lazy, `filter`, `map`, `reduce`, `collect` và hữu ích khi tổng hợp theo nhóm, thiết kế collector tùy chỉnh, xử lý song song hoặc kiểm soát sai số, tràn số và tài nguyên. Các ví dụ chính sử dụng Java 8 trở lên, trừ khi có ghi rõ phiên bản khác.

## 1. Vì sao nguồn rỗng là trường hợp bắt buộc phải xử lý?

Giả sử ứng dụng có danh sách hóa đơn nhưng hôm nay **không có hóa đơn nào đã thanh toán**. Hai câu hỏi nghiệp vụ nghe gần nhau:

- “Tổng số tiền đã thanh toán hôm nay?”: thông thường là **0 đồng**, vì không có giao dịch đóng góp vào tổng.
- “Giá trị trung bình của mỗi hóa đơn đã thanh toán hôm nay?”: **chưa xác định**, vì không tồn tại hóa đơn để tính trung bình.

Trung bình số học của `n` giá trị là:

\[
\overline{x}=\frac{x_1+x_2+\dots+x_n}{n},\quad n>0
\]

Khi `n = 0`, mẫu số bằng 0; không thể suy ra giá trị trung bình chỉ bằng cách lấy tổng bằng 0. Java phản ánh điều này bằng hai loại API:

| Phép toán | Nguồn không rỗng | Nguồn rỗng |
|---|---|---|
| `IntStream.sum()` | Tổng kiểu `int` | `0` |
| `LongStream.sum()` | Tổng kiểu `long` | `0L` |
| `DoubleStream.sum()` | Tổng kiểu `double` | `0.0` |
| `IntStream.average()` | `OptionalDouble` có giá trị trung bình | `OptionalDouble.empty()` |
| `LongStream.average()` | `OptionalDouble` có giá trị trung bình | `OptionalDouble.empty()` |
| `DoubleStream.average()` | `OptionalDouble` có giá trị trung bình | `OptionalDouble.empty()` |
| `IntStream.count()` (tương tự `LongStream`, `DoubleStream`) | Số phần tử | `0L` |

**Điểm quan trọng:** Kết quả tổng bằng 0 **không nói được** nguồn là rỗng. Một nguồn có phần tử `0`, hoặc các giá trị `-5` và `5`, cũng có thể có tổng bằng 0.

## 2. Tổng: vì sao sum() trả 0 trên Stream rỗng?

Phép cộng có **phần tử đơn vị** là `0`: với mọi số `a`, `a + 0 = 0 + a = a`. Do đó, tổng trên không phần tử có thể được định nghĩa hợp lý là phần tử đơn vị, tương tự `reduce(0, ...)`.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

System.out.println(IntStream.empty().sum());    // 0
System.out.println(LongStream.empty().sum());   // 0
System.out.println(DoubleStream.empty().sum()); // 0.0
System.out.println(IntStream.empty().count());  // 0
```

Nếu đã có danh sách số, các Stream nguyên thủy hỗ trợ tổng trực tiếp:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> amounts = Arrays.asList(100, 200, -300);

int total = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 0, dù có ba phần tử.
```

### 2.1. Lọc hết phần tử cũng tạo ra nguồn rỗng cho terminal operation

```java
List<Integer> amounts = Arrays.asList(100, 200, 300);

int emptySum = amounts.stream()
        .filter(value -> value < 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(emptySum); // 0
```

Các thao tác trung gian như `filter` thường **lazy**. Việc không có phần tử sau lọc chỉ bộc lộ khi `sum` thực sự duyệt pipeline; không có ngoại lệ chỉ vì kết quả lọc rỗng.

### 2.2. mapToInt/mapToLong trước khi sum

Đối với `Stream<Order>` hoặc `Stream<Product>`, phải ánh xạ đối tượng sang số:

```java
long totalCents = orders.stream()
        .filter(Order::isPaid)
        .mapToLong(Order::getAmountCents)
        .sum();
```

Đoạn minh họa giả định tồn tại kiểu `Order` với `isPaid()` trả `boolean` và `getAmountCents()` trả `long`. Sau lọc, nếu không có đơn đã thanh toán, `totalCents` bằng `0L`.

Không được mặc định tổng số nguyên luôn an toàn về độ lớn: `IntStream.sum()` có thể **tràn `int`**, còn `LongStream.sum()` có thể **tràn `long`** khi tổng thực vượt miền giá trị. Xem thêm phần về độ chính xác bên dưới.

## 3. Trung bình: OptionalDouble biểu diễn khả năng thiếu kết quả

Trung bình của các Stream nguyên thủy đều trả về `OptionalDouble`:

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble averageOfThree = IntStream.of(10, 20, 30)
        .average();
System.out.println(averageOfThree); // OptionalDouble[20.0]

OptionalDouble averageOfNothing = IntStream.empty()
        .average();
System.out.println(averageOfNothing); // OptionalDouble.empty
```

Không truy cập `getAsDouble()` nếu chưa xác nhận có giá trị:

```java
OptionalDouble average = IntStream.empty().average();

// SAI: ném NoSuchElementException khi OptionalDouble rỗng.
// double value = average.getAsDouble();

if (average.isPresent()) {
    System.out.println("Trung bình = " + average.getAsDouble());
} else {
    System.out.println("Chưa có dữ liệu để tính trung bình");
}
```

Có thể xử lý gọn hơn bằng `ifPresent`, `orElse` hoặc `orElseGet`:

```java
OptionalDouble average = IntStream.of(10, 20).average();

average.ifPresent(value -> System.out.println("TB = " + value));

double displayValue = average.orElse(0.0);
System.out.println(displayValue); // 15.0
```

Tuy nhiên, chọn `orElse(0.0)` là **chính sách của ứng dụng**, không phải định nghĩa toán học của trung bình rỗng. Chỉ dùng mặc định 0 khi người dùng hoặc nghiệp vụ **chấp nhận** đồng nhất “không có dữ liệu” với số hiển thị 0.

### 3.1. Phân biệt ba trường hợp

| Dữ liệu | `sum()` | `average()` | Diễn giải |
|---|---:|---|---|
| `[]` | `0` | Rỗng | Chưa có phép đo |
| `[0]` | `0` | Có giá trị `0.0` | Một phép đo thực sự bằng 0 |
| `[-5, 5]` | `0` | Có giá trị `0.0` | Hai phép đo triệt tiêu nhau |

Nếu hệ thống cần báo cáo tình trạng **“có dữ liệu hay chưa”**, hãy giữ `OptionalDouble` hoặc cặp `count` và `sum`, thay vì chỉ lưu một số `double`.

## 4. reduce có identity và không có identity

`sum()` là công cụ chuyên dụng, nhưng `reduce` giúp hiểu rõ vì sao một phép tổng có thể trả 0 trên nguồn rỗng.

### 4.1. Có identity: luôn có kết quả

```java
import java.util.stream.Stream;

int total = Stream.<Integer>empty()
        .reduce(0, Integer::sum);

System.out.println(total); // 0
```

Phiên bản `reduce(identity, accumulator)` trả chính `identity` khi không có phần tử. Với phép cộng, identity phải là `0`. Dùng `100` làm giá trị khởi tạo sẽ biến tổng rỗng thành `100`, và có thể còn làm sai phép tổng trong xử lý song song nếu không thỏa hợp đồng phép gộp.

### 4.2. Không có identity: trả Optional

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> totalIfPresent = Stream.<Integer>empty()
        .reduce(Integer::sum);

System.out.println(totalIfPresent); // Optional.empty
```

Với nguồn có dữ liệu:

```java
Optional<Integer> total = Stream.of(4, -4)
        .reduce(Integer::sum);

System.out.println(total); // Optional[0]
```

`reduce(BinaryOperator<T>)` phù hợp khi muốn phân biệt tổng của **không phần tử** với tổng của **một tập phần tử có giá trị cộng lại bằng 0**. Ngược lại, nếu nghiệp vụ định nghĩa tổng rỗng bằng 0 và không cần phân biệt, `sum()` hoặc `reduce(0, ...)` là lựa chọn rõ ràng.

Chú ý: phép gộp trong `reduce` phải thỏa tính kết hợp nhóm (*associativity*) nếu muốn kết quả đúng khi Stream chia việc song song. Với số dấu phẩy động, thứ tự cộng khác nhau có thể tạo sai số khác nhau; không nên đồng nhất “đúng về mặt công thức” với “bit kết quả luôn giống nhau”.

## 5. Collectors có thể xử lý nguồn rỗng khác average()

Trong `collect`, Java cung cấp `Collectors.summingInt`, `summingLong`, `summingDouble`, `averagingInt`, `averagingLong` và `averagingDouble`. Những collector này có hợp đồng trả về giá trị số cụ thể, **không trả OptionalDouble** cho phép trung bình.

```java
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> empty = Collections.emptyList();

int sum = empty.stream()
        .collect(Collectors.summingInt(Integer::intValue));

double avg = empty.stream()
        .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(sum); // 0
System.out.println(avg); // 0.0
```

Đây là sự khác biệt quan trọng:

| Cách tính | Nguồn rỗng | Có phân biệt “không có dữ liệu” không? |
|---|---|---|
| `IntStream.empty().sum()` | `0` | Không, nếu chỉ xét số tổng |
| `IntStream.empty().average()` | `OptionalDouble.empty()` | Có |
| `empty.stream().collect(summingInt(...))` | `0` | Không, nếu chỉ xét số tổng |
| `empty.stream().collect(averagingInt(...))` | `0.0` | Không, nếu chỉ xét số trung bình |
| `empty.stream().reduce(Integer::sum)` | `Optional.empty()` | Có |
| `empty.stream().count()` | `0L` | Có thể dùng để xác định nguồn rỗng |

**Không thay `average()` bằng `Collectors.averagingInt` mà kỳ vọng cả hai cùng trả “không xác định” trên nguồn rỗng.** Khi cần sự phân biệt, lưu thêm số lượng phần tử hoặc áp dụng collector tự thiết kế để trả một kiểu kết quả có cờ dữ liệu.

### 5.1. summaryStatistics: nhận count, sum và average cùng lúc

Nếu báo cáo cần nhiều đại lượng thống kê, có thể dùng `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.empty()
        .summaryStatistics();

System.out.println(stats.getCount());   // 0
System.out.println(stats.getSum());     // 0
System.out.println(stats.getAverage()); // 0.0
```

`getAverage()` của statistics trả `0.0` khi `count == 0`. Vì vậy, muốn biểu diễn **không có trung bình** thì kiểm tra số lượng:

```java
import java.util.OptionalDouble;

OptionalDouble avgFromStats = stats.getCount() == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of(stats.getAverage());
```

Với `IntSummaryStatistics` rỗng, `getMin()` ban đầu là `Integer.MAX_VALUE` và `getMax()` là `Integer.MIN_VALUE`; **không** nên hiển thị chúng như cực trị thực tế khi `getCount() == 0`. Các kiểu `LongSummaryStatistics`, `DoubleSummaryStatistics` cũng cần được xử lý tương tự theo hợp đồng tương ứng.

Ưu điểm của statistics là đếm và tích lũy trong **một lần thu thập**. Điều này đặc biệt hữu ích với nguồn Stream chỉ tiêu thụ được một lần; không cần tạo cùng một Stream rồi gọi `sum()` sau đó `average()` trên chính đối tượng Stream đã dùng.

## 6. Ví dụ Java 8 hoàn chỉnh: hóa đơn không có bản ghi khớp

Ví dụ sau có ba trạng thái đơn hàng và một trường `amountCents` kiểu `long`, đại diện số tiền ở đơn vị nhỏ nhất. Ứng dụng tính tổng và trung bình của đơn đã thanh toán, sau đó thử tính trên một trạng thái **không tồn tại** trong dữ liệu.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

public class EmptyAggregationDemo {
    static final class Order {
        private final String status;
        private final long amountCents;

        Order(String status, long amountCents) {
            this.status = status;
            this.amountCents = amountCents;
        }

        String getStatus() {
            return status;
        }

        long getAmountCents() {
            return amountCents;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("PAID", 10_000L),
                new Order("PENDING", 50_000L),
                new Order("PAID", 30_000L)
        );

        // Mỗi terminal operation cần một Stream mới từ danh sách.
        long paidTotal = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .sum();

        OptionalDouble paidAverage = orders.stream()
                .filter(order -> "PAID".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .average();

        System.out.println("Tổng PAID: " + paidTotal); // 40000
        System.out.println("TB PAID: " + paidAverage.orElse(-1)); // 20000.0

        // Không có đơn REFUNDED trong danh sách.
        long refundedTotal = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .sum();

        OptionalDouble refundedAverage = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .mapToLong(Order::getAmountCents)
                .average();

        System.out.println("Tổng REFUNDED: " + refundedTotal); // 0
        System.out.println("Có TB REFUNDED? " + refundedAverage.isPresent());
        // false

        // Nếu cần count/sum/average cùng nhau, thu thập một lần.
        LongSummaryStatistics stats = orders.stream()
                .filter(order -> "REFUNDED".equals(order.getStatus()))
                .collect(Collectors.summarizingLong(Order::getAmountCents));

        System.out.println("Số REFUNDED: " + stats.getCount()); // 0
        System.out.println("Tổng REFUNDED: " + stats.getSum()); // 0

        if (stats.getCount() == 0) {
            System.out.println("TB REFUNDED: chưa có dữ liệu");
        } else {
            System.out.println("TB REFUNDED: " + stats.getAverage());
        }
    }
}
```

Điểm cần rút ra: cùng một tập đơn có thể cho **tổng bằng 0** và **trung bình rỗng** trong nhóm `REFUNDED`. Sử dụng `"REFUNDED".equals(order.getStatus())` còn tránh lỗi dereference nếu `status` của một đơn có thể null; ví dụ giả định chính phần tử `Order` không null.

Nếu cần báo cáo tổng và trung bình trên **một nguồn chỉ tiêu thụ một lần** (ví dụ nguồn đọc dữ liệu), hãy chọn `summarizingLong` hoặc collector khác giữ đủ thống kê, thay vì tạo Stream một lần rồi cố dùng lại sau khi đã gọi terminal operation.

## 7. Nhóm rỗng: groupingBy và partitioningBy không giống nhau

Trong tổng hợp theo nhóm, “nhóm không có bản ghi” có thể biểu diễn bằng **không tồn tại khóa** hoặc **có khóa nhưng kết quả mặc định**. Cần phân biệt hai trường hợp khi thiết kế báo cáo.

### 7.1. groupingBy không tự tạo nhóm vắng mặt

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> statuses = Arrays.asList("PAID", "PAID", "PENDING");

Map<String, Long> counts = statuses.stream()
        .collect(Collectors.groupingBy(
                status -> status,
                Collectors.counting()));

System.out.println(counts.get("PAID"));      // 2
System.out.println(counts.containsKey("REFUNDED")); // false
```

Không có phần tử thuộc nhóm `REFUNDED` thì `groupingBy` không tự thêm khóa này. Nếu yêu cầu báo cáo phải luôn có đủ các trạng thái quy định, lớp báo cáo cần chủ động điền các nhóm còn thiếu, phân biệt được **không phát sinh bản ghi** với **trung bình 0 từ dữ liệu thực tế**.

### 7.2. partitioningBy luôn có hai khóa boolean

```java
import java.util.Collections;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Double> averages = Collections.<Integer>emptyList()
        .stream()
        .collect(Collectors.partitioningBy(
                number -> number >= 0,
                Collectors.averagingInt(Integer::intValue)));

System.out.println(averages.get(true));  // 0.0
System.out.println(averages.get(false)); // 0.0
```

`partitioningBy` tạo hai nhóm `true` và `false` ngay cả khi đầu vào hoàn toàn rỗng; với downstream collector `averagingInt`, cả hai nhận kết quả `0.0`. **Đây là giá trị mặc định của collector**, không chứng minh mỗi nhóm có một phép đo bằng 0. Có thể thu thập thêm `count` cho từng nhóm để xác định trường hợp rỗng trước khi trình bày.

## 8. Tính trung bình thủ công: bảo vệ phép chia cho 0

Một cách viết dễ gây lỗi là:

```java
long sum = values.stream().mapToLong(Long::longValue).sum();
long count = values.size();

// SAI nếu count == 0: với phép chia long/long, gây ArithmeticException.
// long mean = sum / count;
```

Ngay cả khi `count > 0`, `sum / count` với hai toán hạng nguyên **cắt phần thập phân**, không cho trung bình chính xác dạng số thực. Nếu dữ liệu phù hợp với tính toán dấu phẩy động, dùng:

```java
OptionalDouble average = values.stream()
        .mapToLong(Long::longValue)
        .average();
```

Nếu cần bảo toàn sự vắng mặt bằng tính toán thủ công:

```java
long count = values.size();
long sum = values.stream().mapToLong(Long::longValue).sum();

OptionalDouble average = count == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of((double) sum / count);
```

Hai đoạn giả định `values` là `List<Long>` chứa các phần tử không null, và `sum` không tràn `long`. Phương thức `average()` của Stream được khuyến nghị cho bài toán trung bình thông thường; ví dụ chia thủ công chỉ minh họa cách tách **quy tắc rỗng** khỏi **phép tính**.

### 8.1. Tránh dùng NaN làm nhãn trống một cách ngầm định

Phép toán `0.0 / 0.0` ở kiểu `double` cho `NaN`, không phải ngoại lệ `ArithmeticException`. Tuy nhiên, `NaN` không phải cách thay thế có cùng hợp đồng với `OptionalDouble.empty()`: `NaN` cũng có thể xuất hiện vì dữ liệu đầu vào không hợp lệ hoặc phép tính với vô cực. Nếu cần phân biệt nguồn rỗng với dữ liệu chứa `NaN`, hãy kiểm tra `count` hay giữ `OptionalDouble`.

## 9. Độ chính xác: có dữ liệu chưa chắc đã có trung bình hợp lệ

`OptionalDouble.isPresent()` chỉ cho biết **có phần tử được đưa vào phép tính**; nó không tự khẳng định trung bình hữu hạn, chính xác tuyệt đối hay hợp lệ theo nghiệp vụ.

### 9.1. Sai số dấu phẩy động

`double` sử dụng biểu diễn nhị phân hữu hạn, nên các số thập phân như `0.1` và `0.2` thường không được lưu chính xác tuyệt đối.

```java
import java.util.stream.DoubleStream;

double sum = DoubleStream.of(0.1, 0.2).sum();
OptionalDouble average = DoubleStream.of(0.1, 0.2).average();
```

Không so sánh số thực bằng cách đòi bit kết quả phải khớp với biểu diễn thập phân lý tưởng. `DoubleStream.sum()` có thể sử dụng kỹ thuật cộng bù để tăng độ chính xác, nhưng không có nghĩa mọi phép tính dấu phẩy động đều chính xác tuyệt đối hoặc thứ tự cộng ở các cấu hình song song luôn tạo kết quả giống hệt.

### 9.2. NaN và vô cực

`DoubleStream.average()` trả `OptionalDouble.empty()` trên nguồn **rỗng**. Nếu nguồn không rỗng nhưng có `NaN`, kết quả có thể là `OptionalDouble` **có giá trị `NaN`**; hai trạng thái phải được phân biệt.

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

OptionalDouble result = DoubleStream.of(Double.NaN, 10.0)
        .average();

System.out.println(result.isPresent()); // true
System.out.println(Double.isNaN(result.getAsDouble())); // true
```

Nếu yêu cầu chỉ tổng hợp số hữu hạn, có thể lọc có chủ đích:

```java
OptionalDouble finiteAverage = DoubleStream
        .of(10.0, Double.NaN, Double.POSITIVE_INFINITY, 20.0)
        .filter(Double::isFinite) // Java 8+
        .average();

System.out.println(finiteAverage.orElse(Double.NaN)); // 15.0
```

Lọc giá trị không hợp lệ có nghĩa thay đổi tập dữ liệu dùng để tính trung bình; hệ thống có thể cần ghi nhận số bản ghi bị loại để người xem hiểu đầy đủ chất lượng dữ liệu.

### 9.3. Tràn số nguyên

`int` và `long` không tự nâng kích thước khi tổng vượt phạm vi. Ví dụ:

```java
import java.util.stream.IntStream;

int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(overflowed); // -2147483648 (tràn int)
```

Nếu giá trị đầu vào là `int` và tổng có thể vượt `int`, chọn `mapToLong` để mở rộng phạm vi kết quả. `IntStream.mapToLong` yêu cầu `IntToLongFunction` nhận `int`; dùng lambda chuyển kiểu nguyên thủy:

```java
long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(value -> (long) value)
        .sum();
System.out.println(widened); // 2147483648
```

Phép chuyển sang `long` giải quyết trường hợp trên nhưng **không** loại bỏ khả năng tràn `long`. Với các tổng có thể vượt cả phạm vi `long`, dùng `BigInteger` hoặc `BigDecimal` theo miền dữ liệu, đồng thời chọn quy tắc làm tròn thích hợp cho trung bình.

## 10. Số tiền: tổng chính xác bằng BigDecimal, trung bình chỉ khi count > 0

Với tiền tệ hoặc các giá trị cần kiểm soát làm tròn, `BigDecimal` giúp biểu diễn số thập phân chính xác theo giá trị đã nhập. Phép tổng có thể dùng `reduce(BigDecimal.ZERO, BigDecimal::add)`, còn trung bình chỉ được chia khi có phần tử.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

List<BigDecimal> amounts = Arrays.asList(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"));

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

Optional<BigDecimal> average = amounts.isEmpty()
        ? Optional.empty()
        : Optional.of(total.divide(
                BigDecimal.valueOf(amounts.size()),
                2,
                RoundingMode.HALF_UP));

System.out.println(total);   // 0.30
System.out.println(average); // Optional[0.15]

List<BigDecimal> none = Collections.emptyList();
BigDecimal emptyTotal = none.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
Optional<BigDecimal> emptyAverage = none.isEmpty()
        ? Optional.empty()
        : Optional.of(emptyTotal.divide(
                BigDecimal.valueOf(none.size()),
                2,
                RoundingMode.HALF_UP));

System.out.println(emptyTotal);   // 0
System.out.println(emptyAverage); // Optional.empty
```

Ví dụ dựa trên danh sách không chứa `null`. Nếu số phần tử được dùng để tính tổng đến từ pipeline lọc, phải đếm **chính các phần tử đã qua lọc**, không dùng `amounts.size()` của danh sách gốc. Nếu nguồn chỉ có thể tiêu thụ một lần, hãy thu thập tổng và count bằng một collector phù hợp trước khi tính trung bình.

Nên dùng `new BigDecimal("0.10")` thay vì `new BigDecimal(0.10)` để tránh đưa vào sai số do biểu diễn `double` trước khi tạo `BigDecimal`.

## 11. Thiết kế chính sách cho nguồn rỗng theo nghiệp vụ

Một API trả về `OptionalDouble.empty()` giúp **bảo toàn thông tin**; nơi trình bày dữ liệu mới quyết định nên hiển thị gì khi thiếu kết quả.

| Yêu cầu | Chính sách đề xuất |
|---|---|
| Tổng doanh thu của ngày chưa có giao dịch | Trả `0` ở đơn vị tiền tệ tương ứng |
| Trung bình hóa đơn của ngày chưa có giao dịch | Giữ “không có trung bình”; hiển thị “Chưa có dữ liệu” |
| Dashboard bắt buộc chỉ hiển thị số | Có thể dùng `orElse(0)` nếu quy tắc nghiệp vụ chấp nhận; nên giữ thêm `count` hoặc cờ rỗng |
| Giá trị trung bình phải tồn tại để dùng trong bước sau | Kiểm tra dữ liệu; từ chối hoặc xử lý bằng ngoại lệ nghiệp vụ phù hợp |
| Tính trung bình theo nhóm | Kiểm tra nhóm có tồn tại và số bản ghi từng nhóm; tránh hiểu nhầm `averaging...() == 0.0` |
| Báo cáo tài chính cần tổng và trung bình chính xác | Dùng `BigDecimal`/đơn vị nhỏ nhất và xác định chế độ làm tròn |

Không có một giá trị mặc định đúng cho mọi hệ thống. Điều cần nhất quán là **tách trạng thái dữ liệu rỗng khỏi giá trị số 0** khi nghiệp vụ quan tâm đến sự khác biệt ấy.

## 12. Bài tập thực hành có đáp án

### Bài 1: Kết quả tổng và trung bình

```java
int sum = java.util.stream.IntStream.of(4, -4).sum();
java.util.OptionalDouble avg =
        java.util.stream.IntStream.of(4, -4).average();
```

**Đáp án:** `sum == 0`, `avg.isPresent() == true` và `avg.getAsDouble() == 0.0`. Có hai số thật sự nên trung bình xác định.

### Bài 2: Nguồn bị filter hết

```java
java.util.OptionalDouble avg =
        java.util.stream.IntStream.of(1, 3, 5)
                .filter(n -> n % 2 == 0)
                .average();
```

**Đáp án:** `OptionalDouble.empty()`, vì không có số chẵn nào sau `filter`.

### Bài 3: So sánh hai cách lấy trung bình

```java
List<Integer> empty = java.util.Collections.emptyList();

java.util.OptionalDouble a =
        empty.stream().mapToInt(Integer::intValue).average();

double b = empty.stream().collect(
        java.util.stream.Collectors.averagingInt(Integer::intValue));
```

**Đáp án:** `a` rỗng; `b == 0.0`. Không thể dựa riêng vào `b` để phân biệt nguồn rỗng với nguồn chứa một số `0`.

### Bài 4: Giá trị summaryStatistics ban đầu

```java
java.util.IntSummaryStatistics stats =
        java.util.stream.IntStream.empty().summaryStatistics();
```

**Đáp án:** `stats.getCount() == 0`, `stats.getSum() == 0`, `stats.getAverage() == 0.0`. Không hiển thị `stats.getMin()` và `stats.getMax()` như cực trị có ý nghĩa khi count bằng 0.

### Bài 5: Thiết kế kết quả báo cáo

Yêu cầu API báo cáo trả tổng tiền, số đơn và trung bình tiền đơn; khi không có đơn thì giữ nguyên tín hiệu “chưa có trung bình”. Nên trả ba `double`, hay trả count, tổng và một giá trị có thể vắng mặt?

**Đáp án:** Trả **count + total + trung bình tùy chọn** (ví dụ `OptionalDouble` nếu sai số chấp nhận được, hoặc `Optional<BigDecimal>` cho tiền tệ). Khi count bằng 0, tổng có thể là 0 nhưng trung bình phải được đánh dấu vắng mặt nếu đó là yêu cầu nghiệp vụ.

## 13. Ghi nhớ

`sum()` trên `IntStream`, `LongStream` và `DoubleStream` rỗng trả về **0**, còn `average()` trả **`OptionalDouble.empty()`**. `reduce` có identity trả identity trên nguồn rỗng, trong khi `reduce` không identity trả `Optional` rỗng. Các collector `averagingInt`/`averagingLong`/`averagingDouble` và statistics thường đưa ra `0.0` khi không có phần tử, nên cần `count` nếu muốn phân biệt thiếu dữ liệu với trung bình thật sự bằng 0. Khi tính tổng và trung bình, hãy luôn xét ba yếu tố: **nguồn có phần tử hay không, miền giá trị có thể tràn hay không và kiểu số có đáp ứng yêu cầu độ chính xác hay không**.
