# Kiểm thử `stripIndent()` và `translateEscapes()` với dữ liệu biên và dữ liệu sai (Java 15+)

Hai phương thức `String.stripIndent()` và `String.translateEscapes()` trở thành API chính thức từ Java 15 và tiếp tục được hỗ trợ trong JDK hiện đại. Chúng xử lý **chuỗi đã tồn tại lúc chạy**: một phương thức chuẩn hóa lề/đầu dòng, phương thức kia diễn giải các dấu gạch chéo ngược tạo thành escape sequence. Cả hai liên quan đến cách Java xử lý text block, nhưng khi kiểm thử dữ liệu từ file, HTTP, database hoặc cấu hình, phải xác định **giá trị thực tế của `String`**, không suy ra từ cách mã nguồn trông như thế nào.

Bài này tập trung vào kiểm thử giá trị đầu ra, dữ liệu biên, dữ liệu đầu vào không hợp lệ, kiểu ngoại lệ, tính ổn định trên các JDK được hỗ trợ và những lỗi thực tế dễ bị bỏ sót. Các ví dụ sử dụng Java 17+ để có thể biên dịch và chạy không cần thư viện ngoài.

## 1. Xác định chính xác hợp đồng của từng API

| Tiêu chí | `stripIndent()` | `translateEscapes()` |
| --- | --- | --- |
| Mục đích | Bỏ lề chung và khoảng trắng cuối dòng của một chuỗi nhiều dòng | Chuyển các escape sequence dạng văn bản như dấu `\` rồi `n` thành ký tự điều khiển/newline thực |
| Phạm vi tác động | Các dòng, khoảng trắng đầu/cuối dòng và ký tự xuống dòng | Các ký tự `\` cùng ký tự theo sau |
| Với chuỗi rỗng `""` | Trả về `""` | Trả về `""` |
| Với dữ liệu “không đẹp” nhưng vẫn là `String` hợp lệ | Thường **không ném ngoại lệ**; vẫn trả chuỗi có thể đã bị chuẩn hóa | Ném `IllegalArgumentException` nếu phát hiện escape sequence sai |
| Với biến nhận `null` | Gọi phương thức trực tiếp gây `NullPointerException` | Gọi phương thức trực tiếp gây `NullPointerException` |
| Điều không thực hiện | Không kiểm tra schema, không duy trì nguyên dạng CRLF, không mở rộng tab thành tab stop | Không phải JSON/XML/URL decoder, không diễn giải `\uXXXX`, không tự kiểm tra tính hợp lệ của nghiệp vụ |
| Kết quả | Một `String` mới về mặt giá trị; không thay đổi chuỗi gốc | Một `String` mới về mặt giá trị; không thay đổi chuỗi gốc |

**Phân biệt cách biểu diễn:** Trong mã Java, `"a\\nb"` chứa **dấu gạch chéo ngược và chữ n** ở giữa; `"a\nb"` chứa **ký tự LF** thực. Trong log hoặc test failure, nên hiển thị LF thành `\n`, CR thành `\r` và tab thành `\t` để người đọc thấy sự khác biệt.

### 1.1. Hợp đồng của `stripIndent()`

Theo Javadoc, thuật toán xử lý các dòng của chuỗi như sau:

1. Tách theo terminator `\n`, `\r` hoặc `\r\n`. Một dấu xuống dòng ở cuối vẫn tạo nên **dòng cuối rỗng** để xác định lề.
2. Đếm số ký tự khoảng trắng đầu dòng của **mọi dòng không trắng**, đồng thời đếm lề của **dòng cuối ngay cả khi dòng đó trắng**; lấy giá trị nhỏ nhất làm lề chung `min`.
3. Với mỗi dòng không trắng, bỏ `min` ký tự whitespace đầu dòng và **loại mọi whitespace cuối dòng**; với dòng trắng, thay nội dung bằng chuỗi rỗng.
4. Ghép lại bằng **LF (`\n`)**. Số lượng dấu kết thúc dòng được giữ lại, nhưng CR và CRLF được chuẩn hóa thành LF.

Whitespace ở đây theo `Character.isWhitespace` (cũng dùng để xác định `String.isBlank()`); không phải mọi ký tự trông như khoảng trắng đều thuộc nhóm này. Tab đếm như **một ký tự** lề; không được mở thành 4 hoặc 8 cột hiển thị.

**Bẫy nổi bật: dòng cuối rỗng làm lề chung bằng 0.** Xét hai chuỗi:

```java
String withoutFinalLf = "    a\n      b";
String withFinalLf    = "    a\n      b\n";

System.out.println(withoutFinalLf.stripIndent().equals("a\n  b")); // true
System.out.println(withFinalLf.stripIndent().equals(withFinalLf)); // true
```

Chuỗi có LF cuối cùng chứa dòng cuối rỗng, nên `min = 0`; hai dòng đầu **không bị dời lề**. Một dòng cuối chứa bốn dấu cách (không có LF thêm sau đó) tạo ra `min = 4` và sẽ bị xóa nội dung, nên kết quả khác:

```java
String input = "    a\n      b\n    ";
String expected = "a\n  b\n";
System.out.println(expected.equals(input.stripIndent())); // true
```

Không nên chỉ viết một testcase “nhiều dòng có lề” rồi mặc định trường hợp có newline ở cuối sẽ xử lý giống nhau.

### 1.2. Hợp đồng của `translateEscapes()`

Các escape sequence được hỗ trợ trong chuỗi đầu vào tại runtime:

| Escape trong dữ liệu | Kết quả | Trường hợp cần kiểm thử |
| --- | --- | --- |
| `\b`, `\f` | Backspace U+0008, form feed U+000C | Ký tự điều khiển có thể bị log che khuất |
| `\t` | Tab U+0009 | Phân biệt tab thật với hai ký tự `\` và `t` |
| `\n`, `\r` | LF U+000A, CR U+000D | Khác biệt hệ điều hành và xuống dòng |
| `\s` | Một dấu cách ASCII U+0020 | Giữ khoảng trắng mà dữ liệu muốn diễn đạt |
| `\"`, `\'`, `\\` | Dấu ngoặc kép, nháy đơn, dấu gạch chéo ngược | Dễ sai khi escape **hai lần** |
| `\0` tới `\377` | Ký tự biểu diễn bằng mã octal từ 1–3 chữ số, theo quy tắc Java | Giới hạn số chữ số được tiêu thụ |
| Dấu `\` ngay trước LF, CR hoặc CRLF thực | Cả dấu `\` lẫn dấu xuống dòng bị bỏ (continuation) | Không nhầm với ký tự `\` theo sau bằng hai chữ `r`, `n` |

Escape octal bắt đầu bằng `0` đến `7`. Nếu chữ số đầu là `0`–`3` thì có thể lấy thêm tối đa **hai** chữ số octal; nếu đầu là `4`–`7` thì chỉ lấy thêm tối đa **một** chữ số. Do đó `\377` tạo ký tự U+00FF, còn chuỗi `\400` tạo **dấu cách + chữ số 0**: `\40` là dấu cách, `0` còn lại là ký tự thông thường. Đây là test biên quan trọng, không được mặc định `\400` là một escape 3 chữ số không hợp lệ.

Các dạng `\q`, `\8`, `\x41`, dấu `\` đứng cuối chuỗi và `\u0041` (dạng escape Unicode được viết thành dữ liệu lúc chạy) **không thuộc grammar** của phương thức; chúng ném `IllegalArgumentException`. `\uXXXX` có ý nghĩa đặc biệt khi Java compiler đọc **mã nguồn**, chứ `translateEscapes()` không phải trình phân tích Unicode escapes trên dữ liệu runtime. JSON có bộ quy tắc riêng, cần dùng JSON parser nếu đầu vào là JSON.

## 2. Lập ma trận kiểm thử trước khi viết assertion

Các trường hợp sau giúp bao phủ hợp đồng của API thay vì chỉ kiểm tra happy path. Trong bảng, `\n`, `\r` và `\t` biểu diễn bằng ký hiệu để dễ đọc; ở `String` thực chúng là ký tự xuống dòng/tab nếu không được ghi chú là chuỗi escape thô.

| Nhóm | Đầu vào/đặc điểm | Kỳ vọng và nguyên nhân |
| --- | --- | --- |
| Rỗng | `""` | Hai phương thức trả `""`, không lỗi |
| Một dòng | `"   hello   "` + `stripIndent` | `"hello"`: bỏ lề và whitespace cuối |
| Hai dòng khác lề | `"    a\n      b"` | `"a\n  b"`: bỏ đúng lề chung 4 ký tự |
| Newline cuối | `"    a\n      b\n"` | Lề giữ nguyên vì dòng cuối rỗng; vẫn kết thúc LF |
| Dòng cuối chỉ có space | `"    a\n      b\n    "` | `"a\n  b\n"`: dòng trắng cuối vẫn tham gia tìm `min` |
| Dòng trắng ở giữa | `"  a\n   \n  b"` | `"a\n\nb"`: dòng trắng bị rỗng, không làm mất dòng |
| Toàn whitespace | `"   \n   "` | `"\n"`: còn dấu tách dòng |
| CRLF và CR | `" \ta\r\n \tb"` | `"a\nb"`: chuẩn hóa xuống LF |
| Tab + space lẫn nhau | `"\ta\n  b"` | `"a\n b"`: một tab đếm một ký tự |
| NBSP U+00A0 | NBSP + `"a\n"` + NBSP + `"b"` | NBSP không được coi là `Character.isWhitespace`, nên còn nguyên |
| Escape hợp lệ | Dữ liệu thô `a\nb` (chứa ký tự `\` + `n`) | Sau `translateEscapes` có LF thật giữa `a` và `b` |
| Escape khoảng trắng | Dữ liệu thô `a\sb` | Kết quả `"a b"` |
| Octal | `\101` / `\377` / `\400` | `"A"` / U+00FF / `" 0"` |
| Continuation | `\` + LF hoặc CRLF thực | Loại `\` và terminator, nối hai phần |
| Escape bị escape lần nữa | Dữ liệu thô `\\n` | Kết quả còn `\n` **dạng văn bản**, chưa thành LF |
| Escape sai | `\q`, `\8`, `\x41`, `\u0041`, dấu `\` cuối | `IllegalArgumentException` |
| Receiver không có giá trị | `String x = null; x.stripIndent();` | `NullPointerException` vì gọi instance method trên `null` |

Không nên đưa `null` vào cùng nhóm `IllegalArgumentException`: bản thân `String` không nhận tham số cho hai phương thức này; `null` là lỗi tham chiếu ở mã gọi, không phải lỗi dữ liệu escape đang được phân tích.

## 3. Chương trình kiểm thử độc lập: 32 trường hợp chạy được

Tạo file **`StringBoundaryChecks.java`** với nội dung sau. Không cần framework và không dựa vào trạng thái hệ điều hành. Mỗi assertion kiểm tra toàn bộ `String`, bao gồm whitespace và line terminator. Khi sai, chương trình ném `AssertionError` với tên testcase cùng giá trị có ký tự đặc biệt được biểu diễn rõ ràng.

```java
public class StringBoundaryChecks {
    private static int passed = 0;

    private static void eq(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected=[" + display(expected)
                    + "], actual=[" + display(actual) + "]");
        }
        passed++;
    }

    private static void rejects(String name, String raw) {
        try {
            raw.translateEscapes();
        } catch (IllegalArgumentException good) {
            passed++;
            return;
        }
        throw new AssertionError(name + ": accepted invalid escape");
    }

    private static String display(String s) {
        return s.replace("\\", "\\\\").replace("\r", "\\r")
                .replace("\n", "\\n").replace("\t", "\\t");
    }

    public static void main(String[] args) {
        // stripIndent(): ranh giới dòng và whitespace
        eq("s01 empty", "", "".stripIndent());
        eq("s02 one line", "hello", "   hello   ".stripIndent());
        eq("s03 common indent", "a\n  b", "    a\n      b".stripIndent());
        eq("s04 LF at end", "    a\n      b\n", "    a\n      b\n".stripIndent());
        eq("s05 last blank", "a\n  b\n", "    a\n      b\n    ".stripIndent());
        eq("s06 blank middle", "a\n\nb", "  a\n   \n  b".stripIndent());
        eq("s07 all blank", "\n", "   \n   ".stripIndent());
        eq("s08 CRLF", "a\nb", " \ta\r\n \tb".stripIndent());
        eq("s09 mixed tab", "a\n b", "\ta\n  b".stripIndent());
        eq("s10 trailing whitespace", "a\nb", "  a \t\n  b\t ".stripIndent());
        eq("s11 initial blank", "\na\n b", "\n  a\n   b".stripIndent());

        // NBSP U+00A0 nhìn giống khoảng trắng, nhưng không phải whitespace ở đây.
        String nbsp = Character.toString(0x00A0);
        eq("s12 NBSP", nbsp + "a\n" + nbsp + "b",
                (nbsp + "a\n" + nbsp + "b").stripIndent());

        // translateEscapes(): trường hợp hợp lệ
        eq("t01 empty", "", "".translateEscapes());
        eq("t02 plain", "abc", "abc".translateEscapes());
        eq("t03 newline", "a\nb", "a\\nb".translateEscapes());
        eq("t04 tab", "a\tb", "a\\tb".translateEscapes());
        eq("t05 space", "a b", "a\\sb".translateEscapes());
        eq("t06 quotes", "\"'\\", "\\\"\\'\\\\".translateEscapes());
        eq("t07 octal A", "A", "\\101".translateEscapes());
        eq("t08 octal space", " ", "\\040".translateEscapes());
        eq("t09 octal high", Character.toString(0xFF), "\\377".translateEscapes());
        eq("t10 octal bounded", " 0", "\\400".translateEscapes());
        eq("t11 LF continuation", "ab", "a\\\nb".translateEscapes());
        eq("t12 CRLF continuation", "ab", "a\\\r\nb".translateEscapes());
        eq("t13 escaped slash", "\\n", "\\\\n".translateEscapes());

        // translateEscapes(): dữ liệu sai phải bị từ chối
        rejects("bad01 unknown letter", "\\q");
        rejects("bad02 digit eight", "\\8");
        rejects("bad03 final slash", "\\");
        rejects("bad04 unicode notation", "\\" + "u0041");
        rejects("bad05 hex notation", "\\x41");

        // Thứ tự hai phép xử lý là một phần của yêu cầu nghiệp vụ.
        String raw = "    a\\s\n      b";
        eq("order: strip then translate", "a \n  b",
                raw.stripIndent().translateEscapes());
        eq("order: translate then strip", "a\n  b",
                raw.translateEscapes().stripIndent());

        System.out.println("PASS " + passed + " checks");
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac --release 17 StringBoundaryChecks.java
java StringBoundaryChecks
```

**Stdout khi toàn bộ testcase thành công:**

```text
PASS 32 checks
```

Đã kiểm tra kết quả trên JDK 24 (các phương thức này ổn định từ Java 15). Nếu một phép so sánh thất bại, chương trình ném `AssertionError` và tiến trình dừng, vì thế một pipeline CI nhận được exit code khác 0. `java` không bật assertions bằng `-ea` vẫn chạy đủ testcase, vì chương trình dùng phương thức `eq` của chính nó thay cho từ khóa Java `assert`.

**Đọc một số testcase đáng chú ý:**

- `s04` và `s05` cố ý có kỳ vọng khác nhau: với `s04`, dòng cuối trống không có lề (min bằng 0); với `s05`, dòng cuối chứa bốn dấu cách (min bằng 4).
- `s08` không kiểm tra riêng từng hệ điều hành: đây là API chuẩn hóa dữ liệu, vì vậy đầu vào CRLF phải cho kết quả LF dù chạy trên Windows hay Linux.
- `s09` kiểm tra tab chỉ bị xem là một ký tự whitespace. Không thể tính lề dựa vào số cột tab hiển thị trên màn hình.
- `s12` phân biệt NBSP U+00A0 với dấu cách ASCII. Test này dùng mã code point để không vô tình làm mất NBSP trong copy/paste.
- `t10` chốt quy tắc tối đa 2 chữ số octal khi chữ số đầu là 4–7; `\400` không phải trường hợp bị từ chối.
- `t13` phân biệt một chuỗi escape được bảo vệ bằng thêm dấu `\` với ký tự xuống dòng thực. Không nên mặc định việc gọi `translateEscapes()` hai lần tương đương một lần.
- `bad04` tạo chuỗi `\` + `u0041` tại runtime bằng phép cộng chuỗi; không để Java compiler xử lý nhầm Unicode escape ở bước đọc source.
- Hai test `order` chứng minh **thứ tự xử lý ảnh hưởng kết quả**: xử lý escape `\s` sau `stripIndent` giữ dấu cách do escape sinh ra, còn dịch escape trước thì dấu cách cuối dòng bị `stripIndent` xóa.

## 4. Dùng JUnit Jupiter trong dự án có sẵn test runner

Chương trình trên là tài liệu thực thi độc lập. Trong dự án đang dùng JUnit Jupiter, nên tách testcase thành các phương thức có tên mô tả rõ, dùng `assertEquals` cho dữ liệu biên và `assertThrows` cho escape sai. Ví dụ dưới đây **phụ thuộc JUnit Jupiter trong project**; không phải file `java` tự chạy như chương trình ở mục 3.

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class StringMethodsTest {
    @Test
    void trailingLfParticipatesInIndentCalculation() {
        String source = "    a\n      b\n";
        assertEquals(source, source.stripIndent());
    }

    @Test
    void finalBlankLineWithSpacesChangesCommonIndent() {
        String source = "    a\n      b\n    ";
        assertEquals("a\n  b\n", source.stripIndent());
    }

    @Test
    void crlfIsNormalizedByStripIndent() {
        assertEquals("a\nb", " \ta\r\n \tb".stripIndent());
    }

    @Test
    void validEscapesBecomeActualCharacters() {
        assertEquals("a\nb", "a\\nb".translateEscapes());
        assertEquals(" 0", "\\400".translateEscapes());
    }

    @Test
    void invalidEscapesFailWithDocumentedException() {
        assertThrows(IllegalArgumentException.class,
                () -> "\\q".translateEscapes());
        assertThrows(IllegalArgumentException.class,
                () -> ("\\" + "u0041").translateEscapes());
        assertThrows(IllegalArgumentException.class,
                () -> "\\".translateEscapes());
    }
}
```

Nếu muốn bảng kiểm thử lớn hơn, sử dụng `@ParameterizedTest` cùng `@MethodSource` để mỗi cặp `input/expected` trở thành một case độc lập; trường hợp hợp lệ và trường hợp `assertThrows` nên nằm ở các bảng riêng. Chạy bằng test task của hệ thống build hiện tại; cấu hình dependency JUnit Jupiter và engine theo quy chuẩn của dự án thay vì sao chép một phiên bản thư viện không liên quan.

Trong CI, nên giữ các test này ở JDK thấp nhất đang cam kết hỗ trợ (ví dụ 17 khi yêu cầu runtime là 17+) và thêm một bản JDK mục tiêu triển khai. Tránh viết expected bằng chính phương thức đang kiểm thử, ví dụ `assertEquals(s.stripIndent(), s.stripIndent())`: test này không xác minh hợp đồng.

## 5. Dữ liệu “sai” của `stripIndent()` phải định nghĩa ở tầng nghiệp vụ

`stripIndent()` không nhận grammar và không có cách biết một nội dung bị coi là lỗi theo quy tắc ứng dụng. Các đầu vào như toàn tab, các dòng lề không nhất quán, dòng rỗng, ký tự điều khiển hoặc NBSP vẫn là `String` hợp lệ. Đầu ra có thể đúng hợp đồng API nhưng **không hợp lệ đối với giao thức của hệ thống**.

Ví dụ một ứng dụng chỉ cho phép hai dòng văn bản không trống, không chứa dấu CR sau khi chuẩn hóa:

```java
import java.util.List;

final class InputRules {
    static List<String> normalizeTwoLines(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Input must not be null");
        }
        if (raw.length() > 1_000) {
            throw new IllegalArgumentException("Input too long");
        }

        String normalized = raw.stripIndent();
        List<String> lines = normalized.lines().toList();
        if (lines.size() != 2 || lines.stream().anyMatch(String::isBlank)) {
            throw new IllegalArgumentException("Expected exactly two nonblank lines");
        }
        return lines;
    }
}
```

Đoạn mã này minh họa một **quy tắc nghiệp vụ tùy chọn**, không phải hành vi mặc định của `stripIndent()`; nó không có phương thức `main` riêng. `lines()` tách theo LF, CR và CRLF và không trả dòng trống ở sau một terminator cuối, nên nếu nghiệp vụ cần giữ/kiểm tra riêng dấu kết thúc cuối tệp thì phải kiểm tra `normalized.endsWith("\n")` hoặc giữ metadata ban đầu trước khi gọi `lines()`. Giới hạn 1.000 ký tự chỉ là ví dụ về giới hạn do ứng dụng tự đặt, không phải giới hạn API.

Với dữ liệu độc hại hoặc không đáng tin cậy, hãy xác định trước chính sách: có cho phép tab, NBSP, ký tự điều khiển, nhiều dòng trống, độ dài cực lớn hay không; cách báo lỗi nên mô tả ràng buộc dữ liệu, tránh chỉ ghi “stripIndent failed” khi không có ngoại lệ nào.

## 6. Quan hệ với text block và thứ tự biến đổi

Text block trong Java 15+ xử lý ba bước ngữ nghĩa theo thứ tự: **chuẩn hóa terminator → loại bỏ incidental whitespace → diễn giải escape sequence**. Chúng là các bước compiler xử lý nội dung text block trong mã nguồn. `stripIndent()` và `translateEscapes()` cho phép áp dụng những biến đổi tương ứng **lúc chạy** lên một chuỗi đến từ nguồn ngoài.

Không đánh đồng hai nguồn sau:

```java
String literal = "a\nb";     // LF thật đã có từ khi compiler xử lý literal.
String external = "a\\nb";   // Backslash thật + chữ n.
String decoded = external.translateEscapes();

System.out.println(literal.equals(decoded));  // true
```

Với text block đã được compiler xử lý, gọi `stripIndent()` hoặc `translateEscapes()` **thêm lần nữa** có thể biến đổi ngoài ý muốn. Đặc biệt, nếu dữ liệu runtime chứa `\\n` (hai dấu gạch chéo rồi chữ n), lần gọi đầu có thể đưa về `\n` dạng escape thô, lần gọi tiếp mới thành LF; đây là lý do nên gắn bước decode vào một biên giới xử lý rõ ràng và có test xác nhận chỉ xử lý một lần.

Khi thiết kế pipeline cho văn bản thô, hai chuỗi sau không tương đương:

```java
String raw = "    a\\s\n      b";
String first = raw.stripIndent().translateEscapes();
String second = raw.translateEscapes().stripIndent();

System.out.println(first.equals("a \n  b"));   // true
System.out.println(second.equals("a\n  b"));   // true
```

Nếu phần hậu xử lý muốn giữ dấu cách có ý nghĩa trong dữ liệu đã escape, thường phải loại lề **trước** rồi mới dịch escape. Tuy nhiên, thứ tự cuối cùng là quyết định của giao thức dữ liệu và phải có testcase làm rõ.

## 7. Kiểm thử biên trong hệ thống thực tế

### 7.1. Test contract thay cho nhìn bằng mắt

Dùng `assertEquals(expected, actual)` hoặc so sánh theo code point khi cần; không dùng `System.out.println` để quyết định chuỗi đúng vì console dễ che NBSP, tab và trailing whitespace. Với lỗi ngoại lệ, xác minh **loại ngoại lệ**; hạn chế so khớp nguyên văn exception message vì thông báo có thể thay đổi giữa các bản JDK.

Ví dụ đếm LF sau `stripIndent()` mà không dựa vào dấu xuống dòng hệ điều hành:

```java
String value = "  a\r\n  b\r  c".stripIndent();
long lfCount = value.chars().filter(ch -> ch == '\n').count();

System.out.println(value.equals("a\nb\nc")); // true
System.out.println(lfCount);                  // 2
```

### 7.2. Bổ sung dữ liệu sinh và bất biến

Khi đã có bộ test cụ thể, có thể thêm property-based/fuzz testing để bắt lỗi mà bảng thủ công bỏ sót. Sinh tổ hợp giới hạn của: số dòng, số dấu cách/tab, CR/LF/CRLF, dòng rỗng, Unicode whitespace, dấu `\` ở đầu/cuối, octal 0–7 và ký tự escape không được hỗ trợ. Nên đặt giới hạn độ dài và số lần thử để test CI tái lập được với seed cố định.

Các bất biến hữu ích cho `stripIndent()`:

- Mọi CR và CRLF dùng làm terminator trong chuỗi đầu vào được biểu diễn bằng LF trong đầu ra.
- Ký tự whitespace cuối mỗi dòng không trắng bị bỏ; dòng trắng trở thành nội dung rỗng.
- Số line terminator trong đầu ra bằng số line terminator trong đầu vào (trong đó CRLF tính là **một** terminator).
- Khi cùng thêm một mức indentation nhất quán cho mọi dòng không trắng **và không tạo dòng cuối rỗng không lề**, relative indentation sau xử lý phải không đổi; nếu có dòng cuối trắng, phải xét riêng theo hợp đồng ở mục 1.

Với `translateEscapes()`, **không** viết bất biến `decode(decode(s)) == decode(s)`: nó không được bảo đảm, như testcase `t13` đã cho thấy. Có thể thử một tập chuỗi không chứa dấu `\`, khi đó kết quả phải giữ nguyên; tập malformed escape đã biết phải gây `IllegalArgumentException`.

### 7.3. Chọn dữ liệu an toàn để báo lỗi

Một chuỗi đầu vào có thể chứa ký tự điều khiển, newline hoặc dữ liệu cá nhân. Khi báo test failure, dùng trình hiển thị `display` như ví dụ; với dữ liệu sản xuất không nên log toàn bộ payload không tin cậy. Nên log mã lỗi, loại ngoại lệ, chiều dài và vị trí gây lỗi nếu bộ parser ứng dụng xác định được. `translateEscapes()` có thể sinh ký tự LF/CR/control, vì vậy hãy kiểm tra quy tắc của giao thức đầu ra **sau khi giải mã**, không chỉ kiểm tra dữ liệu trước giải mã.

## 8. Các lỗi thường gặp và cách tránh

| Lỗi kiểm thử/triển khai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Chỉ test một dòng hoặc không test LF cuối | Dòng cuối trắng ảnh hưởng đến `min` | Thêm case có LF cuối, dòng cuối chứa space và không có LF |
| So sánh chuỗi sau khi `trim()` trong test | Làm biến mất chính dấu cách/newline cần kiểm tra | So sánh nguyên chuỗi và hiển thị ký tự không nhìn thấy khi fail |
| Kỳ vọng CRLF được giữ nguyên | `stripIndent()` chuẩn hóa terminator thành LF | Viết expected với LF; chỉ chuyển sang CRLF khi giao thức đầu ra cần |
| Xem tab có độ rộng 4/8 cột | `stripIndent()` đếm từng ký tự whitespace | Kiểm thử riêng tab và space |
| Coi NBSP giống space thường | U+00A0 không được xem là whitespace theo `Character.isWhitespace` | Dùng fixture code point rõ ràng |
| Gọi `translateEscapes()` để giải mã JSON | JSON có `\uXXXX` và escape grammar khác | Dùng JSON parser cho JSON |
| Coi `\400` là một escape octal sai | Grammar chỉ tiêu thụ `\40` rồi giữ chữ `0` | Đặt expected là `" 0"` |
| Chỉ test dữ liệu hợp lệ | Bỏ sót đường ném `IllegalArgumentException` | Thêm invalid `\q`, `\8`, `\u0041`, dấu `\` cuối |
| Gọi bộ giải mã nhiều lần | Dữ liệu chứa dấu `\` có thể đổi ý nghĩa ở lần sau | Xác định một điểm decode duy nhất trong pipeline |
| Cho rằng `stripIndent()` kiểm tra dữ liệu không hợp lệ | Nó chuẩn hóa `String`, không kiểm tra quy tắc ứng dụng | Thêm validator độc lập trước/sau biến đổi |
| Copy chuỗi có escape vào test nhưng Java compiler xử lý từ mã nguồn | Test đang kiểm tra `String` khác dữ liệu thật | Xây dựng input raw có chủ đích, dùng `"\\n"` để nhận dấu `\` + `n` |

## 9. Checklist khi hoàn thiện test suite

1. Có giá trị **thực tế** của input `String`, phân biệt rõ escape trong mã nguồn và escape trong dữ liệu.
2. Có test rỗng, một dòng, nhiều dòng, whitespace thuần, LF cuối, dòng cuối trắng, CRLF/CR, tab và Unicode whitespace.
3. Có expected chính xác từng ký tự, bao gồm số dấu LF và dấu cách cuối dòng.
4. Có escape hợp lệ, octal ở ranh giới số chữ số, dấu `\` được escape lần nữa và line continuation.
5. Có test `IllegalArgumentException` cho escape sai, tách riêng `null`/`NullPointerException`.
6. Có test **thứ tự gọi** `stripIndent()` và `translateEscapes()` nếu pipeline dùng cả hai.
7. Có test validation nghiệp vụ riêng; không dựa vào hai phương thức `String` để tự phát hiện dữ liệu rác.
8. Chạy trên JDK tối thiểu mà dự án hỗ trợ và môi trường triển khai, với stdout/exception không phụ thuộc hệ điều hành.

## Nguồn tham khảo hiện hành

- [Javadoc `String.stripIndent()` và `String.translateEscapes()` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): hợp đồng chính thức, whitespace, grammar và ngoại lệ. 
- [Javadoc `String` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): chi tiết thuật toán `stripIndent` và danh sách escape hợp lệ.
- [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): liên hệ giữa text block và các phép xử lý ở runtime.
- [Java Language Specification, `3.10.7 Escape Sequences`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7): quy tắc escape ở mức ngôn ngữ.
