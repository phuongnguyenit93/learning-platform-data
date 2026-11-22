# Tệp tạm, đường dẫn tuyệt đối và tài nguyên đóng gói trong JAR

Ứng dụng Java thường làm việc với nhiều loại tài nguyên tệp: tệp cấu hình bên ngoài, tệp tạm do ứng dụng tạo, dữ liệu được đóng gói trong JAR và tệp được trích xuất để thư viện native hoặc công cụ bên ngoài sử dụng. Khi đưa ứng dụng vào CRaC, cần phân biệt rõ các loại này vì checkpoint lưu trạng thái tiến trình, còn nội dung trên filesystem vẫn do filesystem và môi trường triển khai quản lý.

Một `Path` hoặc `File` còn tồn tại trong heap sau restore không chứng minh tệp ở đường dẫn đó vẫn tồn tại, vẫn có cùng nội dung hoặc vẫn có thể truy cập. Thư mục tạm có thể bị dọn, container có thể được tạo lại, mount có thể thay đổi và quyền truy cập có thể khác. Ngược lại, một tài nguyên nằm trong JAR không nhất thiết là một tệp độc lập trên filesystem để có thể mở bằng `File`.

Khi thiết kế, hãy trả lời ba câu hỏi: tệp đến từ đâu, nó cần tồn tại trong bao lâu và ứng dụng sẽ làm gì nếu tệp không còn sau restore? Câu trả lời quyết định nên đọc trực tiếp từ classpath, tạo tệp tạm, dùng một thư mục làm việc được cấu hình hay lưu dữ liệu vào một nơi bền vững.

## 1. Phân biệt tài nguyên trên filesystem và tài nguyên trong JAR

Một tệp trên filesystem có một đường dẫn mà hệ điều hành có thể phân giải, ví dụ `/var/lib/myapp/config.yml` hoặc `C:\\app\\config.yml`. Java có thể thao tác với nó thông qua `Path`, `Files`, `FileChannel` và các API liên quan.

Một tài nguyên đóng gói trong JAR là một entry bên trong archive, ví dụ:

```text
application.jar
└── BOOT-INF/classes/
    └── templates/
        └── report-template.xlsx
```

Entry `templates/report-template.xlsx` không nhất thiết tồn tại như một tệp độc lập trong thư mục triển khai. Khi chạy ứng dụng từ IDE, tài nguyên có thể nằm trong `target/classes` hoặc `build/resources/main`, nên một số cách truy cập có vẻ hoạt động. Khi chạy ứng dụng từ executable JAR, tài nguyên có thể được đọc thông qua class loader từ bên trong archive hoặc từ cấu trúc JAR lồng nhau.

Vì vậy, không nên giả định mọi tài nguyên classpath đều có thể chuyển thành `File` hoặc `Path`. Nếu chỉ cần đọc nội dung, hãy dùng `InputStream`:

```java
import java.io.IOException;
import java.io.InputStream;

public final class TemplateReader {

    public byte[] readTemplate() throws IOException {
        try (InputStream input = TemplateReader.class
                .getResourceAsStream("/templates/report-template.xlsx")) {
            if (input == null) {
                throw new IOException("Template resource was not found");
            }
            return input.readAllBytes();
        }
    }
}
```

`getResourceAsStream()` hoạt động với tài nguyên trên classpath mà không yêu cầu tài nguyên phải là một tệp độc lập. Dấu `/` ở đầu tên tài nguyên trong `Class.getResourceAsStream()` biểu thị đường dẫn tính từ gốc classpath. Nếu dùng `ClassLoader.getResourceAsStream()`, tên thường không có dấu `/` ở đầu.

Đối với dữ liệu lớn, có thể xử lý trực tiếp theo luồng thay vì đọc toàn bộ vào `byte[]`, nhằm tránh tăng bộ nhớ heap. Chỉ nên trích xuất ra filesystem khi API tiếp theo bắt buộc nhận một đường dẫn tệp.

## 2. Đường dẫn tương đối và đường dẫn tuyệt đối

Đường dẫn tương đối được phân giải dựa trên thư mục làm việc hiện tại của tiến trình. Ví dụ:

```java
Path relative = Path.of("data/input.csv");
Path absolute = relative.toAbsolutePath();

System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("relative = " + relative);
System.out.println("absolute = " + absolute);
```

Nếu ứng dụng được khởi chạy từ một thư mục khác, cùng một đường dẫn tương đối có thể trỏ đến một vị trí khác. Điều này thường xảy ra khi chuyển giữa IDE, lệnh chạy local, service manager, Docker container hoặc môi trường triển khai.

`toAbsolutePath()` chuyển đường dẫn tương đối thành đường dẫn tuyệt đối theo filesystem mặc định và thư mục làm việc của tiến trình. `normalize()` loại bỏ các thành phần `.` và `..` theo quy tắc cú pháp của đường dẫn. Hai thao tác này không chứng minh tệp tồn tại, không kiểm tra quyền truy cập và không đảm bảo đường dẫn có thể dùng trên một máy khác.

```java
Path configured = Path.of("./data/../data/input.csv");
Path absoluteNormalized = configured.toAbsolutePath().normalize();

System.out.println(absoluteNormalized);

if (Files.exists(absoluteNormalized)) {
    Path actual = absoluteNormalized.toRealPath();
    System.out.println("resolved existing path = " + actual);
}
```

`toRealPath()` yêu cầu đường dẫn tồn tại và có thể truy cập; nó phân giải các liên kết symbolic theo tùy chọn được dùng. Vì vậy, hãy phân biệt:

| API | Ý nghĩa | Điều không được bảo đảm |
|---|---|---|
| `Path.of("data/a.txt")` | Tạo biểu diễn đường dẫn | Không tự tạo tệp hoặc thư mục |
| `toAbsolutePath()` | Chuyển thành đường dẫn tuyệt đối | Không bảo đảm tệp tồn tại hoặc tồn tại sau restore |
| `normalize()` | Chuẩn hóa thành phần `.` và `..` | Không truy cập filesystem để xác minh |
| `toRealPath()` | Phân giải đường dẫn hiện có trên filesystem | Không bảo đảm mount hoặc nội dung giữ nguyên trong tương lai |

Với dữ liệu cần tồn tại qua nhiều lần khởi động, nên cấu hình một thư mục làm việc rõ ràng thay vì dựa vào thư mục hiện tại. Ví dụ, lấy `app.data-dir` từ cấu hình triển khai, chuyển nó thành đường dẫn tuyệt đối và tạo thư mục nếu được phép:

```java
Path dataDirectory = Path.of(configuredDataDirectory)
        .toAbsolutePath()
        .normalize();

Files.createDirectories(dataDirectory);

Path inputFile = dataDirectory.resolve("input.csv");
```

Đường dẫn tuyệt đối giúp giảm sự phụ thuộc vào current working directory, nhưng nó vẫn gắn với filesystem của môi trường. Nếu restore sang container hoặc host khác, cùng chuỗi đường dẫn có thể không tồn tại hoặc trỏ đến mount có nội dung khác. Với dữ liệu quan trọng, hãy dùng volume được quản lý hoặc kho lưu trữ bền vững và xác minh lại đường dẫn sau restore.

## 3. Tạo và quản lý tệp tạm

Tệp tạm phù hợp cho dữ liệu trung gian chỉ cần tồn tại trong một khoảng thời gian, chẳng hạn kết quả giải nén, nội dung chuyển đổi, dữ liệu gửi cho một thư viện chỉ nhận `File`, hoặc đầu vào cho một tiến trình native.

Nên dùng `Files.createTempFile()` hoặc `Files.createTempDirectory()` thay vì tự ghép tên tệp trong `/tmp` hay thư mục tạm của Windows:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TemporaryFiles {

    public Path createWorkFile() throws IOException {
        Path temporaryFile = Files.createTempFile(
                "myapp-job-",
                ".tmp");

        Files.writeString(temporaryFile, "temporary work data");
        return temporaryFile;
    }
}
```

Nếu cần đặt tệp trong một thư mục cụ thể, hãy truyền thư mục đó vào API:

```java
Path workDirectory = Path.of(configuredWorkDirectory)
        .toAbsolutePath()
        .normalize();

Files.createDirectories(workDirectory);

Path temporaryFile = Files.createTempFile(
        workDirectory,
        "conversion-",
        ".bin");
```

API tạo tệp tạm sinh tên duy nhất và tạo tệp trong thao tác của filesystem, giúp tránh kiểu lỗi tự ghép một tên cố định rồi nhiều tiến trình cùng ghi vào. Không nên tạo đường dẫn từ dữ liệu người dùng mà không kiểm tra phạm vi thư mục, vì thành phần `..` hoặc symbolic link có thể làm đường dẫn thoát khỏi thư mục dự kiến.

### Vòng đời của tệp tạm

Tệp tạm cần có chủ sở hữu và thời điểm xóa rõ ràng. Với công việc ngắn trong một lần gọi, có thể dùng `try/finally`:

```java
Path temporaryFile = Files.createTempFile("myapp-", ".tmp");
try {
    generateIntermediateData(temporaryFile);
    consumeIntermediateData(temporaryFile);
} finally {
    Files.deleteIfExists(temporaryFile);
}
```

Với tệp được một bean hoặc dịch vụ sử dụng trong suốt vòng đời ứng dụng, cần quản lý nó theo vòng đời của thành phần. Có thể giữ `Path` trong field, nhưng sau restore phải xác minh tệp còn tồn tại và có đúng nội dung. Nếu tệp chỉ là dữ liệu có thể tái tạo, cách đơn giản là xóa trước checkpoint rồi tạo lại sau restore.

Không nên xem `File.deleteOnExit()` là cơ chế quản lý vòng đời cho checkpoint. Lệnh này đăng ký xóa tệp khi JVM kết thúc bình thường; checkpoint không phải là một lần shutdown bình thường và không làm cho hook xóa tệp chạy tại thời điểm chụp. Hơn nữa, việc restore không tự khôi phục nội dung tệp đã bị filesystem xóa.

### Tệp tạm không phải kho lưu trữ bền vững

Thư mục hệ thống tạm có thể được dọn bởi hệ điều hành, container runtime, job cleanup hoặc chính ứng dụng. Trong một số môi trường, thư mục `/tmp` nằm trên filesystem tạm hoặc bị xóa khi container thay thế. Một đường dẫn được lưu trong heap có thể vẫn là chuỗi hợp lệ trong khi file đã biến mất.

Nếu dữ liệu cần thiết để tiếp tục nghiệp vụ sau restore, không nên chỉ lưu nó trong tệp tạm. Hãy lưu dữ liệu vào volume bền vững, database, object storage hoặc một kho lưu trữ có vòng đời được quản lý. Tệp tạm chỉ nên chứa dữ liệu có thể tạo lại hoặc dữ liệu mà ứng dụng có thể phục hồi từ nguồn bền vững.

## 4. Checkpoint lưu trạng thái tiến trình, không tự đóng gói filesystem

CRaC tập trung vào trạng thái tiến trình. Nội dung của một tệp thông thường vẫn thuộc filesystem và cơ chế checkpoint/restore của hệ điều hành. Không nên giả định rằng tạo checkpoint sẽ sao chép tất cả tệp mà ứng dụng đã đọc hoặc ghi vào checkpoint artifact.

Ví dụ, ứng dụng tạo tệp `/tmp/report-123.bin`, lưu `Path` vào một field rồi checkpoint. Sau một khoảng thời gian, hệ thống có thể dọn `/tmp/report-123.bin`. Khi restore, field vẫn chứa đường dẫn cũ, nhưng `Files.exists(path)` có thể trả về `false`.

```java
if (Files.exists(temporaryFile)) {
    process(temporaryFile);
} else {
    temporaryFile = regenerateTemporaryFile();
}
```

Kiểm tra tồn tại là cần thiết nhưng đôi khi chưa đủ. Tệp có thể tồn tại nhưng nội dung đã thay đổi, quyền truy cập đã đổi hoặc tệp thuộc một lần chạy khác. Với dữ liệu có thể tái tạo, nên kiểm tra checksum, version hoặc metadata cần thiết. Với dữ liệu quan trọng, dùng một nguồn sự thật bền vững và giao thức ghi dữ liệu an toàn.

### Khi nào có thể giữ tệp qua checkpoint?

Có thể giữ tệp nếu môi trường triển khai bảo đảm filesystem và mount tương ứng tiếp tục khả dụng, nội dung không bị thay đổi ngoài dự kiến và ứng dụng có cách xác minh nó sau restore. Ví dụ, một tệp trên persistent volume được mount ổn định có thể được giữ lại nếu chính sách triển khai bảo đảm mount đó được gắn vào tiến trình được restore.

Ngay cả khi tệp được giữ lại, các handle đang mở, file lock, memory mapping và trạng thái thư viện native cần được đánh giá riêng. Hãy tuân theo hướng dẫn của JDK CRaC, hệ điều hành và thư viện đang sử dụng. Một `Path` tồn tại không đồng nghĩa một `FileChannel` hoặc lock cũ có thể dùng an toàn sau restore.

## 5. Đọc tài nguyên được đóng gói trong JAR

Với tài nguyên chỉ cần đọc, nên dùng class loader hoặc `Class.getResourceAsStream()`:

```java
try (InputStream input = MyService.class
        .getResourceAsStream("/templates/email.html")) {
    if (input == null) {
        throw new IOException("email.html was not found on the classpath");
    }

    String template = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8);
}
```

Cách này hoạt động khi tài nguyên nằm trong thư mục classpath lúc phát triển và khi nó được đóng gói bên trong JAR. Nó cũng tránh giả định rằng URL tài nguyên luôn là một đường dẫn filesystem thông thường.

### Vì sao `getResource(...).getFile()` có thể thất bại?

Trong môi trường phát triển, URL tài nguyên có thể có dạng `file:/.../classes/templates/email.html`. Khi chạy từ JAR, URL có thể có dạng `jar:file:/.../application.jar!/templates/email.html` hoặc một dạng URL do class loader của framework cung cấp. Phần `!/templates/email.html` chỉ một entry bên trong archive, không phải một thư mục trên filesystem.

Vì vậy, đoạn mã sau không có tính tổng quát:

```java
URL resource = MyService.class.getResource("/templates/email.html");
File file = new File(resource.getFile());
```

Nó có thể chạy trong IDE rồi thất bại khi ứng dụng được đóng gói. `Paths.get(resource.toURI())` cũng chỉ dùng trực tiếp được khi URI thuộc filesystem provider phù hợp, chẳng hạn scheme `file`. URI scheme `jar` không tự biến entry trong JAR thành `Path` của filesystem mặc định.

Java có Zip/JAR filesystem provider và có thể mở archive thành một `FileSystem` trong một số trường hợp, nhưng cách đó yêu cầu quản lý vòng đời filesystem, xử lý archive lồng nhau và phụ thuộc vào class loader/cách đóng gói. Với ứng dụng cần chạy trên nhiều môi trường, `InputStream` thường là lựa chọn đơn giản và ổn định hơn.

## 6. Khi API cần một đường dẫn tệp: trích xuất tài nguyên từ JAR

Một số thư viện chỉ nhận đường dẫn tệp thay vì `InputStream`. Khi đó, hãy sao chép tài nguyên classpath sang một tệp tạm do ứng dụng quản lý:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ResourceExtractor {

    public Path extractSchema() throws IOException {
        try (InputStream input = ResourceExtractor.class
                .getResourceAsStream("/schemas/customer.schema")) {
            if (input == null) {
                throw new IOException("customer.schema was not found");
            }

            Path extracted = Files.createTempFile(
                    "customer-schema-",
                    ".schema");
            try {
                Files.copy(input, extracted,
                        StandardCopyOption.REPLACE_EXISTING);
                return extracted;
            } catch (IOException exception) {
                Files.deleteIfExists(extracted);
                throw exception;
            }
        }
    }
}
```

Sau khi trích xuất, truyền `Path` tuyệt đối cho API cần tệp. Đóng `InputStream` ngay sau khi sao chép để không giữ handle của archive lâu hơn cần thiết. Nếu thư viện sử dụng tệp trong thời gian dài, hãy xác định ai sở hữu tệp và thời điểm được phép xóa nó.

Nếu tệp trích xuất là dữ liệu nhỏ, có thể đọc nó thành `byte[]` trước checkpoint và tạo lại tệp từ mảng byte sau restore. Nếu dữ liệu lớn, đọc lại từ JAR sau restore để tránh giữ thêm một bản sao lớn trong heap. Trong cả hai trường hợp, cần bảo đảm JAR và class loader còn khả dụng khi thao tác trích xuất diễn ra.

### Tài nguyên cần quyền thực thi

Một số thư viện native hoặc công cụ ngoài cần tệp được trích xuất có quyền thực thi. Tệp được tạo bởi `createTempFile()` không mặc nhiên có cùng quyền như tệp gốc trên mọi hệ điều hành. Hãy đặt quyền tối thiểu cần thiết theo nền tảng, kiểm tra kết quả thao tác và không giả định API quyền POSIX có sẵn trên Windows. Với native library, nên ưu tiên cơ chế tải tài nguyên được thư viện hỗ trợ; việc trích xuất và nạp thư viện native còn có các ràng buộc riêng về kiến trúc, ABI và vòng đời của native state khi checkpoint/restore.

## 7. Quản lý tệp trích xuất qua vòng đời CRaC

Nếu tệp trích xuất chỉ là dữ liệu tạm có thể tạo lại từ tài nguyên JAR, có thể xóa nó trước checkpoint và trích xuất lại sau restore. Điều này tránh phụ thuộc vào việc thư mục tạm có được giữ nguyên hay không.

Ví dụ dưới đây minh họa một resource quản lý tệp trích xuất:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class ExtractedSchema implements Resource {

    private volatile Path file;

    public ExtractedSchema() throws IOException {
        file = extract();
        Core.getGlobalContext().register(this);
    }

    public Path getFile() {
        Path current = file;
        if (current == null || !Files.isRegularFile(current)) {
            throw new IllegalStateException("Schema file is not ready");
        }
        return current;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopUsersAndWait();
        if (file != null) {
            Files.deleteIfExists(file);
            file = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        file = extract();
        resumeUsers();
    }

    private Path extract() throws IOException {
        try (InputStream input = ExtractedSchema.class
                .getResourceAsStream("/schemas/customer.schema")) {
            if (input == null) {
                throw new IOException("customer.schema was not found");
            }

            Path target = Files.createTempFile("customer-schema-", ".schema");
            try {
                Files.copy(input, target,
                        StandardCopyOption.REPLACE_EXISTING);
                return target;
            } catch (IOException exception) {
                Files.deleteIfExists(target);
                throw exception;
            }
        }
    }

    private void stopUsersAndWait() throws Exception {
        // Ngừng lời gọi mới và chờ các consumer đang dùng file kết thúc.
    }

    private void resumeUsers() {
        // Cho phép consumer sử dụng file mới sau khi trích xuất thành công.
    }
}
```

Các phương thức `stopUsersAndWait()` và `resumeUsers()` là điểm tích hợp với ứng dụng thực tế. Trước khi xóa tệp, phải bảo đảm không còn thread đang đọc hoặc ghi nó. Nếu việc drain thất bại, callback cần báo lỗi để checkpoint không tiếp tục trong trạng thái không an toàn. Sau restore, chỉ resume consumer khi tệp đã được tạo và xác minh thành công.

Ví dụ này giả định tài nguyên trong JAR có thể đọc lại sau restore. Nếu class loader hoặc archive không còn khả dụng, hãy dùng một nguồn bền vững hoặc lưu dữ liệu phù hợp trong bộ nhớ trước checkpoint. Nếu tệp phải tồn tại qua checkpoint vì một tiến trình native cần tiếp tục sử dụng nó, không xóa tệp; thay vào đó, đặt nó trên filesystem được bảo đảm tồn tại, kiểm tra nội dung và quyền truy cập sau restore, đồng thời xử lý các handle/native state theo hướng dẫn tương ứng.

## 8. Tệp tuyệt đối, thư mục làm việc và môi trường container

Trong container, đường dẫn tuyệt đối vẫn chỉ có ý nghĩa bên trong filesystem namespace mà container nhìn thấy. Ví dụ `/app/data/input.csv` có thể tồn tại trong một container hiện tại nhưng không có trong container mới nếu thư mục đó không nằm trên volume được mount. Tương tự, `/tmp` thường thích hợp cho dữ liệu tạm trong một vòng đời ngắn nhưng không nên dùng làm kho lưu trữ cần tồn tại lâu dài.

Hãy phân biệt các vị trí sau:

| Vị trí | Mục đích phù hợp | Cần lưu ý khi restore |
|---|---|---|
| Classpath/JAR | Tài nguyên chỉ đọc, đóng gói cùng ứng dụng | Đọc qua class loader; archive phải còn khả dụng khi cần đọc lại |
| Thư mục tạm hệ thống | Dữ liệu trung gian có thể tạo lại | Có thể bị dọn hoặc thay đổi; kiểm tra và tái tạo |
| Thư mục làm việc được cấu hình | File ứng dụng cần đường dẫn rõ ràng | Xác minh thư mục, quyền và mount sau restore |
| Persistent volume | Dữ liệu cần tồn tại qua thay thế tiến trình/container | Kiểm tra volume được mount đúng và nội dung nhất quán |
| Database/object storage | Dữ liệu nghiệp vụ hoặc dữ liệu bền vững | Dùng giao thức truy cập và xác thực lại sau restore |

Không nên hard-code một đường dẫn riêng cho máy phát triển rồi kỳ vọng nó hoạt động trong container. Cấu hình base directory theo môi trường, tạo thư mục nếu phù hợp và xác minh quyền đọc/ghi khi ứng dụng khởi động hoặc restore.

## 9. File handle, stream và memory mapping

Đường dẫn và handle là hai khái niệm khác nhau. `Path` mô tả vị trí; `InputStream`, `OutputStream`, `FileChannel` và memory mapping đại diện cho tài nguyên đang mở hoặc vùng dữ liệu gắn với filesystem.

Ví dụ, đóng một `InputStream` không xóa tệp. Xóa một tệp không nhất thiết đóng mọi handle đang mở. Trên một số hệ điều hành, việc xóa hoặc đổi tên một tệp đang được mở có hành vi khác nhau. File lock và memory mapping còn phụ thuộc vào khả năng của hệ điều hành và cơ chế checkpoint/restore.

Trước checkpoint:

- Đóng stream và channel không cần giữ.
- Flush dữ liệu cần được ghi bền vững.
- Chờ thao tác ghi đang diễn ra hoàn tất.
- Nhả lock nếu quyền sở hữu cần được xác lập lại.
- Kiểm tra hỗ trợ của thư viện đối với file descriptor, memory mapping và native handle.

Sau restore:

- Mở lại stream/channel từ đường dẫn đã xác minh.
- Kiểm tra nội dung và version nếu file có thể thay đổi bên ngoài.
- Lấy lại lock hoặc lease theo cơ chế hiện hành.
- Chỉ tiếp tục công việc sau khi handle mới ở trạng thái hợp lệ.

Không nên giả định `FileChannel` hoặc native handle còn hợp lệ chỉ vì field Java chứa chúng đã được khôi phục. Chủ sở hữu tài nguyên cần có chiến lược mở lại hoặc dùng integration CRaC tương ứng.

## 10. Các lỗi thường gặp

### Dùng `getResource().getFile()` với ứng dụng đóng gói JAR

Tài nguyên có thể nằm trong archive hoặc JAR lồng nhau, không phải file riêng. Hãy dùng `getResourceAsStream()` để đọc và trích xuất ra tệp tạm khi API yêu cầu đường dẫn.

### Dùng đường dẫn tương đối phụ thuộc thư mục khởi chạy

Ứng dụng có thể chạy từ IDE, service manager hoặc container với working directory khác nhau. Hãy cấu hình thư mục gốc rõ ràng và resolve đường dẫn từ thư mục đó.

### Cho rằng đường dẫn tuyệt đối bảo đảm tệp tồn tại

Đường dẫn tuyệt đối chỉ loại bỏ sự mơ hồ của working directory. Nó không bảo đảm filesystem, mount, nội dung hoặc quyền truy cập được giữ nguyên sau restore.

### Dùng `/tmp` cho dữ liệu cần tồn tại lâu dài

Thư mục tạm có thể bị dọn khi tiến trình hoặc container thay đổi. Dữ liệu cần phục hồi phải nằm trong volume hoặc kho lưu trữ bền vững.

### Dựa vào `deleteOnExit()` để xóa trước checkpoint

Checkpoint không phải shutdown bình thường. Hãy xóa tệp trong callback `beforeCheckpoint` nếu đó là chính sách phù hợp, hoặc dùng một cơ chế cleanup riêng có thể quan sát.

### Giữ `Path` trong heap và không kiểm tra lại sau restore

Field có thể giữ nguyên chuỗi đường dẫn trong khi file đã biến mất. Hãy kiểm tra tồn tại, loại tệp, quyền và nội dung/version; nếu có thể tái tạo thì tạo lại.

### Xóa tệp khi vẫn còn thread sử dụng

Một consumer có thể đang đọc file trong lúc callback xóa nó. Hãy ngừng nhận việc mới và drain người dùng tệp trước khi xóa hoặc đóng handle.

## 11. Hướng dẫn lựa chọn cách lưu trữ

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Đọc template hoặc schema đóng gói trong JAR | `getResourceAsStream()` |
| Thư viện cần một file path cho tài nguyên trong JAR | Trích xuất bằng `Files.createTempFile()` và quản lý vòng đời |
| Dữ liệu trung gian chỉ dùng trong một thao tác | Tệp tạm, xóa trong `finally` |
| Dữ liệu tạm được dùng qua nhiều bước trước checkpoint | Resource sở hữu tệp; drain, xóa/tạo lại hoặc xác minh sau restore |
| File cần tồn tại qua thay thế tiến trình/container | Persistent volume hoặc kho lưu trữ bền vững |
| File cấu hình triển khai | Đường dẫn tuyệt đối được cấu hình, kiểm tra lại sau restore |
| Dữ liệu nghiệp vụ cần phục hồi chính xác | Database, object storage hoặc workflow store; không chỉ dựa vào heap hay `/tmp` |

## 12. Kết luận

Tệp tạm, đường dẫn tuyệt đối và tài nguyên trong JAR có vòng đời khác nhau. Tệp tạm phù hợp với dữ liệu trung gian có thể tái tạo và cần được tạo/xóa theo một chủ sở hữu rõ ràng. Đường dẫn tuyệt đối giúp tránh phụ thuộc vào thư mục làm việc, nhưng không bảo đảm tệp hoặc mount còn tồn tại sau restore. Tài nguyên đóng gói trong JAR nên được đọc qua class loader; chỉ trích xuất thành tệp khi API tiếp theo thực sự cần một đường dẫn filesystem.

Trong ứng dụng CRaC, hãy nhớ rằng trạng thái `Path` trong heap không đồng nghĩa nội dung file được đóng gói trong checkpoint. Trước checkpoint, drain người dùng tệp và đóng các handle cần xử lý. Sau restore, xác minh filesystem, tạo lại tệp tạm có thể tái tạo, đọc lại tài nguyên JAR khi cần và chỉ tiếp tục xử lý khi đường dẫn cùng nội dung đã hợp lệ. Dữ liệu cần tồn tại lâu dài phải được lưu ở một nơi có bảo đảm bền vững.
