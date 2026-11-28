# Thông báo khi thiếu giá trị, thiếu đối số hoặc gặp tùy chọn lạ

## 1. Vì sao cần phân biệt các lỗi cú pháp?

Khi gọi một command, người dùng có thể quên một option bắt buộc, gõ tên option nhưng bỏ quên giá trị, thiếu argument theo vị trí hoặc nhập sai tên option. Những lỗi này có nguyên nhân khác nhau và cần thông báo giúp người dùng sửa đúng phần đầu vào.

Ví dụ, với command `user disable`:

| Trường hợp | Lệnh minh họa | Ý nghĩa |
|---|---|---|
| Thiếu option bắt buộc | `user disable alice` | Chưa cung cấp `--reason`. |
| Thiếu giá trị của option | `user disable alice --reason` | Có tên option nhưng không có giá trị theo sau. |
| Thiếu argument | `user disable --reason="nghỉ việc"` | Chưa cung cấp tên người dùng ở vị trí đầu tiên. |
| Tùy chọn lạ | `user disable alice --reason=x --reasn=y` | Tên option bị gõ sai hoặc không thuộc command. |
| Sai kiểu dữ liệu | `report run --limit=abc` | Giá trị không chuyển đổi được thành kiểu mà tham số yêu cầu. |

Không nên gộp tất cả thành thông báo chung như “lệnh không hợp lệ”. Thông báo tốt nên chỉ ra tên option hoặc argument, nêu điều kiện cần thỏa mãn và gợi ý cách xem cú pháp.

## 2. Spring Shell xử lý dòng lệnh như thế nào?

Trong Spring Shell 4.x, parser chuyển dòng văn bản thành một đối tượng `ParsedInput`, gồm tên command, subcommand, danh sách option và danh sách argument. Command executor tra cứu command trong registry, sau đó adapter ánh xạ dữ liệu đã phân tích vào các tham số của phương thức `@Command`.

~~~mermaid
flowchart TD
    A[Người dùng nhập dòng lệnh] --> B[CommandParser]
    B --> C[ParsedInput: command, options, arguments]
    C --> D[CommandRegistry tìm command]
    D --> E[Adapter ánh xạ tham số Java]
    E --> F[Bean Validation và chuyển đổi kiểu]
    F --> G{Đầu vào hợp lệ?}
    G -->|Có| H[Gọi phương thức command]
    G -->|Không| I[Thông báo lỗi / Usage error]
    H --> J[Output và ExitStatus]
~~~

Parser mặc định hỗ trợ hai cách truyền option:

~~~text
--key=value
--key value
-k=value
-k value
~~~

Option và argument có thể xuất hiện theo thứ tự khác nhau. Argument được đánh chỉ số từ `0` theo thứ tự các argument, không tính option. Để tránh nhầm lẫn khi có nhiều tham số, nên ưu tiên option có tên.

Option thông thường cần một giá trị, có thể đặt sau dấu `=` hoặc ở token kế tiếp. Option kiểu `boolean` hoặc `Boolean` là ngoại lệ: có thể dùng như một cờ, ví dụ `--notify` đặt giá trị thành `true`; cũng có thể truyền tường minh `--notify=false` hoặc `--notify false`. Nếu token tiếp theo của boolean không phải `true` hoặc `false`, token đó được xem là argument. Tên option ngắn không thể ghép thành nhóm như `-abc`; hãy truyền từng option riêng.

## 3. Khai báo đầu vào có quy tắc rõ ràng

Ví dụ sau khai báo command có một argument bắt buộc là tên người dùng, một option bắt buộc là lý do và một option boolean có giá trị mặc định:

~~~java
package com.example.users;

import java.util.List;
import java.util.Set;

import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class UserCommands {

    private static final Set<String> SUPPORTED_OPTIONS =
            Set.of("reason", "notify");

    @Command(
            name = "user disable",
            description = "Vô hiệu hóa một tài khoản",
            group = "User Management",
            help = "Cú pháp: user disable <username> --reason=<text> [--notify=true|false]")
    public String disable(
            @Argument(index = 0, description = "Tên tài khoản")
            @NotBlank String username,
            @Option(longName = "reason", required = true,
                    description = "Lý do vô hiệu hóa")
            @NotBlank String reason,
            @Option(longName = "notify", defaultValue = "false",
                    description = "Gửi thông báo cho người dùng")
            boolean notify,
            CommandContext context) {

        rejectUnknownOptions(context);

        // Trong ứng dụng thực tế, gọi UserService để thực hiện nghiệp vụ.
        return "Đã vô hiệu hóa tài khoản " + username
                + ". Lý do: " + reason
                + ". Gửi thông báo: " + notify;
    }

    private void rejectUnknownOptions(CommandContext context) {
        List<String> unknown = context.parsedInput().options().stream()
                .map(option -> option.longName() != null
                        ? option.longName()
                        : String.valueOf(option.shortName()))
                .filter(name -> !SUPPORTED_OPTIONS.contains(name))
                .toList();

        if (!unknown.isEmpty()) {
            String names = unknown.stream()
                    .map(name -> name.length() == 1 ? "-" + name : "--" + name)
                    .collect(java.util.stream.Collectors.joining(", "));
            throw new IllegalArgumentException(
                    "Tùy chọn không được hỗ trợ: " + names
                            + ". Dùng 'help user disable' để xem cú pháp.");
        }
    }
}
~~~

Để các annotation Bean Validation như `@NotBlank` hoạt động trong ứng dụng Spring Boot, hãy thêm implementation Bean Validation, thường là dependency `spring-boot-starter-validation`. Spring Shell tích hợp validation trên các tham số command và thực hiện kiểm tra trước khi gọi phương thức.

Có ba chi tiết quan trọng trong ví dụ:

- `@Option(required = true)` yêu cầu người dùng cung cấp option `--reason`. Nếu bỏ option, command không có đủ đầu vào theo khai báo.
- `@NotBlank` kiểm tra cả trường hợp giá trị rỗng hoặc chỉ chứa khoảng trắng. `--reason=""` là một giá trị đã được truyền, nhưng giá trị đó không hợp lệ.
- `@Argument` không có thuộc tính `required`. Nếu argument cần có nội dung, hãy đặt ràng buộc như `@NotBlank` hoặc kiểm tra thủ công. Có thể đặt `defaultValue` nếu argument thực sự được phép bỏ qua.

Ví dụ hợp lệ:

~~~text
shell:>user disable alice --reason="nghỉ việc" --notify=true
Đã vô hiệu hóa tài khoản alice. Lý do: nghỉ việc. Gửi thông báo: true

shell:>user disable alice --reason="nghỉ việc" --notify
Đã vô hiệu hóa tài khoản alice. Lý do: nghỉ việc. Gửi thông báo: true
~~~

## 4. Thiếu option bắt buộc

Một option có thể được đánh dấu bắt buộc bằng `required = true` trong `@Option`. Khi người dùng không truyền option đó, Spring Shell báo lỗi sử dụng và không thực hiện phần nghiệp vụ của command.

Với command ở trên, lệnh sau thiếu `--reason`:

~~~text
shell:>user disable alice --notify=true
~~~

Thông báo có thể có dạng:

~~~text
Thiếu option bắt buộc: --reason
~~~

Đây là nội dung minh họa ý nghĩa lỗi; câu chữ cụ thể phụ thuộc phiên bản, adapter và result handler đang dùng. Điểm cần giữ là thông báo nêu đúng tên option còn thiếu.

Không nên đặt `required = true` cho option đồng thời mong người dùng có thể bỏ qua vì đã có `defaultValue`. Hãy chọn một chính sách rõ ràng:

- Option bắt buộc: dùng `required = true`, không đặt giá trị mặc định.
- Option tùy chọn: để `required` ở giá trị mặc định `false`, có thể cung cấp `defaultValue`.

Nếu command cần biết người dùng có thực sự nhập option hay không, hãy kiểm tra trạng thái option trong `CommandContext` thay vì chỉ so sánh giá trị sau khi đã áp dụng mặc định.

## 5. Thiếu giá trị của option

Thiếu option và thiếu giá trị của option là hai lỗi khác nhau. Ví dụ:

~~~text
user disable alice
~~~

không có option `--reason`; còn:

~~~text
user disable alice --reason
~~~

có tên option nhưng không có giá trị được cung cấp rõ ràng.

Theo cú pháp Spring Shell 4.x, option được viết với giá trị ngay sau dấu `=` hoặc ở token kế tiếp. Nếu dùng dạng cách trắng và bỏ quên giá trị, token tiếp theo có thể bị parser tiêu thụ như giá trị của option. Vì vậy, trong script nên ưu tiên dạng `--key=value`, đặc biệt với option có nhiều giá trị hoặc giá trị có thể bắt đầu bằng dấu gạch ngang.

Một giá trị rỗng được đặt tường minh, ví dụ:

~~~text
user disable alice --reason=""
~~~

khác với việc bỏ hẳn giá trị. Trường hợp này được chuyển vào tham số rồi bị `@NotBlank` từ chối. Thông báo validation thường chỉ rõ tham số nào không thỏa điều kiện, ví dụ:

~~~text
The following constraints were not met:
    --reason: must not be blank
~~~

Với giá trị có khoảng trắng, đặt toàn bộ giá trị trong dấu nháy đơn hoặc nháy kép:

~~~text
user disable alice --reason="nghỉ việc theo yêu cầu"
~~~

Nếu giá trị cần chứa chính dấu nháy đang dùng để bao quanh, hãy escape dấu nháy đó bằng `\` hoặc chọn loại dấu nháy còn lại. Một dấu nháy không cân bằng cũng là lỗi cú pháp đầu vào.

## 6. Thiếu argument theo vị trí

Argument là giá trị không có tên option và được ánh xạ theo chỉ số. Với khai báo:

~~~java
@Argument(index = 0, description = "Tên tài khoản")
@NotBlank String username
~~~

giá trị đầu tiên sau tên command được ánh xạ vào `username`. Khi gọi:

~~~text
shell:>user disable --reason="nghỉ việc"
~~~

argument `username` bị thiếu. Vì tham số được đánh dấu `@NotBlank`, validation từ chối giá trị null hoặc chuỗi trống trước khi thân phương thức chạy.

Thông báo minh họa:

~~~text
The following constraints were not met:
    username: must not be blank
~~~

Đừng tự thêm `required = true` vào `@Argument`: annotation này không có thuộc tính đó. Dùng `@NotBlank`, `@NotNull`, `@Size` hoặc kiểm tra nghiệp vụ phù hợp với kiểu dữ liệu. Nếu argument thực sự tùy chọn, khai báo `defaultValue` và xử lý giá trị mặc định một cách tường minh.

Khi command nhận một danh sách argument, dùng `@Arguments` trên mảng hoặc collection. Có thể giới hạn số argument bằng thuộc tính `arity`; nếu command cần ít nhất một phần tử, hãy kiểm tra trường hợp collection rỗng trước khi xử lý.

## 7. Gặp tùy chọn lạ hoặc gõ sai tên option

Một lỗi phổ biến là gõ sai tên option, ví dụ `--reasn` thay vì `--reason`. Tùy chọn lạ là tên không nằm trong danh sách option mà command công bố. Đây không phải lỗi “không tìm thấy command”: tên command vẫn đúng, nhưng phần đầu vào phía sau không khớp hợp đồng của command.

Trong Spring Shell 4.x, `CommandContext` cung cấp `parsedInput()` để đọc các option mà parser đã nhận. Ví dụ trong phần 3 so sánh các tên option được nhập với danh sách `SUPPORTED_OPTIONS`, rồi ném lỗi có nội dung rõ ràng nếu phát hiện tên lạ. Kết quả minh họa:

~~~text
shell:>user disable alice --reason="nghỉ việc" --reasn=x
Tùy chọn không được hỗ trợ: --reasn. Dùng 'help user disable' để xem cú pháp.
~~~

Đây là bước kiểm tra tường minh của ứng dụng khi đầu vào đã được phân tích và phương thức command được gọi. Một parser hoặc adapter cũng có thể từ chối option không được khai báo trước khi phương thức chạy; trong trường hợp đó, thông báo mặc định của shell sẽ xuất hiện và đoạn kiểm tra trong phương thức không được thực thi. Nếu ứng dụng cần chính sách parsing thống nhất trên toàn shell, Spring Shell 4.x cho phép thay parser mặc định bằng cách triển khai `CommandParser` và đăng ký parser tùy chỉnh thành Spring bean.

Khi viết kiểm tra tên option thủ công:

- Lấy option đã phân tích từ `context.parsedInput().options()`.
- So sánh tên dài hoặc tên ngắn với các option command cho phép.
- Báo tất cả tên lạ trong cùng một thông báo nếu có thể.
- Gợi ý `help <command>` để người dùng xem tên hợp lệ.
- Không âm thầm bỏ qua option lạ, vì một lỗi chính tả có thể khiến command chạy với giá trị mặc định ngoài ý muốn.

Nếu command có tên option ngắn, phải đưa cả tên ngắn vào danh sách cho phép. Không chỉ so sánh `longName()` rồi bỏ qua trường hợp option dùng một ký tự.

## 8. Sai kiểu dữ liệu và vi phạm validation

Ngay cả khi tên option đúng và giá trị đã được cung cấp, dữ liệu vẫn có thể không hợp lệ.

Ví dụ, một command nhận giới hạn số bản ghi:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "report run", description = "Chạy báo cáo")
public String run(
        @Option(longName = "limit", defaultValue = "100")
        @Min(1) @Max(1000) int limit) {
    return "Đang tạo báo cáo với tối đa " + limit + " bản ghi";
}
~~~

Các trường hợp khác nhau:

| Đầu vào | Lỗi |
|---|---|
| `report run --limit=abc` | Không chuyển được chuỗi `abc` thành `int`. |
| `report run --limit=0` | Chuyển đổi thành công nhưng vi phạm `@Min(1)`. |
| `report run --limit=5000` | Chuyển đổi thành công nhưng vi phạm `@Max(1000)`. |
| `report run` | Dùng giá trị mặc định `100`. |

Chuyển đổi kiểu và validation là hai bước khác nhau. Chuyển đổi xác nhận dữ liệu có thể biểu diễn bằng kiểu Java; validation xác nhận giá trị đó có nằm trong miền nghiệp vụ được chấp nhận hay không.

## 9. Viết thông báo lỗi có thể hành động

Thông báo lỗi nên cho người dùng biết điều gì cần sửa. Một mẫu hữu ích là:

~~~text
Lỗi: <vấn đề cụ thể>
Cách sửa: <cú pháp hoặc giá trị được chấp nhận>
Trợ giúp: help <tên-command>
~~~

Ví dụ:

~~~text
Lỗi: thiếu option bắt buộc --reason.
Cách sửa: user disable <username> --reason=<text>.
Trợ giúp: help user disable
~~~

Với lỗi validation, nêu tên tham số và điều kiện cần thỏa mãn, ví dụ “`--limit` phải nằm trong khoảng 1 đến 1000”. Với lỗi chuyển đổi kiểu, nói rõ kiểu mong đợi, ví dụ “`--limit` cần là số nguyên”. Với option lạ, nhắc lại tên đã nhập và chỉ ra các tên hợp lệ nếu danh sách ngắn.

Không đưa stack trace, thông tin kết nối, token hoặc dữ liệu nhạy cảm vào thông báo thông thường. Có thể ghi chi tiết kỹ thuật vào log và để chế độ debug hỗ trợ chẩn đoán khi phát triển.

### Ánh xạ ngoại lệ sang trạng thái sử dụng

`ExitStatusExceptionMapper` ánh xạ ngoại lệ phát sinh trong quá trình thực thi command sang `ExitStatus` và thông báo phù hợp. Ví dụ sau coi `IllegalArgumentException` do kiểm tra đầu vào là lỗi sử dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.ParameterValidationException;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class CliErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper cliExitStatusMapper() {
        return exception -> {
            if (exception instanceof IllegalArgumentException) {
                return new ExitStatus(2, exception.getMessage());
            }
            if (exception instanceof ParameterValidationException) {
                return new ExitStatus(2, exception.getMessage());
            }
            return ExitStatus.EXECUTION_ERROR;
        };
    }
}
~~~

Tham chiếu mapper trong `@Command`:

~~~java
@Command(
        name = "user disable",
        description = "Vô hiệu hóa một tài khoản",
        exitStatusExceptionMapper = "cliExitStatusMapper")
~~~

Mã `2` trong ví dụ là quy ước của ứng dụng, không phải mã bắt buộc cho mọi lỗi sử dụng trong tất cả ứng dụng Spring Shell. Hãy công bố bảng mã thoát của CLI và giữ nó ổn định cho script. Mapper này xử lý ngoại lệ trong quá trình thực thi command; các lỗi cú pháp hoặc lỗi phân tích đầu vào có thể được shell xử lý ở giai đoạn trước đó.

## 10. Dùng help và kiểm thử các trường hợp lỗi

Lệnh built-in `help` giúp người dùng xem danh sách command và chi tiết cú pháp:

~~~text
shell:>help
shell:>help user disable
~~~

Thông tin trợ giúp nên mô tả option bắt buộc, kiểu dữ liệu, giá trị mặc định và argument theo vị trí. Thuộc tính `description` và `help` trong `@Command`, cùng mô tả trên `@Option` và `@Argument`, giúp tài liệu được sinh từ chính khai báo command.

Kiểm thử command nên bao gồm cả đầu vào đúng và sai:

1. Đầu vào hợp lệ: command được gọi và trả output mong muốn.
2. Thiếu option bắt buộc: thông báo chỉ ra đúng tên option còn thiếu.
3. Option không có giá trị: command không thực hiện nghiệp vụ với dữ liệu bị thiếu.
4. Giá trị rỗng hoặc chỉ có khoảng trắng: Bean Validation từ chối theo ràng buộc.
5. Thiếu argument: thông báo chỉ rõ tham số vị trí cần có.
6. Option lạ: tên gõ sai được phát hiện và hướng dẫn cách xem help.
7. Sai kiểu hoặc ngoài miền hợp lệ: thông báo chỉ rõ kiểu hoặc giới hạn mong đợi.
8. Chế độ non-interactive: xác nhận command trả mã thoát khác `0` khi đầu vào không hợp lệ.

Spring Shell cung cấp `@ShellTest`, `ShellTestClient` và `ShellAssertions` để gửi command và kiểm tra nội dung màn hình. Với kiểm tra hợp đồng, nên xác nhận cả nội dung thông báo lẫn việc phương thức nghiệp vụ không bị gọi khi đầu vào không hợp lệ. Với lỗi option lạ được kiểm tra bằng `CommandContext`, thêm trường hợp có tên option dài sai chính tả và trường hợp dùng tên ngắn không được hỗ trợ.

## 11. Khi nào cần thay parser mặc định?

Hầu hết ứng dụng có thể dùng parser mặc định và khai báo option/argument rõ ràng. Chỉ nên thay parser khi cú pháp chung của ứng dụng có yêu cầu đặc biệt, chẳng hạn cách nhóm token, quy tắc quoting riêng hoặc chính sách nghiêm ngặt về token chưa được nhận diện.

Spring Shell 4.x cung cấp interface `CommandParser` với phương thức `parse(String)` trả về `ParsedInput`. Có thể triển khai parser riêng và đăng ký thành bean trong Spring context. Parser tùy chỉnh phải giữ đúng cấu trúc dữ liệu command, option và argument mà command executor cần; vì vậy cần kiểm thử kỹ các trường hợp có khoảng trắng, dấu nháy, dấu gạch ngang, boolean, option thiếu giá trị và argument theo vị trí.

Đừng thay parser chỉ để sửa một thông báo. Trước tiên, khai báo đúng `required`, `defaultValue`, `@Argument`, validation và help. Dùng parser tùy chỉnh khi chính sách phân tích token thực sự khác với quy tắc mặc định.

## Kết luận

Thông báo lỗi tốt bắt đầu từ việc phân biệt đúng nguyên nhân: thiếu option bắt buộc, thiếu giá trị của option, thiếu argument, tên option không được hỗ trợ, sai kiểu hoặc vi phạm validation. Spring Shell 4.x cung cấp `@Option`, `@Argument`, Bean Validation, `CommandContext`, `ParsedInput` và `CommandParser` để xây dựng quy tắc đầu vào rõ ràng. Hãy khai báo yêu cầu ngay trên tham số, đưa ra thông báo có thể hành động, kiểm thử từng trường hợp lỗi và giữ mã thoát nhất quán để cả người dùng lẫn script đều biết cách xử lý.

## Tài liệu tham khảo

- [Spring Shell 4.x – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell 4.x – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell 4.x – Option Help](https://docs.spring.io/spring-shell/reference/commands/help.html)
- [Spring Shell 4.x – Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell 4.0.4 API – CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell 4.0.4 API – ParsedInput](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ParsedInput.html)
- [Spring Shell 4.0.4 API – CommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html)
- [Spring Shell 4.x – Testing](https://docs.spring.io/spring-shell/reference/testing.html)
