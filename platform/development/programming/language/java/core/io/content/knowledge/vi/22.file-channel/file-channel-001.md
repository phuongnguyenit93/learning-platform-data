# Mở FileChannel bằng Path và OpenOption trong Java NIO

`FileChannel` là kênh truy cập tệp có thể đọc, ghi, di chuyển vị trí, lấy kích thước, cắt ngắn tệp và thực hiện một số thao tác nâng cao như `transferTo`, `transferFrom` hoặc `map`. Trong Java NIO.2, cách mở trực tiếp phổ biến là `FileChannel.open(Path, OpenOption...)`. Các `OpenOption` xác định **quyền truy cập, việc tạo tệp mới, cách xử lý tệp đã tồn tại và yêu cầu đồng bộ ghi**.

Chọn sai option có thể khiến ứng dụng âm thầm mở chỉ để đọc, ghi đè dữ liệu ngoài ý muốn, cắt ngắn tệp ngay khi mở, thất bại nếu tệp không tồn tại hoặc gặp tổ hợp option không hợp lệ. Bài này tập trung vào việc **mở đúng tệp và đúng chế độ**, kiểm tra hậu quả của từng option và quản lý vòng đời `FileChannel`.

## 1. Hai dạng `FileChannel.open`

Các phương thức tĩnh chính trong `java.nio.channels.FileChannel`:

```java
public static FileChannel open(
        Path path, OpenOption... options) throws IOException;

public static FileChannel open(
        Path path,
        Set<? extends OpenOption> options,
        FileAttribute<?>... attrs) throws IOException;
```

Đây là chữ ký API để tham khảo, không phải một lớp Java độc lập.

- `path` là đường dẫn tệp, biểu diễn bởi `java.nio.file.Path`, ví dụ `Path.of("data", "events.bin")`. Đường dẫn tương đối được giải quyết theo thư mục làm việc của chương trình tại thời điểm thao tác; không nhất thiết là thư mục chứa file `.java`.
- `options` là những hành vi mở tệp, phần lớn chọn từ enum `java.nio.file.StandardOpenOption`. Đối với dạng varargs, truyền nhiều option cách nhau bằng dấu phẩy.
- `attrs` là thuộc tính tùy chọn được áp dụng khi **tạo** tệp mới, ví dụ quyền POSIX ở những hệ thống hỗ trợ. Dạng nhận `Set` cho phép truyền attributes và options một cách có cấu trúc.
- Giá trị trả về là một `FileChannel` đang mở. Mọi thao tác I/O phải xử lý `IOException` và đóng channel khi sử dụng xong.

Ví dụ mở tệp đã tồn tại ở chế độ đọc:

```java
Path path = Path.of("data", "events.bin");
try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    System.out.println("size=" + channel.size());
}
```

Đây là đoạn minh họa trong chương trình có các import `Path`, `FileChannel`, `StandardOpenOption`, và phương thức cho phép ném `IOException`. Tệp phải tồn tại và truy cập được; output `size` phụ thuộc nội dung tệp.

**Quy tắc mặc định dễ quên:** Nếu không truyền bất kỳ option nào, `FileChannel.open(path)` mở **chỉ để đọc**, tương đương ý định `READ`. Nó không tự tạo tệp và không tự cho phép ghi.

## 2. Những `StandardOpenOption` cần biết

Các option dưới đây thường được kết hợp khi mở `FileChannel`:

| Option | Ý nghĩa |
| --- | --- |
| `READ` | Mở tệp để đọc; `read(...)` được phép |
| `WRITE` | Mở tệp để ghi; `write(...)` được phép |
| `CREATE` | Tạo tệp nếu chưa tồn tại, khi mở có quyền ghi; nếu đã tồn tại thì mở tệp đó |
| `CREATE_NEW` | Tạo tệp mới và thất bại nếu đường dẫn đã tồn tại; bước kiểm tra tồn tại và tạo là thao tác nguyên tử theo hợp đồng API |
| `TRUNCATE_EXISTING` | Khi mở **để ghi**, cắt kích thước tệp có sẵn về 0 ngay lúc mở |
| `APPEND` | Khi ghi, đưa dữ liệu về cuối tệp theo ngữ nghĩa append; không dùng cùng `READ` hoặc `TRUNCATE_EXISTING` |
| `SYNC` | Yêu cầu đồng bộ nội dung và metadata liên quan tới thiết bị lưu trữ cho các cập nhật theo hợp đồng của API |
| `DSYNC` | Yêu cầu đồng bộ nội dung tệp; phạm vi metadata cần đồng bộ hẹp hơn `SYNC` |
| `DELETE_ON_CLOSE` | Yêu cầu xóa tệp khi đóng channel (best effort khi thất bại hoặc tiến trình kết thúc bất thường); cần hiểu hệ quả trên từng hệ thống |
| `SPARSE` | Gợi ý tạo tệp thưa khi tạo mới; hệ thống có thể bỏ qua gợi ý, không bảo đảm file sẽ thật sự sparse |

`READ`, `WRITE`, `CREATE`, `CREATE_NEW`, `TRUNCATE_EXISTING` và `APPEND` là các option quan trọng nhất để hiểu hành vi mở tệp. Những option đồng bộ ảnh hưởng độ bền dữ liệu và có thể làm tăng độ trễ ghi; chỉ chọn theo yêu cầu lưu trữ.

Lưu ý tinh tế: `CREATE`, `CREATE_NEW` và `TRUNCATE_EXISTING` không tự làm một lần mở **chỉ đọc** trở thành mở để ghi. Với `FileChannel.open`, các tùy chọn này được bỏ qua khi tệp không được mở cho ghi; muốn tạo, cập nhật hay truncate phải yêu cầu `WRITE` rõ ràng. Cũng không nên trông cậy `APPEND` sẽ tự mang lại một cấu hình đọc/ghi tùy ý: cấu hình dễ hiểu và phổ biến là `WRITE, APPEND`.

## 3. Những cấu hình mở thông dụng

### 3.1. Đọc tệp hiện có

```java
try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    // Đọc từ channel.
}
```

Đây là đoạn minh họa với `path` kiểu `Path`. Nếu file không có, thao tác thường ném `NoSuchFileException`. Đọc không làm tệp dài thêm, và `channel.write(...) `trên channel chỉ đọc ném `NonWritableChannelException`.

### 3.2. Đọc và sửa tệp đã có

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    // Đọc và ghi, không tự cắt ngắn.
}
```

Nếu không có `CREATE` hoặc `CREATE_NEW`, tệp cần tồn tại. Có `WRITE` không có nghĩa tự xóa dữ liệu cũ: việc ghi bắt đầu từ vị trí hiện hành của channel, mặc định 0 khi mới mở; ghi byte vào giữa tệp sẽ thay thế byte tại vùng tương ứng.

### 3.3. Tạo nếu chưa có, giữ nội dung nếu đã có

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE)) {
    // File được tạo nếu thiếu; nội dung file cũ không bị truncate khi mở.
}
```

**Cảnh báo:** "Không truncate" không đồng nghĩa với "ghi nối cuối". Vị trí mặc định của channel mới mở là 0; ghi ngay lập tức sẽ **ghi đè từ đầu tệp**. Muốn ghi nối cuối, dùng `APPEND` hoặc chủ động tìm EOF khi phù hợp, đồng thời cân nhắc tính đồng thời.

### 3.4. Tạo mới duy nhất, không chấp nhận ghi đè file cũ

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE_NEW)) {
    // Chỉ đến đây khi tệp mới đã được tạo thành công.
}
```

Khi đường dẫn đã tồn tại, việc mở thất bại, thường với `FileAlreadyExistsException`. `CREATE_NEW` phù hợp để bảo vệ file kết quả mới hoặc tên file duy nhất và tránh lỗi "kiểm tra `exists` rồi mới tạo" giữa các luồng/tiến trình. Một symbolic link đã tồn tại tại đường dẫn cũng được xem là tồn tại cho việc `CREATE_NEW`, kể cả khi đích của nó không còn.

### 3.5. Tạo mới hoặc xóa sạch nội dung file cũ

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    // Nếu file tồn tại, size đã về 0 ngay sau khi mở thành công.
}
```

Đây là lựa chọn dùng khi cố ý **thay thế toàn bộ dữ liệu file**. Truncation xảy ra ngay khi mở, trước khi code của khối `try` ghi dữ liệu. Nếu ứng dụng crash sau khi mở nhưng trước khi ghi xong, nội dung cũ đã mất. Không dùng cách này khi muốn cập nhật một vài byte, thêm bản ghi hoặc cần quy trình thay thế file an toàn.

### 3.6. Ghi nối vào cuối file

```java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    // Ghi các byte mới ở cuối tệp.
}
```

Khi đang ở chế độ `APPEND`, thao tác ghi được thực hiện theo ngữ nghĩa nối cuối tệp. Tuy nhiên hợp đồng `FileChannel` **không bảo đảm trên mọi hệ điều hành** rằng bước định vị EOF và ghi luôn diễn ra nguyên tử đối với các tiến trình/luồng khác cùng ghi. Nếu cần nhiều writer cập nhật cùng một file, cần thiết kế phối hợp thích hợp; đừng coi `APPEND` là một transaction hoặc thay thế hoàn toàn locking.

Không kết hợp `APPEND` với `READ` hoặc `TRUNCATE_EXISTING`; đó là tổ hợp bất hợp lệ theo API.

## 4. Chương trình Java 17+ hoàn chỉnh: mở, ghi, đọc, cập nhật, append và truncate

Ví dụ tạo **thư mục tạm riêng** rồi dùng một tệp `sample.bin` trong thư mục đó. Các byte là ASCII để số lượng byte và kết quả không phụ thuộc charset mặc định. Toàn bộ channel được đóng bằng `try-with-resources`, sau đó chương trình dọn tệp/thư mục tạm.

Tạo file **`FileChannelOpenDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileChannelOpenDemo {
    private FileChannelOpenDemo() {}

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("file-channel-demo-");
        Path file = directory.resolve("sample.bin");
        try {
            // CREATE_NEW: tạo mới; WRITE: cho phép ghi.
            try (FileChannel out = FileChannel.open(file,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                writeAll(out, ByteBuffer.wrap(
                        "Java NIO".getBytes(StandardCharsets.US_ASCII)));
                System.out.println("created bytes=" + out.size());
            }

            // Không có option: mặc định chỉ đọc.
            try (FileChannel in = FileChannel.open(file)) {
                ByteBuffer buffer = ByteBuffer.allocate(8);
                while (buffer.hasRemaining()) {
                    int n = in.read(buffer);
                    if (n < 0) {
                        break;
                    }
                    if (n == 0) {
                        throw new IOException("No read progress");
                    }
                }
                buffer.flip();
                System.out.println("default read="
                        + StandardCharsets.US_ASCII.decode(buffer));
                System.out.println("readable=" + in.isOpen());
            }

            // Đọc/ghi file cũ mà không xóa dữ liệu.
            try (FileChannel edit = FileChannel.open(file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE)) {
                edit.position(5); // Chữ 'N' ở byte thứ 5.
                writeAll(edit, ByteBuffer.wrap(
                        "API".getBytes(StandardCharsets.US_ASCII)));
                System.out.println("edited size=" + edit.size());
            }

            // APPEND: nối vào cuối, không thay phần đầu.
            try (FileChannel append = FileChannel.open(file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND)) {
                writeAll(append, ByteBuffer.wrap(
                        "!".getBytes(StandardCharsets.US_ASCII)));
                System.out.println("after append size=" + append.size());
            }

            System.out.println("content="
                    + Files.readString(file, StandardCharsets.US_ASCII));

            // TRUNCATE_EXISTING: file đã có và được cắt về 0.
            try (FileChannel truncate = FileChannel.open(file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                System.out.println("after truncate=" + truncate.size());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }

    private static void writeAll(FileChannel channel, ByteBuffer source)
            throws IOException {
        while (source.hasRemaining()) {
            int n = channel.write(source);
            if (n == 0) {
                throw new IOException("No write progress");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac FileChannelOpenDemo.java
java FileChannelOpenDemo
```

Kết quả khi các thao tác tệp tạm đều thành công:

```text
created bytes=8
default read=Java NIO
readable=true
edited size=8
after append size=9
content=Java API!
after truncate=0
```

Giải thích:

1. `CREATE_NEW + WRITE` tạo tệp chưa tồn tại và ghi 8 byte `Java NIO`; `size()` là 8.
2. `FileChannel.open(file)` không có option được mở ở chế độ `READ`. Vòng đọc nạp tối đa 8 byte vào buffer rồi `flip()` để giải mã. `isOpen()` là `true` bên trong khối `try`.
3. `READ + WRITE` mở tệp hiện có. Vị trí byte 5 là `N`; ghi `API` thay ba byte `NIO` và giữ kích thước bằng 8.
4. `WRITE + APPEND` nối byte `!` tại cuối, kích thước trở thành 9 và nội dung `Java API!`.
5. `WRITE + TRUNCATE_EXISTING` xóa nội dung về kích thước 0 ngay khi mở. Việc đọc lại sau đó sẽ cho EOF nếu chưa ghi tiếp.

**Phân biệt rõ:** `FileChannel.write(ByteBuffer)` có thể ghi *ít hơn* số byte còn lại trong buffer. Hàm `writeAll` lặp cho đến khi đã tiêu thụ toàn bộ buffer; nhờ đó ví dụ không phụ thuộc việc một lần ghi hoàn tất hết dữ liệu. Đây là tệp tạm do chương trình sở hữu, không can thiệp vào tệp dữ liệu của người học.

## 5. Dạng `Set<OpenOption>` và `FileAttribute`

Khi option được xây dựng có điều kiện hoặc khi cần thuộc tính lúc tạo file, dùng overload nhận `Set`:

```java
import java.nio.channels.FileChannel;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;

// Đoạn minh họa trong phương thức xử lý IOException; path đã được khai báo.
Set<OpenOption> options = Set.of(
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);

try (FileChannel channel = FileChannel.open(path, options)) {
    // Ghi vào file vừa được tạo.
}
```

Overload thực tế nhận `Set<? extends OpenOption>` và có varargs `FileAttribute<?>...` ở cuối. Nếu môi trường có filesystem POSIX, có thể yêu cầu quyền truy cập khi tạo:

```java
// Minh họa riêng cho hệ thống tệp hỗ trợ POSIX attributes.
var permissions = java.nio.file.attribute.PosixFilePermissions
        .asFileAttribute(
                java.nio.file.attribute.PosixFilePermissions
                        .fromString("rw-------"));

try (FileChannel channel = FileChannel.open(
        path,
        java.util.Set.of(StandardOpenOption.CREATE_NEW,
                         StandardOpenOption.WRITE),
        permissions)) {
    // File tạo mới với POSIX permission được yêu cầu.
}
```

Đây là đoạn mã minh họa cần `path` kiểu `Path`, import cần thiết và xử lý `IOException`. Trên Windows hoặc provider không hỗ trợ thuộc tính POSIX, yêu cầu này có thể thất bại; không áp dụng mù quáng như một cấu hình tương thích mọi hệ điều hành. Quyền và chính sách bảo mật thực tế còn tùy filesystem, môi trường chạy và các hạn chế của hệ điều hành.

Các thuộc tính tạo tệp này khác với `StandardOpenOption`: `OpenOption` xác định *cách mở*, trong khi `FileAttribute` mô tả *thuộc tính cho tệp được tạo*.

## 6. Xử lý ngoại lệ theo chế độ mở

Không phải mọi lỗi mở tệp đều là "file không tồn tại". Các lỗi phổ biến:

| Tình huống | Kết quả hoặc ngoại lệ cần chuẩn bị |
| --- | --- |
| `READ` một đường dẫn không tồn tại | Thường `NoSuchFileException` |
| `CREATE_NEW + WRITE` với tên file đã tồn tại | Thường `FileAlreadyExistsException` |
| Đường dẫn sai, thiếu quyền hoặc file bị khóa bởi tác nhân khác | `IOException` phù hợp với nền tảng, có thể `AccessDeniedException` |
| Kết hợp `APPEND` và `READ`, hoặc `APPEND` và `TRUNCATE_EXISTING` | `IllegalArgumentException` |
| Đưa option mà provider không hỗ trợ | Có thể `UnsupportedOperationException` |
| Gọi `write(...)` trên channel chỉ đọc | `NonWritableChannelException` |
| Gọi `read(...)` trên channel chỉ ghi | `NonReadableChannelException` |
| Gọi thao tác trên channel đã đóng | Có thể `ClosedChannelException` |
| Dung lượng lưu trữ hết hoặc thiết bị gặp sự cố trong khi ghi | `IOException` trong quá trình I/O, không chỉ tại lúc `open` |

Tên exception chi tiết phụ thuộc provider và nền tảng; `IOException` cần được xử lý/báo lại khi ứng dụng cần biết file có thực sự được ghi thành công hay không. Đừng bắt `Exception` rồi giả vờ đã tạo/ghi xong file.

Ví dụ xử lý tình huống tạo mới khi file đã tồn tại:

```java
// Đoạn minh họa trong phương thức đã khai báo Path file.
try (FileChannel output = FileChannel.open(file,
        StandardOpenOption.WRITE,
        StandardOpenOption.CREATE_NEW)) {
    // Tiến hành ghi dữ liệu mới.
} catch (java.nio.file.FileAlreadyExistsException e) {
    System.out.println("File already exists: " + file);
} catch (java.io.IOException e) {
    // Báo lỗi I/O thực sự cho tầng gọi.
    throw e;
}
```

Chỉ xử lý `FileAlreadyExistsException` theo cách trên nếu "tên đã có" là một trường hợp nghiệp vụ đã dự kiến. Nếu bảo vệ dữ liệu người dùng, không tự chuyển sang `TRUNCATE_EXISTING` để ghi đè khi gặp lỗi đó.

## 7. Vị trí kênh và việc ghi đè sau khi mở

Ngay sau khi mở `FileChannel` thông thường, vị trí hiện tại bắt đầu ở **byte 0**. Với kiểu I/O tương đối:

```java
int bytesRead = channel.read(buffer);
int bytesWritten = channel.write(buffer);
long where = channel.position();
```

Đây là đoạn minh họa trong đó `channel` và `buffer` phải có sẵn, channel cần mở với đúng quyền tương ứng; không được dùng chính buffer một cách tùy tiện cho cả đọc và ghi khi chưa quản lý `flip()/clear()`. Các thao tác tương đối thay đổi vị trí hiện hành theo số byte đã thực sự đọc/ghi.

Với channel mở `WRITE + CREATE` nhưng file đã tồn tại, `channel.write(buffer)` tại position 0 sẽ **ghi đè từ đầu**, không tự append và không tự truncate phần đuôi. Ví dụ file cũ `ABCDEFGH` dài 8 byte, ghi ba byte `xyz` từ vị trí 0 sẽ tạo nội dung `xyzDEFGH`, vẫn dài 8 byte.

Nếu cần cập nhật tại offset cụ thể mà không thay đổi vị trí hiện tại, `FileChannel` còn có các phương thức positional I/O:

```java
// Đoạn minh họa, buffer đã được chuẩn bị và channel có quyền ghi.
long offset = 4;
int written = channel.write(buffer, offset);
```

Lời gọi `write(buffer, offset)` sử dụng offset trong tệp cho lần ghi đó, **không thay đổi `channel.position()`**, nhưng vẫn làm tăng `buffer.position()` theo số byte đã ghi. Cần xử lý số byte `written` thực tế. Kiểu này phù hợp với cập nhật bản ghi ngẫu nhiên, trong khi `APPEND` dùng cho luồng ghi nối tiếp.

Không nên kết hợp suy đoán dựa trên `position()` và `APPEND`: khi append, ý định ghi là cuối tệp và việc định vị EOF có thể được thực hiện khi ghi. Hãy tách rõ trường hợp cập nhật vị trí và trường hợp ghi nối.

## 8. Đóng tài nguyên, độ bền dữ liệu và ghi file an toàn

`FileChannel` triển khai `AutoCloseable`, nên sử dụng `try-with-resources`. Đóng channel giải phóng tài nguyên hệ điều hành gắn với lần mở; nó không có nghĩa một thao tác ghi trước đó đã thỏa mãn mọi yêu cầu durability của ứng dụng trên mọi thiết bị lưu trữ.

`channel.force(true)` yêu cầu đẩy cập nhật nội dung và metadata liên quan đến thiết bị lưu trữ theo hợp đồng của `FileChannel`, trong khi `force(false)` chỉ buộc nội dung và metadata cần cho việc lấy lại nội dung; phạm vi đảm bảo phụ thuộc loại tệp/thiết bị/provider. Với kênh không phải tệp trên thiết bị lưu trữ cục bộ, các đảm bảo có thể yếu hơn. `SYNC` và `DSYNC` là những yêu cầu được chọn **ngay từ lúc mở** để đồng bộ các cập nhật trong suốt vòng đời kênh. Các cơ chế này có chi phí I/O, nên chọn theo mức an toàn dữ liệu thật sự cần thiết.

Nếu mục tiêu là **thay thế toàn bộ một file quan trọng**, `TRUNCATE_EXISTING` mở thẳng file đích có rủi ro mất nội dung cũ khi ghi lỗi. Một thiết kế thường dùng là:

1. Tạo file tạm **trong cùng filesystem/thư mục thích hợp** bằng `CREATE_NEW + WRITE`.
2. Ghi đầy đủ và kiểm tra lỗi, bảo đảm channel được đóng; thực hiện `force` nếu yêu cầu độ bền dữ liệu.
3. Thay thế tên file đích bằng `Files.move(...)` với chiến lược phù hợp, có thể yêu cầu `ATOMIC_MOVE` khi filesystem hỗ trợ.
4. Xử lý trường hợp `AtomicMoveNotSupportedException`, thiếu quyền, tệp đích đang được mở hoặc sự cố I/O, cùng chính sách cleanup rõ ràng.

Đây là **quy trình thiết kế** chứ không phải bảo đảm rằng mọi filesystem hỗ trợ thay thế nguyên tử hoặc `Files.move` tự động bền vững trước mất điện. Việc ghi file tạm và thao tác thay thế tên có những ràng buộc durability/phối hợp khác nhau tùy nền tảng. Khi nội dung cực kỳ quan trọng, cần quy trình kiểm thử failure/recovery trên hệ thống triển khai thật.

## 9. Cân nhắc quyền truy cập và cấu hình an toàn

- **Chỉ đọc khi chỉ cần đọc:** Mở `READ` khiến code không thể tình cờ ghi qua channel này; nó cũng thể hiện đúng ý định.
- **Bảo vệ file đã tồn tại:** Sử dụng `CREATE_NEW` nếu không được phép ghi đè. Không dựa vào `Files.notExists()` rồi mở `CREATE` như một bước "tạo nếu chưa có" an toàn khỏi race.
- **Tránh truncate ngoài ý muốn:** Chỉ thêm `TRUNCATE_EXISTING` khi nghiệp vụ đòi hỏi làm rỗng file cũ ngay lúc mở.
- **Không tin mặc định đường dẫn:** `Path.of("result.bin")` dựa vào working directory; với ứng dụng thực tế cần xác định root, quyền và cách xử lý đường dẫn người dùng nhập.
- **Đừng cho rằng CREATE tạo cha:** `CREATE` tạo tệp, **không tạo những thư mục cha còn thiếu**. Nếu cần, tạo các thư mục cha được phép bằng `Files.createDirectories(parent)` trước khi mở.
- **Symlink và đường dẫn không tin cậy:** `CREATE` / `WRITE` có thể tác động đến một file khác theo cách đường dẫn được hệ thống tệp phân giải. Với thư mục có thể bị tác nhân không tin cậy sửa, phải có thiết kế bảo vệ đường dẫn và quyền truy cập thích hợp; kiểm tra `exists` trước khi mở không loại bỏ race.
- **Giới hạn quyền theo tác vụ:** Không cho phép `WRITE` hoặc `DELETE_ON_CLOSE` chỉ vì "có thể sẽ cần"; cấu hình càng rộng càng dễ phá dữ liệu.

Nếu cần mở `FileChannel` từ một `RandomAccessFile` có sẵn, có thể dùng `randomAccessFile.getChannel()`. Trường hợp đó khác với `FileChannel.open(Path, ...)`: channel lấy từ `RandomAccessFile` **chia sẻ trạng thái vị trí tệp** với đối tượng `RandomAccessFile` của cùng lần mở. Còn mở channel mới trực tiếp qua `Path` tạo một lần mở với trạng thái vị trí riêng, dù hai channel có thể tham chiếu đến cùng nội dung tệp.

## 10. Những lỗi thực hành dễ mắc

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `FileChannel.open(path)` rồi `write()` | Mặc định chỉ đọc, ném `NonWritableChannelException` | Thêm `WRITE` khi thật sự cần ghi |
| Dùng `WRITE + CREATE` và nghĩ luôn ghi nối | Ghi đè từ đầu tệp hiện có | Dùng `APPEND` khi cần nối hoặc đặt vị trí có chủ đích |
| Thêm `TRUNCATE_EXISTING` để "cập nhật" file | File bị làm rỗng ngay khi mở | Bỏ truncate khi chỉ sửa vùng dữ liệu |
| Dùng `CREATE` khi không được phép thay nội dung cũ | File tồn tại vẫn được mở để ghi | Dùng `CREATE_NEW` và xử lý file đã có |
| Truyền `READ + APPEND` | Tổ hợp bất hợp lệ | Thiết kế luồng đọc và ghi nối riêng, tránh option xung đột |
| Không đóng channel | Giữ file descriptor/tài nguyên, có thể gây lỗi file lock hoặc cạn tài nguyên | Dùng `try-with-resources` |
| Gọi `write` một lần và giả định đã ghi mọi byte | Dữ liệu có thể thiếu | Lặp đến khi `ByteBuffer.hasRemaining()==false` |
| Tin rằng `CREATE` tự tạo thư mục cha | Mở file thất bại nếu thư mục cha chưa có | Chủ động tạo thư mục cha hợp lệ |
| Giả định `SYNC/DSYNC` miễn phí hoặc luôn bảo đảm chống mọi kiểu lỗi | Chậm bất ngờ hoặc đánh giá sai durability | Đo và kiểm tra hợp đồng trên hệ thống triển khai |
| Cắt ngắn trực tiếp file cấu hình quan trọng khi thay thế | Crash giữa ghi có thể để file trống hoặc một phần | Ghi file tạm, xác minh và thay thế theo chính sách recovery |

**Quy tắc lựa chọn:** Dùng `READ` cho tệp hiện có chỉ cần đọc; `READ + WRITE` cho cập nhật tại chỗ; `WRITE + CREATE_NEW` khi tạo file mới bắt buộc không trùng tên; `WRITE + CREATE` khi được phép tạo nếu thiếu; thêm `TRUNCATE_EXISTING` chỉ khi thực sự muốn làm rỗng tệp cũ; thêm `APPEND` để ghi nối cuối. Viết rõ các option giúp chương trình dễ kiểm tra, tránh sai lệch dữ liệu và làm rõ chính sách xử lý lỗi.