# Nội dung dành cho người dùng khác chi tiết phục vụ chẩn đoán

Một command CLI cần thông báo rõ cho người dùng biết thao tác đã thành công hay thất bại và họ nên làm gì tiếp theo. Khi có lỗi, đội phát triển lại cần thêm thông tin kỹ thuật như exception, nguyên nhân gốc, stack trace và ngữ cảnh thực thi để tìm vấn đề. Hai nhu cầu này liên quan nhưng không nên trộn thành một thông báo duy nhất.

Thông báo hướng người dùng cần ngắn, chính xác và có thể hành động. Thông tin chẩn đoán cần đủ chi tiết để điều tra, nhưng phải được ghi vào kênh phù hợp và bảo vệ dữ liệu nhạy cảm. Spring Shell cung cấp `CommandContext`, `ExitStatusExceptionMapper` và các result handler để hỗ trợ việc tách hai lớp thông tin này.

Bài sử dụng Spring Shell 4.x, tham chiếu tài liệu 4.0.4.

## 1. Hai đối tượng đọc thông tin khác nhau

Người đang chạy command thường chỉ cần biết kết quả và cách xử lý tiếp theo. Người vận hành hoặc developer cần thông tin sâu hơn để xác định nguyên nhân. Có thể phân biệt như sau:

| Nội dung | Dành cho | Ví dụ |
|---|---|---|
| Kết quả thao tác | Người dùng | `Đã xuất báo cáo report-42.` |
| Hướng dẫn sửa lỗi | Người dùng | `Không tìm thấy báo cáo. Kiểm tra mã báo cáo rồi thử lại.` |
| Mã tham chiếu | Người dùng và bộ phận hỗ trợ | `Mã tham chiếu: 7a6...` |
| Exception type và cause | Developer/vận hành | `AccessDeniedException`, `IOException` |
| Stack trace | Developer/vận hành | Chuỗi lời gọi dẫn tới vị trí phát sinh lỗi |
| Ngữ cảnh kỹ thuật | Developer/vận hành | command, report ID, thời điểm, correlation ID, endpoint đã che dữ liệu nhạy cảm |

Ví dụ, nếu người dùng không có quyền ghi file, thông báo phù hợp là:

```text
Không thể xuất báo cáo tới thư mục đã chọn.
Hãy kiểm tra quyền ghi hoặc chọn thư mục khác.
Mã tham chiếu: 7a6f2d...
```

Log chẩn đoán có thể ghi:

```text
ERROR Report export failed: reportId=report-42, referenceId=7a6f2d..., cause=AccessDeniedException
```

Stack trace và chi tiết hệ thống được giữ trong log hoặc công cụ chẩn đoán. Người dùng không cần đọc tên class nội bộ, đường dẫn tuyệt đối trên máy chủ hay chuỗi lời gọi Java để biết cách khắc phục.

## 2. Thiết kế thông báo hướng người dùng

Một thông báo tốt thường trả lời ba câu hỏi:

1. **Điều gì đã xảy ra?** Nêu kết quả hoặc thao tác không hoàn tất.
2. **Người dùng có thể làm gì?** Đưa ra bước tiếp theo cụ thể nếu có thể khắc phục.
3. **Cần cung cấp thông tin gì khi nhờ hỗ trợ?** Đưa mã tham chiếu hoặc mã lỗi ổn định nếu cần điều tra.

Nên ưu tiên câu ngắn và dùng thuật ngữ mà người sử dụng CLI hiểu được. Ví dụ:

| Không nên hiển thị | Nên hiển thị |
|---|---|
| `java.nio.file.AccessDeniedException: /srv/app/private/out.csv` | `Không có quyền ghi vào thư mục đích. Hãy chọn thư mục khác hoặc kiểm tra quyền ghi.` |
| `NullPointerException at ReportService.java:84` | `Không thể tạo báo cáo do dữ liệu đầu vào chưa đầy đủ. Kiểm tra bộ lọc rồi thử lại.` |
| `HTTP 503 from https://internal-host:8443` | `Dịch vụ báo cáo hiện chưa phản hồi. Hãy thử lại sau ít phút.` |
| `ConstraintViolationException` | `Giá trị ngày kết thúc phải bằng hoặc sau ngày bắt đầu.` |

Không khẳng định nguyên nhân khi ứng dụng chưa xác định được nguyên nhân. Nếu chỉ biết thao tác thất bại, hãy nói rõ thao tác chưa hoàn tất và đưa mã tham chiếu để hỗ trợ điều tra.

## 3. Dùng `CommandContext.outputWriter()` để ghi kết quả

Trong Spring Shell 4, `CommandContext` cung cấp `PrintWriter` qua `outputWriter()`. Tài liệu khuyến nghị dùng writer này để in nội dung command thay vì ghi trực tiếp bằng `System.out`.

Ví dụ:

```java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class StatusCommands {

    @Command(name = "system status", description = "Hiển thị trạng thái hệ thống")
    public void status(CommandContext context) {
        context.outputWriter().println("Hệ thống đang hoạt động.");
        context.outputWriter().flush();
    }
}
```

`flush()` đẩy nội dung đã ghi ra writer ngay tại thời điểm đó. Điều này hữu ích khi command tạo output theo từng giai đoạn hoặc cần hiển thị kết quả trước khi tiếp tục xử lý.

`CommandContext` 4.x cung cấp `outputWriter`, `inputReader`, dữ liệu input đã parse và command registry. API này không có `errorWriter()` riêng. Vì vậy, không nên viết code dựa trên một phương thức `context.errorWriter()` không tồn tại. Hãy dùng result handling/exception mapping của Spring Shell cho lỗi command và logging framework cho thông tin chẩn đoán.

## 4. Chọn dạng output theo mục đích command

Với command chỉ trả một kết quả đơn giản, kiểu trả về có thể là `String`, số hoặc object phù hợp với result handler. Khi cần định dạng nhiều dòng, bảng hoặc output có cấu trúc, có thể dùng `CommandContext.outputWriter()`.

Ví dụ kết quả cho người dùng:

```text
Đã đồng bộ 18 tài khoản.
Thành công: 16
Bỏ qua: 2
Thất bại: 0
```

Với automation, output nên ổn định và có thể phân tích bằng máy. Nếu command xuất JSON, đừng trộn thêm dòng chào mừng, log debug hoặc stack trace vào cùng stdout. Các dòng phụ có thể làm hỏng JSON hoặc CSV mà script đang đọc.

Ví dụ JSON:

```json
{
  "status": "success",
  "reportId": "report-42",
  "rowsExported": 18
}
```

Nếu cần hỗ trợ cả người dùng tương tác và script, hãy cân nhắc option định dạng như `--output json` hoặc `--output text`. Mỗi định dạng cần có schema/contract rõ ràng và được kiểm thử. Không thay đổi tên field hoặc cách biểu diễn lỗi một cách tùy tiện giữa các phiên bản.

## 5. Phân biệt output command với logging

Output command là một phần giao diện mà người dùng hoặc chương trình gọi command tiêu thụ. Logging ghi lại sự kiện và ngữ cảnh để vận hành, giám sát hoặc chẩn đoán.

| Kênh | Mục đích | Nội dung phù hợp |
|---|---|---|
| Command output | Phản hồi trực tiếp cho người dùng | Kết quả, hướng dẫn, bảng dữ liệu, mã tham chiếu |
| Application log | Chẩn đoán và vận hành | Exception, cause, stack trace, thời gian, ID nghiệp vụ đã lọc |
| Process exit code | Báo thành công/thất bại cho hệ điều hành | Mã số ổn định theo quy ước ứng dụng |

Không dùng `System.out.println()` thay cho logger trong service. Nếu stdout được pipe sang chương trình khác, log có thể bị hiểu nhầm là dữ liệu kết quả. Với CLI tương tác, log ghi ra console liên tục cũng có thể chen vào prompt và làm khó đọc. Có thể cấu hình logging backend ghi ra file hoặc một đích log riêng phù hợp môi trường.

Ví dụ Spring Boot ghi log vào file:

```yaml
logging:
  file:
    name: logs/admin-cli.log
  level:
    root: INFO
    com.example.admin: DEBUG
```

Hãy chọn mức log theo môi trường. `DEBUG` và `TRACE` hữu ích khi điều tra nhưng có thể tạo lượng dữ liệu lớn hoặc vô tình ghi thêm thông tin nhạy cảm. Trên production, chỉ bật mức chi tiết khi có lý do và thời hạn rõ ràng.

## 6. Ghi log chẩn đoán bằng SLF4J

Dùng logger để ghi thông tin kỹ thuật tại tầng có đủ ngữ cảnh. Khi log exception, truyền chính exception vào logger để backend có thể ghi stack trace và cause.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    private static final Logger log =
            LoggerFactory.getLogger(ReportService.class);

    public void export(String reportId, Path output, String referenceId) {
        try {
            String csv = loadReportCsv(reportId);
            Files.writeString(output, csv);
        } catch (IOException exception) {
            log.error(
                    "Report export failed. reportId={}, referenceId={}",
                    reportId,
                    referenceId,
                    exception);
            throw new ReportExportException(referenceId, exception);
        }
    }

    private String loadReportCsv(String reportId) {
        // Thay bằng truy vấn repository; ví dụ này chỉ minh họa luồng xử lý.
        if (!"report-42".equals(reportId)) {
            throw new ReportNotFoundException(reportId);
        }
        return "id,name\n42,Example\n";
    }
}
```

Log có cấu trúc với placeholder `{}` giúp giữ riêng giá trị và thông điệp. Tránh nối chuỗi thủ công nếu logger hỗ trợ parameterized logging. Ghi exception ở một ranh giới xử lý phù hợp; nếu mọi tầng đều log cùng một exception rồi ném tiếp, một lỗi có thể tạo nhiều bản ghi giống nhau và gây nhiễu khi điều tra.

Chỉ ghi dữ liệu cần thiết để chẩn đoán. Nếu đường dẫn, tên người dùng, câu truy vấn hoặc URL có thể chứa dữ liệu riêng tư, hãy rút gọn, che hoặc thay bằng định danh đã kiểm soát.

## 7. Trả thông báo lỗi thân thiện bằng `ExitStatusExceptionMapper`

Spring Shell cung cấp `ExitStatusExceptionMapper` để ánh xạ exception phát sinh trong command thành `ExitStatus` có mã và thông báo phù hợp cho người dùng. Với command khai báo bằng annotation, có thể tham chiếu bean mapper qua thuộc tính `exitStatusExceptionMapper`.

Ví dụ exception nghiệp vụ giữ mã tham chiếu:

```java
class ReportExportException extends RuntimeException {

    private final String referenceId;

    ReportExportException(String referenceId, Throwable cause) {
        super("Report export failed", cause);
        this.referenceId = referenceId;
    }

    String referenceId() {
        return referenceId;
    }
}
```

Lỗi nghiệp vụ báo cáo không tồn tại có thể được biểu diễn bằng một exception riêng:

```java
class ReportNotFoundException extends RuntimeException {

    ReportNotFoundException(String reportId) {
        super("Report not found: " + reportId);
    }
}
```

Mapper chuyển exception thành thông báo có thể hiểu được:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class CommandErrorConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(CommandErrorConfiguration.class);

    @Bean
    ExitStatusExceptionMapper commandErrorMapper() {
        return exception -> {
            if (exception instanceof ReportNotFoundException) {
                return new ExitStatus(4,
                        "Không tìm thấy báo cáo. Hãy kiểm tra mã báo cáo.");
            }
            if (exception instanceof ReportExportException exportException) {
                return new ExitStatus(5,
                        "Không thể xuất báo cáo. Mã tham chiếu: "
                                + exportException.referenceId());
            }
            log.error("Unexpected command failure", exception);
            return new ExitStatus(1,
                    "Command không thể hoàn tất. Hãy kiểm tra log ứng dụng hoặc liên hệ hỗ trợ.");
        };
    }
}
```

Gắn mapper vào command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    private final ReportService reportService;

    ReportCommands(ReportService reportService) {
        this.reportService = reportService;
    }

    @Command(
        name = "report export",
        description = "Xuất báo cáo",
        exitStatusExceptionMapper = "commandErrorMapper"
    )
    public String export(
            @Option(longName = "id", required = true) String reportId,
            @Option(longName = "output", required = true) String output) {
        String referenceId = java.util.UUID.randomUUID().toString();
        reportService.export(reportId, java.nio.file.Path.of(output), referenceId);
        return "Đã xuất báo cáo " + reportId + ".";
    }
}
```

Mã `4`, `5` và `1` là quy ước minh họa của ứng dụng. Hãy định nghĩa mã ổn định để script hoặc người vận hành có thể phân loại lỗi. Mapper chỉ kiểm soát `ExitStatus` của command; nó không tự cấu hình JVM process exit code. Đây là hai tầng kết quả riêng biệt.

## 8. Spring Shell xử lý exception như thế nào?

Spring Shell có result handler dành cho `Throwable`. `ThrowableResultHandler` hiển thị thông báo exception trên terminal bằng màu đỏ và lưu exception cuối cùng để người dùng có thể xem chi tiết trong interactive mode. Trong non-interactive mode, stack trace được in ra vì không có phiên shell còn mở để người dùng gọi command xem chi tiết.

Trong interactive shell, command built-in `stacktrace` cho phép xem đầy đủ stack trace của lỗi gần nhất. Đây là công cụ chẩn đoán, không phải thông báo thành công/thất bại thông thường mà command nghiệp vụ nên tự in ra sau mỗi lần chạy.

Spring Shell cũng có debug mode:

```yaml
spring:
  shell:
    debug:
      enabled: true
```

Khi bật `spring.shell.debug.enabled`, Spring Shell in thêm thông tin debug, bao gồm stack trace của lỗi command. Tính năng này hữu ích trong phát triển và troubleshooting. Trên production, chỉ bật khi cần vì stack trace có thể tiết lộ package, class, đường dẫn và chi tiết hạ tầng.

Nếu đã dùng `ExitStatusExceptionMapper`, hãy kiểm tra tương tác giữa mapper và result handler trong đúng mode chạy của ứng dụng. Không giả định mapper tự ghi log stack trace hoặc thay thế toàn bộ logging của ứng dụng.

## 9. Phân loại lỗi trước khi hiển thị

Không phải exception nào cũng cần một thông báo giống nhau. Có thể chia thành ba nhóm:

| Nhóm | Ví dụ | Thông báo phù hợp |
|---|---|---|
| Lỗi người dùng có thể sửa | Thiếu option, định dạng ngày sai, file không tồn tại | Nêu trường sai và cách nhập đúng |
| Lỗi nghiệp vụ đã biết | Báo cáo không tồn tại, tài khoản bị khóa, thao tác không được phép | Nêu kết quả nghiệp vụ và bước tiếp theo được phép |
| Lỗi kỹ thuật không dự kiến | Database unavailable, lỗi lập trình, hỏng kết nối | Thông báo chung, mã tham chiếu; chi tiết nằm trong log |

Với lỗi validation, ưu tiên thông báo cụ thể:

```text
Giá trị --limit phải nằm trong khoảng từ 1 đến 500.
```

Với lỗi kỹ thuật:

```text
Không thể hoàn tất thao tác do lỗi hệ thống.
Mã tham chiếu: 7a6f2d...
```

Không hiển thị thông tin nội bộ như SQL statement, JDBC URL, access token, mật khẩu, stack trace hoặc đường dẫn bí mật cho người dùng thông thường. Nếu người vận hành cần thêm chi tiết, hãy cung cấp cơ chế chẩn đoán có kiểm soát.

## 10. Bảo vệ dữ liệu nhạy cảm trong output và log

CLI thường chạy trong terminal có history, log, CI output hoặc hệ thống thu thập console. Vì vậy, dữ liệu in ra có thể được lưu lâu hơn dự kiến.

Không ghi các nội dung sau vào thông báo hoặc log thông thường:

- Password, access token, refresh token, API key hoặc private key.
- Header `Authorization`, cookie hoặc session secret.
- Toàn bộ nội dung file có dữ liệu cá nhân hoặc dữ liệu khách hàng.
- Chuỗi kết nối chứa username/password.
- Query hoặc URL có tham số nhạy cảm.

Nếu cần đối chiếu một tài khoản hoặc tài nguyên, dùng ID nội bộ hoặc giá trị đã che. Ví dụ, chỉ log `userId=U-1042`, không log token xác thực của người dùng đó.

Mã tham chiếu nên là định danh ngẫu nhiên hoặc định danh tác vụ không chứa dữ liệu bí mật. Không dùng password, email đầy đủ hoặc access token làm correlation ID.

## 11. Giữ stdout ổn định cho automation

Trong non-interactive mode, output có thể được script hoặc CI đọc. Nếu command trả JSON/CSV, stdout nên chỉ chứa dữ liệu theo contract đã công bố. Log chẩn đoán nên đi tới file hoặc kênh riêng; tránh trộn timestamp, stack trace và dòng log vào payload.

Ví dụ một lần chạy thành công:

```text
{"status":"success","reportId":"report-42","rowsExported":18}
```

Ví dụ thất bại với thông báo máy có thể xử lý:

```text
{"status":"error","code":"REPORT_EXPORT_FAILED","referenceId":"7a6f2d..."}
```

Nếu command dùng JSON như output contract, hãy thống nhất cả lỗi cũng theo JSON. Đừng để một số lỗi trả JSON còn exception khác lại in stack trace lẫn vào stdout mà không có quy ước. Kiểm thử output bằng parser JSON/CSV thật thay vì chỉ so sánh một phần chuỗi trên terminal.

Với contract JSON nghiêm ngặt, hãy xử lý các lỗi dự kiến ở ranh giới command và tạo response JSON có schema lỗi thống nhất. Nếu để exception đi qua result handler mặc định, nội dung terminal có thể là thông báo lỗi hoặc stack trace tùy mode, không phải JSON envelope của ứng dụng. `ExitStatusExceptionMapper` giúp chuẩn hóa command status và thông báo, nhưng tự nó không biến mọi output lỗi thành JSON.

## 12. Kiểm thử thông báo và diagnostics

Kiểm thử cần xác nhận người dùng thấy đúng thông tin và log giữ đủ dữ liệu kỹ thuật:

1. Khi thành công, output nêu rõ thao tác và kết quả có ý nghĩa.
2. Khi input sai, output chỉ rõ option hoặc giá trị cần sửa.
3. Khi gặp lỗi nghiệp vụ đã biết, mapper trả đúng thông báo và command status.
4. Khi gặp lỗi kỹ thuật, người dùng nhận thông báo chung cùng mã tham chiếu.
5. Log có exception gốc, cause và ngữ cảnh cần thiết để điều tra.
6. Log không chứa token, password hoặc dữ liệu nhạy cảm.
7. Interactive mode cho phép dùng `stacktrace` để xem chi tiết lỗi gần nhất.
8. Non-interactive mode có hành vi lỗi và mã thoát đã được kiểm thử.
9. Output JSON/CSV không bị log hoặc stack trace làm hỏng định dạng.
10. `spring.shell.debug.enabled` chỉ được bật trong profile hoặc môi trường cần debug.

Ví dụ kiểm thử command bằng `@ShellTest` và `ShellTestClient` cần xác nhận output hiển thị cho người dùng. Phần log có thể kiểm thử riêng bằng appender test của logging backend hoặc bằng integration test ghi log vào file tạm.

## 13. Bài tập thực hành

Xây dựng command `report export --id <report-id> --output <path>`. Command cần xử lý các trường hợp báo cáo không tồn tại, thư mục đích không có quyền ghi và lỗi kỹ thuật không dự kiến.

Hãy thực hiện:

1. Dùng `CommandContext.outputWriter()` để hiển thị kết quả thành công.
2. Tạo `ReportNotFoundException` cho lỗi nghiệp vụ đã biết.
3. Tạo `ReportExportException` chứa reference ID và cause.
4. Ghi log exception cùng report ID và reference ID bằng SLF4J.
5. Dùng `ExitStatusExceptionMapper` để trả thông báo ngắn, dễ hiểu.
6. Không đưa stack trace hoặc đường dẫn nội bộ vào thông báo người dùng.
7. Thử command trong interactive mode và xem chi tiết bằng `stacktrace`.
8. Thử non-interactive mode, xác nhận hành vi exception, output và process exit code.
9. Chạy với output JSON và xác nhận stdout vẫn parse được.
10. Tìm trong log và output để bảo đảm không có token, password hoặc thông tin nhạy cảm.

**Kết quả cần nộp:** command, exception mapper, ví dụ output thành công/thất bại, log chẩn đoán và kết quả kiểm thử bảo mật thông tin.

## 14. Checklist thiết kế output và diagnostics

- [ ] Thông báo hướng người dùng mô tả kết quả và bước tiếp theo.
- [ ] Lỗi có thể sửa được nêu rõ trường hoặc giá trị cần kiểm tra.
- [ ] Lỗi kỹ thuật dùng thông báo an toàn và mã tham chiếu.
- [ ] Command dùng `CommandContext.outputWriter()` khi cần ghi trực tiếp vào shell.
- [ ] Không giả định `CommandContext` có `errorWriter()`.
- [ ] Exception được ánh xạ bằng `ExitStatusExceptionMapper` khi cần mã và thông báo command ổn định.
- [ ] Log giữ exception/cause/stack trace ở kênh chẩn đoán phù hợp.
- [ ] Không log hoặc in bí mật, token, password hay dữ liệu cá nhân không cần thiết.
- [ ] Output máy đọc được không bị trộn với log hoặc stack trace.
- [ ] Đã phân biệt command `ExitStatus` và JVM process exit code.
- [ ] `stacktrace` và debug mode được dùng có kiểm soát.
- [ ] Đã kiểm thử cả interactive lẫn non-interactive mode.

## Tài liệu tham khảo

- [Spring Shell Reference — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell Reference — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell Reference — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell Reference — Execution and Debug Mode](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell Reference — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell API — `CommandContext`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell API — `ThrowableResultHandler`](https://docs.spring.io/spring-shell/docs/current-SNAPSHOT/api/org/springframework/shell/result/ThrowableResultHandler.html)
- [Spring Shell API — `ExitStatusExceptionMapper`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
