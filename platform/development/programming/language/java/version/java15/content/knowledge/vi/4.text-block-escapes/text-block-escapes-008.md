# Phân biệt ký tự thật trong dữ liệu với ký hiệu escape của Java text block

> **Ngữ cảnh:** Java 15 chuẩn hóa text block (JEP 378). Kiến thức về escape và dữ liệu chuỗi trong bài này vẫn áp dụng cho Java 17+ và các JDK hiện đại. Điều quan trọng nhất: **ký tự xuất hiện trong mã nguồn Java không nhất thiết là ký tự nằm trong `String` khi chạy**.

## 1. Hai cấp độ phải đọc riêng: mã nguồn và giá trị của chuỗi

Giả sử trong trình soạn thảo ta nhìn thấy `\n`. Có ít nhất hai cách hiểu rất khác nhau:

- **Ký hiệu escape ở mã nguồn Java:** `\n` trong một string literal hoặc text block biểu diễn **một ký tự xuống dòng LF**, có mã Unicode **U+000A**. Dấu gạch chéo ngược và chữ `n` chỉ là cách *viết* ký tự này trong source.
- **Hai ký tự dữ liệu thật:** một dấu gạch chéo ngược `\` (U+005C), tiếp theo là chữ `n` (U+006E). Muốn có đúng hai ký tự đó trong một literal Java, thông thường phải viết `\\n`.

Dấu xuống dòng **thực sự giữa hai dòng** trong phần nội dung text block cũng trở thành ký tự LF của `String` (sau chuẩn hóa dòng). Vì vậy, ký tự LF được tạo bởi hai cách viết khác nhau:

~~~java
// Hai đoạn minh họa bên trong phương thức; dấu đóng đặt cùng dòng cuối.
String physicalLine = """
        A
        B""";
String escapeLine = "A\nB";
~~~

Hai chuỗi trên **bằng nhau**: mỗi chuỗi gồm `'A'`, LF, `'B'`, tổng cộng **3 UTF-16 code units**. Ngược lại:

~~~java
String literalSlashN = "A\\nB";
~~~

`literalSlashN` gồm `'A'`, `'\\'`, `'n'`, `'B'`: **4 UTF-16 code units**; không có xuống dòng giữa A và B.

Bảng so sánh chính xác:

| Viết trong mã nguồn Java | Giá trị lúc chạy | `length()` |
| --- | --- | ---: |
| `"A\nB"` | Chữ A, **LF**, chữ B | 3 |
| `"A\\nB"` | Chữ A, **backslash**, chữ n, chữ B | 4 |
| Text block có A và B trên **hai dòng nguồn**, dấu đóng sau B | Chữ A, **LF**, chữ B | 3 |
| `"A\tB"` | A, **tab** (U+0009), B | 3 |
| `"A\\tB"` | A, **backslash**, chữ t, B | 4 |
| `"A\sB"` | A, **space** (U+0020), B | 3 |

**Lưu ý:** bảng biểu diễn *source* trong code span, không phải một hệ thống escape riêng của Markdown. Đặc biệt, nhìn thấy hai ký tự `\` + `n` khi hiển thị có thể chỉ là cách một logger/JSON serializer *biểu diễn* LF. Hãy xem giá trị thực hoặc mã ký tự để phân biệt.

## 2. Escape hoạt động trong text block như thế nào?

Text block được mở bằng ba dấu nháy kép `"""`, bắt buộc có dấu xuống dòng sau dấu mở, và tạo ra một `String` như literal `"..."` thông thường.

Quy trình biên dịch nội dung text block cần hiểu theo đúng thứ tự:

1. **Chuẩn hóa line terminator** trong phần nội dung về LF (`\n`), bất kể file nguồn được lưu với CRLF hay LF.
2. **Loại bỏ incidental indentation**: phần thụt lề phụ do text block được đặt sâu trong file Java, và phần trailing whitespace không được bảo vệ.
3. **Diễn giải escape sequence**: những tổ hợp như `\n`, `\t`, `\s`, `\\`, `\"` hoặc dấu `\` ngay trước một line terminator được chuyển thành ký tự/hiệu ứng tương ứng.

Thứ tự này rất quan trọng. Ví dụ, `\s` được giải mã **sau khi** Java loại trailing whitespace, nhờ đó có thể bảo toàn một dấu cách cuối dòng mà compiler sẽ loại nếu viết trực tiếp.

### Escape thông dụng, còn hợp lệ trên JDK hiện đại

| Escape trong source | Giá trị tạo ra | Trường hợp sử dụng |
| --- | --- | --- |
| `\n` | LF, U+000A | Xuống dòng do người viết biểu diễn bằng escape |
| `\r` | CR, U+000D | Dữ liệu thực sự đòi carriage return |
| `\t` | Tab ngang, U+0009 | Dữ liệu có tab |
| `\b` | Backspace, U+0008 | Ký tự điều khiển khi thật sự cần |
| `\f` | Form feed, U+000C | Ký tự điều khiển khi thật sự cần |
| `\"` | Dấu nháy kép `"` | Escape dấu nháy kép khi cần, đặc biệt khi có chuỗi dấu nháy liên tục |
| `\'` | Dấu nháy đơn `'` | Cho phép, nhưng thường không cần trong text block |
| `\\` | Một dấu gạch chéo ngược `\` | Đường dẫn, regex, JSON có escape |
| `\s` | Một dấu cách U+0020 | Giữ khoảng trắng cuối dòng có chủ ý |
| Dấu `\` ngay trước line terminator | **Không có** ký tự newline ở ranh giới đó | Nối các dòng nguồn thành một dòng dữ liệu |
| Một số dạng escape bát phân như `\040` | Ký tự ứng với giá trị bát phân | Có hỗ trợ; với nhu cầu giữ dấu cách, `\s` thường dễ hiểu hơn |

Không phải mọi tổ hợp gạch chéo ngược đều được chấp nhận: `\q` không phải escape hợp lệ trong Java và gây **lỗi biên dịch**. Việc text block chứa nhiều dòng không biến nó thành **raw string**.

### Ngoại lệ đáng nhớ: Unicode escape

Chuỗi ký tự dạng `\uXXXX` là cơ chế **Unicode escape ở bước xử lý nguồn Java trước khi phân tích token**, khác với các escape kể trên. Ví dụ, không nên dùng `\u000a` như một cách thay thế `\n` bên trong string literal: nó có thể biến thành dấu xuống dòng ở bước tiền xử lý nguồn và làm cú pháp Java sai. Khi cần LF trong dữ liệu chuỗi, dùng `\n` hoặc dòng thật trong text block. Khi dữ liệu đòi các ký tự `\`, `u`, `0`, ..., hãy xây dựng/escape chuỗi theo đúng hợp đồng của định dạng đích; đừng suy đoán từ cách nhìn trong IDE.

## 3. Một ký tự xuống dòng có thể được biểu diễn theo nhiều cách

Đặt cả hai đoạn dưới trong một phương thức Java:

~~~java
String sourceLine = """
        first
        second""";

String escapeLine = "first\nsecond";
boolean same = sourceLine.equals(escapeLine); // true
~~~

Ký tự LF trong `sourceLine` xuất phát từ **ranh giới dòng vật lý** của text block; LF trong `escapeLine` xuất phát từ **ký hiệu `\n`** trong mã nguồn. Nhưng giá trị cuối cùng bằng nhau.

Text block với dấu đóng trên **dòng riêng** thường có thêm LF cuối:

~~~java
String withFinalLf = """
        first
        second
        """;

boolean exact = withFinalLf.equals("first\nsecond\n"); // true
~~~

Dấu đóng ngay sau chữ `second` sẽ không thêm LF cuối dòng. Khi xác minh chuỗi, hãy luôn xem xét **LF giữa hai dòng** và **LF ở cuối** như hai điều kiện riêng.

### “Nhìn thấy `\n` trên console” chưa nói lên dữ liệu thật

Ví dụ:

~~~java
String actualLf = "A\nB";
String writtenSlashN = "A\\nB";
~~~

- `System.out.println(actualLf)` sẽ in A và B trên **hai dòng**.
- `System.out.println(writtenSlashN)` sẽ in **một dòng** có chữ `A\nB`.

Tuy nhiên, một API log hoặc trình xem JSON có thể *escape lại* LF thành chuỗi nhìn thấy `\n` để dễ đọc, dù dữ liệu ban đầu chứa ký tự LF thật. Muốn kiểm tra chắc chắn, đo `length()` và đọc `charAt`/`codePointAt` hoặc dùng một biểu diễn đã quy ước, thay vì tin hình thức hiển thị.

## 4. Backslash trong text block: viết gì để giá trị chứa đúng dấu `\`?

Đối chiếu ba đoạn (đặt trong một phương thức):

~~~java
String newline = """
        A\nB""";

String rawSlashN = """
        A\\nB""";

String physicalNewline = """
        A
        B""";
~~~

Kết quả:

- `newline` và `physicalNewline` đều là ba ký tự `A`, LF, `B`.
- `rawSlashN` chứa bốn ký tự `A`, backslash, `n`, `B`.
- `newline.equals(physicalNewline)` trả về `true`.
- `newline.equals(rawSlashN)` trả về `false`.

**Quy tắc thực hành:** muốn chèn một backslash **thật** vào chuỗi Java, hãy dùng `\\` trong mã nguồn, kể cả khi viết text block. Điều này đặc biệt quan trọng với đường dẫn Windows, regex, JSON escape và mã nguồn khác được nhúng dưới dạng văn bản.

Ví dụ đường dẫn Windows:

~~~java
String path = """
        C:\\work\\data.txt""";
~~~

Giá trị chứa các dấu `\` thực trước `work` và `data.txt`. Nếu viết `C:\work\data.txt`, một số tổ hợp có thể là escape Java hợp lệ với ý nghĩa khác, hoặc là escape không hợp lệ gây lỗi biên dịch.

## 5. JSON: dữ liệu escape qua **hai ngôn ngữ**

JSON và Java đều có quy tắc escape riêng, nhưng chúng xử lý ở **hai giai đoạn khác nhau**.

Mục tiêu: tạo một *văn bản JSON hợp lệ* chứa chuỗi JSON `"line1\nline2"`, trong đó JSON dùng hai ký tự `\` và `n` để biểu diễn newline trong giá trị trường.

~~~java
String jsonText = """
        {"message":"line1\\nline2"}""";
~~~

Giải thích theo hai tầng:

1. **Java biên dịch text block:** `\\` của Java trở thành **một backslash thật**. Giá trị `jsonText` là các ký tự của JSON text, trong đó còn tổ hợp `\n` **hai ký tự** ở vị trí giữa `line1` và `line2`.
2. **JSON parser xử lý văn bản JSON:** bên trong một JSON string, `\n` được hiểu là một ký tự newline trong **giá trị dữ liệu đã parse**.

Vì vậy, `jsonText.contains("\\n")` là `true`, nhưng `jsonText.contains("\n")` là `false` (ví dụ đặt dấu đóng cùng dòng, không có LF cuối).

### Sai khác gây JSON không hợp lệ

~~~java
String invalidJson = """
        {"message":"line1\nline2"}""";
~~~

Lúc này Java đã thay `\n` thành **LF thật bên trong cặp nháy JSON**. Theo cú pháp JSON, dấu xuống dòng điều khiển không được viết trực tiếp bên trong JSON string; văn bản này **không hợp lệ**.

### Khi nào nên dùng JSON serializer?

Text block phù hợp cho **JSON tĩnh** hoặc mẫu phục vụ học/test. Nếu dữ liệu đến từ người dùng hoặc chứa dấu nháy, backslash, ký tự điều khiển, **đừng ghép trực tiếp** thành JSON bằng `+` hay `formatted` mà không escape. Hãy dùng thư viện serializer JSON để nó thực hiện escaping theo đặc tả JSON. Escape của Java và escape của JSON không thay thế được nhau.

## 6. HTML, regex và source code có yêu cầu khác nhau

Một số ví dụ đối chiếu:

| Dữ liệu mong muốn lúc chạy | Viết trong Java text block | Lý do |
| --- | --- | --- |
| Hai ký tự backslash và n | `\\n` | Java cần escape backslash |
| Một dấu tab thật | `\t` hoặc tab thật trong nội dung | Cả hai tạo U+0009, nhưng tab thật gây khó kiểm tra thụt lề |
| Ba ký tự `\`, `d`, `+` để đưa vào regex engine | `\\d+` | Java giữ lại backslash; regex engine mới hiểu `\d` |
| Dấu nháy kép `"` trong HTML/JSON | `"` | Dấu nháy kép đơn thường dùng trực tiếp trong text block |
| Chuỗi dấu nháy có thể tạo `"""` trong nội dung | Escape một dấu phù hợp, chẳng hạn `\"""` | Tránh bị parser coi là dấu kết thúc text block |
| Dấu cách ở cuối dòng có chủ ý | `\s` sau ký tự cuối | Được thêm sau bước Java loại trailing whitespace |

Một thắc mắc thường gặp: HTML **không có** quy tắc “backslash trong Java text block tự thành HTML escape”. Ví dụ `&lt;` là HTML entity được xử lý theo quy tắc HTML; nó không phải escape của Java. Dữ liệu phải đi qua đúng parser ở đúng lớp.

Với regex, ngược lại, một dấu backslash ở runtime thường cần thiết vì regex engine dùng nó làm meta syntax; để có được dấu đó trong literal Java, mã nguồn phải escape thêm một tầng.

## 7. `\s`, khoảng trắng cuối dòng và nối dòng bằng `\`

### 7.1. Giữ dấu cách cuối dòng có chủ ý

Thông thường, trailing spaces trong phần text block sẽ bị loại khi compiler xử lý incidental whitespace. Muốn giữ một dấu cách ở cuối dòng, có thể dùng `\s`:

~~~java
String value = """
        A\s
        B""";

boolean correct = value.equals("A \nB"); // true
~~~

Dấu cách sau A không “vô tình còn sót” trong source; chính `\s` tạo ra một **ký tự space thật** sau khi bước strip trailing whitespace kết thúc. Điều này hữu ích trong dữ liệu có yêu cầu chính xác về độ rộng dòng. Không lạm dụng trailing spaces vì người đọc khó nhận ra chúng và nhiều công cụ sẽ tự xóa.

### 7.2. Nối hai dòng nguồn thành một dòng dữ liệu

Đặt `\` **ngay trước dấu kết thúc một dòng nguồn** để không đưa line terminator đó vào chuỗi:

~~~java
String joined = """
        Hello\
        World""";

boolean exact = joined.equals("HelloWorld"); // true
~~~

Đây là cú pháp escape ở mức Java: editor hiển thị **hai dòng**, nhưng giá trị chuỗi chỉ có **một dòng** và không tự thêm dấu cách. Nếu cần dấu cách giữa hai từ, hãy cung cấp ký tự space một cách có chủ đích. Đừng nhầm với ký hiệu `\n`, vì `\n` **tạo** LF, còn `\` trước line terminator **loại** LF.

### 7.3. Dấu nháy kép

Trong text block:

~~~java
String html = """
        <a href="https://example.org">Link</a>""";
~~~

Không cần escape những dấu `"` đơn lẻ. Nếu cần biểu diễn ba dấu nháy kép liên tục để tạo mã nguồn có text block bên trong, phải escape phù hợp để chúng không kết thúc text block ngoài. Quy tắc này vẫn là quy tắc của **mã nguồn Java**, không phải HTML hoặc JSON.

## 8. Chương trình Java chạy được: nhìn thấy các ký tự thật

Lưu mã sau thành file **`EscapeDataDemo.java`**:

~~~java
public class EscapeDataDemo {
    public static void main(String[] args) {
        String physicalLine = """
                A
                B""";

        String escapeLine = "A\nB";
        String literalSlashN = "A\\nB";

        System.out.println("equal LF: " + physicalLine.equals(escapeLine));
        System.out.println("equal slash-n: " + physicalLine.equals(literalSlashN));
        System.out.println("physical length: " + physicalLine.length());
        System.out.println("slash-n length: " + literalSlashN.length());
        System.out.println("physical middle code: " + (int) physicalLine.charAt(1));
        System.out.println("slash-n middle code: " + (int) literalSlashN.charAt(1));

        String withSpace = """
                x\s
                """;
        System.out.println("trailing space: " + withSpace.equals("x \n"));

        String joined = """
                Hello\
                World""";
        System.out.println("joined: " + joined.equals("HelloWorld"));

        String json = """
                {"message":"line1\\nline2"}""";
        System.out.println("JSON has slash-n: " + json.contains("\\n"));
        System.out.println("JSON has real LF: " + json.contains("\n"));

        String atRuntime = "\\n";
        System.out.println("translateEscapes length: "
                + atRuntime.translateEscapes().length());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac EscapeDataDemo.java
java EscapeDataDemo
~~~

**Stdout chính xác:**

~~~text
equal LF: true
equal slash-n: false
physical length: 3
slash-n length: 4
physical middle code: 10
slash-n middle code: 92
trailing space: true
joined: true
JSON has slash-n: true
JSON has real LF: false
translateEscapes length: 1
~~~

Những con số then chốt:

- **10** là mã thập phân của LF (U+000A).
- **92** là mã thập phân của backslash (U+005C).
- `translateEscapes()` là API của `String` (có từ Java 15) dùng để dịch một số escape nằm trong **dữ liệu chuỗi lúc chạy**. Nó **không phải** lệnh bật text block hay cơ chế tự động của mọi `String`. Với `"\\n"`, chuỗi lúc chạy dài 2; gọi `translateEscapes()` biến nó thành ký tự LF dài 1. Phương thức có thể ném ngoại lệ nếu escape text không hợp lệ, nên không dùng vô điều kiện trên dữ liệu người dùng.

Có thể kiểm tra biên dịch ở mức Java 15 bằng JDK còn hỗ trợ `--release 15`:

~~~bash
javac --release 15 EscapeDataDemo.java
~~~

Bài này không dùng tính năng preview và không phụ thuộc API đã lỗi thời.

## 9. Cách kiểm tra chuỗi khi debugger, log hoặc JSON hiển thị khác nhau

Giả sử một log ghi:

~~~text
A\nB
~~~

Không thể kết luận ngay giá trị Java thật có LF hay có hai ký tự `\`, `n`. Hãy thực hiện:

1. **Xác định lớp biểu diễn:** đây là nội dung trong source code, giá trị `String` lúc chạy, chuỗi JSON trên mạng hay màn hình log đã escape?
2. **Đếm và đọc mã ký tự:** `length()`, `charAt(i)`, `codePointAt(i)` (khi cần Unicode đầy đủ) giúp xác nhận byte/character theo mục tiêu. Với LF, giá trị số thường được dùng để kiểm tra là 10.
3. **So sánh với literal chính xác:** `value.equals("A\nB")` so với `value.equals("A\\nB")`.
4. **Kiểm tra parser thứ hai:** nếu string còn được đưa cho JSON parser, regex engine, SQL engine hoặc template engine, cần thêm một tầng diễn giải.
5. **Kiểm soát charset khi xét byte:** `String` là dữ liệu ký tự UTF-16 ở mức API; byte thực khi ghi file/truyền mạng phụ thuộc charset, ví dụ `getBytes(StandardCharsets.UTF_8)`. Không nhầm `String.length()` với kích thước byte UTF-8, đặc biệt với tiếng Việt hoặc emoji.

Một hàm hỗ trợ tự viết có thể hiển thị code point dưới dạng số/hex mà không phụ thuộc vào console đang escape như thế nào; tuy nhiên với các ví dụ ASCII và LF trong bài, `charAt` đã đủ để phân biệt.

## 10. Lỗi phổ biến và cách khắc phục

| Nhầm lẫn | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `\n` trong nguồn Java là hai ký tự lúc chạy | So sánh, độ dài và newline sai | Phân biệt source notation với runtime character; đo `length()` |
| Nghĩ text block là raw string | Backslash bị xử lý ngoài ý muốn | Dùng `\\` nếu muốn giữ một backslash thật |
| Nghĩ cứ nhìn thấy `\n` trong JSON log nghĩa là dữ liệu không xuống dòng | Đánh giá sai payload | Xác định tầng serialize/escape; kiểm tra dữ liệu trước hoặc sau khi parse |
| Viết `\n` của Java trực tiếp bên trong một JSON string rồi cho là JSON hợp lệ | LF thật khiến JSON string không hợp lệ | Viết `\\n` trong nguồn Java hoặc dùng JSON serializer |
| Trộn `\n` và dấu xuống dòng thực mà không tính LF cuối | Dư/thừa newline làm hỏng snapshot | Quyết định vị trí dấu đóng `"""` và test chuỗi chính xác |
| Giữ khoảng trắng cuối dòng bằng space vô hình | Compiler strip mất | Dùng `\s` khi thực sự cần trailing space |
| Dùng `\u000a` để tạo newline trong literal | Unicode escape xảy ra quá sớm, có thể phá source | Dùng `\n` hoặc line terminator thực trong text block |
| Nhầm `translateEscapes()` với cách đọc raw/JSON chuẩn | Dịch dữ liệu không có chủ đích hoặc gặp escape lỗi | Chỉ gọi khi hợp đồng dữ liệu thực sự yêu cầu cú pháp escape của Java |

## 11. Bài tập tự kiểm tra

**Bài 1.** Xác định độ dài:

~~~java
String a = "\n";
String b = "\\n";
String c = """
        X
        Y""";
~~~

**Đáp án:** `a.length() == 1`; `b.length() == 2`; `c.length() == 3`.

**Bài 2.** Vì sao `"A\nB"` và text block chứa A, B trên hai dòng có thể bằng nhau?

**Đáp án:** cả hai có cùng dữ liệu ký tự `A`, LF, `B`. Ký hiệu escape của source và ký tự thực ở dòng text block dẫn tới cùng giá trị `String`.

**Bài 3.** Muốn một JSON parser nhận `{"message":"A\nB"}` dưới dạng **văn bản JSON có backslash+n** ở vị trí giữa A và B, mã nguồn Java text block cần viết mấy backslash?

**Đáp án:** viết `\\n` trong source Java (hai backslash). Bước Java chuyển thành một backslash thật; bước JSON parser mới hiểu escape `\n`.

**Bài 4.** Hai câu sau có tương đương không: “`\n` tạo newline” và “`\` ở cuối dòng loại newline”?

**Đáp án:** **Không**. `\n` ở mã nguồn tạo ký tự LF trong giá trị; `\` ngay trước line terminator của text block nối hai dòng nguồn mà không đưa LF đó vào giá trị.

**Bài 5.** Một chuỗi được in bởi `System.out.print` nhưng debugger cho thấy `\\n`. Nó có newline thật không?

**Đáp án:** chưa đủ dữ kiện; debugger có thể đang hiển thị *biểu diễn escape*. Kiểm tra ký tự/mã số tại vị trí đó hoặc đối chiếu với literal mong đợi.

## 12. Tài liệu chuẩn có thể dùng lâu dài

- **JEP 378 — Text Blocks (hoàn thiện trong Java 15):** https://openjdk.org/jeps/378
- **Oracle — Programmer's Guide to Text Blocks:** https://docs.oracle.com/en/java/javase/25/language/text-blocks.html
- **Java Language Specification — Text Blocks & Escape Sequences:** https://docs.oracle.com/javase/specs/
- **Java SE API — `String.translateEscapes()`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html

**Nguyên tắc:** luôn phân biệt ba thứ — **cách viết trong file `.java`**, **các ký tự thực trong `String`**, và **cách một hệ thống khác serialize/hiển thị `String`**. Escape là cách biểu diễn ở một tầng; kết quả ở tầng sau phải được kiểm tra như dữ liệu thật.
