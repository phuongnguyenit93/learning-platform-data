# Phạm vi xử lý lỗi chung với xử lý riêng cho một command

Khi một command Spring Shell phát sinh exception, ứng dụng cần quyết định cách chuyển lỗi thành thông báo dễ hiểu và trạng thái kết thúc phù hợp. Có lỗi xuất hiện ở nhiều command, chẳng hạn lỗi kết nối dịch vụ hoặc lỗi xác thực; cũng có lỗi chỉ có ý nghĩa với một thao tác, chẳng hạn không tìm thấy báo cáo cần xuất. Đặt handler đúng phạm vi giúp tái sử dụng quy tắc chung mà vẫn giữ được thông tin riêng của từng command.

Spring Shell có cơ chế xử lý exception ở phạm vi toàn shell và phạm vi command. API cụ thể thay đổi giữa 3.x và 4.x: dòng 3.x dùng **CommandExceptionResolver** và **CommandHandlingResult**; dòng 4.x dùng **ExitStatusExceptionMapper** và **ExitStatus**. Cần xác định phiên bản trước khi áp dụng ví dụ.

## 1. Chọn phạm vi theo nơi cần áp dụng quy tắc

Một handler chung phù hợp với quy tắc có ý nghĩa trên toàn ứng dụng:

- Dịch exception hạ tầng thành thông báo thống nhất.
- Che chi tiết nội bộ và trả mã lỗi mặc định.
- Ghi log hoặc gắn mã tương quan cho lỗi chưa được xử lý.
- Áp dụng quy ước exit status nhất quán cho nhiều command.

Handler riêng phù hợp khi một command cần diễn giải exception theo ngữ cảnh:

- **report export** biến **ReportNotFoundException** thành “Không tìm thấy báo cáo để xuất”.
- **user delete** biến **UserInUseException** thành thông báo rằng tài khoản vẫn còn tài nguyên phụ thuộc.
- **backup restore** giải thích lỗi phiên bản snapshot hoặc lỗi checksum theo quy trình khôi phục.

| Tiêu chí | Handler chung | Handler riêng command |
| --- | --- | --- |
| Phạm vi | Nhiều hoặc tất cả command trong shell | Một command hoặc một nhóm command liên quan |
| Mục tiêu | Quy tắc lỗi thống nhất, fallback | Thông báo và mã lỗi sát nghiệp vụ của command |
| Ví dụ | Lỗi dịch vụ ngoài, lỗi xác thực chung, lỗi không dự kiến | Không tìm thấy báo cáo, tài khoản đang được tham chiếu |
| Rủi ro nếu dùng sai | Có thể che mất ngữ cảnh cụ thể | Lặp code và tạo cách xử lý không nhất quán |
| Thứ tự áp dụng | Thường là fallback sau quy tắc hẹp hơn | Có thể được ưu tiên trước handler chung |

Không nên đưa mọi exception vào một handler chung rồi trả cùng một thông báo. Khi đó người dùng không biết cần sửa đầu vào, kiểm tra quyền, thử lại hay liên hệ quản trị viên. Cũng không nên sao chép cùng một logic hạ tầng vào từng command.

## 2. Phân loại exception trước khi viết handler

Hãy xác định exception biểu thị loại vấn đề nào:

| Nhóm | Ví dụ | Cách xử lý thường phù hợp |
| --- | --- | --- |
| Cú pháp và chuyển đổi đầu vào | Thiếu option, số không chuyển được, giá trị enum không hợp lệ | Để parser/resolver mặc định báo lỗi sử dụng command; giữ mã lỗi usage |
| Validation dữ liệu | Giá trị ngoài miền hợp lệ hoặc vi phạm constraint | Nêu trường và điều kiện hợp lệ; yêu cầu người dùng sửa đầu vào |
| Quy tắc nghiệp vụ | Tài khoản không tồn tại, trạng thái không cho phép xóa | Thông báo nghiệp vụ cụ thể; không retry mù quáng |
| Hạ tầng có thể tạm thời | Timeout, dịch vụ từ xa tạm ngừng, lỗi kết nối | Thông báo dịch vụ và hướng thử lại; chỉ retry khi thao tác an toàn |
| Quyền truy cập | Không có quyền đọc hoặc cập nhật tài nguyên | Thông báo thao tác bị từ chối; không tiết lộ dữ liệu nhạy cảm |
| Lỗi lập trình hoặc lỗi không dự kiến | Null dereference, invariant bị phá vỡ | Mã lỗi chung, log stack trace phía ứng dụng và mã tương quan |

Nên dùng exception có kiểu riêng cho lỗi nghiệp vụ thay vì dựa vào việc so khớp chuỗi message. Kiểu exception ổn định hơn khi nội dung thông báo được dịch hoặc chỉnh sửa.

Ví dụ các exception:

```java
public class ReportNotFoundException extends RuntimeException {
    public ReportNotFoundException(String reportId) {
        super("Report not found: " + reportId);
    }
}

public class RemoteServiceUnavailableException extends RuntimeException {
    public RemoteServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Thông điệp của exception có thể chứa thông tin kỹ thuật để log, vì vậy handler cần tạo thông báo dành cho người dùng từ loại exception và dữ liệu an toàn. Tránh đưa nguyên văn thông tin nhạy cảm, token, câu truy vấn hoặc đường dẫn nội bộ ra terminal.

## 3. Cơ chế xử lý chung trong Spring Shell 3.x

Trong mô hình command registration của Spring Shell 3.x, **CommandExceptionResolver** là một functional interface nhận **Exception** và trả về **CommandHandlingResult**. Kết quả có thể chứa thông báo cùng exit code. Resolver có thể đăng ký thành Spring bean để áp dụng chung hoặc gắn vào một **CommandRegistration** cụ thể.

Resolver chung có thể được viết như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

@Configuration
public class ShellErrorConfiguration {

    @Bean
    @Order(100)
    CommandExceptionResolver commonExceptionResolver() {
        return exception -> {
            if (exception instanceof RemoteServiceUnavailableException) {
                return CommandHandlingResult.of(
                        "Dịch vụ hiện không khả dụng. Hãy thử lại sau.",
                        4
                );
            }
            return null;
        };
    }
}
```

Phương thức **resolve** trả về **null** khi resolver không xử lý exception đó. Spring Shell tiếp tục chuỗi resolver và cho phép handler khác hoặc xử lý mặc định quyết định kết quả. Khi đã nhận diện exception, resolver trả **CommandHandlingResult** để cung cấp thông báo và mã kết thúc.

Các resolver mặc định của Spring Shell xử lý những lỗi phổ biến, bao gồm lỗi phân tích command. Có thể dùng **@Order** hoặc **Ordered** để kiểm soát thứ tự tương đối của resolver tùy chỉnh với các resolver khác. Không nên tạo resolver chung bắt mọi **Exception** và luôn trả một kết quả; làm vậy sẽ ngăn các resolver chuyên biệt và xử lý mặc định có cơ hội chạy.

## 4. Gắn resolver riêng vào một command trong Spring Shell 3.x

Nếu chỉ một command cần cách xử lý đặc thù, có thể gắn resolver trực tiếp vào **CommandRegistration**:

```java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.CommandRegistration;

CommandExceptionResolver exportResolver = exception -> {
    if (exception instanceof ReportNotFoundException) {
        return CommandHandlingResult.of(
                "Không tìm thấy báo cáo. Kiểm tra mã báo cáo rồi thử lại.",
                3
        );
    }
    return null;
};

CommandRegistration exportCommand = CommandRegistration.builder()
        .command("report export")
        .withErrorHandling()
            .resolver(exportResolver)
            .and()
        .build();
```

Đoạn code tập trung minh họa phần cấu hình error handling; khi hoàn thiện command, bổ sung các option, mô tả và executor theo nghiệp vụ của ứng dụng.

Trong chuỗi xử lý của Spring Shell 3.x, resolver gắn với command được xét trước resolver toàn cục. Vì vậy, command có thể xử lý **ReportNotFoundException** bằng thông báo phù hợp; nếu exception không thuộc phạm vi đó, resolver trả **null** để quy tắc chung tiếp tục xử lý.

Mô hình này hữu ích khi một exception chỉ có ý nghĩa với một command, hoặc khi command cần mã lỗi riêng cho hệ thống gọi tự động. Không nên gắn cùng một resolver vào từng command nếu nó chỉ chứa quy tắc hạ tầng chung; hãy đăng ký thành bean toàn shell.

## 5. Dùng @ExceptionResolver trong mô hình annotation 3.x

Với mô hình legacy dùng **@ShellComponent** và **@ShellMethod**, có thể khai báo phương thức **@ExceptionResolver** trong component chứa command. Phương thức này xử lý exception phát sinh từ các command method thuộc component đó:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

@ShellComponent
public class ReportCommands {

    @ShellMethod(key = "report export", value = "Xuất một báo cáo.")
    public String export(String reportId) {
        return reportService.export(reportId);
    }

    @ExceptionResolver
    CommandHandlingResult handleMissingReport(ReportNotFoundException ex) {
        return CommandHandlingResult.of(
                "Không tìm thấy báo cáo cần xuất.",
                3
        );
    }
}
```

**@ExceptionResolver** có thể giới hạn loại exception bằng giá trị annotation hoặc suy ra từ kiểu tham số của method. Nên khai báo kiểu exception cụ thể trong tham số để Spring Shell chọn đúng handler. Khi có nhiều handler khớp, exception gần nhất với loại được ném thường được ưu tiên; exception ở cause lồng bên trong cũng có thể được xét.

Phạm vi của phương thức annotation này là component command tương ứng. Nếu muốn xử lý exception dùng chung cho nhiều component, hãy dùng cơ chế resolver bean toàn shell của 3.x thay vì sao chép một method **@ExceptionResolver** vào từng component.

Phương thức resolver có thể trả về:

- **CommandHandlingResult**: kiểm soát cả thông báo và exit code.
- **String**: ghi nội dung ra shell; nếu không đặt mã khác, exit code theo tài liệu là **1**.
- **void**: xem exception đã được xử lý; nếu cần ghi nội dung, có thể nhận **Terminal** và dùng **@ExitCode** để đặt mã.

Không nên trả về **void** nếu mục tiêu là để exception tiếp tục đi tới handler khác. Một phương thức resolver đã nhận xử lý exception sẽ kết thúc nhánh xử lý tương ứng.

## 6. Cơ chế xử lý theo command trong Spring Shell 4.x

Spring Shell 4.x dùng **ExitStatusExceptionMapper** để chuyển exception thành **ExitStatus**. Mapper là một hàm nhận **Exception** và trả về mã cùng mô tả trạng thái của command.

```java
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;
import org.springframework.stereotype.Component;

@Component("reportExportExceptionMapper")
public class ReportExportExceptionMapper implements ExitStatusExceptionMapper {

    @Override
    public ExitStatus apply(Exception exception) {
        if (exception instanceof ReportNotFoundException) {
            return new ExitStatus(
                    3,
                    "Không tìm thấy báo cáo cần xuất."
            );
        }
        return new ExitStatus(
                1,
                "Không thể xuất báo cáo do lỗi không dự kiến."
        );
    }
}
```

Gắn mapper với command bằng tên bean trong **@Command**:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    private final ReportService reportService;

    public ReportCommands(ReportService reportService) {
        this.reportService = reportService;
    }

    @Command(
        name = "report export",
        description = "Xuất một báo cáo.",
        exitStatusExceptionMapper = "reportExportExceptionMapper"
    )
    public String export(
            @Option(longName = "id", required = true) String reportId) {
        return reportService.export(reportId);
    }
}
```

**ExitStatusExceptionMapper** phải là Spring bean để được tham chiếu trong annotation. Với command đăng ký bằng Java builder, có thể gắn trực tiếp mapper qua **Command.Builder.exitStatusExceptionMapper(...)**.

### Dùng một mapper chung cho nhiều command

Nếu nhiều command cần cùng một chính sách, có thể tạo một mapper bean dùng chung rồi tham chiếu tên bean đó trong từng **@Command**. Mỗi command vẫn khai báo rõ mapper đang sử dụng:

```java
@Command(
    name = "user list",
    exitStatusExceptionMapper = "commonExceptionMapper"
)
public String list() {
    // ...
}

@Command(
    name = "project list",
    exitStatusExceptionMapper = "commonExceptionMapper"
)
public String listProjects() {
    // ...
}
```

Đây là cách tái sử dụng một chính sách chung trong API 4.x. Tài liệu 4.x mô tả mapper được gắn vào từng command bằng thuộc tính **exitStatusExceptionMapper** hoặc builder; không nên giả định bean mapper tự động trở thành một chuỗi fallback toàn cục giống **CommandExceptionResolver** của 3.x.

Nếu một command cần quy tắc riêng, tạo mapper riêng và gắn tên bean riêng vào command đó. Giữ mapper dùng chung cho các lỗi phổ quát như lỗi kết nối hoặc lỗi không dự kiến.

## 7. So sánh phạm vi và API giữa 3.x với 4.x

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Kiểu xử lý exception | **CommandExceptionResolver** | **ExitStatusExceptionMapper** |
| Kết quả | **CommandHandlingResult** chứa message/exit code | **ExitStatus** chứa code/description |
| Xử lý chung | Đăng ký resolver bean trong application context | Tạo mapper bean dùng chung và tham chiếu trong từng command |
| Xử lý riêng | Resolver trên **CommandRegistration**; hoặc **@ExceptionResolver** trong **@ShellComponent** | **@Command(exitStatusExceptionMapper = "beanName")** hoặc **Command.Builder** |
| Thứ tự | Resolver gắn command được xét trước resolver global; resolver chain có precedence | Mapper được chọn theo command; không giả định có global resolver chain giống 3.x |
| Cách bỏ qua exception | Resolver trả **null** để nhường xử lý tiếp | Mapper trả **ExitStatus**; thiết kế mapper để phân loại các exception mà command cần xử lý |

Khi nâng cấp, không thể chỉ đổi tên **CommandExceptionResolver** thành **ExitStatusExceptionMapper**. Cần chuyển logic tạo **CommandHandlingResult** sang **ExitStatus**, đồng thời thay cách đăng ký global/per-command theo mô hình command của 4.x.

## 8. Phân biệt command exit status và mã thoát của tiến trình

Mã kết quả của command và mã thoát của JVM là hai khái niệm cần kiểm tra riêng.

Trong Spring Shell 3.x, **CommandHandlingResult.exitCode()** chỉ có ý nghĩa khi shell chạy ở chế độ non-interactive. Mặc định được tài liệu 3.4 mô tả:

| Tình huống | Exit code mặc định |
| --- | ---: |
| Lỗi phân tích option/command | **2** |
| Lỗi chung | **1** |
| Thành công | **0** |

Trong phiên interactive, shell tiếp tục nhận lệnh sau khi hiển thị lỗi; không nên xem exit code của một command là mã thoát tiến trình tại thời điểm đó.

Trong Spring Shell 4.x, **ExitStatus** biểu diễn trạng thái của command. Tài liệu nêu rõ command status tách biệt với JVM process exit code; chỉ cấu hình **ExitStatusExceptionMapper** không tự cấu hình mã thoát của tiến trình. Nếu CI/CD cần mã thoát của process, hãy cấu hình và kiểm thử riêng cơ chế kết thúc ứng dụng/runner của Spring Boot.

Vì vậy, khi thiết kế CLI cho automation:

- Chọn một quy ước mã lỗi ổn định cho command.
- Phân biệt lỗi sử dụng command với lỗi nghiệp vụ và lỗi hệ thống.
- Kiểm tra mã thoát thực tế của process bằng shell hoặc CI runner ở phiên bản triển khai.
- Không giả định rằng một mapper trả code **3** thì mọi cách khởi chạy đều tự trả process exit code **3**.

## 9. Thiết kế mã lỗi có thể dùng trong automation

Mã lỗi nên ổn định theo loại vấn đề, không phụ thuộc nội dung message. Một quy ước đơn giản:

| Mã | Ý nghĩa gợi ý | Hành động của hệ thống gọi |
| ---: | --- | --- |
| **0** | Thành công | Tiếp tục bước kế tiếp |
| **1** | Lỗi không dự kiến | Dừng workflow và kiểm tra log |
| **2** | Cú pháp hoặc cách sử dụng không hợp lệ | Sửa command/option |
| **3** | Tài nguyên nghiệp vụ không tồn tại hoặc trạng thái không phù hợp | Kiểm tra ID hoặc trạng thái dữ liệu |
| **4** | Dịch vụ phụ thuộc tạm thời không khả dụng | Có thể retry theo chính sách |
| **5** | Không đủ quyền thực hiện | Kiểm tra danh tính và quyền truy cập |

Đây là quy ước của ứng dụng, không phải toàn bộ mã mặc định bắt buộc của Spring Shell. Hãy ghi lại mã trong tài liệu CLI và giữ nguyên ý nghĩa qua các phiên bản để script không phải thay đổi theo nội dung thông báo.

Chỉ retry những lỗi được xác định là tạm thời và thao tác có tính idempotent hoặc có cơ chế chống thực thi trùng. Không retry lỗi cú pháp, không tìm thấy tài nguyên hoặc không đủ quyền một cách tự động.

## 10. Quy tắc thiết kế handler chung và handler riêng

Một cách tổ chức dễ bảo trì:

1. Command/service ném exception có kiểu rõ ràng.
2. Handler riêng chuyển exception đặc thù thành thông báo nghiệp vụ ngắn.
3. Handler chung chuyển lỗi hạ tầng đã biết thành thông báo thống nhất.
4. Exception chưa nhận diện đi qua xử lý mặc định hoặc thành lỗi chung có mã tương quan.
5. Log nội bộ giữ stack trace và thông tin chẩn đoán đã lọc.

Handler nên làm nhiệm vụ chuyển đổi lỗi thành kết quả trình bày. Tránh đặt logic nghiệp vụ như xóa dữ liệu, retry dài hoặc cập nhật trạng thái domain trong exception resolver. Khi cần khôi phục, hãy đặt logic đó trong service/orchestrator trước khi exception đi đến lớp hiển thị.

Không nên:

- Bắt **Exception** ở từng command rồi chỉ in **getMessage()** và trả thành công.
- Trả exit code **0** cho một lỗi chỉ vì đã hiển thị thông báo.
- Nuốt exception khiến CI tưởng rằng workflow đã thành công.
- Đưa stack trace, SQL, token hoặc đường dẫn bí mật ra terminal.
- Dùng cùng một mã lỗi cho tất cả trường hợp nếu automation cần phân biệt cách xử lý.
- Để handler chung bắt trước mọi exception và ngăn handler riêng chạy.

## 11. Kiểm thử thứ tự và phạm vi handler

Hãy kiểm thử không chỉ nội dung thông báo mà cả resolver nào đã xử lý exception và mã kết quả được tạo ra.

**Kiểm thử resolver chung:**

- Exception hạ tầng đã biết tạo đúng thông báo và mã lỗi.
- Exception không thuộc phạm vi trả **null** trong mô hình resolver chain 3.x.
- Exception không dự kiến đi tới fallback phù hợp.
- Resolver không làm lộ message hoặc dữ liệu nhạy cảm.

**Kiểm thử resolver riêng command:**

- **report export** xử lý **ReportNotFoundException** bằng thông báo riêng.
- Exception không thuộc command đó được nhường cho resolver chung trong 3.x.
- Command khác không bị áp dụng nhầm thông báo đặc thù của **report export**.
- Với 4.x, command tham chiếu đúng mapper bean và trả **ExitStatus** như mong đợi.

**Kiểm thử mã thoát:**

- Thành công trả mã **0**.
- Lỗi cú pháp và lỗi nghiệp vụ có mã khác nhau theo quy ước.
- Chạy non-interactive và xác nhận process exit code thực tế.
- Chạy interactive và xác nhận shell vẫn tiếp tục nhận command sau lỗi.
- Với 4.x, xác nhận riêng command status và process exit code.

Ví dụ bảng ca kiểm thử:

| Command | Exception | Handler mong đợi | Kết quả |
| --- | --- | --- | --- |
| **report export** | **ReportNotFoundException** | Handler riêng của export | Thông báo báo cáo không tồn tại, mã **3** |
| **report export** | **RemoteServiceUnavailableException** | Handler chung | Thông báo dịch vụ tạm thời không khả dụng, mã **4** |
| **user list** | **RemoteServiceUnavailableException** | Handler chung | Cùng thông báo và mã **4** |
| **user list** | Exception không dự kiến | Fallback chung/default | Thông báo lỗi chung, mã **1** |
| **report export** | Sai option hoặc thiếu option | Parser/default resolver | Thông báo cách sử dụng, mã usage |

## 12. Checklist triển khai

- Xác định phiên bản Spring Shell trước khi chọn API.
- Phân loại exception theo cú pháp, validation, nghiệp vụ, hạ tầng và lỗi không dự kiến.
- Dùng handler chung cho chính sách áp dụng rộng.
- Dùng handler riêng khi command cần thông báo hoặc mã lỗi đặc thù.
- Với 3.x, đăng ký **CommandExceptionResolver** bean hoặc resolver trên **CommandRegistration**.
- Với legacy annotation 3.x, giới hạn **@ExceptionResolver** trong component phù hợp.
- Với 4.x, gắn **ExitStatusExceptionMapper** bean vào từng command qua annotation hoặc builder.
- Trong resolver chain 3.x, trả **null** khi không xử lý để nhường handler tiếp theo.
- Giữ nguyên exception chưa biết để fallback ghi log và trả lỗi chung.
- Không để handler nuốt lỗi rồi báo thành công.
- Tách command exit status khỏi process exit code, đặc biệt trong 4.x.
- Kiểm thử thứ tự resolver, nội dung thông báo, mã lỗi và hành vi interactive/non-interactive.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/index.html)
- [Spring Shell 3.4 — Exception Resolving](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/resolving.html)
- [Spring Shell 3.4 — ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/annotation.html)
- [Spring Shell 3.4 — Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html)
- [Spring Shell 4.0.4 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.3 — ExitStatusExceptionMapper API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)
- [Spring Shell 4.0.3 — Command API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
