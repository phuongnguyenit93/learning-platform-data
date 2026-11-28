# Kiểm tra tồn tại, quyền truy cập và loại của đường dẫn

Một command Spring Shell nhận đường dẫn thường cần trả lời ba câu hỏi trước khi xử lý: mục được chỉ định có tồn tại không, tiến trình có thể thực hiện thao tác cần thiết không và mục đó có đúng loại mà command mong đợi không. Ví dụ, command nhập dữ liệu cần một file thường có thể đọc; command liệt kê cần một thư mục có thể mở; command xuất báo cáo cần một đường dẫn đích mà tiến trình có thể tạo hoặc ghi.

Spring Shell nhận option và chuyển giá trị vào command target. Việc một chuỗi có thể biểu diễn thành đường dẫn chỉ cho biết cú pháp đầu vào có thể phân tích được; nó không chứng minh file tồn tại, có quyền truy cập hoặc là file thường. Những kiểm tra này thuộc về Java NIO, đặc biệt là lớp Files và thao tác I/O thực tế của ứng dụng.

Spring Shell hỗ trợ khai báo command, xử lý đối số, validation, trợ giúp và tự hoàn thành. Bài này tập trung vào kiểm tra đường dẫn trước khi đọc, liệt kê hoặc ghi dữ liệu, đồng thời giải thích cách báo lỗi rõ ràng và xử lý các thay đổi có thể xảy ra giữa lúc kiểm tra với lúc thao tác.

Sau bài này, bạn có thể:

- Nhận đường dẫn từ option của Spring Shell và chuyển thành Path.
- Phân biệt đường dẫn không hợp lệ, không tồn tại, không truy cập được và sai loại.
- Dùng Files.readAttributes, isRegularFile, isDirectory, isReadable và isWritable.
- Kiểm tra đường dẫn đầu vào và đường dẫn đầu ra theo yêu cầu của command.
- Xử lý InvalidPathException, NoSuchFileException, AccessDeniedException và IOException.
- Hiểu giới hạn của kiểm tra quyền trước thao tác và tránh lỗi TOCTOU.
- Giới hạn đường dẫn trong thư mục được phép khi ứng dụng cần vùng dữ liệu an toàn.

> Các ví dụ command dùng API annotation legacy @ShellComponent, @ShellMethod và @ShellOption có trong Spring Shell 3.x. Phần kiểm tra filesystem dùng Java NIO (Path, Files) và áp dụng độc lập với mô hình đăng ký command.

## 1. Ba nhóm kiểm tra đường dẫn

Một đường dẫn hợp lệ về mặt cú pháp vẫn có thể không dùng được cho mục đích của command. Hãy kiểm tra riêng ba nhóm:

| Nhóm | Câu hỏi | API thường dùng |
|---|---|---|
| Tồn tại | Mục được chỉ định có tồn tại không? | Files.exists, Files.notExists, Files.readAttributes |
| Quyền truy cập | Tiến trình có thể đọc, ghi hoặc thực thi không? | Files.isReadable, Files.isWritable, Files.isExecutable; sau đó thực hiện I/O thật |
| Loại mục | Đó là file thường, thư mục, symbolic link hay loại khác? | Files.isRegularFile, Files.isDirectory, Files.isSymbolicLink, BasicFileAttributes |

Yêu cầu của từng command quyết định loại nào được chấp nhận:

- file import thường yêu cầu file thường, tồn tại và đọc được.
- directory list yêu cầu thư mục, đồng thời tiến trình có thể mở và liệt kê nội dung.
- report export có thể yêu cầu thư mục cha tồn tại và có quyền tạo file; file đích nếu đã tồn tại phải đúng loại và có thể ghi.
- script run có thể yêu cầu file thường, đọc được và có phần mở rộng phù hợp nếu ứng dụng đặt quy ước đó.

Không có một kiểm tra chung như exists() có thể thay thế tất cả các điều kiện trên.

## 2. Nhận chuỗi và chuyển thành Path

Trong command, có thể nhận đường dẫn dưới dạng String, sau đó chuyển bằng Path.of(...). Cách này giúp ứng dụng kiểm soát rõ lỗi cú pháp và cách xử lý đường dẫn tương đối.

~~~java
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

public Path parsePath(String rawPath) {
    if (rawPath == null || rawPath.isBlank()) {
        throw new IllegalArgumentException("Bạn phải cung cấp đường dẫn.");
    }

    try {
        return Path.of(rawPath).toAbsolutePath().normalize();
    } catch (InvalidPathException ex) {
        throw new IllegalArgumentException(
                "Đường dẫn không hợp lệ: " + rawPath, ex);
    }
}
~~~

Path.of(...) tạo đối tượng biểu diễn đường dẫn theo file system provider hiện tại. Nó không truy cập filesystem để xác nhận mục có tồn tại hay không.

toAbsolutePath() chuyển đường dẫn tương đối thành đường dẫn tuyệt đối dựa trên thư mục làm việc hiện tại của tiến trình Java. normalize() loại bỏ các thành phần dư thừa về mặt cú pháp như . và một số cặp ..; phương thức này không kiểm tra filesystem và không giải quyết symbolic link.

Ví dụ, nếu ứng dụng chạy với thư mục làm việc là C:/apps/my-shell, đầu vào tương đối data/orders.csv được phân giải dựa trên thư mục đó. Khi cần thư mục gốc cố định, hãy cấu hình rõ ràng trong ứng dụng thay vì phụ thuộc thư mục người dùng đang mở terminal.

Trong terminal, đường dẫn có dấu cách nên được đặt trong dấu nháy:

~~~text
file inspect --path "data/import files/orders.csv"
~~~

Đường dẫn Windows có dấu gạch chéo ngược và đường dẫn Unix có dấu gạch chéo xuôi được xử lý theo file system provider đang dùng. Không tự nối chuỗi bằng dấu phân cách cố định; dùng Path.resolve(...) để ghép các thành phần.

## 3. Kiểm tra file đầu vào tồn tại và đúng loại

Giả sử command file count-lines cần đọc một file văn bản. Điều kiện tối thiểu:

1. Đường dẫn có thể phân tích.
2. Mục tồn tại và đọc được thuộc tính.
3. Mục là file thường, không phải thư mục.
4. Tiến trình có quyền đọc theo kiểm tra hiện tại.
5. Khi mở file thật, thao tác đọc phải thành công.

Có thể gom logic kiểm tra vào service dùng chung:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

import org.springframework.stereotype.Service;

@Service
public class FilePathService {

    public Path requireReadableRegularFile(String rawPath) {
        Path path = parsePath(rawPath);

        try {
            BasicFileAttributes attributes =
                    Files.readAttributes(path, BasicFileAttributes.class);

            if (!attributes.isRegularFile()) {
                throw new IllegalArgumentException(
                        "Đường dẫn phải trỏ tới một file thường: " + path);
            }

            if (!Files.isReadable(path)) {
                throw new IllegalArgumentException(
                        "Tiến trình hiện không có quyền đọc file: " + path);
            }

            return path;
        } catch (NoSuchFileException ex) {
            throw new IllegalArgumentException(
                    "Không tìm thấy file: " + path, ex);
        } catch (AccessDeniedException ex) {
            throw new IllegalArgumentException(
                    "Không có quyền truy cập file: " + path, ex);
        } catch (IOException ex) {
            throw new IllegalArgumentException(
                    "Không thể kiểm tra file: " + path, ex);
        }
    }

    private Path parsePath(String rawPath) {
        if (rawPath == null || rawPath.isBlank()) {
            throw new IllegalArgumentException("Bạn phải cung cấp đường dẫn.");
        }
        try {
            return Path.of(rawPath).toAbsolutePath().normalize();
        } catch (InvalidPathException ex) {
            throw new IllegalArgumentException("Đường dẫn không hợp lệ.", ex);
        }
    }
}
~~~

Files.readAttributes(...) đọc thuộc tính filesystem và có thể phân biệt trường hợp không tìm thấy mục với lỗi I/O hoặc từ chối truy cập. BasicFileAttributes.isRegularFile() xác nhận mục là file thường. Files.isReadable() kiểm tra quyền đọc hiệu lực mà JVM có thể xác định tại thời điểm gọi.

### Dùng kiểm tra trong command

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
import java.nio.file.Path;

@ShellComponent
public class FileCommands {

    private final FilePathService filePathService;

    public FileCommands(FilePathService filePathService) {
        this.filePathService = filePathService;
    }

    @ShellMethod(key = "file inspect", value = "Kiểm tra file đầu vào.")
    public String inspect(@ShellOption("--path") String rawPath) {
        Path path = filePathService.requireReadableRegularFile(rawPath);
        return "File hợp lệ để đọc: " + path;
    }
}
~~~

Phương thức command chỉ điều phối đầu vào và gọi service. Khi có thêm REST endpoint hoặc batch job cần đọc cùng loại file, chúng có thể tái sử dụng FilePathService mà không phải sao chép điều kiện filesystem.

## 4. Kiểm tra thư mục

Một command liệt kê thư mục cần kiểm tra thư mục tồn tại và đúng loại. Sau đó, thao tác liệt kê mới xác nhận tiến trình thực sự có thể mở thư mục:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.NotDirectoryException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public List<String> listDirectory(Path directory) {
    if (!Files.isDirectory(directory)) {
        throw new IllegalArgumentException(
                "Đường dẫn không phải thư mục: " + directory);
    }
    if (!Files.isReadable(directory)) {
        throw new IllegalArgumentException(
                "Không có quyền đọc thư mục: " + directory);
    }

    List<String> names = new ArrayList<>();
    try (DirectoryStream<Path> entries = Files.newDirectoryStream(directory)) {
        for (Path entry : entries) {
            names.add(entry.getFileName().toString());
        }
        return names;
    } catch (NotDirectoryException ex) {
        throw new IllegalArgumentException("Đường dẫn không phải thư mục.", ex);
    } catch (AccessDeniedException ex) {
        throw new IllegalArgumentException("Không có quyền liệt kê thư mục.", ex);
    } catch (IOException ex) {
        throw new IllegalArgumentException("Không thể đọc thư mục.", ex);
    }
}
~~~

DirectoryStream được đóng bằng try-with-resources để giải phóng tài nguyên sau khi duyệt.

Trên một số filesystem, quyền liệt kê thư mục còn phụ thuộc quyền search/traverse trên thư mục và các thư mục cha. Vì vậy, isReadable() chỉ là kiểm tra sơ bộ; Files.newDirectoryStream(...) mới thực hiện thao tác mở thư mục mà command cần.

## 5. Kiểm tra đường dẫn đầu ra

Đường dẫn đầu ra khác đường dẫn đầu vào. File đích có thể chưa tồn tại; trong trường hợp đó, cần kiểm tra thư mục cha và chính sách tạo file.

Giả sử command xuất báo cáo tới reports/monthly.csv. Có thể áp dụng các điều kiện:

- Thư mục cha phải tồn tại và là thư mục.
- Tiến trình phải có quyền tạo file trong thư mục cha.
- Nếu file đích đã tồn tại, nó phải là file thường và có thể ghi.
- Nếu không xác định được trạng thái tồn tại do lỗi truy cập metadata, từ chối xử lý và báo rõ.

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public Path requireWritableTarget(String rawPath) {
    if (rawPath == null || rawPath.isBlank()) {
        throw new IllegalArgumentException("Bạn phải cung cấp đường dẫn đầu ra.");
    }

    final Path target;
    try {
        target = Path.of(rawPath).toAbsolutePath().normalize();
    } catch (InvalidPathException ex) {
        throw new IllegalArgumentException("Đường dẫn đầu ra không hợp lệ.", ex);
    }

    Path parent = target.getParent();
    if (parent == null || !Files.isDirectory(parent)) {
        throw new IllegalArgumentException(
                "Thư mục cha không tồn tại, không phải thư mục hoặc không thể xác định: " + parent);
    }
    if (!Files.isWritable(parent)) {
        throw new IllegalArgumentException(
                "Không có quyền tạo file trong thư mục: " + parent);
    }

    if (Files.notExists(target)) {
        return target;
    }
    if (!Files.exists(target)) {
        throw new IllegalArgumentException(
                "Không thể xác định trạng thái của đường dẫn đầu ra: " + target);
    }

    try {
        BasicFileAttributes attributes =
                Files.readAttributes(target, BasicFileAttributes.class);
        if (!attributes.isRegularFile()) {
            throw new IllegalArgumentException(
                    "Đường dẫn đầu ra đã tồn tại nhưng không phải file thường: " + target);
        }
        if (!Files.isWritable(target)) {
            throw new IllegalArgumentException(
                    "Không có quyền ghi file hiện tại: " + target);
        }
        return target;
    } catch (AccessDeniedException ex) {
        throw new IllegalArgumentException(
                "Không có quyền kiểm tra file đầu ra: " + target, ex);
    } catch (IOException ex) {
        throw new IllegalArgumentException(
                "Không thể kiểm tra file đầu ra: " + target, ex);
    }
}
~~~

Files.exists() và Files.notExists() không phải hai kết quả luôn đối nghịch. Khi filesystem không thể xác định trạng thái, cả hai có thể trả về false. Vì vậy, code trên chỉ coi đường dẫn là chắc chắn chưa tồn tại khi notExists() trả về true; nếu cả hai đều false, command dừng lại thay vì giả định có thể tạo file.

### Thực hiện ghi thật

Sau khi kiểm tra, ứng dụng vẫn phải mở hoặc tạo file và xử lý IOException:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public void writeReport(Path target, String content) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            target,
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE)) {
        writer.write(content);
    }
}
~~~

Tổ hợp CREATE và TRUNCATE_EXISTING tạo file nếu chưa có, hoặc xóa nội dung cũ trước khi ghi nếu file đã tồn tại. Đây là chính sách ghi đè; nếu command không được phép ghi đè, hãy dùng CREATE_NEW để thao tác thất bại khi đích đã tồn tại. Cần công bố chính sách này trong trợ giúp command và chỉ ghi sau khi người dùng đã xác nhận nếu thao tác có thể làm mất dữ liệu.

## 6. Hiểu quyền truy cập trên filesystem

Files.isReadable, Files.isWritable và Files.isExecutable kiểm tra quyền hiệu lực mà JVM có thể xác định cho tiến trình hiện tại:

| API | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| Files.isReadable(path) | Có thể mở mục để đọc theo kiểm tra hiện tại | File nguồn cần import; thư mục cần liệt kê |
| Files.isWritable(path) | Có thể mở mục để ghi theo kiểm tra hiện tại | File đích đã tồn tại; thư mục cha cần tạo file |
| Files.isExecutable(path) | Có thể thực thi hoặc truy cập theo quyền execute của filesystem | Script hoặc chương trình cần được thực thi |

Các kiểm tra này không chỉ đọc bit quyền POSIX. Tùy filesystem và hệ điều hành, kết quả có thể phụ thuộc ACL, quyền của tài khoản chạy JVM, mount option, container và các cơ chế kiểm soát truy cập khác.

Không nên đọc permission bit rồi tự kết luận người dùng có thể thao tác. Ví dụ trên hệ thống Unix, quyền đọc file có thể được cấp cho group hoặc ACL; trên Windows, quyền truy cập có thể được điều khiển bởi ACL thay vì bộ bit POSIX.

### Quyền của file và quyền của thư mục

Để đọc một file, tiến trình cần quyền truy cập file và quyền đi qua các thư mục cha. Để tạo file mới, tiến trình thường cần quyền ghi và quyền traverse trên thư mục cha. Để liệt kê thư mục, tiến trình cần quyền mở thư mục và đọc danh sách entry. Vì vậy, kiểm tra file cuối cùng mà không xét thư mục cha có thể chưa đủ để giải thích lỗi.

Nếu cần chẩn đoán sâu trên POSIX filesystem, có thể đọc quyền bằng Files.getPosixFilePermissions(path). API này không được hỗ trợ trên mọi filesystem, nên không dùng làm cơ chế kiểm tra khả năng truy cập đa nền tảng. Với ứng dụng CLI đa nền tảng, ưu tiên API Files và xử lý lỗi I/O thực tế.

## 7. Phân biệt file thường, thư mục và symbolic link

Một đường dẫn có thể trỏ tới nhiều loại mục. Các phương thức kiểm tra loại phổ biến:

| API | Kết quả |
|---|---|
| Files.isRegularFile(path) | Mục được xem là file thường |
| Files.isDirectory(path) | Mục được xem là thư mục |
| Files.isSymbolicLink(path) | Chính mục được chỉ định là symbolic link |
| Files.readAttributes(path, BasicFileAttributes.class) | Đọc thuộc tính như regular file, directory, symbolic link và thời gian sửa đổi |

Mặc định, nhiều thao tác kiểm tra thuộc tính theo symbolic link để xem mục đích cuối cùng của link. Ví dụ, một symbolic link trỏ tới file thường có thể khiến Files.isRegularFile(link) trả về true, trong khi Files.isSymbolicLink(link) cũng trả về true.

Nếu ứng dụng cần kiểm tra chính link thay vì đích của nó, dùng LinkOption.NOFOLLOW_LINKS:

~~~java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attributes = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

if (attributes.isSymbolicLink()) {
    throw new IllegalArgumentException("Không chấp nhận symbolic link.");
}
~~~

Quyết định có chấp nhận symbolic link hay không tùy vào use case. Một CLI xử lý file cá nhân có thể chấp nhận link; công cụ chạy trên thư mục dữ liệu giới hạn hoặc thực hiện thao tác nhạy cảm có thể cần từ chối link hoặc xác minh đích thật.

## 8. Giới hạn đường dẫn trong thư mục được phép

Nếu command chỉ được đọc hoặc ghi bên trong một thư mục gốc, không nên chỉ nối chuỗi kiểu root + userInput. Người dùng có thể truyền ../ để đi ra ngoài thư mục, hoặc dùng symbolic link trỏ tới nơi khác.

Với đường dẫn tương đối, có thể chuẩn hóa và kiểm tra nó vẫn nằm dưới root:

~~~java
Path root = configuredRoot.toRealPath();
Path candidate = root.resolve(userInput).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException(
            "Đường dẫn phải nằm trong thư mục dữ liệu được phép.");
}
~~~

normalize() loại bỏ các thành phần . và .. trong biểu diễn đường dẫn, còn startsWith(root) kiểm tra quan hệ theo thành phần Path, không phải so sánh chuỗi tiền tố. Ví dụ /data/app-backup không được coi là nằm trong /data/app chỉ vì chuỗi bắt đầu giống nhau.

Kiểm tra này chưa xử lý hết symbolic link. Với file đã tồn tại, có thể gọi toRealPath() rồi kiểm tra đường dẫn thật nằm dưới root thật. Với file đầu ra chưa tồn tại, kiểm tra thư mục cha bằng toRealPath() và xác minh nó nằm dưới root; sau đó vẫn phải thực hiện thao tác tạo file và xử lý lỗi.

Không dựa vào normalize() để chống traversal trong ứng dụng có yêu cầu bảo mật cao. Hãy xác minh đường dẫn thật, chính sách symbolic link và quyền truy cập tại thời điểm mở file. Nếu cần thao tác chống race condition trên filesystem có hỗ trợ, cân nhắc API như SecureDirectoryStream.

## 9. Tổ chức validation trong Spring Shell

Spring Shell tích hợp Bean Validation để kiểm tra constraint trên tham số command trước khi gọi target. Có thể dùng constraint chuẩn để kiểm tra đầu vào rỗng:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellMethod(key = "file inspect", value = "Kiểm tra file đầu vào.")
public String inspect(
        @ShellOption("--path") @NotBlank String rawPath) {
    Path path = filePathService.requireReadableRegularFile(rawPath);
    return "File hợp lệ: " + path;
}
~~~

Ứng dụng Spring Boot cần có implementation Bean Validation, thường được thêm bằng dependency spring-boot-starter-validation. Spring Shell thực hiện validation constraint trước khi chạy command target.

Ví dụ khai báo dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

@NotBlank chỉ xác nhận chuỗi có nội dung. Nó không kiểm tra file có tồn tại, file có thể đọc hoặc đường dẫn có trỏ tới thư mục hay không. Các điều kiện phụ thuộc filesystem nên được kiểm tra trong service hoặc một custom constraint riêng. Dù dùng custom constraint, vẫn phải xử lý lỗi I/O ở thao tác thật vì trạng thái filesystem có thể thay đổi sau validation.

### Đặt trách nhiệm theo tầng

| Tầng | Trách nhiệm |
|---|---|
| Spring Shell command | Nhận option, kiểm tra đầu vào cơ bản, gọi service và chuyển lỗi thành thông báo CLI dễ hiểu |
| Path validation service | Phân tích đường dẫn, kiểm tra loại, thuộc tính và quyền truy cập dự kiến |
| Tầng thao tác I/O | Mở, đọc, liệt kê, tạo hoặc ghi file; xử lý lỗi thực tế từ filesystem |
| Domain/application service | Áp dụng quy tắc nghiệp vụ như loại file được phép import, thư mục export được phép và giới hạn dữ liệu |

Không nên để command chỉ kiểm tra một lần rồi service khác giả định file chắc chắn còn tồn tại. Tầng thực hiện I/O phải luôn xử lý exception từ chính thao tác đó.

## 10. Lỗi filesystem và thông báo phù hợp

Các exception thường gặp:

| Exception | Tình huống thường gặp | Thông báo gợi ý |
|---|---|---|
| InvalidPathException | Chuỗi không thể chuyển thành đường dẫn trên provider hiện tại | “Đường dẫn không hợp lệ.” |
| NoSuchFileException | Không tìm thấy file hoặc thư mục khi đọc thuộc tính hoặc mở | “Không tìm thấy đường dẫn được chỉ định.” |
| AccessDeniedException | Hệ điều hành hoặc filesystem từ chối thao tác | “Tiến trình không có quyền truy cập đường dẫn.” |
| NotDirectoryException | Command cần thư mục nhưng đường dẫn là file hoặc mục khác | “Đường dẫn phải là thư mục.” |
| FileAlreadyExistsException | Dùng CREATE_NEW nhưng file đích đã tồn tại | “File đích đã tồn tại; hãy chọn tên khác.” |
| IOException | Lỗi I/O khác, thiết bị, mạng, filesystem hoặc thao tác bị gián đoạn | “Không thể hoàn thành thao tác file.” |

Không nên bắt mọi exception rồi chỉ in “đường dẫn không hợp lệ”. Một đường dẫn có thể hợp lệ nhưng file không tồn tại; một file có thể tồn tại nhưng tiến trình không có quyền đọc; hoặc một thư mục có thể được truyền vào command chỉ chấp nhận file thường. Thông báo phân biệt đúng nguyên nhân giúp người dùng sửa đầu vào nhanh hơn.

Không đưa stack trace, thông tin nhạy cảm hoặc chi tiết nội bộ của máy chủ vào output mặc định. Ghi exception đầy đủ ở log phù hợp, còn CLI hiển thị thông báo có thể hành động.

## 11. Kiểm tra trước thao tác không thay thế thao tác thật

Có một khoảng thời gian giữa lúc kiểm tra Files.exists, Files.isReadable hoặc Files.isWritable và lúc mở file. Trong khoảng đó, file có thể bị xóa, thay thế, đổi quyền hoặc đổi symbolic link. Đây là dạng race condition thường được gọi là TOCTOU (time of check to time of use).

Ví dụ:

1. Command kiểm tra Files.isReadable(path) và nhận true.
2. Một tiến trình khác thay file hoặc thay quyền truy cập.
3. Command gọi Files.newBufferedReader(path) và nhận AccessDeniedException hoặc một lỗi I/O khác.

Do đó:

- Dùng kiểm tra thuộc tính để đưa ra thông báo sớm và dễ hiểu.
- Mở hoặc tạo file bằng API I/O thực tế và bắt IOException.
- Giữ file handle/stream mở trong lúc xử lý thay vì kiểm tra rồi mở lại nhiều lần không cần thiết.
- Với thao tác nhạy cảm, hạn chế symbolic link và kiểm soát thư mục cha.
- Không xem Files.isReadable() hoặc Files.isWritable() là cam kết rằng thao tác kế tiếp chắc chắn thành công.

## 12. Ví dụ luồng xử lý command hoàn chỉnh

Một command nhập file có thể phối hợp kiểm tra đầu vào và thao tác đọc như sau:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ImportCommands {

    private final FilePathService filePathService;

    public ImportCommands(FilePathService filePathService) {
        this.filePathService = filePathService;
    }

    @ShellMethod(key = "data import", value = "Đọc file dữ liệu đầu vào.")
    public String importData(@ShellOption("--source") String rawPath) {
        Path source = filePathService.requireReadableRegularFile(rawPath);

        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8)) {
            long lineCount = 0;
            while (reader.readLine() != null) {
                lineCount++;
            }
            return "Đã đọc " + lineCount + " dòng từ " + source;
        } catch (NoSuchFileException ex) {
            return "File không còn tồn tại: " + source;
        } catch (AccessDeniedException ex) {
            return "Không có quyền đọc file: " + source;
        } catch (IOException ex) {
            return "Không thể đọc file: " + source;
        }
    }
}
~~~

Ví dụ trên minh họa luồng xử lý; trong ứng dụng thật, service có thể trả về lỗi miền hoặc exception riêng để command xử lý thống nhất. Nếu command nhập dữ liệu lớn, hãy xử lý theo stream hoặc theo từng dòng thay vì tải toàn bộ file vào bộ nhớ.

Thử các tình huống:

~~~text
data import --source "data/orders.csv"
data import --source "data/missing.csv"
data import --source "data"
data import --source "data/restricted.csv"
~~~

Kết quả phụ thuộc filesystem, hệ điều hành, quyền của tài khoản chạy ứng dụng và nội dung thư mục kiểm thử. Mục tiêu là mỗi trường hợp được phân loại rõ ràng và không làm command tiếp tục đọc một mục sai loại.

## 13. Checklist kiểm tra đường dẫn

- Kiểm tra chuỗi rỗng trước khi chuyển đổi.
- Dùng Path.of(...) và xử lý InvalidPathException.
- Xác định rõ đường dẫn tương đối được tính từ thư mục làm việc nào.
- Kiểm tra tồn tại và đọc thuộc tính filesystem.
- Kiểm tra đúng loại: file thường hay thư mục.
- Kiểm tra quyền phù hợp với thao tác: đọc, ghi, liệt kê hoặc thực thi.
- Kiểm tra thư mục cha khi tạo file đầu ra.
- Quyết định rõ có chấp nhận symbolic link hay không.
- Nếu giới hạn trong thư mục gốc, xác minh đường dẫn thật và chống traversal.
- Thực hiện I/O thật và xử lý IOException, không dựa hoàn toàn vào kiểm tra trước.
- Dùng thông báo lỗi phân biệt nguyên nhân và hướng khắc phục.
- Kiểm thử trên hệ điều hành và filesystem mà ứng dụng sẽ hỗ trợ.

## 14. Bài tập thực hành

Xây dựng nhóm command data để nhập và xuất dữ liệu:

1. data inspect --path <path> hiển thị đường dẫn tuyệt đối, loại mục và trạng thái đọc được.
2. data import --source <path> chỉ chấp nhận file thường tồn tại và đọc được.
3. data list --directory <path> chỉ chấp nhận thư mục có thể liệt kê.
4. data export --output <path> chấp nhận file đích chưa tồn tại nếu thư mục cha có thể ghi; nếu file đã tồn tại, chỉ cho phép ghi đè khi người dùng truyền --overwrite.
5. Phân biệt đường dẫn sai cú pháp, không tồn tại, bị từ chối truy cập, sai loại và lỗi I/O xảy ra khi thao tác.
6. Thử symbolic link trỏ tới file thường, symbolic link trỏ tới thư mục và symbolic link bị hỏng.
7. Thử đường dẫn tương đối, đường dẫn tuyệt đối và đường dẫn có dấu cách.
8. Nếu command chỉ được làm việc trong một thư mục gốc, thử đầu vào có ../ và symbolic link dẫn ra ngoài thư mục đó.

Khi hoàn thành, hãy giải thích vì sao kiểm tra quyền trước thao tác chỉ mang tính dự báo và vì sao command vẫn cần bắt lỗi khi mở hoặc ghi file.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Validation](https://docs.spring.io/spring-shell/reference/3.3/options/validation.html): Bean Validation trên tham số command và thời điểm validation trước khi target được gọi.
- [Spring Shell 3.3 – Types](https://docs.spring.io/spring-shell/reference/3.3/options/types.html): cách Spring Shell xử lý các kiểu dữ liệu option được hỗ trợ.
- [Java SE 21 – Files API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): kiểm tra tồn tại, loại file, quyền truy cập và thao tác I/O.
- [Java SE 21 – Path API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): tạo, chuẩn hóa, phân giải và so sánh đường dẫn.
- [Java SE 21 – BasicFileAttributes API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): thuộc tính cơ bản của file và thư mục.
