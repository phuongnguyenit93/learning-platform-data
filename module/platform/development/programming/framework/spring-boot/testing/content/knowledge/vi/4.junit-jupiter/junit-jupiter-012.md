# @TempDir cho tài nguyên tạm và dọn dữ liệu sau test

## 1. Vì sao kiểm thử cần thư mục tạm?

Một ứng dụng Java/Spring Boot thường đọc hoặc ghi file: xuất báo cáo CSV, tạo PDF, xử lý file upload, giải nén ZIP, lưu ảnh trung gian, ghi log, tạo file cấu hình hoặc kiểm tra cơ chế import/export. Nếu bài test ghi trực tiếp vào thư mục của dự án, ổ đĩa người phát triển hoặc đường dẫn sản xuất, nó có thể:

- Để lại file sau mỗi lần chạy và làm kết quả các lần sau phụ thuộc trạng thái cũ.
- Ghi đè dữ liệu thật hoặc file của test chạy đồng thời.
- Thất bại trên máy CI vì đường dẫn tuyệt đối khác nhau hoặc thiếu quyền.
- Phải tự viết cleanup dễ sót khi assertion ném lỗi.

JUnit Jupiter cung cấp **`@TempDir`** (package `org.junit.jupiter.api.io`). Extension tích hợp sẵn tạo một **thư mục tạm** cho test, cung cấp đường dẫn của thư mục đó và **tự dọn nội dung khi hết phạm vi** theo cấu hình cleanup.

Tư duy đúng: test chỉ ghi dữ liệu thuộc phạm vi do `@TempDir` cấp; assert **nội dung và hành vi file khi test đang chạy**; để JUnit xử lý vòng đời của thư mục khi test kết thúc.

### Khi nào @TempDir hữu ích?

| Tình huống | Sử dụng thư mục tạm |
| --- | --- |
| Export một file báo cáo | Ghi file vào `tempDir.resolve("report.csv")` rồi assert nội dung |
| Import từ file | Tạo file dữ liệu mẫu trong thư mục tạm, sau đó gọi service đọc |
| Giải nén hoặc sinh nhiều file | Tạo thư mục con trong `tempDir`, assert cấu trúc và nội dung |
| Kiểm tra lỗi đầu vào | Xác nhận không tạo file nếu dữ liệu không hợp lệ |
| Kiểm thử giao tiếp với filesystem thực | Dùng API `java.nio.file.Files` trên thư mục được quản lý, tránh mock toàn bộ thao tác file |

`@TempDir` **không tự tạo file báo cáo** và cũng không làm thay phần assertion: nó chỉ cấp và quản lý **thư mục gốc tạm**. Chính test hoặc code được thử phải tạo file/thư mục con bên trong.

## 2. @TempDir hoạt động như thế nào?

Khi phát hiện `@TempDir` trên một vị trí được hỗ trợ, JUnit Jupiter dùng extension `TempDirectory` để tạo thư mục tạm và tiêm đối tượng trỏ tới thư mục đó. Hai kiểu được hỗ trợ là:

- **`java.nio.file.Path`** — lựa chọn thường nên dùng với Java 17+ và các API `Files`.
- **`java.io.File`** — hữu ích khi mã cũ cần `File`; có thể chuyển bằng `file.toPath()`.

Ví dụ đặt annotation trực tiếp tại tham số của test:

~~~java
@Test
void writesText(@TempDir Path tempDir) throws IOException {
    Path file = tempDir.resolve("note.txt");
    Files.writeString(file, "Hello test", StandardCharsets.UTF_8);

    assertTrue(Files.exists(file));
    assertEquals("Hello test", Files.readString(file, StandardCharsets.UTF_8));
}
~~~

Đây là **một phương thức minh họa nằm bên trong lớp test**, cần import `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.io.TempDir`, `java.nio.file.Path`, `Files`, `IOException`, `StandardCharsets` và các assertion JUnit. JUnit cấp sẵn `tempDir` khi gọi test.

Thư mục thực tế có thể mang tên ngẫu nhiên và nằm ở vùng tạm của hệ điều hành hoặc filesystem được cấu hình. **Đừng hard-code đường dẫn** như `/tmp/report-test` hay `C:\temp\my-test`, và đừng assert tên vật lý của thư mục. Chỉ làm việc thông qua `Path` JUnit cung cấp.

### Vòng đời bình thường của một test

~~~text
JUnit tạo thư mục tạm
        ↓
Tiêm @TempDir Path/File
        ↓
@BeforeEach và các bước chuẩn bị test
        ↓
@Test ghi/đọc file và chạy assertions
        ↓
@AfterEach và các bước teardown test
        ↓
Hết phạm vi @TempDir → JUnit dọn đệ quy (mặc định)
~~~

Đây là sơ đồ khái quát; thứ tự callback nội bộ còn có các extension khác. Điều quan trọng là **JUnit dọn ở cuối phạm vi**, nên test có thể đọc file sau khi vừa tạo để kiểm tra nội dung. Không viết assertion `assertFalse(Files.exists(tempDir))` ngay trong thân `@Test` để thử việc cleanup: tại thời điểm đó thư mục vẫn đang phục vụ test.

## 3. Ba cách tiêm thư mục: tham số, instance field, static field

### Cách A — Tham số của test: rõ nhu cầu từng ca

~~~java
@Test
void createsInputFile(@TempDir Path tempDir) throws IOException {
    Path input = tempDir.resolve("input.txt");
    Files.writeString(input, "sample", StandardCharsets.UTF_8);
    assertEquals("sample", Files.readString(input, StandardCharsets.UTF_8));
}
~~~

Điểm mạnh: nhìn vào chữ ký phương thức là biết test có làm việc với file. Thích hợp nếu chỉ một vài test trong lớp cần thư mục tạm. Với nhiều tham số có `@TempDir`, các khai báo riêng có thể nhận những thư mục riêng; không tự giả định chúng chỉ đến cùng một vị trí.

### Cách B — Instance field: dùng cùng thư mục trong setup, test và teardown

~~~java
@TempDir
Path tempDir;

@BeforeEach
void prepare() throws IOException {
    Files.writeString(tempDir.resolve("config.txt"), "mode=test");
}

@Test
void readsPreparedFile() throws IOException {
    assertEquals("mode=test", Files.readString(tempDir.resolve("config.txt")));
}
~~~

Đây là **đoạn trích đặt trong một lớp test**, cần import JUnit và Java NIO. Với test instance lifecycle mặc định `PER_METHOD`, mỗi test thông thường có một instance riêng, nên instance field này phục vụ fixture của lượt test đó. Đây cũng là cách hữu ích nếu `@AfterEach` cần kiểm tra hoặc đóng tài nguyên file có liên quan đến cùng thư mục.

Trường gắn `@TempDir` phải là trường thích hợp để JUnit tiêm giá trị (không phải `final`, không gán sẵn một path tùy ý). Không tự tạo một `Path` rồi mong JUnit tự dọn thư mục đó.

### Cách C — Static field: thư mục được chia sẻ ở cấp lớp

~~~java
@TempDir
static Path sharedTempDir;
~~~

Với một trường `static`, thư mục thuộc phạm vi dùng chung của lớp test. Có thể chuẩn bị fixture dùng chung trong `@BeforeAll` và để JUnit dọn ở cuối phạm vi lớp, thay vì cuối từng phương thức.

Điều này chỉ nên dùng cho dữ liệu **không bị các test sửa gây ảnh hưởng lẫn nhau**. Nếu hai test cùng tạo `sharedTempDir.resolve("result.txt")`, chúng có thể ghi đè nhau hoặc gây lỗi khi chạy song song. Với test cần ghi file, ưu tiên tham số hoặc instance field để cô lập.

**Cẩn thận với `@TestInstance(PER_CLASS)`:** các test có thể cùng dùng một instance và state của instance đó. Không giả định chỉ vì một field không `static` thì mọi test luôn có dữ liệu hoàn toàn độc lập nếu đã đổi test instance lifecycle. Khi cần phạm vi per-invocation rõ ràng, dùng tham số `@TempDir` trực tiếp trên mỗi test.

## 4. Ví dụ hoàn chỉnh: kiểm thử service xuất file bằng Java 17 + JUnit Jupiter

Xây dựng một service đơn giản: với dữ liệu hợp lệ, tạo `report.txt` dưới thư mục được truyền vào; với nội dung trống, từ chối mà không sinh file. Ta muốn test logic xuất file **trên filesystem thật**, nhưng không ghi ra ngoài vùng tạm.

**Tệp `src/main/java/com/example/testing/ReportWriter.java`:**

~~~java
package com.example.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReportWriter {
    public Path write(Path outputDirectory, String content) throws IOException {
        Objects.requireNonNull(outputDirectory, "outputDirectory");

        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("Report content must not be blank");
        }

        Path output = outputDirectory.resolve("report.txt");
        Files.writeString(output, content, StandardCharsets.UTF_8);
        return output;
    }
}
~~~

`ReportWriter` nhận `Path` từ bên ngoài thay vì tự chọn một thư mục hệ thống cố định. Điều này làm code có thể kiểm thử dễ dàng, và cũng hữu ích trong ứng dụng thực tế khi nơi lưu được quyết định bởi cấu hình.

**Tệp `src/test/java/com/example/testing/ReportWriterTest.java`:**

~~~java
package com.example.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReportWriterTest {
    @TempDir
    Path tempDir;

    private ReportWriter writer;

    @BeforeEach
    void setUp() {
        writer = new ReportWriter();
    }

    @Test
    void write_whenContentIsValid_createsFileInsideTempDir() throws IOException {
        // Arrange: tempDir là thư mục JUnit đã tạo;
        // writer được chuẩn bị bởi @BeforeEach.
        String content = "Bao cao kiem thu\n";

        // Act
        Path generated = writer.write(tempDir, content);

        // Assert
        assertEquals(tempDir.resolve("report.txt"), generated);
        assertTrue(Files.exists(generated));
        assertEquals(content, Files.readString(generated, StandardCharsets.UTF_8));
    }

    @Test
    void write_whenContentIsBlank_throwsWithoutCreatingFile() {
        // Act + Assert: service từ chối đầu vào trống.
        assertThrows(
                IllegalArgumentException.class,
                () -> writer.write(tempDir, "   ")
        );

        // Không được tạo file sau khi từ chối.
        assertFalse(Files.exists(tempDir.resolve("report.txt")));
    }

    @Test
    void write_whenNestedDirectoryExists_createsFileThere() throws IOException {
        Path nested = Files.createDirectories(
                tempDir.resolve("exports").resolve("daily")
        );

        Path generated = writer.write(nested, "Daily\n");

        assertEquals(nested.resolve("report.txt"), generated);
        assertEquals("Daily\n", Files.readString(generated, StandardCharsets.UTF_8));
    }
}
~~~

### Giải thích

- `@TempDir Path tempDir`: mỗi invocation có phạm vi thư mục riêng trong cấu hình JUnit mặc định; test không tự tìm tên của thư mục.
- `@BeforeEach`: tạo `ReportWriter` cho từng test; không cần `@SpringBootTest` vì service không phụ thuộc Spring container.
- Ca hợp lệ xác nhận **đường dẫn**, **file tồn tại** và **nội dung UTF-8**.
- Ca lỗi xác nhận `IllegalArgumentException` và **không có file kết quả**.
- Ca thư mục lồng nhau tạo `exports/daily` bên trong thư mục tạm; cleanup mặc định xóa đệ quy cả thư mục con và file khi hết phạm vi.

**Không cần viết `@AfterEach` chỉ để gọi `Files.delete(...)` hay `deleteOnExit()` đối với những file đã tạo trong `tempDir`.** Extension JUnit sẽ xử lý việc đó theo cleanup mode.

### Cấu hình và chạy trong dự án Spring Boot

Ví dụ Spring Boot 3.x/Java 17+ sử dụng Gradle Groovy DSL. Trong `build.gradle`, phần liên quan có thể là:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Giả định dự án đã có Spring Boot plugin, repositories và cấu hình Java/Gradle thích hợp. Đây là **đoạn cấu hình bổ sung**, không phải tệp build độc lập. `spring-boot-starter-test` cung cấp các thư viện kiểm thử cần thiết trong cấu hình Spring Boot 3.x thông dụng.

Từ thư mục có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.ReportWriterTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.ReportWriterTest"
~~~

Khi tất cả assertion đúng, ba test được JUnit/Gradle đánh dấu thành công. Ví dụ **không gọi `System.out.println`**, nên không có một chuỗi stdout cố định của chương trình để chép lại. Định dạng báo cáo/log phụ thuộc cấu hình Gradle và JUnit.

**Khả năng chạy:** hai lớp Java ở trên dùng API Java 17 và JUnit Jupiter, đặt đúng package và đúng thư mục source. Có thể chạy test trong một dự án Spring Boot đã cấu hình như mô tả; không thể biên dịch riêng `ReportWriterTest.java` bằng `javac` không có JUnit trên classpath.

## 5. Tự động dọn khi kết thúc: hiểu đúng về cleanup

Mặc định `@TempDir` sử dụng chế độ **`CleanupMode.ALWAYS`**. Khi phạm vi kết thúc (thường là một invocation của test hoặc một lớp nếu dùng thư mục cấp lớp), JUnit **thử xóa đệ quy**:

1. Các file được tạo trực tiếp trong thư mục tạm.
2. Các thư mục con và file nằm bên trong.
3. Cuối cùng là chính thư mục tạm.

Cơ chế này thường áp dụng cả khi assertion của test thất bại. Nó giúp lần chạy sau không vô tình sử dụng file cũ, đồng thời giảm rác trong vùng tạm. Tuy nhiên không thể bảo đảm mọi trường hợp: tiến trình bị kill, JVM crash, filesystem lỗi, file bị khóa hoặc không đủ quyền có thể ngăn cleanup. Một số lỗi dọn file còn có thể khiến JUnit báo test/class thất bại.

### Các mức cleanup

| Giá trị `TempDir.CleanupMode` | Hành vi | Khi cân nhắc |
| --- | --- | --- |
| `ALWAYS` (mặc định) | Cố gắng xóa khi hết phạm vi, kể cả test fail | Phần lớn các test thông thường |
| `ON_SUCCESS` | Chỉ dọn nếu test hoàn thành thành công | Tạm giữ dữ liệu để điều tra ca thất bại |
| `NEVER` | Không tự dọn khi hết phạm vi | Chỉ dùng có chủ đích để debug; cần tự quản lý dữ liệu lưu lại |

Ví dụ chỉ giữ thư mục tạm nếu ca test thất bại:

~~~java
@TempDir(cleanup = TempDir.CleanupMode.ON_SUCCESS)
Path tempDir;
~~~

Đây là **đoạn field trong lớp test**, cần import `org.junit.jupiter.api.io.TempDir`. Cú pháp `TempDir.CleanupMode.ON_SUCCESS` nêu rõ enum thuộc annotation.

Muốn luôn giữ dữ liệu (ít dùng trong CI):

~~~java
@TempDir(cleanup = TempDir.CleanupMode.NEVER)
Path tempDir;
~~~

Đừng bật `NEVER` bừa bãi trên toàn bộ test suite: file tạm có thể chứa dữ liệu nhạy cảm, chiếm dung lượng và tích lũy qua nhiều lần chạy. Hãy ưu tiên mặc định `ALWAYS`, rồi điều chỉnh tạm thời cho ca cần chẩn đoán. JUnit cũng có cấu hình `junit.jupiter.tempdir.cleanup.mode.default` để thay đổi mặc định khi cần chính sách chung, nhưng cấu hình cục bộ phải được xem xét theo mục đích test.

**Quan trọng:** Không viết một test thứ hai rồi assert thư mục cũ đã bị xóa để “chứng minh JUnit cleanup”. Đó là kiểm tra lifecycle của framework và thường cần test harness riêng bên ngoài phạm vi test, không phải điều kiện nghiệp vụ của ứng dụng.

## 6. Dọn file đúng cách nếu test tự mở stream hoặc tài nguyên khác

`@TempDir` quản lý **thư mục và file nằm trong thư mục đó**. Nó không thay cho việc đóng stream, socket, process, database connection hoặc resource mà application code tự mở.

Ví dụ sử dụng `try-with-resources` để bảo đảm stream đóng trước khi JUnit dọn thư mục:

~~~java
@Test
void readsFileUsingStream(@TempDir Path tempDir) throws IOException {
    Path file = tempDir.resolve("data.bin");
    Files.write(file, new byte[] { 1, 2, 3 });

    try (var input = Files.newInputStream(file)) {
        assertEquals(1, input.read());
        assertEquals(2, input.read());
        assertEquals(3, input.read());
        assertEquals(-1, input.read());
    }
}
~~~

Đây là **phương thức minh họa**, cần import `IOException`, `Path`, `Files`, `Test`, `TempDir` và `assertEquals`. Trên Windows, file còn đang được một stream/process giữ mở thường khó xóa hơn, nên quản lý vòng đời stream là vấn đề thực tế, không chỉ vấn đề phong cách mã.

`@AfterEach` chỉ cần thiết khi có **tài nguyên per-test khác** phải dọn ngoài phạm vi tự động của `@TempDir`. Ví dụ test khởi động một process phụ hoặc tạo dữ liệu trong một dịch vụ bên ngoài; phải đóng hoặc rollback theo đúng cơ chế quản lý tương ứng. Không dùng `@AfterEach` để xóa mọi file trong thư mục tạm một lần nữa nếu JUnit đã chịu trách nhiệm.

Với file nằm **ngoài** thư mục tạm (chẳng hạn một đường dẫn cấu hình cố định), JUnit sẽ không tự dọn chỉ vì trong cùng test có `@TempDir`. Do đó cần đưa code ghi file về một thư mục do test chỉ định, hoặc tách riêng quy trình cleanup rõ ràng cho tài nguyên ngoài vùng tạm.

## 7. Kiểm tra tạo nhiều thư mục, file lồng nhau và tính cô lập

Cách an toàn để tạo dữ liệu phức tạp:

~~~java
@Test
void exportsMultipleFiles(@TempDir Path tempDir) throws IOException {
    Path archive = Files.createDirectories(tempDir.resolve("archive"));
    Path first = Files.writeString(archive.resolve("a.txt"), "A");
    Path second = Files.writeString(archive.resolve("b.txt"), "B");

    assertTrue(Files.isDirectory(archive));
    assertEquals("A", Files.readString(first));
    assertEquals("B", Files.readString(second));
}
~~~

Đây là **đoạn minh họa** đặt trong lớp test; `Files.writeString` trả về `Path` của file ghi được. Các đường dẫn đều là hậu duệ của `tempDir`, do đó việc dọn đệ quy mặc định bao phủ chúng.

Không tạo file dưới `src/test/resources` hoặc thư mục working directory chỉ để test có đầu vào nếu dữ liệu đó do test sinh động mỗi lần. Các fixture **bất biến** có thể nằm trong `src/test/resources`; còn dữ liệu cần được ghi/sửa khi chạy test nên nằm trong `@TempDir`. Không đưa file sinh ra trong test lên Git hoặc phụ thuộc file tồn dư trong môi trường phát triển.

Nếu tên file hoặc đường dẫn con lấy từ input chưa tin cậy, đừng dùng `tempDir.resolve(userInput)` một cách mù quáng: đường dẫn tuyệt đối hoặc chuỗi `..` có thể thoát ra ngoài thư mục tạm. Ứng dụng cần xác thực tên file hoặc chuẩn hóa và kiểm tra đường dẫn đích thực sự nằm bên trong thư mục được phép, đồng thời cân nhắc symbolic link trong kịch bản bảo mật.

## 8. Phân biệt @TempDir với các kỹ thuật khác

| Cách làm | Phù hợp khi | Giới hạn cần nhớ |
| --- | --- | --- |
| `@TempDir` | Test thao tác file/thư mục thật, muốn cô lập và dọn tự động | Không quản lý database, mạng hoặc tài nguyên ngoài thư mục |
| `Files.createTempDirectory(...)` | Mã ngoài JUnit hoặc cần tự kiểm soát vòng đời | Người viết code phải dọn đệ quy; không tự có lifecycle JUnit |
| `Files.createTempFile(...)` | Cần một file tạm | Chỉ tạo file; trách nhiệm xóa phụ thuộc phạm vi quản lý |
| `@BeforeEach` / `@AfterEach` | Chuẩn bị hoặc dọn tài nguyên riêng của mỗi test | Nếu chỉ dọn file trong `@TempDir` thì có thể thừa |
| `@BeforeAll` / `@AfterAll` | Tài nguyên dùng chung ở cấp lớp | Dễ gây chia sẻ mutable state; không thay thế cleanup tích hợp |
| Mock filesystem/file service | Test chỉ nhắm vào logic không cần I/O thật | Mock có thể bỏ sót lỗi đường dẫn, encoding, permission, ghi/đọc file thật |

Có thể kết hợp: `@BeforeEach` tạo data fixture **trong** `@TempDir`, test dùng chúng, còn JUnit dọn thư mục khi hết phạm vi. Đừng nhầm chức năng chuẩn bị điều kiện và chức năng quản lý vòng đời dữ liệu.

### Dùng cùng Spring Boot Test

Các test dùng `@SpringBootTest`, `@WebMvcTest` hoặc test slice vẫn có thể sử dụng `@TempDir` vì nó là cơ chế của **JUnit Jupiter**. Ví dụ một test kiểm tra service xuất báo cáo có bean Spring thật có thể truyền `tempDir` cho method của service được `@Autowired`. Với logic thuần Java như `ReportWriter`, unit test JUnit không cần khởi động Spring context sẽ nhanh và trực tiếp hơn.

Nếu service dùng một path từ `application.yml` hoặc `@ConfigurationProperties`, cần cấu hình đường dẫn đầu ra trong **ngữ cảnh test** để nó trỏ đến vùng tạm phù hợp. Nếu path được chốt khi Spring context khởi tạo, không chỉ sửa một biến sau đó rồi giả định bean đang dùng path mới. Chọn cách inject `Path` qua method/constructor hoặc thiết lập test property trước khi bean được tạo; bảo đảm không có đường dẫn file thật bị sử dụng ngoài ý muốn.

Nếu test dùng transaction/rollback của Spring để dọn dữ liệu database, rollback **không xóa file trên disk**. Ngược lại, `@TempDir` không rollback database. Mỗi loại tài nguyên có cơ chế quản lý riêng.

## 9. Những lỗi thường gặp với @TempDir

1. **Tự gán đường dẫn cho trường `@TempDir`:** JUnit cần được quyền cấp phát trường. **Sửa:** để trường chưa khởi tạo, ví dụ `@TempDir Path tempDir;`.
2. **Đường dẫn tuyệt đối trong test:** ghi trực tiếp vào `/tmp/demo.txt` hoặc thư mục dự án. **Sửa:** viết dưới `tempDir.resolve("demo.txt")`.
3. **Đặt annotation lên một biến tùy ý trong thân method:** `@TempDir` dùng trên field hoặc parameter hỗ trợ, không phải cơ chế annotate local variable bất kỳ. **Sửa:** đặt tại tham số `@Test` hoặc field test class.
4. **Nhầm scope per-test và per-class:** dùng `static @TempDir` rồi để nhiều test tạo chung `output.txt`. **Sửa:** dùng field instance theo mặc định hoặc parameter riêng cho từng test.
5. **Đòi thư mục đã bị xóa trong lúc test đang chạy:** JUnit chỉ dọn khi hết phạm vi. **Sửa:** assert file khi test chạy, để framework xử lý cleanup sau đó.
6. **Mở file stream nhưng không đóng:** một số hệ thống không thể xóa file còn bị khóa. **Sửa:** đóng tài nguyên với `try-with-resources` hoặc cleanup đúng chủ sở hữu.
7. **Dọn thủ công thiếu an toàn:** dùng xóa đệ quy trên path sai hoặc tự xóa thư mục JUnit đang quản lý khiến hook khác cần dữ liệu bị lỗi. **Sửa:** để `@TempDir` cleanup mặc định, chỉ tự dọn tài nguyên ngoài scope.
8. **Bật `CleanupMode.NEVER` nhưng quên xóa dữ liệu debug:** rác test và file nhạy cảm có thể tồn tại lâu. **Sửa:** bật có chủ đích, quản lý vòng đời artifact được giữ lại và quay về `ALWAYS`.
9. **Cho rằng thư mục luôn trống giữa các test chia sẻ:** `static` hoặc đổi instance lifecycle có thể làm các test tác động nhau. **Sửa:** thiết kế test không chia sẻ file có thể thay đổi.
10. **Nhầm cleanup filesystem với rollback database:** hai cơ chế độc lập. **Sửa:** xác định rõ tài nguyên test tạo ra và ai chịu trách nhiệm dọn từng loại.
11. **Đặt tên file theo input không kiểm soát:** path traversal hoặc file bên ngoài vùng tạm bị ảnh hưởng. **Sửa:** kiểm tra đầu vào, đường dẫn chuẩn hóa và ranh giới cho phép.

## 10. Checklist thực hành

Trước khi kết thúc một test có I/O file:

- [ ] Dùng `@TempDir` trên `Path` hoặc `File` tại vị trí JUnit hỗ trợ.
- [ ] Dữ liệu sinh ra bởi test nằm **bên trong** thư mục tạm.
- [ ] Cần thư mục riêng cho mỗi ca thì dùng parameter hoặc fixture per-test, tránh state chung.
- [ ] Code được kiểm tra nhận được đường dẫn có thể cấu hình; không hard-code đường dẫn sản xuất.
- [ ] Assertion kiểm tra đúng nội dung file, tên file, cấu trúc hoặc trạng thái lỗi theo yêu cầu nghiệp vụ.
- [ ] File stream, reader, writer hoặc process được đóng trước khi hết scope.
- [ ] Dùng cleanup mặc định `ALWAYS` trừ khi có lý do debug cụ thể.
- [ ] Không kỳ vọng thư mục bị xóa khi test còn đang chạy.
- [ ] File ở ngoài `tempDir`, database hoặc tài nguyên mạng có chiến lược cleanup riêng.
- [ ] Test chạy độc lập và không phụ thuộc file của lần chạy trước.

**Ghi nhớ:** `@TempDir` giúp test tạo một **không gian filesystem an toàn, độc lập và có vòng đời xác định**. Tạo file bằng `Files` bên trong không gian đó, assert kết quả khi test thực thi, và để JUnit dọn đệ quy theo phạm vi/cleanup mode đã chọn.

### Tài liệu tham khảo

- [JUnit 5 User Guide — Built-in Extensions / @TempDir](https://docs.junit.org/5.12.0/user-guide/)
- [JUnit 5 API — TempDir](https://docs.junit.org/5.13.3/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html)