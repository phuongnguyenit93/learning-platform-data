# Khả năng mở rộng FileSystemProvider và ranh giới của Java API

## 1. Vấn đề: chung API không có nghĩa chung mọi khả năng

Java NIO.2 (`java.nio.file`) cho phép viết mã dựa trên `Path` và `Files` để truy cập các hệ thống tệp khác nhau: hệ thống tệp mặc định của OS, nội dung ZIP/JAR và những backend do thư viện bên thứ ba triển khai. Cơ chế đó dựa trên **FileSystemProvider**, một Service Provider Interface (SPI) mở rộng được.

Ví dụ, cùng một lời gọi `Files.readString(path)` có thể đọc một file trên ổ đĩa hay một entry trong ZIP, **miễn là provider của `path` hỗ trợ thao tác cần thiết**.

Phải phân biệt ba lớp trách nhiệm:

1. **Java API** định nghĩa giao diện, kiểu dữ liệu, các quy tắc và ngoại lệ được tài liệu hóa.
2. **File-system provider** biến yêu cầu từ API thành thao tác của backend cụ thể và công bố tính năng mà nó hỗ trợ.
3. **File system/file store thực tế** quyết định hiệu năng, quyền truy cập, loại thuộc tính, tính nguyên tử và những giới hạn nền tảng.

Do đó, một phương thức xuất hiện trong `Files` không chứng minh mọi hệ thống tệp đều có cùng chức năng hay bảo đảm hành vi.

## 2. Những thành phần tạo nên kiến trúc

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `Path` | Biểu diễn đường dẫn gắn với một `FileSystem` cụ thể | `Path.of("data.txt")` hoặc `zipFs.getPath("/data.txt")` |
| `FileSystem` | Quản lý root, separator, provider, attribute views và vòng đời của một hệ thống tệp | `FileSystems.getDefault()`, file system ZIP |
| `FileSystemProvider` | SPI tạo/tìm file system, chuyển URI thành Path, thực thi các thao tác tệp cấp thấp | Provider scheme `file` và `jar` |
| `Files` | Các thao tác tiện lợi ở cấp API, thường dùng provider của các `Path` tương ứng | `readString`, `copy`, `walk`, `readAttributes` |
| `FileStore` | Thông tin kho lưu trữ do provider đại diện | `Files.getFileStore(path)` |

Luồng hoạt động ở mức khái niệm:

~~~text
Ứng dụng
   └── Path / Files / FileSystems (API Java NIO.2)
          └── FileSystemProvider (SPI)
                 └── Hệ thống tệp mặc định, ZIP hoặc backend cụ thể
~~~

Đây là sơ đồ kiến trúc; từng phương thức `Files` có thể phối hợp nhiều thao tác provider, không nhất thiết ủy quyền đúng một phương thức SPI.

Một `Path` luôn gắn với `FileSystem` của nó. Để biết nó thuộc provider nào:

~~~java
Path path = Path.of("data.txt");
FileSystem fs = path.getFileSystem();
System.out.println(fs.provider().getScheme()); // file với default provider
~~~

Đây là đoạn minh họa, không phải một chương trình độc lập. Tệp `data.txt` không cần tồn tại để tạo `Path`.

## 3. Mở rộng provider có nghĩa gì?

### 3.1. Provider mặc định

`FileSystems.getDefault()` trả về file system mặc định của JVM. Provider mặc định dùng URI scheme `file` và tạo các `Path` từ lời gọi thông thường như `Path.of("notes.txt")`.

Không đồng nhất scheme `file` với NTFS, ext4 hay APFS. Cùng provider mặc định có thể làm việc với các file store khác nhau, với quy tắc case sensitivity, quyền, khóa và độ chính xác timestamp phụ thuộc nền tảng.

### 3.2. Provider bổ sung

Một provider là lớp con cụ thể của `java.nio.file.spi.FileSystemProvider`, được nhận diện bằng URI scheme, đóng vai trò factory cho một hay nhiều `FileSystem`.

Ví dụ thực tế trong JDK 17: **module `jdk.zipfs` cung cấp ZIP file-system provider** với scheme `jar`, để đọc/ghi các entry trong ZIP/JAR như những `Path`.

Một thư viện khác *có thể* cung cấp backend in-memory, mạng hoặc object storage với scheme riêng (chẳng hạn `memory`). Các tên scheme giả định không phải khả năng có sẵn của Java SE; chúng chỉ có ý nghĩa nếu provider tương ứng đã được cài đặt và hỗ trợ.

Provider định nghĩa cách phân tích URI, đường dẫn, nội dung, thuộc tính tệp và các thao tác I/O. Nhờ đó mã ứng dụng có thể tái sử dụng nhiều thao tác `Files`, trong phạm vi hợp đồng mà provider hiện thực hóa.

### 3.3. ZIP là ví dụ dễ hiểu

ZIP provider cho phép sử dụng `Path` bên trong một tệp ZIP:

~~~java
URI uri = URI.create("jar:" + archive.toUri());
try (FileSystem zipFs =
         FileSystems.newFileSystem(uri, Map.of("create", "true"))) {
    Path entry = zipFs.getPath("/notes.txt");
    Files.writeString(entry, "Xin chao");
}
~~~

Đây là đoạn minh họa trong một phương thức đã có biến `Path archive` và xử lý `IOException`. `create=true` là **cấu hình của ZIP provider**, không phải tham số chung cho tất cả provider. Ví dụ đầy đủ, chạy được, có ở mục 6.

`FileSystem` mở riêng như ZIP nên được đóng với `try-with-resources`. Các `Path` trỏ đến file system đã đóng không thể tiếp tục I/O bình thường; đừng giữ `Path` ZIP sau khi đóng rồi giả định nó vẫn đọc được.

Một runtime image tùy biến (ví dụ tạo bằng `jlink`) có thể thiếu module `jdk.zipfs`. Khi đó, ứng dụng phải xử lý lỗi provider không khả dụng, thay vì giả định mọi bản phân phối Java đều có ZIP provider.

## 4. Tìm kiếm, nạp và khởi tạo provider

Những API liên quan:

- `FileSystems.getDefault()`: lấy file system mặc định.
- `FileSystemProvider.installedProviders()`: lấy danh sách provider đã được nạp theo SPI, gồm default provider.
- `FileSystems.newFileSystem(URI, Map)`: tìm provider theo URI scheme và yêu cầu tạo một file system theo tham số provider quy định.
- `FileSystems.getFileSystem(URI)`: lấy file system đã tồn tại; không phải lệnh tạo mới.
- `FileSystems.newFileSystem(Path)`: thử mở một tệp dưới dạng file system theo định dạng/provider khả dụng, ví dụ ZIP.
- `Path.of(URI)` hay `Paths.get(URI)`: đổi URI thành `Path` bằng provider. Tùy provider, file system tương ứng có thể phải được khởi tạo trước.

Ví dụ phân biệt:

~~~java
URI uri = URI.create("jar:file:/tmp/sample.zip");

// newFileSystem: tạo một phiên file system khi provider cho phép
FileSystem created = FileSystems.newFileSystem(uri, Map.of());

// getFileSystem: yêu cầu lấy file system đã tồn tại theo URI
FileSystem existing = FileSystems.getFileSystem(uri);
~~~

Đây là mã minh họa, **không phải đoạn chạy độc lập**. Nó giả định tệp ZIP có thật, provider `jar` khả dụng và `created` vẫn đang mở. Cú pháp đường dẫn URI cụ thể phụ thuộc OS/provider.

Những ngoại lệ thường gặp:

| Trường hợp | Ngoại lệ |
|---|---|
| Không có provider cho URI scheme | `ProviderNotFoundException` |
| Chưa có file system tương ứng khi gọi `getFileSystem` | `FileSystemNotFoundException` |
| Tạo trùng file system mà provider không cho phép | `FileSystemAlreadyExistsException` |
| File system đã đóng | `ClosedFileSystemException` |
| Dữ liệu/archive lỗi hoặc sự cố backend | `IOException` hoặc ngoại lệ cụ thể |

**Nạp plugin qua ServiceLoader**

JAR trên classpath thường có một lớp con concrete của `FileSystemProvider` với constructor không tham số, cùng tệp service descriptor:

~~~text
META-INF/services/java.nio.file.spi.FileSystemProvider
~~~

Nội dung tệp descriptor có một hay nhiều dòng là tên lớp provider đầy đủ, chẳng hạn `com.example.CustomProvider`. Tên này **chỉ để minh họa**, đòi hỏi lớp thật sự tồn tại và được triển khai đúng SPI.

Với named module, có thể khai báo trong `module-info.java`:

~~~java
provides java.nio.file.spi.FileSystemProvider
        with com.example.CustomProvider;
~~~

Đây chỉ là một khai báo JPMS minh họa, **không phải module hoàn chỉnh**. Module và lớp provider phải được build, cung cấp trên module path/runtime và triển khai hợp đồng SPI.

Provider bổ sung được khám phá qua `ServiceLoader`; thứ tự tải các provider không được ứng dụng tùy tiện phụ thuộc. Nếu trùng URI scheme với provider đã được chọn trước, provider trùng sau có thể bị bỏ qua; không thiết kế logic chọn provider theo vị trí danh sách.

**Mở rộng provider mặc định là trường hợp khác:** system property `java.nio.file.spi.DefaultFileSystemProvider` có thể chỉ định chuỗi lớp provider bọc provider mặc định. Những lớp này nhận một `FileSystemProvider` qua constructor một tham số và cùng scheme `file`. Đây không phải cơ chế cần dùng khi đơn giản muốn thêm scheme mới như `jar`.

## 5. Ranh giới giữa API chung và khả năng backend

### 5.1. Không phải mọi thao tác đều được hỗ trợ

| Nhu cầu | Vì sao cần kiểm tra provider/file store? |
|---|---|
| Symbolic link, hard link | Backend có thể không hỗ trợ hoặc không cấp quyền tạo link |
| POSIX owner/permissions, ACL | Chỉ có trên các attribute view được hỗ trợ |
| WatchService | Có thể không hỗ trợ, hoặc có cách thông báo khác nhau |
| File locking, memory mapping, async channel | Không phải provider nào cũng có đầy đủ tính năng kênh |
| `ATOMIC_MOVE` | Chỉ thực hiện được nếu backend hỗ trợ move nguyên tử trong hoàn cảnh đó |
| Thời gian sửa tệp và attribute copying | Độ chính xác, thuộc tính được copy phụ thuộc file store/provider |
| Case sensitivity, root, separator và path syntax | Là quy tắc của `FileSystem` |
| Latency, consistency và xử lý lỗi | Khác nhau giữa local FS, ZIP và backend từ xa |

Hỏi provider về capability thay vì suy luận theo tên OS:

~~~java
FileSystem fs = path.getFileSystem();
boolean supportsPosix =
        fs.supportedFileAttributeViews().contains("posix");
~~~

Đây là đoạn mã minh họa với `path` có sẵn. Muốn kiểm tra attribute view cụ thể cho một `Path`, có thể gọi `Files.getFileAttributeView(path, PosixFileAttributeView.class)`; có thể trả `null` nếu view không có. Việc hỗ trợ view không bảo đảm mọi thao tác quyền trên mọi tệp đều thành công.

### 5.2. Không được đánh mất hệ thống tệp của Path

Hai `Path` có chuỗi in ra giống nhau nhưng có thể thuộc hai provider khác nhau. Vì vậy:

- `Path.equals` không coi hai `Path` từ file system khác nhau là bằng nhau.
- `Files.isSameFile(a, b)` trả `false` nếu hai đường dẫn thuộc các provider khác nhau.
- Các phép như `resolve(Path)` với các đối số không tương thích có thể phát sinh `ProviderMismatchException`.
- `Path.of(zipEntry.toString())` tạo `Path` **mới trên default file system**, không còn là `Path` của ZIP.
- Dùng `zipFs.getPath("/entry.txt")` hoặc `directoryInZip.resolve("entry.txt")` để tiếp tục với ZIP provider.

Sử dụng API cùng tên không làm danh tính backend của hai `Path` trở thành một.

### 5.3. Copy giữa provider không đồng nghĩa thao tác nguyên tử

`Files.copy(source, target)` hỗ trợ trường hợp source và target thuộc những provider khác nhau. Java có thể phối hợp đọc từ provider nguồn và ghi tới provider đích.

Tuy nhiên, các bảo đảm cần hiểu rõ:

1. Copy tạo một tệp đích độc lập; nội dung giống không làm hai tệp thành cùng một tệp.
2. Copy không nguyên tử; nếu lỗi giữa chừng, đích có thể chưa hoàn chỉnh.
3. Copy attributes tùy nền tảng/provider/option, có thể mất độ chính xác timestamp hoặc không copy được một số thuộc tính.
4. `Files.copy` một thư mục **không tự copy đệ quy toàn bộ cây**; cần duyệt cây nếu muốn chuyển cả cấu trúc.
5. Move giữa các provider/file store có thể không thực hiện được hoặc cần cơ chế khác; `ATOMIC_MOVE` không được bảo đảm và có thể ném `AtomicMoveNotSupportedException`.

Một lời gọi API chung không tự biến ZIP/local/network thành cùng một transaction.

### 5.4. Từ chối đúng cách khi feature không tồn tại

Tùy phương thức và provider, Java có thể phát sinh `UnsupportedOperationException` cho option/feature/attribute view không được hỗ trợ, `IOException` cho lỗi I/O, `ProviderMismatchException` cho Path không tương thích, hoặc ngoại lệ cụ thể khác theo tài liệu API.

Không chuyển tất cả thành kết luận “file không tồn tại”. Lỗi thiếu provider, lỗi đóng file system, lỗi permission và lỗi I/O cần chiến lược xử lý khác nhau.

## 6. Ví dụ Java 17+ chạy được: local và ZIP provider

Chương trình sau tạo file local, tạo ZIP file system, copy tệp sang ZIP, rồi đóng và mở lại ZIP để chứng minh dữ liệu được lưu. Nó sử dụng JDK có module `jdk.zipfs`, không cần dependency ngoài.

**Tệp: `ProviderBoundaryDemo.java`**

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ProviderBoundaryDemo {
    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("provider-demo-");
        Path source = work.resolve("source.txt");
        Path archive = work.resolve("bundle.zip");

        try {
            Files.writeString(source, "Xin chao", StandardCharsets.UTF_8);
            URI zipUri = URI.create("jar:" + archive.toUri());

            try (FileSystem zipFs =
                    FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
                Path entry = zipFs.getPath("/message.txt");
                Files.copy(source, entry);

                System.out.println(
                        source.getFileSystem().provider().getScheme());
                System.out.println(
                        entry.getFileSystem().provider().getScheme());
                System.out.println(Files.readString(entry));
                System.out.println(Files.isSameFile(source, entry));
            }

            try (FileSystem reopened = FileSystems.newFileSystem(archive)) {
                System.out.println(
                        Files.readString(reopened.getPath("/message.txt")));
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(work);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file mã nguồn:

~~~bash
javac ProviderBoundaryDemo.java
java ProviderBoundaryDemo
~~~

**Stdout khi ZIP provider có sẵn:**

~~~text
file
jar
Xin chao
false
Xin chao
~~~

Giải thích kết quả:

1. `source` ở default provider (`file`).
2. `entry` nằm trong ZIP (`jar`).
3. Cùng API `Files.copy` và `Files.readString` thao tác qua hai provider khác nhau.
4. `Files.isSameFile` trả `false` do hai provider khác nhau.
5. Mở lại ZIP từ file sau khi đóng chứng minh `message.txt` vẫn được lưu trong archive.

Chương trình dùng tên thư mục tạm ngẫu nhiên nhưng không in ra, nên kết quả hiển thị ổn định. `finally` thực hiện dọn tệp; việc xóa vẫn có thể thất bại với `IOException` nếu backend/OS gặp lỗi. Khi runtime không có `jdk.zipfs`, việc mở `jar` có thể báo không tìm thấy provider.

## 7. Nếu tự viết FileSystemProvider thì cần làm những gì?

Một provider không chỉ là “adapter đọc file”. Nhà phát triển phải triển khai concrete `FileSystemProvider` và các kiểu `FileSystem`/`Path` có semantics nhất quán.

Những nhóm trách nhiệm chính:

- **Định danh/khởi tạo:** `getScheme()`, `newFileSystem(URI, env)`, `getFileSystem(URI)`, `getPath(URI)`.
- **Đường dẫn:** root, relative/absolute, tên và separator, so sánh/chuẩn hóa, vòng đời file system.
- **I/O:** `newByteChannel`, đọc/ghi dữ liệu, `newDirectoryStream`, tạo/xóa/copy/move file và directory.
- **Metadata:** `checkAccess`, `isSameFile`, `getFileStore`, `readAttributes`, `getFileAttributeView`, `setAttribute`, cùng khả năng hỗ trợ view.
- **Lỗi và concurrency:** ném ngoại lệ tương thích hợp đồng, xử lý đóng tài nguyên, I/O đồng thời, trạng thái tệp thay đổi.

Có phương thức SPI bắt buộc triển khai (`abstract`) và phương thức có mặc định có thể báo không hỗ trợ. Trước khi triển khai phải xem Javadoc từng phương thức, thay vì sao chép logic từ một loại backend rồi giả định áp dụng cho mọi hệ thống.

Với object storage, ví dụ “thư mục” có thể là cách biểu diễn tên key, rename có thể không nguyên tử, và danh sách file có tính chất khác POSIX. Nếu viết provider, cần mô tả rõ ranh giới về semantics, consistency và hiệu năng. Nếu chỉ cần truy cập ZIP, dùng `jdk.zipfs` sẵn có thường đơn giản hơn tự viết SPI.

## 8. Nguyên tắc viết code có thể làm việc với nhiều provider

- **Giữ nguyên `Path` và file system của nó:** truyền `Path` giữa các lớp, tránh đổi qua `toString()` rồi dựng lại bằng `Path.of(...)`.
- **Giải quyết đường dẫn con trong file system hiện tại:** `directory.resolve("child.txt")` hoặc `directory.getFileSystem().getPath(...)`. Tránh lắp ghép chuỗi separator theo OS.
- **Khảo sát capability trước tính năng đặc thù:** attribute views, file store, hỗ trợ link/watch/channel và atomic move.
- **Dùng `Files` khi hợp đồng đủ cho nhu cầu:** các thao tác đọc/ghi/copy có thể dùng chung, nhưng không giả định các tùy chọn bổ sung đều khả dụng.
- **Xử lý lỗi theo loại:** phân biệt không có provider, file system đã đóng, feature thiếu, permission và lỗi I/O.
- **Quản lý vòng đời:** đóng `FileSystem` được mở riêng như ZIP, channel, stream và `Stream<Path>` từ `Files.walk`. Không chủ động đóng file system mặc định của JVM.
- **Kiểm tra thực tế trên provider đích:** test filesystem behavior, atomicity, thuộc tính, hiệu năng. Unit test trên thư mục tạm local không thay thế được integration test của backend đặc thù.
- **Không bỏ qua chi phí:** provider từ xa có thể phát sinh nhiều request/network I/O từ các thao tác tưởng nhỏ như `exists`, `list` hoặc `readAttributes`.

## 9. Những hiểu lầm phổ biến

1. **“Có `Files.readString` thì mọi backend đọc được.”** Sai: provider phải hỗ trợ thao tác và dữ liệu phải truy cập được.
2. **“File bên trong ZIP và file local đều là `Path` nên có thể so/ghép tùy ý.”** Sai: hai file system/provider khác nhau.
3. **“`getFileSystem(uri)` tự tạo file system khi chưa có.”** Sai: nó lấy một file system đang tồn tại, khác `newFileSystem`.
4. **“`Files.copy` sẽ copy cả cây con và bảo toàn mọi thuộc tính.”** Sai: phải tự xử lý đệ quy; thuộc tính phụ thuộc provider.
5. **“`ATOMIC_MOVE` sẽ thành công giữa hai provider.”** Không được bảo đảm.
6. **“Chỉ cần service descriptor là có custom provider hoạt động.”** Sai: phải có lớp thực thi hợp đồng, đăng ký và đóng gói đúng.
7. **“Mọi runtime Java đều có `jdk.zipfs`.”** Runtime tối giản có thể loại module này.

## 10. Ghi nhớ

~~~text
Java API: mô tả cách ứng dụng yêu cầu thao tác.
FileSystemProvider: thực thi yêu cầu trên backend cụ thể.
Backend/file store: quyết định khả năng, giới hạn và chi phí thực tế.
~~~

Trước khi phụ thuộc vào một khả năng, hãy hỏi: **`Path` này thuộc provider nào? Hợp đồng Java cam kết gì? Provider/file store có thực sự hỗ trợ tính năng và mức bảo đảm mà ứng dụng cần không?**

### Tài liệu chính thức

- [Java 17: FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [Java 17: FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html)
- [Java 17: Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17: Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [JDK 17: jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html)
