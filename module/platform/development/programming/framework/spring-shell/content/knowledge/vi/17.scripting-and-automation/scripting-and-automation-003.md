# Đường dẫn tệp, thư mục làm việc và mã hóa văn bản

Script Spring Shell thường đọc lệnh từ một tệp, còn chính các command trong script có thể đọc hoặc ghi thêm cấu hình, dữ liệu và báo cáo. Những lỗi như “không tìm thấy file”, đọc nhầm thư mục, tiếng Việt thành ký tự lỗi hoặc script chạy được trong IDE nhưng thất bại trên máy khác thường xuất phát từ ba yếu tố: đường dẫn, thư mục làm việc và encoding.

Để script chạy ổn định, cần xác định rõ file nằm ở đâu, đường dẫn tương đối được tính từ đâu và văn bản được giải mã bằng charset nào. Bài học này tập trung vào built-in `script` của Spring Shell, Java NIO `Path`/`Files` và cách tổ chức tệp để chạy được trong IDE, terminal, CI và môi trường đóng gói.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Đường dẫn tệp | Cách định vị một file hoặc thư mục trong file system | `scripts/setup.shell` |
| Working directory | Thư mục hiện hành của tiến trình Java | `/opt/task-cli` |
| Charset/encoding | Quy tắc chuyển byte trong file thành ký tự và ngược lại | UTF-8 |

Một đường dẫn tương đối không tự mô tả thư mục gốc. Nó cần được kết hợp với working directory hoặc một thư mục gốc do ứng dụng quy định. Tương tự, một file chứa tiếng Việt chỉ được đọc đúng nếu chương trình dùng charset phù hợp với charset đã dùng khi lưu file.

Đừng nhầm **đường dẫn script** với **đường dẫn dữ liệu mà command bên trong script sử dụng**. Ví dụ `script` mở `scripts/deploy.shell`, nhưng một dòng trong file gọi `import-config config/app.yml`. Đường dẫn `config/app.yml` được command xử lý theo quy tắc của command đó; Java thường giải quyết đường dẫn tương đối theo working directory của tiến trình, không tự động theo thư mục chứa `deploy.shell`.

## 2. Working directory là gì?

Working directory (thư mục làm việc hiện tại) là thư mục mà tiến trình Java xem như điểm bắt đầu khi giải quyết đường dẫn tương đối. Với file system mặc định của Java, thư mục này được thể hiện bởi system property `user.dir` và thường là thư mục mà JVM được khởi chạy.

Có thể in ra để chẩn đoán:

```java
System.out.println("user.dir = " + System.getProperty("user.dir"));
System.out.println("working directory = "
        + Path.of("").toAbsolutePath().normalize());
```

Working directory có thể khác nhau tùy cách khởi chạy:

- IDE dùng giá trị trong cấu hình Run/Debug.
- Terminal thường dùng thư mục hiện hành tại thời điểm gọi `java -jar`.
- CI runner dùng thư mục checkout hoặc thư mục làm việc do job chỉ định.
- Container dùng `WORKDIR` trong image hoặc thư mục được truyền lúc chạy container.
- Service manager có thể thiết lập working directory riêng cho tiến trình.

Vì vậy, không giả định working directory luôn là thư mục chứa file JAR, thư mục dự án hoặc thư mục chứa script. Hãy cấu hình rõ và ghi nhận giá trị thực tế khi cần chẩn đoán.

## 3. Đường dẫn tuyệt đối và tương đối

Đường dẫn tuyệt đối xác định vị trí từ gốc của file system hoặc volume, ví dụ:

```text
/opt/task-cli/scripts/deploy.shell
C:/work/task-cli/scripts/deploy.shell
```

Đường dẫn tương đối được giải quyết dựa trên working directory:

```text
scripts/deploy.shell
../shared/config.yml
data/output/report.csv
```

Nếu tiến trình có `user.dir=/opt/task-cli`, đường dẫn `scripts/deploy.shell` được giải quyết thành `/opt/task-cli/scripts/deploy.shell`. Nếu IDE chạy với `user.dir=/tmp/run-config`, cùng chuỗi đó lại trỏ đến `/tmp/run-config/scripts/deploy.shell`.

Đường dẫn tuyệt đối phù hợp với lệnh vận hành cần chỉ rõ một file cụ thể. Đường dẫn tương đối phù hợp với cấu trúc thư mục dự án khi ứng dụng kiểm soát working directory. Với script dùng trong nhiều môi trường, nên truyền đường dẫn gốc qua cấu hình thay vì dựa vào một thư mục ngầm định.

## 4. Dùng `Path` thay vì ghép chuỗi đường dẫn

Java NIO cung cấp `Path` và `Paths` để biểu diễn đường dẫn độc lập hơn với hệ điều hành. Dùng `resolve` để nối các thành phần đường dẫn, `normalize` để rút gọn `.` và `..`, `toAbsolutePath` để tạo đường dẫn tuyệt đối theo working directory hiện tại.

```java
import java.nio.file.Path;

Path workingDirectory = Path.of(System.getProperty("user.dir"));
Path scriptPath = workingDirectory
        .resolve("scripts")
        .resolve("deploy.shell")
        .normalize();

Path absoluteScriptPath = scriptPath.toAbsolutePath().normalize();
System.out.println(absoluteScriptPath);
```

Tránh ghép chuỗi bằng dấu `/` hoặc `\\`:

```java
// Không nên ghép chuỗi theo hệ điều hành
String path = root + "/scripts/" + fileName;

// Nên dùng Path
Path path = rootPath.resolve("scripts").resolve(fileName);
```

`Path.normalize()` chỉ chuẩn hóa cấu trúc đường dẫn về mặt từ vựng; nó không kiểm tra file có tồn tại và không giải quyết symbolic link. `toRealPath()` trả về đường dẫn thực đã phân giải, yêu cầu mục tiêu tồn tại và có thể truy cập.

## 5. Built-in `script` và khác biệt giữa phiên bản

Lệnh `script` đọc một file chứa các command rồi thực thi lần lượt. Cách truyền file và khả năng dùng Spring resource đã thay đổi theo phiên bản:

| Phiên bản | Cách chỉ định file theo tài liệu |
| --- | --- |
| Spring Shell 3.4.3 | Nhận một local file argument; kiểm tra `help script` của bản đang dùng để xác nhận cú pháp option |
| Spring Shell 4.0.3 | Dùng option `--file` với đường dẫn file tuyệt đối |
| Spring Shell 4.0.4 | Nhận đường dẫn file tuyệt đối hoặc Spring resource reference như `classpath:` và `file:` |

Ví dụ Spring Shell 4.0.3:

```text
script --file /opt/task-cli/scripts/deploy.shell
```

Trên Windows, có thể dùng đường dẫn tuyệt đối và đặt trong dấu nháy khi có khoảng trắng:

```text
script --file "C:/work/task cli/scripts/deploy.shell"
```

Spring Shell 4.0.4 còn cho phép tham chiếu resource:

```text
script --file classpath:scripts/bootstrap.shell
script --file file:/opt/task-cli/scripts/deploy.shell
```

`classpath:` phù hợp với script mẫu được đóng gói cùng ứng dụng và chỉ đọc. `file:` phù hợp với file nằm ngoài JAR mà người vận hành có thể cập nhật. Khả năng này được ghi trong tài liệu 4.0.4; không mặc định áp dụng cú pháp resource reference cho Spring Shell 4.0.3 hoặc 3.4.3. <Link url="https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/script.html" title="Script — Spring Shell 3.4.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/commands/builtin/script.html" title="Script — Spring Shell 4.0.4"/>.

## 6. Cú pháp và nội dung của script file

Tài liệu Spring Shell mô tả file script là danh sách command được thực thi theo thứ tự. Các dòng bắt đầu bằng `//` là comment. Spring Shell 3.4.3 còn mô tả dấu gạch chéo ngược ở cuối dòng để nối dòng lệnh tiếp theo. Tài liệu Spring Shell 4.0.3/4.0.4 mô tả một command trên mỗi dòng và comment `//`; không nên mặc định tính năng line continuation của 3.4 hoạt động giống hệt trong mọi bản 4.x.

Ví dụ file `deploy.shell`:

```text
// Chọn cấu hình triển khai
config use staging
environment show

// Kiểm tra trước khi triển khai
artifact verify --file build/app.jar
deploy --environment staging --version 2.5.0
deployment status
```

Các dòng command được chạy theo thứ tự. Nếu command sau phụ thuộc kết quả command trước, hãy sắp xếp rõ ràng và xác định cách xử lý khi một command lỗi. Đừng đưa mật khẩu hoặc token trực tiếp vào script vì file có thể được lưu trong repository, backup hoặc log.

Nếu script cần một file cấu hình khác, hãy truyền đường dẫn theo hợp đồng của command đó. Để tránh phụ thuộc working directory, có thể dùng đường dẫn tuyệt đối hoặc cấu hình một thư mục dữ liệu gốc mà mọi command cùng tuân theo.

## 7. Đường dẫn của script và đường dẫn trong script

Giả sử cấu trúc triển khai:

```text
/opt/task-cli/
  app.jar
  scripts/
    deploy.shell
  config/
    staging.yml
  data/
    exports/
```

Nếu tiến trình được chạy với working directory `/opt/task-cli`, script có thể gọi command với đường dẫn tương đối `config/staging.yml`. Nhưng nếu người vận hành chạy JAR từ `/tmp`, command sẽ tìm `/tmp/config/staging.yml` trừ khi ứng dụng tự áp dụng một base directory khác.

Đường dẫn của chính file script cũng không tự động trở thành working directory cho các command trong file. Nếu muốn đường dẫn tương đối trong script được tính theo thư mục chứa script, ứng dụng cần chủ động thiết kế quy ước đó: ví dụ custom script runner truyền script base directory vào context hoặc yêu cầu command nhận tham số gốc rõ ràng.

Một quy ước dễ vận hành là cấu hình `app.data-directory` hoặc `app.workspace`, chuẩn hóa thành một `Path` tuyệt đối lúc khởi động, rồi mọi command dùng service chung để resolve file dưới thư mục đó.

## 8. Kiểm tra file và thư mục trước khi đọc hoặc ghi

Lớp `Files` cung cấp các thao tác kiểm tra và tạo thư mục:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path script = Path.of("scripts", "deploy.shell")
        .toAbsolutePath()
        .normalize();

if (!Files.exists(script)) {
    throw new IllegalArgumentException("Không tìm thấy script: " + script);
}
if (!Files.isRegularFile(script)) {
    throw new IllegalArgumentException("Đường dẫn không phải file thường: " + script);
}
if (!Files.isReadable(script)) {
    throw new IllegalArgumentException("Không có quyền đọc script: " + script);
}

Path outputDirectory = Path.of("data", "exports");
Files.createDirectories(outputDirectory);
```

`Files.createDirectories` tạo cả các thư mục cha còn thiếu và không báo lỗi chỉ vì thư mục đã tồn tại. Khi ghi file, kiểm tra thư mục cha và quyền ghi; khi đọc, kiểm tra file tồn tại, là file thường và đọc được. Các kiểm tra này giúp thông báo sớm, nhưng thao tác đọc/ghi vẫn phải bắt và xử lý `IOException` vì file hoặc quyền có thể thay đổi sau lúc kiểm tra.

## 9. Giới hạn đường dẫn trong một workspace

Nếu command chỉ được phép đọc script trong một thư mục, không kiểm tra bằng `String.startsWith`. Cách so sánh chuỗi có thể nhầm `/workspace/scripts-old` là con của `/workspace/scripts`. Hãy dùng `Path` theo từng thành phần và phân giải symbolic link khi file đã tồn tại.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path allowedRoot = Path.of("/opt/task-cli/scripts").toRealPath();
Path requested = allowedRoot.resolve(userSuppliedName).normalize();

if (!requested.startsWith(allowedRoot)) {
    throw new IllegalArgumentException("Script nằm ngoài thư mục cho phép.");
}

Path realScript = requested.toRealPath();
if (!realScript.startsWith(allowedRoot)) {
    throw new IllegalArgumentException("Script trỏ ra ngoài thư mục cho phép.");
}
if (!Files.isRegularFile(realScript) || !Files.isReadable(realScript)) {
    throw new IllegalArgumentException("Script không phải file có thể đọc.");
}
```

`normalize()` ngăn đường dẫn kiểu `../secret.txt` thoát khỏi root về mặt từ vựng; `toRealPath()` giúp phát hiện symbolic link trỏ ra ngoài root. Nếu ứng dụng ghi file mới, file đích có thể chưa tồn tại nên cần xác minh thư mục cha thực tế rồi mới resolve tên file. Với môi trường nhiều tiến trình có thể thay đổi symlink đồng thời, cần thiết kế quyền file và thao tác mở file an toàn để tránh race condition.

## 10. Encoding của tệp văn bản

File lưu byte; Java xử lý văn bản dưới dạng ký tự. Charset quy định cách giải mã byte thành ký tự khi đọc và mã hóa ký tự thành byte khi ghi. Nếu file được lưu bằng UTF-8 nhưng chương trình đọc bằng charset khác, chữ tiếng Việt có dấu có thể bị sai.

Với script, YAML, JSON, CSV và file cấu hình văn bản, nên thống nhất UTF-8. Không dựa vào charset mặc định của máy hoặc constructor cũ có thể dùng platform default như `FileReader`/`FileWriter` không chỉ định charset.

Trong Java NIO:

- `Files.newBufferedReader(path)` đọc UTF-8.
- `Files.readString(path)` đọc UTF-8 từ Java 11 trở lên.
- Có thể chỉ định charset tường minh bằng overload nhận `Charset`.
- Khi ghi, dùng `Files.newBufferedWriter(path, StandardCharsets.UTF_8, ...)` hoặc `Files.writeString(..., StandardCharsets.UTF_8, ...)`.

Tài liệu Java xác nhận các overload không nhận charset của `Files.newBufferedReader` và `Files.readString` sử dụng UTF-8. <Link url="https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html" title="Java 17 — Files API"/>.

Tài liệu built-in `script` của Spring Shell mô tả cách chỉ định file, command theo dòng và comment, nhưng không công bố một cam kết charset thống nhất cho mọi nhánh phiên bản. Vì vậy, không suy luận rằng built-in `script` luôn đọc UTF-8 chỉ từ việc Java NIO có API mặc định UTF-8. Nếu script chứa tiếng Việt hoặc ký tự ngoài ASCII, hãy kiểm tra với đúng release Spring Shell đang dùng; nếu ứng dụng tự đọc script, chỉ định `StandardCharsets.UTF_8` như các ví dụ dưới đây.

## 11. Đọc và ghi UTF-8 bằng `Files`

Với file nhỏ, có thể đọc toàn bộ nội dung:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path configFile = Path.of("config", "staging.yml");
String content = Files.readString(configFile, StandardCharsets.UTF_8);
```

Với file lớn hoặc cần xử lý từng dòng, dùng `BufferedReader`:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path configFile = Path.of("config", "staging.yml");
try (BufferedReader reader = Files.newBufferedReader(
        configFile, StandardCharsets.UTF_8)) {
    String line;
    int lineNumber = 0;
    while ((line = reader.readLine()) != null) {
        lineNumber++;
        processLine(lineNumber, line);
    }
}
```

`processLine` là phương thức xử lý từng dòng do ứng dụng định nghĩa; thay nó bằng logic đọc cấu hình hoặc xử lý bản ghi của command.

Khi ghi, chỉ định rõ charset và chính sách mở file:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path report = Path.of("data", "exports", "deployment-report.txt");
Files.createDirectories(report.getParent());

try (BufferedWriter writer = Files.newBufferedWriter(
        report,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE)) {
    writer.write("Kết quả triển khai thành công");
    writer.newLine();
}
```

`TRUNCATE_EXISTING` xóa nội dung cũ trước khi ghi. Nếu muốn thêm vào cuối file, dùng `APPEND` và xác định rõ khi file chưa tồn tại có cần `CREATE` hay không. Không dùng chế độ ghi đè cho file quan trọng nếu chưa có chính sách backup hoặc ghi nguyên tử phù hợp.

## 12. BOM, line ending và ký tự tiếng Việt

UTF-8 không yêu cầu byte order mark (BOM). Một số editor có thể lưu file UTF-8 kèm BOM; khi giải mã bằng UTF-8 thông thường, ký tự BOM có thể xuất hiện ở đầu chuỗi dưới dạng `\uFEFF`. Nếu parser không xử lý ký tự này, command đầu tiên trong script có thể bị nhận diện sai.

Khuyến nghị:

- Lưu script UTF-8 không BOM nếu parser không công bố hỗ trợ BOM.
- Nếu nhận file từ nguồn bên ngoài, kiểm tra ký tự đầu tiên và xử lý BOM một cách tường minh.
- Dùng font terminal hỗ trợ tiếng Việt; encoding của file đúng không tự bảo đảm terminal hiển thị đúng.
- Giữ line ending LF hoặc CRLF nhất quán trong cùng repository.
- Kiểm tra file có dòng cuối kết thúc bằng newline nếu công cụ xử lý theo dòng.

`BufferedReader.readLine()` đọc được dòng kết thúc bằng LF, CRLF hoặc CR và bỏ ký tự kết thúc dòng khỏi chuỗi trả về. Nếu ứng dụng cần giữ nguyên line ending để ghi lại nội dung, không dùng `readLine()` như một phép round-trip vì nó không giữ lại dấu phân cách dòng.

## 13. Resource `classpath:` khác với đường dẫn file

Một resource nằm trong `src/main/resources` thường được đóng gói bên trong JAR. Khi chạy từ IDE, resource có thể trông giống một file trong thư mục build; khi chạy JAR, resource có thể nằm bên trong archive và không có đường dẫn file hệ thống tương ứng.

Vì vậy, không nên chuyển mọi `classpath:` resource thành `File` hoặc `Path`. Dùng Spring `Resource` để đọc resource:

```java
import java.io.IOException;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;

@Component
public class ScriptTemplateLoader {

    private final ResourceLoader resourceLoader;

    public ScriptTemplateLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public String loadTemplate() throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:scripts/bootstrap.shell");
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(resource.getInputStream(), StandardCharsets.UTF_8))) {
            return reader.lines().collect(Collectors.joining(System.lineSeparator()));
        }
    }
}
```

Resource có thể đại diện classpath, file hoặc nguồn khác; `getInputStream()` là cách đọc tổng quát. Với file người dùng có thể sửa, dùng filesystem path bên ngoài JAR. Với script mẫu chỉ đọc, `classpath:` giúp đóng gói cùng ứng dụng. Built-in `script` chỉ hỗ trợ các dạng resource được tài liệu của phiên bản công bố; Spring Shell 4.0.4 có mô tả `classpath:` và `file:` trong option `--file`.

## 14. Kiểm thử script trong nhiều working directory

Một bài test chạy từ thư mục dự án có thể che giấu lỗi đường dẫn. Hãy thử cùng một JAR và cùng một script từ nhiều working directory khác nhau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Chạy từ thư mục gốc dự án | Đường dẫn tương đối theo quy ước hoạt động |
| Chạy từ thư mục khác | Không vô tình phụ thuộc vào vị trí dự án |
| Chạy trong IDE | Working directory khớp cấu hình Run/Debug |
| Chạy executable JAR | File ngoài JAR được tìm đúng vị trí |
| Chạy trong container | `WORKDIR` và volume mount khớp cấu hình |
| Đường dẫn có dấu cách hoặc Unicode | Parser và file system nhận đúng path |
| File UTF-8 tiếng Việt | Nội dung đọc đúng dấu và không có ký tự thay thế |
| File có BOM | Parser không nhận nhầm BOM thành ký tự đầu command |
| File CRLF/LF | Script được đọc theo dòng đúng |

Khi kiểm thử built-in `script`, dùng đúng cú pháp của phiên bản Spring Shell đang chạy. Kiểm tra command đầu tiên, một command có đường dẫn tương đối, một comment `//` và một command có giá trị tiếng Việt. Với Spring Shell 3.4.3, kiểm tra thêm line continuation nếu script sử dụng dấu `\\` cuối dòng.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| IDE chạy được nhưng JAR không tìm thấy file | Working directory khác nhau | In `user.dir`, cấu hình working directory hoặc dùng base directory rõ ràng |
| Script file không được mở | Dùng relative path trong khi phiên bản yêu cầu absolute path | Kiểm tra tài liệu đúng phiên bản và truyền đường dẫn tuyệt đối |
| `classpath:` bị báo không phải file | Đang coi Spring Resource như filesystem path | Dùng Resource API hoặc built-in `script` hỗ trợ resource trong phiên bản tương ứng |
| Command trong script không tìm thấy config | Đường dẫn tương đối được tính theo process working directory | Dùng absolute path hoặc cấu hình workspace root |
| Tên file có dấu cách bị tách | Không quote giá trị option | Đặt toàn bộ đường dẫn trong dấu nháy phù hợp parser |
| Tiếng Việt thành ký tự lỗi | Charset đọc và charset lưu khác nhau | Chuẩn hóa UTF-8 và chỉ định `StandardCharsets.UTF_8` |
| Command đầu tiên không nhận diện | File có UTF-8 BOM chưa được xử lý | Lưu UTF-8 không BOM hoặc loại BOM tường minh |
| Script chạy khác giữa Windows và Linux | Dùng dấu phân cách, quyền file hoặc line ending giả định | Dùng `Path`, kiểm tra quyền và test trên môi trường mục tiêu |
| File output không ghi được | Thư mục cha chưa tồn tại hoặc thiếu quyền | `Files.createDirectories` và kiểm tra quyền ghi |
| Đường dẫn vượt khỏi workspace | Chỉ kiểm tra chuỗi hoặc bỏ qua `..`/symlink | Dùng `Path.normalize`, `startsWith` và `toRealPath` |

## 16. Bài thực hành tổng hợp

Tạo một CLI chạy script triển khai và đọc file cấu hình UTF-8:

1. Tạo thư mục `scripts`, `config` và `data/exports` trong workspace.
2. Tạo file `scripts/deploy.shell` gồm comment, command kiểm tra cấu hình, command triển khai và command xem trạng thái.
3. Chạy script bằng built-in `script` theo đúng cú pháp của phiên bản Spring Shell trong dự án.
4. In `user.dir` và thử chạy JAR từ thư mục gốc dự án rồi từ một thư mục khác.
5. Dùng `Path.resolve` để tạo đường dẫn đến file cấu hình và thư mục báo cáo.
6. Đọc cấu hình bằng `Files.newBufferedReader(..., UTF_8)` và ghi báo cáo bằng `Files.newBufferedWriter(..., UTF_8, ...)`.
7. Đưa vào file cấu hình một số nội dung tiếng Việt có dấu; xác nhận nội dung không bị lỗi encoding.
8. Thử file UTF-8 có BOM, CRLF và LF; ghi lại hành vi parser của phiên bản đang dùng.
9. Thêm kiểm tra để mọi script phải nằm trong workspace cho phép, bao gồm kiểm tra symbolic link nếu cần.
10. Viết README ghi rõ working directory, cấu trúc thư mục, cú pháp `script`, charset và ví dụ chạy trên Windows/macOS/Linux.

## 17. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Working directory | Xác định và chẩn đoán được `user.dir` ở IDE, terminal và container |
| Path | Dùng `Path.resolve`, `normalize`, `toAbsolutePath` thay cho ghép chuỗi |
| Spring Shell script | Biết cú pháp và khả năng path/resource theo phiên bản |
| File system | Kiểm tra file, thư mục, quyền đọc/ghi và tạo thư mục |
| Encoding | Đọc và ghi UTF-8 tường minh |
| Script format | Hiểu comment, line ending và khác biệt line continuation theo phiên bản |
| Resource | Phân biệt `classpath:` resource với file system path |
| An toàn đường dẫn | Giới hạn đường dẫn trong workspace bằng Path và real path |
| Kiểm thử | Chạy được từ nhiều working directory và xác minh tiếng Việt |

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Script](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/script.html)
- [Spring Shell 4.0.3 — Script](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell 4.0.4 — Script và Spring Resource](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Java 17 — `Path` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Java 17 — `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Spring Framework — Resource abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html)
