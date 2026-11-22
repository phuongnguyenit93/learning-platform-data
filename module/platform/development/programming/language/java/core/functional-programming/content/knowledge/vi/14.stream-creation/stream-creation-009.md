# Đóng Stream giữ tài nguyên bằng `try-with-resources` trong Java

## 1. Vì sao có Stream cần đóng?

`java.util.stream.Stream<T>` mô tả một pipeline xử lý dữ liệu theo kiểu khai báo: nguồn → các thao tác trung gian → thao tác kết thúc. Một Stream có thể tạo từ collection, mảng, giá trị tự cung cấp, file hoặc việc duyệt thư mục. **Không phải mọi Stream đều sở hữu tài nguyên phải đóng**, nhưng một số nguồn dựa trên I/O giữ file handle hoặc directory handle mở trong suốt thời gian duyệt. Nếu không đóng những Stream ấy, ứng dụng có thể rò rỉ tài nguyên, không thể giải phóng handle kịp thời và gặp lỗi khi mở thêm file hoặc thao tác với thư mục.

Trong Java, `Stream<T>` kế thừa khả năng đóng từ `BaseStream<T,S>`, và `BaseStream` mở rộng `AutoCloseable`. Vì vậy, có thể dùng cú pháp:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    System.out.println(count);
}
~~~

Đây là **mảnh mã đặt trong phương thức**, yêu cầu `path` kiểu `Path` đã tồn tại, import `java.nio.file.Files`, `java.nio.file.Path`, `java.util.stream.Stream` và xử lý `IOException`. Khi kết thúc block, Java gọi `lines.close()` tự động, kể cả khi một thao tác trong block ném ngoại lệ.

**Đừng nhầm:** `count()`, `forEach()`, `toList()` và các terminal operations khác **không tự động gọi `Stream.close()`**. Việc pipeline đã tiêu thụ hết phần tử và việc đóng tài nguyên là **hai khái niệm khác nhau**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết Stream nào cần đóng; phân biệt nguồn trong bộ nhớ và nguồn I/O.
- Hiểu vai trò `AutoCloseable`, `Stream.close()`, `BaseStream.onClose()`.
- Viết `try-with-resources` đúng phạm vi sử dụng Stream từ `Files.lines`, `Files.list`, `Files.walk` và `Files.find`.
- Phân biệt đóng Stream với tiêu thụ Stream; hiểu rằng terminal operation không có nghĩa resource đã được đóng.
- Quản lý vòng đời tài nguyên khi pipeline lazy, có exception, dùng helper, trả Stream cho caller hoặc có nhiều tài nguyên.
- Tránh lỗi thường gặp: return Stream thoát khỏi block `try`, tái sử dụng Stream sau terminal operation, quên đóng khi dùng `iterator()` hoặc `findFirst()`.
- Chạy và giải thích chương trình Java 17 có đầu ra xác định, không cần file bên ngoài.

## 2. Stream là gì và không phải là gì?

### 2.1. Stream là pipeline, không phải collection

Với nguồn collection:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
List<String> upper = names.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Đây là mã trong phương thức đã import `java.util.List`. Stream nhận nguồn dữ liệu từ `List` và tạo kết quả. Nó **không phải một danh sách khác có thể tùy tiện đọc lại**; pipeline có lifecycle riêng và thường chỉ nên tiêu thụ một lần.

Một Stream được tạo từ collection hoặc `Stream.of(...)` thường **không nắm tài nguyên hệ điều hành cần đóng**. Gọi `close()` với loại Stream này nhìn chung không có lợi ích về resource ngoài việc thực hiện close handlers đã đăng ký. Javadoc `BaseStream` cũng nhấn mạnh phần lớn Stream không cần đóng; ngoại lệ đáng lưu ý là các Stream được hậu thuẫn bởi I/O, chẳng hạn nguồn từ `Files`.

### 2.2. Stream có thể gắn với tài nguyên bên ngoài

Khi dùng `Files.lines(path)`, `Files.list(directory)` hoặc `Files.walk(directory)`, quá trình duyệt có thể cần file/directory handles. Việc dùng Stream giúp đọc/dò tìm theo nhu cầu nhưng cũng đặt trách nhiệm đóng resource lên người gọi hoặc thành phần sở hữu vòng đời.

Ví dụ:

~~~java
Stream<String> lines = Files.lines(path);
~~~

Đây là một Stream cần được quản lý. Chỉ khai báo như vậy mà không đóng sẽ dễ tạo lỗi quản lý tài nguyên khi code thoát sớm, gặp exception hoặc trả về trước khi duyệt hết.

Thay vì dựa vào việc garbage collector hoặc runtime tự dọn tài nguyên “khi nào đó”, hãy đặt Stream trong `try-with-resources` để đóng **đúng thời điểm đã xác định**.

### 2.3. Bảng nhận diện nhanh

| Cách tạo Stream | Nguồn | Có cần quản lý đóng? | Cách dùng phù hợp |
| --- | --- | --- | --- |
| `list.stream()` | `Collection` trong bộ nhớ | Thường không phải đóng vì I/O | Thực hiện pipeline trực tiếp |
| `Stream.of(...)` | Các giá trị có sẵn | Thường không có resource bên ngoài | Dùng trực tiếp |
| `Arrays.stream(array)` | Mảng trong bộ nhớ | Thường không có resource bên ngoài | Dùng trực tiếp |
| `IntStream.range(a,b)` | Dãy số tạo trong bộ nhớ | Thường không có resource bên ngoài | Dùng trực tiếp |
| `Files.lines(path)` | Dữ liệu file | **Có** | `try (Stream<String> ...)` |
| `Files.list(dir)` | Mục con trực tiếp của thư mục | **Có** | `try (Stream<Path> ...)` |
| `Files.walk(dir)` | Cây thư mục | **Có** | `try (Stream<Path> ...)` |
| `Files.find(dir, depth, matcher)` | Cây thư mục kèm điều kiện | **Có** | `try (Stream<Path> ...)` |

Quy tắc thực tế: đọc **Javadoc của phương thức tạo Stream**. Nếu tài liệu nói Stream chứa reference tới thư mục/file đang mở và phải đóng, thì dùng `try-with-resources`. Không kết luận dựa trên việc dữ liệu thuộc kiểu `String` hay `Path`; cùng một kiểu phần tử có thể đến từ nguồn trong bộ nhớ hoặc I/O.

## 3. `AutoCloseable` và lifecycle của Stream

### 3.1. Vì sao Java cho phép Stream trong `try`?

`BaseStream` mở rộng `AutoCloseable` nên một `Stream<T>` có phương thức `close()`. `try-with-resources` yêu cầu biến tài nguyên implement `AutoCloseable`, vì vậy Stream phù hợp:

~~~java
try (Stream<String> stream = Files.lines(path)) {
    // Sử dụng stream chỉ trong phạm vi này.
}
~~~

Thực thi khái quát:

~~~text
Tạo tài nguyên và Stream
          |
          v
Đăng ký Stream vào try-with-resources
          |
          v
Thực thi pipeline (có thể kết thúc sớm hoặc ném lỗi)
          |
          v
Ra khỏi khối try (bình thường / return / exception)
          |
          v
Tự gọi stream.close()
          |
          v
Giải phóng nguồn I/O theo hợp đồng của Stream
~~~

`close()` là thao tác **đóng lifecycle của Stream** và kích hoạt các close handlers. Với Stream không có I/O hoặc close handler, việc đóng có thể không tạo ra hành động quan sát được. Với Stream từ `Files.lines`/`list`, nó có vai trò giải phóng nguồn gắn với I/O.

### 3.2. Terminal operation không tự đóng Stream

~~~java
Stream<String> lines = Files.lines(path);
long total = lines.count();
~~~

Sau `count()`, Stream đã được tiêu thụ cho mục đích xử lý, nhưng **không có quy tắc terminal operation sẽ tự gọi `close()`**. Nếu code không đóng `lines` thì vẫn có nguy cơ giữ handle đến thời điểm không mong muốn.

Phải dùng:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long total = lines.count();
    System.out.println(total);
}
~~~

Với `findFirst()`, `limit(n)` hoặc `anyMatch()`, pipeline có thể **short-circuit** và không đọc hết nguồn, nên việc đóng ở cuối block càng quan trọng.

### 3.3. Đóng Stream không có nghĩa tự động xóa file

`close()` giải phóng tài nguyên đọc/duyệt do Stream sở hữu; nó **không xóa file** và không nhất thiết giải quyết những resource ngoài Stream mà bạn tự tạo. Các thao tác tạo, ghi, xóa file thuộc hợp đồng riêng của `Files` và resource tương ứng.

Nếu bạn tạo thêm `BufferedReader`, `InputStream` hoặc database resource rồi gắn một Stream của riêng mình, phải xác định **ai sở hữu** từng đối tượng, không mặc định `stream.close()` sẽ đóng tất cả resource tùy ý.

## 4. Dùng `Files.lines` đúng cách

`Files.lines(Path)` và `Files.lines(Path, Charset)` tạo Stream các dòng của file, phục vụ xử lý lazy. Thay vì tải toàn bộ file qua `Files.readAllLines`, chương trình có thể lọc, đếm hoặc chuyển đổi từng dòng khi cần. Đây là lý do Stream thường thích hợp với file lớn, đồng thời cần được đóng cẩn thận.

### 4.1. Mẫu nên dùng

~~~java
Path file = Path.of("data.txt");

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Đây là **mảnh mã trong method** có import `Path`, `Files`, `StandardCharsets`, `Stream` và xử lý `IOException`. Nó giả định `data.txt` tồn tại. Cách dùng `StandardCharsets.UTF_8` làm rõ encoding thay vì phụ thuộc suy đoán từ môi trường.

Khi khối kết thúc, `lines.close()` được gọi. Nếu `filter` hoặc `count` ném runtime exception, `try-with-resources` vẫn thực hiện đóng Stream.

### 4.2. Lỗi khi dùng `Files.lines`

Phương thức tạo Stream `Files.lines(...)` có thể ném `IOException`; những lỗi I/O **phát sinh trong quá trình duyệt** có thể được biểu diễn thành `UncheckedIOException` vì các hàm của Stream API không khai báo checked exception. Cần phân biệt **thời điểm** và **kiểu ngoại lệ**:

- Gọi `Files.lines(file)`: có thể ném `IOException` khi mở file.
- Duyệt `filter`/`map`/`count`/`toList`: lỗi I/O về sau có thể xuất hiện dưới dạng `UncheckedIOException`.
- Khi đóng và chạy close handlers: cũng có thể có lỗi trong quá trình cleanup; phải chú ý exception propagation và suppressed exceptions.

Một mẫu xử lý:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    // Lỗi I/O xảy ra khi duyệt, xem ex.getCause().
    System.err.println("Read failed: " + ex.getCause());
} catch (IOException ex) {
    // Lỗi checked khi tạo/mở tài nguyên.
    System.err.println("Open failed: " + ex);
}
~~~

Đây là **mảnh mã có `path` hợp lệ**. Không viết logic nghiệp vụ chỉ dựa vào giả định mọi lỗi I/O đều có cùng kiểu và cùng thời điểm. `UncheckedIOException` là unchecked, và việc catch chỉ để in message chưa chắc đáp ứng yêu cầu xử lý trong ứng dụng thực.

### 4.3. Tránh đưa tài nguyên ra ngoài phạm vi đóng

Mã sau **sai về lifecycle** dù cấu trúc Java có thể biên dịch:

~~~java
static Stream<String> broken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    }
}
~~~

Ngay lúc method trả về, khối `try` kết thúc, Stream đã được đóng. Caller nhận một pipeline trỏ tới nguồn đã bị đóng; cố thực thi sau đó có thể thất bại vì Stream đã được đóng hoặc nguồn I/O không còn dùng được.

Nếu caller chỉ cần một danh sách nhỏ, có thể **vật hóa kết quả trong `try`**:

~~~java
static List<String> readNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).toList();
    }
}
~~~

`toList()` là terminal operation; dữ liệu kết quả được tạo **trước khi** Stream đóng. `List` được trả ra không còn phụ thuộc stream I/O. `Stream.toList()` trong Java 17 trả danh sách unmodifiable; nếu cần sửa, tạo collection mới rõ ràng. Với file rất lớn, vật hóa toàn bộ kết quả có thể tốn bộ nhớ; hãy cân nhắc trả kết quả tổng hợp, xử lý qua callback hoặc chuyển quyền sở hữu Stream cho caller (xem phần 8).

## 5. Duyệt thư mục với `Files.list`, `Files.walk` và `Files.find`

### 5.1. `Files.list` — liệt kê một mức

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> names = paths
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
~~~

Đây là **mảnh mã** có `directory` kiểu `Path` trỏ tới thư mục hợp lệ, với import phù hợp và `IOException` được xử lý. `Files.list` là nguồn gắn với một directory stream; kết quả duyệt không có thứ tự cố định theo hợp đồng, nên ví dụ dùng `sorted()` trước khi in.

**Không** đổi `Files.list(directory).forEach(...)` thành một dòng nếu điều đó khiến tài nguyên không được đóng. Cách gọn đúng là mở trong `try-with-resources` rồi thao tác trong block.

### 5.2. `Files.walk` — duyệt cây thư mục

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    long count = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(count);
}
~~~

Đoạn code là **mảnh mã** với `root` kiểu `Path` và xử lý `IOException`. `Files.walk` có thể cần giữ các directory handles trong quá trình duyệt cây, nên rất cần đóng.

Theo mặc định, `Files.walk` **không tự đi theo symbolic link** nếu không chỉ định `FileVisitOption.FOLLOW_LINKS`. Khi theo liên kết, cần cân nhắc vòng lặp, quyền truy cập và lỗi I/O. Với cây lớn, duyệt có thể tốn thời gian và gặp file bị xóa/đổi quyền khi đang chạy.

Nếu chỉ muốn duyệt một độ sâu nhất định, có overload `Files.walk(root, maxDepth)`. Không nên dùng `Files.walk(root)` vô điều kiện trên thư mục hệ thống rất lớn.

### 5.3. `Files.find` — lọc theo thông tin file khi duyệt

~~~java
try (Stream<Path> files = Files.find(root, 3,
        (path, attrs) -> attrs.isRegularFile()
                && path.toString().endsWith(".java"))) {
    long javaFiles = files.count();
    System.out.println(javaFiles);
}
~~~

Đây là mảnh mã trong method có `root` kiểu `Path` hợp lệ. `Files.find` dùng `BiPredicate<Path,BasicFileAttributes>` để chọn phần tử, và cũng trả một Stream cần đóng. Kết quả trên phụ thuộc trạng thái cây thư mục thật, nên không có stdout cố định cho đoạn minh họa.

### 5.4. So sánh nhanh

| API | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `Files.lines` | Duyệt dòng văn bản | Charset, lỗi đọc trong quá trình duyệt, đóng nguồn |
| `Files.list` | Mục con trực tiếp của thư mục | Không đảm bảo thứ tự; handle thư mục cần đóng |
| `Files.walk` | Duyệt cây thư mục | Độ sâu, symlink, lỗi truy cập, handle cần đóng |
| `Files.find` | Duyệt cây và lọc theo attributes | Predicate/độ sâu, nguồn I/O cần đóng |

## 6. Chương trình Java 17 độc lập: đóng Stream sau khi dùng

Chương trình tạo thư mục tạm và hai file mẫu, đọc nội dung, liệt kê file, rồi dọn file tạm. Tên thư mục được Java tạo ngẫu nhiên nhưng **không in ra**, nên kết quả stdout có thể kiểm chứng chính xác.

Tạo tệp **`StreamResourceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class StreamResourceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("stream-close-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");

        try {
            Files.writeString(
                    a, "Java\n\nLambda\nStream\n",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    b, "notes\n",
                    StandardCharsets.UTF_8);

            // Nguồn là file, dùng try-with-resources.
            try (Stream<String> lines = Files.lines(
                    a, StandardCharsets.UTF_8)
                    .onClose(() -> System.out.println("lines closed"))) {
                long nonBlank = lines
                        .filter(s -> !s.isBlank())
                        .count();

                System.out.println("nonblank=" + nonBlank);
            }

            // Nguồn là directory, cũng cần đóng.
            try (Stream<Path> paths = Files.list(dir)
                    .onClose(() -> System.out.println("paths closed"))) {
                List<String> names = paths
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();

                System.out.println("files=" + names);
            }
        } finally {
            // Cleanup riêng; close() không xóa file.
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 StreamResourceDemo.java
java StreamResourceDemo
~~~

**Stdout chính xác trong điều kiện chạy thành công với thư mục tạm mới tạo:**

~~~text
nonblank=3
lines closed
files=[a.txt, b.txt]
paths closed
~~~

Giải thích:

1. `Files.writeString` tạo `a.txt` với 4 dòng gồm `Java`, dòng rỗng, `Lambda`, `Stream`; chỉ 3 dòng không rỗng nên `nonblank=3`.
2. Terminal `count()` kết thúc pipeline **nhưng không đóng Stream**. Khi ra khỏi block `try`, close handler do `onClose` đăng ký chạy và in `lines closed`.
3. `Files.list(dir)` cung cấp hai đường dẫn. `sorted()` bảo đảm danh sách tên được in theo `a.txt` rồi `b.txt`, thay vì phụ thuộc thứ tự trả về của hệ thống file.
4. Ra khỏi block duyệt thư mục, close handler in `paths closed`.
5. `finally` dọn file và thư mục. Việc xóa riêng này không phải chức năng của `Stream.close()`. Nếu việc tạo file hoặc cleanup thất bại do quyền truy cập/điều kiện môi trường, chương trình có thể ném `IOException` và không in đúng toàn bộ kết quả; đây là chương trình chạy trên hệ thống file thật.

Trong ví dụ, `onClose` được dùng để **quan sát thời điểm đóng**, không phải để thay thế `try-with-resources`. Khi dùng sản xuất, bạn thường không cần in thông báo mỗi lần close; việc đóng quan trọng là giải phóng resource.

## 7. `onClose` — đăng ký hành động khi đóng Stream

`BaseStream.onClose(Runnable closeHandler)` trả một Stream có handler sẽ chạy khi Stream được đóng. Nó thường được dùng cho logic cleanup hoặc theo dõi vòng đời, đặc biệt khi tự kết hợp nguồn dữ liệu với tài nguyên bên ngoài.

~~~java
try (Stream<String> s = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"))) {
    System.out.println(s.count());
}
~~~

Stdout:

~~~text
2
closed
~~~

Vì `Stream.of` không giữ file handle, close handler là lý do hiển thị `closed`. Terminal `count()` không kích hoạt handler; chỉ khi ra khỏi `try`, Stream được đóng.

### 7.1. Nhiều handler: thứ tự đăng ký

Khi có nhiều handler đăng ký qua `onClose`, Java chạy theo **thứ tự đăng ký**:

~~~java
try (Stream<String> stream = Stream.of("x")
        .onClose(() -> System.out.println("first"))
        .onClose(() -> System.out.println("second"))) {
    stream.count();
}
~~~

Stdout:

~~~text
first
second
~~~

Nếu một handler ném exception, các handler khác vẫn được thực thi; ngoại lệ đầu tiên được đưa ra và các lỗi sau có thể được gắn ở dạng **suppressed exceptions**. Vì vậy, handler cleanup nên đơn giản, có hợp đồng lỗi rõ và tránh tác dụng phụ phức tạp. `Stream.close()` có ngữ nghĩa idempotent với việc chạy close handlers: đóng lặp lại một Stream đã đóng không làm handler chạy lại lần nữa.

### 7.2. Liên kết `onClose` với resource khác

Nếu bạn tự tạo Stream từ một nguồn có tài nguyên ngoài, có thể dùng:

~~~java
Stream<String> stream = makeStreamFromResource(resource)
        .onClose(resource::close);
~~~

Đây là **sơ đồ API minh họa, không chạy độc lập**: phải định nghĩa `makeStreamFromResource` và kiểu `resource` phù hợp; `Runnable` close handler không được khai báo checked exception. Nếu `resource.close()` ném checked exception, method reference `resource::close` có thể **không tương thích `Runnable`**, nên cần xử lý exception hoặc thiết kế lớp sở hữu tài nguyên khác. Đừng gắn handler hai lần nếu đã có một Stream từ `Files` tự đóng đúng resource.

Nếu resource có vòng đời phức tạp, quản lý tường minh từng resource bằng `try-with-resources` thường minh bạch hơn.

## 8. Quyền sở hữu tài nguyên: đóng ở tầng nào?

### 8.1. Nguyên tắc cơ bản

**Tầng tạo Stream gắn với tài nguyên phải xác định rõ ai đóng nó.** Một phương thức có thể:

1. **Sở hữu toàn bộ vòng đời:** tạo, tiêu thụ, đóng Stream bên trong; trả kết quả đã tính.
2. **Chuyển quyền sở hữu cho caller:** trả về Stream còn mở và **ghi rõ caller phải đóng** bằng `try-with-resources`.
3. **Nhận callback xử lý:** tạo Stream, gọi callback bên trong block `try` rồi đóng trước khi trả một kết quả bình thường.

Dạng 1 thường dễ dùng nhất khi chỉ cần số đếm, kết quả tổng hợp hoặc một danh sách phù hợp bộ nhớ.

### 8.2. Helper trả kết quả đã tính

~~~java
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).count();
    }
}
~~~

Việc `return` xuất hiện trong khối `try` không bỏ qua cleanup: Java vẫn gọi `close()` **trước khi method thực sự trả kết quả**. Method này không để Stream thoát ra ngoài.

### 8.3. Helper trả Stream: caller phải đóng

~~~java
static Stream<String> openNonBlank(Path path) throws IOException {
    return Files.lines(path).filter(s -> !s.isBlank());
}
~~~

Đây là method **chuyển quyền sở hữu tài nguyên**. Nếu chọn thiết kế như vậy, caller phải được thông báo rõ:

~~~java
try (Stream<String> lines = openNonBlank(path)) {
    lines.forEach(System.out::println);
}
~~~

Close trên Stream kết quả của pipeline sẽ đóng toàn bộ pipeline liên quan đến nguồn Stream ban đầu và các close handlers. Không nên gọi `openNonBlank(path).toList()` một cách tùy tiện mà không có cơ chế close rõ ràng.

Trong API công khai, Javadoc nên nêu: *Returned Stream must be closed by the caller*. Cần thận trọng nếu caller có thể lưu Stream và chỉ sử dụng sau, vì thời gian giữ resource mở trở nên khó kiểm soát.

### 8.4. Helper nhận callback và đảm bảo đóng

Nếu không muốn caller quản lý Stream trực tiếp, có thể nhận một hàm xử lý:

~~~java
static <R> R withLines(
        Path path, Function<Stream<String>, R> action)
        throws IOException {
    Objects.requireNonNull(action, "action");
    try (Stream<String> lines = Files.lines(path)) {
        return action.apply(lines);
    }
}
~~~

Đây là method minh họa với import `Path`, `Files`, `Function`, `Objects` và `Stream`. Nó đóng Stream khi callback hoàn tất, trả giá trị hoặc ném unchecked exception. **Không** để callback trả về chính Stream còn cần duyệt sau block, vì kết quả ấy sẽ trỏ tới Stream đã đóng. Nếu callback cần ném checked exception khác `IOException`, phải thiết kế hợp đồng lambda riêng cho trường hợp đó.

Ví dụ dùng với kết quả `Long`:

~~~java
long count = withLines(path,
        lines -> lines.filter(s -> !s.isBlank()).count());
~~~

Cách này chuyển trách nhiệm resource về helper mà vẫn cho caller lựa chọn hành động trong phạm vi an toàn.

## 9. Lazy evaluation và đóng tài nguyên

### 9.1. Thao tác trung gian chưa duyệt dữ liệu

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Stream<String> filtered =
            lines.filter(s -> s.startsWith("A"));

    // Chưa có terminal operation: filter chưa duyệt hết dữ liệu.
}
~~~

Khi thoát `try`, Stream nguồn được đóng, kể cả khi chưa có phần tử nào được đọc. Điều này quan trọng nếu một Stream lazy được tạo nhưng không bao giờ đi tới terminal operation: **vẫn phải đóng** nếu nó giữ resource.

### 9.2. Short-circuit vẫn phải đóng

~~~java
try (Stream<String> lines = Files.lines(path)) {
    boolean found =
            lines.anyMatch(s -> s.contains("ERROR"));
    System.out.println(found);
}
~~~

`anyMatch` có thể dừng ngay khi gặp dòng phù hợp, không tiêu thụ hết file. `try-with-resources` đóng nguồn ở cuối block. Điều này cũng áp dụng với `findFirst`, `limit`, `findAny` và các pipeline có thể kết thúc sớm.

### 9.3. Stream không được tái sử dụng sau khi tiêu thụ

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    // long second = lines.count(); // Sai: Stream đã tiêu thụ.
}
~~~

Stream thường chỉ được xử lý qua một pipeline một lần. Gọi lại terminal operation hoặc thao tác sau khi Stream đã được tiêu thụ/đóng có thể ném `IllegalStateException`. Khi cần phân tích dữ liệu hai lần, hãy mở Stream mới và đóng nó riêng, hoặc vật hóa kết quả vào collection nếu kích thước cho phép.

Đừng dùng lại một Stream đã xử lý chỉ vì object Java vẫn còn được biến tham chiếu giữ.

## 10. Ngoại lệ khi dùng `try-with-resources`

### 10.1. Khối `try` hoặc `close` có thể lỗi

`try-with-resources` bảo đảm có nỗ lực đóng resource đã tạo thành công khi thoát khỏi khối, bao gồm cả khi callback/lambda ném runtime exception. Nếu `close()` hoặc close handler cũng ném exception, Java áp dụng quy tắc về **suppressed exception**:

- Nếu thân `try` ném exception chính và đóng resource lại lỗi, lỗi khi đóng thường được gắn vào exception chính qua `getSuppressed()`.
- Nếu thân `try` hoàn tất bình thường nhưng đóng lỗi, exception của bước đóng có thể là exception được ném ra.
- Khi nhiều resource được khai báo trong cùng `try-with-resources`, chúng được đóng theo **thứ tự ngược** với thứ tự khởi tạo, và các lỗi đóng có thể bị suppressed.

Không bắt lỗi tràn lan rồi bỏ qua `getSuppressed()` khi cần điều tra các sự cố đọc/đóng file phức tạp.

### 10.2. Nhiều resource trong một khối

~~~java
try (BufferedReader reader = Files.newBufferedReader(path);
     Stream<String> lines = reader.lines()) {
    lines.forEach(System.out::println);
}
~~~

Đây là **mảnh mã minh họa** có xử lý `IOException`, và **reader** là resource thực sự được đăng ký đóng. `BufferedReader.lines()` trả Stream các dòng nhưng **không được dùng Stream.close() thay thế cho reader.close()**; trong ví dụ, `try-with-resources` đóng `reader` độc lập. Thứ tự đóng là `lines` trước, `reader` sau.

Điểm này khác với `Files.lines(path)`, nơi Stream trả về được thiết kế để đóng nguồn file gắn bên dưới. Khi nguồn là `Reader` do bạn sở hữu, hãy quản lý rõ Reader, thay vì suy đoán Stream luôn đóng hộ.

### 10.3. Phân biệt lỗi mở và lỗi khi duyệt

Với `Files.lines`, `Files.list`, `Files.walk`, mở nguồn có thể ném `IOException`; khi thực hiện traversal, lỗi I/O có thể được chuyển thành `UncheckedIOException`. Tài liệu có thể quy định chi tiết khác nhau cho từng API; không nên viết một catch duy nhất rồi khẳng định nó bao phủ mọi trường hợp. Việc truyền lỗi, hủy tác vụ và dọn resource nên được kiểm thử trên các tình huống file bị thiếu, bị khóa, thiếu quyền, hoặc bị thay đổi trong lúc duyệt.

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `Files.lines(path).count()` không đóng | Có nguy cơ giữ file handle | Đặt Stream vào `try-with-resources` |
| Tin rằng `count()`/`toList()` tự đóng | Terminal operation tiêu thụ, không cam kết close | Luôn đóng nguồn có resource |
| Trả Stream ra khỏi `try` đã đóng | Caller nhận pipeline trên resource đã đóng | Trả kết quả, hoặc chuyển ownership rõ |
| Dùng `Stream` hai lần | Stream bị tiêu thụ/đóng | Tạo nguồn mới hoặc lưu kết quả |
| Dùng `findFirst()` rồi bỏ Stream | Short-circuit không tự close | Dùng `try-with-resources` |
| Cho rằng Stream collection nào cũng cần close | Không phải mọi Stream giữ I/O | Xem API tạo nguồn và Javadoc |
| Dùng `Files.list`/`walk` không đóng | Có thể rò rỉ handle thư mục | Dùng `try (Stream<Path> ...)` |
| Phụ thuộc thứ tự `Files.list` | Directory traversal không đảm bảo order | `sorted()` nếu cần thứ tự |
| Quên đóng `BufferedReader` nhưng đóng `reader.lines()` | Đóng Stream đó không được xem là thay thế Reader.close | Đưa Reader vào `try-with-resources` |
| Dùng `onClose` thay cho `try-with-resources` | Handler chỉ chạy nếu có `close()` | Vẫn phải có nơi gọi close rõ |
| Bắt hết exception rồi nuốt | Mất nguyên nhân, bỏ lỡ lỗi cleanup | Catch có chủ đích, giữ cause/suppressed |
| Cho rằng `close()` xóa file | Close giải phóng resource, không delete dữ liệu | Xóa bằng API riêng nếu thực sự cần |
| Tạo pipeline lazy rồi không tiêu thụ nên không cần close | Nguồn vẫn có thể giữ resource | Đóng ngay cả khi không chạy terminal |
| Trả Stream từ callback của helper rồi dùng sau | Stream đã đóng khi helper trả về | Đừng để Stream thoát khỏi scope |
| Mở Stream từ quá nhiều file cùng lúc | Có thể hết handle hệ điều hành | Xử lý theo scope nhỏ, đóng từng nguồn |

## 12. Checklist rà soát code

Khi một phương thức **tạo Stream**, hãy hỏi:

1. Stream có nguồn từ `Collection`/`Stream.of` hay từ `Files`/I/O?
2. Javadoc API nguồn có yêu cầu đóng Stream không?
3. Nếu có, `try-with-resources` bao toàn bộ quá trình **tạo, biến đổi, terminal operation** chưa?
4. Có `return` sớm, exception hoặc short-circuit không? Close vẫn diễn ra đúng nơi chứ?
5. Có trả Stream cho caller không? Nếu có, **ai là owner** và Javadoc có ghi rõ caller phải close không?
6. Có vô tình trả Stream/iterator/spliterator phụ thuộc nguồn **ra khỏi scope đã đóng** không?
7. Khi nguồn là `BufferedReader`/`InputStream` riêng, có đóng chính resource đó không?
8. Có dùng `onClose` không? Handler có được gọi chắc chắn thông qua một lệnh close không?
9. Có nhiều resource không? Thứ tự đóng và suppressed exception đã được cân nhắc chưa?
10. Có đang dựa vào thứ tự directory traversal không? Có cần `sorted()`?
11. Có thể gặp lỗi I/O trong quá trình traversal lazy không? Đã xử lý `IOException` và `UncheckedIOException` theo hợp đồng?
12. Có thử chạy với file rỗng, thiếu file, thư mục rỗng, thoát sớm và lỗi quyền truy cập không?
13. Có vô tình tiêu thụ Stream hai lần hoặc dùng Stream sau khi đóng không?
14. Có đang giữ file handle lâu hơn cần thiết do lồng nhiều pipeline hoặc trả Stream khỏi tầng tạo không?

## 13. Bài tập thực hành

### Bài 1 — Đếm dòng có nội dung

Tạo file UTF-8 có 5 dòng, trong đó 2 dòng trắng. Viết method `static long countNonBlank(Path path) throws IOException` dùng `Files.lines` trong `try-with-resources`, `filter(s -> !s.isBlank())` và `count()`. Kết quả mong đợi: `3`. Giải thích vì sao không nên gọi `Files.lines(path).filter(...).count()` trực tiếp mà không close.

### Bài 2 — Tìm dòng đầu tiên và đóng

Dùng `Files.lines(path)` cùng `filter`/`findFirst()` để tìm dòng đầu chứa `"ERROR"`. Dù tìm thấy ngay ở dòng đầu, chứng minh đoạn `try-with-resources` vẫn gọi close khi ra khỏi scope. Thử gắn `onClose(() -> System.out.println("closed"))` để quan sát.

### Bài 3 — Liệt kê file theo tên

Tạo thư mục mẫu chứa `b.txt`, `a.txt`. Dùng `Files.list(dir)` trong `try-with-resources`, lấy `getFileName()`, `sorted()` và `toList()`. Dự đoán đầu ra `[a.txt, b.txt]`. Thử bỏ `sorted()` và giải thích vì sao thứ tự in không còn được đảm bảo.

### Bài 4 — Refactor method trả Stream đã đóng

Sửa method:

~~~java
static Stream<String> bad(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    }
}
~~~

Có hai hướng sửa: (a) trả `List<String>` bằng `toList()` trong block `try`, hoặc (b) trả Stream còn mở và yêu cầu caller đóng. Hãy viết Javadoc mô tả ownership cho phương án (b).

### Bài 5 — Reader và Stream

Dùng `Files.newBufferedReader(path)` trong `try-with-resources` và duyệt `reader.lines()`. Giải thích vì sao cần bảo đảm `reader.close()` thay vì giả định Stream được tạo từ `reader.lines()` đóng cả Reader.

### Bài 6 — Thử lỗi và suppressed exception

Tự tạo một `AutoCloseable` có `close()` ném `IllegalStateException("close failed")` và thân `try` ném `IllegalArgumentException("body failed")`. Bắt exception chính, kiểm tra `getSuppressed()` để thấy lỗi lúc đóng không bị mất. Liên hệ với trường hợp Stream có `onClose` handler ném exception.

### Bài 7 — Duyệt cây thư mục có giới hạn

Dùng `Files.walk(root, 2)` để đếm file thường trong hai cấp độ bên dưới root. Đặt trong `try-with-resources`. Giải thích vì sao nên giới hạn độ sâu khi thư mục rất lớn và cách xử lý `UncheckedIOException` trong traversal.

### Bài 8 — Thiết kế API có quyền sở hữu

Viết hai cách: `countLines(Path)` trả `long` và `openLines(Path)` trả `Stream<String>`. Với cách thứ hai, viết ví dụ caller dùng `try (Stream<String> lines = openLines(path))`. Đánh giá trade-off giữa tiện dụng và trách nhiệm đóng tài nguyên.

## 14. Tổng kết và tài liệu tham khảo

**Stream có nguồn tài nguyên I/O phải được đóng đúng lúc.** `BaseStream` kế thừa `AutoCloseable` nên `try-with-resources` là cách chuẩn để tự gọi `close()` khi thoát scope. Với Stream từ `Files.lines`, `Files.list`, `Files.walk` và `Files.find`, hãy đặt phần **tạo nguồn và toàn bộ pipeline cần dùng** trong khối `try`; đừng mặc định `count()`/`toList()`/`findFirst()` đóng resource.

Phần lớn Stream từ collection/mảng không yêu cầu đóng vì tài nguyên ngoài, nhưng vẫn có thể có close handlers. `onClose` là điểm đăng ký callback cleanup khi đóng, không phải sự thay thế cho việc quản lý lifecycle. Nếu trả Stream ra khỏi method, hãy chuyển ownership rõ cho caller; nếu không, ưu tiên trả kết quả đã tính trong `try`. Với nguồn Reader do bạn tạo, đóng **Reader** đúng nơi sở hữu, không suy đoán Stream sẽ đóng hộ mọi resource bên dưới.

**Tài liệu chính thức nên tra cứu:** Javadoc Java SE 17 của `java.util.stream.BaseStream` và `Stream`; `java.nio.file.Files` (`lines`, `list`, `walk`, `find`); `java.io.BufferedReader` và `AutoCloseable`; Java Language Specification mục `14.20.3 try-with-resources`.
