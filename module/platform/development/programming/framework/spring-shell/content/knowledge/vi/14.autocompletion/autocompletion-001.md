# Gợi ý tên lệnh, lệnh con và tùy chọn khi nhấn Tab

## 1. Tự hoàn thành giúp người dùng khám phá command

Trong một ứng dụng CLI có nhiều command, người dùng khó nhớ chính xác tên lệnh, lệnh con và option. Spring Shell tích hợp cơ chế tự hoàn thành (completion) trong shell dựa trên JLine. Khi đang nhập lệnh, người dùng nhấn **Tab** để yêu cầu shell đề xuất phần còn thiếu.

Completion giúp:

- Khám phá những command đã đăng ký.
- Hoàn thành các tên command nhiều từ, chẳng hạn `user create` hoặc `user disable`.
- Gợi ý option hợp lệ của command hiện tại, ví dụ `--email`, `--role` hoặc `--force`.
- Gợi ý giá trị option như môi trường triển khai, trạng thái, enum hoặc tên tệp.
- Giảm lỗi chính tả và giúp người dùng làm quen với cú pháp mà không phải mở tài liệu liên tục.

Spring Shell 4.x có completion mặc định dựa trên nội dung đang nhập. Với những giá trị động hoặc phụ thuộc ngữ cảnh, ứng dụng có thể bổ sung `CompletionProvider` riêng cho command.

## 2. Thử completion trong shell tương tác

Giả sử ứng dụng đăng ký các command:

~~~text
user list
user create
user disable
user enable
~~~

Khi người dùng nhập một phần tên command rồi nhấn Tab, shell có thể hiển thị hoặc hoàn thành các tên phù hợp với tiền tố hiện tại.

| Nội dung đang nhập | Gợi ý có thể nhận được |
|---|---|
| `u` rồi nhấn Tab | Các command bắt đầu bằng `u`, ví dụ `user ...`. |
| `user ` rồi nhấn Tab | Các command có tiền tố `user`, ví dụ `user list`, `user create`, `user disable`. |
| `user cr` rồi nhấn Tab | `user create` nếu đây là kết quả duy nhất phù hợp. |
| `user create --` rồi nhấn Tab | Các option của `user create`, ví dụ `--email`, `--role`. |

Kết quả cụ thể phụ thuộc vào những command đã đăng ký và phần văn bản đang có trong buffer. Nếu chỉ có một kết quả khớp, shell có thể hoàn thành trực tiếp; nếu có nhiều kết quả, shell hiển thị các lựa chọn để người dùng tiếp tục nhập.

### Ví dụ khai báo command có lệnh con

Trong Spring Shell 4.x, có thể khai báo tên command gồm nhiều phần bằng thuộc tính `name` của `@Command`:

~~~java
package com.example.users;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class UserCommands {

    @Command(name = "user list", description = "Liệt kê tài khoản")
    public String list() {
        return "Danh sách tài khoản";
    }

    @Command(name = "user create", description = "Tạo tài khoản mới")
    public String create(
            @Option(longName = "email", required = true) String email,
            @Option(longName = "role", defaultValue = "USER") String role) {
        return "Đã tạo tài khoản " + email + " với vai trò " + role;
    }

    @Command(name = "user disable", description = "Vô hiệu hóa tài khoản")
    public String disable(
            @Option(longName = "id", required = true) long id) {
        return "Đã vô hiệu hóa tài khoản " + id;
    }
}
~~~

Khi các phương thức nằm trong Spring bean và được Spring Shell khám phá, command sẽ xuất hiện trong danh mục command. Cơ chế completion mặc định sử dụng các command đã đăng ký để đề xuất tên phù hợp. Bạn không cần tự viết một provider chỉ để liệt kê lại các tên command tĩnh.

## 3. Gợi ý tên option

Sau khi shell nhận diện được command, completion có thể đề xuất các option được khai báo trên command đó. Ví dụ:

~~~text
shell:>user create --<Tab>
--email
--role
~~~

Các option đến từ metadata của command, vì vậy hãy khai báo tên và mô tả rõ ràng bằng `@Option`:

~~~java
@Command(name = "user create", description = "Tạo tài khoản mới")
public String create(
        @Option(longName = "email", required = true,
                description = "Địa chỉ email của tài khoản") String email,
        @Option(longName = "role", defaultValue = "USER",
                description = "Vai trò của tài khoản") UserRole role) {
    return "Đã tạo tài khoản " + email + " với vai trò " + role;
}
~~~

Completion giúp chọn tên option; trợ giúp (`help user create`) cung cấp mô tả và cú pháp đầy đủ. Hai cơ chế bổ trợ cho nhau: completion hỗ trợ nhập nhanh, còn help giải thích ý nghĩa và cách sử dụng.

## 4. Gợi ý giá trị enum và tên tệp

Spring Shell 4.x có sẵn một số `CompletionProvider` thường dùng:

| Provider | Công dụng |
|---|---|
| `DefaultCompletionProvider` | Hỗ trợ completion mặc định cho option và giá trị của option kiểu enum. |
| `EnumCompletionProvider` | Đề xuất các hằng số của một enum; có thể thêm tiền tố như `--mode` trước giá trị. |
| `FileNameCompletionProvider` | Đề xuất tên tệp và thư mục trên hệ thống tệp hiện tại. |
| `CompositeCompletionProvider` | Kết hợp nhiều provider để trả về một tập đề xuất chung. |

Ví dụ enum mô tả chế độ triển khai:

~~~java
public enum DeployMode {
    ROLLING,
    BLUE_GREEN,
    RECREATE
}
~~~

Khai báo command có option enum:

~~~java
@Command(name = "deploy start", description = "Bắt đầu triển khai")
public String start(
        @Option(longName = "mode", defaultValue = "ROLLING") DeployMode mode) {
    return "Chế độ triển khai: " + mode;
}
~~~

`DefaultCompletionProvider` có thể lấy các giá trị enum từ kiểu tham số để đề xuất khi người dùng đang nhập option tương ứng. Nếu muốn tự cấu hình provider riêng cho enum, có thể dùng `EnumCompletionProvider`:

~~~java
CompletionProvider modeCompletion =
        new EnumCompletionProvider(DeployMode.class, "--mode");
~~~

Provider này tạo các đề xuất gắn với option `--mode`. Không cần kết hợp đồng thời nhiều provider cùng đề xuất một enum nếu điều đó tạo ra các kết quả trùng lặp.

Với option nhận đường dẫn, có thể dùng `FileNameCompletionProvider` để đề xuất tệp và thư mục. Việc hoàn thành đường dẫn giúp giảm lỗi gõ, nhưng ứng dụng vẫn phải kiểm tra quyền truy cập, sự tồn tại và loại tệp trước khi thực hiện thao tác.

## 5. CompletionProvider tùy chỉnh cho giá trị động

Giá trị cần gợi ý đôi khi đến từ cấu hình hoặc dữ liệu đang thay đổi. Ví dụ, command triển khai cần đề xuất các môi trường hiện được phép triển khai như `development`, `staging` và `production`.

Spring Shell 4.x dùng `CompletionProvider` ở cấp command. Đây là functional interface nhận `CompletionContext` và trả về danh sách `CompletionProposal`. Context cho biết command, option hiện tại, các từ đã nhập và vị trí con trỏ. Mỗi proposal chứa nội dung được chèn vào dòng lệnh; có thể bổ sung mô tả hoặc nhóm để hiển thị thông tin hữu ích hơn.

### Khai báo command

~~~java
package com.example.deploy;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeployCommands {

    private final DeployService deployService;

    public DeployCommands(DeployService deployService) {
        this.deployService = deployService;
    }

    @Command(
            name = "deploy start",
            description = "Bắt đầu triển khai ứng dụng",
            group = "Deployment",
            completionProvider = "deployCompletionProvider")
    public String start(
            @Option(longName = "environment", required = true,
                    description = "Môi trường đích") String environment,
            @Option(longName = "mode", defaultValue = "ROLLING",
                    description = "Chiến lược triển khai") DeployMode mode,
            @Option(longName = "config",
                    description = "Đường dẫn tệp cấu hình") String config) {

        DeployReceipt receipt = deployService.start(environment, mode, config);
        return "Đã tạo yêu cầu triển khai " + receipt.requestId();
    }
}
~~~

### Đăng ký provider

~~~java
package com.example.deploy;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.DefaultCompletionProvider;

@Configuration
public class DeployCompletionConfiguration {

    @Bean
    CompletionProvider deployCompletionProvider(EnvironmentCatalog environmentCatalog) {

        CompletionProvider environmentProvider = context -> {
            CommandOption option = context.getCommandOption();

            if (option == null || !"environment".equals(option.longName())) {
                return List.of();
            }

            return environmentCatalog.findDeployableEnvironments().stream()
                    .map(environment -> new CompletionProposal(
                            "--environment=" + environment)
                            .description("Môi trường " + environment))
                    .toList();
        };

        return new CompositeCompletionProvider(
                new DefaultCompletionProvider(),
                environmentProvider);
    }
}
~~~

Trong ví dụ này:

1. `@Command(completionProvider = "deployCompletionProvider")` tham chiếu đến bean provider theo tên.
2. `CompletionContext.getCommandOption()` cho biết option đang được hoàn thành. Nếu context không gắn với option hoặc option hiện tại không phải `environment`, provider tùy chỉnh trả về danh sách rỗng.
3. `EnvironmentCatalog` lấy danh sách môi trường hiện được phép triển khai.
4. Mỗi môi trường được chuyển thành `CompletionProposal`, có nội dung chèn `--environment=<giá-trị>` và mô tả hiển thị.
5. `CompositeCompletionProvider` kết hợp provider tùy chỉnh với `DefaultCompletionProvider`, giữ các gợi ý mặc định cho option và enum.

`EnvironmentCatalog` và `DeployService` là thành phần nghiệp vụ của ứng dụng ví dụ, cần được định nghĩa trong project. Nên giữ truy vấn completion nhanh và chỉ đọc; không khởi chạy triển khai hoặc thay đổi trạng thái chỉ vì người dùng nhấn Tab. Nếu danh sách môi trường cần gọi hệ thống bên ngoài, hãy dùng cache có thời hạn hợp lý và vẫn xác thực lại môi trường trong `DeployService` khi command thực thi.

### Kết quả mong đợi

Khi người dùng nhập:

~~~text
shell:>deploy start --environment=<Tab>
~~~

shell có thể đề xuất các giá trị như:

~~~text
--environment=development
--environment=staging
--environment=production
~~~

Sau đó người dùng chọn một giá trị và tiếp tục nhập `--mode`. Giá trị được đề xuất chỉ giúp nhập nhanh; service vẫn phải xác nhận môi trường tồn tại, đang hoạt động và người gọi có quyền triển khai.

## 6. CompletionProvider nhận biết ngữ cảnh như thế nào?

`CompletionContext` cung cấp các thông tin hữu ích:

| Phương thức | Ý nghĩa |
|---|---|
| `getWords()` | Danh sách các từ trong buffer, không gồm các từ tạo thành tên command. |
| `getWordIndex()` | Chỉ số từ mà con trỏ đang đứng. |
| `getPosition()` | Vị trí con trỏ bên trong từ hiện tại. |
| `currentWord()` | Toàn bộ từ tại vị trí con trỏ; có thể là `null` nếu con trỏ nằm sau từ cuối. |
| `currentWordUpToCursor()` | Phần của từ hiện tại tính từ đầu từ đến vị trí con trỏ. |
| `getCommand()` | Command đang được hoàn thành, nếu đã xác định được. |
| `getCommandOption()` | Metadata của option hiện tại, nếu con trỏ đang ở ngữ cảnh option. |
| `upToCursor()` | Nội dung buffer từ đầu đến vị trí con trỏ. |

Ví dụ, provider có thể dùng `getCommandOption().longName()` để quyết định danh sách giá trị cần đề xuất. Với command có nhiều option phụ thuộc lẫn nhau, `getWords()` và `upToCursor()` có thể giúp phân tích các lựa chọn người dùng đã nhập trước đó.

Không giả định `getCommand()` hoặc `getCommandOption()` luôn khác `null`. Khi người dùng mới nhập tiền tố command hoặc đang ở giữa một token chưa được phân tích thành option, provider phải xử lý trường hợp chưa có metadata.

## 7. Kết hợp nhiều provider

Một command có thể cần nhiều loại gợi ý. Ví dụ:

- `--environment`: môi trường từ `EnvironmentCatalog`.
- `--mode`: giá trị enum `DeployMode`.
- `--config`: tên tệp cấu hình.

Giả sử command `deploy start` cũng khai báo option tùy chọn `--config` để nhận đường dẫn tệp. Có thể ghép các provider bằng `CompositeCompletionProvider`. Đoạn mã sau là phiên bản mở rộng thay thế bean `deployCompletionProvider` ở phần 5; chỉ đăng ký một bean có tên này trong ứng dụng:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.DefaultCompletionProvider;
import org.springframework.shell.core.command.completion.FileNameCompletionProvider;

@Bean
CompletionProvider deployCompletionProvider(EnvironmentCatalog catalog) {
    CompletionProvider environmentProvider = context ->
            context.getCommandOption() != null
                    && "environment".equals(context.getCommandOption().longName())
                    ? catalog.findDeployableEnvironments().stream()
                            .map(value -> new CompletionProposal("--environment=" + value))
                            .toList()
                    : List.of();

    FileNameCompletionProvider fileNameProvider = new FileNameCompletionProvider();
    CompletionProvider fileProvider = context ->
            context.getCommandOption() != null
                    && "config".equals(context.getCommandOption().longName())
                    ? fileNameProvider.apply(context)
                    : List.of();

    return new CompositeCompletionProvider(
            new DefaultCompletionProvider(),
            environmentProvider,
            fileProvider);
}
~~~

Các provider trong composite cùng nhận một `CompletionContext`; kết quả được tổng hợp thành các đề xuất. Vì vậy, mỗi provider tùy chỉnh nên kiểm tra đúng option hoặc ngữ cảnh mà nó phụ trách và trả danh sách rỗng khi không liên quan. Tránh để nhiều provider cùng tạo các proposal giống nhau.

## 8. Completion với command khai báo bằng Builder

Nếu ứng dụng định nghĩa command bằng API programmatic, có thể gắn provider bằng `Command.Builder.completionProvider(...)`:

~~~java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Bean
Command deployStartCommand(CompletionProvider deployCompletionProvider,
        DeployService deployService) {

    return Command.builder()
            .name("deploy start")
            .description("Bắt đầu triển khai ứng dụng")
            .options(
                    CommandOption.with()
                            .longName("environment")
                            .description("Môi trường đích")
                            .required(true)
                            .type(String.class)
                            .build(),
                    CommandOption.with()
                            .longName("mode")
                            .description("Chiến lược triển khai")
                            .defaultValue("ROLLING")
                            .type(DeployMode.class)
                            .build(),
                    CommandOption.with()
                            .longName("config")
                            .description("Đường dẫn tệp cấu hình")
                            .type(String.class)
                            .build())
            .completionProvider(deployCompletionProvider)
            .execute(context -> {
                String environment = context.getOptionByName("environment").value();
                String mode = context.getOptionByName("mode").value();
                String config = context.getOptionByName("config").value();
                DeployReceipt receipt = deployService.start(
                        environment, DeployMode.valueOf(mode), config);
                context.outputWriter().println(
                        "Đã tạo yêu cầu triển khai " + receipt.requestId());
            });
}
~~~

Ví dụ minh họa vị trí cấu hình provider trong builder. Khi định nghĩa command programmatic, cần khai báo cả metadata option bằng `CommandOption` hoặc builder API tương ứng để parser và completion biết những option nào tồn tại. Đừng chỉ gắn provider mà bỏ qua việc khai báo option của command.

## 9. Completion trong shell tương tác và shell của hệ điều hành

Completion bằng phím Tab trong bài này là completion của **JLine-based interactive shell**. Khi người dùng chạy ứng dụng ở chế độ non-interactive bằng cách truyền command qua tham số tiến trình, không có phiên JLine để nhận phím Tab.

Spring Shell 4.x cũng đã loại bỏ built-in command `completion` dùng để sinh script completion cho hệ điều hành. Nếu muốn hoàn thành lệnh trực tiếp tại Bash hoặc Zsh, cần cấu hình tích hợp theo cơ chế completion của shell hệ điều hành mà người dùng chọn. Đây là luồng cấu hình riêng với `CompletionProvider` trong phiên JLine.

## 10. Những lỗi thường gặp

**Nhấn Tab nhưng không có gợi ý:** kiểm tra ứng dụng đang chạy shell dựa trên JLine và command đã được đăng ký hay chưa. Completion của bài này không hoạt động trong một tiến trình non-interactive không có phiên nhập tương tác.

**Tên command không xuất hiện:** kiểm tra lớp chứa phương thức `@Command` có phải Spring bean và nằm trong phạm vi component scanning hay không. Kiểm tra `name` có được khai báo đúng và không bị ẩn ngoài ý muốn.

**Option không được gợi ý:** kiểm tra option đã được khai báo bằng `@Option` hoặc metadata programmatic tương ứng. Tên option trong lệnh phải khớp với tên được đăng ký.

**Giá trị động không xuất hiện:** kiểm tra `@Command` tham chiếu đúng tên bean `completionProvider`, provider trả danh sách `CompletionProposal` và `getCommandOption()` đang nhận đúng option. Nếu provider trả danh sách rỗng, JLine không có giá trị tùy chỉnh để hiển thị.

**Gợi ý xuất hiện ở option khác:** provider chưa kiểm tra ngữ cảnh. Hãy kiểm tra `context.getCommandOption()` và chỉ trả proposal khi option hiện tại thuộc trách nhiệm của provider.

**Gợi ý trùng lặp:** nhiều provider đang đề xuất cùng một giá trị. Hãy phân chia trách nhiệm rõ ràng hoặc lọc các proposal trùng trước khi trả kết quả.

**Nhấn Tab làm ứng dụng chậm:** provider đang gọi database hoặc dịch vụ mạng quá lâu. Hãy giảm số lần truy vấn, giới hạn số lượng đề xuất và cân nhắc cache dữ liệu chỉ đọc. Không chạy tác vụ nghiệp vụ trong provider.

**Dùng API cũ của Spring Shell 3.x:** Spring Shell 4.x dùng `CompletionProvider` cấp command và thuộc tính `completionProvider` của `@Command`. `ValueProvider` và `@ShellOption(valueProvider = ...)` là mô hình cũ; `@OptionValues` đã bị loại bỏ. Hãy kiểm tra phiên bản trước khi sao chép ví dụ từ tài liệu 3.x.

## 11. Quy trình triển khai completion

Khi bổ sung gợi ý cho command, thực hiện theo thứ tự:

1. Đăng ký command với tên và option rõ ràng.
2. Thử completion mặc định cho tên command, tên lệnh con và option.
3. Xác định option nào cần gợi ý giá trị enum, tệp hoặc dữ liệu động.
4. Dùng `DefaultCompletionProvider`, `EnumCompletionProvider` hoặc `FileNameCompletionProvider` nếu phù hợp.
5. Viết `CompletionProvider` riêng cho dữ liệu động và gắn bằng `@Command(completionProvider = "...")`.
6. Dùng `CompositeCompletionProvider` khi cần kết hợp nhiều nguồn gợi ý.
7. Kiểm tra provider xử lý đúng context, không trả gợi ý cho option khác và không thực hiện tác dụng phụ.
8. Thử các trường hợp không có kết quả, nhiều kết quả, tiền tố một phần và dữ liệu nguồn tạm thời không sẵn sàng.

## Kết luận

Spring Shell 4.x cung cấp completion mặc định cho command và option trong JLine-based shell, giúp người dùng khám phá tên lệnh, lệnh con và cú pháp bằng phím Tab. Khi cần gợi ý giá trị, có thể dùng các provider có sẵn cho enum và tên tệp hoặc tạo `CompletionProvider` riêng dựa trên `CompletionContext`. Kết hợp nhiều nguồn bằng `CompositeCompletionProvider` giúp command hỗ trợ cả gợi ý mặc định lẫn dữ liệu động. Completion chỉ hỗ trợ nhập liệu; command và service vẫn phải xác thực mọi giá trị trước khi thực thi nghiệp vụ.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 – Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [Spring Shell 4.0.3 API – CompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [Spring Shell 4.0.4 API – CompletionContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html)
- [Spring Shell 4.0.4 API – CompletionProposal](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html)
- [Spring Shell 4.0.4 API – DefaultCompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/DefaultCompletionProvider.html)
- [Spring Shell 4.0.4 API – EnumCompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/EnumCompletionProvider.html)
- [Spring Shell 4.0.4 API – CompositeCompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompositeCompletionProvider.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
