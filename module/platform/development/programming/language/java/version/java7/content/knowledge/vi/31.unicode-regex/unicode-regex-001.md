# Nhóm bắt có tên và đọc kết quả theo tên trong Java Regex

## Mục tiêu

**Nhóm bắt có tên** (*named capturing group*) cho phép gắn tên có ý nghĩa cho phần dữ liệu khớp một biểu thức chính quy. Thay vì chỉ truy cập kết quả bằng `matcher.group(1)`, `matcher.group(2)`, ta dùng tên như `matcher.group("year")`. Cách này làm code dễ đọc, nhất là khi biểu thức có nhiều nhóm và cần chỉnh sửa cấu trúc sau này.

Ví dụ `(?<prefix>[A-Z]{2})-(?<year>\d{4})` khớp `HD-2026` và bắt được `prefix = "HD"`, `year = "2026"`. Nhóm có tên đã được hỗ trợ từ Java 7 và **vẫn được dùng trong các phiên bản Java hiện đại**. Bài này dùng các chương trình Java 17+ có thể tự biên dịch, bao gồm nội dung Unicode phù hợp với ngữ cảnh Regex Unicode.

## 1. Cú pháp và các API liên quan

| Cú pháp / lời gọi | Vai trò |
| --- | --- |
| `(?<code>[A-Z]{2})` | Đặt tên `code` cho nhóm bắt hai chữ in hoa. |
| `matcher.group("code")` | Đọc văn bản nhóm `code` đã bắt trong lần khớp thành công gần nhất. |
| `matcher.start("code")` | Chỉ số bắt đầu của nhóm (tính cả vị trí này). |
| `matcher.end("code")` | Chỉ số kết thúc của nhóm (không tính vị trí này). |
| `\k<code>` | Tham chiếu ngược đến nội dung của nhóm `code` ngay **trong regex**. |
| `${code}` | Chèn kết quả nhóm `code` vào **chuỗi thay thế** của `Matcher.replaceAll` hoặc `replaceFirst`. |
| `(?:...)` | Gom một biểu thức con nhưng không tạo capturing group mới. |

Cấu trúc đầy đủ: `(?<tenNhom>regexCon)`. Tên nhóm bắt đầu bằng chữ cái ASCII `A-Z` hoặc `a-z`, các ký tự tiếp theo chỉ được là chữ cái ASCII hoặc chữ số `0-9`. Các tên `userId`, `year2` hợp lệ; `2year`, `user_id`, `tên` không hợp lệ. Trong một `Pattern` không được khai báo hai nhóm cùng tên. Đây là **quy định về tên nhóm**, không phải giới hạn nội dung nhóm được phép khớp: nhóm tên `name` vẫn bắt được chữ Unicode.

Nhóm có tên vẫn được **đánh số** theo thứ tự dấu ngoặc mở của capturing group. `group(0)` hay `group()` là toàn bộ phần khớp; `group(1)` là nhóm bắt thứ nhất. `(?:...)` không tham gia đánh số. Khi đã đặt tên, ưu tiên đọc bằng tên vì dễ bảo trì.

Lưu ý phiên bản: nhóm có tên và `group(String)` có từ **Java 7**, còn `start(String)` và `end(String)` có từ **Java 8**. Tất cả vẫn được hỗ trợ.

### Hai lần escape khi viết regex trong Java String

Java string literal và regex đều dùng backslash. Vì vậy:

| Regex muốn chạy | Viết trong Java source |
| --- | --- |
| `\d{4}` | `"\\d{4}"` |
| `\k<word>` | `"\\k<word>"` |
| `\p{L}+` | `"\\p{L}+"` |

Viết `"\d"` trong Java sẽ không biên dịch vì `\d` không phải Java string escape hợp lệ.

## 2. Tìm nhiều kết quả và đọc theo tên

Lưu thành **`NamedGroupsDemo.java`**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class NamedGroupsDemo {
    public static void main(String[] args) {
        String input = "HD-2026; AB-2048";
        Pattern pattern = Pattern.compile(
                "(?<prefix>[A-Z]{2})-(?<year>\\d{4})");
        Matcher matcher = pattern.matcher(input);

        while (matcher.find()) {
            System.out.printf(
                    "%s | %s | %s | [%d, %d)%n",
                    matcher.group(),
                    matcher.group("prefix"),
                    matcher.group("year"),
                    matcher.start("prefix"),
                    matcher.end("prefix"));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NamedGroupsDemo.java
java NamedGroupsDemo
~~~

Đầu ra chính xác:

~~~text
HD-2026 | HD | 2026 | [0, 2)
AB-2048 | AB | 2048 | [9, 11)
~~~

**Diễn giải:**

1. `Pattern.compile` tạo regex đã biên dịch, còn `pattern.matcher(input)` tạo `Matcher` gắn với chuỗi đầu vào.
2. Mỗi lần gọi `find()` thành công, `Matcher` trỏ đến **đoạn con** tiếp theo phù hợp. Ở đây có hai đoạn: `HD-2026` và `AB-2048`.
3. `group()` là toàn bộ đoạn khớp; `group("prefix")` trả `HD` hoặc `AB`; `group("year")` trả `2026` hoặc `2048`.
4. Khoảng `[start, end)` bao gồm vị trí bắt đầu và loại trừ vị trí kết thúc. Vì vậy `AB` nằm ở `[9, 11)`.

**Chọn cách khớp đúng:** `find()` tìm một đoạn con phù hợp; `matches()` yêu cầu **toàn bộ** chuỗi phù hợp; `lookingAt()` yêu cầu phù hợp từ đầu chuỗi nhưng không nhất thiết đến hết. Sau thao tác khớp thất bại, không được đọc các nhóm như thể đang có kết quả thành công.

## 3. Nhóm tùy chọn: `null` khác với `""`

Khi nhóm `(?<name>...)` nằm trong một phần tùy chọn và **không tham gia** lần khớp, `group("name")` trả về `null`, còn `start("name")` và `end("name")` trả `-1`. Nếu nhóm thực sự tham gia nhưng **khớp chuỗi rỗng**, `group("name")` trả `""` và hai vị trí bằng nhau. Không nên gộp hai trường hợp.

Lưu thành **`OptionalGroupDemo.java`**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class OptionalGroupDemo {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile(
                "(?<key>[A-Z]+)(?:=(?<value>.*))?");

        for (String input : new String[] {
                "MODE", "LEVEL=", "COLOR=blue" }) {
            Matcher matcher = pattern.matcher(input);
            if (matcher.matches()) {
                String value = matcher.group("value");
                System.out.println(input + " -> "
                        + (value == null ? "(missing)" : "[" + value + "]"));
            }
        }
    }
}
~~~

Chạy `javac -encoding UTF-8 OptionalGroupDemo.java` rồi `java OptionalGroupDemo`:

~~~text
MODE -> (missing)
LEVEL= -> []
COLOR=blue -> [blue]
~~~

Cụm `(?:=(?<value>.*))?` cho phép cả phần `=...` vắng mặt. Dấu `?:` giúp phần bao ngoài không trở thành một nhóm bắt mới. Nếu muốn cấm giá trị rỗng, cân nhắc đổi `.*` thành `.+` và quy định rõ input nào hợp lệ.

## 4. Tham chiếu ngược theo tên và thay thế theo tên

Trong **regex**, cú pháp `\k<word>` yêu cầu phần sau phải giống văn bản nhóm `word` đã bắt trước đó. Còn trong **replacement string**, cú pháp `${year}` đưa nội dung nhóm `year` vào chuỗi kết quả. Hai cú pháp có ý nghĩa khác nhau.

Lưu thành **`NamedGroupReuseDemo.java`**:

~~~java
import java.util.regex.Pattern;

public class NamedGroupReuseDemo {
    public static void main(String[] args) {
        Pattern repeated = Pattern.compile(
                "(?<word>[A-Za-z]+)\\s+\\k<word>",
                Pattern.CASE_INSENSITIVE);

        System.out.println(repeated.matcher("Java JAVA").matches());
        System.out.println(repeated.matcher("Java Kotlin").matches());

        Pattern dates = Pattern.compile(
                "(?<year>\\d{4})-(?<month>\\d{2})-(?<day>\\d{2})");
        String result = dates.matcher("2026-11-05")
                .replaceAll("${day}/${month}/${year}");
        System.out.println(result);
    }
}
~~~

Chạy `javac -encoding UTF-8 NamedGroupReuseDemo.java` rồi `java NamedGroupReuseDemo`:

~~~text
true
false
05/11/2026
~~~

`Pattern.CASE_INSENSITIVE` phù hợp cho ví dụ sử dụng `[A-Za-z]`. Nếu so khớp không phân biệt hoa/thường với chữ Unicode, cân nhắc dùng thêm `Pattern.UNICODE_CASE` và kiểm thử trên ngôn ngữ thực tế.

**Lưu ý khi thay thế:** các ký tự `$` và backslash có ý nghĩa đặc biệt trong replacement string. Nếu giá trị thay thế lấy từ người dùng và phải được hiểu **nguyên văn**, sử dụng `Matcher.quoteReplacement(value)`. Nếu muốn thay bằng nội dung nhóm, dùng đúng `${name}`.

## 5. Kết hợp nhóm có tên với Unicode

Tên nhóm chỉ dùng ký tự ASCII, nhưng nội dung nhóm có thể là tiếng Việt có dấu. `\p{L}` khớp các chữ cái Unicode; `\p{M}` khớp dấu kết hợp (*combining marks*). Ghép `[\p{L}\p{M}]+` giúp khớp chữ ở dạng dựng sẵn hoặc chữ có dấu kết hợp.

Lưu thành **`UnicodeNamedGroupDemo.java`**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeNamedGroupDemo {
    public static void main(String[] args) {
        String input = "Tên: Nguyễn";
        Pattern pattern = Pattern.compile(
                "Tên: (?<name>[\\p{L}\\p{M}]+)");
        Matcher matcher = pattern.matcher(input);

        if (matcher.matches()) {
            System.out.println(matcher.group("name"));
        }
    }
}
~~~

Chạy trong terminal hỗ trợ UTF-8:

~~~bash
javac -encoding UTF-8 UnicodeNamedGroupDemo.java
java UnicodeNamedGroupDemo
~~~

Kết quả:

~~~text
Nguyễn
~~~

Một số ký hiệu rút gọn như `\w` và `\b` có hành vi phụ thuộc vào cờ Unicode. Khi cần xử lý dữ liệu nhiều ngôn ngữ, xem xét `Pattern.UNICODE_CHARACTER_CLASS` hoặc cờ `(?U)`, kiểm thử dữ liệu có dấu và cân nhắc chuẩn hóa Unicode nếu cần so sánh. Cờ này **không thay đổi quy định đặt tên nhóm**.

`start(name)` và `end(name)` sử dụng chỉ số **UTF-16 code units** trong Java `String`, không phải số ký tự hiển thị. Một số ký tự ngoài BMP dùng hai code units; chuỗi có dấu kết hợp có thể gồm nhiều code points.

## 6. Hành vi lỗi và điểm cần tránh

| Tình huống | Hành vi / hướng xử lý |
| --- | --- |
| Gọi `group("x")` trước khi có kết quả khớp thành công | `IllegalStateException`; kiểm tra `find()` / `matches()` trước. |
| Truy cập một tên nhóm không có trong pattern | `IllegalArgumentException`; dùng chính xác tên đã khai báo. |
| Dùng tên sai quy tắc (ví dụ `user_id`, `tên`) hoặc trùng tên | `PatternSyntaxException` khi biên dịch; chọn tên ASCII hợp lệ và duy nhất. |
| Nhóm tùy chọn không tham gia | `group(name) == null`, `start(name) == -1`, `end(name) == -1`. |
| Nhóm tham gia nhưng khớp rỗng | `group(name).equals("")` và `start(name) == end(name)`. |
| Dùng `"\d"` trong Java | Sai cú pháp Java string; phải viết `"\\d"`. |
| Dùng `\k<name>` trong replacement hoặc `${name}` trong regex | Nhầm ngữ cảnh; phân biệt tham chiếu ngược và chèn nhóm khi thay thế. |
| Dùng `find()` để kiểm tra định dạng của toàn chuỗi | Có thể chấp nhận dữ liệu thừa; dùng `matches()` khi cần kiểm tra toàn bộ. |

Không sao chép máy móc cú pháp regex giữa các ngôn ngữ. Chẳng hạn Java dùng `(?<name>...)`, không dùng `(?P<name>...)` như Python.

Regex chỉ kiểm tra **mẫu văn bản**, không tự kiểm tra **ý nghĩa dữ liệu**. Mẫu ngày `(?<year>\d{4})-(?<month>\d{2})-(?<day>\d{2})` có thể khớp `2026-99-99` dù ngày không tồn tại. Khi cần ngày hợp lệ, dùng API `java.time`, ví dụ `LocalDate` / `DateTimeFormatter`, sau bước trích xuất.

## 7. Cách áp dụng an toàn, dễ bảo trì

- Đặt tên theo ý nghĩa dữ liệu (`userId`, `year`, `month`) để người đọc hiểu mục đích; dùng `(?:...)` cho các phần chỉ cần gom mà không cần kết quả.
- Biên dịch và tái sử dụng `Pattern` khi cùng regex được chạy nhiều lần. `Pattern` bất biến và có thể được chia sẻ; `Matcher` giữ trạng thái, do đó nên tạo mới cho mỗi lần xử lý hoặc luồng.
- Dùng `find()` cho bài toán trích các đoạn từ văn bản; dùng `matches()` khi toàn bộ chuỗi bắt buộc đúng cấu trúc.
- Nếu cần ghép dữ liệu đầu vào **nguyên văn** vào pattern, sử dụng `Pattern.quote(text)`. Với replacement nguyên văn, sử dụng `Matcher.quoteReplacement(text)`. Tránh regex quá phức tạp trên đầu vào không tin cậy vì rủi ro backtracking lớn.
- Kiểm thử các trường hợp: không khớp, khớp nhiều lần, nhóm tùy chọn thiếu, nhóm rỗng, tên nhóm sai, chuỗi có dấu Unicode, chuỗi có văn bản thừa ở hai đầu.

## 8. Bài tập tự kiểm tra

1. Với `(?<country>[A-Z]{2})-(?<number>\d{3})` và `VN-123`, xác định kết quả `group()`, `group("country")`, `group("number")`.
2. Với `"Mã: VN-123; mã: US-456"`, dùng `find()` và hai tên nhóm để đọc lần lượt từng mã.
3. Thêm nhóm `suffix` tùy chọn; tạo một đầu vào khiến nhóm không tham gia và một đầu vào khiến nhóm tham gia nhưng khớp rỗng. Phân biệt `null` với `""`.
4. Thêm một capturing group trước `country`, rồi so sánh độ ổn định của cách đọc `group(1)` với `group("country")`.
5. Dùng `(?<word>[\p{L}\p{M}]+)` trích một từ tiếng Việt có dấu; giải thích vì sao tên `word` hợp lệ nhưng tên `từ` không hợp lệ.

**Đáp án nhanh bài 1:** `group() = "VN-123"`, `group("country") = "VN"`, `group("number") = "123"`.

## 9. Tài liệu chính thức

- [Java SE 26: Pattern — nhóm bắt có tên, backreference, Unicode](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 25: Matcher — group(String), start(String), end(String), replaceAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html)

Các cú pháp, API và hướng dẫn trong bài hiện vẫn phù hợp với Java mới, không phụ thuộc vào cơ chế đã lỗi thời.
