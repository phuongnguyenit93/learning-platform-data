# Gọi phương thức xử lý rồi chuyển kết quả thành nội dung hiển thị

## 1. Luồng từ câu lệnh đến kết quả

Một command thường bắt đầu bằng dòng văn bản do người dùng nhập, ví dụ `product show SKU-001`. Spring Shell phân tích dòng lệnh, tìm command tương ứng, chuyển các đối số và option thành tham số Java, rồi gọi phương thức xử lý. Sau khi phương thức hoàn tất, kết quả được đưa ra shell để người dùng đọc.

Trong mô hình annotation của Spring Shell 4.x, phương thức có `@Command` là điểm vào của nghiệp vụ. Spring Shell tạo một command adapter cho phương thức đó. Adapter nhận `CommandContext`, ánh xạ dữ liệu đầu vào vào các tham số phương thức, gọi phương thức trên Spring bean và xử lý kết quả thực thi.

~~~mermaid
flowchart TD
    A[Người dùng nhập command] --> B[CommandParser phân tích input]
    B --> C[CommandRegistry tìm command]
    C --> D[CommandContext chứa input đã phân tích]
    D --> E[MethodInvokerCommandAdapter ánh xạ tham số]
    E --> F[Gọi phương thức @Command]
    F --> G[Phương thức gọi service và xử lý nghiệp vụ]
    G --> H{Kiểu kết quả}
    H -->|Có giá trị trả về| I[Adapter ghi giá trị vào shell output]
    H -->|void| J[Phương thức ghi qua outputWriter]
    I --> K[Command adapter trả ExitStatus]
    J --> K
    K --> L[CommandExecutor chuyển trạng thái cho ShellRunner]
~~~

Điểm cần phân biệt là **giá trị trả về của phương thức command** và **ExitStatus của command** có mục đích khác nhau. Ví dụ, phương thức có thể trả về `String` để hiển thị lời nhắn, trong khi command adapter trả về `ExitStatus` cho bộ thực thi biết thao tác thành công hay thất bại.

## 2. Spring Shell gọi phương thức `@Command` như thế nào?

Ví dụ khai báo một command xem thông tin sản phẩm:

~~~java
package com.example.inventory;

import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProductCommands {

    private final ProductService productService;

    public ProductCommands(ProductService productService) {
        this.productService = productService;
    }

    @Command(
            name = "product show",
            description = "Hiển thị thông tin một sản phẩm",
            group = "Inventory")
    public String show(
            @Argument(index = 0, description = "Mã sản phẩm") String sku) {
        Product product = productService.findBySku(sku);

        return "Mã: " + product.sku()
                + "\nTên: " + product.name()
                + "\nTồn kho: " + product.quantity();
    }
}
~~~

Giả sử người dùng nhập:

~~~text
shell:>product show SKU-001
~~~

Spring Shell thực hiện các bước sau:

1. Phân tích `product show` là tên command và `SKU-001` là argument ở vị trí 0.
2. Tra cứu command đã đăng ký trong `CommandRegistry`.
3. Đưa giá trị argument vào tham số `sku` theo khai báo `@Argument`.
4. Gọi phương thức `show(...)` trên bean `ProductCommands` do Spring quản lý.
5. Phương thức gọi `ProductService` để lấy dữ liệu, sau đó tạo chuỗi kết quả.
6. Giá trị `String` trả về được ghi vào output của shell.

Kết quả minh họa:

~~~text
Mã: SKU-001
Tên: Bàn phím cơ
Tồn kho: 18
~~~

Lớp command không cần tự phân tích chuỗi `product show SKU-001`. Spring Shell đảm nhiệm việc tìm command và ánh xạ argument vào tham số. Phương thức có thể tập trung vào việc gọi service và quyết định nội dung cần hiển thị.

## 3. Phương thức trả về giá trị: shell hiển thị kết quả

Với command khai báo bằng annotation, nếu phương thức trả về một giá trị, Spring Shell đưa giá trị đó ra shell output. Với thông báo đơn giản, `String` là kiểu trả về dễ kiểm soát và dễ đọc nhất.

~~~java
@Command(name = "hello", description = "Chào người dùng")
public String hello(
        @Option(longName = "name", defaultValue = "bạn") String name) {
    return "Xin chào, " + name + "!";
}
~~~

Khi gọi `hello --name=Lan`, shell hiển thị:

~~~text
Xin chào, Lan!
~~~

Có thể trả về một số kiểu dữ liệu khác nếu nội dung của chúng phù hợp với mục đích hiển thị. Tuy nhiên, với kết quả nghiệp vụ phức tạp, không nên phụ thuộc vào cách `toString()` mặc định của một đối tượng để tạo giao diện ổn định. Hãy chủ động định dạng thành chuỗi có nhãn, thứ tự và cách xuống dòng rõ ràng.

Ví dụ, thay vì trả về trực tiếp một đối tượng `Product` có thể tạo chuỗi hiển thị:

~~~java
@Command(name = "product status")
public String status() {
    Product product = productService.findFeaturedProduct();
    return "Sản phẩm: " + product.name()
            + "\nMã: " + product.sku()
            + "\nSố lượng: " + product.quantity();
}
~~~

Kết quả trả về là nội dung dành cho người sử dụng CLI. Nếu command cần trả dữ liệu cho một hệ thống khác tiêu thụ, cần định nghĩa định dạng đầu ra ổn định và xử lý mã thoát riêng; không nên xem dòng chữ được in ra là giao thức dữ liệu mặc định.

## 4. Phương thức `void`: chủ động ghi nội dung qua CommandContext

Nếu phương thức trả về `void`, không có giá trị trả về để Spring Shell hiển thị tự động. Trong trường hợp này, command có thể nhận `CommandContext` và ghi nội dung qua `outputWriter()`.

~~~java
import java.io.PrintWriter;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;

@Command(name = "product list", description = "Liệt kê sản phẩm")
public void list(CommandContext context) {
    PrintWriter writer = context.outputWriter();

    writer.println("SKU-001  Bàn phím cơ  18");
    writer.println("SKU-002  Chuột không dây  32");
    writer.flush();
}
~~~

`CommandContext` chứa thông tin của lần gọi hiện tại. Trong Spring Shell 4.x, context cung cấp các thành phần như:

- `parsedInput()`: dữ liệu dòng lệnh sau khi đã được phân tích.
- `commandRegistry()`: registry chứa các command của ứng dụng.
- `outputWriter()`: `PrintWriter` để ghi nội dung ra shell.
- `inputReader()`: thành phần đọc dữ liệu nhập trong phiên shell.
- Các phương thức `getOptionByName(...)`, `getOptionByLongName(...)`, `getOptionByShortName(...)` và `getArgumentByIndex(...)` để tự đọc option hoặc argument đã phân tích khi command cần truy cập dữ liệu qua context.

Đối với command annotation, nên khai báo `@Option` và `@Argument` trên tham số phương thức khi muốn Spring Shell ánh xạ đầu vào trực tiếp. `CommandContext` hữu ích khi cần đọc thông tin runtime hoặc ghi output tùy chỉnh.

Nên dùng `PrintWriter` từ context thay vì ghi trực tiếp bằng `System.out`, vì writer này gắn với cơ chế output của shell và dễ kiểm soát hơn trong kiểm thử. Gọi `flush()` sau khi ghi để bảo đảm nội dung được đẩy ra luồng output khi cần.

## 5. Chọn giữa return value và outputWriter

Hai cách đều có thể đưa kết quả ra terminal, nhưng phù hợp với các tình huống khác nhau.

| Nhu cầu | Cách nên dùng | Lý do |
|---|---|---|
| Trả một thông báo ngắn hoặc kết quả tính toán | Phương thức trả `String` hoặc giá trị phù hợp | Mã ngắn, kết quả tập trung tại câu lệnh `return`. |
| Trình bày nhiều dòng theo từng bước | `void` và `CommandContext.outputWriter()` | Có thể ghi từng phần trong lúc xử lý. |
| In bảng hoặc danh sách dài | `outputWriter()` kết hợp logic định dạng | Chủ động căn cột, tiêu đề và cách xuống dòng. |
| Cần hiển thị tiến trình khi tác vụ đang chạy | `outputWriter()` | Có thể ghi và flush nhiều lần trong quá trình xử lý. |
| Tạo output cần kiểm soát chính xác | Tạo chuỗi đã định dạng hoặc dùng writer | Chủ động về nhãn, thứ tự trường và định dạng. |

Không nên vừa `return` một kết quả vừa ghi lại cùng nội dung qua `outputWriter()`, vì người dùng có thể nhìn thấy dữ liệu lặp hai lần. Hãy chọn một đường xuất kết quả chính cho mỗi command.

## 6. Phân biệt kết quả hiển thị với ExitStatus

Trong Spring Shell 4.x, hợp đồng thực thi ở tầng `Command` là:

~~~java
ExitStatus execute(CommandContext commandContext) throws Exception;
~~~

`ExitStatus` mô tả trạng thái thực thi của command, bao gồm mã và mô tả. Nó không phải chuỗi kết quả mà người dùng muốn xem. Với command khai báo bằng annotation, `MethodInvokerCommandAdapter` thực hiện lời gọi phương thức và chuyển kết quả thực thi thành hợp đồng `Command`; `CommandExecutor` nhận `ExitStatus` từ command.

Ví dụ về sự khác nhau:

~~~java
@Command(name = "stock check")
public String checkStock() {
    return "Tồn kho còn đủ hàng";
}
~~~

Ở đây:

- `"Tồn kho còn đủ hàng"` là giá trị trả về của phương thức, được dùng làm nội dung hiển thị.
- `ExitStatus` là trạng thái do command adapter trả cho `CommandExecutor` để thể hiện việc thực thi thành công hay có lỗi.

Nếu tự tạo command bằng `AbstractCommand`, bạn trực tiếp triển khai `doExecute(CommandContext)` và trả về `ExitStatus`:

~~~java
@Bean
Command stockCheckCommand(StockService stockService) {
    return new AbstractCommand("stock check", "Kiểm tra tồn kho") {
        @Override
        public ExitStatus doExecute(CommandContext context) {
            int quantity = stockService.availableQuantity();
            println("Số lượng khả dụng: " + quantity, context);
            return ExitStatus.OK;
        }
    };
}
~~~

Với cách programmatic này, `println(...)` ghi nội dung và `ExitStatus.OK` báo command hoàn tất thành công. Đây là một mô hình khác với phương thức annotation trả `String`, dù cả hai cuối cùng đều được đưa về hợp đồng `Command` để shell thực thi.

## 7. Xử lý ngoại lệ trong quá trình gọi phương thức

Phương thức command có thể gặp lỗi khi gọi service, đọc tệp, truy cập cơ sở dữ liệu hoặc giao tiếp với hệ thống bên ngoài. Nếu ngoại lệ thoát khỏi phương thức, quá trình thực thi command sẽ đi vào nhánh lỗi.

Với Spring Shell 4.x, có thể dùng `ExitStatusExceptionMapper` để chuyển ngoại lệ thành `ExitStatus` có mã và mô tả phù hợp. Mapper có thể được khai báo thành Spring bean và tham chiếu theo tên trong `@Command`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper commandErrorMapper() {
        return exception -> {
            if (exception instanceof ProductNotFoundException) {
                return new ExitStatus(4, "Không tìm thấy sản phẩm");
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Gắn mapper vào command:

~~~java
@Command(
        name = "product show",
        description = "Hiển thị thông tin sản phẩm",
        exitStatusExceptionMapper = "commandErrorMapper")
public String show(@Argument(index = 0) String sku) {
    Product product = productService.findBySku(sku);
    return "Sản phẩm: " + product.name();
}
~~~

Trong ứng dụng thực tế, nên phân biệt lỗi người dùng có thể xử lý, chẳng hạn mã sản phẩm không tồn tại hoặc dữ liệu nhập sai, với lỗi hạ tầng như mất kết nối cơ sở dữ liệu. Không hiển thị stack trace hoặc thông tin bí mật như thông tin kết nối và token cho người dùng cuối. Có thể ghi chi tiết kỹ thuật vào log và trả về thông báo ngắn gọn cùng mã trạng thái phù hợp.

Mapper quyết định `ExitStatus`; nếu muốn in thêm hướng dẫn cụ thể ra terminal, hãy chủ động ghi thông báo bằng output writer ở nơi phù hợp hoặc tổ chức lớp xử lý lỗi theo quy ước thống nhất của ứng dụng.

## 8. Định dạng nội dung hiển thị

Kết quả command nên được thiết kế theo người đọc. Một thông báo đơn giản có thể chỉ cần một dòng. Khi hiển thị dữ liệu nghiệp vụ, nên giữ thứ tự trường nhất quán và dùng nhãn để tránh gây nhầm lẫn.

Ví dụ định dạng một sản phẩm:

~~~java
private String formatProduct(Product product) {
    return "Mã sản phẩm : " + product.sku() + "\n"
            + "Tên         : " + product.name() + "\n"
            + "Tồn kho     : " + product.quantity() + "\n"
            + "Trạng thái  : " + product.status();
}
~~~

Nếu kết quả gồm nhiều bản ghi, cần tránh nối chuỗi tùy tiện trong nhiều lớp nghiệp vụ. Hãy tách phần định dạng thành một phương thức riêng hoặc một formatter chuyên trách để có thể thay đổi cách trình bày mà không sửa quy tắc nghiệp vụ.

Một số nguyên tắc hữu ích:

- Đưa đơn vị đo vào output, ví dụ `18 sản phẩm`, `2.5 GB` hoặc `350 ms`.
- Dùng nhãn rõ ràng cho các giá trị dễ nhầm lẫn.
- Với danh sách dài, in tiêu đề cột và căn chỉnh cột nhất quán.
- Khi không có dữ liệu, hiển thị trạng thái rỗng rõ nghĩa thay vì để output trống.
- Giữ output dành cho máy đọc ổn định nếu command được gọi từ script; tránh thêm banner hoặc dòng trang trí vào định dạng mà script đang phân tích.
- Không đưa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào kết quả thông thường.

## 9. Kiểm thử phương thức xử lý và nội dung output

Nên kiểm tra riêng hai phần: nghiệp vụ do service thực hiện và hành vi của command khi gọi service rồi tạo output.

Với command Spring Shell, có thể sử dụng các tiện ích kiểm thử của Spring Shell như `@ShellTest`, `ShellTestClient` và `ShellAssertions` để gửi command và kiểm tra nội dung hiển thị. Ví dụ minh họa:

~~~java
@SpringBootApplication
class InventoryApplication {

    @Command(name = "hello")
    public String hello() {
        return "Hello from shell";
    }
}

@ShellTest
@ContextConfiguration(classes = InventoryApplication.class)
class GreetingCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void shouldDisplayGreeting() throws Exception {
        ShellScreen screen = client.sendCommand("hello");

        ShellAssertions.assertThat(screen)
                .containsText("Hello from shell");
    }
}
~~~

Kiểm thử nên bao gồm:

1. Gọi command với đầu vào hợp lệ và xác nhận phương thức xử lý được thực thi.
2. Kiểm tra nội dung trả về được hiển thị đúng, bao gồm xuống dòng và nhãn.
3. Với command dùng `outputWriter()`, xác nhận toàn bộ nội dung đã được ghi ra shell.
4. Giả lập service ném ngoại lệ và xác nhận lỗi được chuyển thành thông báo hoặc `ExitStatus` theo cấu hình.
5. Kiểm tra trường hợp không tìm thấy dữ liệu và trường hợp danh sách rỗng.

Khi kiểm thử toàn bộ ứng dụng Spring Boot, cần chọn chế độ shell phù hợp để runner không chờ nhập liệu tương tác trong môi trường test tự động. Các bài kiểm thử command riêng bằng `ShellTestClient` giúp gửi nhiều lệnh trong cùng test context và xác nhận màn hình sau từng lần gọi.

## 10. Quy trình triển khai một command có output rõ ràng

Khi tạo command mới, có thể áp dụng trình tự sau:

1. Xác định dữ liệu đầu vào mà người dùng cung cấp và khai báo bằng `@Argument` hoặc `@Option`.
2. Gọi service nghiệp vụ từ phương thức command; giữ các quy tắc nghiệp vụ ở service.
3. Chọn kiểu trả về. Dùng `String` khi chỉ cần trả một kết quả hiển thị; dùng `void` và `CommandContext.outputWriter()` khi cần ghi nhiều phần hoặc điều khiển luồng output.
4. Định dạng dữ liệu thành thông báo có nhãn, đơn vị và thứ tự trường rõ ràng.
5. Quy định cách xử lý ngoại lệ và mã `ExitStatus` để script có thể nhận biết thành công hoặc thất bại.
6. Kiểm thử cả nội dung hiển thị lẫn trạng thái thực thi.

## Kết luận

Spring Shell 4.x phân tích dòng lệnh, tìm command và gọi phương thức xử lý thông qua command adapter. Với phương thức `@Command`, giá trị trả về được đưa ra shell output; phương thức `void` có thể chủ động ghi qua `CommandContext.outputWriter()`. `ExitStatus` là trạng thái thực thi của command, tách biệt với nội dung người dùng nhìn thấy. Khi phân chia rõ nghiệp vụ, định dạng output và trạng thái kết thúc, command sẽ dễ đọc, dễ kiểm thử và đáng tin cậy khi chạy tương tác hoặc trong script.

## Tài liệu tham khảo

- [Spring Shell 4.x – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.x – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.x – Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell 4.x – Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell 4.x – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.x API – MethodInvokerCommandAdapter](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html)
- [Spring Shell 4.x API – CommandExecutor](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html)
- [Spring Shell 4.x – Testing](https://docs.spring.io/spring-shell/reference/testing.html)
