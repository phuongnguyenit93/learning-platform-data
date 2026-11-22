# Kết hợp `partitioningBy` với Collector phía sau

Trong Java Stream API, `Collectors.partitioningBy(predicate)` phân hoạch dữ liệu thành hai nhóm theo một điều kiện đúng/sai. Khi muốn làm **nhiều hơn việc lưu danh sách phần tử** — chẳng hạn đếm đơn hàng, cộng doanh thu, tìm đơn giá trị lớn nhất hoặc tiếp tục phân nhóm theo khu vực — ta dùng overload nhận **Collector phía sau** (*downstream collector*).

Bài thuộc chương **Phân nhóm và phân hoạch** của module **JAVA_STREAM_API**. Mục tiêu là hiểu hợp đồng của `partitioningBy(predicate, downstream)`, cách kết hợp với `counting`, `mapping`, `summingLong`, `summarizingLong`, `filtering`, `groupingBy`, `maxBy`, `collectingAndThen` và `teeing`. Bài cũng giải thích kết quả trên nhóm rỗng, thứ tự, xử lý song song và giới hạn về trạng thái, tài nguyên và hiệu năng khi xây dựng pipeline `filter`, `map`, `reduce`, `collect`.

Các ví dụ sử dụng Java 17 để có `record`. `partitioningBy` và phần lớn collector cơ bản đã có từ Java 8; `Collectors.filtering` có từ Java 9, `Collectors.teeing` từ Java 12.

## 1. Tình huống: phân hoạch đơn hàng theo trạng thái thanh toán

Giả sử hệ thống có tập đơn hàng sau; tiền được lưu dưới dạng **số xu (`long`)** để tránh sai số nhị phân khi cộng các khoản tiền nhỏ:

```java
import java.util.List;

record Order(String id, String region, long amountCents, boolean paid) {}

List<Order> orders = List.of(
        new Order("O-101", "Bắc", 12_500, true),
        new Order("O-102", "Nam",  5_000, false),
        new Order("O-103", "Bắc",  7_500, true),
        new Order("O-104", "Bắc", 10_000, false),
        new Order("O-105", "Nam",  3_000, true)
);
```

Ta cần tạo hai nhóm:

- **`true`**: đơn hàng đã thanh toán (`paid == true`).
- **`false`**: đơn hàng chưa thanh toán (`paid == false`).

Nếu chỉ cần giữ danh sách đơn hàng, dùng overload một đối số:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Order>> byPaid = orders.stream()
        .collect(Collectors.partitioningBy(Order::paid));

System.out.println(byPaid.get(true).size());  // 3
System.out.println(byPaid.get(false).size()); // 2
```

Nhưng khi chỉ muốn đếm, việc lưu tất cả `Order` trong hai danh sách là không cần thiết. Đó là lý do sử dụng **downstream collector**.

## 2. Cú pháp và cách hiểu `downstream`

Overload có hai đối số có dạng khái niệm:

```java
static <T, D, A> Collector<T, ?, Map<Boolean, D>> partitioningBy(
        Predicate<? super T> predicate,
        Collector<? super T, A, D> downstream
);
```

Trong đó:

| Thành phần | Vai trò |
|---|---|
| `T` | Kiểu phần tử nguồn, ví dụ `Order` |
| `predicate` | Phân loại từng phần tử vào khóa `true` hoặc `false` |
| `downstream` | Quy định cách tổng hợp **bên trong từng nhóm** |
| `D` | Kiểu kết quả mà downstream tạo ra cho mỗi nhóm |
| `Map<Boolean, D>` | Kết quả cuối, chứa hai giá trị tổng hợp tương ứng với hai khóa Boolean |

Có thể đọc pipeline như sau:

```text
Stream<Order>
     |
     v
  Order::paid
     |
     +------------> true  ----> downstream ----> D cho nhóm true
     |
     +------------> false ----> downstream ----> D cho nhóm false
                                               |
                                               v
                                          Map<Boolean, D>
```

Ví dụ đếm:

```java
Map<Boolean, Long> counts = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(counts.get(true));  // 3
System.out.println(counts.get(false)); // 2
```

`Collectors.counting()` là downstream collector. Nó nhận các phần tử `Order` của **từng phân hoạch** và trả về `Long`. Do đó kết quả toàn bộ là `Map<Boolean, Long>`, không phải `Map<Boolean, List<Order>>`.

## 3. Hợp đồng quan trọng: luôn có hai khóa Boolean

Khác biệt nổi bật của `partitioningBy` là kết quả luôn có **cả hai khóa `Boolean.TRUE` và `Boolean.FALSE`**, ngay cả khi một hoặc cả hai phân hoạch không nhận phần tử nào.

```java
Map<Boolean, Long> allPaid = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(allPaid.get(true));            // 3
System.out.println(allPaid.get(false));           // 0
System.out.println(allPaid.containsKey(false));   // true
```

Nguồn hoàn toàn rỗng vẫn tạo **hai kết quả downstream cho hai phân hoạch rỗng**:

```java
import java.util.stream.Stream;

Map<Boolean, List<Order>> emptyLists = Stream.<Order>empty()
        .collect(Collectors.partitioningBy(Order::paid));

System.out.println(emptyLists.get(true));  // []
System.out.println(emptyLists.get(false)); // []
```

Nhưng “kết quả downstream cho nhóm rỗng” **không phải lúc nào cũng là `null` hay một danh sách rỗng**. Nó phụ thuộc collector được chọn:

| Downstream | Giá trị cho phân hoạch rỗng |
|---|---|
| `toList()` | Danh sách rỗng |
| `toSet()` | Tập rỗng |
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `averagingLong(...)` | `0.0` |
| `maxBy(...)` | `Optional.empty()` |
| `groupingBy(...)` | Map rỗng |
| `summarizingLong(...)` | Đối tượng thống kê có `count == 0` |

Chẳng hạn:

```java
Map<Boolean, Long> none = Stream.<Order>empty()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(none.get(true));  // 0
System.out.println(none.get(false)); // 0
```

**Lưu ý:** Có đủ hai khóa không có nghĩa `Map` có thứ tự duyệt cố định. Không dựa vào việc `entrySet()` in `false` trước hay `true` trước. Cũng không được mặc định kiểu triển khai, khả năng chỉnh sửa hay tính thread-safe của `Map` kết quả.

## 4. Đếm và tính tổng trong từng phân hoạch

### 4.1. Đếm với `counting()`

```java
Map<Boolean, Long> countByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(countByPayment.get(true));  // 3
System.out.println(countByPayment.get(false)); // 2
```

Kiểu giá trị là `Long`, không phải `Integer`. Nếu mục tiêu chỉ là số lượng hai nhóm, cách này nói rõ yêu cầu và không phải lưu toàn bộ đối tượng.

### 4.2. Cộng doanh thu với `summingLong()`

```java
Map<Boolean, Long> moneyByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.summingLong(Order::amountCents)
        ));

System.out.println(moneyByPayment.get(true));  // 23000
System.out.println(moneyByPayment.get(false)); // 15000
```

Kết quả nhóm đã thanh toán là `12500 + 7500 + 3000 = 23000` xu, nhóm chưa thanh toán là `5000 + 10000 = 15000` xu.

Nếu chỉ cần tổng tiền, hãy dùng `summingLong` thay vì lưu hai `List<Order>` rồi duyệt lại để cộng. Cần nhớ `long` **vẫn có thể overflow** nếu tổng vượt miền biểu diễn; lưu tiền theo đơn vị nguyên loại bỏ sai số nhị phân nhưng không loại bỏ nguy cơ tràn số.

### 4.3. Tính trung bình với `averagingLong()`

```java
Map<Boolean, Double> averageByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.averagingLong(Order::amountCents)
        ));

System.out.println(averageByPayment.get(true));  // 7666.666666666667 (xấp xỉ)
System.out.println(averageByPayment.get(false)); // 7500.0
```

Nhóm đã thanh toán có tổng `23000` xu chia cho `3` đơn hàng. Kết quả trung bình là `double` và mang tính xấp xỉ. Với nhóm rỗng, `averagingLong` trả `0.0`; giá trị này **không cho biết** nhóm thực sự có trung bình bằng 0 hay không có phần tử. Nếu cần phân biệt, thu thập thêm số lượng hoặc dùng thống kê có `count`.

### 4.4. Nhiều thống kê với `summarizingLong()`

```java
import java.util.LongSummaryStatistics;

Map<Boolean, LongSummaryStatistics> statistics = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.summarizingLong(Order::amountCents)
        ));

LongSummaryStatistics paid = statistics.get(true);
System.out.println(paid.getCount());   // 3
System.out.println(paid.getSum());     // 23000
System.out.println(paid.getMin());     // 3000
System.out.println(paid.getMax());     // 12500
```

`summarizingLong` cung cấp `count`, `sum`, `min`, `max` và `average` mà không cần duyệt lại đầu vào. Với một nhóm rỗng, `getCount() == 0`, nhưng `getMin()` và `getMax()` có giá trị khởi tạo lần lượt `Long.MAX_VALUE` và `Long.MIN_VALUE`. Không coi chúng là cực trị nghiệp vụ khi nhóm không có dữ liệu.

## 5. `mapping()`: đổi kiểu dữ liệu trước khi thu thập

`Collectors.mapping(mapper, downstream)` biến từng `Order` thành một giá trị khác **trong phạm vi phân hoạch tương ứng**. Nó giúp chọn trường dữ liệu cần giữ ở kết quả cuối.

```java
Map<Boolean, List<String>> idsByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::id,
                        Collectors.toList()
                )
        ));

System.out.println(idsByPayment.get(true)); 
// [O-101, O-103, O-105]
System.out.println(idsByPayment.get(false));
// [O-102, O-104]
```

`T` của nguồn là `Order`, nhưng `mapping` biến nó thành `String`, rồi `toList` cho kết quả `List<String>`. Kết quả toàn bộ có kiểu `Map<Boolean, List<String>>`.

### 5.1. Lấy giá trị duy nhất trong mỗi nhóm

```java
import java.util.Set;

Map<Boolean, Set<String>> regionsByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::region,
                        Collectors.toSet()
                )
        ));

System.out.println(regionsByPayment.get(true).equals(Set.of("Bắc", "Nam")));
// true
System.out.println(regionsByPayment.get(false).equals(Set.of("Bắc", "Nam")));
// true
```

`toSet()` loại trùng theo hợp đồng của `Set`. Nó **không bảo đảm thứ tự phần tử** hay kiểu `Set` cụ thể. Nếu cần các mã vùng duy nhất theo thứ tự xuất hiện lần đầu ở nguồn có encounter order, dùng `toCollection(LinkedHashSet::new)`:

```java
import java.util.LinkedHashSet;

Map<Boolean, LinkedHashSet<String>> orderedRegions = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(
                        Order::region,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));

System.out.println(orderedRegions.get(true)); // [Bắc, Nam]
```

Giữ encounter order có thể tăng chi phí phối hợp khi xử lý song song. Nếu thứ tự không quan trọng, không nên thêm ràng buộc chỉ để được đầu ra “đẹp mắt” khi in.

### 5.2. `mapping` trước hay `map` trên stream?

Trong ví dụ chỉ cần phân hoạch rồi lấy `id`, có thể viết:

```java
// Đúng: phân hoạch Order trước, rồi lấy id trong mỗi nhóm.
Map<Boolean, List<String>> result = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.mapping(Order::id, Collectors.toList())
        ));
```

Nếu viết `orders.stream().map(Order::id)` **trước** `partitioningBy`, phần tử nguồn đã trở thành `String` và không còn `paid` để phân loại bằng `Order::paid`. Vì vậy, đặt `mapping` vào downstream là cách diễn đạt tự nhiên khi phép phân loại cần dữ liệu gốc còn kết quả chỉ cần một phần trường.

## 6. `filtering()` bên trong phân hoạch

`Collectors.filtering(predicate, downstream)` (Java 9+) cho phép mỗi phân hoạch chỉ **đóng góp những phần tử đạt thêm điều kiện** cho collector phía sau.

Ví dụ chỉ đếm đơn hàng có giá trị từ `10000` xu trở lên trong từng trạng thái thanh toán:

```java
Map<Boolean, Long> highValueCounts = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.filtering(
                        order -> order.amountCents() >= 10_000,
                        Collectors.counting()
                )
        ));

System.out.println(highValueCounts.get(true));  // 1: O-101
System.out.println(highValueCounts.get(false)); // 1: O-104
```

Ta có thể đọc pipeline theo thứ tự:

1. Dựa vào `paid` để xác định phần tử thuộc phân hoạch `true` hay `false`.
2. Trong phân hoạch đó, chỉ giữ đơn có `amountCents >= 10000` cho bước đếm.
3. Đưa kết quả đếm của hai phân hoạch vào `Map<Boolean, Long>`.

Lọc **trước** khi gọi `partitioningBy` cũng có thể cho cùng số đếm trong ví dụ này:

```java
Map<Boolean, Long> alternative = orders.stream()
        .filter(order -> order.amountCents() >= 10_000)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));
```

Khác biệt nằm ở **cách biểu đạt các bước xử lý**: lọc trước collector loại phần tử ra khỏi toàn bộ luồng; `filtering` downstream diễn đạt điều kiện bổ sung trong cách tổng hợp từng phân hoạch. Với `partitioningBy`, hai khóa Boolean vẫn xuất hiện dù một phân hoạch không còn phần tử sau lọc. Khi lồng thêm `groupingBy`, đặt `filtering` ở đâu có thể ảnh hưởng những nhóm con nào được tạo ra; cần xác định mục đích trước khi di chuyển bước lọc.

## 7. Kết hợp `partitioningBy` với `groupingBy`

Khi hai chiều phân tích cùng quan trọng, ta có thể **phân hoạch trước, phân nhóm sau**.

Yêu cầu: với mỗi trạng thái thanh toán, tính tổng tiền theo vùng:

```java
Map<Boolean, Map<String, Long>> totalsByPaymentAndRegion =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.groupingBy(
                                Order::region,
                                Collectors.summingLong(Order::amountCents)
                        )
                ));

System.out.println(totalsByPaymentAndRegion.get(true).get("Bắc"));  // 20000
System.out.println(totalsByPaymentAndRegion.get(true).get("Nam"));  // 3000
System.out.println(totalsByPaymentAndRegion.get(false).get("Bắc")); // 10000
System.out.println(totalsByPaymentAndRegion.get(false).get("Nam")); // 5000
```

Cấu trúc kết quả:

```text
Map<Boolean, Map<String, Long>>
  true
    Bắc -> 20000
    Nam -> 3000
  false
    Bắc -> 10000
    Nam -> 5000
```

Đổi thứ tự nesting thành `groupingBy(Order::region, partitioningBy(Order::paid, summingLong(...)))` sẽ tạo `Map<String, Map<Boolean, Long>>`. Hai cách có thể chứa cùng số liệu, nhưng phục vụ **hai cách tra cứu khác nhau**:

- `Map<Boolean, Map<String, Long>>`: nhìn trạng thái thanh toán trước.
- `Map<String, Map<Boolean, Long>>`: nhìn khu vực trước.

Quan trọng: `partitioningBy` luôn có hai khóa Boolean **ở tầng mà nó được dùng**. Nhưng `groupingBy` chỉ tạo khóa cho những nhóm phân loại thực sự xuất hiện. Nếu một phân hoạch không có đơn hàng, map vùng bên trong của nó là map rỗng, không tự chứa tất cả các vùng tưởng tượng.

### 7.1. Nếu muốn cộng theo vùng mà không dùng `groupingBy`

Vì `toMap` cũng là một collector, có thể dùng nó làm downstream và cung cấp merge function:

```java
Map<Boolean, Map<String, Long>> amountsByRegion =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.toMap(
                                Order::region,
                                Order::amountCents,
                                Long::sum
                        )
                ));

System.out.println(amountsByRegion.get(true).get("Bắc")); // 20000
```

Nếu bỏ `Long::sum`, hai đơn đã thanh toán cùng vùng `Bắc` tạo **khóa trùng** trong `toMap`, có thể gây `IllegalStateException`. `groupingBy(..., summingLong(...))` diễn đạt mục đích phân nhóm và cộng rõ ràng hơn. Ngoài ra, `groupingBy` không chấp nhận classifier trả khóa `null`; cần quy định chính sách cho vùng thiếu dữ liệu trước khi dùng.

## 8. Tìm phần tử tốt nhất với `maxBy` hoặc `minBy`

Một phân hoạch có thể cần lấy **một đối tượng thỏa tiêu chí cực trị**. `Collectors.maxBy` trả `Optional<T>` cho từng nhóm, vì nhóm có thể rỗng:

```java
import java.util.Comparator;
import java.util.Optional;

Map<Boolean, Optional<Order>> biggestByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.maxBy(
                        Comparator.comparingLong(Order::amountCents)
                                .thenComparing(Order::id)
                )
        ));

System.out.println(biggestByPayment.get(true).orElseThrow().id());
// O-101
System.out.println(biggestByPayment.get(false).orElseThrow().id());
// O-104
```

`thenComparing(Order::id)` định nghĩa tiêu chí phụ để phân định khi tiền bằng nhau. Nếu không có tiêu chí phụ và hai đơn có cùng giá trị lớn nhất, không nên dựa vào một lựa chọn đại diện không được quy định bởi nghiệp vụ.

Đối với nguồn không có phần tử trong một nhóm:

```java
Map<Boolean, Optional<Order>> noUnpaid = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.maxBy(Comparator.comparingLong(Order::amountCents))
        ));

System.out.println(noUnpaid.get(false).isEmpty()); // true
```

Không dùng `orElseThrow()` khi phân hoạch có thể rỗng trừ khi rỗng thật sự là lỗi nghiệp vụ. Nếu muốn chuyển `Optional<Order>` thành mã định danh hoặc giá trị mặc định, hãy xử lý `Optional` rõ ràng.

## 9. `collectingAndThen`: hoàn thiện kết quả của từng phân hoạch

`Collectors.collectingAndThen(downstream, finisher)` cho phép biến đổi **kết quả đã thu thập xong của mỗi nhóm**.

Ví dụ kết quả là danh sách mã đơn hàng không thể chỉnh sửa:

```java
Map<Boolean, List<String>> immutableListsByPayment =
        orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.collectingAndThen(
                                Collectors.mapping(
                                        Order::id,
                                        Collectors.toList()
                                ),
                                List::copyOf
                        )
                ));

System.out.println(immutableListsByPayment.get(true));
// [O-101, O-103, O-105]

// immutableListsByPayment.get(true).add("O-999");
// Ném UnsupportedOperationException.
```

Lưu ý **mỗi danh sách** được bọc/thay bằng kết quả không thể chỉnh sửa, nhưng không nên suy rằng **bản thân `Map`** cũng không thể chỉnh sửa. Nếu cần cả hai cấp không thể chỉnh sửa, có thể bọc thêm một `collectingAndThen` bên ngoài:

```java
Map<Boolean, List<String>> fullyReadOnly = orders.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.partitioningBy(
                        Order::paid,
                        Collectors.collectingAndThen(
                                Collectors.mapping(Order::id, Collectors.toList()),
                                List::copyOf
                        )
                ),
                Map::copyOf
        ));
```

`List.copyOf` và `Map.copyOf` không chấp nhận phần tử/giá trị `null`. Chúng tạo các kết quả không thể chỉnh sửa ở mức collection; **không tạo deep immutability** nếu phần tử bên trong là đối tượng mutable.

## 10. `teeing`: tính nhiều chỉ số cùng lúc (Java 12+)

`Collectors.teeing(left, right, merger)` đưa mỗi phần tử vào **hai collector con**, sau đó kết hợp hai kết quả thành một. Khi dùng làm downstream, ta có thể tính cả số lượng và tổng tiền của từng phân hoạch:

```java
record Summary(long count, long totalCents) {}

Map<Boolean, Summary> summaryByPayment = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Order::amountCents),
                        Summary::new
                )
        ));

System.out.println(summaryByPayment.get(true));
// Summary[count=3, totalCents=23000]
System.out.println(summaryByPayment.get(false));
// Summary[count=2, totalCents=15000]
```

Ý nghĩa:

- `counting()` tạo `Long` số đơn hàng trong một phân hoạch.
- `summingLong(...)` tạo `Long` tổng tiền của chính phân hoạch đó.
- `Summary::new` ghép hai kết quả thành một record bất biến.

Với phân hoạch rỗng, kết quả là `Summary(0, 0)`. Đó là hợp đồng rõ ràng hơn việc tự tạo một biến tổng mutable bên ngoài pipeline và cập nhật nó qua `peek`/`forEach`.

Trong ứng dụng dùng Java 8–11, khi chưa có `teeing`, có thể dùng `summarizingLong` nếu cần bộ thống kê sẵn có, hoặc thiết kế collector phù hợp. Không cần tạo hai stream chỉ để đếm và cộng nếu một collector đã giải quyết được cả hai yêu cầu.

## 11. Phân biệt `partitioningBy` và `groupingBy`

Hai collector đều chia dữ liệu thành các nhóm nhưng có hợp đồng khác nhau:

| Tiêu chí | `partitioningBy(predicate, downstream)` | `groupingBy(classifier, downstream)` |
|---|---|---|
| Khóa | Chỉ `true` và `false` | Khóa kiểu `K` từ classifier |
| Số nhóm có thể tạo | Luôn đúng hai khóa Boolean | Phụ thuộc các khóa thực tế xuất hiện |
| Nhóm rỗng | Vẫn có kết quả downstream | Khóa không xuất hiện thường không có trong map |
| Điều kiện đầu vào | Một `Predicate<T>` | Một `Function<T, K>` |
| Dùng khi | Hai nhánh có/không, đạt/không đạt | Nhiều nhóm theo vùng, loại, trạng thái |

Ví dụ khi tất cả đơn đều đã thanh toán:

```java
List<Order> paidOnly = orders.stream()
        .filter(Order::paid)
        .toList();

Map<Boolean, Long> partitioned = paidOnly.stream()
        .collect(Collectors.partitioningBy(
                Order::paid, Collectors.counting()
        ));

Map<Boolean, Long> grouped = paidOnly.stream()
        .collect(Collectors.groupingBy(
                Order::paid, Collectors.counting()
        ));

System.out.println(partitioned.containsKey(false)); // true
System.out.println(partitioned.get(false));         // 0
System.out.println(grouped.containsKey(false));     // false
```

Nếu cần **chính xác hai ô kết quả**, kể cả khi một ô rỗng, `partitioningBy` diễn đạt mô hình tốt hơn `groupingBy`. Nếu cần nhiều trạng thái, chẳng hạn `NEW`, `PAID`, `CANCELLED`, không nên ép chúng thành `true`/`false` làm mất thông tin; hãy dùng `groupingBy` với khóa miền dữ liệu phù hợp.

## 12. Null, ngoại lệ và trạng thái dùng chung

### 12.1. Điều kiện phân hoạch phải xác định

Với dữ liệu nguồn đúng kiểu `Order` và `paid` là `boolean` primitive, predicate `Order::paid` luôn trả `true` hoặc `false`. Nếu nguồn chứa **phần tử `null`**, method reference này có thể ném `NullPointerException` khi phần tử được xử lý:

```java
import java.util.Objects;

Map<Boolean, Long> safeCounts = java.util.stream.Stream
        .of(new Order("O-X", "Bắc", 100, true), null)
        .filter(Objects::nonNull)
        .collect(Collectors.partitioningBy(
                Order::paid, Collectors.counting()
        ));

System.out.println(safeCounts.get(true)); // 1
```

Trong bài toán có trạng thái thanh toán kiểu `Boolean` (có thể `null`), không tự coi `null` là `false` nếu nghiệp vụ cần phân biệt “chưa biết” với “chưa thanh toán”. `Boolean.TRUE.equals(value)` sẽ gom cả `false` và `null` vào nhánh `false`; đó là **lựa chọn nghiệp vụ có chủ đích**, không phải tính chất mặc định của `partitioningBy`.

Muốn ba trạng thái riêng `TRUE`, `FALSE`, `UNKNOWN`, hãy dùng `groupingBy` với enum hoặc một khóa không null thể hiện đủ ba trạng thái.

### 12.2. Downstream cũng có thể thất bại

Nếu mapper hay classifier trong downstream ném exception, lỗi phát sinh khi `collect` thực sự tiêu thụ pipeline. Ví dụ `Collectors.groupingBy(Order::region)` không chấp nhận classifier trả khóa `null` trong các trường hợp thông thường; `Collectors.toMap` có thể ném lỗi do trùng khóa hoặc `null` value.

Vì vậy, việc predicate đã phân hoạch thành công **không đảm bảo** toàn bộ downstream collector thành công. Hãy xác định chính sách cho dữ liệu thiếu/trùng trước khi thu thập.

### 12.3. Tránh side effect trong predicate và collector

```java
// Không nên dùng biến ngoài để tự ghi kết quả trong pipeline song song.
// List<Order> paid = new ArrayList<>();
// orders.parallelStream().filter(order -> {
//     if (order.paid()) paid.add(order); // không an toàn
//     return order.paid();
// }).count();
```

Predicate nên **stateless** và **non-interfering**, không sửa nguồn hoặc cập nhật một `ArrayList` chung. Các collector chuẩn phối hợp tích lũy và kết hợp theo hợp đồng; không cần tự quản lý một container dùng chung bằng side effect.

## 13. Song song, thứ tự và hiệu năng

```java
Map<Boolean, Long> parallelCounts = orders.parallelStream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()
        ));

System.out.println(parallelCounts.get(true));  // 3
System.out.println(parallelCounts.get(false)); // 2
```

Pipeline song song có thể chia nguồn thành nhiều phần rồi kết hợp **hai phân hoạch trung gian**. `Collectors.partitioningBy` không cam kết map kết quả là một map concurrent để các thread bên ngoài cùng cập nhật. Tránh giả định `Map<Boolean, D>` trả về thread-safe chỉ vì nguồn là `parallelStream()`.

Các yếu tố ảnh hưởng hiệu năng:

1. **Loại downstream:** `counting` và `summingLong` chỉ giữ tổng hợp nhỏ; `toList` có thể giữ toàn bộ phần tử, còn `groupingBy` lồng nhau tạo thêm map và container.
2. **Chi phí predicate/mapper:** nên dùng hàm thuần, đơn giản; đừng thực hiện I/O hay sửa trạng thái ngoài từ predicate.
3. **Encounter order:** với nguồn có thứ tự, collector như `toList` thường cho kết quả phần tử theo encounter order; một số collector như `toSet` không cam kết thứ tự. Không dựa vào thứ tự duyệt của map hai khóa.
4. **Số phần tử:** chỉ có **hai nhóm** không có nghĩa dùng song song chắc chắn nhanh hơn. Chi phí phân tách, tạo và ghép kết quả có thể vượt lợi ích với nguồn nhỏ.
5. **Kiểu số:** cộng `double` có thể chịu sai số và thay đổi theo cách gộp song song; `long` tránh sai số dấu phẩy động cho đơn vị nguyên nhưng vẫn có thể overflow.

`collect` là terminal operation, nên sau khi gọi không thể tiêu thụ lại cùng đối tượng stream. Với nguồn không giới hạn, `partitioningBy(..., counting())` hoặc `toList()` thông thường **không kết thúc** nếu không có giới hạn phù hợp. Với nguồn gắn tài nguyên, ví dụ `Files.lines(path)`, phải quản lý `close()` bằng `try-with-resources`; `partitioningBy` không tự đóng tài nguyên nguồn.

## 14. Chương trình tổng hợp có thể chạy (Java 17+)

Chương trình sau là một ví dụ độc lập. Nó dùng cùng tập đơn hàng để tạo danh sách, đếm, cộng tiền, nhóm theo vùng, tìm đơn lớn nhất và kết hợp hai phép thống kê:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

public class PartitioningDownstreamDemo {
    record Order(String id, String region, long amountCents, boolean paid) {}
    record Summary(long count, long totalCents) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-101", "Bắc", 12_500, true),
                new Order("O-102", "Nam",  5_000, false),
                new Order("O-103", "Bắc",  7_500, true),
                new Order("O-104", "Bắc", 10_000, false),
                new Order("O-105", "Nam",  3_000, true)
        );

        Map<Boolean, Long> counts = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.counting()
                ));
        System.out.println(counts.get(true));  // 3
        System.out.println(counts.get(false)); // 2

        Map<Boolean, Long> totals = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.summingLong(Order::amountCents)
                ));
        System.out.println(totals.get(true));  // 23000
        System.out.println(totals.get(false)); // 15000

        Map<Boolean, Set<String>> regions = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.mapping(Order::region, Collectors.toSet())
                ));
        System.out.println(regions.get(true).equals(Set.of("Bắc", "Nam")));
        // true

        Map<Boolean, Map<String, Long>> byRegion = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.groupingBy(
                                Order::region,
                                Collectors.summingLong(Order::amountCents)
                        )
                ));
        System.out.println(byRegion.get(true).get("Bắc")); // 20000

        Map<Boolean, Optional<Order>> largest = orders.stream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.maxBy(
                                Comparator.comparingLong(Order::amountCents)
                                        .thenComparing(Order::id)
                        )
                ));
        System.out.println(largest.get(false).orElseThrow().id());
        // O-104

        Map<Boolean, Summary> summaries = orders.parallelStream()
                .collect(Collectors.partitioningBy(
                        Order::paid,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingLong(Order::amountCents),
                                Summary::new
                        )
                ));
        System.out.println(summaries.get(true));
        // Summary[count=3, totalCents=23000]

        Map<Boolean, Long> noUnpaid = orders.stream()
                .filter(Order::paid)
                .collect(Collectors.partitioningBy(
                        Order::paid, Collectors.counting()
                ));
        System.out.println(noUnpaid.containsKey(false)); // true
        System.out.println(noUnpaid.get(false));         // 0
    }
}
```

Ở ví dụ song song, `teeing` kết hợp các collector chuẩn để thu thập cả số lượng và tổng. Không dùng biến `count` hoặc `sum` nằm ngoài pipeline để tự cập nhật qua nhiều thread.

## 15. Các lỗi thường gặp và cách sửa

| Cách hiểu hoặc cách làm | Vấn đề | Cách phù hợp |
|---|---|---|
| Nghĩ `partitioningBy` chỉ có khóa đã xuất hiện | Hợp đồng luôn tạo hai khóa Boolean | Truy cập trực tiếp `get(true)`/`get(false)`, xử lý giá trị downstream cho nhóm rỗng |
| Nghĩ downstream mặc định là `List` | Kết quả phụ thuộc collector | Dùng đúng kiểu `Map<Boolean, D>` |
| Dùng `toList` rồi đếm/cộng lại dù chỉ cần thống kê | Lưu dữ liệu và duyệt lại không cần thiết | Dùng `counting`, `summingLong`, `summarizingLong` |
| `averagingLong` trả `0.0` nên nhóm chắc có dữ liệu | Nhóm rỗng cũng có thể trả `0.0` | Xem thêm `count` hoặc `Optional` phù hợp |
| `orders.map(Order::id)` trước phân hoạch theo `paid` | Sau `map` không còn dữ liệu để kiểm tra `paid` | Dùng `mapping(Order::id, ...)` làm downstream |
| Dùng `toSet` rồi mong giữ thứ tự | `toSet` không bảo đảm thứ tự | Dùng `toCollection(LinkedHashSet::new)` khi cần |
| Nghĩ `groupingBy` lồng trong `partitioningBy` luôn tạo mọi khóa vùng | Chỉ nhóm Boolean cố định; nhóm vùng có thể rỗng | Xử lý map vùng rỗng khi cần |
| Dùng `toMap` downstream với khóa vùng trùng mà thiếu merge | Có thể ném `IllegalStateException` | Dùng merge phù hợp hoặc `groupingBy` |
| Gọi `Optional.get()` trên `maxBy` của nhóm rỗng | Có thể ném `NoSuchElementException` | Dùng `isPresent`, `orElse`, `orElseThrow` có chủ đích |
| Mặc định `Map` kết quả được sắp xếp hoặc thread-safe | Collector không cam kết | Chọn API/cấu trúc kết quả theo yêu cầu |
| Predicate cập nhật `ArrayList` dùng chung khi chạy song song | Data race và side effect khó kiểm soát | Predicate thuần, collector phù hợp |
| Thu thập từ stream vô hạn không giới hạn | Terminal operation không hoàn tất | Dùng nguồn hữu hạn hoặc `limit` trước `collect` |

## 16. Tự kiểm tra

1. **Khác biệt giữa `partitioningBy(predicate)` và `partitioningBy(predicate, counting())` là gì?** Cách đầu trả `Map<Boolean, List<T>>`, cách sau trả `Map<Boolean, Long>`.
2. **Nếu mọi phần tử đều thỏa predicate, kết quả có khóa `false` không?** Có; downstream cho nhóm `false` nhận phân hoạch rỗng.
3. **`Stream.<Order>empty().collect(partitioningBy(Order::paid, counting()))` trả những gì?** Map có cả `true -> 0L` và `false -> 0L`.
4. **Muốn tổng tiền theo trạng thái thanh toán, dùng downstream nào?** `Collectors.summingLong(Order::amountCents)`.
5. **Muốn danh sách `id` theo trạng thái, chọn gì?** `Collectors.mapping(Order::id, Collectors.toList())` bên trong `partitioningBy`.
6. **Muốn tập vùng không trùng theo từng trạng thái?** `mapping(Order::region, toSet())`; nếu cần thứ tự xuất hiện đầu tiên thì dùng `toCollection(LinkedHashSet::new)`.
7. **`filtering` downstream khác việc lọc trước collector ở chỗ nào?** Nó diễn đạt điều kiện lọc bên trong cách tổng hợp từng phân hoạch; cần xét vị trí bước lọc khi lồng collector khác.
8. **Vì sao `partitioningBy(..., groupingBy(...))` không tự chứa mọi vùng?** Vì `groupingBy` chỉ sinh khóa vùng có dữ liệu; chỉ hai khóa Boolean là luôn hiện diện.
9. **Vì sao `maxBy` trả `Optional<Order>`?** Để mô tả trường hợp phân hoạch không có phần tử phù hợp.
10. **`teeing(counting(), summingLong(...), Summary::new)` tạo gì?** Một `Summary` chứa số đơn và tổng tiền của mỗi phân hoạch.
11. **`partitioningBy` chạy từ `parallelStream` có trả map thread-safe không?** Không có bảo đảm đó; framework quản lý quá trình thu thập, không biến kết quả thành concurrent map.
12. **Khi nào không nên dùng `partitioningBy`?** Khi có hơn hai trạng thái cần phân biệt; dùng `groupingBy` với khóa nhiều giá trị để không mất thông tin.

**Ghi nhớ:** `partitioningBy(predicate, downstream)` có cấu trúc **hai khóa Boolean cố định**, còn downstream quyết định **giá trị của từng khóa**. Chọn `counting` để đếm, `summingLong` để cộng, `mapping` để đổi kiểu, `groupingBy` để nhóm thêm, `maxBy` cho cực trị, `collectingAndThen` cho bước hoàn thiện và `teeing` để lấy nhiều chỉ số. Luôn kiểm tra kết quả của nhóm rỗng, các yêu cầu về thứ tự, kiểu số và hợp đồng xử lý song song trước khi đưa pipeline vào ứng dụng.
