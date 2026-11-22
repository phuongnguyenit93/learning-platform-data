# Phân biệt stream I/O với `java.util.stream.Stream` trong Java

Trong Java, từ **stream** xuất hiện ở hai nhóm API khác nhau. **I/O stream** là luồng đọc/ghi dữ liệu qua thiết bị, file, socket hoặc bộ nhớ; **`java.util.stream.Stream<T>`** là pipeline xử lý các phần tử theo phong cách khai báo. Chúng có thể kết hợp, nhưng không thay thế trực tiếp cho nhau. Bài này đặt trong phần **Tổng quan I/O** và tập trung vào cách chọn, dùng và quản lý hai loại stream.

## 1. Hai ý nghĩa của “stream”

**I/O stream — dữ liệu đi qua một kênh đọc/ghi**

- `java.io.InputStream` đọc **byte**; `java.io.OutputStream` ghi **byte**.
- `java.io.Reader` đọc **ký tự**; `java.io.Writer` ghi **ký tự**. Khi đổi giữa byte và ký tự, cần xác định mã hóa như UTF-8.
- Nguồn/đích có thể là file (`FileInputStream`), bộ nhớ (`ByteArrayInputStream`), kết nối mạng hoặc một luồng I/O khác được bọc thêm (`BufferedInputStream`, `InputStreamReader`).
- Các lệnh như `read()`, `write()`, `flush()` trực tiếp thực hiện hoặc yêu cầu hoạt động I/O. Đọc tiến dần theo vị trí hiện tại; kết thúc luồng đọc thường biểu thị bằng `-1`. Nhiều thao tác có thể chặn luồng thực thi và ném `IOException`.
- Phần lớn tài nguyên I/O cần `close()` đúng lúc. `try-with-resources` giúp đóng cả khi có ngoại lệ.

**Stream API — tập hợp các phép biến đổi/tiêu thụ phần tử**

- `java.util.stream.Stream<T>` biểu diễn pipeline trên các **đối tượng kiểu `T`**, ví dụ `Stream<String>`; `IntStream`, `LongStream`, `DoubleStream` chuyên cho kiểu nguyên thủy.
- Nguồn có thể là `Collection.stream()`, `Arrays.stream()`, `Stream.of()`, bộ sinh phần tử, hoặc API đọc dữ liệu như `Files.lines()`.
- Các thao tác trung gian như `filter`, `map`, `distinct` tạo pipeline; thao tác kết thúc như `toList`, `count`, `reduce`, `forEach` kích hoạt tiêu thụ dữ liệu.
- Pipeline thông thường **lazy**: định nghĩa thao tác trung gian chưa xử lý ngay phần tử. Stream là luồng sử dụng một lần; không chạy lại cùng pipeline sau terminal operation.
- Stream API có thể xử lý tuần tự hay song song, nhưng song song **không** tự động làm I/O nhanh hơn.

> Phân biệt tên đầy đủ khi giải thích hoặc import: `java.io.InputStream` / `java.io.OutputStream` thuộc I/O; `java.util.stream.Stream` thuộc Stream API. `Reader`/`Writer` cũng là I/O dù tên không chứa “Stream”.

## 2. Bảng so sánh trực tiếp

| Tiêu chí | I/O stream (`InputStream`, `OutputStream`, `Reader`, `Writer`) | `java.util.stream.Stream<T>` |
|---|---|---|
| Câu hỏi nó giải quyết | Dữ liệu được **đọc từ đâu, ghi đi đâu, bằng cách nào**? | Phần tử được **lọc, chuyển đổi, tổng hợp thế nào**? |
| Đơn vị chính | Byte hoặc ký tự | Phần tử đối tượng (`T`) hoặc primitive stream |
| Hướng xử lý | Đọc/ghi qua nguồn hoặc đích cụ thể | Luồng phần tử chạy từ nguồn qua pipeline đến kết quả |
| API đặc trưng | `read`, `write`, `flush`, `close` | `filter`, `map`, `sorted`, `collect`, `toList`, `count` |
| Thời điểm làm việc | Thao tác đọc/ghi diễn ra khi gọi phương thức; có thể block | Intermediate operations thường lazy, terminal operation mới kích hoạt |
| Ngoại lệ | Thường dùng `IOException` (checked) | Các thao tác thông thường không khai báo `IOException`; nguồn dựa trên I/O có thể phát sinh `UncheckedIOException` khi duyệt |
| Tài nguyên | File descriptor, socket, buffer… có thể cần đóng | Stream từ collection thường không giữ tài nguyên ngoài; Stream dựa trên file có thể cần đóng |
| Dùng lại | Đọc làm tiến vị trí; có loại hỗ trợ `mark/reset` hoặc mở lại nguồn | Không tái sử dụng sau terminal; cần tạo Stream mới |
| Parallel | Tự bản thân I/O stream không cung cấp pipeline `parallel()` | Có `parallel()` nhưng phải xét tính đúng, thứ tự, chi phí và nguồn dữ liệu |
| Kết quả | Byte/ký tự đã đọc, hoặc hiệu ứng ghi ra đích | Giá trị tổng hợp, collection, phần tử tùy terminal operation |

Cả hai đều có tính **đọc dần** trong nhiều trường hợp, nhưng “lazy” ở Stream API nói về **lúc chạy các phép biến đổi**, không có nghĩa chỉ Stream API mới tiết kiệm bộ nhớ hay mới hỗ trợ đọc theo từng phần.

## 3. Ví dụ 1 — cùng chữ “stream”, hai công việc khác nhau

Tệp `StreamKindsDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StreamKindsDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "abc".getBytes(StandardCharsets.UTF_8);

        // I/O: đọc byte từ một nguồn.
        try (InputStream input = new ByteArrayInputStream(data)) {
            System.out.println((char) input.read());
            System.out.println(
                    new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }

        // Stream API: xử lý các phần tử của một List.
        List<String> chosen = List.of("An", "Binh", "Chi").stream()
                .filter(name -> name.length() >= 3)
                .map(String::toUpperCase)
                .toList();
        System.out.println(chosen);
    }
}
```

Chạy:

```bash
javac --release 17 StreamKindsDemo.java
java StreamKindsDemo
```

Kết quả:

```text
a
bc
[BINH, CHI]
```

Ở phần đầu, `read()` lấy byte đầu tiên (`'a'`); `readAllBytes()` lấy **phần còn lại** (`"bc"`), không tự quay về đầu. `ByteArrayInputStream` là I/O stream nhưng đọc trong bộ nhớ, vì thế “I/O” không đồng nghĩa mọi lần đọc đều truy cập đĩa hoặc mạng.

Ở phần sau, `List.stream()` tạo `Stream<String>`, `filter` giữ tên dài ít nhất ba ký tự, `map` viết hoa và `toList()` tạo kết quả. Pipeline không đọc byte từ thiết bị; nó xử lý các đối tượng đã có trong `List`. Danh sách trả về bởi `Stream.toList()` là **không thể chỉnh sửa cấu trúc** (unmodifiable), từ Java 16.

## 4. Lazy pipeline và cơ chế tiêu thụ một lần

Ví dụ `LazyPipelineDemo.java` (Java 17+):

```java
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        Stream<String> pipeline = Stream.of("a", "bb", "ccc")
                .map(value -> {
                    System.out.println("map:" + value);
                    return value.toUpperCase();
                })
                .filter(value -> value.length() >= 2);

        System.out.println("Built pipeline");
        System.out.println(pipeline.toList());
    }
}
```

```bash
javac --release 17 LazyPipelineDemo.java
java LazyPipelineDemo
```

```text
Built pipeline
map:a
map:bb
map:ccc
[BB, CCC]
```

`map` và `filter` chỉ dựng pipeline; gọi `toList()` mới khiến các phần tử đi qua pipeline. Thứ tự tác vụ có thể khác nếu đổi cách xây dựng pipeline, dùng phép tối ưu hoặc chạy song song. Lệnh in trong `map` ở đây chỉ để minh họa thời điểm thực thi; trong chương trình thực tế, hạn chế dựa vào side effect của intermediate operation.

**Điểm dễ nhầm:** `Stream<T>` không phải một “túi chứa” có thể duyệt đi duyệt lại:

```java
Stream<String> oneShot = Stream.of("A", "B");
long count = oneShot.count();       // Hợp lệ
// oneShot.toList();                // IllegalStateException: stream đã được dùng
```

Đoạn trên là **minh họa**, không phải chương trình độc lập. Sau `count()`, nếu cần tính tiếp, hãy tạo stream mới từ nguồn. Tương tự, `parallel()` chỉ đổi cách thực thi pipeline; nó không biến I/O stream thành Stream API và không cho phép dùng lại stream đã tiêu thụ.

## 5. Khi hai API kết hợp: đọc file và lọc các dòng

Một file thường lưu **byte**. `Files.lines(path, charset)` tạo ra `Stream<String>`: phần I/O đọc và giải mã dữ liệu, còn Stream API cung cấp `filter`/`count`. Đây là **cầu nối** giữa hai khái niệm.

Tệp `FileLinesDemo.java` (Java 17+; tự tạo và dọn file tạm):

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-stream-demo-", ".txt");
        try {
            Files.writeString(file, "Java\nI/O\nStream\n",
                    StandardCharsets.UTF_8);

            // Stream API đọc các dòng từ nguồn I/O: phải đóng Stream.
            try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
                long count = lines.filter(line -> line.length() >= 4).count();
                System.out.println("Long lines: " + count);
            }

            // I/O Reader: tự đọc tuần tự từng dòng.
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                System.out.println("First: " + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 FileLinesDemo.java
java FileLinesDemo
```

```text
Long lines: 2
First: Java
```

Giải thích:

1. `Files.writeString` ghi văn bản UTF-8; ký hiệu `\n` trong chuỗi Java tạo xuống dòng.
2. `Files.lines` tạo một `Stream<String>` đọc dòng theo nhu cầu khi terminal operation chạy. `filter` giữ `"Java"` và `"Stream"`; `count` in `2`.
3. `try-with-resources` đóng stream từ `Files.lines`, nhờ đó tài nguyên file liên quan được giải phóng kể cả khi pipeline lỗi. Terminal operation như `count()` **không có nghĩa** tự đóng stream.
4. `Files.newBufferedReader` trả về `BufferedReader`; `readLine()` tự đọc dòng đầu. Reader cũng được đóng bằng `try-with-resources`.
5. Khối `finally` xóa file tạm sau khi cả stream và reader đã đóng. Nếu thao tác dọn file lỗi, `deleteIfExists` có thể ném `IOException`.

Cú pháp `BufferedReader.lines()` cũng trả ra `Stream<String>`, nhưng bạn vẫn phải quản lý **`BufferedReader` đã tạo ra stream đó**. Đừng mặc định chỉ đóng Stream trả về bởi `reader.lines()` là đã đóng reader. Ví dụ khi reader do bạn mở:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long total = reader.lines().filter(s -> !s.isBlank()).count();
    System.out.println(total);
}
```

Đoạn này là **mẫu minh họa**: `path` phải là một `Path` hợp lệ, và nơi gọi phải xử lý/khai báo `IOException`. Reader còn mở trong lúc terminal operation chạy. `Files.lines` và `BufferedReader.lines` không đảm bảo tải toàn bộ file vào bộ nhớ; dù vậy, các phép biến đổi có trạng thái như `sorted` hoặc terminal operation như `toList` vẫn có thể gom nhiều phần tử vào bộ nhớ.

## 6. Chọn API theo yêu cầu thực tế

**Cần sao chép, đọc/ghi dữ liệu thô, truyền qua socket, hoặc xử lý định dạng nhị phân:** dùng `InputStream`/`OutputStream`, hoặc `Files.copy` khi phù hợp. Làm việc với byte thì không áp dụng `filter` hay `map` trực tiếp lên `InputStream`; nếu cần pipeline, phải chuyển thành nguồn phần tử có ý nghĩa và cân nhắc chi phí.

**Cần đọc/ghi văn bản:** dùng `Reader`/`Writer` và đặt `Charset` rõ ràng khi chuyển đổi byte ↔ ký tự. Ví dụ `Files.newBufferedReader(path, UTF_8)` để đọc từng dòng, `Files.newBufferedWriter` để ghi chuỗi. Đừng biến một byte bất kỳ thành `char` rồi kỳ vọng đúng Unicode; ví dụ 1 chỉ làm vậy vì byte `'a'` thuộc ASCII.

**Cần lọc/biến đổi/tổng hợp dữ liệu đã có:** chọn `Stream<T>` từ `Collection`/mảng/nguồn phát sinh phần tử. Với thao tác đơn giản, vòng lặp truyền thống có thể dễ hiểu và tiết kiệm overhead hơn.

**Cần đọc file văn bản và xử lý từng dòng:** `Files.lines(path, UTF_8)` kết hợp I/O và Stream API; đóng stream trong `try-with-resources`. Nếu cần tự kiểm soát cách đọc, xử lý luồng ký tự, hoặc đọc luân phiên từng dòng theo quy trình trạng thái, `BufferedReader.readLine()` là lựa chọn trực tiếp.

**File nhỏ hay lớn?** `Files.readAllLines` đọc toàn bộ các dòng thành `List<String>`; thuận tiện khi dữ liệu vừa bộ nhớ. `Files.lines` hỗ trợ xử lý dần theo pipeline, thường giảm bộ nhớ với các phép lọc/tổng hợp streaming, nhưng không tự giải quyết mọi bài toán bộ nhớ (ví dụ `sorted().toList()` phải giữ dữ liệu đáng kể).

## 7. Những sai lầm thường gặp

1. **Gọi nhầm phương thức:** `InputStream` không có `map`/`filter`; `Stream<String>` không có `read()`/`write()` như I/O stream. Hai API khác mục đích và kiểu dữ liệu.
2. **Bỏ qua mã hóa:** đọc byte rồi chuyển thẳng sang chữ bằng charset mặc định có thể hỏng tiếng Việt. Với dữ liệu văn bản, nêu rõ `StandardCharsets.UTF_8` ở hai phía khi cần.
3. **Quên đóng nguồn I/O:** dùng `Files.lines` nhưng chỉ gọi `count()`/`toList()`, rồi quên `close()`. Giữ `try-with-resources` quanh stream gắn với file. Với reader do mình mở, đóng reader.
4. **Cho rằng mọi Stream phải đóng:** `Stream.of(...)` và `list.stream()` thông thường không giữ tài nguyên hệ điều hành. Mặc dù `Stream` kế thừa `AutoCloseable`, nhu cầu đóng phụ thuộc **nguồn**; `try-with-resources` vẫn hợp lệ nhưng không thường cần cho stream trong bộ nhớ.
5. **Giả định `readAllBytes()` luôn tốt:** nó lưu toàn bộ byte còn lại trong một mảng; dữ liệu lớn nên cân nhắc xử lý theo khối, `transferTo`, hay API xử lý trực tiếp.
6. **Dùng lại Stream sau terminal:** muốn chạy `count` và `toList` độc lập thì tạo hai stream mới, hoặc thu dữ liệu trước nếu giới hạn bộ nhớ cho phép.
7. **Coi Stream API luôn nhanh hơn:** xây pipeline có overhead; `parallel()` có thể làm giảm hiệu năng hoặc gây tranh chấp ở nguồn I/O. Đo hiệu năng theo dữ liệu thực tế trước khi tối ưu.
8. **Không hiểu ranh giới ngoại lệ:** các phương thức I/O như `Files.lines`/`readLine` thường khai báo `IOException`; lỗi đọc khi đang duyệt stream dựa trên file có thể xuất hiện ở runtime dưới dạng `UncheckedIOException`. Xử lý tại đúng biên I/O; đừng nuốt lỗi.
9. **Lạm dụng side effect và trật tự:** `forEach` trên parallel stream không đảm bảo thứ tự gặp phần tử; nếu thứ tự quan trọng, xem `forEachOrdered` hoặc xử lý tuần tự. Dùng `map`/`filter` chủ yếu cho hàm biến đổi và điều kiện thuần.

## 8. Checklist ghi nhớ

- Đang **truyền/đọc/ghi byte hoặc ký tự**? Nghĩ tới `java.io` và `java.nio.file`.
- Đang **xử lý chuỗi phần tử**? Nghĩ tới `java.util.stream`.
- Đang đọc từ file qua `Files.lines`? **Cả hai** cùng xuất hiện: I/O cung cấp phần tử, Stream API xử lý phần tử.
- Có file/socket/reader mở? Xác định **ai sở hữu và ai đóng** tài nguyên.
- Có terminal operation? Pipeline đã bị tiêu thụ; muốn chạy lại phải tạo Stream mới.

**Kết luận:** “stream” trong I/O nói về **dòng dữ liệu đi qua điểm đọc/ghi**; “stream” trong Stream API nói về **pipeline xử lý phần tử**. Khi kết hợp chúng, chọn API theo dạng dữ liệu, kiểm soát ngoại lệ và đóng tài nguyên tại đúng ranh giới.

### Tài liệu tra cứu (Java SE 17)

- [`java.io.InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`Reader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [`java.util.stream.Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [`Files.lines` và các tiện ích `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`BufferedReader.lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
