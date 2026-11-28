# Console JDK cơ bản so với các khả năng cần môđun JLine

Spring Shell có thể tương tác với terminal bằng API `java.io.Console` có sẵn trong JDK hoặc bằng JLine. Cả hai đều cho phép ứng dụng đọc và ghi văn bản, nhưng mức hỗ trợ cho trải nghiệm nhập lệnh rất khác nhau.

Trong Spring Shell 4.x, thay đổi module làm cho sự khác biệt này trở nên rõ ràng: `spring-shell-core` không còn phụ thuộc JLine và mặc định dùng console của JDK. Nếu cần lịch sử lệnh, chỉnh sửa dòng nhập, tab completion và định dạng văn bản phong phú, ứng dụng cần có module `spring-shell-jline`.

Bài học dùng Spring Shell 4.0.4 làm mốc chính, đồng thời giải thích khác biệt với dòng 3.3.x để tránh áp dụng nhầm hướng dẫn dependency khi nâng cấp.

## 1. Terminal interface là gì?

Terminal interface là lớp giao tiếp giữa ứng dụng dòng lệnh và môi trường terminal nơi ứng dụng chạy. Lớp này chịu trách nhiệm nhận ký tự người dùng nhập, hiển thị output và xử lý một số khả năng của terminal như di chuyển con trỏ, kích thước màn hình, màu sắc hoặc phím điều khiển.

Một ứng dụng CLI đơn giản có thể chỉ cần:

- Hiển thị một dòng thông báo.
- Đọc một dòng văn bản.
- In kết quả xử lý.
- Đọc mật khẩu mà không hiển thị ký tự người dùng gõ.

Một shell tương tác giàu tính năng có thể cần thêm:

- Di chuyển con trỏ và sửa nội dung ở giữa dòng.
- Duyệt lịch sử lệnh bằng phím lên/xuống.
- Gợi ý command hoặc giá trị option khi nhấn Tab.
- Hiển thị màu, kiểu chữ và văn bản có định dạng.
- Nhận biết kích thước terminal và điều chỉnh cách hiển thị.
- Xử lý key binding và tín hiệu terminal.

JDK có sẵn `java.io.Console` cho nhu cầu nhập/xuất cơ bản. JLine bổ sung lớp xử lý terminal và bộ đọc dòng nâng cao để xây dựng trải nghiệm shell tương tác.

## 2. Console của JDK cung cấp những gì?

`java.io.Console` là API tiêu chuẩn từ JDK 6 để đọc và ghi dữ liệu dạng ký tự tới console gắn với JVM.

Lấy đối tượng console qua:

```java
Console console = System.console();
```

Một số phương thức thường dùng:

| Phương thức | Chức năng |
|---|---|
| `System.console()` | Lấy console gắn với JVM, có thể trả về `null` |
| `readLine()` | Đọc một dòng văn bản |
| `readLine(format, args...)` | Hiển thị prompt rồi đọc một dòng |
| `readPassword()` | Đọc mật khẩu mà không echo ký tự |
| `writer()` | Lấy `PrintWriter` để ghi output |
| `printf()` / `format()` | Ghi văn bản theo định dạng |
| `flush()` | Đẩy dữ liệu đang đệm ra console |

Ví dụ một chương trình Java độc lập:

```java
import java.io.Console;
import java.util.Arrays;

public class ConsoleExample {

    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            throw new IllegalStateException(
                "Không tìm thấy console tương tác"
            );
        }

        String username = console.readLine("Tên đăng nhập: ");
        char[] password = console.readPassword("Mật khẩu: ");

        if (password == null) {
            return; // Người dùng đã kết thúc input.
        }

        try {
            console.printf("Xin chào %s%n", username);

            // Xác thực username và password ở đây.
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

`readPassword()` trả về `char[]` thay vì `String`. Sau khi sử dụng, nên ghi đè mảng ký tự để giảm thời gian dữ liệu nhạy cảm tồn tại trong bộ nhớ.

### 2.1. System.console() có thể trả về null

Không phải mọi tiến trình Java đều có console. JDK có thể trả về `null` nếu JVM được chạy mà không có console gắn kèm, ví dụ:

- Ứng dụng chạy từ một background job hoặc scheduler.
- Standard input/output được redirect hoặc nối vào pipe.
- Một số cấu hình chạy từ IDE hoặc công cụ test.
- Tiến trình được khởi chạy trong môi trường không cung cấp terminal.

Vì vậy, không nên gọi `System.console().readLine()` mà không kiểm tra null trước.

Ví dụ xử lý an toàn:

```java
import java.io.Console;

Console console = System.console();

if (console == null) {
    System.err.println(
        "Lệnh này cần terminal tương tác. Hãy truyền dữ liệu qua option."
    );
    return;
}

String value = console.readLine("Giá trị: ");
```

Khi chạy Spring Shell trong môi trường tự động, nên dùng chế độ non-interactive và truyền dữ liệu qua option hoặc argument thay vì phụ thuộc vào `Console`.

### 2.2. Giới hạn của Console

`Console` phù hợp với các thao tác nhập/xuất theo dòng. API này không cung cấp sẵn một bộ soạn thảo dòng lệnh có lịch sử, tab completion hoặc cơ chế định dạng văn bản phong phú.

| Khả năng | JDK Console |
|---|---|
| Đọc một dòng | Có |
| In prompt và output | Có |
| Đọc password không echo | Có |
| Định dạng output cơ bản | Có |
| Lịch sử lệnh | Không có sẵn |
| Sửa dòng bằng phím mũi tên | Không có bộ line editor tích hợp |
| Tab completion | Không có sẵn |
| Key binding tùy chỉnh | Không có sẵn |
| Rich text và điều khiển terminal nâng cao | Hạn chế |

Các giới hạn này không làm `Console` trở nên kém hữu ích. Nếu CLI chỉ cần nhận command hoặc đọc vài giá trị đơn giản, API tiêu chuẩn giúp giảm dependency và giữ ứng dụng gọn.

## 3. JLine bổ sung những khả năng nào?

JLine là thư viện Java chuyên xử lý terminal và nhập dòng tương tác. Spring Shell dùng JLine để cung cấp trải nghiệm REPL nâng cao.

Những khả năng quan trọng gồm:

- **Line editing:** di chuyển con trỏ, chèn/xóa ký tự và chỉnh sửa nội dung ngay trong dòng hiện tại.
- **History:** lưu và duyệt các lệnh đã nhập.
- **Tab completion:** hiển thị các gợi ý command, option hoặc giá trị có thể nhập tiếp.
- **Key bindings:** gán hành động cho các tổ hợp phím.
- **Terminal capabilities:** làm việc với đặc điểm của terminal và các chuỗi điều khiển tương ứng.
- **Styled output:** hỗ trợ màu sắc và định dạng văn bản.
- **Terminal size:** có thể đọc thông tin kích thước để bố trí output phù hợp.

Ví dụ, trong một shell có JLine, người dùng có thể:

```text
shell:>proj<Tab>
project

shell:>project <Tab>
create  delete  list  show

shell:>project li<Tab>
shell:>project list
```

Các giá trị completion cụ thể phụ thuộc vào command và CompletionProvider mà ứng dụng đăng ký. JLine cung cấp cơ chế đọc phím và hiển thị gợi ý; ứng dụng vẫn phải khai báo dữ liệu hoặc logic gợi ý phù hợp.

### 3.1. JLine không thay thế command parser

Cần phân biệt ba trách nhiệm:

1. **JLine** đọc và chỉnh sửa dòng người dùng nhập, xử lý phím và tương tác với terminal.
2. **Spring Shell command parser** phân tích dòng lệnh thành tên command, option và argument.
3. **Command handler** thực hiện nghiệp vụ sau khi tham số đã được bind.

JLine giúp người dùng nhập lệnh thuận tiện hơn. Việc kiểm tra cú pháp, chuyển đổi kiểu, validation và thực thi vẫn do Spring Shell cùng ứng dụng đảm nhiệm.

## 4. Thay đổi module trong Spring Shell 4.x

Trong Spring Shell 4.x, `spring-shell-core` không còn phụ thuộc vào JLine. Core sử dụng console tiêu chuẩn của JDK để cung cấp shell tương tác cơ bản.

Hai runner tương tác chính có thể dùng là:

| Runner | Công nghệ | Đặc điểm |
|---|---|---|
| `SystemShellRunner` | JDK `java.io.Console` | Chức năng shell cơ bản, không cần dependency JLine |
| `JLineShellRunner` | JLine | Có line editing, history, completion và hỗ trợ terminal nâng cao |

`NonInteractiveShellRunner` là runner dành cho cách chạy command từ đối số, script và automation; nó không cần mở REPL tương tác.

Khi JLine không có trên classpath, Spring Shell dùng `SystemShellRunner`. Khi ứng dụng có JLine và cấu hình tương ứng, `JLineShellRunner` được chọn. Với Spring Boot starter của Spring Shell, JLine được tích hợp để cung cấp trải nghiệm tương tác phong phú.

### 4.1. Sơ đồ lựa chọn

```text
Spring Shell 4.x
       |
       v
Có JLine trên classpath?
       |
   +---+---+
   |       |
  Không   Có
   |       |
   v       v
System   JLine
Shell    Shell
Runner   Runner
   |       |
   v       v
JDK      JLine
Console  Terminal
cơ bản   nâng cao
```

Điểm cần nhớ khi nâng cấp: không còn giả định rằng JLine luôn được kéo vào chỉ vì dự án có `spring-shell-core`. Hãy kiểm tra dependency tree và chọn module phù hợp với trải nghiệm terminal mà ứng dụng cần.

## 5. Cấu hình dùng JDK Console trong Spring Shell 4.x

Nếu ứng dụng chỉ cần shell cơ bản, có thể dùng `spring-shell-core` cùng module autoconfigure trong ứng dụng Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-core</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-core-autoconfigure</artifactId>
</dependency>
```

Các dependency này được quản lý phiên bản qua BOM `spring-shell-dependencies` hoặc dependency management tương ứng của dự án.

Với cấu hình này, Spring Shell có thể sử dụng `SystemShellRunner` dựa trên console của JDK. Không cần thêm JLine chỉ để hiển thị prompt, đọc dòng và thực thi command cơ bản.

Phù hợp khi:

- Ứng dụng chỉ có vài command đơn giản.
- Người dùng nhập lệnh theo dòng và không cần lịch sử.
- Muốn giảm số dependency runtime.
- Môi trường triển khai có terminal hỗ trợ Java Console.
- Ưu tiên shell gọn cho công cụ nội bộ.

Nếu dùng Spring Boot, cần bảo đảm có module `spring-shell-core-autoconfigure` hoặc starter tương ứng để cấu hình tự động các bean của Spring Shell.

## 6. Thêm JLine bằng spring-shell-jline

Nếu muốn có trải nghiệm terminal nâng cao, thêm dependency `spring-shell-jline`:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
```

`spring-shell-jline` cung cấp các API và cấu hình để Spring Shell tích hợp với JLine. Module này phụ thuộc vào `spring-shell-core` và thư viện JLine.

Nếu dự án dùng Spring Shell starter đã bao gồm JLine, không cần khai báo lại module này. Nếu tự lắp ghép các module, hãy thêm `spring-shell-jline` một cách tường minh.

Một số starter chuyên biệt có thể chọn terminal provider cho JLine:

| Starter | Terminal provider |
|---|---|
| `spring-shell-starter-jansi` | JLine Jansi |
| `spring-shell-starter-jni` | JLine JNI |
| `spring-shell-starter-jna` | JLine JNA |
| `spring-shell-starter-ffm` | JLine FFM, yêu cầu JDK 22+ |

Các provider này liên quan đến cách JLine tương tác với terminal ở cấp hệ điều hành. Với phần lớn ứng dụng, hãy bắt đầu từ cấu hình JLine cơ bản; chỉ chọn provider chuyên biệt khi có yêu cầu tương thích terminal hoặc native access cụ thể.

### 6.1. Chọn dependency theo cách triển khai

| Cách xây dựng ứng dụng | Dependency phù hợp |
|---|---|
| Dùng JDK Console cơ bản | `spring-shell-core` và `spring-shell-core-autoconfigure` |
| Tự lắp ghép và muốn JLine | Thêm `spring-shell-jline` |
| Dùng Spring Boot starter với JLine | `spring-shell-starter` |
| Cần chọn JLine Jansi provider | `spring-shell-starter-jansi` |
| Cần chọn JLine JNI/JNA provider | Starter tương ứng |

Spring Shell 4.x dựa trên Spring Framework 7 và Spring Boot 4. Khi chuyển từ Spring Shell 3.x, cần nâng nền tảng tương ứng trước khi dùng module mới.

## 7. Sử dụng output writer theo shell context

Trong command, nên ghi output qua API của Spring Shell để output đi qua đúng lớp terminal mà runner đang sử dụng.

Ví dụ với annotation command của Spring Shell 4.x:

```java
import java.io.PrintWriter;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "greet")
    public void greet(CommandContext context) {
        PrintWriter writer = context.outputWriter();

        writer.println("Xin chào từ Spring Shell");
        writer.flush();
    }
}
```

Cách này giữ output gắn với command context. Khi shell dùng JLine, output được đưa qua writer tương ứng thay vì tự ghi trực tiếp vào một stream không được shell quản lý.

Với ví dụ nhỏ hoặc chương trình Java độc lập, `System.out` vẫn là cách ghi output tiêu chuẩn. Tuy nhiên, trong command tương tác, không nên trộn tùy tiện `System.out`, `System.err` và writer của shell vì output có thể chen vào lúc JLine đang vẽ lại prompt hoặc dòng nhập.

### 7.1. Ghi output trong command programmatic

Với command được tạo bằng builder, `CommandContext` cũng cung cấp writer:

```java
Command.builder()
    .name("status")
    .execute(context -> {
        context.outputWriter().println("Application is ready");
        context.outputWriter().flush();
    });
```

Hãy chọn một cơ chế output nhất quán trong command. Nếu cần ghi lỗi, dùng error writer hoặc cơ chế kết quả/lỗi của Spring Shell theo phiên bản đang sử dụng; tránh tự in stack trace ra console như output thông thường.

## 8. Đọc dữ liệu từ người dùng: command input và Console API

Trong Spring Shell, dữ liệu command thông thường nên được nhận qua argument và option. Ví dụ:

```text
user create --name=Lan --role=admin
```

Khai báo tham số command giúp Spring Shell phân tích, chuyển đổi và kiểm tra đầu vào trước khi gọi handler.

Không nên dùng `System.console().readLine()` bên trong command chỉ để hỏi lại giá trị mà command có thể nhận qua option. Cách này có thể xung đột với reader đang điều khiển REPL và không hoạt động trong môi trường không có console.

Nếu ứng dụng thật sự cần một bước nhập tương tác, hãy dùng API prompt/input mà phiên bản Spring Shell và terminal implementation đang hỗ trợ. Với JLine, có thể xây dựng trải nghiệm hỏi đáp nâng cao; với JDK Console, chỉ nên dựa vào các thao tác nhập/xuất cơ bản mà console cung cấp.

Đối với dữ liệu nhạy cảm như mật khẩu, không in giá trị ra output hoặc log. Nếu dùng trực tiếp JDK Console, `readPassword()` tắt echo và trả `char[]`; hãy xóa nội dung mảng sau khi sử dụng. Nếu dùng JLine, dùng cơ chế đọc mật khẩu hoặc prompt bảo mật mà ứng dụng cấu hình.

## 9. Console có đủ cho ứng dụng của bạn không?

Hãy chọn theo trải nghiệm người dùng cần có, không chỉ theo số lượng command.

| Nhu cầu | JDK Console | JLine |
|---|---|---|
| Nhập một dòng và in kết quả | Đủ | Đủ |
| Prompt đơn giản | Đủ | Đủ |
| Đọc mật khẩu không echo | Có API `readPassword()` | Có thể cấu hình input bảo mật |
| Sửa dòng bằng phím mũi tên | Không có sẵn | Có |
| Lịch sử lệnh | Không có sẵn | Có |
| Tab completion | Không có sẵn | Có cơ chế hỗ trợ |
| Màu và styled text | Cơ bản, phụ thuộc output | Hỗ trợ phong phú hơn |
| Key binding tùy chỉnh | Không có sẵn | Có |
| Terminal UI và hiển thị nâng cao | Hạn chế | Có thêm module/công cụ |
| Ít dependency | Tốt | Cần thêm module |

Nếu CLI chỉ dùng cho một nhóm kỹ thuật và chủ yếu được gọi bằng command một lần, JDK Console hoặc non-interactive runner có thể đủ. Nếu CLI là công cụ tương tác hằng ngày, có nhiều command và người dùng cần completion/history, JLine mang lại trải nghiệm phù hợp hơn.

## 10. Lưu ý khi chạy trong IDE, container và CI

Khả năng terminal phụ thuộc vào cách JVM được khởi chạy và cách môi trường cấp standard input/output.

**Trong IDE:** cửa sổ Run có thể không cung cấp Java Console giống một terminal thật. Nếu `System.console()` trả `null`, shell dựa trên JDK Console không thể thực hiện thao tác đọc console theo cách thông thường. Hãy chạy từ terminal tích hợp hoặc kiểm thử trong môi trường tương đương môi trường triển khai.

**Trong container:** cần cấp pseudo-terminal nếu muốn thao tác tương tác. Khi container chạy ở chế độ background hoặc stdin bị đóng, không nên mong đợi prompt hoạt động.

**Trong CI/CD:** thường không cần REPL. Dùng `NonInteractiveShellRunner`, truyền đầy đủ option/argument và để tiến trình kết thúc sau khi thực thi. Không để job chờ nhập liệu.

**Khi redirect output:** terminal có thể không nhận biết được các khả năng như màu sắc hoặc điều khiển con trỏ. Với output dành cho máy đọc, ưu tiên định dạng ổn định như JSON hoặc CSV và tránh ký tự điều khiển terminal.

Nếu dùng JLine, cũng cần kiểm tra hành vi trên terminal thực tế của hệ điều hành mục tiêu. Có JLine trong classpath không đồng nghĩa mọi terminal đều hỗ trợ mọi chuỗi điều khiển hoặc tính năng native giống nhau.

## 11. Khác biệt giữa Spring Shell 3.3 và 4.x

Cần lưu ý thay đổi module khi nâng cấp:

| Nội dung | Spring Shell 3.3.x | Spring Shell 4.x |
|---|---|---|
| JLine trong core | JLine đã được tích hợp trong stack Spring Shell thông thường | Core không còn phụ thuộc JLine |
| Shell tương tác | `InteractiveShellRunner` dựa trên JLine | `SystemShellRunner` hoặc `JLineShellRunner` |
| Console JDK | Có thể dùng JDK API trực tiếp, nhưng trải nghiệm interactive mặc định gắn với JLine | Core mặc định dùng `java.io.Console` |
| Thêm JLine riêng | Thường dùng starter/module của dòng 3.x | Thêm `spring-shell-jline` hoặc starter có JLine |
| Module table | `spring-shell-table` là module riêng | Đã được hợp nhất vào `spring-shell-jline` |
| Cấu hình runner | Có thể có nhiều `ShellRunner` cùng tham gia điều phối | Chỉ một `ShellRunner` được chọn trong application context |

Vì vậy, khi nâng cấp từ 3.3 lên 4.x, hãy kiểm tra dependency tree. Nếu ứng dụng đang dựa vào history, tab completion, styled output hoặc terminal UI của JLine, cần bảo đảm `spring-shell-jline` vẫn có mặt sau khi chuyển sang module mới.

Trong Spring Shell 4.x, ứng dụng không dùng nhiều `ShellRunner` cùng lúc như dòng 3.x. Hãy chọn implementation cần thiết ở thời điểm khởi động.

## 12. Các lỗi thường gặp

**Gọi `System.console()` mà không kiểm tra null.** Console có thể không tồn tại trong IDE, background job hoặc khi stream bị redirect. Kiểm tra trước khi đọc.

**Cho rằng JLine luôn có sẵn trong `spring-shell-core`.** Từ Spring Shell 4, core không phụ thuộc JLine. Thêm `spring-shell-jline` hoặc starter phù hợp.

**Chỉ thêm thư viện JLine nhưng không kiểm tra runner được chọn.** Xác nhận cấu hình auto-configuration và classpath để biết ứng dụng dùng `SystemShellRunner` hay `JLineShellRunner`.

**Mong đợi Console có history và completion.** `java.io.Console` chỉ cung cấp API nhập/xuất theo dòng. Các tính năng line editing, history và completion cần JLine hoặc cơ chế riêng.

**Dùng `System.out` lẫn với writer của shell.** Output có thể chen vào prompt hoặc dòng nhập. Dùng writer từ `CommandContext` cho output của command.

**Đọc stdin trực tiếp trong command handler.** Cách này có thể xung đột với reader của shell và không phù hợp khi chạy non-interactive. Dùng option, argument hoặc input abstraction.

**Coi JLine là bảo đảm mọi terminal có cùng tính năng.** Khả năng native và chuỗi điều khiển phụ thuộc terminal emulator, hệ điều hành và provider. Hãy kiểm thử trên môi trường đích.

**Đưa JLine vào ứng dụng automation không cần REPL.** Nếu job chỉ gọi command rồi kết thúc, không nhất thiết phải thêm dependency terminal tương tác.

## 13. Checklist lựa chọn và cấu hình

- [ ] Xác định người dùng cần nhập/xuất theo dòng hay cần shell tương tác nâng cao.
- [ ] Xác nhận phiên bản Spring Shell đang sử dụng.
- [ ] Với Spring Shell 4.x, nhớ rằng `spring-shell-core` không kéo JLine vào.
- [ ] Chọn `SystemShellRunner` nếu cần console cơ bản và môi trường có JDK Console.
- [ ] Thêm `spring-shell-jline` hoặc starter phù hợp nếu cần JLine.
- [ ] Kiểm tra runner thực tế được chọn khi ứng dụng khởi động.
- [ ] Kiểm tra `System.console()` có thể trả `null`.
- [ ] Dùng `CommandContext.outputWriter()` cho output của command trong API 4.x.
- [ ] Nhận dữ liệu qua option/argument thay vì tự đọc stdin trong command.
- [ ] Dùng `readPassword()` hoặc cơ chế tương đương cho dữ liệu bí mật.
- [ ] Không trộn output trực tiếp với writer của shell khi REPL đang chạy.
- [ ] Kiểm thử trên terminal thật, IDE, container và môi trường CI.
- [ ] Không thêm dependency JLine nếu ứng dụng chỉ chạy non-interactive và không cần tính năng terminal nâng cao.

## 14. Tài liệu tham khảo chính thức

- [Spring Shell 4.0.4 — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi module, việc tách JLine khỏi core, `SystemShellRunner`, `JLineShellRunner` và các khả năng khác nhau.
- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html): lựa chọn runner tương tác và non-interactive.
- [Spring Shell 4.0.3 — Building](https://docs.spring.io/spring-shell/reference/building.html): starter, terminal provider và dependency cho JLine.
- [Spring Shell — Writing](https://docs.spring.io/spring-shell/reference/3.3-SNAPSHOT/commands/writing.html): cách ghi output qua `System.out`, `Terminal` và command context.
- [JDK 21 — java.io.Console](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Console.html): API console, `System.console()`, `readLine()` và `readPassword()`.
- [Spring Shell 4.0.3 API — SystemShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/SystemShellRunner.html): runner tương tác dựa trên console của JDK.
- [Spring Shell 4.0.3 API — JLineShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/JLineShellRunner.html): runner tương tác sử dụng JLine.

JDK Console phù hợp với CLI có nhu cầu nhập/xuất cơ bản và muốn giữ dependency tối thiểu. JLine phù hợp với shell tương tác cần chỉnh sửa dòng, history, completion và định dạng terminal phong phú. Trong Spring Shell 4.x, hãy quyết định rõ runner và dependency cần dùng vì JLine đã được tách khỏi `spring-shell-core`.

