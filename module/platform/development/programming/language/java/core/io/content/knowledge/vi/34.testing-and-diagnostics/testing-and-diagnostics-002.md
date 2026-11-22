# Tạo thư mục tạm riêng cho từng kịch bản kiểm thử trong Java 17+

## 1. Tại sao phải cô lập dữ liệu I/O của từng kịch bản?

Khi kiểm thử xử lý tệp, ứng dụng thường cần tạo file đầu vào, ghi file đầu ra, tạo cây thư mục hoặc mô phỏng đường lỗi. Nếu nhiều kịch bản cùng sử dụng một vị trí cố định như `./test-data/output.txt`, các lần chạy có thể ảnh hưởng lẫn nhau:

- Bài kiểm thử trước để lại file khiến lần chạy sau thành công hoặc thất bại sai.
- Hai bài kiểm thử chạy song song ghi cùng tên file và tạo **race condition**.
- Bài kiểm thử phụ thuộc dữ liệu tồn tại trên máy lập trình viên nhưng không có trên CI.
- Khi kiểm thử lỗi, dữ liệu ghi dở vẫn còn và tác động đến kịch bản kế tiếp.
- Lệnh dọn dẹp dùng đường dẫn cứng có thể xóa nhầm dữ liệu thật.

Một giải pháp mặc định tốt là **mỗi kịch bản có thư mục tạm riêng**, tạo ngay khi kịch bản bắt đầu và dọn khi kết thúc:

~~~text
Thư mục tạm của hệ điều hành
├── test-import-48297.../
│   ├── input/
│   │   └── data.csv
│   └── output/
│       └── result.json
└── test-export-12058.../
    ├── input/
    │   └── data.csv
    └── output/
        └── result.json
~~~

Các tên có phần ngẫu nhiên ở trên chỉ là minh họa. Hai kịch bản đều có thể dùng đường dẫn tương đối `input/data.csv` mà vẫn không đụng nhau vì **thư mục gốc hoàn toàn khác nhau**.

Sau bài này, bạn sẽ biết cách tạo thư mục tạm bằng `Files.createTempDirectory`, phân chia phạm vi ownership, xử lý cleanup khi test thất bại, kiểm tra tính portable trên CI và kết hợp với framework kiểm thử như JUnit Jupiter `@TempDir`.

## 2. API cốt lõi: `Files.createTempDirectory`

Java NIO.2 định nghĩa hai dạng phổ biến:

~~~java
Path root = Files.createTempDirectory("case-import-");

Path rootUnderParent = Files.createTempDirectory(
        parentDirectory, "case-import-");
~~~

Đây là **đoạn minh họa**, cần import `java.nio.file.Files`, `java.nio.file.Path`; `parentDirectory` phải là thư mục cha phù hợp, tồn tại và có quyền tạo mục.

- `Files.createTempDirectory(String prefix, FileAttribute<?>... attrs)` tạo một thư mục mới trong vùng tạm mặc định do môi trường/provider quyết định.
- `Files.createTempDirectory(Path dir, String prefix, FileAttribute<?>... attrs)` tạo một thư mục mới **ngay dưới `dir`**, phù hợp khi muốn tất cả artifact kiểm thử nằm trong workspace tạm dành riêng cho lần chạy.
- Hàm trả về `Path` của **thư mục vừa tạo**; `Path` chỉ là biểu diễn đường dẫn, **không phải tài nguyên `AutoCloseable`** và không tự xóa khi ra khỏi scope.
- Mỗi lần gọi được thiết kế để tạo tên chưa tồn tại trong vị trí đích. Bạn không cần tự tạo tên bằng timestamp hoặc ép xung đột bằng số thứ tự chia sẻ.
- `prefix` giúp nhìn log/trace thuận tiện; không nên dùng dữ liệu nhạy cảm như token, mật khẩu hoặc tên khách hàng trong prefix.
- Nếu không có quyền ghi, đường dẫn không hợp lệ hoặc provider không hỗ trợ cấu hình attributes, lời gọi có thể thất bại; test cần báo lỗi thay vì lặng lẽ chuyển sang xóa/thay thế một thư mục khác.

Ví dụ tạo file nằm trong vùng cô lập:

~~~java
Path root = Files.createTempDirectory("scenario-");
Path inputDir = Files.createDirectories(root.resolve("input"));
Path input = inputDir.resolve("data.txt");

Files.writeString(input, "sample", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW);
~~~

Đây là ví dụ rời, cần import `Files`, `Path`, `StandardCharsets`, `StandardOpenOption` và cleanup khi hoàn thành. `CREATE_NEW` từ chối ghi đè đường dẫn file đã tồn tại; kết hợp với root mới là một kiểm tra tốt rằng test không phụ thuộc file cũ.

**Không nhầm `Files.createTempFile(...)` với `createTempDirectory(...)`.** Hàm đầu tạo file mới, hàm sau tạo thư mục mới. Với một kịch bản cần nhiều input/output, tạo một thư mục gốc rồi dùng `resolve` để tổ chức file bên trong thường thuận tiện hơn.

## 3. Phạm vi ownership: ai tạo thì ai dọn?

Một nguyên tắc đơn giản:

> Thành phần tạo root tạm sở hữu root đó, chịu trách nhiệm dọn nội dung bên trong và **chỉ** nội dung bên trong root đó.

Ví dụ phương thức test sở hữu vùng:

~~~text
testScenario():
  root = createTempDirectory()
  try:
      chuẩn bị input trong root
      chạy mã cần kiểm thử trên các path thuộc root
      assert output
  finally:
      xóa cây root
~~~

Nếu helper nhận `Path root` từ caller, helper **không nên tự xóa cả root** trừ khi hợp đồng nói rõ nó được giao ownership. Helper chỉ nên tạo/sửa những mục đã được caller cho phép.

Phạm vi thích hợp tùy bài toán:

| Phạm vi | Cách dùng | Khi nào hợp lý |
| --- | --- | --- |
| Một scenario/test method | Mỗi lần gọi tạo một root mới | Lựa chọn mặc định giúp test độc lập |
| Một nhóm test dùng chung fixture bất biến | Có thể tạo một root cho nhóm, chia thư mục con | Khi setup đắt và dữ liệu **thật sự không bị sửa** |
| Một lần chạy bộ test | Tạo parent duy nhất rồi tạo root con cho từng scenario | Dễ thu thập artifact và dọn cả lần chạy |
| Một tác vụ concurrent | Root riêng cho mỗi request/task | Khi nhiều tác vụ có thể ghi cùng tên file |
| Production job | Staging root riêng cho job | Khi cần không công bố dữ liệu ghi dở; thường có chính sách dọn và giám sát riêng |

**Cô lập root không tự động cô lập mọi thứ.** Hai test có root khác nhau vẫn có thể tranh chấp cổng TCP cố định, database, biến môi trường, static state, file ngoài root hay tài nguyên native. Nếu gặp vấn đề đó, phải cô lập hoặc điều phối từng tài nguyên tương ứng.

## 4. Không sử dụng đường dẫn cố định hoặc tên dựng từ thời gian

Mẫu dễ gây xung đột:

~~~java
Path root = Path.of("build/tmp/my-test");
Files.createDirectories(root);
~~~

Đây là **mẫu phản ví dụ** nếu nhiều kịch bản cùng dùng `root` mà không có cơ chế điều phối. `createDirectories` cho phép thư mục đã tồn tại, nên một test có thể vô tình dùng lại file hoặc dữ liệu của test trước.

Mẫu tốt hơn:

~~~java
Path base = Path.of("build", "test-scratch");
Files.createDirectories(base);

Path scenarioRoot = Files.createTempDirectory(base, "import-");
~~~

Đoạn này chỉ minh họa. Thư mục cha `build/test-scratch` có thể là workspace dùng chung; còn `scenarioRoot` luôn là thư mục con mới. Trong CI hoặc chạy parallel, cần bảo đảm `base` nằm trên phân vùng đủ dung lượng và có quyền ghi. Nếu dự án dùng hệ thống build khác, không bắt buộc sử dụng tên `build`.

**Không dựa vào timestamp `System.currentTimeMillis()` để tạo uniqueness tuyệt đối.** Hai tác vụ có thể khởi phát trong cùng mili giây. `UUID` hoặc một hàm tạo tên an toàn có thể dùng trong trường hợp đặc biệt, nhưng `Files.createTempDirectory` đã giải quyết trực tiếp nhu cầu tạo thư mục mới mà không cần tự thiết kế thuật toán.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai kịch bản, tên file giống nhau

Chương trình độc lập dưới đây chạy hai kịch bản sử dụng chung tên file tương đối `input/data.txt` và `output/result.txt`. Mỗi kịch bản tự tạo root mới, chuẩn bị nội dung khác nhau, copy dữ liệu và kiểm tra. `finally` bảo đảm quy trình dọn được gọi dù assert hoặc thao tác I/O bị lỗi.

Lưu file **`ScenarioTempDirectoryDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;

public class ScenarioTempDirectoryDemo {

    public static void main(String[] args) throws IOException {
        runScenario("alpha", "NORTH");
        runScenario("beta", "SOUTH");
        System.out.println("All scenarios passed");
    }

    private static void runScenario(String name, String content)
            throws IOException {
        Path root = Files.createTempDirectory("io-" + name + "-");

        try {
            Path inputDirectory =
                    Files.createDirectory(root.resolve("input"));
            Path outputDirectory =
                    Files.createDirectory(root.resolve("output"));

            Path input = inputDirectory.resolve("data.txt");
            Path output = outputDirectory.resolve("result.txt");

            Files.writeString(
                    input, content, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            // Mô phỏng một thao tác I/O mà test muốn xác minh.
            Files.copy(input, output, StandardCopyOption.COPY_ATTRIBUTES);

            String actual =
                    Files.readString(output, StandardCharsets.UTF_8);
            if (!content.equals(actual)) {
                throw new AssertionError("Unexpected file content");
            }

            System.out.println(name + " output: " + actual);
        } finally {
            deleteTree(root);
        }
    }

    private static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attributes)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path directory, IOException error)
                    throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ScenarioTempDirectoryDemo.java
java ScenarioTempDirectoryDemo
~~~

**Stdout kỳ vọng khi môi trường cho phép tạo, sao chép và xóa file tạm:**

~~~text
alpha output: NORTH
beta output: SOUTH
All scenarios passed
~~~

### Giải thích mã

1. `runScenario` gọi `Files.createTempDirectory(...)` cho **mỗi** scenario, nên root của `alpha` và root của `beta` khác nhau. Prefix chỉ hỗ trợ truy vết; phần tên còn lại do provider sinh.
2. Trong mỗi root, chương trình tự tạo hai thư mục con bằng `Files.createDirectory`, sau đó dùng tên `data.txt` và `result.txt` giống nhau. Nếu dùng chung root, hai kịch bản có thể xung đột; dùng hai root giúp tránh phụ thuộc này.
3. `Files.writeString(..., CREATE_NEW)` tạo file input mới và không ghi đè file tồn tại. `Files.copy` copy sang đường dẫn output chưa tồn tại.
4. `Files.readString` đọc file output có nội dung rất nhỏ. Ở ví dụ này việc đọc toàn file là hợp lý; với file lớn trong bài học hiệu năng cần chọn đọc theo khối.
5. Kiểm tra `content.equals(actual)` xác minh từng kịch bản nhận chính xác dữ liệu của nó. `AssertionError` được dùng để báo test failure mà không cần thư viện ngoài.
6. `finally` chạy sau thao tác thành công hoặc lỗi. `deleteTree` dọn file trước, thư mục sau, phù hợp vì xóa một thư mục còn file bên trong sẽ thất bại.
7. `Files.walkFileTree` **không theo symbolic link theo mặc định**; code không truyền `FileVisitOption.FOLLOW_LINKS`. Vì vậy một symlink được phát hiện như mục trong cây sẽ được xóa như mục liên kết, thay vì cố truy cập cây đích của symlink.
8. Stdout không in tên root ngẫu nhiên, nên khi I/O thành công thì kết quả luôn như trên. Nếu môi trường chặn quyền ghi/xóa, chương trình báo lỗi và không giả vờ hoàn thành.

**Lưu ý:** `COPY_ATTRIBUTES` cố gắng sao chép một số thuộc tính cơ bản, nhưng khả năng hỗ trợ phụ thuộc file system. Với mục tiêu chỉ test byte content, có thể dùng `Files.copy(input, output)` đơn giản hơn. Nếu `COPY_ATTRIBUTES` không được hỗ trợ, ví dụ có thể báo lỗi thay vì in kết quả; đây là lý do nên bỏ tùy chọn không cần thiết trong test portable.

## 6. Dọn cây thư mục đúng: vì sao không chỉ dùng `Files.delete(root)`?

`Files.delete(path)` xóa một file hoặc **thư mục trống**. Nếu root tạm còn tệp đầu vào, tệp đầu ra hoặc thư mục con, xóa root trực tiếp có thể gặp `DirectoryNotEmptyException`.

Ví dụ không đúng khi root có nội dung:

~~~java
Files.delete(root); // Thất bại nếu root còn file/thư mục con.
~~~

Cách thường dùng trong Java Core là duyệt toàn cây rồi xóa **con trước, cha sau**, chẳng hạn `Files.walkFileTree` với `SimpleFileVisitor` như ví dụ đầy đủ ở phần 5.

Một mẫu khác có thể dùng `Files.walk(root)`, sắp xếp thứ tự ngược và xóa:

~~~java
try (var paths = Files.walk(root)) {
    for (Path p : paths.sorted(
            java.util.Comparator.reverseOrder()).toList()) {
        Files.deleteIfExists(p);
    }
}
~~~

Đây là **đoạn minh họa**, yêu cầu `root` là vùng được phép xóa và import `Files`, `Path`. `Files.walk` tạo stream cần đóng bằng `try-with-resources`. `toList()` tích lũy tất cả path vào RAM; trên cây rất lớn, `walkFileTree` thường thích hợp hơn vì xử lý từng mục.

**Không dùng xóa đệ quy trên một đường dẫn không được kiểm soát.** Đặc biệt tránh “cleanup” bằng cách xóa trực tiếp thư mục tạm chung của hệ điều hành hoặc workspace dùng chung. Hàm dọn chỉ được nhận đúng root vừa tạo và thuộc quyền sở hữu của kịch bản.

### Xử lý lỗi khi cleanup

Nếu thao tác test phát sinh exception và cleanup cũng ném exception từ `finally`, exception cleanup có thể **che mất nguyên nhân test ban đầu**. Đó là hành vi của `finally` với exception mới.

Đối với framework hoặc helper nghiêm ngặt, có thể thiết kế để giữ lỗi gốc, rồi gắn lỗi cleanup bằng `Throwable.addSuppressed(...)`. Nếu cleanup thất bại, nên log root tạm và trạng thái còn sót để có thể điều tra; không nên nuốt lỗi hoàn toàn hoặc xóa file ngoài phạm vi nhằm “khắc phục”.

Ví dụ phương án giữ cả hai lỗi (minh họa cấu trúc, không độc lập):

~~~java
Throwable primary = null;
try {
    runTestBody(root);
} catch (Throwable failure) {
    primary = failure;
    throw failure;
} finally {
    try {
        deleteTree(root);
    } catch (IOException cleanupFailure) {
        if (primary != null) {
            primary.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
~~~

Trong thực tế, kiểu `Throwable` và việc ném lại cần phù hợp chữ ký phương thức/cách xử lý checked exception; ví dụ chỉ minh họa ý tưởng giữ thông tin lỗi. `try-with-resources` hỗ trợ suppressed exception tự động cho các resource triển khai `AutoCloseable`, **không áp dụng trực tiếp cho `Path`** vì `Path` không có `close()`.

## 7. Đừng xóa file khi stream hoặc channel vẫn còn mở

Một kịch bản có thể mở `InputStream`, `OutputStream`, `FileChannel`, `RandomAccessFile` hoặc `DirectoryStream`. Cần đóng các resource đó **trước** khi xóa root.

Trên một số hệ điều hành, nhất là Windows, file đang mở có thể không cho phép xóa/đổi tên. Trên một số hệ thống khác, hành vi xóa file đang mở khác; không nên dùng đặc tính của máy hiện tại làm hợp đồng portable.

Cách tổ chức:

~~~java
Path root = Files.createTempDirectory("channel-test-");
try {
    Path file = root.resolve("payload.bin");

    try (var output = Files.newOutputStream(
            file, StandardOpenOption.CREATE_NEW)) {
        output.write(new byte[] { 1, 2, 3 });
    }

    try (var input = Files.newInputStream(file)) {
        int firstByte = input.read();
        if (firstByte != 1) {
            throw new AssertionError("Unexpected byte");
        }
    }
} finally {
    deleteTree(root);
}
~~~

Đây là đoạn minh họa, `deleteTree` đã được định nghĩa ở phần ví dụ độc lập. `try-with-resources` đảm bảo stream được đóng trước khi chạy cleanup. Nếu callback/worker bất đồng bộ còn ghi file, kịch bản còn phải đợi hoặc hủy và xác nhận các công việc đó đã kết thúc trước khi xóa.

## 8. Root tạm và thư mục làm việc: không được nhầm

Ba vị trí có thể có ý nghĩa khác nhau:

- **Current working directory:** thường liên quan `System.getProperty("user.dir")`, ví dụ thư mục khởi chạy Maven/Gradle. Không nên dùng làm nơi test ghi file nếu cần độc lập.
- **Thư mục tạm mặc định:** thường liên quan cấu hình môi trường của JVM/provider (ví dụ thuộc tính `java.io.tmpdir` trên provider mặc định).
- **Thư mục cha do test chọn:** ví dụ một workspace tạm do runner/CI cấp cho test job; gọi `createTempDirectory(parent, prefix)` để đặt scenario root ở đó.

Đừng tự cho rằng việc thay đổi `System.setProperty("java.io.tmpdir", ...)` trong lúc JVM đang chạy sẽ chuyển mọi thao tác `Files.createTempDirectory` sau đó sang nơi khác. Nhà cung cấp file system hoặc JVM có thể lưu cấu hình từ trước; nếu muốn chọn vị trí rõ ràng, **truyền `Path parent` trực tiếp**.

Ví dụ:

~~~java
Path parent = Path.of("/workspace/test-scratch");
Files.createDirectories(parent);
Path scenario = Files.createTempDirectory(parent, "parse-");
~~~

Đây là ví dụ đường dẫn chỉ phù hợp trên hệ thống có `/workspace/test-scratch`. Khi chạy cross-platform, nhận `parent` từ cấu hình build/test hoặc dựng từ `Path` thích hợp; đừng đưa nguyên đường dẫn POSIX vào chương trình dành cho Windows.

### Nên chọn vị trí tạm nào?

Nếu kịch bản cần kiểm tra file I/O thông thường, vùng tạm mặc định thường hợp lý. Nhưng khi kiểm thử những hành vi phụ thuộc file system, vị trí gốc quan trọng:

- **`Files.move(..., ATOMIC_MOVE)`:** có thể cần các đường dẫn trong cùng file system và provider hỗ trợ; không phải mọi hệ thống tệp bảo đảm thao tác này.
- **File locks, quyền file, symlink:** phụ thuộc hệ điều hành, mount option và quyền process.
- **Kiểm thử network file system:** muốn kiểm thử thực tế NFS/SMB thì cần chọn parent nằm trên mount NFS/SMB, không dùng mặc định vùng tạm local rồi suy ra đặc điểm remote.
- **Kích thước/quota:** một vùng tạm có thể có quota nhỏ hoặc nằm trên tmpfs dùng RAM; không giả định nó có không gian vô hạn.

## 9. Thư mục tạm hỗ trợ parallel test như thế nào?

Giả sử runner chạy hai test đồng thời:

~~~text
Thread A:
  rootA = createTempDirectory("case-A-")
  write rootA/input.txt
  assert rootA/output.txt
  cleanup rootA

Thread B:
  rootB = createTempDirectory("case-B-")
  write rootB/input.txt
  assert rootB/output.txt
  cleanup rootB
~~~

Vì `rootA` và `rootB` khác nhau, hai thread có thể dùng cùng tên file tương đối mà không ghi vào cùng path.

Tuy nhiên, muốn **thật sự độc lập**, test cũng không được dựa vào thứ tự thực thi. Ví dụ, test B không được cho rằng test A đã chạy để tạo dữ liệu nào đó. Nếu có fixture dùng chung bắt buộc, hãy chỉ định rõ setup/teardown và đồng bộ theo framework.

Những giới hạn vẫn phải tính:

1. Dung lượng đĩa của thư mục tạm dùng chung có thể bị nhiều test tiêu thụ.
2. Hai test có thể đụng tài nguyên ngoài root như port, database hoặc static state.
3. Một test lỗi có thể để lại file nếu process bị kill trước `finally`.
4. Chạy song song quá nhiều tác vụ I/O có thể gây contention và làm benchmark biến động.
5. Môi trường antivirus, file-indexer hoặc scanner khác có thể gây trễ file operations, nhất là trên CI Windows.

Tạo root riêng là **một lớp cô lập**, không phải sandbox bảo mật giữa những tiến trình không tin cậy.

## 10. Dùng JUnit Jupiter `@TempDir` khi đã có framework

Trong dự án dùng **JUnit Jupiter (JUnit 5)**, extension `@TempDir` cung cấp một thư mục tạm cho test mà bạn không cần tự viết vòng tạo/xóa trong mỗi test.

Ví dụ minh họa, **không thuộc JDK chuẩn**; cần dependency JUnit Jupiter thích hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileProcessingTest {

    @Test
    void readsGeneratedFile(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("input.txt");
        Files.writeString(file, "hello", StandardCharsets.UTF_8);

        assertTrue(Files.exists(file));
        assertEquals("hello",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

Khi test runner/extension quản lý root, **không tự xóa vùng root của framework khi một test khác còn được quyền dùng nó**. Phạm vi và chính sách cleanup có thể phụ thuộc phiên bản/cấu hình framework; đọc tài liệu phiên bản thực tế. Mẫu parameter `@TempDir Path tempDir` giúp một test không cần dựa vào tên hard-coded hay working directory.

Đối với **JUnit 4**, một số dự án sử dụng `TemporaryFolder` rule; đó là API của framework khác và có quy tắc vòng đời khác. Không trộn lẫn với JUnit Jupiter chỉ vì tên tương tự.

### Khi nào dùng manual helper thay vì `@TempDir`?

- Đoạn mã chạy như ứng dụng Java độc lập, không phụ thuộc thư viện kiểm thử.
- Cần tạo nhiều root tạm có vòng đời khác nhau bên trong một test.
- Cần chọn parent/mount cụ thể để kiểm tra file system hoặc network share.
- Cần giữ lại artifact khi test thất bại theo chính sách debug riêng.
- Cần kiểm soát kỹ quy trình publish/cleanup trong integration test nhiều process.

Trong trường hợp tiêu chuẩn dùng JUnit Jupiter, `@TempDir` thường ngắn gọn hơn và giảm boilerplate.

## 11. Dữ liệu kiểm thử nhỏ, rõ và xác định

Thư mục tạm cô lập path, nhưng muốn test đáng tin còn phải tạo fixture **deterministic**:

- Dùng UTF-8 được khai báo rõ cho văn bản: `Files.writeString(path, text, StandardCharsets.UTF_8)`.
- Nếu quan trọng với giao thức byte, ghi `byte[]` cụ thể thay vì dùng platform default charset.
- Hạn chế dựa vào timestamp hay thời gian hệ điều hành để xác nhận file đã được xử lý; độ phân giải `lastModifiedTime` có thể khác nhau.
- Không in tên root ngẫu nhiên vào stdout nếu cần assert output cố định; có thể ghi root vào log riêng khi debug.
- Nếu kịch bản cần dữ liệu lớn, nên tạo dữ liệu theo chunk thay vì cấp phát một mảng cỡ file lớn.
- Nếu kiểm thử cách xử lý file đã tồn tại, tạo file theo setup **của chính kịch bản đó** thay vì phụ thuộc dữ liệu cũ từ test trước.
- Tách file `expected` và `actual` trong các thư mục con để tránh test tự ghi đè đáp án.

Ví dụ cấu trúc:

~~~text
scenario-root/
  fixtures/
    input.csv
    expected.json
  actual/
    result.json
  diagnostics/
    process.log
~~~

`expected.json` có thể được tạo từ một literal đã kiểm tra hoặc copy từ test resource **chỉ đọc**, rồi đặt vào root scenario trước khi chạy. Quan trọng là mỗi test có đầy đủ dữ liệu đầu vào và không thay đổi resource gốc dùng chung.

## 12. Xử lý trường hợp test cố tình phát sinh lỗi

Một số kịch bản cần xác minh phản ứng khi:

- File đầu vào thiếu.
- File đầu ra đã tồn tại.
- Tên file không hợp lệ.
- Nội dung file sai encoding.
- Thiếu quyền hoặc ổ đĩa đầy.
- Một luồng xử lý bị interrupt hoặc channel đóng giữa thao tác.

Trong các kịch bản này, **root riêng giúp không làm hỏng môi trường của các test khác**, nhưng không có nghĩa mọi lỗi file system đều mô phỏng được chỉ bằng cách tạo thư mục tạm.

Ví dụ để kiểm tra phương thức phải từ chối ghi đè:

~~~java
Path root = Files.createTempDirectory("collision-");
try {
    Path file = root.resolve("output.txt");
    Files.writeString(file, "already exists");

    boolean rejected = false;
    try {
        Files.newOutputStream(file, StandardOpenOption.CREATE_NEW).close();
    } catch (java.nio.file.FileAlreadyExistsException expected) {
        rejected = true;
    }

    if (!rejected) {
        throw new AssertionError("Expected overwrite protection");
    }
} finally {
    deleteTree(root);
}
~~~

Đây là đoạn minh họa, `deleteTree` đã được định nghĩa ở phần 5 và cần import `Files`, `Path`, `StandardOpenOption`. Nếu muốn test thiếu quyền, không nên giả định `setReadable(false)`/`setWritable(false)` luôn hoạt động giống nhau trên Windows, POSIX, container/root user và network share. Dùng environment phù hợp hoặc abstraction cho file I/O nếu cần một phép thử portable.

## 13. File tạm và bảo mật: cô lập logic không phải sandbox

`Files.createTempDirectory` giúp tránh trùng path nhưng **không cấp phép để xử lý dữ liệu tùy ý từ người dùng như thể nó an toàn**. Cần phân biệt hai tình huống:

**Kiểm thử dữ liệu do chính test sinh ra:** root tạm mặc định thường đủ để tránh ảnh hưởng chéo giữa scenario, miễn cleanup chỉ thao tác trong root đó.

**Giải nén/upload/dữ liệu không tin cậy:** phải có thêm giới hạn dung lượng, count, path traversal, symbolic link, quyền file và kiểm tra file output. Một tên tạm ngẫu nhiên không ngăn tất cả cuộc tấn công vào thư mục chứa.

Cân nhắc:

- **Không dùng đường dẫn nhập từ bên ngoài làm root xóa đệ quy.** Bảo đảm `root` được chính thành phần tạo ra và không bị thay bằng value không tin cậy.
- **Không theo symlink** khi cleanup nếu không có yêu cầu rõ ràng. `walkFileTree` mặc định không theo symlink, giúp giảm nguy cơ đi ra ngoài vùng cleanup.
- **Không chia sẻ root với tiến trình không tin cậy.** Nếu tiến trình khác có thể thay mục trong root khi cleanup, vẫn tồn tại rủi ro race/TOCTOU.
- **Không đưa bí mật vào tên prefix.** Tên thư mục tạm có thể xuất hiện trong log, file listing hoặc báo lỗi.
- **Quyền truy cập:** khi có dữ liệu nhạy cảm, đánh giá permission của root, parent và storage thực tế; sử dụng `FileAttribute` phù hợp provider khi yêu cầu, đồng thời xử lý nền tảng không hỗ trợ attributes.
- **Không dùng `deleteOnExit()` làm cơ chế quản lý chính** của một bộ test khối lượng lớn: danh sách path có thể tồn tại tới khi JVM kết thúc và cleanup không được bảo đảm khi process bị kill.

### Thư mục root và symlink

Nếu root là `/tmp/case-abc` và bên trong có symlink `external -> /home/user/documents`, hành vi `Files.walkFileTree(root, visitor)` **mặc định không duyệt xuyên symlink**; symlink thường được thăm như một file entry để xóa bản thân liên kết. Tuy nhiên, trong môi trường có actor khác sửa cây đồng thời, vẫn phải kiểm soát quyền và tránh mở file theo path không đáng tin sau thời điểm kiểm tra.

## 14. Giữ artifact để debug mà không làm bẩn các test khác

Đôi khi xóa tất cả ngay khi test fail sẽ khiến khó điều tra. Một chính sách thực tế:

1. **Mặc định cleanup luôn**, kể cả khi test thất bại.
2. Khi bật chế độ debug có chủ đích, giữ lại **chỉ root của kịch bản thất bại**, ghi đường dẫn trong log.
3. Đặt thời hạn lưu lại, quota dung lượng và cơ chế dọn định kỳ do runner/quản trị viên kiểm soát.
4. Không để tên root hoặc nội dung log chứa dữ liệu nhạy cảm không cần thiết.
5. Trong CI, khi cần xem artifact, có thể copy output/log đã chọn sang khu vực artifact chính thức rồi dọn root tạm; không phụ thuộc thư mục tạm còn tồn tại sau job.

Một biến cấu hình như `KEEP_TEST_ARTIFACTS` có thể điều khiển chính sách trong helper, nhưng chỉ giữ khi người vận hành chủ động bật. **Không bật mặc định chỉ để dễ debug**, vì các file lớn bị bỏ lại có thể khiến CI hết đĩa.

### Đo giới hạn tài nguyên

Mỗi kịch bản root riêng cũng giúp đo và hạn chế dung lượng dễ hơn: đếm số file tạo ra, tổng byte output, số open handle và thời gian cleanup. Tuy nhiên, phép đếm sau khi test kết thúc không phải bảo vệ chống disk full trong lúc ghi; với đầu vào không tin cậy, quota phải được thực thi **trong vòng ghi/đọc**.

## 15. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mọi test ghi cùng `./output.txt` | Đè file, test phụ thuộc thứ tự | Root tạm riêng cho từng kịch bản |
| Dùng timestamp làm tên không kiểm tra va chạm | Parallel test đụng tên | `Files.createTempDirectory` |
| `Files.createDirectories(sharedRoot)` rồi coi root là riêng | Dùng lại dữ liệu cũ | Tạo **subdirectory mới** bằng `createTempDirectory` |
| Xóa trực tiếp root còn file | `DirectoryNotEmptyException` | Xóa con trước cha bằng `walkFileTree` |
| Cleanup xóa cả vùng tạm chung | Mất dữ liệu của tác vụ khác | Chỉ xóa root **do mình tạo và sở hữu** |
| Quên `finally` khi test fail | File/tệp tạm tồn đọng | Cleanup trên mọi đường chạy |
| Không đóng stream trước khi cleanup | Xóa thất bại, đặc biệt trên Windows | `try-with-resources` trước cleanup |
| Dùng `deleteOnExit()` cho mọi file | Rò danh sách path đến cuối JVM, không đảm bảo khi bị kill | Cleanup chủ động có quản lý |
| Dùng symlink-following tree walk không kiểm soát | Có thể đi khỏi root tạm | Không bật `FOLLOW_LINKS` khi không cần |
| In tên folder tạm rồi assert stdout y nguyên | Test không xác định | Chỉ assert nội dung/kết quả ổn định |
| Giả định OS/file system hỗ trợ mọi quyền và atomic move | CI khác nền tảng thất bại | Test môi trường thật, xử lý unsupported |
| Chia sẻ root giữa các test parallel có ghi dữ liệu | Race và nondeterminism | Per-test root hoặc cơ chế khóa rõ ràng |
| Cleanup có exception che lỗi test gốc | Khó điều tra nguyên nhân | Suppress/ghi nhận cả lỗi cleanup |
| Test sửa global `java.io.tmpdir` khi JVM đang chạy | Không portable, ảnh hưởng test khác | Truyền `Path parent` vào API |
| Tạo thư mục tạm nhưng vẫn ghi file ngoài root | Không còn cô lập | Truyền root vào mọi thành phần xử lý I/O |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Hai test chạy song song đều ghi `output/result.json`. Làm sao tránh xung đột mà vẫn dùng cùng tên tương đối?

**Đáp án:** Mỗi test gọi `Files.createTempDirectory(...)` để có root riêng, sau đó dùng `root.resolve("output/result.json")`. Tên tương đối giống nhau nhưng đường dẫn đầy đủ khác nhau.

**Câu 2.** `Files.createTempDirectory` trả về `Path`. Khi biến `root` ra khỏi scope thì thư mục có tự bị xóa không?

**Đáp án:** Không. `Path` không phải `AutoCloseable` và không tự xóa. Dùng `finally`, helper hoặc framework như JUnit Jupiter `@TempDir` để quản lý cleanup.

**Câu 3.** Tại sao `Files.delete(root)` có thể thất bại dù root do test tạo?

**Đáp án:** Vì root còn file hoặc thư mục con. Cần duyệt và xóa thành phần con trước khi xóa root.

**Câu 4.** Có thể dùng một parent chung cho nhiều test không?

**Đáp án:** Có, nếu mỗi test tạo **một root con mới** bằng `createTempDirectory(parent, prefix)`, không dùng chính parent đó làm nơi ghi/xóa bừa bãi.

**Câu 5.** Đóng `FileChannel` liên quan gì tới cleanup?

**Đáp án:** Channel đang mở có thể giữ handle/lock khiến file không xóa được trên một số hệ điều hành. Đóng bằng `try-with-resources` trước khi xóa cây.

**Câu 6.** Một kịch bản cố ý gây lỗi parse và ném exception. Thư mục tạm có nên vẫn được dọn?

**Đáp án:** Có theo chính sách mặc định. `finally` sẽ chạy khi method thoát vì exception thông thường; nếu muốn giữ để debug thì cần chế độ riêng có quota và dọn sau.

**Câu 7.** `@TempDir` là annotation của Java SE 17?

**Đáp án:** Không. Đó là cơ chế hỗ trợ bởi **JUnit Jupiter** và cần framework/dependency tương ứng. `Files.createTempDirectory` mới thuộc Java SE.

**Câu 8.** Tạo root tạm mới có bảo đảm chống mọi cuộc tấn công path traversal từ ZIP do người dùng gửi không?

**Đáp án:** Không. Vẫn cần kiểm tra entry path, xử lý symlink, quyền, dung lượng, concurrency và chính sách giải nén an toàn.

## 17. Ghi nhớ

- **Mỗi kịch bản I/O có một root tạm riêng** giúp giảm nhiễm bẩn dữ liệu, test phụ thuộc thứ tự và xung đột khi chạy song song.
- **`Files.createTempDirectory` tạo mới; `Path` không tự cleanup.** Người tạo root chịu trách nhiệm dọn.
- **Dọn con trước cha** bằng `Files.walkFileTree`, không theo symlink nếu không có nhu cầu; đóng stream/channel trước khi dọn.
- **Truyền root vào mã cần test** thay vì ghi vào working directory hoặc thay đổi cấu hình tạm toàn JVM.
- **Framework `@TempDir`** giúp tự động hóa trong JUnit Jupiter; với chương trình Java độc lập dùng helper và `try/finally`.
- **Cô lập root là nền tảng của test đáng tin**, nhưng không thay thế quota, bảo mật path, kiểm soát tài nguyên ngoài file system và test trên môi trường thật.
