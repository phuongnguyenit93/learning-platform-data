# `CompletionResolver` hoặc cấu hình completion bằng builder trong Spring Shell 3.x

Spring Shell 3.x cho phép bổ sung gợi ý khi người dùng nhấn Tab trong phiên shell tương tác. Khi cần gợi ý giá trị option, có thể triển khai `CompletionResolver` và đăng ký thành bean dùng chung, hoặc gắn hàm completion trực tiếp vào từng option trong `CommandRegistration.Builder`. Cả hai cách đều nhận `CompletionContext` và trả về danh sách `CompletionProposal`.

`CompletionResolver` phù hợp khi nhiều command dùng chung quy tắc gợi ý. Cấu hình bằng builder phù hợp khi gợi ý chỉ thuộc về một option của một command được đăng ký theo kiểu programmatic. Bài học này tập trung vào hai cách đó trong Spring Shell 3.x, đồng thời phân biệt chúng với `ValueProvider` của mô hình annotation legacy.

## 1. Completion hoạt động như thế nào?

Khi người dùng nhập một phần command rồi nhấn Tab, shell phân tích nội dung hiện có và tạo `CompletionContext`. Resolver đọc ngữ cảnh đó để xác định vị trí con trỏ, command đang được gọi, option hiện tại và phần văn bản người dùng đã nhập. Resolver trả về các đề xuất; JLine hiển thị chúng hoặc chèn giá trị phù hợp vào dòng lệnh.

Ví dụ người dùng nhập:

```text
app deploy --environment st<Tab>
```

Nếu các môi trường có thể triển khai là `staging`, `staging-eu` và `production`, completion có thể đưa ra hai lựa chọn bắt đầu bằng `st`. Người dùng chọn một đề xuất rồi tiếp tục nhập command.

Completion giúp khám phá cú pháp và giảm lỗi gõ. Nó không thay thế validation hoặc kiểm tra nghiệp vụ. Dù `production` không xuất hiện trong danh sách gợi ý, người dùng vẫn có thể tự nhập giá trị đó; command phải tự kiểm tra giá trị nhận được trước khi thực hiện thao tác.

Trong Spring Shell 3.x, cần phân biệt hai môi trường:

- **Phiên tương tác:** shell đang chạy cùng JLine, có thể gọi resolver Java ngay khi người dùng nhấn Tab.
- **Command-line không tương tác:** người dùng gọi ứng dụng từ Bash hoặc shell hệ điều hành. Completion cần tích hợp ở cấp shell hệ điều hành bằng script được tạo từ command tích hợp `completion`; tài liệu Spring Shell 3.4 hiện mô tả hỗ trợ Bash.

## 2. Các kiểu dữ liệu của completion

`CompletionContext` và `CompletionProposal` nằm trong package `org.springframework.shell`. `CompletionProvider` và `CompletionResolver` nằm trong package `org.springframework.shell.completion`.

| Kiểu | Vai trò |
| --- | --- |
| `CompletionContext` | Cung cấp ngữ cảnh của dòng lệnh tại vị trí con trỏ khi completion được yêu cầu |
| `CompletionProposal` | Đại diện cho một giá trị gợi ý cùng metadata hiển thị |
| `CompletionProvider` | Functional interface nhận `CompletionContext` và trả danh sách `CompletionProposal` |
| `CompletionResolver` | Mở rộng `CompletionProvider`, được thiết kế để Spring tự động kết nối như resolver dùng chung |

`CompletionResolver` là functional interface, có phương thức `apply(CompletionContext)`. Một resolver có thể được viết thành lớp hoặc lambda. Nếu resolver được đăng ký như Spring bean, Spring Shell có thể sử dụng nó ở phạm vi toàn shell.

### Đọc `CompletionContext`

Những phương thức thường dùng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getCommandRegistration()` | Lấy thông tin đăng ký command hiện tại |
| `getCommandOption()` | Lấy metadata option đang được completion |
| `getWords()` | Danh sách từ trong buffer, không bao gồm các từ tạo tên command |
| `getWordIndex()` | Vị trí từ hiện tại trong danh sách |
| `getPosition()` | Vị trí con trỏ bên trong từ hiện tại |
| `currentWord()` | Toàn bộ từ tại vị trí con trỏ; có thể là `null` nếu con trỏ ở sau từ cuối |
| `currentWordUpToCursor()` | Phần từ hiện tại tính từ đầu từ đến vị trí con trỏ |
| `upToCursor()` | Nội dung buffer tính đến vị trí con trỏ |
| `drop(int)` | Tạo context mới sau khi bỏ một số từ đầu danh sách |

Một resolver dùng chung nên kiểm tra `getCommandOption()` trước khi tạo gợi ý. Nếu option không phải option mà resolver phụ trách, hãy trả về danh sách rỗng để không làm nhiễu completion của command khác.

### Tạo `CompletionProposal`

Constructor `new CompletionProposal("staging")` tạo một đề xuất có giá trị được chèn vào dòng lệnh. Ngoài `value`, proposal còn hỗ trợ metadata:

- `displayText(...)`: nội dung hiển thị trong danh sách gợi ý.
- `description(...)`: mô tả ngắn cho đề xuất.
- `category(...)`: nhóm của đề xuất.
- `complete(...)`: xác định đề xuất có hoàn tất phần nhập hiện tại hay không.
- `dontQuote(...)`: điều khiển việc shell có đặt dấu nháy cho giá trị hay không.

Nếu chỉ cần đề xuất một giá trị đơn giản, `new CompletionProposal(value)` là đủ. Metadata hữu ích khi có nhiều lựa chọn gần giống nhau hoặc khi cần giải thích ý nghĩa của từng giá trị.

## 3. Đăng ký `CompletionResolver` dùng chung

Khi nhiều command cần cùng một danh sách giá trị, có thể tạo một resolver Spring bean. Ví dụ dưới đây gợi ý các môi trường triển khai cho option `--environment`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Component;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.completion.CompletionResolver;
import org.springframework.shell.command.CommandOption;

@Component
public class EnvironmentCompletionResolver implements CompletionResolver {

    private static final List<String> ENVIRONMENTS =
            List.of("development", "staging", "production");

    @Override
    public List<CompletionProposal> apply(CompletionContext context) {
        CommandOption option = context.getCommandOption();

        if (option == null ||
                Arrays.stream(option.getLongNames())
                        .noneMatch("environment"::equals)) {
            return List.of();
        }

        String prefix = Optional.ofNullable(context.currentWordUpToCursor())
                .orElse("");

        return ENVIRONMENTS.stream()
                .filter(value -> value.startsWith(prefix))
                .map(value -> new CompletionProposal(value)
                        .description("Môi trường " + value)
                        .category("environment"))
                .toList();
    }
}
```

Spring Shell tự phát hiện bean `CompletionResolver` và sử dụng nó như resolver dùng chung. Không cần khai báo resolver này trên từng command. Khi người dùng hoàn thành một option có tên `environment`, resolver trả về các môi trường phù hợp với phần tiền tố đang nhập. Với option khác, resolver trả về danh sách rỗng.

Nếu nhiều command có option `environment` nhưng yêu cầu danh sách khác nhau, có thể kiểm tra thêm command:

```java
String commandName = context.getCommandRegistration() == null
        ? ""
        : context.getCommandRegistration().getCommand();

if (!"app deploy".equals(commandName)) {
    return List.of();
}
```

Đặt điều kiện theo command giúp một resolver toàn cục chỉ xử lý đúng phạm vi cần thiết. Có thể tách danh sách gợi ý sang một service dùng chung nếu danh sách được lấy từ cấu hình hoặc hệ thống bên ngoài.

## 4. Completion động dựa trên dữ liệu ứng dụng

Danh sách gợi ý không nhất thiết là hằng số. Một command chọn dự án có thể đề xuất những dự án mà người dùng hiện tại được phép truy cập; command chọn nhánh Git có thể đề xuất các nhánh có trong repository; command chọn máy chủ có thể đề xuất các endpoint được cấu hình.

Ví dụ resolver dùng service để lấy tên dự án:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Component;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.completion.CompletionResolver;
import org.springframework.shell.command.CommandOption;

@Component
public class ProjectCompletionResolver implements CompletionResolver {

    private final ProjectQueryService projectQueryService;

    public ProjectCompletionResolver(ProjectQueryService projectQueryService) {
        this.projectQueryService = projectQueryService;
    }

    @Override
    public List<CompletionProposal> apply(CompletionContext context) {
        CommandOption option = context.getCommandOption();
        if (option == null ||
                !List.of(option.getLongNames()).contains("project")) {
            return List.of();
        }

        String prefix = Optional.ofNullable(context.currentWordUpToCursor())
                .orElse("");

        return projectQueryService.findAccessibleProjectNames(prefix).stream()
                .map(name -> new CompletionProposal(name)
                        .description("Dự án " + name)
                        .category("project"))
                .toList();
    }
}
```

Service truy vấn dữ liệu nên chỉ đọc và trả kết quả gọn. Completion được gọi thường xuyên khi người dùng nhấn Tab, vì vậy tránh chạy truy vấn toàn bộ dữ liệu, gọi API chậm hoặc thực hiện side effect ở mỗi lần gợi ý. Nên lọc theo tiền tố ngay tại nguồn dữ liệu, giới hạn số kết quả và dùng cache khi danh sách ít thay đổi.

Resolver cũng không nên coi danh sách gợi ý là danh sách được phép thực thi cuối cùng. Quyền truy cập dự án phải được kiểm tra lại trong command hoặc application service vì dữ liệu và quyền có thể thay đổi sau lúc completion được hiển thị.

## 5. Gắn completion trực tiếp vào option bằng `CommandRegistration.Builder`

Nếu command được đăng ký theo mô hình programmatic và chỉ một option cần gợi ý riêng, có thể cấu hình completion ngay trên `OptionSpec`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.CompletionProposal;

@Configuration
public class DeployCommandConfiguration {

    @Bean
    CommandRegistration deployRegistration(
            CommandRegistration.BuilderSupplier builderSupplier) {

        return builderSupplier.get()
                .command("app deploy")
                .description("Triển khai ứng dụng tới một môi trường.")
                .withTarget()
                    .function(context -> {
                        String environment =
                                context.getOptionValue("environment");
                        return "Đã yêu cầu triển khai tới " + environment;
                    })
                    .and()
                .withOption()
                    .longNames("environment")
                    .type(String.class)
                    .required()
                    .completion(context -> {
                        String prefix = Optional.ofNullable(
                                context.currentWordUpToCursor()
                        ).orElse("");

                        return List.of("development", "staging", "production")
                                .stream()
                                .filter(value -> value.startsWith(prefix))
                                .map(CompletionProposal::new)
                                .toList();
                    })
                    .and()
                .build();
    }
}
```

`CommandRegistration.BuilderSupplier` cung cấp một builder mới đã được cấu hình theo các customizer của ứng dụng. `CommandRegistration` được khai báo thành Spring bean sẽ được Spring Shell tự động đăng ký. Trong ví dụ, `withOption()` tạo option `--environment`; `completion(...)` gắn hàm đề xuất riêng cho option đó. Target dùng `CommandContext.getOptionValue("environment")` để đọc giá trị khi command thực thi.

Khi người dùng nhập:

```text
app deploy --environment st<Tab>
```

builder completion chỉ tạo gợi ý cho option `environment` của command `app deploy`. Những command khác không bị ảnh hưởng.

Nếu không cần dùng `BuilderSupplier`, có thể tạo trực tiếp bằng `CommandRegistration.builder()`. Tuy nhiên, `BuilderSupplier` phù hợp hơn khi ứng dụng có các `CommandRegistrationCustomizer` hoặc muốn dùng cấu hình chung mà auto-configuration cung cấp.

## 6. Khi nào nên dùng resolver toàn cục, khi nào nên dùng builder?

| Nhu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Nhiều command dùng cùng một quy tắc gợi ý | Bean `CompletionResolver` | Dùng lại logic và dữ liệu |
| Chỉ một option trong command programmatic cần gợi ý | `OptionSpec.completion(...)` | Cấu hình nằm ngay cạnh option |
| Mỗi command cần danh sách gợi ý riêng nhưng cùng cấu trúc | Một resolver toàn cục kiểm tra command và option | Tránh lặp code nhưng vẫn phân nhánh theo ngữ cảnh |
| Command dùng annotation legacy `@ShellMethod`/`@ShellOption` | `ValueProvider` qua `@ShellOption(valueProvider = ...)` | Đây là extension point riêng của legacy annotation model |
| Command dùng annotation mới `@Command`/`@Option` trong 3.x | `@Option` của Spring Shell 3.4 không có thuộc tính `valueProvider`; dùng resolver dùng chung hoặc đăng ký command theo programmatic model nếu cần completion riêng cho option | Không giả định thuộc tính của `@ShellOption` có mặt trên `@Option` |

Không nên tạo một resolver toàn cục chỉ để gợi ý cho một option duy nhất nếu command có thể được cấu hình trực tiếp bằng builder. Ngược lại, nếu cùng một danh sách môi trường được dùng ở nhiều command, nên đưa logic vào một resolver hoặc service dùng chung thay vì sao chép lambda ở từng option.

## 7. Phân biệt `CompletionResolver` với `ValueProvider`

Spring Shell 3.x có các mô hình đăng ký command khác nhau. Đối với annotation legacy, option có thể khai báo `valueProvider` trên `@ShellOption`. Provider phải triển khai `ValueProvider` và được đăng ký thành Spring bean:

```java
import java.util.List;

import org.springframework.stereotype.Component;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;

@Component
public class LegacyEnvironmentValueProvider implements ValueProvider {

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        return List.of("development", "staging", "production").stream()
                .map(CompletionProposal::new)
                .toList();
    }
}
```

Command legacy sử dụng provider:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class LegacyDeployCommands {

    @ShellMethod(key = "legacy deploy")
    public String deploy(
            @ShellOption(
                value = "--environment",
                valueProvider = LegacyEnvironmentValueProvider.class
            ) String environment) {
        return "Đã yêu cầu triển khai tới " + environment;
    }
}
```

Các API này có mục đích gần nhau nhưng không cùng loại:

- `CompletionResolver` thuộc package `org.springframework.shell.completion`, dùng `apply(CompletionContext)` và được kết nối toàn cục hoặc gắn vào option builder.
- `ValueProvider` thuộc package `org.springframework.shell.standard`, dùng `complete(CompletionContext)` và được khai báo trên `@ShellOption` của legacy annotation model.
- `@ShellOption(valueProvider = ...)` không phải thuộc tính của annotation mới `@Option`.

Không trộn các import legacy với mô hình annotation mới chỉ vì tên khái niệm tương tự. Khi chuyển command từ legacy sang programmatic hoặc annotation mới, hãy chuyển cả cách cung cấp completion theo API tương ứng.

## 8. Completion cho Bash và command-line không tương tác

Completion trong phiên tương tác được JLine gọi trực tiếp khi người dùng nhấn Tab. Khi ứng dụng được gọi như một command từ Bash, quá trình hoàn thành phải được tích hợp vào shell hệ điều hành. Spring Shell 3.4 cung cấp command tích hợp `completion`; tài liệu mô tả sub-command `bash` để tạo script completion cho Bash.

Có thể phân biệt:

| Môi trường | Cách kích hoạt | Cơ chế |
| --- | --- | --- |
| Phiên Spring Shell tương tác | Nhấn Tab trong prompt của ứng dụng | JLine gọi completion resolver và provider |
| Bash bên ngoài ứng dụng | Nhấn Tab sau khi cài/nạp script completion | Bash dùng script do command `completion bash` tạo |
| Script tự động gọi command | Không có thao tác Tab | Script cần truyền đầy đủ tên command và giá trị option |

Không nên giả định một bean `CompletionResolver` sẽ tự động làm cho mọi terminal hệ điều hành gợi ý giá trị. Resolver phục vụ completion trong shell đang chạy; Bash cần script tích hợp riêng. Tài liệu Spring Shell 3.4 hiện nêu Bash là implementation command-line completion được hỗ trợ.

## 9. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Nhấn Tab nhưng không có gợi ý | Resolver chưa được đăng ký thành bean hoặc option chưa có completion | Kiểm tra component scan, bean và tên option |
| Resolver trả gợi ý cho mọi command | Không kiểm tra `getCommandOption()` hoặc command hiện tại | Lọc theo option và command cần hỗ trợ |
| Gợi ý không lọc theo phần đã nhập | Không sử dụng `currentWordUpToCursor()` | Lọc danh sách theo tiền tố tại vị trí con trỏ |
| Completion chậm | Resolver truy vấn dữ liệu lớn hoặc gọi dịch vụ mạng đồng bộ | Lọc tại nguồn, giới hạn kết quả và dùng cache |
| Gợi ý có giá trị nhưng command từ chối | Danh sách completion đã cũ hoặc không phản ánh quyền hiện tại | Validation và kiểm tra quyền lại khi thực thi |
| Builder completion không được gọi | Đang dùng command đăng ký bằng mô hình khác hoặc cấu hình sai option | Xác nhận command thực sự dùng `CommandRegistration` và completion gắn đúng `OptionSpec` |
| `ValueProvider` không được gọi | Provider chưa là Spring bean hoặc command không dùng legacy `@ShellOption` | Đăng ký bean và kiểm tra đúng annotation model |
| Bash không gợi ý nhưng JLine có gợi ý | Chưa tạo hoặc chưa nạp script Bash completion | Dùng command `completion bash` và cấu hình script theo hướng dẫn |

## 10. Checklist triển khai completion

- Xác định completion chạy trong JLine tương tác hay Bash bên ngoài ứng dụng.
- Dùng `CompletionResolver` toàn cục khi nhiều command chia sẻ logic.
- Dùng `OptionSpec.completion(...)` khi chỉ một option programmatic cần gợi ý riêng.
- Kiểm tra option và command trong `CompletionContext` trước khi trả đề xuất.
- Lọc kết quả theo `currentWordUpToCursor()` để gợi ý khớp phần đã nhập.
- Dùng `CompletionProposal` metadata khi cần mô tả hoặc phân loại lựa chọn.
- Giữ resolver nhanh, không có side effect và không truy vấn dữ liệu không giới hạn.
- Không xem completion là validation hoặc cơ chế phân quyền.
- Dùng `ValueProvider` chỉ trong đúng legacy annotation model.
- Kiểm tra command với trường hợp chưa nhập gì, đã nhập một phần, không có kết quả và dữ liệu thay đổi.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Completion](https://docs.spring.io/spring-shell/reference/3.4/completion.html)
- [Spring Shell 3.4 — CompletionResolver API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/completion/CompletionResolver.html)
- [Spring Shell 3.4 — CompletionContext API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/CompletionContext.html)
- [Spring Shell 3.4 — CompletionProposal API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/CompletionProposal.html)
- [Spring Shell 3.4 — CommandRegistration.Builder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html)
- [Spring Shell 3.4 — Programmatic Command Registration](https://docs.spring.io/spring-shell/reference/3.4/commands/registration/programmatic.html)
- [Spring Shell 3.4 — ValueProvider API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/ValueProvider.html)
