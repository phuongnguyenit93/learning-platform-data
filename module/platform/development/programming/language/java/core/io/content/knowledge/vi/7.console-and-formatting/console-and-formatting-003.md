# `System.console()` và trường hợp không có console

## Mục tiêu bài học

Một chương trình Java có thể chạy trong cửa sổ terminal, nhưng cũng có thể chạy từ IDE, qua pipe, bằng scheduler, như service, trong CI/CD hoặc container. Cách khởi chạy quyết định liệu Java có nhận được **console tương tác** hay không. Vì vậy, **`System.console()` có thể trả về `null`**, dù `System.in` và `System.out` vẫn tồn tại và hoạt động.

Sau bài này, bạn có thể:

- Phân biệt **`java.io.Console`** với ba luồng chuẩn **`System.in`**, **`System.out`**, **`System.err`**.
- Giải thích vì sao `System.console()` trả về một `Console` hoặc `null` và tránh suy luận sai chỉ từ việc chương trình có in được nội dung.
- Sử dụng `Console.readLine()`, `readPassword()`, `printf()`, `format()`, `writer()`, `reader()` và `flush()` đúng mục đích.
- Xây dựng chương trình có **fallback rõ ràng** khi chạy không có console, xử lý EOF và I/O error, đồng thời không làm lộ mật khẩu do tự động chuyển sang input có echo.
- Viết mã Java 17+ chạy được và hiểu đầu ra nào thay đổi theo môi trường.

## 1. Console khác gì `System.in`, `System.out`, `System.err`?

`java.io.Console` là API hướng tới **thiết bị console tương tác** gắn với JVM, cung cấp khả năng đọc một dòng, đọc mật khẩu với echo bị vô hiệu hóa khi có thể, ghi định dạng và tương tác text. Lấy đối tượng bằng:

```java
Console console = System.console();
```

Đây là **đoạn mã minh họa**; cần `import java.io.Console;`. Biến `console` có thể là `null`.

Ngược lại, ba luồng chuẩn là những đối tượng có sẵn:

| API | Kiểu | Chức năng |
|---|---|---|
| `System.in` | `InputStream` | Nguồn byte đầu vào chuẩn; có thể là keyboard, pipe, file hoặc EOF |
| `System.out` | `PrintStream` | Đích đầu ra chuẩn; có thể là terminal, file, pipe hoặc logger bên ngoài |
| `System.err` | `PrintStream` | Đích thông báo lỗi chuẩn; có thể chuyển hướng riêng |
| `System.console()` | `Console` hoặc `null` | Giao diện console tương tác nếu JVM/môi trường cung cấp |

**Không có quy tắc “có `System.in` thì phải có `Console`”**. Java vẫn có thể đọc từ pipe hoặc file bằng `System.in` và in qua `System.out` khi `System.console() == null`.

Ví dụ sơ đồ:

```text
                          Một tiến trình JVM
               ┌────────────────────────────────┐
terminal/pipe → │ System.in       (luồng byte)   │
terminal/file ← │ System.out      (luồng byte)   │
terminal/file ← │ System.err      (luồng byte)   │
               │                                │
console thực ↔ │ System.console() (có thể null) │
               └────────────────────────────────┘
```

`System.console()` phụ thuộc **cách JVM được khởi chạy và môi trường nền tảng**. Một JVM chạy từ dòng lệnh tương tác, không chuyển hướng các stream chuẩn, **thường** có console; đây không phải cam kết cho mọi shell, terminal giả lập, container hoặc triển khai Java.

## 2. Khi nào `System.console()` trả `null`?

Các tình huống thường gặp:

1. **IDE:** chương trình chạy qua cửa sổ *Run* hoặc *Debug* của IntelliJ IDEA, Eclipse hay công cụ khác. Giao diện “console” của IDE thường chỉ là panel mô phỏng I/O, không phải thiết bị console JVM nhận diện.
2. **Chuyển hướng / pipe:** chẳng hạn `java App < input.txt`, `java App > output.txt`, hoặc `echo data | java App`. Việc chuyển hướng có thể khiến console không khả dụng, nhưng `System.in`/`System.out` vẫn hoạt động theo chuyển hướng.
3. **CI/CD, cron, scheduled task, service/daemon:** tiến trình thường không được gắn terminal tương tác.
4. **Container không gắn TTY:** tiến trình có thể có stdin/stdout để gắn log nhưng không có terminal. Việc cấp pseudo-TTY (ví dụ `docker run -it`) có thể thay đổi điều kiện, song vẫn phụ thuộc runtime/launcher.
5. **Kiểm thử tự động:** bộ test có thể thay thế `System.in`/`System.out` bằng stream trong bộ nhớ; điều đó không tạo ra `Console` cho JVM.

Không khẳng định tuyệt đối rằng **mọi lần** chạy trong IDE hoặc redirect **đều** trả `null`: hành vi là đặc điểm môi trường; **kiểm tra tại runtime** là cách đáng tin cậy:

```java
Console console = System.console();
if (console == null) {
    // Chọn chế độ phi tương tác hoặc xử lý nguồn stdin được cấu hình.
} else {
    // Có thể dùng readLine/readPassword/printf của Console.
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Không gọi `console.readLine()` ngay khi chưa kiểm tra `null`: sẽ gây `NullPointerException` ở môi trường không có console.

### Điều `null` không nói lên

- Không có nghĩa ứng dụng **không thể nhận input**; `System.in` có thể là một file, pipe hoặc stream test.
- Không có nghĩa ứng dụng **không thể in ra output**; `System.out` và `System.err` vẫn có thể gửi đến logging agent/file.
- Không có nghĩa **mạng hoặc database** không hoạt động; `Console` chỉ là một phương tiện tương tác text.
- Không có nghĩa **không có người dùng**: IDE có thể vẫn cho nhập chữ vào `System.in` mà không cấp `Console`.
- Ngược lại, `Console` khác `null` cũng không có nghĩa luôn có người sẵn sàng nhập, hoặc một lời gọi đọc không thể kết thúc bằng EOF/lỗi.

## 3. API chính của `java.io.Console`

| Phương thức | Ý nghĩa |
|---|---|
| `System.console()` | Lấy console gắn với JVM hoặc `null` |
| `console.readLine()` | Đọc một dòng, không bao gồm line terminator; có thể trả `null` khi EOF |
| `console.readLine("Name: ")` | In prompt dạng format rồi đọc dòng |
| `console.readPassword()` | Đọc mật khẩu với echo bị vô hiệu hóa khi có thể, trả `char[]`, có thể `null` khi EOF |
| `console.readPassword("Password: ")` | In prompt rồi đọc `char[]` |
| `console.printf(format, args...)` | Xuất văn bản có định dạng; trả về `Console` |
| `console.format(format, args...)` | Tương tự `printf` |
| `console.writer()` | Trả `PrintWriter` liên kết console để ghi text |
| `console.reader()` | Trả `Reader` liên kết console để đọc text |
| `console.flush()` | Flush writer của console |

Cả `readLine` và `readPassword` có phiên bản không prompt hoặc prompt dùng format string. `readLine("Name: ")` là cú pháp dùng phiên bản có tham số format, và định dạng sẽ được xử lý tương tự một lời gọi format của console; nếu prompt chứa `%` muốn in nguyên văn qua định dạng, cần escape thành `%%` hoặc chuyển định dạng phù hợp.

**Giới hạn lỗi:** `Console` có thể phát sinh `java.io.IOError` nếu có lỗi I/O bên dưới, ngoài các tình huống kết thúc input bình thường (`null` ở `readLine`/`readPassword`). Không nên gộp EOF với chuỗi rỗng:

- `readLine() == null`: hết input.
- `readLine().isEmpty()`: người dùng đã nhập dòng trống.
- `readPassword() == null`: hết input.
- `readPassword().length == 0`: người dùng nhập mật khẩu trống.

### Dùng formatter đúng chỗ

```java
console.printf("Items: %d, total: %.2f%n", 3, 19.75);
```

Đây là **đoạn minh họa**, giả sử `console` hợp lệ; `%n` tạo newline theo hệ thống, `%d` cho số nguyên, `%.2f` cho số thực. Formatter dùng quy tắc locale trong quá trình format, nên dạng dấu thập phân có thể khác nhau theo locale nếu không được chỉ định rõ. Đừng viết test yêu cầu nguyên văn dấu `.` cho mọi locale khi không kiểm soát locale.

## 4. Ví dụ Java 17: nhận biết console và fallback nhập tên

Chương trình sau hỗ trợ cả chế độ **interactive** khi có console lẫn chế độ **stdin** khi không có console. Nó không coi việc thiếu console là lỗi đối với thông tin thông thường như tên người dùng.

Lưu **`ConsoleAwareDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ConsoleAwareDemo {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        String name;

        if (console != null) {
            console.printf("Mode: console%n");
            name = console.readLine("Name: ");
        } else {
            System.out.println("Mode: standard input");
            System.out.print("Name: ");
            System.out.flush();

            // Không đóng reader ở đây: nó bao System.in thuộc tiến trình.
            BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8)
            );
            name = reader.readLine();
        }

        if (name == null) {
            System.out.println();
            System.out.println("No input (EOF).");
            return;
        }

        name = name.strip();
        if (name.isEmpty()) {
            System.out.println("Name cannot be blank.");
            return;
        }

        System.out.println("Hello, " + name + "!");
    }
}
```

Biên dịch:

```bash
javac ConsoleAwareDemo.java
```

Chạy từ terminal tương tác:

```bash
java ConsoleAwareDemo
```

Nếu có console, một phiên tương tác điển hình (các dòng người dùng gõ có thể được terminal echo):

```text
Mode: console
Name: An
Hello, An!
```

Nếu chạy trong môi trường `System.console() == null`, ví dụ nhận `An` qua stdin, stdout sau khi nhập dòng sẽ là:

```text
Mode: standard input
Name: Hello, An!
```

Ở trường hợp nhập qua pipe, terminal không nhất thiết hiển thị lại `An` như khi người dùng gõ; `Name: ` được in không kèm newline, nên `Hello, An!` xuất hiện trên cùng dòng. Điều kiện hiển thị tùy cách chạy, nhưng **cả hai nhánh đều xử lý một chuỗi tên và EOF**. Trong shell Unix có thể thử `printf 'An\n' | java ConsoleAwareDemo`; trên PowerShell có thể thử `'An' | java ConsoleAwareDemo`. Nếu môi trường thực tế vẫn cấp `Console`, chương trình sẽ chọn nhánh console; ví dụ stdout nhánh fallback chỉ áp dụng khi console là `null`.

Để kiểm tra chính xác và độc lập môi trường phần “đọc dòng”, hãy tách việc đọc từ một `Reader` thành hàm nhận dependency; khi test truyền `StringReader` thay vì cố ép `System.console()` thành một giá trị.

### Tại sao code không đóng `System.in`?

Đóng `BufferedReader` sẽ đóng luôn `InputStreamReader` và thường cả underlying `System.in`. Trong một lệnh CLI nhỏ mà chương trình sắp kết thúc, chuyện này có thể không đáng kể; nhưng trong ứng dụng/library cần tiếp tục đọc stdin, việc đóng global stream có thể phá các tác vụ khác. Vì thế **xác định ai sở hữu resource** trước khi dùng try-with-resources trên wrapper của `System.in`.

Khi đọc một file do ứng dụng tự mở bằng `Files.newBufferedReader(path, charset)`, ngược lại, caller thường sở hữu reader và **nên đóng** bằng try-with-resources.

### Chọn charset cho fallback

`System.in` là byte stream; `InputStreamReader(System.in, StandardCharsets.UTF_8)` giả định nguồn input thực sự được encode UTF-8. Nếu terminal, pipe hoặc file dùng charset khác, có thể xuất hiện ký tự lỗi. Hợp đồng CLI cần ghi rõ input encoding hoặc tuân theo charset terminal/phần mềm đích. Việc chọn UTF-8 ở ví dụ chỉ phù hợp khi nguồn được quy định là UTF-8; nó không tự chuyển byte sai charset thành đúng tiếng Việt.

## 5. Vì sao `readPassword()` đặc biệt?

`Console.readPassword()` cố gắng đọc mật khẩu khi **vô hiệu hóa echo** từ console (để ký tự người dùng gõ không hiển thị). Mật khẩu được trả về dưới dạng **`char[]`** thay vì `String` nhằm cho phép code xóa nội dung mảng khi dùng xong.

- `String` bất biến; ứng dụng không có cách đáng tin để chủ động ghi đè các ký tự bên trong một instance `String`.
- `char[]` có thể được ghi đè bằng `Arrays.fill(secret, '\0')`.
- Điều này **giảm thời gian mảng do ứng dụng nắm giữ còn chứa mật khẩu**, nhưng không phải bảo đảm mọi bản sao của mật khẩu biến mất khỏi JVM hoặc thư viện, hệ điều hành và phần cứng.
- Không log `char[]`, không in mật khẩu lên console, không lưu nó lâu hơn mức cần thiết.
- Không convert sang `String` chỉ để thao tác tiện hơn nếu thư viện nhận được `char[]` hoặc API xác thực an toàn hơn.

### Ví dụ Java 17: đọc mật khẩu khi có console, từ chối fallback echo

Lưu **`PasswordConsoleDemo.java`**:

```java
import java.io.Console;
import java.util.Arrays;

public class PasswordConsoleDemo {
    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            System.err.println(
                "Secure interactive console is unavailable."
            );
            return;
        }

        char[] password = console.readPassword("Password: ");
        if (password == null) {
            console.printf("Input ended.%n");
            return;
        }

        try {
            if (password.length == 0) {
                console.printf("Empty password was entered.%n");
            } else {
                // Demo: nơi này sẽ truyền char[] cho hàm xác thực tin cậy.
                console.printf("Password input received.%n");
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PasswordConsoleDemo.java
java PasswordConsoleDemo
```

Nếu có console, chương trình in prompt, nhận mật khẩu không echo rồi in `Password input received.` hoặc thông báo chuỗi trống. Nếu không có console, chương trình chỉ in ra stderr:

```text
Secure interactive console is unavailable.
```

Phương án này **cố ý không tự chuyển sang `Scanner(System.in)` để đọc mật khẩu**. Đối với thông tin bí mật, fallback có echo có thể khiến mật khẩu lộ trong terminal, log, transcript hoặc qua công cụ theo dõi input. Đừng tự động bật fallback chỉ vì `System.console() == null`.

Trong ứng dụng thực tế, phần xác thực sẽ gọi API thích hợp, xử lý lỗi và xoá mảng trong `finally` kể cả khi xác thực thất bại. Không đem chương trình minh họa này làm hệ thống kiểm tra mật khẩu hoàn chỉnh: nó chỉ trình diễn vòng đời input và không xác thực độ mạnh/đúng sai của mật khẩu.

### Nếu automation phải cung cấp secret?

Đây là **thiết kế khác** với nhập mật khẩu tương tác. Tùy hệ thống có thể chọn secret manager, cơ chế cấp credential của môi trường chạy, file descriptor bảo vệ, hoặc API chuyên dụng. Không tự đọc qua stdin như mật khẩu ở chế độ echo rồi giả định rằng nó an toàn; cũng tránh truyền secret trên command-line argument vì có thể bị ghi vào process listing, logs hoặc lịch sử lệnh. Biến môi trường cũng có rủi ro bị lộ trong cấu hình, log và công cụ quản trị, nên cần tuân theo cơ chế secret của nền tảng.

Một CLI hợp lý có thể hỗ trợ các mode được khai báo rõ ràng:

```text
--interactive        yêu cầu Console; không có -> báo lỗi
--input-file <path>  nhận dữ liệu thường từ file, charset định rõ
--batch              không prompt; lấy cấu hình đã được cấp
```

Đây là **minh họa giao diện**, không phải các option chuẩn tự có trong JVM. Đối với secret, nguồn cấp phải được định nghĩa riêng và đánh giá an toàn theo môi trường triển khai.

## 6. EOF, dòng trống và lỗi I/O

Một lỗi phổ biến là code giả định mọi lần đọc trả `String`. Nhưng dù dùng `Console.readLine()` hay `BufferedReader.readLine()`, caller cần xử lý **EOF**.

```text
readLine() == null    → Không còn dữ liệu để đọc (EOF)
readLine().isEmpty()  → Có dòng được đọc, nhưng nội dung rỗng
readLine() == "  "    → Có dòng chỉ chứa khoảng trắng
```

Nếu muốn cấm input trắng, sau khi đã kiểm tra `null` mới gọi `isBlank()` hoặc `strip()`. Không viết:

```java
String name = console.readLine().strip();
```

Đoạn **phản ví dụ** này có hai lỗi: `console` có thể `null`, và `readLine()` có thể `null`. Thứ tự đúng là kiểm tra cả hai trước khi xử lý chuỗi.

Ví dụ vòng lặp trong trường hợp đã xác minh có console:

```java
String line;
while ((line = console.readLine("> ")) != null) {
    if (line.equalsIgnoreCase("quit")) {
        break;
    }
    console.printf("You typed: %s%n", line);
}
```

Đây là **đoạn minh họa**, `console` là đối tượng `Console` khác `null`. Khi EOF, vòng lặp dừng; khi người dùng nhập `quit`, vòng lặp cũng dừng. Nếu prompt yêu cầu nhập số, hãy đọc text rồi parse với `Integer.parseInt` và xử lý `NumberFormatException`, thay vì bỏ qua input lỗi.

`Console` có thể ném `IOError` khi lỗi I/O. `BufferedReader.readLine()` thường báo lỗi qua checked `IOException`. Phải phân biệt ngoại lệ thật với EOF, có chính sách exit code và thông báo phù hợp trong ứng dụng CLI.

### Ctrl+D, Ctrl+Z và Ctrl+C có phải luôn giống nhau?

Không. Tùy terminal/OS:

- Ctrl+D trên nhiều terminal kiểu Unix khi dòng đang trống có thể khiến `readLine()` thấy EOF.
- Ctrl+Z rồi Enter thường được dùng để báo EOF trong console Windows.
- Ctrl+C thường tạo interrupt/signal hoặc yêu cầu dừng chương trình, **không đồng nghĩa** với việc `readLine()` chắc chắn trả `null`.

Không xây dựng logic nghiệp vụ phụ thuộc mù quáng vào một phím cụ thể trên mọi hệ điều hành; hãy xử lý giá trị API trả về và chính sách dừng của tiến trình.

## 7. Các lựa chọn khi không có console

| Nhu cầu | Hướng xử lý phù hợp | Vì sao |
|---|---|---|
| CLI tương tác cần hỏi câu đơn giản | Nếu có `Console`, dùng `readLine`; nếu không, có thể `BufferedReader(System.in)` tùy hợp đồng | Chạy được trong IDE hoặc pipe |
| CLI nhận dữ liệu từ pipeline/file | Dùng `System.in`, reader charset rõ ràng, parse theo định dạng xác định | Không cần console tương tác |
| CLI cần nhập mật khẩu không echo | Yêu cầu `Console.readPassword` và báo lỗi khi không có console, hoặc thiết kế nguồn secret chuyên dụng | Tránh lộ bí mật do fallback |
| Tool chạy trong CI hoặc cron | Cấu hình bằng tham số/file/nguồn config được duyệt; không đợi prompt | Non-interactive, tránh chạy treo |
| Server/web application | Request, config, secrets service, logging thay cho prompt | Server không phụ thuộc terminal |
| Công cụ có nhiều loại input | Tách `Reader`/`InputStream` và logic xử lý để unit test | Giảm ràng buộc với môi trường |
| Thông báo lỗi cho người vận hành | Dùng `System.err` hoặc framework logging | stderr có thể được capture riêng |
| Output được pipe sang chương trình khác | In đúng cấu trúc, giữ prompt/status ở stderr khi thiết kế giao thức CLI | Tránh làm bẩn dữ liệu stdout |

Một chương trình dùng stdin theo giao thức batch **không nhất thiết phải coi thiếu console là lỗi**. Điều nguy hiểm là **tự động đổi sang đường nhập kém an toàn cho mật khẩu** hoặc để chương trình chờ vô hạn một prompt không bao giờ có người trả lời.

### Lưu ý `Scanner` và `BufferedReader`

`Scanner` tiện cho đọc dữ liệu dạng token và parse kiểu nguyên thủy, nhưng `next()` và `nextLine()` có ngữ nghĩa khác nhau; việc trộn hai phương thức thường để sót newline trong input. Trong CLI xử lý dòng, `BufferedReader.readLine()` thường rõ ràng hơn.

`Scanner.close()` trên `System.in` đóng luôn nguồn toàn cục. Vì vậy, nếu scanner chỉ là wrapper của input được quản lý ở nơi khác, cần định nghĩa ownership cẩn thận. Nếu scan file tự mở, dùng try-with-resources.

Không thay thế `Console.readPassword()` bằng `Scanner.nextLine()` rồi giả định tính năng ẩn ký tự vẫn được giữ. `Scanner` không cung cấp bảo đảm disabling terminal echo giống Console password API.

## 8. Kiểm thử khi hành vi phụ thuộc môi trường

Kiểm thử `System.console()` trực tiếp trong JUnit thường khó ổn định vì framework và runner có thể không gắn terminal. Thay vì ép mọi test chạy với TTY, hãy **tách nguồn đọc khỏi logic ứng dụng**.

### Ví dụ Java 17: kiểm thử fallback bằng stream trong bộ nhớ

Lưu **`LineInputDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class LineInputDemo {
    static String greeting(BufferedReader reader) throws IOException {
        String line = reader.readLine();

        if (line == null) {
            return "No input (EOF).";
        }
        if (line.isBlank()) {
            return "Blank name.";
        }
        return "Hello, " + line.strip() + "!";
    }

    public static void main(String[] args) throws IOException {
        try (BufferedReader normal =
                 new BufferedReader(new StringReader("An\n"));
             BufferedReader blank =
                 new BufferedReader(new StringReader(" \n"));
             BufferedReader eof =
                 new BufferedReader(new StringReader(""))) {
            System.out.println(greeting(normal));
            System.out.println(greeting(blank));
            System.out.println(greeting(eof));
        }
    }
}
```

Chạy:

```bash
javac LineInputDemo.java
java LineInputDemo
```

Stdout **không phụ thuộc terminal**:

```text
Hello, An!
Blank name.
No input (EOF).
```

`StringReader` mô phỏng input để kiểm tra xử lý dòng trống và EOF; đây không phải thử nghiệm xem runtime có `Console` hay không. Ở ứng dụng thật, đưa abstraction input/output vào logic nghiệp vụ là cách tách biệt transport với validation. Khi test chế độ console, có thể integration-test trong môi trường PTY phù hợp, song không bắt buộc mọi unit test phải được gắn TTY.

## 9. Những tình huống gây hiểu nhầm

### “IDE có tab Console, tại sao `System.console() == null`?”

Tên tab UI của IDE không quyết định đối tượng `Console` JVM. IDE có thể gửi văn bản tới stdout và nhận stdin thông qua stream riêng nhưng không cấp console hệ thống theo cách JVM nhận diện. Dùng fallback stdin cho dữ liệu thường hoặc chạy từ terminal phù hợp nếu cần `readPassword`.

### “Có terminal trên màn hình thì chắc chắn có Console?”

Không. Chuyển hướng, pseudo-terminal, cách tiến trình con được khởi chạy và cấu hình runtime đều ảnh hưởng. Kiểm tra `System.console()` tại runtime; không suy từ việc có cửa sổ terminal.

### “`System.console() == null` có nghĩa `System.in == null`?”

Không. `System.in` thường vẫn là `InputStream`; nó có thể lập tức đến EOF, có dữ liệu được pipe hoặc đã bị thay bằng test fixture. Sự tồn tại của stream không bảo đảm có dữ liệu.

### “Nếu `readPassword()` trả `char[]`, mật khẩu đã hoàn toàn an toàn?”

Không. `char[]` cho phép xóa **mảng hiện có**, nhưng input có thể đã qua các buffer bên dưới hoặc bị copy bởi thư viện. Bảo vệ secret cần xem xét toàn bộ vòng đời, log, crash dump, cách truyền và xác thực. Dùng `Arrays.fill` trong `finally`, đồng thời tránh tạo `String` không cần thiết.

### “In prompt bằng `System.out.print` rồi đọc dòng có tự hiện ngay không?”

Không nên phụ thuộc hoàn toàn vào buffering của các wrapper và sink. Nếu muốn prompt không kết thúc newline được đẩy ra ngay, gọi `System.out.flush()` hoặc writer phù hợp. Khi stdout bị chuyển hướng sang file/pipe, prompt có thể xuất hiện ở nơi không có người đọc; CLI nên có chế độ `--batch` hoặc không prompt khi nguồn input không tương tác.

### “Gọi `console.reader()` và `new Scanner(System.in)` xen kẽ có ổn không?”

Không nên nếu chúng cùng liên quan một nguồn terminal. Hai wrapper có thể buffer trước dữ liệu khiến thứ tự đọc khó dự đoán, hoặc xử lý charset/newline khác nhau. Chọn một phương pháp làm chủ input trong một luồng xử lý. `Console` còn có cơ chế đồng bộ dành cho read/write console; đừng tự giả định trộn mọi đối tượng reader đều an toàn.

### “Không có console nên lấy password từ dòng tham số là được?”

Tham số dòng lệnh có thể hiện trong process listing, diagnostic, crash report và lịch sử shell. Không dùng giải pháp này như fallback tự động. Chọn nguồn secret được nền tảng hỗ trợ và giới hạn quyền truy cập.

### “`Console.readLine()` luôn trả text theo UTF-8?”

Đừng giả định. Encoding/decoding của console liên quan cấu hình terminal và JVM; `System.in` đọc byte cũng cần reader với charset đúng. Với file/pipe có định dạng rõ ràng, dùng charset tường minh để tránh sai tiếng Việt.

## 10. Quy trình triển khai CLI ổn định

1. **Quy định chế độ chạy.** Chương trình tương tác hay batch? Có cần bí mật? Dữ liệu qua stdin là dòng UTF-8, JSON hay định dạng khác?
2. **Kiểm tra console một lần tại điểm chọn chế độ.** `Console console = System.console();` rồi chọn nhánh phù hợp; không gọi API của `console` nếu `null`.
3. **Dữ liệu thường:** nếu cho phép pipe hoặc IDE, dùng `BufferedReader` trên `System.in` với charset phù hợp. Nếu không có dữ liệu, xử lý EOF để thoát rõ ràng.
4. **Mật khẩu:** dùng `readPassword` khi có console hoặc nguồn secret non-interactive được thiết kế trước. Không tự downgrade sang nhập hiện ký tự.
5. **Tách input, validation và output.** Logic xử lý nhận kiểu `String` hoặc object đã parse; để lớp UI/CLI tương tác với Console/Reader. Dễ kiểm thử độc lập.
6. **Không chờ vô hạn trong môi trường batch.** Nếu thiếu tham số bắt buộc và không cho phép prompt, báo thiếu cấu hình, chọn exit code phù hợp.
7. **Xử lý lỗi và resource ownership.** Phân biệt EOF với lỗi I/O. File reader tự mở cần đóng, wrapper trên `System.in` có thể không nên đóng nếu tiến trình còn dùng.
8. **Tách stdout/stderr có chủ đích.** Nếu stdout được dùng như data protocol cho shell pipe, prompt/error/status nên được định tuyến rõ ràng để không phá dữ liệu.
9. **Kiểm chứng môi trường thực tế.** Chạy qua IDE, terminal tương tác, chuyển hướng stdin/stdout và CI/container nếu sản phẩm phải hỗ trợ các chế độ đó. Đừng biến kết quả một hệ điều hành thành cam kết xuyên nền tảng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Trong IDE, chương trình in được `Hello` qua `System.out`. Điều đó có chứng minh `System.console() != null` không?

**Đáp án:** Không. stdout có thể được IDE capture độc lập với console. Phải kiểm tra `System.console()`.

**Câu 2.** Khi `System.console() == null`, có còn cách đọc dữ liệu thường do shell pipe vào không?

**Đáp án:** Có, có thể đọc `System.in` bằng `BufferedReader(new InputStreamReader(System.in, charset))`, xử lý EOF và charset theo hợp đồng.

**Câu 3.** Vì sao không viết `System.console().readLine()` trực tiếp?

**Đáp án:** `System.console()` có thể `null`, gây `NullPointerException`; bản thân `readLine()` cũng có thể trả `null` khi EOF.

**Câu 4.** `Console.readPassword()` khác `Scanner.nextLine()` ở điểm quan trọng nào?

**Đáp án:** `readPassword()` có cơ chế nhập không echo khi có thể và trả về `char[]` để chủ động xóa; `Scanner.nextLine()` không cung cấp bảo đảm đó.

**Câu 5.** Nếu nhập dòng trắng và EOF đều dẫn đến không có tên người dùng, có nên coi chúng là cùng một trạng thái?

**Đáp án:** Không. Dòng trống là **một dòng được nhập**; EOF là **kết thúc nguồn input**. Quy trình prompt/thoát/validation thường xử lý hai trạng thái khác nhau.

**Câu 6.** Muốn kiểm thử validation của CLI mà CI không có terminal, có phải tìm cách tạo `Console` trong mọi unit test không?

**Đáp án:** Không. Tách logic đọc/validation bằng `Reader` hay interface, dùng `StringReader` cho unit test và kiểm thử tích hợp với console thật khi cần.

**Ghi nhớ:** `System.console()` **có thể trả `null`** và đây là tình huống vận hành bình thường. `System.in/out/err` là các luồng chuẩn vẫn có thể hoạt động. Với text thông thường, thiết kế fallback rõ ràng qua stdin; với mật khẩu, giữ yêu cầu nhập không echo hoặc một nguồn secret an toàn đã xác định; luôn xử lý EOF, lỗi và khác biệt giữa môi trường tương tác với batch.
