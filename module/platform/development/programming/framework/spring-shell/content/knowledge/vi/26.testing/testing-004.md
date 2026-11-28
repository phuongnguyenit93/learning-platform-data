# Vai trò của môđun spring-shell-test và cấu hình kiểm thử tương ứng

Kiểm thử ứng dụng CLI có một điểm khác với kiểm thử service thông thường: đầu vào đi qua command parser và terminal, còn kết quả hiển thị trên màn hình có thể chứa prompt, ký tự điều khiển, màu sắc và xuống dòng. Chỉ gọi trực tiếp phương thức Java của command sẽ không kiểm tra được cách Spring Shell phân tích lệnh hoặc hiển thị kết quả.

Spring Shell 3.4 cung cấp hai môđun hỗ trợ kiểm thử. `spring-shell-test` chứa client và các kiểu dữ liệu để mô phỏng phiên shell, đọc màn hình và xác nhận kết quả. `spring-shell-test-autoconfigure` cung cấp cấu hình Spring Test cùng annotation `@ShellTest`, giúp dựng shell test context. Kết hợp với `spring-boot-starter-test`, chúng tạo nền tảng để kiểm tra command theo cách người dùng thực sự gọi.

## 1. Vai trò của spring-shell-test

Môđun `spring-shell-test` cung cấp các API chính:

| Thành phần | Vai trò |
| --- | --- |
| `ShellTestClient` | Mô phỏng người dùng gọi command hoặc thao tác với shell tương tác |
| `ShellScreen` | Đại diện cho nội dung nhìn thấy trên terminal |
| `ShellAssertions` | Cung cấp assertion chuyên biệt cho `ShellScreen` |
| `InteractiveShellSession` | Chạy phiên shell tương tác và gửi phím/ký tự vào terminal |
| `NonInteractiveShellSession` | Chạy command theo chế độ không tương tác |
| `ShellWriteSequence` | Xây dựng chuỗi phím và thao tác terminal để gửi vào phiên shell |

`ShellTestClient` giúp kiểm tra đường đi từ command line text qua parser, command registry, command invocation đến output. Nó cho phép gửi lệnh, đọc màn hình và mô phỏng thao tác bàn phím mà không cần người kiểm thử gõ trực tiếp trong terminal thật.

## 2. Vai trò của spring-shell-test-autoconfigure

Môđun `spring-shell-test-autoconfigure` bổ sung phần tích hợp với Spring Test:

- Annotation `@ShellTest` khởi tạo test context dành cho các thành phần Spring Shell.
- Tự động cấu hình shell và `ShellTestClient`.
- Cung cấp các thuộc tính để đặt chiều rộng và chiều cao terminal giả lập.
- Cho phép giới hạn hoặc mở rộng bean được đưa vào test context thông qua các bộ lọc component.

`@ShellTest` phù hợp cho kiểm thử tập trung vào command và thành phần shell. Nếu test cần toàn bộ hạ tầng của ứng dụng, hãy cấu hình context phù hợp và cân nhắc một integration test riêng.

## 3. Khai báo dependency kiểm thử

Với Maven, import Spring Shell BOM để các artifact cùng dùng một phiên bản. Ví dụ dùng Spring Shell 3.4.3:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.shell</groupId>
            <artifactId>spring-shell-dependencies</artifactId>
            <version>3.4.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, Mockito và AssertJ. Phiên bản Spring Boot nên được quản lý bằng parent hoặc BOM của ứng dụng; không tự ghép các phiên bản Spring Boot và Spring Shell không tương thích.

Với Gradle:

```groovy
dependencies {
    testImplementation platform("org.springframework.shell:spring-shell-dependencies:3.4.3")
    testImplementation "org.springframework.shell:spring-shell-test"
    testImplementation "org.springframework.shell:spring-shell-test-autoconfigure"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
```

Đặt các dependency này trong test scope để công cụ kiểm thử không đi vào runtime artifact của CLI.

## 4. Tạo command mẫu để kiểm thử

Ví dụ ứng dụng có command `greet` nhận tên người dùng:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@SpringBootApplication
@ShellComponent
public class GreetingShellApplication {

    @ShellMethod(key = "greet", value = "Chào một người dùng")
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Command trả về một chuỗi để Spring Shell hiển thị. Khi kiểm thử, ta gửi lệnh `greet Lan` qua `ShellTestClient` và xác nhận màn hình có nội dung `Xin chào, Lan!`.

Ví dụ dùng programming model `@ShellComponent` và `@ShellMethod` của Spring Shell 3.4. Nếu ứng dụng dùng command registration theo kiểu khác, giữ nguyên command thật và cấu hình test theo đúng kiểu đăng ký đó.

## 5. Tạo test context bằng @ShellTest

`@ShellTest` được khai báo trong package `org.springframework.shell.test.autoconfigure`. Kết hợp với `@ContextConfiguration` để chỉ rõ cấu hình ứng dụng cần nạp:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = GreetingShellApplication.class)
class GreetingCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void greetsTheRequestedUser() {
        var session = client
                .nonInteractive("greet", "Lan")
                .run();

        ShellAssertions.assertThat(session.screen())
                .containsText("Xin chào, Lan!");
    }
}
```

Test context sẽ nạp cấu hình shell và cung cấp `ShellTestClient`. Không cần khởi chạy terminal thật hoặc tự tạo `CommandParser` và `CommandRegistry` cho trường hợp thông thường.

`@ShellTest` có các bộ lọc component để giới hạn bean được nạp. Nếu command không xuất hiện trong test, hãy kiểm tra lớp cấu hình được chỉ định, package scan và các `includeFilters`/`excludeFilters`.

## 6. Kiểm thử command không tương tác

Command không tương tác phù hợp với script và CI. Dùng `nonInteractive(...)` để truyền command cùng các token đối số, sau đó gọi `run()`:

```java
@Test
void executesNonInteractiveCommand() {
    var session = client
            .nonInteractive("greet", "Lan")
            .run();

    ShellAssertions.assertThat(session.screen())
            .containsText("Xin chào, Lan!");
}
```

Có thể kiểm tra thêm đầu vào khác:

```java
@Test
void displaysTheResultForAnotherName() {
    var session = client
            .nonInteractive("greet", "Minh")
            .run();

    ShellAssertions.assertThat(session.screen())
            .containsText("Xin chào, Minh!");
}
```

`nonInteractive(String...)` là tên phương thức đúng từ Spring Shell 3.4.2. API cũ có lỗi chính tả `nonInterative(...)` đã deprecated; với 3.4.3, hãy dùng `nonInteractive(...)`.

## 7. Đọc và xác nhận ShellScreen

`ShellTestClient` trả về session; gọi `screen()` để lấy `ShellScreen`. Có thể xác nhận bằng `ShellAssertions.assertThat(...)`:

```java
ShellScreen screen = session.screen();

ShellAssertions.assertThat(screen)
        .containsText("Xin chào, Lan!");
```

`ShellScreen` đại diện cho các dòng hiển thị trên terminal và cung cấp `lines()` để kiểm tra từng dòng:

```java
assertThat(screen.lines())
        .anySatisfy(line -> assertThat(line).contains("Xin chào, Lan!"));
```

`ShellAssertions` bổ sung assertion theo ngữ nghĩa shell, ví dụ `containsText(...)`. Nên xác nhận nội dung quan trọng thay vì so sánh toàn bộ màn hình theo chuỗi tuyệt đối nếu prompt, khoảng trắng hoặc cách wrap không phải mục tiêu của test.

## 8. Kiểm thử phiên shell tương tác

Với command cần người dùng gõ lệnh, gọi `interactive().run()` để tạo một phiên tương tác. Sau đó gửi chuỗi phím qua `writeSequence()`:

```java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;

import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.annotation.DirtiesContext.ClassMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = GreetingShellApplication.class)
@DirtiesContext(classMode = ClassMode.AFTER_EACH_TEST_METHOD)
class InteractiveShellTests {

    @Autowired
    ShellTestClient client;

    @Test
    void acceptsACommandFromTheInteractiveSession() {
        InteractiveShellSession session = client.interactive().run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("shell"));

        session.write(
                session.writeSequence()
                        .text("help")
                        .carriageReturn()
                        .build());

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("AVAILABLE COMMANDS"));
    }
}
```

Phiên tương tác chạy bất đồng bộ. Sau khi gửi phím, terminal có thể cần thêm thời gian để xử lý command và cập nhật màn hình. Dùng Awaitility để đợi điều kiện mong muốn thay vì đọc screen ngay lập tức rồi giả định output đã hoàn tất.

Tài liệu Spring Shell dùng `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` trong ví dụ interactive test để làm mới Spring context sau mỗi test. Cách này hữu ích khi phiên shell hoặc trạng thái terminal có thể ảnh hưởng đến test kế tiếp. Không cần áp dụng cho mọi test đơn giản nếu chúng không làm thay đổi context.

## 9. Tạo chuỗi phím bằng ShellWriteSequence

`ShellWriteSequence` giúp mô tả thao tác bàn phím theo từng bước:

```java
session.write(
        session.writeSequence()
                .text("greet Lan")
                .carriageReturn()
                .build());
```

Các thao tác thường dùng:

| Thao tác | Mục đích |
| --- | --- |
| `text(...)` | Gửi chuỗi ký tự |
| `carriageReturn()` | Nhấn Enter để thực thi dòng hiện tại |
| `build()` | Hoàn tất chuỗi thao tác để gửi vào session |

Có thể ghép nhiều thao tác để kiểm tra command history, help, completion hoặc prompt tương tác. Khi test phụ thuộc thời gian xử lý, vẫn nên đợi screen đạt trạng thái mong đợi bằng Awaitility.

## 10. Cấu hình kích thước terminal giả lập

Terminal emulation mặc định có chiều rộng 80 cột và chiều cao 24 dòng. Nếu command render bảng hoặc nội dung dài, hãy đặt kích thước phù hợp với tình huống kiểm thử.

Có thể cấu hình trực tiếp trên `@ShellTest`:

```java
@ShellTest(terminalWidth = 120, terminalHeight = 40)
@ContextConfiguration(classes = GreetingShellApplication.class)
class WideTerminalTests {
}
```

Hoặc truyền property:

```java
@ShellTest(properties = {
        "spring.shell.test.terminal-width=120",
        "spring.shell.test.terminal-height=40"
})
class TerminalDimensionTests {
}
```

Kiểm thử nhiều kích thước giúp phát hiện output tràn cột, bảng bị wrap ngoài ý muốn hoặc nội dung bị đẩy khỏi vùng nhìn thấy. Có thể tạo test cho 60, 80 và 120 cột tùy layout ứng dụng hỗ trợ.

## 11. Kiểm tra command parsing và kết quả nghiệp vụ

`ShellTestClient` chạy command thông qua hạ tầng shell nên có thể kiểm tra các tình huống mà unit test gọi trực tiếp method không bao phủ:

- Tên command và alias được đăng ký đúng.
- Argument được chuyển tới đúng tham số.
- Option, giá trị mặc định và kiểu dữ liệu được parse đúng.
- Command trả output mong đợi.
- Validation hoặc lỗi nghiệp vụ được chuyển thành thông báo phù hợp.
- Command không tồn tại hoặc cách gọi sai được xử lý theo cấu hình shell.

Nên kiểm tra cả đường đi thành công và thất bại. Với lỗi, xác nhận thông báo hoặc hành vi công khai mà người dùng nhìn thấy; không khóa test vào stack trace hoặc chi tiết nội bộ của exception nếu đó không phải hợp đồng CLI.

## 12. Kiểm thử command có dependency

Command thường gọi service để truy vấn dữ liệu hoặc thực hiện nghiệp vụ. Tách logic nghiệp vụ vào service giúp có thể kiểm thử riêng:

| Lớp | Phạm vi kiểm thử |
| --- | --- |
| Service | Quy tắc nghiệp vụ, validation, gọi repository/API và xử lý lỗi |
| Command | Nhận tham số, gọi đúng service, chuyển kết quả thành output |
| Spring Shell integration | Parsing, registration, output và tương tác terminal |

Trong test command, có thể thay dependency bằng mock hoặc fake bean để không gọi database, mạng hoặc hệ thống thật. Sau đó xác nhận command truyền đúng tham số và hiển thị kết quả service trả về.

Không nên dùng `ShellTestClient` để kiểm tra mọi nhánh nội bộ của service. Những nhánh đó thuộc unit test của service; shell integration test nên tập trung vào hợp đồng giữa người dùng và command.

## 13. Kiểm thử component và giao diện terminal

Các component như input, selector, `ComponentFlow` hoặc view tương tác cần kiểm thử theo hành vi:

- Component hiển thị prompt hoặc tiêu đề đúng.
- Người dùng nhập hoặc chọn dữ liệu thì context nhận đúng kết quả.
- Hủy thao tác không gọi service ghi dữ liệu.
- Chuyển nhánh flow đi tới đúng component tiếp theo.
- Terminal hẹp vẫn hiển thị thông tin cần thiết.

Với interactive component, dùng session tương tác và chuỗi phím để mô phỏng thao tác. Không chỉ xác nhận text ban đầu; cần gửi phím lựa chọn, Enter hoặc hủy rồi xác nhận kết quả cuối cùng. Với TUI phức tạp hoặc phụ thuộc đặc tính terminal thật, bổ sung integration test bằng pseudo-terminal hoặc terminal emulator.

## 14. Phân biệt Shell test với unit test và end-to-end test

Mỗi tầng kiểm thử trả lời một câu hỏi khác nhau:

| Tầng | Công cụ | Câu hỏi |
| --- | --- | --- |
| Unit test | JUnit, Mockito, AssertJ | Service hoặc helper có xử lý đúng quy tắc không? |
| Shell integration test | `@ShellTest`, `ShellTestClient` | Người dùng gọi command có nhận đúng kết quả không? |
| Application integration test | Spring Boot Test, test database hoặc fake service | Các bean và cấu hình của ứng dụng có phối hợp đúng không? |
| Process end-to-end | Chạy JAR/native executable trong tiến trình riêng | Artifact thực tế có khởi động, nhận args và trả mã thoát đúng không? |

`spring-shell-test` chủ yếu hỗ trợ kiểm thử ở tầng shell integration. Nó không tự chứng minh JAR đóng gói đúng, biến môi trường hệ điều hành được đọc đúng hoặc tiến trình trả mã thoát mà CI mong đợi. Những hành vi đó cần test ở cấp ứng dụng hoặc tiến trình.

## 15. Giới hạn và lưu ý khi kiểm thử terminal

Kiểm thử CLI có thể khác nhau giữa hệ điều hành và shell. Output terminal có thể chứa ký tự điều khiển, màu, khoảng trắng và cập nhật bất đồng bộ. Một màn hình nhìn thấy trong terminal thật không nhất thiết tương ứng với một chuỗi đơn giản.

Một số nguyên tắc:

- Ưu tiên `ShellAssertions.containsText(...)` cho nội dung quan trọng.
- Chỉ kiểm tra toàn bộ `lines()` khi cấu trúc dòng là yêu cầu rõ ràng.
- Dùng Awaitility cho output cập nhật bất đồng bộ.
- Cố định terminal width/height khi test layout.
- Không phụ thuộc vào màu ANSI nếu màu không phải hợp đồng cần kiểm tra.
- Không gọi endpoint production hoặc database dùng chung từ test.
- Dùng fake clock, dữ liệu mẫu hoặc mock để tránh test phụ thuộc thời gian và môi trường.
- Tách test terminal giả lập khỏi test process/OS thật.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không inject được `ShellTestClient` | Thiếu `spring-shell-test-autoconfigure` hoặc `@ShellTest` | Kiểm tra dependency và annotation |
| Command không xuất hiện trong test | Test context không nạp lớp command hoặc bị filter | Kiểm tra `@ContextConfiguration`, component scan và include/exclude filters |
| Output rỗng ngay sau khi gửi phím | Session chưa xử lý xong input | Dùng Awaitility chờ nội dung xuất hiện |
| Test interactive ảnh hưởng test sau | Context/session còn trạng thái | Dùng `@DirtiesContext` khi test làm thay đổi context |
| Bảng bị wrap khác dự kiến | Kích thước terminal giả lập không khớp | Cấu hình `terminalWidth` và `terminalHeight` |
| Test phụ thuộc màu terminal | Assertion so sánh escape sequence | Xác nhận nội dung nhìn thấy thay vì chuỗi ANSI thô |
| Dùng sai API test client | Sao chép ví dụ từ Spring Shell 4.x | Với 3.4.3 dùng `interactive()` và `nonInteractive(...)` |
| Test gọi dịch vụ thật | Command phụ thuộc bean thật không được thay thế | Dùng mock/fake bean hoặc cấu hình test chuyên biệt |

## 17. Bài thực hành tổng hợp

Tạo test suite cho CLI quản lý project:

1. Thêm `spring-shell-test`, `spring-shell-test-autoconfigure` và `spring-boot-starter-test` trong test scope.
2. Import BOM Spring Shell 3.4.3 để quản lý phiên bản dependency.
3. Tạo test context có command `project status`.
4. Dùng `@ShellTest` và `ShellTestClient` để gọi command không tương tác.
5. Kiểm tra output với `ShellAssertions`.
6. Tạo test interactive, gửi `help` bằng `ShellWriteSequence` và chờ screen cập nhật.
7. Đặt terminal width 60 và 120 để kiểm tra bảng hiển thị.
8. Thay service thật bằng mock/fake để test command không gọi hệ thống bên ngoài.
9. Kiểm thử đầu vào sai, project không tồn tại và lỗi service.
10. Tạo một test riêng chạy JAR để xác nhận command line arguments và process exit code.

## 18. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Module roles | Phân biệt `spring-shell-test` và `spring-shell-test-autoconfigure` |
| Dependencies | Khai báo đúng dependency test scope và quản lý phiên bản bằng BOM |
| Test context | Tạo context bằng `@ShellTest` và `@ContextConfiguration` |
| Non-interactive | Gọi command bằng `ShellTestClient.nonInteractive(...)` |
| Interactive | Gửi phím qua `InteractiveShellSession` và `ShellWriteSequence` |
| Assertions | Đọc `ShellScreen` và xác nhận nội dung bằng `ShellAssertions` |
| Async behavior | Chờ output bằng Awaitility khi cần |
| Terminal settings | Kiểm tra nhiều chiều rộng và chiều cao |
| Isolation | Quản lý context/session state giữa các test |
| Test layers | Phân biệt unit, shell integration, application integration và process E2E |

## Tài liệu tham khảo

- [Spring Shell 3.4 — Testing Basics](https://docs.spring.io/spring-shell/reference/3.4/testing/basics.html)
- [Spring Shell 3.4 — Testing Settings](https://docs.spring.io/spring-shell/reference/3.4/testing/settings.html)
- [Spring Shell 3.4.3-SNAPSHOT — ShellTest API](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 3.4.3-SNAPSHOT — ShellTestClient API](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 3.4.3-SNAPSHOT — ShellAssertions API](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellAssertions.html)
- [Spring Framework — DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html)
