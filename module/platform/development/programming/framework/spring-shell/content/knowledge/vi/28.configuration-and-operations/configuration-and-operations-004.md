# Tách log kỹ thuật khỏi dữ liệu đầu ra dành cho người dùng

## 1. Vì sao cần tách hai loại đầu ra?

Một ứng dụng Spring Shell thường chạy trực tiếp trong terminal. Người dùng nhập command, đọc kết quả và có thể chuyển kết quả đó sang tệp hoặc chương trình khác. Đồng thời, ứng dụng và các thư viện Spring cần ghi nhận thông tin khởi động, thời gian xử lý, lỗi kết nối và chi tiết phục vụ chẩn đoán.

Hai nhu cầu này có mục đích khác nhau:

- **Đầu ra của command** là kết quả mà người dùng cần đọc, sao chép hoặc đưa vào script.
- **Log kỹ thuật** là thông tin dành cho người vận hành và người phát triển để tìm nguyên nhân, theo dõi hoạt động và xử lý sự cố.

Nếu log khởi động hoặc stack trace xuất hiện xen giữa dữ liệu command, người dùng khó đọc kết quả. Với command xuất JSON hoặc CSV, một dòng log chen vào có thể làm hỏng toàn bộ dữ liệu và khiến script phía sau parse thất bại.

Spring Shell 3.4 có tài liệu riêng cảnh báo log console mặc định của Spring Boot có thể trộn với output của shell command. Cách xử lý được khuyến nghị là tắt console log pattern và ghi log vào tệp khi cần giữ log trong ứng dụng shell.

## 2. Phân biệt các kênh đầu ra

| Kênh | Nội dung phù hợp | Cách sử dụng |
|---|---|---|
| Giá trị trả về của command | Kết quả cuối cùng, thông báo thành công hoặc hướng dẫn người dùng | Trả về `String`, object hoặc kiểu kết quả mà Spring Shell hỗ trợ. |
| Terminal writer | Tiến độ, nhiều dòng, nội dung cần in trong lúc command đang chạy | Với `@Command` hoặc programmatic target, lấy writer từ `CommandContext.getTerminal()`; với legacy `@ShellMethod`, inject JLine `Terminal`. |
| Logger | Sự kiện kỹ thuật, thời gian xử lý, trạng thái dependency và exception | Dùng SLF4J `Logger` với các mức log. |
| Tệp log | Nhật ký cần giữ sau khi command kết thúc | Cấu hình `logging.file.name` hoặc Logback appender. |
| stdout/stderr của tiến trình | Kênh tích hợp với shell hệ điều hành và script | Chọn quy ước ổn định, kiểm tra bằng redirect trên môi trường đích. |

Một command nên có hợp đồng đầu ra rõ ràng. Ví dụ, `project list --format=json` chỉ trả JSON hợp lệ; log xử lý, thời gian chạy và stack trace phải đi theo kênh log riêng.

## 3. Dùng giá trị trả về cho kết quả của command

Với command chỉ tạo một kết quả, cách đơn giản nhất là trả về giá trị. Spring Shell nhận giá trị trả về và hiển thị nó trong shell.

~~~java
package com.example.cli.commands;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(key = "project status", value = "Hiển thị trạng thái project")
    public String status() {
        return "Project đang hoạt động";
    }
}
~~~

Nội dung trả về là dữ liệu dành cho người dùng. Không thêm timestamp, thread name, tên logger hoặc stack trace vào chuỗi này chỉ để phục vụ chẩn đoán.

Nếu command trả về JSON hoặc CSV, hãy giữ định dạng đó thuần nhất. Không thêm dòng `Đang xử lý...` trước JSON hoặc `Hoàn tất` sau CSV nếu người dùng dự kiến pipe output vào công cụ parse.

## 4. Dùng Terminal writer khi cần in nhiều dòng hoặc tiến độ

Spring Shell 3.4 cho phép lấy terminal theo kiểu command đang dùng. Với programmatic target hoặc annotation model mới `@Command`, `CommandContext` cung cấp `getTerminal()`. Với legacy `@ShellMethod`, inject JLine `Terminal` vào bean command rồi lấy writer từ terminal đó.

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DiagnosticsCommands {

    private final Terminal terminal;

    public DiagnosticsCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @ShellMethod(key = "diagnostics summary", value = "In báo cáo nhiều dòng")
    public void summary() {
        var writer = terminal.writer();
        writer.println("Trạng thái dịch vụ:");
        writer.println("- Database: sẵn sàng");
        writer.println("- Storage: sẵn sàng");
        writer.flush();
    }
}
~~~

Terminal writer phù hợp với nội dung giao diện như tiến độ hoặc báo cáo nhiều dòng. Không dùng nó để in log debug. Nếu cần hiển thị tiến độ cho người dùng, có thể in một thông điệp ngắn hoặc cập nhật progress view; các chi tiết như thời gian từng bước và stack trace vẫn thuộc logger.

Tránh dùng `System.out.println(...)` trực tiếp trong command khi đã có terminal context. `System.out` bỏ qua abstraction terminal của Spring Shell/JLine và làm việc kiểm thử, redirect hoặc tích hợp terminal khó kiểm soát hơn.

## 5. Ghi log kỹ thuật bằng SLF4J

Spring Boot starter mặc định cấu hình Logback khi logging starter có mặt. Trong code ứng dụng, dùng SLF4J API thay vì gọi trực tiếp Logback để có thể thay logging implementation mà không sửa logic nghiệp vụ.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    private static final Logger log =
            LoggerFactory.getLogger(ExportService.class);

    public ExportResult export(ExportRequest request) {
        log.info("Export started: format={}", request.format());

        // Thực hiện đọc, chuyển đổi và ghi dữ liệu.
        ExportResult result = doExport(request);

        log.info("Export completed: rows={}", result.rows());
        return result;
    }
}
~~~

`ExportRequest`, `ExportResult` và `doExport(...)` là kiểu và logic của ứng dụng ví dụ. Logger được đặt trong service vì service biết các sự kiện kỹ thuật của quá trình export; command chịu trách nhiệm trình bày kết quả phù hợp cho người dùng.

Dùng placeholder `{}` thay vì nối chuỗi:

~~~java
log.debug("Loaded {} records for project {}", count, projectId);
~~~

Logger có thể bỏ qua việc định dạng thông điệp nếu mức `DEBUG` đang tắt. Cách này tránh tạo chuỗi không cần thiết và giúp log dễ tìm kiếm hơn.

## 6. Chọn mức log theo ý nghĩa sự kiện

| Mức | Khi nên dùng | Ví dụ |
|---|---|---|
| `ERROR` | Một thao tác thất bại và cần điều tra hoặc can thiệp | Không thể ghi tệp, database không truy cập được. |
| `WARN` | Có tình huống bất thường nhưng ứng dụng vẫn xử lý được | Dùng giá trị mặc định vì cấu hình tùy chọn bị thiếu. |
| `INFO` | Mốc hoạt động quan trọng ở mức vận hành | Bắt đầu/kết thúc import, số bản ghi đã xử lý. |
| `DEBUG` | Chi tiết phục vụ điều tra trong môi trường phát triển hoặc khi bật chẩn đoán | Tên bước, thời gian từng bước, số lần retry. |
| `TRACE` | Dấu vết rất chi tiết của một luồng xử lý | Chi tiết vòng lặp hoặc protocol ở mức thấp. |

Không ghi mọi bước ở `INFO`; log quá nhiều khiến sự kiện quan trọng khó tìm và làm tăng chi phí lưu trữ. Cũng không ghi lỗi nghiệp vụ do người dùng nhập sai thành `ERROR` nếu đó là trường hợp dự kiến và đã được xử lý bình thường. Dùng `WARN` hoặc chỉ trả thông báo validation phù hợp.

## 7. Ví dụ command trả kết quả sạch và log lỗi có mã tham chiếu

Ví dụ sau tách thông điệp dành cho người dùng khỏi chi tiết exception. Người dùng nhận thông báo ngắn cùng mã tham chiếu; log giữ stack trace để người vận hành tìm nguyên nhân.

~~~java
package com.example.cli.commands;

import java.io.IOException;
import java.nio.file.Path;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ExportCommands {

    private static final Logger log =
            LoggerFactory.getLogger(ExportCommands.class);

    private final ExportService exportService;

    public ExportCommands(ExportService exportService) {
        this.exportService = exportService;
    }

    @ShellMethod(key = "report export", value = "Xuất báo cáo")
    public String export(
            @ShellOption("--file") String file,
            @ShellOption(defaultValue = "csv") String format) {

        String operationId = UUID.randomUUID().toString();
        log.info("Export requested: operationId={}, format={}", operationId, format);

        try {
            ExportResult result = exportService.export(
                    new ExportRequest(Path.of(file), format));

            log.info("Export completed: operationId={}, rows={}",
                    operationId, result.rows());

            return "Đã xuất " + result.rows()
                    + " dòng. Mã thao tác: " + operationId;
        }
        catch (InvalidExportRequest ex) {
            log.warn("Export rejected: operationId={}, code={}",
                    operationId, ex.code());
            return "Không thể xuất báo cáo: " + ex.safeMessage();
        }
        catch (IOException ex) {
            log.error("Export failed: operationId={}", operationId, ex);
            throw new ExportCommandException(
                    "Không thể hoàn tất export. Mã tham chiếu: " + operationId, ex);
        }
    }
}
~~~

`ExportService`, `ExportRequest`, `ExportResult`, `InvalidExportRequest` và `ExportCommandException` là kiểu của ứng dụng ví dụ. Exception handler của ứng dụng nên trình bày message an toàn của `ExportCommandException`; stack trace đã được ghi vào log. Nếu command cần trả exit code khác 0 cho script khi lỗi, hãy cấu hình cơ chế exit code riêng của ứng dụng thay vì dựa vào nội dung chuỗi trả về.

Mã tham chiếu giúp nối thông báo mà người dùng nhìn thấy với bản ghi log tương ứng. Không cần đưa toàn bộ stack trace hoặc thông tin nội bộ như JDBC URL vào output của command.

## 8. Tắt console log và ghi log vào tệp

Đây là cấu hình phù hợp khi terminal cần dành cho kết quả command. Trong `application.yml`, đặt console pattern rỗng và cấu hình tên file log:

~~~yaml
logging:
  pattern:
    console: ""
  file:
    name: logs/spring-shell.log
  level:
    root: INFO
    com.example.cli: DEBUG
    org.springframework.shell: WARN
~~~

Ý nghĩa:

- `logging.pattern.console: ""` làm im lặng console logging theo hướng dẫn Spring Shell 3.4.
- `logging.file.name` bật ghi log vào `logs/spring-shell.log`, đường dẫn tương đối tính từ working directory của tiến trình.
- `logging.level.root` đặt mức mặc định cho toàn ứng dụng.
- `logging.level.com.example.cli` cho phép xem chi tiết của code ứng dụng khi cần.
- `logging.level.org.springframework.shell` giảm bớt log framework không cần thiết trong vận hành thông thường.

Nếu chỉ cấu hình `logging.file.name` mà không tắt console pattern, log vẫn được ghi ra console và có thể tiếp tục trộn với kết quả command. Hai cấu hình này giải quyết hai mục tiêu khác nhau: giữ log trong file và giữ console sạch.

Spring Boot mặc định dùng Logback khi ứng dụng sử dụng các starter. File log mặc định được xoay vòng khi đạt kích thước giới hạn mặc định 10 MB; chính sách lưu trữ có thể cấu hình thêm bằng các thuộc tính `logging.logback.rollingpolicy.*`.

## 9. Điều chỉnh log level khi chạy ứng dụng

Khi cần bật debug tạm thời, Spring Shell 3.4 khuyến nghị dùng các cơ chế cấu hình của Spring Boot như JVM system property hoặc biến môi trường. Không nên giả định mọi logging property đều có thể truyền như option của command Spring Shell.

Linux/macOS:

~~~bash
java -Dlogging.level.com.example.cli=DEBUG -jar build-cli.jar report export --file=data.csv
~~~

Windows PowerShell:

~~~powershell
$env:LOGGING_LEVEL_COM_EXAMPLE_CLI = "DEBUG"
java -jar .\build-cli.jar
~~~

Đặt lại mức `INFO` sau khi điều tra xong. Tránh bật `DEBUG` hoặc `TRACE` lâu dài nếu log chứa dữ liệu nhạy cảm hoặc có lưu lượng lớn.

## 10. Khi cần log xuất hiện trên terminal nhưng không lẫn vào stdout

Một số môi trường vận hành muốn xem log trực tiếp mà vẫn giữ stdout dành cho dữ liệu command. Có thể cấu hình Logback ConsoleAppender ghi sang `System.err`.

Tạo `src/main/resources/logback-spring.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>

    <appender name="CONSOLE_ERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>${CONSOLE_LOG_PATTERN}</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE_ERR"/>
    </root>
</configuration>
~~~

Với cấu hình này, log đi qua stderr còn output command đi qua terminal writer của Spring Shell. Hãy kiểm tra hành vi trên non-interactive runner và terminal thực tế của ứng dụng trước khi dựa vào quy ước redirect này trong script. Nếu cần giữ log lâu dài, có thể cấu hình thêm file appender thay vì chỉ ghi stderr.

Đây là cấu hình thay thế cho cách tắt console pattern ở phần 8. Khi dùng appender này, hãy bỏ `logging.pattern.console: ""`; nếu giữ property đó, pattern được chuyển sang `CONSOLE_LOG_PATTERN` có thể rỗng và log stderr cũng không hiển thị nội dung.

Ví dụ khi command được chạy ở chế độ non-interactive và các kênh đã được xác nhận:

~~~bash
java -jar build-cli.jar report export --file=data.csv > result.txt 2> diagnostic.log
~~~

`result.txt` chứa output command; `diagnostic.log` chứa log console gửi qua stderr. Nếu ứng dụng dùng cấu hình file-only ở phần trước, log sẽ nằm trong file log được cấu hình thay vì `diagnostic.log`.

Không giả định mọi terminal emulator, test harness hoặc interactive session đều có cách xử lý stdout/stderr giống nhau. Kiểm tra cả khi chạy trong terminal trực tiếp, khi redirect và khi output được pipe sang chương trình khác.

## 11. Giữ log có ngữ cảnh để tìm sự cố

Log hữu ích cần cho biết sự kiện nào xảy ra, liên quan đến tác vụ nào và kết quả ra sao. Với command chạy lâu hoặc có nhiều tác vụ nền, tạo operation ID hoặc task ID rồi dùng ID đó trong các log liên quan.

~~~java
String operationId = UUID.randomUUID().toString();
log.info("Import started: operationId={}", operationId);

try {
    ImportResult result = importService.run(request);
    log.info("Import completed: operationId={}, rows={}",
            operationId, result.rows());
}
catch (IOException ex) {
    log.error("Import failed: operationId={}", operationId, ex);
    throw ex;
}
~~~

Nếu cần thêm correlation ID vào mọi dòng log trong một luồng đồng bộ, có thể dùng MDC của SLF4J. Luôn xóa MDC trong `finally` vì thread pool tái sử dụng thread cho nhiều lần thực thi:

~~~java
import org.slf4j.MDC;

String operationId = UUID.randomUUID().toString();
MDC.put("operationId", operationId);
try {
    importService.run(request);
}
finally {
    MDC.remove("operationId");
}
~~~

Để hiển thị giá trị MDC, cấu hình pattern Logback có `%X{operationId}`. MDC không tự truyền qua mọi thread hoặc executor; nếu tác vụ chuyển sang worker thread, hãy truyền operation ID tường minh hoặc cấu hình cơ chế context propagation phù hợp.

## 12. Không ghi dữ liệu bí mật hoặc đầu vào nhạy cảm

Log có thể được lưu lâu hơn output terminal, được gửi đến hệ thống tập trung và được nhiều người vận hành truy cập. Không ghi trực tiếp:

- Mật khẩu, access token, refresh token, API key hoặc private key.
- Header `Authorization`, cookie hoặc nội dung credential.
- Dữ liệu cá nhân không cần thiết cho chẩn đoán.
- Toàn bộ payload hoặc file người dùng nếu chỉ cần biết kích thước, loại dữ liệu hoặc mã bản ghi.

Thay vì ghi token, hãy ghi loại xác thực, tên provider hoặc mã tham chiếu không nhạy cảm. Thay vì log toàn bộ nội dung request, hãy ghi operation ID, loại thao tác, số bản ghi và kết quả.

Nếu phải log giá trị do người dùng nhập, hãy giới hạn độ dài và xử lý ký tự xuống dòng để tránh log injection. Không nối chuỗi đầu vào tùy ý thành nhiều dòng log có vẻ như sự kiện riêng biệt.

## 13. Phân biệt command history và application log

Spring Shell có thể lưu lịch sử command để người dùng xem lại lệnh đã nhập. Command history phục vụ trải nghiệm shell; application log phục vụ vận hành và chẩn đoán.

Hai loại này có chính sách lưu trữ và quyền truy cập khác nhau. Lịch sử command có thể chứa option hoặc đường dẫn do người dùng nhập. Nếu command nhận secret qua tham số, hãy tránh đưa secret trực tiếp vào command line vì nó có thể xuất hiện trong shell history, process listing hoặc log của môi trường chạy.

Đối với dữ liệu nhạy cảm, ưu tiên cơ chế nhập an toàn hoặc lấy từ secret store/environment được bảo vệ, rồi tránh ghi lại giá trị đó trong output và log.

## 14. Kiểm thử để bảo đảm log không làm bẩn output

Kiểm thử riêng hai hợp đồng:

1. **Hợp đồng output:** command trả đúng nội dung, đúng định dạng và không chứa timestamp, log level, tên logger hoặc stack trace.
2. **Hợp đồng log:** sự kiện quan trọng được ghi với level phù hợp; lỗi có stack trace và operation ID; dữ liệu bí mật không xuất hiện.

Các trường hợp nên kiểm tra:

- Command thành công: người dùng nhận thông báo hoặc JSON/CSV đúng định dạng; log có sự kiện hoàn tất.
- Validation thất bại: người dùng nhận hướng dẫn có thể hành động; log ghi mã lỗi nghiệp vụ ở mức phù hợp.
- Lỗi hạ tầng: output có thông báo an toàn và mã tham chiếu; log chứa exception đầy đủ.
- Console logging đã tắt: kết quả command vẫn hiển thị bình thường.
- File logging bật: log được ghi vào đúng file và thư mục có quyền phù hợp.
- Redirect stdout/stderr: dữ liệu command và log được tách theo quy ước đã chọn.
- Debug bật tạm thời: log chi tiết xuất hiện theo package đã cấu hình và có thể tắt lại.
- Nhiều command chạy liên tiếp: MDC hoặc operation ID không bị rò từ lần gọi trước sang lần gọi sau.

Với Spring Shell test support, dùng `@ShellTest` và `ShellTestClient` để kiểm tra nội dung shell screen. Kiểm tra file log bằng thư mục tạm riêng của test; không phụ thuộc vào log file còn sót lại từ lần chạy trước.

## 15. Các lỗi thiết kế thường gặp

**Dùng logger để in kết quả command:** log có timestamp, level và metadata; format có thể thay đổi theo môi trường. Hãy trả kết quả qua command hoặc terminal writer.

**Dùng `System.out` cho mọi nội dung:** cách này bỏ qua terminal abstraction và có thể gây khó khăn cho test hoặc interactive rendering. Dùng API của Spring Shell.

**Chỉ đặt `logging.file.name` rồi nghĩ console đã sạch:** thuộc tính này bật file output nhưng mặc định console appender vẫn có thể hoạt động. Với Spring Shell 3.4, đặt `logging.pattern.console` rỗng hoặc cấu hình appender phù hợp.

**Ghi stack trace vào output người dùng:** stack trace là thông tin chẩn đoán, có thể lộ đường dẫn nội bộ hoặc cấu trúc hệ thống. Ghi exception bằng logger và hiển thị thông báo an toàn kèm mã tham chiếu.

**Log tất cả ở `INFO`:** log quá nhiều khiến vận hành khó đọc. Chọn level theo ý nghĩa sự kiện và bật `DEBUG` khi cần điều tra.

**Ghi secret vào log hoặc command history:** thông tin nhạy cảm có thể tồn tại lâu và bị truy cập ngoài dự kiến. Hãy loại bỏ hoặc che dữ liệu trước khi ghi.

**Không kiểm tra redirect:** output có thể trông đúng trong terminal nhưng bị hỏng khi pipe hoặc redirect. Hãy kiểm tra stdout/stderr trong môi trường chạy thật.

## 16. Checklist trước khi phát hành

- [ ] Kết quả command được trả về qua Spring Shell hoặc terminal writer.
- [ ] Logger SLF4J chỉ dùng cho sự kiện kỹ thuật.
- [ ] Console log không trộn với output command theo chế độ chạy đã chọn.
- [ ] File log có đường dẫn và quyền ghi phù hợp.
- [ ] Log level mặc định không quá chi tiết.
- [ ] Có operation ID hoặc task ID cho tác vụ cần điều tra.
- [ ] Exception được log với stack trace ở kênh kỹ thuật.
- [ ] Output lỗi không lộ stack trace hoặc thông tin nội bộ.
- [ ] Không ghi password, token, key hoặc payload nhạy cảm.
- [ ] MDC được dọn sau mỗi lần thực thi và có chính sách truyền context qua worker thread.
- [ ] Đã kiểm thử output, file log và redirect stdout/stderr.
- [ ] Đã kiểm tra log rotation và thời gian lưu trữ theo chính sách vận hành.

## Kết luận

Đầu ra của command là hợp đồng giao tiếp với người dùng hoặc script; log kỹ thuật là dữ liệu dành cho vận hành. Trong Spring Shell 3.4, hãy dùng giá trị trả về hoặc terminal writer cho nội dung shell (inject JLine `Terminal` với legacy `@ShellMethod`, hoặc lấy terminal từ `CommandContext` với `@Command`/programmatic target), dùng SLF4J cho log và cấu hình Spring Boot để đưa log vào file hoặc stderr riêng. Khi tách đúng hai kênh, output giữ được định dạng ổn định, log vẫn đủ ngữ cảnh để điều tra và các script có thể xử lý kết quả mà không bị nhiễu.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – Logging](https://docs.spring.io/spring-shell/reference/3.4/customization/logging.html)
- [Spring Shell 3.4.3 – Writing](https://docs.spring.io/spring-shell/reference/3.4/commands/writing.html)
- [Spring Shell 3.4.3 API – CommandContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandContext.html)
- [Spring Shell 3.4.3 – Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [Spring Boot 3.4 – Logging](https://docs.spring.io/spring-boot/3.4/reference/features/logging.html)
- [Spring Boot 3.4 – Logging Configuration](https://docs.spring.io/spring-boot/3.4/how-to/logging.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
