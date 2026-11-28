# Chuyển completion, availability và ánh xạ lỗi sang API mới

Spring Shell 4.0 thiết kế lại cách khai báo command và các phần mở rộng gắn với command. Ba khu vực thường cần sửa khi nâng cấp từ 3.4.x là gợi ý hoàn thành lệnh (completion), điều kiện command có thể chạy (availability) và cách chuyển exception thành trạng thái thoát (exit status).

Trong Spring Shell 3, completion thường được khai báo riêng cho từng option, availability dùng annotation hoặc method riêng, còn xử lý exception được chia qua nhiều API. Spring Shell 4 gom các phần tùy chỉnh này vào hợp đồng của từng command: `CompletionProvider`, `AvailabilityProvider` và `ExitStatusExceptionMapper`.

Hướng dẫn này tập trung vào ba thay đổi đó. Trước khi chuyển, hãy nâng ứng dụng lên bản Spring Shell 3.4.x mới nhất để xử lý các deprecation và thay đổi trung gian. Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên; hãy nâng nền tảng dependency tương ứng trước khi sửa API command.

## 1. Bảng ánh xạ API cũ và mới

| Chức năng | Spring Shell 3.4.x | Spring Shell 4.x |
|---|---|---|
| Gợi ý giá trị của từng option | `ValueProvider`, `@ShellOption(valueProvider = ...)`, `@OptionValues` | `CompletionProvider` ở cấp command, gắn bằng `@Command(completionProvider = "...")` |
| Gợi ý enum và file | `EnumValueProvider`, `FileValueProvider` | `EnumCompletionProvider`, `FileNameCompletionProvider` |
| Gộp nhiều nguồn gợi ý | Các provider/resolver theo từng option | `CompositeCompletionProvider` |
| Availability theo annotation command | `@CommandAvailability(provider = "...")` | Thuộc tính `availabilityProvider` của `@Command` |
| Availability của legacy `@ShellMethod` | `@ShellMethodAvailability` hoặc method `<commandName>Availability()` | Chuyển command sang `@Command` và dùng `availabilityProvider` |
| Kiểu trả về availability | `Availability` | `Availability` |
| Xử lý exception | `CommandExceptionResolver`, `CommandHandlingResult`, `@ExceptionResolver`, `@ExitCode` | `ExitStatusExceptionMapper` trả về `ExitStatus` |
| Ánh xạ exit code bằng builder | `withErrorHandling().resolver(...)`, `withExitCode().map(...)` | `Command.Builder.exitStatusExceptionMapper(...)` |
| Trạng thái command | Các API exit code/result tách rời | `ExitStatus(code, description)` |

Các tên package cũng thay đổi. Trong Spring Shell 4, các API command mới nằm dưới `org.springframework.shell.core.command`; completion và availability có package con riêng. Không chỉ đổi tên import rồi giữ nguyên cách tổ chức cũ: cần chuyển logic về đúng cấp command mới.

## 2. Chuyển completion từ ValueProvider sang CompletionProvider

### Cách làm trong Spring Shell 3

Với command khai báo bằng `@ShellMethod`, mỗi option có thể chỉ định một `ValueProvider` qua `@ShellOption(valueProvider = ...)`. Provider nhận `CompletionContext` và trả về danh sách `CompletionProposal`.

Ví dụ provider gợi ý tên project:

~~~java
import java.util.List;

import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;

@Component
class ProjectNameValueProvider implements ValueProvider {

    private final ProjectCatalog projectCatalog;

    ProjectNameValueProvider(ProjectCatalog projectCatalog) {
        this.projectCatalog = projectCatalog;
    }

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        return projectCatalog.findProjectNames().stream()
                .map(CompletionProposal::new)
                .toList();
    }
}
~~~

Command gắn provider vào option:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
class ProjectCommands {

    @ShellMethod(key = "project deploy")
    public void deploy(
            @ShellOption(
                    value = "--name",
                    valueProvider = ProjectNameValueProvider.class)
            String projectName) {
        // Triển khai project.
    }
}
~~~

Với command registration dạng builder, completion cũng được đặt ở từng option. Cách làm này dễ hiểu khi các giá trị gợi ý độc lập, nhưng khó phối hợp khi gợi ý của option này phụ thuộc vào option khác.

### Cách làm trong Spring Shell 4

Spring Shell 4 dùng `CompletionProvider` ở cấp command. Provider nhận toàn bộ `CompletionContext`, có thể xem các từ đã nhập, từ hiện tại, command và option đang được hoàn thành. Nhờ đó, một provider có thể đưa ra gợi ý dựa trên nhiều option trong cùng một dòng lệnh.

Khai báo command và provider:

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.stereotype.Component;

@Component
class ProjectCommands {

    @Command(
            name = "project deploy",
            completionProvider = "projectDeployCompletion")
    public void deploy(
            @Option(longName = "name") String projectName,
            @Option(longName = "include-archived") boolean includeArchived) {
        // Triển khai project.
    }

    @Bean
    CompletionProvider projectDeployCompletion(ProjectCatalog projectCatalog) {
        return context -> {
            String prefix = Objects.requireNonNullElse(
                    context.currentWord(), "");
            boolean includeArchived =
                    context.getWords().contains("--include-archived");

            return projectCatalog.suggestProjectNames(
                            prefix, includeArchived)
                    .stream()
                    .map(name -> new CompletionProposal("--name=" + name))
                    .toList();
        };
    }
}
~~~

Trong ví dụ, provider xem các từ đã nhập để quyết định có đưa project đã lưu trữ vào danh sách hay không. `currentWord()` cung cấp từ tại vị trí con trỏ; `getWords()` cung cấp các từ trong buffer, không bao gồm tên command. `CompletionProposal` biểu diễn một gợi ý hoàn chỉnh mà shell có thể chèn vào dòng lệnh.

Tên bean được tham chiếu bởi thuộc tính `completionProvider` của `@Command`. Bean có thể là một lambda như ví dụ, hoặc một lớp riêng triển khai `CompletionProvider` nếu logic phức tạp và cần kiểm thử độc lập.

### Dùng các provider tích hợp sẵn

Spring Shell 4 cung cấp các provider thường dùng:

| Provider | Mục đích |
|---|---|
| `EnumCompletionProvider` | Gợi ý các giá trị của enum |
| `FileNameCompletionProvider` | Gợi ý file và thư mục từ working directory |
| `CompositeCompletionProvider` | Kết hợp nhiều provider |

Ví dụ kết hợp provider cho enum và tên người dùng:

~~~java
import java.util.List;

import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;

@Bean
CompletionProvider greetingCompletion() {
    CompletionProvider genderProvider =
            new EnumCompletionProvider(Gender.class, "--gender");

    CompletionProvider nameProvider = context -> List.of(
            new CompletionProposal("--name=Lan"),
            new CompletionProposal("--name=Minh"));

    return new CompositeCompletionProvider(
            nameProvider, genderProvider);
}
~~~

Khi dùng enum, kiểm tra tên option truyền vào `EnumCompletionProvider` trùng với `longName` của `@Option`. Với file path, có thể dùng `FileNameCompletionProvider` thay vì tự duyệt thư mục.

### Những API completion cần loại bỏ khi nâng cấp

- Bỏ các lớp tự viết chỉ triển khai `ValueProvider`; chuyển logic sang `CompletionProvider`.
- Bỏ thuộc tính `valueProvider` khỏi `@ShellOption` khi chuyển sang mô hình command mới.
- Bỏ `@OptionValues`; annotation này không còn được dùng trong Spring Shell 4.
- Thay `EnumValueProvider` bằng `EnumCompletionProvider`.
- Thay `FileValueProvider` bằng `FileNameCompletionProvider`.
- Lưu ý built-in command `completion` đã bị loại bỏ trong Spring Shell 4. `CompletionProvider` điều khiển gợi ý trong shell tương tác; cấu hình completion cho Bash, Zsh hoặc shell hệ điều hành khác cần theo cơ chế riêng của shell đó.

Đừng tạo một `CompletionProvider` riêng cho từng option nếu chúng có thể dùng chung logic. Một provider cấp command giúp nhìn thấy ngữ cảnh đầy đủ và tránh nhân bản bean.

## 3. Chuyển availability sang thuộc tính của @Command

Availability cho biết command có thể thực thi trong trạng thái hiện tại hay không. Ví dụ, `project deploy` chỉ chạy sau khi người dùng đã đăng nhập vào máy chủ hoặc đã chọn workspace.

### Cách làm trong Spring Shell 3

Với mô hình annotation command mới của Spring Shell 3, có thể đặt `@CommandAvailability` trên method command và chỉ định bean cung cấp trạng thái:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.Availability;
import org.springframework.shell.AvailabilityProvider;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.CommandAvailability;

@Command(command = "project deploy")
@CommandAvailability(provider = "deployAvailability")
public void deploy() {
    // Triển khai project.
}

@Bean
AvailabilityProvider deployAvailability() {
    return () -> connected
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
~~~

Nếu ứng dụng vẫn dùng legacy `@ShellMethod`, availability thường được xác định bằng method trả về `Availability`, chẳng hạn `deployAvailability()`, hoặc được chỉ định qua `@ShellMethodAvailability`.

### Cách làm trong Spring Shell 4

Trong Spring Shell 4, `@Command` có thuộc tính `availabilityProvider`. Không cần annotation riêng `@CommandAvailability`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
import org.springframework.stereotype.Component;

@Component
class ProjectCommands {

    private boolean connected;

    @Command(name = "project connect")
    public void connect() {
        // Thực hiện kết nối.
        connected = true;
    }

    @Command(
            name = "project deploy",
            availabilityProvider = "deployAvailability")
    public void deploy() {
        // Triển khai project.
    }

    @Bean
    AvailabilityProvider deployAvailability() {
        return () -> connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

`AvailabilityProvider` là một functional interface cung cấp `Availability`. Khi command chưa khả dụng, trả về `Availability.unavailable(reason)` với lý do ngắn gọn, dễ ghép vào câu thông báo của shell. Khi trạng thái hợp lệ, trả về `Availability.available()`.

Lý do nên là một cụm từ tự nhiên, viết thường và không có dấu chấm cuối, vì shell sẽ ghép nó sau cụm “because”. Ví dụ `you are not connected` tạo thông báo dễ đọc hơn một câu hoàn chỉnh có dấu chấm.

### Chuyển từ ShellMethodAvailability

Nếu code cũ dựa vào quy ước method như `deployAvailability()` hoặc dùng `@ShellMethodAvailability`, hãy:

1. Chuyển command từ `@ShellMethod` sang method được đánh dấu `@Command`.
2. Đưa logic kiểm tra trạng thái vào bean triển khai `AvailabilityProvider`.
3. Gắn bean bằng `@Command(availabilityProvider = "deployAvailability")`.
4. Xóa method availability cũ và annotation legacy sau khi không còn nơi sử dụng.

Một `AvailabilityProvider` có thể được dùng chung bởi nhiều command nếu chúng phụ thuộc cùng một trạng thái. Nếu mỗi command có quy tắc khác nhau, tạo provider riêng để lý do unavailable phản ánh đúng điều kiện.

### Availability không thay thế kiểm tra nghiệp vụ

Availability cải thiện trải nghiệm người dùng bằng cách báo trước command chưa thể chạy. Service nghiệp vụ vẫn cần kiểm tra điều kiện quan trọng tại thời điểm thực thi, vì trạng thái có thể thay đổi giữa lúc shell hiển thị gợi ý và lúc người dùng gọi command.

Ví dụ, provider có thể kiểm tra đã kết nối hay chưa, nhưng service triển khai vẫn nên xác nhận phiên kết nối còn hiệu lực và người dùng có quyền thực hiện thao tác.

## 4. Chuyển ánh xạ exception sang ExitStatusExceptionMapper

Spring Shell 3 phân chia xử lý lỗi qua nhiều API:

- `CommandExceptionResolver` nhận exception và trả về `CommandHandlingResult`.
- `CommandHandlingResult` có thể chứa thông báo và exit code.
- `CommandExitCode` mô tả các hàm ánh xạ exception sang số exit code.
- Với command annotation, `@ExceptionResolver` có thể xử lý exception; `@ExitCode` chỉ định mã thoát cho handler.
- Với builder, `.withErrorHandling().resolver(...)` và `.withExitCode().map(...)` là hai nhánh cấu hình riêng.

Spring Shell 4 đưa hợp đồng về một kiểu kết quả là `ExitStatus` và một mapper là `ExitStatusExceptionMapper`.

### Cách làm trong Spring Shell 3

Một resolver cũ có thể trả cả thông báo lẫn exit code:

~~~java
import org.springframework.shell.command.CommandExceptionResolver;
import org.springframework.shell.command.CommandHandlingResult;

class ProjectExceptionResolver implements CommandExceptionResolver {

    @Override
    public CommandHandlingResult resolve(Exception exception) {
        if (exception instanceof ProjectNotFoundException) {
            return CommandHandlingResult.of(
                    "Project was not found", 4);
        }
        return null;
    }
}
~~~

Resolver có thể được đăng ký thành bean toàn cục hoặc gắn vào một `CommandRegistration`. Với annotation command, `@ExceptionResolver` method có thể trả về `CommandHandlingResult`, `String` hoặc `void`, kết hợp `@ExitCode` để đặt mã thoát.

### Cách làm trong Spring Shell 4

`ExitStatusExceptionMapper` nhận một `Exception` và trả về `ExitStatus`. `ExitStatus` là record chứa hai thành phần: `code` và `description`.

~~~java
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;
import org.springframework.stereotype.Component;

@Component
class ProjectExitStatusExceptionMapper
        implements ExitStatusExceptionMapper {

    @Override
    public ExitStatus apply(Exception exception) {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(4, "Project was not found");
        }
        if (exception instanceof ProjectPermissionException) {
            return new ExitStatus(5, "Permission denied");
        }
        return ExitStatus.EXECUTION_ERROR;
    }
}
~~~

Gắn mapper vào command bằng tên bean:

~~~java
@Command(
        name = "project deploy",
        exitStatusExceptionMapper = "projectExitStatusExceptionMapper")
public void deploy(@Option(longName = "name") String projectName) {
    projectService.deploy(projectName);
}
~~~

Mapper cũng có thể khai báo dưới dạng bean lambda:

~~~java
@Bean
ExitStatusExceptionMapper projectExitStatusExceptionMapper() {
    return exception -> {
        if (exception instanceof ProjectNotFoundException) {
            return new ExitStatus(4, "Project was not found");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
~~~

Nếu đăng ký command bằng API lập trình, đặt mapper trực tiếp qua `Command.Builder.exitStatusExceptionMapper(...)`. Một mapper có thể được tái sử dụng cho nhiều command nếu cùng quy ước mã lỗi; nếu từng command cần thông điệp khác nhau, gắn mapper riêng để tránh ánh xạ quá rộng.

### Chọn ExitStatus phù hợp

Spring Shell 4 cung cấp các trạng thái dựng sẵn:

| Hằng số | Ý nghĩa |
|---|---|
| `ExitStatus.OK` | Command hoàn tất thành công |
| `ExitStatus.USAGE_ERROR` | Cách gọi command không hợp lệ |
| `ExitStatus.AVAILABILITY_ERROR` | Command hiện không khả dụng |
| `ExitStatus.EXECUTION_ERROR` | Lỗi trong khi thực thi |

Khi cần mã riêng, tạo `new ExitStatus(code, description)`. Chọn mã ổn định và mô tả ngắn gọn để script, CI hoặc người vận hành có thể xử lý nhất quán.

### Phân biệt command status và process exit code

`ExitStatusExceptionMapper` ánh xạ exception thành trạng thái của command. Tài liệu Spring Shell 4 nêu rõ command status khác mã thoát của tiến trình JVM; chỉ cấu hình mapper không tự cấu hình process exit code.

Nếu script hoặc CI cần dựa vào mã thoát của tiến trình, hãy kiểm tra riêng runner/entry point của ứng dụng và chạy integration test ở cấp tiến trình. Đừng kết luận rằng mapper trả `ExitStatus(4, ...)` thì mọi cách khởi chạy đều chắc chắn kết thúc JVM với mã `4`.

## 5. Chuyển exception resolver dạng annotation

Nếu ứng dụng 3.x dùng method resolver:

~~~java
@ExceptionResolver
@ExitCode(code = 5)
String handlePermissionError(ProjectPermissionException exception) {
    return "Permission denied";
}
~~~

Hãy chuyển logic phân loại exception sang `ExitStatusExceptionMapper`:

~~~java
@Bean
ExitStatusExceptionMapper projectExceptionMapper() {
    return exception -> {
        if (exception instanceof ProjectPermissionException) {
            return new ExitStatus(5, "Permission denied");
        }
        return ExitStatus.EXECUTION_ERROR;
    };
}
~~~

Sau đó tham chiếu bean từ `@Command(exitStatusExceptionMapper = "projectExceptionMapper")`. Nếu nhiều command dùng chung chính sách lỗi, chúng có thể cùng tham chiếu một bean mapper.

Không chuyển một method `@ExceptionResolver` thành một `@Command` mới. Exception mapper là thành phần xử lý kết quả lỗi, không phải command để người dùng gọi trực tiếp.

## 6. Chuyển command registration dạng builder

Với command registration lập trình trong Spring Shell 3, availability, completion và exception handling có thể nằm ở các nhánh builder khác nhau. Ví dụ cũ:

~~~java
CommandRegistration.builder()
        .command("project deploy")
        .withErrorHandling()
            .resolver(projectExceptionResolver)
            .and()
        .withExitCode()
            .map(ProjectNotFoundException.class, 4)
            .and()
        .build();
~~~

Trong Spring Shell 4, command được tạo bằng `Command.Builder`; các provider được gắn trực tiếp vào command:

~~~java
Command.builder()
        .name("project deploy")
        .availabilityProvider(deployAvailability)
        .completionProvider(projectCompletion)
        .exitStatusExceptionMapper(projectExitStatusMapper)
        .execute(context -> {
            // Thực hiện command.
            return ExitStatus.OK;
        });
~~~

Đoạn mã trên thể hiện vị trí của ba API mới. Khi chuyển command thật, giữ nguyên parser, option và phần thực thi nghiệp vụ theo mô hình `Command.Builder` của phiên bản 4, rồi gắn provider phù hợp. Không giữ các nhánh `withErrorHandling()` hoặc `withExitCode()` từ builder 3.x.

## 7. Checklist chuyển đổi theo từng command

Với mỗi command đang có completion, availability hoặc exception resolver, thực hiện lần lượt:

1. Ghi lại tên command, các option và hành vi hiện tại.
2. Liệt kê `ValueProvider`, `@OptionValues`, `EnumValueProvider` và `FileValueProvider` đang được dùng.
3. Tạo `CompletionProvider` ở cấp command; chuyển các gợi ý cũ vào provider mới.
4. Kiểm tra provider mới có cần đọc các option khác trong `CompletionContext` hay không.
5. Chuyển `@CommandAvailability` hoặc `@ShellMethodAvailability` sang `AvailabilityProvider`.
6. Gắn provider bằng `@Command(availabilityProvider = "...")`.
7. Liệt kê các `CommandExceptionResolver`, method `@ExceptionResolver`, `@ExitCode` và mapping `CommandExitCode`.
8. Chuyển logic ánh xạ sang `ExitStatusExceptionMapper`.
9. Gắn mapper bằng `@Command(exitStatusExceptionMapper = "...")` hoặc `Command.Builder`.
10. Xóa import, annotation, bean và dependency cũ sau khi không còn tham chiếu.
11. Kiểm thử cả command khả dụng và unavailable, completion theo từng option và các nhánh exception.
12. Kiểm tra riêng process exit code nếu command được gọi từ script hoặc CI.

## 8. Lỗi thường gặp khi nâng cấp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy `ValueProvider` | API completion cũ đã bị thay thế | Dùng `CompletionProvider` trong package completion mới |
| `@OptionValues` không còn tồn tại | Annotation đã bị loại bỏ | Chuyển logic gợi ý sang provider cấp command |
| Gợi ý không xuất hiện sau khi chuyển | Chưa gắn bean bằng `completionProvider` hoặc tên bean sai | Kiểm tra `@Command` và bean provider |
| Provider chỉ gợi ý đúng một option | Logic cũ vẫn giả định completion theo option | Đọc toàn bộ `CompletionContext` để xét ngữ cảnh liên quan |
| Không tìm thấy `EnumValueProvider` | Tên API đã đổi | Dùng `EnumCompletionProvider` |
| Không tìm thấy `FileValueProvider` | Tên API đã đổi | Dùng `FileNameCompletionProvider` |
| `@CommandAvailability` không được nhận diện | Annotation cũ đã được gộp vào `@Command` | Dùng `availabilityProvider` |
| Command luôn unavailable | Provider trả về `Availability.unavailable(...)` hoặc bean state không cập nhật | Kiểm tra trạng thái phiên và điều kiện trong provider |
| Lỗi không còn được chuyển thành mã như trước | Resolver cũ chưa được chuyển sang mapper mới | Dùng `ExitStatusExceptionMapper` và trả `ExitStatus` |
| `CommandHandlingResult` không còn tồn tại | Hợp đồng xử lý lỗi 3.x đã được thay thế | Trả `ExitStatus(code, description)` |
| Mapper không được áp dụng | `@Command` tham chiếu sai tên bean | Kiểm tra tên bean và context |
| Exit status đúng nhưng script nhận mã khác | Nhầm command status với process exit code | Kiểm thử runner và JVM ở cấp tiến trình |
| Không biên dịch sau khi nâng cấp | Vẫn còn import API cũ hoặc dependency nền chưa nâng | Tìm các symbol cũ và kiểm tra tương thích Spring Boot 4/Spring Framework 7 |

## 9. Kiểm thử sau khi chuyển đổi

### Completion

- Nhấn Tab tại từng option và xác nhận gợi ý đúng.
- Thử completion khi option khác đã được nhập.
- Thử prefix rỗng và prefix một phần.
- Kiểm tra giá trị enum, file path và provider tổng hợp.
- Xác nhận proposal chèn đúng cú pháp option và không làm mất các từ đã nhập.

### Availability

- Trước khi kết nối, command bị chặn và có lý do dễ hiểu.
- Sau khi kết nối, command trở nên khả dụng.
- Khi phiên hết hạn hoặc trạng thái bị thu hồi, command lại unavailable.
- Service nghiệp vụ vẫn kiểm tra điều kiện quan trọng khi thực thi.

### Exception mapping

- Exception nghiệp vụ được ánh xạ đúng `ExitStatus.code()`.
- Mô tả lỗi phù hợp và không làm lộ dữ liệu nhạy cảm.
- Exception chưa được phân loại đi vào trạng thái lỗi mặc định đã chọn.
- Nhiều command cùng dùng mapper không làm thay đổi quy tắc riêng ngoài dự kiến.
- Nếu CLI phục vụ script/CI, kiểm tra mã thoát của tiến trình thực tế riêng với `ExitStatus`.

## 10. Lộ trình nâng cấp an toàn

Không nên nâng đồng thời toàn bộ command, dependency và chính sách lỗi trong một thay đổi khó rà soát. Một lộ trình dễ kiểm chứng:

1. Nâng Spring Shell 3 lên bản 3.4.x mới nhất và xử lý deprecation.
2. Nâng Spring Boot/Spring Framework lên phiên bản tương thích Spring Shell 4.
3. Chuyển một command mẫu có đủ completion, availability và exception mapping.
4. Chạy test command và test process-level cho command đó.
5. Chuyển các command còn lại theo cùng mẫu.
6. Xóa API cũ khi toàn bộ tham chiếu đã được thay thế.
7. Chạy toàn bộ test suite và kiểm tra script/CI.

Giữ một bảng mã lỗi ổn định trong quá trình chuyển để script hiện có không phải thay đổi ngoài dự kiến. Nếu muốn đổi mã hoặc thông điệp, thực hiện như một thay đổi hợp đồng riêng và cập nhật tài liệu gọi CLI.

## 11. Bài tập thực hành

Có một ứng dụng quản lý project với ba command:

- `project connect`: tạo phiên kết nối.
- `project deploy`: chỉ chạy khi đã kết nối; option `--name` có completion từ danh sách project.
- `project delete`: nếu project không tồn tại, trả lỗi nghiệp vụ với mã riêng.

Hãy thực hiện:

1. Chuyển `ProjectNameValueProvider` từ 3.x thành `CompletionProvider` cấp command.
2. Làm cho completion của `--name` thay đổi theo option `--include-archived`.
3. Chuyển availability từ `@CommandAvailability` sang `@Command(availabilityProvider = "...")`.
4. Chuyển `CommandExceptionResolver` thành `ExitStatusExceptionMapper`.
5. Gắn mapper vào `project delete` bằng thuộc tính `exitStatusExceptionMapper`.
6. Kiểm thử completion, trạng thái kết nối, lỗi project không tồn tại và trạng thái mặc định.
7. Chạy ứng dụng theo đúng cách CI sử dụng và xác nhận process exit code.

Sau bài tập, hãy giải thích được vì sao completion và availability thuộc về command, vì sao `ExitStatus` chứa cả mã lẫn mô tả, và vì sao phải kiểm tra process exit code độc lập.

## Tài liệu tham khảo

- [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 3.4 – Completion](https://docs.spring.io/spring-shell/reference/3.4/completion.html)
- [Spring Shell 3.4 – Command Availability](https://docs.spring.io/spring-shell/reference/3.4/commands/availability.html)
- [Spring Shell 3.4 – Exception Resolving](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/resolving.html)
- [Spring Shell 3.4 – Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html)
- [Spring Shell 4.0.3 – Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [Spring Shell 4.0.3 – Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell 4.0.3 – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.3 API – CompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [Spring Shell 4.0.3 API – ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
