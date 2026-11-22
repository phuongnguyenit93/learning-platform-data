# Stream.generate và iterate — tạo nguồn Stream theo yêu cầu, hữu hạn hoặc vô hạn

## 1. Vấn đề cần hiểu

Stream API của Java, ra mắt trong Java 8 và **vẫn là công cụ chủ đạo được hỗ trợ trên các JDK hiện đại**, có thể lấy dữ liệu từ collection/array/file hoặc tạo các phần tử **theo nhu cầu** (*on demand*). Hai factory methods đặc biệt quan trọng nằm trong `java.util.stream.Stream`:

- `Stream.generate(Supplier<? extends T> supplier)`: gọi một nhà cung cấp giá trị để tạo các phần tử; trả một **sequential, unordered, conceptually infinite Stream**.
- `Stream.iterate(T seed, UnaryOperator<T> next)`: bắt đầu từ `seed`, sinh phần tử kế bằng cách áp dụng `next` lên phần tử trước; trả một **sequential, ordered, conceptually infinite Stream**.
- `Stream.iterate(T seed, Predicate<? super T> hasNext, UnaryOperator<T> next)`: overload **từ Java 9**, chỉ phát phần tử khi `hasNext` còn đúng; là **sequential, ordered Stream** và có thể kết thúc hữu hạn nếu điều kiện cuối cùng trở thành false.

Hai cách tạo stream đều **lười** (*lazy*): bản thân lời gọi factory không materialize một danh sách vô hạn. Không được nhầm “không tạo tất cả ngay lập tức” với “tự động an toàn”: một terminal operation như `collect(toList())` có thể cố kéo mãi các phần tử, gây treo, tăng CPU hoặc hết bộ nhớ nếu nguồn không có điều kiện dừng.

**Mục tiêu:** Phân biệt quy tắc tạo giá trị, thứ tự (*encounter order*), cách dừng, áp dụng `limit` và các terminal short-circuit, lựa chọn đúng cho dữ liệu có phụ thuộc trạng thái trước đó, xử lý parallel/null/overflow, và tự kiểm thử bằng chương trình Java 17+ có output xác định.

Nội dung chỉ sử dụng **kiến thức Java vẫn còn hiệu lực**, phân biệt rõ phiên bản Java 8 và Java 9+. Không cần sử dụng các API nội bộ, không dựa trên kỹ thuật stream cũ đã lỗi thời.

## 2. Nguồn Stream, pipeline và lazy evaluation

Một pipeline gồm:

~~~text
Stream source
    │
    ├── generate(supplier)
    └── iterate(seed, next) / iterate(seed, hasNext, next)
    │
    ▼
intermediate operations: map / filter / limit / distinct / ...
    │
    ▼
terminal operation: collect / findFirst / anyMatch / reduce / ...
    │
    ▼
result
~~~

`generate` và `iterate` là **source factories**, không phải intermediate operations trên một stream đã tồn tại. Stream chúng tạo ra có thể được xử lý bằng các phép toán tương tự stream từ `List`.

Ví dụ nguồn được tạo từ một hằng số:

~~~java
java.util.List<String> names =
    java.util.stream.Stream.generate(() -> "A")
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
// [A, A, A]
~~~

Cơ chế:

1. `() -> "A"` là `Supplier<String>`: mỗi lần được yêu cầu trả một `"A"`.
2. `Stream.generate` thiết lập một nguồn có khả năng cung cấp các phần tử tiếp tục.
3. `limit(3)` là intermediate short-circuiting: chỉ để tối đa ba phần tử chảy qua.
4. `collect` mới kích hoạt pipeline và xây danh sách.

**Lưu ý bản chất:** Một stream có thể được xem như một mô tả cách duyệt/tạo phần tử, chứ không mặc định là container lưu sẵn toàn bộ phần tử. Một đối tượng stream được **tiêu thụ một lần**; sau terminal phải tạo stream mới nếu muốn chạy phép tính khác.

## 3. `Stream.generate(Supplier)` — mỗi phần tử từ một Supplier

Chữ ký:

~~~java
static <T> Stream<T> generate(Supplier<? extends T> s)
~~~

`Supplier<T>` là functional interface với một phương thức chính `T get()`, không nhận đối số. `Stream.generate` yêu cầu `Supplier` không null; vì không nhận một giá trị trước đó làm tham số, nó phù hợp với nguồn **độc lập giữa các lần tạo giá trị**: cùng hằng số, một nhà sản xuất giá trị, hoặc dữ liệu pseudo-random với các yêu cầu thích hợp.

### 3.1. Tạo giá trị hằng

~~~java
java.util.List<String> events = java.util.stream.Stream
    .generate(() -> "READY")
    .limit(4)
    .collect(java.util.stream.Collectors.toList());
// [READY, READY, READY, READY]
~~~

Đầu vào vẫn **không** phải một collection có bốn phần tử. Hằng `"READY"` chỉ được cung cấp khi pipeline cần một phần tử. Đây là cách viết đơn giản và có kết quả xác định để test.

### 3.2. Tại sao `generate` được định nghĩa là unordered?

Javadoc nói `generate` trả một *infinite sequential unordered stream*. **Unordered** là đặc tính **không có encounter order được API bảo đảm**, không phải “mỗi lần chạy Java sẽ xáo trộn phần tử” và cũng không có nghĩa stream ngay lập tức parallel.

Một `Supplier` trả các phần tử giống nhau vẫn làm kết quả nhìn thấy có thứ tự đồng nhất, nhưng đó không phải chứng cứ về encounter order. Nếu bạn viết Supplier tăng một counter để gán sequence number, rồi dựa vào `limit` hoặc `findFirst` ở parallel pipeline để chọn “đúng n số đầu”, đó là thiết kế dễ sai.

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger();

java.util.stream.Stream<Integer> sequence =
    java.util.stream.Stream.generate(counter::incrementAndGet);
~~~

Đoạn này **hợp lệ về cú pháp** và có thể minh họa supplier có state, nhưng **không được khuyến khích** để mô tả dãy số có thứ tự trong production. Khi pipeline parallel, các lần gọi có thể xảy ra từ nhiều luồng; kết quả và thời điểm Supplier được gọi không tạo hợp đồng encounter order. Nếu nghiệp vụ thực sự cần dãy số theo bước trước, dùng `iterate` (hoặc range stream cho khoảng hữu hạn) thay vì phụ thuộc counter dùng chung.

### 3.3. Random data với `generate`

~~~java
java.util.Random random = new java.util.Random(123);

java.util.List<Integer> samples =
    java.util.stream.Stream.generate(() -> random.nextInt(100))
        .limit(5)
        .collect(java.util.stream.Collectors.toList());
~~~

Đây là **mảnh code minh họa** cho việc gọi API; không ấn định stdout vì mục đích là cơ chế nguồn, không phải cam kết chuỗi giá trị cho mọi thiết kế/concurrency. `Random` là nguồn trạng thái, nên khi cần parallel/splitting đúng cách hoặc xử lý khối lượng lớn, hãy cân nhắc các API primitive stream chuyên dụng như `Random.ints(...)` và chiến lược random generator phù hợp runtime đang hỗ trợ.

**Bảo mật:** `Random` và các generator giả ngẫu nhiên thông thường không được dùng làm secret/session token. Với dữ liệu đòi hỏi ngẫu nhiên mật mã, dùng API có thiết kế bảo mật như `SecureRandom`, đồng thời hiểu yêu cầu throughput và cách tạo lượng hữu hạn. Stream factory không làm một Supplier trở nên cryptographically secure.

### 3.4. Supplier có thể trả null?

Một stream đối tượng có thể chứa tham chiếu `null` trong những tình huống hợp lệ của Java; kiểu `T` trong generics **không tự đặt hợp đồng non-null**. Nếu Supplier có thể trả null, các thao tác phía sau có thể ném exception:

~~~java
// Fragment để phân tích; không phải mẫu nên dùng:
// Stream.generate(() -> (String) null)
//       .limit(1)
//       .map(String::length)
//       .collect(Collectors.toList()); // Có thể NPE khi map.
~~~

Đặc biệt, những terminal operations trả `Optional` như `findFirst`/`findAny` không thể tạo một `Optional` chứa null; việc chọn null có thể dẫn đến `NullPointerException`. Nếu dữ liệu thật có thể thiếu, hãy dùng mô hình `Optional`/giá trị hợp lệ hoặc lọc `Objects::nonNull` theo hợp đồng của ứng dụng, không lặng lẽ đẩy null qua mọi operation.

## 4. `Stream.iterate(seed, next)` — phần tử tiếp theo phụ thuộc phần tử trước

Chữ ký có từ Java 8:

~~~java
static <T> Stream<T> iterate(T seed, UnaryOperator<T> f)
~~~

Nguồn lần lượt sinh:

~~~text
seed
f(seed)
f(f(seed))
f(f(f(seed)))
...
~~~

Khác với `generate`, `iterate` có **seed** và quy tắc **chuyển trạng thái từ giá trị trước sang giá trị sau**. Kết quả là một **ordered sequential stream**, nên có encounter order xác định bởi thứ tự kế tiếp của các phần tử.

### 4.1. Dãy số tự nhiên

~~~java
java.util.List<Integer> numbers =
    java.util.stream.Stream.iterate(0, n -> n + 1)
        .limit(6)
        .collect(java.util.stream.Collectors.toList());
// [0, 1, 2, 3, 4, 5]
~~~

- `seed = 0`: phần tử **đầu tiên** là 0, không phải 1.
- `next = n -> n + 1`: tạo phần tử tiếp theo.
- `limit(6)`: chỉ lấy sáu phần tử để kết thúc pipeline.
- Không có `limit`, factory này về mặt mô hình **tiếp tục sinh** phần tử, chứ không tự dừng vì vượt một giá trị nào đó.

### 4.2. Lũy thừa của hai

~~~java
java.util.List<Integer> powers =
    java.util.stream.Stream.iterate(1, n -> n * 2)
        .limit(5)
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 4, 8, 16]
~~~

`iterate` diễn đạt đúng quy tắc “giá trị tiếp theo phụ thuộc vào giá trị hiện tại”; không cần mutable counter ngoài pipeline. Nhưng với `int`, dãy có thể **overflow** nếu tiếp tục đủ lâu. Việc overflow trong số nguyên Java là hành vi được định nghĩa, không tự ném exception. Muốn giữ giới hạn số học, dùng predicate có biên, kiểm số trước khi cập nhật, hoặc cấu trúc dữ liệu khác như `BigInteger` tùy bài toán.

### 4.3. Dãy ký tự và trạng thái bất biến

~~~java
java.util.List<String> steps =
    java.util.stream.Stream.iterate("A", s -> s + "A")
        .limit(4)
        .collect(java.util.stream.Collectors.toList());
// [A, AA, AAA, AAAA]
~~~

`String` bất biến nên mỗi bước tạo giá trị mới; logic không cần sửa một danh sách bên ngoài. Tuy nhiên, các thao tác nối chuỗi liên tiếp có thể tốn thời gian/bộ nhớ khi dãy lớn. Dùng toán học hoặc mô hình dữ liệu phù hợp thay vì tạo chuỗi kích thước tăng vô hạn.

**Đặc tính ordered:** `iterate` có thứ tự tự nhiên của chuỗi; nhưng nếu bạn cố tình thêm `unordered()` ở sau hoặc dùng terminal không tôn trọng encounter order, ví dụ `findAny()` trong parallel, một phần ordering guarantees ở pipeline cuối có thể thay đổi theo API.

## 5. `Stream.iterate(seed, hasNext, next)` — overload Java 9+

Từ **Java 9**, Java bổ sung overload có điều kiện:

~~~java
static <T> Stream<T> iterate(
    T seed,
    Predicate<? super T> hasNext,
    UnaryOperator<T> next
)
~~~

Cách hoạt động giống một vòng `for`:

~~~java
for (T value = seed;
     hasNext.test(value);
     value = next.apply(value)) {
    // sử dụng value
}
~~~

**Quy tắc quan trọng:**

1. `hasNext` được kiểm với **seed trước khi seed được phát**. Nếu false ngay, stream rỗng.
2. Khi true, giá trị hiện tại được phát ra, sau đó có thể áp dụng `next` để chuẩn bị ứng viên kế tiếp khi traversal yêu cầu.
3. Nếu `hasNext` false cho ứng viên, ứng viên đó **không** thuộc stream.
4. Điều kiện chỉ bảo đảm stream hữu hạn khi trên dãy thực tế, **cuối cùng nó trở thành false**. Viết predicate luôn true vẫn tạo stream có khả năng vô hạn.

### 5.1. Dãy hữu hạn có ranh giới

~~~java
java.util.List<Integer> values =
    java.util.stream.Stream.iterate(1, n -> n <= 10, n -> n + 3)
        .collect(java.util.stream.Collectors.toList());
// [1, 4, 7, 10]
~~~

Diễn giải:

~~~text
current=1   hasNext? true   -> emit 1    -> next=4
current=4   hasNext? true   -> emit 4    -> next=7
current=7   hasNext? true   -> emit 7    -> next=10
current=10  hasNext? true   -> emit 10   -> next=13
current=13  hasNext? false  -> STOP (13 không được emit)
~~~

Không cần `limit` vì predicate có điểm dừng rõ và không overflow trong phạm vi này.

### 5.2. Seed không thỏa điều kiện

~~~java
java.util.List<Integer> empty =
    java.util.stream.Stream.iterate(11, n -> n <= 10, n -> n + 3)
        .collect(java.util.stream.Collectors.toList());
// []
~~~

Vì `hasNext.test(11) == false`, stream rỗng. Đừng vô tình cho rằng `seed` **luôn** là phần tử đầu tiên của overload ba tham số: điều đó đúng với overload hai tham số nhưng không đúng khi predicate đầu tiên false.

### 5.3. “Cho đến khi” khác “bao gồm giá trị dừng”

~~~java
java.util.List<Integer> belowFive =
    java.util.stream.Stream.iterate(0, n -> n < 5, n -> n + 2)
        .collect(java.util.stream.Collectors.toList());
// [0, 2, 4]
~~~

Giá trị 6 không xuất hiện vì kiểm predicate trước khi phát. Đây là dạng duyệt với **end-exclusive condition**, tương tự vòng `for (int i = 0; i < 5; i += 2)`.

Đừng nhầm `iterate(seed, hasNext, next)` với `Stream.iterate(seed, next).filter(hasNext)`: `filter` chỉ bỏ các phần tử không thỏa, **không khiến nguồn tự dừng**. Với một nguồn vô hạn, collect sau filter vẫn có thể không kết thúc.

### 5.4. Có thể dùng `BigInteger` khi tránh integer overflow

~~~java
java.math.BigInteger maximum = new java.math.BigInteger("1000");

java.util.List<java.math.BigInteger> values =
    java.util.stream.Stream.iterate(
        java.math.BigInteger.ONE,
        n -> n.compareTo(maximum) <= 0,
        n -> n.multiply(java.math.BigInteger.valueOf(2)))
    .collect(java.util.stream.Collectors.toList());
// [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
~~~

`BigInteger` tăng độ an toàn số học cho dãy lớn hơn phạm vi kiểu primitive, dù vẫn phải giới hạn số bước và bộ nhớ. Ví dụ kết thúc khi giá trị tiếp theo vượt 1000.

**Tương thích phiên bản:** Code overload ba đối số **không biên dịch với `--release 8`**. Nếu muốn hỗ trợ môi trường Java 8 về mặt source/binary, dùng bản hai đối số kết hợp `limit` khi số bước biết trước, hoặc một thiết kế source phù hợp; đừng gán nhãn API này là tính năng Java 8.

## 6. So sánh ngắn gọn: chọn nguồn nào?

| Tiêu chí | `generate(supplier)` | `iterate(seed, next)` | `iterate(seed, hasNext, next)` |
| --- | --- | --- | --- |
| Xuất hiện từ Java | 8 | 8 | **9** |
| Đầu vào chính | `Supplier<T>` | `seed` + `UnaryOperator<T>` | `seed` + `Predicate<T>` + `UnaryOperator<T>` |
| Quy tắc tạo giá trị | Gọi `get()` khi cần | Từ phần tử trước tính phần tử tiếp | Như iterate nhưng kiểm điều kiện trước khi phát |
| Encounter order của source | **Unordered** | **Ordered** | **Ordered** |
| Execution mode ban đầu | Sequential | Sequential | Sequential |
| Độ dài mặc định | Có khả năng vô hạn | Có khả năng vô hạn | Có thể hữu hạn nếu predicate dừng |
| Khi cần giới hạn | `limit(n)` hoặc terminal có điều kiện | `limit(n)` hoặc terminal có điều kiện | Predicate dừng, hoặc thêm `limit(n)` bảo vệ |
| Dùng tốt cho | Giá trị độc lập, hằng, supplier dữ liệu | Dãy truy hồi theo bước trước | Dãy truy hồi có điều kiện kết thúc |
| Rủi ro thường gặp | Shared-state Supplier, unordered parallel | Overflow, truy hồi mãi | Predicate không dừng, overflow, predicate/next có side effects |

**Cần nhấn mạnh:** Cả ba factories đều trả **sequential stream ban đầu**, nhưng điều đó không có nghĩa phép xử lý sẽ không bao giờ chạy parallel: một pipeline sau đó có thể gọi `parallel()`. Trong ứng dụng đòi output có thể dự đoán, hãy chủ động thiết kế encounter order, độ dài và đặc tính purity của behavioral parameters.

## 7. Cắt nguồn vô hạn: `limit` và terminal short-circuit

### 7.1. Cắt số lượng bằng `limit(n)`

~~~java
java.util.List<Integer> firstFour =
    java.util.stream.Stream.iterate(100, n -> n + 10)
        .limit(4)
        .collect(java.util.stream.Collectors.toList());
// [100, 110, 120, 130]
~~~

`limit(maxSize)` là intermediate operation **stateful + short-circuiting**, chỉ cho tối đa số phần tử đã chỉ định. `limit(0)` trả stream rỗng, `limit(-1)` ném `IllegalArgumentException`. Với nguồn hữu hạn có ít hơn `n` phần tử, kết quả chỉ chứa số phần tử thực có. `limit` không khiến mọi nguồn trước đó có thể dừng: một stage như `sorted()` đặt **trước limit** trên nguồn không giới hạn có thể cần hết toàn bộ dữ liệu trước khi phát một phần tử.

### 7.2. Terminal short-circuit

~~~java
boolean hasTen =
    java.util.stream.Stream.iterate(0, n -> n + 1)
        .anyMatch(n -> n == 10);
// true
~~~

`anyMatch` có khả năng dừng sau khi gặp phần tử 10. Nhưng nếu điều kiện **không bao giờ** thỏa trên nguồn vô hạn, như `n < 0` với một dãy không âm được sinh theo cách không overflow ở phạm vi thực tế, terminal vẫn có thể không kết thúc. Vì vậy “có anyMatch” chỉ có nghĩa **có thể** dừng, không phải một cam kết luôn hữu hạn.

~~~java
java.util.Optional<String> first =
    java.util.stream.Stream.generate(() -> "ready")
        .findAny();
// Optional[ready]
~~~

`findAny` là terminal có thể ngừng khi có một phần tử; vì generate là unordered, **không** có lời hứa “phần tử đầu tiên theo sequence nghiệp vụ” khi các lần gọi Supplier tạo các giá trị khác nhau.

### 7.3. Thứ tự stage quyết định có kết thúc không

~~~java
// Có thể hoàn tất, vì lấy năm giá trị trước rồi sắp xếp:
java.util.List<Integer> ok =
    java.util.stream.Stream.iterate(0, n -> n + 1)
        .limit(5)
        .sorted(java.util.Comparator.reverseOrder())
        .collect(java.util.stream.Collectors.toList());
// [4, 3, 2, 1, 0]
~~~

~~~java
// KHÔNG CHẠY với nguồn vô hạn:
// Stream.iterate(0, n -> n + 1)
//     .sorted()
//     .limit(5)
//     .collect(Collectors.toList());
~~~

Trong ví dụ thứ hai, `sorted()` phải có đủ nguồn để sắp xếp toàn bộ, không thể hoàn tất trên một dãy không giới hạn. `limit(5)` đứng ở sau không thể cứu được stage đã bị chặn.

### 7.4. Stream vô hạn + `count`

~~~java
// KHÔNG CHẠY:
// Stream.generate(() -> 1).count();
// Stream.iterate(0, n -> n + 1).collect(Collectors.toList());
~~~

`count()` hay `collect(toList())` trên nguồn không giới hạn mà không có thao tác bảo đảm hữu hạn có thể tiêu thụ vô hạn thời gian/tài nguyên. `Stream.generate` hoặc `iterate` **không tự cấp cơ chế timeout hoặc cancellation**. Nếu chạy trong hệ thống server, áp dụng giới hạn số lượng/thời gian ở lớp điều phối thích hợp và kiểm cancellation/resource cleanup.

## 8. Nguồn `generate` không giống vòng lặp stateful được đồng bộ

Một `Supplier` có side effect dễ khiến người học lầm tưởng stream luôn gọi chính xác theo thứ tự:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger(1);

java.util.List<Integer> sample =
    java.util.stream.Stream.generate(counter::getAndIncrement)
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
~~~

Với traversal **tuần tự** như snippet, kết quả thường là `[1, 2, 3]`. Nhưng đây chỉ là **minh họa để thấy Supplier được gọi theo nhu cầu**, không nên chọn cách này làm contract nghiệp vụ trong pipeline parallel. `AtomicInteger` đảm bảo atomicity của counter, **không** tự tạo encounter order cho `generate` hoặc bảo đảm số lần Supplier được gọi trong mọi pipeline.

Để tạo 1,2,3 với thứ tự rõ ràng:

~~~java
java.util.List<Integer> safer =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 3]
~~~

Với dãy số hữu hạn thông thường, **`IntStream.range(1, 4)` còn phù hợp hơn**:

~~~java
java.util.List<Integer> range =
    java.util.stream.IntStream.range(1, 4)
        .boxed()
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 3]
~~~

`range` truyền trực tiếp semantics khoảng start-inclusive/end-exclusive, tránh boxing khi không cần object stream và phù hợp splitting/parallel processing hơn việc dùng `iterate` để giả lập một for-loop đơn giản.

### Có nên dùng mutable state trong `next`?

~~~java
// Đừng triển khai dãy phụ thuộc state từ biến mutable bên ngoài:
// int[] shared = {0};
// Stream.iterate(0, previous -> ++shared[0]);
~~~

`iterate` đã cung cấp giá trị previous, vì vậy hãy diễn đạt phép chuyển trạng thái bằng **đầu vào của lambda**:

~~~java
java.util.stream.Stream.iterate(0, previous -> previous + 1)
~~~

Nếu trạng thái gồm nhiều trường, dùng một object immutable (record ở Java mới, class immutable ở Java 8+) làm seed/next; tránh mutate seed được share ở nhiều nơi.

## 9. Primitive streams: `IntStream.iterate` và `IntStream.generate`

Khi xử lý số lượng lớn số primitive, `Stream<Integer>` tạo object wrapper trong nhiều trường hợp. Java còn cung cấp:

- `IntStream.generate(IntSupplier)`;
- `IntStream.iterate(int seed, IntUnaryOperator next)`;
- `IntStream.iterate(int seed, IntPredicate hasNext, IntUnaryOperator next)` từ Java 9+;
- Các phiên bản tương tự của `LongStream` và `DoubleStream`.

~~~java
int sum =
    java.util.stream.IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .sum();
// 15
~~~

~~~java
// Java 9+ (cùng kết quả, không cần limit):
int sum =
    java.util.stream.IntStream.iterate(1, n -> n <= 5, n -> n + 1)
        .sum();
// 15
~~~

Các snippet trên độc lập với nhau, **không** đặt cả hai khai báo `int sum` cùng scope. Chọn primitive streams khi cần giảm boxing/unboxing và có các terminal như `sum`, `average`, `summaryStatistics`; không có nghĩa primitive stream tự an toàn trước overflow. Với `int sum` vượt `Integer.MAX_VALUE`, vẫn phải có thiết kế số học phù hợp.

`IntStream.range` hoặc `rangeClosed` thường rõ và hiệu quả hơn `iterate` cho **khoảng số nguyên hữu hạn đều bước 1**:

~~~java
int sum = java.util.stream.IntStream.rangeClosed(1, 5).sum();
// 15
~~~

Đừng ép mọi dãy sang generate/iterate nếu một factory đơn giản hơn thể hiện đúng contract.

## 10. Ví dụ Java 17+ hoàn chỉnh: cả generate và hai dạng iterate

Tạo file **`StreamFactoriesDemo.java`** UTF-8. Dùng JDK 17 trở lên đang được dự án hỗ trợ; không cần dependency ngoài. Chương trình có một phần minh họa side effect bằng `AtomicInteger` **chỉ để quan sát lazy evaluation trong pipeline tuần tự**, không gợi ý dùng counter làm trạng thái nghiệp vụ.

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public final class StreamFactoriesDemo {
    public static void main(String[] args) {
        List<String> repeated = Stream.generate(() -> "ping")
            .limit(3)
            .collect(Collectors.toList());
        System.out.println("generate: " + repeated);

        List<Integer> doubled = Stream.iterate(1, n -> n * 2)
            .limit(5)
            .collect(Collectors.toList());
        System.out.println("iterate-two: " + doubled);

        List<Integer> bounded =
            Stream.iterate(1, n -> n <= 10, n -> n + 3)
                .collect(Collectors.toList());
        System.out.println("iterate-three: " + bounded);

        List<Integer> empty =
            Stream.iterate(11, n -> n <= 10, n -> n + 3)
                .collect(Collectors.toList());
        System.out.println("empty-seed: " + empty);

        AtomicInteger calls = new AtomicInteger();
        Stream<Integer> lazy = Stream.generate(() -> {
            calls.incrementAndGet();
            return 7;
        });
        System.out.println("before: " + calls.get());

        List<Integer> values = lazy.limit(2)
            .collect(Collectors.toList());
        System.out.println("values: " + values);
        System.out.println("after: " + calls.get());

        int sum = IntStream.iterate(1, n -> n <= 5, n -> n + 1)
            .sum();
        System.out.println("primitive-sum: " + sum);

        boolean found = Stream.iterate(0, n -> n + 1)
            .anyMatch(n -> n == 4);
        System.out.println("anyMatch: " + found);
    }
}
~~~

Biên dịch và chạy:

~~~text
javac --release 17 -encoding UTF-8 StreamFactoriesDemo.java
java StreamFactoriesDemo
~~~

**Stdout chính xác — 9 dòng:**

~~~text
generate: [ping, ping, ping]
iterate-two: [1, 2, 4, 8, 16]
iterate-three: [1, 4, 7, 10]
empty-seed: []
before: 0
values: [7, 7]
after: 2
primitive-sum: 15
anyMatch: true
~~~

Giải thích:

1. `generate` được cắt bằng `limit(3)` nên tạo danh sách ba chuỗi `"ping"`.
2. `iterate(seed, next)` bao gồm seed 1 rồi nhân đôi liên tiếp, `limit(5)` giữ năm số.
3. Overload ba tham số kiểm `n <= 10` trước mỗi lần phát nên dãy gồm 1,4,7,10, không chứa 13.
4. Seed 11 không thỏa điều kiện nên stream rỗng.
5. Trước terminal, chưa cần gọi supplier, `calls` vẫn 0; sau `collect` trên nguồn `generate` tuần tự với hai giá trị 7, supplier được gọi hai lần trong pipeline cụ thể.
6. `IntStream.iterate` hữu hạn bằng predicate cho tổng 1+2+3+4+5 = 15.
7. `anyMatch` tìm thấy 4 trên ordered iterate, có thể kết thúc mà không tiêu thụ nguồn vô hạn.

### Chạy được trên Java 8 như thế nào?

Mẫu chính dùng API overload **ba tham số từ Java 9**, nên không tương thích `javac --release 8` nếu giữ nguyên. Nếu cần một ví dụ Java 8 độc lập, tạo file riêng:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class StreamJava8Demo {
    public static void main(String[] args) {
        List<Integer> numbers = Stream.iterate(1, n -> n + 3)
            .limit(4)
            .collect(Collectors.toList());

        List<String> labels = Stream.generate(() -> "ready")
            .limit(2)
            .collect(Collectors.toList());

        System.out.println(numbers);
        System.out.println(labels);
    }
}
~~~

~~~text
javac --release 8 -encoding UTF-8 StreamJava8Demo.java
java StreamJava8Demo
~~~

Output:

~~~text
[1, 4, 7, 10]
[ready, ready]
~~~

**So sánh quan trọng:** `limit(4)` nói “lấy bốn phần tử”, còn predicate `n <= 10` nói “tiếp tục trong khi giá trị thỏa điều kiện”. Hai cách cho cùng output trong ví dụ nhỏ nhưng **không đồng nghĩa cho mọi dữ liệu**. Chọn theo yêu cầu thực, đừng thay predicate bằng một giới hạn giả định nếu số bước không biết trước.

## 11. Source ordering, parallel execution và những bảo đảm không nên suy luận

### 11.1. Sequential ban đầu không có nghĩa ordered

`generate` được mô tả là **sequential unordered**; `iterate` là **sequential ordered**. Hai tính từ mô tả **hai trục khác nhau**:

- *Sequential/parallel* nói về execution mode và cách pipeline có thể xử lý.
- *Ordered/unordered* nói về encounter order mà pipeline có nghĩa vụ giữ.

Một stream unordered vẫn có thể được duyệt tuần tự. Một stream ordered có thể được xử lý parallel; khi đó một số terminal như `forEach` không bảo đảm thứ tự action, còn `forEachOrdered` tôn trọng order nếu stream có encounter order.

### 11.2. `parallel()` không làm Supplier thành thread-safe

~~~java
// Không dùng để sinh dãy tăng có thứ tự trong production:
// AtomicInteger counter = new AtomicInteger();
// Stream.generate(counter::incrementAndGet)
//       .parallel()
//       .limit(10)
//       .collect(Collectors.toList());
~~~

`AtomicInteger` bảo vệ phép tăng, nhưng thứ tự giá trị nào được giữ khi pipeline parallel/unordered và số lần Supplier được gọi không nên dùng làm API contract. Nếu cần một range có thứ tự, `IntStream.range` thường phù hợp; nếu cần một chuỗi phụ thuộc phần tử trước, `iterate` thể hiện nghĩa đúng nhưng **không tự cam kết parallel sẽ nhanh**.

### 11.3. `iterate` có dependency chain

Trong `iterate(seed, next)`, phần tử `n+1` phụ thuộc phần tử `n`, nên không thể tùy tiện tính phần tử xa bất kỳ mà không xét phép chuyển trạng thái. Điều này có thể hạn chế parallel splitting. Javadoc quy định các quan hệ *happens-before* liên quan giữa lần áp dụng function/predicate cho các bước liên tiếp; việc thực hiện có thể ở thread khác. Vì vậy, **không** dựa vào stateful side effects trong `next` để đồng bộ nghiệp vụ.

Bộ dữ liệu hữu hạn dạng khoảng số nguyên thường có factory tốt hơn cho parallelization, như `IntStream.range`, `LongStream.range` hoặc một `Spliterator` được thiết kế rõ đặc tính, thay vì ép `iterate` làm mọi việc.

### 11.4. `findFirst`, `findAny` và nguồn generate

Với source iterate có encounter order, `findFirst` trả phần tử đầu nếu có; với source generate **unordered**, “first theo sequence nghiệp vụ” không có nghĩa được API xác nhận. `findAny` có thể lấy bất kỳ phần tử nào và hữu ích cho parallel processing khi nghiệp vụ không cần order.

Không viết unit test mà kỳ vọng một stream generated bằng shared mutable supplier luôn trả số 1 ở `findFirst` hoặc `findAny` trong mọi execution mode. Hãy test bằng supplier **pure/deterministic** hoặc yêu cầu dữ liệu riêng khi cần tính đúng.

## 12. Dừng stream, cancellation và tài nguyên ngoài

### 12.1. Vì sao “infinite” chỉ có nghĩa nguồn không có điểm dừng tự nhiên?

`Stream.generate` và `Stream.iterate(seed,next)` được mô tả là *infinite* ở mức mô hình: có thể tiếp tục yêu cầu phần tử. Tuy nhiên, quá trình thực có thể dừng vì:

- Short-circuiting operation;
- Exception do Supplier/UnaryOperator;
- Thread cancellation/quy tắc hệ thống;
- Resource exhaustion;
- Process termination.

Các tình huống lỗi **không biến source thành finite stream có hợp đồng kết thúc**. Nếu đưa vào server, không dùng “mong exception tự ngắt” thay cho thiết kế giới hạn rõ ràng.

### 12.2. `limit` giới hạn số phần tử nhưng không phải timeout

~~~java
java.util.List<String> result = java.util.stream.Stream
    .generate(() -> slowExternalCall())
    .limit(10)
    .collect(java.util.stream.Collectors.toList());
~~~

Đây là **fragment minh họa**, không phải runnable độc lập vì `slowExternalCall()` chưa được định nghĩa. `limit(10)` không bảo đảm thời gian thực thi: nếu Supplier bị treo ở lần đầu hoặc chậm, pipeline vẫn có thể chờ rất lâu.

Khi Supplier đọc tài nguyên ngoài như file, network hoặc database, nên ưu tiên API streaming có khả năng quản lý lifecycle và cancellation rõ; nếu tự tạo nguồn, phải đóng tài nguyên trong `try-with-resources`/`onClose` hoặc logic lifecycle phù hợp. **Không mặc định** short-circuit hoặc terminal tự đóng mọi resource bên ngoài. `Stream.onClose` chỉ đăng ký close handler; ứng dụng vẫn phải thực sự gọi `close()` khi cần.

### 12.3. Tránh materialize dữ liệu vô hạn

~~~java
// KHÔNG CHẠY:
java.util.stream.Stream.generate(() -> "X")
    .collect(java.util.stream.Collectors.toList());
~~~

Không có giới hạn output. Dù mỗi chuỗi chỉ một ký tự, list không thể là hữu hạn theo contract, có nguy cơ tràn bộ nhớ. Nếu mục đích thực là ghi từng dòng một cách liên tục, cần một hệ xử lý có backpressure/cancellation/lifecycle thay vì collect vào `List` không giới hạn.

### 12.4. Overflow trong condition

~~~java
// Sai nếu muốn chắc chắn dừng tại giá trị cực lớn:
// Stream.iterate(1, n -> n > 0, n -> n * 2)
~~~

Với `Integer`, tăng gấp đôi cuối cùng có thể overflow thành số âm/0 rồi predicate có thể dừng, nhưng đó **không phải** giới hạn số học bạn muốn dùng làm contract. Ngược lại, nhiều hàm next có thể quay vòng trạng thái khiến predicate **không bao giờ false**. Hãy phân tích mối quan hệ giữa state, transition và termination bằng input lớn nhất/biên.

### 12.5. Null từ seed/next

`iterate` sử dụng kiểu tham chiếu `T` và có thể gặp null nếu seed/next trả null; đó không phải giá trị báo “kết thúc” được phương thức hai đối số tự diễn giải. Overload có predicate có thể dùng logic dừng tương ứng, nhưng vẫn phải quản lý việc đánh giá null và exception hợp lệ.

Nếu dữ liệu có sentinel hoặc giá trị nullable, hãy viết một state holder/`Optional` contract rõ ràng hoặc dùng iterator/spliterator thích hợp, thay vì mong `Stream.iterate` dừng khi next trả null. Một terminal như `findFirst` trên null có thể ném `NullPointerException`, nên việc nhận null phải là quyết định có test.

## 13. Lựa chọn giải pháp theo nhu cầu thật

| Nhu cầu | Nguồn gợi ý | Lý do |
| --- | --- | --- |
| Lặp một hằng số hữu hạn N lần | `Stream.generate(() -> constant).limit(N)` | Ngắn, đúng, dễ test |
| Dãy phụ thuộc phần tử trước | `Stream.iterate(seed, next)` với giới hạn | Mô hình đệ quy theo bước rõ |
| Dãy có điều kiện dừng theo giá trị | `Stream.iterate(seed, hasNext, next)` Java 9+ | Predicate thể hiện biên dừng |
| Khoảng `int` hữu hạn | `IntStream.range`/`rangeClosed` | Không cần boxing, semantics khoảng rõ |
| Dãy số random hữu hạn | Các factory `Random.ints(...)`/random generator được hỗ trợ | Đã có API số phần tử và phân phối |
| Dữ liệu trong `List` | `list.stream()` | Giữ semantics collection/order |
| Dữ liệu từ file | `Files.lines` với `try-with-resources` | Quản lý nguồn I/O rõ |
| Truy hồi state phức hợp | `iterate` với state immutable nếu phù hợp | Tránh mutable shared state, dễ kiểm termination |
| Phần tử từ network liên tục | API reactive/streaming có backpressure và lifecycle phù hợp | Stream factory không tự mang backpressure/cancellation |
| Chỉ cần một phần tử thỏa điều kiện | `anyMatch`/`findFirst` trên nguồn được kiểm soát | Short-circuit nếu điều kiện thỏa; có thể vẫn cần giới hạn bảo vệ |

Không nên xây một abstraction phức tạp chỉ để thay thế vòng lặp đơn giản. `for`/`while` vẫn là lựa chọn rõ ràng khi logic cần mutation/early break/resource control đặc thù, hoặc khi phụ thuộc chi tiết thứ tự side effects mà Stream API không cam kết.

## 14. Những sai lầm thường gặp

### 14.1. “`generate` tự có thứ tự giống `iterate`”

**Sai.** `generate` được công bố là **unordered**, `iterate` được công bố là **ordered**. Kết quả đầu vào của Supplier có thể trông như dãy theo thứ tự ở chế độ tuần tự, nhưng **không lấy điều đó làm hợp đồng encounter order**.

### 14.2. “`generate` và `iterate` đều sinh tất cả ngay lúc gọi”

**Sai.** Các factories tạo mô tả nguồn lazy. Tuy nhiên một terminal không có điểm dừng có thể cố kéo toàn bộ nguồn vô hạn sau đó.

### 14.3. “Có `limit` ở đâu trong pipeline thì luôn an toàn”

**Sai.** Một stateful stage như `sorted` đặt trước `limit` vẫn có thể cần toàn bộ nguồn. Cần phân tích đúng **thứ tự operations**.

### 14.4. “`filter(n -> n <= 10)` tương đương iterate có hasNext”

**Sai.** `filter` không yêu cầu dừng nguồn khi điều kiện trở thành false; nó chỉ bỏ phần tử không phù hợp. `iterate(seed, hasNext, next)` **ngừng nguồn** ngay khi predicate false đối với ứng viên tiếp theo. Với stream vô hạn không có phần tử thoát filter, collect sau đó có thể chạy mãi.

### 14.5. “Seed luôn được phát ra”

Overload hai đối số sẽ bắt đầu từ seed; overload **ba đối số** có thể rỗng nếu `hasNext(seed) == false`. Dùng test empty-seed.

### 14.6. “Java 8 có overload ba tham số”

**Sai.** `Stream.iterate(seed, hasNext, next)` có **từ Java 9**. Mã nhắm `--release 8` phải dùng bản hai tham số hoặc thiết kế khác; để học API mới, compile với `--release 17` hoặc release được dự án hỗ trợ.

### 14.7. “Stream.generate(counter::incrementAndGet) tương đương dãy iterate”

Counter là mutable state bên ngoài Supplier; `generate` không có encounter order. `iterate` phụ thuộc phần tử trước và tạo ordered source. Parallel hóa counter không tự bảo đảm sequence semantics.

### 14.8. “`count()` luôn gọi Supplier chính xác n lần”

`count` là terminal, nhưng optimizer có thể bỏ một số stage khi kết quả có thể biết từ source metadata; không dùng số lần side effect trong `peek`/mapper làm contract chung. Với nguồn generate không giới hạn và không cắt, `count` không thể có một giá trị hữu hạn đúng, đừng chạy nó.

### 14.9. “Parallel luôn tăng tốc trên iterate”

Không chắc. `iterate` có dependency giữa các phần tử, nên splitting/parallel execution có thể kém hiệu quả; luôn benchmark workload thật và kiểm ràng buộc thứ tự.

### 14.10. “Supplier trả null tức là kết thúc”

Không có quy tắc đó. `null` là một giá trị tham chiếu có thể gây lỗi downstream, không phải termination signal mặc định của `Stream.generate` hoặc `Stream.iterate(seed,next)`.

### 14.11. “Cứ dùng `collect(toList())` trên nguồn không giới hạn”

Có thể dẫn đến không kết thúc và hết bộ nhớ. Cần tính toán **giới hạn output và vòng đời** trước khi materialize.

### 14.12. “Cứ mở stream xong mặc nhiên được đóng khi short-circuit”

Không đúng với nguồn có resource ngoài. Dùng try-with-resources khi API/nguồn yêu cầu đóng, và kiểm close/cancellation trong test.

## 15. Kiểm thử: điều gì phải có bằng chứng?

Bộ test nên xác nhận **kết quả** và **điều kiện dừng** mà không dựa vào thread scheduler hay side effects không được bảo đảm.

| Test case | Expression | Kỳ vọng |
| --- | --- | --- |
| Generate hằng | `generate(() -> "X").limit(3)` | `[X, X, X]` |
| Iterate tuần tự | `iterate(1, n -> n*2).limit(4)` | `[1, 2, 4, 8]` |
| Iterate bounded | `iterate(1, n -> n <= 10, n -> n+3)` | `[1, 4, 7, 10]` |
| Seed không hợp lệ | `iterate(11, n -> n <= 10, n -> n+3)` | `[]` |
| Giới hạn zero | `generate(() -> "X").limit(0)` | Empty result |
| Giới hạn âm | `generate(() -> "X").limit(-1)` | `IllegalArgumentException` |
| Find trên generate hằng | `generate(() -> "X").findAny()` | Một kết quả `"X"` |
| Any match hữu hạn | `iterate(0,n -> n+1).anyMatch(n -> n==4)` | true |
| Phiên bản Java | Compile bounded iterate với `--release 8` | Không hỗ trợ method 3 đối số |
| No duplicate consumption | Gọi terminal hai lần trên cùng stream | Không hợp lệ; thường `IllegalStateException` |
| Primitive iterate | `IntStream.iterate(1,n -> n <= 5,n -> n+1).sum()` | 15 |
| Stateful supplier in parallel | Sinh với counter và kỳ vọng thứ tự | **Không** đặt expectation sequence không được contract bảo đảm |

**Test cho trường hợp vô hạn:** Không đưa pipeline không có termination vào CI rồi chờ nó tự thoát. Viết test cho pipeline đã có `limit` hoặc điều kiện dừng, dùng timeout trong test harness cho những tình huống có thể treo để bảo vệ runner, và **không** coi timeout là một cách tạo kết quả đúng.

### Ví dụ JUnit-oriented test (fragment)

~~~java
// Trong một @Test method khi dự án đã cấu hình JUnit:
java.util.List<Integer> actual =
    java.util.stream.Stream.iterate(2, n -> n * 2)
        .limit(4)
        .collect(java.util.stream.Collectors.toList());

org.junit.jupiter.api.Assertions.assertEquals(
    java.util.Arrays.asList(2, 4, 8, 16), actual);
~~~

Đây **không phải chương trình Java standalone**, và JUnit là dependency của hệ thống test, không có sẵn trong Java SE. Dùng version JUnit đang được duy trì/tương thích với toolchain dự án; không ép công cụ test lỗi thời vào ứng dụng mới.

### Kiểm theo bảng quyết định

- Nếu cần **tính theo phần tử trước và đúng thứ tự**, chọn `iterate`.
- Nếu cần **Supplier độc lập**, chọn `generate`.
- Nếu cần **điều kiện dừng dựa trên trạng thái**, chọn iterate **3 đối số Java 9+**.
- Nếu chỉ cần **n phần tử đầu**, dùng `limit(n)` đúng vị trí.
- Nếu chỉ cần **range primitive**, cân nhắc `IntStream.range`.
- Nếu muốn **parallel** hoặc **random**, kiểm semantics/order/thread safety riêng trước khi tối ưu.

## 16. Bài tập thực hành có đáp án định hướng

**Bài 1 — Sinh hằng:** Viết `Stream.generate(() -> "OK").limit(4)`. Đáp án khi collect: `[OK, OK, OK, OK]`. Giải thích vì sao không cần tạo List bốn phần tử trước.

**Bài 2 — Dãy số chẵn:** Dùng `Stream.iterate(0, n -> n+2).limit(5)`. Đáp án `[0, 2, 4, 6, 8]`; seed được phát đầu tiên.

**Bài 3 — Số nhân ba:** `Stream.iterate(1, n -> n*3).limit(4)` trả gì? Đáp án `[1, 3, 9, 27]`; giải thích nguy cơ overflow nếu không giới hạn.

**Bài 4 — Dãy bounded Java 9+:** `Stream.iterate(0, n -> n < 10, n -> n+3)` trả `[0,3,6,9]`. Giá trị 12 không được emit.

**Bài 5 — Seed rỗng:** `Stream.iterate(10, n -> n < 10, n -> n+1)` trả gì? Đáp án stream rỗng vì predicate false tại seed.

**Bài 6 — So sánh semantics:** Thử `iterate(0,n->n+1).filter(n->n<5).limit(3)` và `iterate(0,n->n<5,n->n+1).limit(3)` trên Java 9+. Cả hai có thể cho `[0,1,2]` nhưng chỉ bản thứ hai có điều kiện tự dừng nguồn; `filter` không tạo tính hữu hạn của toàn bộ stream.

**Bài 7 — Không dừng:** Giải thích lý do `generate(() -> 1).collect(toList())` không nên chạy. Đáp án: output không có giới hạn, có thể hết bộ nhớ.

**Bài 8 — Sort và limit:** Vì sao `iterate(0,n->n+1).sorted().limit(5)` không thể kết thúc như mong đợi trên nguồn vô hạn? Đáp án: `sorted` chặn trước khi limit được nhận dữ liệu; đổi `limit(5).sorted()` nếu cần sắp xếp năm giá trị đầu.

**Bài 9 — Encounter order:** Viết hai câu mô tả `generate` và `iterate`. Đáp án: generate là **unordered**, iterate là **ordered** dù cả hai trả sequential stream ban đầu.

**Bài 10 — Primitive:** Dùng `IntStream.range(1,6).sum()` và `IntStream.iterate(1,n -> n <= 5,n -> n+1).sum()` để nhận 15. Giải thích trường hợp range đơn giản hơn.

**Bài 11 — Parallel mutation:** Tại sao `Stream.generate(counter::incrementAndGet).parallel().limit(10)` không nên làm API cho “10 số đầu có thứ tự”? Đáp án: unordered semantics và counter side effects; atomic chỉ bảo vệ cập nhật, không bảo đảm encounter order.

**Bài 12 — Dữ liệu null:** Nếu Supplier trả null, vì sao `findFirst`/`map(String::length)` có thể lỗi? Đáp án: null không phải sentinel tự ngừng; các operations có contract không chấp nhận null ở những vị trí đó.

**Bài 13 — Phiên bản:** Viết chương trình dùng bounded iterate rồi compile với `--release 8`; ghi nhận không có overload tương ứng. Compile với Java 17+ được hỗ trợ để chạy đúng. Không gán nhầm chức năng Java 9 cho Java 8.

**Bài 14 — API thiết kế:** Chọn source cho ba bài toán: (a) 10 giá trị cố định, (b) dãy Fibonacci, (c) khoảng 1..10. Đáp án gợi ý: generate+limit cho (a), iterate với **state immutable** và termination hợp lý cho (b), IntStream.rangeClosed cho (c).

**Bài 15 — An toàn tài nguyên:** Phân biệt một Supplier pure trong bộ nhớ và Supplier gọi database/network. Với trường hợp thứ hai, cần kiểm cancellation, timeout, close và số yêu cầu tối đa; `limit` không thay thế lifecycle.

**Tiêu chí đạt:** Bạn dự đoán đúng output Java ở mục 10, phân biệt ordered/unordered với sequential/parallel, giải thích được seed/next/predicate, dùng `limit` đúng vị trí, không materialize nguồn vô hạn, và chọn factory phù hợp khi cần dãy hữu hạn.

## 17. Tài liệu chính thức đang còn áp dụng

- **Java SE 26, `java.util.stream.Stream`:** Javadoc chính thức cho `generate(Supplier)`, `iterate(seed,next)`, `iterate(seed,hasNext,next)`, `limit`, `findAny`, `anyMatch`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- **Java SE 26, `java.util.stream.IntStream`:** overload primitive iterate/generate/range: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html
- **Java SE 26, package `java.util.stream`:** lazy pipeline, encounter order, side effects, non-interference, statelessness: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- **Dev.java — Creating Streams:** https://dev.java/learn/api/streams/creating/
- **Java SE 9 Stream API (lịch sử ra đời overload ba đối số):** https://docs.oracle.com/javase/9/docs/api/java/util/stream/Stream.html

**Tóm tắt:** `generate` tạo các phần tử từ `Supplier` và **không bảo đảm encounter order**; `iterate(seed,next)` tạo một chuỗi ordered theo quan hệ với phần tử trước; `iterate(seed,hasNext,next)` (Java 9+) còn có điều kiện kết thúc. Cả ba đều lazy và đều cần quản lý giới hạn tài nguyên. Hãy chọn cách tạo stream theo **ngữ nghĩa thực của dữ liệu**, rồi đặt điều kiện dừng và terminal phù hợp trước khi áp dụng vào môi trường production.