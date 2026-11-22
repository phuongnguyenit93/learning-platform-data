# Tạo báo cáo nhiều chỉ số và kết quả tổng hợp bất biến

Trong **Java Stream API**, một báo cáo thường không chỉ cần một tổng số. Chẳng hạn, từ danh sách đơn hàng ta muốn xem **số đơn, tổng tiền, giá trị nhỏ nhất/lớn nhất, trung bình và số đơn trễ** theo từng nhóm. Nếu mỗi chỉ số được tính bằng một pipeline riêng, việc lọc, phân nhóm và duyệt dữ liệu có thể lặp lại nhiều lần. Các **collector nhiều tầng** cho phép mô tả việc phân nhóm và tổng hợp trong một terminal operation `collect`.

Kết quả báo cáo còn cần một hợp đồng khác: sau khi tính xong, các phần khác của chương trình **không được vô tình thay đổi** những con số đã công bố. Vì thế, bài học này kết hợp hai ý tưởng:

1. **Tổng hợp nhiều chỉ số trong cùng lần thu thập**, bằng `summarizingLong`, `groupingBy`, `filtering`, `teeing` hoặc collector tùy chỉnh.
2. **Chốt kết quả thành các giá trị bất biến** bằng kiểu dữ liệu bất biến, `collectingAndThen`, `Map.copyOf` và `List.copyOf` khi phù hợp.

Chúng ta sẽ tách biệt *trạng thái tích lũy có thể thay đổi trong collector* và *dữ liệu báo cáo trả ra không thể thay đổi*. Đây là cách thiết kế quan trọng đối với Java Stream API khi xử lý dữ liệu khai báo, thống kê và các pipeline song song.

## 1. Xác định trước hình dạng báo cáo và hợp đồng dữ liệu

Giả sử dữ liệu đầu vào gồm các đơn hàng có thuộc tính: đội phụ trách, mã đơn, số tiền theo đơn vị nguyên nhỏ nhất, trạng thái thanh toán và trạng thái giao trễ.

Ta muốn báo cáo **chỉ những đơn đã thanh toán** theo đội:

| Đội | Số đơn | Tổng tiền | Nhỏ nhất | Lớn nhất | Trung bình | Số đơn trễ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| API | 2 | 2.000 | 800 | 1.200 | 1.000 | 1 |
| UI | 1 | 2.000 | 2.000 | 2.000 | 2.000 | 1 |

Một số quyết định cần có **trước khi viết code**:

- Điều kiện đủ điều kiện được đặt **trước bước phân nhóm** hay chỉ áp dụng cho một chỉ số trong nhóm?
- Khi không có dữ liệu, một nhóm **không tồn tại** hay vẫn cần dòng báo cáo với các giá trị rỗng?
- Số tiền dùng `long`, `BigDecimal` hay `double`? Có thể tràn hoặc có quy tắc làm tròn nào?
- Báo cáo chỉ cần **đọc** hay người dùng còn phải chỉnh sửa các nhóm và chỉ số?
- Có cần giữ **thứ tự đội** khi hiển thị không?

Ví dụ xuyên suốt dùng `long` cho số tiền nguyên. Các mẫu dữ liệu nhỏ không gây tràn `long`; hệ thống thật vẫn cần kiểm soát giới hạn số tiền và tổng tiền.

## 2. Tránh tính từng chỉ số bằng một pipeline độc lập

Đây là cách viết hợp lệ trên một `List` có thể tạo stream nhiều lần, nhưng thường không phải thiết kế tốt cho báo cáo nhiều chỉ số:

```java
import java.util.Arrays;
import java.util.List;

List<Long> amounts = Arrays.asList(1200L, 800L, 2000L);

long count = amounts.stream().count();
long sum = amounts.stream().mapToLong(Long::longValue).sum();
long min = amounts.stream().mapToLong(Long::longValue)
    .min().orElseThrow(IllegalStateException::new);
long max = amounts.stream().mapToLong(Long::longValue)
    .max().orElseThrow(IllegalStateException::new);
double average = amounts.stream().mapToLong(Long::longValue)
    .average().orElseThrow(IllegalStateException::new);
```

Mỗi `amounts.stream()` tạo **một đối tượng stream khác**, còn các terminal operation trên nguồn thông thường sẽ duyệt hoặc xử lý phần dữ liệu liên quan. Trong pipeline thực tế, việc lọc, ánh xạ, giải mã bản ghi hay truy cập nguồn I/O có thể đắt hơn nhiều so với phép cộng.

**Không** thể dùng lại cùng một `Stream` sau terminal operation:

```java
import java.util.stream.LongStream;

LongStream values = LongStream.of(1200L, 800L, 2000L);
long sum = values.sum();

// Sai: cùng stream đã bị tiêu thụ.
// long count = values.count(); // IllegalStateException
```

Nếu nguồn chỉ được tiêu thụ một lần, chẳng hạn luồng tệp hoặc một iterator phát dữ liệu, nhiều lần đọc lại còn có thể không khả thi. Giải pháp là thiết kế collector cho những phép tổng hợp cần thực hiện **trong cùng một lần thu thập logic**.

## 3. `summarizingInt`, `summarizingLong`, `summarizingDouble`: nhiều chỉ số sẵn có

Ba collector này tính **count, sum, min, max, average** cho một trường số của phần tử:

| Collector | Mapper | Kiểu kết quả |
| --- | --- | --- |
| `Collectors.summarizingInt(...)` | `ToIntFunction<T>` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(...)` | `ToLongFunction<T>` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(...)` | `ToDoubleFunction<T>` | `DoubleSummaryStatistics` |

Ví dụ:

```java
import java.util.Arrays;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

LongSummaryStatistics stats = Arrays.asList(1200L, 800L, 2000L)
    .stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 4000
System.out.println(stats.getMin());     // 800
System.out.println(stats.getMax());     // 2000
System.out.println(stats.getAverage()); // 1333.333...
```

`summarizingLong` là một **collector** dành cho `Stream<T>`; nó không giống terminal operation `LongStream.summaryStatistics()`, dù kết quả thống kê có cùng kiểu. Phiên bản collector đặc biệt hữu ích khi đặt bên trong `groupingBy` hoặc `partitioningBy`.

Lưu ý: `LongSummaryStatistics` **mutable**; các phương thức `accept` và `combine` có thể thay đổi đối tượng. Vì vậy, trả trực tiếp `Map<String, LongSummaryStatistics>` chưa tạo ra một bản báo cáo bất biến.

## 4. Phân nhóm rồi thống kê: `groupingBy` với downstream collector

`Collectors.groupingBy(classifier, downstream)` tạo một map có khóa được xác định bởi `classifier`; từng nhóm dùng `downstream` để tính kết quả:

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

List<String> data = Arrays.asList("API:1200", "UI:2000", "API:800");

Map<String, LongSummaryStatistics> byTeam = data.stream()
    .collect(Collectors.groupingBy(
        line -> line.substring(0, line.indexOf(':')),
        Collectors.summarizingLong(line ->
            Long.parseLong(line.substring(line.indexOf(':') + 1))
        )
    ));

System.out.println(byTeam.get("API").getCount()); // 2
System.out.println(byTeam.get("API").getSum());   // 2000
System.out.println(byTeam.get("UI").getMax());    // 2000
```

Khi từng phần tử được duyệt, classifier quyết định nhóm và downstream cập nhật thống kê tương ứng. Về mặt logic, nguồn chỉ qua một terminal operation, không phải gọi `filter` năm lần cho từng đội.

Nhưng kết quả này có **hai tầng mutable**: map có thể được thay đổi trong các triển khai thông dụng, và từng `LongSummaryStatistics` chắc chắn là đối tượng có thể cập nhật. Muốn chốt báo cáo, cần chuyển các bộ thống kê sang kiểu giá trị bất biến và bảo vệ map chứa chúng.

## 5. `collectingAndThen`: chốt kết quả sau khi tích lũy

`Collectors.collectingAndThen(downstream, finisher)` bọc một collector bằng **bước hoàn thiện cuối**. Downstream được phép sử dụng container mutable để tích lũy hiệu quả; `finisher` biến kết quả đã hoàn tất thành kiểu đầu ra mong muốn.

```text
Stream<T>
   |
   +--> groupingBy(key, downstream)
             |
             +--> summarizingLong(...)    // tích lũy mutable
                         |
                         +--> finisher     // tạo DTO bất biến
             |
             +--> finisher map ngoài       // Map.copyOf(...)
   |
   +--> Map<K, ImmutableReport>
```

Một kiểu báo cáo đơn giản có thể là `record` (Java 16+):

```java
import java.util.LongSummaryStatistics;

record BasicMetrics(
    long count,
    long total,
    long minimum,
    long maximum,
    double average
) {
    static BasicMetrics from(LongSummaryStatistics source) {
        return new BasicMetrics(
            source.getCount(),
            source.getSum(),
            source.getMin(),
            source.getMax(),
            source.getAverage()
        );
    }
}
```

`record` không có setter cho các trường thành phần; với các thành phần chỉ là primitive, `BasicMetrics` là một giá trị bất biến theo thiết kế ở ví dụ này. Chuyển đổi bằng `from` cũng tránh làm lộ đối tượng `LongSummaryStatistics` mutable.

**Cẩn thận với nhóm rỗng:** `LongSummaryStatistics.getMin()` khi `count == 0` trả `Long.MAX_VALUE`, còn `getMax()` trả `Long.MIN_VALUE`. Hai giá trị đó **không** phải dữ liệu đo được. Ví dụ `BasicMetrics` thích hợp cho **nhóm đã xuất hiện và chứa ít nhất một phần tử**. Nếu thiết kế một báo cáo tổng quát có thể rỗng, nên biểu diễn min/max bằng `OptionalLong`, đánh dấu trạng thái không có dữ liệu, hoặc chỉ đọc chúng sau khi đã kiểm tra count.

### Chốt từng nhóm và map ngoài

Giả sử đã định nghĩa `BasicMetrics` như trên:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BasicMetrics> report = Arrays.asList(
        "API:1200", "UI:2000", "API:800"
    ).stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(
            line -> line.substring(0, line.indexOf(':')),
            Collectors.collectingAndThen(
                Collectors.summarizingLong(line ->
                    Long.parseLong(line.substring(line.indexOf(':') + 1))
                ),
                BasicMetrics::from
            )
        ),
        Map::copyOf
    ));

System.out.println(report.get("API").total()); // 2000
// report.put("OTHER", new BasicMetrics(...)); // Không được phép
```

`Map.copyOf` có từ Java 10: nó tạo một map **không sửa đổi được** từ map đầu vào. Kết hợp với `BasicMetrics` chỉ gồm primitive, ta được kết quả bất biến ở cấp map và ở cấp giá trị thống kê. Với các thành phần là `List`, `Map`, array hoặc bean mutable, chỉ dùng `record` vẫn **không đủ** để có tính bất biến sâu.

## 6. `teeing`: kết hợp hai phép tổng hợp độc lập vào một kết quả

`summarizingLong` cho năm chỉ số sẵn có. Nếu báo cáo cần **thêm một chỉ số khác**, ví dụ số đơn giao trễ, có thể dùng `Collectors.teeing` (Java 12+):

```java
Collectors.teeing(downstream1, downstream2, merger)
```

Mỗi phần tử đầu vào được đưa qua hai downstream collector; khi hoàn tất, `merger` nhận **hai kết quả** và tạo một kết quả cuối. Nhờ vậy, ta có thể tính `summarizingLong` và `counting` có lọc trong **một lần duyệt logic**.

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

record NumberReport(long count, long sum, long evenCount) {}

NumberReport report = Stream.of(2, 3, 4, 5)
    .collect(Collectors.teeing(
        Collectors.summarizingLong(Integer::longValue),
        Collectors.filtering(
            value -> value % 2 == 0,
            Collectors.counting()
        ),
        (stats, evens) -> new NumberReport(
            stats.getCount(), stats.getSum(), evens
        )
    ));

System.out.println(report); // NumberReport[count=4, sum=14, evenCount=2]
```

`Collectors.filtering` (Java 9+) là một downstream collector giúp **chỉ chuyển những phần tử đạt điều kiện vào collector con**. Trong ví dụ, `summarizingLong` tính trên **tất cả** các số, còn nhánh `counting` chỉ thấy số chẵn.

Đừng nhầm `Collectors.teeing` với chạy stream hai lần. Dù cả hai downstream xử lý mỗi phần tử theo hợp đồng của collector, **chỉ có một terminal `collect` trên nguồn**. Mặt khác, `teeing` vẫn duy trì **hai bộ trạng thái**; nó không miễn phí. Với nhiều chỉ số phức tạp và khối lượng lớn, collector tùy chỉnh có thể rõ ràng hoặc hiệu quả hơn.

## 7. Ví dụ hoàn chỉnh: báo cáo đa chỉ số bất biến theo đội

Ví dụ dưới đây dùng **Java 17+**, nên có thể sử dụng `record`, `Collectors.filtering`, `Collectors.teeing` và `Map.copyOf` cùng lúc. Mỗi nhóm chỉ gồm các đơn **đã thanh toán**; số đơn trễ là **số đơn trễ trong các đơn đã thanh toán**, không phải toàn bộ đơn gốc.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ImmutableSalesReport {
    record Sale(
        String team,
        String orderId,
        long amountInMinorUnits,
        boolean paid,
        boolean late
    ) {}

    record TeamMetrics(
        long orderCount,
        long totalAmount,
        long minimumAmount,
        long maximumAmount,
        double averageAmount,
        long lateCount
    ) {}

    static Map<String, TeamMetrics> buildReport(List<Sale> orders) {
        Collector<Sale, ?, TeamMetrics> metricsCollector =
            Collectors.teeing(
                Collectors.summarizingLong(Sale::amountInMinorUnits),
                Collectors.filtering(
                    Sale::late,
                    Collectors.counting()
                ),
                (LongSummaryStatistics stats, Long lateCount) ->
                    new TeamMetrics(
                        stats.getCount(),
                        stats.getSum(),
                        stats.getMin(),
                        stats.getMax(),
                        stats.getAverage(),
                        lateCount
                    )
            );

        return orders.stream()
            .filter(Sale::paid)
            .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Sale::team, metricsCollector),
                Map::copyOf
            ));
    }

    public static void main(String[] args) {
        List<Sale> orders = Arrays.asList(
            new Sale("API", "A-01", 1200L, true, false),
            new Sale("UI",  "U-01", 2000L, true, true),
            new Sale("API", "A-02",  800L, true, true),
            new Sale("UI",  "U-02",  500L, false, true),
            new Sale("API", "A-03",  900L, false, false)
        );

        Map<String, TeamMetrics> report = buildReport(orders);

        System.out.println(report.get("API"));
        // TeamMetrics[orderCount=2, totalAmount=2000,
        // minimumAmount=800, maximumAmount=1200,
        // averageAmount=1000.0, lateCount=1]

        System.out.println(report.get("UI").orderCount()); // 1
        System.out.println(report.get("UI").lateCount());  // 1

        // report.clear(); // UnsupportedOperationException
    }
}
```

Giải thích từng tầng:

1. `filter(Sale::paid)` loại đơn chưa thanh toán **khỏi mọi chỉ số**; vì vậy đội chỉ có đơn chưa thanh toán sẽ không xuất hiện trong map.
2. `groupingBy(Sale::team, metricsCollector)` phân phần tử đã lọc vào nhóm theo tên đội.
3. `summarizingLong` tích lũy `count/sum/min/max/average` cho **mỗi đội**.
4. `filtering(Sale::late, counting())` đếm những đơn trễ trong **cùng đội**.
5. Merger của `teeing` tạo `TeamMetrics` bất biến từ hai kết quả tạm.
6. `collectingAndThen(..., Map::copyOf)` chốt map ngoài thành không sửa đổi được.

Điểm đáng chú ý: `TeamMetrics` chỉ chứa primitive, nên không mang tham chiếu mutable vào kết quả. Các đối tượng tích lũy `LongSummaryStatistics` có thể thay đổi **bên trong lúc collect**, nhưng không thoát ra bên ngoài. Sau khi kết thúc, người sử dụng chỉ thấy map và các record.

### Những điều ví dụ không tự giải quyết

- **Không có đơn đã thanh toán:** `buildReport` trả map rỗng. `report.get("API")` lúc đó là `null`; mã gọi phải kiểm tra trước khi truy cập accessor.
- **Đội là `null`:** `groupingBy` mặc định không chấp nhận classifier trả `null`; cần chính sách xác thực hoặc chuẩn hóa dữ liệu.
- **Tràn số:** `LongSummaryStatistics.getSum()` vẫn dùng `long` và có thể tràn. Đây không phải tổng chính xác vô hạn.
- **Trung bình:** `getAverage()` trả `double`, không phải số tiền thập phân chính xác theo quy tắc làm tròn nghiệp vụ.
- **Thứ tự map:** `Map.copyOf` không bảo đảm thứ tự duyệt entry. Không dựa vào thứ tự in map để xác định thứ tự đội.

## 8. Đặt điều kiện ở đâu? `Stream.filter` khác `Collectors.filtering`

Hai cách đặt `filter` có thể đưa ra **báo cáo khác nhau**.

### Lọc trước `groupingBy`: nhóm không đạt điều kiện biến mất

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String team, boolean paid) {}

Map<String, Long> paidOnly = Arrays.asList(
        new Item("API", false),
        new Item("UI", true)
    ).stream()
    .filter(Item::paid)
    .collect(Collectors.groupingBy(
        Item::team,
        Collectors.counting()
    ));

System.out.println(paidOnly.containsKey("API")); // false
```

`API` bị loại hoàn toàn trước classifier, nên không có khóa `"API"` trong map.

### `Collectors.filtering` làm downstream: giữ nhóm đã xuất hiện

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

record Item(String team, boolean paid) {}

Map<String, Long> paidPerExistingTeam = Arrays.asList(
        new Item("API", false),
        new Item("UI", true)
    ).stream()
    .collect(Collectors.groupingBy(
        Item::team,
        Collectors.filtering(
            Item::paid,
            Collectors.counting()
        )
    ));

System.out.println(paidPerExistingTeam.get("API")); // 0
System.out.println(paidPerExistingTeam.get("UI"));  // 1
```

`groupingBy` tạo nhóm `API` từ bản ghi đã gặp, rồi downstream `filtering` không chuyển bản ghi không thanh toán vào `counting`. Vì vậy nhóm xuất hiện với giá trị `0`.

Với báo cáo quản trị, đây là lựa chọn ngữ nghĩa quan trọng: **“không có nhóm”** và **“có nhóm nhưng chưa có đơn hợp lệ”** không phải cùng một trạng thái.

## 9. Tổng hợp nhiều tầng và chốt bất biến đến cấp danh sách

Báo cáo nhiều tầng thường có dạng `Map<String, Map<Boolean, List<String>>>`: theo đội, rồi theo trạng thái hoàn thành, rồi đến danh sách mã công việc. Chỉ bọc map ngoài thành không sửa đổi được **không bảo vệ được map và list lồng bên trong**.

Ví dụ Java 17+:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Task(String team, String id, boolean done) {}

List<Task> tasks = Arrays.asList(
    new Task("API", "T-01", true),
    new Task("API", "T-02", false),
    new Task("UI", "T-03", true)
);

Map<String, Map<Boolean, List<String>>> report = tasks.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(
            Task::team,
            Collectors.collectingAndThen(
                Collectors.partitioningBy(
                    Task::done,
                    Collectors.mapping(
                        Task::id,
                        Collectors.collectingAndThen(
                            Collectors.toList(),
                            List::copyOf
                        )
                    )
                ),
                Map::copyOf
            )
        ),
        Map::copyOf
    ));

System.out.println(report.get("API").get(true));  // [T-01]
System.out.println(report.get("API").get(false)); // [T-02]
System.out.println(report.get("UI").get(false));  // []

// report.clear();                     // Không được
// report.get("API").clear();          // Không được
// report.get("API").get(true).add("X"); // Không được
```

Mỗi lớp có một công việc rõ ràng:

- `mapping(Task::id, ...)` chỉ giữ mã công việc trong danh sách.
- `collectingAndThen(toList(), List::copyOf)` chốt **từng danh sách** sau khi tích lũy.
- `partitioningBy(Task::done, ...)` tạo cả hai khóa Boolean cho mỗi đội xuất hiện.
- `Map.copyOf` bên trong chốt map trạng thái của từng đội.
- `Map.copyOf` bên ngoài chốt map các đội.

`List.copyOf`/`Map.copyOf` (Java 10+) từ chối phần tử hoặc giá trị `null` không hợp lệ; đồng thời đây vẫn là **bất biến nông**: nếu danh sách chứa các đối tượng mutable thay vì `String`, bản thân các đối tượng đó vẫn có thể thay đổi trạng thái. Với báo cáo lồng sâu, nên ưu tiên các kiểu giá trị bất biến ở lá.

Không có bảo đảm về thứ tự duyệt của các map do `Map.copyOf` tạo. Nếu giao diện phải trình bày đội theo thứ tự cố định, nên sắp xếp **tại bước hiển thị** hoặc thiết kế map thứ tự rõ ràng thay vì trông đợi `Map.copyOf` bảo toàn insertion order.

## 10. Khi nào cần collector tùy chỉnh?

`teeing` ghép đúng **hai** downstream collector trong một bước; muốn ghép ba nhánh trở lên có thể lồng `teeing`, nhưng biểu thức generic dễ dài và khó đọc. Một collector tùy chỉnh là lựa chọn khi:

- Cần nhiều chỉ số có thể cập nhật cùng lúc trong một accumulator nhỏ.
- Cần quy tắc phát hiện tràn, làm tròn hoặc xử lý dữ liệu lỗi đặc biệt.
- Cần tạo một kết quả bất biến riêng, không nên lộ các bộ chứa mutable bên trong.
- Việc lồng nhiều collector khiến code khó bảo trì hơn logic tích lũy trực tiếp.

Mẫu ý tưởng:

```text
Collector.of(
    Accumulator::new,          // supplier: tạo bộ tích lũy mới
    Accumulator::add,          // accumulator: nhận một phần tử
    Accumulator::combine,      // combiner: gộp hai bộ tích lũy độc lập
    Accumulator::toImmutable   // finisher: chốt DTO bất biến
)
```

Ở đây, `Accumulator` được phép mutable **trong phạm vi riêng của collector**. Supplier phải tạo instance mới, combiner phải gộp đúng cho mọi cách chia nguồn, và finisher phải tránh làm lộ trạng thái mutable ra ngoài. Đừng thay bằng `reduce(new ArrayList<>(), ...)` rồi sửa identity: `reduce` có hợp đồng khác và không cung cấp supplier tạo container riêng cho từng phần tích lũy.

**Không khai báo `Collector.Characteristics.CONCURRENT`** nếu accumulator tùy chỉnh chưa thật sự hỗ trợ nhiều thread cập nhật an toàn vào cùng một container. Cũng đừng khai báo `IDENTITY_FINISH` khi vẫn cần finisher để chuyển bộ tích lũy mutable thành DTO bất biến.

## 11. Độ chính xác của số liệu và hành vi trên dữ liệu rỗng

Báo cáo nhiều chỉ số dễ che giấu những vấn đề số học nếu chỉ quan tâm cấu trúc collector:

| Vấn đề | Hành vi cần biết | Cách xử lý |
| --- | --- | --- |
| Tổng nhiều `int` | `summingInt` trả `int`, có thể tràn | Cân nhắc `summingLong` hoặc `summarizingInt` có tổng kiểu `long` khi phù hợp. |
| Tổng `long` quá lớn | `LongSummaryStatistics` và `summingLong` vẫn có thể tràn | Xác thực giới hạn hoặc dùng `BigInteger`/`BigDecimal` theo nhu cầu. |
| Trung bình số thực | `getAverage()` trả `double` | Quy định sai số và làm tròn; không coi đây là số thập phân chính xác tuyệt đối. |
| Nhóm không có phần tử | `groupingBy` không tạo nhóm chưa xuất hiện | Kiểm tra `containsKey`/`get` trước khi truy cập DTO. |
| Bộ thống kê rỗng | Min/max có giá trị sentinel, average mặc định `0.0` | Kiểm tra `getCount()` hoặc dùng `OptionalLong`/`OptionalDouble`. |
| `NaN` hoặc vô cực | Có thể làm tổng/trung bình/mốc cực trị của thống kê `double` không có ý nghĩa | Kiểm soát dữ liệu đầu vào trước khi tổng hợp. |
| Khóa hoặc giá trị `null` | `groupingBy` không cho classifier trả `null`; `Map.copyOf` từ chối null | Xác thực, phân nhóm giá trị thiếu theo quy tắc rõ ràng, hoặc báo lỗi. |
| Thứ tự map | `groupingBy` và `Map.copyOf` không hứa iteration order | Sắp xếp riêng khi hiển thị hoặc chọn loại map có hợp đồng thứ tự. |

Ví dụ: nếu bộ thống kê dùng để tính một báo cáo toàn hệ thống (không qua `groupingBy`) và đầu vào rỗng, min/max từ `LongSummaryStatistics` **không phải** số đo. Thay vì tạo `TeamMetrics` từ nhóm rỗng với các sentinel, hãy biểu diễn thiếu dữ liệu bằng `Optional` hoặc một trạng thái báo cáo không có mẫu.

Với tiền tệ, tổng bằng `long` theo đơn vị nhỏ nhất giúp tránh nhiều sai số biểu diễn thập phân; tuy nhiên, **trung bình tiền** vẫn cần chính sách làm tròn nếu xuất hóa đơn hoặc chuyển đổi đơn vị. Khi yêu cầu độ chính xác cao hoặc tổng có thể vượt `long`, `BigDecimal` có thể phù hợp hơn.

## 12. Song song, thứ tự và tài nguyên

Collectors như `groupingBy`, `summarizingLong`, `teeing` được thiết kế để Stream API có thể tổ chức tích lũy các phần nguồn và kết hợp kết quả. Khi thêm `parallel()`, cần chú ý:

1. **Hàm hành vi không phụ thuộc trạng thái chia sẻ mutable:** classifier, predicate, mapper và merger nên thuần theo dữ liệu. Không cập nhật một `HashMap` ngoài pipeline trong `map` hoặc `filter`.
2. **Không yêu cầu thứ tự thực thi lambda:** encounter order của nguồn và iteration order của map đầu ra là những khái niệm khác nhau.
3. **Combiner của collector tùy chỉnh phải đúng hợp đồng:** không được dùng một container chung cho mọi nhánh, không được làm mất hoặc cộng trùng phần tử.
4. **Số thực có sai số:** tổng `double` khi song song có thể khác vài bit cuối do thứ tự phép cộng, ngay cả khi kết quả nghiệp vụ tương đương trong sai số cho phép.
5. **Bất biến không tự tạo thread-safety cho các giá trị lồng nhau:** map không sửa đổi được vẫn có thể giữ tham chiếu đến bean hoặc collection mutable.
6. **Hiệu năng không mặc nhiên tốt hơn:** `teeing`, `groupingBy` và `Map.copyOf` đều có chi phí tích lũy, gộp và chốt. Cần đo trên dữ liệu và workload thật.

Một báo cáo chỉ cần `count`, `sum` và các giá trị cực trị thường có thể được tính với bộ nhớ tỷ lệ **số nhóm**, không cần giữ toàn bộ từng bản ghi. Nhưng nếu downstream là `toList`, bộ nhớ vẫn tăng theo **số phần tử được lưu**.

`collect` là terminal operation; một `Stream` chỉ được vận hành một lần. Với nguồn như `Files.lines`, phải đóng stream bằng `try-with-resources`; `collect` không tự giải phóng mọi tài nguyên I/O. Với nguồn vô hạn, các collector tổng hợp toàn bộ dữ liệu thường không thể kết thúc nếu không có `limit` hoặc điều kiện dừng.

## 13. Chọn cách ghép collector theo yêu cầu

| Yêu cầu | Gợi ý thiết kế | Lý do |
| --- | --- | --- |
| Count/sum/min/max/average của một trường | `summarizingInt/Long/Double` | Năm chỉ số trong một bộ thống kê. |
| Năm chỉ số theo nhóm | `groupingBy(key, summarizingLong(...))` | Tích lũy từng nhóm trong một pipeline. |
| Năm chỉ số + một chỉ số điều kiện | `teeing(summarizingLong(...), filtering(..., counting()), merger)` | Hai downstream, một DTO kết quả. |
| Biến thống kê mutable thành record | `collectingAndThen(summarizingLong(...), Metrics::from)` | Không làm lộ bộ tích lũy mutable. |
| Chốt map các nhóm thành không sửa đổi được | `collectingAndThen(groupingBy(...), Map::copyOf)` | Không cho sửa ánh xạ sau khi chốt. |
| Map lồng danh sách bất biến | `mapping(..., collectingAndThen(toList(), List::copyOf))` và chốt từng map | Bảo vệ nhiều tầng dữ liệu. |
| Nhiều chỉ số phụ thuộc nhau, logic phức tạp | `Collector.of` với accumulator riêng và immutable finisher | Kiểm soát trạng thái và phép gộp. |
| Cần thứ tự khóa ổn định khi hiển thị | Sắp xếp ở tầng hiển thị hoặc dùng map có thứ tự xác định | `Map.copyOf` không giữ bảo đảm thứ tự chèn. |

### Sai lầm thường gặp

- Gọi nhiều terminal operation trên **cùng một stream**: stream đã tiêu thụ sẽ không dùng lại được.
- Trả trực tiếp `LongSummaryStatistics` rồi gọi đó là “báo cáo bất biến”: đối tượng vẫn có `accept` và `combine`.
- Bọc `Map` ngoài nhưng để `List` hay `Map` con mutable: người dùng vẫn thay đổi được dữ liệu lồng.
- Dùng `Stream.filter` trong khi cần giữ nhóm có **0 kết quả hợp lệ**: `Collectors.filtering` ở downstream có ý nghĩa khác.
- Cho rằng `teeing` tạo đúng một accumulator duy nhất: thực tế có **hai downstream** và một merger.
- Dùng tổng `long` mà không xem xét tràn, hoặc trung bình `double` mà không có chính sách sai số.
- Mặc định kết quả `groupingBy` đã chứa mọi nhóm nghiệp vụ: chỉ các nhóm thực sự xuất hiện mới được tạo.
- Giả định `Map.copyOf` bảo toàn thứ tự và sao chép sâu các đối tượng giá trị.
- Đánh dấu `CONCURRENT` hay `IDENTITY_FINISH` cho collector tùy chỉnh khi chưa đáp ứng hợp đồng tương ứng.

## 14. Bài tập thực hành

**Bài 1 — Báo cáo theo nhóm.** Cho `List<String>` gồm `["API:10", "UI:20", "API:30"]`. Dùng `groupingBy` và `summarizingLong` để tính số lượng, tổng, min, max và trung bình theo đội. Kiểm tra đội `API` có count = 2, sum = 40, average = 20.0.

**Bài 2 — Chốt kết quả.** Tạo `record Metrics(long count, long sum)`. Dùng `collectingAndThen(summarizingLong(...), stats -> new Metrics(...))` cho mỗi nhóm, sau đó chốt map bằng `Map.copyOf`. Thử gọi `put` trên kết quả và giải thích tại sao bị từ chối.

**Bài 3 — `teeing`.** Trên dữ liệu `Stream.of(1, 2, 3, 4, 5)`, vừa tính `summarizingInt` cho toàn bộ phần tử, vừa đếm số chẵn bằng `filtering(n -> n % 2 == 0, counting())`. Gộp thành một record; dự đoán count = 5, sum = 15, số chẵn = 2.

**Bài 4 — Vị trí của filter.** Với nhóm `API` chỉ có đơn `paid = false`, so sánh `stream.filter(paid).collect(groupingBy(team, counting()))` và `stream.collect(groupingBy(team, filtering(paid, counting())))`. Phương án nào không có khóa `API`, phương án nào trả `API -> 0`?

**Bài 5 — Bất biến nhiều tầng.** Tạo `Map<String, Map<Boolean, List<String>>>` theo đội và trạng thái hoàn tất, rồi dùng `List.copyOf` và `Map.copyOf` để chốt các lớp. Xác minh không thể `put` vào map ngoài, `put` vào map con hoặc `add` vào list, đồng thời giải thích vì sao một bean mutable bên trong danh sách vẫn cần bảo vệ riêng.

**Bài 6 — Kiểm tra dữ liệu rỗng.** Chạy báo cáo trên danh sách rỗng. Tại sao `groupingBy` trả map rỗng mà không tạo các đội `API`, `UI`? Nếu nghiệp vụ bắt buộc hiển thị mọi đội, hãy đề xuất cách bổ sung danh mục đội và giá trị mặc định **sau khi** tổng hợp hoặc dùng cấu trúc báo cáo đã có các đội được xác định.

**Ghi nhớ:** Để tạo báo cáo nhiều chỉ số, hãy đặt `groupingBy` ở tầng phân loại, `summarizing*` hoặc `teeing` ở tầng tổng hợp, và `collectingAndThen` ở tầng chốt kết quả. Collector có thể dùng trạng thái mutable **trong lúc xử lý**, nhưng giá trị công bố nên là DTO bất biến và map/list không sửa đổi được theo đúng mức độ mà nghiệp vụ yêu cầu. Đừng bỏ qua nhóm rỗng, kiểu số, thứ tự duyệt hoặc sự khác biệt giữa bất biến nông và bất biến sâu.
