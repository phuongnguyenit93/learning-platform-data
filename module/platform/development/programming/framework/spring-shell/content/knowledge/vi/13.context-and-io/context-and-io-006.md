# Trả về kết quả từ phương thức xử lý so với ghi đầu ra trực tiếp

Một command Spring Shell có thể tạo nội dung hiển thị theo hai cách. Cách thứ nhất là trả về một giá trị từ phương thức xử lý để Spring Shell chuyển giá trị đó qua cơ chế xử lý kết quả. Cách thứ hai là ghi nội dung trực tiếp vào terminal bằng writer của JLine. Hai cách đều có thể đưa thông tin tới người dùng, nhưng chúng khác nhau về luồng thực thi, khả năng định dạng, kiểm thử và cách xử lý kết quả.

Nếu command chỉ cần hiển thị một kết quả cuối cùng như tên khách hàng, tổng tiền hoặc danh sách đã định dạng, trả về giá trị thường là cách đơn giản nhất. Nếu command cần hiển thị nhiều thông báo theo tiến trình, cập nhật trạng thái hoặc điều khiển thời điểm ghi và flush, ghi trực tiếp vào terminal phù hợp hơn.

Spring Shell 3.3 có cơ chế ResultHandler để xử lý giá trị trả về. Với kiểu dữ liệu thông thường, DefaultResultHandler là handler dự phòng và sử dụng Object.toString(). Với kiểu dữ liệu đặc biệt, Spring Shell có các handler riêng, ví dụ cho AttributedCharSequence, TerminalSizeAware và lỗi. Nếu cần giao diện riêng cho một kiểu kết quả nghiệp vụ, ứng dụng có thể đăng ký ResultHandler<T> tương ứng.

Bài này giúp bạn:

- Mô tả luồng xử lý một giá trị trả về trong Spring Shell.
- Phân biệt kết quả trả về với nội dung ghi trực tiếp vào terminal.
- Chọn kiểu trả về phù hợp cho command chỉ có một kết quả cuối.
- Dùng Terminal.writer() hoặc CommandContext.getTerminal() để ghi output.
- Dùng PrintWriter.flush() đúng lúc khi cần hiển thị nội dung ngay.
- Tránh in trùng khi vừa ghi trực tiếp vừa trả về một giá trị.
- Tùy chỉnh cách hiển thị một kiểu kết quả bằng ResultHandler.
- Kiểm thử kết quả đã render và output được ghi trực tiếp.
- Phân biệt thông báo hiển thị với exit code của command.

> Ví dụ dùng Spring Shell 3.3.x và JLine 3.x. Các API CommandContext, ResultHandler, DefaultResultHandler và ResultHandlerService được tham chiếu theo Javadoc Spring Shell 3.3.0; phần ghi output theo tài liệu Spring Shell 3.3.4.

## 1. Hai cách tạo output của một command

Giả sử người dùng chạy:

~~~text
orders total --id 1024
~~~

Command cần hiển thị tổng tiền của đơn hàng. Có thể trả về một chuỗi:

~~~java
@ShellComponent
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @ShellMethod(key = "orders total", value = "Hiển thị tổng tiền đơn hàng.")
    public String total(@ShellOption("--id") long orderId) {
        BigDecimal total = orderService.totalOf(orderId);
        return "Tổng tiền: " + total.toPlainString();
    }
}
~~~

Phương thức không tự gọi println. Nó trả về chuỗi. Spring Shell nhận giá trị trả về và chuyển nó tới cơ chế xử lý kết quả để hiển thị.

Một command khác có thể ghi trực tiếp:

~~~java
@ShellComponent
public class ExportCommands {

    private final ExportService exportService;
    private final Terminal terminal;

    public ExportCommands(ExportService exportService, Terminal terminal) {
        this.exportService = exportService;
        this.terminal = terminal;
    }

    @ShellMethod(key = "orders export", value = "Xuất đơn hàng ra file.")
    public void export(@ShellOption("--file") Path file) throws IOException {
        PrintWriter writer = terminal.writer();
        writer.println("Đang chuẩn bị dữ liệu...");
        writer.flush();

        exportService.exportTo(file);

        writer.println("Đã xuất dữ liệu vào " + file);
        writer.flush();
    }
}
~~~

Phương thức có kiểu trả về void. Nó dùng writer của terminal để ghi từng thông báo vào phiên shell. Vì không trả về một kết quả cuối, Spring Shell không cần render thêm giá trị từ phương thức này.

## 2. Luồng xử lý khi phương thức trả về giá trị

Với command trả về một giá trị, luồng xử lý có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Spring Shell parse input và bind tham số]
    B --> C[Gọi method của command]
    C --> D[Method trả về object]
    D --> E[ResultHandlerService]
    E --> F{Tìm ResultHandler phù hợp}
    F -->|Có handler chuyên biệt| G[Handler render theo kiểu kết quả]
    F -->|Không có handler chuyên biệt| H[DefaultResultHandler]
    G --> I[Terminal output]
    H --> I
~~~

ResultHandler<T> là hợp đồng để xử lý kết quả từ lời gọi method. ResultHandlerService nhận kết quả và chọn handler phù hợp. Spring Shell 3.3 cung cấp các handler mặc định trong ResultHandlerConfig.

Một số handler tiêu biểu:

| Kiểu kết quả | Handler | Vai trò |
|---|---|---|
| AttributedCharSequence | AttributedCharSequenceResultHandler | Render nội dung có style của JLine |
| TerminalSizeAware | TerminalSizeAwareResultHandler | Render kết quả có khả năng thích ứng với kích thước terminal |
| Throwable | ThrowableResultHandler | Hiển thị thông báo lỗi |
| Lỗi validation tham số | ParameterValidationExceptionResultHandler | Hiển thị lỗi validation |
| Object thông thường | DefaultResultHandler | Dùng Object.toString() như handler dự phòng |

DefaultResultHandler là lựa chọn cuối cho các object chưa có handler chuyên biệt. Điều đó có nghĩa là nếu trả về một object nghiệp vụ như Order, người dùng có thể thấy chuỗi toString() của object. Chuỗi này thường phục vụ debug hơn là giao diện CLI.

Vì vậy, với một kết quả đơn giản, hãy trả về chuỗi đã định dạng. Với kiểu dữ liệu nghiệp vụ cần hiển thị nhất quán ở nhiều command, hãy cân nhắc một ResultHandler chuyên biệt.

## 3. Khi nào nên trả về kết quả?

Trả về kết quả phù hợp khi command tạo ra một giá trị cuối cùng, có thể biểu diễn như một object:

- Một thông báo xác nhận đã lưu thành công.
- Một số liệu như tổng tiền, số lượng bản ghi hoặc trạng thái.
- Một dòng hoặc bảng đã được định dạng.
- Một object có kiểu mà ứng dụng đã đăng ký result handler.
- Một nội dung có thể được kiểm thử độc lập trước khi render.

Ví dụ service trả về một object kết quả:

~~~java
public record OrderTotal(long orderId, BigDecimal amount, String currency) {
}
~~~

Command có thể chuyển object đó thành chuỗi dễ đọc:

~~~java
@ShellMethod(key = "orders total")
public String total(@ShellOption("--id") long orderId) {
    OrderTotal result = orderService.calculateTotal(orderId);
    return "Đơn hàng %d: %s %s".formatted(
            result.orderId(),
            result.amount().toPlainString(),
            result.currency());
}
~~~

Việc định dạng nằm trong command hoặc một formatter riêng. Service chỉ chịu trách nhiệm nghiệp vụ và trả dữ liệu có cấu trúc.

### Không phụ thuộc vào Object.toString() cho output người dùng

Không nên mặc định rằng mọi object trả về đều được hiển thị theo định dạng phù hợp. Ví dụ:

~~~java
public record Customer(String id, String name, String email) {
}

@ShellMethod(key = "customer find")
public Customer find(@ShellOption("--id") String id) {
    return customerService.findById(id);
}
~~~

Nếu không có handler riêng, handler dự phòng có thể in kết quả tương tự:

~~~text
Customer[id=C102, name=Nguyen An, email=an@example.test]
~~~

Định dạng này bộc lộ cấu trúc Java và có thể thay đổi khi record hoặc class thay đổi. Nếu output là giao diện công khai của CLI, hãy định dạng rõ ràng hoặc viết result handler riêng.

## 4. Khi nào nên ghi trực tiếp vào terminal?

Ghi trực tiếp phù hợp khi command cần kiểm soát thời điểm output xuất hiện:

- Hiển thị thông báo trước khi bắt đầu một thao tác lâu.
- In nhiều dòng theo từng giai đoạn.
- Cập nhật tiến độ hoặc trạng thái khi command đang chạy.
- Hiển thị nội dung mà không cần tạo một object kết quả cuối.
- Dùng API terminal của JLine để ghi style hoặc tương tác với terminal.

Spring Shell 3.3 cho phép lấy terminal từ CommandContext:

~~~java
import java.io.PrintWriter;

import org.jline.terminal.Terminal;
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class MaintenanceCommands {

    @ShellMethod(key = "maintenance rebuild")
    public void rebuild(CommandContext context) {
        Terminal terminal = context.getTerminal();
        PrintWriter writer = terminal.writer();

        writer.println("Bắt đầu xây dựng lại chỉ mục...");
        writer.flush();

        // Thực hiện công việc.

        writer.println("Đã xây dựng lại chỉ mục.");
        writer.flush();
    }
}
~~~

Với command dùng @ShellMethod, cũng có thể inject Terminal qua constructor như ví dụ ở phần đầu. Tài liệu Spring Shell 3.3 minh họa cả hai cách: lấy terminal từ CommandContext hoặc autowire Terminal.

Nếu dùng target kiểu Consumer<CommandContext> trong programmatic registration, consumer không trả về giá trị. Nó có thể lấy terminal từ context và ghi output:

~~~java
CommandRegistration.builder()
        .command("maintenance rebuild")
        .withTarget()
            .consumer(context -> {
                PrintWriter writer = context.getTerminal().writer();
                writer.println("Đang xây dựng lại chỉ mục...");
                writer.flush();
            })
            .and()
        .build();
~~~

Target kiểu Function<CommandContext, ?> thì trả về một giá trị để Spring Shell xử lý như kết quả command. Consumer không có giá trị trả về; nếu cần hiển thị nội dung, consumer tự ghi vào terminal.

## 5. Terminal.writer() và System.out

Có thể ghi trực tiếp ra output của JVM bằng System.out. Tài liệu Spring Shell cũng ghi nhận cách này. Tuy nhiên, trong một command Spring Shell, Terminal.writer() thường là lựa chọn phù hợp hơn vì nó đi qua terminal mà shell đang sử dụng.

| Tiêu chí | Terminal.writer() | System.out |
|---|---|---|
| Gắn với terminal của shell | Có | Ghi vào standard output của JVM |
| Dùng trong CommandContext | Có, qua getTerminal() | Không cần context |
| Tích hợp với JLine terminal | Có | Không trực tiếp |
| Phù hợp với output command | Được khuyến nghị trong tài liệu Spring Shell | Có thể dùng cho output đơn giản hoặc môi trường không cần terminal abstraction |
| Kiểm thử qua terminal giả lập | Phù hợp khi ghi qua terminal được test cung cấp | Có thể đi ra luồng khác với màn hình giả lập |

Nếu trộn System.out và Terminal.writer() trong cùng command, thứ tự hiển thị có thể khó dự đoán do hai writer có bộ đệm và đường đi khác nhau. Hãy chọn một kênh output chính cho command.

Không dùng System.out.println() để thay thế logger. Log vận hành, debug và diagnostic nên đi qua logging framework; output terminal dành cho người đang sử dụng CLI.

## 6. Dùng PrintWriter và flush

Terminal.writer() trả về PrintWriter. Có thể dùng print, println, printf hoặc các phương thức ghi văn bản khác:

~~~java
PrintWriter writer = terminal.writer();

writer.println("Đang kết nối...");
writer.printf("Đã đọc %d bản ghi.%n", count);
writer.flush();
~~~

println ghi nội dung và ký tự xuống dòng. printf cho phép định dạng theo mẫu. flush() yêu cầu đẩy dữ liệu đang được buffer ra writer đích.

### Khi nào cần flush?

Nếu command ghi thông báo rồi tiếp tục thực hiện một thao tác mất thời gian, hãy flush trước thao tác đó để người dùng nhìn thấy thông báo ngay:

~~~java
writer.println("Đang tải dữ liệu...");
writer.flush();

List<Order> orders = orderService.loadAll();

writer.printf("Đã tải %d đơn hàng.%n", orders.size());
writer.flush();
~~~

Không nhất thiết flush sau từng ký tự hoặc từng trường trong một dòng. Với output ngắn, có thể ghi nhiều nội dung rồi flush một lần. Với tiến độ cần hiển thị liên tục, flush ở mỗi mốc tiến độ có ý nghĩa.

## 7. Không ghi trực tiếp rồi lại trả về cùng một thông báo

Một lỗi thường gặp là vừa ghi nội dung qua terminal, vừa trả về một chuỗi chứa chính nội dung đó:

~~~java
@ShellMethod(key = "orders create")
public String create() {
    terminal.writer().println("Đang tạo đơn hàng...");
    terminal.writer().flush();

    Order order = orderService.create();

    return "Đã tạo đơn hàng " + order.id();
}
~~~

Đây có thể là chủ đích nếu command muốn hiển thị tiến trình rồi hiển thị kết quả cuối. Nhưng nếu ghi trực tiếp và trả về cùng một nội dung, người dùng sẽ thấy thông báo lặp:

~~~text
Đã tạo đơn hàng 1024
Đã tạo đơn hàng 1024
~~~

Hãy xác định rõ output nào là tiến trình và output nào là kết quả cuối. Nếu chỉ cần một thông báo cuối, trả về chuỗi. Nếu cần nhiều thông báo trong lúc xử lý, ghi tiến trình trực tiếp và có thể trả về một kết quả cuối khác. Nếu toàn bộ nội dung đã được ghi trực tiếp, dùng void để không tạo thêm result.

## 8. Tùy chỉnh hiển thị bằng ResultHandler

Khi nhiều command trả về cùng một kiểu object và cần cùng một định dạng, có thể đăng ký ResultHandler<T> cho kiểu đó. Spring Shell 3.3 auto-configuration thu thập các bean ResultHandler<?> và đưa chúng vào ResultHandlerService.

Ví dụ, command trả về OrderReport:

~~~java
public record OrderReport(
        long orderId,
        String customerName,
        BigDecimal total,
        String status) {
}
~~~

Handler chịu trách nhiệm render:

~~~java
import java.io.PrintWriter;

import org.jline.terminal.Terminal;
import org.springframework.shell.ResultHandler;
import org.springframework.stereotype.Component;

@Component
public class OrderReportResultHandler implements ResultHandler<OrderReport> {

    private final Terminal terminal;

    public OrderReportResultHandler(Terminal terminal) {
        this.terminal = terminal;
    }

    @Override
    public void handleResult(OrderReport report) {
        PrintWriter writer = terminal.writer();
        writer.println("Đơn hàng: " + report.orderId());
        writer.println("Khách hàng: " + report.customerName());
        writer.println("Tổng tiền: " + report.total().toPlainString());
        writer.println("Trạng thái: " + report.status());
        writer.flush();
    }
}
~~~

Command chỉ cần trả về object:

~~~java
@ShellMethod(key = "orders report")
public OrderReport report(@ShellOption("--id") long orderId) {
    return orderService.report(orderId);
}
~~~

Lúc này method command trả về dữ liệu nghiệp vụ; OrderReportResultHandler đảm nhiệm cách trình bày. Các command khác trả về cùng kiểu OrderReport có thể dùng lại cùng quy tắc render.

Chỉ tạo handler riêng khi kiểu kết quả có định dạng dùng chung hoặc cần xử lý đặc biệt. Với một thông báo đơn giản chỉ dùng một lần, trả về String thường dễ đọc và dễ bảo trì hơn.

## 9. Trả về kết quả và ghi trực tiếp ảnh hưởng đến kiểm thử thế nào?

Với command trả về giá trị, có thể kiểm thử method bằng unit test để xác nhận dữ liệu hoặc chuỗi được tạo đúng. Tuy nhiên, unit test gọi method trực tiếp không chứng minh Spring Shell đã chọn đúng ResultHandler hoặc render đúng terminal.

Với command ghi trực tiếp, gọi method Java và kiểm tra giá trị trả về không có ích vì method có kiểu void. Cần kiểm thử qua terminal giả lập để xác nhận writer đã ghi nội dung đúng.

Spring Shell cung cấp @ShellTest, ShellTestClient và ShellScreen để chạy command và đọc output hiển thị. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class OrderCommandsShellTest {

    @Autowired
    ShellTestClient client;

    @Test
    void displaysTheCommandResult() {
        var session = client.nonInterative("orders total --id 1024").run();

        assertThat(session.screen().lines())
                .anySatisfy(line ->
                        assertThat(line).contains("Tổng tiền:"));
    }
}
~~~

Tên method nonInterative trong API Spring Shell 3.3.0 có cách viết như trên. Khi nâng lên phiên bản mới hơn, hãy kiểm tra API tương ứng vì tên method có thể đã được sửa hoặc deprecated.

Để kiểm tra command ghi trực tiếp, vẫn dùng ShellTestClient và kiểm tra session.screen() sau khi command chạy. Vì output đi qua terminal của shell, test có thể xác nhận thông báo được ghi bởi Terminal.writer().

### Kiểm tra từng lớp riêng

| Điều cần kiểm tra | Cách kiểm thử |
|---|---|
| Service tạo dữ liệu đúng | Unit test service |
| Command trả về đúng object/string | Unit test command method |
| Result handler định dạng đúng | Unit test handler với terminal/writer giả hoặc test hỗ trợ |
| Spring Shell render kết quả đúng | @ShellTest và ShellTestClient |
| Output trực tiếp xuất hiện đúng thứ tự | Test qua terminal giả lập |
| Màu, cursor hoặc layout phức tạp | Test screen/terminal behavior và kiểm tra thủ công trên terminal mục tiêu khi cần |

Không chỉ kiểm tra method trả về một chuỗi rồi kết luận output terminal đã đúng. Kết quả cuối còn phụ thuộc result handler, terminal và cách runner hiển thị.

## 10. Output và exit code là hai vấn đề riêng

Một command có thể in thông báo lỗi nhưng vẫn kết thúc với exit code thành công nếu ứng dụng chỉ trả về một chuỗi thông thường:

~~~java
@ShellMethod(key = "orders delete")
public String delete(@ShellOption("--id") long orderId) {
    if (!orderService.exists(orderId)) {
        return "Không tìm thấy đơn hàng " + orderId;
    }
    orderService.delete(orderId);
    return "Đã xóa đơn hàng " + orderId;
}
~~~

Chuỗi Không tìm thấy... chỉ là nội dung kết quả. Nó không tự động có nghĩa là command thất bại đối với script hoặc CI.

Nếu lỗi cần được biểu diễn như thất bại, hãy dùng exception handling hoặc cơ chế exit-code mapping của Spring Shell. Không dùng màu đỏ, tiền tố ERROR: hay việc ghi ra System.err làm tín hiệu duy nhất cho hệ thống gọi.

Tương tự, command ghi trực tiếp thông báo thành công không tự tạo ra exit code thành công hoặc thất bại theo nội dung thông báo. Output là giao diện cho người đọc; exit status là kết quả điều khiển cho shell script và tiến trình bên ngoài.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Object hiển thị thành chuỗi kiểu Java | Không có result handler riêng, DefaultResultHandler dùng toString() | Trả về chuỗi đã định dạng hoặc đăng ký ResultHandler<T> |
| Thông báo xuất hiện hai lần | Vừa ghi qua terminal vừa trả về cùng nội dung | Chọn một cách cho mỗi phần output; dùng void nếu đã ghi toàn bộ |
| Thông báo tiến trình chỉ xuất hiện sau khi command kết thúc | Writer còn giữ buffer | Gọi flush() sau mốc tiến độ cần hiển thị ngay |
| Output không xuất hiện trong màn hình test | Ghi bằng System.out thay vì terminal giả lập | Dùng Terminal.writer() hoặc kiểm thử đúng luồng standard output |
| Output và log xen lẫn nhau | Dùng nhiều kênh ghi không có quy ước | Dùng terminal cho thông báo người dùng, logger cho log vận hành |
| Test method pass nhưng terminal hiển thị sai | Chỉ kiểm thử giá trị trả về, chưa kiểm thử result handler | Thêm @ShellTest và kiểm tra ShellScreen |
| Bảng/object bị hiển thị bằng toString() | Dùng kiểu dữ liệu không có formatter | Viết formatter hoặc result handler chuyên biệt |
| Thông báo lỗi nhưng CI nhận exit code 0 | Chỉ trả về một chuỗi báo lỗi | Dùng exception resolver hoặc exit-code mapping |
| Thứ tự output không ổn định | Trộn System.out và Terminal.writer() | Dùng một writer chính cho command |
| Tiến trình nền ghi ra terminal sau khi command đã kết thúc | Worker thread giữ writer và tiếp tục ghi | Quản lý vòng đời tác vụ; chỉ ghi khi phiên shell còn hợp lệ |
| Output bị thiếu dòng cuối | Không flush trước khi luồng kết thúc hoặc context đóng | Flush sau nội dung cuối và kiểm tra vòng đời writer |

## 12. Checklist chọn cách xuất output

- Xác định command cần một kết quả cuối hay nhiều thông báo trong lúc xử lý.
- Ưu tiên trả về String hoặc kiểu dữ liệu có formatter khi chỉ cần một kết quả.
- Nhớ rằng Spring Shell chuyển giá trị trả về qua ResultHandlerService.
- Không dựa vào Object.toString() làm giao diện công khai nếu định dạng cần ổn định.
- Dùng ResultHandler<T> khi một kiểu kết quả cần cách render dùng chung.
- Dùng Terminal.writer() hoặc terminal lấy từ CommandContext khi cần ghi trực tiếp.
- Dùng void nếu command đã tự ghi toàn bộ nội dung.
- Gọi flush() sau thông báo tiến trình cần hiển thị ngay.
- Không ghi cùng một thông báo qua terminal rồi trả về lặp lại.
- Không trộn System.out và Terminal.writer() nếu không có lý do rõ ràng.
- Dùng logger cho log kỹ thuật, terminal cho thông tin hướng tới người dùng.
- Kiểm thử output cuối qua @ShellTest và ShellTestClient.
- Kiểm tra exit code riêng với nội dung thông báo.
- Quản lý việc ghi output từ tác vụ bất đồng bộ để tránh ghi sau khi command kết thúc.

## 13. Bài tập thực hành

Xây dựng hai command cho đơn hàng:

1. Tạo command orders total --id <id> trả về chuỗi tổng tiền.
2. Tạo command orders export --file <path> ghi thông báo bắt đầu và hoàn tất qua Terminal.writer().
3. Dùng PrintWriter.flush() sau thông báo bắt đầu để người dùng nhìn thấy trước khi export hoàn tất.
4. Viết unit test cho service tính tổng tiền.
5. Viết unit test cho method orders total để kiểm tra chuỗi trả về.
6. Viết @ShellTest để xác nhận chuỗi kết quả được render trên shell screen.
7. Viết test cho command export để xác nhận hai thông báo xuất hiện qua terminal giả lập.
8. Thử bỏ flush() ở thông báo bắt đầu và quan sát khác biệt trong test hoặc terminal.
9. Tạo record OrderReport và ResultHandler<OrderReport> để hiển thị báo cáo theo nhiều dòng.
10. Cho command trả về OrderReport; xác nhận Spring Shell dùng handler đã đăng ký.
11. Thử trả về object không có handler riêng và quan sát fallback toString().
12. Tạo tình huống không tìm thấy đơn hàng; quyết định đây là kết quả nghiệp vụ bình thường hay lỗi command cần exit code khác.
13. Xác nhận command không vừa ghi trực tiếp vừa trả về cùng một thông báo.

Khi hoàn thành, hãy giải thích vì sao return "Đã xuất file" và terminal.writer().println("Đã xuất file") có luồng xử lý khác nhau, và vì sao một chuỗi có nội dung lỗi không tự động làm command thất bại trong script.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Writing](https://docs.spring.io/spring-shell/reference/3.3/commands/writing.html): ghi output bằng System.out, Terminal.writer() và CommandContext.
- [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): command method trả về giá trị và kết quả được hiển thị trong shell.
- [Spring Shell 3.3.0 – CommandContext API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandContext.html): context của command và phương thức getTerminal().
- [Spring Shell 3.3.0 – ResultHandler API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/ResultHandler.html): hợp đồng xử lý kết quả của method invocation.
- [Spring Shell 3.3.0 – DefaultResultHandler API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/result/DefaultResultHandler.html): handler dự phòng dùng Object.toString().
- [Spring Shell 3.3.0 – ResultHandlerConfig API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/result/ResultHandlerConfig.html): các result handler mặc định.
- [Spring Shell 3.3.0 – SpringShellAutoConfiguration API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/SpringShellAutoConfiguration.html): đăng ký ResultHandlerService từ tập bean ResultHandler.
- [Spring Shell 3.3 – Testing](https://docs.spring.io/spring-shell/reference/3.3/testing.html): kiểm thử command và output qua test support.
