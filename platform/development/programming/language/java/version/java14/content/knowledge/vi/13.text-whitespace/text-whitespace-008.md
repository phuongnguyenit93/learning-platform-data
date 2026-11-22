# Kiểm thử nội dung khi chuyển giữa các hệ điều hành — Java text blocks và khoảng trắng văn bản

> **Module:** Java 14 → **Khoảng trắng văn bản**. Đề bài: **Kiểm thử nội dung khi chuyển giữa các hệ điều hành**. Text blocks xuất hiện lần đầu dưới dạng preview ở Java 13, tiếp tục preview tại Java 14, và **chính thức từ Java 15 (JEP 378)**. Bài này chỉ dùng kiến thức còn áp dụng với Java hiện đại: cách xử lý dấu xuống dòng, khoảng trắng, tab, ký tự UTF-8 và cách kiểm thử chuỗi/file trên Windows, Linux, macOS. Ví dụ dùng JDK hiện hành được cập nhật (như 21 hoặc 25), biên dịch theo ngôn ngữ Java 17. Không cần cài JDK 14 cũ hay bật `--enable-preview`.

## 1. Vấn đề thực tế: cùng mã nguồn, khác hệ điều hành thì điều gì có thể khác?

Một ứng dụng có thể được phát triển trên Windows, kiểm thử trong Linux container và chạy trên macOS. Code chứa text block:

~~~java
String message = """
        Alpha
        Beta
        """;
~~~

Trên cả ba môi trường, **giá trị `String` của text block trên vẫn là `"Alpha\nBeta\n"`**, miễn là mã nguồn Java giữ cùng nội dung và quy tắc thụt lề. Java chuẩn hóa line terminator bên trong text block thành **LF**. Nhưng mọi thao tác liên quan tới file, console hay hệ thống bên ngoài **không tự động được chuẩn hóa như vậy**.

Ba tầng khác nhau thường gây nhầm lẫn:

1. **Mã nguồn `.java`**: editor/Git có thể lưu dòng bằng LF (`\n`), CRLF (`\r\n`), hoặc hiếm hơn là CR (`\r`).
2. **Giá trị `String` trong chương trình**: text block đã được Java xử lý, có quy tắc chuẩn hóa line terminator, loại khoảng trắng thụt lề phụ, rồi giải mã escape.
3. **Bytes/file/output khi chạy**: được quyết định bởi API ghi file, charset, dữ liệu thật và đôi khi `System.lineSeparator()`; không nhất thiết giống cách file `.java` xuống dòng.

**Mục tiêu kiểm thử:** mỗi bài test phải xác định mình đang xác minh **nội dung ký tự `String`**, **nội dung file sau đọc/ghi**, hay **bytes chính xác**. Không dùng một loại so sánh thay cho tất cả.

## 2. Kết quả cần đạt

Học xong, bạn có thể:

- Giải thích LF, CRLF, CR và vì sao text block trong Java có nội dung nhất quán khi file nguồn được chuyển đổi giữa các hệ điều hành.
- Phân biệt **newline trong source**, **newline trong `String`**, **newline do API xuất file**, và **ký tự xuống dòng do console hiển thị**.
- Viết assertion kiểm tra chính xác `\n`, `\r`, dấu xuống dòng cuối, khoảng trắng đầu/cuối và tab.
- Kiểm thử giá trị text block có thụt lề, dòng trống, dấu cách cuối dòng được giữ bằng `\s`.
- Đọc/ghi file bằng `Files.readString`/`Files.writeString` với charset xác định; biết khi nào cần so sánh `Files.readAllBytes`.
- Dùng chuẩn hóa line endings **chỉ khi hợp đồng cho phép**, không che giấu lỗi của định dạng phải chính xác từng byte.
- Thiết kế golden-file tests và CI chạy trên Windows, Linux, macOS để phát hiện sai lệch thực tế.
- Biết xử lý ảnh hưởng của cấu hình IDE/Git, console encoding và file fixture mà không nhầm chúng với cú pháp Java.

## 3. Cơ chế chính thức: text block có ba bước xử lý

Theo Java Language Specification `3.10.6, nội dung text block được xử lý theo thứ tự:

1. **Chuẩn hóa line terminators** trong nội dung: `\r\n` → `\n`, và `\r` → `\n`.
2. **Loại incidental white space**: tính và loại phần thụt lề không thiết yếu, xử lý các khoảng trắng cuối dòng theo thuật toán tương đương `String.stripIndent()`.
3. **Diễn giải escape sequences**: ví dụ `\n`, `\t`, `\s`, `\\` và backslash nối dòng.

Thứ tự này rất quan trọng. Đặc biệt, escape `\s` được diễn giải **sau** khi xử lý khoảng trắng thừa, nên có thể tạo một dấu cách cuối dòng mà formatter không thể xóa ở giai đoạn trước.

| Ký hiệu | Unicode | Diễn giải |
| --- | --- | --- |
| LF, `\n` | U+000A | Một ký tự *line feed*. |
| CR, `\r` | U+000D | Một ký tự *carriage return*. |
| CRLF, `\r\n` | U+000D + U+000A | **Hai ký tự** liên tiếp, thường là một lần xuống dòng ở file Windows. |
| Space, ` ` | U+0020 | Một dấu cách thường. |
| Tab, `\t` | U+0009 | Ký tự tab; độ rộng hiển thị phụ thuộc công cụ. |
| Nonbreaking space | U+00A0 | Dấu cách không ngắt; không đồng nhất với space ASCII trong mọi phép xử lý. |

Một chương trình có thể chạy trên Windows với `System.lineSeparator()` bằng `"\r\n"`, nhưng text block thông thường vẫn có `\n` trong giá trị. **Không dùng `System.lineSeparator()` làm kỳ vọng mặc định cho giá trị text block.**

### Ví dụ minh họa nhanh

~~~java
String block = """
        A
        B
        """;
String expected = "A\nB\n";
~~~

Hai biến chứa **cùng nội dung**. Dấu xuống dòng ngay sau dấu mở `"""` là phần bắt buộc của cú pháp, **không tự tạo `\n` đầu chuỗi**. Dấu đóng trên dòng riêng khiến giá trị có `\n` cuối.

## 4. Ví dụ chạy độc lập: kiểm tra text block ổn định trên mọi hệ điều hành

Tạo tệp **`CrossPlatformTextBlockDemo.java`**:

~~~java
public class CrossPlatformTextBlockDemo {
    public static void main(String[] args) {
        String actual = """
                Alpha
                  Beta
                Gamma
                """;

        String expected = "Alpha\n  Beta\nGamma\n";

        System.out.println(actual.equals(expected));
        System.out.println(actual.startsWith("\n"));
        System.out.println(actual.endsWith("\n"));
        System.out.println(actual.indexOf('\r') == -1);
        System.out.println(
                actual.replace(" ", "·").replace("\n", "|"));
    }
}
~~~

Biên dịch bằng JDK hiện hành (chọn UTF-8 để việc đọc mã nguồn có ký tự tiếng Việt và ký hiệu đặc biệt được nhất quán):

~~~bash
javac -encoding UTF-8 --release 17 CrossPlatformTextBlockDemo.java
java CrossPlatformTextBlockDemo
~~~

**Stdout chính xác:**

~~~text
true
false
true
true
Alpha|··Beta|Gamma|
~~~

Phân tích:

- `expected` dùng escape `\n` để mô tả **chính xác** những ký tự cần có.
- `actual.equals(expected)` là `true`, không phụ thuộc giá trị `System.lineSeparator()`.
- `startsWith("\n")` trả `false` dù dấu mở của text block bắt buộc phải xuống dòng.
- `endsWith("\n")` trả `true` vì dấu đóng nằm trên dòng riêng.
- `indexOf('\r') == -1` xác nhận không có CR trong nội dung.
- Sau khi thay space thành `·` và LF thành `|`, có thể thấy dòng `Beta` còn đúng **hai dấu cách** thụt lề có ý nghĩa, còn phần thụt lề mã nguồn đã bị loại bỏ.

Đây là ví dụ kiểm thử **giá trị runtime**. Nó không khẳng định file `.java` trên mọi máy có bytes giống nhau; source có thể dùng LF hoặc CRLF nhưng khi biên dịch đúng, giá trị text block được chuẩn hóa.

## 5. Vì sao phải kiểm tra dấu xuống dòng cuối?

Hai text block đều hợp lệ nhưng khác giá trị:

~~~java
String withFinalLf = """
        one
        two
        """;
~~~

Giá trị: `"one\ntwo\n"`.

~~~java
String withoutFinalLf = """
        one
        two""";
~~~

Giá trị: `"one\ntwo"`.

**Điểm khác nhau không phải hệ điều hành** mà là **vị trí dấu đóng `"""`**. Golden files, snapshots, SQL text và format đầu ra có thể yêu cầu chính xác có hoặc không có newline cuối; nếu assertion chỉ so từng dòng thì rất dễ bỏ sót.

### Ví dụ chạy độc lập

Tạo tệp **`FinalNewlineTestDemo.java`**:

~~~java
public class FinalNewlineTestDemo {
    public static void main(String[] args) {
        String withFinalLf = """
                one
                two
                """;

        String withoutFinalLf = """
                one
                two""";

        System.out.println(withFinalLf.equals("one\ntwo\n"));
        System.out.println(withoutFinalLf.equals("one\ntwo"));
        System.out.println(withFinalLf.endsWith("\n"));
        System.out.println(withoutFinalLf.endsWith("\n"));
        System.out.println(withFinalLf.lines().count());
        System.out.println(withoutFinalLf.lines().count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 FinalNewlineTestDemo.java
java FinalNewlineTestDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
false
2
2
~~~

`String.lines()` trả 2 dòng với cả hai chuỗi; nó **không tạo thêm dòng rỗng sau line terminator cuối**. Vì vậy đếm dòng **không đủ** để kiểm tra dấu xuống dòng cuối. Dùng `equals` hoặc `endsWith("\n")` khi yêu cầu cần chính xác.

## 6. Kiểm thử khoảng trắng: dấu cách, tab và cuối dòng

Hành vi dễ gây sai khi chuyển hệ điều hành không chỉ là `\r\n`/`\n`. IDE có thể tự đổi tab thành space, Git có thể báo lỗi trailing whitespace, hoặc một formatter làm thay đổi căn lề. Cần phân biệt:

- **Incidental indentation**: khoảng trắng để căn mã Java, thường bị Java loại khỏi text block.
- **Khoảng trắng có ý nghĩa trong nội dung**: khoảng trắng giữa từ, độ thụt vào thêm của JSON/HTML, ký tự tab thực sự hoặc dấu cách cần giữ cuối dòng.
- **Trailing spaces vô hình**: khoảng trắng thừa sau ký tự cuối dòng, thường bị text block loại bỏ trừ khi dùng escape phù hợp.
- **Dòng trống**: có thể là một phần của giá trị và phải được tính riêng với line terminator sau dấu mở.

Theo hướng dẫn chính thức, thuật toán xử lý indentation coi **mỗi ký tự tab là một ký tự khoảng trắng** khi xác định độ thụt; nó không mô phỏng độ rộng tab 4 hoặc 8 ô của editor. Vì vậy, mã nguồn dùng lẫn tab và space có thể **trông thẳng hàng ở một editor** nhưng tạo kết quả bất ngờ.

**Quy ước nên áp dụng:** chọn một kiểu thụt lề nhất quán cho text block; khi khoảng trắng thuộc giao thức hoặc định dạng cần chính xác, viết test kiểm tra ký tự thực thay vì chỉ nhìn source.

### Giữ dấu cách ở cuối dòng bằng `\s`

~~~java
String text = """
        A\s
        B
        """;
~~~

Giá trị mong đợi: `"A \nB\n"` — có **một dấu cách giữa A và newline**. Vì escape `\s` chỉ được diễn giải sau bước loại incidental whitespace, dấu cách này được giữ.

### Ví dụ chạy độc lập: dấu cách và tab

Tạo tệp **`WhitespaceEscapeTestDemo.java`**:

~~~java
public class WhitespaceEscapeTestDemo {
    public static void main(String[] args) {
        String trailingSpace = """
                A\s
                B
                """;

        String containsTab = """
                A\tB
                """;

        System.out.println(trailingSpace.equals("A \nB\n"));
        System.out.println(trailingSpace.contains("A \n"));
        System.out.println(containsTab.equals("A\tB\n"));
        System.out.println(containsTab.indexOf('\t') == 1);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 WhitespaceEscapeTestDemo.java
java WhitespaceEscapeTestDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
true
~~~

`\t` trong nội dung tạo tab thực, không phải một số dấu cách tương đương. `String.replace(" ", "·")` sẽ không hiển thị tab; nếu cần quan sát, hãy hiển thị `\t` bằng ký hiệu riêng hoặc in code point của ký tự.

**Đừng “sửa” mọi lỗi trắng bằng `trim()` hoặc `strip()`:** chúng có thể loại ký tự hợp lệ mà test cần bảo toàn, đặc biệt với dữ liệu cố định cột, file checksum, đoạn mã nhiều dòng hoặc định dạng nhạy cảm với whitespace.

## 7. Kiểm thử dòng trống đầu và cuối

Line terminator sau dấu mở `"""` chỉ kết thúc opening delimiter. Để tạo một `\n` **ở đầu giá trị**, phải có **một dòng trống thực sự** ngay sau dòng dấu mở:

~~~java
String withLeadingEmptyLine = """

        Header
        """;
~~~

Giá trị là `"\nHeader\n"`. Nếu lỡ thêm/xóa dòng trống lúc chỉnh sửa trên hệ điều hành khác, source vẫn có thể biên dịch nhưng nội dung runtime thay đổi.

Kiểm thử thích hợp:

~~~java
if (!withLeadingEmptyLine.equals("\nHeader\n")) {
    throw new AssertionError("unexpected leading/trailing blank lines");
}
~~~

Đây là **mảnh lệnh** trong phương thức có biến `withLeadingEmptyLine`. Assertion cho giá trị đầy đủ rõ ràng hơn kiểm tra `lines().count()` hoặc nhìn output console, vì một số terminal không làm dòng trống cuối nổi bật.

**Nên phân biệt hai chính sách:**

- Nội dung văn bản có thể co giãn: một số dòng trống/căn lề thay đổi được cho phép theo hợp đồng.
- Cấu trúc giao thức, snapshot, nội dung gửi API hoặc dữ liệu ký số: từng ký tự, bao gồm whitespace, có thể phải **khớp tuyệt đối**.

Không biến một kiểm thử yêu cầu chính xác thành so sánh sau `strip()` nếu hợp đồng không cho phép.

## 8. Text block chuẩn hóa source; file đọc từ đĩa thì không nhất thiết

Một `String` đã được compiler tạo từ text block thường dùng LF. Ngược lại, `Files.readString(path, UTF_8)` đọc **ký tự từ bytes trong file thật**. Nếu file có CRLF, chuỗi đọc được sẽ chứa CRLF. API này **không tự chuẩn hóa line endings như trình biên dịch text block**.

Ví dụ:

~~~java
String fromTextBlock = """
        A
        B
        """;
String fromCrLfFile = "A\r\nB\r\n";
~~~

`fromTextBlock.equals(fromCrLfFile)` là **`false`** dù khi xem bằng trình soạn thảo thông thường, hai đoạn có thể trông giống hệt nhau.

Có hai chiến lược kiểm thử khác nhau:

1. **So sánh chính xác:** dùng `expected.equals(actual)` hoặc so byte khi CRLF/LF là một phần của hợp đồng.
2. **So sánh logic sau chuẩn hóa:** chỉ khi tài liệu định dạng **cho phép** dùng LF, CRLF hoặc CR như những cách xuống dòng tương đương, chuẩn hóa chúng về LF rồi so sánh.

Không chọn chiến lược 2 chỉ để làm test “xanh” nếu dữ liệu thực tế cần chính xác.

### Hàm chuẩn hóa line endings theo hợp đồng

~~~java
static String normalizeToLf(String text) {
    return text.replace("\r\n", "\n").replace('\r', '\n');
}
~~~

Đây là **mảnh phương thức**. Thứ tự thay `\r\n` trước `\r` là quan trọng: nó tránh biến một CRLF thành hai LF. Hàm chỉ xử lý **CRLF và CR**, không tự đổi dấu cách, tab, form feed hoặc mọi Unicode line separator.

### Ví dụ chạy độc lập: mô phỏng ba kiểu file

Tạo tệp **`LineEndingNormalizationDemo.java`**:

~~~java
public class LineEndingNormalizationDemo {
    static String normalizeToLf(String text) {
        return text.replace("\r\n", "\n").replace('\r', '\n');
    }

    public static void main(String[] args) {
        String lf = "A\nB\n";
        String crlf = "A\r\nB\r\n";
        String cr = "A\rB\r";

        System.out.println(normalizeToLf(lf).equals(lf));
        System.out.println(normalizeToLf(crlf).equals(lf));
        System.out.println(normalizeToLf(cr).equals(lf));
        System.out.println(crlf.equals(lf));
        System.out.println(lf.lines().count());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 LineEndingNormalizationDemo.java
java LineEndingNormalizationDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
false
2
~~~

Dòng thứ tư `false` là bằng chứng **khác nhau thật về ký tự** trước khi chuẩn hóa. Hàm chuẩn hóa trả cùng nội dung khi đầu vào mang một trong ba kiểu newline được cho phép.

Lưu ý: **`String.lines()` nhận diện `\n`, `\r` và `\r\n` để tách dòng nhưng bỏ ký tự ngăn dòng**. Vì vậy, so sánh danh sách dòng có thể làm mất thông tin loại separator và newline cuối. Nếu cần phát hiện sự khác nhau này, **không chỉ so `lines()`**.

## 9. Khi ghi file, phải phân biệt `Files.writeString` và `Files.write(lines)`

Hai API Java NIO rất dễ bị nhầm:

| API | Quy tắc xuống dòng quan trọng |
| --- | --- |
| `Files.writeString(path, text, UTF_8)` | Ghi các ký tự **đúng như có trong `text`**, gồm LF hoặc CRLF; không tự thêm separator. |
| `Files.readString(path, UTF_8)` | Đọc lại các ký tự theo bytes thực của file, giữ ký tự xuống dòng trong file. |
| `Files.write(path, Iterable<CharSequence>, UTF_8)` | Ghi **từng dòng** và thêm **platform line separator** sau mỗi dòng. |
| `Files.readAllLines(path, UTF_8)` | Đọc danh sách dòng, **loại bỏ separators**; không thích hợp khi phải kiểm tra nguyên văn line ending. |
| `Files.readAllBytes(path)` | Trả **bytes thực**, dùng khi phải kiểm tra encoding, BOM, LF/CRLF hoặc file golden từng byte. |

Vì `Files.writeString` không đổi LF thành CRLF theo hệ điều hành, bạn có thể tạo một file UTF-8 với LF hoàn toàn giống nhau trên Windows/Linux/macOS. Nhưng với `Files.write` nhận danh sách dòng, khi hệ điều hành có `System.lineSeparator()` khác nhau thì **bytes có thể khác**, dù dữ liệu từng dòng giống nhau. 

Dùng các API phù hợp mục đích, không dựa vào nhận xét chung “Java tự đổi line endings theo OS”.

### Ví dụ chạy độc lập: `writeString` giữ nguyên `String`

Tạo tệp **`WriteStringRoundTripDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class WriteStringRoundTripDemo {
    public static void main(String[] args) throws Exception {
        String content = """
                Cà phê
                Java
                """;

        Path file = Files.createTempFile("tb-roundtrip-", ".txt");
        try {
            Files.writeString(file, content, StandardCharsets.UTF_8);

            String restored =
                    Files.readString(file, StandardCharsets.UTF_8);
            byte[] expected =
                    content.getBytes(StandardCharsets.UTF_8);
            byte[] actual = Files.readAllBytes(file);

            System.out.println(restored.equals(content));
            System.out.println(Arrays.equals(actual, expected));
            System.out.println(restored.indexOf('\r') == -1);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 WriteStringRoundTripDemo.java
java WriteStringRoundTripDemo
~~~

**Stdout chính xác trong trường hợp ghi/đọc file thành công:**

~~~text
true
true
true
~~~

Điều đã kiểm tra:

- `Files.writeString` lưu nội dung chính xác theo charset UTF-8 và không thêm CRLF theo OS.
- `Files.readString` đọc lại đúng các ký tự, bao gồm dấu `\n` cuối.
- `Arrays.equals` xác nhận **bytes thật trong file** khớp với việc encode chính `content` bằng UTF-8.
- `finally` dọn file tạm sau kiểm thử để không để lại artifact trên máy.

Chương trình sử dụng thư mục tạm do Java tạo; nếu môi trường không cho tạo file, test sẽ thất bại vì điều kiện I/O — **không phải vì semantics của text block**. Trong CI, cung cấp quyền file tạm đúng theo môi trường chạy.

### Ví dụ chạy độc lập: danh sách dòng dùng separator của nền tảng

Tạo tệp **`WriteLinesPlatformDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class WriteLinesPlatformDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("line-api-", ".txt");

        try {
            Files.write(file, List.of("A", "B"),
                    StandardCharsets.UTF_8);

            String actual =
                    Files.readString(file, StandardCharsets.UTF_8);
            String expected = "A" + System.lineSeparator()
                    + "B" + System.lineSeparator();

            System.out.println(actual.equals(expected));
            System.out.println(actual.endsWith(
                    System.lineSeparator()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 WriteLinesPlatformDemo.java
java WriteLinesPlatformDemo
~~~

**Stdout chính xác trong trường hợp I/O thành công:**

~~~text
true
true
~~~

`System.lineSeparator()` phản ánh dấu kết thúc dòng của môi trường Java lúc khởi động: thường `"\r\n"` trên Windows và `"\n"` trên Linux/macOS. Chương trình **không in giá trị separator**, nên kết quả boolean giống nhau; bytes file giữa các OS vẫn có thể khác.

Nếu **hợp đồng file quy định LF cố định**, dùng `Files.writeString` với chuỗi đã chứa `\n`, không dùng `Files.write` với danh sách dòng rồi kỳ vọng luôn thu được cùng bytes ở mọi OS.

## 10. Charset và Unicode cũng là một phần của kiểm thử đa nền tảng

Nhiều lỗi nhìn giống “sai khoảng trắng” thực ra là **sai charset**, nhất là với tiếng Việt hoặc ký tự đặc biệt. Các quy tắc nên áp dụng:

- Lưu file nguồn `.java` dưới dạng **UTF-8** và cấu hình build rõ ràng; lệnh `javac -encoding UTF-8 --release 17` giúp chủ động xử lý ký tự non-ASCII.
- Khi ghi/đọc file phục vụ test, chỉ định `StandardCharsets.UTF_8`. Các overload `Files.readString(path)`/`Files.writeString(path, text)` của Java 11+ vốn dùng UTF-8, nhưng ghi rõ charset giúp người học thấy contract.
- Không suy đoán từ console hiển thị. Console encoding, font và terminal có thể khiến ký tự tiếng Việt nhìn khác, trong khi `String.equals` hoặc bytes UTF-8 vẫn chính xác.
- Xác định có hay không **BOM** (byte-order mark) trong fixture. Ký tự U+FEFF ở đầu dữ liệu có thể khiến so sánh thất bại. Đừng tự xóa BOM nếu định dạng yêu cầu bảo toàn bytes.
- **Unicode normalization (NFC/NFD) khác newline normalization**. Hai cách biểu diễn dấu tiếng Việt có thể nhìn giống nhau nhưng có dãy code point khác; Java không tự chuẩn hóa NFC chỉ vì dùng text block. Chỉ áp dụng `java.text.Normalizer` khi hợp đồng dữ liệu quy định.
- `String.length()` đếm **UTF-16 code units**, không phải số bytes UTF-8 hay số ký tự người dùng nhìn thấy. Khi test nội dung Unicode, nên so bằng `equals` và ghi rõ chuẩn encoding.

### Kiểm tra bytes khi cần tính ổn định cao

~~~java
byte[] expectedBytes =
        expected.getBytes(java.nio.charset.StandardCharsets.UTF_8);
byte[] actualBytes = java.nio.file.Files.readAllBytes(path);
boolean same = java.util.Arrays.equals(
        expectedBytes, actualBytes);
~~~

Đây là **mảnh mã trong phương thức**, có `expected` là `String` và `path` là `Path`. So bytes hữu ích với file snapshot, payload signed hoặc giao thức yêu cầu đúng encoding + line endings. Nếu quy tắc chỉ cần nội dung logic, kiểm tra `String` có thể dễ đọc hơn.

**Cẩn trọng:** dữ liệu được ký, hash, checksum hoặc yêu cầu reproducible artifacts thường cần **so bytes chính xác**, không tự chuẩn hóa line endings sau khi đọc vì thao tác đó có thể che sai lệch quan trọng.

## 11. So sánh chính xác và so sánh chuẩn hóa: chọn đúng hợp đồng

| Tình huống | Loại kiểm thử phù hợp | Vì sao |
| --- | --- | --- |
| Text block dùng làm câu SQL/HTML/JSON tĩnh trong mã | So `String.equals(expected)` khi whitespace có ý nghĩa | Kiểm soát dấu xuống dòng và indent thực. |
| Nội dung hiển thị cho con người, LF/CRLF đều được chấp nhận | Chuẩn hóa CRLF/CR về LF rồi so | Loại khác biệt được **hợp đồng cho phép**. |
| File export được đặc tả **LF** | So String/bytes **chính xác với LF** | Phát hiện output vi phạm LF. |
| File output phải dùng separator riêng của OS | Kỳ vọng `System.lineSeparator()` khi đó là yêu cầu thật | Tránh hardcode CRLF/LF không phù hợp hợp đồng. |
| Tệp fixture được kiểm tra checksum hoặc chữ ký | So bytes thực, không chuẩn hóa | Một byte khác phải thất bại. |
| Nội dung cần bảo toàn dấu cách cuối dòng | So byte/`equals`, test `\s` và dấu cách | `strip()` có thể xóa thông tin có ý nghĩa. |
| So nội dung đã đọc bằng `readAllLines` | Chỉ khi dấu xuống dòng không cần bảo toàn | API trả các dòng không kèm separators. |
| Kiểm tra đầu/cuối chuỗi | Dùng `startsWith`, `endsWith` hoặc `equals` | `lines().count()` không xác nhận được newline cuối. |

**Không nên dùng `actual.trim().equals(expected.trim())` như lời giải mặc định.** Nó bỏ đi các ký tự đầu/cuối có thể quan trọng và khiến bài test bỏ sót lỗi. `String.strip()` cũng không phải giải pháp chung. Chuẩn hóa chỉ nên tác động đến **những khác biệt được định nghĩa là tương đương**.

Nếu một test chuẩn hóa line endings, hãy viết comment/README nói rõ tại sao hợp đồng cho phép. Nếu không, người sau có thể hiểu nhầm normalization là yêu cầu kỹ thuật bắt buộc của Java thay vì lựa chọn nghiệp vụ.

## 12. Kỹ thuật nhìn thấy khoảng trắng vô hình

Khi một assertion thất bại, thông báo `expected != actual` đôi khi không giúp tìm ra ký tự khác biệt. Có thể hiển thị bằng các ký hiệu rõ ràng:

~~~java
static String visible(String text) {
    return text
            .replace("\r", "␍")
            .replace("\n", "␊\n")
            .replace("\t", "⇥")
            .replace(" ", "·");
}
~~~

Đây là **mảnh phương thức** để chẩn đoán. Với `"A \r\nB\t"`, nó hiển thị space là `·`, CR là `␍`, LF là `␊` và tab là `⇥`. Ký hiệu không thay đổi `String` gốc; chỉ tạo một chuỗi trình bày để nhận ra sai lệch.

Một số mẹo khác:

- Kiểm tra vị trí đầu tiên khác nhau thay vì in cả nội dung dài (đặc biệt với fixture bí mật).
- Dùng `codePointAt` hoặc vòng lặp duyệt ký tự để in mã Unicode, chẳng hạn U+000D, U+000A, U+0009, U+0020.
- Hiển thị `expected.length()`/`actual.length()` nhưng nhớ đó là số UTF-16 code units, **không phải byte count**.
- Ghi rõ index của điểm khác biệt và một đoạn ngắn quanh vị trí đó, tránh in payload nhạy cảm vào CI log.
- Với file, dùng hex view hoặc so `Files.readAllBytes` để thấy bytes 0D 0A khác 0A.

### Ví dụ chạy độc lập: chẩn đoán rõ khác biệt CRLF và LF

Tạo tệp **`WhitespaceVisualizerDemo.java`**:

~~~java
public class WhitespaceVisualizerDemo {
    static String visible(String value) {
        return value.replace("\r", "␍")
                .replace("\n", "␊")
                .replace("\t", "⇥")
                .replace(" ", "·");
    }

    public static void main(String[] args) {
        String lf = "A \nB";
        String crlf = "A \r\nB";

        System.out.println(visible(lf));
        System.out.println(visible(crlf));
        System.out.println(lf.equals(crlf));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 WhitespaceVisualizerDemo.java
java WhitespaceVisualizerDemo
~~~

**Stdout chính xác nếu terminal hiển thị Unicode đúng:**

~~~text
A·␊B
A·␍␊B
false
~~~

Trên terminal không hỗ trợ các ký hiệu `·`/`␍`/`␊`, hình hiển thị có thể khác nhưng `lf.equals(crlf)` vẫn là `false`. Vì vậy kiểm thử nên assert **giá trị**, không nên dựa vào screenshot terminal.

## 13. Golden file/snapshot: nơi đa hệ điều hành hay gây test flakiness

Một *golden file* là file chuẩn được dùng làm kỳ vọng. Khi Git hoặc editor đổi LF ↔ CRLF, một phép so bytes có thể fail dù nội dung đọc theo dòng trông không khác; ngược lại, test chỉ so dòng có thể bỏ sót lỗi cần bắt.

Quy trình an toàn:

1. **Định nghĩa chuẩn kỳ vọng**: fixture có LF cố định, hay mỗi OS được phép dùng separator riêng?
2. **Định nghĩa charset**: với nội dung text, ưu tiên UTF-8 và quy định BOM nếu có.
3. **Chọn API so đúng mức**: `Files.readString` để giữ các ký tự separator; `readAllBytes` nếu phải so bytes; chỉ dùng `readAllLines` khi separators không quan trọng.
4. **Kiểm tra newline cuối**: nhiều formatter/editor thêm newline cuối theo policy; nếu phải giữ, viết assertion `endsWith("\n")` hoặc so nguyên file.
5. **Kiểm tra tab/space và trailing whitespace**: text block có thuật toán xử lý indent, nhưng fixture file không tự áp dụng thuật toán đó.
6. **Đóng khung chính sách chuyển đổi của Git**: nếu fixture quy định LF, có thể cấu hình `.gitattributes` cho loại file tương ứng; nếu fixture cần bytes bất biến, không tự bật text conversion.
7. **Chạy test trên nhiều OS** và ghi kết quả; nếu fail, so sánh code points/bytes trước khi sửa kỳ vọng.

Ví dụ chính sách **minh họa** trong `.gitattributes` của repository dùng Git:

~~~gitattributes
*.java text eol=lf
*.golden text eol=lf
*.bin -text
~~~

- Các file `.java` và `.golden` được chỉ định line ending LF trong working tree ở những môi trường Git hỗ trợ cấu hình này.
- File `.bin` được xem như dữ liệu không chuyển đổi line endings kiểu text.
- Đây là **quy ước quản lý nguồn**, không phải cú pháp Java và **không thay thế test**. Cần kiểm tra các file fixture hiện có trước khi đổi policy, nhất là file Windows-specific cần CRLF.

**Tránh quy ước “mọi test đều normalize LF”**: với một file có yêu cầu bytes chính xác, việc đó che đi sai lệch. Ngược lại, nếu hợp đồng coi CRLF và LF tương đương, test fail chỉ vì line ending của fixture là test quá chặt.

## 14. Ví dụ kiểm thử tự chứa: không phụ thuộc JUnit hay OS

Khi mới học, có thể dùng một `main` kèm `AssertionError` để minh họa điều kiện. Trong dự án thật, chuyển sang JUnit hoặc framework kiểm thử đang được hỗ trợ và giữ cùng logic kỳ vọng. Lợi ích của ví dụ độc lập là chạy được ở mọi máy có JDK phù hợp mà không cần tải dependency.

Tạo tệp **`CrossPlatformAssertionsDemo.java`**:

~~~java
public class CrossPlatformAssertionsDemo {
    private static void requireEqual(
            String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " mismatch");
        }
    }

    private static String normalizeToLf(String input) {
        return input.replace("\r\n", "\n").replace('\r', '\n');
    }

    public static void main(String[] args) {
        String report = """
                Name: Java
                Count: 2
                """;

        requireEqual("Name: Java\nCount: 2\n",
                report, "text block");

        String windowsFile = "Name: Java\r\nCount: 2\r\n";
        requireEqual(report, normalizeToLf(windowsFile),
                "line ending equivalent by contract");

        String withSpace = """
                X\s
                """;
        requireEqual("X \n", withSpace,
                "trailing space");

        if (!report.endsWith("\n")
                || report.indexOf('\r') != -1) {
            throw new AssertionError("unexpected line ending");
        }

        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 CrossPlatformAssertionsDemo.java
java CrossPlatformAssertionsDemo
~~~

**Stdout chính xác:**

~~~text
all checks passed
~~~

Giải thích từng kiểm tra:

- `requireEqual` so **nguyên chuỗi** để giữ được khoảng trắng, line ending và newline cuối.
- `report` là text block Java với LF do compiler chuẩn hóa.
- `windowsFile` mô phỏng nội dung file có CRLF; chỉ được xem là tương đương sau khi áp dụng **chính sách normalizeToLf** đã chọn.
- `withSpace` xác nhận escape `\s` bảo toàn một dấu cách cuối dòng.
- Assertion cuối đảm bảo text block kết thúc bằng LF và không chứa CR.

Mẫu này thích hợp làm bước đầu trước khi chuyển sang test framework chuyên nghiệp. **Không in nguyên nội dung thất bại** trong hệ thống có dữ liệu bí mật; dùng label, index khác biệt hoặc marker thử nghiệm an toàn.

## 15. Ma trận chạy test trên Windows, Linux và macOS

Viết test đúng chưa đủ; khi định dạng file, bộ đệm hoặc công cụ khác tham gia, nên chạy cùng test suite trên ít nhất hai OS khác biệt, nếu dự án thực sự phân phối đa nền tảng.

| Hạng mục | Linux | Windows | macOS | Điều cần quan sát |
| --- | --- | --- | --- | --- |
| `String` từ cùng text block | Chạy | Chạy | Chạy | Giá trị **LF như nhau** khi nguồn tương đương. |
| `String` đọc từ fixture CRLF | Chạy | Chạy | Chạy | `Files.readString` vẫn giữ CRLF thật trong file. |
| `Files.writeString(..., UTF_8)` từ chuỗi LF | Chạy | Chạy | Chạy | Bytes file giống nhau nếu input giống nhau. |
| `Files.write(..., lines, UTF_8)` | Chạy | Chạy | Chạy | Dùng line separator của **OS đang chạy**; test theo contract. |
| Fixture và golden files | Chạy | Chạy | Chạy | Chính sách Git/editor có thay đổi LF/CRLF, BOM hay trailing spaces không? |
| Console encoding | Quan sát | Quan sát | Quan sát | Hiển thị Unicode có thể khác, **không thay assertion bằng việc nhìn console**. |
| Path/temporary files | Chạy | Chạy | Chạy | Dùng `Path.of`/`Files.createTempFile`; tránh hardcode slash/backslash theo OS. |

Lệnh chạy các ví dụ:

~~~bash
javac -encoding UTF-8 --release 17 CrossPlatformTextBlockDemo.java
java CrossPlatformTextBlockDemo

javac -encoding UTF-8 --release 17 FinalNewlineTestDemo.java
java FinalNewlineTestDemo

javac -encoding UTF-8 --release 17 WhitespaceEscapeTestDemo.java
java WhitespaceEscapeTestDemo

javac -encoding UTF-8 --release 17 LineEndingNormalizationDemo.java
java LineEndingNormalizationDemo

javac -encoding UTF-8 --release 17 WriteStringRoundTripDemo.java
java WriteStringRoundTripDemo

javac -encoding UTF-8 --release 17 WriteLinesPlatformDemo.java
java WriteLinesPlatformDemo

javac -encoding UTF-8 --release 17 WhitespaceVisualizerDemo.java
java WhitespaceVisualizerDemo

javac -encoding UTF-8 --release 17 CrossPlatformAssertionsDemo.java
java CrossPlatformAssertionsDemo
~~~

Mỗi ví dụ đặt trong **tệp riêng**, tên tệp trùng `public class` được nêu. Không cần chạy file `.java` bằng một đường dẫn tuyệt đối kiểu Windows hoặc Linux; chỉ cần đứng tại thư mục chứa tệp khi thực hiện lệnh.

Nếu dùng CI matrix, có thể chạy cùng các lệnh trong job Linux/Windows/macOS. Khi kiểm tra riêng hành vi hệ điều hành, **đừng ép biến `line.separator` trong một JVM rồi suy luận rằng đã tái hiện toàn bộ Windows**: OS còn khác ở file system, quyền, locale, shell và cấu hình I/O. Matrix thật vẫn cần thiết khi sản phẩm hỗ trợ đa nền tảng.

## 16. Những bẫy không nên nhầm với lỗi text block

### 16.1. Mẫu JSON không đồng nghĩa JSON hợp lệ

Một text block chứa JSON trông đẹp nhưng Java **không tự parse JSON**. Nếu thêm dữ liệu người dùng bằng phép nối chuỗi, bạn vẫn phải escape JSON bằng serializer phù hợp. Text block chỉ là cách khai báo `String`, không phải JSON builder an toàn.

### 16.2. SQL không tự an toàn khi đặt trong text block

Text block làm câu SQL dễ đọc hơn, nhưng dữ liệu động vẫn nên truyền bằng **prepared statements/parameters**. Không nối raw input vào SQL rồi cho rằng chữ `"""` làm giảm SQL injection.

### 16.3. Console không phải bằng chứng bytes

`System.out.println(text)` có thể thêm **line separator của hệ điều hành** sau nội dung. Nếu text đã có LF cuối, console có thể hiển thị thêm một dòng trống hoặc có hai kiểu newline liên tiếp. Kiểm thử bằng `String.equals` hoặc file bytes, không suy ra từ mắt nhìn console. Đặc biệt, `System.out.println` thêm separator do `PrintStream` theo cấu hình; hành vi này **tách biệt** với text block.

### 16.4. Path separator khác line separator

`Path.of("data", "expected.txt")` để Java xử lý đường dẫn đúng hệ điều hành. `System.lineSeparator()` để lấy dấu xuống dòng của môi trường; `File.separator` hay dấu `/`, `\` trong path **không liên quan** tới LF/CRLF trong nội dung file. Đừng dùng `replace("\\", "/")` lên dữ liệu text chỉ để “chạy trên Linux”.

### 16.5. Compiler và thời điểm chuẩn hóa

Text blocks xử lý line endings **lúc biên dịch nguồn thành chuỗi**, không phải khi mọi đối tượng `String` được tạo. Chuỗi nhận qua network, đọc file, environment variable hay tham số dòng lệnh không tự được text-block-normalize.

### 16.6. Dòng trống và `String.lines()`

`String.lines()` bỏ line terminators và không tạo dòng rỗng mới chỉ vì chuỗi kết thúc bằng newline. Nếu cần biết `"A\n"` khác `"A"`, dùng `equals`/`endsWith` hoặc bytes, không chỉ đếm dòng.

### 16.7. Ký tự Unicode vô hình

BOM, zero-width characters, nonbreaking space và các dạng tổ hợp dấu Unicode có thể gây khác biệt dù người xem thấy giống nhau. Khi kiểm thử giá trị nhạy cảm với ký tự, **ghi rõ dãy code points hoặc byte encoding**; không tự gọi `Normalizer.normalize` hoặc `strip` nếu hợp đồng không cho phép.

## 17. Checklist chẩn đoán khi bài test chỉ lỗi trên một OS

| Câu hỏi | Cách kiểm chứng |
| --- | --- |
| String được tạo từ text block hay đọc từ file? | Lần theo nơi tạo giá trị. Text block được compiler chuẩn hóa; file không tự được như vậy. |
| Nguồn `.java` dùng LF hay CRLF? | Kiểm tra file nguồn/CI/Git nếu cần; text block sẽ chuẩn hóa nội dung. |
| Fixture file có CRLF thật không? | Dùng `Files.readAllBytes` hoặc kiểm tra `indexOf('\r')` sau đọc. |
| Test có vô tình so `System.lineSeparator()` với LF của text block không? | Xem lại `expected` theo hợp đồng text block. |
| `Files.writeString` hay `Files.write(lines)` được gọi? | API trước ghi nguyên chuỗi; API sau thêm platform separator mỗi dòng. |
| Có newline cuối hay dòng trống đầu không? | Dùng `startsWith("\n")`, `endsWith("\n")` và so nguyên chuỗi. |
| Có tab, trailing space, CR hoặc ký tự Unicode lạ không? | Dùng hàm hiển thị whitespace hoặc byte/code-point dump an toàn. |
| Charset có thống nhất không? | Chỉ định `UTF_8` khi đọc/ghi file và `-encoding UTF-8` cho compiler. |
| Git/editor có đổi newline của fixture không? | Kiểm tra `.gitattributes`, policy formatter và bytes của file thực. |
| Bài test đang kiểm tra bytes hay nội dung logic? | Chỉ normalize khi contract cho phép; không bỏ qua lỗi của file bắt buộc chính xác. |
| Chỉ console hiển thị khác? | So `equals`/bytes trước khi kết luận chương trình tạo dữ liệu khác. |
| Cần kiểm thử nhiều OS thật không? | Chạy matrix nếu API, đường dẫn, bộ nhớ, locale hoặc công cụ ngoài phụ thuộc OS. |

Nếu test fail, nên ghi lại **input giả không nhạy cảm**, loại phép so sánh, expected/actual lengths, ký tự đầu tiên khác nhau và OS/JDK/charset. Sau khi tìm nguyên nhân, sửa **đúng tầng**: mã nguồn, cấu hình Git, API ghi file, giá trị kỳ vọng hoặc chính sách normalize.

## 18. Bài tập có đáp án định hướng

### Bài 1 — Đoán chính xác nội dung text block

~~~java
String s = """
    red
      blue
    """;
~~~

Đáp án: `"red\n  blue\n"`. Có hai dấu cách trước `blue` và LF cuối, không có LF đầu. Giải thích theo thứ tự normalization → incidental indentation → escape.

### Bài 2 — Vì sao hai test đếm dòng vẫn PASS?

Một giá trị `"A\nB\n"` và một giá trị `"A\nB"` cùng có `lines().count() == 2`. Viết assertion dùng `endsWith("\n")` hoặc `equals` để nhận diện khác biệt. Đáp án: phương thức `lines` không tạo thêm dòng rỗng phía sau separator cuối.

### Bài 3 — Test Windows fixture trên Linux

Fixture đọc được là `"A\r\nB\r\n"` còn text block kỳ vọng là `"A\nB\n"`. Nếu hợp đồng cho phép LF/CRLF tương đương, dùng `normalizeToLf` rồi so; nếu hợp đồng quy định LF cố định, **không normalize**, trả lỗi đúng để sửa fixture.

### Bài 4 — File UTF-8 vẫn có CRLF?

Dù đọc/ghi bằng `StandardCharsets.UTF_8`, một file vẫn có thể chứa bytes `0D 0A` vì **charset** quy định encoding ký tự, **không đồng nghĩa quy định line separator**. Hãy chỉ ra API viết file và nội dung đầu vào để giải thích nguồn CRLF.

### Bài 5 — Dấu cách cuối dòng

Tạo text block có giá trị `"X \n"`, gồm một dấu cách sau `X`. Dùng `\s` rồi viết assertion `equals("X \n")`. Không dùng `trim` để so vì nó xóa đúng ký tự cần kiểm tra.

### Bài 6 — File round-trip

Dùng `Files.writeString` với UTF-8 ghi text block chứa tiếng Việt và LF. Đọc lại bằng `Files.readString`, so chuỗi và bytes; xóa file tạm sau test. Giải thích vì sao phải dùng đúng API và charset thay vì chỉ quan sát console.

### Bài 7 — Thiết kế test cho hai mục đích

Nêu hai phép kiểm tra cho cùng file:
- **Logic content:** nếu hợp đồng cho phép, chuẩn hóa newline rồi so `String`.
- **Exact artifact:** so `Files.readAllBytes` với expected UTF-8 bytes.

Giải thích tại sao không được dùng kết quả kiểm tra logic để tuyên bố bytes đã chính xác.

### Bài 8 — Chạy CI nhiều OS

Thiết kế matrix Windows/Linux/macOS dùng cùng JDK LTS còn hỗ trợ và cùng lệnh build/test. Nếu chỉ một OS fail, thu thập cách ghi file, separator, charset, bytes fixture, không vội bỏ assertion. Nêu rõ test kỳ vọng **giống nhau** hay **khác nhau được phép** giữa các OS.

## 19. Nguồn tham khảo chính thức, còn áp dụng

1. [JLS 25 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy tắc chuẩn hóa line terminators, xử lý incidental whitespace và escape theo đúng thứ tự.
2. [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): giải thích LF/CRLF đa nền tảng, tab/space, trailing whitespace, `\s` và ví dụ thực tế.
3. [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng text blocks chính thức từ Java 15 và yêu cầu thiết kế về tính dễ đọc, ổn định.
4. [Java SE 25 API — `String.lines()`, `stripIndent()`, `indent()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): ý nghĩa dòng, các phép xử lý whitespace và ảnh hưởng tới line endings.
5. [Java SE 25 API — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `write` với danh sách dòng, `readAllLines` và `readAllBytes`.
6. [Java SE 25 API — `System.lineSeparator()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#lineSeparator()): separator phụ thuộc hệ thống, cần dùng theo hợp đồng output, không nhầm với LF của text block.
7. [Java SE 25 API — `StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html#UTF_8): định danh charset UTF-8 chuẩn, giúp ghi/đọc file một cách tường minh.

**Ghi nhớ:** source text block có thể mang LF/CRLF/CR tùy máy nhưng **giá trị `String` được compiler chuẩn hóa về LF**. File đọc và file xuất không tự động mang cùng quy tắc: `readString` giữ separators thật trong file, `writeString` ghi nguyên chuỗi, còn `write(lines)` dùng separator nền tảng. Kiểm thử tốt phải chọn **so chính xác hay so sau chuẩn hóa** theo hợp đồng, xác định UTF-8 và kiểm tra đầy đủ dấu cách, tab, dòng trống cùng newline cuối.