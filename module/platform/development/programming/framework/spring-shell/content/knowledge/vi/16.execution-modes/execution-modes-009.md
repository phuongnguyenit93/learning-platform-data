# InteractionMode ở nhánh cũ và phạm vi API đã bỏ ở 4.x

Trong các phiên bản Spring Shell 3.x, `InteractionMode` cho phép đánh dấu command chỉ nên xuất hiện khi shell chạy ở chế độ tương tác hoặc không tương tác. Cách này hữu ích khi một command chỉ có ý nghĩa trong phiên REPL đang mở, còn command khác được thiết kế để chạy một lần từ tham số tiến trình hoặc trong automation.

Spring Shell 4.x đã thay đổi mô hình. Ứng dụng chọn chế độ shell ngay khi khởi động; command không còn được gắn nhãn interactive hoặc non-interactive. Enum `InteractionMode` và cơ chế lọc command theo enum này đã bị loại bỏ. Vì vậy, khi nâng cấp, cần phân biệt hai quyết định: chọn cách shell chạy và quyết định command nào được đăng ký trong ứng dụng.

## 1. InteractionMode giải quyết vấn đề gì trong 3.x?

Một shell có thể chạy như REPL: ứng dụng giữ prompt mở để người dùng nhập nhiều command. Nó cũng có thể chạy như CLI một lần: nhận command qua tham số tiến trình, thực thi rồi kết thúc.

Không phải command nào cũng phù hợp với cả hai cách chạy. Ví dụ:

- `clear-screen` chỉ có ý nghĩa khi đang có terminal tương tác.
- `exit` dùng để thoát một phiên REPL; khi command chạy một lần rồi tiến trình tự kết thúc, lệnh này không còn tác dụng.
- `report export` có thể chạy từ terminal, script hoặc pipeline tự động vì mọi đầu vào đều được truyền qua argument và option.

Trong Spring Shell 3.x, `InteractionMode` biểu diễn phạm vi chế độ mà command được phép xuất hiện:

| Giá trị | Ý nghĩa |
|---|---|
| `ALL` | Command phù hợp với mọi chế độ |
| `INTERACTIVE` | Command chỉ dành cho shell tương tác, có phiên chạy liên tục |
| `NONINTERACTIVE` | Command chỉ dành cho shell không tương tác, thực thi rồi kết thúc |

Enum nằm trong package `org.springframework.shell.context`:

~~~java
import org.springframework.shell.context.InteractionMode;
~~~

`InteractionMode` là metadata về khả năng sử dụng command theo chế độ shell. Nó không phải cờ để bật/tắt toàn bộ shell và cũng không phải cơ chế phân quyền bảo mật.

## 2. Khai báo InteractionMode bằng @Command trong 3.4

Ở API annotation mới của Spring Shell 3.4, `@Command` có thuộc tính `interactionMode`. Thuộc tính này là mảng `InteractionMode[]`, vì một command có thể được chỉ định cho một hoặc nhiều chế độ.

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class ShellCommands {

    @Command(
            command = "screen clear",
            description = "Clear the interactive terminal",
            interactionMode = { InteractionMode.INTERACTIVE }
    )
    public void clearScreen() {
        // Thao tác làm sạch màn hình terminal.
    }

    @Command(
            command = "report export",
            description = "Export a report",
            interactionMode = { InteractionMode.NONINTERACTIVE }
    )
    public void exportReport() {
        // Thực hiện export bằng các argument/option đã khai báo.
    }

    @Command(
            command = "version",
            description = "Show application version",
            interactionMode = { InteractionMode.ALL }
    )
    public String version() {
        return "1.0.0";
    }
}
~~~

Trong ví dụ, `screen clear` chỉ phù hợp với REPL, `report export` dành cho lần chạy không tương tác và `version` dùng được trong cả hai chế độ. Giá trị `interactionMode` có thể khai báo ở cấp lớp để các command bên trong kế thừa, hoặc khai báo riêng ở từng method để ghi đè phạm vi chung.

Nếu không chỉ định `interactionMode`, annotation 3.4 để mảng này rỗng, nghĩa là không đặt một giới hạn chế độ riêng cho command. `ALL` là giá trị tường minh khi muốn diễn đạt rằng command hỗ trợ mọi chế độ.

## 3. Cách khai báo trong API cũ và CommandRegistration

Trong API annotation cũ, `@ShellMethod` cũng có thuộc tính `interactionMode`. Ví dụ:

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.stereotype.Component;

@Component
class LegacyShellCommands {

    @ShellMethod(
            key = "clear-screen",
            value = "Clear the interactive terminal",
            interactionMode = InteractionMode.INTERACTIVE
    )
    public void clearScreen() {
        // Thao tác làm sạch màn hình terminal.
    }
}
~~~

`@ShellMethod` là API annotation legacy của dòng 3.x và đã bị loại bỏ trong 4.x. Nếu ứng dụng dùng annotation `@Command` mới của 3.4, hãy dùng thuộc tính mảng như ví dụ trước.

Với command đăng ký bằng `CommandRegistration`, Spring Shell 3.x cung cấp `CommandRegistration.Builder.interactionMode(InteractionMode)`:

~~~java
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.context.InteractionMode;

CommandRegistration.Builder builder = CommandRegistration.builder()
        .command("report export")
        .interactionMode(InteractionMode.NONINTERACTIVE);

// Tiếp tục khai báo target, argument và option cho command,
// sau đó gọi builder.build() để tạo registration.
~~~

Builder nhận một giá trị `InteractionMode` cho command registration. Đây là một cách cấu hình tương đương với việc gắn mode vào annotation.

## 4. InteractionMode ảnh hưởng đến command như thế nào?

Trong nhánh 3.x, framework dùng metadata này để lọc command theo chế độ shell đang hoạt động. Một command được đánh dấu `INTERACTIVE` không được đưa vào tập command dành cho chế độ `NONINTERACTIVE`, và ngược lại.

| Command | Chế độ shell | Kết quả theo metadata |
|---|---|---|
| `clear-screen` (`INTERACTIVE`) | Interactive | Có thể sử dụng |
| `clear-screen` (`INTERACTIVE`) | Non-interactive | Không khả dụng trong chế độ này |
| `report export` (`NONINTERACTIVE`) | Non-interactive | Có thể sử dụng |
| `report export` (`NONINTERACTIVE`) | Interactive | Không khả dụng trong chế độ này |
| `version` (`ALL`) | Interactive hoặc non-interactive | Có thể sử dụng trong cả hai |

Đây là quy tắc khám phá và khả dụng của command, không phải bảo vệ thao tác nhạy cảm. Nếu command xóa dữ liệu hoặc thay đổi tài khoản, ứng dụng vẫn phải kiểm tra quyền trong service dù command chỉ được đăng ký cho một chế độ.

## 5. Phân biệt InteractionMode với ShellRunner

Hai khái niệm này có liên quan nhưng giải quyết hai tầng khác nhau:

- `ShellRunner` quyết định ứng dụng nhận và xử lý đầu vào theo cách nào.
- `InteractionMode` trong 3.x giới hạn command nào phù hợp với chế độ shell đang chạy.

Trong Spring Shell 3.3 và 3.4, các runner gồm `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner`. Các thuộc tính cấu hình tương ứng nằm dưới `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled`. Từ 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định; những runner khác cần được bật theo cấu hình ứng dụng.

Ví dụ bật interactive runner và script runner:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true
~~~

Sau khi runner được chọn, `InteractionMode` mới quyết định command nào được coi là phù hợp với chế độ đó. Không dùng `InteractionMode` để bật runner; cũng không dùng thuộc tính runner để thay thế metadata command trong ứng dụng 3.x.

## 6. Thay đổi trong Spring Shell 4.x

Spring Shell 4.x chuyển sang mô hình mỗi ứng dụng chọn một chế độ shell khi khởi động:

- Interactive mode được bật mặc định.
- Muốn chạy command từ tham số tiến trình rồi thoát, đặt `spring.shell.interactive.enabled=false`.
- Ứng dụng dùng một `ShellRunner` được chọn tại startup.
- Tất cả command đã đăng ký đều có thể dùng trong cả hai chế độ.
- Command không còn thuộc tính để đánh dấu riêng `INTERACTIVE` hoặc `NONINTERACTIVE`.

Ví dụ cấu hình chạy không tương tác:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Khi cấu hình này được áp dụng, `NonInteractiveShellRunner` thực thi command được truyền qua tham số tiến trình rồi kết thúc ứng dụng. Trong 4.0.4, interactive mode vẫn là mặc định kể cả khi có command-line arguments; nếu muốn xử lý command từ process arguments, phải tắt interactive mode một cách tường minh.

Điểm thay đổi quan trọng là phạm vi lựa chọn. Trong 3.x, có thể bật nhiều runner và gắn phạm vi cho từng command. Trong 4.x, chọn một cách chạy cho toàn ứng dụng và command đều hoạt động trong cách chạy đó.

## 7. InteractionMode đã bị loại bỏ khỏi API 4.x

Migration guide 4.x nêu rõ command không còn được đánh dấu interactive hoặc non-interactive. Tất cả command được dùng trong cả hai chế độ và thực thi theo mode mà shell đã khởi động. Vì vậy enum `InteractionMode` không còn được sử dụng và đã bị xóa.

Các đoạn code 3.x sau không còn hợp lệ khi chuyển nguyên trạng sang 4.x:

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.command.annotation.Command;

@Command(
        command = "screen clear",
        interactionMode = { InteractionMode.INTERACTIVE }
)
public void clearScreen() {
    // ...
}
~~~

~~~java
CommandRegistration.builder()
        .command("report export")
        .interactionMode(InteractionMode.NONINTERACTIVE);
~~~

API annotation 4.x dùng `org.springframework.shell.core.command.annotation.Command` và không có thuộc tính `interactionMode`. Command model lập trình 4.x dùng `Command.Builder` và `CommandRegistry`; builder cũng không cung cấp phương thức `interactionMode(...)`.

Không chỉ xóa import `InteractionMode` để làm code biên dịch. Hãy xác định lý do command từng bị giới hạn ở một mode, sau đó chọn cách thiết kế phù hợp với mô hình 4.x.

## 8. Chọn cách thay thế khi nâng cấp lên 4.x

Không có một thuộc tính 4.x tương đương trực tiếp với `InteractionMode`. Cách thay thế phụ thuộc mục tiêu của command:

| Mục tiêu trong code 3.x | Cách xử lý trong 4.x |
|---|---|
| Chọn interactive hay non-interactive cho toàn ứng dụng | Cấu hình `spring.shell.interactive.enabled` |
| Chỉ đăng ký command ở bản ứng dụng interactive | Điều kiện hóa bean command bằng profile hoặc `@ConditionalOnProperty` |
| Command chạy được ở cả hai mode nhưng cần đầu vào khác nhau | Dùng argument/option tường minh; tránh phụ thuộc prompt trong batch |
| Command chỉ có ý nghĩa với terminal có tương tác | Kiểm tra khả năng terminal tại lúc thực thi và trả thông báo rõ nếu không hỗ trợ |
| Command phụ thuộc trạng thái runtime như đăng nhập/kết nối | Dùng `AvailabilityProvider` cho điều kiện trạng thái; không xem đây là thay thế trực tiếp cho mode |

Nếu muốn chỉ đăng ký command phục vụ giao diện terminal khi interactive mode được bật, có thể điều kiện hóa bean chứa command:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "spring.shell.interactive",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
class InteractiveOnlyCommands {

    @Command(
            name = "screen clear",
            description = "Clear the interactive terminal"
    )
    public void clearScreen() {
        // Gọi chức năng làm sạch màn hình khi có terminal phù hợp.
    }
}
~~~

Điều kiện này được đánh giá khi Spring tạo application context. Nó phù hợp khi ứng dụng biết chế độ khởi động từ cấu hình. Nếu cần cùng một command bean tồn tại ở cả hai mode, hãy giữ command đăng ký và tự kiểm tra khả năng thực hiện ở thời điểm chạy.

Đối với command dùng trong script hoặc CI, nên nhận toàn bộ dữ liệu qua argument/option, không chờ người dùng nhập thêm qua prompt. Ví dụ:

~~~text
report export --period=monthly --output=reports/monthly.csv
~~~

Nếu command cần xác nhận thao tác nguy hiểm, cung cấp option tường minh như `--confirm=true` hoặc thiết kế một bước xác nhận riêng trong quy trình. Không giả định prompt luôn có người dùng phản hồi khi command chạy trong automation.

## 9. AvailabilityProvider không phải InteractionMode mới

Spring Shell 4.x có `Availability` và `AvailabilityProvider` để quyết định command có thể chạy dựa trên trạng thái hiện tại, chẳng hạn đã đăng nhập, đã kết nối hoặc đã chọn project hay chưa.

Đây là điều kiện runtime của ứng dụng. Nó khác với `InteractionMode` cũ:

| Cơ chế | Điều kiện được kiểm tra |
|---|---|
| `InteractionMode` trong 3.x | Shell đang ở interactive hay non-interactive |
| `AvailabilityProvider` trong 4.x | Trạng thái hiện tại của ứng dụng có cho phép command chạy không |
| `spring.shell.interactive.enabled` trong 4.x | Toàn ứng dụng khởi động bằng runner interactive hay non-interactive |

Không nên tạo `AvailabilityProvider` chỉ để mô phỏng `InteractionMode`. Trong 4.x, nếu yêu cầu là chọn chế độ chạy, cấu hình runner. Nếu yêu cầu là trạng thái nghiệp vụ, dùng availability. Nếu yêu cầu là đăng ký command khác nhau theo cấu hình, điều kiện hóa bean hoặc cấu hình ứng dụng.

## 10. Checklist chuyển từ 3.x sang 4.x

Khi nâng cấp, rà soát lần lượt:

1. Tìm import `org.springframework.shell.context.InteractionMode`.
2. Tìm thuộc tính `interactionMode` trên `@Command` hoặc `@ShellMethod`.
3. Tìm lời gọi `.interactionMode(...)` trên `CommandRegistration.Builder`.
4. Phân loại command theo mục đích: command REPL, command automation hay command dùng chung.
5. Chọn mode toàn ứng dụng bằng `spring.shell.interactive.enabled`.
6. Nếu command cần được đăng ký có điều kiện, dùng Spring profile hoặc `@ConditionalOnProperty`.
7. Với command automation, bảo đảm mọi đầu vào bắt buộc được truyền qua argument/option.
8. Kiểm tra command không còn phụ thuộc prompt, history hoặc trạng thái terminal nếu chạy non-interactive.
9. Kiểm thử cả ứng dụng interactive lẫn non-interactive sau khi chuyển đổi.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biên dịch sau khi nâng lên 4.x | Còn import hoặc tham chiếu `InteractionMode` | Xóa metadata mode cũ và thiết kế lại điều kiện đăng ký/thực thi |
| `@Command` báo không có thuộc tính `interactionMode` | Dùng annotation API 4.x nhưng giữ cấu hình 3.x | Chọn mode toàn ứng dụng hoặc điều kiện hóa bean |
| `.interactionMode(...)` không còn tồn tại | Đang dùng API `CommandRegistration.Builder` cũ | Chuyển command sang `Command.Builder`/`CommandRegistry` |
| Ứng dụng vẫn mở prompt dù đã truyền command-line arguments | Trong 4.x interactive mode bật mặc định | Đặt `spring.shell.interactive.enabled=false` |
| Command REPL vẫn xuất hiện trong bản batch | 4.x đăng ký command dùng chung cho cả hai mode | Dùng profile hoặc `@ConditionalOnProperty` nếu cần loại command khỏi bản batch |
| Command automation chờ nhập dữ liệu | Code phụ thuộc prompt hoặc input tương tác | Truyền dữ liệu bằng argument/option và xử lý thiếu đầu vào rõ ràng |
| Dùng AvailabilityProvider để thay InteractionMode | Nhầm điều kiện nghiệp vụ với chế độ shell | Dùng runner cho mode, availability cho trạng thái nghiệp vụ |
| Coi command bị ẩn là đã được bảo vệ | Nhầm lọc command với authorization | Kiểm tra quyền tại service hoặc hệ thống đích |

## 12. Bài tập thực hành

Giả sử ứng dụng Spring Shell 3.4 có ba command:

- `clear-screen`: chỉ dùng trong REPL.
- `report export`: chạy từ script hoặc tham số tiến trình.
- `version`: dùng trong cả hai mode.

Thực hiện:

1. Khai báo `clear-screen` với `InteractionMode.INTERACTIVE`.
2. Khai báo `report export` với `InteractionMode.NONINTERACTIVE`.
3. Khai báo `version` với `InteractionMode.ALL`.
4. Thử gọi từng command trong interactive và non-interactive runner để quan sát command nào khả dụng.
5. Chuyển project sang Spring Shell 4.x và xóa mọi tham chiếu `InteractionMode`.
6. Cấu hình non-interactive mode bằng `spring.shell.interactive.enabled=false`.
7. Nếu muốn loại `clear-screen` khỏi bản batch, điều kiện hóa bean command bằng `@ConditionalOnProperty`.
8. Chạy lại `report export` trong batch và `version` trong cả hai mode.

Các lệnh minh họa:

~~~text
clear-screen
report export --period=monthly --output=reports/monthly.csv
version
~~~

Sau bài tập, hãy giải thích được vì sao `InteractionMode` là metadata theo command trong 3.x, còn `spring.shell.interactive.enabled` là lựa chọn runner cho toàn ứng dụng trong 4.x.

## Tài liệu tham khảo

- [Spring Shell 3.4 – InteractionMode API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/context/InteractionMode.html)
- [Spring Shell 3.4 – @Command API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.4 – CommandRegistration.Builder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html)
- [Spring Shell 3.4 – Execution and Shell Runners](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Shell 4.x – Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
