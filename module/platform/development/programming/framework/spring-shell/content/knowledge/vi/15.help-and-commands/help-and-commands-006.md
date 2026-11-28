# Lệnh `clear`, `exit` và `version` trong từng môi trường chạy

Spring Shell cung cấp một số lệnh có sẵn để người dùng điều khiển phiên làm việc và kiểm tra thông tin runtime. Ba lệnh thường gặp là `clear`, `exit` và `version`. Chúng có mục đích khác nhau: `clear` làm sạch màn hình terminal, `exit` kết thúc vòng lặp shell tương tác, còn `version` hiển thị phiên bản Spring Shell đang dùng.

Khi xây dựng CLI, cần hiểu môi trường đang chạy là interactive hay non-interactive. Một lệnh hữu ích tại prompt có thể không có ý nghĩa khi chạy một command duy nhất từ script hoặc CI. Bài viết hướng dẫn cách sử dụng ba lệnh, cấu hình bật/tắt, phân biệt lệnh Spring Shell với lệnh của hệ điều hành và kiểm tra hành vi trong từng môi trường.

## 1. Ba lệnh có sẵn và mục đích của chúng

| Lệnh Spring Shell | Tác dụng | Ngữ cảnh phù hợp |
|---|---|---|
| `clear` | Xóa nội dung màn hình terminal và đưa prompt về góc trên bên trái | Phiên interactive có terminal |
| `exit` | Alias của `quit`, kết thúc vòng lặp shell tương tác | Khi người dùng muốn rời REPL |
| `quit` | Yêu cầu shell kết thúc vòng lặp tương tác | Tương đương `exit` |
| `version` | Hiển thị phiên bản Spring Shell hiện tại | Interactive hoặc non-interactive |

Các lệnh này thuộc nhóm built-in commands của Spring Shell. Khi ứng dụng dùng cấu hình standard commands, người dùng có thể xem chúng bằng lệnh `help` và xem mô tả chi tiết bằng `help clear`, `help quit` hoặc `help version`.

Ví dụ:

```text
shell:>help

Built-In Commands
    clear: Clear the terminal screen
    help: Display help about available commands
    quit, exit: Exit the shell
    version: Show version info
```

Danh sách thực tế phụ thuộc phiên bản, dependency và cấu hình của ứng dụng. Có thể có thêm `script`, `history`, `stacktrace` hoặc các built-in command khác.

## 2. Phân biệt interactive và non-interactive mode

Spring Shell có hai cách chạy chính:

- **Interactive mode:** ứng dụng mở một phiên REPL (Read-Eval-Print Loop). Người dùng nhập nhiều command tại prompt cho đến khi kết thúc phiên.
- **Non-interactive mode:** ứng dụng nhận một command từ process arguments, thực thi command đó rồi hoàn tất lượt chạy. Cách này phù hợp với script, automation và CI.

Trong Spring Shell 4.x, interactive mode được bật mặc định, kể cả khi tiến trình được khởi chạy với command-line arguments. Để thực thi command từ các process arguments, cần đặt `spring.shell.interactive.enabled=false`.

Ví dụ cấu hình non-interactive trong `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó có thể gọi command từ terminal:

```bash
java -jar catalog-cli.jar version
```

Nếu không tắt interactive mode, việc truyền `version` sau tên JAR không tự động bảo đảm command được thực thi ngay; ứng dụng có thể mở prompt tương tác theo cấu hình mặc định.

### Ý nghĩa của ba lệnh theo từng mode

| Lệnh | Interactive | Non-interactive |
|---|---|---|
| `clear` | Hữu ích để làm sạch màn hình giữa các thao tác | Thường không có ý nghĩa với output được chuyển hướng hoặc chạy một lần |
| `exit` / `quit` | Kết thúc vòng lặp shell để người dùng rời prompt | Không cần thiết vì runner đã hoàn tất sau command |
| `version` | Hiển thị thông tin phiên bản ngay trong phiên | Có thể chạy như một command độc lập và trả output cho script |

Không nên dùng `exit` làm bước cuối của mọi script. Trong non-interactive mode, tiến trình được điều khiển bởi runner và vòng đời ứng dụng; hãy để command hoàn tất theo cơ chế đó.

## 3. Dùng `clear` để xóa màn hình terminal

Lệnh `clear` của Spring Shell xóa màn hình và đưa vị trí prompt về góc trên bên trái. Nó giúp người dùng bắt đầu một thao tác mới với màn hình gọn hơn, đặc biệt khi vừa xem một bảng dữ liệu hoặc output dài.

Ví dụ trong phiên interactive:

```text
shell:>report-list
ID       NAME                 STATUS
101      Monthly report       READY
102      Quarterly report     READY
103      Annual report        PROCESSING

shell:>clear
```

Sau khi chạy `clear`, nội dung hiển thị trước đó được xóa khỏi màn hình terminal và prompt xuất hiện ở vị trí đầu màn hình.

### Phân biệt `clear` của Spring Shell và lệnh hệ điều hành

Cùng một từ có thể được hiểu bởi các lớp khác nhau:

| Nơi nhập | Lệnh thường gặp | Thành phần xử lý |
|---|---|---|
| Prompt Spring Shell | `clear` | Built-in command của Spring Shell |
| Bash hoặc shell POSIX | `clear` | Lệnh/tiện ích của môi trường terminal hệ điều hành |
| PowerShell | `Clear-Host` hoặc alias `clear` | Cmdlet của PowerShell |
| Windows `cmd.exe` | `cls` | Lệnh nội bộ của `cmd.exe` |

Khi đang ở prompt Spring Shell, `clear` được gửi tới command registry của Spring Shell. Khi đã thoát về terminal hệ điều hành, cùng chuỗi ký tự có thể được xử lý bởi shell hệ điều hành.

### Khi nào `clear` không phù hợp?

Trong non-interactive mode, output thường được ghi vào stdout, file log hoặc pipeline. Xóa màn hình không giúp ích cho người đọc file output và có thể làm mất nội dung mà script cần lưu lại. Vì vậy, command tự động hóa nên in kết quả có cấu trúc và giữ stdout ổn định thay vì gọi `clear` giữa luồng dữ liệu.

Nếu terminal không hỗ trợ thao tác điều khiển màn hình như mong đợi, hãy kiểm tra loại terminal, terminal emulator và cấu hình JLine. Không nên giả định `clear` sẽ xóa được nội dung của mọi cửa sổ console hoặc file đã redirect.

## 4. Dùng `exit` hoặc `quit` để kết thúc phiên tương tác

Trong Spring Shell, `quit` là built-in command yêu cầu interactive shell loop kết thúc. `exit` là alias của `quit`, vì vậy hai cách gọi có cùng mục đích:

```text
shell:>quit
```

hoặc:

```text
shell:>exit
```

Khi người dùng gọi một trong hai lệnh, Spring Shell rời vòng lặp interactive. Nếu không còn thành phần nào giữ tiến trình sống, ứng dụng sẽ kết thúc theo vòng đời runtime bình thường.

### Kết thúc shell loop và đóng Spring ApplicationContext

Hai việc này có liên quan nhưng cần phân biệt:

- `quit` / `exit` kết thúc vòng lặp shell tương tác.
- `spring.shell.context.close=true` yêu cầu Spring Shell đóng `ApplicationContext` sau khi shell hoàn tất phần thực thi.

`spring.shell.context.close` mặc định không bật. Có thể cấu hình:

```yaml
spring:
  shell:
    context:
      close: true
```

Thiết lập này hữu ích khi ứng dụng có background thread hoặc scheduler khiến JVM vẫn còn sống sau khi shell loop kết thúc. Nếu ứng dụng có chủ đích duy trì các tác vụ nền sau phiên shell, cần xem xét vòng đời đó trước khi bật tự động đóng context.

### `quit.enabled` trong non-interactive mode

Trong non-interactive mode, có thể loại lệnh `quit` khỏi command registry và phần trợ giúp bằng cấu hình:

```yaml
spring:
  shell:
    command:
      quit:
        enabled: false
```

Thuộc tính này chỉ có tác dụng với non-interactive mode. Trong interactive mode, gõ `quit` hoặc `exit` vẫn kết thúc shell loop; lệnh vẫn được giữ trong phần trợ giúp để người dùng luôn có cách rời phiên.

## 5. Dùng `version` để kiểm tra phiên bản Spring Shell

Lệnh built-in `version` hiển thị phiên bản Spring Shell hiện tại mà ứng dụng đang sử dụng.

Trong interactive mode:

```text
shell:>version
Spring Shell 4.0.4
```

Trong non-interactive mode:

```bash
java -jar catalog-cli.jar version
```

Output cụ thể tùy phiên bản thư viện và metadata có trong artifact. Lệnh `version` không đồng nghĩa với lệnh hiển thị phiên bản Java hoặc phiên bản Spring Boot. Nếu cần chẩn đoán toàn bộ runtime, hãy bổ sung command thông tin môi trường riêng của ứng dụng.

### Build metadata và Git metadata

Spring Shell có thể nhận `BuildProperties` và `GitProperties` do Spring Boot cung cấp. Khi các bean metadata này tồn tại và các trường tương ứng được bật, lệnh version có thể hiển thị thêm thông tin build hoặc Git như:

- Tên artifact, group hoặc build name.
- Phiên bản build và thời điểm build.
- Git branch.
- Git commit ID hoặc short commit ID.
- Thời điểm commit.

Ví dụ cấu hình chọn một số trường metadata:

```yaml
spring:
  shell:
    command:
      version:
        enabled: true
        show-build-version: true
        show-build-time: true
        show-git-branch: true
        show-git-short-commit-id: true
```

Các thuộc tính này chỉ có dữ liệu khi ứng dụng cung cấp metadata tương ứng. Nếu `BuildProperties` hoặc `GitProperties` không tồn tại, bật cờ hiển thị không tự tạo ra thông tin build/Git.

### Nếu cần phiên bản sản phẩm của chính ứng dụng

Không nên giả định built-in `version` là phiên bản nghiệp vụ hoặc phiên bản phát hành của CLI. Nếu muốn hiển thị một phiên bản sản phẩm ổn định, có thể:

1. Sinh build metadata trong pipeline đóng gói và cung cấp `BuildProperties`.
2. Định nghĩa property riêng như `app.version` từ build configuration.
3. Tạo command riêng, ví dụ `app-version` hoặc `about`, để hiển thị phiên bản ứng dụng cùng thông tin runtime đã chọn.

Ví dụ command đơn giản đọc phiên bản ứng dụng từ cấu hình:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class ApplicationInfoCommands {

    private final String applicationVersion;

    public ApplicationInfoCommands(
            @Value("${app.version:unknown}") String applicationVersion) {
        this.applicationVersion = applicationVersion;
    }

    @Command(name = "app-version", description = "Show the application version")
    public String version() {
        return "Catalog CLI " + applicationVersion;
    }
}
```

Property có thể được đặt trong `application.yml` hoặc được inject từ build pipeline:

```yaml
app:
  version: 1.4.2
```

Trong hệ thống thực tế, nên lấy phiên bản từ một nguồn build duy nhất để output của `app-version`, manifest và artifact không lệch nhau.

## 6. Bật hoặc tắt các built-in command

Các standard command `clear` và `version` có thể được điều khiển bằng property tương ứng. Theo auto-configuration của Spring Shell 4.x, chúng được bật khi property bị bỏ qua; có thể tắt rõ ràng trong `application.yml`.

Ví dụ tắt `clear` và `version`:

```yaml
spring:
  shell:
    command:
      clear:
        enabled: false
      version:
        enabled: false
```

Các property thường dùng:

| Property | Tác dụng |
|---|---|
| `spring.shell.command.clear.enabled` | Bật/tắt built-in `clear` |
| `spring.shell.command.version.enabled` | Bật/tắt built-in `version` |
| `spring.shell.command.quit.enabled` | Có thể loại `quit` khỏi registry trong non-interactive mode; không vô hiệu hóa `exit`/`quit` ở interactive mode |
| `spring.shell.interactive.enabled` | Chọn interactive hoặc non-interactive runner |
| `spring.shell.context.close` | Yêu cầu đóng ApplicationContext sau khi shell hoàn tất |

Không nên tắt một command chỉ vì tên của nó trùng với một lệnh hệ điều hành. Trước khi đổi cấu hình, hãy xác định người dùng đang nhập ở prompt Spring Shell hay ở terminal hệ điều hành.

## 7. Ví dụ cấu hình theo môi trường

### Môi trường phát triển tương tác

Mục tiêu là cho người phát triển sử dụng prompt, xóa màn hình, xem phiên bản và thoát phiên dễ dàng:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    command:
      clear:
        enabled: true
      version:
        enabled: true
```

Khởi chạy:

```bash
java -jar catalog-cli.jar
```

Sau đó thử:

```text
shell:>version
shell:>clear
shell:>quit
```

### Môi trường script hoặc CI

Mục tiêu là chạy command một lần, lấy output và để process kết thúc:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    context:
      close: true
    command:
      version:
        enabled: true
      quit:
        enabled: false
```

Gọi command:

```bash
java -jar catalog-cli.jar version
```

Trong môi trường này, `version` hữu ích để kiểm tra artifact đang được triển khai. `clear` thường không cần thiết vì output có thể được redirect vào log hoặc pipeline; `quit` không cần thiết để kết thúc một command non-interactive.

## 8. Kiểm tra hành vi khi triển khai

Không nên chỉ kiểm tra command xuất hiện trong `help`. Hãy xác nhận command hoạt động trong đúng mode và đúng terminal mà ứng dụng sẽ sử dụng.

| Kiểm tra | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| Built-in commands được đăng ký | Chạy `help` | Có `clear`, `quit`/`exit`, `version` theo cấu hình |
| Chi tiết command | Chạy `help clear`, `help quit`, `help version` | Mô tả phù hợp với hành vi hiện tại |
| Clear trong terminal | Chạy `clear` ở prompt interactive | Màn hình được làm sạch và prompt được đặt lại |
| Alias thoát | Chạy lần lượt `quit` và `exit` trong các phiên thử | Cả hai đều kết thúc interactive loop |
| Context close | Bật `spring.shell.context.close=true`, kết thúc shell | ApplicationContext được yêu cầu đóng sau khi shell hoàn tất |
| Version | Chạy `version` | Hiển thị đúng phiên bản Spring Shell |
| Build/Git metadata | Bật các trường `show-*` và đóng gói metadata | Chỉ các trường có metadata mới được hiển thị |
| Non-interactive | Đặt `interactive.enabled=false`, chạy `version` từ process args | Command được thực thi một lần và runner hoàn tất |
| Tắt built-in | Đặt `clear.enabled=false` hoặc `version.enabled=false` | Command tương ứng không còn trong registry/help |

Nếu `version` không hiển thị build metadata, kiểm tra artifact có tạo `BuildProperties` hoặc `GitProperties` hay không và các thuộc tính `show-*` đã bật đúng chưa. Nếu `exit` vẫn hoạt động dù `quit.enabled=false`, hãy xác nhận ứng dụng có đang ở interactive mode không; thuộc tính này không tắt khả năng thoát khỏi interactive shell.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhập `clear` ở terminal ngoài ứng dụng nhưng không chạy built-in Spring Shell | Lệnh được gửi tới shell hệ điều hành | Khởi chạy ứng dụng và nhập tại prompt Spring Shell |
| Chạy `java -jar app.jar version` nhưng ứng dụng mở prompt | Interactive mode vẫn bật mặc định | Đặt `spring.shell.interactive.enabled=false` |
| Dùng `exit` trong script nhưng command không có ý nghĩa | `exit` được thiết kế để rời interactive loop | Để non-interactive runner hoàn tất command và process |
| `quit.enabled=false` nhưng vẫn thoát được bằng `exit` | Đang chạy interactive mode | Đây là hành vi được thiết kế; property chỉ tác động registry non-interactive |
| Sau `exit`, JVM vẫn còn chạy | Background thread hoặc scheduler vẫn giữ process sống | Xem xét `spring.shell.context.close=true` và vòng đời các tác vụ nền |
| `version` chỉ hiển thị phiên bản Spring Shell | Chưa có build/Git metadata hoặc trường chưa được bật | Tạo `BuildProperties`/`GitProperties` và cấu hình `show-*` |
| Nhầm phiên bản Shell với phiên bản ứng dụng | Built-in `version` không mặc định là app release command | Tạo property `app.version` hoặc command `app-version` riêng |
| `clear` không làm sạch màn hình như mong đợi | Terminal emulator hoặc môi trường không hỗ trợ thao tác màn hình | Kiểm tra terminal/JLine và tránh dùng clear trong output redirect |

## 10. Checklist sử dụng `clear`, `exit` và `version`

- [ ] Đã xác định ứng dụng chạy interactive hay non-interactive.
- [ ] Dùng `clear` tại prompt interactive khi cần làm sạch màn hình.
- [ ] Phân biệt `clear` của Spring Shell với `clear`, `Clear-Host` hoặc `cls` của hệ điều hành.
- [ ] Dùng `quit` hoặc alias `exit` để kết thúc interactive shell loop.
- [ ] Chỉ bật `spring.shell.context.close=true` khi vòng đời ứng dụng cần đóng context sau shell.
- [ ] Không dùng `exit` làm bước điều khiển luồng trong script non-interactive.
- [ ] Dùng `version` để kiểm tra phiên bản Spring Shell.
- [ ] Có `BuildProperties`/`GitProperties` nếu muốn hiển thị metadata build và Git.
- [ ] Tạo command riêng nếu cần hiển thị phiên bản sản phẩm của ứng dụng.
- [ ] Kiểm tra các property enable/disable trong đúng profile triển khai.
- [ ] Đã thử `help` và các built-in command trên terminal thực tế.

## Tài liệu tham khảo

1. [Spring Shell 4 – Built-In Commands](https://docs.spring.io/spring-shell/reference/commands/builtin/index.html) – danh sách các command có sẵn.
2. [Spring Shell 4 – Clear](https://docs.spring.io/spring-shell/reference/commands/builtin/clear.html) – hành vi xóa màn hình terminal.
3. [Spring Shell 4 – Exit](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html) – `quit`, alias `exit`, cấu hình trong non-interactive mode.
4. [Spring Shell 4 – Version](https://docs.spring.io/spring-shell/reference/commands/builtin/version.html) – phiên bản Spring Shell được sử dụng.
5. [Spring Shell 4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html) – interactive/non-interactive mode và `ShellRunner`.
6. [Spring Shell 4 – Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html) – cấu hình `spring.shell.context.close`.
7. [Spring Shell 4 – `StandardCommandsAutoConfiguration` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/StandardCommandsAutoConfiguration.html) – auto-configuration và các property bật/tắt standard commands.

Hãy chọn command theo môi trường chạy: `clear` hỗ trợ phiên terminal tương tác, `exit`/`quit` kết thúc REPL, còn `version` cung cấp thông tin phiên bản để kiểm tra artifact. Khi chuyển CLI sang script hoặc CI, hãy xác định rõ runner và vòng đời ApplicationContext để hành vi kết thúc tiến trình luôn dự đoán được.
