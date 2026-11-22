# Rút gọn từng nhóm bằng reducing

## 1. Từ phân nhóm đến một giá trị tổng hợp cho mỗi nhóm

Trong chương **Collector nhiều tầng và tổng hợp** của **JAVA_STREAM_API**, `Collectors.groupingBy` không chỉ có thể gom các bản ghi vào `List`. Mỗi nhóm còn có thể được **rút gọn trực tiếp thành một giá trị**: khoản doanh thu, đơn hàng lớn nhất, chuỗi mã, hoặc đối tượng thống kê gồm nhiều chỉ tiêu.

Ví dụ, hệ thống bán hàng muốn tạo báo cáo theo khu vực. Với mỗi khu vực, thay vì giữ toàn bộ đơn hàng rồi duyệt lại danh sách, ta có thể dùng một *downstream collector* để tính kết quả ngay trong lúc thu thập:

~~~text
Stream<Order>
     │
     ▼
groupingBy(Order::region, downstream)
     │
     ├─ Khu vực "Nam" ──► reducing(...) ──► Tổng hợp vùng Nam
     ├─ Khu vực "Bắc" ──► reducing(...) ──► Tổng hợp vùng Bắc
     └─ Khu vực "Trung" ► reducing(...) ──► Tổng hợp vùng Trung
     │
     ▼
Map<String, KếtQuảNhóm>
~~~

`Collectors.reducing` đóng vai trò **downstream reduction**: thu các phần tử trong một nhóm thành một kết quả, tuân theo identity và phép kết hợp. Kết quả của `groupingBy` vẫn là `Map<K,D>` nhưng `D` không nhất thiết là `List<T>`.

Bài tập trung vào ba overload của `reducing`, cách ghép với `groupingBy`, cách xử lý nhóm rỗng, cách xây dựng kết quả bất biến và những điều kiện để phép gộp đúng khi pipeline chạy song song. Các ví dụ sử dụng Java 17+; `Collectors.reducing` và `groupingBy` đã có từ Java 8.

## 2. Ba overload của Collectors.reducing

Chữ ký khái niệm trong `java.util.stream.Collectors`:

~~~java
// 1. Không có identity: có thể không có kết quả.
static <T> Collector<T, ?, Optional<T>> reducing(
    BinaryOperator<T> op
);

// 2. Có identity, phần tử và kết quả cùng kiểu T.
static <T> Collector<T, ?, T> reducing(
    T identity,
    BinaryOperator<T> op
);

// 3. Có identity, chuyển phần tử T thành U trước khi gộp.
static <T, U> Collector<T, ?, U> reducing(
    U identity,
    Function<? super T, ? extends U> mapper,
    BinaryOperator<U> op
);
~~~

| Dạng | Đầu vào mỗi nhóm | Kết quả mỗi nhóm | Tình huống thường dùng |
| --- | --- | --- | --- |
| `reducing(op)` | `T` | `Optional<T>` | Lấy phần tử tốt nhất, kết hợp khi không có phần tử đơn vị thích hợp |
| `reducing(identity, op)` | `T` | `T` | Cộng các số hoặc ghép giá trị cùng kiểu |
| `reducing(identity, mapper, op)` | `T` | `U` | Tính tổng doanh thu từ Order, tạo value object thống kê |

**Khác biệt với `Stream.reduce`:** `Stream.reduce(...)` là terminal operation gọi trực tiếp trên một Stream; `Collectors.reducing(...)` trả về một **Collector**, thường dùng làm đối số `downstream` của `groupingBy` hoặc `partitioningBy`. Chẳng hạn, một tổng toàn Stream có thể viết bằng `stream.reduce(...)`, còn một tổng **cho từng khóa** thường viết bằng `stream.collect(groupingBy(key, reducing(...)))`.

`reducing` không nhận trực tiếp ba tham số `identity, accumulator, combiner` như overload `Stream.reduce(identity, accumulator, combiner)`. Overload ba tham số của **collector** là `identity, mapper, binaryOperator`; hiểu nhầm hai chữ ký dễ dẫn tới lỗi biên dịch.

## 3. Bộ dữ liệu dùng xuyên suốt bài

Ví dụ sau có thể chạy độc lập. Tiền được giữ ở dạng `BigDecimal` để tránh sai số dấu chấm động khi cộng giá trị thập phân; giả định tất cả đơn cùng đơn vị tiền tệ.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class OrderData {
    record Order(
        String id,
        String region,
        String sku,
        int quantity,
        BigDecimal unitPrice
    ) {
        BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    static List<Order> orders() {
        return List.of(
            new Order("O1", "Nam",   "BOOK", 2, new BigDecimal("50.00")),
            new Order("O2", "Bắc",   "PEN",  3, new BigDecimal("10.00")),
            new Order("O3", "Nam",   "PEN",  1, new BigDecimal("10.00")),
            new Order("O4", "Trung", "PAD",  1, new BigDecimal("30.00")),
            new Order("O5", "Bắc",   "BOOK", 1, new BigDecimal("50.00"))
        );
    }

    public static void main(String[] args) {
        System.out.println(
            orders().stream().map(Order::lineTotal).toList()
        );
        // [100.00, 30.00, 10.00, 30.00, 50.00]
    }
}
~~~

Trong các snippet ngắn sau, `Order` và `orders` được hiểu là `OrderData.Order` và kết quả từ `OrderData.orders()`, hoặc các thành phần tương đương khai báo trong cùng lớp. Ba nhóm có dữ liệu:

| Khu vực | Mã đơn | Số dòng | Tổng doanh thu |
| --- | --- | ---: | ---: |
| Nam | O1, O3 | 2 | 110.00 |
| Bắc | O2, O5 | 2 | 80.00 |
| Trung | O4 | 1 | 30.00 |

Các kết quả được so sánh theo khóa bằng `Map.get(...)`; **không dựa vào thứ tự in ra của Map mặc định**, vì `groupingBy` không cam kết kiểu Map hoặc thứ tự duyệt khóa.

## 4. Dạng thứ nhất: reducing(BinaryOperator) trả Optional cho mỗi nhóm

Khi muốn lấy **đơn hàng có giá trị lớn nhất** của từng khu vực, không có một đơn hàng “số 0” tự nhiên để dùng làm identity. Vì vậy, dùng overload một tham số:

~~~java
import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

// Trong ngữ cảnh đã có List<Order> orders:
Comparator<Order> byValueThenId = Comparator
    .comparing(Order::lineTotal)
    .thenComparing(Order::id);

Map<String, Optional<Order>> biggestOrderByRegion =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(BinaryOperator.maxBy(byValueThenId))
    ));

System.out.println(biggestOrderByRegion.get("Nam").orElseThrow().id()); // O1
System.out.println(biggestOrderByRegion.get("Bắc").orElseThrow().id()); // O5
System.out.println(biggestOrderByRegion.get("Trung").orElseThrow().id()); // O4
~~~

Giải thích:

1. `Order::region` tạo khóa nhóm.
2. `BinaryOperator.maxBy(byValueThenId)` so sánh hai đơn theo thành tiền, sau đó theo mã đơn nếu cần phá hòa.
3. `Collectors.reducing(...)` dùng phép chọn “lớn hơn” để gộp các đơn trong **một nhóm**.
4. Giá trị tương ứng với mỗi khóa có kiểu `Optional<Order>`.

Tại sao Map chứa Optional dù các nhóm được tạo ra từ bản ghi thực tế? Vì collector này phải hỗ trợ việc **không nhận phần tử nào**, nhất là khi kết hợp với downstream `filtering`. Không nên tùy tiện gọi `get()` trên Optional; hãy dùng `orElseThrow` nếu chắc chắn không rỗng theo nghiệp vụ hoặc xử lý nhánh rỗng một cách rõ ràng.

### 4.1. Khi nào dùng maxBy thay vì reducing?

Với trường hợp chọn max, thư viện đã có collector chuyên dụng:

~~~java
Map<String, Optional<Order>> biggest = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.maxBy(byValueThenId)
    ));
~~~

`Collectors.maxBy(comparator)` tương đương về ngữ nghĩa với `Collectors.reducing(BinaryOperator.maxBy(comparator))`. Dạng chuyên dụng thường ngắn và thể hiện rõ chủ đích hơn. Tương tự, chọn min dùng `Collectors.minBy(...)`.

Dùng `reducing(BinaryOperator)` khi phép kết hợp có ý nghĩa nghiệp vụ riêng, ví dụ chọn một phiên bản theo quy tắc so sánh nhiều trường, hoặc hợp nhất hai value object bằng một operator đã định nghĩa.

### 4.2. Lưu ý với dữ liệu bằng nhau theo comparator

Nếu comparator coi hai bản ghi khác nhau là tương đương, việc giữ **bản ghi đại diện nào** có thể phụ thuộc vào thứ tự và cách kết hợp. Khi danh tính bản ghi có ý nghĩa, hãy thiết kế comparator phá hòa bằng khóa ổn định (ví dụ mã duy nhất) hoặc xác định chính sách chọn đại diện tường minh.

## 5. Dạng thứ hai: reducing(identity, op) trên các giá trị cùng kiểu

Nếu đầu vào của downstream đã là `BigDecimal`, ta có thể dùng `BigDecimal.ZERO` làm identity và `BigDecimal::add` để gộp:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::lineTotal,
            Collectors.reducing(
                BigDecimal.ZERO,
                BigDecimal::add
            )
        )
    ));

System.out.println(revenueByRegion.get("Nam"));   // 110.00
System.out.println(revenueByRegion.get("Bắc"));   // 80.00
System.out.println(revenueByRegion.get("Trung")); // 30.00
~~~

Ở đây có **hai collector phía sau lồng nhau**:

- `mapping(Order::lineTotal, ...)` chuyển mỗi `Order` trong nhóm thành `BigDecimal`.
- `reducing(BigDecimal.ZERO, BigDecimal::add)` gộp các khoản tiền đã chuyển.

Kết quả của `groupingBy` là `Map<String, BigDecimal>` chứ không phải Map chứa danh sách hay Optional.

`BigDecimal.ZERO` là identity hợp lệ **về giá trị số** của phép cộng. `BigDecimal.add` không làm tròn khi không truyền `MathContext`, nên thích hợp để cộng những lượng tiền có cùng đơn vị trong ví dụ. Khi hệ thống có nhiều loại tiền tệ, phải nhóm theo đồng tiền hoặc quy đổi với chính sách tỷ giá rõ ràng; phép cộng không tự làm việc đó.

### 5.1. Cùng ý nghĩa bằng dạng thứ ba, ít lớp lồng hơn

~~~java
Map<String, BigDecimal> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

Cách này thường rõ hơn khi chỉ cần một bước ánh xạ rồi cộng: `reducing(identity, mapper, op)` đã tích hợp việc biến `Order` thành `BigDecimal`.

### 5.2. Khi chỉ cần tổng số nguyên

Nếu tiền đã được mô hình hóa hợp lệ bằng `long` theo đơn vị nhỏ nhất và không có nguy cơ tràn, collector chuyên dụng thường đơn giản hơn:

~~~java
// Giả sử Order có phương thức long totalInMinorUnits().
Map<String, Long> sums = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::totalInMinorUnits)
    ));
~~~

Đoạn trên là mẫu cho một model khác có method `totalInMinorUnits`; nó không thuộc record `Order` được khai báo ở mục 3. `summingLong` có thể tràn `long` nếu tổng quá lớn; nó không tự kiểm soát overflow. Cần chọn kiểu số và chính sách kiểm tra phù hợp nghiệp vụ.

## 6. Dạng thứ ba: reducing(identity, mapper, op) cho kiểu kết quả khác kiểu nguồn

Đây là dạng rất hữu ích khi `groupingBy` cần một **value object tổng hợp** cho mỗi nhóm, thay vì chỉ đếm hoặc cộng một trường.

Giả sử mỗi khu vực phải có ba chỉ tiêu: số đơn, tổng đơn vị và doanh thu. Ta định nghĩa `Summary` là record bất biến.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupedSalesSummary {
    record Order(
        String id,
        String region,
        int quantity,
        BigDecimal unitPrice
    ) {
        BigDecimal revenue() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Summary(
        long orderCount,
        long unitCount,
        BigDecimal revenue
    ) {
        static Summary zero() {
            return new Summary(0L, 0L, BigDecimal.ZERO);
        }

        static Summary from(Order order) {
            return new Summary(
                1L,
                order.quantity(),
                order.revenue()
            );
        }

        Summary merge(Summary other) {
            return new Summary(
                orderCount + other.orderCount(),
                unitCount + other.unitCount(),
                revenue.add(other.revenue())
            );
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O1", "Nam", 2, new BigDecimal("50.00")),
            new Order("O2", "Bắc", 3, new BigDecimal("10.00")),
            new Order("O3", "Nam", 1, new BigDecimal("10.00")),
            new Order("O4", "Trung", 1, new BigDecimal("30.00")),
            new Order("O5", "Bắc", 1, new BigDecimal("50.00"))
        );

        Map<String, Summary> report = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                Collectors.reducing(
                    Summary.zero(),
                    Summary::from,
                    Summary::merge
                )
            ));

        System.out.println(report.get("Nam"));
        // Summary[orderCount=2, unitCount=3, revenue=110.00]

        System.out.println(report.get("Bắc"));
        // Summary[orderCount=2, unitCount=4, revenue=80.00]

        System.out.println(report.get("Trung"));
        // Summary[orderCount=1, unitCount=1, revenue=30.00]
    }
}
~~~

Các thành phần làm việc như sau:

| Thành phần | Chức năng | Kiểu |
| --- | --- | --- |
| `Order::region` | Tính khóa nhóm | `Order → String` |
| `TreeMap::new` | Tạo Map có khóa sắp xếp | `TreeMap<String, Summary>` |
| `Summary.zero()` | Kết quả trung hòa của mỗi nhóm | `Summary` |
| `Summary::from` | Chuyển một đơn thành summary một phần tử | `Order → Summary` |
| `Summary::merge` | Gộp hai kết quả summary | `(Summary, Summary) → Summary` |

Do `Summary` không bị thay đổi tại chỗ, mỗi phép `merge` tạo record mới. Thiết kế này giúp tránh tình trạng nhiều nhánh xử lý cùng sửa một đối tượng tích lũy dùng chung.

**Giới hạn dữ liệu:** Ví dụ giả định số lượng và đơn giá hợp lệ, cùng một đơn vị tiền tệ, các phép cộng `long` không tràn. Trong hệ thống thực, cần kiểm tra các điều kiện đó. Khi phép cộng không được làm tròn tùy tiện, `BigDecimal` là một lựa chọn hữu ích cho tổng thập phân.

## 7. Nhóm rỗng: phân biệt không có khóa, Optional.empty và identity

Đây là một khác biệt quan trọng giữa các overload của `reducing`.

### 7.1. Một khóa chưa hề xuất hiện thì không tồn tại trong groupingBy

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String region, int value) {}

Map<String, Integer> sums = List.of(
    new Row("Nam", 5),
    new Row("Bắc", 7)
).stream().collect(Collectors.groupingBy(
    Row::region,
    Collectors.reducing(0, Row::value, Integer::sum)
));

System.out.println(sums.containsKey("Trung")); // false
~~~

`groupingBy` **không tự tạo** khóa `"Trung"` nếu nguồn không có dòng nào thuộc vùng đó, dù downstream có identity bằng `0`.

### 7.2. filtering downstream có thể tạo một nhóm với 0 phần tử phù hợp

`Collectors.filtering` (Java 9+) hoạt động **bên trong** nhóm, sau khi classifier đã nhận diện khóa:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

record Row(String region, int value) {}

List<Row> rows = List.of(
    new Row("Nam", 5),
    new Row("Nam", 9),
    new Row("Bắc", 2)
);

Map<String, Optional<Integer>> qualifiedMax = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.mapping(
                Row::value,
                Collectors.reducing(BinaryOperator.maxBy(Integer::compare))
            )
        )
    ));

System.out.println(qualifiedMax.get("Nam"));   // Optional[9]
System.out.println(qualifiedMax.get("Bắc"));   // Optional.empty
System.out.println(qualifiedMax.containsKey("Trung")); // false
~~~

`"Bắc"` **có mặt trong Map** vì đã có một phần tử mang khóa này, nhưng downstream `filtering` loại phần tử đó. Kết quả reducer không có identity nên là `Optional.empty()`. Trong khi đó, `"Trung"` chưa từng xuất hiện nên không có key trong Map.

### 7.3. Có identity thì nhóm lọc rỗng nhận identity

~~~java
Map<String, Integer> qualifiedSum = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.reducing(
                0,
                Row::value,
                Integer::sum
            )
        )
    ));

System.out.println(qualifiedSum.get("Nam")); // 14
System.out.println(qualifiedSum.get("Bắc")); // 0
System.out.println(qualifiedSum.containsKey("Trung")); // false
~~~

Dạng có identity phù hợp nếu số `0` chính là ý nghĩa tổng của **nhóm hiện diện nhưng không có phần tử được chọn**. Tuy nhiên, “không có quan sát” và “giá trị quan sát bằng 0” đôi khi phải được phân biệt; khi đó dạng Optional có thể phù hợp hơn.

### 7.4. filtering upstream và downstream không tương đương

~~~java
// Có thể loại hẳn nhóm Bắc.
Map<String, Integer> upstream = rows.stream()
    .filter(row -> row.value() >= 5)
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.reducing(0, Row::value, Integer::sum)
    ));

// Vẫn giữ khóa Bắc với tổng 0.
Map<String, Integer> downstream = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.reducing(0, Row::value, Integer::sum)
        )
    ));
~~~

Nếu dashboard cần hiển thị các nhóm đã có dữ liệu đầu vào kể cả khi tổng hợp sau lọc bằng 0, dùng `filtering` làm downstream. Nếu chỉ hiển thị nhóm còn phần tử hợp lệ, lọc trước `groupingBy` phù hợp hơn.

## 8. Kết hợp reducing với mapping và groupingBy nhiều tầng

Downstream có thể được **lồng nhau** để tạo các báo cáo khác nhau mà không phải xây dựng Map thủ công.

### 8.1. mapping trước reducing

Ví dụ muốn nối các mã đơn theo một khu vực thành một chuỗi không có dấu phân cách:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> idsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::id,
            Collectors.reducing("", String::concat)
        )
    ));

System.out.println(idsByRegion.get("Nam")); // O1O3
~~~

`String::concat` có identity `""` và có tính kết hợp khi giữ thứ tự các chuỗi. Tuy nhiên, việc nối nhiều chuỗi bất biến bằng reducer có thể tạo nhiều chuỗi trung gian và tốn chi phí sao chép. Khi chỉ cần ghép văn bản, `Collectors.joining(delimiter)` thường ngắn gọn, hiệu quả và tự mô tả hơn:

~~~java
Map<String, String> prettyIds = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(Order::id, Collectors.joining(", "))
    ));

System.out.println(prettyIds.get("Nam")); // O1, O3
~~~

Phép nối chuỗi **không giao hoán**: `"O1O3"` khác `"O3O1"`. Nếu cần thứ tự xác định, giữ encounter order hoặc sắp xếp rõ ràng; đừng gọi `unordered()` trước phép gộp phụ thuộc thứ tự.

### 8.2. groupingBy nhiều cấp và reducing ở cấp cuối

Bài toán: doanh thu của từng SKU **trong mỗi khu vực**.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, BigDecimal>> byRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.groupingBy(
            Order::sku,
            TreeMap::new,
            Collectors.reducing(
                BigDecimal.ZERO,
                Order::lineTotal,
                BigDecimal::add
            )
        )
    ));

System.out.println(byRegionAndSku.get("Nam").get("BOOK")); // 100.00
System.out.println(byRegionAndSku.get("Nam").get("PEN"));  // 10.00
~~~

Ở đây có ba quyết định độc lập: **khóa nhóm ngoài** là khu vực, **khóa nhóm trong** là SKU và **phép reduction cuối** là cộng thành tiền. `TreeMap` bảo đảm các khóa Map được sắp xếp theo `String.compareTo`; nó **không** thay đổi quy tắc cộng tiền.

Nếu cấu trúc lồng nhau khiến mã khó đọc, hãy tách downstream thành một biến collector có kiểu rõ ràng hoặc một phương thức đặt tên theo nghiệp vụ:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<Order, ?, BigDecimal> revenueCollector =
    Collectors.reducing(
        BigDecimal.ZERO,
        Order::lineTotal,
        BigDecimal::add
    );

Map<String, Map<String, BigDecimal>> report =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.groupingBy(Order::sku, revenueCollector)
    ));
~~~

Đặt tên `revenueCollector` giúp làm rõ chức năng và dễ tái sử dụng trong các pipeline khác.

## 9. Identity và tính kết hợp: điều kiện để kết quả đúng

Một downstream reducer có thể được chia thành các phần rồi ghép lại khi pipeline xử lý song song. `identity` và `op` phải tạo thành phép gộp **có phần tử trung hòa và tính kết hợp** trên miền giá trị được hỗ trợ.

Với mọi kết quả hợp lệ `a`, `b`, `c` và identity `e`:

~~~text
op(e, a) = a
op(a, e) = a
op(op(a, b), c) = op(a, op(b, c))
~~~

| Phép gộp | Identity | Hợp lệ khi |
| --- | --- | --- |
| `BigDecimal::add` | `BigDecimal.ZERO` | Cùng miền/đơn vị tiền, không dùng chính sách làm tròn phá tính kết hợp |
| `Integer::sum` | `0` | Chấp nhận ngữ nghĩa số nguyên Java; nếu cần tổng toán học không tràn, phải chọn kiểu/kiểm tra phù hợp |
| `String::concat` | `""` | Cần giữ encounter order nếu thứ tự ký tự có ý nghĩa |
| `Summary::merge` | `Summary.zero()` | Các thành phần summary có identity và phép gộp tương thích |

### 9.1. Sai: chọn identity không trung hòa

~~~java
import java.util.List;
import java.util.stream.Collectors;

int wrong = List.of(2, 3).stream()
    .collect(Collectors.reducing(10, Integer::sum));

System.out.println(wrong); // 15; không phải tổng 5.
~~~

`10` không phải identity của phép cộng. Với `groupingBy`, giá trị này còn làm mỗi nhóm bị cộng thêm một lượng không mong muốn.

### 9.2. Sai: dùng phép trừ hoặc phép chia như phép gộp kết hợp

~~~java
int wrong = List.of(10, 3, 2).stream()
    .collect(Collectors.reducing(0, (left, right) -> left - right));
~~~

Phép trừ không kết hợp và `0` không là identity hai phía. Kết quả quan sát được khi chạy tuần tự không biến công thức này thành phép reduction có hợp đồng đúng cho parallel stream.

Nếu cần tính “10 trừ tổng các khoản giảm”, hãy cộng **các khoản giảm** trước, sau đó trừ tổng đúng một lần ở bước nghiệp vụ cuối.

### 9.3. Sai: dùng object mutable làm identity rồi sửa nó

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

// CHỐNG CHỈ ĐỊNH: minh họa cách viết sai.
List<String> broken = List.of("A", "B").parallelStream()
    .collect(Collectors.reducing(
        new ArrayList<String>(),
        value -> new ArrayList<>(List.of(value)),
        (left, right) -> {
            left.addAll(right); // Sửa object accumulator.
            return left;
        }
    ));
~~~

Dạng `reducing(identity, mapper, op)` không được thiết kế để mutation vào cùng một identity do các nhánh dùng chung. Khi combiner sửa List, có thể xảy ra dữ liệu trùng, race condition hoặc sai kết quả. Hãy dùng `toList`/`toCollection` hoặc custom collector đúng hợp đồng nếu cần mutable reduction:

~~~java
List<String> good = List.of("A", "B").parallelStream()
    .collect(Collectors.toList());
~~~

Tương tự, không tăng biến toàn cục hoặc ghi I/O trong `classifier`, `mapper` và `op` để đếm số lần callback chạy. Stream có thể tối ưu hóa và phân chia công việc; các side effect này không phải cơ chế tích lũy đúng.

## 10. Thứ tự, Map đầu ra và xử lý song song

`Collectors.groupingBy` và `Collectors.reducing` có thể được dùng trên **parallel stream**, nhưng `groupingBy` không phải concurrent collector. Khi song song, implementation có thể tạo các Map trung gian rồi hợp nhất, dẫn đến chi phí phối hợp và cấp phát.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> parallelRevenue = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

Vì phép cộng tiền trong ví dụ có identity hợp lệ và có tính kết hợp về giá trị số, việc chia các đơn thành những nhánh khác nhau vẫn cho tổng đúng. Tuy nhiên, sự đúng đắn không tự kéo theo hiệu năng nhanh hơn: nguồn nhỏ, nhóm phân bố lệch và chi phí gộp Map có thể làm parallel chậm hơn tuần tự.

### 10.1. Vị trí của ràng buộc thứ tự

Map mặc định từ `groupingBy` không cam kết thứ tự duyệt **khóa**. Nếu cần khóa theo thứ tự so sánh, truyền `TreeMap::new` vào overload ba tham số. Nếu cần thứ tự xuất hiện đầu của nhóm trên một pipeline tuần tự có encounter order, dùng `LinkedHashMap::new`.

Thứ tự duyệt **các khóa Map** là một vấn đề khác với encounter order của **các phần tử được đưa vào reducer**. Khi `op` là nối chuỗi, thứ tự dữ liệu có thể ảnh hưởng kết quả; khi `op` là cộng số trong miền thích hợp, thứ tự thường không ảnh hưởng đến tổng về mặt toán học.

### 10.2. groupingByConcurrent có dùng với reducing được không?

Có thể dùng `Collectors.reducing` làm downstream cho `groupingByConcurrent` nếu phép reduction tuân thủ hợp đồng:

~~~java
import java.math.BigDecimal;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, BigDecimal> totals = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

`groupingByConcurrent` trả `ConcurrentMap` và là collector **unordered**; không phù hợp khi kết quả reducer yêu cầu giữ đúng thứ tự phần tử của nguồn. Downstream `reducing` không vì được đặt trong `groupingByConcurrent` mà có thể tự ý mutation vào trạng thái dùng chung.

Việc tích lũy song song có lợi hay không còn phụ thuộc contention giữa các nhóm, kích thước dữ liệu, độ nặng của mapper và số lượng phần tử từng nhóm. Không mặc định concurrent luôn nhanh hơn.

## 11. Khi nào nên dùng collector chuyên dụng thay vì reducing?

`reducing` là công cụ tổng quát và rất hữu ích để tạo giá trị miền nghiệp vụ. Nhưng khi bài toán chỉ là một phép thống kê phổ biến, collector chuyên dụng thường gọn hơn, tránh boxing hoặc hoạt động hiệu quả hơn.

| Mục tiêu theo từng nhóm | Chọn thường hợp lý | Dạng reducing tương đương |
| --- | --- | --- |
| Số phần tử trong nhóm | `counting()` | `reducing(0L, x -> 1L, Long::sum)` |
| Tổng số lượng kiểu `int` | `summingInt(Order::quantity)` | `reducing(0, Order::quantity, Integer::sum)` |
| Tổng số lượng kiểu `long` | `summingLong(...)` | `reducing(0L, mapper, Long::sum)` |
| Giá trị lớn nhất | `maxBy(comparator)` | `reducing(BinaryOperator.maxBy(comparator))` |
| Giá trị nhỏ nhất | `minBy(comparator)` | `reducing(BinaryOperator.minBy(comparator))` |
| Nối chuỗi có dấu phân cách | `mapping(mapper, joining(", "))` | `mapping(mapper, reducing(...))` nhưng thường dài và tạo thêm chuỗi |
| Count/min/max/sum/average chuẩn | `summarizingInt/Long/Double(...)` | Tự dựng đối tượng thống kê rồi `reducing(...)` |
| Hai phép thống kê tạo một record | `teeing(...)` | Có thể dựng record trung gian rồi `reducing(...)` |
| Gộp một value object đặc thù | `reducing(identity, mapper, op)` | Đây thường là mục tiêu phù hợp nhất |

`Collectors.summingDouble` và `DoubleSummaryStatistics` còn chịu tác động của số thực dấu chấm động và thứ tự cộng. Không dựa vào tính kết hợp toán học tuyệt đối của `double`: làm tròn có thể khiến kết quả tuần tự và song song chênh lệch.

Ví dụ dùng `teeing` để gộp hai chỉ tiêu thành record trong mỗi nhóm, không cần viết operator gộp record thủ công:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

record Totals(long count, BigDecimal revenue) {}

Map<String, Totals> totals = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.reducing(
                BigDecimal.ZERO,
                Order::lineTotal,
                BigDecimal::add
            ),
            Totals::new
        )
    ));
~~~

`teeing` có từ Java 12; nó đưa từng bản ghi của một nhóm qua hai downstream rồi kết hợp kết quả của chúng bằng `Totals::new`. Nếu hệ thống có nhiều chỉ tiêu liên quan nhau, một summary bất biến như mục 6 có thể biểu diễn miền nghiệp vụ rõ hơn.

## 12. Kiểm thử kết quả đúng với nhóm, nguồn rỗng và thứ tự

Cách thử tốt nhất không phải chỉ nhìn chuỗi `Map.toString()`, bởi Map mặc định không cam kết thứ tự. Hãy kiểm tra trực tiếp giá trị ứng với từng khóa và phân biệt ba trường hợp:

1. **Nhóm có dữ liệu:** kiểm tra tổng/đại diện được chọn.
2. **Nhóm xuất hiện nhưng downstream lọc hết:** kiểm tra identity hoặc `Optional.empty()`.
3. **Nhóm không tồn tại:** kiểm tra `Map.containsKey(...) == false`.

Ví dụ kiểm tra nhanh bằng Java thuần:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupedReducingChecks {
    record Item(String group, BigDecimal amount) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
            new Item("A", new BigDecimal("2.50")),
            new Item("A", new BigDecimal("1.25")),
            new Item("B", new BigDecimal("4.00"))
        );

        Map<String, BigDecimal> serial = items.stream()
            .collect(Collectors.groupingBy(
                Item::group,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Item::amount,
                    BigDecimal::add
                )
            ));

        Map<String, BigDecimal> parallel = items.parallelStream()
            .collect(Collectors.groupingBy(
                Item::group,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Item::amount,
                    BigDecimal::add
                )
            ));

        if (serial.get("A").compareTo(new BigDecimal("3.75")) != 0) {
            throw new AssertionError("Tổng nhóm A sai");
        }

        if (serial.get("B").compareTo(new BigDecimal("4.00")) != 0) {
            throw new AssertionError("Tổng nhóm B sai");
        }

        if (serial.containsKey("C")) {
            throw new AssertionError("Không được tự tạo nhóm C");
        }

        if (!serial.equals(parallel)) {
            throw new AssertionError("Kết quả tuần tự và song song khác nhau");
        }

        System.out.println("PASS");
    }
}
~~~

Trong ví dụ này, cùng các `BigDecimal` đầu vào và cùng cách gộp không làm tròn, giá trị tổng được giữ nhất quán khi phân nhánh. Nếu miền thực tế có dữ liệu null, giá trị tiền âm, tiền nhiều đơn vị hoặc các phép tính số nguyên có nguy cơ tràn, phải bổ sung kiểm thử và kiểm soát nghiệp vụ.

## 13. Những lỗi thường gặp khi reducing từng nhóm

### Lỗi 1: gộp toàn Stream rồi mới nghĩ đến nhóm

~~~java
// Chỉ tính MỘT tổng cho toàn bộ Stream:
BigDecimal overall = orders.stream()
    .map(Order::lineTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

// Tính MỘT tổng CHO MỖI khu vực:
Map<String, BigDecimal> perRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

`Stream.reduce` không tự phân nhóm; muốn có nhiều kết quả theo khóa phải kết hợp `groupingBy` với downstream collector.

### Lỗi 2: kỳ vọng overload không identity trả T trực tiếp

~~~java
// reducing(BinaryOperator<T>) trả Optional<T> cho mỗi nhóm.
Map<String, Optional<Order>> selected = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BinaryOperator.maxBy(Comparator.comparing(Order::lineTotal))
        )
    ));
~~~

`Map<String, Order>` không phải kiểu đúng của kết quả trên. Nếu cần bỏ Optional, hãy thiết kế chính sách cho trường hợp rỗng (đặc biệt nếu dùng downstream `filtering`).

### Lỗi 3: đặt identity thành một giá trị nghiệp vụ không trung hòa

~~~java
// Sai nếu muốn tổng bình thường: mỗi nhóm sẽ bị cộng thêm 100.
Collectors.reducing(
    new BigDecimal("100"),
    Order::lineTotal,
    BigDecimal::add
);
~~~

Dùng `BigDecimal.ZERO` cho tổng, hoặc định nghĩa identity đúng cho value object cụ thể.

### Lỗi 4: làm biến dạng kết quả bằng mutable identity và side effect

~~~java
// Không tăng một biến đếm mutable bên ngoài mapper/operator để xây báo cáo;
// không sửa một List/Map dùng chung từ phép gộp reducing trong parallel stream.
~~~

Hãy để collector quản lý tích lũy, hoặc dùng `toList` / `toMap` / `groupingBy` / collector tùy chỉnh đúng hợp đồng khi thực sự cần mutable reduction.

### Lỗi 5: đặt filter sai tầng

Nếu cần giữ mọi nhóm đã từng xuất hiện, đặt `Collectors.filtering` **bên trong** `groupingBy`. Nếu chỉ muốn các nhóm có phần tử phù hợp, lọc **trước** `groupingBy`. Hai dạng có thể khác nhau dù tổng của các nhóm còn lại giống nhau.

### Lỗi 6: tưởng parallel sẽ luôn tăng tốc

Reduction tùy biến có thể tạo nhiều object trung gian; grouping còn có chi phí gộp Map. Với nguồn nhỏ hoặc nhóm quá lệch, parallel có thể chậm hơn. Đo bằng dữ liệu đại diện và xác minh tính kết hợp trước khi tối ưu.

## 14. Bảng ra quyết định

| Câu hỏi | Lựa chọn nên cân nhắc |
| --- | --- |
| Cần một giá trị trên toàn bộ nguồn? | `Stream.reduce` hoặc collector terminal phù hợp |
| Cần một giá trị trên từng khóa? | `groupingBy(classifier, reducing(...))` |
| Không có identity hợp lệ? | `reducing(BinaryOperator)` → `Optional<T>` |
| Có identity, phần tử và kết quả cùng kiểu? | `reducing(identity, op)` |
| Cần biến phần tử `T` thành kết quả kiểu `U`? | `reducing(identityU, mapper, op)` |
| Chỉ cần đếm/tổng/min/max chuẩn? | `counting`, `summingX`, `minBy`, `maxBy` |
| Cần thống kê nhiều trường gộp được? | `reducing` với record bất biến hoặc `teeing` |
| Muốn giữ nhóm lọc rỗng? | `groupingBy(key, filtering(predicate, reducing(...)))` |
| Cần báo cáo hai cấp? | `groupingBy(key1, groupingBy(key2, reducing(...)))` |
| Cần thứ tự duyệt khóa Map? | Thêm `LinkedHashMap::new` hoặc `TreeMap::new` |
| Muốn xử lý song song không quan tâm thứ tự? | Kiểm tra luật gộp; cân nhắc `groupingByConcurrent` và benchmark |

## 15. Câu hỏi tự kiểm tra

1. **Ba overload của `Collectors.reducing` khác nhau ở đâu?** Dạng một trả `Optional<T>`, dạng hai dùng identity cho các phần tử kiểu `T`, dạng ba thêm mapper từ `T` sang `U`.
2. **Vì sao `groupingBy(region, reducing(...))` khác `stream.reduce(...)`?** Dạng đầu tạo kết quả riêng cho từng khóa; dạng sau chỉ tạo một kết quả toàn nguồn.
3. **Khi dùng `reducing(BinaryOperator.maxBy(...))`, mỗi giá trị Map có kiểu gì?** `Optional<T>`.
4. **Nhóm không tồn tại có tự xuất hiện với identity của reducer không?** Không; `groupingBy` chỉ tạo các khóa mà classifier đã nhận diện.
5. **Nhóm có phần tử nhưng downstream `filtering` bỏ hết thì dạng reducing không identity cho gì?** `Optional.empty()`.
6. **Nếu cùng trường hợp nhưng reducer có identity `0`?** Giá trị của nhóm là `0` (nếu identity là 0 và phép gộp phù hợp).
7. **Tại sao `BigDecimal.ZERO` là identity hợp lý khi cộng doanh thu cùng đơn vị?** Vì cộng 0 không thay đổi giá trị số của tổng.
8. **Tại sao không dùng phép trừ để gộp các summary khi cần parallel?** Phép trừ không kết hợp và thường không có identity hai phía phù hợp.
9. **Trong overload `reducing(identity, mapper, op)`, mapper nhận Order hay Summary?** Nhận Order (phần tử đầu vào), trả Summary hoặc kiểu `U` tương ứng.
10. **`groupingBy(..., TreeMap::new, reducing(...))` thay đổi điều gì?** Thứ tự duyệt khóa Map; không đổi cách reducer tính giá trị nhóm.
11. **Khi chỉ cần số lượng đơn mỗi vùng, cách nào ngắn hơn?** `groupingBy(Order::region, counting())`.
12. **Khi kết quả cần hai chỉ tiêu độc lập, có công cụ nào thay cho việc tự viết record merge?** `Collectors.teeing` kết hợp hai downstream.
13. **`groupingByConcurrent` có bảo đảm thứ tự phần tử của nguồn trong mỗi nhóm không?** Không; đó là concurrent, unordered collector.
14. **Vì sao không dùng `StringBuilder` mutable làm identity trong reducing?** Phá giả định tích lũy dạng giá trị; dùng collector chuyên dụng như `joining` khi ghép chuỗi.
15. **Làm sao kiểm tra reducer đúng trên parallel stream?** Kiểm tra identity, tính kết hợp, miền giá trị, nhóm rỗng và so sánh kết quả tuần tự/song song với bộ dữ liệu đại diện.

**Ghi nhớ:** `Collectors.reducing` cho phép **tổng hợp trực tiếp mỗi nhóm** khi được dùng làm downstream của `groupingBy`. Dạng không identity cho `Optional`; dạng có identity cho giá trị trực tiếp; dạng có mapper giúp kết hợp `Order` thành tiền hoặc summary bất biến. Chọn phép gộp có identity và tính kết hợp phù hợp, phân biệt nhóm vắng mặt với nhóm lọc rỗng, rồi cân nhắc collector chuyên dụng và hiệu năng song song trước khi tối ưu.
