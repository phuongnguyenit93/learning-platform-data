# Đọc pipeline theo kiểu dữ liệu và hình dạng dữ liệu qua từng bước

Một pipeline Java Stream có thể rất ngắn nhưng vẫn khó gỡ lỗi:

```java
var result = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .sorted()
    .toList();
```

Khi đọc đoạn này, chỉ biết `result` là “một danh sách” là chưa đủ. Ta cần trả lời **hai câu hỏi khác nhau tại mỗi bước**:

1. **Kiểu dữ liệu Java là gì?** Ví dụ `Stream<Order>`, `Stream<List<String>>`, `Stream<String>` hay `List<String>`.
2. **Hình dạng dữ liệu (*data shape*) là gì?** Có bao nhiêu phần tử, mỗi phần tử là một bản ghi hay một danh sách, có nhóm lồng nhau không, thứ tự nào được bảo đảm, có thể rỗng hoặc trùng lặp không?

Đây là kỹ năng nền tảng để đọc, giải thích, gỡ lỗi và kiểm thử các pipeline dùng `filter`, `map`, `flatMap`, `reduce`, `collect`, collector nhiều tầng, `Spliterator` và các Stream Gatherer. Bài thuộc chương **Gỡ lỗi và kiểm thử pipeline** của mô-đun **JAVA_STREAM_API**: học xử lý dữ liệu theo phong cách khai báo, nhưng không đánh mất khả năng lý giải tính đúng, trạng thái, tài nguyên và hiệu năng.

Các ví dụ cơ sở sử dụng **Java 17+**; phần `Stream.gather` được tách riêng cho **Java 24+** vì Stream Gatherers chỉ chính thức từ JDK 24.

## 1. Kiểu dữ liệu và hình dạng dữ liệu không phải cùng một thứ

Hãy phân biệt:

| Khái niệm | Câu hỏi cần hỏi | Ví dụ |
| --- | --- | --- |
| **Kiểu phần tử** | Mỗi phần tử có kiểu Java nào? | `Order`, `String`, `List<String>` |
| **Kiểu Stream** | Pipeline hiện phát phần tử theo kiểu nào? | `Stream<Order>`, `LongStream` |
| **Số lượng (cardinality)** | Có bao nhiêu phần tử sau stage? | Từ 4 đơn hàng còn 3 đơn đã thanh toán |
| **Mức lồng nhau** | Mỗi phần tử là một giá trị hay tập con? | `Stream<List<String>>` thay vì `Stream<String>` |
| **Thứ tự gặp (encounter order)** | Phần tử có thứ tự được bảo đảm không? | `List.stream()` có thứ tự; `HashSet.stream()` không bảo đảm |
| **Trùng lặp** | Có phần tử cùng giá trị xuất hiện nhiều lần không? | `["java", "java", "api"]` |
| **Giá trị rỗng/thiếu** | Nguồn hoặc nhóm có thể rỗng? Có `null`? | `List.of()`, `Optional.empty()` |
| **Hình dạng kết quả cuối** | Terminal operation trả đối tượng nào? | `List<String>`, `Map<String,Long>`, `Optional<Order>` |

Một `Stream<List<String>>` với ba phần tử **không** giống `Stream<String>` với ba phần tử. Ở trường hợp thứ nhất, mỗi phần tử lại là một danh sách và độ dài của từng danh sách có thể khác nhau.

### Hình dung bằng hai trục

```text
Kiểu tĩnh                    Hình dạng quan sát được

Stream<Order>              [O1, O2, O3, O4]
      |                              |
      | filter(paid)                 | bỏ O2
      v                              v
Stream<Order>              [O1, O3, O4]
      |                              |
      | map(tags)                    | mỗi O -> một List
      v                              v
Stream<List<String>>       [[java, backend], [java, streams], []]
      |                              |
      | flatMap(List::stream)        | nối các danh sách con
      v                              v
Stream<String>             [java, backend, java, streams]
      |                              |
      | distinct()                   | loại giá trị trùng
      v                              v
Stream<String>             [java, backend, streams]
      |                              |
      | sorted()                     | sắp xếp
      v                              v
Stream<String>             [backend, java, streams]
      |                              |
      | toList()                     | vật hóa
      v                              v
List<String>               [backend, java, streams]
```

**Quy tắc:** Đừng chỉ nói “`map` đã đổi danh sách”. Hãy chỉ ra **đổi kiểu phần tử** ra sao và **đổi hình dạng quan sát được** ra sao. Hai thông tin này là chìa khóa để phát hiện lỗi `map`/`flatMap`, lỗi collector và kỳ vọng sai về số lượng.

## 2. Bộ dữ liệu mẫu dùng xuyên suốt

Để các ví dụ có thể kiểm tra được bằng tay, dùng một bộ dữ liệu nhỏ, chứa cả trường hợp bình thường và biên.

```java
import java.util.List;

record Order(
    String id,
    String region,
    List<String> tags,
    long amountCents,
    boolean paid
) {}

List<Order> orders = List.of(
    new Order("O-1", "Bac",   List.of("java", "backend"), 120_000L, true),
    new Order("O-2", "Nam",   List.of("frontend"),       90_000L, false),
    new Order("O-3", "Bac",   List.of("java", "streams"),  80_000L, true),
    new Order("O-4", "Trung", List.of(),                  50_000L, true)
);
```

Dữ liệu nguồn gồm bốn bản ghi theo thứ tự `O-1, O-2, O-3, O-4`.

| Đơn | Thanh toán? | Tags | Số tags | Amount (cent) |
| --- | --- | --- | ---: | ---: |
| O-1 | Có | java, backend | 2 | 120.000 |
| O-2 | Không | frontend | 1 | 90.000 |
| O-3 | Có | java, streams | 2 | 80.000 |
| O-4 | Có | (rỗng) | 0 | 50.000 |

Khi chỉ lấy đơn đã thanh toán, còn `O-1, O-3, O-4`: ba đơn, có tổng **bốn lần xuất hiện tag**, nhưng chỉ **ba tag phân biệt**.

Trong các đoạn mã phía dưới, khi chỉ dùng biến `orders`, hãy hiểu rằng chúng là các đoạn chạy **trong cùng phạm vi** với khai báo record và danh sách trên. Phần cuối bài có chương trình Java hoàn chỉnh.

## 3. Bước khởi tạo nguồn: `Collection` sang `Stream<T>`

`orders` có kiểu `List<Order>`. Khi gọi `stream()`:

```java
java.util.stream.Stream<Order> source = orders.stream();
```

kiểu là `Stream<Order>`, **không phải `List<Order>`**. Chưa có danh sách kết quả mới được xây dựng và chưa chạy pipeline xử lý nào. Dữ liệu vẫn nằm trong collection nguồn, còn Stream mô tả một lần duyệt và xử lý.

Hình dạng logic:

```text
List<Order>      : [O-1, O-2, O-3, O-4]
                       |
                       | stream()
                       v
Stream<Order>    : các phần tử Order theo encounter order của List
```

Cần chú ý:

- Stream được **tiêu thụ một lần**; sau terminal operation không thể tiếp tục chạy một terminal operation khác trên chính Stream đó.
- Các intermediate operation tạo các stage mới, chứ không nhất thiết sao chép nguồn thành collection mới.
- `Stream<T>` không phải `T[]`, `List<T>` hoặc `Optional<T>`.
- Đừng giả định Stream đã có sẵn số lượng chính xác nếu nguồn tùy chỉnh không công bố kích thước.

## 4. Bảng hợp đồng hình dạng của các intermediate operation

Bảng này là “từ điển” đọc nhanh. Số lượng ký hiệu là số phần tử **logic** có thể đi đến đầu ra nếu pipeline được duyệt phù hợp, không phải cam kết về số lần gọi lambda.

| Operation | Kiểu vào → kiểu ra | Hình dạng và số lượng điển hình |
| --- | --- | --- |
| `filter(Predicate<T>)` | `Stream<T> → Stream<T>` | Giữ 0 hoặc 1 phần tử cho mỗi đầu vào; tổng 0..N |
| `map(Function<T,R>)` | `Stream<T> → Stream<R>` | Biến đổi 1:1 về logic; có thể đổi kiểu phần tử |
| `flatMap(Function<T,Stream<R>>)` | `Stream<T> → Stream<R>` | Mỗi đầu vào thành 0..n phần tử; bỏ một tầng Stream |
| `mapMulti(...)` | `Stream<T> → Stream<R>` | Có thể phát 0..n kết quả mỗi đầu vào, không buộc tạo Stream con |
| `distinct()` | `Stream<T> → Stream<T>` | Loại phần tử bằng nhau; 0..N |
| `sorted(...)` | `Stream<T> → Stream<T>` | Cùng phần tử, sắp xếp theo comparator; có thể tốn trạng thái |
| `limit(k)` | `Stream<T> → Stream<T>` | Giữ tối đa k phần tử; trên ordered Stream giữ k phần tử đầu |
| `skip(k)` | `Stream<T> → Stream<T>` | Bỏ k phần tử đầu trên ordered Stream |
| `takeWhile(p)` | `Stream<T> → Stream<T>` | Trên ordered Stream giữ tiền tố dài nhất thỏa p |
| `dropWhile(p)` | `Stream<T> → Stream<T>` | Trên ordered Stream bỏ tiền tố đó, giữ toàn bộ hậu tố |
| `peek(Consumer<T>)` | `Stream<T> → Stream<T>` | Không đổi kiểu hoặc tập kết quả logic; chỉ quan sát có điều kiện |
| `mapToInt(...)` | `Stream<T> → IntStream` | Biến đổi một phần tử thành một `int` khi được đánh giá |
| `mapToLong(...)` | `Stream<T> → LongStream` | Biến đổi thành nguồn số `long` |
| `boxed()` | `IntStream → Stream<Integer>` | Boxing các số, không tự gộp phần tử |
| `gather(Gatherer)` | `Stream<T> → Stream<R>` | Số đầu ra linh hoạt; có thể giữ trạng thái, ghép cửa sổ; JDK 24+ |

Với `map`, câu “một vào một ra” nói về **quan hệ logic giữa những phần tử được xử lý**, không có nghĩa Java buộc chạy callback `map` đúng N lần trong mọi terminal operation. Khi kết quả không cần thiết, một số giai đoạn có thể được tối ưu bỏ qua.

## 5. Đọc `filter`: loại phần tử, không đổi kiểu

`filter` chọn các đơn đã thanh toán:

```java
java.util.stream.Stream<Order> paidOrders = orders.stream()
    .filter(Order::paid);
```

Kiểu vẫn là `Stream<Order>`. Hình dạng thay đổi từ bốn bản ghi còn ba:

```text
Stream<Order> : [O-1, O-2, O-3, O-4]
filter(paid)  : [O-1,      O-3, O-4]
Stream<Order> : [O-1, O-3, O-4]
```

`filter` không tạo `Stream<Boolean>`. Phương thức `Order::paid` trả boolean, nhưng boolean ở đây chỉ được dùng để **quyết định giữ hoặc bỏ phần tử Order**.

Phân biệt:

```java
// Giữ các Order thỏa điều kiện.
List<Order> paid = orders.stream()
    .filter(Order::paid)
    .toList();

// Biến mỗi Order thành Boolean, kể cả đơn chưa thanh toán.
List<Boolean> flags = orders.stream()
    .map(Order::paid)
    .toList();

System.out.println(paid.size()); // 3
System.out.println(flags);       // [true, false, true, true]
```

Khi đọc pipeline, hãy hỏi: **predicate chỉ quyết định chọn phần tử hay giá trị boolean được đưa vào dữ liệu kết quả?** Câu trả lời phân biệt `filter` với `map`.

## 6. Đọc `map`: đổi kiểu phần tử nhưng không tự san phẳng

Chuyển mỗi đơn thành danh sách các tag:

```java
java.util.stream.Stream<List<String>> groupedTags = orders.stream()
    .filter(Order::paid)
    .map(Order::tags);
```

Kiểu sau `map` là **`Stream<List<String>>`**:

```text
[O-1, O-3, O-4]
       |
       | map(Order::tags)
       v
[[java, backend], [java, streams], []]
```

Có **ba phần tử ở cấp Stream ngoài**, tương ứng ba đơn. Nhưng từng phần tử lại là `List<String>` dài 2, 2 và 0.

### 6.1. Lỗi phổ biến: kỳ vọng `List<String>` khi đang có `List<List<String>>`

```java
List<List<String>> nested = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .toList();

System.out.println(nested);
// [[java, backend], [java, streams], []]
```

Khai báo sau sẽ **không biên dịch**, vì hai kiểu khác nhau:

```java
// SAI KIỂU:
// List<String> tags = orders.stream()
//     .filter(Order::paid)
//     .map(Order::tags)
//     .toList();
```

Bản thân `map` **không biết** bạn muốn giữ danh sách con hay ghép chúng thành một danh sách dài. Nếu mục tiêu là nhóm tag **theo từng đơn**, `List<List<String>>` có thể hoàn toàn đúng; nếu mục tiêu là tất cả tag trên cùng một cấp, cần `flatMap` hoặc `mapMulti`.

## 7. Đọc `flatMap`: bỏ một tầng lồng nhau

`flatMap` nhận một phần tử đầu vào rồi tạo một Stream con, sau đó nối các Stream con thành một Stream phẳng.

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .toList();

System.out.println(tags);
// [java, backend, java, streams]
```

Bảng bước:

| Bước | Kiểu | Hình dạng |
| --- | --- | --- |
| `orders.stream()` | `Stream<Order>` | 4 `Order` |
| `filter(Order::paid)` | `Stream<Order>` | 3 `Order` |
| `map(Order::tags)` | `Stream<List<String>>` | 3 danh sách: dài 2, 2, 0 |
| `flatMap(List::stream)` | `Stream<String>` | 4 chuỗi: java, backend, java, streams |
| `toList()` | `List<String>` | 4 chuỗi được vật hóa |

Cách viết ngắn tương đương:

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .toList();
```

**Điểm quan trọng về cardinality:** số đơn đã thanh toán là 3, nhưng số tag sau `flatMap` là 4. Không được tính `count()` trước và sau `flatMap` như thể chúng đang đếm cùng một loại thực thể.

### 7.1. Phân biệt `map(List::stream)` với `flatMap(List::stream)`

```java
// Mỗi phần tử của Stream ngoài là một Stream con.
List<java.util.stream.Stream<String>> nestedStreams = orders.stream()
    .filter(Order::paid)
    .map(order -> order.tags().stream())
    .toList();

// Nối toàn bộ tag vào một Stream<String>.
List<String> flatTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .toList();
```

Kiểu của biểu thức `map(order -> order.tags().stream())` là `Stream<Stream<String>>`. `flatMap` mới là thao tác để **làm phẳng** các Stream con. Đừng xem danh sách các Stream con như một kết quả lâu dài bình thường: mỗi Stream con có vòng đời sử dụng một lần và có thể giữ tài nguyên tùy nguồn.

### 7.2. `flatMap` với `Optional` và `Stream.ofNullable`

Khi dữ liệu có thể thiếu, có thể chuyển `Optional<T>` thành 0 hoặc 1 phần tử với `Optional.stream()` (Java 9+):

```java
import java.util.List;
import java.util.Optional;

List<Optional<String>> values = List.of(
    Optional.of("A"),
    Optional.empty(),
    Optional.of("B")
);

List<String> present = values.stream()
    .flatMap(Optional::stream)
    .toList();

System.out.println(present); // [A, B]
```

Hình dạng là `Stream<Optional<String>> → Stream<String>`. Mỗi `Optional.empty()` góp **0** phần tử. Tương tự, `Stream.ofNullable(value)` tạo Stream có 0 hoặc 1 phần tử tùy `value` có null không.

## 8. `mapMulti`: cùng mục tiêu 0..n đầu ra, cách triển khai khác

Từ Java 16, `Stream.mapMulti` cho một callback nhận đầu vào và một `Consumer` để phát nhiều phần tử, không buộc callback phải trả Stream con.

```java
List<String> tags = orders.stream()
    .filter(Order::paid)
    .<String>mapMulti((order, output) -> {
        for (String tag : order.tags()) {
            output.accept(tag);
        }
    })
    .toList();

System.out.println(tags);
// [java, backend, java, streams]
```

So sánh:

| Cách | Kiểu trước → sau | Đầu ra cho một `Order` |
| --- | --- | --- |
| `map(Order::tags)` | `Stream<Order> → Stream<List<String>>` | Một `List<String>` |
| `flatMap(o -> o.tags().stream())` | `Stream<Order> → Stream<String>` | 0..n `String` |
| `mapMulti((o,out) -> ...)` | `Stream<Order> → Stream<String>` | 0..n `String` |

Dấu `<String>` trước `mapMulti` giúp compiler biết kiểu `R` cần phát ra trong những biểu thức suy luận kiểu khó. Đó là **type witness**, không có nghĩa `mapMulti` tạo `List<String>` ngay tại bước trung gian.

`mapMulti` có thể hữu ích khi mỗi phần tử tạo ít kết quả và muốn tránh tạo nhiều Stream con; nhưng không mặc định rằng nó sẽ luôn nhanh hơn `flatMap`. Cần kiểm chứng cùng ngữ nghĩa và đo trên dữ liệu đại diện.

## 9. `distinct`, `sorted`, `limit`: kiểu có thể giữ nguyên, shape vẫn đổi

Sau khi làm phẳng tag:

```text
[java, backend, java, streams]
```

`distinct()` làm số lượng giảm từ 4 xuống 3:

```java
List<String> uniqueTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .toList();

System.out.println(uniqueTags); // [java, backend, streams]
```

`sorted()` giữ cùng ba giá trị nhưng đổi thứ tự:

```java
List<String> sortedTags = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .sorted()
    .toList();

System.out.println(sortedTags); // [backend, java, streams]
```

`limit(2)` lấy tối đa hai giá trị đầu của pipeline tại vị trí đó:

```java
List<String> firstTwo = orders.stream()
    .filter(Order::paid)
    .flatMap(order -> order.tags().stream())
    .distinct()
    .sorted()
    .limit(2)
    .toList();

System.out.println(firstTwo); // [backend, java]
```

| Stage | Kiểu | Hình dạng |
| --- | --- | --- |
| `flatMap(...)` | `Stream<String>` | 4 tag, có tag `java` trùng |
| `distinct()` | `Stream<String>` | 3 tag phân biệt, theo thứ tự xuất hiện đầu với nguồn có thứ tự |
| `sorted()` | `Stream<String>` | 3 tag theo thứ tự chữ cái |
| `limit(2)` | `Stream<String>` | 2 tag đầu |
| `toList()` | `List<String>` | `[backend, java]` |

**Ngộ nhận cần tránh:** “Kiểu không đổi” **không có nghĩa** “dữ liệu không đổi”. `distinct` đổi số lượng; `sorted` đổi encounter order; `limit` đổi phạm vi; `skip` đổi điểm bắt đầu.

### 9.1. Thứ tự stage quyết định ý nghĩa

```java
List<String> a = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .limit(2)
    .toList();

List<String> b = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .limit(2)
    .distinct()
    .toList();

System.out.println(a); // [java, backend]
System.out.println(b); // [java, backend]
```

Hai kết quả ở đây trùng nhau **do dữ liệu ví dụ**, không chứng minh hai phép luôn hoán đổi được. Với dãy `[A, A, B]`:

```java
List<String> values = List.of("A", "A", "B");

System.out.println(values.stream().distinct().limit(2).toList());
// [A, B]

System.out.println(values.stream().limit(2).distinct().toList());
// [A]
```

Đây là cách debug lỗi hình dạng **do thứ tự phép toán**, không phải do kiểu Java.

## 10. `takeWhile`/`dropWhile`: hình dạng tiền tố và hậu tố

Với một Stream **có thứ tự**, `takeWhile(predicate)` trả **tiền tố dài nhất** còn thỏa điều kiện; `dropWhile(predicate)` bỏ tiền tố đó và giữ toàn bộ phần còn lại.

```java
List<Integer> readings = List.of(2, 4, 9, 3, 6);

System.out.println(readings.stream()
    .filter(n -> n < 5)
    .toList()); // [2, 4, 3]

System.out.println(readings.stream()
    .takeWhile(n -> n < 5)
    .toList()); // [2, 4]

System.out.println(readings.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [9, 3, 6]
```

Cả ba pipeline đều trả `List<Integer>`, nhưng chúng diễn đạt **ba hình dạng khác nhau**. Nếu người dùng báo “thiếu số 3”, hãy kiểm tra đó là lỗi hay chính là ý nghĩa của `takeWhile`.

Trên **unordered Stream**, ngữ nghĩa lấy/bỏ tiền tố không còn gắn với một thứ tự nghiệp vụ cố định. Đừng dùng `unordered()` rồi tiếp tục đòi kết quả giống cắt từ đầu danh sách ban đầu.

## 11. Primitive Stream: thay đổi cả giao diện lẫn khả năng tổng hợp

Một bước `mapToLong` không chỉ “đổi mỗi giá trị sang long”. Nó đổi **kiểu Stream**:

```java
java.util.stream.LongStream amounts = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents);
```

Hình dạng:

```text
Stream<Order>  : [O-1, O-3, O-4]
       |
       | mapToLong(Order::amountCents)
       v
LongStream    : [120000, 80000, 50000]
       |
       | sum()
       v
long          : 250000
```

Đoạn mã:

```java
long totalPaidCents = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents)
    .sum();

System.out.println(totalPaidCents); // 250000
```

### 11.1. Một số terminal operation trên primitive Stream

| Biểu thức | Kiểu kết quả |
| --- | --- |
| `IntStream.sum()` | `int` |
| `LongStream.sum()` | `long` |
| `DoubleStream.sum()` | `double` |
| `IntStream.average()` | `OptionalDouble` |
| `LongStream.max()` | `OptionalLong` |
| `IntStream.summaryStatistics()` | `IntSummaryStatistics` |
| `IntStream.boxed()` | `Stream<Integer>` |

Ví dụ:

```java
java.util.OptionalDouble average = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountCents)
    .average();

System.out.println(average.orElse(0.0)); // 83333.33333333333
```

Điểm cần nhớ:

- `average()` trả `OptionalDouble` vì Stream có thể rỗng.
- `sum()` trả giá trị số nguyên ngay cả khi nguồn rỗng (với tổng thì kết quả là 0).
- Chuyển `IntStream` thành `Stream<Integer>` bằng `boxed()` nếu thật sự cần phương thức của Stream đối tượng.
- `IntStream.sum()` có thể tràn `int`; `LongStream.sum()` vẫn có thể tràn `long`. **Thay đổi shape không tự giải quyết tràn số**.

### 11.2. Sai khác giữa `map` và `mapToLong`

```java
// Kiểu: Stream<Long>, có boxing.
var boxedAmounts = orders.stream()
    .map(Order::amountCents);

// Kiểu: LongStream, không boxing từng giá trị kiểu Long.
var primitiveAmounts = orders.stream()
    .mapToLong(Order::amountCents);
```

Sau biểu thức thứ nhất, không có phương thức `sum()` trực tiếp trên `Stream<Long>`. Sau biểu thức thứ hai, `sum()` là terminal operation của `LongStream`.

Không cố sửa lỗi bằng cách ép kiểu `(LongStream) boxedAmounts`: đó là hai loại Stream khác nhau. Hãy chọn `mapToLong` hoặc một collector thích hợp.

## 12. Terminal operation: đọc kiểu đầu ra sau cùng

Các intermediate operation thường giữ hình thức `Stream<...>` hoặc primitive Stream; terminal operation **kết thúc** pipeline và tạo một kiểu kết quả khác.

| Terminal operation | Kiểu thường gặp | Khi nào hợp lý |
| --- | --- | --- |
| `toList()` | `List<T>` | Cần lưu tất cả phần tử đầu ra |
| `count()` | `long` | Cần số phần tử sau các bước biến đổi |
| `findFirst()` | `Optional<T>` | Có thể không tồn tại phần tử đầu tiên |
| `findAny()` | `Optional<T>` | Không bắt buộc lấy phần tử đầu theo thứ tự |
| `anyMatch(p)` | `boolean` | Cần biết có phần tử thỏa không |
| `min(comparator)` | `Optional<T>` | Có thể không có giá trị nhỏ nhất |
| `reduce(identity, op)` | `T` | Có identity và phép kết hợp |
| `reduce(op)` | `Optional<T>` | Không có identity; nguồn có thể rỗng |
| `collect(collector)` | `R` do Collector quyết định | `Map`, `List`, báo cáo nhiều cấp |
| `forEach(action)` | `void` | Thực hiện action, không trả collection |

Ví dụ:

```java
long paidCount = orders.stream()
    .filter(Order::paid)
    .count(); // 3

java.util.Optional<Order> firstPaid = orders.stream()
    .filter(Order::paid)
    .findFirst(); // Optional[O-1] theo thứ tự List

boolean hasLargePaidOrder = orders.stream()
    .filter(Order::paid)
    .anyMatch(order -> order.amountCents() >= 100_000L);
// true
```

### 12.1. `Optional<T>` là container giá trị tùy chọn, không phải Stream

```java
java.util.Optional<Order> found = orders.stream()
    .filter(o -> o.id().equals("MISSING"))
    .findFirst();

System.out.println(found.isPresent()); // false
```

Không gọi `found.toList()` như thể `found` vẫn là Stream. Nếu cần tiếp tục xử lý tùy chọn:

```java
String idOrFallback = found
    .map(Order::id)
    .orElse("NOT_FOUND");

System.out.println(idOrFallback); // NOT_FOUND
```

`Optional.map` là phương thức trên `Optional`, khác `Stream.map` về **kiểu kết quả**: `Optional<Order> → Optional<String>`.

Khi Stream có phần tử `null`, `findFirst()` không phải phương pháp an toàn để tạo một `Optional` “có null”: API có thể ném `NullPointerException` khi phần tử được chọn là null. Xác định chính sách null trước khi tìm phần tử.

## 13. `reduce`: hình dạng của bộ tích lũy và kết quả

Không phải `reduce` nào cũng yêu cầu kiểu bộ tích lũy giống kiểu phần tử đầu vào.

### 13.1. `reduce(identity, BinaryOperator<T>)`

```java
int sum = List.of(1, 2, 3)
    .stream()
    .reduce(0, Integer::sum);

System.out.println(sum); // 6
```

Kiểu đầu vào `Stream<Integer>`; identity và kết quả đều `Integer` (được unbox sang `int` khi gán).

### 13.2. `reduce(U identity, BiFunction<U,T,U>, BinaryOperator<U>)`

Ví dụ cộng tổng amount từ `Stream<Order>` mà tích lũy thành `Long`:

```java
long total = orders.stream()
    .filter(Order::paid)
    .reduce(
        0L,
        (acc, order) -> acc + order.amountCents(),
        Long::sum
    );

System.out.println(total); // 250000
```

Ở đây:

- `T = Order`: kiểu phần tử nguồn.
- `U = Long`: kiểu bộ tích lũy và kết quả.
- Accumulator nhận `(Long, Order)` và trả `Long`.
- Combiner nhận `(Long, Long)` và trả `Long`, dùng để ghép các phần nếu cần.

**Không viết combiner xử lý `Order`** trong overload này; nó kết hợp **hai bộ tích lũy `U`**, không lấy thêm một phần tử nguồn `T`.

Các phép reduce dùng trong pipeline song song phải có identity và tính kết hợp phù hợp. Không giữ một `ArrayList` mutable làm identity rồi dùng `add` trong accumulator của `reduce` để gom phần tử; `collect` là công cụ thích hợp hơn cho kiểu tích lũy mutable đó.

## 14. `collect`: thay đổi từ chuỗi phần tử sang cấu trúc báo cáo

`collect` có thể tạo `List`, `Set`, `Map`, hoặc một đối tượng tổng hợp domain. Khi đọc collector, phải đọc **cả downstream collector**, chứ không chỉ nhìn `groupingBy`.

### 14.1. Gom nhóm theo vùng: `Map<String, List<Order>>`

```java
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;

Map<String, List<Order>> byRegion = orders.stream()
    .collect(Collectors.groupingBy(Order::region));
```

Hình dạng:

```text
Stream<Order>
  [O-1(Bac), O-2(Nam), O-3(Bac), O-4(Trung)]
                |
                | groupingBy(region)
                v
Map<String, List<Order>>
  Bac   -> [O-1, O-3]
  Nam   -> [O-2]
  Trung -> [O-4]
```

Một `Map` chỉ có **ba khóa** nhưng vẫn chứa tổng cộng bốn đơn trong các danh sách giá trị. Vì thế nói “`groupingBy` làm mất một đơn” là sai: nó đổi **cấp tổ chức dữ liệu**, không nhất thiết bỏ phần tử.

### 14.2. Chỉ đếm theo vùng: `Map<String, Long>`

```java
Map<String, Long> counts = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.counting()
    ));

System.out.println(counts.get("Bac"));   // 2
System.out.println(counts.get("Trung")); // 1
System.out.println(counts.containsKey("Nam")); // false
```

Kiểu `Map<String,Long>` hoàn toàn khác `Map<String,List<Order>>`. Nếu chỉ nhìn chữ `groupingBy`, rất dễ hiểu nhầm giá trị Map là danh sách thay vì số đếm.

Vùng `Nam` không có đơn đã thanh toán, nên **không có khóa** tương ứng trong Map. Điều này khác với Map có khóa `Nam` và giá trị 0. Nếu báo cáo cần thể hiện cả vùng không có kết quả, phải bổ sung danh mục khóa chuẩn hoặc bước hoàn thiện báo cáo.

### 14.3. `mapping` đổi kiểu dữ liệu ở cấp nhóm

```java
Map<String, List<String>> idsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::id,
            Collectors.toList()
        )
    ));
```

`groupingBy` chia nguồn thành nhóm theo `String region`; `mapping` chuyển từng `Order` trong mỗi nhóm thành `String id`; `toList` tạo danh sách ID.

Không nhầm với:

```java
List<String> allIds = orders.stream()
    .map(Order::id)
    .toList();
```

Hai phép đều có chuyển `Order → String`, nhưng một kết quả là `Map<String,List<String>>` theo vùng, kết quả còn lại là `List<String>` phẳng.

### 14.4. `partitioningBy` và `toMap`

`partitioningBy(Order::paid)` cho Map có kiểu `Map<Boolean,List<Order>>`, chia nguồn thành hai phía true/false. Nó khác `groupingBy` ở kiểu khóa và quy tắc phân chia.

`toMap` chuyển các phần tử thành cặp khóa/giá trị. Nếu nhiều bản ghi cùng khóa mà không có merge function, `Collectors.toMap` có thể ném `IllegalStateException`:

```java
// Order O-1 và O-3 cùng region "Bac": khóa trùng.
// orders.stream().collect(Collectors.toMap(
//     Order::region, Order::amountCents
// )); // Có thể ném IllegalStateException khi gặp khóa trùng.
```

Cách hợp lệ khi cần tổng theo vùng:

```java
Map<String, Long> totals = orders.stream()
    .collect(Collectors.toMap(
        Order::region,
        Order::amountCents,
        Long::sum
    ));

System.out.println(totals.get("Bac")); // 200000
```

Hoặc dùng `groupingBy(..., summingLong(...))` với ý nghĩa tổng hợp rõ ràng hơn.

**Cảnh báo thứ tự:** `Collectors.groupingBy` và `Collectors.toMap` mặc định không hứa thứ tự duyệt khóa Map. Nếu báo cáo yêu cầu thứ tự hiển thị, hãy xác định một `mapFactory` phù hợp hoặc sắp xếp khi tạo đầu ra.

## 15. Cách tách pipeline thành các biến có kiểu để debug

Khi pipeline dài, có thể tách các stage để **đọc kiểu** mà không vội dùng debugger:

```java
import java.util.List;
import java.util.stream.Stream;

Stream<Order> source = orders.stream();

Stream<Order> paid = source.filter(Order::paid);

Stream<List<String>> tagLists = paid.map(Order::tags);

Stream<String> flattened = tagLists.flatMap(List::stream);

Stream<String> unique = flattened.distinct();

Stream<String> sorted = unique.sorted();

List<String> result = sorted.toList();
```

Kết quả:

```text
[backend, java, streams]
```

Mỗi biến trên có **một kiểu tĩnh rõ ràng**. Nếu đổi nhầm:

```java
// SAI kiểu ở biến:
// Stream<String> tagLists = paid.map(Order::tags);
```

compiler sẽ chỉ ra rằng `map(Order::tags)` tạo `Stream<List<String>>`, không phải `Stream<String>`.

### 15.1. Đừng dùng lại một Stream đã tiêu thụ

Cách debug sai:

```java
Stream<Order> paid = orders.stream().filter(Order::paid);

long count = paid.count();

// paid.toList(); // Không hợp lệ: cùng Stream đã bị tiêu thụ.
```

Cách đúng nếu muốn đo nhiều câu hỏi từ cùng collection:

```java
long count = orders.stream()
    .filter(Order::paid)
    .count();

List<Order> paidList = orders.stream()
    .filter(Order::paid)
    .toList();
```

Hai câu hỏi sử dụng **hai Stream khác nhau**. Với nguồn từ tệp hoặc kết nối, không phải lúc nào cũng có thể đọc lại tùy ý; khi đó cần quyết định vật hóa dữ liệu để debug, hoặc thiết kế phép thống kê trong **một lượt**.

### 15.2. Snapshot trung gian giúp nhìn hình dạng

Với bộ dữ liệu nhỏ, có thể tạm vật hóa một stage:

```java
List<Order> paidSnapshot = orders.stream()
    .filter(Order::paid)
    .toList();

List<List<String>> tagsSnapshot = paidSnapshot.stream()
    .map(Order::tags)
    .toList();

System.out.println(tagsSnapshot);
// [[java, backend], [java, streams], []]
```

Nhờ đó ta thấy cả **số phần tử ngoài (3)** và **số phần tử trong từng danh sách (2, 2, 0)**. Nhưng cách chụp snapshot thay đổi tính lazy, dùng thêm bộ nhớ và có thể không phù hợp với nguồn lớn/vô hạn. Chỉ dùng nó như kỹ thuật debug có kiểm soát.

## 16. `peek`: quan sát có giới hạn, không phải log bắt buộc

`peek` có thể hữu ích để quan sát những giá trị đi qua một stage:

```java
List<String> result = orders.stream()
    .filter(Order::paid)
    .peek(order -> System.out.println("paid: " + order.id()))
    .flatMap(order -> order.tags().stream())
    .peek(tag -> System.out.println("tag: " + tag))
    .distinct()
    .toList();
```

Hai `peek` nhìn **hai kiểu phần tử khác nhau**: lần đầu là `Order`, lần sau là `String`. Nếu không chú ý kiểu ở từng stage, thông điệp log dễ gây hiểu nhầm.

Tuy nhiên:

- `peek` là **intermediate operation**; không có terminal operation thì không có gì buộc pipeline phải chạy.
- Một terminal operation có thể được tối ưu mà không gọi một số stage trung gian nếu kết quả cuối vẫn đúng.
- Với `parallel()`, thứ tự và thread của các log có thể khác thứ tự gặp.
- Side effect trong `peek` không nên dùng để thực hiện ghi nhận nghiệp vụ bắt buộc.

Ví dụ quan trọng:

```java
long n = List.of("A", "B", "C").stream()
    .peek(System.out::println)
    .count();

System.out.println(n); // 3
// Không được khẳng định chắc chắn đã in cả A, B, C.
```

Vì nguồn có kích thước biết trước và `peek` không thay đổi số phần tử, `count()` có thể được triển khai mà không cần duyệt từng phần tử. Dùng `peek` cho **debug quan sát có điều kiện**, không dùng số lần callback được gọi làm chỉ số đúng/sai.

## 17. Dùng bảng truy vết thủ công trước khi sửa code

Một bảng tracing là kỹ thuật nhanh để xem lỗi xảy ra ở đâu. Với pipeline đầy đủ:

```java
List<String> result = orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .sorted()
    .toList();
```

Lập bảng:

| Bước | Kiểu tĩnh | Số phần tử ngoài | Nội dung/hình dạng quan sát |
| --- | --- | ---: | --- |
| `orders` | `List<Order>` | 4 | O-1, O-2, O-3, O-4 |
| `stream` | `Stream<Order>` | 4 | 4 bản ghi nguồn |
| `filter(paid)` | `Stream<Order>` | 3 | O-1, O-3, O-4 |
| `map(tags)` | `Stream<List<String>>` | 3 | List dài 2, 2, 0 |
| `flatMap` | `Stream<String>` | 4 | java, backend, java, streams |
| `distinct` | `Stream<String>` | 3 | java, backend, streams |
| `sorted` | `Stream<String>` | 3 | backend, java, streams |
| `toList` | `List<String>` | 3 | danh sách kết quả |

Khi so sánh kỳ vọng với thực tế, hãy chỉ rõ **bước đầu tiên khiến kỳ vọng diverge**. Ví dụ:

- Kỳ vọng 4 đơn nhưng sau `filter` chỉ còn 3: có đúng đang lọc paid?
- Kỳ vọng 4 tag nhưng sau `map` vẫn chỉ thấy 3 phần tử: đó là 3 **danh sách**, cần `flatMap`.
- Kỳ vọng 4 tag nhưng sau `distinct` chỉ còn 3: tag `java` bị loại trùng.
- Kỳ vọng thứ tự đầu vào nhưng sau `sorted` thay đổi: đúng theo hợp đồng sắp xếp.

Bảng tracing giúp phân biệt một **lỗi code** với một **hành vi đúng nhưng khác kỳ vọng nghiệp vụ**.

## 18. Bất biến (*invariant*) hữu ích khi kiểm thử shape

Để kiểm thử pipeline có hệ thống, hãy phát biểu những thuộc tính phải đúng.

### 18.1. Bất biến về số lượng

Với nguồn hữu hạn:

- `filter` không thể làm **tăng** số phần tử kết quả.
- `map` bảo toàn số phần tử **logic** khi đánh giá mỗi phần tử đầu vào.
- `flatMap` và `mapMulti` có thể tăng, giảm hoặc giữ số phần tử.
- `distinct` không tăng số phần tử.
- `sorted` không thay đổi tập phần tử, chỉ tổ chức lại thứ tự.
- `limit(k)` cho tối đa k phần tử, với k không âm.

Không nên biến bất biến về **kết quả** thành bất biến về **số lần callback thực thi**. Số lần thực thi có thể khác do short-circuit và tối ưu.

### 18.2. Bất biến về nội dung

Với bài toán “tag phân biệt của đơn đã thanh toán”:

- Mọi tag đầu ra phải đến từ ít nhất một đơn đã thanh toán.
- Không có tag trùng theo `String.equals`.
- Nếu đã gọi `sorted()`, danh sách phải theo thứ tự so sánh tương ứng.
- Đơn có danh sách tag rỗng không làm xuất hiện một tag `""` hoặc `null` trừ khi dữ liệu thực sự có giá trị đó.

### 18.3. Bất biến về cấu trúc

- Sau `groupingBy(Order::region)`, giá trị Map là danh sách các `Order` của cùng vùng.
- Sau `groupingBy(..., counting())`, giá trị Map là `Long`, không còn là danh sách.
- Sau `flatMap(Optional::stream)`, không còn lớp `Optional` bao quanh từng phần tử.
- Sau `findFirst()`, kết quả là `Optional<T>` và cần xử lý nhánh rỗng.

Những bất biến này có thể chuyển thành các assertion có thể tự chạy.

## 19. Kiểm thử bằng JUnit 5: kiểm tra cả giá trị và hình dạng

Bài học không cần cài thư viện test để đọc hiểu; đoạn dưới là **ví dụ JUnit 5** nếu dự án đã có dependency JUnit Jupiter.

Giả sử có các record và hàm:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(
    String id, String region, List<String> tags,
    long amountCents, boolean paid
) {}

class OrderQueries {
    static List<String> uniquePaidTags(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .flatMap(o -> o.tags().stream())
            .distinct()
            .sorted()
            .toList();
    }

    static Map<String, Long> paidCountByRegion(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }
}
```

Bộ kiểm thử (ở một tệp test thông thường của dự án):

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderQueriesTest {
    private static List<Order> sample() {
        return List.of(
            new Order("O-1", "Bac", List.of("java", "backend"), 120_000L, true),
            new Order("O-2", "Nam", List.of("frontend"), 90_000L, false),
            new Order("O-3", "Bac", List.of("java", "streams"), 80_000L, true),
            new Order("O-4", "Trung", List.of(), 50_000L, true)
        );
    }

    @Test
    void uniquePaidTagsHaveCorrectShapeAndOrder() {
        List<String> result = OrderQueries.uniquePaidTags(sample());

        assertEquals(List.of("backend", "java", "streams"), result);
        assertEquals(3, result.size());
        assertEquals(3, result.stream().distinct().count());
    }

    @Test
    void emptySourceProducesEmptyListAndMap() {
        assertEquals(List.of(), OrderQueries.uniquePaidTags(List.of()));
        assertEquals(Map.of(), OrderQueries.paidCountByRegion(List.of()));
    }

    @Test
    void groupsContainCountsRatherThanLists() {
        Map<String, Long> counts =
            OrderQueries.paidCountByRegion(sample());

        assertEquals(Long.valueOf(2L), counts.get("Bac"));
        assertEquals(Long.valueOf(1L), counts.get("Trung"));
        assertFalse(counts.containsKey("Nam"));
    }
}
```

Điểm cần học không phải số lượng assertion, mà là **kiểm tra ở nhiều cấp**:

1. **Giá trị:** tag nào xuất hiện?
2. **Hình dạng:** kết quả là `List<String>` hay `Map<String,Long>`?
3. **Số lượng:** có đúng 3 tag phân biệt?
4. **Thứ tự:** `sorted` có thực sự được áp dụng?
5. **Trường hợp rỗng:** nguồn rỗng tạo danh sách/Map rỗng?
6. **Không có nhóm:** khóa `Nam` vắng mặt thay vì bị gán 0 tùy tiện?

Với Map, nên so sánh theo cặp khóa/giá trị hoặc `Map.equals` thay vì dựa vào chuỗi in ra có thứ tự nào đó.

## 20. Chương trình Java 17 hoàn chỉnh để tự kiểm tra

Ví dụ sau có thể lưu thành `PipelineShapeWalkthrough.java` và biên dịch bằng Java 17 trở lên.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PipelineShapeWalkthrough {

    record Order(
        String id, String region, List<String> tags,
        long amountCents, boolean paid
    ) {}

    static List<Order> data() {
        return List.of(
            new Order("O-1", "Bac", List.of("java", "backend"), 120_000L, true),
            new Order("O-2", "Nam", List.of("frontend"), 90_000L, false),
            new Order("O-3", "Bac", List.of("java", "streams"), 80_000L, true),
            new Order("O-4", "Trung", List.of(), 50_000L, true)
        );
    }

    static List<String> uniquePaidTags(List<Order> orders) {
        Stream<Order> paid = orders.stream().filter(Order::paid);

        Stream<List<String>> nested = paid.map(Order::tags);

        Stream<String> flat = nested.flatMap(List::stream);

        return flat.distinct().sorted().toList();
    }

    static Map<String, Long> countPaidByRegion(List<Order> orders) {
        return orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.counting()
            ));
    }

    public static void main(String[] args) {
        List<Order> orders = data();

        List<String> tags = uniquePaidTags(orders);
        Map<String, Long> counts = countPaidByRegion(orders);
        long totalPaid = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountCents)
            .sum();

        System.out.println("tags = " + tags);
        System.out.println("Bac = " + counts.get("Bac"));
        System.out.println("Trung = " + counts.get("Trung"));
        System.out.println("paid total = " + totalPaid);

        if (!tags.equals(List.of("backend", "java", "streams"))) {
            throw new AssertionError("Unexpected tags");
        }

        if (!Long.valueOf(2L).equals(counts.get("Bac"))) {
            throw new AssertionError("Unexpected Bac count");
        }

        if (totalPaid != 250_000L) {
            throw new AssertionError("Unexpected paid total");
        }
    }
}
```

Kết quả mong đợi:

```text
tags = [backend, java, streams]
Bac = 2
Trung = 1
paid total = 250000
```

Chương trình không cần `peek` hoặc side effect trong pipeline. Những biến trung gian được đặt kiểu rõ ràng, khiến thay đổi loại phần tử lộ ra ngay ở thời điểm biên dịch.

## 21. Nguyên nhân lỗi shape thường bị bỏ sót

### 21.1. Null, danh sách rỗng và dữ liệu thiếu

`List.of(...)` và `List.copyOf(...)` không chấp nhận null. Nhưng một `Stream` có thể lấy dữ liệu từ nguồn khác có phần tử null. Nếu gọi `Order::tags` trên một `Order` null, pipeline có thể ném `NullPointerException`. Nếu `Order.tags()` trả null, `flatMap(order -> order.tags().stream())` cũng ném lỗi.

Cách xử lý phụ thuộc **hợp đồng dữ liệu**, ví dụ loại bỏ phần tử null nếu null được phép ở nguồn:

```java
import java.util.Objects;

List<String> safeNames = someNames.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .toList();
```

Đoạn trên giả định `someNames` là một collection chuỗi có thể chứa null. Không nên tự tiện lọc null nếu null biểu diễn một trạng thái nghiệp vụ cần thống kê.

### 21.2. `Map` không có thứ tự khóa mặc định

Nếu có `Map<String,List<Order>>`, thứ tự trong `List<Order>` của từng nhóm và thứ tự duyệt các khóa `String` là **hai chuyện khác nhau**. `groupingBy` mặc định không cam kết thứ tự các khóa trong Map; nếu nghiệp vụ cần thứ tự, hãy chọn cách xây Map và kiểm thử riêng.

### 21.3. `toList()` không giống mọi dạng `Collectors.toList()`

`Stream.toList()` (Java 16+) trả danh sách **không thể chỉnh sửa** theo hợp đồng. `Collectors.toList()` không cam kết một implementation, tính mutable hay khả năng serialization cụ thể. Khi việc chỉnh sửa danh sách sau thu thập là yêu cầu chính thức, nên tự tạo `ArrayList` hoặc dùng collector được thiết kế cho mục tiêu đó.

### 21.4. Type inference với `var` có thể che vấn đề shape

`var result = ...` thường tiện lợi, nhưng khi debug có thể che khuất sự khác biệt giữa `Stream<List<String>>` và `Stream<String>` đối với người mới.

Tạm dùng các biến khai báo kiểu tường minh giúp nhìn rõ:

```java
Stream<List<String>> beforeFlatten = orders.stream()
    .map(Order::tags);

Stream<String> afterFlatten = orders.stream()
    .flatMap(o -> o.tags().stream());
```

Không bắt buộc từ bỏ `var` trong code sản xuất; mục tiêu là có cách **kiểm tra giả thuyết về kiểu** khi code khó đọc.

## 22. `parallel()` và `unordered()`: shape giống nhưng thứ tự khác

Với `List` có thứ tự, những pipeline không có side effect và sử dụng terminal operation phù hợp thường có kết quả logic giống nhau giữa tuần tự và song song:

```java
List<String> sequential = orders.stream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .sorted()
    .toList();

List<String> parallel = orders.parallelStream()
    .filter(Order::paid)
    .flatMap(o -> o.tags().stream())
    .distinct()
    .sorted()
    .toList();

System.out.println(sequential.equals(parallel)); // true
```

Tuy nhiên:

- `forEach` trong parallel Stream **không bảo đảm** action chạy theo encounter order.
- `findAny` không hứa trả phần tử đầu tiên.
- `unordered()` bỏ ràng buộc thứ tự; những thao tác nhạy với thứ tự như `limit` hoặc `takeWhile` có thể có ngữ nghĩa khác khi nguồn không còn ordered.
- `groupingByConcurrent` trả Map có đặc tính concurrent/unordered, không được suy thứ tự phần tử trong từng nhóm từ thứ tự đầu vào.
- Lambda đọc/ghi **trạng thái mutable chung** có thể gây data race và khiến shape kết quả bất định.

**Debug song song:** trước tiên thử pipeline **tuần tự** với đầu vào nhỏ, xác minh các bất biến về kiểu và kết quả; sau đó chạy song song và so sánh những tính chất mà hợp đồng thật sự bảo đảm. Không so sánh log `peek` như thể log là thứ tự dữ liệu được bảo đảm.

## 23. `Spliterator` và nguồn tự định nghĩa ảnh hưởng cách đọc shape

Với các nguồn chuẩn như `ArrayList`, `Stream.of` hoặc `IntStream.range`, ta thường biết rõ encounter order và kích thước. Nhưng một `Spliterator` tùy chỉnh có thể không biết số phần tử trước, có thể chia nguồn khác nhau hoặc không bảo đảm thứ tự.

```java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> spliterator =
    List.of("A", "B", "C").spliterator();

System.out.println(spliterator.estimateSize()); // 3
System.out.println(
    spliterator.hasCharacteristics(Spliterator.ORDERED)
); // true
```

Các cờ như `ORDERED`, `SIZED` và `SUBSIZED` là **hợp đồng nguồn** để framework quyết định cách xử lý. Nếu custom Spliterator khai báo `SIZED` nhưng `estimateSize()` sai hoặc `trySplit()` làm mất/trùng phần tử, kết quả pipeline có thể sai dù `map` và `filter` hoàn toàn đúng.

Khi debug shape từ custom source, hãy kiểm tra **đầu vào và đặc tính nguồn trước**, thay vì chỉ nhìn đoạn code downstream. `StreamSupport` dùng Spliterator làm nguồn Stream, nhưng không bảo đảm sửa được lỗi hợp đồng mà Spliterator đã khai báo.

## 24. Stream Gatherers (Java 24+): một stage đổi hẳn cấp dữ liệu

`Stream.gather(...)` cho phép tạo thao tác trung gian linh hoạt, thường có trạng thái. Đặc biệt `Gatherers.windowFixed(k)` và `Gatherers.windowSliding(k)` chuyển `Stream<T>` thành **`Stream<List<T>>`**.

Ví dụ Java 24+:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> fixed = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList();

List<List<Integer>> sliding = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(fixed);   // [[1, 2, 3], [4, 5]]
System.out.println(sliding); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Hãy đọc shape theo hai cấp:

| Stage | Kiểu | Kết quả quan sát |
| --- | --- | --- |
| `Stream.of(1,...,5)` | `Stream<Integer>` | 5 số |
| `gather(windowFixed(3))` | `Stream<List<Integer>>` | 2 danh sách: 3 và 2 số |
| `gather(windowSliding(3))` | `Stream<List<Integer>>` | 3 danh sách: mỗi danh sách 3 số |
| `map(window -> window.size())` | `Stream<Integer>` | Số lượng phần tử trong từng cửa sổ |
| `toList()` | `List<Integer>` | Danh sách kích thước cửa sổ |

Nếu nguồn có 1 hoặc 2 phần tử mà `windowSliding(3)` được dùng, API phát **một cửa sổ ngắn** chứa toàn bộ nguồn; nguồn rỗng không phát cửa sổ nào. Vì thế đừng mặc định mỗi `List<Integer>` đều dài đúng 3.

### 24.1. Tính chỉ số ngay sau bước tạo cửa sổ

```java
List<Long> windowTotals = Stream.of(10L, 20L, 30L, 40L)
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream().mapToLong(Long::longValue).sum())
    .toList();

System.out.println(windowTotals); // [60, 90]
```

Kiểu lần lượt:

```text
Stream<Long>
    -> Stream<List<Long>>
    -> Stream<Long>
    -> List<Long>
```

Đây là một **chuyển đổi hình dạng nhiều cấp**, dù code chỉ gồm vài dòng. Từ `Stream<Long>` ban đầu, các phần tử được nhóm lại, từng nhóm được tổng hợp rồi lại trở về dạng phẳng `Stream<Long>`.

### 24.2. Không dùng `gather` trực tiếp trên `IntStream`

Trong Java 24, `gather` được cung cấp trên `Stream<T>`; `IntStream` không có `gather` tương ứng. Khi cần Gatherer cho nguồn `int`, có thể `boxed()` trước:

```java
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

Điểm cần debug: **`IntStream → Stream<Integer> → Stream<List<Integer>> → List<List<Integer>>`**. Boxing có thể có chi phí khi dữ liệu rất lớn; không nên dùng Gatherer nếu chỉ cần tính tổng trên primitive Stream.

## 25. Nguồn I/O: shape đúng nhưng vòng đời sai vẫn là lỗi

`Files.lines(path)` trả `Stream<String>` chứa các dòng từ tệp, với tài nguyên đọc tệp cần đóng. Các stage sau có thể tạo ra đúng kiểu và nội dung, nhưng nếu quên đóng thì pipeline vẫn có lỗi quản lý tài nguyên.

Ví dụ đếm số dòng chứa `ERROR`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> line.contains("ERROR"))
            .count();
    }
}
```

Hình dạng:

```text
Path
  |
  | Files.lines(path)
  v
Stream<String> : các dòng, nguồn có tài nguyên I/O
  |
  | filter(contains ERROR)
  v
Stream<String> : các dòng lỗi
  |
  | count()
  v
long           : số dòng lỗi
```

`try-with-resources` đóng nguồn ngay cả khi có ngoại lệ hoặc pipeline dừng sớm. Terminal operation `count` **không tự thay thế `close()`**.

Nếu API trả Stream còn sống cho caller, cần ghi rõ **bên nào sở hữu và đóng** tài nguyên. Khi debug một pipeline lazy đọc tệp, đừng trả Stream từ bên trong `try-with-resources` rồi cố tiêu thụ nó sau khi nguồn đã đóng.

## 26. Checklist gỡ lỗi một pipeline dài

Khi gặp một pipeline “chạy được nhưng kết quả sai”, có thể kiểm tra theo thứ tự sau:

1. **Nguồn:** Dữ liệu đầu vào là gì? `List`, `Map`, `Set`, tệp hay custom `Spliterator`? Có thứ tự không?
2. **Kiểu ban đầu:** `Stream<T>` chứa kiểu phần tử gì?
3. **Đổi kiểu:** Stage nào chuyển `T → R`, hoặc `Stream<T> → IntStream`?
4. **Cấp lồng nhau:** Có `Stream<List<R>>` hoặc `Stream<Optional<R>>` cần flatten không?
5. **Số lượng:** Stage nào lọc, nhân bản, gộp, loại trùng hoặc giới hạn phần tử?
6. **Thứ tự:** Có `sorted`, `unordered`, `parallel` hoặc collector không bảo đảm thứ tự?
7. **Giá trị thiếu:** Có `null`, nhóm rỗng hoặc `Optional.empty()` không?
8. **Kết quả terminal:** `List`, `Map`, `Optional`, primitive hay `void`?
9. **Trạng thái:** Lambda/collector có phụ thuộc biến mutable ngoài pipeline không?
10. **Tài nguyên:** Có nguồn I/O phải đóng hoặc pipeline dừng sớm không?
11. **Kiểu số:** `int`, `long`, `double`, `BigDecimal` có đúng miền và độ chính xác?
12. **Kiểm thử:** Có test nguồn rỗng, phần tử trùng, danh sách con rỗng và dữ liệu đổi thứ tự?

### 26.1. Những dấu hiệu có thể nhận ra rất nhanh

| Dấu hiệu | Nghi vấn | Hướng kiểm tra |
| --- | --- | --- |
| Có `List<List<T>>` ngoài dự kiến | Dùng `map` nơi muốn `flatMap` | In/suy kiểu từng stage |
| Có ít phần tử hơn sau `distinct` | Giá trị bị trùng theo `equals` | Dữ liệu trùng có hợp lệ không |
| `Map` có ít khóa hơn số bản ghi | `groupingBy` đã gom theo khóa | Đếm cả số phần tử trong từng nhóm |
| Thiếu khóa nhóm sau `filter` | Không có phần tử thỏa ở nhóm đó | Vắng khóa hay giá trị 0 |
| `findFirst` trả rỗng | Không có phần tử trong phạm vi tìm | Kiểm tra filter và thứ tự |
| `toMap` ném lỗi | Khóa trùng nhưng thiếu merge function | Chọn phép gộp đúng nghiệp vụ |
| `count()` đúng nhưng `peek` không in đủ | Stage quan sát có thể bị tối ưu bỏ | Không dùng `peek` cho logic bắt buộc |
| `parallel` cho kết quả bất định | Side effect hoặc nguồn/collector sai hợp đồng | Loại trạng thái dùng chung |
| Stream đã đóng/đã dùng | Terminal operation hoặc close trước đó | Tạo Stream mới hoặc sửa vòng đời |
| Chạy trên Java 17 báo không có `gather` | API yêu cầu Java 24+ | Nâng JDK hoặc dùng phương án khác |

## 27. Bài tập thực hành

### Bài 1: Ghi kiểu từng stage

Cho:

```java
orders.stream()
    .filter(Order::paid)
    .map(Order::tags)
    .flatMap(List::stream)
    .distinct()
    .toList();
```

Hãy viết kiểu Java **trước và sau mỗi phương thức**. Với bộ dữ liệu mẫu, ghi số lượng phần tử ngoài sau từng stage và liệt kê kết quả.

### Bài 2: Thay `map` bằng `flatMap`

Đầu vào `List.of(List.of(1,2), List.of(), List.of(3))`. So sánh kết quả của `map(List::stream).toList()`, `map(list -> list).toList()` và `flatMap(List::stream).toList()`. Những trường hợp này khác nhau ở kiểu, cấp lồng hay số phần tử nào?

### Bài 3: `filter` với `map` boolean

Tạo `List<Order>` chứa cả paid và unpaid. So sánh `filter(Order::paid).count()` với `map(Order::paid).count()`. Tại sao biểu thức thứ hai không đếm số đơn đã thanh toán, ngay cả khi số callback `map` có thể được tối ưu?

### Bài 4: Cardinality qua `distinct` và `limit`

Với `["A","A","B","C"]`, so sánh `distinct().limit(2)` và `limit(2).distinct()`. Phát biểu bằng từ ngữ nghiệp vụ từng pipeline đang làm gì.

### Bài 5: Primitive Stream và kết quả tùy chọn

Từ `orders`, tạo tổng amount đã thanh toán dưới dạng `long` và trung bình dưới dạng `OptionalDouble`. Kiểm tra nguồn rỗng. Vì sao `average()` cần kiểu Optional còn `sum()` thường không?

### Bài 6: Đọc collector nhiều cấp

Suy kiểu của:

```java
orders.stream().collect(
    Collectors.groupingBy(
        Order::region,
        Collectors.mapping(Order::id, Collectors.toList())
    )
);
```

Với các đơn ở vùng `Bac`, kết quả value là `List<Order>`, `List<String>` hay `Long`? Viết test chứng minh.

### Bài 7: Xử lý khóa vắng mặt

Tính số đơn đã thanh toán theo vùng. Tại sao `Nam` không có khóa trong Map? Nếu dashboard phải luôn hiển thị `Bac`, `Nam` và `Trung`, hãy đề xuất bước bổ sung khóa với số đếm 0.

### Bài 8: Tìm lỗi khi debug bằng `peek`

Một pipeline gọi `peek(System.out::println).count()` trên `List` nhưng không thấy log. Giải thích vì sao điều này có thể hợp lệ. Viết cách kiểm thử số phần tử thực bằng assertion thay vì dựa vào số dòng log.

### Bài 9: Kiểm thử Map không theo thứ tự in

Tạo Map bằng `groupingBy` và viết test so sánh số lượng mỗi khóa. Vì sao không nên so sánh chuỗi in ra của Map như thể nó có thứ tự mặc định?

### Bài 10: Truy vết Gatherer trên Java 24

Với `Stream.of(1,2,3,4,5).gather(Gatherers.windowSliding(3)).map(List::size).toList()`, ghi kiểu tại mỗi bước và kết quả cuối. Thử nguồn chỉ có hai phần tử rồi giải thích trường hợp cửa sổ ngắn.

### Bài 11: Truy vết nguồn I/O

Với `Files.lines(path).filter(...).limit(10).toList()`, chỉ ra kiểu tại từng stage, điều kiện dừng sớm, và nơi phải đặt `try-with-resources`. Tại sao `toList()` không tự bảo đảm đóng tệp?

### Bài 12: Chuyển pipeline thành bảng tracing

Lấy một pipeline do bạn từng viết, tạo bảng có các cột: stage, kiểu Java, số phần tử logic, hình dạng/độ lồng, thứ tự. Xác định stage nào thay đổi đúng **kiểu**, stage nào thay đổi **số phần tử**, stage nào đổi **cấu trúc kết quả**, stage nào làm thay đổi **thứ tự**.

## 28. Câu hỏi tự kiểm tra

- Sự khác nhau giữa kiểu tĩnh của Stream và hình dạng dữ liệu runtime là gì?
- Vì sao `filter(Order::paid)` vẫn trả `Stream<Order>` thay vì `Stream<Boolean>`?
- Khi nào `map(Order::tags)` trả `Stream<List<String>>`?
- `flatMap(List::stream)` thay đổi kiểu và số phần tử thế nào?
- `mapMulti` có thể phát bao nhiêu kết quả cho một phần tử đầu vào?
- `distinct`, `sorted` và `limit` có thay đổi kiểu phần tử không? Có thay đổi shape không?
- Khi nào `findFirst` trả `Optional.empty()`?
- Vì sao `IntStream.average` trả `OptionalDouble`?
- `Collectors.groupingBy` với downstream `counting` trả kiểu Map nào?
- Vì sao thiếu khóa nhóm khác với khóa có giá trị 0?
- `reduce` dạng ba tham số khác reduce dạng hai tham số thế nào về kiểu bộ tích lũy?
- Vì sao không thể dùng lại Stream sau `count()`?
- `peek` có phải nơi phù hợp để đếm nghiệp vụ không?
- `unordered()` làm thay đổi những bảo đảm nào về thứ tự?
- Vì sao `Stream.gather(windowFixed(...))` tạo một cấp `List<T>` mới trong phần tử?
- Vì sao debug pipeline đọc `Files.lines` phải quan tâm `close()`?
- Để kiểm thử pipeline, vì sao cần kiểm tra nguồn rỗng, dữ liệu trùng và danh sách con rỗng?

## 29. Tài liệu tham khảo

Các tài liệu chính thức hỗ trợ tra cứu kiểu trả về và hợp đồng operation:

1. [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `filter`, `map`, `flatMap`, `mapMulti`, `toList`, `reduce`, `collect` và các terminal operation.
2. [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `mapping`, `counting`, `toMap` và các downstream collector.
3. [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): chuyển đổi primitive, `sum`, `average` và `summaryStatistics`.
4. [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): xử lý giá trị có thể vắng mặt.
5. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): `ORDERED`, `SIZED`, `SUBSIZED` và đặc tính nguồn.
6. [Java SE 24 — Stream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html): phương thức `gather`.
7. [Java SE 24 — Gatherers](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): các phép cửa sổ và biến đổi trung gian có trạng thái.

**Ghi nhớ:** Khi đọc một pipeline, luôn theo dõi **hai dòng thông tin song song**: **kiểu Java** (ví dụ `Stream<Order> → Stream<List<String>> → Stream<String> → List<String>`) và **hình dạng dữ liệu** (4 đơn → 3 đơn → 3 danh sách → 4 tag → 3 tag phân biệt). Kiểu giúp phát hiện nhầm lẫn ở thời điểm biên dịch, còn hình dạng và bất biến giúp phát hiện lỗi nghiệp vụ khi chạy. Dùng bảng tracing, biến có kiểu rõ ràng và kiểm thử đầu vào nhỏ; quan sát bằng `peek` có giới hạn, đồng thời luôn kiểm tra thứ tự, trạng thái song song, kiểu số và vòng đời nguồn I/O.
