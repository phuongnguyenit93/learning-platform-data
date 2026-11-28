# stacktrace trong nhánh cũ so với debug mode ở 4.x

## 1. Vì sao cần xem stack trace?

Khi một command phát sinh exception, người dùng thường chỉ cần biết thao tác thất bại và lý do ngắn gọn. Ví dụ: “Không thể kết nối đến máy chủ” hoặc “Không tìm thấy tài khoản A001”. Thông tin này phù hợp với người vận hành, nhưng chưa đủ để lập trình viên xác định lỗi bắt đầu ở đâu, đi qua những phương thức nào hoặc có nguyên nhân gốc nào được bọc bên trong.

**Stack trace** ghi lại chuỗi lời gọi phương thức tại thời điểm exception xảy ra. Nó giúp xác định:

- Lớp và phương thức phát sinh lỗi.
- Dòng mã cần kiểm tra.
- Các lớp gọi dẫn đến vị trí lỗi.
- Chuỗi `Caused by` nếu exception hiện tại bọc một exception khác.

Spring Shell thay đổi cách xem stack trace giữa phiên bản 3.x và 4.x. Ở nhánh 3.x, shell giữ exception gần nhất để người dùng gọi command `stacktrace` khi cần. Từ 4.x, command này bị loại bỏ và được thay bằng debug mode để in stack trace ngay khi lỗi xảy ra trong phiên tương tác.

## 2. Cách hoạt động trong Spring Shell 3.x

Trong Spring Shell 3.x, khi code của command ném exception, shell bắt exception và hiển thị một thông báo ngắn trên terminal. Framework lưu exception gần nhất để người dùng có thể xem chi tiết sau đó bằng command built-in `stacktrace`.

Ví dụ command cố ý phát sinh lỗi:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DiagnosticCommands {

    @ShellMethod(key = "demo fail", value = "Mô phỏng một lỗi để kiểm tra stack trace")
    public String fail() {
        throw new IllegalStateException("Không thể đọc cấu hình dịch vụ");
    }
}
~~~

Khi chạy trong shell tương tác, người dùng có thể thấy thông báo rút gọn tương tự:

~~~text
shell:>demo fail
Command failed: Không thể đọc cấu hình dịch vụ
~~~

Sau đó gọi:

~~~text
shell:>stacktrace
~~~

Shell in stack trace của exception gần nhất, bao gồm các frame gọi và nguyên nhân lồng nhau nếu có. Câu chữ thông báo lỗi đầu tiên phụ thuộc result handler và phiên bản; ví dụ trên chỉ minh họa hành vi, không phải output cố định.

Command `stacktrace` được thiết kế cho chế độ tương tác. Nó hiển thị exception cuối cùng mà shell đã ghi nhận, vì vậy nếu một lỗi mới xảy ra trước khi người dùng gọi `stacktrace`, thông tin cần xem có thể đã bị thay thế bằng lỗi mới hơn.

### Bật hoặc tắt command stacktrace trong 3.x

Trong ứng dụng Spring Boot dùng Spring Shell 3.x, command built-in có thể được cấu hình bằng property:

~~~properties
spring.shell.command.stacktrace.enabled=true
~~~

Để tắt command này:

~~~properties
spring.shell.command.stacktrace.enabled=false
~~~

Mặc định, auto-configuration đăng ký command nếu không có command khác thay thế và property không bị đặt thành `false`. Có thể tắt nó khi ứng dụng không muốn cung cấp khả năng xem stack trace trực tiếp trong shell, nhưng đội phát triển vẫn cần một kênh chẩn đoán phù hợp như log ứng dụng.

## 3. Vì sao Spring Shell 4.x bỏ command stacktrace?

Command `stacktrace` của 3.x cần giữ exception gần nhất trong trạng thái có thể truy cập toàn cục để command built-in đọc lại. Cách này tạo ra trạng thái mutable dùng chung và buộc người dùng phải thực hiện thêm một lệnh sau khi gặp lỗi.

Spring Shell 4.x loại bỏ command `stacktrace` và bổ sung **debug mode**. Khi debug mode được bật, shell in stack trace ngay khi command phát sinh lỗi trong chế độ tương tác. Người dùng không cần gọi một command thứ hai để lấy chi tiết của lỗi vừa xảy ra.

Đây là thay đổi về trải nghiệm chẩn đoán:

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Shell hiển thị thông báo ngắn khi command lỗi. | Ở chế độ thường, shell vẫn hướng đến thông báo lỗi gọn. |
| Exception gần nhất được lưu để truy vấn sau. | Debug mode in stack trace ngay tại thời điểm lỗi. |
| Người dùng gõ `stacktrace` để xem chi tiết. | Không còn built-in command `stacktrace`. |
| Có thể tắt command bằng `spring.shell.command.stacktrace.enabled=false`. | Dùng `spring.shell.debug.enabled` để bật hoặc tắt việc in stack trace trong interactive mode. |

Migration guide của Spring Shell 4.x nêu rõ command cũ bị loại bỏ vì yêu cầu lưu trạng thái exception toàn cục; debug mode thay thế bằng cách in stack trace ngay khi lỗi xảy ra.

## 4. Bật debug mode trong Spring Shell 4.x

Property dùng để bật debug mode là:

~~~properties
spring.shell.debug.enabled=true
~~~

Đặt trong `src/main/resources/application.properties` nếu muốn mọi lần chạy cấu hình đó đều in stack trace khi command lỗi trong interactive mode.

Khi bật debug mode, một lỗi có thể được hiển thị theo dạng minh họa:

~~~text
shell:>demo fail
Command failed: Không thể đọc cấu hình dịch vụ

java.lang.IllegalStateException: Không thể đọc cấu hình dịch vụ
    at com.example.cli.DiagnosticCommands.fail(DiagnosticCommands.java:18)
    at ...
~~~

Các frame cụ thể phụ thuộc code và runtime. Nếu exception có nguyên nhân gốc, stack trace có thể hiển thị thêm phần `Caused by`.

Để tắt debug mode, đặt:

~~~properties
spring.shell.debug.enabled=false
~~~

Không cần tạo command riêng hoặc lưu exception vào một biến toàn cục chỉ để phục vụ thao tác xem stack trace sau đó.

### Chỉ bật debug trong môi trường phát triển

Không nên bật stack trace chi tiết cho mọi người dùng ở mọi môi trường. Có thể tạo file `application-debug.properties`:

~~~properties
spring.shell.debug.enabled=true
~~~

Khi cần chẩn đoán, kích hoạt profile `debug` lúc khởi chạy ứng dụng:

~~~bash
java -Dspring.profiles.active=debug -jar target/my-shell.jar
~~~

Hoặc bật bằng biến môi trường theo quy tắc relaxed binding của Spring Boot:

~~~bash
SPRING_SHELL_DEBUG_ENABLED=true java -jar target/my-shell.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_SHELL_DEBUG_ENABLED = "true"
java -jar .\target\my-shell.jar
Remove-Item Env:SPRING_SHELL_DEBUG_ENABLED
~~~

Các ví dụ trên dùng Spring Boot để nạp cấu hình. Nếu ứng dụng Spring Shell 4.x không dùng Spring Boot, cần cung cấp cấu hình tương ứng cho `SpringShellProperties` hoặc cấu hình runner theo cách ứng dụng khởi tạo; property binding của Boot không tự xuất hiện trong một application context thuần Spring.

## 5. Debug mode áp dụng trong phạm vi nào?

Tài liệu Spring Shell 4.x mô tả `spring.shell.debug.enabled=true` là chế độ bổ sung thông tin chẩn đoán trong **interactive mode**, bằng cách in stack trace của lỗi command. Vì vậy, hãy kiểm tra chế độ chạy trước khi kết luận rằng property không hoạt động.

Spring Shell 4.x phân biệt shell tương tác và non-interactive. Trong ứng dụng Spring Boot, interactive mode được bật mặc định; muốn thực thi command từ tham số tiến trình rồi kết thúc, cấu hình `spring.shell.interactive.enabled=false`.

Trong non-interactive mode, không có phiên shell để người dùng gõ `stacktrace`. Tài liệu debug mode của Spring Shell 4.x mô tả rõ hành vi in stack trace trong interactive mode; không nên suy rộng property này thành một công tắc điều khiển mọi output lỗi của runner non-interactive. Với script, hãy kiểm tra output, mã thoát và log của đúng runner/phiên bản đang dùng.

Ví dụ cấu hình chạy một command từ tiến trình:

~~~properties
spring.shell.interactive.enabled=false
~~~

Đừng nhầm property này với debug mode. `spring.shell.interactive.enabled` chọn runner và cách ứng dụng nhận lệnh; `spring.shell.debug.enabled` điều khiển việc in thông tin stack trace trong debug mode của shell tương tác.

## 6. Debug mode không phải logging level DEBUG

Hai cấu hình có mục đích khác nhau:

| Cấu hình | Tác động |
|---|---|
| `spring.shell.debug.enabled=true` | Bật debug mode của Spring Shell để in stack trace khi command lỗi trong interactive mode. |
| `logging.level.root=DEBUG` | Tăng mức log của các logger trong ứng dụng theo cấu hình logging. |
| `logging.level.com.example=DEBUG` | Tăng mức log cho package ứng dụng được chỉ định. |

Ví dụ, đặt mức log cho package ứng dụng:

~~~properties
logging.level.com.example=DEBUG
~~~

Điều này không phải cách thay thế trực tiếp cho `spring.shell.debug.enabled`. Ngược lại, bật debug mode cũng không tự động làm mọi logger của ứng dụng chuyển sang mức DEBUG.

Khi chẩn đoán một lỗi, có thể cần cả hai: stack trace để xem chuỗi lời gọi và log ở mức phù hợp để hiểu dữ liệu hoặc trạng thái tại từng bước. Hãy cấu hình từng cơ chế theo nhu cầu, tránh bật log quá chi tiết nếu không cần thiết.

## 7. Stack trace và thông báo lỗi dành cho người dùng

Stack trace hữu ích với lập trình viên nhưng thường quá dài và chứa chi tiết nội bộ. Không nên xem nó là thông báo nghiệp vụ mặc định cho người vận hành hoặc người dùng cuối.

Ví dụ, command có thể để exception nghiệp vụ có kiểu riêng thoát ra khỏi phương thức:

~~~java
@Command(name = "account show", description = "Hiển thị tài khoản")
public String show(@Option(longName = "id", required = true) long id) {
    Account account = accountService.findById(id)
            .orElseThrow(() -> new AccountNotFoundException(id));
    return account.toDisplayString();
}
~~~

Đây là phần thân command minh họa; `Account`, `accountService` và `AccountNotFoundException` là kiểu của ứng dụng. Exception có kiểu riêng có thể được xử lý hoặc ánh xạ thành thông báo và `ExitStatus` phù hợp. Trong ứng dụng thực tế, nên phân biệt lỗi có thể dự đoán với lỗi bất ngờ:

- Lỗi nghiệp vụ dự kiến, như không tìm thấy tài khoản hoặc trạng thái không cho phép thao tác, nên có thông báo dễ hiểu và mã thoát phù hợp.
- Lỗi kỹ thuật bất ngờ, như `NullPointerException`, lỗi kết nối hoặc lỗi lập trình, cần được ghi nhận với nguyên nhân và stack trace để đội phát triển điều tra.
- Không đưa mật khẩu, token, chuỗi kết nối, dữ liệu cá nhân hoặc nội dung nhạy cảm vào thông báo hoặc log nếu không có lý do và biện pháp bảo vệ phù hợp.

Trong Spring Shell 4.x, cơ chế exception mapping và `ExitStatus` giúp kiểm soát kết quả command. Debug mode chỉ bổ sung chi tiết chẩn đoán; nó không thay thế việc phân loại lỗi, xử lý exception nghiệp vụ hoặc thiết kế mã thoát cho script.

## 8. Những điểm cần lưu ý khi nâng cấp từ 3.x lên 4.x

Khi nâng cấp, hãy rà soát các đoạn tài liệu vận hành và script có gọi command `stacktrace`:

1. Xóa hướng dẫn yêu cầu người dùng chạy `stacktrace` sau khi gặp lỗi vì command này không còn trong 4.x.
2. Chuyển cấu hình chẩn đoán sang `spring.shell.debug.enabled=true` khi cần stack trace ngay lập tức trong interactive mode.
3. Chỉ bật debug mode trong môi trường phát triển hoặc khi có yêu cầu điều tra cụ thể.
4. Kiểm tra cách xử lý exception của ứng dụng, bao gồm thông báo, `ExitStatus` và log.
5. Kiểm tra riêng interactive và non-interactive mode vì chúng có cách hiển thị lỗi khác nhau.
6. Cập nhật tài liệu onboarding và runbook để không còn chỉ dẫn cũ về command `stacktrace`.

Không nên cố khôi phục command cũ chỉ để giữ nguyên thói quen thao tác nếu ứng dụng đã chuyển sang 4.x. Nếu có yêu cầu đặc biệt cần truy xuất lịch sử nhiều exception, hãy thiết kế một cơ chế chẩn đoán riêng có giới hạn truy cập, vòng đời và chính sách lưu trữ rõ ràng.

## 9. Quy trình chẩn đoán lỗi command

Khi command thất bại, có thể làm theo trình tự:

1. Đọc thông báo ngắn để xác định command và điều kiện thất bại.
2. Xác nhận phiên bản Spring Shell đang chạy là 3.x hay 4.x.
3. Với 3.x interactive, gọi `stacktrace` để xem exception gần nhất.
4. Với 4.x interactive, bật `spring.shell.debug.enabled=true` rồi chạy lại thao tác để nhận stack trace ngay khi lỗi xảy ra.
5. Đọc frame đầu tiên thuộc package ứng dụng và lần theo các frame gọi phía trên.
6. Tìm phần `Caused by` sâu nhất có liên quan để xác định nguyên nhân gốc.
7. Đối chiếu với log ứng dụng, trạng thái hệ thống và dữ liệu đầu vào tại thời điểm xảy ra lỗi.
8. Sau khi điều tra, tắt debug mode nếu không còn cần thiết và giữ lại log đã được xử lý theo chính sách của môi trường.

## Kết luận

Spring Shell 3.x lưu exception gần nhất và cung cấp command `stacktrace` để người dùng chủ động xem chi tiết sau khi lỗi xảy ra. Spring Shell 4.x loại bỏ command này và thay bằng debug mode, bật qua `spring.shell.debug.enabled=true`, để in stack trace ngay khi command lỗi trong interactive mode. Khi nâng cấp, hãy cập nhật runbook và cách cấu hình chẩn đoán; đồng thời tách stack trace dành cho lập trình viên khỏi thông báo nghiệp vụ, logging level và mã thoát mà script sử dụng.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Stacktrace command](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/stacktrace.html)
- [Spring Shell 3.4 API – Stacktrace](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Stacktrace.html)
- [Spring Shell 3.4 API – Stacktrace.Command](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Stacktrace.Command.html)
- [Spring Shell 4.0.4 – Execution and Debug Mode](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
