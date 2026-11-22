# Thao tác xuyên file system và giới hạn provider trong Java NIO.2

## Mục tiêu

Java NIO.2 cho phép thao tác tệp thông qua `Path`, `FileSystem`, `FileSystemProvider` và lớp tiện ích `Files`. Một `Path` không nhất thiết trỏ đến tệp trên ổ đĩa của máy đang chạy: nó có thể đại diện một entry trong ZIP/JAR, một file system trong bộ nhớ hoặc một hệ thống lưu trữ được thư viện cung cấp. Vì vậy, **thao tác trên các đường dẫn thuộc những file system/provider khác nhau** có quy tắc và giới hạn riêng, không thể suy diễn từ việc copy/rename trên cùng một ổ đĩa.

Trong bài học, bạn sẽ:

- Phân biệt `Path`, `FileSystem`, `FileSystemProvider` và `FileStore`.
- Biết cách xác định provider của một `Path` và nhận diện trường hợp hai đường dẫn thuộc hai provider khác nhau.
- Hiểu rõ khi nào `Files.copy(source, target)` / `Files.move(source, target)` có thể thao tác xuyên provider; vì sao `ATOMIC_MOVE` có thể không được hỗ trợ.
- Biết các giới hạn của `Path.resolve`, `relativize`, `toFile`, file attributes, symbolic links, permissions và việc đóng file system.
- Thực hành ví dụ Java 17+ copy file từ filesystem mặc định vào một ZIP filesystem.
- Thiết kế thao tác file có kiểm tra lỗi, giới hạn tài nguyên và chiến lược rollback thích hợp.

## 1. File system và provider là gì?

`java.nio.file.Path` biểu diễn một tên đường dẫn **gắn với một `FileSystem`**. `FileSystem` mô tả cách tạo và phân tích đường dẫn, thư mục gốc, dấu phân cách, thuộc tính được hỗ trợ và vòng đời của hệ thống tệp. Một `FileSystemProvider` là triển khai cung cấp các thao tác I/O cho những file system thuộc nó.

```text
                    java.nio.file.Files
                     (API tiện ích)
                           |
                    ủy quyền thao tác
                           v
                FileSystemProvider
                /                \
      provider "file"        provider "jar"
           |                      |
   FileSystem mặc định       ZIP/JAR FileSystem
           |                      |
       Path trên OS          Path trong archive
    /tmp/report.txt         /docs/report.txt
```

Ví dụ:

- Provider **`file`** mặc định giúp truy cập hệ thống tệp do hệ điều hành cung cấp. Một `FileSystem` mặc định có thể nhìn thấy nhiều ổ đĩa/partition/mount.
- Provider **`jar`** (module `jdk.zipfs` của JDK) cho phép đọc và ghi các entry bên trong tệp ZIP/JAR qua API `Path`/`Files`.
- Một thư viện có thể thêm provider cho hệ thống tệp chuyên biệt. Khả năng đọc, ghi, metadata, file locking hoặc symbolic links phụ thuộc vào triển khai thực tế.

**Đừng đồng nhất ba khái niệm:**

| Khái niệm | Ý nghĩa |
| --- | --- |
| `FileSystemProvider` | Triển khai giao diện truy cập filesystem; thường được nhận diện qua URI scheme (`file`, `jar`, …). |
| `FileSystem` | Một thể hiện hệ thống tệp do provider cung cấp; một provider có thể quản lý nhiều thể hiện. |
| `FileStore` | Vùng lưu trữ/đơn vị lưu trữ được filesystem báo cáo (ví dụ phân vùng, volume, mount); không đồng nghĩa với provider. |

**Hai đường dẫn ở hai ổ đĩa không nhất thiết là hai provider.** Trên máy dùng provider `file` mặc định, nhiều drive hoặc mount thường vẫn thuộc cùng provider, dù thao tác rename nguyên tử giữa chúng không được bảo đảm.

## 2. Xác định provider của một `Path`

Đường dẫn cung cấp cách lấy filesystem và provider:

```java
// Snippet minh họa: path là Path đã được tạo.
FileSystem fs = path.getFileSystem();
FileSystemProvider provider = fs.provider();
String scheme = provider.getScheme();
```

Cần các import `java.nio.file.FileSystem` và `java.nio.file.spi.FileSystemProvider` nếu dùng đoạn mã trên như một phần chương trình.

Đối với một path trên filesystem mặc định, scheme thường là `file`. Với một path entry ZIP thuộc provider chuẩn, scheme là `jar`.

Có thể so sánh hai provider bằng:

```java
boolean sameProvider =
        pathA.getFileSystem().provider()
        == pathB.getFileSystem().provider();
```

Đây chỉ là phép so sánh **đối tượng provider**. Nó không chứng minh hai đường dẫn thuộc **cùng `FileSystem`**, cùng `FileStore`, cùng thiết bị vật lý hay có khả năng di chuyển nguyên tử.

Khi muốn so sánh **đúng cùng thể hiện FileSystem**, bạn có thể so sánh `pathA.getFileSystem() == pathB.getFileSystem()` trong ngữ cảnh thích hợp. Khi muốn hỏi filesystem nằm trên vùng lưu trữ nào, `Files.getFileStore(path)` có thể cung cấp thông tin, nhưng provider có thể không hỗ trợ hay giới hạn chi tiết này; hãy xử lý `IOException`.

## 3. Những thao tác hoạt động xuyên provider và những thao tác không

Không có quy tắc “khác provider thì mọi API NIO.2 đều thất bại”. Phải đọc hợp đồng **từng phương thức**.

| Thao tác | Khi source và target khác provider |
| --- | --- |
| `Files.copy(Path, Path, ...)` | API cấp cao **cho phép** source và target thuộc provider khác nhau; vẫn có thể lỗi do quyền, loại file, giới hạn provider, thuộc tính hoặc tài nguyên. |
| `Files.move(Path, Path, ...)` | API cấp cao cũng cho phép target khác provider; khi không thể rename trực tiếp, thao tác không nguyên tử có thể phải copy rồi xóa và có nhiều tình huống thất bại. |
| `Files.move(..., ATOMIC_MOVE)` | **Không được bảo đảm** xuyên filesystem/`FileStore`/provider; nếu không thực hiện nguyên tử được, ném `AtomicMoveNotSupportedException`. |
| `source.resolve(other)` | Là phép ghép đường dẫn của một filesystem; `other` từ provider khác có thể gây `ProviderMismatchException`. |
| `source.relativize(other)` | Yêu cầu đường dẫn tương thích; khác provider có thể gây `ProviderMismatchException` hoặc lỗi liên quan kiểu đường dẫn. |
| `Files.isSameFile(source, target)` | Nếu hai đường dẫn gắn với provider khác nhau thì kết quả là `false`, không phải phép suy luận nội dung hai file giống nhau. |
| `path.toFile()` | Chỉ được hỗ trợ với filesystem mặc định; ZIP/non-default `Path` thường ném `UnsupportedOperationException`. |
| `Files.readAttributes` / `getAttribute` | Tên view và thuộc tính phải được provider hỗ trợ; không có bảo đảm mọi provider đều hỗ trợ POSIX, DOS, owner, ACL, symlink hoặc timestamp với độ chính xác như nhau. |

Phân biệt **`Files.copy`** (phương thức facade cấp cao có thể phối hợp hai provider) với **`FileSystemProvider.copy`** (SPI của một provider, theo hợp đồng yêu cầu hai `Path` thuộc chính provider đó). Khi viết ứng dụng bình thường, hãy dùng `Files.copy` thay vì trực tiếp gọi `provider.copy` với hai kiểu path khác nhau.

### “Có thể thực hiện” không có nghĩa “luôn thành công”

Ngay cả `Files.copy` được thiết kế cho hai provider khác nhau cũng có thể từ chối vì:

- Đích là filesystem chỉ đọc hoặc đã đóng.
- Không hỗ trợ tạo file loại đó, symbolic link, attributes hoặc tùy chọn sao chép.
- File/thư mục đích đã tồn tại, đường dẫn cha chưa có hoặc không đủ quyền.
- Tệp nguồn thay đổi trong quá trình đọc.
- Hết dung lượng, giới hạn quota, lỗi I/O mạng, hoặc dữ liệu lớn hơn giới hạn của provider.

Vì vậy nên xem cross-filesystem operation là **một giao dịch I/O có thể thất bại giữa chừng**, không phải câu lệnh đổi tên tức thì.

## 4. Ví dụ Java 17+: copy file từ filesystem mặc định vào ZIP

Ví dụ sau sử dụng ZIP filesystem của JDK để thể hiện **hai provider thật sự khác nhau** mà không yêu cầu hai ổ đĩa vật lý. Chương trình tạo thư mục tạm, tạo tệp nguồn, mở một archive ZIP làm filesystem, copy dữ liệu vào ZIP, kiểm tra provider và đọc lại nội dung. Cuối chương trình nó đóng ZIP rồi dọn các tệp tạm.

Lưu tệp **`CrossProviderCopyDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class CrossProviderCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("provider-demo-");
        Path source = root.resolve("hello.txt");
        Path archive = root.resolve("sample.zip");

        try {
            Files.writeString(source, "Hello ZIP", StandardCharsets.UTF_8);

            URI zipUri = URI.create("jar:" + archive.toUri());
            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {
                Path entry = zip.getPath("/hello.txt");
                Files.copy(source, entry);

                System.out.println("source scheme = "
                        + source.getFileSystem().provider().getScheme());
                System.out.println("target scheme = "
                        + entry.getFileSystem().provider().getScheme());
                System.out.println("same provider = "
                        + (source.getFileSystem().provider()
                           == entry.getFileSystem().provider()));
                System.out.println("copied content = "
                        + Files.readString(entry, StandardCharsets.UTF_8));

                try {
                    source.resolve(zip.getPath("other.txt"));
                } catch (ProviderMismatchException e) {
                    System.out.println("resolve = ProviderMismatchException");
                }

                try {
                    entry.toFile();
                } catch (UnsupportedOperationException e) {
                    System.out.println("ZIP toFile = UnsupportedOperationException");
                }
            }
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy trên **JDK 17+ có module `jdk.zipfs`** (JDK đầy đủ thông thường cung cấp module này):

```bash
javac CrossProviderCopyDemo.java
java CrossProviderCopyDemo
```

Stdout trong môi trường JDK chuẩn hỗ trợ ZIP filesystem:

```text
source scheme = file
target scheme = jar
same provider = false
copied content = Hello ZIP
resolve = ProviderMismatchException
ZIP toFile = UnsupportedOperationException
```

**Giải thích:**

1. `source` thuộc filesystem mặc định (`file`). `entry` thuộc ZIP filesystem (`jar`).
2. `Files.copy(source, entry)` chuyển nội dung vào entry trong ZIP dù hai provider khác nhau. Đây là API cấp cao của `Files`, không phải kết quả của việc ép hai đường dẫn thành cùng kiểu.
3. `source.resolve(zip.getPath("other.txt"))` thử trộn một `Path` ZIP vào phép resolve của path filesystem mặc định nên báo `ProviderMismatchException`. Với loại đường dẫn này, `Path` không phải chuỗi ký tự có thể trộn tùy tiện.
4. `entry.toFile()` không dùng được vì `java.io.File` đại diện đường dẫn của filesystem mặc định, không phải đường dẫn entry ZIP.
5. `try-with-resources` **đóng `FileSystem` ZIP** trước khi xóa file archive. Các path trong ZIP không còn dùng để I/O sau khi filesystem đó đã đóng.
6. Ví dụ tạo tệp ZIP thật tại đường dẫn tạm `sample.zip`. Môi trường chỉ chứa JRE tùy biến không có `jdk.zipfs` có thể ném `ProviderNotFoundException`; quyền tạo file/quota cũng có thể gây lỗi I/O.

**Bài học quan trọng:** `Files.copy` làm việc được với nhiều provider, nhưng **không biến `Path` của ZIP thành `Path` của OS**. Hãy giữ và dùng đúng đường dẫn do filesystem tương ứng tạo.

## 5. `Files.move` và giới hạn của `ATOMIC_MOVE`

Khi rename file trong cùng một directory trên cùng vùng lưu trữ, hệ điều hành thường có thể hoàn thành nhanh mà không sao chép nội dung. Khi chuyển dữ liệu sang filesystem hoặc provider khác, không thể giả định thao tác đổi tên ấy còn khả thi.

```java
// Snippet: source và target là Path đã xác định.
Files.move(source, target);
```

`Files.move` cho phép đường dẫn đích khác provider, nhưng thực tế có thể tương đương quá trình **tạo bản sao rồi xóa nguồn**. Vì thế:

- Có thể tốn thời gian tỉ lệ với kích thước file.
- Metadata được bảo toàn không hoàn toàn đồng đều.
- Nếu lỗi giữa chừng, nguồn và đích có thể **cùng tồn tại**, đích có thể thiếu dữ liệu, hoặc trạng thái khác tùy triển khai.
- Không có bảo đảm một cây thư mục phức tạp được tự động di chuyển đệ quy.
- Không có bảo đảm chạy nguyên tử chỉ vì phương thức tên là `move`.

### Yêu cầu atomic move

```java
// Snippet, cần import java.nio.file.Files;
// java.nio.file.StandardCopyOption.
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

`ATOMIC_MOVE` yêu cầu thao tác di chuyển nguyên tử ở mức filesystem. Nếu không hỗ trợ, phương thức ném `AtomicMoveNotSupportedException`. Trường hợp nguồn và đích khác `FileStore` hoặc khác provider là ví dụ điển hình không thực hiện được atomic rename.

**Không được âm thầm bỏ `ATOMIC_MOVE`** nếu nghiệp vụ dựa trên nguyên tắc “người đọc chỉ nhìn thấy bản cũ hoặc bản mới, không bao giờ thấy file đang sao chép dở”. Một fallback không nguyên tử có thể phá hợp đồng an toàn của ứng dụng.

Một cách xử lý ngoại lệ đúng ngữ nghĩa:

```java
// Snippet: source/target đã xác định, phương thức khai báo IOException.
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (java.nio.file.AtomicMoveNotSupportedException e) {
    // Yêu cầu nghiệp vụ phải nguyên tử: báo không hỗ trợ,
    // không tự đổi thành move thường.
    throw new java.io.IOException(
            "The destination cannot provide an atomic move", e);
}
```

Nếu nghiệp vụ **chấp nhận move không nguyên tử**, hãy quyết định riêng một quy trình có staging, xác minh nội dung, cleanup và phục hồi khi lỗi. Việc đổi từ atomic sang non-atomic không đơn thuần là sửa một tham số cho chương trình hết exception.

### `REPLACE_EXISTING` không giải quyết mọi vấn đề

`StandardCopyOption.REPLACE_EXISTING` giúp thay thế một số loại tệp đích hiện có. Nó không bảo đảm:

- Thay thế một thư mục đích không rỗng.
- Ghi nguyên tử hoặc rollback khi copy thất bại.
- Bảo toàn mọi thuộc tính của tệp nguồn.
- Không có race giữa lúc kiểm tra tồn tại và lúc thay thế.

Khi `ATOMIC_MOVE` được chỉ định, các tùy chọn move khác theo đặc tả sẽ bị bỏ qua; cách xử lý tệp đích đã tồn tại có thể phụ thuộc triển khai. Đừng coi `REPLACE_EXISTING` cộng `ATOMIC_MOVE` là phép thay thế nguyên tử được bảo đảm trên mọi provider.

## 6. `Files.copy`: nội dung, thuộc tính và symbolic link

Sao chép một file thường bằng:

```java
// Snippet: source/target là Path, xử lý IOException ở nơi gọi.
Files.copy(source, target);
```

Để thay thế file đích nếu chính sách cho phép:

```java
Files.copy(source, target,
        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
```

Một số tùy chọn:

- **`REPLACE_EXISTING`:** thử thay thế đích có sẵn theo các giới hạn của API; không tự xóa cây thư mục không rỗng.
- **`COPY_ATTRIBUTES`:** yêu cầu cố gắng sao chép thuộc tính. Những thuộc tính **thực sự** được sao chép phụ thuộc provider và file store; `lastModifiedTime` là mức tối thiểu được nêu khi cả hai phía hỗ trợ, và độ chính xác timestamp có thể thay đổi.
- **`NOFOLLOW_LINKS`:** không đi theo symbolic link nguồn trong quá trình copy. Việc tạo symbolic link tương ứng ở đích có thể thất bại nếu provider đích không hỗ trợ symbolic link.

Copy không phải thao tác nguyên tử. Nếu `IOException` phát sinh, file đích có thể đã xuất hiện và **chưa hoàn chỉnh**. Với nội dung quan trọng, thường cần:

1. Chọn đích tạm trên filesystem **của đích cuối cùng**.
2. Copy vào đích tạm và xác minh nội dung theo yêu cầu (kích thước, checksum hoặc format).
3. Chỉ sau đó mới áp dụng phương thức công bố đích cuối; nếu yêu cầu nguyên tử, thử atomic rename **trong cùng vùng lưu trữ phù hợp**.
4. Nếu atomic rename không hỗ trợ mà nghiệp vụ bắt buộc nguyên tử, báo lỗi thay vì giả định fallback tương đương.
5. Dọn tệp tạm thuộc quyền sở hữu của mình khi lỗi; lưu ý crash có thể khiến file tạm còn lại để quá trình phục hồi xử lý.

Staging trên filesystem đích giúp **giảm** rủi ro xuất hiện file cuối đang được copy dở; nó không tự bảo đảm mọi vấn đề về durability, fsync, security hoặc recovery.

## 7. Directory không được copy/move đệ quy chỉ bằng một lời gọi

`Files.copy(sourceDir, targetDir)` **không tự copy mọi file con**. Theo hợp đồng chung, khi source là directory, thao tác copy tạo một directory đích tương ứng nhưng không sao chép các entry bên trong. Muốn copy tree, cần triển khai logic duyệt riêng, ví dụ `Files.walkFileTree` và xử lý:

- Tạo từng thư mục đích đúng thứ tự.
- Copy file con.
- Giải quyết vấn đề symbolic link và tránh vòng lặp.
- Giới hạn số lượng entry, chiều sâu, tổng byte và lỗi truy cập.
- Ánh xạ metadata dựa trên khả năng của provider đích.
- Hành vi khi đang copy mà file nguồn thay đổi hoặc đích bị trùng.

### Ví dụ Java 17+: copy directory không tự copy file con

Lưu thành **`DirectoryCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryCopyDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-copy-");
        Path source = root.resolve("source");
        Path target = root.resolve("target");

        try {
            Files.createDirectory(source);
            Files.writeString(source.resolve("child.txt"),
                    "data", StandardCharsets.UTF_8);

            Files.copy(source, target);
            System.out.println("target directory exists = "
                    + Files.isDirectory(target));
            System.out.println("child was copied = "
                    + Files.exists(target.resolve("child.txt")));
        } finally {
            Files.deleteIfExists(source.resolve("child.txt"));
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac DirectoryCopyDemo.java
java DirectoryCopyDemo
```

Stdout:

```text
target directory exists = true
child was copied = false
```

Ví dụ không phải copy xuyên provider; nó cô lập một giới hạn quan trọng **áp dụng cả với cùng filesystem**. Khi copy cây xuyên provider, giới hạn càng đáng chú ý vì hai bên có thể khác nhau về symlink, attributes và quyền.

## 8. `ProviderMismatchException`: lỗi do trộn đường dẫn không tương thích

Lớp `Path` là **đối tượng thuộc một filesystem cụ thể**, không chỉ là chuỗi path tùy ý. Ví dụ, một path `/docs/report.txt` trong ZIP không chỉ định tệp `/docs/report.txt` của hệ điều hành.

Các thao tác như `resolve` và `relativize` thuộc về **hệ thống quy tắc tên đường dẫn của chính filesystem**. Chuyển path của provider khác vào đó có thể gây `ProviderMismatchException`.

**Tránh cách làm sai:**

```java
// Snippet minh họa: nativePath thuộc provider "file",
// zipPath thuộc provider "jar".
Path wrong = nativePath.resolve(zipPath);
```

Đừng chữa bằng cách ép `zipPath.toString()` thành native `Path` rồi xem nó là cùng file. Chuỗi `/docs/report.txt` không chứa đủ thông tin về provider, archive hoặc mount. Làm vậy thường **đổi ý nghĩa đường dẫn**, không biến path ZIP thành path native.

**Cách đúng:** Khi copy, đưa **hai `Path` gốc** trực tiếp cho `Files.copy(nativePath, zipPath)`. Nếu tạo đường dẫn con trong ZIP, dùng chính `zipPath.getFileSystem().getPath(...)` hoặc `zipDirectory.resolve("child.txt")` với phần tử tương đối thuộc filesystem đó.

### `Path.toFile()` không phải cầu nối giữa mọi provider

`java.io.File` được thiết kế cho filesystem mặc định. Vì thế:

```java
// Snippet: zipEntry là Path của ZIP FileSystem.
File legacy = zipEntry.toFile(); // UnsupportedOperationException.
```

Khi API cũ chỉ nhận `File` nhưng dữ liệu nằm trong ZIP, phải đổi **chiến lược xử lý**, ví dụ dùng `Files.newInputStream(zipEntry)` và một API nhận `InputStream`, hoặc giải nén sang một file tạm trên filesystem mặc định nếu yêu cầu thật sự cần file vật lý. Không nên “chữa lỗi” bằng cách đổi dấu phân cách của `zipEntry.toString()`.

## 9. Thuộc tính file và capability khác nhau theo provider

Ngay cả khi `Files.copy` sao chép thành công **nội dung**, không nên mặc định metadata cũng được giữ y nguyên.

| Khả năng | Vì sao có thể khác |
| --- | --- |
| `basic` attributes | Thông tin size, timestamp hoặc loại file có thể có mức hỗ trợ và độ chính xác khác nhau. |
| `posix` permissions | Không phải provider nào cũng mô hình hóa bit `rwx` kiểu Unix. |
| `dos` attributes | Không phải hệ thống nào cũng hỗ trợ hidden/read-only/archive/system như DOS/Windows. |
| ACL/owner/group | Principal và mô hình quyền có thể không tương thích giữa nguồn và đích. |
| Symbolic links | Có provider không hỗ trợ, hoặc có cách biểu diễn link khác. |
| Hard links | `Files.createLink` có thể không được hỗ trợ hoặc chỉ hợp lệ trong filesystem thích hợp. |
| File locking/memory mapping | Khả năng và ngoại lệ phụ thuộc provider/channel. |
| Timestamp granularity | Sao chép mốc thời gian có thể mất độ chính xác. |
| FileStore / quota | Không phải provider nào cũng báo quota/dung lượng theo cách có ích. |

Kiểm tra danh sách attribute views của filesystem:

```java
// Snippet: path là Path hợp lệ.
System.out.println(path.getFileSystem()
        .supportedFileAttributeViews());
```

Cần nhớ kết quả phản ánh capability của **provider/filesystem** ở mức được công bố; thao tác trên một file cụ thể vẫn có thể thất bại do quyền hoặc loại đối tượng.

Ví dụ nếu provider đích không hỗ trợ `posix`, lời gọi `Files.getPosixFilePermissions(target)` có thể ném `UnsupportedOperationException`. Không cố copy thủ công một tập quyền POSIX vào ZIP filesystem mà chưa kiểm tra mức hỗ trợ và đặc tả của provider.

**`COPY_ATTRIBUTES` không có nghĩa sao chép tất cả metadata.** Thuộc tính nào được copy còn phụ thuộc cả nguồn, đích và loại attribute. Khi metadata là yêu cầu nghiệp vụ quan trọng, hãy liệt kê rõ những thuộc tính bắt buộc, kiểm tra khả năng hỗ trợ và **xác minh lại trên đích**.

## 10. Vòng đời ZIP filesystem và provider tùy biến

Một ZIP filesystem được tạo bằng `FileSystems.newFileSystem(...)` phải được **đóng** để giải phóng tài nguyên và hoàn tất các thao tác nội bộ cần thiết. Khi filesystem đã đóng:

- Các path của nó có thể vẫn tồn tại dưới dạng object Java nhưng **không còn dùng được cho I/O**; thao tác thích hợp có thể ném `ClosedFileSystemException`.
- Không giả định `Files.readString(entry)` vẫn hoạt động sau khi khối `try (FileSystem zip = ...)` kết thúc.
- Không xóa archive ZIP khi vẫn còn một filesystem đang thao tác trên nó nếu cần độ nhất quán dữ liệu.
- Không dùng một filesystem dùng chung trong nhiều thành phần mà không quy định rõ **ai được phép gọi `close()`**.

Đối với provider bên thứ ba, tài liệu của provider là nơi xác định thêm quy tắc mở, đóng, URI scheme, thuộc tính, hỗ trợ song song và chính sách lỗi. Tên `Path` hoặc tên file extension không đủ để kết luận provider nào đang được sử dụng.

## 11. Thiết kế thao tác cross-filesystem an toàn hơn

Một quy trình thực tế thường cần nhiều bước hơn một lời gọi `Files.move`:

1. **Xác định loại nguồn/đích**: regular file, directory, symlink hay special file; kiểm tra khả năng của filesystem đích.
2. **Kiểm soát đường dẫn**: với input bên ngoài, kiểm tra absolute path, `..`, symlink và quyền hạn theo mô hình bảo mật; không dùng riêng `normalize` để coi là an toàn.
3. **Đặt giới hạn tài nguyên**: kích thước byte, số entry, chiều sâu thư mục, tổng dung lượng, thời gian và quota.
4. **Chọn chiến lược ghi**: copy trực tiếp khi có thể chấp nhận file đích chưa hoàn chỉnh lúc lỗi; nếu không, copy vào staging area của đích.
5. **Xác minh**: kiểm tra kích thước hoặc checksum nội dung (khi định dạng và nghiệp vụ yêu cầu), các thuộc tính thật sự phải bảo toàn.
6. **Công bố kết quả**: nếu cần bảo đảm thay thế nguyên tử, chỉ dùng `ATOMIC_MOVE` khi filesystem thực sự hỗ trợ; nếu không, báo không thể đáp ứng yêu cầu.
7. **Xóa nguồn khi đã an toàn**: nếu nghiệp vụ là di chuyển bằng copy+delete, chỉ xóa sau khi xác nhận dữ liệu đích đúng tiêu chí. Thao tác này vẫn không trở thành một giao dịch nguyên tử giữa hai filesystem.
8. **Phục hồi sau lỗi**: log trạng thái, biết file tạm nào do ứng dụng tạo, tránh xóa mất dữ liệu nguồn/đích hợp lệ; thiết kế retry/idempotency nếu cần.

Khi dùng mạng, cloud mount hoặc file system ảo, còn phải xét kết nối bị cắt, tính nhất quán metadata và cơ chế xác thực quyền truy cập riêng. Không có cách “tự động dùng `Files.move`” nào đảm bảo cùng chất lượng giao dịch trên mọi provider.

## 12. Những lỗi phổ biến

1. **Tưởng mọi `Path` đều thuộc `FileSystems.getDefault()`.** ZIP, memory filesystem và provider khác có namespace riêng.
2. **Tưởng hai ổ đĩa là hai provider.** Chúng có thể chung provider `file` nhưng khác `FileStore`.
3. **Tưởng khác provider thì `Files.copy` luôn ném `ProviderMismatchException`.** Facade `Files.copy` cho phép target khác provider; `Path.resolve`/`relativize` lại là chuyện khác.
4. **Tưởng `Files.move` xuyên provider tự động nguyên tử.** Không có bảo đảm; `ATOMIC_MOVE` có thể thất bại.
5. **Bắt `AtomicMoveNotSupportedException` rồi chuyển sang move thường mà không kiểm tra yêu cầu nghiệp vụ.** Fallback có thể phá tính nhất quán mà người đọc kỳ vọng.
6. **Tưởng `COPY_ATTRIBUTES` đồng nghĩa giữ mọi quyền sở hữu/timestamp/ACL.** Tính năng và độ chính xác khác nhau theo provider.
7. **Tưởng `Files.copy` copy đệ quy cả thư mục.** Nó không tự copy các entry con; cần thuật toán duyệt cây riêng.
8. **Tưởng `REPLACE_EXISTING` là cơ chế rollback.** Có thể còn file đích không hoàn chỉnh nếu I/O lỗi giữa chừng.
9. **Gọi `zipPath.toFile()`.** API `File` không thể biểu diễn mọi đường dẫn không thuộc filesystem mặc định.
10. **Lấy `zipPath.toString()` rồi tạo `Path.of(...)`.** Thao tác đó làm mất ý nghĩa ZIP provider và có thể trỏ tới file khác hoàn toàn.
11. **Tiếp tục dùng path sau khi đóng ZIP filesystem.** Có thể nhận `ClosedFileSystemException`.
12. **Không kiểm tra symbolic link và security boundary.** Copy link khác copy dữ liệu đích link; traversal/race cần chính sách rõ.
13. **Chỉ kiểm tra `Files.exists` trước khi thao tác rồi nghĩ rằng không thể xảy ra race.** File có thể bị thay đổi giữa hai lần gọi.
14. **Dùng metadata size làm toàn bộ cơ chế giới hạn dữ liệu.** Nguồn có thể thay đổi, dữ liệu có thể quá lớn, cần đếm/giới hạn trong quá trình xử lý.

## 13. Câu hỏi tự kiểm tra

**1.** Một path ở ổ C: và path ở ổ D: có nhất thiết khác provider không?

**Đáp án:** Không. Chúng có thể cùng dùng provider `file` mặc định, nhưng khác `FileStore`, và atomic move giữa chúng vẫn có thể không được hỗ trợ.

**2.** Có thể gọi `Files.copy(pathOnDisk, pathInsideZip)` không?

**Đáp án:** Có thể, nếu ZIP filesystem được mở để ghi, đích hợp lệ và provider hỗ trợ thao tác cần thiết. `Files.copy` cấp cao cho phép đường dẫn ở hai provider khác nhau.

**3.** Vì sao `pathOnDisk.resolve(pathInsideZip)` không phải cách tạo địa chỉ entry ZIP?

**Đáp án:** Hai path thuộc namespace khác nhau. Phép resolve của filesystem mặc định không hiểu path ZIP và có thể ném `ProviderMismatchException`. Hãy dùng ZIP filesystem để tạo path đích.

**4.** `Files.move(source, target, ATOMIC_MOVE)` thất bại khi khác filesystem. Có thể tự động bỏ `ATOMIC_MOVE` không?

**Đáp án:** Chỉ khi nghiệp vụ **chấp nhận không nguyên tử** và đã thiết kế logic xác minh/phục hồi thích hợp. Nếu yêu cầu nguyên tử là bắt buộc, phải báo không hỗ trợ.

**5.** `Files.copy(sourceDirectory, targetDirectory)` có sao chép cả cây con không?

**Đáp án:** Không. Muốn sao chép cây thư mục phải tự duyệt và copy từng entry theo chính sách symbolic link và lỗi.

**6.** Khi dùng `COPY_ATTRIBUTES`, có chắc chắn giữ nguyên toàn bộ POSIX permissions và ACL trong ZIP không?

**Đáp án:** Không. Thuộc tính được hỗ trợ và chuyển giao phụ thuộc provider/`FileStore`; cần kiểm tra, xác minh những thuộc tính thật sự quan trọng.

**7.** Tại sao phải đóng `FileSystem` ZIP?

**Đáp án:** Để giải phóng tài nguyên và hoàn tất các thao tác nội bộ cần thiết. Khi ZIP filesystem đã đóng, các entry `Path` của nó không còn sử dụng được cho I/O bình thường.

**8.** Magic scheme `jar` và `file` có đồng nghĩa hai vùng lưu trên hai thiết bị vật lý khác nhau không?

**Đáp án:** Không. ZIP archive bản thân có thể nằm trên cùng thiết bị lưu trữ với file nguồn; provider khác nói về **cách truy cập và namespace**, không nhất thiết nói về phần cứng.

## 14. Tài liệu Java 17

- [`Files.copy`, `Files.move` và các tùy chọn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileSystemProvider` và khác biệt SPI/API cấp cao](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html)
- [`Path` — `resolve`, `relativize`, `toFile`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [`jdk.zipfs` — thuộc tính và tùy chọn của ZIP File System](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html)

**Ghi nhớ:** `Path` luôn gắn với một filesystem/provider. `Files.copy` và `Files.move` có thể hoạt động **xuyên provider** theo hợp đồng API, nhưng không có bảo đảm mọi thuộc tính được giữ hoặc thao tác di chuyển là nguyên tử. Đừng trộn `Path` từ hai namespace bằng `resolve`, đừng mặc định `toFile()` hoạt động với ZIP, và luôn xử lý lỗi, giới hạn provider, metadata và vòng đời tài nguyên một cách tường minh.