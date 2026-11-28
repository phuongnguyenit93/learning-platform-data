# sendCommand và ShellScreen trong API kiểm thử 4.x

Khi kiểm thử một ứng dụng Spring Shell, cần xác nhận command có thể được phân tích, thực thi và tạo ra nội dung đúng như người dùng nhìn thấy. Spring Shell 4.x cung cấp **ShellTestClient** để gửi command bằng chuỗi hoặc mô phỏng dữ liệu nhập, và **ShellScreen** để giữ các dòng đầu ra sau khi command chạy xong. **ShellAssertions** bổ sung assertion chuyên biệt để kiểm tra nội dung màn hình.

Ba API này tạo thành một luồng kiểm thử gọn:

1. Gọi **sendCommand(...)** để thực thi command trong test context.
2. Nhận **ShellScreen** chứa các dòng hiển thị.
3. Dùng **ShellAssertions.assertThat(screen).containsText(...)** hoặc đọc **screen.lines()** để xác nhận kết quả.

API **sendCommand(ShellInputProvider)** có từ Spring Shell 4.0.2. Bài viết tập trung vào API 4.x, đặc biệt phiên bản 4.0.3. Khi nâng cấp từ 3.x, cần cập nhật cách mô phỏng phiên tương tác vì bộ test API đã được thiết kế lại.

## 1. Các thành phần kiểm thử chính

Các lớp kiểm thử nằm trong package **org.springframework.shell.test**; annotation cấu hình nằm trong **org.springframework.shell.test.autoconfigure**.

| Thành phần | Package | Vai trò |
| --- | --- | --- |
| **ShellTestClient** | org.springframework.shell.test | Gửi command vào shell và nhận màn hình sau khi thực thi |
| **ShellScreen** | org.springframework.shell.test | Record chứa danh sách dòng đầu ra |
| **ShellAssertions** | org.springframework.shell.test | Điểm bắt đầu cho assertion trên màn hình |
| **ShellScreenAssert** | org.springframework.shell.test | Assertion như containsText(...) |
| **ShellInputProvider** | org.springframework.shell.test | Cung cấp trước input và password để mô phỏng câu trả lời |
| **@ShellTest** | org.springframework.shell.test.autoconfigure | Thiết lập Spring test context cho kiểm thử shell |
| **ShellTestClientAutoConfiguration** | org.springframework.shell.test.autoconfigure | Cung cấp các bean hỗ trợ client và command registry |

**@ShellTest** được meta-annotate với **@ExtendWith(SpringExtension.class)** và import **ShellTestClientAutoConfiguration**. Vì vậy, test dùng annotation này có thể inject **ShellTestClient** mà không cần tự tạo **CommandParser** hoặc **CommandRegistry**.

## 2. Thêm dependency kiểm thử

Spring Shell tách API test và phần auto-configuration thành hai artifact:

- **spring-shell-test**: chứa ShellTestClient, ShellScreen, ShellAssertions và ShellInputProvider.
- **spring-shell-test-autoconfigure**: chứa @ShellTest và cấu hình bean hỗ trợ kiểm thử.

Nếu dự án dùng BOM **spring-shell-dependencies**, khai báo dependency theo version được BOM quản lý. Ví dụ Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.shell</groupId>
            <artifactId>spring-shell-dependencies</artifactId>
            <version>4.0.3</version>
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
</dependencies>
```

Nếu không dùng BOM, cần khai báo cùng phiên bản tương thích cho hai artifact. Dự án Spring Shell 4.x tích hợp Spring Boot cần dùng dòng Spring Boot 4 và Spring Framework 7 tương ứng; không ghép test module 4.x vào ứng dụng Spring Boot 3.x.

Với Maven, các dependency kiểm thử thông thường như JUnit Jupiter, AssertJ và Spring Boot Test có thể được quản lý qua **spring-boot-starter-test** nếu ứng dụng đã dùng Spring Boot. Spring Shell test API dùng AssertJ cho **ShellAssertions**.

## 3. Thiết lập test context bằng @ShellTest

**@ShellTest** tạo test context tập trung vào các thành phần Spring Shell. Dùng **@ContextConfiguration** để chỉ định ứng dụng hoặc cấu hình chứa command cần kiểm thử.

Ví dụ ứng dụng có một command **hi**:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.core.command.annotation.Command;

@SpringBootApplication
public class ExampleShellApplication {

    @Command(name = "hi", description = "Chào người dùng.")
    public String hello() {
        return "Xin chào từ Spring Shell";
    }
}
```

Test gửi command và kiểm tra nội dung:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = ExampleShellApplication.class)
class ShellCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesHiCommand() throws Exception {
        ShellScreen screen = client.sendCommand("hi");

        ShellAssertions.assertThat(screen)
                .containsText("Xin chào từ Spring Shell");
    }
}
```

Trong ví dụ, **@ShellTest** cung cấp test infrastructure, còn **@ContextConfiguration** đăng ký command từ **ExampleShellApplication**. **ShellTestClient** được inject từ Spring context; không cần khởi chạy một terminal tương tác thật.

Nếu command phụ thuộc service, hãy đưa service vào test context bằng cấu hình ứng dụng, **@Import** hoặc test configuration. Có thể thay service bằng fake hoặc mock để kiểm tra command độc lập với hệ thống bên ngoài. Mục tiêu của test shell là xác nhận đường đi từ câu lệnh đến nội dung đầu ra; logic nghiệp vụ phức tạp vẫn nên có unit test riêng.

## 4. Gửi command bằng sendCommand(String)

**ShellTestClient.sendCommand(String)** nhận chuỗi command thô, thực thi command và trả về **ShellScreen** sau khi chạy:

```java
ShellScreen screen = client.sendCommand("hi");
```

Chuỗi được đưa qua command parser và command registry của shell test context. Vì vậy, test này kiểm tra nhiều phần hơn việc gọi trực tiếp method Java:

- Tên command được đăng ký đúng.
- Cú pháp command được phân tích.
- Argument và option được bind.
- Command được thực thi.
- Kết quả được chuyển thành nội dung trên shell screen.

Ví dụ kiểm tra command có option:

```java
import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Component
public class GreetingCommands {

    @Command(name = "greet", description = "Chào theo tên.")
    public String greet(@Option(longName = "name") String name) {
        return "Xin chào, " + name;
    }
}
```

Test gửi đúng cú pháp mà người dùng sẽ nhập:

```java
@Test
void bindsOptionAndDisplaysGreeting() throws Exception {
    ShellScreen screen = client.sendCommand("greet --name Ada");

    ShellAssertions.assertThat(screen)
            .containsText("Xin chào, Ada");
}
```

Nên viết chuỗi command giống cách người dùng thật sẽ nhập, gồm tên command, option, argument và dấu nháy nếu giá trị có khoảng trắng. Điều này giúp phát hiện lỗi parser hoặc cấu hình option mà một unit test gọi thẳng method không thể phát hiện.

Mỗi lần gọi **sendCommand(...)** trả về màn hình của lần thực thi đó. Có thể gọi client nhiều lần trong cùng test class để kiểm tra nhiều command khác nhau:

```java
ShellScreen help = client.sendCommand("help");
ShellScreen greeting = client.sendCommand("hi");

ShellAssertions.assertThat(help).containsText("AVAILABLE COMMANDS");
ShellAssertions.assertThat(greeting).containsText("Xin chào từ Spring Shell");
```

Đối với test có thay đổi trạng thái dùng chung, hãy chuẩn bị dữ liệu và dọn trạng thái giữa các test. Không dựa vào thứ tự chạy test để chia sẻ trạng thái shell.

## 5. ShellScreen lưu đầu ra như thế nào?

**ShellScreen** là một Java record với thành phần **lines** có kiểu **List<String>**. Nó đại diện cho nội dung màn hình shell được thu lại sau khi command thực thi:

```java
public record ShellScreen(List<String> lines) {
}
```

Có thể đọc trực tiếp các dòng:

```java
ShellScreen screen = client.sendCommand("hi");
List<String> lines = screen.lines();
```

**lines()** hữu ích khi cần kiểm tra cấu trúc theo dòng, ví dụ tiêu đề, bảng hoặc một thông báo xuất hiện ở dòng cụ thể. Với assertion nội dung thông thường, nên dùng **ShellAssertions** vì helper này tìm văn bản trong toàn bộ màn hình.

Không nên dùng **screen.toString()** làm hợp đồng kiểm thử. **toString()** là cách Java biểu diễn record, không phải API định dạng nội dung terminal. Hãy dùng **lines()** hoặc **ShellAssertions.assertThat(screen)**.

### Kiểm tra nội dung bằng ShellAssertions

**ShellAssertions.assertThat(screen)** trả về **ShellScreenAssert**, hiện cung cấp phương thức chuyên biệt **containsText(String)**:

```java
ShellAssertions.assertThat(screen)
        .containsText("Xin chào");
```

Phương thức này xác nhận đoạn văn bản có xuất hiện trong màn hình. Nó phù hợp khi output có thể chứa thêm lời nhắc, khoảng trắng hoặc nội dung phụ không liên quan đến mục tiêu của test.

### Kiểm tra dòng cụ thể bằng AssertJ

Khi cần xác nhận dòng hiển thị:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(screen.lines())
        .anyMatch(line -> line.contains("Xin chào"));
```

Nếu thứ tự dòng là một phần quan trọng của giao diện, có thể so sánh danh sách dòng hoặc kiểm tra index. Tuy nhiên, chỉ nên kiểm tra toàn bộ snapshot khi định dạng đó là yêu cầu ổn định của sản phẩm. Các thay đổi nhỏ về căn lề, tiêu đề hoặc terminal width có thể khiến snapshot quá mong manh.

## 6. Kiểm tra command không tồn tại

Khi command không có trong registry, **sendCommand(...)** có thể ném **CommandNotFoundException**. Có thể kiểm tra trường hợp này bằng AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.shell.core.command.CommandNotFoundException;

@Test
void reportsUnknownCommand() {
    assertThatThrownBy(() -> client.sendCommand("unknown-command"))
            .isInstanceOf(CommandNotFoundException.class);
}
```

Đây là một kiểm tra quan trọng khi ứng dụng có alias hoặc command được đăng ký có điều kiện. Nó giúp xác nhận tên command người dùng dự kiến đã thực sự có trong registry.

Lưu ý phân biệt command không tồn tại với command tồn tại nhưng thất bại khi thực thi. Trường hợp thứ hai phụ thuộc vào cách exception resolver hoặc command xử lý lỗi được cấu hình. Hãy viết test theo hợp đồng lỗi của ứng dụng: lỗi được chuyển thành thông báo trên screen hay được ném ra khỏi **sendCommand(...)**.

## 7. Cung cấp input cho command bằng ShellInputProvider

Một số command đọc dữ liệu sau khi đã được gọi, ví dụ yêu cầu tên người dùng, xác nhận hoặc mật khẩu. **sendCommand(String)** chỉ cung cấp chuỗi command; nó không tự tạo câu trả lời cho các lần đọc input tiếp theo.

**ShellInputProvider** giải quyết trường hợp này. Tạo provider bằng **providerFor(command)**, thêm các câu trả lời qua **withInput(...)**, thêm mật khẩu qua **withPassword(...)**, rồi gọi **build()**:

```java
import org.springframework.shell.test.ShellInputProvider;

ShellInputProvider inputProvider = ShellInputProvider
        .providerFor("ask")
        .withInput("Ada")
        .build();

ShellScreen screen = client.sendCommand(inputProvider);
```

**sendCommand(ShellInputProvider)** gửi command, cung cấp các input/password đã khai báo cho những lần command đọc dữ liệu, rồi trả về **ShellScreen**.

**ShellInputProvider** lưu riêng hai hàng đợi: **inputs** chứa chuỗi input thông thường và **passwords** chứa mật khẩu. Vì vậy, hãy dùng đúng phương thức tương ứng với cách command đọc dữ liệu. Không đưa password vào **withInput(...)** nếu command đang gọi API đọc password.

### Ví dụ command đọc input

Spring Shell 4.x cho phép định nghĩa command bằng **Command** API. Một command dùng **CommandContext** có thể đọc input từ **inputReader()**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration
public class InputCommandConfiguration {

    @Bean
    Command ask() {
        return new AbstractCommand("ask", "Hỏi tên người dùng") {
            @Override
            public ExitStatus doExecute(CommandContext commandContext) throws Exception {
                String name = commandContext.inputReader().readInput();
                commandContext.outputWriter().println("Bạn đã nhập: " + name);
                return ExitStatus.OK;
            }
        };
    }
}
```

Test mô phỏng câu trả lời:

```java
@Test
void suppliesUserInput() throws Exception {
    ShellInputProvider input = ShellInputProvider
            .providerFor("ask")
            .withInput("Ada")
            .build();

    ShellScreen screen = client.sendCommand(input);

    ShellAssertions.assertThat(screen)
            .containsText("Bạn đã nhập: Ada");
}
```

Đây là kiểm thử input theo luồng command thực tế. Nó xác nhận command gọi đúng input reader và xử lý câu trả lời nhận được.

### Cung cấp nhiều câu trả lời

Nếu command đọc nhiều lần, truyền nhiều giá trị theo đúng thứ tự đọc:

```java
ShellInputProvider input = ShellInputProvider
        .providerFor("wizard")
        .withInput("workspace-demo", "staging", "yes")
        .build();
```

Các giá trị trong **withInput(...)** được đưa vào queue input. Hãy kiểm tra thứ tự đọc trong command để tránh câu trả lời bị gán nhầm trường. Nếu command thay đổi thứ tự prompt, test này sẽ giúp phát hiện sự không tương thích.

## 8. Mô phỏng password input

Khi command yêu cầu password, dùng **withPassword(...)**:

```java
ShellInputProvider input = ShellInputProvider
        .providerFor("login")
        .withInput("ada")
        .withPassword("test-password")
        .build();

ShellScreen screen = client.sendCommand(input);

ShellAssertions.assertThat(screen)
        .containsText("Đăng nhập thành công");
```

Trong ví dụ, **withInput("ada")** cung cấp tên tài khoản và **withPassword(...)** cung cấp câu trả lời cho thao tác đọc password. Test nên xác nhận kết quả nghiệp vụ như đăng nhập thành công hoặc thất bại; không xác nhận rằng mật khẩu được in ra screen.

Không ghi password thật của người dùng hoặc bí mật môi trường vào test source. Dùng dữ liệu giả chỉ dành cho test, và tránh đưa password vào log khi assertion thất bại. **ShellInputProvider** là dữ liệu mô phỏng input; nó không phải kho bí mật và không mã hóa các giá trị được truyền vào.

## 9. Kiểm tra nhiều command trong cùng test context

**ShellTestClient** có thể được dùng để chạy nhiều command trong cùng test class. Ví dụ:

```java
@Test
void verifiesSeveralCommands() throws Exception {
    ShellScreen help = client.sendCommand("help");
    ShellScreen hi = client.sendCommand("hi");
    ShellScreen bye = client.sendCommand("bye");

    ShellAssertions.assertThat(help)
            .containsText("AVAILABLE COMMANDS");
    ShellAssertions.assertThat(hi)
            .containsText("Hello world!");
    ShellAssertions.assertThat(bye)
            .containsText("Goodbye world!");
}
```

Cách này hữu ích để kiểm tra command registry của ứng dụng, tên command, mô tả help và nội dung kết quả. Mỗi lần gửi command đều nhận một **ShellScreen** riêng, nên assertion của command này không phụ thuộc vào nội dung của command trước.

Nếu command dùng chung database hoặc bean có trạng thái, hãy tạo dữ liệu test cô lập và reset sau mỗi test. **ShellScreen** chỉ là snapshot đầu ra, không tự cách ly trạng thái nghiệp vụ.

## 10. Kiểm thử với đầy đủ Spring Boot application

**@ShellTest** phù hợp với test tập trung vào shell components. Khi cần kiểm tra quá trình khởi động ứng dụng Spring Boot và runner thực thi command, có thể dùng **@SpringBootTest** cùng **OutputCaptureExtension**.

Ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        useMainMethod = SpringBootTest.UseMainMethod.ALWAYS,
        classes = ExampleShellApplication.class,
        properties = "spring.shell.interactive.enabled=false",
        args = "hi"
)
@ExtendWith(OutputCaptureExtension.class)
class ShellApplicationEndToEndTests {

    @Test
    void printsCommandOutput(CapturedOutput output) {
        assertThat(output).contains("Xin chào từ Spring Shell");
    }
}
```

Ở đây, ứng dụng được khởi động qua main method với command **hi** truyền trong **args**. Thuộc tính **spring.shell.interactive.enabled=false** chọn runner non-interactive để test không chờ terminal input. **OutputCaptureExtension** thu stdout/stderr để kiểm tra nội dung.

Phương pháp end-to-end hữu ích khi cần kiểm tra cấu hình khởi động, runner và cách ứng dụng thực thi command khi chạy như một process Spring Boot. Tuy nhiên, không tiện để chạy nhiều command khác nhau trong cùng test class vì command được truyền qua thuộc tính **args** lúc khởi tạo context. Với nhiều command, dùng **ShellTestClient.sendCommand(...)** thuận tiện hơn.

## 11. sendCommand và kiểm tra exit status

**sendCommand(...)** trả về **ShellScreen**, tức nội dung hiển thị sau khi command chạy. **ShellScreen** chỉ chứa **lines**; nó không phải đối tượng **ExitStatus** và không cung cấp trực tiếp mã thoát của tiến trình JVM.

Vì vậy, cần chọn đúng cấp kiểm thử:

| Điều cần xác nhận | Cách kiểm thử phù hợp |
| --- | --- |
| Command có được gọi đúng không? | ShellTestClient.sendCommand(...) |
| Người dùng nhìn thấy thông báo nào? | ShellScreen và ShellAssertions |
| Command có nhận input/password đúng không? | ShellInputProvider |
| Command không tồn tại có được nhận diện không? | Kiểm tra CommandNotFoundException |
| Command trả ExitStatus nào? | Kiểm tra lớp thực thi command hoặc lớp điều phối trả trạng thái |
| Tiến trình ứng dụng kết thúc với mã nào? | Chạy ứng dụng trong process test riêng và kiểm tra process exit value |

Không suy ra exit code bằng cách tìm một chuỗi như ERROR trên màn hình. Thông báo có thể thay đổi, được dịch hoặc được ghi ra stderr mà không phản ánh chính xác trạng thái kết thúc của process.

## 12. Xử lý exception trong test

**ShellTestClient.sendCommand(...)** khai báo có thể ném **Exception** khi có lỗi trong quá trình thực thi. Tùy loại lỗi và cấu hình resolver, lỗi có thể:

- Được chuyển thành thông báo và xuất hiện trong **ShellScreen**.
- Được ném ra khỏi lời gọi **sendCommand(...)**.
- Được xử lý thành một kết quả lỗi theo quy ước command của ứng dụng.

Với command không tồn tại, test có thể mong đợi **CommandNotFoundException**. Với lỗi nghiệp vụ, hãy xác định rõ resolver có chuyển exception thành thông báo hay để exception truyền ra. Không viết một assertion chung rằng mọi lỗi đều phải ném exception hoặc mọi lỗi đều phải xuất hiện trên màn hình.

Ví dụ kiểm tra thông báo lỗi do resolver tạo:

```java
@Test
void displaysBusinessError() throws Exception {
    ShellScreen screen = client.sendCommand("project delete --id P404");

    ShellAssertions.assertThat(screen)
            .containsText("Không tìm thấy dự án P404");
}
```

Nếu resolver của ứng dụng để exception truyền ra, hãy dùng **assertThatThrownBy(...)** và kiểm tra đúng loại exception. Không nên kiểm tra stack trace đầy đủ vì nội dung phụ thuộc môi trường, phiên bản và cấu hình logging.

## 13. Giới hạn của ShellScreen và cách viết assertion bền vững

**ShellScreen** ghi lại danh sách dòng mà test client nhận được sau command. Nó không phải bản ghi mọi thao tác bàn phím theo thời gian và cũng không phải một ảnh chụp đồ họa terminal có đầy đủ mọi trạng thái tương tác.

Vì vậy:

- Dùng **containsText(...)** cho nội dung người dùng cần thấy.
- Dùng **lines()** khi thứ tự hoặc cấu trúc dòng là yêu cầu.
- Không kiểm tra **toString()** của record như output terminal.
- Không khóa test vào khoảng trắng/căn lề nếu đó không phải hợp đồng giao diện.
- Không dùng **ShellScreen** để suy ra process exit code.
- Với giao diện terminal động hoặc TUI, kiểm thử logic điều hướng và view bằng test phù hợp cho view/event; **sendCommand** chủ yếu xác nhận kết quả command.

Nếu command in bảng, hãy kiểm tra tiêu đề cột và một vài giá trị quan trọng. Chỉ kiểm tra toàn bộ bảng theo snapshot khi format được quy định ổn định và terminal width của test được kiểm soát.

## 14. Khác biệt bộ test API giữa Spring Shell 3.x và 4.x

Spring Shell 4.0 thiết kế lại test utilities. Không nên sao chép nguyên ví dụ 3.x rồi chỉ đổi version dependency.

| Chủ đề | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Mô phỏng phiên interactive | ShellTestClient.interactive().run() và session/write sequence trong tài liệu 3.x | Dùng sendCommand(...) cho command; cung cấp dữ liệu đọc bằng ShellInputProvider |
| Gửi command | API client/session theo mô hình test 3.x | sendCommand(String) |
| Cấp input/password | Mô phỏng session hoặc input theo API 3.x | sendCommand(ShellInputProvider) |
| Kết quả | API session/screen theo mô hình 3.x | ShellScreen record có lines() |
| Assertion | ShellAssertions và screen assertion | ShellAssertions.assertThat(screen).containsText(...) |
| Cấu hình test | Các annotation và tiện ích test 3.x | @ShellTest từ spring-shell-test-autoconfigure |

Migration guide 4.x nêu rõ một số test API/annotation cũ đã bị loại bỏ, gồm **ShellWriteSequence**, **ShellTypeExcludeFilter**, **SpringShellTestProperties**, **@AutoConfigureShell** và **@AutoConfigureShellTestClient**. **ShellInputProvider** cùng overload **sendCommand(ShellInputProvider)** được bổ sung từ 4.0.2.

Khi nâng cấp:

1. Thay dependency test theo bộ artifact 4.x.
2. Chuyển test context sang **@ShellTest** và **@ContextConfiguration** phù hợp.
3. Thay lời gọi session/write sequence cũ bằng **sendCommand(...)**.
4. Dùng **ShellInputProvider** để mô phỏng input/password.
5. Chuyển assertion sang **ShellScreen** và **ShellAssertions**.
6. Tách test command output khỏi test process exit code hoặc test TUI tương tác.

## 15. Tổ chức test theo tầng

Một bộ test CLI dễ bảo trì thường có nhiều tầng:

| Tầng | Mục tiêu | Công cụ |
| --- | --- | --- |
| Unit test service | Quy tắc nghiệp vụ, validation và side effect | JUnit, Mockito hoặc fake |
| Command test | Parsing, binding và output của command | @ShellTest, ShellTestClient, ShellScreen |
| Input test | Prompt input và password | ShellInputProvider |
| Application integration | Boot context, runner và command khởi động cùng ứng dụng | @SpringBootTest, OutputCaptureExtension |
| Process test | Mã thoát JVM và hành vi process thực tế | Khởi chạy process test riêng |

Không nên dùng test shell để thay thế mọi unit test. Nếu service tính sai tổng tiền hoặc xóa nhầm dữ liệu, một test command chỉ xác nhận thông báo có chứa chữ thành công sẽ không phát hiện đầy đủ lỗi nghiệp vụ.

Ngược lại, test gọi trực tiếp method command không xác nhận parser đã bind option đúng hoặc command đã được đăng ký. **sendCommand(...)** bổ sung lớp kiểm thử tích hợp này với chi phí thấp hơn so với khởi chạy process thật.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không inject được ShellTestClient | Thiếu @ShellTest hoặc test auto-configuration dependency | Thêm spring-shell-test-autoconfigure và annotation |
| Không tìm thấy ShellAssertions | Thiếu spring-shell-test | Thêm test API dependency |
| Command không được tìm thấy | Command bean chưa nằm trong test context hoặc sai tên | Kiểm tra @ContextConfiguration và command registry |
| sendCommand chờ input | Command đọc input nhưng test chỉ gửi chuỗi command | Dùng ShellInputProvider |
| Password không được nhận | Đưa password vào withInput thay vì withPassword | Cấp dữ liệu đúng queue |
| Assertion không ổn định | So sánh toàn bộ dòng có khoảng trắng hoặc định dạng thay đổi | Dùng containsText hoặc kiểm tra phần nội dung cần thiết |
| Test nhiều command bị ảnh hưởng lẫn nhau | Dùng chung trạng thái nghiệp vụ hoặc dữ liệu không được reset | Cô lập dữ liệu và dọn trạng thái |
| Test end-to-end treo | Shell vẫn chạy interactive runner và đợi input | Đặt spring.shell.interactive.enabled=false |
| Dùng ví dụ test 3.x không biên dịch | API session/write sequence cũ đã thay đổi hoặc bị loại bỏ | Chuyển sang sendCommand và ShellInputProvider |
| Dùng screen để kiểm tra exit code | Nhầm nội dung màn hình với trạng thái kết thúc process | Kiểm tra exit status/process ở đúng tầng |

## 17. Checklist viết test bằng sendCommand và ShellScreen

- Thêm spring-shell-test và spring-shell-test-autoconfigure vào test scope.
- Dùng phiên bản dependency tương thích với Spring Shell 4.x và Spring Boot 4.
- Khai báo @ShellTest và context chứa command.
- Inject ShellTestClient từ Spring context.
- Gửi command bằng sendCommand(String) với cú pháp giống người dùng thật.
- Nhận ShellScreen và assert bằng ShellAssertions.
- Dùng screen.lines() khi cần kiểm tra cấu trúc theo dòng.
- Dùng ShellInputProvider khi command đọc input hoặc password.
- Kiểm tra command không tồn tại và lỗi nghiệp vụ theo đúng exception resolver.
- Không suy ra process exit code từ nội dung screen.
- Dùng @SpringBootTest riêng khi cần kiểm tra runner và khởi động ứng dụng.
- Tắt interactive mode trong test end-to-end không cần input.
- Tách unit test nghiệp vụ khỏi test parser/output của shell.
- Không dùng API test 3.x đã bị loại bỏ trong Spring Shell 4.x.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — ShellTestClient API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.3 — ShellScreen API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellScreen.html)
- [Spring Shell 4.0.3 — ShellAssertions API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellAssertions.html)
- [Spring Shell 4.0.3 — ShellScreenAssert API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellScreenAssert.html)
- [Spring Shell 4.0.3 — ShellInputProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html)
- [Spring Shell 4.0.3 — ShellInputProvider.Builder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.Builder.html)
- [Spring Shell 4.0.3 — @ShellTest API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/autoconfigure/ShellTest.html)
- [Spring Shell 4.0.3 — ShellTestClientAutoConfiguration API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/autoconfigure/ShellTestClientAutoConfiguration.html)
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0.3 — spring-shell-test artifact](https://central.sonatype.com/artifact/org.springframework.shell/spring-shell-test)
- [Spring Shell 4.0.3 — spring-shell-dependencies BOM](https://central.sonatype.com/artifact/org.springframework.shell/spring-shell-dependencies)
