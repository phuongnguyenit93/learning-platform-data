# Escape code point và cú pháp Java chứa biểu thức chính quy

## Mục tiêu

Khi viết biểu thức chính quy (regular expression, hay regex) để xử lý Unicode trong Java, cần phân biệt **mã điểm Unicode (code point)**, **đơn vị mã UTF-16** và **cú pháp escape của Java so với cú pháp escape của regex**. Sau bài này, bạn có thể:

- Biểu diễn một ký tự bằng `U+...`, `\xhh`, `\uhhhh`, `\x{...}` hoặc tên Unicode khi thích hợp.
- Đặt regex trong chuỗi Java mà không làm mất dấu gạch chéo ngược `\\`.
- Tìm đúng ký tự ngoài Basic Multilingual Plane (BMP), ví dụ U+1F600, và hiểu vị trí `Matcher.start()`/`end()`.
- Kết hợp các lớp ký tự Unicode, dấu tổ hợp và chuẩn hóa Unicode mà không nhầm lẫn chúng với code point.
- Phân biệt lỗi biên dịch chuỗi Java với `PatternSyntaxException` khi phân tích regex.

Các ví dụ dùng API `java.util.regex.Pattern`/`Matcher` còn được hỗ trợ trong Java hiện đại. Chương trình minh họa chạy với JDK 17 trở lên.

## 1. Code point, UTF-16 và ký tự người dùng nhìn thấy

Unicode gán cho mỗi mã điểm một số, thường viết `U+0041` (A), `U+00E9` (é), `U+0301` (dấu sắc tổ hợp) hoặc `U+1F600` (biểu tượng mặt cười). Các giá trị Unicode nằm từ U+0000 đến U+10FFFF; vùng surrogate U+D800–U+DFFF không phải mã điểm vô hướng hợp lệ để biểu diễn ký tự độc lập.

`String` của Java được đánh chỉ mục theo **UTF-16 code unit**:

- Ký tự thuộc BMP (không kể surrogate) dùng một đơn vị mã 16 bit. Ví dụ `é` ở U+00E9 chiếm một vị trí `char`.
- Ký tự ngoài BMP dùng **surrogate pair**, gồm hai `char`. Ví dụ U+1F600 tương ứng `D83D DE00`.
- `String.length()`, `charAt()`, `substring()` và chỉ số `Matcher.start()`/`Matcher.end()` tính theo **UTF-16 offset**, không phải số code point.
- Một ký tự người dùng nhìn thấy (grapheme cluster) có thể gồm nhiều code point. Chẳng hạn `e` + U+0301 có hai code point nhưng thường hiển thị thành một chữ é.

Để đếm mã điểm, dùng `String.codePointCount(0, text.length())` hoặc duyệt `text.codePoints()`. Để tạo `String` từ một code point ngoài BMP, dùng `new String(Character.toChars(0x1F600))`. Đừng tự ý lấy `charAt()` hay cắt `substring()` tại giữa surrogate pair.

## 2. Những escape hữu ích trong Java regex

Bảng dưới mô tả **cú pháp mà bộ phân tích `Pattern` nhận được**, rồi đối chiếu với cách viết trong Java source:

| Cú pháp regex | Ý nghĩa | Chuỗi Java chứa regex |
| --- | --- | --- |
| `\x41` | Giá trị hex đúng **hai** chữ số; ở đây là `A` (U+0041) | `"\\x41"` |
| `\u00E9` | Giá trị hex đúng **bốn** chữ số UTF-16; ở đây là `é` (U+00E9) | `"\\u00E9"` |
| `\x{1F600}` | Một code point Unicode viết bằng số hex dài linh hoạt; biểu diễn cả ngoài BMP | `"\\x{1F600}"` |
| `\N{WHITE SMILING FACE}` | Một ký tự theo **tên Unicode** được JDK nhận biết (U+263A) | `"\\N{WHITE SMILING FACE}"` |
| `\p{L}` / `\P{L}` | Một mã điểm thuộc / không thuộc nhóm Unicode Letter | `"\\p{L}"` / `"\\P{L}"` |
| `\p{M}` | Dấu kết hợp (Unicode Mark), hữu ích với chữ có dấu được tách mã điểm | `"\\p{M}"` |
| `\Q...\E` | Giữ nguyên các dấu đặc biệt regex trong đoạn được quote | `"\\Q[a-z]+\\E"` |
| `\\` | Khớp đúng một dấu gạch chéo ngược `\\` | `"\\\\"` |

Có thể dùng các escape điều khiển `\t`, `\n`, `\r` và `\f` trong regex. Ký hiệu `\x{...}` là lựa chọn rõ ràng nhất khi cần chỉ **một code point cụ thể**, nhất là code point lớn hơn U+FFFF. `\u` trong regex chỉ mang bốn chữ số hex, nên **`\u1F600` không phải** cách viết đúng cho U+1F600; dùng `\x{1F600}` hoặc hai `\u` tương ứng surrogate pair.

Tên trong `\N{...}` là tên ký tự Unicode thực sự, không phải nhãn tự đặt. Các cú pháp không hợp lệ hoặc code point vượt U+10FFFF sẽ làm `Pattern.compile(...)` ném `PatternSyntaxException`. Khi cần đối sánh ký tự Unicode theo nhóm, sử dụng `\p{...}` thường dễ bảo trì hơn việc liệt kê hàng loạt mã hex.

## 3. Hai tầng escape: mã nguồn Java và bộ máy regex

Một regex đặt trong Java literal đi qua **hai bước**:

1. Trình biên dịch Java đọc literal, xử lý backslash Java. Trong mã nguồn `"\\x{1F600}"` có **hai dấu `\\` liên tiếp** trước `x` để tạo thành chuỗi runtime chứa **một dấu `\\`**.
2. `Pattern.compile` đọc chuỗi runtime `\x{1F600}` và hiểu đó là mã điểm Unicode U+1F600.

~~~java
String regex = "\\x{1F600}"; // Chuỗi runtime chứa: \x{1F600}
Pattern pattern = Pattern.compile(regex);
~~~

`Pattern.compile("\x{1F600}")` **không biên dịch được** vì `\x` không phải Java string escape hợp lệ. Ngược lại, trong tệp cấu hình chứa **nội dung regex thuần**, có thể ghi `\x{1F600}` rồi chuyển nội dung đọc được vào `Pattern.compile`; không tự thêm backslash chỉ vì đã quen cú pháp Java source. Nếu tệp có một lớp escaping riêng (ví dụ JSON), phải tuân theo cả lớp đó.

Java còn có **Unicode escape ở mức văn bản nguồn**: chuỗi ký tự nguồn `\u00E9` được compiler xử lý rất sớm, trước cả khi phân tích literal. Vì vậy `"\u00E9"` chứa trực tiếp ký tự é, còn `"\\u00E9"` chứa sáu ký tự biểu diễn escape regex; cả hai đều có thể tạo một `Pattern` khớp é nhưng bản thân hai `String` không bằng nhau. Unicode escape nguồn `\u000A` có thể biến thành ký tự xuống dòng **trước bước phân tích Java**, làm hỏng source nếu đặt trong string literal; hãy dùng Java escape `"\n"` cho dòng mới. Text block của Java cũng có xử lý escape, không phải raw string.

Một ví dụ phân biệt dấu backslash literal:

~~~java
Pattern backslash = Pattern.compile("\\\\");
boolean ok = backslash.matcher("\\").matches(); // true
~~~

Trong regex có hai backslash liên tiếp để khớp một backslash; để tạo **hai** backslash đó qua Java source cần viết **bốn**. Tương tự, Java literal `"\b"` là ký tự backspace, còn `"\\b"` là regex word boundary; chúng có ý nghĩa hoàn toàn khác.

## 4. Ví dụ chạy được: khớp code point ngoài BMP

Lưu thành `RegexCodePointDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexCodePointDemo {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String text = "A" + emoji + "B";

        Matcher matcher = Pattern.compile("\\x{1F600}").matcher(text);
        boolean found = matcher.find();
        System.out.println("found=" + found);
        if (found) {
            System.out.println("span=" + matcher.start() + ".." + matcher.end());
        }

        System.out.println("utf16Length=" + text.length());
        System.out.println("codePointCount=" + text.codePointCount(0, text.length()));
        System.out.println("surrogateRegex="
                + Pattern.compile("\\uD83D\\uDE00").matcher(emoji).matches());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RegexCodePointDemo.java
java RegexCodePointDemo
~~~

Kết quả:

~~~text
found=true
span=1..3
utf16Length=4
codePointCount=3
surrogateRegex=true
~~~

`find()` phát hiện một đoạn con; nếu muốn khớp **toàn bộ** chuỗi, dùng `matches()`. Khoảng `1..3` nghĩa là bắt đầu tại UTF-16 offset 1 và kết thúc ngay trước offset 3: emoji chiếm hai `char`. Chuỗi `A + emoji + B` có bốn UTF-16 code unit nhưng chỉ ba code point. Cách regex `\\uD83D\\uDE00` cũng khớp cùng emoji, song `\\x{1F600}` diễn đạt rõ một code point và ít phụ thuộc chi tiết surrogate pair hơn.

## 5. Escape Unicode theo thuộc tính, dấu tổ hợp và chuẩn hóa

Khi cần tìm **nhóm** ký tự, không nên liệt kê từng code point:

- `\p{L}`: Unicode Letter, gồm chữ cái của nhiều hệ chữ viết.
- `\p{M}`: Unicode Mark, gồm dấu có thể xuất hiện dưới dạng code point kết hợp riêng.
- `\p{Nd}`: Unicode decimal digit; thích hợp khi thực sự muốn nhận các chữ số thập phân nhiều hệ chữ viết.
- `\p{sc=Han}` hoặc `\p{IsHan}`: nhóm theo Unicode Script (cần phân biệt với category và block).
- `\P{L}`: phủ định của `\p{L}`.

Mặc định, các shorthand `\d`, `\w`, `\s` của `Pattern` có ý nghĩa ASCII đối với các lớp xác định sẵn. Nếu muốn dùng phiên bản Unicode, bật `Pattern.UNICODE_CHARACTER_CLASS` (tương đương inline flag `(?U)`); chế độ này cũng bật Unicode-aware case folding. Khi khớp không phân biệt hoa/thường, `CASE_INSENSITIVE` kết hợp `UNICODE_CASE` cho xử lý Unicode thay vì chỉ ASCII. Đừng bật flag ngoài nhu cầu: nó có thể thay đổi tập ký tự được chấp nhận.

Biểu thức `\p{L}[\p{L}\p{M}]*` dùng ký tự đầu là Letter, các ký tự sau là Letter hoặc Mark. Nó cho phép các dấu kết hợp, nhưng **không phải bộ kiểm tra tên người phổ quát**: quy tắc nghiệp vụ vẫn phải quyết định khoảng trắng, dấu nối, ký tự riêng của ngôn ngữ, độ dài và chuẩn hóa.

Hai chuỗi trông giống nhau có thể khác mã điểm: `é` là U+00E9, còn `e` + U+0301 là dạng phân rã. Regex khớp chính xác một code point không tự động coi chúng là tương đương. Nếu dữ liệu cần so sánh thống nhất, hãy chuẩn hóa bằng `java.text.Normalizer` (thường là NFC). `Pattern.CANON_EQ` có tồn tại nhưng có chi phí và rủi ro tài nguyên, nên không phải lựa chọn mặc định.

Cuối cùng, `\X` khớp một **extended grapheme cluster** (đơn vị người dùng thường thấy là một ký tự), không đồng nghĩa với một code point. Ví dụ `e` + dấu sắc kết hợp là hai code point nhưng một grapheme cluster; không thể thay mọi phép kiểm tra mã điểm bằng `\X` vì chúng giải quyết hai bài toán khác nhau.

Lưu thành `UnicodeTextMatchDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeTextMatchDemo {
    public static void main(String[] args) {
        String decomposed = "e" + Character.toString(0x0301);
        Pattern eAcute = Pattern.compile("\\x{00E9}");

        System.out.println("beforeNfc="
                + eAcute.matcher(decomposed).matches());
        String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("afterNfc="
                + eAcute.matcher(normalized).matches());

        Pattern lettersAndMarks =
                Pattern.compile("\\p{L}[\\p{L}\\p{M}]*");
        System.out.println("lettersAndMarks="
                + lettersAndMarks.matcher("Cafe" + Character.toString(0x0301)).matches());

        String nonAsciiDigit = Character.toString(0x0661);
        System.out.println("asciiDigit="
                + Pattern.compile("\\d").matcher(nonAsciiDigit).matches());
        System.out.println("unicodeDigit="
                + Pattern.compile("\\d", Pattern.UNICODE_CHARACTER_CLASS)
                         .matcher(nonAsciiDigit).matches());

        System.out.println("graphemeCount="
                + Pattern.compile("\\X").matcher(decomposed).results().count());
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeTextMatchDemo.java
java UnicodeTextMatchDemo
~~~

~~~text
beforeNfc=false
afterNfc=true
lettersAndMarks=true
asciiDigit=false
unicodeDigit=true
graphemeCount=1
~~~

Chương trình trên minh họa ba khác biệt độc lập: hai biểu diễn Unicode của chữ é; phạm vi ASCII/Unicode của `\d`; và code point so với grapheme cluster. Phương thức `Matcher.results()` có trong Java hiện đại và dùng được với JDK 17+.

## 6. Khi cần khớp nguyên văn ký tự và chuỗi nhập vào

Các ký tự `.`, `+`, `*`, `?`, `(`, `[`, `{` và `\\` có thể mang nghĩa đặc biệt trong regex. Nếu đối tượng cần tìm là chuỗi literal do người dùng hoặc cấu hình cung cấp, nên dùng `Pattern.quote(text)` thay vì tự chèn backslash vào từng ký tự. Phương thức này xử lý an toàn cả trường hợp chuỗi đầu vào chứa chính ký hiệu `\E`.

~~~java
String input = "a+b";
Pattern literal = Pattern.compile("^" + Pattern.quote(input) + "$");

System.out.println(literal.matcher("a+b").matches());  // true
System.out.println(literal.matcher("aaab").matches()); // false
~~~

Cú pháp regex `\Q...\E` cũng quote một đoạn cố định; ví dụ `"\\Q[a-z]+\\E"` khớp đúng chuỗi `[a-z]+`. Khi muốn coi **toàn bộ** regex là literal và không dùng thêm anchor hay nhóm, `Pattern.compile(text, Pattern.LITERAL)` là một lựa chọn khác. Không đưa dữ liệu người dùng trực tiếp vào regex nếu mục đích chỉ là tìm đúng văn bản đó.

## 7. Các lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Java báo `illegal escape character` ở `"\x{1F600}"` | Escape regex bị Java compiler hiểu trước | Viết `"\\x{1F600}"` |
| Regex không khớp U+1F600 khi viết `\u1F600` | `\u` chỉ nhận bốn hex digit, không nhận mã sáu ký tự | Dùng `\x{1F600}` |
| `start()/end()` lệch so với số ký tự nhìn thấy | Chỉ số thuộc UTF-16 code unit | Dùng `codePointCount` khi cần đếm code point; không cắt giữa surrogate pair |
| Chữ có dấu nhìn giống nhau nhưng regex khớp khác nhau | Dạng NFC và dạng decomposed có dãy code point khác | Chuẩn hóa dữ liệu theo một chính sách thống nhất, thường là NFC |
| `\d` không khớp chữ số ngoài ASCII | Chưa bật Unicode character class | Dùng `\p{Nd}` hoặc `UNICODE_CHARACTER_CLASS` theo yêu cầu |
| `\p{L}+` loại chuỗi chứa dấu kết hợp | Dấu kết hợp thuộc `Mark`, không phải `Letter` | Cân nhắc `\p{M}` và quy tắc cú pháp đầu/cuối |
| Dấu `+` trong từ khóa đầu vào bị hiểu là lượng từ | Chuỗi đầu vào được coi là regex | Dùng `Pattern.quote` khi tìm literal |
| `PatternSyntaxException` với escape `\x{...}` | Hex sai định dạng, thiếu dấu `}` hoặc ngoài dải Unicode | Kiểm tra cú pháp và giá trị code point trước khi biên dịch pattern |

Khi debug một pattern tạo ra từ mã nguồn, hãy **in chính chuỗi runtime** `pattern.pattern()` hoặc giá trị trước khi gọi `Pattern.compile`; kiểm tra xem nó chứa một hay hai dấu backslash. Nếu `javac` từ chối source, lỗi thuộc tầng Java literal; nếu source biên dịch được nhưng `Pattern.compile` ném `PatternSyntaxException`, lỗi thuộc tầng regex. Với nội dung đọc từ file, đừng giả định các quy tắc Java literal vẫn áp dụng nguyên xi.

## 8. Checklist áp dụng

1. Xác định mục tiêu là **một code point**, **lớp ký tự Unicode**, **chuỗi literal** hay **grapheme cluster**.
2. Dùng `\x{HEX}` cho code point rõ ràng, nhất là ngoài BMP; dùng `\p{...}` khi cần phân loại.
3. Nếu regex nằm trong Java string literal, escape từng backslash cho đúng; nếu đến từ dữ liệu bên ngoài, chỉ áp dụng escaping tương ứng với định dạng lưu trữ đó.
4. Với dữ liệu có dấu, quy định có chuẩn hóa NFC hay không và có chấp nhận combining mark hay không.
5. Khi xử lý kết quả khớp, nhớ rằng chỉ số `Matcher` là UTF-16 offsets; kiểm thử ít nhất một code point ngoài BMP.
6. Với nội dung động cần khớp nguyên văn, dùng `Pattern.quote`; dùng `matches()` cho toàn bộ đầu vào, `find()` để tìm đoạn con.
7. Viết test gồm BMP, ngoài BMP, ký tự có dấu dạng composed/decomposed, non-ASCII digit và ký tự metacharacter như `+`.

## Tài liệu tham khảo hiện hành

- Java API — `java.util.regex.Pattern`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html
- Java Language Specification — Unicode escapes, string literals và text blocks: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html
- Java API — `java.text.Normalizer`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html
