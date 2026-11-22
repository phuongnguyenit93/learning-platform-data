# Chọn kiểu Map và Collector phía sau của groupingBy

## 1. Phân nhóm không chỉ là chọn khóa

Trong **JAVA_STREAM_API**, ta thường bắt đầu bằng một pipeline khai báo: lấy dữ liệu, `filter` bản ghi hợp lệ, `map` sang dạng cần thiết, rồi dùng `collect` để tạo kết quả. Khi muốn tập hợp các phần tử có cùng thuộc tính, `Collectors.groupingBy` là lựa chọn tự nhiên.

Ví dụ, từ một danh sách đơn hàng, ta muốn biết:

- Mỗi khu vực có **những đơn hàng nào**?
- Mỗi khu vực có **bao nhiêu đơn**?
- **Tổng doanh thu** của từng khu vực là bao nhiêu?
- Mỗi khu vực có những **mã sản phẩm phân biệt** nào?
- Khi hiển thị báo cáo, **các nhóm cần theo thứ tự xuất hiện, thứ tự bảng chữ cái hay không quan tâm thứ tự**?

Các câu hỏi trên đều có thể có cùng hàm phân nhóm, nhưng **kiểu Map** và **downstream collector** quyết định hình dạng và hợp đồng của kết quả.

~~~text
                      Stream<Order>
                             │
                             ▼
                  groupingBy(classifier)
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                     ▼
    Chọn Map chứa nhóm                    Chọn downstream
    ─ HashMap (*)                         ─ toList() (*)
    ─ LinkedHashMap                       ─ counting()
    ─ TreeMap                             ─ summingLong()
    ─ EnumMap                             ─ mapping(..., toSet())
                                          ─ groupingBy(...) lồng nhau
          └──────────────────┬──────────────────┘
                             ▼
                       Map<K, D>
             khóa nhóm K → kết quả D của nhóm

(*) Mô tả kiểu thường gặp, không phải cam kết mặc định
    về lớp triển khai cụ thể của Collectors.groupingBy.
~~~

Đây là bài thuộc chương **Phân nhóm và phân hoạch**. Ta sẽ tìm hiểu ba overload của `groupingBy`, cách kiểm soát thứ tự và tính sửa đổi được của Map, cách chọn collector phía sau để trả `List`, `Set`, số đếm hoặc thống kê, cùng các lưu ý về `null`, tài nguyên và parallel stream.

Ví dụ sử dụng **Java 17+**. Những API như `Collectors.mapping`, `groupingBy`, `counting` và `summingLong` đã có từ Java 8; `filtering` và `flatMapping` có từ Java 9; `teeing` có từ Java 12.

## 2. Ba overload của Collectors.groupingBy

Dạng tổng quát của API:

~~~java
// 1. Nhóm theo khóa, mỗi nhóm thu thành List<T>.
<T, K> Collector<T, ?, Map<K, List<T>>> groupingBy(
    Function<? super T, ? extends K> classifier
);

// 2. Nhóm theo khóa, tùy chọn cách tích lũy từng nhóm.
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
);

// 3. Tùy chọn cả Map đầu ra lẫn cách tích lũy từng nhóm.
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
);
~~~

Đọc từng tham số:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `classifier` | Tính khóa nhóm `K` từ một phần tử đầu vào. | `Order::region` |
| `mapFactory` | Tạo Map lưu nhóm; giúp quy định loại Map. | `LinkedHashMap::new` |
| `downstream` | Rút gọn các phần tử **trong từng nhóm** thành kết quả `D`. | `Collectors.counting()` |
| `Map<K, D>` | Mỗi khóa `K` tương ứng một kết quả nhóm kiểu `D`. | `Map<String, Long>` |

Với overload chỉ nhận `classifier`, downstream mặc định về mặt ngữ nghĩa là `toList()`, nên mỗi khóa ánh xạ tới một `List<T>`. API **không cam kết** chính xác kiểu Map/List triển khai, khả năng sửa đổi, khả năng tuần tự hóa hoặc tính an toàn luồng của các Collection mặc định.

Overload ba tham số là cách rõ nhất khi hai yêu cầu cần được kiểm soát độc lập: **Map lưu các khóa như thế nào** và **giá trị của từng khóa phải là loại kết quả gì**.

## 3. Ví dụ nền: nhóm đơn hàng theo khu vực

Đầu tiên, dùng một `record` bất biến để mô tả dòng đơn hàng và các phép phân nhóm đơn giản. Ví dụ này chạy độc lập trên Java 17+.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingBasics {
    record Order(
        String id,
        String region,
        String sku,
        int quantity,
        long unitPrice
    ) {
        long lineTotal() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O1", "Nam", "BOOK", 2, 50_000L),
            new Order("O2", "Bắc", "PEN", 3, 10_000L),
            new Order("O3", "Nam", "PEN", 1, 10_000L),
            new Order("O4", "Trung", "BOOK", 1, 50_000L)
        );

        Map<String, List<Order>> grouped = orders.stream()
            .collect(Collectors.groupingBy(Order::region));

        System.out.println(grouped.get("Nam").size());  // 2
        System.out.println(grouped.get("Bắc").size());   // 1
        System.out.println(grouped.get("Trung").size()); // 1
    }
}
~~~

Ở đây:

- `Order::region` là classifier: mỗi `Order` cho ra khóa nhóm như `"Nam"` hoặc `"Bắc"`.
- `groupingBy(Order::region)` trả về `Map<String, List<Order>>`.
- `grouped.get("Nam")` có hai đơn `O1` và `O3`.
- Không nên suy ra thứ tự duyệt **các khóa của Map** từ thứ tự in ra một lần.

Ta sẽ dùng cấu trúc `Order` này làm ngữ cảnh trong các đoạn code ngắn ở phần sau. Khi muốn chạy riêng một ví dụ trong lớp khác, hãy khai báo `record Order` và danh sách `orders` tương ứng.

## 4. Chọn Map: mặc định, LinkedHashMap, TreeMap và EnumMap

### 4.1. Map mặc định: khi không có yêu cầu cụ thể về thứ tự khóa

~~~java
Map<String, List<Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
~~~

Với Java phổ biến, kết quả thường được lưu trong `HashMap`, nhưng tài liệu `groupingBy` không cam kết một lớp Map cụ thể. Đừng viết code phụ thuộc vào:

- Map luôn là `HashMap`.
- Map luôn có thể gọi `put` hoặc `remove`.
- Các khóa luôn xuất hiện theo thứ tự đầu vào.
- Map luôn thread-safe.

Nếu yêu cầu nghiệp vụ chỉ là tra cứu theo khóa và không phụ thuộc thứ tự duyệt, kiểu khai báo `Map<K,D>` là đủ.

### 4.2. LinkedHashMap: thứ tự xuất hiện đầu tiên của nhóm

Khi cần hiển thị theo thứ tự **nhóm được gặp lần đầu** trong một pipeline tuần tự có thứ tự, dùng `LinkedHashMap`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> inFirstSeenOrder = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toList()
    ));

System.out.println(inFirstSeenOrder.keySet());
// [Nam, Bắc, Trung]
~~~

`LinkedHashMap` duyệt các khóa theo thứ tự chèn. Vì nguồn `List` có encounter order và pipeline này là tuần tự, khóa `"Nam"` được chèn đầu tiên, tiếp theo `"Bắc"` và `"Trung"`. Các lần gặp lại `"Nam"` chỉ cập nhật nhóm đang có, không biến nó thành khóa cuối.

Đây là lựa chọn phù hợp cho báo cáo cần bám theo thứ tự nhóm xuất hiện trong dữ liệu đầu vào. Nếu nguồn đã `unordered()` hoặc các phần tử đến từ một nguồn không có encounter order, thứ tự khóa theo thứ tự nguồn gốc không còn được bảo đảm.

### 4.3. TreeMap: thứ tự khóa được sắp xếp

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, List<Order>> sortedByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.toList()
    ));

System.out.println(sortedByRegion.keySet());
// [Bắc, Nam, Trung] theo String.compareTo.
~~~

`TreeMap` sắp xếp khóa theo thứ tự tự nhiên hoặc theo comparator cung cấp khi tạo Map. Nó phù hợp khi yêu cầu là **thứ tự chữ cái, mã số hoặc quy tắc ưu tiên rõ ràng**.

Nếu cần comparator riêng:

~~~java
import java.util.Comparator;
import java.util.TreeMap;

Map<String, List<Order>> reverseOrder = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        () -> new TreeMap<>(Comparator.reverseOrder()),
        Collectors.toList()
    ));
~~~

Cần chọn comparator nhất quán với định nghĩa **hai khóa có thuộc cùng nhóm hay không**. Một `TreeMap` coi hai khóa tương đương nếu comparator trả `0`. Nếu comparator gộp hai khóa không bằng nhau theo `equals`, số nhóm có thể ít hơn dự kiến.

### 4.4. EnumMap: khóa là enum hữu hạn

Với các trạng thái có miền giá trị hữu hạn, `EnumMap` thường diễn đạt miền khóa rõ và có thứ tự theo thứ tự khai báo hằng enum:

~~~java
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingByStatus {
    enum Status { NEW, PAID, CANCELLED }

    record Invoice(String code, Status status) {}

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
            new Invoice("A", Status.PAID),
            new Invoice("B", Status.NEW),
            new Invoice("C", Status.PAID)
        );

        Map<Status, Long> counts = invoices.stream()
            .collect(Collectors.groupingBy(
                Invoice::status,
                () -> new EnumMap<>(Status.class),
                Collectors.counting()
            ));

        System.out.println(counts);
        // {NEW=1, PAID=2}
    }
}
~~~

`EnumMap` không tự tạo các khóa chưa xuất hiện: nhóm `CANCELLED` không có trong Map vì không có invoice thuộc trạng thái này. Muốn báo cáo gồm **tất cả trạng thái kể cả 0**, phải bổ sung các trạng thái rỗng có chủ đích sau khi grouping hoặc khởi tạo một cấu trúc kết quả phù hợp.

### Bảng lựa chọn Map

| Mong muốn | mapFactory điển hình | Thứ tự duyệt khóa |
| --- | --- | --- |
| Tra cứu nhóm, không quan tâm thứ tự | Không truyền factory | Không cam kết |
| Giữ thứ tự gặp nhóm đầu tiên | `LinkedHashMap::new` | Thứ tự chèn |
| Sắp theo khóa/comparator | `TreeMap::new` hoặc supplier có comparator | Thứ tự so sánh |
| Khóa là enum | `() -> new EnumMap<>(MyEnum.class)` | Thứ tự khai báo enum |
| Khóa cần lookup đồng thời trong kết quả | Cân nhắc `groupingByConcurrent` | Không cam kết thứ tự |

## 5. Chọn downstream collector: List, Set, số đếm và tổng

Downstream quyết định kiểu **giá trị** của Map, không quyết định kiểu khóa. Cùng classifier `Order::region` có thể tạo nhiều báo cáo khác nhau.

### 5.1. Mặc định: List<Order>

~~~java
Map<String, List<Order>> ordersByRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
~~~

Dùng khi cần giữ các bản ghi trong từng nhóm để tiếp tục xử lý. Nếu nguồn có encounter order và collector downstream là `toList()`, các phần tử mỗi nhóm được tích lũy theo thứ tự gặp; tuy nhiên, **thứ tự khóa của Map** vẫn phụ thuộc Map.

Nếu cần đảm bảo từng List **có thể sửa**, dùng supplier rõ ràng:

~~~java
import java.util.ArrayList;

Map<String, ArrayList<Order>> editableGroups = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.toCollection(ArrayList::new)
    ));

editableGroups.get("Nam").add(
    new Order("O5", "Nam", "PAD", 1, 20_000L)
);
~~~

Không dựa vào việc `Collectors.toList()` trên JDK hiện tại tình cờ trả `ArrayList` mutable: hợp đồng không bảo đảm kiểu hay khả năng sửa của Collection đó.

### 5.2. Counting: Map<K, Long>

~~~java
Map<String, Long> orderCounts = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(orderCounts.get("Nam")); // 2
System.out.println(orderCounts.get("Bắc"));  // 1
~~~

`counting()` đếm **phần tử trong nhóm**, không đếm tổng `quantity`. Nếu muốn tính số đơn vị hàng đã bán thì dùng `summingInt(Order::quantity)` hoặc `summingLong(...)`.

### 5.3. Summing: doanh thu theo vùng

~~~java
Map<String, Long> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::lineTotal)
    ));

System.out.println(revenueByRegion.get("Nam")); // 110000
System.out.println(revenueByRegion.get("Bắc"));  // 30000
System.out.println(revenueByRegion.get("Trung")); // 50000
~~~

`summingLong` trả giá trị `Long` ở từng nhóm. Nếu tổng có khả năng vượt miền `long`, cả phép nhân `quantity * unitPrice` lẫn phép cộng tổng đều cần chính sách overflow. Ví dụ dùng `Math.multiplyExact` để phát hiện overflow phép nhân; collector `summingLong` không tự phát hiện overflow phép cộng.

### 5.4. Mapping: chỉ lưu thuộc tính cần thiết

~~~java
import java.util.Set;

Map<String, Set<String>> skusByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::sku,
            Collectors.toSet()
        )
    ));

System.out.println(skusByRegion.get("Nam"));
// Chứa BOOK và PEN, không cam kết thứ tự in.
~~~

`mapping` biến mỗi `Order` thành `sku` **bên trong từng nhóm**, rồi `toSet` loại các SKU trùng nhau. Đây là khác biệt quan trọng với việc gọi `stream.map(Order::sku)` **trước khi grouping**: khi đó ta mất trường `region` cần thiết để tính khóa.

Nếu cần giữ thứ tự xuất hiện đầu tiên của các SKU trong từng nhóm, chọn `LinkedHashSet`:

~~~java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> orderedSkus = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::sku,
            Collectors.toCollection(LinkedHashSet::new)
        )
    ));
~~~

`toSet()` không cam kết thứ tự hoặc khả năng sửa được của Set trả về; `toCollection(LinkedHashSet::new)` chọn rõ cấu trúc và tính sửa đổi được.

## 6. Chọn downstream để tạo Map con và cấu trúc nhiều tầng

### 6.1. Grouping hai cấp

Bài toán: mỗi khu vực có nhiều mã SKU; ta muốn số lượng dòng đơn hàng theo từng SKU trong từng vùng.

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, Long>> countsByRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.groupingBy(
            Order::sku,
            TreeMap::new,
            Collectors.counting()
        )
    ));

System.out.println(countsByRegionAndSku);
// {Bắc={PEN=1}, Nam={BOOK=1, PEN=1}, Trung={BOOK=1}}
~~~

Ở đây:

- Outer `TreeMap` sắp các khóa **khu vực**.
- Inner `TreeMap` sắp các khóa **SKU**.
- `counting()` đếm đơn hàng ở mỗi cặp (khu vực, SKU).

Nếu muốn số lượng sản phẩm thay vì số dòng, thay downstream trong cùng bằng `summingInt(Order::quantity)`. Kiểu kết quả khi đó là `Map<String, Map<String, Integer>>`.

### 6.2. Mỗi nhóm chứa Map từ SKU tới tổng số lượng

Một SKU có thể xuất hiện nhiều lần trong cùng khu vực. `Collectors.toMap` với merge function cho phép gộp trùng SKU:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Map<String, Integer>> unitsByRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.toMap(
            Order::sku,
            Order::quantity,
            Integer::sum
        )
    ));

System.out.println(unitsByRegionAndSku.get("Nam"));
// {BOOK=2, PEN=1}; thứ tự key của Map con không được cam kết.
~~~

Nếu không truyền merge function vào `toMap` mà hai đơn có cùng SKU, collector có thể ném `IllegalStateException` vì khóa trùng. Điều này khác với `groupingBy`, vốn **thiết kế để gom nhiều phần tử cùng khóa**.

### 6.3. Kết quả chỉ là một số thống kê của mỗi nhóm

Khi yêu cầu là giá trị min/max/tổng/trung bình, ưu tiên downstream tính trực tiếp:

~~~java
import java.util.IntSummaryStatistics;

Map<String, IntSummaryStatistics> quantityStats = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summarizingInt(Order::quantity)
    ));

System.out.println(quantityStats.get("Nam").getCount()); // 2
System.out.println(quantityStats.get("Nam").getSum());   // 3
System.out.println(quantityStats.get("Nam").getMin());   // 1
System.out.println(quantityStats.get("Nam").getMax());   // 2
~~~

`IntSummaryStatistics` là kiểu tổng hợp có các thao tác cập nhật; không xem nó như một value object bất biến sâu. Nếu cần trả ra ngoài một API không cho chỉnh sửa, hãy chuyển nó sang record bất biến hoặc các giá trị số riêng trước khi công bố.

## 7. filtering và flatMapping làm việc *bên trong* nhóm

Hai downstream được bổ sung từ Java 9 giúp tránh phải tự xây dựng vòng lặp hoặc Map tạm. Chúng khác việc đặt `filter`/`flatMap` trước `groupingBy`.

### 7.1. filtering downstream giữ nhóm dù không có phần tử đạt điều kiện

Giả sử mọi đơn ở vùng `"Trung"` có số lượng dưới 2. Ta cần báo cáo các vùng đã xuất hiện, nhưng chỉ liệt kê đơn có `quantity >= 2`.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> largeOrdersByRegion =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            order -> order.quantity() >= 2,
            Collectors.toList()
        )
    ));

System.out.println(largeOrdersByRegion.get("Nam").size()); // 1
System.out.println(largeOrdersByRegion.get("Bắc").size()); // 1
System.out.println(largeOrdersByRegion.get("Trung"));      // []
~~~

`groupingBy` tạo khóa vùng trước, sau đó `filtering` quyết định có đưa `Order` vào downstream List không. Vì thế vùng `"Trung"` vẫn có key với List rỗng.

Đối chiếu với `filter` **trước** `groupingBy`:

~~~java
Map<String, List<Order>> onlyRegionsWithLargeOrders = orders.stream()
    .filter(order -> order.quantity() >= 2)
    .collect(Collectors.groupingBy(Order::region));

System.out.println(onlyRegionsWithLargeOrders.containsKey("Trung")); // false
~~~

**Chọn theo nghiệp vụ:** nếu báo cáo phải có mọi vùng đã xuất hiện (kể cả vùng không có đơn đạt điều kiện), dùng downstream `filtering`; nếu chỉ cần vùng có ít nhất một đơn đạt điều kiện, dùng upstream `filter`.

### 7.2. flatMapping downstream phát nhiều giá trị trong từng nhóm

Một vé hỗ trợ có thể có nhiều thẻ. Ta muốn tập thẻ theo mỗi đội xử lý:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class GroupTicketTags {
    record Ticket(String team, List<String> tags) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
            new Ticket("Core", List.of("java", "api")),
            new Ticket("Data", List.of("sql")),
            new Ticket("Core", List.of("api", "stream")),
            new Ticket("Data", List.of())
        );

        Map<String, Set<String>> tagsByTeam = tickets.stream()
            .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.flatMapping(
                    ticket -> ticket.tags().stream(),
                    Collectors.toSet()
                )
            ));

        System.out.println(tagsByTeam.get("Core"));
        // Chứa java, api, stream; thứ tự không được cam kết.
    }
}
~~~

`flatMapping` chuyển mỗi phần tử trong nhóm thành một Stream con rồi gửi các phần tử của Stream đó xuống collector tiếp theo. Nếu Stream con cần đóng tài nguyên, việc đóng được `flatMapping` quản lý theo hợp đồng; dù vậy, nguồn tài nguyên bên ngoài pipeline vẫn cần được quản lý đúng.

Nếu một team chỉ có các danh sách tag rỗng, team đó vẫn có một nhóm và kết quả là một Set rỗng. Đặt `flatMap` trước grouping sẽ làm mất thông tin classifier nếu các tag không còn mang tên team.

## 8. Downstream kết hợp nhiều phép thống kê: collectingAndThen và teeing

### 8.1. collectingAndThen để hoàn thiện kết quả mỗi nhóm

Với `Collectors.collectingAndThen(downstream, finisher)`, ta để một downstream tích lũy xong rồi áp dụng bước cuối.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> readonlyLists = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.collectingAndThen(
            Collectors.toList(),
            List::copyOf
        )
    ));
~~~

Các List bên trong không sửa đổi được. **Map bên ngoài** vẫn theo hợp đồng chung của `groupingBy`, không tự trở thành Map không sửa đổi được. Ngoài ra, `List.copyOf` không chấp nhận phần tử `null`.

Nếu muốn rõ cả **Map theo thứ tự chèn và List không sửa đổi được**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> result = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toUnmodifiableList()
    ));
~~~

Kết quả có cấu trúc `LinkedHashMap` và mỗi List không sửa đổi được; bản thân Map vẫn là LinkedHashMap có thể thay đổi. Để công bố một kết quả không sửa cấu trúc được ở cả hai tầng, có thể bọc bản sao của Map:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;

Map<String, List<Order>> immutableStructure =
    Collections.unmodifiableMap(new LinkedHashMap<>(result));
~~~

Các `Order` là record bất biến về các trường được lưu ở ví dụ, nên dữ liệu minh họa khá gần với snapshot bất biến. Với object con mutable, bọc Map và List **không tự làm bất biến sâu** đồ thị dữ liệu.

### 8.2. teeing để tính hai chỉ tiêu trong một lần gom

Từ Java 12, `Collectors.teeing` cho hai downstream xử lý cùng một dòng và ghép kết quả bằng một hàm.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupCountAndRevenue {
    record Order(String region, int quantity, long unitPrice) {
        long total() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    record Summary(long orderCount, long revenue) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Nam", 2, 50_000L),
            new Order("Bắc", 3, 10_000L),
            new Order("Nam", 1, 10_000L)
        );

        Map<String, Summary> reports = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Order::total),
                    Summary::new
                )
            ));

        System.out.println(reports.get("Nam"));
        // Summary[orderCount=2, revenue=110000]
    }
}
~~~

Ở ví dụ này, khóa nhóm là `String`, còn downstream trả một `Summary` bất biến với hai chỉ tiêu. Không phải tạo `List<Order>` cho từng nhóm rồi duyệt lại để đếm và cộng. Tuy nhiên, mọi phép cộng số nguyên vẫn phải nằm trong giới hạn kiểu `long`, và `teeing` không biến phép tính có tác dụng phụ thành an toàn.

## 9. Tính sửa đổi được, thứ tự và null của kết quả nhóm

### 9.1. Hai tầng Map và Collection có hợp đồng riêng

Dù ta chọn `LinkedHashMap`, kết quả downstream có thể là List, Set hoặc số; khả năng sửa được và thứ tự của **mỗi tầng** độc lập.

| Cấu hình | Map bên ngoài | Giá trị mỗi nhóm |
| --- | --- | --- |
| `groupingBy(key)` | Loại Map và mutability không cam kết | `List<T>`; mutability không cam kết |
| `groupingBy(key, LinkedHashMap::new, toList())` | LinkedHashMap theo thứ tự chèn | List theo encounter order (nếu có), mutability không cam kết |
| `groupingBy(key, TreeMap::new, toSet())` | TreeMap theo comparator | Set bỏ trùng, thứ tự không cam kết |
| `groupingBy(key, LinkedHashMap::new, toCollection(LinkedHashSet::new))` | LinkedHashMap theo thứ tự chèn | LinkedHashSet theo thứ tự chèn |
| `groupingBy(key, counting())` | Loại Map không cam kết | Long là số lượng |
| `groupingBy(key, toUnmodifiableList())` | Mutability Map không cam kết | List không sửa đổi được, cấm phần tử null |

Một ví dụ trực quan:

~~~java
Map<String, List<Order>> grouped = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        LinkedHashMap::new,
        Collectors.toUnmodifiableList()
    ));

// grouped.put("Tây", List.of());  // Map có thể sửa được.
// grouped.get("Nam").add(...);  // Ném UnsupportedOperationException.
~~~

### 9.2. Classifier trả null: phải quy định chính sách trước grouping

Với triển khai chuẩn của Java, `groupingBy` yêu cầu khóa nhóm do classifier trả về **khác null**; nếu classifier trả null, quá trình thu thập sẽ ném `NullPointerException`.

~~~java
record Customer(String name, String region) {}

List<Customer> customers = List.of(
    new Customer("An", "Nam"),
    new Customer("Bình", null)
);

// Không được dựa vào việc groupingBy sẽ tạo một nhóm có khóa null.
// customers.stream().collect(groupingBy(Customer::region));
~~~

Nếu “chưa rõ khu vực” là một nhóm nghiệp vụ hợp lệ, chuyển nó thành khóa tường minh:

~~~java
Map<String, List<Customer>> grouped = customers.stream()
    .collect(Collectors.groupingBy(
        customer -> customer.region() == null
            ? "CHUA_XAC_DINH"
            : customer.region()
    ));

System.out.println(grouped.get("CHUA_XAC_DINH").size()); // 1
~~~

Cần tránh xung đột nếu `"CHUA_XAC_DINH"` cũng là giá trị hợp lệ của dữ liệu. Có thể dùng enum riêng hoặc kiểu khóa kết quả có trạng thái thay vì chuỗi sentinel nếu cần phân biệt chính xác.

### 9.3. Null trong downstream

`Collectors.toUnmodifiableList()` và `toUnmodifiableSet()` cấm phần tử `null`. `Collectors.toList()` không cam kết đặc tính mutability hay lớp triển khai, nên nếu chính sách null là yêu cầu quan trọng, hãy xử lý rõ trước khi collecting: lọc bỏ, ánh xạ sang giá trị thay thế, hoặc cố ý báo lỗi.

~~~java
Map<String, List<String>> cleanSkus = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            order -> order.sku() == null
                ? "UNKNOWN"
                : order.sku(),
            Collectors.toUnmodifiableList()
        )
    ));
~~~

Với ví dụ `Order` mẫu, SKU đều có giá trị; đoạn này minh họa chính sách nếu hệ thống khác có thể cung cấp SKU null.

## 10. groupBy và partitioningBy: khác nhau về miền khóa

`Collectors.partitioningBy(predicate)` chia phần tử thành hai nhóm Boolean `true` và `false`. Nó phù hợp khi bài toán thật sự có **hai phía của một điều kiện**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Order>> partitions = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.quantity() >= 2
    ));
~~~

Sự khác nhau cần ghi nhớ:

| Tiêu chí | `groupingBy` | `partitioningBy` |
| --- | --- | --- |
| Khóa | Hàm classifier trả `K` | Predicate trả Boolean |
| Số nhóm | Chỉ những khóa xuất hiện trong nguồn | Luôn có hai khóa `true` và `false` |
| Nguồn rỗng | Map rỗng | Map có hai khóa với kết quả downstream rỗng |
| Có thể chọn Map supplier? | Có ở overload ba tham số | Không có tham số mapFactory |
| Chọn downstream? | Có | Có, qua `partitioningBy(predicate, downstream)` |

Ví dụ đếm hai phía:

~~~java
Map<Boolean, Long> counts = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.quantity() >= 2,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 2
System.out.println(counts.get(false)); // 2
~~~

Với `groupingBy(order -> order.quantity() >= 2)`, một bên có thể hoàn toàn không có trong Map nếu nguồn chỉ chứa dữ liệu của bên còn lại; `partitioningBy` giữ cả hai khóa. Đây là khác biệt thường ảnh hưởng tới báo cáo và giao diện.

## 11. groupingBy và groupingByConcurrent khi chạy song song

### 11.1. groupingBy trên parallel stream

~~~java
Map<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));
~~~

`groupingBy` có thể dùng trên parallel stream, nhưng theo tài liệu API nó **không là concurrent collector**. Ở giai đoạn kết hợp, triển khai có thể cần hợp nhất các Map trung gian, gây overhead khi có nhiều khóa hoặc nhiều dữ liệu.

Với nguồn có encounter order và downstream có thứ tự như `toList()`, groupingBy giúp giữ ý nghĩa thứ tự phần tử theo từng nhóm; việc Map đầu ra duyệt các **khóa** theo thứ tự nào vẫn cần mapFactory phù hợp.

### 11.2. groupingByConcurrent khi không cần thứ tự

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> concurrentCounts =
    orders.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Order::region,
            Collectors.counting()
        )
    );
~~~

`groupingByConcurrent` là concurrent, unordered collector; kết quả là `ConcurrentMap<K,D>`. Nó cho phép triển khai phù hợp với việc tích lũy các nhóm song song, nhưng **không cam kết encounter order** của phần tử trong từng nhóm hoặc thứ tự duyệt khóa.

Nếu cần chọn loại ConcurrentMap cụ thể, dùng overload ba tham số với supplier thích hợp:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> counts =
    orders.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Order::region,
            ConcurrentHashMap::new,
            Collectors.counting()
        )
    );
~~~

Không thể dùng `LinkedHashMap::new` làm supplier cho overload này: nó yêu cầu `ConcurrentMap`. Bản thân việc Map đầu ra là concurrent **không có nghĩa** mọi giá trị downstream như `List` sẽ có thể tùy ý sửa đồng thời sau khi thu thập.

### 11.3. Chọn theo mục tiêu và đo hiệu năng

| Mục tiêu | Lựa chọn thường hợp lý |
| --- | --- |
| Báo cáo nhỏ hoặc logic rõ ràng, cần thứ tự theo nguồn | `groupingBy` trên stream tuần tự |
| Cần chia việc song song và vẫn giữ ngữ nghĩa ordered của nhóm | `groupingBy` trên parallel stream, kiểm thử và đo |
| Nhiều phần tử, nhiều nhóm, không quan tâm thứ tự | Cân nhắc `groupingByConcurrent` |
| Cần Map có khóa sắp xếp | `groupingBy(..., TreeMap::new, ...)` |
| Chỉ cần hai nhóm true/false | `partitioningBy` |

Đừng mặc định concurrent luôn nhanh hơn: kích thước nguồn, số nhóm, độ lệch giữa các nhóm, chi phí classifier và downstream, contention và số CPU đều tác động đến hiệu năng. Không dùng các lambda ghi trạng thái mutable bên ngoài để “tăng tốc” grouping; hãy giữ classifier không trạng thái và không can thiệp nguồn.

## 12. Hoàn chỉnh báo cáo nghiệp vụ: Map có thứ tự và giá trị thống kê

Giả sử một dashboard cần hiển thị khu vực theo thứ tự tên. Mỗi khu vực cần số đơn, tổng đơn vị, tổng doanh thu. Có thể dùng downstream tùy chỉnh cho một đối tượng kết quả bất biến:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class SalesDashboard {
    record Order(String region, int quantity, long unitPrice) {
        long revenue() {
            return Math.multiplyExact(quantity, unitPrice);
        }
    }

    record Summary(long orders, long units, long revenue) {
        static Summary zero() {
            return new Summary(0L, 0L, 0L);
        }

        Summary add(Order order) {
            return new Summary(
                orders + 1,
                units + order.quantity(),
                revenue + order.revenue()
            );
        }

        Summary merge(Summary other) {
            return new Summary(
                orders + other.orders(),
                units + other.units(),
                revenue + other.revenue()
            );
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("Nam", 2, 50_000L),
            new Order("Bắc", 3, 10_000L),
            new Order("Nam", 1, 10_000L),
            new Order("Trung", 1, 50_000L)
        );

        Collector<Order, ?, Summary> summaryCollector =
            Collectors.reducing(
                Summary.zero(),
                order -> Summary.zero().add(order),
                Summary::merge
            );

        Map<String, Summary> report = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                summaryCollector
            ));

        System.out.println(report);
        // {Bắc=Summary[orders=1, units=3, revenue=30000],
        //  Nam=Summary[orders=2, units=3, revenue=110000],
        //  Trung=Summary[orders=1, units=1, revenue=50000]}
    }
}
~~~

Phép `reducing(identity, mapper, op)` trong downstream chuyển mỗi `Order` thành một summary một phần tử rồi gộp bằng `Summary::merge`. `Summary` là record bất biến, `zero()` trung hòa và `merge` kết hợp được trong miền giá trị không tràn số. Cách này thích hợp khi muốn trả về đúng một đối tượng tổng hợp. Khi báo cáo chỉ cần đếm/tổng chuẩn, `counting()`, `summingLong()` hay `teeing()` thường ngắn gọn hơn.

Với dữ liệu tiền tệ thật, hãy bảo đảm các đơn hàng cùng đơn vị, kiểm tra số lượng/đơn giá hợp lệ và phát hiện overflow hoặc dùng kiểu số phù hợp. `TreeMap` chỉ giải quyết **thứ tự khóa hiển thị**, không thay thế các kiểm tra nghiệp vụ.

## 13. Lỗi thường gặp và cách sửa

### Lỗi 1: giả định Map mặc định có thứ tự chèn

~~~java
Map<String, List<Order>> map = orders.stream()
    .collect(Collectors.groupingBy(Order::region));

// Không dựa vào map.keySet() theo thứ tự Nam, Bắc, Trung.
~~~

Nếu cần thứ tự chèn của các nhóm theo một nguồn tuần tự có encounter order, hãy chọn `LinkedHashMap::new`. Nếu cần thứ tự theo tên, chọn `TreeMap::new`.

### Lỗi 2: nhầm số đơn với tổng số lượng

~~~java
Map<String, Long> orderCount = orders.stream()
    .collect(Collectors.groupingBy(Order::region, Collectors.counting()));

Map<String, Integer> units = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingInt(Order::quantity)
    ));
~~~

Với khu vực `"Nam"` trong bộ dữ liệu mẫu, `orderCount` là `2` nhưng `units` là `3`.

### Lỗi 3: dùng upstream filter khi cần giữ nhóm rỗng

~~~java
// Chỉ tạo nhóm có phần tử đạt điều kiện:
orders.stream()
    .filter(order -> order.quantity() >= 2)
    .collect(Collectors.groupingBy(Order::region));

// Giữ mọi nhóm đã gặp; mỗi nhóm có thể có danh sách rỗng:
orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.filtering(
            order -> order.quantity() >= 2,
            Collectors.toList()
        )
    ));
~~~

Hai pipeline không tương đương khi một nhóm chỉ có phần tử không đạt điều kiện.

### Lỗi 4: muốn List mutable nhưng chỉ dùng toList downstream

~~~java
// Đặc tả không cam kết mutability của List:
Collectors.groupingBy(Order::region, Collectors.toList());

// Rõ ràng hơn nếu cần ArrayList có thể sửa:
Collectors.groupingBy(
    Order::region,
    Collectors.toCollection(java.util.ArrayList::new)
);
~~~

Nếu cần kết quả không sửa được, cân nhắc `toUnmodifiableList()` và bọc Map ngoài sau khi thu thập.

### Lỗi 5: key null hoặc giá trị null không được xử lý

Một key null từ classifier có thể làm `groupingBy` ném NPE, trong khi downstream `toUnmodifiableList` cũng ném NPE nếu phần tử null. Hãy xác định chính sách: **lọc**, **thay bằng trạng thái rõ ràng** hoặc **báo lỗi**, trước khi lựa chọn collector.

### Lỗi 6: nghĩ dùng parallel là luôn nhanh hơn

~~~java
Map<String, Long> counts = orders.parallelStream()
    .collect(Collectors.groupingBy(Order::region, Collectors.counting()));
~~~

Đoạn này đúng hợp đồng, nhưng có thể chậm hơn stream tuần tự nếu đầu vào nhỏ hoặc có chi phí gộp Map lớn. Đo với dữ liệu đại diện và cân nhắc `groupingByConcurrent` nếu thứ tự không quan trọng.

### Lỗi 7: cố cập nhật Map chia sẻ từ bên trong classifier

~~~java
// Không làm: classifier chỉ nên tính khóa thuần,
// không viết vào một Map bên ngoài ở mỗi phần tử.
orders.parallelStream()
    .collect(Collectors.groupingBy(order -> {
        // sharedMap.put(...); // Side effect nguy hiểm.
        return order.region();
    }));
~~~

Hãy để `Collector` tích lũy kết quả, không viết cùng lúc vào một cấu trúc mutable ngoài pipeline.

## 14. Cách lựa chọn nhanh

| Câu hỏi | Phương án nên cân nhắc |
| --- | --- |
| Cần danh sách bản ghi theo khóa? | `groupingBy(classifier)` |
| Cần đếm số bản ghi mỗi nhóm? | `groupingBy(classifier, counting())` |
| Cần tổng doanh thu mỗi nhóm? | `groupingBy(classifier, summingLong(...))` |
| Chỉ cần một trường của mỗi phần tử? | `mapping(fieldMapper, downstream)` |
| Muốn giữ nhóm dù phần tử sau lọc là 0? | `filtering(predicate, downstream)` |
| Một phần tử phát nhiều giá trị cho nhóm? | `flatMapping(..., downstream)` |
| Cần hai chỉ tiêu cho một nhóm? | `teeing(downstream1, downstream2, merger)` |
| Cần phân nhóm hai tầng? | `groupingBy(classifier1, groupingBy(classifier2, downstream))` |
| Cần thứ tự gặp khóa trong nguồn tuần tự? | `groupingBy(key, LinkedHashMap::new, downstream)` |
| Cần khóa sắp theo comparator? | `groupingBy(key, TreeMap::new, downstream)` |
| Khóa là enum? | `groupingBy(key, () -> new EnumMap<>(Type.class), downstream)` |
| Chỉ có hai miền true/false? | `partitioningBy(predicate, downstream)` |
| Có thể bỏ encounter order để xử lý song song? | Cân nhắc `groupingByConcurrent` và benchmark |

## 15. Tự kiểm tra kiến thức

1. **Ba tham số của overload đầy đủ `groupingBy` là gì?** Classifier, mapFactory và downstream collector.
2. **Tại sao `groupingBy(Order::region)` không có nghĩa khóa Map sẽ theo thứ tự vùng xuất hiện?** Vì collector mặc định không cam kết kiểu Map hoặc thứ tự duyệt khóa.
3. **Khi nào chọn `LinkedHashMap` và khi nào chọn `TreeMap`?** LinkedHashMap cho thứ tự chèn; TreeMap cho thứ tự so sánh.
4. **`groupingBy(region, counting())` trả giá trị mỗi key kiểu gì?** `Long`, là số phần tử được phân vào nhóm.
5. **Muốn tổng số lượng, dùng `counting()` được không?** Không, dùng `summingInt(Order::quantity)` hoặc `summingLong(...)`.
6. **`mapping(Order::sku, toSet())` làm gì?** Chọn SKU trong từng nhóm, tạo Set các giá trị phân biệt.
7. **Sự khác nhau giữa `filter(...)` trước `groupingBy` và `Collectors.filtering(...)` downstream là gì?** Cách đầu có thể loại cả khóa nhóm; cách sau vẫn giữ khóa đã được classifier nhìn thấy với kết quả downstream rỗng.
8. **Một group có thể chứa một Map con không?** Có, dùng downstream `groupingBy` hoặc `toMap` phù hợp.
9. **Classifier trả null có được bảo đảm tạo nhóm null không?** Không; trong Java chuẩn hiện hành nó ném `NullPointerException`.
10. **Đặt `TreeMap::new` ở mapFactory có làm List nhóm được sắp xếp không?** Không. Nó chỉ sắp thứ tự khóa; muốn sắp giá trị nhóm cần downstream hoặc bước xử lý thích hợp.
11. **`groupingByConcurrent` có bảo đảm encounter order của các phần tử trong nhóm không?** Không; collector là unordered.
12. **`partitioningBy` khác `groupingBy(booleanClassifier)` ở trường hợp nguồn chỉ có một loại giá trị thế nào?** PartitioningBy vẫn giữ hai khóa Boolean; groupingBy chỉ có khóa xuất hiện.
13. **Map có List không sửa được có nghĩa Map ngoài cũng không sửa được không?** Không, hai tầng có hợp đồng riêng.
14. **Tại sao không tăng một bộ đếm dùng chung trong classifier khi chạy song song?** Vì lambda nên không trạng thái/không can thiệp, mutation dùng chung có thể race và phá hợp đồng.
15. **Nếu nhu cầu chỉ là đếm theo khóa, có nhất thiết tạo List rồi tính size không?** Không; dùng downstream `counting()` để tính trực tiếp.

**Ghi nhớ:** `groupingBy` là một cơ chế **phân nhóm và rút gọn từng nhóm**. `classifier` quyết định khóa, `mapFactory` quyết định cấu trúc Map và thứ tự duyệt khóa, còn `downstream` quyết định kết quả của từng nhóm: List, Set, số đếm, tổng, Map lồng nhau hoặc một summary. Hãy thiết kế ba phần theo yêu cầu nghiệp vụ, kiểm soát `null` và encounter order, rồi chỉ song song hóa khi đã bảo đảm phép tích lũy đúng và có lợi về hiệu năng.
