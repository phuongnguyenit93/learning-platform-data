# Matcher.quoteReplacement: giữ nguyên văn nội dung thay thế trong Java

## Mục tiêu bài học

Khi dùng biểu thức chính quy để thay thế nội dung trong `String`, Java diễn giải **mẫu cần tìm** (*regex*) và **chuỗi dùng để thay thế** (*replacement*) theo hai bộ quy tắc khác nhau. Bài này giúp bạn:

- Giải thích tại sao dấu `$` và dấu gạch chéo ngược `\` trong chuỗi thay thế có thể bị Java hiểu là cú pháp đặc biệt.
- Dùng `Matcher.quoteReplacement(String s)` để đưa nội dung thay thế vào `String.replaceAll`, `String.replaceFirst` hoặc `Matcher.appendReplacement` **đúng nguyên văn**.
- Phân biệt `Matcher.quoteReplacement` với `Pattern.quote`, với `String.replace` và với cú pháp tham chiếu nhóm như `$1` hoặc `${name}`.
- Viết ví dụ Java 17+ có thể biên dịch, đồng thời nhận diện lỗi và giới hạn áp dụng.

## 1. Vấn đề: replacement không phải văn bản thuần túy

Xét lời gọi:

~~~java
String result = input.replaceAll(regex, replacement);
~~~

Đối số `regex` là mẫu để **tìm** các đoạn phù hợp trong `input`. Sau khi tìm được từng đoạn khớp, Java còn diễn giải đối số `replacement`:

| Ký hiệu trong replacement | Ý nghĩa khi dùng trực tiếp |
| --- | --- |
| `$0` | Toàn bộ đoạn vừa khớp |
| `$1`, `$2`, ... | Nội dung nhóm bắt (*capturing group*) tương ứng |
| `${name}` | Nội dung nhóm bắt có tên `name`, nếu mẫu khai báo nhóm đó |
| `\` | Escape ký tự kế tiếp trong cú pháp replacement, ví dụ làm `$` trở thành ký tự thông thường |

Do vậy, nếu muốn thay một đoạn bằng đúng văn bản `$1\docs`, truyền thẳng nội dung đó vào `replaceAll` sẽ không có nghĩa là “chép nguyên văn”: `$1` bị xem là tham chiếu nhóm bắt, còn `\` có thể làm mất dấu gạch chéo hoặc gây lỗi tùy vị trí. Khi nhóm `1` không tồn tại, `$1` có thể khiến thao tác thay thế ném ngoại lệ.

**`Matcher.quoteReplacement(s)` giải quyết đúng vấn đề này.** Phương thức tĩnh thuộc `java.util.regex.Matcher` trả về một chuỗi *replacement* tương ứng với **nội dung nguyên văn của `s`**. Khi dùng chuỗi trả về làm đối số thay thế của API regex, mọi `$` và `\` xuất phát từ `s` đều được coi là ký tự bình thường. Nó không đổi nội dung cần chèn và không điều khiển regex tìm kiếm.

Chữ ký API:

~~~java
public static String quoteReplacement(String s)
~~~

Đây là phương thức `static`, nên gọi `Matcher.quoteReplacement(s)` mà không cần tạo một đối tượng `Matcher`. Giá trị `null` không phải chuỗi thay thế hợp lệ; truyền `null` sẽ gây `NullPointerException`.

## 2. Ví dụ Java 17+: thay thế bằng nội dung có dấu $ và \

Lưu toàn bộ chương trình sau vào tệp `QuoteReplacementDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QuoteReplacementDemo {
    public static void main(String[] args) {
        String source = "A1 B2";
        String literalReplacement = "$5\\bin";

        // Thay mọi đoạn phù hợp bằng đúng nội dung "$5\bin".
        String all = source.replaceAll(
                "[A-Z]\\d",
                Matcher.quoteReplacement(literalReplacement));
        System.out.println(all);

        // Thay duy nhất đoạn khớp đầu tiên.
        String first = source.replaceFirst(
                "[A-Z]\\d",
                Matcher.quoteReplacement(literalReplacement));
        System.out.println(first);

        // Khi muốn dùng nhóm bắt, KHÔNG quote cả template.
        System.out.println(
                source.replaceAll("([A-Z])(\\d)", "$2-$1"));

        // Khi muốn chính các ký tự "$2-$1" xuất hiện, HÃY quote.
        System.out.println(
                source.replaceAll("([A-Z])(\\d)",
                        Matcher.quoteReplacement("$2-$1")));

        // Bảo vệ cả chuỗi tìm kiếm nguyên văn và chuỗi thay thế nguyên văn.
        String text = "a.b|a.b";
        String needle = "a.b";
        String replacement = "$1\\dst";
        System.out.println(text.replaceAll(
                Pattern.quote(needle),
                Matcher.quoteReplacement(replacement)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 QuoteReplacementDemo.java
java QuoteReplacementDemo
~~~

Kết quả chuẩn:

~~~text
$5\bin $5\bin
$5\bin B2
1-A 2-B
$2-$1 $2-$1
$1\dst|$1\dst
~~~

Diễn giải:

1. `"[A-Z]\\d"` khớp lần lượt `A1` và `B2`; `quoteReplacement` làm cho `$5\bin` được chèn y hệt, dù không có nhóm số 5.
2. `replaceFirst` có cách diễn giải replacement giống `replaceAll` nhưng chỉ thay lần khớp đầu tiên, nên `B2` vẫn còn.
3. Trong `"([A-Z])(\\d)"`, nhóm `1` là chữ cái và nhóm `2` là chữ số. Replacement `"$2-$1"` cố ý lấy nhóm và đổi `A1` thành `1-A`.
4. Sau khi bọc `"$2-$1"` bằng `quoteReplacement`, chuỗi này được chèn đúng nguyên văn; nhóm bắt không còn được thay vào vị trí `$1` hoặc `$2`.
5. `Pattern.quote("a.b")` làm dấu `.` trong **mẫu tìm kiếm** mất ý nghĩa đặc biệt; `Matcher.quoteReplacement("$1\\dst")` làm `$` và `\` trong **replacement** mất ý nghĩa đặc biệt.

**Hai tầng escape cần nhớ:** Mã Java `"$5\\bin"` tạo ra giá trị thực `$5\bin` vì hai ký tự `\\` trong source tạo một dấu `\` trong chuỗi runtime. `Matcher.quoteReplacement` sau đó xây dựng biểu diễn phù hợp cho bộ xử lý replacement, giúp dấu `\` runtime được giữ lại ở kết quả.

## 3. Phân biệt pattern, replacement và cách gọi API

Đừng nhầm vị trí của dữ liệu:

| Nhu cầu | Cách làm | Lý do |
| --- | --- | --- |
| Mẫu tìm là regex, nội dung thay là chuỗi thuần | `input.replaceAll(regex, Matcher.quoteReplacement(literal))` | Regex vẫn hoạt động; replacement được bảo toàn |
| Mẫu tìm là đoạn văn bản thuần, nội dung thay là chuỗi thuần | `input.replace(literalTarget, literalReplacement)` | Không cần regex hoặc quote |
| Bắt buộc dùng API regex nhưng cần tìm chuỗi nguyên văn | `input.replaceAll(Pattern.quote(target), Matcher.quoteReplacement(replacement))` | Quote **cả hai đối số**, mỗi cái theo ngữ pháp của nó |
| Cần chèn giá trị các nhóm bắt | `input.replaceAll(regex, "$2-$1")` | Cho phép bộ máy replacement mở rộng nhóm bắt |
| Cần dùng quy trình thay thế từng match | `matcher.appendReplacement(builder, Matcher.quoteReplacement(value))` rồi `matcher.appendTail(builder)` | Mỗi match có thể có replacement riêng, bảo toàn giá trị tạo ra |

**`Pattern.quote` và `Matcher.quoteReplacement` không hoán đổi được:**

- `Pattern.quote(literalTarget)` tạo biểu thức chính quy khớp nguyên văn `literalTarget`. Nó giải quyết dấu regex đặc biệt, chẳng hạn `.`, `*`, `[`, `(`.
- `Matcher.quoteReplacement(literalReplacement)` tạo cú pháp replacement đại diện cho nội dung nguyên văn `literalReplacement`. Nó giải quyết `$` và `\` trong **văn bản thay thế**.
- `String.replace(target, replacement)` là thay thế chuỗi con nguyên văn, không dùng regex cho cả `target` lẫn `replacement`; đó thường là lựa chọn ngắn nhất khi không cần regex.

Nếu **chỉ có** nội dung replacement cần bảo toàn, không bọc `regex` trong `Pattern.quote`: làm vậy sẽ biến các ký hiệu regex mong muốn thành văn bản literal và thay đổi logic tìm kiếm.

## 4. So sánh mở rộng nhóm bắt với chèn đúng nguyên văn

Giả sử một mẫu có hai nhóm:

~~~java
String source = "id=42";
String regex = "([a-z]+)=(\\d+)";
~~~

Ba cách thay thế dưới đây có ý nghĩa khác nhau:

| Lệnh | Kết quả | Giải thích |
| --- | --- | --- |
| `source.replaceAll(regex, "$2:$1")` | `42:id` | `$2` và `$1` được mở rộng từ nhóm bắt |
| `source.replaceAll(regex, Matcher.quoteReplacement("$2:$1"))` | `$2:$1` | Nội dung có `$` được chèn đúng nguyên văn |
| `source.replaceAll(regex, Matcher.quoteReplacement("USD $5\\tmp"))` | `USD $5\tmp` | Giữ cả dấu `$` lẫn dấu `\` |

Vì thế **không bọc cả template nhóm bắt trong `quoteReplacement`** nếu chủ đích là dùng `$1`, `$2` hoặc `${name}` để tạo kết quả từ dữ liệu tìm được. Ngược lại, nếu một giá trị replacement đến từ ô nhập liệu, cấu hình hoặc nội dung sinh động mà người dùng muốn giữ đúng ký tự, `quoteReplacement` là cách bảo vệ hợp lý.

Có thể trộn dữ liệu nhóm bắt và văn bản literal bằng cách **tạo giá trị kết quả cuối cùng cho từng match**, rồi `quoteReplacement` giá trị cuối cùng đó trước khi đưa vào `appendReplacement`; ví dụ ở phần tiếp theo. Cách này còn tránh các mơ hồ như nối `"$1" + "2"` thành `"$12"`: bộ xử lý có thể diễn giải `$12` là nhóm 12 nếu nhóm đó tồn tại.

## 5. Thay thế động theo từng match với Matcher.appendReplacement

`String.replaceAll` nhận một replacement chung cho mọi match. Khi replacement cần dựa trên chính đoạn vừa khớp hoặc logic tùy biến, sử dụng `Matcher.find()` với `appendReplacement` và `appendTail`.

Ví dụ: với mỗi mã gồm hai chữ in hoa và hai chữ số, bao quanh nó bằng `[` và `]`, đồng thời thêm hậu tố literal có dấu `$` và `\`.

Lưu vào `DynamicReplacementDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DynamicReplacementDemo {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile("[A-Z]{2}[0-9]{2}");
        Matcher matcher = pattern.matcher("AB12 and CD34");
        StringBuilder result = new StringBuilder();

        while (matcher.find()) {
            String text = "[" + matcher.group() + " $5\\log]";
            matcher.appendReplacement(
                    result,
                    Matcher.quoteReplacement(text));
        }
        matcher.appendTail(result);

        System.out.println(result);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DynamicReplacementDemo.java
java DynamicReplacementDemo
~~~

Kết quả:

~~~text
[AB12 $5\log] and [CD34 $5\log]
~~~

Trình tự hoạt động:

1. `find()` tìm `AB12`, sau đó `CD34`.
2. `group()` trả về phần vừa khớp và giúp chương trình xây dựng replacement riêng cho mỗi lần.
3. `quoteReplacement(text)` bảo đảm các ký tự `$` và `\` trong giá trị cuối cùng là dữ liệu literal.
4. `appendReplacement` nối phần văn bản chưa được xử lý và replacement cho match hiện tại vào `StringBuilder`.
5. `appendTail` nối nốt văn bản còn lại sau match cuối cùng. Nếu quên bước này, phần đuôi có thể bị mất; nếu không có match nào, bước này vẫn giữ lại toàn bộ văn bản gốc.

`appendReplacement(StringBuilder, String)` có mặt từ Java 9 nên dùng được trong Java 17+. Với mẫu dùng lặp lại nhiều lần, `Pattern.compile` một lần rồi tạo `Matcher` cho từng input giúp tránh biên dịch regex lặp lại không cần thiết. Đừng chia sẻ cùng một `Matcher` giữa nhiều luồng mà không đồng bộ vì đối tượng này có trạng thái thay đổi theo mỗi lần tìm khớp.

## 6. Những lỗi phổ biến

### 6.1. Chèn replacement từ người dùng mà không quote

Ví dụ sai khi `userReplacement` là `"$10"` hoặc `"C:\\new"`:

~~~java
// Sai nếu muốn thay bằng đúng chuỗi mà người dùng nhập:
String result = input.replaceAll(regex, userReplacement);
~~~

`$10` có thể được diễn giải là tham chiếu nhóm (quy tắc số nhóm phụ thuộc các nhóm hiện có); `\` có thể bị tiêu thụ để escape ký tự tiếp theo. Nếu dấu `$` đứng ở vị trí không hợp lệ hoặc tham chiếu nhóm không tồn tại, chương trình có thể ném `IllegalArgumentException` hay `IndexOutOfBoundsException` tùy trường hợp.

Cách đúng để chèn nguyên văn:

~~~java
String result = input.replaceAll(
        regex, Matcher.quoteReplacement(userReplacement));
~~~

### 6.2. Nhầm escape của Java với escape của replacement

Hai tầng có vai trò khác nhau:

- **Tầng chuỗi Java:** `"\\":` biểu diễn **một** dấu `\` trong giá trị runtime. Trong ví dụ code, `"$1\\docs"` là giá trị có ký tự `$`, `1`, `\`, `d`, `o`, `c`, `s`.
- **Tầng replacement của regex:** Bộ xử lý `replaceAll` gán ý nghĩa cho `$` và `\` trong giá trị runtime. `quoteReplacement` giúp chúng trở thành literal mà không cần tự viết các dấu escape thủ công.

Lưu ý: khi đọc regex từ biến hoặc tệp, escape của **source Java** đã được xử lý (hoặc không liên quan); không nên thêm ngẫu nhiên dấu `\` trước khi gọi `quoteReplacement`.

### 6.3. Dùng quoteReplacement để sửa một regex sai

`Matcher.quoteReplacement` chỉ bảo vệ chuỗi dùng để **thay thế**. Nó không sửa regex thiếu dấu `]`, không biến `.*` thành mẫu tìm literal, và không xử lý `PatternSyntaxException` phát sinh ở đối số tìm kiếm. Nếu muốn tìm chính xác văn bản đầu vào, dùng `Pattern.quote` cho đối số regex hoặc `String.replace` nếu không cần regex.

### 6.4. Quote quá nhiều khi chủ đích sử dụng nhóm bắt

~~~java
// Muốn đảo hai nhóm: đúng
String ok = "A1".replaceAll("([A-Z])(\\d)", "$2$1");

// Muốn "$2$1" xuất hiện nguyên văn: đúng
String literal = "A1".replaceAll(
        "([A-Z])(\\d)", Matcher.quoteReplacement("$2$1"));
~~~

Giá trị `ok` là `"1A"`, còn `literal` là `"$2$1"`. Khác biệt đến từ **ý định sử dụng replacement**, không phải do cú pháp nào “tốt hơn” trong mọi tình huống.

### 6.5. Quên xử lý null, đầu vào lớn hoặc độ phức tạp regex

- `Matcher.quoteReplacement(null)` gây `NullPointerException`; kiểm tra null hoặc xác định chính sách dữ liệu thiếu trước khi dùng.
- Nếu regex không khớp đoạn nào, `replaceAll` trả lại toàn bộ nội dung gốc; `quoteReplacement` không ép phải có match.
- `quoteReplacement` chỉ giải quyết ký tự đặc biệt trong replacement. Nó không bảo vệ khỏi regex quá tốn thời gian (chẳng hạn một số biểu thức lặp lồng nhau gây *catastrophic backtracking*), không xác thực định dạng và không tự giới hạn kích thước đầu vào.

## 7. Bài tập thực hành

Dự đoán kết quả:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReplacementQuiz {
    public static void main(String[] args) {
        System.out.println("aa".replaceAll("a", Matcher.quoteReplacement("$0")));
        System.out.println("a1".replaceAll("([a-z])(\\d)", "$2$1"));
        System.out.println("a1".replaceAll("([a-z])(\\d)",
                Matcher.quoteReplacement("$2$1")));
        System.out.println("x.y".replaceAll(
                Pattern.quote("."), Matcher.quoteReplacement("$")));
        System.out.println("aaa".replaceFirst("a",
                Matcher.quoteReplacement("\\dir")));
    }
}
~~~

Lưu `ReplacementQuiz.java`, chạy `javac -encoding UTF-8 ReplacementQuiz.java` rồi `java ReplacementQuiz`. Đáp án:

~~~text
$0$0
1a
$2$1
x$y
\diraa
~~~

Lý do: hai `a` được thay bằng chuỗi literal `$0`; `$2$1` không quote thì đảo nhóm; quote thì giữ nguyên ký tự; `Pattern.quote(".")` tìm đúng dấu chấm; và `replaceFirst` thay chỉ chữ `a` đầu tiên bằng `\dir`.

## Ghi nhớ và checklist áp dụng

- Hỏi rõ: **giá trị replacement cần giữ nguyên văn hay cần mở rộng các nhóm bắt?** Chỉ dùng `Matcher.quoteReplacement` cho phần cần giữ nguyên văn.
- Với regex để tìm và nội dung tự do để thay: `replaceAll(regex, Matcher.quoteReplacement(text))`.
- Với cả chuỗi tìm và chuỗi thay là literal: ưu tiên `String.replace(target, replacement)`; nếu cần matcher thì phối hợp `Pattern.quote(target)` và `Matcher.quoteReplacement(replacement)`.
- Với nội dung thay khác nhau theo mỗi match: tính giá trị cần chèn dựa trên `group()` rồi đưa qua `quoteReplacement` trước `appendReplacement`, cuối cùng gọi `appendTail`.
- Kiểm tra các tình huống có `$`, `\`, không có match, nhiều match, chuỗi rỗng, nhóm bắt và giá trị `null`.

## Tài liệu tham khảo

- [Java SE 17 — Matcher.quoteReplacement(String)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html#quoteReplacement(java.lang.String))
- [Java SE 17 — Matcher.appendReplacement và appendTail](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
- [Java SE 17 — Pattern.quote(String)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html#quote(java.lang.String))
- [Java SE 17 — String.replaceAll, replaceFirst, replace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
