# `Files` trong Java: Sao chép thuộc tính và giới hạn giữa các hệ thống tệp

## 1. Vấn đề: sao chép được nội dung không đồng nghĩa sao chép toàn bộ file

Khi ứng dụng Java chuyển tài liệu từ một thư mục sang thư mục khác, từ đĩa cục bộ sang ổ chia sẻ, hoặc từ filesystem thông thường vào filesystem ZIP, người viết thường mong muốn **file đích giống file nguồn**. Nhưng “giống” có nhiều mức:

- **Nội dung:** các byte trong tệp có giống nhau?
- **Thuộc tính cơ bản:** thời điểm chỉnh sửa cuối, thời điểm truy cập, thời điểm tạo, loại file và các thuộc tính do provider cung cấp có giống không?
- **Quyền truy cập:** quyền đọc/ghi/thực thi, chủ sở hữu, ACL có giữ được không?
- **Cấu trúc filesystem:** symbolic link, hard link, thư mục con, extended attributes, sparse files, file đặc biệt có được giữ nguyên không?
- **Tính nguyên tử và nhất quán:** trong lúc copy hoặc nếu copy thất bại, dữ liệu đích có ở trạng thái hoàn chỉnh không?

`java.nio.file.Files.copy(Path, Path, CopyOption...)` là API chuẩn có từ Java 7 và vẫn được dùng trong Java 17+. Nó cho phép sao chép giữa các đường dẫn thuộc **các filesystem provider khác nhau**, nhưng hành vi sao chép **thuộc tính** phụ thuộc vào khả năng thực tế của nguồn, đích và provider.

Ví dụ tối thiểu:

```java
Path result = Files.copy(source, target);
```

Ở đây `source` và `target` là các đối tượng `Path` đã được khai báo; phương thức có thể ném `IOException`.

Mặc định, file thường được sao chép về **nội dung**, còn **không bắt buộc** phải sao chép thuộc tính. Để yêu cầu cố gắng sao chép thuộc tính:

```java
Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);
```

**Điểm quan trọng nhất:** `COPY_ATTRIBUTES` có nghĩa là **“thử sao chép thuộc tính được hỗ trợ”**, không phải cam kết mọi metadata đều giống nguồn trên mọi ổ đĩa, hệ điều hành và filesystem provider.

Trong bài này, chúng ta phân biệt rõ tác dụng của `COPY_ATTRIBUTES`, `REPLACE_EXISTING`, `NOFOLLOW_LINKS`, API kiểm tra thuộc tính, giới hạn cross-filesystem, việc copy thư mục, xử lý lỗi và quy trình kiểm thử. Tất cả đều là kiến thức Java còn hiệu lực; ví dụ độc lập sử dụng JDK 17+.

## 2. Cú pháp `Files.copy` và ba tùy chọn thường gặp

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Files.copy(source, target);

Files.copy(
        source,
        target,
        StandardCopyOption.COPY_ATTRIBUTES);

Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Đây là các **lời gọi minh họa**, cần đặt trong phương thức có xử lý `IOException`. Hai `Path` phải chỉ tới các vị trí mà provider có thể truy cập; đích không được tự động coi là “thư mục cha”, mà là **tên tệp/thư mục đích đầy đủ**.

| Tùy chọn | Ý nghĩa theo API | Không bảo đảm |
| --- | --- | --- |
| Không truyền option | Sao chép file; nếu target đã tồn tại thường thất bại (ngoại lệ khi nguồn/đích là cùng file) | Không bảo đảm copy metadata |
| `StandardCopyOption.COPY_ATTRIBUTES` | Yêu cầu sao chép thuộc tính liên quan file | Không bảo đảm mọi thuộc tính/độ chính xác timestamp đều giữ |
| `StandardCopyOption.REPLACE_EXISTING` | Cho phép thay thế target đã có, theo các điều kiện của API | Không khiến thao tác trở thành atomic |
| `LinkOption.NOFOLLOW_LINKS` | Không theo symbolic link nguồn; khi source là link, cố copy **chính link** | Không bảo đảm provider đích hỗ trợ link/metadata của link |

`NOFOLLOW_LINKS` là `LinkOption`, nhưng có thể được truyền vào `Files.copy(...)` vì `LinkOption` triển khai `CopyOption`. Cần import `java.nio.file.LinkOption` khi dùng.

**Ví dụ một câu lệnh đủ ý định:**

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Câu lệnh này nói: **cho phép thay target hiện có và cố sao chép thuộc tính**. Nó *không* nói: “mọi ACL, owner, quyền POSIX, timestamp, extended attributes chắc chắn giống” hoặc “không ai nhìn thấy trạng thái nửa chừng”.

### 2.1. Các overload của `copy` khác nhau

`Files` còn có:

```java
Files.copy(sourcePath, outputStream);
Files.copy(inputStream, targetPath);
```

Đây là các overload làm việc giữa **byte stream** và file. Chúng phục vụ chuyển nội dung byte; không thể tự suy ra chúng có đầy đủ metadata của một `Path` nguồn, và các tùy chọn/khả năng cũng không giống overload `copy(Path, Path, CopyOption...)`.

Khi mục tiêu có cả **nội dung và thuộc tính**, cần chọn đúng overload `Path → Path` rồi kiểm tra cụ thể thuộc tính đích. Đừng áp `COPY_ATTRIBUTES` cho lời gọi chỉ có `InputStream` và giả định stream có thể cung cấp POSIX/ACL.

## 3. `COPY_ATTRIBUTES` thực sự cam kết điều gì?

Tài liệu chính thức của `Files.copy(Path, Path, CopyOption...)` quy định rõ:

- `COPY_ATTRIBUTES` yêu cầu **attempt**: Java cố sao chép các thuộc tính file liên quan.
- **Tập thuộc tính chính xác được sao chép phụ thuộc platform và filesystem**, không được đặc tả cố định.
- Tối thiểu, thuộc tính **last-modified-time** được sao chép nếu **cả file store nguồn và đích đều hỗ trợ**.
- **Độ chính xác của timestamp có thể giảm** khi chuyển giữa các file store.
- Với **symbolic link** được copy dưới dạng chính link, `COPY_ATTRIBUTES` có thể bị bỏ qua cho metadata của link, tùy implementation.

Điều này đặc biệt quan trọng khi sao chép giữa NTFS, ext4, FAT/exFAT, filesystem mạng, ZIP filesystem hoặc custom provider. **Hai filesystem đều chứa file được** không đồng nghĩa chúng có cùng mô hình metadata.

### 3.1. Những thuộc tính thường muốn bảo toàn

| Nhóm | Ví dụ thuộc tính | Mức có thể trông đợi |
| --- | --- | --- |
| **Basic** | `lastModifiedTime`, `lastAccessTime`, `creationTime` | Có thuộc tính đọc được không đồng nghĩa tất cả đều được copy |
| **POSIX** | `rwxr-x---`, group, owner | Chỉ có trên provider hỗ trợ `posix`; copy không bảo đảm từng quyền được giữ |
| **DOS** | readonly, hidden, system, archive | Không có cùng mô hình trên mọi filesystem |
| **ACL** | Danh sách access control entries, chủ thể/identity | Phụ thuộc provider, danh tính, quyền và chính sách truy cập |
| **User-defined** | Extended attributes / metadata do ứng dụng lưu | Không phải tất cả filesystem đều hỗ trợ; không mặc định được copy |
| **Liên kết** | Symbolic link, hard link, mục tiêu link | Copy file không bảo toàn mọi quan hệ link theo nghĩa giống filesystem gốc |

**Tối thiểu last-modified-time** là một yêu cầu có điều kiện theo đặc tả. Không có câu nào trong API nói `COPY_ATTRIBUTES` nhất định sao chép **mọi** POSIX/ACL/DOS attribute.

### 3.2. Ví dụ yêu cầu copy timestamp

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

Files.setLastModifiedTime(
        source,
        FileTime.from(Instant.parse("2024-01-02T03:04:06Z")));

Files.copy(
        source,
        target,
        StandardCopyOption.COPY_ATTRIBUTES);
```

Đoạn này là **minh họa trong phương thức** có xử lý `IOException`. Việc đặt timestamp bằng `Files.setLastModifiedTime` cũng phụ thuộc quyền/file store. Ví dụ dùng một mốc cố định để dễ kiểm thử thay vì lấy thời gian hiện tại.

Để xem kết quả:

```java
FileTime sourceTime = Files.getLastModifiedTime(source);
FileTime targetTime = Files.getLastModifiedTime(target);

System.out.println(sourceTime);
System.out.println(targetTime);
```

**Đừng viết một unit test khẳng định độ phân giải microsecond/nanosecond phải khớp tuyệt đối giữa mọi filesystem**. Với một số provider, timestamp được làm tròn/cắt về độ phân giải thấp hơn. Điều cần kiểm chứng là **mức độ bảo toàn theo hợp đồng thực sự của đích**, và có chính sách rõ khi hệ thống yêu cầu độ chính xác cao hơn khả năng lưu trữ.

### 3.3. Có phải cứ copy xong là mọi thuộc tính của nguồn giữ nguyên?

Không. `Files.copy` có thể tạo một file mới với quyền/owner do thư mục đích, default ACL, umask hoặc provider quyết định, rồi thử áp một số thuộc tính nguồn. Nếu chính sách bảo mật đòi hỏi một ACL nhất định, ứng dụng phải **thiết lập và kiểm chứng ACL/quyền đích riêng**, thay vì xem `COPY_ATTRIBUTES` là kiểm toán bảo mật đầy đủ.

Việc cố giữ lại quyền nguồn cũng có thể **không phù hợp** với chính sách đích (ví dụ một file private từ máy A cần được bảo vệ theo policy trên máy B). Điều đúng không phải lúc nào cũng là “copy càng nhiều metadata càng tốt”; phải xuất phát từ yêu cầu quyền, audit và format dữ liệu.

## 4. Tìm hiểu thuộc tính bằng `BasicFileAttributes` và `FileTime`

### 4.1. Đọc nhóm basic

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes info = Files.readAttributes(
        path, BasicFileAttributes.class);

System.out.println(info.isRegularFile());
System.out.println(info.size());
System.out.println(info.lastModifiedTime());
System.out.println(info.lastAccessTime());
System.out.println(info.creationTime());
```

Đây là **đoạn minh họa** trong phương thức có xử lý `IOException`, với `path` đã được khai báo.

`BasicFileAttributes` mô tả các thông tin cơ bản mà provider cung cấp. Một số filesystem không hỗ trợ đầy đủ ý nghĩa của từng trường. Đặc biệt **creation time** có thể không có timestamp riêng đáng tin cậy; một số implementation cung cấp giá trị thay thế theo contract của attribute view. Vì vậy, code không được mặc định tất cả file stores có timestamp creation-time chính xác như nhau.

### 4.2. File size không phải toàn bộ câu chuyện

`BasicFileAttributes.size()`/`Files.size(path)` thường diễn tả kích thước **logic** bằng byte. Nó không bảo đảm dung lượng cấp phát vật lý giống nhau khi copy sparse file, file nén, filesystem có deduplication hay metadata riêng.

Với yêu cầu copy **nội dung**, so sánh byte hoặc checksum theo dữ liệu đã mở/đọc. Với yêu cầu bảo toàn sparse allocation hoặc cấu trúc lưu trữ đặc thù, `Files.copy` không hứa làm được trên mọi provider.

### 4.3. Xác nhận source và target bằng thông tin đáng tin

Sau copy, kiểm tra:

```java
boolean sameLogicalSize =
        Files.size(source) == Files.size(target);
```

Điều này hữu ích nhưng **chưa chứng minh hai tệp có cùng byte**. Hai tệp khác nội dung hoàn toàn có thể cùng độ dài.

Với file nhỏ:

```java
boolean equalBytes = java.util.Arrays.equals(
        Files.readAllBytes(source),
        Files.readAllBytes(target));
```

Với file lớn, nên so sánh/đọc luồng theo khối hoặc dùng `MessageDigest` để kiểm tra SHA-256 của nội dung theo chính sách. **Checksum** xác nhận nội dung theo giả định và mô hình tin cậy của ứng dụng, nhưng **không xác nhận** ACL, owner hoặc mọi timestamp.

Java 12+ có `Files.mismatch(path1, path2)` để tìm byte đầu tiên khác nhau mà không cần tự đọc cả file vào RAM; giá trị `-1L` nghĩa là không phát hiện byte khác trong hai file được so sánh. Ví dụ này vẫn nằm trong phạm vi Java 17+.

## 5. Quyền và thuộc tính đặc thù: POSIX, DOS, ACL và metadata người dùng

### 5.1. API attribute view không phải lúc nào cũng sẵn có

JDK có các giao diện:

- `BasicFileAttributeView` và `BasicFileAttributes`: thuộc tính cơ bản.
- `PosixFileAttributeView`: quyền kiểu POSIX, owner/group.
- `DosFileAttributeView`: những cờ metadata kiểu DOS.
- `AclFileAttributeView`: danh sách ACL trên provider hỗ trợ.
- `UserDefinedFileAttributeView`: thuộc tính mở rộng do người dùng/ứng dụng định nghĩa.

`Files.getFileAttributeView(path, PosixFileAttributeView.class)` có thể trả `null` nếu provider **không hỗ trợ** loại view ấy. Đừng lấy kết quả thành công trên Linux rồi giả định một ZIP filesystem hoặc Windows cũng có `posix` theo cùng semantics.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;

PosixFileAttributeView view =
        Files.getFileAttributeView(
                path, PosixFileAttributeView.class);

if (view != null) {
    // Có thể đọc các thuộc tính POSIX theo quyền hiện tại.
    System.out.println(view.readAttributes().permissions());
} else {
    System.out.println("POSIX view is not supported");
}
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException`. Có **view** không đồng nghĩa caller có quyền **ghi mọi thuộc tính**; việc đặt owner, group hoặc ACL có thể bị OS từ chối.

### 5.2. Kiểm tra khả năng của file store

```java
import java.nio.file.FileStore;
import java.nio.file.Files;

FileStore store = Files.getFileStore(path);

boolean posix = store.supportsFileAttributeView("posix");
boolean dos = store.supportsFileAttributeView("dos");

System.out.println("posix=" + posix);
System.out.println("dos=" + dos);
```

**Đầu ra khác nhau giữa các môi trường** nên bài không tuyên bố `posix=true` hoặc `dos=false` cho mọi JDK. Mỗi file store/provider có thể hỗ trợ những tập thuộc tính khác nhau.

Cũng nên phân biệt **attribute view được công bố hỗ trợ** với việc thao tác **đọc/ghi thuộc tính cụ thể** được cấp quyền thành công. Cần catch `IOException`, `SecurityException` hoặc exception phù hợp theo API khi thực sự dùng.

### 5.3. Nếu cần copy một thuộc tính cụ thể

Nếu yêu cầu nghiệp vụ nêu rõ: “tệp mới phải có chính xác lastModifiedTime” hoặc “file chỉ owner được đọc”, đừng dừng ở `COPY_ATTRIBUTES` rồi tự tin rằng đã xong.

Có thể:

1. Đọc thuộc tính nguồn bằng view phù hợp.
2. Tạo/copy target.
3. Kiểm tra provider đích có hỗ trợ view cần thiết.
4. Thử thiết lập thuộc tính đích qua `Files.setLastModifiedTime` hoặc attribute view thích hợp.
5. Đọc lại và so sánh trong **độ chính xác chấp nhận được**.
6. Nếu không thể đáp ứng, xử lý theo contract: **báo lỗi, từ chối publish, hoặc chuyển sang định dạng metadata riêng**.

Không nên cố sao chép **owner/ACL của máy nguồn** sang máy đích khi danh tính người dùng không tương ứng; copy một giá trị metadata kỹ thuật chưa chắc có ý nghĩa về bảo mật.

## 6. Sao chép giữa hai filesystem providers

### 6.1. `Files.copy` cho phép source và target thuộc provider khác nhau

Khác với suy nghĩ “cứ phải cùng một ổ đĩa”, overload `Files.copy(Path, Path, ...)` có thể nhận `Path` của **các filesystem providers khác nhau**. API chính thức nêu rõ `target` có thể liên kết với provider khác `source`.

Ví dụ dùng các khái niệm:

```text
source: Path trong filesystem mặc định (file trên disk)
target: Path trong ZIP filesystem do JDK cung cấp

Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES)
```

Khi source/target khác provider, nội dung có thể được chuyển qua đường triển khai do hai provider hỗ trợ, còn metadata cần được **chuyển nghĩa** theo khả năng của bên đích. Không có cơ chế tổng quát nào khiến POSIX owner, ACL Windows và metadata ZIP trở thành tương đương hoàn toàn.

### 6.2. Ví dụ ZIP filesystem (Java 17+)

`jdk.zipfs` là provider dùng để làm việc với nội dung ZIP như một filesystem. Với JDK đầy đủ có module đó, ta có thể mở một ZIP archive mới:

```java
Path zipFile = workspace.resolve("archive.zip");

try (FileSystem zip = FileSystems.newFileSystem(
        zipFile, Map.of("create", "true"))) {

    Path insideZip = zip.getPath("/copied.txt");
    Files.copy(
            source,
            insideZip,
            StandardCopyOption.COPY_ATTRIBUTES);
}
```

Đây là **đoạn minh họa trong phương thức**, có import `java.nio.file.FileSystem`, `java.nio.file.FileSystems`, `java.util.Map`, `Path`, `Files` và `StandardCopyOption`; `workspace` và `source` đã được tạo.

Tệp ZIP đích phải **chưa tồn tại** hoặc có trạng thái phù hợp với API tạo filesystem ở môi trường đó. Trong ví dụ hoàn chỉnh ở mục 11, `zipFile` là **đường dẫn chưa được tạo** bên trong một thư mục tạm riêng.

**Cần lưu ý:**

- Nếu runtime image đã cắt bỏ module `jdk.zipfs`, ví dụ mở ZIP filesystem có thể không chạy; đó là thiếu provider, không có nghĩa `Files.copy` không hỗ trợ cross-provider.
- Dù `copy` thành công, không suy ra tất cả metadata/permission được bảo toàn khi chuyển từ default filesystem sang ZIP.
- Khi kết thúc `try-with-resources`, `FileSystem.close()` đóng ZIP filesystem; phải quản lý vòng đời và xử lý lỗi đóng.
- Không giả định ZIP provider có cùng `PosixFileAttributeView`, ACL hay cách lưu timestamp với filesystem gốc.

### 6.3. Không dùng kết quả kiểm thử một provider để khẳng định mọi provider

Tài liệu API cho phép các hành vi khác nhau: một provider có thể chỉ copy được một subset thuộc tính, provider khác có thể không hỗ trợ một copy option cụ thể hoặc từ chối vì quyền truy cập.

Nếu một ứng dụng hỗ trợ lưu sang SFTP mount, cloud file gateway, network share hoặc ZIP, cần có **integration test riêng cho những provider thực tế**. Một unit test trên filesystem mặc định không kiểm tra được mọi giới hạn đó.

## 7. Sao chép thư mục: `Files.copy` chỉ tạo thư mục đích rỗng

Một nhầm lẫn phổ biến:

```java
Path sourceDir = Path.of("project");
Path targetDir = Path.of("backup");

Files.copy(sourceDir, targetDir);
```

Nếu source là một **directory**, theo đặc tả `Files.copy(Path, Path, ...)`, thao tác **tạo một thư mục rỗng** ở target; **không copy các entry con**. Không có tùy chọn `COPY_ATTRIBUTES` nào tự biến lời gọi trên thành sao chép cả cây.

### 7.1. Muốn copy đệ quy phải duyệt cây

Dùng `Files.walkFileTree` với `SimpleFileVisitor<Path>`:

```java
static void copyTree(Path sourceRoot, Path targetRoot)
        throws IOException {
    Files.walkFileTree(sourceRoot, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult preVisitDirectory(
                Path dir, BasicFileAttributes attributes)
                throws IOException {
            Path relative = sourceRoot.relativize(dir);
            Path destination = targetRoot.resolve(relative);

            Files.createDirectories(destination);
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attributes)
                throws IOException {
            Path relative = sourceRoot.relativize(file);
            Path destination = targetRoot.resolve(relative);

            Files.copy(
                    file,
                    destination,
                    StandardCopyOption.COPY_ATTRIBUTES);

            return FileVisitResult.CONTINUE;
        }
    });
}
```

Đây là **phương thức minh họa** dùng với nguồn tin cậy, target không tồn tại, cùng các import `Path`, `Files`, `SimpleFileVisitor`, `FileVisitResult`, `BasicFileAttributes`, `StandardCopyOption`, `IOException`. Một ứng dụng sản xuất cần xử lý thêm symbolic link, target đã tồn tại, lỗi, quyền bảo mật, đích nằm bên trong nguồn, quota và xác minh cấu trúc.

**Điểm quan trọng:** Khi tạo thư mục đích bằng `Files.createDirectories`, các thuộc tính riêng của thư mục nguồn **không tự động được giữ**. Nếu cần giữ timestamp của directory, thường phải đặt thuộc tính **sau khi** đã copy nội dung con; việc tạo các entry mới có thể làm thay đổi timestamp của thư mục cha.

### 7.2. Đừng chuyển sourceRoot thành targetRoot nằm trong chính cây nguồn

Nếu copy cây từ `project/` sang `project/backup/` mà không có bảo vệ, traversal có thể gặp lại cây đích đang được tạo, gây lặp hoặc copy tràn dung lượng. Cần đảm bảo target **không là hậu duệ** của source theo mô hình đường dẫn đang dùng, và lưu ý symlink/race.

Đây là bài toán **cây thư mục** chứ không chỉ việc dùng `COPY_ATTRIBUTES`; phải thiết kế rõ trước khi gọi `walkFileTree`.

## 8. Symbolic links: sao chép đích liên kết hay chính liên kết?

### 8.1. Mặc định `Files.copy` theo link nguồn

Với source là symbolic link và provider hỗ trợ, `Files.copy` **mặc định theo link** và sao chép **file mà link trỏ tới**. Target thường là bản sao nội dung file đích của link, **không tự là một symbolic link**.

Nếu mục tiêu là copy **chính symlink**, truyền:

```java
Files.copy(
        sourceLink,
        targetLink,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa trên filesystem hỗ trợ symlink. Trong trường hợp `NOFOLLOW_LINKS`, source link được copy như một link nếu provider hỗ trợ; nếu kết hợp `COPY_ATTRIBUTES`, việc copy metadata của link **có thể bị bỏ qua** tùy implementation.

### 8.2. Target có thể không còn trỏ đến cùng nơi

Một symlink có thể lưu target **tương đối**. Nếu copy chính link sang vị trí khác, chuỗi target của link giữ nguyên nhưng **được diễn giải tương đối với vị trí mới**, có thể trở thành broken link hoặc trỏ đến nơi khác.

Do đó, “copy được symlink” **không đồng nghĩa** bảo toàn cấu trúc tham chiếu theo nghĩa vật lý. Khi di chuyển cả cây filesystem, cần thiết kế rõ có giữ link, theo link hay bỏ qua link.

### 8.3. `REPLACE_EXISTING` gặp symlink đích

Nếu target đã là symbolic link, `REPLACE_EXISTING` thay **bản thân entry link** theo đặc tả, không mặc định ghi đè file vật lý mà link trỏ tới. Điều này khác với suy nghĩ rằng “ghi vào path link tức là sửa file đích của link”.

Với đường dẫn từ nguồn không tin cậy, cần đánh giá symlink traversal và race condition, không xem `NOFOLLOW_LINKS` như một giải pháp sandbox tổng quát cho toàn bộ pipeline I/O.

## 9. `REPLACE_EXISTING` không có nghĩa sao chép nguyên tử

### 9.1. Mặc định target đã tồn tại có thể làm copy thất bại

```java
Path result = Files.copy(source, target);
```

Nếu target đã tồn tại, theo mặc định `Files.copy` thất bại (ngoại lệ khi source/target được xác định là **cùng file**, khi đó copy có thể hoàn tất mà không làm gì). Trên filesystem thông thường, bạn có thể gặp `FileAlreadyExistsException`, nhưng API mô tả loại exception cụ thể đó là **optional specific exception**; hãy xử lý `IOException` theo contract tổng quát.

### 9.2. Có `REPLACE_EXISTING`, target cũ có thể bị thay

```java
Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING);
```

Nếu target là một **non-empty directory**, provider thường không thể thay bằng file nên có thể ném `DirectoryNotEmptyException` hoặc `IOException` khác. Không dùng `REPLACE_EXISTING` mà không kiểm soát overwrite khi target có dữ liệu quan trọng.

Về bảo mật, việc chọn target phải dựa trên những đường dẫn đã được phép ghi; `REPLACE_EXISTING` có khả năng xóa/thay entry ở đích theo điều kiện provider.

### 9.3. File copy không phải atomic

Java API nói rõ:

- `Files.copy(Path,Path,...)` **không phải một thao tác nguyên tử**.
- Nếu copy ném `IOException`, target **có thể đã được tạo nhưng chưa đầy đủ**, hoặc một số metadata chưa được copy.
- Với `REPLACE_EXISTING`, kiểm tra tồn tại và tạo target thay thế **có thể không atomic** so với tác vụ filesystem khác.
- Không có cam kết rằng các bên đọc file luôn chỉ thấy “toàn bộ nội dung cũ” hoặc “toàn bộ nội dung mới” trong quá trình copy.

**Hệ quả vận hành:** nếu copy file cấu hình quan trọng hoặc file dùng bởi tiến trình khác, cần một quy trình publish/replace nhất quán, không chỉ thêm `COPY_ATTRIBUTES` và `REPLACE_EXISTING`.

## 10. Thiết kế copy an toàn hơn: staging, xác minh và publish

Khi người dùng không được phép thấy file đích viết dở, cân nhắc:

1. Tạo **file tạm trong cùng thư mục / cùng filesystem** với target, bằng `Files.createTempFile(...)`.
2. Copy dữ liệu nguồn vào staging, với những tùy chọn metadata phù hợp.
3. Kiểm tra nội dung/thuộc tính cần thiết. Nếu source có thể thay đổi đồng thời, phải có chiến lược snapshot hoặc khóa logic thích hợp.
4. Di chuyển staging thành target bằng `Files.move(..., StandardCopyOption.ATOMIC_MOVE)` **nếu provider hỗ trợ**.
5. Nếu provider không hỗ trợ atomic move, chọn chính sách fallback **có ghi rõ là không atomic**, hoặc trả lỗi nếu atomicity là bắt buộc.
6. Khi copy/move thất bại, dọn staging mà tác vụ sở hữu, không bỏ qua lỗi cleanup.

### 10.1. Mẫu ý tưởng

```java
Path parent = target.toAbsolutePath().getParent();
Path staging = Files.createTempFile(
        parent, ".copy-", ".partial");

try {
    Files.copy(
            source,
            staging,
            StandardCopyOption.REPLACE_EXISTING,
            StandardCopyOption.COPY_ATTRIBUTES);

    // Xác minh nội dung/thuộc tính theo contract tại đây.

    Files.move(
            staging,
            target,
            StandardCopyOption.ATOMIC_MOVE);
} finally {
    Files.deleteIfExists(staging);
}
```

Đây là **mã minh họa, không phải một tiện ích sản xuất hoàn chỉnh**. Điều kiện đầu vào: `target` thuộc một thư mục có thật, có quyền tạo staging; `source` và `target` đã được kiểm tra, cả exception và cleanup cần được quản lý đúng.

Một số điểm phải hiểu rõ:

- Tệp staging vừa được tạo **đã tồn tại**, vì vậy ví dụ dùng `REPLACE_EXISTING` khi copy source vào staging. Nếu chỉ tạo trước rồi gọi `copy(source,staging)` không option, copy có thể bị từ chối vì target đã có.
- `ATOMIC_MOVE` có thể ném `AtomicMoveNotSupportedException`, ví dụ khác file store hoặc provider. Tính nguyên tử và việc target đã tồn tại được xử lý thế nào phụ thuộc implementation theo đặc tả.
- Khi truyền `ATOMIC_MOVE`, các tùy chọn move khác **bị bỏ qua** theo API Java; không mặc định rằng thêm `REPLACE_EXISTING` cùng `ATOMIC_MOVE` sẽ cho một quy tắc ghi đè chung trên mọi provider.
- Nếu `ATOMIC_MOVE` thất bại, đoạn minh họa truyền lỗi, không âm thầm fallback sang một move không atomic.
- `finally` có thể gặp lỗi xóa staging, nên trong ứng dụng thực cần dùng chiến lược quản lý exception/suppressed khi cả việc publish và cleanup đều lỗi.
- `Files.move` không phải bản sao của `Files.copy`: di chuyển nội dung cùng metadata có một hợp đồng khác, và move qua provider khác có giới hạn riêng.

### 10.2. Không thể biến cross-provider copy thành atomic chỉ bằng option

`ATOMIC_MOVE` là tùy chọn của `Files.move`, **không phải `Files.copy`**. Không tồn tại tùy chọn chung `ATOMIC_COPY` cho `Files.copy(Path,Path,...)` trong API chuẩn Java.

Việc copy từ filesystem A sang B có thể yêu cầu stream dữ liệu thực giữa hai nơi lưu trữ. Trong thời gian đó, không thể mặc định rằng người đọc trên B không thấy file đích dở dang.

Staging **ngay ở filesystem đích**, kiểm tra rồi mới publish giúp giảm cửa sổ file chưa hoàn chỉnh mà người đọc bình thường nhìn thấy. Nhưng chiến lược này chỉ cung cấp atomicity nếu **bước publish được provider hỗ trợ atomic theo hợp đồng** và các điều kiện cụ thể được đáp ứng.

## 11. Chương trình Java 17+ đầy đủ: hai providers và các giới hạn thật

Ví dụ này tạo một **thư mục tạm riêng**, sao chép trong filesystem mặc định, rồi tạo một filesystem ZIP bằng `FileSystems.newFileSystem` để copy sang provider khác. Nó chỉ dùng các đường dẫn **tự tạo**; sau khi ZIP filesystem được đóng, toàn bộ workspace tạm được xóa.

Những điều được kiểm tra bằng chương trình:

1. Bản copy cùng filesystem có nội dung bằng nhau và giữ lastModifiedTime trong **môi trường chạy thử**.
2. Copy không option tới target đã có bị từ chối; có `REPLACE_EXISTING` thì cho phép thay.
3. Nguồn và đích trong ZIP có **provider khác nhau**, nhưng nội dung file vẫn được copy.
4. Tệp ZIP có thể đọc được `BasicFileAttributes`; chương trình **không khẳng định mọi POSIX/ACL attribute đều tồn tại** trên ZIP.
5. Gọi `Files.copy(sourceDirectory, targetDirectory)` tạo thư mục đích rỗng, **không copy file con**.
6. Mọi kiểm tra logic quan trọng kết thúc bằng `checks=PASS`.

Tạo tệp **`CopyAttributesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.time.Instant;
import java.util.Arrays;
import java.util.Map;

public final class CopyAttributesDemo {

    static void check(boolean ok, String detail) {
        if (!ok) throw new AssertionError(detail);
    }

    static boolean sameBytes(Path a, Path b) throws IOException {
        return Arrays.equals(
                Files.readAllBytes(a),
                Files.readAllBytes(b));
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException problem)
                    throws IOException {
                if (problem != null) throw problem;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path workspace =
                Files.createTempDirectory("copy-attrs-");

        try {
            Path source = workspace.resolve("source.txt");
            Files.writeString(
                    source, "hello UTF-8",
                    StandardCharsets.UTF_8);

            Files.setLastModifiedTime(
                    source,
                    FileTime.from(Instant.parse(
                            "2024-01-02T03:04:06Z")));

            Path same = workspace.resolve("same.txt");
            Files.copy(
                    source,
                    same,
                    StandardCopyOption.COPY_ATTRIBUTES);

            boolean sameContent = sameBytes(source, same);
            boolean sameTime =
                    Files.getLastModifiedTime(source).equals(
                            Files.getLastModifiedTime(same));

            System.out.println("same.content=" + sameContent);
            System.out.println("same.lastModified=" + sameTime);

            boolean existingRejected = false;
            try {
                Files.copy(source, same);
            } catch (IOException expected) {
                existingRejected = true;
            }
            System.out.println(
                    "existing.rejected=" + existingRejected);

            Files.writeString(
                    same, "old", StandardCharsets.UTF_8);

            Files.copy(
                    source,
                    same,
                    StandardCopyOption.REPLACE_EXISTING);

            System.out.println(
                    "replaced.content=" + sameBytes(source, same));

            Path zipLocation =
                    workspace.resolve("archive.zip");

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipLocation, Map.of("create", "true"))) {

                Path zipTarget = zipFs.getPath("/copied.txt");

                Files.copy(
                        source,
                        zipTarget,
                        StandardCopyOption.COPY_ATTRIBUTES);

                boolean distinctProvider =
                        !source.getFileSystem().provider().getClass()
                            .equals(
                              zipTarget.getFileSystem().provider().getClass());

                System.out.println(
                        "different.provider=" + distinctProvider);
                System.out.println(
                        "cross.content=" + sameBytes(source, zipTarget));

                BasicFileAttributes attrs = Files.readAttributes(
                        zipTarget,
                        BasicFileAttributes.class);

                System.out.println(
                        "cross.regularFile=" + attrs.isRegularFile());

                Path sourceDirectory = Files.createDirectory(
                        workspace.resolve("folder"));

                Files.writeString(
                        sourceDirectory.resolve("child.txt"),
                        "child",
                        StandardCharsets.UTF_8);

                Path zipDirectory = zipFs.getPath("/folder");
                Files.copy(sourceDirectory, zipDirectory);

                System.out.println(
                        "directory.created="
                                + Files.isDirectory(zipDirectory));
                System.out.println(
                        "directory.childCopied="
                                + Files.exists(
                                     zipDirectory.resolve("child.txt")));

                check(distinctProvider
                        && sameContent
                        && sameTime
                        && existingRejected
                        && sameBytes(source, zipTarget)
                        && attrs.isRegularFile()
                        && Files.isDirectory(zipDirectory)
                        && !Files.exists(
                                zipDirectory.resolve("child.txt")),
                      "copy checks failed");
            }

            System.out.println("checks=PASS");
        } finally {
            deleteTree(workspace);
        }
    }
}
```

Biên dịch và chạy với JDK 17+ có ZIP filesystem provider (ví dụ JDK đầy đủ):

```bash
javac -encoding UTF-8 CopyAttributesDemo.java
java CopyAttributesDemo
```

**Stdout đã được chạy kiểm chứng trên filesystem thử nghiệm:**

```text
same.content=true
same.lastModified=true
existing.rejected=true
replaced.content=true
different.provider=true
cross.content=true
cross.regularFile=true
directory.created=true
directory.childCopied=false
checks=PASS
```

### 11.1. Không nên suy rộng output sang mọi filesystem

- `same.content=true`: dữ liệu hai file nhỏ có cùng bytes trong test. Đây là kiểm tra **nội dung**, không phải metadata.
- `same.lastModified=true`: filesystem mặc định của **lần chạy thử** giữ được giá trị thời gian khi copy với `COPY_ATTRIBUTES`. API vẫn cho phép **mất độ chính xác** ở các file stores khác; một chương trình chạy ở provider khác có thể báo `false` mà không nhất thiết vi phạm đặc tả.
- `existing.rejected=true`: copy mặc định tới target đã tồn tại bị từ chối. Bài bắt `IOException` chung thay vì khẳng định provider luôn ném đúng một lớp con cụ thể.
- `replaced.content=true`: `REPLACE_EXISTING` cho phép thay nội dung target đã có trong tình huống này.
- `different.provider=true`: `Path` nguồn và `Path` bên trong ZIP thuộc provider khác loại.
- `cross.content=true`: copy qua ZIP provider bảo toàn bytes. Không có output nào nói **toàn bộ attributes** cũng bằng nhau.
- `cross.regularFile=true`: có thể đọc thuộc tính cơ bản và xác định file trong ZIP; không đồng nghĩa có quyền POSIX hay ACL giống đĩa nguồn.
- `directory.created=true` / `directory.childCopied=false`: chứng minh copy directory **không tự duyệt và sao chép file con**.
- `checks=PASS`: các điều kiện chính được assert; tên tệp tạm do OS sinh ra **không được in ra**.

**Lưu ý môi trường:** Mã cần quyền tạo/xóa thư mục tạm và provider ZIP hoạt động. Nó không chứng minh rằng mọi volume/đĩa mạng/permission đều cho phép `Files.copy` hoặc `Files.setLastModifiedTime` thành công. Với Java runtime image tùy biến thiếu `jdk.zipfs`, chương trình cần được chạy trên JDK có provider này.

### 11.2. Vì sao không in `lastModifiedTime` cố định của ZIP?

Mục tiêu là chứng minh **có thể copy file qua provider** và **không được giả định metadata trùng tuyệt đối**. In `zipTarget.lastModifiedTime == source.lastModifiedTime` rồi assert luôn `true` sẽ biến một chi tiết khả năng/độ chính xác riêng của ZIP provider thành yêu cầu phổ quát sai. Ví dụ chỉ kiểm tra các điều **API thực sự cam kết và provider thử nghiệm đang đáp ứng**.

## 12. Khi nào phải copy metadata thủ công?

Đặt câu hỏi theo yêu cầu thực tế, không theo số lượng thuộc tính mà máy nguồn trả về.

### 12.1. Backup lưu trữ dài hạn

Nếu đây là bản backup cần khôi phục thông tin đầy đủ, metadata có thể là dữ liệu nghiệp vụ:

- Timestamp và độ phân giải theo contract.
- Quyền/ACL/owner hoặc mapping danh tính giữa hai hệ thống.
- Symlink và cấu trúc thư mục, đường dẫn tương đối.
- Extended attributes, metadata của ứng dụng, checksum.
- Hard links và khả năng khôi phục đúng quan hệ nhiều tên tới cùng inode/file.
- Phiên bản/tính nhất quán khi source thay đổi đồng thời.

`Files.copy(...COPY_ATTRIBUTES)` **không phải giải pháp backup đầy đủ** theo mọi ý nghĩa trên. Cần thiết kế định dạng backup, metadata manifest và cơ chế khôi phục theo từng platform/đích lưu trữ.

### 12.2. Publish file cấu hình/asset

Nếu nhu cầu chính là tạo một file cấu hình UTF-8, có thể chỉ cần **nội dung đúng** và quyền đích được cấp theo policy. Việc sao chép owner/ACL nguồn có khi **không cần hoặc không nên**.

Dùng staging ở thư mục đích, kiểm tra bytes, thiết lập quyền cần thiết, publish bằng move nếu hỗ trợ. Khi copy thất bại, không để file nửa chừng được dùng bởi thành phần khác.

### 12.3. Chuyển file sang ZIP hoặc object storage

ZIP có metadata riêng; object storage có thể không có POSIX permission, directory entry hay symlink theo cùng nghĩa. Nếu business yêu cầu giữ metadata, thường cần lưu riêng vào **manifest** (ví dụ JSON có key/type/timestamp/permission mapping rõ ràng) và khi giải nén/khôi phục phải kiểm tra khả năng của nơi đến.

**Không ghi metadata dạng chuỗi platform-specific rồi tuyên bố có thể áp nguyên vẹn lên mọi OS.** Ví dụ chuỗi quyền POSIX không tự biến thành Windows ACL theo một ánh xạ chuẩn chung.

## 13. Xử lý lỗi: không nhầm “đã copy xong” với “đã đạt chuẩn”

### 13.1. Các lỗi điển hình

| Tình huống | Hành vi có thể gặp | Xử lý nên làm |
| --- | --- | --- |
| Source không tồn tại | `NoSuchFileException` hoặc `IOException` tương ứng | Báo lỗi nguồn; không tạo output giả |
| Target đã tồn tại, không dùng replace | `FileAlreadyExistsException` (cụ thể tùy provider) | Dừng hoặc dùng overwrite theo policy đã xác nhận |
| Target là non-empty directory | `DirectoryNotEmptyException`/`IOException` | Không ghi đè cây thư mục ngoài ý muốn |
| Không có quyền ghi | `AccessDeniedException` hoặc `IOException` khác | Kiểm tra quyền, không bỏ qua lỗi |
| Copy attribute đích không hỗ trợ | Có thể không copy đủ, hoặc phát sinh lỗi tùy thuộc trường hợp | Đọc lại metadata quan trọng; có fallback có chủ đích |
| Cross-provider không hỗ trợ option | `UnsupportedOperationException` hoặc lỗi tương ứng | Nhận diện capability, không giả định có |
| Source thay đổi trong lúc copy | Nội dung/metadata có thể không cùng snapshot | Thiết kế snapshot/locking nếu cần nhất quán |
| I/O bị ngắt giữa chừng | Target có thể đã tồn tại nhưng chưa đủ byte | Không publish; kiểm tra và dọn staging |
| Symlink thay đổi đồng thời | Có thể ảnh hưởng file được đọc/ghi thực tế | Kiểm soát root, quyền và race |
| Thiếu ZIP provider | Không mở được ZIP filesystem | Dùng JDK/runtime có provider hoặc chọn storage khác |

### 13.2. Bảo toàn lỗi gốc khi cleanup cũng lỗi

Nếu code copy vào staging thất bại, việc xóa staging trong `finally` cũng có thể ném `IOException`. Nếu không xử lý cẩn thận, lỗi cleanup có thể che lỗi copy gốc.

Có thể gói staging thành một `AutoCloseable` sở hữu tệp tạm, dùng `try-with-resources` để Java gắn lỗi `close()` vào `getSuppressed()` của exception chính. Hoặc xử lý cleanup bằng cấu trúc tương đương, nhưng không nuốt lỗi quan trọng mà không có chính sách rõ.

**Không dùng `Files.deleteIfExists` như bằng chứng “cleanup không thể lỗi”**: nó chỉ bỏ qua tình huống path không tồn tại; các lỗi I/O khác vẫn có thể xảy ra.

## 14. Bảo mật và thuộc tính đích

### 14.1. `COPY_ATTRIBUTES` không phải cơ chế bảo mật quyền truy cập

Một file nguồn có quyền hạn rộng hoặc metadata từ máy khác không nên được “bê nguyên” sang môi trường production. Hãy xác định **quyền tối thiểu** và mapping chủ sở hữu cho môi trường đích.

Nếu yêu cầu là file private, nên đặt quyền trong bước tạo/ghi file hoặc ngay trước publish theo provider hỗ trợ; **không dựa vào thư mục tạm public**, và không tin rằng `COPY_ATTRIBUTES` sẽ tự thay mọi ACL cho đúng.

### 14.2. Race condition trên source/target

Nếu source hoặc target nằm trong thư mục người khác có thể thay đổi, `Files.exists` rồi `Files.copy` không tạo một transaction atomic. Symlink có thể đổi mục tiêu hoặc một entry có thể bị thay bằng file khác giữa các bước.

Với dữ liệu không tin cậy, cần kiểm soát thư mục gốc, chuẩn hóa/kiểm tra path theo policy, giới hạn quyền ở OS và cân nhắc API hạn chế race (như `SecureDirectoryStream` khi provider hỗ trợ). `NOFOLLOW_LINKS` ở **source copy** không tự giải quyết toàn bộ an toàn đường dẫn đích.

### 14.3. Nếu cần xác minh toàn vẹn nội dung

Dùng `Files.mismatch` hoặc checksum đọc từ **file đã được tạo xong**, nhưng hiểu rằng nguồn có thể thay đổi trong lúc kiểm tra. Với transfer đa máy hoặc storage từ xa, nên có manifest/checksum trên một snapshot đã xác định và so kết quả sau copy.

**Phân biệt:** kiểm tra byte đúng ≠ metadata đúng; metadata đúng ≠ permissions đúng; và permissions đúng ≠ đảm bảo không có race.

## 15. Bộ kiểm thử nên có trước khi dùng trong hệ thống thật

### 15.1. Ma trận theo file store/provider

| Ca thử | Cần chứng minh điều gì? |
| --- | --- |
| Cùng filesystem, target mới | Nội dung copy được; metadata yêu cầu được xác nhận |
| Target tồn tại, không replace | Lỗi được báo; target cũ không bị xóa ngoài chính sách |
| Target tồn tại, cho phép replace | Thao tác thay thế đúng theo provider; không mặc định atomic |
| `COPY_ATTRIBUTES` trên cùng provider | Last-modified-time theo độ phân giải đang hỗ trợ |
| `COPY_ATTRIBUTES` sang provider khác | Tính khả dụng/độ chính xác thuộc tính được xác minh |
| Source là directory | Thư mục đích được tạo rỗng, không tự copy entries |
| Copy cây bằng `walkFileTree` | Cây và metadata quan trọng theo contract được bảo toàn |
| Symlink mặc định | Đích được copy, không nhầm thành link |
| `NOFOLLOW_LINKS` | Link entry được copy nếu provider hỗ trợ; link target có ý nghĩa |
| Source bị thay đổi | Có policy snapshot/retry/abort rõ |
| Đĩa đích hết dung lượng | Không công bố file nửa chừng; cleanup staging phù hợp |
| Thuộc tính POSIX/ACL không hỗ trợ | Có báo lỗi hoặc fallback; không suy ra copy thành công là đầy đủ |
| Tệp lớn hoặc sparse | Kiểm tra byte, quota, hiệu năng và kích thước logic |
| ZIP/file store/network thực | Integration test trên từng provider mà sản phẩm cam kết |

### 15.2. Không viết test phụ thuộc chi tiết provider không được đặc tả

Test “copy qua ZIP thì creationTime phải bằng chính xác từng microsecond” dễ trở thành một test **sai hợp đồng**.

Test tốt hơn:

1. Xác định **tập metadata bắt buộc** của ứng dụng.
2. Kiểm tra hai file stores **có khả năng lưu/đọc** những metadata đó.
3. Sao chép bằng `COPY_ATTRIBUTES`.
4. Đọc lại **từng thuộc tính bắt buộc**, so sánh theo độ phân giải và ngữ nghĩa được hỗ trợ.
5. Nếu không hỗ trợ, xác nhận ứng dụng **không âm thầm báo thành công đầy đủ**, mà báo lỗi hoặc dùng fallback phù hợp.

**Tránh một boolean `copied=true` cho cả nội dung, quyền và ACL**. Một đối tượng kết quả có các trạng thái `contentCopied`, `metadataVerified`, `permissionsVerified` có thể rõ hơn khi hệ thống thực sự cần bảo đảm nhiều chiều.

## 16. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Nghĩ `Files.copy` mặc định copy mọi thuộc tính | API không yêu cầu copy attributes mặc định | Truyền `COPY_ATTRIBUTES` khi cần và xác minh |
| Cho rằng `COPY_ATTRIBUTES` giữ nguyên mọi ACL/owner | Tập attrs phụ thuộc filesystem/provider | Kiểm tra capability và thuộc tính đích thực |
| So sánh timestamp chính xác tuyệt đối trên các volume khác nhau | Có thể mất precision | Định nghĩa tolerance/precision theo contract |
| Cho rằng file copy thành công là atomic | `Files.copy` không atomic | Staging + publish move nếu provider hỗ trợ |
| Cho rằng `REPLACE_EXISTING` đồng nghĩa atomic replace | Thay file không bảo đảm nguyên tử | Không dùng cho yêu cầu transaction nếu thiếu publish |
| Cho rằng copy directory sẽ copy mọi file con | Thực tế chỉ tạo thư mục rỗng | `Files.walkFileTree` và visitor |
| Coi `NOFOLLOW_LINKS` và `COPY_ATTRIBUTES` là một bảo đảm symlink metadata | Copy thuộc tính link có thể bị bỏ qua | Kiểm tra provider/symlink theo contract |
| Không phân biệt stream-copy và path-copy | Stream không mang đầy đủ metadata của file nguồn | Dùng đúng overload `Path→Path` |
| Trả về thành công dù copy attribute bắt buộc bị thiếu | App không đạt hợp đồng metadata | Đọc lại từng thuộc tính quan trọng |
| Dựa vào tên file ZIP giống đường dẫn Unix | ZIP là provider với giới hạn riêng | Kiểm thử khả năng thực sự, không suy theo tên |
| So sánh mỗi `Files.size` để kết luận bytes bằng nhau | Hai tệp khác nội dung có thể cùng size | So sánh bytes / `mismatch` / checksum |
| Giữ file nguồn có symlink mutable mà không kiểm soát | Race và dữ liệu không nhất quán | Snapshot/permission/path policy |
| Copy cây vào một nhánh con của chính nguồn | Có nguy cơ lặp hoặc tràn | Kiểm tra root và topology |
| Dọn staging bằng `finally` nhưng làm mất lỗi copy | Cleanup exception có thể che lỗi chính | Dùng suppressed exception/policy phù hợp |
| Không chạy test cross-provider | Chỉ biết hành vi trên một volume | Test volume/provider thật được hỗ trợ |

## 17. Câu hỏi ôn tập

**Câu 1.** `Files.copy(source, target)` có buộc copy cả `lastModifiedTime` không?  
**Đáp án:** Không. Nếu muốn yêu cầu copy metadata, dùng `StandardCopyOption.COPY_ATTRIBUTES`; ngay cả khi đó, khả năng và độ chính xác vẫn phụ thuộc source/target stores.

**Câu 2.** Với `COPY_ATTRIBUTES`, điều gì được đặc tả tối thiểu?  
**Đáp án:** Cố copy `last-modified-time` nếu cả nguồn và đích hỗ trợ. Các attrs khác và độ chính xác timestamp phụ thuộc provider/file store.

**Câu 3.** `NOFOLLOW_LINKS` dùng khi nào?  
**Đáp án:** Khi muốn copy **chính symbolic link** thay vì file mà link trỏ đến, với điều kiện provider hỗ trợ.

**Câu 4.** Có thể dùng `COPY_ATTRIBUTES` để tự động copy ACL Windows sang POSIX hoặc ngược lại không?  
**Đáp án:** Không có bảo đảm chung. Cần mapping quyền, khả năng view và chính sách bảo mật riêng.

**Câu 5.** `Files.copy` có sao chép cây thư mục không?  
**Đáp án:** Không. Với source là thư mục, lời gọi đơn lẻ tạo một thư mục đích **rỗng**; để copy cây phải duyệt `walkFileTree` và xử lý từng entry.

**Câu 6.** Tại sao `REPLACE_EXISTING` không loại bỏ rủi ro file nửa chừng?  
**Đáp án:** File copy không atomic; I/O lỗi có thể để target chưa đủ bytes hoặc thiếu metadata. Replace chỉ là chính sách đối với target đã có.

**Câu 7.** Khi copy qua provider ZIP, byte đúng thì đã đủ chứng minh metadata đúng chưa?  
**Đáp án:** Chưa. Phải đọc lại metadata cần thiết trên ZIP và xác định tập thuộc tính được hỗ trợ.

**Câu 8.** Có thể dùng `ATOMIC_MOVE` cho chính `Files.copy` không?  
**Đáp án:** Không. `ATOMIC_MOVE` là tùy chọn `Files.move`; có thể dùng trong bước publish staging nếu provider hỗ trợ.

**Câu 9.** `FileStore.supportsFileAttributeView("posix")` trả false thì phải làm gì?  
**Đáp án:** Không thực hiện các thao tác yêu cầu POSIX view mà giả định thành công; chọn fallback có tài liệu, mapping khác hoặc báo lỗi theo contract.

**Câu 10.** Copy file từ nguồn sang đích khác provider có được API Java cho phép không?  
**Đáp án:** Có. `Files.copy(Path,Path,...)` cho phép target liên kết với provider khác, nhưng thuộc tính/tùy chọn được hỗ trợ có thể khác.

## 18. Checklist trước khi triển khai

- [ ] Đã phân biệt **copy byte** với **copy metadata/quyền/symlink**.
- [ ] Dùng đúng overload `Files.copy(Path, Path, CopyOption...)`.
- [ ] Đã xác nhận target có thể tồn tại hay không và có được replace không.
- [ ] Nếu cần metadata, yêu cầu `COPY_ATTRIBUTES` và **đọc lại** các attrs bắt buộc.
- [ ] Đã xem xét độ phân giải timestamp khác nhau giữa các file stores.
- [ ] Có kiểm tra `BasicFileAttributes`, khả năng POSIX/DOS/ACL của provider nếu nghiệp vụ cần.
- [ ] Không dùng một boolean copy thành công làm bằng chứng mọi metadata đều đúng.
- [ ] Có chính sách nếu attribute view không hỗ trợ hoặc caller không có quyền đặt thuộc tính.
- [ ] Nếu copy thư mục, đã thiết kế traversal riêng; không ngộ nhận đệ quy tự động.
- [ ] Đã xác định copy symlink hay follow symlink; cân nhắc vị trí mới của relative link.
- [ ] Đã xử lý `IOException` và trạng thái target có thể copy dở.
- [ ] Nếu cần atomic publish, dùng staging ở filesystem đích rồi kiểm tra `ATOMIC_MOVE`.
- [ ] Không dựa vào `REPLACE_EXISTING` để bảo đảm atomic.
- [ ] Có bảo vệ input path, root, symlink và race theo mô hình tin cậy.
- [ ] Có test cùng filesystem và **cross-provider thật** theo danh sách sản phẩm hỗ trợ.
- [ ] Staging/ZIP filesystem/streams được đóng và dọn đúng vòng đời.

## 19. Kết luận và tài liệu chính thức

**`Files.copy(source, target, COPY_ATTRIBUTES)` là yêu cầu thử bảo toàn thuộc tính, không phải lời hứa sao chép toàn bộ ý nghĩa của file trên mọi hệ thống tệp.** File có thể được copy về nội dung nhưng mất ACL, owner, độ chính xác timestamp hoặc tính chất đặc thù khi chuyển sang provider khác.

Để dùng đúng: xác định thuộc tính nào thực sự bắt buộc, kiểm tra provider nguồn/đích, sao chép và **đọc lại target**, xử lý trường hợp metadata không được hỗ trợ, và nhớ `Files.copy` **không nguyên tử** cũng **không đệ quy thư mục**. Với dữ liệu cần tính nhất quán cao, xây dựng quy trình staging/verify/publish dựa trên khả năng filesystem đích.

### Tài liệu tham khảo Oracle/OpenJDK hiện hành

- [Java SE 17 — `java.nio.file.Files.copy(Path,Path,CopyOption...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#copy(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `NOFOLLOW_LINKS`, copy thư mục, symlink và copy không atomic.
- [Java SE 17 — `java.nio.file.StandardCopyOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): enum các tùy chọn `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `ATOMIC_MOVE`.
- [Java SE 17 — `java.nio.file.FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): xác minh khả năng của file store, `supportsFileAttributeView`.
- [Java SE 17 — `java.nio.file.attribute.BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): các metadata cơ bản và điều kiện hỗ trợ.
- [Java SE 17 — `java.nio.file.attribute.FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html): thời điểm file và độ phân giải.
- [Java SE 17 — `java.nio.file.Files.move`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): `ATOMIC_MOVE` và các giới hạn khi publish/replace.
- [Java SE 17 — `java.nio.file.FileSystems.newFileSystem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): tạo filesystem từ ZIP/JAR qua provider được cài đặt.