# ProviderMismatchException, FileSystemNotFoundException và ClosedFileSystemException trong Java NIO.2

## 1. Bối cảnh: một `Path` luôn thuộc về một `FileSystem`

Java NIO.2 (`java.nio.file`) không giới hạn ở đĩa máy tính: một `FileSystem` có thể biểu diễn hệ thống tệp mặc định, nội dung ZIP/JAR (Zip File System), hoặc hệ thống tệp ảo do thư viện cung cấp. `FileSystemProvider` là thành phần hiện thực các thao tác truy cập; `Path` được tạo bởi một `FileSystem` cụ thể và mang theo quan hệ này.

```text
FileSystemProvider (cách hiện thực I/O)
        |
        +-- FileSystem (một thể hiện đang mở / vòng đời truy cập)
                |
                +-- Path (đường dẫn thuộc đúng FileSystem đó)
```

Ví dụ:

- `Path.of("report.txt")` thường thuộc file system mặc định, có provider scheme `file`.
- `zipFs.getPath("/report.txt")` thuộc một file system ZIP/JAR đã mở bằng `FileSystems.newFileSystem(...)`, có provider scheme `jar`.
- Hai `Path` nhìn giống chuỗi ký tự không có nghĩa chúng cùng provider hoặc cùng file system.
- `FileSystems.getDefault()` lấy hệ thống tệp mặc định, do JVM quản lý. File system mặc định không đóng được; một file system ZIP hoặc provider tùy chỉnh thường phải đóng khi dùng xong.

Ba ngoại lệ trong bài có nguyên nhân khác nhau: **trộn đối tượng từ provider không tương thích**; **tra cứu file system không tồn tại trong ngữ cảnh truy cập**; **dùng file system đã đóng**. Nắm được nguồn gốc `Path` và vòng đời `FileSystem` giúp chẩn đoán chính xác.

## 2. Bảng phân biệt nhanh

| Ngoại lệ | Nhóm ngoại lệ | Nguyên nhân điển hình | Hành động đúng |
| --- | --- | --- | --- |
| `ProviderMismatchException` | `IllegalArgumentException` → `RuntimeException` | API yêu cầu `Path` cùng provider nhưng nhận `Path` do provider khác tạo | Kiểm tra nguồn `Path`; tạo `Path` phụ trợ bằng cùng `FileSystem`, hoặc dùng API hỗ trợ truyền dữ liệu qua providers |
| `FileSystemNotFoundException` | `RuntimeException` | Cần một `FileSystem` theo URI nhưng chưa có thể hiện tương ứng; hoặc phép chuyển URI không tìm/tạo tự động được file system | Kiểm tra URI, provider, và bước mở/mount file system trước khi truy xuất |
| `ClosedFileSystemException` | `IllegalStateException` → `RuntimeException` | Gọi thao tác truy cập qua `Path` thuộc `FileSystem` đã đóng | Đảm bảo truy cập nằm trong thời gian file system còn mở; không giữ `Path` để dùng sau khi chủ sở hữu đóng |

Cả ba là **unchecked exceptions**: không bắt buộc khai báo `throws` trong chữ ký. Chúng khác `IOException`, `NoSuchFileException`, và `AccessDeniedException` vốn phản ánh các lỗi I/O hoặc truy cập cụ thể. Không nên gom mọi lỗi liên quan đến đường dẫn thành “file không tồn tại”.

## 3. `ProviderMismatchException`: trộn đường dẫn của các provider

### 3.1. Điều kiện xảy ra

`ProviderMismatchException` được ném khi một phương thức hoạt động trên đối tượng do provider A tạo nhưng nhận đối số do provider B tạo mà phương thức ấy yêu cầu cùng provider. Một tình huống quen thuộc là kết hợp `Path` của file system mặc định với `Path` của Zip File System trong phép `resolve(Path)` hoặc `relativize(Path)`.

Ví dụ ý tưởng:

```java
Path hostPath = Path.of("logs");       // Provider file mặc định
Path zipPath = zipFs.getPath("a.txt"); // Provider jar của ZipFS

hostPath.resolve(zipPath);             // Không tương thích provider
```

Đây là đoạn minh họa trong một phương thức; `zipFs` phải là `FileSystem` ZIP đã mở. Trên provider file/ZipFS chuẩn trong JDK, lời gọi `resolve(Path)` này gây `ProviderMismatchException`.

**Không kết luận rằng mọi API có hai `Path` đều từ chối khác provider.** Ví dụ, `Files.copy(source, target)` hỗ trợ sao chép giữa các provider, mặc dù thuộc tính, tính nguyên tử và tùy chọn hỗ trợ phụ thuộc provider. Phải đọc hợp đồng API cụ thể.

### 3.2. Cách nhận diện

```java
System.out.println(hostPath.getFileSystem().provider().getScheme());
System.out.println(zipPath.getFileSystem().provider().getScheme());
System.out.println(hostPath.getFileSystem() == zipPath.getFileSystem());
```

Thông thường hai scheme là `file` và `jar`; phép so sánh identity giúp nhận biết hai đối tượng `FileSystem` có cùng thể hiện hay không. **Scheme giống nhau chưa chứng minh hai `FileSystem` là cùng một instance**: một provider có thể quản lý nhiều file system, chẳng hạn các kho ZIP khác nhau.

### 3.3. Cách sửa mà vẫn giữ đúng ngữ nghĩa

Nếu muốn tính đường dẫn con **nằm trong ZIP**, dùng một `Path` tạo bởi ZIP:

```java
Path zipBase = zipFs.getPath("/docs");
Path zipChild = zipBase.resolve("lesson.txt");  // resolve(String) theo provider của zipBase
```

Nếu cần `Path` ở filesystem mặc định, tạo bằng `Path.of(...)`, `FileSystems.getDefault().getPath(...)`, hoặc `hostBase.resolve("name")`. Không dùng `Path.toString()` rồi `Path.of(...)` để “chuyển” file nằm trong ZIP sang file thật: chuỗi `/docs/lesson.txt` chỉ là tên đường dẫn, không chứa nội dung hay ngữ cảnh ZIP.

Nếu muốn **di chuyển dữ liệu** giữa file system, cân nhắc `Files.copy(zipEntry, hostFile)` hoặc `Files.newInputStream(zipEntry)` kết hợp với output stream ở đích, theo nhu cầu dữ liệu và ngoại lệ I/O. Nếu muốn **tương đối hóa** hai đường dẫn, bảo đảm chúng thuộc cùng hệ thống tệp và có ràng buộc root phù hợp trước khi `relativize`.

## 4. `FileSystemNotFoundException`: không tìm được file system cần truy xuất

### 4.1. Khác biệt giữa “file thiếu” và “file system chưa được mở”

`FileSystemNotFoundException` không phải thông báo rằng `docs/report.txt` bị xóa. Nó liên quan đến **việc tìm một file system**, chẳng hạn gọi:

```java
FileSystems.getFileSystem(uri);
```

`getFileSystem(URI)` chỉ **tra cứu một file system đang tồn tại** do provider nhận diện qua scheme trong URI. Nó không có nhiệm vụ tạo file system mới. Đối với ZipFS, nếu file system cho URI đó chưa được mở, provider ZIP chuẩn ném `FileSystemNotFoundException`.

```java
URI zipFsUri = URI.create("jar:file:///path/to/archive.zip");

// Chưa gọi FileSystems.newFileSystem(zipFsUri, ...):
FileSystems.getFileSystem(zipFsUri); // Có thể ném FileSystemNotFoundException
```

Đường dẫn `jar:file:///path/to/archive.zip` là minh họa định dạng URI, không phải đường dẫn di động trên mọi OS. Trong code thực tế, tạo URI từ `archive.toUri()` để tránh sai ký tự, dấu cách hoặc phân cách Windows.

`Path.of(URI)` có quy tắc riêng: nó nhờ provider chuyển URI thành `Path`, và có thể ném `FileSystemNotFoundException` khi không tìm/tự tạo được file system, **hoặc khi không có provider cho scheme**. Trong khi đó, `FileSystems.getFileSystem(URI)` có thể ném `ProviderNotFoundException` nếu provider tương ứng chưa được cài. Những API và điều kiện khác nhau không nên bị gộp thành một.

### 4.2. `getFileSystem`, `newFileSystem`, `getDefault`

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `FileSystems.getDefault()` | Lấy file system mặc định của JVM | Không phải API mount ZIP/JAR |
| `FileSystems.getFileSystem(uri)` | Tìm file system đã tồn tại theo URI | Không tự tạo; khi chưa tồn tại có thể `FileSystemNotFoundException` |
| `FileSystems.newFileSystem(uri, env)` | Yêu cầu provider tạo/mở file system theo URI | Có thể `IOException`, `ProviderNotFoundException`, `FileSystemAlreadyExistsException` hoặc lỗi cấu hình |
| `Path.of(uri)` | Chuyển URI thành `Path` qua provider | Một số provider cho phép tự tạo file system; một số cần mount trước |
| `Files.exists(path)` | Kiểm tra một đường dẫn cụ thể | `false` không có nghĩa file system provider không tồn tại |

Muốn dùng URI đến mục bên trong ZIP sau khi file system được mở, `Path.of(jarEntryUri)` đôi khi phù hợp, nhưng cú pháp URI là đặc thù provider. Cách rõ ràng hơn trong code đang quản lý ZipFS là giữ đối tượng `FileSystem` và dùng `zipFs.getPath("/inside.txt")`.

### 4.3. Không xử lý bằng cách mở lặp vô điều kiện

`newFileSystem` cũng không phải hàm idempotent “đảm bảo có file system”: nếu file system theo URI đã có và provider quy định chỉ được một instance, có thể ném `FileSystemAlreadyExistsException`. Khi một ứng dụng có nhiều thành phần sử dụng chung ZIP FS, cần chỉ định rõ **ai tạo, ai giữ và ai đóng**. Tránh cách chữa lỗi bằng việc bắt mọi exception rồi gọi `newFileSystem` hoặc đóng đối tượng do thành phần khác sở hữu.

## 5. `ClosedFileSystemException`: sử dụng file system sau khi đóng

`FileSystem` mở khi được tạo. Với các file system có thể đóng như ZIP FS, gọi `close()` giải phóng tài nguyên của instance đó. Sau khi đóng, những thao tác truy cập qua các `Path` liên quan có thể ném `ClosedFileSystemException`.

Mẫu lỗi phổ biến:

```java
Path saved;
try (FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of())) {
    saved = zipFs.getPath("/report.txt");
}
// zipFs đã close: saved vẫn là một đối tượng Path
Files.readString(saved); // ClosedFileSystemException với ZipFS chuẩn
```

Đoạn này minh họa phạm vi tài nguyên; giả định `zipUri` trỏ tới một ZIP đã tồn tại. Việc `Path` còn tham chiếu được **không chứng minh file system của nó vẫn mở**. Chưa chắc `toString()` hoặc truy cập tên cú pháp trên `Path` luôn ném ngoại lệ, nhưng các thao tác I/O đòi file system đang hoạt động.

**Không thể “mở lại” một instance đã đóng bằng `isOpen()`.** Có thể phải tạo một `FileSystem` instance mới qua provider (nếu được hỗ trợ) và dựng lại `Path` từ instance mới. Không tiếp tục dùng `Path` cũ đã lấy từ instance cũ.

### 5.1. Bẫy try-with-resources

Sai ngữ cảnh:

```java
static Path locate(FileSystem zipFs) {
    return zipFs.getPath("/data.txt");
}
```

Hàm trên chỉ trả `Path`; caller cần bảo đảm `zipFs` còn sống đến khi hoàn tất I/O. Nếu có code đóng zipFs trước khi caller dùng kết quả, lỗi nằm ở **quản lý vòng đời**, không nằm ở `locate` hay cú pháp đường dẫn.

Một thiết kế dễ kiểm soát hơn là mở và xử lý nội dung trong cùng phạm vi:

```java
static String readEntry(FileSystem zipFs) throws IOException {
    return Files.readString(zipFs.getPath("/data.txt"));
}
```

`readEntry` vẫn yêu cầu caller giữ `zipFs` mở trong lúc gọi. Một phương án khác là thành phần sở hữu ZipFS thực hiện toàn bộ I/O, sau đó trả nội dung hoặc dữ liệu đã tách khỏi vòng đời ZipFS. Không nên trả stream, iterator hoặc `Path` dài hạn mà không tài liệu hóa lifecycle.

### 5.2. Mặc định và custom provider

`FileSystems.getDefault().close()` không dùng để “refresh”: file system mặc định không thể đóng. Với các provider tùy chỉnh, quy tắc chia sẻ, cache, mở lại và đóng có thể khác, nhưng hợp đồng file system đóng vẫn quan trọng. Đừng nhầm `ClosedFileSystemException` với `ClosedWatchServiceException`, vì watch service có vòng đời riêng.

## 6. Ví dụ Java 17+ chạy được: cả ba ngoại lệ trong cùng chương trình

Chương trình này dùng **ZIP File System** có sẵn trong bản phân phối JDK chứa module `jdk.zipfs`. Nó tạo một ZIP mới trong thư mục tạm; chưa mount thì thử tra cứu; mount rồi trộn `Path` của hai provider; đóng ZipFS rồi thử đọc mục cũ. Ví dụ tự xóa tài nguyên do nó tạo.

Tạo file `FileSystemExceptionsDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.ClosedFileSystemException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class FileSystemExceptionsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-provider-");
        Path archive = dir.resolve("sample.zip");

        // Tạo một URI jar: từ URI chuẩn hóa của file ZIP thật.
        URI zipUri = URI.create("jar:" + archive.toUri());
        Path zipEntry = null;

        try {
            // Case 1: file system ZIP mới này chưa được mở.
            try {
                FileSystems.getFileSystem(zipUri);
                System.out.println("already mounted");
            } catch (FileSystemNotFoundException ex) {
                System.out.println("before mount: FileSystemNotFoundException");
            }

            // Mở ZIP; try-with-resources sẽ đóng ZipFS ở cuối block.
            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                zipEntry = zipFs.getPath("/lesson.txt");
                Files.writeString(zipEntry, "Hello ZIP");
                System.out.println("zip content: " + Files.readString(zipEntry));

                // Case 2: Path mặc định + Path ZipFS ở phép resolve(Path).
                Path hostDir = Path.of("local");
                Path zipRelative = zipFs.getPath("relative.txt");
                try {
                    hostDir.resolve(zipRelative);
                    System.out.println("resolved unexpectedly");
                } catch (ProviderMismatchException ex) {
                    System.out.println("mixed resolve: ProviderMismatchException");
                }

                System.out.println("zip open: " + zipFs.isOpen());
            }

            // Case 3: Path còn tồn tại trong bộ nhớ nhưng ZipFS đã đóng.
            try {
                Files.readString(zipEntry);
                System.out.println("read unexpectedly");
            } catch (ClosedFileSystemException ex) {
                System.out.println("after close: ClosedFileSystemException");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file nguồn:

```bash
javac FileSystemExceptionsDemo.java
java FileSystemExceptionsDemo
```

Kết quả dự kiến với JDK 17+ chuẩn có `jdk.zipfs`, quyền ghi thư mục tạm và không có can thiệp đồng thời:

```text
before mount: FileSystemNotFoundException
zip content: Hello ZIP
mixed resolve: ProviderMismatchException
zip open: true
after close: ClosedFileSystemException
```

Diễn giải theo thời điểm:

1. URI `jar:` xác định file system cho file ZIP mới; `getFileSystem` chỉ tìm instance đã mở nên báo `FileSystemNotFoundException`.
2. `newFileSystem(..., Map.of("create", "true"))` mở ZipFS và tạo archive; `Files.writeString` và `Files.readString` thực hiện I/O qua `zipEntry` hợp lệ.
3. `hostDir.resolve(zipRelative)` nhận `Path` thuộc provider `jar` trong khi `hostDir` thuộc provider `file`, nên có `ProviderMismatchException` trong triển khai JDK file + ZipFS.
4. Thoát `try` đóng ZIP. `zipEntry` vẫn tồn tại dưới dạng đối tượng Java, nhưng `Files.readString(zipEntry)` truy cập vào ZipFS đã đóng và báo `ClosedFileSystemException`.
5. Khối `finally` dọn ZIP và thư mục tạm sau khi giải phóng ZipFS. Lỗi môi trường như không đủ quyền, thiếu module `jdk.zipfs`, hoặc I/O hỏng có thể khiến chương trình ném ngoại lệ khác và không in đủ các dòng trên.

**Chú ý:** chương trình minh họa sử dụng cùng ZIP FS ở một luồng. Nếu nhiều luồng hoặc thư viện cùng thao tác trên ZIP, cần quy định ownership để không đóng một file system trong lúc thành phần khác còn đang đọc.

## 7. Cùng một triệu chứng nhưng ba hướng sửa khác nhau

Giả sử code xử lý ZIP qua nhiều tầng service:

```text
Request -> URI hoặc Path -> chọn FileSystem -> đọc entry
                           |                   |
                           |                   +-- đã close -> ClosedFileSystemException
                           +-- chưa mount / tra cứu sai -> FileSystemNotFoundException
         +-- trộn host Path với zip Path -> ProviderMismatchException
```

Với `ProviderMismatchException`, bước đầu là kiểm tra `path.getFileSystem()` và `path.getFileSystem().provider()` trên từng đối số. Nếu ý đồ là thao tác cú pháp trong ZIP, tạo đối số qua ZIP FS. Nếu ý đồ là sao chép nội dung, dùng API truyền dữ liệu được đặc tả hỗ trợ khác provider.

Với `FileSystemNotFoundException`, kiểm tra URI `scheme`, thời điểm mount, đường dẫn kho chứa và `FileSystems.getFileSystem` có đang dùng đúng URI mà `newFileSystem` từng nhận không. Không lập tức sửa bằng cách `Files.createFile`: file entry và file system là hai tầng khác nhau.

Với `ClosedFileSystemException`, xác định lời gọi `close()`, `try-with-resources`, hoặc component dọn cache xảy ra trước I/O. Đừng chỉ bắt ngoại lệ rồi retry cùng `Path`: nó vẫn trỏ tới instance đã đóng.

## 8. Phân biệt với các ngoại lệ dễ nhầm

| Ngoại lệ khác | Khi nào đáng nghi | Phân biệt |
| --- | --- | --- |
| `NoSuchFileException` | Đường dẫn đích không tồn tại khi thao tác I/O | File system có thể đang mở và hoạt động; chỉ thiếu mục tệp |
| `ProviderNotFoundException` | Chưa có provider cho URI scheme trong API tìm/mở provider | Khác với đã có provider nhưng chưa tạo file system instance |
| `FileSystemAlreadyExistsException` | Mở mới một file system theo URI đã được mount, khi provider không cho instance trùng | Ngược chiều với lookup file system chưa có; không có nghĩa entry đã tồn tại |
| `FileSystemException` | Lỗi hệ thống tệp trong thao tác cụ thể | Là `IOException` có thể mang file, otherFile và reason; không phải đồng nghĩa với closed/mismatch |
| `IllegalArgumentException` / `InvalidPathException` | URI hoặc cú pháp đường dẫn không hợp lệ | Lỗi định dạng/tiền điều kiện, cần kiểm tra dữ liệu đầu vào |
| `ClosedWatchServiceException` | Dùng `WatchService` đã đóng | Vòng đời watch service khác vòng đời `FileSystem` |

Đặc biệt, **`ProviderMismatchException` là một dạng `IllegalArgumentException`**. Nếu muốn xử lý riêng trường hợp mismatch, đặt `catch (ProviderMismatchException)` trước `catch (IllegalArgumentException)` (nếu cần cả hai); ngược lại Java báo catch con không thể tới được.

## 9. Thiết kế dịch vụ truy cập nhiều file system

### 9.1. Quy định ownership

Đối với một chức năng đọc tài liệu từ ZIP, có thể chọn:

- Mỗi thao tác tự mở ZIP, đọc toàn bộ dữ liệu cần dùng, đóng trước khi trả kết quả.
- Một component chuyên trách quản lý một ZIP FS dùng chung; mọi người sử dụng thông qua component và chỉ component này được đóng khi không còn tác vụ đang dùng.
- API trả dữ liệu độc lập như `byte[]`, `String` hoặc DTO sau khi đã đọc xong; nếu trả stream hoặc `Path`, phải xác định ai giữ tài nguyên mở và đóng lúc nào.

Dùng `try-with-resources` cho instance do chính phạm vi đó tạo, nhưng **không tự ý đóng** một file system mà caller đưa vào. Hạn chế lưu `Path` ZipFS trong singleton lâu hơn vòng đời ZipFS.

### 9.2. Giữ nhất quán nguồn của `Path`

Một method tiếp nhận đường dẫn trong ZIP nên nhận `FileSystem` hoặc một `Path` ZIP làm gốc; tạo con bằng `root.resolve("name")` để theo cùng provider. Nếu cần đích ngoài ZIP, truyền vào một `Path` host riêng và gọi thao tác có hỗ trợ cross-provider, thay vì ghép cơ học `host.resolve(zipPath)`.

Tránh dùng `toString()` để suy ra provider hoặc dùng `Path.of(...) ` để chuyển đổi tùy tiện. `Path.toUri()` mang nhiều ngữ cảnh hơn chuỗi tên, nhưng URI vẫn phải được xử lý qua provider/file system phù hợp; không phải phép “đổi provider” phổ quát.

### 9.3. Phân biệt các tầng khi ghi log

Khi có lỗi, thông tin hữu ích gồm: tên thao tác, scheme của provider, URI định danh file system (nếu có và phù hợp), tình trạng `isOpen()`, loại đối số `Path`, và stack trace. Tránh log thông tin nhạy cảm hoặc nguyên văn đường dẫn bí mật ở mức log công khai. Chỉ dùng `Files.exists()` để chẩn đoán entry nếu thực sự cần; nó không thay thế đánh giá trạng thái file system.

## 10. Checklist xử lý sự cố

1. **Đang gọi API nào?** `resolve`/`relativize`, `getFileSystem`/`Path.of(URI)`, hay thao tác đọc/ghi như `Files.readString`?
2. **`Path` được sinh ra ở đâu?** `Path.of` của host, `zipFs.getPath`, hay thư viện provider khác?
3. **Hai đối số có thuộc cùng provider không?** Nếu không, xác minh API có cho phép cross-provider.
4. **Provider có được cài không?** Nếu thiếu scheme, xem `ProviderNotFoundException` hoặc hợp đồng phương thức gọi.
5. **File system đã được tạo/mount chưa?** `getFileSystem` không tạo mới; cần bước `newFileSystem` phù hợp.
6. **File system đã bị đóng chưa?** Kiểm tra `isOpen()` khi còn giữ reference và rà soát ownership/try-with-resources.
7. **Có race với luồng khác?** Trạng thái có thể đổi sau khi kiểm tra; bảo đảm thời gian sử dụng không chồng lấn với lúc close.
8. **Kết quả sửa có đúng nghiệp vụ?** Nếu phải copy dữ liệu từ ZIP ra host, dùng copy; nếu xây đường dẫn trong ZIP, tạo con qua chính ZIP FS; nếu cần lookup, đảm bảo mount tồn tại.

## 11. Bài tập kiểm tra hiểu biết

**Bài 1.** Hai `Path` in cùng `"/a.txt"`. Có thể đưa chúng vào bất kỳ `resolve(Path)` nào không?

**Đáp án:** Không. Chuỗi biểu diễn giống nhau không chứng minh chúng cùng provider; kiểm tra `getFileSystem()`/provider và hợp đồng API.

**Bài 2.** Một file `archive.zip` thật tồn tại trên đĩa, nhưng `FileSystems.getFileSystem(zipUri)` ném `FileSystemNotFoundException`. Vì sao?

**Đáp án:** File ZIP tồn tại không có nghĩa một instance ZipFS ứng với URI đó đang được mount. `getFileSystem` tra cứu instance; `newFileSystem` mới là API tạo/mở.

**Bài 3.** Sau `try (FileSystem fs = ...)`, biến `Path p = fs.getPath("/x")` còn khác `null`. Có thể gọi `Files.readString(p)` không?

**Đáp án:** Không thể trông đợi thành công vì `p` gắn với file system đã đóng; ZipFS chuẩn ném `ClosedFileSystemException`.

**Bài 4.** Có thể `Files.copy(zipEntry, hostTarget)` khi hai `Path` thuộc providers khác nhau không?

**Đáp án:** Có; `Files.copy` có hợp đồng hỗ trợ khác provider. Vẫn cần xử lý `IOException`, tùy chọn có thể không hỗ trợ hoặc có ngữ nghĩa khác, và bảo đảm ZipFS mở trong toàn bộ thao tác.

**Bài 5.** Nếu `newFileSystem(uri, env)` gặp `FileSystemAlreadyExistsException`, có nên ngay lập tức đóng instance đã tồn tại không?

**Đáp án:** Không. Phải xác định chủ sở hữu và chính sách sử dụng chung; đóng có thể phá các thao tác đang chạy ở thành phần khác.

## Tài liệu chuẩn

- Java SE 21, `ProviderMismatchException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ProviderMismatchException.html
- Java SE 21, `FileSystemNotFoundException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemNotFoundException.html
- Java SE 21, `ClosedFileSystemException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedFileSystemException.html
- Java SE 21, `FileSystems`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html
- Java SE 21, `FileSystem`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html
- Java SE 21, `Path`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
