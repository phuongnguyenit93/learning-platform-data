# `@ShellTest` cùng phạm vi context trong từng thế hệ

`@ShellTest` giúp kiểm thử command Spring Shell mà không cần khởi chạy một terminal thật. Tuy nhiên, cách annotation này tạo test context đã thay đổi đáng kể giữa Spring Shell 3.3 và 4.0. Nếu chỉ giữ nguyên annotation và copy code test khi nâng cấp, bạn có thể vô tình chạy với phạm vi bean khác, bỏ mất cấu hình ứng dụng hoặc tạo thêm nhiều `ApplicationContext` khiến bộ test chậm hơn.

Điều cần xác định trước khi viết test là phạm vi context: bạn muốn một shell test slice chỉ chứa command và dependency liên quan, hay muốn khởi động gần như toàn bộ ứng dụng? Sau đó mới chọn annotation, cấu hình và cách tương tác với `ShellTestClient` theo đúng thế hệ Spring Shell.

Bài này so sánh Spring Shell 3.3.x với 4.0.4, tập trung vào `@ShellTest`, `ApplicationContext`, context cache và vòng đời test.

## 1. Phạm vi context là gì?

Một Spring test context là `ApplicationContext` được tạo để chạy test. Nó chứa bean, configuration, auto-configuration, environment, profile và các thành phần hạ tầng cần thiết.

Với Spring Shell, context có thể chứa:

- Command bean và command registry.
- Service, repository và các dependency của command.
- Parser, result handler, conversion service và test client.
- Các bean cấu hình cho terminal, input và output.
- Những auto-configuration khác của ứng dụng nếu test nạp chúng.

Hai test có cùng `@ShellTest` chưa chắc dùng cùng phạm vi context. Các class cấu hình, profile, property source, mock bean và context customizer cũng ảnh hưởng tới context được tạo.

Hãy phân biệt ba mức test:

| Mức test | Context | Mục tiêu |
|---|---|---|
| Unit test command/service | Không cần Spring context hoặc chỉ dùng mock | Kiểm tra logic thuần |
| Shell-focused test | Chỉ nạp shell infrastructure, command và dependency cần thiết | Kiểm tra parser, binding, command execution và output |
| Full application integration test | Nạp application context gần với ứng dụng thật | Kiểm tra wiring, auto-configuration, persistence và tích hợp |

`@ShellTest` không thay thế unit test cho service. Nó hữu ích khi cần xác nhận command hoạt động đúng trong môi trường Spring Shell.

## 2. Khác biệt chính giữa Spring Shell 3.3 và 4.0

Tên annotation và package của `@ShellTest` vẫn là `org.springframework.shell.test.autoconfigure.ShellTest`, nhưng metadata và cách dựng context đã thay đổi.

| Khía cạnh | Spring Shell 3.3.x | Spring Shell 4.0.4 |
|---|---|---|
| Vai trò của `@ShellTest` | Shell test slice dựa trên Spring Boot test bootstrapper | Bật Spring Test extension và import cấu hình `ShellTestClient` |
| Tạo test context | `ShellTestContextBootstrapper` kế thừa `SpringBootTestContextBootstrapper` | Context do `@ContextConfiguration`, `@SpringBootTest` hoặc cấu hình Spring Test khác quyết định |
| Lọc bean | Có `ShellTypeExcludeFilter`, include/exclude filters và default filters | `@ShellTest` không còn tự khai báo shell type-exclude filter |
| Shell auto-configuration | Có `@AutoConfigureShell` và `@AutoConfigureShellTestClient` | Import `ShellTestClientAutoConfiguration`; cấu hình ứng dụng phải cung cấp shell infrastructure |
| Cấu hình terminal size | Có `terminalWidth`, `terminalHeight` và test properties | Các API `SpringShellTestProperties` và thuộc tính annotation này đã bị loại bỏ |
| Test client | Interface có interactive/non-interactive session | Class có `sendCommand(...)` |

Đây là thay đổi về phạm vi test, không chỉ là đổi tên method. Khi nâng cấp, hãy chọn lại cấu hình context trước khi chuyển các test.

## 3. Chuẩn bị test dependencies

Test support được chia thành module lõi và module auto-configuration. Dùng cùng thế hệ/version với Spring Shell của ứng dụng và quản lý version bằng BOM hoặc dependency management của dự án.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.shell:spring-shell-test")
    testImplementation("org.springframework.shell:spring-shell-test-autoconfigure")
    testImplementation("org.awaitility:awaitility") // dùng cho ví dụ interactive 3.3
}
```

`spring-shell-test` chứa các API như `ShellTestClient`, `ShellScreen` và `ShellAssertions`. `spring-shell-test-autoconfigure` cung cấp `@ShellTest` cùng cấu hình kiểm thử liên quan.

Không trộn test module 3.3 với runtime 4.0 hoặc ngược lại. Nếu dùng Spring Boot dependency management, hãy kiểm tra compatibility matrix của phiên bản Spring Shell và Spring Boot đang chọn.

## 4. `@ShellTest` trong Spring Shell 3.3 là một test slice

Trong Spring Shell 3.3, `@ShellTest` có metadata tương tự một Spring Boot test slice. Annotation dùng `ShellTestContextBootstrapper`, tắt auto-configuration mặc định, áp dụng `ShellTypeExcludeFilter`, rồi import shell auto-configuration và test client auto-configuration.

Điều này giúp context chỉ tập trung vào thành phần shell và những bean được phép đưa vào. Annotation có các thuộc tính như:

- `includeFilters` và `excludeFilters` để điều chỉnh bean được component scan.
- `useDefaultFilters` để điều chỉnh default component scan filters.
- `excludeAutoConfiguration` để loại một auto-configuration.
- `properties` để thêm property vào Spring `Environment`.
- `terminalWidth` và `terminalHeight` để đặt kích thước terminal giả lập.

Ví dụ một command dùng API annotation 3.3:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class GreetingCommands {

    @ShellMethod(key = "greet", value = "Hiển thị lời chào")
    String greet() {
        return "Xin chào từ Spring Shell 3.3";
    }
}
```

Để Spring Boot test bootstrapper tìm được application configuration, đặt một lớp `@SpringBootApplication` trong package phù hợp với command và test:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
class GreetingShellApplication {
}
```

Test slice:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD;

@ShellTest
@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)
class GreetingCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesGreetingCommand() {
        var session = client.nonInterative("greet").run();

        ShellAssertions.assertThat(session.screen())
                .containsText("Xin chào từ Spring Shell 3.3");
    }
}
```

Trong ví dụ 3.3, method API được viết là `nonInterative(...)` theo đúng tên trong API của thế hệ này. Đây là tên có cách viết thiếu chữ `c`; không tự sửa thành `nonInteractive` khi dùng API 3.3.

`@ShellTest` 3.3 có thể tìm Spring Boot configuration theo quy tắc của Spring Boot test bootstrapper. Command bean cần nằm trong phạm vi component scan hoặc được đưa vào qua include filter, import hay test configuration.

Nếu cần full application context thay vì shell slice, dùng `@SpringBootTest` và bật test client riêng:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.test.autoconfigure.AutoConfigureShellTestClient;

@SpringBootTest(classes = GreetingShellApplication.class)
@AutoConfigureShellTestClient
class FullApplicationShellTests33 {
    // ShellTestClient được inject từ test client auto-configuration.
}
```

## 5. Dùng ShellTestClient 3.3 cho phiên tương tác

Trong 3.3, `ShellTestClient` là interface. Nó cung cấp hai kiểu phiên:

- `interactive()` tạo `InteractiveShellSession` để gửi chuỗi phím vào REPL.
- `nonInterative(String... args)` tạo `NonInteractiveShellSession` để chạy một command.

Ví dụ gửi lệnh `help` vào phiên interactive:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.awaitility.Awaitility.await;
import static org.springframework.test.annotation.DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD;

@ShellTest
@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void typesHelpIntoInteractiveShell() {
        InteractiveShellSession session = client.interactive().run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));

        session.write(session.writeSequence()
                .text("help")
                .carriageReturn()
                .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE COMMANDS"));
    }
}
```

Terminal session có tính bất đồng bộ. Sau khi gửi chuỗi phím, không giả định output đã hoàn tất ngay ở câu lệnh kế tiếp. Dùng Awaitility hoặc cơ chế chờ có timeout để đợi nội dung xuất hiện.

## 6. Dùng `@ShellTest` trong Spring Shell 4.0.4

Trong 4.0.4, metadata của `@ShellTest` đã đơn giản hơn. Annotation được gắn với `SpringExtension` và import `ShellTestClientAutoConfiguration`. Nó không còn tự áp dụng `ShellTestContextBootstrapper`, `ShellTypeExcludeFilter`, `@AutoConfigureShell` hoặc `@AutoConfigureShellTestClient` như 3.3.

Vì vậy, test phải khai báo context mà nó cần. Với cấu hình ứng dụng Spring Boot, có thể dùng `@ContextConfiguration`:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.CommandContext;

@SpringBootApplication
class DemoShellApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoShellApplication.class, args);
    }

    @Command(name = "greet", description = "Hiển thị lời chào")
    String greet() {
        return "Xin chào từ Spring Shell 4";
    }

    @Command(name = "ask", description = "Đọc thêm một dòng input")
    String ask(CommandContext context) throws Exception {
        return "You said: " + context.inputReader().readInput();
    }
}
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest
@ContextConfiguration(classes = DemoShellApplication.class)
class GreetingCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesGreetingCommand() throws Exception {
        ShellScreen screen = client.sendCommand("greet");

        ShellAssertions.assertThat(screen)
                .containsText("Xin chào từ Spring Shell 4");
    }
}
```

Trong ví dụ, `@ContextConfiguration` xác định configuration class. `@SpringBootApplication` cung cấp component scan và Boot auto-configuration; `@ShellTest` bổ sung test client để gửi command và đọc screen.

Không dùng ví dụ `@ShellTest` 3.3 rồi bỏ `@ContextConfiguration` trong 4.0.4. `@ShellTest` 4.0.4 không còn bootstrap một shell test slice tự tìm application class như annotation 3.3.

## 7. Chọn `@ContextConfiguration` hay `@SpringBootTest` trong 4.0

Trong 4.0, chính annotation Spring Test quyết định context scope. Hai lựa chọn phổ biến:

| Annotation | Khi nào dùng | Phạm vi |
|---|---|---|
| `@ContextConfiguration(classes = ...)` | Muốn chỉ rõ cấu hình test | Những configuration class được khai báo và các bean mà chúng import/scan |
| `@SpringBootTest(classes = ...)` | Muốn nạp ứng dụng Spring Boot như một integration test | Application context của Boot với các auto-configuration phù hợp |

Với một shell test hẹp, tạo test configuration chỉ import command và dependency cần thiết. Với kiểm thử wiring toàn ứng dụng, dùng `@SpringBootTest` cùng `@ShellTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@SpringBootTest(
        classes = DemoShellApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullApplicationShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void commandUsesApplicationServices() throws Exception {
        var screen = client.sendCommand("greet");

        ShellAssertions.assertThat(screen)
                .containsText("Xin chào từ Spring Shell 4");
    }
}
```

Ở đây `@SpringBootTest` tạo full application context; `@ShellTest` bổ sung test client. Nếu ứng dụng có database, message broker hoặc service bên ngoài, hãy dùng test database, mock bean hoặc Testcontainers theo nhu cầu. Đừng mong `@ShellTest` tự loại các bean đó trong 4.0.

## 8. So sánh ShellTestClient giữa hai thế hệ

`ShellTestClient` là nơi khác biệt API dễ thấy nhất:

| Tác vụ | Spring Shell 3.3 | Spring Shell 4.0.4 |
|---|---|---|
| Kiểu API | Interface | Class |
| Chạy một command | `client.nonInterative("help").run()` | `client.sendCommand("help")` |
| Mở REPL session | `client.interactive().run()` | Không dùng API session cũ trong `ShellTestClient` 4.0 |
| Gửi chuỗi phím | `session.write(session.writeSequence()...)` | Không còn `ShellWriteSequence` trong API test 4.0 |
| Nhận output | `session.screen()` hoặc `client.screen()` | `ShellScreen` trả trực tiếp từ `sendCommand(...)` |
| Cấp input/password | Qua cơ chế session/input của 3.3 | `ShellInputProvider` và `sendCommand(provider)` |

Ví dụ 4.0 cung cấp input cho command cần đọc thêm dữ liệu:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellInputProvider;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

@ShellTest
@ContextConfiguration(classes = DemoShellApplication.class)
class InputCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void suppliesInputToCommand() throws Exception {
        ShellInputProvider input = ShellInputProvider
                .providerFor("ask")
                .withInput("hello")
                .build();

        var screen = client.sendCommand(input);

        ShellAssertions.assertThat(screen)
                .containsText("You said: hello");
    }
}
```

`ShellInputProvider` có thể chứa input thường và password riêng. Dùng nó để kiểm thử command đọc dữ liệu bổ sung mà không cần thao tác terminal thật. API này được bổ sung từ Spring Shell 4.0.2.

## 9. Giữ cùng phạm vi context khi nâng cấp

Muốn test 3.3 và 4.0 có cùng phạm vi bean, hãy xác định bean nào thực sự cần cho test rồi dựng context tương ứng ở mỗi thế hệ.

Ví dụ, một command gọi `CustomerService` và repository:

```text
Shell-focused test
  ├── Shell command infrastructure
  ├── CustomerCommands
  ├── CustomerService
  └── Mock CustomerRepository
```

Trong 3.3, `@ShellTest` tạo slice; có thể đưa service/test bean vào bằng `@Import`, include filter hoặc test configuration. Trong 4.0, khai báo context bằng `@ContextConfiguration` với cấu hình test chỉ import các bean tương ứng, đồng thời cung cấp shell auto-configuration cần cho command.

Nếu cần kiểm tra cả repository thật và transaction, hãy dùng full application context ở cả hai thế hệ. Không so sánh kết quả giữa một test slice 3.3 với một full context 4.0 rồi kết luận rằng nâng cấp đã làm thay đổi logic command.

Một nguyên tắc thực tế là ghi rõ phạm vi test trong tên lớp hoặc cấu hình base test, ví dụ `CustomerCommandSliceTests` và `CustomerCommandIntegrationTests`. Cách đặt tên này giúp reviewer nhận ra hai test có mục đích và context khác nhau.

## 10. Context cache và việc dùng chung giữa các test

Spring TestContext framework cache `ApplicationContext` sau khi tạo. Các test khai báo cùng cấu hình context trong cùng test suite có thể dùng lại context đó thay vì khởi động Spring lại.

Các thành phần thường tham gia xác định cache key gồm:

- Class hoặc resource trong `@ContextConfiguration`.
- Context loader, initializer và resource base path nếu có.
- Active profiles.
- Property source và property values.
- Context customizer, dynamic property source và bean override.
- Parent context nếu có hierarchy.

Ví dụ, hai test class có cùng `@ContextConfiguration(classes = DemoShellApplication.class)`, cùng profile và property có thể dùng chung context. Nếu một class thêm profile hoặc property khác, Spring có thể tạo một context khác.

Context cache nằm trong JVM của test suite. Nếu build tool fork một process riêng cho từng test class, các process không chia sẻ static cache nên context sẽ được dựng lại.

Context được dùng lại nghĩa là các singleton bean trong đó cũng được dùng lại. Nếu command gọi service có mutable state, kết quả test trước có thể ảnh hưởng test sau. Đây là vấn đề test isolation cần xử lý bằng cách reset fixture/state hoặc tạo context mới khi thật sự cần.

## 11. Dùng `@DirtiesContext` đúng lúc

`@DirtiesContext` đánh dấu context đã bị thay đổi đến mức không nên tiếp tục dùng. Spring loại context đó khỏi cache và đóng nó; test tiếp theo cần cùng cấu hình sẽ phải dựng context mới.

Ví dụ:

```java
@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {
    // Mỗi test method kết thúc thì context được loại khỏi cache.
}
```

Trong tài liệu 3.3, ví dụ test interactive/non-interactive sử dụng `AFTER_EACH_TEST_METHOD`. Điều này hữu ích khi phiên shell hoặc state của context còn ảnh hưởng đến test kế tiếp.

Tuy nhiên, không nên gắn `@DirtiesContext` vào mọi shell test theo thói quen. Mỗi lần loại context khỏi cache làm tăng chi phí khởi động Spring. Ưu tiên dọn dữ liệu test, reset mock, kết thúc phiên terminal và giữ service không có mutable state giữa các lần gọi. Chỉ dirty context khi test thực sự làm thay đổi trạng thái container hoặc không thể cleanup đáng tin cậy.

Có thể chọn scope khác tùy nhu cầu:

| Cấu hình | Khi nào context bị đánh dấu dirty |
|---|---|
| `AFTER_EACH_TEST_METHOD` | Sau mỗi test method |
| `AFTER_CLASS` | Sau khi toàn bộ test class hoàn tất |
| `BEFORE_EACH_TEST_METHOD` | Trước mỗi test method |
| `BEFORE_CLASS` | Trước khi test class chạy |

Đừng dùng `@DirtiesContext` để che giấu race condition hoặc shared state không được quản lý trong command/service. Hãy sửa lifecycle của tài nguyên trước.

## 12. Cấu hình terminal size và test properties

Spring Shell 3.3 cung cấp terminal emulator mặc định 80 cột x 24 dòng. Có thể thay đổi bằng thuộc tính annotation:

```java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
class WideTerminalTests {
}
```

Hoặc dùng `properties`:

```java
@ShellTest(properties = {
        "spring.shell.test.terminal-width=120",
        "spring.shell.test.terminal-height=40"
})
class WideTerminalTests {
}
```

Trong Spring Shell 4.0, `terminalWidth`, `terminalHeight` và `SpringShellTestProperties` đã bị loại bỏ. Không copy hai thuộc tính annotation 3.3 vào test 4.0.4. Nếu layout phụ thuộc kích thước terminal, hãy kiểm thử với test harness/terminal giả lập phù hợp với API hiện tại hoặc chuyển phần layout thuần sang unit test của component.

Các property nghiệp vụ khác vẫn có thể được cấu hình bằng `@TestPropertySource` hoặc thuộc tính của `@SpringBootTest`; điều đó không có nghĩa các property terminal cũ vẫn được hỗ trợ.

## 13. Khi nào cần full end-to-end test?

`ShellTestClient` phù hợp để kiểm tra command thông qua test client trong Spring context. Nếu cần xác minh cách JAR khởi động, runner chọn chế độ, process arguments, exit code hoặc hành vi stdout/stderr, hãy chạy ứng dụng như một process test riêng.

Trong Spring Shell 4, tài liệu hướng dẫn dùng `@SpringBootTest` với:

- `webEnvironment = WebEnvironment.NONE` cho ứng dụng CLI.
- `useMainMethod = ALWAYS` khi cần chạy qua main method.
- `spring.shell.interactive.enabled=false` để command được thực thi non-interactive.
- `OutputCaptureExtension` để kiểm tra output.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS,
        classes = DemoShellApplication.class,
        properties = "spring.shell.interactive.enabled=false",
        args = "greet")
@ExtendWith(OutputCaptureExtension.class)
class ShellProcessTests {

    @Test
    void writesGreeting(CapturedOutput output) {
        assertThat(output).contains("Xin chào từ Spring Shell 4");
    }
}
```

Đây là black-box test cho lần khởi động ứng dụng. Vì command được truyền qua `args` của `@SpringBootTest`, cách này không tiện để gọi nhiều command khác nhau trong cùng test class. Với nhiều command trong cùng context, dùng `ShellTestClient`.

## 14. Lỗi thường gặp khi chuyển từ 3.3 sang 4.0

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy bean `ShellTestClient` | Chưa dùng `@ShellTest` hoặc chưa import test client auto-configuration | Dùng `@ShellTest` và cấu hình context đúng phiên bản |
| Không tìm thấy command bean | Context 4.0 chỉ nạp config được chỉ định; command không nằm trong component scan/import | Thêm command bean vào test configuration hoặc dùng application class |
| Test 4.0 thiếu service/repository | `@ShellTest` 4.0 không còn tự tạo Boot slice theo cơ chế 3.3 | Dùng `@ContextConfiguration` hoặc `@SpringBootTest` phù hợp |
| Không biên dịch được `client.interactive()` | API session của `ShellTestClient` 3.3 đã thay đổi | Dùng `sendCommand(...)` trong 4.0; dùng process test nếu cần kiểm thử runner/REPL |
| Không biên dịch được `terminalWidth` | Thuộc tính `@ShellTest` 3.3 đã bị loại bỏ | Dùng test terminal phù hợp với thế hệ 4.0 |
| Test class tạo nhiều context | Các test dùng config/profile/property khác nhau hoặc bị `@DirtiesContext` loại cache | Chuẩn hóa test configuration và chỉ dirty khi cần |
| Test phụ thuộc thứ tự chạy | Singleton bean hoặc command giữ mutable state | Reset state sau mỗi test, dùng fixture độc lập hoặc context mới có chủ đích |

Các API sau của 3.3 đã bị loại bỏ trong 4.0: `ShellWriteSequence`, `ShellTypeExcludeFilter`, `SpringShellTestProperties`, `@AutoConfigureShell` và `@AutoConfigureShellTestClient`. `@ShellTest` tự import test client auto-configuration trong 4.0.

## 15. Quy trình chọn context cho một bộ test

Trước khi thêm annotation, hãy trả lời theo thứ tự:

1. Test đang kiểm tra parser/command output hay toàn bộ wiring ứng dụng?
2. Command cần những service/repository nào để chạy?
3. Có thể mock dependency bên ngoài hay cần database thật?
4. Nhiều test class có thể dùng cùng profile, property và cấu hình context không?
5. Test có mở interactive session hoặc làm thay đổi singleton state không?
6. Có cần kiểm tra terminal dimensions, process args hoặc exit code không?
7. Có thể cleanup state sau test hay cần `@DirtiesContext`?

Chọn shell-focused context cho test command nhanh. Chọn full context cho wiring/integration. Chọn process-level test cho startup, runner và exit code. Không cần dùng một loại context cho mọi loại kiểm thử.

## 16. Bài tập thực hành

Có một command `customer list` gọi `CustomerService`, hiển thị bảng khách hàng và có thể đọc thêm một giá trị filter từ input provider.

Hãy thực hiện hai bộ test riêng:

**Bộ A — Spring Shell 3.3.x**

1. Dùng `@ShellTest` để tạo shell test slice.
2. Đưa `CustomerService` vào context hoặc mock dependency của command.
3. Dùng `ShellTestClient.nonInterative(...)` để chạy command.
4. Dùng `interactive()` để gửi một chuỗi phím vào REPL.
5. Thử `terminalWidth=120` và xác nhận bảng không bị wrap ngoài dự kiến.
6. Thử `@DirtiesContext(AFTER_EACH_TEST_METHOD)` rồi so sánh thời gian chạy với cách reset state.

**Bộ B — Spring Shell 4.0.4**

1. Dùng `@ShellTest` cùng `@ContextConfiguration` để chỉ rõ test context.
2. Tạo test full context bằng `@SpringBootTest` và `@ShellTest`.
3. Dùng `ShellTestClient.sendCommand(...)` để gọi command.
4. Dùng `ShellInputProvider` để cung cấp input bổ sung.
5. Xác nhận API 3.3 như `interactive()`, `nonInterative()` và `terminalWidth` không được copy sang 4.0.
6. Dùng process-level test nếu cần xác minh main method và exit code.

**Kết quả cần nộp:** hai bộ test, sơ đồ bean/context của mỗi thế hệ, bảng so sánh API, kết quả context cache và giải thích khi nào dùng `@DirtiesContext`.

## 17. Checklist trước khi nâng cấp test

- [ ] Đã xác định test cần shell slice hay full application context.
- [ ] Đã kiểm tra đúng phiên bản Spring Shell và Spring Boot.
- [ ] Test 3.3 dùng đúng `@ShellTest` slice semantics.
- [ ] Test 4.0 khai báo context bằng `@ContextConfiguration` hoặc `@SpringBootTest`.
- [ ] Command bean và các dependency cần thiết thực sự nằm trong context.
- [ ] Không dùng `@ShellTest` 4.0 như thể nó vẫn tự áp dụng `ShellTestContextBootstrapper`.
- [ ] Đã đổi API `ShellTestClient` theo đúng thế hệ.
- [ ] Không dùng `ShellWriteSequence` hoặc terminal dimension attributes đã bị loại bỏ trong 4.0.
- [ ] Context cache được tận dụng bằng cách giữ cấu hình test nhất quán.
- [ ] State của singleton/service được reset giữa các test.
- [ ] `@DirtiesContext` chỉ dùng khi cần loại context khỏi cache.
- [ ] Interactive/async output được chờ bằng timeout phù hợp ở 3.3.
- [ ] Process startup, args và exit code được kiểm thử ở tầng end-to-end.

## Tài liệu tham khảo

- [Spring Shell 3.3 — Testing Basics](https://docs.spring.io/spring-shell/reference/3.3/testing/basics.html)
- [Spring Shell 3.3 — Testing Settings](https://docs.spring.io/spring-shell/reference/3.3/testing/settings.html)
- [Spring Shell 3.3 API — `@ShellTest`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 3.3 API — `ShellTestContextBootstrapper`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/autoconfigure/ShellTestContextBootstrapper.html)
- [Spring Shell 3.3 API — `ShellTestClient`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.4 API — `@ShellTest`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 4.0.4 API — `ShellTestClient`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.4 API — `ShellInputProvider`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Framework — Context Caching](https://docs.spring.io/spring/reference/7.0/testing/testcontext-framework/ctx-management/caching.html)
