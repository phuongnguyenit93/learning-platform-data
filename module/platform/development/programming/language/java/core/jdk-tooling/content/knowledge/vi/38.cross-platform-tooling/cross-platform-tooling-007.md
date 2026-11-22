# Encoding terminal trong Java

**Terminal encoding** là quy tắc chuyển đổi giữa ký tự và byte khi một chương trình đọc dữ liệu từ terminal hoặc ghi dữ liệu ra terminal. Với ứng dụng Java, lỗi encoding thường xuất hiện khi chương trình, shell, hệ điều hành, terminal emulator hoặc công cụ nhận log không thống nhất charset.

Ví dụ, Java tạo chuỗi `Xin chào` trong bộ nhớ. Khi ghi ra `System.out`, chuỗi được mã hóa thành byte. Terminal emulator nhận byte và giải mã để vẽ ký tự lên màn hình. Nếu Java mã hóa UTF-8 nhưng terminal giải mã theo một code page khác, người dùng có thể thấy `Xin chÃ o` hoặc ký tự thay thế. Ngược lại, nếu terminal gửi byte theo một encoding nhưng Java đọc bằng charset khác, dữ liệu nhập cũng bị sai.

Để xử lý đúng, cần tách bốn việc:

1. **Encoding của dữ liệu:** file, network protocol, pipe hoặc terminal dùng charset nào?
2. **Encoding của Java stream:** `System.in`, `System.out`, `System.err` đang đọc/ghi bằng charset nào?
3. **Encoding của môi trường:** shell, locale, Windows console code page, SSH hoặc container đang cấu hình ra sao?
4. **Khả năng hiển thị:** terminal font có glyph và cách render phù hợp không?

Không phải mọi lỗi chữ bị sai đều do Java. Charset có thể đúng nhưng font thiếu glyph; hoặc byte đúng nhưng shell chuyển đổi dữ liệu khi pipe/redirect.

## 1. Ký tự, Unicode, charset và byte

Các khái niệm sau có quan hệ với nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Character | Đơn vị văn bản theo ngữ cảnh ứng dụng | Chữ `A`, chữ `ế` |
| Unicode code point | Mã số đại diện cho một ký tự trong Unicode | `U+0041`, `U+1F600` |
| UTF-16 code unit | Đơn vị 16 bit dùng trong biểu diễn `String` của Java | Một `char` là một code unit |
| Charset | Quy tắc ánh xạ ký tự/code point sang byte và ngược lại | UTF-8, UTF-16LE, windows-1258 |
| Byte | Đơn vị dữ liệu thực sự được truyền qua stream hoặc lưu trong file | `C3 A0` |
| Terminal code page | Encoding mà console/terminal dùng cho dữ liệu nhập hoặc xuất | Windows code page 65001 |

Java `String` biểu diễn văn bản bằng UTF-16 code units. Điều này không có nghĩa mọi chuỗi Java được lưu dưới dạng UTF-8 hoặc mọi ký tự đều chiếm một `char`.

Ví dụ:

- Chữ `A` có code point `U+0041`, chiếm một UTF-16 code unit.
- Chữ `ế` có thể biểu diễn bằng một code point dựng sẵn hoặc bằng chuỗi code point gồm chữ `e` và dấu kết hợp.
- Emoji `😀` có code point `U+1F600`, được biểu diễn bằng hai UTF-16 code units (surrogate pair).

Vì vậy, `String.length()` trả về số UTF-16 code units, không phải số code point hoặc số glyph nhìn thấy. Nếu cần đếm code point:

```java
String value = "A😀";

System.out.println("utf16.units=" + value.length());
System.out.println("code.points=" +
        value.codePointCount(0, value.length()));
```

Stdout:

```text
utf16.units=3
code.points=2
```

Một ký tự người dùng nhìn thấy cũng có thể gồm nhiều code point, ví dụ chữ có dấu kết hợp hoặc emoji có modifier. Nếu xử lý con trỏ, độ rộng terminal hoặc cắt chuỗi theo ký tự hiển thị, cần khái niệm grapheme cluster; `codePointCount()` vẫn chưa đếm chính xác số ký tự hiển thị.

## 2. Luồng dữ liệu giữa Java và terminal

Một chương trình CLI có hai luồng dữ liệu chính:

**Input**

Bàn phím hoặc nguồn pipe tạo byte → terminal/OS hoặc shell chuyển byte → `System.in` nhận byte → Java decoder chuyển byte thành `String`.

**Output**

Java tạo `String` → encoder của `System.out` hoặc `System.err` chuyển thành byte → OS/shell/pipe chuyển byte → terminal emulator hoặc log collector giải mã byte → font vẽ glyph.

Mỗi bước có thể dùng cấu hình khác nhau. Ví dụ:

- File Java source được lưu UTF-8.
- Java compiler đọc source theo UTF-8.
- Java `String` giữ nội dung Unicode.
- `System.out` mã hóa theo `stdout.encoding`.
- Terminal emulator hiển thị theo UTF-8.
- Font terminal có hỗ trợ tiếng Việt.

Nếu một mắt xích không khớp, output có thể sai dù source code và `String` vẫn đúng.

Một pipeline cũng có thể thay đổi hành vi khi chuyển từ terminal tương tác sang redirect:

```sh
java TerminalEncodingDemo
java TerminalEncodingDemo > output.txt
java TerminalEncodingDemo | another-command
```

Lệnh đầu thường chạy với terminal tương tác. Hai lệnh sau chuyển stdout sang file hoặc pipe; runtime có thể chọn encoding khác và `System.console()` có thể trả về `null`. Vì vậy, hãy kiểm tra cả cách chạy tương tác và cách chạy trong CI/redirect.

## 3. Phân biệt default charset với terminal charset trong Java

Một nhầm lẫn phổ biến là nghĩ `Charset.defaultCharset()` luôn là encoding của terminal. Điều này không đúng.

Java có các charset mặc định khác nhau cho từng mục đích:

| API/stream | Charset được dùng |
|---|---|
| `Charset.defaultCharset()` | Default charset của Java runtime |
| `System.in` | `stdin.encoding` trên các JDK công bố thuộc tính này |
| `System.out` | `stdout.encoding` |
| `System.err` | `stderr.encoding` |
| `Console` output | `Console.charset()` |
| File I/O không chỉ định charset | Thường dùng default charset của API tương ứng |
| File I/O có charset rõ ràng | Charset được truyền vào API |

Từ JDK 18, theo JEP 400, default charset của các Java SE API là UTF-8 trên các hệ điều hành. Trước JDK 18, default charset thường phụ thuộc locale và môi trường. Trên Windows, ví dụ, nó có thể là code page như `windows-1258`, `windows-1252` hoặc một charset theo ngôn ngữ cài đặt.

Tuy nhiên, `System.in`, `System.out` và `System.err` có encoding riêng. Trong JDK 25, các thuộc tính `stdin.encoding`, `stdout.encoding` và `stderr.encoding` mô tả encoding của các standard stream; giá trị mặc định phụ thuộc platform và user environment. Chúng có thể khác `file.encoding` và `native.encoding`.

`Console.charset()` được bổ sung từ Java 17 và trả về charset dùng cho thao tác ghi của `Console`. Charset này có thể khác `Charset.defaultCharset()`.

**Quy tắc thực hành:** không dùng `Charset.defaultCharset()` để suy đoán encoding của terminal. Hãy kiểm tra đúng stream hoặc chỉ định encoding của giao thức input/output.

## 4. Khác biệt giữa JDK 17 và JDK 18+

JDK 18 đưa vào JEP 400 — UTF-8 by Default:

- JDK 17 trở xuống: default charset được xác định theo host environment và locale.
- JDK 18 trở lên: default charset của Java SE API là UTF-8, trừ khi runtime được khởi động với chế độ tương thích được hỗ trợ.
- `native.encoding` được giới thiệu trong JDK 17 để cho biết encoding từ môi trường host.
- `System.in`, `System.out`, `System.err` vẫn có charset riêng; không mặc định suy ra từ `file.encoding`.

Trên JDK 18+, `file.encoding=COMPAT` có thể yêu cầu hành vi default charset như các bản JDK trước. Đây là tùy chọn tương thích khi migration, không nên dùng làm cách sửa encoding chung cho ứng dụng mới.

Không nên gọi `System.setProperty("file.encoding", "UTF-8")` sau khi JVM đã khởi động để đổi charset. Default charset được xác định trong quá trình khởi tạo runtime; thay đổi property lúc chạy không phải cơ chế đáng tin cậy để thay đổi encoding của các stream đã tạo.

Nếu cần kiểm tra ứng dụng cũ, có thể thử chạy trên JDK cũ với `-Dfile.encoding=UTF-8` để phát hiện chỗ phụ thuộc vào default charset. Nhưng việc này không tự cấu hình terminal hoặc shell.

## 5. Kiểm tra charset thực tế của JVM và terminal

Trước khi sửa code, hãy thu thập thông tin runtime.

Các lệnh kiểm tra Java:

```sh
java --version
java -XshowSettings:properties -version
```

Trong output, chú ý các thuộc tính:

- `file.encoding`
- `native.encoding`
- `stdin.encoding`
- `stdout.encoding`
- `stderr.encoding`
- `user.language`
- `user.country`
- `user.timezone`

Một số property có thể không được công bố trên mọi phiên bản JDK. Đừng giả định thuộc tính vắng mặt đồng nghĩa với UTF-8.

Kiểm tra môi trường Linux/macOS:

```sh
locale
locale charmap
printf '%s\n' "$LANG" "$LC_ALL" "$LC_CTYPE"
```

`LC_ALL` có ưu tiên cao hơn các biến locale khác. `LC_CTYPE` ảnh hưởng đến cách phân loại và xử lý ký tự. `LANG` là locale mặc định khi các biến cụ thể không được đặt.

Kiểm tra Windows:

```powershell
chcp
[Console]::InputEncoding
[Console]::OutputEncoding
$PSVersionTable.PSVersion
```

`chcp` hiển thị active console code page. Windows console có code page cho input và output; hai hướng có thể được cấu hình riêng bằng API. PowerShell còn có encoding riêng cho cmdlet, file và giao tiếp với native executable.

Kiểm tra trong Java code bằng chương trình ở phần tiếp theo để biết runtime đang thực sự nhìn thấy gì.

## 6. Ví dụ Java 17+: chương trình chẩn đoán terminal encoding

Tạo file `TerminalEncodingDemo.java`:

```java
import java.io.Console;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class TerminalEncodingDemo {
    private static void printProperty(String name) {
        System.out.println(name + "="
                + System.getProperty(name, "<not exposed>"));
    }

    public static void main(String[] args) {
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("default.charset="
                + Charset.defaultCharset().name());

        printProperty("file.encoding");
        printProperty("native.encoding");
        printProperty("stdin.encoding");
        printProperty("stdout.encoding");
        printProperty("stderr.encoding");

        Console console = System.console();
        System.out.println("console.present=" + (console != null));
        if (console != null) {
            System.out.println("console.charset="
                    + console.charset().name());
        }

        String message = "Xin chào, Java!";
        System.out.println("message=" + message);
        System.out.println("message.utf8.hex="
                + HexFormat.of().formatHex(
                        message.getBytes(StandardCharsets.UTF_8)));
        System.out.println("message.utf16.units=" + message.length());
        System.out.println("message.codePoints="
                + message.codePointCount(0, message.length()));

        String supplementary = "A😀";
        System.out.println("emoji.utf16.units="
                + supplementary.length());
        System.out.println("emoji.codePoints="
                + supplementary.codePointCount(
                        0, supplementary.length()));
    }
}
```

Biên dịch và chạy:

```sh
javac TerminalEncodingDemo.java
java TerminalEncodingDemo
```

Ví dụ output khi chạy trên JDK 25 trong terminal Linux UTF-8:

```text
java.version=25.0.x
default.charset=UTF-8
file.encoding=UTF-8
native.encoding=UTF-8
stdin.encoding=UTF-8
stdout.encoding=UTF-8
stderr.encoding=UTF-8
console.present=true
console.charset=UTF-8
message=Xin chào, Java!
message.utf8.hex=58696e206368c3a06f2c204a61766121
message.utf16.units=15
message.codePoints=15
emoji.utf16.units=3
emoji.codePoints=2
```

Version cụ thể và các property encoding phụ thuộc JDK/OS/terminal. Nếu chạy từ IDE, CI hoặc redirect, `console.present` thường là `false`; khi đó không có `console.charset` để đọc. Output mẫu chỉ mô tả một môi trường UTF-8, không phải kết quả bắt buộc trên mọi máy.

Chuỗi hex của message giúp phân biệt lỗi mã hóa với lỗi hiển thị. Nếu byte UTF-8 đúng nhưng màn hình vẫn hiển thị sai, hãy kiểm tra cách terminal giải mã và font.

## 7. Đọc input tương tác và input từ pipe

Khi ứng dụng cần đọc từ bàn phím, ưu tiên `Console` nếu có:

```java
Console console = System.console();

if (console != null) {
    String line = console.readLine("Nhập tên: ");
    System.out.println("received=" + line);
} else {
    System.err.println("Không có interactive console.");
}
```

`System.console()` trả về `null` khi JVM không có console gắn với nó, ví dụ IDE, CI hoặc khi standard input/output được redirect. Không dùng `System.console()` như cách đọc dữ liệu duy nhất nếu ứng dụng cần hỗ trợ pipe.

Với pipe có hợp đồng UTF-8, chỉ định charset rõ ràng:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class Utf8PipeInput {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            System.out.println("received=" + line);
        }
    }
}
```

Chạy với input UTF-8:

```sh
printf 'Xin chào\n' | java Utf8PipeInput
```

Stdout khi pipe gửi UTF-8 và output được đọc như UTF-8:

```text
received=Xin chào
```

Ví dụ này định nghĩa giao thức pipe là UTF-8. Nếu chương trình nhận input từ một nguồn dùng encoding khác, hãy cấu hình charset đúng theo hợp đồng của nguồn đó. Không đổi charset của decoder để “thử cho đến khi nhìn đúng”, vì dữ liệu có thể bị giải mã sai mà không phát sinh exception.

Với JDK 25, tài liệu `System` khuyến nghị dùng `stdin.encoding` để chuyển byte của `System.in` thành ký tự khi cần theo encoding platform. Với pipe do ứng dụng kiểm soát, chỉ định UTF-8 trực tiếp thường rõ ràng và dễ kiểm thử hơn.

## 8. Ghi output cho terminal, pipe và file

Đối với output tương tác, `System.out` đã được JVM cấu hình theo `stdout.encoding`. Nếu chỉ in thông báo CLI, có thể dùng:

```java
System.out.println("Xin chào");
System.err.println("Có lỗi xảy ra");
```

Đối với dữ liệu file hoặc protocol, chỉ định encoding ngay tại điểm ghi:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);

String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
```

Không dựa vào default charset để đọc/ghi file có định dạng đã quy định UTF-8. Cùng một ứng dụng có thể chạy trên JDK 17 và JDK 25; chỉ định charset rõ ràng giúp giữ hành vi ổn định.

Nếu ứng dụng xuất dữ liệu để một chương trình khác đọc, hãy xem stdout như một protocol stream. Chọn encoding, delimiter, line ending và error handling rõ ràng. Tránh trộn thông báo chẩn đoán vào stdout nếu stdout đang chứa JSON, CSV hoặc dữ liệu máy đọc; gửi thông báo chẩn đoán sang stderr.

Không đóng `System.in`, `System.out` hoặc `System.err` khi ứng dụng vẫn cần dùng chúng. Khi bọc stream, chỉ flush khi cần; đóng wrapper có thể đóng luôn stream chuẩn.

## 9. Dùng Console và charset của standard streams

`Console` phù hợp với ứng dụng CLI tương tác:

- `System.console()` lấy console gắn với JVM nếu có.
- `Console.readLine()` đọc dòng từ console.
- `Console.readPassword()` đọc password mà không echo ký tự.
- `Console.writer()` ghi text qua console.
- `Console.charset()` trả charset dùng cho thao tác ghi của console, có từ Java 17.

`Console.charset()` không phải là charset của mọi file hoặc mọi pipe. Khi `System.console()` là `null`, không có đối tượng Console để truy vấn.

Trong JDK 25, các property sau mô tả standard stream:

| Property | Stream |
|---|---|
| `stdin.encoding` | `System.in` |
| `stdout.encoding` | `System.out` và console output |
| `stderr.encoding` | `System.err` |

Các property này mặc định theo platform/user environment. Tài liệu JDK 25 cho phép khởi động JVM với giá trị `UTF-8` cho các property tương ứng. Không đặt một giá trị tùy ý không được runtime hỗ trợ; cần bảo đảm terminal/pipe ở đầu kia cũng dùng UTF-8.

Ví dụ trên JDK có hỗ trợ các property này:

```sh
java -Dstdin.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 TerminalEncodingDemo
```

Lệnh này chỉ phù hợp khi nguồn input và nơi nhận output đều gửi/nhận UTF-8. Nếu terminal đang dùng code page khác, ép Java output UTF-8 có thể làm hiển thị sai hơn.

`file.encoding` điều khiển default charset của các API phụ thuộc default charset. Nó không phải công tắc chung để đổi terminal input/output. Không nhầm `file.encoding`, `native.encoding`, `stdin.encoding` và `stdout.encoding`.

## 10. Windows Command Prompt và console code page

Windows có nhiều lớp encoding: Unicode trong ứng dụng, console input code page, console output code page, ANSI code page, OEM code page và encoding của shell.

`chcp` hiển thị hoặc thay đổi active console code page:

```cmd
chcp
chcp 65001
chcp
```

Code page `65001` là UTF-8. Hãy chạy ứng dụng Java sau khi đã đổi code page để process mới nhận cấu hình mới. Windows console có code page cho input và output; API Windows cho phép truy vấn hoặc đặt riêng hai giá trị.

Một số điểm cần lưu ý:

- Terminal emulator hiện đại có thể dùng Unicode, nhưng tiến trình con vẫn chịu ảnh hưởng từ cách host cung cấp standard streams.
- `chcp 65001` không tự đổi charset của mọi file được tạo bởi PowerShell.
- Font terminal phải có glyph cần hiển thị.
- `cmd.exe`, Windows Terminal, PowerShell và IDE terminal có thể có hành vi khác nhau.
- Nếu Java output được redirect sang file, hãy kiểm tra byte của file thay vì chỉ nhìn màn hình.

Nếu gặp lỗi tiếng Việt trong Command Prompt, kiểm tra code page, `stdout.encoding`, `stderr.encoding`, font và JDK version. Đừng vội đổi encoding source file nếu source đã được compiler đọc đúng.

## 11. Windows PowerShell 5.1 và PowerShell 7+

PowerShell có encoding riêng cho file, cmdlet, pipeline và native command. Đây là lý do một lệnh Java in đúng trên màn hình nhưng file redirect lại có bytes khác mong đợi.

### Windows PowerShell 5.1

Windows PowerShell 5.1 có nhiều default encoding không đồng nhất giữa cmdlet. Tham số `-Encoding UTF8` thường tạo UTF-8 có BOM; `Default` dùng active ANSI code page; `Oem` dùng OEM code page. File script UTF-8 không BOM có ký tự non-ASCII có thể bị diễn giải theo code page cũ.

Khi cần lưu output UTF-8, chỉ định encoding rõ ràng:

```powershell
java TerminalEncodingDemo | Out-File -FilePath output.txt -Encoding utf8
Get-Content output.txt -Encoding utf8
```

### PowerShell 7+

PowerShell 6 trở lên mặc định dùng UTF-8 không BOM cho nhiều thao tác text output. PowerShell 7.1+ cung cấp các giá trị như `utf8`, `utf8NoBOM` và `utf8BOM`; `utf8` mặc định là không BOM.

Ví dụ:

```powershell
java TerminalEncodingDemo | Out-File -FilePath output.txt -Encoding utf8NoBOM
Get-Content output.txt -Encoding utf8
```

`$OutputEncoding` điều khiển encoding PowerShell dùng khi gửi text qua pipeline tới external/native program. Nó không điều khiển encoding mà `Out-File` hoặc file cmdlet sử dụng khi ghi file.

Không giả định `>` có cùng hành vi giữa Windows PowerShell 5.1 và PowerShell 7. Chỉ định `-Encoding` khi lưu text cần trao đổi giữa nhiều công cụ. Với dữ liệu nhị phân, tránh đi qua pipeline text; dùng file/byte stream phù hợp với phiên bản PowerShell.

## 12. Linux và macOS: locale và UTF-8

Trên Linux/macOS, locale thường quyết định encoding mặc định của nhiều công cụ dòng lệnh. Kiểm tra:

```sh
locale
locale charmap
locale -a
```

Các biến thường gặp:

- `LANG`: locale mặc định.
- `LC_CTYPE`: quy tắc phân loại ký tự và charset.
- `LC_ALL`: ghi đè các thiết lập locale khác.

Một môi trường UTF-8 có thể dùng:

```sh
export LANG=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
```

Hoặc dùng locale UTF-8 có sẵn trên hệ thống, ví dụ `C.UTF-8` nếu distribution hỗ trợ:

```sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
```

Không phải mọi image/container đều cài sẵn locale `en_US.UTF-8` hoặc `C.UTF-8`. Kiểm tra `locale -a` trước khi cấu hình. Nếu locale chưa được generate/cài đặt, chỉ đặt biến môi trường có thể khiến công cụ báo locale không hợp lệ hoặc fallback.

Tránh đặt `LC_ALL=C` khi ứng dụng cần đọc/ghi văn bản UTF-8. Locale C truyền thống thường dùng môi trường ASCII/POSIX; điều này có thể làm các tiện ích xử lý text hoạt động khác kỳ vọng.

macOS thường sử dụng UTF-8 trong terminal mặc định. Tuy vậy, ứng dụng vẫn nên chỉ định encoding rõ ràng cho file và protocol, không dựa vào locale của máy developer.

## 13. SSH, WSL, container và CI logs

Encoding có thể thay đổi khi ứng dụng chạy qua nhiều lớp môi trường.

### SSH

Terminal local và remote shell phải thống nhất cách trao đổi ký tự. SSH có thể chuyển tiếp các biến locale như `LANG` và `LC_*` nếu client/server cho phép. Kiểm tra `locale` trên máy remote, không chỉ trên máy local.

Nếu remote không nhận locale, kiểm tra cấu hình `SendEnv` phía client và `AcceptEnv` phía server. Không gửi biến môi trường chứa secret.

### WSL

WSL nối terminal Windows với môi trường Linux. Kiểm tra locale bên trong WSL bằng `locale` và kiểm tra terminal host có hỗ trợ font/glyph. Không mặc định code page của Windows Command Prompt quyết định locale Linux trong WSL.

### Docker/container

Container cần được cấu hình locale và terminal phù hợp. Ví dụ:

```sh
docker run --rm -it \
  -e LANG=C.UTF-8 \
  -e LC_ALL=C.UTF-8 \
  -e TZ=UTC \
  your-java-image
```

Image tối giản có thể không cài locale data. Xác minh charset bằng `locale charmap` trong container. Khi chạy container không có TTY, `System.console()` thường trả `null`; ứng dụng cần hỗ trợ pipe hoặc standard input đã redirect.

### CI logs

CI runner thường thu thập stdout/stderr thay vì hiển thị terminal tương tác. Hãy:

- Xác định encoding mà log collector mong đợi.
- Dùng UTF-8 cho log text nếu runner hỗ trợ.
- In version JDK và các encoding property trong bước diagnostic.
- Không giả định `System.console()` tồn tại.
- Không trộn output binary hoặc file archive vào log text.
- Kiểm tra cả log tải xuống và log hiển thị trong web UI.

## 14. BOM và encoding của file

UTF-8 có thể có hoặc không có Byte Order Mark (BOM). BOM là một chuỗi byte ở đầu file giúp một số công cụ nhận diện encoding.

Đối với file UTF-8 trao đổi giữa nhiều hệ điều hành, UTF-8 không BOM thường tương thích tốt với Unix tools và các công cụ hiện đại. Tuy nhiên, một số công cụ cũ có yêu cầu riêng.

Java không tự động nhận diện mọi charset chỉ từ nội dung file. Khi đọc file, truyền charset đúng:

```java
String text = Files.readString(
        Path.of("input.txt"),
        StandardCharsets.UTF_8);
```

Nếu file có BOM và API đọc trả BOM như ký tự đầu tiên, cần xử lý theo định dạng file. Không xóa ký tự đầu tiên một cách mù quáng vì dữ liệu có thể thực sự bắt đầu bằng ký tự đó.

Tránh lưu một file UTF-8 lúc có BOM, lúc không BOM tùy theo máy hoặc shell. Chọn một convention và kiểm tra bằng byte-level tool.

## 15. Charset conversion và lỗi mất dữ liệu

Khi chuyển đổi từ charset này sang charset khác, không phải mọi ký tự đều biểu diễn được ở đích.

Ví dụ, UTF-8 có thể biểu diễn đầy đủ Unicode. Một code page legacy có thể không biểu diễn được một số chữ tiếng Việt, emoji hoặc ký tự toán học.

Nhiều API decoder/encoder mặc định thay ký tự không hợp lệ hoặc không biểu diễn được bằng replacement character. Điều này có thể làm dữ liệu bị mất mà chương trình vẫn chạy.

Khi dữ liệu quan trọng, dùng `CodingErrorAction.REPORT` để phát hiện lỗi:

```java
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;

public class StrictEncodingDemo {
    public static void main(String[] args) throws Exception {
        Charset charset = Charset.forName("windows-1252");

        CharsetEncoder encoder = charset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        encoder.encode(CharBuffer.wrap("Xin chào"));
        System.out.println("ENCODABLE");
    }
}
```

Trên JDK có charset `windows-1252`, ví dụ này ném `UnmappableCharacterException` vì chữ `à` không thuộc repertoire của charset đó. Do exception xảy ra trước `println`, dòng `ENCODABLE` không được in.

Với dữ liệu tiếng Việt, UTF-8 thường là lựa chọn phù hợp cho file, database protocol, HTTP payload và pipe do ứng dụng kiểm soát. Nếu phải trao đổi với hệ thống cũ dùng code page cụ thể, hãy xác định charset từ hợp đồng tích hợp và kiểm thử các ký tự biên.

## 16. Chuẩn hóa Unicode khi so sánh chuỗi

Một số ký tự có thể có nhiều biểu diễn Unicode tương đương về mặt hiển thị. Ví dụ, chữ có dấu có thể được mã hóa bằng một code point dựng sẵn hoặc chữ cái cộng dấu kết hợp.

Hai chuỗi có thể trông giống nhau nhưng không bằng nhau khi so sánh byte hoặc `String.equals()`.

Nếu nghiệp vụ yêu cầu so sánh theo dạng chuẩn hóa, có thể dùng Unicode normalization:

```java
import java.text.Normalizer;

String first = "é";
String second = "e\u0301";

String normalizedFirst =
        Normalizer.normalize(first, Normalizer.Form.NFC);
String normalizedSecond =
        Normalizer.normalize(second, Normalizer.Form.NFC);

System.out.println(normalizedFirst.equals(normalizedSecond));
```

Stdout:

```text
true
```

Chỉ chuẩn hóa khi hợp đồng dữ liệu yêu cầu. Không tự ý normalize nội dung nhị phân, chữ ký số hoặc dữ liệu mà byte identity có ý nghĩa.

## 17. Cấu hình encoding trong Gradle và Maven

Terminal encoding là một phần của I/O runtime; source/resource encoding là một phần khác của build. Cần cấu hình cả hai.

### Gradle Kotlin DSL

```kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.withType<ProcessResources>().configureEach {
    filteringCharset = "UTF-8"
}
```

`options.encoding` chỉ định charset cho Java source compiler. `filteringCharset` dùng khi task process resources thực hiện filtering. Nếu không filter resource, vẫn nên quy định encoding rõ cho công cụ hoặc task thực sự đọc text.

### Maven

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

Đặt encoding trong build giúp compiler và plugin xử lý source/resource nhất quán. Nó không tự cấu hình code page của terminal chạy Maven.

Nếu build log tiếng Việt bị lỗi nhưng artifact source/resource đúng, kiểm tra Maven/Gradle process output encoding và log collector riêng. Không thay đổi encoding của source chỉ để sửa một terminal log.

## 18. Logging và command-line output

Logging framework có encoder riêng cho console appender và file appender. Cần kiểm tra cấu hình của từng appender:

- Console appender: charset phải phù hợp với `stdout.encoding`/terminal.
- File appender: chọn UTF-8 hoặc encoding theo hệ thống thu nhận log.
- JSON log: dùng UTF-8 theo hợp đồng của hệ thống ingest.
- Error output: kiểm tra `stderr.encoding` riêng.
- Log aggregation: xác minh collector không giải mã byte bằng code page khác.

Không nên dùng một cấu hình console charset để áp dụng cho file appender nếu hai đích có hợp đồng encoding khác nhau.

Với CLI, nên giữ stdout cho kết quả mà chương trình khác có thể parse và stderr cho warning/error. Nếu command được pipe sang chương trình khác, output cần có format và encoding ổn định, không phụ thuộc terminal font hoặc locale.

## 19. Chẩn đoán bằng byte thay vì chỉ nhìn màn hình

Khi chữ hiển thị sai, hãy kiểm tra byte gốc.

Linux/macOS:

```sh
printf 'Xin chào\n' > sample.txt
xxd -g 1 sample.txt
file -bi sample.txt
```

Nếu `xxd` cho byte UTF-8 của `à` là `c3 a0`, dữ liệu file đã được encode UTF-8. Nếu terminal hiển thị sai, lỗi có thể nằm ở bước decode/render.

Windows PowerShell:

```powershell
[System.IO.File]::WriteAllText(
    "sample.txt",
    "Xin chào",
    [System.Text.UTF8Encoding]::new($false)
)
Format-Hex -Path sample.txt
```

`Format-Hex` hiển thị byte của file; nó giúp phân biệt lỗi lưu file với lỗi hiển thị text.

Với output Java, redirect sang file rồi kiểm tra byte. Nhưng cần nhớ shell có thể tham gia chuyển đổi khi redirect. Nếu cần kiểm tra raw bytes, dùng công cụ redirect phù hợp với shell/phiên bản và kiểm tra byte bằng `xxd`, `od` hoặc `Format-Hex`.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tiếng Việt hiển thị thành `Ã` hoặc ký tự lạ | UTF-8 bị giải mã bằng code page khác | So sánh charset Java output với terminal code page |
| Chữ hiện thành dấu hỏi `?` | Charset đích không biểu diễn được ký tự | Dùng UTF-8 hoặc charset theo hợp đồng; bật strict encoder khi cần |
| Ký tự thành hình vuông | Font thiếu glyph hoặc terminal không render được | Kiểm tra font/glyph sau khi xác nhận byte đúng |
| `System.out` sai dù `defaultCharset()` là UTF-8 | `stdout.encoding` khác default charset | Kiểm tra stream encoding và console charset |
| `Scanner` đọc sai tiếng Việt | Scanner dùng charset khác input source | Truyền charset rõ ràng cho Scanner hoặc dùng Console |
| Chạy trong IDE bị `System.console() == null` | IDE không gắn terminal trực tiếp vào JVM | Hỗ trợ stdin pipe hoặc chạy trong terminal thật |
| Chạy CI khác local | CI redirect stream và dùng environment khác | Kiểm tra stdin/stdout encoding, locale và log collector |
| Java 17 lỗi nhưng Java 25 đúng | Default charset thay đổi từ JDK 18 | Chỉ định charset rõ ràng; kiểm thử JDK 17 compatibility |
| File UTF-8 có ký tự lạ đầu tiên | BOM bị coi là nội dung | Kiểm tra BOM và xử lý theo file format |
| PowerShell redirect ra file bị khác encoding | PowerShell 5.1/7 có default khác nhau | Chỉ định `Out-File -Encoding` hoặc API .NET có encoding rõ |
| Input qua PowerShell pipe bị sai | `$OutputEncoding` không khớp native program | Cấu hình pipeline encoding theo hợp đồng |
| Linux báo locale không hợp lệ | Locale chưa được cài/generate trong image | Kiểm tra `locale -a` và cài locale phù hợp |
| SSH remote bị lỗi chữ | Locale không được forward hoặc remote locale khác | Kiểm tra `LANG`, `LC_*`, SSH SendEnv/AcceptEnv |
| Chữ có dấu bị so sánh khác nhau | Unicode normalization khác nhau | Chuẩn hóa NFC/NFD khi nghiệp vụ yêu cầu |
| Dữ liệu bị mất nhưng không có exception | Decoder/encoder thay ký tự lỗi bằng replacement | Dùng `CodingErrorAction.REPORT` và kiểm tra charset |

## 21. Quy trình xử lý lỗi terminal encoding

Khi người dùng báo CLI hiển thị sai tiếng Việt:

1. Xác nhận lỗi xảy ra ở input, output, file, pipe hay log.
2. Chạy `java --version` và in các charset property.
3. Kiểm tra `System.console()` có tồn tại không.
4. Nếu có console, xem `Console.charset()`.
5. Trên Windows, kiểm tra `chcp`, PowerShell version và console input/output encoding.
6. Trên Linux/macOS, kiểm tra `locale`, `locale charmap`, `LANG`, `LC_CTYPE` và `LC_ALL`.
7. Ghi một chuỗi test cố định, so sánh byte UTF-8 bằng hex tool.
8. Nếu byte đúng, kiểm tra terminal decoder và font.
9. Nếu byte sai, kiểm tra encoder/decoder của Java stream hoặc shell pipeline.
10. Chỉ định UTF-8 rõ ràng cho file và protocol.
11. Kiểm thử cả terminal tương tác, redirect file và pipe.
12. Chạy lại trên JDK 17 và JDK 18+ nếu ứng dụng cần hỗ trợ cả hai.

Thay đổi từng lớp một để xác định chính xác nơi chuyển đổi sai. Đừng đổi cùng lúc `file.encoding`, code page, locale và PowerShell preferences vì sẽ khó xác định nguyên nhân.

## 22. Checklist

- [ ] Đã phân biệt Unicode code point, UTF-16 code unit, charset và byte.
- [ ] Đã hiểu luồng input/output giữa Java, shell và terminal.
- [ ] Đã phân biệt `Charset.defaultCharset()` với terminal charset.
- [ ] Đã biết JDK 18+ dùng UTF-8 làm default charset cho Java SE APIs.
- [ ] Đã kiểm tra riêng `stdin.encoding`, `stdout.encoding`, `stderr.encoding`.
- [ ] Đã biết `Console.charset()` có từ Java 17 và có thể khác default charset.
- [ ] Đã xử lý trường hợp `System.console()` trả về `null`.
- [ ] Đã chỉ định charset rõ ràng cho file và pipe protocol.
- [ ] Đã kiểm tra Windows code page bằng `chcp`.
- [ ] Đã phân biệt PowerShell 5.1 và PowerShell 7 encoding defaults.
- [ ] Đã kiểm tra Linux/macOS locale và locale availability.
- [ ] Đã kiểm tra SSH, WSL, container và CI log collector.
- [ ] Đã xử lý BOM theo định dạng file.
- [ ] Đã dùng strict encoding khi không cho phép mất dữ liệu.
- [ ] Đã kiểm tra Unicode normalization nếu cần so sánh văn bản.
- [ ] Đã xác minh byte bằng hex tool thay vì chỉ nhìn màn hình.
- [ ] Đã cấu hình source/resource encoding trong Gradle hoặc Maven.

## 23. Tài liệu tham khảo

- Oracle Java SE 25 API — System and standard streams: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html
- Oracle Java SE 25 API — Console.charset(): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html
- Oracle Java SE 25 Internationalization Guide — Default Charset and standard stream charsets: https://docs.oracle.com/en/java/javase/25/intl/internationalization-guide.pdf
- Oracle JDK 18 Release Notes — JEP 400, UTF-8 by Default: https://www.oracle.com/java/technologies/javase/18-relnote-issues.html
- Microsoft Learn — Console Code Pages: https://learn.microsoft.com/en-us/windows/console/console-code-pages
- Microsoft Learn — chcp command: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/chcp
- Microsoft Learn — PowerShell Character Encoding: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding
- Java SE API — Charset, CharsetEncoder and CodingErrorAction: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/package-summary.html

Terminal encoding là sự phối hợp giữa charset của Java stream, shell, hệ điều hành, terminal emulator và nguồn nhận dữ liệu. JDK 18+ giúp default charset của nhiều Java API thống nhất ở UTF-8, nhưng standard streams vẫn có encoding riêng. Khi chỉ định rõ charset cho file/protocol, kiểm tra đúng encoding của terminal và xác minh byte thực tế, ứng dụng Java có thể xử lý tiếng Việt và Unicode ổn định trên Windows, Linux, macOS, SSH, container và CI.