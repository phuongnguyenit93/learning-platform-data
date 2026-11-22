# Phân biệt tìm chuỗi nguyên văn với tìm theo biểu thức chính quy trong Java

## 1. Hai kiểu tìm kiếm có ý nghĩa khác nhau

Một thao tác tìm văn bản có thể nhận **từ khóa nguyên văn (literal)** hoặc **biểu thức chính quy (regex)**. Hai khái niệm này khác nhau ngay cả khi tình cờ cho ra cùng kết quả.

- **Tìm nguyên văn:** các ký tự của từ khóa chính là dữ liệu cần tìm. Từ khóa **a.b** chỉ khớp đúng ba ký tự **a**, dấu chấm, **b**.
- **Tìm regex:** từ khóa là một *mẫu* có ký hiệu điều khiển. Regex **a.b** khớp **a.b**, **aXb**, **a1b**, vì dấu chấm **.** biểu diễn một ký tự bất kỳ (trừ một số line terminator theo chế độ mặc định).

Trong Java, chọn **String.contains()** hoặc **String.indexOf()** khi người dùng muốn tìm một đoạn văn bản chính xác; chọn **java.util.regex.Pattern** và **Matcher** khi cần một quy tắc như “mã bắt đầu bằng item- rồi tới nhiều chữ số”.

Không nên nghĩ rằng String chứa ký tự **.**, **\**, **+**, **?** hoặc ngoặc vuông thì tự động biến thành regex. Chúng chỉ mang ý nghĩa regex khi được đưa vào một API **chủ động phân tích biểu thức chính quy**.

Ví dụ nhanh, đặt trong một phương thức:

~~~java
String text = "a.b aXb";
System.out.println(text.contains("a.b")); // true: literal "a.b"
System.out.println(text.indexOf("a.b"));  // 0
System.out.println(text.contains("a.b aXb")); // true
System.out.println(java.util.regex.Pattern
        .compile("a.b").matcher("aXb").find()); // true: "." là wildcard
~~~

## 2. Những API tìm nguyên văn của String

| API | Kết quả | Cách tìm |
| --- | --- | --- |
| **text.contains(query)** | boolean | Có đoạn **query** xuất hiện nguyên văn trong text không? |
| **text.indexOf(query)** | int | Vị trí đầu tiên của đoạn query hoặc **-1** nếu không có |
| **text.indexOf(query, fromIndex)** | int | Tìm nguyên văn, bắt đầu từ một offset UTF-16 |
| **text.lastIndexOf(query)** | int | Tìm lần xuất hiện cuối theo chiều ngược |
| **text.startsWith(prefix)** | boolean | Khớp tiền tố nguyên văn |
| **text.endsWith(suffix)** | boolean | Khớp hậu tố nguyên văn |
| **text.equals(query)** | boolean | So toàn bộ nội dung, không phải tìm chuỗi con |

Ví dụ:

~~~java
String path = "report.v1.txt";
System.out.println(path.contains(".v1."));   // true
System.out.println(path.indexOf(".v1."));    // 6
System.out.println(path.startsWith("rep"));  // true
System.out.println(path.endsWith(".txt"));   // true
System.out.println(path.contains("\\d+"));   // false
~~~

Ở câu cuối, **"\\d+"** là một String Java có nội dung gồm dấu gạch chéo ngược, chữ **d** và dấu **+**. **contains()** không giải mã nó như regex “một hoặc nhiều chữ số”.

Các phương thức tìm String nêu trên **phân biệt hoa thường**, không tự chuẩn hóa Unicode và không nhận chính sách so khớp bỏ dấu tiếng Việt.

### Trường hợp rỗng, null và vị trí

- **text.contains("")** trả về **true** với một String text khác null.
- **text.indexOf("")** trả về **0**; **text.lastIndexOf("")** trả về **text.length()**.
- Nếu **text == null**, việc gọi phương thức trên text gây **NullPointerException**. Nếu query của **contains** hoặc **indexOf(String)** là null, phương thức cũng không chấp nhận và ném ngoại lệ.
- **indexOf()**, **lastIndexOf()** và đa số phép cắt String dùng **offset UTF-16**, không phải số ký tự người dùng nhìn thấy. Emoji ngoài BMP có thể chiếm hai đơn vị UTF-16.

Nếu query rỗng không có ý nghĩa trong chức năng tìm kiếm, hãy kiểm tra đầu vào trước khi gọi API; đừng mặc nhiên hiểu **contains("") == true** là kết quả người dùng mong muốn.

### Backslash trong literal Java

~~~java
String location = "C:\\temp\\file.txt";
System.out.println(location.contains("\\"));  // true
System.out.println(location.contains(".txt")); // true
~~~

Dấu **\\** trong mã nguồn được viết kép vì cú pháp **Java string literal**. Đây là cơ chế escape của ngôn ngữ Java, độc lập với cú pháp regex. Nếu query đã được nhập từ bàn phím dưới dạng biến String thì dùng **contains(query)** trực tiếp, không tự chèn thêm các dấu gạch chéo ngược.

## 3. Regex trong Java: Pattern và Matcher

Để dùng biểu thức chính quy, import:

~~~java
import java.util.regex.Pattern;
import java.util.regex.Matcher;
~~~

**Pattern.compile(regex)** biên dịch một regex thành **Pattern**. **pattern.matcher(text)** tạo **Matcher** có trạng thái duyệt một văn bản. Sau đó:

- **find()** tìm **đoạn con** khớp regex ở vị trí tiếp theo.
- **matches()** yêu cầu **toàn bộ vùng được xét** khớp regex.
- **lookingAt()** yêu cầu regex khớp ngay **đầu vùng**, không nhất thiết hết vùng.
- **group()** lấy văn bản vừa khớp; **start()** và **end()** trả về offset UTF-16 bắt đầu và ngay sau đoạn khớp.

Ví dụ tìm các mã theo mẫu:

~~~java
Pattern pattern = Pattern.compile("item-\\d+");
Matcher matcher = pattern.matcher("item-42, item-7");

while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Stdout:

~~~text
item-42
item-7
~~~

**\\d** trong regex đại diện cho chữ số theo quy tắc của Java Pattern; **+** nghĩa là ít nhất một lần. Trong **mã nguồn Java**, regex này phải viết **"item-\\d+"** để giá trị String thực tế đưa vào engine chứa dấu gạch chéo ngược.

### find(), matches() và String.matches()

~~~java
Pattern digits = Pattern.compile("\\d+");

System.out.println(digits.matcher("abc123xyz").find());      // true
System.out.println(digits.matcher("abc123xyz").matches());   // false
System.out.println(digits.matcher("123abc").lookingAt());    // true
System.out.println("123".matches("\\d+"));                   // true
System.out.println("abc123xyz".matches("\\d+"));             // false
~~~

Các câu lệnh có import **Pattern** ở trên là minh họa trong một phương thức.

**String.matches(regex)** cũng kiểm tra **toàn chuỗi**. Vì vậy **"abc123".matches("\\d+")** là false, dù phần **123** hoàn toàn khớp regex. Nếu muốn **tìm xem có tồn tại một đoạn khớp** trong văn bản, dùng **Pattern.compile(regex).matcher(text).find()**.

Không nên máy móc bọc regex bằng **".*"** ở hai đầu để giả lập find(): quy tắc sẽ khó đọc hơn, dễ bị ảnh hưởng bởi cách **.** xử lý newline và có thể phát sinh chi phí xử lý không cần thiết.

## 4. Chạy ví dụ Java 17+: so sánh literal với regex

Lưu thành **LiteralVsRegexSearchDemo.java** theo UTF-8:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class LiteralVsRegexSearchDemo {
    public static void main(String[] args) {
        String text = "file.txt | fileXtxt | item-42 | ITEM-7";

        System.out.println(text.contains("file.txt"));
        System.out.println(text.indexOf("file.txt"));
        System.out.println(text.indexOf("fileXtxt"));

        Pattern exactDot = Pattern.compile("file\\.txt");
        Pattern wildcardDot = Pattern.compile("file.txt");

        System.out.println(exactDot.matcher(text).find());
        System.out.println(wildcardDot.matcher("fileXtxt").matches());
        System.out.println(exactDot.matcher("fileXtxt").matches());
        System.out.println(text.matches("file\\.txt"));

        Matcher items = Pattern.compile("(?i)item-\\d+")
                .matcher(text);

        while (items.find()) {
            System.out.printf("%s@%d-%d%n",
                    items.group(), items.start(), items.end());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 LiteralVsRegexSearchDemo.java
java LiteralVsRegexSearchDemo
~~~

Stdout:

~~~text
true
0
11
true
true
false
false
item-42@22-29
ITEM-7@32-38
~~~

Giải thích:

1. **contains("file.txt")** tìm chuỗi nguyên văn có dấu chấm, trả true.
2. **indexOf("file.txt") == 0**, còn **fileXtxt** bắt đầu tại offset 11.
3. Regex **file\\.txt** trong Java yêu cầu **dấu chấm thật**; vì vậy tìm được file.txt nhưng không khớp fileXtxt.
4. Regex **file.txt** cho phép một ký tự bất kỳ tại dấu chấm và vì vậy khớp cả fileXtxt.
5. **text.matches("file\\.txt")** trả false vì text dài hơn file.txt; **matches** yêu cầu khớp toàn bộ.
6. Flag inline **(?i)** bật so khớp không phân biệt hoa thường, nên tìm được item-42 và ITEM-7.
7. **start()/end()** trả về offset UTF-16, trong đó **end()** không được tính vào đoạn khớp. Có thể dùng **text.substring(start, end)** để lấy lại đoạn đã khớp.

## 5. Các ký hiệu regex dễ bị hiểu thành văn bản nguyên vẹn

| Cú pháp regex | Ý nghĩa theo mẫu | Khi muốn tìm literal |
| --- | --- | --- |
| **.** | Một ký tự bất kỳ, ngoại trừ một số line terminator theo chế độ | Escape thành **\\.** |
| **\\d** | Chữ số | Quote ký tự backslash và d nếu chúng thực sự là dữ liệu |
| **[abc]** | Một ký tự trong tập a, b, c | Quote cả chuỗi **[abc]** |
| **a+** | Một hoặc nhiều ký tự a | Escape dấu cộng nếu cần tìm **a+** |
| **a*** | Không hoặc nhiều ký tự a | Escape dấu sao nếu cần tìm **a*** |
| **a?** | Không hoặc một ký tự a | Escape dấu hỏi nếu cần tìm **a?** |
| **^abc** | Mẫu tại đầu theo chế độ | Quote dấu mũ nếu là dữ liệu |
| **abc$** | Mẫu tại cuối theo chế độ | Quote dấu đô-la nếu là dữ liệu |
| **(abc)** | Nhóm regex | Quote dấu ngoặc nếu cần tìm văn bản có ngoặc |
| **a\|b** | Khớp a hoặc b | Quote dấu pipe khi nó là văn bản |
| **\\bcat\\b** | Từ cat với ranh giới từ | Tìm bằng regex khi nghiệp vụ thực sự cần ranh giới |

Regex có các cấu trúc nhóm, character class, quantifier, anchor, lookaround. Chúng rất hữu ích khi đầu vào là một **mẫu có chủ đích**, nhưng sẽ gây kết quả sai nếu lấy nguyên từ khóa người dùng rồi coi như mẫu.

### Tìm từ nguyên vẹn khác tìm một phần của từ

~~~java
String text = "cat scatter cat";
Pattern word = Pattern.compile("\\bcat\\b");
Matcher matcher = word.matcher(text);
while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Đoạn minh họa trên in:

~~~text
cat
cat
~~~

**String.contains("cat")** vẫn trả true vì chứa đoạn cat; **indexOf** còn có thể tìm chuỗi con cat bên trong scatter. Regex **\\bcat\\b** giới hạn bằng ranh giới từ và không nhận chữ cat bên trong scatter. Quy tắc word boundary của regex không thay thế hoàn toàn tách từ ngôn ngữ tự nhiên, nhất là văn bản đa ngữ.

## 6. Hiểu đúng hai tầng escape: Java literal và regex

Giả sử muốn tìm dấu chấm thật:

1. Văn bản cần khớp: **.**
2. Cú pháp regex: **\\.**
3. Java string literal truyền vào Pattern: **"\\."**

**Java xử lý escape của string literal trước; regex engine đọc kết quả sau đó.**

| Ý định | Regex thực tế | Viết trong Java String literal |
| --- | --- | --- |
| Dấu chấm | **\\.** | **"\\."** |
| Dấu cộng | **\\+** | **"\\+"** |
| Dấu hỏi | **\\?** | **"\\?"** |
| Một backslash | **\\\\** | **"\\\\\\\\"** |
| Một hoặc nhiều chữ số | **\\d+** | **"\\d+"** |
| Ba ký tự a, ., b | **a\\.b** | **"a\\.b"** |

Với biến **query** đã là String chứa dữ liệu người dùng, không áp dụng quy tắc escape Java string literal thêm lần nữa. Ví dụ **query = "a.b"** được nhận từ một form đã là văn bản thực tế. Để tìm nguyên văn, gọi **text.contains(query)**; để tìm bằng Matcher mà vẫn giữ literal, dùng **Pattern.quote(query)**.

## 7. Tìm nguyên văn bằng Pattern: quote và LITERAL

Đôi khi ứng dụng muốn duyệt từng lần xuất hiện, lấy **Matcher.start()/end()** hoặc kết hợp một phần literal vào mẫu regex lớn. Lúc đó có hai công cụ quan trọng.

### 7.1. Pattern.quote(query)

**Pattern.quote(String)** biến query thành một đoạn regex có nghĩa **khớp nguyên văn toàn bộ nội dung query**, kể cả dấu cộng, dấu hỏi, dấu ngoặc, backslash hoặc chuỗi **\\E**.

~~~java
String query = "a.b";
Pattern literalPattern = Pattern.compile(Pattern.quote(query));
System.out.println(literalPattern.matcher("aXb a.b").find()); // true
~~~

Đoạn trên nằm trong một phương thức có import **Pattern**. Kết quả true vì văn bản có **a.b** ở cuối; regex này không nhận aXb làm đoạn literal.

Đừng tự ghép **"\\Q" + query + "\\E"** cho đầu vào tùy ý: bản thân query có thể chứa ký hiệu **\\E**. **Pattern.quote** đã xử lý trường hợp đặc biệt đó.

Khi chỉ **một phần** mẫu là dữ liệu người dùng, quote phần đó:

~~~java
String query = "a.b";
Pattern token = Pattern.compile(
        "start:" + Pattern.quote(query) + ":end");

System.out.println(token.matcher("start:a.b:end").matches()); // true
System.out.println(token.matcher("start:aXb:end").matches()); // false
~~~

Phần **start:** và **:end** ở ví dụ này cố định; query là văn bản nguyên vẹn được chèn vào giữa. Nếu các phần cố định có ký hiệu đặc biệt của regex thì chính chúng cũng phải được thiết kế hoặc quote thích hợp.

### 7.2. Pattern.LITERAL

**Pattern.LITERAL** khiến **toàn bộ mẫu đầu vào** được hiểu là văn bản nguyên vẹn, không phân tích các regex metacharacter:

~~~java
String query = "a.b";
Pattern literal = Pattern.compile(query, Pattern.LITERAL);

System.out.println(literal.matcher("aXb").find()); // false
System.out.println(literal.matcher("a.b").find()); // true
~~~

**Pattern.LITERAL** phù hợp khi cả mẫu là literal. **Pattern.quote** linh hoạt hơn khi phải trộn regex cố định với một đoạn dữ liệu literal. Các flag về cách khớp hoa/thường như **CASE_INSENSITIVE** và **UNICODE_CASE** vẫn có thể có tác dụng với mẫu **LITERAL**.

### Ví dụ Java 17+ đầy đủ

Lưu thành **SafeLiteralSearchDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SafeLiteralSearchDemo {
    static void printMatches(String label, Pattern p, String text) {
        Matcher m = p.matcher(text);
        while (m.find()) {
            System.out.printf("%s=%d:%s%n",
                    label, m.start(), m.group());
        }
    }

    public static void main(String[] args) {
        String text = "a.b aXb [a.b]";
        String query = "a.b";

        System.out.println("contains=" + text.contains(query));
        System.out.println("index=" + text.indexOf(query));

        printMatches("regex", Pattern.compile(query), text);
        printMatches("quoted", Pattern.compile(Pattern.quote(query)), text);
        printMatches("literal",
                Pattern.compile(query, Pattern.LITERAL), text);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeLiteralSearchDemo.java
java SafeLiteralSearchDemo
~~~

Stdout:

~~~text
contains=true
index=0
regex=0:a.b
regex=4:aXb
regex=9:a.b
quoted=0:a.b
quoted=9:a.b
literal=0:a.b
literal=9:a.b
~~~

Đầu vào có **3 đoạn** khớp regex **a.b**, vì wildcard cũng nhận aXb, trong khi **quote** và **LITERAL** chỉ khớp **2 đoạn** a.b nguyên văn. Vị trí 0, 4 và 9 là offset UTF-16.

## 8. Phân biệt với replace, replaceAll và split

Nhiều nhầm lẫn xuất phát từ việc một số API của String dùng literal, nhưng các API khác lại nhận regex.

| API | Nghĩa của đối số tìm kiếm |
| --- | --- |
| **contains(CharSequence)** | Literal |
| **indexOf(String)** | Literal |
| **replace(CharSequence, CharSequence)** | Literal cho đoạn cần thay và đoạn thay thế |
| **replaceAll(String regex, String replacement)** | Regex |
| **replaceFirst(String regex, String replacement)** | Regex |
| **split(String regex)** | Regex để xác định dấu phân cách |
| **matches(String regex)** | Regex yêu cầu khớp toàn chuỗi |

Ví dụ:

~~~java
String file = "one.two.three";
System.out.println(file.replace(".", "-"));     // one-two-three
System.out.println(file.replaceAll("\\.", "-")); // one-two-three
System.out.println(file.replaceAll(".", "-"));   // -------------
~~~

Regex **.** trong **replaceAll** khớp từng ký tự ở ví dụ không có line terminator. Với **split**, muốn tách theo dấu chấm thì viết **split("\\.")** hoặc **split(Pattern.quote("."))** thay vì **split(".")**.

**split(regex)** có giới hạn ngầm **limit = 0**, làm bỏ các phần tử rỗng ở cuối. Nếu muốn giữ các phần rỗng cuối chuỗi, dùng **split(regex, -1)**.

### Replacement là cú pháp riêng

Đối số **replacement** của **Matcher.replaceAll** và **String.replaceAll** có cách hiểu đặc biệt với ký hiệu **$** tham chiếu capture group và backslash escape. Khi replacement là dữ liệu người dùng, dùng **Matcher.quoteReplacement(replacement)**, khác với **Pattern.quote(query)** dùng cho mẫu tìm:

~~~java
String text = "cost=42";
String replacement = "$5";
String safe = Pattern.compile("\\d+")
        .matcher(text)
        .replaceAll(Matcher.quoteReplacement(replacement));
System.out.println(safe); // cost=$5
~~~

Đoạn minh họa nằm trong phương thức có import **Pattern** và **Matcher**. Nếu không quote replacement, ký hiệu **$5** có thể bị diễn giải thành tham chiếu nhóm không có thật và gây lỗi. Với **String.replace(old, new)**, đoạn thay thế là văn bản nguyên vẹn.

## 9. Hoa/thường và Unicode là những quy tắc độc lập

**String.contains** và **indexOf** tìm nguyên văn có phân biệt chữ hoa/thường. Regex có thể dùng:

~~~java
Pattern insensitive = Pattern.compile(
        "java", Pattern.CASE_INSENSITIVE);
System.out.println(insensitive.matcher("JAVA").find()); // true
~~~

Nếu cần case folding Unicode theo Java Pattern, dùng thêm **Pattern.UNICODE_CASE** cùng **CASE_INSENSITIVE**. Chọn rõ chính sách nghiệp vụ; việc tìm không phân biệt hoa/thường không tự đồng nghĩa với tìm bỏ dấu tiếng Việt.

String và regex cũng không tự bảo đảm hai cách mã hóa Unicode có hình thức hiển thị giống nhau sẽ khớp:

~~~java
String composed = "\u00E1";     // á dựng sẵn
String decomposed = "a\u0301"; // a + dấu sắc kết hợp

System.out.println(composed.contains(decomposed)); // false
~~~

Nếu cần canonical equivalence cho tiếng Việt, chuẩn hóa dữ liệu và truy vấn theo cùng một quy tắc, ví dụ **java.text.Normalizer.Form.NFC**, trước khi tìm. Regex có **Pattern.CANON_EQ** nhưng cách sử dụng và chi phí cần đánh giá; chuẩn hóa nhất quán thường dễ kiểm soát hơn cho tìm kiếm thông thường.

Một regex có thể khớp một hoặc nhiều code point; “một ký tự hiển thị” vẫn có thể là grapheme cluster gồm nhiều code point. Nếu thật sự xử lý grapheme, Java Pattern hỗ trợ **\\X**; đó là một bài toán khác với tìm chuỗi nguyên văn.

## 10. Hiệu năng, an toàn và đầu vào người dùng

**Tìm nguyên văn đơn giản:** ưu tiên **contains** hoặc **indexOf**. Ý định được thể hiện trực tiếp và không phải biên dịch regex.

**Tìm theo mẫu thực sự:** biên dịch **Pattern** và dùng **Matcher**. Nếu lặp lại nhiều lần với cùng regex, có thể tái sử dụng **Pattern**. Một **Pattern** là đối tượng bất biến và có thể dùng chung giữa các luồng; **Matcher** chứa trạng thái tìm kiếm biến đổi, nên mỗi tác vụ hoặc luồng cần Matcher riêng.

**Đầu vào là từ khóa người dùng:** không gọi **Pattern.compile(userInput)** trừ khi chức năng thực sự cho phép người dùng viết regex. Ký tự như **[**, **(** có thể gây **PatternSyntaxException**; lượng từ hoặc điều kiện khác có thể thay đổi hoàn toàn kết quả.

~~~java
String query = userInput; // giá trị đến từ form hoặc API
boolean found = text.contains(query);

// Nếu cần vị trí các lần khớp do Matcher cung cấp:
Pattern safe = Pattern.compile(Pattern.quote(query));
boolean foundByMatcher = safe.matcher(text).find();
~~~

Đoạn trên giả định **text**, **userInput** đã được khai báo, với import Pattern. Với từ khóa null hoặc rỗng, áp dụng hợp đồng đầu vào trước khi tìm.

**Cho phép người dùng nhập regex một cách có chủ đích:** bắt **PatternSyntaxException** để báo lỗi cú pháp có ích:

~~~java
try {
    Pattern userPattern = Pattern.compile("[unclosed");
} catch (java.util.regex.PatternSyntaxException ex) {
    System.out.println("Invalid regex");
}
~~~

Ngoài lỗi cú pháp, regex trên dữ liệu không đáng tin cậy có thể gây **quá tải do backtracking** trong những mẫu phức tạp. Nếu hỗ trợ chế độ tìm regex, nên giới hạn đầu vào, kiểm soát độ phức tạp và kiểm thử những mẫu tốn tài nguyên. **Pattern.quote(query)** giúp tránh diễn giải các ký hiệu regex khi ý định là literal.

## 11. Chọn API theo tình huống

| Yêu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Có chứa đúng **item.42** không? | **text.contains("item.42")** | Dấu chấm là dữ liệu |
| Vị trí đầu tiên của một URL/ID cố định? | **text.indexOf(query)** | Trả về offset UTF-16 |
| Tìm mã **item-** kèm nhiều chữ số | **Pattern.compile("item-\\d+").matcher(text).find()** | Mẫu thay đổi phần chữ số |
| Toàn bộ chuỗi chỉ có ba chữ cái và bốn chữ số | **text.matches("[A-Za-z]{3}\\d{4}")** | Xác thực toàn chuỗi |
| Người dùng nhập dấu ngoặc, dấu cộng, dấu chấm và cần offsets | **Pattern.compile(Pattern.quote(query))** | Tìm literal bằng Matcher |
| Toàn bộ regex phải được hiểu là văn bản | **Pattern.compile(query, Pattern.LITERAL)** | Không diễn giải ký hiệu regex |
| Tách dữ liệu bằng dấu chấm thật | **text.split("\\.")** | split nhận regex |
| Thay dấu chấm bằng dấu gạch ngang | **text.replace(".", "-")** | replace tìm nguyên văn |

Trước khi triển khai một ô tìm kiếm, xác định rõ: literal hay regex, khớp toàn bộ hay một đoạn, có phân biệt chữ hoa/thường không, xử lý Unicode normalization thế nào, có cần tất cả vị trí khớp không và đầu vào rỗng được hiểu ra sao.

## 12. Những lỗi phổ biến

1. **Dùng text.matches("abc") để hỏi có chứa abc không.** Vì matches đòi khớp toàn bộ, dùng **contains** hoặc **Matcher.find**.
2. **Tưởng regex a.b chỉ khớp đúng a.b.** Escape dấu chấm (**"a\\.b"**), hoặc dùng **Pattern.quote**.
3. **Truyền query nguyên văn cho Pattern.compile(query).** Query có thể chứa metacharacter, sai kết quả hoặc gây lỗi cú pháp. Dùng literal search khi thích hợp.
4. **Quên hai tầng escape Java và regex.** Regex **\\.** được viết **"\\."** trong mã Java.
5. **Dùng split(".") để tách dấu chấm.** Regex **.** là wildcard; dùng **split("\\.")**.
6. **Dùng replaceAll(".", "-") để đổi duy nhất dấu chấm.** Nó thay tất cả ký tự khớp wildcard; dùng **replace(".", "-")** hoặc regex escape.
7. **Nhầm quoteReplacement với Pattern.quote.** Một cái xử lý văn bản thay thế, cái kia xử lý từ khóa tìm kiếm.
8. **Tưởng Matcher.start()/end() là số Unicode code point.** Chúng là offset UTF-16; đặc biệt lưu ý emoji ngoài BMP.
9. **Bỏ qua normalization.** Hai chuỗi tiếng Việt cùng hiển thị có thể khác mã hóa và không được tìm thấy nếu không có chính sách chuẩn hóa.
10. **Dùng lại Matcher giữa các luồng.** Matcher mutable, nên tạo riêng từ Pattern đã biên dịch.
11. **Coi mọi regex đều an toàn vì compile thành công.** Regex có thể tiêu thụ nhiều CPU trên một số đầu vào; cần kiểm soát chế độ tìm mẫu do người dùng nhập.

## 13. Tự kiểm tra kiến thức

1. **"a.b"** trong **contains** và **Pattern.compile** khác nhau thế nào? — contains tìm dấu chấm thật; regex a.b cho phép một ký tự bất kỳ ở vị trí giữa.
2. Tại sao **"abc123".matches("\\d+")** là false nhưng **Pattern.compile("\\d+").matcher("abc123").find()** là true? — Khớp toàn bộ khác khớp một đoạn con.
3. Tìm chính xác ký tự dấu chấm bằng String làm thế nào? — **contains(".")** hoặc **indexOf(".")**.
4. Khi query do người dùng nhập có **[**, **?**, **+**, làm sao tìm nguyên văn bằng Matcher? — **Pattern.compile(Pattern.quote(query))**.
5. **Pattern.LITERAL** khác **Pattern.quote** ở đâu? — LITERAL áp dụng cho toàn bộ mẫu; quote cho phép quote một thành phần hoặc cả từ khóa khi xây regex.
6. **Matcher.quoteReplacement** dùng để làm gì? — Giữ nguyên văn bản thay thế, không để **$** và backslash bị diễn giải là cú pháp replacement.
7. **Matcher.start()** trả về loại vị trí nào? — Offset UTF-16.
8. Tìm tiếng Việt muốn coi chữ dạng NFC và NFD tương đương thì làm gì? — Xác định chính sách chuẩn hóa và chuẩn hóa nhất quán dữ liệu với query trước khi tìm.

## 14. Ghi nhớ

- **Tìm nguyên văn:** **String.contains**, **indexOf**, **startsWith**, **endsWith**. Ký tự đặc biệt của regex chỉ là ký tự dữ liệu.
- **Tìm theo mẫu:** **Pattern.compile(regex)** và **Matcher.find()**; kiểm tra full match bằng **Matcher.matches()** hoặc **String.matches(regex)**.
- **Dấu chấm regex . là wildcard**; regex khớp dấu chấm thật cần escape, viết **"\\."** trong Java.
- **Từ khóa người dùng cần tìm nguyên văn:** dùng **Pattern.quote(query)** hoặc **Pattern.LITERAL** khi vẫn cần Regex API.
- **contains/indexOf/replace** và **matches/replaceAll/split** có ngữ nghĩa khác nhau. Chọn đúng API trước khi xử lý escape.
- **Hoa thường, Unicode normalization và grapheme** là các yêu cầu riêng, không tự được giải quyết chỉ nhờ chọn literal hoặc regex.

Tham khảo Java SE 17: **java.lang.String** (contains, indexOf, matches, replace, replaceAll, split), **java.util.regex.Pattern** (compile, quote, LITERAL, flags) và **java.util.regex.Matcher** (find, matches, lookingAt, group, start, end, quoteReplacement).