# Lựa chọn quy tắc giữ bản ghi đầu, cuối hoặc gộp giá trị

> **Chương:** Thu thập thành Map  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Chọn đúng quy tắc xử lý khóa trùng khi thu thập Stream thành Map bằng `Collectors.toMap`: giữ bản ghi xuất hiện đầu tiên, giữ bản ghi xuất hiện cuối cùng, hoặc gộp dữ liệu của nhiều bản ghi; nhận diện sự khác nhau giữa thứ tự nguồn và thứ tự nghiệp vụ.

Trong **JAVA_STREAM_API**, các phép toán trung gian như `filter` và `map` tạo nên pipeline xử lý dữ liệu khai báo. Khi kết quả cần truy cập theo khóa, ta thường kết thúc pipeline bằng `collect(Collectors.toMap(...))`. Vấn đề nảy sinh khi **nhiều phần tử tạo ra cùng một khóa**: một `Map<K,V>` thông thường chỉ chứa một giá trị ứng với mỗi khóa, vậy phải chọn giá trị nào?

Ví dụ hệ thống nhận nhiều bản ghi cập nhật cho cùng một sản phẩm:

| Mã sự kiện | Mã sản phẩm | Số lượng | Thời điểm nghiệp vụ |
| --- | --- | ---: | ---: |
| E01 | A | 4 | 100 |
| E02 | B | 3 | 101 |
| E03 | A | 2 | 105 |
| E04 | A | 6 | 103 |
| E05 | B | 7 | 98 |

Nếu cần lưu mỗi sản phẩm một giá trị, có ít nhất bốn quy tắc hợp lệ tùy bài toán:

- **Giữ lần gặp đầu tiên:** với A chọn E01; với B chọn E02.
- **Giữ lần gặp cuối cùng:** với A chọn E04; với B chọn E05.
- **Gộp số lượng:** với A tính `4 + 2 + 6 = 12`; với B tính `3 + 7 = 10`.
- **Giữ bản ghi có thời điểm mới nhất:** với A chọn E03 (105); với B chọn E02 (101).

Bản ghi **cuối cùng trong Stream không nhất thiết là bản ghi mới nhất về thời gian nghiệp vụ**. Đó là khác biệt quan trọng nhất khi thiết kế hàm xử lý khóa trùng.

Bài học này kết nối trực tiếp với `collect`, hợp đồng `Collector`, grouping, xử lý song song và thứ tự của `Spliterator` trong module Java Stream API. Những nguyên tắc về trạng thái, tính kết hợp và chi phí gộp dữ liệu cũng hữu ích khi xây collector tùy chỉnh và các phép xử lý Stream nâng cao như Stream Gatherers.

Các ví dụ chính sử dụng Java 17+ với `record` và `List.of`. `Collectors.toMap` và các overload có hàm gộp đã có từ Java 8.

## 1. Vì sao toMap gặp xung đột khóa?

`Collectors.toMap` biến các phần tử của `Stream<T>` thành cặp khóa–giá trị:

```text
Stream<T>
   │
   ├── keyMapper(T) ───────► K
   │
   └── valueMapper(T) ─────► V
                              │
                              ▼
                         Map<K, V>
```

Giả sử có các sản phẩm với mã nhóm:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String sku, String category, long price) {}

List<Product> products = List.of(
    new Product("P01", "Sách", 100_000),
    new Product("P02", "Sách", 150_000),
    new Product("P03", "Thiết bị", 200_000)
);
```

Nếu chọn SKU làm khóa, mỗi giá trị là duy nhất:

```java
Map<String, Product> bySku = products.stream()
    .collect(Collectors.toMap(
        Product::sku,
        product -> product
    ));

// bySku chứa 3 mục vì mỗi sku chỉ xuất hiện một lần.
```

Nếu chọn `category` làm khóa:

```java
Map<String, Product> byCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        product -> product
    )); // IllegalStateException: khóa "Sách" bị trùng.
```

**Overload hai tham số của `toMap` không tự chọn bản ghi đầu hay cuối.** Khi gặp các phần tử ánh xạ đến khóa trùng theo quy tắc của Map, collector mặc định ném `IllegalStateException`. Điều này giúp phát hiện lỗi dữ liệu nếu nghiệp vụ thật sự yêu cầu khóa phải duy nhất.

Một cách xử lý hợp lệ là **nêu rõ merge function**. Cách xử lý khác là thiết kế lại khóa hoặc dùng `groupingBy` nếu cần giữ mọi bản ghi.

## 2. Đọc đúng các overload của Collectors.toMap

`Collectors` có ba overload quan trọng:

```java
// 1) Không khai báo quy tắc khi khóa bị trùng:
toMap(keyMapper, valueMapper);

// 2) Có quy tắc gộp khi khóa bị trùng:
toMap(keyMapper, valueMapper, mergeFunction);

// 3) Có cả quy tắc gộp và loại Map cần tạo:
toMap(keyMapper, valueMapper, mergeFunction, mapFactory);
```

Hình dạng kiểu generic (rút gọn để dễ đọc):

```java
<T, K, U> Collector<T, ?, Map<K, U>> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);

<T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
);
```

| Tham số | Chức năng | Ví dụ |
| --- | --- | --- |
| `keyMapper` | Trích khóa `K` từ một phần tử `T` | `Product::category` |
| `valueMapper` | Trích giá trị `U` từ một phần tử `T` | `Product::price` |
| `mergeFunction` | Nhận hai giá trị `U` khi chúng ứng với cùng khóa và trả một giá trị kết hợp | `(oldValue, newValue) -> oldValue` |
| `mapFactory` | Tạo loại Map cần thu thập | `LinkedHashMap::new`, `TreeMap::new` |

`mergeFunction` có kiểu `BinaryOperator<U>`: nhận hai giá trị **cùng kiểu `U`** và trả một giá trị kiểu `U`. Nó không nhận trực tiếp khóa `K` hay phần tử `T` gốc, trừ khi `valueMapper` giữ lại cả đối tượng đầu vào làm giá trị.

Ví dụ:

```java
Map<String, Long> maxPriceByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category, // K = String
        Product::price,    // U = Long (boxing từ long)
        Long::max          // BinaryOperator<Long>
    ));

// "Sách" -> 150000; "Thiết bị" -> 200000.
```

Nếu muốn gộp dựa vào những thuộc tính khác của `Product` (chẳng hạn ngày cập nhật hoặc độ ưu tiên), ta có thể dùng `Function.identity()` làm `valueMapper` để giữ nguyên đối tượng.

## 3. Giữ bản ghi đầu tiên: (first, next) -> first

Trong một Stream **có thứ tự gặp phần tử xác định** (*encounter order*), quy tắc giữ bản ghi xuất hiện đầu tiên thường được viết:

```java
Map<String, Product> firstByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        product -> product,
        (first, next) -> first
    ));
```

Trong ví dụ, nhóm `"Sách"` giữ P01 vì P01 xuất hiện trước P02 trong danh sách nguồn.

Có thể dùng `Function.identity()` để trả phần tử ban đầu:

```java
import java.util.function.Function;

Map<String, Product> firstByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        Function.identity(),
        (first, next) -> first
    ));
```

### 3.1. "Đầu tiên" là theo thứ tự nào?

Trong ví dụ trên, `products` là `List` có thứ tự và `products.stream()` giữ *encounter order*. Nếu dữ liệu đến từ một `HashSet`, một Stream bị gọi `unordered()` hoặc một nguồn không khai báo thứ tự, **không có căn cứ để xác định bản ghi nào là đầu tiên theo nghiệp vụ**.

So sánh:

```java
List<String> names = List.of("An", "Bình", "Chi");

// Với List và Stream tuần tự, thứ tự gặp là An, Bình, Chi.
String first = names.stream().findFirst().orElseThrow();
```

Với một Stream unordered, khái niệm “đầu” không có bảo đảm ổn định giống List. Muốn chọn bản ghi đầu tiên theo thời gian tạo, **đưa thời gian vào quy tắc so sánh**, thay vì phụ thuộc một cách ngầm định vào thứ tự dữ liệu đầu vào.

### 3.2. Khi nào giữ bản ghi đầu?

Quy tắc này phù hợp khi:

- Danh sách đầu vào đã được sắp xếp theo **độ ưu tiên cao nhất trước**.
- Cần duy trì giá trị đầu tiên được nhập trong một luồng sự kiện có thứ tự.
- Bài toán quy định “mỗi khóa lấy lần xuất hiện đầu tiên trong dữ liệu đầu vào”.

Nếu mục tiêu là lấy bản ghi có **thời gian nhỏ nhất**, hãy sử dụng Comparator trực tiếp như ở mục 6; cách này còn rõ ràng khi thứ tự nguồn chưa được bảo đảm.

### 3.3. Không được hiểu first là biến global giữ một lần

Trong collector, `(first, next) -> first` chỉ định **cách giải quyết hai giá trị đang tranh cùng khóa**. Nó không tạo biến toàn cục và không có nghĩa toàn bộ Stream chỉ giữ một phần tử. Mỗi khóa có lịch sử xung đột riêng.

Vì vậy:

```text
[A: E01, B: E02, A: E03, A: E04, B: E05]
                     │
                giữ đầu tiên
                     ▼
                 A → E01
                 B → E02
```

## 4. Giữ bản ghi cuối cùng: (oldValue, newValue) -> newValue

Để chọn giá trị gặp sau theo thứ tự nguồn:

```java
Map<String, Product> lastByCategory = products.stream()
    .collect(Collectors.toMap(
        Product::category,
        Function.identity(),
        (oldValue, newValue) -> newValue
    ));
```

Trong nhóm `"Sách"`, P02 thay P01. Quy tắc thường được gọi là **last wins**.

Ví dụ số:

```java
record Reading(String sensorId, int value) {}

List<Reading> readings = List.of(
    new Reading("S1", 10),
    new Reading("S2", 20),
    new Reading("S1", 15),
    new Reading("S1", 18)
);

Map<String, Integer> latestInSequence = readings.stream()
    .collect(Collectors.toMap(
        Reading::sensorId,
        Reading::value,
        (oldValue, newValue) -> newValue
    ));

// "S1" -> 18; "S2" -> 20.
```

### 4.1. "Cuối cùng" không đồng nghĩa "mới nhất"

Giả sử dữ liệu đến trễ:

```text
Sự kiện xuất hiện trong danh sách:
E01 (thời điểm 100)
E03 (thời điểm 105)
E04 (thời điểm 103)

last wins theo encounter order = E04
newest theo timestamp         = E03
```

Nếu dữ liệu đến từ hàng đợi, API phân trang hoặc các dịch vụ gửi lại bản ghi cũ, thứ tự xuất hiện có thể khác thứ tự thời gian. **Last wins chỉ đúng với bài toán “ghi đè bằng phần tử đến sau”**, không mặc định đúng với bài toán “giá trị cập nhật mới nhất”.

### 4.2. Last wins có thay thứ tự các khóa trong Map không?

Việc thay giá trị của một khóa không nhất thiết di chuyển khóa ấy đến cuối thứ tự duyệt Map. Ví dụ với `LinkedHashMap` mặc định lưu thứ tự chèn:

```java
Map<String, Reading> map = readings.stream()
    .collect(Collectors.toMap(
        Reading::sensorId,
        Function.identity(),
        (oldValue, newValue) -> newValue,
        LinkedHashMap::new
    ));
```

Ở đây khóa `S1` xuất hiện đầu, nên vị trí của khóa ấy được ghi nhận khi chèn lần đầu. Các lần ghi đè **giá trị** của `S1` không tự biến nó thành khóa được chèn gần đây nhất. `LinkedHashMap` ở chế độ insertion order không di chuyển vị trí khóa chỉ vì cập nhật một giá trị đã tồn tại.

Nếu cần sắp khóa theo thời gian cập nhật cuối cùng, phải chọn cấu trúc hoặc quy tắc sắp xếp dành riêng cho yêu cầu đó.

## 5. Gộp giá trị: sum, max, min và quy tắc nghiệp vụ

Giữ đầu/cuối là hai trường hợp đặc biệt: khi va chạm, một giá trị được giữ nguyên và giá trị còn lại bị bỏ qua. Nhưng nhiều bài toán cần **tích lũy**.

### 5.1. Tính tổng số lượng theo khóa

```java
record Item(String sku, long quantity) {}

List<Item> items = List.of(
    new Item("A", 4),
    new Item("B", 3),
    new Item("A", 2),
    new Item("A", 6),
    new Item("B", 7)
);

Map<String, Long> totalQuantity = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));

// "A" -> 12; "B" -> 10.
```

Ở mỗi xung đột khóa, `Long::sum` kết hợp giá trị đang có với giá trị vừa tới. Cuối quá trình, mỗi khóa chứa một tổng.

Có thể viết lambda tương đương:

```java
(left, right) -> left + right
```

Nhưng `Long::sum` biểu đạt rõ hơn ý định cộng hai số `long`.

### 5.2. Chọn giá trị lớn nhất hoặc nhỏ nhất

```java
Map<String, Long> maxQuantity = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::max
    ));

// A -> 6; B -> 7.
```

`Long::min` tương tự cho yêu cầu lấy giá trị nhỏ nhất. Đây là phép gộp độc lập với vị trí xuất hiện và thường phù hợp khi thứ tự đầu vào không có ý nghĩa nghiệp vụ.

### 5.3. Khi cần ghép các trường thay vì chỉ cộng một số

Giả sử mỗi bản ghi chứa doanh thu và số đơn hàng:

```java
record Totals(long revenue, long orders) {}

record PartialReport(String category, Totals totals) {}

List<PartialReport> parts = List.of(
    new PartialReport("Sách", new Totals(100, 2)),
    new PartialReport("Thiết bị", new Totals(250, 1)),
    new PartialReport("Sách", new Totals(300, 3))
);

Map<String, Totals> summary = parts.stream()
    .collect(Collectors.toMap(
        PartialReport::category,
        PartialReport::totals,
        (left, right) -> new Totals(
            left.revenue() + right.revenue(),
            left.orders() + right.orders()
        )
    ));

// "Sách" -> Totals(revenue=400, orders=5).
```

Hàm gộp tạo ra một giá trị mới, không cần chỉnh sửa đối tượng cũ. Đây là cách đơn giản để hạn chế lỗi trạng thái chung khi xử lý song song. Với dữ liệu thật, cần kiểm soát tràn `long` nếu tổng có thể vượt phạm vi biểu diễn.

### 5.4. Gộp danh sách hay dùng groupingBy?

Nếu muốn giữ **mọi bản ghi** của mỗi nhóm, `groupingBy` thường tự nhiên hơn:

```java
Map<String, List<Item>> itemsBySku = items.stream()
    .collect(Collectors.groupingBy(Item::sku));

// "A" có 3 Item; "B" có 2 Item.
```

Có thể viết `toMap` với `valueMapper` tạo danh sách một phần tử, rồi gộp danh sách. Nhưng việc quản lý một vùng mutable cho mỗi khóa, giữ thứ tự và gộp trong song song phức tạp hơn không cần thiết nếu `groupingBy` đã thể hiện đúng bài toán.

Ngược lại, nếu chỉ cần tổng số lượng, `toMap(..., Long::sum)` gọn và rõ. Một lựa chọn khác là:

```java
Map<String, Long> totals = items.stream()
    .collect(Collectors.groupingBy(
        Item::sku,
        Collectors.summingLong(Item::quantity)
    ));
```

Cả hai cách đều biểu diễn “tổng theo khóa”; chọn API dựa vào nhu cầu kết hợp downstream collector, loại Map, độ rõ của mã và kết quả cần thu.

## 6. Giữ bản ghi theo thời gian hoặc độ ưu tiên: dùng Comparator

Khi khóa trùng và cần chọn bản ghi **mới nhất về thời gian**, hãy so sánh một thuộc tính của chính đối tượng. Với dữ liệu từ mục mở đầu:

```java
record Event(String id, String product, long quantity, long occurredAt) {}
```

Giữ nguyên Event làm giá trị Map:

```java
Comparator<Event> byTimestampThenId = Comparator
    .comparingLong(Event::occurredAt)
    .thenComparing(Event::id);

Map<String, Event> newestByProduct = events.stream()
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        BinaryOperator.maxBy(byTimestampThenId)
    ));
```

Biến `events` là `List<Event>` được khai báo đầy đủ trong chương trình chạy độc lập ở mục 9.

`BinaryOperator.maxBy(...)` trả về giá trị lớn hơn theo Comparator. Khóa chính `occurredAt` quyết định bản ghi mới nhất; `id` giúp quyết định một cách nhất quán khi hai sự kiện có cùng timestamp.

### 6.1. Vì sao cần tie-breaker?

Nếu chỉ so timestamp, hai sự kiện cùng thời điểm có thể được Comparator xem là tương đương. Khi đó phần tử nào được giữ có thể phụ thuộc cách xử lý những trường hợp bằng nhau.

```java
Comparator<Event> byTimestamp =
    Comparator.comparingLong(Event::occurredAt);
```

Với hệ thống yêu cầu kết quả tái lập, có thể thêm khóa cuối **duy nhất và ổn định**:

```java
Comparator<Event> byTimestampThenId = Comparator
    .comparingLong(Event::occurredAt)
    .thenComparing(Event::id);
```

Điều này chỉ hiệu quả nếu `id` đáp ứng yêu cầu phân biệt của dữ liệu. Nếu mã sự kiện không duy nhất, cần xác định quy tắc tiếp theo.

### 6.2. Dùng minBy cho bản ghi cũ nhất

```java
Map<String, Event> oldestByProduct = events.stream()
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        BinaryOperator.minBy(byTimestampThenId)
    ));
```

`minBy` lấy phần tử có khóa so sánh nhỏ nhất. Khi Comparator mang ngữ nghĩa “thời gian rồi ID tăng dần”, nó chọn bản ghi cũ nhất theo thời gian; nếu bằng thời gian, chọn ID nhỏ hơn.

### 6.3. Một phương án khác: sort trước rồi last wins

Nếu cần thể hiện chính xác quy tắc “duyệt theo timestamp tăng dần rồi lấy cuối”:

```java
Map<String, Event> newestSorted = events.stream()
    .sorted(byTimestampThenId)
    .collect(Collectors.toMap(
        Event::product,
        Function.identity(),
        (first, second) -> second
    ));
```

Cách này có thể cho cùng kết quả với `maxBy` trên dữ liệu có thứ tự toàn phần phù hợp. Nhưng `sorted` phải sắp xếp toàn bộ nguồn, thường tiêu tốn thời gian `O(n log n)` và bộ nhớ bổ sung; `maxBy` trong merge function không đòi hỏi sắp toàn bộ chỉ để chọn đại diện cho từng khóa.

Nếu không cần một danh sách đã sắp, **so sánh trực tiếp trong merge function** thường là cách rõ ràng và ít công việc hơn.

### 6.4. Không dùng first/last để thay quy tắc cập nhật phiên bản

Trong hệ thống phân tán, một bản ghi có thể đến chậm, được xử lý lại hoặc được gửi trùng. Nếu nghiệp vụ lựa chọn theo `version`, hãy so sánh phiên bản:

```java
record VersionedValue(String key, long version, String payload) {}

Comparator<VersionedValue> byVersion =
    Comparator.comparingLong(VersionedValue::version)
        .thenComparing(VersionedValue::payload);

Map<String, VersionedValue> chosen = updates.stream()
    .collect(Collectors.toMap(
        VersionedValue::key,
        Function.identity(),
        BinaryOperator.maxBy(byVersion)
    ));
```

`updates` đại diện cho Stream hoặc List các cập nhật. Comparator này chỉ minh họa việc chọn ưu tiên theo phiên bản và dùng payload để phá hòa; nếu dữ liệu có cùng phiên bản nhưng nội dung khác nhau, hệ thống thực cần một **chính sách xung đột rõ ràng**, có thể là từ chối dữ liệu thay vì chọn ngẫu nhiên theo chuỗi.

## 7. Tính kết hợp của mergeFunction và xử lý song song

Collector có thể được thực thi bằng `parallelStream()`. Framework khi đó có thể tạo nhiều Map cục bộ, xử lý các phần dữ liệu riêng rồi **gộp các Map** bằng merge function.

```text
                 Nguồn có thứ tự
               [A1, B1, A2, A3, B2]
                        │
                  chia công việc
               ┌────────┴────────┐
               ▼                 ▼
          Map cục bộ 1       Map cục bộ 2
           A → ...             A → ...
           B → ...             B → ...
               └──── merge ───────┘
                       │
                       ▼
                   Map kết quả
```

Để quá trình chia/gộp vẫn đúng, **hàm gộp phải có tính kết hợp** (*associative*) và tuân thủ hợp đồng collector.

### 7.1. Những phép gộp có tính kết hợp

| Hàm gộp | Công thức | Tính kết hợp về kết quả |
| --- | --- | --- |
| Giữ đầu | `(a, b) -> a` | Có: luôn giữ giá trị phía trái của dãy gộp đúng thứ tự. |
| Giữ cuối | `(a, b) -> b` | Có: luôn giữ giá trị phía phải của dãy gộp đúng thứ tự. |
| Cộng số nguyên | `Long::sum` | Có theo số học nguyên và modulo của Java; nghiệp vụ phải xét tràn. |
| Lớn nhất | `Long::max` | Có. |
| Nhỏ nhất | `Long::min` | Có. |
| Lớn nhất theo Comparator ổn định | `BinaryOperator.maxBy(comparator)` | Có khi quan hệ so sánh hợp lệ và trường hợp bằng nhau được xử lý nhất quán. |
| Phép trừ | `(a, b) -> a - b` | **Không**. |
| Trung bình hai trung bình không có trọng số | `(a, b) -> (a + b) / 2` | **Không** trong bài toán tổng quát. |

Ví dụ sai:

```text
(20 - 7) - 3 = 10
20 - (7 - 3) = 16
```

Đổi cách nhóm phần tử sẽ cho kết quả khác nhau. Vì vậy không chọn phép trừ làm merge function cho việc tổng hợp cần đúng khi chia/gộp.

### 7.2. first/last theo encounter order và parallel

Với nguồn `List` có thứ tự, `Collectors.toMap` thông thường là collector **không đồng thời**, không khai báo `UNORDERED`. Khi được thực thi song song, nó phải bảo toàn ngữ nghĩa tương đương với phép thu thập tuần tự đối với thứ tự gặp phần tử; các merge function giữ đầu hoặc cuối có tính kết hợp phù hợp cho mục tiêu này.

Tuy nhiên, không suy ra rằng:

- Có thể dự đoán **thứ tự thời gian** các lambda được chạy trên từng luồng.
- Mọi nguồn đều có encounter order.
- `Map` kết quả tự có thứ tự duyệt giống nguồn.
- Quy tắc first/last diễn tả “sớm nhất/mới nhất theo ngày” nếu chưa so sánh ngày.

Nếu cần “mới nhất theo timestamp”, dùng Comparator như mục 6. Nếu cần first/last theo dữ liệu nhập, bảo đảm nguồn có encounter order rõ ràng.

### 7.3. toConcurrentMap cần đặc biệt cẩn thận

`Collectors.toConcurrentMap` tạo collector đồng thời, thường không có thứ tự. Ví dụ:

```java
ConcurrentMap<String, Long> totals = items.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));
```

Với phép cộng theo khóa, không cần biết phần tử nào “đầu tiên”. Nhưng nếu thay `Long::sum` bằng `(first, next) -> first` hoặc `(first, next) -> next`, giá trị thắng có thể phụ thuộc vào lịch biểu chạy đồng thời; **không dùng các quy tắc đó để chọn một bản ghi đầu/cuối theo thứ tự nguồn** với collector không có thứ tự.

Đoạn mã cần `import java.util.concurrent.ConcurrentMap;`. Không nên mặc định `toConcurrentMap` nhanh hơn; tranh chấp khóa, số lượng phần tử và đặc tính nguồn vẫn quyết định hiệu năng.

### 7.4. Tránh tác động phụ trong merge function

**Không nên viết:**

```java
List<String> audit = new ArrayList<>();

Map<String, Long> totals = items.parallelStream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        (a, b) -> {
            audit.add("Có khóa trùng"); // Không an toàn, tác động phụ bên ngoài.
            return a + b;
        }
    ));
```

`ArrayList` không an toàn khi nhiều luồng cùng cập nhật; hơn nữa số lần gọi merge phụ thuộc cách chia/gộp, không thích hợp để xác định số bản ghi trùng hoặc tạo audit chính thức.

Nếu cần thống kê số lượng theo khóa, thu thêm dữ liệu bằng `groupingBy` và `counting` hoặc một collector có trạng thái đúng hợp đồng. Việc ghi nhật ký nghiệp vụ nên là bước riêng được điều phối rõ ràng sau khi kết quả đã có.

## 8. Chọn Map nào: HashMap, LinkedHashMap hay TreeMap?

Overload ba tham số của `toMap` không cam kết một kiểu Map cụ thể hoặc thứ tự duyệt của Map kết quả. Nếu ứng dụng phụ thuộc vào cách các khóa được duyệt, chỉ định `mapFactory`:

```java
Map<String, Item> firstWithInsertionOrder = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Function.identity(),
        (first, next) -> first,
        LinkedHashMap::new
    ));
```

### 8.1. Khác biệt giữa các map

| Map | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `HashMap` | Không bảo đảm thứ tự duyệt. | Cần tra cứu theo khóa, không cần thứ tự trình bày. |
| `LinkedHashMap` | Mặc định giữ thứ tự chèn khóa. | Cần hiển thị khóa theo thứ tự xuất hiện đầu tiên. |
| `TreeMap` | Duyệt khóa theo Comparator hoặc thứ tự tự nhiên. | Cần khóa được sắp xếp để trình bày hoặc xử lý. |
| `ConcurrentHashMap` | Hỗ trợ thao tác đồng thời theo hợp đồng riêng. | Cần cập nhật/tra cứu đồng thời và đã thiết kế đúng merge semantics. |

Để sắp mã sản phẩm theo tên khóa:

```java
Map<String, Long> sortedKeys = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum,
        TreeMap::new
    ));
```

Ví dụ này giữ kết quả Map có khóa theo thứ tự tự nhiên của `String`. Nó **không có nghĩa** giá trị trong Map được sắp tăng dần.

### 8.2. TreeMap có thể định nghĩa "khóa trùng" khác HashMap

Với `HashMap`, hai khóa `String` được xem là giống nhau khi `equals` là `true`. Với `TreeMap`, quy tắc so sánh của Comparator có thể quyết định hai khóa là cùng một vị trí nếu `compare(a,b) == 0`.

```java
TreeMap<String, Long> map = new TreeMap<>(
    String.CASE_INSENSITIVE_ORDER
);

map.merge("SKU-a", 10L, Long::sum);
map.merge("sku-A", 20L, Long::sum);

System.out.println(map.size()); // 1
```

Lưu ý: Map dùng comparator không nhất quán với `equals` có thể không tuân thủ hợp đồng Map tổng quát theo cách mọi người kỳ vọng. Khi quy tắc khóa là **không phân biệt chữ hoa/chữ thường**, thường rõ ràng hơn nếu chuẩn hóa `keyMapper` ngay từ đầu:

```java
Map<String, Long> normalized = items.stream()
    .collect(Collectors.toMap(
        item -> item.sku().trim().toLowerCase(Locale.ROOT),
        Item::quantity,
        Long::sum
    ));
```

Đoạn này cần `import java.util.Locale;`. Lựa chọn chuẩn hóa mã phải theo quy tắc nghiệp vụ; có hệ thống mà chữ hoa và chữ thường tạo ra mã khác nhau.

### 8.3. Giữ thứ tự Map không thay thế giữ bản ghi đầu

`LinkedHashMap` giữ **thứ tự các khóa**, còn merge function quyết định **giá trị của từng khóa**. Cần thiết kế hai thứ độc lập:

```java
// Giữ khóa theo thứ tự gặp lần đầu, nhưng giữ giá trị gặp lần cuối.
Map<String, Item> map = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Function.identity(),
        (first, next) -> next,
        LinkedHashMap::new
    ));
```

Nếu cần phân trang kết quả theo thứ tự số lượng giảm dần, hãy sắp các entry theo số lượng sau khi thu thập hoặc thiết kế quy trình truy vấn phù hợp; việc dùng LinkedHashMap không tạo thứ tự theo giá trị.

## 9. Ví dụ Java hoàn chỉnh: so sánh bốn chính sách

Ví dụ sau dùng cùng một nguồn để so sánh **first wins**, **last wins**, **sum** và **newest by timestamp**. Lưu vào tệp `MapMergePoliciesDemo.java`, chạy trên Java 17+:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapMergePoliciesDemo {
    record Event(
        String id,
        String product,
        long quantity,
        long occurredAt
    ) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("E01", "A", 4, 100),
            new Event("E02", "B", 3, 101),
            new Event("E03", "A", 2, 105),
            new Event("E04", "A", 6, 103),
            new Event("E05", "B", 7, 98)
        );

        Map<String, Event> first = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                (kept, incoming) -> kept,
                LinkedHashMap::new
            ));

        Map<String, Event> last = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                (kept, incoming) -> incoming,
                LinkedHashMap::new
            ));

        Map<String, Long> sum = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Event::quantity,
                Long::sum,
                LinkedHashMap::new
            ));

        Comparator<Event> byTimeThenId = Comparator
            .comparingLong(Event::occurredAt)
            .thenComparing(Event::id);

        Map<String, Event> newest = events.stream()
            .collect(Collectors.toMap(
                Event::product,
                Function.identity(),
                BinaryOperator.maxBy(byTimeThenId),
                LinkedHashMap::new
            ));

        System.out.println("First A: " + first.get("A").id());
        System.out.println("Last A: " + last.get("A").id());
        System.out.println("Sum A: " + sum.get("A"));
        System.out.println("Newest A: " + newest.get("A").id());

        System.out.println("First B: " + first.get("B").id());
        System.out.println("Last B: " + last.get("B").id());
        System.out.println("Sum B: " + sum.get("B"));
        System.out.println("Newest B: " + newest.get("B").id());
    }
}
```

Kết quả:

```text
First A: E01
Last A: E04
Sum A: 12
Newest A: E03
First B: E02
Last B: E05
Sum B: 10
Newest B: E02
```

### 9.1. Vì sao dùng bốn Stream độc lập?

Mỗi lần gọi `events.stream()` tạo một Stream mới từ `List` có thể duyệt lại. Một Stream đã kết thúc bằng `collect` **không được tái sử dụng**.

Cả bốn lần thu thập đọc cùng dữ liệu nhưng sử dụng các quy tắc xung đột khác nhau. Chúng ta không cần sửa `events` hoặc sao chép nguồn chỉ để thay đổi cách tổng hợp.

### 9.2. So sánh kết quả theo từng khóa

| Khóa | Giữ đầu | Giữ cuối | Tổng quantity | Mới nhất theo timestamp |
| --- | --- | --- | ---: | --- |
| A | E01 | E04 | 12 | E03 |
| B | E02 | E05 | 10 | E02 |

Bảng cho thấy **last wins và newest không tương đương** khi dữ liệu đến sai thứ tự thời gian. Chọn nhầm quy tắc có thể tạo sai trạng thái hiện tại của một đối tượng nghiệp vụ.

### 9.3. Nếu dùng nguồn không có thứ tự thì sao?

Với một nguồn không có encounter order, kết quả của hai phép giữ đầu/cuối có thể khác giữa những lượt chạy hoặc cách tổ chức xử lý. Trong khi đó, phép tổng như `Long::sum` và lựa chọn lớn nhất theo một Comparator với tie-breaker nhất quán vẫn có ý nghĩa độc lập với thứ tự nguồn (trong giới hạn số học của kiểu).

Nếu cần tái lập kết quả trên nguồn bất kỳ, hãy định nghĩa **quy tắc so sánh có thứ tự toàn phần phù hợp**, hoặc sắp xếp nguồn theo một khóa nghiệp vụ trước khi dùng first/last.

## 10. Null, khóa trùng, hàm gộp trả null và lỗi dữ liệu

### 10.1. valueMapper không nên trả null

Các overload `Collectors.toMap` dựa trên cơ chế tạo và gộp giá trị trong Map. **Giá trị ánh xạ null không được hỗ trợ an toàn**; trong các triển khai JDK thông dụng, một giá trị `null` sẽ gây `NullPointerException`.

```java
record User(String id, String email) {}

List<User> users = List.of(
    new User("U1", "an@example.com"),
    new User("U2", null)
);

// Không làm như sau khi email có thể null:
// Map<String, String> byId = users.stream()
//     .collect(Collectors.toMap(User::id, User::email));
```

Có thể lọc phần tử thiếu giá trị:

```java
Map<String, String> byId = users.stream()
    .filter(user -> user.email() != null)
    .collect(Collectors.toMap(
        User::id,
        User::email
    ));
```

Nhưng lọc bỏ là **chính sách dữ liệu**, không phải cách duy nhất: nếu email thiếu là trạng thái hợp lệ cần giữ, hãy biểu diễn bằng kiểu giá trị thích hợp hoặc một đối tượng chứa thông tin có/không có.

### 10.2. keyMapper cần tạo khóa hợp lệ

Đừng giả định mọi loại Map đều chấp nhận khóa `null`. Ví dụ `TreeMap` theo thứ tự tự nhiên thường không cho phép khóa null; những map khác có chính sách khác nhau. Cách chắc chắn là xác định ràng buộc đầu vào:

```java
Map<String, Long> amounts = items.stream()
    .filter(item -> item.sku() != null)
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Long::sum
    ));
```

Nếu khóa không hợp lệ phải bị từ chối thay vì bỏ qua, hãy xác thực và ném một ngoại lệ có ý nghĩa trước bước collect.

### 10.3. mergeFunction trả null có nghĩa gì?

Hợp đồng `Map.merge` quy định nếu hàm gộp trả `null` khi khóa đang có giá trị, **mục khóa có thể bị xóa khỏi Map**. Đây là cách hoạt động đặc biệt, không phải “giữ giá trị null”.

```java
Map<String, Long> map = new HashMap<>();

map.merge("A", 4L, Long::sum);
map.merge("A", 2L, (left, right) -> null);

System.out.println(map.containsKey("A")); // false
```

Đoạn này cần import `java.util.HashMap`. Tùy triển khai collector và kiểu Map, dùng hàm merge trả null trong `toMap` có thể khiến khóa biến mất rồi được tạo lại khi phần tử tiếp theo xuất hiện. Đây là chính sách riêng cần được thiết kế và kiểm chứng cẩn thận; **không dùng null để biểu diễn “giữ nguyên giá trị cũ”**. Muốn giữ cũ, trả `left`.

### 10.4. Tràn số khi gộp tổng

`Long::sum` dùng số học `long` của Java và **không ném lỗi khi tràn**:

```java
long overflow = Long.sum(Long.MAX_VALUE, 1L);
// Kết quả bị tràn theo số học long.
```

Nếu hệ thống phải phát hiện tràn, có thể dùng:

```java
Map<String, Long> exact = items.stream()
    .collect(Collectors.toMap(
        Item::sku,
        Item::quantity,
        Math::addExact
    ));
```

`Math.addExact` ném `ArithmeticException` khi phép cộng trung gian vượt giới hạn. Khi có số âm và dương rất lớn, thứ tự gộp khác nhau có thể tạo hoặc tránh tràn trung gian, dù tổng toán học cuối có thể nằm trong phạm vi. Nếu cần tổng toán học chính xác cho mọi tổ hợp đầu vào, cân nhắc `BigInteger` làm kiểu giá trị thay vì `Long`.

## 11. Thiết kế quy tắc chọn bản ghi theo nghiệp vụ

Trước khi chọn merge function, trả lời ba câu hỏi:

1. **Khóa nào xác định hai phần tử là cùng một đối tượng nghiệp vụ?** Có cần chuẩn hóa khóa không?
2. **Giá trị cuối cần đại diện cho điều gì?** Một bản ghi cụ thể, tổng số, giá trị lớn nhất hay toàn bộ lịch sử?
3. **Nếu hai giá trị xung đột, điều gì quyết định bên thắng?** Thứ tự gặp, timestamp, phiên bản, mức ưu tiên hay một phép tổng hợp?

Bảng chọn nhanh:

| Yêu cầu | Hướng giải quyết | Ghi nhớ |
| --- | --- | --- |
| Dữ liệu bảo đảm mỗi khóa chỉ xuất hiện một lần | `toMap(keyMapper, valueMapper)` | Trùng khóa thì ném ngoại lệ, giúp phát hiện dữ liệu bất thường. |
| Giữ phần tử xuất hiện đầu theo nguồn ordered | `toMap(k, v, (first, next) -> first)` | Cần hiểu encounter order. |
| Giữ phần tử xuất hiện cuối theo nguồn ordered | `toMap(k, v, (first, next) -> next)` | Không đồng nghĩa mới nhất theo timestamp. |
| Cộng số lượng/doanh thu theo khóa | `toMap(k, v, Long::sum)` | Cân nhắc tràn số. |
| Lấy giá trị lớn nhất/nhỏ nhất theo khóa | `Long::max` / `Long::min` | Không phụ thuộc thứ tự nguồn. |
| Giữ bản ghi mới nhất theo timestamp | `BinaryOperator.maxBy(comparator)` | Comparator cần tie-breaker nếu có đồng thời điểm. |
| Giữ toàn bộ bản ghi theo khóa | `groupingBy(keyMapper)` | Kết quả là nhóm danh sách, không mất lịch sử. |
| Gom thống kê phức tạp cho từng khóa | `groupingBy(keyMapper, downstreamCollector)` | Phù hợp collector có nhiều trường/trạng thái. |
| Cần duyệt khóa theo thứ tự xuất hiện đầu | `toMap(k, v, merge, LinkedHashMap::new)` | Thứ tự khóa khác quy tắc giá trị thắng. |
| Cần khóa được sắp | `toMap(k, v, merge, TreeMap::new)` | Comparator của map ảnh hưởng tính tương đương khóa. |
| Cần map không thể sửa | `Map.copyOf(...)` hoặc `toUnmodifiableMap(...)` | Chú ý `null`, khóa trùng và thứ tự duyệt. |

### 11.1. Không nên che giấu xung đột nghiệp vụ

Nếu một hệ thống yêu cầu mã người dùng duy nhất, việc viết `(first, second) -> first` có thể **che lỗi dữ liệu**. Khi không có quy tắc hợp pháp để chọn giữa hai giá trị, để `toMap` ném ngoại lệ hoặc thực hiện bước xác thực tường minh sẽ an toàn hơn.

Nếu cần báo cáo đầy đủ xung đột, có thể thu nhóm trước:

```java
Map<String, List<User>> byId = users.stream()
    .collect(Collectors.groupingBy(User::id));
```

Rồi xác định các nhóm có nhiều phần tử để điều tra. `groupingBy` không tự xác nhận giá trị trong nhóm có cùng nội dung hay không; đó là bước nghiệp vụ tiếp theo.

### 11.2. Thứ tự gặp phần tử cũng là dữ liệu cần được xác định

Với nguồn lấy từ cơ sở dữ liệu, không nên giả định thứ tự bản ghi nếu truy vấn không có quy tắc `ORDER BY`. Với nguồn xử lý song song hoặc nguồn unordered, thứ tự xử lý có thể khác mong đợi. Nếu first/last thực sự là lựa chọn theo một trường thời gian hoặc sequence number, hãy biểu diễn trường đó trong Comparator.

Tương tự, nếu thứ tự của `HashMap` hiện tại “trông đúng” trên dữ liệu thử nghiệm, đó không phải hợp đồng bảo đảm. Chọn `LinkedHashMap` hoặc `TreeMap` có chủ đích khi cần bảo đảm thứ tự duyệt kết quả.

## 12. Hiệu năng, bộ nhớ và tài nguyên

### 12.1. Chi phí tổng hợp so với sắp xếp

Một phép thu thập vào Map thường duyệt các phần tử đầu vào và xử lý xung đột theo khóa. Với hash map và điều kiện thông thường, chi phí trung bình có thể gần `O(n)`, cộng chi phí băm, so sánh khóa và gộp; hiệu năng thực tế còn phụ thuộc phân phối khóa và thiết kế Map.

Nếu sắp xếp toàn bộ `n` phần tử chỉ để chọn bản ghi mới nhất cho từng khóa, phải trả thêm công sắp xếp khoảng `O(n log n)`. Dùng merge dựa trên Comparator thường tránh việc phải sắp toàn bộ nguồn khi chỉ cần một đại diện cho mỗi khóa.

`TreeMap` có chi phí thao tác theo cây tìm kiếm và thường theo `O(log k)` với `k` khóa phân biệt. Chọn map cần dựa trên yêu cầu thứ tự khóa và khối lượng dữ liệu.

### 12.2. Số lượng khóa quyết định bộ nhớ kết quả

Giữ một giá trị cho mỗi khóa thường dùng bộ nhớ tỷ lệ với số khóa phân biệt, trong khi `groupingBy` giữ danh sách tất cả phần tử có thể cần bộ nhớ tỷ lệ với tổng số bản ghi. Nếu chỉ cần tổng hoặc đại diện mới nhất, không cần giữ mọi sự kiện.

Ngược lại, nếu ứng dụng cần audit hoặc truy xuất lịch sử, chỉ giữ last wins sẽ làm mất các bản ghi trước. Hãy xác định yêu cầu lưu trữ trước khi chọn collector.

### 12.3. Parallel không mặc định nhanh hơn

`parallelStream()` có thể phân chia công việc theo `Spliterator` và hợp nhất Map cục bộ. Với nhiều khóa và dữ liệu lớn, lợi ích phụ thuộc khả năng chia nguồn, phân phối khóa, chi phí merge và tài nguyên phần cứng.

Các yếu tố có thể làm song song kém hiệu quả:

- Mỗi phần phải tạo Map riêng rồi gộp số lượng lớn khóa.
- Các phần tử tập trung vào rất ít khóa, gây nhiều va chạm.
- Merge function tính toán hoặc cấp phát đối tượng tốn kém.
- Bắt buộc duy trì encounter order hoặc quy tắc tie-break phức tạp.
- Dữ liệu lấy từ I/O bị chặn, không phù hợp chia việc đơn giản.

Chỉ chọn chế độ song song khi đã đo đạc trên dữ liệu đại diện và merge function tuân thủ hợp đồng.

### 12.4. Thu thập không tự đóng nguồn I/O

Ví dụ đọc tệp CSV có hai cột `sku,quantity` và thu tổng theo SKU:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

class MapFromFile {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("items.csv");

        try (Stream<String> lines = Files.lines(path)) {
            Map<String, Long> totals = lines
                .filter(line -> !line.isBlank())
                .map(line -> line.split(",", -1))
                .collect(Collectors.toMap(
                    columns -> columns[0].trim(),
                    columns -> Long.parseLong(columns[1].trim()),
                    Long::sum
                ));

            System.out.println(totals);
        }
    }
}
```

Đoạn mã minh họa tệp đơn giản không có header, mỗi dòng đúng hai cột và không có dấu phẩy nằm trong trường dữ liệu. Với CSV thực tế cần parser và xử lý lỗi phù hợp. `Files.lines(path)` gắn với tài nguyên I/O phải đóng qua `try-with-resources`; `collect` không tự gọi `close()`.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `toMap(key, value)` dù khóa có thể trùng | `IllegalStateException` khi có khóa xung đột. | Định nghĩa merge function hoặc sửa quy tắc khóa. |
| Dùng `(a,b)->a` mà không xác định thứ tự nguồn | Giá trị được giữ có thể không phải bản ghi mong muốn. | Xác lập encounter order hoặc chọn theo Comparator. |
| Dùng last wins để chọn bản ghi có timestamp mới nhất | Dữ liệu đến trễ có thể ghi đè bản ghi mới hơn. | `BinaryOperator.maxBy` theo timestamp và tie-breaker. |
| Gộp bằng phép trừ | Không có tính kết hợp; kết quả khác khi chia/gộp. | Dùng phép gộp hợp lệ theo nghiệp vụ. |
| Dùng `Long::sum` mà không xem xét tràn số | Tổng có thể sai khi vượt `long`. | `Math.addExact` hoặc kiểu số đủ rộng. |
| Viết merge function có tác động phụ vào list ngoài | Sai khi song song; số lần gọi không đại diện cho số va chạm nghiệp vụ. | Tách audit và thu thập kết quả. |
| Cho rằng `Map` kết quả luôn giữ thứ tự Stream | Overload mặc định không cam kết thứ tự Map. | Dùng `LinkedHashMap::new` hoặc `TreeMap::new` phù hợp. |
| Nhầm `LinkedHashMap` thay giá trị với di chuyển khóa | Thứ tự các khóa không đổi theo lần cập nhật cuối. | Xây chiến lược thứ tự theo thời điểm nếu cần. |
| Dùng `toConcurrentMap` với first/last theo thứ tự nguồn | Collector không có bảo đảm thứ tự, kết quả có thể phụ thuộc lịch chạy. | Dùng collector phù hợp ordered stream hoặc Comparator theo khóa nghiệp vụ. |
| `valueMapper` trả `null` | Có thể ném `NullPointerException`. | Xác thực, lọc hoặc biểu diễn thiếu dữ liệu rõ ràng. |
| `mergeFunction` trả null để “giữ giá trị cũ” | Khóa có thể bị loại khỏi Map. | Trả chính giá trị cũ nếu muốn giữ. |
| Gộp tất cả bản ghi thành một đại diện khi cần lịch sử | Mất dữ liệu chi tiết. | `groupingBy` để giữ tất cả. |
| Dùng `HashMap` với khóa mutable đã bị thay đổi | Có thể không còn tra cứu đúng theo hashCode/equals ban đầu. | Dùng khóa bất biến và nhất quán. |
| Lấy dữ liệu từ tệp nhưng không đóng nguồn | Rò rỉ tài nguyên. | `try-with-resources`. |

## 14. Tự kiểm tra kiến thức

1. Khi có hai sản phẩm cùng `category`, overload `Collectors.toMap(Product::category, Product::price)` làm gì?
2. Ba tham số `keyMapper`, `valueMapper` và `mergeFunction` khác nhau thế nào?
3. `(first, next) -> first` và `(first, next) -> next` cho kết quả gì với danh sách `[A1, B1, A2]`?
4. Vì sao bản ghi gặp cuối trong Stream không nhất thiết có timestamp mới nhất?
5. Khi cần giữ giá trị lớn nhất theo `version`, nên dùng `BinaryOperator.maxBy` hay last wins? Vì sao?
6. Với nguồn không có encounter order, quy tắc first/last có bảo đảm chọn cùng bản ghi qua mọi lần chạy không?
7. Vì sao `(a,b) -> a-b` không phù hợp để gộp dữ liệu khi chạy song song?
8. `toConcurrentMap` có thích hợp để giữ bản ghi gặp đầu theo thứ tự List không?
9. `LinkedHashMap::new` quyết định giá trị thắng khi khóa trùng hay chỉ quyết định loại Map?
10. Khi nào nên dùng `groupingBy` thay vì `toMap`?
11. Một `mergeFunction` trả `null` có thể gây điều gì với khóa?
12. `Long::sum` có tự phát hiện tràn `long` không?

**Gợi ý trả lời:** (1) ném `IllegalStateException`; (2) tạo khóa, tạo giá trị, quyết định cách gộp hai giá trị cùng khóa; (3) A1 so với A2, B1 giữ nguyên; (4) dữ liệu có thể đến không đúng thứ tự thời gian; (5) `maxBy` theo Comparator có tie-breaker; (6) không; (7) phép trừ không có tính kết hợp; (8) không phù hợp để cam kết thứ tự nguồn; (9) loại Map và quy tắc duyệt khóa, không thay merge function; (10) cần giữ nhiều bản ghi hoặc dùng downstream collector; (11) có thể xóa mục khóa; (12) không.

## 15. Bài tập thực hành

**Bài 1 — Giữ đầu và cuối.** Cho `List<Event>` với các bản ghi có `product` bị trùng. Dùng hai `Collectors.toMap` để lấy sự kiện đầu và cuối theo thứ tự List; giải thích vì sao kết quả khác nhau.

**Bài 2 — Chọn phiên bản cao nhất.** Cho `VersionedValue(String key, long version, String payload)`. Dùng `BinaryOperator.maxBy(Comparator.comparingLong(...))` để giữ phiên bản mới nhất. Bổ sung tie-breaker khi cùng version.

**Bài 3 — Tổng theo nhóm.** Cho `Item(String sku, long quantity)`. Thu Map tổng số lượng bằng `Long::sum`, rồi viết lại bằng `groupingBy(..., summingLong(...))`; so sánh độ rõ và trường hợp mở rộng downstream.

**Bài 4 — Phát hiện xung đột.** Cho danh sách người dùng với mã ID có thể trùng. Sử dụng `groupingBy(User::id)` để tìm nhóm có nhiều hơn một bản ghi. Khi nào nên ném lỗi thay vì giữ bản ghi đầu?

**Bài 5 — Chỉnh thứ tự hiển thị.** Dùng `LinkedHashMap::new` để giữ thứ tự khóa xuất hiện đầu trong danh sách. Sau đó tạo một Map mới với `TreeMap::new` để sắp khóa theo thứ tự tự nhiên. Không thay đổi merge function.

**Bài 6 — Dữ liệu không theo thứ tự thời gian.** Cho ba sự kiện cùng sản phẩm theo thứ tự thời gian `100, 105, 103`. Chứng minh last wins chọn `103`, còn maxBy theo timestamp chọn `105`.

**Bài 7 — Parallel.** Chạy phép tổng theo khóa trên Stream tuần tự và song song, kiểm tra kết quả. Thử thay phép gộp bằng phép trừ và giải thích vì sao kết quả không còn đáng tin.

**Bài 8 — Lỗi null.** Cho một `User` có `email == null`. Viết cách xử lý an toàn trước khi thu Map từ ID sang email; thảo luận khi nào lọc bỏ bản ghi là không chấp nhận được.

Gợi ý cho Bài 2:

```java
Comparator<VersionedValue> byVersionThenPayload = Comparator
    .comparingLong(VersionedValue::version)
    .thenComparing(VersionedValue::payload);

Map<String, VersionedValue> best = updates.stream()
    .collect(Collectors.toMap(
        VersionedValue::key,
        Function.identity(),
        BinaryOperator.maxBy(byVersionThenPayload)
    ));
```

Ví dụ giả định các đối tượng và biến `updates` đã được tạo, `payload` không null, có quy tắc so sánh chuỗi hợp lệ. Nếu payload không phải tie-breaker nghiệp vụ, hãy chọn một trường khác hoặc từ chối các bản ghi xung đột cùng phiên bản.

## 16. Ghi nhớ cốt lõi

- **`Collectors.toMap` mặc định ném lỗi khi khóa trùng**; muốn chọn một giá trị phải cung cấp `mergeFunction` phù hợp.
- **`(first, next) -> first`** giữ bản ghi gặp đầu; **`(first, next) -> next`** giữ bản ghi gặp cuối khi nguồn có encounter order phù hợp.
- **Giữ cuối không đồng nghĩa bản ghi mới nhất theo thời gian**. Nếu cần chọn theo timestamp, version hoặc độ ưu tiên, hãy dùng `BinaryOperator.maxBy`/`minBy` với Comparator rõ ràng và tie-breaker hợp lệ.
- **Gộp giá trị** như `Long::sum`, `Long::max` hoặc kết hợp các record thống kê phải tuân thủ hợp đồng phép gộp, đặc biệt tính kết hợp khi chạy song song.
- **`groupingBy` giữ nhiều giá trị theo một khóa** và kết hợp downstream collector; `toMap` phù hợp khi mỗi khóa cần một giá trị kết quả.
- **`mapFactory` quyết định loại Map**. `LinkedHashMap` bảo toàn thứ tự chèn khóa, `TreeMap` sắp khóa; hai quyết định này khác chính sách chọn giá trị khi trùng khóa.
- **Không gộp bằng tác động phụ bên ngoài, không mặc định thứ tự nguồn, không lạm dụng `toConcurrentMap` cho first/last**, và kiểm soát `null`, tràn số, khóa bất biến, cùng vòng đời tài nguyên I/O.
- Hiểu quy tắc merge trong Map là nền tảng để thiết kế `collect`, collector tùy chỉnh, grouping và các pipeline dựa trên `Spliterator` hoặc xử lý song song trong **JAVA_STREAM_API**.
