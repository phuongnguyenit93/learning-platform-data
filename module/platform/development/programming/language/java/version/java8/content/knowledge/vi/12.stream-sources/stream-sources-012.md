# Giới hạn luồng vô hạn và quản lý tài nguyên của nguồn trong Java Stream

## 1. Mục tiêu và tư duy nền tảng

Java Stream API có từ Java 8 và **vẫn hiện hành trên JDK được bảo trì**. Một nguồn Stream có thể hữu hạn như `List.stream()`, `Arrays.stream(...)`, `Files.lines(path)`, hoặc **không có điểm dừng tự nhiên** như `Stream.generate(supplier)` và `Stream.iterate(seed, next)`. Dù các phần tử được tạo hoặc đọc **lazily** theo nhu cầu, pipeline vẫn có thể gây quá tải CPU, tăng bộ nhớ liên tục, giữ file/socket/connection quá lâu hoặc không bao giờ hoàn tất nếu thiếu giới hạn và cơ chế đóng nguồn.

Bài học trả lời hai câu hỏi khác nhau nhưng liên quan:

1. **Làm thế nào giới hạn công việc và output?** Sử dụng `limit`, điều kiện kết thúc, terminal short-circuit, cách sắp xếp các stage, giới hạn số phần tử được đọc và những biện pháp timeout/cancellation ở lớp điều phối.
2. **Làm thế nào quản lý tài nguyên của nguồn?** Phân biệt stream từ collection/generator thuần với stream giữ tài nguyên ngoài; dùng `try-with-resources`, `close()`, `onClose`, xử lý lỗi I/O và vòng đời của nguồn.

Bài này phân biệt đặc biệt rõ:

- **Finite source**: nguồn có số phần tử hữu hạn.
- **Conceptually infinite source**: nguồn có thể tiếp tục sinh phần tử nếu được yêu cầu, không mang hạn cuối tự nhiên.
- **Short-circuit**: một operation có **khả năng** hoàn tất trước khi tiêu thụ tất cả đầu vào.
- **Bounded output**: kết quả có giới hạn số phần tử, **không đồng nghĩa** chi phí hoặc thời gian xử lý đã được giới hạn.
- **Closed resource**: một tài nguyên của nguồn thực sự đã được đóng, **không đồng nghĩa** terminal operation đã kết thúc.

Cuối bài có chương trình Java 17+ tự tạo một file tạm, tìm một dòng bằng `findFirst`, xác nhận close handler được gọi, đồng thời minh họa nguồn sinh vô hạn được cắt bằng `limit`. Các phần dùng API xuất hiện từ Java 9+ sẽ được đánh dấu riêng, không gán sai chúng cho Java 8.

## 2. Mô hình pipeline và chỗ phát sinh rủi ro

~~~text
Source
  ├── List / array / finite range                  → hữu hạn
  ├── Stream.generate / Stream.iterate              → có thể không giới hạn
  └── Files.lines / Files.walk / socket-adapter      → có thể giữ tài nguyên
       │
       ▼
Intermediate stages
  filter / map / distinct / sorted / limit / takeWhile ...
       │
       ▼
Terminal
  findFirst / anyMatch / collect / count / forEach ...
       │
       ├── Có kết quả trong thời gian hữu hạn?
       ├── Đã giới hạn CPU / kích thước / memory?
       └── Đã đóng file / directory / connection?
~~~

**Lazy evaluation** nghĩa là các thao tác trung gian như `filter` và `map` nói chung chưa kéo nguồn cho đến khi một terminal operation bắt đầu traversal. Lazy **không** đảm bảo nguồn không thể chặn: một Supplier có thể chờ network, một file stream có thể gặp lỗi đọc giữa chừng, và một `collect(toList())` có thể yêu cầu vô số phần tử.

~~~java
java.util.stream.Stream<Integer> pending =
    java.util.stream.Stream.iterate(0, n -> n + 1);
// Chưa yêu cầu toàn bộ dữ liệu, nhưng vẫn không có biên kết thúc.

java.util.List<Integer> firstFive = pending
    .limit(5)
    .collect(java.util.stream.Collectors.toList());
// [0, 1, 2, 3, 4]
~~~

Đối tượng `pending` đã được tiêu thụ bởi terminal `collect`; không được gọi terminal lần hai trên cùng stream. Nếu cần một phép tính khác, tạo **stream mới** từ nguồn hoặc dùng một supplier tạo pipeline mới.

Không phải mọi stream đều cần `close()` sau mỗi lần tính. Stream dựa trên collection/array hoặc generator thuần thường không giữ tài nguyên ngoài; stream từ `Files.lines`/`Files.walk` thì khác. Vì vậy quản lý lifecycle phải dựa trên **loại nguồn** chứ không dựa vào việc có gọi `limit` hay không.

## 3. Các nguồn vô hạn thường gặp

### 3.1. `Stream.generate(Supplier)`

~~~java
java.util.List<String> result =
    java.util.stream.Stream.generate(() -> "tick")
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
// [tick, tick, tick]
~~~

`generate` trả về stream **sequential, unordered, conceptually infinite**. `Supplier.get()` được gọi khi pipeline yêu cầu thêm phần tử. Bản thân API không có tham số số lượng hoặc điều kiện kết thúc. Khi số phần tử cần thiết đã đủ, `limit(3)` cho phép pipeline dừng.

Không được suy ra rằng `generate` có encounter order ổn định chỉ vì Supplier tăng một counter. Đặc biệt khi gọi `parallel()`, stateful Supplier hoặc mutable counter có thể chạy từ nhiều luồng. `AtomicInteger` bảo đảm cập nhật nguyên tử, **không** tạo một hợp đồng về thứ tự được chọn trên nguồn unordered.

### 3.2. `Stream.iterate(seed, next)`

~~~java
java.util.List<Integer> result =
    java.util.stream.Stream.iterate(10, n -> n + 10)
        .limit(4)
        .collect(java.util.stream.Collectors.toList());
// [10, 20, 30, 40]
~~~

`iterate(seed,next)` trả stream **sequential, ordered, conceptually infinite**; giá trị tiếp theo phụ thuộc giá trị trước. Nó không tự ngừng nếu số nguyên overflow, nếu giá trị lặp lại hoặc nếu một trạng thái trông như “hết”. Cần giới hạn rõ.

Cả `generate` và bản `iterate` hai đối số có từ Java 8; **không** có timeout mặc định, backpressure kiểu reactive-stream, hoặc bảo đảm dừng sau một số lần gọi Supplier/next.

### 3.3. `Stream.iterate(seed, hasNext, next)` (Java 9+)

~~~java
java.util.List<Integer> bounded =
    java.util.stream.Stream.iterate(
        1,
        n -> n <= 10,
        n -> n + 3)
      .collect(java.util.stream.Collectors.toList());
// [1, 4, 7, 10]
~~~

Overload ba đối số có **từ Java 9**. Nó kiểm `hasNext` trước khi phát mỗi giá trị. Vì vậy giá trị ứng viên 13 không được phát, và nếu seed đã không thỏa predicate thì stream rỗng. Đây là cách tự nhiên để biểu diễn “duyệt đến khi điều kiện dừng”. Nhưng **chỉ** hữu hạn nếu điều kiện thật sự trở thành false trong quá trình chuyển trạng thái.

### 3.4. Các nguồn hữu hạn không cần giả lập bằng iterate

Đối với khoảng nguyên hữu hạn, `IntStream.range(0, 10)` hoặc `rangeClosed(1, 10)` thể hiện biên rõ, thường dễ hiểu hơn việc tạo nguồn vô hạn rồi cắt. Với dữ liệu từ `List`, dùng `list.stream()`. Với file, cần chọn API duyệt file theo yêu cầu bộ nhớ và lifecycle.

~~~java
int sum = java.util.stream.IntStream.rangeClosed(1, 4)
    .sum();
// 10
~~~

Không sử dụng `Stream.generate`/`iterate` chỉ vì tất cả đoạn code đều có thể viết thành Stream. Chọn nguồn mang semantics đúng sẽ giảm rủi ro vô hạn hoặc mất thứ tự.

## 4. `limit(n)`: giới hạn số phần tử đầu ra, không phải toàn bộ chi phí

`Stream.limit(long maxSize)` là **stateful short-circuiting intermediate operation**, trả stream có tối đa `maxSize` phần tử. `maxSize` phải không âm; `limit(0)` cho kết quả rỗng; `limit(-1)` ném `IllegalArgumentException`.

~~~java
java.util.List<Integer> page =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .limit(5)
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 3, 4, 5]
~~~

Ở pipeline này, `limit` đứng trực tiếp sau một nguồn iterate không chặn, nên việc collect chỉ cần các phần tử tương ứng để tạo danh sách hữu hạn.

### 4.1. `limit` sau `filter`: không biết phải duyệt bao nhiêu input

~~~java
java.util.List<Integer> firstThreeMultiples =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 7 == 0)
        .limit(3)
        .collect(java.util.stream.Collectors.toList());
// [7, 14, 21]
~~~

Output có ba phần tử, nhưng nguồn phải cung cấp **ít nhất đến 21** trong ví dụ tuần tự để thấy đủ ba phần tử đạt điều kiện. Nếu predicate không bao giờ true trên một nguồn không giới hạn, `limit(3)` **không thể tự tạo phần tử phù hợp**; traversal có thể không bao giờ hoàn tất.

~~~java
// KHÔNG chạy: filter luôn false trên nguồn vô hạn.
// Stream.generate(() -> 1)
//     .filter(n -> n == 2)
//     .limit(1)
//     .collect(Collectors.toList());
~~~

Ngược lại:

~~~java
java.util.List<Integer> firstFive =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .limit(5)
        .filter(n -> n % 7 == 0)
        .collect(java.util.stream.Collectors.toList());
// []  (chỉ xét 1..5)
~~~

**Thứ tự thao tác thay đổi ý nghĩa**: `filter().limit(3)` là “ba giá trị đầu thỏa điều kiện”; `limit(5).filter()` là “trong năm giá trị nguồn đầu, giữ giá trị thỏa điều kiện”. Không được tùy tiện hoán vị để nhanh hơn.

### 4.2. `limit` trước hoặc sau `sorted`

~~~java
java.util.List<Integer> a =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted(java.util.Comparator.reverseOrder())
        .collect(java.util.stream.Collectors.toList());
// [5, 4, 3, 2, 1]
~~~

~~~java
// KHÔNG chạy với nguồn không giới hạn:
// Stream.iterate(1, n -> n + 1)
//     .sorted()
//     .limit(5)
//     .collect(Collectors.toList());
~~~

`sorted` là **stateful intermediate operation** thường cần thấy toàn bộ input để sắp xếp chính xác. Khi `sorted` đứng **trước** `limit` trên nguồn vô hạn, việc sắp xếp toàn bộ input không hoàn tất. `limit` ở phía sau không thể giải quyết việc upstream chưa phát phần tử nào.

### 4.3. `distinct` cũng có thể khiến giới hạn không bao giờ đạt

~~~java
// KHÔNG chạy: chỉ có một giá trị duy nhất, không thể lấy 2 distinct.
// Stream.generate(() -> "A")
//     .distinct()
//     .limit(2)
//     .collect(Collectors.toList());
~~~

`distinct` cần nhớ các giá trị đã thấy để chỉ phát giá trị chưa trùng. Nếu nguồn cứ sinh `"A"`, pipeline sẽ chỉ tìm được một giá trị duy nhất và không thể lấp `limit(2)`. **`limit(2)` không chứng minh pipeline hữu hạn về thời gian**.

Với stream tạo giá trị mới liên tục, `distinct` cũng có thể tăng bộ nhớ theo số phần tử unique đã gặp. Hãy xác định **biên input**, **biên số lượng unique** và **biên bộ nhớ**, không dựa vào `limit` ở cuối như cơ chế chống quá tải tổng quát.

### 4.4. `skip` không biến vô hạn thành hữu hạn

~~~java
// Không có điểm dừng:
// Stream.iterate(0, n -> n + 1)
//     .skip(10)
//     .collect(Collectors.toList());
~~~

`skip(10)` chỉ bỏ 10 phần tử ban đầu, phần còn lại vẫn không giới hạn. Muốn số lượng output hữu hạn, có thể dùng `skip(offset).limit(size)` với offset và size đã kiểm tra. Với offset lớn, vẫn có chi phí duyệt qua các phần tử bỏ qua; trong ứng dụng DB, nên phân trang tại nguồn khi phù hợp.

## 5. Các terminal short-circuit và giới hạn logic

Một **short-circuiting terminal** có thể dừng khi thấy kết quả đủ để quyết định:

| Terminal | Khi nào có thể hoàn tất sớm? | Nếu điều kiện không xuất hiện trên nguồn vô hạn? |
| --- | --- | --- |
| `findFirst()` | Khi đã xác định phần tử đầu theo encounter order | Có thể chờ mãi nếu trước đó có filter không cho phần tử nào qua |
| `findAny()` | Khi tìm thấy một phần tử bất kỳ | Có thể chờ mãi nếu không có phần tử qua các stage |
| `anyMatch(p)` | Khi gặp phần tử thỏa `p` | Có thể chạy mãi nếu `p` không bao giờ đúng |
| `allMatch(p)` | Khi gặp phần tử không thỏa `p` | Có thể chạy mãi nếu mọi phần tử luôn thỏa |
| `noneMatch(p)` | Khi gặp phần tử thỏa `p` | Có thể chạy mãi nếu mọi phần tử luôn không thỏa |

~~~java
boolean found =
    java.util.stream.Stream.iterate(0, n -> n + 1)
        .anyMatch(n -> n == 4);
// true
~~~

Ở ví dụ hữu hạn về mặt công việc này, predicate đã đạt tại số 4 nên `anyMatch` có thể hoàn tất sớm. Nhưng:

~~~java
// KHÔNG chạy trên nguồn không giới hạn:
// Stream.generate(() -> 1).anyMatch(n -> n == 2);
~~~

vì điều kiện không bao giờ thỏa. Từ **“có thể dừng”** trong định nghĩa short-circuit không phải “luôn dừng”.

### 5.1. `findFirst` và `findAny`

- `Stream.iterate` tạo ordered source, nên `findFirst` giữ quan hệ “đầu tiên theo encounter order”.
- `Stream.generate` tạo unordered source, vì thế không có cam kết “giá trị thứ nhất của supplier” theo nghĩa thứ tự nghiệp vụ khi parallel.
- `findAny` có thể trả bất kỳ phần tử phù hợp, hữu ích khi order không cần thiết.
- Với object stream, `findFirst`/`findAny` trả `Optional<T>`, không thể tạo `Optional` chứa null: nếu phần tử được chọn là null, có thể có `NullPointerException`.

Không viết test cho parallel stream dựa vào số lần gọi predicate hay thread cụ thể; đó không phải hợp đồng đầu ra chung của Stream API.

### 5.2. `takeWhile` từ Java 9+: chặn theo một prefix

~~~java
// Chỉ Java 9+:
java.util.List<Integer> firstFive =
    java.util.stream.Stream.iterate(1, n -> n + 1)
        .takeWhile(n -> n <= 5)
        .collect(java.util.stream.Collectors.toList());
// [1, 2, 3, 4, 5]
~~~

Trên **ordered stream**, `takeWhile` trả longest prefix thỏa predicate. Nó có thể đưa pipeline vô hạn thành hữu hạn nếu predicate eventually false. `takeWhile` **khác** `filter`: sau khi gặp phần tử không thỏa, `takeWhile` không tiếp tục tìm phần tử thỏa ở phía sau trong encounter order.

~~~java
// Java 9+; trên ordered source:
java.util.List<Integer> prefix =
    java.util.stream.Stream.of(1, 2, 0, 3, 4)
        .takeWhile(n -> n > 0)
        .collect(java.util.stream.Collectors.toList());
// [1, 2]
~~~

`dropWhile` cũng có từ Java 9+ nhưng **không phải một operation short-circuit để cắt toàn bộ output**: nó bỏ prefix thỏa predicate rồi tiếp tục cho phần còn lại đi qua. Không dùng `dropWhile` một mình để đảm bảo nguồn vô hạn kết thúc.

### 5.3. Dừng theo predicate tại source

~~~java
// Java 9+: nguồn tự có điều kiện kết thúc.
java.util.List<Integer> bounded =
    java.util.stream.Stream.iterate(
        0, n -> n < 5, n -> n + 1)
      .collect(java.util.stream.Collectors.toList());
// [0, 1, 2, 3, 4]
~~~

Đặt điều kiện dừng **ngay tại nguồn** thường giúp semantics rõ hơn khi bài toán vốn có ranh giới theo trạng thái; điều kiện phải được kiểm thử với seed, step, null và overflow. Nếu predicate không bao giờ false thì dù overload có ba tham số, stream vẫn có thể vô hạn.

## 6. Giới hạn số phần tử khác với timeout, cancellation và backpressure

Một pipeline có `limit(100)` không tự đảm bảo hoàn tất trong 100 ms hay chỉ tốn 100 lần đọc:

- Supplier đọc network có thể chờ vô hạn ngay ở lần đầu.
- Một `filter` có thể phải xét hàng triệu phần tử mới lấy đủ 100 kết quả.
- `sorted` ở upstream có thể cần toàn bộ input.
- Nguồn I/O có thể gặp lỗi hoặc network bị đứt giữa traversal.
- Parallel pipeline có thể xử lý thêm phần tử đang chạy dở trước khi short-circuit có hiệu lực.
- Một `map` có thể thực hiện công việc CPU rất nặng cho từng phần tử.
- Một nguồn có data không giới hạn và `collect(toList())` trước khi giới hạn ở lớp ứng dụng có thể gây hết bộ nhớ.

Hãy phân biệt **bốn loại ngân sách**:

| Ngân sách | Ví dụ ràng buộc | Cơ chế phù hợp |
| --- | --- | --- |
| Số phần tử **output** | Tối đa 100 record | `limit(100)` hoặc source có giới hạn |
| Số phần tử **input/attempt** | Không đọc quá 1.000 candidate | Đặt `limit(1000)` phía **trước** filter phù hợp, hoặc kiểm budget tại nguồn |
| Thời gian | Dừng request sau một deadline | Timeout/cancellation của executor, I/O và layer điều phối; không chỉ `limit` |
| Bộ nhớ/tài nguyên | Không buffer toàn file, không giữ open socket | Stream tiêu thụ từng phần tử, tránh barrier, đóng nguồn trong scope |

**Cảnh báo về semantics:** `source.limit(1000).filter(...).limit(100)` không phải yêu cầu “trả đủ 100 kết quả”; nó nói “chỉ xem tối đa 1.000 input đầu để tìm tối đa 100 kết quả”. Chấp nhận có ít kết quả hơn khi hết ngân sách. Điều đó phải được document trong API.

### 6.1. Timeout bên ngoài không mặc định dừng worker bên trong

Ví dụ, một Future timeout ở thread gọi có thể khiến caller ngừng chờ, nhưng tác vụ nền hoặc I/O đang kẹt có thể **vẫn tiếp tục** nếu không có cơ chế hủy/cooperative cancellation ở tầng tương ứng. Một stream API không tự cấp backpressure giữa remote producer và consumer; nếu nguồn là network hoặc message broker, hãy dùng API streaming/cancellation có hợp đồng lifecycle riêng của thư viện đang được bảo trì.

Khi thiết kế service, cân nhắc deadline, cancel propagation, interrupt handling, kết thúc resource trong `finally`/`try-with-resources`, và quota số requests/bytes. Không lấy `limit` làm một cơ chế bảo vệ hệ thống duy nhất.

### 6.2. Kiểm giới hạn do người dùng truyền

~~~java
static int validatedPageSize(int requested) {
    if (requested < 0 || requested > 500) {
        throw new IllegalArgumentException("pageSize must be 0..500");
    }
    return requested;
}
~~~

Đây là **mảnh method minh họa**, không phải file độc lập. Nó cho thấy phải phân biệt logic validation trong ứng dụng với hợp đồng `limit(maxSize)` (chỉ từ chối giá trị âm, không từ chối giá trị cực lớn). Giới hạn tối đa riêng là yêu cầu nghiệp vụ.

Kiểm cả `offset`/`pageSize`, overflow khi tính `page * size`, khả năng dữ liệu thay đổi giữa nhiều pages và việc phân trang tại nguồn (database) thường hiệu quả hơn stream toàn bộ dữ liệu rồi `skip`.

## 7. Khi nào cần đóng một Stream?

`Stream<T>` kế thừa `BaseStream<T,Stream<T>>`, triển khai `AutoCloseable` và hỗ trợ `close()`/`onClose(Runnable)`. Nhưng tài nguyên thật **do nguồn sở hữu**:

| Nguồn | Có tài nguyên ngoài cần đóng? | Cách thực hành |
| --- | --- | --- |
| `List.stream()`, `Arrays.stream(...)` | Thường không | Tiêu thụ một lần; không cần đóng chỉ vì đã dùng Stream |
| `Stream.generate`/`iterate` với hàm thuần | Thường không | Đặt biên dừng; tránh giữ state dùng chung |
| `Files.lines(path)` | **Có**: file mở | Dùng `try-with-resources` bao quanh **toàn bộ traversal** |
| `Files.list(dir)` | **Có**: directory mở | Đóng stream sau khi xử lý |
| `Files.walk(dir)` / `Files.find(...)` | **Có**: có thể mở directory resources | Đóng stream |
| `BufferedReader.lines()` | Reader sở hữu nguồn có thể cần đóng | Quản lý/đóng **BufferedReader** sở hữu resource |
| Stream từ adapter database/network | Tùy contract của thư viện | Xác minh chính xác owner và close semantics; thường dùng scoped resource/transaction |

**Phân biệt rất quan trọng:** `BufferedReader.lines()` cung cấp stream trên reader; đừng mặc định `stream.close()` sẽ đóng mọi `BufferedReader` giống `Files.lines()`. Hợp đồng đóng của nguồn ngoài cần được kiểm. Khi chính bạn mở reader, cách rõ nhất là:

~~~java
// Trong method throws IOException hoặc xử lý checked exception:
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             path, java.nio.charset.StandardCharsets.UTF_8)) {
    java.util.Optional<String> first = reader.lines()
        .filter(s -> s.startsWith("WARN"))
        .findFirst();
    // Tài nguyên reader được đóng khi rời block.
}
~~~

Tương tự, không giả định mọi stream object truy xuất từ HTTP client/DB driver có thể đóng toàn bộ connection pool, hoặc rằng `close` trả connection về pool, nếu docs/framework không bảo đảm điều đó.

## 8. `Files.lines` và `try-with-resources`: mẫu chuẩn

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

// Fragment bên trong method có xử lý IOException:
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    Optional<String> firstWarning = lines
        .filter(s -> s.startsWith("WARN"))
        .findFirst();
    // Dùng firstWarning bên trong hoặc lấy kết quả ra ngoài block.
}
~~~

`Files.lines` mở file và trả một **lazily populated stream**. Theo Javadoc, file sẽ được đóng khi stream được đóng; phải dùng try-with-resources hoặc cấu trúc tương đương. `findFirst` thường không cần đọc hết file, nhưng **việc tìm thấy kết quả không tự gọi `lines.close()`**. Tài nguyên được giải phóng bởi phần `try` khi rời scope, kể cả khi có exception.

### 8.1. Tạo stream bên ngoài rồi đóng quá sớm

~~~java
// Đừng làm vậy:
Stream<String> lines;
try (Stream<String> opened = Files.lines(path)) {
    lines = opened;
}
// lines đã đóng; dùng terminal ở đây là sai lifecycle.
~~~

Nếu cần trả kết quả, hãy **trả một giá trị đã materialize phù hợp** như `Optional<String>`, `List<String>` đã giới hạn, hoặc DTO; không trả một lazy stream đã đóng. Nếu API thật sự trả `Stream` đang mở, phải document rõ **caller là owner và phải close**, và có test chứng minh trách nhiệm được thực hiện. Thiết kế trả stream mở có thể hữu ích trong một số thư viện, nhưng làm tăng nguy cơ resource leak nếu không quản lý ownership.

### 8.2. Chỉ đóng khi sử dụng xong, không đợi GC

Rely on garbage collection/finalization để đóng file là không đáng tin và không đảm bảo đóng đúng lúc. Trên server có nhiều requests, leaked file descriptors có thể làm toàn bộ service không mở được file/socket mới. Dùng `try-with-resources` và kiểm scope ngay cả khi pipeline short-circuit, thất bại hoặc bị hủy.

### 8.3. Terminal operation không đồng nghĩa close

~~~java
// Có thể đọc xong, nhưng nguồn Files.lines vẫn cần close.
Stream<String> lines = Files.lines(path);
long count = lines.limit(10).count();
// Đừng bỏ qua lines.close(); trong code đúng nên dùng try-with-resources.
~~~

Đoạn trên là **anti-pattern minh họa**, không phải khuyến nghị thực thi. Với stream từ `List`, terminal xong thường đủ vì không có file/socket cần giải phóng; điều này không mở rộng sang nguồn I/O.

## 9. `onClose` và propagation qua pipeline

`BaseStream.onClose(Runnable)` đăng ký một hành động chạy khi gọi `close()` trên stream/pipeline. Đây là công cụ hữu ích để nối lifecycle cho nguồn custom hoặc quan sát đóng nguồn trong test.

~~~java
java.util.concurrent.atomic.AtomicBoolean closed =
    new java.util.concurrent.atomic.AtomicBoolean(false);

try (java.util.stream.Stream<Integer> stream =
         java.util.stream.Stream.iterate(1, n -> n + 1)
             .onClose(() -> closed.set(true))) {
    long count = stream.limit(2).count();
    // count == 2, nhưng closed có thể vẫn false trong block.
}
// try-with-resources gọi close(), handler đánh dấu true.
// closed.get() == true
~~~

**Điểm then chốt:** `onClose` **không** nói “hành động này được gọi sau mỗi terminal operation”; nó chạy khi pipeline được **đóng**. Hệ thống không đóng stream tự động chỉ vì `count`, `findFirst` hoặc `collect` đã hoàn tất. Nếu bạn cần close handler, hãy thực sự gọi `close()`/dùng try-with-resources.

### 9.1. Close handler không phải callback cho từng phần tử

Không dùng `onClose` để xử lý record cuối hoặc điều khiển counter dữ liệu. Nó là callback lifecycle của stream, không phải `peek` và không gắn với mỗi lần Supplier được gọi.

### 9.2. Nhiều close handlers và exception

Theo `BaseStream` API, các close handlers được gọi theo thứ tự thêm vào; nếu một handler ném exception, framework vẫn gọi các handlers tiếp theo. Exception đầu tiên được truyền ra và các exception còn lại có thể được thêm dưới dạng **suppressed exceptions**. Đây là lý do nên viết handler an toàn, idempotent và có test cleanup khi nhiều resource.

~~~java
// Fragment:
Stream<String> stream = Stream.of("A")
    .onClose(() -> System.out.print("A"))
    .onClose(() -> System.out.print("B"));
// Gọi stream.close() sẽ thực thi handlers theo thứ tự A rồi B.
~~~

Tránh việc close handler ném exception che khuất lỗi nghiệp vụ chính; khi cần xử lý, logging và suppressed-exception inspection nên làm theo exception policy của ứng dụng.

### 9.3. Close propagation qua một số combinators

`Stream.concat(a, b)` tạo stream mới; khi đóng stream concat, close handlers của cả `a` và `b` được gọi theo hợp đồng API. `flatMap` xử lý inner streams và đóng mỗi mapped stream sau khi nội dung của nó được đưa vào outer stream. Nhưng điều đó **không miễn** trách nhiệm đóng **outer stream sở hữu nguồn** khi cần.

Không suy ra mọi custom operator/gatherer/plugin đều có cùng close propagation; đọc contract của operator cụ thể, nhất là khi nó mở resource ngoài hoặc chuyển execution sang thread khác.

## 10. Lỗi I/O trong traversal và quản lý exception

Đối với `Files.lines`, lỗi mở file xảy ra tại invocation có thể là checked `IOException`. Một lỗi đọc xuất hiện **sau đó khi terminal duyệt stream** có thể được bọc trong `UncheckedIOException`; lỗi đóng file cũng có thể xuất hiện theo contract. Vì vậy:

- Đặt cả **mở nguồn và terminal traversal** bên trong scope có quản lý resource.
- Xử lý/ghi log lỗi ở boundary phù hợp; đừng nuốt exception rồi tuyên bố xử lý thành công.
- Nếu business operation và close cùng lỗi, hiểu cơ chế suppressed exceptions của try-with-resources.
- Không dùng `findFirst` như bằng chứng “toàn bộ file không còn lỗi”; nó chỉ đọc đủ để tìm phần tử phù hợp, có thể không đọc phần file sau đó.

~~~java
// Cần khai báo throws IOException hoặc catch IOException ở method:
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(s -> !s.isEmpty())
         .limit(100)
         .forEach(System.out::println);
} catch (java.io.UncheckedIOException ex) {
    // Lỗi phát sinh khi đang đọc/đóng file: xử lý hoặc báo về caller.
    throw ex;
}
~~~

**Lưu ý:** catch `UncheckedIOException` ở đây không bắt mọi checked `IOException` lúc `Files.lines(...)` mở file; code xung quanh vẫn cần method `throws IOException` hoặc catch riêng. Không dùng code này để giấu các lỗi I/O.

### Khi dùng `Files.walk`

`Files.walk(start)` tạo stream Path có thể mở nhiều directory resources; nên giới hạn độ sâu với overload `Files.walk(start, maxDepth)` khi yêu cầu nghiệp vụ cho phép, đồng thời dùng try-with-resources. Một `limit(10)` trên `Files.walk` **không thay thế** depth/permission/symlink policy và không tự đóng directories khi dừng sớm.

~~~java
// Fragment trong method throws IOException:
try (Stream<Path> paths = Files.walk(root, 2)) {
    long fileCount = paths
        .filter(Files::isRegularFile)
        .count();
}
~~~

Ví dụ tính `fileCount` sau khi giới hạn độ sâu. Trong production, cân nhắc symbolic links, đường dẫn untrusted, access controls, file-tree mutations và chi phí file metadata; nếu chỉ cần file đầu tiên, dùng `findFirst` nhưng vẫn phải close stream.

## 11. Chương trình Java 17+ chạy độc lập, xác minh cả giới hạn và đóng nguồn

Tạo file **`BoundedSourcesDemo.java`** bằng UTF-8. Chương trình chạy với Java 17+ (các API sử dụng ở đây đã có từ Java 8), không cần thư viện ngoài. Nó:

1. Tạo một `generate` chưa được tiêu thụ, chứng minh lazy.
2. Lấy đúng ba phần tử rồi thu kết quả.
3. Tạo một `iterate` vô hạn về mô hình nhưng lấy bốn phần tử đầu.
4. Giới hạn trước khi sort để có kết quả hữu hạn.
5. Kiểm `limit(0)` với nguồn tạo giá trị.
6. Tạo file tạm, đọc bằng `Files.lines`, `findFirst` và đóng bằng try-with-resources.
7. Tạo một stream generator có close handler, chứng minh terminal `count` không tự thay thế việc đóng stream.
8. Dọn file tạm cả khi xảy ra lỗi.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class BoundedSourcesDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger calls = new AtomicInteger();

        Stream<String> generated = Stream.generate(() -> {
            calls.incrementAndGet();
            return "ping";
        });

        System.out.println("generate-before: " + calls.get());

        List<String> result = generated.limit(3)
            .collect(Collectors.toList());
        System.out.println("generate: " + result);
        System.out.println("generate-after: " + calls.get());

        List<Integer> numbers = Stream.iterate(1, n -> n + 1)
            .limit(4)
            .collect(Collectors.toList());
        System.out.println("iterate: " + numbers);

        List<Integer> sorted = Stream.iterate(1, n -> n + 1)
            .limit(4)
            .sorted((a, b) -> Integer.compare(b, a))
            .collect(Collectors.toList());
        System.out.println("sort-limited: " + sorted);

        long zero = Stream.generate(() -> "X")
            .limit(0)
            .count();
        System.out.println("limit-zero: " + zero);

        Path temp = Files.createTempFile("bounded-stream-", ".txt");
        AtomicBoolean fileClosed = new AtomicBoolean(false);

        try {
            Files.write(
                temp,
                Arrays.asList(
                    "INFO: boot",
                    "WARN: one",
                    "WARN: two"),
                StandardCharsets.UTF_8);

            Optional<String> first;
            try (Stream<String> lines =
                     Files.lines(temp, StandardCharsets.UTF_8)
                         .onClose(() -> fileClosed.set(true))) {
                first = lines
                    .filter(s -> s.startsWith("WARN"))
                    .findFirst();
            }

            System.out.println("file-first: "
                + first.orElse("none"));
            System.out.println("file-close: " + fileClosed.get());
        } finally {
            Files.deleteIfExists(temp);
        }

        AtomicBoolean generatedClosed = new AtomicBoolean(false);
        long count;
        try (Stream<Integer> source =
                 Stream.iterate(10, n -> n + 1)
                     .onClose(() -> generatedClosed.set(true))) {
            count = source.limit(2).count();
        }

        System.out.println("generated-count: " + count);
        System.out.println("generated-close: " + generatedClosed.get());
    }
}
~~~

Biên dịch/chạy với JDK hiện đại có hỗ trợ target 17:

~~~text
javac --release 17 -encoding UTF-8 BoundedSourcesDemo.java
java BoundedSourcesDemo
~~~

**Stdout chính xác — 10 dòng:**

~~~text
generate-before: 0
generate: [ping, ping, ping]
generate-after: 3
iterate: [1, 2, 3, 4]
sort-limited: [4, 3, 2, 1]
limit-zero: 0
file-first: WARN: one
file-close: true
generated-count: 2
generated-close: true
~~~

**Phân tích kết quả:**

- Trước terminal, `calls == 0`, thể hiện nguồn generate chưa bị kéo.
- `limit(3).collect(toList())` lấy ba chuỗi `ping`. Trong **sequential pipeline cụ thể** này Supplier được gọi ba lần; không dùng số lần gọi Supplier làm hợp đồng của bất kỳ parallel pipeline nào.
- `iterate(1,n->n+1).limit(4)` tạo 1,2,3,4. `limit(4).sorted(reverse)` sort **sau** khi cắt xuống bốn phần tử, tạo 4,3,2,1.
- `limit(0)` trả stream rỗng, `count` bằng 0.
- `Files.lines` tìm WARN đầu tiên rồi block try-with-resources đóng stream. `onClose` xác nhận `fileClosed == true`. File tạm được xóa trong `finally` sau khi stream đã đóng.
- `Stream.iterate` có close handler dù bản thân nguồn thuần không đòi file descriptor. Chương trình thực sự đóng stream bằng try-with-resources, nên `generatedClosed == true`; terminal `count` không được hiểu là hành động đóng.

Chương trình dùng đường dẫn file tạm ngẫu nhiên **nhưng không in tên file**, vì thế stdout ổn định. Nó không đòi network hay framework ngoài Java SE. Nếu môi trường không cho phép tạo file tạm hoặc gặp lỗi I/O, chương trình ném exception thay vì bịa một kết quả thành công; đó là điều cần kiểm trong CI có filesystem bị hạn chế.

## 12. Mẫu riêng cho Java 8 (không dùng API từ Java 9)

Đây là file độc lập **`BoundedJava8Demo.java`** dùng API tồn tại ngay từ Java 8:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class BoundedJava8Demo {
    public static void main(String[] args) {
        List<Integer> values =
            Stream.iterate(0, n -> n + 2)
                .limit(4)
                .collect(Collectors.toList());

        List<String> repeated =
            Stream.generate(() -> "OK")
                .limit(2)
                .collect(Collectors.toList());

        System.out.println(values);
        System.out.println(repeated);
    }
}
~~~

Biên dịch trên JDK hiện đại có hỗ trợ release 8:

~~~text
javac --release 8 -encoding UTF-8 BoundedJava8Demo.java
java BoundedJava8Demo
~~~

Stdout:

~~~text
[0, 2, 4, 6]
[OK, OK]
~~~

Đừng compile những snippet chứa `takeWhile` hoặc `iterate(seed,hasNext,next)` bằng `--release 8`: hai tính năng đó được thêm từ Java 9. Java 8-origin `limit`, `Files.lines`, `onClose` và try-with-resources vẫn được dùng trong ứng dụng trên JDK hiện đại; không xem chúng là legacy chỉ vì nguồn gốc phiên bản.

## 13. Lưu ý đặc biệt khi stream có nguồn bên ngoài

### 13.1. File handle và directory handle

File và directory stream có thể giữ descriptor/handle. Trong một API web, việc rò rỉ một handle mỗi request có thể dẫn tới lỗi “too many open files” hoặc không thể xóa/rename file trên một số hệ điều hành. Đừng dựa vào garbage collector để đóng đúng lúc. Kiểm bằng test lặp lại, logging resource usage ở môi trường thử nghiệm, và code review scope TWR.

### 13.2. Database cursor và transaction

Một số ORM/driver có API trả stream từ query, nhưng contract **không phải JDK Stream chuẩn thống nhất về việc mở/đóng JDBC resources**. Có thư viện yêu cầu transaction còn mở trong suốt traversal và gọi close trên stream, một số thư viện sở hữu statement/result set riêng. Hãy đọc docs của phiên bản đang dùng, đặt traversal **bên trong** transaction/resource scope và viết integration test khi dừng sớm hoặc exception.

Không trả một lazy query stream sau khi transaction scope đã đóng. Ngược lại, không mở transaction quá lâu để tiêu thụ một nguồn vô hạn. Có thể cần pagination/batching hoặc API cursor có lifecycle tường minh.

### 13.3. Network, message broker và producer vô hạn

Một stream adapter trên socket không tự mang demand/backpressure/cancel semantics chỉ vì nó trả `java.util.stream.Stream`. Producer có thể tiếp tục phát dữ liệu dù consumer dùng `limit` và ngừng yêu cầu. Nếu nguồn có listener/thread/background task, thiết kế close handler hoặc cơ chế subscription cancellation theo thư viện tương ứng, xác minh nó **thật sự dừng producer**.

Dùng API phản ứng có backpressure khi workload cần điều phối tốc độ producer/consumer, thay vì collect vô hạn vào List. Không lẫn khái niệm Stream API với các API reactive có contract khác.

### 13.4. Dữ liệu từ bên thứ ba có thể không ổn định

File đang bị sửa trong lúc `Files.lines` duyệt có semantics ngoài kỳ vọng; tài liệu nêu không nên sửa file khi terminal đang chạy. Với nguồn network/DB, kết quả có thể thay đổi khi các request bị phân trang theo thời gian. Hãy xác định snapshot/isolation/version cần thiết cho tính đúng của API, không giả định Stream mang ảnh chụp bất biến của dữ liệu.

## 14. Parallel stream và rủi ro khi giới hạn

Trên ordered parallel stream, `limit(n)` có thể cần giữ **đúng n phần tử đầu** theo encounter order, làm tăng đồng bộ/buffering. `unordered()` có thể giảm chi phí nhưng **chỉ** khi nghiệp vụ không cần kết quả đầu tiên theo thứ tự.

~~~java
java.util.List<Integer> values =
    java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .limit(3)
        .boxed()
        .collect(java.util.stream.Collectors.toList());
// Kết quả theo order nguồn là [0, 1, 2] đối với pipeline này.
~~~

Khi không cần order, `findAny` thay cho `findFirst` có thể hữu ích; nhưng không thể viết test bắt `findAny` luôn trả một phần tử cố định.

**Hạn chế shared-state Supplier:**

~~~java
// Tránh diễn giải đây là "10 số liên tiếp đầu" trong parallel:
// AtomicInteger counter = new AtomicInteger();
// Stream.generate(counter::incrementAndGet).parallel()
//     .limit(10).collect(Collectors.toList());
~~~

Cập nhật nguyên tử không đồng nghĩa phần tử có encounter order. Nếu cần range hữu hạn và có thể chia đều, `IntStream.range` hoặc `LongStream.range` thường tốt hơn.

**Tối ưu hóa và side effects:** Stream implementation được phép bỏ qua một số lời gọi behavioral parameters khi kết quả không đổi. `peek` không phải một công cụ audit/metering đáng tin cho mọi pipeline; đặc biệt `count()` trên nguồn có exact size metadata có thể không duyệt phần tử. Đừng đo “số phần tử đã đọc” bằng side effects của `peek` rồi dùng như security quota toàn cục. Đặt budget ở lớp nguồn/connector đáng tin và test.

## 15. Bảng lựa chọn theo loại bài toán

| Bài toán | Hướng làm | Nguy cơ chính |
| --- | --- | --- |
| Lấy 20 phần tử đầu của dãy sinh đơn giản | `generate(...).limit(20)` hoặc `iterate(...).limit(20)` | Shared state, output count |
| Lấy các phần tử đến một mốc trạng thái | Bounded `iterate(seed,hasNext,next)` Java 9+ | Predicate không kết thúc, overflow |
| Tìm dòng đầu tiên có chứa ERROR trong log lớn | `Files.lines` + `filter` + `findFirst` trong TWR | File handle leak, read-time IOException |
| Lấy N dòng đầu của file | `Files.lines` + `limit(N)` trong TWR | N cần validate, file vẫn cần close |
| Quét thư mục giới hạn độ sâu | `Files.walk(root,maxDepth)` trong TWR | Symlink policy, handle/depth |
| Tìm N giá trị thỏa từ nguồn vô hạn | `filter` + `limit(N)` **và** budget input/deadline | Không đủ N matches nên không kết thúc |
| Cần sort toàn bộ một stream vô hạn | Đổi yêu cầu/thuật toán; không dùng `sorted()` toàn nguồn | Không thể hoàn tất, memory |
| Top-k từ nguồn hữu hạn lớn | Heap/selection hoặc `sorted().limit(k)` nếu hợp lý | Memory, tie-breaking, comparator |
| Batch hàng triệu bản ghi DB | Pagination/cursor API có lifecycle rõ | Transaction/cursor leak, DB load |
| Network feed liên tục | API streaming có cancellation và backpressure | Không có giới hạn tốc độ/tài nguyên |
| Đọc dữ liệu vào tài liệu/report | Giới hạn số dòng/bytes và materialize kết quả cần thiết trong resource scope | Output không giới hạn, latency |

**Không cần dùng Stream trong mọi tình huống.** Một vòng `for` với counter kiểm tổng số lần đọc, timeout/cancel và tài nguyên trong TWR đôi khi diễn đạt contract dễ kiểm hơn một pipeline có nhiều stage stateful.

## 16. Những hiểu nhầm và lỗi thường gặp

### 16.1. “Lazy nghĩa là không thể hết bộ nhớ”

Sai. Lazy chỉ hoãn traversal. `Stream.generate(...).collect(toList())` có thể liên tục thêm vào List mà không có giới hạn và cuối cùng hết bộ nhớ.

### 16.2. “Có `limit(10)` là chắc chắn chỉ gọi Supplier 10 lần”

Không phải hợp đồng chung trong mọi pipeline, đặc biệt nếu có filter, parallel stage hoặc optimizer. `limit` bảo đảm **kích thước kết quả tối đa** trong vị trí mà nó được áp dụng, không cam kết số lần gọi mọi callback trong mọi thực thi.

### 16.3. “`filter` tự dừng khi predicate false”

Sai. `filter` chỉ bỏ phần tử hiện tại, không báo source kết thúc. `takeWhile` có semantics prefix từ Java 9+, khác `filter` và có thể dừng ở phần tử không thỏa đầu tiên trên ordered stream.

### 16.4. “`skip` biến nguồn vô hạn thành hữu hạn”

Sai. `skip(n)` chỉ loại n phần tử đầu. Phần còn lại có thể vẫn vô hạn.

### 16.5. “`sorted().limit(10)` luôn an toàn trên nguồn vô hạn”

Sai. `sorted` ở upstream cần thấy hết input trước khi cung cấp kết quả; nguồn vô hạn khiến việc sort không hoàn tất.

### 16.6. “`findFirst` đóng file khi tìm được dữ liệu”

Sai. `findFirst` là terminal short-circuit, **không phải** lời gọi `close()` trên stream giữ file. Dùng TWR.

### 16.7. “Tất cả Java Streams phải được đóng như file”

Không đúng. Stream từ collection/generator thuần thường không nắm tài nguyên ngoài. Đóng những stream cần đóng và stream có close handler để bảo đảm lifecycle, nhưng không phát sinh nghi thức đóng giả tạo chỉ vì muốn “chuẩn” hóa mọi List stream.

### 16.8. “`BufferedReader.lines()` được đóng y hệt `Files.lines()`”

Không nên suy luận vậy. Đối với reader tự mở, đặt **reader** trong TWR; `Files.lines()` là API có tài liệu nói stream close sẽ đóng file được mở cho stream.

### 16.9. “`onClose` chạy sau mọi terminal”

Không. Nó chạy khi `close` được gọi. Test bằng `AtomicBoolean` trong ví dụ mục 11.

### 16.10. “Timeout hoàn tất là task I/O cũng đã bị hủy”

Không được bảo đảm. Future timeout có thể chỉ dừng việc caller chờ. Phải có cancellation hợp tác và cơ chế đóng ngắt nguồn/I/O phù hợp.

### 16.11. “Parallel làm `limit` luôn nhanh hơn”

Không. Với encounter order, parallel limit có thể đòi synchronization và buffer. Chọn đúng semantics trước rồi benchmark.

### 16.12. “Đã dùng `Files.walk` thì không cần xét security”

Sai. Cần quản lý maxDepth, symlink, path permissions, TOCTOU và tài nguyên. Stream không tự đặt sandbox hoặc bảo vệ truy cập file.

### 16.13. “Không thể phát sinh exception khi đã mở được file”

Lỗi đọc có thể xuất hiện **giữa traversal** dưới dạng `UncheckedIOException`, không chỉ lúc mở bằng `Files.lines`. Scope đóng tài nguyên và exception handling phải bao cả terminal.

### 16.14. “Nguồn vô hạn luôn có thể được giới hạn bằng `count`”

Sai. `count` là phép đếm, không phải một biên số phần tử khi nguồn không có finite size; không nên gọi trực tiếp trên nguồn vô hạn.

## 17. Checklist production

- [ ] Xác định nguồn hữu hạn, conceptually infinite hay chỉ là external feed không biết độ dài.
- [ ] Có biên output rõ (số record tối đa), kiểm `limit` nhận số không âm.
- [ ] Có biên input/attempt và thời gian khi một `filter` có thể hiếm khi đạt điều kiện.
- [ ] Tránh blocking stateful stage trên stream không có điểm kết thúc.
- [ ] Chọn `findFirst`, `findAny`, `anyMatch` theo semantics và điều kiện dừng thật.
- [ ] Các nguồn `Files.lines`, `Files.list`, `Files.walk`/`find` đều ở trong TWR.
- [ ] Với reader/DB/network, xác định chính xác owner và close/cancel contract.
- [ ] Không trả lazy stream đã đóng ra khỏi scope; khi trả stream mở, document caller ownership.
- [ ] Biết rằng terminal kết thúc **không** tự gọi `close`; close handlers chỉ chạy khi đóng.
- [ ] Kiểm lỗi mở/đọc/đóng tài nguyên; không nuốt lỗi hoặc lộ file paths nhạy cảm qua log công khai.
- [ ] Có timeout/cancellation/backpressure riêng cho I/O hoặc feed liên tục, không chỉ `limit`.
- [ ] Không dùng mutable shared Supplier như nguồn sequence khi parallel.
- [ ] Tôn trọng encounter order hoặc chủ động bỏ nếu semantics cho phép.
- [ ] Đánh giá chi phí buffer của `sorted`/`distinct` và memory usage trước khi collect.
- [ ] Dùng API phù hợp phiên bản: bounded iterate và `takeWhile` có từ Java 9; các API Java 8 còn được hỗ trợ.
- [ ] Viết test ngăn regression về leak, source đã đóng sớm, nguồn không dừng và lỗi I/O trong traversal.
- [ ] Chọn JDK/tooling còn được bảo trì theo project policy; không dùng kỹ thuật đóng resource lỗi thời.

## 18. Bài tập có đáp án định hướng

**Bài 1 — Limit đơn giản.** `Stream.generate(() -> "x").limit(4).collect(toList())` tạo gì? **Đáp án:** `[x, x, x, x]`. Nêu rõ vì sao không cần tạo sẵn collection vô hạn.

**Bài 2 — Input budget khác output limit.** Với `Stream.iterate(1,n->n+1)`, thử `filter(n->n%100==0).limit(2)`. Đáp án là `[100,200]`; để lấy 2 outputs cần xét ít nhất đến 200 trong tuần tự. Thêm `limit(150)` trước filter thì chỉ có `[100]`.

**Bài 3 — Filter không kết thúc.** Vì sao `Stream.generate(()->1).filter(n->n==2).limit(1).collect(toList())` không nên chạy? Vì nguồn mãi sinh 1, filter không cho phần tử nào qua.

**Bài 4 — Distinct hiếm.** Vì sao `Stream.generate(()->"A").distinct().limit(2)` không hoàn tất? Vì chỉ có một giá trị unique, không có giá trị thứ hai.

**Bài 5 — Sort.** Đổi thứ tự `Stream.iterate(1,n->n+1).sorted().limit(5)` thành `limit(5).sorted()`. Giải thích tại sao bản sau có thể hoàn tất.

**Bài 6 — Predicate hữu hạn.** `Stream.iterate(0,n->n<5,n->n+1)` (Java 9+) cho `[0,1,2,3,4]`; giải thích seed được kiểm trước khi emit và không có 5.

**Bài 7 — Short-circuit terminal.** `Stream.iterate(0,n->n+1).anyMatch(n->n==3)` là true. Thay predicate thành điều kiện không bao giờ đúng trên nguồn bất biến toàn 1 để thấy nguy cơ không kết thúc.

**Bài 8 — Files.lines.** Viết `try (Stream<String> lines = Files.lines(path))` kết hợp `filter`/`findFirst`. Trả `Optional<String>` từ method khi đã đóng stream; không trả `lines` sau scope.

**Bài 9 — Close handler.** Tạo `AtomicBoolean closed`, gắn `onClose` cho stream, chạy `count` rồi kiểm `closed` trong block TWR và sau block. Đáp án: terminal không mặc nhiên gọi handler; sau TWR `closed==true`.

**Bài 10 — Files.walk.** Tạo temp directory có vài file, gọi `Files.walk(root,2)` trong TWR, tính số file regular. Kiểm không leak directory handle, và dọn temp tree đúng cách.

**Bài 11 — Lỗi I/O.** Thiết kế test để nguồn bị lỗi khi traversal, kiểm `UncheckedIOException` và resource close. Không khẳng định `Files.lines` đã đọc toàn file ngay tại lúc mở.

**Bài 12 — API server.** Một endpoint cần tối đa 50 kết quả, nhưng nguồn có thể có hàng triệu phần tử không phù hợp. Thiết kế output limit, input attempt cap, deadline và error response có nghĩa. Vì sao chỉ thêm `limit(50)` sau filter là chưa đủ?

**Bài 13 — Parallel.** So sánh `IntStream.range(0,1000).parallel().limit(3)` với `Stream.generate(counter::incrementAndGet).parallel().limit(3)`. Đáp án: range có order/semantics khoảng; generate unordered và shared counter không định nghĩa “ba giá trị đầu”.

**Bài 14 — DB cursor.** Nếu repository trả stream từ một query còn mở transaction, xác định ai đóng stream, khi nào transaction kết thúc, và test với short-circuit. Không trả stream ra ngoài transaction scope đã đóng.

**Bài 15 — Stream vs reactive.** Một feed không có hồi kết và producer nhanh hơn consumer. Giải thích tại sao Stream API `limit` không tự mang backpressure/cancel propagation. Đề xuất API phù hợp mà hệ thống hỗ trợ.

**Bài 16 — Review toàn diện.** Với pipeline `Files.lines(path).filter(expensivePredicate).limit(100).collect(toList())`, viết checklist cho file handle, biên input, CPU, timeout, PII logging, exception handling và test. Chứng minh `limit(100)` chỉ giới hạn output, không đảm bảo thời gian hoặc số dòng thực đọc.

**Tiêu chí đạt:** Bạn lý giải được vì sao **giới hạn output ≠ giới hạn input/time/memory**, phân biệt short-circuit với guarantee kết thúc, đặt `limit` đúng phía của stateful stages, dùng `try-with-resources` cho nguồn I/O và xác minh `onClose` chỉ chạy khi đóng. Chạy được ví dụ `BoundedSourcesDemo.java` với **10 dòng stdout**; nếu không có quyền tạo file tạm, cần điều chỉnh môi trường test thay vì bỏ kiểm resource lifecycle.

## 19. Tài liệu chính thức, kiến thức vẫn áp dụng

- **Java SE 25 Stream API:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- **Java SE 25 BaseStream.close / onClose / AutoCloseable:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html
- **Java SE 25 java.util.stream package summary:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- **Java SE 25 Files.lines / Files.walk / Files.list / Files.find:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
- **Java SE 25 java.nio.file.Path:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html
- **Java SE 25 AutoCloseable / try-with-resources:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html
- **Java SE 25 UncheckedIOException:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html
- **Dev.java — Stream API:** https://dev.java/learn/api/streams/

**Ghi nhớ:** Stream được tiêu thụ lazily nhưng **không tự bảo đảm hữu hạn**; `limit` không phải timeout hoặc backpressure. `Files.lines`/`Files.walk` có lifecycle của tài nguyên khác `List.stream()`; terminal kết thúc không đồng nghĩa nguồn đã đóng. Cách lập trình tin cậy là **giới hạn đầu vào/đầu ra/tài nguyên và đóng đúng owner**, kiểm thử cả kết quả, khả năng kết thúc, cancellation và resource cleanup trên JDK còn được bảo trì.