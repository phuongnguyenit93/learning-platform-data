# CommandRegistration.builder và bean đăng ký lệnh trong Spring Shell 3.x

## 1. Mô hình đăng ký command bằng mã

Spring Shell 3.x cung cấp hai cách chính để định nghĩa command: khai báo bằng annotation trên phương thức và đăng ký bằng API. Bài này tập trung vào cách thứ hai, trong đó **CommandRegistration** mô tả một command và **CommandRegistration.builder()** tạo đối tượng đăng ký theo từng bước.

Một `CommandRegistration` mô tả những thông tin như tên command, mô tả, nhóm, option, alias, điều kiện khả dụng và đích thực thi (target). Sau khi được tạo, registration được đưa vào **CommandCatalog** để shell có thể tìm và thực thi command.

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| `CommandRegistration` | Đối tượng mô tả một command và cách command nhận dữ liệu, gọi xử lý. |
| `CommandRegistration.Builder` | API dạng fluent để khai báo command, option, target và metadata trước khi gọi `build()`. |
| `CommandContext` | Cung cấp dữ liệu đã phân tích và các thành phần runtime cho target trong một lần gọi. |
| `CommandCatalog` | Lưu các registration hiện có; hỗ trợ đăng ký và hủy đăng ký command. |
| Spring `@Bean` | Cho phép Spring quản lý vòng đời của `CommandRegistration`; Spring Shell Boot tự đưa các bean này vào catalog. |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[CommandRegistration.builder] --> B[Khai báo tên và metadata]
    B --> C[Khai báo option và target]
    C --> D[build tạo CommandRegistration]
    D --> E[Spring bean hoặc CommandCatalog.register]
    E --> F[CommandCatalog]
    G[Người dùng nhập command] --> H[Parser phân tích input]
    F --> H
    H --> I[Target nhận CommandContext]
    I --> J[Phương thức hoặc Function/Consumer]
    J --> K[Output và trạng thái thực thi]
~~~

Các ví dụ trong bài sử dụng API `org.springframework.shell.command` của Spring Shell 3.x, đặc biệt phù hợp với nhánh 3.1–3.4. Cần kiểm tra đúng phiên bản dependency đang dùng vì một số API cũ hơn có thể khác.

## 2. Tạo CommandRegistration bằng builder

Điểm bắt đầu là gọi phương thức tĩnh `CommandRegistration.builder()`. Builder cho phép ghép các cấu hình bằng chuỗi lời gọi và kết thúc bằng `build()` để tạo `CommandRegistration`.

Ví dụ nhỏ nhất:

~~~java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
        .command("hello")
        .description("Gửi lời chào")
        .build();
~~~

Ở đây, `command("hello")` đặt tên command và `description(...)` cung cấp mô tả. Registration này chưa khai báo target nên chưa đủ để thực hiện một hành động hữu ích. Một command thực tế cần có target để Spring Shell biết phải gọi phần xử lý nào.

### Tên command và nhóm

Phương thức `command(String... commands)` nhận một hoặc nhiều phần tên. Ví dụ:

~~~java
.command("product show")
~~~

hoặc:

~~~java
.command("product", "show")
~~~

Hai cách trên đều tạo command có tên đầy đủ `product show`. Có thể tổ chức các thao tác thành nhóm lệnh cha/con như `product list`, `product show` và `product delete`. `group("Inventory")` đặt nhóm hiển thị trong phần trợ giúp; nhóm là metadata trình bày, còn các từ trong `command(...)` mới xác định cú pháp người dùng nhập.

Một số cấu hình cấp command thường dùng:

| Phương thức builder | Ý nghĩa |
|---|---|
| `command(...)` | Khai báo tên command và các phần tên con. |
| `description(...)` | Mô tả ngắn của command. |
| `group(...)` | Nhóm command trong trợ giúp. |
| `hidden()` hoặc `hidden(true)` | Ẩn command khỏi danh sách trợ giúp thông thường. |
| `interactionMode(...)` | Giới hạn chế độ tương tác mà command hỗ trợ. |
| `availability(...)` | Cung cấp điều kiện để xác định command có sẵn ở trạng thái hiện tại hay không. |
| `defaultOptionNameModifier(...)` | Áp dụng quy tắc chuẩn hóa tên option dài cho command. |

Không nên đặt tên command quá chung chung như `run` hoặc `do`. Một tên có ngữ cảnh, chẳng hạn `product show`, giúp người dùng hiểu mục đích và giảm nguy cơ xung đột khi ứng dụng có nhiều nhóm chức năng.

## 3. Khai báo target: nơi command thực hiện công việc

`withTarget()` mở phần cấu hình target. Spring Shell 3.x hỗ trợ ba loại target chính:

- **method:** gọi một phương thức trên một đối tượng Java có sẵn.
- **function:** gọi `Function<CommandContext, ?>`; giá trị trả về được hiển thị trong shell.
- **consumer:** gọi `Consumer<CommandContext>`; target không có giá trị trả về, vì vậy có thể ghi output thông qua context.

Sau khi cấu hình target, gọi `and()` để quay về builder chính và tiếp tục khai báo option hoặc metadata khác.

### Function target

Ví dụ command `hello` đọc option `name` và trả về một chuỗi:

~~~java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
        .command("hello")
        .description("Gửi lời chào")
        .withTarget()
            .function(context -> {
                String name = context.getOptionValue("name");
                return "Xin chào, " + name + "!";
            })
            .and()
        .build();
~~~

Function nhận `CommandContext`, đọc dữ liệu đã phân tích và trả kết quả. Spring Shell đưa giá trị trả về ra output của shell. Trong ứng dụng thực tế, function nên gọi service nghiệp vụ thay vì tự chứa truy vấn cơ sở dữ liệu hoặc logic xử lý phức tạp.

### Consumer target

Khi muốn chủ động ghi nội dung và không cần trả một giá trị, dùng consumer:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("system status")
        .description("Hiển thị trạng thái hệ thống")
        .withTarget()
            .consumer(context -> {
                context.getTerminal().writer()
                        .println("Hệ thống đang hoạt động");
            })
            .and()
        .build();
~~~

Consumer phù hợp với thao tác cần ghi nhiều dòng hoặc chủ động điều khiển cách trình bày. Vì consumer không trả kết quả, hãy bảo đảm phần xử lý ghi output một cách rõ ràng.

### Method target

Nếu đã có một phương thức trong POJO hoặc service, có thể tham chiếu trực tiếp phương thức đó thay vì viết lại logic trong lambda:

~~~java
import org.springframework.stereotype.Component;

@Component
public class GreetingHandler {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Đăng ký phương thức:

~~~java
@Bean
CommandRegistration helloCommand(GreetingHandler handler) {
    return CommandRegistration.builder()
            .command("hello")
            .withOption()
                .longNames("name")
                .type(String.class)
                .required()
                .and()
            .withTarget()
                .method(handler, "greet", String.class)
                .and()
            .build();
}
~~~

`method(bean, methodName, parameterTypes...)` tìm phương thức theo đối tượng và tên phương thức. Có overload nhận trực tiếp đối tượng `java.lang.reflect.Method`. Trong ví dụ, `GreetingHandler` là Spring bean được inject vào phương thức `@Bean`; option `name` được ánh xạ vào tham số `String` của `greet`. Cách này giữ dependency injection trong quyền quản lý của Spring.

## 4. Khai báo option cho command

Option là dữ liệu có tên mà người dùng truyền vào, thường dùng để điều chỉnh hành vi của command. Trong builder, gọi `withOption()` để mở phần cấu hình một option. Có thể khai báo nhiều option bằng cách gọi `withOption()` nhiều lần.

Ví dụ command `hello` nhận option bắt buộc `--name`, đồng thời có tên viết tắt `-n`:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("hello")
        .description("Gửi lời chào đến một người")
        .withOption()
            .longNames("name")
            .shortNames('n')
            .type(String.class)
            .required()
            .description("Tên người được chào")
            .and()
        .withTarget()
            .function(context -> {
                String name = context.getOptionValue("name");
                return "Xin chào, " + name + "!";
            })
            .and()
        .build();
~~~

Người dùng có thể gọi:

~~~text
shell:>hello --name Lan
Xin chào, Lan!

shell:>hello -n Lan
Xin chào, Lan!
~~~

Các cấu hình option thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `longNames("name")` | Tên option dài, gọi bằng `--name`. Có thể khai báo nhiều tên; tên đầu tiên là tên chính. |
| `shortNames('n')` | Tên option ngắn, gọi bằng `-n`. |
| `type(String.class)` | Kiểu dữ liệu mà parser cần chuyển đổi. |
| `required()` hoặc `required(true)` | Bắt buộc người dùng cung cấp option. |
| `required(false)` | Cho phép bỏ qua option. |
| `defaultValue("World")` | Giá trị được sử dụng khi option không được truyền. |
| `description(...)` | Mô tả option trong phần trợ giúp. |
| `label(...)` | Nhãn hiển thị cho giá trị option. |
| `position(...)` | Gợi ý vị trí khi option tham gia ánh xạ dữ liệu theo vị trí. |
| `arity(min, max)` | Giới hạn số lượng giá trị mà option có thể nhận. |

### Option có giá trị mặc định

Nếu option có thể bỏ qua và cần giá trị mặc định, dùng `defaultValue(...)`:

~~~java
.withOption()
    .longNames("name")
    .shortNames('n')
    .type(String.class)
    .defaultValue("World")
    .description("Tên người được chào")
    .and()
~~~

Khi người dùng nhập `hello`, target nhận giá trị `World`. Khi nhập `hello --name Lan`, target nhận `Lan`. Giá trị mặc định là một phần của cấu hình option, giúp target không phải tự xử lý trường hợp thiếu dữ liệu cho một option tùy chọn.

### Option có nhiều giá trị

Option có thể nhận nhiều giá trị, chẳng hạn một danh sách mã sản phẩm. Dùng `arity(min, max)` để giới hạn số giá trị và khai báo kiểu phù hợp, ví dụ `String[].class`:

~~~java
.withOption()
    .longNames("sku")
    .type(String[].class)
    .required()
    .arity(1, 5)
    .description("Từ một đến năm mã sản phẩm")
    .and()
~~~

Với cấu hình này, người dùng phải truyền ít nhất một và nhiều nhất năm giá trị cho option. Hãy chọn arity theo nghiệp vụ và kiểm tra trường hợp thiếu hoặc thừa giá trị.

## 5. Tạo bean CommandRegistration trong Spring

Với ứng dụng Spring Boot sử dụng Spring Shell 3.x starter, cách đơn giản để đăng ký command programmatic là khai báo một bean có kiểu trả về `CommandRegistration`. Auto-configuration của Spring Shell sẽ lấy các registration bean và đưa chúng vào `CommandCatalog`.

Ví dụ hoàn chỉnh cho command hiển thị sản phẩm:

~~~java
package com.example.inventory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class InventoryCommandConfiguration {

    @Bean
    CommandRegistration productShowCommand(ProductService productService) {
        return CommandRegistration.builder()
                .command("product show")
                .description("Hiển thị thông tin sản phẩm")
                .group("Inventory")
                .withOption()
                    .longNames("sku")
                    .shortNames('s')
                    .type(String.class)
                    .required()
                    .description("Mã sản phẩm")
                    .and()
                .withTarget()
                    .function(context -> {
                        String sku = context.getOptionValue("sku");
                        Product product = productService.findBySku(sku);
                        return "Mã: " + product.sku()
                                + "\nTên: " + product.name()
                                + "\nTồn kho: " + product.quantity();
                    })
                    .and()
                .build();
    }
}
~~~

Trong ví dụ này:

1. Spring gọi phương thức `productShowCommand(...)` khi tạo bean và inject `ProductService`.
2. Builder tạo registration có tên `product show`, mô tả và nhóm `Inventory`.
3. Option `sku` được khai báo là bắt buộc, có tên ngắn `-s` và kiểu `String`.
4. Function target đọc giá trị `sku`, gọi service và trả chuỗi thông tin sản phẩm.
5. `build()` tạo đối tượng `CommandRegistration` để Spring quản lý.

Sau khi ứng dụng khởi động, người dùng có thể gọi:

~~~text
shell:>product show --sku SKU-001
Mã: SKU-001
Tên: Bàn phím cơ
Tồn kho: 18
~~~

Bạn không cần tự gọi `catalog.register(...)` cho bean này trong ứng dụng Spring Boot đã bật auto-configuration. Nếu vừa khai báo bean vừa đăng ký thủ công cùng một registration, có thể tạo đăng ký trùng hoặc xung đột tên.

## 6. Dùng CommandRegistration.BuilderSupplier và CommandRegistrationCustomizer

Khi nhiều command dùng chung quy ước, Spring Shell 3.x cung cấp **CommandRegistration.BuilderSupplier** để lấy builder mới. Trong ứng dụng Boot, supplier mặc định được cấu hình để mỗi lần gọi `get()` trả về một builder riêng, nhờ đó các command không dùng chung trạng thái cấu hình.

Ví dụ inject supplier vào phương thức tạo bean:

~~~java
@Bean
CommandRegistration auditStatusCommand(
        CommandRegistration.BuilderSupplier builderSupplier) {

    return builderSupplier.get()
            .command("audit status")
            .description("Hiển thị trạng thái kiểm toán")
            .group("Audit")
            .withTarget()
                .function(context -> "Audit service is ready")
                .and()
            .build();
}
~~~

BuilderSupplier hữu ích khi muốn tận dụng cấu hình builder mặc định của ứng dụng. `CommandRegistrationCustomizer` là extension point để điều chỉnh builder tập trung, ví dụ áp dụng quy ước chung cho option hoặc metadata. Nếu tự định nghĩa một bean BuilderSupplier, auto-configuration sẽ nhường quyền cung cấp supplier mặc định để ứng dụng kiểm soát hành vi này.

Không cần tạo BuilderSupplier riêng nếu ứng dụng chỉ có một vài command đơn giản. Dùng builder trực tiếp vẫn rõ ràng và ít cấu hình hơn.

## 7. Đăng ký command động qua CommandCatalog

Bean `CommandRegistration` phù hợp với command có mặt trong suốt vòng đời ứng dụng. Nếu command chỉ nên xuất hiện khi một tính năng được bật hoặc người dùng đã kết nối đến một hệ thống bên ngoài, có thể đăng ký và hủy đăng ký động thông qua **CommandCatalog**.

Ví dụ một command chẩn đoán chỉ được bật trong chế độ hỗ trợ:

~~~java
import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticsCommandManager {

    private final CommandCatalog commandCatalog;
    private CommandRegistration diagnosticsRegistration;

    public DiagnosticsCommandManager(CommandCatalog commandCatalog) {
        this.commandCatalog = commandCatalog;
    }

    public void enableDiagnostics() {
        if (diagnosticsRegistration != null) {
            return;
        }

        diagnosticsRegistration = CommandRegistration.builder()
                .command("system diagnostics")
                .description("Hiển thị thông tin chẩn đoán")
                .withTarget()
                    .function(context -> "Diagnostic mode is enabled")
                    .and()
                .build();

        commandCatalog.register(diagnosticsRegistration);
    }

    public void disableDiagnostics() {
        if (diagnosticsRegistration == null) {
            return;
        }

        commandCatalog.unregister(diagnosticsRegistration);
        diagnosticsRegistration = null;
    }
}
~~~

Điểm quan trọng là lưu lại chính đối tượng registration đã đăng ký để truyền lại cho `unregister(...)`. `CommandCatalog` cũng có overload hủy đăng ký theo tên command. Hãy chọn một cách nhất quán và tránh gỡ nhầm command khác có cùng tên hoặc thuộc thành phần khác quản lý.

Nếu cần xây dựng danh mục command dựa trên nguồn dữ liệu động, Spring Shell còn có `CommandResolver`. Resolver được gọi mỗi khi shell cần phân giải command; vì vậy không nên đặt truy vấn chậm hoặc thao tác mạng tốn thời gian trực tiếp trong `resolve()`, nếu không trải nghiệm nhập lệnh có thể bị chậm.

## 8. Các metadata và cơ chế bổ sung

Ngoài target và option, builder còn có một số phần mở rộng để điều chỉnh hành vi command:

| API | Mục đích |
|---|---|
| `withAlias()` | Khai báo tên thay thế cho command. |
| `withHelpOptions()` | Tùy chỉnh option trợ giúp như `-h` và `--help`. |
| `availability(...)` | Đặt điều kiện command có thể thực thi dựa trên trạng thái ứng dụng. |
| `withErrorHandling()` | Khai báo cách xử lý ngoại lệ cho command. |
| `withExitCode()` | Ánh xạ kết quả thực thi sang mã thoát. |
| `interactionMode(...)` | Xác định command hỗ trợ interactive, non-interactive hoặc cả hai theo enum tương ứng. |
| `hidden()` | Ẩn command khỏi danh sách trợ giúp mặc định. |

Ví dụ alias giúp người dùng gọi một command bằng tên ngắn hơn:

~~~java
CommandRegistration registration = CommandRegistration.builder()
        .command("product list")
        .withAlias()
            .command("products")
            .and()
        .withTarget()
            .function(context -> "Danh sách sản phẩm")
            .and()
        .build();
~~~

Alias là một cách gọi khác của cùng command. Nếu hai thao tác có ý nghĩa hoặc quy tắc nghiệp vụ khác nhau, hãy tạo registration riêng thay vì dùng alias để che giấu sự khác biệt.

## 9. Chọn cách đăng ký phù hợp

| Cách đăng ký | Khi nên dùng | Đặc điểm |
|---|---|---|
| `@Bean CommandRegistration` | Command tồn tại ổn định trong ứng dụng | Spring quản lý bean; Spring Shell Boot tự đưa registration vào catalog. |
| Inject `BuilderSupplier` rồi gọi `get()` | Nhiều command dùng chung cơ chế tạo builder | Nhận builder mới theo cấu hình mặc định hoặc supplier tùy chỉnh. |
| `CommandCatalog.register/unregister` | Command xuất hiện hoặc biến mất theo trạng thái runtime | Chủ động điều khiển vòng đời registration. |
| `CommandCatalogCustomizer` | Cần điều chỉnh catalog tập trung trong quá trình cấu hình | Spring Shell gọi customizer để ứng dụng bổ sung hoặc thay đổi registration. |
| `CommandResolver` | Danh sách command được tính từ trạng thái hoặc nguồn dữ liệu động | Resolver được gọi khi cần phân giải command; cần tránh xử lý chậm. |

Với phần lớn ứng dụng, hãy bắt đầu bằng `@Bean CommandRegistration`. Chỉ chuyển sang catalog động khi tập command thực sự thay đổi trong thời gian chạy. Điều này làm cho vòng đời command dễ hiểu và giảm nguy cơ đăng ký trùng.

## 10. Lỗi thường gặp

**Quên gọi `build()`:** các lời gọi builder mới chỉ cấu hình registration. Phải gọi `build()` để tạo đối tượng cuối cùng trước khi trả về bean hoặc truyền vào catalog.

**Quên khai báo target:** command có tên và mô tả nhưng không có target sẽ không thực hiện được công việc mong muốn. Kiểm tra đã gọi `withTarget()` và hoàn tất bằng `.and()` hay chưa.

**Option không có kiểu phù hợp:** nếu target cần số nguyên, boolean, enum hoặc mảng, hãy khai báo `.type(...)` phù hợp để parser chuyển đổi giá trị chính xác.

**Không đọc đúng tên option:** `getOptionValue("name")` dùng tên option logic, không kèm tiền tố `--` hoặc `-`. Tên dài và tên ngắn là cách người dùng nhập cùng một option.

**Dùng `required()` cùng `defaultValue(...)` mà không có chủ đích:** option bắt buộc và option có giá trị mặc định thể hiện hai chính sách đầu vào khác nhau. Hãy xác định rõ người dùng có được phép bỏ qua option hay không.

**Đăng ký trùng:** registration bean đã được auto-configuration đưa vào catalog. Không đăng ký lại cùng registration bằng một customizer hoặc đoạn code khởi tạo khác.

**Dùng target consumer nhưng không ghi output:** consumer không trả kết quả. Nếu muốn người dùng nhìn thấy kết quả, cần ghi qua terminal trong `CommandContext`.

**Dùng API 3.x trong dự án 4.x:** Spring Shell 4.x đã thay đổi mô hình programmatic command. `CommandRegistration` và `CommandCatalog` của 3.x được thay bằng mô hình `Command` và `CommandRegistry` trong 4.x. Không sao chép nguyên ví dụ của bài này vào project 4.x mà chưa chuyển đổi API.

## 11. Quy trình triển khai một command programmatic

Khi tạo command bằng mã, có thể làm theo trình tự sau:

1. Chọn tên command, nhóm và mô tả theo hành động nghiệp vụ.
2. Xác định dữ liệu đầu vào và khai báo từng option bằng `withOption()`.
3. Chọn target phù hợp: `method`, `function` hoặc `consumer`.
4. Dùng `build()` để tạo `CommandRegistration`.
5. Trả registration từ một Spring `@Bean` nếu command có vòng đời ổn định.
6. Dùng `CommandCatalog` khi cần thêm hoặc gỡ command theo trạng thái runtime.
7. Kiểm tra command bằng trợ giúp, gọi với dữ liệu hợp lệ, dữ liệu thiếu và dữ liệu sai kiểu.

## Kết luận

Trong Spring Shell 3.x, `CommandRegistration.builder()` cung cấp cách định nghĩa command theo từng bước: đặt tên, mô tả, nhóm, option và target, sau đó gọi `build()`. Đăng ký đối tượng này thành Spring bean là cách phù hợp cho command tồn tại ổn định trong ứng dụng Spring Boot; `CommandCatalog` hỗ trợ đăng ký và hủy đăng ký khi trạng thái runtime thay đổi. Hiểu rõ vai trò của registration, target và catalog giúp tổ chức command rõ ràng, dễ kiểm thử và dễ bảo trì.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Programmatic Registration](https://docs.spring.io/spring-shell/reference/3.4/commands/registration/programmatic.html)
- [Spring Shell 3.4 – Command Registration Builder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html)
- [Spring Shell 3.4 – Command Target API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.TargetSpec.html)
- [Spring Shell 3.4 – Command Catalog](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/commandcatalog.html)
- [Spring Shell 3.4 – Programmatic Options](https://docs.spring.io/spring-shell/reference/3.4/options/basics/programmatic.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
