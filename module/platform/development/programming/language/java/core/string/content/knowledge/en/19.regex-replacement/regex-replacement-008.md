# Kiểm thử dữ liệu chứa ký tự có ý nghĩa đặc biệt khi thay thế bằng regex trong Java

## 1. Vì sao cần kiểm thử riêng?

`String.replaceAll(String regex, String replacement)` và `String.replaceFirst(String regex, String replacement)` sử dụng **hai ngôn ngữ cú pháp khác nhau**:

- **Regex tìm kiếm**: dấu chấm, dấu sao, dấu cộng, dấu hỏi, ngoặc, dấu gạch đứng, dấu mũ, dấu dollar và backslash đều có thể mang ý nghĩa đặc biệt.
- **Chuỗi replacement**: `$1` hoặc nhóm bắt có tên có thể được thay bằng nội dung nhóm đã khớp; dấu backslash có vai trò escape ký tự tiếp theo.

Bên ngoài hai cú pháp đó còn có **cú pháp Java string literal**: dấu backslash phải được escape một lần nữa trong mã Java. Vì vậy, dữ liệu chứa `.`, `[`, `|`, `$` và `\` dễ làm một phép thay thế trả kết quả sai hoặc ném ngoại lệ.

Ví dụ, `"a.b".replaceAll(".", "_")` trả về `"___"` chứ không phải `"a_b"`. Regex `.` là wildcard khớp các ký tự `a`, `.` và `b`. Ở phía replacement, truyền thẳng `"$1"` khi không có nhóm bắt thứ nhất có thể ném `IndexOutOfBoundsException`; một dấu `"$"` đứng riêng trong replacement có thể ném `IllegalArgumentException`.

**Mục tiêu kiểm thử:** chứng minh rằng dữ liệu tìm kiếm được xem đúng là regex hay văn bản nguyên văn theo yêu cầu, replacement giữ đúng từng ký tự, các trường hợp biên hoạt động rõ ràng, và lỗi cú pháp được phát hiện.

## 2. Phân biệt các API

| Nhu cầu | Cách dùng | Vì sao |
| --- | --- | --- |
| Thay thế hai chuỗi **nguyên văn** | `text.replace(target, replacement)` | `String.replace(CharSequence, CharSequence)` không diễn giải hai đối số theo regex hoặc tham chiếu nhóm. |
| Thay nguyên văn nhưng cần gọi `replaceAll` | `text.replaceAll(Pattern.quote(target), Matcher.quoteReplacement(replacement))` | Quote riêng cho cú pháp regex tìm kiếm và cú pháp replacement. |
| Chủ động thay theo regex và dùng nhóm bắt | `text.replaceAll("(\\d+)", "[$1]")` | Giữ regex và `$1` đúng mục đích. |
| Chỉ thay lần khớp đầu | `replaceFirst(regex, replacement)` | Vẫn phải áp dụng đúng hai quy tắc escape như `replaceAll`. |

**`Pattern.quote(String s)`** biến chuỗi tìm kiếm thành biểu thức khớp **nguyên văn**. Nó hoạt động với metacharacter như `.`, `*`, `[`, `\` và cả các chuỗi chứa tổ hợp `\E`. Nó không xử lý replacement.

**`Matcher.quoteReplacement(String s)`** biến chuỗi thay thế thành **văn bản nguyên văn** khi truyền cho `replaceAll`/`replaceFirst`. Nó giữ ký tự `$` và `\`, không biến `$1` thành group reference. Nó không xử lý regex.

Hai chức năng **không thay thế được cho nhau**. Nếu cả hai đối số là dữ liệu văn bản thuần túy, `String.replace` thường là API đơn giản nhất.

Ví dụ ngắn (các lệnh đặt bên trong phương thức Java):

~~~java
String text = "a.b";
System.out.println(text.replaceAll(".", "_"));          // ___
System.out.println(text.replaceAll("\\.", "_"));        // a_b
System.out.println(text.replace(".", "$1\\backup"));    // a$1\backup
~~~

Lệnh đầu dùng wildcard; lệnh thứ hai escape đúng regex dấu chấm; lệnh thứ ba thay văn bản nguyên văn, nên `$1` và backslash không bị diễn giải theo cú pháp replacement.

## 3. Hàm thay thế nguyên văn an toàn

Nếu API của hệ thống yêu cầu dùng `replaceAll`, có thể bọc quy tắc escape:

~~~java
static String replaceLiteral(String text, String target, String replacement) {
    if (target.isEmpty()) {
        throw new IllegalArgumentException("target must not be empty");
    }
    return text.replaceAll(
            java.util.regex.Pattern.quote(target),
            java.util.regex.Matcher.quoteReplacement(replacement));
}
~~~

Đây là **mảnh phương thức minh họa**, được tích hợp đầy đủ trong chương trình phía dưới.

Hàm chủ động **từ chối target rỗng**. Vì regex rỗng có thể khớp các vị trí độ rộng 0, việc thay toàn bộ có thể chèn replacement vào nhiều ranh giới; điều này thường không phải yêu cầu “tìm và thay một từ khóa”. Nếu ứng dụng muốn cho phép target rỗng, hãy quy định hành vi cụ thể và viết thêm test cho trường hợp đó.

Không nên chỉ escape thủ công một hoặc hai ký tự: danh sách metacharacter regex rộng và cách parse replacement lại khác hẳn. Với dữ liệu thuần, hãy dùng API quote của thư viện chuẩn.

## 4. Bộ kiểm thử Java 17+ chạy độc lập

Ví dụ sau kiểm tra cả ký tự đặc biệt ở **target**, ở **replacement**, hành vi khi không khớp, Unicode, newline và những ngoại lệ cần xuất hiện. Không cần thư viện bên ngoài hay JUnit. Mỗi trường hợp so sánh chính xác chuỗi đầu ra bằng `equals`.

Tạo tệp **RegexSpecialCharacterTest.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

public class RegexSpecialCharacterTest {
    private static int passed = 0;

    static String replaceLiteral(String text, String target, String replacement) {
        if (target.isEmpty()) {
            throw new IllegalArgumentException("target must not be empty");
        }
        return text.replaceAll(
                Pattern.quote(target),
                Matcher.quoteReplacement(replacement));
    }

    private static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected <" + expected + "> but got <" + actual + ">");
        }
        passed++;
    }

    private static void expectThrows(
            String name, Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (type.isInstance(ex)) {
                passed++;
                return;
            }
            throw new AssertionError(name + ": unexpected exception " + ex, ex);
        }
        throw new AssertionError(name + ": expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        // Special characters in regex search patterns.
        check("regex dot wildcard", "___", "a.b".replaceAll(".", "_"));
        check("literal dot", "a_b", replaceLiteral("a.b", ".", "_"));
        check("literal star", "aXb", replaceLiteral("a*b", "*", "X"));
        check("literal pipe", "a/b/c", replaceLiteral("a|b|c", "|", "/"));
        check("literal brackets", "X X",
                replaceLiteral("[tag] [tag]", "[tag]", "X"));
        check("literal backslash search", "C:/temp/v1",
                replaceLiteral("C:\\temp\\v1", "\\", "/"));
        check("literal dollar search", "price USD",
                replaceLiteral("price $5", "$5", "USD"));

        // Literal dollar and backslash in replacement text.
        check("replacement dollar one", "x$1y",
                replaceLiteral("x.y", ".", "$1"));
        check("replacement backslash", "x\\tmpy",
                replaceLiteral("x.y", ".", "\\tmp"));
        check("replacement both", "$1\\new",
                replaceLiteral("$5", "$5", "$1\\new"));

        // Use a capturing group deliberately.
        check("intentional capture", "x=[42]",
                "x=42".replaceAll("(\\d+)", "[$1]"));
        check("replaceFirst quotes replacement", "a$1a.a",
                "a.a.a".replaceFirst(
                        Pattern.quote("."), Matcher.quoteReplacement("$1")));

        // Boundaries: no match, adjacent matches, Unicode, and newlines.
        check("no match", "abc", replaceLiteral("abc", "XYZ", "$\\"));
        check("adjacent delimiters", "$\\$\\$\\$\\",
                replaceLiteral("....", ".", "$\\"));
        check("Unicode and emoji", "[X]\uD83D\uDE42[X]",
                replaceLiteral(
                        "\u0111\u00E1\uD83D\uDE42\u0111\u00E1",
                        "\u0111\u00E1", "[X]"));
        check("line break as data", "a\\nb",
                replaceLiteral("a\nb", "\n", "\\n"));
        check("empty input", "", replaceLiteral("", ".", "_"));

        // Invalid input must fail in a controlled, testable way.
        expectThrows("empty target", IllegalArgumentException.class,
                () -> replaceLiteral("abc", "", "x"));
        expectThrows("invalid regex [", PatternSyntaxException.class,
                () -> "abc".replaceAll("[", "x"));
        expectThrows("bare dollar replacement", IllegalArgumentException.class,
                () -> "a.b".replaceAll("\\.", "$"));

        System.out.println("PASS: " + passed + " checks");
    }
}
~~~

Biên dịch, rồi chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RegexSpecialCharacterTest.java
java RegexSpecialCharacterTest
~~~

Stdout khi toàn bộ kiểm thử thành công:

~~~text
PASS: 20 checks
~~~

Nếu kỳ vọng khác kết quả thực tế, chương trình ném `AssertionError` và sẽ **không in thông báo PASS**. Cách này đáng tin cậy hơn việc chỉ nhìn `System.out.println` để đoán các token rỗng hay dấu backslash. `expectThrows` còn kiểm tra đúng loại ngoại lệ thay vì coi mọi ngoại lệ đều là thành công. Không dùng Java `assert` ở đây vì câu lệnh `assert` có thể bị bỏ qua nếu JVM chạy thiếu cờ `-ea`.

Các trường hợp bao quát nhiều hơn phép thay một dấu chấm: mã còn thử dấu `|`, dấu ngoặc vuông, backslash trong từ khóa tìm kiếm, `$5` trong từ khóa, `$1` và `\` trong replacement, thay một lần bằng `replaceFirst`, nhóm bắt thật `$1`, nhiều dấu liên tiếp, dữ liệu Unicode/emoji, xuống dòng thật, chuỗi đầu vào rỗng và các đầu vào sai cú pháp.

## 5. Ma trận kiểm thử với dữ liệu thực

| Nhóm | Tình huống cần thử | Kỳ vọng quan trọng |
| --- | --- | --- |
| Regex metacharacters | Các ký tự `.`, `*`, `+`, `?`, `|`, `[`, `]`, `(`, `)`, `^`, `$` | Khi mục tiêu là tìm nguyên văn, ký tự không biến thành wildcard, quantifier, character class, nhóm hoặc anchor. |
| Backslash trong target | Tìm `\` trong một đường dẫn | Regex khớp đúng một dấu backslash và không lỗi cú pháp. |
| Dollar trong target | Tìm chuỗi `$5` | Dollar là dữ liệu nguyên văn, không thành anchor cuối chuỗi. |
| Dollar trong replacement | Thay thành `$1`, `$5` hoặc chỉ `$` | Dollar không bị xử lý thành nhóm bắt nếu ứng dụng không yêu cầu. |
| Backslash trong replacement | Thay thành chuỗi chứa `\tmp` hoặc `\` | Backslash vẫn tồn tại chính xác trong kết quả. |
| Nhiều khớp liên tiếp | Thay từng dấu chấm trong `....` | Mỗi vị trí khớp được xử lý đúng một lần; không thiếu hoặc nhân đôi. |
| Không có khớp | Input `abc`, target `XYZ` | Trả về nguyên chuỗi ban đầu. |
| Unicode và emoji | Ký tự tiếng Việt có dấu và emoji | Không mất dấu hay làm hỏng cặp surrogate. |
| Xuống dòng | Thay newline thật bằng hai ký tự `\` và `n` | Phân biệt newline thật với văn bản biểu diễn newline. |
| Biên | Input rỗng, target rỗng, dữ liệu lặp | Có kết quả rõ ràng hoặc ngoại lệ được quy định. |
| Cú pháp hỏng | Regex `[` hoặc replacement `$` chưa quote | Test xác nhận đúng loại lỗi, không nuốt exception. |

Khi có yêu cầu mới, mở rộng ma trận: chỉ thay lần đầu, thay không phân biệt chữ hoa/thường, nhóm bắt có tên, ký tự xuống dòng Windows CRLF, chuỗi rất dài hoặc target thuộc nhiều bảng mã. Các lựa chọn đó cần được kiểm thử theo hợp đồng thực tế của ứng dụng.

## 6. Ba lớp escape thường bị nhầm

### Lớp 1: Java string literal

Để có một dấu backslash thật ở runtime, mã Java viết `"\\"`. Newline thật viết `"\n"`. Để có hai ký tự **backslash rồi chữ n**, mã Java viết `"\\n"`.

### Lớp 2: Regex tìm kiếm

Regex dấu chấm nguyên văn cần `\.`, tức Java string literal `"\\."`. Regex khớp một backslash thật cần hai backslash trong regex, tức bốn backslash trong Java string literal `"\\\\"`. Với target từ người dùng, `Pattern.quote` giúp khỏi phải tự tính các lớp escape đó.

### Lớp 3: Cú pháp replacement

`$1` là tham chiếu tới nhóm bắt số 1 nếu chủ động dùng cú pháp này. Dấu `\` trong replacement có thể được parser dùng để escape ký tự tiếp theo. Bởi vậy, replacement từ dữ liệu như `"$1\\new"` cần `Matcher.quoteReplacement` nếu phải giữ nguyên mọi ký tự. **Quote regex không đồng thời quote replacement.**

Khi debug, so sánh toàn chuỗi bằng `equals`. Nếu cần phân tích sâu, có thể in `length` và từng code point; nhìn văn bản log đôi khi không phân biệt được một dấu backslash bị nuốt hoặc một newline thực.

## 7. Các lỗi phổ biến

1. **Chỉ quote target:** `Pattern.quote` xử lý regex nhưng replacement chứa `$` hoặc `\` vẫn có thể bị diễn giải hay gây lỗi.
2. **Chỉ quote replacement:** regex chứa `.` hoặc `|` vẫn có thể khớp vị trí khác dự kiến.
3. **Quote biểu thức khi thực sự muốn regex:** `Pattern.quote("(\\d+)")` tìm đúng các ký tự của biểu thức, chứ không tìm chữ số. Cần thống nhất target là **regex có chủ ý** hay **văn bản nguyên văn**.
4. **Dùng `replaceAll` cho thay thế hoàn toàn nguyên văn:** cân nhắc `String.replace`, vừa rõ ý định vừa tránh lỗi cú pháp.
5. **Catch mọi exception rồi đánh dấu test PASS:** `PatternSyntaxException` báo regex sai; replacement sai cũng có thể gây `IllegalArgumentException` hoặc `IndexOutOfBoundsException`. Phải kiểm tra đúng ngoại lệ mong đợi.
6. **Chỉ thử dữ liệu ASCII đơn giản:** chưa bao phủ newline, Unicode, backslash hoặc dấu dollar; cần kiểm thử với dữ liệu thực tế.
7. **Nhận regex tùy ý từ người dùng mà không giới hạn:** nếu tính năng cho phép regex tự do, cần thông báo lỗi cú pháp và kiểm soát tài nguyên do một số regex có thể chạy rất lâu. Nếu chỉ cần tìm văn bản thuần, quote target.

## 8. Quy trình áp dụng

Khi xây tính năng tìm và thay thế trong một trình soạn thảo hay công cụ xử lý chuỗi:

1. Xác định target là **regex** hay **dữ liệu nguyên văn**, và replacement là **template nhóm bắt** hay **dữ liệu nguyên văn**.
2. Chọn API thích hợp: `String.replace` cho nguyên văn; `Pattern.quote` kết hợp `Matcher.quoteReplacement` nếu cần `replaceAll` với dữ liệu nguyên văn; regex thực khi cần nhóm bắt.
3. Xây bộ test bao gồm metacharacters ở cả hai phía, nhiều lần khớp, không khớp, lỗi cú pháp, chuỗi rỗng, Unicode và newline.
4. Kiểm tra **nội dung chính xác** và **ngoại lệ chính xác**, thay vì chỉ xác nhận chương trình không bị crash.

**Ghi nhớ:** ký tự đặc biệt chỉ có ý nghĩa trong **ngữ cảnh cú pháp cụ thể**. `.` quan trọng với regex tìm kiếm, `$1` quan trọng với replacement, còn `\` phải đi qua lớp escape của Java. Kiểm thử tốt phải chứng minh cả ba lớp được xử lý đúng, đồng thời giữ nguyên dữ liệu người dùng muốn thay thế.
