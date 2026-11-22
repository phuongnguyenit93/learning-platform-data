# Phân biệt replace, replaceFirst và replaceAll trong Java

Ba phương thức xử lý chuỗi `replace()`, `replaceFirst()` và `replaceAll()` đều tạo kết quả biến đổi từ một `String`. Điểm khác biệt quyết định là **phần cần tìm có được coi là văn bản nguyên vẹn (literal) hay regex**, và **thay một hay nhiều lần**. Ngoài ra, với hai phương thức regex, chuỗi thay thế có cú pháp đặc biệt dành cho các nhóm bắt.

**Quy tắc cốt lõi:** `replace()` tìm literal và thay **tất cả**; `replaceFirst()` tìm regex và thay **khớp đầu tiên**; `replaceAll()` tìm regex và thay **tất cả các khớp không chồng lấp**.

## 1. So sánh API

| Phương thức | Cách hiểu phần cần tìm | Số lần thay | Cách hiểu nội dung thay thế |
|---|---|---|---|
| `replace(char, char)` | Một ký tự `char` theo UTF-16 | Mọi lần xuất hiện | Literal |
| `replace(CharSequence, CharSequence)` | Chuỗi con literal | Mọi lần xuất hiện không chồng lấp | Literal, kể cả dollar và backslash |
| `replaceFirst(String regex, String replacement)` | Regex | Khớp đầu tiên | Có cú pháp nhóm bắt như `$1` |
| `replaceAll(String regex, String replacement)` | Regex | Tất cả các khớp | Có cú pháp nhóm bắt như `$1` |

Ví dụ:

~~~java
String text = "a.b.a";
System.out.println(text.replace(".", "-"));      // a-b-a
System.out.println(text.replaceFirst(".", "-")); // -.b.a
System.out.println(text.replaceAll(".", "-"));   // -----
~~~

Trong `replace()`, dấu chấm là ký tự chấm thật. Trong regex, dấu chấm thường có nghĩa là khớp một ký tự bất kỳ (trừ một số ký tự kết thúc dòng nếu không bật chế độ DOTALL), nên `replaceAll(".", "-")` thay cả năm ký tự.

Với `String` bất biến, ba phép gọi đều **không sửa đối tượng `text`**. Muốn giữ kết quả, phải gán lại biến hoặc chuyển trực tiếp kết quả sang bước xử lý tiếp theo.

## 2. replace(): thay mọi chuỗi con literal

Hai overload của `String` là:

~~~java
public String replace(char oldChar, char newChar)
public String replace(CharSequence target, CharSequence replacement)
~~~

Đây là **chữ ký API minh họa**, không phải một file Java chạy độc lập.

Đặc tính:

- `replace(char,char)` thay mọi code unit bằng `oldChar` bằng `newChar`.
- `replace(CharSequence,CharSequence)` tìm một đoạn literal và thay mọi lần xuất hiện không chồng lấp.
- Pattern và replacement đều **không phải regex**. Dấu chấm, dấu sao, dollar, ngoặc vuông hoặc backslash mang nghĩa văn bản thuần.
- Tên `replace` không có chữ `All`, nhưng phương thức này vẫn thay **tất cả lần xuất hiện** của literal.

~~~java
System.out.println("a.b".replace(".", "-"));         // a-b
System.out.println("a.b".replace('.', '_'));         // a_b
System.out.println("a.b".replace(".", "$1"));        // a$1b
System.out.println("red red".replace("red", "blue")); // blue blue
System.out.println("aaaa".replace("aa", "X"));       // XX
~~~

Ở ví dụ `"aaaa"`, các đoạn `"aa"` được chọn tại vị trí 0 và 2, nên cho `"XX"`. Những lần khớp **không chồng lấp**; phương thức không duyệt mọi đoạn có thể bắt đầu ở từng vị trí.

Với emoji như 🚀, một ký tự hiển thị có thể gồm hai UTF-16 `char`, nên muốn thay trọn emoji nên chọn overload nhận `CharSequence`:

~~~java
System.out.println("🚀 + 🚀".replace("🚀", "⭐")); // ⭐ + ⭐
~~~

Nếu `target` là chuỗi rỗng, phép thay có thể chèn chuỗi thay vào đầu, giữa các code unit và cuối: `"ab".replace("", "-")` cho `"-a-b-"`. Cần xác thực giá trị tìm kiếm rỗng nếu không muốn hành vi đó.

## 3. replaceFirst(): chỉ thay kết quả regex đầu tiên

Chữ ký:

~~~java
public String replaceFirst(String regex, String replacement)
~~~

Tham số đầu được biên dịch như regex. Java tìm khớp đầu tiên bên trong chuỗi rồi thay đúng một lần. Nó không yêu cầu toàn bộ chuỗi khớp regex.

~~~java
String text = "Mã 12, mã 345, mã 67";
System.out.println(text.replaceFirst("\\d+", "#"));
// Mã #, mã 345, mã 67

System.out.println("red red".replaceFirst("red", "blue")); // blue red
System.out.println("abc123def".replaceFirst("\\d+", "#")); // abc#def
System.out.println("hello".replaceFirst("\\d+", "#")); // hello
~~~

Regex `\\d+` biểu diễn một hoặc nhiều chữ số. Vì cần truyền backslash vào regex engine, **mã nguồn Java** phải viết `"\\d+"`, không thể viết ký tự escape Java không hợp lệ. `replaceFirst()` dùng việc tìm *đoạn con* tương tự `Matcher.find()`, khác `String.matches()` kiểm tra **toàn bộ** chuỗi.

Để thay dấu chấm đầu tiên theo nghĩa literal bằng API regex, cần escape dấu chấm:

~~~java
System.out.println("a.b.c".replaceFirst("\\.", "/")); // a/b.c
~~~

Nếu chỉ có một từ cần thay theo nghĩa literal, có thể dùng `Pattern.quote(target)` trước khi gọi `replaceFirst()`, và `Matcher.quoteReplacement(replacement)` khi chuỗi thay có dấu dollar hoặc backslash.

## 4. replaceAll(): thay mọi kết quả regex

Chữ ký:

~~~java
public String replaceAll(String regex, String replacement)
~~~

Nó tìm các match regex không chồng lấp và thay tất cả. Regex linh hoạt hơn literal vì có thể mô tả nhóm ký tự, số lần lặp, ranh giới và các điều kiện khác.

~~~java
String text = "Mã 12, mã 345, mã 67";
System.out.println(text.replaceAll("\\d+", "#"));
// Mã #, mã #, mã #

System.out.println("A  B   C".replaceAll(" +", " ")); // A B C
System.out.println("abc123def456".replaceAll("\\d+", "#")); // abc#def#
System.out.println("a,b;c".replaceAll("[,;]", "|")); // a|b|c
~~~

Regex `\\d+` gom một **chuỗi chữ số liên tiếp** thành một match. Regex `" +"` tìm cụm một hoặc nhiều dấu cách. Nếu cần nhóm whitespace rộng hơn, cân nhắc `\\s+` nhưng phải hiểu quy tắc lớp ký tự và Unicode flags của Java; nó không tự tương đương mọi tiêu chí Unicode whitespace trong ứng dụng.

Nếu chỉ thay mọi lần xuất hiện một đoạn cố định, `replace()` thường phù hợp hơn `replaceAll()` vì không phải diễn giải regex.

## 5. Escape: có hai tầng cú pháp khác nhau

Khi viết Java source, phải phân biệt:

1. **Java string literal:** dấu backslash là dấu escape cho Java.
2. **Regex pattern:** Java regex xử lý các toán tử như `.`, `*`, `+`, `[]`, `()`, `^`, dollar và các character class.
3. **Regex replacement:** dấu dollar đi cùng chỉ số nhóm như `$1`, `$2` có ý nghĩa thay bằng nhóm được bắt; backslash có thể escape ký tự trong replacement.

### 5.1. Pattern có ký tự đặc biệt

| Mục đích | Java String literal dùng làm regex |
|---|---|
| Một hoặc nhiều chữ số | `"\\d+"` |
| Dấu chấm thật | `"\\."` |
| Dấu dollar thật | `"\\$"` |
| Một hoặc nhiều dấu cách ASCII | `" +"` |
| Chuỗi con literal do người dùng nhập | `Pattern.quote(userText)` |

Chú ý trong Java 17, Java escape `"\s"` tạo **một dấu cách** trước khi tới regex engine. Nếu muốn regex `\\s`, phải viết `"\\s"` ở source. Đây là một lỗi dễ lọt qua quá trình biên dịch vì `"\s"` là Java String literal hợp lệ trên Java hiện đại nhưng không có nghĩa regex whitespace class.

### 5.2. Replacement có `$1` và các nhóm bắt

Ví dụ đổi thứ tự họ và tên được ngăn cách bởi dấu phẩy:

~~~java
String name = "Nguyen, An";
String result = name.replaceAll("(\\w+),\\s*(\\w+)", "$2 $1");
System.out.println(result); // An Nguyen
~~~

Regex có hai nhóm bắt: nhóm 1 là `Nguyen`, nhóm 2 là `An`. Trong replacement, `$2 $1` lấy nhóm 2 trước rồi đến nhóm 1. Nếu muốn nhóm chỉ để gom cấu trúc mà không đánh số, dùng dạng `(?:...)`; nhóm có tên được khai báo với cú pháp `(?<name>...)` và tham chiếu bằng tên theo tài liệu `Matcher`.

Trong `replace()`, replacement `"$1"` là literal, không tham chiếu nhóm. Trong `replaceAll()` hoặc `replaceFirst()`, replacement `"$1"` có nghĩa đặc biệt; nếu không có nhóm bắt tương ứng, có thể ném exception. Không trộn hai ngữ nghĩa.

### 5.3. Dữ liệu replacement có dollar/backslash

Nếu replacement đến từ người dùng và cần giữ nguyên tất cả ký tự, dùng `Matcher.quoteReplacement()`:

~~~java
import java.util.regex.Matcher;

String replacement = "$1\\temp";
String result = "abc".replaceAll(
        "b", Matcher.quoteReplacement(replacement));

System.out.println(result.equals("a$1\\tempc")); // true
~~~

`quoteReplacement()` bảo đảm dollar và backslash **không bị hiểu như cú pháp replacement**. Hàm này **không** biến regex trong tham số tìm kiếm thành literal.

### 5.4. Dữ liệu tìm kiếm có dấu regex

Nếu muốn tìm dấu chấm do người dùng nhập, truyền trực tiếp dấu chấm vào `replaceAll()` sẽ gây khớp rộng. Dùng `Pattern.quote()` để bảo vệ bên tìm kiếm:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String source = "a.b";
String find = ".";
String put = "$5\\x";
String converted = source.replaceAll(
        Pattern.quote(find),
        Matcher.quoteReplacement(put));

System.out.println(converted.equals("a$5\\xb")); // true
~~~

`Pattern.quote()` bảo vệ cú pháp regex **pattern**; `Matcher.quoteReplacement()` bảo vệ cú pháp **replacement**. Nếu cả hai đầu đều literal, viết `source.replace(find, put)` đơn giản và rõ ràng hơn.

## 6. Trường hợp biên quan trọng

### Match rỗng hoặc có độ rộng bằng 0

~~~java
System.out.println("ab".replace("", "-"));         // -a-b-
System.out.println("ab".replaceFirst("", "-"));    // -ab
System.out.println("ab".replaceAll("", "-"));      // -a-b-
~~~

Regex có thể khớp tại **vị trí** không tiêu thụ ký tự, chẳng hạn regex rỗng hay lookahead. Regex engine có quy tắc tiến vị trí để tránh lặp vô hạn trong lúc thay. Vì vậy cần kiểm tra input tìm kiếm rỗng trước nếu đó không phải kết quả mong đợi.

### Không thay các match chồng lấp

~~~java
System.out.println("aaaa".replace("aa", "X"));       // XX
System.out.println("aaaa".replaceFirst("aa", "X"));  // Xaa
System.out.println("aaaa".replaceAll("aa", "X"));    // XX
~~~

Ở đây regex hoặc phép tìm literal xét các match không chồng lấp. Nếu cần một thuật toán đặc biệt xử lý cả các vị trí chồng lấp, hãy thiết kế bài toán riêng với lookaround, vị trí hoặc logic quét chuỗi; không mặc định những API trên làm việc đó.

### Replacement mới không bị thay tiếp trong cùng lượt

~~~java
System.out.println("aaa".replace("a", "aa")); // aaaaaa
~~~

`replace()` thực hiện một lượt trên dữ liệu gốc: ba ký tự `a` được thay thành sáu ký tự `a`. Nó không tự lặp thay trên phần văn bản mới sinh ra cho đến vô hạn.

### Không tự thay đổi String ban đầu

~~~java
String s = "red red";
s.replace("red", "blue");
System.out.println(s); // red red
s = s.replace("red", "blue");
System.out.println(s); // blue blue
~~~

Nhớ sử dụng giá trị trả về do `String` immutable.

### Null và regex không hợp lệ

- Tham chiếu nhận `String` là null: gọi phương thức sẽ ném `NullPointerException`.
- Target/pattern/replacement cần dữ liệu không null. Phải xác thực trước; không dùng null để diễn đạt “bỏ qua thay thế”.
- Regex sai cú pháp, ví dụ `"["`, có thể ném `PatternSyntaxException`.
- Replacement có tham chiếu nhóm không tồn tại có thể ném exception; `Matcher.quoteReplacement()` là cách giải quyết khi muốn literal.

~~~java
try {
    "abc".replaceAll("[", "x");
} catch (java.util.regex.PatternSyntaxException e) {
    System.out.println("Invalid regex"); // Invalid regex
}
~~~

### Unicode và ký tự hiển thị

Overload `char` làm việc theo UTF-16 code unit; emoji thường gồm hai `char`. Dùng overload `CharSequence` khi muốn thay một emoji nguyên vẹn. Đồng thời, `replace()` và regex **không tự chuẩn hóa Unicode**. Hai chuỗi nhìn giống nhau, như `é` dựng sẵn và `e` cộng dấu sắc, có thể không khớp theo dãy code point; nếu cần đối chiếu biểu diễn tương đương, sử dụng `Normalizer` một cách có chủ đích.

## 7. Hiệu năng và an toàn khi xử lý dữ liệu động

Với các literal ngắn hoặc từ khóa cố định, `replace()` thường rõ nghĩa và tránh công việc xử lý regex không cần thiết. Nếu phải áp dụng **một regex lặp lại nhiều lần**, có thể compile `Pattern` một lần rồi dùng `Matcher` trên từng chuỗi:

~~~java
import java.util.regex.Pattern;

Pattern numbers = Pattern.compile("\\d+");
System.out.println(numbers.matcher("A12").replaceAll("#"));  // A#
System.out.println(numbers.matcher("B345").replaceAll("#")); // B#
~~~

`Pattern` có thể chia sẻ và tái sử dụng; `Matcher` thay đổi trạng thái và không nên dùng đồng thời giữa nhiều thread nếu không quản lý an toàn. Đừng khẳng định regex luôn chậm hơn trong mọi trường hợp; đo bằng profiler/JMH với dữ liệu đại diện khi có yêu cầu hiệu năng.

**Regex nhận từ người dùng** có thể bị lỗi cú pháp và một số mẫu có thể gây xử lý rất chậm với input phù hợp (*ReDoS*). Nếu người dùng chỉ muốn tìm literal, tránh đưa input vào regex nguyên trạng: dùng `replace()` hoặc `Pattern.quote()`. Nếu thật sự cung cấp tính năng regex, giới hạn độ dài input/pattern, kiểm thử worst case và đặt các chính sách bảo vệ tài nguyên. `Pattern.quote()` khiến pattern trở thành literal, không phải cách “làm regex tùy ý an toàn” mà vẫn giữ chức năng regex.

Khi thay liên tiếp trên một `String` lớn trong nhiều vòng lặp, tạo `String` trung gian có thể tốn bộ nhớ; cân nhắc `StringBuilder` hoặc thuật toán xử lý theo luồng tùy bài toán.

## 8. Chương trình Java 17 hoàn chỉnh

Lưu đoạn sau vào file UTF-8 **`ReplaceMethodsDemo.java`**. Khác với các snippet riêng lẻ ở phần trên, đây là một chương trình chạy độc lập.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReplaceMethodsDemo {
    public static void main(String[] args) {
        String source = "a.b.a";
        System.out.println("literal=" + source.replace(".", "-"));
        System.out.println("regexFirst=" + source.replaceFirst(".", "-"));
        System.out.println("regexAll=" + source.replaceAll(".", "-"));
        System.out.println("escapedFirst=" + source.replaceFirst("\\.", "-"));
        System.out.println("escapedAll=" + source.replaceAll("\\.", "-"));

        String repeated = "aa aa aa";
        System.out.println("repeatLiteral=" + repeated.replace("aa", "X"));
        System.out.println("repeatFirst=" + repeated.replaceFirst("aa", "X"));
        System.out.println("repeatAll=" + repeated.replaceAll("aa", "X"));

        String digits = "AB12-CD034";
        System.out.println("digitsFirst=" + digits.replaceFirst("\\d+", "#"));
        System.out.println("digitsAll=" + digits.replaceAll("\\d+", "#"));

        String name = "Nguyen, An";
        System.out.println("group=" +
                name.replaceAll("(\\w+),\\s*(\\w+)", "$2 $1"));

        String find = ".";
        String replace = "$5\\x";
        String safe = "a.b".replaceAll(Pattern.quote(find),
                Matcher.quoteReplacement(replace));
        System.out.println("safeLiteral=" + safe.equals("a$5\\xb"));

        System.out.println("overlap=" + "aaaa".replace("aa", "X"));
        System.out.println("emptyTarget=" + "ab".replace("", "-"));
        System.out.println("original=" + source);
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 ReplaceMethodsDemo.java
java ReplaceMethodsDemo
~~~

Đầu ra:

~~~text
literal=a-b-a
regexFirst=-.b.a
regexAll=-----
escapedFirst=a-b.a
escapedAll=a-b-a
repeatLiteral=X X X
repeatFirst=X aa aa
repeatAll=X X X
digitsFirst=AB#-CD034
digitsAll=AB#-CD#
group=An Nguyen
safeLiteral=true
overlap=XX
emptyTarget=-a-b-
original=a.b.a
~~~

`regexAll` cho năm dấu `-` vì regex `.` khớp toàn bộ từng ký tự của `a.b.a`. `safeLiteral=true` xác minh cả dollar và backslash của replacement được giữ nguyên nhờ `Matcher.quoteReplacement()`. `original=a.b.a` cho thấy các phương thức không đổi nội dung String nguồn.

## 9. Lỗi thường gặp

| Lỗi | Vì sao | Cách xử lý |
|---|---|---|
| `replaceAll(".", "X")` để thay dấu chấm | Dấu chấm là toán tử regex | Dùng `replace(".", "X")` hoặc regex dấu chấm đã escape |
| Nghĩ `replace()` chỉ thay một lần | Tên phương thức dễ gây nhầm | `replace()` thay tất cả literal |
| Tìm văn bản từ người dùng qua regex nguyên trạng | Dấu ngoặc/sao/chấm có nghĩa đặc biệt | `replace()` hoặc `Pattern.quote()` |
| Replacement từ người dùng có dollar | Có thể bị giải nghĩa như nhóm regex | `Matcher.quoteReplacement()` |
| Viết Java regex `"\d+"` | Dấu escape của Java không hợp lệ | `"\\d+"` |
| Viết `"\s+"` để tìm whitespace regex | Trong Java mới, `\\s` ở mức Java literal có thể là dấu cách | Viết `"\\s+"` |
| Không dùng giá trị trả về | String bất biến | Gán lại hoặc chuyển tiếp kết quả |
| Dùng `replace(char,char)` cho cả emoji | Một emoji có thể gồm hai code unit | Dùng `replace(CharSequence,CharSequence)` |
| Tưởng thay thế diễn ra đệ quy | Một lượt match trên chuỗi đầu vào | Nếu cần nhiều pha, xây dựng rõ các bước |
| Chấp nhận regex tùy ý không giới hạn | Có thể lỗi syntax hoặc tiêu tốn CPU | Validate, giới hạn và kiểm thử |

## 10. Checklist chọn đúng phương thức

1. **Thay literal tại mọi nơi:** chọn `replace()`.
2. **Thay match regex đầu tiên:** chọn `replaceFirst()`.
3. **Thay tất cả match regex:** chọn `replaceAll()`.
4. **Có dấu chấm, dollar, backslash hoặc dấu ngoặc trong input:** phân biệt ký tự thuộc *pattern* hay *replacement*; dùng quote phù hợp nếu phải đi qua regex.
5. **Input rỗng, null hoặc Unicode phức tạp:** kiểm tra và quyết định ngữ nghĩa từ trước.
6. **Regex được áp dụng nhiều lần:** có thể compile `Pattern` một lần; dùng `Matcher` mới hoặc được quản lý đúng cho mỗi tác vụ.
7. **Có nhu cầu tối ưu hay xử lý dữ liệu không tin cậy:** đo hiệu năng và kiểm soát kích thước/độ phức tạp regex.

**Ghi nhớ:** `replace()` thay mọi literal; `replaceFirst()` thay regex match đầu tiên; `replaceAll()` thay mọi regex match. Với regex, **pattern và replacement có cú pháp khác nhau**, và còn phải escape đúng khi viết Java source.