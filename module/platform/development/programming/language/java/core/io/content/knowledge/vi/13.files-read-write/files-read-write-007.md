# READ, WRITE, CREATE, CREATE_NEW và TRUNCATE_EXISTING trong Java Files I/O

> **Bối cảnh:** Java Core → I/O → **Đọc ghi bằng Files**. Bài này giải thích các `StandardOpenOption` quan trọng khi mở tệp, sự khác biệt giữa đọc và ghi, tạo mới có hoặc không ghi đè, cắt nội dung tệp đã tồn tại và các giá trị **mặc định** của `Files`. Ví dụ độc lập dùng Java 17, tạo và dọn tệp tạm để không can thiệp vào dữ liệu thật.

## 1. Vì sao chế độ mở tệp quan trọng?

Một câu lệnh “ghi tệp” có thể mang các ý nghĩa hoàn toàn khác nhau:

- Chỉ ghi vào **tệp đã có**, nhưng không xóa phần đuôi còn lại.
- Tạo tệp nếu chưa có và ghi; nếu đã có thì ghi đè từ đầu.
- Tạo tệp nếu chưa có, nhưng **tuyệt đối từ chối** khi đường dẫn đã tồn tại.
- Mở tệp đã có rồi **xóa trắng trước khi ghi**.
- Chỉ đọc dữ liệu, **không** có quyền ghi và không thay đổi nội dung.

Trong Java NIO.2, các lựa chọn này được thể hiện bằng `java.nio.file.StandardOpenOption`, một enum triển khai giao diện `OpenOption`. Chúng thường là các đối số varargs truyền cho `Files.newInputStream`, `Files.newOutputStream`, `Files.write`, `Files.writeString` và những API mở channel khác. Mỗi API có **hợp đồng riêng**: không phải option nào cũng hợp lệ, và **mặc định khi bỏ qua options có thể khác nhau**.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.txt");
// Đây chỉ là fragment; đoạn sau phải ở trong method có xử lý IOException.
// Files.writeString(path, "hello",
//         StandardOpenOption.CREATE, StandardOpenOption.WRITE);
~~~

`Path.of(...)` chỉ tạo một đối tượng định danh đường dẫn; `Files.writeString(...)` mới thực hiện I/O. Hầu hết thao tác ghi có thể sửa dữ liệu vĩnh viễn, nên phải quyết định chế độ mở **trước** khi thao tác.

### 1.1. Năm option trọng tâm

| Option | Ý nghĩa khi dùng đúng ngữ cảnh | Điều **không** có nghĩa |
| --- | --- | --- |
| `READ` | Mở quyền **đọc** các byte trong tệp | Không tự tạo tệp khi thiếu, không tự cho phép ghi. |
| `WRITE` | Mở quyền **ghi** các byte vào tệp | Không tự tạo tệp hoặc xóa trắng nội dung nếu không có option tương ứng. |
| `CREATE` | **Nếu thiếu** thì tạo tệp; **nếu đã có** thì mở tệp đó | Không tự yêu cầu từ chối ghi đè và không đồng nghĩa truncate. |
| `CREATE_NEW` | Chỉ tạo tệp **mới**; nếu mục tiêu đã tồn tại, thao tác mở thất bại | Không phải “ghi đè tệp với nội dung mới”; không cho phép thay thế tên đang tồn tại. |
| `TRUNCATE_EXISTING` | Khi mở tệp đã tồn tại **để ghi**, đặt độ dài về **0** ngay ở bước mở | Không phải xóa file khỏi thư mục, không dùng để append và bị bỏ qua khi chỉ mở READ. |

**Mẹo ghi nhớ:** `WRITE` trả lời “được sửa byte không?”, `CREATE` trả lời “thiếu thì có được tạo không?”, `CREATE_NEW` trả lời “đã tồn tại thì phải thất bại không?”, `TRUNCATE_EXISTING` trả lời “đã tồn tại thì có xóa trắng ngay khi mở không?”. `READ` quyết định khả năng đọc và có thể đi cùng `WRITE` trên các API channel hỗ trợ cả hai chiều.

## 2. `READ` — chỉ đọc dữ liệu

Mở luồng đọc chuẩn:

~~~java
// Fragment nằm trong method throws IOException:
try (InputStream in = Files.newInputStream(path)) {
    int firstByte = in.read();
}
~~~

Cần import `java.io.InputStream`, `java.nio.file.Files` và `java.nio.file.Path`. Không truyền option nào vào `Files.newInputStream(path)` nghĩa là **mở để đọc**. Bạn cũng có thể viết `Files.newInputStream(path, StandardOpenOption.READ)`. Nếu tệp không có, thường nhận `NoSuchFileException`; nếu không có quyền đọc hoặc xảy ra lỗi khác, nhận một dạng `IOException` thích hợp.

`READ` **không tạo tệp**. Đừng mong `Files.newInputStream(path, CREATE)` trở thành “mở để đọc, nếu chưa có thì tạo rỗng”; input-stream factory không có nghĩa đó. Những option không được API hỗ trợ có thể gây `UnsupportedOperationException` hoặc kết hợp sai gây `IllegalArgumentException`.

Khi đọc text có charset rõ ràng:

~~~java
// Fragment Java 11+: method throws IOException.
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

`Files.readString` tự mở/đọc/đóng file nội bộ, không nhận `StandardOpenOption...` tùy ý. Muốn đọc theo nhiều chế độ, phải chọn API mở stream/channel có options thích hợp.

### 2.1. READ không làm thay đổi file

Ở tầng `SeekableByteChannel` hoặc `FileChannel`, một channel mở **chỉ READ** không cho phép write; gọi `write` có thể ném `NonWritableChannelException`. `TRUNCATE_EXISTING` bị **bỏ qua khi mở chỉ READ** theo contract của channel. Điều này không có nghĩa dùng READ+TRUNCATE để xóa file; không hề xóa nội dung nếu đó là channel chỉ đọc.

## 3. `WRITE` — cho phép ghi, nhưng không mặc nhiên tạo hoặc truncate

Ví dụ chỉ mở để ghi tệp **đã tồn tại**:

~~~java
// Fragment; method throws IOException.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.WRITE)) {
    out.write("XY".getBytes(StandardCharsets.UTF_8));
}
~~~

Cần import `java.io.OutputStream` và `java.nio.charset.StandardCharsets`. Với tệp ban đầu chứa ASCII `ABCDE`, nếu ghi `XY` từ vị trí đầu mà **không** truncate, nội dung có thể thành `XYCDE`. Cùng nguyên tắc áp dụng khi dùng `FileChannel`: khi mở thông thường, vị trí ghi bắt đầu ở đầu file, chứ **không tự đến cuối**.

Điều cần nhớ:

- `WRITE` **không tương đương** `CREATE`: nếu file thiếu và không yêu cầu tạo, mở để ghi có thể thất bại với `NoSuchFileException`.
- `WRITE` **không tương đương** `TRUNCATE_EXISTING`: nếu bạn ghi chuỗi ngắn hơn byte cũ, phần dư cũ **có thể vẫn còn**.
- `WRITE` **không đồng nghĩa append**: muốn viết tiếp cuối file dùng `APPEND` ở các API hỗ trợ hoặc đặt vị trí bằng channel. `APPEND` có quy tắc kết hợp riêng.
- Độ dài một lần gọi `write` **không nói** chắc đã ghi hết trong API channel: `SeekableByteChannel.write(ByteBuffer)` có thể ghi số byte nhỏ hơn số được yêu cầu; với channel cần lặp đến khi `ByteBuffer.hasRemaining() == false`. `OutputStream.write(byte[])` thông thường ghi tất cả byte của mảng hoặc ném IOException.
- `WRITE` không quyết định charset của văn bản. Với `byte[]`, caller encode; với `Files.writeString`, bạn chỉ định charset hoặc theo mặc định API đó.

## 4. `CREATE` — tạo nếu thiếu, dùng tệp hiện có nếu đã tồn tại

`CREATE` thường đi cùng `WRITE`:

~~~java
// Fragment: tạo tệp thiếu, hoặc ghi từ đầu tệp đã tồn tại.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {
    out.write("hi".getBytes(StandardCharsets.UTF_8));
}
~~~

Nếu tệp chưa tồn tại và có quyền, nó được tạo. Nếu tệp đã tồn tại, nó được mở cho ghi. **Chỉ `CREATE` và `WRITE` không buộc truncate**; khi ghi ngắn hơn nội dung cũ, phần đuôi có thể còn như ví dụ `XYCDE`.

`CREATE` không làm cha tự xuất hiện: nếu `path` là `logs/2026/app.log` mà thư mục cha `logs/2026` không tồn tại, việc tạo file vẫn có thể thất bại. Khi ứng dụng có trách nhiệm tạo thư mục, dùng `Files.createDirectories(path.getParent())` sau khi xác định parent khác `null` và kiểm tra chính sách đường dẫn.

**Khi nào chọn?** Một ứng dụng ghi định kỳ vào một tệp cố định **được phép đã tồn tại** có thể chọn `CREATE + WRITE + TRUNCATE_EXISTING` nếu muốn thay toàn bộ nội dung. Nếu muốn giữ phần cũ và thêm bản ghi, dùng `CREATE + APPEND` theo contract API. Nếu **không** cho phép tên trùng, dùng `CREATE_NEW` thay vì `CREATE`.

## 5. `CREATE_NEW` — tạo mới độc quyền và kiểm tra tồn tại nguyên tử

`CREATE_NEW` được dùng khi **không muốn ghi đè bất kỳ entry nào có sẵn** tại tên đích:

~~~java
// Fragment: method throws IOException.
Files.writeString(
        path, "new-data", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

Nếu tên đích đã tồn tại, bao gồm trường hợp chính entry đó là **symbolic link**, việc mở với `CREATE_NEW` phải thất bại. Thường nhận `FileAlreadyExistsException`, tuy Javadoc cho phép IOException phù hợp tùy provider; không nên bắt tất cả IOException rồi tự cho rằng đó là “tệp đã tồn tại”.

**Tại sao `CREATE_NEW` tốt hơn đoạn `if (!Files.exists(path)) ...`?** Bởi kiểm tra tồn tại rồi tạo thành **hai thao tác**, có cửa sổ race giữa chúng. `CREATE_NEW` đưa yêu cầu “chỉ tạo nếu chưa tồn tại” vào một thao tác mở/tạo có kiểm tra và tạo **atomic đối với các thao tác filesystem khác** theo contract.

~~~java
// PHẢN VÍ DỤ DỄ RACE; không dùng làm bảo đảm không ghi đè.
if (!Files.exists(path)) {
    Files.writeString(path, content);
    // Tên đích có thể được tạo bởi thread/process khác giữa hai dòng.
}
~~~

Thay bằng:

~~~java
// Fragment: content là String do caller chuẩn bị.
try {
    Files.writeString(
        path, content, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException ex) {
    // Quy tắc nghiệp vụ: báo tên trùng, đổi tên, hoặc từ chối yêu cầu.
}
~~~

Các đoạn trên cần import `java.nio.file.FileAlreadyExistsException`, `java.nio.file.Files` và các kiểu liên quan. Nếu một provider không dùng chính subclass `FileAlreadyExistsException` cho tình huống này, vẫn phải xử lý IOException tại ranh giới I/O.

### 5.1. Atomic creation không phải atomic content replacement

`CREATE_NEW` chỉ bảo đảm **bước kiểm tra tên và tạo entry mới** là atomic theo contract. Nó **không** bảo đảm toàn bộ dữ liệu ghi sau đó xuất hiện đồng thời, không bảo đảm crash-safe, không fsync và không là transaction. Một exception sau khi tạo tệp có thể để lại tệp **đã tồn tại nhưng chỉ chứa một phần dữ liệu**. Với dữ liệu quan trọng, thiết kế cleanup cho file mới tạo thất bại và giao thức publish nội dung hoàn chỉnh.

### 5.2. Kết hợp `CREATE` và `CREATE_NEW`?

Khi cả hai cùng hiện diện, `CREATE_NEW` **ưu tiên**, `CREATE` bị bỏ qua theo API. Không phải cách “vừa tạo mới vừa ghi đè nếu có”: đã tồn tại vẫn thất bại. Chỉ viết `CREATE_NEW` là rõ ý định hơn.

## 6. `TRUNCATE_EXISTING` — xóa trắng nội dung cũ trước khi ghi

`TRUNCATE_EXISTING` dùng với quyền ghi để đặt chiều dài tệp hiện có về **0 byte ngay khi mở**:

~~~java
// Fragment: muốn thay nội dung file đã tồn tại, không cho tạo file thiếu.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    out.write("OK".getBytes(StandardCharsets.UTF_8));
}
~~~

Nếu file trước đó là `ABCDE`, sau thao tác thành công nội dung là `OK`, không phải `OKCDE`. Nếu file chưa tồn tại, việc không có `CREATE` hoặc `CREATE_NEW` có thể dẫn tới `NoSuchFileException`.

Kết hợp phổ biến để **tạo nếu chưa có, thay toàn bộ nếu có**:

~~~java
Files.writeString(
    path, "full replacement", StandardCharsets.UTF_8,
    StandardOpenOption.CREATE,
    StandardOpenOption.WRITE,
    StandardOpenOption.TRUNCATE_EXISTING);
~~~

**Rủi ro lớn:** truncate diễn ra **khi mở**, trước khi bạn viết hết dữ liệu mới. Nếu đọc nguồn lỗi, process bị dừng, hết dung lượng ổ đĩa hoặc writer thất bại, dữ liệu cũ **đã có thể bị mất**. Vì vậy `CREATE+TRUNCATE_EXISTING` không phải cơ chế cập nhật an toàn tuyệt đối cho file quan trọng.

**TRUNCATE_EXISTING không phải DELETE:** tên file và entry còn tồn tại, chỉ size/contents bị thay đổi. Khi mở chỉ đọc bằng channel, tùy chọn này **bị bỏ qua**; đừng mong `READ + TRUNCATE_EXISTING` cắt tệp.

## 7. Ma trận tình huống theo ý định nghiệp vụ

Giả định đối tượng đích là file thường trên provider hỗ trợ các option chuẩn, không có xung đột quyền hoặc I/O error khác.

| Mong muốn | Ví dụ API và options | Nếu tệp chưa có | Nếu tệp đã có |
| --- | --- | --- | --- |
| Chỉ đọc | `Files.newInputStream(path, READ)` | Thất bại | Đọc, không ghi |
| Ghi đè từ đầu **không xóa phần đuôi** | `newOutputStream(path, WRITE)` | Thất bại | Ghi bắt đầu từ đầu; phần dư có thể còn |
| Tạo nếu thiếu, ghi từ đầu không mặc định truncate | `newOutputStream(path, CREATE, WRITE)` | Tạo mới | Ghi đè từ đầu, có thể còn đuôi |
| Chỉ tạo tên mới, chống trùng | `newOutputStream(path, CREATE_NEW, WRITE)` | Tạo mới | Thất bại |
| Chỉ ghi đè hoàn toàn file đang tồn tại | `newOutputStream(path, WRITE, TRUNCATE_EXISTING)` | Thất bại | Xóa size về 0 trước khi ghi |
| Tạo nếu thiếu hoặc thay nội dung nếu đã có | `newOutputStream(path, CREATE, WRITE, TRUNCATE_EXISTING)` | Tạo mới | Truncate rồi ghi |
| Đọc và ghi qua một channel | `newByteChannel(path, EnumSet.of(READ,WRITE))` | Thất bại | Có thể đọc/ghi, không tự truncate |
| Mặc định ghi ngắn gọn | `Files.writeString(path, text, UTF_8)` | Tạo mới | Truncate rồi ghi |
| Thêm nội dung vào cuối | `Files.writeString(path, text, UTF_8, WRITE, APPEND)` | Thất bại nếu thiếu CREATE | Giữ dữ liệu cũ rồi append |

**Chú ý:** hàng cuối dùng `APPEND` như một đối chiếu, không phải một trong năm option chủ đề. Khi muốn “thêm nếu thiếu cũng tạo”, truyền thêm `CREATE`. Một lời gọi APPEND giữa nhiều process/thread **không bảo đảm** toàn bộ thông điệp của mỗi bên là một đơn vị atomic; xem hợp đồng provider và phối hợp tương ứng.

### 7.1. Những tổ hợp đáng nhớ

- `CREATE_NEW + WRITE`: chỉ tạo mới; đã có thì lỗi. Không cần thêm `TRUNCATE_EXISTING` vì file mới vốn chưa có nội dung.
- `CREATE + WRITE + TRUNCATE_EXISTING`: thao tác “create-or-replace” phổ biến nhưng **không an toàn khi write nửa chừng**.
- `WRITE` **một mình**: chỉ mở tệp tồn tại để ghi, không tự truncate.
- `READ + WRITE`: thường dùng với `FileChannel` hoặc `SeekableByteChannel`, **không** phải cho `Files.newInputStream` hoặc `newOutputStream`.
- `READ + TRUNCATE_EXISTING` (channel chỉ đọc): truncate bị bỏ qua.
- `APPEND + TRUNCATE_EXISTING`: kết hợp không hợp lệ ở channel chuẩn.
- `APPEND + READ`: kết hợp không hợp lệ ở channel chuẩn.
- `CREATE + CREATE_NEW`: `CREATE_NEW` thắng, `CREATE` bị bỏ qua.
- `CREATE`/`CREATE_NEW` trong context **chỉ đọc** của `newByteChannel`: bị bỏ qua theo contract, không tự tạo tệp chỉ để đọc.

## 8. Các mặc định quan trọng trong `Files`

Một điểm rất dễ gây mất dữ liệu là mặc định **khác nhau theo method**. Không đọc tên `Files` rồi suy luận rằng tất cả đều giống nhau.

| Method | Khi không truyền options | Ai đóng tài nguyên? |
| --- | --- | --- |
| `Files.newInputStream(path)` | Mở để **READ** | Caller đóng `InputStream`, thường trong try-with-resources |
| `Files.newOutputStream(path)` | **CREATE + TRUNCATE_EXISTING + WRITE** | Caller đóng `OutputStream` |
| `Files.write(path, bytes)` | **CREATE + TRUNCATE_EXISTING + WRITE** | API tự đóng stream nội bộ |
| `Files.writeString(path, text)` (Java 11+) | **CREATE + TRUNCATE_EXISTING + WRITE** | API tự đóng stream/writer nội bộ |
| `Files.write(path, lines, charset)` | Mặc định **CREATE + TRUNCATE_EXISTING + WRITE** | API tự đóng |
| `Files.newByteChannel(path)` | **READ** nếu không có READ/WRITE/APPEND | Caller đóng channel |
| `FileChannel.open(path)` | Theo quy tắc `FileChannel.open`: mặc định **READ** | Caller đóng `FileChannel` |

**Lưu ý then chốt:** Khi bạn **truyền danh sách options rõ ràng**, các lựa chọn **mặc định cho lời gọi không options không tự được cộng thêm**. Ví dụ: nếu code cũ dùng `Files.writeString(path, text)` rồi bạn sửa thành `Files.writeString(path, text, UTF_8, WRITE)`, bạn đã chỉ định **WRITE**, không còn yêu cầu tạo mới hoặc truncate như mặc định. Nếu file đang tồn tại chứa nội dung dài, kết quả có thể khác hoàn toàn.

Các API xử lý văn bản dùng overload khác nhau: ví dụ `Files.writeString(path, text, charset, options...)` là hợp lệ từ Java 11; `Files.write(path, byte[], options...)` nhận mảng byte; các overload ghi dòng có thêm charset và iterable. Khi cần đọc byte một chiều, đừng vô tình mở output stream chỉ để “lấy access vào file”.

## 9. Ví dụ hoàn chỉnh 1: quan sát READ, WRITE, CREATE_NEW, TRUNCATE_EXISTING

Lưu thành **`FileOpenModesDemo.java`**:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileOpenModesDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("open-options-");
        Path file = dir.resolve("sample.txt");
        try {
            // READ không tạo file thiếu.
            try (InputStream in = Files.newInputStream(
                    file, StandardOpenOption.READ)) {
                in.read();
            } catch (NoSuchFileException expected) {
                System.out.println("readMissing=true");
            }

            // CREATE_NEW: chỉ tạo khi chưa có, và không overwrite.
            Files.writeString(
                    file, "ABCDE", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try {
                Files.writeString(
                        file, "FAIL", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);
            } catch (FileAlreadyExistsException expected) {
                System.out.println("exclusiveCreate=true");
            }

            // WRITE không bao gồm truncate khi option được chỉ định rõ.
            try (OutputStream out = Files.newOutputStream(
                    file, StandardOpenOption.WRITE)) {
                out.write("XY".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("afterWriteOnly="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // TRUNCATE_EXISTING cắt file trước khi ghi.
            Files.writeString(
                    file, "OK", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            System.out.println("afterTruncate="
                    + Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

~~~bash
javac --release 17 FileOpenModesDemo.java
java FileOpenModesDemo
~~~

**Stdout đã kiểm tra:**

~~~text
readMissing=true
exclusiveCreate=true
afterWriteOnly=XYCDE
afterTruncate=OK
~~~

**Phân tích:**

1. Không tạo trước file, nên `newInputStream(READ)` báo `NoSuchFileException`.
2. `CREATE_NEW+WRITE` tạo file `ABCDE` thành công lần đầu; lần hai thất bại mà không ghi `FAIL` lên file.
3. `newOutputStream(WRITE)` bắt đầu từ vị trí đầu và ghi hai byte `XY`. File ban đầu có 5 byte; không truncate nên còn `CDE` ở cuối.
4. `WRITE+TRUNCATE_EXISTING` làm chiều dài file về 0 khi mở rồi ghi `OK`, vì vậy kết quả chỉ là `OK`.
5. Tệp và directory tạm được dọn trong `finally`. Đây là demo sử dụng file tạm mới, không đụng vào file công việc.

Đây là ví dụ ASCII để so số byte trực quan. Nếu thay bằng Unicode UTF-8, **độ dài sau ghi** phụ thuộc số byte sau mã hóa, không bằng `String.length()`. Khi ghi byte giữa một chuỗi UTF-8 nhiều byte, bạn có thể tạo văn bản không hợp lệ; cần tránh sửa các offset tùy ý trong file text.

## 10. Ví dụ hoàn chỉnh 2: mặc định của Files.writeString và newOutputStream

Lưu thành **`DefaultOpenOptionsDemo.java`**:

~~~java
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DefaultOpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("default-write-", ".txt");
        try {
            Files.writeString(file, "long-data", StandardCharsets.UTF_8);

            // Không options: CREATE + TRUNCATE_EXISTING + WRITE.
            Files.writeString(file, "hi", StandardCharsets.UTF_8);
            System.out.println("defaultWrite="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // OutputStream không options cũng truncate file tồn tại.
            try (OutputStream out = Files.newOutputStream(file)) {
                out.write("OK".getBytes(StandardCharsets.UTF_8));
            }
            System.out.println("defaultOutput="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // APPEND được chỉ định; không dùng TRUNCATE_EXISTING.
            Files.writeString(
                    file, "!", StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
            System.out.println("appended="
                    + Files.readString(file, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 DefaultOpenOptionsDemo.java
java DefaultOpenOptionsDemo
~~~

**Stdout đã kiểm tra:**

~~~text
defaultWrite=hi
defaultOutput=OK
appended=OK!
~~~

Cần quan sát `Files.writeString(file, "hi", UTF_8)` không giữ phần đuôi `ng-data` của nội dung cũ: **mặc định là truncate**. `Files.newOutputStream(file)` cũng tương tự. Cuối cùng, `WRITE+APPEND` thêm `!` vào tệp đang tồn tại; nếu muốn hoạt động cả khi chưa có file, hãy xét thêm `CREATE`.

**Đừng nhầm** giá trị mặc định của `Files.writeString` với `Files.newByteChannel`: không options ở channel thường là **READ**, chứ không phải CREATE+TRUNCATE+WRITE. Bảng ở mục 8 dùng để tra cứu khi chuyển qua API khác.

## 11. `READ + WRITE` trên channel: một handle hai chiều

`Files.newByteChannel` nhận tập `OpenOption` và trả `SeekableByteChannel`, có thể đọc/ghi và di chuyển vị trí nếu mở đủ quyền:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        path, EnumSet.of(StandardOpenOption.READ,
                         StandardOpenOption.WRITE))) {
    // Đọc bytes bằng channel.read(ByteBuffer).
    // Ghi bytes bằng channel.write(ByteBuffer).
    // channel.position(...) để điều chỉnh offset.
}
~~~

Đây là **fragment**; cần import `java.nio.channels.SeekableByteChannel`, `java.util.EnumSet` và `IOException`. `FileChannel.open(path, READ, WRITE)` là lựa chọn khác nếu cần các API riêng của FileChannel. Không nhầm quyền đọc+ghi với “đọc rồi ghi tiếp ở cuối”: vị trí channel được duy trì, thay đổi theo read/write, có thể đặt bằng `position(long)`.

### 11.1. Ví dụ hoàn chỉnh 3: một channel đọc và ghi không truncate

Lưu thành **`FileChannelOptionsDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class FileChannelOptionsDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("open-channel-", ".txt");
        try {
            Files.writeString(file, "ABCDE", StandardCharsets.UTF_8);

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file, EnumSet.of(
                            StandardOpenOption.READ,
                            StandardOpenOption.WRITE))) {

                ByteBuffer buffer = ByteBuffer.allocate(2);
                channel.read(buffer);
                buffer.flip();
                System.out.println("prefix="
                        + StandardCharsets.UTF_8.decode(buffer));

                channel.position(2);
                channel.write(ByteBuffer.wrap(
                        "zz".getBytes(StandardCharsets.UTF_8)));
            }

            System.out.println("readWrite="
                    + Files.readString(file, StandardCharsets.UTF_8));

            // TRUNCATE_EXISTING bị bỏ qua với channel chỉ READ.
            try (SeekableByteChannel channel = Files.newByteChannel(
                    file, EnumSet.of(
                            StandardOpenOption.READ,
                            StandardOpenOption.TRUNCATE_EXISTING))) {
                System.out.println("readOnlySize=" + channel.size());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 FileChannelOptionsDemo.java
java FileChannelOptionsDemo
~~~

**Stdout đã kiểm tra:**

~~~text
prefix=AB
readWrite=ABzzE
readOnlySize=5
~~~

Hãy tách nghĩa của từng thao tác: channel đọc 2 byte `AB`; `position(2)` đưa offset tới byte thứ ba (zero-based); ghi `zz` đè `CD` mà không truncate, giữ `E`. Khi chỉ mở `READ+TRUNCATE_EXISTING`, truncate bị bỏ qua theo hợp đồng channel, size vẫn bằng 5.

Đối với một buffer có thể cần nhiều lần ghi, production code phải lặp:

~~~java
// Fragment: channel đã mở WRITE và buffer có dữ liệu.
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
~~~

Nếu channel là non-blocking trong hệ thống khác, cần xem thêm hợp đồng về tiến triển khi trả 0; đối với file channel thông thường, đây là khuôn mẫu xử lý partial writes. Demo ở trên có dữ liệu 2 byte và đã kiểm tra hoạt động trong môi trường thử nghiệm; đừng mở rộng kết luận về “một write luôn ghi hết” cho mọi channel.

## 12. READ, WRITE, APPEND và các kết hợp sai

Không phải cứ kết hợp nhiều option là mạnh hơn. Mỗi factory kiểm tra tùy chọn hợp lệ.

| Kết hợp | Kết luận |
| --- | --- |
| `READ + WRITE` với `newByteChannel` / `FileChannel.open` | Hợp lệ để dùng cả hai chiều nếu provider hỗ trợ. |
| `READ` với `Files.newInputStream` | Hợp lệ; đây là quyền đọc đúng API. |
| `READ` với `Files.newOutputStream` | **Không hợp lệ** theo hợp đồng của output-stream factory. |
| `WRITE` với `Files.newInputStream` | Không phải chế độ input chuẩn được API này hỗ trợ. |
| `CREATE + WRITE` | Cho tạo file thiếu, còn file đang tồn tại không tự bị truncate. |
| `CREATE_NEW + WRITE` | Tạo nếu chưa có; từ chối tên trùng. |
| `CREATE + CREATE_NEW + WRITE` | `CREATE_NEW` có hiệu lực, `CREATE` bị bỏ qua. |
| `APPEND + TRUNCATE_EXISTING` với channel | **Không hợp lệ** vì vừa giữ nội dung để thêm cuối vừa yêu cầu xóa trắng. |
| `READ + APPEND` với channel | **Không hợp lệ** theo contract của `newByteChannel`/`FileChannel`. |
| `TRUNCATE_EXISTING + READ` (không WRITE) với channel | Truncate bị **bỏ qua**. |
| `CREATE/CREATE_NEW + READ` (không WRITE/APPEND) với channel | Tùy chọn tạo mới bị **bỏ qua** vì mở chỉ đọc. |

**Ngoại lệ và giới hạn:** Tổ hợp không hợp lệ có thể ném `IllegalArgumentException`; option mà provider/API không hỗ trợ có thể ném `UnsupportedOperationException`; vấn đề file/quyền/I/O thường ném `IOException`. Cụ thể từng API được nêu trong Javadoc; không dựa vào một exception duy nhất cho mọi provider.

### 12.1. Files.newOutputStream không nhất thiết có buffer

Javadoc `Files.newOutputStream` cho biết stream trả về **không được buffer** bởi method này. Với nhiều write nhỏ, có thể bọc:

~~~java
// Fragment: method throws IOException; dùng đúng một owner cho stream.
try (OutputStream out = new BufferedOutputStream(
        Files.newOutputStream(
                path, StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING))) {
    // Ghi nhiều byte vào out...
}
~~~

Cần import `java.io.BufferedOutputStream` và `java.io.OutputStream`. Đóng outer buffered stream sẽ đóng stream bên trong. Nhưng buffering **không** thay đổi semantics của việc mở tệp: `TRUNCATE_EXISTING` vẫn tác động **khi mở**, không phải sau khi buffer đã viết xong.

## 13. Nguyên tắc chống mất dữ liệu khi cần thay toàn bộ file

Dùng `TRUNCATE_EXISTING` trực tiếp cho file thật phù hợp khi nghiệp vụ **chấp nhận** kết quả có thể rỗng hoặc thiếu sau khi ghi lỗi (ví dụ file cache dễ tái tạo). Với config, hồ sơ hoặc dữ liệu quan trọng, thường không nên ghi đè tại chỗ rồi tin rằng ghi xong là giao dịch nguyên tử.

Một chiến lược phổ biến:

1. Tạo **file tạm mới** trong cùng thư mục/volume với đích khi có thể.
2. Ghi toàn bộ dữ liệu mới vào file tạm, dùng `CREATE_NEW` hoặc `Files.createTempFile` để tránh đụng tên có trước.
3. Đóng output (và áp dụng cơ chế đảm bảo độ bền dữ liệu khi yêu cầu).
4. Thử di chuyển file tạm sang tên đích bằng `Files.move` với `ATOMIC_MOVE` nếu provider/filesystem hỗ trợ.
5. Nếu filesystem không hỗ trợ atomic move, phải quyết định fallback có thể mất atomicity hay từ chối thao tác; không âm thầm khẳng định đó là “atomic”.
6. Dọn file tạm nếu có lỗi; kiểm soát quyền truy cập, race, symbolic links và điều kiện ghi đè mục tiêu theo yêu cầu nghiệp vụ.

**Cẩn trọng:** `Files.move(..., ATOMIC_MOVE)` có những quy tắc về các option khác và việc target đã tồn tại phụ thuộc provider/implementation; không được xem `ATOMIC_MOVE + REPLACE_EXISTING` là cam kết portable rằng thay một target có sẵn luôn thành công nguyên tử. Ngoài ra, **atomic rename khác durable write**: dữ liệu đã đổi tên có thể vẫn cần sync và các biện pháp ở mức filesystem/OS nếu yêu cầu chống mất dữ liệu khi mất điện.

### 13.1. CREATE_NEW cũng cần xử lý an ninh đường dẫn

`CREATE_NEW` chặn ghi đè **final path entry** đang tồn tại, kể cả symlink ở tên cuối. Nhưng nó không tự vô hiệu hóa symbolic link ở các thư mục cha, không khóa quyền truy cập vào root và không ngăn tác nhân khác sửa cây thư mục. Với tên file nhận từ người dùng, cần chính sách kiểm soát relative path, traversal `..`, symlink, quyền truy cập và race; không dùng `CREATE_NEW` như một sandbox đầy đủ.

## 14. Ghi văn bản so với ghi byte

Các option mô tả **cách mở tệp**, độc lập với cách mã hóa nội dung.

~~~java
// Hai cách ghi tương đương về các byte UTF-8 của chuỗi này.
byte[] data = "Xin chào".getBytes(StandardCharsets.UTF_8);

Files.write(path, data,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);

Files.writeString(path, "Xin chào", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING);
~~~

Đây là **fragment**, hai lời gọi chạy lần lượt; lời gọi sau ghi lại cùng nội dung. Điều quan trọng:

- `StandardCharsets.UTF_8` đảm bảo chọn charset rõ ràng; `String.length()` đếm UTF-16 code units, không phải kích thước file UTF-8.
- Các flag `WRITE/CREATE/TRUNCATE_EXISTING` không chọn charset, không chuyển newline và không bảo đảm nội dung UTF-8 hợp lệ nếu bạn tự sửa byte trong file.
- Với I/O tệp lớn, đừng mặc định `Files.readAllBytes`/`readString` là lựa chọn tốt nếu cần xử lý theo dòng/khối. Dùng buffered reader/stream và quản lý đóng resource khi dữ liệu lớn.
- Dùng `Files.writeString(..., Charset, OpenOption...)` từ Java 11; ở Java 8 có thể dùng `Files.write(path, byte[], OpenOption...)` hoặc `Files.newBufferedWriter(path, charset, options...)`.

### 14.1. Không mặc định File System hỗ trợ toàn bộ tùy chọn

Trong môi trường ZIPFS, mạng, cloud mounted filesystem hoặc provider riêng, một số option có thể không được hỗ trợ, và behavior hoặc exception cụ thể có thể khác. Các ví dụ tập trung vào default provider hỗ trợ StandardOpenOption phổ biến. Một API portable phải dự trù `UnsupportedOperationException`, `IOException` và các constraint như filesystem chỉ đọc; kiểm tra những option bắt buộc trong môi trường triển khai.

## 15. Xử lý exception và cleanup đúng

Khi mở/ghi tệp, các lỗi cần được phân biệt để trả thông báo đúng:

| Tình huống | Kiểu lỗi thường gặp | Phản ứng hợp lý |
| --- | --- | --- |
| Tệp thiếu khi chỉ READ/WRITE | `NoSuchFileException` | Báo đường dẫn không có hoặc chuyển sang flow có quyền tạo, nếu hợp lệ |
| CREATE_NEW gặp tên đã tồn tại | `FileAlreadyExistsException` (thường) | Không tự động ghi đè; xử lý trùng tên theo yêu cầu nghiệp vụ |
| Không đủ quyền hoặc hệ thống từ chối truy cập | `AccessDeniedException`/`IOException` | Báo lỗi truy cập; không tự mở rộng quyền |
| File cha chưa tồn tại | `NoSuchFileException`/`IOException` | Kiểm tra parent, có thể tạo thư mục theo chính sách |
| Tổ hợp options sai | `IllegalArgumentException` | Sửa lỗi lập trình, không retry vô hạn |
| Provider không hỗ trợ option | `UnsupportedOperationException` | Chọn chiến lược thay thế phù hợp provider |
| Hết dung lượng, lỗi ổ đĩa, ngắt ghi | `IOException` | Xem file có thể đã tạo/truncate/ghi dở; cleanup và báo lỗi |
| Lỗi khi `close()` | `IOException` hoặc loại khác theo resource | Bảo toàn thông tin lỗi, xử lý suppressed exceptions |

Ví dụ khung mở output và đóng trong mọi đường thoát:

~~~java
// Fragment: method throws IOException.
try (OutputStream out = Files.newOutputStream(
        path, StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    out.write(data); // data do caller chuẩn bị.
}
~~~

Nếu lỗi xảy ra **sau khi tệp đã được mở**, `try-with-resources` vẫn gọi close, nhưng không hoàn tác dữ liệu đã ghi hoặc thao tác truncate. Các exception phát sinh khi close có thể xuất hiện dưới dạng suppressed nếu body đã ném exception. **Không** suy ra “có close nghĩa là write đã hoàn tất và an toàn”.

## 16. Mô hình ra quyết định nhanh cho một API ghi file

~~~text
Cần CHỈ đọc?
  └── Có: Files.newInputStream(path) hoặc Files.readString(path, charset)
       Không tự CREATE.

Cần ghi file?
  ├── Không được đụng tên đã tồn tại
  │     └── CREATE_NEW + WRITE
  ├── Chỉ tệp đã tồn tại, muốn giữ phần dữ liệu chưa bị overwrite
  │     └── WRITE
  ├── Chỉ tệp đã tồn tại, muốn xóa trắng trước khi ghi
  │     └── WRITE + TRUNCATE_EXISTING
  ├── Thiếu thì tạo, đã có thì xóa trắng và ghi lại
  │     └── CREATE + WRITE + TRUNCATE_EXISTING
  └── Thiếu thì tạo, đã có thì thêm cuối
        └── CREATE + APPEND (+ WRITE theo API/để rõ ý định)

Cần READ và WRITE cùng một handle?
  └── Files.newByteChannel(path, EnumSet.of(READ, WRITE))
        hoặc FileChannel.open(path, READ, WRITE).
~~~

**Nhắc lại:** nếu file quan trọng và cần thay thế nguyên khối, flow ghi file tạm → đóng → di chuyển phù hợp có thể thích hợp hơn trực tiếp `TRUNCATE_EXISTING`. Không dựa vào `Files.exists` trước `Files.write` để giả lập điều kiện CREATE_NEW.

## 17. Các lỗi dễ gặp khi học hoặc review code

1. **“`WRITE` tự tạo file.”** Sai: không yêu cầu tạo thì tệp thiếu có thể lỗi.
2. **“`WRITE` tự xóa phần đuôi cũ.”** Sai: muốn xoá size cũ cần `TRUNCATE_EXISTING` khi mở để ghi.
3. **“`CREATE` chỉ tạo file mới.”** Sai: nếu file đã tồn tại thì mở được; không bảo vệ khỏi ghi đè.
4. **“`CREATE_NEW` ghi đè file với nội dung mới.”** Sai: tên đã tồn tại thì thất bại.
5. **“`CREATE_NEW` là bảo đảm ghi file atomic.”** Chỉ atomic ở bước kiểm tra/tạo tên, không bảo đảm dữ liệu được ghi hết.
6. **“`TRUNCATE_EXISTING` chỉ có tác dụng khi write thành công.”** Sai: truncate diễn ra khi mở trước khi viết.
7. **“`TRUNCATE_EXISTING` xóa tệp khỏi directory.”** Sai: nó làm length về 0, file entry còn.
8. **“`READ+WRITE` dùng được trên InputStream/OutputStream đơn chiều.”** Sai: chọn channel hỗ trợ hai chiều.
9. **“Không options ở mọi API là READ.”** Sai: `newOutputStream`/`Files.write*` mặc định có CREATE+TRUNCATE+WRITE, còn `newByteChannel` mặc định READ.
10. **“Thêm `WRITE` vào Files.writeString không ảnh hưởng.”** Có thể ảnh hưởng: custom options không tự kế thừa default CREATE/TRUNCATE.
11. **“`Files.exists` rồi `Files.writeString` chống race.”** Sai: hai thao tác không atomic.
12. **“Kết hợp `APPEND+TRUNCATE_EXISTING` để ghi rồi giữ đuôi.”** Sai: không hợp lệ cho channel chuẩn.
13. **“`CREATE+CREATE_NEW` sẽ ưu tiên CREATE.”** Sai: CREATE_NEW chi phối.
14. **“Đọc thuần READ mà truyền TRUNCATE_EXISTING sẽ xóa file.”** Sai: bị bỏ qua trong channel chỉ đọc.
15. **“FileOutputStream mở không options luôn giữ nguyên file cũ.”** Không phải mặc định của `Files.newOutputStream`: có truncate.
16. **“Dùng WRITE và ghi chuỗi ngắn hơn thì file tự thu nhỏ.”** Sai, có thể còn đuôi cũ.
17. **“Tất cả Files API trả stream đều tự đóng.”** Sai: method trả InputStream/OutputStream/Channel để caller dùng thì caller đóng; `Files.writeString` tự quản lý.
18. **“Đã có try-with-resources thì không thể mất dữ liệu.”** Sai: try đảm bảo gọi close, không rollback truncate/partial write.
19. **“File ZIP hoặc provider khác luôn hỗ trợ mọi StandardOpenOption.”** Không bảo đảm; phải theo provider.
20. **“Ghi byte theo offset bất kỳ vào UTF-8 luôn giữ text hợp lệ.”** Sai: có thể phá một sequence nhiều byte.
21. **“Đặt TRUNCATE_EXISTING làm giải pháp cập nhật crash-safe.”** Sai: cần thiết kế temp/atomic move/durability phù hợp.
22. **“APPEND là cùng nghĩa với WRITE mặc định.”** Sai: APPEND nhắm cuối file, còn WRITE đơn thuần thường từ đầu.

## 18. Bài tập tự kiểm tra

1. File `A.txt` chứa `12345678`. `Files.newOutputStream(path, WRITE)` ghi hai byte `XY`. Nội dung dự kiến là gì?
2. Tương tự, thêm `TRUNCATE_EXISTING` rồi ghi `XY`. Khác nhau thế nào?
3. Muốn **chỉ tạo mới** file upload và từ chối tên trùng, chọn option nào? Vì sao `if (!exists)` chưa đủ?
4. Muốn chạy trên file đã tồn tại nhưng **không được tạo mới**, phải bỏ option gì?
5. `Files.writeString(file, "A")` không options làm gì nếu file chứa `ABCDEFG`?
6. Khi thêm `StandardOpenOption.WRITE` tường minh vào overload `Files.writeString(file, "A", UTF_8, WRITE)`, có còn được hiểu mặc định CREATE và TRUNCATE không?
7. Nếu mở `Files.newByteChannel(file, EnumSet.of(READ, WRITE))`, có thể đọc/ghi với cùng handle không?
8. Có thể yêu cầu `READ + APPEND` trên channel chuẩn không?
9. `READ + TRUNCATE_EXISTING` trên channel chỉ đọc sẽ làm gì với size file?
10. `CREATE_NEW` có bảo đảm file được ghi hoàn chỉnh nếu máy mất điện lúc ghi không?
11. Đường dẫn có symbolic link ở **thư mục cha** có được CREATE_NEW tự xử lý thành sandbox không?
12. Vì sao phải đóng `Files.newOutputStream` bằng try-with-resources còn `Files.writeString` không trả output stream để caller đóng?
13. Nếu thiếu thư mục cha, `CREATE` có tự tạo mọi thư mục không?
14. Muốn giữ phần cũ và ghi thêm cuối thì option nào phù hợp, và tại sao không dùng `TRUNCATE_EXISTING`?
15. File cấu hình quan trọng cần cập nhật với khả năng giảm thiểu ghi nửa chừng: có chiến lược nào tốt hơn trực tiếp truncate?
16. Vì sao gọi `write(ByteBuffer)` trên một channel không được luôn giả định đã tiêu thụ hết buffer?

**Đáp án định hướng:**

1. `XY345678` vì WRITE không truncate.
2. Chỉ còn `XY` sau thao tác thành công vì length được cắt về 0.
3. `CREATE_NEW+WRITE`; kiểm tra và tạo file cùng một thao tác atomic theo hợp đồng.
4. Bỏ `CREATE` và `CREATE_NEW`; dùng `WRITE` hoặc `WRITE+TRUNCATE_EXISTING` tùy muốn xóa.
5. Ghi theo default CREATE+TRUNCATE+WRITE nên file thành `A`.
6. Không; khi chỉ định options phải nêu rõ CREATE/TRUNCATE nếu muốn những hành vi đó.
7. Có, với channel được mở bằng cả hai quyền; vị trí file cần quản lý.
8. Không, combination không hợp lệ theo contract của channel.
9. Không thay đổi size vì truncate bị bỏ qua khi chỉ đọc.
10. Không, atomic creation khác atomic/complete write và durability.
11. Không, cần kiểm soát traversal, symlink và quyền truy cập theo threat model.
12. `newOutputStream` trả resource mở do caller quản lý; `writeString` tự làm việc và dọn nội bộ.
13. Không; tạo parent riêng khi được phép.
14. `APPEND`, thường đi cùng `CREATE` nếu muốn file thiếu cũng tạo; không kết hợp TRUNCATE.
15. Ghi file tạm cùng vị trí phù hợp, đóng và thay thế bằng move atomic nếu hỗ trợ; xem thêm durability, error handling.
16. Channel có thể ghi một phần; kiểm tra `ByteBuffer.hasRemaining()` và lặp.

## 19. Tài liệu tham khảo chuẩn Java SE

- [Oracle Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): ý nghĩa `READ`, `WRITE`, `CREATE`, `CREATE_NEW`, `TRUNCATE_EXISTING`, `APPEND`.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): mặc định của `newInputStream`, `newOutputStream`, `newByteChannel`, `write`, `writeString`, ngoại lệ và cách đóng handle.
- [Oracle Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): các option mở channel hai chiều, position, read/write và giới hạn tổ hợp.
- [Oracle Java SE 21 — SeekableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SeekableByteChannel.html): đọc/ghi/di chuyển vị trí và size/truncate.
- [Oracle Java SE 21 — FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): lỗi thường gặp khi `CREATE_NEW` gặp tên đã có.
- [Oracle Java SE 21 — Files.move](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `ATOMIC_MOVE`, `REPLACE_EXISTING` và giới hạn theo provider.
- [Oracle Java SE 21 — StandardCopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html): các lựa chọn khi move/copy file.

**Ghi nhớ cuối bài:** `READ` là quyền đọc; `WRITE` là quyền ghi; `CREATE` tạo khi thiếu nhưng dùng lại file đã có; `CREATE_NEW` chỉ tạo tên mới và từ chối trùng một cách atomic ở bước tạo; `TRUNCATE_EXISTING` xóa trắng file đã có ngay lúc mở để ghi. **Đừng suy đoán default giữa các Files API**: ghi không options thường CREATE+TRUNCATE+WRITE, còn channel không options thường READ. Chọn options dựa vào yêu cầu nghiệp vụ và khả năng chấp nhận mất dữ liệu, không theo cảm giác.