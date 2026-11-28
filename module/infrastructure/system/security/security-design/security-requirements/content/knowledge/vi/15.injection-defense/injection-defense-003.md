# Command injection — Đặc tả phòng vệ khi ứng dụng gọi chương trình bên ngoài

## 1. Mục tiêu bảo mật: người dùng chọn nghiệp vụ, không chọn lệnh

Một dịch vụ xuất báo cáo nhận định dạng và tên tài liệu từ request. Đội phát triển ghép các giá trị này vào một chuỗi để gọi công cụ chuyển đổi. Khi đầu vào có thể thay đổi cấu trúc lệnh hoặc tùy chọn của công cụ, caller có thể khiến hệ thống thực hiện việc khác với nghiệp vụ được cấp quyền.

**Command injection** xảy ra khi dữ liệu chịu ảnh hưởng từ bên ngoài bị diễn giải thành một phần điều khiển của lệnh. Rủi ro nằm ở ranh giới giữa dữ liệu và chỉ thị, không chỉ ở sự xuất hiện của một ký tự “đáng ngờ”. CWE mô tả nhóm vấn đề này trong [CWE-78 — OS Command Injection](https://cwe.mitre.org/data/definitions/78.html).

Trong module yêu cầu bảo mật, mục tiêu cần được chuyển thành các điều kiện có thể nghiệm thu:

- Caller chỉ chọn được thao tác nghiệp vụ và tài nguyên mà mình có quyền sử dụng.
- Executable, cấu trúc đối số và môi trường thực thi do hệ thống quyết định.
- Dữ liệu đầu vào không trở thành shell script, tùy chọn tùy ý hoặc cấu hình có quyền thực thi.
- Tiến trình chỉ có quyền và tài nguyên cần thiết cho một job.
- Kết quả kiểm thử chứng minh hành vi thực tế ở ranh giới khởi chạy, không chỉ chứng minh response không báo lỗi.

Bài học tập trung vào cách đặc tả và kiểm chứng những điều kiện này. Các tên công cụ, đường dẫn và ngưỡng trong ví dụ là giả định của một hệ thống minh họa.

## 2. Phân biệt shell injection và argument injection

### 2.1. Shell injection: dữ liệu được đưa vào chương trình lệnh

Anti-pattern dễ nhận thấy là tạo chuỗi rồi giao cho một shell:

```java
// Anti-pattern: userValue trở thành một phần mã lệnh của shell.
String script = "report-tool --input " + userValue;

new ProcessBuilder("/bin/sh", "-c", script).start();
```

Trong trường hợp này, shell phân tích chuỗi `script`. Các cấu trúc như dấu phân cách lệnh, pipe, chuyển hướng hoặc phép thay thế có thể có ý nghĩa điều khiển thay vì dữ liệu, tùy shell và ngữ cảnh.

Không nên diễn đạt phòng vệ bằng câu “xóa dấu chấm phẩy”. Một blacklist nhỏ không mô tả được toàn bộ cú pháp và không xử lý sự khác biệt giữa shell, hệ điều hành hay các lớp quoting.

Đối với một chức năng nghiệp vụ thông thường, thiết kế ưu tiên không tạo shell script từ dữ liệu request. Nếu công cụ có API trực tiếp, hãy đánh giá việc sử dụng API đó trước khi giữ một ranh giới thực thi lệnh.

### 2.2. Argument injection: không có shell vẫn có thể sai

Giả sử ứng dụng gọi trực tiếp một binary bằng danh sách đối số. Dữ liệu không được shell phân tích, nhưng chương trình đích vẫn có cú pháp riêng.

Nếu caller đưa một giá trị như `--help` vào vị trí mà công cụ có thể diễn giải là tùy chọn, hành vi có thể thay đổi. Một tùy chọn khác có thể chọn file cấu hình, nơi ghi, plugin, giao thức hoặc chế độ xử lý ngoài phạm vi nghiệp vụ.

Vì vậy, “mỗi giá trị là một đối số” chỉ bảo vệ ranh giới phân tách đối số. Nó không tự xác nhận rằng ý nghĩa của đối số được phép. CWE phân loại vấn đề về ranh giới đối số tại [CWE-88 — Argument Injection](https://cwe.mitre.org/data/definitions/88.html).

| Câu hỏi kiểm tra | Shell injection | Argument hoặc option injection |
|---|---|---|
| Ai diễn giải cấu trúc? | Shell hoặc bộ thông dịch | Parser của chương trình đích |
| Dữ liệu có thể làm gì? | Thay đổi mã lệnh được thực thi | Thay đổi tùy chọn, toán hạng hoặc chế độ công cụ |
| Bỏ shell đã đủ chưa? | Loại một ranh giới rủi ro quan trọng | Chưa; vẫn cần hợp đồng đối số |
| Kiểm soát chính | Không tạo mã shell từ input | Cấu trúc cố định và validation theo công cụ |
| Bằng chứng | Không có shell nằm trong đường khởi chạy ngoài thiết kế | Đúng số đối số, vị trí và ý nghĩa được phép |

Một command injection cũng có thể bắt đầu từ dữ liệu lưu trong database, tên file hoặc message nội bộ. Việc dữ liệu không đến trực tiếp từ request hiện tại không khiến nó trở thành cấu trúc lệnh đáng tin.

## 3. Giảm nhu cầu gọi tiến trình trước khi thêm bộ lọc

Câu hỏi thiết kế đầu tiên nên là: hệ thống có cần gọi công cụ hệ điều hành không?

Ví dụ, đọc metadata, tạo thư mục hoặc tính digest thường có thể được thực hiện bằng API phù hợp trong ngôn ngữ. Loại bỏ một tiến trình ngoài giúp giảm các vấn đề về command line, môi trường kế thừa và quản lý vòng đời.

Điều đó không có nghĩa mọi thư viện nội bộ đều an toàn vô điều kiện. Dữ liệu vẫn phải được kiểm tra, đường dẫn vẫn phải được phân quyền và bộ xử lý nội dung vẫn có thể cần cách ly. Lợi ích là bỏ đi một ranh giới diễn giải lệnh không cần thiết.

Nếu cần một binary chuyên dụng, quyết định giữ nó nên ghi nhận:

1. Năng lực nghiệp vụ mà công cụ cung cấp.
2. Lý do chưa dùng API hoặc thư viện phù hợp.
3. Executable và phiên bản được triển khai.
4. Các tùy chọn bắt buộc và tùy chọn bị vô hiệu hóa.
5. Dữ liệu nào được công cụ đọc, ghi hoặc truy cập mạng.
6. Chủ sở hữu của bản cập nhật công cụ và hợp đồng command line.

OWASP ưu tiên tránh gọi OS command khi có API phù hợp; nếu cần gọi, phải giữ ranh giới dữ liệu và kiểm tra các giá trị theo công cụ. Tham khảo [OWASP OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html).

## 4. Mô hình luồng dữ liệu cần được đặc tả

Một thiết kế xuất báo cáo minh họa:

```text
Request: reportId + format
          |
          v
Xác thực và phân quyền trên reportId
          |
          v
Ánh xạ format vào enum nghiệp vụ
          |
          v
Tạo job nội bộ và đường dẫn do server quản lý
          |
          v
Factory dựng executable + argv cố định
          |
          v
Launcher có môi trường và ngân sách đã định nghĩa
          |
          v
Worker hoặc sandbox của job
          |
          v
Kiểm tra kết quả rồi mới công bố thành công
```

Caller không gửi `command`, `shell`, `extraArgs`, đường dẫn binary hoặc câu lệnh tùy ý. Nếu API nhận một chuỗi `extraArgs` rồi chỉ kiểm tra độ dài, nó đang để caller can thiệp vào cấu trúc thực thi.

Dữ liệu có quyền kiểm soát khác nhau cần được tách rõ:

| Thành phần | Nguồn được phép | Ràng buộc minh họa |
|---|---|---|
| Executable | Artifact triển khai tin cậy | Đường dẫn tuyệt đối, không sửa được bởi worker không tin cậy |
| Tên tùy chọn | Mã ứng dụng | Tập cố định, không lấy từ request |
| Định dạng xuất | Enum từ hợp đồng nghiệp vụ | Chỉ các giá trị đã ánh xạ |
| Đường dẫn input | Tra cứu tài nguyên đã kiểm tra quyền | Thuộc vùng dữ liệu của job |
| Đường dẫn output | Server cấp phát | Không chọn theo tên client |
| Working directory | Thư mục job do server tạo | Quyền riêng, không chứa cấu hình ngoài ý muốn |
| Environment | Chính sách launcher | Tập biến cần thiết, không sao chép tùy ý từ request |
| Nội dung input | Dữ liệu chưa tin cậy | Công cụ xử lý như dữ liệu theo cấu hình được hỗ trợ |

Phân quyền phải diễn ra trước khi tạo tác động xử lý. UUID hợp lệ về cú pháp không chứng minh caller có quyền đọc một báo cáo hoặc ghi vào một job.

## 5. Hợp đồng đối số phải dựa trên ngữ nghĩa công cụ

### 5.1. Không chỉ kiểm tra metacharacter

Một đối số chỉ chứa chữ và số vẫn có thể chọn một tài nguyên không được phép. Một đối số bắt đầu bằng dấu gạch ngang có thể là một option hợp lệ nhưng không được nghiệp vụ cho phép.

Do đó, validation phải trả lời “giá trị này có nghĩa gì ở vị trí này?”:

- Nếu là định dạng, ánh xạ từ enum.
- Nếu là ID, phân tích cú pháp rồi kiểm tra quyền trên bản ghi.
- Nếu là đường dẫn, lấy từ lớp lưu trữ và kiểm soát containment.
- Nếu là URL, xác định đích được phép theo yêu cầu mạng riêng.
- Nếu là số lượng, kiểm tra kiểu và khoảng nghiệp vụ.
- Nếu là mẫu tìm kiếm hoặc biểu thức, xem công cụ có diễn giải nó như ngôn ngữ hay không.

Một giá trị là một phần tử của argv vẫn có thể chứa một chương trình con, một biểu thức hoặc một cấu hình nếu công cụ hỗ trợ cú pháp đó.

### 5.2. End-of-options chỉ có ý nghĩa theo tài liệu công cụ

Một số chương trình hỗ trợ `--` để kết thúc việc phân tích tùy chọn. Chỉ sử dụng cơ chế này khi đúng với công cụ, phiên bản và vị trí đối số.

`--` không phải thuốc giải phổ quát. Các toán hạng phía sau vẫn có thể chọn một đích mạng không được phép hoặc một file ngoài quyền. Một số công cụ còn có cơ chế mở rộng riêng cho wildcard, response file hay nguồn cấu hình.

Vì thế hợp đồng phải cố định số lượng toán hạng, loại toán hạng và các tính năng mở rộng được phép. Không chèn `--` rồi bỏ qua phân quyền và kiểm tra nội dung.

### 5.3. Không tự thêm quoting kiểu shell vào API đối số

Khi dùng API nhận từng đối số, không tự bọc mọi giá trị bằng dấu nháy theo một công thức shell. Dấu nháy đó có thể trở thành dữ liệu thực mà chương trình nhận, hoặc không có tác dụng như dự kiến trên nền tảng khác.

Cần dùng API và hợp đồng của nền tảng đích. Hành vi giữa POSIX, Windows, native executable và script wrapper có thể khác nhau; phải kiểm thử ở môi trường triển khai thực tế.

Đặc biệt, gọi một script hoặc wrapper không chứng minh đường đi không có shell. Phải xem thành phần đó có tiếp tục ghép input vào một chuỗi lệnh hay không.

## 6. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã sau là ví dụ để liên kết rủi ro, thành phần và bằng chứng trong một dự án.

### CMD-01 — Không cung cấp chức năng thực thi lệnh tùy ý

API nghiệp vụ không được nhận executable, shell script hoặc danh sách tùy chọn tùy ý từ caller. Thao tác phải được chọn từ tập nghiệp vụ cố định.

**Bằng chứng:** schema request; thử gửi field không được hỗ trợ; kiểm tra không có nhánh fallback nhận raw command.

Một hệ thống quản trị có chức năng thực thi mã thật sự cần mô hình quyền và cách ly riêng. Không coi nó là ngoại lệ ngầm cho endpoint xuất báo cáo.

### CMD-02 — Executable và cấu trúc argv do hệ thống quyết định

Mỗi điểm gọi tiến trình phải có executable tin cậy và cấu trúc đối số đã định nghĩa. Dữ liệu chưa tin cậy không được chọn binary hoặc sinh tên option.

**Bằng chứng:** danh mục điểm gọi; factory cấu trúc; giá trị executable và argv quan sát tại launcher.

### CMD-03 — Không đưa input vào mã của bộ thông dịch

Không ghép dữ liệu request hoặc dữ liệu lưu chưa tin cậy vào chuỗi được truyền cho `sh -c`, `cmd /c`, PowerShell command string hoặc một bộ thông dịch tương đương.

**Bằng chứng:** kiểm tra đường khởi chạy thực tế, kể cả wrapper và script downstream; test double xác nhận cấu trúc không chứa chuỗi lệnh tổng hợp.

Nếu cần một script cố định, phải mô tả ranh giới truyền dữ liệu và chứng minh script không nối dữ liệu đó thành mã ở bên trong.

### CMD-04 — Validation theo ý nghĩa của từng đối số

Đối số nghiệp vụ phải được phân tích sang kiểu phù hợp, có giới hạn và kiểm tra quyền hoặc phạm vi tương ứng. Không dùng blacklist ký tự làm bằng chứng duy nhất.

**Bằng chứng:** test option-like input, ID ngoài quyền, đường dẫn ngoài vùng, số vượt biên và dữ liệu được lưu rồi dùng lại.

### CMD-05 — Môi trường và thư mục làm việc được kiểm soát

Launcher phải có chính sách environment, working directory, cấu hình và dependency của công cụ. Input không được sửa các giá trị này hoặc chọn plugin, config hay chương trình phụ ngoài thiết kế.

**Bằng chứng:** manifest triển khai, quyền file cấu hình, tập biến truyền vào và kiểm thử không tự nạp cấu hình từ nơi caller có thể ghi.

### CMD-06 — Worker chạy với quyền tối thiểu

Tiến trình không được có quyền đọc secret, ghi ngoài vùng job hoặc truy cập mạng vượt nhu cầu đã xác định. Quyền tài khoản, filesystem, credential và mạng phải phù hợp với nghiệp vụ.

**Bằng chứng:** cấu hình runtime và phép thử truy cập bị từ chối trong môi trường có kiểm soát.

Cách ly giảm tác động nếu công cụ gặp lỗi; nó không làm việc ghép chuỗi lệnh trở thành an toàn.

### CMD-07 — Vòng đời và tài nguyên được giới hạn

Mỗi job phải có giới hạn thời gian, số job đồng thời, dữ liệu vào, dữ liệu ra và tài nguyên phù hợp. Hành vi timeout, hủy và dọn tiến trình con phải được định nghĩa.

**Bằng chứng:** thử công cụ không kết thúc, output quá lớn, queue đầy và các tiến trình con tồn tại sau khi hủy.

### CMD-08 — Lỗi không bật đường thực thi yếu hơn

Khi binary thiếu, format không hợp lệ hoặc công cụ thất bại, hệ thống không được fallback sang một chuỗi shell ghép từ dữ liệu cũ. Thất bại phải đi qua chính sách lỗi đã định nghĩa.

**Bằng chứng:** fault injection cho lỗi launcher và lỗi công cụ; không có lần khởi chạy bổ sung ngoài contract.

### CMD-09 — Không công bố kết quả chưa xác minh

Exit code và output phải được kiểm tra theo hợp đồng công cụ. Kết quả dở, timeout hoặc thất bại không được đánh dấu thành công và đưa vào luồng tải xuống.

**Bằng chứng:** trạng thái job, output được công bố và tác động nghiệp vụ sau từng loại lỗi.

### CMD-10 — Quan sát không làm lộ dữ liệu thực thi nhạy cảm

Không log nguyên command line, environment hoặc stdout/stderr khi chúng có thể chứa secret hay dữ liệu nghiệp vụ. Sự kiện quan sát phải đủ để liên kết job và lý do thất bại bằng metadata phù hợp.

**Bằng chứng:** log và cảnh báo trong các kịch bản thành công, lỗi và timeout; không có credential hoặc payload thô bị phát tán.

## 7. Ví dụ Java: tạo mô tả thực thi có cấu trúc

Giả sử hệ thống có một native executable Linux giả định là `/opt/acme/bin/report-renderer`. Phiên bản được triển khai có hợp đồng nhận đúng ba option: `--input`, `--output` và `--format`.

Ví dụ này chỉ dựng mô tả thực thi. Nó không khởi chạy tiến trình và chưa thực hiện phần quản lý vòng đời.

**Tiền điều kiện:** `internalJobId` là ID job do server cấp sau khi phân quyền tài nguyên; thư mục job, input và output được lớp lưu trữ tin cậy quản lý. Không lấy ID của caller rồi mặc định quyền đã được kiểm tra.

```java
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

public final class ReportInvocationPolicy {
    private static final String EXECUTABLE =
            "/opt/acme/bin/report-renderer";

    private static final Path JOB_ROOT =
            Path.of("/srv/report-jobs");

    public enum Format {
        PDF("pdf", "result.pdf"),
        TEXT("text", "result.txt");

        private final String toolValue;
        private final String outputName;

        Format(String toolValue, String outputName) {
            this.toolValue = toolValue;
            this.outputName = outputName;
        }

        public static Format fromApi(String value) {
            if (value == null) {
                throw new IllegalArgumentException("FORMAT_REQUIRED");
            }

            return switch (value) {
                case "pdf" -> PDF;
                case "text" -> TEXT;
                default -> throw new IllegalArgumentException(
                        "FORMAT_NOT_ALLOWED");
            };
        }
    }

    public record Invocation(
            List<String> argv,
            Path workingDirectory,
            Map<String, String> environment) {

        public Invocation {
            argv = List.copyOf(argv);
            environment = Map.copyOf(environment);
            Objects.requireNonNull(workingDirectory);
        }
    }

    public static Invocation forAuthorizedJob(
            UUID internalJobId,
            Format format) {

        Objects.requireNonNull(internalJobId);
        Objects.requireNonNull(format);

        Path work = JOB_ROOT.resolve(internalJobId.toString());
        Path input = work.resolve("source.bin");
        Path output = work.resolve(format.outputName);

        List<String> argv = List.of(
                EXECUTABLE,
                "--input", input.toString(),
                "--output", output.toString(),
                "--format", format.toolValue);

        return new Invocation(
                argv,
                work,
                Map.of("LANG", "C", "LC_ALL", "C"));
    }

    public static ProcessBuilder createBuilder(
            Invocation invocation) {

        Objects.requireNonNull(invocation);

        ProcessBuilder builder = new ProcessBuilder(invocation.argv());
        builder.directory(invocation.workingDirectory().toFile());

        builder.environment().clear();
        builder.environment().putAll(invocation.environment());

        // Công cụ giả định ghi kết quả vào --output.
        // Ví dụ không dùng stdout/stderr làm dữ liệu nghiệp vụ.
        builder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
        builder.redirectError(ProcessBuilder.Redirect.DISCARD);

        return builder;
    }
}
```

Điểm cốt lõi không phải là tên lớp `ProcessBuilder`, mà là nguồn và cấu trúc dữ liệu:

- Executable là giá trị cố định thuộc deployment.
- Tên option là hằng số trong mã.
- Format được ánh xạ sang enum, không có `extraArgs`.
- Đường dẫn được dựng từ root nội bộ và UUID job, không từ tên tệp hiển thị.
- Không tạo chuỗi shell và không nhờ caller cung cấp quoting.
- Môi trường ví dụ được xây từ một tập cố định cho công cụ Linux giả định.

Record `Invocation` chỉ là mô tả bất biến của một yêu cầu chạy; public constructor của nó không chứng minh người tạo có quyền thực thi. Trong ứng dụng thật, lớp launcher phải có phạm vi gọi phù hợp và chỉ nhận invocation từ đường nghiệp vụ đã được kiểm soát. Không cung cấp endpoint deserialize trực tiếp record này từ request.

Việc xóa môi trường kế thừa là chính sách của ví dụ, không phải công thức dùng nguyên cho mọi hệ điều hành hoặc công cụ. Công cụ cần biến môi trường nào phải được xác định và kiểm thử; dependency tìm qua PATH, loader, thư viện hoặc config cũng phải nằm trong thiết kế.

Việc bỏ stdout/stderr chỉ thích hợp khi hợp đồng không dùng hai luồng đó. Nếu cần chẩn đoán, thiết kế một cơ chế thu có giới hạn và xử lý dữ liệu nhạy cảm. Không thay bằng ghi toàn bộ output vào log.

Java mô tả command, environment, working directory và I/O trong [ProcessBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html). Tính đúng của ví dụ phải được kiểm tra với binary và hệ điều hành mà ứng dụng thực sự triển khai.

## 8. Những điều ví dụ dựng argv chưa giải quyết

Một cấu trúc argv đúng chưa đủ để nghiệm thu toàn hệ thống.

### 8.1. Tính tin cậy của binary và dependency

Đường dẫn tuyệt đối ngăn việc chọn executable chỉ bằng tên tìm qua PATH, nhưng không bảo vệ được nếu attacker có quyền thay binary tại đường dẫn đó. Cũng phải kiểm soát thư viện, plugin, file cấu hình và các chương trình phụ mà binary sử dụng.

Artifact cần có nguồn triển khai tin cậy, quyền phù hợp và cơ chế cập nhật rõ ràng. Một wrapper đáng tin ở tên gọi có thể vẫn ghép lệnh không an toàn ở bên trong.

### 8.2. Quyền trên dữ liệu và đường dẫn

Một input path được truyền như một đối số riêng vẫn có thể trỏ tới dữ liệu ngoài quyền. Phòng vệ command injection không thay thế kiểm soát path traversal, symlink hoặc phân quyền đọc tệp.

Output path cũng cần được cấp phát để không ghi đè tài nguyên khác. Công cụ phải có ngữ nghĩa ghi phù hợp và thư mục job phải được bảo vệ khỏi thay đổi ngoài thiết kế.

### 8.3. Ngôn ngữ hoặc tính năng bên trong công cụ

Một công cụ có thể nhận template, biểu thức, script nhúng, config mở rộng hoặc nội dung tham chiếu tài nguyên khác. Khi đó ranh giới diễn giải nằm sâu hơn command line.

Cần mô tả tính năng nào bị vô hiệu hóa, nội dung nào được phép và có cần sandbox hay không. “Không qua shell” không chứng minh một trình xử lý template hoặc tài liệu không thể thực thi chức năng ngoài ý muốn.

### 8.4. Tính độc lập giữa quyền và cấu trúc

Một caller có thể yêu cầu thao tác hoàn toàn đúng cú pháp nhưng không được phép. Ví dụ ID báo cáo của tenant khác có thể đi qua parser UUID mà không có lỗi.

Do đó, test cấu trúc argv và test phân quyền phải là hai nhóm bằng chứng riêng. Cả hai đều cần để chứng minh một job thực hiện đúng nghiệp vụ được cấp quyền.

## 9. Vòng đời tiến trình và giới hạn tài nguyên

Launcher cần một hợp đồng rõ ràng thay vì chỉ gọi `start()` rồi chờ vô hạn.

Một chính sách minh họa có thể quy định mỗi job xử lý tối đa một tài liệu, có deadline, trần output, số job đồng thời và quota tài nguyên. Các con số phải được chọn từ nhu cầu và ngân sách hệ thống, không dùng một giá trị thời gian phổ quát.

Những tình huống cần định nghĩa:

1. Công cụ chờ stdin dù nghiệp vụ không dùng input qua luồng này.
2. Stdout hoặc stderr đầy buffer làm tiến trình không tiếp tục.
3. Công cụ tạo tiến trình con tồn tại sau khi parent kết thúc.
4. Job bị hủy trong khi đang ghi output.
5. Ứng dụng restart còn tiến trình hoặc tệp dở.
6. Nhiều request hợp lệ cùng lúc làm cạn tài nguyên worker.

Java cảnh báo việc không phục vụ I/O của tiến trình có thể gây block hoặc deadlock; các API chờ và hủy cũng có các cam kết cần hiểu theo nền tảng. Xem [Java Process API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html).

Một timeout trả về ở luồng HTTP không đồng nghĩa tiến trình đã dừng. Yêu cầu phải xác minh trạng thái thực tế, xử lý output dở và quản lý tiến trình con. Với mô hình đe dọa cần kiểm soát toàn job, có thể cần cơ chế quản lý tiến trình hoặc cách ly ở hệ điều hành thay vì chỉ gửi tín hiệu tới một parent.

Đọc output đến hết rồi mới kiểm tra kích thước không bảo vệ bộ nhớ. Nếu thu output, phải có cách đọc có giới hạn và vẫn xử lý luồng để không tạo bế tắc. Hành vi khi vượt giới hạn phải đi vào cùng chính sách hủy và dọn tài nguyên.

## 10. Kiểm thử tại ranh giới khởi chạy

### 10.1. Dùng test double cho launcher

Một launcher thử nghiệm có thể ghi nhận executable, từng phần tử argv, working directory và tập tên biến môi trường mà không chạy công cụ thật.

Bằng chứng cần trả lời:

- Executable có giữ nguyên không?
- Số lượng và thứ tự đối số có đúng không?
- Mỗi giá trị nghiệp vụ có nằm đúng một vị trí không?
- Có xuất hiện shell hoặc chuỗi command được ghép không?
- Request có thể thêm option hay thay working directory không?
- Biến nhạy cảm có bị kế thừa ngoài chính sách không?

Không dùng `String.join(" ", argv)` làm bằng chứng duy nhất. Chuỗi ghép để hiển thị mất ranh giới đối số và có thể khiến hai invocation khác nhau trông giống nhau.

### 10.2. Dùng chương trình probe vô hại trong môi trường kiểm thử

Một probe do đội dự án quản lý có thể trả lại số lượng đối số và biểu diễn có cấu trúc của chúng trong vùng thử nghiệm. Cách này giúp kiểm tra ranh giới Java, wrapper và hệ điều hành mà không cần chạy hành động phá hoại.

Probe chỉ cần dữ liệu giả. Không đưa token, credential hoặc tài liệu thật vào output kiểm thử để “xem command line”.

### 10.3. Kiểm thử với công cụ thật

Test double chứng minh cấu trúc được dựng, nhưng không chứng minh parser của binary diễn giải đúng. Cần chạy các ca tích hợp trên phiên bản công cụ và hệ điều hành được hỗ trợ.

Nếu một chương trình xem một đối số như đường dẫn config hoặc biểu thức, test cần quan sát hành vi đó. Không kết luận an toàn chỉ vì một dấu chấm phẩy được giữ nguyên trong một phần tử argv.

## 11. Ma trận kiểm thử minh họa

| Nhóm kịch bản | Dữ liệu hoặc điều kiện thử | Kết quả mong đợi |
|---|---|---|
| Nghiệp vụ hợp lệ | ID thuộc quyền, format cho phép | Một job với invocation đúng hợp đồng |
| Format ngoài tập | `custom`, chuỗi chứa khoảng trắng hoặc option | Bị từ chối trước khi khởi chạy |
| Input trông như option | Giá trị `--help` ở field không cho phép | Không thay đổi cấu trúc hoặc chế độ công cụ |
| Metacharacter | Chuỗi giả chứa dấu phân cách, pipe, xuống dòng | Không trở thành mã shell; field sai bị từ chối theo contract |
| Định danh ngoài quyền | UUID đúng cú pháp thuộc tenant khác | Không đọc hoặc xử lý tài nguyên |
| Tên file có cấu trúc lệnh | Metadata tên chứa ký tự đặc biệt | Không đi vào command line như cấu trúc điều khiển |
| Dữ liệu lưu rồi dùng lại | Tên hoặc cấu hình từ bản ghi cũ | Vẫn áp dụng cùng ranh giới tin cậy |
| Wrapper hoặc script | Đường triển khai có thành phần trung gian | Không tái ghép input thành mã lệnh |
| Môi trường không mong muốn | Biến cấu hình, plugin hoặc search path từ parent | Không vượt tập cho phép |
| Lỗi binary hoặc exit code | Thiếu công cụ, lỗi xử lý | Không fallback sang shell, không công bố thành công |
| Timeout và output lớn | Công cụ probe có hành vi đã kiểm soát | Hủy theo chính sách, giới hạn tài nguyên, quản lý output dở |
| Tiến trình con | Job thử sinh child theo kịch bản kiểm soát | Không để tác vụ ngoài vòng đời được phép |
| Đường dẫn input/output | Thử tham chiếu ngoài vùng job | Bị từ chối hoặc bị chặn bởi kiểm soát phù hợp |
| Log lỗi | Thông báo công cụ chứa dữ liệu giả nhạy cảm | Không phát tán nguyên command, environment hoặc output |

Payload kiểm thử nên được chọn để đo hành vi, không cần tạo hậu quả nguy hiểm. Mục tiêu là chứng minh input không mở rộng quyền hoặc thay cấu trúc thực thi, không phải cố gây tác động trên hệ thống thật.

Nếu dùng dữ liệu như `--help`, cần bảo đảm chức năng đó vô hại trong công cụ thử và không dùng response của nó làm bằng chứng duy nhất cho mọi loại argument injection.

## 12. Thiết kế tiêu chí chấp nhận và bằng chứng

Một bộ tiêu chí có thể gồm:

1. Danh mục đầy đủ các điểm gọi tiến trình trong phạm vi, kể cả job nền và wrapper.
2. Mỗi điểm gọi có lý do nghiệp vụ, executable và cấu trúc argv được chốt.
3. Không có field cho caller gửi raw command hoặc extra options tùy ý.
4. Dữ liệu request không được nối vào mã của shell hoặc interpreter.
5. Các tham số nghiệp vụ được phân tích sang kiểu và kiểm tra quyền trước khi tạo job.
6. Binary, dependency, working directory và environment được kiểm soát bằng deployment.
7. Runtime thực thi đúng quyền, giới hạn tài nguyên và chính sách mạng đã định nghĩa.
8. Timeout, lỗi và hủy không kích hoạt fallback yếu hơn hoặc công bố output chưa đạt.
9. Test double và test tích hợp xác nhận cùng cấu trúc và ngữ nghĩa thực thi.
10. Log, cảnh báo và báo cáo kiểm thử không làm lộ dữ liệu nhạy cảm.

Bằng chứng nên gồm cấu trúc invocation đã che dữ liệu nhạy cảm, kết quả từ probe, trạng thái job, cấu hình runtime và tác động thực tế được quan sát.

Không dùng “không thấy lỗi 500” hoặc “response không chứa output của lệnh” làm điều kiện PASS. Một tác động ngoài ý muốn có thể xảy ra mà không được phản ánh trong response. Cần đo đúng ranh giới và tài nguyên mà yêu cầu bảo vệ.

Nếu chưa xác minh được một wrapper hoặc behavior trên Windows, phải ghi rõ giới hạn bằng chứng thay vì suy từ kết quả Linux. Những khác biệt về command line cần được kiểm tra trên nền tảng triển khai tương ứng.

## 13. Những cách đặc tả chưa đủ

| Cách viết | Điểm còn thiếu | Cách làm rõ |
|---|---|---|
| “Chặn ký tự đặc biệt” | Không xác định parser và ngữ nghĩa | Bỏ shell, cấu trúc argv cố định và validation theo tham số |
| “Dùng ProcessBuilder là an toàn” | Caller vẫn có thể chọn option hoặc interpreter | Xác định executable, vị trí đối số và nguồn dữ liệu |
| “Escape mọi chuỗi” | Quoting phụ thuộc ngữ cảnh, vẫn có option injection | Dùng API cấu trúc và contract công cụ |
| “Đã có --” | Toán hạng vẫn có thể ngoài quyền | Giới hạn toán hạng, đích và tính năng công cụ |
| “Input từ database nên tin cậy” | Dữ liệu có thể do người dùng tạo trước đó | Theo dõi nguồn và giữ ranh giới tại sink |
| “Chạy trong container là đủ” | Container có thể có quyền hoặc mạng quá rộng | Giữ phòng vệ cấu trúc và kiểm tra cấu hình cách ly |
| “Dùng đường dẫn tuyệt đối” | Binary, config hoặc dependency có thể bị thay | Bảo vệ artifact và môi trường triển khai |
| “Timeout HTTP là xong” | Tiến trình có thể tiếp tục hoạt động | Kiểm soát vòng đời job và tiến trình con |
| “Không có output nên không bị injection” | Tác động có thể không trả về response | Quan sát invocation và tài nguyên bị tác động |

## 14. Bài tập xây dựng yêu cầu

Một API nhận `documentId`, `format` và `options`. Nó tra tên tệp trong database, ghép vào một chuỗi shell rồi chạy công cụ chuyển đổi. Worker kế thừa toàn bộ environment của ứng dụng và chạy với cùng tài khoản có quyền đọc cấu hình dịch vụ.

Hãy viết một đề xuất đặc tả:

1. Loại bỏ hoặc thay thế field `options` bằng các lựa chọn nghiệp vụ cụ thể.
2. Phân biệt dữ liệu từ database với cấu trúc lệnh đáng tin.
3. Xác định executable, argv, working directory và environment được phép.
4. Nêu bước kiểm tra quyền trên tài liệu trước khi tạo job.
5. Chọn quyền và các vùng đọc/ghi mà worker thực sự cần.
6. Viết tiêu chí cho timeout, lỗi công cụ và output dở.
7. Thiết kế một probe vô hại để kiểm tra ranh giới đối số.
8. Chỉ ra test nào cần binary thật và nền tảng triển khai thật.
9. Định nghĩa log phục vụ điều tra mà không ghi nguyên command hoặc secret.

Đầu ra cần là yêu cầu gắn với bằng chứng, không chỉ là một hàm xóa ký tự. Một thiết kế đạt mục tiêu phải bảo đảm caller chỉ yêu cầu được nghiệp vụ đã cấp quyền qua cấu trúc thực thi mà hệ thống kiểm soát.

## 15. Tài liệu tham khảo

- [CWE-78 — OS Command Injection](https://cwe.mitre.org/data/definitions/78.html): ranh giới dữ liệu và cấu trúc lệnh.
- [CWE-88 — Argument Injection](https://cwe.mitre.org/data/definitions/88.html): ranh giới đối số và tùy chọn.
- [OWASP OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html): tránh OS command khi có thể và kiểm soát dữ liệu truyền vào.
- [Java ProcessBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): thuộc tính tạo tiến trình.
- [Java Process API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): I/O, chờ kết thúc và quản lý tiến trình.

Phòng vệ command injection cần giữ ranh giới từ API nghiệp vụ đến chương trình cuối cùng diễn giải dữ liệu. Việc bỏ shell và tách argv là nền tảng; hợp đồng đối số, phân quyền, môi trường và bằng chứng toàn luồng mới cho phép nghiệm thu hành vi hệ thống.
