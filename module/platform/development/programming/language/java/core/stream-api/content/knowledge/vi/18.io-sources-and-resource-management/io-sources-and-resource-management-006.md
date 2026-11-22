# Thứ tự chạy `onClose` và ngoại lệ bị `suppressed`

Trong Java Stream API, một pipeline có thể xử lý dữ liệu đến từ file, thư mục hoặc một nguồn cần giải phóng tài nguyên. Khi đóng stream, các hàm dọn dẹp đã đăng ký qua `onClose(...)` được gọi theo một thứ tự xác định. Nếu nhiều hàm dọn dẹp cùng ném ngoại lệ, Java giữ lại các lỗi đó bằng cơ chế **suppressed exceptions** để không đánh mất thông tin về quá trình đóng tài nguyên.

Bài học này thuộc chương **Nguồn vào ra và quản lý tài nguyên** của `JAVA_STREAM_API`. Mục tiêu là hiểu khi nào `onClose` chạy, thứ tự chạy các handler, ngoại lệ nào được ném ra ngoài, và vì sao `try-with-resources` có thể tạo thành nhiều tầng ngoại lệ bị `suppressed`.

## 1. `onClose` gắn với việc đóng stream, không gắn với terminal operation

`BaseStream.onClose(Runnable closeHandler)` đăng ký một hành động được thực hiện khi stream được **đóng**. Mỗi lần gọi `onClose` trả về một stream tương đương có thêm close handler, vì vậy cách viết thông dụng là nối các lệnh `onClose` vào lúc tạo stream.

Phân biệt hai sự kiện:

| Sự kiện | Điều gì xảy ra? |
| --- | --- |
| `count()`, `collect()`, `forEach()`, `findFirst()`... | Terminal operation kích hoạt hoặc kết thúc quá trình xử lý pipeline; **không tự động gọi `close()`**. |
| `stream.close()` | Đóng stream và kích hoạt những close handler đã đăng ký. |
| Kết thúc khối `try-with-resources` | Java tự gọi `close()` trên tài nguyên được khai báo, kể cả khi xử lý bị lỗi. |

Ví dụ ngắn:

```java
import java.util.stream.Stream;

public class CloseLifecycleDemo {
    public static void main(String[] args) {
        Stream<String> stream = Stream.of("A", "B")
                .onClose(() -> System.out.println("stream da dong"));

        System.out.println(stream.count()); // 2
        System.out.println("da thuc hien count");
        stream.close();
    }
}
```

Kết quả:

```text
2
da thuc hien count
stream da dong
```

Điều đáng chú ý là dòng `stream da dong` chỉ xuất hiện sau `close()`. Khi làm việc với `Files.lines(...)`, `Files.walk(...)` hoặc nguồn I/O tương tự, không nên chỉ gọi terminal operation rồi bỏ quên stream: những nguồn này cần được đóng để giải phóng tài nguyên tương ứng. Với stream thuần bộ nhớ như `Stream.of(...)`, ví dụ trên chỉ nhằm quan sát vòng đời, không có file nào cần giải phóng.

## 2. Thứ tự thực thi các close handler

Theo hợp đồng của `BaseStream.onClose`, **các close handler chạy theo thứ tự chúng được đăng ký**. Nếu handler đầu tiên ném ngoại lệ, Java vẫn cố chạy tất cả handler còn lại.

Ví dụ, khi lần lượt đăng ký `H1`, `H2`, `H3`, `H4`:

```text
Dang ky:  H1 -> H2 -> H3 -> H4
close():  H1 -> H2 -> H3 -> H4
                  |     |
                loi A  loi B
```

Nếu `H2` ném lỗi A và `H3` ném lỗi B thì `H4` **vẫn chạy**. Lỗi A là ngoại lệ chính của lần `close()`; lỗi B được lưu trong danh sách ngoại lệ bị `suppressed` của A.

Hãy chạy chương trình đầy đủ sau:

```java
import java.util.stream.Stream;

public class OnCloseOrderDemo {
    public static void main(String[] args) {
        try (Stream<String> stream = Stream.of("A", "B")
                .onClose(() -> System.out.println("close-1"))
                .onClose(() -> {
                    System.out.println("close-2");
                    throw new IllegalStateException("error-2");
                })
                .onClose(() -> {
                    System.out.println("close-3");
                    throw new IllegalArgumentException("error-3");
                })
                .onClose(() -> System.out.println("close-4"))) {

            System.out.println(stream.count());
        } catch (RuntimeException error) {
            System.out.println("primary=" + error.getMessage());
            for (Throwable suppressed : error.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả:

```text
2
close-1
close-2
close-3
close-4
primary=error-2
suppressed=error-3
```

Từ kết quả có thể rút ra ba quy tắc:

1. `close-1` đến `close-4` chạy đúng thứ tự đăng ký.
2. Lỗi của `close-2` không ngăn `close-3` và `close-4` chạy.
3. Ngoại lệ đầu tiên do handler ném ra là ngoại lệ được `close()` chuyển ra ngoài; các ngoại lệ đến sau nằm trong `getSuppressed()` của ngoại lệ đầu tiên.

Khi chỉ một handler thất bại, `getSuppressed()` có thể là mảng rỗng; khi nhiều handler thất bại, mảng này chứa các lỗi bổ sung. Trường hợp đặc biệt: nếu một handler sau đó ném lại **cùng chính đối tượng** `Throwable` đã là ngoại lệ chính, Java không gắn đối tượng đó làm suppressed của chính nó.

## 3. `suppressed` khác gì `cause`?

`Throwable` có hai cơ chế diễn tả những quan hệ khác nhau:

| API | Ý nghĩa | Tình huống thường gặp |
| --- | --- | --- |
| `getCause()` | Ngoại lệ gây ra hoặc được bọc bởi ngoại lệ hiện tại. | `new UncheckedIOException(ioException)` hoặc `new IllegalStateException("...", cause)`. |
| `getSuppressed()` | Các ngoại lệ phụ được ghi nhận trong khi vẫn ưu tiên một ngoại lệ chính. | Một số close handler cùng thất bại; `close()` thất bại khi thân khối `try` cũng đã thất bại. |

Đối với lỗi dọn dẹp, `suppressed` rất hữu ích: chương trình có thể giữ ngoại lệ chính làm tín hiệu lỗi cần xử lý, đồng thời vẫn cung cấp thông tin về các tài nguyên khác không đóng được. Không nên suy luận rằng suppressed là nguyên nhân (`cause`) của ngoại lệ chính; đó là hai quan hệ độc lập.

Khi phân tích sự cố, hãy kiểm tra cả exception chính lẫn `getSuppressed()`. Một số logger hoặc bản in stack trace chuẩn có thể hiển thị các nhánh `Suppressed: ...`, nhưng cách lập trình trực tiếp và rõ ràng nhất là duyệt `Throwable#getSuppressed()` như trong ví dụ trên.

## 4. Hai tầng `suppressed` trong `try-with-resources`

`try-with-resources` có quy tắc ưu tiên riêng. Nếu **phần thân `try` đã ném ngoại lệ**, sau đó `close()` cũng thất bại, ngoại lệ từ thân `try` tiếp tục là ngoại lệ chính; ngoại lệ do `close()` ném ra được gắn vào nó dưới dạng `suppressed`.

Điều này kết hợp với quy tắc `onClose` để tạo thành một cấu trúc lồng nhau:

```text
Loi tu than try: body-error                <-- ngoai le chinh ra khoi try
  Suppressed: close-error-1                <-- close() nem ra
    Suppressed: close-error-2              <-- handler onClose tiep theo
```

Ví dụ có thể biên dịch và chạy độc lập:

```java
import java.util.stream.Stream;

public class NestedSuppressedDemo {
    public static void main(String[] args) {
        try (Stream<String> stream = Stream.of("A")
                .onClose(() -> {
                    throw new IllegalStateException("close-error-1");
                })
                .onClose(() -> {
                    throw new IllegalArgumentException("close-error-2");
                })) {

            stream.findFirst();
            throw new UnsupportedOperationException("body-error");
        } catch (RuntimeException error) {
            System.out.println("primary=" + error.getMessage());

            for (Throwable closeError : error.getSuppressed()) {
                System.out.println("  suppressed=" + closeError.getMessage());
                for (Throwable laterCloseError : closeError.getSuppressed()) {
                    System.out.println("    nested=" + laterCloseError.getMessage());
                }
            }
        }
    }
}
```

Kết quả:

```text
primary=body-error
  suppressed=close-error-1
    nested=close-error-2
```

Ở đây diễn ra hai bước độc lập:

1. Trong quá trình `close()`, handler đầu ném `close-error-1`; handler thứ hai vẫn chạy và ném `close-error-2`. `close-error-2` được gắn vào `close-error-1`.
2. Vì phần thân `try` đã ném `body-error`, `try-with-resources` giữ `body-error` làm lỗi chính, rồi gắn **toàn bộ** ngoại lệ `close-error-1` (kèm ngoại lệ con của nó) vào `body-error`.

Do đó `error.getSuppressed()` ở mức ngoài **không nhất thiết chứa mọi lỗi close ở cùng một cấp**. Muốn xem đầy đủ, cần kiểm tra cả suppressed của từng ngoại lệ con. Nếu phần thân `try` không lỗi, `close-error-1` sẽ trở thành ngoại lệ chính được ném ra khỏi khối.

## 5. Phân biệt thứ tự đóng *nhiều tài nguyên* với thứ tự `onClose`

Có hai quy tắc không nên trộn lẫn:

- Bên trong **một stream**, close handler chạy theo **thứ tự đăng ký**.
- Với **nhiều tài nguyên khai báo trong một `try-with-resources`**, Java đóng tài nguyên theo **thứ tự ngược với thứ tự khai báo**.

Ví dụ:

```java
import java.util.stream.Stream;

public class MultipleResourcesDemo {
    public static void main(String[] args) {
        try (Stream<String> first = Stream.<String>empty()
                    .onClose(() -> System.out.println("first/H1"))
                    .onClose(() -> System.out.println("first/H2"));
             Stream<String> second = Stream.<String>empty()
                    .onClose(() -> System.out.println("second/H1"))
                    .onClose(() -> System.out.println("second/H2"))) {
            // Không cần terminal operation để minh họa thứ tự đóng.
        }
    }
}
```

Kết quả:

```text
second/H1
second/H2
first/H1
first/H2
```

`second` được đóng trước `first`; trong từng stream, `H1` chạy trước `H2`. Khi các tài nguyên cùng ném ngoại lệ, `try-with-resources` vẫn bảo toàn thông tin về những lần đóng thất bại bằng cơ chế suppressed; đối tượng ngoại lệ chính phụ thuộc vào việc phần thân `try` có lỗi hay không và thứ tự đóng tài nguyên.

## 6. Ứng dụng với stream đọc file

Một ví dụ thực tế là đọc file theo từng dòng. `Files.lines(...)` tạo một stream có nguồn dữ liệu cần được đóng. Ta có thể đăng ký thêm handler để ghi nhận việc kết thúc sử dụng nguồn:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class ReadLinesDemo {
    public static long countNonEmptyLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)
                .onClose(() -> System.out.println("Da ket thuc su dung stream"))) {
            return lines.filter(line -> !line.isBlank()).count();
        }
    }
}
```

Ví dụ này dùng `String.isBlank()` (Java 11 trở lên). `try-with-resources` đảm bảo gọi `close()` khi xử lý thành công và khi pipeline phát sinh lỗi. Lưu ý rằng `onClose` không phải nơi thay thế cơ chế đóng nguồn I/O của `Files.lines`; việc cần làm là đóng chính stream đã mở, còn handler bổ sung dùng để gắn những thao tác dọn dẹp hoặc quan sát hợp lý.

Nếu việc đóng file và một thao tác `onClose` bổ sung cùng thất bại, hãy xem toàn bộ chuỗi ngoại lệ và `suppressed` thay vì chỉ đọc thông điệp lỗi ngoài cùng.

## 7. Những lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng `collect()` hoặc `forEach()` tự đóng stream. | Handler không chạy; nguồn I/O có thể còn mở. | Dùng `try-with-resources` cho stream sở hữu tài nguyên cần đóng. |
| Nghĩ handler ném lỗi sẽ làm dừng các handler sau. | Dự đoán sai luồng dọn dẹp và log. | Ghi nhớ tất cả handler đều được thử chạy; kiểm tra lỗi chính và các suppressed. |
| Chỉ in `error.getMessage()`. | Mất dấu lỗi của các handler đóng tài nguyên khác. | Ghi log stack trace và kiểm tra `getSuppressed()` khi điều tra. |
| Chỉ nhìn `error.getSuppressed()` ở cấp ngoài. | Bỏ sót lỗi `onClose` nằm dưới một ngoại lệ close đã bị suppressed bởi lỗi phần thân. | Duyệt thêm suppressed của các ngoại lệ con khi cần. |
| Nhầm `getCause()` với `getSuppressed()`. | Hiểu sai lỗi gốc và lỗi phát sinh khi dọn dẹp. | Xem chúng là hai quan hệ ngoại lệ riêng biệt. |
| Đăng ký handler có tác dụng phụ phức tạp và dễ lỗi. | Tăng rủi ro phát sinh lỗi thứ cấp trong lúc đóng. | Để handler tập trung vào dọn dẹp ngắn gọn, có phạm vi sở hữu tài nguyên rõ ràng. |

Để tự kiểm tra kiến thức, xét stream có ba handler: `A` chạy thành công, `B` ném `IllegalStateException`, `C` ném `IllegalArgumentException`. Khi gọi `close()`, cả ba vẫn được gọi; ngoại lệ từ `B` được ném ra, còn ngoại lệ từ `C` nằm trong `B.getSuppressed()`. Nếu trước đó thân `try-with-resources` đã ném một ngoại lệ khác, ngoại lệ từ thân `try` mới là lỗi ngoài cùng và lỗi từ `B` nằm trong danh sách suppressed của nó.

**Ghi nhớ:** terminal operation kết thúc xử lý, còn `close()` kích hoạt dọn dẹp; `onClose` chạy theo thứ tự đăng ký và không bỏ qua các handler phía sau khi một handler thất bại; `try-with-resources` bảo toàn lỗi phần thân và lỗi đóng tài nguyên qua các tầng suppressed exceptions.
