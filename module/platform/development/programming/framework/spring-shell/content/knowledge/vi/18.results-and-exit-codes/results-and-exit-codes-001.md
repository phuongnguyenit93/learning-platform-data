# Phân biệt kết quả nghiệp vụ, nội dung hiển thị và mã thoát tiến trình

## 1. Một command có nhiều loại kết quả

Khi một command chạy xong, người dùng có thể nhìn thấy một thông báo, ứng dụng có thể nhận được một đối tượng nghiệp vụ, shell có thể ghi nhận trạng thái thực thi và hệ điều hành có thể nhận mã thoát của tiến trình. Những giá trị này liên quan với nhau nhưng không đồng nghĩa.

Ví dụ command `invoice show --id=42`:

- **Kết quả nghiệp vụ:** hóa đơn có mã `42`, tổng tiền và trạng thái thanh toán.
- **Nội dung hiển thị:** chuỗi hoặc JSON được in ra terminal để người dùng đọc hoặc script phân tích.
- **Trạng thái command:** cho biết lần gọi command thành công hay thất bại theo hợp đồng Spring Shell.
- **Mã thoát tiến trình:** giá trị tiến trình Java trả về cho terminal, scheduler hoặc CI khi ứng dụng kết thúc.

Trong Spring Shell 4.x, cần phân biệt rõ `ExitStatus` của command với mã thoát của JVM. Tài liệu Spring Shell nêu rõ `ExitStatusExceptionMapper` chỉ ánh xạ exception sang trạng thái command; cấu hình mapper này không tự cấu hình mã thoát tiến trình.

## 2. Bốn khái niệm cần tách biệt

| Khái niệm | Đại diện cho điều gì? | Ví dụ |
|---|---|---|
| Kết quả nghiệp vụ | Dữ liệu hoặc quyết định do service tạo ra | `Invoice`, `TransferReceipt`, `ImportSummary` |
| Output | Nội dung được ghi ra terminal hoặc stdout | `Đã tạo hóa đơn 42`, JSON, bảng kết quả |
| `ExitStatus` | Kết quả thực thi một command trong Spring Shell | `ExitStatus.OK`, `ExitStatus.USAGE_ERROR` |
| Process exit code | Mã tiến trình trả cho hệ điều hành khi kết thúc | `0`, `1`, `2`, `4` theo quy ước ứng dụng |

~~~mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Command nhận input]
    B --> C[Service xử lý nghiệp vụ]
    C --> D[Kết quả nghiệp vụ]
    D --> E[Command định dạng output]
    E --> F[Terminal / stdout]
    C --> G[Command trả ExitStatus]
    G --> H[Spring Shell xử lý trạng thái]
    H --> I[Runner / application lifecycle]
    I --> J[Process exit code khi tiến trình kết thúc]
~~~

Sơ đồ mô tả luồng khái niệm. Ở chế độ interactive, tiến trình thường tiếp tục chạy sau mỗi command, nên không có process exit code mới cho từng lần gọi. Ở chế độ non-interactive, runner thực thi command rồi kết thúc tiến trình; khi đó mã thoát của tiến trình mới được bên gọi bên ngoài quan sát.

## 3. Kết quả nghiệp vụ được tạo ở service

Service nên trả dữ liệu có ý nghĩa với nghiệp vụ, không nên tự quyết định cách trình bày trên terminal. Ví dụ service tạo hóa đơn có thể trả về một record:

~~~java
package com.example.billing;

import java.math.BigDecimal;

public record InvoiceReceipt(
        long invoiceId,
        BigDecimal total,
        String currency,
        String status) {
}
~~~

Service thực hiện nghiệp vụ và trả kết quả:

~~~java
package com.example.billing;

import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    public InvoiceReceipt create(CreateInvoiceRequest request) {
        // Kiểm tra nghiệp vụ, lưu hóa đơn và lấy ID được tạo.
        return new InvoiceReceipt(
                42L,
                request.total(),
                request.currency(),
                "CREATED");
    }
}
~~~

`CreateInvoiceRequest` là kiểu request thuộc ứng dụng ví dụ. Trong ứng dụng thực tế, service sẽ kiểm tra dữ liệu, lưu hóa đơn và trả lại thông tin thực tế từ hệ thống lưu trữ.

Command nhận kết quả đó rồi quyết định cách trình bày. Cùng một `InvoiceReceipt` có thể được hiển thị thành văn bản cho người vận hành hoặc JSON cho script. Việc thay đổi format không cần làm thay đổi nghiệp vụ tạo hóa đơn.

## 4. Output: nội dung được hiển thị cho người dùng

### Phương thức `@Command` trả về giá trị

Trong mô hình annotation của Spring Shell 4.x, nếu phương thức command trả về một giá trị, giá trị đó được in ra output của shell. Ví dụ:

~~~java
package com.example.billing;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class InvoiceCommands {

    private final InvoiceService invoiceService;

    public InvoiceCommands(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @Command(name = "invoice create", description = "Tạo hóa đơn")
    public String create(
            @Option(longName = "total", required = true) java.math.BigDecimal total,
            @Option(longName = "currency", defaultValue = "VND") String currency) {

        InvoiceReceipt receipt = invoiceService.create(
                new CreateInvoiceRequest(total, currency));

        return "Đã tạo hóa đơn " + receipt.invoiceId()
                + ", tổng tiền " + receipt.total() + " " + receipt.currency()
                + ", trạng thái " + receipt.status();
    }
}
~~~

Ở đây:

- `InvoiceReceipt` là kết quả nghiệp vụ.
- Chuỗi được trả về từ `create(...)` là nội dung hiển thị.
- Việc phương thức trả về `String` không có nghĩa `String` đó là mã trạng thái command.

Giữ thông báo ngắn gọn và có ý nghĩa. Nếu output cần được script đọc, hãy cung cấp format máy đọc riêng thay vì buộc script phân tích câu văn dành cho con người.

### Ghi output qua `CommandContext`

Nếu command cần in nhiều dòng hoặc kiểm soát nội dung output, khai báo phương thức `void` và dùng `PrintWriter` từ `CommandContext`:

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class SystemCommands {

    @Command(name = "system status", description = "Hiển thị trạng thái hệ thống")
    public void status(CommandContext context) {
        context.outputWriter().println("Service: billing");
        context.outputWriter().println("Status: UP");
        context.outputWriter().println("Version: 1.4.0");
        context.outputWriter().flush();
    }
}
~~~

Spring Shell khuyến nghị dùng `commandContext.outputWriter()` để ghi output của command. Cách này sử dụng writer mà shell cung cấp, phù hợp với terminal và giúp việc kiểm thử output dễ kiểm soát hơn. Không nên dùng `System.out.println()` tràn lan trong command vì output có thể đi thẳng vào system stream thay vì writer được shell quản lý.

## 5. Chọn format output cho người và cho máy

Một command có thể cung cấp option `--format` để chọn kiểu hiển thị:

~~~java
@Command(name = "invoice show", description = "Hiển thị hóa đơn")
public String show(
        @Option(longName = "id", required = true) long id,
        @Option(longName = "format", defaultValue = "plain") String format) {

    InvoiceReceipt invoice = invoiceService.findReceipt(id);

    return switch (format.toLowerCase(java.util.Locale.ROOT)) {
        case "plain" -> "Hóa đơn " + invoice.invoiceId()
                + " | " + invoice.total() + " " + invoice.currency()
                + " | " + invoice.status();
        case "json" -> objectMapper.writeValueAsString(invoice);
        default -> throw new IllegalArgumentException(
                "--format chỉ nhận plain hoặc json");
    };
}
~~~

Ví dụ trên giả định command có `invoiceService` và `objectMapper` được inject qua constructor; `findReceipt(...)` là phương thức service thuộc ứng dụng mẫu.

| Format | Người nhận | Đặc điểm |
|---|---|---|
| `plain` | Người vận hành | Nhãn rõ ràng, dễ đọc trên terminal. |
| `json` | Script hoặc công cụ tích hợp | Cấu trúc dữ liệu có thể parse bằng JSON parser. |

Khi cung cấp JSON cho script, hãy coi tên field, kiểu dữ liệu, đơn vị và ý nghĩa của `null` là một hợp đồng. Không trộn banner, log hoặc thông báo tiến trình vào cùng stdout đang chứa JSON. Dùng logging cho chẩn đoán và giữ payload output đúng format đã công bố.

## 6. `ExitStatus`: trạng thái của command trong Spring Shell 4.x

Trong Spring Shell 4.x, `Command` là functional interface có phương thức:

~~~java
ExitStatus execute(CommandContext commandContext) throws Exception;
~~~

`ExitStatus` là record gồm hai thành phần:

- `code`: mã trạng thái của lần thực thi command.
- `description`: mô tả trạng thái.

Spring Shell cung cấp các trạng thái dựng sẵn:

| Hằng số | Ý nghĩa |
|---|---|
| `ExitStatus.OK` | Command hoàn tất thành công. |
| `ExitStatus.USAGE_ERROR` | Đầu vào hoặc cách sử dụng command không hợp lệ. |
| `ExitStatus.EXECUTION_ERROR` | Command gặp lỗi khi thực thi. |
| `ExitStatus.AVAILABILITY_ERROR` | Command không khả dụng tại thời điểm được gọi. |

Không nên tự đoán giá trị số của các hằng số. Khi cần mã riêng theo nghiệp vụ, có thể tạo `new ExitStatus(code, description)` và công bố quy ước đó trong tài liệu CLI.

### Trả ExitStatus bằng AbstractCommand

Với command được tạo theo API programmatic, `AbstractCommand` giúp triển khai trạng thái một cách tường minh:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.ExitStatus;

@Bean
Command invoiceCheckCommand(InvoiceService invoiceService) {
    AbstractCommand command = new AbstractCommand(
            "invoice check",
            "Kiểm tra trạng thái hóa đơn",
            "Billing") {

        @Override
        public ExitStatus doExecute(CommandContext context) {
            long id = Long.parseLong(
                    context.getOptionByName("id").value());
            boolean exists = invoiceService.exists(id);

            println(exists ? "Hóa đơn tồn tại" : "Không tìm thấy hóa đơn", context);

            return exists
                    ? ExitStatus.OK
                    : new ExitStatus(4, "Invoice not found");
        }
    };

    command.setOptions(List.of(
            CommandOption.with()
                    .longName("id")
                    .description("Mã hóa đơn")
                    .type(Long.class)
                    .required(true)
                    .build()));

    return command;
}
~~~

`InvoiceService.exists(...)` là phương thức service thuộc ứng dụng ví dụ. Option `id` được khai báo trong metadata để parser biết kiểu và yêu cầu đầu vào. Điểm chính là `doExecute(...)` trả `ExitStatus` riêng, độc lập với thông báo đã in.

Một command có thể in thông báo dễ hiểu nhưng vẫn trả trạng thái thất bại. Ví dụ “Không tìm thấy hóa đơn” là output; mã `4` trong ví dụ là trạng thái command. Script không nên phân tích câu chữ để đoán thành công hay thất bại.

## 7. Ánh xạ exception thành ExitStatus

Trong nhiều command, lỗi được biểu diễn bằng exception có kiểu riêng. `ExitStatusExceptionMapper` chuyển exception phát sinh trong quá trình thực thi thành `ExitStatus` và mô tả phù hợp.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class BillingCommandConfiguration {

    @Bean
    ExitStatusExceptionMapper billingExitStatusMapper() {
        return exception -> {
            if (exception instanceof InvoiceNotFoundException) {
                return new ExitStatus(4, "Invoice not found");
            }
            if (exception instanceof IllegalArgumentException) {
                return ExitStatus.USAGE_ERROR;
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Gắn mapper vào command annotation bằng tên bean:

~~~java
@Command(
        name = "invoice show",
        description = "Hiển thị hóa đơn",
        exitStatusExceptionMapper = "billingExitStatusMapper")
public String show(@Option(longName = "id", required = true) long id) {
    InvoiceReceipt invoice = invoiceService.findReceipt(id);
    return "Hóa đơn " + invoice.invoiceId();
}
~~~

Với command tạo bằng `Command.Builder`, có thể cấu hình mapper qua `exitStatusExceptionMapper(...)`. Khi dùng annotation, mapper phải là Spring bean và tên được tham chiếu trong `@Command`.

Mapper giúp chuẩn hóa trạng thái command và mô tả lỗi. Nó không thay thế việc ghi log, không tự quyết định format output và cũng không tự thiết lập mã thoát của JVM.

## 8. Mã thoát tiến trình là kết quả của ứng dụng khi kết thúc

Process exit code là số nguyên mà hệ điều hành nhận được khi tiến trình kết thúc. Đây là tín hiệu mà Bash, PowerShell, cron, CI/CD hoặc một chương trình gọi CLI dùng để quyết định bước tiếp theo.

Quy ước phổ biến:

| Mã ví dụ | Ý nghĩa ứng dụng | Bên gọi thường làm gì? |
|---:|---|---|
| `0` | Thành công | Tiếp tục pipeline. |
| `1` | Lỗi thực thi không dự kiến | Dừng và ghi log. |
| `2` | Cú pháp hoặc dữ liệu đầu vào không hợp lệ | Báo lỗi tham số. |
| `4` | Không tìm thấy tài nguyên | Xử lý nhánh nghiệp vụ tương ứng. |
| `10` | Xung đột trạng thái nghiệp vụ | Yêu cầu người vận hành kiểm tra hoặc thử lại. |

Đây là bảng quy ước minh họa của một ứng dụng. Không phải tất cả các mã trên đều là mã cố định của Spring Shell. Hãy công bố bảng mã thực tế và giữ ý nghĩa của mỗi mã ổn định qua các phiên bản.

### Interactive mode và non-interactive mode

Trong interactive mode, shell vẫn tiếp tục chờ lệnh sau khi một command hoàn tất. `ExitStatus` mô tả lần gọi command hiện tại; process exit code chỉ xuất hiện khi toàn bộ ứng dụng kết thúc.

Trong non-interactive mode, Spring Shell thực thi command được truyền qua đối số tiến trình rồi kết thúc. Đây là chế độ phù hợp với script và CI. Cấu hình:

~~~properties
spring.shell.interactive.enabled=false
~~~

Sau đó có thể gọi:

~~~bash
java -jar target/billing-cli.jar invoice show --id=42
~~~

Khi kiểm tra trong shell hệ điều hành, dùng `$?` trên Bash hoặc `$LASTEXITCODE` trên PowerShell để đọc mã tiến trình vừa kết thúc. Không dùng nội dung output để thay thế kiểm tra mã thoát.

## 9. ExitStatus không tự động bằng JVM process exit code

Đây là điểm dễ nhầm nhất khi xây CLI cho tự động hóa.

- `ExitStatus` là trạng thái của command trong Spring Shell.
- `ExitStatusExceptionMapper` ánh xạ exception sang `ExitStatus`.
- Process exit code là kết quả ở ranh giới tiến trình, do runner và cơ chế kết thúc ứng dụng quyết định.

Tài liệu Spring Shell 4.0.4 nói rõ việc cấu hình `ExitStatusExceptionMapper` không tự cấu hình mã thoát JVM. Ở tầng Spring Boot, ứng dụng có các cơ chế như `ExitCodeGenerator` và `ExitCodeExceptionMapper`; khi tự quản lý điểm kết thúc trong `main`, Spring Boot cũng cung cấp mẫu `System.exit(SpringApplication.exit(...))` để trả mã ứng dụng về hệ điều hành.

Vì cách runner non-interactive kết thúc ứng dụng phụ thuộc vào phiên bản Spring Shell và cách ứng dụng được khởi chạy, hãy kiểm thử process exit code bằng cách chạy JAR như một tiến trình con. Không kết luận mã tiến trình chỉ từ unit test của `ExitStatusExceptionMapper`.

### Lưu ý phiên bản runner

Spring Shell 4.0.2 đã sửa lỗi khiến non-interactive runner luôn trả mã `0` trong một số tình huống thực thi lỗi. Tuy nhiên, tại thời điểm biên soạn bài này, issue #1391 vẫn được báo cáo mở cho Spring Shell 4.0.4: lỗi parse command trong `NonInteractiveShellRunner` có thể được ghi log rồi bỏ qua, khiến tiến trình trả mã `0`. Vì vậy, cần kiểm tra cả command hợp lệ, lỗi nghiệp vụ và lỗi parse trên đúng bản Spring Shell mà ứng dụng phân phối.

## 10. Dùng mã thoát trong script

### Bash

~~~bash
java -jar target/billing-cli.jar invoice show --id=42 --format=json
status=$?

if [ "$status" -eq 0 ]; then
  echo "Invoice query succeeded"
else
  echo "Invoice query failed with code $status" >&2
  exit "$status"
fi
~~~

### PowerShell

~~~powershell
java -jar .\target\billing-cli.jar invoice show --id=42 --format=json
$status = $LASTEXITCODE

if ($status -eq 0) {
    Write-Output "Invoice query succeeded"
} else {
    Write-Error "Invoice query failed with code $status"
    exit $status
}
~~~

Trong cả hai ví dụ, script đọc mã của tiến trình Java ngay sau khi tiến trình kết thúc. Nếu cần giữ output JSON sạch, không ghi thêm thông báo tiến trình vào cùng stdout trước khi script parse JSON; có thể ghi thông báo chẩn đoán ra stderr.

## 11. Kiểm thử riêng từng loại kết quả

Một bộ kiểm thử command nên xác nhận từng lớp độc lập:

1. **Kết quả nghiệp vụ:** service trả đúng đối tượng hoặc exception theo dữ liệu đầu vào.
2. **Output:** command in đúng thông tin, format và schema đã công bố.
3. **ExitStatus:** command trả `ExitStatus.OK` khi thành công và trạng thái phù hợp khi thất bại.
4. **Process exit code:** ứng dụng non-interactive trả mã mà script/CI mong đợi khi JAR kết thúc.

### Kiểm thử output và command

Spring Shell cung cấp `@ShellTest`, `ShellTestClient` và `ShellAssertions` để gửi command và kiểm tra nội dung terminal. Có thể dùng chúng để kiểm tra output của `invoice show`, thông báo lỗi và việc command không gọi service khi đầu vào không hợp lệ.

### Kiểm thử process exit code

Process exit code cần được kiểm thử ở cấp tiến trình. Tạo tiến trình con chạy JAR với các trường hợp:

| Ca kiểm thử | Lệnh | Điều cần xác nhận |
|---|---|---|
| Thành công | `invoice show --id=42` với hóa đơn tồn tại | Output đúng và process code bằng `0`. |
| Lỗi nghiệp vụ | ID không tồn tại | Thông báo đúng và process code khác `0` theo hợp đồng ứng dụng. |
| Sai cú pháp | Thiếu option hoặc sai kiểu dữ liệu | Runner không được âm thầm coi là thành công. |
| Command không tồn tại | Gõ sai tên command | Process code phản ánh lỗi gọi command. |
| Output JSON | `--format=json` | stdout parse được và mã thoát vẫn chính xác. |

Với kiểm thử tiến trình, đọc `Process.exitValue()` sau khi `waitFor()` hoàn tất. Cũng nên thu stdout và stderr riêng để xác nhận output máy đọc không bị trộn với log.

## 12. Quy tắc thiết kế kết quả cho CLI

- Để service trả kết quả nghiệp vụ có kiểu rõ ràng.
- Để command quyết định cách trình bày kết quả cho người dùng.
- Dùng `CommandContext.outputWriter()` khi cần chủ động ghi output.
- Dùng `ExitStatus` để biểu diễn trạng thái thực thi của command.
- Dùng `ExitStatusExceptionMapper` để ánh xạ exception dự kiến thành trạng thái và mô tả nhất quán.
- Xác định riêng chính sách process exit code ở ranh giới ứng dụng.
- Giữ stdout dành cho payload mà script cần parse; dùng logging/stderr cho chẩn đoán.
- Kiểm thử cả command-level status và process-level exit code.
- Duy trì bảng mã thoát ổn định và mô tả cách xử lý cho từng mã.

## Kết luận

Kết quả nghiệp vụ, output, `ExitStatus` và process exit code phục vụ bốn mục đích khác nhau. Service tạo dữ liệu nghiệp vụ; command định dạng và ghi nội dung; Spring Shell dùng `ExitStatus` để biểu diễn kết quả thực thi; hệ điều hành nhận process exit code khi ứng dụng kết thúc. `ExitStatusExceptionMapper` giúp chuẩn hóa lỗi của command nhưng không tự cấu hình mã thoát JVM. Khi xây CLI cho script hoặc CI, hãy thiết kế từng lớp rõ ràng và kiểm thử tiến trình non-interactive như một ứng dụng thực tế.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.4 – Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell 4.0.4 – Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell 4.0.4 – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.4 API – Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [Spring Shell 4.0.4 API – ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [Spring Shell 4.0.4 API – ExitStatusExceptionMapper](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Shell 4.0.4 API – CommandExecutionException](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html)
- [Spring Shell 4.x – Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell issue #1391 – NonInteractiveShellRunner wrong exit value on parse errors](https://github.com/spring-projects/spring-shell/issues/1391)
- [Spring Boot – Application Exit and ExitCodeGenerator](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
