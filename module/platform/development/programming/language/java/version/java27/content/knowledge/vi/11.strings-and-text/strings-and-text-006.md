# Biểu thức chính quy bằng Pattern và Matcher trong Java 27

Khi xử lý văn bản, ta thường cần xác nhận một mã đơn hàng đúng định dạng, tìm tất cả số trong thông điệp, tách các trường được phân cách bằng dấu phẩy, che một phần dữ liệu nhạy cảm hoặc trích xuất thông tin từ nhật ký. **Biểu thức chính quy** (*regular expression*, viết tắt là *regex*) mô tả các quy tắc nhận diện chuỗi ký tự. Java cung cấp bộ công cụ chính thức trong gói `java.util.regex`, chủ yếu gồm **`Pattern`**, **`Matcher`** và **`MatchResult`**.

Trong **Java 27**, những API này vẫn là cách chuẩn để tìm kiếm, kiểm tra, tách và thay thế văn bản bằng regex. Bài học trình bày từ cú pháp đến cách vận dụng an toàn với Unicode, dữ liệu đầu vào không tin cậy và các bài toán thực tế; chỉ dùng tính năng Java hiện hành, không phụ thuộc API lỗi thời hay tính năng preview.

Nguồn đối chiếu chính thức: [Java SE 27 – Pattern](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html), [Matcher](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Matcher.html), [MatchResult](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/MatchResult.html) và [PatternSyntaxException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/PatternSyntaxException.html).

## 1. Ba thành phần của regex trong Java

| Thành phần | Vai trò | Đặc điểm |
| --- | --- | --- |
| `Pattern` | Biểu thức chính quy **đã biên dịch** | Bất biến; có thể dùng lại và chia sẻ giữa các luồng |
| `Matcher` | Thực hiện tìm khớp trên một `CharSequence` | Có trạng thái; **không an toàn** để dùng chung đồng thời giữa các luồng |
| `MatchResult` | Cung cấp thông tin về một kết quả khớp | Truy vấn đoạn khớp, nhóm, vị trí bắt đầu/kết thúc; không cho điều khiển quá trình tìm |

Luồng cơ bản là **biên dịch regex thành Pattern → tạo Matcher cho văn bản → gọi một thao tác tìm khớp → đọc kết quả**:

~~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexFirstExample {
    public static void main(String[] args) {
        Pattern invoice = Pattern.compile("INV-\\d{4}");
        Matcher matcher = invoice.matcher("Đơn A: INV-0248; đơn B: INV-1052");

        while (matcher.find()) {
            System.out.println(matcher.group());
        }
        // INV-0248
        // INV-1052
    }
}
~~~~

Trong ví dụ này, `\\d` đại diện chữ số (mặc định là `[0-9]` khi chưa bật chế độ lớp ký tự Unicode) và `{4}` yêu cầu đúng bốn lần xuất hiện. `find()` tìm từng đoạn phù hợp; `group()` lấy nội dung đoạn khớp gần nhất.

Có thể hình dung mối quan hệ:

~~~~text
Regex: "INV-\\d{4}"
        |
        v
Pattern.compile(...)   -> Pattern bất biến, dùng lại
        |
        +-- matcher(văn bản A) -> Matcher A, trạng thái riêng
        |
        +-- matcher(văn bản B) -> Matcher B, trạng thái riêng
~~~~

Nếu cùng một quy tắc được dùng nhiều lần, nên biên dịch một lần (thường lưu trong `private static final Pattern`) và tạo `Matcher` mới cho mỗi văn bản. `Pattern.matches(regex, input)` là phương thức tiện lợi cho một lần kiểm tra nhưng **biên dịch lại** regex mỗi khi gọi.

## 2. Vì sao phải viết hai dấu gạch chéo ngược?

Một regex có thể chứa `\d`, `\s`, `\w` hoặc `\b`. Nhưng khi viết nó trong **chuỗi Java**, ký tự `\` còn có vai trò mở đầu escape của Java. Vì vậy cần phân biệt hai tầng:

| Muốn regex engine nhận | Mã chuỗi Java cần viết | Ý nghĩa |
| --- | --- | --- |
| `\d+` | `"\\d+"` | Một hay nhiều chữ số |
| `\s+` | `"\\s+"` | Một hay nhiều ký tự khoảng trắng |
| `\.` | `"\\."` | Dấu chấm thật thay vì ký tự bất kỳ |
| `\bword\b` | `"\\bword\\b"` | Từ `word` tại hai ranh giới từ |
| `\\` | `"\\\\"` | Một dấu gạch chéo ngược trong văn bản |

Ví dụ:

~~~~java
Pattern dot = Pattern.compile("\\.");     // Tìm dấu chấm thật
Pattern number = Pattern.compile("\\d+"); // Tìm dãy chữ số

System.out.println(dot.matcher("a.b").find());    // true
System.out.println(number.matcher("x123").find()); // true
~~~~

Nếu viết `"."` làm regex, dấu chấm là ký tự đặc biệt khớp với một ký tự bất kỳ (trừ một số ký tự kết thúc dòng trong chế độ mặc định). Nếu viết `"\\b"` sai thành `"\b"`, Java sẽ tạo ký tự backspace, làm regex có nghĩa khác hoàn toàn.

**Text block** của Java cũng xử lý escape; nó không biến văn bản thành raw regex. Quy tắc phân biệt tầng escape vẫn áp dụng khi đặt regex trong text block.

## 3. Cú pháp regex cần nắm

### 3.1. Ký tự thường, lớp ký tự và lớp có sẵn

| Regex | Ý nghĩa | Ví dụ khớp |
| --- | --- | --- |
| `cat` | Chính xác chuỗi `cat` | `cat` |
| `.` | Một ký tự bất kỳ, tùy chế độ đối với xuống dòng | `A` |
| `[abc]` | Một trong ba ký tự `a`, `b`, `c` | `b` |
| `[A-Z]` | Chữ cái viết hoa ASCII từ A đến Z | `Q` |
| `[^0-9]` | Một ký tự không thuộc dãy chữ số ASCII | `x` |
| `[a-zA-Z0-9_]` | Chữ, số ASCII hoặc dấu gạch dưới | `_` |
| `\d` | Chữ số; mặc định ASCII, có thể thay đổi theo flag | `5` |
| `\D` | Ký tự không thuộc `\d` | `!` |
| `\s` | Khoảng trắng theo chế độ của regex | Dấu cách, tab |
| `\S` | Ký tự không thuộc `\s` | `X` |
| `\w` | Ký tự “word”; mặc định `[a-zA-Z_0-9]` | `x` |
| `\W` | Ký tự không thuộc `\w` | `-` |
| `\p{L}` | Ký tự thuộc phân loại Unicode Letter | `Đ` |
| `\p{M}` | Dấu kết hợp Unicode (*combining mark*) | Dấu thanh tách rời |
| `\p{Nd}` | Chữ số thập phân Unicode | `7` |
| `\R` | Một chuỗi ngắt dòng Unicode | `\r\n` |
| `\X` | Một cụm ký tự đồ họa Unicode mở rộng (*grapheme cluster*) | Ký tự có dấu và các mã kết hợp |

Với tiếng Việt, `[a-zA-Z]` không bao phủ nhiều chữ có dấu. `\p{L}` có phạm vi rộng hơn nhưng các chuỗi Unicode có dấu tổ hợp có thể chứa thêm `\p{M}`. Chọn regex dựa trên **quy tắc dữ liệu thực**, không mặc định mọi “chữ cái” đều là ASCII.

Ví dụ nhận diện một mã sản phẩm chỉ gồm chữ cái Latin viết hoa và chữ số ASCII:

~~~~java
Pattern productCode = Pattern.compile("[A-Z]{2,5}-[0-9]{3,6}");

System.out.println(productCode.matcher("ABC-2501").matches());  // true
System.out.println(productCode.matcher("ABC_2501").matches());  // false
~~~~

Ở đây dùng `[0-9]` là chủ đích vì hệ thống chỉ cho phép mã số ASCII. Nếu nghiệp vụ chấp nhận số từ những hệ chữ viết khác, cần kiểm tra định nghĩa “số” và cách chuẩn hóa trước khi dùng `\p{Nd}`.

### 3.2. Lượng từ (quantifier)

Lượng từ biểu thị số lần một thành phần được phép xuất hiện:

| Cú pháp | Số lần xuất hiện | Ví dụ |
| --- | --- | --- |
| `X?` | 0 hoặc 1 | `colou?r` |
| `X*` | 0 hoặc nhiều | `ab*` |
| `X+` | 1 hoặc nhiều | `ab+` |
| `X{3}` | Đúng 3 | `[0-9]{3}` |
| `X{2,}` | Từ 2 trở lên | `[A-Z]{2,}` |
| `X{2,5}` | Từ 2 đến 5 | `[A-Z]{2,5}` |

Ví dụ cho phép mã có 2–4 chữ cái viết hoa và đúng 3 chữ số:

~~~~java
Pattern code = Pattern.compile("[A-Z]{2,4}-\\d{3}");

System.out.println(code.matcher("AB-123").matches());   // true
System.out.println(code.matcher("ABCDE-123").matches()); // false
~~~~

Lượng từ thường ở chế độ **greedy**: thử nhận nhiều nhất có thể rồi lùi lại nếu cần. Java còn hỗ trợ **reluctant** (`*?`, `+?`, `??`) và **possessive** (`*+`, `++`, `?+`):

~~~~java
String input = "<b>one</b><i>two</i>";

System.out.println(
        Pattern.compile("<.*>").matcher(input).find()); // true

Matcher reluctant = Pattern.compile("<.*?>").matcher(input);
while (reluctant.find()) {
    System.out.println(reluctant.group());
}
// <b>, </b>, <i>, </i>
~~~~

`<.*>` sẽ khớp một đoạn dài từ dấu mở đầu đến dấu kết thúc cuối cùng có thể sử dụng; `<.*?>` ưu tiên điểm kết thúc sớm hơn. Ví dụ chỉ minh họa cơ chế lượng từ: **không dùng regex tổng quát để phân tích HTML/XML đầy đủ**, vì hai định dạng này cần parser chuyên dụng.

Lượng từ possessive không nhả lại ký tự đã nhận để thử nhánh khác:

~~~~java
System.out.println(Pattern.matches("a+a", "aaa"));  // true
System.out.println(Pattern.matches("a++a", "aaa")); // false
~~~~

Với `a++a`, phần `a++` đã nhận hết các ký tự `a` và không backtrack cho `a` ở cuối. Kỹ thuật possessive hữu ích để hạn chế backtracking khi phù hợp với ngữ nghĩa cần nhận diện.

### 3.3. Ranh giới và neo (anchor)

| Regex | Ý nghĩa |
| --- | --- |
| `^` | Đầu input hoặc đầu dòng khi bật `MULTILINE` |
| `$` | Cuối input (có quy tắc riêng với ký tự kết thúc dòng) hoặc cuối dòng khi bật `MULTILINE` |
| `\A` | Đầu input tuyệt đối |
| `\z` | Cuối input tuyệt đối |
| `\Z` | Cuối input, có thể bỏ qua ký tự kết thúc dòng cuối |
| `\b` | Ranh giới từ theo quy tắc regex |
| `\B` | Vị trí không phải ranh giới từ |

Để xác minh **toàn bộ input**, `matcher.matches()` thường dễ đọc hơn việc tự bọc `^...$`, vì `matches()` kiểm tra toàn bộ vùng đối chiếu. Nếu dùng anchor trong regex, lưu ý `MULTILINE` thay đổi ý nghĩa của `^` và `$`.

Regex ranh giới từ hữu ích cho việc tìm `cat` trong `"a cat sleeps"` mà không nhận `"catalog"`:

~~~~java
Pattern word = Pattern.compile("\\bcat\\b");
System.out.println(word.matcher("a cat sleeps").find()); // true
System.out.println(word.matcher("catalog").find());      // false
~~~~

Ranh giới từ của regex không phải bộ tách từ tự nhiên cho mọi ngôn ngữ. Nếu cần phân đoạn từ tiếng Việt hoặc ngôn ngữ phức tạp, hãy xác định yêu cầu xử lý ngôn ngữ thay vì giả định `\b` luôn là ranh giới từ theo nghĩa ngôn ngữ học.

### 3.4. Phép chọn, nhóm và thứ tự ưu tiên

`|` diễn đạt “hoặc” giữa các nhánh. Dấu ngoặc đơn gom biểu thức thành một đơn vị:

~~~~java
Pattern imageName = Pattern.compile("photo\\.(?:jpg|jpeg|png)");

System.out.println(imageName.matcher("photo.jpeg").matches()); // true
System.out.println(imageName.matcher("photo.gif").matches());  // false
~~~~

`(?:...)` là **non-capturing group**: dùng để gom biểu thức nhưng không tạo nhóm dữ liệu có thể đọc qua `group(n)`. Nó hữu ích khi chỉ cần ưu tiên phép chọn, không cần trích xuất.

Không viết `photo\\.jpg|png` nếu muốn nhận `photo.jpg` hoặc `photo.png`: phép chọn khi đó có thể nhận nguyên chuỗi `png` mà không cần tiền tố `photo.`. Đặt các nhánh trong nhóm đúng vị trí.

## 4. `matches()`, `lookingAt()` và `find()`

Ba thao tác của Matcher phục vụ các yêu cầu khác nhau:

| Phương thức | Cách kiểm tra | Tình huống |
| --- | --- | --- |
| `matches()` | Toàn bộ vùng input phải khớp | Kiểm tra một giá trị đúng định dạng |
| `lookingAt()` | Phải khớp từ **đầu vùng input**, có thể không hết | Kiểm tra tiền tố |
| `find()` | Tìm một đoạn phù hợp ở vị trí tiếp theo | Trích xuất một hay nhiều kết quả trong văn bản |

Ví dụ:

~~~~java
Pattern pattern = Pattern.compile("[A-Z]{2}-\\d{3}");

System.out.println(pattern.matcher("AB-123").matches());       // true
System.out.println(pattern.matcher("AB-123 extra").matches()); // false

System.out.println(pattern.matcher("AB-123 extra").lookingAt()); // true
System.out.println(pattern.matcher("prefix AB-123").lookingAt()); // false

System.out.println(pattern.matcher("prefix AB-123").find()); // true
~~~~

Sau một lần tìm khớp **thành công**, `group()` lấy đoạn khớp, `start()` và `end()` trả về vị trí:

~~~~java
String text = "Phiếu AB-123, phiếu CD-456";
Matcher matcher = pattern.matcher(text);

while (matcher.find()) {
    System.out.printf("%s tại [%d, %d)%n",
            matcher.group(), matcher.start(), matcher.end());
}
// AB-123 tại [6, 12)
// CD-456 tại [20, 26)
~~~~

Vị trí `start()` bao gồm, `end()` loại trừ: đoạn văn bản tương ứng là `text.substring(start, end)`. Đó là **chỉ số UTF-16** của `CharSequence`, không phải số byte UTF-8 và cũng không phải số grapheme/“ký tự nhìn thấy” trong Unicode.

**Lưu ý trạng thái:** gọi `group()`, `start()` hoặc `end()` trước một lần khớp thành công sẽ ném `IllegalStateException`. Một lần tìm thất bại cũng không cung cấp match hiện hành để đọc:

~~~~java
Matcher matcher = Pattern.compile("\\d+").matcher("no digits");
if (matcher.find()) {
    System.out.println(matcher.group());
} else {
    System.out.println("Không tìm thấy số");
}
~~~~

Nếu cần tìm từ đầu lại hoặc thay input, dùng `matcher.reset()` hoặc `matcher.reset(newInput)`. Đừng dùng cùng một Matcher giữa những lời gọi độc lập mà không kiểm soát trạng thái hiện tại của nó.

### 4.1. Giới hạn tìm trong một vùng với `region`

`Matcher.region(start, end)` chỉ cho phép tìm trong một đoạn của input:

~~~~java
String source = "abc123xyz456";
Matcher matcher = Pattern.compile("\\d+").matcher(source);

matcher.region(6, source.length());
System.out.println(matcher.find());  // true
System.out.println(matcher.group()); // 456
System.out.println(matcher.start()); // 9: vị trí trong input gốc
~~~~

Vùng `[start, end)` có điểm kết thúc loại trừ. Mặc định region có **anchoring bounds**, nghĩa là các anchor như `^` và `$` có thể xét ranh giới vùng như ranh giới input. Mặc định region có **opaque bounds**, nên lookaround không nhìn xuyên qua giới hạn vùng. Khi cần xử lý nâng cao, có thể xem `useAnchoringBounds(boolean)` và `useTransparentBounds(boolean)` của Matcher.

## 5. Capturing group, nhóm có tên và lookaround

### 5.1. Capturing group theo chỉ số

Dấu ngoặc tròn `(...)` mặc định tạo một **capturing group**. Các nhóm được đánh số từ 1 theo thứ tự dấu ngoặc mở, còn `group(0)` là toàn bộ đoạn khớp:

~~~~java
Pattern id = Pattern.compile("([A-Z]{2})-(\\d{4})");
Matcher matcher = id.matcher("Mã: AB-2048");

if (matcher.find()) {
    System.out.println(matcher.group(0)); // AB-2048
    System.out.println(matcher.group(1)); // AB
    System.out.println(matcher.group(2)); // 2048
    System.out.println(matcher.groupCount()); // 2
}
~~~~

`groupCount()` không tính group 0. Với nhóm tùy chọn không tham gia vào lần khớp thành công, `group(n)` trả về `null`, còn `start(n)`/`end(n)` trả về `-1`. Trường hợp này khác nhóm tham gia nhưng khớp **chuỗi rỗng**, khi đó `group(n)` trả về `""`.

### 5.2. Named capturing group

Cú pháp `(?<name>...)` đặt tên cho nhóm để tránh phụ thuộc vào thứ tự đếm:

~~~~java
Pattern order = Pattern.compile(
        "(?<prefix>[A-Z]{3})-(?<year>\\d{4})-(?<seq>\\d{3})");
Matcher matcher = order.matcher("ORD-2026-042");

if (matcher.matches()) {
    System.out.println(matcher.group("prefix")); // ORD
    System.out.println(matcher.group("year"));   // 2026
    System.out.println(matcher.group("seq"));    // 042
}
~~~~

Tên nhóm phân biệt chữ hoa và chữ thường; mỗi tên phải duy nhất và theo cú pháp được Java quy định. `group("name")` giúp thể hiện ý nghĩa dữ liệu rõ hơn `group(2)` trong các regex dài. Java 27 còn có `namedGroups()` để lấy ánh xạ tên sang số thứ tự nhóm.

Backreference `\1` hoặc `\k<name>` yêu cầu một đoạn xuất hiện giống nội dung đã nhận bởi nhóm trước:

~~~~java
Pattern repeatedWord = Pattern.compile(
        "(?<word>[A-Za-z]+)\\s+\\k<word>");

System.out.println(repeatedWord.matcher("hello hello").matches()); // true
System.out.println(repeatedWord.matcher("hello world").matches()); // false
~~~~

Ví dụ so khớp chữ phân biệt hoa thường; nếu muốn bỏ qua hoa thường phải đưa vào cấu hình regex một cách có chủ đích.

### 5.3. Lookahead và lookbehind

**Lookaround** kiểm tra ngữ cảnh mà không tiêu thụ các ký tự trong đoạn kết quả:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `(?=X)` | Positive lookahead: phía sau phải khớp `X` |
| `(?!X)` | Negative lookahead: phía sau không được khớp `X` |
| `(?<=X)` | Positive lookbehind: phía trước phải khớp `X` |
| `(?<!X)` | Negative lookbehind: phía trước không được khớp `X` |

Ví dụ, lấy chữ số đứng sau dấu `#` nhưng không lấy chính dấu đó:

~~~~java
Pattern ticketNumber = Pattern.compile("(?<=#)\\d+");
Matcher matcher = ticketNumber.matcher("Vé #125, vé #207");

while (matcher.find()) {
    System.out.println(matcher.group());
}
// 125
// 207
~~~~

Regex có lookaround dài và các lượng từ lồng nhau có thể khó bảo trì và khó dự đoán hiệu năng. Nếu yêu cầu là phân tích một ngôn ngữ hoặc cấu trúc phức tạp, hãy cân nhắc parser hoặc thao tác chuỗi rõ ràng hơn.

## 6. Flags điều chỉnh cách diễn giải regex

Có thể truyền flags vào `Pattern.compile(regex, flags)` bằng phép `|` bit:

| Flag | Ảnh hưởng |
| --- | --- |
| `CASE_INSENSITIVE` | Bỏ qua hoa/thường khi khớp |
| `UNICODE_CASE` | Áp dụng quy tắc case folding Unicode khi dùng cùng chế độ bỏ qua hoa/thường |
| `MULTILINE` | `^` và `$` có thể khớp ở đầu/cuối từng dòng |
| `DOTALL` | `.` có thể khớp cả ký tự kết thúc dòng |
| `UNICODE_CHARACTER_CLASS` | Dùng phiên bản Unicode của các lớp ký tự có sẵn và POSIX; đồng thời bật Unicode case |
| `COMMENTS` | Cho phép khoảng trắng và chú thích trong regex theo quy tắc flag |
| `LITERAL` | Đọc toàn bộ biểu thức được cung cấp như ký tự literal, không phải cú pháp regex |
| `UNIX_LINES` | Chỉ nhận line terminator kiểu Unix trong các thao tác liên quan |

Ví dụ tìm một trường trên nhiều dòng, không phân biệt chữ hoa chữ thường:

~~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String text = """
        Mã: AB-2048
        Ghi chú: đã nhận
        MÃ: CD-1033
        """;

Pattern codeLine = Pattern.compile(
        "^mã:\\h*(?<code>[A-Z]{2}-\\d{4})$",
        Pattern.MULTILINE | Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

Matcher matcher = codeLine.matcher(text);
while (matcher.find()) {
    System.out.println(matcher.group("code"));
}
// AB-2048
// CD-1033
~~~~

Ở đây `MULTILINE` làm cho các anchor tác động trên từng dòng, còn `\\h*` chỉ nhận **khoảng trắng ngang** sau dấu hai chấm, tránh vô tình tiêu thụ ký tự xuống dòng như `\\s*` có thể làm.

Java cũng hỗ trợ các flag dạng inline như `(?i)`, `(?m)`, `(?s)`, hoặc giới hạn phạm vi bằng `(?i:...)`. Hãy chọn một cách cấu hình nhất quán để người đọc dễ nhận ra những quy tắc đang có hiệu lực.

### 6.1. Regex và Unicode trong dữ liệu tiếng Việt

Ở chế độ mặc định, `\\d`, `\\w` và `\\s` không bao trùm toàn bộ các lớp ký tự Unicode tương ứng. Khi thực sự cần hành vi Unicode, có thể bật:

~~~~java
Pattern unicodeWords = Pattern.compile(
        "\\w+", Pattern.UNICODE_CHARACTER_CLASS);

System.out.println(unicodeWords.matcher("Tiếng Việt").find()); // true
~~~~

Tuy nhiên, “ký tự Unicode” không đồng nghĩa với “tên người hợp lệ”, “từ tiếng Việt” hoặc “mọi chữ cái được nghiệp vụ chấp nhận”. Các quy tắc nghiệp vụ có thể cần phân biệt dấu kết hợp, ký tự điều khiển, chữ số ở hệ chữ viết khác hoặc những ký tự tương tự nhau về hình thức.

Nếu phải so sánh văn bản với các dạng Unicode tương đương (ví dụ chữ có dấu được biểu diễn bằng một code point hoặc một chuỗi ký tự tổ hợp), có thể chuẩn hóa với `java.text.Normalizer` theo dạng được hợp đồng quy định trước khi áp dụng regex. Không tự động loại dấu hoặc chuẩn hóa thông tin nhạy cảm nếu quy tắc đầu vào không cho phép.

**Không dùng `CANON_EQ` theo thói quen** để xử lý mọi chuỗi Unicode: API Java 27 có cảnh báo chế độ này có thể tiêu thụ nhiều bộ nhớ với dữ liệu chứa nhiều dấu kết hợp. Trong nhiều bài toán thông thường, chuẩn hóa có chủ đích và kiểm tra độ dài là hướng kiểm soát được hơn.

### 6.2. Chỉ số khớp và các ký tự Unicode nhiều đơn vị UTF-16

`Matcher.start()` và `end()` dùng offset trong `CharSequence`. Với một `String` Java, offset là vị trí **UTF-16 code unit**, nên một ký tự bổ sung ngoài Basic Multilingual Plane có thể chiếm hai đơn vị. Ví dụ emoji có thể làm vị trí hiển thị khác số code point hoặc số cụm grapheme.

Khi tính chiều dài văn bản theo người đọc, hãy phân biệt code unit, code point và grapheme cluster. Java hỗ trợ `String.codePoints()` và regex `\\X` cho một số công việc xử lý theo cụm ký tự; không coi `end() - start()` là số “ký tự nhìn thấy” trong mọi văn bản.

## 7. Thay thế bằng `replaceAll`, `replaceFirst` và `quoteReplacement`

### 7.1. Thay thế tĩnh

`Matcher.replaceAll(replacement)` tạo String mới với tất cả đoạn khớp được thay; `replaceFirst` chỉ thay đoạn khớp đầu tiên:

~~~~java
Pattern digits = Pattern.compile("\\d+");

System.out.println(digits.matcher("A12 B345").replaceAll("#"));
// A# B#

System.out.println(digits.matcher("A12 B345").replaceFirst("#"));
// A# B345
~~~~

Chuỗi thay thế có cú pháp riêng: `$1`, `$2` tham chiếu nhóm đánh số; dạng `${name}` tham chiếu nhóm có tên.

~~~~java
Pattern name = Pattern.compile("(?<first>[A-Za-z]+)\\s+(?<last>[A-Za-z]+)");
String result = name.matcher("An Nguyen").replaceAll("${last}, ${first}");
System.out.println(result); // Nguyen, An
~~~~

**Chú ý:** trong replacement, `$` và `\` có ý nghĩa đặc biệt. Nếu replacement đến từ người dùng hoặc cần được chèn **nguyên văn**, phải dùng `Matcher.quoteReplacement`:

~~~~java
String userReplacement = "$5\\docs";
String safeReplacement = Matcher.quoteReplacement(userReplacement);

String result = Pattern.compile("PLACEHOLDER")
        .matcher("Value: PLACEHOLDER")
        .replaceAll(safeReplacement);

System.out.println(result); // Value: $5\docs
~~~~

Không nhầm `Pattern.quote` với `Matcher.quoteReplacement`: một bên escape **biểu thức tìm kiếm**, bên còn lại escape **nội dung thay thế**.

### 7.2. Thay thế có tính toán cho từng match

Java 27 hỗ trợ overload `replaceAll(Function<MatchResult, String>)`. Mỗi lần khớp, lambda được gọi với kết quả của lần khớp đó:

~~~~java
Pattern number = Pattern.compile("\\d+");

String changed = number.matcher("A12 B345")
        .replaceAll(result -> "[" + result.group() + "]");

System.out.println(changed); // A[12] B[345]
~~~~

Kết quả String của lambda **vẫn được diễn giải theo cú pháp replacement**, nên nếu lambda tạo chuỗi có `$` hoặc `\` với ý nghĩa literal, phải bọc bằng `Matcher.quoteReplacement(...)`. Không sửa trạng thái của chính Matcher từ trong lambda; tài liệu API cảnh báo về việc thay đổi Matcher trong quá trình thay thế.

Với trường hợp cần xây dựng kết quả theo nhiều bước, Java còn hỗ trợ `appendReplacement(StringBuilder, ...)` và `appendTail(StringBuilder)`:

~~~~java
Matcher matcher = Pattern.compile("\\d+").matcher("A12 B345");
StringBuilder builder = new StringBuilder();

while (matcher.find()) {
    matcher.appendReplacement(builder, "[" + matcher.group() + "]");
}
matcher.appendTail(builder);

System.out.println(builder); // A[12] B[345]
~~~~

Không cần dùng phiên bản `StringBuffer` nếu ứng dụng chỉ xây dựng chuỗi trong một luồng; overload `StringBuilder` là API hiện hành và phù hợp cho trường hợp này.

### 7.3. Phân biệt `String.replace` và `String.replaceAll`

| API | Đối số tìm kiếm được hiểu là | Dùng khi |
| --- | --- | --- |
| `String.replace(CharSequence, CharSequence)` | Chuỗi literal | Chỉ đổi một đoạn văn bản cố định |
| `String.replaceAll(String, String)` | Regex | Cần thay các đoạn theo một mẫu |
| `Pattern.matcher(input).replaceAll(...)` | Pattern đã biên dịch | Cần tái sử dụng mẫu hoặc lấy nhóm và kết quả |

Ví dụ thay mọi dấu chấm **literal** trong tên tệp:

~~~~java
String fileName = "report.v2.txt";
System.out.println(fileName.replace(".", "_"));   // report_v2_txt
System.out.println(fileName.replaceAll("\\.", "_")); // report_v2_txt
~~~~

Nếu đã biết chuỗi cố định và không cần regex, `String.replace` thường rõ ý định hơn và tránh sai vì ký tự đặc biệt.

## 8. Tách chuỗi bằng `Pattern.split` và `splitAsStream`

`Pattern.split(input)` tách input tại những đoạn khớp với regex. Với cách tách theo dấu phẩy và khoảng trắng quanh dấu phẩy:

~~~~java
import java.util.Arrays;
import java.util.regex.Pattern;

Pattern comma = Pattern.compile("\\s*,\\s*");

System.out.println(Arrays.toString(comma.split("An, Binh, Lan")));
// [An, Binh, Lan]
~~~~

Phương thức `split(input, limit)` xử lý số phần tử đầu ra:

| `limit` | Hành vi chính |
| --- | --- |
| Dương | Áp dụng tối đa `limit - 1` lần tách; phần cuối giữ lại phần dữ liệu còn lại |
| 0 | Tách nhiều nhất có thể và **bỏ các chuỗi rỗng ở cuối** |
| Âm | Tách nhiều nhất có thể và **giữ các chuỗi rỗng ở cuối** |

~~~~java
Pattern comma = Pattern.compile(",");
String data = "A,B,";

System.out.println(Arrays.toString(comma.split(data)));
// [A, B]

System.out.println(Arrays.toString(comma.split(data, -1)));
// [A, B, ]

System.out.println(Arrays.toString(comma.split(data, 2)));
// [A, B,]
~~~~

`splitAsStream(input)` tạo `Stream<String>` từ các đoạn tách; các chuỗi rỗng cuối bị loại bỏ. Đây là API thuận tiện để tiếp tục lọc hoặc biến đổi dữ liệu:

~~~~java
Pattern comma = Pattern.compile("\\s*,\\s*");
java.util.List<String> codes = comma
        .splitAsStream(" AB-123, CD-456, EF-789 ")
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .toList();
~~~~

Với CSV đầy đủ, nơi trường có thể được đặt trong dấu nháy và chứa dấu phẩy hoặc xuống dòng, một regex tách theo dấu phẩy là **không đủ**. Hãy dùng parser CSV phù hợp với đặc tả đầu vào.

## 9. `Matcher.results()` và `Pattern` dưới dạng Predicate

### 9.1. Lấy danh sách các kết quả bằng Stream

`Matcher.results()` trả về một `Stream<MatchResult>` tuần tự, rất tiện khi cần trích xuất tất cả lần khớp:

~~~~java
import java.util.List;
import java.util.regex.MatchResult;
import java.util.regex.Pattern;

String text = "Đơn 103, đơn 204, đơn 305";

List<String> ids = Pattern.compile("\\d+")
        .matcher(text)
        .results()
        .map(MatchResult::group)
        .toList();

System.out.println(ids); // [103, 204, 305]
~~~~

Các `MatchResult` do stream trả về cung cấp dữ liệu của từng lần khớp. Đừng gọi thao tác khác làm thay đổi Matcher khi stream vẫn đang được duyệt. Nếu cần tái sử dụng Matcher sau khi kết thúc stream, nên `reset()` trước.

### 9.2. Predicate: toàn chuỗi hay chỉ một phần?

`Pattern.asMatchPredicate()` kiểm tra **toàn chuỗi** (tương đương `matches()`), trong khi `Pattern.asPredicate()` tìm **một đoạn khớp** (tương đương `find()`).

~~~~java
import java.util.List;
import java.util.regex.Pattern;

Pattern code = Pattern.compile("[A-Z]{2}-\\d{4}");
List<String> values = List.of("AB-2027", "prefix AB-2027", "BAD");

System.out.println(values.stream()
        .filter(code.asMatchPredicate())
        .toList());
// [AB-2027]

System.out.println(values.stream()
        .filter(code.asPredicate())
        .toList());
// [AB-2027, prefix AB-2027]
~~~~

Lựa chọn Predicate đúng theo mục tiêu của pipeline: **xác thực dữ liệu** thường cần toàn chuỗi; **phát hiện văn bản chứa mẫu** thường chỉ cần một đoạn.

## 10. Regex động và dữ liệu không tin cậy

### 10.1. Dùng `Pattern.quote` khi đầu vào là chuỗi cần tìm nguyên văn

Giả sử người dùng yêu cầu tìm chuỗi `a.b`. Nếu ghép trực tiếp vào regex, dấu chấm sẽ khớp với ký tự bất kỳ và tạo kết quả sai:

~~~~java
String keyword = "a.b"; // Nội dung do người dùng cung cấp

Pattern unsafe = Pattern.compile(keyword);
System.out.println(unsafe.matcher("aXb").find()); // true (không mong muốn)

Pattern literal = Pattern.compile(Pattern.quote(keyword));
System.out.println(literal.matcher("aXb").find()); // false
System.out.println(literal.matcher("a.b").find()); // true
~~~~

`Pattern.quote(keyword)` biến toàn bộ keyword thành biểu thức nhận đúng ký tự literal, kể cả nếu chuỗi chứa `.`, `*`, `[` hoặc dấu gạch chéo ngược. Với nhu cầu này cũng có thể dùng `Pattern.compile(keyword, Pattern.LITERAL)`.

Chỉ nên cho người dùng nhập **regex thực sự** khi sản phẩm có tính năng tìm kiếm regex rõ ràng và có biện pháp kiểm soát tài nguyên phù hợp.

### 10.2. Tránh regex quá tốn tài nguyên

Một số regex có các lựa chọn lồng nhau hoặc lượng từ lặp gây **backtracking rất lớn** trên chuỗi gần khớp. Ví dụ dạng `(a+)+$` có thể mất nhiều thời gian với một chuỗi dài gồm nhiều chữ `a` theo sau bởi ký tự không phù hợp.

Trong ứng dụng nhận dữ liệu không tin cậy:

- Giới hạn kích thước input trước khi chạy regex.
- Giữ regex đơn giản, tránh các lượng từ lồng nhau mơ hồ và những nhánh thay thế chồng lấp.
- Neo kiểm tra toàn chuỗi bằng `matches()` khi thực sự xác minh định dạng; đừng quét `find()` không cần thiết trên văn bản dài.
- Khi ngữ nghĩa cho phép, xem xét lượng từ possessive hoặc nhóm atomic `(?>...)` để tránh backtracking không cần thiết.
- Đánh giá độ phức tạp với cả input hợp lệ và những chuỗi gần khớp nhưng sai ở cuối.
- Dùng parser hay xử lý chuỗi chuyên dụng nếu bài toán cần cấu trúc nhiều cấp hoặc ngữ nghĩa phức tạp.

API `java.util.regex` không cung cấp trực tiếp tham số **timeout cho từng phép match**. Không nên coi việc hủy một tác vụ bên ngoài là bảo đảm rằng một lời gọi regex đã lập tức ngừng tiêu tốn tài nguyên. Với dữ liệu không đáng tin và regex do người dùng tùy ý định nghĩa, cần thiết kế giới hạn tài nguyên ở kiến trúc phù hợp và kiểm thử khả năng chống quá tải.

### 10.3. Tránh coi regex là bộ xác nhận mọi loại dữ liệu

Một regex có thể kiểm tra **hình dạng sơ bộ** của ngày, email hoặc URL, nhưng không nhất thiết xác nhận được ý nghĩa:

- `\\d{4}-\\d{2}-\\d{2}` có thể nhận `2026-02-30`, dù ngày này không tồn tại.
- Email có nhiều quy tắc cú pháp và chính sách thực tế; một regex ngắn không thay thế được xác minh địa chỉ hoặc chính sách chấp nhận email của sản phẩm.
- URI/URL cần API phân tích cú pháp và chính sách kiểm soát scheme/host/path tùy ngữ cảnh.
- HTML, XML, JSON và CSV phức tạp cần parser đúng định dạng.

Hãy dùng regex để **phát hiện hoặc tách cấu trúc văn bản phù hợp**, sau đó áp dụng validation bằng kiểu dữ liệu hoặc thư viện chuyên dụng.

## 11. Ví dụ tổng hợp: phân tích một dòng nhật ký

Ví dụ sau trích xuất ngày, mức độ log và thông điệp từ một dòng có cấu trúc:

~~~~text
2026-11-27 INFO Đã bắt đầu phiên xử lý
2026-11-27 WARN Bộ nhớ cache gần đầy
2026-02-30 ERROR Ngày không tồn tại
~~~~

Yêu cầu:

1. Dòng phải khớp **toàn bộ** mẫu có ba nhóm `date`, `level` và `message`.
2. Ngày phải là ngày hợp lệ thực sự, không chỉ đúng dạng `YYYY-MM-DD`.
3. Mức độ log chỉ thuộc `INFO`, `WARN` hoặc `ERROR`.
4. Không tạo đối tượng khi dữ liệu không hợp lệ.
5. Biên dịch regex một lần, tạo Matcher cho từng dòng.

Chương trình sau có thể lưu thành `LogParserDemo.java`:

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

enum Level {
    INFO, WARN, ERROR
}

record LogEntry(LocalDate date, Level level, String message) {
}

public class LogParserDemo {
    private static final Pattern LOG_LINE = Pattern.compile(
            "^(?<date>\\d{4}-\\d{2}-\\d{2})\\h+"
            + "(?<level>INFO|WARN|ERROR)\\h+"
            + "(?<message>.+)$");

    static Optional<LogEntry> parse(String line) {
        Objects.requireNonNull(line, "line");
        Matcher matcher = LOG_LINE.matcher(line);
        if (!matcher.matches()) {
            return Optional.empty();
        }

        try {
            LocalDate date = LocalDate.parse(matcher.group("date"));
            Level level = Level.valueOf(matcher.group("level"));
            return Optional.of(new LogEntry(
                    date, level, matcher.group("message")));
        } catch (DateTimeParseException exception) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> lines = List.of(
                "2026-11-27 INFO Đã bắt đầu phiên xử lý",
                "2026-11-27 WARN Bộ nhớ cache gần đầy",
                "2026-02-30 ERROR Ngày không tồn tại",
                "2026-11-27 DEBUG Mức log chưa được hỗ trợ");

        lines.stream()
                .map(LogParserDemo::parse)
                .flatMap(Optional::stream)
                .forEach(System.out::println);
    }
}
~~~~

**Vì sao ví dụ tách regex và validation?** Regex xác nhận khuôn dạng và loại trừ những mức log ngoài `INFO|WARN|ERROR`. `LocalDate.parse` xác nhận ngày lịch thực sự, nên dòng `2026-02-30` bị loại. Một số định dạng dữ liệu đòi hỏi nhiều bước xác nhận như vậy; ép tất cả logic vào một regex thường làm chương trình khó kiểm tra.

Nếu dữ liệu log có thể chứa dòng rất dài, hãy kiểm tra giới hạn độ dài trước khi gọi `matcher.matches()`. Nếu thông điệp cần hỗ trợ nhiều dòng, quy tắc và cách đọc log phải được định nghĩa lại, thay vì chỉ bật `DOTALL` một cách tùy ý.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Regex `"\\d+"` bị viết thành `"\d+"` trong Java | Quên tầng escape của String literal | Viết `"\\d+"` |
| `matches()` trả `false` dù nhìn thấy đoạn đúng mẫu | `matches()` kiểm tra **toàn bộ vùng input** | Dùng `find()` nếu cần tìm đoạn, hoặc sửa quy tắc xác thực |
| `find()` bỏ sót trường hợp mong muốn | Regex quá chặt, vùng tìm kiếm sai hoặc đã thay đổi trạng thái Matcher | Kiểm tra pattern, flags, `region` và `reset` |
| `group()` ném `IllegalStateException` | Chưa có lần khớp thành công hoặc lần thử gần nhất thất bại | Chỉ đọc group sau khi `find`/`matches`/`lookingAt` trả true |
| `group(1)` không có dữ liệu | Nhóm là tùy chọn và không tham gia match | Xem xét null và dùng nhóm có tên khi phù hợp |
| `replaceAll` gây lỗi với dấu `$` hoặc `\` của dữ liệu đầu vào | Replacement được hiểu theo cú pháp tham chiếu nhóm | Dùng `Matcher.quoteReplacement` cho replacement literal |
| Tìm keyword `a.b` lại nhận `aXb` | Keyword được hiểu như regex | Dùng `Pattern.quote(keyword)` hoặc `Pattern.LITERAL` |
| `^`/`$` không làm việc theo từng dòng | Chưa bật `MULTILINE` | Bật flag nếu cần; lưu ý `matches()` vẫn cần toàn bộ region |
| `.` không nhận ký tự xuống dòng | Chế độ mặc định không nhận mọi line terminator | Dùng `DOTALL` khi nghiệp vụ cần |
| Ký tự tiếng Việt không khớp với `[A-Za-z]` hoặc `\\w` mặc định | Lớp ASCII không bao gồm mọi ký tự Unicode | Dùng `\\p{L}`/`\\p{M}` hoặc `UNICODE_CHARACTER_CLASS` theo yêu cầu |
| Chỉ số `start/end` lệch với vị trí nhìn thấy | Offset theo UTF-16 code unit | Phân biệt code unit, code point và grapheme |
| `split` làm mất phần tử rỗng cuối | `limit = 0` mặc định loại phần tử rỗng cuối | Dùng `split(input, -1)` khi cần giữ |
| Regex chạy rất chậm trên dữ liệu dài | Backtracking quá lớn | Đơn giản hóa pattern, giới hạn input, kiểm tra dữ liệu gần khớp |
| Chia sẻ Matcher giữa nhiều luồng tạo kết quả không nhất quán | Matcher có trạng thái, không thread-safe | Chia sẻ Pattern và tạo Matcher riêng mỗi lần xử lý |
| `Pattern.compile` ném `PatternSyntaxException` | Regex sai cú pháp | Sửa biểu thức; nếu người dùng chỉ nhập từ khóa literal, dùng `Pattern.quote` |

## 13. Checklist lựa chọn API

- [ ] Bài toán thực sự cần regex, thay vì thao tác chuỗi literal, parser hoặc kiểu dữ liệu chuyên dụng.
- [ ] Đã xác định rõ cần **khớp toàn chuỗi** (`matches`), **tiền tố** (`lookingAt`) hay **tìm đoạn** (`find`).
- [ ] Đã viết đúng hai tầng escape: String Java và cú pháp regex.
- [ ] Đã chọn lớp ký tự phù hợp cho ASCII/Unicode và quy tắc thực tế của dữ liệu.
- [ ] Có nhóm `(?:...)` nếu chỉ cần gom biểu thức, nhóm `(...)`/`(?<name>...)` nếu cần trích xuất.
- [ ] Chỉ truy cập `group`, `start` và `end` sau lần khớp thành công.
- [ ] Tái sử dụng Pattern khi cần khớp nhiều lần; tạo Matcher riêng cho từng input hoặc từng luồng.
- [ ] Đã phân biệt `Pattern.quote` (regex literal) và `Matcher.quoteReplacement` (replacement literal).
- [ ] Với split, đã quyết định có cần giữ phần tử rỗng cuối hay không.
- [ ] Với input không tin cậy, đã hạn chế kích thước và đánh giá rủi ro backtracking.
- [ ] Với ngày, URI, email hoặc cấu trúc phức tạp, đã áp dụng kiểm tra ngữ nghĩa ngoài regex.
- [ ] Đã kiểm tra đầu vào hợp lệ, không hợp lệ, chuỗi rỗng, Unicode và trường hợp gần khớp.

## Tài liệu chính thức để tra cứu thêm

- [Pattern – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html): bảng cú pháp regex, Unicode, flags, `compile`, `quote`, `split`, Predicate.
- [Matcher – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Matcher.html): `find`, `matches`, `lookingAt`, nhóm, region, replacement, `results`.
- [MatchResult – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/MatchResult.html): vị trí và dữ liệu của một lần khớp, nhóm theo chỉ số và nhóm có tên.
- [PatternSyntaxException – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/PatternSyntaxException.html): thông tin lỗi cú pháp và vị trí trong biểu thức chính quy.

Nắm vững `Pattern` và `Matcher` nghĩa là biết mô tả **đúng quy tắc**, chọn **đúng thao tác khớp**, đọc **đúng nhóm/vị trí**, và sử dụng regex **đúng phạm vi**. Khi cần, hãy kết hợp với parser và validation của kiểu dữ liệu để xây dựng xử lý văn bản rõ ràng, hiệu quả và đáng tin cậy trong Java 27.
