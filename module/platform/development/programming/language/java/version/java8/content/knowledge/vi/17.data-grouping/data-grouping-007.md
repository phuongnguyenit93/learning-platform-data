# Chọn `mapFactory` và thứ tự khóa khi phân nhóm dữ liệu với Stream

Khi phân nhóm một danh sách bằng `Collectors.groupingBy(...)`, kết quả thường là một `Map<K, D>`: **khóa** là tiêu chí phân nhóm, **giá trị** là dữ liệu hoặc kết quả tổng hợp của từng nhóm. Tuy nhiên, không phải mọi `Map` đều duyệt các khóa theo cùng một thứ tự. Nếu cần hiển thị báo cáo theo thứ tự nhóm xuất hiện, theo bảng chữ cái hoặc theo thứ tự ưu tiên, hãy chọn **`mapFactory`** phù hợp ngay trong collector.

Các API trong bài, gồm `Collectors.groupingBy`, `HashMap`, `LinkedHashMap`, `TreeMap`, `EnumMap` và các downstream collector như `toList`, `counting`, `mapping`, đều vẫn được hỗ trợ trong Java hiện đại. Mã chạy được viết theo cú pháp Java 8 và có thể biên dịch, chạy trên JDK 17+.

## 1. Một kết quả phân nhóm có hai loại thứ tự

Giả sử các đơn hàng đi vào stream theo thứ tự khu vực:

```text
south, north, south, west, north, south
```

Nếu phân nhóm theo `region` thì có ba khóa `south`, `north`, `west`. Tuy nhiên, thứ tự các khóa khi duyệt `result.keySet()` phụ thuộc vào **cấu trúc `Map` được tạo**:

- `LinkedHashMap` theo thứ tự chèn thông thường: `[south, north, west]`.
- `TreeMap` theo thứ tự tự nhiên của chuỗi: `[north, south, west]`.
- `TreeMap` với comparator đảo chiều: `[west, south, north]`.
- `HashMap`: **không bảo đảm thứ tự duyệt**. Một lần chạy có thể in ra một thứ tự tình cờ, nhưng ứng dụng không nên dựa vào đó.

Đồng thời, **thứ tự các phần tử bên trong từng nhóm** là chuyện khác. Ví dụ, một nhóm có `List<Order>` có thể giữ encounter order của các đơn hàng, trong khi các khóa `Map` được sắp xếp theo `TreeMap`. Đổi `mapFactory` không tự động sắp xếp những `List` này.

## 2. Chữ ký `groupingBy` có `mapFactory`

Java cung cấp nhiều overload của `groupingBy`. Muốn kiểm soát kiểu `Map` kết quả, dùng overload **ba tham số**:

```java
Collectors.groupingBy(classifier, mapFactory, downstream)
```

Ý nghĩa:

| Tham số | Vai trò | Ví dụ |
| --- | --- | --- |
| `classifier` | Biến mỗi phần tử `T` thành khóa nhóm `K` | `Order::getRegion` |
| `mapFactory` | Tạo một `Map<K,D>` **mới, rỗng**, quyết định cấu trúc và thứ tự duyệt khóa | `LinkedHashMap::new`, `TreeMap::new` |
| `downstream` | Gom các phần tử cùng khóa thành giá trị `D` | `Collectors.toList()`, `Collectors.counting()` |

Chữ ký generic (lược bỏ chú thích API):

```java
public static <T, K, D, A, M extends Map<K, D>>
Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream)
```

Từ đó có thể đọc một biểu thức như sau:

```java
Map<String, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,       // mỗi Order -> khóa String
        TreeMap::new,           // các khóa được sắp theo thứ tự String
        Collectors.counting()   // mỗi khóa -> số lượng Long
    ));
```

`Order` được định nghĩa trong chương trình đầy đủ ở mục 9. Ví dụ trên là **đoạn minh họa** và giả định biến `orders` đã có.

**Không có** overload `groupingBy(classifier, mapFactory)`. Overload hai tham số nhận `classifier` và `downstream`. Vì vậy, nếu muốn chỉ định một factory nhưng vẫn lấy `List` từng nhóm, phải viết đủ ba tham số:

```java
Map<String, List<Order>> grouped = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

## 3. Chọn `HashMap`, `LinkedHashMap` hay `TreeMap`

| Nhu cầu | `mapFactory` | Thứ tự khóa | Chi phí thường gặp |
| --- | --- | --- | --- |
| Chỉ tra cứu từng nhóm theo khóa, thứ tự không quan trọng | `HashMap::new` | Không được bảo đảm | Tra cứu/chèn trung bình gần `O(1)` |
| Hiển thị nhóm theo thứ tự khóa **xuất hiện lần đầu** | `LinkedHashMap::new` | Thứ tự chèn | Tra cứu/chèn trung bình gần `O(1)`; thêm bộ nhớ lưu liên kết |
| Sắp nhóm theo khóa tự nhiên | `TreeMap::new` | Tăng dần theo thứ tự tự nhiên | Tra cứu/chèn thường `O(log k)` với `k` khóa khác nhau |
| Sắp nhóm theo comparator riêng | `() -> new TreeMap<>(comparator)` | Theo comparator | Chi phí so sánh của cây, thường `O(log k)` |
| Khóa là một enum cố định | `() -> new EnumMap<>(Status.class)` | Thứ tự khai báo enum | Cấu trúc chuyên biệt cho enum, gọn và hiệu quả |

Các mức độ phức tạp là xu hướng phổ biến, không phải cam kết thời gian tuyệt đối. Chọn đúng loại `Map` trước hết là để **đáp ứng hợp đồng nghiệp vụ về thứ tự**, sau đó mới đánh giá hiệu năng bằng dữ liệu thực tế.

### `HashMap`: khi không yêu cầu thứ tự

```java
Map<String, List<Order>> groups = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        HashMap::new,
        Collectors.toList()
    ));
```

`HashMap` phù hợp khi sau đó chương trình chủ yếu gọi `groups.get("south")`, `containsKey` hay duyệt tất cả nhóm mà **không cần một thứ tự cố định**.

Nếu viết dạng ngắn `Collectors.groupingBy(Order::getRegion)`, tài liệu API **không cam kết** kiểu `Map`, mutability hoặc thứ tự khóa. Dù JDK hiện tại thường sử dụng `HashMap` ở một số overload, đừng coi chi tiết triển khai đó là hợp đồng để viết ứng dụng.

### `LinkedHashMap`: khóa xuất hiện lần đầu được đứng trước

```java
Map<String, List<Order>> firstSeen = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        LinkedHashMap::new,
        Collectors.toList()
    ));
```

Với một `List` đầu vào được xử lý bằng `stream()` **tuần tự**, khóa đầu tiên chèn vào `LinkedHashMap` ở trước. Các đơn hàng sau cùng khu vực được tích lũy vào nhóm có sẵn và không làm khóa đó chuyển vị trí:

```text
south, north, south, west, north, south
→ keySet(): [south, north, west]
```

`LinkedHashMap::new` dùng **insertion order**. `LinkedHashMap` cũng có cấu hình **access order** qua constructor đặc biệt, nhưng cấu hình đó không phải ý nghĩa của `LinkedHashMap::new`; việc truy cập khóa ở access-order map có thể thay đổi thứ tự. Đối với phân nhóm theo thứ tự xuất hiện lần đầu, nên dùng factory mặc định như trên.

Lưu ý: nếu nguồn là một `Set` vốn không có encounter order xác định, dùng `LinkedHashMap` **không tự tạo lại được thứ tự ban đầu**. Để kết quả dễ đoán, chọn một nguồn có thứ tự hoặc sắp xếp dữ liệu trước khi phân nhóm. Với phân nhóm yêu cầu thứ tự khóa theo lần gặp đầu tiên, ví dụ và quy tắc trên dùng stream **tuần tự, có thứ tự**.

### `TreeMap`: khóa luôn theo thứ tự được so sánh

```java
Map<String, Long> counts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        TreeMap::new,
        Collectors.counting()
    ));
```

Với khóa `String`, `TreeMap::new` sử dụng thứ tự tự nhiên; `counts.keySet()` là `[north, south, west]`. Đây là cách phù hợp khi xuất báo cáo cần sắp theo tên nhóm.

Muốn hiển thị giảm dần, dùng **factory chứa comparator**:

```java
Map<String, Integer> totalsDescending = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        () -> new TreeMap<>(Comparator.reverseOrder()),
        Collectors.summingInt(Order::getAmount)
    ));
```

Lúc này khóa được duyệt `west` → `south` → `north`. `TreeMap` tự sắp các **khóa**, nên không cần thêm `sorted()` ở trước chỉ nhằm sắp thứ tự khóa.

**Comparator còn quyết định khóa nào được xem là cùng nhóm trong `TreeMap`.** Ví dụ, nếu tạo `new TreeMap<>(String.CASE_INSENSITIVE_ORDER)`, các khóa `"Java"` và `"java"` được comparator xem là bằng nhau. Chúng có thể được gom vào cùng một mục bản đồ. Khi comparator không nhất quán với `equals`, ngữ nghĩa khóa của `TreeMap` có thể khác với `HashMap`/`LinkedHashMap`. Chỉ dùng comparator phân biệt hoa/thường, chuẩn hóa tên hay so theo độ dài khi chủ đích gom nhóm đúng với cách so đó.

Với các khóa không có thứ tự tự nhiên, ví dụ một kiểu đối tượng tự tạo không thực thi `Comparable`, `TreeMap::new` có thể gây `ClassCastException`. Hãy định nghĩa comparator phù hợp trong factory. `TreeMap` dùng thứ tự tự nhiên cũng không chấp nhận khóa `null`.

## 4. `EnumMap` khi khóa nhóm là enum

Nếu khóa chỉ có thể là một trong các giá trị enum đã xác định (ví dụ trạng thái đơn hàng), `EnumMap` giúp diễn đạt miền khóa và duyệt theo **thứ tự các hằng enum được khai báo**.

```java
enum Status { NEW, PROCESSING, DONE }

Map<Status, Long> countsByStatus =
    Arrays.asList(Status.DONE, Status.NEW, Status.DONE)
        .stream()
        .collect(Collectors.groupingBy(
            Function.identity(),
            () -> new EnumMap<>(Status.class),
            Collectors.counting()
        ));

System.out.println(countsByStatus); // {NEW=1, DONE=2}
```

`EnumMap` cần biết **kiểu enum** khi tạo, nên factory đúng là `() -> new EnumMap<>(Status.class)`, không phải `EnumMap::new` không tham số. Thứ tự `NEW` trước `DONE` tới từ **thứ tự khai báo**, không phải thứ tự xuất hiện trong stream.

Chỉ dùng `EnumMap` khi khóa thực sự là enum. `EnumMap` không chứa khóa `null` và không phù hợp với khóa chuỗi hoặc số bất kỳ.

## 5. Thứ tự khóa và cách lưu phần tử trong nhóm là hai quyết định độc lập

Xét biểu thức:

```java
Map<String, List<Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::getRegion,
        TreeMap::new,
        Collectors.toList()
    ));
```

`TreeMap::new` sắp **các khóa khu vực** theo chữ cái. Nhưng `Collectors.toList()` quyết định mỗi nhóm lưu **danh sách các `Order`**; nó không có nghĩa các đơn hàng trong mỗi nhóm được sắp theo giá trị tiền.

Có thể thay downstream mà **giữ nguyên lựa chọn mapFactory**:

| Downstream | Giá trị cho mỗi khóa | Ý nghĩa |
| --- | --- | --- |
| `Collectors.toList()` | `List<Order>` | Lưu toàn bộ đơn hàng thuộc nhóm |
| `Collectors.counting()` | `Long` | Đếm số đơn hàng của nhóm |
| `Collectors.summingInt(Order::getAmount)` | `Integer` | Tổng số tiền nguyên của nhóm |
| `Collectors.mapping(Order::getItem, Collectors.toSet())` | `Set<String>` | Các tên mặt hàng duy nhất, không cam kết thứ tự duyệt |
| `Collectors.mapping(Order::getItem, Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<String>` | Tên mặt hàng duy nhất, giữ thứ tự gặp trong nhóm ở stream tuần tự có thứ tự |

Ví dụ vừa muốn **thứ tự nhóm xuất hiện đầu tiên**, vừa muốn **tên hàng duy nhất, theo thứ tự đầu tiên trong từng nhóm**:

```java
Map<String, LinkedHashSet<String>> itemsByRegion =
    orders.stream()
        .collect(Collectors.groupingBy(
            Order::getRegion,
            LinkedHashMap::new,
            Collectors.mapping(
                Order::getItem,
                Collectors.toCollection(LinkedHashSet::new)
            )
        ));
```

Kết quả với dữ liệu ở mục 9:

```text
{south=[Pen, Pencil], north=[Book, Paper], west=[Bag]}
```

Lưu ý `Collectors.toList()` không cam kết loại `List` hay khả năng chỉnh sửa theo hợp đồng API. Nếu phải có `ArrayList` cụ thể để chỉnh sửa sau đó, dùng downstream `Collectors.toCollection(ArrayList::new)`.

### Muốn sắp các phần tử **trong nhóm** thì làm gì?

Có thể sắp các bản ghi theo số tiền **trước khi phân nhóm**:

```java
Map<String, List<Order>> byRegionAndAmount = orders.stream()
    .sorted(Comparator.comparingInt(Order::getAmount))
    .collect(Collectors.groupingBy(
        Order::getRegion,
        TreeMap::new,
        Collectors.toList()
    ));
```

Lúc này:

1. `sorted` sắp **tất cả phần tử stream** theo `amount` tăng dần.
2. `TreeMap` sắp **các khóa nhóm** theo tên khu vực.
3. `toList` nhận các phần tử của mỗi nhóm theo thứ tự sau bước `sorted` trong pipeline tuần tự có encounter order.

Đừng dùng `LinkedHashMap` chỉ với hy vọng nó sắp các phần tử trong `List`. `Map` và downstream collector giải quyết **hai nhu cầu khác nhau**.

## 6. Phải hiểu đầu vào và khóa phân nhóm

### Khóa trùng là mục đích của `groupingBy`

Mọi phần tử có cùng khóa phân nhóm sẽ được tích lũy vào một giá trị nhóm. Đây không phải hiện tượng `Map.put` "ghi đè" dữ liệu cũ. Chẳng hạn, ba đơn hàng có khu vực `south` được `toList` gom cả ba, còn `counting` trả về `3`.

`groupingBy` xác định khóa theo quy tắc của `Map` kết quả:

- `HashMap` / `LinkedHashMap`: khóa được nhận diện qua `hashCode`/`equals`.
- `TreeMap`: khóa được nhận diện bằng comparator hoặc thứ tự tự nhiên, trong đó `compare(a,b) == 0` nghĩa là cùng một khóa theo bản đồ.
- `EnumMap`: khóa là hằng enum của đúng loại enum được chỉ định.

Không dùng đối tượng khóa có trạng thái thay đổi ảnh hưởng đến `hashCode`, `equals` hoặc comparator sau khi thêm vào map. Chuyện này có thể khiến việc tra cứu, phân nhóm hoặc tính đúng đắn của cấu trúc trở nên khó dự đoán.

### Classifier trả `null`: không được xem là một nhóm hợp lệ

Trong các bản Java hiện hành, `Collectors.groupingBy` yêu cầu khóa do classifier sinh ra **không được `null`**; nếu classifier trả về `null`, phép gom có thể ném `NullPointerException`, ngay cả khi bạn chọn loại map vốn cho phép khóa `null`. Không nên kỳ vọng `HashMap::new` xử lý được vấn đề này.

Nếu nghiệp vụ có giá trị khu vực thiếu, hãy đưa ra quy tắc rõ ràng:

```java
Map<String, Long> countsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        order -> order.getRegion() == null
            ? "UNKNOWN"
            : order.getRegion(),
        LinkedHashMap::new,
        Collectors.counting()
    ));
```

Hoặc lọc những bản ghi không hợp lệ trước khi nhóm nếu đó là yêu cầu. Đừng tự động thay dữ liệu thiếu bằng chuỗi tùy ý trong hệ thống sản xuất mà chưa xác định ý nghĩa nghiệp vụ và khả năng va chạm với khóa thật.

### `mapFactory` phải trả về map **mới, rỗng**

`Supplier<M>` do collector nhận có thể được gọi nhiều lần, đặc biệt khi gom stream song song. Không dùng một map đã tạo trước và dùng chung làm factory:

```java
Map<String, List<Order>> shared = new LinkedHashMap<>();

// Sai ý nghĩa supplier: trả về cùng một đối tượng cho mọi lần gọi.
// Collectors.groupingBy(Order::getRegion, () -> shared, Collectors.toList())
```

Cách đúng là `LinkedHashMap::new` hoặc `() -> new TreeMap<>(comparator)`, mỗi lần được gọi sẽ tạo **một instance mới, rỗng, độc lập**. Factory không phải nơi đặt dữ liệu mặc định hay thao tác tác dụng phụ.

## 7. Nếu có `parallelStream()` thì sao?

`Collectors.groupingBy` theo API là collector **không concurrent**. Với parallel stream, framework có thể tạo nhiều map bộ phận rồi gọi **combiner** để hợp nhất chúng. Việc chọn `LinkedHashMap` hay `TreeMap` không biến collector thành concurrent và cũng không làm các map kết quả tự động an toàn cho nhiều luồng cùng chỉnh sửa về sau.

Nếu cần thứ tự **khóa xuất hiện đầu tiên** trên nguồn có thứ tự, lựa chọn rõ ràng, dễ kiểm chứng là `stream()` **tuần tự** và `LinkedHashMap::new`. Không nên dựa vào chi tiết lịch trình hoặc cách ghép các map bộ phận trong triển khai parallel để suy đoán thứ tự lần đầu xuất hiện.

Khi thực sự cần giảm chi phí ghép nhóm trên pipeline song song và **không cần bảo toàn encounter order**, Java có `Collectors.groupingByConcurrent(...)`. Collector này là **concurrent, unordered** và dùng `ConcurrentMap`; overload có factory yêu cầu một supplier tạo `ConcurrentMap` (không nhận `LinkedHashMap::new`). Ví dụ:

```java
ConcurrentMap<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::getRegion,
        Collectors.counting()
    ));
```

Cần import `java.util.concurrent.ConcurrentMap` cho đoạn mã này. Không dựa vào thứ tự `counts.keySet()` hoặc thứ tự phần tử trong mỗi nhóm của `groupingByConcurrent` như thể đó là encounter order. Việc chạy song song chỉ đáng cân nhắc nếu kích thước dữ liệu và phép tính đủ lớn, được đo bằng benchmark phù hợp.

## 8. Những tình huống nên chọn map factory nào?

| Yêu cầu báo cáo / xử lý sau nhóm | Gợi ý |
| --- | --- |
| Chỉ lấy số lượng theo mã nhóm, không quan tâm thứ tự in ra | `groupingBy(key, HashMap::new, counting())` |
| Xuất JSON / màn hình theo thứ tự khóa xuất hiện đầu tiên trong dữ liệu đầu vào | `groupingBy(key, LinkedHashMap::new, downstream)` trên stream tuần tự có thứ tự |
| Hiển thị danh mục nhóm theo tên A–Z | `groupingBy(key, TreeMap::new, downstream)` |
| Hiển thị danh mục nhóm Z–A | `groupingBy(key, () -> new TreeMap<>(Comparator.reverseOrder()), downstream)` |
| Khóa là enum và cần thứ tự enum ổn định | `groupingBy(key, () -> new EnumMap<>(Status.class), downstream)` |
| Muốn thay đổi cách lưu các giá trị bên trong nhóm | Giữ `mapFactory`; đổi `downstream` |
| Cần thứ tự của phần tử trong từng danh sách nhóm | Xử lý `sorted` thích hợp, hoặc dùng downstream có cấu trúc/thao tác sắp xếp |
| Cần gom song song mà không yêu cầu thứ tự gặp | Cân nhắc `groupingByConcurrent` và đo hiệu năng |

Để xuất JSON hay dùng với giao diện, **thứ tự thành viên của object JSON không nên được xem là hợp đồng hiển thị mặc định của mọi hệ thống tiêu thụ**. Nếu bên nhận yêu cầu thứ tự một cách rõ ràng, có thể xuất danh sách nhóm có khóa, giá trị và vị trí theo thứ tự đã quy định, thay vì chỉ dựa vào việc serializer giữ thứ tự map.

## 9. Chương trình Java hoàn chỉnh, chạy được

Tạo file **`GroupingMapFactoryDemo.java`** dưới đây. Chương trình dùng Java 8 Stream API, chạy với JDK 17+ và cho thấy kết quả của các map factory khác nhau.

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class GroupingMapFactoryDemo {
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

    enum Status { NEW, PROCESSING, DONE }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("south", "Pen", 120),
                new Order("north", "Book", 200),
                new Order("south", "Pencil", 80),
                new Order("west", "Bag", 500),
                new Order("north", "Paper", 40),
                new Order("south", "Pen", 160));

        Map<String, List<Order>> firstSeen = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        LinkedHashMap::new,
                        Collectors.toList()));

        Map<String, Long> counts = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        TreeMap::new,
                        Collectors.counting()));

        Map<String, Integer> descendingTotals = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        () -> new TreeMap<>(Comparator.reverseOrder()),
                        Collectors.summingInt(Order::getAmount)));

        Map<String, LinkedHashSet<String>> items = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Order::getItem,
                                Collectors.toCollection(LinkedHashSet::new))));

        Map<String, Long> unorderedCounts = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion,
                        Collectors.counting()));

        System.out.println("First seen keys: " + firstSeen.keySet());
        System.out.println("Sorted counts: " + counts);
        System.out.println("Descending totals: " + descendingTotals);
        System.out.println("Items by region: " + items);
        System.out.println("Default south count: " + unorderedCounts.get("south"));

        Map<Status, Long> statusCounts =
                Arrays.asList(Status.DONE, Status.NEW, Status.DONE)
                    .stream()
                    .collect(Collectors.groupingBy(
                            Function.identity(),
                            () -> new EnumMap<>(Status.class),
                            Collectors.counting()));

        System.out.println("EnumMap counts: " + statusCounts);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GroupingMapFactoryDemo.java
java GroupingMapFactoryDemo
```

Đầu ra chuẩn:

```text
First seen keys: [south, north, west]
Sorted counts: {north=2, south=3, west=1}
Descending totals: {west=500, south=360, north=240}
Items by region: {south=[Pen, Pencil], north=[Book, Paper], west=[Bag]}
Default south count: 3
EnumMap counts: {NEW=1, DONE=2}
```

Giải thích:

- Có ba khóa khu vực theo thứ tự gặp lần đầu: `south`, `north`, `west`.
- `TreeMap::new` đưa khóa về thứ tự A–Z và `counting()` cho số lượng `north=2`, `south=3`, `west=1`.
- `TreeMap` với comparator đảo chiều kết hợp `summingInt` cho tổng tiền `west=500`, `south=360` (120 + 80 + 160), `north=240` (200 + 40).
- `LinkedHashSet` trong downstream bỏ tên mặt hàng `Pen` bị lặp trong nhóm `south` nhưng vẫn giữ `Pen` trước `Pencil`.
- Ví dụ với overload không có map factory **chỉ truy xuất một khóa cụ thể**; không in toàn bộ `Map` để người đọc hiểu nhầm thứ tự mặc định là ổn định.
- `EnumMap` hiển thị `NEW` trước `DONE` theo khai báo enum, dù dữ liệu `DONE` xuất hiện trước.

Mỗi dòng gọi `orders.stream()` tạo **một stream mới**; stream đã dùng `collect` không thể được gọi terminal operation thêm lần nữa.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Thấy `groupingBy(key)` in đúng thứ tự trên máy mình nên coi đó là hợp đồng | Thứ tự có thể đổi giữa dữ liệu, môi trường hoặc phiên bản | Chỉ định `LinkedHashMap` hay `TreeMap` khi thứ tự quan trọng |
| Gọi `groupingBy(key, LinkedHashMap::new)` | Không có overload tương ứng | Dùng ba tham số `groupingBy(key, LinkedHashMap::new, downstream)` |
| Chọn `TreeMap` nhưng muốn giữ thứ tự lần gặp đầu tiên | Khóa được sắp theo comparator | Dùng `LinkedHashMap` nếu cần insertion order |
| Dùng comparator chỉ so độ dài khóa rồi nghĩ mọi chuỗi khác nhau đều là nhóm khác | `TreeMap` coi những khóa có `compare == 0` là cùng khóa | Thiết kế comparator nhận diện khóa đúng nghiệp vụ |
| Dùng nguồn `HashSet` rồi kỳ vọng `LinkedHashMap` tái hiện thứ tự nhập ban đầu | Stream nguồn không có encounter order đó | Dùng nguồn có thứ tự hoặc sắp trước |
| Muốn sắp các phần tử trong nhóm nên chỉ đổi `mapFactory` | Factory chỉ điều khiển bản đồ khóa | Sắp phần tử đầu vào hoặc tùy chỉnh downstream |
| Dùng supplier trả cùng một map đã tồn tại | Collector có thể tạo các kết quả bộ phận, gây dữ liệu lẫn và lỗi khi parallel | Factory phải tạo map mới và rỗng |
| Cho classifier trả `null` | `groupingBy` không chấp nhận khóa `null` | Lọc, sửa hoặc gán nhóm thiếu theo quy tắc nghiệp vụ rõ ràng |
| Dùng `groupingByConcurrent` rồi chờ thứ tự xuất hiện đầu tiên | Collector unordered và concurrent | Dùng `groupingBy` tuần tự cùng `LinkedHashMap` khi yêu cầu thứ tự |
| Giả định kết quả `Map` có thể sửa từ mọi overload `groupingBy` | Overload mặc định không cam kết mutability theo API | Khi cần implementation cụ thể, chỉ định `mapFactory` thích hợp; tránh tùy tiện thay đổi bản đồ đang được chia sẻ |

## 11. Tự kiểm tra

Cho dữ liệu tuần tự có thứ tự:

```java
List<String> labels = Arrays.asList("blue", "red", "blue", "green", "red");
```

Hãy dự đoán `keySet()` và các giá trị trước khi chạy:

1. `groupingBy(Function.identity(), LinkedHashMap::new, counting())` → **khóa `[blue, red, green]`**, đếm theo từng khóa `blue=2`, `red=2`, `green=1`.
2. `groupingBy(Function.identity(), TreeMap::new, counting())` → **khóa `[blue, green, red]`**, các số lượng không đổi.
3. `groupingBy(Function.identity(), () -> new TreeMap<>(Comparator.reverseOrder()), toList())` → **khóa `[red, green, blue]`**, mỗi giá trị là `List<String>` chứa các lần xuất hiện của chính nhãn đó.

**Ghi nhớ:** hãy chọn thứ tự khóa theo quy tắc cần thiết ở đầu ra (`HashMap` không cam kết thứ tự, `LinkedHashMap` thứ tự chèn, `TreeMap` thứ tự so sánh, `EnumMap` thứ tự enum), sau đó chọn `downstream` theo dữ liệu bạn muốn có trong mỗi nhóm. Hai lựa chọn phối hợp với nhau nhưng không thay thế cho nhau.

### Tài liệu API chính thức, còn áp dụng

- [`Collectors.groupingBy` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): các overload, `mapFactory` và downstream collector.
- [`LinkedHashMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LinkedHashMap.html): insertion order và access order.
- [`TreeMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeMap.html): thứ tự khóa theo comparator và phép so sánh bằng nhau.
- [`HashMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HashMap.html): thứ tự duyệt khóa không được cam kết.
- [`EnumMap` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/EnumMap.html): thứ tự khai báo của enum.
- [`Collectors.groupingByConcurrent` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): cơ chế concurrent và unordered khi nhóm song song.