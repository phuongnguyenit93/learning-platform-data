# Chuyển sang Stream đối tượng bằng `boxed` và `mapToObj`

## 1. Khi nào cần rời khỏi primitive stream?

Java Stream API có ba loại luồng chuyên biệt để xử lý số nguyên thủy:

- `IntStream` chứa giá trị `int`.
- `LongStream` chứa giá trị `long`.
- `DoubleStream` chứa giá trị `double`.

Các primitive stream cho phép viết pipeline khai báo với `filter`, `map`, `reduce`, `sum`, `average`, `summaryStatistics` mà thường không phải đóng gói mỗi số vào một object. Tuy vậy, nhiều bước xử lý lại cần **kiểu đối tượng**: đưa số vào `List<Integer>`, tạo bản ghi DTO, chuyển từng số thành chuỗi, hoặc dùng các `Collector` như `groupingBy`.

Khi ấy, hai phương thức quan trọng là:

- **`boxed()`**: đóng gói mỗi giá trị nguyên thủy thành wrapper tương ứng (`Integer`, `Long`, `Double`).
- **`mapToObj(mapper)`**: dùng một hàm biến từng giá trị nguyên thủy thành **một đối tượng thuộc kiểu tùy chọn**.

Ví dụ đầu tiên:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 4)
    .boxed()
    .toList();
// [1, 2, 3, 4]

List<String> labels = IntStream.rangeClosed(1, 4)
    .mapToObj(number -> "Mã-" + number)
    .toList();
// [Mã-1, Mã-2, Mã-3, Mã-4]
```

Hai pipeline bắt đầu từ `IntStream`, nhưng kết thúc bằng `Stream<Integer>` và `Stream<String>` trước khi gọi `toList()`.

Sau bài này, bạn sẽ đọc được chữ ký của các phép chuyển, lựa chọn đúng điểm chuyển kiểu, kết hợp với `collect` và grouping, đồng thời nhận diện chi phí boxing, tính lười, trạng thái và các giới hạn về số học hoặc hiệu năng.

## 2. Nhận diện kiểu của pipeline trước và sau khi chuyển

Các kiểu luồng thường gặp trong chương **Stream kiểu nguyên thủy**:

| Luồng ban đầu | Kiểu phần tử | Sau `boxed()` | Ví dụ `mapToObj` |
| --- | --- | --- | --- |
| `IntStream` | `int` | `Stream<Integer>` | `Stream<String>`, `Stream<Item>` |
| `LongStream` | `long` | `Stream<Long>` | `Stream<BigInteger>`, `Stream<Invoice>` |
| `DoubleStream` | `double` | `Stream<Double>` | `Stream<String>`, `Stream<Measurement>` |

Sơ đồ:

```text
IntStream (int)
   │
   ├── boxed() ──────────────> Stream<Integer>
   │
   ├── mapToObj(n -> "...") ─> Stream<String>
   │
   └── mapToObj(n -> new R(n)) ─> Stream<R>
                                  │
                                  └── collect(...), toList(), groupingBy(...)
```

Hãy lưu ý:

1. `boxed()` **không** trả về `List<Integer>`; nó trả về một `Stream<Integer>` còn cần terminal operation.
2. `mapToObj` **không** tự thu thập kết quả vào collection; nó tạo một `Stream<U>`.
3. `IntStream` có `toArray()` trả `int[]` nhưng **không có** phương thức `toList()`. Để có `List<Integer>`, thường dùng `boxed().toList()`.
4. Sau khi chuyển thành object stream, các phép `map`, `filter`, `flatMap`, `collect(Collector)` của `Stream<T>` hoạt động theo kiểu đối tượng.

Ví dụ theo dõi kiểu ngay trong code:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

IntStream source = IntStream.range(0, 3); // int: 0, 1, 2
Stream<Integer> objects = source.boxed(); // Integer: 0, 1, 2

System.out.println(objects.toList());    // [0, 1, 2]
// Không thể dùng lại source: pipeline đã được tiêu thụ.
```

`IntStream.range(startInclusive, endExclusive)` lấy đầu và loại cuối; `rangeClosed(a, b)` bao gồm cả hai đầu khi có phần tử trong phạm vi.

## 3. `boxed()`: đóng gói giá trị, không đổi ý nghĩa dữ liệu

Chữ ký của các phương thức:

```java
// Trên IntStream:
Stream<Integer> boxed()

// Trên LongStream:
Stream<Long> boxed()

// Trên DoubleStream:
Stream<Double> boxed()
```

`boxed()` là **intermediate operation** (phép toán trung gian) dùng để tạo object stream chứa wrapper của các giá trị nguyên thủy.

### 3.1. Từ `IntStream` thành `List<Integer>`

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> scores = IntStream.of(70, 90, 80)
    .boxed()
    .toList();

System.out.println(scores); // [70, 90, 80]
```

Ở JDK 16 trở lên, `Stream.toList()` tạo danh sách **không thể sửa đổi**; gọi `scores.add(100)` ném `UnsupportedOperationException`. Nếu cần collection có thể sửa đổi theo hợp đồng riêng, chỉ rõ loại collection:

```java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<Integer> mutableScores = IntStream.of(70, 90, 80)
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

mutableScores.add(100); // Hợp lệ.
```

`Collectors.toList()` cũng là một lựa chọn để thu thập nhưng **không cam kết** loại danh sách, tính có thể sửa đổi hoặc khả năng tuần tự hóa. Đừng dựa vào triển khai hiện tại của nó để thiết kế hợp đồng API.

### 3.2. Từ `LongStream` và `DoubleStream`

```java
import java.util.List;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

List<Long> ids = LongStream.of(10L, 20L, 30L)
    .boxed()
    .toList();

List<Double> temperatures = DoubleStream.of(21.5, 23.0, 20.75)
    .boxed()
    .toList();

System.out.println(ids);          // [10, 20, 30]
System.out.println(temperatures); // [21.5, 23.0, 20.75]
```

`boxed()` giữ **giá trị số** và chuyển cách biểu diễn sang wrapper; nó không định dạng theo locale, không làm tròn, không gắn đơn vị và không kiểm tra miền giá trị. Nếu bài toán cần các thao tác đó, hãy dùng một mapper tường minh bằng `mapToObj` hoặc một bước biến đổi trước đó.

### 3.3. Vì sao gọi là boxing?

`int` là kiểu nguyên thủy, trong khi `Integer` là object wrapper. Việc chuyển:

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(primitive);
int again = wrapper.intValue();
```

được gọi lần lượt là **boxing** và **unboxing**. Java có thể thực hiện tự động (autoboxing/unboxing) ở vị trí cần thiết. `IntStream.boxed()` là cách chuyển *trên cả dòng dữ liệu* được định nghĩa rõ trong API.

Không nên so sánh wrapper bằng `==` để kiểm tra bằng giá trị: `==` giữa hai object so sánh tham chiếu và có thể chịu ảnh hưởng cơ chế cache. Hãy dùng `equals` hoặc unbox để so sánh giá trị; với dữ liệu có thể bằng `null`, xem xét chính sách null trước khi unbox.

## 4. `mapToObj`: ánh xạ số thành đối tượng tùy ý

Chữ ký tương ứng:

```java
// IntStream:
<U> Stream<U> mapToObj(IntFunction<? extends U> mapper)

// LongStream:
<U> Stream<U> mapToObj(LongFunction<? extends U> mapper)

// DoubleStream:
<U> Stream<U> mapToObj(DoubleFunction<? extends U> mapper)
```

`U` là kiểu đối tượng mới do trình biên dịch suy luận. `IntFunction<U>` nhận một `int` và trả đối tượng `U`, `LongFunction<U>` nhận `long`, còn `DoubleFunction<U>` nhận `double`. Khi mapper được đánh giá, mỗi phần tử nguồn tạo **một giá trị kết quả**, kể cả khi giá trị ấy là `null`.

### 4.1. Biến số thành chuỗi có ý nghĩa

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(index -> "Trang " + index)
    .toList();

System.out.println(labels); // [Trang 1, Trang 2, Trang 3]
```

Nếu dùng `boxed().map(...)`, ta vẫn tạo được kết quả nhưng việc chuyển sang wrapper chỉ là bước trung gian:

```java
List<String> alsoLabels = IntStream.rangeClosed(1, 3)
    .boxed()
    .map(index -> "Trang " + index)
    .toList();
```

Về ý nghĩa, hai cách có cùng kết quả. `mapToObj` thể hiện trực tiếp phép `int → String` và không đòi hỏi boxing thành `Integer` như một bước API riêng. Điều này có thể giảm chi phí trung gian, dù mức tối ưu thực tế tùy JDK và JVM.

### 4.2. Biến số thành record/DTO

```java
import java.util.List;
import java.util.stream.IntStream;

record PageLink(int pageNumber, String path) {}

List<PageLink> links = IntStream.rangeClosed(1, 3)
    .mapToObj(page -> new PageLink(page, "/catalog?page=" + page))
    .toList();

System.out.println(links.get(1));
// PageLink[pageNumber=2, path=/catalog?page=2]
```

Điểm mạnh của `mapToObj` là **kiểu kết quả do nghiệp vụ quyết định**. Thay vì bọc số rồi tự phân tích chúng ở nhiều nơi, có thể tạo đối tượng được đặt tên, có trường hợp lệ và thuận tiện cho xử lý phía sau.

### 4.3. Ánh xạ `long` và `double`

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

List<String> orderIds = LongStream.of(101L, 102L)
    .mapToObj(id -> "ORD-" + id)
    .toList();
// [ORD-101, ORD-102]

record Measurement(double value, String unit) {}

List<Measurement> lengths = DoubleStream.of(2.5, 3.25)
    .mapToObj(value -> new Measurement(value, "m"))
    .toList();

List<String> formatted = DoubleStream.of(2.5, 3.25)
    .mapToObj(value -> String.format(Locale.ROOT, "%.2f m", value))
    .toList();
// [2.50 m, 3.25 m]
```

Ví dụ định dạng dùng `Locale.ROOT` để đầu ra có dấu thập phân nhất quán. Với giá tiền, số thập phân nhị phân `double` có thể gây sai số; cân nhắc lưu số tiền nguyên đơn vị nhỏ nhất (`long` cent/VND đồng) hoặc dùng `BigDecimal` và quy tắc làm tròn rõ ràng.

### 4.4. Tham chiếu phương thức

Khi có một phương thức nhận số nguyên thủy và trả đối tượng, `mapToObj` có thể nhận method reference:

```java
import java.util.List;
import java.util.stream.IntStream;

static String formatTicket(int number) {
    return "TICKET-" + number;
}

List<String> tickets = IntStream.rangeClosed(1, 3)
    .mapToObj(YourClass::formatTicket)
    .toList();
```

Đoạn trên là ví dụ **đặt bên trong lớp** có tên `YourClass` chứa phương thức `formatTicket`. Khi viết mã thực tế, thay tên lớp cho đúng. Nếu method reference gây khó đọc do overload hoặc suy luận generic, một lambda ngắn như `number -> formatTicket(number)` thường rõ ý hơn.

## 5. Chọn `boxed` hay `mapToObj`?

| Tiêu chí | `boxed()` | `mapToObj(...)` |
| --- | --- | --- |
| Mục tiêu | Đưa giá trị primitive vào wrapper | Chuyển giá trị primitive thành đối tượng theo quy tắc |
| Có phải cung cấp mapper? | Không | Có |
| Kiểu trả về từ `IntStream` | `Stream<Integer>` | `Stream<U>` do mapper quyết định |
| Có đổi ý nghĩa giá trị không? | Không; chỉ đổi cách biểu diễn | Có thể đổi, gắn nhãn, xây DTO, áp quy tắc |
| Ví dụ | `IntStream.range(1, 5).boxed()` | `IntStream.range(1, 5).mapToObj(n -> "P" + n)` |
| Khi cần grouping theo chính giá trị số | Tiện lợi | Có thể làm được, nhưng không cần mapper riêng |
| Khi cần object nghiệp vụ | Phải thêm `map(...)` sau `boxed()` | Ánh xạ trực tiếp |

Một quy tắc thực hành:

- **Cần `List<Integer>`, `Set<Long>` hoặc muốn dùng `Collectors` trên wrapper:** thường chọn `boxed()`.
- **Cần `String`, DTO, entity bất biến, giá trị gắn đơn vị hoặc đối tượng phức tạp:** chọn `mapToObj(...)`.
- **Chỉ cần tính tổng, trung bình, min/max hoặc thống kê số:** hãy **giữ primitive stream** và dùng các terminal operation chuyên dụng.

Ví dụ không cần boxing:

```java
int total = java.util.stream.IntStream.of(10, 20, 30)
    .sum(); // 60

double mean = java.util.stream.IntStream.of(10, 20, 30)
    .average()
    .orElseThrow(); // 20.0
```

Không chuyển sang object stream chỉ để quay lại phép cộng số nếu đã có `sum()` trên primitive stream.

## 6. Ghép `boxed` với `Collectors`, grouping và loại trùng

`IntStream` có phương thức `collect(Supplier<R>, ObjIntConsumer<R>, BiConsumer<R,R>)` riêng, nhưng không nhận `Collector<T,A,R>` giống `Stream<T>`. Nếu cần factory collector trong `java.util.stream.Collectors`, thường phải chuyển sang object stream.

Ví dụ nhóm số chẵn và lẻ:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, List<Integer>> groups = IntStream.rangeClosed(1, 8)
    .boxed()
    .collect(Collectors.groupingBy(
        value -> value % 2 == 0 ? "even" : "odd"
    ));

System.out.println(groups.get("even")); // [2, 4, 6, 8]
System.out.println(groups.get("odd"));  // [1, 3, 5, 7]
```

`Collectors.groupingBy` không cam kết loại `Map` hay thứ tự duyệt **khóa**. Với stream có encounter order như `IntStream.rangeClosed`, các `List<Integer>` thu bằng collector mặc định giữ thứ tự phần tử trong nhóm theo hợp đồng collector trên ordered stream.

Ví dụ tạo `Set<Integer>`:

```java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Set<Integer> unique = IntStream.of(3, 1, 3, 2, 1)
    .distinct()
    .boxed()
    .collect(Collectors.toSet());

System.out.println(unique.containsAll(Set.of(1, 2, 3))); // true
```

`Collectors.toSet()` không bảo đảm thứ tự duyệt hoặc loại triển khai. Nếu mục tiêu chỉ loại giá trị trùng trước khi tổng hợp số, `distinct()` ngay trên primitive stream tránh boxing sớm:

```java
int sumUnique = IntStream.of(3, 1, 3, 2, 1)
    .distinct()
    .sum(); // 6
```

### 6.1. Vì sao `boxed` cần thiết cho một số kiểu collector?

Chẳng hạn muốn gom các số vào danh sách bằng `Collectors.toList()`:

```java
List<Integer> values = IntStream.rangeClosed(1, 4)
    .boxed()
    .collect(Collectors.toList());
```

Không thể viết `IntStream.rangeClosed(1, 4).collect(Collectors.toList())` vì chữ ký `IntStream.collect` không có overload nhận `Collector`. Trình biên dịch sẽ báo không phù hợp tham số.

Nếu JDK hỗ trợ `Stream.toList()` và không cần collector đặc biệt, `IntStream.rangeClosed(1,4).boxed().toList()` ngắn gọn hơn.

## 7. Ví dụ thực tế: dùng chỉ số số nguyên để tạo DTO và tổng hợp

Một ứng dụng có hai mảng dữ liệu song song: danh sách mã hàng và số tiền ở đơn vị đồng. Cần tạo từng dòng báo cáo có số thứ tự, mã hàng và giá trị, sau đó tính doanh thu theo mã hàng.

Ở đây `IntStream.range` cung cấp **chỉ số**, `mapToObj` tạo **đối tượng báo cáo**, và `collect(groupingBy(...))` tổng hợp:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PrimitiveToObjectReport {

    public record SaleLine(int lineNo, String sku, long amountVnd) {}

    public static void main(String[] args) {
        List<String> skus = List.of("PEN", "BOOK", "PEN", "BAG");
        long[] amountsVnd = {12_000L, 85_000L, 8_000L, 150_000L};

        if (skus.size() != amountsVnd.length) {
            throw new IllegalArgumentException("Số phần tử nguồn không khớp");
        }

        List<SaleLine> report = IntStream.range(0, skus.size())
            .mapToObj(i -> new SaleLine(
                i + 1,
                skus.get(i),
                amountsVnd[i]
            ))
            .toList();

        // Trên JDK 17+, toList() tạo List không thể sửa đổi.
        System.out.println(report.get(0));
        // SaleLine[lineNo=1, sku=PEN, amountVnd=12000]

        Map<String, Long> totalsBySku = report.stream()
            .collect(Collectors.groupingBy(
                SaleLine::sku,
                Collectors.summingLong(SaleLine::amountVnd)
            ));

        System.out.println(totalsBySku.get("PEN"));  // 20000
        System.out.println(totalsBySku.get("BOOK")); // 85000
        System.out.println(totalsBySku.get("BAG"));  // 150000

        long grandTotal = report.stream()
            .mapToLong(SaleLine::amountVnd)
            .sum();
        System.out.println(grandTotal); // 255000
    }
}
```

Theo dõi kiểu:

| Bước | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `IntStream.range(0, skus.size())` | `IntStream` | Chỉ số nguyên thủy từ 0 đến n − 1 |
| `.mapToObj(i -> new SaleLine(...))` | `Stream<SaleLine>` | Tạo một DTO cho từng chỉ số |
| `.toList()` | `List<SaleLine>` | Thu kết quả, kích hoạt pipeline |
| `report.stream()` | `Stream<SaleLine>` | Mở pipeline mới từ dữ liệu kết quả |
| `.mapToLong(SaleLine::amountVnd)` | `LongStream` | Quay về primitive stream để tính tổng |
| `.sum()` | `long` | Terminal operation tính tổng |

Mẫu `IntStream.range(...).mapToObj(...)` đặc biệt hữu ích khi cần tạo bản ghi có **index**, nhưng cũng có giới hạn:

- Hai nguồn `skus` và `amountsVnd` phải cùng kích thước, được kiểm tra trước.
- Nếu nguồn bị sửa đồng thời, chỉ số có thể không còn khớp dữ liệu. Trong ứng dụng thật, cân nhắc snapshot bất biến hoặc một model thống nhất cho mỗi dòng.
- `long` tránh sai số thập phân khi biểu diễn số tiền nguyên đơn vị nhỏ nhất nhưng vẫn có thể **tràn số**. `Collectors.summingLong` và `LongStream.sum()` không tự phát hiện tràn; đối với số tiền có thể vượt giới hạn, sử dụng kiểu phù hợp hoặc kiểm tra miền dữ liệu.
- Không dùng `parallel()` tùy tiện nếu mapper đọc dữ liệu có thể thay đổi từ nơi khác; độ an toàn của việc đọc phụ thuộc nguồn và toàn bộ pipeline.

## 8. Đi từ object stream về primitive stream

Trong nhiều pipeline, chuyển sang object stream chỉ là một giai đoạn. Sau khi tạo DTO, ta có thể **chuyển ngược** sang primitive stream để tính số học.

### 8.1. Từ `Stream<Integer>` sang `IntStream`

```java
import java.util.List;

List<Integer> values = List.of(4, 5, 6);

int sum = values.stream()
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sum); // 15
```

Các phương thức chuyên biệt trên `Stream<T>`:

| Phương thức | Đầu vào mapper | Kết quả |
| --- | --- | --- |
| `mapToInt(ToIntFunction<? super T>)` | `T → int` | `IntStream` |
| `mapToLong(ToLongFunction<? super T>)` | `T → long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<? super T>)` | `T → double` | `DoubleStream` |

Nếu một `Stream<Integer>` chứa giá trị `null`, `Integer::intValue` sẽ ném `NullPointerException` khi gặp phần tử đó. Cần xác định chính sách dữ liệu null, ví dụ `filter(Objects::nonNull)` nếu được phép bỏ giá trị, hoặc kiểm tra hợp lệ trước.

### 8.2. Không phải mọi chuyển đổi là boxing

Các chuyển đổi như `IntStream.asLongStream()` hoặc `IntStream.asDoubleStream()` vẫn tạo **primitive stream** với kiểu số khác, không tạo wrapper object. Đừng nhầm chúng với `boxed()`:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

LongStream widened = IntStream.of(1, 2, 3)
    .asLongStream(); // int -> long, vẫn là primitive.

System.out.println(widened.sum()); // 6
```

Với tính toán cần chính xác hơn miền số `int`, nên cân nhắc mở rộng kiểu trước khi cộng hoặc nhân; boxing thành `Integer` **không** làm tăng miền giá trị.

## 9. Mảng, danh sách, generic và suy luận kiểu

### 9.1. `int[]` khác `Integer[]` và `List<Integer>`

Một nguồn mảng nguyên thủy có thể trở thành `IntStream`:

```java
import java.util.Arrays;
import java.util.List;

int[] source = {7, 8, 9};

int[] primitiveArray = Arrays.stream(source)
    .toArray(); // int[]

Integer[] objectArray = Arrays.stream(source)
    .boxed()
    .toArray(Integer[]::new); // Integer[]

List<Integer> list = Arrays.stream(source)
    .boxed()
    .toList(); // List<Integer>
```

Các cấu trúc có đặc tính khác nhau:

| Cấu trúc | Phần tử | Có thể chứa `null`? | Có phải collection generic? |
| --- | --- | --- | --- |
| `int[]` | `int` | Không | Không |
| `Integer[]` | `Integer` | Có | Không phải `Collection` |
| `List<Integer>` | `Integer` | Tùy implementation/cách tạo | Có |

Lưu ý đặc biệt: `Stream.of(source)` khi `source` có kiểu `int[]` tạo stream chứa **một phần tử là chính mảng `int[]`** (kiểu `Stream<int[]>`), chứ không phải dãy các số trong mảng. Để duyệt từng số, dùng `Arrays.stream(source)` hoặc `IntStream.of(source)`.

### 9.2. Kiểu generic `U` được suy ra thế nào?

Với `mapToObj`, `U` đến từ biểu thức trong mapper:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<String> names = IntStream.of(1, 2, 3)
    .mapToObj(n -> "Item-" + n);

Stream<Integer> boxedEquivalent = IntStream.of(1, 2, 3)
    .mapToObj(Integer::valueOf);
```

Ví dụ thứ hai cho ra cùng kiểu `Stream<Integer>` như `boxed()`, nhưng `boxed()` là cách rõ ràng hơn khi yêu cầu chỉ là bọc wrapper.

Đôi khi cần chú thích generic tường minh để tránh compiler suy ra kiểu quá rộng:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<Number> numericObjects = IntStream.of(1, 2, 3)
    .<Number>mapToObj(Integer::valueOf);
```

`<Number>mapToObj` chỉ định kiểu `U` là `Number`; mapper trả `Integer` là một kiểu con nên phù hợp. Việc chọn kiểu quá rộng như `Object` ở mọi bước thường làm mất thông tin và gây khó khăn khi sử dụng kết quả. Hãy giữ kiểu cụ thể cho đến khi yêu cầu thật sự cần đa hình.

### 9.3. `mapToObj` không tự làm phẳng

Nếu mapper trả về một `List<String>` thì kết quả là `Stream<List<String>>`, vì mỗi phần tử vẫn tạo **một đối tượng List**. Khi cần trộn phần tử bên trong:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> flattened = IntStream.rangeClosed(1, 2)
    .mapToObj(n -> List.of("A" + n, "B" + n))
    .flatMap(List::stream)
    .toList();

System.out.println(flattened); // [A1, B1, A2, B2]
```

`flatMap` là bước riêng trên object stream để làm phẳng cấu trúc; `mapToObj` chỉ xác định cách ánh xạ mỗi primitive sang đối tượng.

## 10. Tính lười, side effects và vòng đời stream

`boxed()` và `mapToObj` đều là intermediate operations **lazy**. Mapper được đánh giá khi terminal operation cần phần tử, và số lần mapper chạy không nên được xem là hợp đồng nghiệp vụ.

```java
import java.util.List;
import java.util.stream.IntStream;

var pipeline = IntStream.range(1, 5)
    .mapToObj(n -> "ID-" + n);

List<String> ids = pipeline.toList();
System.out.println(ids); // [ID-1, ID-2, ID-3, ID-4]
```

Một ví dụ không nên dựa vào side effect:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger calls = new AtomicInteger();

long count = IntStream.range(0, 10)
    .mapToObj(n -> {
        calls.incrementAndGet();
        return "Value-" + n;
    })
    .count();

System.out.println(count); // 10
// Không dựa vào việc calls.get() chắc chắn bằng 10.
```

Với một nguồn biết trước số phần tử như `IntStream.range`, các tối ưu hóa của Stream có thể xác định `count()` mà không cần chạy mapper. Vì vậy, nếu cần ghi nhận số bản ghi thực sự được xử lý, hãy gắn phép đếm với kết quả nghiệp vụ hoặc một cơ chế quan sát có thiết kế rõ ràng.

Các mapper nên **non-interfering** và **stateless**: không sửa dữ liệu nguồn đang duyệt, không phụ thuộc biến đếm hoặc collection mutable dùng chung. Ví dụ:

```java
// Mapper có thể kiểm thử độc lập:
record Code(int value, String label) {}

static Code toCode(int value) {
    return new Code(value, "C-" + value);
}

// Trong một phương thức khác:
// List<Code> codes = IntStream.range(0, 3)
//     .mapToObj(YourClass::toCode)
//     .toList();
```

`boxed()` hoặc `mapToObj` không tự mở tài nguyên. Nhưng primitive stream có thể xuất phát từ I/O hoặc được tạo qua một nguồn có handler đóng; khi nguồn nắm giữ tài nguyên, cần đóng stream theo hợp đồng của nguồn (thường bằng `try-with-resources`). Đừng dùng lại stream đã được terminal operation tiêu thụ; hãy tạo pipeline mới từ nguồn có thể duyệt lại.

## 11. Hiệu năng: boxing lúc cần, không quá sớm

Primitive stream thường hữu ích cho khối lượng xử lý số lớn vì tránh chi phí wrapper trong nhiều bước. Khi dùng `boxed()`, mỗi số được biểu diễn dưới dạng wrapper ở phần object stream; việc này có thể làm tăng áp lực cấp phát, sử dụng bộ nhớ và garbage collection, dù JVM có thể tối ưu hóa hoặc tái sử dụng một số wrapper.

So sánh ba cách tính tổng:

```java
import java.util.stream.IntStream;

long primitiveSum = IntStream.rangeClosed(1, 1_000_000)
    .asLongStream()
    .sum();

long boxedSum = IntStream.rangeClosed(1, 1_000_000)
    .boxed()
    .mapToLong(Integer::longValue)
    .sum();

long mappedSum = IntStream.rangeClosed(1, 1_000_000)
    .mapToLong(n -> n)
    .sum();

System.out.println(primitiveSum); // 500000500000
System.out.println(boxedSum);     // 500000500000
System.out.println(mappedSum);    // 500000500000
```

Ba cách cho cùng kết quả ở dữ liệu này. Hai cách `asLongStream` và `mapToLong` giữ kiểu nguyên thủy suốt quá trình tính tổng, diễn đạt nhu cầu rõ hơn và có thể tránh các bước boxing/unboxing. `boxedSum` minh họa bước chuyển đối tượng không cần thiết.

**Lưu ý tràn số:** tổng từ 1 đến 1.000.000 vượt miền `int`, nên ví dụ chuyển sang `long` **trước** khi tính. `IntStream.sum()` trả `int` và có thể tràn; việc `boxed()` không khắc phục điều đó.

### 11.1. Đo hiệu năng đúng cách

Không kết luận `mapToObj` luôn nhanh hơn `boxed().map(...)` hoặc ngược lại chỉ từ cấu trúc code. Hiệu quả còn phụ thuộc:

- Số phần tử và chi phí tạo object đầu ra.
- Mức độ tối ưu của JIT, kiểu mapper và khả năng loại bỏ allocation.
- Có terminal operation nào khiến những bước trung gian được bỏ qua hay không.
- Nguồn có thứ tự, chi phí `sorted`/`distinct`/`limit`, collector và GC.
- Chế độ tuần tự hay `parallel()`; overhead phân chia/gộp kết quả.

Để đánh giá thực tế, dùng benchmark được warm-up và kiểm soát kết quả (ví dụ JMH trong quy trình tối ưu ở bước khác). Một phép đo thời gian bằng `System.nanoTime()` cho một lần chạy dễ gây kết luận sai do JIT, GC và nhiễu hệ thống. Ở bài này, nguyên tắc là **giữ primitive khi đang tính số, chuyển sang object tại điểm cần dữ liệu đối tượng**.

### 11.2. Stream song song

`IntStream.range(...).parallel().mapToObj(...)` vẫn hợp lệ nếu mapper không dùng trạng thái mutable chia sẻ và nguồn hỗ trợ duyệt an toàn. Nhưng parallel stream không mặc nhiên nhanh hơn:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> codes = IntStream.range(0, 1_000)
    .parallel()
    .mapToObj(i -> "C-" + i)
    .toList();

System.out.println(codes.get(0)); // C-0
```

Với `IntStream.range` có encounter order, `toList()` giữ thứ tự đó trong kết quả dù thời gian xử lý phần tử có thể khác nhau. Không được dùng thứ tự thực thi lambda làm bằng chứng thứ tự gặp phần tử.

## 12. Những bẫy cụ thể khi chuyển sang object stream

| Bẫy | Vì sao sai hoặc khó bảo trì | Cách xử lý |
| --- | --- | --- |
| Gọi `.toList()` trực tiếp trên `IntStream` | `IntStream` không có API này | `.boxed().toList()` hoặc `.toArray()` nếu cần `int[]` |
| Dùng `Stream.of(intArray)` để duyệt số | Tạo `Stream<int[]>` với một phần tử mảng | `Arrays.stream(intArray)` |
| Dùng `boxed()` để chuyển thành `Stream<String>` | `boxed()` trả wrapper, không định dạng chuỗi | `mapToObj(n -> "...")` |
| Box số rồi lại unbox để `sum()` | Tăng bước chuyển không cần thiết | Giữ `IntStream`/`LongStream` |
| Dùng `Integer` như thể luôn khác `null` | Object stream có thể chứa null | Xác định chính sách null trước unboxing |
| So sánh wrapper bằng `==` | Có thể so sánh tham chiếu object | `equals` hoặc so sánh primitive |
| Cho rằng `toList()` luôn sửa được | `Stream.toList()` là unmodifiable | Dùng collector tạo collection mutable khi cần |
| Tưởng `mapToObj` tạo nhiều kết quả cho một phần tử | Một primitive được ánh xạ thành một giá trị object | Dùng `flatMap`/`mapMulti` trong bài toán 0–n |
| Coi `mapToObj` là terminal operation | Đây vẫn là một bước lazy | Dùng `toList`, `collect`, `count`,... để tiêu thụ |
| Dùng `int` cho tổng có thể vượt `Integer.MAX_VALUE` | `IntStream.sum()` có thể tràn | Mở rộng sang `long` trước phép cộng hoặc dùng kiểu chính xác hơn |

### 12.1. Dữ liệu null và kết quả mapper

`IntStream`, `LongStream` và `DoubleStream` **không chứa null**. Nhưng mapper `mapToObj` có thể trả `null` vì đầu ra là object:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

List<String> nonNullLabels = IntStream.rangeClosed(1, 4)
    .mapToObj(n -> n % 2 == 0 ? null : "N-" + n)
    .filter(Objects::nonNull)
    .toList();

System.out.println(nonNullLabels); // [N-1, N-3]
```

Ví dụ chỉ minh họa ranh giới kiểu. Nếu “không có nhãn” là trạng thái hợp lệ, có thể dùng mapper tạo `Optional<String>` rồi `flatMap(Optional::stream)`; nếu việc thiếu nhãn là lỗi nghiệp vụ, nên ném lỗi rõ ràng ở bước xác thực.

### 12.2. `DoubleStream` và các giá trị đặc biệt

`double` hỗ trợ `NaN`, `Infinity`, `-Infinity` và phân biệt `0.0` với `-0.0` ở cấp bit. `DoubleStream.boxed()` giữ nguyên kiểu số dưới dạng `Double`, không xóa những giá trị này:

```java
import java.util.List;
import java.util.stream.DoubleStream;

List<Double> values = DoubleStream.of(
    0.0, -0.0, Double.NaN, Double.POSITIVE_INFINITY
).boxed().toList();

System.out.println(values);
// [0.0, -0.0, NaN, Infinity]
```

Khi dùng wrapper `Double` làm khóa `Map` hoặc phần tử `Set`, cần đọc quy tắc `Double.equals` và `hashCode`: `NaN` được coi bằng `NaN` theo wrapper; `0.0` và `-0.0` không `equals`. Những quy tắc này có thể khác ý nghĩa toán học của phép so sánh primitive bằng `==`. Nếu dữ liệu yêu cầu giá trị hữu hạn, kiểm tra `Double.isFinite(value)` trước khi xây DTO hoặc dùng collector.

## 13. Kiểm thử giá trị sau khi chuyển

Với JUnit 5 và JDK 17+, có thể kiểm thử trực tiếp kết quả của hai phương thức:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import org.junit.jupiter.api.Test;

class PrimitiveObjectConversionTest {

    @Test
    void boxedKeepsValuesAndOrder() {
        assertEquals(
            List.of(2, 3, 4),
            IntStream.rangeClosed(2, 4).boxed().toList()
        );
    }

    @Test
    void mapToObjBuildsLabels() {
        assertEquals(
            List.of("ID-1", "ID-2", "ID-3"),
            IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "ID-" + n)
                .toList()
        );
    }

    @Test
    void emptySourceProducesEmptyObjectStream() {
        assertEquals(
            List.of(),
            LongStream.empty().boxed().toList()
        );
    }

    @Test
    void primitiveAndBoxedArrayHaveDifferentTypes() {
        int[] primitive = IntStream.of(1, 2).toArray();
        Integer[] boxed = IntStream.of(1, 2)
            .boxed()
            .toArray(Integer[]::new);

        assertArrayEquals(new int[]{1, 2}, primitive);
        assertArrayEquals(new Integer[]{1, 2}, boxed);
    }

    @Test
    void arithmeticAfterMappingRemainsCorrect() {
        long sum = IntStream.rangeClosed(1, 100_000)
            .mapToLong(n -> n)
            .sum();

        assertEquals(5_000_050_000L, sum);
    }
}
```

Những kiểm thử hữu ích khác gồm: một phần tử, dữ liệu có số âm, giá trị biên `Integer.MIN_VALUE`/`MAX_VALUE`, `Long.MAX_VALUE`, mảng rỗng, kiểu `Double` đặc biệt, mapper trả `null`, và thao tác group theo giá trị đã boxing. Kiểm thử **giá trị và kiểu mong muốn**, không ràng buộc số lần lambda được gọi nếu API không bảo đảm.

## 14. Bài tập áp dụng

**Bài 1 — Wrapper và collection.** Tạo `List<Long>` từ các số `5, 6, 7, 8` bằng `LongStream.rangeClosed` và `boxed()`. Sau đó tạo `ArrayList<Long>` có thể chỉnh sửa bằng `Collectors.toCollection`. Giải thích vì sao `Stream.toList()` không thích hợp nếu muốn `add()`.

**Bài 2 — Ánh xạ nhãn.** Dùng `IntStream.rangeClosed(1, 5)` và `mapToObj` để tạo `List<String>` gồm `"Chapter-1"` đến `"Chapter-5"`. Viết một phiên bản khác bằng `boxed().map(...)` và xác định kiểu stream ở từng bước.

**Bài 3 — Tạo DTO.** Định nghĩa `record ProductId(long value, String label)`. Dùng `LongStream.of(101, 102, 103)` với `mapToObj` để tạo các đối tượng có label `"PRD-101"`, `"PRD-102"`, `"PRD-103"`. Từ danh sách kết quả, dùng `mapToLong(ProductId::value).sum()` để cộng ID.

**Bài 4 — Grouping chẵn/lẻ.** Từ `IntStream.rangeClosed(1, 12)`, phân nhóm thành `Map<String, List<Integer>>` có hai khóa `"even"` và `"odd"`. Giải thích vì sao cần `boxed()` trước `Collectors.groupingBy`. Nếu chỉ cần tổng các số chẵn, hãy viết một pipeline giữ kiểu nguyên thủy.

**Bài 5 — Phân biệt mảng.** Từ `int[] numbers = {2, 4, 6}`, tạo một `int[]` mới và một `List<Integer>`. So sánh kết quả của `Stream.of(numbers)` với `Arrays.stream(numbers)` bằng kiểu biên dịch.

**Bài 6 — Tổng lớn.** Tính tổng số từ `1` đến `1_000_000`. So sánh kiểu trả về của `IntStream.sum()` với `IntStream.asLongStream().sum()`, chỉ ra trường hợp tràn và viết unit test cho giá trị đúng `500000500000L`.

**Bài 7 — Trạng thái và tối ưu hóa.** Một lập trình viên tạo `AtomicInteger counter = new AtomicInteger()` rồi viết `IntStream.range(0, 100).mapToObj(n -> { counter.incrementAndGet(); return n; }).count()` và kỳ vọng bộ đếm bằng 100. Phân tích lý do kỳ vọng này không thuộc hợp đồng Stream và viết lại bằng pipeline không có side effect. Nếu đổi sang biến cục bộ `int counter` với phép `counter++` trong lambda, trình biên dịch còn từ chối vì biến được capture phải là `final` hoặc *effectively final*.

## 15. Bảng ghi nhớ khi thiết kế pipeline

| Cần làm | API thường chọn | Kiểu đầu ra |
| --- | --- | --- |
| Tạo object wrapper từ `int` | `IntStream.boxed()` | `Stream<Integer>` |
| Tạo object wrapper từ `long` | `LongStream.boxed()` | `Stream<Long>` |
| Tạo object wrapper từ `double` | `DoubleStream.boxed()` | `Stream<Double>` |
| Tạo nhãn/DTO từ `int` | `IntStream.mapToObj(IntFunction)` | `Stream<U>` |
| Tạo nhãn/DTO từ `long` | `LongStream.mapToObj(LongFunction)` | `Stream<U>` |
| Tạo nhãn/DTO từ `double` | `DoubleStream.mapToObj(DoubleFunction)` | `Stream<U>` |
| Thu vào `List<Integer>` (JDK 16+) | `intStream.boxed().toList()` | `List<Integer>` |
| Dùng `Collectors.groupingBy` trên số | `intStream.boxed().collect(...)` | `Map<K, V>` |
| Lấy `int[]` | `intStream.toArray()` | `int[]` |
| Tính tổng `int` có thể vượt miền `int` | `intStream.asLongStream().sum()` | `long` |
| Tính tổng trường `long` trên DTO | `stream.mapToLong(Dto::amount).sum()` | `long` |
| Đổi số thành đối tượng rồi làm phẳng collection | `mapToObj(...).flatMap(...)` | `Stream<R>` |

`boxed()` và `mapToObj()` là cầu nối giữa xử lý số nguyên thủy và hệ kiểu đối tượng của Java Stream API. Chọn `boxed()` khi chỉ cần wrapper, chọn `mapToObj()` khi cần tạo một giá trị đối tượng mới, và giữ primitive stream khi các phép tính số chưa yêu cầu collection hoặc DTO. Cách quyết định này giúp pipeline `JAVA_STREAM_API` dễ đọc, dễ kiểm thử và kiểm soát được chi phí boxing, trạng thái và hiệu năng trước khi mở rộng sang `filter`, `reduce`, `collect`, grouping hay xử lý song song.
