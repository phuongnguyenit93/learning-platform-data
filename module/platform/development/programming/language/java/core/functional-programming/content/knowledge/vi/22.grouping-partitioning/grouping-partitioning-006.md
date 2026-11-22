# Đếm, tính tổng và tìm phần tử đại diện theo nhóm với Java Stream

Một nhu cầu rất thường gặp khi xử lý dữ liệu là **chia các bản ghi thành nhóm theo một khóa**, rồi tính toán một kết quả cho từng nhóm: có bao nhiêu bản ghi, tổng giá trị là bao nhiêu và bản ghi nào đại diện cho nhóm. Java Stream API giải quyết bằng `Collectors.groupingBy(...)` kết hợp với các **downstream collector** như `counting()`, `summingInt()`, `summingLong()`, `maxBy()`, `minBy()` và `teeing()`.

Ví dụ dữ liệu đơn hàng có mã, phòng ban, số lượng và số tiền:

~~~java
record Order(String id, String department, int quantity, long cents, boolean paid) {}
~~~

Ta có thể tính số đơn theo phòng ban bằng:

~~~java
Map<String, Long> countByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.counting()));
~~~

Đây là **đoạn minh họa**, cần `List<Order> orders`, `Map` và `Collectors` trong ngữ cảnh thích hợp. Nếu không cung cấp Map factory, **không được dựa vào thứ tự duyệt các khóa** của Map kết quả. Ở ví dụ chạy đầy đủ phía dưới, ta dùng `TreeMap::new` để in các nhóm theo thứ tự khóa, nhờ vậy đầu ra có thể kiểm chứng chính xác.

## 1. Tư duy hai tầng: classifier và downstream collector

Hãy đọc biểu thức:

~~~java
orders.stream().collect(
    Collectors.groupingBy(
        Order::department,
        Collectors.counting()
    )
);
~~~

thành hai quyết định:

1. **Classifier `Order::department`**: phần tử nào thuộc nhóm nào? Từ `Order` trả về khóa `String`.
2. **Downstream `Collectors.counting()`**: từng nhóm sẽ được thu thập thành giá trị gì? Ở đây là `Long` chứa số phần tử.

Mô hình:

~~~text
Stream<Order>
   |
   | classifier: Order::department
   v
books: [order A, order C, order E] ---> counting() ---> 3L
games: [order B, order D, order G] ---> counting() ---> 3L
toys : [order F]                 ---> counting() ---> 1L
   |
   v
Map<String, Long>
~~~

`groupingBy(classifier, downstream)` là một **collector**. Chính lời gọi `stream.collect(...)` mới là terminal tiêu thụ Stream. Kết quả Map chứa khóa là nhóm và giá trị là kết quả downstream. Phân biệt với:

~~~java
Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::department));
~~~

Khi bỏ downstream, `groupingBy(classifier)` có hiệu ứng tương đương dùng downstream `toList()`: kết quả là danh sách bản ghi theo nhóm. Nếu chỉ cần đếm hay tổng, đừng tự động thu toàn bộ danh sách rồi tính tiếp; downstream chuyên dụng thường biểu đạt yêu cầu rõ hơn và tránh phải giữ list của mọi phần tử.

## 2. `Collectors.counting()`: đếm bản ghi trong mỗi nhóm

Cú pháp:

~~~java
Map<String, Long> counts = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.counting()));
~~~

`counting()` có kiểu kết quả `Long`; đừng khai báo `Map<String, Integer>`. Nó đếm **số bản ghi** đã chuyển tới downstream, không đếm số nhóm và không tự loại phần tử trùng.

Nếu cùng một phòng ban có ba đơn, Map chứa khóa phòng ban đó với giá trị `3L`. Tổng số nhóm là `counts.size()`, khác tổng số đơn `counts.values().stream().mapToLong(Long::longValue).sum()`.

So sánh:

| Mục đích | Phép toán | Ý nghĩa |
| --- | --- | --- |
| Đếm tất cả bản ghi trong toàn Stream | `orders.stream().count()` | Một giá trị `long` |
| Đếm số bản ghi mỗi nhóm | `groupingBy(key, counting())` | `Map<K, Long>` |
| Đếm các nhóm có ít nhất một phần tử | `counts.size()` | Số khóa trong Map |
| Đếm các bản ghi thỏa điều kiện trong nhóm | `groupingBy(key, filtering(p, counting()))` | Nhóm gốc được giữ, có thể đếm 0 |
| Đếm phần tử phân biệt theo một khóa phụ | `groupingBy(key, mapping(subKey, toSet()))` rồi xem size | Cần nêu rõ quy tắc bằng nhau của khóa |

### `counting()` và đầu vào rỗng

Với `Stream.empty()`, `groupingBy(..., counting())` tạo Map rỗng: **không có nhóm nào để nhận giá trị 0**. Khi đã có một nhóm từ classifier, downstream counting đếm các phần tử của nhóm đó.

Nếu nghiệp vụ yêu cầu mọi nhóm dự kiến xuất hiện dù không có bản ghi, phải bổ sung các khóa dự kiến theo quy tắc riêng hoặc dùng cấu trúc dữ liệu quản lý tập nhóm cố định. `groupingBy` không tự tạo các nhóm không có phần tử.

## 3. `summingInt()`, `summingLong()`, `summingDouble()`: tính tổng theo nhóm

Nếu bản ghi có thuộc tính số, dùng downstream collector thích hợp:

~~~java
Map<String, Integer> quantityByDept = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.summingInt(Order::quantity)));

Map<String, Long> centsByDept = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.summingLong(Order::cents)));
~~~

Trong trường hợp đầu, `Order::quantity` trả `int`; `summingInt` chọn một số lượng nguyên cho mỗi bản ghi rồi cộng và trả `Integer`. Trường hợp hai, `Order::cents` trả `long`, nên `summingLong` cộng và trả `Long`.

Cả hai tránh thao tác trung gian kiểu `Stream<Integer>` hay `Stream<Long>` chỉ để tính một tổng. Không cần tự viết:

~~~java
// Nặng cấu trúc dữ liệu hơn nếu chỉ cần tổng:
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(Order::department));
// Sau đó duyệt lại từng List để tính sum.
~~~

Dùng downstream `summing...` nếu mục đích cuối cùng là một tổng theo nhóm. Dẫu vậy, chọn loại số phải chính xác theo miền nghiệp vụ.

| Collector | Hàm trích xuất | Giá trị Map | Cần lưu ý |
| --- | --- | --- | --- |
| `summingInt` | `ToIntFunction<T>` | `Integer` | Tổng có thể tràn `int` |
| `summingLong` | `ToLongFunction<T>` | `Long` | Tổng vẫn có thể tràn `long` |
| `summingDouble` | `ToDoubleFunction<T>` | `Double` | Sai số floating point, `NaN`, vô cực |

### Tránh tràn số bằng cách mở rộng trước khi cộng

Giả sử `quantity` là `int` nhưng số lượng cộng dồn có thể vượt `Integer.MAX_VALUE`:

~~~java
Map<String, Long> longQuantities = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.summingLong(o -> (long) o.quantity())));
~~~

Ép sang `long` **trước** phép cộng sẽ giúp tổng nằm trong miền `long`. Không cộng bằng `summingInt` rồi mới chuyển `Integer` thành `Long`, vì tràn số đã xảy ra trong phép cộng.

Với tiền tệ, ví dụ chọn `long cents` để tránh sai số nhị phân của `double`. Nếu miền giá trị vượt `long` hoặc cần quy tắc làm tròn phức tạp, `BigDecimal` cùng một phép giảm hợp lệ có thể phù hợp hơn; không chuyển tiền thành `double` chỉ vì có `summingDouble`.

## 4. `maxBy()` và `minBy()`: tìm phần tử đại diện cho từng nhóm

"Phần tử đại diện" phải được định nghĩa rõ: **lớn nhất theo doanh thu? nhỏ nhất theo số lượng? mới nhất theo thời gian?** `maxBy` và `minBy` nhận một `Comparator` để chọn phần tử cực trị.

~~~java
Comparator<Order> byCents = Comparator.comparingLong(Order::cents);

Map<String, Optional<Order>> maxByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.maxBy(byCents)));

Map<String, Optional<Order>> minByDepartment = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.minBy(byCents)));
~~~

Kết quả của `maxBy` và `minBy` là **`Optional<Order>`**, vì collector cực trị có hợp đồng xử lý đầu vào rỗng. Do đó Map có kiểu `Map<String, Optional<Order>>`, không phải `Map<String, Order>`.

Với `groupingBy` thông thường, một khóa chỉ có thể được tạo từ ít nhất một phần tử thực sự đi qua classifier, nên nhóm tương ứng thường không rỗng. Tuy nhiên, **giữ Optional là hợp đồng công khai của downstream collector**; không tự loại bỏ nó bằng ép kiểu.

### Khi có phần tử đồng hạng

Nếu comparator chỉ so số tiền, hai đơn có tiền bằng nhau được coi là ngang hạng. Việc đơn nào trở thành đại diện không nên là một giả định nghiệp vụ chưa được diễn đạt, đặc biệt khi chạy song song.

Thêm tiêu chí phụ rõ ràng:

~~~java
Comparator<Order> byCentsThenId = Comparator
        .comparingLong(Order::cents)
        .thenComparing(Order::id);
~~~

`maxBy(byCentsThenId)` chọn đơn có `cents` lớn nhất; nếu bằng, chọn `id` lớn nhất theo thứ tự tự nhiên của chuỗi. `minBy` dùng cùng comparator sẽ chọn tiền nhỏ nhất, nếu bằng sẽ chọn `id` nhỏ nhất.

Chỉ dùng `thenComparing` nếu tiêu chí phụ thực sự đúng nghiệp vụ; không dùng ID tăng dần để mặc định thay thế "đơn mới nhất" nếu ID không biểu diễn thời gian.

### Tìm bản ghi hay chỉ tìm số lớn nhất?

- Cần **giá trị lớn nhất**: có thể dùng `maxBy(Comparator.comparingLong(...))` rồi đọc trường, hoặc `mapping(Order::cents, maxBy(Long::compare))`.
- Cần **bản ghi chứa nhiều thuộc tính**: downstream `maxBy(comparator)` trực tiếp giữ lại `Order` phù hợp hơn.
- Cần **tất cả bản ghi đồng hạng**: `maxBy` chỉ trả một phần tử; phải thiết kế quy tắc khác (tìm giá trị cực trị rồi lọc bản ghi cùng mức, hoặc collector tích lũy danh sách đồng hạng).

Không nhầm `maxBy` với `Stream.max`: `stream.max(comparator)` là **terminal trên toàn bộ stream**, còn `Collectors.maxBy(comparator)` là **downstream collector** dùng bên trong `groupingBy`.

## 5. `Collectors.filtering()`: đếm có điều kiện mà vẫn giữ nhóm

Có hai cách rất dễ nhầm:

~~~java
// Chỉ nhóm những đơn đã thanh toán:
Map<String, Long> onlyPaidGroups = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::department, Collectors.counting()));

// Nhóm tất cả trước, rồi chỉ đếm những đơn đã thanh toán:
Map<String, Long> paidCountPerExistingGroup = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.filtering(Order::paid, Collectors.counting())));
~~~

**Khác biệt cốt lõi:** cách thứ nhất loại bản ghi trước khi classifier phân nhóm. Một phòng ban không có đơn thanh toán sẽ **không xuất hiện**. Cách thứ hai vẫn tạo khóa cho mọi phòng ban được gặp từ nguồn, rồi downstream filter chỉ chuyển các đơn thỏa điều kiện vào counting; nhóm không có đơn thanh toán vẫn có thể nhận **giá trị `0L`**.

Ví dụ nguồn có nhóm `toys` với một đơn chưa thanh toán:

~~~text
Lọc trước groupingBy:
{books=2, games=3}         // toys biến mất

groupingBy + filtering:
{books=2, games=3, toys=0} // toys vẫn có mặt
~~~

Để in kết quả theo thứ tự cố định trong thực tế, dùng overload có `TreeMap::new` như chương trình đầy đủ ở mục 9. Nếu dùng Map mặc định, không suy diễn thứ tự khi gọi `toString()`.

Đây cũng là minh họa vì sao một downstream operation có thể tạo giá trị rỗng/0 dù nhóm có phần tử nguồn. `filtering` (Java 9+) phù hợp để thu thập thống kê có điều kiện **trên tập khóa đã được hình thành**.

## 6. `mapping()` và collector lồng nhau khi cần chọn khóa/giá trị khác

`Collectors.mapping(mapper, downstream)` biến đổi **từng phần tử trong nhóm**, rồi chuyển giá trị đã biến đổi tới downstream. Nó hữu ích khi dữ liệu tổng hợp dựa trên khóa con.

Ví dụ muốn danh sách các mã đơn khác nhau trong từng phòng ban:

~~~java
Map<String, Set<String>> ids = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.mapping(Order::id, Collectors.toSet())));
~~~

`mapping` không làm thay đổi classifier ngoài: nhóm vẫn theo `department`, nhưng nội dung downstream là `id`. Khi chỉ cần tổng số bản ghi, dùng `counting` thay vì gom `Set` rồi `size`. Khi cần đếm **mã phân biệt**, Set mới có ý nghĩa; chú ý `toSet()` không cam kết thứ tự hay loại triển khai.

Muốn thống kê tổng số lượng theo phòng ban và trạng thái thanh toán có thể nhóm nhiều tầng:

~~~java
Map<String, Map<Boolean, Long>> nested = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.groupingBy(
                        Order::paid,
                        Collectors.summingLong(o -> (long) o.quantity()))));
~~~

Với nested grouping, key `Boolean` chỉ xuất hiện khi có bản ghi tương ứng. Nếu muốn luôn có cả `true` và `false` trong từng phòng ban thì cần một chính sách/default riêng; có thể cân nhắc `partitioningBy(Order::paid, downstream)` sau khi đã nhóm theo phòng ban.

## 7. `teeing()`: tính đếm và tổng trong một lần thu thập

Từ **Java 12**, `Collectors.teeing(downstream1, downstream2, merger)` phân phối mỗi phần tử cho hai downstream collectors và sau cùng ghép hai kết quả. Kết hợp với groupingBy, mỗi nhóm có thể có cả **số lượng bản ghi** và **tổng tiền**:

~~~java
record Summary(long count, long cents) {}

Map<String, Summary> reports = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Order::cents),
                        Summary::new)));
~~~

Đây là đoạn minh họa với `record Summary` đặt trong một lớp; `orders` là danh sách `Order` và cần import `Map`, `Collectors`.

`teeing` phù hợp khi cần hai thống kê độc lập nhưng muốn có một kết quả ghép trong một collector. Một số điểm cần nhớ:

1. Mỗi phần tử của nhóm được downstream thứ nhất và thứ hai xử lý, không có nghĩa `Stream` phải được tái sử dụng hai lần.
2. `Summary::new` nhận hai giá trị downstream theo đúng thứ tự `(count, cents)`; thứ tự tham số rất quan trọng nếu cùng là `long`.
3. Cả hai downstream đều phải an toàn theo hợp đồng khi kết hợp các kết quả song song; không nên truyền các accumulator tự tạo có side effect dùng chung.
4. Nếu cần nhiều chỉ số hơn hai, cân nhắc collector thống kê chuyên biệt hoặc một accumulator có hợp đồng rõ ràng, tránh lồng nhiều `teeing` khiến mã khó đọc.

Một lựa chọn khác với số nguyên là `summarizingInt(Order::quantity)`, trả `IntSummaryStatistics` có count, sum, min, max, average trong một kết quả. Khi dữ liệu yêu cầu cả cực trị **bản ghi** (không chỉ giá trị số), `maxBy(OrderComparator)` vẫn cần được diễn đạt riêng.

## 8. Kiểu Map, thứ tự khóa và null

### `groupingBy(classifier, downstream)` không cam kết Map cụ thể

Với overload hai tham số, Java không đảm bảo `HashMap`, thứ tự key, thread safety hoặc khả năng serializable của Map kết quả. Không viết test giả định nhóm sẽ in theo thứ tự chữ cái nếu không quy định Map factory.

Muốn Map có các khóa `String` theo thứ tự tự nhiên:

~~~java
Map<String, Long> countSortedByKey = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                TreeMap::new,
                Collectors.counting()));
~~~

Overload ba tham số gồm **classifier, mapFactory, downstream**. Ở đây `TreeMap::new` đặt hợp đồng thứ tự khóa; nếu khóa không hỗ trợ thứ tự tự nhiên hoặc cần quy tắc khác, dùng `TreeMap` với comparator phù hợp.

### Null classifier không được chấp nhận

`groupingBy` hiện thực hợp đồng **không chấp nhận classifier trả null**: điều đó dẫn đến `NullPointerException` khi phần tử như vậy được xử lý. Đừng dựa vào khả năng `HashMap` chứa null để đoán rằng `groupingBy` cũng chấp nhận khóa null.

Nếu phòng ban có thể thiếu, phải quyết định chính sách:

~~~java
Map<String, Long> withUnknown = orders.stream()
        .collect(Collectors.groupingBy(
                o -> o.department() == null ? "UNKNOWN" : o.department(),
                Collectors.counting()));
~~~

Đây là **đoạn minh họa**: có nguy cơ trùng khóa nếu `"UNKNOWN"` cũng là một phòng ban hợp lệ; trong ứng dụng thực tế cần chọn sentinel hoặc kiểu khóa rõ ràng hơn. Một phương án khác là lọc những bản ghi thiếu nhóm trước, nhưng chỉ khi nghiệp vụ cho phép bỏ chúng.

### Có thể trống toàn bộ nguồn

`orders.stream()` rỗng tạo Map rỗng. `groupingBy` không tự tạo các phòng ban có sẵn trong danh mục. Nếu báo cáo phải hiển thị nhóm không có đơn với count/tổng là 0, sau khi collect cần kết hợp với tập khóa danh mục gốc hoặc thiết kế một report có tập nhóm cố định.

## 9. Ví dụ hoàn chỉnh Java 17+ có stdout kiểm chứng

Lưu thành **`GroupMetricsDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupMetricsDemo {
    record Order(String id, String department, int quantity, long cents, boolean paid) {}
    record Summary(long count, long cents) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", "books", 2, 1200, true),
                new Order("B", "games", 1, 2500, true),
                new Order("C", "books", 3, 1600, false),
                new Order("D", "games", 4, 900, true),
                new Order("E", "books", 1, 2600, true),
                new Order("F", "toys", 5, 700, false),
                new Order("G", "games", 2, 2600, true)
        );

        Map<String, Long> counts = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.counting()));
        Map<String, Integer> units = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.summingInt(Order::quantity)));
        Map<String, Long> cents = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.summingLong(Order::cents)));

        Comparator<Order> byCentsThenId = Comparator
                .comparingLong(Order::cents).thenComparing(Order::id);
        Map<String, Optional<Order>> mostExpensive = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.maxBy(byCentsThenId)));

        Map<String, Long> paidCounts = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.filtering(Order::paid, Collectors.counting())));

        Map<String, Summary> summaries = orders.stream().collect(
                Collectors.groupingBy(Order::department, TreeMap::new,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingLong(Order::cents),
                                Summary::new)));

        System.out.println("counts=" + counts);
        System.out.println("units=" + units);
        System.out.println("cents=" + cents);
        System.out.println("paidCounts=" + paidCounts);
        System.out.println("summaries=" + summaries);
        mostExpensive.forEach((key, value) ->
                System.out.println("top " + key + "=" + value.orElseThrow().id()));
        System.out.println("noMissingKey=" + counts.containsKey("missing"));
    }
}
~~~

Biên dịch và chạy với **JDK 17** trở lên:

~~~bash
javac GroupMetricsDemo.java
java GroupMetricsDemo
~~~

Đầu ra chính xác:

~~~text
counts={books=3, games=3, toys=1}
units={books=6, games=7, toys=5}
cents={books=5400, games=6000, toys=700}
paidCounts={books=2, games=3, toys=0}
summaries={books=Summary[count=3, cents=5400], games=Summary[count=3, cents=6000], toys=Summary[count=1, cents=700]}
top books=E
top games=G
top toys=F
noMissingKey=false
~~~

Đây không phải là thứ tự tình cờ của Map: cả sáu Map đều dùng `TreeMap::new`, nên duyệt keys `books`, `games`, `toys` theo thứ tự tự nhiên của `String`. `mostExpensive.forEach` cũng lặp theo thứ tự đó.

Giải thích chi tiết:

- **`counts`**: books có ba đơn A, C, E; games có B, D, G; toys chỉ có F.
- **`units`**: số lượng books = 2+3+1=6; games = 1+4+2=7; toys = 5.
- **`cents`**: tổng tiền books = 1200+1600+2600=5400; games = 2500+900+2600=6000; toys = 700.
- **`paidCounts`**: toys xuất hiện với `0` do downstream filtering, dù không có đơn thanh toán; điều này khác filter trên Stream trước grouping.
- **`summaries`**: `teeing` thu cả `count` và `summingLong` rồi gộp thành `Summary`.
- **`mostExpensive`**: books chọn E (2600), games chọn G (2600), toys chọn F (700). Comparator dùng `id` làm tiêu chí phụ để giải quyết trường hợp ngang tiền.
- **`noMissingKey=false`**: Map không chứa nhóm chưa bao giờ xuất hiện trong dữ liệu.

Mỗi lần gọi `orders.stream()` tạo một Stream mới; một Stream đã chạy terminal `collect` không thể sử dụng lại cho một terminal khác.

## 10. Chọn phần tử đại diện và chính sách tie-breaking

Khái niệm "đại diện" phụ thuộc nghiệp vụ. Trong một nhóm có thể cần:

| Mục đích | Cách biểu diễn |
| --- | --- |
| Đơn giá trị cao nhất | `maxBy(Comparator.comparingLong(Order::cents))` |
| Đơn giá trị thấp nhất | `minBy(Comparator.comparingLong(Order::cents))` |
| Đơn nhiều hàng nhất | `maxBy(Comparator.comparingInt(Order::quantity))` |
| Đơn mới nhất | `maxBy(Comparator.comparing(Order::createdAt))` nếu `createdAt` thật sự có trong model |
| Đơn cao nhất, đồng hạng thì ID lớn nhất | `maxBy(comparingLong(...).thenComparing(...))` |
| Tất cả các đơn có cùng giá trị cao nhất | Cần collector/thuật toán giữ nhiều phần tử, `maxBy` đơn lẻ không đủ |

Mục `createdAt` ở bảng là **ý tưởng áp dụng trong model có trường thời gian**, không phải lời gọi chạy được trên `record Order` của ví dụ hiện tại.

Quan trọng: `Comparator` có thể xác định hai đối tượng bằng nhau trong thứ tự mà **không** khiến chúng bằng nhau theo `equals`. `maxBy` chỉ dùng comparator để chọn cực trị; nó không thực hiện phép loại trùng `distinct()`. Khi comparator thiếu tiêu chí phụ, kết quả chọn đại diện từ các phần tử đồng hạng có thể không phù hợp mong đợi, nhất là khi cách duyệt/song song thay đổi. Nếu phải chọn tất định, thêm tiêu chí phụ có thứ tự toàn phần phù hợp dữ liệu.

### Nếu muốn bỏ Optional trong kết quả

Một cách chuyển `Optional<Order>` thành `Order` là dùng `collectingAndThen`:

~~~java
Map<String, Order> topByDept = orders.stream().collect(
        Collectors.groupingBy(
                Order::department,
                Collectors.collectingAndThen(
                        Collectors.maxBy(byCentsThenId),
                        Optional::orElseThrow)));
~~~

Đây là **đoạn mã minh họa** dùng biến `orders` và `byCentsThenId` đã xác định. Vì `groupingBy` gọi downstream trên các nhóm có ít nhất một phần tử từ nguồn, `Optional` của cực trị trong trường hợp thông thường có giá trị. Tuy nhiên, nếu tự xây collector hay dùng biến thể có downstream lọc hết phần tử, Optional có thể rỗng; lúc đó `orElseThrow()` ném `NoSuchElementException`. Chọn fallback hoặc giữ Optional khi khả năng rỗng mang ý nghĩa nghiệp vụ.

## 11. Grouping, partitioning và nhóm nhiều tầng

`groupingBy` dùng classifier trả **khóa K bất kỳ**, ví dụ `String department`. `partitioningBy` chia theo một `Predicate` thành **hai phía `Boolean.TRUE` và `Boolean.FALSE`**:

~~~java
Map<Boolean, Long> paidUnpaid = orders.stream()
        .collect(Collectors.partitioningBy(
                Order::paid,
                Collectors.counting()));
~~~

Đoạn mã minh họa trên tạo Map với hai khóa true/false, kể cả khi một phía không có phần tử (count 0), theo hợp đồng partitioning. Đây là lựa chọn phù hợp nếu câu hỏi chính chỉ là "đã thanh toán hay chưa", không cần classifier nhiều giá trị.

Nếu cần vừa chia theo phòng ban vừa chia trạng thái:

~~~java
Map<String, Map<Boolean, Long>> byDeptAndPaid = orders.stream()
        .collect(Collectors.groupingBy(
                Order::department,
                Collectors.partitioningBy(
                        Order::paid,
                        Collectors.counting())));
~~~

Kết quả mỗi phòng ban sẽ có hai nhánh true/false theo `partitioningBy`. Đây là một cách giữ giá trị 0 trong một nhánh, khác với `groupingBy(Order::paid)` có thể không tạo nhánh absent.

Dùng grouping nhiều tầng khi chiều phân nhóm thực sự có giá trị; nếu chỉ cần một báo cáo đơn giản, tránh lồng ba bốn mức Map khiến downstream xử lý khó hiểu.

## 12. Các lỗi thường gặp

### Nhầm đếm bản ghi với đếm nhóm

`groupingBy(key, counting())` tạo `Map<K, Long>`. `map.size()` là số nhóm; `map.get(key)` là số bản ghi trong nhóm. Nếu muốn đếm tất cả phần tử, `stream.count()` không cần grouping.

### Dùng `summingInt` khi tổng vượt `int`

`summingInt` trả `Integer` và phép cộng dùng miền `int`. Nếu tổng lớn, dùng `summingLong(o -> (long) o.quantity())` trước khi cộng. Tiền nên chọn kiểu số theo giới hạn và độ chính xác của nghiệp vụ.

### Xem `maxBy` là bản ghi thay vì `Optional<Order>`

`Collectors.maxBy` trả `Optional<T>`. Vì vậy không thể khai báo `Map<K, T>` trừ khi thêm bước biến đổi hợp lệ, chẳng hạn `collectingAndThen` với cách xử lý empty rõ ràng.

### Thiếu quy tắc đồng hạng

`maxBy(Comparator.comparingLong(Order::cents))` không nêu cách chọn giữa hai đơn cùng tiền. Nếu quan trọng, bổ sung tiêu chí có tính tất định; nếu muốn mọi đơn đồng hạng, `maxBy` không phải collector đủ biểu đạt.

### Lọc trước rồi thắc mắc vì sao nhóm biến mất

`stream.filter(p).collect(groupingBy(...))` loại bản ghi trước khi tạo khóa. Nếu cần **mọi nhóm có trong nguồn** nhưng mỗi nhóm đếm chỉ những phần tử đạt điều kiện, dùng `groupingBy(key, filtering(p, counting()))`.

### Dựa vào thứ tự của Map mặc định

`groupingBy` mặc định không hứa thứ tự khóa hay loại Map. Nếu thứ tự quan trọng cho xuất báo cáo, cung cấp `TreeMap::new` hoặc loại Map phù hợp, hay sắp xếp khi trình bày.

### Đưa null vào classifier

`groupingBy` từ chối khóa null. Thiết kế quy tắc cho "không xác định" trước khi nhóm, hoặc báo lỗi dữ liệu theo hợp đồng.

### Tự thu List cho mọi nhóm chỉ để cộng số

`groupingBy(key)` trả `Map<K, List<T>>`, có thể giữ thêm nhiều tham chiếu. Nếu chỉ cần count/sum/max, downstream chuyên biệt làm mục đích rõ và thường tiết kiệm công đoạn hơn.

### Sử dụng accumulator có trạng thái chung trong parallel stream

~~~java
// Không dùng cách này:
// Map<String, Long> counts = new HashMap<>();
// orders.parallelStream().forEach(o ->
//         counts.merge(o.department(), 1L, Long::sum));
~~~

Ví dụ sai vì sửa `HashMap` không đồng bộ từ nhiều thread. Hãy để `Collectors.groupingBy` quản lý việc thu thập và kết hợp, hoặc dùng `groupingByConcurrent` khi phù hợp về thứ tự, dữ liệu và yêu cầu an toàn luồng. `groupingByConcurrent` là concurrent/unordered collector; không áp dụng máy móc khi cần giữ encounter order hoặc xác định đại diện theo thứ tự gặp.

### Nghĩ grouping tự tạo nhóm không có dữ liệu

Nhóm không xuất hiện trong nguồn sẽ không tự có khóa. Nếu báo cáo cần mọi phòng ban trong danh mục, bổ sung nhóm thiếu theo danh mục sau collect hoặc tạo cấu trúc báo cáo có tập khóa cố định.

## 13. Hiệu năng, bộ nhớ và kiểm thử

- **Đếm/tính tổng trực tiếp:** downstream `counting`/`summing...` giữ trạng thái tích lũy nhỏ cho mỗi nhóm, không bắt buộc giữ toàn bộ danh sách `Order` như `groupingBy(key)` mặc định.
- **Cực trị:** `maxBy`/`minBy` chỉ cần duy trì ứng viên hiện tại theo nhóm (trong các triển khai thông thường) và comparator phù hợp.
- **Số nhóm:** nếu nguồn có rất nhiều khóa khác nhau, Map và trạng thái nhóm vẫn có thể tốn bộ nhớ lớn. Grouping không làm dữ liệu "miễn phí".
- **Tính toán số:** `summingDouble` chịu sai số floating point; với tổng tiền chính xác chọn kiểu nguyên hoặc `BigDecimal` theo yêu cầu.
- **Song song:** collector quản lý accumulator và combiner, nhưng có chi phí hợp nhất Map/nhóm. Không giả định parallel stream luôn nhanh hơn tuần tự.
- **Kiểm thử:** kiểm tra dữ liệu rỗng, nhóm chỉ có một phần tử, nhóm có count 0 sau downstream filtering, giá trị số cực hạn, comparator có đồng hạng, khóa null và Map order mong muốn.

Đừng đặt hành vi ghi log, gửi email hay sửa dữ liệu chia sẻ vào classifier/downstream mapper chỉ để "tận dụng" pipeline. Chúng có thể được gọi theo cách triển khai hoặc song song khác nhau; tốt nhất là các hàm thuần hoặc không ảnh hưởng trạng thái bên ngoài.

## 14. Bảng chọn công cụ

| Yêu cầu | Downstream phù hợp | Kiểu Map thường thấy |
| --- | --- | --- |
| Đếm bản ghi mỗi nhóm | `counting()` | `Map<K, Long>` |
| Tổng số lượng `int` mỗi nhóm | `summingInt(getQuantity)` | `Map<K, Integer>` |
| Tổng số lượng không tràn `int` | `summingLong(x -> (long) getQuantity(x))` | `Map<K, Long>` |
| Tổng tiền `long` mỗi nhóm | `summingLong(getCents)` | `Map<K, Long>` |
| Trung bình `double` mỗi nhóm | `averagingDouble(getScore)` | `Map<K, Double>` |
| Bản ghi lớn nhất theo tiêu chí | `maxBy(comparator)` | `Map<K, Optional<T>>` |
| Bản ghi nhỏ nhất theo tiêu chí | `minBy(comparator)` | `Map<K, Optional<T>>` |
| Đếm theo predicate nhưng vẫn giữ nhóm | `filtering(predicate, counting())` | `Map<K, Long>` |
| Đếm và tính tổng cùng lúc | `teeing(counting(), summingLong(...), Summary::new)` | `Map<K, Summary>` |
| Nhóm theo khóa con khác | `mapping(mapper, downstream)` | `Map<K, R>` |
| Gom nhóm và trả các khóa có thứ tự | `groupingBy(key, TreeMap::new, downstream)` | `TreeMap<K, R>` |

**Tóm lại:** `groupingBy` xác định **khóa nhóm**, còn downstream collector xác định **phép tổng hợp trong mỗi nhóm**. Chọn `counting` để đếm, `summingInt/Long` để cộng, `maxBy/minBy` để chọn bản ghi theo comparator và `teeing` khi cần ghép hai chỉ số. Muốn báo cáo đúng và ổn định, phải xác định thêm chính sách **nhóm thiếu dữ liệu, khóa null, tràn số, đại diện đồng hạng và thứ tự xuất kết quả**.