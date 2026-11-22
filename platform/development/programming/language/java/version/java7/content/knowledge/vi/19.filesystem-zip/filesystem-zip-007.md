# Java 7 — FileSystem và ZIP: Đóng FileSystem và vòng đời các Path liên quan

## 1. Mục tiêu bài học

Trong NIO.2, `java.nio.file.FileSystem` không chỉ là một “đường dẫn” mà là **một hệ thống tệp đang được mở** do `FileSystemProvider` quản lý. FileSystem tạo ra các đối tượng `Path`, cung cấp API cho việc truy cập entry và có **vòng đời** rõ ràng: mở, sử dụng, rồi đóng nếu đó là FileSystem có thể đóng.

Đặc biệt, Java có thể **mount một tệp ZIP hoặc JAR dưới dạng FileSystem**, nhờ provider `jdk.zipfs`. Khi đó bạn có thể thao tác với các entry bên trong archive bằng `Files.createDirectories`, `Files.writeString`, `Files.copy`, `Files.readString`, `Files.walk` và nhiều API NIO.2 thông thường, miễn là FileSystem sở hữu các Path đó còn mở.

Một lỗi phổ biến là:

1. Tạo một ZIP FileSystem trong `try-with-resources`.
2. Lấy ra một `Path` tới entry ở bên trong ZIP.
3. Thoát khối try, làm FileSystem bị đóng.
4. Mang `Path` cũ ra sử dụng tiếp với `Files.readString` hoặc `Files.newInputStream`.
5. Gặp **`ClosedFileSystemException`** dù object `Path` vẫn tồn tại trong Java.

Bài học tập trung vào cách **đóng FileSystem và hiểu vòng đời các Path liên quan**, không phải chỉ cách nén/giải nén ZIP. Các kiến thức cốt lõi đã có từ **Java 7**, vẫn áp dụng với **Java 17+**; ví dụ dùng các API hiện đại như `Path.of`, `Files.writeString` và `Map.of`.

Sau bài học, bạn có thể:

- Phân biệt **default FileSystem** và **FileSystem do ứng dụng mount**.
- Xác định ai **sở hữu trách nhiệm đóng** và ai chỉ **mượn** FileSystem.
- Sử dụng `try-with-resources` để tránh rò rỉ ZIP FileSystem, channel, stream.
- Nhận diện `ClosedFileSystemException` và tác động của việc đóng lên Path cũ.
- Mở lại ZIP và tạo **Path mới** thay vì tái sử dụng Path của instance đã đóng.
- Hiểu `FileSystems.newFileSystem(...)`, `FileSystems.getFileSystem(URI)` và xung đột mount.
- Thiết kế API trả dữ liệu bền vững hơn việc trả Path với vòng đời không rõ.
- Xử lý lỗi lúc đóng, concurrency, copy giữa providers và test portability.

## 2. Mô hình: FileSystem, FileSystemProvider và Path

Cấu trúc quan hệ:

```text
FileSystems.getDefault()
    └── FileSystem mặc định (file:///, provider của hệ điều hành)
          ├── Path.of("C:/data/report.txt") hoặc Path.of("/data/report.txt")
          ├── Files.newInputStream(path)
          └── Luôn mở; không được đóng bằng close()

FileSystems.newFileSystem(jarUri, env)
    └── ZIP FileSystem (jar:..., provider jdk.zipfs)
          ├── zip.getPath("/docs/readme.txt") ──► ZIP Path
          ├── zip.getPath("/images/logo.png")  ──► ZIP Path
          ├── DirectoryStream/Stream/Channel từ ZIP Path
          └── zip.close() ──► FileSystem đóng
                                   └── I/O từ ZIP Path cũ không còn dùng được
```

`FileSystem` là factory cho `Path`, `PathMatcher`, các views/stores và các đối tượng khác, còn `Files` thực hiện những thao tác dựa trên provider của Path.

### 2.1. Một Path luôn gắn với một FileSystem

```java
Path local = Path.of("notes.txt");
FileSystem localFs = local.getFileSystem();
```

Đây là **snippet trong phương thức** với import `java.nio.file.Path` và `java.nio.file.FileSystem`. `local` thuộc default FileSystem trong môi trường thông thường.

Với ZIP:

```java
Path entry = zipFs.getPath("/notes.txt");
FileSystem entryFs = entry.getFileSystem();
```

Đây là snippet với biến `FileSystem zipFs` đang mở. `entryFs == zipFs` cho biết entry thuộc ZIP FileSystem đó. Cùng chuỗi `"/notes.txt"` không có nghĩa hai Path thuộc hai providers khác nhau trỏ cùng đối tượng.

### 2.2. Path là object, không phải file descriptor đã mở

Một `Path` **biểu diễn địa chỉ** theo quy tắc của FileSystem mà nó thuộc về. Nó không tự mở file hoặc chụp nội dung file tại thời điểm tạo.

Ví dụ:

```java
Path entry = zipFs.getPath("/docs/readme.txt");
System.out.println(entry.getFileSystem() == zipFs);
```

Đây là snippet, yêu cầu `zipFs` đã được mở. Khi ZIP FileSystem đóng, biến `entry` **không tự biến thành null hoặc bị Java garbage collector xóa ngay**. Nhưng object Path cũ vẫn gắn với **FileSystem đã đóng**, và việc truy cập filesystem thông qua object đó phải tuân theo trạng thái đóng.

Điều đó khác với Path của default FileSystem: đóng **một ZIP** không làm các `Path.of(...)` thuộc default FileSystem mất hiệu lực.

## 3. Điều Java SE 17 bảo đảm khi đóng FileSystem

Javadoc `FileSystem.close()` quy định:

1. **FileSystem mới được tạo có trạng thái mở.**
2. Sau khi FileSystem đóng, những lần truy cập filesystem đó qua các phương thức của FileSystem hoặc các object gắn với nó ném **`ClosedFileSystemException`**.
3. Nếu FileSystem **đã đóng**, gọi `close()` lần nữa **không có tác dụng**.
4. Đóng FileSystem sẽ đóng các **channels, directory streams, watch services và các resource đóng được khác** gắn với FileSystem đó.
5. `close()` có thể ném **`IOException`**.
6. **Default FileSystem không thể đóng**; cố gọi `close()` có thể ném `UnsupportedOperationException`.
7. FileSystem có thể được dùng bởi nhiều thread, nhưng việc đóng đồng thời khi một thread đang truy cập được xử lý ra sao là **tùy provider** — không hứa dừng ngay lập tức hay không có blocking.

### 3.1. Kiểm tra trạng thái với isOpen()

```java
boolean currentlyOpen = zipFs.isOpen();
```

Đây là snippet với `FileSystem zipFs`. `isOpen()` giúp đọc trạng thái hiện tại. Tuy nhiên, **kiểm tra trước không đảm bảo thao tác kế tiếp thành công** nếu thread khác có thể đóng FileSystem ngay sau khi kiểm tra.

Nếu code yêu cầu “còn mở suốt thời gian làm việc”, cần **quản lý ownership/lifetime** giữa các thread, không chỉ kiểm tra boolean.

### 3.2. close không chỉ tác động lên object FileSystem

Một số resource có thể liên quan:

```text
ZIP FileSystem đang mở
├── ZIP Path A
├── ZIP Path B
├── SeekableByteChannel tạo từ Path A
├── DirectoryStream duyệt một thư mục bên trong ZIP
└── Stream<Path> tạo từ Files.walk(...)
```

Khi FileSystem đóng, các resource liên quan có thể bị đóng theo hợp đồng. Dùng lại chúng sau khi FileSystem đóng sẽ thất bại hoặc không còn giá trị sử dụng. Đừng hứa code vẫn đọc được phần dữ liệu còn trong buffer sau close: hành vi cấp thấp/phương thức cụ thể tùy triển khai và không phải hợp đồng I/O nên dựa vào.

### 3.3. close có thể là thao tác I/O thật

Với ZIP FileSystem của JDK, việc đóng có thể liên quan đến **hoàn tất các thay đổi trong archive**. Lỗi ghi vào ổ đĩa, hết dung lượng, mất quyền hoặc provider lỗi có thể khiến `close()` ném IOException. Vì vậy không coi “đã thoát thân try” đồng nghĩa archive cuối cùng chắc chắn hợp lệ cho mọi trường hợp.

Không tự mở một ZIP bằng FileSystem rồi quên close, vì có thể giữ tài nguyên và làm chậm/quản lý việc hoàn tất file ZIP. Ngược lại, cũng **không đóng quá sớm** khi còn các thao tác dùng ZIP Path.

## 4. Default FileSystem khác với FileSystem mount từ ZIP

### 4.1. Default FileSystem luôn mở

```java
FileSystem defaultFs = FileSystems.getDefault();
System.out.println(defaultFs.isOpen()); // true
```

Đây là snippet Java 17+ trong một phương thức, với imports FileSystem/FileSystems. Theo hợp đồng Java SE 17, FileSystem do default provider tạo **luôn mở**. Bạn không được dùng:

```java
try (FileSystem fs = FileSystems.getDefault()) {
    // Không nên xem default FS là resource mình sở hữu.
}
```

Đây là **anti-pattern** để nhận diện. Try-with-resources sẽ cố gọi `close()` lúc thoát, nhưng default FileSystem **không hỗ trợ close** và `UnsupportedOperationException` có thể được ném. Không thêm xử lý “catch rồi bỏ qua” để hợp thức hóa ownership sai.

### 4.2. ZIP/custom FileSystem thường cần close

```java
URI archiveUri = URI.create("jar:" + archivePath.toUri());

try (FileSystem zipFs = FileSystems.newFileSystem(
        archiveUri, Map.of())) {
    Path entry = zipFs.getPath("/docs/readme.txt");
    String text = Files.readString(entry, StandardCharsets.UTF_8);
    System.out.println(text);
}
```

Đây là snippet **trong phương thức**, yêu cầu `Path archivePath` trỏ đến ZIP/JAR **đã tồn tại**, provider `jdk.zipfs` sẵn có, imports `URI`, `FileSystem`, `FileSystems`, `Files`, `Path`, `Map`, `StandardCharsets` và xử lý `IOException`. ZIP FileSystem được **tạo trong scope** nên nên **đóng trong chính scope đó**.

### 4.3. Tại sao hai trường hợp có lifecycle khác?

Default FileSystem là môi trường I/O chung của JVM. Các `Path.of(...)` thông thường do default provider quản lý; nếu ai cũng đóng tùy ý, JVM sẽ không thể dùng các đường dẫn tệp thông thường. Vì vậy hợp đồng cấm đóng default FS.

Trái lại, một ZIP/custom FileSystem được mount có **tài nguyên và phạm vi riêng**. Bạn có thể có một instance ZIP FileSystem cho archive A và một instance khác cho archive B. Khi công việc với archive A kết thúc, đóng instance A để giải phóng tài nguyên; archive B và default FileSystem không bị đóng theo.

**Cần phân biệt:** “provider của FileSystem” và “đối tượng FileSystem instance” không giống nhau. Đóng một ZIP FileSystem không hủy lớp provider toàn cục; bạn có thể tạo instance mới theo chính sách provider.

## 5. ZIP FileSystem: mount tệp ZIP như một cây Path

Trong JDK 17, module **`jdk.zipfs`** cung cấp ZIP/JAR FileSystem provider. Nó biểu diễn các entry bên trong archive như một hệ thống tệp; scheme URI nhận diện provider là **`jar`**.

### 5.1. URI cho ZIP FileSystem

```java
Path archive = Path.of("data", "lessons.zip").toAbsolutePath();
URI uri = URI.create("jar:" + archive.toUri());
```

Đây là snippet trong một phương thức, với imports `Path` và `URI`. Ví dụ `archive.toUri()` có thể trả `file:///.../lessons.zip`, sau đó URI của ZIP FileSystem là `jar:file:///.../lessons.zip`.

**Đừng nhầm URI của whole FileSystem với URI một entry** trong ZIP. Entry có thể được biểu diễn trong một URI kiểu `jar:file:///.../lessons.zip!/docs/readme.txt`, tùy provider. Khi tạo FileSystem từ URI, dùng **archive URI** đúng định dạng mà provider yêu cầu.

### 5.2. Tạo ZIP mới với create=true

```java
Path workDir = Files.createTempDirectory("zip-demo-");
Path archive = workDir.resolve("lesson.zip"); // Chưa tồn tại.
URI uri = URI.create("jar:" + archive.toUri());

try (FileSystem zipFs = FileSystems.newFileSystem(
        uri, Map.of("create", "true"))) {
    Path entry = zipFs.getPath("/docs/readme.txt");
    Files.createDirectories(entry.getParent());
    Files.writeString(entry, "hello zip", StandardCharsets.UTF_8);
}
```

Đây là **snippet trong phương thức** với imports FileSystem, FileSystems, Files, Path, URI, Map, StandardCharsets và xử lý IOException. Dùng một `Path` ZIP **chưa tồn tại**; property `"create"="true"` yêu cầu ZIP provider tạo archive nếu chưa có. Sau đó cần dọn `archive` và `workDir` ở một scope/finally phù hợp.

**Sai lầm thường gặp:** tạo tệp bằng `Files.createTempFile("...", ".zip")` (kết quả là file rỗng **đã tồn tại**) rồi nghĩ `"create"="true"` luôn chuyển file rỗng đó thành ZIP hợp lệ. Với ZIP provider, file đã tồn tại nhưng không phải archive hợp lệ có thể bị từ chối; nên tạo thư mục tạm trước, rồi chọn **tên archive chưa tồn tại**.

### 5.3. Mở một ZIP đã có

```java
try (FileSystem zipFs = FileSystems.newFileSystem(
        archiveUri, Map.of())) {
    Path entry = zipFs.getPath("/docs/readme.txt");
    System.out.println(Files.readString(entry));
}
```

Đây là snippet, `archiveUri` là một URI `jar:...` hợp lệ, ZIP đã tồn tại. `Map.of()` là môi trường không yêu cầu tạo archive mới. Nếu archive bị hỏng, không đọc được, hoặc provider không có, việc mount có thể thất bại.

### 5.4. Những property nào là provider-specific?

`"create"`, `"encoding"` và các ZIP properties khác được mô tả trong tài liệu module `jdk.zipfs`. Chúng **không phải property chung cho mọi FileSystemProvider**. Một provider tùy biến có thể dùng cấu hình khác, hoặc không chấp nhận key đó.

Một runtime JDK được đóng gói tùy chỉnh bằng `jlink` có thể **không chứa module `jdk.zipfs`**. Khi không có provider hỗ trợ scheme `jar`, `FileSystems.newFileSystem(archiveUri, env)` có thể ném `ProviderNotFoundException`. Không hard-code giả định mọi runtime Java đều chắc chắn có ZIP provider.

## 6. Chương trình Java 17+ hoàn chỉnh — đóng, Path cũ, mở lại

Ví dụ sau tạo archive trong thư mục tạm; trong lúc ZIP FileSystem mở, ghi và đọc một entry. Nó cố mount **trùng URI** để minh họa xung đột, sau đó đóng FileSystem và chứng minh `Path` cũ không đọc được. Cuối cùng, mở lại archive để lấy **Path mới** và đọc nội dung vẫn còn.

**Tệp: `ZipLifecycleDemo.java`**

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.ClosedFileSystemException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemAlreadyExistsException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path temporaryDirectory = Files.createTempDirectory("zip-lifecycle-demo-");
        Path archive = temporaryDirectory.resolve("lessons.zip");
        URI archiveUri = URI.create("jar:" + archive.toUri());
        FileSystem original = null;
        Path oldEntry = null;

        try {
            try (FileSystem zip = FileSystems.newFileSystem(
                    archiveUri, Map.of("create", "true"))) {
                original = zip;
                oldEntry = zip.getPath("/docs/readme.txt");
                Files.createDirectories(oldEntry.getParent());
                Files.writeString(oldEntry, "hello zip", StandardCharsets.UTF_8);

                System.out.println("zip open = " + zip.isOpen());
                System.out.println("entry content = " +
                        Files.readString(oldEntry, StandardCharsets.UTF_8));
                System.out.println("entry belongs to zip = " +
                        (oldEntry.getFileSystem() == zip));
                System.out.println("lookup returns same mount = " +
                        (FileSystems.getFileSystem(archiveUri) == zip));
                try {
                    FileSystems.newFileSystem(archiveUri, Map.of());
                    System.out.println("second mount = unexpected");
                } catch (FileSystemAlreadyExistsException expected) {
                    System.out.println("second mount = FileSystemAlreadyExistsException");
                }
            }

            System.out.println("original zip closed = " + !original.isOpen());
            try {
                Files.readString(oldEntry, StandardCharsets.UTF_8);
                System.out.println("old path read = unexpected");
            } catch (ClosedFileSystemException expected) {
                System.out.println("old path read = ClosedFileSystemException");
            }

            System.out.println("archive exists on default = " +
                    Files.isRegularFile(archive));
            try (FileSystem reopened = FileSystems.newFileSystem(
                    archiveUri, Map.of())) {
                Path freshEntry = reopened.getPath("/docs/readme.txt");
                System.out.println("reopened reads = " +
                        Files.readString(freshEntry, StandardCharsets.UTF_8));
                System.out.println("fresh entry belongs to reopened = " +
                        (freshEntry.getFileSystem() == reopened));
                System.out.println("old path still closed = " +
                        !oldEntry.getFileSystem().isOpen());
            }
            System.out.println("default filesystem open = " +
                    FileSystems.getDefault().isOpen());
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(temporaryDirectory);
        }
    }
}
```

Biên dịch và chạy với JDK 17+ (có module `jdk.zipfs`):

```bash
javac --release 17 ZipLifecycleDemo.java
java ZipLifecycleDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, với ZIP provider có sẵn:**

```text
zip open = true
entry content = hello zip
entry belongs to zip = true
lookup returns same mount = true
second mount = FileSystemAlreadyExistsException
original zip closed = true
old path read = ClosedFileSystemException
archive exists on default = true
reopened reads = hello zip
fresh entry belongs to reopened = true
old path still closed = true
default filesystem open = true
```

**Giải thích kết quả theo thứ tự:**

1. `zip open = true` — instance ZIP FileSystem đang mở trong try-with-resources.
2. `entry content = hello zip` — Path thuộc ZIP FileSystem có thể đọc/ghi entry khi filesystem vẫn mở.
3. `entry belongs to zip = true` — `oldEntry.getFileSystem()` chính là object `zip`.
4. `lookup returns same mount = true` — trong ZIP provider JDK với URI vừa mount, `FileSystems.getFileSystem(archiveUri)` trả **instance đang mở**, không tạo một FileSystem mới.
5. `second mount = FileSystemAlreadyExistsException` — thử `newFileSystem` **cùng URI khi mount cũ vẫn hoạt động** bị từ chối. Không nên dùng exceptions như một cơ chế chia sẻ ownership không có điều phối.
6. Sau khi rời khối try, `original zip closed = true`.
7. Object `oldEntry` vẫn còn nhưng `Files.readString(oldEntry)` ném `ClosedFileSystemException`, được bắt và in ra.
8. `archive exists on default = true` — ZIP **vẫn là tệp archive thật** trên default filesystem; đóng ZIP view không xóa archive.
9. `reopened reads = hello zip` — mở lại archive tạo ZIP FileSystem mới và đọc đúng dữ liệu đã ghi.
10. `fresh entry belongs to reopened = true` — Path mới thuộc **FileSystem mới**.
11. `old path still closed = true` — việc mở lại archive **không hồi sinh Path cũ**; nó vẫn gắn với object đã đóng.
12. `default filesystem open = true` — đóng ZIP không ảnh hưởng default filesystem.

**Lưu ý về phạm vi kiểm thử:** Chương trình sử dụng **ZIP provider JDK 24** trên Windows. Hợp đồng chung của FileSystem nói rằng đóng làm I/O trên Path cũ thất bại; kết quả về duplicate URI và lookup được kiểm chứng với ZIP provider ở môi trường thử nghiệm, và các chi tiết sau close của lookup URI **phụ thuộc provider**. Nếu thiếu ZIP provider, quyền ghi thư mục tạm hoặc archive có lỗi, chương trình có thể thất bại khi mount/đọc/ghi/close.

### 6.1. Vì sao mã có `original` và `oldEntry` ngoài khối try?

Đó là cách **cố ý giữ tham chiếu** đến FileSystem và Path sau khi scope đóng, nhằm minh họa lỗi lifecycle. Đây **không** phải mẫu thiết kế được khuyên dùng trong ứng dụng production; phần 10 sẽ đưa mẫu đúng hơn.

### 6.2. Vì sao dùng Path archive khác Path oldEntry?

`archive` là Path thuộc **default filesystem**, trỏ tới tệp ZIP trên ổ đĩa. `oldEntry` là Path thuộc **ZIP FileSystem**, trỏ tới entry bên trong archive. Đóng ZIP FileSystem làm mất khả năng truy cập entry qua oldEntry, nhưng **không** làm archive Path của default filesystem ngừng hoạt động.

### 6.3. Vì sao finally xóa sau khi đóng các mount?

Nếu xóa ZIP archive khi vẫn có ZIP FileSystem mở, một số OS có thể từ chối vì handle còn hoạt động; một số môi trường cho phép nhưng semantics khác. Ví dụ xóa archive **sau** khi các TWR đã đóng. Khối finally chỉ xóa thư mục/file tạm do chính chương trình tạo, không xóa dữ liệu người dùng.

## 7. Sau khi đóng: Path còn là object nhưng không còn quyền truy cập provider

**Điểm cốt lõi:** Java object `Path` không có phương thức `close()`, và GC không tự biến mọi Path của FileSystem đóng thành null. Nhưng Path **gắn với provider object cũ**, nên I/O thông qua nó không còn hợp lệ.

```java
Path stale;
FileSystem opened = FileSystems.newFileSystem(zipUri, Map.of());
try {
    stale = opened.getPath("/data/items.txt");
} finally {
    opened.close();
}
Files.readString(stale); // Có thể ném ClosedFileSystemException.
```

Đây là snippet **chủ ý minh họa hành vi thất bại**, với ZIP đã tồn tại và xử lý IOException. Đừng đặt vào ứng dụng nếu còn muốn đọc file sau khi đóng.

### 7.1. Những thao tác nào không nên gọi sau close?

Không sử dụng Path của closed FileSystem để:

- `Files.readString`, `Files.writeString`, `Files.newInputStream`, `Files.newOutputStream`.
- `Files.newByteChannel`, `Files.copy`, `Files.move`, `Files.delete`.
- `Files.list`, `Files.walk`, `Files.newDirectoryStream`.
- `Files.readAttributes` hoặc lấy các attribute views/stores của file đã đóng.
- Mở `WatchService` gắn với FileSystem đã đóng.

Theo hợp đồng, các thao tác **truy cập filesystem** trên những đối tượng gắn với instance đã đóng sẽ báo `ClosedFileSystemException`. Các thao tác thuần cấu trúc/chuỗi của Path, như `getFileName` hoặc `toString`, có thể vẫn tạo kết quả trong một số implementations, nhưng **không khôi phục khả năng I/O**, và không nên dùng làm bằng chứng FileSystem vẫn mở.

### 7.2. Không dùng Files.exists để phân biệt closed với missing

```java
boolean exists = Files.exists(stalePath);
```

Đây là snippet minh họa với `Path stalePath`. `Files.exists` có thể trả false **khi không xác định được sự tồn tại**, không chỉ khi thực sự không có file. Do đó, không dùng `Files.exists(stalePath) == false` để kết luận entry đã bị xóa; với closed ZIP FileSystem, trạng thái lifecycle phải được kiểm tra qua `stalePath.getFileSystem().isOpen()` và xử lý đúng ngoại lệ I/O.

**Đừng âm thầm đổi ClosedFileSystemException thành “file not found”.** Lỗi này thường cho biết API đã trả Path ra ngoài lifetime của FileSystem hoặc một component khác đã đóng mount dùng chung.

### 7.3. Đóng xong rồi mở lại không hồi sinh stale Path

```java
Path oldPath = firstZip.getPath("/data/items.txt");
firstZip.close();

try (FileSystem secondZip = FileSystems.newFileSystem(zipUri, Map.of())) {
    Path newPath = secondZip.getPath("/data/items.txt");
    // Chỉ dùng newPath trong scope secondZip còn mở.
}
```

Đây là snippet trong phương thức với `FileSystem firstZip` đang mở trước khi gọi, `URI zipUri` hợp lệ và ZIP có sẵn. Nếu provider cho phép mở lại cùng URI, `newPath` thuộc instance mới; `oldPath` vẫn thuộc instance đã đóng.

Các Path có cùng tên hiển thị không có nghĩa cùng filesystem identity. `Path.equals` và `Path.compareTo` không phải cách đáng tin để chứng minh hai entry ở hai FileSystem instances khác nhau là cùng một đối tượng dữ liệu.

## 8. Quy tắc ownership: ai được phép đóng FileSystem?

### 8.1. Người tạo resource thường sở hữu resource

Một quy tắc đơn giản:

- Hàm trực tiếp **gọi `newFileSystem`** thường là **owner** và chịu trách nhiệm close.
- Hàm nhận `FileSystem` hoặc `Path` như tham số thường **borrow** để sử dụng trong khi caller bảo đảm resource còn sống.
- Hàm gọi `FileSystems.getFileSystem(uri)` thường lấy **tham chiếu tới instance sẵn có**, không tự nhiên được quyền đóng nó.
- Default FileSystem là **shared singleton** của JVM, không ai nên đóng.

Ví dụ giao diện:

```java
static String readEntry(FileSystem archive, String name) throws IOException {
    Path entry = archive.getPath(name);
    return Files.readString(entry);
}
```

Đây là **phương thức hoàn chỉnh trong một class** với imports FileSystem/Path/Files/IOException. Phương thức **không gọi archive.close()** vì nó chỉ mượn FileSystem. Caller phải bảo đảm archive còn mở trong suốt lúc `readEntry` chạy.

### 8.2. Đóng một shared FileSystem gây lỗi cho nhiều người

Giả sử service A mount một archive và chia sẻ `FileSystem zip` cho service B/C. Nếu B tự đóng zip khi xong một request, C có thể đang đọc ZIP Path và gặp lỗi ngoài dự kiến. Javadoc FileSystem cho phép nhiều thread cùng sử dụng; nhưng việc đóng đồng thời với thao tác đang chạy là **provider-specific**, có thể chặn/đợi hoặc gây ảnh hưởng khác.

Để tránh:

1. Định nghĩa owner của mount ở tầng cao, ví dụ `ArchiveManager`.
2. Tất cả worker được cấp **lease/lifetime scope** rõ ràng, không được tự đóng shared FileSystem.
3. Owner chỉ close sau khi không còn worker sử dụng; cần synchronization hoặc ref-count/lease tùy thiết kế.
4. Không truyền Path borrowed sang hàng đợi asynchronous khi không giữ FileSystem sống đủ lâu.
5. Không “sửa” concurrency bằng kiểm tra `zip.isOpen()` ngay trước mỗi lời gọi; vẫn có race giữa check và use.

### 8.3. Khi nào không nên chia sẻ FileSystem?

Nếu chỉ đọc một file từ archive rồi trả String, đơn giản nhất là **mount ngắn, thao tác ngay, trả dữ liệu**, đóng trong cùng phương thức. Với ứng dụng đọc rất nhiều entry liên tiếp, có thể dùng mount dùng chung nhưng cần quản lý lifecycle tập trung.

Đừng chọn shared mount vì “tiết kiệm một dòng try” mà không có owner và shutdown contract.

## 9. Anti-pattern: return Path rồi close trước khi caller sử dụng

**Sai:**

```java
static Path findEntry(URI archiveUri) throws IOException {
    try (FileSystem fs = FileSystems.newFileSystem(
            archiveUri, Map.of())) {
        return fs.getPath("/docs/readme.txt");
    }
}
```

Hàm trả `Path` rồi đóng `fs` **trước khi caller nhận kết quả**. Caller nhìn thấy một Path hợp lệ về mặt kiểu Java nhưng `Files.readString(result)` không thể truy cập archive do FileSystem đã đóng.

Đây là ví dụ **anti-pattern**, không phải hàm có thể dùng để đọc file sau return.

### 9.1. Mẫu đúng: trả dữ liệu đã đọc

```java
static String readArchiveText(URI archiveUri, String entryName)
        throws IOException {
    try (FileSystem fs = FileSystems.newFileSystem(
            archiveUri, Map.of())) {
        Path entry = fs.getPath(entryName);
        return Files.readString(entry, StandardCharsets.UTF_8);
    }
}
```

Đây là **phương thức Java 17+ độc lập trong một class**, với imports URI, FileSystem, FileSystems, Files, Path, StandardCharsets, Map, IOException. Caller nhận **String đã được đọc trước close**, không phải Path còn phụ thuộc một mount đã đóng.

### 9.2. Mẫu đúng: nhận callback/consumer trong scope mở

```java
static <T> T withZip(URI uri, Function<FileSystem, T> action)
        throws IOException {
    try (FileSystem fs = FileSystems.newFileSystem(uri, Map.of())) {
        return action.apply(fs);
    }
}
```

Đây là **phương thức minh họa** có import `java.util.function.Function` và các loại NIO. Callback thực hiện **synchronously** trong scope; nó không được trả Path/Stream/channel borrowed ra ngoài nếu resource vẫn cần dùng. Nếu callback cần ném checked IOException, `Function` có hạn chế checked exception, nên trong API thực tế có thể định nghĩa một functional interface riêng với `throws IOException`.

### 9.3. Mẫu đúng: trả dữ liệu tự sở hữu

Nếu caller cần đọc muộn, cân nhắc các lựa chọn:

- Trả `byte[]` hoặc `String` sau khi đọc hoàn tất (cho dữ liệu vừa phải).
- Copy entry thành **tệp tạm của default filesystem** trước khi đóng ZIP; caller quản lý tệp tạm theo hợp đồng cleanup.
- Trả một đối tượng chứa **URI archive + tên entry**, kèm hàm `open/read` thực hiện mount trong scope mới khi cần.
- Trả một **handle object có AutoCloseable** do tầng quản lý tạo, gói FileSystem cùng một lease và kiểm soát close rõ. Cần cẩn trọng khi nhiều caller dùng chung.
- Nếu là Stream hoặc channel, bảo đảm FileSystem sống ít nhất cho tới khi Stream/channel đóng; không đóng fs trong hàm tạo stream rồi trả stream “đang hoạt động”.

Lựa chọn tùy kích thước dữ liệu, tần suất đọc, memory budget, độ an toàn và mức độ chia sẻ tài nguyên.

## 10. Một Path cũ có thể được lưu cho lần sử dụng sau không?

### 10.1. Không nên cache ZIP Path qua vòng đời mount

Sai:

```java
Map<String, Path> cachedEntries = new HashMap<>();
try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
    cachedEntries.put("readme", zip.getPath("/docs/readme.txt"));
}
// cachedEntries giữ Path thuộc zip đã đóng!
```

Đây là snippet minh họa với `URI uri`, imports Map/HashMap/FileSystem/FileSystems/Path. Cache này gây lỗi lifecycle khi truy cập sau scope.

### 10.2. Cache mô tả địa chỉ thay vì object Path

Đối với một entry bên trong archive, có thể cache dữ liệu như:

```text
archiveUri: "jar:file:///.../lessons.zip"
entryName:  "/docs/readme.txt"
```

Khi cần đọc, mở ZIP FileSystem theo chính sách owner rồi tạo `zipFs.getPath(entryName)` **trong scope mới**. Nếu dùng `FileSystems.getFileSystem(uri)` để lấy mount có sẵn, phải bảo đảm instance đó được quản lý bởi owner, không được close ở code chỉ mượn.

**Cẩn thận:** Cache đường dẫn không bảo đảm archive không thay đổi trên đĩa. Nếu nội dung phải đúng một version, cần checksum, signature, version ID hoặc mô hình snapshot riêng.

### 10.3. Đừng tự tái tạo Path ZIP bằng Path.of(String)

```java
Path wrong = Path.of("/docs/readme.txt");
```

Đây là snippet minh họa. `Path.of` dùng **default filesystem** trong bối cảnh thường gặp; nó **không** tạo một Path bên trong ZIP chỉ vì chuỗi trông giống đường dẫn ZIP. Cách đúng là:

```java
Path insideZip = zipFs.getPath("/docs/readme.txt");
```

với `zipFs` đang mở. Path mang **provider identity**, không chỉ một chuỗi text. Chuyển ZIP Path thành String rồi dùng `Path.of` có thể làm mất provider và dẫn tới đọc nhầm file local hoặc thao tác sai nơi.

## 11. FileSystems.newFileSystem(URI, env) và getFileSystem(URI)

### 11.1. newFileSystem: tạo mount mới

```java
FileSystem zipFs = FileSystems.newFileSystem(
        archiveUri, Map.of());
```

Đây là snippet với ZIP archive có sẵn và URI hợp lệ. Nó yêu cầu provider tạo một FileSystem mới, theo hợp đồng API. Trong ZIP provider của JDK, nếu cùng ZIP URI **đang được mount bởi một instance**, lời gọi duplicate thường ném `FileSystemAlreadyExistsException`.

### 11.2. getFileSystem: lấy reference đã tồn tại

```java
FileSystem existing = FileSystems.getFileSystem(archiveUri);
```

Đây là snippet trong phương thức. Nó **không tạo FileSystem mới**, mà yêu cầu provider tìm instance đã có. Nếu không có phù hợp, có thể ném `FileSystemNotFoundException`. Nếu provider không được cài đặt, có thể ném `ProviderNotFoundException`.

**Ai close?** Nếu caller chỉ dùng `getFileSystem`, đừng xem reference đó là ownership tự động. Đóng nó có thể làm hỏng các Path/streams của những thành phần khác cũng đang mượn cùng mount.

### 11.3. Điều gì xảy ra với lookup sau close?

Javadoc `FileSystems.getFileSystem(URI)` nêu rằng sau khi FileSystem đã đóng, việc provider trả instance đã đóng hay ném `FileSystemNotFoundException` **phụ thuộc provider**. Nếu provider hỗ trợ mở lại cùng URI, việc gọi getFileSystem sau close (trước khi có mount mới) sẽ ném exception tương ứng.

**Không áp một quy tắc cứng cho mọi provider.** Với `jdk.zipfs` hiện hành, người dùng thường thấy mount được bỏ khỏi registry sau khi close, và có thể `newFileSystem` lại URI đó; nhưng code portable phải dựa trên hợp đồng của provider và xử lý exception hợp lý.

### 11.4. Nếu nhiều request cùng muốn mount archive?

Hai request có thể cùng gọi `newFileSystem(archiveUri, env)`:

- Một request tạo mount thành công.
- Request khác có thể gặp `FileSystemAlreadyExistsException`.
- Nếu request thứ hai gọi `getFileSystem` để mượn, nó không được tự đóng instance do request đầu quản lý.
- Nếu request đầu đóng trước khi request thứ hai xử lý, request thứ hai có thể gặp `ClosedFileSystemException`.

Do vậy một server có nhiều request thường cần **mount manager hoặc lock/lease**, không chỉ chuỗi “try new, catch already exists, get, finally close” không có ownership.

## 12. Overload Path so với URI: cùng nhiệm vụ nhưng không giống registry

Java SE 17 cung cấp nhiều factory methods:

```java
FileSystems.newFileSystem(URI uri, Map<String, ?> env);
FileSystems.newFileSystem(Path path, Map<String, ?> env);
FileSystems.newFileSystem(Path path);
```

Đây là **chữ ký mô tả API**, không phải những phương thức cần khai báo trong code. Chúng có cách chọn provider/cơ chế quản lý instance khác nhau.

### 12.1. URI-based FileSystem

`newFileSystem(URI, env)` tìm provider theo URI scheme, như `jar` cho ZIP provider. Với ZIP/JAR, đây là cách rõ ràng để ánh xạ URI sang mount mà `getFileSystem(URI)` có thể tra cứu trong provider registry.

### 12.2. Path-based FileSystem

`newFileSystem(Path, env)` yêu cầu tìm một provider có thể diễn giải **một file hiện có** (ví dụ ZIP) như một FileSystem. Factory này phù hợp với thao tác mở archive theo đường dẫn, nhưng **không nên giả định `getFileSystem(URI)` trả lại instance tạo qua Path-overload**.

Javadoc `FileSystemProvider.getFileSystem(URI)` quy định tra cứu những FileSystem được tạo bằng URI factory theo scheme/URI; FileSystem tạo bằng Path factory **không phải loại được provider trả về từ lookup đó**.

### 12.3. Không trộn hai factory để “lách” duplicate mount

Nếu ứng dụng dùng Path factory ở một component và URI factory ở component khác, chúng có thể hoạt động theo cơ chế ownership/registry khác. Không dùng việc có thể mở qua một overload như bằng chứng hai instance cùng sửa archive an toàn đồng thời. Nhiều writer trên cùng ZIP file có thể tạo tình huống ghi đè, race hoặc dữ liệu bị mất.

**Nguyên tắc:** chọn **một cơ chế mở + một owner** cho mỗi archive theo phạm vi ứng dụng, rồi tài liệu hóa lifecycle.

## 13. Đóng FileSystem và các resource con: thứ tự đóng đúng

Một ZIP FileSystem có thể cung cấp:

- `InputStream`/`OutputStream` qua `Files.newInputStream/newOutputStream`.
- `SeekableByteChannel` qua `Files.newByteChannel`.
- `DirectoryStream<Path>` qua `Files.newDirectoryStream`.
- `Stream<Path>` qua `Files.list/walk/find`.
- Các resource provider-specific khác.

**Mẫu đúng là đóng resource bên trong trước**, rồi mới đóng FileSystem ở bên ngoài.

```java
try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
    Path entry = zip.getPath("/docs/readme.txt");
    try (InputStream input = Files.newInputStream(entry)) {
        byte[] firstBytes = input.readNBytes(128);
        // Xử lý firstBytes tại đây.
    }
}
```

Đây là snippet **trong phương thức** với imports `java.io.InputStream`, `FileSystem`, `FileSystems`, `Files`, `Path`, `Map`; cần xử lý IOException. Try-with-resources đóng `input` trước khi close `zip`.

### 13.1. Với Files.walk, phải đóng Stream<Path>

```java
try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
    Path root = zip.getPath("/");
    try (Stream<Path> paths = Files.walk(root)) {
        long count = paths.count();
        System.out.println(count);
    }
}
```

Đây là snippet với import `java.util.stream.Stream` và xử lý IOException/UncheckedIOException khi cần. `Files.walk` có thể giữ directory resource mở, vì vậy cần đóng Stream bằng TWR **trước** khi ZIP FileSystem đóng.

### 13.2. Sai: return Stream<Path> trong khi đóng FS

```java
static Stream<Path> broken(URI uri) throws IOException {
    try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
        return Files.walk(zip.getPath("/"));
    }
}
```

Đây là **anti-pattern**. Method trả Stream gắn ZIP Path, nhưng filesystem đã đóng trước khi caller gọi terminal operation. Kết quả có thể gây `ClosedFileSystemException` hoặc lỗi stream đã đóng; không thiết kế API kiểu này nếu không trả cùng resource owner và lifetime.

### 13.3. Đóng FS có tự đóng resource con thì có cần đóng riêng không?

**Có.** Dù FileSystem.close theo đặc tả đóng các resource liên quan, bạn vẫn nên:

- Close channels/streams ngay khi xong thao tác.
- Dùng try-with-resources cho từng loại có AutoCloseable.
- Không giữ open stream giữa các request ngoài scope.
- Có chính sách xử lý exception khi close.
- Chỉ close FileSystem sau khi resource con và worker hoàn tất.

Điều này làm ownership và thứ tự hoạt động rõ ràng, giảm rủi ro flush/cleanup muộn hoặc phụ thuộc cách provider xử lý đóng đồng thời.

## 14. FileSystem.close() và tính hoàn tất của ZIP archive

ZIP provider của JDK cho phép chỉnh sửa entry như một filesystem. Khi FileSystem đóng, provider cần hoàn thành công việc đóng và các thay đổi ở archive theo triển khai. Đó là lý do thực hành tốt là **đóng xong rồi mới xem archive như một ZIP đã được xuất bản**.

### 14.1. Không coi close là commit transaction chung

Dù ZIP provider thường ghi ra archive ở giai đoạn đóng, `FileSystem.close` **không phải API commit transaction được chuẩn hóa** cho mọi FileSystem. Đừng suy:

- Một ZIP write + close có tính nguyên tử giữa mọi entry.
- Mất điện ngay sau close luôn cho archive hợp lệ/durable ở mọi tầng lưu trữ.
- Close của ZIP luôn có thể rollback mọi thay đổi nếu một entry ghi lỗi.
- Người đọc khác sẽ thấy “nửa ZIP trước/nửa ZIP sau” theo một mô hình nhất quán duy nhất.
- `FileSystem.close` cung cấp fsync cho file ZIP và parent directory trên mọi OS.

Khi cần phát hành archive nhạy cảm về toàn vẹn, hãy tạo ở một **file tạm trong thư mục/volume phù hợp**, đóng và kiểm tra/archive checksum, sau đó publish bằng `Files.move(..., ATOMIC_MOVE)` **nếu provider hỗ trợ**, với fallback được thiết kế rõ và chính sách durability riêng.

### 14.2. Tránh xóa/ghi đè archive khi mount còn mở

Nếu một process đang mount archive và process khác thay thế ZIP file trên disk, kết quả có thể khác tùy OS/provider (lỗi handle, file bị thay, dữ liệu cũ/mới). Không xây hệ thống “vừa mount read-write vừa thay thế archive từ ngoài” mà không có lock/ownership.

**Thực hành hợp lý:** finish mọi entry I/O, close ZIP FS, kiểm tra thành phẩm, rồi cho bước publish/backup/đọc từ đối tượng archive mới.

### 14.3. close có thể thất bại

```java
try (FileSystem zip = FileSystems.newFileSystem(uri, env)) {
    // Ghi các entry bên trong ZIP.
}
```

Try-with-resources có thể ném IOException **khi close** dù thân khối không báo lỗi. Caller cần bắt/truyền lỗi này. Nếu nghiệp vụ cần ghi nhận thành công, chỉ đánh dấu thành công khi **toàn bộ scope (bao gồm close) đã hoàn tất** và các bước kiểm tra tính toàn vẹn cần thiết đều pass.

## 15. Exceptions cần nhận diện đúng

| Tình huống | Exception thường gặp | Cách xử lý đúng |
| --- | --- | --- |
| I/O vào Path thuộc FileSystem đã đóng | `ClosedFileSystemException` | Kiểm tra lifetime/owner, mở lại và tạo Path mới |
| Đóng default FileSystem | `UnsupportedOperationException` | Không gọi close; default là shared resource |
| Mount cùng URI khi instance đã có | `FileSystemAlreadyExistsException` | Dùng owner/lease; không đóng instance của bên khác |
| Tra cứu URI chưa có mount | `FileSystemNotFoundException` | Tạo/mount theo chính sách hoặc thông báo không có |
| Scheme/provider không cài đặt (ví dụ thiếu jdk.zipfs) | `ProviderNotFoundException` | Kiểm tra runtime modules/providers, có fallback rõ |
| ZIP archive không tồn tại và `create` không bật | `NoSuchFileException`/`IOException` | Xác minh Path và chủ đích create/open |
| ZIP archive tồn tại nhưng không hợp lệ | `IOException`, ví dụ lỗi định dạng ZIP | Không đổi thành “file không tồn tại” |
| Mở ZIP chỉ đọc rồi cố ghi | `ReadOnlyFileSystemException` hoặc I/O tương ứng | Tôn trọng read-only provider/file store |
| Close khi chưa flush/xong hoặc storage lỗi | `IOException` | Không đánh dấu công việc thành công |
| Thao tác provider khác/không hỗ trợ | `UnsupportedOperationException` / `IOException` | Kiểm tra capability đúng provider |
| Dùng `Files.walk` rồi không close Stream | Có thể giữ tài nguyên tới khi FS close | Dùng TWR cho Stream riêng |
| Thread khác đóng FS lúc đang đọc | `ClosedFileSystemException`, I/O hoặc blocking tùy provider | Quản lý ownership và synchronization |
| Delete archive đang mount | `AccessDeniedException` hoặc I/O khác trên một số OS | Close resource trước khi cleanup |

Một số ngoại lệ kể trên là **unchecked**, số khác là `IOException`. Không bắt mọi `Exception` rồi trả `null` hoặc `false`: sẽ làm biến mất thông tin rằng lỗi thật nằm ở ownership/lifetime.

### 15.1. IOException trong close và suppressed exceptions

Try-with-resources xử lý đúng trường hợp cả thân khối và close đều phát sinh exception. Nếu thân khối đã ném lỗi chính, lỗi khi đóng thường nằm trong `Throwable.getSuppressed()`. Khi chẩn đoán lỗi ZIP corruption hoặc storage failure, đừng chỉ log exception chính và bỏ suppressed errors.

### 15.2. close() lần hai có phải “safe” để retry thao tác không?

Hợp đồng nói gọi close lần nữa trên FileSystem **đã đóng** không có hiệu ứng. Nhưng điều này **không** cho phép:

- Tái sử dụng Path cũ sau close lần hai.
- Coi việc close lỗi giữa chừng là đã commit thành công.
- Gọi close nhiều lần thay cho kiểm soát ownership.
- Giữ FileSystem dùng chung mà yêu cầu mỗi component tự close khi rảnh.

TWR là mặc định tốt để close đúng một lần tại scope owner.

## 16. Concurrency: close và open streams ở nhiều thread

FileSystem được thiết kế **thread-safe cho các thao tác chung**, nhưng Javadoc không chuẩn hóa chi tiết đóng bất đồng bộ. Khi một thread gọi `close()` trong khi thread khác đang dùng Path của FileSystem đó, provider có thể block chờ hoặc gây những lỗi I/O/lifecycle phù hợp.

```text
Thread A (owner)                     Thread B (consumer)
    open ZIP FS
    share Path ----------------------> Files.newInputStream(entry)
    ...                                đọc dữ liệu
    close ZIP FS  -------------------> resource có thể bị đóng/đọc thất bại
```

Không giải quyết bằng:

```java
if (zipFs.isOpen()) {
    Files.readString(entry); // Có thể bị close ngay sau isOpen().
}
```

Đây là snippet minh họa **race**. Cần bảo đảm **lifetime** qua synchronization, ref-count/leases hoặc kiến trúc chỉ một owner. Nếu xử lý bất đồng bộ, định nghĩa deadline shutdown và cách hủy tác vụ đang chạy.

### 16.1. Một cách chia ownership hợp lý

Trong server có nhiều request, thay vì tạo và đóng ZIP mount ở mọi handler ngẫu nhiên:

- Một `ArchiveSession` hoặc `ArchiveManager` chịu trách nhiệm mount và close.
- Consumer nhận session lease hoặc callback được thực thi trong phạm vi lease.
- Session chỉ close khi không còn consumer active, theo một cơ chế đồng bộ.
- Lỗi mount/close được report, không bị ẩn bởi API `getFileSystem`.
- Nếu mỗi request độc lập và archive nhỏ, có thể **mount/close riêng** với lock/coordination phù hợp, tránh shared mutable ZIP và duplicate URI collisions.

Đây là thiết kế gợi ý ở tầng ứng dụng; Java NIO.2 **không tự cung cấp ref-count manager chung cho mọi provider**.

### 16.2. Không giữ Path trong task chạy sau khi scope đóng

```java
try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
    Path entry = zip.getPath("/docs/readme.txt");
    executor.submit(() -> Files.readString(entry));
} // ZIP có thể đóng trước khi task được scheduler chạy.
```

Đây là **anti-pattern minh họa**, với `ExecutorService executor`, `URI uri` và các imports/exception handling phù hợp. Nó chứa race: task có thể thực thi sau TWR và gặp ClosedFileSystemException. Cách xử lý là **chờ Future hoàn tất trước close**, hoặc giữ session lease còn hiệu lực trong suốt task.

## 17. Cross-provider Paths và copy giữa default FS và ZIP FS

Một Path từ ZIP và một Path từ default FileSystem có thể được dùng với `Files.copy`:

```java
Path localFile = Path.of("data", "source.txt");
try (FileSystem zip = FileSystems.newFileSystem(uri, Map.of())) {
    Path zipEntry = zip.getPath("/assets/source.txt");
    Files.createDirectories(zipEntry.getParent());
    Files.copy(localFile, zipEntry);
}
```

Đây là snippet trong phương thức, `localFile` và ZIP archive tồn tại, `uri` hợp lệ; cần imports FileSystem/FileSystems/Files/Path/Map và xử lý IOException. Việc copy giữa providers được hỗ trợ theo các hợp đồng của Files, nhưng khả năng preserve attributes/atomicity tùy provider.

**Quan trọng:** Nếu muốn sử dụng `zipEntry` sau khi đã đóng zip, code phải **mở lại ZIP và lấy Path mới**. Ngược lại, `localFile` vẫn thuộc default FS, không bị ảnh hưởng bởi việc ZIP FileSystem đóng.

### 17.1. Đừng so sánh Path chỉ bằng chuỗi

`zipEntry.toString()` có thể trả `"/assets/source.txt"`, còn `Path.of("/assets/source.txt")` là file local trên Linux/Unix hoặc cú pháp tương ứng trên Windows. Hai Path trông giống nhau nhưng thuộc **hai providers khác nhau**.

Không dùng một map key chỉ là `path.toString()` để định danh resource đa FileSystem nếu có thể có tên trùng. Dùng key gồm **archive URI + entry path**, phiên bản/checksum nếu cần.

### 17.2. Khi extraction cần security review

Nếu chương trình đọc tên entry từ ZIP không tin cậy rồi copy ra default filesystem, phải kiểm tra:

- Entry có đường dẫn tuyệt đối hay chứa các đoạn `..` không?
- Đích sau resolve/normalize có nằm trong root cho phép không?
- Các directory cha của đích có thể là symbolic link không?
- Có race từ tiến trình khác thay entry sau kiểm tra không?
- Có giới hạn tổng bytes, số file, độ sâu và tỷ lệ nén để tránh zip bomb không?
- Có kiểm tra quyền/overwrite policy và không ghi vào đường dẫn nhạy cảm?

Đừng tin rằng `Path.normalize()` hoặc một lần `startsWith(root)` giải quyết mọi rủi ro symlink/traversal. Lưu ý provider `jdk.zipfs` hiện hành **không hỗ trợ mở ZIP sẵn có có những entry chứa thành phần tên `.` hoặc `..`**, nhưng điều đó không thay thế việc validate các bước export/copy của ứng dụng và các provider khác.

## 18. ZIP FileSystem không phải ZipFile/ZipInputStream

NIO có nhiều API để làm việc với ZIP:

| API | Mô hình sử dụng | Vòng đời |
| --- | --- | --- |
| `FileSystems.newFileSystem(jarUri, env)` | Mount ZIP/JAR thành cây `Path` và dùng `Files` | **Đóng FileSystem** |
| `ZipFile` | Mở ZIP và truy cập entries theo API `java.util.zip` | **Đóng ZipFile** |
| `ZipInputStream` | Đọc tuần tự các entry trên một InputStream | **Đóng Stream** |
| `ZipOutputStream` | Ghi ZIP entries tuần tự ra OutputStream | **Finish/close Stream** |

Bài này tập trung vào **FileSystem và Path**, vì đó là nguồn `ClosedFileSystemException` nếu ownership sai. Không áp nguyên xi mô hình `ZipFile.getEntry`/`ZipInputStream.getNextEntry` cho ZIP Path từ `jdk.zipfs`.

### 18.1. Khi nào dùng ZIP FileSystem?

Phù hợp khi:

- Cần thao tác entry bằng các API `Files` và `Path` đồng nhất.
- Cần tạo/sửa nhiều entry trong một archive theo scope được kiểm soát.
- Code hiện tại đã dùng các utilities NIO cho việc tạo directory, copy file, đọc metadata.

Khi chỉ cần stream đọc/ghi ZIP tuần tự, `ZipInputStream`/`ZipOutputStream` có thể đơn giản hơn. **Dù chọn API nào, resource owner vẫn phải close đúng cách** và kiểm tra lỗi đóng/flush theo nhu cầu dữ liệu.

## 19. Mất tính hợp lệ khác với mất dữ liệu

Một số tình huống cần phân biệt:

### 19.1. Path cũ không sử dụng được nhưng archive vẫn còn

Sau `zip.close()`:

```java
boolean closed = !zip.isOpen();
boolean archiveStillExists = Files.isRegularFile(archivePath);
```

Đây là snippet với `zip` đã đóng và `Path archivePath` thuộc default filesystem. Nếu close và ghi archive thành công, `archiveStillExists` có thể true. Điều đó không có nghĩa `oldEntry` còn dùng được: file ZIP trên disk và FileSystem mount là **hai lớp khác nhau**.

### 19.2. Path vẫn là object nhưng không có dữ liệu cached

Object Path không giữ bản sao nội dung file. Đừng hy vọng `oldEntry.toString()` hay `oldEntry.getFileName()` có thể phục hồi nội dung. Cần mở lại filesystem, xác minh archive và đọc lại bằng một **Path thuộc instance mới**.

### 19.3. Archive có thể thay đổi sau khi đóng

Nếu một process khác thay thế file ZIP giữa hai lượt mount, một entry có cùng tên có thể chứa dữ liệu khác. Nếu bạn cần đọc đúng version, nên gắn checksum/hash, version identifier, hoặc dùng snapshot immutable. **Mở lại cùng URI không mặc định mang nghĩa mở lại cùng phiên bản dữ liệu**.

### 19.4. Không phải tất cả providers đều cho reopen

Đặc tả `FileSystems.newFileSystem(URI,...)` nói khả năng tạo lại FileSystem cùng URI sau khi instance cũ đóng là **provider-dependent**. `jdk.zipfs` hiện hành cho phép theo ví dụ, nhưng không áp dụng như cam kết phổ quát cho custom/remote/virtual provider.

## 20. Các lỗi thường gặp và cách sửa

**Lỗi 1 — Return ZIP Path từ try-with-resources.** Path cũ bị gắn với closed filesystem. Trả dữ liệu hoặc đối tượng session có ownership.

**Lỗi 2 — Cache `Path` qua nhiều lượt mount.** Không. Cache archive URI + entry name, rồi lấy Path mới khi mount lại.

**Lỗi 3 — Gọi `FileSystems.getDefault().close()`.** Default filesystem không thể đóng; không làm vậy.

**Lỗi 4 — Đóng FileSystem được mượn từ `getFileSystem(uri)`.** Có thể làm hỏng những consumer khác. Xác lập owner.

**Lỗi 5 — Coi `isOpen()` đủ chống concurrent close.** Có TOCTOU race; cần giữ lease/lifecycle đồng bộ.

**Lỗi 6 — Coi `Files.exists(stale) == false` là file trong ZIP bị xóa.** Có thể không xác định được trạng thái. Phân biệt closed filesystem với missing entry.

**Lỗi 7 — Tạo Path ZIP bằng `Path.of("/docs/readme.txt")`.** Đây là Path default provider, không phải ZIP. Dùng `zipFs.getPath(...)`.

**Lỗi 8 — Dùng `newFileSystem(uri)` trùng khi mount đã mở rồi xử lý bằng cách close người khác.** Có thể gây duplicate mount error hoặc đóng nhầm ownership.

**Lỗi 9 — Mở lại ZIP và tiếp tục dùng old Path.** Mở lại tạo FileSystem mới; phải lấy fresh Path.

**Lỗi 10 — Quên close ZIP FileSystem.** Có thể giữ handles và làm quá trình hoàn tất archive không đúng lúc.

**Lỗi 11 — Nghĩ rời thân try là chắc archive đã commit thành công.** Close có thể ném IOException. Thành công phải bao gồm kết quả close.

**Lỗi 12 — Dùng `Files.walk` nhưng không đóng Stream.** Cần try-with-resources cho resource con.

**Lỗi 13 — Đóng ZIP trong khi worker khác còn đọc.** Rủi ro I/O exception/blocking tùy provider; đồng bộ lifetime.

**Lỗi 14 — Trả Stream<Path> từ hàm đã đóng ZIP FS.** Stream có thể được tiêu thụ sau đó; phải giữ mount sống hoặc collect data.

**Lỗi 15 — Tạo file ZIP rỗng có sẵn rồi dùng `create=true` và nghĩ đó là ZIP hợp lệ.** Để ZIP provider tạo một archive **chưa tồn tại**.

**Lỗi 16 — Suy `newFileSystem(Path)` có thể lấy lại qua `getFileSystem(URI)` như URI-based mount.** Hai factory không có cùng hợp đồng registry.

**Lỗi 17 — Chỉ test default filesystem mà bỏ kiểm tra module `jdk.zipfs`.** Runtime tùy biến có thể thiếu module này.

**Lỗi 18 — Coi `FileSystem.close` là durability transaction cho mọi provider.** Không có hợp đồng chung như vậy.

**Lỗi 19 — Dùng chỉ path text làm khóa cache giữa ZIP/local providers.** Có thể đụng tên và đọc sai filesystem.

**Lỗi 20 — Bắt mọi IOException/RuntimeException rồi trả “không có file”.** Che lỗi close/lifetime, xung đột mount và permission.

**Lỗi 21 — Dùng relative entry path mà không xác định root ZIP.** `zip.getPath("docs/readme.txt")` có cú pháp tương đối; `zip.getPath("/docs/readme.txt")` rõ ràng hơn khi bạn cần vị trí tuyệt đối trong archive.

**Lỗi 22 — Xóa file archive khi mount còn mở.** Có thể gặp permission/locking issues; đóng trước khi cleanup.

**Lỗi 23 — Không tính đến việc archive thay đổi giữa hai lượt mở.** URI giống nhau không chứng minh content/version giống nhau.

**Lỗi 24 — Lấy Filesystem do provider khác cấp rồi áp assumption của ZIP.** ZIP-specific properties/URI semantics không nhất thiết đúng cho custom provider.

## 21. Checklist code review cho FileSystem và ZIP lifecycle

- [ ] Đã xác định FileSystem nào thuộc **default** và FileSystem nào do ứng dụng **tạo/mount**?
- [ ] Có phân biệt **người tạo resource (owner)** với **người dùng mượn (borrower)**?
- [ ] Mọi `FileSystems.newFileSystem(...)` có scope đóng rõ ràng, ưu tiên `try-with-resources`?
- [ ] Có tránh gọi `close()` trên `FileSystems.getDefault()`?
- [ ] Có tránh close một FileSystem lấy từ `FileSystems.getFileSystem(uri)` nếu không sở hữu?
- [ ] Mọi `Path` ZIP được tạo bằng `zipFs.getPath(...)` thuộc đúng instance?
- [ ] Không trả ZIP Path/Stream/channel từ hàm đã đóng ZIP FileSystem?
- [ ] Không giữ ZIP Path cũ trong cache/queue sau khi mount đóng?
- [ ] Nếu mở lại ZIP, code lấy **fresh Path** từ instance mới?
- [ ] Có phân biệt `ClosedFileSystemException` với `NoSuchFileException`?
- [ ] Có xử lý `FileSystemAlreadyExistsException` khi URI đang mount?
- [ ] Có xử lý `FileSystemNotFoundException` khi lookup không có mount?
- [ ] Có kiểm tra runtime có module/provider `jdk.zipfs` khi cần?
- [ ] Khi dùng `create=true`, archive Path có chưa tồn tại đúng mục đích?
- [ ] Khi ZIP đã tồn tại, không vô tình overwrite bằng policy tạo archive mới?
- [ ] Có close `InputStream/OutputStream/Channel/DirectoryStream/Files.walk Stream` trước khi close ZIP?
- [ ] Có xử lý IOException khi `close()`, kể cả suppressed exceptions?
- [ ] Có chỉ ghi nhận thành công sau khi close đã hoàn tất không lỗi?
- [ ] Có thể có **thread khác close** trong lúc đang dùng Path không, và đã đồng bộ lifecycle?
- [ ] Nếu nhiều request dùng cùng archive, có owner/lease hoặc mount manager?
- [ ] Nếu access giữa ZIP và local filesystem, code giữ đúng provider identity?
- [ ] Khi copy/xuất ZIP, có chính sách metadata/atomicity/durability và kiểm tra kết quả?
- [ ] Nếu archive nhận từ người dùng, có giới hạn size, path traversal và zip bomb không?
- [ ] Khi FileSystem đóng, có đảm bảo resources ngoài scope (workers/tasks) không còn sử dụng?
- [ ] Test có kiểm tra `isOpen()`, stale Path I/O, reopen và fresh Path?
- [ ] Có test ZIP provider/runtime thực tế trên Windows/Linux/môi trường deploy?
- [ ] Có dọn các file tạm **sau khi** đóng các mount và stream liên quan?
- [ ] Nếu dữ liệu phải đúng version, có checksum/version thay vì giả định URI không thay đổi?

## 22. Câu hỏi tự kiểm tra

**1.** `FileSystem` là gì? — Là đối tượng do provider quản lý, tạo `Path` và cung cấp quyền truy cập một filesystem, có vòng đời mở/đóng.

**2.** `Path` thuộc một `FileSystem` xác định không? — **Có**, truy cập qua `path.getFileSystem()`.

**3.** ZIP FileSystem có phải API mới thay thế NIO.2 không? — **Không**, `jdk.zipfs` là provider hiện hành triển khai FileSystem để truy cập ZIP/JAR bằng NIO.2.

**4.** `FileSystems.newFileSystem(jarUri, env)` trả gì? — Một FileSystem mới cho provider tương ứng, nếu URI, cấu hình và capability hợp lệ.

**5.** `"create"="true"` trong ZIP provider nghĩa là gì? — Tạo ZIP/JAR nếu file archive chưa tồn tại, theo property của `jdk.zipfs`.

**6.** Vì sao không tạo một file ZIP rỗng trước rồi trông `create=true` sửa lại? — File đã tồn tại nhưng không phải ZIP hợp lệ có thể không được mount.

**7.** `FileSystem.close()` có thể ném checked exception không? — **Có**, `IOException`.

**8.** `FileSystem.close()` đóng các channels/streams liên quan không? — **Có** theo hợp đồng; vẫn nên đóng resource con đúng scope.

**9.** Đóng ZIP có xóa file `lessons.zip` trên default filesystem không? — **Không** theo thao tác đóng mount.

**10.** Sau ZIP close, biến `Path oldEntry` có tự trở thành null? — **Không**, nhưng I/O qua nó không còn hợp lệ.

**11.** Đọc stale ZIP Path thường gặp lỗi gì? — `ClosedFileSystemException`.

**12.** Mở lại ZIP có làm old Path hoạt động lại không? — **Không**, phải tạo Path mới trong FileSystem mới.

**13.** `FileSystems.getDefault()` có được close không? — **Không**, default FileSystem luôn mở và close không được hỗ trợ.

**14.** `getFileSystem(uri)` tạo mount mới hay lấy mount đã có? — **Lấy tham chiếu hiện có**, không tự tạo mới.

**15.** Tại sao không tự close instance lấy từ getFileSystem? — Có thể đó là resource dùng chung của component khác.

**16.** Tạo FileSystem trùng URI khi đã mount có thể gây lỗi gì? — `FileSystemAlreadyExistsException`.

**17.** Gọi getFileSystem khi chưa có mount có thể gặp gì? — `FileSystemNotFoundException`.

**18.** Cơ chế `getFileSystem(uri)` sau close có thống nhất mọi provider không? — **Không**, phụ thuộc provider.

**19.** `Path.of("/docs/readme.txt")` có phải Path bên trong ZIP không? — **Không**, thường là Path default filesystem.

**20.** Sau khi `Files.walk(zipPath)`, cần đóng gì trước? — Đóng `Stream<Path>` rồi ZIP FileSystem theo nested TWR.

**21.** Đóng ZIP ở Thread A khi Thread B đang đọc có bảo đảm luôn không chặn và không lỗi? — **Không**, hành vi async close là provider-dependent.

**22.** Check `zip.isOpen()` rồi đọc có tránh race nếu thread khác close không? — **Không**, cần đồng bộ lifetime.

**23.** Vì sao return Path từ TWR ZIP là anti-pattern? — Caller nhận object Path thuộc FileSystem đã bị đóng.

**24.** Một cách API tốt hơn return ZIP Path là gì? — Trả String/byte[], copy ra file độc lập, hoặc trả session handle có owner/lifetime rõ.

**25.** `FileSystems.newFileSystem(Path, Map)` có đương nhiên được tìm qua getFileSystem(URI)? — **Không**, registry của Path factory khác URI factory.

**26.** Vì sao chỉ `Files.exists(zipPath) == false` không chứng minh entry mất? — Không xác định được trạng thái có thể trả false, kể cả lifecycle/provider lỗi.

**27.** ZIP file vẫn còn nhưng ZIP Path cũ không dùng được có mâu thuẫn không? — **Không**: archive file và mount FileSystem là hai lớp khác nhau.

**28.** Close của ZIP có đủ là crash-safe transaction cho mọi trường hợp không? — **Không**, cần thiết kế integrity/durability riêng.

**29.** Khi nhiều request cùng truy cập archive, ai đóng? — **Owner/manager đã được chỉ định**, sau khi tất cả borrowers không còn sử dụng.

**30.** Vì sao không được bỏ IOException của close? — Archive có thể không được hoàn tất đúng; ghi thành công cần bao gồm cả kết quả close.

## Tài liệu chính thức hiện hành

- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): vòng đời, `close()`, `isOpen()`, default FileSystem không đóng được, close của resources và concurrency.
- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): `getDefault()`, `newFileSystem(URI/Path)`, `getFileSystem(URI)`, duplicate/lookup/reopen.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `getFileSystem()`, `toUri()`, `getPath()`, provider identity và các thao tác đường dẫn.
- [Java SE 17 — ClosedFileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): lỗi khi truy cập filesystem đã đóng.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString/writeString`, `copy`, `walk`, `newDirectoryStream`, `isRegularFile`.
- [Java SE 17 — ZIP FileSystem provider (jdk.zipfs)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): URI scheme `jar`, property `create`, mở/tạo ZIP và giới hạn của provider.
- [Java SE 17 — FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): factory, URI-based registry/Path-based construction và provider-specific semantics.
- [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `AutoCloseable` và stream cần đóng khi backed by IO resources.

**Ghi nhớ:** `FileSystem` có **vòng đời riêng**, còn `Path` luôn gắn với **FileSystem đã tạo ra nó**. Đối với một ZIP/custom FileSystem do ứng dụng mount, hãy dùng `try-with-resources`, đóng các stream/channel con trước, và **không sử dụng Path cũ sau close**. Mở lại ZIP tạo một FileSystem mới và cần lấy **Path mới**. Default FileSystem thì **không thể đóng**, còn FileSystem dùng chung phải có **owner/lease** rõ ràng. Nếu thao tác dữ liệu cần độ tin cậy cao, phải xử lý lỗi `close()` và tự thiết kế integrity/durability thay vì coi close là transaction tuyệt đối.