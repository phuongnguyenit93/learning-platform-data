# String.matches(): kiểm tra toàn bộ chuỗi bằng biểu thức chính quy

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao `String.matches(regex)` chỉ trả về `true` khi **toàn bộ** giá trị `String` khớp với regex; viết regex trong chuỗi ký tự Java đúng cách; phân biệt kiểm tra toàn chuỗi với tìm đoạn khớp; và chọn `String.matches` hay `Pattern`/`Matcher` cho từng tình huống.

## 1. Nguyên lý: khớp toàn bộ, không tìm chuỗi con

Phương thức có chữ ký:

~~~java
public boolean matches(String regex)
~~~

`regex` là biểu thức chính quy (regular expression); kết quả là `boolean`. `text.matches(regex)` có cùng kết quả với `Pattern.matches(regex, text)` của `java.util.regex.Pattern`.

Điều kiện thành công là **regex phải bao phủ toàn bộ chuỗi đầu vào**, từ ký tự đầu đến ký tự cuối. Ví dụ:

| Chuỗi | Regex Java | Kết quả | Lý do |
| --- | --- | --- | --- |
| `"abc123"` | `"[a-z]+\\d+"` | `true` | Chữ thường theo sau bởi một hoặc nhiều chữ số, không thừa ký tự |
| `"abc123!"` | `"[a-z]+\\d+"` | `false` | Dấu `!` không thuộc mẫu |
| `"12345"` | `"\\d+"` | `true` | Cả chuỗi là chữ số |
| `"ID-42"` | `"\\d+"` | `false` | Có tiền tố `ID-` |
| `"abcXYZdef"` | `"XYZ"` | `false` | `XYZ` chỉ xuất hiện ở giữa |
| `"abcXYZdef"` | `".*XYZ.*"` | `true` | Phần trước và sau `XYZ` được regex cho phép |

Có thể hình dung `matches` kiểm tra **cả chuỗi có đúng dạng này không?**, còn `Matcher.find()` kiểm tra **có chỗ nào trong chuỗi khớp không?**. Không cần thêm `^` và `$` chỉ để buộc `String.matches` khớp toàn bộ: chính API đã yêu cầu điều đó. Tuy nhiên `^`/`$` là các anchor có ngữ nghĩa riêng trong regex (đặc biệt khi dùng cờ nhiều dòng), nên không nên xem việc thêm anchor là phép biến đổi luôn tương đương trong mọi trường hợp.

## 2. Ví dụ Java 17+ chạy độc lập

Lưu vào `StringMatchesDemo.java`:

~~~java
public class StringMatchesDemo {
    public static void main(String[] args) {
        System.out.println("abc123".matches("[a-z]+\\d+"));
        System.out.println("abc123!".matches("[a-z]+\\d+"));
        System.out.println("123".matches("\\d+"));
        System.out.println("ID-42".matches("ID-\\d{2}"));
        System.out.println("42".matches("\\d"));
        System.out.println("42".matches("\\d+"));

        System.out.println("".matches("a*"));
        System.out.println("".matches("a+"));

        System.out.println("abcXYZdef".matches("XYZ"));
        System.out.println("abcXYZdef".matches(".*XYZ.*"));

        System.out.println("a\nb".matches("a.b"));
        System.out.println("a\nb".matches("(?s)a.b"));
    }
}
~~~

Chạy bằng terminal tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 StringMatchesDemo.java
java StringMatchesDemo
~~~

Kết quả chuẩn (theo đúng thứ tự các lệnh `println`):

~~~text
true
false
true
true
false
true
true
false
false
true
false
true
~~~

Giải thích các trường hợp dễ nhầm:

- `"42".matches("\\d")` trả về `false` vì `\d` khớp **một** chữ số, trong khi chuỗi có hai; `\d+` cho phép một hoặc nhiều chữ số.
- `"".matches("a*")` là `true` vì dấu `*` cho phép **0 lần** xuất hiện; `a+` yêu cầu ít nhất một `a`.
- `"abcXYZdef".matches("XYZ")` là `false` vì phần `abc` và `def` chưa được mẫu bao phủ.
- Theo mặc định dấu chấm `.` không khớp ký tự xuống dòng trong ví dụ; `(?s)` bật chế độ DOTALL, nên `"a\nb"` khớp `(?s)a.b`.

## 3. Hai tầng cú pháp: Java String và regex

Regex được truyền dưới dạng **chuỗi Java**, nên dấu gạch chéo ngược `\` phải qua hai tầng diễn giải: Java xử lý chuỗi trước, sau đó bộ máy regex mới đọc mẫu. Chẳng hạn để regex nhìn thấy `\d+`, mã nguồn Java phải viết `"\\d+"`.

| Muốn kiểm tra | Mẫu regex có ý nghĩa | Viết trong mã Java |
| --- | --- | --- |
| Một hoặc nhiều chữ số | `\d+` | `"\\d+"` |
| Chính xác ba chữ số | `\d{3}` | `"\\d{3}"` |
| Một dấu chấm thật | `\.` | `"\\."` |
| Một khoảng trắng regex | `\s` | `"\\s"` |
| Mã gồm 2 chữ in hoa, dấu gạch ngang và 3 số | `[A-Z]{2}-\d{3}` | `"[A-Z]{2}-\\d{3}"` |

Một số thành phần thường dùng:

- `[abc]`: một ký tự thuộc tập `a`, `b`, `c`; `[A-Z]`: một chữ cái Latin in hoa trong khoảng chỉ định.
- `\d`, `\w`, `\s`: lớp ký tự dựng sẵn; ngữ nghĩa Unicode có thể chịu tác động của cờ regex.
- `?`: 0 hoặc 1 lần; `*`: 0 hoặc nhiều lần; `+`: 1 hoặc nhiều lần; `{n}`: đúng n lần; `{m,n}`: từ m đến n lần.
- `(...)`: nhóm; `|`: lựa chọn; `.`: ký tự bất kỳ trừ một số dấu kết thúc dòng nếu chưa bật DOTALL.
- `[0-9]` kiểm tra chữ số ASCII rõ ràng; `\d` mặc định dùng lớp chữ số regex của Java và có thể mở rộng khi bật `UNICODE_CHARACTER_CLASS`/`(?U)`.

Ví dụ, `"v1x2".matches("v1.2")` là `true` vì dấu `.` đại diện cho một ký tự bất kỳ (ở đây `x`). Muốn so sánh với dấu chấm thật, dùng `"v1\\.2"`. Nếu chuỗi cần so khớp đến từ người dùng và phải được hiểu theo nghĩa **nguyên văn**, dùng `Pattern.quote(text)` thay vì đưa thẳng vào regex.

## 4. So sánh matches, find, lookingAt và contains

`String.matches` và `Matcher.matches()` đều yêu cầu khớp toàn bộ chuỗi (hoặc toàn bộ *region* được cấu hình trong `Matcher`). `Matcher.lookingAt()` kiểm tra tiền tố, còn `Matcher.find()` quét tìm một đoạn khớp. `String.contains` chỉ tìm đoạn ký tự **nguyên văn**, không hiểu cú pháp regex.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatchVsFindDemo {
    public static void main(String[] args) {
        String text = "Order 42";
        Pattern digits = Pattern.compile("\\d+");

        System.out.println(digits.matcher(text).matches());
        System.out.println(digits.matcher(text).lookingAt());

        Matcher matcher = digits.matcher(text);
        System.out.println(matcher.find());
        System.out.println(matcher.group());

        System.out.println(text.contains("42"));
        System.out.println(text.matches(".*\\d+"));
    }
}
~~~

Lưu là `MatchVsFindDemo.java`, biên dịch bằng `javac -encoding UTF-8 MatchVsFindDemo.java` và chạy `java MatchVsFindDemo`. Kết quả:

~~~text
false
false
true
42
true
true
~~~

`matches()` thất bại vì `"Order "` còn dư; `lookingAt()` thất bại vì đầu chuỗi không phải chữ số; `find()` tìm được `42` và `group()` trả về đoạn đã khớp. Ví dụ tạo `Matcher` riêng cho từng kiểu kiểm tra để không phụ thuộc trạng thái của những lần match trước.

| Nhu cầu | API phù hợp |
| --- | --- |
| Kiểm tra toàn bộ giá trị có đúng định dạng regex | `value.matches(regex)` hoặc `pattern.matcher(value).matches()` |
| Tìm một đoạn phù hợp regex trong văn bản | `pattern.matcher(value).find()` |
| Kiểm tra phần đầu chuỗi theo regex | `pattern.matcher(value).lookingAt()` |
| Tìm sự hiện diện của đoạn ký tự cố định | `value.contains(literal)` |
| So sánh toàn bộ chuỗi với một giá trị cố định | `value.equals(literal)` |

## 5. Áp dụng: xác thực định dạng dữ liệu

Giả sử một mã có dạng **hai chữ cái ASCII in hoa, một dấu `-`, chính xác ba chữ số ASCII**. Regex phù hợp là `[A-Z]{2}-[0-9]{3}`. Dùng `matches` để ngăn phần dư ở đầu/cuối vô tình được chấp nhận.

~~~java
import java.util.regex.Pattern;

public class CodeValidationDemo {
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}-[0-9]{3}");

    public static boolean isValidCode(String value) {
        return value != null && CODE.matcher(value).matches();
    }

    public static void main(String[] args) {
        String[] candidates = {"AB-123", "AB-1234", "ab-123", " AB-123", "XY-000"};
        for (String candidate : candidates) {
            System.out.println(candidate + " -> " + isValidCode(candidate));
        }
        System.out.println("null -> " + isValidCode(null));
    }
}
~~~

Lưu là `CodeValidationDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 CodeValidationDemo.java
java CodeValidationDemo
~~~

Kết quả:

~~~text
AB-123 -> true
AB-1234 -> false
ab-123 -> false
 AB-123 -> false
XY-000 -> true
null -> false
~~~

Ở ví dụ này `Pattern.compile(...)` được gọi một lần rồi dùng lại: hợp lý khi kiểm tra cùng một regex nhiều lần. `String.matches(regex)` tiện cho kiểm tra ngắn, ít lần; mỗi lời gọi thực hiện thao tác tương đương `Pattern.matches(regex, value)`, nên tránh biên dịch lại biểu thức không cần thiết trong vòng lặp lớn.

Đây là **kiểm tra hình thức**, chưa khẳng định một mã có tồn tại trong hệ thống. Tương tự, một regex cho email hoặc URL hiếm khi thay thế được mọi quy tắc nghiệp vụ hay bước xác thực thực tế.

## 6. Lỗi thường gặp và cách xử lý

**1. Nhầm khớp toàn chuỗi với tìm chuỗi con.** Nếu muốn tìm số trong `"Order 42"`, dùng `find()`. Nếu phải xác thực định dạng gồm cả tiền tố và số, viết mẫu phủ cả hai, ví dụ `"Order \\d+"`.

**2. Quên escape dấu gạch chéo trong Java.** Mã `"\\d+"` tạo regex `\d+`. Viết `"\d+"` trực tiếp trong chuỗi Java là lỗi biên dịch (*illegal escape character*). Muốn dấu chấm thật phải viết `"\\."`, không phải `"."`.

**3. Tưởng `.` khớp mọi thứ kể cả newline.** Mặc định dấu chấm không khớp dấu kết thúc dòng. Dùng `(?s)` khi chủ đích muốn chế độ DOTALL; hoặc chọn tập ký tự chặt chẽ hơn nếu đang xác thực dữ liệu.

**4. Bỏ qua ký tự trắng ở đầu/cuối.** `" AB-123 "` không khớp `[A-Z]{2}-[0-9]{3}`. Chỉ gọi `strip()` trước `matches` nếu quy tắc nhập liệu cho phép bỏ khoảng trắng; nếu khoảng trắng là dữ liệu không hợp lệ, phải giữ nguyên để từ chối.

**5. Không xét `null` hoặc regex sai.** Gọi `matches` trên biến `String` đang `null` gây `NullPointerException`. Regex sai cú pháp như `"[abc"` gây `PatternSyntaxException`. Nếu regex lấy từ bên ngoài, cần xử lý lỗi cú pháp và giới hạn độ phức tạp trước khi chạy.

**6. Chấp nhận input theo regex quá rộng.** Mẫu `".*"` khớp cả chuỗi rỗng; `".+"` không khớp chuỗi rỗng, nhưng vẫn quá rộng cho mã định danh. Viết lớp ký tự và độ dài thật sự cần (ví dụ `[A-Z]{2}-[0-9]{3}`).

**7. Xem regex như bộ xác thực mọi ngôn ngữ/ký tự.** `[A-Z]` chỉ nói tới các chữ từ A đến Z; `(?i)` có thể bật so khớp không phân biệt hoa thường theo quy tắc regex, nhưng yêu cầu Unicode/ngôn ngữ khác có thể cần cách xây dựng lớp ký tự và cờ phù hợp. Không giả định một mẫu ASCII bao phủ tiếng Việt hay toàn bộ Unicode.

**8. Đưa regex không tin cậy vào xử lý dữ liệu dài.** Một số biểu thức có nhánh lặp lồng nhau gây thời gian chạy rất lớn (*catastrophic backtracking*) khi gặp chuỗi gần khớp. Ưu tiên regex đơn giản, có giới hạn; cân nhắc giới hạn đầu vào, hiệu năng và giải pháp parser chuyên biệt nếu cần.

## 7. Tự kiểm tra

Không cần chạy code, hãy dự đoán:

1. `"A12".matches("[A-Z]\\d{2}")`
2. `"A123".matches("[A-Z]\\d{2}")`
3. `"".matches("\\d*")`
4. `"x42y".matches("\\d+")`
5. `"x42y".matches(".*\\d+.*")`

**Đáp án:** (1) `true`; (2) `false` vì thừa một chữ số; (3) `true` vì `*` cho phép 0 lần; (4) `false` vì có `x` và `y`; (5) `true` vì `.*` ở hai phía bao phủ ký tự không phải chữ số.

Khi tự thiết kế mẫu để xác thực, luôn thử ít nhất bốn nhóm giá trị: **hợp lệ**, **thừa tiền tố/hậu tố**, **thiếu hoặc sai ký tự**, **rỗng/null**. Đây là cách nhanh để bắt lỗi nhầm lẫn giữa kiểm tra toàn bộ và tìm một phần của chuỗi.

## Tham khảo chính thức

- [Java SE 17 — String.matches(String regex)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#matches(java.lang.String))
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 17 — Matcher: matches(), lookingAt(), find()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
