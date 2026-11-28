# Mô phỏng dữ liệu nhập hoặc mật khẩu bằng khả năng của phiên bản

Khi kiểm thử command có prompt, test cần cung cấp dữ liệu như thể người dùng đang gõ trên terminal. Với mật khẩu, test còn phải bảo đảm secret được chuyển tới service nhưng không xuất hiện trong output. Cách làm phụ thuộc phiên bản Spring Shell: dòng 3.x chủ yếu mô phỏng thao tác bàn phím qua interactive session; từ Spring Shell 4.0.2, test support có `ShellInputProvider` với hai hàng đợi riêng cho input thông thường và password.

Hãy chọn API theo phiên bản đang dùng, không sao chép ví dụ 4.x vào dự án 3.x. Đồng thời, chỉ dùng secret giả trong test. Một test fixture có thể giữ mật khẩu ở dạng rõ trong bộ nhớ, kể cả khi terminal hiển thị dấu `*`.

## Kiểm thử cần mô phỏng điều gì?

Một command có thể nhận dữ liệu theo nhiều cách:

| Cách nhập | Ví dụ | Điều cần kiểm thử |
|---|---|---|
| Command option/argument | `user-create --name alice` | Parser, binding và validation |
| Prompt nhập văn bản | `Tên người dùng: ` | Dữ liệu được gửi đúng thứ tự và xử lý đúng |
| ComponentFlow | `StringInput`, `PathInput`, selector | Flow mở, nhận giá trị và chuyển sang bước tiếp theo |
| Prompt mật khẩu | `Password: ` | Service nhận đúng secret; output không lộ secret |
| Xác nhận | `Tiếp tục? [y/N]` | Giá trị mặc định, nhánh chấp nhận và từ chối |
| Non-interactive | Command chạy trong CI hoặc script | Không chờ bàn phím; thiếu input phải báo lỗi rõ |

Phân biệt ba việc:

1. **Mô phỏng input:** đưa dữ liệu vào command hoặc prompt.
2. **Kiểm tra masking:** xác nhận nội dung nhạy cảm không được render thành văn bản rõ.
3. **Kiểm tra bảo mật:** xác nhận secret không lọt vào log, exception, output hoặc history.

Một test có thể làm tốt việc thứ nhất nhưng chưa chứng minh hai việc còn lại. Ví dụ, `ShellInputProvider` có thể đưa password vào `InputReader`, nhưng test vẫn phải kiểm tra screen và log không chứa password.

## Chọn API theo phiên bản Spring Shell

| Phiên bản | Mô phỏng text input | Mô phỏng password riêng | API chính |
|---|---|---|---|
| Spring Shell 3.3.x/3.4.x | Có, qua interactive session và chuỗi phím | Không có `ShellInputProvider`/password queue trong API test được tài liệu 3.4 công bố | `ShellTestClient.interactive()`, `ShellWriteSequence`, `ComponentFlow` |
| Spring Shell 4.0.0–4.0.1 | Có thể dùng interactive test session | Chưa có `ShellInputProvider` (API này được thêm từ 4.0.2) | `ShellTestClient`, `CommandContext.inputReader()` |
| Spring Shell 4.0.2 trở lên | Có, qua provider | Có queue riêng cho password | `ShellInputProvider`, `ShellTestClient.sendCommand(provider)` |

Spring Shell 3.4 có `ShellTestClient` để chạy interactive/non-interactive session và `ShellWriteSequence` để gửi text, Enter, phím điều hướng hoặc control key. API này mô phỏng thao tác terminal ở mức chuỗi phím. Javadoc 3.4 không công bố một provider có queue password riêng.

Spring Shell 4.0.2 bổ sung `ShellInputProvider` và overload `ShellTestClient.sendCommand(ShellInputProvider)`. Provider tách `inputs` và `passwords` thành hai `Deque<String>` riêng. Từ Spring Shell 4.x, `CommandContext.inputReader().readPassword()` đọc password và trả về `char[]`.

## Spring Shell 3.x: gửi text qua interactive session

Trong dòng 3.x, `@ShellTest` thiết lập test context. Dùng `client.interactive().run()` để mở phiên shell, sau đó gửi command và dữ liệu prompt qua `writeSequence()`.

Ví dụ một component nhập password bằng `ComponentFlow`:

```java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;

@Component
class PasswordPrompt {

    private final ComponentFlow.Builder flowBuilder;

    PasswordPrompt(ComponentFlow.Builder flowBuilder) {
        this.flowBuilder = flowBuilder;
    }

    String readPassword() {
        var result = flowBuilder.clone().reset()
                .withStringInput("password")
                    .name("Mật khẩu")
                    .maskCharacter('*')
                    .and()
                .build()
                .run();

        return result.getContext().get("password", String.class);
    }
}
```

`maskCharacter('*')` quy định cách component hiển thị ký tự nhập. Giá trị thực vẫn được trả về trong `ComponentContext` dưới dạng `String`; masking không mã hóa dữ liệu và không biến nó thành `char[]`.

Một command gọi prompt:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class LoginCommands {

    private final PasswordPrompt passwordPrompt;
    private final AuthenticationService authenticationService;

    LoginCommands(
            PasswordPrompt passwordPrompt,
            AuthenticationService authenticationService) {
        this.passwordPrompt = passwordPrompt;
        this.authenticationService = authenticationService;
    }

    @ShellMethod(key = "login")
    public String login() {
        String password = passwordPrompt.readPassword();
        authenticationService.authenticate(password);
        return "Đã xác thực.";
    }
}
```

Đoạn command trên chỉ minh họa luồng 3.x. Vì giá trị là `String`, không thể xóa nội dung bên trong đối tượng sau khi dùng. Giữ phạm vi sử dụng ngắn, không lưu vào singleton/session và không log giá trị.

### Test gửi password qua chuỗi phím

Trong 3.x, interactive session có thể gửi command, chờ prompt rồi gửi text và Enter:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class LoginCommandTests {

    private static final String TEST_PASSWORD = "fake-password-123";

    @Autowired
    ShellTestClient client;

    @Test
    void passwordIsMaskedAndNotPrinted() {
        var session = client.interactive().run();
        session.write(session.writeSequence().command("login").build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen()).containsText("Mật khẩu"));

        session.write(session.writeSequence()
                .text(TEST_PASSWORD)
                .carriageReturn()
                .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen()).containsText("Đã xác thực"));

        assertThat(session.screen().lines())
                .noneMatch(line -> line.contains(TEST_PASSWORD));
    }
}
```

`writeSequence().text(...)` gửi chuỗi ký tự như input terminal; `carriageReturn()` gửi Enter. Test chờ prompt trước khi gửi password để tránh dữ liệu đến quá sớm. `@DirtiesContext` hữu ích khi test tạo interactive session có vòng đời dài; nó buộc Spring tạo context mới sau method.

Test này kiểm tra luồng ComponentFlow và output đã capture. Nó không tạo một kênh password riêng biệt như API 4.0.2. Nếu ứng dụng tự gọi JLine `LineReader` hoặc có input reader tùy chỉnh, cần cấu hình terminal/test adapter tương ứng và kiểm thử riêng.

### Test text input và nhiều bước

Với wizard có username rồi password, gửi từng bước theo đúng thứ tự:

```java
session.write(session.writeSequence().command("login").build());

await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen()).containsText("Tên người dùng"));

session.write(session.writeSequence().text("alice").carriageReturn().build());

await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen()).containsText("Mật khẩu"));

session.write(session.writeSequence()
        .text("fake-password-123")
        .carriageReturn()
        .build());
```

Đừng gửi liền nhiều dòng nếu component thay đổi prompt theo kết quả trước đó. Chờ mỗi trạng thái rồi mới gửi bước tiếp theo giúp test ổn định hơn và chỉ rõ bước nào bị lỗi.

### Khi cần test non-interactive trong 3.x

Non-interactive session chạy command với arguments, không phải nơi để trả lời prompt bàn phím. Dùng `client.nonInteractive(...)` từ Spring Shell 3.4.2 trở lên; ở bản 3.4.1 trở xuống, API có tên cũ `nonInterative(...)` (chính tả của method) và được giữ để tương thích.

Nếu command bắt buộc phải hỏi password nhưng chạy trong non-interactive mode, thiết kế command để từ chối với hướng dẫn dùng secret provider/file/option tham chiếu phù hợp. Không chờ input vô hạn trong CI.

## Spring Shell 4.0.0–4.0.1: InputReader đã có, provider password chưa có

Spring Shell 4.0.0 đưa `InputReader` vào `CommandContext`. API có:

- `readInput()` và `readInput(prompt)` trả `String`.
- `readPassword()` và `readPassword(prompt)` trả `char[]`.

Ví dụ command programmatic:

```java
import java.util.Arrays;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
class LoginCommandConfiguration {

    @Bean
    Command login(AuthenticationService authenticationService) {
        return new AbstractCommand("login", "Xác thực người dùng") {

            @Override
            public ExitStatus doExecute(CommandContext context) throws Exception {
                String username = context.inputReader().readInput("Tên người dùng: ");
                char[] password = context.inputReader().readPassword("Mật khẩu: ");
                try {
                    authenticationService.authenticate(username, password);
                    context.outputWriter().println("Đã xác thực.");
                    return ExitStatus.OK;
                } finally {
                    Arrays.fill(password, '\0');
                }
            }
        };
    }
}
```

`InputReader` đã có từ 4.0.0, nhưng test provider có queue riêng cho password chỉ xuất hiện từ 4.0.2. Với 4.0.0–4.0.1, có thể dùng interactive session hoặc tự cấu hình test input adapter; không import `ShellInputProvider` từ ví dụ 4.0.2+.

## Spring Shell 4.0.2 trở lên: dùng ShellInputProvider

`ShellInputProvider` là record trong package `org.springframework.shell.test`. Nó giữ:

- `command`: command cần chạy.
- `inputs`: hàng đợi text input.
- `passwords`: hàng đợi password input.

Builder cung cấp `providerFor(command)`, `withInput(...)`, `withPassword(...)` và `build()`. Sau đó gọi overload `client.sendCommand(provider)`.

```java
import org.springframework.shell.test.ShellInputProvider;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;

ShellInputProvider provider = ShellInputProvider.providerFor("login")
        .withInput("alice")
        .withPassword("fake-password-123")
        .build();

ShellScreen screen = client.sendCommand(provider);
```

Nếu command hỏi nhiều giá trị, thêm nhiều `withInput(...)` hoặc `withPassword(...)` theo thứ tự mỗi loại được yêu cầu. Hai queue tách biệt giúp test cung cấp text và password qua đúng kênh mà `InputReader` sử dụng.

### Test InputReader nhận password và không in secret

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.shell.test.ShellInputProvider;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class LoginPasswordInputTests {

    private static final String TEST_PASSWORD = "fake-password-123";

    @Autowired
    ShellTestClient client;

    @MockitoBean
    AuthenticationService authenticationService;

    @Test
    void suppliesPasswordThroughDedicatedPasswordQueue() throws Exception {
        AtomicReference<char[]> received = new AtomicReference<>();

        doAnswer(invocation -> {
            char[] supplied = invocation.getArgument(1);
            received.set(Arrays.copyOf(supplied, supplied.length));
            return null;
        }).when(authenticationService)
                .authenticate(eq("alice"), any(char[].class));

        ShellInputProvider provider = ShellInputProvider.providerFor("login")
                .withInput("alice")
                .withPassword(TEST_PASSWORD)
                .build();

        ShellScreen screen = client.sendCommand(provider);

        try {
            assertThat(received.get()).containsExactly(TEST_PASSWORD.toCharArray());
            assertThat(screen.lines()).noneMatch(line -> line.contains(TEST_PASSWORD));
        } finally {
            char[] copy = received.get();
            if (copy != null) {
                Arrays.fill(copy, '\0');
            }
        }
    }
}
```

Trong test này, mock sao chép mảng password trước khi command xóa mảng gốc trong `finally`. Mảng sao chép chỉ tồn tại để assertion; test xóa nó sau khi kiểm tra. Có thể thay cách capture bằng fake service ghi nhận một kết quả kiểm thử không nhạy cảm. Không dùng password thật trong test fixture.

`ShellInputProvider` chỉ là cơ chế cung cấp dữ liệu cho test. Queue của nó chứa `String` nên password test vẫn tồn tại dưới dạng rõ trong heap. Không ghi provider vào log, không nối provider vào assertion message và không dùng `provider.toString()` để debug.

## Cẩn thận với toString() của ShellInputProvider

`ShellInputProvider` là Java record. `toString()` do record sinh ra bao gồm tên và giá trị các component, tức có thể in cả `inputs` và `passwords` queue. Vì vậy, đoạn sau có thể làm lộ password giả trong log:

```java
// Không nên: toString() của record chứa queue input/password.
log.debug("Input provider: {}", provider);
```

Chỉ log thông tin không nhạy cảm như tên test hoặc command ID:

```java
log.debug("Executing shell input test for command={}", "login");
```

Không dùng dữ liệu production, token dùng được hoặc password cá nhân trong `ShellInputProvider`. Dùng chuỗi sentinel giả, giới hạn quyền truy cập test report và không lưu raw input vào snapshot.

## Kiểm tra masking và kiểm tra password được truyền là hai assertion khác nhau

Với component có `maskCharacter('*')`, test nên xác minh:

1. Prompt được hiển thị.
2. Input thực được chuyển tới service xác thực.
3. Screen không chứa secret dạng rõ.
4. Nếu renderer hiển thị mask, screen chỉ có ký tự mask theo hành vi mong muốn.
5. Output sau xác thực chỉ thông báo kết quả, không echo password.

Không kiểm tra rằng số dấu `*` luôn bằng số ký tự password nếu component/terminal có chính sách che độ dài. Một số giao diện có thể không echo gì để tránh lộ độ dài. Hãy kiểm tra hợp đồng renderer của ứng dụng thay vì giả định mọi phiên bản hiển thị giống nhau.

`ShellInputProvider` kiểm thử đường đọc `InputReader` bằng queue riêng. Nó không tự chứng minh terminal thật đã tắt echo, masking hoạt động trên mọi terminal emulator hoặc không có keylogger. Nếu bảo mật phụ thuộc vào hành vi TTY/JLine, cần thêm acceptance test trên terminal phù hợp.

## Kiểm tra nhiều input, thứ tự và lỗi

Với command có nhiều bước, test các trường hợp:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Một text input | Giá trị đến đúng prompt |
| Một password input | Giá trị đến đúng password reader; không xuất hiện trên screen |
| Nhiều text input | Mỗi giá trị được tiêu thụ đúng thứ tự |
| Nhiều password input | Password queue được tiêu thụ đúng thứ tự |
| Text và password xen kẽ | Mỗi loại được lấy từ đúng queue/reader |
| Queue thiếu giá trị | Test phát hiện input chưa được cung cấp; không treo vô hạn |
| Queue thừa giá trị | Test phát hiện dữ liệu không được tiêu thụ hoặc flow thay đổi |
| Password sai | Service từ chối; output không tiết lộ password |
| Service ném exception | Secret vẫn được xóa trong `finally`; lỗi không chứa secret |
| Người dùng hủy prompt | Command dừng theo chính sách, không gọi service với giá trị rỗng |
| Non-interactive không có input | Command từ chối rõ ràng hoặc dùng secret provider được cấu hình |

Với Spring Shell 3.x, gửi từng chuỗi phím và chờ screen chuyển trạng thái trước khi gửi tiếp. Với 4.0.2+, sắp xếp `withInput(...)` và `withPassword(...)` theo đúng thứ tự mà command gọi `readInput()`/`readPassword()`; kiểm tra các queue không bị tiêu thụ sai khi thêm prompt mới.

## Phân biệt test framework với kiểm thử đầu cuối

`@ShellTest` và `ShellTestClient` giúp kiểm tra command, input và output trong test context. Chúng không thay thế kiểm thử tiến trình thực tế cho mọi hành vi terminal.

| Tầng test | Nên kiểm tra |
|---|---|
| Unit test service | Password đúng/sai, policy, lockout và xử lý credential |
| Shell test 3.x | ComponentFlow, write sequence, thứ tự prompt và output masking |
| Shell test 4.0.2+ | Input queue, password queue, `InputReader.readPassword()` và output redaction |
| Integration test | Wiring của Spring context, command registration và service thật/fake |
| Process/terminal test | Echo, PTY, Ctrl+C, encoding, prompt và process exit trong môi trường mục tiêu |

Không đưa secret thật vào process arguments chỉ để kiểm thử password. Test bảo mật nên dùng sentinel giả và kiểm tra output/log capture không chứa sentinel đó.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không biên dịch `ShellInputProvider` trong Spring Shell 3.x | API chỉ được thêm từ 4.0.2 | Dùng interactive session và `ShellWriteSequence` cho 3.x |
| Test 3.x gửi password trước khi prompt xuất hiện | Gửi input quá sớm hoặc không chờ flow chuyển trạng thái | Chờ prompt bằng Awaitility rồi gửi text/Enter |
| Test non-interactive bị treo ở password prompt | Non-interactive session không phải interactive input queue | Thiết kế command nhận secret qua provider/config phù hợp; không chờ terminal |
| Screen có password rõ | Component không cấu hình masking hoặc code echo giá trị | Dùng `maskCharacter`, bỏ echo và kiểm tra output |
| Test pass nhưng service nhận password rỗng | Test chỉ kiểm tra prompt/output, chưa xác minh service call | Verify service nhận giá trị fake mong đợi |
| Log test chứa password | Log `ShellInputProvider`, context hoặc input object | Không log provider/context; chỉ log metadata allowlist |
| Dùng `toString()` để debug provider | Record tự in cả queue inputs/passwords | Không stringify provider; dùng fake secret và log command name |
| Test phụ thuộc số lượng dấu `*` | Giả định renderer luôn echo từng ký tự | Kiểm tra hợp đồng masking, không mặc định lộ độ dài |
| Mảng password bị giữ lại sau test | Test capture `char[]` mà không xóa bản sao | Xóa test buffer trong `finally` hoặc sau assertion |
| Test pass nhưng terminal thật echo password | Test provider không kiểm tra terminal emulator/TTY | Bổ sung acceptance test với terminal mục tiêu |

## Quy trình chọn cách mô phỏng

1. Xác định phiên bản Spring Shell đang dùng từ dependency thực tế.
2. Nếu dùng 3.3.x/3.4.x, dùng `@ShellTest` và interactive session để gửi `ShellWriteSequence`; với `ComponentFlow`, cấu hình `maskCharacter` cho input nhạy cảm.
3. Nếu dùng 4.0.0–4.0.1, dùng `InputReader` cho command mới nhưng chưa dùng `ShellInputProvider`.
4. Nếu dùng 4.0.2 trở lên, dùng `ShellInputProvider.providerFor(...)`, `withInput(...)`, `withPassword(...)` và `client.sendCommand(provider)`.
5. Chỉ dùng secret giả; không log provider vì `toString()` có thể chứa queue password.
6. Kiểm tra cả giá trị service nhận và nội dung screen/log không chứa secret.
7. Xóa các bản sao `char[]` do test tự tạo sau assertion.
8. Kiểm thử riêng trường hợp thiếu input, sai password, exception và non-interactive mode.
9. Chạy acceptance test trên terminal thật nếu cần xác minh echo, masking, PTY hoặc key handling.

Khả năng mô phỏng input/password thay đổi theo thế hệ Spring Shell. 3.x cho phép test tương tác bằng chuỗi phím; 4.0.2 trở lên cung cấp kênh test riêng cho text và password. Chọn đúng API giúp test phản ánh đúng luồng ứng dụng, đồng thời giữ dữ liệu kiểm thử tách biệt khỏi output và log.

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Testing Basics](https://docs.spring.io/spring-shell/reference/3.4/testing/basics.html): `@ShellTest`, interactive/non-interactive sessions và cách gửi chuỗi phím qua `ShellWriteSequence`.
- [Spring Shell 3.4.3 API — ShellTestClient](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/test/ShellTestClient.html): interactive session và non-interactive session trong 3.x.
- [Spring Shell 3.4.3 API — ShellWriteSequence](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/test/ShellWriteSequence.html): `text`, `carriageReturn`, `command`, phím điều hướng và control key.
- [Spring Shell 3.4.3 API — BaseStringInput](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/BaseStringInput.html): `maskCharacter(Character)` cho `StringInput`.
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html): `ShellInputProvider` để cung cấp text input và password trong test.
- [Spring Shell 4.0.4 API — ShellInputProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html): queue `inputs`/`passwords`, `providerFor(...)` và thời điểm API xuất hiện từ 4.0.2.
- [Spring Shell 4.0.4 API — ShellInputProvider.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.Builder.html): `withInput(...)`, `withPassword(...)` và `build()`.
- [Spring Shell 4.0.3 API — ShellTestClient](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html): `sendCommand(ShellInputProvider)` và `sendCommand(String)`.
- [Spring Shell 4.0.4 API — InputReader](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputReader.html): `readInput()` và `readPassword()` trả về `char[]`.
- [Spring Shell 4.0.3 API — CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html): lấy `InputReader` qua `inputReader()`.
