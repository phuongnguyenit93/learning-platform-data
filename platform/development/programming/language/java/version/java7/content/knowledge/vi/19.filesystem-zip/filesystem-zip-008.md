# Lỗi nhà cung cấp không khớp hoặc hệ thống tệp đã đóng trong Java NIO.2

**Chủ đề:** Java 7 — FileSystem và ZIP  
**Bài học:** Lỗi nhà cung cấp không khớp hoặc hệ thống tệp đã đóng  
**Môi trường:** Java 17+ với NIO.2 (`java.nio.file`). Ví dụ ZIP dùng ZIP filesystem provider (`jdk.zipfs`) có trong nhiều bản phân phối JDK đầy đủ, nhưng có thể vắng mặt trong runtime tùy biến. Những API `Path`, `FileSystem`, `Files`, `FileSystems`, `ProviderMismatchException` và `ClosedFileSystemException` vẫn hiện hành.

## 1. Hai lỗi trông giống nhau nhưng nguyên nhân hoàn toàn khác

Khi Java coi tệp ZIP như một filesystem, bạn có thể thao tác nội dung ZIP bằng `Path` giống như với một thư mục bình thường. Tuy nhiên, một `Path` không chỉ là tên file. Nó luôn gắn với **một `FileSystem`**, và `FileSystem` gắn với **một `FileSystemProvider`**.

Hai lỗi trọng tâm:

- **`ProviderMismatchException`:** một phương thức nhận đối tượng do **provider A** tạo ra nhưng được truyền đối số do **provider B** tạo ra, trong khi phương thức cần đối tượng thuộc provider tương thích. Ví dụ gọi `zipPath.resolve(defaultPath)` với `zipPath` thuộc ZIP filesystem và `defaultPath` thuộc filesystem mặc định.
- **`ClosedFileSystemException`:** một thao tác cần truy cập file được gọi qua `Path` thuộc một **`FileSystem` đã đóng**. Ví dụ bạn giữ `Path` bên trong ZIP ra khỏi khối `try-with-resources` rồi mới gọi `Files.readString(path)`.

Điểm nhận diện:

| Vấn đề | ProviderMismatchException | ClosedFileSystemException |
| --- | --- | --- |
| Nguyên nhân trực tiếp | Phối hợp đối tượng khác provider trong operation không hỗ trợ phối hợp | Sử dụng filesystem đã đóng để thao tác file |
| Superclass | `IllegalArgumentException` | `IllegalStateException` |
| Checked? | **Không**, runtime exception | **Không**, runtime exception |
| Mối liên hệ với ZIP | Dễ gặp khi trộn `Path.of(...)` của default FS và `zipFs.getPath(...)` | Dễ gặp sau `zipFs.close()` hoặc sau khi ra khỏi TWR |
| Cách sửa căn bản | Tạo đường dẫn thành phần từ **đúng `FileSystem`** | Giữ filesystem mở trong toàn bộ vòng đời I/O; hoặc mở lại và lấy **Path mới** |
| Có nên retry mù? | Không: thường là bug truyền đối tượng | Không: cần sửa ownership/lifecycle, không dùng lại Path cũ |

**Không phải mọi phép toán có hai `Path` khác provider đều ném `ProviderMismatchException`.** `Files.copy(source, target)` và `Files.move(source, target)` có contract hỗ trợ nguồn và đích thuộc provider khác nhau trong những giới hạn cụ thể. Ngược lại, `Path.resolve(Path)`, `relativize(Path)` và nhiều phép xử lý tên đường dẫn cần cùng provider/filesystem. Bài sẽ phân biệt bằng code chạy được.

Cả hai lỗi xuất hiện từ Java 7 và **vẫn được dùng** ở Java 17/21 trở lên. Không nên thay thế NIO.2 bằng một API cũ chỉ để tránh phải hiểu lifecycle.

## 2. FileSystem, provider và Path tạo thành một quan hệ sở hữu

Ba khái niệm:

1. **`FileSystemProvider`:** implementation cung cấp file operations, ví dụ provider với scheme `file` cho filesystem mặc định hoặc `jar` cho ZIP/JAR filesystem.
2. **`FileSystem`:** một đối tượng filesystem cụ thể. Một provider có thể tạo **nhiều filesystem instances**, ví dụ hai ZIP archives khác nhau.
3. **`Path`:** đường dẫn chỉ tới một file hoặc directory **trong một filesystem cụ thể**.

Quan hệ:

```text
Java process
  ├── default provider ("file")
  │     └── default FileSystem
  │           ├── Path: C:\data\notes.txt   (ví dụ Windows)
  │           └── Path: /srv/data/notes.txt (ví dụ Unix)
  │
  └── ZIP provider ("jar", nếu runtime có)
        ├── FileSystem của archive-a.zip
        │     ├── Path: /docs/readme.md
        │     └── Path: /config.json
        └── FileSystem của archive-b.zip
              └── Path: /docs/readme.md
```

Tên `/docs/readme.md` trong hai ZIP archives có vẻ giống nhau nhưng **không phải cùng một file**, vì chúng thuộc hai `FileSystem` khác nhau.

Các phép truy vấn không mở file:

```java
FileSystem owner = path.getFileSystem();
FileSystemProvider provider = owner.provider();
String scheme = provider.getScheme();
boolean open = owner.isOpen();
```

Đây là snippet; cần import `Path`, `FileSystem`, `FileSystemProvider` và biến `path`. `isOpen()` là quan sát tình trạng của filesystem tại lúc hỏi, **không là khóa** bảo đảm filesystem còn mở khi thao tác I/O tiếp theo chạy trong thread khác.

### 2.1. Đường dẫn ZIP phải được tạo từ ZIP FileSystem

Với ZIP filesystem được mount thành công:

```java
Path insideZip = zipFs.getPath("/docs/readme.md");
Path local = Path.of("docs", "readme.md");
```

Hai `Path` trên là hai object của **hai filesystem khác nhau** mặc dù mô tả tên tương tự.

- `Path.of(...)`/`Paths.get(String, ...)` theo kiểu string thông thường dùng **default filesystem**.
- `zipFs.getPath(...)` tạo `Path` thuộc filesystem ZIP vừa mở.
- `insideZip.getFileSystem()` trả đối tượng ZIP filesystem đang sở hữu `insideZip`.
- `Files.readString(insideZip)` định tuyến thao tác tới provider của `insideZip` khi filesystem còn mở.

**Không chuyển `Path` của filesystem này sang filesystem kia bằng cách ép kiểu**. Nếu chỉ cần giữ tên entry, bạn có thể lấy `getFileName().toString()` rồi tạo `Path` mới với **factory của filesystem đích**, nhưng phải kiểm tra cấu trúc/tên nếu dữ liệu không đáng tin.

### 2.2. Ví dụ runnable: nhận diện provider của hai Path

Tạo `ZipProviderIdentityDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipProviderIdentityDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-id-");
        Path archive = dir.resolve("example.zip");
        Path local = dir.resolve("outside.txt");

        try {
            Files.writeString(
                    local, "OUTSIDE", StandardCharsets.UTF_8);

            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        archive, Map.of("create", "true"))) {
                Path inner = zipFs.getPath("/inside.txt");
                Files.writeString(
                        inner, "INSIDE", StandardCharsets.UTF_8);

                System.out.println(
                        "local-scheme="
                        + local.getFileSystem()
                            .provider().getScheme());
                System.out.println(
                        "zip-scheme="
                        + inner.getFileSystem()
                            .provider().getScheme());
                System.out.println(
                        "providers-differ="
                        + (local.getFileSystem().provider()
                            != inner.getFileSystem().provider()));
                System.out.println(
                        "inner-text="
                        + Files.readString(
                            inner, StandardCharsets.UTF_8));
                System.out.println(
                        "zip-open=" + zipFs.isOpen());
            }
        } finally {
            Files.deleteIfExists(local);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipProviderIdentityDemo.java
java ZipProviderIdentityDemo
```

**stdout khi ZIP provider có sẵn:**

```text
local-scheme=file
zip-scheme=jar
providers-differ=true
inner-text=INSIDE
zip-open=true
```

**Giải thích:**

- `FileSystems.newFileSystem(archive, Map.of("create", "true"))` yêu cầu tạo/mở một ZIP filesystem tại một pathname ZIP **chưa tồn tại**.
- `local` thuộc provider mặc định, còn `inner` thuộc provider ZIP.
- Cả hai đều dùng kiểu Java `Path` nhưng **không thay thế lẫn nhau** trong mọi method của `Path`.
- `try (FileSystem zipFs = ...)` đảm bảo đóng ZIP filesystem sau khi hoàn tất.
- Các file demo được tạo trong thư mục tạm và chỉ xóa **sau khi ZIP filesystem đã đóng**, quan trọng đặc biệt trên Windows.

Overload `FileSystems.newFileSystem(Path, Map)` có từ **Java 13**; hoàn toàn hợp lệ với hướng dẫn Java 17+. Java 7 đã có các factory `newFileSystem(URI, Map)`, và cả `Path`/`FileSystem`/hai exception trọng tâm đều bắt đầu từ Java 7. Không cần sử dụng syntax hoặc library lỗi thời.

**Nếu module/provider ZIP không có**, lời gọi mở có thể ném `ProviderNotFoundException`; không suy rằng mọi Java runtime đều cung cấp ZIPFS. Một bản runtime được tạo bằng `jlink` có thể bỏ module `jdk.zipfs`. Khi ZIPFS là yêu cầu chức năng, hãy kiểm tra runtime cấu hình đúng, không catch rồi giả mạo kết quả.

## 3. Khi nào ProviderMismatchException xuất hiện?

Theo JavaDoc, `ProviderMismatchException` là unchecked exception ném khi **phương thức trên một đối tượng của provider này** được truyền **tham số của provider khác**, trong khi phương thức yêu cầu tham số tương thích.

Các thao tác dễ nhầm:

```java
Path zipDir = zipFs.getPath("/docs");
Path localName = Path.of("readme.txt");

// Không phù hợp: zipDir và localName thuộc provider khác.
Path bad = zipDir.resolve(localName);

// Đúng nếu muốn child tên readme.txt trong ZIP:
Path good = zipDir.resolve("readme.txt");
```

Đây là snippet minh họa với `zipFs` đã mở. `resolve(String)` tạo pathname thành phần bằng **filesystem của receiver**, vì vậy tránh nhét `Path` do default provider tạo vào `zipDir.resolve(Path)`.

### 3.1. Các phương thức phải đánh giá riêng

| API | Kỳ vọng hợp lý với Path khác provider |
| --- | --- |
| `zipPath.resolve(defaultPath)` | Có thể ném `ProviderMismatchException` |
| `zipPath.relativize(defaultPath)` | Có thể ném `ProviderMismatchException` |
| `zipPath.compareTo(defaultPath)` | Có thể ném `ClassCastException` hoặc `ProviderMismatchException` tùy contract/implementation; không dùng để sort path khác provider |
| `zipPath.startsWith(defaultPath)` | Với provider khác, JavaDoc cho phép **trả false**; đừng ép khẳng định mọi phép so đều ném |
| `zipPath.endsWith(defaultPath)` | Có thể trả false, không tự tạo quan hệ cùng provider |
| `zipPath.resolve("child.txt")` | Dùng string overload, thuộc provider của zipPath |
| `zipFs.getPath("child.txt")` | Tạo Path đúng ZIP filesystem |
| `Files.copy(zipPath, localPath)` | **Được thiết kế cho copy chéo provider** khi thao tác hỗ trợ |
| `Files.move(zipPath, localPath)` | Có thể di chuyển chéo provider trong giới hạn; **không cam kết atomic move** |

Không nên viết một hàm chung bắt tất cả `IllegalArgumentException` rồi tuyên bố “provider mismatch”. Loại ngoại lệ và thao tác cụ thể có ý nghĩa riêng. Nếu input là chuỗi mode/path không hợp lệ, `IllegalArgumentException` có thể đến từ hoàn cảnh khác.

### 3.2. Ví dụ runnable: so Path thuộc ZIP và default FS

Tạo `ZipPathMismatchDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderMismatchException;
import java.util.Map;

public class ZipPathMismatchDemo {
    static boolean mismatched(Runnable task) {
        try {
            task.run();
            return false;
        } catch (ProviderMismatchException ex) {
            return true;
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-mismatch-");
        Path archive = dir.resolve("example.zip");

        try {
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        archive, Map.of("create", "true"))) {
                Path zipPath = zipFs.getPath("/docs");
                Path defaultChild = Path.of("child.txt");

                System.out.println(
                        "resolve-mismatch="
                        + mismatched(
                            () -> zipPath.resolve(defaultChild)));
                System.out.println(
                        "relativize-mismatch="
                        + mismatched(
                            () -> zipPath.relativize(defaultChild)));
                System.out.println(
                        "compare-mismatch="
                        + mismatched(
                            () -> zipPath.compareTo(defaultChild)));

                Path correct = zipPath.resolve("child.txt");
                System.out.println(
                        "correct-provider="
                        + (correct.getFileSystem() == zipFs));
                System.out.println(
                        "correct-name="
                        + correct.getFileName());
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipPathMismatchDemo.java
java ZipPathMismatchDemo
```

**stdout trên JDK ZIP provider chuẩn:**

```text
resolve-mismatch=true
relativize-mismatch=true
compare-mismatch=true
correct-provider=true
correct-name=child.txt
```

Các phép gọi được test từng cái và **không làm thay đổi ZIP archive**. Chúng dùng hai provider `jar`/`file` thật. Với các provider tùy biến, chi tiết exception cho những phép so/path operations có thể khác; hãy xem contract của từng method thay vì mở rộng kết luận sang mọi provider.

**Khác biệt quan trọng:** một số phép predicate như `startsWith(Path)` có thể trả `false` khi filesystem không tương thích, thay vì ném. Do đó, đừng viết test “mọi thao tác trộn Path đều phải ném `ProviderMismatchException`”. Hãy kiểm tra từng operation mà ứng dụng thật sự dùng.

## 4. Sửa lỗi: luôn tạo Path thành phần bằng đúng FileSystem

Lỗi thường phát sinh từ việc dùng mặc định `Path.of(...)` trong một utility được truyền `Path` ZIP:

```java
static Path faultyChild(Path parent, String name) {
    return parent.resolve(Path.of(name));
}
```

Đây là snippet. Nếu `parent` thuộc ZIPFS, còn `Path.of(name)` thuộc default FS, `resolve(Path)` có nguy cơ `ProviderMismatchException`.

Hai cách sửa:

```java
static Path childByString(Path parent, String name) {
    return parent.resolve(name);
}

static Path childBySameFileSystem(
        Path parent, String name) {
    Path child = parent.getFileSystem().getPath(name);
    return parent.resolve(child);
}
```

Đây cũng là snippets. Chúng bảo đảm pathname thành phần được tạo qua đúng filesystem của `parent`. **Tuy nhiên:** đối với tên do người dùng gửi, cần validate tên/đường dẫn và security boundary; sửa provider mismatch **không đồng nghĩa đã chặn path traversal**.

### 4.1. Không dùng Path.toString làm “converter” phổ quát

Một cách sửa có vẻ hấp dẫn:

```java
Path copied = Path.of(zipEntry.toString());
```

Nó tạo ra Path thuộc **default filesystem** với chuỗi biểu diễn của ZIP Path; `"/docs/a.txt"` giờ có thể chỉ một file trên ổ thật chứ không phải entry trong ZIP. Đây **không phải conversion đồng nhất đối tượng file**.

Khi cần sử dụng tên từ ZIP:

```java
String name = zipEntry.getFileName().toString();
Path destination = trustedOutputDir.resolve(name);
```

Đây là snippet dành cho trường hợp bạn **chủ ý** lấy **file name đơn** để tạo destination trong default filesystem. Phải kiểm soát collisions, ký tự/độ dài tên, case sensitivity, traversal, reserved names của OS, symbolic links và phần nội dung được phép xuất.

**Nếu cần giữ nguyên file:** dùng `Files.copy(source, target)` với source/destination đúng provider — không “chuyển” source Path về default provider rồi cố `Files.readString` ở path mới.

### 4.2. Kiểm tra trước khi phối hợp Path

```java
if (left.getFileSystem() != right.getFileSystem()) {
    throw new IllegalArgumentException(
            "Paths belong to different FileSystem instances");
}
```

Đây là một guard **nghiêm ngặt**, hữu ích khi API của bạn yêu cầu hai path thuộc **chính cùng một FileSystem instance**. Không phải quy tắc bắt buộc cho `Files.copy`; cũng không nhất thiết đủ để đảm bảo phép toán hợp lệ (ví dụ một absolute path và relative path không phải lúc nào `relativize` được).

**Một provider có thể có nhiều filesystem instances.** Hai path từ hai ZIP archives có thể cùng `provider().getScheme() == "jar"` nhưng **khác FileSystem**, vì vậy so scheme `"jar"` không chứng minh chúng có thể `resolve`/`relativize` cùng nhau.

## 5. Files.copy hoạt động khác Path.resolve

`Files.copy(Path source, Path target, CopyOption...)` cho phép `target` thuộc provider khác `source`. Đây là **tính năng của Files.copy**, không phải một ngoại lệ bí mật của `Path.resolve(Path)`.

Cơ chế copy giữa providers có thể dùng stream/transfer bên dưới, với giới hạn như:

- Không là thao tác nguyên tử tổng thể.
- Có thể tốn bộ nhớ/I/O tùy implementation và kích thước.
- Khi lỗi giữa chừng, destination có thể tồn tại **không hoàn chỉnh**.
- Một số attributes không được copy đầy đủ/giữ nguyên giữa providers.
- `REPLACE_EXISTING` cần được xét nếu destination đã tồn tại; không tùy tiện overwrite file khác.
- ZIPFS có thể có quy tắc về directories, attributes, case sensitivity và compressed storage.

### 5.1. Ví dụ runnable: copy hai chiều qua provider

Tạo `ZipCrossProviderCopyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipCrossProviderCopyDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-copy-");
        Path archive = dir.resolve("storage.zip");
        Path source = dir.resolve("source.txt");
        Path extracted = dir.resolve("extracted.txt");

        try {
            Files.writeString(
                    source, "FROM-LOCAL",
                    StandardCharsets.UTF_8);

            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        archive, Map.of("create", "true"))) {
                Path zipped = zipFs.getPath("/inside.txt");

                Files.copy(source, zipped);
                Files.copy(zipped, extracted);

                System.out.println(
                        "zip-copy="
                        + Files.readString(
                            zipped, StandardCharsets.UTF_8));
                System.out.println(
                        "local-copy="
                        + Files.readString(
                            extracted, StandardCharsets.UTF_8));
                System.out.println(
                        "different-provider="
                        + (source.getFileSystem().provider()
                            != zipped.getFileSystem().provider()));

                Files.writeString(
                        extracted, "CHANGED",
                        StandardCharsets.UTF_8);
                System.out.println(
                        "copy-independent="
                        + Files.readString(
                            zipped, StandardCharsets.UTF_8)
                            .equals("FROM-LOCAL"));
            }
        } finally {
            Files.deleteIfExists(extracted);
            Files.deleteIfExists(source);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipCrossProviderCopyDemo.java
java ZipCrossProviderCopyDemo
```

```text
zip-copy=FROM-LOCAL
local-copy=FROM-LOCAL
different-provider=true
copy-independent=true
```

Hai chiều `Files.copy` đều hoạt động trên JDK ZIP provider mặc định, trong khi `Path.resolve(Path)` với Path khác provider ở ví dụ trước ném mismatch. Đây chính là **ranh giới API** cần nhớ.

**Không dùng `Files.move(..., ATOMIC_MOVE)` làm lối đi mặc định giữa ZIPFS và filesystem thật.** `Files.move` có thể hỗ trợ chuyển giữa providers, nhưng `ATOMIC_MOVE` thường không khả dụng khi phải thực hiện copy/delete và có thể ném `AtomicMoveNotSupportedException`. Nếu di chuyển không nguyên tử thất bại, trạng thái source/target có thể không xác định theo contract. Với tài liệu/backup quan trọng, nên copy ra pathname tạm, validate, sau đó publish theo chính sách filesystem đích và chỉ xóa nguồn khi đã commit hợp lệ.

## 6. ClosedFileSystemException: Path còn nhưng FileSystem đã đóng

ZIP filesystem không phải chỉ là đối tượng string; nó giữ lifecycle của archive. Khi gọi `FileSystem.close()`:

- ZIPFS kết thúc lifecycle, có thể flush các thay đổi vào archive.
- Các thao tác I/O trên `Path` thuộc ZIPFS đã đóng sẽ không hoạt động như khi mở; có thể ném `ClosedFileSystemException`.
- Các object `Path` cũ **không tự chuyển** sang ZIPFS mới khi archive được mở lại.
- `FileSystem.isOpen()` trả false sau close.
- Muốn tiếp tục đọc, hãy **mở filesystem mới và tạo Path mới từ filesystem đó**.

Mẫu lỗi:

```java
Path retained;

try (FileSystem zipFs =
        FileSystems.newFileSystem(archive, Map.of())) {
    retained = zipFs.getPath("/report.txt");
}

// ZIP filesystem đã đóng:
String text = Files.readString(retained); // Sai lifecycle.
```

Đây là snippet minh họa lỗi, không phải chương trình chạy độc lập. Exception thường là `ClosedFileSystemException` theo provider ZIP.

**Cạm bẫy:** `retained != null` và `retained.toString()` vẫn có thể hoạt động sau close. Một số phép xử lý **thuần cú pháp** như `getFileName()` hoặc `resolve("child")` có thể thành công vì chúng không đụng storage. Vì vậy **đừng dùng khả năng toString/resolve như bằng chứng filesystem còn mở**.

### 6.1. Ví dụ runnable: close rồi reopen đúng cách

Tạo `ClosedZipFileSystemDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.ClosedFileSystemException;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ClosedZipFileSystemDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-close-");
        Path archive = dir.resolve("example.zip");
        Path retained;
        FileSystem previous;

        try {
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        archive, Map.of("create", "true"))) {
                previous = zipFs;
                retained = zipFs.getPath("/data.txt");
                Files.writeString(
                        retained, "HELLO", StandardCharsets.UTF_8);
                System.out.println(
                        "inside-open=" + zipFs.isOpen());
            }

            System.out.println(
                    "after-close-open=" + previous.isOpen());

            try {
                Files.readString(
                        retained, StandardCharsets.UTF_8);
                System.out.println("unexpected-read");
            } catch (ClosedFileSystemException ex) {
                System.out.println(
                        "retained-path-rejected=true");
            }

            try (FileSystem reopened =
                    FileSystems.newFileSystem(
                        archive, Map.of())) {
                Path fresh = reopened.getPath("/data.txt");
                System.out.println(
                        "reopened-text="
                        + Files.readString(
                            fresh, StandardCharsets.UTF_8));
                System.out.println(
                        "fresh-filesystem="
                        + (fresh.getFileSystem() == reopened));
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ClosedZipFileSystemDemo.java
java ClosedZipFileSystemDemo
```

```text
inside-open=true
after-close-open=false
retained-path-rejected=true
reopened-text=HELLO
fresh-filesystem=true
```

Đây là ví dụ đặc biệt quan trọng: **reopen không làm Path cũ sống lại**. `reopened.getPath("/data.txt")` tạo một `Path` mới gắn với filesystem đang mở. Vì archive đã được đóng/flush trước khi reopen, nội dung `HELLO` có thể đọc lại.

**Ghi nhớ ownership:** `Path` không có phương thức `close()` riêng. Bạn phải quản lý vòng đời của **`FileSystem`** — và mọi stream, channel, reader/writer dùng filesystem đó.

## 7. Default FileSystem không giống ZIP FileSystem về quyền đóng

Filesystem mặc định:

```java
FileSystem defaultFs = FileSystems.getDefault();
```

Là đối tượng sống cùng default provider của JVM. Theo contract, mặc định nó không thể bị đóng như một ZIP filesystem mở riêng; gọi `defaultFs.close()` có thể ném `UnsupportedOperationException`.

**Không viết `try (FileSystem fs = FileSystems.getDefault())` như một pattern cleanup phổ quát.** `try-with-resources` nên dùng cho filesystem mà component **thực sự tạo/mở và sở hữu**, chẳng hạn ZIPFS qua `newFileSystem`.

ZIP filesystem riêng:

```java
try (FileSystem zipFs =
        FileSystems.newFileSystem(zipPath, Map.of())) {
    Path entry = zipFs.getPath("/docs/file.txt");
    // Đọc/ghi tại đây.
}
```

Khi code đóng ZIPFS, đừng trả `entry`, `Stream<Path>` hay `InputStream` phụ thuộc vào ZIPFS cho caller sử dụng sau scope. Cần **materialize kết quả độc lập** (chuỗi, bytes có kiểm soát, DTO) hoặc đưa quyền sở hữu filesystem ra một API mà caller phải `close` đúng thời điểm.

### 7.1. Khi nhiều component cùng dùng một ZIPFS

Giả sử một service cache `FileSystem` để phục vụ nhiều request:

```text
ArchiveManager
  ├── sở hữu zipFs của archive X
  ├── Request A -> đọc /docs/a.md
  ├── Request B -> đọc /docs/b.md
  └── shutdown -> đóng zipFs sau khi các request đang dùng kết thúc
```

Nếu Request A gọi `zipFs.close()` trong khi Request B đang đọc, Request B có thể gặp `ClosedFileSystemException` hoặc lỗi I/O do lifecycle không hợp lệ. **Đừng để mọi request tự close một filesystem dùng chung**.

Thiết kế ownership rõ:

- Component tạo filesystem sở hữu việc close.
- Nếu share, dùng lifecycle manager/ref-count/lease được thiết kế thích hợp; không chỉ share biến toàn cục.
- Chặn task mới khi bắt đầu shutdown.
- Chờ/cancel tasks hiện có theo policy, sau đó close.
- Nếu tệp ZIP thay đổi ở ngoài khi filesystem đang mở, đừng giả định provider tự reload; hãy thiết kế reopen/versioning có kiểm soát.
- Đừng dùng một `Path` cache vĩnh viễn mà không lưu ý phiên bản/lifecycle của filesystem sở hữu nó.

### 7.2. isOpen() không giải quyết race đồng thời

Code sau **không phải kiểm tra atomically usable**:

```java
if (zipFs.isOpen()) {
    Files.readString(zipFs.getPath("/docs/a.md"));
}
```

Thread khác có thể đóng `zipFs` **sau** `isOpen()` nhưng **trước** `Files.readString`. Với hệ thống đồng thời, cần ownership/lease và synchronization thích hợp, đồng thời vẫn xử lý `ClosedFileSystemException`/`IOException` tại ranh giới thao tác I/O.

Không catch `ClosedFileSystemException` rồi sleep/retry **trên cùng Path**: filesystem đã đóng không được hồi sinh bằng cách chờ. Hãy sửa lifecycle hoặc mở session mới, rồi lấy Path mới.

## 8. FileSystemNotFoundException và FileSystemAlreadyExistsException: hai lỗi khác nữa

Hai exception liên quan việc tìm/mount `FileSystem` **không đồng nhất** với `ClosedFileSystemException`:

- **`FileSystemNotFoundException`:** yêu cầu tìm một filesystem theo URI, nhưng không có instance tương ứng trong phạm vi quản lý của provider. Ví dụ gọi `FileSystems.getFileSystem(jarUri)` trước khi mount.
- **`FileSystemAlreadyExistsException`:** cố tạo/mount lại một filesystem với URI đã có một instance đang mở theo contract của provider.
- **`ClosedFileSystemException`:** bạn có một `Path` của một filesystem đã đóng rồi tiếp tục thao tác I/O với nó.
- **`ProviderNotFoundException`:** không tìm được provider hỗ trợ scheme/tệp theo factory được gọi. Có thể gặp nếu runtime thiếu `jdk.zipfs`.

Đừng ghi log tất cả như “ZIP corrupt”. Một lỗi lifecycle/registration hoàn toàn khác lỗi archive bị hỏng hoặc thiếu quyền.

### 8.1. URI jar và thao tác mount

Một ZIP/JAR URI thường có dạng:

```text
jar:file:///.../archive.zip
```

URI của một entry có thể có thêm `!/entry/path`:

```text
jar:file:///.../archive.zip!/docs/readme.md
```

**URI** không giống `Path.of("...")`. Chọn API theo mục đích:

- `FileSystems.newFileSystem(jarUri, env)`: tạo/mount một instance khi provider hỗ trợ.
- `FileSystems.getFileSystem(jarUri)`: tìm một instance **đã được tạo**.
- `Path.of(entryUri)`: yêu cầu provider xử lý URI của entry; với ZIPFS trên JDK, thường cần instance filesystem tương ứng đã tồn tại.
- `zipFs.getPath("/docs/readme.md")`: cách trực tiếp nhất để lấy Path khi bạn đã có ZIPFS instance.

Cách mở bằng URI là API được giới thiệu từ Java 7; bản thân Java 17+ cũng hỗ trợ overload mở bằng `Path` thuận tiện.

### 8.2. Ví dụ runnable: chưa mount, mount trùng, rồi unmount

Tạo `ZipUriMountDemo.java`:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystemAlreadyExistsException;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipUriMountDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-uri-");
        Path archive = dir.resolve("data.zip");
        URI jarUri = URI.create("jar:" + archive.toUri());
        URI entryUri = URI.create(
                jarUri + "!/message.txt");

        try {
            try {
                FileSystems.getFileSystem(jarUri);
                System.out.println("unexpected-mounted");
            } catch (FileSystemNotFoundException ex) {
                System.out.println("before-mount=NOT_FOUND");
            }

            try (FileSystem mounted =
                    FileSystems.newFileSystem(
                        jarUri, Map.of("create", "true"))) {
                Path item = mounted.getPath("/message.txt");
                Files.writeString(
                        item, "URI", StandardCharsets.UTF_8);

                System.out.println(
                        "mounted=" + mounted.isOpen());
                System.out.println(
                        "entry-scheme="
                        + Path.of(entryUri)
                            .getFileSystem().provider().getScheme());

                try (FileSystem duplicate =
                        FileSystems.newFileSystem(
                            jarUri, Map.of())) {
                    System.out.println(
                            "unexpected-second="
                            + duplicate.isOpen());
                } catch (FileSystemAlreadyExistsException ex) {
                    System.out.println("second-mount=ALREADY_EXISTS");
                }
            }

            try {
                FileSystems.getFileSystem(jarUri);
                System.out.println("unexpected-after-close");
            } catch (FileSystemNotFoundException ex) {
                System.out.println("after-close=NOT_FOUND");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipUriMountDemo.java
java ZipUriMountDemo
```

**stdout với JDK ZIP provider chuẩn:**

```text
before-mount=NOT_FOUND
mounted=true
entry-scheme=jar
second-mount=ALREADY_EXISTS
after-close=NOT_FOUND
```

**Mục đích:** giải thích cơ chế lookup bằng URI và mount lifecycle. Vì tên ZIP trong thư mục tạm là mới, trước lần `newFileSystem` đầu tiên không có mount cùng URI. Trong khối TWR, provider quản lý một instance nên yêu cầu mount lại cùng URI báo already exists. Sau close, lookup không thấy mount nữa.

**Không biến ví dụ này thành “mount ZIP dùng chung toàn hệ thống”**. Sự tồn tại của instance được quản lý trong runtime/provider, không có nghĩa một Java process khác sẽ nhìn thấy cùng `FileSystem` object.

Một số overload `newFileSystem(Path, Map)` tạo instance theo cách **khác cách lookup bằng URI**, nên không nên giả định mọi provider map hai cách mở vào cùng khóa quản lý. Với một ứng dụng, chọn một cơ chế mount nhất quán và quản lý ownership rõ.

## 9. Không trả Path/Stream từ một ZIPFS đã bị đóng

Vấn đề thường xuất hiện khi viết helper:

```java
static Path getReportPath(Path archive)
        throws IOException {
    try (FileSystem fs =
            FileSystems.newFileSystem(archive, Map.of())) {
        return fs.getPath("/reports/latest.csv");
    }
}
```

Đây là snippet minh họa lỗi thiết kế. Khi method trả về, `fs` đã đóng; caller nhận `Path` không còn dùng được cho I/O.

**Sai tương tự:** trả `Stream<Path>` được tạo từ `Files.walk(fs.getPath("/"))` nhưng lại đóng `fs` trước khi caller thực thi terminal operation. Java streams nhiều khi **lazy** và còn có tài nguyên riêng cần close.

Sửa đúng theo **trách nhiệm trả dữ liệu**:

- Nếu method trả nội dung, đọc `Files.readString`/**streaming read** bên trong TWR, rồi trả một object độc lập.
- Nếu method trả danh sách, duyệt và materialize `List<String>` trong scope còn mở; đóng `Stream<Path>` và ZIPFS trước khi return.
- Nếu API cần trả lazy paths/stream, phải thiết kế wrapper `AutoCloseable` có ownership rõ, và caller chịu trách nhiệm giữ filesystem sống rồi đóng.
- Nếu caller cần update ZIPFS, nên truyền callback/function được thực thi bên trong một scope do service quản lý; không để caller giữ `Path` sau scope.

### 9.1. Ví dụ runnable: materialize danh sách trước khi close ZIPFS

Tạo `ZipScopedListingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public class ZipScopedListingDemo {
    static List<String> listFiles(Path archive)
            throws IOException {
        try (FileSystem zipFs =
                FileSystems.newFileSystem(
                    archive, Map.of())) {
            try (Stream<Path> entries =
                    Files.walk(zipFs.getPath("/"))) {
                return entries
                        .filter(Files::isRegularFile)
                        .map(Path::toString)
                        .sorted()
                        .toList();
            }
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("zip-list-");
        Path archive = dir.resolve("docs.zip");

        try {
            try (FileSystem zipFs =
                    FileSystems.newFileSystem(
                        archive, Map.of("create", "true"))) {
                Files.createDirectory(zipFs.getPath("/docs"));
                Files.writeString(
                        zipFs.getPath("/readme.txt"),
                        "ROOT", StandardCharsets.UTF_8);
                Files.writeString(
                        zipFs.getPath("/docs/guide.txt"),
                        "GUIDE", StandardCharsets.UTF_8);
            }

            List<String> names = listFiles(archive);
            System.out.println("names=" + names);
            System.out.println("count=" + names.size());

            try {
                names.add("/extra.txt");
                System.out.println("unexpected-mutable");
            } catch (UnsupportedOperationException ex) {
                System.out.println("immutable=true");
            }
        } finally {
            Files.deleteIfExists(archive);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipScopedListingDemo.java
java ZipScopedListingDemo
```

```text
names=[/docs/guide.txt, /readme.txt]
count=2
immutable=true
```

**Vì sao đúng?** `Files.walk` tạo một `Stream<Path>` cần đóng; TWR trong `listFiles` đóng stream **trước** ZIP filesystem. `toList()` tạo một danh sách không sửa được, chứa **Strings**, không giữ `Path` cần I/O. Khi caller nhận danh sách, ZIPFS đã đóng nhưng strings vẫn độc lập.

**Cảnh báo bộ nhớ:** `toList()` materialize toàn bộ tên file. Nếu ZIP chứa hàng triệu entries, hãy dùng streaming consumer bên trong scope, pagination phù hợp hoặc giới hạn quota và số entry; không dùng `toList()` không giới hạn trên ZIP không tin cậy.

### 9.2. Close có thể ném IOException

`FileSystem.close()` thuộc `Closeable`; provider ZIP có thể gặp lỗi I/O khi kết thúc/flush archive. `try-with-resources` đảm bảo gọi close và giữ **suppressed exceptions** theo ngữ nghĩa Java, nhưng không bảo đảm close luôn thành công.

Nếu việc cập nhật ZIP cần độ tin cậy:

- Chỉ báo success sau khi TWR hoàn tất không lỗi.
- Nếu close/flush thất bại, coi archive có thể chưa được ghi hoàn chỉnh.
- Đừng xóa file tạm của bản backup nếu chưa xác nhận kết quả.
- Không catch `IOException` rồi trả success chỉ vì `Files.writeString` bên trong ZIPFS đã trả về.
- Với archive nhạy cảm, dùng staging và thao tác publish trên filesystem thật theo policy, không ghi trực tiếp đè archive production.

## 10. Phân loại đúng các exception liên quan ZIP filesystem

| Exception | Loại | Thường xảy ra khi |
| --- | --- | --- |
| `ProviderMismatchException` | Unchecked, `IllegalArgumentException` | Truyền `Path` khác provider vào operation không hỗ trợ mix |
| `ClosedFileSystemException` | Unchecked, `IllegalStateException` | Dùng file operation qua `Path` của FileSystem đã đóng |
| `FileSystemNotFoundException` | Unchecked | Lookup filesystem/URI chưa được mount hoặc không còn registered |
| `FileSystemAlreadyExistsException` | Unchecked | Tạo cùng FileSystem URI đang active |
| `ProviderNotFoundException` | Unchecked | Không có provider cho scheme/file type cần mở |
| `AtomicMoveNotSupportedException` | Checked, subclass `IOException` | Yêu cầu atomic move không thực hiện được |
| `ReadOnlyFileSystemException` | Unchecked | Thực hiện write trên filesystem read-only |
| `UnsupportedOperationException` | Unchecked | Provider không hỗ trợ operation/option |
| `NoSuchFileException` | Checked, subclass `IOException` | File/entry không tìm thấy theo operation |
| `FileAlreadyExistsException` | Checked, subclass `IOException` | Tạo target đã tồn tại |
| `FileSystemException`/`IOException` | Checked | ZIP hỏng, permission, I/O, invalid filesystem state hoặc provider-specific failure |
| `InvalidPathException` | Unchecked, `IllegalArgumentException` | Chuỗi path không hợp lệ theo provider |

**Không bắt `RuntimeException` rồi chuyển hết thành `IOException`**. `ProviderMismatchException` chỉ ra lỗi xây API/path; `ClosedFileSystemException` chỉ ra lỗi lifecycle. Nếu wrap để chuẩn hóa boundary, giữ **cause** và log rõ ngữ cảnh, không che root cause thành “file không tồn tại”.

### 10.1. Ví dụ runnable: taxonomy bằng các exception giả lập

Tạo `ZipExceptionTaxonomyDemo.java`:

```java
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.ClosedFileSystemException;
import java.nio.file.FileSystemAlreadyExistsException;
import java.nio.file.FileSystemNotFoundException;
import java.nio.file.ProviderMismatchException;
import java.nio.file.ProviderNotFoundException;

public class ZipExceptionTaxonomyDemo {
    static String category(Throwable failure) {
        if (failure instanceof ProviderMismatchException) {
            return "PROVIDER_MISMATCH";
        }
        if (failure instanceof ClosedFileSystemException) {
            return "CLOSED_FILE_SYSTEM";
        }
        if (failure instanceof FileSystemNotFoundException) {
            return "NOT_MOUNTED";
        }
        if (failure instanceof FileSystemAlreadyExistsException) {
            return "ALREADY_MOUNTED";
        }
        if (failure instanceof ProviderNotFoundException) {
            return "PROVIDER_MISSING";
        }
        if (failure instanceof AtomicMoveNotSupportedException) {
            return "NO_ATOMIC_MOVE";
        }
        if (failure instanceof IOException) {
            return "IO_FAILURE";
        }
        return "OTHER_FAILURE";
    }

    public static void main(String[] args) {
        System.out.println(
                "mismatch="
                + category(new ProviderMismatchException()));
        System.out.println(
                "closed="
                + category(new ClosedFileSystemException()));
        System.out.println(
                "notfound="
                + category(new FileSystemNotFoundException()));
        System.out.println(
                "already="
                + category(new FileSystemAlreadyExistsException()));
        System.out.println(
                "provider="
                + category(new ProviderNotFoundException()));
        System.out.println(
                "atomic="
                + category(new AtomicMoveNotSupportedException(
                    "from", "to", "different file systems")));
        System.out.println(
                "io=" + category(new IOException("ZIP error")));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ZipExceptionTaxonomyDemo.java
java ZipExceptionTaxonomyDemo
```

```text
mismatch=PROVIDER_MISMATCH
closed=CLOSED_FILE_SYSTEM
notfound=NOT_MOUNTED
already=ALREADY_MOUNTED
provider=PROVIDER_MISSING
atomic=NO_ATOMIC_MOVE
io=IO_FAILURE
```

Đây là **unit test taxonomy**, không thao tác filesystem. Giá trị của nó là tránh policy lỗi: không retry provider mismatch như lỗi mạng, không dùng lại Path sau khi FS đóng và không coi thiếu provider là archive “rỗng”.

## 11. Những lỗi thiết kế thường gặp

### 11.1. Trộn Path từ utility viết cho default filesystem

Một utility nhận `Path directory` nhưng bên trong luôn làm:

```java
Path child = directory.resolve(Path.of("settings.json"));
```

Đây là snippet dễ lỗi. Khi `directory` thuộc ZIPFS, `Path.of("settings.json")` do default provider tạo ra. **Sửa:** `directory.resolve("settings.json")` hoặc `directory.resolve(directory.getFileSystem().getPath("settings.json"))`.

### 11.2. Dùng Path.getFileName() rồi đưa thẳng vào Path của provider khác

```java
Path sourceName = zipEntry.getFileName();
Path output = localDir.resolve(sourceName);
```

Với `zipEntry` ZIPFS và `localDir` default FS, phép resolve(Path) có thể mismatch. Nếu chủ ý đặt output theo file name, validate tên rồi dùng `localDir.resolve(sourceName.toString())`; cách này tạo child thuộc **provider của localDir**.

**Không dùng cách này để chuyển toàn bộ đường dẫn cây ZIP một cách mù quáng**. Với nested entries, phải kiểm tra tên, root, `..` và symlinks; phần bảo mật bên dưới.

### 11.3. Coi mọi provider có cùng tên path semantics

`Path.of("config/app.yml")` dùng cú pháp của default OS; `zipFs.getPath("/config/app.yml")` dùng syntax của ZIPFS. Một path với dấu `\` trên Windows và một path trong ZIP không có semantics giống nhau hoàn toàn.

Không giả định `Path.toString` là định dạng lưu trữ canonical cho mọi provider. Khi có URI tương thích, dùng provider URI contract; khi cần di chuyển bytes giữa providers, dùng `Files.copy` hoặc streaming I/O.

### 11.4. Close filesystem trong helper rồi trả Path

`getEntry(Path archive)` mở ZIPFS, trả `Path` rồi close. Caller gọi `Files.readString` sau đó nhận `ClosedFileSystemException`. **Sửa:** trả content/DTO độc lập hoặc trao ownership rõ ràng cho caller.

### 11.5. Đóng filesystem dùng chung quá sớm

Một request đóng shared ZIPFS mà các request khác đang dùng. **Sửa:** tập trung lifecycle vào một owner, quản lý số lượt sử dụng, shutdown và việc xử lý ZIP version theo transaction/lease. Không chỉ catch exception và hy vọng thử lại sẽ hết lỗi.

### 11.6. Dùng exists(Path) để kiểm tra FileSystem có mở

`Files.exists(path)` là một phương thức boolean có thể trả `false` khi không xác định được trạng thái tệp; không phải một phép chẩn đoán exception đầy đủ. Để xác định lifecycle, kiểm tra `path.getFileSystem().isOpen()` kết hợp thao tác thực và lỗi được báo. **Vẫn không** dùng `isOpen()` làm synchronization chống concurrent close.

### 11.7. Mở cùng ZIP URI hai lần rồi catch sai

`FileSystemAlreadyExistsException` nghĩa cùng URI đã có instance theo provider — không có nghĩa ZIP file bị hỏng. Có thể lookup một filesystem đang mở nếu **quyền sở hữu và chính sách ứng dụng cho phép**, nhưng **không được close một instance do component khác sở hữu**.

### 11.8. Suy rằng Files.copy có thể xử lý mọi thứ nguyên tử

Copy chéo provider có thể hoạt động nhưng **không atomic** và không giữ toàn bộ metadata. Nếu source/destination nằm ở hai providers, hãy thiết kế staging, checksum/validation, conflict handling và cleanup, không chỉ catch IOException và tin archive nguyên vẹn.

## 12. Kiến trúc service xử lý ZIP: quản lý session thay vì cache Path vĩnh viễn

Một API đơn giản, rõ ownership:

```java
public static String readArchiveEntry(
        Path archive, String entryName) throws IOException {
    try (FileSystem fs =
            FileSystems.newFileSystem(archive, Map.of())) {
        Path entry = fs.getPath(entryName);
        return Files.readString(entry);
    }
}
```

Đây là method minh họa, cần imports `Path`, `IOException`, `FileSystem`, `FileSystems`, `Files`, `Map`. **Với đầu vào không đáng tin**, phải validate `entryName`, giới hạn nội dung, chỉ đọc entry cho phép và kiểm soát resource. Method trả **String** độc lập thay vì Path của một filesystem đã đóng.

Với ZIP có nhiều entry, mở/đóng filesystem cho từng entry thường không hiệu quả. Có thể mở **một lần** trong một scope và xử lý hết entries trước khi close. Nếu nhiều threads cần dùng cùng archive, tạo một session/service có owner và lifetime rõ thay vì tự gọi `newFileSystem` trong từng method hoặc share một biến không đồng bộ.

### 12.1. Quyền sở hữu rõ ràng: caller hay callee?

Hai kiểu API:

**Service owns ZIPFS:** service nhận pathname ZIP, mở và close trong một method hoặc một transaction; caller chỉ nhận dữ liệu đã materialize.

**Caller owns ZIPFS:** caller mở `FileSystem`, truyền `Path`/`FileSystem` cho helper, đảm bảo helpers không close resource. Caller close ở cuối tất cả operations. Type contracts cần nêu rõ resource còn mở khi gọi.

**Đừng trộn hai kiểu trong cùng helper**: nếu helper tự close một filesystem do caller quản lý, sẽ gây lỗi ClosedFileSystemException ở caller.

### 12.2. Một FileSystem sống cùng nhiều workers

Nếu workflow async cần đọc ZIP ở workers khác nhau:

```text
ZIP session owner
  ├── acquire lease -> worker A
  ├── acquire lease -> worker B
  ├── release A
  ├── release B
  └── close ZIP filesystem khi không còn lease và không nhận job mới
```

Đây là thiết kế logic; Java NIO.2 **không tự cung cấp** hệ thống lease/ref-count. Bạn phải implement theo concurrency model. `FileSystem.isOpen()` kiểm tra trước một thao tác chưa đủ tránh race đóng resource giữa chừng.

Nếu chỉ cần một task đơn lẻ, giải pháp đơn giản nhất vẫn là TWR. Đừng dựng bộ quản lý phiên phức tạp nếu không có nhu cầu thực.

## 13. Test trên nhiều providers: unit, integration và lifecycle

**Unit tests cần kiểm tra:**

- Dùng `Path` từ hai providers trong `Path.resolve(Path)` thì nhận lỗi phù hợp trên JDK ZIPFS.
- `resolve(String)` hoặc `getFileSystem().getPath(...)` tạo thành phần đúng provider.
- `ProviderMismatchException` khác `ClosedFileSystemException` cả nguyên nhân và superclass.
- Các phép predicate như `startsWith` không nhất thiết phải ném khi khác provider.
- Classifier giữ đúng taxonomy và không biến mọi error thành một mã chung.

**Integration tests cần kiểm tra:**

- ZIPFS provider hiện diện trong runtime dự kiến.
- Tạo ZIP tạm (tên chưa tồn tại), ghi nội dung, đóng, mở lại và đọc chính xác bytes.
- `Files.copy` từ default FS vào ZIP và từ ZIP ra default FS.
- `Files.move` với `ATOMIC_MOVE` khi source/target khác providers: xử lý failure theo contract, không assert luôn thành công.
- Cùng URI đang mount: ứng dụng phát hiện already exists theo cơ chế mở.
- `FileSystems.getFileSystem(jarUri)` khi chưa mount: not found.
- `Files.readString` trên Path ZIP đã đóng: closed FS error.
- Đường dẫn bên trong ZIP từ filesystem cũ không tự trở nên hợp lệ sau reopen.
- `Files.walk`, `Files.list` trên ZIPFS: đóng Stream trước ZIPFS.
- Hai ZIP archives khác nhau: không trộn các Path chỉ vì cùng scheme `jar`.

**Failure tests và vận hành:**

- ZIP bị corrupt/truncated: mở có thể ném `IOException`; không gộp lỗi với provider mismatch.
- Filesystem read-only/ACL: ghi có thể ném `ReadOnlyFileSystemException`/`IOException`.
- Thiếu module `jdk.zipfs` trong custom JRE: lỗi provider unavailable.
- Archive được thay đổi bên ngoài khi session đang mở: policy reload/reopen rõ.
- Close hoặc flush failure: không báo kết quả đã commit nếu chưa xác minh.
- ZIP có rất nhiều entries hoặc kích thước giải nén lớn: giới hạn tài nguyên.
- Dữ liệu entry có tên chứa `..`, absolute path, separators khác hệ thống: chống Zip Slip nếu extract.
- Hai workers cùng reopen/mount shared URI: quản lý ownership và conflict.
- Default FS nhiều volume/file stores: phân biệt **khác file store** với **khác provider**.

### 13.1. Khác provider không đồng nghĩa khác FileStore

**Provider** quyết định implementation/Path semantics; **FileStore** đại diện storage/volume do filesystem cung cấp. Hai `Path` trên hai ổ đĩa vật lý khác nhau có thể đều thuộc default provider `file`, nên không nhất thiết ném `ProviderMismatchException` khi `resolve(Path)` — nhưng việc move atomic có thể không khả dụng giữa hai file stores.

Ngược lại, ZIPFS và default FS có providers khác nhau ngay cả khi file ZIP được lưu **trên cùng một ổ đĩa vật lý**. Đây là sự khác biệt ở tầng abstraction, không phải chỉ khoảng cách vật lý.

### 13.2. Provider mismatch không phải vấn đề encoding của ZIP

Chữ tiếng Việt hay tên file Unicode trong ZIP không tự tạo `ProviderMismatchException`. Nếu gặp lỗi encoding/entry name của một archive cụ thể, đó là vấn đề khác: chính sách charset của ZIP provider, entry metadata, input format hoặc dữ liệu hỏng. Không sửa `ProviderMismatchException` bằng cách đổi UTF-8 hay format tên nếu nguyên nhân thật là truyền một `Path` từ provider sai.

## 14. Bảo mật và dữ liệu ZIP không đáng tin

Một ZIP có thể chứa entries được dùng để **đọc hoặc giải nén**. Dù đã sửa đúng provider và giữ filesystem mở, vẫn cần kiểm soát dữ liệu:

- **Zip Slip/path traversal:** entry name chứa `..` hoặc absolute path có thể dẫn ra ngoài thư mục extraction nếu ghép tùy tiện.
- **Symbolic links/junctions:** kiểm tra lexical `normalize().startsWith(root)` chỉ là một lớp, không loại bỏ mọi vấn đề nếu các directory cha là links hoặc bị thay đồng thời.
- **Resource exhaustion:** ZIP bombs, file nén nhỏ nhưng giải nén rất lớn, hàng triệu entries, zip64 hoặc nhiều lồng tầng.
- **Data validation:** xác nhận checksum, định dạng file, content type, schema, size và tính toàn vẹn theo nhu cầu.
- **Quyền filesystem:** chỉ ghi vào thư mục do service kiểm soát và với quyền tối thiểu.
- **Overwrite:** dùng unique destination hoặc policy collision, không cho user đưa tên đích tùy ý đè file quan trọng.
- **Lộ dữ liệu:** log exception có thể chứa đường dẫn ZIP/local path; kiểm soát nội dung log.

Một kiểm tra đường dẫn theo cú pháp:

```java
Path root = trustedDestination.toAbsolutePath().normalize();
Path candidate = root.resolve(entryName).normalize();
if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException(
            "Archive entry escapes destination");
}
```

Đây là **snippet minh họa guard lexical**, **không phải sandbox hoàn chỉnh**. `entryName` đến từ nguồn không tin cậy cần được kiểm tra đúng dạng và các thao tác filesystem phải có cơ chế chống symlink/TOCTOU, quotas và chính sách overwrite riêng.

**Provider mismatch và closed FS là lỗi kỹ thuật**, còn boundary security của archive là một bài toán độc lập. Đừng coi code không ném hai exception này là bằng chứng xử lý ZIP an toàn.

## 15. Những lỗi phổ biến và hướng sửa

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `zipDir.resolve(Path.of("a.txt"))` ném ProviderMismatch | Path child thuộc default FS | Dùng `zipDir.resolve("a.txt")` |
| `zipPath.relativize(localPath)` lỗi | Hai Path khác provider/filesystem | Chỉ relativize paths tương thích; đừng chuyển bằng string mù quáng |
| `zipPath.compareTo(localPath)` lỗi | Ordering giữa providers không được định nghĩa phù hợp | Sort theo domain key/strings nếu chính sách hợp lý, không so Path trộn |
| `zipPath.startsWith(localPath)` trả false | Hai paths không cùng provider | Kiểm tra provider và boundary riêng |
| `Files.copy(zipPath, localPath)` thành công | API copy hỗ trợ providers khác nhau | Đây là hành vi hợp lệ, vẫn xử lý partial copy |
| `Files.move(..., ATOMIC_MOVE)` thất bại | Khác provider/file store, không atomic | Dùng staging/publish policy hoặc fail rõ |
| `Files.readString(inner)` sau try ném Closed FS | ZIPFS đã close nhưng caller giữ Path | Đọc trong scope hoặc reopen và lấy Path mới |
| `inner.toString()` vẫn chạy sau close | Phép xử lý lexical không cần I/O | Không dùng để kết luận FS còn sống |
| `FileSystems.getFileSystem(jarUri)` ném NotFound | Chưa mount hoặc không còn registered | Tạo/mount theo ownership policy |
| `newFileSystem(jarUri,...)` ném AlreadyExists | URI đang có mount active | Reuse có kiểm soát hoặc tránh mount trùng |
| `newFileSystem(...)` ném ProviderNotFound | Thiếu provider/module | Bổ sung ZIPFS runtime hoặc chọn xử lý ZIP khác |
| ZIP được ghi nhưng archive rỗng/hỏng sau crash | Close/flush thất bại, write giữa chừng | Không báo commit trước close; dùng staging, verify |
| FileSystem.close bị gọi trong worker | Sai ownership shared resource | Owner đóng sau khi workers kết thúc |
| ZIPFS Path cache vẫn dùng sau reopen | Path thuộc instance cũ | Recreate Path từ filesystem mới |
| Default FS `close()` lỗi | Không phải resource để đóng theo kiểu ZIPFS | Không TWR trên FileSystems.getDefault() |
| `Path.of(zipEntry.toString())` đọc file local sai | Chuyển pathname giữa providers bằng string | Dùng original ZIP Path cho I/O, `Files.copy` để chuyển data |
| Tên ZIP có `../` gây output ngoài root | Zip Slip | Validate entry names, root, symlinks, quotas |
| `FileSystems.newFileSystem` mở archive đã tồn tại nhưng env create sai | Factory/provider options không phù hợp | Phân biệt tạo ZIP mới và mở ZIP hiện có |
| Test trên JDK đầy đủ PASS nhưng custom runtime FAIL | Module `jdk.zipfs` vắng | Test module/provider ở runtime deploy |

## 16. Checklist code review

1. Mỗi `Path` đang thuộc `FileSystem` nào? Provider scheme là gì?
2. Có trộn `Path.of(...)` của default provider vào `resolve(Path)` trên ZIP Path không?
3. Nếu chỉ cần tên child, đã dùng `resolve(String)`/`getFileSystem().getPath` chưa?
4. Nếu làm việc với hai `Path` trong một operation, contract có cho cross-provider không?
5. Có hiểu `Files.copy` khác `Path.resolve(Path)` về cross-provider support không?
6. Có phân biệt **cùng provider** và **cùng FileSystem instance** không?
7. Có dùng `Path.toString` để convert file identity giữa providers sai cách không?
8. Có xác định component nào sở hữu `FileSystem` và trách nhiệm close không?
9. Có TWR cho ZIPFS riêng, nhưng không đóng default FileSystem không?
10. Có đóng `Files.walk/list` stream trước khi đóng ZIPFS không?
11. Có trả `Path`/`Stream<Path>` gắn ZIPFS sau khi ZIPFS đã đóng không?
12. Có khả năng thread khác đóng ZIPFS trong lúc I/O đang chạy không?
13. Có hiểu `isOpen()` là quan sát không atomic với close không?
14. Nếu reopen ZIP, có lấy Path mới chứ không dùng Path retained không?
15. Có phân biệt `ProviderMismatchException` với `ClosedFileSystemException` theo superclass và nguyên nhân không?
16. Có phân biệt `FileSystemNotFoundException`, `FileSystemAlreadyExistsException` và `ProviderNotFoundException` không?
17. Với `FileSystems.getFileSystem(jarUri)`, URI đã được mount trong runtime/provider chưa?
18. Có xử lý thiếu `jdk.zipfs` ở custom JRE/`jlink` runtime không?
19. Với `Files.move` chéo provider, có tránh kỳ vọng atomic không?
20. Với `Files.copy`, có xử lý partial destination và metadata loss không?
21. Có đợi close/flush thành công trước khi tuyên bố archive được commit không?
22. Có tạo ZIP mới ở đường dẫn **chưa tồn tại** khi dùng create env không?
23. Có tránh test chạm archive thật hoặc source project khi chỉ cần demo không?
24. Có kiểm tra ZIP input không đáng tin: path traversal, symlink, zip bomb, quotas không?
25. Có hạn chế logs chứa full paths/metadata nhạy cảm không?
26. Có test nhiều providers/file stores/runtime modes thay vì chỉ local default FS không?
27. Có không biến mọi runtime exception thành `IOException` chung không?
28. Có test error conditions thực sự, không chỉ so `Path.toString` sau close không?
29. Có check case-sensitivity và path separator semantics của từng filesystem không?
30. Có tài liệu hóa API's lifetime contract cho caller và các background workers không?

## 17. Bài tập thực hành

**Bài 1 — Provider identity.** Chạy `ZipProviderIdentityDemo`. Viết code in `getFileSystem()`/`provider()` và lý giải vì sao `file` và `jar` là hai nguồn `Path` khác nhau.

**Bài 2 — Mismatch.** Chạy `ZipPathMismatchDemo`. Thử thêm `zipPath.startsWith(defaultChild)` rồi quan sát behavior. Vì sao một method có thể trả false thay vì ném?

**Bài 3 — Sửa Path.** Viết `safeChild(Path parent, String name)` dựa trên `parent.resolve(name)`. Bổ sung validation để không nhận absolute name hoặc `..` khi root do server quản lý.

**Bài 4 — Copy khác provider.** Chạy `ZipCrossProviderCopyDemo`. So sánh `Files.copy` với `zipPath.resolve(defaultPath)`. Vì sao copy hợp lệ nhưng resolve mismatch?

**Bài 5 — Reopen.** Chạy `ClosedZipFileSystemDemo`. Giữ `Path retained` sau close, thử `getFileName()` rồi thử `Files.readString`. Giải thích sự khác nhau giữa phép xử lý lexical và I/O.

**Bài 6 — URI mount.** Chạy `ZipUriMountDemo`. Dự đoán kết quả `getFileSystem(jarUri)` trước/sau mount và `newFileSystem(jarUri)` khi URI đang active.

**Bài 7 — Ownership.** Chạy `ZipScopedListingDemo`. Thử sửa method `listFiles` để trả `Stream<Path>` sau TWR và giải thích vì sao thiết kế đó không đúng; thiết kế lại bằng callback hoặc DTO.

**Bài 8 — Exception taxonomy.** Chạy `ZipExceptionTaxonomyDemo`. Tại sao không nên retry `ProviderMismatchException` mà không sửa source/path construction? Khi nào `ProviderNotFoundException` chỉ ra lỗi cấu hình runtime?

**Bài 9 — FileSystem khác nhau cùng provider.** Tạo hai ZIP archives cùng được mở và so sánh `getFileSystem()`, scheme, Path names. Vì sao cùng `jar` không chứng minh hai paths có thể phối hợp?

**Bài 10 — Cross-provider move.** Thử `Files.move(local, zipEntry, ATOMIC_MOVE)` trong sandbox. Xử lý `AtomicMoveNotSupportedException` và thiết kế fallback có staging/checksum/commit rõ.

**Bài 11 — ZIP corrupt.** Tạo một tệp rỗng `bad.zip` rồi thử mở `newFileSystem(badZip, Map.of())`. Phân biệt `IOException` do ZIP hỏng với `ProviderNotFoundException`/`ClosedFileSystemException`.

**Bài 12 — Runtime.** Dùng một JDK đầy đủ và một custom runtime phù hợp để kiểm tra module `jdk.zipfs`. Trình bày cách báo lỗi cấu hình nếu feature ZIPFS là bắt buộc.

**Bài 13 — Multi-thread.** Thiết kế manager có lease/ref count để một worker không close filesystem đang được worker khác dùng. Giải thích vì sao chỉ check `isOpen()` là chưa đủ.

**Bài 14 — Cross-archive.** So sánh path `/docs/readme.md` trong hai ZIP khác nhau. Định nghĩa logical document ID đủ phân biệt archive identity và entry name.

**Bài 15 — Security.** Tạo ZIP chứa tên entry `../../escape.txt` trong môi trường thử nghiệm hợp lệ, thiết kế extraction kiểm soát root. Nêu hạn chế lexical checks khi directory đích chứa symlink.

## 18. Kết luận

- `Path` gắn với **một `FileSystem`**, không chỉ là chuỗi. `FileSystem` gắn với một **provider**; default filesystem và ZIPFS thường khác providers `file` và `jar`.
- **`ProviderMismatchException`** là unchecked `IllegalArgumentException`, xuất hiện khi API không hỗ trợ phối hợp đối tượng khác provider. Dùng `resolve(String)`/`fs.getPath` để tạo child từ đúng filesystem.
- **`ClosedFileSystemException`** là unchecked `IllegalStateException`, xuất hiện khi thao tác I/O qua filesystem đã đóng. Reopen ZIPFS và tạo **Path mới**, không tái dùng Path giữ từ instance cũ.
- **Không đồng nhất mọi thao tác hai Path:** `Files.copy` có thể hoạt động giữa provider khác nhau, trong khi `Path.resolve(Path)` không tương thích. `Files.move` chéo provider không bảo đảm atomic.
- **ZIPFS phải có lifecycle rõ:** TWR, ownership, đóng stream trước filesystem, không trả Path/Stream phụ thuộc filesystem ra ngoài scope đã đóng.
- **`FileSystemNotFoundException`, `FileSystemAlreadyExistsException` và `ProviderNotFoundException`** phản ánh cơ chế mount/provider khác với hai lỗi trọng tâm.
- **Default FileSystem không được đóng như ZIPFS**, còn `isOpen()` không tự giải quyết race đồng thời.
- **Test trên ZIP provider thật**, đọc lại dữ liệu sau close/reopen, và kiểm tra runtime có `jdk.zipfs` khi chức năng yêu cầu.
- **Bảo mật ZIP** cần chống traversal, symlinks, unbounded decompression và partial copy; sửa provider mismatch không tự giải quyết những vấn đề này.
- Toàn bộ hướng dẫn dùng **Java 17+ và NIO.2 vẫn còn hiệu lực**, không dựa vào cách làm legacy.

## Tài liệu chính thức

- [ProviderMismatchException — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ProviderMismatchException.html): định nghĩa, quan hệ kế thừa.
- [ClosedFileSystemException — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedFileSystemException.html): thao tác trên filesystem đã đóng.
- [FileSystem — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html): ownership, isOpen, close và paths.
- [FileSystems — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystems.html): newFileSystem, getFileSystem, providers và URI.
- [Path — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): resolve, relativize, startsWith và mối liên hệ filesystem.
- [Files — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): copy/move giữa providers, readString, walk/list và lỗi I/O.
- [FileSystemProvider — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): provider contract, scheme và khác biệt implementations.
- [JDK ZIP File System Provider](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): tham khảo công cụ JAR/ZIP; khi cần cấu hình ZIPFS, xem tài liệu module `jdk.zipfs` của bản phân phối JDK đang chạy.
