# Phân nhóm đồng thời bằng `groupingByConcurrent`

## 1. Vì sao cần phân nhóm đồng thời?

Trong module **JAVA_STREAM_API**, chúng ta dùng pipeline khai báo với `filter`, `map`, `reduce` và `collect` để xử lý dữ liệu. Khi đầu vào lớn, có thể cân nhắc `parallelStream()` hoặc `parallel()` để nhiều phần tử được xử lý trên nhiều luồng. Tuy nhiên, **thu thập kết quả vào cùng một `Map`** đặt ra câu hỏi: ai quản lý quyền cập nhật nhóm, dữ liệu có mất hay trùng không, và thứ tự còn được bảo đảm đến đâu?

Hãy xét dữ liệu đơn hàng:

```text
O-1: HN  = 120_000
O-2: HCM =  80_000
O-3: HN  =  30_000
O-4: DN  =  50_000
O-5: HCM =  20_000

Mong muốn:
HN  -> 2 đơn, 150_000
HCM -> 2 đơn, 100_000
DN  -> 1 đơn,  50_000
```

`Collectors.groupingBy` đã có thể nhóm dữ liệu, kể cả trên parallel stream. Nhưng với phép thu thập cần **cấu trúc map đồng thời**, `Collectors.groupingByConcurrent` cung cấp một collector kiểu **concurrent**, **unordered**, trả kết quả `ConcurrentMap`.

Điều đó **không** có nghĩa:

- Stream chắc chắn chạy song song.
- Từng danh sách giá trị trong map đều thread-safe.
- Thứ tự khóa hoặc thứ tự phần tử từng nhóm được bảo đảm.
- Mọi dữ liệu luôn chạy nhanh hơn `groupingBy`.

Bài thuộc chương **Thu thập đồng thời** và tập trung vào việc thiết kế đúng hợp đồng trước khi tối ưu. Sau bài học, bạn sẽ:

1. Đọc ba overload của `groupingByConcurrent` và kiểu trả về `ConcurrentMap<K,D>`.
2. Hiểu hai đặc tính `CONCURRENT` và `UNORDERED` cùng ảnh hưởng của downstream collector.
3. Phân biệt tính đồng thời của **map bên ngoài** với tính an toàn của **value trong từng nhóm**.
4. Kết hợp `counting`, `summingLong`, `mapping`, `filtering` và `summarizingLong` để tổng hợp theo nhóm.
5. Chọn `ConcurrentHashMap` hoặc `ConcurrentSkipListMap` khi cần một chính sách thứ tự khóa.
6. Kiểm soát khóa `null`, giá trị thiếu, overflow, dữ liệu không đồng đều và rủi ro bộ nhớ.
7. Viết bài test so sánh tuần tự/song song **không dựa vào thứ tự không được API cam kết**.

Các ví dụ đầy đủ dùng **JDK 17 trở lên**, vì có `record`, `Stream.toList()` và `Collectors.filtering` (JDK 9+). `groupingByConcurrent` đã có từ Java 8.

## 2. Đọc ba overload của `Collectors.groupingByConcurrent`

Các chữ ký rút gọn từ `java.util.stream.Collectors`:

```java
// 1. Mỗi khóa nhận một List<T>.
<T, K> Collector<T, ?, ConcurrentMap<K, List<T>>>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier
)

// 2. Mỗi khóa nhận kết quả D của downstream collector.
<T, K, A, D> Collector<T, ?, ConcurrentMap<K, D>>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)

// 3. Chọn loại ConcurrentMap bằng mapFactory.
<T, K, A, D, M extends ConcurrentMap<K, D>> Collector<T, ?, M>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Cần import `java.util.concurrent.ConcurrentMap`, `java.util.function.Function`, `java.util.function.Supplier`, `java.util.stream.Collector`.

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử đầu vào của stream, ví dụ `Order` |
| `K` | Kiểu khóa do `classifier` sinh ra, ví dụ `String` |
| `A` | Trạng thái tích lũy trung gian của downstream collector, được che giấu ở collector ngoài |
| `D` | Kiểu kết quả downstream của **một nhóm**, ví dụ `Long` hoặc `LongSummaryStatistics` |
| `M` | Kiểu map đích, phải là subtype của `ConcurrentMap<K,D>` |
| `?` | Kiểu tích lũy nội bộ của toàn collector không được công khai |

Ví dụ:

```java
ConcurrentMap<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));
```

Compiler suy ra `T = Order`, `K = String`, `D = Long`, nên `collect` trả `ConcurrentMap<String,Long>`. Đối với overload một tham số, `D = List<Order>`.

**Lưu ý kiểu trả về:** `groupingByConcurrent` cho kết quả qua interface `ConcurrentMap`. Overload mặc định thường dùng `ConcurrentHashMap` theo triển khai JDK hiện hành, nhưng thiết kế ứng dụng không nên phụ thuộc vào class cụ thể trừ khi dùng overload `mapFactory` và xác định nó tường minh.

## 3. `groupingBy` khác `groupingByConcurrent` như thế nào?

Cùng một yêu cầu đếm đơn hàng theo vùng:

```java
Map<String, Long> sequentialStyle = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

ConcurrentMap<String, Long> concurrentStyle = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.counting()
    ));
```

Chúng có thể trả **cùng ánh xạ giá trị**, nhưng hợp đồng thực thi và kết quả khác nhau.

| Tiêu chí | `groupingBy` | `groupingByConcurrent` |
| --- | --- | --- |
| Kiểu trả về mặc định | `Map<K,D>` | `ConcurrentMap<K,D>` |
| Collector concurrent? | Không phải concurrent collector theo mặc định | Có đặc tính `CONCURRENT` |
| Collector unordered? | Không mặc định khai `UNORDERED` | Có đặc tính `UNORDERED` |
| Có dùng được với parallel stream? | Có | Có |
| Có phải dùng một map chung khi chạy song song? | Không | Framework có thể dùng tích lũy đồng thời theo hợp đồng |
| Giữ thứ tự phần tử trong danh sách nhóm? | Phụ thuộc encounter order và downstream | **Không cam kết** thứ tự |
| Có phải luôn nhanh hơn? | Không | Không |

Trong nhiều trường hợp, `groupingBy` khi chạy song song sẽ tích lũy vào các map cục bộ rồi **gộp map với nhau**, và chi phí hợp nhất khóa có thể đáng kể. `groupingByConcurrent` cho phép cách tích lũy đồng thời vào một cấu trúc `ConcurrentMap` thích hợp, nhưng các luồng có thể tranh chấp cùng một nhóm.

**Phân biệt:** `parallelStream()` là chế độ thực thi của pipeline; `CONCURRENT` là **cam kết của collector**. Một collector không concurrent vẫn có thể được dùng an toàn trên parallel stream nhờ framework phân tách trạng thái. Đừng cho rằng cứ đặt `parallel()` là phải dùng `groupingByConcurrent`.

## 4. `CONCURRENT`, `UNORDERED` và encounter order

Collector có các characteristic trong `Collector.Characteristics`. Hai characteristic quyết định thiết kế bài này:

### 4.1. `CONCURRENT` nói về tích lũy

`CONCURRENT` báo cho framework rằng các lời gọi accumulator có thể thực hiện đồng thời trên **cùng container tích lũy**. Nó không nói rằng mọi loại object được lưu trong container đều thích hợp cho ứng dụng tùy ý sửa từ nhiều thread.

`groupingByConcurrent` tổ chức việc phân loại và tích lũy theo hợp đồng collector. Khi downstream không concurrent (ví dụ `Collectors.toList()`), triển khai collector phải phối hợp an toàn trong quá trình thu thập; **không được suy ngược rằng `ArrayList` kết quả giờ đã thread-safe**.

### 4.2. `UNORDERED` nói về thứ tự kết quả

`UNORDERED` cho biết collector không yêu cầu bảo toàn encounter order khi tích lũy. Vì vậy, các list trong nhóm của `groupingByConcurrent(classifier)` **không có bảo đảm thứ tự**; Javadoc mô tả không có đảm bảo về loại, tính có thể sửa, khả năng tuần tự hóa hoặc thread-safety của các list được trả về.

Ví dụ:

```java
List<Integer> ids = java.util.stream.IntStream.range(0, 10)
    .boxed().toList();

ConcurrentMap<String, List<Integer>> grouped = ids.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        n -> n % 2 == 0 ? "even" : "odd"
    ));

// Hợp đồng: có đủ năm số chẵn và năm số lẻ.
// Không viết test yêu cầu grouped.get("even") luôn là [0, 2, 4, 6, 8].
```

Khi cần giữ đúng thứ tự từng nhóm, ưu tiên ordered stream kết hợp `groupingBy(classifier, downstream)` hoặc sắp xếp **sau khi** thu thập theo tiêu chí xác định.

### 4.3. Framework có thể chọn cách tổ chức khác nhau

Với concurrent collector, điều kiện về encounter order ảnh hưởng việc tích lũy vào container chia sẻ. `groupingByConcurrent` tự khai `UNORDERED` nên cho phép framework thực hiện concurrent reduction theo hợp đồng. Tuy vậy, **đừng phụ thuộc số lần gọi supplier, combiner hay thứ tự tạo nhóm**, vì đây không phải API nghiệp vụ.

Một pipeline tuần tự dùng `groupingByConcurrent` vẫn tạo `ConcurrentMap`, nhưng không có nghĩa nó đã chạy trên nhiều luồng. Một pipeline parallel cũng không đảm bảo có tốc độ nhanh hơn hay tất cả lõi đều bận.

## 5. Dòng dữ liệu đi vào các nhóm đồng thời như thế nào?

Để hiểu, hãy nhìn một mô hình **khái niệm**, không phải cam kết về chi tiết triển khai:

```text
          Stream<Order> chạy song song
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
       Order    Order    Order
        │        │        │
      classifier: region
        │        │        │
        └────────┼────────┘
                 ▼
       ConcurrentMap<String, A>
          HN   -> A_HN
          HCM  -> A_HCM
          DN   -> A_DN
                 │
       downstream finisher (nếu cần)
                 ▼
       ConcurrentMap<String, D>
```

Collector ngoài bảo đảm tính đúng của việc phân nhóm và tương tác với downstream collector. Nếu downstream là `counting()`, `D = Long`; nếu là `toList()`, `D = List<Order>`; nếu là `summarizingLong(...)`, `D = LongSummaryStatistics`.

**Ba tầng cần tách biệt:**

1. **Đầu vào:** nguồn có an toàn khi được duyệt song song không? Mapper và classifier có stateless, non-interfering không?
2. **Tích lũy:** collector có bảo đảm phối hợp cập nhật đúng không?
3. **Kết quả cuối:** đối tượng `ConcurrentMap` cho phép một tập thao tác đồng thời, nhưng nội dung value có thể vẫn mutable và không thread-safe.

Không tự viết `parallelStream().forEach(order -> sharedHashMap.put(...))` rồi hy vọng Java tự đồng bộ. Collector cung cấp cơ chế hợp đồng rõ ràng hơn.

## 6. Ví dụ Java 17 đầy đủ: phân nhóm và thống kê đơn hàng

Ví dụ sau định nghĩa dữ liệu bất biến và cho thấy ba dạng kết quả: danh sách đơn, số đơn và tổng tiền theo vùng.

```java
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public final class ConcurrentOrderReport {

    private ConcurrentOrderReport() {}

    public record Order(
        String id,
        String region,
        long amountVnd,
        boolean paid
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O1", "HN", 120_000L, true),
            new Order("O2", "HCM", 80_000L, true),
            new Order("O3", "HN", 30_000L, true),
            new Order("O4", "DN", 50_000L, false),
            new Order("O5", "HCM", 20_000L, true),
            new Order("O6", "DN", 10_000L, true)
        );
    }

    public static ConcurrentMap<String, List<Order>> allByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .collect(Collectors.groupingByConcurrent(Order::region));
    }

    public static ConcurrentMap<String, Long> countByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.counting()
            ));
    }

    public static ConcurrentMap<String, Long> paidAmountByRegion(
        List<Order> source
    ) {
        return source.parallelStream()
            .filter(Order::paid)
            .collect(Collectors.groupingByConcurrent(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));
    }

    public static void main(String[] args) {
        var orders = sample();

        var groups = allByRegion(orders);
        System.out.println(groups.get("HN").size()); // 2
        System.out.println(groups.get("DN").size()); // 2

        var counts = countByRegion(orders);
        System.out.println(counts.get("HN"));  // 2
        System.out.println(counts.get("HCM")); // 2
        System.out.println(counts.get("DN"));  // 2

        var totals = paidAmountByRegion(orders);
        System.out.println(totals.get("HN"));  // 150000
        System.out.println(totals.get("HCM")); // 100000
        System.out.println(totals.get("DN"));  // 10000
    }
}
```

**Giải thích:**

- `allByRegion` trả `ConcurrentMap<String,List<Order>>`. Có đủ mỗi đơn đúng một lần trong nhóm thích hợp, nhưng **không cam kết vị trí đơn trong list**.
- `countByRegion` dùng `Collectors.counting` làm downstream, chỉ lưu kết quả đếm mỗi nhóm.
- `paidAmountByRegion` lọc theo trạng thái thanh toán **trước** khi phân nhóm, nên mỗi vùng có ít nhất một đơn đã thanh toán mới có khóa. Với dữ liệu ví dụ, cả ba vùng đều còn khóa.
- Dùng `long` nguyên VND cho bài học tổng hợp; `summingLong` không tự phát hiện tràn số.
- `record Order` bảo vệ các trường bất biến, nhưng nếu nguồn là collection đang bị thay đổi cấu trúc trong lúc duyệt thì vẫn cần đảm bảo non-interference.

Kết quả được in bằng cách tra cứu theo khóa, **không dựa vào thứ tự khi lặp map**. Một `ConcurrentMap` không có yêu cầu giữ thứ tự chèn giống `LinkedHashMap`.

## 7. Tính an toàn của các `List` trong nhóm

Chữ ký overload một tham số là:

```java
Collector<Order, ?, ConcurrentMap<String, List<Order>>>
```

Điều này **không** có nghĩa `List<Order>` là `CopyOnWriteArrayList`, `synchronizedList` hay một loại list an toàn khi caller tùy ý ghi song song.

Trong quá trình thực hiện `collect`, framework và collector chịu trách nhiệm tích lũy đúng. **Sau khi terminal operation trả về**, `ConcurrentMap` quản lý thao tác map, nhưng nếu nhiều thread cùng gọi `get("HN").add(order)` lên cùng một list thông thường, chúng có thể gây race hoặc làm hỏng dữ liệu.

Phản ví dụ:

```java
ConcurrentMap<String, List<ConcurrentOrderReport.Order>> result =
    ConcurrentOrderReport.allByRegion(
        ConcurrentOrderReport.sample()
    );

// Không coi đoạn sau là thread-safe chỉ vì result là ConcurrentMap:
// result.get("HN").add(newOrder); // nhiều thread cùng sửa một List.
```

Để xử lý đúng:

- Nếu chỉ cần **đọc** các nhóm sau khi `collect` hoàn tất và không còn ai sửa list, có thể xử lý read-only.
- Nếu cần **snapshot bất biến**, sao chép list và map sau khi đã kết thúc thu thập.
- Nếu cần **nhiều luồng sửa cùng value** sau khi thu thập, thiết kế một cấu trúc/đồng bộ riêng cho value, không mặc định dựa vào `groupingByConcurrent`.
- Nếu chỉ cần số đếm hoặc tổng, dùng `counting`/`summingLong` thay vì giữ mọi `Order` trong list, giảm rủi ro mutation và áp lực bộ nhớ.

Javadoc của `groupingByConcurrent(classifier)` nêu rõ không có bảo đảm về **thread-safety của các `List` được trả về**; câu này quan trọng hơn tên có chữ “Concurrent”.

## 8. Downstream collector: `counting`, `summingLong` và `summarizingLong`

### 8.1. Đếm phần tử của từng nhóm

```java
ConcurrentMap<String, Long> counts =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));

System.out.println(counts.get("HN")); // 2
```

`counting()` trả `Long` cho từng nhóm. Khi chỉ cần số lượng, tránh tạo `List<Order>` để đếm bằng `size()` sau đó, nhất là với dữ liệu lớn.

### 8.2. Cộng `long` theo nhóm

```java
ConcurrentMap<String, Long> totals =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.summingLong(
                ConcurrentOrderReport.Order::amountVnd
            )
        ));

System.out.println(totals.get("DN")); // 60000 (bao gồm đơn chưa thanh toán)
```

Nếu chỉ muốn đơn đã thanh toán, thêm `filter(Order::paid)` trước grouping hoặc một downstream `filtering`, nhưng **hai cách sẽ khác tập khóa** khi một nhóm không có phần tử thỏa.

### 8.3. Bộ thống kê đầy đủ với `summarizingLong`

```java
import java.util.LongSummaryStatistics;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, LongSummaryStatistics> stats =
    ConcurrentOrderReport.sample().parallelStream()
        .filter(ConcurrentOrderReport.Order::paid)
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.summarizingLong(
                ConcurrentOrderReport.Order::amountVnd
            )
        ));

LongSummaryStatistics hn = stats.get("HN");
System.out.println(hn.getCount());   // 2
System.out.println(hn.getSum());     // 150000
System.out.println(hn.getMin());     // 30000
System.out.println(hn.getMax());     // 120000
System.out.println(hn.getAverage()); // 75000.0
```

`LongSummaryStatistics` có `accept` và `combine`, nên **mutable**. Tương tự `List`, việc nó được tạo bởi concurrent grouping **không có nghĩa caller có thể sửa cùng một instance từ nhiều thread một cách an toàn**.

Với nguồn rỗng, map kết quả rỗng: không có nhóm nào để tạo thống kê. Với một nhóm được hình thành trước downstream `filtering` nhưng không có phần tử được tính, thống kê của nhóm ấy có `count == 0`; `getMin/getMax` khi đó là sentinel chứ không phải số liệu thực tế.

## 9. `mapping`, `filtering` và collector nhiều tầng

`groupingByConcurrent` chấp nhận downstream, nhờ đó các phép biến đổi và tổng hợp được viết **ngay trong từng nhóm**.

### 9.1. Chỉ thu ID đơn hàng theo vùng

```java
ConcurrentMap<String, List<String>> idsByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.mapping(
                ConcurrentOrderReport.Order::id,
                Collectors.toList()
            )
        ));

// Các nhóm chứa đủ ID; không khẳng định List có thứ tự cố định.
System.out.println(idsByRegion.get("HN").size()); // 2
```

Ở đây, collector ngoài nhận `Order` và xác định `String region`; downstream `mapping` chuyển từng `Order` thành `String id` trước khi `toList` tích lũy.

### 9.2. Lọc trước nhóm: nhóm có thể biến mất

```java
var onlyPaid = ConcurrentOrderReport.sample().parallelStream()
    .filter(ConcurrentOrderReport.Order::paid)
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.counting()
    ));
```

Nếu thêm một vùng chỉ có đơn chưa thanh toán, vùng đó **không có khóa** trong `onlyPaid`.

### 9.3. `Collectors.filtering` bên trong nhóm: nhóm rỗng vẫn hiện diện

`Collectors.filtering` (Java 9+) nhận predicate và downstream:

```java
var countsIncludingZero = ConcurrentOrderReport.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.filtering(
            ConcurrentOrderReport.Order::paid,
            Collectors.counting()
        )
    ));

System.out.println(countsIncludingZero.get("DN")); // 1
```

Nếu DN chỉ có đơn chưa thanh toán, `countsIncludingZero` vẫn chứa `"DN" -> 0L` vì collector ngoài đã nhìn thấy khóa DN, còn downstream filtering loại những đơn không phù hợp. Nhờ vậy, downstream filtering hữu ích cho báo cáo cần giữ các nhóm **đã hiện diện trong nguồn** dù số liệu hợp lệ bằng 0.

**Giới hạn:** nếu một vùng hoàn toàn không tồn tại trong nguồn, `groupingByConcurrent` không tự tạo khóa đó; muốn hiển thị đầy đủ tập vùng cấu hình, cần tạo thêm những mục thiếu sau bước thu thập.

### 9.4. Dùng `collectingAndThen` để trả kết quả bất biến

`collectingAndThen` bọc downstream collector và chạy finisher trên kết quả từng nhóm. Ví dụ trả danh sách ID đã sắp và không thể sửa đổi:

```java
ConcurrentMap<String, List<String>> sortedIdsByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.collectingAndThen(
                Collectors.mapping(
                    ConcurrentOrderReport.Order::id,
                    Collectors.toList()
                ),
                ids -> ids.stream().sorted().toList()
            )
        ));

System.out.println(sortedIdsByRegion.get("HN")); // [O1, O3]
// sortedIdsByRegion.get("HN").add("O7"); // UnsupportedOperationException
```

Nhờ `sorted()`, thứ tự **ID trong một nhóm** được định nghĩa tường minh, bất kể lịch chạy song song. `Stream.toList()` tạo danh sách không thể sửa đổi từ JDK 16+. Map ngoài vẫn là `ConcurrentMap` mutable; cần bảo vệ riêng nếu muốn cố định toàn bộ kết quả.

## 10. Chọn loại map: `ConcurrentHashMap` và `ConcurrentSkipListMap`

Overload có `mapFactory` cho phép chọn một subtype của `ConcurrentMap<K,D>`:

```java
<T, K, A, D, M extends ConcurrentMap<K, D>> Collector<T, ?, M>
groupingByConcurrent(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

### 10.1. `ConcurrentHashMap`: tra cứu đồng thời, không cam kết thứ tự

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

ConcurrentHashMap<String, Long> counts =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            ConcurrentHashMap::new,
            Collectors.counting()
        ));
```

`ConcurrentHashMap` hỗ trợ thao tác map đồng thời, nhưng thứ tự duyệt `keySet` không phải thứ tự gặp phần tử hay thứ tự từ điển. Iteration trên concurrent collections có thể phản ánh thay đổi trong quá trình duyệt; không xây báo cáo “ổn định thứ tự” khi dữ liệu còn được sửa.

### 10.2. `ConcurrentSkipListMap`: map đồng thời có khóa sắp xếp

Nếu cần **khóa** được duyệt theo thứ tự tự nhiên của `String`:

```java
import java.util.List;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

ConcurrentSkipListMap<String, Long> countsBySortedKey =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            ConcurrentSkipListMap::new,
            Collectors.counting()
        ));

System.out.println(List.copyOf(countsBySortedKey.keySet()));
// [DN, HCM, HN]
```

`ConcurrentSkipListMap` dùng thứ tự khóa theo `Comparable` hoặc `Comparator`, không giữ **thứ tự nhóm xuất hiện trong nguồn**. Khi map không còn bị cập nhật, thứ tự duyệt khóa theo comparator là một hợp đồng hữu ích cho hiển thị.

Nếu cần thứ tự giảm dần, truyền comparator vào factory:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;

ConcurrentSkipListMap<String, Long> descending =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            () -> new ConcurrentSkipListMap<String, Long>(
                Comparator.reverseOrder()
            ),
            Collectors.counting()
        ));

System.out.println(List.copyOf(descending.keySet()));
// [HN, HCM, DN]
```

### 10.3. Không dùng `LinkedHashMap::new` trong overload này

`LinkedHashMap` không triển khai `ConcurrentMap`, nên biểu thức:

```java
// Không biên dịch: LinkedHashMap không phải subtype ConcurrentMap.
// Collectors.groupingByConcurrent(
//     Order::region, LinkedHashMap::new, Collectors.counting()
// )
```

Nếu yêu cầu đúng là **thứ tự chèn lần đầu trong một ordered stream**, hãy dùng `Collectors.groupingBy(..., LinkedHashMap::new, downstream)` với chính sách xử lý thứ tự phù hợp, thay vì cố ép một collector concurrent unordered đáp ứng insertion order.

## 11. `groupingByConcurrent` so với `toConcurrentMap`

Cả hai factory đều có thể tạo `ConcurrentMap`, nhưng cách đọc nghiệp vụ khác nhau.

### 11.1. `groupingByConcurrent`: một khóa, một nhóm

```java
ConcurrentMap<String, Long> countByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));
```

Đây là **bài toán phân nhóm**: dùng classifier xác định khóa, sau đó downstream tổng hợp các phần tử cùng nhóm.

### 11.2. `toConcurrentMap`: ánh xạ khóa và giá trị, giải quyết xung đột

```java
ConcurrentMap<String, Long> totalByRegion =
    ConcurrentOrderReport.sample().parallelStream()
        .collect(Collectors.toConcurrentMap(
            ConcurrentOrderReport.Order::region,
            ConcurrentOrderReport.Order::amountVnd,
            Long::sum
        ));
```

Đây là bài toán **keyMapper → valueMapper → mergeFunction**. Nếu một khóa có nhiều phần tử, `mergeFunction` quyết định cách kết hợp các giá trị.

| Nhu cầu | Thường chọn |
| --- | --- |
| Lưu mọi bản ghi cùng khóa vào một list | `groupingByConcurrent(classifier)` |
| Đếm/tổng hợp/thống kê theo nhóm | `groupingByConcurrent(classifier, downstream)` |
| Biến mỗi record thành cặp khóa–giá trị, trùng khóa thì gộp hai giá trị | `toConcurrentMap(key, value, merge)` |
| Cần một map concurrent có khóa được sắp | `groupingByConcurrent(classifier, ConcurrentSkipListMap::new, downstream)` |
| Cần giữ encounter order trong các list | Cân nhắc `groupingBy` có thứ tự, hoặc sắp sau khi thu thập |

Không dùng merge function phụ thuộc trạng thái mutable dùng chung hoặc không có tính kết hợp chỉ vì ví dụ chạy một lần ra kết quả mong muốn. Với số thực `double`, kết quả cộng có thể khác ở chữ số cuối theo cách phân nhóm và thứ tự gộp.

## 12. Nguồn rỗng, khóa `null` và dữ liệu không hợp lệ

### 12.1. Nguồn rỗng cho map rỗng

```java
ConcurrentMap<String, Long> empty =
    List.<ConcurrentOrderReport.Order>of().parallelStream()
        .collect(Collectors.groupingByConcurrent(
            ConcurrentOrderReport.Order::region,
            Collectors.counting()
        ));

System.out.println(empty.isEmpty()); // true
```

Một map rỗng khác với map chứa khóa có count bằng `0`. Trường hợp đầu **không có nhóm được hình thành**; trường hợp sau có nhóm nhưng downstream có thể đã lọc hết phần tử của nhóm ấy.

### 12.2. Khóa classifier trả `null` không hợp lệ

`groupingByConcurrent` không hỗ trợ classifier tạo khóa `null`. Đồng thời, những implementation như `ConcurrentHashMap` và `ConcurrentSkipListMap` không cho phép khóa `null`. Trên các JDK thông dụng, collector sẽ ném `NullPointerException` nếu classifier trả null.

```java
record RawOrder(String region, long amount) {}

List<RawOrder> raw = List.of(
    new RawOrder("HN", 10L),
    new RawOrder(null, 20L)
);

// Không làm nếu region có thể null:
// raw.parallelStream().collect(
//     Collectors.groupingByConcurrent(RawOrder::region)
// );
```

Chọn chính sách **trước khi nhóm**:

- Nếu null là dữ liệu lỗi, hãy validate và ném lỗi rõ ràng.
- Nếu nghiệp vụ cho phép một vùng “chưa xác định”, có thể dùng khóa đại diện `"UNKNOWN"` (đảm bảo không trùng với mã vùng hợp lệ).
- Nếu được phép bỏ bản ghi thiếu vùng, lọc nó trước collector.

Ví dụ chuẩn hóa tường minh:

```java
ConcurrentMap<String, Long> totals = raw.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        row -> row.region() == null ? "UNKNOWN" : row.region(),
        Collectors.summingLong(RawOrder::amount)
    ));

System.out.println(totals.get("UNKNOWN")); // 20
```

Đối với một hệ thống lớn, thay vì chuỗi sentinel có nguy cơ trùng, có thể dùng kiểu khóa riêng biểu diễn vùng hợp lệ và “thiếu vùng”.

### 12.3. Phần tử nguồn `null` khác classifier trả `null`

Nếu collection nguồn chứa **phần tử `null`**, một lời gọi method reference `Order::region` có thể ném `NullPointerException` **trước cả khi** classifier tạo khóa. Nếu chính sách cho phép bỏ phần tử rỗng:

```java
List<ConcurrentOrderReport.Order> nullable =
    new java.util.ArrayList<>();
nullable.add(null);
nullable.addAll(ConcurrentOrderReport.sample());

ConcurrentMap<String, Long> counts = nullable.parallelStream()
    .filter(java.util.Objects::nonNull)
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.counting()
    ));
```

`List.of(...)` không chấp nhận phần tử `null`; ví dụ dùng `ArrayList`. Nếu `null` là lỗi dữ liệu bắt buộc báo, **không** âm thầm dùng `filter(Objects::nonNull)`.

### 12.4. Không suy ra value có thể là `null`

`ConcurrentHashMap` và `ConcurrentSkipListMap` từ chối giá trị null trong map. Các downstream collector thông thường như `counting()` trả một giá trị không null. Nếu dùng downstream có finisher trả null, hoặc mapper không được thiết kế cho null, kết quả có thể thất bại. Hãy quy định dữ liệu thiếu rõ ràng và kiểm thử đường đi này.

## 13. Thứ tự, tính xác định và kiểm thử kết quả song song

### 13.1. Thứ tự khóa không phải thứ tự xử lý

`ConcurrentHashMap` không cam kết thứ tự duyệt khóa. `ConcurrentSkipListMap` có thể cung cấp thứ tự khóa theo comparator. Cả hai không làm thay đổi thực tế **classifier có thể chạy ở các thread với thứ tự khác nhau**.

Nếu báo cáo cần danh sách đơn hàng theo `id`, hãy sắp list kết quả sau khi thu thập:

```java
List<String> orderedIds = ConcurrentOrderReport.sample()
    .parallelStream()
    .collect(Collectors.groupingByConcurrent(
        ConcurrentOrderReport.Order::region,
        Collectors.mapping(
            ConcurrentOrderReport.Order::id,
            Collectors.toList()
        )
    ))
    .get("HN")
    .stream()
    .sorted()
    .toList();

System.out.println(orderedIds); // [O1, O3]
```

Đây là thứ tự theo **ID**, không phải theo thứ tự nhập liệu. Nếu mục tiêu thật sự là thứ tự nhập liệu, nên bảo toàn encounter order bằng collector thích hợp hoặc mang theo **sequence number** từ nguồn rồi sắp theo sequence sau khi nhóm.

### 13.2. Dùng `Set` để so sánh có thể làm mất thông tin trùng

Nếu một nhóm được phép có nhiều bản ghi có ID giống nhau, so sánh `Set<String>` sẽ bỏ số lần xuất hiện. Để kiểm chứng đầy đủ, so sánh **tần suất**, hoặc dùng ID duy nhất cho mỗi bản ghi trong test.

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static <T> Map<T, Long> frequency(List<T> values) {
    return values.stream().collect(
        Collectors.groupingBy(
            Function.identity(),
            Collectors.counting()
        )
    );
}
```

### 13.3. Kết quả `double` có thể khác ở phần lẻ

Với downstream `averagingDouble` hoặc `summingDouble`, thứ tự cộng và gộp có thể thay đổi lỗi làm tròn. Không viết test buộc kết quả `double` song song phải khớp tuyệt đối từng bit với kết quả tuần tự, trừ khi có hợp đồng số học đặc biệt. Dùng dung sai được xác định theo miền dữ liệu hoặc thuật toán chính xác hơn.

Với `summingLong`, phép cộng `long` có thể **tràn** nhưng không tự ném lỗi. Trong ví dụ doanh thu, chỉ đúng khi tổng nằm trong miền `long`; nghiệp vụ cần phát hiện tràn có thể dùng accumulator kiểm tra hoặc `BigInteger`.

## 14. Hiệu năng: khóa nóng và độ phân bố nhóm

“Concurrent” mô tả khả năng tích lũy, không phải một bảo đảm thời gian. Những yếu tố quan trọng:

### 14.1. Nhiều khóa phân bố đều

Nếu có nhiều khóa và dữ liệu phân bố tương đối đều, các thread có thể làm việc trên nhiều nhóm khác nhau. `groupingByConcurrent` có thể giảm một phần chi phí **gộp nhiều map cục bộ** của collector không concurrent.

### 14.2. Khóa nóng (*hot key*)

Nếu 99% bản ghi có cùng `region = "HN"`, nhiều thread sẽ cập nhật cùng một nhóm. Với downstream không concurrent như `toList()`, collector phải phối hợp các cập nhật trên cùng container. Tranh chấp khóa nóng có thể làm giảm hoặc triệt tiêu lợi ích song song.

```text
Phân bố đều:                 Một khóa rất nóng:
HN  ████                    HN  ███████████████████████
HCM ████                    HCM █
DN  ████                    DN  █
HP  ████                    HP  █
```

Không thể suy từ số luồng CPU để khẳng định tốc độ của `groupingByConcurrent`. Cần đo theo **số khóa, phân bố tần suất, chi phí classifier, downstream collector và kích thước nguồn**.

### 14.3. Nguồn nhỏ và phép tính rẻ

Với vài chục bản ghi và mapper đơn giản, overhead chia công việc, lập lịch và phối hợp đồng thời có thể lớn hơn thời gian xử lý tuần tự. `stream().collect(groupingBy(...))` thường dễ hiểu và đủ nhanh.

### 14.4. Downstream giữ dữ liệu so với downstream tổng hợp

| Downstream | Bộ nhớ cần giữ |
| --- | --- |
| `toList()` | Giữ từng phần tử trong mỗi nhóm, tổng có thể gần `O(n)` |
| `counting()` | Trạng thái đếm gọn cho mỗi nhóm |
| `summingLong()` | Trạng thái tổng theo nhóm |
| `summarizingLong()` | Một bộ thống kê count/sum/min/max/average mỗi nhóm |
| `mapping(..., toSet())` | Giữ các giá trị phân biệt, phụ thuộc số giá trị |

Nếu chỉ cần số lượng hoặc doanh thu, **không** thu danh sách đầy đủ chỉ để `size`/`sum` sau đó. Khi số khóa cực lớn, ngay cả những trạng thái gọn cũng dùng bộ nhớ tỷ lệ với số nhóm.

## 15. Nguồn I/O, tài nguyên và dữ liệu có thể thay đổi

`groupingByConcurrent` không tự giải quyết vòng đời tài nguyên của stream. Với `Files.lines` hoặc `Files.walk`, phải đóng nguồn bằng `try-with-resources`, kể cả khi terminal operation hoàn tất:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static ConcurrentMap<String, Long> wordInitials(Path file)
    throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines
            .flatMap(line -> java.util.Arrays.stream(
                line.strip().split("\\s+")
            ))
            .filter(word -> !word.isEmpty())
            .parallel()
            .collect(Collectors.groupingByConcurrent(
                word -> word.substring(0, 1),
                Collectors.counting()
            ));
    }
}
```

`Files.lines` có thể ném `IOException` khi mở và `UncheckedIOException` khi duyệt; không nên biến lỗi đọc thành map rỗng rồi báo thành công. Với file rất lớn, một parallel pipeline I/O không mặc nhiên nhanh hơn: có thể bị giới hạn bởi tốc độ đọc đĩa.

**Nguồn mutable:** tránh chỉnh sửa một `ArrayList` nguồn khi parallel stream đang duyệt. Collector thread-safe không làm nguồn thành thread-safe. Nếu muốn ảnh chụp của dữ liệu, có thể tạo `List.copyOf(source)` ở thời điểm xác định (với điều kiện snapshot được tạo an toàn), rồi thu thập trên snapshot.

## 16. JUnit 5: kiểm chứng nội dung, nhóm và đồng thời

Các test sau dùng lớp `ConcurrentOrderReport` ở mục 6. Chúng **không** giả định thứ tự map hay list trong nhóm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ConcurrentOrderReportTest {

    @Test
    void preservesAllElementsAcrossGroups() {
        var source = ConcurrentOrderReport.sample();
        ConcurrentMap<String, List<ConcurrentOrderReport.Order>> grouped =
            ConcurrentOrderReport.allByRegion(source);

        assertEquals(3, grouped.size());
        assertEquals(source.size(),
            grouped.values().stream().mapToInt(List::size).sum());

        var expectedIds = source.stream()
            .map(ConcurrentOrderReport.Order::id)
            .sorted()
            .toList();
        var actualIds = grouped.values().stream()
            .flatMap(List::stream)
            .map(ConcurrentOrderReport.Order::id)
            .sorted()
            .toList();

        assertEquals(expectedIds, actualIds);
    }

    @Test
    void countsAndSumsByKey() {
        var source = ConcurrentOrderReport.sample();
        var counts = ConcurrentOrderReport.countByRegion(source);
        var totals = ConcurrentOrderReport.paidAmountByRegion(source);

        assertEquals(2L, counts.get("HN"));
        assertEquals(2L, counts.get("HCM"));
        assertEquals(2L, counts.get("DN"));

        assertEquals(150_000L, totals.get("HN"));
        assertEquals(100_000L, totals.get("HCM"));
        assertEquals(10_000L, totals.get("DN"));
    }

    @Test
    void emptySourceReturnsEmptyConcurrentMap() {
        var empty = List.<ConcurrentOrderReport.Order>of();
        assertTrue(ConcurrentOrderReport.countByRegion(empty).isEmpty());
        assertTrue(ConcurrentOrderReport.allByRegion(empty).isEmpty());
    }

    @Test
    void sequentialAndParallelGroupingAgreeOnCounts() {
        var input = IntStream.range(0, 50_000)
            .mapToObj(i -> new ConcurrentOrderReport.Order(
                "ID-" + i,
                "R-" + (i % 17),
                i,
                true
            ))
            .toList();

        Map<String, Long> expected = input.stream()
            .collect(Collectors.groupingBy(
                ConcurrentOrderReport.Order::region,
                Collectors.counting()
            ));

        ConcurrentMap<String, Long> actual = input.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                ConcurrentOrderReport.Order::region,
                Collectors.counting()
            ));

        assertEquals(expected, actual);
        assertEquals(50_000L,
            actual.values().stream().mapToLong(Long::longValue).sum());
    }

    @Test
    void sortedConcurrentMapOrdersKeys() {
        ConcurrentSkipListMap<String, Long> actual =
            ConcurrentOrderReport.sample().parallelStream()
                .collect(Collectors.groupingByConcurrent(
                    ConcurrentOrderReport.Order::region,
                    ConcurrentSkipListMap::new,
                    Collectors.counting()
                ));

        assertEquals(List.of("DN", "HCM", "HN"),
            List.copyOf(actual.keySet()));
    }

    @Test
    void classifierReturningNullIsRejected() {
        record RawOrder(String region) {}
        var input = List.of(new RawOrder(null));

        assertThrows(NullPointerException.class, () ->
            input.parallelStream().collect(
                Collectors.groupingByConcurrent(RawOrder::region)
            )
        );
    }

    @Test
    void downstreamFilteringRetainsGroupWithZeroCount() {
        var source = List.of(
            new ConcurrentOrderReport.Order(
                "X", "ONLY-UNPAID", 10L, false
            )
        );

        var grouped = source.parallelStream()
            .collect(Collectors.groupingByConcurrent(
                ConcurrentOrderReport.Order::region,
                Collectors.filtering(
                    ConcurrentOrderReport.Order::paid,
                    Collectors.counting()
                )
            ));

        assertTrue(grouped.containsKey("ONLY-UNPAID"));
        assertEquals(0L, grouped.get("ONLY-UNPAID"));
    }
}
```

Test `sequentialAndParallelGroupingAgreeOnCounts` dùng nhiều khóa và dữ liệu lớn để phát hiện lỗi phân nhóm. Khi so sánh bản ghi trong `List`, sắp ID hoặc so sánh tần suất; **không** khẳng định list con có thứ tự nguồn.

Các ca nên mở rộng trong dự án thật: nguồn có giá trị trùng, dữ liệu không cân bằng (một khóa rất nóng), mapper tốn CPU, tập khóa lớn, `null` đầu vào, overflow số học và sai số `double`. Một benchmark hiệu năng phải tách khỏi unit test và đo với warm-up, dữ liệu đại diện.

## 17. Phản mẫu thường gặp

| Phản mẫu | Nguy cơ | Cách sửa |
| --- | --- | --- |
| `parallelStream().forEach(sharedHashMap::put)` | Race, mất cập nhật hoặc sai cấu trúc map | Dùng collector đúng hợp đồng |
| Giả định `groupingByConcurrent` giữ thứ tự đầu vào | Các list con là unordered | Dùng `groupingBy` theo encounter order hoặc sắp sau khi thu thập |
| Gọi `result.get(key).add(...)` từ nhiều thread | List bên trong không mặc nhiên thread-safe | Thiết kế đồng bộ/value riêng hoặc snapshot bất biến |
| Dùng `LinkedHashMap::new` với concurrent overload | Không triển khai `ConcurrentMap` | Chọn map concurrent hoặc collector thường |
| Classifier trả `null` | Không có khóa nhóm hợp lệ | Validate, chuẩn hóa hoặc lọc theo nghiệp vụ |
| Dùng `summingLong` cho số tiền có thể tràn | Kết quả sai do overflow | Chọn số học chính xác hoặc kiểm tra tràn |
| Thu `List<Order>` chỉ để đếm | Dùng bộ nhớ lớn, tăng cạnh tranh trên nhóm | `counting()` |
| Kỳ vọng parallel luôn nhanh | Chi phí thread/đồng bộ có thể trội | Đo và xem độ lệch phân bố khóa |
| Đo bằng một lần `System.nanoTime()` không warm-up | Kết quả thiếu tin cậy | Dùng benchmark có thiết kế phù hợp |
| Sửa `ArrayList` nguồn trong lúc thu thập | Non-interference bị vi phạm | Ổn định/snapshot nguồn trước |
| Coi concurrent map là snapshot bất biến | Kết quả vẫn mutable và có thể đổi | Sao chép sau khi thu thập, công bố hợp đồng |
| Cho rằng `CONCURRENT` đồng nghĩa mọi value concurrent | Nhầm an toàn tầng map và tầng value | Phân biệt rõ ownership |

## 18. Bài tập thực hành

### Bài 1 — Nhóm theo vùng

Từ `ConcurrentOrderReport.sample()`, dùng `groupingByConcurrent(Order::region)` lấy `ConcurrentMap<String,List<Order>>`. Kiểm thử mỗi đơn xuất hiện đúng một lần và đúng vùng, không dựa vào thứ tự list.

### Bài 2 — Đếm và tính tổng

Viết hai pipeline với downstream `counting()` và `summingLong(Order::amountVnd)`. So sánh trên nguồn tuần tự và song song. Giải thích khác biệt giữa “phân nhóm” và “gộp các cặp khóa–giá trị” trong `toConcurrentMap`.

### Bài 3 — Nhóm có số liệu bằng 0

Thêm vùng `"ONLY-UNPAID"` chỉ có đơn chưa thanh toán. So sánh `stream.filter(Order::paid).collect(groupingByConcurrent(...))` và `collect(groupingByConcurrent(..., filtering(Order::paid, counting())))` về tập khóa và giá trị của nhóm.

### Bài 4 — Sắp xếp khóa

Chuyển `mapFactory` thành `ConcurrentSkipListMap::new` để nhận khóa tăng dần. Sau đó dùng comparator đảo chiều cho khóa giảm dần. Giải thích vì sao việc sắp xếp khóa không làm các list trong nhóm tự theo encounter order.

### Bài 5 — Danh sách bất biến theo nhóm

Viết downstream `collectingAndThen(mapping(Order::id, toList()), ids -> ids.stream().sorted().toList())`. Kiểm tra mỗi list đã sắp và không thể thêm phần tử. Map ngoài có bất biến không? Nêu cách tạo bản báo cáo snapshot ở cấp map.

### Bài 6 — Hot key

Tạo 100.000 bản ghi, 99% vào khóa `"HN"` và 1% chia cho nhóm khác. So sánh `groupingBy` và `groupingByConcurrent` khi chạy tuần tự/song song. Đo thời gian bằng benchmark có warm-up; giải thích vì sao một nhóm nóng có thể gây tranh chấp.

### Bài 7 — Dữ liệu không hợp lệ

Tạo record có region bằng `null`. Viết chính sách:

- Thất bại rõ ràng với message phù hợp, **hoặc**
- Chuẩn hóa khóa về một kiểu/giá trị có ý nghĩa “chưa xác định”.

Không tự ý bỏ phần tử nếu yêu cầu báo cáo phải đầy đủ.

### Bài 8 — Số học và bộ nhớ

Thu thống kê `LongSummaryStatistics` theo nhóm, so sánh `getCount`, `getSum` và `getAverage`. Giải thích vì sao đối tượng thống kê mutable không đồng nghĩa thread-safe với mọi cập nhật của caller. Nếu tổng có thể vượt `Long.MAX_VALUE`, đề xuất giải pháp chính xác hơn.

## 19. Bảng quyết định cuối bài

| Câu hỏi | Lựa chọn |
| --- | --- |
| Cần map nhóm và không đòi thứ tự của list con? | `groupingByConcurrent(classifier)` |
| Cần số liệu gọn theo từng nhóm? | `groupingByConcurrent(classifier, counting/summing/summarizing)` |
| Cần biến đổi nội dung từng nhóm? | `groupingByConcurrent(classifier, mapping(...))` |
| Cần khóa nhóm tồn tại dù downstream lọc hết? | `groupingByConcurrent(classifier, filtering(...))` |
| Cần danh sách theo thứ tự xác định? | Sắp theo một khóa tường minh sau thu thập, hoặc dùng ordered grouping phù hợp |
| Cần map concurrent có khóa được sắp? | `ConcurrentSkipListMap` qua `mapFactory` |
| Cần giữ thứ tự chèn khóa của nguồn? | Cân nhắc `groupingBy` với `LinkedHashMap` trên ordered stream |
| Cần key/value mapper và merge function? | `toConcurrentMap` |
| Nguồn có khóa `null`? | Không truyền trực tiếp vào concurrent grouping; validate/chuẩn hóa |
| Cần nhiều thread sửa value sau collect? | Thiết kế value và đồng bộ riêng; không tin `toList()` thread-safe |
| Số nhóm ít, một khóa rất nóng? | Benchmark vì tranh chấp có thể cao |
| Nguồn nhỏ hoặc phép mapper rẻ? | Stream tuần tự/`groupingBy` có thể hợp lý hơn |
| Nguồn I/O có tài nguyên? | `try-with-resources` và chính sách lỗi rõ ràng |
| Tổng tiền vượt miền `long` hoặc yêu cầu số học chính xác? | BigInteger/BigDecimal hay collector số học có kiểm tra |
| Kiểm thử đồng thời? | So sánh map theo giá trị/tần suất, không áp thứ tự ngoài hợp đồng |

`Collectors.groupingByConcurrent` là công cụ để **phân nhóm dữ liệu theo khóa vào một `ConcurrentMap`**, đặc biệt khi đầu vào có thể được xử lý song song và không cần bảo toàn encounter order trong danh sách nhóm. Tính concurrent của collector giúp framework tổ chức tích lũy đúng theo hợp đồng; nó **không** biến mọi value thành cấu trúc thread-safe, không giải quyết lỗi dữ liệu nguồn, cũng không đảm bảo hiệu năng tốt hơn. Hãy chọn downstream theo nhu cầu thật, xác định rõ chính sách thứ tự, kiểm thử tính đầy đủ dữ liệu và đo hiệu năng với phân bố khóa thực tế trước khi áp dụng trong hệ thống.
