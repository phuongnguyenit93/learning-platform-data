# Console.readLine: nhập chuỗi có lời nhắc trong Java

## 1. Bài toán và ý tưởng

Ứng dụng dòng lệnh thường cần đặt một câu hỏi trước khi đọc câu trả lời:

~~~text
Tên của bạn: An
Bạn An ở thành phố nào? Hue
Xin chào An từ Hue!
~~~

Để thực hiện với terminal tương tác, Java cung cấp `java.io.Console`. Hai khả năng cần nắm:

- `console.readLine()`: đọc **một dòng** từ console mà **không tự in lời nhắc**.
- `console.readLine(String format, Object... args)`: **hiển thị một lời nhắc được định dạng**, rồi đọc một dòng trong cùng thao tác ở cấp `Console`.

Console được lấy qua `System.console()`, không tạo bằng `new Console()`. Khi JVM không có console thích hợp, `System.console()` có thể trả `null`. Vì thế phải kiểm tra tồn tại console trước khi gọi `readLine` và cần một chính sách rõ ràng cho IDE, file input hoặc pipeline.

**Ví dụ nhanh (mã đặt trong `main` hoặc method, không phải file độc lập):**

~~~java
Console console = System.console();
if (console == null) {
    System.err.println("Không có console tương tác.");
    return;
}

String name = console.readLine("Tên của bạn: ");
if (name == null) {
    System.out.println("Đã hết dữ liệu đầu vào.");
} else {
    System.out.println("Xin chào " + name + "!");
}
~~~

Cần `import java.io.Console;` và nằm trong method có thể `return`. Khi người dùng gõ `An` rồi nhấn Enter, chuỗi kết quả là `"An"`, **không chứa** ký tự kết thúc dòng.

Bài tập trung vào Java 17+ với hành vi/API còn áp dụng hiện nay. Khi chạy trên toolchain có console provider khác nhau, khả năng có console hoặc echo đầu vào cũng phải được xem xét riêng.

## 2. Ba thứ phải phân biệt

| Thành phần | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `System.console()` | Lấy `Console` gắn với JVM, nếu có | **Có thể là `null`**; không dùng `console.readLine` khi chưa kiểm tra |
| `Console.readLine()` | Đọc một dòng và trả `String` | Không in prompt; trả `null` nếu EOF |
| `Console.readLine("Hỏi: ")` | In prompt rồi đọc một dòng | Prompt không tự thêm newline nếu không có `%n` trong format |
| `Console.readLine("Hỏi %s: ", value)` | In prompt với `Formatter`, rồi đọc | `%s` được thay từ arguments; kiểu và số tham số phải hợp lệ |
| `System.out.print(...)` rồi `Console.readLine()` | In và đọc qua hai thao tác | Có thể cần `flush()` và không gom thành một thao tác đồng bộ |
| `BufferedReader.readLine()` | Đọc dòng từ một `Reader` | Hữu ích khi stdin đến từ file/pipe, nhưng không tự in prompt |
| `Console.readPassword(...)` | Nhập dữ liệu bí mật mà không echo | Trả `char[]`, **không** nên thay bằng `readLine` cho mật khẩu |

Những phương thức `Console.readLine()` và `Console.readLine(String, Object...)` đã tồn tại lâu và vẫn thuộc API chính thức ở Java SE 25; không phải API lỗi thời. `Console.readLine(Locale, String, Object...)` là overload mới hơn **từ JDK 23**, không có trên API `--release 17`; ví dụ chạy trên Java 17 sẽ không dùng overload này.

### Dòng kết thúc ở đâu?

`readLine` đọc tới ranh giới dòng hoặc EOF, bỏ ký tự kết thúc dòng như `\n`, `\r` hoặc `\r\n` khỏi chuỗi trả về. Nó **không tự bỏ** các khoảng trắng bên trái/phải nội dung. Ví dụ người dùng gõ hai dấu cách, chữ `An`, rồi hai dấu cách thì dữ liệu nhận được là `"  An  "`.

- Người dùng nhấn **Enter ngay**: thường nhận `""` (chuỗi rỗng), **không phải `null`**.
- Người dùng chỉ gõ dấu cách: nhận chuỗi không rỗng gồm khoảng trắng, ví dụ `"   "`.
- Luồng đầu vào đã hết trước khi nhận dòng mới: `null` (EOF).
- Người dùng nhập `An` và Enter: `"An"`, không có dấu Enter ở cuối.
- Một lời nhắc không phải phần của dữ liệu trả về; nó được **in ra**, còn input chỉ chứa nội dung người dùng nhập.

**Không dùng** `if (name == "")` để kiểm tra rỗng: so sánh chuỗi Java cần `name.isEmpty()` hoặc `name.isBlank()` theo yêu cầu nghiệp vụ; luôn xử lý `null` trước.

## 3. Cách in lời nhắc bằng overload `readLine(format, args)`

~~~java
String user = console.readLine("Tên người dùng: ");
String project = console.readLine("Dự án của %s: ", user);
String answer = console.readLine("Mức %d%% mục tiêu: ", 80);
~~~

Đây là **mã minh họa** với `console` đã khác `null`; chương trình thật cần kiểm tra EOF giữa các lần đọc.

`format` là chuỗi theo cú pháp `java.util.Formatter`:

- `%s`: chèn giá trị dưới dạng chuỗi. Ví dụ `readLine("Xin chào %s, nhập mã: ", "Lan")` hiển thị `Xin chào Lan, nhập mã: `.
- `%d`: chèn một giá trị số nguyên tương thích với `Formatter`.
- `%%`: hiển thị **một dấu phần trăm**. Nếu chuỗi format chứa `100%` không được escape, ký tự `%` có thể bị hiểu là mở đầu format specifier và gây lỗi.
- `%n`: xuống dòng theo hệ điều hành nếu muốn lời nhắc chiếm dòng riêng; với prompt thông thường, nên để dấu cách ở cuối và không thêm `%n` để con trỏ nằm cùng dòng.
- `args` là `Object...`; số lượng và kiểu argument phải hợp lệ với các format specifier.

### Prompt cố định tốt hơn format do người dùng nhập

Không lấy dữ liệu không tin cậy dùng **trực tiếp làm format string**:

~~~java
// Sai: dữ liệu do người dùng đưa có thể chứa %d, %s hoặc cú pháp format lỗi.
String result = console.readLine(userSuppliedPrompt);
~~~

Dùng format **được ứng dụng kiểm soát**, dữ liệu động là argument:

~~~java
// Tốt hơn: dấu % trong promptValue không bị phân tích như format specifier.
String result = console.readLine("%s: ", promptValue);
~~~

Hai đoạn là **mã ghép vào ngữ cảnh**. Ngoài việc dùng `%s`, vẫn cần giới hạn và kiểm soát các ký tự xuống dòng/control/escape trong `promptValue` khi đến từ bên ngoài, vì chúng có thể làm rối giao diện terminal hoặc log.

**Lỗi format** như thiếu argument cho `%s` hoặc dùng sai conversion có thể ném `IllegalFormatException` **trước khi có dữ liệu nhập**. Đừng nhầm exception của format với `null` (EOF) hoặc chuỗi rỗng.

### So sánh với `printf` rồi `readLine()`

Cách sau vẫn hợp lệ:

~~~java
console.printf("Tên của bạn: ");
String user = console.readLine();
~~~

Tuy nhiên hai lời gọi là hai thao tác riêng biệt, nên nếu nhiều thread cùng tương tác trên một console, prompt và thao tác đọc có thể bị xen kẽ với những thao tác khác. Overload `console.readLine("Tên của bạn: ")` thường rõ ràng và thuận tiện hơn, vì nó tạo lời nhắc rồi đọc trong một lời gọi. Javadoc mô tả các thao tác đọc/ghi/format của `Console` được đồng bộ để hoàn tất các thao tác quan trọng; điều này **không** biến cả hội thoại nhiều câu hỏi thành một transaction.

## 4. Lấy console và chính sách khi không có terminal

~~~java
Console console = System.console();
if (console == null) {
    // Chọn một trong hai: thông báo cần terminal, hoặc đọc từ System.in.
    System.err.println("Ứng dụng này cần terminal tương tác.");
    return;
}
String input = console.readLine("Nhập mã: ");
~~~

Đây là đoạn minh họa, `return` yêu cầu nó ở trong method.

### Tại sao `System.console()` lại có thể bằng `null`?

Console phụ thuộc vào **cách JVM được khởi chạy và nhà cung cấp console**. Chương trình chạy từ terminal có stdin/stdout thực có cơ hội nhận `Console`. Chạy trong IDE, automated tests, server, scheduler, container không có terminal, hoặc khi chuyển hướng input/output có thể cho kết quả khác.

**Chi tiết phiên bản đáng chú ý:**

- Với API Java 17, code phải kiểm tra `System.console() != null` trước khi gọi `readLine`; tuy vậy không dùng kết quả đó làm bằng chứng bảo mật rằng chắc chắn có một terminal thật.
- Từ **JDK 22**, API có `Console.isTerminal()` để hỏi rõ đối tượng `Console` có gắn với terminal hay không. Phương thức này **không tồn tại khi compile với `--release 17`**.
- Một số triển khai **JDK 22–24** dùng console provider dựa trên JLine và có thể trả `Console` ngay cả khi I/O đã chuyển hướng. Vì vậy `console != null` không bảo đảm đang có người gõ trực tiếp.
- **JDK 25 mặc định** chuyển khỏi JLine provider; hành vi khi redirect thường quay về `System.console() == null`. Tuy nhiên có thể có provider được cấu hình riêng, nên đừng dựa vào sự khác nhau về bản JDK để suy luận thay cho test môi trường thực.
- Với script/CI, nên có đường chạy qua `System.in` hoặc một lựa chọn CLI như `--stdin`, tránh phụ thuộc vào cách JVM quyết định tạo `Console`.

Nếu môi trường bắt buộc **terminal thật** và ứng dụng chỉ hỗ trợ JDK 22+, có thể kiểm tra `console != null && console.isTerminal()`; nhưng không copy dòng gọi `isTerminal()` vào chương trình nhắm `--release 17` vì nó không biên dịch với API target ấy.

### Đọc từ stdin khi không có Console

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

System.out.print("Tên: ");
System.out.flush();
String name = reader.readLine();  // có thể null khi EOF
~~~

Đây là mã minh họa cần import `java.io.BufferedReader`, `java.io.InputStreamReader`, `java.nio.charset.StandardCharsets` và xử lý/khai báo `IOException`. Nó đọc được input từ file/pipe; `BufferedReader` **không in prompt hộ bạn**. Việc cố định UTF-8 ở đây giả định đầu vào có encoding UTF-8; với chương trình triển khai thực, phải đồng bộ encoding với nguồn dữ liệu, không tự tin mọi terminal/file đều UTF-8. Java `Console` tự sử dụng encoding do môi trường cung cấp cho console; `Console.charset()` trả charset cho **output**, không phải lời hứa rằng mọi stdin đều có cùng encoding.

Khi dùng `System.in`, **tạo một BufferedReader và dùng thống nhất**. Đừng tạo lại nhiều buffered reader hoặc trộn với `Scanner`/`System.in.read()` cho cùng input mà không có chủ đích: buffer có thể đã đọc trước dữ liệu làm những lời gọi sau có vẻ “mất input”. Trong ứng dụng nhỏ, thường không cần đóng `System.in` vì nó thuộc quyền quản lý của runtime/quy trình gọi.

## 5. Chương trình Java 17+ đầy đủ: nhập hai chuỗi có lời nhắc

Mã dưới đây hỗ trợ **hai chế độ**:

1. Mặc định: thử `System.console()` và dùng `console.readLine(format, args)` nếu có.
2. Khi `Console` không có, hoặc truyền `--stdin`: in lời nhắc bằng `System.out.printf`, đọc bằng **một** `BufferedReader` trên `System.in`. `--stdin` là **tham số riêng của chương trình ví dụ**, không phải option của JVM hay của `java.io.Console`. Nó giúp kiểm thử bằng file/pipe mà không phụ thuộc khác biệt giữa console providers/JDK.

Ở chế độ đọc stdin, chương trình tự thêm một dòng mới **sau mỗi lượt đọc**, vì dữ liệu từ pipe không được terminal echo; vì thế output được trình bày thành từng dòng rõ ràng. Với console tương tác, nó **không** thêm dòng mới: khi người dùng nhấn Enter, terminal thông thường đã đưa con trỏ sang dòng tiếp theo.

Tạo file **`ConsolePromptDemo.java`** với **toàn bộ nội dung**:

~~~java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class ConsolePromptDemo {
    private static String ask(Console console, BufferedReader stdin,
                              String format, Object... args) throws IOException {
        if (console != null) {
            return console.readLine(format, args);
        }
        System.out.printf(format, args);
        System.out.flush();
        String line = stdin.readLine();
        // Redirected input does not echo, so add the line break ourselves.
        System.out.println();
        return line;
    }

    public static void main(String[] args) throws IOException {
        boolean forceStdin = args.length > 0 && "--stdin".equals(args[0]);
        Console console = forceStdin ? null : System.console();
        BufferedReader stdin = console == null
                ? new BufferedReader(new InputStreamReader(
                        System.in, StandardCharsets.UTF_8))
                : null;

        String rawName = ask(console, stdin, "Tên của bạn: ");
        if (rawName == null) {
            System.out.println("EOF: không có tên.");
            return;
        }
        String name = rawName.strip();
        if (name.isEmpty()) {
            System.out.println("Tên không được để trống.");
            return;
        }

        String rawCity = ask(console, stdin, "Bạn %s ở thành phố nào? ", name);
        if (rawCity == null) {
            System.out.println("EOF: không có thành phố.");
            return;
        }
        String city = rawCity.strip();
        if (city.isEmpty()) {
            System.out.println("Thành phố không được để trống.");
            return;
        }
        System.out.printf("Xin chào %s từ %s!%n", name, city);
    }
}
~~~

**Giải thích cơ chế:**

1. `System.console()` trả `Console` nếu provider và môi trường cung cấp. Với tham số `--stdin`, chương trình **chủ động không sử dụng console**.
2. `ask(...)` là một helper gom logic tạo prompt. Nhánh console dùng đúng `readLine(format, args)`; nhánh stdin dùng `System.out.printf + flush + BufferedReader.readLine`.
3. `stdin` chỉ được tạo khi không dùng console. Do đó chương trình **không đọc chéo hai reader** trên cùng luồng input.
4. `rawName == null` biểu thị EOF. Dòng rỗng sau khi `strip()` thì được báo là dữ liệu không hợp lệ. `String.strip()` có trên Java 11+, vì vậy hợp lệ với Java 17.
5. Prompt thứ hai truyền `name` qua `%s`, là ví dụ cụ thể của lời nhắc có argument. Nó không biến tên user thành format string.
6. Không có cách làm nào trong đây bắt buộc class `Console` tồn tại lúc chạy; khi không có, chương trình vẫn có thể đọc stdin. Việc console đọc/ghi có thể ném `IOError`; stdin fallback có thể ném `IOException`.
7. Đây là **chương trình minh họa để học**, chưa phải form production có giới hạn độ dài input, rate limit, retry hay lọc terminal control characters.

### 5.1. Biên dịch và chạy tương tác

Dùng JDK 17+ trong terminal của hệ điều hành:

~~~bash
javac -encoding UTF-8 --release 17 ConsolePromptDemo.java
java ConsolePromptDemo
~~~

**Ví dụ tương tác minh họa** khi người dùng tự gõ `An` và `Hue` (dòng user nhập được terminal echo nếu console thực có hỗ trợ echo):

~~~text
Tên của bạn: An
Bạn An ở thành phố nào? Hue
Xin chào An từ Hue!
~~~

Ba dòng trên là **transcript màn hình**, không phải stdout cố định khi không có input; lời nhắc là phần ứng dụng in, còn `An` và `Hue` do người dùng gõ. Trên terminal, cách hiển thị ký tự có thể khác nhau tùy platform/console provider.

### 5.2. Chạy tự động bằng input qua pipe hoặc file

Ở Bash/Linux/macOS, để cung cấp hai dòng bằng pipeline, ghi:

~~~bash
printf 'An\nHue\n' | java ConsolePromptDemo --stdin
~~~

**Stdout chính xác** trong chế độ `--stdin` với input trên:

~~~text
Tên của bạn: 
Bạn An ở thành phố nào? 
Xin chào An từ Hue!
~~~

Trên PowerShell/Windows, cách dễ kiểm soát encoding là tạo file văn bản UTF-8 không BOM có **đúng hai dòng** `An` và `Hue`, sau đó chạy qua `cmd.exe` redirection hoặc bằng cơ chế redirect input thích hợp. Cú pháp `<` trong lệnh sau thuộc **cmd.exe**, không phải cú pháp redirection của Windows PowerShell 5.1:

~~~bat
java ConsolePromptDemo --stdin < input.txt
~~~

Đây là cơ chế đặc biệt hữu ích khi chạy unit/integration test hoặc CI vì không phụ thuộc có console thật. Với file input, `readLine` không echo nội dung file, nên chương trình thêm newline sau mỗi prompt.

### 5.3. Những trường hợp biên cần kiểm thử

**Chỉ có một dòng trống** (tức file chứa đúng một newline) → stdout:

~~~text
Tên của bạn: 
Tên không được để trống.
~~~

**Input rỗng hoàn toàn** (EOF ngay) → stdout:

~~~text
Tên của bạn: 
EOF: không có tên.
~~~

**Hai dòng hợp lệ** (`An` rồi `Hue`) → có câu chào như phần 5.2.

Ba trường hợp trên đã được thử với **JDK 24, biên dịch `--release 17`**, sử dụng input file trong chế độ `--stdin`. Các dòng **không** chứa nội dung người nhập sau prompt vì đây là output của đường pipe chứ không phải phiên terminal echo.

Trong ứng dụng thật, có thể muốn hỏi lại nếu người dùng nhập rỗng, nhưng cần đặt giới hạn số lần và xử lý EOF để tránh vòng lặp vô hạn:

~~~java
// Mã minh họa trong ngữ cảnh có helper ask(...) và biến console/stdin.
String value = null;
for (int attempt = 0; attempt < 3; attempt++) {
    String line = ask(console, stdin, "Nhập mã: ");
    if (line == null) break;            // EOF: không hỏi lại mãi
    if (!line.isBlank()) {
        value = line.strip();
        break;
    }
}
~~~

Đây là **đoạn rời**, không copy trực tiếp ngoài method nếu chưa khai báo các biến. Tùy yêu cầu, đừng dùng `strip()` nếu khoảng trắng đầu/cuối là **dữ liệu có ý nghĩa**, ví dụ tên tệp có khoảng trắng hoặc câu trả lời cần giữ nguyên.

## 6. Dữ liệu nhạy cảm: `readLine` không thay thế `readPassword`

`Console.readLine()` thường cho phép **echo ký tự nhập** lên terminal. Với mật khẩu, token hoặc passphrase, hãy dùng `readPassword`, được thiết kế để đọc khi echo tắt và trả về `char[]`. Không đưa password vào `readLine` rồi chỉ “ẩn khi in ra”, vì input có thể đã hiển thị trước đó.

~~~java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Cần terminal để nhập mật khẩu an toàn.");
}

char[] password = console.readPassword("Mật khẩu: ");
if (password == null) {
    throw new IllegalStateException("EOF khi nhập mật khẩu.");
}
try {
    // Xác thực thông qua cơ chế phù hợp; không in hoặc ghi log password.
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

Đây là **mã minh họa tích hợp vào ứng dụng**, phần xác thực phải được triển khai riêng theo yêu cầu bảo mật. Xóa nội dung mảng ký tự giúp giảm thời gian dữ liệu nhạy cảm còn hiện diện trong memory; nó không bảo đảm mọi bản sao nội bộ của dữ liệu đều đã bị loại bỏ. Không tạo `new String(password)` một cách không cần thiết vì `String` là immutable và khó xóa khỏi memory có chủ đích.

Nếu `System.console() == null`, **không** tự động fallback sang `System.in`/`BufferedReader` cho mật khẩu rồi tuyên bố vẫn có no-echo. Với stdin redirect, bí mật có thể đã nằm trong script/file/log hoặc hệ thống shell; dùng giải pháp secure secret provisioning phù hợp.

## 7. Ngoại lệ và lỗi thường gặp

### Hai loại lỗi khác nhau

`Console.readLine(format, args)` có thể gây:

- **`IllegalFormatException`**: format specifier không hợp lệ, sai kiểu hoặc thiếu argument; đây là lỗi **lập trình lời nhắc**, không phải user nhập sai.
- **`IOError`**: có lỗi I/O trong quá trình đọc console. Đây là `Error` thuộc Java I/O API, không phải `IOException` checked exception. Đừng biến mọi lỗi I/O thành dòng trống và tiếp tục vô hạn.

`BufferedReader.readLine()` trong nhánh fallback có thể ném **`IOException`** (checked) và cũng trả `null` khi EOF. Vì vậy helper trong ví dụ khai báo `throws IOException` nhưng `Console.readLine` vẫn có khả năng ném `IOError` unchecked khi backend console gặp sự cố.

### Lỗi phổ biến và cách sửa

| Sai lầm | Điều xảy ra | Cách sửa |
| --- | --- | --- |
| `System.console().readLine("Tên: ")` không kiểm tra | `NullPointerException` khi JVM không có console | Lấy console và kiểm tra `null` trước |
| Nghĩ `readLine()` tự in câu hỏi | Chương trình chờ input mà không có prompt | Dùng `readLine("Câu hỏi: ")` |
| Dùng `readLine("Tỷ lệ 100%: ")` | `%` có thể bị phân tích là format specifier không hợp lệ | Viết `100%%` |
| Đọc `null` rồi gọi `strip()` hoặc `length()` | `NullPointerException` khi EOF | Kiểm tra `null` trước |
| Dùng `name == ""` | So sánh object reference, không so sánh nội dung | `name.isEmpty()` / `isBlank()` sau null check |
| Hiểu `""` là EOF | Bỏ qua trường hợp chỉ nhấn Enter | Phân biệt `null` và chuỗi rỗng |
| Bảo đảm console tồn tại trong IDE/CI | Chương trình lỗi hoặc chờ input mãi | Có đường stdin fallback, hoặc thông báo cần terminal |
| Dùng `console != null` làm phép kiểm terminal tuyệt đối trên mọi JDK | JDK 22–24 có provider trả console cả khi redirect | Nếu chỉ nhắm JDK 22+, dùng `isTerminal()` khi cần; thử môi trường thực |
| Mix `Scanner` và `BufferedReader` trên cùng `System.in` | Đệm dữ liệu có thể làm những lần đọc sau không như dự kiến | Dùng một reader nhất quán |
| Không `flush()` sau `System.out.print` | Lời nhắc có thể chưa hiện trước khi chương trình chờ input | Flush đầu ra khi dùng print + read riêng |
| Dùng `readLine` đọc mật khẩu | Input có thể được echo | Dùng `readPassword` và xóa `char[]` |
| Gọi `Integer.parseInt(console.readLine(...))` mà không kiểm tra | Null, rỗng hoặc chữ không phải số gây exception | Kiểm tra null/blank và bắt `NumberFormatException` phù hợp |
| Xem input là dữ liệu tin cậy | Có thể có control characters hoặc input rất dài | Kiểm tra size, chuẩn hóa theo mục đích và không log bí mật |

### Không dùng format string động tùy tiện

Ví dụ người dùng đặt nhãn `"100% hoàn thành"` rồi ứng dụng gọi:

~~~java
String answer = console.readLine(userLabel);
~~~

Có thể gây format error vì dấu `%` trong nhãn. Dùng `console.readLine("%s", userLabel)` nếu muốn in chính giá trị label mà không để `Formatter` diễn giải các ký hiệu `%`. Nhưng vẫn phải xử lý việc nhãn có thể chứa newline hoặc ký tự điều khiển terminal.

## 8. Khi nào chọn Console, BufferedReader hoặc Scanner?

| Nhu cầu | API thường phù hợp | Lý do |
| --- | --- | --- |
| CLI hỏi từng dòng với prompt và terminal thật | `Console.readLine(format, args)` | Một lời gọi cho prompt và input |
| CLI cần nhập password không echo | `Console.readPassword(format, args)` | API chuyên biệt cho dữ liệu nhạy cảm |
| File, pipe, subprocess, batch script, CI | `BufferedReader` trên `System.in` | Không phụ thuộc console terminal |
| Nhập token/số/phân tách theo delimiter | `Scanner` nếu cần khả năng parse | Nhiều thao tác parsing hơn so với line-based read |
| Command-line options không cần prompt | `main(String[] args)` / parser CLI | Không yêu cầu tương tác |
| HTTP service / GUI | Framework/API input của môi trường | Console thường không có và có thể block server thread |

Một chương trình Java có thể hỗ trợ **cả chế độ tương tác lẫn chế độ batch**; quan trọng là chính sách được nói rõ. Tránh bắt người dùng automation gõ câu trả lời cho prompt, và tránh coi mỗi process có stdin như đang có console tương tác.

### Đồng thời và blocking

`Console.readLine` là thao tác **blocking** cho đến khi có dòng/EOF hoặc lỗi I/O. Nhiều thread cùng dùng console dễ gây trải nghiệm khó hiểu dù API có đồng bộ nội bộ. Nên dùng **một luồng điều phối hội thoại**; nếu cần timeout/cancel, phải thiết kế theo cách kiểm soát input phù hợp thay vì giả định interrupt lúc nào cũng ngắt được mọi lệnh đọc terminal.

Một prompt không tự đảm bảo dữ liệu được nhập đúng. Ở mức ứng dụng cần đặt validation, giới hạn độ dài, số lần thử và xử lý EOF/exit rõ ràng. Với input do người dùng cung cấp, tránh in lại trực tiếp nội dung chứa ANSI escape/control characters khi hiển thị kết quả trong terminal/log không tin cậy.

## 9. Checklist áp dụng

1. **Đúng môi trường?** Xác định chương trình chạy tại terminal, IDE, scheduler hay pipeline.
2. **Chọn đúng overload?** `readLine()` chỉ đọc; `readLine(format, args)` in lời nhắc rồi đọc.
3. **Kiểm tra console?** `System.console()` có thể `null`; nhớ khác biệt provider/JDK nếu cần xác nhận terminal thật.
4. **Format an toàn?** Prompt format là chuỗi cố định, dùng `%s`/`%d` và escape `%%`; không lấy input bên ngoài làm format.
5. **Xử lý EOF?** `null` khác chuỗi rỗng, khác khoảng trắng.
6. **Xử lý user input?** Validate/canonicalize tùy bài toán trước khi sử dụng; không strip dữ liệu nếu dấu cách có ý nghĩa.
7. **Đọc nhiều dòng?** Cần gọi `readLine` nhiều lần; một lời gọi chỉ đọc một dòng.
8. **Automation?** Dùng `--stdin` hay đường batch input đã thiết kế và encoding thống nhất.
9. **Bí mật?** Dùng `readPassword` thay vì `readLine`, không log, xóa `char[]` sớm.
10. **Chạy thử?** Kiểm tra phiên terminal thực, pipe/file, input rỗng và EOF riêng.

## 10. Câu hỏi tự kiểm tra

1. **`Console.readLine("Tên: ")` làm gì khác `Console.readLine()`?** Cái đầu in prompt rồi đọc; cái sau chỉ đọc.
2. **Người dùng nhấn Enter không gõ gì thì kết quả là `null` hay `""`?** Thường là `""`; `null` dành cho EOF.
3. **`readLine` có xóa whitespace và newline không?** Loại bỏ line-termination chars, **không** tự trim whitespace.
4. **Vì sao `System.console()` phải kiểm tra `null`?** JVM có thể không có console tùy cách khởi chạy và provider.
5. **Với JDK 22–24, `console != null` có luôn chứng minh có terminal thật không?** Không; có thể có console từ provider dù I/O redirect. `isTerminal()` chỉ có từ JDK 22.
6. **Muốn in prompt `"Mức 80%"` bằng formatter thì viết sao?** `console.readLine("Mức %d%%: ", 80)`.
7. **Có nên nhận input từ pipe bằng `Console` rồi xem output/echo tương tự terminal thật không?** Không; đường `System.in`/`BufferedReader` rõ ràng hơn cho batch tests.
8. **Vì sao main ví dụ nhận `--stdin`?** Đó là flag của **ứng dụng demo** buộc đường fallback để test nhất quán trên các JDK/provider.
9. **Trong bài nhập mật khẩu nên dùng `readLine` hay `readPassword`?** `readPassword`; kiểm tra `null` và xóa `char[]` khi xong.
10. **Nếu chuỗi format có `%q` thì chuyện gì xảy ra?** Format không hợp lệ và có thể ném `IllegalFormatException`, không phải lỗi do dòng user vừa nhập.

## 11. Tài liệu chính thức và tham khảo còn hiệu lực

- [Java SE 25 — java.io.Console](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): `readLine()`, `readLine(String, Object...)`, EOF, định dạng prompt, `IOError`, `readPassword`, `isTerminal()` và charset.
- [Java SE 25 — java.lang.System.console()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#console()): lấy console gắn với JVM, có thể trả `null`.
- [Java SE 25 — java.io.BufferedReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): `readLine()` cho đầu vào dòng từ reader.
- [Java SE 25 — java.util.Formatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): `%s`, `%d`, `%%`, `%n` và lỗi format.
- [Oracle JDK 25 Release Notes — Default Console Implementation No Longer Based on JLine](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): hành vi hiện hành của console provider.
- [Inside Java — JLine is now the Default Console Provider (bối cảnh JDK 22–24)](https://inside.java/2023/07/31/quality-heads-up/): bối cảnh thay đổi provider và lý do `console != null` không phải phép thử terminal độc lập. Bài chỉ dùng thông tin này để giải thích khác biệt còn gặp trên các JDK được sử dụng, không đề xuất quay lại cấu hình cũ.

**Ghi nhớ:** `Console.readLine(format, args)` là cách tự nhiên nhất để **hỏi một câu và đọc một dòng** trên terminal, nhưng không tồn tại console ở mọi nơi. Luôn phân biệt **prompt**, **chuỗi người dùng nhập**, **EOF**, và **chế độ input của môi trường**, rồi chọn `Console` hoặc `BufferedReader` đúng nhu cầu.