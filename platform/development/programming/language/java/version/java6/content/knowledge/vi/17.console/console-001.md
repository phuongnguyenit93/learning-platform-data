# System.console và truy cập thiết bị nhập xuất tương tác

## 1. Console trong Java là gì?

Khi viết chương trình chạy từ terminal, ứng dụng thường cần hỏi tên người dùng, nhận một dòng lệnh, xác nhận lựa chọn hoặc nhập dữ liệu bí mật. Java hỗ trợ hai cơ chế gần nhau nhưng **khác mục đích**:

- `System.in`, `System.out` và `System.err` là các **standard streams**. Chúng có thể nối với terminal, nhưng cũng có thể được chuyển hướng sang file hoặc pipeline. Nhờ đó chương trình phù hợp với cả thao tác trực tiếp và tự động hóa.
- `System.console()` trả về đối tượng `java.io.Console` gắn với **console của JVM hiện tại, nếu có**. `Console` cung cấp các thao tác theo dòng như `readLine(...)`, in prompt dạng format và `readPassword(...)` để nhập dữ liệu mà không echo ký tự ra màn hình.

Điểm quan trọng nhất của chủ đề **“System.console và truy cập thiết bị nhập xuất tương tác”**: **`System.console()` có thể trả về `null`**. Chương trình không được giả định môi trường thực thi luôn có một thiết bị tương tác.

~~~text
Chương trình Java
       |
       +--> System.in / System.out / System.err
       |         |
       |         +--> terminal, file hoặc pipeline
       |
       +--> System.console()
                 |
                 +--> Console hiện hữu: readLine, readPassword, writer, flush...
                 |
                 +--> null: IDE, service, không có terminal phù hợp,
                             hoặc chuyển hướng standard streams
~~~

`System.console()` và `java.io.Console` là **API chính thức vẫn được hỗ trợ trong Java hiện đại**. Nội dung thực hành dưới đây dùng **Java 17+**, đồng thời phân biệt một số API bổ sung ở JDK mới, không sử dụng cách làm đã lỗi thời.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định khi nào ứng dụng có một `Console` tương tác và xử lý khi không có.
2. Đọc một dòng văn bản bằng `Console.readLine(...)` và hiểu kết quả `null` tại end-of-input.
3. Đọc dữ liệu nhạy cảm qua `Console.readPassword(...)`, không hiển thị hoặc ghi log bí mật, và xóa `char[]` trong `finally`.
4. Phân biệt console với standard input/output để thiết kế cả lệnh tương tác và chương trình dùng pipeline.
5. Kiểm thử logic CLI mà **không cần nhập mật khẩu thật** hoặc buộc CI phải có terminal.

## 2. Khi nào System.console() có giá trị và khi nào trả null?

`System.console()` trả về đối tượng `Console` duy nhất gắn với JVM nếu môi trường cung cấp; nếu không sẽ trả `null`. Khả năng có console phụ thuộc hệ điều hành, terminal, cách JVM được khởi động và việc chuyển hướng standard streams.

| Môi trường chạy | Điều cần dự kiến |
| --- | --- |
| Mở một terminal tương tác rồi chạy `java ConsoleDemo` trực tiếp | Thường có console; có thể hiển thị prompt và nhận input trực tiếp |
| Chạy qua IDE Run/Debug console | Có thể `null`; màn hình output trong IDE không nhất thiết là terminal thực của JVM |
| Chạy trong CI, job scheduler hoặc tiến trình nền | Thường không có console tương tác |
| Chuyển `stdin` từ file/pipe hoặc chuyển `stdout` sang file/pipe | Không nên kỳ vọng có `Console`; Java SE 26 mô tả trường hợp chuyển hướng là không có console |
| Shell/terminal giả lập, container hoặc remote terminal | Phụ thuộc cách cấp phát terminal và gắn các luồng; cần kiểm tra trong môi trường thực |
| Chạy test dùng fake input | Không cần console thật; nên tách logic đối thoại ra khỏi adapter `Console` |

**Không suy ra `System.console() != null` chỉ vì `System.in` đọc được dữ liệu.** Một pipeline có thể cung cấp dữ liệu cho `System.in` dù không có console tương tác.

Cũng không nên xem `System.console() == null` là lỗi Java hoặc bằng chứng phiên bản JDK không hỗ trợ Console. Nó là một kết quả hợp lệ của API, thường phản ánh môi trường chạy.

### 2.1. Probe nhỏ để hiểu môi trường của mình

Chỉ cần hai dòng Java sau trong một `main` đang chạy:

~~~java
Console console = System.console();
System.out.println("console-present=" + (console != null));
~~~

Đây là **đoạn minh họa**, cần `import java.io.Console;` và một phương thức `main`; chương trình hoàn chỉnh nằm ở mục 5.

Hai dạng kết quả đều đúng tùy môi trường:

~~~text
console-present=true
~~~

hoặc:

~~~text
console-present=false
~~~

Không chọn `true` hay `false` làm assertion cố định cho mọi IDE, hệ điều hành và runner. Trong lần kiểm thử trực tiếp trên terminal công cụ của OpenJDK 24, probe trả `true`; kết quả này không có nghĩa mọi tiến trình Java đều có Console.

### 2.2. Console không phải một đối tượng bạn tự khởi tạo

`Console` do nền tảng JVM quản lý, lấy qua `System.console()`. Chương trình không tự `new Console()` để biến một pipe thành terminal. Nếu cần test logic tương tác, cách thích hợp là tạo **interface của ứng dụng** rồi cung cấp implementation adapter và fake input; không giả lập bằng cách cố subclass `java.io.Console`.

Trên Java SE 26, `Console` được khai báo dưới dạng **sealed class**. Dù dùng Java 17, chiến lược test thông qua interface của riêng ứng dụng vẫn phù hợp và không lệ thuộc chi tiết triển khai của JVM.

## 3. Những API cần biết của java.io.Console

| API | Công dụng và chú ý |
| --- | --- |
| `System.console()` | Lấy console hiện tại hoặc `null` |
| `console.readLine()` | Đọc một dòng văn bản, không kèm ký tự xuống dòng; trả `null` tại EOF |
| `console.readLine(String format, Object... args)` | In prompt theo cú pháp format rồi đọc một dòng |
| `console.readPassword()` | Đọc một dòng bí mật, cố tình tắt echo; trả `char[]` hoặc `null` |
| `console.readPassword(String format, Object... args)` | Hiển thị prompt rồi đọc input bí mật không echo |
| `console.printf(String format, Object... args)` | In thông báo dạng format |
| `console.format(String format, Object... args)` | Tương tự `printf`, trả lại `Console` để có thể nối các lời gọi |
| `console.writer()` | Lấy `PrintWriter` của console |
| `console.reader()` | Lấy `Reader` của console |
| `console.flush()` | Flush output buffer |
| `console.charset()` | Từ Java 17: trả `Charset` mà Console dùng cho thao tác ghi output |
| `console.isTerminal()` | Từ Java 22: kiểm tra console instance là terminal; **không dùng trong code target Java 17** |

Các overload có `Locale` cho `format`, `printf`, `readLine` và `readPassword` được hỗ trợ trên JDK mới (ví dụ Java SE 26), nhưng **không bắt buộc** trong ví dụ Java 17. Khi target Java 17, chỉ dùng các overload có sẵn ở release đó.

### 3.1. Prompt được format, không phải in nguyên văn

`console.readLine("Tên: ")` là một lời gọi hợp lệ, vì format không có specifier. Tuy nhiên nếu prompt xây từ dữ liệu tùy ý, nó có thể chứa dấu `%` và vô tình bị diễn giải là format string.

Hãy để format string cố định và truyền nội dung prompt thành đối số:

~~~java
String label = "Nhập mã 100% hợp lệ: ";
String answer = console.readLine("%s", label);
~~~

Đây là **đoạn minh họa** trong ngữ cảnh đã có biến `Console console` khác `null`. Cách làm này tránh nhầm `%` trong `label` với cú pháp `Formatter`.

Ngược lại, `console.readLine("Số lượng %d: ", 3)` dùng format có chủ đích. Với format sai hoặc thiếu đối số, các phương thức định dạng có thể ném `IllegalFormatException`. Bài lab chính dùng `"%s"` và `"%s%n"` để in chuỗi an toàn theo đúng vai trò format.

### 3.2. readLine: EOF khác chuỗi rỗng

`readLine(...)` có thể trả về:

- Một chuỗi không rỗng, ví dụ `"Linh"`.
- Chuỗi rỗng `""` khi người dùng chỉ nhấn Enter.
- `null` khi đã đến end-of-input (EOF), chẳng hạn gửi tín hiệu kết thúc input trên terminal.

Không viết `console.readLine(...).strip()` ngay nếu chưa kiểm tra `null`. Một input rỗng là **dữ liệu đầu vào**, còn `null` là **điều kiện kết thúc dòng nhập**. Quyết định xử lý nên rõ: yêu cầu nhập lại, báo lỗi, hoặc kết thúc chương trình.

### 3.3. readPassword: char[] và không echo

`readPassword(...)` trả về một mảng `char[]`, thay vì `String`. Đó là thiết kế giúp ứng dụng có thể **chủ động ghi đè bộ nhớ của chính mảng ấy** khi không còn cần dữ liệu bí mật.

~~~java
char[] password = console.readPassword("%s", "Mật khẩu: ");
if (password == null) {
    // End-of-input: không có mật khẩu để xử lý.
    return;
}
try {
    // Xử lý thông tin bí mật tại đây, không log hoặc in password.
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là **đoạn trích minh họa**, không phải chương trình độc lập. `readPassword` không echo ký tự khi người dùng gõ trong console phù hợp; khi xong, `Arrays.fill(password, '\0')` xóa nội dung của **mảng do phương thức trả về**.

Lưu ý bảo mật:

- **Không** `System.out.println(password)` hoặc `new String(password)` để tiện debug. Việc tạo `String` gây thêm bản sao bất biến không thể xóa chủ động một cách đáng tin cậy.
- **Không** tự động chuyển sang `Scanner(System.in).nextLine()` để nhận mật khẩu khi `System.console() == null`; cách đó có thể echo input và làm lộ dữ liệu trong terminal/log/pipeline.
- `char[]` và `Arrays.fill` giảm thời gian dữ liệu còn trong một mảng, **không bảo đảm toàn bộ các bản sao trong OS/JVM/terminal đều đã bị xóa**. Với xác thực thật phải chọn cơ chế xử lý credential và kênh truyền phù hợp.
- `readPassword() == null` là EOF, còn mảng ký tự độ dài 0 nghĩa là người dùng đã nhập dòng rỗng. Hai trường hợp có thể cần xử lý khác nhau.
- Không đưa bí mật vào command-line arguments, environment, lịch sử shell hoặc URL chỉ để tránh lời gọi `readPassword`.

## 4. Thiết kế chương trình tương tác có thể kiểm thử

Một lỗi phổ biến là viết toàn bộ logic CLI trong `main`, gọi trực tiếp `System.console().readLine(...)` rồi rất khó thử nghiệm trong CI, IDE hay terminal không tương tác.

Thiết kế tốt hơn là tách:

~~~text
                 +----------------------+
Terminal thật --->| SystemTextConsole    |
                  | adapter dùng Console |
                  +----------+-----------+
                             |
                             v
                      TextConsole interface
                             |
                             v
                     conversation(TextConsole)
                             ^
                             |
                  +----------+-----------+
Unit tests ------>| FakeConsole           |
                  | input xác định sẵn    |
                  +----------------------+
~~~

`TextConsole` là interface của **ứng dụng**, không phải interface có sẵn trong Java SE. Mục tiêu là kiểm thử **quy tắc xử lý input**, thông báo đầu ra và việc xóa password buffer **mà không phụ thuộc console thật**.

Như vậy có hai loại kiểm thử:

1. **Unit test**: gọi `conversation(...)` với `FakeConsole`, hoàn toàn không cần TTY.
2. **Integration/manual test**: chạy `java ConsoleDemo` trong terminal thật để kiểm tra prompting, khả năng tắt echo, charset và hành vi EOF của hệ điều hành.

Không dùng unit test giả lập như bằng chứng rằng tất cả terminal Windows/Linux/macOS sẽ hiển thị prompt giống hệt nhau; đó là trách nhiệm của integration/manual test.

## 5. Chương trình Java 17+ chạy được: ConsoleDemo.java

Tạo tệp `ConsoleDemo.java`:

~~~java
import java.io.Console;
import java.util.Arrays;

public final class ConsoleDemo {
    interface TextConsole {
        String ask(String prompt);
        char[] askSecret(String prompt);
        void say(String message);
    }

    static final class SystemTextConsole implements TextConsole {
        private final Console console;

        SystemTextConsole(Console console) {
            this.console = console;
        }

        @Override
        public String ask(String prompt) {
            return console.readLine("%s", prompt);
        }

        @Override
        public char[] askSecret(String prompt) {
            return console.readPassword("%s", prompt);
        }

        @Override
        public void say(String message) {
            console.printf("%s%n", message);
            console.flush();
        }
    }

    static void conversation(TextConsole io) {
        String name = io.ask("Tên của bạn: ");
        if (name == null) {
            io.say("Đã kết thúc nhập.");
            return;
        }
        name = name.strip();
        if (name.isEmpty()) {
            io.say("Tên không được rỗng.");
            return;
        }

        char[] password = io.askSecret("Mật khẩu: ");
        if (password == null) {
            io.say("Đã kết thúc nhập.");
            return;
        }
        try {
            io.say("Xin chào, " + name + ".");
            io.say("Đã nhận dữ liệu bí mật.");
        } finally {
            Arrays.fill(password, '\0');
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("--check")) {
            System.out.println("console-present=" + (System.console() != null));
            return;
        }
        Console console = System.console();
        if (console == null) {
            System.err.println("Không có console tương tác; hãy chạy trong terminal không chuyển hướng stdin/stdout.");
            return;
        }
        conversation(new SystemTextConsole(console));
    }
}
~~~

### 5.1. Phân tích đường chạy

- Chương trình không gọi `readLine` hay `readPassword` trước khi kiểm tra `System.console() != null`.
- `--check` là chế độ **không yêu cầu nhập input**, dùng để kiểm tra khả năng có console của môi trường.
- `SystemTextConsole` chỉ là adapter: `ask` gọi `readLine("%s", prompt)`, `askSecret` gọi `readPassword("%s", prompt)`, `say` dùng `printf` và `flush`.
- `conversation` chỉ biết `TextConsole`, không biết hệ điều hành đang dùng terminal thật, IDE hay fake. Phần này vì thế có thể test tự động.
- `name == null` dẫn tới kết thúc nhẹ nhàng do EOF; `name.strip()` bỏ khoảng trắng biên; tên rỗng bị từ chối.
- Mật khẩu `null` cũng được xử lý như EOF.
- `Arrays.fill(password, '\0')` nằm trong `finally` để vẫn chạy nếu có lỗi trong phần xử lý sau khi đã nhận mảng.

**Giới hạn demo:** chương trình chỉ minh họa **thu nhận dữ liệu** và bảo vệ việc nhập bí mật khỏi echo/log; nó **không phải hệ thống xác thực mật khẩu**. Thông báo “Đã nhận dữ liệu bí mật” không đồng nghĩa mật khẩu hợp lệ. Nếu ứng dụng thật yêu cầu mật khẩu không rỗng, hãy kiểm tra `password.length == 0` ở bên trong `try` và báo lỗi mà không in password.

### 5.2. Vì sao không ghi trực tiếp readPassword trong main?

Có thể viết một chương trình đơn giản với `Console c = System.console();` rồi gọi `c.readPassword(...)` ngay sau khi kiểm tra null. Nhưng việc tách `TextConsole` đem lại ba lợi ích thực tế:

1. CI có thể tự động cung cấp input giả, không phụ thuộc TTY.
2. Test có thể kiểm tra `Arrays.fill` đã xóa đúng mảng secret.
3. Khi muốn đổi UI hoặc chạy trong môi trường không có terminal, bạn thay **adapter** thay vì sửa logic nghiệp vụ; tuy nhiên không được tự ý hạ cấp bảo mật khi cần nhập bí mật.

## 6. Unit test độc lập, không nhập mật khẩu thật

Tạo tệp `ConsoleDemoTest.java` **cùng thư mục** với `ConsoleDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class ConsoleDemoTest {
    static final class FakeConsole implements ConsoleDemo.TextConsole {
        final String name;
        final char[] secret;
        final List<String> messages = new ArrayList<>();
        int secretReads;

        FakeConsole(String name, char[] secret) {
            this.name = name;
            this.secret = secret;
        }

        public String ask(String prompt) { return name; }
        public char[] askSecret(String prompt) {
            secretReads++;
            return secret;
        }
        public void say(String message) { messages.add(message); }
    }

    static void require(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    public static void main(String[] args) {
        char[] dummy = {'d', 'e', 'm', 'o'};
        FakeConsole normal = new FakeConsole(" Linh ", dummy);
        ConsoleDemo.conversation(normal);
        require(normal.messages.equals(List.of(
                "Xin chào, Linh.", "Đã nhận dữ liệu bí mật.")), "normal messages");
        require(Arrays.equals(dummy, new char[4]), "secret not cleared");
        System.out.println("normal=PASS");

        FakeConsole eofName = new FakeConsole(null, null);
        ConsoleDemo.conversation(eofName);
        require(eofName.messages.equals(List.of("Đã kết thúc nhập.")), "name EOF");
        require(eofName.secretReads == 0, "read secret after name EOF");
        System.out.println("name-eof=PASS");

        FakeConsole blank = new FakeConsole("   ", null);
        ConsoleDemo.conversation(blank);
        require(blank.messages.equals(List.of("Tên không được rỗng.")), "blank name");
        require(blank.secretReads == 0, "read secret after blank name");
        System.out.println("blank-name=PASS");

        FakeConsole eofSecret = new FakeConsole("An", null);
        ConsoleDemo.conversation(eofSecret);
        require(eofSecret.messages.equals(List.of("Đã kết thúc nhập.")), "secret EOF");
        require(eofSecret.secretReads == 1, "missing secret read");
        System.out.println("password-eof=PASS");
    }
}
~~~

**Các assert kiểm tra gì?**

| Test | Điều kiện đầu vào | Điều kiện cần chứng minh |
| --- | --- | --- |
| `normal` | `" Linh "` và mảng ký tự giả | Tên được trim bằng `strip()`, thông báo đúng, mảng `char[]` được ghi đè thành `'\0'` |
| `name-eof` | `name == null` | Kết thúc, không gọi `askSecret(...)` |
| `blank-name` | Chỉ chứa khoảng trắng | Báo tên rỗng, không gọi `askSecret(...)` |
| `password-eof` | Tên hợp lệ nhưng `secret == null` | Có gọi thao tác đọc secret, xử lý EOF thay vì dùng mảng null |

`FakeConsole` **không ghi mật khẩu ra stdout**, chỉ cung cấp một mảng ký tự giả `{'d','e','m','o'}`. Test đầu tiên giữ tham chiếu mảng đó và assert bằng `Arrays.equals(dummy, new char[4])` để xác nhận toàn bộ vị trí đã được ghi đè bằng ký tự NUL sau xử lý.

Test không khẳng định rằng FakeConsole thực sự tắt echo: đó là hành vi phải kiểm thử với `Console.readPassword` trên một terminal thật. Nó chỉ bảo đảm logic ứng dụng **gọi đúng API của abstraction** và không vô tình in/lưu giá trị giả.

## 7. Lệnh build và stdout đã kiểm chứng

Trong thư mục chứa hai tệp Java:

~~~bash
javac -encoding UTF-8 --release 17 ConsoleDemo.java ConsoleDemoTest.java
java ConsoleDemoTest
~~~

**Kết quả chuẩn từ chương trình kiểm thử**:

~~~text
normal=PASS
name-eof=PASS
blank-name=PASS
password-eof=PASS
~~~

Bốn trường hợp đã được biên dịch/chạy với **OpenJDK 24**, mục tiêu `--release 17`, và tất cả assertions đạt. Chương trình test hoàn toàn không cần một `Console` thật.

Để kiểm tra sự hiện diện của console, chạy:

~~~bash
java ConsoleDemo --check
~~~

Kết quả là **một trong hai giá trị**, tùy môi trường, không phải stdout cố định của mọi máy:

~~~text
console-present=true
~~~

hoặc:

~~~text
console-present=false
~~~

Khi chạy probe trên môi trường kiểm thử thực tế nói trên, kết quả là `console-present=true`. Nếu chạy từ IDE hoặc một tiến trình không có terminal tương tác, bạn có thể nhận `false`. **Đừng biến kết quả probe thành assertion bắt buộc** trong unit test.

### 7.1. Thử thao tác tương tác thật

Mở một terminal tương tác thông thường (không chuyển hướng stdin/stdout), chạy:

~~~bash
java ConsoleDemo
~~~

Ví dụ minh họa một phiên tương tác, giả định người dùng gõ tên `Linh` và một mật khẩu giả:

~~~text
Tên của bạn: Linh
Mật khẩu:
Xin chào, Linh.
Đã nhận dữ liệu bí mật.
~~~

Đây là **transcript mô tả**, không phải stdout cố định của một test tự động. Người dùng nhập tên sẽ thấy ký tự được echo ở dòng `Tên của bạn`; khi nhập mật khẩu, `readPassword` không echo các ký tự đã gõ. Nếu Console không tồn tại, chương trình in thông báo lỗi vào `System.err` rồi dừng thay vì tiếp tục đọc bằng một API không bảo đảm ẩn mật khẩu.

Nếu người dùng gửi EOF khi được hỏi tên hoặc mật khẩu, chương trình in `Đã kết thúc nhập.`. Nếu tên chỉ có dấu cách, chương trình in `Tên không được rỗng.`. Không phải tình huống nào cũng đi đến hai dòng `Xin chào...` và `Đã nhận dữ liệu bí mật.`.

## 8. Console và standard input: dùng đúng loại luồng

Có một khác biệt kiến trúc quan trọng:

- **Console** là API dành cho tương tác qua terminal. Nó cung cấp việc hiển thị prompt và đọc password không echo.
- **`System.in`** là luồng byte nhập tiêu chuẩn; nó có thể nhận dữ liệu từ bàn phím, file hay pipeline. Chúng ta có thể giải mã thành text với `InputStreamReader` và `BufferedReader` hoặc sử dụng `Scanner`.
- **`System.out`** là luồng byte xuất tiêu chuẩn, phù hợp với output của chương trình trong automation.
- **`System.err`** là luồng lỗi, thường dùng thông báo chẩn đoán ngay cả khi output chính được chuyển hướng.

Điểm đáng lưu ý: `System.console().reader()` và `System.in` đều có thể cuối cùng liên quan đến thiết bị đầu vào, nhưng **không nên trộn các bộ đệm/reader cùng đọc thiết bị đó một cách tùy tiện**. Dùng một cơ chế đọc nhất quán cho mỗi luồng input.

### 8.1. Ví dụ đúng cho đầu vào từ file hoặc pipeline

Tạo `PipeText.java`:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class PipeText {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line = input.readLine();
        System.out.println(line == null ? "input=EOF" : "input=" + line);
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 --release 17 PipeText.java
~~~

Ví dụ Linux/macOS Bash:

~~~bash
printf 'hello\n' | java PipeText
~~~

Kết quả:

~~~text
input=hello
~~~

Trên Windows `cmd.exe`, có thể ghi file văn bản UTF-8 (không có BOM) chứa `hello` và dùng redirect:

~~~bat
java PipeText < input.txt
~~~

Đoạn `PipeText` đã được kiểm tra với OpenJDK 24 bằng input file UTF-8 không BOM, và in `input=hello`.

**Vì sao không dùng Console cho việc này?** Trong pipeline hoặc khi redirect input, chương trình có thể không có `Console`, nhưng `System.in` vẫn nhận dữ liệu rất tốt. Với input dùng trong CI, batch job hoặc command-line pipeline, dùng standard streams thường phù hợp hơn.

**Lưu ý về encoding:** `InputStreamReader(System.in, StandardCharsets.UTF_8)` yêu cầu bên gửi dữ liệu cung cấp **UTF-8**. Những môi trường shell cũ có thể phát sinh BOM hoặc dùng encoding khác; nếu chuyển dữ liệu từ Windows PowerShell 5.1 bằng pipeline sang native process, cần kiểm tra encoding thực tế thay vì giả định mọi byte đều là UTF-8 không BOM. Không khuyến khích tự loại bỏ mọi ký tự U+FEFF một cách tùy tiện khi dữ liệu đầu vào có thể chứa ký tự ấy với ý nghĩa hợp lệ.

### 8.2. Có nên fallback từ Console sang Scanner?

Tùy mục đích:

| Dữ liệu cần đọc | Khi `System.console() == null` |
| --- | --- |
| Tên, ID công khai hoặc dòng text cho automation | Có thể thiết kế fallback riêng đọc `System.in`/`BufferedReader`, với charset và EOF rõ ràng |
| Mật khẩu, token hoặc dữ liệu bí mật cần **không echo** | **Không** tự động chuyển sang `Scanner(System.in)` như thể có cùng bảo vệ; từ chối hoặc dùng cơ chế bí mật đã được thiết kế phù hợp |
| Chương trình CLI phải có tương tác và xác nhận của người dùng | Thông báo “yêu cầu terminal tương tác”, không silently chọn mặc định |
| Lệnh chuyên dùng trong pipeline | Ưu tiên standard input/output; không phụ thuộc `Console` ngay từ đầu |

Việc đọc mật khẩu qua `System.in` có thể là một lựa chọn trong **giao thức tự động hóa được thiết kế riêng**, nhưng nó không có đảm bảo tắt echo như `readPassword` và cần quản lý nơi cung cấp input, quyền truy cập, logs và secret storage. Không được gọi nó là “fallback tương đương về bảo mật”.

## 9. Reader, Writer, flush và charset

### 9.1. Console.reader() và Console.writer()

`console.reader()` trả một `Reader` của console; `console.writer()` trả một `PrintWriter` để ghi ra console. Có thể dùng khi cần làm việc ở mức stream thay vì một dòng `readLine`.

Ví dụ **đoạn trích**, chỉ chạy khi đã có `Console console`:

~~~java
console.writer().println("Bắt đầu phiên tương tác.");
console.flush();
String answer = console.readLine("%s", "Tiếp tục? ");
~~~

`flush()` giúp đẩy output còn trong buffer ra thiết bị. Nếu ghi output không có newline và muốn người dùng nhìn thấy prompt ngay, nên bảo đảm flush ở nơi phù hợp. Các thao tác `Console.readLine(prompt)` hoặc `readPassword(prompt)` đã được thiết kế cho việc đưa prompt trước khi đọc.

Đừng đóng `System.in` hoặc `System.out` tùy tiện trong một thư viện tái sử dụng: chúng là các luồng chia sẻ cấp JVM. Theo API hiện hành, đóng reader/writer lấy từ `Console` không đóng underlying streams, nhưng code ứng dụng vẫn nên coi đây là tài nguyên **do JVM quản lý**, không sở hữu để tùy ý thay thế.

### 9.2. Console.charset() và sự khác nhau giữa input/output encoding

`console.charset()` được hỗ trợ từ **Java 17**. Trên Java SE 26, API mô tả đây là `Charset` dùng cho **thao tác ghi** của Console, và nó không nhất thiết bằng `Charset.defaultCharset()`. Tài liệu hiện hành cũng mô tả `stdin.encoding` và `stdout.encoding` ảnh hưởng đến việc đọc/ghi.

Đừng ngầm giả định:

~~~java
// Suy luận không đáng tin: console charset luôn giống default charset.
boolean alwaysSame =
        console.charset().equals(java.nio.charset.Charset.defaultCharset());
~~~

Đây là **đoạn minh họa**, biến `alwaysSame` có thể `true` hoặc `false` tùy runtime. Khi thiết kế pipeline, hãy chọn encoding rõ ràng cho `System.in` và file; không dùng charset của Console để diễn giải mọi nguồn dữ liệu ngoài terminal.

### 9.3. Console.isTerminal(): API mới hơn, không có trong Java 17

`console.isTerminal()` được bổ sung từ **Java 22**. Nếu source code được biên dịch với `--release 17`, không thể gọi phương thức này.

Trên **Java SE 26**, tài liệu `Console.isTerminal()` nói nó luôn trả `true` khi đã có `Console`, vì `System.console()` chỉ cung cấp console khi cả standard input lẫn output không bị chuyển hướng và đang chạy với terminal tương tác. Đừng dùng kết luận đó để suy đoán hành vi mọi triển khai/JDK cũ hoặc đưa lệnh `isTerminal()` vào ví dụ Java 17.

Đối với ứng dụng Java 17+ trong bài, cách tương thích nhất để biết có Console dùng được hay không là **kiểm tra null của `System.console()`** và xử lý rõ các môi trường không có.

## 10. EOF, lỗi I/O và trường hợp người dùng hủy

Phần xử lý lỗi đầu vào không nên trộn lẫn:

| Trường hợp | Dấu hiệu | Xử lý khuyến nghị |
| --- | --- | --- |
| Không có console gắn với JVM | `System.console() == null` | Báo môi trường thiếu terminal; không gọi `Console` |
| Người dùng gửi EOF | `readLine(...) == null` hoặc `readPassword(...) == null` | Kết thúc hoặc hủy phiên một cách rõ ràng |
| Người dùng nhấn Enter không nhập gì | `""` hoặc `char[0]` | Xử lý như input rỗng, **không** nhầm là EOF |
| Nhập format prompt không hợp lệ | `IllegalFormatException` | Sửa format string hoặc bỏ dữ liệu người dùng ra khỏi format |
| Lỗi khi đọc/ghi console | `IOError` | Ghi nhận ở ranh giới CLI; xử lý/thoát theo chính sách ứng dụng |
| Có console nhưng terminal không hiển thị như mong đợi | Khác OS, terminal settings, remote environment | Kiểm tra thủ công trên terminal đích và đường kết nối |

`Console.readLine(...)` và `Console.readPassword(...)` có thể ném `java.io.IOError` khi gặp lỗi I/O. Đây là một `Error`, **không phải `IOException` checked exception**. Đừng nghĩ một `catch (IOException e)` quanh `readLine` sẽ tự bắt được mọi lỗi console.

Các hàm đọc có thể **block chờ input**. Việc gọi trong request handler/server thread là một lựa chọn thiết kế nguy hiểm nếu không có người dùng tương tác. Đừng biến một ứng dụng server/CI thành chương trình chờ bàn phím vô hạn chỉ vì gọi `System.console()` mà không kiểm tra bối cảnh.

### 10.1. Prompt có thể chia sẻ quyền truy cập giữa các thread

Theo API hiện hành, các thao tác đọc/ghi của `Console` được đồng bộ hóa để bảo đảm các thao tác quan trọng hoàn tất theo tính nguyên tử. Vì vậy nhiều thread cùng gọi `readLine`, `readPassword`, `printf` hoặc thao tác trên reader/writer có thể **chờ nhau**.

Tính đồng bộ của từng thao tác **không** tự biến toàn bộ hội thoại gồm “hỏi tên → hỏi mật khẩu → in thông báo” thành transaction bất khả phân. Nếu nhiều thread cùng hỏi người dùng, hãy dùng một cơ chế điều phối phiên tương tác (ví dụ một luồng CLI chuyên trách) để prompt không xen kẽ, thay vì hy vọng console tự phối hợp mọi bước.

## 11. Bảo mật khi tương tác với dữ liệu bí mật

Có ba lớp cần phân biệt:

1. **Hiển thị trên terminal**: `readPassword` giúp nhập mà không echo ký tự, tránh lộ mắt nhìn hoặc terminal transcript theo cách nhập text thông thường.
2. **Bộ nhớ ứng dụng**: mảng `char[]` có thể được chủ động xóa bằng `Arrays.fill` ngay sau xử lý. Không tạo thêm bản sao không cần thiết, nhất là `String`.
3. **Hệ thống và quy trình**: đường truyền remote terminal, secret store, logging, crash reports, tiến trình và quyền hệ điều hành cần được quản lý riêng. `readPassword` **không phải** cơ chế mã hóa hay xác thực hoàn chỉnh.

Ví dụ ở mục 5 chỉ kiểm tra thao tác nhập và việc dọn buffer, không thực hiện xác thực. Một chương trình production nên chuyển `char[]` tới API xác thực phù hợp trong `try`, tránh giữ tham chiếu lâu hoặc in thông tin nhạy cảm ra exception/log.

Cách kiểm thử không cần bí mật thật: dùng các ký tự giả cố định hoặc mảng `char[]` do test tạo. Một test có ích phải xác nhận không ai vô tình gọi `new String(password)` để in/debug và phải kiểm tra mảng được xóa trong `finally`.

### 11.1. Không cố “giả lập TTY bảo mật” bằng việc đổi standard streams

`System.setIn(...)` và `System.setOut(...)` thay các stream của JVM. Chúng **không** bảo đảm `System.console()` xuất hiện, không cấp phát terminal và không làm `Scanner` tự tắt echo.

Trong unit test, đừng phải thay global streams chỉ để test một chức năng hỏi tên/mật khẩu. Interface `TextConsole` và fake trong ví dụ giúp giữ test độc lập, không làm ảnh hưởng test khác đang chạy cùng JVM.

### 11.2. Không đặt bí mật vào format string

`console.readPassword("%s", "Mật khẩu: ")` dùng prompt công khai. Không xây prompt chứa sẵn token/password hoặc những giá trị nhạy cảm rồi in ra terminal. Cũng không dùng `console.printf("%s", secret)` cho dữ liệu cần giữ bí mật. Các thao tác output và input secret phải có mục đích khác nhau.

## 12. Kiểm thử thực tế trên CI và terminal

| Trường hợp test | Cách kiểm tra | Điều cần xác nhận |
| --- | --- | --- |
| Unit test bình thường | `java ConsoleDemoTest` | Có tên, mảng secret được xóa, output đúng |
| EOF khi đọc tên | `FakeConsole` trả `null` từ `ask` | Không hỏi secret, thông báo kết thúc |
| Tên rỗng | `FakeConsole` trả chuỗi khoảng trắng | Không hỏi secret, báo lỗi |
| EOF khi đọc secret | `FakeConsole` trả `null` từ `askSecret` | Không dereference null, thông báo kết thúc |
| Console sẵn có? | `java ConsoleDemo --check` trong từng môi trường | Ghi nhận true/false; không cố định giá trị mọi máy |
| Prompt/echo trên terminal thật | Chạy `java ConsoleDemo` không chuyển hướng | Tên echo đúng, mật khẩu **không** echo, chương trình kết thúc |
| Chạy từ IDE không có terminal | Thực thi ứng dụng trong IDE | Nếu `null`, thông báo rõ chứ không NPE |
| Piped input | `PipeText` với stdin UTF-8 | Đọc text công khai và xử lý EOF được |
| Lỗi format prompt | Test riêng format string không hợp lệ | Có xử lý/nhận diện `IllegalFormatException` |
| Tương tác đa luồng | Test tích hợp theo terminal/framework đích | Prompt không xen kẽ gây nhầm đầu vào |

Trên CI, **không nên bắt unit test phải có terminal thật**. Chỉ chạy các bài test console tích hợp trong môi trường được cấp phát TTY phù hợp. Kết quả của `--check` giúp phân loại môi trường, nhưng nó không đo thay mức an toàn của transport hoặc secret management.

## 13. Các lỗi phổ biến cần tránh

| Lỗi | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| `System.console().readLine(...)` mà không kiểm tra null | IDE/CI/pipeline có thể không có Console | Lấy `Console` một lần rồi kiểm tra `null` |
| Dùng `Scanner(System.in)` thay `readPassword` không phân biệt | Input có thể bị echo hoặc đi qua log/pipeline | Với bí mật cần non-echo, yêu cầu Console hoặc cơ chế secret riêng |
| Coi `readLine() == null` như chuỗi rỗng | EOF không đồng nghĩa người dùng nhấn Enter | Xử lý EOF riêng |
| Chuyển `char[]` mật khẩu thành `String` | Có bản sao bất biến khó xóa | Hạn chế copy, xóa mảng sau dùng |
| Không xóa secret trong nhánh exception | Bí mật còn trong mảng lâu hơn cần thiết | `try/finally` + `Arrays.fill` |
| Dùng `readLine(userInputPrompt)` với dấu `%` ngẫu nhiên | Có thể bị hiểu là format string | `readLine("%s", userInputPrompt)` |
| Nhầm `Console` với `System.in` | Console không được bảo đảm khi stdin từ file | Dùng standard streams cho pipeline |
| Dùng `isTerminal()` trong code Java 17 | API chỉ có từ Java 22 | Kiểm tra `System.console() != null` |
| Cho CI tự chạy flow nhập mật khẩu thật | Có thể block hoặc rò rỉ secrets | Fake adapter trong unit test; manual TTY test riêng |
| Đóng hoặc thay global input để test | Ảnh hưởng các phần khác của JVM | Inject abstraction thay vì sửa streams toàn cục |
| Giả định một kết quả `--check` cố định trên mọi máy | TTY phụ thuộc cách JVM khởi động | Test giá trị cục bộ, không hardcode toàn cục |
| Dùng `console.charset()` như UTF-8 của mọi file | Console output charset khác encoding của file/pipe | Chọn charset rõ ràng cho file/pipeline |

## 14. Bài tập tự luyện và lời giải định hướng

**Câu 1.** Chạy cùng một chương trình trên terminal thật và trong IDE nhưng `System.console()` lúc thì khác `null`, lúc thì `null`. Có phải Java chạy sai không?

**Đáp án:** Không. `System.console()` phản ánh việc JVM có được gắn console tương tác thích hợp hay không. IDE output panel hoặc một pipeline không phải lúc nào cũng là thiết bị console thật. Phải kiểm tra null và thiết kế đường chạy thay thế có chủ đích.

**Câu 2.** Vì sao `readPassword` trả `char[]` thay vì `String`?

**Đáp án:** `char[]` cho phép ứng dụng ghi đè các phần tử sau khi xử lý. `String` là bất biến, không thể xóa nội dung theo cùng cách đáng tin. Nhưng xóa mảng chỉ giảm thời gian tồn tại của dữ liệu trong mảng ấy, không chứng minh toàn bộ bản sao đã biến mất.

**Câu 3.** Người dùng nhấn Enter ở prompt tên, `readLine` trả `null` hay `""`?

**Đáp án:** Thường là chuỗi rỗng `""` (không có ký tự trước dấu xuống dòng). `null` dùng cho end-of-input, chẳng hạn người dùng gửi EOF.

**Câu 4.** Tại sao phải test `ConsoleDemo.conversation(...)` qua fake thay vì bắt CI nhập mật khẩu?

**Đáp án:** Fake cung cấp input xác định và đo được output/đường điều khiển, bao gồm nhánh EOF, tên rỗng và dọn `char[]`. Nó không cần TTY, không cần secret thật và không khiến build block chờ bàn phím.

**Câu 5.** Một chương trình nhận `stdin` từ file có thể dùng `System.console()` để đọc dòng trong file không?

**Đáp án:** Không nên thiết kế như vậy. `Console` dành cho terminal tương tác và có thể `null` khi redirect. `System.in`/`BufferedReader` là đường phù hợp cho file và pipe, với encoding rõ ràng.

**Câu 6.** `Console.charset()` có phải lúc nào cũng là `StandardCharsets.UTF_8` không?

**Đáp án:** Không. Nó phản ánh charset mà Console dùng cho output theo môi trường; không bảo đảm luôn là UTF-8 hay trùng `Charset.defaultCharset()`.

**Câu 7.** `Console.isTerminal()` có dùng được khi compile bằng `javac --release 17` không?

**Đáp án:** Không. Phương thức được bổ sung từ Java 22; trên source target Java 17 hãy dùng `System.console() != null` để xử lý sự hiện diện của Console.

**Bài tập thực hành:**

1. Mở rộng `conversation`: nếu tên rỗng, hỏi tối đa ba lần, nhưng luôn cho phép hủy khi EOF.
2. Bổ sung nhánh mật khẩu rỗng: báo lỗi mà không echo nội dung; bảo đảm `Arrays.fill` vẫn được gọi trong mọi nhánh sau khi đã nhận `char[]`.
3. Viết thêm `FakeConsole` chứa danh sách nhiều tên để kiểm thử vòng lặp, không cần terminal.
4. Thêm chế độ `--name-from-stdin` chỉ dành cho **tên công khai**, sử dụng UTF-8 và thông báo rõ nếu EOF; không dùng fallback này cho mật khẩu.
5. Chạy `java ConsoleDemo --check` trong terminal thật, IDE và một tác vụ không tương tác; so sánh môi trường, **không suy ra quy luật từ một lần chạy đơn lẻ**.

## 15. Tài liệu chính thức còn áp dụng

- [Java SE 26 — System.console()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#console()): contract trả `Console` hoặc `null`.
- [Java SE 26 — java.io.Console](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): sự tồn tại của console, `readLine`, `readPassword`, `reader`, `writer`, `flush`, `charset` và `isTerminal`.
- [Java SE 17 — java.io.Console](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): các phương thức tương thích với bài lab Java 17.
- [Java SE 26 — java.lang.System](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): `System.in/out/err` và điều kiện `System.console`.
- [Java SE 26 — InputStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): giải mã byte của `System.in` sang ký tự.
- [Java SE 26 — BufferedReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): đọc dòng text từ `Reader`.
- [Microsoft Learn — Windows PowerShell 5.1 character encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1): lưu ý BOM/encoding khi chuyển dữ liệu vào native process qua pipeline trên PowerShell cũ.

**Ghi nhớ:** `System.console()` là lối vào **thiết bị nhập xuất tương tác nếu có**, không phải một bảo đảm rằng mọi chương trình Java đều có terminal. Kiểm tra `null`, dùng `readLine` cho text và `readPassword` cho dữ liệu bí mật, xử lý EOF/format/I/O rõ ràng, xóa `char[]` ngay sau dùng và tách logic CLI ra khỏi Console để test tự động an toàn.
