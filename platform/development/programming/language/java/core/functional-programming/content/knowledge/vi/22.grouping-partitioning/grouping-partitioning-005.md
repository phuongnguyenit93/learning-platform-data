# Phân biệt `partitioningBy()` với `groupingBy()` theo boolean trong Java Stream

## 1. Cùng chia hai nhóm, nhưng hợp đồng kết quả không giống nhau

Khi dùng Stream API để thu thập dữ liệu (*collect*), chúng ta thường muốn tách phần tử thành hai nhóm, ví dụ:

- Đơn hàng có tổng tiền từ 100 trở lên và đơn hàng dưới 100.
- Học viên đậu và chưa đậu.
- Yêu cầu hợp lệ và không hợp lệ.
- Công việc đã hoàn thành và chưa hoàn thành.

Hai collector thường thấy là:

```java
Collectors.partitioningBy(predicate)
Collectors.groupingBy(classifier)
```

Cả hai **có thể tạo `Map<Boolean, List<T>>`** khi điều kiện chia nhóm trả boolean. Tuy nhiên, cách chúng định nghĩa tập khóa rất khác:

**`partitioningBy(predicate)` luôn có hai khóa `Boolean.TRUE` và `Boolean.FALSE`**, ngay cả khi một nhóm không có phần tử hoặc cả nguồn rỗng. Danh sách tương ứng có thể rỗng.

**`groupingBy(element -> booleanExpression)` chỉ tạo khóa cho những kết quả phân loại thực sự gặp trong nguồn.** Nếu không có phần tử nào trả false, map không có khóa false. Với nguồn rỗng, kết quả là map rỗng.

Đây là khác biệt mang tính **contract**, không chỉ là sở thích cú pháp. Nó ảnh hưởng đến việc sử dụng `get(false)`, khả năng xảy ra `null`, số nhóm khi không có dữ liệu, các bộ thống kê và cách thiết kế API.

Ví dụ:

```java
List<Integer> numbers = List.of(10, 20, 30);

Map<Boolean, List<Integer>> partition =
        numbers.stream().collect(
                Collectors.partitioningBy(n -> n >= 10));

Map<Boolean, List<Integer>> grouping =
        numbers.stream().collect(
                Collectors.groupingBy(n -> n >= 10));

// partition.get(false) là List rỗng.
// grouping.get(false) là null vì không tồn tại khóa false.
```

Đây là đoạn minh họa trong một phương thức; cần import `java.util.List`, `java.util.Map` và `java.util.stream.Collectors`.

## 2. Chữ ký và cách đọc hai collector

### `partitioningBy` nhận một `Predicate`

Các overload chính:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
    partitioningBy(Predicate<? super T> predicate);

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
    partitioningBy(
        Predicate<? super T> predicate,
        Collector<? super T, A, D> downstream);
```

Chữ ký trên được giản lược để làm rõ kiểu; trong API thật `Collectors` chứa các khai báo generic đầy đủ.

- `Predicate<T>.test(T)` trả **primitive `boolean`**.
- Kết quả `true` đưa phần tử vào nhóm true; kết quả `false` đưa vào nhóm false.
- `partitioningBy` không dùng một “nhãn nhóm” tùy ý; nó cố định **hai nhánh** tương ứng hai giá trị boolean.
- Overload có `downstream` cho phép gom thành danh sách, đếm, tính tổng, lấy min/max, hoặc xử lý riêng từng nhánh.

### `groupingBy` nhận một `Function` phân loại

Một số overload:

```java
static <T, K> Collector<T, ?, Map<K, List<T>>>
    groupingBy(Function<? super T, ? extends K> classifier);

static <T, K, A, D> Collector<T, ?, Map<K, D>>
    groupingBy(
        Function<? super T, ? extends K> classifier,
        Collector<? super T, A, D> downstream);
```

- `Function<T,K>.apply(T)` trả một **khóa kiểu `K`**.
- Nếu viết `order -> order.amount() >= 100`, biểu thức boolean được boxing thành `Boolean` để làm khóa.
- `groupingBy` có thể nhóm theo `String`, `Integer`, enum, record hoặc những khóa hợp lệ khác, chứ không giới hạn ở boolean.
- Map chỉ có nhóm cho các khóa xuất hiện trong dữ liệu đầu vào.

**Với yêu cầu tách hai nhánh đúng/sai, `partitioningBy` diễn đạt chủ đích rõ hơn.** `groupingBy` phù hợp hơn khi bài toán cần phân loại nhiều nhãn hoặc khi việc chỉ có các nhóm thực sự xuất hiện là một phần ý nghĩa dữ liệu.

## 3. Bảng đối chiếu hợp đồng

| Tiêu chí | `partitioningBy(predicate)` | `groupingBy(e -> condition)` |
| --- | --- | --- |
| Mapper được nhận | `Predicate<? super T>` | `Function<? super T, ? extends K>` |
| Kiểu khóa khi chia boolean | `Boolean` | `Boolean` |
| Khóa false có luôn tồn tại? | **Có** | **Không**, chỉ khi có phần tử false |
| Khóa true có luôn tồn tại? | **Có** | **Không**, chỉ khi có phần tử true |
| Nguồn rỗng | Map gồm true và false, mỗi nhóm rỗng | Map rỗng |
| Tất cả phần tử true | `true -> list`; `false -> []` | Chỉ có `true -> list` |
| Tất cả phần tử false | `false -> list`; `true -> []` | Chỉ có `false -> list` |
| Nhiều hơn hai nhóm | Không phù hợp | Phù hợp với classifier nhiều khóa |
| Tham số downstream | Có | Có |
| Có overload chọn map factory? | Không có overload mapFactory của `partitioningBy` | Có `groupingBy(classifier, mapFactory, downstream)` |
| Bảo đảm thứ tự duyệt các khóa Map | Không | Không mặc định |
| Bảo đảm loại cụ thể của Map | Không nên dựa vào | Không nên dựa vào |
| Bảo đảm kết quả luôn mutable | Không có hợp đồng tổng quát | Không có hợp đồng tổng quát |

Vì thứ tự iteration của Map không phải mục tiêu của hai collector, **đừng viết expected stdout dựa trên `System.out.println(map)`** nếu cần kiểm thử độc lập với implementation. Thay vào đó truy cập rõ `get(true)` rồi `get(false)`, hoặc tự chọn cách trình bày có thứ tự xác định.

## 4. Ví dụ Java 17 hoàn chỉnh: chia đơn hàng theo ngưỡng

Chương trình sau minh họa đầy đủ:

1. Phân vùng và nhóm cùng dữ liệu có cả true/false.
2. Đối chiếu dữ liệu **chỉ có true** và dữ liệu **rỗng**.
3. Dùng downstream `counting()` và `summingInt()`.
4. Lấy nhóm false an toàn với `partitioningBy`, và xử lý khóa vắng mặt của `groupingBy`.
5. In kết quả theo cách không phụ thuộc thứ tự Map.

Tạo tệp **`BooleanCollectorsDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BooleanCollectorsDemo {
    record Order(String id, int amount) {}

    static List<String> ids(List<Order> orders) {
        return orders.stream()
                .map(Order::id)
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", 120),
                new Order("A02", 80),
                new Order("A03", 200),
                new Order("A04", 110)
        );

        Predicate<Order> isLarge = order -> order.amount() >= 100;

        Map<Boolean, List<Order>> partition = orders.stream()
                .collect(Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> grouped = orders.stream()
                .collect(Collectors.groupingBy(
                        order -> order.amount() >= 100));

        System.out.println("Partition keys: "
                + partition.containsKey(true) + "/"
                + partition.containsKey(false));
        System.out.println("Grouped keys: "
                + grouped.containsKey(true) + "/"
                + grouped.containsKey(false));
        System.out.println("Partition true: " + ids(partition.get(true)));
        System.out.println("Partition false: " + ids(partition.get(false)));
        System.out.println("Grouped true: " + ids(grouped.get(true)));
        System.out.println("Grouped false: " + ids(grouped.get(false)));

        // Trường hợp toàn bộ phần tử thỏa điều kiện.
        List<Order> onlyLarge = orders.stream()
                .filter(isLarge)
                .toList();

        Map<Boolean, List<Order>> onlyPartition =
                onlyLarge.stream().collect(
                        Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> onlyGrouped =
                onlyLarge.stream().collect(
                        Collectors.groupingBy(isLarge::test));

        System.out.println("Only-large partition false: "
                + ids(onlyPartition.get(false)));
        System.out.println("Only-large group has false: "
                + onlyGrouped.containsKey(false));
        System.out.println("Only-large group false via get: "
                + onlyGrouped.get(false));

        // Trường hợp hoàn toàn không có phần tử.
        Map<Boolean, List<Order>> emptyPartition =
                Stream.<Order>empty().collect(
                        Collectors.partitioningBy(isLarge));

        Map<Boolean, List<Order>> emptyGrouped =
                Stream.<Order>empty().collect(
                        Collectors.groupingBy(isLarge::test));

        System.out.println("Empty partition keys: "
                + emptyPartition.containsKey(true) + "/"
                + emptyPartition.containsKey(false));
        System.out.println("Empty partition sizes: "
                + emptyPartition.get(true).size() + "/"
                + emptyPartition.get(false).size());
        System.out.println("Empty grouped isEmpty: "
                + emptyGrouped.isEmpty());

        // Downstream: số lượng cho từng nhánh, kể cả nhóm thiếu dữ liệu.
        Map<Boolean, Long> counts = onlyLarge.stream()
                .collect(Collectors.partitioningBy(
                        isLarge, Collectors.counting()));

        System.out.println("Counts true/false: "
                + counts.get(true) + "/" + counts.get(false));

        // Downstream: tổng tiền của từng nhánh.
        Map<Boolean, Integer> sums = orders.stream()
                .collect(Collectors.partitioningBy(
                        isLarge, Collectors.summingInt(Order::amount)));

        System.out.println("Sums true/false: "
                + sums.get(true) + "/" + sums.get(false));

        // GroupingBy có thể không có khóa => chọn fallback rõ ràng.
        long missingCount = onlyLarge.stream()
                .collect(Collectors.groupingBy(
                        isLarge::test, Collectors.counting()))
                .getOrDefault(false, 0L);

        System.out.println("Grouped missing count: " + missingCount);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 BooleanCollectorsDemo.java
java BooleanCollectorsDemo
```

**Stdout xác định:**

```text
Partition keys: true/true
Grouped keys: true/true
Partition true: [A01, A03, A04]
Partition false: [A02]
Grouped true: [A01, A03, A04]
Grouped false: [A02]
Only-large partition false: []
Only-large group has false: false
Only-large group false via get: null
Empty partition keys: true/true
Empty partition sizes: 0/0
Empty grouped isEmpty: true
Counts true/false: 3/0
Sums true/false: 430/80
Grouped missing count: 0
```

### Đối chiếu từng dòng

- `orders` có ba đơn đạt `amount >= 100`: A01 (120), A03 (200), A04 (110). Đơn A02 (80) thuộc nhóm false.
- Với dữ liệu có **cả true và false**, cả hai collector đều chứa hai khóa, nên các dòng đầu có kết quả tương đương về nội dung.
- `onlyLarge` chỉ có A01, A03, A04. `partitioningBy` vẫn có khóa false với `List.of()` tương đương về nội dung là danh sách rỗng. `groupingBy` không thấy phần tử false nên **không tạo khóa false**.
- Vì thiếu khóa, `onlyGrouped.get(false)` trả `null`. Đây **không phải một danh sách rỗng**. Nếu gọi `onlyGrouped.get(false).size()` sẽ ném `NullPointerException`.
- Với đầu vào rỗng, `partitioningBy` có hai danh sách rỗng, còn `groupingBy` trả map rỗng.
- `Collectors.counting()` là downstream trả `Long`. Với `onlyLarge`, nhánh true có 3 phần tử, nhánh false có 0.
- `Collectors.summingInt(Order::amount)` tạo tổng primitive int rồi boxing về `Integer` trong map kết quả: true = 120+200+110 = 430, false = 80.
- `groupingBy(..., counting())` với đầu vào chỉ có true **không có khóa false**; `getOrDefault(false,0L)` trả 0 để trình bày một thống kê có giá trị mặc định theo chủ đích caller.

> Ví dụ dùng stream tuần tự có encounter order từ `List`, nên danh sách mã đơn của mỗi nhóm được in theo thứ tự bắt gặp. Không có giả định về thứ tự duyệt khóa của map.

## 5. Trường hợp khiến code thay đổi hành vi

Xét hai dòng:

```java
Map<Boolean, List<Order>> partition =
        orders.stream().collect(
                Collectors.partitioningBy(order -> order.amount() >= 100));

Map<Boolean, List<Order>> grouping =
        orders.stream().collect(
                Collectors.groupingBy(order -> order.amount() >= 100));
```

Ở đây `Order`/`orders` là kiểu/dữ liệu minh họa như chương trình đầy đủ. Nếu có cả hai loại đơn, caller có thể không nhận thấy khác biệt.

Nhưng khi thiếu một loại đơn:

```java
List<Order> small = partition.get(false); // Không null.
List<Order> possiblyNull = grouping.get(false); // Có thể null.
```

Cách gọi `partition.get(false).size()` luôn đọc được số lượng phần tử của nhóm false. Trong khi đó, `grouping.get(false).size()` có thể ném `NullPointerException` nếu không có khóa false.

Giải pháp dành cho `groupingBy` khi đầu ra có thể thiếu khóa:

```java
List<Order> small = grouping.getOrDefault(false, List.of());
System.out.println(small.size());
```

Hoặc kiểm tra `containsKey(false)` nếu yêu cầu nghiệp vụ cần biết rõ **nhóm thực sự xuất hiện** hay chưa.

**Quan trọng:** `getOrDefault` chỉ trả fallback mà caller chỉ định; nó **không tạo thêm khóa false trong map gốc**. Nếu bạn cần cấu trúc kết quả luôn có đúng hai nhóm, `partitioningBy` diễn đạt hợp đồng tốt hơn.

## 6. Tại sao không thể dùng `partitioningBy` cho nhiều hơn hai nhãn?

`partitioningBy` chỉ chia theo một `Predicate<T>` trả `boolean`. Nếu bài toán là phân loại đơn theo:

- `LOW`: dưới 100;
- `MEDIUM`: từ 100 đến dưới 200;
- `HIGH`: từ 200 trở lên;

thì `groupingBy` phù hợp hơn:

```java
enum Band { LOW, MEDIUM, HIGH }

Map<Band, List<Order>> byBand = orders.stream()
        .collect(Collectors.groupingBy(order -> {
            if (order.amount() < 100) return Band.LOW;
            if (order.amount() < 200) return Band.MEDIUM;
            return Band.HIGH;
        }));
```

Đây là **đoạn minh họa** giả định `Order` và `orders` đã khai báo và enum `Band` nằm ở phạm vi hợp lệ. Các khóa enum vẫn chỉ xuất hiện nếu có đơn thuộc nhóm tương ứng. `groupingBy` cho phép tùy biến comparator/map factory trong overload ba tham số, nhưng bản thân nó **không tự thêm mọi giá trị enum** vào map.

Muốn kết quả luôn có nhóm LOW, MEDIUM, HIGH, caller phải quy định và xây dựng đầu ra phù hợp, ví dụ thêm giá trị mặc định cho từng khóa ở một bước rõ ràng.

## 7. Có downstream collector: hành vi của nhóm rỗng

Dạng có downstream của `partitioningBy` rất hữu ích:

```java
Collectors.partitioningBy(predicate, downstream)
```

Với nhóm không có phần tử, collector vẫn tạo **giá trị kết quả của downstream đối với một nhóm rỗng**. Ví dụ:

| Downstream | Kết quả của nhánh trống |
| --- | --- |
| `Collectors.toList()` | Danh sách rỗng |
| `Collectors.counting()` | `0L` |
| `Collectors.summingInt(...)` | `0` |
| `Collectors.averagingInt(...)` | `0.0` |
| `Collectors.maxBy(...)` | `Optional.empty()` |
| `Collectors.mapping(mapper, toList())` | Danh sách rỗng |

Ngược lại, khi dùng `groupingBy(classifier, downstream)` mà khóa tương ứng **không bao giờ xuất hiện**, map thường **không có entry** cho khóa ấy, bất kể downstream có thể tính được một giá trị trên nhóm rỗng hay không.

Ví dụ:

```java
Map<Boolean, Long> counts =
        onlyLarge.stream().collect(
            Collectors.partitioningBy(
                isLarge, Collectors.counting()));

System.out.println(counts.get(false)); // 0
```

Thay `partitioningBy` bằng `groupingBy(isLarge::test, counting())` thì `get(false)` trả `null`, không phải `0L`.

**Không được đánh đồng `0` với “chưa có nhóm”.** Trong một báo cáo, “nhóm này có 0 đơn” và “không hề ghi nhận trạng thái nhóm này” có thể là hai trạng thái cần phân biệt. Chọn collector theo hợp đồng báo cáo.

## 8. Kết hợp downstream `mapping`, `collectingAndThen` và `toSet`

Hai collector đều hỗ trợ downstream để điều khiển kiểu giá trị trong map.

### Chỉ lấy mã đơn thay vì object nguyên vẹn

```java
Map<Boolean, List<String>> idsBySize = orders.stream()
        .collect(Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(Order::id, Collectors.toList())
        ));
```

Kết quả về nội dung: true có A01, A03, A04; false có A02. Với input chỉ có true, false sẽ là `List<String>` rỗng.

### Thu thập về số lượng

```java
Map<Boolean, Long> countBySize = orders.stream()
        .collect(Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.counting()
        ));
```

Bạn không cần tự xây hai biến đếm mutable rồi cập nhật trong `forEach`. Collector điều phối việc tích lũy và kết hợp kết quả.

### Trả list không cho sửa

```java
Map<Boolean, List<String>> immutableGroups =
        orders.stream().collect(
            Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(
                    Order::id,
                    Collectors.collectingAndThen(
                        Collectors.toList(),
                        List::copyOf)
                )
            )
        );
```

`List.copyOf` tạo danh sách không cho sửa cấu trúc và **không chấp nhận phần tử null**. Vì `Order::id` trong ví dụ không null, điều này phù hợp. Tuy nhiên, việc downstream tạo list unmodifiable **không tự bảo đảm bản thân Map có thể/không thể sửa**. Không phụ thuộc implementation cụ thể của collector nếu contract không yêu cầu.

### Muốn loại mã trùng

```java
Map<Boolean, java.util.Set<String>> uniqueIds =
        orders.stream().collect(
            Collectors.partitioningBy(
                order -> order.amount() >= 100,
                Collectors.mapping(
                    Order::id,
                    Collectors.toSet()
                )
            )
        );
```

`Collectors.toSet()` không bảo đảm encounter order của set kết quả; nếu phải hiển thị có thứ tự, hãy chủ động dùng sorted/collection phù hợp. Kể cả với set rỗng, `partitioningBy` vẫn có hai khóa.

## 9. `Predicate` khác `Function<T, Boolean>` ở đâu?

`Predicate<T>` có phương thức:

```java
boolean test(T value);
```

`Function<T, Boolean>` có phương thức:

```java
Boolean apply(T value);
```

Đây là khác biệt thực sự giữa **primitive boolean** và **wrapper Boolean**.

Ví dụ hợp lệ:

```java
Predicate<Order> large = order -> order.amount() >= 100;

Map<Boolean, List<Order>> partition =
        orders.stream().collect(
                Collectors.partitioningBy(large));

Map<Boolean, List<Order>> grouping =
        orders.stream().collect(
                Collectors.groupingBy(large::test));
```

`large::test` là method reference tới phương thức instance `test` của đối tượng `large`; kết quả boolean được boxing phù hợp với khóa `Boolean` của `groupingBy`.

**Nếu classifier `groupingBy` trả `null`:** `groupingBy` không chấp nhận null làm kết quả phân loại và có thể ném `NullPointerException`. Với `partitioningBy`, predicate có kết quả primitive `boolean` nên bản thân `Predicate.test` không có giá trị null hợp lệ. Tuy nhiên, một lambda tự unbox từ `Boolean` nullable vẫn có thể ném NPE:

```java
// Có nguy cơ NPE nếu order.flag() trả Boolean null:
// Predicate<Order> p = order -> order.flag();
```

`Order.flag()` là thuộc tính minh họa giả định; nó không tồn tại trong record `Order` của chương trình chính. Hãy quy định cách xử lý trạng thái **chưa biết**. Nếu thực sự có ba trạng thái true/false/unknown, `partitioningBy` không mô hình hóa đủ; nên dùng enum hoặc kiểu trạng thái khác với `groupingBy`/mô hình tương ứng.

## 10. Khi nào `groupingBy(boolean)` lại phù hợp?

Dù chia đúng hai nhánh thường nên dùng `partitioningBy`, `groupingBy(boolean)` vẫn có những trường hợp hợp lý:

- Bạn đã có một hàm phân loại `Function<T, Boolean>` và cần dùng chung kiến trúc `groupingBy` với những khóa khác.
- **Sự vắng mặt của khóa có ý nghĩa** và caller cố ý muốn biết chỉ những trạng thái đã từng xuất hiện.
- Bạn cần overload của `groupingBy` với một **mapFactory** theo yêu cầu thiết kế riêng.
- Bài toán sẽ sớm mở rộng từ boolean sang enum hoặc nhiều nhóm.

Với overload ba tham số:

```java
Map<Boolean, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(
                order -> order.amount() >= 100,
                java.util.LinkedHashMap::new,
                Collectors.toList()
        ));
```

`LinkedHashMap` giữ thứ tự **chèn khóa khi các nhóm đầu tiên được tạo**, không có nghĩa luôn là false trước true hay ngược lại. Trong pipeline song song, không nên dựa vào thứ tự xuất hiện khóa làm thứ tự nghiệp vụ; muốn cố định true/false hãy in/truy cập chúng bằng khóa cụ thể.

**Không nên chọn collector chỉ vì tên hay tốc độ suy đoán.** Hãy xác định trước output contract và trường hợp nguồn rỗng.

## 11. Nguồn rỗng và ngữ nghĩa báo cáo

Nguồn rỗng là một tình huống dễ làm lộ khác biệt mà code happy-path không thể hiện.

Với `partitioningBy`:

```java
Map<Boolean, List<Integer>> parts =
        Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n >= 0));

System.out.println(parts.containsKey(true));  // true
System.out.println(parts.containsKey(false)); // true
System.out.println(parts.get(true).size());   // 0
System.out.println(parts.get(false).size());  // 0
```

Với `groupingBy`:

```java
Map<Boolean, List<Integer>> groups =
        Stream.<Integer>empty()
                .collect(Collectors.groupingBy(n -> n >= 0));

System.out.println(groups.isEmpty());         // true
System.out.println(groups.get(false));        // null
```

Do đó:

- Với dashboard cần luôn hiển thị “Hợp lệ: 0, Không hợp lệ: 0”, `partitioningBy` rất tự nhiên.
- Với danh mục chỉ hiển thị các nhóm đã có dữ liệu, `groupingBy` cho map chỉ chứa các khóa đã gặp.
- Với API cần phân biệt “không có bản ghi” và “không có nhãn nhóm”, nên thiết kế một cấu trúc Result/DTO tường minh thay vì chỉ suy luận từ map.

## 12. Đọc kết quả an toàn: `get`, `getOrDefault`, `containsKey`

`partitioningBy` bảo đảm có hai entry, nên `get(true)`/`get(false)` cho kết quả được định nghĩa bởi downstream. Với downstream mặc định, đó là `List<T>` (có thể rỗng).

`groupingBy` không bảo đảm cả hai khóa hiện diện, vì vậy:

```java
List<Order> trueItems =
        grouped.getOrDefault(true, List.of());

List<Order> falseItems =
        grouped.getOrDefault(false, List.of());
```

Nếu caller cần phân biệt “không có khóa” với “khóa có danh sách rỗng”, kiểm tra `containsKey` trước. Đừng dùng `grouped.get(false) == null` để thay thế mọi kiểm tra trong API có thể cho phép giá trị map null do nguồn khác cung cấp; với kết quả mặc định của `groupingBy`, vắng khóa là trường hợp chính, nhưng thiết kế API tổng quát vẫn nên định nghĩa hợp đồng.

`getOrDefault` không thêm entry vào map. Nếu code sau đó làm `grouped.put(false, new ArrayList<>())`, nó đang **mutate map kết quả** và cần biết rõ tính mutable được bảo đảm hay không; thông thường nên tạo một map/DTO đầu ra của riêng ứng dụng với hai khóa đã khởi tạo khi cần cấu trúc ổn định.

### Đừng viết biểu thức có nguy cơ NPE

```java
// Có thể lỗi nếu grouped thiếu khóa false:
// int count = grouped.get(false).size();

// Hợp lệ với dữ liệu nhóm có thể thiếu khóa:
int count = grouped.getOrDefault(false, List.of()).size();
```

Phần code minh họa giả định `grouped` có kiểu `Map<Boolean,List<Order>>` và `Order` đã khai báo.

## 13. Thứ tự các phần tử, mutable result và dữ liệu đồng thời

### Thứ tự phần tử trong mỗi nhóm

Với `List` có encounter order và pipeline tuần tự, downstream mặc định của hai collector là danh sách chứa những phần tử thuộc nhóm theo thứ tự gặp. Ví dụ A01, A03, A04 trong nhánh true.

Trong pipeline song song có encounter order, collector tương ứng vẫn phải đáp ứng semantics thứ tự của downstream khi được áp dụng; **không nên suy ra thứ tự các thread chạy predicate** từ thứ tự phần tử kết quả. Predicate nên **không can thiệp trạng thái nguồn hoặc dùng shared mutable state**.

### Không phụ thuộc map implementation

Các collector không cam kết một lớp map cụ thể để caller dựa vào tên class hoặc thứ tự iteration. Không viết unit test so sánh `map.toString()` theo một thứ tự khóa cứng. Kiểm tra `map.get(true)`/`map.get(false)` hoặc so sánh các giá trị từng nhánh.

### Song song hóa có được không?

Bạn có thể gọi:

```java
Map<Boolean, List<Order>> partition =
        orders.parallelStream()
                .collect(Collectors.partitioningBy(
                        order -> order.amount() >= 100));
```

`collect` quản lý việc tích lũy và kết hợp kết quả theo collector. Không cần tự khai báo hai `ArrayList` dùng chung rồi `parallelStream().forEach(...)` gọi `add` vào chúng, vì đó là nguy cơ data race.

**Lưu ý hiệu năng:** `partitioningBy` và `groupingBy` có thể khác nhau về overhead/đặc điểm kết hợp, nhưng không có quy tắc “partitioningBy luôn nhanh hơn” cho mọi dữ liệu/JDK. Chọn theo output contract trước; benchmark đại diện nếu hiệu năng thực sự quan trọng.

## 14. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Nghĩ `partitioningBy` chỉ tạo nhóm đã có phần tử | Hợp đồng luôn có true và false | Xử lý hai nhóm, cho phép danh sách rỗng |
| Nghĩ `groupingBy(boolean)` cũng luôn có hai khóa | Nó chỉ tạo khóa khi có phần tử thuộc nhóm | `getOrDefault`/`containsKey` hoặc chọn `partitioningBy` |
| Gọi `grouped.get(false).size()` vô điều kiện | Có thể NPE khi thiếu khóa | `getOrDefault(false,List.of()).size()` |
| Nghĩ nguồn rỗng trả kết quả giống nhau | Partition hai nhóm rỗng; grouping map rỗng | Test edge case không dữ liệu |
| In `map.toString()` và assert thứ tự khóa | Không có contract thứ tự khóa phù hợp | Truy cập từng khóa rõ ràng |
| Dùng `partitioningBy` để tạo 3 nhãn | Predicate chỉ có true/false | `groupingBy` với enum/nhãn |
| Dùng `Boolean` nullable rồi auto-unbox | Có thể NPE | Định nghĩa trạng thái unknown |
| Phân loại bằng `groupingBy` trả null key | Không chấp nhận classifier null | Validate/chuẩn hóa hoặc dùng kiểu nhãn hợp lệ |
| Nghĩ `counting` trên nhóm vắng mặt luôn là 0 entry | Grouping không tạo entry cho nhánh vắng mặt | `getOrDefault(false,0L)` |
| Dùng `forEach` sửa hai `ArrayList` ngoài | Side effect khó kiểm soát, nguy hiểm khi parallel | Collector tích lũy |
| Xem `Map<Boolean,...>` là định nghĩa đủ cho mọi trạng thái nghiệp vụ | Có thể có trạng thái lỗi/chưa xác định | Enum/Result/DTO rõ ràng |
| Dựa vào khả năng mutate map/list collector | Không nên dựa implementation | Tạo output riêng nếu cần chỉnh |

## 15. Bài tập thực hành

1. Với các số `[1,2,3,4]`, dùng `partitioningBy(n -> n % 2 == 0)`. Dự đoán hai danh sách true/false. Đáp án: true `[2,4]`; false `[1,3]`.
2. Chạy cùng danh sách với `groupingBy(n -> n % 2 == 0)`. Vì có đủ chẵn/lẻ, kết quả về nội dung có gì giống và khác `partitioningBy`?
3. Với `List.of(2,4,6)`, kiểm tra `partition.get(false)` và `grouped.get(false)`. Tại sao một giá trị là list rỗng còn một giá trị là null?
4. Thu thập `Stream.<Integer>empty()` qua hai collector. Xác nhận `partitioningBy` có hai khóa còn `groupingBy` không có khóa.
5. Dùng `partitioningBy(n -> n > 10, counting())` trên `[1,2,3]`. Dự đoán `true=0L`, `false=3L`.
6. Dùng `groupingBy(n -> n > 10, counting())` trên cùng dữ liệu. Tại sao `get(true)` trả null thay vì 0?
7. Thay `Collectors.toList()` bằng `Collectors.mapping(Order::id, toList())` để nhóm chỉ chứa mã đơn. Xác định kiểu `Map<Boolean,List<String>>`.
8. Dùng `summingInt(Order::amount)` để tính tiền theo nhánh. Với dữ liệu `BooleanCollectorsDemo`, giải thích kết quả true=430, false=80.
9. Thiết kế phân loại ba nhóm `LOW/MEDIUM/HIGH` bằng enum và `groupingBy`. Vì sao `partitioningBy` không biểu diễn được cả ba nhãn?
10. Viết unit test kiểm tra hai khóa của `partitioningBy`, bao gồm khi dữ liệu rỗng; viết test cho `groupingBy` nơi chỉ có một nhãn.
11. Viết code nhận `Map<Boolean, List<Order>>` từ `groupingBy` rồi dùng `getOrDefault` để trả thống kê không NPE. Nêu rõ việc `getOrDefault` không thêm entry.
12. So sánh lựa chọn `partitioningBy` và `groupingBy` khi chuẩn bị response cho dashboard phải luôn có hai thẻ “đạt”/“không đạt”.
13. Tạo `Predicate<Order> large = order -> order.amount() >= 100` rồi dùng cả `partitioningBy(large)` và `groupingBy(large::test)`. Giải thích `boolean` so với `Boolean`.
14. Chạy collector trên parallel stream và dùng kết quả theo từng khóa; vì sao không được dùng thứ tự các lần gọi predicate hoặc thứ tự iteration của Map làm tiêu chí kiểm thử?

## 16. Checklist khi chọn collector

- Bài toán có đúng **hai nhánh boolean** hay là phân loại nhiều nhãn?
- Có cần map **luôn tồn tại khóa true và false**, kể cả khi rỗng không?
- Caller có dùng `get(false)` rồi gọi `size`/`stream` ngay không?
- Nhánh không có dữ liệu nên biểu diễn là **một nhóm rỗng** hay **khóa vắng mặt**?
- Downstream nên thu thập list, count, sum, average, min/max hay mã định danh?
- Với nhóm rỗng, downstream có trả giá trị mặc định đúng ngữ nghĩa không?
- Predicate/classifier có thuần, nhất quán và xử lý dữ liệu null đúng hợp đồng không?
- Có đang suy diễn thứ tự key hoặc tính mutable của map theo implementation hiện tại không?
- Có thử dữ liệu chỉ true, chỉ false, cả hai, và nguồn rỗng chưa?
- Nếu dùng parallel stream, có giữ side effect bên ngoài collector và dữ liệu mutable chung ở mức tối thiểu không?

**Kết luận:** `Collectors.partitioningBy(predicate)` là lựa chọn trực tiếp cho **hai nhánh đúng/sai và bảo đảm có cả hai khóa Boolean**, kể cả với nguồn rỗng. `Collectors.groupingBy(element -> booleanExpression)` có thể cho dữ liệu giống nhau khi xuất hiện cả hai loại, nhưng **chỉ giữ những khóa thực sự có phần tử**. Khác biệt nhỏ về tập khóa này quyết định an toàn của `get(...)`, giá trị thống kê mặc định và ý nghĩa của kết quả khi dữ liệu thiếu.
