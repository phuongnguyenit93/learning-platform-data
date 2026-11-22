# Tính trung bình và thống kê bằng `averaging` và `summarizing`

## 1. Bài toán: cần một con số hay cả bộ thống kê?

Trong module **JAVA_STREAM_API**, một pipeline khai báo thường dùng `filter`, `map` và `flatMap` để chọn hoặc biến đổi dữ liệu, sau đó dùng `collect` để tổng hợp. Hai nhóm collector đặc biệt hữu ích khi xử lý dữ liệu số là:

- **`averagingInt`, `averagingLong`, `averagingDouble`**: tính **trung bình cộng**, trả một giá trị kiểu `Double`.
- **`summarizingInt`, `summarizingLong`, `summarizingDouble`**: tạo **một đối tượng thống kê** chứa số mẫu, tổng, cực tiểu, cực đại và trung bình.

Ví dụ, với bốn đơn hàng đã thanh toán, bộ phận vận hành có thể cần:

1. Số lượng sản phẩm trung bình trong một đơn.
2. Doanh thu trung bình của một đơn.
3. Đồng thời biết số đơn, doanh thu thấp nhất, cao nhất và tổng doanh thu.
4. Thống kê tương tự theo **từng vùng** bằng `groupingBy`.

`averaging` phù hợp khi chỉ cần **một số trung bình**. `summarizing` phù hợp khi cần **nhiều chỉ số cùng lúc**, thường trong một lần duyệt pipeline.

Mục tiêu của bài:

- Đọc chữ ký và kiểu kết quả của sáu collector.
- Phân biệt `Collector<T, ?, Double>` với `Collector<T, ?, IntSummaryStatistics>` (và các biến thể khác).
- Kết hợp collector thống kê làm **downstream** của `groupingBy`, `filtering` và `collectingAndThen`.
- Xác định hợp đồng cho **nguồn rỗng**, giá trị `0` hợp lệ và phép chia trung bình.
- Kiểm soát rủi ro **tràn số**, **sai số `double`**, `NaN`, nguồn `null` và xử lý song song.
- Viết kiểm thử kết quả nghiệp vụ, không dựa vào thứ tự gọi lambda.

Các ví dụ đầy đủ trong bài sử dụng **JDK 17 trở lên** để dùng `record` và `Stream.toList()`. Các collector `averaging*` và `summarizing*` đã có từ Java 8; những API mới hơn sẽ được ghi chú khi xuất hiện.

## 2. Đọc chữ ký của sáu collector

`Collectors` cung cấp những factory method sau (lược bớt chú thích để tập trung vào generic):

```java
<T> Collector<T, ?, Double> averagingInt(
    ToIntFunction<? super T> mapper
)

<T> Collector<T, ?, Double> averagingLong(
    ToLongFunction<? super T> mapper
)

<T> Collector<T, ?, Double> averagingDouble(
    ToDoubleFunction<? super T> mapper
)

<T> Collector<T, ?, IntSummaryStatistics> summarizingInt(
    ToIntFunction<? super T> mapper
)

<T> Collector<T, ?, LongSummaryStatistics> summarizingLong(
    ToLongFunction<? super T> mapper
)

<T> Collector<T, ?, DoubleSummaryStatistics> summarizingDouble(
    ToDoubleFunction<? super T> mapper
)
```

Ở đây:

- `T` là **kiểu phần tử của stream nguồn**, ví dụ `Order`.
- `mapper` trích một giá trị nguyên thủy `int`, `long` hoặc `double` từ mỗi `T`.
- `?` đại diện cho **kiểu trạng thái tích lũy `A`** mà collector giấu khỏi người gọi; nó không có nghĩa collector không cần trạng thái.
- Tham số kiểu thứ ba, **`R`**, là kết quả của `collect`: `Double` hoặc một `*SummaryStatistics`.

| Collector | Mapper nhận `T` và trả | Kiểu kết quả `R` | Công dụng |
| --- | --- | --- | --- |
| `averagingInt` | `int` | `Double` | Trung bình các số nguyên |
| `averagingLong` | `long` | `Double` | Trung bình các số nguyên dài |
| `averagingDouble` | `double` | `Double` | Trung bình các số thực |
| `summarizingInt` | `int` | `IntSummaryStatistics` | Đếm, tổng, min, max, average |
| `summarizingLong` | `long` | `LongSummaryStatistics` | Đếm, tổng, min, max, average |
| `summarizingDouble` | `double` | `DoubleSummaryStatistics` | Đếm, tổng, min, max, average |

Ví dụ đọc kiểu từ ngoài vào:

```java
// Giả sử orders là List<Order>, Order.amountVnd() trả long.
Double averageAmount = orders.stream()
    .collect(Collectors.averagingLong(Order::amountVnd));

LongSummaryStatistics amountStats = orders.stream()
    .collect(Collectors.summarizingLong(Order::amountVnd));
```

Đầu vào vẫn là `Stream<Order>`, **không phải `LongStream`**. Collector dùng `ToLongFunction<Order>` để trích số tiền nguyên thủy từ từng đơn hàng.

**Phân biệt:** `Stream.collect(Collector)` là terminal operation. Sau khi gọi, stream đã bị tiêu thụ; muốn tính một kết quả khác từ `List<Order>`, tạo stream mới bằng `orders.stream()`. Nếu muốn nhiều số đo trong **một pipeline**, `summarizing` thường giúp tránh lặp lại việc duyệt nguồn.

## 3. `averagingInt`, `averagingLong` và `averagingDouble`

### 3.1. `averagingInt`: số nguyên đầu vào, `Double` đầu ra

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> quantities = List.of(1, 2, 3, 4);

double average = quantities.stream()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(average); // 2.5
```

Collector tích lũy các giá trị nguyên rồi trả **giá trị trung bình kiểu `Double`**. Đó không phải phép chia nguyên `int / int`, nên kết quả `2.5` không bị cắt thành `2`.

Nếu nguồn là một `Stream<Order>`, không cần boxing số lượng ra `Integer` rồi mới tính:

```java
double averageQuantity = orders.stream()
    .collect(Collectors.averagingInt(Order::quantity));
```

### 3.2. `averagingLong`: trung bình các giá trị `long`

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> amounts = List.of(100L, 200L, 300L);

double average = amounts.stream()
    .collect(Collectors.averagingLong(Long::longValue));

System.out.println(average); // 200.0
```

Kiểu đầu vào của mapper là `long`, nhưng kiểu kết quả vẫn là `Double`, **không phải `Long`**. Nếu dữ liệu là số tiền nguyên đơn vị nhỏ nhất và quy tắc nghiệp vụ không cho phép sai số, không nên xem `Double` là định dạng tiền tệ chính xác tuyệt đối.

### 3.3. `averagingDouble`: trung bình giá trị số thực

```java
import java.util.List;
import java.util.stream.Collectors;

record Measurement(double kilograms) {}

List<Measurement> samples = List.of(
    new Measurement(1.5),
    new Measurement(2.0),
    new Measurement(3.5)
);

double meanWeight = samples.stream()
    .collect(Collectors.averagingDouble(Measurement::kilograms));

System.out.println(meanWeight); // 2.3333333333333335
```

`double` là số thực dấu phẩy động nhị phân. Nhiều giá trị thập phân không biểu diễn chính xác; tổng và trung bình có thể chịu sai số làm tròn. Với `Double.NaN` và các giá trị vô hạn, kết quả cũng cần chính sách dữ liệu riêng.

### 3.4. Cả ba trả gì khi stream rỗng?

`Collectors.averagingInt`, `averagingLong` và `averagingDouble` **trả `0.0`** nếu không có phần tử đầu vào:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> empty = List.of();

Double average = empty.stream()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(average); // 0.0
```

Đây là **hợp đồng của collector**, không có nghĩa “đã quan sát được một mẫu với giá trị 0”. Nếu nghiệp vụ cần phân biệt **không có mẫu** và **trung bình thực sự bằng 0**, cần giữ thêm `count` hoặc trả kiểu như `OptionalDouble`. Mục 8 trình bày cách làm.

## 4. `summarizing`: một collector thu nhiều số đo

Ba loại `*SummaryStatistics` có năm getter quan trọng:

| Getter | Kiểu trả về với `IntSummaryStatistics` | Ý nghĩa |
| --- | --- | --- |
| `getCount()` | `long` | Số phần tử đã đưa vào thống kê |
| `getSum()` | `long` | Tổng các giá trị `int` |
| `getMin()` | `int` | Nhỏ nhất |
| `getMax()` | `int` | Lớn nhất |
| `getAverage()` | `double` | Trung bình cộng |

Với `LongSummaryStatistics`, `getSum()`, `getMin()` và `getMax()` trả `long`; với `DoubleSummaryStatistics`, chúng trả `double`. Cả ba đều có `getCount()` kiểu `long` và `getAverage()` kiểu `double`.

Ví dụ:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(3, 5, 8, 4);

IntSummaryStatistics stats = values.stream()
    .collect(Collectors.summarizingInt(Integer::intValue));

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 20
System.out.println(stats.getMin());     // 3
System.out.println(stats.getMax());     // 8
System.out.println(stats.getAverage()); // 5.0
```

Một phép `collect` tạo đầy đủ năm chỉ số. Nếu nguồn là một stream chỉ đọc một lần (ví dụ dòng từ file), cách này thường phù hợp hơn việc chạy năm terminal operation độc lập — vốn sẽ yêu cầu tái tạo nguồn hoặc lưu toàn bộ dữ liệu.

### 4.1. `IntSummaryStatistics` có tổng kiểu `long`

`IntSummaryStatistics` dùng `long` cho `getSum()` dù từng giá trị là `int`:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics s = IntStream.of(
    Integer.MAX_VALUE, Integer.MAX_VALUE
).summaryStatistics();

System.out.println(s.getSum()); // 4294967294
```

Tổng trên vượt giới hạn `int` nhưng vẫn nằm trong `long`. Tuy vậy, **`long` cũng có giới hạn**: với số lượng cực lớn hoặc phép cộng không được phép tràn, phải thiết kế kiểm tra số học hoặc kiểu dữ liệu lớn hơn.

### 4.2. Kiểu thống kê là object mutable

Các lớp `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics` có `accept(...)` và `combine(...)` để cập nhật trạng thái:

```java
import java.util.LongSummaryStatistics;

LongSummaryStatistics left = new LongSummaryStatistics();
left.accept(100L);
left.accept(200L);

LongSummaryStatistics right = new LongSummaryStatistics();
right.accept(300L);

left.combine(right);
System.out.println(left.getCount()); // 3
System.out.println(left.getSum());   // 600
```

Do đó, đối tượng trả từ `summarizing*` là **snapshot có thể bị cập nhật**, không phải immutable value object. Tránh phát tán cùng tham chiếu cho các phần khác của hệ thống sửa ngoài ý muốn. Nếu cần kết quả bất biến, chuyển những getter mong muốn thành `record` hoặc DTO trong một bước hoàn thiện riêng.

## 5. Bảng hợp đồng cho nguồn rỗng

Trung bình và thống kê có những giá trị mặc định khác nhau. Các giá trị `min`/`max` của thống kê rỗng đặc biệt dễ gây lỗi nếu được đưa thẳng vào báo cáo.

| Collector / kết quả | Count | Sum | Min | Max | Average |
| --- | ---: | ---: | --- | --- | ---: |
| `averagingInt/Long/Double` trên rỗng | — | — | — | — | `0.0` |
| `IntSummaryStatistics` rỗng | 0 | 0 (`long`) | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0.0` |
| `LongSummaryStatistics` rỗng | 0 | 0 (`long`) | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0.0` |
| `DoubleSummaryStatistics` rỗng | 0 | 0.0 | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` |

Ví dụ:

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

LongSummaryStatistics emptyStats = List.<Long>of().stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(emptyStats.getCount());   // 0
System.out.println(emptyStats.getSum());     // 0
System.out.println(emptyStats.getMin() == Long.MAX_VALUE); // true
System.out.println(emptyStats.getMax() == Long.MIN_VALUE); // true
System.out.println(emptyStats.getAverage()); // 0.0
```

**Quy tắc thiết kế:** chỉ coi `getMin()` và `getMax()` là số đo thực tế **khi `getCount() > 0`**. Nếu count bằng 0, kết quả hiển thị nên là “chưa có dữ liệu”, `OptionalLong.empty()`, hoặc một trạng thái tương ứng, không phải các sentinel ở bảng trên.

Trên primitive streams, `IntStream.average()`, `LongStream.average()` và `DoubleStream.average()` trả `OptionalDouble`; với nguồn rỗng, chúng trả `OptionalDouble.empty()`. Đây là khác biệt quan trọng so với `Collectors.averaging*` trả `0.0`.

## 6. Ví dụ nghiệp vụ đầy đủ: thống kê đơn hàng đã thanh toán

Ví dụ dưới đây sử dụng một bản ghi `Order` gồm vùng, số lượng hàng, tiền đơn hàng (đơn vị VND), khối lượng và trạng thái thanh toán.

Nghiệp vụ yêu cầu:

1. Chỉ thống kê các đơn đã thanh toán.
2. Tính **số lượng hàng trung bình** bằng `averagingInt`.
3. Tính **số tiền trung bình** bằng `averagingLong`.
4. Tính **khối lượng trung bình** bằng `averagingDouble`.
5. Thu **count / sum / min / max / average** của tiền đơn hàng bằng `summarizingLong`.
6. Group số tiền theo vùng, chỉ tính các đơn đã thanh toán.

Mã hoàn chỉnh, biên dịch trên **JDK 17+**:

```java
import java.util.DoubleSummaryStatistics;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class OrderAggregationDemo {

    public record Order(
        String id,
        String region,
        int quantity,
        long amountVnd,
        double weightKg,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank()
                    || quantity < 0 || amountVnd < 0
                    || !Double.isFinite(weightKg) || weightKg < 0) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 2, 120_000L, 1.5,  true),
            new Order("O-2", "HCM", 1, 80_000L, 2.0, true),
            new Order("O-3", "HN", 3, 60_000L, 0.75, true),
            new Order("O-4", "DN", 2, 40_000L, 1.25, false),
            new Order("O-5", "HCM", 4, 160_000L, 4.5, true)
        );
    }

    public static double averagePaidQuantity(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingInt(Order::quantity));
    }

    public static double averagePaidAmount(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingLong(Order::amountVnd));
    }

    public static double averagePaidWeight(List<Order> source) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.averagingDouble(Order::weightKg));
    }

    public static LongSummaryStatistics paidAmountStats(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.summarizingLong(Order::amountVnd));
    }

    public static DoubleSummaryStatistics paidWeightStats(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.summarizingDouble(Order::weightKg));
    }

    public static Map<String, LongSummaryStatistics> paidByRegion(
        List<Order> source
    ) {
        return source.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                LinkedHashMap::new,
                Collectors.summarizingLong(Order::amountVnd)
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        System.out.println(averagePaidQuantity(orders)); // 2.5
        System.out.println(averagePaidAmount(orders));   // 105000.0
        System.out.println(averagePaidWeight(orders));   // 2.1875

        LongSummaryStatistics amount = paidAmountStats(orders);
        System.out.println(amount.getCount());   // 4
        System.out.println(amount.getSum());     // 420000
        System.out.println(amount.getMin());     // 60000
        System.out.println(amount.getMax());     // 160000
        System.out.println(amount.getAverage()); // 105000.0

        DoubleSummaryStatistics weight = paidWeightStats(orders);
        System.out.println(weight.getSum());     // 8.75
        System.out.println(weight.getAverage()); // 2.1875

        Map<String, LongSummaryStatistics> regions = paidByRegion(orders);
        System.out.println(regions.get("HN").getAverage());  // 90000.0
        System.out.println(regions.get("HCM").getAverage()); // 120000.0
        System.out.println(regions.containsKey("DN"));      // false
    }
}
```

Đọc kiểu trong phép nhóm:

```text
Stream<Order>
    │ filter(Order::paid)
    ▼
Stream<Order>
    │ groupingBy(Order::region, ..., summarizingLong(Order::amountVnd))
    ▼
Map<String, LongSummaryStatistics>
```

`LinkedHashMap::new` trong ví dụ chỉ quyết định **loại Map và thứ tự chèn khóa** trên nguồn `List` tuần tự có encounter order. Bộ thống kê cho từng vùng do downstream collector tạo ra. `Map` không được mặc định hiểu là bất biến, và `LongSummaryStatistics` bên trong cũng mutable.

## 7. `groupingBy` và downstream `averaging` / `summarizing`

### 7.1. Trung bình riêng cho từng nhóm

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Double> averageAmountByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.averagingLong(
                OrderAggregationDemo.Order::amountVnd
            )
        ));

System.out.println(averageAmountByRegion.get("HN"));  // 90000.0
System.out.println(averageAmountByRegion.get("HCM")); // 120000.0
```

Ở đây:

- Collector **ngoài** nhóm các `Order` theo `region`.
- Collector **trong** nhận những `Order` thuộc từng vùng, trích `amountVnd` và tính trung bình.
- Kiểu downstream là `Collector<Order, ?, Double>`.
- Kết quả ngoài là `Map<String, Double>`.

Không cần tự tạo `Map<String,List<Order>>` rồi lặp qua từng list để tính trung bình. Việc dùng downstream collector diễn đạt cấu trúc tổng hợp **nhiều tầng** ngay trong một phép `collect`.

### 7.2. Nhận cả bộ thống kê theo nhóm

```java
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, LongSummaryStatistics> statsByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            )
        ));

LongSummaryStatistics hn = statsByRegion.get("HN");
System.out.println(hn.getCount());   // 2
System.out.println(hn.getSum());     // 180000
System.out.println(hn.getMin());     // 60000
System.out.println(hn.getMax());     // 120000
System.out.println(hn.getAverage()); // 90000.0
```

Về bản chất, mỗi nhóm có một trạng thái thống kê riêng. Không được lấy **trung bình của các trung bình vùng** để suy ra trung bình toàn bộ đơn, trừ khi các vùng có cùng số lượng mẫu.

Ví dụ, HN có hai đơn và HCM có hai đơn thì trung bình của hai số trung bình `90_000` và `120_000` tình cờ đúng bằng trung bình toàn bộ `105_000`. Nhưng nếu một vùng có một đơn còn vùng kia có mười đơn, cách lấy trung bình đơn giản của hai số trung bình sẽ sai.

Công thức cần dùng khi gộp những nhóm có số mẫu khác nhau:

\[
\overline{x}
= \frac{\sum_{g} n_g \cdot \overline{x}_g}{\sum_{g} n_g}
= \frac{\sum_{g} \mathrm{sum}_g}{\sum_{g} n_g}
\]

Trong đó `n_g` là số mẫu của nhóm `g`. `summarizing` giữ cả `count` lẫn `sum` nên thích hợp để diễn đạt bài toán này.

## 8. `filter` trước nhóm và `Collectors.filtering` trong nhóm

Hai cách lọc có thể tạo **khác biệt về tập khóa**, mặc dù các thống kê trên những nhóm còn lại giống nhau.

### 8.1. `Stream.filter` trước `groupingBy`

```java
var filteredBeforeGrouping = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(Collectors.groupingBy(
        OrderAggregationDemo.Order::region,
        Collectors.summarizingLong(
            OrderAggregationDemo.Order::amountVnd
        )
    ));

System.out.println(filteredBeforeGrouping.containsKey("DN")); // false
```

Vùng DN chỉ có đơn chưa thanh toán. Khi lọc trước grouping, **không còn phần tử DN** để tạo nhóm.

### 8.2. `Collectors.filtering` làm downstream

`Collectors.filtering` có từ **JDK 9**:

```java
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, LongSummaryStatistics> withEmptyGroups =
    OrderAggregationDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.filtering(
                OrderAggregationDemo.Order::paid,
                Collectors.summarizingLong(
                    OrderAggregationDemo.Order::amountVnd
                )
            )
        ));

System.out.println(withEmptyGroups.containsKey("DN")); // true
System.out.println(withEmptyGroups.get("DN").getCount()); // 0
System.out.println(withEmptyGroups.get("DN").getSum());   // 0
```

Collector ngoài vẫn nhìn thấy đơn DN và tạo **khóa nhóm DN**; downstream `filtering` loại phần tử đó trước khi tính thống kê, tạo kết quả có `count == 0`. Vì vậy:

- **Lọc trước nhóm:** chỉ có khóa của các phần tử đã lọc.
- **Lọc trong downstream:** các khóa của nguồn trước lọc vẫn có thể tồn tại, với bộ thống kê rỗng.

Nếu tất cả đơn của một vùng đều bị downstream loại, `getAverage() == 0.0` chỉ là giá trị trả về trên thống kê không có mẫu; **không** được báo cáo là doanh thu trung bình thực bằng 0.

## 9. Giữ trạng thái “không có mẫu” bằng `collectingAndThen`

Nếu một API cần phân biệt “trung bình bằng 0” và “không có dữ liệu”, `Collectors.averaging*` không đủ thông tin khi đứng một mình. Có thể dùng `summarizing*` rồi chuyển `count == 0` thành một kết quả tùy chọn.

`Collectors.collectingAndThen` nhận downstream collector và một finisher để biến kết quả downstream thành kiểu công khai mong muốn:

```java
import java.util.OptionalDouble;
import java.util.stream.Collector;
import java.util.stream.Collectors;

static <T> Collector<T, ?, OptionalDouble> optionalAverageLong(
    java.util.function.ToLongFunction<? super T> mapper
) {
    return Collectors.collectingAndThen(
        Collectors.summarizingLong(mapper),
        stats -> stats.getCount() == 0
            ? OptionalDouble.empty()
            : OptionalDouble.of(stats.getAverage())
    );
}
```

Ví dụ dùng trên `Order`:

```java
import java.util.OptionalDouble;

OptionalDouble average = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(optionalAverageLong(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(average.orElseThrow()); // 105000.0

OptionalDouble missing = java.util.stream.Stream
    .<OrderAggregationDemo.Order>empty()
    .collect(optionalAverageLong(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(missing.isEmpty()); // true
```

Đây là một ví dụ về **composed collector**:

```text
Order
  └─ summarizingLong(amountVnd) ──> LongSummaryStatistics
                                    └─ collectingAndThen
                                       ├─ count == 0: OptionalDouble.empty()
                                       └─ count > 0: OptionalDouble.of(avg)
```

**Lưu ý:** `OptionalDouble` giải quyết **có/không có mẫu** nhưng không biến số `double` thành kiểu tính tiền chính xác. Nếu doanh thu phải đảm bảo số thập phân tuyệt đối theo quy tắc tài chính, xem mục 11.

Nếu đầu vào đã là một primitive stream, `LongStream.average()` trả `OptionalDouble` trực tiếp:

```java
OptionalDouble direct = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToLong(OrderAggregationDemo.Order::amountVnd)
    .average();
```

Chọn giữa cách này và composed collector dựa trên mục tiêu: primitive terminal thích hợp cho **một thống kê của toàn luồng**; composed collector phù hợp khi cần kết hợp với `groupingBy` hoặc một bước hoàn thiện riêng.

## 10. Biến bộ thống kê mutable thành kết quả bất biến

Các lớp `*SummaryStatistics` cho phép cập nhật sau khi thu thập. Để trả báo cáo bất biến, có thể dùng một `record` và `collectingAndThen`.

```java
import java.util.OptionalLong;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record AmountReport(
    long count,
    long totalVnd,
    OptionalLong minVnd,
    OptionalLong maxVnd,
    java.util.OptionalDouble averageVnd
) {}

static <T> Collector<T, ?, AmountReport> amountReport(
    java.util.function.ToLongFunction<? super T> mapper
) {
    return Collectors.collectingAndThen(
        Collectors.summarizingLong(mapper),
        stats -> {
            boolean any = stats.getCount() > 0;
            return new AmountReport(
                stats.getCount(),
                stats.getSum(),
                any ? OptionalLong.of(stats.getMin()) : OptionalLong.empty(),
                any ? OptionalLong.of(stats.getMax()) : OptionalLong.empty(),
                any ? java.util.OptionalDouble.of(stats.getAverage())
                    : java.util.OptionalDouble.empty()
            );
        }
    );
}
```

`AmountReport` có các trường giá trị bất biến, vì vậy caller không thể tiếp tục gọi `accept` hay `combine` để sửa thống kê đã công bố.

Lưu ý rằng record chỉ bảo đảm các **tham chiếu trường** là final; nếu một trường trỏ tới collection mutable thì record đó chưa chắc bất biến sâu. Ví dụ trên dùng primitive và các Optional nên không có vấn đề đó.

Sử dụng:

```java
AmountReport report = OrderAggregationDemo.sample().stream()
    .filter(OrderAggregationDemo.Order::paid)
    .collect(amountReport(
        OrderAggregationDemo.Order::amountVnd
    ));

System.out.println(report.count()); // 4
System.out.println(report.totalVnd()); // 420000
System.out.println(report.minVnd().orElseThrow()); // 60000
System.out.println(report.averageVnd().orElseThrow()); // 105000.0
```

Nếu một nhóm không có mẫu, `AmountReport` thể hiện điều đó qua `count == 0` và các Optional rỗng, thay vì đưa `Long.MAX_VALUE` hay `Long.MIN_VALUE` vào JSON hoặc bảng báo cáo.

## 11. Sai số số thực, tràn số và tính đúng đắn của trung bình

### 11.1. Số nguyên cũng có thể tràn khi cộng

`summarizingInt` lưu tổng ở kiểu `long`, nhưng `summarizingLong` lưu tổng ở kiểu `long` và **có thể tràn**. Các collector `summingLong`/`averagingLong` cũng không cung cấp bảo đảm tự ném lỗi khi cộng vượt phạm vi `long`.

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> huge = List.of(Long.MAX_VALUE, 1L);

long wrapped = huge.stream()
    .collect(Collectors.summarizingLong(Long::longValue))
    .getSum();

// Giá trị long đã tràn miền biểu diễn; không dùng cho thống kê tài chính.
```

Nếu cần chính xác tuyệt đối, không tính tiền lớn bằng một accumulator có tổng `long` không kiểm soát tràn. Có thể dùng `BigInteger` hoặc `BigDecimal` và chính sách làm tròn.

Ví dụ tổng số tiền nguyên VND bằng `BigInteger`, dùng downstream `reducing`:

```java
import java.math.BigInteger;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> exactByRegion =
    OrderAggregationDemo.sample().stream()
        .filter(OrderAggregationDemo.Order::paid)
        .collect(Collectors.groupingBy(
            OrderAggregationDemo.Order::region,
            Collectors.reducing(
                BigInteger.ZERO,
                order -> BigInteger.valueOf(order.amountVnd()),
                BigInteger::add
            )
        ));

System.out.println(exactByRegion.get("HN")); // 180000
```

Đối với **trung bình tiền tệ**, phép chia có thể không có biểu diễn thập phân hữu hạn. Vì vậy nên quy định `scale` và `RoundingMode`, thay vì chuyển ngay sang `double`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

BigInteger sum = BigInteger.valueOf(10L);
long count = 3L;

BigDecimal exactRoundedAverage =
    new BigDecimal(sum).divide(
        BigDecimal.valueOf(count),
        2,
        RoundingMode.HALF_UP
    );

System.out.println(exactRoundedAverage); // 3.33
```

Chỉ dùng ví dụ khi nghiệp vụ cho phép hai chữ số thập phân và quy tắc `HALF_UP`. Với dữ liệu thực, phải lấy đúng `sum` và `count` từ cùng tập bản ghi; dùng hai pipeline trên nguồn có trạng thái thay đổi có thể dẫn đến kết quả không nhất quán.

### 11.2. `double` không kết hợp chính xác về mặt bit

Với `double`, phép cộng không bảo đảm:

```text
(a + b) + c == a + (b + c)
```

vì sai số làm tròn. Một phép thu thập song song có thể gộp các tổng cục bộ theo thứ tự khác, làm chữ số cuối của `average` hoặc `sum` thay đổi. Javadoc cũng lưu ý thứ tự đầu vào và thứ tự cộng có thể ảnh hưởng độ chính xác của `averagingDouble` và `summarizingDouble`.

Ví dụ minh họa mất độ chính xác:

```java
double a = 1.0e16;
double b = 1.0;
double c = -1.0e16;

System.out.println((a + b) + c); // 0.0
System.out.println(a + (b + c)); // 0.0 trong trường hợp này

// Xét phép nhóm khác:
System.out.println((a + c) + b); // 1.0
```

Không viết unit test đòi kết quả dấu phẩy động của collector song song phải **bằng bit** với kết quả tuần tự nếu không có hợp đồng đảm bảo. Nên dùng sai số dung sai phù hợp, hoặc một thuật toán cộng chính xác/ổn định hơn cho nghiệp vụ yêu cầu.

### 11.3. `NaN`, vô cực và dữ liệu đo không hợp lệ

`DoubleSummaryStatistics` có các quy tắc đặc biệt cho `NaN` và vô cực. Nếu bất kỳ mẫu nào là `NaN`, các phép tính tổng/trung bình có thể thành `NaN`; kết quả min/max cũng chịu ảnh hưởng theo hợp đồng của lớp. Với `+Infinity` và `-Infinity` đồng thời, phép cộng cho `NaN`.

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream.of(
    1.0, Double.NaN, 2.0
).summaryStatistics();

System.out.println(Double.isNaN(stats.getAverage())); // true
```

Nếu báo cáo chỉ cho phép số hữu hạn, kiểm tra ở **ranh giới dữ liệu** bằng `Double.isFinite(value)`. Có thể dùng `filter` để bỏ mẫu không hợp lệ nếu được nghiệp vụ cho phép; khi mẫu không hợp lệ biểu thị lỗi thiết bị hay lỗi nhập liệu, việc **ném lỗi hoặc ghi nhận lỗi riêng** thường đúng hơn việc âm thầm bỏ qua.

### 11.4. Tỷ lệ và trung bình có trọng số

`averagingInt`/`averagingLong`/`averagingDouble` tính **trung bình cộng không trọng số**: mỗi phần tử stream đóng góp một mẫu. Nếu muốn doanh thu trung bình **mỗi sản phẩm** thì lấy trung bình giá trị của mỗi đơn là không đúng khi số lượng sản phẩm mỗi đơn khác nhau.

Với `quantity` là số sản phẩm và `amountVnd` là tổng tiền của đơn:

\[
\text{Giá trị trung bình/sản phẩm}
= \frac{\sum \text{amountVnd}}{\sum \text{quantity}}
\]

Hai mẫu có số lượng khác nhau phải có trọng số khác nhau. Hãy dùng một phép tích lũy cho cả tử số và mẫu số (ví dụ collector tùy chỉnh, `teeing` hoặc mô hình thống kê phù hợp) và xử lý trường hợp mẫu số bằng 0. Không cố gắng ép một bài toán trung bình có trọng số vào `averagingLong(Order::amountVnd)`.

## 12. Lựa chọn giữa collector và terminal operation của primitive stream

Nếu chỉ cần **một số đo của cả luồng**, primitive stream đôi khi ngắn gọn và tránh boxing:

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;

var source = OrderAggregationDemo.sample();

OptionalDouble avg = source.stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToInt(OrderAggregationDemo.Order::quantity)
    .average();

IntSummaryStatistics stats = source.stream()
    .filter(OrderAggregationDemo.Order::paid)
    .mapToInt(OrderAggregationDemo.Order::quantity)
    .summaryStatistics();
```

So sánh:

| Bài toán | API tự nhiên |
| --- | --- |
| Một số trung bình trên `Stream<Order>` | `collect(averagingInt/Long/Double(mapper))` |
| Một bộ thống kê trên `Stream<Order>` | `collect(summarizingInt/Long/Double(mapper))` |
| Trung bình toàn bộ `IntStream` | `IntStream.average()` → `OptionalDouble` |
| Bộ thống kê toàn bộ `LongStream` | `LongStream.summaryStatistics()` |
| Trung bình theo từng khóa của `Stream<Order>` | `groupingBy(key, averaging*)` |
| Bộ thống kê theo từng khóa | `groupingBy(key, summarizing*)` |
| Trung bình phải phân biệt nguồn rỗng trong grouping | `collectingAndThen(summarizing*, finisher)` làm downstream |

`IntStream`, `LongStream`, `DoubleStream` có những terminal operation chuyên biệt, nhưng **không** hỗ trợ `collect(Collector<T,A,R>)` giống object stream. Nếu cần dùng `Collectors.groupingBy` cho dữ liệu nguyên thủy, bạn có thể chuyển sang object stream bằng `boxed()` hoặc `mapToObj(...)`, hoặc thiết kế một phép tổng hợp primitive phù hợp.

## 13. Tính lười, side effect và hiệu năng xử lý song song

Các collector chỉ chạy khi `collect` tiêu thụ pipeline. `filter` và `map` phía trước vẫn là intermediate operation lazy.

```java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

double averageEven = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(averageEven); // 6.0
```

Đây là ví dụ đúng về ngữ nghĩa nhưng nếu chỉ cần trung bình, phiên bản `IntStream.filter(...).average()` trực tiếp hơn và tránh bước boxing sang `Integer`.

### 13.1. Không đưa side effect vào mapper

Tránh dùng mapper `ToIntFunction` như cơ chế tăng bộ đếm bên ngoài:

```java
// Phản ví dụ:
java.util.concurrent.atomic.AtomicInteger observed =
    new java.util.concurrent.atomic.AtomicInteger();

double wrongDesign = OrderAggregationDemo.sample().stream()
    .collect(Collectors.averagingInt(order -> {
        observed.incrementAndGet();
        return order.quantity();
    }));

// observed không nên là một phần hợp đồng nghiệp vụ.
```

Mapper của stream nên **non-interfering** và **stateless**. `AtomicInteger` chỉ giải quyết vấn đề cập nhật đồng thời của biến đếm, không biến side effect trong mapper thành lựa chọn thiết kế đúng. Muốn biết số mẫu, dùng `summarizingInt(...).getCount()` thay vì viết side effect.

### 13.2. Parallel stream không tự nhanh hơn

`groupingBy` cùng downstream `summarizing*` có thể chạy với stream song song: framework có thể tạo nhiều trạng thái thống kê rồi gộp chúng. Tuy nhiên:

- Chi phí phân chia và gộp tăng lên, nhất là khi số bản ghi ít hoặc có nhiều nhóm nhỏ.
- Collector không nhất thiết `CONCURRENT`; cơ chế hợp lệ thường là mỗi nhánh tích lũy vào trạng thái riêng, rồi kết hợp.
- Số học `double` có thể cho khác biệt do thứ tự gộp.
- Nếu yêu cầu thứ tự đầu ra, hãy xem thêm encounter order và collector characteristics; bản đồ nhóm thông thường không cam kết thứ tự duyệt khóa.
- Không chia sẻ cùng một `IntSummaryStatistics` mutable cho nhiều luồng tự gọi `accept` nếu không có cơ chế đồng bộ phù hợp.

Đo bằng bộ dữ liệu đại diện trước khi thêm `parallel()`. Trên dữ liệu nhỏ, code tuần tự thường đơn giản hơn.

### 13.3. Tài nguyên và bộ nhớ

`summarizing` giữ trạng thái tương đối gọn (một số biến tổng, đếm, cực trị), không cần giữ tất cả phần tử như `toList()`. Tuy nhiên, `groupingBy` tạo bộ thống kê **cho từng khóa**, nên số nhóm lớn vẫn làm bộ nhớ tăng.

Nếu nguồn là `Files.lines(path)` hoặc stream nắm tài nguyên I/O, phải đóng bằng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.IntSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static IntSummaryStatistics lineLengthStats(Path path)
    throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.collect(
            Collectors.summarizingInt(String::length)
        );
    }
}
```

Với file rỗng, `getCount() == 0`. Nếu truy cập file gặp lỗi, không được tùy tiện chuyển thành bộ thống kê rỗng rồi coi như “không có dữ liệu”; lỗi I/O và nguồn rỗng là hai trạng thái khác nhau.

## 14. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Cách xử lý |
| --- | --- | --- |
| Xem `averaging*` trên rỗng trả `OptionalDouble.empty()` | Thực tế collector trả `0.0` | Dùng `summarizing*` + count hoặc primitive `average()` |
| Đọc `getMin/getMax` khi `count == 0` như số thực tế | Các giá trị là sentinel | Kiểm tra `getCount() > 0` |
| Dùng trung bình nhóm để suy ra trung bình chung mà không xét số mẫu | Trung bình nhóm có thể có trọng số khác nhau | Cộng tổng và số mẫu |
| Dùng `summarizingLong` cho tổng tiền có thể vượt `long` | Tổng có thể tràn | `BigInteger`/`BigDecimal` hoặc cơ chế kiểm tra số học |
| So sánh `double` bằng tuyệt đối ở mọi bài test | Sai số làm tròn phụ thuộc dữ liệu và thứ tự gộp | Sai số dung sai hoặc số học chính xác |
| Giữ `NaN`/Infinity mà không có hợp đồng | Có thể làm hỏng tổng, min, max, average | Validate dữ liệu hoặc phân loại lỗi |
| Gọi `average` khi yêu cầu trung bình có trọng số | Mỗi phần tử được tính một mẫu như nhau | Thiết kế tử số và mẫu số |
| Thay `Stream.filter` bằng downstream `filtering` không suy xét | Thay đổi tập khóa của grouping | Chọn theo yêu cầu tồn tại nhóm rỗng |
| Trả trực tiếp đối tượng `SummaryStatistics` nhưng giả định bất biến | Người gọi có thể `accept/combine` | Tạo DTO/record bất biến |
| Chạy nhiều terminal operation trên cùng stream | Stream chỉ dùng một lần | Tạo stream mới hoặc dùng một collector tổng hợp |
| Cho rằng `parallel` chắc chắn nhanh hơn | Có chi phí gộp và khác biệt dấu phẩy động | Benchmark và giữ mapper thuần |

## 15. Kiểm thử JUnit 5

Ví dụ dưới đây tham chiếu lớp `OrderAggregationDemo` từ mục 6. Đặt file test trong cùng package phù hợp với mã nguồn và khai báo JUnit Jupiter trong dự án.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class OrderAggregationDemoTest {

    @Test
    void averagingCollectorsCalculateMean() {
        var source = OrderAggregationDemo.sample();

        assertEquals(2.5,
            OrderAggregationDemo.averagePaidQuantity(source), 1e-12);
        assertEquals(105_000.0,
            OrderAggregationDemo.averagePaidAmount(source), 1e-12);
        assertEquals(2.1875,
            OrderAggregationDemo.averagePaidWeight(source), 1e-12);
    }

    @Test
    void summarizingLongReturnsAllMetrics() {
        LongSummaryStatistics stats =
            OrderAggregationDemo.paidAmountStats(
                OrderAggregationDemo.sample()
            );

        assertEquals(4L, stats.getCount());
        assertEquals(420_000L, stats.getSum());
        assertEquals(60_000L, stats.getMin());
        assertEquals(160_000L, stats.getMax());
        assertEquals(105_000.0, stats.getAverage(), 1e-12);
    }

    @Test
    void summarizingDoubleReturnsWeightMetrics() {
        DoubleSummaryStatistics stats =
            OrderAggregationDemo.paidWeightStats(
                OrderAggregationDemo.sample()
            );

        assertEquals(4L, stats.getCount());
        assertEquals(8.75, stats.getSum(), 1e-12);
        assertEquals(0.75, stats.getMin(), 1e-12);
        assertEquals(4.5, stats.getMax(), 1e-12);
        assertEquals(2.1875, stats.getAverage(), 1e-12);
    }

    @Test
    void averagingOnEmptyInputIsZero() {
        var empty = List.<OrderAggregationDemo.Order>of();

        assertEquals(0.0,
            OrderAggregationDemo.averagePaidAmount(empty), 0.0);

        LongSummaryStatistics stats =
            OrderAggregationDemo.paidAmountStats(empty);
        assertEquals(0L, stats.getCount());
        assertEquals(Long.MAX_VALUE, stats.getMin());
        assertEquals(Long.MIN_VALUE, stats.getMax());
    }

    @Test
    void groupingAfterFilterOmitsRegionWithoutPaidOrders() {
        Map<String, LongSummaryStatistics> map =
            OrderAggregationDemo.paidByRegion(
                OrderAggregationDemo.sample()
            );

        assertFalse(map.containsKey("DN"));
        assertEquals(2L, map.get("HN").getCount());
        assertEquals(180_000L, map.get("HN").getSum());
    }

    @Test
    void downstreamFilteringPreservesExistingRegionKey() {
        var map = OrderAggregationDemo.sample().stream()
            .collect(Collectors.groupingBy(
                OrderAggregationDemo.Order::region,
                Collectors.filtering(
                    OrderAggregationDemo.Order::paid,
                    Collectors.summarizingLong(
                        OrderAggregationDemo.Order::amountVnd
                    )
                )
            ));

        assertTrue(map.containsKey("DN"));
        assertEquals(0L, map.get("DN").getCount());
    }

    @Test
    void sequentialAndParallelIntegerSummariesAgree() {
        var data = OrderAggregationDemo.sample();

        LongSummaryStatistics sequential = data.stream()
            .collect(Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            ));
        LongSummaryStatistics parallel = data.parallelStream()
            .collect(Collectors.summarizingLong(
                OrderAggregationDemo.Order::amountVnd
            ));

        assertEquals(sequential.getCount(), parallel.getCount());
        assertEquals(sequential.getSum(), parallel.getSum());
        assertEquals(sequential.getMin(), parallel.getMin());
        assertEquals(sequential.getMax(), parallel.getMax());
    }
}
```

**Ma trận kiểm thử nên bổ sung:** nguồn rỗng, nguồn chỉ có một mẫu, mọi mẫu bằng `0`, chỉ có giá trị âm (nếu mô hình cho phép), min/max bằng nhau, giá trị ở sát giới hạn kiểu số, thiếu khóa nhóm, mapper gặp `null`, giá trị `NaN` và vô cực, dữ liệu song song lớn, sai số trung bình và phép gộp có trọng số.

## 16. Bài tập tự luyện

### Bài 1 — So sánh `averagingInt` và `summarizingInt`

Cho `List<Integer> values = List.of(1, 3, 5, 7)`. Viết hai pipeline:

1. Lấy một giá trị trung bình bằng `Collectors.averagingInt`.
2. Lấy `IntSummaryStatistics` rồi in `count`, `sum`, `min`, `max`, `average`.

Giải thích vì sao cả hai trung bình bằng `4.0` nhưng kiểu kết quả khác nhau.

### Bài 2 — Nguồn rỗng và `OptionalDouble`

Với `List<Integer> empty = List.of()`, đối chiếu:

```java
empty.stream().collect(Collectors.averagingInt(Integer::intValue))
empty.stream().mapToInt(Integer::intValue).average()
```

Giải thích tại sao kết quả thứ nhất là `0.0` và kết quả thứ hai là `OptionalDouble.empty()`. Đề xuất kiểu trả về cho API mà số `0` cũng là một giá trị trung bình hợp lệ.

### Bài 3 — Thống kê theo nhóm

Cho danh sách sản phẩm có `category` và `price`. Dùng `groupingBy(category, summarizingLong(price))` để trả `Map<String,LongSummaryStatistics>`. Viết test cho hai nhóm có giá trị và một nhóm bị loại hết sau `Stream.filter`.

### Bài 4 — Khác nhau giữa hai cách lọc

Từ `OrderAggregationDemo.sample()`, dùng `Stream.filter(Order::paid)` trước grouping, rồi dùng downstream `Collectors.filtering(Order::paid, summarizingLong(...))`. Kiểm tra sự khác nhau về việc vùng DN có khóa trong map hay không.

### Bài 5 — Trung bình có trọng số

Định nghĩa `record Item(int quantity, long totalVnd) {}`. Với `[Item(1,100), Item(3,900)]`:

- Trung bình của `totalVnd` **theo bản ghi** là `(100+900)/2 = 500`.
- Giá trị trung bình **trên mỗi sản phẩm** là `(100+900)/(1+3) = 250`.

Hãy thiết kế phép tích lũy đúng cho kết quả thứ hai và xử lý nguồn có tổng `quantity == 0`. Đừng dùng `averagingLong(Item::totalVnd)` cho câu hỏi “mỗi sản phẩm”.

### Bài 6 — Số tiền lớn

Cho số tiền `Long.MAX_VALUE` và `1`. Giải thích vì sao `summarizingLong` không phù hợp nếu báo cáo yêu cầu tổng chính xác tuyệt đối. Viết phiên bản dùng `BigInteger` để tổng không tràn; sau đó dùng `BigDecimal.divide` với `RoundingMode` để trình bày trung bình.

### Bài 7 — Bất biến và tài nguyên

Viết một collector gồm `summarizingInt(String::length)` rồi `collectingAndThen` thành `record LengthReport(long count, long sum, OptionalInt min, OptionalInt max)`. Với file đọc bằng `Files.lines`, dùng `try-with-resources`. Phân biệt trường hợp file rỗng với trường hợp file không tồn tại.

## 17. Bảng quyết định khi tổng hợp bằng collector

| Yêu cầu | Lựa chọn |
| --- | --- |
| Cần trung bình của một thuộc tính trên object stream | `averagingInt/Long/Double(mapper)` |
| Cần count, sum, min, max, average trong một lượt | `summarizingInt/Long/Double(mapper)` |
| Cần các số đo theo từng khóa | `groupingBy(key, summarizing*)` |
| Chỉ cần trung bình theo từng khóa | `groupingBy(key, averaging*)` |
| Cần giữ khóa nhóm dù phần tử không qua điều kiện downstream | `groupingBy(key, filtering(predicate, summarizing*))` |
| Cần phân biệt không có mẫu và trung bình bằng 0 | `getCount()` hoặc `OptionalDouble` từ finisher |
| Cần trả DTO bất biến | `collectingAndThen(summarizing*, stats -> new Report(...))` |
| Cần tính trung bình trực tiếp trên primitive stream | `IntStream/LongStream/DoubleStream.average()` |
| Cần tổng tiền chính xác vượt `long` | `BigInteger`/`BigDecimal` và quy tắc chia/làm tròn |
| Có `NaN` hoặc vô cực trong dữ liệu đo | Validate hoặc quy định chính sách rõ ràng |
| Cần trung bình có trọng số | Tích lũy tổng có trọng số và tổng trọng số |
| Muốn tăng tốc bằng `parallel()` | Giữ mapper thuần, hiểu combiner, đo hiệu năng và dung sai số thực |

`averaging*` và `summarizing*` là hai nhóm collector bổ trợ nhau trong Java Stream API. **`averaging` tạo một số trung bình**, còn **`summarizing` giữ đủ thông tin về số lượng, tổng và cực trị** để đưa ra báo cáo đáng tin hơn. Khi kết hợp chúng với `groupingBy`, `filtering` và `collectingAndThen`, hãy đặc biệt chú ý khác biệt giữa **không có mẫu** và **mẫu bằng 0**, giới hạn miền số, độ chính xác của `double`, tính mutable của thống kê và chi phí khi gộp kết quả song song.
