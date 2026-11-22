# FileSystem, FileSystems và FileSystemProvider trong Java NIO.2

## 1. Vì sao Java có ba thành phần này?

Khi viết chương trình I/O, ta thường thao tác với `Path` và `Files`: mở tệp, tạo thư mục, sao chép hoặc đọc thuộc tính. Tuy nhiên, **không phải mọi đường dẫn đều thuộc hệ thống tệp mặc định của hệ điều hành**. Java NIO.2 (gói `java.nio.file` và `java.nio.file.spi`) cho phép truy cập nhiều hệ thống tệp khác nhau thông qua kiến trúc *provider*.

Ví dụ, cùng một ứng dụng Java có thể sử dụng:

- Hệ thống tệp mặc định của máy: ổ đĩa Windows, phân vùng Linux, macOS…
- Một hệ thống tệp biểu diễn nội dung tệp ZIP/JAR khi có ZIP filesystem provider.
- Một filesystem chỉ đọc cung cấp hình ảnh các module của Java Runtime (JRT).
- Một hệ thống tệp ảo do thư viện hoặc ứng dụng cài đặt thêm, nếu có provider tương ứng.

Ba tên rất dễ nhầm có vai trò khác nhau:

| Thành phần | Kiểu và gói | Trách nhiệm chính |
| --- | --- | --- |
| `FileSystems` | Lớp tiện ích `java.nio.file.FileSystems` | Cung cấp filesystem mặc định; tìm filesystem đã mở; khởi tạo/mount một filesystem qua provider thích hợp. |
| `FileSystem` | Lớp trừu tượng `java.nio.file.FileSystem` | Đại diện **một instance hệ thống tệp**; tạo `Path` thuộc nó, cung cấp root, separator, file store, metadata hỗ trợ và quản lý vòng đời. |
| `FileSystemProvider` | Lớp trừu tượng SPI `java.nio.file.spi.FileSystemProvider` | Bộ triển khai thao tác I/O và quản lý filesystem theo một URI scheme, như `file` hoặc `jar`. |

Mối quan hệ tổng quát:

~~~text
FileSystems (điểm truy cập / factory)
       |
       +-- getDefault(), getFileSystem(), newFileSystem()
                           |
                           v
                  FileSystem (instance)
                    |        |
                    |        +--> provider(): FileSystemProvider
                    |
                    +--> getPath(...) --> Path --> Files.readString/copy/delete/...
                                            |
                                            +--> provider thực hiện I/O tương ứng
~~~

`Files` là lớp API thao tác trên `Path`. Khi cần truy cập dữ liệu, Java sẽ làm việc với provider của hệ thống tệp sở hữu đường dẫn đó. Nhờ vậy, phần lớn mã dùng `Files` không cần biết đường dẫn nằm trên ổ đĩa hay trong một ZIP filesystem.

## 2. `FileSystems`: lấy, tìm và mở một filesystem

### 2.1. Hệ thống tệp mặc định: `getDefault()`

~~~java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

FileSystem fs = FileSystems.getDefault();
Path path = fs.getPath("data", "report.txt");
System.out.println(path.getFileSystem() == fs);
~~~

Đây là **đoạn mã minh họa** có các import cần thiết; để chạy độc lập hãy đặt vào phương thức `main` của một lớp Java.

- `FileSystems.getDefault()` trả về đối tượng filesystem mặc định mà ứng dụng dùng để làm việc với hệ thống tệp của máy. Các lệnh thông thường như `Path.of("data.txt")` tạo đường dẫn thuộc filesystem mặc định.
- `fs.getPath("data", "report.txt")` tạo `Path` dựa trên cú pháp của `fs`; cách biểu diễn dấu phân cách phụ thuộc provider/nền tảng.
- `path.getFileSystem()` trả về filesystem sở hữu `Path` đó. Kết quả so sánh trong ví dụ là `true`.

Không chủ động đóng `FileSystems.getDefault()`; filesystem mặc định do Java runtime quản lý và không thể bị đóng như một filesystem tự tạo.

### 2.2. Mở một filesystem qua provider: `newFileSystem(...)`

~~~java
FileSystem fs = FileSystems.newFileSystem(uri, options);
~~~

Đối với overload nhận `URI` và `Map<String, ?>`, Java tìm provider phù hợp với **scheme** trong `uri`, rồi yêu cầu provider tạo filesystem. `options` là các tùy chọn phụ thuộc từng provider: Java không bảo đảm mọi provider hiểu chung một tập khóa.

Một số overload thường gặp:

| API | Ý nghĩa |
| --- | --- |
| `FileSystems.newFileSystem(URI, Map<String, ?>)` | Tạo filesystem với URI và các tùy chọn môi trường. |
| `FileSystems.newFileSystem(Path)` | Tìm provider hỗ trợ dùng đường dẫn tới một tệp làm nền cho filesystem; ví dụ ZIP/JAR trên JDK có ZIP provider, tùy runtime. |
| `FileSystems.newFileSystem(Path, Map<String, ?>)` | Tương tự overload `Path` nhưng có thêm tùy chọn môi trường. |
| `FileSystems.newFileSystem(URI, Map<String, ?>, ClassLoader)` | Cho phép sử dụng class loader để tìm provider tùy chọn, ngoài các provider cài sẵn; chi tiết phân giải phụ thuộc overload và cấu hình runtime. |

Cần phân biệt **khởi tạo instance mới** và **lấy instance đã tồn tại**. Gọi `newFileSystem` cho một filesystem/URI đang được provider quản lý có thể gây `FileSystemAlreadyExistsException`. Không mặc định rằng gọi lại sẽ trả về đối tượng cũ.

### 2.3. Lấy một filesystem đang mở: `getFileSystem(URI)`

~~~java
FileSystem mounted = FileSystems.getFileSystem(uri);
~~~

Phương thức này yêu cầu provider nhận diện một filesystem **đã tồn tại** theo URI. Nó không tự tạo filesystem mới. Nếu provider không tìm thấy instance tương ứng, có thể ném `FileSystemNotFoundException`.

Tùy provider, URI xác định filesystem có thể khác URI xác định **một tệp bên trong** nó. Với ZIP filesystem, URI kiểu `jar:file:/.../archive.zip` mô tả archive dùng để mở filesystem; để tới một entry cụ thể, cách trực tiếp và rõ ràng là lấy `Path` từ đối tượng `FileSystem` đã mở.

## 3. `FileSystem`: một không gian đường dẫn cụ thể

Sau khi có `FileSystem`, ta có thể hỏi filesystem về đặc tính và tạo đường dẫn bên trong nó.

| Phương thức | Công dụng | Lưu ý |
| --- | --- | --- |
| `getPath(first, more...)` | Tạo `Path` theo cú pháp filesystem hiện tại. | Không tự đọc nội dung hay xác thực tệp có tồn tại. |
| `provider()` | Truy cập provider triển khai filesystem. | Có thể xem scheme bằng `provider().getScheme()`. |
| `getSeparator()` | Ký tự phân cách tên trong đường dẫn theo provider. | Không giả định mọi hệ thống dùng cùng `/` hoặc `\`. |
| `getRootDirectories()` | Liệt kê các root được filesystem cung cấp. | Có thể là nhiều root hoặc một root; không ép theo dạng ổ đĩa Windows. |
| `getFileStores()` | Các kho lưu trữ mà provider cho phép liệt kê. | Có thể thất bại/không đầy đủ tùy môi trường và quyền. |
| `supportedFileAttributeViews()` | Các nhóm thuộc tính có thể được hỗ trợ (ví dụ `basic`). | Không mặc định có `posix`, `dos` hay `acl`. |
| `getPathMatcher("glob:...")` | Tạo bộ so khớp đường dẫn theo cú pháp provider hỗ trợ. | Phụ thuộc provider/cú pháp `glob` hoặc `regex`. |
| `isOpen()`, `isReadOnly()` | Kiểm tra trạng thái đóng/mở và khả năng ghi. | Các hệ thống tệp ảo có thể chỉ đọc. |
| `close()` | Giải phóng tài nguyên filesystem có thể đóng. | Không đóng filesystem mặc định; đóng filesystem riêng khi dùng xong. |

Một `Path` luôn **gắn với một `FileSystem` cụ thể**:

~~~java
Path local = FileSystems.getDefault().getPath("notes.txt");
FileSystem owner = local.getFileSystem();
~~~

Hai `Path` nhìn giống tên nhau vẫn có thể thuộc hai filesystem khác nhau. Một số phép toán đường dẫn như `relativize` hoặc `resolve` với `Path` từ provider khác có thể ném `ProviderMismatchException`. Tạo đường dẫn bằng **`fs.getPath(...)` của filesystem đích** là cách đáng tin cậy để tránh nhầm không gian tên.

Ví dụ, `zipFs.getPath("/notes.txt")` là entry bên trong ZIP; `Path.of("notes.txt")` là đường dẫn trên filesystem mặc định. Chúng không trỏ vào cùng một nơi dù phần tên đều là `notes.txt`.

## 4. `FileSystemProvider`: lớp triển khai thao tác và cơ chế mở rộng

`FileSystemProvider` nằm trong `java.nio.file.spi`. Một provider công bố một URI scheme thông qua `getScheme()` và triển khai các phương thức để làm việc với tài nguyên của scheme đó.

Provider chịu trách nhiệm cho các nghiệp vụ nền tảng như:

- Tạo, tìm, trả về các filesystem: `newFileSystem(...)`, `getFileSystem(URI)` và `getPath(URI)`.
- Mở I/O hoặc channel: `newByteChannel(...)`, `newInputStream(...)`, `newOutputStream(...)` (một số phương thức có triển khai mặc định).
- Thao tác mục: `createDirectory(...)`, `delete(...)`, `copy(...)`, `move(...)` và `checkAccess(...)`.
- Đọc/ghi thuộc tính và hỗ trợ các thao tác liên quan đến link, directory stream, permissions tùy khả năng của provider.

Ta có thể liệt kê các provider được cài đặt và phát hiện trong runtime:

~~~java
import java.nio.file.spi.FileSystemProvider;

for (FileSystemProvider provider : FileSystemProvider.installedProviders()) {
    System.out.println(provider.getScheme());
}
~~~

Đây là **mảnh mã dùng trong `main`**. Trên một JDK thông thường có thể thấy `file` và `jar`, có thể có `jrt` hoặc provider bổ sung; **không dựa vào thứ tự hoặc số lượng provider** trong chương trình. Với runtime được tối giản bằng `jlink`, module ZIP provider (`jdk.zipfs`) có thể không hiện diện.

Kiến trúc SPI cho phép thư viện cung cấp một provider mới. Khi tự xây dựng provider, ngoài việc kế thừa `FileSystemProvider` còn phải triển khai các đối tượng `FileSystem`, `Path` và các thao tác I/O phù hợp, xử lý vòng đời, lỗi và quyền truy cập. Provider trên classpath thường được khai báo trong tệp dịch vụ:

~~~text
META-INF/services/java.nio.file.spi.FileSystemProvider
~~~

Nội dung là tên đầy đủ của lớp provider có thể khởi tạo theo quy tắc service provider. Trong một **named module**, có thể dùng khai báo `provides java.nio.file.spi.FileSystemProvider with ...;` trong `module-info.java` thay vì cơ chế khai báo classpath. Đây là công việc phát triển một filesystem provider hoàn chỉnh, không phải yêu cầu khi chỉ muốn đọc/ghi tệp bằng NIO.2.

## 5. Ví dụ Java 17+: tạo, ghi, đóng và mở lại ZIP filesystem

**Mục tiêu:** dùng một `FileSystemProvider` có scheme `jar` để coi tệp ZIP như một filesystem. Chương trình sẽ tạo một ZIP ở thư mục tạm, tạo tệp bên trong ZIP, đọc nội dung, đóng filesystem rồi mở lại để chứng minh dữ liệu đã được lưu.

Lưu toàn bộ mã sau vào `FileSystemDemo.java`:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class FileSystemDemo {
    public static void main(String[] args) throws IOException {
        FileSystem defaultFs = FileSystems.getDefault();
        System.out.println("defaultScheme=" + defaultFs.provider().getScheme());

        Path local = defaultFs.getPath("example.txt");
        System.out.println("localUsesDefault=" + (local.getFileSystem() == defaultFs));

        Path tempDir = Files.createTempDirectory("nio-fs-demo-");
        Path archive = tempDir.resolve("example.zip");
        URI zipUri = URI.create("jar:" + archive.toUri());

        try {
            // "create" là tùy chọn của ZIP filesystem provider,
            // không phải tùy chọn dùng chung cho mọi provider.
            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path entry = zipFs.getPath("/message.txt");
                Files.writeString(entry, "Hello, ZipFS", StandardCharsets.UTF_8);

                System.out.println("zipScheme=" + zipFs.provider().getScheme());
                System.out.println("zipText=" +
                        Files.readString(entry, StandardCharsets.UTF_8));
            }

            // Mở lại cùng archive sau khi instance ZIP trước đã đóng.
            try (FileSystem reopened = FileSystems.newFileSystem(
                    zipUri, Map.of())) {

                Path entry = reopened.getPath("/message.txt");
                System.out.println("reopenedText=" +
                        Files.readString(entry, StandardCharsets.UTF_8));
            }
        } finally {
            // Chỉ xóa archive sau khi ZIP filesystem đã được đóng.
            Files.deleteIfExists(archive);
            Files.deleteIfExists(tempDir);
        }
    }
}
~~~

Lệnh biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac FileSystemDemo.java
java FileSystemDemo
~~~

Kết quả điển hình trên JDK đầy đủ với default provider `file` và `jdk.zipfs`:

~~~text
defaultScheme=file
localUsesDefault=true
zipScheme=jar
zipText=Hello, ZipFS
reopenedText=Hello, ZipFS
~~~

Giải thích theo trình tự:

1. `defaultFs` là filesystem của máy; `local` là một `Path` thuộc filesystem đó. Chương trình không tạo `example.txt` ở ổ đĩa, chỉ tạo đối tượng đường dẫn.
2. `tempDir` là một thư mục tạm được tạo thật; `archive` xác định tệp ZIP sẽ được tạo. `URI.create("jar:" + archive.toUri())` tạo URI để ZIP provider nhận diện archive.
3. `FileSystems.newFileSystem(zipUri, Map.of("create", "true"))` yêu cầu ZIP provider tạo/mở filesystem trên archive; provider ghi nhận dữ liệu trong ZIP. Khóa `create` chỉ có ý nghĩa với ZIP provider.
4. `zipFs.getPath("/message.txt")` là **đường dẫn entry trong ZIP**, không phải `Path` trực tiếp tới tệp trên đĩa. `Files.writeString` và `Files.readString` thao tác qua provider của `zipFs`.
5. Khối `try-with-resources` gọi `close()` khi rời khối. Đóng ZIP filesystem rất quan trọng để ghi hoàn tất cấu trúc archive và giải phóng tài nguyên.
6. Khối thứ hai tạo một instance ZIP filesystem mới trên archive đã lưu, đọc lại `message.txt` và in `reopenedText`. Sau khi đóng, mã `finally` mới dọn archive và thư mục tạm.

Giá trị `defaultScheme=file` và `zipScheme=jar` là đặc điểm của provider trong môi trường chạy ví dụ. Nếu thiếu `jdk.zipfs`, provider bị vô hiệu hoặc thiếu quyền truy cập hệ thống tệp, ví dụ có thể ném ngoại lệ. Đây là điều kiện môi trường cần kiểm tra, không phải stdout thay thế.

Một cách khác để truy cập một ZIP **đã tồn tại** là `FileSystems.newFileSystem(Path.of("archive.zip"))` (overload hỗ trợ trên Java 17), khi runtime có provider chấp nhận loại tệp đó. Cách này khác với việc tạo archive mới bằng URI và tùy chọn `create`.

## 6. URI, filesystem instance và đường dẫn: chọn đúng thao tác

Ba loại truy cập thường được đặt cạnh nhau:

~~~java
FileSystem defaultFs = FileSystems.getDefault();      // Lấy mặc định
FileSystem mounted = FileSystems.getFileSystem(uri);   // Lấy instance đã mở
FileSystem created = FileSystems.newFileSystem(uri, Map.of()); // Tạo instance mới
~~~

Đây là **mảnh minh họa**, giả sử biến `uri` đã được định nghĩa và một provider tương ứng đã có. Không chạy liên tiếp ba dòng này trên một URI bất kỳ và mong luôn thành công: `getFileSystem` cần instance đã tồn tại, còn `newFileSystem` cần các điều kiện tạo/mở hợp lệ.

Phân biệt `Path.of(URI)` với `FileSystem.getPath(...)`:

- `Path.of(URI)` yêu cầu Java tìm provider của URI và lấy `Path` tương ứng. Không phải URI nào cũng đủ thông tin để tạo `Path`, và provider có thể yêu cầu filesystem đã được khởi tạo.
- `fileSystem.getPath("/inside.txt")` chỉ tạo một đường dẫn **trong filesystem đó**; không cần dịch lại scheme từ URI mỗi lần.
- `Path.of("relative.txt")` dùng filesystem mặc định, kể cả khi trong chương trình đang có ZIP filesystem mở.

Với ZIP/JAR, tránh ghép URI hoặc đường dẫn thủ công dựa trên giả định về hệ điều hành. Mở filesystem bằng API thích hợp và tạo entry bằng chính `zipFs.getPath(...)`. Không dùng `Path.of("/message.txt")` để chỉ entry ZIP.

Một đường dẫn giữa hai provider có thể được chuyển thành dữ liệu để sao chép bằng `Files.copy(source, target)` khi thao tác/provider hỗ trợ, nhưng không có nghĩa hai `Path` nằm trong cùng không gian tên; các lựa chọn thuộc tính, symbolic link và atomicity có thể khác nhau giữa provider. Không giả định một phép `move` xuyên filesystem có tính nguyên tử.

## 7. Vòng đời và giới hạn hỗ trợ

**Filesystem mặc định:** được Java runtime sở hữu, tồn tại trong suốt vòng đời ứng dụng. Đừng gọi `close()` lên filesystem mặc định.

**Filesystem tự mở:** nếu nó có thể đóng (ví dụ ZIP filesystem), dùng `try-with-resources`. Sau khi đóng:

- `isOpen()` thường trả `false` đối với instance đó.
- Những thao tác I/O dựa trên `Path` thuộc instance đã đóng có thể ném `ClosedFileSystemException`.
- `Path` không tự chuyển sang filesystem vừa mở lại; sau khi mở lại hãy lấy `Path` mới từ instance mới.
- Việc đọc metadata hoặc thao tác trên filesystem đóng phụ thuộc hợp đồng phương thức, nên không tận dụng một đối tượng đã đóng để làm việc tiếp.

`isReadOnly()` giúp nhận biết filesystem chỉ đọc. Không phải provider nào cũng hỗ trợ đồng đều symbolic link, watch service, file attribute views, permissions hoặc thao tác đồng bộ. Khi chỉ đọc dữ liệu tĩnh, đừng giả định có khả năng tạo file; với các thao tác có ràng buộc, hãy kiểm tra các API hỗ trợ rồi xử lý ngoại lệ thực tế.

Với provider của JAR/JRT/ảo, `FileStore` và root có thể khác xa cấu trúc ổ đĩa truyền thống. `getRootDirectories()` là nguồn dữ liệu phù hợp hơn việc tự đoán root `C:\` hoặc `/`.

## 8. Những ngoại lệ đáng phân biệt

| Ngoại lệ | Tình huống thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ProviderNotFoundException` | Không tìm thấy provider phù hợp khi cần tạo filesystem. | Xác minh scheme và module/thư viện provider, chẳng hạn `jdk.zipfs`. |
| `FileSystemAlreadyExistsException` | Cố tạo filesystem mà provider đã quản lý instance cho URI tương ứng. | Dùng instance đang mở khi phù hợp, hoặc đóng instance trước khi mở lại. |
| `FileSystemNotFoundException` | `getFileSystem(uri)` không tìm thấy filesystem đã được mở. | Xác minh vòng đời và thời điểm gọi `newFileSystem`. |
| `ClosedFileSystemException` | Dùng filesystem đã đóng. | Mở lại filesystem rồi lấy `Path` mới. |
| `ReadOnlyFileSystemException` | Thử ghi lên filesystem chỉ đọc. | Chọn đích ghi khác hoặc chỉ thực hiện thao tác đọc. |
| `ProviderMismatchException` | Kết hợp các đối tượng đường dẫn không tương thích provider ở phép toán yêu cầu cùng provider. | Tạo/diễn giải đường dẫn bằng đúng filesystem sở hữu. |
| `UnsupportedOperationException` | Provider không hỗ trợ phương thức hoặc tính năng được yêu cầu. | Kiểm tra khả năng của provider, chọn thao tác tương thích. |
| `IOException` và các lớp con | Lỗi tệp, quyền truy cập, định dạng archive hoặc vấn đề I/O khi tạo/đọc/ghi/đóng. | Xử lý theo nghiệp vụ; đừng coi lỗi I/O là filesystem không tồn tại. |

Một số exception ở bảng là unchecked; `IOException` là checked exception. Khi sử dụng `try-with-resources`, lỗi phát sinh từ `close()` cũng có thể là lỗi I/O cần xử lý. Không nuốt lỗi nếu kết quả ghi chưa chắc chắn đã được lưu.

## 9. Sai lầm phổ biến khi thiết kế mã NIO.2

**Nhầm `FileSystems` với `FileSystem`.** `FileSystems` chỉ là điểm truy cập với các phương thức tĩnh. Chính **instance** `FileSystem` mới quyết định `getPath`, root, provider và trạng thái đóng/mở.

**Tự tạo `Path.of("...")` rồi mong truy cập ZIP.** `Path.of(String...)` luôn dùng default filesystem. Muốn làm việc bên trong ZIP, dùng `zipFs.getPath(...)`.

**Gọi `newFileSystem` liên tục mà không đóng.** Nếu URI đó đã có instance, provider có thể từ chối; hơn nữa rò rỉ tài nguyên ZIP khiến thao tác quản lý archive bị ảnh hưởng. Dùng `try-with-resources` và xác định rõ đối tượng sở hữu vòng đời.

**Đoán scheme, provider hoặc khả năng hỗ trợ.** Đừng giả định mọi runtime đều có `jar` hoặc mọi provider đều có `posix`. Dùng `FileSystemProvider.installedProviders()` khi cần chẩn đoán; kiểm tra theo mục tiêu thực tế.

**Nhầm filesystem với thư mục.** Một `FileSystem` là toàn bộ không gian đường dẫn/đối tượng I/O do provider cung cấp; nó không đồng nghĩa một thư mục. Một ZIP archive có thể được trình bày thành filesystem riêng, còn một thư mục thường chỉ là một `Path` trong filesystem đã có.

**Cho rằng path bất kỳ tương thích với mọi provider.** `Path` mang thông tin hệ thống tệp sở hữu. Khi xây dựng API nhận `Path` từ bên ngoài, bảo toàn filesystem của nó thay vì âm thầm chuyển sang `Path.of(path.toString())` vì thao tác này có thể đổi ý nghĩa đường dẫn.

**Tin rằng API đồng nghĩa quyền truy cập.** Provider chịu trách nhiệm kiểm tra truy cập, định dạng và quyền hệ điều hành. Lỗi giữa kiểm tra và thao tác thực tế vẫn có thể xảy ra nếu hệ thống tệp thay đổi đồng thời. Khi xử lý đường dẫn do người dùng nhập, cần áp dụng quy tắc an toàn và phân quyền phù hợp.

## 10. Khi nào cần mỗi API?

| Nhu cầu | Chọn API |
| --- | --- |
| Đọc/ghi tệp thông thường trên máy | `Path.of(...)` và `Files.*`; ít khi cần tự gọi `FileSystems.getDefault()`. |
| Cần biết đường dẫn thuộc filesystem nào | `path.getFileSystem()`. |
| Cần tạo `Path` bên trong một ZIP filesystem đã mở | `zipFs.getPath(...)`. |
| Cần tạo/mở filesystem đặc biệt | `FileSystems.newFileSystem(...)` với URI/Path và tùy chọn provider thích hợp. |
| Cần dùng lại filesystem đã mở được định danh theo URI | `FileSystems.getFileSystem(uri)` nếu provider hỗ trợ và instance đang tồn tại. |
| Cần biết provider nào đang thao tác | `path.getFileSystem().provider()`. |
| Cần liệt kê provider được phát hiện | `FileSystemProvider.installedProviders()`. |
| Cần hỗ trợ giao thức/hệ thống tệp mới trong thư viện | Triển khai `FileSystemProvider` cùng `FileSystem`/`Path` phù hợp và đăng ký qua SPI. |

## 11. Tự kiểm tra

1. **`FileSystems.getDefault()` trả `FileSystem` hay `FileSystemProvider`?** Trả về một `FileSystem`; có thể lấy provider bằng `provider()`.
2. **Hai `Path` có cùng chuỗi tên thì chắc chắn chỉ cùng tệp?** Không. Chúng có thể thuộc các filesystem khác nhau hoặc được phân giải trong các ngữ cảnh khác nhau.
3. **Sau khi mở ZIP, `Path.of("/message.txt")` có chỉ entry bên trong ZIP?** Không. Nó thuộc default filesystem; phải dùng `zipFs.getPath("/message.txt")`.
4. **Vì sao cần đóng ZIP filesystem?** Để hoàn tất ghi/đồng bộ dữ liệu archive theo provider và giải phóng tài nguyên; nên dùng `try-with-resources`.
5. **`getFileSystem(uri)` và `newFileSystem(uri, env)` khác nhau ở đâu?** Phương thức đầu lấy filesystem đã có; phương thức sau yêu cầu tạo instance filesystem qua provider.
6. **Tại sao không hard-code danh sách provider?** Thành phần của runtime, module và thư viện có thể khác nhau giữa môi trường chạy.

**Ghi nhớ:** `FileSystems` là nơi **lấy hoặc khởi tạo** filesystem; `FileSystem` đại diện **một không gian đường dẫn cụ thể**; `FileSystemProvider` là **bộ triển khai các thao tác I/O** cho không gian đó. Khi đường dẫn không nằm trên filesystem mặc định, luôn lấy `Path` từ đúng `FileSystem` và quản lý vòng đời của filesystem được mở.
