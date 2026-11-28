# Tắt hoặc thay lệnh có sẵn bằng cơ chế được phiên bản hỗ trợ

Spring Shell cung cấp một số lệnh có sẵn như `help`, `clear`, `quit` hoặc `exit`, `version` và `script`. Các lệnh này giúp người dùng tra cứu cách dùng, dọn màn hình, thoát shell, xem phiên bản và chạy một file script. Khi ứng dụng cần giao diện CLI riêng, bạn có thể tắt một lệnh có sẵn hoặc thay hành vi của nó bằng implementation của ứng dụng.

Cơ chế thay thế phụ thuộc phiên bản. Spring Shell 3.4 có các marker interface như `Help.Command` và `Script.Command`; bean tùy chỉnh triển khai marker tương ứng sẽ khiến implementation mặc định lùi lại. Spring Shell 4 chuyển sang mô hình `Command` và `CommandRegistry`: tắt bean built-in bằng property, sau đó đăng ký command thay thế. Không nên mang nguyên cách override marker interface của 3.x sang 4.x.

## 1. Nhận diện nhóm lệnh có sẵn

Các lệnh tích hợp thường được chia theo mục đích:

| Lệnh | Mục đích |
| --- | --- |
| `help` | Liệt kê command và hiển thị hướng dẫn sử dụng |
| `clear` | Xóa nội dung màn hình terminal |
| `quit`, `exit` | Kết thúc vòng lặp shell tương tác |
| `version` | Hiển thị phiên bản Spring Shell và thông tin build được cấu hình |
| `script` | Đọc và thực thi tuần tự command từ file |
| `history` | Xem hoặc lưu lịch sử command trong các phiên bản có cung cấp command này |
| `stacktrace` | Hiển thị stack trace của lỗi gần nhất trong các phiên bản có cung cấp command này |
| `completion` | Tạo script completion cho shell hệ điều hành trong các phiên bản có hỗ trợ |

Danh sách thực tế thay đổi theo nhánh phiên bản và dependency được thêm vào. Tài liệu Spring Shell 3.4.3 liệt kê `help`, `clear`, `exit`, `stacktrace`, `script`, `history`, `completion` và `version`. Danh sách Spring Shell 4.0.3 tập trung vào `help`, `clear`, `exit`, `version` và `script`; một số chức năng trước đây có command riêng đã thay đổi hoặc được chuyển vào hạ tầng khác. Vì vậy, hãy tra đúng phiên bản và kiểm tra command đang có trong `help` của ứng dụng. <Link url="https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/index.html" title="Built-In Commands — Spring Shell 3.4.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/commands/builtin/index.html" title="Built-In Commands — Spring Shell 4.0.3"/>.

## 2. Phân biệt tắt, ẩn và thay thế

Ba thao tác này có kết quả khác nhau:

| Thao tác | Kết quả | Người dùng có gọi lệnh được không? |
| --- | --- | --- |
| Tắt (disable) | Không đăng ký implementation built-in | Không, trừ khi có command khác cùng tên được đăng ký |
| Ẩn (hide) | Không liệt kê trong help hoặc danh sách command theo cách hiển thị thông thường | Có thể vẫn gọi trực tiếp bằng tên |
| Thay thế (override/replace) | Đưa implementation của ứng dụng vào vị trí command có sẵn | Có, nhưng hành vi do ứng dụng quyết định |

Ví dụ, `hidden = true` chỉ là điều khiển hiển thị. Nó không phải cơ chế bảo mật và không bảo đảm command không thể thực thi. Nếu cần loại bỏ `script`, hãy tắt command bằng cơ chế của phiên bản; nếu chỉ muốn bớt một mục khỏi help trong khi vẫn cho phép gọi nội bộ, mới cân nhắc ẩn command.

## 3. Spring Shell 3.4: tắt một built-in bằng property

Trong Spring Shell 3.4, các lệnh built-in có thể được tắt bằng property theo tên command:

```yaml
spring:
  shell:
    command:
      help:
        enabled: false
      script:
        enabled: false
      stacktrace:
        enabled: false
```

Tên property có dạng `spring.shell.command.<command>.enabled`. Ví dụ, `spring.shell.command.help.enabled=false` tắt command `help`; `spring.shell.command.script.enabled=false` tắt command `script`. Property có thể được đặt trong `application.yml`, profile riêng hoặc truyền qua biến môi trường/argument khởi động theo quy tắc cấu hình Spring Boot.

Ví dụ dùng tham số khi khởi chạy:

```bash
java -jar app.jar --spring.shell.command.help.enabled=false
```

Property này tác động tới đăng ký command built-in. Nếu ứng dụng tự đăng ký command `help` khác, command tùy chỉnh vẫn có thể xuất hiện theo cấu hình riêng của ứng dụng.

## 4. Spring Shell 3.4: thay thế bằng marker interface

Spring Shell 3.4 cung cấp marker interface lồng trong các lớp command built-in. Để thay một built-in, đăng ký bean tùy chỉnh triển khai marker interface tương ứng. Implementation mặc định sẽ back off.

Ví dụ thay `help` bằng lệnh trợ giúp theo quy ước của sản phẩm:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
import org.springframework.shell.standard.commands.Help;

@ShellComponent
public class ProductHelpCommands implements Help.Command {

    @ShellMethod(key = "help", value = "Hiển thị hướng dẫn của ứng dụng")
    public String help(
            @ShellOption(defaultValue = "") String command) {

        if (command.isBlank()) {
            return "Các nhóm lệnh: project, environment, deployment. "
                    + "Dùng help <command> để xem hướng dẫn chi tiết.";
        }

        return "Hướng dẫn cho command: " + command;
    }
}
```

`Help.Command` là marker interface báo với Spring Shell rằng ứng dụng cung cấp implementation riêng cho chức năng help. Method `@ShellMethod(key = "help")` tạo command cùng tên. Phần thân ví dụ là nội dung minh họa; trong ứng dụng thực tế, hãy lấy mô tả và tham số từ catalog command hoặc service trợ giúp của sản phẩm.

Tương tự, có thể triển khai marker interface của command cần thay:

| Built-in 3.4 | Marker interface |
| --- | --- |
| `help` | `Help.Command` |
| `clear` | `Clear.Command` |
| `quit` | `Quit.Command` |
| `script` | `Script.Command` |
| `history` | `History.Command` |
| `stacktrace` | `Stacktrace.Command` |
| `completion` | `Completion.Command` |
| `version` | `Version.Command` |

Các marker interface được đặt trong package `org.springframework.shell.standard.commands`. Hãy dùng marker của đúng chức năng; triển khai nhầm marker không làm implementation built-in khác lùi lại. Tài liệu API của `Help.Command`, `Clear.Command`, `Quit.Command`, `Script.Command` và `History.Command` mô tả rõ cơ chế back off này. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Help.Command.html" title="Help.Command API"/> · <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Clear.Command.html" title="Clear.Command API"/> · <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Script.Command.html" title="Script.Command API"/>.

## 5. Spring Shell 3.4: kết hợp tắt và thay thế

Nếu muốn thay một built-in bằng command riêng, thông thường chỉ cần marker interface và command cùng tên. Nếu cần bỏ hoàn toàn chức năng, đặt property `enabled=false`.

Ví dụ thay `script` bằng bộ chạy script có kiểm tra thư mục được phép:

```java
import java.io.File;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.commands.Script;

@ShellComponent
public class WorkspaceScriptCommands implements Script.Command {

    @ShellMethod(key = "script", value = "Chạy script trong workspace")
    public String script(File file) {
        if (!file.isFile()) {
            throw new IllegalArgumentException("Không tìm thấy file script.");
        }
        if (!file.getAbsolutePath().startsWith("/workspace/")) {
            throw new IllegalArgumentException("Script phải nằm trong workspace.");
        }
        return "Đã tiếp nhận script " + file.getName();
    }
}
```

Đây là ví dụ rút gọn về điểm mở rộng; một script runner thực tế cần dùng parser/command executor của ứng dụng và xử lý encoding, comment, lỗi từng dòng cùng mã thoát. Nếu chỉ thay đổi nội dung help hoặc giao diện clear, không nên viết lại toàn bộ cơ chế thực thi script.

## 6. Spring Shell 4.0.3: tắt built-in bằng property

Spring Shell 4 chuyển command sang API `Command` và auto-configuration tạo các bean built-in. Trong Spring Shell 4.0.3, `StandardCommandsAutoConfiguration` tạo các command `help`, `clear`, `version` và `script` khi property tương ứng cho phép.

Ví dụ tắt `help` và `script`:

```yaml
spring:
  shell:
    command:
      help:
        enabled: false
      script:
        enabled: false
```

Các property được kiểm tra bởi auto-configuration:

| Built-in trong `StandardCommandsAutoConfiguration` 4.0.3 | Property |
| --- | --- |
| `help` | `spring.shell.command.help.enabled` |
| `clear` | `spring.shell.command.clear.enabled` |
| `version` | `spring.shell.command.version.enabled` |
| `script` | `spring.shell.command.script.enabled` |

Mặc định các property này bật nếu không được cấu hình. API `StandardCommandsAutoConfiguration` 4.0.3 xác nhận từng bean dùng `@ConditionalOnProperty` với `havingValue=true` và `matchIfMissing=true`. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/StandardCommandsAutoConfiguration.html" title="StandardCommandsAutoConfiguration API — 4.0.3"/>.

Không suy ra rằng mọi command xuất hiện trong help đều được tạo bởi class này. `quit`/`exit` là điều khiển vòng lặp shell tương tác; các chức năng phụ thuộc JLine có thể do auto-configuration khác cung cấp. Hãy xác định bean và property của đúng phiên bản trước khi tắt.

## 7. Spring Shell 4.0.3: thay thế bằng bean `Command`

Trong Spring Shell 4, một bean kiểu `Command` được tự động thêm vào `CommandRegistry`. Khi thay built-in, tắt implementation mặc định bằng property trước, sau đó đăng ký command tùy chỉnh có cùng tên.

Ví dụ thay `help` bằng một command riêng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
public class CustomHelpConfiguration {

    @Bean
    Command productHelpCommand() {
        return Command.builder()
                .name("help")
                .description("Hiển thị trợ giúp theo quy ước sản phẩm")
                .execute(context -> {
                    context.outputWriter().println(
                            "Dùng help <command> để xem hướng dẫn của từng lệnh.");
                });
    }
}
```

Kết hợp với cấu hình:

```yaml
spring:
  shell:
    command:
      help:
        enabled: false
```

Property ngăn implementation help mặc định được tạo; bean `productHelpCommand` cung cấp command `help` của ứng dụng. Nếu không tắt built-in, hai command cùng tên có thể gây xung đột khi registry được khởi tạo. Command tùy chỉnh cần có mô tả, help, option và hành vi phù hợp với hợp đồng CLI mà ứng dụng công bố.

Spring Shell 4 cũng hỗ trợ annotation model mới với `@Command` trên method của Spring bean. Có thể dùng annotation để tạo command thay thế; nguyên tắc vẫn là tắt built-in trước và bảo đảm chỉ có một command được đăng ký với tên đó. <Link url="https://docs.spring.io/spring-shell/reference/commands/registration.html" title="Command Registration — Spring Shell 4.0.3"/>.

## 8. Thay command trong lúc ứng dụng đang chạy bằng `CommandRegistry`

Khi command thay đổi theo plugin, module hoặc tính năng được bật trong phiên, Spring Shell 4 cung cấp `CommandRegistry` để đăng ký và gỡ command lúc runtime. Registry có thể tìm command theo tên, đăng ký command mới và gỡ command hiện tại.

Ví dụ thay command `help` sau khi shell đã khởi tạo:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class RuntimeCommandSwitcher {

    private final CommandRegistry registry;

    public RuntimeCommandSwitcher(CommandRegistry registry) {
        this.registry = registry;
    }

    public void replaceHelp(Command replacement) {
        Command current = registry.getCommandByName("help");
        if (current != null) {
            registry.unregisterCommand(current);
        }
        registry.registerCommand(replacement);
    }
}
```

Thứ tự quan trọng: lấy command hiện tại, gỡ command đó, sau đó đăng ký command thay thế. Cách này tránh giữ hai implementation cùng tên trong registry. `CommandRegistry` tự động được Spring Shell nạp từ các command bean trong application context; chỉ dùng thao tác runtime khi thực sự cần thay đổi tập command trong lúc chạy. <Link url="https://javadoc.io/static/org.springframework.shell/spring-shell-core/4.0.3/org/springframework/shell/core/command/CommandRegistry.html" title="CommandRegistry API — 4.0.3"/>.

Nếu command thay thế cũng được khai báo thành bean `Command`, Spring Shell tự đăng ký bean đó khi khởi tạo. Không gọi `registerCommand` thêm lần nữa cho cùng bean sau khi registry đã tự nạp, trừ khi bạn đã chủ động gỡ và đang thực hiện một quy trình đăng ký lại có kiểm soát.

## 9. Phân biệt `hidden` với disable

Spring Shell cho phép ẩn command khỏi danh sách trợ giúp. Trong Spring Shell 4, có thể dùng `@Command(hidden = true)` hoặc thuộc tính hidden của `Command.Builder`; trong các API programmatic của 3.x cũng có cờ `hidden`.

Ví dụ:

```java
@Command(name = "internal-diagnostics", hidden = true)
public String diagnostics() {
    return "Thông tin chẩn đoán";
}
```

Command ẩn vẫn có thể được gọi nếu người dùng biết tên và có quyền truy cập. Vì vậy:

- Dùng `hidden` để giảm nhiễu trong help.
- Dùng property `enabled=false` hoặc cơ chế unregister để bỏ command khỏi registry.
- Dùng kiểm tra quyền trong service để bảo vệ hành động nhạy cảm.

Không xem việc ẩn command là một lớp authorization.

## 10. Lưu ý đặc biệt với `quit` và `exit`

`quit`/`exit` là lệnh điều khiển vòng lặp tương tác. Nếu xóa khả năng thoát khỏi shell, người dùng có thể phải kết thúc tiến trình từ terminal. Vì vậy, chỉ thay đổi hành vi này khi sản phẩm có một cơ chế kết thúc phiên rõ ràng khác.

Trong Spring Shell 3.4.3, API có `Quit.Command` marker và property `spring.shell.command.quit.enabled=false`; có thể thay hoặc tắt theo cơ chế built-in 3.x. Trong Spring Shell 4.0.3, tài liệu built-in liệt kê `exit`, nhưng `StandardCommandsAutoConfiguration` 4.0.3 không tạo command quit như các bean help/clear/version/script. Tài liệu 4.0.4 bổ sung mô tả property `spring.shell.command.quit.enabled=false` chỉ loại `quit` khỏi registry ở non-interactive mode; property này không tác động interactive shell, nơi `quit`/`exit` vẫn hoạt động để người dùng thoát. Không áp dụng hướng dẫn 4.0.4 cho 4.0.3 nếu chưa xác minh đúng release. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Quit.Command.html" title="Quit.Command API — 3.4.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html" title="Exit — Spring Shell 4.0.4"/>.

## 11. Khác biệt chính giữa Spring Shell 3.4 và 4.0.3

| Nội dung | Spring Shell 3.4.3 | Spring Shell 4.0.3 |
| --- | --- | --- |
| Mô hình command | Legacy `@ShellMethod`, programmatic `CommandRegistration` và annotation model mới | `@Command` trên Spring bean hoặc bean `Command` |
| Override built-in | Bean triển khai marker interface như `Help.Command`; standard bean back off | Tắt built-in bằng property rồi đăng ký `Command` tùy chỉnh cùng tên |
| Disable built-in | `spring.shell.command.<name>.enabled=false` | Property được hỗ trợ bởi từng built-in auto-config, ví dụ help/clear/version/script |
| Đăng ký động | Phụ thuộc cơ chế command registration của 3.x | `CommandRegistry.registerCommand` và `unregisterCommand` |
| Ẩn command | Cờ `hidden` trong registration | `@Command(hidden = true)` hoặc builder |
| Exit/quit | `Quit.Command` marker và property quit | Điều khiển shell tương tác; kiểm tra chính xác phiên bản trước khi thay đổi |

Spring Shell 4 là một lần thiết kế lại API. Các marker interface của package `org.springframework.shell.standard.commands` thuộc mô hình 3.x không phải cách thay thế chung trong 4.x. Migration guide mô tả mô hình command mới và cách định nghĩa command qua `Command.Builder`/`CommandRegistry`. <Link url="https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide" title="Spring Shell v4 Migration Guide"/>.

## 12. Kiểm tra sau khi tắt hoặc thay thế

Sau khi thay đổi cấu hình, hãy kiểm tra cả registry, help và hành vi thực thi. Chỉ kiểm tra help là chưa đủ vì một command bị ẩn vẫn có thể được gọi trực tiếp.

Ma trận kiểm thử đề xuất:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| `help` sau khi disable built-in | Command đã tắt không còn trong danh sách |
| Gọi tên command đã disable | Parser báo không tìm thấy command nếu không có implementation thay thế |
| Gọi command sau khi thay thế | Implementation tùy chỉnh được thực thi |
| `help <command>` | Hiển thị mô tả và option của implementation mới |
| Alias của command | Không còn alias cũ ngoài ý muốn; alias mới hoạt động đúng |
| `--help` hoặc `-h` | Hành vi trợ giúp vẫn nhất quán nếu command hỗ trợ |
| Script đang dùng command bị tắt | Script báo lỗi rõ ràng hoặc được cập nhật theo command mới |
| Runtime unregister/register | Command cũ không còn trong registry và command mới có thể gọi |
| Quit/exit | Người dùng vẫn có cách kết thúc shell theo thiết kế |

Với Spring Shell 4, có thể kiểm tra registry qua `getCommandByName`, `getCommands` và chạy command bằng test support của phiên bản. Khi dùng Spring Boot, kiểm tra thêm property đã được nạp đúng profile; khi chạy JAR, xác nhận profile/argument trong môi trường triển khai giống cấu hình được test.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Command mặc định vẫn xuất hiện | Property sai tên, sai profile hoặc đặt sau khi auto-configuration đã chạy | Kiểm tra `spring.shell.command.<name>.enabled` trong Environment lúc khởi động |
| Hai command cùng tên gây xung đột | Đăng ký custom command nhưng không disable built-in | Tắt built-in trước khi thêm implementation thay thế |
| Marker interface không có tác dụng trong 4.x | Dùng cơ chế override của 3.x trên API mới | Dùng property và `Command` bean/registry |
| Command biến mất khỏi help nhưng vẫn chạy | Chỉ đặt `hidden = true` | Disable bằng property hoặc unregister command |
| Thay help làm mất tài liệu tham số | Implementation mới chỉ in thông báo chung | Xây dựng help từ metadata command hoặc giữ cú pháp `help <command>` |
| Script cũ không chạy | Script phụ thuộc command vừa bị tắt hoặc đổi tên | Cập nhật script và tài liệu CLI cùng lúc |
| Không tắt được `quit` trong interactive | Quit/exit được shell giữ lại để thoát vòng lặp | Giữ cơ chế thoát; kiểm tra hành vi theo đúng bản Spring Shell |
| Registry runtime có hai command | Đăng ký replacement mà chưa unregister command cũ | Gỡ command hiện tại trước khi đăng ký command mới |

## 14. Bài thực hành tổng hợp

Tạo một CLI quản lý dự án với help tùy chỉnh và chính sách script riêng:

1. Xác định phiên bản Spring Shell đang dùng và liệt kê built-in có trong `help`.
2. Với Spring Shell 3.4, triển khai `Help.Command` và tạo command `help` theo format của sản phẩm.
3. Tắt `script` bằng `spring.shell.command.script.enabled=false` nếu chính sách sản phẩm không cho chạy script tùy ý.
4. Với Spring Shell 4.0.3, tắt built-in `help` bằng property và đăng ký bean `Command` cùng tên.
5. Tạo một `CommandRegistry` switcher để thay command `help` khi plugin trợ giúp được bật hoặc tắt trong phiên.
6. Đánh dấu một command chẩn đoán là hidden và xác nhận command vẫn gọi được khi biết tên.
7. Kiểm tra `help`, `help <command>`, command alias, script cũ và cách thoát shell.
8. Viết integration test cho cấu hình built-in disabled và implementation thay thế.

Khi hoàn thành, bạn cần giải thích được khác biệt giữa disable, hide và override; lý do Spring Shell 3.4 dùng marker interface; cách Spring Shell 4 quản lý command qua registry; và vì sao cần kiểm thử cả help lẫn việc gọi command trực tiếp.

## 15. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Nhận diện | Biết built-in nào có trong phiên bản đang dùng |
| Disable | Tắt được command bằng property đúng tên |
| Override 3.x | Dùng marker interface đúng loại để standard implementation back off |
| Replace 4.x | Đăng ký bean `Command` sau khi tắt implementation mặc định |
| Registry | Gỡ command cũ và đăng ký command mới đúng trình tự |
| Hidden | Phân biệt ẩn command với tắt command |
| Exit | Giữ hành vi thoát shell phù hợp với phiên bản và mode |
| Kiểm thử | Xác nhận help, invocation, alias, script và registry |

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Built-In Commands](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/index.html)
- [Spring Shell 3.4.3 — `Help.Command`](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Help.Command.html)
- [Spring Shell 3.4.3 — `Clear.Command`](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Clear.Command.html)
- [Spring Shell 3.4.3 — `Script.Command`](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Script.Command.html)
- [Spring Shell 3.4.3 — `Quit.Command`](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Quit.Command.html)
- [Spring Shell 4.0.3 — Built-In Commands](https://docs.spring.io/spring-shell/reference/commands/builtin/index.html)
- [Spring Shell 4.0.3 — StandardCommandsAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/StandardCommandsAutoConfiguration.html)
- [Spring Shell 4.0.3 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 — CommandRegistry API](https://javadoc.io/static/org.springframework.shell/spring-shell-core/4.0.3/org/springframework/shell/core/command/CommandRegistry.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
