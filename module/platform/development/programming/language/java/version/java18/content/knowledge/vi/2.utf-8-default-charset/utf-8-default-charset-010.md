# `Console.charset()`, `System.console()` và trường hợp chương trình không gắn với console

## 1. Vì sao console có charset riêng?

Một chương trình Java có thể chạy trực tiếp trong terminal, từ IDE, trong container, dưới dạng service nền hoặc với đầu vào/đầu ra được chuyển hướng qua file và pipe. Những môi trường này không cung cấp cùng một thiết bị console, và encoding của luồng chuẩn cũng không nhất thiết giống default charset của JVM.

Từ JDK 18, theo **JEP 400**, UTF-8 là default charset thông thường cho các API Java SE phụ thuộc default charset. Tuy nhiên, **các luồng chuẩn `System.in`, `System.out` và `System.err` có charset riêng**. Chúng sử dụng các system property `stdin.encoding`, `stdout.encoding` và `stderr.encoding` tương ứng. Charset của console cũng được xác định theo môi trường console.

Java cung cấp hai API cần hiểu rõ:

- `System.console()` trả về đối tượng `Console` nếu JVM có console gắn với nó; nếu không có thì trả về `null`.
- `Console.charset()` trả về `Charset` được console sử dụng cho thao tác **ghi ra console**. Phương thức này có từ **JDK 17**, nên có sẵn trên Java 18 và các JDK hiện đại.

**Không được suy luận rằng console luôn dùng UTF-8 chỉ vì `Charset.defaultCharset()` trả về UTF-8.** Để đọc và ghi tương tác, hãy dùng API `Console` khi có console; nếu không có, chọn charset theo hợp đồng của nguồn hoặc đích dữ liệu.

## 2. `System.console()` trả về gì?

`System.console()` là phương thức tĩnh trả về đối tượng console duy nhất gắn với JVM hiện tại, nếu có. Phương thức đã có từ Java 6 và vẫn được hỗ trợ trên JDK hiện đại.

```java
import java.io.Console;

Console console = System.console();

if (console == null) {
    System.out.println("Không có console gắn với JVM");
} else {
    System.out.println("Console sẵn sàng");
}
```

Console thường tồn tại khi chương trình được chạy từ dòng lệnh tương tác và đầu vào/đầu ra chuẩn không bị chuyển hướng. Console thường không tồn tại trong các tình huống sau:

- JVM được khởi chạy từ một background job hoặc scheduler.
- `System.in` hoặc `System.out` được chuyển hướng sang file hay pipe.
- Ứng dụng chạy dưới môi trường IDE, test runner, service hoặc container không cấp terminal tương tác.
- Nền tảng hoặc cách khởi chạy không cung cấp thiết bị console cho JVM.

Đây là hành vi phụ thuộc môi trường và cách khởi chạy; không nên viết chương trình dựa trên giả định rằng một IDE hoặc một terminal cụ thể luôn có hoặc luôn không có console.

### 2.1. Không gọi phương thức trên đối tượng `null`

Đoạn mã sau có thể gây `NullPointerException`:

```java
Console console = System.console();
String line = console.readLine("Tên của bạn: ");
```

Nếu chương trình chạy từ IDE hoặc scheduler mà không có console, biến `console` là `null`. Hãy kiểm tra trước khi gọi các phương thức:

```java
Console console = System.console();

if (console != null) {
    String line = console.readLine("Tên của bạn: ");
    System.out.println("Xin chào " + line);
} else {
    System.err.println("Chương trình không có console tương tác.");
}
```

Nếu tính năng yêu cầu tương tác trực tiếp với người dùng, có thể dừng với thông báo rõ ràng khi console không tồn tại. Nếu chương trình được thiết kế để chạy cả trong pipeline hoặc service, hãy cung cấp một đường đọc/ghi phù hợp với luồng chuẩn hoặc giao thức của ứng dụng.

### 2.2. Không có console không đồng nghĩa không có standard streams

Ngay cả khi `System.console()` trả về `null`, các trường `System.in`, `System.out` và `System.err` vẫn là các luồng chuẩn của tiến trình. Chúng có thể được nối với bàn phím/màn hình, file, pipe hoặc một nguồn/đích do môi trường cung cấp.

Vì vậy, hai câu hỏi phải được tách riêng:

- **Có console tương tác không?** Kiểm tra `System.console()`.
- **Có thể đọc/ghi byte qua standard streams không?** Kiểm tra cách tiến trình được khởi chạy và hợp đồng của luồng đó.

Không có console chỉ có nghĩa API `Console` không khả dụng; không có nghĩa ứng dụng không thể nhận input hoặc ghi output.

## 3. `Console.charset()` trả về charset nào?

`Console.charset()` trả về đối tượng `Charset` được dùng cho **các thao tác ghi** của console. Phương thức này có từ **JDK 17**. Trên JDK 18+, có thể dùng nó để biết charset mà console sử dụng khi hiển thị văn bản.

```java
import java.io.Console;
import java.nio.charset.Charset;

Console console = System.console();

if (console != null) {
    Charset outputCharset = console.charset();
    System.out.println("Console output charset = "
            + outputCharset.name());
}
```

Charset này được xác định theo môi trường console và mặc định dựa trên `stdout.encoding`. Nó **có thể khác** `Charset.defaultCharset()`.

Ví dụ minh họa:

```text
Charset.defaultCharset() = UTF-8
Console.charset()        = windows-1258
```

Đây là tình huống có thể xảy ra khi JVM chọn UTF-8 làm default charset nhưng môi trường console dùng một encoding khác. Không nên ép kết luận rằng một trong hai giá trị là sai.

### 3.1. `Console.charset()` là charset ghi, không phải cam kết charset đọc

Một chi tiết quan trọng trong hợp đồng API hiện hành:

- Các thao tác **đọc** của `Console` sử dụng charset được chỉ định bởi `stdin.encoding`.
- Các thao tác **ghi** của `Console` sử dụng charset được chỉ định bởi `stdout.encoding`.
- `Console.charset()` trả về charset dùng cho thao tác **ghi**.

Hai charset đọc và ghi thường giống nhau trên terminal tương tác, nhưng không được mặc định rằng chúng luôn giống nhau. Vì vậy, không dùng `console.charset()` làm charset đầu vào trong mọi trường hợp.

Nếu cần dùng một `Reader` cho input console, hãy dùng `console.reader()`; API này được console tạo sẵn với quy tắc đọc tương ứng. Nếu chỉ cần đọc từng dòng, `console.readLine()` thường đơn giản và rõ ràng hơn.

## 4. Dùng `Console` cho chương trình tương tác

`Console` cung cấp các phương thức làm việc với thiết bị console theo dạng ký tự. Các phương thức thường dùng:

| API | Mục đích |
| --- | --- |
| `readLine()` | Đọc một dòng văn bản từ console |
| `readLine(format, args...)` | Hiển thị prompt theo format rồi đọc một dòng |
| `readPassword()` | Đọc mật khẩu với ký tự không được echo ra màn hình |
| `reader()` | Lấy `Reader` gắn với console |
| `writer()` | Lấy `PrintWriter` gắn với console |
| `printf(format, args...)` / `format(...)` | Ghi văn bản đã định dạng ra console |
| `charset()` | Lấy charset dùng cho thao tác ghi |

Ví dụ chương trình tương tác:

```java
import java.io.Console;

public class ConsoleGreeting {
    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            System.err.println(
                    "Hãy chạy chương trình trong terminal tương tác.");
            return;
        }

        String name = console.readLine("Tên của bạn: ");
        if (name == null) {
            System.err.println("Đầu vào đã kết thúc.");
            return;
        }

        console.printf("Xin chào, %s!%n", name);
        console.flush();
    }
}
```

`readLine()` trả về `null` khi gặp cuối luồng input. Vì vậy, ngay cả khi `console` khác `null`, chương trình vẫn cần xử lý trường hợp người dùng gửi EOF hoặc thiết bị đầu vào kết thúc.

### 4.1. Đọc mật khẩu mà không hiển thị ký tự

Khi cần nhận mật khẩu tương tác, dùng `readPassword()` thay vì `readLine()`. Phương thức này tắt echo trong lúc đọc và trả về `char[]`:

```java
import java.io.Console;
import java.util.Arrays;

Console console = System.console();

if (console == null) {
    throw new IllegalStateException(
            "Không thể đọc mật khẩu an toàn khi không có console.");
}

char[] password = console.readPassword("Mật khẩu: ");
if (password == null) {
    throw new IllegalStateException("Không nhận được mật khẩu.");
}

try {
    // Chuyển giao password tới API xác thực phù hợp.
    authenticate(password);
} finally {
    Arrays.fill(password, '\0');
}
```

Ví dụ giả định có phương thức `authenticate(char[])` của ứng dụng. Xóa nội dung mảng sau khi dùng giúp giảm thời gian dữ liệu nhạy cảm còn tồn tại trong bộ nhớ. Không chuyển mật khẩu thành `String` nếu không cần thiết vì `String` bất biến và không thể chủ động xóa nội dung của nó.

Nếu `System.console()` trả về `null`, không nên âm thầm thay `readPassword()` bằng `Scanner(System.in)` hoặc `BufferedReader` thông thường rồi tiếp tục nhận mật khẩu: cách đó thường echo dữ liệu nhập và không có bảo đảm tương đương. Hãy dùng cơ chế xác thực phù hợp với môi trường không tương tác, chẳng hạn secret được cấp qua kênh bảo mật của nền tảng triển khai.

## 5. Dùng `Console.reader()` và `Console.writer()`

Đối với ứng dụng cần thao tác theo luồng ký tự, `Console` cung cấp một `Reader` và một `PrintWriter` gắn với console.

```java
import java.io.Console;
import java.io.Reader;
import java.io.PrintWriter;

Console console = System.console();

if (console != null) {
    Reader reader = console.reader();
    PrintWriter writer = console.writer();

    writer.print("Nhập mã: ");
    writer.flush();

    char[] buffer = new char[128];
    int count = reader.read(buffer);

    if (count >= 0) {
        writer.println("Đã nhận " + count + " UTF-16 code unit.");
        writer.flush();
    }
}
```

`Console.reader()` được tạo cho việc đọc console và sử dụng encoding đầu vào theo `stdin.encoding`. `Console.writer()` ghi theo encoding đầu ra của console. Đóng `Reader` hoặc `PrintWriter` trả về từ các phương thức này không đóng luồng nền tảng của console.

Các thao tác đọc/ghi của `Console` được đồng bộ hóa. Trong chương trình nhiều luồng, các thao tác như `readLine()`, `readPassword()`, `format()`, `printf()` và thao tác trên reader/writer có thể block khi luồng khác đang tương tác với console. Hãy tổ chức việc đọc prompt tập trung, tránh nhiều thread cùng chờ input tương tác.

Với ứng dụng đơn giản chỉ cần đọc một dòng, ưu tiên `readLine()` để code ngắn gọn và thể hiện đúng mục đích.

## 6. JEP 400 không biến charset console thành UTF-8

JEP 400 chuẩn hóa **default charset** của các API phụ thuộc default charset từ JDK 18. Tuy nhiên, charset của các standard streams không lấy từ default charset này.

| Thành phần | Charset được sử dụng |
| --- | --- |
| `Charset.defaultCharset()` | UTF-8 trong cấu hình JDK 18+ thông thường |
| `System.in` | `stdin.encoding` |
| `System.out` | `stdout.encoding` |
| `System.err` | `stderr.encoding` |
| `Console` khi đọc | `stdin.encoding` |
| `Console` khi ghi | `stdout.encoding` |
| `Console.charset()` | Charset dùng cho thao tác ghi của console |

Các property standard stream được thiết lập theo nền tảng và môi trường người dùng; chúng có thể khác `file.encoding` và `native.encoding`. Điều này giải thích tại sao chuỗi Java đúng vẫn có thể hiển thị sai khi in ra terminal.

### 6.1. Kiểm tra charset khi có console

```java
import java.io.Console;
import java.nio.charset.Charset;

Console console = System.console();

System.out.println("default = "
        + Charset.defaultCharset().name());
System.out.println("stdin.encoding = "
        + System.getProperty("stdin.encoding"));
System.out.println("stdout.encoding = "
        + System.getProperty("stdout.encoding"));

if (console != null) {
    System.out.println("console output = "
            + console.charset().name());
}
```

Không giả định `console.charset()` luôn bằng `Charset.defaultCharset()`. Cũng không giả định `stdin.encoding` và `stdout.encoding` luôn giống nhau.

## 7. Khi `System.console()` trả về `null`

Đây là tình huống phổ biến khi chương trình chạy trong IDE, CI, container không cấp TTY, service nền hoặc khi standard streams được chuyển hướng. Lúc đó, ứng dụng phải xác định input/output dựa trên hợp đồng của nguồn và đích.

### 7.1. Đầu vào được quy định là UTF-8

Nếu chương trình nhận dữ liệu từ pipe hoặc file được đặc tả UTF-8, hãy tạo reader với charset tường minh:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader input = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

String line = input.readLine();
```

Ví dụ này phù hợp khi hợp đồng của standard input quy định UTF-8. Nó không tự đúng cho mọi terminal hoặc mọi pipeline; charset phải khớp với chương trình đã tạo dữ liệu đầu vào.

Không tạo nhiều reader độc lập cùng đọc `System.in`. Một reader có thể buffer byte vượt quá dòng hiện tại; việc đọc tiếp trực tiếp từ `System.in` hoặc tạo reader khác có thể làm dữ liệu bị tiêu thụ hoặc thứ tự đọc không xác định. Chọn một cách đọc duy nhất trong toàn bộ ứng dụng.

### 7.2. Đầu vào tương ứng với encoding của standard input

Nếu ứng dụng cần đọc dữ liệu theo encoding mà runtime gắn với `System.in`, tài liệu Java khuyến nghị dùng property `stdin.encoding`:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.Charset;

String inputEncoding = System.getProperty("stdin.encoding");
if (inputEncoding == null) {
    throw new IllegalStateException(
            "Không xác định được charset của standard input.");
}

Charset inputCharset = Charset.forName(inputEncoding);
BufferedReader input = new BufferedReader(
        new InputStreamReader(System.in, inputCharset));

String line = input.readLine();
```

Property này mô tả charset của standard input. Nếu nó không có, ứng dụng cần chọn charset theo hợp đồng đầu vào hoặc cấu hình triển khai; không tự suy ra từ `Console.charset()` vì console có thể không tồn tại và `charset()` là charset ghi.

### 7.3. Ghi output khi không có console

`System.out` và `System.err` vẫn là các `PrintStream` của tiến trình. Chúng dùng encoding riêng của standard output và standard error, tương ứng với `stdout.encoding` và `stderr.encoding`.

Nếu mục tiêu là ghi thông điệp thông thường ra standard output, có thể dùng `System.out.print/println`. Nếu chương trình tạo file hoặc payload cần byte UTF-8, hãy ghi bằng API file hoặc stream có charset tường minh thay vì giả định encoding của console:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Files.writeString(
        Path.of("report.txt"),
        "Báo cáo hoàn tất",
        StandardCharsets.UTF_8);
```

Không nên tạo `OutputStreamWriter(System.out)` không truyền charset với giả định nó sẽ tự dùng charset của console. `OutputStreamWriter` không nhận biết `Console`; constructor đó dùng default charset của JVM. Nếu cần tự bọc một luồng byte, hãy chỉ định charset phù hợp với hợp đồng của đích.

## 8. Các cách chạy và kết quả mong đợi

| Cách chạy | `System.console()` | Cách xử lý phù hợp |
| --- | --- | --- |
| Terminal tương tác, không chuyển hướng stdin/stdout | Thường khác `null` | Dùng `Console.readLine()`, `readPassword()` và `charset()` |
| IDE hoặc test runner | Có thể `null` | Dùng test input, cấu hình charset hoặc stream được cấp bởi môi trường |
| CI/background scheduler | Thường `null` | Đọc file, biến cấu hình hoặc pipe theo hợp đồng |
| `java App < input.txt` | `null` trong trường hợp stdin bị chuyển hướng | Đọc `System.in` bằng charset của file input |
| `java App > output.txt` | `null` trong trường hợp stdout bị chuyển hướng | Ghi standard output theo hợp đồng của tiến trình nhận file |
| Container có cấp pseudo-terminal (TTY) | Có thể khác `null` | Phụ thuộc cấu hình cấp TTY và cách chạy container |

Có thể kiểm tra trên terminal:

```bash
java ConsoleProbe
```

Chuyển hướng input/output để quan sát khác biệt:

```bash
java ConsoleProbe < input.txt
java ConsoleProbe > output.txt
```

Không dùng kết quả từ một môi trường để kết luận tất cả môi trường khác sẽ có cùng trạng thái console. Chính sách cấp TTY, shell, IDE và scheduler đều có thể ảnh hưởng.

## 9. Ví dụ chương trình chạy được cả khi có và không có console

Ví dụ sau chọn luồng tương tác nếu console tồn tại; nếu không có, nó đọc một dòng UTF-8 từ standard input theo hợp đồng đã xác định của ứng dụng:

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ConsoleOrPipe {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        String name;

        if (console != null) {
            name = console.readLine("Tên của bạn: ");
        } else {
            // Hợp đồng của ứng dụng quy định stdin không-console là UTF-8.
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            System.in, StandardCharsets.UTF_8));
            name = reader.readLine();
        }

        if (name == null) {
            System.err.println("Không có dữ liệu đầu vào.");
            return;
        }

        System.out.println("Xin chào, " + name);
    }
}
```

Trong nhánh console, `Console` tự sử dụng encoding của luồng console. Trong nhánh không console, ứng dụng chọn UTF-8 vì ví dụ quy định standard input của nó là UTF-8. Nếu môi trường pipeline dùng charset khác, hãy thay charset theo hợp đồng thực tế.

Ví dụ không dùng `console.charset()` để decode input vì phương thức đó trả charset cho thao tác ghi. Nếu cần dùng charset của standard input, hãy đọc `stdin.encoding` hoặc cấu hình cụ thể cho nguồn.

## 10. Các lỗi thường gặp

1. **Không kiểm tra `System.console()`:** gọi `readLine()` trên `null` gây `NullPointerException` trong IDE hoặc service.
2. **Cho rằng JEP 400 đổi charset console sang UTF-8:** JEP 400 không thay đổi charset của standard streams.
3. **Dùng `Console.charset()` để đọc input:** phương thức trả charset dùng cho thao tác ghi; input sử dụng `stdin.encoding`.
4. **Cho rằng không có console nghĩa là không có input/output:** standard streams vẫn có thể được kết nối với file, pipe hoặc nguồn khác.
5. **Dùng default charset khi bọc `System.in`:** `InputStreamReader(System.in)` dùng default charset, không nhất thiết là charset của standard input.
6. **Tạo nhiều reader trên `System.in`:** buffering có thể làm các reader tiêu thụ dữ liệu lẫn nhau.
7. **Dùng `readLine()` để nhập mật khẩu:** ký tự thường được echo ra màn hình; dùng `readPassword()` khi có console.
8. **Giả định IDE luôn cấp console:** trạng thái phụ thuộc cấu hình run/debug và cách IDE khởi chạy tiến trình.
9. **Dùng `Console.charset()` như API mới riêng của Java 18:** phương thức có từ JDK 17 và vẫn dùng được trên JDK 18+.

## 11. Bài tập tự kiểm tra

**Bài 1.** `System.console()` trả về `null` khi ứng dụng chạy trong một IDE. Điều đó có nghĩa `System.in` không thể đọc dữ liệu không?

*Đáp án:* Không. `System.console()` chỉ cho biết JVM không có đối tượng console. `System.in` vẫn có thể nhận dữ liệu từ IDE, file hoặc pipe; ứng dụng cần biết charset của nguồn.

**Bài 2.** `Console.charset()` trả về charset dùng cho thao tác nào?

*Đáp án:* Thao tác ghi ra console. Đọc từ console dùng charset `stdin.encoding`; ghi dùng `stdout.encoding`. Hai charset thường giống nhau nhưng không được giả định luôn giống.

**Bài 3.** JEP 400 có khiến `System.out` luôn dùng UTF-8 không?

*Đáp án:* Không. `System.out` sử dụng `stdout.encoding` theo môi trường. Default charset UTF-8 của JEP 400 không áp dụng để thay đổi charset của standard streams.

**Bài 4.** Khi chương trình chạy nền và `System.console()` là `null`, một file input được quy định UTF-8. Nên tạo reader như thế nào?

*Đáp án:* Bọc `System.in` bằng `InputStreamReader(System.in, StandardCharsets.UTF_8)` nếu byte đầu vào thật sự là nội dung file UTF-8 được chuyển qua stdin; hoặc dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` nếu đọc file trực tiếp.

**Bài 5.** Khi nhập mật khẩu trên terminal, vì sao nên dùng `Console.readPassword()` thay vì `Scanner(System.in)`?

*Đáp án:* `readPassword()` tắt echo ký tự khi nhập và trả về `char[]`. `Scanner` đọc input thông thường và không bảo đảm ẩn ký tự. Sau khi dùng mật khẩu, nên xóa mảng ký tự.

## 12. Ghi nhớ

`System.console()` cho biết JVM có thiết bị console tương tác hay không; kết quả có thể là `null` khi chạy trong IDE, service nền hoặc khi standard streams bị chuyển hướng. Không có console không đồng nghĩa standard streams không hoạt động.

`Console.charset()` có từ JDK 17 và trả charset dùng cho thao tác ghi của console. Thao tác đọc và ghi console lần lượt sử dụng `stdin.encoding` và `stdout.encoding`. Các charset này không nhất thiết giống `Charset.defaultCharset()`, kể cả khi JDK 18+ mặc định UTF-8 theo JEP 400.

Khi có console, dùng `Console` để đọc prompt, hiển thị nội dung và nhập mật khẩu. Khi không có console, xác định charset theo nguồn/đích dữ liệu và chỉ định rõ tại API I/O. Đây là cách xây dựng chương trình Java hoạt động ổn định trong terminal, IDE, CI, container và service nền.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 26 — Console](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html).
- [Oracle Java SE 26 — System.console() và standard streams](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html).
- [Oracle Java SE 26 — PrintStream.charset()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html).
- [Oracle Java SE 27 — Supported Encodings: Standard input, output and error streams](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 26 — Internationalization Guide: Default Charset](https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.pdf).
- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
