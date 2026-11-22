# String.translateEscapes với dữ liệu ở runtime — API chuỗi Java 15

> **Mục tiêu:** Sử dụng đúng `String.translateEscapes()` để chuyển các chuỗi escape theo cú pháp Java **đang tồn tại như dữ liệu lúc chương trình chạy** thành ký tự thật; hiểu phạm vi hỗ trợ, thứ tự xử lý, ngoại lệ, những trường hợp không nên chuyển đổi và cách kiểm thử chính xác. API này được bổ sung chính thức từ **Java 15** và vẫn dùng được trên các JDK hiện đại. Ví dụ chạy với **Java 17+**, không cần bật preview.

## 1. Vấn đề cần giải quyết: hai dấu ký tự hay một ký tự điều khiển?

Trong một ứng dụng, thông tin từ file cấu hình, cơ sở dữ liệu, giao diện hoặc một định dạng văn bản riêng có thể chứa **hai ký tự** backslash `\` và `n`, với mong muốn cuối cùng là **một ký tự xuống dòng LF**.

Hãy phân biệt:

| Dữ liệu | Ý nghĩa tại runtime |
| --- | --- |
| `"A\nB"` trong **mã Java** | Trình biên dịch biến `\n` thành LF; chuỗi có 3 ký tự: `A`, LF, `B` |
| `"A\\nB"` trong **mã Java** | Trình biên dịch biến `\\` thành một backslash; chuỗi có 4 ký tự: `A`, `\`, `n`, `B` |
| Văn bản nguồn ngoài chương trình `A\nB` (backslash và `n` thật) | Khi đọc nguyên văn, chuỗi vẫn chứa 4 ký tự; Java **không tự giải mã** |
| `raw.translateEscapes()`, với `raw` chứa `A\nB` dạng văn bản | Trả chuỗi 3 ký tự: `A`, LF, `B` |

Ví dụ nhỏ:

~~~java
String raw = "A\\nB";                  // A, \, n, B
String decoded = raw.translateEscapes();

System.out.println(raw.length());      // 4
System.out.println(decoded.length());  // 3
System.out.println(decoded.equals("A\nB")); // true
~~~

**Điểm cốt lõi:** `translateEscapes()` là một phép biến đổi **runtime trên dữ liệu `String` đã có**, không phải thay đổi cách Java compiler xử lý source code. Nếu đầu vào vốn đã chứa newline thật, không cần dùng phương thức này để tạo newline lần nữa.

## 2. Hợp đồng của `String.translateEscapes()`

Khai báo trên `java.lang.String`:

~~~java
public String translateEscapes()
~~~

- **Có từ Java 15 (`@since 15`)** và là API công khai ổn định trên JDK hiện đại.
- Trả về một `String` mới theo ngữ nghĩa: mọi escape **hợp lệ theo tập escape của Java string literal** được chuyển thành ký tự tương ứng.
- Những ký tự bình thường (không nằm trong một escape) được giữ lại; không tự thêm/dỡ khoảng trắng, không tự chuẩn hóa Unicode hay dùng regex.
- Nếu gặp **escape sai cú pháp**, ném `IllegalArgumentException`; không trả về chuỗi được giải mã một phần để gọi tiếp.
- Không biến đổi nội dung `String` gốc vì `String` là bất biến. Hãy giữ cả `raw` và `decoded` nếu cần truy vết dữ liệu ban đầu.

Ví dụ:

~~~java
String raw = "status=\\sOK\\n";
String decoded = raw.translateEscapes();

System.out.println(decoded.equals("status= OK\n")); // true
System.out.println(raw.equals("status=\\sOK\\n"));   // true
~~~

Ở đây `\s` biểu diễn **một dấu cách U+0020**, không phải lớp ký tự whitespace của biểu thức chính quy.

## 3. Chính xác những escape nào được hỗ trợ?

Bảng dưới đây mô tả **hai ký tự trở lên đang có trong dữ liệu đầu vào runtime**, không phải cách gõ escape trong Java source.

| Văn bản escape trong đầu vào | Ký tự tạo ra | Vai trò thường gặp |
| --- | --- | --- |
| `\b` | Backspace U+0008 | Dữ liệu điều khiển, ít cần trong văn bản thông thường |
| `\t` | Tab U+0009 | Căn/đánh dấu tab |
| `\n` | LF U+000A | Xuống dòng |
| `\f` | Form feed U+000C | Ký tự điều khiển |
| `\r` | CR U+000D | Khi cần CRLF, viết `\r\n` |
| `\s` | Space U+0020 | Dấu cách có chủ đích, kể cả ở cuối dòng |
| `\"` | Dấu nháy kép `"` | Giải escape dấu nháy |
| `\'` | Dấu nháy đơn `'` | Giải escape dấu nháy |
| `\\` | Một backslash `\` | Giữ backslash thành ký tự thực |
| `\0` đến `\377` | Giá trị ký tự U+0000–U+00FF | Escape bát phân theo cú pháp Java |
| Backslash đứng ngay trước **LF** hoặc **CRLF** thật | Không tạo ký tự, bỏ backslash + line terminator | Nối dòng (*line continuation*) |

Cú pháp bát phân là **1 chữ số từ 0–7, 2 chữ số từ 0–7, hoặc 3 chữ số với chữ số đầu 0–3**. Ví dụ `\040` tạo dấu cách (32), `\011` tạo tab (9), `\377` tạo ký tự U+00FF (255). `\400` **không** tạo ký tự 256: nó được phân tích thành `\40` (space) rồi ký tự `0`.

**Các chuỗi `\d`, `\w`, `\x41`, `\/` và `\u0041` không nằm trong tập này.** Chúng có thể hợp lệ trong cú pháp khác, nhưng `translateEscapes()` không phải bộ giải mã đa ngôn ngữ: khi gặp escape không được hỗ trợ, phương thức ném `IllegalArgumentException`.

## 4. Ví dụ hoàn chỉnh, kiểm chứng được trên Java 17+

Tạo file **RuntimeEscapeDemo.java** với nội dung sau. Hàm `visible` hiển thị backslash, space, tab và newline để đầu ra trên console có thể kiểm tra được.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public class RuntimeEscapeDemo {
    static String visible(String value) {
        return value
                .replace("\\", "\\\\")
                .replace(" ", "·")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    static String tryTranslate(String raw) {
        try {
            return visible(raw.translateEscapes());
        } catch (IllegalArgumentException e) {
            return "IllegalArgumentException";
        }
    }

    public static void main(String[] args) {
        String raw = "Name:\\sAda\\nStatus:\\tOK\\nQuote:\\\"Hi\\\"";
        String translated = raw.translateEscapes();
        System.out.println("raw=" + visible(raw));
        System.out.println("translated=" + visible(translated));
        System.out.println("expected=" + translated.equals(
                "Name: Ada\nStatus:\tOK\nQuote:\"Hi\""));

        String octal = "\\040\\011\\377".translateEscapes();
        System.out.println("octal=" + octal.chars()
                .mapToObj(Integer::toString)
                .collect(Collectors.joining(",")));
        System.out.println("utf8-ff=" + HexFormat.of()
                .formatHex("\377".getBytes(StandardCharsets.UTF_8)));

        String once = "\\\\n".translateEscapes();
        System.out.println("once=" + visible(once));
        System.out.println("onceIsNewline=" + once.equals("\n"));

        String path = "C:\\temp\\new";
        System.out.println("pathRaw=" + visible(path));
        System.out.println("pathDecoded=" + visible(path.translateEscapes()));

        System.out.println("badQ=" + tryTranslate("\\q"));
        System.out.println("badU=" + tryTranslate("\\u0041"));
        System.out.println("badEnd=" + tryTranslate("\\"));
        System.out.println("noSlash=" + tryTranslate("one\ntwo"));
        System.out.println("continuationLF="
                + visible("x\\\ny".translateEscapes()));
        System.out.println("continuationCRLF="
                + visible("x\\\r\ny".translateEscapes()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 RuntimeEscapeDemo.java
java RuntimeEscapeDemo
~~~

Kết quả kỳ vọng đã được đối chiếu bằng chương trình thực tế:

~~~text
raw=Name:\\sAda\\nStatus:\\tOK\\nQuote:\\"Hi\\"
translated=Name:·Ada\nStatus:\tOK\nQuote:"Hi"
expected=true
octal=32,9,255
utf8-ff=c3bf
once=\\n
onceIsNewline=false
pathRaw=C:\\temp\\new
pathDecoded=C:\temp\new
badQ=IllegalArgumentException
badU=IllegalArgumentException
badEnd=IllegalArgumentException
noSlash=one\ntwo
continuationLF=xy
continuationCRLF=xy
~~~

**Giải thích:**

- `raw` là văn bản chứa các ký hiệu escape; `translated` đã có space, LF, tab và dấu nháy kép thật. Ký hiệu `·` trong output là do hàm hiển thị, không tồn tại trong chuỗi.
- `octal` cho các giá trị ký tự 32, 9, 255. **U+00FF là ký tự**, và khi encode theo UTF-8 nó cho **hai byte `C3 BF`**, không phải byte `FF` duy nhất.
- `once` cho thấy phương thức giải mã **một lượt**. Sau một lần, `\\\\n` trong dữ liệu được giải thành hai ký tự `\` và `n`, vẫn chưa phải LF.
- `pathDecoded` thể hiện **rủi ro dữ liệu đường dẫn**: `\t` và `\n` vốn là ký tự trong đường dẫn Windows có thể bị biến thành tab và LF. Hàm `visible` cho thấy chúng bằng chuỗi hiển thị `\t` và `\n`. Không tự chạy `translateEscapes()` trên path.
- `badQ`, `badU`, `badEnd` xác nhận phản ứng khi có escape không hợp lệ hoặc backslash không có ký tự phía sau.
- `noSlash` cho thấy LF đã tồn tại thật trong chuỗi vẫn giữ nguyên.
- `continuationLF` và `continuationCRLF` cho thấy backslash theo sau ngay bởi line terminator thật được bỏ, nối hai phần text thành `xy`.

Hàm `visible` giúp học và debug; nó **không phải serialization có thể đảo ngược cho mọi dữ liệu** nếu dữ liệu gốc chứa `·` hay những ký hiệu hiển thị trùng nhau. Đối chiếu chính xác bằng `equals` hoặc bytes phù hợp khi kiểm thử.

## 5. Ba tầng dễ nhầm: Java source, dữ liệu runtime và dữ liệu sau chuyển đổi

Xét tệp cấu hình hoặc trường database có **nội dung thật** như sau:

~~~text
First\\nSecond
~~~

Dòng này đang minh họa **hai dấu backslash** rồi `n`. Nếu ý định muốn có một backslash thật kèm chữ `n`, cần bảo vệ chúng khi giải mã; nếu giải mã trực tiếp **một lượt**, chuỗi `\\` trở thành một backslash và `n` được giữ như chữ bình thường.

Ngược lại, với nội dung:

~~~text
First\nSecond
~~~

Có **một backslash** rồi chữ `n`, nên `translateEscapes()` tạo chuỗi `First` + LF + `Second`.

Nếu đang **mô phỏng dữ liệu ngoài trong mã Java**, nhớ viết **hai backslash** trong literal Java để tạo **một backslash** ở runtime:

~~~java
String rawFromFile = "First\\nSecond";
String decoded = rawFromFile.translateEscapes();

System.out.println(decoded.equals("First\nSecond")); // true
~~~

Chuỗi thường, text block và compiler đã xử lý escape **trước** khi runtime bắt đầu. Không gọi `translateEscapes()` một cách vô điều kiện trên dữ liệu vốn đã diễn giải xong. Chẳng hạn:

~~~java
String alreadyDecoded = "Line 1\nLine 2";
System.out.println(alreadyDecoded.translateEscapes()
        .equals(alreadyDecoded)); // true
~~~

Trong trường hợp này, không còn backslash escape nào phải xử lý nên kết quả không đổi. Tuy nhiên, nếu một chuỗi **đã giải mã** chứa các backslash bình thường thì gọi lại có thể làm sai dữ liệu.

## 6. Chỉ giải mã một lần: vì sao “giải đến khi không còn backslash” sai?

Xét:

~~~java
String input = "\\\\n";              // runtime: hai backslash rồi 'n'
String once = input.translateEscapes(); // runtime: một backslash rồi 'n'
String twice = once.translateEscapes(); // runtime: một LF

System.out.println(once.equals("\\n")); // true
System.out.println(twice.equals("\n"));  // true
~~~

Bản thân lời gọi API không có cơ chế *recursive decoding*: mỗi lần gọi chỉ duyệt một lượt trên chuỗi hiện tại. Gọi lần thứ hai **thay đổi ý nghĩa** một chuỗi đã được escape có chủ đích. Đặc biệt nếu có đầu vào ngoài do người dùng kiểm soát, giải nhiều lượt có thể biến một chuỗi được hiển thị như văn bản thành ký tự điều khiển thật.

**Quy tắc sử dụng:** xác định rõ ở ranh giới hệ thống nào việc giải escape được phép xảy ra, gọi **đúng một lần**, và lưu/log tên biến thể `raw` hoặc `decoded` cho rõ. Đừng viết vòng lặp gọi `translateEscapes()` cho đến khi chuỗi không còn thay đổi.

## 7. Escape Unicode không được giải mã bởi phương thức này

Javadoc nêu rõ `translateEscapes()` **không xử lý escape Unicode `\uNNNN`**. Trong Java, Unicode escape là một cơ chế **dịch mã nguồn của compiler từ rất sớm**, trước khi phân tích string literal; nó không thuộc nhóm escape thông thường của string literal.

~~~java
String rawUnicode = "\\u0041"; // runtime: \ u 0 0 4 1
// rawUnicode.translateEscapes(); // ném IllegalArgumentException
~~~

Mặc dù ký tự `A` có giá trị Unicode U+0041, phương thức này **không biến** `\u0041` trong text runtime thành `A`. Tương tự, nó không giải chuỗi `\x41` theo kiểu C/JavaScript hay `%41` theo URL encoding.

Nếu đầu vào là một định dạng chứa các escape Unicode (ví dụ JSON `"\u0041"`), **dùng parser của chính định dạng**. Không tự kết hợp `replace` và `translateEscapes` để “giải mã JSON” vì quy tắc escape, quoting, ký tự điều khiển và cặp surrogate có thể khác nhau.

Khi chương trình cần tạo một Unicode code point, có thể dùng:

~~~java
String text = new String(Character.toChars(0x1F600)); // 😀
~~~

Hoặc dùng literal Unicode/UTF-8 trực tiếp khi yêu cầu cho phép. `translateEscapes()` không phải API thay thế cho xử lý Unicode nói chung.

## 8. Escape bát phân và giới hạn 0–255: ký tự khác bytes

Escape bát phân trong `translateEscapes()` theo cú pháp Java:

~~~java
String raw = "\\040\\011\\377";
String value = raw.translateEscapes();

// value chứa: space (32), tab (9), U+00FF (255)
~~~

Chữ số bát phân chỉ từ 0–7; ba chữ số chỉ được có chữ số đầu từ 0–3. Giá trị trực tiếp tối đa là U+00FF. `\400` trong dữ liệu được phân tích theo quy tắc escape ngắn hơn cộng ký tự thường, **không báo lỗi vì số 256 vượt phạm vi**; vì thế phải có kiểm thử nếu định dạng mong muốn chính xác.

**Không dùng `\377` để biểu diễn “byte FF” tùy ý.** `String` chứa ký tự Unicode; khi gọi `getBytes(StandardCharsets.UTF_8)`, ký tự U+00FF được mã hóa thành bytes `C3 BF`. Nếu đang xử lý file nhị phân, giao thức byte hoặc checksum trên bytes, hãy làm việc với `byte[]` hoặc API byte phù hợp.

## 9. Nối dòng bằng escape runtime khác với newline thông thường

Một trường hợp ít gặp nhưng vẫn được định nghĩa là backslash đứng **ngay trước dấu xuống dòng thật**. Khi đó cả backslash và line terminator bị loại bỏ:

~~~java
String input = "A\\\nB";
String output = input.translateEscapes();

System.out.println(output.equals("AB")); // true
~~~

Ví dụ đầu vào gồm `A`, backslash, LF, `B`; sau chuyển đổi thành `AB`.

Với CRLF cũng vậy:

~~~java
String input = "A\\\r\nB";
System.out.println(input.translateEscapes().equals("AB")); // true
~~~

**Phân biệt:** Nếu dữ liệu là `"A\\nB"` ở runtime (backslash rồi chữ `n`), phương thức tạo **LF**, còn nếu dữ liệu là `A`, backslash rồi **LF thật** thì phương thức **loại cả backslash và LF**. Đó là hai trường hợp khác nhau.

Việc nối dòng hữu ích trong một số cú pháp mẫu văn bản có quy ước backslash cuối dòng. Tuy nhiên, đừng dùng `translateEscapes()` để làm “chuẩn hóa newline” chung: nó không tự chuyển mọi CRLF, không tự thêm newline, và những backslash trong dữ liệu có thể mang nghĩa khác.

## 10. Dữ liệu từ file, database và cấu hình: dùng đúng ranh giới

Ví dụ ứng dụng đọc **tệp văn bản UTF-8 nguyên văn**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

// Đặt trong một phương thức có throws IOException:
String raw = Files.readString(
        Path.of("message-template.txt"),
        StandardCharsets.UTF_8);
String decoded = raw.translateEscapes();
~~~

Đây là **đoạn code minh họa**, không phải chương trình `main` độc lập. Chỉ gọi `translateEscapes()` nếu **định dạng của `message-template.txt` quy định escape theo cú pháp Java**. Nếu file chứa văn bản cần giữ nguyên (tên đường dẫn, đoạn code, biểu thức chính quy, log nguyên bản), hãy dùng `raw` trực tiếp.

**Chú ý:** mỗi định dạng cấu hình có parser riêng. Ví dụ `Properties.load` có quy tắc backslash/escape riêng; JSON parser cũng đã giải escape JSON. Nếu gọi tiếp `translateEscapes()` trên giá trị chúng trả về, có thể **giải mã hai lần** hoặc làm biến dạng backslash. Hãy xác định giá trị thực tế **sau parser** và hợp đồng dữ liệu trước khi áp dụng API này.

Cơ sở dữ liệu cũng vậy: cột `VARCHAR` lưu đúng một backslash trước `n` có thể là biểu diễn escape có chủ đích, hoặc chỉ là một đường dẫn/cụm text. **Không thể suy ra chỉ từ việc có backslash**. Schema hoặc quy ước dữ liệu phải nói rõ cột nào được giải mã.

## 11. Ngoại lệ và kiểm soát lỗi thực tế

`translateEscapes()` ném **`IllegalArgumentException`** khi gặp escape không hợp lệ, chẳng hạn `\q`, `\u0041` hoặc chuỗi kết thúc bằng backslash đơn.

~~~java
static String decodeTemplate(String raw) {
    try {
        return raw.translateEscapes();
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid Java escape syntax in template", ex);
    }
}
~~~

Hàm trên minh họa trong phạm vi một class; cần bao bọc nó bằng class khi viết chương trình thực. Khi cung cấp API cho người dùng, bạn có thể chuyển lỗi này thành thông báo rõ dòng/cột hoặc tên field mà **không tiết lộ toàn bộ dữ liệu nhạy cảm trong thông báo**.

Có thể lựa chọn chính sách tùy yêu cầu:

- **Đầu vào bắt buộc phải đúng cú pháp:** báo lỗi và yêu cầu sửa. Đây là mặc định dễ kiểm chứng.
- **Đầu vào là văn bản nguyên bản, không có hợp đồng escape:** không gọi `translateEscapes()`.
- **Đầu vào hỗn hợp và muốn chấp nhận một vài escape:** cần định nghĩa rõ parser theo hợp đồng (hoặc escape backslash dữ liệu đầu vào theo định dạng đã định); không âm thầm bỏ lỗi bằng cách trả lại một phần dữ liệu đã chuyển đổi.

Không khuyến khích cách “bắt lỗi rồi trả luôn `raw`” nếu hệ thống đòi nội dung đã được chuẩn hóa; điều đó khiến cùng một trường dữ liệu có hai kiểu ngữ nghĩa khác nhau và khó debug.

## 12. Khác gì `replace`, `stripIndent`, regex và bộ giải mã JSON?

| Công cụ | Công dụng thực sự | Khi phù hợp |
| --- | --- | --- |
| `String.translateEscapes()` | Dịch các **Java escape hợp lệ** trong dữ liệu runtime | Tệp mẫu hoặc trường dữ liệu quy định chính xác syntax Java escape |
| `String.replace("\\n", "\n")` | Chỉ thay **mẫu ký tự cụ thể** | Hợp đồng chỉ có một loại escape đơn giản và bạn kiểm soát hoàn toàn dữ liệu |
| `String.stripIndent()` | Bỏ incidental indentation và trailing whitespace theo quy tắc chuỗi nhiều dòng | Làm sạch indent có chủ đích, không dùng để giải `\n` |
| `String.formatted(...)` | Thay placeholder định dạng `%s`, `%d`… | Chèn biến vào template định dạng, không tự giải Java escape runtime |
| `Pattern` / `Matcher` | Phân tích, tìm kiếm, thay thế theo **cú pháp regex** | Khi đầu vào thực sự là regex; `\d`, `\w` có nghĩa trong regex nhưng **không** trong `translateEscapes()` |
| JSON/XML/URL parser đúng chuẩn | Giải mã đúng cú pháp của **định dạng tương ứng** | Khi input từ JSON, XML, URL…; không tự dùng Java escape parser |

Ví dụ khác biệt giữa Java escape và regex:

~~~java
String regexRaw = "\\d+";         // runtime: \d+
System.out.println(regexRaw);     // \d+
// regexRaw.translateEscapes();    // IllegalArgumentException

boolean matched = java.util.regex.Pattern.compile(regexRaw)
        .matcher("123")
        .matches();
System.out.println(matched); // true
~~~

Ở đây `Pattern` hiểu `\d+` là “một hay nhiều chữ số”, còn `translateEscapes()` không hiểu `\d`. Không chuyển đổi `regexRaw` trước khi đưa vào `Pattern`.

**An toàn vận hành:** gọi `translateEscapes()` trên dữ liệu không đáng tin có thể biến `\n`, `\r`, `\t`, NUL hay những ký tự điều khiển khác thành giá trị thật, làm thay đổi cách hiển thị log, mẫu thông báo hoặc giao thức. Chỉ cho phép những escape mà định dạng đầu vào đã định nghĩa và kiểm tra đầu ra nếu ngữ cảnh đích có hạn chế. API này **không phải sanitizer**.

## 13. Kiểm thử chính xác và tránh lỗi hiển thị

Console không hiển thị rõ sự khác nhau giữa backslash-`n` và newline thật. Viết test với các giá trị kỳ vọng tường minh:

~~~java
String input = "A\\nB\\s";
String expected = "A\nB ";
String actual = input.translateEscapes();

if (!expected.equals(actual)) {
    throw new AssertionError("Translated value changed");
}
if (actual.length() != 4) {
    throw new AssertionError("Unexpected length");
}
~~~

Trong đoạn này, `actual` gồm bốn ký tự: `A`, LF, `B` và space. Đây là **đoạn code đặt trong method**, không phải class độc lập.

Với trường hợp thất bại, kiểm thử loại ngoại lệ chứ không phụ thuộc nguyên văn message của JDK:

~~~java
try {
    "\\q".translateEscapes();
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    // Đúng: \q không thuộc tập escape Java hợp lệ.
}
~~~

Để đảm bảo dữ liệu đúng mức byte (khi hợp đồng yêu cầu), encode với charset đã chọn và dùng `Arrays.equals(expectedBytes, actualBytes)`. `String.equals()` kiểm tra **ký tự**, còn encoding quyết định **bytes**. Khi ký số hay hash một payload, chỉ cần một LF, CR hoặc dấu cách khác đi cũng có thể khiến bytes không còn khớp.

**Checklist kiểm thử có giá trị:** `\n`, `\s`, `\t`, `\\`, `\"`, octal ở ranh giới `\377`, chuỗi không có backslash, escape sai, backslash cuối chuỗi, đầu vào đã giải mã và trường hợp có literal path/regex cần giữ nguyên.

## 14. Bài thực hành và tiêu chí đạt

**Bài 1 — Ký tự nguồn hay ký tự runtime?** Cho `String raw = "A\\nB";`. Dự đoán `raw.length()`, `raw.translateEscapes().length()` và giá trị `equals("A\nB")`. **Đạt** khi giải thích được vì sao lần lượt là 4, 3, `true`.

**Bài 2 — Tạo template runtime:** Dữ liệu đầu vào là văn bản `Name:\s%s\n`. Viết mã mô phỏng đầu vào này thành `String`, gọi `translateEscapes()` một lượt, rồi dùng `formatted("Ada")`. **Đạt** khi chuỗi có dạng `Name: Ada` + LF và biết tại sao phải giải escape trước khi in.

**Bài 3 — Kiểm thử đầu vào sai:** Viết hàm gọi `translateEscapes()` trên `\q`, `\u0041` và backslash đứng cuối. **Đạt** khi cả ba được báo là `IllegalArgumentException` và nêu được lý do, không âm thầm đổi sang dữ liệu khác.

**Bài 4 — Giải mã hai lần:** Dùng chuỗi runtime chứa hai backslash và chữ `n`. Gọi `translateEscapes()` một lần rồi hai lần; so sánh với newline thật. **Đạt** khi giải thích được vì sao giải mã lặp làm đổi ý nghĩa và cách thiết kế ranh giới giải mã một lượt.

**Bài 5 — Bảo toàn đường dẫn và regex:** Cho `"C:\\temp\\new"` và `"\\d+"` ở dạng Java literal. **Đạt** khi biết chúng là dữ liệu phải giữ nguyên hoặc gửi đúng parser, giải thích tác hại nếu dùng `translateEscapes()` một cách không có hợp đồng.

**Bài 6 — Octal và bytes:** Giải `"\\040\\011\\377"` và nêu mã ký tự; encode ký tự cuối bằng UTF-8. **Đạt** khi cho kết quả `32,9,255` và byte `C3 BF`, không nhầm ký tự U+00FF với byte `FF`.

## 15. Tài liệu tham khảo chính thức

- [Oracle Java SE 25 API — String.translateEscapes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#translateEscapes()) — hợp đồng, escape được hỗ trợ, lỗi `IllegalArgumentException`, giới hạn Unicode.
- [Oracle Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html) — text blocks, escape và các API chuỗi liên quan từ Java 15.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378) — mốc chuẩn hóa text blocks và xử lý escape.
- [Java Language Specification `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7) — cú pháp escape chính thức, bao gồm octal và line continuation.
- [OpenJDK String.java](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/String.java) — mã nguồn triển khai `translateEscapes()` (dùng để đối chiếu hành vi, không phụ thuộc vào chi tiết nội bộ khi viết ứng dụng).

**Ghi nhớ:** `String.translateEscapes()` giải mã **một lần** các Java escape có trong **dữ liệu runtime**. Nó hữu ích khi đầu vào được quy định rõ là Java-escaped text; không nên gọi để “làm sạch mọi chuỗi” hay để giải JSON, regex, Unicode escapes và đường dẫn. Kiểm tra hợp đồng dữ liệu, xử lý `IllegalArgumentException`, và test ký tự/bytes thực tế thay vì chỉ quan sát console.
