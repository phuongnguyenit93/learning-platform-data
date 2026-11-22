# reduce và collect trong tổng hợp dữ liệu (Java Stream)

## 1. Bài toán và vị trí trong Stream pipeline

Trong ứng dụng thực tế, dữ liệu thường cần được **tổng hợp**: tính tổng doanh thu, tìm giá trị lớn nhất, đếm đơn hàng theo trạng thái, nhóm giao dịch theo khách hàng hoặc tạo một `Map` từ danh sách. Java Stream cung cấp hai phép toán kết thúc (terminal operations) cốt lõi:

- **`reduce`**: kết hợp các phần tử bằng một phép toán để tạo ra **một giá trị kết quả** như tổng, tích, cực đại hoặc một đối tượng bất biến mới.
- **`collect`**: gom các phần tử vào **cấu trúc hoặc kết quả tổng hợp**, thường dùng vùng chứa có thể thay đổi như `List`, `Set`, `Map` hoặc một `Collector` tính thống kê.

Ví dụ dòng xử lý `nguồn → filter → map → reduce/collect`: các bước `filter` và `map` là trung gian, còn `reduce`/`collect` kích hoạt việc duyệt và kết thúc pipeline. Sau một terminal operation, không được dùng lại cùng đối tượng `Stream`; hãy tạo stream mới từ nguồn nếu cần tính một kết quả khác.

**Chọn nhanh:** chỉ cần một giá trị và phép kết hợp không làm thay đổi đối tượng tích lũy → xét `reduce`; cần nhóm, đưa vào collection, đếm theo khóa hoặc kết hợp nhiều chỉ tiêu → dùng `collect` và `Collectors`. Với tổng/đếm đơn giản, ưu tiên phép chuyên dụng như `mapToInt(...).sum()`, `count()`, `min()`, `max()` khi biểu đạt rõ ràng hơn.

## 2. `reduce`: phép gộp trên giá trị

Phép gộp phải tuân theo quy tắc **kết hợp được** (associative): `f(f(a,b),c)` cho cùng kết quả ngữ nghĩa với `f(a,f(b,c))`. Điều này quan trọng vì Stream có thể chia dữ liệu thành nhiều phần khi chạy song song; thứ tự chia và ghép không nhất thiết giống cách duyệt tuần tự.

### 2.1. Không có giá trị khởi tạo: `Optional<T> reduce(BinaryOperator<T>)`

~~~java
Optional<Integer> highest = Stream.of(4, 9, 2).reduce(Integer::max);
int result = highest.orElse(0); // 9

Optional<Integer> absent = Stream.<Integer>empty().reduce(Integer::max);
// absent == Optional.empty()
~~~

Kết quả kiểu `Optional<T>` vì stream có thể rỗng. Không gọi `get()` khi chưa biết có giá trị; dùng `orElse`, `orElseGet` hoặc `ifPresent` theo yêu cầu nghiệp vụ. Với stream rỗng, dạng này trả `Optional.empty()`.

### 2.2. Có giá trị khởi tạo: `T reduce(T identity, BinaryOperator<T>)`

~~~java
int sum = Stream.of(4, 9, 2).reduce(0, Integer::sum); // 15
int product = Stream.of(4, 9, 2).reduce(1, (a, b) -> a * b); // 72
int emptySum = Stream.<Integer>empty().reduce(0, Integer::sum); // 0
~~~

`identity` phải là **phần tử trung hòa** của phép kết hợp: với phép cộng là `0`; với phép nhân là `1`. Kết quả của stream rỗng chính là `identity`. Không chọn tùy tiện, chẳng hạn khởi tạo tổng bằng `10` có thể khiến kết quả sai, đặc biệt trên stream song song vì các nhánh đều có thể dùng giá trị khởi tạo.

Lưu ý: cộng/trừ số nguyên có nguy cơ tràn kiểu; trừ và chia không có tính kết hợp cần thiết cho phép `reduce` tổng quát. Với số thực dấu phẩy động, thứ tự tính còn có thể làm thay đổi chút ít kết quả do làm tròn.

### 2.3. Đổi kiểu kết quả: `<U> U reduce(U identity, BiFunction<U,T,U> accumulator, BinaryOperator<U> combiner)`

- `identity`: giá trị trung hòa của kết quả kiểu `U`.
- `accumulator`: kết hợp kết quả tạm kiểu `U` với một phần tử nguồn kiểu `T`.
- `combiner`: ghép hai kết quả tạm kiểu `U` khi pipeline được tách phần. Nó phải tương thích với `identity` và `accumulator`.

~~~java
int totalCharacters = Stream.of("Java", "API")
    .reduce(0, (length, word) -> length + word.length(), Integer::sum);
// totalCharacters = 7
~~~

Ở đây phần tử đầu vào là `String` còn kết quả là `Integer`. Tuy nhiên, cho bài toán này cách dưới đây thường ngắn gọn, dễ tối ưu hơn:

~~~java
int totalCharacters = Stream.of("Java", "API")
    .mapToInt(String::length)
    .sum(); // 7
~~~

### 2.4. Khi nào `reduce` thực sự phù hợp?

- Cộng các giá trị bất biến, ví dụ `BigDecimal`: `amounts.reduce(BigDecimal.ZERO, BigDecimal::add)`.
- Lấy giá trị tốt nhất bằng phép kết hợp có tính kết hợp, ví dụ `reduce(BigDecimal::max)`.
- Tự định nghĩa phép gộp bất biến khi API chuyên dụng chưa đủ.

**Không dùng `reduce` để thay đổi một `ArrayList`, `HashMap` hay `StringBuilder` đang tích lũy.** Dạng `reduce` yêu cầu phép kết hợp thuần túy về mặt trạng thái; dùng vùng chứa có thể thay đổi dễ làm hỏng kết quả khi chạy song song. Với kiểu dữ liệu đó, hãy dùng `collect`.

## 3. `collect`: phép tổng hợp sử dụng vùng chứa

### 3.1. Hai cách gọi

**Cách phổ biến — `collect(Collector)`:**

~~~java
List<String> names = Stream.of("Java", "Stream")
    .collect(Collectors.toList());

Map<Integer, List<String>> byLength = Stream.of("Java", "API", "Stream")
    .collect(Collectors.groupingBy(String::length));
~~~

`Collectors` cung cấp các bộ tổng hợp chuẩn; `groupingBy` phân loại phần tử theo khóa rồi dùng bộ tổng hợp con (downstream collector) cho từng nhóm.

**Dạng ba tham số — `collect(supplier, accumulator, combiner)`:**

~~~java
List<String> names = Stream.of("Java", "Stream")
    .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
// names = [Java, Stream]
~~~

`supplier` tạo vùng chứa mới; `accumulator` thêm phần tử vào vùng chứa; `combiner` hợp nhất hai vùng chứa. Khác với `reduce`, việc *thay đổi vùng chứa nội bộ* là đúng mục đích của `collect`. Trên stream song song, thư viện có thể tạo các vùng chứa tạm độc lập rồi ghép chúng. Không tự chia sẻ một `ArrayList` bên ngoài cho nhiều luồng thao tác.

### 3.2. Hiểu cấu trúc của một `Collector`

Một collector tổng quát có năm thành phần ý nghĩa: **supplier** tạo trạng thái tích lũy, **accumulator** nhận phần tử, **combiner** ghép trạng thái, **finisher** biến trạng thái thành kết quả và **characteristics** mô tả đặc tính (ví dụ thứ tự, tính đồng thời). Khi dùng `Collectors.groupingBy`, `counting` hoặc `reducing`, ta tận dụng các collector được định nghĩa sẵn thay vì tự viết toàn bộ cơ chế này.

## 4. Những công thức tổng hợp đang được dùng rộng rãi

| Nhu cầu | Biểu thức/Collector | Điều cần nhớ |
| --- | --- | --- |
| Tính tổng số nguyên | `mapToInt(f).sum()`, `Collectors.summingInt(f)` | `summingInt` tiện làm downstream của `groupingBy`. |
| Đếm số phần tử | `count()` hoặc `Collectors.counting()` | `counting` rất hữu ích để đếm theo nhóm. |
| Trung bình/thống kê | `averagingInt(f)`, `summarizingInt(f)` | `IntSummaryStatistics` chứa count, sum, min, max, average; dùng `long` hoặc `BigDecimal` nếu miền dữ liệu yêu cầu. |
| Tạo danh sách | `Collectors.toList()` | Không có bảo đảm về kiểu triển khai hoặc khả năng sửa danh sách trả về. |
| Cần `ArrayList` có thể sửa | `Collectors.toCollection(ArrayList::new)` | Yêu cầu về kiểu/vùng chứa được thể hiện tường minh. |
| Loại trùng | `Collectors.toSet()` | Không có bảo đảm thứ tự duyệt; nếu cần thứ tự, chọn `toCollection(LinkedHashSet::new)`. |
| Ghép chuỗi | `Collectors.joining(", ")` | Thường rõ ràng và hiệu quả hơn cộng chuỗi lặp lại bằng `reduce`. |
| Nhóm theo thuộc tính | `groupingBy(classifier)` | Trả `Map<K,List<T>>`; không mặc định bảo đảm thứ tự khóa. |
| Chia theo điều kiện đúng/sai | `partitioningBy(predicate)` | Có cả hai khóa `true` và `false`, kể cả khi một phía rỗng. |
| Đổi thành bản đồ khóa/giá trị | `toMap(keyMapper, valueMapper, mergeFunction)` | Có thể trùng khóa; cần quyết định cách gộp. |

### 4.1. Tổng hợp theo nhóm với downstream collector

Các đoạn sau giả sử có `List<OrderLine> lines`; mỗi `OrderLine` có `category()` và `quantity()` như chương trình hoàn chỉnh ở mục 5.

~~~java
Map<String, Long> numberOfLinesByCategory = lines.stream()
    .collect(Collectors.groupingBy(
        OrderLine::category,
        Collectors.counting()
    ));

Map<String, Integer> unitsByCategory = lines.stream()
    .collect(Collectors.groupingBy(
        OrderLine::category,
        Collectors.summingInt(OrderLine::quantity)
    ));

Map<String, IntSummaryStatistics> statsByCategory = lines.stream()
    .collect(Collectors.groupingBy(
        OrderLine::category,
        Collectors.summarizingInt(OrderLine::quantity)
    ));
~~~

Điểm mạnh ở đây: phần *phân loại* (`groupingBy`) và phần *tổng hợp mỗi nhóm* (`counting`, `summingInt`, `summarizingInt`) tách biệt, dễ thay đổi độc lập. Có thể dùng `mapping` làm downstream để chỉ lấy trường cần thiết.

### 4.2. Trùng khóa khi chuyển sang `Map`

Nếu hai giao dịch có cùng mã sản phẩm, lời gọi `toMap(OrderLine::product, OrderLine::quantity)` **không tự cộng số lượng**: nó sẽ ném `IllegalStateException` khi gặp khóa trùng. Phải xác định quy tắc hợp nhất:

~~~java
Map<String, Integer> quantityByProduct = lines.stream()
    .collect(Collectors.toMap(
        OrderLine::product,
        OrderLine::quantity,
        Integer::sum
    ));
~~~

`Integer::sum` cộng số lượng của các dòng trùng khóa. Nếu cần sắp xếp khóa, truyền thêm `TreeMap::new` ở tham số thứ tư; nếu cần thứ tự thêm vào, cân nhắc `LinkedHashMap::new` cùng điều kiện encounter order phù hợp. Không suy ra thứ tự hiển thị từ `HashMap` mặc định.

### 4.3. Danh sách có thể sửa và danh sách bất biến trên JDK hiện đại

`Collectors.toList()` đã có từ Java 8 nhưng **không cam kết** danh sách có thể sửa. Nếu thực sự cần sửa sau khi collect, dùng `Collectors.toCollection(ArrayList::new)`. Trên JDK 16+, `stream.toList()` trả danh sách **không thể sửa**, khác với việc giả định `Collectors.toList()` luôn trả `ArrayList`; hãy chọn API dựa trên yêu cầu, không dựa vào hành vi tình cờ của một phiên bản JDK.

## 5. Ví dụ hoàn chỉnh: tổng hợp dữ liệu bán hàng

Ta có bốn dòng bán hàng; cần tổng số lượng, doanh thu, dòng lớn nhất, doanh thu/đếm theo nhóm, số lượng theo sản phẩm và số dòng vượt ngưỡng. Chương trình sau dùng **cú pháp và Stream API tương thích Java 8**, đồng thời biên dịch/chạy được bằng JDK 17+.

Lưu nội dung vào tệp **StreamAggregationDemo.java**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StreamAggregationDemo {
    static final class OrderLine {
        private final String category;
        private final String product;
        private final int quantity;
        private final BigDecimal unitPrice;

        OrderLine(String category, String product, int quantity, String unitPrice) {
            this.category = category;
            this.product = product;
            this.quantity = quantity;
            this.unitPrice = new BigDecimal(unitPrice);
        }

        String category() { return category; }
        String product() { return product; }
        int quantity() { return quantity; }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        List<OrderLine> lines = Arrays.asList(
            new OrderLine("Book", "Java", 2, "150.00"),
            new OrderLine("Book", "SQL", 1, "100.00"),
            new OrderLine("Course", "Stream", 3, "80.00"),
            new OrderLine("Book", "Java", 1, "150.00")
        );

        int totalUnits = lines.stream()
            .mapToInt(OrderLine::quantity)
            .sum();

        BigDecimal totalRevenue = lines.stream()
            .map(OrderLine::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        Optional<BigDecimal> largestLine = lines.stream()
            .map(OrderLine::amount)
            .reduce(BigDecimal::max);

        Map<String, BigDecimal> revenueByCategory = lines.stream()
            .collect(Collectors.groupingBy(
                OrderLine::category,
                TreeMap::new,
                Collectors.reducing(
                    BigDecimal.ZERO, OrderLine::amount, BigDecimal::add
                )
            ));

        Map<String, Long> lineCountByCategory = lines.stream()
            .collect(Collectors.groupingBy(
                OrderLine::category,
                TreeMap::new,
                Collectors.counting()
            ));

        Map<String, Integer> unitsByProduct = lines.stream()
            .collect(Collectors.toMap(
                OrderLine::product,
                OrderLine::quantity,
                Integer::sum,
                TreeMap::new
            ));

        List<String> distinctProducts = lines.stream()
            .map(OrderLine::product)
            .distinct()
            .collect(Collectors.toCollection(ArrayList::new));

        Map<Boolean, Long> linesOver200 = lines.stream()
            .collect(Collectors.partitioningBy(
                line -> line.amount().compareTo(new BigDecimal("200.00")) > 0,
                Collectors.counting()
            ));

        System.out.println("Tong so luong: " + totalUnits);
        System.out.println("Tong doanh thu: " + totalRevenue);
        System.out.println("Gia tri dong lon nhat: " + largestLine.orElse(BigDecimal.ZERO));
        System.out.println("Doanh thu theo nhom: " + revenueByCategory);
        System.out.println("So dong theo nhom: " + lineCountByCategory);
        System.out.println("So luong theo san pham: " + unitsByProduct);
        System.out.println("Danh sach san pham: " + distinctProducts);
        System.out.println("So dong > 200: " + linesOver200.get(true));
        System.out.println("So dong <= 200: " + linesOver200.get(false));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 StreamAggregationDemo.java
java StreamAggregationDemo
```

Kết quả:

```text
Tong so luong: 7
Tong doanh thu: 790.00
Gia tri dong lon nhat: 300.00
Doanh thu theo nhom: {Book=550.00, Course=240.00}
So dong theo nhom: {Book=3, Course=1}
So luong theo san pham: {Java=3, SQL=1, Stream=3}
Danh sach san pham: [Java, SQL, Stream]
So dong > 200: 2
So dong <= 200: 2
```

**Giải thích các điểm trọng tâm:**

1. `mapToInt(...).sum()` tính tổng số lượng bằng primitive stream, phù hợp hơn `reduce(0, Integer::sum)` cho trường hợp đơn giản.
2. `map(OrderLine::amount).reduce(BigDecimal.ZERO, BigDecimal::add)` cộng tiền theo số thập phân chính xác từ chuỗi giá, tránh sai số nhị phân kiểu `double` trong nghiệp vụ tiền tệ.
3. `reduce(BigDecimal::max)` trả `Optional<BigDecimal>`; trường hợp danh sách rỗng được xử lý rõ bằng `orElse`.
4. `groupingBy(..., TreeMap::new, reducing(...))` vừa nhóm theo loại vừa cộng tiền từng loại; `TreeMap` bảo đảm thứ tự khóa trong output ví dụ.
5. `toMap(..., Integer::sum, TreeMap::new)` xử lý trùng sản phẩm đúng quy tắc cộng số lượng; `partitioningBy` tạo đúng hai nhánh theo ngưỡng.

Chương trình tạo **stream mới từ `lines` cho mỗi phép tổng hợp**. Điều này hợp lệ; ngược lại, giữ một biến `Stream` rồi gọi hai terminal operations liên tiếp trên biến đó sẽ gây `IllegalStateException`.

## 6. Tính đúng đắn, thực thi song song và các lỗi thường gặp

### 6.1. Tính kết hợp, tính trung hòa và trạng thái bên ngoài

Đối với `reduce`, phép gộp phải kết hợp được; `identity` phải trung hòa; lambda không được phụ thuộc vào hay thay đổi trạng thái bên ngoài. Với dạng ba tham số, `combiner` còn phải ghép kết quả tạm tương thích với cách `accumulator` xử lý phần tử. Chẳng hạn cộng số nguyên phù hợp; trừ tuần tự không thể tùy tiện thay bằng phép giảm song song vì cách ghép các nhóm làm thay đổi đáp án.

**Sai về ý tưởng:** dùng `reduce` để thêm phần tử trực tiếp vào cùng một `ArrayList` và trả lại chính danh sách đó. Điều này biến phép giảm thành thay đổi trạng thái chia sẻ và có thể nhân đôi/mất dữ liệu khi chạy song song.

**Đúng:**

```java
List<Integer> values = Stream.of(1, 2, 3)
    .collect(Collectors.toCollection(ArrayList::new));
```

Nếu buộc phải tự viết collector, supplier phải tạo vùng chứa mới, accumulator cập nhật vùng chứa được cấp và combiner hợp nhất chính xác các vùng chứa; không dùng biến danh sách tĩnh/global để gom kết quả.

### 6.2. Không phải cứ `parallelStream()` là nhanh hơn

- Phép gom bản đồ bằng `groupingBy` trên stream song song có chi phí hợp nhất các `Map`; với dữ liệu nhỏ, chạy tuần tự thường đơn giản và có thể nhanh hơn.
- `groupingByConcurrent` có ích trong tình huống phù hợp với map concurrent và không cần bảo toàn thứ tự phần tử; nó không phải thay thế mặc định cho `groupingBy`.
- Đầu vào, lambda và collector phải đáp ứng yêu cầu **non-interfering** (không sửa nguồn dữ liệu trong khi pipeline đang chạy) và thường là **stateless**. Đừng cho các lambda cùng ghi vào danh sách hoặc biến đếm bên ngoài.
- Nếu cần thứ tự đầu ra ổn định, cần chọn nguồn có encounter order, collector/cấu trúc có hợp đồng thứ tự tương ứng và tránh phụ thuộc thứ tự thực thi của tác vụ song song.

Chỉ chuyển sang xử lý song song khi có dữ liệu và phép đo hiệu năng đủ thuyết phục; kiểm tra độ đúng trước và sau.

### 6.3. Độ chính xác, dữ liệu rỗng, trùng khóa và `null`

- **Tiền tệ:** dùng `BigDecimal` tạo từ chuỗi hoặc giá trị thập phân đáng tin cậy, quy định cách làm tròn theo nghiệp vụ nếu có phép chia; không xem `double` là kiểu tiền tệ chính xác.
- **Tập rỗng:** `reduce(accumulator)` trả `Optional.empty()`; `reduce(identity, accumulator)` trả `identity`; `count()` trả `0`. Với nhóm, kết quả có thể là map rỗng. Thiết kế giá trị mặc định theo ý nghĩa nghiệp vụ.
- **Khóa trùng:** `Collectors.toMap` hai đối số báo lỗi nếu tạo trùng khóa; cần merge function như `Integer::sum` hoặc chính sách khác do nghiệp vụ quy định.
- **Kết quả collection:** không giả định `Collectors.toList()` luôn sửa được, có thứ tự đặc biệt ngoài hợp đồng, hoặc luôn là `ArrayList`; dùng `toCollection` khi cần kiểu cụ thể.
- **Giá trị `null`:** quyết định chính sách lọc, thay thế hoặc từ chối `null` trước khi tổng hợp; không mặc nhiên cho rằng mọi collector hoặc phép `reduce` chấp nhận `null`.
- **Làm tròn/tràn số:** `summingInt` có thể tràn `int`; cộng `double` có thể khác nhau do thứ tự phép tính. Với số lượng rất lớn cân nhắc `long` và các quy tắc kiểm tra tràn phù hợp.
- **Chi phí bộ nhớ:** `collect(toList())` lưu các phần tử đầu ra; nếu chỉ cần tổng/đếm, dùng phép thống kê trực tiếp để tránh tạo danh sách trung gian.

## 7. Bảng quyết định và bài tự kiểm tra

| Tình huống | Lựa chọn rõ ràng |
| --- | --- |
| Tổng trường số nguyên trên toàn bộ stream | `mapToInt(f).sum()` (hoặc `mapToLong` nếu phù hợp) |
| Cộng `BigDecimal` | `map(f).reduce(BigDecimal.ZERO, BigDecimal::add)` |
| Lấy giá trị lớn nhất có thể thiếu | `max(comparator)` hoặc `reduce(BinaryOperator)`, xử lý `Optional` |
| Lấy `List`, `Set` hoặc `Map` | `collect` với collector tương ứng |
| Đếm/tổng theo nhóm | `groupingBy(key, counting/summingInt/reducing)` |
| Hai nhóm theo điều kiện Boolean | `partitioningBy(predicate, downstream)` |
| Tạo map có khóa trùng | `toMap(key, value, mergeFunction)` |

Tự kiểm tra:

1. Với stream rỗng, hai biểu thức `reduce(Integer::sum)` và `reduce(0, Integer::sum)` khác nhau thế nào? **Đáp án:** biểu thức thứ nhất trả `Optional.empty()`, biểu thức thứ hai trả số `0`.
2. Danh sách sản phẩm chứa hai phần tử cùng mã `"A"` có số lượng `2` và `3`. `toMap(code, quantity)` xử lý thế nào? **Đáp án:** lỗi trùng khóa; thêm merge function `Integer::sum` cho kết quả `A → 5`.
3. Vì sao `reduce(0, (a,b) -> a-b)` không thích hợp cho tổng hợp song song? **Đáp án:** phép trừ không kết hợp được; chia nhóm và ghép lại có thể tạo kết quả khác nhau.

## 8. Tài liệu API chính thức

- [`Stream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): đặc tả `reduce`, `collect`, tính kết hợp, phép kết thúc và `Stream.toList()`.
- [`Collectors` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toMap`, `groupingBy`, `partitioningBy`, `reducing` và các collector thống kê.
- [`java.util.stream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): quy tắc non-interference, reduction, concurrency và ordering.
