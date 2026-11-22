# Quan hệ `Path`, `FileSystem` và `FileSystemProvider` trong Java NIO.2

> **Mục tiêu:** Hiểu rõ cách một `Path` thuộc về một `FileSystem`, cách `FileSystem` được triển khai bởi `FileSystemProvider` và cách `Files` thực hiện I/O trong nhiều filesystem khác nhau. Bài dùng các API NIO.2 từ Java 7 còn hữu ích trong Java 17+, đặc biệt default filesystem và ZIP filesystem do module `jdk.zipfs` cung cấp. Tám chương trình độc lập đã biên dịch và chạy với JDK 17. Những helper mới hơn như `Map.of` (Java 9), `Path.of` và `Files.readString/writeString` (Java 11), cùng một số overload `newFileSystem(Path,...)` (Java 13) được ghi rõ để không nhầm chúng là API của Java 7.

## 1. Nhìn toàn cảnh

```text
           java.nio.file.Files
                    |
               thao tác trên
                    |
                    v
               Path object
                    |
        path.getFileSystem()
                    |
                    v
           FileSystem instance
                    |
              fs.provider()
                    |
                    v
           FileSystemProvider
             URI scheme / SPI

Provider "file"
  +-- default FileSystem
         +-- Path trên host disk, mount hoặc volume

Provider "jar"
  +-- ZIP FileSystem A (a.zip)
  |      +-- /docs/readme.txt
  +-- ZIP FileSystem B (b.zip)
         +-- /docs/readme.txt
```

Một provider có thể cung cấp nhiều FileSystem instances. Hai ZIP Paths cùng in `/docs/readme.txt` không nhất thiết là cùng file: mỗi Path thuộc archive/instance riêng.

| Đối tượng | Bản chất | API quan hệ | Điều không nên nhầm |
| --- | --- | --- | --- |
| `Path` | Đường dẫn trong namespace | `path.getFileSystem()` | Không nhất thiết là file tồn tại |
| `FileSystem` | Instance có root, Path factories và capability | `fs.getPath()`, `fs.provider()` | Không luôn là một ổ vật lý |
| `FileSystemProvider` | SPI/factory triển khai filesystem operations | `provider.getScheme()` | Một provider không chỉ có một FS |
| `FileSystems` | Static factories/lookup | `getDefault()`, `newFileSystem()` | Không phải instance |
| `Files` | Static I/O utilities | `copy()`, `readAttributes()` | Không chỉ dùng trên host |
| `FileStore` | Thông tin vùng lưu trữ | `Files.getFileStore(path)` | Không phải provider |

Từ một Path có sẵn:

```java
FileSystem fs = path.getFileSystem();
java.nio.file.spi.FileSystemProvider provider = fs.provider();
String scheme = provider.getScheme();
```

Đây là **snippet**, không phải class chạy riêng. Nó chỉ lấy quan hệ object, không cần tạo file.

## 2. `Path`: đường dẫn và namespace, không phải một file đã mở

`Path` là interface. Nó có thể biểu diễn một tên file, directory hoặc symbolic link, kể cả khi entry thực **chưa tồn tại**.

```java
Path p = Path.of("reports", "2026", "summary.txt");
Path parent = p.getParent();
Path name = p.getFileName();
Path next = p.resolveSibling("summary-new.txt");
```

Đây là snippet với `import java.nio.file.Path`; không thực hiện I/O. `Path.of` có từ Java 11. Nếu cần target Java 7, dùng `Paths.get("reports","2026","summary.txt")`.

### 2.1. Path methods và I/O là hai nhóm khác nhau

| Method | Ý nghĩa | Có cần file thật? |
| --- | --- | --- |
| `getFileName()`, `getParent()` | Xem thành phần tên | Không |
| `resolve()`, `resolveSibling()` | Ghép tên | Không |
| `normalize()` | Loại `.` và `..` theo cấu trúc tên | Không |
| `relativize()` | Tính path tương đối | Không, nhưng cần Path tương thích |
| `isAbsolute()` | Xem Path có root không | Không |
| `toAbsolutePath()` | Tạo absolute path theo FS/context | Không nhất thiết |
| `toUri()` | Chuyển sang URI theo provider | Không nhất thiết |
| `toRealPath()` | Kiểm tra và giải path thật | **Có I/O** |
| `Files.readString()` | Đọc bytes/text thật | **Có I/O** |
| `Files.readAttributes()` | Đọc metadata | **Có I/O** |

`normalize()` không phải giải symlink, không bảo đảm path tồn tại và không đủ để chống path traversal/TOCTOU.

### 2.2. Tạo Path trong đúng filesystem

- `Path.of("a.txt")` → default FS, Java 11+.
- `Paths.get("a.txt")` → default FS, Java 7+.
- `FileSystems.getDefault().getPath("a.txt")` → default FS.
- `zipFs.getPath("/docs/a.txt")` → ZIPFS instance đã chọn.
- `root.resolve("child.txt")` → Path theo filesystem của `root`.

Một thư viện nhận `Path root` muốn hỗ trợ cả host và ZIP nên dùng `root.resolve("child.txt")`. Gọi `Path.of("child.txt")` giữa chừng sẽ chuyển về default FS, có thể làm thao tác I/O sai namespace.

### 2.3. Không lấy tên Path làm file identity toàn cục

Hai ZIP archives khác nhau đều có `/same.txt`, hoặc host và ZIP cùng có `/docs/readme.txt`. String giống không có nghĩa cùng object. Cần xét Path thuộc FileSystem instance nào, URI/provider và ngữ nghĩa của thao tác.

## 3. `FileSystem`: nguồn tạo Path và nơi quản lý capability/lifecycle

`java.nio.file.FileSystem` cung cấp:
- `getPath(String,String...)`: Path factory trong namespace đó.
- `provider()`: provider quản lý instance.
- `getSeparator()`, `getRootDirectories()`: cấu trúc paths/roots.
- `getFileStores()`: thông tin các vùng lưu trữ theo provider.
- `supportedFileAttributeViews()`: views thuộc tính có thể đọc.
- `getPathMatcher()`, `newWatchService()`: pattern matching và dịch vụ theo dõi nếu hỗ trợ.
- `isOpen()`, `isReadOnly()`, `close()`: vòng đời và trạng thái.

**Không đồng nhất FileSystem với FileStore.** Một default FileSystem trên Windows có thể truy cập nhiều volumes, còn ZIP FileSystem biểu diễn một archive như namespace riêng.

`FileSystem` là resource có thể đóng. Nhưng **không đóng default FileSystem**: JVM quản lý nó. Với ZIPFS do chính ứng dụng mở, dùng try-with-resources để đóng sau khi hoàn tất; Path gắn với instance đã đóng không còn dùng an toàn cho I/O.

## 4. `FileSystemProvider`: SPI và nhà máy tạo filesystem

`java.nio.file.spi.FileSystemProvider` là Service Provider Interface cung cấp các operation tạo/mở filesystem, truy vấn Path và I/O. Provider có URI scheme, ví dụ:
- `file`: provider mặc định.
- `jar`: ZIPFS provider do module JDK `jdk.zipfs` cung cấp khi có trong runtime.
- Các provider riêng: filesystem ảo hoặc dịch vụ storage khác, với semantics riêng.

Provider có thể:
1. Tạo/tra cứu FileSystem qua `newFileSystem(URI,Map)` và `getFileSystem(URI)`.
2. Trả Path cho một URI theo định dạng provider chấp nhận.
3. Hỗ trợ I/O, metadata, directory operations qua `Files` và các API liên quan.
4. Thông báo không hỗ trợ optional operation bằng exception thích hợp.

### 4.1. Thông tin về provider đang cài

`FileSystemProvider.installedProviders()` trả danh sách providers của runtime hiện tại. Trên JDK đủ module thường có `file` và `jar`; bản runtime được tối giản bằng `jlink` có thể thiếu `jdk.zipfs`. **Không phỏng đoán khả năng chỉ từ tên OS**.

### 4.2. Thường không cần tự viết provider

Để đọc host hoặc ZIP, app chỉ cần `Path`/`Files`/`FileSystems`. Viết provider mới là công việc hạ tầng cần implement nhiều operation cùng hợp đồng; không phải thao tác thường xuyên của người dùng NIO.2.

## 5. `Files`: lớp static utility thực hiện I/O theo Path

`Files` có các method như:

```java
Files.writeString(path, "hello");
String value = Files.readString(path);
long size = Files.size(path);
```

Đây là snippet Java 11+ trong method xử lý IOException. `Files` áp dụng operation lên Path với provider tương ứng. Nếu Path nằm trong ZIPFS, hoạt động trên entry ZIP; nếu ở default FS, hoạt động trên host file.

Không phải mọi providers hỗ trợ giống nhau: symlinks, POSIX permissions, watch service, atomic move và metadata views đều có thể khác.

## 6. Default FileSystem

`FileSystems.getDefault()` trả default FS của JVM; provider mặc định có scheme `file`. `Path.of(String...)` và `Paths.get(String...)` lấy Path từ filesystem này.

### 6.1. Chương trình 1 — Path → FS → Provider

Lưu thành `ProviderLayersDemo.java`:

```java
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.spi.FileSystemProvider;

public class ProviderLayersDemo {
    public static void main(String[] args) {
        FileSystem system = FileSystems.getDefault();
        Path relative = Path.of("project", "report.txt");
        FileSystemProvider provider = system.provider();

        System.out.println("pathUsesDefault=" + (relative.getFileSystem() == system));
        System.out.println("providerMatches=" +
                (relative.getFileSystem().provider() == provider));
        System.out.println("defaultScheme=" + provider.getScheme());
        System.out.println("relativePath=" + !relative.isAbsolute());
        System.out.println("defaultOpen=" + system.isOpen());
        System.out.println("fileProviderInstalled=" +
                FileSystemProvider.installedProviders().stream()
                        .anyMatch(p -> p.getScheme().equalsIgnoreCase("file")));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ProviderLayersDemo.java
java ProviderLayersDemo
```

Stdout đã kiểm thử trên JDK 17:

```text
pathUsesDefault=true
providerMatches=true
defaultScheme=file
relativePath=true
defaultOpen=true
fileProviderInstalled=true
```

Kết quả chứng minh Path từ `Path.of` thuộc default FS và provider `file`. Nó không tạo file `project/report.txt` thật. `relativePath=true` vì không có root absolute trong ví dụ.

### 6.2. Chương trình 2 — không đóng default FS

Lưu thành `DefaultFileSystemLifetimeDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;

public class DefaultFileSystemLifetimeDemo {
    public static void main(String[] args) throws IOException {
        FileSystem fs = FileSystems.getDefault();
        System.out.println("defaultOpenBefore=" + fs.isOpen());
        try {
            fs.close();
            System.out.println("defaultClose=UNEXPECTED");
        } catch (UnsupportedOperationException expected) {
            System.out.println("defaultClose=UnsupportedOperationException");
        }
        System.out.println("defaultOpenAfter=" + fs.isOpen());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DefaultFileSystemLifetimeDemo.java
java DefaultFileSystemLifetimeDemo
```

Stdout đã kiểm chứng:

```text
defaultOpenBefore=true
defaultClose=UnsupportedOperationException
defaultOpenAfter=true
```

Chương trình minh họa hợp đồng của default provider: close không được hỗ trợ theo cách này, FS vẫn mở. Trong code thật **đừng gọi close trên default FS**, đặc biệt đừng đóng `path.getFileSystem()` khi Path do caller truyền vào.

## 7. `FileSystems` là class factory, không phải instance

Các static methods quan trọng:

| API | Chức năng |
| --- | --- |
| `FileSystems.getDefault()` | Lấy default FileSystem |
| `FileSystems.getFileSystem(URI)` | Lookup một FileSystem đang tồn tại theo URI |
| `FileSystems.newFileSystem(URI,Map)` | Tạo/mount FileSystem theo provider URI scheme |
| `FileSystems.newFileSystem(URI,Map,ClassLoader)` | Có thêm class loader để tìm provider |
| `FileSystems.newFileSystem(Path,ClassLoader)` | Yêu cầu provider mở file làm filesystem |
| `FileSystems.newFileSystem(Path)` | Convenience overload có từ Java 13 |
| `FileSystems.newFileSystem(Path,Map)` | Overload từ Java 13 kèm options |

`getFileSystem` chỉ tra cứu instance; nó không tự mount ZIP. `newFileSystem` yêu cầu provider tạo instance. Nếu provider không có, nhận `ProviderNotFoundException`. Nếu một URI đã mount và provider không cho mount trùng, có thể nhận `FileSystemAlreadyExistsException`.

### 7.1. Lựa chọn provider theo URI scheme

Khi muốn mở ZIP/JAR, dùng URI `jar:`, không phải `file:` của host:

```java
Path archive = Path.of("archive.zip");
URI zipUri = URI.create("jar:" + archive.toUri());
FileSystem zipFs =
        FileSystems.newFileSystem(zipUri, Map.of("create","true"));
```

Đây là snippet, cần `import java.net.URI` và java.nio.file.*, java.util.Map, trong method xử lý IOException. `Map.of("create","true")` là option của **ZIP provider**, không phải option chung của mọi FileSystemProvider.

Dùng `archive.toUri()` để có encoding phù hợp của host path (nhất là dấu cách/Unicode), tránh tự ghép raw Windows paths vào URI.

### 7.2. URI scheme không phải FileSystem identity đầy đủ

`jar` chỉ định provider loại ZIP; URI còn chứa địa chỉ archive. Hai URI ứng với `a.zip` và `b.zip` có thể mở hai FS instances độc lập. Một ZIPFS không biến thành một host volume mới chỉ vì có scheme khác.

## 8. ZIP FileSystem do module `jdk.zipfs` cung cấp

Module JDK hiện đại `jdk.zipfs` trình bày ZIP/JAR archive như một filesystem có root `/`:

```text
Host default FS ("file"):
  /tmp/bundle.zip   <-- Path host

ZIPFS ("jar") mount từ bundle.zip:
  /
  /docs/
  /docs/readme.txt  <-- ZIP Path
```

`archive` là Path host tới **file ZIP**, còn `zipFs.getPath("/docs/readme.txt")` là Path thuộc **namespace archive**, không phải host path `/docs/readme.txt`.

### 8.1. Cách mở/ghi ZIP có try-with-resources

```java
Path archive = Path.of("bundle.zip");
URI uri = URI.create("jar:" + archive.toUri());

try (FileSystem zipFs =
        FileSystems.newFileSystem(uri, Map.of("create","true"))) {
    Path entry = zipFs.getPath("/docs/readme.txt");
    Files.createDirectories(entry.getParent());
    Files.writeString(entry, "IN ZIP");
}
```

Đây là snippet Java 17 với method xử lý IOException. `create` yêu cầu provider tạo archive nếu chưa có. Đóng FileSystem có thể cần lưu thay đổi; **close có thể ném IOException**. ZIPFS được mở từ một archive file host, nhưng ZIP entries không phải các files host riêng.

### 8.2. Cách dùng API theo các phiên bản

- Java 7: `Path`, `Files`, `FileSystem`, `FileSystems`, `FileSystemProvider`, `newFileSystem(URI,Map)`.
- Java 9: `Map.of` và kiến trúc module `jdk.zipfs`.
- Java 11: `Path.of`, `Files.readString`, `Files.writeString`.
- Java 13: `FileSystems.newFileSystem(Path)` / `newFileSystem(Path,Map)` convenience overloads.
- Java 17+: tất cả APIs hiện đại trên tiếp tục hữu ích; ví dụ dùng `--release 17`.

Không gán nhầm các convenience APIs mới cho Java 7, cũng không gọi lõi NIO.2 là legacy.

## 9. Chương trình 3 — so sánh `file` và `jar`

Lưu thành `ZipProviderDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.nio.file.spi.FileSystemProvider;
import java.util.Map;

public class ZipProviderDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("zip-provider-");
        Path archive = dir.resolve("bundle.zip");
        URI zipUri = URI.create("jar:" + archive.toUri());
        try {
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
                Path inside = zipFs.getPath("/docs/readme.txt");
                Files.createDirectories(inside.getParent());
                Files.writeString(inside, "ZIPFS");

                System.out.println("defaultScheme=" +
                        FileSystems.getDefault().provider().getScheme());
                System.out.println("zipScheme=" + zipFs.provider().getScheme());
                System.out.println("pathUsesZip=" + (inside.getFileSystem() == zipFs));
                System.out.println("fsDifferent=" +
                        (inside.getFileSystem() != archive.getFileSystem()));
                System.out.println("jarProviderInstalled=" +
                        FileSystemProvider.installedProviders().stream()
                                .anyMatch(p -> p.getScheme().equalsIgnoreCase("jar")));
                System.out.println("insideUriScheme=" + inside.toUri().getScheme());
                System.out.println("content=" + Files.readString(inside));
            }
            System.out.println("archiveRemains=" + Files.exists(archive));
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipProviderDemo.java
java ZipProviderDemo
```

Stdout đã kiểm thử trên JDK 17 có `jdk.zipfs`:

```text
defaultScheme=file
zipScheme=jar
pathUsesZip=true
fsDifferent=true
jarProviderInstalled=true
insideUriScheme=jar
content=ZIPFS
archiveRemains=true
```

**Diễn giải:**
- `defaultScheme=file` và `zipScheme=jar` là schemes của hai providers.
- `pathUsesZip=true` chứng minh Path ZIP trả về đúng FS instance.
- `fsDifferent=true`: Path host archive và entry ZIP thuộc hai FS khác nhau.
- `jarProviderInstalled=true` đúng với JDK thử nghiệm, không bảo đảm trên custom runtime bị lược module.
- `insideUriScheme=jar`: URI được provider sinh cho ZIP entry có scheme jar.
- `archiveRemains=true`: đóng ZIPFS không xóa file host archive; demo xóa nó riêng ở finally.

## 10. Tạo/biến đổi Path bên trong ZIP

`zipFs.getPath("/")` là root của ZIPFS, không phải root host. Những phép như `relativize`, `normalize` xử lý tên theo semantics ZIPFS.

```java
Path root = zipFs.getPath("/");
Path file = zipFs.getPath("/docs/readme.txt");
Path relative = root.relativize(file);
Path normalized = zipFs.getPath("/docs/../readme.txt").normalize();
```

Đây là snippet. `relative` thường là `docs/readme.txt` và `normalized` là `/readme.txt`. Normalize **không tạo file**, không chứng minh entry có thật và không phải kiểm tra bảo mật đường dẫn có symbolic links.

### 10.1. Chương trình 4 — thao tác Path trong ZIPFS

Lưu thành `ZipPathOperationsDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class ZipPathOperationsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("zip-path-");
        Path archive = dir.resolve("data.zip");
        URI uri = URI.create("jar:" + archive.toUri());
        try {
            try (FileSystem fs = FileSystems.newFileSystem(
                    uri, Map.of("create", "true"))) {
                Path file = fs.getPath("/docs/readme.txt");
                Files.createDirectories(file.getParent());
                Files.writeString(file, "HI");
                Path raw = fs.getPath("/docs/../readme.txt");

                System.out.println("zipRoot=" + fs.getPath("/"));
                System.out.println("insideAbsolute=" + file.isAbsolute());
                System.out.println("relative=" + fs.getPath("/").relativize(file));
                System.out.println("normalize=" + raw.normalize());
                System.out.println("zipReal=" + file.toRealPath());
                System.out.println("zipContent=" + Files.readString(file));
                System.out.println("zipFileStores=" +
                        fs.getFileStores().iterator().hasNext());
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipPathOperationsDemo.java
java ZipPathOperationsDemo
```

Stdout đã kiểm chứng:

```text
zipRoot=/
insideAbsolute=true
relative=docs/readme.txt
normalize=/readme.txt
zipReal=/docs/readme.txt
zipContent=HI
zipFileStores=true
```

**Chú ý:** `zipReal` vẫn là Path của ZIPFS, không phải một file riêng `/docs/readme.txt` trên host. `getFileStores` cung cấp abstraction lưu trữ theo provider; không chứng minh archive là volume vật lý mới.

## 11. Hai ZIP FileSystems có thể chia sẻ provider mà không chia sẻ dữ liệu

Một ZIP provider `jar` có thể tạo các instances A và B cho hai archives. Hai Paths đều có tên `/same.txt` nhưng chứa dữ liệu khác.

### 11.1. `resolve(Path)` có điểm cần cảnh giác

Theo Javadoc `Path.resolve(Path other)`, nếu `other` là **absolute**, phép resolve trả lại `other`. Vì vậy foreign absolute Path có thể dẫn đến kết quả thuộc FS khác dù base thuộc FS hiện tại.

Nếu other là relative Path thuộc filesystem khác, provider có thể:
- ném `ProviderMismatchException`;
- hoặc nhận components từ other rồi diễn giải trong namespace của base.

Không mặc định `resolve` là “hàm ép mọi Path vào namespace của bên trái”. Khi muốn tạo child của base, dùng `base.resolve("child.txt")` hoặc `base.getFileSystem().getPath("child.txt")`.

## 12. Chương trình 5 — hai ZIP cùng provider, khác instances

Lưu thành `TwoZipFileSystemsDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class TwoZipFileSystemsDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("two-zipfs-");
        Path aZip = folder.resolve("a.zip");
        Path bZip = folder.resolve("b.zip");
        try {
            URI aUri = URI.create("jar:" + aZip.toUri());
            URI bUri = URI.create("jar:" + bZip.toUri());
            try (FileSystem a = FileSystems.newFileSystem(aUri, Map.of("create", "true"));
                 FileSystem b = FileSystems.newFileSystem(bUri, Map.of("create", "true"))) {
                Path pa = a.getPath("/same.txt");
                Path pb = b.getPath("/same.txt");
                Files.writeString(pa, "A");
                Files.writeString(pb, "B");

                System.out.println("providerSame=" + (a.provider() == b.provider()));
                System.out.println("filesystemDifferent=" + (a != b));
                System.out.println("pathNamesEqual=" + pa.toString().equals(pb.toString()));
                System.out.println("pathObjectsEqual=" + pa.equals(pb));
                System.out.println("aContent=" + Files.readString(pa));
                System.out.println("bContent=" + Files.readString(pb));

                Path relativeFromB = b.getPath("nested.txt");
                Path joined = pa.getParent().resolve(relativeFromB);
                System.out.println("joinedUsesA=" + (joined.getFileSystem() == a));
                System.out.println("joinedPath=" + joined);

                Path absoluteFromB = b.getPath("/absolute.txt");
                Path result = pa.getParent().resolve(absoluteFromB);
                System.out.println("absoluteUsesB=" + (result.getFileSystem() == b));
            }
        } finally {
            Files.deleteIfExists(aZip);
            Files.deleteIfExists(bZip);
            Files.deleteIfExists(folder);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TwoZipFileSystemsDemo.java
java TwoZipFileSystemsDemo
```

Stdout đã kiểm chứng:

```text
providerSame=true
filesystemDifferent=true
pathNamesEqual=true
pathObjectsEqual=false
aContent=A
bContent=B
joinedUsesA=true
joinedPath=/nested.txt
absoluteUsesB=true
```

### 12.1. Ý nghĩa của phép so sánh

`providerSame=true`: cùng provider `jar`. `filesystemDifferent=true`: hai instances riêng. `pathNamesEqual=true` chỉ so chuỗi tên, còn `pathObjectsEqual=false` thể hiện Path objects của hai ZIP archives khác nhau. Dữ liệu A/B khác nhau chứng minh namespaces độc lập.

### 12.2. Vì sao resolve có kết quả bất ngờ?

`joinedUsesA=true` là hành vi của ZIP provider JDK 17 khi nhận một relative Path thuộc ZIPFS khác, rồi ghép các thành phần vào base của A. `absoluteUsesB=true` phản ánh quy tắc absolute argument được trả trực tiếp. **Đừng suy ra mọi provider thực hiện foreign relative resolve giống vậy.** Hãy chủ động tạo Path theo namespace mong muốn.

## 13. I/O cross-provider: Files.copy khác Path.resolve

`Files.copy` có khả năng copy nội dung giữa file systems khác nhau khi cả source/target providers hỗ trợ các operation cần thiết. Nó không cùng ý nghĩa với `Path.resolve`.

| Tình huống | Cần làm gì |
| --- | --- |
| Copy host file vào ZIP | `Files.copy(hostPath, zipFs.getPath("/a.txt"))` |
| Copy ZIP entry ra host | `Files.copy(zipEntry, hostDir.resolve("a.txt"))` |
| Tạo child Path trong ZIP | `zipFs.getPath("/dir").resolve("a.txt")` |
| Tạo child Path trên host | `hostDir.resolve("a.txt")` |
| Lấy attributes của ZIP entry | `Files.readAttributes(zipEntry, ...)` |
| Đọc host archive ZIP bytes | I/O trên `archive` thuộc default FS |

Với copy, cần định nghĩa overwrite policy, permission, size limits và error recovery. `COPY_ATTRIBUTES` không bảo đảm toàn bộ metadata POSIX/ACL giống hệt giữa providers.

## 14. Chương trình 6 — copy host → ZIP → host

Lưu thành `CrossProviderCopyDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class CrossProviderCopyDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("cross-provider-");
        Path input = dir.resolve("input.txt");
        Path archive = dir.resolve("data.zip");
        Path restored = dir.resolve("restored.txt");
        try {
            Files.writeString(input, "HELLO ZIP");
            URI zipUri = URI.create("jar:" + archive.toUri());
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(zipUri, Map.of("create", "true"))) {
                Path zipped = zipFs.getPath("/payload.txt");
                Files.copy(input, zipped);
                Files.copy(zipped, restored);

                System.out.println("inputContent=" + Files.readString(input));
                System.out.println("zipContent=" + Files.readString(zipped));
                System.out.println("restoredContent=" + Files.readString(restored));
                System.out.println("differentFileSystems=" +
                        (input.getFileSystem() != zipped.getFileSystem()));
                try {
                    input.getParent().resolve(zipped);
                    System.out.println("resolveForeign=UNEXPECTED");
                } catch (ProviderMismatchException expected) {
                    System.out.println("resolveForeign=ProviderMismatchException");
                }
            }
        } finally {
            Files.deleteIfExists(restored);
            Files.deleteIfExists(input);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CrossProviderCopyDemo.java
java CrossProviderCopyDemo
```

Stdout đã chạy:

```text
inputContent=HELLO ZIP
zipContent=HELLO ZIP
restoredContent=HELLO ZIP
differentFileSystems=true
resolveForeign=ProviderMismatchException
```

### 14.1. Giải thích

Cross-provider `Files.copy` xử lý dữ liệu được provider đọc/ghi, nên bản thử chuyển chuỗi qua ZIP và trả lại host thành công. Nhưng `input.getParent().resolve(zipped)` là phép **ghép tên**, không phải copy, và default provider đã từ chối ZIP Path bằng `ProviderMismatchException`.

Đây là behavior của cặp providers đã kiểm thử; không phủ định `TwoZipFileSystemsDemo`, nơi hai ZIPFS cùng provider có thể xử lý foreign relative paths khác. Trong code portable, xác định filesystem của Path và gọi đúng API cho mục đích.

## 15. ZIP FileSystem lifecycle và ownership

Dùng try-with-resources khi ứng dụng **tạo** một ZIPFS:

```java
try (FileSystem zipFs = FileSystems.newFileSystem(uri, Map.of())) {
    Path path = zipFs.getPath("/message.txt");
    String message = Files.readString(path);
}
```

Đây là snippet với ZIP archive đã tồn tại và method xử lý IOException.

Sau khi close:
- `zipFs.isOpen()` là false.
- File ZIP host vẫn tồn tại trừ khi bị xóa riêng.
- Path cũ vẫn là object Java nhưng không dùng được đáng tin cho I/O; có thể ném `ClosedFileSystemException`.
- Mở lại archive tạo instance mới, hãy lấy Path mới từ instance đó.

**Anti-pattern:**

```java
Path brokenApi(URI uri) throws IOException {
    try (FileSystem fs = FileSystems.newFileSystem(uri, Map.of())) {
        return fs.getPath("/data.txt");
    }
}
```

Đây là snippet minh họa cách **không nên làm**. Hàm trả Path của FileSystem đã đóng. Cách sửa: trả dữ liệu độc lập được đọc trong block; hoặc trả object quản lý FileSystem + Path + ownership; hoặc dùng callback xử lý trong lifetime.

### 15.1. Không đóng filesystem của caller

Nếu một method nhận `Path input` do caller cung cấp, mặc định nó **không sở hữu** `input.getFileSystem()`. Đừng gọi `input.getFileSystem().close()` sau khi đọc; có thể đóng ZIPFS người khác đang dùng hoặc cố đóng default FS.

## 16. Chương trình 7 — closed ZIP Path và reopen

Lưu thành `ZipFileSystemLifecycleDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class ZipFileSystemLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("zip-lifecycle-");
        Path archive = dir.resolve("data.zip");
        URI uri = URI.create("jar:" + archive.toUri());
        Path oldPath;
        try {
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(uri, Map.of("create", "true"))) {
                oldPath = zipFs.getPath("/message.txt");
                Files.writeString(oldPath, "PERSISTED");
                System.out.println("duringOpen=" + zipFs.isOpen());
                System.out.println("duringRead=" + Files.readString(oldPath));
            }
            System.out.println("afterCloseOpen=" + oldPath.getFileSystem().isOpen());
            try {
                Files.readString(oldPath);
                System.out.println("oldPathRead=UNEXPECTED");
            } catch (ClosedFileSystemException expected) {
                System.out.println("oldPathRead=ClosedFileSystemException");
            }
            try (FileSystem reopened = FileSystems.newFileSystem(uri, Map.of())) {
                System.out.println("reopenedRead=" +
                        Files.readString(reopened.getPath("/message.txt")));
            }
            System.out.println("archiveExists=" + Files.exists(archive));
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipFileSystemLifecycleDemo.java
java ZipFileSystemLifecycleDemo
```

Stdout đã kiểm chứng:

```text
duringOpen=true
duringRead=PERSISTED
afterCloseOpen=false
oldPathRead=ClosedFileSystemException
reopenedRead=PERSISTED
archiveExists=true
```

### 16.1. Tại sao Path cũ không còn đọc được?

Path giữ tham chiếu tới **ZIPFS instance cũ**. Mở lại ZIP file không “hồi sinh” FileSystem đã đóng; instance mới có Path mới. `oldPathRead` do vậy nhận ClosedFileSystemException. `reopenedRead=PERSISTED` chứng minh file ZIP host vẫn có nội dung sau khi close thành công.

### 16.2. Trường hợp close bị lỗi

`FileSystem.close()` có thể ném IOException. Trong try-with-resources, nếu body đã ném lỗi và close cũng lỗi thì exception của close có thể được ghi nhận dưới dạng suppressed. Code production nên xử lý lỗi I/O và trạng thái archive phù hợp, không coi close là transaction ACID.

## 17. `getFileSystem(URI)` vs `newFileSystem(URI,Map)`

- `getFileSystem(uri)`: tra cứu instance, không tự tạo mới.
- `newFileSystem(uri,env)`: yêu cầu provider mở/tạo instance.

Với JDK ZIP provider:
- Chưa mount → lookup có thể báo FileSystemNotFoundException.
- Đang mount → lookup trả instance tương ứng.
- Cố mount lại cùng URI → có thể FileSystemAlreadyExistsException.
- Đã close → lookup thường báo NotFound, nhưng Javadoc để một số chi tiết đóng/mở tùy provider.

## 18. Chương trình 8 — lookup và duplicate mount

Lưu thành `ZipUriLookupDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.util.Map;

public class ZipUriLookupDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("zip-uri-");
        Path archive = dir.resolve("data.zip");
        URI uri = URI.create("jar:" + archive.toUri());
        try {
            try {
                FileSystems.getFileSystem(uri);
                System.out.println("beforeMount=UNEXPECTED");
            } catch (FileSystemNotFoundException expected) {
                System.out.println("beforeMount=FileSystemNotFoundException");
            }
            try (FileSystem zip = FileSystems.newFileSystem(
                    uri, Map.of("create", "true"))) {
                System.out.println("lookupSame=" + (FileSystems.getFileSystem(uri) == zip));
                try {
                    FileSystems.newFileSystem(uri, Map.of());
                    System.out.println("duplicateMount=UNEXPECTED");
                } catch (FileSystemAlreadyExistsException expected) {
                    System.out.println("duplicateMount=FileSystemAlreadyExistsException");
                }
            }
            try {
                FileSystems.getFileSystem(uri);
                System.out.println("afterClose=UNEXPECTED");
            } catch (FileSystemNotFoundException expected) {
                System.out.println("afterClose=FileSystemNotFoundException");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ZipUriLookupDemo.java
java ZipUriLookupDemo
```

Stdout đã kiểm chứng với ZIPFS JDK 17:

```text
beforeMount=FileSystemNotFoundException
lookupSame=true
duplicateMount=FileSystemAlreadyExistsException
afterClose=FileSystemNotFoundException
```

**Không đồng nhất** FileSystemNotFoundException với `archive.zip` không có trên host: nó mô tả lookup mounted instance, không phải nhất thiết thiếu file. Thực tế archive có thể tồn tại nhưng chưa mount.

## 19. Chuyển URI thành Path và version semantics

Các factories:
- `Path.of(String...)`: default FS, Java 11+.
- `Paths.get(String...)`: default FS, Java 7+.
- `Path.of(URI)`: tìm provider theo scheme, Java 11+.
- `Paths.get(URI)`: cách dùng từ Java 7.
- `FileSystem.getPath(String...)`: tạo Path **trong FS instance đã chọn**.

`Path.of(URI)` không đảm bảo auto-mount ZIPFS nếu chưa có instance tương ứng; có thể gặp FileSystemNotFoundException. Với ZIPFS do application quản lý, rõ ràng hơn: newFileSystem → fs.getPath → I/O → close.

### 19.1. `Path.toFile()` có giới hạn

`Path.toFile()` chủ yếu interoperable với host default provider. `zipEntry.toFile()` trên JDK 17 ZIP provider đã kiểm thử **ném UnsupportedOperationException**. Vì thế một library nhận Path nhưng ép sang `java.io.File` có thể tự giới hạn khả năng hỗ trợ ZIP/virtual providers. Dùng trực tiếp `Files` streams/channels khi phù hợp.

### 19.2. ZIP FileStore và attribute views

`fs.supportedFileAttributeViews()` cho biết các views provider hỗ trợ. ZIPFS có view `zip`, có thể có POSIX view khi bật property `enablePosixFileAttributes`. Đừng coi metadata permissions trong ZIP là OS-enforced ACL; ZIP provider không bảo đảm thực thi permissions như filesystem host.

## 20. ZIP provider options và giới hạn

Theo module `jdk.zipfs` của JDK 17:

| Option | Ý nghĩa |
| --- | --- |
| `create` | Tạo archive khi chưa có, nếu true |
| `encoding` | Charset tên entries, mặc định UTF-8 |
| `enablePosixFileAttributes` | Bật POSIX attribute view nếu cần |
| `compressionMethod` | `DEFLATED` (mặc định) hoặc `STORED` |
| `releaseVersion` | Xử lý version entries khi đọc multi-release JAR |
| `defaultOwner`, `defaultGroup`, `defaultPermissions` | Giá trị metadata default khi view hỗ trợ |

Đây là **provider-specific properties**; không đưa options của ZIP sang default hoặc custom FS mà mong luôn được chấp nhận.

Provider cũng có giới hạn với ZIP hiện hữu chứa entry name có `.`/`..` như components. Không hứa mở được mọi archive bất thường hoặc sửa được mọi loại metadata.

## 21. Bảo mật khi xử lý ZIP do người dùng gửi

### 21.1. Tránh Zip Slip

Khi copy entries từ ZIP ra host, phải kiểm tra **đường dẫn output**. Một entry name độc hại có thể chứa `..` hoặc absolute path để ghi ngoài thư mục đích.

```java
Path base = outputDirectory.toAbsolutePath().normalize();
Path target = base.resolve(relativeEntryName).normalize();
if (!target.startsWith(base)) {
    throw new SecurityException("Archive entry escapes output");
}
```

Đây là **snippet**, không phải extractor hoàn chỉnh. Kiểm tra lexical containment không xử lý hết symlink ancestors, TOCTOU, quyền, tên đặc biệt và race khi giải nén. Dùng directory permissions, authorization và cơ chế handle-relative khi cần mức an toàn cao.

### 21.2. ZIP bombs và giới hạn tài nguyên

ZIP nén nhỏ có thể chứa số entry lớn hoặc tổng kích thước uncompressed rất lớn. Với input không tin cậy:
- Giới hạn số entry, kích thước từng file, tổng bytes, độ sâu path và thời gian xử lý.
- Không tự đọc toàn bộ entry lớn vào RAM.
- Có chính sách overwrite, permissions, file type và partial failure.
- Không xuất ra host path do user nhập mà chưa validate.
- Dọn dữ liệu tạm của chính ứng dụng và đóng ZIPFS đúng ownership.
- Nếu archive bị lỗi/giải nén dở, không báo extraction đã hoàn tất.

### 21.3. ZIPFS không phải transaction database

Đóng ZIPFS có thể hoàn tất các cập nhật archive, nhưng không cung cấp transaction ACID đa tệp, rollback, atomic publish hay bảo vệ tuyệt đối trước mất điện. Nếu ứng dụng cần tính toàn vẹn cao, phải có mô hình staging, backup, verification và publish phù hợp với file store.

## 22. Các exception quan trọng

| Exception | Dấu hiệu | Xử lý phù hợp |
| --- | --- | --- |
| `ProviderNotFoundException` | Scheme không có provider | Kiểm tra module/runtime |
| `FileSystemNotFoundException` | Lookup URI chưa có instance | Mở FS nếu đúng ownership |
| `FileSystemAlreadyExistsException` | Mount trùng URI | Dùng instance hiện có hoặc quản lý lifetime |
| `ClosedFileSystemException` | Dùng Path của FS đã đóng | Tạo Path từ FS còn mở |
| `ProviderMismatchException` | API từ chối Path provider không tương thích | Tạo Path đúng namespace |
| `NoSuchFileException` | Host file hoặc ZIP entry không có | Phân biệt host/ZIP path |
| `FileAlreadyExistsException` | Target đã có | Chính sách overwrite |
| `AccessDeniedException` | Thiếu quyền đọc/ghi | Không nhầm với unsupported |
| `UnsupportedOperationException` | Operation/provider không hỗ trợ | Capability check/fallback rõ |
| `InvalidPathException` | Path String sai provider syntax | Validate input |
| `IOException` | I/O/archive/close lỗi | Báo lỗi, cleanup có kiểm soát |

**Không dùng** một catch-all rồi coi mọi lỗi là “file chưa tồn tại”. Thiếu provider, FS đã đóng, entry thiếu và không có quyền là các trạng thái khác nhau với hướng khắc phục khác nhau.

## 23. Những lỗi tư duy thường gặp

| Sai lầm | Sửa thế nào |
| --- | --- |
| Coi Path chỉ là String | Path có FileSystem owner |
| Coi FileSystem là provider | Provider có thể tạo nhiều instances |
| Coi FileSystem là volume host | ZIPFS là virtual namespace |
| Dùng `Path.of` để tạo ZIP entry | `zipFs.getPath` hoặc `zipBase.resolve(String)` |
| Coi hai `/same.txt` là cùng file | Xét instance/provider và identity |
| Giả định `resolve` luôn giữ FS của base | Absolute foreign Path có thể được trả nguyên |
| Giả định mọi cross-provider operation đều lỗi | `Files.copy` có thể copy dữ liệu |
| Giả định mọi cross-provider `resolve` đều thành công | Default provider có thể ném mismatch |
| Dùng `getFileSystem(uri)` để mở ZIP lần đầu | `newFileSystem` khi cần mở |
| Coi ZIP file tồn tại là đang mount | Hai trạng thái khác nhau |
| Dùng Path sau ZIPFS close | Mở lại FS và lấy Path mới |
| Đóng default FS | Không tự đóng FS mặc định |
| Trả Path ZIPFS đã đóng cho caller | Quản lý owner/lifetime |
| Ép ZIP Path sang `java.io.File` | Dùng `Files` APIs |
| Coi `normalize` đủ chống path traversal | Cần policy bảo mật và TOCTOU |
| Coi ZIPFS hỗ trợ mọi permissions | Provider-specific views/options |
| Coi ZIPFS có trong mọi custom Java runtime | Kiểm tra `jdk.zipfs` |
| Coi close ZIPFS là transaction ACID | Cần staging/verification riêng |

## 24. Checklist triển khai

1. Mỗi Path thuộc FileSystem nào?
2. Có vô tình dùng `Path.of(String)` thay vì `zipFs.getPath` không?
3. Có phân biệt provider scheme với FileSystem instance chưa?
4. Có kiểm tra capability và provider module trên runtime đích không?
5. URI ZIP có được tạo từ `archive.toUri()` để tránh escape lỗi không?
6. Có hiểu `getFileSystem` chỉ lookup, không auto-mount không?
7. ZIPFS có được đóng bằng try-with-resources ở đúng scope không?
8. Có trả/giữ Path của FS đã đóng không?
9. Có tránh đóng FS của caller không?
10. Khi ghép Path, argument absolute/foreign có được xem xét không?
11. Có định nghĩa cross-provider copy policy, overwrite, metadata, partial failure chưa?
12. Có tránh dùng `toString()` làm global file key không?
13. Có tránh ép ZIP Path sang `java.io.File` không?
14. Có kiểm tra attribute views thay vì giả định theo OS không?
15. Có tách rõ host archive Path với ZIP entry Path không?
16. Với ZIP không tin cậy, có hạn mức entries/bytes và containment không?
17. Có xử lý provider unavailable, already mounted, closed FS và IOException khác nhau không?
18. Ví dụ/test có tạo và xóa đúng temp files do chính chương trình sở hữu không?
19. Có test trên JDK có `jdk.zipfs` và runtime tùy biến mục tiêu không?
20. Có phân biệt API core Java 7 và helper Java 9/11/13 trong tài liệu không?

## 25. Câu hỏi ôn tập

**1.** `Path.getFileSystem()` trả gì? — **FileSystem instance** mà Path thuộc về.

**2.** `FileSystem.provider()` trả gì? — **FileSystemProvider** quản lý instance.

**3.** Provider ZIP có scheme gì? — **`jar`**, khi module `jdk.zipfs` có mặt.

**4.** Default provider có scheme gì? — **`file`**.

**5.** Hai ZIP archives khác nhau có cùng provider được không? — **Có**, nhưng FileSystem instances riêng.

**6.** Hai Path khác FS nhưng cùng `toString()` có cùng object không? — **Không thể kết luận**.

**7.** `Path.of("abc")` có tạo ZIP Path không? — **Không**, factory String dùng default FS.

**8.** Muốn Path bên trong ZIP dùng gì? — **`zipFs.getPath(...)`**.

**9.** `getFileSystem(uri)` có tạo filesystem mới không? — **Không**.

**10.** `Files.copy` có thể copy từ host vào ZIP không? — **Có khi providers hỗ trợ**, đã test.

**11.** `resolve(Path absoluteFromOtherFs)` chắc chắn trả Path thuộc base FS? — **Không**, absolute argument có thể được trả lại.

**12.** Có dùng Path ZIP sau khi ZIPFS đóng để đọc tiếp? — **Không**, có thể gặp ClosedFileSystemException.

**13.** Đóng ZIPFS có xóa archive host không? — **Không**.

**14.** Có nên đóng default FileSystem? — **Không**.

**15.** ZIP Path có luôn `toFile()` được không? — **Không**, ZIPFS JDK 17 không hỗ trợ.

**16.** ZIPFS metadata POSIX có giống quyền host không? — **Không mặc nhiên**; phải xem provider/view.

**17.** `newFileSystem(Path)` có từ Java 7 không? — **Không**, overload tiện ích từ Java 13; core URI factory từ Java 7.

**18.** Những tiện ích `Path.of` và `Files.writeString` từ Java mấy? — **Java 11**.

**19.** Vì sao cần bảo vệ lúc extract ZIP? — **Zip Slip, quota, overwrite, resource exhaustion, permissions**.

**20.** Một phương thức chỉ nhận Path có được tự đóng `path.getFileSystem()`? — **Không**, trừ khi hợp đồng chuyển quyền sở hữu rõ ràng.

## 26. Bài tập thực hành

### A. Truy vết ba tầng

Chạy `ProviderLayersDemo` và kiểm tra đường dẫn tạo bằng `FileSystems.getDefault().getPath("a","b")` có chung FS với `Path.of("a","b")` hay không.

### B. Thêm entry vào ZIP

Sửa `ZipProviderDemo` để tạo hai files `/docs/a.txt` và `/docs/b.txt` rồi đọc nội dung trong khi ZIPFS mở.

### C. Path cùng tên nhưng hai namespaces

Chạy `TwoZipFileSystemsDemo`, đổi nội dung file A/B và ghi nhận same provider, different FS, same-looking paths, different content.

### D. Copy cross-provider

Chạy `CrossProviderCopyDemo`, phân biệt copy I/O với Path.resolve; thử đặt target ZIP entry vào directory chưa được tạo và xử lý IOException.

### E. Vòng đời ZIPFS

Chạy `ZipFileSystemLifecycleDemo`, xác minh oldPath lỗi sau close và new Path từ reopened FS đọc thành công.

### F. Mount/lookup

Chạy `ZipUriLookupDemo`, giải thích trường hợp trước mount, đang mount và sau close theo provider JDK 17.

### G. Provider capabilities

In `FileSystemProvider.installedProviders()` và `fs.supportedFileAttributeViews()`, so sánh default và ZIPFS trong môi trường thật.

### H. Bảo mật ZIP input

Thiết kế một extractor từ ZIPFS có giới hạn số entries/bytes, kiểm tra relative output paths và không ghi đè ngoài root được phép; không áp dụng ví dụ học trên thư mục dữ liệu thật.

### I. Path-to-File interoperability

Thử `zipFs.getPath("/docs/a.txt").toFile()` trong try/catch, so sánh với `Files.readString(zipEntry)`.

### J. Ownership

Thiết kế method nhận `Path input` và đọc nội dung nhưng **không** gọi `input.getFileSystem().close()`. Giải thích vì sao method không sở hữu resource được truyền vào.

## 27. Tài liệu chính thức

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `getFileSystem`, `resolve`, `normalize`, `toRealPath` và URI.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `getPath`, provider, lifecycle, capabilities.
- [Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): factories, URI lookup và các exceptions.
- [Java SE 17 — FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): SPI, schemes và installed providers.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): operations trên Path và cross-provider copy.
- [JDK 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP provider, URI scheme `jar` và provider-specific options.
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): dữ liệu lưu trữ và capability.
- [Java SE 17 — ProviderMismatchException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ProviderMismatchException.html): Path không tương thích provider.
- [Java SE 17 — ClosedFileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): FileSystem đã đóng.
- [Dev.java — File System](https://dev.java/learn/api/io/java-io/file-system/): tài liệu NIO.2 vẫn cập nhật.

**Ghi nhớ:** `Path` luôn thuộc một `FileSystem`, `FileSystem` do một `FileSystemProvider` triển khai, còn `Files` thực hiện thao tác lên tài nguyên thông qua Path. ZIPFS dùng `jar` và có nhiều instances độc lập, trong khi filesystem mặc định dùng `file`. Dùng đúng Path factory, quản lý ZIPFS lifecycle, hiểu giới hạn cross-provider và xử lý exceptions/capabilities tường minh sẽ giúp mã Java hiện đại vừa portable vừa dễ kiểm thử.
