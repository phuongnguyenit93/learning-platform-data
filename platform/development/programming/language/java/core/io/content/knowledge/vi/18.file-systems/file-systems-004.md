# newFileSystem, getFileSystem và quyền đóng tài nguyên trong Java NIO.2

## 1. Bài toán: FileSystem là gì và ai quản lý vòng đời?

Trong Java NIO.2 (`java.nio.file`), một `FileSystem` là môi trường quản lý các `Path`, thư mục, tệp và thao tác I/O theo quy tắc của một *file system provider*. Hệ thống tệp có thể là hệ thống tệp mặc định của hệ điều hành, nội dung một tệp ZIP/JAR, hoặc một hệ thống tệp ảo do thư viện cung cấp.

Cần phân biệt ba đối tượng:

- `FileSystemProvider`: triển khai cơ chế truy cập một loại hệ thống tệp và xác định cách tạo/tra cứu nó.
- `FileSystem`: đối tượng đại diện cho một hệ thống tệp đang được truy cập; có thể có vòng đời `open → close`.
- `Path`: đường dẫn thuộc **một** `FileSystem` cụ thể. `Path` không sở hữu hay tự đóng `FileSystem`.

Ví dụ, đường dẫn `/data.txt` trong ZIP và đường dẫn `/data.txt` trên ổ đĩa không chỉ khác vị trí: chúng thuộc hai provider/file system khác nhau. Hãy lấy đường dẫn đến tệp trong ZIP bằng `zipFs.getPath("/data.txt")`, không dùng `Path.of("/data.txt")` vốn thuộc hệ thống tệp mặc định.

Câu hỏi quyết định khi làm việc với API này là: **Đoạn mã hiện tại đã tạo/mở `FileSystem` mới, hay chỉ nhận tham chiếu đến `FileSystem` đang được quản lý ở nơi khác?** Câu trả lời quyết định ai được gọi `close()`.

## 2. Ba cách lấy FileSystem và ý nghĩa của chúng

| API | Vai trò | Kết quả điển hình | Quyền đóng |
| --- | --- | --- | --- |
| `FileSystems.getDefault()` | Lấy hệ thống tệp mặc định của JVM | Cùng `FileSystem` mặc định qua các lần gọi | **Không đóng**; `close()` của default FS ném `UnsupportedOperationException` |
| `FileSystems.newFileSystem(uri, env)` | Yêu cầu provider tạo/mở một `FileSystem` mới theo URI và cấu hình | Ví dụ mở một ZIP qua URI `jar:file:...` | Mã tạo thành công thường **sở hữu** `FileSystem` và phải đóng |
| `FileSystems.getFileSystem(uri)` | Lấy tham chiếu đến `FileSystem` **đang tồn tại** được provider tìm theo URI | Với ZipFS, lấy instance ZIP đã được mở trước đó | Mã tra cứu chỉ **mượn** tham chiếu; không tự đóng |

`FileSystems.getFileSystem(uri)` **không tạo mới**, không đảm bảo tệp ZIP trên đĩa đã được mount, và không có cơ chế tự tăng bộ đếm tham chiếu để giữ hệ thống tệp sống. Nếu chưa có instance phù hợp, thao tác thường ném `FileSystemNotFoundException`. Chi tiết tra cứu và nhận diện URI do provider quyết định.

Đối với `FileSystems.newFileSystem(URI, Map<String, ?>)`, Java chọn provider theo *scheme* của URI; một provider có thể từ chối URI không hỗ trợ, cấu hình sai hoặc trường hợp file system cùng định danh đã tồn tại. URI của ZipFS dùng scheme `jar`; URI `file` thông thường dùng cho đường dẫn hệ thống tệp mặc định. Không được coi hai loại URI này tương đương.

Các overload cần biết trong Java 17+:

~~~java
FileSystem a = FileSystems.newFileSystem(uri, env);
FileSystem b = FileSystems.newFileSystem(uri, env, classLoader);
FileSystem c = FileSystems.newFileSystem(path, env);
FileSystem d = FileSystems.newFileSystem(path);
~~~

Đây là **các lời gọi minh họa**, không phải chương trình độc lập; `uri`, `env`, `classLoader` và `path` cần được định nghĩa trước. Với overload nhận `Path`, Java có thể tìm provider hiểu định dạng tệp (ví dụ ZIP/JAR); cơ chế tìm kiếm, lựa chọn provider và khả năng mở tệp phụ thuộc overload/provider. Không giả định mọi overload đều tra cứu cùng một registry hay có chính sách trùng lặp giống hệt nhau.

## 3. Ví dụ chạy được: tạo ZIP FS, mượn, đóng và mở lại

JDK thông dụng có module `jdk.zipfs` hỗ trợ xem ZIP/JAR như một hệ thống tệp. Ví dụ sau dùng thư mục tạm mới, nên không ghi đè tệp hiện có. Chương trình tạo ZIP, ghi nội dung, lấy tham chiếu *mượn* đến cùng ZIP FS, đóng qua chủ sở hữu, rồi mở lại ZIP để chứng minh dữ liệu đã được lưu.

Tạo tệp `FileSystemLifecycleDemo.java`:

~~~java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class FileSystemLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path tempDir = Files.createTempDirectory("nio-fs-demo-");
        Path zipFile = tempDir.resolve("example.zip");
        URI zipUri = URI.create("jar:" + zipFile.toUri());

        FileSystem owner;
        try (FileSystem zipFs =
                FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
            owner = zipFs;

            Path entry = zipFs.getPath("/hello.txt");
            Files.writeString(entry, "Xin chào từ ZIP\n");

            // getFileSystem chỉ mượn instance đang mở.
            FileSystem borrowed = FileSystems.getFileSystem(zipUri);
            System.out.println("Cùng đối tượng: " + (borrowed == zipFs));
            System.out.println(Files.readString(borrowed.getPath("/hello.txt")).strip());

            // Không gọi borrowed.close(): owner vẫn đang sử dụng nó.
        } // Chủ sở hữu đóng ZipFS; dữ liệu ZIP được hoàn tất.

        System.out.println("Đã đóng: " + !owner.isOpen());

        try {
            FileSystems.getFileSystem(zipUri);
        } catch (FileSystemNotFoundException e) {
            System.out.println("Không tìm thấy ZIP FS đang mở");
        }

        try (FileSystem reopened = FileSystems.newFileSystem(zipUri, Map.of())) {
            System.out.println(
                    "Đọc lại: " + Files.readString(reopened.getPath("/hello.txt")).strip());
        }

        Files.delete(zipFile);
        Files.delete(tempDir);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+ có `jdk.zipfs`**:

~~~bash
javac FileSystemLifecycleDemo.java
java FileSystemLifecycleDemo
~~~

Đầu ra dự kiến trên JDK thông dụng:

~~~text
Cùng đối tượng: true
Xin chào từ ZIP
Đã đóng: true
Không tìm thấy ZIP FS đang mở
Đọc lại: Xin chào từ ZIP
~~~

Giải thích theo trình tự:

1. `Files.createTempDirectory` sinh thư mục riêng; `zipFile.toUri()` tạo URI `file:` đúng cho nền tảng đang chạy. Ghép tiền tố `jar:` để đưa URI cho ZipFS.
2. `Map.of("create", "true")` là cấu hình **riêng của ZipFS**: tạo tệp lưu trữ nếu chưa tồn tại. Với một ZIP có sẵn, có thể dùng `Map.of()` để mở.
3. `newFileSystem` trả về instance do đoạn `try` sở hữu. `getPath("/hello.txt")` trả `Path` **bên trong ZIP**.
4. `getFileSystem(zipUri)` trả về instance đang mở; phép so sánh `==` là `true` trong ví dụ này. Tham chiếu `borrowed` không được đóng.
5. Kết thúc `try-with-resources`, Java gọi `zipFs.close()` kể cả khi thân khối ném exception. Với `jdk.zipfs`, thao tác này hoàn tất việc ghi vào archive.
6. Sau khi đóng, ZipFS không còn đăng ký instance đang mở cho URI đó; `getFileSystem(zipUri)` ném `FileSystemNotFoundException`. Đây là **hành vi của ZipFS trong ví dụ**; API cho phép provider khác xử lý lookup sau `close()` khác nhau.
7. `newFileSystem(zipUri, Map.of())` mở lại archive đã có; lúc này `create` không cần thiết. Lần mở lại cũng được đóng qua `try-with-resources` trước khi xóa tệp tạm.

Nếu dùng runtime image đã lược bỏ `jdk.zipfs`, ví dụ có thể không tìm được provider `jar`. Hãy chạy bằng JDK đầy đủ có module đó; không suy diễn rằng API `FileSystems` tự cung cấp mọi provider.

## 4. Quy tắc sở hữu: người tạo đóng, người mượn không đóng

**Ownership (quyền sở hữu vòng đời)** là thỏa thuận giữa các lớp/method, không phải thuộc tính mà `FileSystem` tự kiểm tra. API không phân biệt được biến `owner` với biến `borrowed`: cả hai có thể chỉ đến **cùng một object**, và gọi `close()` qua biến nào cũng có hiệu lực trên object đó.

Quy tắc sử dụng thực tế:

- **Tạo riêng cho một công việc** bằng `newFileSystem`: đặt trong `try-with-resources`, đóng sau khi mọi `Path`, stream, channel và tác vụ sử dụng file system hoàn tất.
- **Lấy qua `getFileSystem` hoặc `path.getFileSystem()`**: xem là tham chiếu mượn trừ khi có hợp đồng chuyển quyền sở hữu rõ ràng. Không tự đóng trong hàm tiện ích.
- **Được truyền từ tham số hoặc dependency injection**: mặc định là tài nguyên do caller/application quản lý; hàm nhận không đóng nếu hợp đồng không yêu cầu.
- **Hệ thống tệp mặc định** lấy bằng `getDefault()`: không đưa vào `try-with-resources`; `close()` ném `UnsupportedOperationException`.
- **Quản lý dùng chung giữa nhiều thành phần/luồng**: đặt nơi tạo/đóng tại tầng sở hữu rõ ràng (ví dụ service manager), bảo đảm không còn tác vụ đang dùng trước khi đóng.

Cách viết hàm *mượn* an toàn:

~~~java
import java.io.IOException;
import java.nio.file.FileSystem;
import java.nio.file.Files;

static String readEntry(FileSystem borrowedFs, String entryName) throws IOException {
    // Hàm mượn FileSystem và chỉ đọc dữ liệu.
    return Files.readString(borrowedFs.getPath(entryName));
    // Không close borrowedFs ở đây.
}
~~~

Đoạn trên là **method minh họa**, phải đặt trong một class và có quyền đọc entry mong muốn. Caller giữ trách nhiệm đóng `FileSystem` nếu caller đã tạo ra nó. Hàm đọc không giữ tham chiếu sống vượt thời gian gọi.

Một anti-pattern nguy hiểm:

~~~java
static String badRead(FileSystem sharedFs) throws IOException {
    try (sharedFs) {
        return Files.readString(sharedFs.getPath("/hello.txt"));
    }
}
~~~

`try (sharedFs)` hợp lệ trong Java 9+ nếu biến *effectively final*, nhưng vẫn **sai về ownership** khi `sharedFs` là tham chiếu mượn. Kết thúc hàm sẽ đóng hệ thống tệp mà caller hoặc thread khác còn cần dùng. Tính hợp lệ của cú pháp không đồng nghĩa với việc có quyền đóng tài nguyên.

## 5. FileSystem, Path và các resource có vòng đời khác nhau

Một `Path` có thể được lưu vào biến, đưa vào collection hoặc trả khỏi phương thức, nhưng không giúp hệ thống tệp tiếp tục mở. Khi parent `FileSystem` đã đóng, các thao tác đọc/ghi trên `Path` liên quan có thể ném `ClosedFileSystemException`. Ví dụ minh họa lỗi:

~~~java
Path entry;
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    entry = zipFs.getPath("/hello.txt");
}
Files.readString(entry); // ClosedFileSystemException: ZipFS đã đóng
~~~

Đây chỉ là **đoạn minh họa**, giả sử `zipUri` trỏ đến archive hợp lệ. Cách sửa là xử lý nội dung khi `FileSystem` còn mở, hoặc trả dữ liệu đã đọc (`String`/`byte[]`) thay vì trả `Path` có vòng đời dài hơn tài nguyên nền.

Đóng `FileSystem` sẽ đóng các channel, directory stream, watch service và các closeable object liên kết theo hợp đồng API; tuy vậy vẫn nên đóng những resource cục bộ ngay khi dùng xong để kiểm soát lỗi và thời gian giữ tài nguyên. Với stream từ `Files.lines(...)` hoặc `Files.walk(...)`, hãy dùng `try-with-resources` riêng để đóng `Stream` đúng lúc. Tránh đóng parent file system trong khi các luồng còn chạy thao tác I/O.

Ví dụ thứ tự đóng đúng (resource con đóng trước parent):

~~~java
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    try (var lines = Files.lines(zipFs.getPath("/log.txt"))) {
        lines.forEach(System.out::println);
    }
} // Đóng ZipFS sau khi Stream đã đóng.
~~~

Đoạn minh họa giả định ZIP tồn tại và chứa `/log.txt`. Khi có nhiều lỗi trong `try-with-resources`, lỗi trong `close()` có thể xuất hiện dưới dạng *suppressed exception* của lỗi chính; không nuốt lỗi đóng vì ZipFS có thể cần hoàn tất dữ liệu.

## 6. Các tình huống thường gặp và cách xử lý

| Tình huống | Hành vi cần hiểu | Cách làm |
| --- | --- | --- |
| Muốn tạo ZIP mới | `newFileSystem(jarUri, Map.of("create", "true"))` | Chủ sở hữu đóng sau khi ghi xong |
| Muốn mở ZIP đã có | `newFileSystem(jarUri, Map.of())` | Dùng `try-with-resources` trong phạm vi công việc |
| ZIP FS đã được một component khác mở | `getFileSystem(jarUri)` lấy instance đang mở | Mượn và tuân theo vòng đời của component sở hữu |
| Chưa có instance nhưng gọi `getFileSystem` | `FileSystemNotFoundException` | Mở bằng `newFileSystem` ở nơi được giao quyền sở hữu |
| Cùng URI đang mở mà tiếp tục `newFileSystem(URI, ...)` | Với ZipFS thường ném `FileSystemAlreadyExistsException` | Tổ chức một chủ sở hữu rõ ràng; client lấy tham chiếu mượn |
| Đóng FS trong khi nơi khác sử dụng | Đường dẫn/I/O có thể gặp `ClosedFileSystemException` | Chỉ chủ sở hữu đóng khi các tác vụ đã kết thúc |
| Cố `close()` FS mặc định | `UnsupportedOperationException` | Không đóng `FileSystems.getDefault()` |
| Ghi vào FS chỉ đọc | `ReadOnlyFileSystemException` | Kiểm tra `isReadOnly()` và chế độ/provider |
| Không tìm được provider `jar` | Provider/module chưa có hoặc không được tải | Kiểm tra JDK/runtime có `jdk.zipfs` |
| Tạo/mở ZIP với URI hoặc cấu hình sai | Có thể gặp `IllegalArgumentException`, `ProviderNotFoundException` hoặc `IOException` tùy API/provider | Dùng đúng URI, config, provider và kiểm tra nguyên nhân gốc |

Không viết kiểu “nếu `getFileSystem` thất bại thì `newFileSystem`” tại nhiều nơi dùng chung mà không đồng bộ. Hai thread đều có thể thấy chưa tồn tại rồi cùng cố tạo; một thread có thể nhận `FileSystemAlreadyExistsException`. Hơn nữa, vừa lấy được tham chiếu không bảo đảm chủ sở hữu khác sẽ không đóng nó ngay sau đó. Thiết kế quản lý tài nguyên phải giải quyết cả **quyền sở hữu** lẫn **thời gian sử dụng**.

### Phân biệt các exception theo mục đích

- `FileSystemNotFoundException`: lookup không tìm được file system/provider phù hợp; hay gặp ở `getFileSystem(uri)` khi ZIP chưa mở.
- `FileSystemAlreadyExistsException`: yêu cầu tạo mới trùng file system đã tồn tại theo quy tắc của provider; hay gặp ở `newFileSystem(URI, ...)` cho cùng ZIP đang mở.
- `ClosedFileSystemException`: file system đã đóng nhưng có thao tác cần dùng nó.
- `ProviderNotFoundException`: không có provider phù hợp trong một số đường tạo/mở; khác với việc có provider nhưng chưa có instance.
- `IOException`: lỗi thực sự khi truy cập, mở, ghi, flush hoặc đóng dữ liệu; phải xử lý theo logic I/O và giữ thông tin nguyên nhân.

Đừng bắt rộng `RuntimeException` để che ba nhóm vấn đề khác nhau: **chưa mở**, **đã mở**, **đã đóng**.

## 7. Chọn API theo câu hỏi thực tế

Giả sử chức năng cần đọc một tệp `config.json` nằm trong `settings.zip`:

1. Nếu chức năng tự chịu trách nhiệm mở archive cho một lượt đọc, tạo `FileSystem` bằng `newFileSystem(...)`, đọc dữ liệu bên trong `try` rồi đóng. Hợp đồng method nên trả nội dung hoặc đối tượng dữ liệu, không trả `Path` thuộc ZIP đã đóng.
2. Nếu ứng dụng đã có dịch vụ quản lý ZIP FS lâu dài, chức năng đọc nhận `FileSystem` hoặc dùng `getFileSystem(uri)` theo hợp đồng của dịch vụ. Không tự đóng sau một yêu cầu nhỏ.
3. Nếu cần đường dẫn bình thường trên máy, sử dụng `Path.of(...)`/`Files...` với default FS; không tạo hoặc đóng `FileSystem` mới.
4. Nếu client phải dùng tệp ZIP từ nhiều luồng, chủ sở hữu chỉ đóng sau khi tất cả công việc kết thúc; tham chiếu mượn không phải một “lease” tự bảo vệ trước `close()`.

Hãy xác định ngay tại API boundary: **ai tạo, ai mượn, tài nguyên sống tới khi nào, và ai được đóng**. Tài liệu hợp đồng của một helper nên chỉ rõ điều đó. Nếu method *trả về một `FileSystem` mới cho caller*, hãy nói rõ caller chịu trách nhiệm đóng; nếu method *trả một instance dùng chung*, hãy nói rõ caller không được đóng.

## 8. Những lỗi phổ biến cần tránh

- **Hiểu `getFileSystem` là thao tác mở ZIP**: nó chỉ tra cứu instance đang tồn tại; archive tồn tại trên đĩa chưa đủ.
- **Quên `close()` sau `newFileSystem`**: ZIP có thể còn giữ resource và các thay đổi chưa được hoàn tất đúng vòng đời.
- **Đóng đối tượng mượn**: vô tình đóng cùng instance mà nơi sở hữu và các thread khác đang dùng.
- **Đóng default FS**: `FileSystems.getDefault().close()` không được hỗ trợ.
- **Giữ `Path` sau khi ZIP FS đã đóng**: path không thể dùng cho I/O khi file system nền không còn mở.
- **Nhầm `jar:` với `file:` hoặc path bên trong ZIP**: `jar:file:/.../archive.zip` định danh ZIP FS cho ZipFS; `zipFs.getPath("/entry.txt")` định danh entry trong FS ấy.
- **Tự ghép đường dẫn máy bằng chuỗi cứng**: ưu tiên `Path.toUri()` để giữ đúng escape và dấu phân cách trên hệ điều hành.
- **Dựa vào registry provider như cơ chế quản lý concurrency**: lấy được reference không trao ownership và không ngăn chủ sở hữu khác đóng.
- **Dùng try-with-resources bừa bãi**: chỉ dùng trên `FileSystem` do khối mã sở hữu hoặc được hợp đồng yêu cầu đóng.

## 9. Câu hỏi tự kiểm tra

1. Một method gọi `FileSystems.getFileSystem(uri)` và thấy trả về `FileSystem`. Method đó có được đóng nó không? **Thông thường không**: nó chỉ mượn tham chiếu, quyền đóng phải được hợp đồng xác nhận.
2. ZIP tồn tại trên đĩa nhưng chưa hề được mở bằng ZipFS; `getFileSystem(jarUri)` có đọc được ngay không? **Không**: với ZipFS, chưa có instance nên thường là `FileSystemNotFoundException`.
3. Vì sao trả `Path` trong ZIP ra khỏi khối `try (FileSystem fs = ...)` là nguy hiểm? Vì `Path` tham chiếu đến FS đã đóng; thao tác I/O về sau có thể ném `ClosedFileSystemException`.
4. Lúc nào dùng `try-with-resources` với `FileSystem`? Khi phạm vi mã **sở hữu** file system mới tạo/mở và cần bảo đảm đóng sau khi hoàn thành công việc.
5. Có thể xem `getDefault()` như `newFileSystem(...)` để đóng cuối tác vụ không? **Không**: default FS là tài nguyên nền JVM, thao tác đóng không được hỗ trợ.

## Tài liệu chuẩn để tra cứu

- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): chữ ký overload, provider lookup và các ngoại lệ.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): vòng đời, `close()`, `isOpen()`, file system mặc định.
- [Java SE 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): scheme `jar`, cấu hình `create` và ZIP/JAR provider.
