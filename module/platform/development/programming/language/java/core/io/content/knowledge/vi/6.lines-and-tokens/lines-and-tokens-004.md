# BufferedReader.lines() và quyền đóng Reader trong Java

`BufferedReader.lines()` biến một `BufferedReader` thành `Stream<String>` để xử lý các dòng văn bản bằng Stream API. Cú pháp rất tiện cho lọc, biến đổi, đếm và tìm kiếm dòng:

~~~java
long count = reader.lines()
        .filter(line -> !line.isBlank())
        .count();
~~~

Tuy nhiên, cần phân biệt **quá trình tiêu thụ stream** và **quyền sở hữu tài nguyên I/O**. Stream được tạo bởi `BufferedReader.lines()` đọc dữ liệu từ cùng `BufferedReader`, nhưng **đóng stream không tự đóng reader**. Nếu reader đọc file hoặc socket, người sở hữu reader vẫn phải đóng reader khi hoàn tất. Điều này khác với `Files.lines(path, charset)`: stream do `Files.lines` trả về gắn với tài nguyên file và phải được đóng để giải phóng tài nguyên đó.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `BufferedReader.lines()` sinh `Stream<String>` **lazy** như thế nào và khi nào thao tác I/O thật sự diễn ra.
- Phân biệt dòng rỗng `""`, dòng có khoảng trắng và `null` của `readLine()`; hiểu ký tự kết thúc dòng không còn trong phần tử stream.
- Đặt `try-with-resources` quanh đúng đối tượng sở hữu tài nguyên, kể cả khi stream dừng sớm với `findFirst()` hoặc `limit()`.
- Chứng minh bằng chương trình chạy được rằng `stream.close()` không tự gọi `BufferedReader.close()`.
- Phân biệt `BufferedReader.lines()` với `Files.lines()` về quyền đóng tài nguyên.
- Xử lý `UncheckedIOException` phát sinh khi đọc lazy, tránh trả một stream gắn với reader đã đóng và tránh dùng reader đồng thời với terminal operation trên stream.
- Biết khi nào nên dùng `readLine()`, `lines()` hoặc đọc từng khối `char[]`.

## 2. Nguồn, stream và tài nguyên: ba vai trò cần tách bạch

Hãy xem mối quan hệ:

~~~text
File / socket / StringReader
          |
          v
     BufferedReader   <-- đối tượng quản lý Reader bên dưới
          |
          | .lines()
          v
     Stream<String>   <-- pipeline xử lý các dòng
          |
          | filter / map / limit / count / forEach / ...
          v
        Kết quả
~~~

- `BufferedReader` là một `Reader` có bộ đệm; bản thân nó triển khai `Closeable`/`AutoCloseable` và `close()` sẽ đóng reader bên dưới.
- `BufferedReader.lines()` trả về một `Stream<String>` **liên kết với reader ấy**; stream tự nó không mang quyền đóng reader theo hợp đồng này.
- `Stream` hỗ trợ `close()`, chủ yếu để chạy các **close handler** gắn với stream (nếu có). Không được suy luận rằng `close()` của mọi stream sẽ đóng nguồn dữ liệu mà pipeline đang đọc.
- Quyền đóng tài nguyên phải xuất phát từ cách **tài nguyên được mở và bàn giao**. Bên mở reader thông thường là bên chịu trách nhiệm đóng, trừ khi hợp đồng API tuyên bố rõ việc chuyển quyền sở hữu.

Một file có thể bị giữ open nếu chỉ đóng `Stream<String>` rồi quên đóng `BufferedReader`. Ngược lại, đóng `BufferedReader` quá sớm khiến stream còn chưa tiêu thụ không thể đọc đúng.

### Hợp đồng thiết yếu của `BufferedReader.lines()`

- Tạo stream gồm các dòng như kết quả của các lần gọi `readLine()`.
- Mỗi phần tử `String` **không chứa** ký tự kết thúc dòng.
- Dữ liệu được đọc **lazily**: chỉ khi thực hiện terminal operation thì pipeline mới yêu cầu các dòng.
- Nếu xảy ra `IOException` từ reader khi pipeline đang đọc, ngoại lệ được bọc trong `UncheckedIOException` để phù hợp Stream API.
- Không nên thực hiện các thao tác khác trên cùng reader trong lúc terminal operation của stream đang chạy; kết quả terminal operation khi đó không được bảo đảm.
- Sau một terminal operation, không được giả định reader còn ở vị trí cụ thể nào để tiếp tục đọc bằng API khác.
- Việc gọi `close()` trên stream trả về không tự động gọi `close()` trên reader.

Cần nhớ sự khác nhau giữa `lines()` và `readLine()`: `readLine()` trả về `null` khi EOF; trong Stream API, EOF khiến stream **hết phần tử** và không phát ra phần tử `null` ở cuối.

## 3. Lazy evaluation: tạo pipeline chưa đồng nghĩa đã đọc file

Ví dụ:

~~~java
Stream<String> pipeline = reader.lines()
        .map(String::trim)
        .filter(line -> !line.isEmpty());
~~~

Tại thời điểm vừa khai báo, các bước `map` và `filter` là **intermediate operations**; chúng chưa duyệt toàn bộ file và chưa trả danh sách dữ liệu. Một terminal operation như `forEach`, `count`, `toList`, `findFirst` hoặc `anyMatch` mới kích hoạt truy xuất và xử lý nguồn.

~~~java
List<String> values = pipeline.toList(); // terminal operation (Java 16+)
~~~

Một stream chỉ được tiêu thụ **một lần**. Sau `toList()` không thể tiếp tục `pipeline.count()`; cần tạo nguồn/pipeline mới nếu dữ liệu cho phép. Ngay cả khi terminal operation dừng sớm, ví dụ `findFirst()`, việc tái sử dụng cùng stream cũng không hợp lệ.

### `limit()` và `findFirst()` không tự đóng reader

~~~java
Optional<String> first = reader.lines()
        .filter(line -> line.startsWith("ERR"))
        .findFirst();
~~~

`findFirst()` có thể dừng mà chưa đi hết file; điều đó không làm tài nguyên reader tự được đóng. `limit(10)` cũng chỉ giới hạn **số phần tử stream** mà pipeline lấy, không giới hạn kích thước một dòng và không thực hiện đóng file. Reader còn mở cho tới khi chủ sở hữu đóng nó.

Một reader có thể đã đọc trước vào bộ đệm nhiều ký tự hơn lượng stream trả cho người gọi. Vì vậy, sau terminal operation **đừng dựa vào vị trí còn lại của reader** để đọc tiếp chính xác từ một offset suy đoán. Nếu phải kết hợp nhiều kiểu đọc theo một giao thức, nên quản lý bằng một cơ chế đọc nhất quán.

## 4. Mẫu sử dụng đúng: mở reader, tiêu thụ stream, rồi đóng reader

Với file văn bản UTF-8, đây là mẫu nên ưu tiên:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LineCounter {
    private LineCounter() {}

    public static long countNonBlank(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            return reader.lines()
                    .filter(line -> !line.isBlank())
                    .count();
        }
    }
}
~~~

Đây là **lớp tiện ích có thể biên dịch** nhưng không có `main`. Khi dùng, gọi `LineCounter.countNonBlank(path)` với một file tồn tại. `String.isBlank()` có từ Java 11; ví dụ dùng được với Java 17+.

- `Files.newBufferedReader` tạo `BufferedReader` gắn với file và sử dụng charset tường minh.
- `try-with-resources` giữ reader mở suốt quá trình `count()` chạy.
- Khi khối `try` kết thúc (kể cả do ngoại lệ), `reader.close()` được gọi.
- Không nhất thiết phải đóng riêng stream tạm thời bằng `try-with-resources` trong ví dụ này, vì stream từ `reader.lines()` không có quyền đóng reader; **reader mới là tài nguyên cần quản lý**.
- Nếu lỗi I/O phát sinh trong lúc `count()` duyệt, cần lưu ý ngoại lệ đó đi qua `UncheckedIOException`; `throws IOException` trong chữ ký trên chủ yếu bao gồm lỗi mở/đóng reader, không tự động biến ngoại lệ đọc lazy trở lại checked exception.

Nếu ứng dụng muốn API luôn báo lỗi đọc dưới dạng `IOException`, có thể chuyển lại từ `UncheckedIOException`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CheckedLineCounter {
    private CheckedLineCounter() {}

    public static long countNonBlank(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            try {
                return reader.lines()
                        .filter(line -> !line.isBlank())
                        .count();
            } catch (UncheckedIOException exception) {
                throw exception.getCause();
            }
        }
    }
}
~~~

Lớp thứ hai cũng không có `main`; nó chứng minh cách trả nguyên nhân I/O về hợp đồng checked exception. Không nên bắt mọi `RuntimeException` rồi coi tất cả là lỗi I/O: lỗi xử lý trong `map/filter` có thể là lỗi lập trình hoặc dữ liệu.

## 5. Ví dụ Java 17+ chạy được: đóng stream vẫn chưa đóng reader

Ví dụ tự theo dõi `close()` của nguồn để quan sát điều này mà không phụ thuộc việc hệ điều hành đang giữ file như thế nào.

Tạo file **`LinesOwnershipDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.List;
import java.util.stream.Stream;

public class LinesOwnershipDemo {
    static final class TrackedReader extends StringReader {
        private boolean closed;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closed = true;
            super.close();
        }

        boolean isClosed() {
            return closed;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedReader source = new TrackedReader("alpha\n\nbeta\n");

        try (BufferedReader reader = new BufferedReader(source)) {
            try (Stream<String> lines = reader.lines()) {
                List<String> values = lines
                        .filter(line -> !line.isEmpty())
                        .toList();
                System.out.println("values=" + values);
            }

            System.out.println("afterStreamClose=" + source.isClosed());
        }

        System.out.println("afterReaderClose=" + source.isClosed());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LinesOwnershipDemo.java
java LinesOwnershipDemo
~~~

**Stdout chính xác:**

~~~text
values=[alpha, beta]
afterStreamClose=false
afterReaderClose=true
~~~

Diễn giải:

1. `TrackedReader` ghi nhận lúc phương thức `close()` của nó được gọi.
2. `BufferedReader` bọc `TrackedReader` và `lines()` tạo pipeline xử lý cả dòng `alpha`, dòng rỗng và `beta`.
3. `filter` bỏ dòng rỗng; `toList()` tiêu thụ stream. `Stream.toList()` có từ Java 16 và trả một list không hỗ trợ thao tác thêm/xóa phần tử.
4. Ra khỏi `try (Stream<String> lines = ...)` thì `lines.close()` chạy, nhưng nguồn bên dưới vẫn **chưa bị đóng**, nên in `false`.
5. Ra khỏi `try (BufferedReader reader = ...)` thì `reader.close()` đóng `TrackedReader`, nên in `true`.

Điều này không phụ thuộc vào việc nguồn là `StringReader` hay file. Với file/socket, hậu quả thực tế khi quên đóng reader còn có thể là giữ file descriptor/socket và bộ đệm liên quan.

**Có cần dùng cả hai `try`?** Nếu stream không có close handler riêng, `try` của stream không bắt buộc để giải phóng file trong ví dụ này; đóng reader là điều chính yếu. Tuy nhiên, có thể đóng cả hai nếu muốn thể hiện rõ vòng đời hoặc stream đã được gắn `onClose` handler. Đừng cho rằng đóng hai tầng là cùng một thao tác.

## 6. `BufferedReader.lines()` khác `Files.lines()` ở quyền đóng

Dù cùng trả về `Stream<String>`, chúng có **hợp đồng sở hữu tài nguyên khác nhau**.

| API | Bạn nhận được | Đối tượng phải đóng | Ví dụ cấu trúc đúng |
| --- | --- | --- | --- |
| `BufferedReader.lines()` | Stream từ reader **đang có** | `BufferedReader` do bên sở hữu tạo ra | `try (BufferedReader r = ...) { r.lines().count(); }` |
| `Files.lines(path, charset)` | Stream đọc file do API mở | **Stream trả về** | `try (Stream<String> s = Files.lines(path, UTF_8)) { s.count(); }` |
| `Stream.of(...)` | Stream dữ liệu trong bộ nhớ | Thường không có tài nguyên I/O để giải phóng | `Stream.of(...).count()` |

`Files.lines` mở một tài nguyên file phục vụ stream; gọi `close()` trên stream trả về sẽ giải phóng tài nguyên file của thao tác này. Với `BufferedReader.lines()`, việc đóng stream **không thay thế** `reader.close()`.

### Ví dụ hoàn chỉnh so sánh cả hai

Tạo file **`FileLinesDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-lines-", ".txt");

        try {
            Files.writeString(file, "red\r\n\r\nblue\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                long nonBlank = reader.lines()
                        .filter(line -> !line.isBlank())
                        .count();
                System.out.println("nonBlank=" + nonBlank);
            }

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long blank = lines
                        .filter(String::isBlank)
                        .count();
                System.out.println("blank=" + blank);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac FileLinesDemo.java
java FileLinesDemo
~~~

Stdout:

~~~text
nonBlank=2
blank=1
~~~

File tạm chứa `red`, một dòng trống và `blue`. Đoạn thứ nhất **đóng reader** bằng `try-with-resources`. Đoạn thứ hai **đóng stream do `Files.lines` trả về** bằng `try-with-resources`. Khối `finally` xóa file tạm sau khi cả hai tài nguyên đọc đã đóng, kể cả khi việc xử lý thất bại.

Lưu ý: việc thử nghiệm trên file tạm không chứng minh “đóng stream của `BufferedReader.lines` là đủ”; trường hợp đó đã được kiểm chứng bằng `TrackedReader` ở mục trước.

## 7. Lỗi quan trọng: trả stream từ reader đã đóng

Mẫu sau thường xuất hiện khi muốn một hàm “tiện lợi” trả về `Stream<String>`:

~~~java
// SAI: dòng chỉ được đọc khi caller bắt đầu terminal operation.
static java.util.stream.Stream<String> broken(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(
                         path, java.nio.charset.StandardCharsets.UTF_8)) {
        return reader.lines();
    } // Reader đã đóng trước khi caller có cơ hội duyệt stream.
}
~~~

`lines()` là lazy. Khi phương thức `broken` trả về, khối `try` kết thúc nên reader đã đóng. Caller gọi `count()` hoặc `toList()` sẽ không thể tiêu thụ nguồn đúng; thường nhận `UncheckedIOException` do cố đọc từ stream đã đóng.

Có hai hướng thiết kế đúng, tùy ai sở hữu tài nguyên.

### Hướng A: xử lý toàn bộ khi reader vẫn còn mở

Nếu hàm cần trả về **kết quả**, thực hiện terminal operation trong `try`:

~~~java
static java.util.List<String> loadNonBlank(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(
                         path, java.nio.charset.StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.isBlank())
                .toList();
    }
}
~~~

Chỉ dùng cách này khi số dòng được giữ trong bộ nhớ là **hữu hạn và hợp lý**. `toList()` materialize mọi dòng; với file rất lớn, việc tạo list có thể tiêu tốn RAM đáng kể. Nếu bài toán chỉ cần số đếm, tổng hợp thống kê hay ghi kết quả sang đích khác, làm việc streaming trong khối `try` thích hợp hơn.

### Hướng B: trả stream có quyền sở hữu file rõ ràng

Nếu API chủ đích bàn giao một stream đọc file cho caller, dùng `Files.lines`:

~~~java
static java.util.stream.Stream<String> openLines(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.lines(
            path, java.nio.charset.StandardCharsets.UTF_8);
}
~~~

Caller bắt buộc sử dụng:

~~~java
try (java.util.stream.Stream<String> lines = openLines(path)) {
    lines.filter(line -> !line.isBlank())
         .forEach(System.out::println);
}
~~~

Đây là các **mảnh mã** (cần đặt phương thức trong lớp, có biến `path` và khai báo/giải quyết `IOException` ở caller). `Files.lines` tạo stream có cơ chế đóng tài nguyên file khi stream được close; tài liệu hàm nên nói rõ rằng caller **sở hữu và phải đóng** stream, kể cả khi terminal operation dừng sớm hoặc phát sinh ngoại lệ.

Không áp dụng máy móc mẹo “gắn `onClose(reader::close)`” vì `BufferedReader.close()` có thể ném checked `IOException` trong khi `onClose` nhận `Runnable`. Việc tự chuyển ngoại lệ và quy ước đóng cần cẩn thận; khi nguồn là file, `Files.lines` hoặc đóng reader ngay trong scope tiêu thụ thường rõ ràng hơn.

## 8. Cách xử lý ngoại lệ đọc lazy

`BufferedReader.readLine()` trực tiếp khai báo `throws IOException`. Nhưng terminal operation của `Stream<String>` không khai báo checked `IOException`. Vì vậy, khi thao tác đọc bên dưới thất bại trong lúc duyệt stream, Java bọc nguyên nhân trong `UncheckedIOException`.

Ví dụ độc lập tạo nguồn cố tình lỗi để thấy điều này. Tạo **`LinesIOExceptionDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.UncheckedIOException;
import java.util.Objects;

public class LinesIOExceptionDemo {
    static final class FailingReader extends Reader {
        @Override
        public int read(char[] buffer, int offset, int length)
                throws IOException {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            if (length == 0) {
                return 0;
            }
            throw new IOException("simulated read failure");
        }

        @Override
        public void close() {
            // Không có tài nguyên thực cần giải phóng trong demo.
        }
    }

    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new FailingReader())) {
            try {
                reader.lines().count();
            } catch (UncheckedIOException exception) {
                System.out.println("cause="
                        + exception.getCause().getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LinesIOExceptionDemo.java
java LinesIOExceptionDemo
~~~

Stdout:

~~~text
cause=simulated read failure
~~~

Lỗi xảy ra **trong `count()`**, tức lúc stream thực sự cần đọc dòng. Khi đóng reader, `close()` vẫn có thể ném `IOException` riêng; `try-with-resources` xử lý trường hợp phải đóng khi khối code đang có ngoại lệ và có thể ghi nhận ngoại lệ đóng dưới dạng *suppressed exception*. Việc biến đổi `UncheckedIOException` trở lại `IOException` ở ranh giới API là lựa chọn hợp lý nếu contract của ứng dụng cần checked exception nhất quán.

Với `Files.lines`, lỗi **mở file** có thể là `IOException` tại lời gọi `Files.lines(...)`, còn lỗi **đọc tiếp trong lúc duyệt** cũng có thể trở thành `UncheckedIOException`. Việc dùng `try-with-resources` vẫn quan trọng, bất kể terminal operation kết thúc bình thường hay lỗi.

## 9. Đọc dòng, dấu kết thúc dòng và dòng rỗng

`BufferedReader.readLine()` (và theo đó là `lines()`) phân biệt dòng theo `\n` (LF), `\r` (CR) hoặc cặp `\r\n` (CRLF). Chúng **loại bỏ** terminator khỏi chuỗi trả về.

| Nội dung ký tự nguồn | Các phần tử stream |
| --- | --- |
| `"A\nB"` | `"A"` và `"B"` |
| `"A\r\nB\n"` | `"A"` và `"B"` |
| `"\n"` | Một phần tử `""` |
| `"A\n\nB"` | `"A"`, `""`, `"B"` |
| Chuỗi rỗng `""` | Không có phần tử |

Dòng trống thật (`""`) vẫn tồn tại trong stream; `filter(String::isBlank)` giúp giữ các dòng chỉ toàn whitespace nếu mục tiêu là đếm chúng, còn `filter(line -> !line.isBlank())` loại bỏ chúng. `String.isBlank()` nhận cả những chuỗi chứa toàn ký tự whitespace theo định nghĩa Java; nó khác `isEmpty()`, vốn chỉ kiểm tra độ dài bằng 0.

`lines()` không thích hợp nếu cần bảo toàn **đúng các terminator**, ví dụ công cụ copy file phải giữ nguyên CRLF/LF từng vị trí. Khi ấy có thể dùng `BufferedReader.read(char[])` rồi `Writer.write(char[], off, count)` để không tự loại bỏ terminator, hoặc dùng byte streams/`Files.copy` khi cần giữ nguyên byte thực tế.

Ngoài ra, `Stream<String>` xử lý theo đơn vị **dòng**, không phải theo số byte hay Unicode code point. Charset thuộc bước chuyển đổi file byte sang `Reader`; luôn ghi rõ UTF-8 (hoặc charset giao thức yêu cầu), thay vì đoán encoding.

## 10. Chú ý tới vị trí reader và việc dùng chung giữa nhiều nơi

### Không đọc cạnh tranh trên cùng reader trong terminal operation

Tránh:

~~~java
// SAI: can thiệp trực tiếp cùng reader bên trong pipeline đang tiêu thụ.
reader.lines().forEach(line -> {
    try {
        System.out.println(reader.readLine());
    } catch (java.io.IOException exception) {
        throw new java.io.UncheckedIOException(exception);
    }
});
~~~

Ở đây pipeline và callback cùng tiêu thụ một reader. Kết quả không được bảo đảm: có thể mất dòng, bỏ sót dữ liệu hoặc rơi vào trạng thái khó dự đoán.

Đừng đồng thời giao một `BufferedReader` cho hai thread đọc từ `reader.lines()` và `reader.readLine()`. Dù một số thao tác có cơ chế đồng bộ nội bộ, hai bộ tiêu thụ vẫn tranh nhau **một vị trí dòng dữ liệu**. Thiết kế có một nơi sở hữu vòng đọc, rồi phân phát dữ liệu đã được giải mã cho các bên khác là cách an toàn và dễ kiểm soát hơn.

### Không dựa vào vị trí sau khi kết thúc pipeline

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String first = reader.lines().findFirst().orElse(null);
    // Không dựa vào giả định readLine() tiếp theo là dòng thứ hai.
}
~~~

Mảnh code cần import `BufferedReader`, `Files`, `Path`, `StandardCharsets` và xử lý `IOException`. API `BufferedReader.lines()` không bảo đảm một vị trí cụ thể của reader sau terminal operation. Nếu cần thật sự đọc dòng đầu rồi tiếp tục tuần tự từ dòng hai, viết bằng `readLine()` trong cùng một vòng đọc hoặc parser kiểm soát vị trí, thay vì cắt giữa hai mô hình.

### Có nên dùng `parallel()`?

`reader.lines().parallel()` không biến một nguồn Reader đơn lẻ thành nhiều nguồn đọc độc lập. Chia tách/đọc dữ liệu phụ thuộc triển khai; tác vụ file I/O có chi phí tuần tự và callback có tác dụng phụ có thể không giữ thứ tự khi dùng `forEach`. Thường nên đọc tuần tự từ một reader; nếu cần xử lý CPU song song, cân nhắc thiết kế hàng đợi/batch hoặc phân đoạn dữ liệu có ranh giới rõ. Chỉ song song khi đã đo và kiểm soát thứ tự, trạng thái chia sẻ và vòng đời tài nguyên.

## 11. Stream close handler khác với đóng nguồn Reader

Một `Stream` cho phép đăng ký `onClose(Runnable)`:

~~~java
try (java.util.stream.Stream<String> stream =
             java.util.stream.Stream.of("A", "B")
                     .onClose(() -> System.out.println("stream closed"))) {
    System.out.println(stream.count());
}
~~~

Mảnh mã trên có thể đặt trong một phương thức Java; kết quả:

~~~text
2
stream closed
~~~

`onClose` chạy khi **`stream.close()` được gọi** (ở đây do `try-with-resources`), không phải tự động sau terminal operation `count()`. Vì vậy, thuật toán gọi `count()`/`findFirst()` rồi quên close vẫn có thể bỏ qua handler đóng nguồn nếu ứng dụng gắn vào stream.

Với `BufferedReader.lines()`, mặc định không có close handler tự động đóng reader. Nếu tự thiết kế wrapper trả về stream có handler đóng reader, cần quyết định rõ quyền sở hữu và cách chuyển checked `IOException` từ `Reader.close()` vào exception phù hợp với `Runnable`. Khi không thật sự cần chuyển quyền đóng, cách đơn giản nhất vẫn là giữ cả tiêu thụ stream lẫn đóng `BufferedReader` trong **cùng một scope**.

## 12. Dùng `Stream<String>` tiết kiệm bộ nhớ nhưng không có nghĩa vô hạn an toàn

Một pipeline như:

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    long count = reader.lines().filter(s -> !s.isBlank()).count();
}
~~~

thường không cần giữ toàn bộ file trong RAM; dữ liệu được đọc lần lượt và tổng hợp thành số đếm. Tuy vậy:

- **Một dòng riêng lẻ** vẫn có thể rất dài. `readLine()` cần tạo chuỗi cho cả dòng, nên `lines()` không áp dụng giới hạn độ dài dòng.
- `toList()`, `collect(...)` hoặc `sorted()` có thể tích lũy nhiều hoặc toàn bộ dữ liệu. Streaming không đồng nghĩa lúc nào cũng có bộ nhớ hằng số.
- `limit(100)` chỉ giới hạn số **dòng**, không giới hạn mỗi dòng là bao nhiêu ký tự và không tự đóng reader.
- `findFirst()`/`anyMatch()` có thể dừng sớm, nhưng Reader vẫn là tài nguyên phải đóng.
- Với đầu vào không tin cậy hoặc socket, cần giới hạn kích thước bản ghi, timeout/chính sách hủy, xử lý encoding và framing rõ ràng. `lines()` có thể chặn chờ dấu xuống dòng hoặc EOF nếu peer tiếp tục giữ kết nối mở.

Nếu cần đặt **giới hạn byte/ký tự mỗi dòng ngay trong lúc đọc**, hãy dùng bộ phân tích đọc từng ký tự/khối có đếm giới hạn trước khi tích lũy, hoặc giao thức với trường độ dài rõ ràng. Kiểm tra `line.length()` sau khi `lines()` đã tạo chuỗi quá dài có thể quá muộn.

## 13. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Chỉ đóng stream từ `BufferedReader.lines()`.**  
Đóng stream này không đóng reader nguồn. Cần đóng `BufferedReader` trong `try-with-resources` khi nó do hàm sở hữu.

**Lỗi 2 — Trả stream lazy khỏi `try (BufferedReader...)`.**  
Reader đã đóng ngay khi trả về, trong khi caller chưa bắt đầu đọc. Hãy thực hiện terminal operation trong scope còn mở, hoặc trả `Files.lines` với hợp đồng caller tự đóng stream.

**Lỗi 3 — Tưởng terminal operation tự gọi `close()`.**  
`count()`, `findFirst()`, `toList()` hoàn thành không bảo đảm `stream.close()` đã được gọi. `onClose` handler chỉ chạy khi stream được close; đóng reader bằng scope đúng.

**Lỗi 4 — Nhầm `UncheckedIOException` với `IOException` trực tiếp.**  
Lỗi đọc lazy qua `lines()` có thể ném `UncheckedIOException` tại terminal operation. Không chỉ xử lý checked exception ở lúc mở file mà bỏ qua đường lỗi này.

**Lỗi 5 — Xen `readLine()` vào pipeline hoặc tiếp tục dựa vào vị trí sau terminal operation.**  
Reader dùng chung một nguồn ký tự và một vị trí; kết quả khi xen thao tác không được bảo đảm. Chọn một cơ chế duyệt thống nhất.

**Lỗi 6 — Lẫn lộn `Files.lines()` và `BufferedReader.lines()` về quyền đóng.**  
`Files.lines` bàn giao một stream cần close để đóng file do chính API mở; `BufferedReader.lines()` tạo stream từ reader hiện hữu mà caller/người sở hữu vẫn phải đóng reader.

**Lỗi 7 — Giả định một phần tử stream giữ nguyên dấu xuống dòng.**  
`lines()` bỏ LF/CR/CRLF; không phù hợp cho tác vụ phải giữ nguyên ký tự phân cách hoặc byte gốc.

**Lỗi 8 — Sử dụng `toList()` với file không giới hạn hoặc xem `limit` là bảo vệ kích thước dòng.**  
`toList()` tích lũy kết quả; `limit` đếm phần tử, không kiểm tra độ dài mỗi phần tử. Đặt giới hạn thích hợp tại lúc đọc.

## 14. Checklist trước khi dùng trong dự án

- [ ] Biết **ai mở** `BufferedReader` và **ai đóng** nó?
- [ ] Terminal operation của `reader.lines()` được chạy khi reader chắc chắn còn mở?
- [ ] Nếu API trả `Files.lines()`, caller có `try-with-resources` để đóng chính stream?
- [ ] Không dùng `stream.close()` làm bằng chứng reader đã đóng?
- [ ] Có cân nhắc `UncheckedIOException` khi lỗi đọc xảy ra trong quá trình xử lý pipeline?
- [ ] Không vừa duyệt `lines()` vừa trực tiếp đọc trên cùng reader hoặc giả định cursor sau khi kết thúc stream?
- [ ] Nếu có `findFirst`/`limit`, reader vẫn được đóng dù pipeline tiêu thụ ít dòng?
- [ ] Charset được chỉ định rõ; newline và dòng trống được xử lý đúng quy định?
- [ ] Nếu có thể gặp dòng dài/dữ liệu từ mạng, đã đặt giới hạn/thời gian chờ theo giao thức?
- [ ] Có tránh giữ toàn bộ dữ liệu trong RAM khi không cần thiết?

### Câu hỏi tự kiểm tra

**1.** Gọi `reader.lines().filter(...).count()` có tự đóng `reader` không?  
**Đáp án:** Không. Hãy đặt `BufferedReader` do bạn sở hữu trong `try-with-resources`.

**2.** Nếu viết `try (Stream<String> stream = reader.lines()) { ... }`, sau `try` reader đã đóng chưa?  
**Đáp án:** Không phải bởi `stream.close()`. Reader chỉ được đóng nếu có thao tác riêng/hợp đồng khác (ví dụ scope của reader tự đóng).

**3.** `Files.lines(path, UTF_8)` cần đóng đối tượng nào?  
**Đáp án:** Đóng `Stream<String>` mà `Files.lines` trả về bằng `try-with-resources` để giải phóng tài nguyên file liên quan.

**4.** Vì sao không trả `reader.lines()` từ một hàm mà reader được tạo bên trong `try-with-resources`?  
**Đáp án:** Stream là lazy; reader bị đóng trước khi caller gọi terminal operation.

**5.** `reader.lines().findFirst()` đọc được dòng đầu và dừng. Có thể chắc chắn lần `reader.readLine()` kế tiếp trả dòng thứ hai không?  
**Đáp án:** Không. Không có bảo đảm về vị trí reader sau terminal operation trên stream.

**6.** Một lỗi I/O khi stream đang chạy `count()` được báo dưới dạng nào?  
**Đáp án:** Thường là `UncheckedIOException` chứa `IOException` gốc trong `getCause()`.

**Ghi nhớ:** `BufferedReader.lines()` là cách **duyệt dòng** bằng Stream API, còn `BufferedReader` là nơi **quản lý nguồn đọc**. Hãy tiêu thụ stream khi reader còn mở và đóng reader đúng owner. Với `Files.lines()`, chính stream được trả về là tài nguyên phải đóng.