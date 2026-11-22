# Đăng ký xử lý đóng bằng `onClose` trong Java Stream API

Khi xử lý dữ liệu với Java Stream API, một pipeline thường gồm **nguồn dữ liệu → các thao tác trung gian → thao tác kết thúc**. Tuy nhiên, việc hoàn tất một thao tác kết thúc như `count()`, `collect()` hay `forEach()` **không đồng nghĩa với việc đóng stream**. Điều này đặc biệt quan trọng khi nguồn dữ liệu giữ tài nguyên hệ thống, chẳng hạn tệp được đọc qua `Files.lines()`.

`onClose(Runnable)` cho phép đăng ký một công việc sẽ được thực hiện **khi stream được đóng**. Kết hợp `onClose` với `try-with-resources` giúp việc giải phóng tài nguyên, ghi log và dọn dẹp trở nên rõ ràng, ngay cả khi xử lý gặp ngoại lệ.

## 1. `onClose` làm gì trong vòng đời stream?

`Stream<T>` kế thừa phương thức từ `BaseStream<T, S>`:

~~~java
S onClose(Runnable closeHandler);
~~~

Phương thức này trả về một stream tương đương, có thêm một **close handler** (hàm xử lý khi đóng). Đây không phải thao tác kết thúc; gọi `onClose` không duyệt phần tử, không đóng nguồn và không lập tức chạy handler.

Một pipeline có hai mốc cần phân biệt:

1. **Thực thi pipeline:** thao tác kết thúc yêu cầu lấy dữ liệu từ nguồn và xử lý các phần tử cần thiết.
2. **Đóng pipeline:** gọi `close()` (trực tiếp hoặc thông qua `try-with-resources`), từ đó kích hoạt các handler đã đăng ký.

~~~text
Stream nguồn ── filter/map/... ── count()/collect()/...  [xử lý dữ liệu]
      │
      └── onClose(handler A) ── onClose(handler B)
                    │                  │
                    └──── close() ─────┘               [dọn dẹp]
~~~

Không phải stream nào cũng cần đóng: với nguồn dữ liệu trong bộ nhớ như `Stream.of(...)` hoặc `list.stream()`, thường không có tài nguyên bên ngoài cần giải phóng. Ngược lại, stream đọc dữ liệu từ tệp có thể sở hữu tài nguyên I/O cần được đóng đúng lúc. `onClose` là điểm mở rộng của bước đóng, **không thay thế hành động gọi `close()`**.

## 2. Ví dụ cơ bản: handler chỉ chạy khi đóng

~~~java
import java.util.stream.Stream;

public class OnCloseDemo {
    public static void main(String[] args) {
        try (Stream<String> names = Stream.of("An", "Binh", "Chi")
                .filter(name -> name.length() >= 3)
                .onClose(() -> System.out.println("Da dong stream"))) {

            long count = names.count();
            System.out.println("So ten hop le: " + count);
            System.out.println("Da thuc thi terminal operation");
        }
    }
}
~~~

Kết quả:

~~~text
So ten hop le: 2
Da thuc thi terminal operation
Da dong stream
~~~

Handler được gọi sau khi rời khối `try`, bởi `try-with-resources` tự động gọi `close()` trên đối tượng `names`. Nếu bỏ `try-with-resources` và không gọi `close()`, lời gọi `count()` vẫn tính xong nhưng không tự kích hoạt handler.

Đăng ký `onClose` **trước** thao tác kết thúc. Stream không được dùng lại sau khi đã chạy thao tác kết thúc; việc cố tạo pipeline mới trên stream đã tiêu thụ có thể ném `IllegalStateException`.

## 3. Trường hợp quan trọng: đọc tệp bằng `Files.lines()`

`Files.lines(Path, Charset)` tạo stream các dòng văn bản. Dữ liệu được đọc khi pipeline yêu cầu, và stream này giữ tài nguyên I/O trong quá trình sử dụng. Cách triển khai an toàn là khai báo stream trong `try-with-resources`.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class CountErrorLines {
    public static void main(String[] args) throws IOException {
        Path logFile = Paths.get("application.log");

        try (Stream<String> errorLines = Files.lines(logFile, StandardCharsets.UTF_8)
                .filter(line -> line.contains("ERROR"))
                .onClose(() -> System.out.println("Da dong stream doc log"))) {

            long errorCount = errorLines.count();
            System.out.println("So dong ERROR: " + errorCount);
        }
    }
}
~~~

Trong ví dụ này:

- `Files.lines(...)` mở nguồn I/O và cài đặt cơ chế đóng nguồn khi stream đóng.
- `filter(...)` chọn những dòng chứa `ERROR` mà không cần nạp toàn bộ tệp vào một danh sách.
- `onClose(...)` thêm hành động ghi nhận quá trình đóng; nó không phải nơi thực hiện việc đọc hoặc lọc.
- Khi rời `try` (kể cả khi xảy ra ngoại lệ), `close()` được gọi; cơ chế đóng của `Files.lines` và handler bổ sung đều được thực hiện.

Việc mở tệp có thể ném `IOException`. Lỗi I/O xảy ra trong lúc stream đang được duyệt có thể xuất hiện dưới dạng `UncheckedIOException`; cần xử lý theo chính sách lỗi của ứng dụng. `onClose` không tự bắt hoặc bỏ qua những lỗi này.

**Quy tắc sở hữu:** thành phần tạo ra stream gắn với tài nguyên phải bảo đảm có người chịu trách nhiệm đóng nó. Nếu phương thức trả stream cho bên gọi, hãy quy định rõ bên gọi phải dùng `try-with-resources`.

## 4. Gắn `onClose` để đóng tài nguyên tự quản lý

Không phải mọi nguồn dữ liệu đều tự gắn hành động đóng. Ví dụ, `BufferedReader.lines()` tạo stream từ một reader, nhưng việc đóng stream đó không tự bảo đảm reader được đóng. Ta có thể nối vòng đời của chúng bằng `onClose`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class ReaderStreams {
    public static Stream<String> openLines(Path path) throws IOException {
        BufferedReader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8);

        return reader.lines().onClose(() -> {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new UncheckedIOException("Khong the dong reader", ex);
            }
        });
    }

    public static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = openLines(path)) {
            return lines.filter(line -> !line.trim().isEmpty()).count();
        }
    }
}
~~~

Ở đây, `reader.lines()` cung cấp các dòng; close handler chịu trách nhiệm gọi `reader.close()`. Vì `Runnable.run()` không khai báo checked exception, handler phải xử lý `IOException` tại chỗ hoặc chuyển thành `UncheckedIOException` để báo lỗi cho bên gọi. Bên gọi `openLines` vẫn **phải đóng stream** thì handler mới chạy.

Nếu chỉ cần đọc tệp theo từng dòng, ưu tiên `Files.lines(...)` để sử dụng trực tiếp cơ chế quản lý tài nguyên sẵn có. Cách tự gắn `onClose` thích hợp khi xây dựng nguồn stream từ một tài nguyên do ứng dụng chủ động quản lý.

## 5. Nhiều close handler: thứ tự và ngoại lệ

Một pipeline có thể đăng ký nhiều handler, kể cả ở các bước trung gian khác nhau:

~~~java
import java.util.stream.Stream;

public class MultipleCloseHandlers {
    public static void main(String[] args) {
        try (Stream<Integer> numbers = Stream.of(1, 2, 3)
                .onClose(() -> System.out.println("Dong A"))
                .filter(number -> number > 1)
                .onClose(() -> System.out.println("Dong B"))) {

            System.out.println("So phan tu: " + numbers.count());
        }
    }
}
~~~

Kết quả:

~~~text
So phan tu: 2
Dong A
Dong B
~~~

Các close handler được thực thi **theo thứ tự đã đăng ký**. Nếu một handler ném ngoại lệ, những handler còn lại **vẫn được gọi**. Ngoại lệ đầu tiên phát sinh trong lúc đóng được chuyển cho bên gọi; các ngoại lệ tiếp theo được gắn vào nó dưới dạng *suppressed exceptions*:

~~~java
import java.util.stream.Stream;

public class CloseExceptionDemo {
    public static void main(String[] args) {
        try (Stream<Integer> stream = Stream.of(1, 2)
                .onClose(() -> {
                    throw new IllegalStateException("Loi dong A");
                })
                .onClose(() -> {
                    System.out.println("Van chay handler B");
                    throw new IllegalArgumentException("Loi dong B");
                })) {

            System.out.println(stream.count());
        } catch (RuntimeException ex) {
            System.out.println("Ngoai le chinh: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Ngoai le bi dinh kem: "
                        + suppressed.getMessage());
            }
        }
    }
}
~~~

Trong ví dụ, handler B vẫn chạy dù handler A ném ngoại lệ. Ngoại lệ từ A là ngoại lệ chính của quá trình đóng, còn ngoại lệ từ B được đính kèm để không mất thông tin lỗi.

Có một tầng xử lý ngoại lệ khác khi dùng `try-with-resources`: nếu **phần thân khối `try` đã ném ngoại lệ**, ngoại lệ đó được ưu tiên làm ngoại lệ chính, còn ngoại lệ phát sinh từ `close()` được đính kèm dưới dạng suppressed. Vì vậy khi điều tra lỗi, nên kiểm tra cả `Throwable.getSuppressed()`.

## 6. Phân biệt các cơ chế liên quan

| Cơ chế | Khi nào hoạt động? | Mục đích |
|---|---|---|
| `onClose(handler)` | Lúc đăng ký chỉ tạo thêm handler; handler chạy khi stream đóng | Bổ sung logic dọn dẹp, ghi log, giải phóng tài nguyên riêng |
| `close()` | Khi được gọi trực tiếp hoặc bởi `try-with-resources` | Đóng pipeline và thực hiện các close handler |
| `try-with-resources` | Tự gọi `close()` khi rời phạm vi `try` | Bảo đảm đóng cả lúc xử lý thất bại |
| `count()`, `collect()`, `forEach()` | Khi thao tác kết thúc được gọi | Tiêu thụ hoặc xử lý phần tử; không tự động đóng stream |
| `peek(action)` | Khi các phần tử thực sự đi qua bước đó trong quá trình thực thi | Quan sát phần tử; không phải callback khi đóng |

`onClose` thường chỉ cần dùng khi có hành động bổ sung lúc đóng. Với stream I/O có sẵn cơ chế đóng như `Files.lines`, **`try-with-resources` mới là bước thiết yếu**; không bắt buộc phải thêm `onClose` chỉ để gọi `close()` lần nữa.

## 7. Lỗi thường gặp và cách phòng tránh

**Nhầm kết thúc pipeline với đóng tài nguyên.** Gọi `lines.count()` xong rồi bỏ biến `lines` không bảo đảm tài nguyên I/O được giải phóng ngay. Hãy bao quanh toàn bộ quá trình sử dụng stream bằng `try-with-resources`.

**Đăng ký handler nhưng không đóng stream.** `onClose` không hoạt động giống `finally` độc lập. Nếu không có `close()`, handler không được kích hoạt chỉ vì pipeline đã hoàn tất hoặc đối tượng không còn được tham chiếu.

**Tự đóng stream trước khi trả về.** Phương thức trả `Stream<T>` để caller tiếp tục xử lý không nên đóng stream trước lúc trả về. Thay vào đó, chuyển quyền sở hữu việc đóng cho caller và nêu rõ hợp đồng sử dụng.

**Dùng `onClose` làm nơi xử lý từng phần tử.** Close handler gắn với vòng đời pipeline, không được gọi một lần cho mỗi phần tử. Công việc theo phần tử thuộc về `map`, `filter`, `forEach` hoặc các thao tác tương ứng.

**Bỏ qua lỗi khi dọn dẹp.** Nếu handler đóng tài nguyên có thể ném `IOException`, cần xử lý hoặc chuyển đổi ngoại lệ có chủ đích. Tránh nuốt lỗi âm thầm; kiểm tra suppressed exceptions khi có nhiều lỗi đồng thời.

## 8. Tự luyện tập

1. Tạo stream bằng `Stream.of("a", "b")`, gắn hai `onClose` lần lượt in `A`, `B`, rồi gọi `count()`. Quan sát kết quả trước và sau khi gọi `close()` để kiểm chứng thời điểm handler chạy.
2. Đọc một tệp UTF-8 qua `Files.lines`, lọc những dòng không rỗng và đếm chúng. Dùng `try-with-resources` và `onClose` để ghi log khi stream được đóng. Thử tạo ngoại lệ trong khối `try` và xác nhận handler vẫn chạy.
3. Đăng ký hai handler đều ném ngoại lệ khác nhau. Dùng `getSuppressed()` để kiểm tra rằng thông tin lỗi từ cả hai handler được giữ lại.

**Ghi nhớ:** `onClose` định nghĩa *việc cần làm khi đóng*; `close()` thực hiện *hành động đóng*; `try-with-resources` bảo đảm *hành động đóng xảy ra đúng lúc*. Kết hợp đúng ba cơ chế này giúp pipeline Java Stream xử lý nguồn I/O an toàn và dễ bảo trì.
