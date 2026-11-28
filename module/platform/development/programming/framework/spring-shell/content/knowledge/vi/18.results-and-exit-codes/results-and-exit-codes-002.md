# Quy ước thành công, lỗi đầu vào và lỗi thực thi

Một command CLI cần cho người dùng biết thao tác đã thành công hay thất bại, đồng thời cung cấp mã trạng thái đủ rõ để script, CI/CD hoặc tiến trình gọi nó quyết định bước tiếp theo. Spring Shell hỗ trợ hiển thị kết quả, xử lý exception và ánh xạ lỗi sang mã thoát. Cách biểu diễn thay đổi giữa Spring Shell 3.x và 4.x, đặc biệt khi phân biệt trạng thái của command với mã thoát của tiến trình Java.

Bài học tập trung vào ba nhóm kết quả chính: **thành công**, **lỗi đầu vào/cách dùng** và **lỗi thực thi**. Phần cuối mở rộng thêm trạng thái command chưa khả dụng và cách tích hợp mã thoát cấp tiến trình.

## 1. Phân biệt kết quả hiển thị và mã thoát

Khi command chạy, có nhiều loại thông tin khác nhau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Nội dung kết quả | Văn bản hoặc dữ liệu được hiển thị cho người dùng | "Đã cập nhật tồn kho." |
| Thông báo lỗi | Giải thích vì sao command không hoàn thành | "Mã SKU không tồn tại." |
| Trạng thái command | Kết quả thực thi được framework ghi nhận | Thành công, lỗi cách dùng, lỗi thực thi |
| Mã thoát của command | Số nguyên gắn với kết quả command, có ý nghĩa rõ nhất khi chạy non-interactive | 0, 1, 2 |
| Mã thoát tiến trình | Số nguyên mà hệ điều hành nhận được khi tiến trình Java kết thúc | java -jar ... kết thúc với status 2 |

Không nên xem một dòng thông báo là bằng chứng duy nhất cho biết command đã thành công. Một command có thể in ra chuỗi “Không thể cập nhật” rồi trả về bình thường; nếu không có cơ chế xử lý lỗi khác, framework vẫn có thể xem đó là một lần thực thi thành công. Ngược lại, command có thể ghi một phần output rồi phát sinh exception và được đánh dấu là lỗi.

**Kết quả hiển thị dành cho người đọc; mã thoát dành cho chương trình gọi command.** Cần thiết kế cả hai một cách nhất quán.

## 2. Ba nhóm kết quả cơ bản

### 2.1. Thành công

Command thành công khi hoàn tất đúng mục tiêu và không phát sinh lỗi cần báo cho caller. Theo quy ước CLI phổ biến và mặc định của Spring Shell 3.x, mã **0** biểu thị thành công.

~~~text
shell:>stock adjust --sku SKU-123 --quantity 5
Đã điều chỉnh tồn kho cho SKU-123: +5.
~~~

Thông báo thành công nên nói rõ hành động đã hoàn tất và đối tượng bị tác động. Với thao tác tạo hoặc cập nhật dữ liệu, có thể trả về mã định danh hoặc số lượng bản ghi đã xử lý để người dùng kiểm tra.

### 2.2. Lỗi đầu vào hoặc cách dùng

Lỗi đầu vào xảy ra trước khi nghiệp vụ có thể thực thi đúng, thường do command, option hoặc giá trị không đúng hợp đồng:

- Không truyền option bắt buộc.
- Dùng tên option không tồn tại.
- Truyền giá trị không chuyển đổi được sang kiểu yêu cầu.
- Số lượng token sai arity.
- Giá trị vi phạm constraint như **@NotBlank**, **@Min** hoặc **@Pattern**.

Ví dụ:

~~~text
shell:>stock adjust --sku SKU-123 --quantity abc
Cannot convert 'abc' to Integer for option '--quantity'.
~~~

Hoặc:

~~~text
shell:>stock adjust --sku SKU-123 --quantity 0
The following constraints were not met:
  --quantity: must be greater than or equal to 1
~~~

Thông báo nên chỉ ra option hoặc giá trị sai và cách sửa. Không nên báo lỗi chung như “Command failed” nếu có thể chỉ rõ **--quantity** phải lớn hơn hoặc bằng 1.

### 2.3. Lỗi thực thi

Lỗi thực thi xảy ra sau khi đầu vào đã được phân tích và chuyển đổi, nhưng nghiệp vụ không thể hoàn thành:

- Không tìm thấy sản phẩm hoặc đơn hàng.
- Không kết nối được cơ sở dữ liệu hoặc dịch vụ từ xa.
- Người dùng không có quyền thực hiện thao tác.
- Ghi file thất bại hoặc giao dịch bị rollback.
- Một lỗi bất ngờ trong code làm command dừng giữa chừng.

Ví dụ:

~~~text
shell:>stock adjust --sku SKU-123 --quantity 5
Không thể điều chỉnh tồn kho: kho HN hiện không khả dụng.
~~~

Thông báo cho người dùng nên đủ cụ thể để họ biết bước tiếp theo, nhưng không để lộ stack trace, SQL, đường dẫn nội bộ, token hoặc thông tin nhạy cảm. Chi tiết kỹ thuật nên được ghi vào log phù hợp.

## 3. Mặc định mã thoát trong Spring Shell 3.x

Tài liệu Spring Shell 3.1.x mô tả các mã thoát mặc định khi command chạy ở chế độ non-interactive:

| Tình huống | Mã mặc định | Ý nghĩa |
|---|---:|---|
| Command hoàn tất bình thường | **0** | Thành công |
| Lỗi phân tích option | **2** | Cách gọi hoặc đầu vào không hợp lệ |
| Lỗi chung | **1** | Lỗi thực thi hoặc lỗi không được phân loại cụ thể |

Đây là quy ước mặc định được tài liệu Spring Shell 3.1.x nêu rõ. Mã thoát có ý nghĩa với môi trường gọi ứng dụng ở chế độ non-interactive; khi người dùng đang ở REPL, shell vẫn tiếp tục nhận command sau khi hiển thị lỗi.

Ví dụ chạy một command từ terminal hệ điều hành:

~~~bash
java -jar inventory-shell.jar stock adjust --sku SKU-123 --quantity 5
echo $?
~~~

Trong Bash, **$?** chứa mã thoát của tiến trình vừa chạy. Nếu command thành công, mã mặc định là **0**. Nếu parser không chấp nhận option hoặc giá trị, mã mặc định là **2**; nếu có lỗi chung, mã mặc định là **1**.

Trên PowerShell, có thể kiểm tra **$LASTEXITCODE** sau khi chạy tiến trình native:

~~~powershell
java -jar .\inventory-shell.jar stock adjust --sku SKU-123 --quantity 5
$LASTEXITCODE
~~~

Đừng nhầm mã thoát của command với mã thoát của một dòng lệnh trong REPL. Trong REPL, người dùng có thể chạy nhiều command trong cùng một tiến trình; lỗi của một command không đồng nghĩa ứng dụng đã kết thúc.

## 4. Xử lý exception trong Spring Shell 3.x

Spring Shell 3.x dùng chuỗi **CommandExceptionResolver** để xử lý exception chưa được command xử lý. Resolver có thể trả về **CommandHandlingResult** chứa thông báo và mã thoát.

### 4.1. Resolver toàn cục

Có thể đăng ký resolver thành Spring bean để xử lý một nhóm exception dùng chung:

~~~java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.stereotype.Component;

@Component
public class InventoryExceptionResolver implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof ProductNotFoundException ex) {
            return CommandHandlingResult.of(
                    "Không tìm thấy sản phẩm: " + ex.getSku(), 1);
        }

        if (exception instanceof InvalidStockInputException ex) {
            return CommandHandlingResult.of(
                    "Dữ liệu tồn kho không hợp lệ: " + ex.getMessage(), 2);
        }

        return null;
    }
}
~~~

Nếu resolver không xử lý exception, trả về **null** để resolver tiếp theo trong chuỗi thử xử lý. Resolver được khai báo trực tiếp trên **CommandRegistration** được chạy trước resolver toàn cục. Với nhiều resolver bean, có thể điều khiển thứ tự bằng **@Order** hoặc **Ordered**.

Trong ứng dụng thật, hãy phân loại exception theo ý nghĩa. **ProductNotFoundException** có thể là lỗi nghiệp vụ hoặc dữ liệu không tồn tại; không nên biến mọi **RuntimeException** thành lỗi đầu vào chỉ để có một mã thoát duy nhất.

### 4.2. @ExceptionResolver cho legacy annotation model

Với lớp **@ShellComponent**, có thể định nghĩa phương thức **@ExceptionResolver** để xử lý exception từ command method trong cùng component. Hai annotation resolver và exit code nằm trong package **org.springframework.shell.command.annotation**; command legacy vẫn dùng annotation trong **org.springframework.shell.standard**.

~~~java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;
import org.springframework.shell.command.annotation.ExitCode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class StockCommands {

    private final InventoryService inventoryService;

    public StockCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @ShellMethod(key = "stock adjust", value = "Điều chỉnh số lượng tồn kho.")
    public String adjust(
            @ShellOption("--sku") String sku,
            @ShellOption("--quantity") int quantity) {
        return inventoryService.adjust(sku, quantity);
    }

    @ExceptionResolver
    CommandHandlingResult handleStockError(ProductNotFoundException exception) {
        return CommandHandlingResult.of(
                "Không tìm thấy sản phẩm: " + exception.getSku(), 1);
    }

    @ExceptionResolver
    @ExitCode(code = 2)
    String handleInvalidInput(InvalidStockInputException exception) {
        return "Dữ liệu không hợp lệ: " + exception.getMessage();
    }
}
~~~

**@ExceptionResolver** có thể trả về **CommandHandlingResult**, **String** hoặc **void**:

- **CommandHandlingResult** cho phép chỉ định cả thông báo và mã thoát.
- **String** được in ra shell; nếu không có **@ExitCode**, mã thoát mặc định của nhánh xử lý này là **1**.
- **void** được xem là đã xử lý exception; mặc định mã thoát là **0**. Có thể dùng **@ExitCode** để chỉ định mã khác và dùng **Terminal** để ghi thông báo.

Khi có nhiều phương thức resolver khớp exception, Spring Shell ưu tiên exception gốc phù hợp hơn exception nằm sâu trong cause chain. Nên khai báo kiểu exception cụ thể trong tham số phương thức thay vì bắt mọi lỗi bằng **Exception**.

### 4.3. Tùy chỉnh exit code bằng CommandRegistration

Với programmatic model của Spring Shell 3.x, có thể ánh xạ exception sang mã thoát trực tiếp trong builder:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("stock adjust")
        .withExitCode()
            .map(InvalidStockInputException.class, 2)
            .map(ProductNotFoundException.class, 1)
            .map(InventoryUnavailableException.class, 3)
            .and()
        .withTarget()
            .function(context -> inventoryService.adjust(
                    context.getOptionValue("sku"),
                    context.getOptionValue("quantity")))
            .and()
        .build();
~~~

Trong ví dụ, mã **3** cho **InventoryUnavailableException** là quy ước riêng của ứng dụng; nó không phải mã mặc định của Spring Shell. Tài liệu Spring Shell 3.x nêu rằng mapping **withExitCode()** không thể tùy chỉnh bằng annotation-based configuration. Với command annotation, hãy dùng **@ExceptionResolver**/**@ExitCode** hoặc xử lý exception bằng resolver phù hợp.

## 5. Spring Shell 4.x: ExitStatus và ExitStatusExceptionMapper

Spring Shell 4 thay mô hình xử lý exception của 3.x bằng API **ExitStatus** và **ExitStatusExceptionMapper**.

**ExitStatus** là record gồm hai thành phần:

- **code**: mã trạng thái dạng số nguyên.
- **description**: mô tả trạng thái.

Framework cung cấp các trạng thái chuẩn:

| Hằng | Ý nghĩa |
|---|---|
| **ExitStatus.OK** | Command thành công |
| **ExitStatus.USAGE_ERROR** | Lỗi cách dùng hoặc đầu vào |
| **ExitStatus.EXECUTION_ERROR** | Lỗi trong khi thực thi command |
| **ExitStatus.AVAILABILITY_ERROR** | Command hiện chưa khả dụng |

Nên dùng các hằng này khi phân loại lỗi theo ý nghĩa chuẩn của framework. Khi cần một mã hoặc mô tả riêng, có thể tạo **new ExitStatus(code, description)**. Không nên tự giả định giá trị số của các hằng nếu ứng dụng chỉ cần phân loại theo API; hãy đọc **code()** từ trạng thái hoặc kiểm tra đúng phiên bản thư viện đang chạy.

### 5.1. Đăng ký ExitStatusExceptionMapper

Mapper nhận exception và trả về **ExitStatus**. Có thể đăng ký mapper thành bean rồi tham chiếu bằng tên trong **@Command**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Bean
ExitStatusExceptionMapper stockExceptionMapper() {
    return exception -> {
        if (exception instanceof InvalidStockInputException) {
            return ExitStatus.USAGE_ERROR;
        }
        if (exception instanceof InventoryUnavailableException) {
            return ExitStatus.AVAILABILITY_ERROR;
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
~~~

Gắn mapper vào command:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class StockCommands {

    private final InventoryService inventoryService;

    public StockCommands(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Command(
        name = "stock adjust",
        description = "Điều chỉnh số lượng tồn kho.",
        exitStatusExceptionMapper = "stockExceptionMapper"
    )
    public String adjust(
            @Option(longName = "sku") String sku,
            @Option(longName = "quantity") int quantity) {
        return inventoryService.adjust(sku, quantity);
    }
}
~~~

Tên mapper trong **exitStatusExceptionMapper** phải khớp tên bean Spring. Với programmatic model, có thể truyền mapper trực tiếp bằng **Command.Builder.exitStatusExceptionMapper(...)**.

Mapper giúp framework tạo trạng thái command và thông báo phù hợp. Nó thay thế **CommandExceptionResolver** của Spring Shell 3.x; không tiếp tục dùng **CommandHandlingResult** trong mô hình 4.x.

### 5.2. Command programmatic trả về ExitStatus

Trong Spring Shell 4, hợp đồng **Command.execute(CommandContext)** trả về **ExitStatus**. Có thể dùng **AbstractCommand** để định nghĩa rõ kết quả thành công:

~~~java
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Bean
Command stockReportCommand(InventoryService inventoryService) {
    return new AbstractCommand("stock report", "Tạo báo cáo tồn kho.") {

        @Override
        public ExitStatus doExecute(CommandContext context) {
            String report = inventoryService.createReport();
            println(report, context);
            return ExitStatus.OK;
        }
    };
}
~~~

Nếu có lỗi nghiệp vụ, command có thể ném exception đã được mapper xử lý. Với lỗi thực thi đặc thù cần mã số cụ thể, Spring Shell 4.0.2+ có **CommandExecutionException(message, exitCode)**. Hãy phân biệt mã được gắn vào exception với mã thoát của tiến trình Java ở phần tiếp theo.

## 6. Kết quả command và cách ghi output

Trong annotation model, khi phương thức command trả về một giá trị như **String**, Spring Shell hiển thị giá trị đó trong shell output. Nếu phương thức trả về **void**, command tự ghi output qua writer hoặc một API hiển thị phù hợp.

Với programmatic model, **Function<CommandContext, ?>** trong Spring Shell 3.x trả về một giá trị được in ra shell; **Consumer<CommandContext>** tự ghi nội dung qua **Terminal** writer. Trong Spring Shell 4, **CommandContext.outputWriter()** là cách được khuyến nghị để ghi output.

Ví dụ Spring Shell 4:

~~~java
@Command(name = "stock report", description = "Tạo báo cáo tồn kho.")
public void report(CommandContext context) {
    context.outputWriter().println("Đã tạo báo cáo tồn kho.");
    context.outputWriter().flush();
}
~~~

Nên giữ output có quy ước:

- Thành công: mô tả kết quả và dữ liệu quan trọng như mã bản ghi hoặc số lượng xử lý.
- Lỗi đầu vào: chỉ ra option/giá trị sai và cách sửa.
- Lỗi thực thi: giải thích thao tác nào thất bại và hướng xử lý tiếp theo.
- Dữ liệu dành cho pipeline: dùng định dạng ổn định, không trộn banner, tiến độ hoặc log vào output dữ liệu.

Không in mật khẩu, access token, secret hoặc thông tin cá nhân nhạy cảm ra terminal. Không in stack trace cho người dùng thông thường; dùng log và chế độ debug khi cần chẩn đoán.

## 7. Mã thoát command khác mã thoát tiến trình trong Spring Shell 4

Đây là điểm cần chú ý khi nâng từ 3.x lên 4.x. Trong Spring Shell 4.0.4, tài liệu nói rõ **ExitStatus** là trạng thái của command và khác với mã thoát của tiến trình JVM. Chỉ cấu hình **ExitStatusExceptionMapper** không tự động đặt mã thoát của tiến trình.

Vì vậy, cần tách hai mục tiêu:

1. **Phản hồi bên trong Spring Shell:** hiển thị thông báo và trạng thái command bằng **ExitStatus**.
2. **Phản hồi cho hệ điều hành:** khi ứng dụng kết thúc, tiến trình Java trả mã thoát để Bash, PowerShell, CI/CD hoặc scheduler đọc được.

Spring Boot cung cấp **ExitCodeGenerator** và **SpringApplication.exit(...)** để tính mã thoát ứng dụng. Trong launcher tự quản lý, mã trả về có thể được truyền vào **System.exit(...)**:

~~~java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(InventoryShellApplication.class, args);

    int exitCode = SpringApplication.exit(context);
    System.exit(exitCode);
}
~~~

Để mã thoát phản ánh kết quả command, ứng dụng phải chuyển kết quả command sang cơ chế **ExitCodeGenerator** của Spring Boot hoặc tự điều phối runner và mã thoát ở launcher. Không nên giả định mapper của Spring Shell tự làm việc này. Khi dùng Spring Boot starter và **springShellApplicationRunner** mặc định, hãy kiểm tra hành vi non-interactive của chính ứng dụng và kiểm thử **$?**/**$LASTEXITCODE** ở mức tiến trình.

## 8. Interactive và non-interactive ảnh hưởng thế nào?

Trong REPL tương tác, người dùng có thể chạy nhiều command liên tiếp. Command lỗi sẽ hiển thị thông báo; shell vẫn hoạt động để nhận lệnh tiếp theo. Mã thoát không phải tín hiệu chính để người dùng điều khiển phiên REPL.

Trong non-interactive mode, một command hoặc script được chạy từ đối số tiến trình rồi kết thúc. Mã thoát lúc này có ý nghĩa với môi trường gọi ứng dụng.

Spring Shell 4 mặc định bật interactive mode, kể cả khi truyền đối số command. Muốn chạy command từ process arguments, cần đặt:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Ví dụ:

~~~bash
java -jar inventory-shell.jar stock report
echo $?
~~~

Hãy kiểm tra riêng hai đường chạy: chạy command tại prompt **shell:>** và gọi ứng dụng từ terminal hệ điều hành. Một test trong REPL không chứng minh mã thoát tiến trình đã đúng.

## 9. Đề xuất quy ước mã cho ứng dụng

Với Spring Shell 3.x, nên giữ mặc định **0**, **2**, **1** trừ khi ứng dụng có lý do cần phân loại thêm. Khi cần mã riêng, công bố một bảng mã ổn định cho script và người vận hành.

Ví dụ quy ước mở rộng của một ứng dụng (các mã **3** và **4** là lựa chọn của ứng dụng, không phải mã mặc định Spring Shell):

| Mã | Nhóm | Ý nghĩa |
|---|---|---|
| **0** | Thành công | Command hoàn tất |
| **1** | Lỗi thực thi | Lỗi không được phân loại riêng hoặc lỗi hệ thống |
| **2** | Lỗi cách dùng | Thiếu/sai option, parse hoặc dữ liệu đầu vào không hợp lệ |
| **3** | Không khả dụng | Dịch vụ hoặc trạng thái hiện tại chưa cho phép thao tác |
| **4** | Không tìm thấy dữ liệu | Đối tượng được yêu cầu không tồn tại |

Trong Spring Shell 4, dùng **ExitStatus** chuẩn để phân loại theo ngữ nghĩa; nếu cần bảng số riêng cho ứng dụng hoặc hệ điều hành, hãy ánh xạ rõ ràng ở tầng ứng dụng và launcher. Không đổi mã đã được script bên ngoài sử dụng nếu chưa cập nhật các caller.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| In chuỗi “Thất bại” rồi trả về bình thường | Caller có thể nhận mã thành công | Ném exception phù hợp hoặc trả trạng thái lỗi theo mô hình đang dùng |
| Dùng mã **0** cho lỗi đã xử lý | Script tưởng command thành công và tiếp tục sai | Chỉ dùng **0** khi thao tác thực sự thành công hoặc khi resolver chủ động coi lỗi đã được xử lý như thành công |
| Gộp lỗi parse và lỗi database | Người dùng không biết cần sửa command hay kiểm tra hệ thống | Phân loại lỗi đầu vào và lỗi thực thi riêng |
| Dùng exception tổng quát cho mọi tình huống | Khó ánh xạ mã ổn định | Tạo exception nghiệp vụ cụ thể như **InvalidStockInputException**, **InventoryUnavailableException** |
| Dùng **ExitStatusExceptionMapper** để kỳ vọng đổi mã JVM | Script bên ngoài vẫn nhận mã tiến trình khác với mong đợi | Kết nối kết quả command với Spring Boot **ExitCodeGenerator**/launcher và kiểm thử process exit |
| Dùng API 3.x trong command 4.x | Không biên dịch hoặc không được gọi | Chuyển **CommandExceptionResolver** sang **ExitStatusExceptionMapper** |
| Dùng exit-code builder trong annotation 3.x | Mapping không được áp dụng như mong đợi | Dùng **@ExceptionResolver**/**@ExitCode** cho annotation hoặc **withExitCode()** cho programmatic registration |
| In stack trace ra output bình thường | Output khó đọc và có thể lộ thông tin nội bộ | Trả thông báo ngắn, ghi chi tiết vào log và bật debug khi cần |
| Chỉ kiểm thử output, không kiểm tra exit code | CI/CD có thể nhận sai trạng thái | Kiểm thử cả nội dung và mã thoát của process |

## 11. Kiểm thử kết quả và mã thoát

Nên kiểm tra cả thông báo hiển thị, trạng thái command và mã thoát tiến trình. Có thể dùng **ShellTestClient** để kiểm tra output của command, sau đó dùng process integration test để xác minh mã thoát thực tế.

Ma trận tối thiểu cho **stock adjust**:

| Trường hợp | Output mong đợi | Mã/nhóm mong đợi |
|---|---|---|
| SKU hợp lệ, quantity hợp lệ | Xác nhận đã cập nhật | Thành công (**0** theo quy ước 3.x) |
| Thiếu **--sku** | Báo thiếu option | Lỗi cách dùng; mặc định 3.x là **2** |
| **--quantity abc** | Báo không chuyển được kiểu | Lỗi parse; mặc định 3.x là **2** |
| **--quantity 0** | Báo vi phạm constraint | Lỗi đầu vào; xử lý theo validation/resolver |
| SKU không tồn tại | Báo không tìm thấy sản phẩm | Lỗi thực thi/nghiệp vụ; mặc định chung 3.x là **1** nếu không map riêng |
| Dịch vụ kho mất kết nối | Báo dịch vụ không khả dụng | Lỗi thực thi hoặc availability theo quy ước ứng dụng |
| Exception bất ngờ | Thông báo an toàn, log có chi tiết | Lỗi thực thi; mặc định 3.x là **1** |

Các bước kiểm thử:

1. Unit test cho service để xác nhận exception nghiệp vụ được ném đúng loại.
2. Test resolver/mapper để xác nhận từng exception ánh xạ sang đúng kết quả hoặc mã.
3. Integration test bằng **ShellTestClient** để xác nhận command hiển thị thông báo đúng và không gọi service khi parse/validation thất bại.
4. Process integration test khởi chạy artifact bằng đối số command, đọc stdout/stderr và xác nhận exit code.
5. Kiểm tra cả trường hợp thành công và thất bại trong Bash (**$?**) hoặc PowerShell (**$LASTEXITCODE**).
6. Kiểm tra command trong REPL để bảo đảm lỗi không làm đóng phiên shell ngoài ý muốn.

## 12. Quy trình xử lý lỗi trong command

1. Để parser xử lý lỗi cú pháp, option thiếu và chuyển đổi kiểu.
2. Dùng Bean Validation hoặc kiểm tra dữ liệu đầu vào cho constraint thuộc command.
3. Dùng exception nghiệp vụ cụ thể cho lỗi thực thi.
4. Ánh xạ exception sang thông báo và trạng thái phù hợp bằng API của phiên bản Spring Shell đang dùng.
5. Chỉ in thông tin cần thiết cho người dùng; ghi chi tiết kỹ thuật vào log.
6. Nếu caller cần mã thoát tiến trình, nối kết quả command với cơ chế exit code của ứng dụng và kiểm thử từ hệ điều hành.

## 13. Ranh giới phiên bản

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Kết quả command | Giá trị trả về được xử lý qua result handler; **CommandHandlingResult** có thể mang message và exit code | **Command.execute** trả **ExitStatus**; annotation method có thể trả kết quả hiển thị |
| Xử lý exception | **CommandExceptionResolver**, **@ExceptionResolver** | **ExitStatusExceptionMapper** |
| Trạng thái chuẩn | Mặc định code **0**, parse **2**, generic **1** trong non-interactive mode | **ExitStatus.OK**, **USAGE_ERROR**, **EXECUTION_ERROR**, **AVAILABILITY_ERROR** |
| Mapping theo command | **CommandRegistration.withExitCode()** hoặc resolver | **Command.Builder.exitStatusExceptionMapper(...)** hoặc **@Command(exitStatusExceptionMapper = ...)** |
| Process exit code | Tài liệu 3.x mô tả exit code cho non-interactive shell | Tài liệu 4.x nhấn mạnh command status khác JVM process exit code |

Spring Shell 4 thay **CommandExceptionResolver** bằng **ExitStatusExceptionMapper** và **CommandHandlingResult** bằng **ExitStatus**. Với **CommandExecutionException(message, exitCode)**, constructor nhận mã cụ thể có từ 4.0.2. Khi nâng cấp, cần chuyển cả exception mapping lẫn các script đang phụ thuộc mã thoát cũ.

## 14. Tổng kết

Quy ước nên giữ đơn giản: **0** cho thành công, lỗi đầu vào/cách dùng được phân biệt với lỗi thực thi, và thông báo phải chỉ rõ người dùng cần làm gì tiếp theo. Trong Spring Shell 3.x, tài liệu nêu mặc định thành công **0**, lỗi parse option **2**, lỗi chung **1**; **CommandExceptionResolver**, **@ExceptionResolver** và **CommandRegistration.withExitCode()** là các điểm tùy chỉnh chính.

Trong Spring Shell 4.x, dùng **ExitStatus** và **ExitStatusExceptionMapper** để biểu diễn trạng thái command. Phải phân biệt trạng thái command với mã thoát JVM: mapper không tự cấu hình process exit code. Khi script hoặc CI/CD cần nhận kết quả chính xác, hãy nối trạng thái command với **ExitCodeGenerator**/launcher của Spring Boot và kiểm thử mã thoát của tiến trình thật.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html) — mục 4.4 Exception Handling, 4.4.1 Exception Resolving, 4.4.2 Exit Code Mappings và 4.4.3 ExceptionResolver.
- [CommandHandlingResult API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandHandlingResult.html) — kết quả xử lý gồm message và exit code.
- [CommandRegistration API 3.1.x](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandRegistration.html) — cấu hình exception resolver và exit-code mapping theo command.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi exception handling từ CommandExceptionResolver sang ExitStatusExceptionMapper và ExitStatus.
- [Spring Shell 4.0.4 Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html) — đăng ký ExitStatusExceptionMapper trong annotation và programmatic model; phân biệt command status với JVM process exit code.
- [ExitStatus API 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html) — các trạng thái chuẩn OK, USAGE_ERROR, EXECUTION_ERROR và AVAILABILITY_ERROR.
- [CommandExecutionException API 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutionException.html) — exception có thể mang mã lỗi cụ thể từ Spring Shell 4.0.2.
- [Spring Boot Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html) — ExitCodeGenerator, SpringApplication.exit() và cách trả mã cho tiến trình bằng System.exit().
