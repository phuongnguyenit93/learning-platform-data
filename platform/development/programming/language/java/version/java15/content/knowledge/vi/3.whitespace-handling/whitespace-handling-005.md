# Khoảng trắng cuối dòng và dữ liệu bị loại bỏ trong Java 15

> **Phạm vi:** Bài học thuộc chủ đề **Khoảng trắng** của Java 15. Tập trung vào cách Java xử lý khoảng trắng cuối dòng khi tạo `String` bằng **text block** (`"""`), vì sao dữ liệu trông như có trong mã nguồn có thể không còn trong chuỗi thực tế, và cách bảo toàn dữ liệu khi khoảng trắng là một phần của yêu cầu. Chỉ sử dụng cú pháp/API vẫn còn áp dụng trên Java hiện đại (Java 17+); không cần tính năng preview hay API đã lỗi thời.

## 1. Khoảng trắng cuối dòng là gì và vì sao nó có thể là dữ liệu?

**Trailing whitespace** là ký tự khoảng trắng xuất hiện **sau ký tự nội dung cuối cùng nhưng trước dấu xuống dòng**. Ví dụ: dấu cách U+0020 hoặc tab U+0009 nằm sau chữ `A` trong một dòng văn bản.

Để nhìn thấy thứ vốn vô hình, các sơ đồ trong bài dùng:

- `·`: một dấu cách U+0020 (ký hiệu minh họa, không phải ký tự thực của dữ liệu).
- `⇥`: một tab.
- `⏎`: kết thúc dòng (thường biểu diễn bằng ký tự LF, `\n`).

~~~text
A···⏎
B⏎
~~~

Chuỗi trên có **ba dấu cách sau A**. Nó khác với:

~~~text
A⏎
B⏎
~~~

Dù trông gần giống nhau khi hiển thị, hai chuỗi khác nhau về độ dài, nội dung byte và kết quả `String.equals()`. Khi tính chữ ký số, so sánh dữ liệu nguyên văn, tạo nội dung theo độ rộng cố định hoặc Markdown sử dụng hai dấu cách trước xuống dòng để xuống hàng, việc mất trailing spaces có thể đổi ý nghĩa.

**Lưu ý phạm vi:** Java không tự động xóa khoảng trắng trong mọi `String`. Hiện tượng chính của bài là **quá trình biên dịch text block**; ngoài ra, một số phương thức xử lý chuỗi chỉ xóa khoảng trắng khi **chúng được gọi tường minh**.

## 2. Cơ chế chính thức của text block từ Java 15

JEP 378 chuẩn hóa text blocks trong **JDK 15**. Text block dùng dấu `"""` để viết chuỗi nhiều dòng mà không phải nối hàng loạt chuỗi con:

~~~java
String message = """
        hello
        world
        """;
~~~

Giá trị là `"hello\nworld\n"`. Khoảng thụt lề để căn code ở bên trái đã bị loại bỏ; dấu xuống dòng sau `world` được giữ vì dấu đóng `"""` nằm ở dòng kế tiếp.

Java xử lý **nội dung của text block trong lúc biên dịch** theo thứ tự sau:

1. **Chuẩn hóa kết thúc dòng:** CRLF (`\r\n`) và CR (`\r`) trong phần nội dung nguồn được chuẩn hóa thành LF (`\n`).
2. **Loại bỏ incidental whitespace:** Xóa phần thụt lề chung không cần thiết ở đầu các dòng và **xóa khoảng trắng cuối từng dòng**. Việc này có ý nghĩa để biên tập viên mã nguồn tự dọn khoảng trắng không âm thầm thay đổi nội dung `String`.
3. **Diễn giải escape:** Sau khi hoàn thành hai bước trên, Java mới chuyển các escape như `\s`, `\t`, `\n`, `\r` hoặc `\040` thành ký tự thực.

**Thứ tự là mấu chốt:** dấu cách bạn gõ trực tiếp ở cuối dòng nguồn text block có thể biến mất tại bước 2; còn `\s` vẫn tồn tại dưới dạng hai ký tự nguồn (backslash và `s`) đến bước 3, khi nó trở thành một dấu cách thật.

| Viết trong text block | Giá trị cuối cùng | Giải thích |
| --- | --- | --- |
| `A` rồi xuống dòng | `"A\n"` | LF được giữ |
| `A` rồi ba dấu cách nguồn, sau đó xuống dòng | `"A\n"` | Ba dấu cách cuối dòng bị loại |
| `A\s\s\s` rồi xuống dòng | `"A   \n"` | Ba dấu cách được thêm sau bước loại bỏ whitespace |
| `A\040` rồi xuống dòng | `"A \n"` | Escape bát phân biểu diễn dấu cách |
| `A\` ngay trước xuống dòng | `"A"` nếu đây là dòng cuối | Escape nối dòng làm mất LF tại vị trí ấy |

**Phân biệt hai nhóm khác nhau:** *leading indentation* được xác định theo thụt lề chung/đóng delimiter; còn *trailing whitespace* bị xóa ở cuối **từng dòng**. Dịch vị trí `"""` đóng có thể đổi độ thụt lề được giữ, nhưng không phải cách đáng tin để bảo toàn dấu cách cuối dòng.

## 3. Ví dụ đầy đủ: ba dấu cách bị mất, rồi được giữ lại bằng `\s`

Tạo tệp **TrailingWhitespaceDemo.java** bằng UTF-8 và dùng Java 17+:

~~~java
public class TrailingWhitespaceDemo {
    static String show(String value) {
        return value
                .replace(" ", "·")
                .replace("\t", "⇥")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String block = """
                A   
                B
                """;
        String safe = """
                A\s\s\s
                B
                """;
        String regular = "A   \nB\n";
        String external = "  A   \n  B \n";
        String singleLine = """
                Hello\
                """;
        String joined = """
                Hello \
                world
                """;

        System.out.println("block=" + show(block));
        System.out.println("safe=" + show(safe));
        System.out.println("regular=" + show(regular));
        System.out.println("stripIndent=" + show(external.stripIndent()));
        System.out.println("stripTrailing=" + show(external.stripTrailing()));
        System.out.println("singleLine=" + show(singleLine));
        System.out.println("joined=" + show(joined));
        System.out.println("endsNewline=" + block.endsWith("\n"));
        System.out.println("exactSafe=" + safe.equals(regular));
    }
}
~~~

**Chi tiết quan trọng của ví dụ:** Ở dòng `A` bên trong text block `block`, mã nguồn cố ý có **ba dấu cách thật ngay sau chữ A**. Chúng vô hình trong nhiều giao diện đọc code; một số trình soạn thảo tự xóa chúng khi lưu. Dù còn trong tệp nguồn trước khi biên dịch, Java vẫn loại bỏ chúng. Trong `safe`, ba dấu `\s` thể hiện rõ ý định phải giữ ba dấu cách.

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 TrailingWhitespaceDemo.java
java TrailingWhitespaceDemo
~~~

Kết quả (ký tự `\n` trong kết quả là **hai ký tự hiển thị**, không phải xuống dòng thật):

~~~text
block=A\nB\n
safe=A···\nB\n
regular=A···\nB\n
stripIndent=··A\n··B\n
stripTrailing=··A···\n··B
singleLine=Hello
joined=Hello·world\n
endsNewline=true
exactSafe=true
~~~

**Giải thích từng kết quả:**

- `block`: không còn ba dấu cách cuối dòng `A`; text block vẫn có LF sau `A` và `B`.
- `safe`: vẫn có đúng ba dấu cách sau `A` vì dùng `\s\s\s`. Vì vậy `safe.equals(regular)` trả về `true`.
- `regular`: chuỗi thường `"A   \nB\n"` giữ các dấu cách thật trong literal; Java **không** áp dụng quy tắc strip incidental whitespace của text block cho chuỗi thường.
- `external.stripIndent()`: xóa trailing spaces của từng dòng; tuy nhiên hai dấu cách **đầu dòng** vẫn còn trong ví dụ này vì chuỗi kết thúc bằng `\n` làm độ thụt lề chung được xét là 0. Không nên mặc định rằng `stripIndent()` luôn xóa hết leading spaces.
- `external.stripTrailing()`: chỉ loại whitespace **ở cuối toàn bộ chuỗi**, gồm dấu xuống dòng cuối và dấu cách ngay trước nó nếu có; nó **không** xóa ba dấu cách ở dòng `A` nằm giữa chuỗi.
- `singleLine` và `joined` minh họa escape nối dòng `\`. `Hello \` có một dấu cách nguồn ngay trước dấu `\` nên kết quả ghép là `Hello world\n`; escape nối dòng loại bỏ LF, còn dấu cách trước `\` không nằm cuối dòng theo quy tắc stripping.
- `endsNewline=true`: text block có delimiter đóng ở dòng mới nên giá trị còn LF cuối.

Hàm `show` chỉ phục vụ quan sát. Khi phải so sánh dữ liệu tùy ý, `replace(" ", "·")` không phải mã hóa không mất thông tin nếu chuỗi gốc đã chứa `·`; hãy kiểm tra độ dài, code point hoặc bytes khi cần độ chính xác tuyệt đối.

## 4. Cách giữ chính xác khoảng trắng cuối dòng

### 4.1. Ưu tiên `\s` để biểu diễn dấu cách có chủ đích

`\s` là escape hiện hành của ngôn ngữ Java, tạo ra **đúng một** dấu cách U+0020:

~~~java
String padded = """
        code\s\s
        next
        """;

boolean correct = padded.equals("code  \nnext\n"); // true
~~~

Đây là cách dễ đọc, thể hiện rõ khoảng trắng có ý nghĩa và không phụ thuộc việc IDE tự dọn trailing whitespace.

Một dạng khác cũng hợp lệ:

~~~java
String padded = """
        code \s
        next
        """;
~~~

Ở dòng `code \s`, một dấu cách thật trước `\s` **không còn ở cuối dòng nguồn** vì ngay sau nó còn escape; vì vậy chuỗi kết quả có hai dấu cách. Dù hợp lệ, nhiều ký tự `\s` liên tiếp thường giúp người đọc kiểm tra số lượng dễ hơn.

### 4.2. Escape bát phân `\040` khi cần

~~~java
String value = """
        A\040\040\040
        """;

System.out.println(value.equals("A   \n")); // true
~~~

`\040` là mã escape bát phân của U+0020. Nó vẫn được Java hỗ trợ; có thể gặp trong mã nguồn cũ hoặc khi cần xác định ký tự theo giá trị, nhưng `\s` thường dễ hiểu hơn khi mục đích chỉ là dấu cách.

**Không dùng `\u0020` để né stripping trong text block.** Unicode escape được xử lý sớm hơn giai đoạn nhận diện string literal, nên cuối cùng nó có thể trở thành một dấu cách nguồn bị loại ở bước strip. `\s` và `\040` được diễn giải muộn hơn.

### 4.3. Chuỗi thường hoặc dữ liệu ngoài mã nguồn khi cần đúng từng byte

Nếu cần một payload tuyệt đối chính xác về dấu cách, dấu tab, LF/CRLF hoặc ký tự điều khiển, biểu diễn tường minh thường an toàn hơn:

~~~java
String payload = "A   \r\nB\t\r\n";
~~~

Ở đây `\r\n` biểu diễn CRLF chủ đích, `\t` biểu diễn tab; không có bước chuẩn hóa ngầm của text block áp dụng cho phần nội dung này.

Đối với mẫu văn bản dài phải được giữ nguyên byte (test fixture, tệp ký số, bản tin giao thức, định dạng có dấu cách cột cố định), cân nhắc đặt nội dung trong **tệp tài nguyên** và đọc bytes qua `Files.readAllBytes(path)` thay vì nhúng vào text block. Khi chuyển bytes sang `String` hoặc ngược lại, chỉ định encoding phù hợp, thường là UTF-8.

**Bảo toàn cuối dòng khác với bảo toàn byte:** text block luôn là `String` (chuỗi ký tự Java) và CRLF/CR nguồn được chuẩn hóa thành LF. Ngay cả khi đã bảo toàn mọi dấu cách bằng `\s`, text block vẫn không phải bản sao byte-for-byte của tệp nguồn CRLF.

## 5. Dấu cách cuối dòng khác với ký tự xuống dòng cuối cùng

Hai thứ này dễ bị nhầm:

- `A···⏎`: ba **dấu cách** đứng ngay trước ký tự xuống dòng.
- `A⏎`: có newline nhưng không có dấu cách cuối dòng.
- `A`: không có newline cuối.

Text block có thể quyết định có giữ **newline cuối cùng** bằng vị trí dấu đóng `"""` hoặc escape nối dòng:

~~~java
String withFinalNewline = """
        done
        """;

String withoutFinalNewline = """
        done\
        """;

System.out.println(withFinalNewline.equals("done\n"));  // true
System.out.println(withoutFinalNewline.equals("done"));  // true
~~~

Cách đặt dấu đóng trên cùng dòng nội dung cũng có thể bỏ newline cuối:

~~~java
String withoutFinalNewline = """
        done""";
~~~

Tuy nhiên nên chọn cách dễ đọc, phù hợp style của dự án. `\` ngay trước line terminator làm **nối hai dòng**; đây là công cụ điều khiển newline, **không** phải escape thay thế cho `\s` dùng để giữ dấu cách.

Trong một bản tin mạng hoặc một test có so sánh chính xác chuỗi, `"done"` và `"done\n"` khác nhau. Đừng tự thêm hoặc bỏ newline cuối mà chưa xác định yêu cầu dữ liệu.

## 6. `stripIndent()` và `stripTrailing()`: mất dữ liệu khi gọi ở runtime

Java hiện đại có những phương thức hữu ích nhưng phải hiểu tác dụng:

| Phương thức | Tác động chính | Nguy cơ với dữ liệu cần bảo toàn |
| --- | --- | --- |
| `String.stripIndent()` (Java 15+) | Chuẩn hóa line terminators, bỏ incidental indentation và trailing whitespace trên **mỗi dòng** | Có thể xóa dấu cách có nghĩa ở dòng nằm giữa chuỗi; không sử dụng trên dữ liệu nguyên văn |
| `String.stripTrailing()` (Java 11+) | Bỏ whitespace ở **cuối toàn bộ chuỗi** | Có thể làm mất newline cuối hoặc dấu cách cuối payload |
| `String.stripLeading()` (Java 11+) | Bỏ whitespace ở **đầu toàn bộ chuỗi** | Có thể làm mất phần thụt lề bắt đầu tài liệu |
| `String.strip()` (Java 11+) | Bỏ whitespace ở cả hai đầu toàn bộ chuỗi | Có thể làm mất khoảng trắng hoặc newline ở biên |
| `String.lines()` (Java 11+) | Trả stream các dòng **không kèm ký tự kết thúc dòng** | Khi ghép lại phải chủ động quyết định newline; không phù hợp để bảo toàn nguyên trạng line endings |

Ví dụ:

~~~java
String original = "A   \nB\n";
System.out.println(original.stripIndent().equals("A\nB\n"));  // true
System.out.println(original.stripTrailing().equals("A   \nB")); // true
~~~

Điểm dễ quên: sau khi dùng `\s` để giữ trailing spaces trong text block, nếu **tiếp tục gọi `stripIndent()` trên `String` đã tạo**, các dấu cách đó có thể lại bị xóa. Bảo toàn ở **thời điểm biên dịch** không đồng nghĩa bảo toàn qua mọi phép biến đổi **lúc chạy**.

Với `stripIndent()`, số ký tự thụt lề bị bỏ phụ thuộc quy tắc tìm mức indent nhỏ nhất; dòng cuối trống cũng ảnh hưởng. Đặc biệt khi một chuỗi truyền vào kết thúc bằng line terminator, nó có dòng cuối trống với indent 0, nên thụt lề đầu các dòng không nhất thiết bị loại như bạn nghĩ. Đừng dùng phương thức này như một hàm “xóa mọi khoảng trắng” hoặc áp dụng bừa lên đầu vào cần giữ chính xác.

## 7. Dấu tab, CRLF, Markdown và dữ liệu có độ rộng cố định

### Tab và space không tương đương

Ký tự tab `\t` chỉ là **một ký tự**, dù trình soạn thảo có thể vẽ nó rộng bằng nhiều cột. Trong phép tính incidental indentation của text blocks, Java không thay tab bằng tám dấu cách; trộn tab và space trong thụt lề có thể khiến nội dung căn cột ngoài dự kiến. Nếu định dạng yêu cầu độ rộng cột ổn định, hãy quy định cụ thể dấu cách và test giá trị đã tạo.

### CRLF bị chuẩn hóa trong phần nội dung text block

Một tệp `.java` lưu bằng CRLF có thể chứa text block mà tại runtime các dấu kết thúc dòng của text block là LF. Đây là hành vi có chủ đích của ngôn ngữ, không phải lỗi encoder. Nếu tích hợp yêu cầu CRLF, hãy tạo `\r\n` có chủ đích ở bước định dạng đầu ra và kiểm tra kết quả. Không suy ra định dạng byte trên disk từ giao diện text block trong editor.

### Markdown, mẫu thư và nội dung ký số

Ví dụ trong nhiều biến thể Markdown, hai dấu cách cuối dòng thể hiện **hard line break**. Một text block ghi hai dấu cách nguồn ở cuối dòng sẽ mất chúng nếu không dùng escape:

~~~java
String markdown = """
        First line\s\s
        Second line
        """;
~~~

Giá trị `markdown` chứa `"First line  \nSecond line\n"` như mong muốn. Khi dùng template để ký hoặc so sánh checksum, chỉ một dấu cách khác đi cũng làm dữ liệu không còn khớp. Nếu định dạng cho phép, nên xây dựng dữ liệu từ object bằng serializer có quy tắc rõ ràng, hoặc giữ fixture dưới dạng tài nguyên, thay vì phụ thuộc vào khoảng trắng không nhìn thấy trong nguồn.

## 8. Phát hiện khoảng trắng bị loại bằng compiler và kiểm thử

### Cảnh báo ngay khi biên dịch

Trình biên dịch `javac` hỗ trợ cảnh báo cho text blocks:

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:text-blocks TrailingWhitespaceDemo.java
~~~

Ví dụ ở mục 3 với ba dấu cách thật sau `A` sẽ sinh cảnh báo thuộc nhóm `[text-blocks]`, nội dung tương tự **`trailing white space will be removed`**. Đây là dấu hiệu mạnh cho thấy các khoảng trắng có trong file nguồn sẽ bị bỏ đi, nhưng không thể thay thế test nội dung đích.

### Test nội dung thực, không chỉ nhìn code

Đối với khoảng trắng có ý nghĩa, hãy kiểm thử `String.equals()` với giá trị kỳ vọng tường minh; nếu cần byte chính xác, dùng phép so sánh `byte[]` theo encoding đã xác định:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String expected = "A   \nB\n";
String actual = """
        A\s\s\s
        B
        """;

if (!expected.equals(actual)) {
    throw new AssertionError("String content changed");
}

byte[] expectedBytes = expected.getBytes(StandardCharsets.UTF_8);
byte[] actualBytes = actual.getBytes(StandardCharsets.UTF_8);
if (!Arrays.equals(expectedBytes, actualBytes)) {
    throw new AssertionError("UTF-8 bytes changed");
}
~~~

Đây là **đoạn code minh họa đặt trong phương thức**, với các `import` cần thiết; không phải chương trình độc lập chứa `main`. Trong dự án có JUnit, thay các phép `if` bằng assertion tương ứng. Đừng dựa vào `System.out.println` thông thường vì nó không làm hiện rõ những dấu cách ở cuối dòng. Có thể dùng hàm `show` như ví dụ ở mục 3 hoặc in giá trị từng byte bằng API phù hợp.

**Một bẫy khác:** escape Java `\s` là **một dấu cách literal**, không phải mẫu regex “mọi whitespace”. Nếu viết regex Java để nhận diện khoảng trắng, cần truyền dấu backslash đến regex engine:

~~~java
String oneSpace = "\s";       // chuỗi chứa một U+0020
String regexWhitespace = "\\s+"; // regex \s+ tới Pattern
~~~

Không nhầm hai cấp escape này khi kiểm tra hoặc làm sạch dữ liệu.

## 9. Quy trình chọn giải pháp trong dự án

1. **Xác định hợp đồng dữ liệu:** khoảng trắng cuối dòng và newline cuối có được phép mất hay phải giữ nguyên? Với JSON/SQL để đọc trong code, whitespace cuối dòng thường không mang nghĩa; với fixed-width, chữ ký, Markdown hoặc fixture nguyên văn thì có thể mang nghĩa.
2. **Chọn kiểu biểu diễn:** text block cho nội dung nhiều dòng dễ đọc; dùng `\s` tại chỗ cần trailing spaces; chuỗi thường/serializer/tệp tài nguyên khi cần kiểm soát byte chính xác.
3. **Tránh biến đổi phá dữ liệu:** không gọi `stripIndent()`, `stripTrailing()` hoặc `strip()` nếu chưa chứng minh việc mất whitespace là hợp lệ. Không dựa vào editor giữ trailing spaces trong file nguồn.
4. **Kiểm chứng kết quả:** so sánh chuỗi hoặc bytes bằng test có kỳ vọng tường minh; dùng `-Xlint:text-blocks` để phát hiện dấu cách nguồn sẽ bị loại, đo cả CRLF/LF và newline cuối khi có yêu cầu.
5. **Ghi quy ước vào code review:** nếu hai dấu cách cuối dòng là thiết yếu, nên dùng `\s\s` và comment ngắn về mục đích, để người sửa sau không vô tình làm mất dữ liệu.

## 10. Những lỗi thường gặp cần tránh

- **“Text block giữ nguyên mọi ký tự như hình trong editor.”** Sai: Java chuẩn hóa line endings và loại incidental whitespace.
- **“Không thấy dấu cách nên không thể có lỗi.”** Sai: dấu cách không hiển thị có thể ảnh hưởng equality, chữ ký, độ dài hoặc cách dựng tài liệu.
- **“Thêm ba dấu cách ở cuối dòng text block là đủ.”** Sai: những dấu đó bị loại ở bước xử lý text block; dùng `\s\s\s`.
- **“`\u0020` tương đương `\s` để giữ trailing spaces.”** Sai về thứ tự dịch escape của mã nguồn Java.
- **“`stripIndent()` chỉ chỉnh thụt lề.”** Sai: phương thức này còn loại bỏ trailing whitespace của từng dòng.
- **“`stripTrailing()` xóa trailing spaces trên mọi dòng.”** Sai: nó chỉ xóa từ cuối **toàn bộ chuỗi**.
- **“`\` cuối dòng và `\s` là cùng một loại escape.”** Sai: một cái nối dòng, một cái tạo dấu cách.
- **“Text block từ nguồn CRLF sẽ cho `\r\n` tại runtime.”** Sai: nội dung nguồn bị chuẩn hóa về LF; phải tạo CRLF có chủ đích nếu giao thức yêu cầu.
- **“`\s` trong Java string literal luôn biểu diễn lớp ký tự whitespace của regex.”** Sai: nó là U+0020; muốn regex `\s+` dùng `"\\s+"`.

## 11. Bài luyện tập có tiêu chí kiểm tra

**Bài 1 — Dữ liệu bị mất:** Viết text block hai dòng có ba dấu cách cuối dòng đầu tiên. Tạo một chuỗi thường `"A   \nB\n"` để so sánh với text block. Dự đoán `equals`, chạy chương trình và lý giải vì sao giá trị khác nhau. **Đạt** khi chỉ đúng giai đoạn loại bỏ trailing spaces trong text block.

**Bài 2 — Bảo toàn:** Sửa text block của bài 1 bằng `\s\s\s` và so sánh lại bằng `equals`. **Đạt** khi hai chuỗi bằng nhau và không cần tính năng preview.

**Bài 3 — Newline cuối:** Tạo một text block có LF cuối và một text block không có LF cuối (dùng `\`), rồi kiểm tra bằng `endsWith("\n")`. **Đạt** khi giải thích được sự khác biệt giữa “dấu cách cuối dòng” và “newline cuối chuỗi”.

**Bài 4 — Mất dữ liệu ở runtime:** Gọi `stripIndent()` lên chuỗi đã giữ khoảng trắng bằng `\s`. **Đạt** khi phát hiện trailing spaces có thể mất lần nữa; đề xuất giữ nguyên chuỗi hoặc chuẩn hóa một cách có chủ đích tùy hợp đồng dữ liệu.

**Bài 5 — Dữ liệu đúng từng byte:** Xây dựng payload `"A   \r\nB\r\n"` và đối chiếu byte UTF-8 với một dữ liệu kỳ vọng cùng encoding. **Đạt** khi chỉ ra vì sao nhúng thẳng nội dung CRLF bằng text block không đủ để đảm bảo giữ nguyên line endings.

## 12. Tài liệu chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng text blocks được chuẩn hóa ở Java 15, ba giai đoạn xử lý nội dung và escape.
- [Oracle Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): ví dụ chính thống về trailing whitespace, `\s`, `\040`, `-Xlint:text-blocks`, dấu xuống dòng cuối.
- [Oracle Java Language Updates — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): cú pháp và quy tắc xử lý indentation/trailing whitespace hiện hành.
- [Java SE 25 API — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): đặc tả `stripIndent()`, `stripTrailing()`, `stripLeading()`, `strip()` và `lines()`.

**Ghi nhớ:** Khoảng trắng chỉ “thừa” khi **hợp đồng dữ liệu** cho phép bỏ đi. Trong text block Java 15 trở đi, Java chủ động loại dấu cách cuối dòng nguồn để mã dễ bảo trì; khi dấu cách mang nghĩa, hãy biểu diễn nó tường minh bằng `\s`, chọn phương thức xử lý chuỗi đúng mục đích và kiểm thử giá trị thực tế.
