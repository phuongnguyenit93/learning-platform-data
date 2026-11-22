# Java 7 — FileSystem và ZIP: Nhà cung cấp mặc định và hệ thống tệp bổ sung

## Mục tiêu và phạm vi

Java NIO.2 không giới hạn `Path` và `Files` vào ổ đĩa của hệ điều hành. Từ **Java 7**, kiến trúc `java.nio.file` cho phép nhiều **file-system providers** cùng tồn tại: một provider mặc định phục vụ hệ thống tệp của máy, và các provider bổ sung có thể ánh xạ một ZIP/JAR, runtime image, bộ nhớ hoặc kho dữ liệu chuyên biệt thành những `FileSystem` khác nhau.

Bài này giải thích đúng trọng tâm **“Nhà cung cấp mặc định và hệ thống tệp bổ sung”**, thuộc nhóm **“FileSystem và ZIP”**:

1. Phân biệt rõ `FileSystemProvider`, `FileSystem`, `Path`, `Files` và `FileStore`.
2. Xác định **default file system** bằng `FileSystems.getDefault()`, provider của nó, scheme `file` và đường dẫn tương ứng.
3. Liệt kê những providers đang thực sự cài đặt bằng `FileSystemProvider.installedProviders()`; không mặc định mọi JDK/provider đều có cùng tập scheme.
4. Hiểu provider được nhận diện bởi **URI scheme** và được tìm qua service-provider mechanism.
5. Phân biệt `FileSystems.newFileSystem(...)` (tạo/mở một instance mới) với `FileSystems.getFileSystem(URI)` (lấy reference đến instance hiện có).
6. Tạo và mở một **ZIP file system** với provider `jdk.zipfs`, scheme `jar`, môi trường `Map.of("create","true")`, rồi đọc/ghi entry bằng API `Files` thông thường.
7. Dùng đúng **ZIP-internal Path** từ `zipFs.getPath(...)` thay vì lấy path từ default filesystem rồi ghép nhầm.
8. Hiểu **provider mismatch**, khi nào `Files.copy` hoạt động xuyên provider và vì sao `Path.toFile()` không portable.
9. Quản lý vòng đời: ZIP `FileSystem` phải được đóng, còn **default file system không được đóng**.
10. Đọc lỗi `ProviderNotFoundException`, `FileSystemAlreadyExistsException`, `FileSystemNotFoundException`, `ClosedFileSystemException`, `ProviderMismatchException` và `IOException` đúng nguyên nhân.
11. Kiểm tra attributes, khả năng hỗ trợ các file-attribute views và giới hạn của ZIP filesystems.
12. Thiết kế ứng dụng an toàn với ZIP nhập từ nguồn không tin cậy, tránh trộn path giữa provider, khai thác ZIP bomb/path traversal và bỏ quên resource.
13. Phân biệt **API có từ Java 7** với các overload và tiện ích được bổ sung ở Java 9, 11 và 13 mà ví dụ Java 17 sử dụng.

**Special Note của module:** Chỉ sử dụng kiến thức còn áp dụng hiện nay; không lấy khuyến nghị đã lỗi thời/legacy. Ví dụ đầy đủ biên dịch với `javac --release 17` và chạy được trên JDK hiện đại. Các mốc phiên bản được ghi rõ để người học không nhầm API NIO.2 Java 7 với overload xuất hiện về sau.

## 1. Mô hình NIO.2: năm khái niệm khác nhau

### 1.1. `FileSystemProvider`: nhà cung cấp triển khai

`java.nio.file.spi.FileSystemProvider` là lớp trừu tượng để nhà cung cấp cụ thể triển khai các thao tác filesystem. Nó xác định cách đọc, ghi, tạo, xóa, truy xuất attributes và xây dựng một hoặc nhiều hệ thống tệp.

Provider được nhận diện bằng một **URI scheme**, thông qua `provider.getScheme()`. Chẳng hạn:

- Provider mặc định dùng scheme **`file`**.
- ZIP file-system provider trong module `jdk.zipfs` dùng scheme **`jar`**.
- Một runtime Java có thể cung cấp scheme **`jrt`** để truy cập runtime image.
- Provider của thư viện bên thứ ba có thể định nghĩa scheme riêng như `memory` hoặc `s3`; đó chỉ là ví dụ về khả năng mở rộng, **không phải provider được Java chuẩn đảm bảo có sẵn**.

**Một provider không nhất thiết tương ứng đúng một FileSystem object.** Nó có thể tạo nhiều FileSystem instances, ví dụ mỗi ZIP archive có một instance được mở riêng.

### 1.2. `FileSystem`: một instance của hệ thống tệp

`java.nio.file.FileSystem` biểu diễn một hệ thống tệp có các quy tắc riêng về đường dẫn, root, separator, store, attribute views và lifecycle.

API tiêu biểu:

```java
FileSystem fs = FileSystems.getDefault();
FileSystemProvider provider = fs.provider();
String separator = fs.getSeparator();
boolean open = fs.isOpen();
boolean readOnly = fs.isReadOnly();
Set<String> views = fs.supportedFileAttributeViews();
```

Đây là **mảnh minh họa**, cần import `FileSystems`, `FileSystem`, `FileSystemProvider`, `Set`. Các giá trị có thể khác theo provider, đặc biệt `separator` và supported views.

**Không đồng nhất FileSystem với ổ đĩa vật lý**: một FileSystem có thể nhìn thấy nhiều roots/stores, hoặc chỉ biểu diễn một ZIP file duy nhất.

### 1.3. `Path`: đường dẫn gắn chặt với một FileSystem

Một `Path` là giá trị mô tả vị trí **bên trong FileSystem tạo ra nó**. Hai path có cùng chuỗi `"/docs/a.txt"` không nhất thiết trỏ cùng resource nếu chúng thuộc hai providers khác nhau.

```java
Path local = Path.of("archive.zip");          // Default filesystem.
Path inside = zipFs.getPath("/docs/a.txt");   // ZIP filesystem.
```

Đây là **mảnh minh họa**; `zipFs` cần là một `FileSystem` ZIP đang mở. `Path.of` xuất hiện từ Java 11, còn `FileSystem.getPath` là API NIO.2 có từ Java 7.

**Nguyên tắc cốt lõi:** `local.getFileSystem()` và `inside.getFileSystem()` khác nhau; string path không thể hoán đổi cho nhau một cách tùy tiện.

### 1.4. `Files`: façade thao tác trên Path

Các phương thức `Files` thường **ủy quyền** việc thực thi cho provider gắn với `Path`:

```java
Files.exists(path);
Files.readString(path);
Files.createDirectories(path);
Files.copy(source, target);
Files.readAttributes(path, BasicFileAttributes.class);
```

Đây là mảnh minh họa, cần `Path` hợp lệ và imports. `Files.readString` có từ Java 11; các API khác được giới thiệu từ Java 7.

Cùng một phương thức `Files.readString` có thể đọc file trên ổ đĩa **hoặc** entry trong ZIP: sự khác biệt ở provider của `path`. Điều đó làm NIO.2 hữu ích cho code không phụ thuộc hệ thống tệp cụ thể.

### 1.5. `FileStore`: kho chứa dữ liệu phía dưới

`FileStore` mô tả một vùng lưu trữ, có thể cung cấp số liệu capacity và hỗ trợ attribute views. Một FileSystem có thể cung cấp **nhiều FileStores**. Không coi `FileStore` là synonym của `FileSystem` hay `FileSystemProvider`.

Ví dụ:

```java
FileStore store = Files.getFileStore(path);
boolean supportsBasic =
        store.supportsFileAttributeView("basic");
```

Đây là mảnh minh họa. Một số capabilities là optional; trên ZIP hoặc filesystem đặc biệt, những thông tin capacity/attributes có thể khác OS filesystem.

## 2. Quan hệ giữa provider, filesystem, path và Files

Sơ đồ ý tưởng:

```text
Java application
      |
      | Path p1          Path p2
      |    |                |
      v    v                v
  java.nio.file.Files  (dispatcher/delegation)
      |                |
      v                v
Default provider     ZIP provider
scheme = "file"      scheme = "jar"
      |                |
      v                v
FileSystem A         FileSystem B (archive.zip)
      |                |
      v                v
Path C:\...          Path /docs/hello.txt
      |                |
      v                v
OS files/directories ZIP/JAR entries
```

Điều cần nhớ:

- `FileSystemProvider`: **ai thực thi**.
- `FileSystem`: **phạm vi và quy tắc**.
- `Path`: **một vị trí trong phạm vi đó**.
- `Files`: **cách code yêu cầu thao tác**.
- `FileStore`: **metadata về storage underlying**.

Đây là quan hệ hướng đối tượng và service-provider architecture, không phải lời hứa rằng mọi provider đều hỗ trợ mọi thao tác giống nhau.

## 3. Default FileSystem: `FileSystems.getDefault()`

`FileSystems.getDefault()` trả về instance default của JVM, thường cho phép làm việc với OS filesystem theo môi trường ứng dụng.

```java
FileSystem fs = FileSystems.getDefault();
String scheme = fs.provider().getScheme();  // "file".
```

Default provider được nhận diện bằng scheme **`file`**. Mặc định thường là provider hệ thống, nhưng Java có cơ chế cấu hình chuyên biệt qua system property `java.nio.file.spi.DefaultFileSystemProvider` cho provider wrapper. Với code thông thường, **đừng tùy tiện thay default provider ở production** chỉ để xử lý ZIP; hãy tạo một FileSystem bổ sung cho ZIP.

### 3.1. Các cách tạo Path trên default filesystem

```java
Path a = Path.of("data", "report.txt");
Path b = FileSystems.getDefault().getPath("data", "report.txt");
Path c = Paths.get("data", "report.txt");
```

Đây là **mảnh minh họa**. `Path.of` có từ Java 11; `Paths.get` và `getDefault().getPath` từ Java 7. Chúng phục vụ default filesystem trong trường hợp này.

**Không dùng `Path.of("docs", "hello.txt")` để lấy entry trong ZIP**. Cách đó tạo path của default FileSystem. Với ZIP, phải dùng `zipFs.getPath("/docs/hello.txt")` hoặc một URI thích hợp với ZIP provider đang được mở.

### 3.2. Một JVM có bao nhiêu default FileSystems?

Theo hợp đồng `FileSystems.getDefault`, lần gọi đầu thiết lập default filesystem và các lần sau trả lại instance đó. Một JVM có một **default** ở tầng API này, nhưng có thể **nhiều FileSystems bổ sung** đồng thời.

Ví dụ bạn có thể mở:

```text
Default FileSystem     → scheme file
ZIP FileSystem #1      → archive-a.zip
ZIP FileSystem #2      → archive-b.zip
ZIP FileSystem #3      → report.jar
Additional provider    → scheme khác (nếu được cài)
```

Không cần thay default filesystem để mở ZIP #1 hoặc #2.

### 3.3. Default FileSystem không được đóng

`FileSystem` implements `Closeable`, nhưng tài liệu Java quy định **FileSystem được tạo bởi default provider không thể đóng**. Không viết:

```java
try (FileSystem defaultFs = FileSystems.getDefault()) {
    // Không nên quản lý default filesystem theo kiểu này.
}
```

Đoạn trên **là anti-pattern**. Với filesystem bổ sung như ZIP, ngược lại, **phải đóng** khi xong việc bằng try-with-resources.

## 4. Chương trình A — Xác minh default provider

Lưu **`DefaultProviderDemo.java`**:

```java
import java.net.URI;
import java.nio.file.*;
import java.nio.file.spi.FileSystemProvider;

public final class DefaultProviderDemo {
    public static void main(String[] args) throws Exception {
        FileSystem fs = FileSystems.getDefault();
        Path p = Path.of("sample.txt");

        System.out.println("scheme=" + fs.provider().getScheme());
        System.out.println("pathOnDefault=" +
                (p.getFileSystem() == fs));
        System.out.println("fileUriReturnsDefault=" +
                (FileSystems.getFileSystem(URI.create("file:///")) == fs));
        System.out.println("defaultOpen=" + fs.isOpen());
        System.out.println("defaultReadOnly=" + fs.isReadOnly());
        System.out.println("defaultProviderFirst=" +
                (FileSystemProvider.installedProviders().get(0) ==
                        fs.provider()));
        System.out.println("defaultRootCountAtLeastOne=" +
                fs.getRootDirectories().iterator().hasNext());
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DefaultProviderDemo.java
java DefaultProviderDemo
```

**Stdout đo được trên Windows/JDK kiểm thử:**

```text
scheme=file
pathOnDefault=true
fileUriReturnsDefault=true
defaultOpen=true
defaultReadOnly=false
defaultProviderFirst=true
defaultRootCountAtLeastOne=true
```

### 4.1. Phân tích

- `scheme=file`: default provider dùng scheme chuẩn `file`.
- `pathOnDefault=true`: `Path.of(...)` trả path thuộc default FileSystem.
- `fileUriReturnsDefault=true`: với URI `file:///` được default provider chấp nhận, `getFileSystem` lấy cùng instance trong bài thử.
- `defaultOpen=true`: default filesystem đang hoạt động.
- `defaultReadOnly=false` chỉ phản ánh filesystem kiểm thử; **không được hứa mọi filesystem luôn cho ghi**.
- `defaultProviderFirst=true`: hợp đồng `installedProviders()` nêu default provider đứng đầu danh sách.
- `defaultRootCountAtLeastOne=true` là quan sát tại máy thử, **không phải con số roots portable**.

Không in tên provider class nội bộ cụ thể vì Java implementations/OS có thể khác. **Dựa vào public API `getScheme()`**, không hardcode tên class nội bộ `sun.nio.fs.*`.

### 4.2. Đừng dùng `toString()` của provider làm contract

Một provider trên Windows có thể mang class name khác Linux, và class nội bộ của JDK không phải API để application phụ thuộc. Kiểm tra `getScheme()` cùng các capability methods khi cần.

## 5. Provider discovery: `FileSystemProvider.installedProviders()`

Java NIO.2 dùng cơ chế service-provider để tìm các triển khai file systems.

```java
List<FileSystemProvider> providers =
        FileSystemProvider.installedProviders();

for (FileSystemProvider p : providers) {
    System.out.println(p.getScheme());
}
```

Đây là **mảnh minh họa**, cần import `List` và `FileSystemProvider`. List trả về **không thể sửa** và chứa **ít nhất default provider**.

### 5.1. Khả năng các scheme thường gặp

| Scheme | Ý nghĩa | Có được đảm bảo trong mọi Java runtime? |
| --- | --- | --- |
| `file` | Default filesystem | Có default provider theo hợp đồng |
| `jar` | ZIP/JAR filesystem qua ZIP provider | Chỉ khi provider phù hợp hiện diện, ví dụ module `jdk.zipfs` |
| `jrt` | Java runtime image (Java 9+) | Phụ thuộc runtime/build/module |
| Scheme bên thứ ba | Filesystem tùy biến | Chỉ nếu ứng dụng/runtime cài và load được provider đó |

**Không suy ra `jar` luôn có chỉ vì bạn gọi Java NIO.2.** Một runtime image tối giản hoặc cấu hình module có thể không chứa `jdk.zipfs`. Trong app module hóa/jlink, kiểm tra module/provider được đóng gói đúng.

### 5.2. ServiceLoader và đăng ký provider

Tài liệu `FileSystems` mô tả các providers bổ sung được phát hiện thông qua cơ chế service-provider. Trên classpath, một provider có thể được đăng ký qua file:

```text
META-INF/services/java.nio.file.spi.FileSystemProvider
```

và nội dung nêu tên fully qualified của lớp kế thừa `FileSystemProvider`.

Với Java modules, khả năng đăng ký provider thông qua khai báo `provides ... with ...` trong module descriptor là một phần của hệ thống service loading.

Đây là **mô tả kiến trúc**, không yêu cầu người học tạo custom provider hay phụ thuộc các class JDK nội bộ. Nếu một thư viện hứa cung cấp memory filesystem hoặc cloud filesystem, phải đọc tài liệu của **chính thư viện** để biết scheme, dependency, registration, security và môi trường.

### 5.3. Provider được tìm khi nào?

Lời gọi `FileSystemProvider.installedProviders()` tải các installed providers nếu chưa được tải. Các factory methods trong `FileSystems` cũng có thể kích hoạt việc tìm provider theo contract.

Không nên:

- Mỗi request lặp lại việc quét provider để giải quyết một vấn đề có thể cache/configure một lần.
- Trông chờ thứ tự các provider bổ sung ngoài quy tắc default provider đứng đầu.
- Trông chờ hai providers khai báo cùng scheme đều được giữ; Java thực hiện xử lý duplicate schemes trong quá trình provider loading.
- Dựa vào provider có mặt ở máy dev nhưng không có trong deployment runtime.

## 6. Chương trình B — Liệt kê installed providers

Lưu **`ProviderCatalogDemo.java`**:

```java
import java.nio.file.*;
import java.nio.file.spi.FileSystemProvider;
import java.util.*;

public final class ProviderCatalogDemo {
    public static void main(String[] args) {
        List<FileSystemProvider> providers =
                FileSystemProvider.installedProviders();

        List<String> schemes = new ArrayList<>();
        for (FileSystemProvider provider : providers) {
            schemes.add(provider.getScheme());
        }
        Collections.sort(schemes);

        System.out.println("schemes=" + String.join(",", schemes));
        System.out.println("hasFile=" + schemes.contains("file"));
        System.out.println("hasJar=" + schemes.contains("jar"));
        System.out.println("providerCount=" + providers.size());
        System.out.println("uniqueSchemes=" +
                (new HashSet<>(schemes).size() == schemes.size()));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ProviderCatalogDemo.java
java ProviderCatalogDemo
```

**Stdout đã kiểm tra trên JDK 24 Windows dùng để chạy mã `--release 17`:**

```text
schemes=file,jar,jrt
hasFile=true
hasJar=true
providerCount=3
uniqueSchemes=true
```

### 6.1. Output nào là bất biến, output nào phụ thuộc runtime?

- `hasFile=true`: default provider luôn có scheme `file`.
- `uniqueSchemes=true`: cơ chế discovery loại providers trùng scheme được phát hiện.
- `schemes=file,jar,jrt`, `hasJar=true`, `providerCount=3`: **quan sát của môi trường QA**, không phải danh sách mặc định được hứa cho mọi JDK/custom runtime.
- `Collections.sort` chỉ giúp hiển thị ổn định theo tên; nó không làm thay đổi thứ tự gốc hay thứ tự ưu tiên providers.

Nếu chạy trên runtime không đóng gói ZIP provider, `jar` có thể không hiện diện. Khi đó cần bổ sung đúng module/dependency, không sửa code bằng cách tự tạo một scheme giả.

### 6.2. Java 7 vs tiện ích dùng trong ví dụ

`FileSystemProvider.installedProviders()`, `ArrayList` và `Collections.sort` đều sẵn từ trước/Java 7. `String.join` được thêm từ Java 8; bài chạy Java 17 nên hợp lệ. Nếu thật sự viết một chương trình tương thích Java 7, bạn cần thay `String.join` bằng builder/formatter phù hợp.

## 7. URI scheme: `file:`, `jar:` và đường dẫn bên trong archive

Một URI có scheme dùng để chỉ provider cho filesystem:

```text
file:///C:/data/report.txt
jar:file:///C:/data/archive.zip
jar:file:///C:/data/archive.zip!/docs/hello.txt
```

Các chuỗi trên **chỉ mang tính minh họa cấu trúc trên Windows**. Trong code portable, không nối chuỗi `"file:/..."` từ một đường dẫn chứa khoảng trắng hoặc ký tự đặc biệt. Nên lấy URI filesystem ngoài từ `zipPath.toUri()`:

```java
Path zipPath = Path.of("archive.zip").toAbsolutePath();
URI zipUri = URI.create("jar:" + zipPath.toUri());
```

Đây là mảnh minh họa, cần imports `URI`, `Path`. `Path.toUri()` xử lý URI encoding của đường dẫn tốt hơn việc tự ghép ổ đĩa, slash và spaces.

### 7.1. Hai cấp nhận diện: archive container và entry bên trong

Với ZIP:

- `zipPath` trên default filesystem chỉ tới **file archive.zip**.
- `zipUri` với `jar:` xác định ZIP filesystem muốn mở.
- `zipFs.getPath("/docs/hello.txt")` chỉ tới **entry** bên trong ZIP.
- `entry.toUri()` có thể tạo URI dùng scheme `jar` và dấu phân cách `!/`; format cụ thể tuân theo provider.
- `Path.of(entryUri)` có thể yêu cầu ZIP filesystem đã được mở; không phải lời hứa provider luôn tự tạo instance.

**Một container ZIP không đồng nghĩa một directory của default filesystem.** Nó là file thông thường đối với provider `file` nhưng có thể là một cây tệp đối với provider `jar`.

### 7.2. `Path.toString` không chứa đủ provider identity

Một ZIP path có thể in là `/docs/hello.txt`. Nếu gửi chuỗi ấy vào:

```java
Path incorrect = Path.of("/docs/hello.txt");
```

bạn đã tạo một path thuộc default filesystem, **không còn biết archive nào**. Đừng serialize/chuyển đổi `Path` giữa providers bằng `toString()` rồi kỳ vọng vẫn trỏ cùng resource.

## 8. Tạo một FileSystem bổ sung

Các factory methods cơ bản:

| API | Việc cần làm | Điểm chú ý |
| --- | --- | --- |
| `FileSystems.getDefault()` | Lấy default FS | Không tạo ZIP FS |
| `FileSystems.getFileSystem(URI)` | Lấy FS **đã tồn tại** theo URI | Có thể ném `FileSystemNotFoundException` |
| `FileSystems.newFileSystem(URI, Map)` | Tạo/mở FS instance bằng URI scheme/provider | Có từ Java 7, env provider-specific |
| `FileSystems.newFileSystem(URI, Map, ClassLoader)` | Tạo FS có thêm provider lookup theo class loader | Có từ Java 7; dùng khi thực sự cần |
| `FileSystems.newFileSystem(Path, ClassLoader)` | Mở file-as-filesystem qua path/provider | Có từ Java 7 |
| `FileSystems.newFileSystem(Path, Map)` | Mở file-as-filesystem qua Path + env | **Có từ Java 13** |
| `FileSystems.newFileSystem(Path)` | Mở file-as-filesystem với env rỗng | **Có từ Java 13** |
| `FileSystems.newFileSystem(Path, Map, ClassLoader)` | Mở qua Path + env + class loader | **Có từ Java 13** |

**Không nhầm overload:** Những đoạn code sử dụng `FileSystems.newFileSystem(zipPath, Map.of())` là mã Java 13+ trong bài. Khi cần minh họa API có từ Java 7, `FileSystems.newFileSystem(zipUri, env)` là factory đã tồn tại, với một provider thích hợp.

### 8.1. `newFileSystem` khác `getFileSystem` thế nào?

`FileSystems.newFileSystem(uri, env)` yêu cầu provider **tạo một instance**. Nếu một instance tương ứng đang mở và provider không cho phép instance thứ hai với cùng URI, bạn có thể gặp `FileSystemAlreadyExistsException`.

`FileSystems.getFileSystem(uri)` chỉ **lấy instance đã tồn tại**, không tự tạo mới. Nếu chưa có instance, có thể gặp `FileSystemNotFoundException`. Nếu scheme chưa có provider, đó lại là `ProviderNotFoundException`.

Sau khi một FileSystem được đóng, việc `getFileSystem(uri)` trả reference đã đóng hay ném exception phụ thuộc provider. Trong ZIP provider kiểm thử, sau close, lookup ném `FileSystemNotFoundException`.

### 8.2. Environment map phụ thuộc provider

`env` trong `newFileSystem` không có một schema “toàn Java” chung. Ví dụ với ZIP provider:

```java
Map<String, String> env = Map.of("create", "true");
FileSystem zipFs = FileSystems.newFileSystem(zipUri, env);
```

`create=true` là option của **ZIP filesystem provider**, không có nghĩa `FileSystems.newFileSystem` với mọi provider đều chấp nhận key `"create"`.

Các environment properties khác cũng do provider định nghĩa. Đọc tài liệu chính thức của provider và không nhồi mọi config option vào tất cả file systems.

## 9. ZIP/JAR as FileSystem: `jdk.zipfs` còn hiện hành

Java hiện đại cung cấp module **`jdk.zipfs`** triển khai ZIP/JAR filesystem provider. Module này ánh xạ nội dung của một ZIP/JAR thành một **FileSystem** mà bạn có thể dùng `Files` và `Path`.

- Module: `jdk.zipfs`.
- Provider scheme: `jar`.
- Mở archive đã có hoặc tạo archive mới qua `FileSystems.newFileSystem`.
- Đọc file entry bằng `Files.readString`, `Files.newInputStream` hoặc `Files.readAllBytes`.
- Tạo directory entry bằng `Files.createDirectories`.
- Ghi entry bằng `Files.writeString`, `Files.write` hoặc streams/channels theo tính năng provider.
- Duyệt bằng `Files.walk`/`Files.walkFileTree` khi phù hợp.
- Đóng instance bằng `FileSystem.close()`/try-with-resources.

**Lưu ý phiên bản:** API `FileSystemProvider` và kiến trúc `FileSystems` ra đời từ Java 7. Tên module `jdk.zipfs` thuộc hệ thống module **Java 9+**. Không khẳng định module Java 9 đã tồn tại theo đúng tên/hệ module trong Java 7; cũng không coi ZIP filesystem provider là tính năng đã bị bỏ trên Java 17+.

### 9.1. `jdk.zipfs` không nhất thiết có ở mọi runtime image

Một JDK đầy đủ thường đóng gói ZIP provider, nhưng runtime được tạo bằng `jlink`/module selection có thể không chứa `jdk.zipfs`. Khi đó:

- Scheme `jar` có thể không nằm trong `installedProviders()`.
- `FileSystems.newFileSystem(jarUri, env)` có thể ném `ProviderNotFoundException`.
- Cần đóng gói runtime đúng module/provider, hoặc dùng chiến lược được sản phẩm hỗ trợ.

**Không sử dụng class nội bộ `jdk.nio.zipfs.*` làm API ứng dụng.** Code portable nên dùng `FileSystems`, `Files` và public provider/zipfs documentation.

### 9.2. ZIP được xem là cây tệp, không phải thư mục OS thông thường

Khi ZIP đang được mở:

```text
archive.zip  (regular file trên default FS)
   |
   +-- /docs
   |    |
   |    +-- hello.txt
   |
   +-- /images
        |
        +-- logo.png
```

`zipFs.getPath("/")` là root của archive, không phải root `C:\` hay `/` của default OS filesystem. Chuỗi `"/"` có thể xuất hiện ở hai filesystems, nhưng chúng thuộc các **không gian tên khác nhau**.

## 10. Chương trình C — Tạo ZIP, ghi entry, đóng và mở lại

Lưu **`ZipCreateDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Map;

public final class ZipCreateDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("zip-create-");
        Path zip = dir.resolve("archive.zip");
        URI uri = URI.create("jar:" + zip.toUri());

        try {
            try (FileSystem archive =
                         FileSystems.newFileSystem(
                                 uri, Map.of("create", "true"))) {
                Path folder = archive.getPath("/docs");
                Files.createDirectory(folder);
                Path entry = folder.resolve("hello.txt");
                Files.writeString(
                        entry, "alpha", StandardCharsets.UTF_8);

                System.out.println("insideScheme=" +
                        archive.provider().getScheme());
                System.out.println("innerRoot=/" +
                        (entry.getRoot() != null));
                System.out.println("innerIsRegular=" +
                        Files.isRegularFile(entry));
                System.out.println("innerContent=" +
                        Files.readString(
                                entry, StandardCharsets.UTF_8));
                System.out.println("insidePathDefault=" +
                        (entry.getFileSystem() ==
                                FileSystems.getDefault()));
                System.out.println("insideSize=" + Files.size(entry));
            }

            System.out.println("zipExistsAfterClose=" +
                    Files.isRegularFile(zip));

            try (FileSystem archive =
                         FileSystems.newFileSystem(zip, Map.of())) {
                System.out.println("reopenContent=" +
                        Files.readString(
                                archive.getPath("/docs/hello.txt"),
                                StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(zip);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 ZipCreateDemo.java
java ZipCreateDemo
```

**Stdout đã xác minh trên JDK24 Windows, biên dịch với `--release 17`:**

```text
insideScheme=jar
innerRoot=/true
innerIsRegular=true
innerContent=alpha
insidePathDefault=false
insideSize=5
zipExistsAfterClose=true
reopenContent=alpha
```

### 10.1. Vì sao `insideScheme=jar`?

`archive.provider().getScheme()` cho biết provider tạo ZIP FileSystem là provider `jar`. Nó không biến ZIP file thành `file:` directory; archive container vẫn là một file thuộc default filesystem.

### 10.2. Dòng `innerRoot=/true` có nghĩa gì?

Ví dụ in chuỗi cố định `"innerRoot=/"` nối với biểu thức boolean `entry.getRoot() != null`. Vì vậy stdout đúng là **`innerRoot=/true`**, không phải giá trị `toString()` của root. Mục đích là xác nhận ZIP entry được tạo từ absolute internal path; root nằm trong archive.

### 10.3. Vì sao `insidePathDefault=false`?

`entry` do `archive.getPath(...)` tạo, thuộc ZIP FileSystem. Nó khác default FileSystem, dù đường dẫn bên trong có dạng `"/docs/hello.txt"` quen thuộc.

### 10.4. Vì sao cần `try-with-resources`?

`Zip FileSystem` là resource cần đóng. Việc đóng kết thúc tương tác với archive và cho provider hoàn tất các thao tác cần thiết; sau đó chương trình mới mở lại để xác minh dữ liệu đã được lưu.

Không mặc định một ZIP thay đổi xong đã bền vững/đã được transactionally commit ở mọi provider trước khi close. Nếu lỗi I/O khi close, code phải xử lý. **Đóng ZIP FileSystem không phải một giao dịch rollback/commit có bảo đảm atomic mặc định**.

### 10.5. Vì sao ví dụ dùng cả overload URI và Path?

- Tạo file ZIP mới: `FileSystems.newFileSystem(uri, Map.of("create","true"))` — factory URI có từ Java 7.
- Mở archive đã có: `FileSystems.newFileSystem(zip, Map.of())` — overload `Path, Map` có từ **Java 13**.

Điều này cố ý minh họa hai cách truy cập hợp lệ trong Java 17+, **không đánh đồng ngày xuất hiện của hai overload**.

### 10.6. Vì sao chỉ xóa file tạm do test tạo?

`Files.createTempDirectory` tạo nơi thử nghiệm độc lập, `archive.zip` được tạo bên trong nó. `finally` chỉ xóa **container archive và folder ấy**, không đụng ZIP cá nhân hay tài liệu thật.

## 11. URI và Path factory: lúc nào có thể dùng `Path.of(URI)`?

Giả sử một ZIP instance đã được mở bằng:

```java
URI zipUri = URI.create("jar:" + zipPath.toUri());
FileSystem zipFs = FileSystems.newFileSystem(zipUri, Map.of());
```

Đây là mảnh minh họa cần ZIP có thật; để lấy entry:

```java
Path inner = zipFs.getPath("/docs/hello.txt");
```

Một URI entry có dạng provider-specific:

```text
jar:file:///somewhere/archive.zip!/docs/hello.txt
```

Và có thể chuyển lại thành `Path` khi provider/instance đã sẵn sàng:

```java
Path inner = Path.of(
        URI.create(zipUri.toString() + "!/docs/hello.txt"));
```

Đây là **mảnh minh họa**: `zipUri` phải đúng định dạng của ZIP provider; nếu instance chưa mở, `Path.of(URI)` có thể bị từ chối hoặc thử tạo tự động tùy provider. Không coi `Path.of(jarUri)` là sự thay thế chung cho lifecycle `newFileSystem`.

### 11.1. Đọc `FileSystems.getFileSystem` đúng bản chất

`FileSystems.getFileSystem(zipUri)` là lookup **instance tồn tại**. Nó không tự tạo ZIP file khi chưa có.

Nếu thiết kế một library có nhiều caller:

- Xác định **ai sở hữu** ZIP FileSystem.
- Chỉ một layer tạo/đóng instance hay có shared ownership contract.
- Những layer dùng `getFileSystem` phải biết instance có thể bị đóng bởi owner.
- Không giả định “get” luôn thành công chỉ vì file ZIP container tồn tại.
- Nếu cần mở mỗi lần trong một scope ngắn, chọn factory mới và quản lý `AlreadyExists` một cách rõ.

### 11.2. Race giữa nhiều threads gọi `newFileSystem`

Hai threads cùng tạo instance với cùng archive URI có thể cạnh tranh. Một thread thành công, thread khác nhận `FileSystemAlreadyExistsException`; xử lý ra sao tùy thiết kế ownership. Đừng catch exception rồi tùy tiện đóng một instance có thể đang được layer khác dùng.

## 12. Chương trình D — Lookup ZIP đã mở, duplicate và close

Lưu **`ZipUriLifecycleDemo.java`**:

```java
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public final class ZipUriLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("zip-uri-");
        Path zip = dir.resolve("named.zip");
        URI uri = URI.create("jar:" + zip.toUri());

        try {
            FileSystem fs = FileSystems.newFileSystem(
                    uri, Map.of("create", "true"));
            try {
                Files.writeString(fs.getPath("/hello.txt"), "OK");

                System.out.println("getExistingMatches=" +
                        (FileSystems.getFileSystem(uri) == fs));

                System.out.println("getFromJarPath=" +
                        Files.readString(Path.of(
                                URI.create(
                                        uri.toString() + "!/hello.txt"))));

                try {
                    FileSystems.newFileSystem(uri, Map.of());
                    System.out.println("duplicateRejected=false");
                } catch (FileSystemAlreadyExistsException expected) {
                    System.out.println("duplicateRejected=true");
                }
            } finally {
                fs.close();
            }

            System.out.println("closed=" + !fs.isOpen());

            try {
                FileSystems.getFileSystem(uri);
                System.out.println("closedMissing=false");
            } catch (FileSystemNotFoundException expected) {
                System.out.println("closedMissing=true");
            }
        } finally {
            Files.deleteIfExists(zip);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 ZipUriLifecycleDemo.java
java ZipUriLifecycleDemo
```

**Stdout đã xác minh:**

```text
getExistingMatches=true
getFromJarPath=OK
duplicateRejected=true
closed=true
closedMissing=true
```

### 12.1. Phân tích

- `getExistingMatches=true`: `getFileSystem(uri)` trả cùng instance đang mở.
- `getFromJarPath=OK`: khi ZIP instance hiện tồn tại, `Path.of(jarUriWithEntry)` trỏ đúng entry.
- `duplicateRejected=true`: ZIP provider kiểm thử từ chối tạo instance thứ hai cho cùng URI khi một instance đang mở.
- `closed=true`: sau `close()`, instance không mở nữa.
- `closedMissing=true`: ZIP provider kiểm thử không trả instance đã đóng khi lookup theo URI.

**Không khái quát hóa sai:** Java API nêu hành vi `getFileSystem(uri)` sau khi close là **provider-dependent**. Một custom provider có thể có contract khác. Luôn ghi điều đã kiểm chứng trong môi trường thử, rồi đối chiếu provider thực tế.

### 12.2. Vì sao không “giải quyết” duplicate bằng cách luôn gọi get rồi close?

Một instance có thể được share bởi nhiều components. Nếu bạn thấy `FileSystemAlreadyExistsException` rồi lấy instance hiện có và tự ý đóng nó, layer khác đang sử dụng có thể bị `ClosedFileSystemException`. Cần ownership/lifetime contract rõ ràng.

## 13. Provider mismatch: không phải mọi Path đều ghép được với nhau

Một trong những rủi ro lớn nhất khi dùng nhiều FileSystems là trộn các `Path` **không cùng provider**.

```java
Path osFile = Path.of("source.txt");       // Default FS.
Path zipEntry = zipFs.getPath("/copy.txt"); // ZIP FS.
```

Nếu gọi những method `Path` yêu cầu operands cùng provider, như `zipEntry.resolve(osFile)`, có thể gặp `ProviderMismatchException`. Đây là unchecked exception, subclass của `IllegalArgumentException`.

**Không chỉ cần chuỗi path “giống nhau” là đủ.** Provider identity là một phần semantic của `Path`.

### 13.1. Cách dùng đúng: tạo các Path trong filesystem của chúng

- Nguồn local: `Path.of(...)` hoặc `FileSystems.getDefault().getPath(...)`.
- Đích ZIP: `zipFs.getPath("/...")`.
- Ghép ZIP path với **chuỗi hoặc một ZIP-relative Path thuộc cùng ZIP filesystem**.
- Không dùng `osPath.resolve(zipEntry)` hoặc `zipEntry.resolve(osPath)` như thao tác chuyển provider.
- Khi cần chuyển dữ liệu giữa providers, sử dụng API hỗ trợ cross-provider copy hoặc stream.

### 13.2. `Files.copy` có thể copy giữa providers

Khác với `Path.resolve`, `Files.copy(source, target)` được định nghĩa để thao tác với hai paths, và Java `Files` có cơ chế hỗ trợ copy khi providers khác nhau.

Tuy nhiên:

- Có thể sao chép **nội dung regular file** giữa default và ZIP provider.
- Không hứa tự bảo toàn mọi metadata, permissions, symlink semantics và attribute views.
- Các options `COPY_ATTRIBUTES`, `REPLACE_EXISTING` hoặc `NOFOLLOW_LINKS` có nghĩa riêng, có thể gặp unsupported operation.
- Move giữa file stores/providers không được mặc định atomic.
- Nếu copy cả directory, phải tổ chức duyệt/copy con theo policy; một lệnh copy directory không có nghĩa copy toàn bộ cây đệ quy.
- Exception/partial state có thể xảy ra khi I/O thất bại.

`Files.copy` phù hợp khi bạn hiểu source/target và đã kiểm thử provider thực, chứ không phải một “migration transaction” chung.

### 13.3. `Path.toFile()` không portable

`java.io.File` chủ yếu tương tác với default filesystem. `Path.toFile()` có thể ném `UnsupportedOperationException` nếu path không thuộc default provider, như ZIP `Path` trong chương trình QA.

Vì vậy, một API library chỉ nhận `java.io.File` có thể không dùng trực tiếp với ZIP entries. Cân nhắc API nhận `Path` hoặc `InputStream`/`OutputStream`, tùy khả năng provider và nhu cầu business.

## 14. Chương trình E — Copy từ default FS vào ZIP FS

Lưu **`CrossProviderCopyDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Map;

public final class CrossProviderCopyDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("cross-provider-");
        Path source = dir.resolve("source.txt");
        Path zip = dir.resolve("store.zip");
        URI uri = URI.create("jar:" + zip.toUri());

        try {
            Files.writeString(
                    source, "COPY", StandardCharsets.UTF_8);

            try (FileSystem archive = FileSystems.newFileSystem(
                    uri, Map.of("create", "true"))) {
                Path entry = archive.getPath("/copy.txt");
                Files.copy(source, entry);

                System.out.println("copiedText=" +
                        Files.readString(entry));
                System.out.println("differentProviders=" +
                        (source.getFileSystem().provider() !=
                                entry.getFileSystem().provider()));

                try {
                    entry.resolve(source);
                    System.out.println("mixedResolveRejected=false");
                } catch (ProviderMismatchException expected) {
                    System.out.println("mixedResolveRejected=true");
                }

                try {
                    entry.toFile();
                    System.out.println("zipToFileUnsupported=false");
                } catch (UnsupportedOperationException expected) {
                    System.out.println("zipToFileUnsupported=true");
                }

                System.out.println("zipEntryIsAbsolute=" +
                        entry.isAbsolute());
            }

            System.out.println("sourceRemains=" +
                    Files.isRegularFile(source));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(zip);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CrossProviderCopyDemo.java
java CrossProviderCopyDemo
```

**Stdout đã kiểm chứng:**

```text
copiedText=COPY
differentProviders=true
mixedResolveRejected=true
zipToFileUnsupported=true
zipEntryIsAbsolute=true
sourceRemains=true
```

### 14.1. Giải thích

- `Files.copy(source, entry)` copy nội dung file local vào ZIP entry.
- `differentProviders=true` xác nhận hai paths khác providers.
- `entry.resolve(source)` bị từ chối bằng `ProviderMismatchException`; Java không hiểu phép ghép một path thuộc ZIP với một path default FS như phép chuyển namespace.
- `entry.toFile()` ném `UnsupportedOperationException` với ZIP Path.
- `entry.isAbsolute()` true **trong không gian tên của ZIP FS**.
- `sourceRemains=true`: copy không xóa source.

**Cẩn thận:** Code copy một file 4 byte. Đừng tự suy rằng copy một directory là copy mọi entry lồng nhau, hoặc `Files.move` qua providers có cùng tính atomic/metadata.

## 15. Đóng FileSystem: ảnh hưởng cả các Path đã tạo

`FileSystem` bổ sung có vòng đời rõ:

```text
newFileSystem(...) → open
    |
    +-- getPath(...)
    +-- Files.read/write/copy(...)
    +-- open streams/channels/iterators
    |
close() → closed
    |
    +-- thao tác I/O trên Path thuộc FS đó có thể lỗi
```

Java tài liệu quy định khi FileSystem đóng, nỗ lực tiếp tục truy cập những đối tượng thuộc FileSystem có thể ném `ClosedFileSystemException`.

### 15.1. `Path` object có thể còn trong bộ nhớ sau close

Một biến `Path` không tự biến mất khi FS đóng. Nhưng **nó không còn có quyền truy cập live filesystem**. Ví dụ:

```java
Path entry;
try (FileSystem fs = FileSystems.newFileSystem(zip, Map.of())) {
    entry = fs.getPath("/docs/a.txt");
}
// Không nên đọc entry bằng Files.readString(entry) ở đây.
```

Đây là **mảnh minh họa**, `zip` phải là ZIP có thật. Sau scope, file system đã đóng. Đừng trả về một `Path` thuộc FS vừa đóng cho caller rồi kỳ vọng họ đọc được nó.

### 15.2. Ownership pattern

Nếu một method trả `Path` tới ZIP entry:

- Hoặc **caller giữ FS còn mở** trong toàn bộ khoảng dùng path.
- Hoặc method trả **dữ liệu đã đọc** (byte[]/stream được quản lý) thay vì Path.
- Hoặc layer service quản lý **shared FS lifetime** với reference-count/ownership rõ.
- Không đóng FS sớm trong khi stream, channel, directory stream hoặc worker vẫn dùng archive.

### 15.3. Close không phải rollback transaction

Với ZIP, provider có thể thực hiện công việc ghi/đóng container khi `close`. Tuy vậy API không hứa **atomic transaction** cho hàng loạt thao tác trên archive. Nếu process crash hoặc storage lỗi giữa chừng, archive có thể bị lỗi hoặc chưa phản ánh mọi thay đổi.

Ứng dụng cần an toàn cao có thể ghi archive vào **file tạm**, xác minh, rồi thay container đích theo protocol phù hợp, xét hỗ trợ `ATOMIC_MOVE` và xử lý fallback lỗi. Không viết “close thành công = fsync mọi layer và commit atomically” khi không có bảo đảm ấy.

## 16. Chương trình F — Path thuộc FileSystem đã đóng

Lưu **`ClosedFileSystemDemo.java`**:

```java
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public final class ClosedFileSystemDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("zip-closed-");
        Path zip = dir.resolve("archive.zip");
        Path path;

        FileSystem archive = FileSystems.newFileSystem(
                URI.create("jar:" + zip.toUri()),
                Map.of("create", "true"));

        try {
            path = archive.getPath("/x.txt");
            Files.writeString(path, "OK");
            archive.close();

            System.out.println("fsClosed=" + !archive.isOpen());

            try {
                Files.readString(path);
                System.out.println("pathReadRejected=false");
            } catch (ClosedFileSystemException expected) {
                System.out.println("pathReadRejected=true");
            }

            System.out.println("zipContainerExists=" +
                    Files.exists(zip));
        } finally {
            archive.close();
            Files.deleteIfExists(zip);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ClosedFileSystemDemo.java
java ClosedFileSystemDemo
```

**Stdout:**

```text
fsClosed=true
pathReadRejected=true
zipContainerExists=true
```

### 16.1. Phân tích

- `Files.writeString(path,"OK")` thành công khi ZIP FS mở.
- Sau `archive.close()`, `isOpen()` false.
- `Files.readString(path)` trên Path đã giữ lại ném `ClosedFileSystemException` trong ZIP provider kiểm thử.
- File `archive.zip` trên default FS vẫn có: **đóng filesystem không xóa container**.
- `finally` chỉ dọn các files do test tạo.
- Trong dự án thật, ưu tiên try-with-resources cho ZIP FS thay vì gọi `close` bằng tay ở nhiều nhánh; demo gọi tường minh để minh họa hành vi.

### 16.2. Cần tránh vòng đời khó kiểm soát

Đừng đặt một `static Map<String, Path>` chứa ZIP paths rồi đóng tất cả ZIP FileSystems ngay sau khi tạo map. Khi caller dùng `Path` sau đó, chúng có thể không còn truy cập được. Nếu cache metadata, lưu giá trị cần thiết và archive identity; nếu cache live resources, quản lý sở hữu và shutdown riêng.

## 17. Các exception quan trọng khi dùng nhiều providers

| Exception | Khi thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ProviderNotFoundException` | URI scheme không có provider, hoặc không có provider nhận file type | Kiểm tra runtime/modules/SPI/config |
| `FileSystemNotFoundException` | Provider có nhưng instance theo URI chưa tồn tại/không còn lookup được | Phân biệt get vs new, quản lý lifecycle |
| `FileSystemAlreadyExistsException` | Yêu cầu tạo instance khi instance trùng URI đang có | Không mở lặp tùy tiện; quy định ownership |
| `ClosedFileSystemException` | Dùng `Path`/operation gắn FS đã đóng | Giữ FS mở trong scope sử dụng |
| `ProviderMismatchException` | Ghép/so sánh theo API không chấp nhận Paths từ providers khác | Tạo Paths cùng FS hoặc dùng copy/stream |
| `ReadOnlyFileSystemException` | Cố ghi vào FileSystem read-only | Tôn trọng read-only; không cố bypass |
| `UnsupportedOperationException` | Provider không hỗ trợ một operation (ví dụ ZIP Path.toFile()) | Chọn API portable/fallback |
| `IOException`, `ZipException` | Archive không hợp lệ, quyền, I/O lỗi, hỏng dữ liệu, thiếu file | Phân loại lỗi và không báo success giả |
| `FileAlreadyExistsException` | Tạo entry đang có hoặc copy không cho replace | Chính sách overwrite rõ ràng |
| `ServiceConfigurationError` | Provider cấu hình service loading lỗi | Kiểm tra build/module/service metadata |

Các exception từ `java.nio.file` có nhiều subtype; **không catch-all và coi mọi lỗi là “ZIP không tồn tại”**.

### 17.1. ProviderNotFound khác FileSystemNotFound

- **ProviderNotFound:** Không tìm thấy nhà cung cấp cho scheme/file type.
- **FileSystemNotFound:** Đã có provider phù hợp với scheme nhưng instance cụ thể chưa mở hoặc không thể truy xuất theo URI.
- **FileSystemAlreadyExists:** Muốn tạo instance đã tồn tại.
- **ClosedFileSystem:** Có Path/FS object nhưng nó đã bị đóng.

Đây là bốn nguyên nhân khác nhau, cần thông báo khác nhau. Một hệ thống logs nên ghi scheme, provider và loại lỗi (không lộ path nhạy cảm).

### 17.2. JDK ZIP provider có thể không có trong runtime tùy biến

Nếu `jar` thiếu, đừng “fix” bằng cách viết URI `file:` rồi gọi `getFileSystem` với hy vọng tự đọc ZIP entries. Phải đóng gói provider phù hợp hoặc dùng thư viện ZIP khác qua một API có contract riêng.

## 18. Chương trình G — Unknown URI scheme

Lưu **`UnknownSchemeDemo.java`**:

```java
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public final class UnknownSchemeDemo {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("nonexistingfs:///data");

        try {
            FileSystems.newFileSystem(uri, Map.of());
            System.out.println("newRejected=false");
        } catch (ProviderNotFoundException expected) {
            System.out.println("newRejected=true");
        }

        try {
            FileSystems.getFileSystem(uri);
            System.out.println("lookupRejected=false");
        } catch (ProviderNotFoundException expected) {
            System.out.println("lookupRejected=true");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 UnknownSchemeDemo.java
java UnknownSchemeDemo
```

**Stdout trên runtime kiểm thử:**

```text
newRejected=true
lookupRejected=true
```

### 18.1. Phân tích và giới hạn

- `nonexistingfs` là scheme được chọn để không trùng với những providers có trong môi trường QA.
- `newFileSystem` không tìm thấy provider tương ứng → `ProviderNotFoundException`.
- `getFileSystem` cũng không có provider → lỗi cùng loại trong test.
- Một ứng dụng có thể cố ý cài một custom provider mang scheme ấy; khi đó output có thể khác. **Lỗi không phải do chuỗi URI “bị Java cấm cố định”**, mà do không có provider hỗ trợ trong runtime hiện tại.

Bài học: xử lý provider discovery ở deployment, không dựa vào khái niệm “Java tự hiểu mọi scheme”.

## 19. Attribute views khác nhau theo FileSystem

Một `FileSystem` công bố các attribute views mà nó hỗ trợ:

```java
Set<String> names = fs.supportedFileAttributeViews();
```

Ở default provider trên OS, tập có thể gồm `basic` và những views như `dos`, `acl`, `posix` tùy filesystem. ZIP provider trong `jdk.zipfs` có view `basic` và `zip`, trong đó `zip:permissions` mô tả permissions tùy chọn lưu trong ZIP metadata.

### 19.1. Zip `zip:permissions` không phải authorization policy

Tài liệu `jdk.zipfs` mô tả view `zip` cho một thuộc tính permissions dạng `Set<PosixFilePermission>`. ZIP provider **không enforce** các permissions lưu trong ZIP entry như quyền của OS filesystem. Do đó:

- Có thể lưu/đọc metadata permissions trong archive.
- Không được coi các bits permission ấy là biện pháp cách ly người dùng bên trong ZIP.
- Quyền đọc/ghi archive container vẫn chịu sự kiểm soát của OS/provider bên ngoài.
- Khi giải nén sang filesystem đích, việc áp dụng metadata permissions phải theo chính sách riêng.

### 19.2. POSIX view trong ZIP không mặc định bật

Theo tài liệu Java 17, ZIP filesystem có thể hỗ trợ `PosixFileAttributeView` khi tạo với property:

```java
Map<String, String> env =
        Map.of("enablePosixFileAttributes", "true");
```

Đây là **mảnh minh họa** về provider config, không phải khuyến nghị bật mọi lúc. Các thông tin owner/group của ZIP có hạn chế persistence; permission bits có contract riêng. Chỉ bật khi ứng dụng cần và đã xác minh semantics/provider.

### 19.3. Không dùng provider-level capability để suy ra quyền

`supportedFileAttributeViews().contains("basic")` cho biết FS công bố view, **không** có nghĩa caller được phép đọc/ghi mọi path bên trong.

`fs.isReadOnly() == false` cũng không đảm bảo một file cụ thể có quyền ghi trong hoàn cảnh hiện tại. Quyền, locks, file state và I/O errors vẫn có thể từ chối thao tác.

## 20. Chương trình H — Basic metadata và ZIP view

Lưu **`FileSystemViewsDemo.java`**:

```java
import java.net.URI;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Map;

public final class FileSystemViewsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("zip-views-");
        Path zip = dir.resolve("archive.zip");

        try {
            try (FileSystem archive = FileSystems.newFileSystem(
                    URI.create("jar:" + zip.toUri()),
                    Map.of("create", "true"))) {
                Path inner = archive.getPath("/entry.txt");
                Files.writeString(inner, "XYZ");

                BasicFileAttributes attrs = Files.readAttributes(
                        inner, BasicFileAttributes.class);

                System.out.println("innerRegular=" +
                        attrs.isRegularFile());
                System.out.println("innerSize=" + attrs.size());
                System.out.println("supportsBasic=" +
                        archive.supportedFileAttributeViews()
                                .contains("basic"));
                System.out.println("supportsZipView=" +
                        archive.supportedFileAttributeViews()
                                .contains("zip"));
                System.out.println("separator=" +
                        archive.getSeparator());
                System.out.println("openDuringUse=" + archive.isOpen());
            }

            System.out.println("containerSizePositive=" +
                    (Files.size(zip) > 0));
        } finally {
            Files.deleteIfExists(zip);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 FileSystemViewsDemo.java
java FileSystemViewsDemo
```

**Stdout đã kiểm chứng với `jdk.zipfs`:**

```text
innerRegular=true
innerSize=3
supportsBasic=true
supportsZipView=true
separator=/
openDuringUse=true
containerSizePositive=true
```

### 20.1. Vì sao hai lớp metadata khác nhau?

- `attrs.size() == 3` là kích thước nội dung entry `XYZ`.
- `Files.size(zip) > 0` đo kích thước **container ZIP** bên ngoài, thường lớn hơn vì có ZIP headers/central directory và metadata.
- `archive.supportedFileAttributeViews()` công bố capability của ZIP FileSystem.
- `archive.getSeparator() == "/"` trên ZIP provider trong ví dụ; default OS filesystem có thể dùng separator khác.
- `archive.isOpen() == true` trong scope try-with-resources.

Đừng cộng kích thước entries rồi giả sử bằng byte size của container. Nén, metadata, directory entries và cấu trúc ZIP ảnh hưởng kết quả.

## 21. FileSystem APIs: chọn theo khả năng provider

| Tình huống | API thường dùng | Điều phải xác minh |
| --- | --- | --- |
| Làm việc với file OS thông thường | `FileSystems.getDefault()`, `Path.of`, `Files.*` | Quyền filesystem, charset, symlinks |
| Liệt kê providers hiện có | `FileSystemProvider.installedProviders()` | Scheme nào thật sự được đóng gói |
| Tạo/mở ZIP mới bằng URI | `FileSystems.newFileSystem(jarUri, env)` | `jar` provider, env `create`, path archive |
| Mở ZIP đã có bằng Path (Java 13+) | `FileSystems.newFileSystem(zipPath, Map.of())` | Runtime/API version và provider hỗ trợ file |
| Lấy ZIP instance đang mở | `FileSystems.getFileSystem(jarUri)` | Instance có trong registry; lifetime |
| Lấy entry trong ZIP | `zipFs.getPath("/...")` | Dùng đúng ZIP FileSystem |
| Đọc/ghi entry | `Files.newInputStream`, `Files.write`, `Files.readString` | Features/provider/permissions |
| Copy local → ZIP | `Files.copy(localPath, zipEntry)` | Đích không tồn tại, copy options, I/O |
| Duyệt ZIP | `Files.walkFileTree` hoặc `Files.walk` | Đóng stream khi dùng walk, giới hạn depth |
| Kiểm tra metadata | `Files.readAttributes` | Supported views, timestamp/permissions semantics |
| Ngừng dùng ZIP | `zipFs.close()` | Đóng các stream/consumers, xử lý close error |
| Gọi API cần `java.io.File` | Chỉ thích hợp với default FS hoặc có adapter | ZIP Path.toFile có thể unsupported |

### 21.1. Khi nào dùng `java.util.zip` thay ZIP FileSystem?

`java.util.zip.ZipFile` / `ZipInputStream` / `ZipOutputStream` vẫn là APIs hợp lệ, hiện hành. ZIP FileSystem phù hợp khi bạn muốn làm việc với entries **như cây Path** bằng NIO.2, còn ZIP stream APIs phù hợp khi bạn muốn xử lý các entries theo dòng dữ liệu, streaming hoặc tích hợp pipeline archive ở mức thấp hơn.

Không đánh giá hai API theo “cũ = bỏ” chỉ dựa trên lịch sử ra đời. Chọn theo nhu cầu:

- Cần paths, copy, attributes, directory traversal: ZIP FileSystem.
- Cần xử lý streaming tuần tự, archive entries và dữ liệu nén: ZIP stream APIs.
- Cần tính năng ZIP không được `jdk.zipfs` hỗ trợ: cân nhắc thư viện được bảo trì, kiểm tra bảo mật và licensing.

### 21.2. ZIP FS không tự giải nén toàn bộ ra ổ đĩa

`FileSystems.newFileSystem` mở một cách nhìn vào archive. `Files.readString(zipEntry)` đọc nội dung một entry; `Files.copy(zipEntry, localTarget)` mới chuyển nội dung ra file OS theo thao tác copy cụ thể. Không nhầm “open ZIP FS” với “extract all entries”.

## 22. Làm việc với nhiều ZIP đồng thời

Một application có thể cần mở hai ZIP khác nhau:

```java
try (FileSystem left = FileSystems.newFileSystem(leftZip, Map.of());
     FileSystem right = FileSystems.newFileSystem(rightZip, Map.of())) {
    Path a = left.getPath("/config/app.json");
    Path b = right.getPath("/config/app.json");
    // a và b có cùng chuỗi nội bộ nhưng thuộc hai FileSystems khác nhau.
}
```

Đây là **mảnh minh họa Java 13+**, cần `leftZip`/`rightZip` là những ZIP archives có thật; phải xử lý `IOException`.

Đừng lưu `a.toString()` rồi dùng nó để nhận diện duy nhất entry, bởi hai archives có thể có cùng internal path. Một identifier logic cần **archive identity + internal entry path** — ví dụ một object chứa URI/container ID và path bên trong, đồng thời có security policy.

### 22.1. Khi nhiều requests cùng xử lý một ZIP

Nếu bạn mở ZIP trên mỗi request trong server, có thể gặp duplicate instance hoặc I/O contention. Hai mô hình thường gặp:

- **Scope riêng:** Tác vụ mở, làm việc và đóng trong một block, bảo đảm không có task khác dùng cùng archive instance.
- **Shared manager:** Một component mở instance và cấp quyền truy cập có kiểm soát, chỉ đóng khi không còn consumer.

Không trộn hai mô hình rồi bắt `FileSystemAlreadyExistsException` làm control flow để “ai cũng có thể close”. Ownership phải được quy định bằng contract.

### 22.2. ZIP đang được ghi bởi process khác

`FileSystem` không tự giải quyết mọi consistency race. Nếu một process bên ngoài sửa container ZIP trong lúc provider đang mở, behavior có thể không đồng bộ hoặc gây lỗi. Nên dùng quy trình tạo archive tạm + publish khi hoàn tất, hoặc khóa/phối hợp thích hợp nếu hệ thống có nhiều writers.

## 23. URI encoding, dấu `!/` và separator

ZIP URI thường xuất hiện dưới dạng:

```text
jar:file:///some/path/archive.zip!/docs/hello.txt
```

Nhưng không nên tự ghép tên file có khoảng trắng/ký tự Unicode bằng cách nối `"jar:file:" + rawFilePath` vì URI escaping có thể sai.

Tốt hơn:

```java
URI jarFsUri = URI.create("jar:" + zipPath.toUri());
FileSystem zipFs = FileSystems.newFileSystem(jarFsUri, Map.of());
Path entry = zipFs.getPath("/docs/hello.txt");
```

Đây là **mảnh minh họa**, cần archive đã có và xử lý lifecycle. Khi muốn chuyển entry path sang URI, có thể dùng `entry.toUri()` rồi xử lý theo contract của provider.

**Không nhầm phân cách ZIP-internal path `/` với OS separator**: đó là quy tắc của ZIP filesystem, không phải yêu cầu dùng `/` để hardcode toàn bộ các đường dẫn hệ điều hành.

### 23.1. Khi resource path chứa ký tự đặc biệt

`Path.toUri` sẽ cung cấp URI biểu diễn path theo provider; rồi `URI.create("jar:"+uri)` cho ZIP provider. Với tên internal entry, dùng `zipFs.getPath` để provider parse theo rules của ZIP path, không tạo “jar URI” bằng string raw dựa trên input không tin cậy.

Nếu một ứng dụng nhận archive URI từ người dùng, không mở tùy ý remote/local resources chỉ vì chúng có prefix `jar:`. Cần whitelist scheme, authority, allowed container và access policy.

## 24. Lỗi runtime và tình huống khó

### 24.1. `ProviderNotFoundException`

Nguyên nhân có thể là runtime thiếu module `jdk.zipfs`, scheme sai, hoặc custom provider chưa được cài/đăng ký. Kiểm tra `installedProviders`, module packaging, classpath/module path và logs.

### 24.2. `FileSystemAlreadyExistsException`

Đã mở cùng archive URI; tránh tạo lại hoặc tự ý đóng instance mà component khác sở hữu. Quản lý lifecycle rõ ràng.

### 24.3. `FileSystemNotFoundException`

Gọi `getFileSystem(jarUri)` khi provider chưa có instance. Sự tồn tại của `archive.zip` trên OS không tự biến nó thành instance ZIP FS đang mở.

### 24.4. `ClosedFileSystemException`

Giữ một ZIP Path sau khi try-with-resources đóng ZIP. Di chuyển các thao tác đọc/ghi vào scope, hoặc trả dữ liệu đã đọc trước khi đóng.

### 24.5. `ProviderMismatchException`

`Path.resolve(otherPath)` với Paths thuộc providers khác. Nếu cần copy dữ liệu, dùng `Files.copy` hoặc stream, không resolve hai namespace.

### 24.6. `UnsupportedOperationException`

Có thể gặp khi chuyển ZIP Path sang `File` hoặc gọi operation không được provider hỗ trợ. Dùng public capability checks và fallback phù hợp.

### 24.7. `ZipException` hoặc `IOException` khi archive không hợp lệ

ZIP hỏng, không phải ZIP, entry metadata bất thường, permission bị từ chối, file đang bị thay hoặc storage lỗi có thể làm open/đọc/close thất bại. Không catch mọi lỗi rồi ghi “archive rỗng”; cần phân loại và báo rõ dữ liệu không đọc được.

### 24.8. `ReadOnlyFileSystemException`

Một filesystem có thể chỉ đọc. `fs.isReadOnly()` cung cấp thông tin mức filesystem, nhưng chưa thay thế quyền thực tế trên file/entry/container. Với provider read-only, không nên cố ghi hoặc bypass.

### 24.9. Kỳ vọng mọi ZIP file đều mở được

Tài liệu `jdk.zipfs` cho Java 17 nêu provider không hỗ trợ mở một existing ZIP chứa entry có thành phần tên `"."` hoặc `".."`. Đừng giả định một archive do nguồn không tin cậy tạo sẽ luôn parse thành path tree hợp lệ. Cần xử lý lỗi nhập liệu và policy an toàn.

## 25. Bảo mật khi xử lý ZIP/JAR từ nguồn không tin cậy

### 25.1. ZIP Slip và path traversal

Một archive độc hại có thể chứa entry names bất thường, ví dụ `../../outside.txt`. Nếu ứng dụng tự duyệt archive entries rồi ghi ra filesystem bằng cách ghép tên một cách ngây thơ, có nguy cơ ghi ngoài directory đích.

Hướng xử lý khi extract:

1. Chọn base directory đã được ủy quyền.
2. Với mỗi entry name, kiểm tra absolute/root/`..` và path components không hợp lệ.
3. Resolve + normalize trong base, kiểm tra containment ở cấp lexical.
4. Không dựa **chỉ** vào lexical `startsWith` để chống symlink ở directory trung gian hoặc races.
5. Cân nhắc APIs relative-to-directory handles khi threat model có attacker kiểm soát entries.
6. Không tự dùng permission/owner từ ZIP để mở rộng quyền ngoài ý muốn.
7. Chỉ tạo/ghi files thuộc scope đã cho phép.

`jdk.zipfs` từ chối mở existing ZIP có các thành phần tên `"."` hoặc `".."` theo tài liệu Java 17, nhưng điều này **không thay thế toàn bộ security policy** cho custom providers, thư viện ZIP khác, symlinks, absolute paths, đường dẫn xung đột hoặc file extraction ở OS.

### 25.2. ZIP bomb và resource exhaustion

Một ZIP có thể rất nhỏ khi nén nhưng giải nén thành lượng dữ liệu lớn. Trước khi trích xuất/đọc vào memory, đặt giới hạn:

- Tổng số entry.
- Kích thước uncompressed cho mỗi entry và tổng.
- Thời gian xử lý và số threads.
- Độ sâu cây thư mục.
- Tổng bytes được đọc/ghi trên output.
- Số archive instances được mở đồng thời.
- Dung lượng ổ đĩa còn lại và quota nghiệp vụ.

Không gọi `Files.readAllBytes(zipEntry)` trên một entry lớn chưa kiểm soát size rồi tin rằng archive container nhỏ sẽ an toàn.

### 25.3. Không tin metadata và file types từ archive

JAR có thể chứa executable bytecode hoặc resources nhạy cảm. Việc một entry tên `readme.txt` không đảm bảo nội dung là text an toàn. Nếu phải parse, giải nén, biên dịch hoặc chạy file từ archive, cần kiểm tra định dạng, charset, trusted source, hash/signature và quyền của caller.

### 25.4. Không coi ZIP permissions là hệ thống phân quyền

ZIP metadata permissions có thể được lưu nhưng ZIP FS không enforce các permission bits ấy như ACL OS. Giới hạn truy cập phải đến từ hệ thống/application và quyền trên container/output.

## 26. Bộ checklist khi đóng gói runtime

Đặc biệt với runtime tối giản hoặc ứng dụng module hóa:

- [ ] Biết app dùng scheme `file`, `jar` hay scheme của thư viện ngoài.
- [ ] Kiểm tra `jdk.zipfs` có trong runtime nếu cần ZIP FS.
- [ ] Không dùng class JDK nội bộ `jdk.nio.zipfs.*`.
- [ ] Kiểm tra third-party provider được đăng ký qua service mechanism đúng.
- [ ] Test `installedProviders()` trong **runtime deploy**, không chỉ JDK dev.
- [ ] Kiểm tra overload được gọi có tồn tại trên mức Java target.
- [ ] Dùng `--release 17` để phát hiện API không hợp với target Java 17.
- [ ] Không giả định `Path.of` (Java 11) hoặc `newFileSystem(Path,Map)` (Java 13) tồn tại ở Java 7.
- [ ] Xử lý thiếu provider một cách tường minh, không giả lập ZIP Path bằng default path.
- [ ] Đóng ZIP FS instances và streams, không đóng default FS.
- [ ] Test ZIP với đường dẫn có khoảng trắng/ký tự Unicode.
- [ ] Test read-only, corrupted ZIP, archive trống, archive entry nested.
- [ ] Test provider mismatch khi dùng Path/Files APIs.
- [ ] Giới hạn tài nguyên khi đọc archive không tin cậy.

## 27. Bài tập thực hành

**Bài 1 — Năm khái niệm.** Phân biệt `FileSystemProvider`, `FileSystem`, `Path`, `Files` và `FileStore`. Chỉ ra đối tượng nào biểu diễn URI scheme.

**Bài 2 — Default.** In `FileSystems.getDefault().provider().getScheme()`, sau đó kiểm tra `Path.of("test.txt").getFileSystem() == FileSystems.getDefault()`.

**Bài 3 — Provider list.** Dùng `FileSystemProvider.installedProviders()` để in các scheme theo thứ tự alphabet. Vì sao không thể hardcode rằng luôn đúng ba providers?

**Bài 4 — ZIP module.** Module nào cung cấp ZIP provider trên JDK hiện đại? Scheme là gì? Khi runtime jlink thiếu module, chuyện gì có thể xảy ra?

**Bài 5 — Tạo ZIP.** Tạo archive mới trong temp directory bằng `FileSystems.newFileSystem(URI.create("jar:"+zip.toUri()), Map.of("create","true"))`, tạo `/docs` và ghi `hello.txt`.

**Bài 6 — Mở lại.** Sau khi close ZIP, mở lại qua `FileSystems.newFileSystem(zipPath, Map.of())` và xác minh entry. Overload này có từ Java mấy?

**Bài 7 — URI.** Với một archive ở đường dẫn có khoảng trắng, vì sao nên lấy `zipPath.toUri()` thay vì tự nối `"jar:file:"` với raw path?

**Bài 8 — Lookup.** So `getFileSystem(uri)` với `newFileSystem(uri,env)`. Nếu ZIP container tồn tại nhưng chưa có instance đang mở, `getFileSystem` có buộc thành công không?

**Bài 9 — Duplicate.** Cùng URI archive đã mở, gọi `newFileSystem(uri,Map.of())` lần nữa. Exception nào đã quan sát với ZIP provider? Có nên tự đóng instance mà code khác đang dùng không?

**Bài 10 — Path identity.** Hai ZIP khác nhau đều có `/docs/config.yaml`. Vì sao `Path.toString()` không đủ làm khóa nhận diện entry?

**Bài 11 — Provider mismatch.** Vì sao `zipEntry.resolve(localPath)` có thể ném `ProviderMismatchException`? Cách copy nội dung local file vào ZIP là gì?

**Bài 12 — `java.io.File`.** Gọi `zipEntry.toFile()` có luôn được hỗ trợ không? API nào phù hợp hơn khi library cần đọc entry trong ZIP?

**Bài 13 — Close.** Giữ `Path` trong một ZIP FileSystem đã đóng rồi gọi `Files.readString`. Điều gì xảy ra trong demo? Làm sao thiết kế API trả dữ liệu mà không trả dead Path?

**Bài 14 — Default close.** Vì sao không nên đưa `FileSystems.getDefault()` vào try-with-resources giống ZIP FS?

**Bài 15 — Basic attrs.** Đọc `BasicFileAttributes` từ ZIP entry, so `size()` của entry với `Files.size(zipContainer)`. Vì sao hai kích thước khác?

**Bài 16 — ZIP permission.** Nếu ZIP view chứa `zip:permissions`, các bits ấy có phải ACL được ZIP provider enforce không?

**Bài 17 — Read-only.** Vì sao `fs.isReadOnly()==false` chưa bảo đảm ghi một entry cụ thể sẽ thành công?

**Bài 18 — Unknown scheme.** Với `URI.create("nonexistingfs:///data")`, factory `newFileSystem` sẽ phản ứng thế nào khi không có provider?

**Bài 19 — Version.** Phân biệt ngày ra đời của `FileSystems.newFileSystem(URI,Map)`, module `jdk.zipfs` và overload `newFileSystem(Path,Map)`.

**Bài 20 — Remote provider.** Một third-party provider công bố scheme mới. Những gì cần kiểm tra trước khi ứng dụng dùng API `Files.copy` với Path của provider đó?

**Bài 21 — ZIP Slip.** Vì sao kiểm tra `normalize().startsWith(base)` vẫn chưa bảo đảm an toàn tuyệt đối nếu attacker có thể thay directory cha thành symlink?

**Bài 22 — ZIP bomb.** Nêu các giới hạn cần áp dụng trước khi đọc/giải nén ZIP từ nguồn ngoài.

**Bài 23 — Reopen.** Một component đã close ZIP FS, component khác giữ Path. Có nên catch `ClosedFileSystemException` rồi tự động dùng lại Path ấy không? Vì sao?

**Bài 24 — Multi-provider unit tests.** Hãy bổ sung test cho missing provider, duplicate instance, closed FS, cross-provider copy, unsupported toFile và invalid ZIP.

### Đáp án gợi ý

- **1:** Provider thực thi và có scheme; FileSystem là instance; Path là vị trí thuộc instance; Files dispatch operations; FileStore mô tả storage.
- **2:** Scheme mặc định `file`; `Path.of` tạo default path.
- **3:** Runtime/module/provider configuration khác nhau; danh sách không cố định.
- **4:** `jdk.zipfs`, scheme `jar`; thiếu provider có thể nhận `ProviderNotFoundException`.
- **5:** Dùng URI `jar:`, env `create=true`; thao tác entries qua `zipFs.getPath` và `Files`.
- **6:** Đóng xong mở lại bằng Path; overload `Path, Map` có từ **Java 13**.
- **7:** `Path.toUri` xử lý URI encoding và format của đường dẫn OS.
- **8:** `getFileSystem` lấy instance có sẵn; không tự tạo.
- **9:** `FileSystemAlreadyExistsException` với ZIP provider đã thử; không đóng instance không sở hữu.
- **10:** Cần archive identity + internal path, không chỉ string.
- **11:** Hai Path khác providers; dùng `Files.copy(local,zipEntry)` nếu providers hỗ trợ.
- **12:** Không portable; dùng `Path` hoặc streams.
- **13:** ZIP demo ném `ClosedFileSystemException`; quản lý lifetime hoặc trả dữ liệu trước close.
- **14:** Default FS không thể đóng theo contract.
- **15:** Entry size khác container ZIP size do nén/metadata/central directory.
- **16:** Không; ZIP FS không enforce ZIP permission bits.
- **17:** Provider/OS/permission/I/O vẫn quyết định thao tác thực.
- **18:** `ProviderNotFoundException` nếu scheme chưa được cài.
- **19:** URI factory NIO.2 Java 7; `jdk.zipfs` module Java 9+; Path/Map factory Java 13.
- **20:** Scheme/discovery, methods support, security, metadata, lifecycle và runtime deployment.
- **21:** Intermediate symlink/race không bị loại chỉ bởi lexical normalize/startsWith.
- **22:** Quota entry count, total/uncompressed size, time, depth, threads và disk.
- **23:** Không; Path vẫn thuộc FS đã đóng, cần một FS đang mở và tạo Path tương ứng mới.
- **24:** Test theo contract, không phụ thuộc OS implementation class names.

## 28. Lỗi sai thường gặp

### 28.1. Nghĩ `Files` chỉ hoạt động trên ổ đĩa vật lý

Sai. `Files` thường delegate cho provider gắn với `Path`; ZIP entries có thể được đọc bằng `Files`.

### 28.2. Nghĩ `FileSystemProvider` và `FileSystem` là cùng một object

Provider là nhà cung cấp triển khai/factory; FileSystem là instance, có lifecycle riêng. Một provider có thể tạo nhiều instances.

### 28.3. Dùng `Path.of("/docs/a.txt")` để chỉ entry ZIP

Nó tạo default path, không phải ZIP entry. Dùng `zipFs.getPath(...)`.

### 28.4. Nghĩ scheme `jar` phải tồn tại trên mọi custom runtime

Không. Module/provider có thể bị lược bỏ; kiểm tra `installedProviders()`.

### 28.5. Hardcode tên class `sun.nio.fs.*` hoặc `jdk.nio.zipfs.*`

Đó không phải API portable của ứng dụng. Dựa vào public `FileSystems`/`FileSystemProvider`.

### 28.6. Nghĩ `FileSystems.getFileSystem` tự mở ZIP

Nó lookup instance hiện có. Chưa mở thường sẽ gặp `FileSystemNotFoundException` với provider phù hợp.

### 28.7. Mở cùng URI nhiều lần mà không xử lý ownership

Có thể gặp `FileSystemAlreadyExistsException`. Đừng tự đóng shared FS của caller khác.

### 28.8. Đóng ZIP rồi trả Path ra khỏi scope

Path vẫn tồn tại nhưng I/O có thể ném `ClosedFileSystemException`.

### 28.9. Đóng default FileSystem như một ZIP FS

Default FileSystem không thể đóng. Chỉ quản lý lifecycle các FS bổ sung theo contract.

### 28.10. Dùng `zipEntry.resolve(localPath)` để chuyển data

`Path.resolve` không copy file và có thể ném `ProviderMismatchException` khi operands khác provider.

### 28.11. Coi `Files.copy` xuyên provider là atomic, giữ mọi metadata

Không có bảo đảm chung. File content có thể copy, nhưng attributes/options/atomicity cần xem provider.

### 28.12. Gọi `zipEntry.toFile()`

Có thể ném `UnsupportedOperationException`; dùng Path/Files hoặc streams.

### 28.13. Nhầm kích thước ZIP container với kích thước uncompressed entries

`Files.size(zipContainer)` đo bytes của archive; `BasicFileAttributes.size` của entry đo thông tin nội dung entry.

### 28.14. Cho rằng `zip:permissions` tự chặn truy cập đọc/ghi

ZIP provider không enforce các permission bits ấy; bảo vệ phải ở OS/application.

### 28.15. Bỏ qua dữ liệu ZIP không tin cậy

ZIP slip/bomb/entries lạ/overflow I/O có thể dẫn tới path escape, kiệt tài nguyên hoặc tệp hỏng. Phải có giới hạn và validation.

### 28.16. Dùng một file path string làm ID giữa nhiều archives

Cùng internal path có thể nằm trong nhiều ZIP FS, mỗi path thuộc instance khác nhau. Cần archive identity.

### 28.17. Nhầm phiên bản Java

`Map.of` từ Java 9, `Path.of` và `Files.readString/writeString` từ Java 11, `newFileSystem(Path,Map)` từ Java 13. Kiến trúc NIO.2 gốc có từ Java 7 nhưng không có nghĩa mọi overload được viết trong bài đều có từ Java 7.

### 28.18. Nghĩ đóng ZIP là rollback toàn bộ thay đổi

Không có contract transactional đầy đủ. Thiết kế publish/backup/verification nếu tính toàn vẹn quan trọng.

### 28.19. Không đóng `Files.walk` stream

`Files.walk` trả stream có tài nguyên cần đóng bằng try-with-resources. Đây là API Java 8+, còn `Files.walkFileTree` dùng visitor (Java 7).

### 28.20. Bỏ qua provider-specific constraints khi xử lý ZIP khác lạ

`jdk.zipfs` từ chối một số entry names không hợp lệ; provider khác có thể có logic khác. Bắt lỗi đọc/parse và không suy giả định portable từ một archive nhỏ.

## 29. Ma trận QA đề xuất

| Test | Kết quả nên kiểm tra | Cảnh báo |
| --- | --- | --- |
| Default FS | Scheme `file`, path thuộc default FS | Read-only/separator/roots phụ thuộc OS |
| installedProviders | Default đứng đầu, scheme unique | Danh sách provider khác giữa runtimes |
| ZIP provider | Scheme `jar` nếu `jdk.zipfs` có | jlink/runtime có thể thiếu module |
| ZIP create | Tạo container khi `create=true` | Không tự ghi ngoài temp directory |
| ZIP write/read | Entry viết và đọc đúng bytes | Open/close I/O có thể lỗi |
| ZIP close/reopen | Nội dung còn sau mở lại | Không suy transaction/atomic |
| URI lookup | get trả same instance khi đã mở | Sau close behavior provider-specific |
| ZIP duplicate | Factory trùng instance bị từ chối ở ZIP provider | Không lấy rồi đóng shared FS |
| Cross-provider copy | Copy nội dung file local vào archive | Metadata/symlink/options khác |
| Provider mismatch | Mixed resolve bị từ chối | Không trộn Path từ namespace khác |
| ZIP toFile | Unsupported với provider QA | java.io.File không portable |
| After close | Path đọc bị từ chối | Resource ownership cần rõ |
| Unknown scheme | ProviderNotFound khi chưa cài | Custom provider có thể đổi kết quả |
| ZIP attrs | Basic view hỗ trợ, `zip` view trong JDK ZIP provider | POSIX view chỉ với property thích hợp |
| Untrusted ZIP | Reject malformed/path traversal hoặc giới hạn extraction | Zip bomb/symlink/races |
| Java version | `javac --release 17` biên dịch | Không suy mọi overload có từ Java 7 |
| Windows/Linux | Không phụ thuộc tên provider class/OS-specific separator | CI đa nền tảng cần logic linh hoạt |

### 29.1. Những đầu ra đã kiểm thử thật

Tám chương trình standalone của bài được biên dịch bằng **`javac --release 17 -encoding UTF-8`** trên JDK hiện đại chạy tại Windows. Những kết quả có tính environment-specific (ví dụ `schemes=file,jar,jrt` hoặc `defaultReadOnly=false`) được ghi nhận là **quan sát**, không phải contract áp dụng mọi Java runtime.

Để CI portable, assert những invariants theo public Java API, không assert exact class name của default provider, số file stores hoặc số ZIP permissions trên mọi OS.

### 29.2. Điều kiện để phát biểu “PASS”

- Mã độc lập có tên class và file trùng nhau.
- Không dùng API vượt target Java 17 khi biên dịch `--release 17`.
- Temporary files được dọn trong `finally`.
- Đọc/ghi ZIP đúng trong scope filesystem đang mở.
- Có xử lý ngoại lệ provider/closed/duplicate/mismatch.
- Kết quả demo phân biệt rõ platform observations và API guarantees.
- Tài liệu không nhầm Java 7 NIO.2 với các overload Java 9–13.

## 30. Tài liệu chính thức còn áp dụng

- [Java SE 17 — `FileSystems`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): default FS, getFileSystem, newFileSystem URI/Path, service provider discovery, mốc `Since: 13` cho các Path factory mới.
- [Java SE 17 — `FileSystem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): lifecycle, path factory, provider, roots, separator, stores, attributes và `close`.
- [Java SE 17 — `FileSystemProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): nhà cung cấp filesystem, scheme, installedProviders và SPI.
- [Java SE 17 — `Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): Path gắn với FileSystem, URI, resolve, toFile/interoperability.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các operations delegate theo Path/provider; copy, read/write, attributes.
- [Java SE 17 — `jdk.zipfs` module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP/JAR provider, scheme `jar`, environment properties, file attribute views, restrictions của ZIP entries.
- [Java SE 17 — `ProviderMismatchException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ProviderMismatchException.html): lỗi khi trộn đối tượng của providers khác.
- [Java SE 17 — `ClosedFileSystemException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): truy cập hệ thống tệp đã đóng.
- [Java SE 17 — `FileSystemAlreadyExistsException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemAlreadyExistsException.html): tạo trùng instance.
- [Java SE 17 — `FileSystemNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemNotFoundException.html): không tìm thấy instance.
- [Java SE 17 — `ProviderNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ProviderNotFoundException.html): thiếu provider cho scheme/file type.

**Kết luận:** `FileSystems.getDefault()` trả FileSystem của nhà cung cấp mặc định với scheme `file`; `FileSystemProvider.installedProviders()` cho biết những nhà cung cấp bổ sung nào đang thực sự có mặt. Để dùng ZIP/JAR như một cây file, ứng dụng có thể mở FileSystem bằng provider `jar` từ module `jdk.zipfs`, tạo entry paths bằng `zipFs.getPath(...)`, dùng `Files` thao tác và **đóng ZIP filesystem khi xong**. Không trộn `Path` từ các providers, không coi `newFileSystem` và `getFileSystem` là một, và không coi ZIP provider/metadata/close là giao dịch hoặc security boundary. Nhận biết đúng phiên bản API (NIO.2 Java 7; `jdk.zipfs` module Java 9+; Path factory Java 13+) và quản lý provider, lifetime, errors, archives không tin cậy là nền tảng để mở rộng hệ thống tệp an toàn trên Java hiện đại.