# ZIP file system trong Java: thao tác archive bằng Path và Files

Một tệp `.zip` thường được xem như một archive cần giải nén rồi mới xử lý. Java NIO.2 còn cung cấp **ZIP file system (ZipFS)**: gắn nội dung ZIP vào một `FileSystem`, từ đó đọc, tạo, sao chép, đổi tên và xóa entry bằng chính `Path` và `Files`. Cách này phù hợp khi cần thao tác nhiều tệp bên trong một ZIP mà không muốn tự quản lý từng `ZipEntry`.

## 1. Mục tiêu và mô hình tư duy

Sau bài này, bạn có thể:

- Tạo archive ZIP mới, mở ZIP đã có và đóng tài nguyên đúng cách.
- Phân biệt đường dẫn của hệ điều hành với đường dẫn **bên trong ZIP**.
- Sử dụng `Files.createDirectories`, `writeString`, `readString`, `copy`, `move`, `delete`, `walk` trên ZIP.
- Hiểu ranh giới provider, giới hạn, lỗi thường gặp và rủi ro khi nhận ZIP không tin cậy.
- Chọn ZipFS hoặc API dạng stream/entry tùy loại công việc.

Sơ đồ:

```text
Hệ điều hành                    ZIP file system
/tmp/work/lesson.zip  ─mở─>   /
                               └── docs/
                                   ├── readme.md
                                   └── source.txt
Path của ZIP trên máy           Path của entry trong ZIP
```

`Files` là lớp thao tác theo `Path`; nó không mặc định chỉ làm việc với đĩa. Mỗi `Path` thuộc về một `FileSystem` và `FileSystemProvider`. Khi `Path` trỏ tới entry của ZipFS, thao tác `Files` được chuyển tới ZIP provider của JDK. Nội dung trong archive chưa trở thành các tệp thông thường ở thư mục bên ngoài.

Các kiểu chính:

| Thành phần | Vai trò |
| --- | --- |
| `java.nio.file.Path` | Định danh ZIP trên đĩa, hoặc một entry **bên trong** ZipFS; hai loại Path có provider khác nhau. |
| `java.nio.file.FileSystem` | Ngữ cảnh truy cập các entry của ZIP; cần đóng bằng `close()`. |
| `java.nio.file.FileSystems` | Mở/tạo ZipFS qua `newFileSystem(...)`. |
| `java.nio.file.Files` | Đọc/ghi/liệt kê/thao tác entry như với một filesystem. |
| `jdk.zipfs` | ZIP filesystem provider đi kèm các bản JDK phổ biến; ứng dụng runtime tối giản phải có module này. |

## 2. Chương trình hoàn chỉnh: tạo, duyệt, đọc và chỉnh sửa ZIP

Ví dụ sau độc lập, chạy trên Java 17+. Nó tạo thư mục tạm riêng nên không xóa hoặc ghi đè ZIP của người học. Sau lượt đầu, `try-with-resources` đóng ZipFS để ghi các thay đổi vào archive; lượt sau mở lại file ZIP đó và sửa các entry.

Lưu đúng tên **`ZipFsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.stream.Stream;

public class ZipFsDemo {
    public static void main(String[] args) throws Exception {
        Path workDir = Files.createTempDirectory("zipfs-demo-");
        Path source = workDir.resolve("source.txt");
        Path archive = workDir.resolve("lesson.zip");
        Files.writeString(source, "Tệp nguồn\n", StandardCharsets.UTF_8);

        // Tạo ZIP chưa tồn tại. Bên trong ZIP dùng Path của zipFs.
        try (FileSystem zipFs = FileSystems.newFileSystem(
                archive, Map.of("create", "true"))) {
            Path docs = zipFs.getPath("/docs");
            Files.createDirectories(docs);
            Files.copy(source, docs.resolve("source.txt"));
            Files.writeString(docs.resolve("readme.md"), "# ZIP FS\n",
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);

            try (Stream<Path> entries = Files.walk(zipFs.getPath("/"))) {
                entries.filter(path -> Files.isRegularFile(path))
                        .map(Path::toString)
                        .sorted()
                        .forEach(System.out::println);
            }
        }

        // ZIP đã tồn tại: mở không có create, đọc, đổi tên, xóa entry.
        try (FileSystem zipFs = FileSystems.newFileSystem(archive, Map.of())) {
            Path docs = zipFs.getPath("/docs");
            Path readme = docs.resolve("readme.md");
            System.out.print(Files.readString(readme, StandardCharsets.UTF_8));
            Path guide = docs.resolve("guide.md");
            Files.move(readme, guide);
            Files.delete(docs.resolve("source.txt"));
            System.out.println("guide exists: " + Files.exists(guide));
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```bash
javac ZipFsDemo.java
java ZipFsDemo
```

Kết quả stdout:

```text
/docs/readme.md
/docs/source.txt
# ZIP FS
guide exists: true
```

Đường dẫn thật của `lesson.zip` thay đổi theo máy, nhưng không được in nên stdout ở trên ổn định. Khi chương trình kết thúc, archive còn `/docs/guide.md`; `/docs/source.txt` đã bị xóa.

**Đọc từng bước:**

1. `Files.createTempDirectory` tạo thư mục vật lý; `archive` là `Path` thuộc filesystem mặc định. `Files.writeString(source, ...)` ghi tệp nguồn *ngoài ZIP*.
2. `FileSystems.newFileSystem(archive, Map.of("create", "true"))` mở một filesystem cho ZIP; tùy chọn `create` cho phép tạo archive nếu chưa có. Nếu file không phải ZIP hợp lệ, mở có thể ném `ZipException`/`IOException`.
3. `zipFs.getPath("/docs")` tạo đường dẫn *bên trong archive*. `Files.createDirectories` tạo thư mục entry; `Files.copy` chép từ file thật sang ZIP; `Files.writeString` ghi thêm một entry.
4. `Files.walk` trả về `Stream<Path>`, phải đóng bằng `try-with-resources`. Lọc file thường để không in `/` và `/docs`; sắp xếp để output ổn định.
5. Đóng `zipFs` là bước cần thiết để giải phóng tài nguyên và hoàn tất ghi; sau đó mở lại ZIP ở chế độ hiện có. `Files.move` đổi tên entry, `Files.delete` xóa entry. Các thay đổi được ghi lại khi đóng.

## 3. Hai không gian Path: điểm dễ nhầm nhất

```java
Path zipOnDisk = Path.of("backup.zip");       // Path trên OS
// Trong một khối đã mở: FileSystem zipFs = ...
Path fileInZip = zipFs.getPath("/docs/a.txt"); // Path thuộc ZipFS
```

Hai dòng chỉ minh họa sự khác biệt; `zipFs` phải được khởi tạo trong mã thực tế. `zipOnDisk.resolve("docs/a.txt")` **không** trỏ vào archive: nó biểu diễn một đường dẫn filesystem ngoài ZIP. Ngược lại, `zipFs.getPath("/docs/a.txt")` trỏ đúng entry khi ZipFS đang mở.

Có thể dùng `zipFs.getPath("/docs").resolve("a.txt")` để tạo đường dẫn con. Dấu `/` trong các ví dụ là cú pháp đường dẫn ZIP; không nên xây đường dẫn entry bằng cách nối chuỗi separator của hệ điều hành. Chỉ dùng `Files` cho những `Path` còn hiệu lực và thuộc đúng provider.

Các thao tác sau đều có ý nghĩa rõ ràng khi cả hai `Path` đã được khai báo:

| Nhu cầu | Gọi API | Ý nghĩa |
| --- | --- | --- |
| Ngoài ZIP → trong ZIP | `Files.copy(hostFile, zipEntry)` | Đưa file vào archive. |
| Trong ZIP → ngoài ZIP | `Files.copy(zipEntry, hostFile)` | Trích **một** entry ra thư mục ngoài. |
| Trong ZIP → trong ZIP | `Files.copy(entryA, entryB)` | Nhân bản một entry trong filesystem phù hợp. |
| Đổi tên trong ZIP | `Files.move(oldEntry, newEntry)` | Di chuyển/đổi tên entry. |
| Xóa entry | `Files.delete(entry)` | Xóa entry; thư mục phải trống nếu xóa thư mục. |

Nếu đích đã tồn tại, `Files.copy` thường ném `FileAlreadyExistsException`, trừ khi cung cấp `StandardCopyOption.REPLACE_EXISTING` và provider chấp nhận. Tránh dùng `Files.move` xuyên hai provider như một giả định về thao tác nguyên tử; chuyển file giữa các filesystem có thể phải sao chép rồi xóa, có thể thất bại giữa chừng.

## 4. Mở ZIP đúng cách và quản lý vòng đời

**Tạo archive mới:**

```java
try (FileSystem fs = FileSystems.newFileSystem(
        archivePath, Map.of("create", "true"))) {
    Files.createDirectories(fs.getPath("/logs"));
    Files.writeString(fs.getPath("/logs/result.txt"), "OK\n");
}
```

Đây là đoạn minh họa dùng biến `archivePath` đã được khai báo là `Path` trên đĩa. Trong API ZipFS của JDK, tùy chọn `create` nhận chuỗi `"true"`; nếu ZIP đã có, lời gọi cũng mở ZIP đó. Nếu yêu cầu **chỉ tạo file mới**, kiểm tra/điều phối việc đặt tên bên ngoài trước và xử lý tranh chấp đồng thời; một phép kiểm tra `Files.exists` đơn lẻ không phải khóa.

**Mở archive đang có:**

```java
try (FileSystem fs = FileSystems.newFileSystem(archivePath, Map.of())) {
    Path entry = fs.getPath("/logs/result.txt");
    if (Files.isRegularFile(entry)) {
        String content = Files.readString(entry, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
```

Hai đoạn này là snippet có biến `archivePath` từ ngữ cảnh, không phải chương trình độc lập. Một ZIP chỉ đọc có thể mở với `Map.of("readonly", "true")` nếu provider và phiên bản JDK hỗ trợ tùy chọn đó; đừng coi quyền filesystem ngoài ZIP hay mọi environment key là khả chuyển giữa các provider. Nếu cần chỉ đọc một cách đơn giản, tránh gọi bất kỳ API ghi nào và đảm bảo file ZIP ở ngoài được bảo vệ theo quyền OS.

Một số API thay thế:

- `FileSystems.newFileSystem(Path, Map<String, ?>)`: dùng `Path` của file archive, tiện cho công việc thông thường.
- `FileSystems.newFileSystem(URI, Map<String, ?>)`: thường dùng URI có scheme `jar:`, ví dụ `URI.create("jar:" + archivePath.toUri())`. Cần phân biệt URI của archive với `Path` entry và với URI của filesystem khác.
- `FileSystems.getFileSystem(URI)`: tra filesystem đã được đăng ký theo URI, không tạo mới. Với biến thể `newFileSystem(URI, ...)`, mở trùng một filesystem còn tồn tại có thể ném `FileSystemAlreadyExistsException`.

**Quy tắc tài nguyên:** giữ mọi thao tác với entry bên trong `try (FileSystem fs = ...)`. Sau khi `fs.close()`, sử dụng `Path` gắn với fs đó có thể ném `ClosedFileSystemException`. Không mở/đóng nhiều lần cho từng entry; xử lý một nhóm tác vụ trong một phiên ZipFS, đóng sau khi hoàn tất.

## 5. Liệt kê, tìm, đọc và ghi các entry

Khi đã có `FileSystem fs` đang mở:

```java
Path root = fs.getPath("/");
try (Stream<Path> stream = Files.walk(root)) {
    stream.filter(Files::isRegularFile)
          .map(root::relativize)
          .forEach(System.out::println);
}
```

`Files.walk` duyệt đệ quy và có thể tốn tài nguyên trên ZIP lớn; dùng `Files.list(fs.getPath("/docs"))` khi chỉ cần một cấp. Cả hai trả về stream cần đóng. Thứ tự duyệt không được đảm bảo, hãy `sorted()` nếu kiểm thử đòi output cố định. `root.relativize(path)` đổi `/docs/a.txt` thành `docs/a.txt` trong cùng filesystem; không trộn `Path` từ hai provider ở các phép `relativize`/`resolve` cần cùng ngữ cảnh.

Với file văn bản nhỏ, `Files.readString(entry, StandardCharsets.UTF_8)` và `Files.writeString(...)` thuận tiện. Dùng `Files.newBufferedReader`, `newBufferedWriter` hoặc stream cho dữ liệu lớn để không giữ toàn bộ entry trong RAM. Cần có parent directory trước khi ghi: `Files.createDirectories(entry.getParent())`. Các option ghi phổ biến:

- `CREATE_NEW`: chỉ tạo nếu entry chưa tồn tại; hữu ích để tránh vô tình thay file.
- `CREATE`: tạo nếu chưa có, nhưng có thể mở file hiện có.
- `TRUNCATE_EXISTING`: xóa nội dung cũ khi mở ghi nếu entry tồn tại.
- `APPEND`: chỉ dùng khi provider và ngữ nghĩa file cho phép; ZIP không tối ưu cho log append thường xuyên.

Khi xử lý byte không phải text, ưu tiên `Files.newInputStream`/`newOutputStream`, `Files.copy` hoặc `Files.readAllBytes` cho payload nhỏ; tránh `readString` đối với ảnh, class, PDF hay dữ liệu nhị phân.

## 6. Hành vi ghi và giới hạn cần hiểu

Một archive là một tệp container. Chỉnh sửa một entry **không tương đương** ghi từng byte trực tiếp vào một thư mục OS: provider có thể tổ chức lại và viết lại dữ liệu archive khi đóng, nên thao tác ghi hàng loạt, kích thước lớn hoặc mở/đóng liên tục có thể đắt. Đừng mặc định đổi tên, sao chép hay ghi entry có cùng chi phí và tính nguyên tử như filesystem vật lý.

Với dự án thực tế:

1. Mở ZipFS một lần cho một batch, thao tác trên `Path` của chính filesystem đó, đóng một lần; tránh xử lý từng file bằng cách mở/đóng ZIP riêng.
2. Luôn quyết định rõ xử lý trùng tên (giữ nguyên, từ chối hay `REPLACE_EXISTING`) và bọc các lỗi `IOException`.
3. Không giả định `StandardCopyOption.ATOMIC_MOVE` hoạt động với ZIP. Không coi cập nhật archive là transaction: nếu tiến trình bị dừng trong lúc sửa, file có thể không đạt trạng thái kỳ vọng.
4. Với dữ liệu quan trọng, làm việc trên bản ZIP tạm trong **cùng filesystem đích trên OS**, kiểm tra kết quả rồi thay archive đích bằng chiến lược phù hợp; lưu bản sao lưu và chuẩn bị xử lý lỗi. Việc thay file trên OS có thể được yêu cầu nguyên tử nhưng còn tùy provider/file store.
5. Tránh nhiều writer cùng sửa một ZIP. Đồng bộ hóa ở mức ứng dụng hoặc dùng quy trình single-writer; khóa filesystem và cache ZipFS không thay thế chiến lược phối hợp.

ZipFS không phải hệ thống file POSIX hoàn chỉnh. Quyền truy cập, symbolic link, file attributes, rename và các option nâng cao có thể khác, thiếu hoặc không được hỗ trợ. `Files.setPosixFilePermissions` và `WatchService` chẳng hạn không nên được giả định hoạt động. ZipFS cũng không phải API để tự động mã hóa/mở ZIP được bảo vệ bằng mật khẩu.

**Hiệu năng:** phù hợp với số entry vừa phải và nhu cầu truy cập ngẫu nhiên nhiều entry; với file lớn cần stream để giới hạn RAM. Đánh giá kích thước tổng, số entry, tần suất ghi và thời gian đóng filesystem. Đừng đọc toàn bộ archive thành mảng byte nếu chưa chắc giới hạn dung lượng.

## 7. Đọc ZIP không tin cậy và giải nén an toàn

Bài này chủ yếu thao tác *trong* ZipFS, nhưng khi copy entry ra một thư mục OS phải đặc biệt chú ý:

- **ZIP Slip/path traversal:** một tên entry do bên ngoài cung cấp có thể chứa `../` hoặc đường dẫn tuyệt đối. Chuẩn hóa đường dẫn đích và bảo đảm đích vẫn nằm trong thư mục giải nén cho phép. Không nối nguyên tên entry vào đường dẫn host rồi ghi ngay.
- **ZIP bomb:** archive nhỏ có thể giải nén thành lượng dữ liệu rất lớn, chứa nhiều entry hoặc đường dẫn lồng sâu. Giới hạn số entry, kích thước sau giải nén, thời gian và dung lượng; giới hạn tổng thể phải được kiểm tra trong lúc streaming, không chỉ tin metadata.
- **Entry bất thường:** chuẩn hóa tên, xử lý separator, tên trùng nhau, tên được mã hóa, thư mục rỗng, loại file/attribute không được hỗ trợ, và mọi `IOException`.
- **Nguồn không tin cậy:** không chạy chương trình, script hay nạp class vừa lấy từ ZIP; chỉ xử lý như dữ liệu.

Phác thảo kiểm tra đường dẫn đích khi trích entry (đoạn này sử dụng `entry` là Path của ZipFS, `destinationRoot` là thư mục OS đã chuẩn hóa):

```java
Path root = destinationRoot.toAbsolutePath().normalize();
Path relative = entry.isAbsolute()
        ? entry.getRoot().relativize(entry)
        : entry;
Path dest = root.resolve(relative.toString()).normalize();
if (!dest.startsWith(root) || dest.equals(root)) {
    throw new SecurityException("Entry path ngoài thư mục đích");
}
```

Đây chỉ là **một lớp kiểm tra cú pháp đường dẫn**, chưa phải trình giải nén an toàn hoàn chỉnh. Với dữ liệu độc hại, cần chính sách rõ về symbolic link đã tồn tại ở thư mục đích, race giữa kiểm tra/ghi, quota, và file đặc biệt; cân nhắc `SecureDirectoryStream` ở nơi hỗ trợ và môi trường giải nén cô lập. Đừng dựa duy nhất vào `normalize()` để bảo vệ trước link hay thay đổi filesystem đồng thời.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | ZIP chưa tồn tại hoặc entry/parent thiếu. | Xác minh archive; tạo mới bằng `create=true` khi đúng mục tiêu; tạo parent trong ZIP trước. |
| `FileAlreadyExistsException` | Tạo/copy vào entry đã có. | Chọn `CREATE_NEW` hay `REPLACE_EXISTING` theo chính sách. |
| `ProviderNotFoundException` | Runtime thiếu ZIP provider, ví dụ custom `jlink` image thiếu `jdk.zipfs`. | Kiểm tra image/module runtime và thêm `jdk.zipfs` khi đóng gói. |
| `FileSystemAlreadyExistsException` | Mở lại cùng URI `jar:` khi FileSystem đó còn được đăng ký. | Dùng lại filesystem hiện có hoặc quản lý vòng đời; không mở trùng URI tùy tiện. |
| `ClosedFileSystemException` | Đọc/ghi entry sau khi đóng `FileSystem`. | Giữ toàn bộ xử lý entry trong khối `try-with-resources`. |
| `ProviderMismatchException` | Trộn Path khác provider trong thao tác yêu cầu cùng hệ. | Xác định rõ Path OS và Path ZipFS; dùng thao tác copy xuyên provider khi hỗ trợ. |
| `ZipException`/`IOException` | Archive hỏng, dữ liệu không phải ZIP, quyền hạn hoặc lỗi I/O. | Xác thực đầu vào, báo lỗi có ngữ cảnh, đóng resources, không tiếp tục với archive hỏng. |
| Không thấy thay đổi ngay trong file ngoài | FileSystem chưa được đóng hoặc ứng dụng còn giữ luồng ghi. | Đóng stream và `FileSystem` trước khi dùng archive ở quy trình khác. |

Lỗi và thời điểm ném phụ thuộc thao tác, provider và hệ điều hành; bảng trên là các tình huống điển hình, không phải ánh xạ 1–1 bắt buộc.

## 9. Khi nào dùng ZipFS, ZipFile hay ZipInputStream?

| Công cụ | Ưu điểm chính | Nên chọn khi |
| --- | --- | --- |
| **ZipFS + `Path`/`Files`** | API thống nhất để đọc/ghi/copy/đổi tên/xóa nhiều entry. | Cần xử lý ZIP như cây thư mục và cập nhật archive. |
| `java.util.zip.ZipFile` | Tra cứu và đọc từng entry trong ZIP có sẵn. | Chủ yếu đọc, muốn duyệt entry và lấy `InputStream`. |
| `ZipInputStream` | Duyệt entry nối tiếp từ một luồng dữ liệu. | Đọc stream ZIP mà không cần filesystem hoặc truy cập ngẫu nhiên. |
| `ZipOutputStream` | Ghi ZIP tuần tự với `ZipEntry`. | Tự tạo archive theo luồng, cần kiểm soát thứ tự/metadata entry. |

Không có một API tốt nhất cho mọi trường hợp. ZipFS hữu ích nhất khi thao tác đa dạng thông qua cùng giao diện NIO. Nếu chỉ trích lần lượt từng entry từ network stream, các lớp `java.util.zip` thường đơn giản hơn. ZIP chuẩn sử dụng nén theo entry; ZIP không cung cấp đầy đủ semantics filesystem như cơ sở dữ liệu hoặc giao dịch.

## 10. Checklist sử dụng và bài tập tự luyện

Trước khi triển khai: xác nhận archive nằm ở đâu, entry thuộc provider nào, ZIP tạo mới hay đang tồn tại, chính sách ghi đè, encoding văn bản, giới hạn kích thước, bảo mật đường dẫn, quản lý `close()` và chiến lược xử lý lỗi.

**Bài tập 1 — Thêm file vào ZIP.** Dựa trên chương trình mẫu, tạo `/images/info.txt` bằng `Files.createDirectories` và `Files.writeString` rồi dùng `Files.walk` chứng minh entry đã xuất hiện. Hãy thử cố tình ghi `CREATE_NEW` lần thứ hai để quan sát lỗi trùng tên.

**Bài tập 2 — Sao chép ra ngoài.** Mở ZIP đã có, chọn `/docs/guide.md` và dùng `Files.copy` ra file mới nằm dưới thư mục `workDir`. Kiểm tra nội dung ngoài ZIP bằng `Files.readString`. Đảm bảo đường dẫn ngoài ZIP được tạo từ `workDir` chứ không phải `zipFs.getPath`.

**Bài tập 3 — Kiểm tra vòng đời và tính toàn vẹn.** Mở ZIP, cập nhật hai entry, đóng ZipFS, mở lại để so sánh nội dung. Sau đó thử truy cập một `Path` cũ sau `close()` và giải thích vì sao phải tạo lại `Path` từ filesystem mới.

**Ghi nhớ:** `archivePath` trỏ tới *container ZIP trên OS*; `zipFs.getPath("/...")` trỏ tới *entry bên trong container*. Dùng `Files` trên đúng `Path`, gom thao tác vào một vòng đời `FileSystem`, đóng tài nguyên và coi dữ liệu ZIP từ bên ngoài là đầu vào không tin cậy.
