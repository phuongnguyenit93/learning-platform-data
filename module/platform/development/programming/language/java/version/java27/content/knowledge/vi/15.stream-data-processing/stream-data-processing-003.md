# `sorted`, `distinct`, `limit` và các thao tác có trạng thái trong Java 27

Trong chương **Xử lý dữ liệu bằng Stream**, nhiều pipeline trông giống một chuỗi phép biến đổi độc lập:

```java
var result = numbers.stream()
    .filter(n -> n > 0)
    .distinct()
    .sorted()
    .limit(5)
    .toList();
```

Tuy nhiên, `distinct()` phải nhận biết phần tử đã xuất hiện, `sorted()` phải xét thứ tự giữa các phần tử và `limit()` phải theo dõi số phần tử đã chọn. Đây là các **stateful intermediate operations** — thao tác trung gian có trạng thái. Chúng khác về ngữ nghĩa, chi phí bộ nhớ và cách phối hợp với **encounter order** (thứ tự duyệt phần tử), đặc biệt trên parallel stream.

Bài học này dùng các API còn được hỗ trợ trong **Java 27**: `sorted`, `distinct`, `limit`, `skip`, `takeWhile` và `dropWhile`; phân tích cách đặt thứ tự thao tác, xử lý dữ liệu vô hạn, tối ưu có điều kiện và tránh lỗi khi thiết kế pipeline.

> Các đoạn mã ngắn trong bài giả định bạn đặt chúng trong một phương thức Java hoặc dùng JShell với import tương ứng. Ví dụ tổng hợp cuối bài là một chương trình hoàn chỉnh.

## 1. Stateful operation là gì?

Một stream pipeline có nguồn dữ liệu, các thao tác trung gian (*intermediate operations*) và một thao tác kết thúc (*terminal operation*):

```text
Nguồn List<Product>
      |
      v
filter(...)        stateless
      |
      v
sorted(...)        stateful
      |
      v
map(...)           stateless
      |
      v
distinct()         stateful
      |
      v
limit(3)           stateful + short-circuiting
      |
      v
toList()           terminal
```

**Stateless intermediate operation** như `map` hay `filter` có thể xử lý mỗi phần tử mà không cần ghi nhớ kết quả xử lý các phần tử khác. **Stateful intermediate operation** có thể phải theo dõi tập phần tử đã gặp, vị trí hiện tại, điều kiện dừng hoặc trật tự của cả luồng.

| Thao tác | Chức năng | Loại | Có short-circuit theo đặc tả? |
| --- | --- | --- | --- |
| `filter(predicate)` | Giữ phần tử thỏa điều kiện | Stateless | Không |
| `map(function)` | Biến đổi từng phần tử | Stateless | Không |
| `distinct()` | Loại phần tử trùng bằng `equals` | Stateful | Không |
| `sorted()` / `sorted(comparator)` | Sắp xếp tăng dần hoặc theo comparator | Stateful | Không |
| `limit(n)` | Giữ tối đa `n` phần tử đầu theo encounter order, nếu có | Stateful | **Có** |
| `skip(n)` | Bỏ qua `n` phần tử đầu theo encounter order, nếu có | Stateful | Không |
| `takeWhile(predicate)` | Lấy prefix thỏa predicate của ordered stream | Stateful | **Có** |
| `dropWhile(predicate)` | Bỏ prefix thỏa predicate của ordered stream | Stateful | Không |

Đây là phân loại về **ngữ nghĩa thao tác**, không có nghĩa programmer nên dùng biến mutable trong lambda. Các hàm hành vi đưa vào stream thông thường phải **không can thiệp nguồn** (*non-interfering*) và **không mang trạng thái thay đổi giữa các lần gọi** (*stateless*).

### 1.1. Intermediate operations vẫn lazy

Gọi `sorted()`, `distinct()` hoặc `limit()` chưa lập tức duyệt collection. Stream chỉ bắt đầu thực thi pipeline khi có terminal operation như `toList()`, `collect()`, `count()`, `findFirst()` hoặc `forEach()`.

```java
import java.util.List;

List<Integer> input = List.of(5, 1, 3, 1, 2);

var pipeline = input.stream()
    .distinct()
    .sorted()
    .limit(3);       // Chưa tính ra các phần tử

List<Integer> result = pipeline.toList();
System.out.println(result); // [1, 2, 3]
```

Vì pipeline được tiêu thụ chỉ một lần, không thể gọi `pipeline.toList()` thêm lần nữa một cách hợp lệ. Khi cần kết quả mới, hãy tạo stream mới từ nguồn.

### 1.2. Short-circuit không đồng nghĩa lúc nào cũng xử lý ít phần tử

Short-circuiting operation có thể cho phép xử lý hữu hạn từ một nguồn vô hạn, nhưng **không bảo đảm pipeline luôn kết thúc**. Thứ tự các công đoạn rất quan trọng.

```java
import java.util.stream.Stream;

var firstFive = Stream.iterate(0, n -> n + 1)
    .limit(5)
    .sorted()
    .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
```

Ở đây `limit(5)` chặn nguồn vô hạn trước khi sắp xếp. Ngược lại, `Stream.iterate(...).sorted().limit(5).toList()` không có cách thu thập toàn bộ nguồn vô hạn để thực hiện sort; pipeline không thể hoàn thành bình thường theo cách này.

## 2. Encounter order: thứ tự duyệt do nguồn và pipeline quy định

**Encounter order** là thứ tự phần tử được xác định bởi đặc tính của nguồn và các thao tác trên stream. Không phải mọi nguồn đều có một encounter order.

Ví dụ:

- `List.stream()`, `Stream.of(...)`, `Arrays.stream(...)` và `IntStream.range(...)` có thứ tự xác định.
- `HashSet.stream()` không hứa hẹn encounter order có ý nghĩa; không dựa vào thứ tự in ra dù thử vài lần thấy giống nhau.
- `sorted(comparator)` thiết lập thứ tự sắp xếp theo comparator.
- `unordered()` loại bỏ ràng buộc encounter order của pipeline khi logic không cần thứ tự.

```java
import java.util.List;

List<String> ids = List.of("B", "A", "B", "C");

System.out.println(ids.stream().distinct().toList());
// [B, A, C] — giữ lần xuất hiện đầu tiên của phần tử trùng
```

Phân biệt **encounter order** với **thứ tự hoàn thành tác vụ song song**. Ví dụ `parallel().forEach(...)` có thể in phần tử theo thứ tự khác thứ tự duyệt; `forEachOrdered` có ràng buộc giữ encounter order.

### 2.1. Có thứ tự không có nghĩa mọi thao tác đều giữ nguyên thứ tự

`sorted()` cố tình thay encounter order thành thứ tự sắp xếp. Các thao tác như `filter` hay `map` thông thường giữ encounter order khi stream có thứ tự; `distinct` trên stream có thứ tự giữ lại bản xuất hiện **đầu tiên** của mỗi nhóm phần tử bằng nhau.

Không được nhầm `unordered()` với **xáo trộn ngẫu nhiên**. Nó chỉ bỏ cam kết về thứ tự, không bảo đảm trộn dữ liệu.

## 3. `sorted()`: sắp xếp theo natural order

Không truyền comparator thì `Stream<T>.sorted()` dùng thứ tự tự nhiên của các phần tử. Phần tử phải hỗ trợ `Comparable` và có thể so sánh được với nhau.

```java
import java.util.List;

List<Integer> numbers = List.of(8, 2, 5, 1);
List<Integer> ascending = numbers.stream()
    .sorted()
    .toList();

System.out.println(ascending); // [1, 2, 5, 8]
```

Với `String`, natural order là thứ tự của `String.compareTo`, không mặc nhiên là cách sắp xếp ngôn ngữ tự nhiên theo locale.

```java
List<String> words = List.of("z", "A", "a");
System.out.println(words.stream().sorted().toList());
// [A, a, z]
```

Nếu phần tử không triển khai `Comparable` phù hợp, terminal operation có thể phát sinh `ClassCastException`. Nếu comparator hoặc natural comparison không xử lý được phần tử `null`, phép sort có thể ném `NullPointerException`. Cần đặt quy tắc cho dữ liệu thiếu rõ ràng, thay vì chờ lỗi khi pipeline chạy.

### 3.1. `sorted(Comparator)`: sắp xếp object theo nghiệp vụ

```java
import java.util.Comparator;
import java.util.List;

record Product(String sku, String category, int price) { }

List<Product> products = List.of(
    new Product("P3", "Home", 200),
    new Product("P1", "Books", 500),
    new Product("P2", "Books", 500)
);

List<Product> ranking = products.stream()
    .sorted(
        Comparator.comparingInt(Product::price)
            .reversed()
            .thenComparing(Product::sku)
    )
    .toList();

System.out.println(ranking.stream().map(Product::sku).toList());
// [P1, P2, P3]
```

Đoạn mã chọn **giá giảm dần**, sau đó lấy **SKU tăng dần** để phá hòa khi hai sản phẩm cùng giá. `Comparator.comparingInt`, `reversed()` và `thenComparing` giúp mô tả quy tắc rõ ràng và tránh chi phí boxing không cần thiết khi so sánh số nguyên.

Không nên viết:

```java
// Tránh phép trừ để so sánh số nguyên vì có thể tràn số:
// (a, b) -> b.price() - a.price()

// Ưu tiên:
Comparator<Product> byPriceDescending =
    Comparator.comparingInt(Product::price).reversed();
```

Comparator được dùng trong stream phải tuân theo hợp đồng so sánh (phản đối xứng, bắc cầu, tính nhất quán của kết quả) và không bị thay đổi trong khi xử lý. Comparator phụ thuộc vào trạng thái mutable ngoài pipeline có thể gây kết quả không nhất quán hoặc lỗi.

### 3.2. Sắp xếp nhiều khóa và null

```java
record Employee(String department, String name, int age) { }

Comparator<Employee> order = Comparator
    .comparing(Employee::department)
    .thenComparing(Employee::name)
    .thenComparingInt(Employee::age);
```

Với trường tham chiếu có thể null, quy định rõ thứ tự của null:

```java
import java.util.Comparator;

Comparator<String> nullableNames =
    Comparator.nullsLast(Comparator.naturalOrder());
```

Như vậy `Stream.of("B", null, "A").sorted(nullableNames).toList()` cho kết quả `["A", "B", null]`. Một số terminal operation không cho phép kết quả null, nhưng `Stream.toList()` có thể chứa null; ở đây mã minh họa dùng `toList()`.

Nếu bài toán yêu cầu collation theo ngôn ngữ hoặc locale (ví dụ tiếng Việt), hãy nghiên cứu `Collator` của `java.text`, cấu hình mức so sánh và kiểm thử dữ liệu thực. Không coi `String.compareTo` là thứ tự từ điển chuẩn cho mọi ngôn ngữ.

### 3.3. Tính ổn định của sort

Với **ordered stream**, `sorted()` và `sorted(comparator)` bảo đảm **stable sort**: các phần tử mà comparator coi là ngang nhau giữ thứ tự tương đối ban đầu.

```java
record Entry(String id, int score) { }

List<Entry> entries = List.of(
    new Entry("A", 10),
    new Entry("B", 5),
    new Entry("C", 10)
);

var ordered = entries.stream()
    .sorted(Comparator.comparingInt(Entry::score).reversed())
    .map(Entry::id)
    .toList();

System.out.println(ordered); // [A, C, B]
```

Trong nhóm `score == 10`, A vẫn trước C. Với **unordered stream**, đặc tả không bảo đảm tính ổn định này. Nếu cần sắp xếp kết quả **có thể tái lập độc lập thứ tự nguồn**, đặt tie-breaker trên một khóa duy nhất, ví dụ `thenComparing(Entry::id)`.

### 3.4. Chi phí xử lý của `sorted`

Sắp xếp nói chung phải xem được tất cả phần tử đầu vào của bước sort trước khi xác định kết quả cuối cùng. Với nguồn lớn, đây là **barrier** có thể cần lưu trữ đáng kể và thường có độ phức tạp kiểu `O(n log n)` cho sắp xếp so sánh. Chi tiết triển khai và tối ưu cụ thể do JDK quyết định.

Điều đó giải thích vì sao `sorted().findFirst()` hoặc `sorted().limit(3)` không đồng nghĩa với thao tác chỉ đọc ba phần tử đầu tiên từ nguồn. Muốn tối ưu bài toán lấy cực trị, hãy cân nhắc `min(comparator)` hoặc `max(comparator)` thay vì sort toàn bộ.

## 4. `distinct()`: loại trùng bằng `equals`, không theo comparator

`Stream<T>.distinct()` giữ các phần tử **không trùng theo `Object.equals(Object)`**. Với stream có encounter order, phần tử đầu tiên của mỗi nhóm bằng nhau được giữ lại.

```java
List<String> values = List.of("A", "B", "A", "C", "B");
System.out.println(values.stream().distinct().toList());
// [A, B, C]
```

Nếu kiểu phần tử không có định nghĩa `equals` theo giá trị nghiệp vụ (ví dụ class mutable chỉ kế thừa `Object.equals`), hai object có nội dung giống nhau vẫn có thể được coi là khác nhau. Records thường tiện cho dữ liệu giá trị vì trình biên dịch tạo `equals` và `hashCode` dựa trên component.

### 4.1. `distinct()` của record khác distinct theo một trường

```java
record Event(String eventId, String customerId) { }

List<Event> events = List.of(
    new Event("E1", "C10"),
    new Event("E2", "C10"),
    new Event("E1", "C10")
);

System.out.println(events.stream().distinct().toList());
// [Event[eventId=E1, customerId=C10], Event[eventId=E2, customerId=C10]]
```

Hai event đầu có cùng `customerId` nhưng **khác `eventId`**, nên chúng không trùng theo `equals` của record. Nếu nghiệp vụ cần **một event cho mỗi customer**, `distinct()` trên `Stream<Event>` là sai về tiêu chí.

Khi chỉ cần danh sách customer ID duy nhất, **đổi sang khóa cần loại trùng trước**:

```java
List<String> customers = events.stream()
    .map(Event::customerId)
    .distinct()
    .toList();

System.out.println(customers); // [C10]
```

Khi cần **giữ nguyên cả object** nhưng chỉ giữ một object mỗi khóa, xem mục 9 về `Collectors.toMap` và quy tắc chọn bản đại diện.

### 4.2. `equals` và `hashCode` phải ổn định

Với object thường, logic `distinct` dựa trên equality; nếu tùy chỉnh `equals` thì phải viết `hashCode` nhất quán. Đừng thay đổi các thuộc tính tham gia equality của phần tử trong khi pipeline đang xử lý.

Một bất ngờ khác là `BigDecimal`: `compareTo` của hai giá trị số có thể trả 0 trong khi `equals` phân biệt scale.

```java
import java.math.BigDecimal;

var amounts = List.of(
    new BigDecimal("1.0"),
    new BigDecimal("1.00")
);

System.out.println(amounts.stream().distinct().count()); // 2
System.out.println(amounts.get(0).compareTo(amounts.get(1))); // 0
```

Vì vậy `sorted().distinct()` **không** có nghĩa “loại các phần tử mà comparator coi là bằng nhau”. Nếu phải loại trùng theo so sánh nghiệp vụ, cần xác định khóa canonical hoặc chiến lược gom nhóm đúng.

### 4.3. Độ ổn định của `distinct`

Với ordered stream, duplicate đầu tiên thắng:

```java
List<String> input = List.of("b", "a", "b", "c");
System.out.println(input.stream().distinct().toList()); // [b, a, c]
```

Với unordered stream, **không có bảo đảm chọn lần xuất hiện nào**, kể cả trong parallel pipeline. Nếu các object bằng nhau nhưng mang dữ liệu phụ khác, việc giữ object nào có thể ảnh hưởng kết quả. Trong trường hợp đó, hãy đưa quy tắc lựa chọn vào logic thu thập thay vì tùy tiện dùng `unordered()`.

## 5. `limit(n)`: lấy tối đa n phần tử, có short-circuit

`limit(long maxSize)` tạo stream gồm nhiều nhất `maxSize` phần tử từ phần đầu của encounter order nếu nguồn có thứ tự. `limit(0)` trả về stream rỗng; truyền số âm ném `IllegalArgumentException`.

```java
import java.util.stream.IntStream;

List<Integer> firstThree = IntStream.rangeClosed(1, 10)
    .boxed()
    .limit(3)
    .toList();

System.out.println(firstThree); // [1, 2, 3]
```

Với nguồn vô hạn nhưng có khả năng sinh lần lượt các phần tử, `limit` có thể giúp terminal operation kết thúc:

```java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .toList();
// [1, 2, 3, 4, 5]
```

Tuy nhiên, có `limit` trong pipeline không bảo đảm toàn bộ pipeline hữu hạn nếu phía trước nó có một thao tác không thể kết thúc hoặc phải xét toàn bộ đầu vào như `sorted` trên nguồn vô hạn.

### 5.1. `limit` và `filter` không giao hoán

```java
List<Integer> numbers = List.of(9, 2, 7, 4, 6);

var a = numbers.stream()
    .filter(n -> n % 2 == 0)
    .limit(2)
    .toList();
// [2, 4] — hai số chẵn đầu tiên

var b = numbers.stream()
    .limit(2)
    .filter(n -> n % 2 == 0)
    .toList();
// [2] — chỉ xét hai phần tử đầu nguồn
```

Đặt `limit` sớm có thể giảm lượng dữ liệu xử lý nhưng **đổi kết quả nghiệp vụ**. Chỉ di chuyển thao tác khi đã chứng minh hai biểu thức tương đương theo yêu cầu.

### 5.2. `limit` và `sorted`: top-k khác sắp xếp một mẫu đầu vào

```java
List<Integer> scores = List.of(30, 90, 70, 80, 60);

var topTwo = scores.stream()
    .sorted(Comparator.reverseOrder())
    .limit(2)
    .toList();
// [90, 80]

var sortedFirstTwo = scores.stream()
    .limit(2)
    .sorted(Comparator.reverseOrder())
    .toList();
// [90, 30]
```

Muốn **top 2 toàn bộ danh sách**, phải sort (hoặc dùng một thuật toán top-k chuyên dụng) trước khi lấy hai kết quả. `limit(2).sorted()` chỉ sort **hai phần tử đầu tiên của nguồn**, không phải hai phần tử tốt nhất toàn cục.

### 5.3. `limit` không hứa hẹn chọn phần tử nào từ unordered stream

Nếu một stream không có encounter order, `limit(3)` chỉ cần trả **bất kỳ ba phần tử** phù hợp về số lượng, không hứa hẹn là ba phần tử nào. Đặc biệt với parallel stream, tập phần tử được lấy có thể thay đổi theo cách thực thi.

```java
var sample = IntStream.range(0, 1_000)
    .parallel()
    .unordered()
    .limit(3)
    .boxed()
    .toList();

// Không dựa vào việc kết quả luôn là [0, 1, 2].
```

Nếu cần lấy **ba phần tử có ưu tiên rõ ràng**, hãy `sorted(comparator).limit(3)` hoặc dùng giải pháp khác có contract lựa chọn cụ thể.

## 6. `skip(n)`: bỏ phần tử theo vị trí

`skip(long n)` bỏ `n` phần tử đầu và trả các phần tử còn lại (với ordered stream). `skip(0)` không bỏ gì; `skip(n)` với `n < 0` ném `IllegalArgumentException`.

```java
var secondPage = IntStream.rangeClosed(1, 10)
    .skip(3)
    .limit(3)
    .boxed()
    .toList();

System.out.println(secondPage); // [4, 5, 6]
```

Để phân trang ổn định, cần **thứ tự xác định** trước khi skip. Nếu nguồn có thứ tự không đáng tin cậy, cùng một `skip(3)` có thể bỏ những phần tử khác nhau giữa các lần chạy.

### 6.1. Tránh tràn số khi tính offset

```java
static <T> List<T> page(
        List<T> source,
        Comparator<? super T> comparator,
        long pageIndex,
        int pageSize) {
    if (pageIndex < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    long offset = Math.multiplyExact(pageIndex, (long) pageSize);

    return source.stream()
        .sorted(comparator)
        .skip(offset)
        .limit(pageSize)
        .toList();
}
```

`Math.multiplyExact` tránh overflow âm thầm khi trang rất lớn. Phân trang bằng `skip` trên tập dữ liệu lớn thường không hiệu quả vì vẫn phải đi qua phần tử phía trước vị trí offset; nếu dữ liệu được lấy từ database, cân nhắc phân trang ở query và keyset/cursor pagination theo thứ tự có khóa ổn định.

## 7. `takeWhile` và `dropWhile`: thao tác trên prefix

Hai thao tác này được hỗ trợ từ Java 9 và vẫn là API hiện hành trong Java 27. Với **ordered stream**, chúng hoạt động trên **prefix liên tiếp**, không phải tất cả phần tử thỏa predicate ở mọi vị trí.

```java
List<Integer> values = List.of(2, 4, 5, 6, 8);

System.out.println(
    values.stream().takeWhile(n -> n % 2 == 0).toList()
); // [2, 4]

System.out.println(
    values.stream().dropWhile(n -> n % 2 == 0).toList()
); // [5, 6, 8]

System.out.println(
    values.stream().filter(n -> n % 2 == 0).toList()
); // [2, 4, 6, 8]
```

Khi gặp phần tử `5` không thỏa điều kiện, `takeWhile` **dừng lấy prefix**; phần tử `6` và `8` thỏa predicate về sau vẫn không được đưa vào kết quả. Ngược lại, `dropWhile` bỏ `2` và `4` rồi giữ tất cả phần tử còn lại, bao gồm `6`, `8`.

| Predicate | `takeWhile` trên ordered stream | `dropWhile` trên ordered stream |
| --- | --- | --- |
| Tất cả phần tử đều thỏa | Giữ tất cả | Bỏ tất cả |
| Không phần tử nào thỏa | Trả rỗng | Giữ tất cả |
| Prefix thỏa, phần sau không thỏa | Lấy prefix | Bỏ prefix |
| Sau phần tử đầu tiên không thỏa lại có phần tử thỏa | Không lấy các phần tử thỏa ở phía sau | Vẫn giữ các phần tử phía sau |

**`takeWhile` là short-circuiting stateful intermediate operation**, còn **`dropWhile` là stateful nhưng không được phân loại short-circuiting**. Đây là khác biệt quan trọng khi đánh giá chi phí xử lý và nguồn không giới hạn.

### 7.1. Khi nào phù hợp hơn `filter`?

`takeWhile` và `dropWhile` phù hợp khi input **đã có thứ tự hữu ích**, chẳng hạn các sự kiện được sắp theo thời gian và cần lấy phần trước một mốc:

```java
import java.time.Instant;

record Event(Instant time, String action) { }

Instant cutoff = Instant.parse("2026-11-27T10:00:00Z");

List<Event> chronological = List.of(
    new Event(Instant.parse("2026-11-27T09:00:00Z"), "open"),
    new Event(Instant.parse("2026-11-27T09:30:00Z"), "edit"),
    new Event(Instant.parse("2026-11-27T10:30:00Z"), "close")
);

List<Event> beforeCutoff = chronological.stream()
    .takeWhile(e -> e.time().isBefore(cutoff))
    .toList();
// [open, edit]
```

Vì `chronological` được biết là tăng theo thời gian, khi bắt gặp một event sau cutoff thì không cần xét event phía sau để tìm thêm phần tử trước cutoff. **Nếu input không thực sự được sắp xếp**, hãy dùng `filter` để lấy mọi event trước cutoff, hoặc sắp xếp trước nếu logic yêu cầu prefix theo thời gian.

### 7.2. Với unordered stream, kết quả có thể không xác định

Khi stream unordered và chỉ một phần tử input thỏa predicate, `takeWhile` được phép lấy **một tập con bất kỳ của các phần tử thỏa** (kể cả tập rỗng); `dropWhile` được phép bỏ một tập con bất kỳ của các phần tử thỏa.

Do vậy `unordered().takeWhile(...) != filter(...)` về mặt contract. Không nên dùng `takeWhile` để thay thế `filter` khi muốn mọi phần tử thỏa predicate.

## 8. Thứ tự thao tác là một phần của logic nghiệp vụ

Những chuỗi phép toán có cùng danh sách method nhưng khác vị trí thường **không tương đương**:

| Pipeline | Ý nghĩa |
| --- | --- |
| `filter(p).sorted(c).limit(k)` | Top k trong tập phần tử thỏa p |
| `limit(k).filter(p).sorted(c)` | Lọc, sắp xếp trong k phần tử đầu của nguồn |
| `map(key).distinct()` | Lấy các key khác nhau |
| `distinct().map(key)` | Loại object trùng hoàn toàn trước, key có thể còn trùng |
| `sorted(c).limit(k)` | Top k toàn cục theo c |
| `limit(k).sorted(c)` | Sắp xếp chỉ k phần tử đầu |
| `sorted(c).skip(a).limit(b)` | Phân trang trên một thứ tự xác định |
| `takeWhile(p)` | Prefix thỏa p; không lấy phần tử thỏa p xuất hiện sau khi prefix kết thúc |
| `filter(p)` | Tất cả phần tử thỏa p, không giới hạn vào prefix |

### 8.1. Ví dụ: lấy ba category có sản phẩm giá cao nhất

Yêu cầu: trên danh sách sản phẩm, ưu tiên category theo **sản phẩm đắt nhất** của category đó, và trả về ba category đầu tiên. Các bước phải là:

1. Sắp xếp sản phẩm theo giá giảm dần; đặt tie-breaker rõ ràng.
2. Chuyển mỗi sản phẩm thành `category`.
3. `distinct()` trên category để giữ category xuất hiện lần đầu — tức category có sản phẩm giá cao nhất.
4. `limit(3)` lấy ba category.

```java
List<String> bestCategories = products.stream()
    .sorted(Comparator.comparingInt(Product::price)
        .reversed()
        .thenComparing(Product::sku))
    .map(Product::category)
    .distinct()
    .limit(3)
    .toList();
```

Nếu chuyển `distinct()` lên trước `map(Product::category)`, nó sẽ loại trùng **Product** chứ không loại trùng **category**, dẫn đến kết quả sai.

### 8.2. Đưa `filter` lên trước sort khi tương đương

Đối với yêu cầu “top 10 sản phẩm có giá ít nhất 100”, việc lọc sản phẩm không đủ điều kiện trước khi sort thường cho kết quả giống việc sort toàn bộ rồi lọc (nếu comparator không phụ thuộc trạng thái bị thay đổi) nhưng giúp bước sort nhận ít phần tử hơn:

```java
var top = products.stream()
    .filter(p -> p.price() >= 100)
    .sorted(Comparator.comparingInt(Product::price).reversed())
    .limit(10)
    .toList();
```

Quy tắc tối ưu có điều kiện: đẩy bước lọc dữ liệu không cần thiết lên sớm **chỉ khi không thay đổi phép chọn và thứ tự kết quả**. Ví dụ `takeWhile` khác `filter` nên không thể đổi tùy ý.

## 9. Loại trùng theo khóa: `distinct()` chưa đủ

Nếu cần giữ **đối tượng đầu tiên theo một khóa**, `distinct()` không có overload nhận key extractor. Một giải pháp minh bạch là `Collectors.toMap` với merge function, kết hợp `LinkedHashMap` để giữ thứ tự thêm khóa ở pipeline tuần tự:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.function.Function;
import java.util.stream.Collectors;

record Ticket(String id, String group, int priority) { }

List<Ticket> tickets = List.of(
    new Ticket("A", "billing", 2),
    new Ticket("B", "technical", 3),
    new Ticket("C", "billing", 5),
    new Ticket("D", "technical", 1)
);

var firstByGroup = tickets.stream()
    .sorted(Comparator.comparingInt(Ticket::priority).reversed()
        .thenComparing(Ticket::id))
    .collect(Collectors.toMap(
        Ticket::group,
        Function.identity(),
        (first, ignored) -> first,
        LinkedHashMap::new
    ));

List<Ticket> winners = new ArrayList<>(firstByGroup.values());
System.out.println(winners.stream().map(Ticket::id).toList());
// [C, B] — ưu tiên cao nhất từng group, theo thứ tự đã sắp
```

Lưu ý:

- Pipeline trên là **sequential**, dùng encounter order của stream đã `sorted` để lựa chọn object đại diện. Đối với parallel execution, hãy kiểm tra và xác định rõ các bảo đảm collector/ordering thay vì mặc định mọi cách chia và gộp đều giữ ý định.
- `LinkedHashMap` giữ thứ tự chèn của các key (theo iteration order mặc định); `HashMap` không cam kết điều đó.
- `Collectors.toMap` không cho phép xây dựng kết quả có giá trị null một cách tùy tiện; nên validate key/value trước.
- Nếu chỉ cần một **tập khóa** mà không cần cả object, `map(key).distinct()` đơn giản hơn và thường dễ đọc hơn.

**Không dùng cách sau để giả lập distinct-by-key trong parallel stream:**

```java
// KHÔNG NÊN DÙNG:
// Set<String> seen = new HashSet<>();
// stream.filter(item -> seen.add(item.group())).toList();
```

Lambda ở trên phụ thuộc state bên ngoài, can thiệp vào collection chia sẻ và có nguy cơ race condition khi parallel. Ngay cả khi dùng collection concurrent, ý nghĩa “bản đầu tiên” có thể không còn rõ ràng do thứ tự thực thi. Dùng collector hoặc thuật toán xác định thứ tự dữ liệu ngay từ đầu.

## 10. Parallel stream: ràng buộc thứ tự làm tăng chi phí

`parallel()` không tự động làm pipeline nhanh hơn. Stateful operations có thể phải phối hợp giữa các nhánh song song, đồng bộ, gom kết quả hoặc lưu dữ liệu trung gian. Theo ghi chú API của Stream Java 27:

- `distinct()` trên **ordered parallel stream** thường đắt do phải giữ bản xuất hiện đầu tiên theo encounter order; có thể cần full barrier và nhiều bộ đệm.
- `limit()`/`skip()` trên **ordered parallel stream** khó hơn vì phải lấy/bỏ đúng phần tử ở vị trí đầu theo encounter order.
- `takeWhile()`/`dropWhile()` trên **ordered parallel stream** có thể đắt vì phải xác định đúng prefix dài nhất.
- `sorted()` vốn phải phối hợp nhiều phần tử và có thể tạo rào cản thực thi; parallel sort không loại bỏ nhu cầu tổ chức dữ liệu.

### 10.1. Khi nào `unordered()` có thể giúp?

Nếu yêu cầu chỉ là **lấy một số lượng phần tử bất kỳ**, **loại các giá trị trùng không quan tâm bản đại diện**, hoặc **tính toán không phụ thuộc thứ tự**, có thể cho phép unordered pipeline để giảm ràng buộc:

```java
var any100Unique = data.parallelStream()
    .unordered()
    .distinct()
    .limit(100)
    .toList();
```

Kết quả có tối đa 100 giá trị duy nhất theo `equals`, nhưng không cam kết chính xác **những giá trị nào** sẽ được chọn khi có nhiều hơn 100 giá trị duy nhất. Chỉ dùng khi đây thực sự là contract mà ứng dụng chấp nhận.

Nếu `data` đã ít hơn 100 giá trị unique, kết quả có thể chứa tất cả unique dù thứ tự không được hứa hẹn. Không coi `unordered()` là một tối ưu an toàn với chức năng “trang đầu tiên”, “giao dịch mới nhất” hoặc “lần xuất hiện đầu tiên”.

### 10.2. `sequential()` có thể tốt hơn `parallel()`

Khi cần encounter order ổn định, ví dụ:

```java
var first100 = data.stream()
    .distinct()
    .limit(100)
    .toList();
```

Thực thi tuần tự có thể nhanh hơn một parallel pipeline phải liên tục đồng bộ để bảo toàn thứ tự. Hiệu quả phụ thuộc số lượng phần tử, chi phí xử lý mỗi phần tử, loại nguồn, số core, tải máy và khả năng chia dữ liệu. Hãy đo bằng benchmark có warm-up và dữ liệu thực, tránh tuyên bố parallel luôn nhanh hơn.

### 10.3. Đừng dùng side effect trong lambda để chứng minh thứ tự

```java
var result = values.stream()
    .peek(System.out::println)
    .distinct()
    .limit(3)
    .toList();
```

`peek` chủ yếu phục vụ quan sát/debug. JVM có quyền tối ưu bỏ các công đoạn hoặc lời gọi hàm hành vi nếu không ảnh hưởng kết quả. Với short-circuit, không phải mọi phần tử nguồn đều cần đi qua `peek`. Trong parallel execution, thứ tự in còn phụ thuộc scheduling. Vì vậy **không dựa vào `peek` hoặc log side effect để xác nhận pipeline xử lý chính xác mỗi phần tử một lần**.

## 11. Các bẫy về dữ liệu lớn, vô hạn và tài nguyên

### 11.1. Sắp xếp trước khi lấy ít phần tử

`sorted().limit(10)` vẫn là **top 10 toàn cục**. Nếu nguồn chứa hàng triệu phần tử, sort có thể tốn bộ nhớ và CPU đáng kể. Các lựa chọn khác khi phù hợp:

- `max(comparator)` hoặc `min(comparator)` nếu chỉ cần một cực trị.
- Dùng priority queue có kích thước k khi cần top-k với chi phí bộ nhớ có giới hạn theo k.
- Nhờ hệ quản trị cơ sở dữ liệu thực hiện `ORDER BY ... LIMIT ...` nếu dữ liệu vốn nằm trong database và có chỉ mục phù hợp.
- Dùng thuật toán domain chuyên biệt thay vì cố gắng diễn tả tất cả qua một stream.

Lưu ý: `priority queue` hoặc database có những trade-off và contract riêng; không có bảo đảm chúng luôn nhanh hơn ở mọi tải.

### 11.2. `distinct()` trên nguồn không giới hạn

`distinct()` có thể cần lưu nhiều giá trị đã gặp; trên stream vô hạn có vô số giá trị phân biệt, việc nhớ các phần tử có thể tăng không giới hạn. `Stream.iterate(0, n -> n+1).distinct().limit(10)` có thể kết thúc nhờ `limit(10)` và không nhất thiết nhớ vô hạn dữ liệu; nhưng `distinct().count()` trên nguồn vô hạn không thể hoàn tất.

Đối với luồng sự kiện lâu dài, hãy xem xét **cửa sổ thời gian**, giới hạn kích thước tập khóa, chính sách hết hạn hoặc xử lý theo batch bằng công cụ phù hợp — Stream API không tự cung cấp windowed deduplication cho nguồn vô hạn.

### 11.3. Không sửa nguồn khi đang duyệt

```java
// KHÔNG NÊN:
// List<Integer> items = new ArrayList<>(List.of(1, 2, 3));
// items.stream().filter(n -> {
//     items.add(99); // Can thiệp nguồn đang được duyệt
//     return true;
// }).toList();
```

Hành vi như vậy có thể dẫn đến `ConcurrentModificationException`, kết quả sai hoặc hành vi không thể dự đoán tùy nguồn. Nếu cần biến đổi, hãy tạo kết quả mới từ stream rồi cập nhật cấu trúc nguồn sau khi terminal operation đã hoàn tất.

### 11.4. Stream một lần và đóng tài nguyên

Stream đã được tiêu thụ thì không thể dùng lại. Với `Collection.stream()`, thường không cần `close`; với nguồn dùng tài nguyên hệ thống như `Files.lines(path)`, phải dùng **try-with-resources** để đóng stream.

```java
import java.nio.file.Files;
import java.nio.file.Path;

try (var lines = Files.lines(Path.of("events.log"))) {
    List<String> first10 = lines
        .filter(line -> !line.isBlank())
        .limit(10)
        .toList();

    System.out.println(first10);
}
```

Đoạn ví dụ chỉ minh họa pattern quản lý tài nguyên; để dùng thật, xử lý `IOException` theo ngữ cảnh của ứng dụng.

## 12. Ví dụ tổng hợp chạy được với Java hiện đại

Bài toán: lấy **ba nhóm sản phẩm có giá trị cao nhất**, ưu tiên mỗi nhóm theo sản phẩm đắt nhất; chỉ nhận giá hợp lệ và tạo kết quả theo thứ tự xác định.

```java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class StatefulStreamExample {
    record Product(String sku, String category, int price) {
        Product {
            sku = Objects.requireNonNull(sku, "sku").strip();
            category = Objects.requireNonNull(category, "category").strip();
            if (sku.isEmpty() || category.isEmpty()) {
                throw new IllegalArgumentException("SKU/category must not be blank");
            }
            if (price < 0) {
                throw new IllegalArgumentException("Price must not be negative");
            }
        }
    }

    static List<String> topCategories(List<Product> products, int count) {
        Objects.requireNonNull(products, "products");
        if (count < 0) {
            throw new IllegalArgumentException("count must not be negative");
        }

        return products.stream()
            .sorted(
                Comparator.comparingInt(Product::price)
                    .reversed()
                    .thenComparing(Product::sku)
            )
            .map(Product::category)
            .distinct()
            .limit(count)
            .toList();
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("P1", "Electronics", 1_000),
            new Product("P2", "Stationery", 400),
            new Product("P3", "Home", 300),
            new Product("P4", "Electronics", 900),
            new Product("P5", "Books", 200),
            new Product("P6", "Stationery", 1_200)
        );

        List<String> result = topCategories(products, 3);
        System.out.println(result);
        // [Stationery, Electronics, Home]
    }
}
```

Giải thích từng bước:

1. `Product` kiểm tra dữ liệu đầu vào một lần khi được tạo; giá không âm và các khóa không rỗng.
2. `sorted` xếp theo giá giảm dần và SKU tăng dần để phá hòa theo quy tắc xác định.
3. `map(Product::category)` chuyển sang chính khóa cần loại trùng.
4. `distinct()` giữ category đầu tiên, tương ứng với sản phẩm có thứ hạng tốt nhất trong category đó.
5. `limit(count)` giữ tối đa ba category theo thứ tự vừa xác lập.
6. `toList()` trả kết quả không thể sửa, phù hợp với API trả danh sách chỉ đọc.

Không nên đổi thứ tự `distinct` và `map` trong bài toán này. Cũng không nên đưa `limit` lên trước `sorted` vì sẽ đổi yêu cầu từ “top category toàn cục” thành “top category trong một prefix tùy ý”.

## 13. Các lỗi hay gặp và cách sửa

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Dùng `distinct()` trên object nhưng muốn unique theo ID | `distinct` dựa vào `equals` của cả object | `map(ID).distinct()` hoặc collector chọn theo key |
| Nghĩ `sorted().distinct()` loại phần tử comparator bằng 0 | `distinct` không dùng comparator | Định nghĩa equality/key phù hợp |
| Viết `limit(n).sorted()` để lấy top-n | Chỉ sort n phần tử đầu nguồn | `sorted().limit(n)` hoặc thuật toán top-k |
| Dùng `takeWhile` như `filter` | Nó xử lý prefix, dừng ở phần tử đầu tiên không thỏa trong ordered stream | Dùng `filter` để lấy mọi phần tử thỏa |
| Dùng `skip(n)` trên nguồn unordered để phân trang | Không có thứ tự ổn định để xác định phần bị bỏ | Xác định sort key và thứ tự trước khi phân trang |
| Cho rằng `parallel()` luôn nhanh | Stateful operations có thể tạo barrier và buffering | Đo benchmark, xem `sequential()`/tối ưu nguồn |
| Gọi `unordered()` với logic “first”, “top”, “latest” | Bỏ ràng buộc encounter order | Giữ ordered stream hoặc sort theo tiêu chí rõ |
| Sử dụng `filter(x -> seen.add(key(x)))` với set chia sẻ | Lambda mang trạng thái ngoài, có race khi parallel | Dùng collector hoặc thuật toán có contract rõ |
| Thay đổi field tham gia `equals` trong `distinct` | Equality không ổn định | Dùng value object bất biến |
| Dùng `peek` để thực thi nghiệp vụ quan trọng | Side effect có thể không được gọi cho tất cả phần tử | Dùng terminal operation/hàm thu thập có chủ đích |
| `sorted` nguồn vô hạn rồi mới `limit` | Sort cần đủ dữ liệu đầu vào | Đặt giới hạn hợp lệ trước sort nếu bài toán cho phép |
| Trừ hai số trong comparator | Có thể tràn số và sai thứ tự | Dùng `Comparator.comparingInt`, `Integer.compare` |
| Sử dụng lại stream sau terminal operation | Stream chỉ được duyệt một lần | Lấy một stream mới từ nguồn |

## 14. Checklist thiết kế pipeline có trạng thái

Trước khi triển khai hoặc tối ưu, hãy xác nhận:

1. **Nguồn có encounter order hay không?** Kết quả có cần một thứ tự xác định không?
2. **Tiêu chí loại trùng là gì?** `equals` của cả object hay một khóa nghiệp vụ?
3. **Comparator có thứ tự rõ và tie-breaker phù hợp không?** Có xử lý null, locale và tràn số đúng cách không?
4. **`limit` đứng trước hay sau sort/filter có đúng nghiệp vụ không?**
5. **`takeWhile`/`dropWhile` có thật sự cần prefix không?** Dữ liệu đã được sắp theo đúng tiêu chí chưa?
6. **Nguồn có thể vô hạn không?** Bước nào bảo đảm đầu ra hữu hạn?
7. **Bước nào có thể phải giữ nhiều phần tử?** Có nguy cơ quá tốn bộ nhớ không?
8. **Có bắt buộc parallel không?** Nếu có, benchmark đã chứng minh lợi ích chưa?
9. **Có side effect hoặc state chia sẻ trong lambda không?** Có thể chuyển sang collector thuần hoặc xử lý tuần tự rõ ràng không?
10. **Kết quả trả về có contract hợp lý không?** Một lần duyệt, quản lý tài nguyên và thứ tự đã được mô tả chưa?

**Ghi nhớ:** `sorted`, `distinct`, `limit` cùng là stateful intermediate operations nhưng **không thể thay đổi vị trí tùy ý**. Encounter order, định nghĩa equality và yêu cầu chọn phần tử mới quyết định pipeline đúng hay sai. Tối ưu hiệu năng chỉ an toàn sau khi đã cố định các hợp đồng ngữ nghĩa đó.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — Stream<T>](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): định nghĩa `distinct`, `sorted`, `limit`, `skip`, `takeWhile`, `dropWhile` và ghi chú về thứ tự/parallel.
- [Java SE 27 API — java.util.stream package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html): stream pipeline, stateless/stateful, laziness, short-circuiting và side effects.
- [Java SE 27 API — BaseStream<T,S>](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/BaseStream.html): `sequential`, `parallel`, `unordered` và quản lý stream.
- [Java SE 27 API — IntStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html): `range`, `boxed` và các thao tác có trạng thái cho primitive stream.
- [Java SE 27 API — Comparator<T>](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): `comparingInt`, `thenComparing`, `reversed`, `nullsFirst`/`nullsLast`.
- [Java SE 27 API — Collectors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html): `toMap` với merge function và map supplier.
