# Tùy biến completion, availability và lỗi theo mô hình phiên bản

Khi một command cần gợi ý giá trị theo dữ liệu đang có, chỉ được chạy sau khi người dùng kết nối, hoặc phải trả mã lỗi có ý nghĩa cho script, ta cần bổ sung các thành phần mở rộng cho command. Spring Shell cung cấp ba cơ chế tương ứng: `CompletionProvider`, `AvailabilityProvider` và `ExitStatusExceptionMapper`.

API của các cơ chế này đã thay đổi đáng kể giữa Spring Shell 3 và 4. Trong Spring Shell 4, chúng được gắn trực tiếp vào command thông qua `Command.Builder` khi đăng ký bằng code. Bài học này dùng mô hình programmatic registration của Spring Shell 4.x, đồng thời chỉ ra tên API cần nhận biết khi bảo trì ứng dụng 3.x.

Trước khi nâng cấp, kiểm tra nền tảng tương thích: Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi chạy cùng Spring Boot. Module `spring-shell-core` không còn kéo theo Spring Boot hoặc JLine; ứng dụng Spring Boot cần starter hoặc `spring-shell-core-autoconfigure`, còn ứng dụng cần JLine phải thêm `spring-shell-jline`. Những thay đổi dependency này thường là nguyên nhân khiến ứng dụng sau nâng cấp thiếu auto-configuration hoặc mất completion bằng Tab.

## 1. Chọn mô hình đăng ký command

Spring Shell hỗ trợ hai cách định nghĩa command:

- **Annotation-based:** khai báo phương thức trong Spring bean và đánh dấu bằng `@Command`, `@Option`, `@Argument` cùng các annotation liên quan.
- **Programmatic:** tạo đối tượng `Command` bằng `Command.builder()` hoặc kế thừa `AbstractCommand`, sau đó cung cấp command cho Spring.

Với Spring Boot, một bean có kiểu `Command` được tự động thêm vào `CommandRegistry`. Cách này phù hợp khi command được tạo bằng code, phụ thuộc cấu hình lúc khởi động hoặc cần gắn các provider trực tiếp vào builder. Nếu command chỉ là một phương thức nghiệp vụ đơn giản và cấu trúc tham số ổn định, mô hình annotation thường ngắn gọn hơn.

Ví dụ đăng ký command bằng bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
public class CommandConfiguration {

    @Bean
    Command pingCommand() {
        return Command.builder()
                .name("ping")
                .description("Kiểm tra CLI đang hoạt động")
                .execute(context -> "pong");
    }
}
```

`Command.builder()` tạo builder; các phương thức như `name`, `description`, `arguments`, `options` và những provider cấu hình hành vi của command. `execute` nhận logic xử lý. Với ví dụ trả về chuỗi, Spring Shell in kết quả đó ra output của shell. Bean `Command` được Spring Boot tự động đăng ký, vì vậy không cần tự thêm một lệnh đăng ký thủ công cho cùng bean.

Nếu ứng dụng không dùng Spring Boot, cần cấu hình cơ chế đăng ký command theo mô hình Spring Shell tương ứng, chẳng hạn `@EnableCommand` cho annotation-based registration. Đừng suy ra rằng mọi cấu hình auto-configuration của Spring Boot đều có sẵn trong một application context Spring thuần.

## 2. Gắn đối số và provider vào `Command.Builder`

Với đăng ký bằng code, có thể mô tả positional argument bằng `CommandArgument.Builder` và option bằng `CommandOption.Builder`, sau đó truyền vào `Command.Builder`.

Ví dụ một command nhận tên dự án ở vị trí đầu tiên:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandArgument;

CommandArgument projectArgument = new CommandArgument.Builder()
        .index(0)
        .description("Tên dự án cần chuyển đến")
        .type(String.class)
        .build();

Command command = Command.builder()
        .name("checkout")
        .description("Chuyển sang một dự án")
        .arguments(projectArgument)
        .execute(context -> {
            String projectName = context.getArgumentByIndex(0).value();
            return "Đã yêu cầu chuyển sang dự án " + projectName;
        });
```

`CommandContext` cung cấp dữ liệu của lần gọi hiện tại. Có thể lấy positional argument bằng `getArgumentByIndex`, lấy option bằng `getOptionByName`, `getOptionByLongName` hoặc `getOptionByShortName`, và ghi output qua `outputWriter()`.

Builder cũng nhận nhiều đối số qua `arguments(...)` và nhiều option qua `options(...)`. Hãy khai báo kiểu, mô tả, giá trị mặc định và tính bắt buộc rõ ràng để parser, help và completion hiểu cùng một hợp đồng command.

## 3. Tùy biến gợi ý bằng `CompletionProvider`

Completion giúp người dùng khám phá giá trị hợp lệ trước khi thực thi command. Trong Spring Shell 4, `CompletionProvider` là một functional interface nhận `CompletionContext` và trả về `List<CompletionProposal>`.

`CompletionContext` mô tả dòng lệnh tại thời điểm người dùng nhấn Tab. Nó cung cấp danh sách từ đã nhập, vị trí con trỏ, từ hiện tại, phần từ đến con trỏ, command đang được hoàn thành và option hiện tại nếu có. `CompletionProposal` mô tả nội dung sẽ được chèn; có thể bổ sung mô tả hoặc category để giải thích gợi ý.

Ví dụ provider gợi ý tên dự án mà người dùng được phép truy cập:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

CompletionProvider projectCompletion = context -> {
    String prefix = Optional.ofNullable(context.currentWordUpToCursor())
            .orElse("");

    return projectService.accessibleProjectNames().stream()
            .filter(name -> name.regionMatches(
                    true, 0, prefix, 0, prefix.length()))
            .sorted()
            .map(name -> new CompletionProposal(name)
                    .description("Dự án bạn có quyền truy cập"))
            .toList();
};
```

Provider lấy phần người dùng đang gõ, lọc danh sách theo tiền tố và tạo proposal. `accessibleProjectNames()` là phương thức minh họa của service trong ứng dụng; service nên chỉ trả về những dự án mà người dùng hiện tại có thể nhìn thấy. Với dữ liệu lớn, nên lọc và giới hạn kết quả ở tầng truy vấn thay vì tải toàn bộ danh sách mỗi lần người dùng nhấn Tab.

Gắn provider vào command bằng `completionProvider(...)`:

```java
return Command.builder()
        .name("checkout")
        .description("Chuyển sang một dự án")
        .arguments(projectArgument)
        .completionProvider(projectCompletion)
        .execute(context -> {
            String projectName = context.getArgumentByIndex(0).value();
            projectService.checkout(projectName);
            return "Đã chuyển sang dự án " + projectName;
        });
```

Provider được đặt ở cấp command, vì vậy nó có thể xem toàn bộ ngữ cảnh dòng lệnh và đưa ra gợi ý phụ thuộc vào nhiều giá trị đã nhập. Khi cần phân biệt option đang được hoàn thành, kiểm tra `context.getCommandOption()` và tên option tương ứng. Điều này hữu ích khi giá trị của `--environment` phụ thuộc vào `--region`, hoặc danh sách tài nguyên thay đổi theo option `--project`.

## 4. Dùng provider có sẵn và kết hợp nhiều nguồn gợi ý

Spring Shell 4 cung cấp một số completion provider thường dùng:

| Provider | Công dụng |
| --- | --- |
| `EnumCompletionProvider` | Gợi ý các hằng của một enum; có thể thêm prefix cho dạng `key=value` |
| `FileNameCompletionProvider` | Gợi ý tên file và thư mục theo thư mục hiện tại |
| `CompositeCompletionProvider` | Kết hợp nhiều provider thành một nguồn gợi ý |
| `DefaultCompletionProvider` | Xử lý gợi ý mặc định cho option kiểu enum và prefix của option; có từ 4.0.1 |

Ví dụ kết hợp gợi ý tên file với giá trị enum:

```java
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;
import org.springframework.shell.core.command.completion.FileNameCompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProvider;

CompletionProvider formatCompletion =
        new EnumCompletionProvider(ExportFormat.class, "--format=");

CompletionProvider fileCompletion = new FileNameCompletionProvider();

CompletionProvider combined = new CompositeCompletionProvider(
        formatCompletion,
        fileCompletion);
```

Đây là ví dụ về cách ghép provider; khi dùng trong một command cụ thể, hãy chọn các provider phù hợp với vị trí hoặc option hiện tại để tránh gợi ý lẫn lộn. Nếu cần gợi ý động từ cơ sở dữ liệu hoặc dịch vụ ngoài, tự triển khai `CompletionProvider` và trả về các `CompletionProposal` phù hợp.

Một proposal có các thuộc tính như `value`, `displayText`, `description`, `category`, `complete` và `dontQuote`. `value` là nội dung được chèn; `displayText` là nội dung hiển thị trong danh sách; `description` giải thích mục; `dontQuote` có thể dùng khi giá trị không nên được shell tự đặt trong dấu nháy. Chỉ đặt các metadata này khi chúng giúp người dùng chọn đúng giá trị.

## 5. Điều kiện hoạt động của command với `AvailabilityProvider`

Một command có thể đã được đăng ký nhưng chưa thể thực thi do trạng thái ứng dụng. Ví dụ, `download` chỉ hợp lệ sau khi người dùng kết nối tới máy chủ. `AvailabilityProvider` cho Spring Shell biết command đang sẵn sàng hay chưa và cung cấp lý do nếu bị khóa.

Provider trả về `Availability.available()` hoặc `Availability.unavailable(reason)`. Lý do nên là một cụm từ ngắn, viết thường và không có dấu chấm cuối, vì Spring Shell nối nó vào thông báo dạng “command hiện không khả dụng because ...”.

Ví dụ:

```java
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

AvailabilityProvider downloadAvailability = () ->
        sessionState.isConnected()
                ? Availability.available()
                : Availability.unavailable("bạn chưa kết nối tới máy chủ");
```

Gắn provider vào command bằng builder:

```java
return Command.builder()
        .name("download")
        .description("Tải dữ liệu từ máy chủ")
        .availabilityProvider(downloadAvailability)
        .execute(context -> {
            downloadService.download();
            return "Đã tải dữ liệu";
        });
```

Khi command chưa khả dụng, Spring Shell thông báo lý do trước khi chạy phần thực thi. Provider nên đọc trạng thái nhanh, chẳng hạn trạng thái đăng nhập hoặc kết nối đã được lưu trong service. Tránh gọi API mạng chậm mỗi lần kiểm tra availability vì điều đó làm shell phản hồi chậm.

Availability là cơ chế cải thiện trải nghiệm và chỉ dẫn người dùng. Service vẫn phải kiểm tra trạng thái kết nối, quyền và điều kiện nghiệp vụ khi thực thi, vì trạng thái có thể thay đổi giữa thời điểm kiểm tra availability và thời điểm command chạy.

## 6. Ánh xạ exception bằng `ExitStatusExceptionMapper`

Command có thể ném exception khi dữ liệu không hợp lệ, tài nguyên không tồn tại hoặc dịch vụ phụ thuộc gặp sự cố. Spring Shell 4 cho phép gắn `ExitStatusExceptionMapper` để chuyển exception thành `ExitStatus` có mã và mô tả.

Mapper là một functional interface nhận `Exception` và trả về `ExitStatus`. Ví dụ:

```java
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

ExitStatusExceptionMapper projectErrorMapper = exception -> {
    if (exception instanceof ProjectNotFoundException) {
        return new ExitStatus(3, "Không tìm thấy dự án được yêu cầu");
    }
    if (exception instanceof IllegalArgumentException) {
        return ExitStatus.USAGE_ERROR;
    }
    return ExitStatus.EXECUTION_ERROR;
};
```

Gắn mapper vào command:

```java
return Command.builder()
        .name("checkout")
        .description("Chuyển sang một dự án")
        .arguments(projectArgument)
        .exitStatusExceptionMapper(projectErrorMapper)
        .execute(context -> {
            String projectName = context.getArgumentByIndex(0).value();
            projectService.checkout(projectName);
            return "Đã chuyển sang dự án " + projectName;
        });
```

Trong ví dụ, command thành công trả về chuỗi kết quả. Nếu service ném `ProjectNotFoundException`, mapper trả mã `3` cùng mô tả lỗi. Những lỗi khác được ánh xạ sang trạng thái thực thi chung. Các mã trong ứng dụng nên được quy ước và ghi rõ trong README để script có thể xử lý ổn định.

Không nên ánh xạ mọi exception thành cùng một trạng thái thành công hoặc bắt rồi bỏ qua lỗi. Nếu cần trả trạng thái cụ thể từ nhánh thực thi bình thường, có thể triển khai command bằng cách kế thừa `AbstractCommand` và trả `ExitStatus` trong `doExecute(CommandContext)`. Với builder `execute(Function<CommandContext, String>)`, kết quả chuỗi là output thành công; exception được chuyển qua mapper đã gắn.

## 7. Đăng ký và gỡ command trong lúc ứng dụng chạy

Spring Shell 4 có `CommandRegistry` để quản lý các command đã biết. Những bean kiểu `Command` được tự động đăng ký trong application context. Khi một command chỉ tồn tại trong một giai đoạn, chẳng hạn command do plugin cung cấp hoặc tính năng chỉ bật sau khi kích hoạt module, có thể đăng ký và gỡ command bằng registry.

Ví dụ một thành phần quản lý vòng đời command:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class OptionalCommandRegistrar {

    private final CommandRegistry commandRegistry;

    public OptionalCommandRegistrar(CommandRegistry commandRegistry) {
        this.commandRegistry = commandRegistry;
    }

    public void enable(Command command) {
        commandRegistry.registerCommand(command);
    }

    public void disable(Command command) {
        commandRegistry.unregisterCommand(command);
    }
}
```

Đối tượng `Command` được truyền vào có thể được tạo theo cấu hình plugin hoặc theo trạng thái tính năng. Không đăng ký lặp một command bean đã được Spring tự động thêm vào registry. Khi gỡ command, cần đảm bảo các luồng đang sử dụng command đó đã được xử lý theo chính sách của ứng dụng.

Với danh sách command cố định, khai báo bean `Command` là đủ. Chỉ dùng registry động khi danh sách command thực sự thay đổi trong thời gian chạy; điều đó giúp tránh tạo thêm trạng thái quản lý không cần thiết.

## 8. Khác biệt quan trọng giữa Spring Shell 3.x và 4.x

Spring Shell 4 thiết kế lại mô hình command và cách gắn các thành phần tùy biến. Khi đọc ví dụ hoặc nâng cấp dự án, cần nhận diện đúng API của phiên bản.

| Chủ đề | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Định nghĩa command | Các API đăng ký cũ, thường gặp `CommandRegistration` và annotation `@ShellComponent` / `@ShellMethod` | Bean `Command` với `Command.Builder`, hoặc `@Command` trên phương thức Spring bean |
| Đăng ký động | `CommandCatalog` và `CommandRegistration` | `CommandRegistry` và `Command` |
| Completion | Provider gắn theo option, `ValueProvider` / `@OptionValues` và các resolver | `CompletionProvider` ở cấp command, gắn bằng `completionProvider(...)` |
| Availability | `@CommandAvailability` hoặc cấu hình availability theo mô hình cũ | `AvailabilityProvider` gắn bằng `availabilityProvider(...)` |
| Exception | `CommandExceptionResolver` và `CommandHandlingResult` | `ExitStatusExceptionMapper` và `ExitStatus` |
| Annotation tùy biến | Nhiều annotation tách rời | Thuộc tính tùy biến tập trung trong `@Command` |

Trong Spring Shell 4, `@ShellComponent`, `@ShellMethod`, `@ShellOption`, `@OptionValues` và các annotation cũ liên quan đã bị loại bỏ. `@CommandAvailability` được thay bằng thuộc tính `availabilityProvider` của `@Command`. `CommandExceptionResolver` được thay bằng `ExitStatusExceptionMapper`. `EnumValueProvider` đổi tên thành `EnumCompletionProvider`; `FileValueProvider` đổi tên thành `FileNameCompletionProvider`.

Mô hình completion 4.x tập trung ở cấp command, nhờ đó provider có thể xét ngữ cảnh của toàn bộ dòng lệnh và đưa ra gợi ý phụ thuộc chéo giữa các option. Mô hình 3.x thường tách provider theo option, vì vậy khi nâng cấp cần chuyển logic cũ sang một `CompletionProvider` thống nhất.

Nếu dùng annotation-based registration trong Spring Shell 4, có thể trỏ đến các bean provider ngay trên `@Command`, ví dụ `@Command(name = "download", availabilityProvider = "loginAvailability", completionProvider = "downloadCompletion", exitStatusExceptionMapper = "downloadErrors")`. Với programmatic registration trong bài này, truyền trực tiếp các đối tượng provider vào `Command.Builder`.

Một lưu ý khi chọn mô hình đăng ký: hướng dẫn migration của Spring Shell hiện ghi nhận rằng, từ 4.0.0, annotation-based command registration chưa được hỗ trợ khi biên dịch GraalVM native image, trong khi programmatic registration được hỗ trợ. Nếu ứng dụng cần native image, hãy kiểm tra lại trạng thái issue tương ứng của đúng release trước khi chốt kiến trúc.

## 9. Phân biệt completion tương tác và completion của shell hệ điều hành

Completion bằng phím Tab trong ứng dụng Spring Shell được cung cấp bởi JLine-based shell. Nếu ứng dụng chỉ dùng `SystemShellRunner`, các tính năng nâng cao như lịch sử lệnh, tab completion và định dạng văn bản phong phú không có đầy đủ. Muốn dùng trải nghiệm JLine, ứng dụng cần có dependency `spring-shell-jline` và cấu hình runner tương ứng.

Spring Shell 4 đã loại bỏ command tích hợp `completion` dùng để tạo script completion như cách cũ. Phần completion ở cấp command vẫn giúp người dùng tương tác bằng Tab trong JLine; việc hoàn thành lệnh trực tiếp tại Bash, Zsh hoặc shell của hệ điều hành cần tích hợp theo cơ chế của shell đó.

Ở chế độ non-interactive, người dùng truyền command và tham số ngay khi khởi chạy ứng dụng. `CompletionProvider` không thay thế validation. Dù người dùng chọn giá trị từ gợi ý hay tự nhập, command vẫn phải kiểm tra dữ liệu và quyền truy cập trước khi thực hiện.

## 10. Kết hợp ba provider trong một command

Một command thực tế có thể cần cả ba cơ chế. Ví dụ `checkout` chỉ hoạt động sau khi kết nối, gợi ý tên dự án người dùng được phép truy cập và trả mã lỗi rõ ràng nếu dự án không tồn tại.

```java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class ProjectCommandConfiguration {

    @Bean
    Command checkoutCommand(
            ProjectService projectService,
            SessionState sessionState) {

        CommandArgument projectArgument = new CommandArgument.Builder()
                .index(0)
                .description("Tên dự án")
                .type(String.class)
                .build();

        CompletionProvider completionProvider = context -> {
            String prefix = Optional.ofNullable(context.currentWordUpToCursor())
                    .orElse("");
            return projectService.accessibleProjectNames().stream()
                    .filter(name -> name.startsWith(prefix))
                    .map(CompletionProposal::new)
                    .toList();
        };

        AvailabilityProvider availabilityProvider = () ->
                sessionState.isConnected()
                        ? Availability.available()
                        : Availability.unavailable("bạn chưa kết nối tới máy chủ");

        ExitStatusExceptionMapper exceptionMapper = exception -> {
            if (exception instanceof ProjectNotFoundException) {
                return new ExitStatus(3, "Không tìm thấy dự án");
            }
            return ExitStatus.EXECUTION_ERROR;
        };

        return Command.builder()
                .name("checkout")
                .description("Chuyển sang một dự án")
                .arguments(projectArgument)
                .completionProvider(completionProvider)
                .availabilityProvider(availabilityProvider)
                .exitStatusExceptionMapper(exceptionMapper)
                .execute(context -> {
                    String projectName = context.getArgumentByIndex(0).value();
                    projectService.checkout(projectName);
                    return "Đã chuyển sang dự án " + projectName;
                });
    }
}
```

Các kiểu `ProjectService`, `SessionState` và `ProjectNotFoundException` là thành phần nghiệp vụ của ứng dụng mẫu. Khi áp dụng vào dự án, thay chúng bằng service và exception thực tế. Cấu hình này thể hiện rõ ranh giới trách nhiệm: completion hỗ trợ nhập dữ liệu, availability giải thích điều kiện trước khi chạy, còn exception mapper chuyển lỗi thực thi thành trạng thái có thể xử lý.

## 11. Kiểm thử completion, availability và exception mapping

Không chỉ kiểm tra rằng command đã được đăng ký. Cần xác minh từng provider hoạt động theo trạng thái và dữ liệu đầu vào.

| Thành phần | Trường hợp cần kiểm tra |
| --- | --- |
| Completion | Prefix rỗng, prefix một phần, không có kết quả, dữ liệu có dấu cách và danh sách rỗng |
| Quyền trong completion | Không gợi ý dự án mà người dùng không được truy cập |
| Availability | Chưa kết nối, đã kết nối, mất kết nối và trạng thái thay đổi trong phiên |
| Availability reason | Câu giải thích ngắn, rõ, viết thường và không có dấu chấm cuối |
| Exception mapper | Exception nghiệp vụ, lỗi tham số và exception không dự kiến |
| Exit status | Đúng code và mô tả cho từng loại lỗi |
| Registry | Command được thêm một lần, gỡ đúng command và không còn xuất hiện trong help/completion |
| Runner | Hành vi trong JLine interactive và non-interactive mode |

Với unit test, gọi trực tiếp `CompletionProvider.apply(context)` bằng context phù hợp và kiểm tra danh sách proposal. Thực thi provider availability với các trạng thái session khác nhau và xác nhận kết quả `Availability`. Gọi mapper với từng exception để xác nhận `ExitStatus`.

Với integration test, khởi động Spring context và dùng `ShellTestClient` của phiên bản Spring Shell đang dùng để thực thi command. Xác minh command unavailable bị chặn trước khi chạy logic, lỗi được ánh xạ đúng và command có thể chạy sau khi trạng thái kết nối thay đổi.

Với end-to-end test, chạy JAR ở chế độ tương tác và không tương tác. Kiểm tra Tab completion trong JLine, output thông báo lỗi và exit code mà script nhận được. Không dùng test unit của provider để thay thế kiểm thử trải nghiệm terminal thực.

## 12. Lỗi thường gặp khi tùy biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Command bean không xuất hiện | Bean không được tạo hoặc không có kiểu `Command` | Kiểm tra cấu hình Spring và kiểu bean |
| Provider không được gọi | Command chưa gắn `completionProvider` hoặc runner không hỗ trợ Tab | Kiểm tra builder và dùng JLine-based shell |
| Gợi ý quá nhiều hoặc chậm | Provider tải toàn bộ dữ liệu hoặc truy vấn mạng mỗi lần Tab | Lọc theo prefix, giới hạn kết quả và dùng cache phù hợp |
| Command luôn unavailable | Availability provider kiểm tra sai trạng thái hoặc không cập nhật session | Kiểm tra service trạng thái và lý do trả về |
| Command vẫn chạy dù không có quyền | Chỉ dựa vào availability để bảo vệ nghiệp vụ | Kiểm tra quyền lại trong service khi thực thi |
| Lỗi luôn thành `EXECUTION_ERROR` | Mapper không nhận diện loại exception hoặc exception bị bọc | Kiểm tra kiểu exception và nguyên nhân lồng bên trong |
| Script nhận mã thành công khi có lỗi | Exception đã bị bắt và chuyển thành chuỗi bình thường trước mapper | Giữ exception hoặc trả `ExitStatus` thất bại theo thiết kế command |
| Không biên dịch sau khi nâng từ 3.x | Vẫn dùng `CommandExceptionResolver`, `ValueProvider` hoặc annotation cũ | Chuyển sang API 4.x tương ứng |

## 13. Bài thực hành tổng hợp

Tạo nhóm command quản lý dự án bằng programmatic registration:

1. Đăng ký `connect` và `checkout` dưới dạng bean `Command`.
2. Định nghĩa positional argument cho tên dự án của `checkout`.
3. Tạo `CompletionProvider` gợi ý những dự án người dùng có thể truy cập và lọc theo prefix.
4. Tạo `AvailabilityProvider` để `checkout` chỉ khả dụng khi session đã kết nối.
5. Tạo `ExitStatusExceptionMapper` ánh xạ lỗi không tìm thấy dự án thành mã lỗi nghiệp vụ; các lỗi không dự kiến trả mã thực thi chung.
6. Bổ sung command tùy chọn được đăng ký bằng `CommandRegistry.registerCommand` khi plugin bật và gỡ bằng `unregisterCommand` khi plugin tắt.
7. Kiểm thử từng provider và chạy command trong cả JLine interactive lẫn non-interactive mode.
8. Viết README giải thích điều kiện command, cách gợi ý hoạt động và bảng mã lỗi.

Sau bài thực hành, bạn cần giải thích được vì sao completion không thay validation, availability không thay kiểm tra quyền trong service, và vì sao exception mapper phải trả trạng thái rõ ràng để script xử lý đúng.

## 14. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Programmatic registration | Tạo và đăng ký bean `Command` bằng `Command.Builder` |
| Completion | Tạo proposal dựa trên ngữ cảnh và tiền tố người dùng nhập |
| Availability | Trả `Availability.available()` hoặc lý do unavailable đúng trạng thái |
| Exception mapping | Ánh xạ exception thành `ExitStatus` có code và mô tả ổn định |
| Registry | Đăng ký và gỡ command động mà không tạo bản trùng |
| Tương thích phiên bản | Phân biệt API 3.x cũ với API 4.x mới |
| Kiểm thử | Kiểm tra provider, registry, output và exit code trong môi trường phù hợp |

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [Spring Shell 4.0.3 — Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell 4.0.3 — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.3 — `Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [Spring Shell 4.0.3 — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
