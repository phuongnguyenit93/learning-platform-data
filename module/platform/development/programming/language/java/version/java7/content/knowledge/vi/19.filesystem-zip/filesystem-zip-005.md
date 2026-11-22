# FileSystem và ZIP trong Java: Tạo, đọc và cập nhật mục trong kho ZIP

## 1. Mục tiêu của bài học

Một ứng dụng Java có thể cần tạo tệp `report.zip`, đưa vào đó các tài liệu và ảnh, mở lại để đọc nội dung, cập nhật một tệp cấu hình, đổi tên hoặc xóa một mục đã cũ. Nếu dùng `java.util.zip.ZipOutputStream`, ứng dụng xử lý các entry theo luồng; khi muốn sửa những entry bất kỳ trong một archive, cách tiếp cận đó đòi hỏi tự tổ chức việc ghi lại kho ZIP.

Từ Java 7, NIO.2 đưa ra một cách khác: xem một **tệp ZIP như một hệ thống tệp (`FileSystem`)** thông qua nhà cung cấp ZIP file system (`ZipFS`). Trong JDK hiện nay, module `jdk.zipfs` cung cấp triển khai này. Khi mount kho ZIP thành một `FileSystem`, ta có thể dùng chính các API hiện hành:

- `FileSystems.newFileSystem(...)`: mở hoặc tạo ZIP filesystem.
- `FileSystem.getPath(...)`: lấy đường dẫn **bên trong** kho.
- `Files.createDirectories(...)`: tạo đường dẫn thư mục bên trong kho.
- `Files.writeString(...)`, `Files.write(...)`: thêm mới hoặc cập nhật entry.
- `Files.readString(...)`, `Files.newInputStream(...)`: đọc entry.
- `Files.list(...)`, `Files.walk(...)`: liệt kê nội dung kho.
- `Files.copy(...)`: chuyển dữ liệu từ file thông thường vào ZIP và ngược lại.
- `Files.move(...)`: đổi tên hoặc di chuyển entry bên trong ZIP.
- `Files.delete(...)`: xóa entry.
- `FileSystem.close()`: giải phóng ZIP filesystem và hoàn tất quy trình ghi theo provider.

**Đây là kỹ thuật còn sử dụng được trên Java 17+**, không phải API bị loại bỏ hay cần thay bằng thư viện bên thứ ba cho mọi trường hợp. Nhưng có những giới hạn quan trọng: `Path` bên trong ZIP khác `Path` của host, một lần cập nhật archive **không mặc nhiên atomic**, đóng `FileSystem` là bước thiết yếu, và **một ZIP không tin cậy không được giải nén tùy ý** ra filesystem thật.

Trong bài này, ví dụ Java độc lập sẽ tự tạo workspace tạm, tạo archive, thêm file văn bản và nhị phân, cập nhật, đổi tên, xóa entry, copy dữ liệu hai chiều, mở lại ZIP và kiểm chứng bằng `java.util.zip.ZipFile`. Chương trình đã được biên dịch/chạy bằng `javac` và `java` trên JDK 17+.

## 2. Hiểu ba lớp đường dẫn: tệp ZIP ngoài, FileSystem ZIP, mục trong ZIP

Một kho ZIP là một tệp trên filesystem của máy nhưng đồng thời chứa **cấu trúc các entry**. Cần tách ba đối tượng:

```text
Filesystem thông thường (file:)
└── /workspace/lesson.zip     ← Path ngoài, chứa toàn bộ archive
              |
              | FileSystems.newFileSystem("jar:file:...", env)
              v
       ZIP FileSystem (jar:)
       /
       ├── docs/
       │   ├── readme.txt     ← Path trong ZIP
       │   └── notes.txt
       └── assets/
           └── payload.bin    ← Path trong ZIP
```

- **`archivePath`**: đường dẫn tệp `lesson.zip` bên ngoài, do filesystem thông thường quản lý.
- **`zipFs`**: đối tượng `FileSystem` đại diện **nội dung** tệp ZIP đã mở.
- **`zipFs.getPath("/docs/readme.txt")`**: đường dẫn entry **trong ZIP**; không phải tệp `/docs/readme.txt` trên máy.

Mã minh họa:

```java
Path archivePath = Path.of("lesson.zip").toAbsolutePath();
URI uri = URI.create("jar:" + archivePath.toUri());

try (FileSystem zipFs =
        FileSystems.newFileSystem(uri, Map.of("create", "true"))) {

    Path internalFile = zipFs.getPath("/docs/readme.txt");
    // internalFile thuộc ZIP filesystem, không thuộc host filesystem.
}
```

Đây là **mã minh họa trong phương thức** có `throws IOException`; cần import `java.net.URI`, `java.nio.file.*` và `java.util.Map`.

### 2.1. Vì sao URI bắt đầu bằng `jar:` khi file có đuôi `.zip`?

Module `jdk.zipfs` định nghĩa URI scheme `jar` cho ZIP filesystem. `jar` là **tên scheme của provider**, không có nghĩa tệp nhất thiết phải là JAR chứa class. ZipFS có thể làm việc với archive ZIP hoặc JAR theo những giới hạn của provider.

Một URI điển hình:

```text
jar:file:///workspace/lesson.zip
```

Đường dẫn host có thể chứa dấu cách hoặc ký tự Unicode. Dùng `archivePath.toUri()` để tạo file URI hợp lệ thay vì tự ghép `"jar:file:" + archivePath.toString()`, vốn có thể gây lỗi separator và escaping giữa Windows/Linux.

### 2.2. Không dùng `Path.of("/docs/readme.txt")` để chỉ mục ZIP

`Path.of(...)` nhận provider của filesystem mặc định, còn `zipFs.getPath(...)` trả path thuộc ZIP filesystem. Hai path có thể hiển thị giống nhau nhưng **thuộc hai providers khác nhau**.

```java
Path inHost = Path.of("/docs/readme.txt");
Path inZip  = zipFs.getPath("/docs/readme.txt");
```

Khi muốn đọc entry ZIP, dùng `Files.readString(inZip)`. Khi muốn đọc file trên máy, dùng `Files.readString(inHost)`. Không được nhầm hai đường dẫn này.

Một số thao tác trộn path khác provider có thể hoạt động có chủ đích (ví dụ `Files.copy(hostPath, zipPath)`); nhưng không phải mọi thao tác provider-specific chấp nhận path lẫn provider, và một số cách so sánh/`relativize` có thể ném `ProviderMismatchException`.

## 3. Tạo một kho ZIP mới bằng `FileSystems.newFileSystem`

### 3.1. Tạo file ZIP chưa tồn tại

Cách dùng chính thức của `jdk.zipfs` là mở `FileSystem` với URI và environment map:

```java
Path archive = Path.of("lesson.zip").toAbsolutePath();
URI jarUri = URI.create("jar:" + archive.toUri());

try (FileSystem zip = FileSystems.newFileSystem(
        jarUri,
        Map.of("create", "true"))) {

    // Tạo các entry bên trong zip.
}
```

`Map.of("create", "true")` là **property của ZIP provider**, có tác dụng yêu cầu tạo ZIP/JAR **nếu archive chưa tồn tại**. Đây không phải một tùy chọn phổ quát của mọi `FileSystemProvider`.

**Lưu ý:**

- Thư mục cha ngoài của `lesson.zip` phải tồn tại và ứng dụng có quyền ghi.
- `create=true` không có nghĩa xoá sạch archive đã tồn tại. Nếu mở archive có sẵn, phải hiểu rằng đang truy cập kho hiện có.
- `FileSystems.newFileSystem` có thể ném `IOException`, `ProviderNotFoundException`, `FileSystemAlreadyExistsException` hoặc lỗi khác tùy trường hợp.
- Nên dùng `try-with-resources` để **đóng ZIP filesystem**. Không để một ZIP filesystem đang mở suốt thời gian không cần thiết.
- Nếu ứng dụng yêu cầu **không bao giờ đụng archive cũ**, phải tổ chức tên archive mới độc nhất và xác minh quyền sở hữu, không chỉ dựa vào cờ `create`.

### 3.2. Khi ZIP provider không có sẵn

Trong JDK phân phối đầy đủ, `jdk.zipfs` thường có mặt. Với Java runtime tùy biến bằng `jlink` hoặc môi trường đã loại module, provider `jar` có thể vắng mặt.

Nếu provider không được cung cấp, `FileSystems.newFileSystem(jarUri, ...)` có thể ném `ProviderNotFoundException`. Kiểm tra runtime thực tế thay vì giả định mọi JRE tùy biến đều gồm ZIP provider.

Một bản phát hành ứng dụng có thể khai báo/đóng gói module cần thiết theo cấu hình build nếu thực sự dựa vào ZIP FileSystem.

## 4. Tạo thư mục và ghi entry văn bản

### 4.1. Path gốc bên trong ZIP

```java
Path root = zip.getPath("/");
Path docs = zip.getPath("/docs");
Path readme = zip.getPath("/docs/readme.txt");
```

Ở ZIP filesystem, `/` thể hiện root và phân cấp entry. Đây là **đường dẫn của provider ZIP**, không phải chỉ dẫn tạo thư mục `/docs` ngoài host.

### 4.2. Tạo thư mục

```java
Files.createDirectories(zip.getPath("/docs"));
Files.createDirectories(zip.getPath("/assets"));
```

`Files.createDirectories` tạo directory entries còn thiếu theo path. Nếu mục nào đã tồn tại dưới dạng tệp thường hoặc provider không cho tạo, thao tác có thể ném `IOException`.

Khi cập nhật mục sâu như `/reports/2026/november/summary.txt`, hãy tạo đường dẫn thư mục cha trước:

```java
Path entry = zip.getPath(
        "/reports/2026/november/summary.txt");

Files.createDirectories(entry.getParent());
```

Không suy rằng `Files.writeString(entry, ...)` luôn tự tạo mọi thư mục cha chưa có: API tạo file không thay cho `createDirectories`.

### 4.3. Thêm tệp văn bản mới

```java
Path entry = zip.getPath("/docs/readme.txt");

Files.writeString(
        entry,
        "Xin chào ZIP!\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Đây là minh họa; cần import `java.nio.charset.StandardCharsets` và `java.nio.file.StandardOpenOption`.

`CREATE_NEW` yêu cầu tạo một mục mới; nếu mục cùng tên đã tồn tại, thao tác thường ném `FileAlreadyExistsException` thay vì vô tình ghi đè. Đây là lựa chọn phù hợp khi nghiệp vụ muốn tránh mất dữ liệu cũ.

Với `Files.writeString(path, text, charset)` không đưa option, phương thức dùng các open options mặc định để tạo file khi thiếu, ghi và **truncate nội dung cũ** nếu file đã tồn tại. Vì vậy không nên bỏ qua options khi ý định là “chỉ được tạo mới”.

### 4.4. Ghi byte nhị phân

```java
Path binary = zip.getPath("/assets/image.bin");
Files.write(binary, new byte[]{1, 2, 3, 4});
```

Không đưa file ảnh/video/PDF qua `String` để lưu vào ZIP. Dữ liệu nhị phân cần được ghi bằng `byte[]`, stream hoặc `Files.copy`.

Với tệp lớn, dùng `Files.copy(hostFile, zipEntry)` hoặc stream để tránh `Files.readAllBytes` nạp toàn bộ file vào RAM.

## 5. Đọc entry từ ZIP

### 5.1. Đọc văn bản bằng `Files.readString`

```java
Path readme = zip.getPath("/docs/readme.txt");

String text = Files.readString(
        readme, StandardCharsets.UTF_8);
```

`Files.readString` có từ Java 11. Nó đọc **nội dung văn bản của một entry** bằng charset chỉ định, không phải cơ chế giải mã **tên entry** trong file ZIP (đó là lớp khác).

Chỉ đọc một entry **có kích thước phù hợp bộ nhớ** bằng `readString`. Với file lớn, ưu tiên `Files.newBufferedReader` hoặc `Files.newInputStream` trong `try-with-resources`.

### 5.2. Đọc nhị phân và stream

```java
Path payload = zip.getPath("/assets/payload.bin");

try (InputStream in = Files.newInputStream(payload)) {
    // Đọc theo từng khối và xử lý dữ liệu.
}
```

Đây là minh họa trong phương thức có `throws IOException`, cần import `java.io.InputStream`.

Nếu file nhỏ:

```java
byte[] data = Files.readAllBytes(payload);
```

Nhưng đừng dùng `readAllBytes` với archive do người khác cung cấp nếu chưa kiểm tra hạn mức giải nén hoặc độ dài logic: một ZIP có thể rất nhỏ ở dạng nén nhưng giải nén thành khối dữ liệu rất lớn.

### 5.3. Kiểm tra entry có tồn tại không

```java
boolean exists = Files.exists(
        zip.getPath("/docs/readme.txt"));

boolean regular = Files.isRegularFile(
        zip.getPath("/docs/readme.txt"));
```

Hai lời gọi trả trạng thái **tại thời điểm kiểm tra**, không bảo đảm entry vẫn còn đúng lúc đọc tiếp nếu có thành phần khác thay đổi archive. Với ứng dụng có concurrency, tổ chức ownership/serialization của ZIP filesystem và xử lý lỗi trực tiếp ở thao tác đọc.

### 5.4. Đọc archive đã tồn tại

Nếu ZIP đã tồn tại và bạn **chỉ mở**, dùng environment rỗng:

```java
Path archive = Path.of("lesson.zip").toAbsolutePath();
URI uri = URI.create("jar:" + archive.toUri());

try (FileSystem zip =
        FileSystems.newFileSystem(uri, Map.of())) {

    Path entry = zip.getPath("/docs/readme.txt");
    String text = Files.readString(
            entry, StandardCharsets.UTF_8);
    System.out.println(text);
}
```

Không có `create=true`, provider không được yêu cầu tự tạo archive thiếu. Nếu archive không tồn tại hoặc không phải ZIP hợp lệ, thao tác có thể lỗi thay vì trả về một ZIP trống.

**Phân biệt quyền:** môi trường không writable vẫn có thể cho đọc ZIP tùy provider, file permissions và filesystem. Không dùng `create=true` như một cờ read-only; nó chỉ điều khiển việc **tạo archive khi thiếu**.

## 6. Liệt kê và duyệt toàn bộ entry

### 6.1. Liệt kê mục trực tiếp bằng `Files.list`

```java
Path docs = zip.getPath("/docs");

try (Stream<Path> stream = Files.list(docs)) {
    stream
        .map(p -> p.getFileName().toString())
        .sorted()
        .forEach(System.out::println);
}
```

Cần import `java.util.stream.Stream`.

`Files.list` chỉ đọc **entry trực tiếp** trong directory, không tự đệ quy. `Stream<Path>` có thể giữ tài nguyên nên cần đóng bằng `try-with-resources`.

### 6.2. Duyệt tất cả bằng `Files.walk`

```java
Path root = zip.getPath("/");

try (Stream<Path> walk = Files.walk(root)) {
    walk.filter(Files::isRegularFile)
        .map(p -> root.relativize(p).toString())
        .sorted()
        .forEach(System.out::println);
}
```

Ví dụ với bài thực hành:

```text
assets/payload.bin
docs/readme.txt
```

`Files.walk` có thể duyệt các directory entries và files trong ZIP. `filter(Files::isRegularFile)` chỉ giữ tệp thường. `sorted()` được dùng để kết quả ổn định vì không nên giả định thứ tự liệt kê của provider.

**Không nhầm “đường dẫn tên trong ZIP” với đường dẫn ngoài máy.** Một entry tên `docs/readme.txt` vẫn là data nằm trong `lesson.zip`; `root.relativize(p)` chỉ trả một path tương đối **nội bộ ZIP**.

### 6.3. Glob/regex áp dụng trong ZIP filesystem

`PathMatcher` vẫn có ý nghĩa khi dùng với `Path` của ZIP:

```java
PathMatcher textNames =
        zip.getPathMatcher("glob:*.txt");

try (Stream<Path> walk = Files.walk(zip.getPath("/"))) {
    walk.filter(Files::isRegularFile)
        .filter(p -> textNames.matches(p.getFileName()))
        .forEach(System.out::println);
}
```

Đây là ví dụ chỉ lọc **tên cuối**. Nếu so `glob:*.txt` trực tiếp với đường dẫn nhiều thành phần `/docs/readme.txt`, kết quả có thể không như ý vì `*` không vượt separator. Muốn lọc toàn bộ path cần xác định pattern tương ứng và ngữ nghĩa ZIP provider.

## 7. Cập nhật nội dung của một entry đã có

### 7.1. Ghi đè nội dung bằng `TRUNCATE_EXISTING`

```java
Path readme = zip.getPath("/docs/readme.txt");

Files.writeString(
        readme,
        "Phiên bản mới\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
```

`TRUNCATE_EXISTING` yêu cầu làm rỗng nội dung cũ khi mở để ghi, sau đó ghi nội dung mới. Nếu muốn **chỉ cập nhật entry đã tồn tại**, không truyền `CREATE` hoặc `CREATE_NEW` trong thao tác này; khi entry không tồn tại, thao tác sẽ lỗi.

**Đừng nhầm cập nhật entry với append vào ZIP ngoài:** `Files.writeString` làm việc trên một `Path` bên trong ZIP filesystem; ZIP provider có trách nhiệm tổ chức lại dữ liệu archive. Nó không đơn giản nối byte mới vào cuối tệp `lesson.zip` theo format ZIP.

### 7.2. Thêm thay vì cập nhật

Khi muốn tránh ghi đè:

```java
Files.writeString(
        zip.getPath("/docs/new-note.txt"),
        "Tệp mới",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
```

Nếu entry đã tồn tại, thao tác sẽ báo lỗi và ứng dụng có thể phản hồi đúng cho người dùng. Tránh dùng `CREATE_NEW` khi mong muốn cập nhật trong place.

### 7.3. Chú ý cú pháp `CREATE`, `CREATE_NEW` và `TRUNCATE_EXISTING`

| Open option | Ý nghĩa thường dùng | Ứng dụng |
| --- | --- | --- |
| `CREATE_NEW` | Chỉ tạo khi entry chưa có | Không ghi đè file cũ |
| `CREATE` | Tạo nếu thiếu, không buộc mới | Upsert theo policy |
| `TRUNCATE_EXISTING` | Làm rỗng file hiện hữu khi mở để ghi | Thay hoàn toàn nội dung |
| `WRITE` | Mở cho phép ghi | Dùng với các option tạo/cập nhật |
| `APPEND` | Ghi thêm vào cuối khi provider hỗ trợ | Thêm dữ liệu có chủ đích |

Không giả định mọi tổ hợp open options đều hỗ trợ trên mọi filesystem provider. Với ZIP, pattern dễ hiểu cho “thay nội dung” là `WRITE + TRUNCATE_EXISTING`, còn “tạo mới không đụng cũ” là `CREATE_NEW + WRITE`.

### 7.4. Kiểm tra lại ngay khi ZIP còn mở

```java
String updated =
        Files.readString(readme, StandardCharsets.UTF_8);
```

Đọc lại entry xác nhận nội dung theo view của filesystem đang mở. Tuy nhiên kiểm tra sau **close rồi reopen** còn hữu ích hơn vì nó xác nhận archive đã tồn tại dưới định dạng ZIP đọc lại được sau khi kết thúc phiên làm việc.

## 8. Đổi tên, di chuyển, xóa và sao chép entry

### 8.1. Đổi tên entry trong cùng ZIP

```java
Path oldName = zip.getPath("/docs/notes.txt");
Path newName = zip.getPath("/docs/renamed.txt");

Files.move(oldName, newName);
```

`Files.move` là thao tác trên filesystem provider của path. Nếu target tồn tại, provider có thể từ chối để tránh ghi đè, trừ khi options/contract khác được yêu cầu và được hỗ trợ.

Đổi tên không phải bằng cách sửa `Path.toString()` hay sửa trực tiếp byte header của archive; dùng API `Files.move`.

### 8.2. Xóa entry

```java
Files.delete(zip.getPath("/docs/renamed.txt"));
```

`Files.delete` ném lỗi nếu entry không tồn tại hoặc không xóa được. `Files.deleteIfExists` trả boolean nếu entry thiếu. Cần chọn rõ policy “xóa phải thành công” hay “xóa nếu có”.

**Xóa directory không rỗng** thường không hợp lệ với `Files.delete`; nếu nghiệp vụ thật sự cần xóa một cây directory bên trong ZIP, phải duyệt con trước rồi xóa parent sau (ví dụ `Files.walkFileTree` với `postVisitDirectory`). Không chuyển routine xóa đệ quy từ bài thực hành sang path của người dùng mà chưa xác minh ownership.

### 8.3. Copy từ host vào ZIP

```java
Path hostFile = Path.of("assets", "logo.png");
Path zipFile = zip.getPath("/assets/logo.png");

Files.copy(hostFile, zipFile);
```

Điều kiện: file nguồn tồn tại, directory `/assets` đã có, destination entry chưa tồn tại nếu không chọn ghi đè.

Đây là một trường hợp **`Files.copy` hỗ trợ source và target từ providers khác nhau**. API tự điều phối việc đọc/ghi; không cần gọi `Files.readAllBytes(hostFile)` cho file lớn.

### 8.4. Copy từ ZIP ra host

```java
Path zipFile = zip.getPath("/assets/logo.png");
Path destination = Path.of("exported-logo.png");

Files.copy(zipFile, destination);
```

**Cảnh báo:** Khi destination được xây từ tên một entry **không tin cậy**, bắt buộc kiểm tra path traversal và symlink policy trước khi tạo file ngoài host. Đây là nguồn rủi ro **Zip Slip** trong các tiện ích giải nén sai cách.

Với ứng dụng đọc archive chưa biết nguồn gốc, không được dùng `dest.resolve(entryName)` một cách mù quáng.

### 8.5. `REPLACE_EXISTING` là lựa chọn phá hủy dữ liệu

```java
Files.copy(
        hostFile,
        zipFile,
        StandardCopyOption.REPLACE_EXISTING);
```

Tùy chọn trên cho phép thay entry đích hiện có, khi provider hỗ trợ. Chỉ dùng khi đó là yêu cầu nghiệp vụ được phép và đã có xử lý khôi phục khi lỗi; đừng đưa `REPLACE_EXISTING` vào mọi thao tác copy theo thói quen.

**Tương tự, không mặc định việc move entry ZIP là atomic.** `Files.move(..., ATOMIC_MOVE)` có thể ném `AtomicMoveNotSupportedException` theo provider và điều kiện lưu trữ.

## 9. `close()`, commit và khả năng đọc lại kho ZIP

### 9.1. Vì sao `try-with-resources` là một phần bắt buộc của ví dụ?

`FileSystem` tạo bởi `newFileSystem` là tài nguyên cần đóng:

```java
try (FileSystem zip =
        FileSystems.newFileSystem(uri, Map.of("create", "true"))) {
    // Thêm, sửa và xóa entries.
}
// ZIP filesystem đã được đóng ở đây.
```

Với ZIP provider, các thay đổi được nhà cung cấp quản lý và archive có thể được **cập nhật/ghi lại khi đóng ZIP filesystem**. Vì vậy, để xác nhận kết quả lưu bền trong file ZIP bên ngoài, hãy:

1. Đóng tất cả luồng đọc/ghi entry đang mở.
2. Đóng `FileSystem` bằng `try-with-resources`.
3. Mở lại archive bằng `FileSystems.newFileSystem(uri, Map.of())` hoặc `ZipFile`.
4. Đọc và kiểm tra nội dung cần xác minh.

Đừng giữ `Path` thuộc ZIP filesystem rồi tiếp tục gọi `Files.readString` sau khi đã đóng: có thể nhận `ClosedFileSystemException`.

### 9.2. `close` không đồng nghĩa một transaction atomic

Dù mọi lệnh trong `try` chạy thành công, Java API không hứa cả archive được cập nhật một cách **all-or-nothing** khi process bị kill, disk full, mất điện hoặc provider lỗi. Khi thay một ZIP quan trọng trong production, dùng một **archive tạm** do ứng dụng sở hữu:

```text
archive chính hiện tại
        |
Đọc/copy dữ liệu vào staging.zip mới
        |
Cập nhật các entries trong staging.zip
        |
Đóng ZipFS và xác minh staging.zip
        |
Publish staging.zip theo contract của filesystem
        |
Dọn staging nếu thất bại
```

Nếu đòi hỏi publication atomic, có thể thử `Files.move(staging, destination, ATOMIC_MOVE)` khi source và target cùng file store và provider hỗ trợ. API có thể ném `AtomicMoveNotSupportedException`; không âm thầm fallback sang move không atomic nếu nghiệp vụ không chấp nhận.

**Không coi việc `Files.writeString` xong một entry là thay đổi archive ngoài đã chắc chắn durable.** Phân biệt rõ flush/close, khả năng đọc lại, tính atomic và durability là những mức bảo đảm khác nhau.

### 9.3. Mở cùng archive nhiều lần

Nếu cùng URI ZIP filesystem đã được mount, gọi `FileSystems.newFileSystem(uri, ...)` lần nữa **có thể ném `FileSystemAlreadyExistsException`**.

Nếu nhiều phần của ứng dụng dùng chung một ZIP filesystem, cần quản lý **ownership**: ai tạo, ai được phép đóng, và các luồng nào đang xử lý entry. Không tự gọi `FileSystems.getFileSystem(uri)` rồi đóng một object mà subsystem khác vẫn đang dùng.

Trong ví dụ đầy đủ, chỉ có **một ZIP filesystem được mở tại mỗi thời điểm**. Chương trình đóng lần một rồi mới mở lại để xác minh nội dung.

## 10. Khác biệt giữa ZipFS và `java.util.zip`

Java có hai nhóm API hiện hành:

### 10.1. `ZipFile`, `ZipInputStream`, `ZipOutputStream`

- `java.util.zip.ZipFile`: mở archive ZIP đã có và đọc entries qua cơ chế `ZipEntry`/streams; phù hợp khi **chủ yếu đọc** và cần thao tác trực tiếp theo ZIP format.
- `ZipInputStream`: đọc một chuỗi ZIP entries tuần tự từ stream; phù hợp với workflow streaming và input stream.
- `ZipOutputStream`: ghi từng entry vào archive đang được tạo; phù hợp khi sản phẩm **tạo ZIP từ đầu** theo thứ tự.

Những API này **không lỗi thời** và vẫn phù hợp. Không cần chuyển toàn bộ code thành ZipFS nếu chỉ muốn ghi một archive mới tuần tự.

### 10.2. `ZipFS`

ZipFS phù hợp khi muốn sử dụng **path-oriented API**:

- Liệt kê directories theo cấu trúc.
- Tạo thư mục và file theo `Path`.
- Đọc/sửa entry theo tên.
- Copy/move/delete entries.
- Tái sử dụng `Files.walk`, `Files.readString`, `Files.copy`, `PathMatcher`.

Sự thuận tiện này có chi phí: phải quản lý lifecycle ZIP filesystem và hiểu archive có thể được viết lại; không phải mọi file store/attribute view giống default filesystem.

### 10.3. Không chỉnh archive cùng lúc bằng nhiều API độc lập

Một ứng dụng không nên đồng thời mở ZIP qua ZipFS để **ghi** và qua một cách khác để sửa chính tệp archive ở host mà không có cơ chế đồng bộ. Các handles/mapping có thể nhìn các trạng thái khác nhau và thay đổi của bên này có nguy cơ ghi đè hoặc làm bên kia lỗi.

Ví dụ trong bài dùng `ZipFile` **sau khi ZipFS đã đóng**, chỉ để xác nhận archive chuẩn có các entries mong đợi.

## 11. ZIP provider `jdk.zipfs` có các tùy chọn gì?

Module `jdk.zipfs` trong Java SE 17 mô tả các properties của environment map. Một số property đáng biết:

| Property | Kiểu/giá trị | Tác dụng |
| --- | --- | --- |
| `create` | Chuỗi hoặc boolean `true`/`false` | Tạo ZIP/JAR nếu chưa có |
| `encoding` | Tên charset, mặc định `UTF-8` | Giải mã/mã hóa **tên các entries** |
| `compressionMethod` | `DEFLATED` hoặc `STORED` | Chọn cách nén các entries được ghi |
| `enablePosixFileAttributes` | `true`/`false` | Bật khả năng hỗ trợ POSIX view của provider |
| `releaseVersion` | Phiên bản Java hoặc `runtime` | Cách chọn entry trong **multi-release JAR** |

Ví dụ:

```java
Map<String, String> options = Map.of(
        "create", "true",
        "encoding", "UTF-8",
        "compressionMethod", "DEFLATED");

try (FileSystem zip = FileSystems.newFileSystem(uri, options)) {
    // Thêm entries.
}
```

Theo tài liệu provider, `compressionMethod` mặc định là `DEFLATED`; `STORED` giữ entry không nén. Giá trị khác có thể làm constructor ném `IllegalArgumentException`.

**Chú ý:** `encoding` nói về **tên entry** bên trong ZIP, không tự xác định charset của nội dung `notes.txt`. Nội dung text phải được đọc/ghi bằng charset riêng, ví dụ `StandardCharsets.UTF_8`. Với ZIP rất cũ có tên entry mã hóa khác UTF-8, cần chính sách rõ và thử provider thực tế; không tự đổi charset để “sửa” nội dung nhị phân.

### 11.1. Attribute view và POSIX permissions

ZIP provider có attribute view tên `zip`, trong đó `zip:permissions` có thể tồn tại. Java 17 ZipFS cũng có thể hỗ trợ `PosixFileAttributeView` khi property `enablePosixFileAttributes` được bật.

Nhưng **đừng suy rằng ZIP tự thực thi quyền truy cập POSIX** như một filesystem ngoài host. Tài liệu nêu ZipFS không tự enforcement các permissions được lưu trong entry; owner/group trong view POSIX của provider có giới hạn lưu trữ riêng.

Nếu nghiệp vụ yêu cầu giữ ACL, executable bit, owner, timestamps hoặc symlink, phải xác định chính xác ZIP format, provider và attribute views thực sự hỗ trợ, rồi kiểm chứng bằng công cụ/OS đích. Không coi `Files.copy(..., COPY_ATTRIBUTES)` là bảo đảm metadata đầy đủ xuyên mọi provider.

### 11.2. Multi-release JAR là trường hợp chuyên biệt

`releaseVersion` phục vụ cách ZipFS nhìn entry của **multi-release JAR**, không phải tính năng cần dùng để tạo hoặc sửa một ZIP dữ liệu thông thường. Không đặt nó nếu không thực sự làm việc với multi-release JAR và hiểu cấu trúc `META-INF/versions`.

Với JAR chứa chữ ký, chỉnh sửa entries có thể làm chữ ký/metadata không còn hợp lệ. Một chương trình “sửa ZIP bất kỳ” không nên coi việc chỉnh JAR đã ký là an toàn tự động.

## 12. Bảo mật: Zip Slip, ZIP bomb và đường dẫn từ input không tin cậy

### 12.1. Zip Slip khi giải nén ra host

Một entry do người khác tạo có thể có tên:

```text
../../outside.txt
/absolute/path.txt
docs/../../secret.txt
```

Nếu chương trình giải nén bằng cách ghép đường dẫn và ghi mà không kiểm tra, nó có thể ghi ra ngoài thư mục được phép.

**Quan trọng:** Tài liệu `jdk.zipfs` cho Java 17 nói provider **không hỗ trợ mở archive hiện có chứa tên entry với thành phần `.` hoặc `..`**. Điều này là một giới hạn của provider, **không đồng nghĩa mọi API ZIP hoặc mọi file ZIP đều an toàn**. Các chương trình dùng `ZipInputStream`/`ZipFile` vẫn phải có bảo vệ khi xuất entry ra host.

Một kiểm tra lexical cơ bản khi tạo path đích:

```java
Path trustedRoot = extractionDirectory
        .toAbsolutePath().normalize();

Path candidate = trustedRoot.resolve(entryName).normalize();

if (!candidate.startsWith(trustedRoot)) {
    throw new SecurityException("Entry outside extraction root");
}
```

Đây là **mã minh họa, không phải bộ giải nén an toàn hoàn chỉnh**. `entryName` phải được kiểm tra là tên tương đối; các tên có separator hoặc absolute-path conventions khác OS cần xử lý rõ, và **symlink trong các thư mục cha cùng các thay đổi TOCTOU** có thể vượt qua phép kiểm tra lexical. Với input không tin cậy, cần chính sách không follow symlink, root được bảo vệ và thao tác I/O an toàn theo mô hình đe dọa, không chỉ một lệnh `normalize()/startsWith()`.

### 12.2. Chống tên entry bất thường khi ứng dụng tự tạo ZIP

Ví dụ đầy đủ có helper `safeEntry`:

```java
static Path safeEntry(FileSystem zip, String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Empty entry");
    }

    Path relative = zip.getPath(name);

    if (relative.isAbsolute()) {
        throw new IllegalArgumentException("Absolute entry");
    }

    for (Path part : relative) {
        if (part.toString().equals(".")
                || part.toString().equals("..")) {
            throw new IllegalArgumentException("Dot segment");
        }
    }

    Path root = zip.getPath("/");
    Path result = root.resolve(relative).normalize();

    if (result.equals(root) || !result.startsWith(root)) {
        throw new IllegalArgumentException("Outside ZIP root");
    }

    return result;
}
```

Helper này là **phòng ngừa một số lỗi tên nội bộ khi ứng dụng tự tạo ZIP**: từ chối tên rỗng, đường tuyệt đối và dot components. Nó **không** thay thế bộ kiểm tra security hoàn chỉnh đối với tên entry không tin cậy: tên có separator khác quy ước, ký tự điều khiển, tên đặc biệt, độ dài bất thường, duplicate/case collisions và chính sách file type vẫn phải được xử lý.

**Điểm khác biệt:** Helper trên chỉ xây `Path` bên trong ZipFS, **không trực tiếp ghi ra host**. Khi giải nén ra host, cần một bộ kiểm tra khác phù hợp với host filesystem và symlink policy.

### 12.3. ZIP bomb và giới hạn tài nguyên

Một ZIP có thể rất nhỏ trên đĩa nhưng chứa các entry có **kích thước giải nén cực lớn**. Khi đọc/giải nén ZIP từ nguồn không tin cậy, cần giới hạn:

- Tổng số entry.
- Tổng byte được giải nén (đếm **trong lúc stream đang đọc**, không chỉ tin metadata).
- Kích thước tối đa của mỗi entry.
- Độ sâu tên/path.
- Thời gian xử lý và mức sử dụng CPU.
- Số file/directory được tạo.
- Dung lượng staging và quota của đích.
- Chính sách đối với file đặc biệt, đường dẫn trùng nhau hoặc nội dung không hỗ trợ.

Không dùng `Files.readAllBytes` cho một entry không tin cậy mà không có giới hạn, vì có thể cạn heap. Với các tệp lớn, đọc stream từng block và chặn khi vượt giới hạn.

### 12.4. ZIP không phải vùng bảo mật độc lập

Một `FileSystem` dạng ZIP giúp thao tác entry theo API nhưng **không tự cung cấp sandbox quyền truy cập**, bảo vệ chống nội dung ác ý hay xác nhận archive lành mạnh. Xác minh nguồn file, loại entry, quota và quyền publish của ứng dụng vẫn cần được thiết kế riêng.

## 13. Ví dụ Java 17+ độc lập: tạo, đọc, cập nhật, move, delete và reopen

Ví dụ tạo **workspace riêng** bằng `Files.createTempDirectory`, không chỉnh file có sẵn của người dùng. Các bước:

1. Tạo tệp ngoài `payload.bin` chứa bốn byte `01 02 03 04`.
2. Tạo ZIP `lesson.zip` bằng URI `jar:` và `create=true`.
3. Tạo directory entries `/docs` và `/assets`.
4. Tạo `/docs/readme.txt` bằng `CREATE_NEW` với text `first`.
5. Cập nhật entry đó thành `updated` qua `TRUNCATE_EXISTING + WRITE` và đọc lại.
6. Tạo `notes.txt`, đổi tên thành `renamed.txt` rồi xóa entry mới.
7. Copy `payload.bin` từ host vào `/assets/payload.bin`, copy ngược ra host và xác minh bytes bằng `Files.mismatch`.
8. Test các tên `../outside.txt` và `/absolute.txt` bị helper từ chối.
9. Liệt kê regular files trong ZIP: chỉ còn `assets/payload.bin` và `docs/readme.txt`.
10. Đóng ZIP filesystem, **mở lại**, đọc text và byte của entries sau close.
11. Mở archive với `ZipFile` chuẩn để xác nhận những entry mới/cũ thực sự xuất hiện/biến mất như mong muốn.
12. Dọn workspace riêng bằng `Files.walkFileTree`.

Tạo tệp **`ZipFileSystemCreateReadUpdateDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.zip.ZipFile;

public final class ZipFileSystemCreateReadUpdateDemo {

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static Path safeEntry(FileSystem zip, String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Empty entry");
        }
        Path relative = zip.getPath(name);

        if (relative.isAbsolute()) {
            throw new IllegalArgumentException("Absolute entry");
        }
        for (Path part : relative) {
            if (part.toString().equals(".")
                    || part.toString().equals("..")) {
                throw new IllegalArgumentException("Dot segment");
            }
        }

        Path root = zip.getPath("/");
        Path resolved = root.resolve(relative).normalize();

        if (resolved.equals(root) || !resolved.startsWith(root)) {
            throw new IllegalArgumentException("Outside ZIP root");
        }
        return resolved;
    }

    static String regularEntries(FileSystem zip) throws IOException {
        try (Stream<Path> stream = Files.walk(zip.getPath("/"))) {
            return stream.filter(Files::isRegularFile)
                    .map(p -> zip.getPath("/").relativize(p).toString())
                    .sorted()
                    .collect(Collectors.joining(", "));
        }
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
                    Path dir, IOException cause)
                    throws IOException {
                if (cause != null) throw cause;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path workspace =
                Files.createTempDirectory("zipfs-lesson-");

        try {
            Path archive = workspace.resolve("lesson.zip");
            Path source = workspace.resolve("payload.bin");

            Files.write(source, new byte[]{1, 2, 3, 4});
            URI zipUri = URI.create("jar:" + archive.toUri());

            boolean blockedTraversal;
            boolean blockedAbsolute;
            boolean copiedEqual;
            String entries;
            String updated;
            boolean moved;
            boolean removed;

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {

                Path docs = zip.getPath("/docs");
                Path assets = zip.getPath("/assets");

                Files.createDirectories(docs);
                Files.createDirectories(assets);

                Path readme = safeEntry(zip, "docs/readme.txt");

                Files.writeString(
                        readme, "first\n", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);

                Files.writeString(
                        readme, "updated\n", StandardCharsets.UTF_8,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE);

                updated = Files.readString(
                        readme, StandardCharsets.UTF_8).strip();

                Path temp = safeEntry(zip, "docs/notes.txt");
                Files.writeString(
                        temp, "notes\n", StandardCharsets.UTF_8);

                Path renamed = safeEntry(zip, "docs/renamed.txt");
                Files.move(temp, renamed);

                moved = Files.exists(renamed)
                        && !Files.exists(temp);

                Files.delete(renamed);
                removed = !Files.exists(renamed);

                Path asset = safeEntry(zip, "assets/payload.bin");
                Files.copy(source, asset);

                Path extracted =
                        workspace.resolve("exported.bin");

                Files.copy(asset, extracted);

                copiedEqual =
                        Files.mismatch(source, extracted) == -1L;

                try {
                    safeEntry(zip, "../outside.txt");
                    blockedTraversal = false;
                } catch (IllegalArgumentException expected) {
                    blockedTraversal = true;
                }

                try {
                    safeEntry(zip, "/absolute.txt");
                    blockedAbsolute = false;
                } catch (IllegalArgumentException expected) {
                    blockedAbsolute = true;
                }

                entries = regularEntries(zip);
            }

            String reopened;
            boolean reopenedBinary;

            try (FileSystem zip = FileSystems.newFileSystem(
                    zipUri, Map.of())) {

                reopened = Files.readString(
                        zip.getPath("/docs/readme.txt"),
                        StandardCharsets.UTF_8).strip();

                reopenedBinary = Files.mismatch(
                        source,
                        zip.getPath("/assets/payload.bin")) == -1L;
            }

            boolean archiveExists =
                    Files.isRegularFile(archive)
                    && Files.size(archive) > 0;

            boolean standardZipReader;

            try (ZipFile zip = new ZipFile(
                    archive.toFile(), StandardCharsets.UTF_8)) {

                standardZipReader =
                        zip.getEntry("docs/readme.txt") != null
                        && zip.getEntry("assets/payload.bin") != null
                        && zip.getEntry("docs/notes.txt") == null
                        && zip.getEntry("docs/renamed.txt") == null;
            }

            System.out.println(
                    "archive.created=" + archiveExists);
            System.out.println(
                    "entry.updated=" + updated);
            System.out.println(
                    "entry.moved=" + moved);
            System.out.println(
                    "entry.deleted=" + removed);
            System.out.println(
                    "copy.bytesEqual=" + copiedEqual);
            System.out.println(
                    "entry.traversalRejected=" + blockedTraversal);
            System.out.println(
                    "entry.absoluteRejected=" + blockedAbsolute);
            System.out.println(
                    "zip.files=" + entries);
            System.out.println(
                    "reopen.updated=" + reopened);
            System.out.println(
                    "reopen.binaryEqual=" + reopenedBinary);
            System.out.println(
                    "standardZipReader.valid=" + standardZipReader);

            check(archiveExists
                    && updated.equals("updated")
                    && moved && removed && copiedEqual
                    && blockedTraversal && blockedAbsolute
                    && entries.equals(
                            "assets/payload.bin, docs/readme.txt")
                    && reopened.equals("updated")
                    && reopenedBinary && standardZipReader,
                    "ZIP operations");

            System.out.println("checks=PASS");
        } finally {
            deleteTree(workspace);
        }

        System.out.println(
                "workspace.cleaned=" + !Files.exists(workspace));
    }
}
```

Chạy bằng **JDK 17+**:

```bash
javac -encoding UTF-8 ZipFileSystemCreateReadUpdateDemo.java
java ZipFileSystemCreateReadUpdateDemo
```

**Stdout chính xác đã kiểm chứng trên JDK với module `jdk.zipfs`:**

```text
archive.created=true
entry.updated=updated
entry.moved=true
entry.deleted=true
copy.bytesEqual=true
entry.traversalRejected=true
entry.absoluteRejected=true
zip.files=assets/payload.bin, docs/readme.txt
reopen.updated=updated
reopen.binaryEqual=true
standardZipReader.valid=true
checks=PASS
workspace.cleaned=true
```

### 13.1. Ý nghĩa các dòng output

- `archive.created=true`: tệp `lesson.zip` ở host tồn tại và có kích thước dương sau khi ZIP filesystem đã đóng.
- `entry.updated=updated`: nội dung entry `docs/readme.txt` đã được thay bởi text mới.
- `entry.moved=true`: entry `notes.txt` đã được đổi tên thành `renamed.txt` trong view ZipFS, tên cũ không còn.
- `entry.deleted=true`: entry đã đổi tên được xóa; bản ZIP cuối không chứa nó.
- `copy.bytesEqual=true`: file nhị phân copy từ host vào ZIP rồi xuất lại **khớp bytes** bằng `Files.mismatch`.
- `entry.traversalRejected=true` và `entry.absoluteRejected=true`: helper từ chối hai tên không hợp lệ theo policy ví dụ.
- `zip.files=...`: danh sách regular files bên trong ZIP đã được sort theo tên tương đối, không bao gồm directory entries.
- `reopen.updated=updated` và `reopen.binaryEqual=true`: sau khi **đóng rồi mở lại ZIP**, nội dung được bảo toàn trong lần kiểm tra.
- `standardZipReader.valid=true`: `ZipFile` tiêu chuẩn đọc được những mục cần có và xác nhận các mục đã xóa không tồn tại.
- `checks=PASS`: toàn bộ điều kiện chính của ví dụ đã qua kiểm tra.
- `workspace.cleaned=true`: workspace riêng được xóa sau khi kết thúc thành công.

### 13.2. Vì sao không in tên thư mục tạm?

`Files.createTempDirectory` tạo tên ngẫu nhiên và vị trí khác nhau theo OS. Ví dụ chỉ in trạng thái và tên entry tương đối bên trong ZIP, nên stdout có thể so sánh được mà không dựa vào `C:\...` hoặc `/tmp/...` cụ thể.

### 13.3. Kết quả nào phụ thuộc môi trường?

Nếu runtime thiếu `jdk.zipfs`, filesystem host không writable, không có quyền tạo/xóa thư mục tạm, archive bị thay đổi đồng thời hoặc provider có lỗi I/O, chương trình có thể ném exception. `checks=PASS` là kết quả của **lần chạy kiểm thử**, không phải lời hứa mọi môi trường luôn thành công.

### 13.4. Dữ liệu ví dụ được xóa thế nào?

Chương trình tạo **workspace tạm mới** của riêng nó, không nhận đường dẫn người dùng để xóa. `deleteTree` xóa đệ quy và chỉ dùng trên workspace ấy. **Không sao chép cách gọi xóa đệ quy này sang một đường dẫn nhập từ người dùng** nếu không có hợp đồng ownership/authorization rõ ràng.

## 14. Lỗi I/O và tình huống cạnh tranh thường gặp

### 14.1. `ProviderNotFoundException`

Có thể xuất hiện khi runtime không cung cấp ZIP file system provider. Với JDK tùy biến, cần kiểm tra module `jdk.zipfs` được đóng gói đúng. Nếu sản phẩm dùng plugin filesystem tự viết, cần kiểm tra cách cài đặt provider tương ứng.

### 14.2. `FileSystemAlreadyExistsException`

Có thể xuất hiện khi cùng URI đã được mount trước đó mà code lại gọi `newFileSystem`. Không cố **mở lần hai rồi tự đóng shared filesystem** mà không có owner rõ ràng; quản lý một phiên mở theo lifecycle và đồng bộ truy cập.

### 14.3. `NoSuchFileException` và `FileAlreadyExistsException`

- Entry đọc/cập nhật không tồn tại: có thể lỗi `NoSuchFileException`.
- Tạo với `CREATE_NEW` khi entry đã có: có thể lỗi `FileAlreadyExistsException`.
- Copy vào tên entry đã có mà không cho replace: có thể lỗi `FileAlreadyExistsException`.

Những exception này phản ánh **hợp đồng ghi cụ thể**; không nên catch tất cả rồi mặc định chuyển sang `REPLACE_EXISTING`.

### 14.4. `ZipException`, archive hỏng hoặc format không được hỗ trợ

Một file có đuôi `.zip` không nhất thiết là ZIP hợp lệ. File có thể hỏng central directory, entry sử dụng format/method không được ZIP provider hỗ trợ, hoặc có tên entry không được provider chấp nhận.

Nếu archive không tin cậy, việc mở phải xử lý `IOException` và các subclass phù hợp (trong đó có thể có `ZipException`). Đừng giả định luôn nhận được một ZIP filesystem dùng được chỉ vì tên file kết thúc `.zip`.

### 14.5. `ClosedFileSystemException`

Sau khi `FileSystem` đóng, những `Path` cũ thuộc ZIP filesystem không còn được dùng để thực hiện I/O. Muốn đọc lại, mở một phiên mới rồi lấy path từ đối tượng FileSystem mới:

```java
try (FileSystem reopened =
        FileSystems.newFileSystem(uri, Map.of())) {
    Path readme = reopened.getPath("/docs/readme.txt");
    System.out.println(Files.readString(readme));
}
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException`.

### 14.6. Cạn dung lượng khi cập nhật archive

Provider có thể phải dùng không gian tạm hay tổ chức lại archive khi cập nhật, nên nhu cầu dung lượng **có thể lớn hơn** kích thước entry đang thay. `Files.getFileStore(archivePath).getUsableSpace()` chỉ cung cấp hint về vùng lưu trữ, không hứa lần cập nhật thành công. Khi disk full, ZIP có thể bị cập nhật dở hoặc quá trình close thất bại.

Với dữ liệu quan trọng, dùng staging độc lập và chỉ publish sau khi close/verify, quản lý lỗi cleanup và backup rõ ràng.

### 14.7. Concurrent edits

Hai threads hoặc hai processes cùng cập nhật archive mà không điều phối có thể gây race, ghi đè hoặc lỗi. Một object `FileSystem` không tạo ra **transaction isolation** cho mọi thao tác nghiệp vụ, và nhiều tiến trình mở file archive bằng công cụ khác nhau không có cơ chế locking chung được hứa tự động.

Một service có thể dùng queue/mutex theo archive, owner của phiên ZIPFS và phiên bản output mới thay cho cập nhật trực tiếp kho chung nhiều nơi cùng lúc.

## 15. Khi nào nên dùng ZipFS thay cho cách khác?

| Nhu cầu | Hướng thường phù hợp |
| --- | --- |
| Tạo ZIP mới theo thứ tự từ nhiều streams | `ZipOutputStream` |
| Đọc entries từ archive đã có | `ZipFile` hoặc ZipFS |
| Đọc ZIP từ `InputStream` liên tục | `ZipInputStream` |
| Cập nhật, đổi tên, xóa entry với `Path` | **ZipFS** |
| Duyệt thư mục nội bộ theo `Files.walk` | **ZipFS** |
| Chuyển file host vào ZIP/ra ZIP | `Files.copy` giữa providers |
| Cần ZIP transaction/atomic update tuyệt đối | Staging, verify, publish theo khả năng storage |
| Kho ZIP rất lớn, file không tin cậy | Thiết kế streaming/limit/quota, benchmark và security checks |
| Cập nhật JAR đã ký | Không tùy tiện sửa; xét tính toàn vẹn/chữ ký của JAR |

Không có lựa chọn nào đúng cho mọi workload. Khi chỉ cần phát một ZIP mới trong HTTP response, `ZipOutputStream` có thể trực tiếp và gọn hơn. Khi cần thao tác nhiều entry theo cấu trúc tên thư mục, ZipFS giúp dùng lại phần lớn NIO.2.

## 16. Checklist kiểm thử cho ứng dụng thao tác ZIP

### 16.1. Các trường hợp đúng

- [ ] Tạo ZIP ở path chưa tồn tại với `create=true`.
- [ ] Đọc lại ZIP tồn tại khi **không** dùng create.
- [ ] Tạo thư mục mẹ và file con.
- [ ] Ghi text Unicode bằng UTF-8.
- [ ] Ghi binary mà không chuyển qua `String`.
- [ ] `CREATE_NEW` từ chối entry đã tồn tại.
- [ ] `TRUNCATE_EXISTING` thay nội dung entry hiện hữu.
- [ ] `Files.move` đổi tên entry và tên cũ không còn.
- [ ] `Files.delete` xóa entry như yêu cầu.
- [ ] `Files.list`/`Files.walk` đưa danh sách chính xác.
- [ ] Copy host → ZIP và ZIP → host giữ nguyên bytes.
- [ ] Đóng rồi **mở lại** ZIP vẫn đọc được nội dung.
- [ ] `ZipFile` tiêu chuẩn xác minh archive hợp lệ.
- [ ] Đúng policy khi target đã có hoặc muốn replace.

### 16.2. Các trường hợp lỗi, an toàn và giới hạn

- [ ] Archive không tồn tại khi mở read-only.
- [ ] ZIP hỏng, sai format, entry method không hỗ trợ.
- [ ] Runtime thiếu module `jdk.zipfs`.
- [ ] Cùng URI bị mount hai lần và ownership chưa rõ.
- [ ] Hết dung lượng trong lúc update/close.
- [ ] Thư mục cha của archive hoặc entry không tồn tại.
- [ ] Không có quyền đọc/ghi hoặc file bên ngoài read-only.
- [ ] Input có `..` hoặc absolute path.
- [ ] ZIP bomb/entry có kích thước giải nén quá lớn.
- [ ] Symlink và đường dẫn host bị đổi trong lúc xuất file.
- [ ] Entry tên dài, có Unicode, ký tự đặc biệt hoặc trùng sau case-folding.
- [ ] Hai tác vụ cùng sửa một archive.
- [ ] Close thất bại; staging/backup được xử lý theo policy.
- [ ] ZIP chứa metadata/permissions quan trọng.
- [ ] Có test cross-platform Windows/Linux và ZIP provider thực.

**Không gây lỗi “disk full” bằng cách làm đầy ổ chung của người dùng**. Dùng filesystem test có quota riêng hoặc mock/fault injection cho các trường hợp này.

## 17. Các lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `Path.of("/docs/readme.txt")` để đọc entry ZIP | Trỏ vào host filesystem | `zipFs.getPath("/docs/readme.txt")` |
| Tự ghép `"jar:file:"+rawPath` | Hỏng URI trên Windows/ký tự escape | `URI.create("jar:" + archive.toUri())` |
| Quên `create=true` khi ZIP chưa tồn tại | Không có archive để mở | Dùng provider env phù hợp |
| Nghĩ `create=true` xóa archive cũ | Ghi vào archive hiện có ngoài ý muốn | Xác minh ownership và path mới |
| Quên tạo directory cha entry | Không ghi được file lồng sâu | `Files.createDirectories(parent)` |
| Dùng `writeString` mặc định khi chỉ muốn create-new | Có thể truncate entry đang có | `CREATE_NEW + WRITE` |
| Dùng `CREATE_NEW` khi muốn cập nhật | Gặp `FileAlreadyExistsException` | `WRITE + TRUNCATE_EXISTING` |
| Không đóng ZIP filesystem | Có thể chưa hoàn tất ghi/archive bị giữ resource | `try-with-resources` |
| Dùng `Path` trong ZIP sau close | `ClosedFileSystemException` | Mở lại FS và lấy Path mới |
| Tưởng update ZIP là atomic | Rủi ro archive dở dang khi lỗi | Staging, verify, publish |
| Ghi `REPLACE_EXISTING` không cần thiết | Mất entry cũ | Policy ghi đè rõ ràng |
| Chuyển binary qua charset text | Dữ liệu bị sai | `Files.copy`/byte streams |
| Đọc mọi entry bằng `readAllBytes` | Có thể cạn heap | Stream có limit |
| Coi tên entry không tin cậy là path host an toàn | Zip Slip/path traversal | Kiểm tra path, symlink, root |
| Chỉ dùng `normalize/startsWith` và coi đủ bảo mật | Symlink/race còn tồn tại | Security policy và I/O chống race |
| Không kiểm soát ZIP bomb | Giải nén có thể làm cạn RAM/disk | Quota, size/count/time limits |
| Dùng ZipFS và `ZipFile` ghi cùng archive đồng thời | Race/đè trạng thái | Chỉ một owner ghi, xác minh sau close |
| Xem ZIP permissions như ACL host bắt buộc có hiệu lực | Sai mô hình bảo mật | Kiểm tra provider/metadata policy |
| Tin mọi ZIP file đều mở được bằng ZipFS | Format/provider có giới hạn | Xử lý `IOException`/`ZipException` |
| Không kiểm tra reopened ZIP | Chỉ biết view trước close | Close, reopen, verify |
| Dùng `Files.walk` mà không đóng stream | Rò tài nguyên | `try-with-resources` |

## 18. Câu hỏi ôn tập

**Câu 1.** ZIP filesystem khác tệp ZIP bên ngoài như thế nào?  
**Đáp án:** Tệp ZIP nằm trên host filesystem, còn ZipFS là provider cho phép truy cập **entries bên trong** archive như `Path`.

**Câu 2.** Tại sao URI của ZipFS bắt đầu bằng `jar:` dù file kết thúc `.zip`?  
**Đáp án:** `jar` là URI scheme của ZIP provider trong JDK; nó không bắt buộc archive là JAR có class.

**Câu 3.** Khi ZIP chưa tồn tại, cần gì để provider tạo file?  
**Đáp án:** Environment property `"create"` có giá trị `"true"` (hoặc boolean true theo provider) và quyền tạo archive ngoài.

**Câu 4.** Muốn tạo `/docs/guide.txt`, có cần tạo `/docs` trước?  
**Đáp án:** Có, nếu directory cha chưa có thì tạo bằng `Files.createDirectories`.

**Câu 5.** `zipFs.getPath("/a.txt")` có giống `Path.of("/a.txt")` không?  
**Đáp án:** Không. Chúng thuộc các filesystem providers khác nhau, dù có thể có cùng tên hiển thị.

**Câu 6.** Cập nhật `readme.txt` bằng open options nào để thay toàn bộ nội dung?  
**Đáp án:** `WRITE + TRUNCATE_EXISTING` trên entry đã có; không dùng `CREATE_NEW` nếu mục đích là update.

**Câu 7.** Muốn tạo entry mới mà không ghi đè tên đã có, dùng gì?  
**Đáp án:** `CREATE_NEW + WRITE`.

**Câu 8.** Tại sao phải đóng `FileSystem` ZIP sau khi cập nhật?  
**Đáp án:** Để provider hoàn tất tài nguyên và quá trình cập nhật archive. Đóng rồi mở lại cho phép xác minh kết quả lưu được đọc lại.

**Câu 9.** `close()` có bảo đảm archive được cập nhật atomic khi mất điện không?  
**Đáp án:** Không. Ứng dụng cần staging/verify/publish và xét khả năng của file store nếu yêu cầu atomic/durable.

**Câu 10.** Khi copy file nhị phân vào ZIP, có nên gọi `new String(bytes)` trước không?  
**Đáp án:** Không. Dùng byte streams hoặc `Files.copy` để giữ nguyên bytes.

**Câu 11.** Với một entry `../../etc/config` từ archive không tin cậy, có được ghép thẳng ra thư mục đích không?  
**Đáp án:** Không. Cần chống Zip Slip, kiểm tra absolute/dot segments, path containment và symlink/race trên host.

**Câu 12.** ZipFS có mở được mọi archive ZIP không?  
**Đáp án:** Không. Provider có giới hạn format và tên entry, trong Java 17 không hỗ trợ ZIP tồn tại có thành phần `.`/`..` trong tên entries.

**Câu 13.** Khi nào `ZipOutputStream` có thể phù hợp hơn ZipFS?  
**Đáp án:** Khi chỉ cần sinh một archive mới theo luồng, không phải sửa nhiều entry ngẫu nhiên bằng `Path`.

**Câu 14.** `encoding` trong env ZipFS chỉ gì?  
**Đáp án:** Charset cho **tên entry** trong ZIP; nội dung text vẫn phải dùng charset đọc/ghi riêng.

**Câu 15.** Làm sao kiểm tra archive sau khi đã cập nhật?  
**Đáp án:** Đóng ZipFS, mở lại bằng ZipFS hoặc `ZipFile`, kiểm tra entries và bytes/nội dung/metadata theo hợp đồng.

## 19. Kết luận và tài liệu chính thức hiện hành

Khi cần **tạo, đọc và cập nhật mục trong kho ZIP**, có thể coi archive là một `FileSystem` thông qua module `jdk.zipfs` và dùng NIO.2:

1. Xác định `Path` của **archive bên ngoài** và tạo URI `jar:` hợp lệ.
2. Dùng `FileSystems.newFileSystem(uri, Map.of("create","true"))` khi cần tạo ZIP mới.
3. Lấy **entry paths** bằng `zipFs.getPath("/...")`.
4. Dùng `Files.createDirectories`, `Files.writeString`, `Files.readString`, `Files.copy`, `Files.move` và `Files.delete` để thao tác các entry.
5. Dùng `Files.list/walk` để duyệt; đóng streams và ZIP filesystem.
6. Đóng ZIP rồi **mở lại** để xác minh nội dung archive.
7. Với archive dữ liệu quan trọng, dùng staging/verify và chính sách atomic publish khi được provider hỗ trợ.
8. Với input không tin cậy, chặn path traversal, ZIP bomb và mọi hành vi xuất tệp ra ngoài vùng được phép.

Đây là kỹ thuật **vẫn áp dụng trong Java 17+**, đồng thời `ZipFile`/`ZipInputStream`/`ZipOutputStream` vẫn có chỗ đứng phù hợp.

### Tài liệu chính thức

- [Oracle Java SE 17 — Module `jdk.zipfs`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP provider, URI scheme `jar`, `create`, `encoding`, `compressionMethod` và các giới hạn.
- [Oracle Java SE 17 — `FileSystems`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): `newFileSystem(URI,Map)` và các overload.
- [Oracle Java SE 17 — `FileSystem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `getPath`, `getPathMatcher`, lifecycle `close`.
- [Oracle Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `writeString`, `readString`, `copy`, `move`, `delete`, `list`, `walk`.
- [Oracle Java SE 17 — `StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `WRITE`, `TRUNCATE_EXISTING`.
- [Oracle Java SE 17 — `ZipFile`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html): đọc archive chuẩn theo ZIP entries.
- [Oracle Java SE 17 — `ZipInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html) và [`ZipOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html): các phương án stream còn hiệu lực.
