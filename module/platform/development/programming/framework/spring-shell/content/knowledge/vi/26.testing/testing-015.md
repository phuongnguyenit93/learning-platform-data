# Đóng phiên, dọn context và tránh kiểm thử bị treo chờ đầu vào

Ứng dụng Spring Shell có thể chạy như một lệnh ngắn hạn hoặc một REPL tương tác kéo dài. Trong kiểm thử, hai kiểu chạy này có vòng đời khác nhau: command non-interactive thường kết thúc sau khi xử lý input, còn interactive session tiếp tục chờ lệnh tiếp theo. Nếu test khởi động REPL nhưng không gửi lệnh thoát, không cung cấp dữ liệu cho prompt hoặc không đóng tài nguyên terminal, tiến trình kiểm thử có thể bị treo và giữ luôn Spring context.

Để kiểm thử ổn định, cần quản lý riêng vòng đời của shell session, `ShellTestClient`, `ShellContext`, Spring `ApplicationContext` và các tài nguyên do ứng dụng tạo. Bài viết sử dụng Spring Shell 3.3 làm mốc API, tập trung vào cách đóng phiên, dọn context và cấp input có kiểm soát để test luôn kết thúc trong thời gian xác định.

## 1. Phân biệt các loại session và context

Trong một ứng dụng Spring Shell có nhiều đối tượng mang tên session hoặc context nhưng có vòng đời khác nhau:

| Thành phần | Vai trò | Cách kết thúc/dọn dẹp |
|---|---|---|
| Interactive shell session | Vòng lặp nhận lệnh liên tục | Gửi lệnh `quit`/`exit` hoặc kết thúc terminal session |
| `ShellTestClient` | Client kiểm thử giao tiếp với terminal giả lập | Gọi `close()` khi client do test tự tạo; nếu được Spring quản lý, đóng context để Spring hủy bean |
| `BaseShellSession` | Phiên chạy trong `ShellTestClient` | Theo dõi bằng `isComplete()`; API 3.3 không có `close()` riêng trên session |
| `ShellContext` | Thông tin chung của shell như interaction mode và PTY | Không phải Spring container và không có `close()` |
| Spring `ApplicationContext` | Container quản lý bean, listener, executor và resource | Spring TestContext, Spring Boot hoặc code sở hữu context gọi `close()` |
| Resource do ứng dụng tạo | File, socket, executor, client HTTP hoặc subscription | `try-with-resources`, `@PreDestroy`, `DisposableBean` hoặc lifecycle callback phù hợp |

Không nên dùng từ “đóng context” cho tất cả các đối tượng. Ví dụ, đóng `ShellTestClient` giải phóng tài nguyên terminal của test client; đóng Spring `ApplicationContext` hủy các bean singleton và tài nguyên do chúng quản lý. `ShellContext` chỉ cung cấp thông tin về phiên shell, không phải một container có thể đóng.

## 2. Vì sao test Spring Shell có thể bị treo?

Các nguyên nhân phổ biến:

- Test khởi động interactive runner nhưng không gửi `quit` hoặc `exit`.
- Command gọi prompt nhập liệu nhưng test không gửi câu trả lời.
- Test dùng `Scanner(System.in)` hoặc `System.in.read()` trực tiếp, trong khi test runner không cấp input.
- Test đợi một prompt hoặc output không bao giờ xuất hiện.
- Một executor, scheduler, listener hoặc thread không daemon giữ JVM sống sau khi command đã kết thúc.
- `ShellTestClient` hoặc terminal session được tạo thủ công nhưng không được đóng.
- Singleton bean giữ trạng thái của test trước, khiến test sau phụ thuộc thứ tự chạy.

Một dấu hiệu thường gặp là `mvn test` hoặc `gradle test` đã in xong kết quả nhưng tiến trình Java vẫn chạy. Khi đó, hãy kiểm tra shell runner, thread nền và tài nguyên terminal còn mở thay vì tăng thời gian chờ của build một cách tùy tiện.

## 3. Chọn đúng chế độ kiểm thử

Spring Shell 3.3 có các runner khác nhau cho interactive, non-interactive và script. Từ phiên bản 3.3, chỉ `NonInteractiveShellRunner` được bật mặc định; interactive và script runner có thể được bật bằng cấu hình. Nếu ứng dụng hoặc profile test bật interactive runner, khởi động Spring context có thể bắt đầu REPL và chờ lệnh.

Chọn cách kiểm thử theo mục tiêu:

| Mục tiêu | Cách kiểm thử |
|---|---|
| Kiểm tra command, parser và output | `@ShellTest` cùng `ShellTestClient` non-interactive |
| Kiểm tra menu, prompt và nhập liệu | Interactive session, cấp đầy đủ chuỗi phím và gửi lệnh thoát |
| Kiểm tra tích hợp Spring Boot đầy đủ | `@SpringBootTest`, tắt runner tương tác trong test và cấp command tường minh nếu cần |
| Kiểm tra service nghiệp vụ | Unit test service, không khởi động shell hoặc terminal |
| Kiểm tra script | Cấp file script test hữu hạn và xác nhận runner kết thúc |

Không cần khởi động REPL để kiểm tra một service xử lý dữ liệu. Giữ phần lớn test ở mức service/command non-interactive; chỉ dùng interactive test cho hành vi phụ thuộc prompt, bàn phím hoặc giao diện terminal.

## 4. Dùng `@ShellTest` để kiểm thử command không cần khởi động REPL

Spring Shell cung cấp module `spring-shell-test` và `spring-shell-test-autoconfigure`. Annotation `@ShellTest` tạo test context tập trung vào thành phần shell và cung cấp `ShellTestClient`.

Ví dụ kiểm tra command `project list`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

@ShellTest
@ContextConfiguration(classes = ProjectShellApplication.class)
class ProjectCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void listsProjects() {
        ShellTestClient.NonInteractiveShellSession session =
                client.nonInterative("project", "list").run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE PROJECTS"));
    }
}
```

Trong Spring Shell 3.3, tên method non-interactive là `nonInterative(...)` (chính tả API có một chữ `a` thừa). Ở các phiên bản sau, hãy kiểm tra API đúng version; từ Spring Shell 3.4.2, method mới `nonInteractive(...)` được bổ sung và method cũ được đánh dấu deprecated.

`@ShellTest` không yêu cầu test tự mở một REPL tương tác. `ShellTestClient` thực thi command với input đã biết và cung cấp `ShellScreen` để kiểm tra kết quả. Đây thường là lựa chọn gọn nhất cho command thông thường.

## 5. Đóng interactive session trong test

Interactive session tiếp tục chạy sau khi một command hoàn tất. Sau khi kiểm tra command, gửi lệnh `quit` hoặc `exit`, rồi đợi session báo đã hoàn tất.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

@ShellTest
@ContextConfiguration(classes = ProjectShellApplication.class)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesCommandAndExits() {
        ShellTestClient.InteractiveShellSession session =
                client.interactive().run();

        session.write(session.writeSequence()
                .text("project list")
                .carriageReturn()
                .build());

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE PROJECTS"));

        session.write(session.writeSequence()
                .text("quit")
                .carriageReturn()
                .build());

        await().atMost(2, SECONDS).until(session::isComplete);
    }
}
```

`BaseShellSession` trong API Spring Shell 3.3 có `run()`, `write(...)`, `writeSequence()`, `screen()` và `isComplete()`. Nó không cung cấp `close()` riêng. Vì vậy, test cần kết thúc REPL bằng lệnh thoát và quản lý `ShellTestClient`/test context sở hữu terminal.

Không chỉ gửi `quit` rồi giả định session đã dừng. Dùng `isComplete()` với timeout để xác nhận. Nếu shell dùng lệnh thoát tùy chỉnh, gửi đúng lệnh mà ứng dụng đăng ký.

## 6. Cấp input tường minh cho prompt

Nếu command mở prompt xác nhận hoặc nhập giá trị, test phải gửi câu trả lời sau khi prompt xuất hiện. Đừng để command chờ input mà test chỉ ngồi đợi kết quả cuối.

Ví dụ command hỏi xác nhận trước khi xóa workspace:

```java
@Test
void confirmsWorkspaceDeletion() {
    var session = client.interactive().run();

    session.write(session.writeSequence()
            .text("workspace delete demo")
            .carriageReturn()
            .build());

    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("Delete workspace demo?"));

    session.write(session.writeSequence()
            .text("y")
            .carriageReturn()
            .build());

    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                    .containsText("Workspace deleted"));

    session.write(session.writeSequence()
            .text("quit")
            .carriageReturn()
            .build());
    await().atMost(2, SECONDS).until(session::isComplete);
}
```

Trình tự nên là:

1. Gửi command.
2. Chờ prompt xuất hiện bằng một assertion có timeout.
3. Gửi input đúng với prompt.
4. Chờ output hoặc trạng thái nghiệp vụ mong đợi.
5. Gửi lệnh thoát và chờ session hoàn tất.

Nếu prompt có nhiều bước, cấp từng câu trả lời theo thứ tự và xác nhận prompt tương ứng trước khi gửi bước tiếp theo. Điều này giúp test phát hiện prompt bị thay đổi hoặc command đi vào nhánh khác.

## 7. Không đọc `System.in` trực tiếp trong command

`Scanner(System.in)`, `BufferedReader(new InputStreamReader(System.in))` hoặc `System.console().readPassword()` có thể đọc từ stdin thật của process thay vì terminal giả lập mà `ShellTestClient` quản lý. Trong CI, stdin thường không có người nhập nên test có thể treo.

Ưu tiên dùng component input của Spring Shell như `StringInput`, `ConfirmationInput` hoặc `ComponentFlow`, hoặc tách việc thu thập input khỏi nghiệp vụ bằng một abstraction có thể thay thế trong test.

Ví dụ tách giao diện nhập liệu:

```java
public interface ConfirmationPrompt {
    boolean confirm(String question);
}
```

Adapter tương tác dùng Spring Shell component:

```java
import org.jline.terminal.Terminal;
import org.springframework.core.io.ResourceLoader;
import org.springframework.shell.component.ConfirmationInput;
import org.springframework.shell.style.TemplateExecutor;
import org.springframework.stereotype.Component;

@Component
public class ShellConfirmationPrompt implements ConfirmationPrompt {

    private final Terminal terminal;
    private final ResourceLoader resourceLoader;
    private final TemplateExecutor templateExecutor;

    public ShellConfirmationPrompt(
            Terminal terminal,
            ResourceLoader resourceLoader,
            TemplateExecutor templateExecutor) {
        this.terminal = terminal;
        this.resourceLoader = resourceLoader;
        this.templateExecutor = templateExecutor;
    }

    @Override
    public boolean confirm(String question) {
        ConfirmationInput input = new ConfirmationInput(terminal, question, false);
        input.setResourceLoader(resourceLoader);
        input.setTemplateExecutor(templateExecutor);
        Boolean result = input.run(ConfirmationInput.ConfirmationInputContext.empty())
                .getResultValue();
        return Boolean.TRUE.equals(result);
    }
}
```

Trong unit test service, thay `ConfirmationPrompt` bằng stub/mock trả về `true` hoặc `false`. Khi kiểm thử tích hợp prompt, dùng terminal test và gửi phím qua `InteractiveShellSession`. Không cần đọc stdin của máy chạy test.

Nếu dùng một API nhập liệu riêng, bảo đảm nó nhận input stream/reader được inject thay vì tự lấy `System.in` toàn cục. Cách này giúp test cấp dữ liệu có thể dự đoán và không phụ thuộc terminal thật.

## 8. Kiểm tra PTY trước khi chạy luồng cần tương tác

Spring Shell 3.3 có `ShellContext` để truy cập thông tin chung của shell. Hai giá trị hữu ích:

- `getInteractionMode()` cho biết shell đang ở chế độ interactive hay non-interactive.
- `hasPty()` cho biết terminal có pseudo-terminal (PTY) phù hợp hay không. Khi output được pipe vào file hoặc chạy trong CI không có người dùng tương tác, PTY có thể không tồn tại.

Với command chỉ có ý nghĩa khi người dùng có terminal, hãy kiểm tra chế độ tương tác/PTY trước khi mở prompt. Nếu không có PTY, trả thông báo rõ ràng và hướng dẫn dùng option hoặc file input. Không tự động fallback sang đọc plain text từ stdin nếu điều đó có thể làm lộ secret hoặc khiến script treo.

`ShellContext` không phải Spring `ApplicationContext`. Trong API 3.3, nó không có `close()` và không phải nơi để lưu tùy tiện dữ liệu riêng của từng test. Hãy xem nó là thông tin trạng thái chung của shell, còn dữ liệu tạm của một command nên được giữ trong phạm vi invocation hoặc object nghiệp vụ riêng.

## 9. Tắt interactive runner trong SpringBootTest

Nếu ứng dụng bật interactive runner trong `application.yml`, `@SpringBootTest` có thể khởi chạy REPL khi context được tạo. Test không cấp terminal input thì runner tiếp tục chờ.

Trong test context không cần REPL, tắt các runner không sử dụng:

```java
@SpringBootTest(properties = {
        "spring.shell.interactive.enabled=false",
        "spring.shell.noninteractive.enabled=false",
        "spring.shell.script.enabled=false"
})
class ApplicationContextTests {
    // Kiểm tra bean, cấu hình hoặc service.
}
```

Với Spring Shell 3.3, `NonInteractiveShellRunner` được bật mặc định; `InteractiveShellRunner` và `ScriptShellRunner` có thể được bật bằng property tương ứng. Đặt rõ các property trong test giúp ngăn cấu hình profile hoặc file bên ngoài vô tình bật runner. Nếu test chủ đích kiểm tra chạy command non-interactive qua runner của ứng dụng, chỉ bật runner cần thiết và truyền command argument tường minh.

Nếu chỉ cần kiểm tra command, ưu tiên `@ShellTest` và `ShellTestClient`. Nếu cần kiểm tra toàn bộ `SpringApplication` startup, dùng `@SpringBootTest` nhưng kiểm soát runner và argument như ví dụ.

## 10. Dọn ShellTestClient và terminal

`ShellTestClient` của Spring Shell 3.3 triển khai `Closeable`/`AutoCloseable` và có `close()`. Phương thức này giải phóng tài nguyên client/terminal được tạo cho test.

Có hai trường hợp:

**Client do test tự tạo:** đóng bằng try-with-resources hoặc `finally`.

```java
try (ShellTestClient client = createShellTestClient()) {
    var session = client.nonInterative("help").run();
    assertThat(session.screen()).containsText("AVAILABLE COMMANDS");
}
```

`createShellTestClient()` đại diện cho builder setup phù hợp với terminal, shell và line reader của test. Khi client do test tạo, test sở hữu vòng đời và phải gọi `close()` dù assertion thành công hay thất bại.

**Client được inject từ Spring:** để Spring quản lý vòng đời bean. Không gọi `client.close()` trong mỗi `@Test` nếu context sẽ được tái sử dụng cho test method kế tiếp; client đã đóng có thể khiến các test sau thất bại. Khi cần đóng client và toàn bộ resource của test context, dùng `@DirtiesContext` ở phạm vi phù hợp.

Không đóng `Terminal`, `LineReader` hoặc bean singleton do Spring quản lý sau mỗi command nếu chúng còn được shell sử dụng. Chỉ đóng tài nguyên mà code hiện tại sở hữu.

## 11. Dùng `@DirtiesContext` đúng phạm vi

Spring TestContext cache `ApplicationContext` để giảm thời gian chạy test. `@DirtiesContext` đánh dấu context đã thay đổi hoặc không còn an toàn để tái sử dụng; framework loại context khỏi cache và đóng nó. Khi test sau cần cùng cấu hình, một context mới sẽ được tạo.

Ví dụ dọn context sau mỗi interactive test method:

```java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
@ContextConfiguration(classes = ProjectShellApplication.class)
class InteractiveSessionTests {
    // Mỗi test có một shell context/client mới.
}
```

`AFTER_EACH_TEST_METHOD` hữu ích khi test để lại interactive session, thay đổi singleton state hoặc resource khó reset. Đổi lại, Spring phải tạo lại context cho từng method nên test suite chậm hơn.

Nếu các test không làm bẩn context và client/session đã được kết thúc đúng cách, có thể để Spring tái sử dụng context. Nếu chỉ cần đóng context sau toàn bộ class, dùng `@DirtiesContext` với `AFTER_CLASS` (đây cũng là class mode mặc định). Đừng thêm `@DirtiesContext` vào mọi test theo thói quen; chỉ dùng khi có trạng thái hoặc tài nguyên cần reset.

## 12. Dọn tài nguyên bean khi ApplicationContext đóng

Các bean tạo executor, scheduler, socket hoặc client bên ngoài phải có lifecycle cleanup. Dùng `@PreDestroy`, `DisposableBean` hoặc `SmartLifecycle` tùy cách quản lý tài nguyên.

Ví dụ đóng executor:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ImportWorker {

    private final ExecutorService executor =
            java.util.concurrent.Executors.newFixedThreadPool(2);

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    void stop() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
        catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Khi Spring đóng context, callback `@PreDestroy` được gọi để dừng executor. Nếu thread không kết thúc, nó có thể giữ JVM sống sau khi command hoàn tất. Không tạo thread nền bằng `new Thread(...)` rồi quên giữ handle và dừng nó.

Với tài nguyên theo từng command, ưu tiên `try-with-resources` ngay trong method:

```java
try (var reader = Files.newBufferedReader(inputPath)) {
    return importService.importFrom(reader);
}
```

Không dựa vào việc Spring đóng context để dọn một file stream hoặc response body thuộc về một command đã kết thúc. Tài nguyên có phạm vi ngắn nên được đóng tại đúng phạm vi ngắn đó.

## 13. `spring.shell.context.close` cho command chạy một lần

Trong ứng dụng Spring Shell chạy một command non-interactive rồi kết thúc, sau khi các `ApplicationRunner` hoàn tất và không còn non-daemon thread giữ JVM, JVM có thể thoát; shutdown hook của Spring Boot khi đó đóng `ApplicationContext`. Nếu scheduler hoặc thread nền làm ứng dụng tiếp tục chạy, Spring Shell có property:

```yaml
spring:
  shell:
    context:
      close: true
```

Property `spring.shell.context.close` đăng ký listener cho `ApplicationReadyEvent` và yêu cầu đóng context sau khi shell hoàn tất execution logic. Mặc định property này không bật.

Chỉ bật khi mô hình ứng dụng là chạy lệnh một lần rồi kết thúc. Không bật cho REPL tương tác cần giữ context sống để nhận nhiều command. Nếu ứng dụng cần worker chạy nền sau command, hãy xác định rõ worker đó thuộc lifecycle của ứng dụng hay phải dừng sau command; đừng đóng context trong khi tài nguyên vẫn được dùng.

Trong test, để Spring TestContext quản lý context thay vì tự gọi `applicationContext.close()` trên context được framework cache. Tự đóng context dùng chung có thể làm test method kế tiếp nhận các bean đã bị hủy.

## 14. Giới hạn thời gian chờ và không dùng Thread.sleep

Test tương tác có tính bất đồng bộ: gửi phím vào terminal không đảm bảo output cuối đã xuất hiện ngay ở câu lệnh tiếp theo. Dùng Awaitility hoặc cơ chế chờ có timeout để chờ một điều kiện cụ thể.

```java
await().atMost(2, SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("Import completed"));
```

Tránh:

```java
Thread.sleep(5000);
```

`Thread.sleep` luôn chờ đủ thời gian dù output đã xuất hiện, đồng thời vẫn có thể không đủ nếu máy CI chậm. Chờ điều kiện với timeout giúp test nhanh khi thành công và thất bại rõ khi command không tiến triển.

Cũng nên đặt timeout ở cấp test:

```java
@Timeout(value = 10, unit = TimeUnit.SECONDS)
@Test
void interactiveCommandTerminates() {
    // Start session, send all required input, send quit and assert completion.
}
```

Timeout cấp test là hàng rào cuối cùng, không thay thế việc cấp input và đóng session đúng cách.

## 15. Kiểm thử context isolation và trạng thái giữa các command

`ShellContext` tồn tại để chia sẻ một số thông tin chung giữa các command trong cùng shell. Trong khi đó, Spring singleton bean cũng tồn tại qua nhiều lần gọi command và qua nhiều test method nếu context được cache.

Để tránh test phụ thuộc thứ tự:

- Không lưu dữ liệu test vào field mutable của command singleton nếu không cần thiết.
- Nếu shell có workspace/session state, cung cấp thao tác reset rõ ràng hoặc tạo context mới giữa các test.
- Không để một test đổi interaction mode hoặc cấu hình terminal mà không khôi phục.
- Dùng `@DirtiesContext` khi không thể reset trạng thái singleton an toàn.
- Kiểm tra test chạy riêng lẻ và chạy cùng toàn bộ suite.
- Không dùng static mutable state để truyền dữ liệu giữa các command hoặc test.

Ví dụ kiểm tra không rò trạng thái giữa các lần gọi:

```java
@Test
void newCommandDoesNotReusePreviousImportSelection() {
    importSession.select("customers.csv");
    importSession.clear();

    assertThat(importSession.selectedFile()).isNull();
}
```

Nếu trạng thái là chủ ý của một phiên shell, test phải kiểm tra cả việc giữ trạng thái trong cùng phiên và việc không rò sang context mới.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `mvn test` treo sau khi context khởi động | Interactive runner đang chờ command | Tắt `spring.shell.interactive.enabled` trong test context |
| Test interactive không bao giờ kết thúc | Không gửi `quit`/`exit` | Gửi lệnh thoát và đợi `session.isComplete()` |
| Test prompt bị treo | Không cấp input cho prompt hoặc đọc `System.in` | Gửi input qua terminal test hoặc inject input abstraction |
| Test chờ output mãi | Output không xuất hiện hoặc điều kiện chờ sai | Dùng Awaitility với timeout ngắn và assertion cụ thể |
| JVM vẫn chạy sau khi test hoàn tất | Executor/scheduler/thread không được dừng | Đóng resource bằng `@PreDestroy`/`SmartLifecycle` |
| Test sau lỗi vì terminal đã đóng | Đóng injected `ShellTestClient` quá sớm | Để Spring quản lý client và đóng context đúng phạm vi |
| Context mới vẫn giữ dữ liệu cũ | State nằm trong static field hoặc external store | Reset external state hoặc cô lập resource; `@DirtiesContext` không xóa dữ liệu ngoài context |
| Dùng `@DirtiesContext` làm suite chậm | Đóng và tạo lại context sau mỗi test không cần thiết | Chỉ dùng khi test thực sự làm bẩn context |
| Script test treo | Script chờ prompt hoặc command không kết thúc | Dùng non-interactive input và không mở prompt trong script |
| Test bị phụ thuộc thứ tự | Singleton mutable state không được reset | Tạo fixture riêng, reset state hoặc dùng context mới |

## 17. Checklist trước khi hoàn tất test Spring Shell

- [ ] Đã chọn `@ShellTest`, `@SpringBootTest` hoặc unit test phù hợp với mục tiêu.
- [ ] Test context không vô tình bật interactive runner.
- [ ] Mọi interactive session đều được cấp đủ input.
- [ ] Mọi interactive session đều gửi `quit`/`exit` hoặc có cách kết thúc rõ ràng.
- [ ] Đã đợi `isComplete()` bằng timeout khi cần xác nhận session kết thúc.
- [ ] `ShellTestClient` tự tạo được đóng bằng `close()`/try-with-resources.
- [ ] Injected `ShellTestClient` được quản lý bởi Spring context, không bị đóng trước khi test khác dùng.
- [ ] Không đọc `System.in` trực tiếp trong command cần kiểm thử.
- [ ] Prompt có đường đi non-interactive rõ ràng hoặc từ chối chạy khi không có PTY.
- [ ] Dùng Awaitility/JUnit timeout thay cho `Thread.sleep`.
- [ ] Executor, scheduler và external client có lifecycle cleanup.
- [ ] Dùng `@DirtiesContext` đúng phạm vi, không lạm dụng.
- [ ] Không tự đóng Spring context do TestContext framework quản lý.
- [ ] Đã kiểm tra test riêng lẻ và toàn bộ suite.

## Tài liệu tham khảo

1. [Spring Shell 3.3 – Testing Basics](https://docs.spring.io/spring-shell/reference/3.3/testing/basics.html) – test interactive/non-interactive bằng `ShellTestClient` và `@ShellTest`.
2. [Spring Shell 3.3 – `ShellTestClient` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) – client terminal và phương thức `close()`.
3. [Spring Shell 3.3 – `BaseShellSession` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.BaseShellSession.html) – `run`, `write`, `screen` và `isComplete`.
4. [Spring Shell 3.3 – `ShellContext` API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/context/ShellContext.html) – interaction mode và kiểm tra PTY.
5. [Spring Shell 3.3 – Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html) – các shell runner và property bật/tắt.
6. [Spring Shell 3.3 – Context Close](https://docs.spring.io/spring-shell/reference/3.3/customization/contextclose.html) – `spring.shell.context.close` và lifecycle khi command hoàn tất.
7. [Spring Framework – `@DirtiesContext`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html) – đánh dấu context cần đóng và loại khỏi cache test.

Một test shell ổn định phải có điểm bắt đầu và kết thúc rõ ràng: chọn đúng runner, cấp input tường minh, xác nhận output bằng điều kiện có timeout, kết thúc interactive session và để đúng thành phần sở hữu đóng client/context. Khi tách bạch `ShellContext`, `ShellTestClient` và Spring `ApplicationContext`, test sẽ ít bị treo và không để tài nguyên của phiên trước ảnh hưởng phiên sau.
