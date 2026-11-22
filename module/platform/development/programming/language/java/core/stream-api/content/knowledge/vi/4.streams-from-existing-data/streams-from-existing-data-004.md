# Dựng nguồn dữ liệu bằng `Stream.Builder`

> **Chương:** Tạo Stream từ dữ liệu có sẵn  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu theo lối khai báo bằng Java Stream API, từ pipeline lazy và `filter`, `map`, `reduce`, `collect` đến grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers.

Khi các phần tử đã nằm trong một `List` hoặc mảng, ta có thể gọi `list.stream()` hoặc `Arrays.stream(array)`. Nhưng đôi khi **nguồn dữ liệu cần được lắp ghép từng phần tử**, chẳng hạn thông điệp phản hồi được tạo từ các nhánh điều kiện, chuỗi sự kiện nghiệp vụ hoặc một nhóm giá trị phát sinh trong quá trình xử lý.

`Stream.Builder<T>` cho phép xây dựng một Stream hữu hạn theo cách này: **thêm các phần tử trước, gọi `build()` một lần, rồi xử lý Stream nhận được bằng pipeline quen thuộc**.

## 1. `Stream.Builder<T>` là gì?

`Stream.Builder<T>` là một giao diện lồng trong `java.util.stream.Stream`, được cung cấp từ Java 8. Nó mô tả bộ dựng có thể nhận từng phần tử kiểu `T` để tạo một `Stream<T>`. Ta lấy bộ dựng qua phương thức tĩnh `Stream.builder()`.

```java
import java.util.List;
import java.util.stream.Stream;

public class BuilderQuickStart {
    public static void main(String[] args) {
        Stream.Builder<String> builder = Stream.builder();

        builder.add("Java");
        builder.add("Stream");
        builder.accept("API");

        Stream<String> stream = builder.build();
        List<String> words = stream
                .map(String::toUpperCase)
                .toList(); // Java 16+

        System.out.println(words); // [JAVA, STREAM, API]
    }
}
```

Ví dụ thể hiện ba thao tác quan trọng:

- `add(T value)`: đưa một phần tử vào Builder và **trả về chính Builder**, phù hợp với cách gọi nối chuỗi.
- `accept(T value)`: đưa một phần tử vào Builder nhưng **trả về `void`**. Builder triển khai `Consumer<T>` nên có phương thức này.
- `build()`: hoàn tất việc xây dựng và **trả về một `Stream<T>` có thứ tự gặp phần tử đúng theo thứ tự đã thêm**.

`Builder` là đối tượng để **tạo nguồn**; `Stream` được trả về mới là đối tượng để gọi `filter`, `map`, `limit`, `collect`, v.v.

## 2. Vòng đời: từ thêm phần tử đến tiêu thụ Stream

```text
Stream.builder()
      │
      ▼
  Đang xây dựng ── add / accept ── add / accept ── ...
      │
      └────────────────── build() ────────────────┐
                                                 ▼
                                          Stream<T> đã tạo
                                                 │
                                          filter / map / ...
                                                 │
                                           terminal operation
                                                 │
                                                 ▼
                                         Kết quả / side effect
```

Có **hai vòng đời một lần** cần nhớ:

1. **Builder chỉ được `build()` một lần.** Sau lần gọi này, Builder chuyển sang trạng thái đã hoàn tất. Gọi tiếp `add()`, `accept()` hoặc `build()` trên cùng Builder sẽ ném `IllegalStateException`.
2. **Stream đã tạo cũng chỉ được tiêu thụ một lần.** Sau một terminal operation như `toList()`, `count()` hoặc `forEach()`, không thể mở lại pipeline trên cùng Stream; cần xây dựng một Stream mới nếu muốn xử lý lại.

Ví dụ minh họa thao tác **không hợp lệ**:

```java
Stream.Builder<String> builder = Stream.builder();
builder.add("first");

Stream<String> stream = builder.build();

// Sai: Builder đã ở trạng thái built.
// builder.add("second"); // IllegalStateException
// builder.build();       // IllegalStateException

System.out.println(stream.count()); // 1

// Sai: Stream đã bị tiêu thụ.
// stream.toList(); // IllegalStateException
```

Không cần tự tạo danh sách trung gian chỉ để chuyển sang Stream: Builder lưu các phần tử đã thêm và `build()` đưa chúng vào một Stream. Tuy vậy, Builder **vẫn phải giữ dữ liệu đã nhận**; không nên hiểu rằng nó cung cấp một nguồn vô hạn hay cơ chế phát từng phần tử khi cần.

## 3. Viết gọn với `add()` và khai báo kiểu `T`

Vì `add()` trả về `Builder<T>`, ta có thể ghép nhiều bước:

```java
Stream<String> languages = Stream.<String>builder()
        .add("Java")
        .add("Kotlin")
        .add("Scala")
        .build();

System.out.println(languages.toList());
// [Java, Kotlin, Scala]
```

Ở đây, `Stream.<String>builder()` chỉ rõ kiểu phần tử. Cách viết này hữu ích trong chuỗi lệnh dài vì trình biên dịch có thể suy ra kiểu quá rộng nếu chỉ dựa vào các lời gọi `add()`:

```java
// Cách rõ nghĩa khi dùng khai báo biến:
Stream.Builder<Integer> builder = Stream.builder();
builder.add(10).add(20);
Stream<Integer> numbers = builder.build();
```

Nếu cần chèn giá trị theo từng nhánh `if`, Builder đặt trong một biến thường dễ đọc hơn cách gọi nối chuỗi.

## 4. Ví dụ thực tế: ghép luồng sự kiện theo điều kiện

Giả sử cần tạo nhật ký trạng thái của một đơn hàng. Một số sự kiện luôn có; những sự kiện khác chỉ có khi điều kiện nghiệp vụ tương ứng đúng:

```java
import java.util.List;
import java.util.stream.Stream;

public class OrderEvents {
    static Stream<String> createEvents(
            boolean paymentConfirmed,
            boolean delivered) {

        Stream.Builder<String> builder = Stream.builder();

        builder.add("ORDER_CREATED");
        if (paymentConfirmed) {
            builder.add("PAYMENT_CONFIRMED");
        }
        if (delivered) {
            builder.add("DELIVERED");
        }
        builder.add("EVENTS_ASSEMBLED");

        return builder.build();
    }

    public static void main(String[] args) {
        List<String> events = createEvents(true, false)
                .filter(e -> !e.equals("EVENTS_ASSEMBLED"))
                .map(String::toLowerCase)
                .toList();

        System.out.println(events);
        // [order_created, payment_confirmed]
    }
}
```

Điểm cần chú ý:

- Các lệnh `add()` phản ánh rõ **điều kiện thêm phần tử** và **thứ tự phát sinh**.
- `createEvents` trả về `Stream<String>`, nên nơi gọi có thể tiếp tục áp dụng các phép toán trung gian và kết thúc.
- Mỗi lần gọi `createEvents(...)` tạo **Builder và Stream mới**, tránh tái sử dụng Builder đã hoàn tất.
- `build()` không tự tạo kết quả `List`: `toList()` ở phía gọi mới là terminal operation gom dữ liệu.

Khi điều kiện nghiệp vụ cần truy cập cơ sở dữ liệu hoặc tài nguyên khác, hãy xác định rõ thời điểm cần đọc dữ liệu và quản lý tài nguyên. Builder phù hợp để lắp ghép **các giá trị đã được xác định**, không thay thế cơ chế truy xuất tài nguyên theo yêu cầu.

## 5. Builder không làm mất tính lazy của pipeline

Một nhầm lẫn phổ biến là nghĩ `Stream.Builder` sẽ trì hoãn cả việc tính giá trị truyền vào `add()`. Thực tế:

- Biểu thức dùng để tính đối số của `add(...)` hoặc `accept(...)` được đánh giá **ngay lúc gọi**.
- `build()` kết thúc việc lắp ghép nguồn và tạo Stream; **nó không phải terminal operation** của Stream.
- Các bước trung gian như `map()` và `filter()` vẫn tuân theo cơ chế **lazy** của Stream: thường chỉ thực thi khi terminal operation được gọi, nếu không bị tối ưu loại bỏ.

```java
import java.util.stream.Stream;

Stream.Builder<Integer> builder = Stream.builder();

System.out.println("A: chuẩn bị nguồn");
builder.add(2 + 3);             // phép cộng được tính tại đây
builder.add(7);

Stream<Integer> pipeline = builder.build()
        .map(n -> {
            System.out.println("map: " + n);
            return n * 10;
        });

System.out.println("B: chưa chạy pipeline");
System.out.println(pipeline.toList());
```

Đầu ra:

```text
A: chuẩn bị nguồn
B: chưa chạy pipeline
map: 5
map: 7
[50, 70]
```

Không nên dùng Builder để mô phỏng nguồn vô hạn hoặc nguồn tạo từng giá trị theo nhu cầu. Khi muốn phát phần tử khi được duyệt, hãy cân nhắc `Stream.generate(...)`, `Stream.iterate(...)` hoặc `Spliterator` được thiết kế phù hợp.

## 6. Thứ tự phần tử và xử lý song song

Stream tạo bởi Builder là một **ordered Stream**: nó có *encounter order* đúng theo thứ tự `add`/`accept`. Ví dụ:

```java
List<Integer> result = Stream.<Integer>builder()
        .add(30)
        .add(10)
        .add(20)
        .build()
        .sorted()
        .toList();

// result = [10, 20, 30]
```

Trước `sorted()`, encounter order là `[30, 10, 20]`; sau đó thứ tự được quyết định bởi phép sắp xếp. Builder **không tự sắp xếp** hoặc tự loại phần tử trùng.

`build()` tạo Stream tuần tự. Có thể gọi `parallel()` trên Stream nếu bài toán phù hợp, nhưng cần phân biệt:

- **Giai đoạn thêm phần tử vào Builder:** thực hiện tuần tự theo chương trình của bạn; không được giả định Builder hỗ trợ nhiều luồng đồng thời gọi `add()`.
- **Giai đoạn xử lý Stream:** `parallel()` yêu cầu xử lý song song, nhưng không bảo đảm hiệu năng tốt hơn; các thao tác cần giữ thứ tự có thể phát sinh chi phí phối hợp.
- `forEach` trên Stream song song không bảo đảm thứ tự in ra. Nếu thứ tự quan trọng, dùng terminal operation giữ encounter order như `forEachOrdered` hoặc thu thập vào `toList()` khi nguồn còn ordered.

```java
Stream.<String>builder()
        .add("A")
        .add("B")
        .add("C")
        .build()
        .parallel()
        .forEachOrdered(System.out::println);

// A
// B
// C
```

Việc gọi `parallel()` diễn ra **sau** `build()`; không biến bản thân Builder thành công cụ nhập dữ liệu song song.

## 7. Builder rỗng, giá trị `null` và kiểu nguyên thủy

### Không thêm phần tử nào

Có thể tạo Stream rỗng:

```java
Stream<String> empty = Stream.<String>builder().build();
System.out.println(empty.count()); // 0
```

Nếu biết ngay từ đầu không có phần tử, `Stream.empty()` thường ngắn gọn và thể hiện ý định rõ hơn.

### Giá trị `null`

`Stream.Builder` có thể nhận `null` như một phần tử của reference Stream. Điều này **khác** với việc bỏ qua phần tử:

```java
List<String> values = Stream.<String>builder()
        .add("ok")
        .add(null)
        .add("done")
        .build()
        .toList();

// values = [ok, null, done]
```

Một số phép toán phía sau có thể lỗi nếu không xử lý `null`; chẳng hạn `map(String::length)` sẽ ném `NullPointerException` khi gặp `null`. Nếu muốn bỏ `null`, có thể dùng `filter(java.util.Objects::nonNull)`. Với **một** giá trị có thể `null`, `Stream.ofNullable(value)` (Java 9+) tạo Stream rỗng khi giá trị đó là `null`.

### Builder cho primitive Stream

Ngoài `Stream.Builder<T>`, Java còn có `IntStream.Builder`, `LongStream.Builder` và `DoubleStream.Builder`. Các loại này phù hợp khi lưu số nguyên hoặc số thực nguyên thủy, giúp tránh boxing thành `Integer`, `Long` hoặc `Double` không cần thiết:

```java
import java.util.stream.IntStream;

IntStream.Builder builder = IntStream.builder();
builder.add(10).add(20).accept(30);

int sum = builder.build().sum();
System.out.println(sum); // 60
```

Chúng cũng tuân theo vòng đời: thêm phần tử trước, `build()` một lần, sau đó tiêu thụ Stream kết quả.

## 8. Khi nào dùng Builder, khi nào chọn cách tạo Stream khác?

| Tình huống | Cách phù hợp | Lý do |
| --- | --- | --- |
| Có sẵn một `List`, `Set` hoặc collection | `collection.stream()` | Dùng trực tiếp nguồn có sẵn. |
| Có sẵn một mảng | `Arrays.stream(array)` | Không cần chép phần tử sang Builder. |
| Biết trước một vài giá trị cố định | `Stream.of(a, b, c)` | Gọn và dễ đọc. |
| Có đúng một giá trị có thể `null` | `Stream.ofNullable(value)` | Trả về 0 hoặc 1 phần tử. |
| Ghép các phần tử phát sinh ở nhiều nhánh điều kiện | `Stream.Builder<T>` | Thêm phần tử linh hoạt, duy trì thứ tự. |
| Cần nối hai Stream có sẵn | `Stream.concat(first, second)` | Ghép hai nguồn Stream đã tồn tại. |
| Cần sinh phần tử theo yêu cầu, có thể vô hạn | `Stream.generate(...)` / `Stream.iterate(...)` | Tạo giá trị lúc duyệt thay vì lưu trước toàn bộ. |
| Cần nguồn tùy chỉnh cho file, iterator hoặc chia tách song song | `Spliterator` và `StreamSupport.stream(...)` | Kiểm soát cơ chế duyệt và đặc tính nguồn. |

Ví dụ, khi dữ liệu **đã có trong List**:

```java
List<String> input = List.of("Java", "Stream", "API");
List<String> upper = input.stream()
        .map(String::toUpperCase)
        .toList();
```

Không cần tạo một Builder mới rồi duyệt `input` để `add` từng phần tử: cách đó phải chuẩn bị thêm một bộ chứa mà không đem lại lợi ích trong tình huống đơn giản này.

Ngược lại, Builder là lựa chọn rõ ràng khi phần tử đến từ **các biểu thức hoặc điều kiện khác nhau**:

```java
Stream.Builder<String> messages = Stream.builder();
messages.add("Bắt đầu xử lý");
if (hasWarnings) {
    messages.add("Có cảnh báo cần kiểm tra");
}
if (isComplete) {
    messages.add("Hoàn tất");
}

List<String> response = messages.build().toList();
```

Nếu cần giữ một bộ dữ liệu có thể sửa đổi, truy cập nhiều lần hoặc chia sẻ lâu dài, hãy dùng collection phù hợp thay vì Builder vì Builder **không hỗ trợ thêm phần tử sau `build()`**.

## 9. Giới hạn tài nguyên và lỗi thường gặp

### 9.1. Dùng Builder cho khối lượng dữ liệu rất lớn

Mỗi giá trị được đưa vào Builder trước khi Stream được tạo. Như vậy, Builder không đem lại khả năng streaming theo nghĩa **đọc bao nhiêu xử lý bấy nhiêu từ một nguồn lớn**. Nếu hàng triệu bản ghi nằm sẵn trong collection, gọi `collection.stream()` thường tự nhiên hơn; nếu dữ liệu được đọc từng phần từ một nguồn ngoại vi, cần cơ chế duyệt lazy và quản lý tài nguyên thích hợp.

### 9.2. Tưởng `build()` là `collect()`

`build()` chỉ hoàn tất nguồn và trả về Stream. Để có `List`, `Set`, bản đồ theo nhóm hoặc giá trị tổng hợp, vẫn cần terminal operation:

```java
List<String> result = Stream.<String>builder()
        .add("blue")
        .add("green")
        .build()
        .filter(color -> color.length() > 4)
        .toList();

// [green]
```

### 9.3. Tái sử dụng Builder hoặc Stream sau khi đã dùng

Đây là lỗi vòng đời, không phải lỗi đồng bộ hay lỗi biên dịch. Hãy tạo Builder mới cho một lượt lắp ghép mới, và gọi `build()` đúng một lần.

### 9.4. Dùng Builder làm nơi tích lũy kết quả trong `parallelStream()`

Không nên đưa một Builder dùng chung vào `forEach` của pipeline song song:

```java
Stream.Builder<String> shared = Stream.builder();

// Không nên: nhiều luồng có thể cùng gọi add trên Builder.
// names.parallelStream().forEach(shared::add);
```

Builder không được thiết kế làm bộ tích lũy dùng chung giữa nhiều luồng. Nếu mục tiêu là thu thập kết quả, hãy dùng terminal operation `collect` với Collector phù hợp, ví dụ `Collectors.toList()` hoặc `groupingBy(...)`. Nếu mục tiêu là tạo một nguồn Stream từ thuật toán tùy chỉnh, hãy thiết kế nguồn hoặc `Spliterator` phù hợp.

### 9.5. Giữ tài nguyên mở sau khi tạo nguồn

Builder bản thân không đọc hoặc đóng file, socket, kết nối cơ sở dữ liệu. Nếu lấy các phần tử từ nguồn có tài nguyên cần đóng **trong lúc lắp ghép**, hãy quản lý chúng ở nơi đọc dữ liệu (ví dụ `try-with-resources`). Đừng mặc định rằng `build()` hoặc terminal operation sẽ tự giải phóng các tài nguyên bên ngoài.

## 10. Bài tập tự kiểm tra

**Bài 1 — Dự đoán kết quả.** Đoạn code sau in gì?

```java
List<Integer> result = Stream.<Integer>builder()
        .add(3)
        .add(1)
        .add(3)
        .add(2)
        .build()
        .distinct()
        .sorted()
        .toList();
```

**Đáp án:** `[1, 2, 3]`. Builder giữ các phần tử `[3, 1, 3, 2]` đúng thứ tự thêm; `distinct` bỏ trùng, `sorted` sắp xếp tăng dần.

**Bài 2 — Vòng đời.** Sau `Stream<String> s = builder.build();`, có được gọi `builder.add("x")` để bổ sung vào `s` không?

**Đáp án:** Không. Builder đã vào trạng thái built; thao tác sẽ ném `IllegalStateException`. Cần thêm toàn bộ phần tử trước khi `build()`.

**Bài 3 — Lazy.** Cho `builder.add(expensiveCalculation())`, phép tính có trì hoãn đến khi gọi `toList()` không?

**Đáp án:** Không. Biểu thức đối số được tính khi gọi `add()`. Các phép toán trung gian được tạo trên Stream sau `build()` mới thường thực hiện lazy.

**Bài 4 — Chọn công cụ.** Muốn chuyển toàn bộ phần tử từ một `List<String>` thành chữ hoa, có cần dùng Builder không?

**Đáp án:** Không. Chỉ cần `list.stream().map(String::toUpperCase).toList()`. Builder hữu ích hơn khi phải thêm linh hoạt nhiều phần tử độc lập trước khi có nguồn Stream.

## Ghi nhớ

- `Stream.Builder<T>` dùng để **lắp ghép một nguồn Stream hữu hạn**, theo thứ tự thêm phần tử, với `add` hoặc `accept`.
- `add` trả về Builder để gọi nối chuỗi; `accept` trả về `void`; `build` trả về một **ordered Stream tuần tự**.
- **Builder chỉ `build()` một lần; Stream cũng chỉ tiêu thụ một lần**. Gọi thêm thao tác trên Builder đã hoàn tất sẽ gặp `IllegalStateException`.
- Giá trị truyền vào `add` được tạo **ngay khi thêm**; pipeline trên Stream kết quả vẫn có thể thực thi **lazy**.
- Với nguồn có sẵn, ưu tiên `collection.stream()` hoặc `Arrays.stream(...)`; với nguồn sinh lười hoặc quy mô lớn, chọn `generate`, `iterate` hoặc `Spliterator` tùy trường hợp. Không dùng Builder chung để gom kết quả của nhiều luồng song song.
