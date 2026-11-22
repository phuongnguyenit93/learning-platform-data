# Java 7 — Path: Khác biệt cú pháp và nhà cung cấp giữa các nền tảng

## 1. Mục tiêu và bức tranh chung

`java.nio.file.Path` (thuộc NIO.2, có từ Java 7) là giao diện mô tả **vị trí một tệp hoặc thư mục trong một hệ thống tệp cụ thể**. Bề ngoài, các đối tượng Path đều có các phương thức quen thuộc như `getRoot()`, `getFileName()`, `resolve()`, `normalize()`, `toUri()` hay `toAbsolutePath()`. Tuy nhiên, **cùng một đoạn ký tự không nhất thiết là cùng một đường dẫn trên Windows, Linux, macOS hoặc một file system provider khác**.

Có hai nguồn khác biệt cần tách bạch:

1. **Cú pháp và ngữ nghĩa đường dẫn của hệ thống tệp:** dấu phân cách, root, ổ đĩa, đường dẫn mạng UNC, chữ hoa/thường, tên bị cấm, symbolic link, tên `.` và `..`, cùng cách giải nghĩa đường dẫn tương đối/tuyệt đối.
2. **Nhà cung cấp hệ thống tệp (*FileSystemProvider*):** mã Java tạo, phân tích cú pháp và thực hiện I/O cho Path. Một chương trình có thể sử dụng **default provider `file`** và một provider khác, chẳng hạn **`jar`/ZIP filesystem** trong cùng JVM. Không phải mọi Path đều tương ứng trực tiếp với tệp trên ổ đĩa của OS.

Mục tiêu thực hành: viết code Java 17+ dùng `Path` an toàn và dễ chuyển nền tảng, hiểu khi nào một giả định về Windows/Linux **không hợp lệ**, biết cách lấy Path từ đúng provider và nhận diện giới hạn của các phép so sánh/ghép/đổi đường dẫn.

**Thông tin phiên bản:** `Path`, `FileSystem`, `FileSystems` và `FileSystemProvider` đã là API Java từ Java 7 và vẫn áp dụng hiện nay. Một số factory hiện đại như `Path.of(...)` được thêm từ **Java 11**, `Map.of(...)` từ Java 9, `Files.readString/writeString` từ Java 11. Ví dụ chính yêu cầu **Java 17+**, không khuyến khích quay lại sử dụng JDK cũ.

## 2. Path là cấu trúc thuộc một FileSystem, không đơn thuần là String

Một đường dẫn có thể có **root** và các **name elements**:

```text
Ví dụ kiểu UNIX: /home/app/data/report.txt
  root:       /
  name[0]:    home
  name[1]:    app
  name[2]:    data
  name[3]:    report.txt

Ví dụ tương đối: data/reports/q1.csv
  root:       null
  name[0]:    data
  name[1]:    reports
  name[2]:    q1.csv
```

Đây là minh họa **cấu trúc** theo một provider kiểu UNIX; Windows có quy tắc root/drive/UNC riêng.

Một Path gắn với một `FileSystem`, truy xuất bằng:

```java
Path path = Path.of("data", "reports", "q1.csv");

FileSystem fs = path.getFileSystem();
System.out.println(fs.provider().getScheme());
```

Đây là **snippet đặt trong một phương thức** với import `java.nio.file.Path` và `java.nio.file.FileSystem`. Trên default filesystem thông thường, scheme của provider là `file`. Nếu Path đến từ ZIP filesystem, scheme có thể là `jar`. **Không thể kết luận provider chỉ từ tên class `Path`**, bởi `Path` là interface và implementation do provider tạo.

Những đặc điểm của `Path`:

- **Immutable:** `resolve`, `normalize`, `relativize`... trả Path kết quả, không sửa Path nguồn.
- **Không cần tệp tồn tại:** `Path.of("missing.txt")` tạo được đối tượng Path dù chưa có file.
- **Không tự thực hiện I/O:** việc tạo/ghép Path thường là thao tác cú pháp; `Files.readString`, `Files.copy`, `Files.move`, `toRealPath` mới truy cập filesystem và có thể thất bại.
- **Cú pháp tùy provider:** phân tách tên, biểu diễn root, quy tắc equality/order và một số cách resolve có thể khác.
- **Provider là một phần của hợp đồng:** không phải mọi Path đều chuyển được sang `java.io.File` hoặc dùng được với cùng bộ thuộc tính filesystem.

## 3. Cách tạo Path portable từ các thành phần

Trên JDK 17+:

```java
Path report = Path.of("workspace", "reports", "2026", "q1.csv");
```

Đây là snippet trong phương thức đã import `java.nio.file.Path`. Ưu điểm của truyền **từng thành phần** cho `Path.of(first, more...)` là để provider mặc định chọn dấu phân cách phù hợp. Code không cần chắp chuỗi:

```java
String fragile = "workspace" + "/" + "reports" + "/" + "2026" + "/" + "q1.csv";
```

Cách ghép String có thể tạo một đường dẫn không được provider hiểu như dự kiến, đặc biệt khi mang cú pháp Windows trên UNIX hoặc ghép ZIP path với `File.separator` của host OS.

**Quy tắc thực hành:**

- Với các tên thành phần do ứng dụng xác định, dùng `Path.of("dir","file.txt")` hoặc `base.resolve("file.txt")`.
- Với một Path đã thuộc provider khác, tiếp tục tạo các thành phần từ **chính `FileSystem` đó**: `zipFs.getPath("docs","info.txt")`, hoặc `zipRoot.resolve("docs").resolve("info.txt")`.
- Không tự coi `/` và `\` là hai dấu phân cách có thể thay thế trên **mọi provider**.
- Không truyền một path tuyệt đối do người dùng kiểm soát vào `trustedRoot.resolve(userPath)` rồi cho rằng nó bị “nhốt” dưới root: với đối số absolute, `resolve` thường trả chính đối số đó.

### 3.1. Path.of và Paths.get không có cùng mốc xuất hiện

`Path.of("a", "b")` có từ **Java 11**. Trên Java 7–10, factory thường dùng là:

```java
Path p = java.nio.file.Paths.get("a", "b");
```

Đây là snippet minh họa. Hai cách đều còn hợp lệ trên Java 17+, nhưng trong code mới có thể ưu tiên `Path.of`. Không cần sử dụng phiên bản Java 7 đã cũ để hiểu hành vi chuẩn của `Path`.

## 4. Dấu phân cách: '/' và '\\' không tương đương trên mọi nền tảng

Một sai lầm phổ biến là hard-code dấu `\` vì ứng dụng được phát triển trên Windows, hoặc giả định dấu `/` có cùng ý nghĩa ở mọi provider.

| Nền tảng/provider | Dấu phân cách thông dụng | `Path.of("a", "b")` thường hiển thị | Lưu ý |
| --- | --- | --- | --- |
| Windows default filesystem | `\` | `a\b` | Nhiều cách nhập đường dẫn cũng chấp nhận `/`, nhưng không nên dùng chuỗi Windows cho mọi nền tảng |
| Linux default filesystem | `/` | `a/b` | Dấu `\` thường là ký tự hợp lệ trong **tên** file, không phải separator |
| macOS default filesystem | `/` | `a/b` | Có thể khác nhau về phân biệt chữ hoa/thường, Unicode normalization và volume |
| ZIP filesystem provider (`jdk.zipfs`) | `/` | `a/b` | Cú pháp path bên trong archive, không phải drive/đường dẫn OS |

Ví dụ nên viết:

```java
Path images = Path.of("app", "assets").resolve("logo.png");
```

Không viết code yêu cầu Windows để phân tích path trên Linux:

```java
Path suspicious = Path.of("C:\\data\\report.txt");
```

Đoạn này **không phải cách tạo Path portable**. Trên Windows, nó có thể được phân tích là drive absolute path, nhưng trên Linux default provider, dấu `\` và dấu `:` không có ngữ nghĩa drive Windows; chúng có thể chỉ là ký tự trong một name element. Vì vậy **đừng đoán rằng `suspicious.isAbsolute()` trả cùng kết quả trên mọi OS**.

Lệnh `FileSystems.getDefault().getSeparator()` cung cấp separator của **default filesystem**. Nếu làm việc với Path của ZIP hoặc provider khác, dùng `path.getFileSystem().getSeparator()`; không dùng `File.separator` của OS để ghép một Path trong archive.

### 4.1. In log portable khác với tạo Path portable

Để hiển thị ví dụ trong tài liệu, có thể đổi dấu `\` thành `/` ở **chuỗi log**:

```java
static String display(Path path) {
    return path.toString().replace('\\', '/');
}
```

Đây là **phương thức minh họa** đặt trong lớp có import `Path`. Nó **không** được dùng để thực hiện chuyển đổi một đường dẫn Windows thực sang Linux hoặc làm bước xác thực bảo mật. Nếu tên file hợp lệ trên Linux chứa dấu `\` theo nghĩa ký tự bình thường, việc thay dấu trong log có thể làm mất ý nghĩa của tên. Trong test thực tế, ưu tiên so sánh `Path` hoặc từng name element thay vì sửa `toString()`.

## 5. Root, absolute và relative: Windows khác UNIX thế nào?

### 5.1. UNIX/POSIX-style path

Trên provider kiểu UNIX:

- `/var/log/app.log` là đường dẫn **absolute**, root `/`.
- `var/log/app.log` là **relative**, được giải nghĩa theo working directory khi truy cập filesystem mặc định.
- `./report.csv` là relative có thành phần `.`.
- `../archive/file.txt` là relative có thành phần `..`.
- `/` có thể là root của một volume/mount hierarchy, nhưng **không đồng nghĩa** mọi file nằm trên cùng thiết bị vật lý.

### 5.2. Windows và những dạng root đặc biệt

Ví dụ cú pháp Windows phổ biến:

```text
C:\work\report.txt       Đường dẫn absolute với drive/root.
C:work\report.txt        Drive-relative, KHÔNG tương đương C:\work\report.txt.
\work\report.txt         Root-relative trên drive hiện hành; không phải full absolute.
\\server\share\file.txt  UNC path tham chiếu một network share.
report.txt               Tên relative.
```

**Đây chỉ là văn bản minh họa cú pháp Windows, không phải mã Java để chạy trên Linux.**

Với Windows, `C:work\report.txt` là **drive-relative**: nó có thể phụ thuộc thư mục làm việc theo drive, không phải đường dẫn tuyệt đối cố định. `\work\report.txt` là **root-relative**: chỉ một root của drive, chưa xác định đầy đủ drive. Một path mạng UNC có phần `\\server\share` nằm trong root. Không nên dùng phép nối String hay logic POSIX thuần túy để suy ra `getRoot()` hoặc `isAbsolute()` của những dạng này.

**Trong mã portable**, dùng chính:

```java
Path p = Path.of("workspace", "report.txt");
System.out.println(p.isAbsolute());
System.out.println(p.getRoot());
System.out.println(p.toAbsolutePath());
```

Đây là snippet trong phương thức. Hai dòng đầu thể hiện tính relative và root của Path, còn `toAbsolutePath()` tạo biểu diễn absolute theo **file system/provider và môi trường hiện tại**. Dòng in absolute phụ thuộc working directory nên không phù hợp để ghi một stdout cố định chung cho mọi máy.

### 5.3. Không phải absolute path nào cũng là đường dẫn tới file hiện hữu

`path.isAbsolute()` nói về **độ đầy đủ về mặt cú pháp**, không khẳng định file tồn tại. `toAbsolutePath()` thường chuyển relative path dựa trên working directory, **không yêu cầu file tồn tại**. Nếu cần kiểm tra đường dẫn thực của file đã tồn tại, dùng `toRealPath()` với xử lý `IOException` và chính sách symbolic link rõ ràng.

## 6. Chữ hoa/thường, Unicode, tên file và thuộc tính filesystem

### 6.1. Case sensitivity không được quyết định chỉ bởi tên OS

- Linux với filesystem thông thường thường **phân biệt** tên `Report.txt` và `report.txt`.
- Windows với NTFS ở cấu hình phổ biến thường **không phân biệt** chữ hoa/thường khi tra cứu, nhưng có các cấu hình per-directory hoặc provider khác có hành vi riêng.
- macOS có thể sử dụng volume **case-insensitive** hoặc **case-sensitive** tùy định dạng/cấu hình; đừng mặc định tất cả máy Mac có cùng quy tắc.

Do đó không nên khẳng định `Path.of("A").equals(Path.of("a"))` có một kết quả cho mọi nền tảng. Theo Javadoc, `Path.equals` có **quy tắc so sánh phụ thuộc implementation**. Nếu cần kiểm tra hai đường dẫn trỏ **cùng file thực**, API như `Files.isSameFile(a, b)` phù hợp hơn nhưng sẽ truy cập filesystem, có thể ném `IOException`, và vẫn phải cân nhắc symlink.

### 6.2. Tên file hợp lệ khác nhau giữa provider

- Một số ký tự/tên có thể hợp lệ trên Linux nhưng không được chấp nhận bởi Windows default provider, ví dụ các dấu ngăn cách và các tên thiết bị dành riêng.
- Dấu hai chấm `:` có ý nghĩa drive hoặc luồng dữ liệu đặc biệt trên Windows; trên nhiều filesystem UNIX có thể là ký tự của tên file.
- Quy tắc về ký tự kết thúc bằng dấu chấm/khoảng trắng, control characters, chiều dài tên, và Unicode normalization có thể thay đổi theo filesystem.
- Một string hợp lệ trong JSON hoặc database **chưa chắc** hợp lệ làm file name trên máy đích.

Khi parse một tên không hợp lệ, `Path.of(...)` có thể ném `InvalidPathException`. Nhưng **parse được chưa đủ chứng minh I/O hợp lệ**: quyền truy cập, tên reserved, độ dài, mount, filesystem capabilities hoặc file tồn tại cũng ảnh hưởng.

### 6.3. Unicode normalization

Hai tên hiển thị giống nhau có thể có **chuỗi code point khác nhau** (ví dụ ký tự có dấu dạng composed và decomposed). Filesystem hoặc ứng dụng có thể chuẩn hóa hoặc so sánh khác nhau. Không tự dùng `String.toLowerCase()` hay thay dấu Unicode để suy luận Path tương đương ở mọi OS.

Khi lưu tên file để đồng bộ giữa hệ thống, quy định một chính sách tên/normalization rõ ràng theo product và filesystem thực tế. Nếu cần so sánh chính xác danh tính file, nên dựa trên API filesystem và kiểm thử trên volume đích thay vì so sánh String.

## 7. FileSystem và FileSystemProvider: ai hiểu Path và ai thực hiện I/O?

Trong Java NIO.2:

- **`Path`:** đường dẫn do một filesystem tạo; chứa tên/root, cung cấp thao tác cú pháp.
- **`FileSystem`:** biểu diễn một filesystem instance, tạo Path bằng `getPath(...)`, cung cấp separator, root directories, attribute views, `PathMatcher` và `WatchService` tùy khả năng.
- **`FileSystemProvider`:** lớp trừu tượng trong `java.nio.file.spi`; thực hiện các thao tác filesystem nền như kiểm tra truy cập, mở file, đọc attributes, tạo thư mục, copy/move/delete.
- **`FileSystems`:** factory lấy default filesystem, mở filesystem mới bằng URI hoặc Path, hoặc tham chiếu tới filesystem đã được mở.

Một Path luôn có quan hệ:

```text
Path
  └── getFileSystem() → FileSystem instance
                         └── provider() → FileSystemProvider
                                           └── getScheme() → "file" / "jar" / ...
```

Provider mặc định được nhận diện bằng URI scheme **`file`**. `jdk.zipfs` cung cấp filesystem provider cho ZIP/JAR, dùng scheme **`jar`** trong JDK có module này. Provider khác có thể đến từ thư viện/ứng dụng và hỗ trợ filesystem trong bộ nhớ, storage khác hoặc API chuyên biệt. Không khẳng định mọi bản runtime tối giản đều có provider `jar`: nếu build runtime bằng `jlink` bỏ module `jdk.zipfs`, chức năng ZIP filesystem có thể không sẵn có.

### 7.1. Tạo Path đúng provider

```java
FileSystem defaultFs = FileSystems.getDefault();
Path p = defaultFs.getPath("docs", "guide.txt");
```

Đây là snippet trong phương thức với import `java.nio.file.FileSystem`, `FileSystems` và `Path`. Ở default provider, `Path.of("docs","guide.txt")` tạo Path có cùng ngữ nghĩa. Nhưng với ZIP filesystem đã mở:

```java
Path entry = zipFs.getPath("/docs/guide.txt");
```

Đây là snippet trong phạm vi có `FileSystem zipFs`, không phải đoạn chạy độc lập. Nó tạo Path trong archive, **không phải** Path `/docs/guide.txt` trên ổ đĩa của máy. Để truy cập entry, dùng `Files` trên Path đó trong khi ZIP filesystem còn mở.

### 7.2. Provider cũng quyết định khả năng hỗ trợ API

Một filesystem có thể không hỗ trợ một số metadata (POSIX permissions, DOS attributes, links, file locking, watch service, file store hoặc atomic moves) theo cùng cách với provider khác.

Hỏi đúng câu hỏi:

- Provider nào đang sở hữu Path?
- Scheme là gì? Filesystem đã được mở hay đóng?
- Attribute views nào được hỗ trợ? Ví dụ `fs.supportedFileAttributeViews()`.
- Thao tác cần dùng có thật sự được provider hỗ trợ không?
- Hành vi atomicity, consistency, symbolic link và permission được tài liệu provider quy định như thế nào?

Không giả định mọi filesystem ảo là đĩa thường với toàn bộ thuộc tính POSIX/NTFS.

## 8. Chương trình Java 17+ hoàn chỉnh: default file và ZIP provider

Ví dụ sau minh họa **cùng interface Path, hai provider khác nhau** trong cùng JVM. ZIP là file tạm được tạo, ghi một entry, đọc lại và xóa trong `finally`. Chương trình cần JDK 17+ **có module `jdk.zipfs`**, như bản JDK đầy đủ thông thường; runtime bị cắt module hoặc thiếu quyền thư mục temp có thể không chạy được.

Tạo file **`PathPlatformDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class PathPlatformDemo {
    private static String slash(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) throws Exception {
        FileSystem defaultFs = FileSystems.getDefault();
        Path relative = Path.of("project", "assets", "logo.png");
        Path fromFileSystem = defaultFs.getPath("project", "assets", "logo.png");

        System.out.println("default scheme = " + defaultFs.provider().getScheme());
        System.out.println("same default path = " + relative.equals(fromFileSystem));
        System.out.println("default separator nonempty = " +
                !defaultFs.getSeparator().isEmpty());
        System.out.println("relative = " + !relative.isAbsolute());
        System.out.println("name count = " + relative.getNameCount());
        System.out.println("last name = " + relative.getFileName());
        System.out.println("parent = " + slash(relative.getParent()));
        System.out.println("resolved = " +
                slash(relative.getParent().resolve("backup.png")));
        System.out.println("normalized = " +
                slash(Path.of("project", ".", "assets", "..", "docs").normalize()));

        Path archive = Files.createTempFile("path-platform-demo-", ".zip");
        try {
            Files.delete(archive);
            URI archiveUri = URI.create("jar:" + archive.toUri());
            try (FileSystem zipFs = FileSystems.newFileSystem(
                    archiveUri, Map.of("create", "true"))) {
                Path entry = zipFs.getPath("/docs/info.txt");
                Files.createDirectories(entry.getParent());
                Files.writeString(entry, "provider demo", StandardCharsets.UTF_8);
                System.out.println("zip scheme = " + zipFs.provider().getScheme());
                System.out.println("zip root = " + entry.getRoot());
                System.out.println("zip path = " + slash(entry));
                System.out.println("zip content = " +
                        Files.readString(entry, StandardCharsets.UTF_8));
                System.out.println("different providers = " +
                        !relative.getFileSystem().provider().getScheme()
                                .equals(zipFs.provider().getScheme()));
                try {
                    entry.toFile();
                    System.out.println("zip toFile = supported");
                } catch (UnsupportedOperationException expected) {
                    System.out.println("zip toFile = unsupported");
                }
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+ có `jdk.zipfs`:

```bash
javac --release 17 PathPlatformDemo.java
java PathPlatformDemo
```

**Stdout đã kiểm thử với default provider Windows và ZIP provider của JDK:**

```text
default scheme = file
same default path = true
default separator nonempty = true
relative = true
name count = 3
last name = logo.png
parent = project/assets
resolved = project/assets/backup.png
normalized = project/docs
zip scheme = jar
zip root = /
zip path = /docs/info.txt
zip content = provider demo
different providers = true
zip toFile = unsupported
```

Giải thích thứ tự:

1. `FileSystems.getDefault().provider().getScheme()` trả `file`; đó là scheme chuẩn của default provider. Không in class implementation vì tên class có thể khác giữa OS/JDK.
2. `Path.of(...)` và `defaultFs.getPath(...)` tạo Path từ default filesystem; cùng các thành phần nên equals trả true trên provider mặc định thông dụng.
3. `relative` không absolute, có ba name elements, tên cuối là `logo.png`. Việc đổi dấu ở `slash` **chỉ để hiển thị**.
4. `normalize()` bỏ `.` và cặp `assets/..` theo quy tắc lexical, tạo `project/docs`; không truy cập file thật.
5. File ZIP được mở bằng `FileSystems.newFileSystem(archiveUri, Map.of("create","true"))`; provider có scheme `jar`, path bên trong ZIP dùng root `/` và entry `/docs/info.txt`.
6. `Files.createDirectories` và `Files.writeString` nhận **Path của ZIP provider**, vì vậy dữ liệu nằm **trong archive**, không được ghi như file `/docs/info.txt` trên ổ đĩa OS.
7. `entry.toFile()` không được hỗ trợ cho Path không thuộc default provider; vì vậy `UnsupportedOperationException` là hành vi mong đợi. Điều này minh họa rằng `Path` không phải lớp vỏ tương đương với `java.io.File`.
8. `try (FileSystem zipFs = ...)` đóng ZIP filesystem; `finally` xóa file archive tạm. Sau khi filesystem đóng, các Path từ nó không còn được dùng bình thường để thao tác I/O.
9. Demo dùng API Java 17+ hiện hành và có thể biên dịch với `--release 17`. Nếu ứng dụng sử dụng runtime tùy biến không gồm ZIP provider, phải bổ sung module/provider trước khi chạy.

**Đừng suy từ ví dụ rằng mọi provider hỗ trợ đóng/mở, thao tác temp file, `toFile`, encoding hay metadata giống ZIP provider.** Đọc tài liệu của provider thực tế.

## 9. ZIP filesystem: một Path có thể nằm bên trong archive

Nếu bạn có một file `archive.zip` trên default filesystem, có hai tầng khác nhau:

```text
Tầng ngoài (default provider "file")
  C:\storage\archive.zip   hoặc   /storage/archive.zip
  └── Là một file ZIP trên ổ đĩa OS

Tầng trong (ZIP provider "jar")
  /
  └── docs/
      └── info.txt
  └── Path "/docs/info.txt" sống trong FileSystem của ZIP
```

Một lời gọi `Path.of("/docs/info.txt")` trên Linux default provider **không** tự trỏ tới file bên trong archive. Muốn lấy Path của ZIP entry, phải lấy nó từ **đúng ZIP FileSystem instance**.

### 9.1. Mở một ZIP có sẵn

Một ứng dụng có thể mở một archive ZIP bằng factory của `FileSystems`:

```java
Path archive = Path.of("data", "archive.zip");

try (FileSystem zipFs = FileSystems.newFileSystem(archive)) {
    Path entry = zipFs.getPath("/docs/info.txt");
    if (Files.exists(entry)) {
        String content = Files.readString(entry, StandardCharsets.UTF_8);
        System.out.println(content);
    }
}
```

Đây là **snippet trong phương thức** có imports `FileSystems`, `FileSystem`, `Path`, `Files`, `StandardCharsets` và xử lý `IOException`. Code giả định archive đã tồn tại và ZIP provider có sẵn. Không cố sử dụng ZIP Path **sau khi** `zipFs.close()` để đọc nội dung.

### 9.2. ZIP provider không giống full filesystem POSIX

Một file ZIP có thể lưu các entry/path và metadata riêng. Nhà cung cấp `jdk.zipfs` có các thuộc tính và giới hạn riêng; không mặc định mọi `Files.setPosixFilePermissions` hoặc symbolic link/atomic rename hoạt động như trên Linux native filesystem. Với những thao tác phụ thuộc filesystem attribute views, kiểm tra provider capabilities. Nếu đọc archive từ nguồn không đáng tin, còn phải giới hạn kích thước entry, số lượng entry, đường dẫn giải nén và tài nguyên xử lý; cú pháp Path đúng không tự bảo vệ trước zip-slip/zip-bomb.

## 10. Ghép, so sánh và phân tích Path từ các provider khác nhau

### 10.1. Không trộn Path tùy ý giữa provider

Một `Path` do default provider tạo và Path do ZIP provider tạo **không thuộc cùng hệ tọa độ**. Những thao tác như `compareTo`, `relativize` hoặc một số dạng `resolve(Path)` có thể yêu cầu Path cùng provider; trộn chúng có thể gây `ClassCastException`, `IllegalArgumentException` hoặc hành vi riêng của implementation.

Theo Javadoc, **`Path.compareTo(other)` không được dùng với hai provider khác nhau** và có thể ném `ClassCastException`. Đừng dùng comparator cho Path từ nhiều provider như thể chúng là cùng một tập tên file toàn cục.

```java
Path diskPath = Path.of("docs", "info.txt");
Path zipPath = zipFs.getPath("/docs/info.txt");

// Không giả định diskPath.compareTo(zipPath) là hợp lệ.
// Không coi diskPath.equals(zipPath) đồng nghĩa file name giống nhau.
```

Đây là **snippet minh họa** cần có `FileSystem zipFs`. Cũng đừng dựa vào `path.toString()` làm khóa duy nhất của hai filesystem: cả hai Path có thể có text tương tự nhưng trỏ tới hai nguồn dữ liệu hoàn toàn khác nhau. Nếu cần một định danh bền vững, hãy lưu **scheme, filesystem identity/URI và đường dẫn trong đó** theo định dạng được provider hỗ trợ, đồng thời cân nhắc vòng đời filesystem.

### 10.2. So sánh Path.equals và Files.isSameFile

`Path.equals(other)` so sánh Path theo quy tắc provider, thường **không truy cập filesystem**. Hai Path khác chuỗi nhưng trỏ tới cùng file qua symbolic link/hard link có thể không equals.

`Files.isSameFile(a,b)` mới kiểm tra **danh tính file** qua filesystem theo hợp đồng và có thể ném `IOException`. Các provider có thể có cách kiểm tra khác nhau. Không dùng `String.equalsIgnoreCase` trên đường dẫn để mô phỏng filesystem case-insensitive; phép đó bỏ qua cách provider xử lý Unicode/volume/root.

### 10.3. Files.copy và Files.move giữa provider

`Files.copy(source, target, options...)` có API hỗ trợ thao tác copy với Path từ filesystem khác nhau, nhưng **không** phải mọi metadata/attribute, permission hoặc capability đều chuyển nguyên vẹn; phải xử lý `IOException` và kiểm tra kết quả.

`Files.move(source, target, options...)` giữa hai filesystem khác nhau có thể hoạt động thông qua copy/delete theo hợp đồng của API và **không nên mặc định atomic**. Nếu ứng dụng yêu cầu atomic move, phải xét provider, file store và `ATOMIC_MOVE`; có thể phát sinh `AtomicMoveNotSupportedException`.

**Không dùng `Path.resolve` để “chuyển” một ZIP Path thành disk Path**: resolve là phép ghép tên, không phải sao chép nội dung. Nếu muốn giải nén một entry, cần đọc từ ZIP Path, validate vị trí đích rồi dùng `Files.copy` hoặc các thao tác streaming phù hợp.

## 11. toFile, toUri và Path.of(URI): ranh giới tương thích

### 11.1. toFile chỉ được bảo đảm cho default provider

Theo Javadoc `Path.toFile()`, Path thuộc default provider có thể chuyển sang `java.io.File`; Path của provider khác **có thể ném `UnsupportedOperationException`**. Demo ZIP ở phần 8 đã thử trực tiếp trường hợp này.

Không sử dụng:

```java
java.io.File file = zipEntry.toFile();
```

để truy cập entry ZIP theo kiểu `File`. Đây là **snippet minh họa không phù hợp** với ZIP Path, không phải một lời khuyên. Thay vào đó, dùng `Files.newInputStream(zipEntry)`, `Files.readString(zipEntry, UTF_8)` hoặc API NIO nhận Path.

### 11.2. toUri không phải luôn là file: URI

`Path.toUri()` cho một URI biểu diễn Path theo provider. Với default provider, thường có scheme `file`; với ZIP có thể có scheme `jar` và cấu trúc URI ghép archive/entry. Không tự giả định định dạng URI ZIP do tất cả provider dùng giống nhau hoặc có thể round-trip giữa mọi phiên bản.

`Path.of(URI)` (có từ Java 11) yêu cầu provider hỗ trợ scheme URI và **filesystem tương ứng tồn tại/được tạo theo chính sách provider**. Nó có thể ném `FileSystemNotFoundException` khi chưa mở ZIP filesystem, hoặc khi provider không cài đặt. Hãy giữ filesystem mở trong scope thao tác cần dùng.

### 11.3. Tham số String không thay thế FileSystem identity

`zipFs.getPath("/docs/a.txt")` và `Path.of("/docs/a.txt")` có thể cùng `toString()` trên UNIX nhưng không cùng filesystem. Vì vậy khi thiết kế API dùng nhiều provider, truyền **`Path` gốc** đến các API NIO, hoặc truyền `FileSystem` để tạo Path. Đừng chuyển nó thành String rồi gọi `Path.of(string)`, vì bước sau thường **đưa về default provider** và làm mất ý nghĩa ban đầu.

## 12. normalize, toAbsolutePath, toRealPath: ba mức khác nhau

| Phương thức | Thao tác | Có đòi hỏi file tồn tại? | Ghi chú |
| --- | --- | --- | --- |
| `normalize()` | Loại bỏ `.` và cặp tên/`..` thừa theo quy tắc lexical | **Không** | Có thể đổi ý nghĩa khi có symbolic link |
| `toAbsolutePath()` | Tạo đường dẫn absolute theo provider/default directory | Thường **không** | Phụ thuộc môi trường/provider; có thể xảy ra lỗi đặc biệt |
| `toRealPath()` | Lấy đường dẫn thực của file đã tồn tại | **Có** | Có thể theo symbolic link; có thể ném `IOException` |

Ví dụ:

```java
Path raw = Path.of("project", "assets", "..", "docs");
Path normalized = raw.normalize();
Path absolute = normalized.toAbsolutePath();

// Chỉ dùng khi file đích thực sự tồn tại:
Path real = absolute.toRealPath();
```

Đây là snippet minh họa; dòng cuối **có thể ném IOException** khi đường dẫn không tồn tại. Cả ba thao tác dùng ngữ nghĩa provider. Đừng hiểu `normalize()` hoặc `toAbsolutePath()` là kiểm tra bảo mật/khả năng truy cập thực tế.

**Symlink warning:** ví dụ `a/link/../target` có thể không tương đương vật lý với `a/target` khi `link` trỏ sang thư mục khác. Chuẩn hóa lexical trước khi kiểm tra real path phải được hiểu theo yêu cầu nghiệp vụ và policy symbolic link.

## 13. Bảo mật và path traversal đa nền tảng

Một path do người dùng/đối tác cung cấp có thể chứa:

- `..` khiến kết quả thoát khỏi thư mục được phép.
- Absolute path làm thay thế base khi `resolve`.
- Drive-relative hoặc root-relative syntax trên Windows.
- Dấu `\` mà parser UNIX xem là ký tự bình thường nhưng parser Windows xem là separator.
- UNC path trỏ tới network share thay vì thư mục cục bộ.
- Symlink đưa đường dẫn lexical “bên trong” tới đối tượng vật lý “bên ngoài”.
- Ký tự, Unicode form hoặc tên reserved được diễn giải khác giữa các provider.

Ví dụ có kiểm tra lexical (chỉ là **một lớp phòng vệ**, không phải sandbox filesystem chống symlink/race):

```java
static Path insideRootLexically(Path root, Path input) {
    if (input.isAbsolute()) {
        throw new IllegalArgumentException("Absolute paths not allowed");
    }
    Path allowed = root.toAbsolutePath().normalize();
    Path candidate = allowed.resolve(input).normalize();
    if (!candidate.startsWith(allowed)) {
        throw new IllegalArgumentException("Escapes allowed directory");
    }
    return candidate;
}
```

Đây là **phương thức minh họa** trong class import `Path`. Với ứng dụng chỉ cho phép **tên file đơn** (không cho path con), nên kiểm tra thêm rằng input đúng một name element, không phải `.`, `..`, drive syntax hay root path theo provider đích, và áp chính sách tên file cụ thể.

**Cực kỳ quan trọng:** kiểm tra `startsWith` trên Path là **kiểm tra lexical**, không giải quyết symbolic links, TOCTOU race hoặc thay đổi mount. Với dữ liệu không tin cậy, phải xét quyền OS, chính sách symlink, đường dẫn thật, cơ chế thao tác an toàn như `SecureDirectoryStream` (nếu provider hỗ trợ) và hạn chế truy cập ngay tại root. Không coi `normalize().startsWith(root)` là một cơ chế cô lập file system đầy đủ.

### 13.1. Không dùng String prefix để kiểm tra root

`"/safe/data-other".startsWith("/safe/data")` là true về chuỗi, nhưng **không** phải con của thư mục `/safe/data`. `Path.startsWith(Path)` so sánh thành phần path theo provider, tuy vậy vẫn là lexical check, không thay thế kiểm tra quyền thực tế.

### 13.2. Kiểm tra đường dẫn theo provider sẽ **thực sự sử dụng**

Nếu ứng dụng nhận tên file từ máy Windows nhưng phục vụ trên Linux, hoặc giải nén ZIP vào Windows, validate **trên hệ thống đích và provider thực**. Một tên hợp lệ ở nguồn có thể chứa dấu phân cách/ngữ nghĩa nguy hiểm ở đích. Không giả định sanitize bằng `replace("../", "")` đủ cho `..\`, UNC, drive-relative, Unicode hoặc các dạng normalize khác.

## 14. Khả năng của provider: attributes, links, watch, lock và atomicity

Các API NIO có cùng chữ ký nhưng provider có thể khác về khả năng:

| Tính năng | Default filesystem | ZIP/provider khác |
| --- | --- | --- |
| Dấu phân cách/root | Theo OS | Theo provider (ZIP thường `/`) |
| POSIX permissions | Thường có trên UNIX, nhưng còn tùy filesystem | Có thể thiếu hoặc có view riêng |
| DOS attributes | Thường gặp trên Windows | Có thể không hỗ trợ |
| Symbolic links | Theo OS/volume/quyền | Không được mặc định hỗ trợ |
| WatchService | Thường có, nhưng giới hạn provider | Có thể không hỗ trợ hoặc khác semantics |
| `toFile()` | Được hỗ trợ cho default Path | Thường không, có thể ném `UnsupportedOperationException` |
| `Files.move(..., ATOMIC_MOVE)` | Tùy file store/OS | Tùy provider; không được suy là atomic |
| Case sensitivity / Unicode | Theo FS, volume và cấu hình | Theo provider/format |
| File locks và file metadata | Tùy filesystem | Có thể bị hạn chế |
| Thời điểm lưu dữ liệu | Theo OS và thao tác I/O | ZIP filesystem có thể cập nhật archive khi đóng |

Để xem supported attribute views:

```java
FileSystem fs = path.getFileSystem();
System.out.println(fs.supportedFileAttributeViews());
```

Đây là snippet trong phương thức với `Path path` và import `FileSystem`. Danh sách phụ thuộc provider và máy, nên **không có stdout cố định**. Kiểm tra API có được hỗ trợ và xử lý lỗi, không lấy kết quả của một môi trường phát triển làm giả định vĩnh viễn cho mọi hệ thống.

Một `FileSystem` được mở bằng `FileSystems.newFileSystem(...)` thường cần đóng đúng thời điểm, ví dụ bằng **try-with-resources**. Đừng trả về Path của một ZIP filesystem đã đóng rồi mong caller tiếp tục đọc bình thường.

## 15. Chọn thiết kế portable cho ứng dụng thực tế

**Tình huống A — ứng dụng lưu file dưới một thư mục cấu hình.** Dùng root do server cấu hình và `root.resolve("reports").resolve(name)` với tên file đã được validate. Tránh ghép String có hard-coded `C:\...` hoặc `/home/...` khi cần chạy nhiều OS.

**Tình huống B — công cụ đọc tài liệu từ ZIP.** Mở ZIP qua FileSystem provider có sẵn, tạo Path bên trong bằng `zipFs.getPath(...)` và dùng các API `Files` trên Path đó. Không gọi `zipEntry.toFile()`.

**Tình huống C — ứng dụng có cả file local và file system ảo.** API của bạn nên nhận `Path`/`FileSystem` phù hợp và phân biệt scheme/provider; không tự biến mọi Path thành String rồi dựng lại bằng default `Path.of(...)`.

**Tình huống D — hệ thống trao đổi tên file giữa Windows và Linux.** Lưu **tên logic hoặc các segment** theo một schema định nghĩa rõ, kiểm tra chúng tại phía nhận, dựng Path bằng provider đích. Đừng đưa nguyên chuỗi path Windows vào parser UNIX rồi mong ý nghĩa ổ đĩa được giữ nguyên.

**Tình huống E — cần đồng bộ hoặc nhận diện cùng file.** So sánh Path theo provider hoặc dùng `Files.isSameFile` khi thực sự cần danh tính file trên filesystem đang tồn tại; không dựa vào lowercase/normalize String.

**Tình huống F — tạo/đổi tên file phải atomic.** Đây là yêu cầu I/O, không phải tính chất tự động của Path. Tìm hiểu `Files.move`, `ATOMIC_MOVE`, file store/provider capabilities và kế hoạch fallback khi unsupported.

## 16. Bảng đối chiếu câu hỏi thực tế

| Câu hỏi | Câu trả lời đúng |
| --- | --- |
| `Path.of("a","b")` có dùng cùng separator trên Windows và Linux? | Không; provider mặc định quyết định. |
| `Path.of("C:\\work\\a.txt")` trên Linux có hiểu ổ C không? | Không theo cách của Windows default provider. |
| `Path.of("a","b")` tạo file thật chưa? | Chưa, chỉ tạo đối tượng Path. |
| `Path.of("x").isAbsolute()` ở mọi OS? | Thường false với tên tương đối; muốn biết hãy gọi API trên provider thực. |
| `Path.equals` có luôn phân biệt case? | Không; theo provider/filesystem implementation. |
| `getFileName()` và `getRoot()` có cùng semantics mọi provider? | Cùng hợp đồng API nhưng root/name syntax theo provider. |
| ZIP entry `/docs/a.txt` là file trên root OS? | Không; nó thuộc ZIP FileSystem instance. |
| `Path.of("/docs/a.txt")` tự trỏ vào ZIP đang mở? | Không; factory mặc định không thay provider. |
| `zipPath.toFile()` có luôn hoạt động? | Không; non-default provider có thể ném `UnsupportedOperationException`. |
| Có nên compareTo hai Path từ provider khác nhau? | Không; Javadoc cấm trộn, có thể gây `ClassCastException`. |
| `normalize()` có giải quyết symlink? | Không; đó là lexical normalization. |
| `toRealPath()` có thể ném IOException? | Có; yêu cầu file tồn tại và truy cập filesystem. |
| `Files.copy` giữa provider có luôn giữ mọi metadata? | Không; xử lý theo khả năng provider và options. |
| `Files.move` luôn atomic? | Không; còn phụ thuộc provider/file store. |

## 17. Lỗi thường gặp khi chuyển ứng dụng giữa các nền tảng

**Lỗi 1 — Hard-code `"\\"` cho mọi đường dẫn.** Trên UNIX, ký tự `\` có thể là một phần tên file; dùng `Path.of(segments...)` hoặc `resolve`.

**Lỗi 2 — Giả định mọi chuỗi `"C:\\"` là absolute trên mọi OS.** Đây là cú pháp Windows, không phải ngôn ngữ đường dẫn phổ quát.

**Lỗi 3 — Nhầm `C:docs\\a.txt` với `C:\\docs\\a.txt`.** Cái đầu là drive-relative, cái sau là drive absolute theo quy tắc Windows.

**Lỗi 4 — Mặc định macOS luôn case-insensitive.** Volume có thể được cấu hình case-sensitive; logic so tên phải theo FS thực.

**Lỗi 5 — Dùng `path.toString()` làm khóa nhận diện file toàn cục.** Hai provider có thể có path String giống nhau nhưng trỏ tới dữ liệu khác.

**Lỗi 6 — Tạo Path từ String của ZIP path bằng `Path.of(string)`.** Nó có thể trở về default provider; dùng `zipFs.getPath(...)`.

**Lỗi 7 — Gọi `zipPath.toFile()`.** Non-default Path không được bảo đảm chuyển sang `java.io.File`.

**Lỗi 8 — Xử lý ZIP Path sau khi đóng FileSystem.** Cần giữ filesystem mở đến khi các thao tác cần thiết hoàn tất.

**Lỗi 9 — Trộn Path của hai provider trong `compareTo`/`relativize`.** Không hợp lệ hoặc phụ thuộc implementation; chỉ thao tác khi provider tương thích.

**Lỗi 10 — Coi `normalize()` là lối bảo vệ chống traversal.** Nó không giải quyết symlink/race và không kiểm tra quyền truy cập.

**Lỗi 11 — Dùng `String.startsWith` cho giới hạn directory.** Có thể bị nhầm bởi prefix tên giống nhau; kiểm tra Path components và an toàn ở tầng I/O.

**Lỗi 12 — Cho rằng tồn tại Path object nghĩa là có file.** `Path.of` không làm I/O; kiểm tra qua Files hoặc thao tác I/O thật.

**Lỗi 13 — Dùng cùng thuộc tính POSIX, DOS và symbolic link cho mọi provider.** Mỗi provider có capabilities khác nhau.

**Lỗi 14 — Cho rằng `Files.move` qua filesystem luôn atomic.** Không; cần xử lý trường hợp không hỗ trợ.

**Lỗi 15 — Ghép URL bằng FileSystem Path API.** URL/URI có encoding và quy tắc riêng, không đồng nhất với đường dẫn OS.

**Lỗi 16 — Giả định runtime Java nào cũng cài `jdk.zipfs`.** Runtime được tạo tối giản có thể thiếu module; kiểm tra thành phần của runtime đích.

**Lỗi 17 — Tự convert tên file Unicode thành lowercase để so sánh.** Có thể sai với locale, normalization và provider case policy; không tự thay thế quy tắc của filesystem.

## 18. Checklist review mã Java sử dụng nhiều filesystem

1. **Xác định Path được tạo ở đâu:** `Path.of` (default provider), `FileSystem.getPath` (provider cụ thể) hay nhận từ thư viện?
2. **Không ghép String theo separator OS** trừ khi format dữ liệu thật sự đòi hỏi; dùng Path segments.
3. **Biết provider scheme và filesystem identity** khi xử lý Path có thể đến từ archive hoặc storage khác.
4. **Xét absolute vs relative, root, UNC/drive-relative và tên rỗng** theo hệ thống đích.
5. **Không dựng lại Path từ `toString` qua default provider** nếu muốn giữ provider gốc.
6. **Không dùng `toFile` cho non-default Path**; ưu tiên API `Files`.
7. **Không dựa vào `Path.equals` để kiểm tra cùng file vật lý**; dùng API phù hợp khi cần.
8. **Nếu so sánh hoặc resolve hai Path**, bảo đảm chúng thuộc provider tương thích hoặc chuyển đổi theo giao thức có chủ đích.
9. **Kiểm tra supported attribute views và capabilities** trước khi sử dụng POSIX/DOS/watch/atomic operations.
10. **Đảm bảo FileSystem mở đúng vòng đời**; đóng provider filesystem được mở khi xong.
11. **Với input không tin cậy, validate tên/segment theo provider đích**, hạn chế absolute và traversal.
12. **Không coi lexical normalization là sandbox**; đánh giá symlink, race, permissions và filesystem boundary.
13. **Test trên target OS và filesystem cấu hình thật**: Windows/Linux/macOS, case sensitivity, names, Unicode, UNC nếu có.
14. **Test ZIP provider nếu dự án yêu cầu**: entry path, read/write, close, toFile unsupported và runtime module.
15. **Dùng đúng JDK target**: Path từ Java 7, `Path.of` từ Java 11; ví dụ Java 17+ yêu cầu `jdk.zipfs`.

## 19. Câu hỏi tự kiểm tra

**1.** Cùng chuỗi `"a\\b"` có thể được parse khác trên Windows và Linux không? — **Có.** Windows thường coi `\` là separator, UNIX thường là ký tự tên file.

**2.** `Path.of("a","b")` có ưu điểm gì? — Provider mặc định tự chọn cú pháp separator, không phải nối chuỗi thủ công.

**3.** `Path.of("C:\\x")` trên Linux có phải đường dẫn ổ C không? — **Không**, vì default provider Linux không có drive Windows.

**4.** `FileSystems.getDefault().provider().getScheme()` thông thường là gì? — **`file`**.

**5.** `FileSystem zipFs` có scheme gì với `jdk.zipfs`? — **`jar`**.

**6.** Tại sao `zipFs.getPath("/docs/a.txt")` không giống `Path.of("/docs/a.txt")`? — Vì chúng thuộc **hai FileSystem/provider khác nhau**.

**7.** Có nên gọi `zipPath.toFile()` không? — **Không**, non-default provider thường ném `UnsupportedOperationException`.

**8.** macOS luôn có filename case-insensitive? — **Không**, tùy volume/cấu hình.

**9.** `Path.equals` có kiểm tra file tồn tại và theo symlink không? — **Không**, đó là so sánh theo provider. `Files.isSameFile` mới phục vụ nhận diện cùng file thật theo hợp đồng.

**10.** `normalize()` có truy cập filesystem không? — **Không**; nó rút gọn thành phần lexical.

**11.** `toRealPath()` khác `toAbsolutePath()` như thế nào? — `toRealPath` yêu cầu file tồn tại và xác định đường dẫn thật với chính sách link, còn `toAbsolutePath` chủ yếu tạo biểu diễn absolute theo môi trường.

**12.** Có thể dùng `Path.compareTo` với một Path ZIP và một Path default không? — **Không**; khác provider, có thể ném `ClassCastException`.

**13.** Nếu ZIP FileSystem đã đóng, có nên giữ Path entry để đọc sau không? — **Không**; phải giữ scope FileSystem phù hợp tới lúc đọc xong.

**14.** `Files.move` giữa hai provider có được giả định atomic không? — **Không**, phải xét hỗ trợ cụ thể và xử lý lỗi.

**15.** Thế nào là một tên file portable? — Là tên/segment được quy định và kiểm tra phù hợp với **mọi hệ thống đích cần hỗ trợ**, không phải một path String hoạt động trên một máy.

**16.** Vì sao test trên Windows/Linux thực tế vẫn cần thiết dù dùng Path? — Vì case, Unicode, names, drive, symlink, permission và filesystem capabilities vẫn khác.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): thuộc tính Path, provider dependence, `getRoot`, `resolve`, `normalize`, `toRealPath`, `toUri`, `toFile` và `compareTo`.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): cách tạo Path, separator, khả năng và vòng đời filesystem.
- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): default filesystem và các factory mở filesystem khác.
- [Java SE 17 — FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): provider SPI, scheme và thao tác I/O.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các thao tác I/O trên Path và giới hạn giữa provider.
- [JDK 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP/JAR filesystem provider, URI scheme `jar`, cấu hình `create` và file attribute views.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác relative theo directory handle khi provider hỗ trợ, hữu ích để giảm nguy cơ race.

**Ghi nhớ:** `Path` không chỉ là “String có dấu phân cách”. Mỗi Path thuộc về **một FileSystem/provider**; Windows, Linux, macOS và ZIP có thể có **root, separator, case sensitivity, tên hợp lệ và tính năng khác nhau**. Xây đường dẫn bằng các segment/`resolve` trong đúng provider, không chuyển Path qua `toString` rồi dựng lại tùy tiện, phân biệt lexical với real path, và **kiểm tra khả năng/tính an toàn trên hệ thống đích thực tế**.