# Kiểm tra runner, mặc định tương tác và API InteractionMode đã thay đổi

## 1. Runner quyết định ứng dụng chạy theo cách nào

Spring Shell có hai cách thực thi chính:

- **Interactive mode:** ứng dụng mở REPL, hiển thị prompt và chờ người dùng nhập nhiều command trong cùng một phiên.
- **Non-interactive mode:** ứng dụng nhận một command từ tham số tiến trình, thực thi command đó rồi kết thúc. Cách này phù hợp với script, CI/CD và automation.

Spring Shell triển khai hai luồng này bằng `InteractiveShellRunner` và `NonInteractiveShellRunner`. Runner được Spring Boot khởi chạy sau khi application context đã được tạo. Mỗi runner có nhiệm vụ riêng: runner tương tác quản lý vòng lặp terminal; runner non-interactive chuyển tham số tiến trình thành một lần gọi command.

Khi nâng cấp Spring Shell, cần kiểm tra runner được bật mặc định như thế nào. Một ứng dụng có thể vẫn compile và đăng ký command đúng nhưng hành vi khởi động thay đổi: trước đây chạy một command rồi thoát, sau nâng cấp lại mở prompt và chờ input; hoặc ngược lại, ứng dụng kết thúc ngay thay vì mở REPL.

## 2. Hai chế độ thực thi và trường hợp sử dụng

| Tiêu chí | Interactive | Non-interactive |
|---|---|---|
| Cách khởi động | Chạy ứng dụng và mở prompt | Truyền command sau tên JAR hoặc qua tham số tiến trình |
| Vòng đời | Tiếp tục cho đến khi người dùng thoát hoặc tiến trình dừng | Thực thi một command rồi kết thúc |
| Input | Có thể hỏi thêm qua terminal | Nên nhận đủ dữ liệu từ option, argument hoặc cấu hình |
| Output | Có prompt, help, thông báo và kết quả của nhiều command | Output của một lần thực thi, thường được redirect hoặc pipe |
| Phù hợp với | Quản trị viên thao tác thủ công, công cụ có nhiều bước | Script, scheduler, CI/CD, container job |
| Rủi ro chính | Prompt không mong muốn hoặc thao tác cần người dùng xác nhận | Thiếu option khiến command thất bại hoặc chờ input ngoài dự kiến |

Không nên coi hai chế độ chỉ là cách hiển thị. Chúng ảnh hưởng đến vòng đời tiến trình, cách nhận input, cách script lấy exit status và việc ứng dụng có tiếp tục chờ người dùng hay không.

## 3. Mặc định runner thay đổi giữa Spring Shell 3.4 và 4.x

Một điểm migration quan trọng là mặc định kích hoạt runner tương tác đã thay đổi:

| Phiên bản | Mặc định interactive | Muốn chạy command từ process arguments |
|---|---|---|
| Spring Shell 3.4.x | Tắt theo cấu hình mặc định; non-interactive runner xử lý command line | Dùng mặc định hoặc đặt `spring.shell.interactive.enabled=false` một cách tường minh |
| Spring Shell 4.0.x | Bật theo cấu hình mặc định | Đặt `spring.shell.interactive.enabled=false` để tắt REPL và dùng non-interactive runner |

Với Spring Shell 3.4.x, bật REPL bằng:

~~~properties
spring.shell.interactive.enabled=true
~~~

Với Spring Shell 4.0.x, nếu cần thực thi một command rồi kết thúc, đặt:

~~~properties
spring.shell.interactive.enabled=false
~~~

Không dựa vào mặc định của một major version khi triển khai. Hãy đặt property rõ ràng theo mục đích của từng artifact hoặc môi trường, đặc biệt với script tự động.

## 4. Chạy interactive mode sau khi nâng cấp

Trong Spring Shell 3.4.x, nếu runner tương tác chưa được bật, ứng dụng có thể khởi động rồi kết thúc mà không mở REPL. Bật bằng property:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=true
~~~

Hoặc đặt trong `application.properties`:

~~~properties
spring.shell.interactive.enabled=true
~~~

Trong Spring Shell 4.0.x, interactive mode được bật mặc định. Có thể khởi động bằng:

~~~bash
java -jar build-cli.jar
~~~

Nếu profile hoặc file cấu hình bên ngoài đã tắt interactive mode, hãy bật lại rõ ràng:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=true
~~~

Khi REPL hoạt động, người dùng có thể gọi nhiều command liên tiếp, xem help và sử dụng các tính năng terminal. Command cần đọc input bổ sung có thể sử dụng terminal API trong chế độ này.

## 5. Chạy non-interactive mode từ tham số tiến trình

Với Spring Shell 3.4.x, non-interactive runner được dùng cho command truyền từ command line. Ví dụ:

~~~bash
java -jar build-cli.jar project status
~~~

Với Spring Shell 4.0.x, interactive mode mặc định được bật. Khi muốn thực thi command từ process arguments và kết thúc, hãy tắt interactive runner:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=false project status
~~~

Có thể truyền option cho command sau tên command:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=false project list --owner=team-a
~~~

Property của Spring Boot nên đặt trước phần command để được xử lý như cấu hình ứng dụng. Khi đóng gói script wrapper, hãy giữ đúng thứ tự tham số và kiểm thử bằng chính shell hệ điều hành mà người dùng sẽ sử dụng.

## 6. Cấu hình runner bằng application properties và environment variable

`spring.shell.interactive.enabled` là property điều khiển runner tương tác. Có thể cấu hình trong file, biến môi trường, system property hoặc command-line property của Spring Boot.

Trong `application.yml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Qua environment variable:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar build-cli.jar project status
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\build-cli.jar project status
~~~

Qua JVM system property:

~~~bash
java -Dspring.shell.interactive.enabled=false -jar build-cli.jar project status
~~~

Property được truyền bằng `-D` phải đứng trước `-jar`. Property dạng `--...` của Spring Boot được đặt sau tên JAR. Chọn một cách cấu hình thống nhất trong script triển khai để tránh có nhiều nguồn cấu hình ghi đè lẫn nhau.

## 7. Tách cấu hình theo môi trường

Ứng dụng có thể dùng REPL trong môi trường phát triển nhưng chạy non-interactive trong production job. Dùng profile để thể hiện chủ đích:

`application-dev.yml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
~~~

`application-ci.yml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Kích hoạt profile khi chạy:

~~~bash
java -jar build-cli.jar --spring.profiles.active=ci project status
~~~

Với Spring Shell 4.0.x, property false trong profile `ci` bảo đảm REPL không mở và non-interactive runner có thể xử lý command. Với Spring Shell 3.4.x, profile `dev` bật REPL tường minh; cấu hình CI có thể giữ mặc định non-interactive hoặc đặt false để tài liệu hóa ý định.

Không dùng một profile mặc định cho cả máy người dùng và pipeline nếu hai môi trường có yêu cầu runner khác nhau. Một profile production có thể được kích hoạt tự động trên máy chủ và vô tình khiến một phiên terminal quản trị chuyển sang chế độ không mong muốn.

## 8. InteractionMode trong Spring Shell 3.x

Trong Spring Shell 3.x, `InteractionMode` cho phép gắn yêu cầu tương tác vào metadata của command. Các chế độ thường gặp là:

| Giá trị | Ý nghĩa |
|---|---|
| `ALL` | Command có thể được sử dụng trong cả hai chế độ. |
| `INTERACTIVE` | Command chỉ dành cho phiên REPL tương tác. |
| `NONINTERACTIVE` | Command dành cho một lần gọi từ process arguments hoặc automation. |

Ví dụ về ý nghĩa thiết kế:

- `wizard setup` cần prompt, lựa chọn và điều hướng nhiều bước nên chỉ phù hợp với interactive mode.
- `project status --id=...` nhận đủ input qua option nên phù hợp với non-interactive mode.
- `project list` có thể dùng trong cả REPL và script nên phù hợp với `ALL`.

Trong Spring Shell 3.x, `InteractionMode` có thể xuất hiện trong annotation legacy hoặc metadata của programmatic `CommandRegistration`, tùy mô hình đăng ký command. Đây là bộ lọc ở cấp command: nó mô tả command được phép chạy trong loại runner nào.

## 9. InteractionMode bị loại bỏ trong Spring Shell 4

Spring Shell 4 loại bỏ API `InteractionMode`. Command không còn được gắn nhãn `INTERACTIVE`, `NONINTERACTIVE` hoặc `ALL` trong registration. Việc chọn runner được chuyển lên cấu hình ứng dụng.

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Command có thể khai báo `InteractionMode` | Không còn API `InteractionMode` |
| Runner và metadata command cùng quyết định khả năng thực thi | Property runner quyết định chế độ của tiến trình |
| Có thể phân loại command theo interactive/non-interactive | Command registration độc lập với runner mode |
| Một command có thể bị giới hạn cho một loại runner | Cần tự thiết kế command và kiểm soát input theo môi trường |

Không cố giữ import `InteractionMode` bằng cách thêm lại dependency cũ. API đã bị loại bỏ khỏi Spring Shell 4; dependency cũ có thể gây xung đột phiên bản và không khôi phục hành vi tương thích.

## 10. Thay thế cách phân loại command theo InteractionMode

Khi chuyển sang Spring Shell 4, hãy phân loại theo nhu cầu input và side effect thay vì cố tái tạo enum cũ.

**Command nhận đủ dữ liệu từ tham số:** có thể chạy trong cả REPL và non-interactive mode. Ví dụ:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ProjectCommands {

@Command(name = "project status", description = "Xem trạng thái project")
public String status(@Option(longName = "id", required = true) String projectId) {
    return projectService.status(projectId);
}
}
~~~

**Command cần prompt:** kiểm tra runner mode hoặc một cấu hình tương tác do ứng dụng quản lý trước khi đọc terminal. Trong non-interactive mode, yêu cầu caller truyền option bắt buộc và trả lỗi rõ ràng nếu thiếu.

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ProjectWizardCommands {

@Command(name = "project wizard", description = "Cấu hình project qua nhiều bước")
public String wizard(CommandContext context) {
    if (!interactiveAllowed) {
        throw new IllegalStateException(
                "Command này cần phiên tương tác; hãy chạy trong REPL");
    }
    return runWizard(context.getTerminal());
}
}
~~~

`interactiveAllowed` là cấu hình ứng dụng được inject; `runWizard(...)` là logic nhập liệu dùng terminal hiện tại. Ví dụ minh họa ranh giới cần bảo vệ, không phải API thay thế có sẵn cho `InteractionMode`.

Nếu một thao tác có cả hai cách sử dụng, có thể tách thành command tương tác và command automation nhưng gọi chung service nghiệp vụ. Ví dụ `project wizard` thu thập input, sau đó gọi service; `project create --name ... --profile ...` nhận đủ tham số rồi gọi cùng service. Cách này giữ contract của script rõ ràng.

## 11. Kiểm tra command không vô tình prompt trong automation

Một command có thể hoạt động trong REPL nhưng treo trong CI vì `LineReader.readLine(...)` đang chờ input. Trong migration, hãy rà soát mọi vị trí:

- `LineReader.readLine(...)` hoặc `Terminal.reader().read()`.
- Component yêu cầu xác nhận hoặc chọn item.
- Wizard nhiều bước hoặc `ComponentFlow`.
- Đọc password, token hoặc secret từ terminal.
- Chờ phím điều khiển hoặc xác nhận trước khi ghi dữ liệu.

Với từng command, xác định cách chạy non-interactive. Ví dụ, command xóa dữ liệu có thể yêu cầu `--yes` trong automation thay vì prompt xác nhận. Nếu không có `--yes`, command phải từ chối trước khi mutation và trả thông báo phù hợp.

Không dùng việc terminal bean tồn tại làm bằng chứng rằng có người dùng đang nhập. Terminal có thể được kết nối với pipe hoặc input đã redirect. Runner mode và cấu hình của ứng dụng phải xác định hành vi.

## 12. Kiểm tra command line arguments và property của Spring Boot

Khi chạy non-interactive, Spring Shell nhận tên command và các token tham số từ tiến trình. Đồng thời Spring Boot cũng đọc các argument có dạng `--property=value` như application property. Cần kiểm tra thứ tự và cách phân tách trong script wrapper để property runner không bị coi là token của command.

Ví dụ chạy Spring Shell 4:

~~~bash
java -jar build-cli.jar \
  --spring.shell.interactive.enabled=false \
  project status --id=demo
~~~

Trong script, không ghép cả command thành một chuỗi duy nhất nếu shell có thể tách token sai. Với Bash, dùng mảng tham số; với PowerShell, truyền từng argument riêng hoặc dùng splatting để tránh lỗi quoting khi giá trị có dấu cách.

Nếu command cần nhận chuỗi có dấu cách, kiểm tra cả trường hợp:

~~~bash
java -jar build-cli.jar --spring.shell.interactive.enabled=false project create --name "demo project"
~~~

Test bằng đúng wrapper script mà người dùng sẽ chạy; một lệnh gõ trực tiếp trong terminal không đảm bảo script CI truyền argument giống hệt.

## 13. Runner mode và exit status

Non-interactive mode thường được dùng bởi script nên exit status là một phần của contract. Khi migration, xác nhận:

- Command thành công trả exit status thành công.
- Validation thất bại trả trạng thái lỗi phù hợp.
- Lỗi hệ thống được ánh xạ sang exit status khác 0.
- Command không khả dụng không bị hiểu nhầm là đã chạy thành công.
- Prompt bị từ chối trong non-interactive mode cũng trả trạng thái phù hợp cho caller.

Spring Shell 4 thay đổi một số API xử lý kết quả và exception so với 3.x. Nếu ứng dụng dùng `CommandExceptionResolver`, `CommandHandlingResult` hoặc `CommandExitCode`, hãy chuyển theo migration guide sang `ExitStatusExceptionMapper` và `ExitStatus`. Kiểm thử exit status bằng cách chạy executable JAR như tiến trình con và đọc mã thoát thực tế, không chỉ kiểm tra chuỗi hiển thị trên shell screen.

## 14. Kiểm thử runner sau migration

Tạo test matrix cho từng phiên bản và từng cách khởi chạy:

| Phiên bản | Cấu hình | Cách chạy | Kết quả mong đợi |
|---|---|---|---|
| 3.4.x | Mặc định | Khởi động không có command | Không tự bật REPL theo mặc định của cấu hình này. |
| 3.4.x | `interactive.enabled=true` | Khởi động không có command | Mở REPL và hiển thị prompt. |
| 3.4.x | Non-interactive | Truyền `project status` | Thực thi command và kết thúc. |
| 4.0.x | Mặc định | Khởi động không có command | Mở REPL. |
| 4.0.x | Mặc định | Truyền command ở process arguments | Interactive runner vẫn được bật; không dựa vào args để tự tắt REPL. |
| 4.0.x | `interactive.enabled=false` | Truyền command ở process arguments | Thực thi command rồi kết thúc. |
| 4.0.x | `interactive.enabled=false` | Command thiếu option bắt buộc | Trả lỗi rõ ràng, không chờ prompt. |

Ngoài test runner, kiểm thử:

1. Help và completion trong REPL.
2. Command quan trọng chạy qua non-interactive runner.
3. Command cần prompt bị chặn hoặc báo lỗi rõ ràng trong automation.
4. Script nhận đúng stdout/stderr và exit status.
5. Property từ profile, environment variable và command line ghi đè đúng thứ tự.
6. Command alias, option và argument không bị thay đổi ngoài dự kiến.
7. Ứng dụng kết thúc sau non-interactive command, không còn thread hoặc runner giữ tiến trình sống ngoài ý muốn.

`@ShellTest` và `ShellTestClient` hữu ích để kiểm thử command trong shell context. Tuy nhiên, để xác nhận runner và process exit behavior, nên có smoke test khởi chạy JAR thật bằng `ProcessBuilder` hoặc script test của hệ điều hành.

## 15. Lỗi thường gặp khi nâng cấp

**Nâng lên 4.x rồi script mở REPL:** interactive runner được bật mặc định. Đặt `spring.shell.interactive.enabled=false` cho tiến trình automation.

**Nâng lên 3.4 rồi không thấy prompt:** interactive runner chưa được bật. Đặt `spring.shell.interactive.enabled=true` cho môi trường cần REPL.

**Giữ `InteractionMode` trong code 4.x:** API đã bị loại bỏ. Xóa metadata cũ và chuyển quyết định lên runner/configuration.

**Cho rằng command tự phát hiện có TTY:** terminal object không bảo đảm input có người dùng. Dùng runner mode hoặc cấu hình tường minh.

**Command automation gọi `readLine()`:** script có thể treo. Yêu cầu option/argument hoặc tách command tương tác.

**Đặt property sai vị trí trong lệnh:** Spring Boot không nhận property như mong đợi hoặc shell truyền nhầm token cho command. Kiểm thử câu lệnh thực tế với wrapper.

**Chỉ test output, không test exit code:** script có thể tiếp tục dù command thất bại. Chạy JAR như process và xác nhận mã thoát.

**Dùng một profile cho mọi môi trường:** runner mode có thể không phù hợp với REPL trên máy người dùng hoặc automation trên CI. Tách cấu hình theo môi trường.

## 16. Quy trình migration và checklist phát hành

1. Kiểm kê nơi dùng `InteractionMode`, runner, prompt và terminal reader.
2. Ghi nhận cách khởi động hiện tại trên 3.x: có args, không args và property override.
3. Chuyển các command có prompt thành command có guard rõ ràng; bổ sung option cho automation.
4. Xóa `InteractionMode` khi nâng lên 4.x và chuyển quyết định runner sang `spring.shell.interactive.enabled`.
5. Cấu hình rõ runner cho dev, production, CI và script wrapper.
6. Chuyển exception/exit mapping nếu đang dùng API cũ.
7. Chạy test matrix cho interactive và non-interactive mode.
8. Chạy executable JAR từ terminal sạch và xác nhận process kết thúc đúng lúc.
9. Kiểm tra stdout, stderr và exit status bằng script thực tế.
10. Cập nhật tài liệu vận hành, lệnh chạy và ví dụ cho người dùng.

Checklist:

- [ ] Đã xác định runner mặc định của đúng phiên bản Spring Shell.
- [ ] Đã đặt `spring.shell.interactive.enabled` tường minh theo môi trường.
- [ ] Không còn tham chiếu `InteractionMode` trong source code 4.x.
- [ ] Command cần prompt không bị gọi ngoài interactive mode.
- [ ] Command automation nhận đủ dữ liệu qua option/argument.
- [ ] Script truyền property và command arguments đúng thứ tự.
- [ ] Exit status được kiểm thử trên tiến trình thật.
- [ ] REPL, help và completion vẫn hoạt động trong interactive mode.
- [ ] Non-interactive command kết thúc tiến trình sau khi hoàn thành.
- [ ] Tài liệu triển khai đã cập nhật cách bật/tắt REPL.

## Kết luận

Khi nâng Spring Shell từ 3.x lên 4.x, cần kiểm tra lại cả runner mặc định và API `InteractionMode`. Spring Shell 3.4 mặc định ưu tiên non-interactive runner; muốn mở REPL cần bật `spring.shell.interactive.enabled=true`. Spring Shell 4 bật interactive mode mặc định; muốn chạy command từ process arguments phải đặt property này thành `false`. API `InteractionMode` theo từng command đã bị loại bỏ, vì vậy ứng dụng chuyển việc lựa chọn chế độ lên cấu hình runner và tự bảo vệ command cần prompt. Kiểm thử cả REPL, script, process exit và cấu hình theo môi trường trước khi phát hành.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – Execution](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Shell 3.4.3 – Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [Spring Shell 3.4.3 API – ShellMethod](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/ShellMethod.html)
- [Spring Shell 3.4.3 API – CommandRegistration](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.html)
- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0 – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Boot 4.0 – Externalized Configuration](https://docs.spring.io/spring-boot/4.0/reference/features/external-config.html)
