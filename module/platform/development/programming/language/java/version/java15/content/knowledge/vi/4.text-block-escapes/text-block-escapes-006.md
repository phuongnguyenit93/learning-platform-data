# Escape bát phân và giới hạn biểu diễn trong text block Java 15

> **Mục tiêu:** Hiểu chính xác cú pháp escape bát phân (*octal escape*) trong `String`, `char` và đặc biệt **text block** từ Java 15; biết vì sao `\040` giữ được dấu cách cuối dòng, giới hạn `\000`–`\377`, cách Java phân tích chuỗi số dài hơn giới hạn, và khi nào nên dùng giải pháp rõ nghĩa hơn trên Java hiện đại. Nội dung chỉ bàn về cơ chế **vẫn được hỗ trợ và sử dụng đúng ngày nay**, không yêu cầu API preview hay dựa vào cách viết đã lỗi thời.

## 1. Escape bát phân là gì?

Trong Java, escape bát phân biểu diễn **một ký tự** bằng một dấu gạch chéo ngược `\` và từ **một đến ba chữ số hệ 8**. Các chữ số bát phân chỉ gồm `0` đến `7`. Ví dụ:

~~~java
String space = "\040";  // một dấu cách U+0020, mã thập phân 32
String tab   = "\011";  // một tab U+0009, mã thập phân 9
String lf    = "\012";  // một LF U+000A, mã thập phân 10
String nul   = "\000";  // một NUL U+0000
char letter  = '\101';  // ký tự 'A', mã thập phân 65
~~~

`"\040"` không chứa bốn ký tự `\`, `0`, `4`, `0`. Sau khi mã Java được biên dịch, giá trị `String` chỉ chứa **một dấu cách thực**. Tương tự, `'\101'` là một `char` có giá trị `'A'`.

**Ứng dụng hiện đại:** Escape bát phân vẫn hợp lệ trong cả string literal, character literal và text block, hữu ích khi cần biểu diễn ký tự điều khiển hoặc giữ khoảng trắng có ý nghĩa. Tuy nhiên, trong code mới, các escape có tên như `\s`, `\t`, `\n`, `\r` thường **dễ đọc hơn**; hãy sử dụng bát phân khi nó thực sự làm rõ ý nghĩa hoặc tương thích với dữ liệu được mô tả bằng các giá trị cụ thể.

## 2. Quy tắc cú pháp: không phải ba chữ số tùy ý

Đặc tả Java Language Specification `3.10.7` định nghĩa chính xác ba dạng:

~~~text
OctalEscape = "\" + (0..7)
            | "\" + (0..7)(0..7)
            | "\" + (0..3)(0..7)(0..7)
~~~

Đây là **ký pháp mô tả**, không phải Java code. Hiểu theo cách đọc thực tế:

1. **Một chữ số:** `\0` đến `\7`.
2. **Hai chữ số:** `\00` đến `\77`, chữ số đầu có thể từ 0 đến 7.
3. **Ba chữ số:** `\000` đến `\377`, nhưng chữ số **đầu chỉ được từ 0 đến 3**.

Không có escape bát phân Java gồm bốn chữ số. Các giá trị một ký tự biểu diễn bằng cú pháp này nằm trong **U+0000 đến U+00FF** (0 đến 255 thập phân). Dùng một ký tự Unicode ngoài miền đó phải chọn cách biểu diễn khác.

| Escape | Giá trị thập phân / ký tự | Nhận xét |
| --- | --- | --- |
| `\0`, `\00`, `\000` | 0 / U+0000 | Cùng một ký tự NUL |
| `\7`, `\07`, `\007` | 7 / U+0007 | Cùng giá trị |
| `\40`, `\040` | 32 / dấu cách U+0020 | Rõ ràng khi cần giữ space cuối dòng |
| `\11`, `\011` | 9 / tab U+0009 | Có thể thay bằng `\t` |
| `\12`, `\012` | 10 / LF U+000A | Có thể thay bằng `\n` |
| `\15`, `\015` | 13 / CR U+000D | Có thể thay bằng `\r` |
| `\77` | 63 / dấu hỏi `?` | Tối đa cho dạng hai chữ số |
| `\100` | 64 / chữ `@` | Dạng ba chữ số hợp lệ |
| `\377` | 255 / U+00FF (`ÿ`) | Mức lớn nhất có thể biểu diễn trực tiếp |

**Cảnh giác với số ở ranh giới:** `\400` **không** phải một escape có giá trị 256. Java có thể diễn giải nó thành `\40` (space) rồi ký tự thường `0`, tức chuỗi gồm **hai ký tự**. Tương tự `\777` tương ứng `\77` (dấu `?`) rồi ký tự `7`. Các ví dụ này **có thể biên dịch thành công** nhưng dễ tạo dữ liệu sai. Trái lại, `\8` hoặc `\9` là escape không hợp lệ vì sau dấu gạch chéo ngược không có ký tự escape được Java cho phép.

**Quy tắc an toàn:** Không tạo escape bát phân bằng cách ghép một số bất kỳ sau dấu `\`. Nếu buộc dùng dạng bát phân, kiểm tra miền 0–255, chọn đúng dạng một/hai/ba chữ số, và thêm test đối chiếu ký tự hoặc byte đích.

## 3. Java 15 làm gì với escape trong text block?

Text block (`"""`) được chuẩn hóa từ **JDK 15** (JEP 378). Trong Java hiện đại, trình biên dịch xử lý nội dung text block theo trình tự:

1. Chuẩn hóa các dấu kết thúc dòng ở mã nguồn thành LF.
2. Xóa *incidental indentation* và các dấu cách/tab **ở cuối từng dòng** nguồn (*trailing whitespace*).
3. **Sau cùng** mới diễn giải escape của Java, gồm `\040`, `\011`, `\012`, `\s`, `\n` và escape nối dòng.

Nhờ thứ tự này, một space được sinh từ `\040` ở bước 3 sẽ **không bị bước 2 xóa**. Trong text block, đây là một trường hợp vẫn rất hữu ích của escape bát phân.

~~~java
String padded = """
        A\040\040
        B
        """;

System.out.println(padded.equals("A  \nB\n")); // true
~~~

Giá trị `padded` thực sự có **hai dấu cách** sau `A` trước LF. Nếu thay `\040\040` bằng hai dấu cách thật gõ ở cuối dòng nguồn, trình biên dịch sẽ loại bỏ chúng trước khi tạo `String`.

Một cách **rõ nghĩa hơn đối với space** trong Java mới là `\s`:

~~~java
String withOctal = """
        A\040\040
        B
        """;

String withNamedEscape = """
        A\s\s
        B
        """;

System.out.println(withOctal.equals(withNamedEscape)); // true
~~~

Hai cách đều hợp lệ và cho cùng giá trị. Với code cần bảo trì lâu dài, `\s` thường giúp người đọc hiểu ngay “một space có chủ đích”, còn `\040` nói rõ giá trị bát phân 040. Không có lý do phải chuyển mọi `\s` sang `\040`.

### Một chi tiết về Unicode escape

**`\u0020` không thay thế an toàn cho `\040` ở cuối dòng text block.** Java xử lý Unicode escapes ngay từ giai đoạn đọc mã nguồn, trước bước text block loại bỏ trailing whitespace. Khi đó `\u0020` có thể trở thành một dấu cách nguồn rồi bị loại. `\040` và `\s` lại được xử lý **sau** bước loại bỏ khoảng trắng nên giữ được giá trị. Đừng suy luận rằng mọi escape đều được áp dụng cùng một lúc.

## 4. Ví dụ hoàn chỉnh, chạy được trên Java 17+

Tạo file **OctalEscapeDemo.java** (mã nguồn UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public class OctalEscapeDemo {
    static String show(String text) {
        return text.replace("\\", "\\\\")
                .replace(" ", "·")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\0", "\\0");
    }

    public static void main(String[] args) {
        String sample = """
                A\040\040
                B\011C
                D\015\012E
                """;
        System.out.println("sample=" + show(sample));

        String values = "\0\7\40\77\100\377";
        System.out.println("values=" + values.chars()
                .mapToObj(Integer::toString)
                .collect(Collectors.joining(",")));

        String tooWide = "\400";
        String tooWideAgain = "\777";
        System.out.println("wide400=" + show(tooWide)
                + ";len=" + tooWide.length());
        System.out.println("wide777=" + show(tooWideAgain)
                + ";len=" + tooWideAgain.length());

        System.out.println("maxCode=" + (int) "\377".charAt(0));
        System.out.println("utf8=" + HexFormat.of().formatHex(
                "\377".getBytes(StandardCharsets.UTF_8)));
        System.out.println("aboveRange=" + (int) "\u0100".charAt(0));
        System.out.println("spaceEquals=" + "A\040\n".equals("A\s\n"));

        String decoded = "\\040\\011".translateEscapes();
        System.out.println("translated=" + show(decoded));
        System.out.println("tabEquals=" + "\011".equals("\t"));
        System.out.println("nullLength=" + "A\000B".length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 OctalEscapeDemo.java
java OctalEscapeDemo
~~~

Kết quả chính xác:

~~~text
sample=A··\nB\tC\nD\r\nE\n
values=0,7,32,63,64,255
wide400=·0;len=2
wide777=?7;len=2
maxCode=255
utf8=c3bf
aboveRange=256
spaceEquals=true
translated=·\t
tabEquals=true
nullLength=3
~~~

**Cách đọc kết quả:**

- Trong `sample`, `\040\040` tạo hai dấu cách, `\011` tạo tab, còn `\015\012` tạo CRLF có chủ đích **bên trong** nội dung text block. Các lần xuống dòng bình thường của text block vẫn tạo LF.
- `values` cho thấy hai dạng escape dài ngắn khác nhau đều tạo một ký tự và có thể đọc dưới dạng giá trị số nguyên của ký tự.
- `wide400` và `wide777` cho thấy **cú pháp phân tách chuỗi** khi vượt miền octal hợp lệ; không nên mặc định trình biên dịch luôn báo lỗi để bảo vệ bạn.
- `\377` là ký tự U+00FF có mã 255, nhưng khi encode theo UTF-8 nó tạo bytes `c3bf` — **không phải byte đơn `ff`**.
- `\u0100` tạo ký tự U+0100 (giá trị 256), nằm ngoài miền có thể biểu diễn bằng một octal escape.
- `String.translateEscapes()` xử lý chuỗi chứa **ký tự escape dưới dạng text lúc runtime**; nó không hoạt động y hệt giai đoạn Unicode preprocessing của compiler.
- `"A\040\n"` và `"A\s\n"` bằng nhau: cả hai chứa `A`, một space và LF.
- `"A\000B"` có độ dài **3**; NUL là một ký tự nằm giữa chuỗi, **không** phải ký tự kết thúc chuỗi Java.

Hàm `show` thay whitespace bằng ký hiệu dễ quan sát, phục vụ học tập và debug. Đối với dữ liệu có ký tự `·` hay các chuỗi `\t` thật, cách hiển thị này **không phải mã hóa đảo ngược hoàn hảo**; khi kiểm thử tính toàn vẹn, hãy đối chiếu `String.equals`, mã ký tự và bytes.

## 5. Giới hạn biểu diễn: 255 là giới hạn **ký tự**, không phải “byte đầu ra”

Cần phân biệt ba khái niệm:

| Khái niệm | Trong ví dụ `\377` | Điều cần nhớ |
| --- | --- | --- |
| Giá trị octal của escape | 377 (hệ 8) = 255 (hệ 10) | Miền 0–255 cho **một octal escape** Java |
| Ký tự Unicode được tạo trong `String` | U+00FF (`ÿ`), một UTF-16 code unit | Đó là giá trị ký tự Java, chưa phải dãy byte truyền đi |
| Byte sau mã hóa UTF-8 | `C3 BF` (hai bytes) | Encoding quyết định byte đầu ra; không tự lấy giá trị 255 làm byte `FF` |

Vì Java `String` lưu văn bản Unicode theo các đơn vị UTF-16, octal escape không phải cơ chế khai báo “một byte bất kỳ” cho giao thức nhị phân. Cách dùng octal dễ gây sai khi ánh xạ một sơ đồ byte trực tiếp sang `String`, nhất là với giá trị 128–255.

Ví dụ:

~~~java
String text = "\377"; // một ký tự U+00FF
byte[] utf8 = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
// Hai byte: C3 BF (hex), không phải một byte FF
~~~

Nếu **dữ liệu đích thực sự là bytes** (file nhị phân, giao thức mạng, checksum trên bytes), biểu diễn trực tiếp với `byte[]`, `ByteBuffer` hoặc API tương ứng; khi cần byte `FF`:

~~~java
byte[] payload = {(byte) 0xFF}; // đúng một byte có bit pattern FF
~~~

Không đi đường vòng qua `String` rồi mặc định encoder sẽ giữ nguyên giá trị octal. Khi chuyển bytes thành text, hãy xác định rõ **charset** và xem dữ liệu có thực sự là văn bản hợp lệ hay không.

## 6. Với ký tự vượt U+00FF, nên viết thế nào?

Một octal escape Java không vượt `\377`. Nếu cần Unicode ngoài miền U+0000–U+00FF:

- Dùng **ký tự Unicode trực tiếp** trong mã nguồn UTF-8 (khi định dạng source của dự án cho phép).
- Dùng **Unicode escape** `\uXXXX` cho một UTF-16 code unit khi thật sự cần viết bằng ASCII; hiểu rằng escape này được xử lý rất sớm trong quá trình dịch nguồn Java.
- Với **Unicode code point ngoài BMP** (trên U+FFFF), có thể dùng `Character.toChars(codePoint)` hoặc `StringBuilder.appendCodePoint(codePoint)` để tạo chuỗi đúng cặp surrogate.

~~~java
String latinExtended = "\u0100";  // U+0100 (Ā), ngoài octal range
String emoji = new String(Character.toChars(0x1F600)); // 😀
~~~

Lưu ý `\u000A` trong nguồn Java **không phải** cách thay thế `\n` trong string literal: nó được chuyển thành **dấu xuống dòng thật trước bước phân tích chuỗi**, có thể khiến source không hợp lệ. Dùng `\n` cho LF, `\r` cho CR, `\t` cho tab và `\s` cho dấu cách.

**Không nhầm với integer literal:** `0377` viết ngoài chuỗi là một **số nguyên bát phân** có giá trị 255; `"\377"` là một `String` chứa ký tự U+00FF. Chúng là những loại dữ liệu khác nhau dù cùng xuất phát từ hệ 8.

## 7. Escape bát phân, ký tự điều khiển và line endings

Bảng tham chiếu hữu ích khi đọc text block hoặc chương trình tích hợp:

| Ý định | Escape bát phân | Escape nên ưu tiên khi có tên | Lưu ý |
| --- | --- | --- | --- |
| NUL | `\000` | Không có tên riêng ngắn tương đương | Có thể gây vấn đề khi đưa sang API native hoặc định dạng không chấp nhận NUL |
| Tab | `\011` | `\t` | Độ rộng hiển thị tab phụ thuộc môi trường |
| LF | `\012` | `\n` | Tương đương về ký tự khi đã diễn giải |
| CR | `\015` | `\r` | Khi cần CRLF, dùng `\r\n` rõ ràng |
| Space | `\040` | `\s` | Cả hai có thể giữ trailing spaces trong text block |
| Double quote | `\042` | `\"` hoặc dấu `"` trực tiếp khi hợp lệ | Text block thường không cần escape từng dấu nháy kép |
| Backslash | `\134` | `\\` | Được dùng khi cần một dấu `\` thật |

### CRLF trong text block

Java chuẩn hóa dấu xuống dòng **có trong mã nguồn** text block về LF (`\n`). Ngược lại, ký tự CR và LF **sinh ra từ escape** như `\015\012`, hoặc cách rõ ràng hơn là `\r\n`, được tạo sau khi chuẩn hóa và vì thế vẫn tồn tại trong giá trị chuỗi cuối cùng.

~~~java
String mixed = """
        first\015\012second
        third
        """;

// mixed.equals("first\r\nsecond\nthird\n") == true
~~~

Điều này có ích khi phải tương tác với một định dạng văn bản quy định CRLF. Tuy vậy, nếu cần bảo toàn **từng byte nguyên bản của file**, dùng bytes/tài nguyên phù hợp sẽ rõ ràng hơn text block.

### NUL không kết thúc String Java

`\000` tạo U+0000 như một ký tự bình thường trong Java `String`. `String.length()` vẫn đếm nó và `String.equals()` vẫn so sánh nó. Nhưng một hệ thống native, parser hoặc định dạng đầu ra có thể không cho phép NUL; hãy kiểm tra đặc tả của hệ thống nhận dữ liệu thay vì gửi NUL chỉ vì Java tạo được.

## 8. `String.translateEscapes()`: giải mã escape tại runtime

Bên cạnh escape trong mã nguồn, Java 15 có phương thức `String.translateEscapes()`, vẫn là API hiện hành. Nó dịch các escape thông thường (gồm octal escapes) trong một **chuỗi đã tồn tại lúc runtime**. Ví dụ:

~~~java
String raw = "\\040\\011";        // 8 ký tự: \ 0 4 0 \ 0 1 1
String translated = raw.translateEscapes();

System.out.println(translated.equals(" \t")); // true
~~~

Ở `raw`, mỗi dấu `\\` trong string literal tạo ra **một** backslash thật; vì vậy `raw` chứa hai mẫu chữ `\040` và `\011`. Khi gọi `translateEscapes()`, chúng lần lượt được đổi thành space và tab.

**Giới hạn sử dụng:**

- Phương thức này hiểu **Java escape syntax**, không phải bộ giải mã tổng quát cho JSON, YAML, URL encoding hay HTML entities.
- Nó **không** dịch Unicode escape `\uXXXX` từ text runtime theo cùng cơ chế xử lý sớm của javac.
- Escape không hợp lệ (chẳng hạn text runtime chứa `\8`) có thể khiến phương thức ném `IllegalArgumentException`. Hãy kiểm tra hoặc bắt lỗi khi xử lý dữ liệu bên ngoài.
- Không tự động đưa dữ liệu không đáng tin qua `translateEscapes()` với giả định “đây là sanitization”; thao tác có thể biến backslash và ký tự văn bản thành ký tự điều khiển thật.

Nếu đọc JSON, hãy dùng JSON parser; nếu xử lý SQL, dùng tham số `PreparedStatement`; nếu tạo nội dung có encoding cụ thể, dùng encoder tương ứng. `translateEscapes()` phù hợp khi **hợp đồng đầu vào thật sự là cú pháp escape của Java**.

## 9. Tình huống chọn lựa trong code Java hiện đại

**Tình huống A — mẫu văn bản nhiều dòng cần hai dấu cách cuối dòng.** Dùng text block với `\s\s`; `\040\040` đúng nhưng ít rõ nghĩa hơn:

~~~java
String markdown = """
        Dòng một\s\s
        Dòng hai
        """;
~~~

Giá trị chứa `"Dòng một  \nDòng hai\n"`. Nếu bạn chỉ gõ hai dấu cách nguồn ở cuối dòng, javac có thể xóa chúng.

**Tình huống B — dữ liệu có tab, newline hoặc CRLF.** Dùng các escape có tên `\t`, `\n`, `\r\n` để người đọc dễ nhìn ra chức năng. `\011`, `\012` và `\015` vẫn có nghĩa chính xác nhưng không nên làm code khó hiểu khi không cần thiết.

**Tình huống C — một API yêu cầu đúng các bytes.** Tạo `byte[]` trực tiếp hoặc mã hóa chuỗi bằng charset được giao thức xác định; kiểm thử bytes đích. Tránh suy luận `\377` là một byte `FF` khi encode UTF-8.

**Tình huống D — Unicode ngoài ký tự Latin-1.** Dùng Unicode source, `\uXXXX` hoặc API code point như `Character.toChars`. Không tìm cách ghi bốn chữ số bát phân trong một escape.

**Tình huống E — bảo trì code có octal escapes.** Khi thấy `\040`, xác nhận giá trị thật và vai trò của nó trong text block trước khi đổi thành `\s`; khi thấy `\400`, kiểm tra ngay xem có lỗi chủ ý/nhầm tách escape hay không. Giữ regression test để chứng minh đầu ra không đổi.

## 10. Lỗi thường gặp và cách tránh

1. **Cho rằng mọi escape `\xyz` ba chữ số đều hợp lệ.** Chỉ ba chữ số mà chữ số đầu từ 0–3; `\400` và `\777` có thể bị tách thành một escape ngắn cộng ký tự thường.
2. **Nhầm `\377` với byte `FF` sau UTF-8 encoding.** `\377` tạo Unicode U+00FF; UTF-8 tạo `C3 BF`.
3. **Dùng `\8`, `\9` hoặc `\x41` như trong ngôn ngữ khác.** Đây không phải octal escape/escape hợp lệ trong string literal Java.
4. **Dùng `\u0020` để bảo toàn trailing whitespace trong text block.** Unicode preprocessing diễn ra trước khi loại bỏ whitespace, khiến ý định giữ dấu cách có thể thất bại.
5. **Nghĩ text block sẽ giữ dấu cách cuối dòng chỉ vì editor còn hiển thị chúng.** Trình biên dịch chủ động xóa trailing whitespace nguồn; `\s` hoặc `\040` mới là biểu diễn tường minh.
6. **Nhầm `\012` và dấu xuống dòng nguồn.** Cùng là LF ở giá trị cuối, nhưng một cái là escape được xử lý muộn; một cái chịu bước chuẩn hóa của text block.
7. **Đưa NUL `\000` sang hệ thống khác mà không kiểm tra.** Java `String` chứa NUL được, nhưng nhiều giao thức, parser hoặc native API có ràng buộc riêng.
8. **Dùng `translateEscapes()` như trình giải mã phổ dụng.** Nó tuân theo Java escape syntax và có thể báo lỗi trên chuỗi không hợp lệ.
9. **Để số lượng dấu cách/tab là nội dung “ẩn”.** Tạo assertion về `String.equals()` hoặc bytes, và bổ sung ví dụ hiển thị whitespace khi debug.
10. **Cố dùng octal vì bài học thuộc Java 15.** Ngày nay `\s`, `\t`, `\n`, `\r`, Unicode source và các API phù hợp thường mô tả ý định tốt hơn; octal vẫn có vị trí khi giá trị số cụ thể thật sự quan trọng.

## 11. Bài tự luyện và tiêu chí đạt

**Bài 1 — Giới hạn cú pháp.** Dự đoán giá trị `"\7"`, `"\77"`, `"\377"`, `"\400"` và `"\777"`. Viết code in `length()` và mã số từng ký tự, rồi chạy để kiểm chứng. **Đạt** khi giải thích được tại sao hai mẫu cuối không tạo một ký tự có mã 256 hoặc 511.

**Bài 2 — Bảo toàn dấu cách cuối dòng.** Viết text block hai dòng, dòng đầu cần đúng ba dấu cách trước LF. So sánh phương án `\040\040\040` với `\s\s\s` bằng `equals()`. **Đạt** khi cả hai bằng chuỗi thường kỳ vọng `"A   \nB\n"` mà không yêu cầu giữ dấu cách vô hình trong mã nguồn.

**Bài 3 — Phân biệt ký tự với bytes.** Lấy `"\377"`, in mã ký tự và các bytes sau `getBytes(StandardCharsets.UTF_8)`. **Đạt** khi chỉ ra được U+00FF khác với một byte `FF`, và giá trị UTF-8 là `C3 BF`.

**Bài 4 — Chuẩn hóa newline có chủ đích.** Xây dựng text block chứa CRLF bằng `\015\012` hoặc `\r\n`, đồng thời giữ một LF nguồn ở dòng khác. **Đạt** khi kiểm tra `equals("first\r\nsecond\n")` hoặc chuỗi kỳ vọng tương ứng, không suy luận dựa vào console.

**Bài 5 — API runtime.** Cho chuỗi `"\\040\\011"`, gọi `translateEscapes()` và kiểm tra kết quả bằng `" \t"`. Sau đó thử đầu vào có `\8` được đọc từ dữ liệu ngoài để xác định cách xử lý ngoại lệ. **Đạt** khi phân biệt được giai đoạn biên dịch literal và giải mã escape lúc runtime.

## 12. Tham khảo đặc tả chính thức

- [Java Language Specification 25 — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7): dạng một/hai/ba chữ số, giới hạn U+0000–U+00FF, và escape hợp lệ.
- [Java Language Specification 15 — `3.10.7](https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html#jls-3.10.7): cùng nguyên tắc ở thời điểm Java 15.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): xử lý nội dung text block, dấu cách và escape sau khi loại incidental whitespace.
- [Oracle Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): ví dụ `\040`, `\s`, chuẩn hóa line terminators và `String.translateEscapes()`.
- [Java SE 25 API — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): API `translateEscapes()` và xử lý chuỗi.

**Ghi nhớ:** Escape bát phân trong Java vẫn hợp lệ nhưng chỉ biểu diễn **một ký tự U+0000–U+00FF**, với quy tắc tối đa ba chữ số và chữ số đầu của dạng ba chữ số phải từ 0–3. Trong text block, `\040` tồn tại sau bước loại bỏ trailing whitespace nên có thể giữ space có ý nghĩa. Khi mục đích là space, tab, newline, Unicode hoặc bytes, hãy chọn biểu diễn dễ hiểu và đúng với hợp đồng dữ liệu hiện đại.
