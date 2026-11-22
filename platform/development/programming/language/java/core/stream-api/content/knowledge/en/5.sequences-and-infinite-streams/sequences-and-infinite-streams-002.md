# Tạo nguồn bằng `Stream.generate` và `Supplier`

Khi xử lý dữ liệu bằng Java Stream API, không phải lúc nào phần tử cũng đã nằm sẵn trong `List`, mảng hoặc tệp. Đôi khi chương trình cần **tạo giá trị khi pipeline yêu cầu**: sinh dữ liệu mẫu, lấy một số ngẫu nhiên, cấp mã định danh hoặc tạo các sự kiện giả lập. `Stream.generate` kết hợp với `Supplier` cho phép mô tả loại nguồn này bằng một pipeline lazy.

Bài thuộc chương **Dãy số và Stream vô hạn** của module **JAVA_STREAM_API**. Mục tiêu là hiểu cách `Supplier` cung cấp phần tử, vì sao `Stream.generate` là nguồn không giới hạn, cách chặn số lượng phần tử trước khi dùng `filter`, `map`, `reduce`, `collect`, và các rủi ro về thứ tự, trạng thái, tài nguyên và hiệu năng. Ví dụ chính sử dụng Java 17 trở lên; phần kiến thức nền `Stream.generate` và `Supplier` đã có từ Java 8.

## 1. `Supplier<T>` là gì?

`Supplier<T>` là một functional interface trong `java.util.function`. Hợp đồng cốt lõi của nó có **một phương thức trừu tượng**:

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

`get()` **không nhận tham số** và **trả về một giá trị** kiểu `T`. Giá trị có thể là hằng số, kết quả của phép tính, kết quả gọi API hoặc một đối tượng mới. Việc có tạo ra giá trị mới ở mỗi lần gọi hay không hoàn toàn phụ thuộc cách triển khai `Supplier`.

```java
import java.util.UUID;
import java.util.function.Supplier;

Supplier<String> fixed = () -> "Java";
Supplier<UUID> newId = UUID::randomUUID;

System.out.println(fixed.get()); // Java
System.out.println(newId.get()); // Một UUID được tạo khi get() chạy
```

Hai cách viết phổ biến là lambda `() -> expression` và method reference `SomeClass::staticMethod` hoặc `object::instanceMethod`.

Lưu ý:

- `Supplier` không có đối số để nhận **phần tử trước đó**. Nếu cần mô tả dãy số theo quy tắc “phần tử tiếp theo phụ thuộc phần tử trước”, `Stream.iterate` thường phù hợp hơn.
- Không có yêu cầu `get()` luôn trả kết quả khác nhau. `() -> 5` có thể trả `5` mãi mãi.
- `Supplier` có thể giữ trạng thái bên trong hoặc tham chiếu đến trạng thái bên ngoài; cách dùng này cần đặc biệt thận trọng khi stream chạy song song.
- `Supplier.get()` có thể trả `null`; bản thân điều đó **không** phải tín hiệu kết thúc stream.

## 2. Cú pháp và hợp đồng của `Stream.generate`

Trong `java.util.stream.Stream`, phương thức có dạng:

```java
public static <T> Stream<T> generate(Supplier<? extends T> s)
```

`Stream.generate(supplier)` tạo ra một stream **tuần tự, không có encounter order được xác định và không giới hạn về số phần tử**. Mỗi lần cần phần tử, nguồn gọi `supplier.get()` để tạo giá trị.

```java
import java.util.List;
import java.util.stream.Stream;

List<String> words = Stream.generate(() -> "Java")
        .limit(4)
        .toList();

System.out.println(words); // [Java, Java, Java, Java]
```

Ở ví dụ này:

1. `Stream.generate(() -> "Java")` dựng nguồn có khả năng sinh phần tử liên tục.
2. `limit(4)` giới hạn pipeline còn tối đa bốn phần tử.
3. `toList()` là terminal operation yêu cầu dữ liệu và tạo danh sách kết quả.

`Stream.generate` **không xây dựng sẵn một danh sách vô hạn** trong bộ nhớ. Nó cung cấp phần tử theo nhu cầu của pipeline. Tuy nhiên, tính lazy không tự bảo vệ chương trình: nếu terminal operation đòi tiêu thụ tất cả phần tử từ một nguồn không giới hạn, chương trình có thể chạy mãi hoặc cạn tài nguyên.

### 2.1. Minh họa tính lazy

```java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.generate(() -> {
    System.out.println("Supplier.get()");
    return 7;
});

System.out.println("Đã tạo stream");
// Tới đây chưa có dòng "Supplier.get()".

numbers.limit(2).forEach(System.out::println);
// Khi terminal operation chạy:
// Supplier.get()
// 7
// Supplier.get()
// 7
```

Lambda tạo `Supplier` được truyền vào `generate`, nhưng **thân lambda chỉ được gọi khi cần phần tử**. Thứ tự in trong ví dụ có tính minh họa cho pipeline **tuần tự**. Khi dùng `parallel()` hoặc thao tác có thể tối ưu hóa, không lấy số lần và thứ tự gọi lambda làm hợp đồng nghiệp vụ.

### 2.2. Những đặc điểm cần phân biệt

| Đặc điểm | `Stream.generate(supplier)` |
|---|---|
| Kiểu phần tử | `T`, do `Supplier<? extends T>` cung cấp |
| Kích thước nguồn | Không giới hạn; không tự kết thúc |
| Chế độ ban đầu | Tuần tự (`sequential`) |
| Encounter order | **Không có thứ tự được bảo đảm** (`unordered`) |
| Khi tạo giá trị | Khi pipeline yêu cầu, bằng `supplier.get()` |
| Tạo chuỗi dựa trên phần tử trước | Không có cơ chế truyền phần tử trước vào `get()` |
| Giải phóng tài nguyên | Không tự đóng các tài nguyên mà supplier tự mở hoặc sử dụng |

Một nguồn được tạo ra tuần tự **không đồng nghĩa** với một nguồn có encounter order. Ngay cả khi lần chạy hiện tại quan sát thấy các giá trị theo một trình tự quen thuộc, các thao tác phụ thuộc thứ tự không nên dựa vào điều đó khi sử dụng `generate`.

## 3. Kết hợp với `limit` để biến nguồn vô hạn thành tác vụ hữu hạn

Trong hầu hết tình huống cần một tập kết quả hữu hạn, cách dùng an toàn và rõ ràng nhất là đặt giới hạn sớm trong pipeline.

```java
import java.util.UUID;
import java.util.stream.Stream;

List<String> ids = Stream.generate(UUID::randomUUID)
        .limit(5)
        .map(UUID::toString)
        .toList();

System.out.println(ids); // Danh sách 5 UUID dạng chuỗi
```

`UUID::randomUUID` là nhà cung cấp giá trị; `limit(5)` quyết định số phần tử được đưa vào các thao tác tiếp theo. Các UUID có xác suất trùng cực nhỏ trong thực tế, nhưng đây không phải bảo đảm toán học rằng mọi lần sinh đều khác nhau.

### 3.1. Sinh số ngẫu nhiên trong một khoảng

```java
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.Stream;

List<Integer> rolls = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(1, 7)
).limit(8).toList();

System.out.println(rolls); // 8 số nguyên, mỗi số từ 1 đến 6
```

`nextInt(1, 7)` có cận dưới **bao gồm** `1` và cận trên **không bao gồm** `7`. `ThreadLocalRandom.current()` phù hợp khi cần sinh số ngẫu nhiên trong các tác vụ có thể chạy trên nhiều thread, nhưng kết quả không được thiết kế để tái lập chính xác giữa các lần chạy.

Khi cần dữ liệu kiểm thử lặp lại được, nên dùng bộ sinh có seed rõ ràng và kiểm soát chế độ thực thi tuần tự, hoặc chuẩn bị trước tập dữ liệu kiểm thử cố định.

### 3.2. Áp dụng `map`, `filter`, `reduce` và `collect`

```java
int total = Stream.generate(() -> 3)
        .limit(4)
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

System.out.println(total); // 24
```

Tương tự, có thể nhóm hoặc thu thập kết quả hữu hạn:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, Long> frequency = Stream.generate(() -> 2)
        .limit(5)
        .collect(Collectors.groupingBy(
                n -> n,
                Collectors.counting()
        ));

System.out.println(frequency); // {2=5}
```

Điều kiện quan trọng: phải biết **terminal operation có thể hoàn tất hay không**. Một pipeline bắt đầu từ nguồn không giới hạn vẫn có thể kết thúc nếu đặt `limit` phù hợp trước những thao tác cần toàn bộ đầu vào.

### 3.3. Vị trí đặt `limit` làm thay đổi kết quả

```java
List<Integer> a = Stream.generate(() -> 5)
        .limit(3)
        .map(n -> n * 10)
        .toList();
// [50, 50, 50]
```

Đối với `filter`, thứ tự của `limit` và `filter` có ý nghĩa:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger aCounter = new AtomicInteger();
List<Integer> firstFiveThenEven = Stream.generate(aCounter::getAndIncrement)
        .limit(5)
        .filter(n -> n % 2 == 0)
        .toList();
// Pipeline tuần tự: [0, 2, 4]

AtomicInteger bCounter = new AtomicInteger();
List<Integer> firstThreeEven = Stream.generate(bCounter::getAndIncrement)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
// Pipeline tuần tự: [0, 2, 4]
```

Hai ví dụ trên được cố ý viết để minh họa cách các bước xử lý dữ liệu khác nhau, **không phải** để khuyến nghị dùng counter như một nguồn có thứ tự: `generate` vẫn là nguồn `unordered`. Ở trường hợp đầu, chỉ năm lần sinh đầu tiên được xét rồi lọc; ở trường hợp sau, pipeline tiếp tục yêu cầu giá trị cho đến khi nhận đủ ba phần tử chẵn. Với predicate khác hoặc giới hạn khác, số lượng và nội dung kết quả có thể khác rõ rệt.

Nếu `filter` không bao giờ cho phần tử đi qua, `filter(...).limit(3)` sẽ không kết thúc. Đặt `limit` **trước** `filter` giúp chặn số phần tử nguồn phải xét, đổi lại kết quả sau lọc có thể ít hơn ba phần tử.

## 4. Những pipeline không kết thúc và cách khắc phục

Do `generate` không có điểm kết thúc tự nhiên, một số đoạn mã trông ngắn gọn nhưng có thể chạy vô hạn.

### 4.1. Terminal operation cần toàn bộ nguồn

```java
// Không chạy: không bao giờ đếm xong nguồn vô hạn.
// long count = Stream.generate(() -> 1).count();

// Có giới hạn rõ ràng, nên hoàn tất.
long count = Stream.generate(() -> 1)
        .limit(100)
        .count();
System.out.println(count); // 100
```

Tương tự, `collect(Collectors.toList())`, `toList()`, `reduce` hoặc `sum` trên toàn bộ nguồn vô hạn sẽ không thể hoàn tất trong điều kiện bình thường. Với `toList()`, chương trình còn có thể tăng mức sử dụng bộ nhớ liên tục.

### 4.2. `sorted` và `distinct` trước `limit`

```java
// Không chạy: sorted() cần biết toàn bộ đầu vào để sắp xếp.
// Stream.generate(() -> 5).sorted().limit(10).toList();

// Hoàn tất: chỉ sắp xếp 10 phần tử.
List<Integer> sortedSample = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(100)
).limit(10).sorted().toList();
```

`distinct()` trước `limit` cũng có thể không kết thúc nếu nguồn không bao giờ tạo đủ số giá trị khác nhau:

```java
// Không chạy: nguồn chỉ có một giá trị khác nhau.
// Stream.generate(() -> "A").distinct().limit(2).toList();

// Hoàn tất: chỉ xử lý mười giá trị của nguồn.
List<String> distinct = Stream.generate(() -> "A")
        .limit(10)
        .distinct()
        .toList();
System.out.println(distinct); // [A]
```

Hãy nhớ hai mục tiêu riêng:

- **Chọn đủ N phần tử đạt điều kiện**: có thể phải đọc rất lâu hoặc vô hạn nếu điều kiện hiếm hoặc bất khả thi.
- **Xét tối đa N phần tử nguồn**: đặt `limit(N)` trước bước lọc/loại trùng; số phần tử kết quả có thể nhỏ hơn N.

### 4.3. `takeWhile` không thay thế tùy tiện cho cơ chế dừng của `generate`

`takeWhile` được thêm ở Java 9. Với **stream có thứ tự**, nó lấy tiền tố liên tiếp thỏa predicate. Nhưng `Stream.generate` tạo stream **không có encounter order**, nên `takeWhile` không có hợp đồng “dừng đúng ở phần tử đầu tiên không thỏa” như một dãy có thứ tự.

Vì vậy, tránh dựa vào `Stream.generate(supplier).takeWhile(...)` để giải mã một giao thức bắt buộc dừng tại sentinel đầu tiên, nhất là khi dùng `parallel()`. Khi cần một dãy có thứ tự với điều kiện tiếp diễn cụ thể, hãy cân nhắc `Stream.iterate(seed, hasNext, next)` (Java 9+) hoặc xây dựng `Spliterator` phù hợp. Khi đọc dữ liệu từ tệp, sử dụng API nguồn chuyên dụng như `BufferedReader.lines()` hoặc `Files.lines()` và quản lý việc đóng tài nguyên.

## 5. `Supplier` có trạng thái: ví dụ và giới hạn

`Supplier` có thể nhớ số lần được gọi, giúp hiểu cơ chế cấp phần tử:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

AtomicInteger counter = new AtomicInteger();
Supplier<Integer> next = counter::getAndIncrement;

List<Integer> numbers = Stream.generate(next)
        .limit(5)
        .toList();

System.out.println(numbers); // Với ví dụ tuần tự: [0, 1, 2, 3, 4]
```

Mặc dù `AtomicInteger` bảo đảm mỗi thao tác tăng là nguyên tử, **nó không tạo encounter order cho `Stream.generate`**. Khi chuyển sang `parallel()`, các thread có thể gọi `get()` và hoàn thành khác thứ tự; không được suy ra kết quả luôn là `[0, 1, 2, 3, 4]`.

```java
// Không dùng nếu cần dãy thứ tự xác định:
// Stream.generate(counter::getAndIncrement)
//       .parallel().limit(5).toList();

// Dãy liên tiếp có thứ tự: mô tả bằng iterate hoặc range.
List<Integer> ordered = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();
System.out.println(ordered); // [0, 1, 2, 3, 4]
```

`AtomicInteger` giúp tránh mất lần tăng, nhưng không giải quyết được tất cả yêu cầu về thứ tự hoặc semantics của một nguồn sinh phần tử. Với `int` lớn, dãy tăng liên tục còn có thể tràn số; cần giới hạn rõ ràng và chọn kiểu dữ liệu phù hợp.

### 5.1. Tránh chia sẻ mutable state tùy tiện trong `parallel()`

```java
int[] holder = {0};

// Không an toàn khi chạy song song: cập nhật holder[0] có data race.
// Stream.generate(() -> holder[0]++).parallel().limit(100).toList();
```

Ngay cả khi dùng cấu trúc thread-safe, mã vẫn có thể khó kiểm soát thứ tự và số lần sinh khi pipeline rẽ nhánh hoặc dừng sớm. Để khai thác xử lý song song, ưu tiên `Supplier` không phụ thuộc trạng thái dùng chung, ví dụ:

```java
List<Integer> randomValues = Stream.generate(
        () -> ThreadLocalRandom.current().nextInt(1, 101)
).parallel().limit(20).toList();

System.out.println(randomValues.size()); // 20
```

Đừng mặc định `parallel()` nhanh hơn: cấp phát tác vụ, đồng bộ, thu thập kết quả và kích thước dữ liệu có thể khiến mã chậm hơn. Nếu thứ tự và khả năng tái lập là yêu cầu nghiệp vụ, chọn nguồn có encounter order, tránh trạng thái dùng chung và đo hiệu năng bằng dữ liệu đại diện.

## 6. So sánh với các nguồn tạo dãy khác

Không phải trường hợp “sinh dữ liệu bằng hàm” nào cũng nên dùng `Stream.generate`.

| Nguồn | Kích thước | Có encounter order? | Giá trị tiếp theo từ đâu? | Dùng khi |
|---|---|---|---|---|
| `Stream.generate(supplier)` | Không giới hạn | Không | Gọi `supplier.get()` | Sinh các mẫu, UUID, giá trị ngẫu nhiên |
| `Stream.iterate(seed, next)` | Không giới hạn nếu không chặn | Có | Áp dụng `next` lên giá trị trước | Dãy truy hồi, lũy thừa, tiến trình theo bước |
| `Stream.iterate(seed, hasNext, next)` | Có thể hữu hạn | Có | Dừng khi `hasNext` không thỏa | Dãy tuần tự có điều kiện dừng |
| `IntStream.range(start, end)` | Hữu hạn | Có | Các số nguyên tăng liên tục | Chỉ số, khoảng số nguyên |
| `Stream.of(values...)` | Hữu hạn | Có | Các giá trị có sẵn | Tập nhỏ các hằng số hoặc đối tượng |

Ví dụ về sự khác biệt:

```java
// Cấp mã mới mỗi khi được yêu cầu (không có thứ tự logic được cam kết).
List<UUID> ids = Stream.generate(UUID::randomUUID)
        .limit(3)
        .toList();

// Dãy phụ thuộc giá trị trước: 1, 2, 4, 8, 16.
List<Integer> powersOfTwo = Stream.iterate(1, n -> n * 2)
        .limit(5)
        .toList();
System.out.println(powersOfTwo); // [1, 2, 4, 8, 16]

// Khoảng hữu hạn, giữ thứ tự: 0, 1, 2, 3, 4.
int[] indexes = java.util.stream.IntStream.range(0, 5).toArray();
```

Hai overload `Stream.iterate` không giống nhau: bản `iterate(seed, next)` (Java 8) là nguồn không giới hạn; bản `iterate(seed, hasNext, next)` (Java 9+) có điều kiện để kết thúc. Trong trường hợp cần một dãy số cụ thể, `IntStream.range` và `IntStream.iterate` còn tránh boxing sang `Integer`.

## 7. Kết hợp với các thao tác terminal ngắn mạch

Một nguồn vô hạn **có thể** được tiêu thụ bằng terminal operation ngắn mạch, nhưng phải xem điều kiện có thực sự tìm thấy kết quả hay không.

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> sample = Stream.generate(() -> 42).findAny();
System.out.println(sample.orElseThrow()); // 42

boolean found = Stream.generate(() -> 42)
        .anyMatch(n -> n > 40);
System.out.println(found); // true
```

`findAny()` có thể hoàn tất khi tìm được một phần tử và không có yêu cầu chọn “đầu tiên”. Trái lại:

```java
// Không chạy: không phần tử nào thỏa điều kiện.
// boolean found = Stream.generate(() -> 42).anyMatch(n -> n < 0);
```

Với một nguồn vô hạn, `allMatch`, `noneMatch`, `anyMatch`, `findAny` hoặc `findFirst` chỉ có cơ hội hoàn tất khi hợp đồng short-circuit cho phép dừng với dữ liệu thực tế. `findFirst()` trên nguồn `generate` không mang nghĩa “giá trị đầu tiên của một dãy có thứ tự”, do nguồn không có encounter order.

## 8. Giá trị `null`, lỗi và tài nguyên

### 8.1. `null` vẫn là một phần tử

```java
List<String> values = Stream.generate(() -> (String) null)
        .limit(2)
        .toList();

System.out.println(values); // [null, null]
```

`Supplier.get()` trả `null` không khiến nguồn kết thúc. Nếu pipeline không nhận `null`, hãy xử lý rõ bằng `filter(Objects::nonNull)` hoặc thiết kế nguồn tạo giá trị không null. Cẩn thận: `filter(Objects::nonNull).limit(3)` sẽ không kết thúc nếu supplier luôn trả null.

Một số terminal operation như `findFirst()` hoặc `findAny()` có thể ném `NullPointerException` nếu phần tử được chọn là `null`. Không nhầm `Stream.generate(() -> null)` với `Stream.empty()` hoặc `Stream.ofNullable(null)`.

### 8.2. Ngoại lệ trong supplier

Nếu `get()` ném một unchecked exception, lỗi xuất hiện khi terminal operation đòi phần tử tương ứng:

```java
Stream<Integer> source = Stream.generate(() -> {
    throw new IllegalStateException("Không cấp được giá trị");
});

// Chỉ tới bước tiêu thụ mới phát sinh IllegalStateException:
// source.limit(1).toList();
```

`Supplier.get()` không khai báo checked exception trong chữ ký. Khi cần thao tác I/O hoặc nguồn có trạng thái kết thúc, nên sử dụng API stream/spliterator chuyên dụng thay vì nhét toàn bộ việc đọc và xử lý lỗi vào lambda.

### 8.3. Vòng đời stream và việc đóng tài nguyên

```java
Stream<String> stream = Stream.generate(() -> "x");
System.out.println(stream.limit(3).count()); // 3

// Không được dùng lại cùng đối tượng stream sau terminal operation:
// stream.findAny(); // IllegalStateException
```

`Stream.generate` tự nó không mở tệp hoặc kết nối. Tuy nhiên, nếu supplier truy cập tài nguyên bên ngoài, `Stream.close()` **không tự động đóng tài nguyên đó** trừ khi bạn thiết kế việc đóng phù hợp (ví dụ đăng ký `onClose` và gọi `close`, thường qua `try-with-resources`). Đối với tệp, ưu tiên nguồn và API đóng tài nguyên đã được thư viện cung cấp.

## 9. Ví dụ tổng hợp có thể chạy (Java 17+)

Chương trình sau kết hợp ba tình huống: nguồn lazy có `Supplier`, tạo mẫu ngẫu nhiên hữu hạn và tạo dãy có thứ tự bằng `iterate`.

```java
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class GenerateAndSupplierDemo {
    public static void main(String[] args) {
        // 1. Supplier chỉ được gọi khi pipeline cần phần tử.
        AtomicInteger calls = new AtomicInteger();
        Supplier<Integer> nextNumber = calls::incrementAndGet;

        Stream<Integer> lazySource = Stream.generate(nextNumber);
        System.out.println(calls.get()); // 0

        List<Integer> samples = lazySource.limit(3).toList();
        System.out.println(samples);     // Chạy tuần tự: [1, 2, 3]
        System.out.println(calls.get()); // 3 trong pipeline tuần tự này

        // 2. Một nguồn sinh dữ liệu có thể chặn bằng limit.
        List<Integer> dice = Stream.generate(
                () -> ThreadLocalRandom.current().nextInt(1, 7)
        ).limit(5).toList();
        System.out.println(dice);        // 5 số, mỗi số thuộc [1, 6]

        // 3. Sinh UUID, biểu diễn thành chuỗi.
        List<String> tokens = Stream.generate(UUID::randomUUID)
                .limit(3)
                .map(UUID::toString)
                .toList();
        System.out.println(tokens);      // Danh sách 3 chuỗi UUID

        // 4. Dãy cần thứ tự xác định: dùng iterate.
        List<Integer> ordered = Stream.iterate(0, n -> n + 1)
                .limit(5)
                .toList();
        System.out.println(ordered);     // [0, 1, 2, 3, 4]
    }
}
```

Trong mã sản xuất, nếu chỉ cần N số liên tiếp, hãy dùng `IntStream.range(0, N)` thay vì supplier có bộ đếm. Nếu cần N giá trị được sinh theo yêu cầu và không có ràng buộc thứ tự, `Stream.generate(...).limit(N)` là lựa chọn dễ đọc.

## 10. Lỗi thường gặp và cách sửa

| Lỗi hoặc suy luận sai | Điều gì có thể xảy ra? | Cách xử lý |
|---|---|---|
| `Stream.generate(...).toList()` không có giới hạn | Chạy mãi, tăng sử dụng bộ nhớ | Đặt `limit` hữu hạn trước terminal operation |
| `sorted().limit(N)` trên nguồn vô hạn | `sorted` không thể chờ hết đầu vào | Đặt `limit(N)` trước `sorted` |
| `distinct().limit(N)` với supplier lặp rất ít giá trị | Không đủ N giá trị khác nhau để dừng | Chặn số mẫu đầu vào hoặc thiết kế điều kiện dừng hữu hạn |
| `filter(...).limit(N)` nhưng predicate luôn false | Pipeline không kết thúc | `limit` trước `filter`, hoặc thay đổi yêu cầu về số mẫu |
| Dùng supplier đếm số rồi dựa vào thứ tự của kết quả song song | `generate` là nguồn unordered | Dùng `iterate`, `IntStream.range` hoặc nguồn ORDERED khác |
| Chia sẻ bộ đếm `int` trong lambda song song | Data race, mất cập nhật | Tránh shared mutable state; kiểm soát đồng bộ khi thực sự cần |
| Cho rằng supplier trả `null` làm stream dừng | `null` tiếp tục là phần tử | Thiết kế cơ chế dừng riêng hoặc dùng nguồn hỗ trợ kết thúc |
| Tái sử dụng đối tượng stream sau `count()` | `IllegalStateException` | Tạo stream mới cho pipeline khác |
| Dùng `parallel()` với tập rất nhỏ rồi mặc định nhanh hơn | Chi phí điều phối có thể lớn hơn lợi ích | Chỉ dùng song song khi đã đo hiệu năng |

## 11. Câu hỏi tự kiểm tra

1. **`Stream.generate(() -> "A").limit(4).count()` trả gì?** Trả `4`, vì `limit` chặn nguồn còn bốn phần tử.
2. **`Stream.generate(() -> 5)` có tự kết thúc sau một phần tử không?** Không. Nó có thể sinh vô hạn phần tử có cùng giá trị `5`.
3. **`Stream.generate(() -> 2).distinct().limit(3).toList()` có hoàn tất không?** Không trong trường hợp thông thường, vì nguồn chỉ tạo một giá trị khác nhau.
4. **`generate` có encounter order vì ban đầu tuần tự không?** Không. Nó là nguồn `unordered`; chế độ chạy tuần tự không tự tạo bảo đảm thứ tự.
5. **`Stream.generate(() -> 1).limit(5).sorted().toList()` có hoàn tất không?** Có; `sorted` chỉ nhận năm phần tử. Đổi thành `sorted().limit(5)` sẽ không thể sắp xếp xong nguồn vô hạn.
6. **Muốn dãy `1, 2, 4, 8` theo thứ tự, nên dùng gì?** `Stream.iterate(1, n -> n * 2).limit(4)`.
7. **Supplier trả `null` có tự kết thúc stream không?** Không. Nếu muốn bỏ null, có thể lọc, nhưng phải bảo đảm pipeline có khả năng kết thúc.
8. **Vì sao không nên dùng biến đếm thông thường trong Supplier khi gọi `parallel()`?** Vì các thread có thể cập nhật cùng trạng thái gây data race và nguồn `generate` vốn không bảo đảm encounter order.

**Ghi nhớ:** `Supplier<T>` trả một giá trị khi `get()` được gọi; `Stream.generate(supplier)` dùng nó làm nguồn lazy, tuần tự ban đầu, unordered và không có điểm kết thúc tự nhiên. Muốn xử lý số lượng hữu hạn, hãy chọn giới hạn và vị trí đặt `limit` có chủ đích. Khi cần một dãy có thứ tự hoặc quy tắc truy hồi xác định, hãy chọn nguồn như `Stream.iterate` hay `IntStream.range` phù hợp với bài toán.
