# Không ghi đè dữ liệu ngoài ý muốn khi mở hoặc copy tệp trong Java

Mất dữ liệu khi xử lý file thường không bắt đầu từ một lệnh xóa tường minh. Chỉ cần mở một đường dẫn bằng API có mặc định **cắt ngắn nội dung**, dùng `REPLACE_EXISTING` sai chỗ hoặc ghi vào một file đã tồn tại ở vị trí byte 0, ứng dụng có thể làm hỏng dữ liệu người dùng dù không hề gọi `Files.delete()`. Trong Java I/O và NIO.2, **chọn đúng chế độ tạo/mở tệp, kiểm tra quyền sở hữu và xử lý lỗi giữa chừng** là những bước quan trọng của thiết kế an toàn.

Bài này giải thích khi nào Java tự tạo, cắt ngắn, ghi đè hoặc từ chối đích đã tồn tại; phân biệt `CREATE` với `CREATE_NEW`, `TRUNCATE_EXISTING` với `APPEND`, hành vi của `Files.copy()`, giới hạn của bước `Files.exists()` trước khi ghi, và cách giảm rủi ro khi cần cập nhật một file quan trọng.

Mục tiêu là chọn chiến lược **“không thay nội dung hiện có trừ khi đã có chủ đích”**, chứ không phải giả định mọi thao tác file đều an toàn chỉ vì không khai báo tùy chọn thay thế.

## 1. Định nghĩa đúng các dạng “ghi đè”

Có ít nhất bốn tình huống khác nhau:

1. **Truncate khi mở:** File có nội dung bị đưa về độ dài 0 ngay lúc mở, trước khi ứng dụng kịp ghi dữ liệu mới.
2. **Overwrite tại offset:** File vẫn giữ kích thước ban đầu hoặc được kéo dài, nhưng một số byte đang có bị thay bởi byte mới, thường khi `position = 0`.
3. **Replace file object/đường dẫn đích:** Thao tác copy/move thay tệp đang nằm ở đường dẫn đích bằng tệp khác, có thể làm mất nội dung hoặc metadata cũ.
4. **Ghi ra ngoài vùng dự kiến:** Đường dẫn bị chuẩn hóa sai hoặc theo symbolic link làm dữ liệu được ghi sang một file khác với mục tiêu nghiệp vụ.

Để tránh mất dữ liệu phải phân biệt cả bốn. Chẳng hạn `StandardOpenOption.WRITE` **không tự xóa sạch file khi mở**, nhưng một lần `write()` tại offset 0 vẫn có thể **ghi đè các byte đầu**. Ngược lại `TRUNCATE_EXISTING` làm rỗng file ngay khi mở thành công, kể cả khi phần thân `try` chưa ghi byte nào.

## 2. Bảng hành vi mở và ghi: những mặc định nguy hiểm

| API / cấu hình | Nếu file đích đã tồn tại | Nếu file chưa tồn tại | Rủi ro |
| --- | --- | --- | --- |
| `Files.newOutputStream(path)` | **Cắt ngắn file** khi mở | Tạo file mới | Dễ mất nội dung vì mặc định tương đương `CREATE + TRUNCATE_EXISTING + WRITE` |
| `Files.newBufferedWriter(path, charset)` | **Cắt ngắn file** khi mở | Tạo file mới | Cũng là mặc định tạo mới hoặc truncate |
| `Files.write(path, bytes)` / `Files.writeString(path, text)` | **Thay nội dung file** (mặc định truncate) | Tạo file mới | Không dùng trực tiếp với tên có thể tồn tại nếu cần bảo toàn |
| `new FileOutputStream(file)` | **Cắt ngắn file** | Tạo file | Mặc định không phải append |
| `new FileOutputStream(file, true)` | Mở để ghi nối | Tạo file nếu thiếu | Có thể thêm dữ liệu vào file không mong muốn |
| `FileChannel.open(path)` | Mở chỉ đọc | Thất bại nếu thiếu | Không tự cho phép ghi |
| `FileChannel.open(path, WRITE)` | Cho phép ghi vào file cũ, vị trí mới mở là 0 | Thường thất bại nếu file thiếu | Ghi đè từ đầu khi gọi `write()` |
| `FileChannel.open(path, WRITE, CREATE)` | Giữ nội dung khi mở; `write()` vẫn có thể ghi đè | Tạo file | Không phải bảo đảm “chỉ tạo nếu thiếu và không bao giờ sửa file cũ” |
| `FileChannel.open(path, WRITE, CREATE, TRUNCATE_EXISTING)` | **Cắt về 0 byte khi mở** | Tạo file | Chỉ phù hợp khi cố ý thay toàn bộ dữ liệu |
| `FileChannel.open(path, WRITE, CREATE_NEW)` | **Thất bại, không mở để ghi** | Tạo file mới | Thích hợp cho mục tiêu “không đụng file đã có” |
| `FileChannel.open(path, WRITE, APPEND)` | Ghi nối cuối | Thất bại nếu thiếu, trừ khi thêm `CREATE` | Không có nghĩa khóa độc quyền giữa nhiều writer |

Các mô tả mặc định dùng các file provider Java thông thường; thao tác cụ thể vẫn có thể thất bại vì quyền, loại đường dẫn, hệ thống tệp hoặc lỗi I/O. Khi mục tiêu là **không bao giờ sửa file đã có**, hãy đặt policy bằng thao tác tạo độc quyền như `CREATE_NEW`, thay vì trông cậy vào việc mở với `CREATE`.

### Vì sao Files.writeString có thể nguy hiểm?

Đoạn mã:

```java
Files.writeString(Path.of("config.txt"), "new");
```

nếu `config.txt` đã tồn tại và ghi được, API mặc định **tạo nếu thiếu và truncate nếu đã có**. Một file cấu hình dài có thể bị biến thành chỉ ba byte `new`. Nếu mục tiêu là chỉ tạo file mới, hãy ghi rõ:

```java
Files.writeString(
        Path.of("config.txt"),
        "new",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Đây là **đoạn minh họa** cần import `Files`, `Path`, `StandardCharsets`, `StandardOpenOption` và xử lý `IOException`. Nếu file đã tồn tại, thao tác thất bại, thường với `FileAlreadyExistsException`, thay vì ghi đè.

## 3. CREATE và CREATE_NEW khác nhau ở đâu?

`CREATE` nghĩa là **tạo file khi chưa có**, nhưng nếu file đã tồn tại và channel được phép ghi, chương trình vẫn có thể mở file đó để sửa. Ngược lại, `CREATE_NEW` yêu cầu **tạo một file mới**; nếu đường dẫn đã tồn tại thì thất bại. Kiểm tra tồn tại và tạo mới được thực hiện **nguyên tử đối với nhau** theo hợp đồng API.

```java
// Minh họa: path là Path được kiểm soát, xử lý IOException ở caller.
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    // Chỉ tới đây nếu tạo file mới thành công.
}
```

Đối với `Files.newOutputStream()`:

```java
// Minh họa: không cấp quyền ghi vào file đã có.
try (OutputStream out = Files.newOutputStream(
        path,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(payload);
}
```

`payload` phải là `byte[]` do caller chuẩn bị; đây là đoạn code minh họa, chưa phải chương trình độc lập.

Một số đặc điểm cần ghi nhớ:

- `CREATE_NEW` từ chối **đường dẫn đã có**, kể cả đường dẫn đang là **symbolic link** dù đích link không còn tồn tại. Đặc điểm này giúp tránh thao tác “theo symlink cũ rồi ghi vào chỗ khác” trong ca tạo mới.
- `CREATE_NEW` không tự tạo **thư mục cha**. Nếu `parent` thiếu, lệnh vẫn thất bại; chỉ tạo thư mục cha khi đó là đường dẫn được phép.
- `CREATE_NEW` không xác thực rằng đường dẫn cha không bị thay đổi đồng thời bởi tác nhân khác. Trong thư mục công cộng hoặc có người khác sửa, cần biện pháp ownership và bảo vệ đường dẫn ở cấp hệ thống tệp.
- Nếu file cần tạo chứa nội dung nhạy cảm, còn phải chọn **quyền truy cập của file mới**, chính sách `FileAttribute`/umask và nơi lưu trữ thích hợp.
- `CREATE_NEW` giải quyết race **tồn tại so với tạo** tại đường dẫn đích, nhưng không biến một chuỗi nhiều lệnh ghi thành giao dịch nguyên tử hoàn chỉnh.

### Files.createFile cũng từ chối tên có sẵn

```java
Path file = Files.createFile(target);
```

`Files.createFile()` là thao tác tạo file mới nguyên tử nếu chưa có, có thể nhận `FileAttribute<?>...` khi hệ thống hỗ trợ. Tuy nhiên, tạo trước một file rỗng rồi gọi `Files.writeString(file, text)` **không tự bảo đảm không có writer khác sửa file giữa hai bước**, và `Files.writeString` mặc định vẫn truncate file đang mở. Nếu cần vừa khẳng định quyền tạo mới vừa ghi dữ liệu, thường đơn giản hơn khi **mở trực tiếp với `CREATE_NEW + WRITE` rồi ghi qua chính stream/channel đó**.

## 4. Kiểm tra Files.exists() trước khi ghi không đủ an toàn

Một anti-pattern:

```java
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
```

Giữa lệnh `notExists()` và `writeString()`, luồng hoặc tiến trình khác có thể tạo file cùng tên. Lệnh ghi phía sau dùng mặc định truncate và có thể **ghi đè file vừa xuất hiện**. Đây là lỗi **TOCTOU** (*time-of-check to time-of-use*).

```text
Thời điểm | Process A                          | Process B
--------- | ---------------------------------- | -------------------
T1        | notExists(target) -> true         |
T2        |                                    | tạo target, ghi "B"
T3        | writeString(target, "A")           |
T4        | target chứa "A" (mất dữ liệu "B")   |
```

Cách đúng khi nghiệp vụ yêu cầu “không tạo đè” là dùng một thao tác có **điều kiện tồn tại gắn với việc tạo**:

```java
try {
    Files.writeString(target, content, StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE);
} catch (FileAlreadyExistsException exists) {
    // Không ghi đè: báo trùng tên hoặc chọn tên mới theo quy tắc nghiệp vụ.
}
```

Đây là đoạn minh họa cần khai báo biến `target` và `content`, import các kiểu và xử lý `IOException` khác. **Không chuyển ngay sang `TRUNCATE_EXISTING` trong nhánh catch chỉ để “cho chạy thành công”**, vì như vậy phá bỏ chính sách không ghi đè.

`Files.exists()` vẫn hữu ích để hiển thị thông tin cho người dùng hoặc chuẩn bị UI, nhưng **không dùng kết quả kiểm tra cũ làm bảo đảm độc quyền ghi**. `notExists()` trả `false` cũng có thể có nghĩa là không xác định được trạng thái, không nhất thiết file đang tồn tại.

## 5. Files.copy(): mặc định từ chối target đã tồn tại

Khi sao chép bằng Java NIO:

```java
Files.copy(source, target);
```

Với `Path source` và `Path target`, **nếu file đích đã tồn tại thì thao tác copy thông thường thất bại** (thường `FileAlreadyExistsException`), trừ các trường hợp đặc biệt do API quy định như hai đường dẫn thực sự tham chiếu đến cùng file. Không cần kiểm tra `Files.exists(target)` trước khi gọi để tránh ghi đè.

Nếu bạn cố ý cho phép thay thế:

```java
Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
```

thì đó là một quyết định **phá hủy dữ liệu cũ có chủ đích**, cần phê duyệt và xử lý lỗi. `Files.copy()` **không được bảo đảm atomic**, kể cả khi không dùng `REPLACE_EXISTING`. Nếu xảy ra `IOException` giữa lúc copy, file đích mới hoặc file đích đang bị thay có thể nằm ở trạng thái dở dang. Vì vậy **“không thay file cũ”** và **“file mới luôn hoàn chỉnh”** là hai yêu cầu khác nhau.

### COPY_ATTRIBUTES và NOFOLLOW_LINKS không phải “chế độ an toàn tuyệt đối”

Một lời gọi:

```java
Files.copy(source, target,
        StandardCopyOption.COPY_ATTRIBUTES,
        LinkOption.NOFOLLOW_LINKS);
```

là **đoạn minh họa**. `COPY_ATTRIBUTES` yêu cầu copy một số metadata phù hợp provider và có thể thất bại. `NOFOLLOW_LINKS` điều khiển việc **không đi theo symbolic link ở source** trong thao tác copy; khi source là symbolic link, API có thể sao chép link thay vì nội dung đích liên kết nếu hỗ trợ. Cả hai **không thay thế** chính sách tạo đích an toàn, kiểm soát quyền và bảo vệ khỏi path traversal.

Nếu cần tránh ghi đè, hãy **không thêm `REPLACE_EXISTING`** và kiểm tra/giữ nguyên nội dung đích khi nhận `FileAlreadyExistsException`.

### Files.copy(InputStream, Path) cũng cần thận trọng

```java
Files.copy(networkInput, target);
```

Đây là mẫu minh họa với `networkInput` kiểu `InputStream`. Overload này không dùng `Path source`, nhưng cũng có tùy chọn `REPLACE_EXISTING` và có thể để lại dữ liệu đã copy một phần nếu lỗi trong quá trình đọc/ghi. Khi input là dữ liệu không tin cậy, cần giới hạn dung lượng/tốc độ và không sử dụng tên file do đầu vào cung cấp trực tiếp để ghi ra ngoài vùng cho phép.

## 6. Chương trình Java 17+ hoàn chỉnh: không ghi đè khi copy hoặc tạo

Ví dụ tự tạo thư mục tạm nên không chạm vào file thật của người học. Chương trình:

- Ghi một file nguồn có nội dung `NEW DATA` và một đích đã tồn tại có nội dung `KEEP`.
- Thử `Files.copy(source, existing)` mà không có `REPLACE_EXISTING`; xác nhận từ chối và đích giữ nguyên.
- Copy đến một tên mới chưa tồn tại.
- Tạo một file khác bằng `FileChannel.open(..., CREATE_NEW, WRITE)`; thử tạo lại lần hai và xác nhận từ chối mà nội dung không đổi.
- Đóng mọi channel trước khi xóa file/thư mục tạm.

Tạo file **`SafeOpenCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class SafeOpenCopyDemo {
    private SafeOpenCopyDemo() {}

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("safe-copy-demo-");
        Path source = directory.resolve("source.txt");
        Path existing = directory.resolve("existing.txt");
        Path copied = directory.resolve("copied.txt");
        Path created = directory.resolve("created.txt");

        try {
            Files.writeString(source, "NEW DATA\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
            Files.writeString(existing, "KEEP\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try {
                Files.copy(source, existing);
                throw new AssertionError("Copy should not replace existing");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("copy-existing=refused");
            }
            System.out.println("existing-still="
                    + Files.readString(existing, StandardCharsets.UTF_8)
                            .strip());

            Files.copy(source, copied);
            System.out.println("copied="
                    + Files.readString(copied, StandardCharsets.UTF_8)
                            .strip());

            try (FileChannel channel = FileChannel.open(created,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                ByteBuffer bytes = ByteBuffer.wrap(
                        "SAFE\n".getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) {
                    if (channel.write(bytes) == 0) {
                        throw new IOException("No write progress");
                    }
                }
            }
            System.out.println("created="
                    + Files.readString(created, StandardCharsets.UTF_8)
                            .strip());

            try (FileChannel ignored = FileChannel.open(created,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                throw new AssertionError("Create should refuse existing");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("create-new-existing=refused");
            }
            System.out.println("created-still="
                    + Files.readString(created, StandardCharsets.UTF_8)
                            .strip());
        } finally {
            Files.deleteIfExists(created);
            Files.deleteIfExists(copied);
            Files.deleteIfExists(existing);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac SafeOpenCopyDemo.java
java SafeOpenCopyDemo
```

Kết quả khi các thao tác trên thư mục tạm thành công trên filesystem thông thường:

```text
copy-existing=refused
existing-still=KEEP
copied=NEW DATA
created=SAFE
create-new-existing=refused
created-still=SAFE
```

Phân tích:

1. `Files.writeString(..., CREATE_NEW, WRITE)` tạo hai file đầu tiên mà không có khả năng vô tình truncate một file trùng tên.
2. `Files.copy(source, existing)` mặc định không thay file đích `existing.txt`; exception được bắt rõ ràng, không nuốt các `IOException` khác.
3. `Files.copy(source, copied)` thành công vì `copied.txt` chưa tồn tại. Nó vẫn không phải thao tác copy nguyên tử đối với lỗi I/O giữa chừng.
4. `FileChannel.open(created, CREATE_NEW, WRITE)` thực hiện mở file mới một cách loại trừ, sau đó vòng lặp `ByteBuffer.hasRemaining()` bảo đảm hoàn tất bytes được chấp nhận ghi.
5. Cố mở `created.txt` lần nữa với `CREATE_NEW` báo `FileAlreadyExistsException`, để nguyên file cũ `SAFE`.
6. `try-with-resources` đóng channel trước khi cleanup. `finally` cố xóa các file tạm thuộc sở hữu ví dụ.

Ví dụ cho thấy **bảo vệ file đã tồn tại**; nó không chứng minh rằng toàn bộ tiến trình copy/ghi sẽ tự rollback khi mất điện hoặc lỗi I/O. Trong ứng dụng thật, nếu thao tác thất bại sau khi đã tạo file mới, phải có chính sách phát hiện và dọn **chính file mới mà ứng dụng sở hữu**, không xóa bừa đường dẫn có thể đã bị một tác nhân khác thay thế.

## 7. Nếu vẫn cần thay nội dung file cũ thì làm thế nào?

Có những nhu cầu hợp lệ như cập nhật cấu hình, thay bản export hoặc ghi phiên bản mới của một file báo cáo. Khi đó **không ghi đè ngoài ý muốn** nghĩa là việc thay thế phải **có chủ đích, được kiểm soát và có phương án phục hồi**, không nhất thiết cấm thay thế trong mọi trường hợp.

### Tránh truncate file đích ngay khi bắt đầu

Cách rủi ro:

```java
Files.writeString(target, newlyGeneratedContent);
```

Nếu file cũ quan trọng, `Files.writeString()` mặc định truncate target và tiến trình có thể chết trước khi ghi xong. Thay vì ghi thẳng vào target, cân nhắc chiến lược:

1. Tạo **file tạm mới** trong cùng filesystem và thư mục thích hợp; tên file tạm phải được cấp phát an toàn, ví dụ `Files.createTempFile(parent, prefix, suffix)`.
2. Ghi dữ liệu mới hết vào file tạm, kiểm tra tính hợp lệ, đóng stream/channel, tùy yêu cầu có thể `FileChannel.force(true)` để yêu cầu đồng bộ nội dung/metadata.
3. Chỉ khi nội dung đã sẵn sàng, thực hiện một thao tác `Files.move()` từ file tạm sang file đích **theo chính sách thay thế đã được cho phép**.
4. Nếu cần tính nguyên tử, thử `StandardCopyOption.ATOMIC_MOVE` trên filesystem hỗ trợ, xử lý `AtomicMoveNotSupportedException` rõ ràng.
5. Ghi log kết quả, kiểm thử crash/recovery và cleanup file tạm còn sót lại.

**Quan trọng:** `ATOMIC_MOVE` không có nghĩa là “tuyệt đối không ghi đè”. Khi `ATOMIC_MOVE` được chọn, **hành vi nếu target đã tồn tại là implementation-specific** và các option khác có thể bị bỏ qua theo hợp đồng `Files.move()`. Do đó không dùng `Files.move(temp, target, ATOMIC_MOVE)` làm bằng chứng chung rằng target cũ chắc chắn không thể bị thay. Nếu yêu cầu **tuyệt đối không chạm file đích đã có**, lựa chọn tạo độc quyền `CREATE_NEW` hoặc cơ chế publish có hợp đồng no-replace được xác minh trên nền tảng sẽ phù hợp hơn.

### Ví dụ thay thế có chủ đích và phải kiểm soát

```java
// Phác thảo: ứng dụng đã kiểm tra quyền thay thế target,
// temporary chứa nội dung hoàn chỉnh, cùng FileStore phù hợp.
try {
    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Chọn chính sách riêng: thất bại an toàn hoặc fallback đã chấp thuận.
}
```

Đây là phác thảo **không độc lập**; đòi hỏi biến `temporary`/`target`, xử lý `IOException` và chính sách fallback. Với `ATOMIC_MOVE`, việc thay thế target có tồn tại hay không còn tùy implementation; **không suy ra chỉ việc thêm `REPLACE_EXISTING` vào một atomic move sẽ cho ngữ nghĩa portable đầy đủ**. Trên hệ thống không hỗ trợ atomic move, fallback không nguyên tử có thể làm tăng nguy cơ ứng dụng khác quan sát trạng thái trung gian. Nếu không chấp nhận điều đó, phải **dừng và báo lỗi**, không tự fallback một cách âm thầm.

`FileChannel.force(true)` yêu cầu đồng bộ nội dung/file metadata theo hợp đồng API; nó không bảo đảm toàn bộ thao tác rename hoặc cập nhật thư mục chứa tên file đã bền vững qua mọi sự cố mất điện trên mọi OS/filesystem. Yêu cầu durability nghiêm ngặt cần chiến lược cấp hệ thống và kiểm thử recovery.

## 8. Bảo vệ khỏi path traversal, symbolic link và nhầm thư mục

`CREATE_NEW` bảo vệ trường hợp có file/symlink ngay tại **đường dẫn đích**, nhưng không tự bảo vệ mọi thành phần của đường dẫn hay mọi loại race. Ví dụ ứng dụng định tạo:

```text
/app/export/report.txt
```

Nếu `/app/export` có thể bị thay bằng symbolic link trỏ tới thư mục khác, thao tác tạo tệp vẫn có thể ghi ngoài vùng dự kiến. Cần lựa chọn thư mục gốc mà ứng dụng sở hữu, xác thực và giới hạn đầu vào tên file, cũng như bảo vệ các directory entries khỏi tác nhân không tin cậy.

Một bước chuẩn hóa đường dẫn cơ bản:

```java
// Minh họa: root là thư mục tin cậy, userName lấy từ đầu vào.
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userName).normalize();
if (!candidate.startsWith(base) || candidate.equals(base)) {
    throw new IllegalArgumentException("Unsafe target path");
}
```

Điều này chặn một số trường hợp lexical `../` trỏ ra ngoài nhưng **không chặn hoàn toàn symlink hoặc race trên các thành phần thư mục**. Đối với môi trường có đối thủ chủ động chỉnh sửa đường dẫn, cần cách truy cập dựa trên thư mục được mở an toàn, quyền filesystem, hoặc `SecureDirectoryStream` nếu provider hỗ trợ. Không tự tuyên bố `normalize() + startsWith()` là giải pháp chống path traversal toàn diện.

Đối với `Files.copy(source, target)`, cũng cần cân nhắc `Files.isSameFile(source, target)` khi thiết kế quy trình: hai đường dẫn có thể tham chiếu cùng một file qua hard link/symlink. Với cùng đối tượng file, một thao tác copy có thể không làm gì theo hợp đồng API; điều này không chứng minh dữ liệu đã được nhân bản thành file độc lập.

### Quyền sở hữu và tập tin tạm

- Chỉ cleanup file mà tiến trình **thực sự tạo và vẫn sở hữu**; không gọi `Files.deleteIfExists(target)` bừa bãi trong `catch` sau thất bại `CREATE_NEW`.
- Đừng tạo file tạm theo tên dễ đoán rồi mở bằng cách có thể truncate một file có sẵn.
- Tránh thư mục tạm chia sẻ không tin cậy cho các thao tác có đường dẫn do người dùng định nghĩa; `Files.createTempFile()` tránh va chạm tên nhưng không tự biến toàn bộ workflow thành không có race.
- Với file nhạy cảm, cần đặt permission cho file và thư mục, nhất là khi dữ liệu được ghi trước khi đổi tên vào nơi công khai.
- Khi dùng `Files.copy(..., REPLACE_EXISTING)`, nhớ việc thay file có thể làm thay metadata hoặc quyền file đích. Kiểm tra nhu cầu bảo toàn attributes/ownership theo provider.

## 9. Khi nào cần APPEND thay vì CREATE_NEW?

Có lúc mục tiêu không phải tạo file mới hay thay toàn bộ file cũ mà là **bổ sung một bản ghi vào log hiện có**:

```java
try (FileChannel channel = FileChannel.open(
        logPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND)) {
    ByteBuffer data = StandardCharsets.UTF_8.encode("record\n");
    while (data.hasRemaining()) {
        channel.write(data);
    }
}
```

Đây là đoạn minh họa với `logPath` kiểu `Path`, import `FileChannel`, `ByteBuffer`, `StandardOpenOption`, `StandardCharsets` và xử lý `IOException`. `APPEND` giúp mỗi lần ghi theo ngữ nghĩa cuối file, tránh tình huống mở `WRITE + CREATE` rồi ghi từ byte 0. Nhưng `APPEND` không phải khóa phân tán, không bảo đảm atomicity khi nhiều tiến trình append trên mọi filesystem, và không khôi phục dữ liệu khi lỗi.

Nếu log phải có từng record bất khả phân, hãy quy định framing, đồng bộ giữa writer, kiểm tra kết quả và chiến lược durability phù hợp. Không dùng `APPEND` cùng `TRUNCATE_EXISTING` trong `FileChannel.open()`; tổ hợp này không hợp lệ.

## 10. Xử lý exception đúng để không làm hỏng dữ liệu

| Tình huống | Ngoại lệ thường gặp | Xử lý an toàn |
| --- | --- | --- |
| `CREATE_NEW` gặp tên đã có | `FileAlreadyExistsException` | Giữ nguyên file, trả lỗi trùng tên hoặc sinh tên mới theo chính sách |
| `Files.copy()` gặp đích đã có | `FileAlreadyExistsException` | Không tự retry bằng `REPLACE_EXISTING` |
| Không tồn tại thư mục cha | `NoSuchFileException` hoặc `IOException` | Kiểm tra root được phép, chỉ tạo parent hợp lệ |
| Không có quyền | `AccessDeniedException` hoặc `IOException` | Báo lỗi quyền, không làm fallback sang đường dẫn ngẫu nhiên |
| Hết dung lượng hoặc lỗi giữa khi ghi/copy | `IOException` | Đánh dấu output chưa hoàn chỉnh, dọn tài nguyên owned, không tuyên bố thành công |
| Move nguyên tử không được hỗ trợ | `AtomicMoveNotSupportedException` | Fail-safe hoặc fallback được cho phép rõ ràng |
| Source/target bị người khác thay đổi giữa các bước | Thay đổi kết quả hoặc `IOException` tùy provider | Thiết kế ownership/locking và không dùng pre-check như cam kết |
| Phần đích là thư mục/link bất thường | Ngoại lệ phụ thuộc OS/provider | Xác thực loại file/đường dẫn và quyền, không ghi đè bất chấp |

Phân biệt lỗi **“file đã tồn tại”** với lỗi I/O khác. Một đoạn `catch (Exception ignored) { ... }` quá rộng có thể che mất lỗi copy dở và khiến ứng dụng ghi metadata “thành công” trong khi dữ liệu thực không đầy đủ.

Nếu đã tạo một file mới nhưng ghi bị lỗi, ứng dụng có thể cần loại bỏ **file mới dở dang**. Nhưng cleanup này không được phép xóa file đã tồn tại từ trước hoặc file thuộc người khác chỉ vì trùng tên; mô hình ownership, thư mục riêng hoặc token theo dõi tài nguyên là điều quan trọng.

## 11. Checklist thiết kế thao tác không ghi đè

Trước khi ghi hoặc copy, kiểm tra:

1. **Chính sách:** Tác vụ này chỉ tạo file mới, nối vào file cũ, sửa một phần, hay thay toàn bộ? Không dùng một API cho mọi trường hợp.
2. **Tên đích:** Path được tạo từ root tin cậy? Có chặn đường dẫn ra ngoài hoặc symlink đáng ngờ? Thư mục cha có do ứng dụng sở hữu?
3. **Mở file:** Đã chọn `CREATE_NEW` khi cần tuyệt đối từ chối tên tồn tại? Có vô tình dùng API mặc định truncate?
4. **Copy:** Có chủ động thêm `REPLACE_EXISTING` không? Nếu có, ai đã cho phép mất nội dung cũ?
5. **TOCTOU:** Có dùng `Files.exists()` rồi dựa vào kết quả cũ để mở bằng API nguy hiểm không?
6. **I/O lỗi giữa chừng:** Có ghi vào file tạm, kiểm soát file dở, cleanup đúng đối tượng và thông báo lỗi rõ ràng không?
7. **Atomicity & durability:** Ứng dụng cần tệp đích luôn hoàn chỉnh, cần cấm overwrite tuyệt đối, hay cần giữ dữ liệu qua mất điện? Các yêu cầu này khác nhau.
8. **Đồng thời:** Có nhiều writer hay các tiến trình khác cùng truy cập? Có cần sở hữu độc quyền, locking hoặc version check không?
9. **Quyền và metadata:** File mới có permission phù hợp, file bị thay có cần giữ attributes/owner?
10. **Kiểm thử:** Đã thử file đích có sẵn, symlink, thư mục cha thiếu, quyền bị từ chối, ENOSPC, crash giữa copy, thao tác hai tiến trình đồng thời và hành vi nền tảng triển khai chưa?

## 12. Những lỗi phổ biến cần tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `Files.writeString(path, text)` với tên file do người dùng cung cấp | Có thể truncate file cũ | `CREATE_NEW + WRITE` nếu chỉ tạo mới |
| Dùng `new FileOutputStream(file)` và nghĩ nó nối cuối | Làm rỗng nội dung cũ | Dùng append rõ ràng nếu đúng nghiệp vụ |
| Dùng `WRITE + CREATE` và nghĩ không bao giờ sửa file đã có | Ghi đè từ offset 0 | Dùng `CREATE_NEW` hoặc ghi offset có chủ đích |
| Kiểm tra `Files.notExists()` trước rồi mới ghi mặc định | Race TOCTOU khiến đè file do tiến trình khác tạo | Dùng một thao tác tạo độc quyền |
| Thêm `REPLACE_EXISTING` khi muốn "copy cho chắc" | Xóa/đổi file đích đã có | Không thêm trừ khi thay thế là nghiệp vụ đã được duyệt |
| Nghĩ `Files.copy()` là atomic | File mới hoặc file thay thế có thể dở khi lỗi | Chiến lược staging + kiểm tra + publish |
| Tin `ATOMIC_MOVE` bảo đảm no-overwrite portable | Target cũ có thể bị thay tùy implementation | Đừng đồng nhất atomic rename với create-if-absent |
| Truyền path từ ZIP/user mà không kiểm tra | Viết ngoài vùng đích dự kiến | Root tin cậy, kiểm tra đường dẫn và symlink/race |
| Xóa `target` ngay trong catch khi `CREATE_NEW` thất bại | Xóa file có sẵn của người khác | Chỉ cleanup những file đã tạo và sở hữu |
| Coi `FileChannel.write()` một lần là đã ghi hết | File mới có thể thiếu byte | Kiểm tra `ByteBuffer.hasRemaining()` |
| Ghi vào cùng file qua hai tên hard link khác nhau | Thay đổi dữ liệu ngoài dự định dù tên khác nhau | Xác minh file identity và quyền |
| Không xử lý `IOException` sau khi tạo file mới | Để lại file hỏng và báo thành công | Cleanup owned partial output, phát lỗi rõ ràng |

**Ghi nhớ:** “Không ghi đè” phải được xác định bằng **hợp đồng của chính thao tác mở/copy**, không bằng một lần kiểm tra tồn tại trước đó. Dùng `CREATE_NEW` để tạo độc quyền và từ chối file đã có; để `Files.copy(source, target)` không có `REPLACE_EXISTING` khi cần giữ nguyên target; tránh mặc định truncate của `Files.writeString()`, `newOutputStream()` và `FileOutputStream`. Khi buộc phải thay file cũ, làm việc với tệp tạm, phương án publish và recovery rõ ràng; đừng nhầm “không ghi đè”, “thao tác nguyên tử” và “ghi bền” là một tính chất.