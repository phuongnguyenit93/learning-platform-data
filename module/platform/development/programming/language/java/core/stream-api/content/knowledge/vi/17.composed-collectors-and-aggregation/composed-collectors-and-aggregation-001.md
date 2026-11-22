# Đếm và tính tổng từng nhóm bằng counting và summing

Một bài toán thường gặp trong Java Stream API là: **mỗi khu vực có bao nhiêu đơn hàng và tổng doanh thu bao nhiêu?** Nếu chỉ gọi `count()` hoặc `sum()` trên toàn bộ Stream, ta có một con số cho tất cả dữ liệu. Muốn có **một kết quả cho từng nhóm**, hãy kết hợp `Collectors.groupingBy(...)` với một *downstream collector* như `Collectors.counting()` hoặc `Collectors.summingLong(...)`.

Bài học thuộc chương **Collector nhiều tầng và tổng hợp** của mô-đun **JAVA_STREAM_API**. Ta sẽ thực hành đếm, tính tổng, nhóm hai tầng, kết hợp nhiều đại lượng và xử lý nhóm không có dữ liệu. Các ví dụ cũng giải thích mối liên hệ với pipeline lazy (`filter`, `map`, `collect`), hợp đồng collector, kiểu số, xử lý song song và hiệu năng. Trọng tâm không phải gọi thật nhiều API, mà là **phân biệt đúng phần tử được nhóm, khóa nhóm và phép tổng hợp trong từng nhóm**.

## 1. Tư duy hai tầng: phân nhóm và tổng hợp

Xét danh sách đơn hàng với ba thông tin chính: khu vực, loại sản phẩm và số tiền.

```java
import java.util.List;

record Order(
    String id,
    String region,
    String category,
    long amountVnd,
    boolean paid
) {}

List<Order> orders = List.of(
    new Order("O-01", "Bắc",   "Sách", 120_000L, true),
    new Order("O-02", "Nam",   "Bút",   30_000L, true),
    new Order("O-03", "Bắc",   "Sách",  80_000L, false),
    new Order("O-04", "Bắc",   "Bút",   50_000L, true),
    new Order("O-05", "Nam",   "Sách", 100_000L, true),
    new Order("O-06", "Trung", "Bút",   40_000L, true),
    new Order("O-07", "Tây",   "Sách",  75_000L, false)
);
```

Dữ liệu có **7 đơn**, trong đó **5 đơn đã thanh toán**. Hai đơn chưa thanh toán là `O-03` và `O-07`.

Nếu yêu cầu “đếm số đơn theo khu vực”, ta cần tạo bốn nhóm: Bắc, Nam, Trung, Tây, rồi đếm từng nhóm. Có thể hình dung:

```text
                  orders.stream()
                         |
             groupingBy(Order::region)
                         |
          +--------------+---------------+-----------+
          |              |               |           |
         Bắc            Nam            Trung        Tây
       3 đơn           2 đơn           1 đơn       1 đơn
          |              |               |           |
      counting()     counting()      counting()  counting()
          |              |               |           |
          3L             2L              1L          1L
                         |
                  Map<String, Long>
```

Hai công việc độc lập về ý nghĩa:

1. **Classifier** của `groupingBy` xác định **khóa** mà mỗi phần tử thuộc về.
2. **Downstream collector** xác định **giá trị** được tích lũy cho từng khóa.

Nếu thay `counting()` bằng `summingLong(Order::amountVnd)`, khóa nhóm vẫn giữ nguyên nhưng giá trị mỗi nhóm chuyển từ **số đơn** sang **tổng tiền**.

## 2. `Collectors.counting()`: đếm phần tử của từng nhóm

`Collectors.counting()` là collector dùng để đếm số phần tử đi vào nó. Kiểu kết quả là `Long`.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(countByRegion.get("Bắc"));   // 3
System.out.println(countByRegion.get("Nam"));   // 2
System.out.println(countByRegion.get("Trung")); // 1
System.out.println(countByRegion.get("Tây"));   // 1
```

Ở đây:

- `orders.stream()` tạo `Stream<Order>`.
- `Order::region` là `Function<Order, String>` chọn khóa nhóm.
- `Collectors.counting()` đếm số phần tử trong **mỗi nhóm**.
- `groupingBy` tạo một collector có kết quả là `Map<String, Long>`.
- `collect(...)` là terminal operation kích hoạt xử lý Stream.

### 2.1. Khác nhau giữa `stream.count()` và `Collectors.counting()`

```java
long totalOrders = orders.stream().count(); // 7

Map<String, Long> perRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
```

`stream.count()` trả về **một** giá trị `long` cho toàn bộ phần tử còn lại của pipeline. `Collectors.counting()` là **một collector**, có thể đặt làm downstream của `groupingBy` để trả về số lượng **riêng cho từng nhóm**.

| Nhu cầu | Cách viết phù hợp | Kiểu kết quả |
| --- | --- | --- |
| Đếm tất cả đơn | `orders.stream().count()` | `long` |
| Đếm đơn theo khu vực | `groupingBy(Order::region, counting())` | `Map<String, Long>` |
| Đếm đơn đã thanh toán theo khu vực | `filter(Order::paid)` rồi `groupingBy(..., counting())` | `Map<String, Long>` |
| Chỉ đếm đơn thuộc một khu vực | `filter(...).count()` | `long` |

Chọn `count()` khi không cần khóa nhóm. Chọn `counting()` khi số lượng là **giá trị của một phép thu thập**.

### 2.2. Kết quả là `Long`, không phải `Integer`

`Collectors.counting()` trả về `Long`, nên khai báo đúng là:

```java
Map<String, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
```

Không khai báo `Map<String, Integer>` và không ép kiểu kết quả theo suy đoán. `Long` là kiểu số nguyên 64 bit; với tập dữ liệu thông thường, nó phù hợp để đếm số bản ghi lớn. Dù vậy, mọi kiểu nguyên hữu hạn đều có giới hạn, và việc dùng `Long` không làm nguồn dữ liệu lớn trở nên miễn phí về thời gian hoặc bộ nhớ.

## 3. `summingInt`, `summingLong` và `summingDouble`

Nếu `counting()` đếm **bao nhiêu** phần tử, các collector `summingX` tính tổng **một thuộc tính số** được trích xuất từ phần tử.

| Downstream collector | Hàm trích xuất | Kiểu kết quả | Trường hợp điển hình |
| --- | --- | --- | --- |
| `Collectors.summingInt(...)` | `ToIntFunction<T>` | `Integer` | Tổng số lượng `int` |
| `Collectors.summingLong(...)` | `ToLongFunction<T>` | `Long` | Tổng giá trị `long`, ví dụ tiền theo đơn vị nguyên |
| `Collectors.summingDouble(...)` | `ToDoubleFunction<T>` | `Double` | Tổng số đo `double` |

Ba collector này nhận hàm **ánh xạ phần tử sang số**. Với đối tượng `Order`, `Order::amountVnd` là một `ToLongFunction<Order>` thích hợp.

```java
Map<String, Long> amountByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

System.out.println(amountByRegion.get("Bắc"));   // 250000
System.out.println(amountByRegion.get("Nam"));   // 130000
System.out.println(amountByRegion.get("Trung")); // 40000
System.out.println(amountByRegion.get("Tây"));   // 75000
```

Đây là **tổng mọi đơn**, kể cả đơn chưa thanh toán. Nếu yêu cầu là doanh thu đã thu tiền, phải lọc theo `paid` trước khi cộng hoặc áp dụng bộ lọc downstream có chủ đích.

### 3.1. `summingInt` cho số lượng hàng hóa

```java
record CartLine(String category, int quantity) {}

List<CartLine> lines = List.of(
    new CartLine("Sách", 2),
    new CartLine("Bút", 5),
    new CartLine("Sách", 3)
);

Map<String, Integer> quantityByCategory = lines.stream()
    .collect(Collectors.groupingBy(
        CartLine::category,
        Collectors.summingInt(CartLine::quantity)
    ));

System.out.println(quantityByCategory.get("Sách")); // 5
System.out.println(quantityByCategory.get("Bút"));  // 5
```

Kết quả là `Map<String, Integer>` vì `summingInt` trả về `Integer`.

### 3.2. `summingLong` cho tổng tiền nguyên

```java
Map<String, Long> paidRevenueByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));

System.out.println(paidRevenueByRegion.get("Bắc"));   // 170000
System.out.println(paidRevenueByRegion.get("Nam"));   // 130000
System.out.println(paidRevenueByRegion.get("Trung")); // 40000
System.out.println(paidRevenueByRegion.containsKey("Tây")); // false
```

Vì khu vực Tây **không có đơn đã thanh toán**, nó **không có khóa** trong Map kết quả khi ta lọc trước khi nhóm. Đây là khác biệt quan trọng giữa “không có nhóm” và “nhóm có tổng bằng 0”.

### 3.3. `summingDouble` cho dữ liệu số thực

```java
record SensorReading(String device, double value) {}

List<SensorReading> readings = List.of(
    new SensorReading("S1", 1.25),
    new SensorReading("S1", 2.50),
    new SensorReading("S2", 3.00)
);

Map<String, Double> totalByDevice = readings.stream()
    .collect(Collectors.groupingBy(
        SensorReading::device,
        Collectors.summingDouble(SensorReading::value)
    ));

System.out.println(totalByDevice.get("S1")); // 3.75
System.out.println(totalByDevice.get("S2")); // 3.0
```

`double` sử dụng số thực dấu phẩy động nhị phân. Với các số không thể biểu diễn chính xác bằng nhị phân, thứ tự cộng và cách gom các phần khi chạy song song có thể ảnh hưởng chữ số cuối của kết quả. Không dùng `summingDouble` cho tiền cần độ chính xác thập phân tuyệt đối nếu chưa có mô hình làm tròn phù hợp.

## 4. Lọc trước hay sau khi phân nhóm?

`filter` trong pipeline và `Collectors.filtering` trong downstream đều hữu ích, nhưng **chúng không tạo ra cùng bộ khóa**.

### 4.1. Lọc toàn nguồn trước `groupingBy`

```java
Map<String, Long> paidCounts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(paidCounts.get("Bắc"));  // 2
System.out.println(paidCounts.get("Nam"));  // 2
System.out.println(paidCounts.get("Trung")); // 1
System.out.println(paidCounts.containsKey("Tây")); // false
```

Chỉ những đơn đã thanh toán đến được `groupingBy`. Khu vực Tây không có phần tử được nhóm nên **không xuất hiện**.

### 4.2. Lọc bên trong mỗi nhóm bằng `Collectors.filtering`

Từ Java 9, `Collectors.filtering(predicate, downstream)` cho phép áp dụng bộ lọc **trong quá trình downstream thu thập**:

```java
Map<String, Long> paidCountsIncludingZero = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            Order::paid,
            Collectors.counting()
        )
    ));

System.out.println(paidCountsIncludingZero.get("Bắc")); // 2
System.out.println(paidCountsIncludingZero.get("Nam")); // 2
System.out.println(paidCountsIncludingZero.get("Trung")); // 1
System.out.println(paidCountsIncludingZero.get("Tây")); // 0
```

Tất cả **khu vực đã xuất hiện trong nguồn** đều được `groupingBy` tạo nhóm; downstream `filtering` không đếm đơn chưa thanh toán, nên nhóm Tây có kết quả `0L`.

Kết quả tổng tiền tương tự:

```java
Map<String, Long> revenueIncludingZero = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            Order::paid,
            Collectors.summingLong(Order::amountVnd)
        )
    ));

System.out.println(revenueIncludingZero.get("Tây")); // 0
```

**Lưu ý:** Nếu một khu vực hoàn toàn không có trong nguồn (ví dụ `"Đông"`), ngay cả `Collectors.filtering` cũng không tự tạo khóa đó. Nếu báo cáo phải thể hiện đủ mọi khu vực hợp lệ, cần có danh mục khu vực chuẩn và bổ sung những khóa còn thiếu theo quy tắc nghiệp vụ.

### 4.3. Quy tắc chọn cách lọc

| Yêu cầu | Đặt `filter` ở đâu? | Nhóm chỉ có phần tử không đạt điều kiện |
| --- | --- | --- |
| Chỉ hiện khu vực có đơn đã thanh toán | Trước `groupingBy` | Không có khóa |
| Hiện mọi khu vực từng có đơn, kể cả doanh thu thanh toán bằng 0 | Bên trong downstream `Collectors.filtering` | Có khóa với giá trị 0 |
| Hiện cả khu vực chưa từng có đơn | Bổ sung danh mục khóa từ bên ngoài dữ liệu | Phải tạo khóa tường minh |

Vị trí đặt phép lọc là một quyết định về **ý nghĩa báo cáo**, không chỉ là cách viết khác nhau.

## 5. Nhóm nhiều tầng: `groupingBy` lồng `groupingBy`

Khi yêu cầu có hai chiều, chẳng hạn “theo khu vực rồi theo loại sản phẩm”, đặt một `groupingBy` bên trong downstream của `groupingBy` ngoài.

### 5.1. Đếm đơn theo khu vực và loại sản phẩm

```java
Map<String, Map<String, Long>> countsByRegionAndCategory =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.groupingBy(
                Order::category,
                Collectors.counting()
            )
        ));

System.out.println(countsByRegionAndCategory.get("Bắc").get("Sách")); // 1
System.out.println(countsByRegionAndCategory.get("Bắc").get("Bút"));  // 1
System.out.println(countsByRegionAndCategory.get("Nam").get("Sách")); // 1
System.out.println(countsByRegionAndCategory.get("Trung").get("Bút")); // 1
```

Kiểu kết quả là `Map<String, Map<String, Long>>`:

- Khóa Map ngoài: `region`.
- Khóa Map trong: `category`.
- Giá trị trong cùng: số lượng đơn đã thanh toán của ô giao nhau.

Sơ đồ:

```text
Stream<Order> (chỉ đơn paid)
    |
    +-- groupingBy(region)
           |
           +-- Bắc
           |    +-- groupingBy(category)
           |           +-- Sách → counting() → 1L
           |           +-- Bút  → counting() → 1L
           |
           +-- Nam
           |    +-- Sách → 1L
           |    +-- Bút  → 1L
           |
           +-- Trung
                +-- Bút  → 1L
```

Cấu trúc Map lồng nhau chỉ có các khóa thực sự xuất hiện sau bước lọc. Do đó, `countsByRegionAndCategory.get("Trung").get("Sách")` trả về `null`, không phải tự động `0L`.

### 5.2. Tính tổng theo hai tầng

Chỉ cần đổi collector ở tầng cuối thành `summingLong`:

```java
Map<String, Map<String, Long>> revenueByRegionAndCategory =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.groupingBy(
                Order::category,
                Collectors.summingLong(Order::amountVnd)
            )
        ));

System.out.println(revenueByRegionAndCategory.get("Bắc").get("Sách")); // 120000
System.out.println(revenueByRegionAndCategory.get("Bắc").get("Bút"));  // 50000
System.out.println(revenueByRegionAndCategory.get("Nam").get("Sách")); // 100000
System.out.println(revenueByRegionAndCategory.get("Nam").get("Bút"));  // 30000
```

Mặc dù hai biểu thức có cùng dạng Map bên ngoài và bên trong, **ý nghĩa của giá trị cuối khác nhau**. Hãy đặt tên biến, kiểu báo cáo và tài liệu API sao cho không nhầm `count` với `amount`.

### 5.3. Thứ tự các chiều nhóm có ý nghĩa

`groupingBy(region, groupingBy(category, ...))` tạo Map ngoài theo khu vực. Đổi thứ tự thành `groupingBy(category, groupingBy(region, ...))` tạo Map ngoài theo loại sản phẩm. Hai báo cáo có cùng các ô tổng hợp về mặt logic, nhưng **cấu trúc và cách truy xuất khác nhau**. Chọn chiều ngoài theo nhu cầu truy cập chính của nghiệp vụ.

## 6. Đếm và tính tổng trong cùng một lượt thu thập

Nếu muốn **cả số đơn và tổng tiền** cho mỗi khu vực, có thể dùng hai pipeline riêng, nhưng cách đó có thể duyệt nguồn hai lần:

```java
Map<String, Long> counts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region, Collectors.counting()
    ));

Map<String, Long> sums = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

Với nguồn là `List` ổn định, hai lượt thường dễ hiểu. Tuy nhiên, khi cần **một bản báo cáo nhất quán**, có thể ghép hai downstream collector bằng `Collectors.teeing` (Java 12+).

### 6.1. `teeing` với `counting` và `summingLong`

```java
import java.util.Map;
import java.util.stream.Collectors;

record RegionStats(long orderCount, long totalVnd) {}

Map<String, RegionStats> statsByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Order::amountVnd),
            RegionStats::new
        )
    ));

System.out.println(statsByRegion.get("Bắc"));   // RegionStats[orderCount=2, totalVnd=170000]
System.out.println(statsByRegion.get("Nam"));   // RegionStats[orderCount=2, totalVnd=130000]
System.out.println(statsByRegion.get("Trung")); // RegionStats[orderCount=1, totalVnd=40000]
```

Hai downstream collector nhận **cùng các phần tử của từng nhóm**, sau đó `teeing` kết hợp hai kết quả thành một `RegionStats`:

```text
                 Mỗi nhóm Order
                       |
         +-------------+--------------+
         |                            |
       counting()               summingLong(amount)
         |                            |
     Long count                  Long total
         +-------------+--------------+
                       |
                 RegionStats::new
                       |
                   RegionStats
```

Đây là cách **kết hợp collector**, không phải tự chia Stream thành hai nhánh để sử dụng lại. Nó cũng tránh phải đưa một bộ đếm mutable ở ngoài lambda. Khi kết quả cần nhiều thống kê hơn, có thể dùng `summarizingLong` hoặc collector tùy chỉnh, thay vì lồng `teeing` quá sâu đến mức khó đọc.

### 6.2. Khi chỉ cần thống kê một trường số

`Collectors.summarizingLong` trả về `LongSummaryStatistics` gồm `count`, `sum`, `min`, `max` và `average`:

```java
import java.util.LongSummaryStatistics;

Map<String, LongSummaryStatistics> summaryByRegion =
    orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
            Order::region,
            Collectors.summarizingLong(Order::amountVnd)
        ));

LongSummaryStatistics north = summaryByRegion.get("Bắc");

System.out.println(north.getCount());   // 2
System.out.println(north.getSum());     // 170000
System.out.println(north.getMin());     // 50000
System.out.println(north.getMax());     // 120000
System.out.println(north.getAverage()); // 85000.0
```

Nếu yêu cầu vừa đếm vừa cộng **cùng một giá trị số**, `summarizingLong` là lựa chọn gọn. Nếu phép đếm và phép cộng có **điều kiện khác nhau**, dùng `teeing` với các downstream `filtering` phù hợp, hoặc định nghĩa một collector tổng hợp riêng.

## 7. Phân biệt đếm phần tử, đếm khóa và đếm nhóm

`counting()` đếm số **phần tử** đến với mỗi downstream, không đếm số lượng khóa Map.

```java
Map<String, Long> byRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

int numberOfRegions = byRegion.size();  // 4
long allOrders = orders.stream().count(); // 7
long northernOrders = byRegion.get("Bắc"); // 3
```

Ba kết quả trả lời ba câu hỏi khác nhau:

| Giá trị | Câu hỏi | Kết quả |
| --- | --- | ---: |
| `byRegion.size()` | Có bao nhiêu khóa khu vực khác nhau? | 4 |
| `orders.stream().count()` | Tổng bao nhiêu đơn? | 7 |
| `byRegion.get("Bắc")` | Khu vực Bắc có bao nhiêu đơn? | 3 |

Nếu muốn đếm số **SKU duy nhất trong mỗi khu vực**, cần đổi ý nghĩa downstream:

```java
record Item(String region, String sku) {}

List<Item> items = List.of(
    new Item("Bắc", "P-01"),
    new Item("Bắc", "P-01"),
    new Item("Bắc", "P-02"),
    new Item("Nam", "P-01")
);

Map<String, Long> distinctSkuByRegion = items.stream()
    .collect(Collectors.groupingBy(
        Item::region,
        Collectors.mapping(
            Item::sku,
            Collectors.collectingAndThen(
                Collectors.toSet(),
                set -> (long) set.size()
            )
        )
    ));

System.out.println(distinctSkuByRegion.get("Bắc")); // 2
System.out.println(distinctSkuByRegion.get("Nam")); // 1
```

Ở đây không dùng `counting()` trực tiếp, vì nó sẽ đếm cả hai lần xuất hiện của `P-01`. Ta chuyển các phần tử thành SKU, gom thành tập giá trị duy nhất rồi đếm số thành viên tập. Đây là một ví dụ của **composed collectors**; chọn quy tắc đếm theo đúng đơn vị nghiệp vụ.

## 8. Stream rỗng, nhóm không tồn tại và giá trị 0

Trường hợp rỗng cần phân biệt ở ba cấp:

1. **Toàn bộ Stream rỗng:** không có phần tử để tạo khóa.
2. **Một nhóm không xuất hiện:** Map không chứa khóa đó.
3. **Một nhóm có phần tử nguồn, nhưng downstream `filtering` loại hết:** nhóm có thể vẫn tồn tại với số lượng hoặc tổng bằng 0.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Order> noOrders = List.of();

Map<String, Long> emptyCounts = noOrders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(emptyCounts.isEmpty()); // true
System.out.println(emptyCounts.get("Bắc")); // null
```

`counting()` riêng trên một tập rỗng cho `0L`, nhưng `groupingBy` **không gọi downstream để tạo kết quả cho những khóa chưa từng có phần tử**. Vì vậy, Map rỗng khác với Map chứa `"Bắc" -> 0L`.

### 8.1. Đọc kết quả với giá trị mặc định

```java
long northCount = emptyCounts.getOrDefault("Bắc", 0L);
System.out.println(northCount); // 0
```

`getOrDefault` giúp trình bày số 0 khi khóa vắng mặt, nhưng nó **không thêm khóa vào Map**. Nếu “chưa có dữ liệu” và “có nhóm với tổng bằng 0” là hai trạng thái khác nhau trong nghiệp vụ, đừng dùng mặc định `0L` để xóa đi sự khác biệt.

### 8.2. Khởi tạo các nhóm hợp lệ từ danh mục nghiệp vụ

Nếu giao diện bắt buộc luôn thể hiện năm khu vực, kể cả `"Đông"` chưa có đơn:

```java
import java.util.LinkedHashMap;

List<String> regions = List.of("Bắc", "Trung", "Nam", "Tây", "Đông");

Map<String, Long> paidCounts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

Map<String, Long> complete = new LinkedHashMap<>();
for (String region : regions) {
    complete.put(region, paidCounts.getOrDefault(region, 0L));
}

System.out.println(complete);
// {Bắc=2, Trung=1, Nam=2, Tây=0, Đông=0}
```

Bước bổ sung danh mục diễn ra **sau khi thu thập**. Nó giúp kiểm soát chính xác những nhóm nào phải tồn tại và thứ tự hiển thị; thay đổi collector đơn thuần không thể suy ra các khu vực chưa có trong nguồn.

## 9. Kiểu Map, thứ tự khóa và nhóm nhiều tầng

`Collectors.groupingBy(classifier, downstream)` **không cam kết** kiểu Map cụ thể hoặc thứ tự duyệt khóa. Khi yêu cầu thứ tự, có thể chọn overload ba tham số với `mapFactory`:

```java
import java.util.LinkedHashMap;
import java.util.TreeMap;

LinkedHashMap<String, Long> byFirstSeenRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.counting()
    ));

TreeMap<String, Long> bySortedRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.summingLong(Order::amountVnd)
    ));
```

Với nguồn `List` và pipeline **tuần tự** như ví dụ, `LinkedHashMap` duyệt khóa theo thứ tự chèn (Bắc, Nam, Trung, Tây). `TreeMap` duyệt theo thứ tự so sánh khóa tự nhiên của `String`; thứ tự này không nhất thiết tương đương quy tắc sắp chữ tiếng Việt.

Map ngoài của một báo cáo nhóm hai tầng có thể là `TreeMap` và Map trong là `LinkedHashMap`:

```java
Map<String, Map<String, Long>> report =
    orders.stream()
        .collect(Collectors.groupingBy(
            Order::region,
            TreeMap::new,
            Collectors.groupingBy(
                Order::category,
                LinkedHashMap::new,
                Collectors.counting()
            )
        ));
```

Chọn thứ tự và kiểu Map theo **cách sử dụng kết quả**, không chỉ theo vẻ đẹp của code.

## 10. `partitioningBy` khi khóa chỉ có hai trạng thái

Nếu mục tiêu là nhóm theo một điều kiện đúng/sai, ví dụ đơn đã thanh toán hay chưa, `Collectors.partitioningBy` là một lựa chọn chuyên biệt.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> countByPayment = orders.stream()
    .collect(Collectors.partitioningBy(
        Order::paid,
        Collectors.counting()
    ));

System.out.println(countByPayment.get(true));  // 5
System.out.println(countByPayment.get(false)); // 2
```

`partitioningBy` trả Map chứa **cả hai khóa `true` và `false`**, ngay cả khi một phía không có phần tử. Downstream `counting()` khi không có phần tử của một phía trả `0L`.

```java
Map<Boolean, Long> emptyPartition = List.<Order>of()
    .stream()
    .collect(Collectors.partitioningBy(
        Order::paid,
        Collectors.counting()
    ));

System.out.println(emptyPartition.get(true));  // 0
System.out.println(emptyPartition.get(false)); // 0
```

Điều này khác với `groupingBy(Order::paid, counting())` trên Stream rỗng: `groupingBy` trả Map rỗng. Nếu chỉ có hai trạng thái boolean và cần luôn có cả hai kết quả, `partitioningBy` thể hiện ý định tốt.

## 11. Độ chính xác số học khi tổng hợp nhóm

Các collector không kiểm tra tràn số thay cho ứng dụng. Điều kiện này đặc biệt quan trọng với báo cáo số lượng lớn và tiền.

### 11.1. `summingInt` có thể tràn số `int`

```java
record Stock(String warehouse, int units) {}

List<Stock> stocks = List.of(
    new Stock("K1", 1_500_000_000),
    new Stock("K1", 1_500_000_000)
);

Map<String, Integer> wrongTotals = stocks.stream()
    .collect(Collectors.groupingBy(
        Stock::warehouse,
        Collectors.summingInt(Stock::units)
    ));

Map<String, Long> longTotals = stocks.stream()
    .collect(Collectors.groupingBy(
        Stock::warehouse,
        Collectors.summingLong(stock -> (long) stock.units())
    ));

System.out.println(wrongTotals.get("K1")); // -1294967296
System.out.println(longTotals.get("K1"));  // 3000000000
```

`summingInt` trả về `Integer` và cộng trong miền `int`. Nếu tổng có thể vượt `int`, cần chuyển kiểu **trước phép cộng**, không phải chỉ gán Map kết quả sang một biến chứa `Long`.

### 11.2. `summingLong` cũng có thể tràn

`Long.MAX_VALUE + 1L` không chứa được trong `long`. Nếu nghiệp vụ cần tổng nguyên lớn hơn giới hạn 64 bit, có thể kết hợp `groupingBy` với `Collectors.reducing` trên `BigInteger`:

```java
import java.math.BigInteger;

record LargeTransfer(String group, long amount) {}

List<LargeTransfer> transfers = List.of(
    new LargeTransfer("A", Long.MAX_VALUE),
    new LargeTransfer("A", 1L)
);

Map<String, BigInteger> exactTotals = transfers.stream()
    .collect(Collectors.groupingBy(
        LargeTransfer::group,
        Collectors.reducing(
            BigInteger.ZERO,
            transfer -> BigInteger.valueOf(transfer.amount()),
            BigInteger::add
        )
    ));

System.out.println(exactTotals.get("A")); // 9223372036854775808
```

`BigInteger` tính tổng số nguyên chính xác theo giá trị đã có trong nguồn. Nó không sửa lỗi nếu phép nhân hoặc ép kiểu **trước đó** đã tràn số. Với tiền thập phân, cân nhắc `BigDecimal` và quy tắc làm tròn nghiệp vụ thay vì đổi sang `double`.

### 11.3. `summingDouble` có giới hạn của số thực

`summingDouble` không cam kết tổng thập phân chính xác tuyệt đối: kết quả có thể sai khác do làm tròn nhị phân, độ lớn các toán hạng và thứ tự cộng. Nếu dữ liệu chứa `NaN` hoặc vô cực, phải định nghĩa chính sách xử lý số đo bất thường. Với số tiền chính xác theo đơn vị thập phân, dùng `BigDecimal` khi mô hình nghiệp vụ yêu cầu.

### 11.4. Kiểu số của biểu thức ánh xạ cũng quan trọng

Với `record Line(String group, int quantity, int priceVnd)`, mã sau vẫn có thể tràn `int` **trước khi summingLong nhận kết quả**:

```java
// Có nguy cơ sai: phép nhân int * int diễn ra trước khi mở rộng sang long.
Collectors.summingLong(line -> line.quantity() * line.priceVnd())
```

Cách đúng hơn khi phép nhân vừa miền `long`:

```java
Collectors.summingLong(
    line -> (long) line.quantity() * line.priceVnd()
)
```

Nếu cả tích hoặc tổng có thể vượt miền `long`, phải dùng kiểu lớn hơn và kiểm tra giới hạn theo nghiệp vụ.

## 12. Tính lazy, chi phí và song song

`filter`, `map` và các thao tác trung gian được đánh giá **lazy**. `collect` là terminal operation kích hoạt duyệt các phần tử cần thiết.

```java
var selected = orders.stream()
    .filter(Order::paid); // Chưa tạo kết quả thống kê.

Map<String, Long> counts = selected.collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    )
);

// selected.count(); // Không được dùng lại Stream đã tiêu thụ.
```

### 12.1. Thu thập thường cần đọc toàn bộ dữ liệu

Đếm và tính tổng theo từng nhóm không phải phép tìm kiếm dừng sớm: với một tập hữu hạn, các nhóm cần nhận hết những phần tử thuộc phạm vi tính toán. Kết quả Map có chi phí lưu **một entry cho mỗi khóa nhóm**; với nhóm hai tầng, còn có Map cho từng nhóm ngoài và các entry trong từng Map con.

`groupingBy(..., counting())` không lưu tất cả phần tử thành danh sách như `groupingBy(...)` mặc định; nó chỉ giữ trạng thái cần thiết cho phép đếm. Tương tự, `summingLong` có thể tránh lưu toàn bộ giao dịch trong nhóm. Đây là lợi ích quan trọng của việc chọn downstream theo đúng kết quả yêu cầu.

### 12.2. `parallelStream` không mặc định nhanh hơn

```java
Map<String, Long> parallelTotals = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

`groupingBy` thông thường **không phải concurrent collector**; khi song song, framework có thể tích lũy vào các Map riêng rồi **kết hợp**. Việc kết hợp nhiều Map có thể tốn chi phí nếu số khóa lớn.

Nếu phù hợp với nghiệp vụ không phụ thuộc thứ tự, có thể cân nhắc:

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
    .filter(Order::paid)
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.summingLong(Order::amountVnd)
    ));
```

`groupingByConcurrent` là một concurrent, unordered collector. Downstream `summingLong` không cần tự thay đổi thành một biến dùng chung giữa các luồng; framework chịu trách nhiệm phối hợp để giữ tính đúng theo hợp đồng. Việc dùng `groupingByConcurrent` cũng **không** bảo đảm luôn nhanh hơn `groupingBy`: dữ liệu có ít khóa và rất nhiều phần tử cùng một khóa có thể gây tranh chấp.

Song song hóa không khắc phục tràn số nguyên, không giải quyết sai số dấu phẩy động và không cho phép sửa tùy tiện một `HashMap` bên ngoài từ `forEach`.

### 12.3. Tránh mutable state ngoài Collector

Ví dụ không nên dùng:

```java
// Không an toàn, nhất là với parallelStream():
Map<String, Long> mutableTotals = new java.util.HashMap<>();

orders.parallelStream().forEach(order ->
    mutableTotals.merge(
        order.region(),
        order.amountVnd(),
        Long::sum
    )
);
```

Đoạn này cập nhật `HashMap` dùng chung từ nhiều luồng mà không có đồng bộ đúng cách. Hãy dùng `groupingBy`/`groupingByConcurrent` với downstream thích hợp; collector quản lý trạng thái tích lũy, combiner và yêu cầu an toàn luồng.

Với nguồn gắn với tài nguyên I/O, ví dụ `Files.lines(path)`, đóng Stream bằng `try-with-resources` dù terminal operation là `collect`. Chi phí hiệu năng phụ thuộc số phần tử, số nhóm, mapper, cấu trúc Map, kiểu số và độ cạnh tranh; đo bằng dữ liệu đại diện, chẳng hạn JMH, trước khi tối ưu.

## 13. Ví dụ hoàn chỉnh: thống kê nhiều tầng và hai đại lượng

Đoạn mã sau chạy trên **Java 17+** (sử dụng `record`, `Collectors.filtering` và `Collectors.teeing`). Nó tổng hợp một lượt các báo cáo phổ biến trên cùng danh sách nguồn; mỗi báo cáo tạo **một Stream mới**, vì Stream không thể dùng lại sau terminal operation.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupedAggregationDemo {
    record Order(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record RegionStats(long count, long totalVnd) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc",   "Sách", 120_000L, true),
            new Order("O-02", "Nam",   "Bút",   30_000L, true),
            new Order("O-03", "Bắc",   "Sách",  80_000L, false),
            new Order("O-04", "Bắc",   "Bút",   50_000L, true),
            new Order("O-05", "Nam",   "Sách", 100_000L, true),
            new Order("O-06", "Trung", "Bút",   40_000L, true),
            new Order("O-07", "Tây",   "Sách",  75_000L, false)
        );

        // 1. Đếm tất cả đơn theo khu vực.
        Map<String, Long> allCounts = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));

        // 2. Đếm đơn đã thanh toán, vẫn giữ khu vực chỉ có đơn chưa thanh toán.
        Map<String, Long> paidCounts = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.filtering(
                    Order::paid,
                    Collectors.counting()
                )
            ));

        // 3. Tổng doanh thu đã thanh toán theo khu vực.
        Map<String, Long> revenue = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        // 4. Đếm đơn đã thanh toán theo cả khu vực và loại sản phẩm.
        Map<String, Map<String, Long>> byRegionAndCategory =
            orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                    Order::region,
                    Collectors.groupingBy(
                        Order::category,
                        Collectors.counting()
                    )
                ));

        // 5. Một report cho mỗi khu vực: vừa số đơn vừa tổng tiền.
        Map<String, RegionStats> combined = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Order::amountVnd),
                    RegionStats::new
                )
            ));

        System.out.println(allCounts.get("Bắc"));           // 3
        System.out.println(paidCounts.get("Tây"));          // 0
        System.out.println(revenue.get("Bắc"));             // 170000
        System.out.println(revenue.containsKey("Tây"));     // false
        System.out.println(
            byRegionAndCategory.get("Nam").get("Sách")
        );                                                  // 1
        System.out.println(combined.get("Bắc"));
        // RegionStats[count=2, totalVnd=170000]
    }
}
```

Phân tích năm kết quả:

| Báo cáo | Kiểu trả về | Nhóm Tây | Ý nghĩa |
| --- | --- | --- | --- |
| `allCounts` | `Map<String, Long>` | 1 | Đếm mọi đơn, không phân biệt thanh toán |
| `paidCounts` | `Map<String, Long>` | 0 | Nhóm tồn tại nhưng không đơn nào đạt điều kiện downstream |
| `revenue` | `Map<String, Long>` | Không có khóa | Stream đã lọc hết đơn ở Tây trước khi nhóm |
| `byRegionAndCategory` | `Map<String, Map<String, Long>>` | Không có khóa | Báo cáo hai chiều chỉ chứa đơn đã thanh toán |
| `combined` | `Map<String, RegionStats>` | Không có khóa | Một kết quả gồm số đơn và tổng tiền cho mỗi nhóm còn lại |

Không phụ thuộc vào thứ tự in của `Map` nếu không chọn một `mapFactory` bảo đảm thứ tự. Các dòng `get(...)` trong ví dụ kiểm tra cụ thể từng khóa, nên không yêu cầu Map phải duyệt theo thứ tự nào.

## 14. Lỗi thường gặp và hướng khắc phục

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `stream.count()` rồi mong nhận số lượng theo từng khóa | Chỉ nhận tổng toàn Stream | Đặt `counting()` vào downstream của `groupingBy` |
| Khai báo `Map<K, Integer>` với `counting()` | Sai kiểu trả về | Dùng `Map<K, Long>` |
| Coi `summingInt` phù hợp cho mọi tổng nguyên | Có thể tràn `int` | Dùng `summingLong` sau khi mở rộng kiểu, hoặc số nguyên chính xác hơn |
| Dùng `summingLong` nhưng phép nhân trong mapper vẫn là `int * int` | Trung gian có thể tràn | Ép kiểu một toán hạng trước phép nhân |
| Lọc trước khi nhóm rồi mong có khóa với giá trị 0 | Nhóm bị lọc hết không xuất hiện | Dùng downstream `filtering` nếu muốn giữ khóa đã có trong nguồn |
| Cho rằng downstream `filtering` sẽ tạo cả nhóm chưa từng có trong nguồn | Không thể suy ra khóa chưa tồn tại | Bổ sung danh mục khóa nghiệp vụ tường minh |
| Xem `get(key) == null` là tổng bằng 0 mà không kiểm tra ngữ nghĩa | Nhầm không có nhóm với nhóm có giá trị 0 | Dùng `containsKey` hoặc kiểu kết quả diễn đạt đủ trạng thái |
| Đếm bản ghi bằng `counting()` khi muốn đếm giá trị duy nhất | Đếm trùng | `mapping` sang khóa duy nhất, `toSet`, rồi tính kích thước |
| Dùng `groupingBy` hai tầng nhưng đọc nhầm thứ tự khóa | Truy xuất sai báo cáo | Xác định rõ Map ngoài là chiều nào, Map trong là chiều nào |
| Lấy trung bình hai nhóm không có trọng số để ra trung bình toàn bộ | Sai khi số phần tử hai nhóm khác nhau | Gộp `sum` và `count` trước, sau đó chia |
| Giả định Map trả về theo thứ tự xuất hiện | Không có bảo đảm từ overload mặc định | Dùng `LinkedHashMap::new`/`TreeMap::new` theo nhu cầu |
| Cộng tiền thập phân bằng `summingDouble` và coi kết quả tuyệt đối chính xác | Sai số dấu phẩy động | Dùng `BigDecimal` và quy tắc làm tròn phù hợp |
| Dùng lại cùng một Stream cho nhiều báo cáo | Stream đã tiêu thụ, có thể ném ngoại lệ | Tạo Stream mới hoặc kết hợp collector có chủ đích |
| Sửa một `HashMap` bên ngoài bằng `parallelStream().forEach(...)` | Race condition, sai dữ liệu | Dùng collector đúng hợp đồng |
| Mặc định `groupingByConcurrent` luôn nhanh hơn | Có thể tranh chấp khóa, overhead tăng | Đo trên dữ liệu, số nhóm và phân bố khóa thực tế |

## 15. Bài tập thực hành

### Bài 1: Đếm theo loại sản phẩm

Với danh sách `Order` trong mục 1, dùng `groupingBy(Order::category, counting())` đếm tất cả đơn theo loại hàng. So sánh với pipeline chỉ tính các đơn đã thanh toán và giải thích vì sao hai báo cáo có ý nghĩa khác nhau.

### Bài 2: Doanh thu đã thanh toán

Dùng `filter(Order::paid)`, `groupingBy(Order::region, summingLong(Order::amountVnd))` để tính doanh thu từng khu vực. Kiểm tra riêng khu vực Tây và nêu lý do khóa này không xuất hiện.

### Bài 3: Đếm có giá trị 0

Viết lại báo cáo bài 2 bằng `groupingBy(Order::region, filtering(Order::paid, summingLong(...)))`. So sánh `containsKey("Tây")`, `get("Tây")` và `getOrDefault("Đông", 0L)`. Ba phép kiểm tra nói gì về sự tồn tại của dữ liệu?

### Bài 4: Nhóm hai tầng

Tạo `Map<String, Map<String, Long>>` đếm số đơn đã thanh toán theo `category` trước, rồi `region` sau. So sánh cách truy xuất với `groupingBy(region, groupingBy(category, ...))`.

### Bài 5: Đếm và tính tổng một lượt

Dùng `Collectors.teeing(counting(), summingLong(...), RegionStats::new)` để tạo `RegionStats` cho mỗi khu vực. Nếu cần thêm giá trị lớn nhất, hãy cân nhắc `summarizingLong` và giải thích lúc nào nó đơn giản hơn `teeing`.

### Bài 6: Độ chính xác khi tổng hợp

Cho hai bản ghi kho cùng nhóm, mỗi bản ghi có `1_500_000_000` đơn vị. So sánh `summingInt` với `summingLong`; giải thích nguyên nhân tràn và thời điểm chuyển kiểu. Sau đó xây nhóm có tổng vượt `Long.MAX_VALUE` bằng `BigInteger`.

### Bài 7: Nhóm không có dữ liệu

Tạo danh mục khu vực gồm Bắc, Trung, Nam, Tây và Đông. Từ `Map` chỉ chứa khu vực có giao dịch đã thanh toán, tạo một báo cáo đầy đủ năm khóa, đặt `0L` khi không có số liệu. Nêu khi nào việc thay thiếu dữ liệu bằng 0 là phù hợp và khi nào cần giữ trạng thái “chưa có dữ liệu”.

### Bài 8: Đánh giá song song

Với tập dữ liệu có nhiều đơn nhưng chỉ hai khu vực, so sánh `groupingBy` và `groupingByConcurrent` khi chạy song song. Giải thích rủi ro tranh chấp ở số khóa ít, ảnh hưởng của `combiner` và vì sao nên đo trên workload đại diện thay vì chọn chỉ theo tên API.

## 16. Tự kiểm tra kiến thức

- `Collectors.counting()` khác `Stream.count()` như thế nào?
- Trong `groupingBy(classifier, downstream)`, thành phần nào quyết định khóa, thành phần nào quyết định giá trị?
- `summingInt`, `summingLong` và `summingDouble` trả về kiểu gì?
- Vì sao tổng doanh thu có thể khác khi đặt `filter` trước và sau bước phân nhóm?
- Khi nào dùng `Collectors.filtering` để giữ nhóm có kết quả bằng 0?
- Cấu trúc `Map<K1, Map<K2, Long>>` biểu diễn hai chiều phân nhóm thế nào?
- Khi nào `teeing` phù hợp hơn chạy hai pipeline độc lập?
- `summarizingLong` có thể thay `counting` và `summingLong` trong tình huống nào?
- Vì sao nhóm không xuất hiện khác với một nhóm có tổng bằng 0?
- `partitioningBy` trên nguồn rỗng khác `groupingBy` như thế nào?
- Vì sao `summingLong` không giải quyết mọi nguy cơ tràn số và mất chính xác?
- Tại sao phải cân nhắc số nhóm và phân bố khóa khi xử lý song song?

**Ghi nhớ:** Để đếm hoặc tính tổng **từng nhóm**, hãy đặt `Collectors.counting()` hoặc `Collectors.summingInt/summingLong/summingDouble(...)` làm **downstream** của `groupingBy`. Muốn thêm chiều báo cáo thì lồng `groupingBy`; muốn nhiều số liệu trong một kết quả thì cân nhắc `teeing` hoặc `summarizingLong`. Luôn phân biệt **nhóm không có khóa**, **nhóm có kết quả 0**, và **giá trị số có thể tràn hoặc sai số** trước khi đưa báo cáo vào nghiệp vụ.
