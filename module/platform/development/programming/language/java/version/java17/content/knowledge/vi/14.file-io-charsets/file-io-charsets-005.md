# Console.charset và mã hóa thực tế của console

## 1. Vì sao console có thể hiển thị sai tiếng Việt?

Một chương trình Java có thể in đúng nội dung Unicode trong bộ nhớ nhưng terminal lại hiển thị ký tự lỗi, dấu hỏi hoặc chuỗi như `Tiáº¿ng Viá»‡t`. Nguyên nhân thường nằm ở **mã hóa ký tự (charset) giữa các thành phần**, không nhất thiết do chuỗi Java đã bị hỏng.

Một đường đi đơn giản của dữ liệu xuất:

~~~text
Java String
    |
    | encode bằng một Charset
    v
Chuỗi byte
    |
    | System.out / Console.writer / pipe
    v
Terminal hoặc chương trình nhận
    |
    | decode bằng charset mà nó đang dùng
    v
Ký tự được hiển thị
~~~

Nếu phía Java mã hóa bằng UTF-8 nhưng terminal giải mã theo một code page khác, cùng một chuỗi byte sẽ bị diễn giải sai. Chiều nhập cũng có vấn đề tương tự: terminal gửi byte theo charset A, trong khi chương trình đọc và giải mã theo charset B.

Trong Java 17, API quan trọng cho console là **`Console.charset()`**. Phương thức này được bổ sung ở Java 17 để cho biết charset mà đối tượng `Console` sử dụng. Nó giúp phân biệt charset của console với charset mặc định của JVM.

Các khái niệm cần tách riêng:

- **`String`:** dữ liệu văn bản trong Java, được biểu diễn bằng các UTF-16 code unit.
- **`Charset`:** quy tắc chuyển giữa ký tự và byte, ví dụ UTF-8.
- **`Console.charset()`:** charset được dùng bởi một đối tượng `Console` nếu JVM có console.
- **`Charset.defaultCharset()`:** charset mặc định của JVM cho các API dùng charset mặc định.
- **Terminal/IDE/pipe/file:** nơi nhận hoặc cung cấp byte; mỗi nơi có thể có cấu hình encoding riêng.

Không có một charset duy nhất tự động đại diện cho mọi đường vào/ra của một tiến trình Java.

## 2. Java String không phải là chuỗi byte UTF-8

### 2.1. String lưu nội dung ký tự, không lưu encoding của terminal

Một `String` Java là chuỗi ký tự theo mô hình Unicode của Java. Ở mức API, các thao tác như `length()` và `charAt()` làm việc với UTF-16 code unit:

~~~java
String text = "Tiếng Việt";
System.out.println(text.length());
System.out.println(text.charAt(0));
~~~

Một `String` không ghi nhớ rằng nó đến từ UTF-8, Windows code page hay một charset khác. Charset chỉ cần thiết khi chuyển văn bản sang byte hoặc chuyển byte thành văn bản.

Ví dụ cùng một chuỗi có thể được mã hóa thành các dãy byte khác nhau:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String text = "Tiếng Việt";

byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
byte[] utf16 = text.getBytes(StandardCharsets.UTF_16);

System.out.println(Arrays.toString(utf8));
System.out.println(Arrays.toString(utf16));
~~~

Hai mảng byte khác nhau nhưng đều có thể giải mã về cùng nội dung nếu dùng đúng charset tương ứng.

### 2.2. Charset phải khớp ở cả hai đầu

~~~java
String original = "Xin chào";
byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

String decodedCorrectly =
        new String(bytes, StandardCharsets.UTF_8);
String decodedWrongly =
        new String(bytes, StandardCharsets.ISO_8859_1);
~~~

`decodedCorrectly` giữ nguyên nội dung. `decodedWrongly` có thể hiển thị thành chuỗi ký tự khác vì byte UTF-8 bị giải mã theo quy tắc ISO-8859-1.

Đây là nguyên lý cơ bản của lỗi mojibake: **byte được tạo theo charset này nhưng bị đọc theo charset khác**.

### 2.3. Unicode code point và UTF-16 code unit

Với chữ cái tiếng Việt thông thường, một ký tự thường tương ứng một UTF-16 code unit. Nhưng Unicode còn có ký tự ngoài Basic Multilingual Plane, ví dụ một số emoji, cần một cặp surrogate:

~~~java
String emoji = "😀";

System.out.println(emoji.length()); // 2 UTF-16 code unit
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
~~~

Điều này không phải lỗi charset. Nó là cách Java biểu diễn một số code point bằng UTF-16. Khi xử lý Unicode tổng quát, hãy phân biệt số code unit, số code point và số byte sau encoding.

## 3. Charset.defaultCharset() và Console.charset() khác nhau

### 3.1. Charset mặc định của JVM

`Charset.defaultCharset()` trả về charset mặc định được JVM sử dụng bởi những API không chỉ định charset tường minh:

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
~~~

Trên Java 17, **không nên giả định charset mặc định luôn là UTF-8 trên mọi hệ điều hành và mọi cấu hình**. JEP 400 chuẩn hóa UTF-8 làm charset mặc định từ JDK 18. Java 17 là phiên bản trước thay đổi đó; charset mặc định có thể phụ thuộc môi trường và cấu hình khởi chạy.

Khi viết code cần chạy trên Java 17 và các JDK mới hơn, hãy chỉ định charset rõ ràng cho file, giao thức và dữ liệu trao đổi. Đừng dựa vào default charset nếu định dạng dữ liệu yêu cầu UTF-8.

### 3.2. Charset của Console

Java 17 bổ sung `Console.charset()`:

~~~java
import java.io.Console;
import java.nio.charset.Charset;

Console console = System.console();
if (console != null) {
    Charset consoleCharset = console.charset();
    console.printf("Console charset: %s%n", consoleCharset.name());
} else {
    System.out.println("Không có console tương tác");
}
~~~

`Console.charset()` cho biết charset mà **Console instance** sử dụng. Charset đó có thể khác `Charset.defaultCharset()`. Vì thế:

- Không dùng `Charset.defaultCharset()` để kết luận chắc chắn terminal đang giải mã byte theo charset nào.
- Không dùng `Console.charset()` để kết luận mọi file hoặc pipe trong ứng dụng đều dùng charset đó.
- Nếu có Console, ưu tiên `Console.reader()`, `Console.writer()`, `readLine()`, `printf()` cho tương tác console vì các API này gắn với Console instance.
- Nếu không có Console, hãy quyết định encoding của luồng chuẩn theo hợp đồng của môi trường chạy.

### 3.3. Vì sao Console.charset() không thay thế defaultCharset()?

Hai API trả lời hai câu hỏi khác nhau:

| API | Câu hỏi được trả lời |
|---|---|
| `Charset.defaultCharset()` | Charset mặc định của JVM cho các API dựa trên default charset là gì? |
| `console.charset()` | Console instance hiện có sử dụng charset nào? |

Ví dụ, một ứng dụng có thể chạy trong môi trường mà console tương tác dùng charset do terminal cung cấp, còn file log được ghi theo UTF-8 tường minh. Không có lý do gì để buộc hai nơi đó phải dùng cùng một encoding.

## 4. System.console() có thể trả về null

### 4.1. Không phải tiến trình Java nào cũng có console

`System.console()` trả về đối tượng `Console` gắn với JVM nếu môi trường có console phù hợp. Nó có thể trả `null`, ví dụ:

- Chương trình chạy từ một số IDE mà standard input/output được chuyển hướng.
- Chương trình chạy như service hoặc background process.
- Standard input/output được nối với pipe hoặc file thay vì terminal tương tác.
- Môi trường thực thi không cung cấp console cho tiến trình.

Vì vậy, đoạn sau không an toàn:

~~~java
// Có thể ném NullPointerException nếu không có Console.
// Charset charset = System.console().charset();
~~~

Luôn kiểm tra null:

~~~java
Console console = System.console();

if (console == null) {
    // Không có console tương tác.
} else {
    System.out.println(console.charset());
}
~~~

Không nên viết logic ứng dụng phụ thuộc vào việc `System.console()` luôn khác null chỉ vì chạy được trên máy lập trình viên. Khi chạy trong CI, IDE, container hoặc môi trường service, kết quả có thể khác.

### 4.2. Console và standard streams là các khái niệm liên quan nhưng không đồng nhất

Java có ba standard streams:

- `System.in`: luồng byte đầu vào.
- `System.out`: luồng byte đầu ra thông thường, kiểu `PrintStream`.
- `System.err`: luồng byte đầu ra dành cho lỗi, kiểu `PrintStream`.

`Console` cung cấp API hướng tới tương tác với console, gồm reader, writer, đọc dòng, đọc password và format. Nếu standard streams bị chuyển hướng, JVM vẫn có `System.in/out/err`, nhưng có thể không có `Console`.

Đừng đồng nhất:

~~~text
System.out != Console.writer()
System.in  != Console.reader()
~~~

Chúng có thể hướng tới cùng thiết bị trong một phiên chạy, nhưng là những API và đường dữ liệu khác nhau. Charset của Console không phải bằng chứng về charset của mọi stream.

## 5. Dùng Console.charset() đúng cách trên Java 17

### 5.1. Đọc và ghi qua Console API

~~~java
import java.io.Console;
import java.nio.charset.Charset;

public class ConsoleCharsetDemo {
    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            System.err.println(
                    "Không có console tương tác; hãy chạy trong terminal phù hợp."
            );
            return;
        }

        Charset charset = console.charset();
        console.printf("Console charset: %s%n", charset.name());

        String name = console.readLine("Nhập tên: ");
        console.printf("Xin chào, %s!%n", name);
        console.flush();
    }
}
~~~

Ở đây:

1. Kiểm tra Console tồn tại trước khi sử dụng.
2. Lấy charset thực tế của Console bằng `charset()`.
3. Dùng `readLine` và `printf` để tương tác qua Console.
4. Gọi `flush()` khi cần bảo đảm nội dung đã được đẩy ra trước khi tiếp tục.

Nếu Console không tồn tại, ví dụ không thể dùng `console.charset()`; hãy chuyển sang một chính sách dành cho standard streams hoặc báo rằng ứng dụng cần chạy ở chế độ tương tác.

### 5.2. Dùng Console.reader() và Console.writer()

Console cung cấp:

- `reader()`: `Reader` để đọc văn bản từ console.
- `writer()`: `PrintWriter` để ghi văn bản ra console.
- `charset()`: charset được Console sử dụng.

~~~java
import java.io.Console;
import java.io.Reader;
import java.io.PrintWriter;

Console console = System.console();
if (console != null) {
    Reader reader = console.reader();
    PrintWriter writer = console.writer();

    writer.println("Nhập dữ liệu theo Console charset:");
    writer.flush();

    // Trong ứng dụng thực tế, có thể bọc reader bằng BufferedReader
    // để gọi readLine() khi cần.
}
~~~

Không cần tự tạo một `InputStreamReader(System.in, console.charset())` chỉ để thay thế Console API khi đã có Console reader. Dùng API của Console giảm nguy cơ vô tình đọc cùng một stream qua nhiều wrapper hoặc trộn các cơ chế buffering.

### 5.3. Đọc password

Console còn có `readPassword()` để đọc mật khẩu mà không echo nội dung ra màn hình:

~~~java
Console console = System.console();
if (console == null) {
    throw new IllegalStateException("Cần console tương tác");
}

char[] password = console.readPassword("Mật khẩu: ");
if (password != null) {
    try {
        // Xác thực password tại đây.
    } finally {
        java.util.Arrays.fill(password, '\0');
    }
}
~~~

`readPassword()` trả `char[]` để caller có thể xóa nội dung sau khi sử dụng. Đây là cách phù hợp hơn việc đọc password thành `String` nếu muốn giảm thời gian dữ liệu bí mật tồn tại trong bộ nhớ. Nó không thay thế quy trình xác thực hoặc lưu trữ mật khẩu an toàn.

## 6. Standard input/output khi không có Console

### 6.1. Chọn charset theo hợp đồng của stream

Nếu chương trình chạy qua pipe, file redirect hoặc trong môi trường không có Console, hãy xác định charset mà chương trình gọi và chương trình nhận đã thống nhất. Với giao thức do ứng dụng kiểm soát, UTF-8 thường là lựa chọn tốt:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8)
);

String line = reader.readLine();
~~~

Đoạn code nói rõ byte từ `System.in` phải được giải mã bằng UTF-8. Điều này đúng khi phía cung cấp input cũng gửi UTF-8. Nếu terminal hoặc chương trình pipe gửi byte theo charset khác, việc chỉ định UTF-8 không tự sửa được phía gửi.

### 6.2. Ghi UTF-8 tường minh ra standard output

~~~java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

Writer utf8Output = new BufferedWriter(
        new OutputStreamWriter(System.out, StandardCharsets.UTF_8)
);

utf8Output.write("Xin chào, Việt Nam!");
utf8Output.newLine();
utf8Output.flush();
~~~

Ở đây ứng dụng chủ động mã hóa thành UTF-8 trước khi ghi byte vào `System.out`. Phía đọc (terminal, pipe hoặc chương trình khác) cũng phải giải mã UTF-8.

Khi dùng wrapper tường minh như trên, hãy thống nhất một đường ghi cho nội dung đó và flush đúng lúc. Không nên trộn tùy tiện `System.out.println()` với một `Writer` có charset/buffer riêng, vì dữ liệu có thể bị xen kẽ hoặc xuất hiện không theo thứ tự mong muốn.

Không đóng `System.out` hoặc `System.in` khi chỉ đang bọc chúng trong ứng dụng; đóng wrapper thường cũng đóng stream nền. Thông thường chỉ cần flush và để tiến trình quản lý vòng đời standard streams.

### 6.3. Không có charset nào tự động phù hợp với mọi terminal

Nếu chương trình ghi UTF-8 nhưng terminal giải mã theo encoding khác, kết quả vẫn sai. Nếu chương trình ghi theo charset của console nhưng output đã được chuyển hướng sang file/pipe mà bên nhận mong đợi UTF-8, dữ liệu cũng có thể sai.

Hãy phân biệt hai tình huống:

| Tình huống | Cách chọn charset |
|---|---|
| Tương tác với Console thật | Dùng `Console.reader()/writer()`; truy vấn `Console.charset()` khi cần |
| Giao tiếp với pipe/file theo protocol do ứng dụng định nghĩa | Chỉ định charset của protocol, thường là UTF-8 |
| Đọc file có charset được ghi trong đặc tả | Dùng đúng charset của file, không suy từ console |
| Chạy trong IDE hoặc CI không có Console | Dùng standard streams với encoding được cấu hình/thoả thuận rõ |

## 7. Charset.defaultCharset() trên Java 17 và JDK mới hơn

### 7.1. Java 17 không nên được giả định là UTF-8 mặc định

JEP 400 chuẩn hóa UTF-8 làm default charset từ **JDK 18**. Vì bài học tập trung Java 17, cần hiểu ranh giới phiên bản:

- Trên Java 17, default charset thường phụ thuộc môi trường hệ điều hành/JVM và có thể khác giữa các máy.
- Từ JDK 18, UTF-8 trở thành default charset theo chính sách mới, với các trường hợp console vẫn cần được hiểu theo cơ chế riêng của console.
- `Console.charset()` vẫn là API cần dùng khi câu hỏi là charset của Console instance, không phải charset mặc định chung.

Không nên dựa vào hành vi mặc định của Java 17 để thiết kế một file hoặc protocol mà đặc tả yêu cầu UTF-8. Hãy chỉ định charset tường minh.

### 7.2. Tránh phụ thuộc vào default charset khi đọc/ghi file

Không nên:

~~~java
// Dễ phụ thuộc default charset của runtime:
// Files.readString(path);
// Files.writeString(path, text);
~~~

Nên:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Các overload chỉ rõ charset giúp file được đọc/ghi thống nhất giữa các máy và JDK.

### 7.3. Tránh biến đổi default charset chỉ để sửa một console

Đổi cấu hình default charset của toàn JVM để xử lý một terminal có thể ảnh hưởng những file, thư viện hoặc giao thức khác. Nếu vấn đề chỉ nằm ở console, hãy dùng Console API; nếu vấn đề nằm ở file hoặc pipe, hãy cấu hình charset đúng tại boundary tương ứng.

Không dùng một cấu hình global như giải pháp thay thế cho hợp đồng encoding rõ ràng của từng luồng dữ liệu.

## 8. Tách encoding của console, file và network

### 8.1. Console

Console là giao diện tương tác với người chạy chương trình. Khi `System.console()` tồn tại:

~~~java
Console console = System.console();
if (console != null) {
    console.printf("Charset: %s%n", console.charset());
    String input = console.readLine("Nhập: ");
}
~~~

Dùng Console API cho prompt, dòng nhập, password và format tương tác.

### 8.2. File

File text cần một encoding xác định trong hợp đồng:

~~~java
Files.writeString(
        Path.of("message.txt"),
        "Xin chào",
        StandardCharsets.UTF_8
);
~~~

Charset của file không nên phụ thuộc vào nơi chương trình được chạy. Một file được tạo từ terminal, IDE hay service vẫn cần đọc được theo cùng format.

### 8.3. Network và protocol

Protocol cần định nghĩa cách văn bản chuyển thành byte. Ví dụ HTTP thường sử dụng UTF-8 cho nhiều định dạng hiện đại, nhưng cần tuân theo charset được khai báo trong media type hoặc đặc tả cụ thể. Không dùng `Console.charset()` để mã hóa payload network.

~~~java
byte[] payload = jsonText.getBytes(StandardCharsets.UTF_8);
~~~

Nếu API yêu cầu charset khác, dùng charset đó theo hợp đồng. Encoding là một phần của giao thức, không phải cài đặt riêng của máy người dùng.

### 8.4. Process và pipe

Khi một chương trình Java gọi chương trình khác hoặc nhận output từ process, cần thống nhất encoding giữa hai tiến trình. `Process.getInputStream()` và `getOutputStream()` là byte streams; dùng `InputStreamReader`/`OutputStreamWriter` với charset được biết rõ.

~~~java
Process process = new ProcessBuilder("some-command").start();

BufferedReader childOutput = new BufferedReader(
        new InputStreamReader(
                process.getInputStream(),
                StandardCharsets.UTF_8
        )
);
~~~

Ví dụ này giả định chương trình con phát UTF-8. Nếu command có quy định encoding khác, hãy dùng đúng charset của command đó; không lấy charset của console Java để suy đoán.

## 9. Phát hiện và xử lý lỗi encoding

### 9.1. Nhận biết lỗi do charset không khớp

Các dấu hiệu thường gặp:

- Tiếng Việt trở thành chuỗi ký tự kiểu `Tiáº¿ng Viá»‡t`.
- Một số ký tự bị thay bằng `?` hoặc ký tự thay thế `�`.
- Emoji hoặc ký tự ngoài ASCII không hiển thị.
- Chương trình Java in đúng trong terminal này nhưng sai trong IDE hoặc khi redirect ra file.
- File đọc được trên máy tạo nhưng lỗi trên máy khác.

Không nên sửa bằng cách thay ký tự lỗi sau khi đã decode sai. Khi byte bị diễn giải theo charset không đúng, dữ liệu gốc có thể đã mất thông tin; cần sửa charset ở điểm encode/decode và đọc lại nguồn byte.

### 9.2. Decoder mặc định có thể thay thế dữ liệu lỗi

Nhiều API đọc văn bản có thể thay thế chuỗi byte không hợp lệ bằng ký tự thay thế tùy theo decoder. Nếu ứng dụng cần **từ chối byte sai**, hãy cấu hình decoder với `CodingErrorAction.REPORT`:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, decoder)
);
~~~

Khi byte đầu vào không hợp lệ với UTF-8, thao tác đọc có thể ném `MalformedInputException` (một loại `CharacterCodingException`) thay vì âm thầm thay thế. Cách này hữu ích cho protocol, dữ liệu nhập có yêu cầu chặt hoặc kiểm tra file.

### 9.3. CharsetEncoder cũng có thể báo lỗi khi mã hóa

Nếu charset đích không thể biểu diễn một ký tự nào đó, encoder có thể thay thế hoặc báo lỗi tùy cấu hình. Với định dạng bắt buộc không mất dữ liệu, có thể cấu hình:

~~~java
var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

UTF-8 có thể mã hóa mọi Unicode scalar value hợp lệ, nhưng chuỗi Java có thể chứa surrogate không hợp lệ. Nếu cần bảo vệ dữ liệu nghiêm ngặt, hãy cân nhắc cấu hình encoder để phát hiện trường hợp đó.

### 9.4. Đừng nhầm charset với font

Ngay cả khi byte đã được decode đúng thành ký tự Unicode, terminal vẫn cần font có glyph tương ứng. Nếu font không hỗ trợ ký tự, terminal có thể hiển thị ô vuông hoặc ký hiệu thay thế.

Phân biệt:

- **Encoding/decoding:** byte chuyển thành code point/ký tự.
- **Font/rendering:** ký tự được vẽ thành hình ảnh trên màn hình.

Nếu Java đã tạo đúng nội dung và terminal đã decode đúng nhưng ký tự vẫn không hiển thị, hãy kiểm tra font hoặc khả năng render của terminal. Đổi charset không thể bổ sung glyph bị thiếu.

## 10. Ví dụ hoàn chỉnh: console tương tác và fallback cho pipe

Lưu file **ConsoleEncodingDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.Console;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class ConsoleEncodingDemo {

    public static void main(String[] args) throws Exception {
        Console console = System.console();

        if (console != null) {
            // Console có charset riêng; dùng các API của Console.
            Charset charset = console.charset();
            console.printf("Console charset: %s%n", charset.name());

            String name = console.readLine("Nhập tên: ");
            console.printf("Xin chào, %s!%n", name);
            console.flush();
            return;
        }

        // Không có console: ví dụ chạy qua pipe/IDE/CI.
        // Contract của ví dụ này quy định stdin/stdout là UTF-8.
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in,
                        StandardCharsets.UTF_8
                )
        );
        PrintWriter writer = new PrintWriter(
                new java.io.OutputStreamWriter(
                        System.out,
                        StandardCharsets.UTF_8
                )
        );

        writer.println("Không có Console; fallback UTF-8 theo contract.");
        writer.flush();

        String name = reader.readLine();
        if (name == null) {
            writer.println("Không có dữ liệu đầu vào.");
        } else {
            writer.println("Xin chào, " + name + "!");
        }
        writer.flush();
    }
}
~~~

Biên dịch trên JDK 17:

~~~shell
javac --release 17 ConsoleEncodingDemo.java
java ConsoleEncodingDemo
~~~

Để kiểm tra nhánh không có Console, chạy chương trình trong môi trường mà standard streams được chuyển hướng, ví dụ qua pipe hoặc runner của IDE/CI. Nhánh fallback trong ví dụ **giả định contract UTF-8**; nếu phía cung cấp input hoặc nhận output không dùng UTF-8, phải thay cấu hình theo contract thực tế.

Ví dụ này minh họa cách chọn API theo loại môi trường. Nó không thể tự phát hiện mọi encoding của terminal hoặc chương trình pipe.

## 11. Chẩn đoán khi console hiển thị sai

Khi gặp lỗi, nên xác định chính xác byte sai ở boundary nào:

**Bước 1 — Xác nhận nội dung String.**  
In một số thông tin cơ bản hoặc kiểm tra code point trong chương trình để biết dữ liệu đã sai trước khi encode hay chưa.

**Bước 2 — Kiểm tra Console có tồn tại.**  
Gọi `System.console()`. Nếu null, không thể dùng `Console.charset()`; xác định chương trình đang chạy trong IDE, service, pipe hay file redirect.

**Bước 3 — Nếu có Console, đọc charset từ chính Console.**  
Gọi `console.charset()`, đồng thời dùng `console.reader()` và `console.writer()` cho tương tác.

**Bước 4 — Kiểm tra default charset riêng.**  
Gọi `Charset.defaultCharset()` để biết JVM default. Không kết luận rằng nó nhất thiết bằng console charset.

**Bước 5 — Kiểm tra bên nhận.**  
Terminal, IDE, file viewer hoặc process nhận phải giải mã byte theo charset mà phía Java đã dùng.

**Bước 6 — Kiểm tra font/rendering.**  
Nếu ký tự đã decode đúng nhưng không có glyph, đổi charset sẽ không giải quyết được.

**Bước 7 — Xác định contract cho từng luồng.**  
Console interactive có thể dùng Console API; file và network nên dùng charset tường minh; pipe phải thống nhất encoding giữa hai process.

## 12. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Java String được lưu bằng UTF-8.” | String là văn bản theo mô hình Unicode/UTF-16 của Java; UTF-8 là encoding khi chuyển sang byte. |
| “Charset.defaultCharset() luôn là charset của terminal.” | Default charset của JVM và Console charset là hai khái niệm khác nhau. |
| “Java 17 mặc định luôn là UTF-8.” | JEP 400 chuẩn hóa UTF-8 làm default từ JDK 18; Java 17 còn phụ thuộc môi trường/cấu hình. |
| “System.console() luôn khác null.” | Có thể null trong IDE, service, pipe, redirect hoặc môi trường không có console tương tác. |
| “Có thể gọi System.console().charset() trực tiếp.” | Phải kiểm tra Console null trước. |
| “Console.charset() là encoding của mọi file và network.” | Nó chỉ báo charset của Console instance. File/protocol cần charset theo contract riêng. |
| “System.out và Console.writer() chắc chắn là cùng một đối tượng.” | Đây là các API/đường output khác nhau; không đồng nhất charset hoặc buffering của chúng. |
| “Đổi default charset sẽ sửa mọi lỗi console.” | Lỗi có thể ở terminal, pipe, file hoặc font; cần sửa đúng boundary. |
| “Dữ liệu lỗi encoding có thể sửa bằng replace sau khi decode.” | Nếu decode sai, thông tin có thể đã mất; cần đọc lại byte bằng charset đúng. |
| “Ký tự ô vuông luôn là lỗi charset.” | Có thể font hoặc terminal không có glyph, dù decode đúng. |
| “UTF-8 tường minh bảo đảm terminal hiển thị đúng.” | Phía nhận cũng phải giải mã UTF-8 và có khả năng render ký tự. |
| “Mọi dữ liệu console phải dùng UTF-8.” | Console có charset riêng; dùng Console API hoặc theo contract thực tế. |

## 13. Bài tập thực hành

### Bài 1 — Quan sát charset

Viết chương trình in:

~~~java
System.out.println(Charset.defaultCharset());
System.out.println(System.console() == null);
~~~

Nếu Console tồn tại, in thêm `System.console().charset()`. Chạy trong terminal và IDE/runner khác nhau, ghi nhận kết quả. Giải thích vì sao không thể giả định ba môi trường có cùng cấu hình.

### Bài 2 — So sánh Console và standard output

Khi có Console, ghi ra:

~~~java
console.writer().println("Tiếng Việt: ă â ê ô ơ ư đ");
console.flush();
~~~

Sau đó so sánh với việc ghi qua một `OutputStreamWriter(System.out, StandardCharsets.UTF_8)`. Nêu rõ hai đường output có contract charset nào và terminal cần cấu hình gì để hiển thị đúng.

### Bài 3 — Kiểm tra byte UTF-8

Mã hóa chuỗi `"Xin chào Việt Nam"` bằng UTF-8, in mảng byte dưới dạng hex và giải mã lại bằng UTF-8. Sau đó giải mã cùng byte bằng một charset khác và giải thích mojibake.

### Bài 4 — Xử lý khi Console null

Viết chương trình:

- Nếu Console có sẵn, dùng `Console.reader()`/`Console.writer()`.
- Nếu không có, đọc/ghi standard streams bằng UTF-8 theo contract.
- Không đóng standard streams.
- Flush output đúng lúc.

Chạy qua một terminal tương tác và một pipeline/IDE runner, ghi nhận nhánh được thực hiện.

### Bài 5 — Từ chối byte UTF-8 sai

Tạo `CharsetDecoder` với `CodingErrorAction.REPORT`, đọc một byte sequence hợp lệ và một byte sequence không hợp lệ. Quan sát exception và giải thích khác biệt giữa REPORT và hành vi thay thế ký tự lỗi.

### Bài 6 — Phân biệt font với charset

Chọn một ký tự mà font terminal hiện tại không hỗ trợ. Kiểm tra code point trong Java, ghi byte UTF-8 và giải mã lại. Nếu nội dung vẫn đúng trong Java nhưng terminal hiển thị ô vuông, giải thích vì sao đây có thể là vấn đề font/rendering.

## 14. Câu hỏi tự kiểm tra

1. `Console.charset()` được bổ sung từ phiên bản Java nào?
2. Phương thức này trả lời câu hỏi gì?
3. Vì sao không thể thay `Charset.defaultCharset()` bằng `Console.charset()` trong mọi tình huống?
4. Khi nào `System.console()` có thể trả về null?
5. Khác nhau giữa `System.in/out/err` và `Console.reader()/writer()`?
6. Java String có lưu lại charset dùng để tạo ra nó không?
7. Vì sao byte UTF-8 bị decode bằng charset khác tạo ra mojibake?
8. JEP 400 thay đổi default charset từ JDK nào?
9. Tại sao file và network nên chỉ định charset tường minh?
10. Khi không có Console, làm sao chọn encoding cho standard streams?
11. Vì sao không nên đóng `System.in` hoặc `System.out` khi chỉ bọc chúng?
12. Khi nào dùng `CodingErrorAction.REPORT`?
13. Vì sao ký tự ô vuông có thể là lỗi font thay vì lỗi encoding?
14. `Console.charset()` có cho biết encoding của pipe hoặc file redirect không?

## 15. Tài liệu tham khảo

- [Java SE 17 API — Console](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): `charset()`, `reader()`, `writer()`, `readLine()`, `readPassword()`.
- [Java SE 17 API — System.console()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#console()): điều kiện JVM có thể cung cấp Console.
- [Java SE 17 API — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): default charset và cơ chế charset.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn, trong đó có UTF-8.
- [Java SE 17 API — InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): giải mã byte thành ký tự với charset/decoder được chỉ định.
- [Java SE 17 API — OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): mã hóa ký tự thành byte.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset được chuẩn hóa từ JDK 18 và mối liên hệ với môi trường console.
- [Java SE 17 API — CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html): cách xử lý dữ liệu không hợp lệ khi encode/decode.

Khi xử lý console trên Java 17, hãy truy vấn `Console.charset()` nếu JVM có Console và dùng các API reader/writer của chính Console cho tương tác. Khi làm việc với file, network hoặc pipe, chỉ định charset theo hợp đồng của dữ liệu. Tách rõ charset của JVM, charset của Console và encoding của thiết bị nhận sẽ giúp chẩn đoán đúng lỗi hiển thị thay vì thay đổi cấu hình toàn ứng dụng một cách thiếu kiểm soát.
