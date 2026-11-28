# InputReader và đọc mật khẩu qua ngữ cảnh trong Spring Shell 4.x

Một command đôi khi cần hỏi thêm thông tin sau khi người dùng đã gọi lệnh. Ví dụ, command tạo tài khoản cần hỏi tên đăng nhập rồi đọc mật khẩu; command kết nối máy chủ cần hỏi mã xác thực; command thay đổi cấu hình có thể cần yêu cầu người dùng nhập lại tên môi trường để xác nhận. Trong Spring Shell 4.x, command có thể lấy InputReader từ CommandContext để đọc những dữ liệu này.

InputReader cung cấp hai nhóm thao tác: đọc một dòng văn bản và đọc mật khẩu. readInput(...) trả về String, còn readPassword(...) trả về char[]. Sự khác biệt này quan trọng khi xử lý thông tin bí mật: mật khẩu nên được đọc bằng API chuyên dụng, giữ trong mảng ký tự trong thời gian ngắn và xóa nội dung sau khi dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của CommandContext trong một lần thực thi command.
- Lấy InputReader từ CommandContext.inputReader().
- Phân biệt readInput() với readPassword().
- Đọc dữ liệu bổ sung bằng prompt trong command Spring Shell 4.x.
- Xử lý mật khẩu dưới dạng char[] và giới hạn thời gian tồn tại của dữ liệu nhạy cảm.
- Dùng CommandContext.outputWriter() để ghi thông báo vào shell.
- Phân biệt InputReader với InputProvider.
- Hiểu sự khác nhau giữa ConsoleInputReader và JLineInputReader.
- Chọn cách nhập phù hợp cho interactive mode và non-interactive mode.
- Kiểm thử input thường và password bằng ShellInputProvider.
- Nhận biết thay đổi package và annotation khi chuyển từ Spring Shell 3.x sang 4.x.

## 1. CommandContext là gì?

Trong Spring Shell 4.x, CommandContext là record chứa thông tin runtime của lần gọi command hiện tại. Command có thể nhận context làm tham số để truy cập dữ liệu đã parse, command registry, output writer và input reader.

Các thành phần chính:

| Thành phần | Kiểu | Vai trò |
|---|---|---|
| parsedInput() | ParsedInput | Dữ liệu command, option và argument đã được phân tích |
| commandRegistry() | CommandRegistry | Registry chứa các command đã đăng ký |
| outputWriter() | PrintWriter | Ghi nội dung vào output của shell |
| inputReader() | InputReader | Đọc thêm dữ liệu từ người dùng trong lúc command chạy |

Sơ đồ luồng cơ bản:

~~~mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Spring Shell phân tích command và option]
    B --> C[Tạo CommandContext cho lần gọi]
    C --> D[Command nhận CommandContext]
    D --> E[inputReader đọc dữ liệu bổ sung]
    D --> F[outputWriter ghi thông báo]
    E --> G[Command gọi service nghiệp vụ]
    G --> H[Trả kết quả về shell]
~~~

CommandContext thuộc về một lần thực thi. Không lưu context hoặc input reader vào biến static, singleton state hay một tác vụ chạy nền để dùng sau khi command kết thúc. Hãy đọc dữ liệu cần thiết trong thời gian command đang chạy và chuyển dữ liệu đã được kiểm tra sang service.

## 2. Lấy InputReader từ CommandContext

API 4.x đặt CommandContext trong package org.springframework.shell.core.command, còn InputReader nằm trong org.springframework.shell.core.

Ví dụ một command đọc tên người dùng:

~~~java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "greeting personalize")
    public String personalize(CommandContext context) throws Exception {
        String name = context.inputReader().readInput("Tên của bạn: ");
        return "Xin chào, " + name + "!";
    }
}
~~~

Trong ví dụ:

1. CommandContext được Spring Shell truyền vào command.
2. context.inputReader() lấy reader dành cho lần gọi hiện tại.
3. readInput("Tên của bạn: ") hiển thị prompt và chờ một dòng input.
4. Command sử dụng kết quả để tạo thông báo trả về shell.

Các method đọc input có thể ném Exception khi xảy ra lỗi trong quá trình đọc. Method command có thể khai báo throws Exception hoặc xử lý lỗi theo chính sách của ứng dụng.

Nếu cần ghi output trực tiếp trong lúc command đang chạy, dùng context.outputWriter():

~~~java
@Command(name = "greeting personalize")
public void personalize(CommandContext context) throws Exception {
    String name = context.inputReader().readInput("Tên của bạn: ");
    context.outputWriter().println("Xin chào, " + name + "!");
    context.outputWriter().flush();
}
~~~

PrintWriter trong context là output của shell. Dùng writer này khi command cần ghi nhiều thông báo hoặc cập nhật output trong quá trình thực hiện; với kết quả đơn giản, có thể trả về một giá trị để Spring Shell xử lý.

## 3. Các method của InputReader

Spring Shell 4.x cung cấp bốn method chính:

| Method | Giá trị trả về | Mục đích |
|---|---|---|
| readInput() | String | Đọc một dòng input |
| readInput(String prompt) | String | Hiển thị prompt rồi đọc một dòng |
| readPassword() | char[] | Đọc mật khẩu |
| readPassword(String prompt) | char[] | Hiển thị prompt rồi đọc mật khẩu |

Ví dụ:

~~~java
String projectName = context.inputReader().readInput();
String environment = context.inputReader().readInput("Môi trường triển khai: ");

char[] password = context.inputReader().readPassword();
char[] confirmation = context.inputReader().readPassword("Nhập lại mật khẩu: ");
~~~

Không dùng readInput() để đọc password. readInput() được thiết kế cho văn bản thông thường và trả về String. Với thông tin xác thực, hãy dùng readPassword() để reader xử lý input theo cơ chế dành cho mật khẩu và trả về char[].

## 4. Khi nào nên dùng prompt thay vì command option?

Spring Shell có thể nhận dữ liệu theo hai cách:

- Khai báo option hoặc argument để người dùng truyền ngay trên command line.
- Dùng InputReader để hỏi thêm dữ liệu khi command đang chạy.

Nên dùng option/argument cho dữ liệu không bí mật, có thể biết trước và cần hỗ trợ script, ví dụ định dạng báo cáo, ID tài nguyên hoặc giới hạn số bản ghi.

Nên dùng prompt cho thông tin chỉ có thể hỏi trong phiên tương tác, thông tin cần người dùng xác nhận tại thời điểm chạy hoặc dữ liệu nhạy cảm như password.

| Dữ liệu | Cách nhận phù hợp |
|---|---|
| Tên báo cáo | @Option hoặc @Argument |
| Mã khách hàng | @Option hoặc @Argument |
| Tên người dùng cần hỏi trong phiên | readInput(prompt) |
| Password đăng nhập | readPassword(prompt) |
| Mã xác nhận một lần | readPassword(prompt) hoặc input chuyên biệt theo chính sách |
| Secret cho job automation | Secret provider, secret store hoặc file secret được bảo vệ |

Không truyền password qua command option như --password my-secret. Giá trị command line có thể xuất hiện trong shell history, process listing, log của scheduler hoặc công cụ giám sát. Với phiên tương tác, dùng readPassword(). Với automation, dùng kênh cấp secret được kiểm soát.

## 5. Đọc password qua InputReader

Điểm khác biệt quan trọng nhất của readPassword() là kiểu dữ liệu trả về. API trả char[], không trả String.

Ví dụ command tạo tài khoản:

~~~java
import java.util.Arrays;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class AccountCommands {

    private final AccountService accountService;

    public AccountCommands(AccountService accountService) {
        this.accountService = accountService;
    }

    @Command(name = "account create", description = "Tạo tài khoản mới")
    public String create(CommandContext context) throws Exception {
        String username = context.inputReader().readInput("Tên đăng nhập: ");
        char[] password = context.inputReader().readPassword("Mật khẩu: ");

        try {
            String normalizedUsername = username.strip();
            if (normalizedUsername.isBlank()) {
                throw new IllegalArgumentException("Tên đăng nhập không được để trống");
            }
            if (password.length < 12) {
                throw new IllegalArgumentException("Mật khẩu phải có ít nhất 12 ký tự");
            }

            accountService.create(normalizedUsername, password);
            return "Đã tạo tài khoản " + normalizedUsername + ".";
        }
        finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

AccountService trong ví dụ nhận char[] và xử lý mật khẩu ngay trong lời gọi. Service nên tạo hash mật khẩu theo chính sách bảo mật của ứng dụng, không lưu mật khẩu gốc và không giữ tham chiếu đến mảng ký tự sau khi hoàn tất.

Khối finally chạy cả khi validation hoặc service ném exception. Nhờ vậy, command có thể xóa nội dung mảng sau khi sử dụng:

~~~java
Arrays.fill(password, '\0');
~~~

Việc ghi đè mảng giúp giảm thời gian dữ liệu nhạy cảm còn trong vùng nhớ mà ứng dụng kiểm soát. Nó không bảo đảm xóa mọi bản sao mà JVM, terminal library hoặc thư viện khác có thể đã tạo; vì vậy vẫn cần tránh tạo thêm bản sao không cần thiết.

### 5.1. Không chuyển password thành String

Không làm như sau:

~~~java
char[] password = context.inputReader().readPassword("Mật khẩu: ");
String passwordText = new String(password);
accountService.create(username, passwordText);
~~~

String là immutable, nên ứng dụng không thể ghi đè nội dung của object đó sau khi tạo. Dữ liệu có thể còn tồn tại trong heap cho đến khi garbage collector thu hồi vùng nhớ.

Giữ password dưới dạng char[] trong suốt luồng xử lý nếu API nghiệp vụ cho phép. Nếu một thư viện bắt buộc nhận String hoặc CharSequence, giới hạn việc chuyển đổi ở một adapter nhỏ, không log giá trị và không lưu giữ chuỗi đó.

### 5.2. Không in hoặc ghi log password

Không nối password vào output:

~~~java
// Không làm như vậy.
context.outputWriter().println("Password: " + password);
~~~

Không ghi password vào:

- Log ứng dụng hoặc stack trace.
- Exception message.
- Shell history.
- Audit event.
- File tạm hoặc file cấu hình.
- Tên biến, metric label hoặc tracing attribute.

Thông báo chỉ nên cho biết thao tác thành công hay thất bại, ví dụ Đã xác thực thành công hoặc Thông tin đăng nhập không hợp lệ.

## 6. Đọc và xác nhận mật khẩu hai lần

Một số command tạo credential cần yêu cầu người dùng nhập lại password để giảm lỗi gõ nhầm. Có thể gọi readPassword() hai lần:

~~~java
char[] password = context.inputReader().readPassword("Mật khẩu mới: ");
try {
    char[] confirmation =
            context.inputReader().readPassword("Nhập lại mật khẩu: ");
    try {
        if (!Arrays.equals(password, confirmation)) {
            throw new IllegalArgumentException("Hai lần nhập mật khẩu không khớp");
        }

        accountService.changePassword(username, password);
    }
    finally {
        Arrays.fill(confirmation, '\0');
    }
}
finally {
    Arrays.fill(password, '\0');
}
~~~

Mỗi mảng được xóa trong finally riêng. Nếu lần đọc thứ hai hoặc việc xác nhận thất bại, mảng đầu tiên vẫn được xóa.

So sánh hai lần nhập do cùng người dùng vừa nhập nhằm phát hiện lỗi gõ nhầm. Đây không phải phép so sánh password với hash lưu trữ và không thay thế cơ chế xác thực của service.

Không hỏi lại password nhiều lần mà không có giới hạn. Nếu cần cho phép thử lại, đặt số lần tối đa, thông báo rõ ràng và kết thúc command an toàn khi vượt giới hạn.

## 7. InputReader và InputProvider khác nhau

Hai tên này dễ gây nhầm lẫn nhưng phục vụ hai hướng input khác nhau:

| Thành phần | Hướng dữ liệu | Vai trò |
|---|---|---|
| InputProvider | Từ nguồn input vào shell runner | Cung cấp dòng command để shell phân tích và thực thi |
| InputReader | Từ người dùng vào command đang chạy | Đọc thêm câu trả lời hoặc password sau khi command đã được gọi |

Ví dụ:

~~~text
account create
Tên đăng nhập: alice
Mật khẩu: ********
~~~

Trong ví dụ, InputProvider cung cấp dòng account create cho shell. Sau khi command bắt đầu, InputReader đọc tên đăng nhập và password.

Không dùng InputReader để thay thế command parser hoặc đọc lại các option đã được Spring Shell phân tích. Nếu một giá trị là option bắt buộc và có thể truyền trước khi command chạy, khai báo nó bằng @Option hoặc @Argument.

## 8. Các implementation của InputReader trong 4.x

API InputReader tách command khỏi cách terminal thực sự nhận input. Spring Shell 4.0.3 có hai implementation chính:

| Implementation | Cách đọc | Runner liên quan |
|---|---|---|
| ConsoleInputReader | Dùng java.io.Console của JDK | SystemShellRunner |
| JLineInputReader | Dùng JLine LineReader | JLineShellRunner |

### 8.1. ConsoleInputReader

ConsoleInputReader đọc input từ system console. Đây là implementation phù hợp với shell tương tác cơ bản dựa trên Java Console.

Ưu điểm:

- Không cần dependency JLine.
- Dùng API console chuẩn của JDK.
- Có method đọc dòng thường và password.

Khi chạy trong IDE, service process, container hoặc môi trường chuyển hướng stdin/stdout, System.console() có thể không khả dụng. Hãy kiểm thử trong đúng môi trường triển khai; đừng giả định mọi cách chạy JAR đều có terminal tương tác.

### 8.2. JLineInputReader

JLineInputReader dùng JLine LineReader để nhận input. Nó được sử dụng trong cấu hình shell dựa trên JLine.

JLine phù hợp khi ứng dụng cần trải nghiệm terminal phong phú như lịch sử lệnh, completion và các tính năng tương tác khác. Spring Shell 4.x tách JLine khỏi module core. Nếu muốn sử dụng JLine, thêm dependency spring-shell-jline phù hợp với phiên bản Spring Shell đang dùng.

Code command chỉ phụ thuộc InputReader qua CommandContext, nên không cần tự tạo ConsoleInputReader hoặc JLineInputReader trong từng command.

### 8.3. Cùng một command, nhiều terminal reader

Command gọi:

~~~java
String name = context.inputReader().readInput("Tên: ");
char[] password = context.inputReader().readPassword("Mật khẩu: ");
~~~

Command không cần biết input đến từ Java Console hay JLine. Spring Shell cung cấp implementation phù hợp với cấu hình runner của ứng dụng.

Không tự khởi tạo một reader mới trong command chỉ để đọc từ System.in. Làm như vậy có thể khiến hai thành phần cùng đọc một luồng input, làm mất dòng hoặc khiến prompt hoạt động không nhất quán.

## 9. Interactive mode và non-interactive mode

Spring Shell 4.x yêu cầu ứng dụng chọn cách vận hành khi khởi động. Interactive mode được bật mặc định. Có thể tắt bằng:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Trong interactive mode, command có thể hỏi người dùng bằng readInput() hoặc readPassword().

Trong non-interactive mode, NonInteractiveShellRunner chạy command được truyền qua process arguments hoặc script rồi kết thúc. Môi trường này thường không có người dùng trả lời prompt. Vì vậy, không thiết kế một command automation phụ thuộc vào việc người dùng nhập thêm dữ liệu tương tác.

Ví dụ command tương tác:

~~~text
account create
Tên đăng nhập: alice
Mật khẩu: [nhập tại terminal]
~~~

Ví dụ command chạy trong batch:

~~~bash
java -Dspring.shell.interactive.enabled=false -jar support-cli.jar report export --format csv
~~~

Command report export nên nhận đủ dữ liệu không nhạy cảm qua option/argument và cấu hình. Nếu một tác vụ tự động cần secret, hãy lấy secret từ secret manager, secret file được mount với quyền phù hợp hoặc một provider bảo mật do ứng dụng quản lý. Không truyền password trực tiếp trên command line.

Nếu command gọi readPassword() trong non-interactive mode, không dựa vào việc nó sẽ hoạt động như một prompt terminal. Tùy runner và môi trường, việc đọc có thể không khả dụng hoặc không có người cung cấp input. Hãy tách đường chạy tương tác và đường chạy automation theo hợp đồng input rõ ràng.

## 10. Xử lý input rỗng, lỗi đọc và hủy thao tác

Input từ terminal vẫn là dữ liệu không đáng tin cậy. Cần validate trước khi gọi service:

- Chuỗi bắt buộc không được rỗng hoặc chỉ chứa khoảng trắng.
- Mã môi trường phải thuộc danh sách cho phép.
- Số lần thử phải có giới hạn.
- Password cần được kiểm tra theo chính sách credential của ứng dụng.
- Lỗi đọc input phải được xử lý như một lần nhập thất bại, không coi là xác nhận thành công.

Ví dụ kiểm tra tên:

~~~java
String username = context.inputReader().readInput("Tên đăng nhập: ").strip();
if (username.isBlank()) {
    throw new IllegalArgumentException("Tên đăng nhập không được để trống");
}
~~~

Nếu command hỗ trợ hủy, hãy thống nhất một cách biểu diễn rõ ràng, ví dụ nhập cancel ở câu hỏi văn bản hoặc dùng thao tác thoát của terminal. Không diễn giải input rỗng, EOF hoặc lỗi đọc thành giá trị mặc định có thể gây thay đổi dữ liệu.

Với password, tránh cho phép input rỗng nếu nghiệp vụ không hỗ trợ credential rỗng. Nếu đọc password thành công nhưng validation thất bại, vẫn phải xóa mảng trong finally.

## 11. Không lưu CommandContext hoặc InputReader để dùng về sau

CommandContext đại diện cho một lần gọi command. InputReader được cung cấp trong context đó để đọc input trong quá trình thực thi.

Không làm:

~~~java
@Component
public class BadCommandState {
    private InputReader savedReader;

    @Command(name = "bad command")
    public void run(CommandContext context) {
        savedReader = context.inputReader();
    }
}
~~~

Không giữ reader trong singleton, không truyền reader vào background executor và không gọi reader sau khi command đã kết thúc. Nếu cần dữ liệu cho tác vụ nền, hãy đọc xong, validate, chuyển phần dữ liệu cần thiết sang một object nghiệp vụ và kết thúc tương tác terminal.

Đặc biệt, không truyền password vào event, queue hoặc tác vụ nền nếu quy trình không thực sự cần. Nếu phải thực hiện xác thực bất đồng bộ, thiết kế cơ chế cấp credential và vòng đời secret riêng thay vì lưu char[] vô thời hạn.

## 12. Kiểm thử input và password với Spring Shell 4.0.3

Spring Shell 4.0.3 cung cấp ShellInputProvider để mô phỏng command cùng các dòng input và password. ShellTestClient.sendCommand(ShellInputProvider) gửi command, cấp input theo thứ tự và trả về ShellScreen.

Ví dụ command:

~~~java
@Component
public class AccountCommands {

    private final AccountService accountService;

    public AccountCommands(AccountService accountService) {
        this.accountService = accountService;
    }

    @Command(name = "account create")
    public String create(CommandContext context) throws Exception {
        String username = context.inputReader().readInput("Tên đăng nhập: ").strip();
        char[] password = context.inputReader().readPassword("Mật khẩu: ");

        try {
            accountService.create(username, password);
            return "Account created";
        }
        finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Test cung cấp input:

~~~java
@ShellTest
@ContextConfiguration(classes = SupportCliApplication.class)
class AccountCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void readsUsernameAndPassword() throws Exception {
        ShellInputProvider input = ShellInputProvider
                .providerFor("account create")
                .withInput("alice")
                .withPassword("test-only-password")
                .build();

        ShellScreen screen = client.sendCommand(input);

        ShellAssertions.assertThat(screen)
                .containsText("Account created");
    }
}
~~~

withInput(...) cung cấp các câu trả lời văn bản; withPassword(...) cung cấp các giá trị dành cho lời gọi readPassword(). Hai nhóm input được quản lý riêng, vì vậy hãy khai báo đúng số lượng và thứ tự mà command yêu cầu.

Password trong test phải là giá trị giả. ShellInputProvider giữ dữ liệu password dưới dạng chuỗi để phục vụ test; không đưa password thật, token thật hoặc dữ liệu production vào fixture, snapshot hay log CI.

### 12.1. Những trường hợp cần kiểm thử

| Kịch bản | Kết quả mong đợi |
|---|---|
| Input tên hợp lệ và password hợp lệ | Service được gọi với dữ liệu đã validate |
| Tên rỗng | Command từ chối trước khi gọi service |
| Password rỗng | Command từ chối nếu chính sách yêu cầu password |
| Password không đạt chính sách | Command báo lỗi và không tạo credential |
| Password được nhập hai lần không khớp | Command từ chối và xóa cả hai mảng |
| Reader ném exception | Command không coi thao tác là thành công |
| Service ném exception | Mảng password vẫn được xóa trong finally |
| Non-interactive command | Không phụ thuộc vào prompt terminal |
| Password được cấp trong test | Không xuất hiện trong output hoặc log |

### 12.2. Kiểm tra việc không làm lộ password

Ngoài kiểm tra command thành công, cần kiểm tra:

- Output không chứa password.
- Log không chứa password.
- Exception message không chứa password.
- Service không lưu mật khẩu gốc.
- Mảng ký tự được xóa sau khi xử lý.
- Test fixture chỉ dùng dữ liệu giả.

Không chỉ kiểm tra màn hình cuối cùng. Password có thể bị ghi vào log ở một tầng khác hoặc xuất hiện trong exception trước khi shell hiển thị kết quả.

## 13. Thay đổi API từ Spring Shell 3.x sang 4.x

Spring Shell 4.x tổ chức lại package và loại bỏ các annotation legacy. Khi chuyển code đọc input từ 3.x, cần cập nhật cách khai báo command và cách lấy context.

| Nội dung | Spring Shell 3.x | Spring Shell 4.x |
|---|---|---|
| Context | API context của mô hình 3.x | org.springframework.shell.core.command.CommandContext |
| Input reader | Không dùng đúng package/API mới này | org.springframework.shell.core.InputReader |
| Password input | Phụ thuộc API và mô hình component của 3.x | readPassword() trả char[] |
| Annotation command | Có legacy @ShellComponent, @ShellMethod | Dùng @Component cùng @Command |
| Tên command | Thuộc tính command ở một số API cũ | Thuộc tính name |
| JLine | Thường được đưa vào dependency mặc định của ứng dụng | Tách thành module spring-shell-jline |

Ví dụ khai báo command 4.x:

~~~java
@Component
class LoginCommands {

    @Command(name = "login")
    public String login(CommandContext context) throws Exception {
        String username = context.inputReader().readInput("Username: ");
        char[] password = context.inputReader().readPassword("Password: ");
        try {
            authenticationService.login(username, password);
            return "Authenticated";
        }
        finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Không sao chép import của 3.x sang 4.x rồi chỉ đổi tên method. Hãy dùng package org.springframework.shell.core... và annotation mới trong org.springframework.shell.core.command.annotation.

## 14. Những lỗi thường gặp

### Dùng readInput() để đọc password

readInput() trả String và được thiết kế cho văn bản thông thường. Dùng readPassword() để nhận char[] và áp dụng xử lý password phù hợp.

### Chuyển password thành String

String immutable nên không thể chủ động ghi đè nội dung. Giữ password dưới dạng char[] và xóa trong finally.

### Không xóa mảng khi service thất bại

Nếu chỉ xóa sau lời gọi service, exception có thể khiến code bỏ qua bước xóa. Dùng try/finally.

### Truyền password qua command option

Giá trị có thể xuất hiện trong shell history, process list hoặc log. Dùng password prompt cho interactive mode và secret provider cho automation.

### Tự đọc System.in bên cạnh InputReader

Hai reader có thể tranh chấp cùng input stream. Dùng context.inputReader() để đọc dữ liệu trong command.

### Nhầm InputProvider với InputReader

InputProvider cung cấp command line cho shell runner; InputReader đọc thêm dữ liệu trong command đang chạy.

### Giữ InputReader sau khi command kết thúc

Context chỉ thuộc một lần thực thi. Đọc input trong command, chuyển dữ liệu cần thiết sang service rồi kết thúc.

### Dùng prompt trong batch job

Không có terminal tương tác có thể khiến command chờ hoặc thất bại. Tách đường chạy interactive và automation, hoặc dùng secret provider được bảo vệ.

### Nghĩ rằng core luôn có JLine

Spring Shell 4.x tách JLine khỏi core. Thêm spring-shell-jline nếu cần JLine runner và các tính năng terminal tương ứng.

### Test chỉ kiểm tra output thành công

Kiểm thử cả input rỗng, password không hợp lệ, lỗi đọc, lỗi service, cleanup và việc không làm lộ secret.

## 15. Checklist triển khai

- [ ] Command nhận CommandContext từ Spring Shell.
- [ ] Đọc input bổ sung qua context.inputReader().
- [ ] Dùng readInput() cho văn bản thông thường.
- [ ] Dùng readPassword() cho password.
- [ ] Xử lý password dưới dạng char[].
- [ ] Xóa mảng password trong finally.
- [ ] Không chuyển password sang String nếu không cần thiết.
- [ ] Không in hoặc log password.
- [ ] Không truyền secret qua command line hoặc shell history.
- [ ] Không giữ CommandContext hoặc InputReader sau khi command kết thúc.
- [ ] Phân biệt InputReader và InputProvider.
- [ ] Chọn SystemShellRunner hoặc JLineShellRunner theo nhu cầu terminal.
- [ ] Đã thêm module JLine nếu ứng dụng cần JLine.
- [ ] Command automation không phụ thuộc prompt tương tác.
- [ ] Đã kiểm thử bằng ShellInputProvider.withInput() và withPassword().
- [ ] Test chỉ sử dụng password giả.
- [ ] Đã kiểm tra output, log và exception không làm lộ secret.

## 16. Tự kiểm tra

**Câu 1.** CommandContext cung cấp những thành phần nào để command tương tác với shell?

**Gợi ý trả lời:** parsedInput, commandRegistry, outputWriter và inputReader.

**Câu 2.** Khác biệt chính giữa readInput() và readPassword() là gì?

**Gợi ý trả lời:** readInput() trả về String cho văn bản thường; readPassword() trả về char[] cho dữ liệu mật khẩu.

**Câu 3.** Vì sao nên giữ password trong char[]?

**Gợi ý trả lời:** Mảng ký tự có thể được ghi đè sau khi dùng, giúp giảm thời gian secret tồn tại trong vùng nhớ do ứng dụng kiểm soát. String là immutable.

**Câu 4.** Vì sao cần xóa password trong finally?

**Gợi ý trả lời:** finally vẫn chạy khi validation hoặc service ném exception, giúp cleanup không bị bỏ qua.

**Câu 5.** InputReader khác InputProvider như thế nào?

**Gợi ý trả lời:** InputProvider đưa dòng command vào shell runner; InputReader đọc dữ liệu bổ sung trong lúc command đang chạy.

**Câu 6.** Spring Shell 4.x có thể dùng những implementation InputReader nào?

**Gợi ý trả lời:** ConsoleInputReader dùng Java Console và JLineInputReader dùng JLine LineReader.

**Câu 7.** Làm thế nào mô phỏng password input trong test Spring Shell 4.0.3?

**Gợi ý trả lời:** Tạo ShellInputProvider bằng providerFor(command).withInput(...).withPassword(...).build() rồi gọi ShellTestClient.sendCommand(provider).

**Câu 8.** Có nên dùng readPassword() trong command chạy bằng non-interactive runner không?

**Gợi ý trả lời:** Không nên phụ thuộc vào prompt tương tác trong batch. Hãy lấy secret từ secret provider hoặc nguồn được bảo vệ phù hợp với automation.

## Kết luận

Trong Spring Shell 4.x, CommandContext cung cấp InputReader để command đọc thêm dữ liệu trong lúc thực thi. readInput() dành cho văn bản thông thường và trả về String; readPassword() dành cho mật khẩu và trả về char[]. Khi xử lý password, hãy giữ dữ liệu trong mảng ký tự, giới hạn thời gian sử dụng, xóa trong finally và tuyệt đối không in hoặc ghi log secret.

InputReader khác InputProvider: một bên đọc dữ liệu bổ sung bên trong command, bên kia cung cấp dòng command cho shell runner. ConsoleInputReader và JLineInputReader cho phép cùng một command hoạt động với các kiểu terminal khác nhau mà không cần tự quản lý System.in. Với automation, không phụ thuộc prompt tương tác; hãy dùng nguồn secret được bảo vệ. Cuối cùng, kiểm thử cả input thường và password bằng ShellInputProvider để xác nhận luồng command, cleanup và việc bảo vệ thông tin nhạy cảm.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Reading Input](https://docs.spring.io/spring-shell/reference/commands/reading.html)
- [Spring Shell 4.0.3 — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell 4.0.3 — InputReader API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputReader.html)
- [Spring Shell 4.0.3 — CommandContext API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell 4.0.3 — ConsoleInputReader API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ConsoleInputReader.html)
- [Spring Shell 4.0.3 — JLineInputReader API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/JLineInputReader.html)
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — ShellInputProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html)
- [Spring Shell 4.0.3 — ShellInputProvider.Builder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.Builder.html)
- [Spring Shell 4.x — Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
