# ShellTestClient và ShellAssertions để tương tác và kiểm tra đầu ra

Kiểm thử một ứng dụng Spring Shell cần mô phỏng cách người dùng nhập lệnh và quan sát terminal. Gọi trực tiếp method command chỉ kiểm tra logic Java; nó không xác minh command đã được đăng ký, option được parse đúng hay output được gửi tới màn hình như mong đợi.

Spring Shell 3.x cung cấp test support gồm `ShellTestClient`, `ShellScreen` và `ShellAssertions`. `ShellTestClient` khởi chạy phiên shell giả lập và nhận input; `ShellScreen` biểu diễn màn hình sau khi chạy; `ShellAssertions` cung cấp assertion để kiểm tra nội dung đã hiển thị.

Bài học sử dụng API Spring Shell 3.1.6. Phiên bản này có một tên method cần chú ý: `ShellTestClient.nonInterative(String...)` viết thiếu chữ `a` trong `Interactive`. Từ Spring Shell 3.4.2, method `nonInteractive(String...)` được bổ sung và method cũ bị deprecated. Hãy dùng API đúng với dependency của dự án.

## 1. Vì sao cần ShellTestClient?

Một command có thể chạy đúng khi gọi trực tiếp method nhưng vẫn thất bại trong shell vì:

- Command chưa được đăng ký hoặc tên command khác với tên test gọi.
- Option bị parse sai hoặc không chuyển đổi được sang kiểu Java.
- Output được định dạng khác dự kiến.
- Prompt yêu cầu input bổ sung nhưng test không gửi input.
- Shell cập nhật màn hình bất đồng bộ, khiến assertion chạy quá sớm.
- Terminal có chiều rộng và chiều cao khác môi trường phát triển.

`ShellTestClient` mô phỏng phiên terminal để test đi qua đường xử lý của Spring Shell. Thay vì gọi method như `projectCommands.list()`, test gửi chuỗi lệnh vào client, chờ shell xử lý và đọc màn hình kết quả.

~~~mermaid
flowchart TD
    A["JUnit test"] --> B["ShellTestClient"]
    B --> C["Phiên terminal giả lập"]
    C --> D["Spring Shell parser"]
    D --> E["Command registration"]
    E --> F["Command method"]
    F --> G["Result handler"]
    G --> H["ShellScreen"]
    H --> I["ShellAssertions"]
    I --> J["Test pass hoặc fail"]
~~~

Cách này kiểm tra được nhiều thành phần hơn unit test method, nhưng vẫn chạy trong terminal giả lập. Kiểm thử tiến trình ứng dụng thật, mã thoát của hệ điều hành hoặc hành vi terminal thật cần một lớp test khác.

## 2. Các module test cần thiết

Spring Shell 3.1.6 chia test support thành hai module:

| Module | Vai trò |
|---|---|
| `spring-shell-test` | Các API cốt lõi như `ShellTestClient`, `ShellScreen` và `ShellAssertions` |
| `spring-shell-test-autoconfigure` | Cấu hình tự động cho test Spring Shell, bao gồm annotation `@ShellTest` |

Với Gradle, khai báo các dependency test cùng phiên bản Spring Shell đang dùng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.shell:spring-shell-test'
    testImplementation 'org.springframework.shell:spring-shell-test-autoconfigure'
}
~~~

Với Maven, thêm hai artifact Spring Shell với scope test:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test-autoconfigure</artifactId>
    <scope>test</scope>
</dependency>
~~~

Dùng Spring Shell BOM hoặc dependency management của dự án để đồng bộ version. Không ghép `spring-shell-test` của một phiên bản với `spring-shell-starter` của phiên bản khác.

`spring-boot-starter-test` thường cung cấp JUnit Jupiter, Mockito và AssertJ. Ví dụ bên dưới cũng dùng Awaitility để chờ terminal cập nhật. Nếu Awaitility chưa có trên test classpath, thêm dependency `org.awaitility:awaitility` với scope test.

## 3. @ShellTest tạo môi trường kiểm thử shell

`@ShellTest` là annotation dành cho test tập trung vào các thành phần Spring Shell. Annotation này thuộc package:

~~~java
import org.springframework.shell.test.autoconfigure.ShellTest;
~~~

Các API tương tác và assertion thuộc package `org.springframework.shell.test`:

~~~java
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
~~~

Ví dụ một test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void clientCanRunShellCommand() {
        // Thực thi một command trong terminal giả lập.
    }
}
~~~

`@ShellTest` thiết lập môi trường test cho các thành phần shell và cung cấp `ShellTestClient` để test tương tác. Test vẫn cần ứng dụng hoặc command bean được Spring nhận diện theo cấu hình dự án.

Nếu command phụ thuộc service hoặc repository, có thể import bean cần thiết hoặc thay dependency bằng mock. Ví dụ dùng `@MockBean` để kiểm tra command mà không cần khởi tạo database thật.

~~~java
@ShellTest
class ProjectCommandsTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;
}
~~~

Trong Spring Boot 3.1, `@MockBean` thuộc Spring Boot test. Ở các phiên bản Spring Boot mới hơn, có thể gặp API thay thế; hãy theo đúng version Boot của ứng dụng.

## 4. Chạy command non-interactive

`ShellTestClient.nonInterative(String... args)` tạo phiên thực thi command không tương tác. Mỗi phần tử trong varargs là một token của command line.

Ví dụ người dùng chạy:

~~~text
project list
~~~

Test tương ứng:

~~~java
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.NonInteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectListTests {

    @Autowired
    ShellTestClient client;

    @Test
    void listCommandDisplaysProjects() {
        NonInteractiveShellSession session =
                client.nonInterative("project", "list").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("inventory-api"));
    }
}
~~~

`run()` khởi chạy phiên test và trả về session để đọc màn hình. `session.screen()` lấy trạng thái terminal hiện tại.

Trong ví dụ, test chờ tối đa hai giây để nội dung `inventory-api` xuất hiện. Cần chờ vì shell có thể xử lý command và ghi output qua các thành phần bất đồng bộ.

### 4.1. Truyền option và argument

Nếu command có option:

~~~text
project show --id 101
~~~

Gửi từng token vào client:

~~~java
NonInteractiveShellSession session = client
        .nonInterative(
                "project", "show",
                "--id", "101")
        .run();

await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("Project 101"));
~~~

Không truyền toàn bộ dòng lệnh thành một chuỗi duy nhất nếu API đang nhận varargs token. Tách command, subcommand, tên option và giá trị thành từng phần tử giúp test mô phỏng đúng đầu vào parser.

| Lệnh người dùng | Token truyền vào |
|---|---|
| `project list` | `"project", "list"` |
| `project show --id 101` | `"project", "show", "--id", "101"` |
| `project create --name inventory-api` | `"project", "create", "--name", "inventory-api"` |

Với option có giá trị chứa dấu cách, truyền toàn bộ giá trị thành một phần tử:

~~~java
client.nonInterative(
        "project", "create",
        "--name", "inventory api")
        .run();
~~~

Không tự thêm dấu nháy shell vào phần tử varargs nếu mục tiêu là truyền một giá trị duy nhất. Việc quote và escape trong một shell OS thực tế khác với việc truyền chuỗi token trực tiếp cho test client.

## 5. ShellScreen và ShellAssertions

`ShellTestClient` trả về session; session cung cấp `screen()` để đọc màn hình. Kết quả có kiểu `ShellScreen`.

`ShellAssertions.assertThat(ShellScreen)` tạo assertion object `ShellScreenAssert`. API được dùng phổ biến nhất là `containsText(String)` để xác minh một đoạn văn bản xuất hiện trên màn hình.

~~~java
ShellAssertions.assertThat(session.screen())
        .containsText("inventory-api");
~~~

Có thể xác minh nhiều phần nội dung:

~~~java
await().atMost(2, TimeUnit.SECONDS).untilAsserted(() -> {
    ShellAssertions.assertThat(session.screen())
            .containsText("ID")
            .containsText("Project")
            .containsText("inventory-api")
            .containsText("ACTIVE");
});
~~~

Nên kiểm tra những nội dung quan trọng đối với người dùng:

- Tên command hoặc tiêu đề output.
- Giá trị nghiệp vụ quan trọng.
- Thông báo thành công hoặc lỗi.
- Nội dung của bảng hoặc danh sách.
- Prompt cần thiết cho bước tiếp theo.

Tránh kiểm tra toàn bộ màn hình như một chuỗi cố định nếu output chứa prompt, con trỏ, thời gian hoặc thông tin có thể thay đổi giữa môi trường.

## 6. Vì sao cần Awaitility?

Terminal có thể trông như xử lý đồng bộ nhưng thực tế việc nhận input, chạy command và cập nhật màn hình có thể diễn ra bất đồng bộ. Spring Shell 3.1.6 khuyến nghị chờ điều kiện output thay vì giả định màn hình đã ổn định ngay sau `run()` hoặc `write()`.

Không nên viết:

~~~java
var session = client.nonInterative("project", "list").run();

ShellAssertions.assertThat(session.screen())
        .containsText("inventory-api");
~~~

Assertion trên có thể đọc màn hình trước khi command ghi xong output.

Dùng Awaitility:

~~~java
await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("inventory-api"));
~~~

Awaitility sẽ thử lại assertion cho đến khi đạt hoặc hết thời gian chờ. Nếu output không xuất hiện, test fail với lỗi assertion thay vì dựa vào một khoảng ngủ cố định.

Tránh dùng `Thread.sleep(2000);`. Cách này làm test chậm ngay cả khi output xuất hiện sớm, đồng thời vẫn có thể không đủ thời gian trên máy chậm. Chờ theo điều kiện giúp test phản ánh trạng thái thực tế.

## 7. Chạy phiên interactive

Để kiểm thử REPL, dùng `interactive()`:

~~~java
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;

InteractiveShellSession session = client.interactive().run();
~~~

Sau khi khởi chạy, chờ prompt hoặc nội dung ban đầu xuất hiện:

~~~java
await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("shell"));
~~~

Gửi command `help` như người dùng nhập:

~~~java
session.write(
        session.writeSequence()
                .text("help")
                .carriageReturn()
                .build());
~~~

Sau đó chờ màn hình hiển thị danh sách command:

~~~java
await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("AVAILABLE COMMANDS"));
~~~

Đây là luồng được mô tả trong tài liệu Spring Shell 3.1.6: mở phiên interactive, chờ shell xuất hiện, gửi chuỗi phím và chờ nội dung mới.

### 7.1. Ví dụ test interactive hoàn chỉnh

~~~java
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void userCanOpenHelpFromInteractiveShell() {
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
~~~

`@DirtiesContext` yêu cầu Spring đóng và tạo lại ApplicationContext sau mỗi test method. Điều này hữu ích khi phiên interactive thay đổi trạng thái shell, history, command state hoặc các singleton bean.

Không cần dùng `@DirtiesContext` cho mọi test theo thói quen. Chỉ bật khi trạng thái test có thể ảnh hưởng đến test khác hoặc khi cần đóng phiên shell sau mỗi method.

## 8. ShellWriteSequence mô phỏng thao tác bàn phím

`session.writeSequence()` trả về `ShellWriteSequence`. Interface này tạo chuỗi ký tự và phím terminal để gửi vào session.

| Method | Mô phỏng |
|---|---|
| `text(String)` | Gõ văn bản |
| `carriageReturn()` | Nhấn Enter |
| `command(String)` | Gửi command và Enter |
| `space()` | Nhấn Space |
| `keyDown()` | Phím mũi tên xuống |
| `keyUp()` | Phím mũi tên lên |
| `keyLeft()` | Phím mũi tên trái |
| `keyRight()` | Phím mũi tên phải |
| `ctrl(char)` | Tổ hợp Ctrl với ký tự |
| `clearScreen()` | Gửi thao tác xóa màn hình |
| `build()` | Tạo chuỗi đầu vào hoàn chỉnh |

Có thể gửi command ngắn hơn bằng `command`:

~~~java
session.write(
        session.writeSequence()
                .command("help")
                .build());
~~~

Tương đương với:

~~~java
session.write(
        session.writeSequence()
                .text("help")
                .carriageReturn()
                .build());
~~~

Với component dạng selector, test có thể mô phỏng phím mũi tên và Enter:

~~~java
session.write(
        session.writeSequence()
                .keyDown()
                .carriageReturn()
                .build());
~~~

Số lần nhấn phím phụ thuộc vị trí mục được chọn mặc định và cách component được cấu hình. Hãy kiểm tra trạng thái màn hình sau từng bước để test không vô tình chọn mục khác.

Có thể nối nhiều thao tác trong một sequence, nhưng chỉ làm vậy khi flow đã sẵn sàng nhận chúng theo thứ tự. Nếu bước tiếp theo xuất hiện sau một tác vụ bất đồng bộ, nên gửi từng thao tác và chờ prompt tương ứng trước khi tiếp tục.

## 9. Kiểm tra command output với mock service

Một test shell thường chỉ cần kiểm tra command adapter, không cần database thật. Dùng mock service để trả dữ liệu xác định:

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.NonInteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectListCommandTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void listCommandDisplaysProjectSummary() {
        when(projectService.listProjects())
                .thenReturn(List.of(
                        new ProjectSummary("inventory-api", "ACTIVE")));

        NonInteractiveShellSession session =
                client.nonInterative("project", "list").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("inventory-api")
                        .containsText("ACTIVE"));
    }
}
~~~

Mock service giúp test tập trung vào ba điều:

1. Command đã được đăng ký.
2. Input của người dùng được chuyển tới command.
3. Kết quả service được trình bày trên màn hình.

Logic nghiệp vụ của service nên có unit test riêng. Không nên dùng một test shell duy nhất để chứng minh cả parser, business rules, database và terminal.

## 10. Kiểm thử option và lỗi parse

Spring Shell parse option trước khi gọi command method. Ví dụ method nhận ID kiểu `Long`:

~~~java
@ShellMethod(key = "project show", value = "Show a project.")
public String show(@ShellOption("--id") Long id) {
    return projectService.show(id);
}
~~~

Input hợp lệ:

~~~java
NonInteractiveShellSession session = client
        .nonInterative(
                "project", "show",
                "--id", "101")
        .run();
~~~

Input sai kiểu:

~~~java
NonInteractiveShellSession session = client
        .nonInterative(
                "project", "show",
                "--id", "abc")
        .run();
~~~

Khi không thể chuyển `abc` thành `Long`, lỗi phát sinh ở bước parse/conversion và command method có thể chưa được gọi.

Khi kiểm thử lỗi parse:

- Xác minh màn hình có thông báo lỗi hữu ích.
- Xác minh service không bị gọi nếu parser từ chối input trước khi gọi command.
- Không khóa test vào toàn bộ câu thông báo dài nếu framework có thể thay đổi wording.
- Dùng một đoạn thông báo ổn định hoặc kiểm tra hành vi ở ranh giới phù hợp.

Ví dụ nếu service được mock:

~~~java
verifyNoInteractions(projectService);
~~~

Đặt assertion này sau khi phiên non-interactive đã hoàn thành. Nếu cần kiểm tra output lỗi, dùng `ShellAssertions` với đoạn văn bản ổn định đã xác định từ phiên bản ứng dụng.

## 11. Kiểm tra exception và command không tồn tại

Nếu command phát sinh exception, Spring Shell đưa lỗi qua cơ chế result handling và exception resolver. Test có thể xác minh thông báo đã được hiển thị:

~~~java
NonInteractiveShellSession session = client
        .nonInterative("project", "show", "--id", "999")
        .run();

await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("Project 999 was not found"));
~~~

Ví dụ này giả định ứng dụng đã cấu hình resolver trả đúng thông báo đó. Nếu dùng resolver riêng, hãy test resolver ở unit test và kiểm thử tích hợp command để bảo đảm thông báo được đưa lên màn hình.

Spring Shell 3.1.6 có result handler mặc định cho command không tìm thấy:

~~~java
NonInteractiveShellSession session =
        client.nonInterative("missing-command").run();

await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("No command found"));
~~~

Nếu ứng dụng tùy biến `CommandNotFoundMessageProvider`, hãy kiểm tra thông báo do ứng dụng định nghĩa thay vì cố định thông điệp mặc định.

### 11.1. Phân biệt thông báo với mã thoát

`ShellAssertions` xác minh nội dung trên màn hình. `ShellTestClient` mô phỏng phiên shell và cung cấp screen/session. API session 3.1.x không phải một trình chạy tiến trình hệ điều hành để xác minh exit code thực tế của JVM hoặc mã trả về từ executable.

Nếu yêu cầu là kiểm tra exit code, cần chạy ứng dụng trong process riêng bằng công cụ kiểm thử tiến trình, ví dụ `ProcessBuilder`, rồi đọc `Process.exitValue()`. Không suy ra exit code của process chỉ từ việc màn hình chứa thông báo lỗi.

## 12. Kiểm thử bảng và output phụ thuộc chiều rộng terminal

Terminal giả lập của Spring Shell 3.1.6 mặc định có:

- Chiều rộng: 80 cột.
- Chiều cao: 24 dòng.

Có thể thay đổi bằng thuộc tính:

- `spring.shell.test.terminal-width`
- `spring.shell.test.terminal-height`

Hoặc khai báo trực tiếp trên `@ShellTest`:

~~~java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
class WideTerminalTests {
}
~~~

Cũng có thể dùng properties:

~~~java
@ShellTest(properties = {
        "spring.shell.test.terminal-width=120",
        "spring.shell.test.terminal-height=40"
})
class WideTerminalTests {
}
~~~

Đây là cách kiểm tra output có bảng, nội dung wrap hoặc nhiều dòng.

Ví dụ:

~~~java
@ShellTest(terminalWidth = 60, terminalHeight = 20)
class NarrowTerminalTests {

    @Autowired
    ShellTestClient client;

    @Test
    void projectListRemainsReadableOnNarrowTerminal() {
        NonInteractiveShellSession session =
                client.nonInterative("project", "list").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Project")
                        .containsText("inventory-api"));
    }
}
~~~

Nên kiểm tra những phần output cần còn nhìn thấy ở chiều rộng hẹp. Nếu cần xác minh chính xác độ wrap, tạo test riêng với dữ liệu và kích thước cố định.

Không nên giả định terminal giả lập luôn bằng terminal thật. Font, độ rộng ký tự Unicode, màu sắc, key binding và cách xử lý control sequence vẫn có thể khác giữa hệ điều hành hoặc terminal emulator.

## 13. Quản lý trạng thái test và vòng đời session

Một interactive session giữ trạng thái qua nhiều lệnh. Ví dụ:

- Lệnh trước đã kết nối tới server.
- History đã lưu command cũ.
- Component flow đang ở một bước nhập liệu.
- Bean singleton giữ thông tin lựa chọn.
- Màn hình đã có nội dung từ thao tác trước.

Nếu test dùng chung ApplicationContext, trạng thái của test trước có thể ảnh hưởng test sau.

Có thể dùng:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
~~~

để đóng context sau mỗi test method. Spring sẽ tạo context mới cho test tiếp theo khi cần.

Không nên dùng annotation này một cách máy móc cho mọi test vì việc tạo lại context có chi phí. Nếu test không thay đổi trạng thái dùng chung, có thể chia sẻ context và reset state bằng fixture hoặc setup method.

`ShellTestClient` triển khai `Closeable`/`AutoCloseable`. Khi tự tạo client bằng builder thay vì inject bean được cấu hình tự động, cần quản lý việc đóng client và terminal session đúng vòng đời. Với client được Spring inject trong test, để test context quản lý bean theo cấu hình.

## 14. Kiểm tra nội dung màn hình thay vì chuỗi terminal thô

Output terminal có thể chứa mã màu ANSI, điều khiển con trỏ, thao tác xóa màn hình, prompt thay đổi và nội dung bị wrap theo kích thước terminal.

Nếu kiểm tra raw output bằng một chuỗi dài, test dễ phụ thuộc vào môi trường.

Dùng:

~~~java
ShellAssertions.assertThat(session.screen())
        .containsText("inventory-api");
~~~

Cách này diễn đạt ý định test: người dùng có thể nhìn thấy nội dung cần thiết trên màn hình.

Nên tránh:

- So sánh toàn bộ màn hình với một file snapshot quá lớn.
- Kiểm tra escape sequence không phải hành vi sản phẩm cần bảo đảm.
- Kiểm tra prompt động hoặc timestamp.
- Dùng nhiều assertion cho khoảng trắng không có ý nghĩa.
- Kiểm tra thứ tự hiển thị nếu command không cam kết thứ tự đó.

Nếu thứ tự hàng là yêu cầu sản phẩm, hãy kiểm tra thứ tự ở service hoặc dữ liệu trả về; đồng thời kiểm tra một số điểm quan trọng của output CLI.

## 15. Kiểm tra command registration và cấu hình test slice

Một test shell chỉ có ý nghĩa khi command thực sự được đăng ký trong context. Nếu test báo không tìm thấy command, hãy kiểm tra:

1. Bean command có được component scan không?
2. Class có annotation hoặc registration đúng theo mô hình Spring Shell đang dùng không?
3. Test context có import cấu hình ứng dụng hoặc command bean cần thiết không?
4. Tên command trong test có khớp key đã đăng ký không?
5. Có command availability condition nào đang tắt command không?
6. Có interaction mode nào giới hạn command ở interactive hoặc non-interactive không?

Ví dụ dùng legacy annotation:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod(
            key = "project list",
            value = "List projects.")
    public String list() {
        return "inventory-api";
    }
}
~~~

Với mô hình command annotation mới hoặc programmatic registration, test vẫn dùng `ShellTestClient` để tương tác. Chỉ cách đăng ký command và cấu hình test context là khác nhau.

Không nên đổi registration model chỉ để test dễ hơn. Hãy cấu hình test theo đúng cách ứng dụng production đăng ký command.

## 16. Phân biệt các cấp độ kiểm thử

`ShellTestClient` phù hợp cho test tích hợp lớp giao diện shell. Không thay thế toàn bộ các loại test khác.

| Loại test | Mục tiêu | Công cụ phù hợp |
|---|---|---|
| Unit test command helper | Logic Java nhỏ trong command | JUnit |
| Unit test service | Quy tắc nghiệp vụ | JUnit, Mockito |
| Shell test non-interactive | Parse command, gọi command, output | `ShellTestClient` |
| Shell test interactive | Prompt, phím, flow, REPL | `ShellTestClient` + `ShellWriteSequence` |
| Repository test | Mapping và truy vấn dữ liệu | `@DataJpaTest` |
| Process integration test | Exit code, startup, shutdown, args JVM | `ProcessBuilder` hoặc test process |
| Packaging/native test | Artifact và môi trường thực tế | CI hoặc môi trường chạy tương ứng |

Một bộ test cân bằng thường có nhiều unit test cho nghiệp vụ và số lượng vừa đủ shell test cho các command quan trọng.

Không nên khởi chạy toàn bộ ứng dụng và terminal thật cho mỗi test nhỏ. Điều đó làm test chậm và khiến lỗi khó xác định.

## 17. Ví dụ tổng hợp: test command project

Giả sử command:

~~~java
@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod(
            key = "project list",
            value = "List projects.")
    public String list() {
        return projectService.listProjects().stream()
                .map(ProjectSummary::name)
                .collect(Collectors.joining("\n"));
    }
}
~~~

Test dùng mock service để cung cấp dữ liệu:

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.NonInteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ProjectCommandsTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void listCommandDisplaysServiceResults() {
        when(projectService.listProjects())
                .thenReturn(List.of(
                        new ProjectSummary("inventory-api", "ACTIVE"),
                        new ProjectSummary("billing-worker", "PAUSED")));

        NonInteractiveShellSession session =
                client.nonInterative("project", "list").run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() -> {
            ShellAssertions.assertThat(session.screen())
                    .containsText("inventory-api")
                    .containsText("billing-worker");
        });
    }
}
~~~

Test này kiểm tra việc đăng ký command, chạy command non-interactive, gọi service và hiển thị hai tên dự án.

Nếu test thất bại:

- Không tìm thấy command: xem registration và test context.
- Service không được gọi: xem command key, parser hoặc interaction mode.
- Output thiếu một tên: xem dữ liệu mock và logic format.
- Assertion timeout: xem command có hoàn thành và output có được cập nhật không.

## 18. Lỗi thường gặp khi dùng ShellTestClient

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy `@ShellTest` | Thiếu `spring-shell-test-autoconfigure` | Thêm dependency test đúng version |
| Không inject được `ShellTestClient` | Test không chạy trong Shell test context | Dùng `@ShellTest` và kiểm tra auto-configuration |
| Command không tồn tại | Bean hoặc registration chưa được nạp | Kiểm tra component scan, import và command key |
| Assertion chạy quá sớm | Shell cập nhật bất đồng bộ | Dùng Awaitility |
| Output không chứa text dù command đã chạy | Test đọc sai session hoặc dữ liệu đầu ra khác | Kiểm tra `session.screen()` và command output |
| Interactive test ảnh hưởng test sau | Context hoặc singleton giữ state | Dùng `@DirtiesContext` khi cần |
| Test bảng fail ở máy khác | Terminal width khác | Cấu hình `terminalWidth` và `terminalHeight` |
| Test phụ thuộc màu ANSI | So sánh raw control sequence | Dùng `ShellAssertions.containsText()` |
| `nonInteractive` không compile trên 3.1.x | API 3.1.x dùng tên `nonInterative` | Dùng đúng tên theo version |
| Test prompt bị treo | Chưa gửi Enter hoặc input tiếp theo | Dùng `ShellWriteSequence.carriageReturn()` |
| Test không kiểm tra được exit code process | Session test không đại diện process OS | Chạy executable trong process test riêng |
| Context test khởi động REPL ngoài ý muốn | Dùng `@SpringBootTest` không phù hợp hoặc runner chưa cấu hình | Ưu tiên `@ShellTest` cho shell component test |

## 19. Khác biệt tên API giữa Spring Shell 3.1.x và 3.4.2+

Tên method non-interactive là khác biệt dễ gặp nhất khi đọc ví dụ từ các version:

| Version | Method | Trạng thái |
|---|---|---|
| Spring Shell 3.1.x | `nonInterative(String...)` | Tên API được cung cấp |
| Spring Shell 3.4.2 trở lên | `nonInteractive(String...)` | Tên đã sửa |
| Spring Shell 3.4.2 trở lên | `nonInterative(String...)` | Deprecated, thay bằng `nonInteractive` |

Không sao chép method name từ tài liệu mới vào dự án 3.1.x nếu IDE báo không tồn tại. Tương tự, nếu dự án đã nâng lên version có method sửa chính tả, hãy ưu tiên API mới và xử lý cảnh báo deprecated.

Các phần chính còn lại vẫn có cùng vai trò: client chạy phiên, session đọc màn hình và write sequence gửi input. Tuy nhiên, luôn đối chiếu Javadoc đúng version khi cần kiểm tra chữ ký method hoặc import.

## 20. Bài thực hành: kiểm thử wizard tạo dự án

Tạo command hoặc flow có các bước:

- Chạy `project create`.
- Nhập tên dự án.
- Xác nhận thao tác.
- Hiển thị thông báo tạo thành công.

Yêu cầu:

1. Khai báo test class với `@ShellTest`.
2. Inject `ShellTestClient`.
3. Viết một test non-interactive cho command nhận đủ option.
4. Viết một test interactive để gửi input bằng `ShellWriteSequence`.
5. Dùng `ShellAssertions.assertThat(session.screen())` để kiểm tra thông báo.
6. Dùng Awaitility để chờ output.
7. Kiểm tra option sai kiểu hoặc dữ liệu không hợp lệ.
8. Kiểm tra trường hợp service ném exception và resolver hiển thị thông báo.
9. Thử terminal width 60 và 120 cột.
10. Dùng `@DirtiesContext` nếu test làm thay đổi trạng thái phiên.

Kịch bản mong đợi:

~~~text
shell:> project create --name inventory-api --owner platform
Created project inventory-api

shell:> project list
ID    Project
101   inventory-api
~~~

Test cần xác minh người dùng nhìn thấy tên dự án và thông báo thành công. Nếu yêu cầu còn bao gồm mã thoát của process, bổ sung một process integration test riêng.

## 21. Checklist trước khi hoàn thiện test

- [ ] Có `spring-shell-test` và `spring-shell-test-autoconfigure` đúng version.
- [ ] Dùng `@ShellTest` cho test tập trung vào command shell.
- [ ] Inject `ShellTestClient` từ test context.
- [ ] Chọn interactive hoặc non-interactive phù hợp với command.
- [ ] Spring Shell 3.1.x dùng `nonInterative(...)`.
- [ ] Gửi input tương tác bằng `ShellWriteSequence`.
- [ ] Đọc output qua `session.screen()`.
- [ ] Dùng `ShellAssertions.assertThat(...).containsText(...)`.
- [ ] Chờ output bất đồng bộ bằng Awaitility.
- [ ] Đặt terminal width/height rõ ràng cho test bố cục.
- [ ] Dùng `@DirtiesContext` khi trạng thái phiên cần được cô lập.
- [ ] Không phụ thuộc raw ANSI hoặc prompt động.
- [ ] Test parser error và exception theo thông báo ổn định.
- [ ] Kiểm thử service/domain ở lớp unit test riêng.
- [ ] Dùng process test riêng nếu cần xác minh exit code thật.
- [ ] Chạy test trên đúng dependency version trước khi nâng cấp Spring Shell.

## 22. Kết luận

`ShellTestClient` cho phép test tương tác với Spring Shell như một người dùng terminal: mở phiên interactive, chạy command non-interactive, gửi phím và đọc màn hình. `ShellScreen` biểu diễn output; `ShellAssertions.assertThat(screen).containsText(...)` giúp kiểm tra nội dung quan trọng mà không cần so sánh toàn bộ chuỗi terminal thô.

Trong Spring Shell 3.1.x, dùng `@ShellTest` từ package `org.springframework.shell.test.autoconfigure`, các API `ShellTestClient` và `ShellAssertions` từ `org.springframework.shell.test`. Chờ output bằng Awaitility vì shell có thể cập nhật bất đồng bộ; đặt terminal width/height rõ ràng khi kiểm tra bảng hoặc nội dung wrap.

Nhớ rằng `nonInterative` là tên method của nhánh 3.1.x; `nonInteractive` chỉ xuất hiện từ 3.4.2. Vì test client mô phỏng session thay vì khởi chạy process hệ điều hành, hãy dùng process integration test riêng cho exit code, startup và hành vi của artifact đã đóng gói.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Testing](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: ShellTestClient](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 3.1 API: ShellTestClient.InteractiveShellSession](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.InteractiveShellSession.html)
- [Spring Shell 3.1 API: ShellTestClient.NonInteractiveShellSession](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.NonInteractiveShellSession.html)
- [Spring Shell 3.1 API: ShellTestClient.BaseShellSession](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.BaseShellSession.html)
- [Spring Shell 3.1 API: ShellWriteSequence](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellWriteSequence.html)
- [Spring Shell 3.1 API: ShellScreen](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellScreen.html)
- [Spring Shell 3.1 API: ShellAssertions](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellAssertions.html)
- [Spring Shell 3.1 API: ShellScreenAssert](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellScreenAssert.html)
- [Spring Shell 3.1 API: ShellTest annotation](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 3.1 API: test package summary](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/package-summary.html)
- [Spring Shell 3.4.3 API: ShellTestClient](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.html)

