# Phân nhóm nhiều cấp với Java Stream

## 1. Bài toán và kết quả cần đạt

**Phân nhóm nhiều cấp (multi-level grouping)** là gom cùng một tập phần tử theo **nhiều tiêu chí theo thứ tự**: trước tiên phân theo khóa cấp 1, sau đó mỗi nhóm tiếp tục phân theo khóa cấp 2, cấp 3, v.v. Ví dụ trong hệ thống bán hàng:

- Cấp 1: vùng kinh doanh (`region`).
- Cấp 2: danh mục hàng (`category`).
- Dữ liệu cuối mỗi nhóm: danh sách sản phẩm, số đơn hàng, tổng tiền hoặc thống kê khác.

Thay vì chỉ có `Map<Region, List<Order>>`, ta có thể nhận được:

```text
North
  Books
    Java, Spring
  Office
    Pen
South
  Books
    SQL, Java
  Office
    Notebook
```

Trong Java, biểu diễn dữ liệu lồng hai cấp thường là:

```java
Map<String, Map<String, List<Order>>>
```

Ở đây `Map` ngoài lưu khóa cấp 1; mỗi giá trị của nó là một `Map` cấp 2; `List<Order>` nằm ở lá. Nếu chỉ cần đếm phần tử ở lá, kiểu kết quả sẽ là `Map<String, Map<String, Long>>`.

**Công cụ chính:** `Stream.collect(...)` và các collector `Collectors.groupingBy(...)`, `counting()`, `mapping()`, `summingLong()`. Chúng được giới thiệu cùng Stream trong Java 8 và vẫn được sử dụng trong JDK hiện hành. Bài học trình bày ví dụ nền tảng chạy trên Java 8+, cùng một số lựa chọn mới hơn được ghi rõ phiên bản tối thiểu khi cần.

## 2. Ý tưởng cốt lõi: một `groupingBy` nằm trong một `groupingBy`

Công thức hai cấp:

```java
stream.collect(
    Collectors.groupingBy(
        item -> keyLevel1,
        Collectors.groupingBy(
            item -> keyLevel2,
            Collectors.toList()
        )
    )
);
```

Đây là **mẫu cú pháp với `item`/`keyLevel1`/`keyLevel2` làm chỗ đại diện**, chưa phải chương trình độc lập. Trong chương trình thật, hai classifier phải trả về khóa cụ thể từ từng phần tử.

`groupingBy` bên ngoài xác định khóa cấp 1; collector bên trong là **downstream collector** và xử lý riêng các phần tử thuộc từng nhóm cấp 1. Thay `toList()` bằng `counting()`, `summingLong(...)` hay collector khác sẽ thay đổi **giá trị lá** mà không đổi hệ thống khóa nhóm.

Có ba overload hữu ích của `Collectors.groupingBy`:

| Dạng | Vai trò |
| --- | --- |
| `groupingBy(classifier)` | Tạo `Map<K, List<T>>`, mỗi nhóm lưu các phần tử gốc |
| `groupingBy(classifier, downstream)` | Tạo `Map<K, D>`, mỗi nhóm được xử lý bởi collector `downstream` |
| `groupingBy(classifier, mapFactory, downstream)` | Tương tự dạng hai đối số, nhưng tự chọn cách tạo `Map` ở cấp đó |

Các thành phần:

- **`classifier`:** hàm từ một phần tử `T` sang khóa `K`; ví dụ `order -> order.region`.
- **`downstream`:** phép tổng hợp áp dụng cho những phần tử có cùng khóa; có thể lại là một `groupingBy`.
- **`mapFactory`:** hàm tạo map trống phù hợp, chẳng hạn `TreeMap::new` khi muốn các khóa được sắp xếp.
- **`D`:** giá trị đã được downstream tổng hợp; nó có thể là `List<T>`, `Long`, `Double`, `Map<K2, D2>` hoặc một kiểu khác.

Đọc biểu thức lồng nhau từ **ngoài vào trong** theo thứ tự tiêu chí phân nhóm; đọc phần cuối từ **trong ra ngoài** để hiểu dữ liệu tại mỗi lá được thu thập thế nào.

## 3. Ví dụ hoàn chỉnh: phân nhóm vùng → danh mục → tên sản phẩm

Lưu thành `GroupTwoLevels.java`. Mỗi đơn hàng có vùng, danh mục và tên sản phẩm; hai cấp dùng `TreeMap` để in khóa theo thứ tự xác định.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupTwoLevels {
    static final class Order {
        final String region;
        final String category;
        final String product;

        Order(String region, String category, String product) {
            this.region = region;
            this.category = category;
            this.product = product;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("North", "Books", "Java"),
                new Order("South", "Books", "SQL"),
                new Order("North", "Office", "Pen"),
                new Order("North", "Books", "Spring"),
                new Order("South", "Office", "Notebook"),
                new Order("South", "Books", "Java")
        );

        Map<String, Map<String, List<String>>> grouped =
                orders.stream().collect(
                        Collectors.groupingBy(
                                order -> order.region,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        order -> order.category,
                                        TreeMap::new,
                                        Collectors.mapping(
                                                order -> order.product,
                                                Collectors.toList()
                                        )
                                )
                        )
                );

        grouped.forEach((region, categories) -> {
            System.out.println(region + ":");
            categories.forEach((category, products) ->
                    System.out.println("  " + category + " -> " + products));
        });
    }
}
```

Biên dịch/chạy:

```bash
javac GroupTwoLevels.java
java GroupTwoLevels
```

Stdout:

```text
North:
  Books -> [Java, Spring]
  Office -> [Pen]
South:
  Books -> [SQL, Java]
  Office -> [Notebook]
```

Giải thích theo pipeline:

1. `orders.stream()` tạo Stream các `Order`.
2. `groupingBy(order -> order.region, ...)` chia toàn bộ đơn thành nhóm `North`/`South`.
3. Với **mỗi vùng**, downstream `groupingBy(order -> order.category, ...)` lại chia thành `Books`/`Office`.
4. `mapping(order -> order.product, toList())` không lưu toàn bộ `Order` ở lá; nó lấy riêng `product` rồi tạo danh sách chuỗi.
5. `TreeMap::new` ở **cả hai cấp** đảm bảo vòng lặp in khóa nhóm theo thứ tự sắp xếp; `toList()` giữ thứ tự gặp phần tử của ordered stream trong từng nhóm.

Hai sản phẩm cùng tên, như `Java` ở hai vùng, vẫn thuộc hai nhóm khác nhau. Nếu tên lặp lại **trong cùng một nhóm** và muốn loại trùng, có thể thay `toList()` bằng `toSet()` nhưng khi đó thứ tự phần tử của `Set` không được mặc định đảm bảo.

## 4. Kiểu dữ liệu, các tầng map và chi phí

Cấu trúc của ví dụ:

```text
Map<String, Map<String, List<String>>>
│           │            └── dữ liệu lá: tên sản phẩm
│           └── khóa cấp 2: category
└── khóa cấp 1: region
```

Cùng một Stream nguồn có thể tạo nhiều dạng kết quả khác nhau:

| Cấu trúc | Ý nghĩa |
| --- | --- |
| `Map<String, Map<String, List<Order>>>` | Giữ đầy đủ đơn hàng trong mỗi nhóm |
| `Map<String, Map<String, List<String>>>` | Chỉ giữ thuộc tính chuỗi cần quan tâm |
| `Map<String, Map<String, Long>>` | Đếm số phần tử trong mỗi cặp khóa |
| `Map<String, Map<String, LongSummaryStatistics>>` | Thống kê số lượng, tổng, min, max, trung bình cho một giá trị `long` |
| `Map<String, Map<String, Map<String, Long>>>` | Ba cấp khóa, giá trị cuối là số đếm |

Giá trị trong `Map` **không nhất thiết là một danh sách**. Ta có thể tính kết quả tổng hợp ngay khi nhóm, tiết kiệm việc giữ toàn bộ phần tử rồi lại duyệt từng danh sách.

`groupingBy` không tạo một ô cho mọi kết hợp khóa có thể tưởng tượng được: nó chỉ tạo nhóm cho những khóa thực sự xuất hiện trong dữ liệu đầu vào. Nếu không có đơn `North/Clothing`, cặp khóa đó vắng mặt, không tự xuất hiện với danh sách rỗng hoặc số `0`. Điều này rất quan trọng khi đọc báo cáo có ô trống.

## 5. Đếm và tính tổng theo hai cấp

Trong thực tế, người dùng thường cần **chỉ số cho mỗi nhóm** thay vì danh sách đơn. Ví dụ tiếp theo tính hai bảng: số đơn và tổng giá trị đơn theo vùng → danh mục.

Lưu thành `GroupCountsAndTotals.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupCountsAndTotals {
    static final class Order {
        final String region;
        final String category;
        final long amount;

        Order(String region, String category, long amount) {
            this.region = region;
            this.category = category;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("North", "Books", 120),
                new Order("South", "Books", 80),
                new Order("North", "Office", 20),
                new Order("North", "Books", 150),
                new Order("South", "Office", 30),
                new Order("South", "Books", 200)
        );

        Map<String, Map<String, Long>> counts =
                orders.stream().collect(
                        Collectors.groupingBy(
                                order -> order.region,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        order -> order.category,
                                        TreeMap::new,
                                        Collectors.counting()
                                )
                        )
                );

        Map<String, Map<String, Long>> totals =
                orders.stream().collect(
                        Collectors.groupingBy(
                                order -> order.region,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        order -> order.category,
                                        TreeMap::new,
                                        Collectors.summingLong(order -> order.amount)
                                )
                        )
                );

        System.out.println("counts = " + counts);
        System.out.println("totals = " + totals);
    }
}
```

```bash
javac GroupCountsAndTotals.java
java GroupCountsAndTotals
```

```text
counts = {North={Books=2, Office=1}, South={Books=2, Office=1}}
totals = {North={Books=270, Office=20}, South={Books=280, Office=30}}
```

`counting()` tạo `Long`, không phải `Integer`. `summingLong(...)` cộng các `long` và cho `Long` theo từng nhóm. Trong ví dụ, mỗi `Order` có thuộc tính `amount` số nguyên; trong hệ thống tính tiền thập phân thực tế, cân nhắc `BigDecimal` và downstream `reducing(BigDecimal.ZERO, Order::getAmount, BigDecimal::add)` để tránh sai số do `double`. Với dữ liệu rất lớn, vẫn cần xét giới hạn của `long` và lựa chọn kiểu đủ độ rộng.

Hai lần gọi `orders.stream()` là chủ ý: một đối tượng Stream sau terminal operation không thể tiêu thụ lại. Nếu cần nhiều số liệu từ cùng dữ liệu với hiệu năng tối ưu, có thể sử dụng downstream collector tổng hợp phù hợp hoặc đối tượng thống kê riêng, nhưng chỉ nên thêm độ phức tạp khi có nhu cầu.

## 6. Phân nhóm ba cấp

Khi có thêm một tiêu chí, đặt thêm một `groupingBy` **bên trong** collector cấp hai:

```java
groupingBy(key1, groupingBy(key2, groupingBy(key3, counting())))
```

*Dòng trên chỉ minh họa cấu trúc; các hàm `key1`/`key2`/`key3` cần được thay bằng classifier thật.*

Ví dụ bảng số ticket theo vùng → thành phần hệ thống → trạng thái. Lưu `GroupThreeLevels.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupThreeLevels {
    static final class Ticket {
        final String region;
        final String component;
        final String status;

        Ticket(String region, String component, String status) {
            this.region = region;
            this.component = component;
            this.status = status;
        }
    }

    public static void main(String[] args) {
        List<Ticket> tickets = Arrays.asList(
                new Ticket("North", "API", "Open"),
                new Ticket("North", "API", "Done"),
                new Ticket("North", "UI", "Open"),
                new Ticket("South", "API", "Open"),
                new Ticket("South", "API", "Open")
        );

        Map<String, Map<String, Map<String, Long>>> counts =
                tickets.stream().collect(
                        Collectors.groupingBy(
                                t -> t.region,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        t -> t.component,
                                        TreeMap::new,
                                        Collectors.groupingBy(
                                                t -> t.status,
                                                TreeMap::new,
                                                Collectors.counting()
                                        )
                                )
                        )
                );

        System.out.println(counts);
    }
}
```

```bash
javac GroupThreeLevels.java
java GroupThreeLevels
```

```text
{North={API={Done=1, Open=1}, UI={Open=1}}, South={API={Open=2}}}
```

Lưu ý: kiểu `Map<String, Map<String, Map<String, Long>>>` có ba khóa cấp khác nhau dù cả ba tình cờ cùng là `String`. Nếu thiếu một cấp khi khai báo kiểu, trình biên dịch sẽ không chấp nhận giá trị collector suy luận. Trong hệ thống thật, dùng tên biến/kiểu rõ ràng (hoặc kiểu `record`/DTO cho kết quả) để tránh quá nhiều dấu ngoặc `<...>` khó đọc.

## 7. Downstream collector ở cấp lá: thay đổi nội dung nhóm

Ở mỗi cấp, `groupingBy` chịu trách nhiệm **chọn khóa**; downstream cuối quyết định **kết quả được giữ lại**. Các collector dưới đây đều còn được dùng:

| Downstream | Dữ liệu lá | Khi nên dùng |
| --- | --- | --- |
| `toList()` | `List<T>` | Giữ phần tử (kể cả giá trị trùng) |
| `toSet()` | `Set<T>` | Loại trùng theo `equals`/`hashCode` |
| `counting()` | `Long` | Đếm phần tử |
| `summingInt(...)`, `summingLong(...)` | `Integer`, `Long` | Tổng một thuộc tính số |
| `averagingDouble(...)` | `Double` | Trung bình một thuộc tính số |
| `summarizingLong(...)` | `LongSummaryStatistics` | Count, sum, min, max, average |
| `mapping(mapper, downstream)` | Theo collector bên trong | Chuyển đổi trước khi gom ở lá |
| `maxBy(comparator)`, `minBy(comparator)` | `Optional<T>` | Lấy cực trị, xử lý trường hợp vắng dữ liệu |
| `joining(delimiter)` | `String` | Ghép các phần tử chuỗi |
| `collectingAndThen(downstream, finisher)` | Kiểu sau `finisher` | Hậu xử lý kết quả nhóm |

Ví dụ nếu chỉ cần tên sản phẩm, dùng:

```java
Collectors.mapping(order -> order.product, Collectors.toList())
```

Nếu cần danh sách **có khả năng chỉnh sửa rõ ràng**, có thể dùng:

```java
Collectors.mapping(order -> order.product,
        Collectors.toCollection(java.util.ArrayList::new))
```

Nếu muốn **danh sách thành phẩm không thể chỉnh sửa** ở từng nhóm, Java 8 có:

```java
Collectors.mapping(order -> order.product,
        Collectors.collectingAndThen(
                Collectors.toList(),
                java.util.Collections::unmodifiableList))
```

Các đoạn này là **mảnh biểu thức collector**, không phải chương trình Java độc lập. `unmodifiableList` ở đây chỉ làm bất biến *giao diện chỉnh sửa danh sách lá*; các `Map` bao ngoài vẫn có thể thay đổi. Đừng nhầm với “toàn bộ cấu trúc lồng nhau bất biến”.

Trong JDK 10+, còn có `Collectors.toUnmodifiableList()`; JDK 16+ có `Stream.toList()`, nhưng `Stream.toList()` là **terminal operation của toàn Stream**, không phải `Collector` để truyền trực tiếp làm downstream. Nếu viết module yêu cầu biên dịch Java 8, hãy sử dụng các API tương thích Java 8 đã minh họa.

## 8. Phân biệt lọc trước khi nhóm và lọc bên trong nhóm

Một chi tiết dễ bị bỏ qua: lọc trước `groupingBy` có thể khiến cả khóa nhóm biến mất; còn downstream `Collectors.filtering(...)` (có từ **Java 9**, vẫn dùng trong JDK hiện hành) có thể giữ một khóa của nhóm đã xuất hiện nhưng giá trị đếm của nhóm đó bằng `0`.

Ví dụ Java 17+, lưu thành `GroupFilteringDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupFilteringDemo {
    record Order(String region, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("North", 50),
                new Order("South", 200)
        );

        Map<String, Long> filterBefore = orders.stream()
                .filter(o -> o.amount() >= 100)
                .collect(Collectors.groupingBy(
                        Order::region, TreeMap::new, Collectors.counting()));

        Map<String, Long> filterInside = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::region,
                        TreeMap::new,
                        Collectors.filtering(
                                o -> o.amount() >= 100,
                                Collectors.counting())));

        System.out.println("before = " + filterBefore);
        System.out.println("inside = " + filterInside);
    }
}
```

```bash
javac GroupFilteringDemo.java
java GroupFilteringDemo
```

```text
before = {South=1}
inside = {North=0, South=1}
```

Giải thích: `filterBefore` loại đơn `North` **trước khi tạo nhóm**, nên không có khóa `North`. `filterInside` tạo nhóm theo vùng từ các phần tử gốc và downstream kiểm tra điều kiện; nhóm `North` vẫn hiện diện với `counting() = 0`.

Khi phân nhóm **nhiều cấp**, cũng có thể đặt `filtering(...)` bên trong `groupingBy` ở cấp tương ứng, tùy khóa nào cần được giữ lại. Tuy nhiên, một cặp khóa chưa từng xuất hiện ở dữ liệu gốc sẽ **không** được tạo mới chỉ vì dùng `filtering`. Với Java 8, cần lọc trước pipeline hoặc tự thiết kế collector/hậu xử lý nếu cần chính xác hành vi giữ nhóm rỗng.

## 9. Thứ tự: sắp xếp khóa khác với thứ tự phần tử trong lá

Có ba loại thứ tự không nên nhầm lẫn:

1. **Thứ tự khóa map cấp 1, cấp 2,...:** mặc định `groupingBy(classifier)` không cam kết dùng `HashMap`, `TreeMap` hay một loại `Map` cụ thể; do đó không dựa vào thứ tự in map. Chọn `TreeMap::new` khi muốn khóa được sắp xếp tự nhiên hoặc theo comparator; chọn `LinkedHashMap::new` để giữ thứ tự chèn khi sử dụng tuần tự và có nhu cầu đó.
2. **Encounter order của Stream nguồn:** `List.stream()` và `Stream.of(...)` có encounter order. `Collectors.toList()` dưới `groupingBy` tôn trọng thứ tự phần tử trong nhóm đối với một ordered stream khi dùng collector có thứ tự.
3. **Thứ tự thực thi khi parallel:** các nhánh có thể xử lý theo thứ tự khác nhau, không có nghĩa thứ tự kết quả cuối của một ordered collector bị thay đổi.

Nếu cần sắp xếp **các giá trị bên trong nhóm** theo một thuộc tính, hãy dùng `sorted(...)` trước `collect(...)` trên ordered Stream hoặc dùng collector/hậu xử lý sắp xếp rõ ràng. Chỉ việc dùng `TreeMap` ở cấp nhóm **không** tự sắp xếp `List` tại lá.

Lưu ý về `TreeMap`: khóa phải so sánh được hoặc được cung cấp comparator hợp lệ. Nếu nhóm theo mã số lớn/cấu trúc phức tạp, cân nhắc khóa chuẩn hóa và comparator phù hợp. Nếu muốn thứ tự xuất hiện đầu tiên trong chuỗi sự kiện, `LinkedHashMap` thường dễ hiểu hơn `HashMap`.

## 10. Alternative: khóa kết hợp thay cho map lồng sâu

Khi chỉ cần gom theo **một cặp khóa**, đôi khi `Map<Key, Result>` dễ truy vấn và truyền qua các lớp ứng dụng hơn `Map<K1, Map<K2, Result>>`. Hai thiết kế phục vụ hai cách tiêu thụ khác nhau:

- **Nested map** phù hợp khi giao diện đọc “vùng → danh mục → thống kê”, cần mở rộng từng vùng hoặc drill-down.
- **Composite key** phù hợp khi cần tra cứu trực tiếp theo cặp (`region`, `category`), nối với hệ thống dữ liệu khác hoặc chuyển thành hàng của bảng.

Từ Java 16 có `record` và đã ổn định trong Java 17+, là cách ngắn gọn để tạo khóa giá trị có `equals`/`hashCode` nhất quán. Ví dụ Java 17+, lưu `GroupCompositeKey.java`:

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupCompositeKey {
    record Order(String region, String category) {}
    record Segment(String region, String category) {}

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("North", "Books"),
                new Order("North", "Office"),
                new Order("South", "Books"),
                new Order("North", "Books")
        );

        Map<Segment, Long> grouped = orders.stream().collect(
                Collectors.groupingBy(
                        order -> new Segment(order.region(), order.category()),
                        LinkedHashMap::new,
                        Collectors.counting()
                ));

        grouped.forEach((key, count) ->
                System.out.println(key + " -> " + count));
    }
}
```

```bash
javac GroupCompositeKey.java
java GroupCompositeKey
```

```text
Segment[region=North, category=Books] -> 2
Segment[region=North, category=Office] -> 1
Segment[region=South, category=Books] -> 1
```

Bài toán này chỉ có một cấp `groupingBy` nhưng khóa là **tổ hợp hai tiêu chí**. `LinkedHashMap::new` giúp kết quả của lần chạy Stream tuần tự phản ánh thứ tự khóa được thêm lần đầu. Trong môi trường chỉ có Java 8, hãy viết một lớp khóa bất biến với `equals` và `hashCode` đầy đủ, hoặc dùng kiểu khóa sẵn có có semantics rõ ràng. Không nên ghép chuỗi tùy tiện thành `region + "|" + category` vì dấu phân cách có thể xuất hiện ngay trong dữ liệu, gây va chạm hoặc khó xử lý.

Nếu có nhiều hơn hai/ba cấp và các cấp thường thay đổi theo người dùng, cân nhắc mô hình dữ liệu chuẩn hóa hoặc biểu diễn khóa đa trường; một chuỗi collector lồng quá sâu có thể khó bảo trì.

## 11. Song song: `groupingBy` và `groupingByConcurrent`

Hai kiểu collector đều còn đang được hỗ trợ nhưng có hợp đồng khác nhau:

- `groupingBy(...)` **không phải concurrent collector**. Khi Stream parallel, Java có thể chia nguồn thành kết quả nhóm tạm thời rồi **merge** các map; việc merge nhiều map lớn có thể tốn chi phí.
- `groupingByConcurrent(...)` tạo `ConcurrentMap` và có đặc tính `CONCURRENT`/`UNORDERED`. Nó phù hợp khi các nhóm không cần giữ encounter order của phần tử và cần hiệu quả trên parallel stream. Không mặc định chuyển sang nó chỉ vì có `parallel()`.

Có thể lồng hai collector concurrent khi cần đếm theo hai cấp nhưng không quan tâm thứ tự. Lưu `GroupConcurrentDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class GroupConcurrentDemo {
    static final class Event {
        final String region;
        final String type;

        Event(String region, String type) {
            this.region = region;
            this.type = type;
        }
    }

    public static void main(String[] args) {
        List<Event> events = Arrays.asList(
                new Event("North", "ERROR"),
                new Event("North", "OK"),
                new Event("South", "ERROR"),
                new Event("North", "ERROR")
        );

        ConcurrentMap<String, ConcurrentMap<String, Long>> counts =
                events.parallelStream().collect(
                        Collectors.groupingByConcurrent(
                                e -> e.region,
                                Collectors.groupingByConcurrent(
                                        e -> e.type,
                                        Collectors.counting()
                                )
                        )
                );

        Map<String, Map<String, Long>> display = new TreeMap<>();
        counts.forEach((region, byType) ->
                display.put(region, new TreeMap<>(byType)));

        System.out.println(display);
    }
}
```

```bash
javac GroupConcurrentDemo.java
java GroupConcurrentDemo
```

```text
{North={ERROR=2, OK=1}, South={ERROR=1}}
```

Bản thân `ConcurrentMap` không có thứ tự duyệt được cam kết, vì vậy ví dụ chuyển dữ liệu **sau khi đã collect xong** sang `TreeMap` chỉ để trình bày kết quả ổn định. Count là phép tổng hợp không phụ thuộc thứ tự; do đó hai cấp concurrent là một lựa chọn hợp lý cho dữ liệu này.

**Đừng hiểu nhầm:** kết quả `groupingByConcurrent(key)` có thể chứa `List<T>`, nhưng API không cam kết các list con ấy thread-safe cho những thao tác người dùng thực hiện sau khi collect, và nó không giữ encounter order. Nếu yêu cầu danh sách giao dịch theo đúng thứ tự phát sinh, hãy ưu tiên `groupingBy` với nguồn có thứ tự hoặc thiết kế bước sort rõ ràng.

Điều kiện dùng concurrent reduction phụ thuộc vào parallel stream, đặc tính `CONCURRENT` của collector và điều kiện thứ tự của Stream/collector. Parallel không mặc nhiên nhanh hơn; việc chia việc, đồng bộ, cấp phát và tranh chấp khóa cũng có chi phí. Hãy đo trên dữ liệu thật thay vì suy đoán.

## 12. Lỗi phổ biến trong phân nhóm nhiều cấp

### 12.1. Tự thêm vào một `Map` chia sẻ trong `forEach`

Mẫu sai khi chạy parallel:

```java
// Sai thiết kế: mutable Map/List dùng chung bị nhiều thread ghi đồng thời.
Map<String, List<Order>> shared = new HashMap<>();
orders.parallelStream().forEach(order ->
        shared.computeIfAbsent(order.region, key -> new ArrayList<>()).add(order));
```

*Đây là snippet mô tả lỗi, cần khai báo `Order`, `orders` và các import nếu thử biên dịch.* `HashMap`/`ArrayList` không an toàn để nhiều thread cùng chỉnh sửa. Dùng `collect(groupingBy(...))` để thư viện quản lý các container trung gian; dùng `groupingByConcurrent` khi chấp nhận semantics unordered và đã xác nhận yêu cầu.

### 12.2. Không có khóa null hoặc khóa biến đổi bất thường

Classifier nên trả khóa hợp lệ và **ổn định**. Trong implementation JDK, `groupingBy` yêu cầu kết quả classifier không phải `null`, dù một số loại map có thể chứa null key; vì vậy dữ liệu thiếu khóa phải được xử lý trước:

```java
order -> order.region == null ? "UNKNOWN" : order.region
```

Đây là snippet chỉ áp dụng cho một kiểu `Order` có trường `region`. Việc chuẩn hóa cần có ý nghĩa nghiệp vụ: các giá trị `"north"`, `"North"` và `" NORTH "` có nên là cùng một vùng không? Xác định quy tắc trước khi nhóm.

Tránh dùng object mutable làm khóa `HashMap` rồi thay đổi các trường tham gia `equals`/`hashCode` sau khi đưa vào map; việc tra cứu nhóm có thể hỏng.

### 12.3. Phụ thuộc thứ tự `HashMap` hoặc kết quả `toSet()`

Đừng viết bài test như “`grouped.toString()` phải đúng thứ tự X” nếu chưa chỉ định mapFactory/comparator. `groupingBy(classifier)` không hứa kiểu map cụ thể; `toSet()` không hứa thứ tự phần tử. Để test ổn định, dùng `TreeMap` cho khóa và sắp xếp dữ liệu cần so sánh.

### 12.4. Chọn sai collector ở lá

- `groupingBy(..., toMap(...))` có thể gây `IllegalStateException` nếu các phần tử trong **cùng nhóm** sinh key trùng mà không chỉ định merge function cho `toMap`.
- `toSet()` loại phần tử “trùng” theo `equals`/`hashCode`; nếu cần giữ cả hai giao dịch giống nhau, dùng `toList()`.
- `Collectors.toList()` không cam kết kiểu danh sách, khả năng chỉnh sửa, serializability hay thread safety. Khi cần điều đó, chọn API có hợp đồng rõ ràng như `toCollection(ArrayList::new)`.
- `maxBy`/`minBy` cho `Optional<T>` ở lá; xử lý `Optional` rõ ràng trước khi hiển thị hoặc gửi ra API.

### 12.5. Sửa dữ liệu nguồn khi Stream đang chạy

Classifier, mapper và downstream collector nên **non-interfering**, không thay đổi collection nguồn đang bị duyệt; không ghi trạng thái mutable ngoài pipeline. Nếu muốn điều chỉnh đối tượng đầu ra, tạo bước `map` tương ứng hoặc thu về kết quả rồi biến đổi sau khi pipeline kết thúc.

### 12.6. Nhầm nhóm vắng mặt với nhóm rỗng

`groupingBy` tạo nhóm khi gặp phần tử có khóa. Không thể suy luận rằng “không tìm thấy `North/Books` trong map” tương đương một nhóm có `count=0` đã được tính. Các báo cáo phải thống nhất cách biểu diễn tổ hợp chưa từng xuất hiện: vắng mặt, số `0` được bổ sung, hay một danh mục cố định.

### 12.7. Dùng Stream cho dữ liệu không phù hợp để giữ hết trong RAM

Nested map và các container lá có chi phí bộ nhớ tăng theo số phần tử và số nhóm. Với dữ liệu từ database có hàng triệu bản ghi, cân nhắc thực hiện `GROUP BY` nhiều cột trong SQL rồi chỉ đưa kết quả tổng hợp vào Java. Stream thích hợp cho dữ liệu đã có ở tầng ứng dụng hoặc lượng dữ liệu phù hợp; không tự động thay thế phép tổng hợp của DB.

## 13. Thực hành: tự kiểm tra hiểu biết

**Bài 1.** Có danh sách `Employee` với `department`, `level` và `salary`. Viết phép nhóm thành `Map<String, Map<String, Long>>` cho **tổng lương** theo phòng ban → cấp bậc. Nếu muốn test stdout, chọn `TreeMap::new` ở cả hai cấp.

**Bài 2.** Sửa yêu cầu bài 1 thành đếm số nhân viên mỗi cặp phòng ban/cấp bậc. Chỉ cần thay downstream cuối nào?

**Bài 3.** Với những cặp (phòng ban, cấp bậc) chưa có nhân viên, `groupingBy` có tự tạo nhóm chứa `0` không? Giải thích.

**Bài 4.** Một nhóm cần vừa số nhân viên vừa mức lương cao nhất. Bạn nên giữ từng nhân viên trong `List` rồi xử lý sau, hay xây dựng một downstream collector tổng hợp có chủ đích? Phương án nào dễ triển khai trước, khi nào cần tối ưu?

Lời giải mẫu chạy độc lập cho bài 1–2. Lưu `GroupExercise.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupExercise {
    static final class Employee {
        final String department;
        final String level;
        final long salary;

        Employee(String department, String level, long salary) {
            this.department = department;
            this.level = level;
            this.salary = salary;
        }
    }

    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
                new Employee("IT", "Junior", 100),
                new Employee("IT", "Senior", 200),
                new Employee("Ops", "Junior", 90),
                new Employee("IT", "Junior", 120)
        );

        Map<String, Map<String, Long>> salaryByGroup =
                employees.stream().collect(
                        Collectors.groupingBy(
                                e -> e.department,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        e -> e.level,
                                        TreeMap::new,
                                        Collectors.summingLong(e -> e.salary)
                                )
                        )
                );

        Map<String, Map<String, Long>> countByGroup =
                employees.stream().collect(
                        Collectors.groupingBy(
                                e -> e.department,
                                TreeMap::new,
                                Collectors.groupingBy(
                                        e -> e.level,
                                        TreeMap::new,
                                        Collectors.counting()
                                )
                        )
                );

        System.out.println("salary = " + salaryByGroup);
        System.out.println("count = " + countByGroup);
    }
}
```

```bash
javac GroupExercise.java
java GroupExercise
```

```text
salary = {IT={Junior=220, Senior=200}, Ops={Junior=90}}
count = {IT={Junior=2, Senior=1}, Ops={Junior=1}}
```

Giải bài 3: **không**; chỉ có nhóm được quan sát trong dữ liệu nguồn. Giải bài 4: với yêu cầu đơn giản và tập dữ liệu nhỏ, gom nhóm thành danh sách có thể dễ đọc và đủ nhanh. Với dữ liệu lớn hoặc chỉ cần chỉ số tổng hợp, dùng collector chuyên biệt (ví dụ `summarizingLong`, custom collector hoặc cách thống kê phù hợp) để không giữ mọi object ở lá. Nếu dùng collector tự viết, phải đảm bảo `supplier`/`accumulator`/`combiner`/`finisher` hợp lệ khi chạy song song.

## 14. Checklist áp dụng vào dự án

- Tôi cần **bao nhiêu cấp khóa** và cần kiểu giá trị nào **ở lá**?
- Mỗi classifier có trả khóa ổn định, không `null`, chuẩn hóa đúng nghiệp vụ?
- Một khóa nhóm bị vắng mặt có phải được bổ sung thành giá trị `0` để phục vụ báo cáo?
- Tôi đã chọn `toList`, `counting`, `summingLong` hay collector khác phù hợp thay vì lưu dư dữ liệu?
- Thứ tự khóa ở **mọi cấp** có quan trọng không? Có cần `TreeMap`, `LinkedHashMap` hoặc sắp xếp lá?
- Tôi có cần giữ encounter order của phần tử trong nhóm không, đặc biệt khi nghĩ đến `groupingByConcurrent`?
- Những khóa trùng, null, sai định dạng, biến đổi sau grouping đã được xử lý rõ chưa?
- Tôi đã kiểm tra bộ nhớ, kích thước dữ liệu và khả năng tổng hợp trong database?
- Code phải chạy trên Java 8 hay JDK 17+? Tôi có dùng API như `filtering` hoặc `record` yêu cầu phiên bản mới hơn không?

## 15. Tài liệu API chính thức còn hiệu lực

- Oracle Java SE 26 — `Collectors`, các overload `groupingBy`/`groupingByConcurrent` và downstream collectors: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- Oracle Java SE 26 — `java.util.stream`, Reduction/Mutable reduction/Ordering/Parallelism: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 26 — `Collector` (supplier, accumulator, combiner, finisher, characteristics): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html
- Oracle Java SE 26 — `TreeMap` và sorted keys: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeMap.html

**Ghi nhớ:** `groupingBy` có thể nhận một `groupingBy` khác làm downstream để tạo map lồng nhiều cấp. Đặt classifier theo thứ tự khóa từ ngoài vào trong; đặt phép tổng hợp cần thiết ở lá; chọn rõ mapFactory/thứ tự nếu kết quả cần ổn định; cân nhắc `groupingByConcurrent` chỉ khi không cần thứ tự và có lợi ích thực tế.