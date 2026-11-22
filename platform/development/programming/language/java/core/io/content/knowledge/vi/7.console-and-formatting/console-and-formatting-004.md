# Console.reader, writer, readLine và readPassword trong Java

> **Chủ đề:** Java Core I/O → **Console và định dạng**. Bài này giải thích cách lấy thiết bị console tương tác, đọc/ghi ký tự bằng `reader()` và `writer()`, nhập từng dòng bằng `readLine()`, nhập dữ liệu bí mật bằng `readPassword()`, cùng khác biệt giữa console thực và standard streams khi chạy trong IDE, CI hoặc qua pipe. Ví dụ dùng API của Java 17+; `java.io.Console` đã có từ Java 6.

## 1. Console là gì, có giống System.in và System.out không?

`java.io.Console` là API Java SE cho thiết bị **console dạng ký tự** gắn với JVM, nếu có. Nó thích hợp với ứng dụng chạy tương tác từ terminal: hiện lời nhắc, đọc tên người dùng, chọn thao tác, nhập mật khẩu mà terminal không echo lại nội dung.

Lấy Console bằng:

~~~java
import java.io.Console;

Console console = System.console();
if (console == null) {
    System.err.println("Không có console tương tác cho tiến trình này.");
    // Chọn cách làm việc khác hoặc dừng tác vụ tương tác.
}
~~~

Đây là **fragment**, nằm trong một phương thức. Không thể tự tạo Console bằng `new Console()`: phương thức phổ biến là `System.console()`. JVM có một đối tượng Console gắn với console của tiến trình nếu môi trường cung cấp.

**Phân biệt quan trọng:**

| Đối tượng/API | Công dụng | Khi chạy từ IDE/CI hoặc redirect |
| --- | --- | --- |
| `System.in` | Standard input dạng `InputStream` (byte) | Có thể đọc pipe/file hoặc nguồn do môi trường cấu hình, kể cả khi không có console. |
| `System.out` | Standard output dạng `PrintStream` | Có thể ghi tới terminal, file hoặc pipe; không đồng nghĩa luôn có Console. |
| `System.err` | Standard error, thường dùng cho thông báo lỗi | Có thể redirect độc lập; không bảo đảm Console tồn tại. |
| `System.console()` | Trả về `Console` nếu JVM có thiết bị console phù hợp, ngược lại `null` | Thường `null` trong nhiều IDE, trình chạy nền, môi trường CI hoặc khi chuyển hướng luồng; phải kiểm tra thực tế. |
| `Console.reader()` / `Console.writer()` | Reader/PrintWriter kiểu ký tự gắn với console | Chỉ gọi sau khi đã xác nhận `console != null`. |
| `Console.readLine()` / `readPassword()` | Đọc tương tác cấp dòng, hoặc cấp dòng với echo bị tắt | Không thay thế API đọc dữ liệu batch từ file/pipe nếu không có console. |

**Không suy diễn:** “chương trình có `System.in` tức có Console” là sai. Console phụ thuộc nền tảng và cách khởi động JVM. Trên terminal thông thường, `System.console()` hay có giá trị; trong test runner, chương trình launch bởi IDE hoặc lệnh redirect, nó thường `null`. Hành vi thực tế có thể khác theo JDK/launcher/terminal, nên code phải xử lý nhánh `null`.

## 2. Tổng quan bốn API được giao

| API | Kết quả | Đơn vị thao tác | Đặc điểm |
| --- | --- | --- | --- |
| `console.reader()` | `Reader` duy nhất gắn với console | `char`/UTF-16 code unit | Đọc ký tự trực tiếp, thích hợp parser/scanner tự quản lý. Không ẩn nội dung gõ. |
| `console.writer()` | `PrintWriter` duy nhất gắn với console | Văn bản đã mã hóa để xuất console | `print`, `println`, `printf`; nên flush khi cần prompt hiển thị ngay. |
| `console.readLine()` hoặc `readLine(fmt,args...)` | `String`, hoặc `null` khi EOF | Một dòng ký tự | Có thể hiển thị prompt, đọc tới dấu kết thúc dòng, loại bỏ ký tự kết thúc dòng. Nội dung nhập thường được echo. |
| `console.readPassword()` hoặc `readPassword(fmt,args...)` | `char[]`, hoặc `null` khi EOF | Một dòng ký tự nhạy cảm | Vô hiệu hóa echo khi nhập mật khẩu; trả mảng ký tự có thể xóa sau sử dụng. |

Các biến thể không tham số đọc một dòng/secret mà không cung cấp prompt. Các biến thể nhận `String fmt, Object... args` tạo prompt bằng cú pháp `Formatter`, ví dụ `console.readLine("Chào %s, tên bạn? ", role)`. Nếu prompt chứa ký tự `%` theo nghĩa literal trong **format string**, viết `%%` để tránh lỗi định dạng.

**Cùng một Console không có bốn nguồn I/O độc lập.** `reader()`, `writer()` và các hàm đọc/ghi cấp cao sử dụng thiết bị console chung. Tự đọc xen kẽ từ `reader()`, `System.in` hoặc nhiều wrapper có bộ đệm trên cùng nguồn có thể làm mất đồng bộ logic đọc.

## 3. `Console.reader()` — đọc console như Reader

`reader()` trả về đối tượng `java.io.Reader` duy nhất gắn với Console. Nó dành cho chương trình cần logic phân tích ký tự riêng, chẳng hạn parser hoặc `Scanner` xử lý token. Các phương thức của `Reader` nhận/trả dữ liệu theo **UTF-16 code unit**, chứ không phải byte thô.

~~~java
// Fragment: phải lấy được console trước khi dùng.
Console console = System.console();
if (console != null) {
    Reader reader = console.reader();
    int codeUnit = reader.read();
    if (codeUnit == -1) {
        console.writer().println("Không còn dữ liệu đầu vào.");
    } else {
        console.writer().printf("Mã char đầu tiên: U+%04X%n", codeUnit);
    }
}
~~~

Vì đây là **fragment**, cần import `java.io.Console`, `java.io.Reader`, khai báo hoặc bắt `IOException` của `Reader.read()`. Nếu người dùng gõ emoji ngoài BMP, một `read()` trả **một code unit**, không đảm bảo toàn bộ code point. `reader()` dùng để đọc dữ liệu nhập thông thường, không có cam kết tắt echo.

### 3.1. Đọc theo dòng trên Reader có khác readLine không?

Có. `Console.readLine(...)` cho tình huống prompt + một dòng thông thường và trả `String`. `reader().read(...)` có thể chặn đợi người dùng hoàn tất dòng; tài liệu `Console.reader` nêu các bulk-read method sẽ không đọc vượt biên dòng trong một invocation dù buffer còn chỗ. `Reader.read()` trả `int` với `-1` ở EOF, và có thể đọc từng code unit.

Ví dụ chuyển Reader thành bộ phân tích:

~~~java
// Fragment: chỉ dùng khi console != null.
java.util.Scanner scanner =
        new java.util.Scanner(console.reader());

String command = scanner.nextLine(); // có thể ném khi không còn dòng.
~~~

`Scanner` còn có quy tắc delimiter, locale và exception của riêng nó. **Không** dùng đồng thời `scanner.nextLine()` và `console.readLine()` trên cùng console rồi giả định các buffer sẽ phối hợp chính xác. Chọn một kiểu đọc phù hợp với vòng đời tương tác. Đừng vô tình đóng scanner giữa chừng nếu code sau vẫn cần tiếp tục dùng chung console.

### 3.2. Đóng Reader do Console trả về?

Theo API Java 21, gọi `close()` trên đối tượng do `console.reader()` hoặc `console.writer()` trả về **không đóng underlying console stream**. Tuy nhiên chúng là đối tượng gắn với Console được chia sẻ, nên tránh tự ý tạo nhiều wrapper rồi đóng/đọc xen kẽ. Sở hữu tài nguyên và hành vi của wrapper (ví dụ `Scanner`, `BufferedReader`) vẫn cần xem riêng. Với CLI đơn giản, thường dùng trực tiếp `readLine()` để không phải tự quản lý stream đọc.

## 4. `Console.writer()` — viết với PrintWriter

`writer()` trả về đối tượng `PrintWriter` gắn với console. Bạn có thể:

- `writer().print(value)` để viết không xuống dòng.
- `writer().println(value)` để viết và thêm dấu xuống dòng.
- `writer().printf("Đã nhận %d mục%n", count)` để định dạng chuỗi.
- `writer().flush()` hoặc `console.flush()` để đẩy nội dung đang đệm ra thiết bị, hữu ích trước khi chờ nhập.

~~~java
// Fragment: console khác null.
java.io.PrintWriter out = console.writer();
out.println("Công cụ nhập dữ liệu");
out.printf("Phiên làm việc: %s%n", "demo");
out.print("Gõ lệnh: ");
out.flush(); // Hiển thị lời nhắc trước khi chờ.
String command = console.readLine();
~~~

Tài liệu `Console` cũng có `console.printf(...)` và `console.format(...)` để in ra console trực tiếp, cùng `console.flush()`. Nếu muốn prompt trên một dòng không có dấu xuống dòng, `console.readLine("Tên: ")` thường rõ ràng hơn tự `print` rồi `readLine()`.

**Đặc điểm của PrintWriter:** nhiều phương thức ghi của `PrintWriter` không ném trực tiếp `IOException` kiểu checked; chúng có thể ghi nhận lỗi để kiểm tra với `checkError()`. Nếu ứng dụng đòi hỏi kiểm tra nghiêm ngặt lỗi xuất, cân nhắc kiểm tra trạng thái lỗi thay vì mặc định `println()` luôn thành công. API `Console.readLine/readPassword` lại có thể ném `java.io.IOError` khi lỗi I/O.

### 4.1. Charset của Console

Console làm việc với ký tự và cần charset phù hợp với môi trường console. Từ **Java 17**, `console.charset()` trả `Charset` sử dụng bởi Console. Charset này có thể **khác** `Charset.defaultCharset()`. Do đó không nên khẳng định mọi Console chỉ dùng UTF-8 hay mặc định của chương trình quyết định cách terminal hiển thị mọi ký tự.

~~~java
// Fragment Java 17+: console != null.
console.writer().printf("Console charset: %s%n", console.charset());
console.flush();
~~~

Khi xuất tiếng Việt bị lỗi, xem xét terminal/font/locale/charset và cấu hình luồng. Không giải quyết bằng cách mù quáng chuyển byte sang `char`; `Console.writer()` đã làm việc ở tầng ký tự, còn terminal chịu trách nhiệm render.

## 5. `Console.readLine()` — đọc một dòng nhập thông thường

Hai dạng cơ bản:

~~~java
String line = console.readLine();                  // Không in prompt.
String name = console.readLine("Tên của bạn: ");  // Có prompt.
~~~

**Hợp đồng quan trọng:**

1. Phương thức đợi người dùng nhập một dòng; dữ liệu bình thường được console **echo** khi gõ.
2. Trả một `String` không chứa ký tự kết thúc dòng `\n`, `\r` hoặc cặp `\r\n`. Nó không tự `trim()` khoảng trắng đầu/cuối.
3. Khi hết input, trả `null`. Dòng rỗng người dùng nhấn Enter là **`""`**, khác hoàn toàn `null`.
4. Nếu lỗi I/O, phương thức có thể ném `IOError`; định dạng prompt sai có thể ném `IllegalFormatException`.
5. Prompt `String fmt` dùng quy tắc định dạng, không phải câu SQL hoặc command. Đừng đưa input không tin cậy thành **format string** nếu mục đích chỉ hiển thị nguyên văn.

Ví dụ nhập tên và kiểm tra EOF:

~~~java
// Fragment: console đã được xác nhận khác null.
String name = console.readLine("Tên hiển thị: ");
if (name == null) {
    console.writer().println("Đã kết thúc đầu vào.");
} else if (name.isEmpty()) {
    console.writer().println("Bạn chưa nhập tên.");
} else {
    console.writer().printf("Xin chào, %s!%n", name);
}
console.flush();
~~~

**Dòng rỗng không phải EOF.** Phân biệt chúng khi xây menu CLI. Nếu đọc số, `readLine()` trả **String**, không tự parse số; phải dùng `Integer.parseInt` với xử lý `NumberFormatException` và xác định cách xử lý khoảng trắng.

### 5.1. Lời nhắc có tham số và ký tự %

~~~java
// Fragment: định dạng prompt theo java.util.Formatter.
String project = "Java";
String answer = console.readLine("Bạn muốn học %s? [y/n] ", project);

// Dấu % literal trong format string phải viết %%.
String ratio = console.readLine("Nhập mức hoàn thành (0..100%%): ");
~~~

Nếu biến `project` là dữ liệu đến từ nguồn khác, cách truyền nó làm **đối số** `%s` rõ ràng và an toàn hơn đặt cả biến làm format string. Đừng nhầm `String.format`/`printf` với nối chuỗi thuần túy: dấu `%` có ý nghĩa cú pháp.

## 6. `Console.readPassword()` — đọc chuỗi bí mật mà không echo

`readPassword()` đọc một dòng trong chế độ **echo disabled**, tức ký tự người dùng gõ không được in lại ra console như lúc nhập thường. Nó trả `char[]` thay vì `String`.

~~~java
// Fragment: console đã có và mã nằm trong method.
char[] password = console.readPassword("Mật khẩu: ");
if (password == null) {
    console.writer().println("Đã kết thúc đầu vào.");
} else {
    try {
        // Truyền char[] tới một API kiểm tra bí mật có hỗ trợ char[],
        // hoặc xử lý tạm thời theo yêu cầu ứng dụng.
        // Không in mật khẩu, không ghi log mật khẩu.
    } finally {
        java.util.Arrays.fill(password, '\0');
    }
}
~~~

Lý do chọn `char[]`: phần tử mảng có thể được ghi đè ngay sau khi dùng. `String` bất biến, không có API đáng tin để chủ động xóa nội dung trong bộ nhớ. **Xóa mảng không phải bảo đảm tuyệt đối xóa mọi bản sao bí mật** trong JVM, thư viện, OS hay swap, nhưng giảm thời gian bản sao bạn kiểm soát còn tồn tại.

**Không nên làm:**

~~~java
// Ví dụ SAI về xử lý dữ liệu bí mật:
String leaked = new String(password);
System.out.println("password=" + leaked);
~~~

Chuyển mảng sang `String` và ghi ra stdout/log có thể tạo bản sao giữ lâu và phơi bày bí mật. Tốt hơn dùng API xác thực hỗ trợ dữ liệu có vòng đời ngắn (char[]/byte[] hoặc cơ chế credential chuyên dụng) và dọn dẹp các buffer trung gian khi có thể.

**Echo bị tắt không đồng nghĩa mật khẩu được bảo mật hoàn toàn.** Nó chỉ che phần nhập khỏi màn hình terminal; không thay thế kết nối an toàn, xác thực đúng, phân quyền, quản lý secrets hoặc phòng chống các thành phần bên ngoài ghi lại input. Với terminal không khả dụng, đừng lặng lẽ chuyển sang `Scanner(System.in)` để nhập mật khẩu theo chế độ echo bình thường mà không cảnh báo hoặc thiết kế bảo mật phù hợp.

### 6.1. Mật khẩu rỗng và hết đầu vào

- Khi người dùng chỉ nhấn Enter, đầu vào có thể là `new char[0]`, tức **mảng rỗng** (phải quyết định có chấp nhận hay không).
- Khi EOF, `readPassword()` trả `null`; không gọi `Arrays.fill(null,...)` hoặc `password.length` khi chưa kiểm tra.
- `readPassword()` có thể ném `IOError` khi thao tác console thất bại, hoặc `IllegalFormatException` nếu format prompt sai.
- Trường hợp người dùng hủy ứng dụng bằng tín hiệu của OS không đồng nghĩa nhất thiết sẽ nhận `null`; môi trường/terminal có thể kết thúc process trước khi Java xử lý.

## 7. Chương trình mẫu tương tác hoàn chỉnh: đọc tên và mật khẩu

Tạo file **`ConsoleInputDemo.java`**:

~~~java
import java.io.Console;
import java.io.PrintWriter;
import java.util.Arrays;

public class ConsoleInputDemo {
    public static void main(String[] args) {
        Console console = System.console();
        if (console == null) {
            System.err.println("Không có console tương tác; hãy chạy từ terminal.");
            return;
        }

        PrintWriter out = console.writer();
        out.println("=== Java Console Demo ===");
        out.flush();

        String name = console.readLine("Tên hiển thị: ");
        if (name == null) {
            out.println("Đầu vào đã kết thúc.");
            out.flush();
            return;
        }

        char[] password = console.readPassword("Mật khẩu (không echo): ");
        if (password == null) {
            out.println("Đầu vào đã kết thúc.");
            out.flush();
            return;
        }

        try {
            // Chỉ mô phỏng việc nhận dữ liệu; chưa xác thực mật khẩu.
            out.printf("Xin chào, %s. Đã nhận thông tin nhập.%n", name);
            out.flush();
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Lệnh biên dịch/chạy trong terminal tương tác ở thư mục có file:

~~~bash
javac --release 17 ConsoleInputDemo.java
java ConsoleInputDemo
~~~

**Ví dụ phiên nhập minh họa** (dòng nhập tên do người dùng gõ; nội dung nhập tại mật khẩu không xuất hiện trong terminal):

~~~text
=== Java Console Demo ===
Tên hiển thị: Mai
Mật khẩu (không echo):
Xin chào, Mai. Đã nhận thông tin nhập.
~~~

Đây là **transcript phụ thuộc nhập liệu**, không phải stdout cố định của mọi môi trường. Nếu JVM không có console, chương trình chỉ ghi vào stderr:

~~~text
Không có console tương tác; hãy chạy từ terminal.
~~~

Ví dụ cố ý **không** xác thực mật khẩu với giá trị hard-code: mục tiêu là cách nhận/dọn mảng nhạy cảm trong CLI. Khi mở chương trình qua nhiều IDE hoặc lệnh redirect, `System.console()` có thể `null` và nhánh lỗi là hành vi đúng được dự kiến. Đừng sửa nhánh này bằng cách in secret ra log hoặc tạo `String`.

### 7.1. Vì sao không dùng try-with-resources cho Console?

`Console` không triển khai `AutoCloseable`; không viết `try (Console c = System.console())`. Các đối tượng `Reader` và `PrintWriter` trả bởi console dùng chung vòng đời thiết bị; với CLI đơn giản, bạn không cần tự đóng chúng sau mỗi prompt. Hàm `Console.flush()` tồn tại để đẩy output theo nhu cầu. `Arrays.fill(password, '\0')` trong `finally` là **cleanup nội dung nhạy cảm**, khác với `close()` một I/O resource.

## 8. Khi cần `reader()` và `writer()` trực tiếp

Chọn chúng khi bạn muốn parser tự điều khiển từng ký tự/nhóm ký tự hoặc có một API nhận `Reader`/`Writer`. Ví dụ **độc lập** dưới đây chỉ minh họa đọc một UTF-16 code unit, không xử lý password hoặc kết hợp các cơ chế input khác.

Tạo **`ConsoleReaderWriterDemo.java`**:

~~~java
import java.io.Console;
import java.io.IOException;
import java.io.Reader;
import java.io.PrintWriter;

public class ConsoleReaderWriterDemo {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        if (console == null) {
            System.err.println("Không có console tương tác.");
            return;
        }

        Reader in = console.reader();
        PrintWriter out = console.writer();

        out.print("Nhập một ký tự ASCII rồi Enter: ");
        out.flush();

        int first = in.read();
        if (first == -1) {
            out.println("EOF");
        } else {
            out.printf("Mã UTF-16 đầu tiên: U+%04X%n", first);
        }
        out.flush();
    }
}
~~~

~~~bash
javac --release 17 ConsoleReaderWriterDemo.java
java ConsoleReaderWriterDemo
~~~

Nếu người dùng nhập chữ `A` rồi Enter, phần chương trình tự in sau khi đọc sẽ là:

~~~text
Mã UTF-16 đầu tiên: U+0041
~~~

Ngoài output này, terminal có thể echo lời nhập và lời nhắc nên transcript toàn bộ còn phụ thuộc môi trường. Ví dụ chỉ đọc **một** `char`, vì vậy ký tự Enter còn ở buffer/nguồn đọc; không dùng đoạn này làm vòng lặp CLI nhiều câu hỏi nếu chưa xử lý phần còn lại của dòng. Với ký tự nằm ngoài BMP như emoji, cần đọc cặp surrogate hoặc giải pháp nhận nguyên dòng, không mặc định một lần `Reader.read()` đủ một “ký tự hiển thị”.

## 9. Tương tác giữa Reader, Scanner, readLine và readPassword

**Mỗi tầng đọc có thể giữ dữ liệu trong buffer**. Giả sử bạn tạo `Scanner(console.reader())`, gọi `scanner.next()`, rồi `console.readLine()`; scanner có thể đã lấy thêm các ký tự/dấu xuống dòng mà đoạn readLine tiếp theo tưởng sẽ đọc. Tương tự, tự bọc `BufferedReader` nhiều lần quanh cùng nguồn có thể gây tình trạng khó đoán.

**Nguyên tắc thiết kế:** trong một luồng tương tác, chọn **một chủ sở hữu cơ chế đọc**. Nếu chỉ cần prompt/dòng/secret, ưu tiên `Console.readLine` và `Console.readPassword`; nếu cần token/grammar phức tạp, tổ chức parser từ một `Reader` và tránh phối hợp tùy tiện với các hàm đọc khác. Đặc biệt không đọc một phần UTF-8 từ `System.in` rồi kỳ vọng `Console.reader()` sẽ tiếp nối đúng trạng thái decoder.

Lưu ý `Console` đồng bộ hóa một số thao tác để bảo đảm tính nguyên tử của các tác vụ quan trọng trên console, nhưng các thread khác có thể **chờ** khi một thread đang nhập/xuất. Điều đó không biến việc thực hiện hai lời gọi riêng `writer.print` rồi `reader.read` thành một transaction không thể chen ngang; không cho nhiều thread hiện prompt đồng thời nếu không có bộ điều phối.

## 10. So với `Scanner(System.in)`, `BufferedReader` và đối số dòng lệnh

| Cách lấy input | Hợp với nhu cầu | Giới hạn liên quan bài này |
| --- | --- | --- |
| `console.readLine("Tên: ")` | Prompt + đọc một dòng người dùng nhập ở terminal có console | Cần `System.console() != null`; trả `null` khi EOF. |
| `console.readPassword("Mật khẩu: ")` | Nhập bí mật có **echo disabled** | Trả `char[]`, cần xóa mảng và quản lý secret; không có trên môi trường không cấp console. |
| `console.reader()` + parser/Scanner | Phân tích input ký tự phức tạp từ console | Quản lý buffer, EOF, exception và tránh đọc trộn cơ chế. |
| `console.writer()` | Xuất ký tự/định dạng trên console | Có thể cần flush; `PrintWriter` có cơ chế kiểm tra lỗi riêng. |
| `new Scanner(System.in)` | Đọc stdin dạng token/dòng, kể cả pipe/file | Không tự tắt echo. Không thay thế `readPassword()` cho secret. |
| `BufferedReader(new InputStreamReader(System.in, charset))` | Đọc stdin dòng thường từ chương trình tự động/file | Chọn charset theo contract, tự quản lý exception, không phụ thuộc console tương tác. |
| `args[]` / biến môi trường / secret provider | Cấu hình không tương tác | Không nên truyền mật khẩu qua command-line args vì có nguy cơ hiện trong process list/log; chọn cách quản lý secret phù hợp môi trường. |

### 10.1. Muốn chạy batch khi không có console?

Đối với **dữ liệu thường** (không nhạy cảm), có thể thiết kế hỗ trợ cả stdin pipe/file. Ví dụ:

~~~java
// Fragment: không tự đóng System.in nếu tài nguyên thuộc vòng đời JVM.
Console console = System.console();
String line;
if (console != null) {
    line = console.readLine("Nhập tên: ");
} else {
    java.io.BufferedReader reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(
            System.in, java.nio.charset.StandardCharsets.UTF_8));
    line = reader.readLine();
}
~~~

Đoạn trên nằm trong method khai báo/bắt `IOException`. Nhánh không có console **không in prompt ra stdout**, vì stdin có thể là dữ liệu tự động từ pipeline; charset UTF-8 là **giả định giao thức của ví dụ**, không phải khẳng định mọi stdin có encoding UTF-8.

Nếu yêu cầu là **mật khẩu**, không tự động đổi từ `readPassword()` sang `readLine()` hay scanner có echo rồi coi tương đương. Thiết kế một đường cấp secret phù hợp cho CI/container và cơ chế CLI cho terminal; không làm lộ secret qua stdout, shell history, log hay đối số dòng lệnh.

## 11. Chi tiết về EOF, lỗi I/O và định dạng

**EOF:** với `readLine` và `readPassword`, kết quả `null` có nghĩa không có dòng tiếp theo do đầu vào kết thúc; với `reader().read()` là `-1`. Dòng trắng chỉ Enter vẫn là dữ liệu hợp lệ về mặt đọc (`""` hoặc `char[0]`), không phải EOF. Terminal có thể phát EOF bằng tổ hợp phím tùy hệ thống, nhưng phím tắt không phải là contract Java ổn định.

**I/O exceptions:** `Reader.read()` khai báo checked `IOException`. Những phương thức `Console.readLine/readPassword` có thể ném `IOError` (một subclass của `Error`, không phải checked `IOException`) khi I/O thất bại; không thể chỉ dựa vào `catch(IOException)` cho mọi lỗi từ Console. Có thể thiết kế boundary của CLI để thoát/báo lỗi phù hợp mà không vô tình nuốt lỗi.

**Format errors:** `readLine(fmt,args...)`, `readPassword(fmt,args...)`, `printf/format` dùng cú pháp định dạng của Java. Dấu `%` không được escape, thiếu argument hoặc type không phù hợp có thể gây `IllegalFormatException`. Ví dụ prompt tỷ lệ phần trăm phải dùng `"Mức 50%%: "` chứ không dùng `"Mức 50%: "` làm format string tùy tiện.

**I/O buffering và visibility:** `PrintWriter` có các chế độ buffering/flush riêng. Trước khi chờ nhập bằng reader, hãy `out.flush()` hoặc `console.flush()` khi đã dùng `out.print(...)`. `Console.readLine(fmt,args...)` đã là API một bước prompt + read, giúp hạn chế các lỗi phối hợp giữa các lần gọi riêng.

**Threading:** Console có đồng bộ hóa các hoạt động quan trọng; một chương trình nhiều thread đọc đồng thời từ một Console dễ tạo trải nghiệm nhắc lệnh chồng chéo. Tách lớp CLI input thành một điểm xử lý duy nhất hoặc xếp hàng yêu cầu tương tác.

## 12. Cách kiểm thử hợp lý

**Không nên** coi `System.console() != null` là điều kiện bắt buộc trong mọi unit test. Test runner/JUnit/IDE thường không cung cấp console tương tác. Thay vào đó:

1. Tách logic phân tích/kiểm tra dữ liệu khỏi việc đọc `Console`. Ví dụ hàm `parseCommand(String input)` nhận chuỗi thường, test trực tiếp bằng JUnit.
2. Tạo boundary nhận input qua interface hoặc đối tượng truyền vào nếu cần kiểm thử quy trình hỏi đáp. Với bài demo nhỏ, đơn giản kiểm tra kết quả của `System.console() == null` là đủ.
3. Kiểm tra thực tế chế độ **no-echo** trong terminal thật với `readPassword()`; không mong CI tái hiện thao tác của terminal.
4. Với nhánh stdin batch, test riêng bằng file UTF-8 đã định nghĩa contract; không cố test secret qua pipeline có echo.
5. Không chụp/ghi nội dung mật khẩu vào snapshot, console log, test failure message hay report. Chỉ kiểm tra hành vi và cleanup mà không lộ dữ liệu nhạy cảm.

Các ví dụ tương tác ở trên không có stdout cố định khi người dùng thay đổi input, và phần hiển thị của terminal phụ thuộc môi trường. Nên đánh giá theo **hợp đồng API và tình huống** thay vì so khớp transcript với mật khẩu thực.

## 13. Lỗi phổ biến

1. **Gọi `System.console().readLine()` mà không kiểm tra null.** Có thể `NullPointerException` trong IDE/CI/redirect.
2. **Cho rằng `System.in` giống `Console.reader()`.** Một bên là byte standard stream, bên kia là reader của console, với đặc tính lifecycle/buffering khác.
3. **Dùng `readLine` để nhập mật khẩu.** Input bình thường có echo, tạo `String` khó chủ động xóa.
4. **Đổi `char[]` mật khẩu thành `String` chỉ để tiện xử lý.** Tăng thời gian và nơi lưu secret không kiểm soát được.
5. **Không xóa `char[]` khi xong.** Dùng `try/finally` và `Arrays.fill(...)` trên chính mảng đã nhận.
6. **Đồng nhất `null` với chuỗi/mảng rỗng.** EOF và dòng trống mang ý nghĩa khác nhau.
7. **Trộn `Scanner(console.reader())`, `Console.readLine()` và đọc trực tiếp `System.in`.** Buffering có thể làm mất/trôi input.
8. **Quên flush khi tự in prompt bằng `writer().print`.** Prompt có thể không hiển thị đúng lúc người dùng cần nhập.
9. **Bỏ qua `IllegalFormatException` khi prompt có `%`.** Format string phải hợp lệ hoặc dùng `%%`.
10. **Tin rằng `PrintWriter.println` ném checked IOException mỗi khi ghi thất bại.** Xem `checkError()` và hành vi của Writer.
11. **Đọc `reader().read()` một lần rồi gọi đó là một ký tự hiển thị.** Đơn vị là UTF-16 code unit, emoji ngoài BMP có thể cần hai `char`.
12. **Giả định Console charset luôn trùng default charset.** `Console.charset()` có thể khác `Charset.defaultCharset()`.
13. **Dùng readPassword như cơ chế bảo mật duy nhất.** No-echo giảm lộ trên màn hình nhưng không thay thế bảo vệ secret trong bộ nhớ và hệ thống.
14. **Cho rằng có Console ở mọi môi trường chạy Java 17/21.** Sự tồn tại phụ thuộc nền tảng và cách launch, không đơn giản là phiên bản JDK.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `System.in` hoạt động nhưng `System.console()` vẫn có thể `null`?
2. Khi nào chọn `console.reader()` thay cho `console.readLine()`?
3. `console.writer()` trả kiểu gì, và vì sao prompt viết bằng `print()` nên được flush?
4. Hai lần người dùng nhập chuỗi rỗng và phát EOF khác nhau về giá trị trả lại thế nào?
5. Vì sao `readPassword()` trả `char[]` mà không trả `String`? Phải làm gì sau khi dùng?
6. Có nên tạo fallback `new Scanner(System.in).nextLine()` để nhập secret khi Console không tồn tại không?
7. Nếu prompt có nội dung `"Hoàn thành 50%?"`, phải chú ý gì khi truyền nó vào overload format `readLine(fmt,args...)`?
8. Java 17 có `Console.charset()`, nó có nhất thiết bằng `Charset.defaultCharset()` không?
9. Vì sao trộn Scanner trên console.reader với console.readLine có thể làm khó dự đoán input?
10. Vì sao code trong `catch (IOException e)` không xử lý được mọi lỗi I/O mà `Console.readPassword()` báo ra?

**Gợi ý đáp án:** (1) stdin vẫn có thể được pipe, console thì không; (2) khi cần parser ký tự/token riêng thay vì chỉ một dòng; (3) `PrintWriter`, cần flush để prompt hiển thị; (4) `""`/`char[0]` khác `null`; (5) mảng có thể xóa bằng `Arrays.fill` trong finally; (6) không nên làm âm thầm vì có thể echo secret; (7) escape `%` thành `%%` hoặc đặt dữ liệu làm argument; (8) không; (9) tầng đọc có thể đệm thêm; (10) Console có thể ném `IOError` là `Error`, khác checked `IOException`.

## 15. Tài liệu chuẩn

- [Oracle Java SE 21 — Console](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Console.html): hợp đồng của `reader`, `writer`, `readLine`, `readPassword`, null/EOF, lỗi I/O, charset, synchronized I/O và bảo vệ mảng mật khẩu.
- [Oracle Java SE 21 — System.console()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#console()): điều kiện console có thể không tồn tại.
- [Oracle Java SE 21 — Reader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Reader.html): đọc ký tự, EOF `-1` và checked `IOException`.
- [Oracle Java SE 21 — PrintWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintWriter.html): `print/println/printf`, `flush` và `checkError`.
- [Oracle Java SE 21 — Arrays.fill](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): xóa nội dung một `char[]` khi hết nhu cầu.
- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): parser token từ Reader và những lưu ý về scanner/buffering.

**Ghi nhớ:** lấy Console bằng `System.console()` rồi **kiểm tra null**; `reader()`/`writer()` dành cho thao tác ký tự trực tiếp; `readLine()` trả `String` và thường echo; `readPassword()` trả `char[]` với echo tắt và cần xóa sau sử dụng. Khi không có console, thiết kế lối xử lý batch/secret riêng phù hợp thay vì tự nhận đầu vào mật khẩu như dòng text bình thường.