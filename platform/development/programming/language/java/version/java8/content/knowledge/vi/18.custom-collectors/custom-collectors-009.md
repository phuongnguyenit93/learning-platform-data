# Khi nên tái sử dụng collector chuẩn thay vì tự viết `Collector`

Trong Java Stream API, **collector** xác định cách gom các phần tử của một stream thành một kết quả: danh sách, tập hợp, bản đồ, chuỗi, thống kê hoặc cấu trúc tổng hợp khác. `Collectors` đã cung cấp các collector chuẩn cùng những **bộ kết hợp** để giải quyết phần lớn nhu cầu thực tế. Khi thiết kế một `Collector` tùy biến, câu hỏi cần trả lời đầu tiên là: **có thể mô tả đúng yêu cầu bằng một hoặc vài collector chuẩn hay không?**

Thông thường nên **tái sử dụng collector chuẩn nếu hành vi được API hỗ trợ và hợp đồng về thứ tự, kiểu kết quả, dữ liệu rỗng, tính duy nhất, khả năng sửa và song song đều phù hợp**. Chỉ cân nhắc `Collector.of(...)` hoặc cài đặt `Collector` riêng khi có một quy tắc tích lũy đặc thù mà các phép kết hợp chuẩn không diễn đạt đúng hoặc tạo chi phí không chấp nhận được. Đây là hướng tiếp cận áp dụng được từ Java 8 đến các JDK hiện hành.

## 1. Tại sao ưu tiên collector chuẩn?

`Stream.collect(collector)` là một **terminal operation**. Một collector theo hợp đồng API có những thành phần sau:

| Thành phần | Vai trò |
| --- | --- |
| `supplier()` | Tạo vùng tích lũy mới, độc lập |
| `accumulator()` | Bổ sung một phần tử vào vùng tích lũy |
| `combiner()` | Gộp hai kết quả tích lũy, đặc biệt quan trọng khi xử lý song song |
| `finisher()` | Chuyển vùng tích lũy thành kết quả cuối cùng |
| `characteristics()` | Khai báo những đặc tính thật sự được bảo đảm như `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` |

Khi tự viết collector, bạn phải đảm bảo các luật **identity**, **associativity**, tính độc lập của vùng tích lũy và kết quả tương đương giữa cách chạy tuần tự với cách chia rồi ghép. Collector chuẩn giúp giảm số lượng quy tắc phải tự chứng minh và bảo trì.

**Ví dụ:** nếu chỉ cần ghép tên sản phẩm với dấu phân cách, `Collectors.joining(", ")` đã xử lý việc tích lũy, dấu phân cách, và ghép kết quả bộ phận. Tự viết `Collector.of(StringBuilder::new, ...)` chỉ để làm việc này tăng mã và nguy cơ lỗi ở `combiner` mà không tạo giá trị.

```java
List<String> names = Arrays.asList("Book", "Pen", "Bag");
String text = names.stream().collect(Collectors.joining(", "));
// "Book, Pen, Bag"
```

Đoạn mã trên là ví dụ minh họa, giả định đã `import java.util.*;` và `import java.util.stream.*;`.

## 2. Sơ đồ quyết định trước khi tạo collector tùy biến

Hãy trả lời lần lượt:

1. **Chỉ cần kết quả terminal đơn giản?** Đếm, kiểm tra điều kiện, tìm giá trị nhỏ/lớn có `count()`, `anyMatch()`, `allMatch()`, `min()` và `max()` trên stream. Không cần bọc tất cả bài toán vào collector.
2. **Cần một collection hoặc map?** Chọn `toList()`, `toSet()`, `toCollection(factory)` hoặc `toMap(...)`.
3. **Cần phân nhóm hoặc chia làm hai nhánh theo điều kiện?** Chọn `groupingBy(...)` hoặc `partitioningBy(...)`, thêm downstream collector nếu cần.
4. **Cần tính giá trị tổng hợp?** Xem `counting()`, `summingInt/Long/Double()`, `averagingInt/Long/Double()`, `summarizingInt/Long/Double()`, `minBy()`, `maxBy()`.
5. **Cần biến đổi giá trị trước khi gom, hoặc hậu xử lý kết quả?** Xem `mapping(...)` và `collectingAndThen(...)`. Với Java 9+, còn có `filtering(...)` và `flatMapping(...)`; Java 12+ có `teeing(...)`.
6. **Các lựa chọn trên không bảo đảm đúng hợp đồng đầu ra hoặc phải tạo dữ liệu trung gian quá lớn?** Lúc này mới thiết kế collector tùy biến, xác định rõ vùng tích lũy, cách ghép, đặc tính song song và phép thử tương đương.

**Không nhất thiết phải dùng `collect()` cho mọi phép tính.** Chẳng hạn:

```java
long count = orders.stream().filter(o -> o.getAmount() >= 100).count();
```

Ở đây `count()` là terminal operation đơn giản và rõ ý định nhất. Biến `orders` và `Order` sẽ được định nghĩa ở ví dụ hoàn chỉnh cuối bài.

## 3. Chọn các collector chuẩn theo loại đầu ra

| Kết quả mong muốn | Nên bắt đầu với | Ghi chú về hợp đồng |
| --- | --- | --- |
| `List<T>` | `Collectors.toList()` | Không cam kết implementation hoặc khả năng sửa |
| `ArrayList<T>` cụ thể | `Collectors.toCollection(ArrayList::new)` | Chọn rõ kiểu collection có thể sửa |
| `Set<T>` | `Collectors.toSet()` | Không cam kết thứ tự lặp hoặc implementation |
| Set giữ thứ tự xuất hiện | `toCollection(LinkedHashSet::new)` | Với nguồn có encounter order, nhất là stream tuần tự |
| Set sắp xếp | `toCollection(TreeSet::new)` | Cực kỳ chú ý comparator quyết định cả thứ tự và tính trùng |
| `Map<K,V>` | `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` | Quy định rõ xử lý khóa trùng và thứ tự khóa |
| Nhiều phần tử thuộc một khóa | `groupingBy(classifier, downstream)` | Chọn collector để tạo giá trị từng nhóm |
| Hai nhóm theo `boolean` | `partitioningBy(predicate, downstream)` | Có cả hai khóa `true` và `false`, kể cả nhóm rỗng |
| Chuỗi ghép từ phần tử văn bản | `joining(delimiter)` | Không cần tự quản lý `StringBuilder` |
| Đếm / tổng / trung bình theo nhóm | `counting`, `summing...`, `averaging...` | Áp dụng như downstream của `groupingBy` |
| Count/min/max/sum/average của thuộc tính số | `summarizingInt/Long/Double` | Một collector tích lũy thống kê |
| Cực trị của đối tượng | `minBy(comparator)`, `maxBy(comparator)` | Trả `Optional<T>` |
| Biến phần tử thành thuộc tính trước khi gom | `mapping(mapper, downstream)` | Kết hợp không cần tự viết collector |
| Chuyển kết quả collector cuối cùng | `collectingAndThen(downstream, finisher)` | Finisher chạy sau quá trình gom |

Các tên ở bảng là API đang có trong JDK hiện đại. Cần chú ý phạm vi **Java 8**: `Collectors.toList`, `toCollection`, `toMap`, `groupingBy`, `partitioningBy`, `mapping`, `collectingAndThen`, `summarizingInt` đều có từ Java 8. Những API có từ phiên bản mới hơn được đánh dấu riêng bên dưới.

### Độ rõ ràng của hợp đồng kết quả

`Collectors.toList()` không cam kết danh sách trả về là `ArrayList` hoặc có thể chỉnh sửa. Nếu kết quả phải là `ArrayList` có thể sửa, hãy nêu yêu cầu bằng `toCollection(ArrayList::new)`. Nếu cần danh sách **không chỉnh sửa được**, Java 10+ có `Collectors.toUnmodifiableList()`, và Java 16+ có `Stream.toList()`; `Stream.toList()` là **terminal operation của stream**, không phải một collector truyền vào `collect(...)`.

`Collectors.toSet()` không cam kết thứ tự phần tử. `HashSet`, `LinkedHashSet` và `TreeSet` có hợp đồng khác nhau; sử dụng `toCollection(...)` khi thứ tự hoặc kiểu cụ thể là một phần của yêu cầu. Tương tự, với `groupingBy` hoặc `toMap`, đừng giả định `Map` mặc định sẽ có thứ tự ổn định nếu API không cam kết; cung cấp `LinkedHashMap::new` hay `TreeMap::new` khi cần.

## 4. Biến đổi phần tử trước khi gom: dùng `map` hoặc `mapping`

Nếu toàn bộ stream cần biến đổi trước khi gom, `map(...)` thường dễ đọc nhất:

```java
List<String> items = orders.stream()
    .map(Order::getItem)
    .collect(Collectors.toList());
```

Trong **phân nhóm**, `mapping(...)` đặc biệt hữu ích vì mỗi nhóm vẫn được xác định từ đối tượng `Order` ban đầu, nhưng dữ liệu được lưu là thuộc tính `item`:

```java
Map<String, List<String>> itemsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        LinkedHashMap::new,
        Collectors.mapping(Order::getItem, Collectors.toList())
    ));
```

Nếu cần loại tên sản phẩm trùng mà vẫn giữ encounter order trong nhóm:

```java
Map<String, LinkedHashSet<String>> uniqueItems = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        LinkedHashMap::new,
        Collectors.mapping(
            Order::getItem,
            Collectors.toCollection(LinkedHashSet::new)
        )
    ));
```

Không cần tự viết một collector có `HashMap`, `Set` và các hàm bổ sung phần tử. `groupingBy` đảm nhận phân nhóm, `mapping` biến đổi kiểu, còn `toCollection` quyết định cấu trúc lưu trữ.

**Tách hai quyết định:** `LinkedHashMap::new` xác định thứ tự **khóa nhóm**; `LinkedHashSet::new` xác định thứ tự và quy tắc trùng của **tên mặt hàng trong mỗi nhóm**. Một collector tùy biến dài hơn chưa chắc mang lại ngữ nghĩa tốt hơn cách ghép này.

## 5. `groupingBy`, `partitioningBy` và tổng hợp theo nhóm

Khi một đối tượng phải thuộc nhóm theo khóa như khu vực, phòng ban, ngày tháng, dùng `groupingBy`. Chẳng hạn:

```java
Map<String, Integer> totalByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        LinkedHashMap::new,
        Collectors.summingInt(Order::getAmount)
    ));
```

Kết quả là `Map<String,Integer>`, **không phải `Map<String,List<Order>>`**: downstream `summingInt` đã tính tổng số tiền của từng nhóm.

Nếu chỉ phân thành hai nhóm theo đúng/sai của điều kiện, `partitioningBy` nói rõ mục đích hơn việc tạo khóa boolean trong `groupingBy`:

```java
Map<Boolean, Long> orderCounts = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.getAmount() >= 100,
        Collectors.counting()
    ));
```

Hai khóa `true` và `false` luôn có trong map của `partitioningBy`. Giá trị của một nhánh có thể bằng 0 khi không có phần tử. Không nên tự viết collector để duy trì hai bộ đếm với mục đích này.

### Khi cần nhiều thống kê trên một thuộc tính

`Collectors.summarizingInt(Order::getAmount)` trả về `IntSummaryStatistics`, gồm `count`, `sum`, `min`, `max` và `average`:

```java
IntSummaryStatistics stats = orders.stream()
    .collect(Collectors.summarizingInt(Order::getAmount));

if (stats.getCount() > 0) {
    System.out.println(stats.getMin());
    System.out.println(stats.getMax());
}
```

Đối với nguồn rỗng, `getCount() == 0` nhưng `getMin()`/`getMax()` là các giá trị sentinel `Integer.MAX_VALUE`/`Integer.MIN_VALUE`; vì thế phải kiểm tra count trước khi diễn giải extrema. `summarizingInt` giữ lại các **giá trị thống kê**, không giữ đối tượng `Order` có giá cực trị. Nếu cần **đơn hàng** lớn nhất, xem `maxBy(Comparator.comparingInt(Order::getAmount))`.

Giá trị tổng kiểu `int` có thể tràn khi tổng rất lớn; hãy cân nhắc `summingLong(...)` hoặc kiểu số phù hợp khi nghiệp vụ đòi độ chính xác và miền giá trị lớn. Đối với tiền tệ, không tự động coi `double` là lựa chọn đúng cho các yêu cầu chính xác thập phân; dùng kiểu tiền/`BigDecimal` và quy tắc làm tròn được thiết kế rõ.

## 6. `toMap`: tái sử dụng collector chuẩn nhưng phải định nghĩa khóa trùng

Một lỗi phổ biến là dùng `Collectors.toMap(keyMapper, valueMapper)` khi nhiều phần tử có cùng khóa. Overload hai tham số ném `IllegalStateException` nếu có khóa trùng. Thay vì viết collector riêng, hãy cung cấp **merge function**:

```java
Map<String, Integer> highestAmountByItem = orders.stream()
    .collect(Collectors.toMap(
        Order::getItem,
        Order::getAmount,
        Integer::max,
        TreeMap::new
    ));
```

Trong ví dụ, mặt hàng `Pen` xuất hiện hai lần với số tiền 40 và 90. `Integer::max` giữ 90. `TreeMap::new` sắp tên sản phẩm theo khóa; không nên suy diễn rằng phiên bản `toMap` mặc định luôn có thứ tự nào đó.

Một `mergeFunction` có thể là cộng, lấy lớn nhất, chọn bản ghi theo ưu tiên hoặc hợp nhất các giá trị, nhưng phải **đúng quy tắc nghiệp vụ**. Với việc chạy song song, kết quả cần ổn định theo cách chia và gộp; hàm kết hợp nên có tính kết hợp (associative). Những lựa chọn "lấy bản ghi xuất hiện cuối" phụ thuộc thứ tự xử lý phải được kiểm chứng riêng, nhất là với stream không có encounter order.

`toMap` sử dụng quy tắc `Map.merge` cho xử lý trùng và không thích hợp để coi giá trị `null` từ `valueMapper` là kết quả gom hợp lệ; tránh mapper trả về `null`. Khi cần lưu **nhiều giá trị** cho một khóa, `groupingBy(key, mapping(..., toList()))` thường đúng mục đích hơn cố ép các `List` vào merge function.

## 7. Kết hợp collector chuẩn thay cho tự viết finisher

`Collectors.collectingAndThen(downstream, finisher)` cho phép biến đổi **kết quả cuối cùng** sau khi đã gom. Ví dụ, cần danh sách không cho sửa bằng API Java 8:

```java
List<String> readOnlyItems = orders.stream()
    .collect(Collectors.mapping(
        Order::getItem,
        Collectors.collectingAndThen(
            Collectors.toList(),
            Collections::unmodifiableList
        )
    ));
```

`Collections.unmodifiableList(...)` trả về một **view không cho chỉnh sửa qua view** của danh sách đã gom. Trong ví dụ, danh sách trung gian chỉ do collector tạo và không bị đưa ra ngoài, nên đây là cách hợp lý để trả kết quả chỉ đọc. Tuy vậy, các **đối tượng phần tử có thể thay đổi** vẫn không được biến thành bất biến chỉ vì được đưa vào list không sửa được.

Java 10+ có collector chuyên dụng `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()`, `toUnmodifiableMap(...)` nếu đúng hợp đồng và đầu vào không chứa `null`. Java 16+ có `orders.stream().map(...).toList()` trả `List` không sửa được. Hãy chọn API theo **phiên bản JDK mục tiêu**, không giả định tất cả API mới đều đã có trong Java 8.

### Những combinator xuất hiện sau Java 8 nhưng vẫn dùng hiện nay

| API | Bắt đầu từ | Khi hữu ích |
| --- | --- | --- |
| `Collectors.filtering(predicate, downstream)` | Java 9 | Chỉ giữ phần tử thỏa điều kiện **bên trong từng nhóm**, vẫn giữ khóa nhóm đã gặp |
| `Collectors.flatMapping(mapper, downstream)` | Java 9 | Mỗi đối tượng đầu vào ánh xạ ra 0..n phần tử cho downstream |
| `Collectors.toUnmodifiableList/Set/Map` | Java 10 | Cần collection/map không chỉnh sửa được và xử lý `null` theo hợp đồng API |
| `Collectors.teeing(first, second, merger)` | Java 12 | Cho cùng đầu vào đi qua **hai collector** rồi ghép hai kết quả |
| `Stream.toList()` | Java 16 | Tạo `List` không chỉnh sửa được trực tiếp từ stream; đây không phải `Collector` |

Điểm quan trọng với `filtering`: hai pipeline sau **không hoàn toàn tương đương** khi một nhóm không có phần tử đạt điều kiện:

```java
// Java 8+: nhóm không đạt điều kiện biến mất.
Map<String, Long> onlyLargeRegions = orders.stream()
    .filter(order -> order.getAmount() >= 100)
    .collect(Collectors.groupingBy(
        Order::getRegion, LinkedHashMap::new, Collectors.counting()));

// Java 9+: nhóm đã gặp vẫn có thể tồn tại với count = 0.
Map<String, Long> largeInEachRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion, LinkedHashMap::new,
        Collectors.filtering(
            order -> order.getAmount() >= 100,
            Collectors.counting())));
```

Với dữ liệu ở mục 9: `onlyLargeRegions` không có khóa `south`; `largeInEachRegion` có `south=0`. Đây là khác biệt nghiệp vụ thật sự; chỉ chọn downstream filtering khi cần giữ các nhóm có đầu vào nhưng không có phần tử thỏa điều kiện.

Nếu chỉ cần count/sum/min/max trên một giá trị `int`, `summarizingInt` thường rõ hơn `teeing` hoặc viết collector riêng. `teeing` hữu ích khi hai kết quả có **kiểu/hợp đồng khác nhau** và cần gộp trong một lần gom, chẳng hạn vừa thu một danh sách chọn lọc vừa tính chỉ số tổng hợp, nhưng phải cân nhắc bộ nhớ của mỗi downstream.

## 8. Khi nào **thật sự** nên viết collector tùy biến?

Có thể cân nhắc `Collector.of(...)` hoặc cài đặt `Collector<T,A,R>` nếu **đồng thời** thỏa các điều kiện:

1. Yêu cầu kết quả có quy tắc tích lũy đặc thù **không diễn đạt chính xác** bằng collector chuẩn kết hợp cùng `map`, `filter`, `flatMap` hoặc `collectingAndThen`.
2. Phương án dùng collector chuẩn phải tạo bộ sưu tập trung gian không chấp nhận được, hoặc phải thực hiện nhiều lượt xử lý **đã được đo** là chi phí quan trọng.
3. Có thể định nghĩa một **vùng tích lũy riêng** và cách gộp hai vùng tích lũy **đúng với mọi cách chia stream**.
4. Nhóm phát triển sẽ kiểm thử trường hợp rỗng, một phần tử, trùng lặp, thứ tự, dữ liệu bất thường và tương đương giữa sequential/parallel nếu có hỗ trợ song song.

Ví dụ có thể cần custom: một thuật toán thống kê theo cửa sổ có trạng thái chuyên biệt, một cấu trúc kết quả nghiệp vụ nhiều trường có quy tắc cập nhật kết hợp chặt chẽ, hoặc một bộ tích lũy đặc thù có giới hạn bộ nhớ được xác định nghiêm ngặt. Nhưng **"muốn trả về một DTO có count, sum, min và max" chưa đủ để kết luận phải viết collector riêng**: có thể gom bằng `summarizingInt` rồi ánh xạ sang DTO ở bước kết thúc.

### Chi phí ẩn khi tự viết `Collector.of`

Hình thức có finisher:

```java
Collector.of(
    supplier,    // tạo một vùng tích lũy mới
    accumulator, // thêm một phần tử
    combiner,    // gộp hai vùng tích lũy
    finisher     // biến vùng tích lũy thành kết quả
)
```

Đây là **khung chữ ký mô tả**, không phải chương trình độc lập; các tên biến trên cần là hàm/lambda có kiểu phù hợp.

Nếu muốn dùng mutable `ArrayList` với `Stream.reduce(identity, accumulator, combiner)` rồi sửa danh sách trong accumulator, hãy thận trọng: `reduce` kỳ vọng phép giảm kết hợp, và **identity dùng chung bị sửa** có thể làm kết quả sai khi xử lý song song. Dùng `collect(Collectors.toCollection(ArrayList::new))` cho bài toán thu thập danh sách.

**Các luật không được bỏ qua khi thiết kế custom collector:**

- `supplier` phải tạo vùng tích lũy **mới, độc lập**. Không giữ danh sách/map dùng chung ở bên ngoài.
- `combiner` phải duy trì kết quả tương đương khi xử lý một lượt hoặc chia dữ liệu rồi gộp. Phép ghép cần tuân thủ luật identity và associativity theo hợp đồng `Collector`.
- `IDENTITY_FINISH` chỉ đúng khi vùng tích lũy trung gian **chính là kết quả cuối**, không có biến đổi kiểu/giá trị ở finisher.
- `CONCURRENT` chỉ được khai báo nếu accumulator có thể được gọi đồng thời trên **cùng** một vùng tích lũy một cách an toàn.
- `UNORDERED` chỉ đúng nếu kết quả không phụ thuộc encounter order; đừng tự gắn cờ này để mong pipeline nhanh hơn.
- Collector không concurrent vẫn có thể dùng với parallel stream nhờ mỗi phần kết quả được tích lũy riêng rồi **ghép bằng combiner**; không cần và không nên tự chia sẻ vùng tích lũy không đồng bộ giữa các luồng.

Không nên tạo collector custom chỉ để thay một dòng `summingInt`, `joining`, `toMap` hay `groupingBy`. Nếu không có lợi ích được đo hoặc yêu cầu chức năng cụ thể, bản triển khai chuẩn giúp code dễ đọc, review và nâng cấp JDK hơn.

## 9. Chương trình Java hoàn chỉnh: giải một bài toán bằng collector chuẩn

Tạo file **`StandardCollectorsReuseDemo.java`** với nội dung dưới đây. Chương trình sử dụng **API có từ Java 8**, không cần thư viện ngoài; biên dịch và chạy được trên JDK 17+.

```java
import java.util.*;
import java.util.stream.*;

public class StandardCollectorsReuseDemo {
    static final class Order {
        private final String region;
        private final String item;
        private final int amount;

        Order(String region, String item, int amount) {
            this.region = region;
            this.item = item;
            this.amount = amount;
        }

        String getRegion() {
            return region;
        }

        String getItem() {
            return item;
        }

        int getAmount() {
            return amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("north", "Book", 150),
            new Order("south", "Pen", 40),
            new Order("north", "Notebook", 70),
            new Order("south", "Pen", 90),
            new Order("west", "Bag", 200));

        Map<String, Long> counts = orders.stream().collect(
            Collectors.groupingBy(Order::getRegion,
                LinkedHashMap::new, Collectors.counting()));

        Map<String, Integer> totals = orders.stream().collect(
            Collectors.groupingBy(Order::getRegion,
                LinkedHashMap::new,
                Collectors.summingInt(Order::getAmount)));

        Map<String, LinkedHashSet<String>> uniqueItems = orders.stream()
            .collect(Collectors.groupingBy(
                Order::getRegion,
                LinkedHashMap::new,
                Collectors.mapping(Order::getItem,
                    Collectors.toCollection(LinkedHashSet::new))));

        Map<String, Integer> maxPriceByItem = orders.stream().collect(
            Collectors.toMap(Order::getItem, Order::getAmount,
                Integer::max, TreeMap::new));

        Map<Boolean, Long> large = orders.stream().collect(
            Collectors.partitioningBy(o -> o.getAmount() >= 100,
                Collectors.counting()));

        IntSummaryStatistics stats = orders.stream().collect(
            Collectors.summarizingInt(Order::getAmount));

        String joined = orders.stream().map(Order::getItem)
            .collect(Collectors.joining(" | "));

        List<String> readOnlyItems = orders.stream().collect(
            Collectors.mapping(Order::getItem,
                Collectors.collectingAndThen(
                    Collectors.toList(), Collections::unmodifiableList)));

        System.out.println("counts: " + counts);
        System.out.println("totals: " + totals);
        System.out.println("unique items: " + uniqueItems);
        System.out.println("max by item: " + maxPriceByItem);
        System.out.println("large/small: " +
            large.get(true) + "/" + large.get(false));
        System.out.println("count/min/max: " +
            stats.getCount() + "/" + stats.getMin() + "/" + stats.getMax());
        System.out.println("joined: " + joined);
        System.out.println("read-only items: " + readOnlyItems);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StandardCollectorsReuseDemo.java
java StandardCollectorsReuseDemo
```

Kết quả chuẩn:

```text
counts: {north=2, south=2, west=1}
totals: {north=220, south=130, west=200}
unique items: {north=[Book, Notebook], south=[Pen], west=[Bag]}
max by item: {Bag=200, Book=150, Notebook=70, Pen=90}
large/small: 2/3
count/min/max: 5/40/200
joined: Book | Pen | Notebook | Pen | Bag
read-only items: [Book, Pen, Notebook, Pen, Bag]
```

Vì sao chương trình đúng mà không cần tự viết `Collector.of`?

- `groupingBy + counting` đếm số đơn hàng mỗi vùng; `LinkedHashMap` giữ thứ tự khóa `north` → `south` → `west` của nguồn `List` khi xử lý tuần tự.
- `groupingBy + summingInt` tính tổng: `north=150+70=220`, `south=40+90=130`, `west=200`.
- `groupingBy + mapping + toCollection(LinkedHashSet::new)` biến nhóm đơn hàng thành tập tên sản phẩm không trùng và giữ thứ tự gặp; tên `Pen` xuất hiện hai lần nhưng còn một lần.
- `toMap + Integer::max + TreeMap::new` xử lý khóa tên sản phẩm trùng và sắp theo bảng chữ cái.
- `partitioningBy + counting` đếm hai đơn hàng có số tiền từ 100 trở lên và ba đơn hàng nhỏ hơn 100.
- `summarizingInt` tính năm phần tử, số tiền nhỏ nhất 40, lớn nhất 200 trong một phép gom.
- `joining` ghép tên có delimiter; `collectingAndThen` cung cấp list chỉ đọc.
- Mỗi `orders.stream()` là **một stream mới**, bởi một stream không thể tái sử dụng sau terminal operation. Với dữ liệu nguồn lớn hoặc không đọc lại được, hãy cân nhắc thiết kế phép tổng hợp gộp hợp lý thay vì chạy nhiều lượt như demo minh họa.

## 10. Những lỗi thường gặp khi chọn giữa chuẩn và tùy biến

| Sai lầm | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| Tạo `Collector.of` chỉ để `count` hoặc `sum` | Viết lại logic đã được thư viện hỗ trợ | `count()`, `counting()`, `summingInt/Long/Double` |
| Tạo một mutable `ArrayList` làm identity cho `reduce` | Không phù hợp mô hình reduction kết hợp, nhất là khi parallel | `collect(toCollection(ArrayList::new))` |
| Giả định `toList()` chắc chắn trả `ArrayList` sửa được | API không cam kết kiểu/mutability | `toCollection(ArrayList::new)` nếu cần kiểu cụ thể |
| Cho rằng `toSet()` luôn theo thứ tự xuất hiện | `toSet` là unordered collector | `toCollection(LinkedHashSet::new)` nếu cần thứ tự |
| Dùng `toMap(k,v)` với khóa trùng | Có thể ném `IllegalStateException` | Định nghĩa merge function hoặc dùng `groupingBy` |
| Dùng downstream `filtering` y hệt lọc stream trước `groupingBy` | Một cách giữ nhóm với giá trị rỗng/0, cách kia có thể loại nhóm | Chọn theo yêu cầu giữ hay bỏ nhóm |
| Dùng `summarizingInt` rồi đọc min/max của stream rỗng mà không kiểm tra | Extremum là sentinel, không phải giá trị dữ liệu | Kiểm tra `getCount() > 0` |
| Tạo collector custom có `combiner` không kết hợp được | Kết quả có thể khác giữa sequential/parallel | Chứng minh/kiểm thử identity và associativity |
| Gắn `CONCURRENT`/`UNORDERED`/`IDENTITY_FINISH` cho nhanh | Khai báo sai đặc tính có thể làm kết quả sai | Chỉ khai báo đặc tính thực sự được bảo đảm |
| Giả định `groupingBy` trả map đã sắp theo khóa | Không có cam kết này cho overload mặc định | Cung cấp `TreeMap::new` hoặc `LinkedHashMap::new` |
| Dùng API Java 9/10/12/16 trên một dự án vẫn biên dịch Java 8 | Lỗi biên dịch do API chưa tồn tại ở phiên bản đó | Xác định target JDK và chọn API phù hợp |
| Đếm, tổng hợp, ghép chuỗi bằng `peek` có tác dụng phụ | Stream có thể tối ưu, đổi lịch thực thi, hoặc không gọi callback như kỳ vọng | Dùng terminal operation/collector chuẩn |

## 11. Bài tập củng cố

Cho danh sách đơn hàng có các trường `customerId`, `region` và `amount`. Hãy lựa chọn cách triển khai trước khi viết mã:

1. **Đếm đơn hàng mỗi vùng:** `groupingBy(Order::getRegion, counting())`.
2. **Lấy các `customerId` duy nhất theo thứ tự gặp trong mỗi vùng:** `groupingBy(Order::getRegion, LinkedHashMap::new, mapping(Order::getCustomerId, toCollection(LinkedHashSet::new)))`, với giả định `Order` có getter này.
3. **Tổng tiền và giá trị nhỏ nhất/lớn nhất trong mỗi vùng:** `groupingBy(Order::getRegion, summarizingInt(Order::getAmount))` và kiểm tra `getCount()` cho tình huống rỗng nếu cần.
4. **Đếm hai nhóm đơn hàng từ 100 trở lên và dưới 100:** `partitioningBy(o -> o.getAmount() >= 100, counting())`.
5. **Sắp khóa vùng theo bảng chữ cái:** dùng overload ba tham số `groupingBy(classifier, TreeMap::new, downstream)`.
6. **Một thuật toán tích lũy đặc thù không có collector chuẩn phù hợp:** mô tả rõ đầu ra, bộ nhớ tích lũy, quy tắc ghép song song, trường hợp rỗng và invariant; sau đó mới đánh giá `Collector.of(...)`.

Các tên `customerId` và `getCustomerId` ở bài tập là ví dụ về thuộc tính giả định, **không phải** thành phần của lớp `Order` trong chương trình chạy ở mục 9.

**Nguyên tắc thiết kế:** dùng collector chuẩn làm các khối chức năng có hợp đồng rõ ràng; kết hợp chúng để giải quyết bài toán phân nhóm, chuyển đổi và tổng hợp. Khi một yêu cầu không thể đáp ứng đúng bằng các khối đó, viết collector tùy biến với điều kiện có kiểm chứng về tính đúng và chi phí.

### Tài liệu chính thức

- [`Collectors` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): collector chuẩn, downstream, phiên bản bắt đầu hỗ trợ từng API.
- [`Collector` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html): `supplier`, `accumulator`, `combiner`, `finisher`, identity/associativity, đặc tính collector.
- [`Stream` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): terminal operations và `Stream.toList()`.
- [Java SE 27 Documentation](https://docs.oracle.com/en/java/javase/27/): bộ tài liệu Java hiện hành để tra cứu thêm về ngôn ngữ và thư viện.