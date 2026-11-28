# Ngoại lệ được báo về terminal và cơ chế xử lý mặc định

Một command có thể gặp lỗi khi đọc file, truy vấn dữ liệu, gọi dịch vụ bên ngoài hoặc xử lý đầu vào. Nếu command ném exception và không tự xử lý, Spring Shell tiếp nhận lỗi và hiển thị thông báo ngắn trên terminal. Cách xử lý mặc định giúp người dùng nhận biết command thất bại mà không bị tràn màn hình bởi toàn bộ stack trace.

Trong Spring Shell 3.3, exception xảy ra bên trong command được shell bắt lại và hiển thị thành thông báo một dòng. Shell lưu exception gần nhất; người dùng có thể gọi built-in command `stacktrace` để xem chi tiết nguyên nhân và các cause lồng nhau. Nếu ứng dụng cần thông báo thân thiện hơn, có thể thêm phương thức `@ExceptionResolver` hoặc đăng ký `CommandExceptionResolver`.

Exception handling và exit code có liên hệ nhưng không giống nhau. Thông báo được hiển thị trong terminal giúp người dùng hiểu lỗi; exit code giúp tiến trình gọi bên ngoài biết command thành công hay thất bại. Exit code có ý nghĩa chủ yếu khi Spring Shell chạy ở chế độ non-interactive.

Sau bài này, bạn có thể:

- Hiểu cách Spring Shell xử lý exception chưa được command bắt.
- Phân biệt thông báo lỗi một dòng với stack trace đầy đủ.
- Dùng built-in command `stacktrace` để chẩn đoán lỗi gần nhất.
- Viết `@ExceptionResolver` cho exception của command legacy.
- Đăng ký `CommandExceptionResolver` dùng chung hoặc theo từng command.
- Hiểu thứ tự xử lý của resolver và cách chuyển tiếp exception chưa được xử lý.
- Phân biệt lỗi phân tích option với lỗi phát sinh trong code command.
- Hiểu mã thoát mặc định và chọn exit code phù hợp cho từng loại lỗi.

> Bài này sử dụng Spring Shell 3.3.x. Ví dụ command dùng mô hình legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption`; API resolver được nhập từ package tương ứng của Spring Shell 3.3.

## 1. Điều gì xảy ra khi command ném exception?

Giả sử command `customer show` truy vấn khách hàng theo ID. Nếu không tìm thấy bản ghi, service ném `CustomerNotFoundException`. Nếu command không bắt exception này, lỗi được chuyển lên cơ chế xử lý kết quả của Spring Shell.

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Spring Shell phân tích đầu vào]
    B --> C[Thực thi command method]
    C --> D{Command hoàn tất?}
    D -->|Có| E[Result handler hiển thị kết quả]
    D -->|Không, có exception| F[Exception resolver chain]
    F --> G{Có resolver xử lý?}
    G -->|Có| H[Trả message và/hoặc exit code]
    G -->|Không| I[Xử lý mặc định của shell]
    I --> J[Hiển thị thông báo lỗi ngắn]
    J --> K[Lưu exception gần nhất]
    K --> L[Người dùng gọi stacktrace để xem chi tiết]
~~~

Spring Shell có thể xử lý exception từ code command và một số lỗi phát sinh trong quá trình phân tích command. Các exception parser thường có resolver mặc định riêng. Vì vậy, lỗi thiếu option, sai kiểu dữ liệu và lỗi nghiệp vụ trong method có thể đi qua những nhánh xử lý khác nhau.

## 2. Thông báo mặc định trên terminal

Khi exception phát sinh bên trong command code, Spring Shell bắt exception và hiển thị thông báo một dòng. Mục tiêu là cung cấp dấu hiệu lỗi ngắn gọn để người dùng biết command không hoàn tất.

Ví dụ:

~~~java
@ShellComponent
public class CustomerCommands {

    @ShellMethod(key = "customer show", value = "Hiển thị khách hàng theo ID.")
    public String show(@ShellOption("--id") long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("ID khách hàng phải lớn hơn 0.");
        }
        return "Thông tin khách hàng #" + id;
    }
}
~~~

Khi gọi:

~~~text
shell:>customer show --id 0
~~~

Spring Shell hiển thị thông báo lỗi ngắn thay vì in toàn bộ stack trace. Sau khi hiển thị lỗi, phiên interactive có thể tiếp tục nhận command tiếp theo. Việc một command thất bại không mặc nhiên làm toàn bộ REPL dừng lại.

Thông báo một dòng phù hợp cho lỗi thường gặp mà người dùng có thể tự sửa, ví dụ giá trị không hợp lệ hoặc bản ghi không tồn tại. Với lỗi kỹ thuật phức tạp, cần xem cause và stack trace để xác định vị trí phát sinh.

### Không nhầm lỗi parser với exception nghiệp vụ

Ví dụ, nếu `--id` cần số nguyên nhưng người dùng nhập `abc`, Spring Shell phát hiện lỗi trong giai đoạn phân tích hoặc chuyển đổi option trước khi gọi command method. Phương thức `show()` không được thực thi.

~~~text
shell:>customer show --id abc
~~~

Trong khi đó, nếu người dùng nhập `--id 0`, parser có thể chuyển đổi thành công sang `long`; command method chạy rồi ném `IllegalArgumentException`. Đây là exception từ logic command.

| Tình huống | Giai đoạn | Ví dụ |
|---|---|---|
| Thiếu option bắt buộc | Phân tích command | Không truyền `--id` |
| Sai định dạng kiểu | Chuyển đổi option | `--id abc` trong khi tham số là `long` |
| Giá trị không hợp lệ theo nghiệp vụ | Thực thi command | `--id 0` |
| Không tìm thấy dữ liệu | Thực thi service/domain | ID hợp lệ về cú pháp nhưng không tồn tại |
| Lỗi hạ tầng | Thực thi service/I/O | Database timeout hoặc file không đọc được |

Phân biệt các giai đoạn giúp chọn đúng nơi xử lý lỗi. Không nên viết `try/catch` trong command để xử lý lỗi parser vì method chưa được gọi khi parser thất bại.

## 3. Xem chi tiết bằng command stacktrace

Spring Shell lưu exception gần nhất xảy ra trong command. Khi cần xem nguyên nhân đầy đủ, chạy:

~~~text
shell:>stacktrace
~~~

Command `stacktrace` hiển thị chi tiết exception trên console, bao gồm stack trace và các cause lồng nhau nếu có. Điều này hữu ích khi thông báo một dòng chỉ cho biết lỗi tổng quát nhưng nguyên nhân thực tế nằm sâu hơn.

Ví dụ chuỗi exception:

~~~text
CustomerImportException
  caused by IllegalStateException
    caused by IOException
~~~

Thông báo ngắn có thể chỉ hiển thị `CustomerImportException`. Stack trace giúp lần theo `IllegalStateException`, `IOException` và vị trí code tạo ra lỗi ban đầu.

### Khi nào dùng stacktrace?

- Khi thông báo ngắn chưa đủ để xác định nguyên nhân.
- Khi exception có nested cause.
- Khi cần tìm lớp và dòng code phát sinh lỗi.
- Khi tái hiện lỗi trong môi trường phát triển hoặc kiểm thử.

Trong môi trường production, stack trace có thể chứa đường dẫn file, tên lớp nội bộ, SQL hoặc thông tin cấu hình. Chỉ người có quyền chẩn đoán mới nên xem nội dung chi tiết. Không nên đưa toàn bộ stack trace vào thông báo mặc định cho người dùng cuối.

Command `stacktrace` hiển thị exception gần nhất còn được shell giữ trong phiên. Nếu ứng dụng đã kết thúc ở chế độ non-interactive, người dùng không còn phiên shell đó để gọi `stacktrace`; khi cần điều tra, hãy dùng log ứng dụng hoặc cơ chế giám sát tương ứng.

## 4. Xử lý exception bằng @ExceptionResolver

Với command được đăng ký bằng `@ShellComponent`, có thể khai báo phương thức `@ExceptionResolver` trong cùng component để xử lý exception phát sinh từ các command method.

Ví dụ tạo exception riêng:

~~~java
public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(long customerId) {
        super("Không tìm thấy khách hàng có ID " + customerId);
    }
}
~~~

Command và resolver:

~~~java
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.annotation.ExitCode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer show", value = "Hiển thị khách hàng theo ID.")
    public String show(@ShellOption("--id") long id) {
        return customerService.findById(id)
                .map(Customer::toString)
                .orElseThrow(() -> new CustomerNotFoundException(id));
    }

    @ExceptionResolver
    @ExitCode(code = 4)
    public String handleCustomerNotFound(CustomerNotFoundException ex) {
        return ex.getMessage();
    }
}
~~~

Resolver nhận đúng kiểu exception cần xử lý và trả về `String`. Spring Shell hiển thị chuỗi đó trên terminal. `@ExitCode(code = 4)` đặt exit code cho kết quả xử lý exception này trong chế độ non-interactive.

Nếu không cần mã thoát riêng, có thể bỏ `@ExitCode`; khi resolver trả `String`, mã thoát mặc định của kiểu kết quả này là `1`.

### Resolver có thể nhận exception lồng bên trong

Exception cần xử lý có thể là exception gốc được ném trực tiếp hoặc một cause nằm trong exception wrapper. Spring Shell có thể tìm exception phù hợp ở các cấp cause khác nhau.

Khi nhiều phương thức resolver cùng khớp, exception ở root thường được ưu tiên hơn exception chỉ xuất hiện ở cause. Spring Shell dùng `ExceptionDepthComparator` để sắp xếp theo độ sâu kiểu exception. Nên khai báo kiểu exception cụ thể trong tham số phương thức resolver để việc khớp rõ ràng.

### Các kiểu giá trị trả về của resolver

`@ExceptionResolver` hỗ trợ ba kiểu trả về thường dùng:

| Kiểu trả về | Ý nghĩa |
|---|---|
| `String` | Chuỗi được hiển thị trên shell; exit code mặc định là `1` |
| `CommandHandlingResult` | Trả về message và exit code tường minh |
| `void` | Resolver được xem là đã xử lý exception; exit code mặc định là `0` |

Ví dụ trả về `CommandHandlingResult`:

~~~java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public CommandHandlingResult handleCustomerNotFound(
        CustomerNotFoundException ex) {
    return CommandHandlingResult.of(
            "Không tìm thấy khách hàng. Hãy kiểm tra lại ID.",
            4);
}
~~~

`CommandHandlingResult.of(message, exitCode)` cho phép trả thông báo và mã thoát trong cùng một kết quả. Dùng cách này khi muốn thể hiện rõ cả nội dung lỗi lẫn trạng thái của command.

Nếu resolver trả `void`, nó được xem là đã xử lý exception hoàn toàn. Có thể nhận thêm `Terminal` để ghi thông báo qua writer của JLine:

~~~java
import java.io.PrintWriter;

import org.jline.terminal.Terminal;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.annotation.ExitCode;

@ExceptionResolver
@ExitCode(code = 5)
public void handleStorageFailure(StorageUnavailableException ex,
                                 Terminal terminal) {
    PrintWriter writer = terminal.writer();
    writer.println("Dịch vụ lưu trữ hiện không khả dụng.");
    writer.flush();
}
~~~

Khi ghi trực tiếp qua `Terminal`, dùng writer do framework cung cấp và flush sau khi ghi. Không đóng writer của terminal vì đây là tài nguyên dùng chung của phiên shell.

## 5. CommandExceptionResolver dùng chung

`@ExceptionResolver` phù hợp với các command method trong một `@ShellComponent`. Nếu cần xử lý exception ở phạm vi toàn ứng dụng hoặc dùng chung cho command được đăng ký programmatic, có thể triển khai interface `CommandExceptionResolver`.

Resolver nhận exception và trả về `CommandHandlingResult`. Nếu không xử lý exception đó, trả `null` để chuyển tiếp cho resolver tiếp theo:

~~~java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.stereotype.Component;

@Component
public class DomainExceptionResolver implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception ex) {
        if (ex instanceof CustomerNotFoundException) {
            return CommandHandlingResult.of(
                    "Không tìm thấy khách hàng được yêu cầu.",
                    4);
        }

        if (ex instanceof StorageUnavailableException) {
            return CommandHandlingResult.of(
                    "Dịch vụ lưu trữ tạm thời không khả dụng.",
                    5);
        }

        return null;
    }
}
~~~

Khi đăng ký thành Spring bean, resolver được áp dụng toàn cục. Nếu chỉ một command programmatic cần resolver riêng, thêm cấu hình sau vào builder của command đó:

~~~java
.withErrorHandling()
    .resolver(new CustomerExceptionResolver())
    .and()
~~~

Resolver gắn trực tiếp với command được xử lý trước resolver toàn cục. Các resolver mặc định của Spring Shell cũng tham gia chuỗi để xử lý những lỗi phổ biến như lỗi phân tích command. Thứ tự resolver có thể điều chỉnh bằng `@Order` hoặc interface `Ordered`, tương tự các bean Spring khác.

Không nên viết một resolver bắt mọi exception rồi trả về một thông báo chung. Resolver chỉ nên nhận những exception mà nó hiểu và có thể chuyển thành kết quả phù hợp. Trả `null` với exception không thuộc trách nhiệm của nó để giữ cơ hội xử lý cho resolver tiếp theo.

## 6. Cơ chế xử lý mặc định và thứ tự resolver

Khi exception chưa được xử lý, nó đi lên `ResultHandlerService`, sau đó được xử lý bởi `ResultHandler` phù hợp. Chuỗi `CommandExceptionResolver` cho phép chuyển exception thành message và/hoặc exit code trong `CommandHandlingResult`.

Một số resolver mặc định được đăng ký để xử lý lỗi phổ biến trong quá trình phân tích command. Các resolver này dùng thứ tự ưu tiên dựa trên `CommandExceptionResolver.DEFAULT_PRECEDENCE`. Có thể dùng `@Order` hoặc `Ordered` để đặt resolver tùy chỉnh trước hoặc sau resolver mặc định khi thật sự cần.

| Giai đoạn | Thành phần | Kết quả |
|---|---|---|
| Phân tích option | Parser và resolver parser mặc định | Thông báo lỗi cú pháp/chuyển đổi |
| Thực thi command | Command method hoặc service | Kết quả hoặc exception |
| Xử lý exception | Resolver theo command, resolver toàn cục và resolver mặc định | Message và/hoặc exit code |
| Hiển thị | Result handler | Đưa kết quả xử lý ra terminal |
| Chẩn đoán | Built-in `stacktrace` | Hiển thị chi tiết exception gần nhất |

Khi dùng resolver tùy chỉnh, hãy xác định nó cần chạy ở phạm vi nào và có nên xử lý exception trước resolver mặc định hay không. Resolver quá rộng có thể làm mất thông báo parser hữu ích hoặc che khuất nguyên nhân thật.

## 7. Exit code mặc định khi chạy non-interactive

Exit code là số nguyên được trả về môi trường gọi ứng dụng sau khi command kết thúc. Shell script, CI pipeline, scheduler hoặc tiến trình cha có thể dựa vào mã này để quyết định bước tiếp theo.

Spring Shell 3.3 có hành vi mặc định:

| Kết quả | Exit code mặc định |
|---|---:|
| Lỗi phân tích option của command | `2` |
| Lỗi chung khi xử lý command | `1` |
| Không có lỗi | `0` |

Exit code có ý nghĩa chủ yếu trong non-interactive mode. Trong interactive shell, người dùng tiếp tục nhập command sau khi một command thất bại; mã thoát không đại diện cho việc toàn bộ phiên shell đã kết thúc.

Ví dụ chạy ứng dụng:

~~~powershell
java -jar customer-shell.jar customer show --id abc
Write-Output $LASTEXITCODE
~~~

Trong ví dụ trên, option `--id` cần kiểu số nhưng nhận `abc`, nên lỗi phân tích/chuyển đổi option có exit code mặc định `2`. Nếu command chạy và ném một exception chung chưa được xử lý, exit code mặc định là `1`. Nếu command thành công, exit code là `0`.

Trên Bash hoặc shell Unix, có thể xem mã thoát bằng:

~~~bash
java -jar customer-shell.jar customer show --id 42
echo $?
~~~

Không nên dùng exit code `0` cho một lỗi chỉ vì resolver đã hiển thị thông báo. Một resolver được xem là đã xử lý exception có thể trả mã mặc định `0` nếu phương thức trả `void`; nếu command vẫn thất bại theo nghĩa nghiệp vụ, hãy đặt `@ExitCode` hoặc trả `CommandHandlingResult` với mã khác `0`.

## 8. Tùy chỉnh mã thoát

Có hai cách phổ biến trong Spring Shell 3.3:

- Với resolver annotation, dùng `@ExitCode` trên phương thức hoặc trả về `CommandHandlingResult` có mã cụ thể.
- Với command programmatic, cấu hình mapping exception sang exit code trên `CommandRegistration`.

Trong builder của command programmatic hiện có, thêm cấu hình mapping:

~~~java
.withExitCode()
    .map(CustomerNotFoundException.class, 4)
    .map(StorageUnavailableException.class, 5)
    .and()
~~~

Có thể map theo một hàm nhận `Throwable` khi cần quyết định mã động dựa trên exception. Mapping `.withExitCode()` là cấu hình của `CommandRegistration`; tài liệu Spring Shell 3.3 không cung cấp cùng dạng mapping này trong annotation-based registration. Với legacy `@ExceptionResolver`, dùng `@ExitCode` hoặc `CommandHandlingResult` để trả mã của trường hợp đã xử lý.

### Exception tự mang exit code

Spring Shell tích hợp với cơ chế exit code của Spring Boot. Có thể dùng exception riêng triển khai `ExitCodeGenerator` để cung cấp mã:

~~~java
import org.springframework.boot.ExitCodeGenerator;

public class CustomerImportException extends RuntimeException
        implements ExitCodeGenerator {

    private final int exitCode;

    public CustomerImportException(String message, int exitCode) {
        super(message);
        this.exitCode = exitCode;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
~~~

Ví dụ này phù hợp khi exit code là một phần của hợp đồng exception và được nhiều tầng gọi sử dụng. Nếu mã thoát chỉ có ý nghĩa trong một command cụ thể, cấu hình ở resolver hoặc `CommandRegistration` thường dễ đọc hơn.

## 9. Chọn nơi xử lý exception

Không phải exception nào cũng cần được bắt tại cùng một tầng:

| Nơi xử lý | Khi phù hợp |
|---|---|
| Service/domain | Khi cần chuyển lỗi kỹ thuật thành lỗi nghiệp vụ hoặc áp dụng quy tắc chung cho nhiều kênh gọi |
| `@ExceptionResolver` trong `@ShellComponent` | Khi muốn chuyển exception của nhóm command legacy thành thông báo thân thiện |
| `CommandExceptionResolver` toàn cục | Khi cùng quy tắc xử lý được áp dụng cho nhiều command |
| Resolver trong `CommandRegistration` | Khi chỉ một command programmatic có quy tắc lỗi riêng |
| Cơ chế mặc định của Spring Shell | Khi không cần định dạng hoặc mã thoát đặc biệt |

Ví dụ, `CustomerNotFoundException` có thể được xử lý ở service để REST API và CLI đều nhận cùng một lỗi nghiệp vụ. Nếu chỉ cần thay đổi cách hiển thị trên terminal, resolver ở lớp shell có thể chuyển exception đó thành thông báo phù hợp với người dùng CLI.

Không nên bắt `Exception` ở mọi command rồi chỉ trả về `ex.getMessage()`. Cách này khiến lỗi hạ tầng, lỗi lập trình và lỗi nghiệp vụ trông giống nhau; đồng thời có thể làm mất cause và stack trace hữu ích.

## 10. Thông báo lỗi tốt cho người dùng

Thông báo lỗi trên terminal nên giúp người dùng hiểu điều gì xảy ra và có thể làm gì tiếp theo. Một thông báo tốt thường có:

- Đối tượng hoặc thao tác bị lỗi.
- Nguyên nhân ở mức người dùng có thể hiểu.
- Giá trị cần kiểm tra hoặc bước khắc phục.
- Mã tham chiếu nếu cần liên hệ log hoặc bộ phận hỗ trợ.

Ví dụ:

| Thông báo kém hữu ích | Thông báo tốt hơn |
|---|---|
| `RuntimeException` | `Không tìm thấy khách hàng có ID 42.` |
| `Invalid input` | `Giá trị --limit phải nằm trong khoảng 1 đến 100.` |
| `Access denied` | `Không thể đọc file đầu vào. Hãy kiểm tra quyền đọc của tài khoản đang chạy ứng dụng.` |
| `Database error` | `Không thể kết nối cơ sở dữ liệu. Hãy thử lại sau hoặc liên hệ quản trị viên nếu lỗi tiếp tục.` |

Tránh đưa stack trace, SQL, token, mật khẩu, chuỗi kết nối hoặc thông tin nội bộ vào thông báo hiển thị mặc định. Ghi chi tiết kỹ thuật vào log có kiểm soát và cung cấp mã tham chiếu để truy vết khi cần.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ thấy một dòng lỗi, không thấy stack trace | Đây là hành vi mặc định của Spring Shell | Chạy `stacktrace` ngay sau lỗi trong phiên tương tác |
| `stacktrace` không hiển thị lỗi mong muốn | Một command khác đã phát sinh exception sau lỗi cần xem | Chạy `stacktrace` ngay sau command thất bại |
| `@ExceptionResolver` không được gọi | Resolver không nằm trong `@ShellComponent` phù hợp hoặc kiểu exception không khớp | Kiểm tra component scan, tham số resolver và cause chain |
| Resolver nhận exception wrapper thay vì exception nghiệp vụ | Exception nghiệp vụ nằm trong nested cause | Khai báo kiểu exception cụ thể và kiểm tra cause matching |
| Resolver xử lý cả lỗi không thuộc phạm vi | Phương thức dùng kiểu quá tổng quát | Chỉ nhận kiểu exception cần xử lý; để resolver khác xử lý phần còn lại |
| Thông báo đã xử lý nhưng script vẫn coi là thành công | Resolver `void` mặc định exit code `0` | Đặt `@ExitCode` hoặc trả `CommandHandlingResult` có mã khác `0` |
| Lỗi option trả mã khác dự kiến | Lỗi xảy ra ở parser, trước khi command method được gọi | Kiểm tra nhóm lỗi parsing; mặc định exit code parsing là `2` |
| Command thất bại nhưng trả mã `0` | Exception bị bắt và chuyển thành kết quả thành công hoặc resolver trả `void` | Xác định rõ mã thoát theo hợp đồng của command |
| Custom resolver không chạy trước resolver mặc định | Thứ tự resolver theo precedence | Điều chỉnh `@Order` hoặc `Ordered` sau khi xác định thứ tự cần thiết |
| Stack trace chứa dữ liệu nội bộ | Exception message/cause chứa thông tin nhạy cảm | Giới hạn quyền xem, chuẩn hóa thông báo và quản lý log |

## 12. Checklist xử lý exception

- Xác định lỗi phát sinh trong parser, command method, service hay hạ tầng.
- Để Spring Shell xử lý mặc định khi không cần thông báo hoặc mã thoát riêng.
- Dùng `stacktrace` để xem chi tiết exception gần nhất trong phiên tương tác.
- Dùng exception nghiệp vụ cụ thể thay vì ném `RuntimeException` chung chung.
- Dùng `@ExceptionResolver` cho nhóm command legacy cần thông báo riêng.
- Dùng `CommandExceptionResolver` khi cần xử lý ở phạm vi toàn cục hoặc programmatic.
- Trả `null` từ resolver toàn cục nếu exception không thuộc trách nhiệm của nó.
- Kiểm tra thứ tự resolver khi có nhiều resolver cùng khớp.
- Đặt exit code khác `0` cho command thất bại trong non-interactive mode.
- Không để thông báo lỗi tiết lộ stack trace hoặc dữ liệu nhạy cảm cho người dùng cuối.
- Ghi log chi tiết có kiểm soát để hỗ trợ chẩn đoán.
- Kiểm thử cả thông báo hiển thị và exit code thực tế của tiến trình.

## 13. Bài tập thực hành

Xây dựng command `customer import --file <path>` và xử lý các lỗi sau:

1. File không tồn tại: ném `ImportFileNotFoundException`.
2. File tồn tại nhưng không đúng định dạng: ném `InvalidImportFormatException`.
3. Cơ sở dữ liệu không khả dụng: ném `StorageUnavailableException`.
4. Để một lần chạy không có resolver tùy chỉnh và quan sát thông báo một dòng mặc định.
5. Chạy `stacktrace` để xem chi tiết exception và cause.
6. Thêm `@ExceptionResolver` trong `@ShellComponent` để xử lý `ImportFileNotFoundException`, trả thông báo có hướng dẫn sửa đường dẫn và exit code `4`.
7. Thêm một `CommandExceptionResolver` toàn cục để xử lý `StorageUnavailableException`, trả message và exit code `5`.
8. Với exception không thuộc hai loại trên, trả `null` từ resolver toàn cục và xác nhận cơ chế mặc định vẫn xử lý.
9. Chạy ứng dụng ở non-interactive mode và kiểm tra exit code cho lỗi parser, lỗi chung và thành công.
10. Xác nhận thông báo terminal không để lộ stack trace hoặc thông tin kết nối cơ sở dữ liệu.

Khi hoàn thành, hãy giải thích sự khác nhau giữa thông báo lỗi mặc định, stack trace, resolver tùy chỉnh và exit code mà tiến trình cha nhận được.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Exception Handling](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/index.html): tổng quan exception handling và phạm vi ý nghĩa của exit code.
- [Spring Shell 3.3 – Stacktrace](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/stacktrace.html): thông báo exception một dòng và command xem stack trace gần nhất.
- [Spring Shell 3.3 – Exception Resolving](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/resolving.html): chuỗi `CommandExceptionResolver`, `CommandHandlingResult` và thứ tự resolver.
- [Spring Shell 3.3 – @ExceptionResolver](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/annotation.html): xử lý exception trong `@ShellComponent`, kiểu trả về và `@ExitCode`.
- [Spring Shell 3.3 – Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.3/commands/exceptionhandling/mappings.html): mã thoát mặc định và mapping exception trong `CommandRegistration`.
- [Spring Shell 3.3 – CommandHandlingResult API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandHandlingResult.html): message và exit code của kết quả xử lý.
- [Spring Boot – ExitCodeGenerator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ExitCodeGenerator.html): cung cấp exit code từ exception hoặc đối tượng ứng dụng.
