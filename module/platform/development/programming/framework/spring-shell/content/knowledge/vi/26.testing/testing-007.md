# Phiên interactive hoặc non-interactive qua API kiểm thử 3.x

Một command Spring Shell có thể được dùng theo hai cách. Người dùng có thể mở REPL, nhập nhiều lệnh và trả lời prompt trong một phiên interactive; hoặc chạy một command rồi kết thúc ngay trong chế độ non-interactive. Hai cách chạy có hành vi khác nhau, vì vậy bài kiểm thử cần tạo đúng loại phiên để mô phỏng cách ứng dụng được sử dụng.

Spring Shell 3.x cung cấp `ShellTestClient` để tạo phiên terminal giả lập. API này cho phép gửi phím và văn bản vào shell, đọc màn hình sau khi command chạy, và kiểm tra kết quả mà người dùng nhìn thấy. Với phiên non-interactive, client nhận command arguments rồi thực thi một lần. Với phiên interactive, client khởi động REPL và cho phép gửi nhiều dòng lệnh vào cùng phiên.

## 1. Chọn đúng loại kiểm thử

Trước khi viết test, hãy xác định điều cần xác minh:

| Mục tiêu | API phù hợp |
|---|---|
| Command chạy và trả output đúng | `ShellTestClient.nonInteractive(...)` |
| Prompt xuất hiện, người dùng nhập lệnh nhiều lần | `ShellTestClient.interactive()` |
| Lệnh tiếp tục hỏi input trong cùng phiên | Interactive session và `ShellWriteSequence` |
| Nhiều command trong một REPL | Một interactive session, gửi nhiều command |
| Cấu hình ứng dụng thật chọn runner đúng | Integration test với Spring Boot context |
| Mã thoát của tiến trình JVM/hệ điều hành | Chạy artifact trong tiến trình con và kiểm tra exit code |

`ShellTestClient` mô phỏng phiên terminal trong test. Nó hữu ích để kiểm tra cách shell nhận input và hiển thị output, nhưng bản thân nó không thay thế kiểm thử đóng gói hoặc mã thoát của tiến trình hệ điều hành.

## 2. Thêm dependency kiểm thử

Spring Shell chia test support thành hai module:

- `spring-shell-test`: API cốt lõi như `ShellTestClient`, `ShellScreen`, `ShellAssertions` và các session.
- `spring-shell-test-autoconfigure`: annotation `@ShellTest` và cấu hình tự động cho test context.

Với Maven, thêm các dependency ở scope `test`:

~~~xml
<dependencies>
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
</dependencies>
~~~

Nếu dự án dùng Spring Boot, `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, AssertJ và các tiện ích test phổ biến. Tài liệu Spring Shell dùng Awaitility để chờ shell cập nhật màn hình; kiểm tra dependency test của dự án để bảo đảm có thư viện này.

Không cần thêm các module test vào dependency runtime của ứng dụng CLI.

## 3. Tạo command dùng chung cho các ví dụ

Các ví dụ sau dùng một command đơn giản:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
class GreetingCommands {

    @ShellMethod(key = "hello", value = "Hiển thị lời chào")
    String hello() {
        return "Xin chào từ Spring Shell";
    }
}
~~~

`@ShellComponent` đăng ký bean chứa command; `@ShellMethod` khai báo command có tên `hello`. Khi test, chỉ cần nạp class này vào context là có thể chạy command qua `ShellTestClient`.

Với command cần service, hãy inject service như trong ứng dụng thật và mock dependency ở test boundary phù hợp. Test phiên shell nên tập trung vào việc command được phân tích, gọi và hiển thị đúng.

## 4. Dùng @ShellTest để tạo test context

`@ShellTest` cấu hình Spring test context tập trung vào các thành phần Spring Shell. Có thể chỉ định class chứa command bằng `@ContextConfiguration`:

~~~java
import org.springframework.test.context.ContextConfiguration;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = GreetingCommands.class)
class GreetingShellTests {
}
~~~

Annotation này tự đăng ký các cấu hình shell test và `ShellTestClient`. Trong test, inject client:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellTestClient;

@Autowired
ShellTestClient client;
~~~

Nếu command phụ thuộc vào bean khác, đưa cấu hình hoặc bean mock cần thiết vào test context. Khi test một ứng dụng lớn, dùng cấu hình test đủ để tạo command và các dependency liên quan thay vì khởi động hạ tầng không cần thiết.

## 5. Kiểm thử một command trong phiên non-interactive

Non-interactive session chạy một command dựa trên danh sách arguments truyền vào. Sau khi chạy, session cung cấp màn hình kết quả:

~~~java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.NonInteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.annotation.DirtiesContext;

@ShellTest
@ContextConfiguration(classes = GreetingCommands.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class NonInteractiveGreetingTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesCommandAndCapturesOutput() {
        NonInteractiveShellSession session =
                client.nonInteractive("hello").run();

        await().atMost(2, SECONDS).until(session::isComplete);

        ShellAssertions.assertThat(session.screen())
                .containsText("Xin chào từ Spring Shell");
    }
}
~~~

Quy trình:

1. Gọi `client.nonInteractive("hello")` để tạo session cho command.
2. Gọi `run()` để thực thi.
3. Chờ `session.isComplete()` vì runner và terminal giả lập hoạt động bất đồng bộ.
4. Đọc `session.screen()` và xác nhận nội dung bằng `ShellAssertions`.

Đối với command có option, truyền các token command và option vào varargs theo cú pháp mà command parser nhận. Ví dụ một command có option `--name` có thể được chạy với các arguments `hello`, `--name=Lan`.

Không nên đọc màn hình ngay sau `run()` rồi giả định mọi output đã xuất hiện. Hãy chờ điều kiện cần kiểm tra, với timeout hữu hạn để test không treo nếu command không hoàn tất.

## 6. Kiểm thử phiên interactive

Interactive session khởi động REPL. Test có thể chờ prompt xuất hiện, nhập một command, rồi tiếp tục nhập command khác trong cùng phiên:

~~~java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.annotation.DirtiesContext;

@ShellTest
@ContextConfiguration(classes = GreetingCommands.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveGreetingTests {

    @Autowired
    ShellTestClient client;

    @Test
    void acceptsCommandsInOneSession() {
        InteractiveShellSession session =
                client.interactive().run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));

        session.write(
                session.writeSequence()
                        .command("hello")
                        .build());

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Xin chào từ Spring Shell"));
    }
}
~~~

Ở đây:

- `interactive().run()` khởi động phiên REPL.
- `screen()` đọc nội dung terminal hiện tại.
- `writeSequence()` tạo chuỗi phím theo cách terminal hiểu.
- `command("hello")` thêm command cùng phím Enter.
- `write(...)` gửi chuỗi phím vào phiên đang chạy.

Có thể gửi nhiều command trong cùng một session:

~~~java
session.write(session.writeSequence().command("hello").build());
session.write(session.writeSequence().command("help").build());
~~~

Mỗi lần gửi input, hãy chờ nội dung tương ứng xuất hiện trước khi gửi thao tác tiếp theo nếu command trước có xử lý bất đồng bộ.

## 7. Gửi từng phím và mô phỏng câu trả lời prompt

`ShellWriteSequence` giúp xây dựng chuỗi thao tác terminal mà không phải tự mã hóa ký tự điều khiển:

| Phương thức | Hành động |
|---|---|
| `text("abc")` | Gửi văn bản |
| `carriageReturn()` hoặc `cr()` | Nhấn Enter |
| `command("hello")` | Gửi command và Enter |
| `keyUp()` / `keyDown()` | Nhấn mũi tên lên/xuống |
| `keyLeft()` / `keyRight()` | Di chuyển con trỏ |
| `ctrl('C')` | Gửi tổ hợp Ctrl |
| `space()` | Gửi phím cách |
| `clearScreen()` | Gửi thao tác xóa màn hình |
| `build()` | Tạo chuỗi ký tự cuối cùng |

Ví dụ, một command hỏi xác nhận trong phiên interactive:

~~~java
session.write(
        session.writeSequence()
                .text("yes")
                .carriageReturn()
                .build());
~~~

Nếu command hỏi nhiều lần, gửi từng câu trả lời theo đúng thứ tự và chờ prompt tiếp theo xuất hiện. Điều này giúp test xác nhận cả thứ tự câu hỏi lẫn kết quả cuối.

Ví dụ kiểm tra điều hướng history hoặc chỉnh sửa dòng:

~~~java
session.write(session.writeSequence().command("hello").build());
session.write(session.writeSequence().keyUp().build());
~~~

Chỉ kiểm tra hành vi phím cụ thể khi đó là yêu cầu sản phẩm. Với phần lớn command, test command parsing và kết quả nghiệp vụ sẽ ổn định hơn test toàn bộ chuỗi điều khiển terminal.

## 8. Kiểm thử command cần đọc input hoặc password

Một command có thể yêu cầu thêm dữ liệu trong lúc chạy, chẳng hạn xác nhận thao tác hoặc nhập giá trị chưa có trong arguments. Với Spring Shell 3.x, hãy chạy command trong interactive session, chờ prompt xuất hiện rồi gửi câu trả lời bằng `ShellWriteSequence`:

~~~java
session.write(
        session.writeSequence()
                .text("yes")
                .carriageReturn()
                .build());
~~~

Nếu command hỏi nhiều lần, gửi từng câu trả lời theo đúng thứ tự và chờ prompt tiếp theo trước khi gửi input kế tiếp. Với command đọc password, không đưa giá trị bí mật vào output hoặc assertion message.

API `ShellInputProvider` dùng để cung cấp trước input/password theo command xuất hiện trong tài liệu Spring Shell 4.0.2 trở lên; không sao chép API đó vào test Spring Shell 3.x nếu phiên bản đang dùng chưa cung cấp nó.

## 9. Kiểm tra ShellScreen và ShellAssertions

`ShellScreen` đại diện cho nội dung hiển thị trong terminal giả lập. Có thể kiểm tra nội dung bằng `ShellAssertions`:

~~~java
ShellAssertions.assertThat(session.screen())
        .containsText("AVAILABLE COMMANDS")
        .containsText("hello");
~~~

Khi cần kiểm tra chi tiết hơn, `ShellScreen.lines()` trả về danh sách dòng hiển thị:

~~~java
List<String> lines = session.screen().lines();

assertThat(lines)
        .anySatisfy(line -> assertThat(line).contains("Xin chào"));
~~~

Nên ưu tiên kiểm tra những nội dung có ý nghĩa với người dùng như kết quả, lỗi validation, trợ giúp và trạng thái command. Tránh so sánh toàn bộ màn hình theo một chuỗi cố định nếu output chứa prompt, khoảng trắng, màu ANSI hoặc nội dung thay đổi theo kích thước terminal.

## 10. Chờ shell hoàn tất thay vì dựa vào thời gian cố định

Terminal test có tính bất đồng bộ. Sau khi gửi input, shell có thể cần thời gian để phân tích command, gọi service, ghi output và cập nhật màn hình.

Dùng Awaitility để chờ điều kiện:

~~~java
await().atMost(2, SECONDS).untilAsserted(() ->
        ShellAssertions.assertThat(session.screen())
                .containsText("Hoàn tất"));
~~~

Với non-interactive session, chờ:

~~~java
await().atMost(2, SECONDS).until(session::isComplete);
~~~

Với interactive session, shell không kết thúc sau một command; vì vậy chờ nội dung mong muốn thay vì chờ `isComplete()` trở thành `true`.

Không dùng `Thread.sleep(...)` với một khoảng thời gian tùy ý để đồng bộ test. Máy CI có thể chạy chậm hoặc nhanh hơn máy phát triển, khiến test khi thì thất bại, khi thì chạy lâu không cần thiết.

## 11. Cô lập phiên interactive giữa các test

Interactive shell giữ một runner đang chờ input. Nếu test kết thúc nhưng context được tái sử dụng, session cũ có thể làm ảnh hưởng đến test sau hoặc giữ tài nguyên.

Tài liệu Spring Shell dùng:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
~~~

Annotation này đánh dấu context cần được đóng và tạo lại sau mỗi test method. Đây là lựa chọn phù hợp khi test khởi chạy một interactive session và cần cô lập vòng đời của shell.

Không nhất thiết phải áp dụng `@DirtiesContext` cho mọi unit test không khởi chạy session. Chỉ dùng nó ở test cần đóng context để dọn runner hoặc tài nguyên gắn với phiên.

## 12. Cấu hình kích thước terminal giả lập

Terminal test có kích thước mặc định rộng 80 cột và cao 24 dòng. Nếu command hiển thị bảng dài hoặc output bị wrap, hãy đặt kích thước phù hợp:

~~~java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
@ContextConfiguration(classes = GreetingCommands.class)
class WideTerminalTests {
}
~~~

Hoặc đặt property:

~~~java
@ShellTest(properties = {
        "spring.shell.test.terminal-width=120",
        "spring.shell.test.terminal-height=40"
})
class WideTerminalTests {
}
~~~

Chỉ tăng kích thước khi test thực sự cần kiểm tra layout ở kích thước đó. Nếu không, nên giữ kích thước mặc định để phát hiện sớm lỗi wrap trên terminal thông thường.

## 13. Phân biệt nonInteractive session với cấu hình runner thật

Hai API sau có mục đích liên quan nhưng khác phạm vi:

| Cách chạy | Phạm vi |
|---|---|
| `client.nonInteractive("hello").run()` | Tạo một non-interactive test session qua `ShellTestClient` |
| `spring.shell.interactive.enabled=false` | Cấu hình ứng dụng Spring Boot dùng `NonInteractiveShellRunner` khi khởi động |

Khi cần kiểm tra ứng dụng thực sự chọn runner non-interactive từ cấu hình, hãy dùng integration test với Spring Boot context và property tương ứng. Ví dụ cấu hình:

~~~properties
spring.shell.interactive.enabled=false
~~~

`@ShellTest` phù hợp để kiểm tra command và phiên terminal trong môi trường kiểm thử. Nếu cần xác nhận toàn bộ startup path, hãy bổ sung test khởi động ứng dụng bằng cấu hình và arguments giống môi trường triển khai.

## 14. Kiểm tra mã thoát của tiến trình thật

`ShellTestClient.NonInteractiveShellSession` giúp kiểm tra command hoàn tất và output hiển thị. Nó không thay thế việc kiểm tra mã thoát của một tiến trình JVM được khởi chạy như chương trình độc lập.

Khi mã thoát là hợp đồng với script hoặc CI, hãy chạy artifact đã build trong tiến trình con:

~~~java
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

Process process = new ProcessBuilder(
        "java",
        "-jar",
        "build/libs/admin-cli.jar",
        "hello"
).redirectErrorStream(true).start();

String output;
try (var input = process.getInputStream()) {
    output = new String(input.readAllBytes(), StandardCharsets.UTF_8);
}

int exitCode = process.waitFor();

assertThat(exitCode).isZero();
assertThat(output).contains("Xin chào");
~~~

Ví dụ này là kiểm thử ở cấp tiến trình. Để kiểm tra trường hợp lỗi, dùng một command có thể thất bại và xác nhận mã khác `0` theo quy ước ứng dụng. Cần cấu hình non-interactive mode trong ứng dụng nếu command được truyền qua arguments khi startup.

## 15. Test slice, integration test và end-to-end test

Chọn phạm vi test theo câu hỏi cần trả lời:

| Loại test | Cách tạo | Phù hợp để kiểm tra |
|---|---|---|
| Unit test service | JUnit và mock dependency | Quy tắc nghiệp vụ, validation, lỗi |
| Shell test | `@ShellTest` và `ShellTestClient` | Command registration, parsing, prompt, output |
| Spring Boot integration test | `@SpringBootTest` | Auto-configuration, properties và wiring toàn ứng dụng |
| Process-level end-to-end | `ProcessBuilder` chạy JAR | Startup, command arguments, output stream và exit code |

Không cần dùng process-level test cho mọi command. Dùng `ShellTestClient` để kiểm tra nhiều command nhanh trong cùng test suite; dành process-level test cho những yêu cầu phụ thuộc vào cách ứng dụng khởi động hoặc kết thúc.

Tài liệu Spring Shell 3.4 lưu ý test support vẫn đang được phát triển và một số phần có thể chưa ổn định. Giữ test tập trung vào hành vi command và nội dung có ý nghĩa; tránh phụ thuộc quá chặt vào mọi ký tự hoặc cách terminal giả lập bố trí màn hình.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test đọc màn hình trước khi có output | Runner xử lý bất đồng bộ | Chờ bằng Awaitility |
| Interactive session ảnh hưởng test tiếp theo | Context hoặc runner chưa được đóng | Dùng `@DirtiesContext` cho test cần cô lập session |
| Non-interactive session không kết thúc | Command chờ input hoặc tác vụ chưa hoàn tất | Cung cấp input cần thiết và kiểm tra điều kiện kết thúc |
| Prompt không giống chuỗi mong đợi | Prompt provider hoặc cấu hình ứng dụng đã thay đổi | Kiểm tra prompt theo nội dung ổn định hoặc cấu hình prompt rõ ràng |
| Output bị wrap khác dự kiến | Kích thước terminal test khác môi trường | Đặt `terminalWidth`/`terminalHeight` phù hợp |
| So sánh màn hình thất bại dù nội dung đúng | Ký tự điều khiển, ANSI hoặc khoảng trắng | Dùng `ShellAssertions.containsText` hoặc kiểm tra từng dòng |
| `nonInterative` bị cảnh báo deprecated | Dùng tên method cũ | Dùng `nonInteractive` từ Spring Shell 3.4.2 |
| Test cần `ShellInputProvider` nhưng không tìm thấy API | Sao chép API từ Spring Shell 4.x vào 3.x | Dùng interactive session và `ShellWriteSequence` |
| Shell test pass nhưng ứng dụng thật chạy sai mode | Chưa kiểm tra cấu hình startup runner | Thêm integration test với property thực tế |
| Shell test pass nhưng CI nhận sai exit code | Chưa kiểm tra tiến trình JVM | Thêm process-level test cho artifact |
| Test chạy không ổn định giữa các hệ điều hành | Phụ thuộc phím terminal hoặc định dạng màn hình | Chỉ test hành vi terminal thiết yếu và tránh snapshot quá chặt |

## 17. Checklist kiểm thử hai chế độ

Trước khi hoàn thành test cho một command, kiểm tra:

1. Test context có `@ShellTest` và nạp đúng command bean.
2. Non-interactive test gọi `nonInteractive(...)`, chờ session hoàn tất và xác nhận output.
3. Interactive test khởi chạy REPL, chờ prompt, gửi command bằng `ShellWriteSequence` và xác nhận output.
4. Nếu command hỏi input, test cung cấp câu trả lời theo đúng thứ tự.
5. Nếu command chạy bất đồng bộ, test chờ kết quả thay vì dựa vào thời gian cố định.
6. Interactive session được cô lập khỏi test method tiếp theo.
7. Kích thước terminal được đặt rõ khi test phụ thuộc layout.
8. Không dùng test session để kết luận về mã thoát của JVM.
9. Có integration test nếu cần xác minh runner được chọn theo property startup.
10. Có process-level test nếu exit code là hợp đồng của script hoặc CI.

## 18. Bài tập thực hành

Tạo hai command:

- `hello`: in lời chào và nhận một option `--name`.
- `confirm-delete`: yêu cầu người dùng xác nhận trước khi xóa dữ liệu giả lập.

Viết test:

1. Dùng `@ShellTest` để nạp command bean.
2. Dùng `nonInteractive("hello", "--name=Lan")` để kiểm tra output một lần.
3. Dùng `interactive().run()` để kiểm tra prompt và gửi command `hello`.
4. Gửi câu trả lời xác nhận qua `ShellWriteSequence` và kiểm tra nhánh đồng ý.
5. Gửi câu trả lời từ chối và xác nhận service xóa không được gọi.
6. Dùng Awaitility để chờ output sau khi command xử lý.
7. Cô lập interactive session bằng `@DirtiesContext`.
8. Nếu ứng dụng được dùng trong CI, chạy JAR ở non-interactive mode và kiểm tra mã thoát cho trường hợp thành công lẫn thất bại.

Sau khi hoàn thành, hãy giải thích được khác biệt giữa interactive session, non-interactive session của `ShellTestClient`, runner được cấu hình khi ứng dụng khởi động và tiến trình JVM thật.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Testing Basics](https://docs.spring.io/spring-shell/reference/3.4/testing/basics.html)
- [Spring Shell 3.4 – Testing Settings](https://docs.spring.io/spring-shell/reference/3.4/testing/settings.html)
- [Spring Shell 3.4.3 API – ShellTestClient](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 3.4.3 API – InteractiveShellSession](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.InteractiveShellSession.html)
- [Spring Shell 3.4.3 API – NonInteractiveShellSession](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.NonInteractiveShellSession.html)
- [Spring Shell 3.4 API – ShellWriteSequence](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/test/ShellWriteSequence.html)
- [Spring Shell 3.4 API – ShellAssertions](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/test/ShellAssertions.html)
- [Spring Shell 3.4 – Execution Modes](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
