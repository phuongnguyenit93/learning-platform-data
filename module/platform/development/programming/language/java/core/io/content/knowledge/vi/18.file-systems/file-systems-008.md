# Giới hạn chuyển sang `File` và giả định về đường dẫn vật lý trong Java NIO.2

## 1. Bài toán: một `Path` không nhất thiết là đường dẫn tệp vật lý

Trong Java, hai kiểu được dùng phổ biến để biểu diễn tên đường dẫn:

- `java.io.File`: API cũ, biểu diễn **tên đường dẫn trừu tượng** của hệ thống tệp mặc định. Đối tượng `File` có thể đại diện cho một mục chưa tồn tại; tạo `new File("abc.txt")` không tạo tệp.
- `java.nio.file.Path`: API NIO.2, biểu diễn một đường dẫn thuộc **một `FileSystem` cụ thể**, do `FileSystemProvider` quản lý. `Path` có thể thuộc hệ thống tệp mặc định hoặc provider khác, như hệ thống tệp bên trong tệp ZIP/JAR.

Một số mã cũ nhận `File` và khiến người học nghĩ rằng mọi `Path` đều có thể chuyển thành `File`. Giả định đó sai:

```java
Path p = /* một Path được nhận từ bên ngoài */;
File file = p.toFile(); // Có thể ném UnsupportedOperationException!
```

Đoạn trên chỉ minh họa chữ ký; `p` phải được cung cấp bởi caller. `Path.toFile()` chỉ hỗ trợ `Path` gắn với **default file-system provider**. Một `Path` trỏ tới entry bên trong ZIP vẫn đọc được bằng `Files.readString(path)` nhưng không thể chuyển trực tiếp thành `File`.

Mục tiêu của bài: nhận biết ranh giới tương thích giữa `File` và `Path`, phân biệt đường dẫn logic với tài nguyên trên đĩa, và thiết kế mã xử lý file không vô tình loại bỏ mọi file-system provider ngoài mặc định.

## 2. Mô hình `Path → FileSystem → FileSystemProvider`

`Path` không tự chứa nội dung tệp. Nó mang tên đường dẫn và tham chiếu đến một hệ thống tệp, còn provider thực hiện thao tác I/O tương ứng.

```text
Path (đường dẫn có ngữ nghĩa của FileSystem)
  ├── FileSystem mặc định (file:)
  │     └── đường dẫn OS, thư mục, ổ đĩa, mount ...
  │            ↳ thường chuyển được Path.toFile()
  │
  ├── ZIP/JAR FileSystem (jar:)
  │     └── mục /docs/readme.txt trong archive.zip
  │            ↳ Files.readString() được; Path.toFile() không được
  │
  └── FileSystem provider tùy biến
        └── hệ thống tệp trong bộ nhớ / mạng / mô hình riêng
               ↳ chỉ dùng tính năng provider hỗ trợ
```

Có thể quan sát ranh giới này:

```java
Path path = Path.of("notes.txt");
FileSystem fileSystem = path.getFileSystem();
System.out.println(fileSystem.provider().getScheme()); // "file" ở provider mặc định thông thường
```

*Đoạn minh họa độc lập trong một phương thức/chương trình có các import phù hợp.* Kết quả scheme của default provider thông thường là `file`. Tuy nhiên, phương thức có thể phụ thuộc vào cấu hình default provider và môi trường; **không dùng riêng chuỗi scheme hoặc tên lớp provider làm một bằng chứng chắc chắn rằng dữ liệu nằm trên đĩa cục bộ**.

Một phân biệt quan trọng:

- **Default provider**: provider tích hợp với hệ thống tệp mặc định của JVM; có thể nhìn thấy ổ đĩa vật lý, ổ mạng, network mount, thư mục được mount hoặc môi trường container.
- **Physical/local file**: kết luận về vị trí và bản chất lưu trữ. `File`, `Path` và tên scheme `file` không bảo đảm dữ liệu thực sự ở ổ đĩa cục bộ, luôn tồn tại, có thể ghi hoặc là tệp thường.

Do đó, tính tương thích với `File` và tính “vật lý” là **hai câu hỏi khác nhau**.

## 3. Quy tắc của `Path.toFile()`

Theo API Java SE, `Path.toFile()` trả về `java.io.File` đại diện cho đường dẫn này **nếu `Path` gắn với default provider**. Trường hợp khác, phương thức ném:

```text
java.lang.UnsupportedOperationException
```

Đối với default provider, thao tác tương đương tạo một `File` từ biểu diễn chuỗi của `Path`. Không có yêu cầu đối tượng được tạo phải trỏ đến tệp đã tồn tại.

### 3.1. Trên hệ thống tệp mặc định

```java
import java.io.File;
import java.nio.file.Path;

Path path = Path.of("docs", "guide.txt");
File legacy = path.toFile();

System.out.println(legacy.getPath().equals(path.toString()));
```

Đây là đoạn minh họa; trên default provider thông thường, kết quả là `true`. Nó cho thấy **biểu diễn tên đường dẫn**, không chứng minh `guide.txt` tồn tại.

Các nhận định đúng:

- `Path.of("docs", "guide.txt")` dùng **default FileSystem**.
- `path.toFile()` thực hiện chuyển đối tượng đối với provider mặc định.
- `path` có thể là tương đối hoặc tuyệt đối, và `File` mới không tự động làm nó tuyệt đối.
- Không có bước đọc tệp hoặc kiểm tra sự tồn tại chỉ vì gọi `toFile()`.

### 3.2. Với provider khác

```java
// zipEntry lấy từ zipFs.getPath("/docs/guide.txt").
Files.readString(zipEntry); // Có thể đọc được nếu entry tồn tại.
zipEntry.toFile();           // UnsupportedOperationException.
```

Đây là mã minh họa dùng `zipEntry` và `zipFs` từ ZIP file system đã mở. Lỗi là do **không có phép biểu diễn tương đương bằng `java.io.File`**, không phải bằng chứng entry không tồn tại. Ngay cả khi `zipEntry.isAbsolute() == true` hoặc `Files.exists(zipEntry) == true`, `toFile()` vẫn không được hỗ trợ trên ZIP provider.

### 3.3. `File.toPath()` và chiều chuyển ngược

`File.toPath()` cung cấp `Path` của tên đường dẫn thuộc hệ thống tệp mặc định:

```java
File oldApiFile = new File("logs/app.log");
Path nioPath = oldApiFile.toPath();
```

Cách chuyển từ `File` sang `Path` phù hợp khi di chuyển dần từ API cũ sang `Files`. Nhưng đừng kết luận tính đối xứng cho mọi `Path`: một ZIP `Path` không có `File` tương ứng, nên không có phép chuyển hai chiều tổng quát. Ngay cả `file.toPath().toFile()` cũng không được API bảo đảm bằng `equals` với `file` ban đầu trong mọi trường hợp; hãy kiểm tra điều kiện nghiệp vụ thay vì dùng đẳng thức đối tượng làm bằng chứng.

## 4. Ví dụ Java 17+ chạy được: cùng thao tác `Files`, hai provider

Chương trình tạo một tệp tạm trên hệ thống tệp mặc định và một kho ZIP tạm. Nó ghi một entry vào ZIP, đọc entry bằng `Files` rồi thử `toFile()`.

**Tệp nguồn:** `PathToFileLimitDemo.java`

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class PathToFileLimitDemo {
    public static void main(String[] args) throws IOException {
        Path regularFile = Files.createTempFile("default-fs-", ".txt");
        Path zipArchive = Files.createTempFile("virtual-fs-", ".zip");

        // ZIP provider với create=true cần một tên archive chưa tồn tại.
        Files.delete(zipArchive);

        try {
            Files.writeString(regularFile, "outside ZIP");

            System.out.println("default conversion: "
                    + regularFile.toFile().isFile());

            URI zipUri = URI.create("jar:" + zipArchive.toUri());

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path zipEntry = zipFs.getPath("/docs/readme.txt");
                Files.createDirectories(zipEntry.getParent());
                Files.writeString(zipEntry, "inside ZIP");

                System.out.println("ZIP content: "
                        + Files.readString(zipEntry));

                System.out.println("same provider: "
                        + (zipEntry.getFileSystem().provider()
                        == FileSystems.getDefault().provider()));

                try {
                    zipEntry.toFile();
                    System.out.println("unexpected conversion");
                } catch (UnsupportedOperationException ex) {
                    System.out.println(
                            "ZIP conversion: UnsupportedOperationException");
                }
            }
        } finally {
            Files.deleteIfExists(regularFile);
            Files.deleteIfExists(zipArchive);
        }
    }
}
```

Biên dịch và chạy với **JDK 17+ chuẩn có module `jdk.zipfs`**:

```bash
javac PathToFileLimitDemo.java
java PathToFileLimitDemo
```

Kết quả dự kiến:

```text
default conversion: true
ZIP content: inside ZIP
same provider: false
ZIP conversion: UnsupportedOperationException
```

**Giải thích từng bước:**

1. `Files.createTempFile` tạo tệp thật trong file system mặc định; sau khi tạo và ghi thành công, `regularFile.toFile().isFile()` trả `true`.
2. `zipArchive` là tên tệp archive thuộc default provider. Mã xóa vỏ tệp ZIP rỗng vì `jdk.zipfs` cần tạo archive hợp lệ.
3. `FileSystems.newFileSystem(zipUri, Map.of("create", "true"))` mở ZIP dưới dạng một `FileSystem` riêng. Định dạng URI `jar:...` và tùy chọn `create` là quy ước của ZIP provider.
4. `zipFs.getPath("/docs/readme.txt")` biểu diễn **entry bên trong archive**, không phải `/docs/readme.txt` ở root hệ điều hành.
5. `Files.createDirectories`, `Files.writeString`, `Files.readString` làm việc trực tiếp qua ZIP provider: in `inside ZIP`.
6. ZIP provider không phải default provider nên hai biểu thức sau đúng theo thứ tự: so sánh provider là `false`, gọi `zipEntry.toFile()` ném `UnsupportedOperationException`.
7. `try-with-resources` đóng ZIP file system để hoàn tất thay đổi lên archive; `finally` xóa các tệp tạm. Không dùng `zipEntry` để truy cập archive sau khi đóng `zipFs`.

Nếu runtime được đóng gói tối giản và không chứa `jdk.zipfs`, thao tác mở ZIP sẽ thất bại do thiếu provider; đó là điều kiện môi trường, không phải thay đổi quy tắc `Path.toFile()`. Chương trình cố ý không giấu lỗi khởi tạo ZIP dưới một output mặc định “thành công”.

### 4.1. Vì sao `new File(zipEntry.toString())` là cách sửa sai?

Ví dụ `zipEntry.toString()` có thể chỉ là `/docs/readme.txt`. Nếu gọi:

```java
File misleading = new File(zipEntry.toString());
```

`misleading` bây giờ chỉ một tên đường dẫn trong **default filesystem**, có thể là một mục hoàn toàn khác, thậm chí có thể trùng với tệp thật ngoài ZIP. Không có Java API nào tự động “giải nén và đổi sang physical path” khi nhận chuỗi trên. Sai lầm nguy hiểm nhất ở đây là thao tác **không ném lỗi** nhưng chuyển sang **khác tài nguyên**.

## 5. Cẩn thận với “đường dẫn tuyệt đối”, “chuẩn hóa” và “đường dẫn thực”

Ba thao tác này thường bị hiểu nhầm là cách “ép” `Path` thành đường dẫn vật lý:

| Phương thức | Điều nó làm | Điều nó không bảo đảm |
|---|---|---|
| `path.toAbsolutePath()` | Tạo đường dẫn tuyệt đối theo ngữ nghĩa của **file system hiện tại** | Không chứng minh tồn tại, không chuyển provider |
| `path.normalize()` | Loại bỏ phần tử tên dư như `.` / `..` theo quy tắc provider, chủ yếu xử lý cú pháp | Không yêu cầu I/O, không đảm bảo trỏ đến cùng mục nếu có symlink |
| `path.toRealPath()` | Yêu cầu đường dẫn hiện hữu và xác định đường dẫn thực theo provider, mặc định theo symlink | Không chuyển ZIP `Path` thành `File`, không có “physical path” chung mọi provider |
| `path.toUri()` | Tạo URI đại diện cho `Path` theo provider | Không chứng minh URI là `file:`, cũng không tự đổi thành `File` |
| `path.toString()` | Biểu diễn văn bản tên đường dẫn | Không mang đủ ngữ cảnh provider để tái dựng đường dẫn tổng quát |

Ví dụ:

```java
Path virtual = zipFs.getPath("/docs/../docs/readme.txt");
Path normalized = virtual.normalize();
Path absolute = normalized.toAbsolutePath();
Path real = normalized.toRealPath();
```

Đoạn minh họa cần `zipFs` còn mở và entry tồn tại. `normalized`, `absolute` và `real` vẫn là đường dẫn do ZIP provider quản lý. Một `Path` *absolute* ở ZIP root không biến thành đường dẫn tuyệt đối ở ổ C: hoặc Linux root. `toRealPath()` có thể ném `IOException` khi mục không tồn tại hoặc không thể truy cập; không dùng nó như phép cast.

**Đặc biệt với symlink:** `normalize()` thuần cú pháp có thể thay đổi đối tượng được tham chiếu. Chẳng hạn `dirLink/../target.txt` không nhất thiết đồng nghĩa với `target.txt` nếu `dirLink` là symbolic link trỏ sang thư mục khác. `toRealPath()` tra cứu hệ thống tệp và có tùy chọn `LinkOption.NOFOLLOW_LINKS`; tuy vậy nó vẫn trả `Path` thuộc provider gốc. Một lần `toRealPath()` cũng không đảm bảo đường dẫn không đổi trước thao tác I/O sau đó.

### 5.1. “Thực” không đồng nghĩa “cục bộ”

Ngay cả với `Path.of("/mnt/share/report.csv")` trên Linux, thư mục `/mnt/share` có thể được mount từ ổ đĩa mạng; trên Windows, ổ đĩa hoặc UNC path cũng có thể trỏ đến tài nguyên mạng. Trong container, tên đường dẫn có thể được map từ máy host. Do đó:

- `path.toFile()` thành công: **có phép chuyển tương thích với API cũ**.
- `Files.exists(path)` hoặc `Files.isRegularFile(path)` thành công: **có thể truy vấn trạng thái đối tượng theo provider tại thời điểm đó**.
- Không phương thức nào trong hai nhóm chứng minh vị trí lưu trữ là ổ đĩa vật lý cục bộ, được sở hữu độc quyền, hay không thể thay đổi bởi tác nhân khác.

## 6. `Path.of(...)`, `FileSystem.getPath(...)` và `Path.resolve(...)`

Khi viết thư viện nhận một `Path` từ caller, bạn cần bảo toàn ngữ cảnh provider thay vì vô tình ép lại vào default provider.

**Cách dễ gây lỗi:**

```java
static Path childBad(Path base, String filename) {
    return Path.of(base.toString(), filename);
}
```

`Path.of(String, String...)` luôn dùng default file system. Nếu `base` nằm trong ZIP hoặc provider khác, phương thức trên trả đường dẫn trong default provider và làm mất ý nghĩa ban đầu.

**Cách phù hợp:**

```java
static Path childGood(Path base, String filename) {
    return base.resolve(filename);
}
```

`base.resolve(filename)` dùng ngữ nghĩa của file system tạo ra `base`. Điều này thường là cách viết tốt nhất cho thư viện xử lý một cây thư mục có root do người gọi cung cấp.

Có thể chọn đường dẫn từ file system cụ thể:

```java
Path defaultPath = Path.of("docs", "guide.txt");
Path zipPath = zipFs.getPath("/docs", "guide.txt");
```

`defaultPath` luôn đến từ default FileSystem; `zipPath` đến từ `zipFs`. Đoạn minh họa yêu cầu `zipFs` đã mở. Nếu muốn thao tác giữa hai provider, dùng API được thiết kế cho việc đó (chẳng hạn `Files.copy` hỗ trợ sao chép giữa provider theo contract của nó), không hoán đổi các `Path` vào phép toán yêu cầu cùng một FileSystem, và không giả định mọi thuộc tính metadata có thể sao chép đầy đủ.

### 6.1. So sánh đường dẫn phải giữ ngữ cảnh

Hai `Path` đều in ra `/docs/readme.txt` không có nghĩa chúng biểu diễn cùng tệp. Một cái có thể là root Linux, một cái là entry trong ZIP. `Path.equals` tuân theo cách định nghĩa của provider; `Files.isSameFile` cần truy cập đối tượng và có thể không hỗ trợ mọi tổ hợp hoặc thất bại I/O. Không dùng duy nhất `toString()` như khóa định danh đa-provider.

## 7. URI cũng là tên tài nguyên, không phải vé thông hành sang `File`

`Path.toUri()` thuận tiện để biểu diễn đường dẫn với scheme:

```java
URI uri = somePath.toUri();
System.out.println(uri.getScheme());
```

Đoạn minh họa với `somePath` đã được khai báo. URI của `Path` mặc định thường có scheme `file`; ZIP file system thường dùng scheme `jar` với cú pháp ghép URI dành riêng provider. Vì vậy:

- `new File(URI)` chỉ nhận dạng URI phù hợp với contract của `java.io.File` (đặc biệt scheme `file` và những ràng buộc URI cụ thể). `new File(zipEntry.toUri())` **không** chuyển nội dung ZIP thành tệp hệ điều hành; có thể ném `IllegalArgumentException` vì scheme không hợp lệ.
- `Path.of(URI)` chọn provider theo scheme URI nếu được cài đặt và có thể mở/lấy file system phù hợp. Một URI thuộc provider khác có thể cần file system đã được khởi tạo. Thiếu provider/file system có thể phát sinh `FileSystemNotFoundException` hoặc lỗi khác của contract.
- `Path.of(somePath.toString())` không tương đương `Path.of(somePath.toUri())`: phiên bản chuỗi dùng default provider, còn phiên bản URI tra cứu provider theo scheme.
- Mỗi provider quyết định phần lớn ngữ nghĩa URI của mình. Đừng tự ghép scheme `file:` trước một đường dẫn tùy ý với hy vọng chuyển provider.

Một thiết kế API tốt là truyền **`Path` hoặc `URI` có ngữ cảnh** khi cần đa-provider, thay vì mã hóa mọi thứ thành chuỗi path mặc định.

## 8. Giải pháp khi thư viện cũ chỉ nhận `java.io.File`

Trong thực tế, có thư viện legacy đưa ra API kiểu:

```java
static void legacyImport(File input) {
    // Ví dụ chữ ký API cũ: chỉ biết java.io.File.
}
```

Giả sử caller cung cấp `Path input` bất kỳ. Có ba hướng xử lý tùy nhu cầu:

### 8.1. Ưu tiên API `Path`, `InputStream` hoặc `ReadableByteChannel`

Nếu thư viện có overload dùng `Path` hoặc `InputStream`, hãy dùng dạng thích hợp:

```java
static String loadText(Path source) throws IOException {
    return Files.readString(source);
}
```

Phương thức này làm việc với mọi provider triển khai thao tác đọc tương ứng; nó không cần `toFile()`. Nếu bên nhận chỉ cần bytes, có thể truyền `Files.newInputStream(source)` và quản lý vòng đời stream rõ ràng. Điều này bảo toàn nơi lưu trữ gốc và tránh file trung gian.

### 8.2. Chỉ chuyển trực tiếp khi có hỗ trợ

Nếu đã biết contract nghiệp vụ là đường dẫn từ default provider, có thể gọi:

```java
File legacyFile = input.toFile();
legacyImport(legacyFile);
```

Đây là minh họa với `input` là một `Path` hợp lệ; caller phải quyết định cách xử lý `UnsupportedOperationException` nếu có thể nhận path ngoài default provider. `toFile()` **không** tự xác nhận file có thể đọc/ghi; thư viện legacy cần xử lý lỗi I/O thực tế.

### 8.3. Nếu buộc phải có file vật lý: staging copy tạm

Khi thư viện thực sự chỉ hỗ trợ `File`, có thể chủ động **sao chép nội dung** sang tệp tạm thuộc default provider. Ví dụ đầy đủ cho chiều đọc:

```java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyBridge {
    @FunctionalInterface
    public interface FileConsumer {
        void accept(File file) throws IOException;
    }

    public static void withStagedFile(
            Path source, FileConsumer consumer) throws IOException {
        Path staging = Files.createTempFile("legacy-", ".bin");

        try {
            Files.copy(source, staging,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            consumer.accept(staging.toFile());
        } finally {
            Files.deleteIfExists(staging);
        }
    }
}
```

Đây là **thư viện hỗ trợ có thể biên dịch** (`LegacyBridge.java`), không có `main` và không in stdout; ví dụ caller phải cung cấp `FileConsumer`. Mã trên minh họa trường hợp nguồn có thể đọc được, không nhất thiết là tệp thường, và consumer chỉ đọc staging file.

Những điều phải thiết kế rõ trước khi áp dụng trong production:

- `staging` là **bản sao**, không còn là cùng đối tượng với source. Đường dẫn, thuộc tính, owner, file key và cập nhật sau đó có thể khác.
- Consumer sửa staging file **không tự cập nhật** entry gốc. Nếu nghiệp vụ cần ghi ngược, phải có luồng đồng bộ riêng, điều kiện lỗi và khả năng xung đột rõ ràng.
- Việc sao chép có chi phí bộ nhớ đệm, I/O, dung lượng đĩa, và có thể thất bại với tài nguyên lớn hoặc quyền hạn chế.
- `createTempFile` chỉ chọn nơi lưu tạm mặc định; chính sách quyền, thư mục staging, dọn dẹp khi process chết, xử lý thông tin nhạy cảm và tránh race cần được thiết kế theo ứng dụng.
- Consumer không được giữ `File` để dùng **sau khi callback kết thúc** vì đoạn `finally` sẽ xóa staging file. Không trả `File` ra ngoài rồi xóa ngay lập tức.
- Nếu code thực sự cần tương tác trực tiếp với hệ thống tệp trong archive hoặc provider đặc biệt, hãy thay thư viện/adapter bằng API `Path` thay vì ngụy tạo một tên file mặc định.

## 9. Trường hợp thường gặp và nhận định đúng

| Tình huống | Có thể `toFile()`? | Điểm cần hiểu |
|---|---|---|
| `Path.of("hello.txt")` trên default provider | Có | Tên có thể tương đối và file có thể chưa tồn tại |
| `Paths.get("/tmp/hello.txt")` trên default provider Unix | Có | “Tuyệt đối” không xác nhận file tồn tại |
| `File("hello.txt").toPath()` | Có theo default provider | Thuận lợi khi hiện đại hóa API cũ |
| ZIP/JAR entry lấy từ `zipFs.getPath(...)` | Không, ném `UnsupportedOperationException` | Dữ liệu nằm trong một file system riêng |
| Path từ provider bên thứ ba | Không theo contract nếu không phải default provider | Có thể hỗ trợ `Files` nhưng không chuyển thành `File` |
| `zipEntry.toRealPath()` | Không | `toRealPath()` vẫn giữ provider |
| `Path` mặc định tới ổ đĩa mạng hoặc mount | Có | Không kết luận file nằm trên ổ cứng cục bộ |
| `Path.of(zipEntry.toString())` | Có vì tạo Path mới trên default provider | **Nguy cơ đổi sang một đối tượng khác**, không phải chuyển ZIP entry |

**Lưu ý thiết kế:** Nếu chương trình thực sự yêu cầu tệp thường tồn tại để đọc, biểu diễn đúng nhất là *thử đọc rồi xử lý kết quả/lỗi* (hoặc đọc metadata theo yêu cầu); không lấy thành công của `toFile()` làm điều kiện tồn tại.

## 10. Ngoại lệ và những nhầm lẫn phổ biến

### 10.1. Các loại lỗi khác nhau

- `UnsupportedOperationException` từ `Path.toFile()`: provider không tương thích với `File`. Không đồng nghĩa “file không tồn tại”.
- `NoSuchFileException`, `AccessDeniedException` hoặc `IOException` từ `Files`: lỗi khi truy cập tài nguyên theo contract I/O của provider.
- `FileSystemNotFoundException` hoặc `ProviderNotFoundException` từ API tạo/lấy file system theo URI: provider hoặc phiên file system cần thiết không có.
- `ClosedFileSystemException`: thao tác dùng file system đã đóng (đặc biệt với ZIP system được quản lý qua `try-with-resources`).
- `InvalidPathException` từ `Path.of(String)`: chuỗi không phù hợp quy tắc parser của default provider.
- `ProviderMismatchException`: đưa `Path` của provider không tương thích vào thao tác yêu cầu cùng provider (tùy API).

Đừng gom tất cả thành “sai đường dẫn” vì cách khắc phục khác nhau. Khi bắt ngoại lệ, phải biết API nào phát sinh và có nên thử nguồn khác, báo lỗi người dùng hay dừng nghiệp vụ.

### 10.2. Danh sách lỗi tư duy cần tránh

1. **“Có `Path` tức có file thật.”** `Path` có thể trỏ tới tên không tồn tại, ZIP entry hoặc nguồn đặc biệt.
2. **“`toFile()` là một phép cast luôn thành công.”** Nó chỉ hỗ trợ default provider.
3. **“`toAbsolutePath()` biến đường dẫn thành physical path.”** Nó chỉ chuyển thành đường dẫn tuyệt đối *trong cùng FileSystem*.
4. **“`normalize()` hoặc `toRealPath()` đổi provider.”** Hai phương thức giữ provider gốc; ngữ nghĩa và I/O khác nhau.
5. **“`new File(path.toString())` tương đương `path.toFile()`.”** Với provider khác, bản `File` mới âm thầm trỏ vào default filesystem.
6. **“URI có chữ `file` ở đâu đó là đủ.”** File URI, jar URI, URI ghép và cú pháp provider riêng là những cơ chế khác nhau.
7. **“Chuỗi slash giống nhau tức cùng file.”** Cần xét provider và trạng thái thật; tên có thể giống nhưng tài nguyên khác.
8. **“`File` là file vật lý và luôn tồn tại.”** `File` cũng chỉ là tên trừu tượng; phương thức kiểm tra không loại trừ thay đổi đồng thời.
9. **“Bản staging copy giữ nguyên định danh/metadata.”** Copy được dữ liệu theo policy, nhưng không còn cùng đối tượng và cần bảo đảm dọn dẹp.
10. **“Mở ZIP xong có thể dùng mãi `Path` trong ZIP.”** Đóng `FileSystem` làm nhiều thao tác truy cập tiếp theo không còn hợp lệ.

### 10.3. Thiết kế giao diện thư viện

Đối với một hàm chỉ cần đọc dữ liệu, ưu tiên:

```java
String read(Path source) throws IOException;
```

Với một hàm chỉ xử lý luồng byte và không cần tên tệp, đôi khi API:

```java
void parse(java.io.InputStream input) throws IOException;
```

là đủ; caller sẽ tự mở/đóng stream theo contract. Với hệ thống đa-provider, **không** gắn giả định default provider vào logic sâu bằng cách gọi `Path.of(input.toString())` hoặc `new File(input.toString())`. Giữ nguyên `Path` từ caller và thao tác `resolve`/`Files` theo provider của nó.

## 11. Tự kiểm tra

1. **Đúng hay sai?** `Path.of("foo.txt").toFile()` chỉ thành công nếu `foo.txt` tồn tại.  
   **Sai.** `toFile()` là chuyển biểu diễn trên default provider, không kiểm tra tồn tại.
2. **Điều gì xảy ra?** `zipFs.getPath("/images/a.png").toFile()`?  
   **`UnsupportedOperationException`**, vì ZIP `Path` không thuộc default provider, cho dù entry tồn tại.
3. **Có thể sửa bằng cách nào?** `new File(zipEntry.toString())`?  
   **Không.** Điều đó diễn giải chuỗi trên default filesystem và có thể trỏ sang đối tượng khác.
4. **Một `Path` trả từ `toRealPath()` có chắc chuyển được thành `File` không?**  
   **Không.** `toRealPath()` vẫn trả đường dẫn trong provider gốc.
5. **Nếu một thư viện chỉ nhận `File` nhưng đầu vào là ZIP entry?**  
   Ưu tiên overload nhận `Path` hoặc `InputStream`; nếu bắt buộc, chép dữ liệu sang staging file ở default provider với vòng đời và đồng bộ riêng.
6. **Một `File` từ đường dẫn mạng có phải file cục bộ?**  
   Không thể kết luận chỉ từ loại `File`/`Path`; default provider có thể truy cập các mount và chia sẻ mạng.
7. **Cần ghép tên tệp con vào `Path base` chưa rõ provider?**  
   Dùng `base.resolve(child)` để giữ ngữ nghĩa file system của `base`.

## 12. Ghi nhớ và tài liệu chính thức

Nguyên tắc trọng tâm: **`Path` thuộc một file system; `java.io.File` thuộc mô hình đường dẫn truyền thống của default provider. `Path.toFile()` chỉ là cầu nối cho default provider, không phải phép biến mọi nguồn dữ liệu thành tệp vật lý.** Nếu nhu cầu là xử lý nội dung, hãy ưu tiên `Files`/`Path`/stream. Nếu bắt buộc tương tác với API legacy, xác định có chuyển trực tiếp được không hoặc dùng staging copy có kiểm soát.

Tài liệu tham khảo chính thức (Java SE 21):

- `Path` — đặc biệt `toFile`, `toUri`, `toRealPath` và `Path.of`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
- `FileSystems` — default provider và mở file system mới: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html
- `Files` — I/O qua `Path`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- `File` — tên đường dẫn trừu tượng và `toPath`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/File.html
- Module `jdk.zipfs` — ZIP/JAR FileSystem Provider: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.zipfs/module-summary.html
