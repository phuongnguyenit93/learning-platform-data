# Java Regex Unicode: Thay thế văn bản bằng nhóm tên

## 1. Mục tiêu

Khi cần tìm các thành phần có cấu trúc trong văn bản rồi **đổi thứ tự hoặc dựng lại nội dung**, nhóm bắt có tên (*named capturing group*) giúp đặt tên cho từng phần thay vì phải nhớ chúng là nhóm số mấy. Kỹ thuật này vẫn được sử dụng trong Java hiện đại. Các chương trình đầy đủ dưới đây tương thích **Java 17+**.

Ví dụ: biến `Nguyễn, An; Trần, Bình` thành `An Nguyễn; Bình Trần` nhưng giữ nguyên dấu tiếng Việt, dấu chấm phẩy và khoảng trắng ngoài vùng cần thay.

Ba khái niệm cần phân biệt:

- **Regex:** `(?<ho>...)` khai báo nhóm bắt tên `ho`, giúp nhận diện phần văn bản cần lấy.
- **Replacement:** `${ho}` chèn nội dung của nhóm `ho` từ **từng lần khớp**; `${ten} ${ho}` đổi thứ tự hai nhóm.
- **Matcher:** `matcher.group("ho")` đọc nội dung nhóm tên sau khi `find()` hoặc `matches()` thành công; dùng khi cần xử lý dữ liệu trước khi thay.

Lệnh thay thế chỉ đổi đoạn mà regex khớp; phần còn lại của chuỗi được giữ nguyên. Regex kiểm tra **mẫu ký tự**, không tự hiểu ý nghĩa văn bản (như họ tên thật hay ngày tháng hợp lệ).

## 2. Cú pháp chuẩn

| Vị trí | Cú pháp | Chức năng |
|---|---|---|
| Regex | `(?<name>pattern)` | Bắt một đoạn và đặt tên `name` |
| Chuỗi replacement | `${name}` | Chèn giá trị nhóm tên vào kết quả |
| Java API | `matcher.group("name")` | Truy cập nhóm tên của lần khớp thành công |
| Chuỗi replacement | `$1`, `$2` | Tham chiếu nhóm bằng số (vẫn hỗ trợ, nhưng khó bảo trì khi mẫu dài) |
| Regex | `\k<name>` | Tham chiếu ngược tới một nhóm **trong regex**; khác với `${name}` ở replacement |

Tên nhóm trong `java.util.regex.Pattern` bắt đầu bằng chữ cái ASCII `A–Z`/`a–z`; các ký tự tiếp theo là chữ cái ASCII hoặc chữ số. Ví dụ `firstName`, `code2` hợp lệ; `first_name`, `tên`, `2code` không hợp lệ. Không khai báo trùng tên trong cùng regex. Các nhóm có tên cũng được đánh số giống các nhóm bắt thông thường.

**Escape hai lớp:** Khi đặt regex trong Java string, `\` phải viết thành `\\`. Ví dụ regex `\p{L}+` cần Java string `"\\p{L}+"`. Cú pháp replacement `${name}` là của Matcher; đây không phải tính năng nội suy biến trong Java string.

## 3. Ví dụ: đảo thành phần tên có dấu Unicode

Tạo file `NamedGroupReplaceDemo.java`:

~~~java
import java.util.regex.Pattern;

public class NamedGroupReplaceDemo {
    public static void main(String[] args) {
        String input = "Nguyễn, An; Trần, Bình";

        Pattern pattern = Pattern.compile(
                "(?<ho>[\\p{L}\\p{M}]+),\\s*(?<ten>[\\p{L}\\p{M}]+)");

        String result = pattern.matcher(input)
                .replaceAll("${ten} ${ho}");

        System.out.println(result);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 NamedGroupReplaceDemo.java
java NamedGroupReplaceDemo
~~~

Đầu ra chính xác:

~~~text
An Nguyễn; Bình Trần
~~~

Giải thích:

1. `(?<ho>[\\p{L}\\p{M}]+)` bắt `Nguyễn` hoặc `Trần`.
2. `,\\s*` nhận dấu phẩy và khoảng trắng sau dấu phẩy.
3. `(?<ten>[\\p{L}\\p{M}]+)` bắt `An` hoặc `Bình`.
4. `replaceAll("${ten} ${ho}")` xây nội dung mới theo thứ tự tên, rồi họ.
5. Các dấu `; ` và khoảng cách giữa hai trường hợp không khớp regex nên được bảo toàn.

`\p{L}` nhận ký tự Unicode thuộc lớp **Letter**; `\p{M}` nhận **Mark** (dấu kết hợp). Kết hợp hai lớp giúp xử lý văn bản có dấu ở cả dạng ký tự dựng sẵn và dạng chữ + dấu kết hợp. Dùng `[A-Za-z]` sẽ loại bỏ rất nhiều chữ tiếng Việt. Không nên mặc định `\w` ở cấu hình mặc định luôn có nghĩa “mọi chữ Unicode”.

**Giới hạn có chủ ý:** ví dụ trên nhận đúng *một từ trước dấu phẩy* và *một từ sau dấu phẩy*. Tên người có nhiều từ, dấu nối hoặc dấu nháy cần thiết kế mẫu riêng theo định dạng đầu vào. Regex này không phải bộ phân tích họ tên tổng quát.

## 4. Chọn API phù hợp

| Nhu cầu | API |
|---|---|
| Thay mọi đoạn khớp | `pattern.matcher(text).replaceAll(replacement)` |
| Chỉ thay đoạn khớp đầu tiên | `pattern.matcher(text).replaceFirst(replacement)` |
| Viết ngắn gọn, dùng một lần | `text.replaceAll(regex, replacement)` |
| Đọc từng nhóm và thay theo logic riêng | `matcher.find()` + `matcher.group(name)` + `appendReplacement` |
| Chỉ kiểm tra toàn bộ đầu vào | `matcher.matches()` |

`String.replaceAll(regex, replacement)` cũng hiểu `${name}` vì dùng engine regex của Java. Khi mẫu được gọi nhiều lần, nên biên dịch `Pattern` một lần rồi tạo `Matcher` cho từng chuỗi. `String.replace(...)` lại là thay **literal**, không hỗ trợ named groups.

Ví dụ thay mã `AB-123` thành `123/AB`:

~~~java
import java.util.regex.Pattern;

public class CodeReplaceDemo {
    public static void main(String[] args) {
        String input = "Mã AB-123, mã CD-456.";
        Pattern code = Pattern.compile(
                "(?<prefix>[A-Z]{2})-(?<number>[0-9]{3})");

        System.out.println(code.matcher(input)
                .replaceAll("${number}/${prefix}"));
        System.out.println(code.matcher(input)
                .replaceFirst("${number}/${prefix}"));
    }
}
~~~

Kết quả:

~~~text
Mã 123/AB, mã 456/CD.
Mã 123/AB, mã CD-456.
~~~

Mã dùng `[0-9]` vì quy tắc chỉ cho phép chữ số ASCII. Nếu yêu cầu chữ số Unicode rộng hơn, phải xác định rõ đặc tả và chế độ ký tự, không suy ra từ `\d`.

### Đọc nhóm tên trực tiếp

~~~java
Pattern p = Pattern.compile("(?<key>[A-Z]+)=(?<value>[0-9]+)");
var m = p.matcher("A=1; BB=20");

while (m.find()) {
    System.out.println(m.group("key") + " -> " + m.group("value"));
}
~~~

Đây là **đoạn mã minh họa trong phương thức**, với `import java.util.regex.Pattern;`. Kết quả:

~~~text
A -> 1
BB -> 20
~~~

Chỉ gọi `group("key")` sau khi `find()` hoặc `matches()` trả về `true`; nếu chưa có match sẽ gặp `IllegalStateException`. Nếu nhóm tùy chọn không tham gia khớp, `group("name")` trả `null`; nhóm tham gia nhưng khớp chuỗi rỗng trả `""`. Tên nhóm không tồn tại gây `IllegalArgumentException`.

## 5. Thay thế động với tên nhóm

Chuỗi mẫu cố định `"${ten} ${ho}"` phù hợp khi chỉ cần ghép phần đã bắt. Nếu mỗi kết quả cần biến đổi (viết hoa nhãn, tra cứu, chuẩn hóa trường), dùng vòng lặp `find`/`group` và cặp `appendReplacement`/`appendTail`.

Tạo file `DynamicNamedReplaceDemo.java`:

~~~java
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DynamicNamedReplaceDemo {
    public static void main(String[] args) {
        String input = "tên=Nguyễn; giá=100$";
        Pattern pair = Pattern.compile(
                "(?<field>[\\p{L}\\p{M}]+)=(?<value>[^;]+)");

        Matcher matcher = pair.matcher(input);
        StringBuilder result = new StringBuilder();

        while (matcher.find()) {
            String replacement =
                    matcher.group("field").toUpperCase(Locale.ROOT)
                    + "=[" + matcher.group("value") + "]";

            matcher.appendReplacement(
                    result, Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(result);

        System.out.println(result);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DynamicNamedReplaceDemo.java
java DynamicNamedReplaceDemo
~~~

Kết quả:

~~~text
TÊN=[Nguyễn]; GIÁ=[100$]
~~~

`matcher.group("field")` và `group("value")` lấy dữ liệu của **lần khớp hiện tại**. `Locale.ROOT` giúp cách viết hoa không phụ thuộc locale mặc định máy chạy; nếu cần biến đổi theo quy tắc một ngôn ngữ cụ thể thì chọn locale phù hợp.

**Vì sao phải dùng `Matcher.quoteReplacement`?** Bên trong replacement của Matcher, `$` có thể mở đầu tham chiếu nhóm và `\` được dùng để escape. Giá trị động như `100$`, `Giá $5`, đường dẫn có `\` hoặc chuỗi do người dùng cung cấp cần được chèn **nguyên văn**. `quoteReplacement` bảo đảm các ký tự này không bị diễn giải thành cú pháp replacement.

`appendReplacement` nối phần trước match và kết quả mới vào `StringBuilder`. `appendTail` nối phần đuôi sau match cuối; thiếu bước này có thể làm mất dữ liệu cuối chuỗi. `StringBuilder` được hỗ trợ trong overload này trên Java 17+.

Ngoài ra Java hiện đại có `Matcher.replaceAll(Function<MatchResult,String>)` để tính replacement bằng lambda. Trên **Java 17**, `MatchResult` có `group(int)` nhưng chưa có `group(String)`; do đó ví dụ dùng tên nhóm rõ ràng nhất là `Matcher.group("field")` trong vòng lặp. Ngay cả khi dùng lambda, giá trị replacement dạng literal chứa `$` hoặc `\` cũng cần `Matcher.quoteReplacement`.

## 6. Unicode: dấu kết hợp và chuẩn hóa

Một chữ như `é` có thể được biểu diễn bằng một ký tự dựng sẵn (NFC) hoặc `e` + dấu sắc kết hợp (NFD). Vì thế, hai chuỗi trông giống nhau có thể có mã Unicode khác nhau. `\p{L}` bắt chữ cái; `\p{M}` bắt dấu kết hợp; và `Normalizer` cho phép chuẩn hóa theo yêu cầu nghiệp vụ.

Tạo file `UnicodeNamedReplaceDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class UnicodeNamedReplaceDemo {
    public static void main(String[] args) {
        // Chữ e + dấu sắc kết hợp, sau đó là ", An".
        String input = "Cafe\u0301, An";
        String normalized = Normalizer.normalize(
                input, Normalizer.Form.NFC);

        Pattern name = Pattern.compile(
                "(?<family>[\\p{L}\\p{M}]+),\\s*(?<given>[\\p{L}\\p{M}]+)");

        System.out.println(name.matcher(normalized)
                .replaceAll("${given} ${family}"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 UnicodeNamedReplaceDemo.java
java UnicodeNamedReplaceDemo
~~~

Kết quả:

~~~text
An Café
~~~

Chỉ chuẩn hóa NFC khi yêu cầu xử lý/lưu trữ phù hợp; nó thay đổi cách biểu diễn chuỗi. Không tự ý bỏ dấu hay đổi chữ hoa/thường khi nhiệm vụ chỉ là thay thứ tự nhóm.

**Mã điểm Unicode khác ký tự hiển thị:** `Matcher.start()` và `end()` dùng chỉ số theo đơn vị mã UTF-16. Một chữ có dấu tổ hợp, emoji hoặc chuỗi ký tự nối có thể gồm nhiều mã điểm. Không dùng hiệu `end() - start()` làm số ký tự người dùng nhìn thấy. Java 17 có biểu thức `\X` để nhận *grapheme cluster* khi nhiệm vụ cần xử lý cụm ký tự hiển thị; nó cũng có thể khớp emoji, dấu cách..., nên không thay thế tùy tiện `[\p{L}\p{M}]+` trong mẫu nhận diện tên.

`Pattern.UNICODE_CHARACTER_CLASS` hoặc cờ `(?U)` mở rộng ý nghĩa của nhiều lớp ký tự viết tắt, chẳng hạn `\w`, theo Unicode. Với bài thay thế này, biểu diễn rõ bằng `\p{L}` và `\p{M}` giúp người đọc hiểu chính xác tiêu chí nhận diện.

## 7. Literal, escape và các lỗi cần tránh

### Regex và replacement là hai ngôn ngữ cú pháp khác nhau

| Giá trị bạn có | Muốn làm gì | Cách dùng |
|---|---|---|
| `(?<code>[A-Z]+)` | Tìm cấu trúc bằng regex | `Pattern.compile(regex)` |
| `${code}` | Lấy nội dung nhóm trong replacement | `matcher.replaceAll(replacement)` |
| `a+b?` do người dùng nhập | Tìm chính xác chuỗi literal | `Pattern.quote(userInput)` |
| `Giá $5` do người dùng nhập | Chèn nguyên văn thành replacement | `Matcher.quoteReplacement(userText)` |

Hai hàm quote không hoán đổi được: `Pattern.quote` bảo vệ **phần tìm kiếm**; `Matcher.quoteReplacement` bảo vệ **phần thay thế**.

Ví dụ: đoạn mã sau đặt trong phương thức Java, với import `java.util.regex.Matcher` và `java.util.regex.Pattern`:

~~~java
String userText = "Giá $5";
String safe = Pattern.compile("(?<item>book)")
        .matcher("book")
        .replaceAll(Matcher.quoteReplacement(userText));
System.out.println(safe); // Giá $5
~~~

Nếu dùng thẳng `replaceAll(userText)`, dấu `$` có thể bị hiểu là tham chiếu nhóm và làm hỏng kết quả.

| Lỗi | Cách sửa |
|---|---|
| Viết `$name` để lấy nhóm tên | Dùng `${name}` trong replacement. |
| Dùng `${name}` làm tham chiếu ngược bên trong regex | Dùng `\k<name>` **trong regex**. |
| Viết `(?<first_name>...)` hoặc tên nhóm có dấu | Đổi thành tên hợp lệ như `firstName`. |
| Quên escape trong Java string | Viết `"\\p{L}"` để regex nhận `\p{L}`. |
| Gọi `group(name)` trước khi `find()` thành công | Kiểm tra kết quả tìm kiếm trước khi đọc nhóm. |
| Chèn replacement động chứa `$` hoặc `\` | Bọc bằng `Matcher.quoteReplacement`. |
| Quên `appendTail` | Gọi sau vòng lặp để giữ phần văn bản cuối. |
| Dùng `String.replace` để xử lý regex | Dùng `String.replaceAll` hoặc `Matcher`. |
| Tự cho rằng mẫu đơn giản nhận mọi tên hoặc mọi ngày tháng | Kiểm thử định dạng đầu vào; nếu cần ngày hợp lệ, dùng `java.time` để kiểm tra giá trị. |

**Hiệu năng và an toàn:** `Pattern` bất biến nên có thể dùng chung, còn `Matcher` giữ trạng thái và không được chia sẻ giữa các luồng. Tránh ghép trực tiếp văn bản không tin cậy thành regex; dùng `Pattern.quote` nếu đó là chuỗi literal. Hạn chế regex có lượng từ lồng nhau dễ gây backtracking, giới hạn kích thước đầu vào theo nghiệp vụ và kiểm thử trường hợp xấu.

## 8. Checklist áp dụng và bài tập

Khi xây giải pháp thay thế bằng nhóm tên:

1. Xác định đúng các trường cần bắt, trường cần giữ nguyên và các ký tự phân cách.
2. Dùng tên nhóm mô tả ý nghĩa (`prefix`, `number`, `given`...), chọn lớp Unicode theo đặc tả.
3. Nhớ escape regex trong Java string (`\\p{L}`, `\\s`).
4. Nếu thay cố định, dùng `${name}` với `replaceAll` hoặc `replaceFirst`.
5. Nếu thay theo logic, dùng `find()`, `group(name)`, `appendReplacement`, `appendTail` và `quoteReplacement`.
6. Thử không có match, nhiều match, nhóm tùy chọn, tiếng Việt có dấu, dữ liệu chứa `$`/`\` và các biến thể Unicode cần hỗ trợ.

**Bài tập:** Đổi `"SP-042 và DV-105"` thành `"042 (SP) và 105 (DV)"`, dùng hai nhóm tên `type` và `id`.

Lời giải (đoạn mã trong một phương thức, với import `java.util.regex.Pattern`):

~~~java
String input = "SP-042 và DV-105";
Pattern p = Pattern.compile(
        "(?<type>[A-Z]{2})-(?<id>[0-9]{3})");
String output = p.matcher(input)
        .replaceAll("${id} (${type})");
System.out.println(output); // 042 (SP) và 105 (DV)
~~~

Lời giải quy định mã loại gồm đúng hai chữ hoa ASCII và mã số gồm đúng ba chữ số ASCII. Nếu dữ liệu thực tế khác, phải điều chỉnh regex theo đặc tả, không mở rộng ngầm.

## 9. Tài liệu chuẩn để đối chiếu

- [Pattern — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): named groups, Unicode character classes, cờ Unicode và regex syntax.
- [Matcher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html): `group(name)`, `replaceAll`, `replaceFirst`, `appendReplacement`, `appendTail` và `quoteReplacement`.
- [MatchResult — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/MatchResult.html): API đọc nhóm của kết quả khớp.
- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa biểu diễn Unicode.

Các kỹ thuật trong bài dùng thư viện chuẩn Java còn được hỗ trợ hiện nay, đáp ứng yêu cầu chỉ học những kiến thức vẫn áp dụng được.