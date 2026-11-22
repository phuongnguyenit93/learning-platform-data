# Tạo hệ thống tệp bằng `FileSystems.newFileSystem` trong Java

## 1. Bài toán: xem tệp ZIP như một hệ thống tệp

Một tệp `.zip` hoặc `.jar` thực chất là một *container*: bên trong có nhiều entry, có thể là thư mục hoặc tệp. Khi muốn đọc/ghi một entry, ta có thể sử dụng `ZipInputStream` hoặc `ZipFile`. Tuy nhiên, Java NIO.2 còn cho phép **gắn nội dung ZIP thành một `FileSystem`**, rồi thao tác với entry trong ZIP bằng các API quen thuộc như `Path` và `Files`.

Cách chính thức là:

~~~java
try (FileSystem zipfs = FileSystems.newFileSystem(
        archive, Map.of("create", "true"))) {
    Path entry = zipfs.getPath("/docs/hello.txt");
    Files.createDirectories(entry.getParent());
    Files.writeString(entry, "Hello ZIP", StandardCharsets.UTF_8);
}
~~~

Đây là **đoạn minh họa**: cần `Path archive` trỏ đến tên ZIP hợp lệ, import các lớp liên quan và xử lý `IOException`. Khi `archive` chưa tồn tại, tùy chọn ZIP provider `"create"="true"` yêu cầu tạo archive. Khi block kết thúc, `FileSystem` được **đóng**, cho phép nhà cung cấp ZIP hoàn tất công việc ghi. Đây **không** phải cách khởi tạo `FileSystems.getDefault()` hay tạo ổ đĩa vật lý mới.

**Đề bài:** “Tạo hệ thống tệp bằng `FileSystems.newFileSystem`”, thuộc nhóm “FileSystem và ZIP”.

Bài này giúp:

1. Phân biệt một `FileSystem` có sẵn với một `FileSystem` mới được mở từ ZIP/JAR.
2. Biết các overload `FileSystems.newFileSystem(...)` hiện được hỗ trợ, chọn `Path` hay `URI` phù hợp.
3. Sử dụng `jdk.zipfs`, sơ đồ `jar:`, thuộc tính môi trường `create` và các tùy chọn ZIP provider.
4. Tạo ZIP mới, ghi file vào ZIP, đóng, mở lại, đọc và copy entry sang filesystem mặc định.
5. Hiểu `Path` nào thuộc provider nào, vấn đề khác provider và vòng đời `FileSystem.close()`.
6. Xử lý các lỗi provider, đường dẫn, file ZIP không hợp lệ, tài nguyên đã đóng, ghi đè, encoding và tương tranh.
7. Không dùng ZIP FS như sandbox; nhận biết ZIP Slip, ZIP bomb, dữ liệu không đáng tin và giới hạn cập nhật archive.
8. Kiểm thử trên Java 21 bằng chương trình thực sự có thể biên dịch và chạy.

**Lưu ý phiên bản theo Special Note:** nền tảng NIO.2 và overload `FileSystems.newFileSystem(URI, Map)` có từ **Java 7**. Overload rất tiện `FileSystems.newFileSystem(Path, Map)` được bổ sung sau, có trong **Java 13 trở lên** và được dùng trong ví dụ **Java 21**. `jdk.zipfs` là module provider chính thức trong các JDK hiện đại; runtime image tùy chỉnh cần chứa module/provider này. Bài tập trung kiến thức **hiện vẫn áp dụng**, không khuyến nghị cách làm legacy.

## 2. `FileSystem`, `Path` và `FileSystemProvider` là những đối tượng khác nhau

Java NIO.2 phân tách ba khái niệm:

| Thành phần | Kiểu Java | Vai trò |
| --- | --- | --- |
| `FileSystem` | `java.nio.file.FileSystem` | Không gian tên đường dẫn, các file stores và tài nguyên để truy cập hệ thống tệp |
| `Path` | `java.nio.file.Path` | Đường dẫn **bên trong một FileSystem cụ thể** |
| `FileSystemProvider` | `java.nio.file.spi.FileSystemProvider` | Cài đặt các thao tác truy cập file system theo scheme/provider |
| `FileSystems` | `java.nio.file.FileSystems` | Các factory/getter để lấy default FS hoặc tạo thêm FS |
| `Files` | `java.nio.file.Files` | Các thao tác đọc, ghi, copy, move, list, tạo thư mục… trên `Path` |

Với ZIP:

~~~text
Hệ thống tệp mặc định (scheme "file")
└── /home/user/data/example.zip        Path trỏ tới FILE archive trên ổ đĩa
        |
        | FileSystems.newFileSystem(archive, env)
        v
Hệ thống tệp ZIP (provider scheme "jar")
└── /                            Path gốc ở BÊN TRONG ZIP
    └── docs/
        └── hello.txt            Một ZIP entry, không phải file độc lập trên ổ đĩa
~~~

Đây là **sơ đồ khái niệm**; đường dẫn thật trên Windows/Linux khác nhau. `example.zip` là file thuộc filesystem mặc định, còn `/docs/hello.txt` được lấy từ `zipfs.getPath(...)` và thuộc filesystem ZIP.

**Điểm quan trọng:** hai đối tượng `Path` có thể hiển thị chuỗi giống nhau nhưng thuộc **hai provider khác nhau**. `Path.of("/docs/hello.txt")` tạo path ở filesystem mặc định; **không** tự hiểu rằng phải đọc `docs/hello.txt` trong archive đang mở. Muốn truy cập entry ZIP, gọi `zipfs.getPath("/docs/hello.txt")`.

### 2.1. Tạo một FS không giống tạo một thư mục

`Files.createDirectory(path)` tạo một directory trong một filesystem **đang có**. Ngược lại, `FileSystems.newFileSystem(...)` yêu cầu một provider tạo **một đối tượng FileSystem mới** để truy cập một nguồn lưu trữ, ở đây là ZIP/JAR. Sau khi mở ZIP FS, các thao tác `Files.createDirectory`/`Files.writeString` bên trong hoạt động trên các entry ZIP.

Không phải mỗi lần gọi `newFileSystem` là tạo một file ZIP mới: nếu mở **archive đã tồn tại** mà không yêu cầu tạo, hàm tạo một **FileSystem instance để truy cập archive đó**, không tạo archive thứ hai. Từ “new” chỉ nói về instance FileSystem được tạo.

## 3. Các overload `FileSystems.newFileSystem` liên quan

Trên Java SE 21 có các dạng:

~~~java
FileSystems.newFileSystem(uri, env);
FileSystems.newFileSystem(uri, env, loader);

FileSystems.newFileSystem(archive);
FileSystems.newFileSystem(archive, loader);
FileSystems.newFileSystem(archive, env);
FileSystems.newFileSystem(archive, env, loader);
~~~

Đây là **danh sách chữ ký rút gọn**, các biến `uri`, `env`, `archive`, `loader` chưa được khai báo. `uri` là `URI`; `env` là `Map<String, ?>`; `archive` là `Path`; `loader` là `ClassLoader` (có thể null theo các overload phù hợp). Mỗi phương thức trả `FileSystem` hoặc ném exception theo hợp đồng.

| Dạng | Khi phù hợp | Điểm cần phân biệt |
| --- | --- | --- |
| `newFileSystem(URI, Map)` | Biết scheme của provider, ví dụ `jar:` | Provider được chọn theo URI scheme; có từ Java 7 |
| `newFileSystem(URI, Map, ClassLoader)` | Cần thêm cơ chế tìm provider bằng class loader | Thường không cần khi ZIP provider đã cài |
| `newFileSystem(Path)` | Mở một archive **đã có**, tự nhận diện loại file | Không truyền `create`; có trên JDK hiện đại |
| `newFileSystem(Path, ClassLoader)` | Mở từ file với class loader để tìm provider | Khác overload nhận Map, không nên dùng `null` mơ hồ |
| `newFileSystem(Path, Map)` | Mở/tạo archive bằng đường dẫn và tùy chọn provider | Có từ Java 13; ví dụ chính dùng Java 21 |
| `newFileSystem(Path, Map, ClassLoader)` | File-based provider với environment và loader | Khi tích hợp provider đặc thù |

**`env` không phải danh sách thuộc tính chung của mọi file system.** Các key như `"create"` là **quy ước của ZIP provider**; provider khác có thể dùng key khác hoặc không hỗ trợ.

### 3.1. `FileSystems.getDefault()` không phải `newFileSystem(...)`

~~~java
FileSystem defaultFs = FileSystems.getDefault();
~~~

Lời gọi này trả filesystem mặc định của JVM. Nó **không mở ZIP** và không cần đóng bởi code của bạn. Đường dẫn `Path.of("example.zip")` thuộc default FS, nhưng ZIP entry cần được tạo từ `zipfs.getPath(...)`.

### 3.2. `FileSystems.getFileSystem(uri)` khác `newFileSystem(uri, env)`

`getFileSystem(URI)` yêu cầu provider trả lại một **instance đã tồn tại** theo URI. Nó **không mở/tạo mới** thay cho `newFileSystem`; nếu chưa có instance tương ứng, có thể ném `FileSystemNotFoundException`.

`newFileSystem(URI, env)` yêu cầu **tạo một instance mới**; với URI provider, có thể ném `FileSystemAlreadyExistsException` nếu cùng định danh đã được mở và provider không cho phép một instance thứ hai. Việc tái mở sau `close()` và cách quản lý caching là **provider-dependent**, không nên tự suy ra một quy tắc chung cho mọi FS.

Đặc biệt không trộn lẫn `newFileSystem(Path, Map)` và `getFileSystem(URI)` để mặc định chúng chia sẻ cùng quy tắc cache. Code nên giữ **biến `FileSystem` trả về từ factory**, sử dụng trong block sở hữu tài nguyên, đóng đúng lúc và chỉ mở lại khi cần.

## 4. ZIP provider chính thức: module `jdk.zipfs`

JDK cung cấp module `jdk.zipfs`, một `FileSystemProvider` để xem nội dung ZIP/JAR như hệ thống tệp. Nó sử dụng scheme:

~~~text
jar
~~~

Một URI ZIP FS có thể có dạng:

~~~text
jar:file:/home/user/data/example.zip
~~~

Đây là ví dụ URI, **không phải đường dẫn tuyệt đối dùng chung cho mọi OS**.

Đặc điểm:

- Provider hiểu các ZIP/JAR archive và trình bày entry bằng `Path`.
- Có thể duyệt, đọc và ghi entry bằng nhiều phương thức trong `Files`.
- Có thể tạo archive khi truyền môi trường `"create"="true"`.
- Việc có module/provider trong một runtime image **không phải mặc nhiên** nếu ứng dụng chạy trên một image đã được tinh giản bằng công cụ đóng gói tùy chỉnh.
- Mô hình provider có **giới hạn**: một số thuộc tính file, operation, security hoặc ZIP đặc biệt có thể không được hỗ trợ như filesystem OS.

Trong Java SE 21, tài liệu module `jdk.zipfs` liệt kê các tính năng hiện hành; vì vậy không nên copy hướng dẫn ZIP FS cũ từ bản Java 8 rồi giả định tất cả property hoặc behavior còn giống hệt.

### 4.1. Provider nhận biết định dạng, không đơn thuần dựa vào đuôi tên

Với overload nhận `Path`, các installed providers được thử theo khả năng xử lý file. Việc một tên kết thúc `.zip` **không tự biến dữ liệu rác thành ZIP hợp lệ**. Nếu file là dữ liệu không phải ZIP, việc mở có thể thất bại vì nội dung sai định dạng, dù đuôi tên đúng.

`FileSystems.newFileSystem(archive, Map.of())` dùng cho **archive đã tồn tại và hợp lệ**. Nếu file chưa có, có thể gặp `NoSuchFileException`/`IOException` theo provider; nếu ZIP hỏng, có thể gặp `ZipException` hoặc lỗi I/O khác. Muốn tạo ZIP mới, dùng `"create"="true"` khi dùng ZIP provider.

## 5. Biến môi trường `env` và những lựa chọn ZIP phổ biến

Tạo archive mới bằng `Path`:

~~~java
Map<String, String> env = Map.of("create", "true");

try (FileSystem fs = FileSystems.newFileSystem(archive, env)) {
    Path root = fs.getPath("/");
    // Tạo directory/file entry trong ZIP ở đây.
}
~~~

Đây là code minh họa với `Path archive` trỏ đến file ZIP **chưa tồn tại**, trên filesystem bình thường và JVM có ZIP provider.

**Quan trọng:** property `"create"` **không có nghĩa “bắt buộc archive mới hoàn toàn”**. Theo ZIP provider, khi `"create"=true` và archive **chưa tồn tại** thì provider tạo archive; khi archive đã tồn tại hợp lệ, provider có thể mở nó. Nếu cần nghiệp vụ “tên file ZIP chưa tồn tại, không ai được dùng trước”, phải có cơ chế kiểm soát xung đột/ownership riêng; không coi `create=true` là bằng chứng về tính độc quyền.

Các property ZIP FS hiện được tài liệu Java SE 21 mô tả:

| Thuộc tính | Kiểu được hỗ trợ | Ý nghĩa / lưu ý |
| --- | --- | --- |
| `"create"` | `String` hoặc `Boolean` | Tạo archive nếu chưa có; mặc định false |
| `"encoding"` | `String` | Charset cho **tên các entry** trong ZIP, mặc định UTF-8; không phải charset của nội dung file |
| `"compressionMethod"` | `String` | `"DEFLATED"` mặc định, hoặc `"STORED"` để không nén entry mới |
| `"enablePosixFileAttributes"` | `String` hoặc `Boolean` | Cho phép POSIX view do provider hỗ trợ; không đồng nghĩa OS áp quyền đó |
| `"defaultOwner"` / `"defaultGroup"` | `UserPrincipal`/`GroupPrincipal` hoặc `String` | Các giá trị owner/group mặc định khi dùng POSIX view; metadata này không được lưu như owner OS thật trong ZIP |
| `"defaultPermissions"` | `Set<PosixFilePermission>` hoặc chuỗi định dạng quyền | Định nghĩa permissions mặc định nếu dùng POSIX view |
| `"releaseVersion"` | `String` hoặc `Integer` | Chọn cách nhìn multi-release JAR nếu cần; **không bắt buộc với ZIP thường** |

**Đừng lẫn hai loại encoding.** `"encoding"` của ZIP provider điều khiển **cách giải mã/ghi tên entry** trong archive. `StandardCharsets.UTF_8` truyền cho `Files.writeString`/`readString` điều khiển **bytes nội dung**. Tên entry đọc được không chứng minh nội dung file là UTF-8.

### 5.1. Tạo archive và ghi file mới

~~~java
try (FileSystem fs = FileSystems.newFileSystem(
        archive, Map.of("create", "true"))) {
    Path folder = fs.getPath("/docs");
    Files.createDirectories(folder);
    Files.writeString(folder.resolve("hello.txt"), "Hello ZIP",
            StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
}
~~~

Đây là đoạn minh họa; cần import `StandardOpenOption`. `CREATE_NEW` trong `Files.writeString` yêu cầu **entry chưa tồn tại**, để tránh vô tình ghi đè một entry đã có. Tuy nhiên `CREATE_NEW` cho entry **không có nghĩa** việc tạo archive và mọi cập nhật của archive là một transaction nguyên tử.

### 5.2. Không tạo tệp ZIP rỗng rồi mong ZipFS coi nó là archive hợp lệ

Một cách dễ sai:

~~~java
Path archive = Files.createTempFile("example-", ".zip");
try (FileSystem fs = FileSystems.newFileSystem(
        archive, Map.of("create", "true"))) {
    // Không bảo đảm mở được vì file ZIP đã tồn tại nhưng có thể chỉ rỗng.
}
~~~

Đây là **phản ví dụ**. File do `Files.createTempFile` tạo có thể là **file dài 0 byte**, chưa có cấu trúc ZIP. `"create"` chỉ giúp tạo ZIP khi archive **chưa tồn tại**, không biến mọi file rỗng/hỏng thành archive hợp lệ.

**Mẫu tốt trong bài chạy:** tạo một **thư mục tạm riêng**, sau đó `workspace.resolve("example.zip")` để chọn **đường dẫn ZIP chưa tồn tại**. Nhờ vậy bài thử không đụng tới file của người khác và ZIP provider có thể tạo archive theo contract.

## 6. Chương trình Java 21 hoàn chỉnh: hai overload, ghi/đọc/copy ZIP

Bài tập dưới đây có thể chạy với JDK 21 đầy đủ có `jdk.zipfs`:

1. Tạo một **thư mục tạm riêng**.
2. Dùng `FileSystems.newFileSystem(archive, Map.of("create","true"))`.
3. Tạo `/docs/hello.txt` **bên trong ZIP** và ghi chuỗi UTF-8.
4. Đóng ZIP FS bằng `try-with-resources`.
5. Dùng `FileSystems.newFileSystem(archive, Map.of())` để **mở lại archive** và đọc entry.
6. Sao chép file bên trong ZIP sang `extracted.txt` thuộc filesystem mặc định.
7. Tạo ZIP thứ hai bằng `FileSystems.newFileSystem(URI.create("jar:" + uriArchive.toUri()), env)` để phân biệt overload URI.
8. Đóng cả hai ZIP FS, dọn tài nguyên tạm.

Đầu ra không in đường dẫn tạm tuyệt đối nên có thể đối chiếu trên Windows/Linux thuận tiện hơn. Chương trình tạo nội dung ASCII đơn giản để output không phụ thuộc locale, nhưng thực tế `Files.writeString` hỗ trợ UTF-8 như ví dụ.

Tạo file `src/main/java/demo/ZipFileSystemsExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;

public final class ZipFileSystemsExample {
    private ZipFileSystemsExample() {}

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("zipfs-lesson-");
        Path archive = workspace.resolve("example.zip");
        Path extracted = workspace.resolve("extracted.txt");
        Path uriArchive = workspace.resolve("uri-example.zip");
        try {
            try (FileSystem zipfs = FileSystems.newFileSystem(
                    archive, Map.of("create", "true"))) {
                Path docs = zipfs.getPath("/docs");
                Files.createDirectories(docs);
                Path inside = docs.resolve("hello.txt");
                Files.writeString(inside, "Hello ZIP", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

                System.out.println("zip-scheme=" + zipfs.provider().getScheme());
                System.out.println("entry-is-zip-path="
                        + (inside.getFileSystem() == zipfs));
                System.out.println("entry-exists=" + Files.exists(inside));
                System.out.println("entry-content="
                        + Files.readString(inside, StandardCharsets.UTF_8));
            }

            System.out.println("archive-exists-after-close="
                    + Files.isRegularFile(archive));

            try (FileSystem reopened = FileSystems.newFileSystem(
                    archive, Map.of())) {
                Path inside = reopened.getPath("/docs/hello.txt");
                System.out.println("reopened-entry="
                        + Files.readString(inside, StandardCharsets.UTF_8));

                Files.copy(inside, extracted);
                System.out.println("copied-to-default="
                        + Files.readString(extracted, StandardCharsets.UTF_8));
                System.out.println("different-providers="
                        + (inside.getFileSystem().provider()
                                != extracted.getFileSystem().provider()));
            }

            URI uri = URI.create("jar:" + uriArchive.toUri());
            try (FileSystem fromUri = FileSystems.newFileSystem(
                    uri, Map.of("create", "true"))) {
                Path entry = fromUri.getPath("/entry.txt");
                Files.writeString(entry, "URI entry", StandardCharsets.UTF_8);
                System.out.println("uri-entry="
                        + Files.readString(entry, StandardCharsets.UTF_8));
            }
            System.out.println("uri-archive-exists-after-close="
                    + Files.isRegularFile(uriArchive));
        } finally {
            Files.deleteIfExists(extracted);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(uriArchive);
            Files.deleteIfExists(workspace);
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/ZipFileSystemsExample.java
java -cp out demo.ZipFileSystemsExample
~~~

**Stdout chính xác đã kiểm thử với JDK 21 và ZIP provider `jdk.zipfs`:**

~~~text
zip-scheme=jar
entry-is-zip-path=true
entry-exists=true
entry-content=Hello ZIP
archive-exists-after-close=true
reopened-entry=Hello ZIP
copied-to-default=Hello ZIP
different-providers=true
uri-entry=URI entry
uri-archive-exists-after-close=true
~~~

### 6.1. Phân tích kết quả chi tiết

**`zip-scheme=jar`:** trong môi trường thử, `FileSystem.provider().getScheme()` của ZIP FS là `"jar"`. Điều này phản ánh ZIP provider được sử dụng, không biến `example.zip` thành Java module hay tự chạy như ứng dụng.

**`entry-is-zip-path=true`:** `Path inside` được lấy từ `zipfs.getPath(...)` và thuộc đúng instance `zipfs`. Nó không phải đường dẫn mặc định của OS.

**`entry-exists=true`:** `Files.exists(inside)` xác nhận entry đã được tạo ở thời điểm kiểm tra. Không biến boolean này thành lời cam kết về các thao tác sau khi FS bị đóng.

**`entry-content=Hello ZIP`:** `Files.readString` đọc nội dung entry thông qua ZIP filesystem khi đang mở.

**`archive-exists-after-close=true`:** sau khi block đầu kết thúc và ZIP FS đóng thành công, file archive đã có trên filesystem mặc định.

**`reopened-entry=Hello ZIP`:** overload nhận `Path` và env rỗng mở lại ZIP đã tồn tại, cho phép đọc cùng entry từ archive.

**`copied-to-default=Hello ZIP`:** `Files.copy(inside, extracted)` sao chép file từ ZIP FS sang một `Path` thuộc default FS. Source và target có provider khác nhau nhưng `Files.copy` có contract hỗ trợ thao tác copy giữa các provider khi điều kiện phù hợp.

**`different-providers=true`:** provider của ZIP entry khác provider của `extracted.txt`. Vì thế phải lấy đúng path cho từng phía.

**`uri-entry=URI entry`:** `FileSystems.newFileSystem(uri, Map.of("create","true"))` mở ZIP FS khác bằng scheme `jar` và ghi một entry.

**`uri-archive-exists-after-close=true`:** ZIP thứ hai được ghi/đóng và tồn tại thành archive trên disk trong môi trường kiểm thử.

### 6.2. Chương trình có ghi đè file người dùng không?

Không. Nó tạo một directory tạm mới với tiền tố `zipfs-lesson-`, đặt các file ZIP và `extracted.txt` **bên trong directory riêng**. Bài sử dụng `CREATE_NEW` cho entry đầu tiên, và `Files.copy` vào một target chưa có.

Khi hoàn thành, chương trình đóng ZIP FS **trước** khi xóa file ZIP vật lý và cuối cùng xóa workspace. Nó không ghi trực tiếp các file của repository hay thư mục ZIP hiện hữu ngoài phạm vi.

### 6.3. Còn trường hợp thất bại thì sao?

`try/finally` bảo đảm nỗ lực cleanup với các thao tác thuộc workspace. Nhưng I/O luôn có thể thất bại, kể cả khi close hoặc delete; nếu cleanup ném `IOException`, exception cần được xử lý/log theo chính sách của ứng dụng thực tế. Ví dụ này không tuyên bố cleanup không bao giờ lỗi trên mọi OS.

## 7. Mở ZIP bằng `URI` có scheme `jar:`

Trong trường hợp muốn chỉ định URI cho ZIP provider, dùng:

~~~java
URI uri = URI.create("jar:" + archive.toUri());

try (FileSystem zipfs = FileSystems.newFileSystem(
        uri, Map.of("create", "true"))) {
    Path entry = zipfs.getPath("/report.txt");
    Files.writeString(entry, "report", StandardCharsets.UTF_8);
}
~~~

Đây là **đoạn minh họa** với `Path archive` trỏ đến đường dẫn muốn tạo, cần import `URI`, `Map`, `FileSystems`, `FileSystem`, `Files`, `Path` và `StandardCharsets`. Lời gọi `archive.toUri()` tạo một URI chuẩn cho file path trên nền tảng hiện tại, bao gồm việc escape ký tự đặc biệt. Nối tiền tố `"jar:"` tạo scheme mà ZIP provider hiểu.

**Không tự viết** các chuỗi như `"jar:file:/C:/Program Files/..."` rồi bỏ qua encoding khoảng trắng. Dùng `Path.toUri()` khi tạo URI từ path có thật hoặc dự định có.

### 7.1. ZIP URI không phải HTTP URL của một dịch vụ bên ngoài

Ví dụ `jar:file:/...` tham chiếu một archive file theo provider có trên JVM. `FileSystems.newFileSystem` không tự tải ZIP từ Internet. Muốn làm việc với file tải về, hãy xử lý/download vào storage theo chính sách rồi đưa vào provider thích hợp. Không trông chờ `newFileSystem(URI.create("https://..."), env)` được ZIP provider chấp nhận.

### 7.2. Khi nào dùng `Path`, khi nào dùng `URI`?

**Chọn `Path + Map`** cho ứng dụng Java 13+ khi đã có local file path và muốn code gọn:

~~~java
FileSystems.newFileSystem(archive, Map.of("create", "true"));
~~~

**Chọn `URI + Map`** khi làm việc rõ ràng theo provider URI scheme, hoặc cần mã tương thích với các API NIO.2 đã có từ Java 7:

~~~java
FileSystems.newFileSystem(
        URI.create("jar:" + archive.toUri()), Map.of("create", "true"));
~~~

Đây chỉ là **mẫu lời gọi**, không phải lời khuyên bỏ qua thời gian sống của FS. Luôn quản lý `FileSystem.close()` và xử lý ngoại lệ.

## 8. Vòng đời `FileSystem`: close, isOpen và dữ liệu ZIP

Các instance `FileSystem` mới được tạo bởi `newFileSystem` thường **sở hữu tài nguyên** như archive handle, internal caches và trạng thái cập nhật. Với ZIP FS, nhà cung cấp có thể thực hiện bước xử lý lại archive khi đóng.

Mẫu quản lý đúng:

~~~java
try (FileSystem zipfs = FileSystems.newFileSystem(zip, Map.of())) {
    Path entry = zipfs.getPath("/hello.txt");
    String content = Files.readString(entry, StandardCharsets.UTF_8);
    System.out.println(content);
}
~~~

Đây là đoạn minh họa cần archive `zip` đã tồn tại hợp lệ, và entry có thật.

**Không giữ `Path` ZIP rồi dùng vô điều kiện sau close:**

~~~java
Path inside;
try (FileSystem fs = FileSystems.newFileSystem(zip, Map.of())) {
    inside = fs.getPath("/hello.txt");
}
// FS của inside đã đóng:
Files.readString(inside); // Có thể ném ClosedFileSystemException.
~~~

Đây là **phản ví dụ**. `Path` có thể tồn tại trong RAM nhưng provider phía sau đã đóng, nên I/O với path đó không còn hợp lệ. Nếu cần tiếp tục, mở một `FileSystem` mới và tạo lại `Path` **từ instance mới**.

`FileSystem.isOpen()` có thể phản ánh FS còn mở hay không, nhưng đừng dùng một lần kiểm tra boolean để thay cho xử lý lỗi I/O khi dùng trong môi trường đa luồng hoặc có người đóng FS đồng thời.

### 8.1. Không đóng `FileSystems.getDefault()`

`FileSystems.getDefault()` là file system mặc định dùng chung của JVM. Ứng dụng không sở hữu vòng đời của nó theo cách sở hữu một ZIP FS mới tạo. **Không gọi `close()` trên default FS** với mục đích dọn tài nguyên; dùng try-with-resources cho những FS chuyên dụng do ứng dụng mở.

### 8.2. Đóng thất bại và tính bền dữ liệu

Việc viết nhiều entry vào ZIP, đóng FS và xuất hiện file ZIP sau close là một **workflow**, không có nghĩa toàn bộ quá trình sửa archive là một transaction crash-safe.

- Khi close/ghi thất bại, archive có thể không ở trạng thái mong muốn; xử lý `IOException` và có kế hoạch recovery.
- Không giả định metadata/bytes đã bền trước mất điện chỉ vì lệnh ghi trả thành công.
- Nếu cập nhật một ZIP quan trọng đang được người khác sử dụng, nên tạo archive mới trong vùng riêng, xác minh, rồi triển khai replace/move theo yêu cầu nghiệp vụ.
- `StandardCopyOption.ATOMIC_MOVE` là khả năng của filesystem đích khi được hỗ trợ; không làm cho toàn bộ quá trình tạo/ghi ZIP thành transaction tuyệt đối.

### 8.3. Nhiều người cùng cập nhật ZIP

Hai tiến trình hoặc luồng cùng chỉnh cùng archive có thể tạo race và mất cập nhật, dù mỗi người sử dụng instance `FileSystem` riêng. Đừng tự giả định ZIP provider cung cấp lock xuyên process hoặc merge thay đổi tự động.

Một dịch vụ cập nhật ZIP nên có quy trình **serialize writes**, ownership riêng, kiểm tra version/source và chính sách khi xung đột. Trong trường hợp chỉ cần đọc, có thể cân nhắc quyền read-only của storage, nhưng vẫn phải xét lifecycle và I/O.

## 9. `Path` bên trong ZIP: các thao tác quen thuộc, provider khác

Khi ZIP FS đã mở:

~~~java
Path root = zipfs.getPath("/");
Path docs = zipfs.getPath("/docs");
Path entry = docs.resolve("hello.txt");

Files.createDirectories(docs);
Files.writeString(entry, "Hello ZIP", StandardCharsets.UTF_8);
boolean exists = Files.exists(entry);
~~~

Đây là code minh họa với `FileSystem zipfs` đang mở; code cần xử lý `IOException` và chú ý default `writeString` có thể **tạo hoặc truncate entry**, vì vậy chỉ dùng khi nghiệp vụ cho phép.

Có thể dùng các API chung của `Files`:

| Nhu cầu | Ví dụ | Ghi chú |
| --- | --- | --- |
| Tạo directory | `Files.createDirectories(zipfs.getPath("/docs"))` | Các directory/entry thuộc ZIP FS |
| Tạo file | `Files.writeString(entry, contents, UTF_8)` | Có thể tạo/truncate; chọn options rõ |
| Đọc file | `Files.readString(entry, UTF_8)` | Nội dung phải dùng charset tương ứng |
| Liệt kê | `Files.list(directory)` | Trả stream cần đóng |
| Duyệt cây | `Files.walk(root)` | Trả stream có I/O resources |
| Kiểm tra tồn tại | `Files.exists(entry)` | Chỉ là quan sát tại thời điểm gọi |
| Sao chép ZIP → disk | `Files.copy(zipEntry, diskPath)` | Source/target khác provider |
| Sao chép disk → ZIP | `Files.copy(diskPath, zipEntry)` | Tùy quyền và target |
| Xóa một entry | `Files.delete(entry)` | Không phải “xóa ZIP archive vật lý” |
| Xóa chính archive | `Files.delete(archivePath)` | Chỉ sau khi đã đóng ZIP FS phù hợp |

### 9.1. Liệt kê có try-with-resources

~~~java
try (Stream<Path> entries = Files.walk(zipfs.getPath("/"))) {
    List<String> paths = entries.map(Path::toString)
            .sorted()
            .toList();
    System.out.println(paths);
}
~~~

Đây là đoạn minh họa với `zipfs` còn mở, và import `Stream`/`List`. `Files.walk` có thể giữ directory resources; **đóng stream** ngay cả khi chỉ dùng một lần hoặc terminal operation thất bại.

### 9.2. Không dùng `Path.of` cho ZIP entries

`Path.of("/docs/hello.txt")` lấy từ default filesystem. Không nên so sánh path từ ZIP FS và path OS bằng `equals` hoặc dùng `resolve(Path)` giữa hai provider rồi mong kết quả hợp lệ. Nhiều thao tác kết hợp path có thể ném `ProviderMismatchException`; ngay cả khi không ném, chuỗi path không phải ánh xạ trực tiếp qua các filesystem.

Muốn copy qua providers, dùng **`Files.copy(source, target)`** với mỗi path thuộc FS của nó, như chương trình hoàn chỉnh đã thử.

### 9.3. ZIP root và tính tương đối

`zipfs.getPath("/")` là ZIP root. `zipfs.getPath("/docs/hello.txt")` là path tuyệt đối trong ZIP FS. `zipfs.getPath("docs/hello.txt")` là path tương đối **trong ZIP FS**, không phải một file của default FS.

Nếu áp dụng `normalize()` cho path, hãy nhớ nó chỉ xử lý **cú pháp đường dẫn**, không tự xác minh entry được phép truy cập, không khóa archive và không loại bỏ path traversal khi dữ liệu không đáng tin.

## 10. Các exception và trường hợp cần kiểm soát

| Tình huống | Exception / hành vi có thể gặp | Xử lý |
| --- | --- | --- |
| Không có ZIP provider trong runtime | `ProviderNotFoundException` | Kiểm tra runtime/modules, provider installation |
| URI định danh FS đã mở | `FileSystemAlreadyExistsException` | Giữ instance đã mở theo lifecycle hoặc thiết kế mở/đóng hợp lý |
| Truy vấn FS không tồn tại | `FileSystemNotFoundException` từ `getFileSystem(URI)` | Không nhầm getter với factory |
| Archive không tồn tại và không bật create | `IOException` / `NoSuchFileException` | Dùng create khi thực sự muốn tạo mới |
| File hiện có không phải ZIP hợp lệ | `ZipException` hoặc `IOException` | Không tin chỉ vào đuôi `.zip` |
| Không có quyền ghi archive | `AccessDeniedException` hoặc `IOException` | Thông báo quyền thực tế, không tự nâng đặc quyền |
| Dùng ZIP Path sau close | `ClosedFileSystemException` | Chỉ sử dụng trong lifecycle của FS đang mở |
| Provider khác nhau khi kết hợp Path | `ProviderMismatchException` | Lấy path từ đúng FS; dùng `Files.copy` để chuyển file |
| Tùy chọn env không hợp lệ | `IllegalArgumentException` | Dùng thuộc tính tài liệu ZIP provider hỗ trợ |
| Đường dẫn entry không tồn tại | `NoSuchFileException` | Kiểm tra cấu trúc và xử lý ngoại lệ |
| Entry đã tồn tại với `CREATE_NEW` | `FileAlreadyExistsException` | Không overwrite, đổi tên hoặc báo xung đột |
| Close/ghi archive thất bại | `IOException` | Không coi dữ liệu đã bền; có recovery/cleanup |
| ZIP input không đáng tin | Có thể lỗi giải nén, thiếu bộ nhớ, quá tải I/O | Đặt giới hạn entry count/size và validation |

**Bắt lỗi theo nghiệp vụ.** Một chương trình nhận `ZipException` không nên giả vờ archive “trống”; archive có thể đã hỏng hoặc dùng định dạng/metadata không được provider chấp nhận. Không được tự tạo ZIP mới đè file hiện có khi đầu vào không đọc được.

### 10.1. Có cần xử lý checked exception không?

`FileSystems.newFileSystem(...)` và các `Files` operations thường khai báo `IOException`. Dùng `throws IOException` trong ví dụ học giúp đơn giản; trong ứng dụng, nên bắt lỗi tại biên thao tác file để báo chính xác file nào, operation nào và liệu có retry/recovery được không.

Không nên bắt `Exception` rồi im lặng tiếp tục, vì sau một lần mở thất bại có thể **không có FileSystem hợp lệ** để lấy entry.

### 10.2. Runtime tối giản / modular application

Khi đóng gói image dùng `jlink` hoặc triển khai runtime tối giản, module `jdk.zipfs` có thể không nằm trong image. Khi đó overload ZIP có thể không tìm được provider dù chương trình đã compile đúng với Java 21.

Đối với ứng dụng muốn hỗ trợ ZIP FS, cần **xác minh runtime có module `jdk.zipfs` và dịch vụ provider được nhận diện**, thay vì cho rằng tất cả bản đóng gói Java đều giống full JDK. Không dùng `--add-opens` hay reflection để tự ép truy cập implementation nội bộ khi API công khai đã đủ.

## 11. An toàn khi xử lý ZIP không đáng tin

Một ZIP tải từ người dùng có thể chứa rất nhiều entry, tên bất thường, dữ liệu nén cực mạnh, hoặc metadata mà chương trình chưa biết cách xử lý.

### 11.1. ZIP Slip / path traversal

Nếu một công cụ trích xuất tự viết:

~~~java
Path output = outputRoot.resolve(entryName).normalize();
~~~

Đây là **một bước cú pháp** trong xử lý tên entry, **chưa đủ** để xây extractor an toàn khi attacker có thể tác động symlink/directory hoặc dữ liệu có path bất thường. Cần kiểm tra path ở trong root cho phép bằng `Path.startsWith(Path)`, kiểm soát các thành phần đường dẫn và chính sách symbolic link, tạo directory/ghi file qua cơ chế tránh race phù hợp và không đè tệp nhạy cảm.

Đặc biệt, tài liệu `jdk.zipfs` Java SE 21 nói rằng provider **không hỗ trợ mở ZIP hiện có chứa những entry có các thành phần tên `"."` hoặc `".."`**. Tuy vậy, đừng coi việc provider từ chối một lớp ZIP như vậy là **giải pháp bảo mật tổng quát** cho mọi rủi ro extract/copy. Code trích xuất phải vẫn có ranh giới và quyền truy cập rõ ràng.

### 11.2. ZIP bomb và giới hạn tài nguyên

Một archive nhỏ có thể giải nén ra lượng dữ liệu rất lớn, hoặc chứa hàng triệu entry. Nếu tự động quét/đọc/copy mọi entry:

- Giới hạn số entry và tổng bytes giải nén.
- Giới hạn kích thước từng entry, độ sâu đường dẫn, tổng CPU/thời gian xử lý và bộ nhớ.
- Không tự load toàn bộ entry vào `String` nếu có thể rất lớn; dùng streaming I/O có hạn mức.
- Xác minh nguồn tin, checksum/signature khi workflow đòi hỏi.
- Từ chối/giới hạn archive có metadata không hợp lệ hoặc quá tải trước khi đưa vào pipeline production.

`FileSystems.newFileSystem(...)` **không tự cấp chính sách anti-ZIP-bomb** cho nghiệp vụ.

### 11.3. ZIP không phải sandbox quyền truy cập

Một entry `/docs/hello.txt` thuộc ZIP FS có path riêng, nhưng bản thân ZIP file vẫn nằm trên filesystem vật lý. Không xem root `"/"` bên trong ZIP là một boundary security cho process; việc mount ZIP qua API không tự cách ly quyền đọc/ghi của ứng dụng với các file khác trên OS.

NIO.2 tạo **cấu trúc truy cập thuận tiện**, không phải “container bảo mật” hoặc virtual machine. Quyền filesystem, validation và policy của ứng dụng vẫn là nền tảng.

## 12. Chọn giữa `FileSystems.newFileSystem` và `ZipFile`

Các API Java khác nhau giải quyết những mục tiêu khác nhau:

| Nhu cầu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ đọc danh sách entry trong ZIP | `ZipFile` hoặc ZIP FS | `ZipFile` trực tiếp, ZIP FS thống nhất với `Files/Path` |
| Đọc ZIP một chiều từ stream | `ZipInputStream` | Phù hợp khi xử lý dòng tuần tự, không cần mounted FS |
| Tạo/sửa nhiều file/thư mục trong ZIP | `FileSystems.newFileSystem` với ZIP provider | Các thao tác quen thuộc `Files` trên ZIP entries |
| Muốn dùng `Files.walk`, `Files.copy` trong ZIP | ZIP FS | Ít phải viết lớp ánh xạ tên entry thủ công |
| Muốn cấu hình riêng provider | `newFileSystem(URI/Path, env)` | Môi trường theo provider |
| Cần đóng gói artifact chính xác ở mức byte/metadata | Cân nhắc `ZipOutputStream` hoặc công cụ build chuyên dụng | ZIP FS không đảm bảo thứ tự entry, metadata, nén và reproducibility theo mọi yêu cầu |
| Cần truy cập URL của JAR resource | `ClassLoader.getResource` hoặc API tài nguyên | Không tự yêu cầu mount ZIP nếu chỉ tìm classpath resource |

`ZipFile` và `ZipInputStream` **không phải API lỗi thời**; chúng vẫn rất hữu ích. Không cần áp dụng ZIP FS cho mọi trường hợp, nhưng ZIP FS là lựa chọn tốt khi vấn đề chính là **các thao tác `Path`/`Files` bên trong một archive**.

## 13. Kiểm thử đúng cho chức năng tạo ZIP filesystem

Để tránh những bài test dựa vào môi trường hoặc thư mục người dùng:

1. Tạo một directory tạm mới bằng `Files.createTempDirectory(...)`.
2. Chọn tên `example.zip` trong directory này **chưa tồn tại**.
3. Mở bằng `FileSystems.newFileSystem(zip, Map.of("create","true"))`.
4. Tạo các entry trong ZIP, đọc lại ngay khi FS mở.
5. Đóng FS qua try-with-resources; xác nhận ZIP file tồn tại trên default FS.
6. Mở lại bằng `FileSystems.newFileSystem(zip, Map.of())` và đọc entry.
7. Copy một entry ra path mới trên default FS và đối chiếu bytes hoặc chuỗi.
8. Thử overload `URI` bằng một tên ZIP **khác**.
9. Dọn tất cả tệp tạm sau khi đóng resources.
10. Test các ngoại lệ riêng trong test case phù hợp, ví dụ archive corrupt, entry đã tồn tại, provider thiếu, path sau close.

**Không kiểm thử bằng một archive production rồi ghi đè.** ZIP FS có thể sửa archive lúc đóng, nên test trên file người dùng là nguy hiểm.

### 13.1. Thử lỗi tạo lại entry đã có

Nếu muốn kiểm tra `CREATE_NEW`, có thể tạo một entry, rồi thử ghi cùng tên với `CREATE_NEW` trong một test riêng và mong `FileAlreadyExistsException`. Đừng thay đổi code runnable chính để phụ thuộc ngoại lệ như một phần normal flow.

### 13.2. Thử ZIP không hợp lệ

Có thể tạo một file text có đuôi `.zip` trong thư mục tạm và thử mở; phải **mong chờ mở thất bại**, không được dùng `"create"=true` để im lặng ghi đè nó. Việc lỗi cụ thể là `ZipException` hoặc một subtype `IOException` khác phụ thuộc provider.

### 13.3. Cross-platform output

Trong ví dụ chính, ta in scheme và các giá trị logic thay vì in đường dẫn absolute của workspace; điều này giúp stdout ổn định. Kết quả đã được kiểm thử với JDK 21 đầy đủ, nhưng trên runtime thiếu `jdk.zipfs`, bước tạo FS có thể thất bại hợp lệ. Một tutorial tốt phải phân biệt **đầu ra đã kiểm chứng ở môi trường thử** với **bảo đảm của API đối với mọi provider**.

## 14. Bài tập có đáp án

**Bài 1.** `Path.of("example.zip")` và `zipfs.getPath("/docs/a.txt")` cùng chỉ đến kiểu đối tượng nào?

**Đáp án:** Đều là `Path` nhưng thuộc **hai filesystem khác nhau**. Path đầu là ZIP file trên default FS; path sau là entry bên trong ZIP FS.

**Bài 2.** `FileSystems.newFileSystem(zip, Map.of("create","true"))` tạo archive trong điều kiện nào?

**Đáp án:** Với ZIP provider, khi archive **chưa tồn tại**. Nếu đã có một ZIP hợp lệ, create=true không mang nghĩa độc quyền tạo mới; phải xét xung đột riêng.

**Bài 3.** Vì sao không nên dùng `Files.createTempFile("x", ".zip")` rồi mặc nhiên mở ZIP FS với create=true?

**Đáp án:** File rỗng vừa tạo đã **tồn tại** nhưng chưa phải ZIP archive hợp lệ. `create=true` không hứa tự sửa file rỗng/corrupt.

**Bài 4.** `FileSystems.newFileSystem(URI, Map)` có từ Java 7, còn `FileSystems.newFileSystem(Path, Map)` thì sao?

**Đáp án:** Overload nhận `Path + Map` được bổ sung sau (Java 13), có trong Java 21. Đây là khác biệt phiên bản quan trọng trong module Java 7 học trên JDK hiện đại.

**Bài 5.** `"encoding"` trong ZIP env có quyết định charset của `Files.readString` không?

**Đáp án:** Không. Nó liên quan **tên entry**; nội dung văn bản cần chỉ định charset khi đọc/ghi nếu muốn rõ ràng.

**Bài 6.** `FileSystems.getDefault()` có nên được đóng khi kết thúc một helper đọc ZIP không?

**Đáp án:** Không. Chỉ ZIP `FileSystem` được mở riêng cần quản lý/đóng theo vòng đời của ứng dụng.

**Bài 7.** Có thể tiếp tục `Files.readString(inside)` sau khi đóng ZIP FS mà `inside` tạo ra không?

**Đáp án:** Không nên. Filesystem của path đã đóng; I/O có thể ném `ClosedFileSystemException`. Mở lại và tạo path mới.

**Bài 8.** Làm sao copy `/a.txt` bên trong ZIP ra file `a.txt` trên default filesystem?

**Đáp án:** Tạo `Path source = zipfs.getPath("/a.txt")`, `Path destination = outputDir.resolve("a.txt")`, rồi dùng `Files.copy(source, destination)` khi FS còn mở, xử lý quyền/trùng tên.

**Bài 9.** `FileSystems.getFileSystem(uri)` có tạo ZIP mới khi archive chưa mở không?

**Đáp án:** Không. Nó tìm một FileSystem đã tồn tại theo URI; `newFileSystem` là factory tạo instance mới.

**Bài 10.** `FileSystemAlreadyExistsException` và `FileSystemNotFoundException` thể hiện khác nhau gì?

**Đáp án:** Exception đầu có thể xảy ra khi **tạo instance đã có** theo URI/provider; exception sau khi **lấy instance chưa có** bằng getter.

**Bài 11.** Gắn một ZIP thành FileSystem có biến nó thành sandbox không?

**Đáp án:** Không. ZIP filesystem là một provider biểu diễn nội dung archive như đường dẫn, không thay thế phân quyền OS hoặc kiểm soát tên entry không đáng tin.

**Bài 12.** Khi trích xuất hàng triệu entry từ ZIP nén cực mạnh, `FileSystems.newFileSystem` có tự giới hạn tổng bytes giải nén không?

**Đáp án:** Không có bảo đảm nghiệp vụ như vậy. Ứng dụng cần giới hạn tài nguyên, đường dẫn và xử lý lỗi để phòng ZIP bomb.

**Bài 13.** Vì sao phải đóng ZIP FS trước khi xóa archive vật lý trong cleanup?

**Đáp án:** FileSystem có thể giữ handle và cần hoàn tất ghi khi đóng. Xóa archive trong lúc đang mở có thể thất bại hoặc làm khó bảo đảm dữ liệu, đặc biệt trên Windows.

**Bài 14.** Có thể dùng `Path.of("/docs/hello.txt")` thay `zipfs.getPath("/docs/hello.txt")` không?

**Đáp án:** Không nếu muốn entry ZIP. `Path.of` lấy filesystem mặc định, có thể tìm một file khác hoàn toàn hoặc không tìm thấy.

**Bài 15.** Một tệp `report.zip` bị hỏng, chương trình có nên bắt `IOException` rồi tạo lại archive rỗng cùng tên không?

**Đáp án:** Không tự động. Có thể làm mất dữ liệu. Báo lỗi và chọn policy backup/recovery rõ ràng.

## 15. Checklist code review

- [ ] Xác định rõ ZIP archive **file path** ở default FS và **entry path** ở ZIP FS.
- [ ] Chọn đúng overload `FileSystems.newFileSystem` cho JDK/nhu cầu.
- [ ] Dùng env `"create"="true"` chỉ khi muốn ZIP provider tạo archive chưa có.
- [ ] Không coi create=true là thao tác “độc quyền tên archive” hoặc transaction.
- [ ] Lấy `Path` entry bằng `zipfs.getPath(...)`, không bằng `Path.of(...)`.
- [ ] Dùng try-with-resources cho `FileSystem` do ứng dụng mở.
- [ ] Không I/O qua path thuộc ZIP FS sau khi đã đóng nó.
- [ ] Khi list/walk entries, đóng `Stream<Path>` đúng cách.
- [ ] Với file text, tách charset tên entry `"encoding"` khỏi charset của nội dung.
- [ ] Dùng `CREATE_NEW` nếu không muốn ghi đè entry hiện có.
- [ ] Kiểm tra provider/module `jdk.zipfs` khi chạy trên runtime tùy chỉnh.
- [ ] Xử lý `ProviderNotFoundException`, `IOException`, `FileSystemAlreadyExistsException` và các lỗi khác theo ngữ nghĩa.
- [ ] Với archive quan trọng, lên kế hoạch ghi/stage/recovery và quản lý concurrent writers.
- [ ] Giới hạn số lượng entry/bytes giải nén và kiểm tra path khi đọc ZIP không đáng tin.
- [ ] Không coi ZIP FS là sandbox; giữ nguyên chính sách quyền và bảo mật của hệ điều hành.
- [ ] Kiểm thử trên archive tạm riêng, xác nhận mở lại và nội dung sau close.
- [ ] Chỉ áp dụng kiến thức ZIP/NIO.2 còn được hỗ trợ trên Java hiện đại, không dựa vào API legacy.

## 16. Tài liệu chính thức (Java SE 21)

- [FileSystems](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): factory `newFileSystem`, `getDefault`, `getFileSystem`, overload `URI` và `Path`.
- [FileSystem](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html): provider, `getPath`, `close`, `isOpen`, `isReadOnly`.
- [Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): sự gắn kết path với filesystem và đường dẫn tương đối/tuyệt đối.
- [Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): đọc/ghi/copy/list/walk và resource rules.
- [Module `jdk.zipfs`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.zipfs/module-summary.html): ZIP provider, `jar` scheme, `create`, `encoding`, `compressionMethod`, POSIX attribute options và giới hạn ZIP entries.
- [FileSystemProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): mô hình provider và cách tạo FS.
- [ProviderNotFoundException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ProviderNotFoundException.html): provider không có.
- [FileSystemAlreadyExistsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemAlreadyExistsException.html): xung đột instance.
- [ClosedFileSystemException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): sử dụng hệ thống tệp đã đóng.

**Kết luận:** `FileSystems.newFileSystem` không chỉ dùng để “tạo file ZIP” mà mở một **không gian `FileSystem` mới qua provider**. Với `jdk.zipfs`, chương trình có thể dùng `Path` và `Files` để đọc/ghi nội dung archive, đóng để hoàn tất công việc rồi mở lại. Đúng API mới chỉ là bước đầu: phải chọn overload theo phiên bản, hiểu thuộc tính provider, phân biệt ZIP path với OS path, quản lý close và xử lý an toàn khi ZIP không đáng tin.
