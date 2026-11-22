# File, đường dẫn, charset và tài nguyên trong @TempDir

## 1. Mục tiêu và vị trí kiến thức

Các bài test có thao tác file thường thất bại ngẫu nhiên khi chuyển từ laptop sang Windows, Linux CI hoặc môi trường đóng gói Spring Boot JAR. Lỗi không nhất thiết nằm ở logic kinh doanh: một đường dẫn bị hardcode, một `InputStream` chưa đóng, charset hệ điều hành khác nhau hoặc hai test cùng ghi vào một thư mục dùng chung đều có thể làm kết quả không ổn định.

**`@TempDir`** của JUnit Jupiter cung cấp một thư mục tạm do test framework tạo và dọn. Khi kết hợp với `java.nio.file.Path`, `java.nio.file.Files`, `StandardCharsets.UTF_8` và Spring `ResourceLoader`, ta có thể kiểm logic file thật mà không sửa dữ liệu trong repository, không cần root path cố định và không phụ thuộc thư mục hiện hành.

Bài thuộc phần **Tích hợp bổ sung** của module **Spring Boot – testing** với chủ đề chính **File, đường dẫn, charset và tài nguyên trong @TempDir**.

Kết thúc bài, bạn có thể:

1. Sử dụng `@TempDir` với `Path` hoặc `File` trên field/test method parameter.
2. Phân biệt `@TempDir` instance, static và parameter-scoped.
3. Hiểu mặc định cleanup, `ON_SUCCESS`, `NEVER` và lỗi resource còn mở.
4. Viết code test portable bằng `Path.resolve`, `Files.createDirectories`, `Files.readString` và `Files.writeString`.
5. Giải thích `normalize` là lexical transformation, còn `toRealPath` truy vấn filesystem thực.
6. Kiểm charset **UTF-8 tường minh**, text tiếng Việt, emoji, bytes, newline, BOM và malformed byte sequences.
7. Phân biệt classpath resource trong JAR với file thật trên filesystem.
8. Đọc fixture bằng `ClassPathResource.getInputStream()` và đọc output qua `FileSystemResource`.
9. Test input filename, path traversal, absolute paths, Windows reserved names, file đã tồn tại và symlink.
10. Dùng `@SpringBootTest` để test một service Spring thật nhưng giữ output root theo từng `@TempDir`.
11. Hiểu giới hạn của local temp filesystem test đối với production volumes, cloud storage, NFS và security races.
12. Chạy ví dụ đầy đủ **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter**.

**Kết luận quan trọng:** Một test filesystem tốt không chỉ assert `Files.exists`, mà kiểm **đúng đường dẫn, đúng bytes, đúng encoding, đúng chính sách overwrite và đúng cleanup boundary**.

## 2. Vì sao không hardcode file paths trong JUnit tests?

Một ví dụ dễ gây lỗi:

~~~java
@Test
void writesOutput() throws IOException {
    Path file = Path.of("C:\\temp\\report.txt");
    Files.writeString(file, "finished");
    assertTrue(Files.exists(file));
}
~~~

Đây chỉ là **snippet minh họa**, không phải class runnable. Nó có nhiều rủi ro:

- Máy Linux không có ổ `C:`.
- Cổng CI có thể không có quyền ghi ở đường dẫn đó.
- File tồn tại sẵn từ test trước khiến assertion bị **false positive**.
- Nếu hai test chạy song song ghi cùng file, content có thể không xác định.
- Test không dọn dữ liệu.
- Nếu ứng dụng đang kỳ vọng UTF-8, code đọc khác charset vẫn có thể sai.
- Thay project working directory có thể đổi nơi ghi của một path tương đối.

Cách tốt hơn:

~~~java
@Test
void writesOutput(@TempDir Path tempDir)
        throws IOException {
    Path file = tempDir.resolve("report.txt");
    Files.writeString(
            file, "Đã hoàn tất",
            StandardCharsets.UTF_8);

    assertEquals("Đã hoàn tất",
            Files.readString(
                    file, StandardCharsets.UTF_8));
}
~~~

JUnit tạo root mới theo scope của declaration; test không cần biết `/tmp` hay `%TEMP%`. Mọi file được ghi bên dưới root này và được dọn theo lifecycle `@TempDir` mặc định.

### Không ghi vào src/test/resources

`src/test/resources` là nơi chứa **fixture gốc đọc-only**. Nếu test chỉnh trực tiếp một file ở đó, nó có thể làm bẩn Git workspace, ảnh hưởng test khác hoặc bị thiếu quyền trong JAR/classpath. Hãy đọc fixture từ classpath rồi copy nó vào `@TempDir`, sau đó biến đổi bản copy.

## 3. Lifecycle của JUnit Jupiter @TempDir

Import chính xác:

~~~java
import org.junit.jupiter.api.io.TempDir;
~~~

JUnit Jupiter có built-in `TempDirectory` extension. Trong JUnit 5.10.x được quản lý bởi Spring Boot 3.3.5, những cách dùng phổ biến là test/lifecycle method parameter và field loại `Path`/`java.io.File`.

### 3.1. Method parameter

~~~java
@Test
void writes(@TempDir Path directory)
        throws IOException {
    Files.writeString(
            directory.resolve("a.txt"), "a",
            StandardCharsets.UTF_8);
}
~~~

Phù hợp khi test chỉ cần root trong một method. Cách này giúp test rõ tài nguyên được cấp theo từng invocation.

### 3.2. Instance field

~~~java
class ExportTest {
    @TempDir
    Path root;

    @BeforeEach
    void prepare() throws IOException {
        Files.writeString(
                root.resolve("seed.txt"), "seed",
                StandardCharsets.UTF_8);
    }

    @Test
    void usesSeed() throws IOException {
        assertEquals("seed",
                Files.readString(
                    root.resolve("seed.txt"),
                    StandardCharsets.UTF_8));
    }
}
~~~

Đây là snippet minh họa có imports cần thiết. Một `@TempDir` instance field có thể được chia sẻ giữa `@BeforeEach` và `@Test` của **cùng invocation**.

### 3.3. Static field

~~~java
class SharedTempTest {
    @TempDir
    static Path sharedRoot;

    @Test
    void testA() { /* uses sharedRoot */ }

    @Test
    void testB() { /* uses sharedRoot */ }
}
~~~

Static `@TempDir` có class-level scope. Nó có thể tiết kiệm setup, nhưng nếu các tests dùng cùng filenames, delete hoặc mutate shared resources, sẽ phát sinh phụ thuộc thứ tự và concurrency problems. Với integration tests không có shared-fixture requirement, ưu tiên **non-static**.

### 3.4. Những khai báo không đúng

- `@TempDir String` không thuộc các type được hỗ trợ.
- `@TempDir final Path` không phù hợp vì field phải được JUnit inject.
- Không tự gán một value vào `@TempDir` field rồi mong JUnit overwrite.
- Không dùng constructor parameter `@TempDir` theo hướng dẫn của **JUnit 5.10.x**; các version JUnit mới hơn có thể bổ sung target constructor, nhưng bài chạy theo Boot 3.3.5 cần API đúng BOM.
- `@TempDir` **không phải Spring bean annotation** và không được tự động áp dụng cho production `@Service`.

### 3.5. Cleanup policy

JUnit mặc định chọn cleanup mode `ALWAYS`: khi scope kết thúc, JUnit cố gắng xóa recursively root và các file/dirs bên dưới. Khi debug có thể dùng:

~~~java
@Test
void preservesOnFailure(
        @TempDir(cleanup = CleanupMode.ON_SUCCESS)
                Path directory) {
    // Nếu test fail, JUnit có thể giữ thư mục.
}
~~~

Snippet minh họa, cần import `CleanupMode`. Các tùy chọn chính:

| Mode | Hành vi | Khi nào |
| --- | --- | --- |
| `ALWAYS` | Cố gắng dọn khi hết scope, kể cả failure | Mặc định cho CI |
| `ON_SUCCESS` | Chỉ dọn khi test thành công | Điều tra lỗi có kiểm soát |
| `NEVER` | Không tự dọn | Debug đặc biệt, phải quản lý disk |

Không giữ lại tất cả temporary directories trên CI chỉ để “xem sau”; có thể làm đầy disk. Khi cleanup thất bại, kiểm resources còn mở và permission trước khi tắt cleanup.

### 3.6. Temp path không có tên cố định

JUnit/JDK có thể tạo root ở thư mục tạm hệ điều hành (liên quan `java.io.tmpdir`) với một tên ngẫu nhiên. Không assert `tempDir.toString().startsWith("/tmp")`. Assertion hữu ích hơn là `Files.isDirectory(tempDir)` và `output.startsWith(tempDir)` trong cùng filesystem.

## 4. `Path`, `File`, `URI`, `Resource` khác nhau ra sao?

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| `Path` | java.nio.file | Biểu diễn path theo filesystem provider |
| `Files` | java.nio.file | Tạo/đọc/ghi/copy/move/delete files |
| `File` | java.io | Pathname theo Java IO truyền thống |
| `URI` | java.net | Định danh tài nguyên theo URI syntax |
| `Resource` | Spring Core | Giao diện đọc resource từ nhiều nguồn |
| `ResourceLoader` | Spring Core | Giải quyết resource theo location |
| `ClassPathResource` | Spring Core | Resource bên trong classpath/JAR |
| `FileSystemResource` | Spring Core | Resource trên filesystem |
| `InputStream` | java.io | Đọc bytes |
| `Reader` | java.io | Giải mã bytes thành characters |

Đối với test file, thường bắt đầu bằng `Path` và `Files`. Chỉ chuyển sang `File` khi một API cũ đòi `File`:

~~~java
Path path = tempDir.resolve("data.txt");
File oldFile = path.toFile();
URI uri = path.toUri();
Resource resource = new FileSystemResource(path);
~~~

Đây là snippet minh họa, không phải một chương trình độc lập. `toFile()` có giới hạn với custom filesystem providers; nó không phải conversion universal cho mọi `Path`.

### 4.1. `resolve` tạo path, không tạo file

~~~java
Path candidate = tempDir.resolve("reports/output.txt");
~~~

Sau lệnh này chưa có file nào được tạo. Nếu parent `reports` chưa tồn tại:

~~~java
Files.createDirectories(candidate.getParent());
Files.writeString(
        candidate, "hello", StandardCharsets.UTF_8);
~~~

`Files.createDirectories` tạo cả các directories thiếu trong hierarchy và có thể trả về bình thường nếu chúng đã tồn tại phù hợp.

### 4.2. `normalize` chỉ sửa cú pháp

~~~java
Path path = tempDir.resolve("drafts/../ready.txt")
        .normalize();
~~~

Kết quả lexical thường là `tempDir/ready.txt`. **Không cần file tồn tại** và **không tự resolve symlink**. Việc gọi `normalize` trước khi kiểm path là một bước nên làm, nhưng không đủ cho security boundary chống attacker có quyền thao tác filesystem.

### 4.3. `toAbsolutePath` và `toRealPath`

`toAbsolutePath` chuyển relative path theo working directory hiện tại; nó không cần file tồn tại. `toRealPath` yêu cầu path tồn tại, truy vấn filesystem và thường resolve symbolic links.

~~~java
Path absolute = tempDir.toAbsolutePath().normalize();
Path real = tempDir.toRealPath();
~~~

Không dùng hai API như đồng nghĩa. Với một root do `@TempDir` tạo, `toRealPath()` phù hợp để kiểm containment và loại một số khác biệt path aliases trong test.

### 4.4. `Path.startsWith` là path operation

~~~java
Path base = tempDir.toRealPath();
Path target = base.resolve("report.txt").normalize();

assertTrue(target.startsWith(base));
~~~

Đây là **Path.startsWith**, không phải `target.toString().startsWith(base.toString())`. Ví dụ string `/work/outside` bắt đầu bằng `/work/out` nhưng không phải child of `/work/out`. Kiểm qua path segments có ý nghĩa hơn. Tuy vậy, symlink/TOCTOU vẫn cần security design riêng.

## 5. Đường dẫn đa nền tảng

| Cách xây path | Kết quả |
| --- | --- |
| `Path.of("C:\\temp\\file.txt")` | Mang cú pháp đặc thù Windows, không portable |
| `Path.of("/tmp/file.txt")` | Giả định POSIX và quyền ghi |
| `Path.of("reports", "file.txt")` | Dùng separator do filesystem provider |
| `tempDir.resolve("reports").resolve("file.txt")` | Portable và nằm trong temp root nếu input trusted |
| `tempDir.toUri()` | URI chuẩn cho path theo provider |
| `Files.createTempFile(tempDir,"part-",".txt")` | File tạm bên trong root được cấp |

Không viết `root.toString() + "\\\\" + name`. Trên Linux, `\` có thể là ký tự hợp lệ của tên file, không phải separator; trên Windows, “C:” và reserved names có ý nghĩa riêng. Hãy dùng `resolve`.

### Windows reserved names

Một filename có thể không hợp lệ trên Windows dù Linux cho phép, ví dụ `CON.txt`, `PRN.txt`, `AUX.txt`, `NUL.txt`, `COM1.txt`, `LPT1.txt`. Trong code demo phía dưới, validator từ chối những tên này để giữ tests portable. Đây chỉ là một phần của chính sách filename cho ứng dụng thật; Unicode normalization, case-insensitive collisions và long-path support còn cần cân nhắc.

### Unicode filename khác Unicode file content

Bài sẽ cho **Unicode trong nội dung file** (tiếng Việt và emoji), nhưng cố ý giới hạn filename thành ASCII một thành phần để dễ kiểm path traversal. Nếu sản phẩm phải chấp nhận tên tiếng Việt có dấu, cần chính sách Unicode normalization và collision detection theo filesystem thực, không phải chỉ thay regex một cách tùy tiện.

## 6. Charset và byte-level assertions

Một chuỗi `String` trong Java chứa text Unicode; file chứa bytes. UTF-8 chuyển các ký tự thành bytes có độ dài biến thiên:

~~~java
String value = "Xin chào 🌱";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);

Files.write(file, bytes);

assertArrayEquals(
        bytes, Files.readAllBytes(file));

assertEquals(
        value, Files.readString(
            file, StandardCharsets.UTF_8));
~~~

Với tiếng Việt và emoji, `value.length()` (UTF-16 code units) thường **khác** `bytes.length` (UTF-8 bytes). Đừng dùng `String.length()` làm expected file size.

### 6.1. Ghi/đọc charset rõ ràng

~~~java
Files.writeString(
    file, "Tiếng Việt có dấu",
    StandardCharsets.UTF_8);

String read = Files.readString(
    file, StandardCharsets.UTF_8);
~~~

Java 17 `Files.writeString/readString` overload không truyền charset dùng UTF-8 theo API, nhưng ghi charset tường minh vẫn làm file contract rõ ràng và giúp tránh nhầm với các API/versions khác vốn dùng platform default.

### 6.2. Không dùng default charset mù

~~~java
String text = new String(byteArray);
~~~

Nếu file được định nghĩa là UTF-8, hãy dùng:

~~~java
String text = new String(
    byteArray, StandardCharsets.UTF_8);
~~~

Java 17 không bảo đảm mọi process/locale có platform default charset giống nhau; và ngay cả với Java mới, một legacy file có thể quy định charset khác. Test nên encode/decode đúng **hợp đồng của file**, không đoán từ OS.

### 6.3. Wrong charset corruption

`Café` trong UTF-8 có ký tự `é` với bytes `C3 A9`. Đọc bằng ISO-8859-1, hai bytes đó trở thành hai ký tự `Ã©`, dẫn tới `CafÃ©`. Một test chủ động đọc sai rồi assert difference giúp người học hiểu vì sao **read có kết quả String** không đồng nghĩa **decode đúng**.

### 6.4. Malformed UTF-8

Bytes `C3 28` không tạo một chuỗi UTF-8 hợp lệ:

~~~java
Files.write(file, new byte[]{
    (byte) 0xC3, (byte) 0x28
});

assertThrows(
    MalformedInputException.class,
    () -> Files.readString(
        file, StandardCharsets.UTF_8));
~~~

`Files.readString` có thể ném `MalformedInputException` khi decoding strict. Các decoder/readers khác có thể thay ký tự lỗi bằng replacement char nếu cấu hình vậy. Với hợp đồng cấm bytes lỗi, hãy chọn strict decoding có chủ đích.

### 6.5. Text và binary

PDF/ZIP/JPEG/binary payload không nên convert tùy tiện qua `String`. Sử dụng `Files.readAllBytes`/`write`, stream I/O và kiểm bytes/checksum. Đừng “sửa” binary bằng cách ép UTF-8 hoặc ISO-8859-1.

## 7. Newline, BOM và file formatting

### LF khác CRLF

- `\n` = LF, thường một byte `0A` trong UTF-8.
- `\r\n` = CRLF, hai bytes `0D 0A`.
- `System.lineSeparator()` phụ thuộc runtime platform.

Nếu contract xuất file JSONL hoặc text dùng LF, viết `"\n"` một cách tường minh. Nếu định dạng yêu cầu native line ending, test dùng `System.lineSeparator()` thay vì hardcode Linux/Windows.

### BOM trong UTF-8

Một file có thể bắt đầu bằng bytes `EF BB BF`, tương ứng `U+FEFF`. Java `Files.readString(..., UTF_8)` không tự diễn giải BOM thành một quy tắc business “phải bỏ”, nên chuỗi có thể bắt đầu bằng `\uFEFF`. Ví dụ:

~~~java
Files.write(file, new byte[]{
    (byte) 0xEF, (byte) 0xBB,
    (byte) 0xBF, (byte) 'A'
});

String text = Files.readString(
    file, StandardCharsets.UTF_8);

assertEquals("\uFEFFA", text);
~~~

Khi contract quy định “UTF-8 không BOM”, test nên đọc bytes đầu và assert không có signature BOM. Khi contract cho phép BOM, cần xử lý có chủ đích. Không dùng `strip` như cơ chế chắc chắn loại `U+FEFF`, vì hành vi whitespace của Unicode không đồng nhất với BOM handling.

### Line readers có thể làm mất newline style

`Files.readAllLines` và `Files.lines` biểu diễn lines, không giữ nguyên mỗi line terminator. Nếu mục tiêu là kiểm CRLF vs LF, dùng `Files.readAllBytes` rồi so expected bytes; đừng chỉ so `List<String>` đã tách dòng.

### Streaming vs in-memory

`readAllBytes/readString` giữ file trong memory, thích hợp fixture nhỏ. Với file lớn, dùng `Files.newBufferedReader`, `Files.newInputStream`, `Files.lines` và đóng mọi resource đúng lúc:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(
            file, StandardCharsets.UTF_8)) {
    String first = reader.readLine();
    assertEquals("header", first);
}
~~~

Trên Windows, còn mở stream có thể khiến test cleanup fail vì file lock. Đừng dùng `Thread.sleep` để “chờ OS thả file” thay vì đóng resource đúng cách.

## 8. Spring Resource: classpath không đồng nghĩa filesystem file

Trong Spring Boot có các loại resource:

- `ClassPathResource`: dữ liệu thuộc classpath, có thể nằm trong directory hoặc JAR.
- `FileSystemResource`: dữ liệu nằm trên filesystem.
- `UrlResource`: dữ liệu truy cập qua URL/URI.
- `PathResource`: dựa trên NIO Path.
- `ByteArrayResource`: nguồn bytes in-memory trong test/libraries.

Một classpath fixture có thể nằm ở `src/main/resources/reports/header.txt` trong source tree và xuất hiện như file ở `build/resources/main` khi chạy test. Nhưng khi ứng dụng được đóng gói thành executable JAR, fixture có thể nằm **bên trong JAR**.

### 8.1. Pattern đúng

~~~java
Resource header =
    new ClassPathResource("reports/header.txt");

try (InputStream input = header.getInputStream()) {
    String text = new String(
        input.readAllBytes(),
        StandardCharsets.UTF_8);
}
~~~

`getInputStream()` hoạt động cho classpath resource được đóng gói đúng.

### 8.2. Pattern không portable

~~~java
File file = new ClassPathResource(
        "reports/header.txt").getFile();
~~~

Khi resource ở trong JAR, `getFile()` có thể ném `FileNotFoundException` vì resource không có standalone filesystem file. Thành công ở IDE/exploded classpath không chứng minh app đóng gói chạy đúng.

### 8.3. ResourceLoader

~~~java
Resource resource = resourceLoader.getResource(
        "classpath:reports/header.txt");
~~~

`ResourceLoader` nhận resource location và trả implementation phù hợp. Nếu dùng `file:` URI, nó có thể truy cập filesystem. **Không cho user input tùy ý quyết định resource URL/scheme** vì có thể mở ra local-file disclosure hoặc SSRF; khi resource location là untrusted data, áp dụng allowlist schemes/path cụ thể.

### 8.4. Copy fixture vào TempDir

~~~java
Resource source =
    new ClassPathResource("reports/header.txt");

Path copied = tempDir.resolve("header.txt");

try (InputStream in = source.getInputStream()) {
    Files.copy(in, copied);
}

assertEquals(
    "BÁO CÁO",
    Files.readString(
        copied, StandardCharsets.UTF_8).strip());
~~~

Bạn có thể chỉnh bản copy ở temp root mà không đụng fixture gốc. Đây là một pattern hữu ích cho CSV input, JSON fixture, template file, cấu hình XML, PDF hoặc sample archives.

## 9. Path traversal và overwrite: thiết kế test âm tính

Khi service nhận filename từ request/user, đừng tạo output trực tiếp như:

~~~java
Path output = root.resolve(userFileName);
Files.writeString(output, body);
~~~

Tên file `../secrets.txt` có thể ra ngoài root; trên Windows có thêm drive letters, UNC paths, backslashes và reserved names. Ngay cả khi `normalize().startsWith(root)` lexical pass, một **symbolic link trong cây thư mục** có thể trỏ ra ngoài.

### Nguyên tắc kiểm soát

1. Nếu nghiệp vụ chỉ cần tên file, **chỉ nhận basename**, không nhận full path.
2. Chọn allowlist ký tự/extension/chiều dài phù hợp.
3. Chặn `..`, separators, absolute paths, reserved names, control chars.
4. Dùng trusted root, `resolve`, `normalize` và kiểm containment.
5. Không dùng String prefix để kiểm path.
6. Dùng `CREATE_NEW` nếu contract là **không được ghi đè** output đã tồn tại.
7. Tách tên lưu trữ do server sinh với tên hiển thị do user cung cấp nếu cần.
8. Kiểm symlink/path races theo threat model; lexical checks không thể chống TOCTOU hoàn chỉnh.
9. Không cho process test đụng đường dẫn bên ngoài `@TempDir`.
10. Khi application sử dụng multi-tenant storage, kiểm ownership/tenant boundary ngoài filename validation.

### `CREATE_NEW` giúp gì?

~~~java
Files.writeString(
        target,
        body,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);
~~~

Nếu file hoặc symbolic link tại target đã tồn tại, phương thức có thể ném `FileAlreadyExistsException` thay vì xóa/truncate dữ liệu cũ. Semantics tạo file mới được provider áp dụng ở cấp filesystem; thao tác này **không tự làm cả quá trình ghi nội dung trở nên atomic**. Nếu ghi giữa chừng fail, target có thể có partial content.

### Symlink và root trusted

Trong bài runnable, filename chỉ được chọn trong một allowlist ASCII không có separators, root được caller tin cậy và file được tạo bằng `CREATE_NEW`. Nếu attacker có quyền thay đổi root hoặc tạo symlink trong parent directories, đây vẫn **không phải một secure filesystem sandbox tổng quát**. Production xử lý untrusted archives/uploads cần thư mục có quyền sở hữu rõ, descriptor-based safe traversal khi khả thi và race-aware file APIs.

## 10. Project đầy đủ: Java 17 + Spring Boot 3.3.5 + Gradle

Project minh họa một service Spring thật: đọc header từ classpath resource `reports/header.txt`, ghép với body Unicode và xuất file `.txt` vào một `Path root` do test truyền. Bộ kiểm thử tách thành:

- **JUnit NIO tests** cho `Path`, `Files`, charset, binary, copy/move và streams.
- **Service unit integration tests** dùng `DefaultResourceLoader` thật nhưng không khởi động ApplicationContext.
- **Resource boundary tests** kiểm classpath/file resources.
- **Spring Boot integration tests** với `@Autowired ReportExportService` và `@TempDir` riêng từng method.

### 10.1. File tree

~~~text
tempdir-resource-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/tempfiles/
    │   │   ├── TempFileApplication.java
    │   │   └── ReportExportService.java
    │   └── resources/reports/
    │       └── header.txt
    └── test/java/com/example/tempfiles/
        ├── NioTempDirTest.java
        ├── ReportExportServiceTest.java
        ├── ResourceBoundaryTest.java
        └── ReportExportServiceSpringBootTest.java
~~~

Gradle Wrapper scripts/JAR cần được tạo bằng Gradle phù hợp hoặc lấy từ repo. `gradle-wrapper.jar` là binary, không thể copy từ tài liệu Markdown.

### 10.2. settings.gradle

~~~groovy
rootProject.name = 'tempdir-resource-lab'
~~~

### 10.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` cung cấp Spring Core/DI/ResourceLoader. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Boot Test và assertions. NIO là API của JDK nên không cần dependency riêng. Không cần database, HTTP server, Testcontainers hoặc Docker.

### 10.4. src/main/java/com/example/tempfiles/TempFileApplication.java

~~~java
package com.example.tempfiles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TempFileApplication {

    public static void main(String[] args) {
        SpringApplication.run(TempFileApplication.class, args);
    }
}
~~~

Application root cùng package với service để component scanning tìm được `@Service`. `@SpringBootTest(webEnvironment=NONE)` chỉ cần Spring context và không mở HTTP port.

### 10.5. src/main/resources/reports/header.txt

~~~text
BÁO CÁO
~~~

File này cần lưu UTF-8. Editor có thể thêm một newline cuối file; service dùng `stripTrailing()` cho header để kết quả ghép ổn định. Khi production template phải giữ nguyên whitespace, **không** áp dụng strip tùy tiện.

### 10.6. src/main/java/com/example/tempfiles/ReportExportService.java

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    private static final Pattern SAFE_NAME =
            Pattern.compile(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,79}\\.txt");

    private static final Set<String> RESERVED =
            Set.of("CON", "PRN", "AUX", "NUL");

    private static final String HEADER_LOCATION =
            "classpath:reports/header.txt";

    private final ResourceLoader resourceLoader;

    public ReportExportService(ResourceLoader resourceLoader) {
        this.resourceLoader =
                Objects.requireNonNull(resourceLoader);
    }

    public Path export(
            Path root, String fileName, String body)
            throws IOException {

        Objects.requireNonNull(root, "root");
        Objects.requireNonNull(body, "body");
        validateFileName(fileName);

        Path base = root.toAbsolutePath().normalize();
        Files.createDirectories(base);

        // Root trong demo được caller cung cấp và tin cậy.
        base = base.toRealPath();

        Path target = base.resolve(fileName).normalize();
        if (!target.startsWith(base)) {
            throw new IllegalArgumentException(
                    "Output escapes export root");
        }

        Resource headerResource =
                resourceLoader.getResource(HEADER_LOCATION);

        String header;
        try (InputStream stream =
                headerResource.getInputStream()) {
            header = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).stripTrailing();
        }

        String contents = header + "\n" + body + "\n";

        // CREATE_NEW: không ghi đè existing file/link.
        return Files.writeString(
                target,
                contents,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
    }

    private static void validateFileName(
            String fileName) {

        if (fileName == null
                || !SAFE_NAME.matcher(fileName).matches()
                || fileName.contains("..")) {
            throw new IllegalArgumentException(
                    "Invalid report filename");
        }

        String stem = fileName.substring(
                0, fileName.length() - ".txt".length());

        String firstPart = stem.split("\\.", 2)[0]
                .toUpperCase(Locale.ROOT);

        if (RESERVED.contains(firstPart)
                || firstPart.matches("COM[1-9]|LPT[1-9]")) {
            throw new IllegalArgumentException(
                    "Reserved report filename");
        }
    }
}
~~~

### 10.7. Giải thích service

**Không giữ mutable root trong singleton.** `ReportExportService` là một Spring singleton nhưng `Path root` là parameter của `export`. Mỗi test có thể truyền `@TempDir` mới mà Spring context không cần khởi động lại.

**Đọc header từ classpath bằng InputStream.** Không gọi `resource.getFile()`, do đó app vẫn có thể đọc resource khi đóng gói JAR.

**UTF-8/LF explicit.** Service ghép `header + "\n" + body + "\n"` rồi viết với `UTF_8`. Test có thể so exact bytes trên cả Windows và Linux.

**Tên file có policy rõ.** Ví dụ chỉ chấp nhận một basename ASCII kết thúc `.txt`, không chứa `..`, không trùng tên thiết bị Windows. Nó từ chối `../escape.txt`, `C:\\temp\\...`, `sub/report.txt`, `report.csv` và tên bất hợp lệ.

**Output root được coi là trusted.** Code tạo root nếu chưa có, normalize, gọi `toRealPath` rồi resolve. Với root do `@TempDir` cấp, đây là hợp đồng phù hợp. Một root bị attacker điều khiển đòi security design sâu hơn.

**CREATE_NEW chống overwrite.** Khi file đã tồn tại, không truncate. Nếu I/O fail trong quá trình ghi, file output có thể vẫn tồn tại một phần; khi yêu cầu atomic export, thêm temp-write/atomic-move design.

## 11. NIO @TempDir tests: Java 17, JUnit Jupiter

**src/test/java/com/example/tempfiles/NioTempDirTest.java**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.*;

class NioTempDirTest {

    @TempDir
    Path workDir;

    @Test
    void injectedRootExistsAndIsDirectory() {
        assertTrue(Files.isDirectory(workDir));
        assertTrue(Files.isWritable(workDir));
    }

    @Test
    void methodParameterCanUseItsOwnTempDir(
            @TempDir Path separate) throws IOException {

        Path file = separate.resolve("note.txt");
        Files.writeString(file, "isolated",
                StandardCharsets.UTF_8);

        assertTrue(Files.isDirectory(separate));
        assertEquals("isolated",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void utf8RoundTripPreservesVietnameseAndEmoji()
            throws IOException {

        String text = "Tiếng Việt: Hà Nội, Cần Thơ 🌱\n";
        Path file = workDir.resolve("viet.txt");

        Files.writeString(file, text,
                StandardCharsets.UTF_8);

        assertEquals(text,
                Files.readString(file,
                        StandardCharsets.UTF_8));

        assertArrayEquals(
                text.getBytes(StandardCharsets.UTF_8),
                Files.readAllBytes(file));

        assertEquals(
                text.getBytes(StandardCharsets.UTF_8).length,
                Files.size(file));
    }

    @Test
    void nestedDirectoriesAndNormalizeWork()
            throws IOException {

        Path directory =
                workDir.resolve("reports/2026");
        Files.createDirectories(directory);

        Path target =
                directory.resolve("../final.txt")
                    .normalize();

        assertEquals(
                workDir.resolve("reports/final.txt"),
                target);
        assertTrue(target.startsWith(workDir));

        Files.writeString(target, "ready",
                StandardCharsets.UTF_8);

        assertEquals("ready",
                Files.readString(target,
                        StandardCharsets.UTF_8));
    }

    @Test
    void createTempFileIsInsideInjectedRoot()
            throws IOException {

        Path file = Files.createTempFile(
                workDir, "part-", ".csv");

        assertTrue(Files.exists(file));
        assertTrue(file.startsWith(workDir));

        Files.writeString(file,
                "id,name\n1,A\n",
                StandardCharsets.UTF_8);

        assertEquals(
                "id,name\n1,A\n",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void wrongCharsetCorruptsText()
            throws IOException {

        Path file = workDir.resolve("encoding.txt");
        Files.writeString(file, "Café",
                StandardCharsets.UTF_8);

        String wrong = Files.readString(
                file, StandardCharsets.ISO_8859_1);

        assertEquals("CafÃ©", wrong);
        assertNotEquals("Café", wrong);

        assertEquals("Café",
                Files.readString(file,
                        StandardCharsets.UTF_8));
    }

    @Test
    void malformedUtf8MustNotBeSilentlyAccepted()
            throws IOException {

        Path file = workDir.resolve("bad.txt");
        Files.write(file, new byte[]{
                (byte) 0xC3, (byte) 0x28
        });

        assertThrows(MalformedInputException.class,
                () -> Files.readString(
                    file, StandardCharsets.UTF_8));
    }

    @Test
    void binaryFileRoundTripUsesBytes()
            throws IOException {

        Path file = workDir.resolve("payload.bin");
        byte[] payload = {
                0x00, 0x01, (byte) 0xFF, 0x7F
        };

        Files.write(file, payload);

        assertArrayEquals(
                payload, Files.readAllBytes(file));
    }

    @Test
    void copyAndMovePreserveFileContents()
            throws IOException {

        Path source = workDir.resolve("source.txt");
        Path copy = workDir.resolve("copy.txt");
        Path moved = workDir.resolve("moved.txt");

        Files.writeString(source, "bản gốc",
                StandardCharsets.UTF_8);

        Files.copy(source, copy);
        Files.move(copy, moved);

        assertTrue(Files.exists(source));
        assertFalse(Files.exists(copy));
        assertTrue(Files.exists(moved));
        assertArrayEquals(
                Files.readAllBytes(source),
                Files.readAllBytes(moved));
    }

    @Test
    void filesLinesStreamIsAlwaysClosed()
            throws IOException {

        Path file = workDir.resolve("rows.txt");
        Files.writeString(file,
                "one\ntwo\nthree\n",
                StandardCharsets.UTF_8);

        List<String> lines;
        try (Stream<String> source =
                Files.lines(file, StandardCharsets.UTF_8)) {
            lines = source.toList();
        }

        assertEquals(
                List.of("one", "two", "three"), lines);
    }
}
~~~

### Vì sao các assertions đủ ý nghĩa?

- Không dựa vào tên temp root ngẫu nhiên, chỉ xác nhận nó là directory.
- Unicode text được kiểm hai hướng **String lẫn bytes**.
- `Files.size` được so với số bytes UTF-8, không phải `text.length()`.
- Directory nested được tạo trước khi ghi; `normalize` được kiểm lexical.
- `Files.createTempFile(workDir,...)` tạo file trong đúng root, không bên ngoài.
- Wrong charset test dùng `Café` để chứng minh mismatch có thể xảy ra dù không bị exception.
- Malformed UTF-8 test xác định chính sách strict.
- Binary test không decode bytes.
- Copy/move test kiểm file cũ/mới và content.
- `Files.lines` được đóng bằng try-with-resources trước khi `@TempDir` cleanup.

### Không bắt buộc ATOMIC_MOVE trên mọi filesystem

Trong test trên, `Files.move(copy, moved)` không yêu cầu atomic semantics vì mục tiêu chỉ là **content/relocation**. Nếu business contract cần atomic move, hãy dùng `StandardCopyOption.ATOMIC_MOVE` trong một test riêng và xử lý `AtomicMoveNotSupportedException` trên provider không hỗ trợ. Đừng biến một feature không được bảo đảm bởi filesystem thành giả định portable của toàn suite.

## 12. Kiểm service: dữ liệu UTF-8, traversal, duplicate và symlink

**src/test/java/com/example/tempfiles/ReportExportServiceTest.java**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.DefaultResourceLoader;

import static org.junit.jupiter.api.Assertions.*;

class ReportExportServiceTest {

    private final ReportExportService service =
            new ReportExportService(
                    new DefaultResourceLoader());

    @Test
    void writesHeaderAndBodyAsUtf8(
            @TempDir Path root) throws IOException {

        Path output = service.export(
                root, "report-01.txt",
                "Khách hàng: Đặng");

        assertTrue(output.startsWith(root.toRealPath()));
        String expected =
                "BÁO CÁO\nKhách hàng: Đặng\n";

        assertEquals(expected,
                Files.readString(
                    output, StandardCharsets.UTF_8));

        assertArrayEquals(
                expected.getBytes(StandardCharsets.UTF_8),
                Files.readAllBytes(output));
    }

    @Test
    void duplicateWriteFailsWithoutChangingOldContent(
            @TempDir Path root) throws IOException {

        Path output = service.export(
                root, "report.txt", "first");

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "report.txt", "second"));

        assertEquals(
                "BÁO CÁO\nfirst\n",
                Files.readString(
                    output, StandardCharsets.UTF_8));
    }

    @Test
    void rejectsParentTraversalAndSeparators(
            @TempDir Path root) {

        List<String> badNames = List.of(
                "../outside.txt",
                "sub/report.txt",
                "..\\windows.txt",
                "report..txt");

        for (String name : badNames) {
            assertThrows(
                IllegalArgumentException.class,
                () -> service.export(
                    root, name, "data"),
                "Should reject: " + name);
        }
    }

    @Test
    void rejectsAbsolutePath(
            @TempDir Path root) {

        String absolute = root
                .resolve("outside.txt")
                .toAbsolutePath()
                .toString();

        assertThrows(
            IllegalArgumentException.class,
            () -> service.export(
                root, absolute, "data"));
    }

    @Test
    void rejectsInvalidNamesAndWindowsDeviceNames(
            @TempDir Path root) {

        assertThrows(
            IllegalArgumentException.class,
            () -> service.export(
                root, null, "x"));

        for (String name : List.of(
                "", "bad name.txt",
                "CON.txt", "COM1.txt",
                "report.csv",
                ".hidden.txt",
                "report.txt/child")) {

            assertThrows(
                IllegalArgumentException.class,
                () -> service.export(
                    root, name, "x"),
                "Should reject: " + name);
        }
    }

    @Test
    void createsTrustedNestedRoot(
            @TempDir Path root) throws IOException {

        Path nested = root.resolve("reports/daily");
        Path output = service.export(
                nested, "daily.txt", "Đã xử lý");

        assertTrue(Files.isDirectory(nested));
        assertTrue(output.startsWith(
                nested.toRealPath()));

        assertEquals(
                "BÁO CÁO\nĐã xử lý\n",
                Files.readString(
                    output, StandardCharsets.UTF_8));
    }

    @Test
    void doesNotReplaceExistingSymbolicLink(
            @TempDir Path root) throws IOException {

        Path original = root.resolve("original.txt");
        Files.writeString(
                original, "untouched",
                StandardCharsets.UTF_8);

        Path link = root.resolve("alias.txt");

        try {
            Files.createSymbolicLink(link, original);
        } catch (IOException
                 | UnsupportedOperationException
                 | SecurityException unavailable) {

            Assumptions.assumeTrue(
                false,
                "OS or filesystem does not permit symlink");
        }

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "alias.txt", "hijack"));

        assertEquals(
                "untouched",
                Files.readString(
                    original, StandardCharsets.UTF_8));
    }

    @Test
    void rejectsNullBodyWithoutCreatingOutput(
            @TempDir Path root) {

        assertThrows(
            NullPointerException.class,
            () -> service.export(
                root, "null.txt", null));

        assertFalse(Files.exists(
                root.resolve("null.txt")));
    }
}
~~~

### Các ca âm tính bắt lỗi gì?

**Traversal và absolute path:** Nếu bỏ filename validation, một input như `../outside.txt` hoặc `sub/report.txt` có thể tạo path không mong muốn. Trong lab, cả separators POSIX/Windows đều bị policy từ chối trên mọi OS.

**Duplicate:** `CREATE_NEW` đảm bảo file cũ không bị ghi đè. Nếu developer đổi sang `Files.writeString(target, contents)` mặc định, test `duplicateWriteFailsWithoutChangingOldContent` phải đỏ.

**Device names:** Một filename có thể hợp lệ trên Linux nhưng không dùng được trên Windows. Test từ chối `CON.txt` và `COM1.txt` ở cấp ứng dụng, không đợi Windows filesystem báo lỗi.

**Symbolic link:** Nếu được OS cho tạo symlink trong TempDir, file target link đã tồn tại. `CREATE_NEW` phải từ chối ghi đè. Nếu Windows policy hoặc filesystem không hỗ trợ link, JUnit test **SKIPPED**, không báo rằng security policy đã được test đầy đủ.

**Null body:** Input programming error phải fail trước khi tạo file output. Điều này giúp ngăn file rỗng bị ghi bất ngờ.

### Vì sao không dùng mock ResourceLoader?

Unit test service dùng `new DefaultResourceLoader()`, nên nó thật sự đọc `classpath:reports/header.txt`. Một mock luôn trả một String header do test tự lập có thể khiến test pass dù path resource trong source đã đổi/mất. Bài này muốn kiểm **classpath resource boundary** nên dùng implementation Spring Core thật là hợp lý.

## 13. Kiểm Spring ClassPathResource, FileSystemResource và ResourceLoader

**src/test/java/com/example/tempfiles/ResourceBoundaryTest.java**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.DefaultResourceLoader;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.junit.jupiter.api.Assertions.*;

class ResourceBoundaryTest {

    @Test
    void copiesClasspathResourceIntoTempRoot(
            @TempDir Path root) throws IOException {

        Resource fixture = new ClassPathResource(
                "reports/header.txt");
        assertTrue(fixture.exists());

        Path copy = root.resolve("copy.txt");
        try (InputStream input = fixture.getInputStream()) {
            Files.copy(input, copy);
        }

        assertEquals("BÁO CÁO",
                Files.readString(
                    copy, StandardCharsets.UTF_8).strip());
    }

    @Test
    void filesystemResourceReadsTempFile(
            @TempDir Path root) throws IOException {

        Path file = root.resolve("note.txt");
        Files.writeString(
                file, "Tiếng Việt",
                StandardCharsets.UTF_8);

        Resource resource = new FileSystemResource(file);

        try (InputStream input = resource.getInputStream()) {
            assertEquals(
                "Tiếng Việt",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8));
        }
    }

    @Test
    void resourceLoaderResolvesClasspathAndFileUri(
            @TempDir Path root) throws IOException {

        ResourceLoader loader = new DefaultResourceLoader();

        Resource classpath = loader.getResource(
                "classpath:reports/header.txt");

        try (InputStream input = classpath.getInputStream()) {
            assertEquals(
                "BÁO CÁO",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).strip());
        }

        Path target = root.resolve("from-uri.txt");
        Files.writeString(
                target, "file uri",
                StandardCharsets.UTF_8);

        Resource fromFileUri = loader.getResource(
                target.toUri().toString());

        try (InputStream input = fromFileUri.getInputStream()) {
            assertEquals(
                "file uri",
                new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8));
        }
    }
}
~~~

### Tại sao không kiểm `getFile()` cho classpath fixture?

Classpath fixture tình cờ là một disk file khi chạy Gradle test; `getFile()` có thể pass. Nhưng khi app đóng gói một executable JAR, nó có thể không là standalone file. Test đúng hợp đồng là **mở `InputStream`** và đọc nội dung. Khi cần chắc chắn packaged-JAR behavior, thêm smoke test khởi động chính artifact.

### ResourceLoader không phải security sandbox

Nếu resource location đến từ HTTP request, không gọi `getResource(userLocation)` mù. Một input `file:///etc/passwd` hoặc `https://unknown.example/...` có thể mở đường đọc dữ liệu không cho phép tùy implementation và quyền runtime. Cố định prefix/scheme/path theo business contract hoặc chọn type resource trực tiếp từ trusted sources.

## 14. Kiểm Spring Boot bean wiring với @TempDir

**src/test/java/com/example/tempfiles/ReportExportServiceSpringBootTest.java**

~~~java
package com.example.tempfiles;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = TempFileApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReportExportServiceSpringBootTest {

    @Autowired
    private ReportExportService service;

    @Test
    void bootInjectsRealResourceLoaderAndExports(
            @TempDir Path root) throws IOException {

        assertNotNull(service);

        Path file = service.export(
                root, "boot.txt", "Đơn hàng: 42");

        assertEquals(
                "BÁO CÁO\nĐơn hàng: 42\n",
                Files.readString(
                    file, StandardCharsets.UTF_8));

        assertTrue(file.startsWith(root.toRealPath()));
    }

    @Test
    void singletonServiceDoesNotReusePathAcrossTests(
            @TempDir Path root) throws IOException {

        Path file = service.export(
                root, "same.txt", "one");

        assertThrows(
            FileAlreadyExistsException.class,
            () -> service.export(
                root, "same.txt", "two"));

        assertEquals(
                "BÁO CÁO\none\n",
                Files.readString(
                    file, StandardCharsets.UTF_8));
    }
}
~~~

### Vì sao @SpringBootTest và @TempDir kết hợp được?

`@SpringBootTest` tạo Spring ApplicationContext và inject `ReportExportService` từ component scanning. `@TempDir` được JUnit tạo cho mỗi test method. Service singleton **không lưu Path trong field**, nên cùng một bean có thể ghi vào root A ở method 1 và root B ở method 2, không phụ thuộc thứ tự.

Điều này khác thiết kế có property root được bind vào constructor một lần: thay `demo.export.root` giữa test methods **không tự thay** field của singleton vì Spring context có thể cache. Khi output root bắt buộc được inject từ configuration, hãy chọn class-scoped root ổn định và quản lý context lifetime, hoặc dùng test-specific bean/configuration.

### Đây có phải end-to-end filesystem test không?

Nó thực sự đọc classpath resource qua Spring bean và ghi local filesystem trong JUnit root. Nó **không** kiểm network FS, production volume mounts, Docker overlay permissions hoặc S3. Hợp đồng đến đâu thì assertions chứng minh đến đó.

## 15. Tổng hợp test cases và kết quả dự kiến

Bộ source có **23 phương thức `@Test`**:

| Lớp | Số test | Phạm vi |
| --- | ---: | --- |
| `NioTempDirTest` | 10 | Directory/Path/charset/binary/copy-move/stream |
| `ReportExportServiceTest` | 8 | Export UTF-8, filenames, duplicate, symlink |
| `ResourceBoundaryTest` | 3 | ClassPathResource/FileSystemResource/ResourceLoader |
| `ReportExportServiceSpringBootTest` | 2 | Spring DI và file I/O theo từng @TempDir |
| **Tổng** | **23** | Tập trung vào I/O correctness và isolation |

Các ví dụ là source được thiết kế, **chưa thực thi Gradle/JUnit tại môi trường này**. Khi chạy, expected là 23 tests thành công trên default filesystem hỗ trợ; symlink test có thể được JUnit đánh dấu skipped nếu OS không cho tạo link.

### Lệnh chạy

Cần JDK 17, Gradle Wrapper và khả năng tải Maven dependencies lần đầu. Không cần Docker.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng một class:

~~~bash
./gradlew test --tests 'com.example.tempfiles.NioTempDirTest'
./gradlew test --tests 'com.example.tempfiles.ReportExportServiceTest'
./gradlew test --tests 'com.example.tempfiles.ResourceBoundaryTest'
./gradlew test --tests 'com.example.tempfiles.ReportExportServiceSpringBootTest'
~~~

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`.

Báo cáo thông thường:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.tempfiles.NioTempDirTest.xml
    ├── TEST-com.example.tempfiles.ReportExportServiceTest.xml
    ├── TEST-com.example.tempfiles.ResourceBoundaryTest.xml
    └── TEST-com.example.tempfiles.ReportExportServiceSpringBootTest.xml
~~~

Nếu Gradle báo `UP-TO-DATE` hoặc `FROM-CACHE`, không mặc định kết luận tests vừa được thực thi. Khi chẩn đoán:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu chưa có Wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó commit Wrapper files theo policy repo. Code test không có `System.out.println`, nên không có stdout nghiệp vụ cố định; paths/Gradle logs phụ thuộc môi trường.

## 16. Sửa một dòng, test nào sẽ đỏ?

Mutation testing thủ công có thể đánh giá sức mạnh của tests:

| Thay đổi cố ý trong nhánh thử nghiệm | Test dự kiến phát hiện |
| --- | --- |
| Đổi UTF-8 sang ISO-8859-1 khi ghi report | `writesHeaderAndBodyAsUtf8` |
| Bỏ header classpath, chỉ ghi body | Service/Boot content assertions |
| Bỏ `CREATE_NEW` và cho phép overwrite | `duplicateWriteFailsWithoutChangingOldContent` |
| Bỏ filename policy | Traversal/absolute/reserved-name tests |
| Cho phép `COM1.txt` | Device-name negative test |
| Thay `"\n"` bằng `System.lineSeparator()` | Exact content test trên môi trường CRLF |
| Đổi resource path thành không tồn tại | Service/resource tests |
| Bỏ `@Service` | Spring Boot injection test |
| Dùng `ClassPathResource.getFile` thay InputStream | Có thể chỉ fail khi packaged-JAR smoke test |
| Đổi file output thành file ở working directory | Path containment assertions |
| Để `Files.lines` không đóng | Có thể gây cleanup failure, nhất là Windows |

Sau khi chứng minh test đỏ, **hoàn nguyên** thay đổi. Không đưa code cố ý có path traversal vào production hoặc CI dùng thư mục thật.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Parent folder chưa tạo | `Files.createDirectories` |
| `FileAlreadyExistsException` | `CREATE_NEW` gặp existing file/link | Dùng filename mới hoặc assert overwrite policy |
| `AccessDeniedException` | Thiếu quyền hoặc file locked | Kiểm permissions/open handles/volume |
| `InvalidPathException` | OS không chấp nhận filename | Validate input portable |
| `MalformedInputException` | Bytes không hợp charset | Kiểm encoding, BOM, fixture |
| Tiếng Việt thành `Ã©`/ký tự lạ | Decode sai charset | Explicit UTF-8 |
| `ClassPathResource.getFile()` fail trong JAR | Resource nằm trong archive | `getInputStream()` |
| Test pass IDE nhưng fail Gradle | Working directory khác | @TempDir + classpath resource |
| Test pass riêng nhưng fail cả suite | Shared root/static state/files | Per-method @TempDir |
| Cleanup fail trên Windows | InputStream/Reader/Files.lines chưa đóng | Try-with-resources |
| File output có backslash trong tên trên Linux | Ghép path bằng string Windows | `Path.resolve` |
| File chứa CRLF thay LF | Dùng System.lineSeparator | Cố định newline contract |
| `Files.size` khác `text.length` | UTF-8 dùng bytes khác UTF-16 chars | So raw UTF-8 bytes |
| File tồn tại nhưng nội dung cũ | Shared filename hoặc write không thực thi | Assert content, CREATE_NEW |
| Symlink test skipped | OS thiếu quyền hỗ trợ symlink | Dedicated runner cho security coverage |
| normalize vẫn cho đi ngoài qua symlink | Lexical validation chưa đủ | Trusted root/secure directory operations |
| Atomic move không hỗ trợ | Provider không bảo đảm | Test capability và policy fallback rõ |
| Test rò files sau failure | Cleanup=NEVER/ON_SUCCESS | Chỉ bật khi debug, đóng resources |
| Spring singleton giữ root đã bị xóa | Config được bind một lần, context cache | Pass root per invocation hoặc quản lý context |
| Large file làm test OOM | readAllBytes/readString không streaming | Stream/chunk và giới hạn size |
| NFS/volume khác local TempDir | Semantics lock/atomic/case khác | Integration test trên deployment-like FS |
| Không đọc được fixture sau packaging | Wrong resource path/packaging | Kiểm JAR contents + InputStream |
| Test xóa nhầm user files | Hardcode path/recursive delete ngoài root | Giới hạn mọi deletion trong TempDir |
| User-supplied resource URL có rủi ro | ResourceLoader đọc scheme tùy ý | Allowlist schemes/paths, không tin client |

### Quy trình debug

1. Xác định temp root do JUnit cung cấp và output path thực tế.
2. Kiểm root tồn tại và có quyền read/write.
3. Kiểm filename validation và parent creation.
4. Kiểm path ghép bằng `resolve` không phải string.
5. Kiểm charset ở **cả** read và write.
6. Kiểm BOM/newline nếu body khác expected.
7. Kiểm classpath resource bằng `getInputStream()` và tên resource đúng.
8. Kiểm readers/streams đã close.
9. Kiểm shared root/test parallelism.
10. Kiểm Spring context caching nếu root được inject vào singleton.
11. Kiểm filesystem semantics (symlink, atomic move, case, permissions).
12. Không dùng `Thread.sleep` để che lỗi I/O/cleanup.
13. Không xóa file bên ngoài test sandbox để “thử lại”.
14. Nếu app đóng gói JAR khác dev classpath, thêm packaged smoke test.

## 18. Những trường hợp nâng cao trong dự án thực

### 18.1. Atomic file export

`CREATE_NEW` bảo vệ khỏi overwrite nhưng không đảm bảo ghi hoàn toàn. Với file cần tính all-or-nothing, một mẫu là:

1. Tạo một temp file **cùng thư mục đích**.
2. Ghi bytes rồi đóng OutputStream.
3. Nếu cần durability, dùng FileChannel/force theo filesystem contract.
4. Move temp sang target với `ATOMIC_MOVE` khi provider hỗ trợ.
5. Quy định overwrite/no-overwrite rõ ràng; tránh âm thầm replace.
6. Cleanup temp file khi có exception, giới hạn đúng trusted root.
7. Test failure injection trước và sau move, kiểm target không chứa dữ liệu dở.

Không coi `ATOMIC_MOVE` được hỗ trợ trên mọi NFS/container overlay filesystem.

### 18.2. Zip Slip

Khi giải nén ZIP vào filesystem, entry có thể tên `../../secrets.txt`. Test nên dùng một ZIP fixture cô lập, giải nén dưới `@TempDir`, normalize/check target, giới hạn total uncompressed size, file count và symlinks. Không giải nén file không tin cậy vào source tree hoặc home directory chỉ để thử.

### 18.3. Permission/ACL

POSIX attributes không được hỗ trợ trên mọi filesystem. Khi muốn test `chmod 600`, trước hết kiểm `FileStore.supportsFileAttributeView("posix")` và chỉ chạy ở runner phù hợp. Không dùng kết quả skip trên Windows làm bằng chứng permission policy đúng.

### 18.4. File size lớn

Đừng `readAllBytes` một file vài GB trong test. Dùng stream + hash/checksum, `Files.newBufferedReader` hoặc `FileChannel` và giới hạn kích thước, thời gian, disk usage. Khi parser cần kiểm malformed data, dùng fixture nhỏ nhưng đại diện đúng.

### 18.5. Unicode filename normalization

Hai filename nhìn giống nhau có thể chứa Unicode codepoint sequences khác nhau, đặc biệt trên macOS filesystems. Nếu ứng dụng cho user chọn tên file Unicode, quyết định NFC/NFD, case folding và collision policy. Lab không tự khẳng định filename validator ASCII là giải pháp cho mọi bài toán i18n.

### 18.6. Server-generated storage name

Đối với upload untrusted, cách an toàn thường là **server sinh storage ID/filename**, còn tên gốc chỉ là metadata hiển thị đã sanitize. Không cho client cung cấp full local path. Thêm test xác minh tenant A không thể thao tác file của tenant B ngay cả khi đoán được ID.

### 18.7. Resource trong packaged Spring Boot JAR

Unit/Gradle tests có thể đọc `build/resources/main/...`, không có JAR nesting. Với yêu cầu production, build `bootJar` rồi chạy một smoke path dùng `Resource.getInputStream()`, xác minh file thực sự đóng gói và đọc được. Tránh dựa trên `ClassPathResource.getFile()` chỉ vì exploded classpath pass.

### 18.8. Spring MVC multipart

`MockMultipartFile`/`MockMvc.multipart(...)` kiểm boundary HTTP binding; service lưu file nên được test riêng với `@TempDir`. Không coi việc controller chấp nhận upload là bằng chứng storage path validation đúng. Cần test filename, size, MIME sniffing theo policy, empty file, overwrite và filesystem errors.

### 18.9. Cloud object storage

`@TempDir` không mô phỏng đầy đủ S3/GCS/blob store: storage keys, ACL, eventual consistency, versioning và multipart semantics khác NIO. Có thể dùng storage abstraction + unit mocks, rồi integration tests với emulator hoặc sandbox đã được cấp quyền. Đừng dùng local file test để tuyên bố cloud storage end-to-end pass.

### 18.10. Caching và timestamp

Filesystem modification time granularity thay đổi theo OS/provider. Tránh assert exact nanoseconds hay dùng `Thread.sleep` để buộc mtime khác. Nếu business dùng timestamp, inject `Clock` cho business metadata; chỉ test filesystem mtime trong runner tương thích nếu đó là hợp đồng.

## 19. So sánh các lựa chọn test

| Công cụ | Phù hợp | Không bảo đảm |
| --- | --- | --- |
| `@TempDir` | Local file I/O thật, tự cleanup | Cloud storage/NFS semantics |
| `Files.createTempDirectory` | Code cần tạo temp dir chủ động | Test phải tự cleanup |
| `Files.createTempFile` | Một file tạm trong root | Không thay thế fixture root |
| `Path`/`Files` | Test bytes, paths, metadata | Không tự bảo vệ untrusted user paths |
| `ClassPathResource` | Fixture read-only từ classpath/JAR | Không phải writable test output root |
| `FileSystemResource` | File đã tạo trên filesystem | Không auto-sanitize filenames |
| `ResourceLoader` | Giải quyết nhiều resource schemes | Không tự áp dụng security allowlist |
| Mockito mock Storage | Unit business rules nhanh | Không kiểm encoding/locks/permissions |
| `@SpringBootTest` + `@TempDir` | Bean DI + local file I/O | Không chứng minh Docker volume/S3 |
| Testcontainers filesystem | Mounted container volumes | Có hạ tầng Docker/lifecycle riêng |

Không buộc mọi unit test khởi động Spring context. Path/charset/byte handling nên được kiểm bằng JUnit thuần trước; chỉ bổ sung `@SpringBootTest` khi bean wiring/configuration/resource integration thực sự là một phần của hợp đồng.

## 20. Bài tập thực hành

**Bài A — field vs parameter:** Viết hai test dùng `@TempDir Path` dưới dạng field và method parameter. Giải thích setup/cleanup scope, không assert exact path name.

**Bài B — UTF-8:** Tạo file chứa `Tôi học Spring Boot 🌱`, đọc với UTF-8 và so bytes. Giải thích vì sao `String.length` khác `Files.size`.

**Bài C — encoding sai:** Ghi `Café` UTF-8, đọc ISO-8859-1 và xác nhận khác nhau. Sau đó sửa read charset.

**Bài D — malformed bytes:** Ghi `C3 28` rồi assert `MalformedInputException` khi đọc UTF-8.

**Bài E — BOM:** Ghi `EF BB BF 41`, đọc UTF-8 và xác minh có U+FEFF. Thiết kế policy reject/strip theo contract.

**Bài F — newline:** Test exact LF bytes và thay code dùng `System.lineSeparator()` trên hai OS; xác định expected contract.

**Bài G — path normalize:** Dùng `root.resolve("a/../b.txt").normalize()`. Giải thích lexical vs real path và symlink limitation.

**Bài H — traversal:** Thử `../escape.txt` và `..\\windows.txt` qua service; bảo đảm exception trước khi tạo file.

**Bài I — Windows names:** Thử `CON.txt`, `COM1.txt`, `LPT1.txt` và xác nhận policy từ chối trên cả Linux.

**Bài J — duplicate:** Gọi export hai lần cùng filename. Test thứ hai phải throw; file đầu không bị truncate.

**Bài K — symlink:** Nếu OS hỗ trợ, tạo symlink rồi thử export cùng tên. Khi không hỗ trợ, skip có lý do, không claim security coverage đã đầy đủ.

**Bài L — classpath:** Copy `reports/header.txt` qua `getInputStream()` vào TempDir. Không dùng `getFile()`.

**Bài M — packaged JAR:** Chạy smoke test từ fat JAR để xác minh resource vẫn đọc được, không chỉ Gradle expanded classpath.

**Bài N — ResourceLoader:** Kiểm `classpath:` và `file:` URI từ root riêng, không cho untrusted input chọn scheme.

**Bài O — File streams:** Dùng `Files.lines` trong try-with-resources và quan sát hậu quả khi quên close trong Windows runner.

**Bài P — static shared root:** Tạo static @TempDir và hai test cùng tên file; quan sát conflict. Đổi về instance/method scope.

**Bài Q — Spring singleton:** Để service nhận Path theo method; kiểm mỗi @SpringBootTest method dùng root mới mà không đổi singleton mutable state.

**Bài R — atomic export:** Thiết kế temp-write + move, kiểm behavior khi write fail giữa chừng; không giả định mọi provider hỗ trợ ATOMIC_MOVE.

**Bài S — permissions:** Trên POSIX runner thích hợp, kiểm read-only directory, file attributes và cleanup khi bị denied. Không ép Windows pass.

**Bài T — ZIP Slip:** Test archive có `../` entry trong isolated TempDir, bảo đảm extractor không ghi ra ngoài trusted root.

**Bài U — unicode filenames:** Thiết kế validator hỗ trợ NFC/NFD và collision trên filesystem khác nhau; thêm OS matrix tests.

**Bài V — CI:** Chạy full suite Windows + Linux, so sánh những tests skipped vì symlink với các tests pass; không coi skipped như security guarantee.

## 21. Checklist trước khi merge file tests

- [ ] Root test do `@TempDir` cấp, không hardcode thư mục toàn cục?
- [ ] Không ghi ngược vào `src/main/resources` hay `src/test/resources`?
- [ ] Sử dụng JUnit Jupiter `@TempDir` với `Path`/`File` hợp lệ?
- [ ] Instance/method scope tránh shared state khi chạy parallel?
- [ ] Parent directories được tạo khi cần?
- [ ] Ghép path bằng `resolve` thay separators thủ công?
- [ ] Dùng `normalize` và kiểm containment khi filename đến từ input?
- [ ] Không coi lexical path check là security sandbox hoàn chỉnh?
- [ ] Có positive và negative filename/path tests (traversal, absolute, Windows separators, reserved names)?
- [ ] Overwrite policy (`CREATE_NEW`/replace/truncate) rõ và được kiểm?
- [ ] UTF-8 được chỉ định ở mọi boundary đọc/ghi text?
- [ ] Có fixture tiếng Việt/emoji để bắt encoding lỗi?
- [ ] Kiểm raw bytes khi hợp đồng bao gồm newline/BOM/binary?
- [ ] Không giả định String.length bằng file size?
- [ ] Có case malformed bytes và wrong charset?
- [ ] Classpath resource đọc bằng `getInputStream`, tránh `getFile` cho packaged JAR?
- [ ] ResourceLoader location không cho user điều khiển scheme/đường dẫn tùy ý?
- [ ] Mọi InputStream/Reader/Files.lines/Files.walk được đóng?
- [ ] Symlink/permissions/atomic move tests có OS/provider strategy phù hợp?
- [ ] Spring context caching không giữ root đã bị JUnit dọn?
- [ ] Không mutate `System.setProperty` toàn JVM giữa test methods để đổi root?
- [ ] Test output không dùng directory của user hoặc source tree?
- [ ] Disk cleanup không recursive-delete ngoài root được cấp?
- [ ] Với production cloud/NFS, có integration test đúng backend?
- [ ] Với packaged JAR, có smoke test resource packaging?
- [ ] Test report cho thấy các tests thực sự chạy, không chỉ Gradle task cached?

## 22. Tài liệu tham khảo

- [JUnit 5.10 — TempDirectory Extension](https://docs.junit.org/5.10.0/user-guide/index.html): scope, fields, method parameter injection, cleanup modes.
- [JUnit Jupiter 5.10 — TempDir API](https://junit.org/junit5/docs/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): supported targets, lifecycle và cleanup.
- [Java 17 — java.nio.file.Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): resolve/normalize/startsWith/toRealPath.
- [Java 17 — java.nio.file.Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): readString/writeString, createTempFile, copy/move, streaming.
- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, ISO-8859-1.
- [Java 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE_NEW, WRITE và overwrite semantics.
- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): ResourceLoader, ClassPathResource, FileSystemResource và JAR.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest và test context lifecycle.
- [JUnit Jupiter 5.10 — Assertions/Assumptions](https://docs.junit.org/5.10.0/user-guide/index.html): assertThrows, Assumptions và tests theo OS.

**Ghi nhớ:** Trong Spring Boot testing, `@TempDir` giúp giữ file I/O trong test-owned root; `Path`/`Files` giúp viết code portable; `UTF_8` tường minh bảo vệ tiếng Việt và bytes; `Resource.getInputStream()` dùng cho classpath/JAR fixture; và negative assertions bảo vệ path/overwrite security policy. Chọn đúng scope của temp root, đóng streams và phân biệt kết quả local filesystem test với production storage guarantees.
