# Console.reader(), writer(), format() và flush() trong Java

## 1. Tổng quan: `Console` phục vụ giao tiếp với thiết bị terminal

`java.io.Console` là API Java SE hiện hành dành cho chương trình **giao tiếp bằng ký tự với console/terminal mà JVM đang kết nối**, khi một thiết bị console phù hợp tồn tại. Nó tiện cho công cụ dòng lệnh (CLI), wizard nhập cấu hình, chương trình cần prompt, và tình huống đọc mật khẩu mà không hiển thị ký tự đã gõ.

Bốn nhóm phương thức trọng tâm của bài:

- **`console.reader()`:** lấy `Reader` duy nhất gắn với đầu vào ký tự của console, dùng khi muốn tự phân tích dòng hoặc token.
- **`console.writer()`:** lấy `PrintWriter` duy nhất gắn với đầu ra ký tự của console, phù hợp khi cần `print`, `println`, `format` hoặc tự kiểm soát `flush()`.
- **`console.format(...)` / `console.printf(...)`:** in thông tin được định dạng ngay lên console, sử dụng format string theo quy tắc của `Formatter`.
- **`console.flush()`:** yêu cầu đẩy dữ liệu đầu ra đang đệm để hiển thị ngay, đặc biệt quan trọng với lời nhắc không có ký tự xuống dòng.

Các thao tác được tổ chức như sau:

~~~text
Terminal của hệ điều hành (có thể tồn tại hoặc không)
                   |
                   v
             System.console()
                   |
       +-----------+-------------+
       |                         |
       v                         v
 console.reader()           console.writer()
 Reader                     PrintWriter
       |                         |
 BufferedReader / Scanner        | print(), println(), format()
       |                         | flush()
 Đọc dòng/token                  |
       |                         v
       +--------> Console.format()/printf()
                   Console.flush()
~~~

**`Console` không phải là tên khác của `System.in` và `System.out`.** Các standard streams vẫn có thể tồn tại khi chương trình không có một thiết bị terminal tương tác; `System.console()` khi ấy có thể là `null`. Ngược lại, có console object không có nghĩa luôn có người dùng đang nhập dữ liệu: luồng đầu vào vẫn có thể tới EOF.

### 1.1. Lấy console một cách an toàn

~~~java
Console console = System.console();
if (console == null) {
    System.err.println("No console available.");
    return;
}
~~~

Đoạn trên là **snippet bên trong một phương thức** có thể `return`, với `import java.io.Console;`. Luôn kiểm tra `null` trước khi gọi bất kỳ method nào trên đối tượng `console`.

Theo tài liệu Java SE, console thường có khi JVM chạy trực tiếp trên terminal tương tác; có thể không có khi chạy trong IDE, job scheduler, service, hoặc khi standard input/output bị chuyển hướng. **Không viết mã dựa trên giả định rằng mọi hệ điều hành, terminal emulator hoặc môi trường CI đều trả cùng kết quả.** Chương trình cần biết xử lý tình huống không có console như thế nào: dừng có thông báo, dùng standard streams hoặc nhận tham số thay thế.

## 2. Bảng API và kiểu trả về

| API | Kiểu trả về | Vai trò |
| --- | --- | --- |
| `System.console()` | `Console` hoặc `null` | Lấy console liên kết với JVM, nếu tồn tại |
| `Console.reader()` | `Reader` | Đọc ký tự từ đầu vào của console |
| `Console.writer()` | `PrintWriter` | Ghi ký tự lên đầu ra của console |
| `Console.format(String, Object...)` | `Console` | In chuỗi có định dạng theo default format locale |
| `Console.printf(String, Object...)` | `Console` | Cách viết tiện ích tương đương `format(...)` |
| `Console.flush()` | `void` | Đẩy buffered output của console |
| `Console.readLine()` | `String` hoặc `null` | Đọc một dòng không bao gồm line terminator |
| `Console.readLine(String, Object...)` | `String` hoặc `null` | In prompt có định dạng, rồi đọc một dòng |
| `Console.readPassword(...)` | `char[]` hoặc `null` | Đọc dữ liệu nhạy cảm với echo bị vô hiệu hóa |
| `Console.charset()` | `Charset` | Charset dùng cho **ghi đầu ra** console (Java 17+) |

Ngoài ra, Java 22+ có `Console.isTerminal()`; Java 23+ có overload `Console.format(Locale, String, Object...)` và `printf(Locale, ...)`. **Không dùng những overload mới này trong chương trình khai báo tương thích Java 17**; phần thực hành sẽ sử dụng API đã có trên Java 17.

`Console` thực hiện giao diện `java.io.Flushable`. Các phương thức `reader()` và `writer()` trả **đối tượng gắn với console** chứ không phải mỗi lần gọi tạo một luồng độc lập mới.

## 3. `Console.reader()`: đọc ký tự thay vì chỉ đọc một dòng

### 3.1. `reader()` trả đối tượng gì?

~~~java
Reader reader = console.reader();
~~~

Đây là snippet trong phương thức đã có `Console console` không `null` và import `java.io.Reader`. Phương thức trả về **`Reader` duy nhất liên kết với console**. Bạn có thể gọi những API mức ký tự như `read()` hoặc `read(char[],off,len)`, hoặc bọc trong parser như `BufferedReader` / `Scanner` khi cần thao tác cấp cao.

Khác với việc đọc stream nhị phân, `Reader` làm việc với **ký tự Java (UTF-16 code units)**; việc giải mã byte từ terminal sang ký tự là trách nhiệm của cơ chế console. Người dùng có thể nhập ký tự Unicode, nhưng ứng dụng vẫn phải hiểu sự khác biệt giữa `char` (một code unit) và Unicode code point nếu đếm/giới hạn ký tự.

Tài liệu `Console.reader()` nêu: các **bulk-read** như `read(char[])`, `read(char[],off,len)`, `read(CharBuffer)` **không đọc vượt ranh giới một dòng trong cùng một lần gọi**, ngay cả khi bộ đệm còn chỗ. Ranh giới dòng có thể là LF, CR, CRLF hoặc EOF. Khi terminal chưa hoàn thành một dòng, lời gọi có thể **block**.

Điều này **không biến `Reader.read(...)` thành `readLine()`**. `read(...)` trả số lượng ký tự đã nhận, có thể ít hơn kích thước mảng yêu cầu; code cần xử lý kết quả thay vì giả định một lần đọc luôn đủ. Nếu mục tiêu chỉ là một câu trả lời theo dòng, `console.readLine(prompt)` đơn giản và ít rủi ro hơn.

### 3.2. Kết hợp `BufferedReader`

~~~java
Reader characters = console.reader();
BufferedReader lines = new BufferedReader(characters);
String answer = lines.readLine();
~~~

Đây là snippet với `console != null`, cần import `Reader` và `BufferedReader`. `BufferedReader.readLine()` trả một `String` không có dấu kết thúc dòng, hoặc `null` nếu stream đã tới EOF mà không còn dữ liệu.

Ưu điểm của cách bọc này là có `readLine()` và các thao tác buffering quen thuộc. Tuy nhiên nó tạo **bộ đệm đọc riêng** phía trên `Console.reader()`. Nếu sau đó cùng một chương trình tiếp tục đọc bằng `console.readLine()`, `Scanner(console.reader())` hoặc một wrapper khác, các buffer/parser có thể **đọc trước và giữ lại dữ liệu**, khiến lần đọc sau không nhận được ký tự mong đợi.

**Quy tắc thực hành:** Trong một phiên tương tác, hãy chọn **một chiến lược tiêu thụ đầu vào** nhất quán. Nếu đã dùng `BufferedReader` trên `console.reader()`, tiếp tục dùng wrapper ấy cho các dòng liên tiếp thay vì luân phiên không kiểm soát với `console.readLine()`.

### 3.3. Kết hợp `Scanner` để đọc token

~~~java
Scanner scanner = new Scanner(console.reader());
if (scanner.hasNextInt()) {
    int quantity = scanner.nextInt();
    // Xử lý quantity.
}
~~~

Đây là snippet trong ứng dụng đã có console, cần import `java.util.Scanner`; nó không phải chương trình độc lập. `Scanner` tiện khi muốn tách token, số nguyên, số thực theo locale, nhưng cần hiểu `hasNextInt()` cũng có thể block và `nextInt()` thường **không tự tiêu thụ hết phần cuối dòng** mà bạn muốn đọc sau đó.

Nếu cần cả token và text tự do trong cùng phiên, xác định chiến lược rõ ràng (`nextLine()`/`useLocale(...)` và quy tắc newline). Tránh tạo nhiều `Scanner` hoặc `BufferedReader` cùng tiêu thụ một `Console.reader()`.

**Không cần đóng `Reader` do console cung cấp ngay sau mỗi prompt**. Theo hợp đồng `Console` hiện hành, việc gọi `close()` trên Reader/PrintWriter trả về không đóng underlying stream của console; tuy nhiên đây là **tài nguyên được console quản lý**, và đóng một wrapper như `Scanner` có thể khiến chính wrapper đó không dùng tiếp được. Chỉ đóng/giải phóng wrapper khi bạn thật sự kết thúc trách nhiệm sở hữu của wrapper; không dùng `try-with-resources` để đóng một console reader dùng chung rồi lại cố dùng nó sau đó.

### 3.4. EOF, CRLF và giới hạn đầu vào

`Reader` báo EOF bằng `-1` (với `read()` hoặc bulk read khi không còn ký tự). `BufferedReader.readLine()` trả `null` khi EOF xảy ra trước khi đọc được dòng mới. Không dùng `line.isBlank()` hay `line.length()` ngay lập tức khi chưa kiểm tra `line != null`.

Khi nhập qua terminal, việc nhấn Enter thường tạo ranh giới dòng và có thể hiện ký tự đã gõ trên màn hình do terminal echo. Bản thân `readLine()` đã loại bỏ line terminator. Code đếm độ dài phải phân biệt: dòng rỗng `""` không giống EOF `null`.

Nếu ứng dụng nhận input không đáng tin cậy hoặc có giới hạn độ dài, hãy kiểm tra chuỗi sau đọc và có chính sách hạn chế đầu vào thích hợp. Đừng giả định terminal luôn gửi dữ liệu ngắn hoặc hợp lệ; `BufferedReader.readLine()` tự nó không đặt giới hạn kích thước dòng để bảo vệ ứng dụng.

## 4. `Console.writer()`: ghi bằng `PrintWriter`

### 4.1. Ghi prompt không có xuống dòng

~~~java
PrintWriter output = console.writer();
output.print("Name: ");
output.flush();
~~~

Đây là snippet với `console != null` và import `java.io.PrintWriter`. `Console.writer()` trả **`PrintWriter` duy nhất** gắn với console. Vì `print(...)` không tự thêm newline, việc gọi `flush()` tường minh là cách rõ ràng để đảm bảo prompt đã được đẩy ra trước khi yêu cầu người dùng nhập.

`PrintWriter` có những phương thức tiện dụng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `print(value)` | In giá trị nhưng không tự thêm newline |
| `println(value)` | In giá trị và kết thúc một dòng |
| `format(fmt,args)` | In văn bản định dạng |
| `format(locale,fmt,args)` | Định dạng theo locale được chỉ định |
| `printf(fmt,args)` | Alias tiện ích của `format(...)` |
| `flush()` | Đẩy dữ liệu ghi qua writer |
| `checkError()` | Kiểm tra trạng thái lỗi ghi sau khi flush nếu cần |

**`PrintWriter` có cơ chế báo lỗi khác `Writer` thường:** nhiều phương thức ghi của nó không truyền tiếp checked `IOException` cho caller; ứng dụng cần phát hiện lỗi I/O có thể kiểm tra `checkError()` và xây chính sách báo lỗi phù hợp. Không ngầm khẳng định `output.print(...)` sẽ ném `IOException` khi không ghi được.

### 4.2. Console writer không phải `System.out`

`System.out` là `PrintStream` gắn với standard output, còn `console.writer()` là `PrintWriter` gắn với console được JVM nhận diện. Trong các môi trường có redirect hoặc công cụ thay thế output, **hai đường đi không nhất thiết tương đương về sự tồn tại/đích đến/charset**.

Đặc biệt:

- `System.out` luôn là một trường output stream của `System` (trừ khi ứng dụng thay đổi cấu hình), nhưng `System.console()` có thể trả `null`.
- `console.writer()` hoạt động với **ký tự**, không phải API để ghi byte tùy ý hoặc giao thức nhị phân.
- `System.setOut(...)` thay standard output không nên được hiểu là tự đổi `Console.writer()` tương ứng.
- Nếu chương trình cần hỗ trợ pipeline, redirect và test automation, cân nhắc một abstraction dùng `Reader`/`Writer` hoặc `InputStream`/`PrintStream` được inject thay vì buộc mọi đường đi phải có `Console`.

### 4.3. `writer()` và `format()` dùng chung thiết bị console

Có thể phối hợp hai cách ghi:

~~~java
console.writer().print("Loading...");
console.writer().flush();

console.format(" done (%d items)%n", 5);
console.flush();
~~~

Đây là snippet minh họa trình tự, không phải chương trình độc lập. Mục tiêu là **đảm bảo prompt/trạng thái được đẩy ra đúng lúc**. Dù cùng console, bạn vẫn nên chọn thứ tự hợp lý để không để hai thread khác nhau chen lời nhắc vào kết quả.

Không tạo `new PrintWriter(System.out)` rồi coi đó là đối tượng trả từ `console.writer()`. Cả hai có cùng tên phương thức phổ biến, nhưng không có nghĩa chúng cùng quản lý một terminal hoặc chia sẻ cùng logic synchronization.

## 5. `Console.format(...)` và `printf(...)`: format string theo Java Formatter

### 5.1. Cú pháp căn bản

~~~java
console.format("User: %s%n", "Lan");
console.printf("Age: %d%n", 21);
console.format("Progress: %.1f%%%n", 87.5);
console.flush();
~~~

Đây là **snippet** trong ứng dụng với `console != null`. Ý nghĩa các ký hiệu:

| Ký hiệu | Công dụng | Ví dụ |
| --- | --- | --- |
| `%s` | Chuỗi/biểu diễn đối tượng | `"Lan"` |
| `%d` | Số nguyên dạng thập phân | `21` |
| `%f` | Số thực dấu phẩy động | `87.5` |
| `%.1f` | Số thực với một chữ số sau dấu thập phân | `87.5` |
| `%n` | Ký tự kết thúc dòng **phù hợp nền tảng** | LF hoặc CRLF |
| `%%` | In một dấu phần trăm `%` | `87.5%` |

Giả sử format locale dùng dấu chấm thập phân, các message được hình thành là:

~~~text
User: Lan
Age: 21
Progress: 87.5%
~~~

**Lưu ý locale:** `%f` có thể dùng dấu thập phân hoặc cách nhóm số khác nhau tùy **default format locale** của JVM. Không coi dấu `.` trong phần thập phân là bất biến nếu chưa chọn locale cụ thể.

`Console.format(String,Object...)` và `Console.printf(String,Object...)` **trả về chính đối tượng `Console`**, nên có thể gọi nối tiếp:

~~~java
console.format("Module: %s%n", "Java")
       .printf("Lessons: %d%n", 4)
       .flush();
~~~

Đây là snippet sử dụng API Java 17+. `flush()` trả `void`, vì vậy phải là lời gọi cuối nếu muốn chaining theo cách trên.

### 5.2. Cú pháp sai và `IllegalFormatException`

Java format string phải tương thích với arguments. Ví dụ:

~~~java
console.format("Value: %d%n", "not-an-integer");
~~~

Đây là **ví dụ lỗi có chủ ý**: `%d` không nhận `String` theo hợp đồng format và có thể gây `IllegalFormatConversionException`, một subclass của `IllegalFormatException`. Những lỗi khác có thể phát sinh khi thiếu argument hoặc format specifier không hợp lệ. Đừng đưa format string nhập trực tiếp từ người dùng vào `console.format(...)` khi chưa kiểm soát được cú pháp, số lượng và kiểu đối số.

Cách an toàn khi chỉ cần hiển thị dữ liệu người dùng là dùng **format string cố định**:

~~~java
console.format("Received: %s%n", userInput);
~~~

`%s` giúp dữ liệu người dùng là **argument**, không phải format specifier. Trong ứng dụng log/terminal thật, vẫn phải cân nhắc ký tự điều khiển, escape sequence và dữ liệu nhạy cảm do userInput có thể chứa.

### 5.3. Locale trong Java 17 và Java 23+

`Console.format(String,Object...)` dùng **default format locale**. Nếu muốn định dạng ổn định theo một locale riêng trên Java 17, dùng `PrintWriter.format(Locale,...)`:

~~~java
console.writer().format(Locale.US, "Price: %.2f%n", 1234.5);
console.flush();
~~~

Đây là snippet Java 17+ với import `java.util.Locale`. Không nên đoán mặc định toàn bộ terminal đều dùng dấu thập phân `.` hoặc locale US.

**Từ Java 23**, `Console` có thêm overload:

~~~java
console.format(Locale.US, "Price: %.2f%n", 1234.5);
~~~

Đoạn sau **chỉ dành cho Java 23+**, không được chép vào bài `--release 17`. Tương tự, `Console.printf(Locale,...)` là API từ Java 23. Với code cần hỗ trợ Java 17, hãy giữ cách dùng `console.writer().format(Locale,...); console.flush();` như ví dụ chính.

## 6. `flush()`: không phải newline, close hay đồng bộ đầu vào

### 6.1. Flush nghĩa là gì?

Khi ghi ký tự, dữ liệu có thể đi qua các lớp đệm trước khi được chuyển tới thiết bị hiển thị. `Console.flush()` được định nghĩa là **đẩy buffered output của console để được ghi ngay**. `PrintWriter.flush()` làm tương tự ở lớp writer. Đây là thao tác cho **đầu ra**, không phải một lệnh yêu cầu đọc xong dữ liệu đầu vào.

Hãy phân biệt:

| Hành động | Công dụng |
| --- | --- |
| `output.print("Name: ")` | Đưa ký tự vào quá trình ghi; không có newline |
| `output.println("Ready")` | Thêm line terminator |
| `output.flush()` | Yêu cầu đẩy output đang đệm ở `PrintWriter` |
| `console.flush()` | Yêu cầu console đẩy buffered output |
| `reader.read(...)` | Chờ nhận ký tự từ thiết bị |
| `console.readLine(...)` | Đọc dòng và có thể hiển thị prompt |
| `close()` trên wrapper | Kết thúc vòng đời wrapper; **không** thay logic flush cho phiên còn đang sử dụng |

**`flush()` không phải `fsync` của file trên ổ đĩa và không bảo đảm người dùng đã nhìn hoặc đọc được nội dung.** Nó đẩy dữ liệu ra theo khả năng của API/thiết bị. Không dùng flush như cơ chế xác nhận UI hoặc network delivery.

### 6.2. Vì sao prompt trước khi read cần flush?

Một lỗi dễ gặp:

~~~java
PrintWriter output = console.writer();
output.print("Your choice: ");
String answer = new BufferedReader(console.reader()).readLine();
~~~

Đây là snippet **thiếu `flush()`**, có nguy cơ người dùng đang phải nhập mà chưa nhìn thấy prompt. Cách tốt hơn:

~~~java
PrintWriter output = console.writer();
output.print("Your choice: ");
output.flush();
String answer = new BufferedReader(console.reader()).readLine();
~~~

Cả hai là snippet trong phương thức đã có console và cho phép `IOException`, không phải chương trình độc lập. Chúng minh họa **lý do flush đúng thời điểm**, chứ không khẳng định mọi JDK/terminal luôn giữ prompt trong buffer cho tới khi flush.

Khi dùng `Console.readLine("Your choice: ")`, API đã có cơ chế prompt và đọc trong một lời gọi, thuận tiện hơn cho input theo dòng. Khi dùng `reader()` để tự xây parser, **ứng dụng chủ động ghi/flush prompt**.

### 6.3. Có nên flush sau từng ký tự?

Thường **không**. Flush quá thường xuyên có thể tạo thêm công việc I/O và giảm hiệu năng. Với ứng dụng CLI, nên flush khi:

- In **prompt không có newline** và chuẩn bị chờ input.
- Cần hiển thị trạng thái tiến trình ngay lập tức.
- Muốn hoàn tất một nhóm thông báo trước khi chuyển sang thao tác blocking hoặc kết thúc phạm vi ghi.

Không nhất thiết flush sau mỗi `print` hoặc tự flush sau mỗi `format` nếu code/thiết bị đã đáp ứng yêu cầu hiển thị; nhưng khi cần bảo đảm ranh giới output rõ ràng, lời gọi tường minh giúp code dễ đọc và ít phụ thuộc auto-flush.

### 6.4. `flush()` và xử lý lỗi

`Console.flush()` có chữ ký `void flush()`, trong khi `PrintWriter` thường **ghi nhận lỗi I/O trong trạng thái nội bộ**. Nếu ứng dụng CLI cần kiểm tra lỗi xuất thông tin, có thể gọi:

~~~java
PrintWriter output = console.writer();
output.format("Saved: %s%n", filename);
output.flush();
if (output.checkError()) {
    // Báo trạng thái lỗi ghi hoặc quyết định dừng.
}
~~~

Đây là **snippet** cần biến `filename` và cách xử lý lỗi do ứng dụng định nghĩa. `checkError()` có ích khi hệ thống đích có thể bị đóng/gián đoạn; không biến nó thành giải pháp tự động phục hồi terminal.

## 7. Ví dụ đầy đủ Java 17+: `reader`, `writer`, `format` và `flush` trong một chương trình

Chương trình **`ConsoleIoDemo.java`** dùng trực tiếp tất cả bốn API của chủ đề. Nó:

1. Lấy console và xử lý nhánh không có console.
2. Lấy `PrintWriter` và `Reader` qua `console.writer()` / `console.reader()`.
3. Ghi `Name: ` không có newline rồi gọi `output.flush()`.
4. Đọc một dòng bằng `BufferedReader` bọc Reader của console.
5. Kiểm tra EOF trước khi dùng kết quả.
6. Ghi lời chào bằng `Console.format(...)`.
7. Ghi số lượng Unicode **code point** bằng `PrintWriter.format(Locale.US,...)`.
8. Gọi `Console.flush()` trước khi kết thúc.

**Lưu thành file `ConsoleIoDemo.java`, tên class public khớp tên file:**

~~~java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Reader;
import java.util.Locale;

public class ConsoleIoDemo {
    public static void main(String[] args) throws IOException {
        Console console = System.console();
        if (console == null) {
            System.out.println("No interactive console available.");
            return;
        }

        PrintWriter output = console.writer();
        Reader characters = console.reader();
        BufferedReader input = new BufferedReader(characters);

        output.print("Name: ");
        output.flush();

        String name = input.readLine();
        if (name == null) {
            console.format("End of input.%n");
            console.flush();
            return;
        }

        console.format("Hello, %s!%n", name);
        output.format(Locale.US,
                "Characters (code points): %d%n",
                name.codePointCount(0, name.length()));
        console.flush();
    }
}
~~~

Các import dùng toàn API Java SE hiện hành. Chương trình chủ ý không đóng `console.reader()`/`console.writer()` vì chúng thuộc console của JVM và chương trình kết thúc ngay sau thao tác. `BufferedReader` chỉ được dùng ở một nơi, tránh sự cạnh tranh buffer với `console.readLine()`.

### 7.1. Biên dịch và chạy từ terminal

Trong thư mục chứa source:

~~~sh
javac --release 17 ConsoleIoDemo.java
java ConsoleIoDemo
~~~

**Trường hợp terminal có thể đọc dữ liệu tương tác:** chương trình in prompt. Khi người dùng gõ `Lan` và nhấn Enter, một transcript thông thường là:

~~~text
Name: Lan
Hello, Lan!
Characters (code points): 3
~~~

Trong transcript đó, chữ `Lan` ở dòng prompt là **dữ liệu người dùng gõ/terminal echo**; Java chủ động ghi `Name: `, `Hello, Lan!` và dòng đếm ký tự. Chương trình không chủ động in lại text nhập ngay ở prompt.

Đã **biên dịch trên JDK 24 với `javac --release 17` và kiểm thử trong terminal tương tác**. Terminal nhận đúng `Lan`, hiện lời chào và in `Characters (code points): 3`.

**Vì sao dùng `codePointCount(...)` thay vì `name.length()`?** Java `String.length()` đếm số **UTF-16 code unit**, không nhất thiết bằng số ký tự Unicode code point nếu tên có ký tự bổ sung nằm ngoài Basic Multilingual Plane. Ví dụ chọn code-point count minh họa một cách hiểu rõ ràng hơn cho nhãn “Characters (code points)”. Cần biết rằng **code point vẫn không hoàn toàn bằng grapheme/user-perceived character**, như emoji tổ hợp hoặc ký tự có dấu dạng combining sequence.

### 7.2. Trường hợp không có console

Nếu `System.console() == null`, chương trình không dereference `null` và tạo đúng một dòng stdout:

~~~text
No interactive console available.
~~~

Đây là **kết quả của nhánh điều kiện**; khả năng vào nhánh tùy cách JVM được khởi chạy và môi trường. Chẳng hạn IDE/CI với input/output redirect có thể không tạo console. Không nên ép ví dụ phải nhận được console trong mọi chế độ chạy.

### 7.3. Trường hợp có console nhưng không có dòng mới (EOF)

Nếu có đối tượng Console nhưng input đạt EOF, `BufferedReader.readLine()` trả `null`. Chương trình lúc ấy ghi:

~~~text
Name: End of input.
~~~

Đây là một kết quả quan sát được khi chạy thử trên JDK 24 trong một phiên không cung cấp dòng nhập: **Console tồn tại, nhưng input đã hết**. Dấu `Name: ` đứng trước thông báo vì prompt không có newline; nhánh EOF không được hiểu là người dùng nhập chuỗi rỗng.

Không thể dựa riêng vào `System.console() != null` để khẳng định luôn có người dùng sẵn sàng nhập. Một hệ thống production cần phân biệt **không có console**, **có console nhưng EOF**, **dòng rỗng** và **dòng hợp lệ**.

### 7.4. Tại sao hai kiểu format cùng xuất hiện?

Chương trình dùng:

~~~java
console.format("Hello, %s!%n", name);
output.format(Locale.US,
        "Characters (code points): %d%n",
        name.codePointCount(0, name.length()));
~~~

Đây là **hai dòng code rút từ chương trình hoàn chỉnh**. `Console.format(...)` dùng default format locale; `PrintWriter.format(Locale.US,...)` chứng minh cách chỉ định locale mà vẫn chạy trên Java 17. Không cần sử dụng `Console.format(Locale,...)` (chỉ có từ Java 23) để đạt yêu cầu này.

## 8. Dòng xử lý nhập/xuất theo thứ tự và tính đồng bộ

Khi chương trình tương tác có nhiều thread, tài liệu `Console` nêu các thao tác đọc/ghi được **đồng bộ để các thao tác quan trọng hoàn thành nguyên tử**. Các hoạt động `readLine`, `readPassword`, `format`, `printf` và đọc/ghi trên đối tượng trả từ `reader()`/`writer()` có thể **chặn nhau**.

Không suy ra rằng toàn bộ chuỗi:

~~~text
print prompt -> flush -> read line -> validate -> print result
~~~

là một transaction không thể chen ngang bởi một thread khác. Từng operation được đồng bộ ở phạm vi mà API định nghĩa, nhưng chuỗi nhiều lời gọi vẫn cần **phối hợp ở cấp ứng dụng** nếu nhiều thread cùng truy cập console.

Các thiết kế thường dùng:

- Chỉ một thread sở hữu phiên tương tác; thread khác gửi thông điệp qua queue.
- Đưa logic input/output vào một vòng lặp đọc lệnh tập trung.
- Nếu có background progress log, bố trí kênh hiển thị riêng hoặc đồng bộ hóa để log không xuất hiện giữa prompt và input.
- Tránh hai `Scanner`/`BufferedReader` cạnh tranh cùng một `Console.reader()`; sự cạnh tranh này rất khó dự đoán.
- Khi có nhu cầu cancel/timeout input, không mặc định `readLine()` có tham số timeout. Cần kiến trúc phù hợp môi trường chạy; đừng kết thúc thread đọc một cách tùy tiện.

Với CLI đơn luồng, ví dụ ở mục 7 đủ rõ ràng và không cần thêm lock do ứng dụng tạo.

## 9. Charset, Unicode và locale: ba khái niệm khác nhau

### 9.1. Charset của console không nhất thiết là charset mặc định

`Console.charset()` (từ Java 17) trả `Charset` được dùng cho **write operations** của Console. Tài liệu hiện hành nêu input và output được điều khiển bởi các charset tương ứng với `stdin.encoding` và `stdout.encoding`; chúng thường giống nhau khi là terminal tương tác nhưng không bắt buộc bằng nhau.

Đừng giả định:

- `console.charset().equals(Charset.defaultCharset())` luôn đúng.
- Biết charset output đồng nghĩa tự động biết charset input.
- Terminal của mọi người dùng đều đang UTF-8 chỉ vì source code lưu UTF-8.

Nếu cần xem encoding của output:

~~~java
Charset outputCharset = console.charset();
console.format("Console output charset: %s%n", outputCharset);
console.flush();
~~~

Đây là snippet Java 17+ với import `java.nio.charset.Charset`. Chương trình chính không dùng charset để giải mã thủ công vì `Console.reader()` trả sẵn dữ liệu ký tự, tránh vô tình giải mã hai lần.

### 9.2. Locale chi phối cách format, không phải cách mã hóa byte

`Locale` ảnh hưởng đến quy tắc hiển thị số, phần thập phân và một số định dạng khác; `Charset` liên quan tới **mã hóa/giải mã văn bản**. Khi định dạng số để người dùng đọc, có thể dùng default locale. Khi tạo output dự kiến parse bằng máy, nên chọn định dạng và giao thức cố định, không chỉ dựa vào console prompt.

Ví dụ:

~~~java
console.writer().format(Locale.US, "ratio=%.2f%n", 12.5);
console.flush();
~~~

Trong Java 17, đoạn này cho ra dấu chấm thập phân `12.50`, nhưng vẫn dùng charset output do Console thiết lập. Format string không quyết định encoding.

### 9.3. `%n` khác `\n`

`%n` là định dạng newline theo hệ thống, phù hợp khi dùng `format`. `\n` trong chuỗi Java là ký tự line feed. Với CLI đa nền tảng, `%n` giúp thống nhất cách kết thúc dòng ở cấp formatting; không cần tự nối `System.lineSeparator()` ở tất cả các câu lệnh format.

## 10. Mật khẩu và dữ liệu nhạy cảm: không dùng `reader()` để che echo

`Console.reader()` được dùng cho input ký tự thông thường. Đối với **password, passphrase hoặc secret**, dùng `console.readPassword(...)` để không hiển thị ký tự khi gõ (khi thiết bị hỗ trợ) và nhận `char[]` thay vì `String`:

~~~java
char[] password = console.readPassword("Password: ");
if (password != null) {
    try {
        // Đưa password cho hàm xác thực do ứng dụng cung cấp.
    } finally {
        Arrays.fill(password, '\0');
    }
}
~~~

Đây là snippet trình bày cách xử lý vòng đời bí mật; cần import `java.util.Arrays`, biến `console != null` và **bổ sung logic xác thực do ứng dụng định nghĩa**. Không phải một chương trình xác thực độc lập.

Lý do:

- Mật khẩu đọc bằng `Reader`/`readLine` có thể bị terminal echo trực tiếp trên màn hình.
- `String` là immutable; ứng dụng không thể chủ động xóa nội dung chuỗi khỏi bộ nhớ.
- `char[]` cho phép dùng `Arrays.fill(...)` để giảm thời gian tồn tại của secret trong bộ nhớ sau khi xử lý.

Không log secret, không in nó qua `console.format("%s", password)`, và không giữ bản sao trong `String` vô thời hạn. `readPassword(...)` không biến một ứng dụng thành sandbox bảo mật, nhưng là API phù hợp để đọc bí mật trong console.

## 11. Khi nào nên dùng `readLine(...)` thay cho `reader()`?

| Nhu cầu | Nên dùng | Lý do |
| --- | --- | --- |
| Nhập một câu trả lời dạng dòng | `console.readLine("Prompt: ")` | Ít code, prompt + đọc một lần |
| Nhập password không echo | `console.readPassword("Prompt: ")` | Tránh echo, trả `char[]` |
| Tách nhiều token/số theo cú pháp tùy biến | `new Scanner(console.reader())` | Hỗ trợ token parser |
| Có logic parser phức tạp hoặc streaming | `console.reader()` qua `Reader`/`BufferedReader` | Kiểm soát cách đọc |
| Ghi prompt hoặc text thường | `console.writer().print/println(...)` | Có API writer và flush |
| Ghi text định dạng | `console.format(...)` hoặc `console.printf(...)` | Dùng Formatter trực tiếp |
| Chỉ định format locale trên Java 17 | `console.writer().format(Locale,...)` | Có mặt trong Java 17 |
| Đảm bảo prompt hiện trước đọc | `console.writer().flush()` | Gọi tại ranh giới chờ input |

**Không phải chương trình CLI nào cũng cần `Console.reader()`.** JavaDoc chính thức coi `reader()` hữu ích với ứng dụng nâng cao; chương trình chỉ hỏi một dòng nên ưu tiên `readLine(prompt)`. Học `reader()` vẫn quan trọng để biết cách kết nối Console với parser hoặc xử lý ký tự phức tạp.

## 12. Thiết kế CLI dễ kiểm thử và chạy được trong pipeline

Một chương trình chỉ truy cập `System.console()` trong mọi hàm có thể khó kiểm thử tự động, vì CI thường không có TTY. Nên tách:

1. **Lớp giao tiếp:** xác định console có tồn tại hay không, in prompt và đọc dòng.
2. **Lớp nghiệp vụ:** nhận `String` hoặc dữ liệu đã parse và trả kết quả độc lập với terminal.
3. **Lớp output:** định dạng câu trả lời; có thể nhận `PrintWriter` hoặc `Writer` do caller cung cấp.

Ví dụ, logic xử lý không phụ thuộc console:

~~~java
static String greeting(String name) {
    return "Hello, " + name + "!";
}
~~~

Đây là snippet trong một class. Có thể unit-test `greeting("Lan")` trả `Hello, Lan!` mà không cần terminal. Ở lớp CLI, gọi `console.format("%s%n", greeting(name))` và `console.flush()` để hiển thị.

Đối với lệnh dùng cả trong shell pipeline lẫn interactive mode, có thể chọn một adapter dựa trên standard streams khi `System.console()==null`. Tuy nhiên, **fallback phải được thiết kế có chủ đích**: khi stdin được redirect từ file, việc in prompt lên stdout có thể phá định dạng output mà script khác đang parse. CLI production nên quy ước rõ chế độ interactive và chế độ batch, đồng thời phân biệt stdout dành cho dữ liệu với stderr dành cho diagnostic.

Nếu cần chạy test tương tác thực sự, sử dụng PTY/terminal emulator tương thích hoặc harness hỗ trợ TTY. Test đó khác với unit test `StringReader/StringWriter`, vì terminal có echo, line discipline, charset và EOF behavior riêng.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Không kiểm tra `System.console() == null` | `NullPointerException` trong IDE/CI | Branch rõ ràng hoặc fallback có chủ đích |
| Chỉ in prompt bằng `writer().print` rồi chờ đọc | Prompt đôi khi chưa hiển thị | Gọi `flush()` trước thao tác blocking |
| Trộn `BufferedReader`, `Scanner` và `console.readLine` trên cùng reader | Mất token/đọc sai dòng vì buffer | Chọn một chiến lược đọc nhất quán |
| Quên xử lý EOF | `NullPointerException` khi gọi method trên kết quả `null` | Phân biệt `null`, `""`, input hợp lệ |
| Dùng `reader()` để đọc mật khẩu | Ký tự bị echo | `readPassword` và xóa `char[]` sau dùng |
| Nhầm `Console.writer()` với `System.out` | Redirect/test behavior không như ý | Phân biệt console device và stdout |
| Giả định `PrintWriter.print` ném checked `IOException` | Lỗi ghi khó được phát hiện | Kiểm tra `checkError()`/thiết kế diagnostic |
| Dùng format string lấy thẳng từ user | `IllegalFormatException` hoặc format injection về giao diện | Giữ format string cố định, user input là argument |
| Dùng `Console.format(Locale,...)` trong source Java 17 | Lỗi compile vì overload chỉ có Java 23+ | Trên Java 17 dùng `console.writer().format(Locale,...)` |
| Gọi `flush()` và tưởng đã đọc input | Chương trình vẫn block | Flush chỉ dành cho đầu ra |
| In quá nhiều từ nhiều thread | Prompt/log xen kẽ | Một owner CLI hoặc queue/synchronization |
| Giả định `Console.charset()` bằng `Charset.defaultCharset()` | Unicode/display sai ở một số máy | Đọc contract của console và cấu hình môi trường |
| Đếm số ký tự bằng `String.length()` rồi gọi là code point | Sai với Unicode bổ sung | Sử dụng `codePointCount(...)` theo mục tiêu |
| Đóng scanner/reader đang được chỗ khác dùng | Reader wrapper không còn dùng được | Định nghĩa ownership rõ ràng |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `System.console()` có thể trả `null` dù `System.in` và `System.out` vẫn tồn tại?

**Trả lời:** `Console` đại diện cho một thiết bị console phù hợp liên kết với JVM, trong khi standard streams là các stream có thể được redirect, thay thế hoặc gắn với môi trường không tương tác. Không phải mọi lần chạy đều có console.

**Câu 2.** Cần hỏi một tên và đợi người dùng nhập. Chọn `Console.readLine("Name: ")` hay `Console.reader()`?

**Trả lời:** Nếu chỉ đọc một dòng, `readLine(prompt)` thường đơn giản hơn. Nếu cần một parser riêng, có thể lấy `reader()` nhưng phải tự quản lý prompt, buffering và EOF.

**Câu 3.** `console.writer().print("Ready: ")` rồi ngay lập tức gọi `BufferedReader.readLine()` có rủi ro gì?

**Trả lời:** Prompt không có newline có thể còn trong buffer. Gọi `console.writer().flush()` hoặc `console.flush()` ở ranh giới trước khi chờ input.

**Câu 4.** `console.format("Total: %d%n", "nine")` hợp lệ không?

**Trả lời:** Không. `%d` cần giá trị số nguyên tương thích, không phải `String`; format sẽ lỗi kiểu `IllegalFormatConversionException`. Đổi argument hoặc specifier.

**Câu 5.** Trên Java 17, làm sao format số theo `Locale.US` khi viết ra console?

**Trả lời:** Dùng `console.writer().format(Locale.US, "...", args)` rồi `console.flush()`. Overload `Console.format(Locale,...)` chỉ có từ Java 23.

**Câu 6.** Nếu `console != null` nhưng `input.readLine() == null`, có nên coi đó là một tên rỗng?

**Trả lời:** Không. `null` biểu thị EOF, khác chuỗi rỗng `""` từ một dòng trống; phải xử lý nhánh kết thúc input.

**Câu 7.** `Console.flush()` có bảo đảm mọi người dùng nhìn thấy prompt hoặc hệ điều hành đã ghi nó xuống ổ đĩa?

**Trả lời:** Không. Nó flush buffered **output** của console, không phải cơ chế xác nhận người dùng đã nhìn và không phải `fsync` cho dữ liệu file.

**Câu 8.** Có nên dùng `console.reader().read(...)` để nhập mật khẩu rồi giữ trong `String`?

**Trả lời:** Không. Sử dụng `readPassword(...)` khi cần tắt terminal echo; xử lý `char[]` cẩn thận và xóa nội dung khi không còn dùng.

**Câu 9.** Có thể hai thread cùng dùng `console.reader()` mà đảm bảo từng thread nhận đúng một câu trả lời riêng biệt không?

**Trả lời:** Không nên giả định điều đó. Dù một số thao tác console được đồng bộ, nhiều thread cùng tiêu thụ input có thể cạnh tranh và làm sai ranh giới hội thoại. Nên có một owner đọc và phân phối kết quả.

**Ghi nhớ:** **`reader()` đọc ký tự, `writer()` ghi ký tự, `format()/printf()` định dạng output, `flush()` đẩy output đang đệm**. Đối với ứng dụng thực tế, kiểm tra `System.console()`, xử lý EOF, chọn một chiến lược đọc, flush trước khi chờ input và phân biệt Java 17 APIs với overload thêm ở Java 23. Đây đều là những API Java SE vẫn hiện hành.

### Tài liệu chính thức

- [Oracle Java SE 26 — java.io.Console](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): `reader`, `writer`, `format`, `printf`, `flush`, charset, terminal, EOF và tương tác đồng bộ.
- [Oracle Java SE 26 — java.io.Reader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Reader.html): hợp đồng đọc ký tự và EOF.
- [Oracle Java SE 26 — java.io.BufferedReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): đọc dòng và buffering.
- [Oracle Java SE 26 — java.io.PrintWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintWriter.html): print/format/flush/checkError.
- [Oracle Java SE 26 — java.util.Formatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Formatter.html): format-string syntax, locale và exception.
