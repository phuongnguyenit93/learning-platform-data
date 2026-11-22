# Chuẩn hóa CR, LF, CRLF trong Java text block

## 1. Quy tắc cốt lõi

Text block là literal `String` nhiều dòng dùng ba dấu nháy kép `"""`. Đây là cú pháp chính thức từ Java 15 và tiếp tục được hỗ trợ trên các phiên bản Java hiện đại. **Bên trong nội dung mã nguồn của text block, mọi dấu kết thúc dòng CR, LF và CRLF đều được chuẩn hóa thành một LF (`\n`, U+000A)** khi biên dịch.

Nhờ vậy, cùng một text block cho ra giá trị `String` ổn định khi file `.java` dùng line ending khác nhau giữa Windows, Linux, macOS hay trình soạn thảo. Quy tắc chỉ áp dụng khi xử lý *literal text block trong mã nguồn*; Java không tự động chuẩn hóa mọi `String` đọc từ file, mạng hoặc cơ sở dữ liệu.

## 2. CR, LF và CRLF khác nhau thế nào?

| Ký hiệu | Tên | Java escape biểu diễn ký tự | Unicode | Số ký tự |
| --- | --- | --- | --- | --- |
| CR | Carriage Return | `\r` | U+000D | 1 |
| LF | Line Feed | `\n` | U+000A | 1 |
| CRLF | Carriage Return + Line Feed | `\r\n` | U+000D rồi U+000A | 2 |

CRLF gồm hai ký tự nhưng được Java nhận diện là **một dấu kết thúc dòng** trong mã nguồn. Quy tắc xử lý text block:

| Dấu kết thúc dòng thực trong file nguồn | Kết quả trong `String` |
| --- | --- |
| CR | Một LF (`\n`) |
| LF | Một LF (`\n`) |
| CRLF | Một LF (`\n`), không phải hai LF |

Ví dụ:

```java
String colors = """
        red
        green
        blue
        """;
```

Bất kể file Java lưu bằng CR, LF hay CRLF, giá trị tương đương là:

```java
String colors = "red\n" + "green\n" + "blue\n";
```

Không có newline ở đầu chuỗi dù bắt buộc phải xuống dòng sau `"""` mở. Newline sau `blue` được giữ vì dấu đóng nằm ở dòng riêng ngay sau dòng nội dung cuối.

## 3. Ba bước xử lý text block theo Java Language Specification

Thứ tự biên dịch nội dung text block là:

1. **Chuẩn hóa các dấu kết thúc dòng:** CRLF → LF, CR → LF, LF giữ nguyên.
2. **Loại khoảng trắng không chủ ý:** xử lý incidental white space như `String.stripIndent()`, gồm quy tắc thụt lề chung và khoảng trắng cuối dòng.
3. **Giải mã escape sequence:** xử lý như `String.translateEscapes()`, bao gồm các escape `\r`, `\n`, `\t`, `\s` và những escape hợp lệ khác.

Điều quan trọng là **escape được giải mã sau bước chuẩn hóa**. Dấu xuống dòng do bạn nhấn Enter trong text block chịu bước 1; escape `\r` hoặc `\n` trong mã nguồn chỉ trở thành ký tự thực ở bước 3.

Do đó, Java vẫn cho phép tạo CR và CRLF *có chủ ý* trong text block. Điều này khác với việc để nguyên ký tự CR, LF hay CRLF thực từ file mã nguồn.

## 4. Ví dụ chạy được trên Java 17+

Tạo file `TextBlockLineEndingDemo.java`:

```java
public class TextBlockLineEndingDemo {
    public static void main(String[] args) {
        String onlyLf = """
                first
                second
                """;

        String escaped = """
                first\r
                second\r
                """;

        String built = onlyLf.replace("\n", "\r\n");

        System.out.println(onlyLf.equals("first\nsecond\n"));
        System.out.println(onlyLf.chars().filter(c -> c == '\r').count());
        System.out.println(onlyLf.chars().filter(c -> c == '\n').count());
        System.out.println(escaped.equals("first\r\nsecond\r\n"));
        System.out.println(built.equals(escaped));
        System.out.println(onlyLf.length());
        System.out.println(built.length());
    }
}
```

Biên dịch và chạy:

```bash
javac TextBlockLineEndingDemo.java
java TextBlockLineEndingDemo
```

Output chính xác (đã kiểm chứng bằng JDK):

```text
true
0
2
true
true
13
15
```

**Giải thích:**

- `onlyLf` bằng `"first\nsecond\n"`: chứa hai LF, không có CR.
- `escaped` bằng `"first\r\nsecond\r\n"`. Trên mỗi dòng, escape `\r` đứng ngay trước newline thực từ mã nguồn. Sau các bước xử lý, hai ký tự đó tạo một cặp CRLF.
- `built` cũng có đúng hai cặp CRLF vì mỗi `\n` trong `onlyLf` được thay bằng `\r\n`.
- `"first\nsecond\n"` dài 13 đơn vị UTF-16 (5 + 1 + 6 + 1); dạng CRLF dài 15 (5 + 2 + 6 + 2).

Bài kiểm thử vẫn đúng khi trình soạn thảo đổi line ending của file `.java` từ LF sang CRLF. Với nguồn CR đơn, editor có hỗ trợ chế độ CR có thể dùng để kiểm nghiệm quy tắc tương tự.

## 5. Vị trí dấu đóng và ký tự xuống dòng cuối

Chuẩn hóa line ending chỉ quy định **loại ký tự** được dùng; nó không tự tạo hoặc xóa tùy ý newline cuối. Vị trí dấu đóng mới quyết định liệu có xuống dòng thực trước nó:

```java
String withFinalLf = """
        hello
        """;
// Giá trị: "hello\n"

String withoutFinalLf = """
        hello""";
// Giá trị: "hello"
```

Với text block hai dòng:

```java
String twoLines = """
        A
        B""";
// Giá trị: "A\nB"
```

Newline giữa `A` và `B` được chuẩn hóa thành LF; sau `B` không có newline vì dấu đóng ngay sát nội dung. Khi di chuyển dấu đóng sang dòng riêng, cũng cần kiểm tra quy tắc incidental indentation vì vị trí thụt lề của nó có thể thay đổi khoảng trắng đầu dòng của kết quả.

## 6. Cố ý tạo CR, LF hoặc CRLF

### 6.1. Dùng LF mặc định khi không có yêu cầu khác

```java
String text = """
        apple
        banana
        """;
// "apple\nbanana\n"
```

Đây là lựa chọn đơn giản để có nội dung nhất quán xuyên nền tảng. Không nên tự động đổi sang newline của hệ điều hành nếu định dạng hoặc hệ thống đích vốn chấp nhận LF.

### 6.2. Khi đầu ra bắt buộc CRLF

Nếu dữ liệu hiện tại **chỉ chứa LF**, có thể chuyển toàn bộ dấu kết thúc dòng sang CRLF:

```java
String crlfText = text.replace("\n", "\r\n");
```

`String.replace(CharSequence, CharSequence)` là thay thế literal; không cần biểu thức chính quy.

Nếu yêu cầu theo dấu xuống dòng của nền tảng hiện tại, dùng:

```java
String nativeText = text.replace("\n", System.lineSeparator());
```

`System.lineSeparator()` phụ thuộc môi trường thực thi, nên không thay cho `"\r\n"` khi giao thức yêu cầu CRLF cố định trên mọi hệ điều hành.

### 6.3. Chèn CR hoặc CRLF bằng escape trong text block

```java
String withCrLf = """
        alpha\r
        beta\r
        """;
// Giá trị: "alpha\r\nbeta\r\n"

String withBareCr = """
        left\rright""";
// Giá trị: "left\rright"
```

Trong `withCrLf`, CR xuất phát từ escape `\r`; LF là newline thực sau dòng nội dung. Hai ký tự kết hợp thành CRLF và **không bị chuẩn hóa lần nữa**. Trong `withBareCr`, chỉ có CR riêng lẻ ở giữa hai từ.

Nếu đã có newline thực cuối dòng, thêm escape `\n` ngay trước nó sẽ tạo **hai LF liên tiếp**, không phải một LF.

### 6.4. Chuỗi đọc từ bên ngoài có thể trộn nhiều loại newline

Chỉ chuẩn hóa nội dung text block khi biên dịch không đủ để xử lý dữ liệu nhận từ I/O. Với `String` đã tồn tại ở runtime, chuẩn hóa mọi kết thúc dòng CRLF/CR thành LF bằng hàm:

```java
static String normalizeToLf(String input) {
    return input.replace("\r\n", "\n")
                .replace("\r", "\n");
}
```

Nếu đầu ra phải toàn bộ là CRLF:

```java
String crlf = normalizeToLf(input).replace("\n", "\r\n");
```

Phải xử lý CRLF **trước** CR riêng. Nếu đầu vào đã có CRLF, việc gọi thẳng `input.replace("\n", "\r\n")` có thể tạo chuỗi sai `\r\r\n`.

## 7. Ảnh hưởng tới ghi file và hiển thị

- **Ghi file:** `Files.writeString(path, text, StandardCharsets.UTF_8)` mã hóa nội dung `text` để ghi file; nó không tự chuyển toàn bộ LF sang CRLF trên Windows. Nếu file đích yêu cầu CRLF, phải tạo giá trị CRLF trước khi ghi.
- **In console:** `System.out.println(text)` tự thêm dấu kết thúc dòng riêng, dễ khiến người đọc tưởng có thêm newline trong `text`. Không dùng hình ảnh console làm bằng chứng duy nhất.
- **So sánh dữ liệu:** `"A\nB"`, `"A\rB"`, `"A\r\nB"` là ba giá trị `String` khác nhau dù nhiều công cụ hiển thị chúng gần giống nhau.
- **Đếm ký tự:** `String.length()` đếm đơn vị UTF-16; CRLF gồm hai ký tự nên dài hơn LF một đơn vị ở mỗi vị trí.
- **Kiểm thử:** so sánh trực tiếp với chuỗi kỳ vọng, hoặc đếm `'\r'` và `'\n'`.

Ví dụ kiểm tra không cần nhìn console:

```java
String value = """
        A
        B
        """;

if (!value.equals("A\nB\n")) {
    throw new AssertionError("Unexpected text block line endings");
}
if (value.indexOf('\r') >= 0) {
    throw new AssertionError("Unexpected carriage return");
}
```

Nếu muốn *nhìn thấy* newline dưới dạng escape, dùng:

```java
String visible = value.replace("\r", "\\r")
                      .replace("\n", "\\n");
System.out.println(visible);
```

Output là một dòng chứa các ký tự hiển thị `A\nB\n` thay vì xuống dòng thực.

## 8. Sai lầm phổ biến cần tránh

1. **“Nguồn CRLF tạo `String` CRLF.”** Sai: newline thực bên trong text block được chuẩn hóa thành LF.
2. **“CRLF nguồn tạo hai LF.”** Sai: một cặp CRLF tạo đúng một LF.
3. **“Escape `\r` cũng bị chuẩn hóa thành LF.”** Sai: escape được giải mã sau bước chuẩn hóa.
4. **“Mọi `String` trong Java đều được chuẩn hóa.”** Sai: hành vi này thuộc biên dịch literal text block; chuỗi từ file/network cần xử lý riêng.
5. **“Text block lúc nào cũng có newline cuối.”** Sai: phụ thuộc dấu đóng và escape.
6. **“Cứ dùng `replace("\n", "\r\n")` cho mọi đầu vào.”** Sai với chuỗi vốn đã có CRLF; cần đưa mọi CRLF/CR về LF trước.
7. **“`println` chứng minh được số newline có sẵn.”** Sai vì `println` có hành vi xuống dòng bổ sung.

## 9. Ghi nhớ và áp dụng

Khi dùng text block, cần tách ba câu hỏi: (1) ký tự xuống dòng **thực trong file Java** là gì; (2) sau chuẩn hóa, escape và vị trí dấu đóng, giá trị **`String` runtime** chứa những ký tự nào; (3) file, API hoặc giao thức đầu ra yêu cầu LF, CRLF hay newline theo nền tảng. Kiểm thử trên giá trị chuỗi thực tế nếu dữ liệu cần đúng từng ký tự.

**Quy tắc tổng quát:** CR / LF / CRLF *trong mã nguồn text block* → LF; escape `\r` và `\n` được áp dụng sau đó; chuyển sang CRLF có chủ đích khi đầu ra yêu cầu.

## Tài liệu tham khảo chính thức

- [Java Language Specification, §3.10.6 — Text Blocks, Java SE 25](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): ba bước biến đổi nội dung text block.
- [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): chuẩn hóa line terminator, escape và ví dụ thực tế.

Đây là kiến thức hiện hành, dựa trên cú pháp text block chính thức từ Java 15, áp dụng cho Java 17+ và các phiên bản Java mới.