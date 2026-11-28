# Ứng dụng khởi động rồi thoát do chế độ hoặc mặc định runner

Một ứng dụng Spring Shell có thể in banner Spring Boot, tạo bean thành công và ghi `Started ...`, sau đó đóng `ApplicationContext` rồi kết thúc process ngay. Nếu log không có lỗi khởi động, nguyên nhân thường nằm ở cách Spring Shell chọn runner: ứng dụng đang chạy ở chế độ non-interactive, runner interactive chưa được bật, hoặc runner điều phối shell không được đăng ký.

Điểm thay đổi dễ gây nhầm nhất nằm ở Spring Shell 3.3.x. Từ phiên bản này, chỉ `NonInteractiveShellRunner` được bật mặc định; `InteractiveShellRunner` không tự mở REPL nếu chưa bật `spring.shell.interactive.enabled=true`. Vì vậy, một ứng dụng trước đây chạy được bằng cách gọi `java -jar app.jar` có thể khởi động rồi thoát sau khi nâng từ 3.2.x lên 3.3.x mà không có lỗi nghiệp vụ nào.

## Nhận diện đúng triệu chứng

Trước tiên, phân biệt process thoát bình thường sau khi hoàn tất runner với lỗi khiến ứng dụng không khởi động:

| Dấu hiệu | Khả năng cao | Hướng kiểm tra |
|---|---|---|
| Có `Started ...`, ngay sau đó có log đóng context và process exit code `0` | Runner đã hoàn tất; REPL không được mở hoặc invocation là one-shot | Kiểm tra phiên bản và `spring.shell.*.enabled` |
| Có `Started ...`, không thấy prompt, nhưng process vẫn chạy | Runner có thể đang chờ ở input provider hoặc terminal không hiển thị prompt | Kiểm tra TTY/console, JLine provider và output stream |
| Có `APPLICATION FAILED TO START`, stack trace hoặc exit code khác `0` | Lỗi cấu hình/bean/dependency hoặc lỗi khi thực thi runner | Đọc exception đầu tiên và condition report |
| Chạy từ terminal được nhưng chạy từ IDE lại thoát | Run configuration, program arguments, active profile hoặc console khác nhau | So sánh VM options, program arguments và environment |
| Chỉ thoát sau khi một command hoàn tất | Đang chạy non-interactive command đúng thiết kế | Kiểm tra command và exit status |

Một dòng `Started ...` xác nhận Spring Boot đã hoàn tất giai đoạn khởi động. Nó không chứng minh REPL đã được mở. Nếu ứng dụng thoát với mã `0`, đừng vội sửa lỗi bằng cách tạo thread nền hoặc bật web server; hãy xác định runner nào đã được chọn và runner đó có chủ đích kết thúc process hay không.

## Kiểm tra thay đổi mặc định theo phiên bản

Đối chiếu phiên bản Spring Shell trước khi sửa cấu hình:

| Phiên bản | Runner mặc định | Cách mở REPL |
|---|---|---|
| Spring Shell 3.2.x trở xuống | `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner` đều được bật mặc định | Chạy ứng dụng không có command arguments thường mở interactive shell |
| Spring Shell 3.3.x và 3.4.x | Chỉ `NonInteractiveShellRunner` được bật mặc định | Bật `spring.shell.interactive.enabled=true` |
| Spring Shell 4.0.x | Interactive mode được bật mặc định | Thường không cần đặt property; kiểm tra xem cấu hình có ghi đè thành `false` không |

Spring Shell 3.3.x thay đổi mặc định để tách rõ ứng dụng chạy một command từ arguments với ứng dụng mở REPL. Khi chỉ có non-interactive runner, process được khởi động để xử lý command truyền vào; nếu không có command phù hợp để thực thi, không có vòng REPL giữ process hoạt động. Spring Boot kết thúc khi các startup runner đã hoàn tất và không còn thread non-daemon giữ JVM.

Trong Spring Shell 4, mặc định quay lại interactive mode. Với starter, interactive runner dùng JLine; nếu JLine không có trên classpath, Spring Shell dùng `SystemShellRunner` dựa trên Java Console. Để chạy một command từ process arguments, đặt `spring.shell.interactive.enabled=false`.

## Cách sửa nhanh cho Spring Shell 3.3.x và 3.4.x

Nếu mục tiêu là mở REPL khi người dùng chạy ứng dụng mà không truyền command, bật interactive runner trong `application.yaml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Sau đó build và chạy lại:

```bash
./mvnw clean package
java -jar target/customer-cli.jar
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean package
java -jar .\target\customer-cli.jar
```

Khi REPL hoạt động, ứng dụng sẽ hiển thị prompt, chờ command và tiếp tục chạy cho tới khi người dùng gọi `exit`/`quit` hoặc shell kết thúc theo cơ chế được cấu hình.

Không cần tắt `spring.shell.noninteractive.enabled` chỉ để mở REPL. Trong Spring Shell 3.3.x/3.4.x, có thể bật nhiều runner; thứ tự ưu tiên giúp runner phù hợp xử lý invocation. Cấu hình mẫu của tài liệu chính thức bật interactive runner bằng property trên và giữ non-interactive runner ở trạng thái mặc định.

### Cấu hình thêm nếu cần chạy script lúc khởi động

Nếu ứng dụng cần thực thi một file chứa nhiều command rồi kết thúc, bật script runner:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true
```

Chạy file script bằng đối số `@file`:

```bash
java -jar target/customer-cli.jar @examples/startup.shell
```

Đừng nhầm `ScriptShellRunner` nhận `@file` lúc khởi động với built-in `script` command được gọi bên trong một phiên REPL. Nếu muốn mở REPL sau khi script kết thúc, hãy kiểm thử thứ tự runner và hành vi phiên bản đang dùng; invocation script thường được thiết kế để chạy batch rồi kết thúc.

## Chọn đúng kiểu chạy theo mục đích

Một CLI có thể được dùng theo ba cách khác nhau. Cần quyết định rõ cách chạy nào là mặc định cho người dùng:

| Mục đích | Spring Shell 3.3.x/3.4.x | Spring Shell 4.0.x |
|---|---|---|
| Mở REPL khi chạy không có command | `spring.shell.interactive.enabled=true` | Mặc định interactive |
| Chạy một command rồi thoát | Truyền command arguments; `NonInteractiveShellRunner` mặc định bật | Đặt `spring.shell.interactive.enabled=false`, rồi truyền command |
| Chạy chuỗi command từ file | Bật `spring.shell.script.enabled=true`, truyền `@file` | Dùng cơ chế script/command được hỗ trợ bởi phiên bản 4.x và kiểm tra mode đã chọn |

Ví dụ chạy một command non-interactive trong Spring Shell 3.3.x/3.4.x:

```bash
java -jar target/customer-cli.jar customer-list --status ACTIVE --limit 20
```

Process thực thi command rồi trả exit status cho shell hệ điều hành. Đây là hành vi mong đợi của một CLI dùng trong script hoặc CI.

Trong Spring Shell 4.0.x, nếu muốn chạy command từ arguments thay vì mở REPL, cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó:

```bash
java -jar target/customer-cli.jar customer-list --status ACTIVE --limit 20
```

Nếu đặt `interactive.enabled=false` trong cấu hình dùng chung, ứng dụng 4.x sẽ không mở REPL khi chạy không có command. Hãy kiểm tra profile, environment variable và command-line property trước khi kết luận runner bị lỗi.

## Phân biệt runner với InteractionMode của command

Trong Spring Shell 3.x, có hai lớp khái niệm dễ bị nhầm:

- **Shell runner** quyết định ứng dụng mở REPL, chạy command từ arguments hay chạy script.
- **`InteractionMode` của command** quyết định command được phép xuất hiện trong interactive hoặc non-interactive invocation.

Đặt `@ShellMethod(interactionMode = InteractionMode.INTERACTIVE)` không tự bật `InteractiveShellRunner`. Nếu runner interactive chưa được đăng ký, annotation này không thể giữ ứng dụng ở REPL.

Ví dụ command chỉ dành cho interactive mode:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.context.InteractionMode;

@ShellComponent
class SessionCommands {

    @ShellMethod(
            key = "session-info",
            value = "Hiển thị thông tin phiên shell.",
            interactionMode = InteractionMode.INTERACTIVE)
    public String sessionInfo() {
        return "Phiên shell đang hoạt động.";
    }
}
```

Nếu REPL đã mở nhưng một command không xuất hiện trong `help`, kiểm tra `interactionMode` của command. Nếu cả prompt lẫn REPL đều không xuất hiện và process kết thúc, kiểm tra runner trước.

Trong Spring Shell 4, `InteractionMode` đã bị loại bỏ; command không còn được đánh dấu riêng cho interactive/non-interactive mode. Ứng dụng chọn mode khi khởi động bằng `spring.shell.interactive.enabled`.

## Kiểm tra cấu hình đang thực sự được nạp

Property trong file có thể bị ghi đè bởi profile, environment variable, Java system property hoặc command-line arguments. Spring Boot ưu tiên nguồn cấu hình có độ ưu tiên cao hơn; vì vậy, sửa `application.yaml` nhưng vẫn thoát có thể do một nguồn khác đang đặt `spring.shell.interactive.enabled=false`.

Kiểm tra lần lượt:

1. Ứng dụng đang chạy phiên bản Spring Shell nào?
2. Profile nào đang active (`dev`, `test`, `prod`)?
3. File `application-{profile}.yaml` có đặt `spring.shell.interactive.enabled` không?
4. Environment có `SPRING_SHELL_INTERACTIVE_ENABLED=false` không?
5. VM options có `-Dspring.shell.interactive.enabled=false` không?
6. Program arguments có `--spring.shell.interactive.enabled=false` không?
7. Có cấu hình runner tùy chỉnh hoặc bean điều phối shell bị thay thế không?

Với Maven, kiểm tra dependency thực tế:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Đảm bảo các module Spring Shell cùng một dòng version tương thích. Nếu starter và core bị trộn phiên bản, auto-configuration có thể không khớp với tài liệu mà bạn đang tham khảo.

## Dùng condition report để tìm runner bị thiếu

Khi chưa rõ vì sao interactive runner không được tạo, chạy ứng dụng với Spring Boot debug condition report:

```bash
java -jar target/customer-cli.jar --debug
```

Đây là `--debug` của Spring Boot để in condition evaluation report. Nó giúp xác định auto-configuration nào được áp dụng và điều kiện nào khiến runner bị bỏ qua.

Trong Spring Shell 3.4.x, tìm các điều kiện liên quan đến:

| Bean/runner | Điều cần kiểm tra |
|---|---|
| `interactiveApplicationRunner` / `InteractiveShellRunner` | `spring.shell.interactive.enabled=true` có được nạp không? Có đủ class/dependency mà runner cần không? |
| `nonInteractiveApplicationRunner` / `NonInteractiveShellRunner` | Runner non-interactive có được bật và có nhận invocation hiện tại không? |
| `scriptApplicationRunner` / `ScriptShellRunner` | `spring.shell.script.enabled=true` đã bật khi dùng `@file` chưa? |
| `springShellApplicationRunner` hoặc `ShellApplicationRunner` | Có bean điều phối nào gọi `ShellRunner` đã được đăng ký không? |

Nếu condition report cho thấy interactive runner không được tạo vì property không khớp, sửa property source đang ghi đè. Nếu runner bị bỏ qua do thiếu class, kiểm tra dependency và starter. Nếu runner đã có nhưng không được gọi, kiểm tra bean điều phối và các startup runner tùy chỉnh.

Không bật `--debug` trong production lâu dài chỉ để giữ ứng dụng chạy. Sau khi chẩn đoán, bỏ cờ debug và giữ cấu hình runner rõ ràng trong profile phù hợp.

## Kiểm tra ApplicationRunner và cấu hình runner tùy chỉnh

Spring Shell kết nối runner với vòng đời Spring Boot thông qua `ApplicationRunner`. Nếu ứng dụng tự tạo runner để làm công việc lúc khởi động, hãy kiểm tra xem runner mặc định của Spring Shell còn tồn tại và được gọi hay không.

Trong Spring Shell 4.0.4, bean điều phối mặc định có tên `springShellApplicationRunner` và gọi `ShellRunner` đã cấu hình. Nếu muốn thay thế logic này, tài liệu yêu cầu cung cấp `ApplicationRunner` với đúng tên bean đó. Khi tự override, bean mới phải chủ động gọi runner mong muốn; nếu chỉ chạy công việc riêng rồi kết thúc, ứng dụng có thể không bao giờ mở REPL.

Ví dụ cấu hình điều phối tùy chỉnh có chủ đích:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.ShellRunner;

@Configuration
class ShellStartupConfiguration {

    @Bean("springShellApplicationRunner")
    ApplicationRunner springShellApplicationRunner(ShellRunner shellRunner) {
        return args -> shellRunner.run(args.getSourceArgs());
    }
}
```

Chỉ tạo bean cùng tên khi thật sự cần thay thế điều phối mặc định và API phiên bản đang dùng phù hợp với ví dụ. Nếu không cần custom startup orchestration, để Spring Shell đăng ký bean mặc định. Không tạo thêm `ApplicationRunner` có tên trùng chỉ để thực hiện một tác vụ khởi động không liên quan.

Trong Spring Shell 3.x, `ShellApplicationRunner` là điểm điều phối nhận `ApplicationArguments`; từ 3.3.x, `ShellRunner` bổ sung `run(String[] args)` và API cũ nhận `ApplicationArguments` được đánh dấu deprecated. Nếu custom code giữ API cũ, kiểm tra Javadoc đúng minor version trước khi nâng cấp.

## Kiểm tra dependency và lựa chọn terminal runner

Với Spring Shell 4.0.x:

| Runner | Điều kiện | Đặc điểm |
|---|---|---|
| `JLineShellRunner` | Có JLine trên classpath; starter thông thường cung cấp tích hợp này | History, completion và các tính năng terminal của JLine |
| `SystemShellRunner` | Không có JLine trên classpath | Dùng Java Console, không cần dependency JLine bổ sung |
| `NonInteractiveShellRunner` | `spring.shell.interactive.enabled=false` | Chạy command từ process arguments rồi kết thúc |

Nếu ứng dụng 4.x cần tính năng JLine mà chỉ có `SystemShellRunner`, bổ sung `spring-shell-jline` hoặc starter phù hợp với BOM đang dùng. Thiếu JLine có thể làm ứng dụng dùng runner dựa trên Console thay vì JLine; không mặc định kết luận đây là nguyên nhân process thoát. Condition report và bean thực tế mới cho biết runner nào được tạo.

Với Spring Shell 3.3.x/3.4.x, `InteractiveShellRunner` dựa vào cấu hình JLine và các bean input tương ứng. Nếu dùng core module tự lắp thay vì starter, xác nhận dependency JLine và interactive runner có mặt trong runtime classpath. Nếu dùng starter, tránh tự loại trừ module JLine mà không kiểm tra tác động.

## Kiểm tra cách khởi chạy từ IDE và terminal

Một ứng dụng có thể nhận cấu hình khác nhau giữa IDE và `java -jar`:

| Mục trong IDE | Cần kiểm tra |
|---|---|
| Program arguments | Có vô tình truyền command hoặc `--spring.shell.interactive.enabled=false` không? |
| VM options | Có `-Dspring.shell.interactive.enabled=false` hoặc cấu hình terminal khác không? |
| Active profiles | IDE có chạy profile `test`/`ci` thay cho `dev` không? |
| Working directory | File cấu hình bên ngoài JAR có nằm trong thư mục IDE đang dùng không? |
| Console | IDE có cấp console/PTY phù hợp với runner không? |
| Classpath | Runtime classpath có đủ Spring Shell starter và JLine module mong muốn không? |

Thử cùng một artifact từ terminal thật:

```bash
java -jar target/customer-cli.jar
```

Nếu terminal thật hoạt động nhưng IDE không hoạt động, so sánh toàn bộ arguments, environment, active profiles và runtime classpath. Một IDE console có thể nhận text nhưng không cung cấp đầy đủ khả năng terminal mà JLine mong đợi.

## Kiểm tra profile test để tránh test bị treo

Khi bật interactive runner, một test tích hợp dùng `@SpringBootTest` có thể khởi động Spring Shell cùng với `ApplicationContext`. Test có thể bị treo vì runner chờ input như đang mở REPL, hoặc thất bại do test process không có terminal.

Trong test profile, tắt interactive runner nếu mục tiêu test không phải kiểm thử vòng đời REPL:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Với test command, ưu tiên `@ShellTest` và `ShellTestClient` để gọi command có kiểm soát. Với kiểm thử end-to-end cho REPL, chạy process trong terminal giả/PTY và gửi input theo đúng kịch bản. Không tắt interactive ở cấu hình production chỉ để làm test pass; đặt property trong `application-test.yaml` hoặc test properties.

## Kiểm tra cấu hình context close

Spring Boot thường đóng `ApplicationContext` sau khi các `ApplicationRunner` đã hoàn tất nếu không còn thread non-daemon giữ process. Spring Shell có property `spring.shell.context.close=true` để yêu cầu đóng context sau khi shell hoàn tất execution logic; property này không bật mặc định.

Nếu cấu hình đang có:

```yaml
spring:
  shell:
    context:
      close: true
```

hãy xác định vì sao shell execution được xem là đã hoàn tất. Chỉ bỏ property này nếu ứng dụng không muốn cơ chế đóng context chủ động đó. Đặt `context.close=false` không thể thay thế một interactive runner bị thiếu; nếu không có runner giữ REPL, JVM vẫn có thể kết thúc sau khi các runner khác hoàn tất và không còn thread non-daemon.

Không thêm `@EnableScheduling`, web server hoặc thread nền giả chỉ để ngăn JVM thoát. Những thành phần đó làm thay đổi vòng đời ứng dụng nhưng không sửa nguyên nhân runner không mở shell.

## Cây chẩn đoán nhanh

```text
Ứng dụng có log Started ... rồi thoát?
             |
             v
       Có startup error?
          /       \
        Có         Không
        |            |
        v            v
   Đọc exception   Xác định Spring Shell version
   đầu tiên             |
                         v
                Đang dùng 3.3.x/3.4.x?
                    /       \
                  Có         Không
                  |            |
                  v            v
        Kiểm tra interactive   Với 4.x, kiểm tra property
        enabled=true chưa?     interactive.enabled có false?
                  |            |
                  v            v
        Runner có được tạo và được gọi?
                         |
                         v
            Có custom ApplicationRunner/
            ShellApplicationRunner override?
                         |
                         v
             Kiểm tra condition report,
             JLine/Console và terminal
```

## Ma trận triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Nâng 3.2.x lên 3.3.x thì app thoát ngay | Interactive runner không còn bật mặc định | Đặt `spring.shell.interactive.enabled=true` |
| Spring Shell 4 mở REPL trên máy này nhưng chạy command rồi thoát trên máy khác | Property/profile khác nhau, `interactive.enabled=false` | So sánh config và environment; chọn mode rõ ràng |
| App có `Started ...` rồi đóng context với exit code 0 | Không có runner nào giữ REPL hoặc runner đã hoàn tất | Kiểm tra runner selection và command arguments |
| Interactive runner không xuất hiện trong condition report | Property false, class/dependency thiếu hoặc auto-configuration bị loại | Kiểm tra active profile, runtime dependency và condition report |
| `help` không có command tự viết | Command bean không được scan/register hoặc bị giới hạn InteractionMode trong 3.x | Kiểm tra package scan, annotation và interaction mode |
| Custom `ApplicationRunner` chạy nhưng không có prompt | Bean điều phối Spring Shell bị thay thế hoặc không được gọi | Giữ `springShellApplicationRunner` mặc định hoặc tự gọi `ShellRunner` đúng cách |
| `@file` bị bỏ qua | Script runner chưa bật hoặc sai cú pháp đường dẫn | Bật `spring.shell.script.enabled=true`, truyền `@path` |
| JLine history/completion không có trong 4.x | App dùng `SystemShellRunner` vì JLine không có trong classpath | Thêm `spring-shell-jline`/starter phù hợp nếu cần JLine |
| Test tích hợp bị treo | Interactive runner chạy trong `@SpringBootTest` | Tắt interactive trong test profile hoặc dùng `@ShellTest` |
| App thoát sau khi script chạy xong | Script runner là batch invocation và đã hoàn tất | Đây là kết quả mong đợi; gọi riêng REPL nếu cần phiên tương tác |
| `context.close=true` và context bị đóng sau shell execution | Đã bật cơ chế close chủ động | Bỏ property nếu không muốn cơ chế này; kiểm tra runner trước |

## Checklist xác minh trước khi sửa code

1. Ghi lại Spring Shell version thực tế từ dependency tree.
2. Xác định mong muốn là REPL, một command hay script file.
3. Kiểm tra mặc định runner đúng với version: 3.3.x/3.4.x khác 3.2.x và 4.0.x.
4. Kiểm tra `spring.shell.interactive.enabled`, `noninteractive.enabled` và `script.enabled` ở mọi property source.
5. Xem active profile và command-line/VM arguments.
6. Bật Spring Boot `--debug` để đọc condition evaluation report.
7. Xác nhận runner bean và bean điều phối `springShellApplicationRunner`/`ShellApplicationRunner` tồn tại.
8. Kiểm tra custom `ApplicationRunner`, `CommandLineRunner` hoặc runner override có thay thế luồng khởi động shell không.
9. Kiểm tra JLine/Console provider và thử từ terminal thật.
10. Kiểm tra `spring.shell.context.close` nếu được cấu hình tường minh.
11. Tách test profile khỏi cấu hình REPL production.
12. Chạy lại cả ba kịch bản: mở REPL không arguments, chạy command một lần và chạy script.

Khi ứng dụng khởi động rồi thoát, hãy kiểm tra runner trước khi sửa vòng đời JVM. Với Spring Shell 3.3.x/3.4.x, bật `spring.shell.interactive.enabled=true` thường là thay đổi cần thiết để khôi phục REPL. Với Spring Shell 4.0.x, interactive mode đã là mặc định; hãy tìm property ghi đè, runner bean bị thay thế hoặc vấn đề terminal/provider. Sau khi chọn đúng mode, process sẽ kết thúc đúng lúc: giữ REPL mở khi cần tương tác và thoát sau command/script khi chạy tự động.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): runner mặc định từ 3.3.x và các property bật interactive/non-interactive/script.
- [Spring Shell 3.4.3 — Execution](https://docs.spring.io/spring-shell/reference/3.4/execution.html): runner defaults, `ShellApplicationRunner` và `InteractionMode`.
- [Spring Shell 3.4.x API — ShellRunnerAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.4.x/api/org/springframework/shell/boot/ShellRunnerAutoConfiguration.NonePrimaryCommandConfiguration.html): điều kiện tạo `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner`.
- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html): interactive mode mặc định, chuyển sang non-interactive và lựa chọn SystemShell/JLine runner.
- [Spring Shell 4.0.4 API — ShellRunnerAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/ShellRunnerAutoConfiguration.html): `springShellApplicationRunner` và các runner bean.
- [Spring Shell — Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html): vòng đời ApplicationRunner, tự đóng context và property `spring.shell.context.close`.
- [Spring Shell 3.3 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): bật interactive runner khi tạo ứng dụng 3.3.x.
- [Spring Shell 4.0.4 — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi mode, runner và `InteractionMode` trong dòng 4.x.
