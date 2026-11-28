# Vai trò của runner đối với vòng đời toàn bộ phiên

Spring Shell cung cấp hạ tầng để xây dựng ứng dụng dòng lệnh theo mô hình Spring: đăng ký command, đọc input, phân tích đối số, thực thi command, hiển thị kết quả và xử lý lỗi. Thành phần điều phối các bước này trong suốt một phiên shell là **`ShellRunner`**.

Runner quyết định ứng dụng bắt đầu phiên tương tác hay chạy command theo kiểu không tương tác, lấy input từ đâu, lặp qua các command như thế nào và khi nào kết thúc vòng thực thi. Nhờ vậy, code của command có thể tập trung vào nghiệp vụ như tạo người dùng, kiểm tra trạng thái dịch vụ hoặc xuất báo cáo. Command không cần tự viết vòng lặp đọc bàn phím hay tự quản lý toàn bộ vòng đời của ứng dụng CLI.

Bài này dùng mô hình API của Spring Shell 4.0.4. Khi làm việc với Spring Shell 3.x, cần tra cứu tài liệu đúng nhánh vì cách tổ chức runner và cấu hình đã thay đổi qua các phiên bản.

## 1. Runner nằm ở đâu trong kiến trúc Spring Shell?

`ShellRunner` là interface chính để chạy một shell. Trong Spring Shell 4, interface có phương thức `run(String[] args)` nhận các đối số thô của tiến trình. Một application context chỉ sử dụng **một `ShellRunner`** để điều phối shell tại thời điểm khởi động.

Runner phối hợp với những thành phần khác:

| Thành phần | Vai trò trong phiên |
|---|---|
| `InputProvider` | Cung cấp từng dòng input. Nguồn có thể là `java.io.Console` hoặc JLine. |
| `CommandParser` | Phân tích dòng lệnh thành cấu trúc `ParsedInput`, gồm tên command, subcommand, argument và option. |
| `CommandRegistry` | Lưu danh sách command đã đăng ký và cho phép tra cứu command cần thực thi. |
| `CommandExecutor` | Thực thi command theo `CommandContext` và trả về `ExitStatus`. |
| `ShellRunner` | Điều phối cách nhận input, chuyển input thành lần gọi command, hiển thị kết quả và kết thúc phiên. |
| Spring `ApplicationContext` | Quản lý bean, dịch vụ, cấu hình và tài nguyên trong suốt thời gian ứng dụng chạy. |

Trong ứng dụng Spring Boot, các command được đăng ký từ những bean trong application context. Với mô hình annotation, Spring Boot auto-configuration phát hiện các phương thức `@Command` trong bean được quét. Ngoài Spring Boot, có thể dùng `@EnableCommand` để đăng ký các lớp chứa command. Với mô hình lập trình, command được khai báo thành bean kiểu `Command`. `CommandRegistry` tập hợp các command này và hỗ trợ đăng ký hoặc gỡ đăng ký command trong lúc ứng dụng chạy.

Runner sử dụng registry đã được chuẩn bị trong application context. Nó không chứa nghiệp vụ riêng của từng command và cũng không thay thế parser, registry hay executor.

## 2. Vòng đời một phiên shell

Trong ứng dụng Spring Boot, vòng đời tổng quát có thể hình dung như sau:

```mermaid
flowchart TD
    A[JVM khởi chạy ứng dụng] --> B[Spring Boot tạo ApplicationContext]
    B --> C[Khởi tạo bean và đăng ký command]
    C --> D[Chuẩn bị CommandRegistry và CommandParser]
    D --> E[Chọn một ShellRunner theo cấu hình]
    E --> F[ApplicationRunner gọi ShellRunner.run(args)]
    F --> G{Chế độ chạy}
    G -->|Interactive| H[Đọc dòng lệnh từ InputProvider]
    H --> I[Parse và tìm command]
    I --> J[Thực thi command]
    J --> K[Hiển thị kết quả / lỗi]
    K --> L{Tiếp tục phiên?}
    L -->|Có| H
    L -->|Không| M[Kết thúc shell loop]
    G -->|Non-interactive| N[Thực thi command hoặc script]
    N --> O[Trả kết quả và kết thúc runner]
    O --> P[Ứng dụng hoàn tất hoặc tiếp tục theo cấu hình]
    M --> P
    P --> Q[Đóng ApplicationContext và giải phóng tài nguyên]
```

Các bước có ý nghĩa như sau:

1. **Khởi động ứng dụng:** JVM gọi điểm vào của chương trình. Spring Boot tạo `ApplicationContext`, nạp cấu hình và khởi tạo các bean cần thiết.
2. **Đăng ký command:** các command được phát hiện từ bean annotation hoặc được khai báo trực tiếp dưới dạng bean `Command`. Registry trở thành danh mục command mà shell có thể gọi.
3. **Chuẩn bị runner:** auto-configuration tạo `ShellRunner` phù hợp với classpath và thuộc tính `spring.shell.interactive.enabled`.
4. **Bắt đầu thực thi:** bean `ApplicationRunner` của Spring Shell gọi `ShellRunner.run(args)` khi Spring Boot chạy các application runner.
5. **Điều phối phiên:** runner đọc input hoặc xử lý command được truyền vào, sau đó phối hợp parser, registry và executor.
6. **Kết thúc:** runner dừng vòng tương tác hoặc hoàn thành command/script. Spring Boot và application context tiếp tục quy trình đóng ứng dụng theo cấu hình và các thread còn hoạt động.

Trong Spring Boot, bean điều phối mặc định có tên `springShellApplicationRunner`. Nếu cần thay đổi logic khởi động shell, có thể cung cấp `ApplicationRunner` của riêng ứng dụng với đúng tên bean này. Chỉ nên tùy biến điểm vào khi thật sự cần thay đổi cách khởi chạy hoặc phối hợp với một quy trình khởi động khác.

## 3. Chọn runner theo chế độ chạy

Spring Shell 4 cung cấp ba implementation chính:

| Runner | Chế độ | Cách nhận lệnh | Trường hợp sử dụng |
|---|---|---|---|
| `SystemShellRunner` | Interactive | Đọc từ `java.io.Console` của JDK | CLI đơn giản, không cần các tính năng nâng cao của JLine |
| `JLineShellRunner` | Interactive | Đọc qua JLine | Cần prompt, lịch sử lệnh, completion, tô sáng hoặc trải nghiệm terminal phong phú |
| `NonInteractiveShellRunner` | Non-interactive | Nhận command từ đối số tiến trình hoặc file script được chỉ định | Script, CI/CD, automation và tác vụ chạy một lần |

Khi dùng Spring Shell starter, chế độ interactive dùng `JLineShellRunner` nếu JLine có trên classpath. Nếu không có JLine, Spring Shell dùng `SystemShellRunner`. Để chạy command theo kiểu không tương tác, đặt `spring.shell.interactive.enabled=false`; khi đó `NonInteractiveShellRunner` được sử dụng.

Ví dụ cấu hình trong `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó truyền command cùng argument khi khởi động:

```bash
java -jar target/admin-cli.jar user show --id 42
```

Có thể truyền thuộc tính ngay trên dòng lệnh Spring Boot:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  user show --id 42
```

**Lưu ý về Spring Shell 4:** interactive mode được bật mặc định, kể cả khi tiến trình nhận command-line arguments. Vì vậy, chỉ truyền `user show --id 42` không tự động khiến shell chạy command rồi thoát. Cần tắt interactive mode rõ ràng nếu mục tiêu là chạy command trong pipeline hoặc script.

## 4. Runner tương tác điều phối vòng REPL

REPL là viết tắt của *Read–Eval–Print Loop*. Runner tương tác duy trì vòng lặp này cho đến khi người dùng yêu cầu thoát hoặc runner được dừng.

Một chu kỳ điển hình gồm:

1. **Read:** `InputProvider` đọc một dòng từ console hoặc JLine. JLine còn hỗ trợ lịch sử lệnh, completion và thao tác dòng nhập.
2. **Parse:** `CommandParser` phân tích chuỗi thô thành `ParsedInput`. Parser xác định tên command, subcommand, argument và option theo cú pháp đã cấu hình.
3. **Resolve:** shell tra cứu command trong `CommandRegistry`, đồng thời kiểm tra command có tồn tại và có khả dụng hay không.
4. **Execute:** `CommandExecutor` gọi command với `CommandContext` chứa dữ liệu của lần gọi hiện tại. Command thực hiện nghiệp vụ và có thể trả `ExitStatus`.
5. **Print:** kết quả hoặc thông báo lỗi được chuyển tới output của shell. Runner flush output để người dùng nhìn thấy kết quả.
6. **Loop:** runner tiếp tục đọc dòng mới và xử lý command kế tiếp.

Ví dụ một phiên:

```text
shell:>user show --id 42
ID: 42
Name: Linh
Status: ACTIVE

shell:>user disable --id 42
User 42 has been disabled.

shell:>help
AVAILABLE COMMANDS
...

shell:>quit
```

Trong ví dụ này, runner quản lý phiên từ lúc đọc `user show` cho đến khi nhận `quit`. Mỗi command được phân tích và thực thi riêng. Command `user show` không cần biết command `user disable` sẽ được gọi sau đó, và cả hai không cần tự đọc dòng tiếp theo từ terminal.

`InteractiveShellRunner` là lớp nền cho runner tương tác. Nó nhận `InputProvider`, `CommandParser` và `CommandRegistry`; implementation cụ thể cung cấp cách đọc, in và flush output. `SystemShellRunner` dùng console chuẩn của JVM. `JLineShellRunner` dùng `JLineInputProvider` để tích hợp JLine. Lớp nền cũng cung cấp `stop()` để yêu cầu dừng runner và đánh thức thao tác đọc input đang chờ, cùng `destroy()` để tham gia vòng đời hủy bean.

## 5. Runner không tương tác xử lý một lần chạy

`NonInteractiveShellRunner` không mở prompt và không chờ người dùng nhập từng dòng. Runner nhận đối số của tiến trình, phân tích command rồi thực thi. Javadoc của Spring Shell 4 mô tả hai dạng đầu vào:

- Một command duy nhất được truyền qua đối số tiến trình.
- Một file chứa các command, được tham chiếu bằng cách thêm ký tự `@` trước tên file.

Ví dụ file `maintenance.shell`:

```text
user list --status INACTIVE
report export --format csv --output ./inactive-users.csv
```

Có thể gọi runner theo dạng tham chiếu file:

```bash
java -jar target/admin-cli.jar @maintenance.shell
```

Đường dẫn file phải được phân giải đúng theo working directory hoặc được truyền dưới dạng đường dẫn phù hợp với môi trường chạy. Với script chạy trong CI, nên dùng đường dẫn rõ ràng và bảo đảm file đã được đưa vào workspace trước khi khởi động ứng dụng.

Không nhầm cách gọi `@file` của runner với command tích hợp `script`. Command `script --file /path/to/file` có thể được gọi trong một phiên shell để chạy tuần tự các dòng command từ file. `@file` là cách đưa file script vào đối số tiến trình để runner không tương tác xử lý ngay khi ứng dụng khởi động.

## 6. Runner, kết quả command và lỗi

Runner điều phối việc thực thi; command chịu trách nhiệm xử lý nghiệp vụ và trả kết quả. Trong Spring Shell 4, `Command.execute(CommandContext)` trả về `ExitStatus`, gồm `code` và `description`. Các trạng thái có sẵn gồm `OK`, `USAGE_ERROR`, `EXECUTION_ERROR` và `AVAILABILITY_ERROR`.

Ví dụ khai báo command theo mô hình lập trình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class StatusCommandConfiguration {

    @Bean
    Command serviceStatus() {
        return Command.builder()
                .name("service-status")
                .description("Display service status")
                .execute(context -> {
                    context.outputWriter().println("Service is healthy");
                    return ExitStatus.OK;
                })
                .build();
    }
}
```

Khi command phát sinh exception, `ExitStatusExceptionMapper` cho phép ánh xạ exception thành `ExitStatus` có mã và thông báo phù hợp. Có thể khai báo mapper dưới dạng Spring bean và tham chiếu từ thuộc tính `exitStatusExceptionMapper` của `@Command`, hoặc gắn mapper vào `Command.Builder`.

Ví dụ mapper dùng chung:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper shellExceptionMapper() {
        return exception -> new ExitStatus(42, "Command failed: " + exception.getMessage());
    }
}
```

Trong interactive mode, thông báo lỗi giúp người dùng sửa input hoặc thử command khác trong cùng phiên. Trong non-interactive mode, mã trạng thái là thông tin quan trọng cho script hoặc CI quyết định bước tiếp theo. Hãy thiết kế mã lỗi ổn định và kiểm tra mã thoát của tiến trình bằng cách chạy artifact thực tế trong môi trường mục tiêu.

Khi cần xem stack trace trong lúc phát triển, bật debug mode:

```yaml
spring:
  shell:
    debug:
      enabled: true
```

Debug mode giúp hiển thị stack trace của lỗi trong interactive mode. Không nên phụ thuộc vào stack trace để làm giao thức đầu ra cho script; hãy dùng thông báo và mã trạng thái có cấu trúc.

## 7. Kết thúc phiên và đóng application context

Kết thúc vòng lặp shell và đóng `ApplicationContext` là hai việc liên quan nhưng không đồng nhất.

Trong interactive mode, command tích hợp `quit` (bí danh `exit`) yêu cầu kết thúc vòng shell tương tác. Spring Shell 4.0.4 mô tả `quit` là thao tác thoát interactive loop. Nếu cần đóng rõ ràng Spring application context sau khi shell hoàn tất, bật thuộc tính:

```yaml
spring:
  shell:
    context:
      close: true
```

Thuộc tính `spring.shell.context.close` không được bật mặc định. Tài liệu Spring Shell giải thích rằng command được chạy thông qua các bean `ApplicationRunner`. Khi các runner hoàn tất, JVM có thể kết thúc nếu không còn non-daemon thread giữ tiến trình sống; shutdown hook của Spring Boot sẽ đóng application context. Các thread nền, chẳng hạn thread từ scheduling, có thể khiến tiến trình tiếp tục chạy. Bật `spring.shell.context.close=true` sẽ đăng ký listener yêu cầu đóng context sau khi shell hoàn tất logic thực thi.

Với JLine, terminal là tài nguyên cần đóng. Auto-configuration của JLine đăng ký xử lý sự kiện `ContextClosedEvent` và terminal bean có destroy method để giải phóng tài nguyên. Khi tự tạo runner hoặc terminal, cần bảo đảm tài nguyên tương ứng cũng được đóng trong vòng đời bean.

Ở non-interactive mode, runner hoàn tất sau command hoặc script. Nếu ứng dụng chỉ dùng để thực hiện tác vụ một lần, hãy kiểm tra ứng dụng có kết thúc đúng lúc hay không, đặc biệt khi có `@EnableScheduling`, executor hoặc thread nền khác. Đừng dùng `System.exit()` bên trong command để ép tiến trình thoát vì cách đó bỏ qua cơ chế đóng bean và tài nguyên có quản lý của Spring.

## 8. Khi nào cần tùy biến runner?

Thông thường, chỉ cần chọn chế độ bằng cấu hình và để auto-configuration tạo runner phù hợp. Tùy biến runner hoặc `ApplicationRunner` chỉ hữu ích khi ứng dụng có yêu cầu khởi động đặc biệt, chẳng hạn:

- Phải kiểm tra điều kiện môi trường trước khi mở shell.
- Cần nạp cấu hình hoặc dữ liệu ban đầu trước khi runner đọc command đầu tiên.
- Muốn thay cách lấy input hoặc cách hiển thị output.
- Muốn phối hợp một tác vụ khởi động riêng với thời điểm bắt đầu phiên shell.

Trong Spring Boot, có thể thay bean `springShellApplicationRunner` để điều khiển thời điểm gọi runner. Nếu chỉ cần đổi từ interactive sang non-interactive, hãy dùng `spring.shell.interactive.enabled` thay vì viết lại ApplicationRunner.

Spring Shell 4 chỉ dùng một `ShellRunner` trong một application context. Nếu ứng dụng cần cả tương tác và automation, hãy chọn chế độ khi khởi động mỗi tiến trình. Có thể đóng gói cùng một ứng dụng và chạy với cấu hình khác nhau cho terminal của người dùng hoặc pipeline CI.

## 9. Kiểm thử vòng đời runner

Kiểm thử command riêng lẻ chưa đủ để xác nhận toàn bộ ứng dụng CLI. Cần kiểm tra runner ở đúng chế độ mà sản phẩm sẽ sử dụng.

| Tình huống | Điều cần xác minh |
|---|---|
| Khởi động interactive | Runner phù hợp được tạo và prompt xuất hiện |
| Nhập command hợp lệ | Input được parse, command được gọi và output hiển thị |
| Nhập command không tồn tại hoặc sai option | Lỗi được trình bày rõ và phiên interactive có thể tiếp tục |
| Chạy non-interactive với một command | Command được thực thi và runner kết thúc |
| Chạy file script | Các dòng command được xử lý theo đúng thứ tự |
| Gõ `quit` hoặc `exit` | Interactive loop dừng theo yêu cầu |
| Đóng application context | Terminal, thread và tài nguyên do bean quản lý được giải phóng |
| Chạy từ CI | Mã thoát và output phù hợp để script kiểm tra |

Ví dụ, khi kiểm thử non-interactive, đặt `spring.shell.interactive.enabled=false`, truyền command vào `ShellTestClient` hoặc khởi chạy ứng dụng với đối số thực tế, rồi xác nhận kết quả. Với kiểm thử tích hợp, hãy bảo đảm không vô tình khởi tạo interactive runner trong test vì runner có thể chờ input và làm test bị treo.

## 10. Bài tập thực hành

Bạn xây dựng một ứng dụng quản trị tên `admin-cli` có hai cách sử dụng:

- Nhân viên hỗ trợ mở terminal và nhập nhiều command để xem thông tin, khóa tài khoản hoặc kiểm tra dịch vụ.
- Pipeline CI chạy một command hoặc một file script để xuất báo cáo mỗi đêm.

Hãy thực hiện các yêu cầu sau:

1. Khai báo ít nhất hai command bằng `@Command` hoặc bean `Command`, sau đó xác minh chúng xuất hiện trong `CommandRegistry`.
2. Chạy ứng dụng với interactive mode mặc định. Theo dõi một chu kỳ đọc, parse, thực thi và hiển thị kết quả.
3. Gõ command sai rồi gõ command đúng. Xác minh lỗi không làm mất toàn bộ phiên interactive.
4. Tạo file script có hai command và chạy bằng `NonInteractiveShellRunner` với cú pháp `@file`.
5. Đặt `spring.shell.interactive.enabled=false`, truyền một command qua đối số tiến trình và xác minh ứng dụng không chờ prompt.
6. Tạo `ExitStatusExceptionMapper` để ánh xạ một exception nghiệp vụ thành mã trạng thái riêng. Gọi command gây lỗi và ghi lại thông báo cùng mã trả về.
7. Gõ `quit` trong phiên tương tác. Thử thêm `spring.shell.context.close=true` và quan sát thời điểm application context được đóng.
8. Chạy ứng dụng từ script hoặc CI để xác nhận mã thoát và bảo đảm tiến trình không bị giữ lại bởi thread nền.

**Kết quả cần nộp:** sơ đồ vòng đời phiên, cấu hình cho hai chế độ chạy, file script, kết quả kiểm thử command lỗi/thành công và bằng chứng application context kết thúc đúng kỳ vọng.

## 11. Checklist khi thiết kế vòng đời phiên

- [ ] Đã phân biệt trách nhiệm của `ShellRunner`, `InputProvider`, `CommandParser`, `CommandRegistry` và `CommandExecutor`.
- [ ] Đã xác định ứng dụng dùng interactive hay non-interactive mode.
- [ ] Đã kiểm tra `spring.shell.interactive.enabled`; không giả định có command-line arguments là tự chuyển sang non-interactive.
- [ ] Chỉ có một `ShellRunner` được sử dụng trong application context.
- [ ] Command được đăng ký trước khi runner bắt đầu xử lý input.
- [ ] Command tập trung vào nghiệp vụ; runner quản lý vòng lặp và phiên làm việc.
- [ ] Exception được ánh xạ thành thông báo và `ExitStatus` phù hợp.
- [ ] Đã kiểm tra hành vi `quit`/`exit` và cấu hình đóng application context.
- [ ] Đã kiểm tra tài nguyên terminal và thread nền được giải phóng.
- [ ] Đã chạy thử non-interactive command/script và xác nhận mã thoát trong môi trường gần production.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell API — ShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ShellRunner.html)
- [Spring Shell API — InteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InteractiveShellRunner.html)
- [Spring Shell API — NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell API — CommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html)
- [Spring Shell API — CommandExecutor](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html)
- [Spring Shell — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell — Exit](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html)
- [Spring Shell — Script](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell — Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html)
