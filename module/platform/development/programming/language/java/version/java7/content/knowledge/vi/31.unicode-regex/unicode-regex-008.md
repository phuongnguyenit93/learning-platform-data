# Kiểm thử đầu vào đa ngôn ngữ và mẫu regex không hợp lệ trong Java

**Chủ đề:** Regex Unicode · **Bài học:** Kiểm thử đầu vào đa ngôn ngữ và mẫu không hợp lệ. Các ví dụ dùng Java 17+ và các API hiện hành của `java.util.regex`, `java.text.Normalizer` và `java.lang.String`.

Một hệ thống nhận dữ liệu bằng nhiều ngôn ngữ có thể gặp hai loại lỗi **khác nhau**:

1. **Đầu vào không thỏa chính sách**: regex biên dịch hợp lệ, nhưng nội dung chứa ký tự, độ dài, khoảng trắng hoặc tổ hợp Unicode không được chấp nhận. Khi đó `Matcher.matches()` trả `false`.
2. **Biểu thức regex bị sai cú pháp**: `Pattern.compile(regex)` ném `PatternSyntaxException` **trước khi** kiểm tra dữ liệu. Một biểu thức hợp lệ về cú pháp vẫn có thể sai yêu cầu nghiệp vụ hoặc chạy quá chậm.

Muốn kiểm thử đúng, phải xây dựng hai bộ ca riêng: **ca dữ liệu** và **ca biên dịch mẫu**, rồi bổ sung kiểm thử hiệu năng và an toàn với dữ liệu không tin cậy.

## 1. Định nghĩa chính sách đầu vào trước khi viết test

Không có một regex “hỗ trợ mọi ngôn ngữ” phù hợp với mọi trường. Với từng trường dữ liệu, cần xác định:

| Quyết định | Câu hỏi phải trả lời |
|---|---|
| Phạm vi ký tự | Chấp nhận mọi chữ thuộc Unicode (`\p{L}`) hay chỉ một tập script được phép? Có cho dấu kết hợp (`\p{M}`), chữ số (`\p{Nd}`), dấu câu, emoji? |
| Chuẩn hóa | So sánh theo NFC hay giữ nguyên từng mã Unicode? Có được phép biến đổi đầu vào trước khi lưu/tìm kiếm? |
| Khoảng trắng | Chỉ cho U+0020, hay chấp nhận thêm tab, xuống dòng, NBSP? Cho một hay nhiều khoảng trắng? |
| Độ dài | Giới hạn theo UTF-16 code unit, Unicode code point, hay grapheme cluster hiển thị? |
| Khớp toàn bộ | Cần kiểm tra **toàn chuỗi** hay chỉ tìm một đoạn trong văn bản? |
| Chữ hoa/thường | Có so khớp không phân biệt hoa/thường không? Quy tắc ngôn ngữ/locale có quan trọng không? |
| Lỗi và tài nguyên | Khi regex do người dùng/cấu hình đưa vào bị sai thì trả lỗi gì? Có giới hạn kích thước đầu vào và thời gian xử lý không? |

**Chính sách minh họa cho phần thực hành:** một *tên hiển thị đơn giản* gồm 1–40 Unicode code point sau chuẩn hóa NFC; mỗi từ bắt đầu bằng chữ Unicode, sau đó là chữ hoặc dấu kết hợp; các từ phân tách bằng đúng một dấu cách ASCII; không chấp nhận chữ số, emoji, ký tự điều khiển, dấu câu hoặc khoảng trắng ở hai đầu. Đây là chính sách **cụ thể để kiểm thử**, không phải tiêu chuẩn tên người toàn cầu. Tên thực tế có thể cần dấu gạch nối, dấu nháy, ký tự nối đặc thù từng script và quy tắc sản phẩm riêng.

Regex cho chính sách đó:

```regex
\p{L}[\p{L}\p{M}]*(?: \p{L}[\p{L}\p{M}]*)*
```

Trong Java string literal, phải viết dấu gạch chéo ngược thành `\\`, ví dụ `"\\p{L}"`. `\p{L}` nhận chữ thuộc các hệ chữ Unicode, `\p{M}` nhận dấu kết hợp; dấu cách trong mẫu ở trên là **U+0020 đúng một lần**, không phải `\s`. Lớp ký tự Unicode chỉ mô tả cấu trúc, **không bảo đảm** chính tả hay tính hợp lệ của mọi tên trong mọi ngôn ngữ.

## 2. Những đặc điểm Unicode phải đưa vào bộ kiểm thử

### 2.1. NFC, NFD và dấu kết hợp

Hai chuỗi trông giống nhau có thể dùng mã khác nhau: `"Hà"` chứa ký tự `à` dựng sẵn (NFC), còn `"Ha\u0300"` có `a` rồi dấu huyền kết hợp U+0300 (NFD). So sánh chuỗi trực tiếp hoặc regex trên chuỗi chưa chuẩn hóa có thể cho kết quả khác mong đợi. Khi hợp đồng dữ liệu cho phép, chuẩn hóa đầu vào với `Normalizer.normalize(input, Normalizer.Form.NFC)` **trước** khi kiểm thử regex, so sánh, lập chỉ mục hoặc lưu trữ; áp dụng nhất quán ở các bước.

NFC bảo toàn tương đương chuẩn tắc; **NFKC có thể gộp các ký tự tương thích** và làm thay đổi ý nghĩa nhận diện, nên không tự chuyển sang NFKC. Không tự chuẩn hóa mật khẩu, chữ ký, token, mã định danh không cho phép biến đổi hoặc dữ liệu đã có hợp đồng so sánh byte riêng.

### 2.2. Unicode class, chữ số và cờ regex

- `\p{L}` là category chữ; `\p{M}` là các dấu kết hợp; `\p{Nd}` là chữ số thập phân Unicode. Các lớp này rõ ý định hơn `[A-Za-z]` khi dữ liệu đa ngôn ngữ.
- Theo cấu hình mặc định của Java `Pattern`, các lớp viết tắt như `\d`, `\w` và `\s` có phạm vi ASCII. `Pattern.UNICODE_CHARACTER_CLASS` (hoặc `(?U)`) làm chúng dùng quy tắc Unicode; vì vậy phải kiểm thử **cả có và không có cờ**. Ví dụ `[0-9]+` chỉ nhận số ASCII, `\p{Nd}+` nhận cả chữ số Arabic-Indic `١٢٣`.
- `Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE` hỗ trợ đối chiếu hoa/thường theo Unicode. Điều đó **không thay thế** quy tắc biến đổi chữ theo locale, so sánh ngôn ngữ tự nhiên, hoặc chuẩn hóa Unicode.
- `Pattern.CANON_EQ` có hỗ trợ tương đương chuẩn tắc nhưng có chi phí; với bài toán có hợp đồng NFC, thường rõ ràng hơn khi chuẩn hóa đầu vào một lần và kiểm thử dữ liệu sau chuẩn hóa.
- Với kiểm tra toàn bộ dữ liệu, dùng `matcher.matches()`; `find()` chỉ cần tìm **một đoạn** trùng. Ví dụ `find()` có thể thấy `Alice` trong `Alice🙂`, dù toàn chuỗi không hợp lệ.

### 2.3. UTF-16, code point và grapheme cluster

`String.length()` trả số **UTF-16 code unit**, không phải số “ký tự nhìn thấy”. `codePointCount(0, s.length())` đếm Unicode code point. Ví dụ chuỗi emoji `👩‍💻` gồm **5** UTF-16 code unit, **3** code point (người phụ nữ + zero-width joiner + laptop), nhưng thường hiển thị như **một** grapheme cluster. Java `Pattern` hỗ trợ `\X` để khớp một Unicode extended grapheme cluster.

Khi thiết kế giới hạn, chọn đơn vị theo nhu cầu: giới hạn xử lý/bộ nhớ theo byte hoặc code unit, giới hạn dữ liệu logic theo code point, độ dài mà người dùng nhìn thấy theo grapheme. Không tự cắt chuỗi bằng `substring` tại vị trí UTF-16 tùy ý vì có thể tách surrogate pair; khi cần, sử dụng API code point và kiểm thử ký tự nằm ngoài BMP.

### 2.4. Script trộn và ký tự vô hình

`\p{L}` có thể nhận cả chữ Latin “a” lẫn chữ Cyrillic “а” (hai code point khác nhau nhưng nhìn tương tự). **NFC không phát hiện confusable/homograph**. Với username, domain label hoặc định danh nhạy cảm, cần chính sách script, cơ chế phát hiện confusable theo Unicode UTS #39 và kiểm thử riêng; không tùy tiện cấm trộn script đối với tên người dùng thật. Kiểm thử cả `U+200D` (zero-width joiner), `U+202E` (bidi override), `U+00A0` (non-breaking space), ký tự điều khiển và newline theo chính sách trường dữ liệu.

## 3. Ma trận kiểm thử đầu vào: dương, âm và biên

Các kỳ vọng trong bảng **chỉ áp dụng cho chính sách tên minh họa ở mục 1**. Trong test, hiển thị hoặc tạo chính xác các code point; hai chuỗi nhìn giống nhau có thể khác nhau về mã.

| Nhóm | Đầu vào | Kỳ vọng | Điều cần xác nhận |
|---|---|---|---|
| Cơ bản | `Alice`, `A` | Hợp lệ | Một từ, biên dưới độ dài |
| Tiếng Việt NFC | `Đặng Thị Hà` | Hợp lệ | Chữ có dấu dựng sẵn |
| Tiếng Việt NFD | `Ha` + U+0300 | Hợp lệ sau NFC | Dấu huyền tách rời vẫn tương đương chuẩn tắc |
| Cyrillic | `Мария` | Hợp lệ | Không giới hạn ASCII |
| Arabic | `فاطمة` | Hợp lệ | Script khác Latin |
| Han | `李雷` | Hợp lệ | Chữ Hán không có dấu cách |
| Devanagari | `हिन्दी` | Hợp lệ | Dấu kết hợp trong chữ |
| Trống hoặc null | `""`, `null` | Không hợp lệ | Không ném lỗi ngoài ý muốn |
| Dấu đứng đầu | U+0301 + `A` | Không hợp lệ | Dấu kết hợp không được đứng đầu từ |
| Khoảng trắng | `An  Bình`, ` Alice` | Không hợp lệ | Không tự trim nếu hợp đồng yêu cầu nguyên trạng |
| Ký tự cấm | `A9`, `A🙂` | Không hợp lệ | Chính sách không nhận số, emoji |
| Ký tự vô hình | `A` + U+200D + `B`; `A` + U+202E + `B` | Không hợp lệ | ZWJ, bidi control |
| Xuống dòng | `A\nB` | Không hợp lệ | Không nhầm `find()` với `matches()` |
| Quá dài | 41 lần `A` | Không hợp lệ | Biên trên theo code point |

Ngoài bảng, nên kiểm tra: chuỗi **đúng 40 code point**, một code point ngoài BMP, dấu kết hợp lặp bất thường, `\r\n`/`\u2028`, NBSP, surrogate lẻ trong Java string, biến thể emoji ZWJ, script trộn và dữ liệu được decode từ UTF-8. **Byte UTF-8 sai định dạng là lỗi ở bước giải mã**, không phải lỗi cú pháp regex; cấu hình decoder nghiêm ngặt nếu cần từ chối dữ liệu hỏng.

## 4. Kiểm thử regex không hợp lệ và mẫu động

Sai cú pháp phải được phát hiện ngay khi gọi `Pattern.compile(...)`. Ví dụ chắc chắn lỗi:

| Biểu thức | Loại lỗi |
|---|---|
| `[` | Character class không đóng |
| `(` | Nhóm không đóng |
| `*abc` | Toán tử lặp thiếu biểu thức đứng trước |
| `\p{NoSuchProperty}` | Tên thuộc tính Unicode không được hỗ trợ |

Bắt **đúng** `PatternSyntaxException`; các thông tin `getPattern()`, `getDescription()` và `getIndex()` hữu ích cho chẩn đoán. `getIndex()` có thể là `-1` nếu không xác định vị trí. Không kiểm tra cứng nội dung `getMessage()` hay vị trí chính xác của mọi lỗi vì thông điệp/chi tiết có thể khác theo JDK. `Pattern.compile(null)` là lỗi đối số null (không cùng loại với regex sai cú pháp).

Có hai trường hợp dữ liệu bên ngoài:

1. **Văn bản do người dùng nhập để tìm kiếm theo nghĩa đen:** dùng `Pattern.quote(userText)`, tránh việc `.`, `+`, `[` hoặc `(?i)` biến thành cú pháp regex. Nếu văn bản được chèn vào chuỗi thay thế của `replaceAll`, dùng `Matcher.quoteReplacement(replacementText)` để `$` và `\` được giữ nguyên.
2. **Regex có chủ đích do người quản trị/cấu hình cung cấp:** xác thực và biên dịch trước khi áp dụng; giới hạn độ dài, các đặc tính cho phép và mức tài nguyên. Regex **biên dịch thành công vẫn có thể nguy hiểm**: mẫu có lặp lồng nhau trên đầu vào đối kháng có thể gây backtracking rất lớn. Không thử tải đối kháng không giới hạn trên luồng xử lý sản xuất; đặt ngân sách thực thi/cô lập thích hợp, dùng mẫu tuyến tính hoặc parser cụ thể nếu bài toán phù hợp hơn. `Matcher` không cung cấp API timeout tích hợp.

## 5. Chương trình Java 17+ chạy độc lập: 34 kiểm tra

Tạo tệp UTF-8 `UnicodeRegexInputTest.java`. Chương trình dùng kiểm tra assertion chủ động (không phụ thuộc cờ `-ea`), nên chạy được bằng JDK mà không cần thư viện test bên ngoài. `Pattern` được tái sử dụng; mỗi lần kiểm tra tạo một `Matcher` mới.

```java
import java.text.Normalizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

public class UnicodeRegexInputTest {
    private static final Pattern NAME = Pattern.compile(
        "\\p{L}[\\p{L}\\p{M}]*(?: \\p{L}[\\p{L}\\p{M}]*)*"
    );
    private static int checks = 0;

    private static boolean validName(String raw) {
        if (raw == null) return false;
        String s = Normalizer.normalize(raw, Normalizer.Form.NFC);
        int length = s.codePointCount(0, s.length());
        return length >= 1 && length <= 40 && NAME.matcher(s).matches();
    }

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
        checks++;
    }

    private static void name(String label, String input, boolean expected) {
        check(validName(input) == expected, "name: " + label);
    }

    private static void malformed(String regex) {
        try {
            Pattern.compile(regex);
            throw new AssertionError("Expected PatternSyntaxException: " + regex);
        } catch (PatternSyntaxException ex) {
            check(regex.equals(ex.getPattern()), "error pattern differs");
        }
    }

    public static void main(String[] args) {
        name("ASCII", "Alice", true);
        name("Vietnamese", "Đặng Thị Hà", true);
        name("NFD Vietnamese", "Ha\u0300", true);
        name("Cyrillic", "Мария", true);
        name("Arabic", "فاطمة", true);
        name("Han", "李雷", true);
        name("Devanagari", "हिन्दी", true);
        name("one letter", "A", true);
        name("empty", "", false);
        name("null", null, false);
        name("leading mark", "\u0301A", false);
        name("double space", "An  Bình", false);
        name("digit", "A9", false);
        name("emoji", "A🙂", false);
        name("join control", "A\u200DB", false);
        name("line break", "A\nB", false);
        name("bidi control", "A\u202EB", false);
        name("over 40 code points", "A".repeat(41), false);

        check(Normalizer.normalize("Ha\u0300", Normalizer.Form.NFC).equals("Hà"),
              "NFC canonical equivalence");

        malformed("[");
        malformed("(");
        malformed("*abc");
        malformed("\\p{NoSuchProperty}");

        Pattern literal = Pattern.compile(Pattern.quote("a+b"));
        check(literal.matcher("a+b").matches(), "literal regex metacharacters");
        check(!literal.matcher("aaab").matches(), "literal pattern must not be regex");
        String replaced = Pattern.compile("x").matcher("x")
            .replaceAll(Matcher.quoteReplacement("$1\\"));
        check(replaced.equals("$1\\"), "literal replacement text");

        check(Pattern.compile("\\p{Nd}+").matcher("١٢٣").matches(),
              "Unicode decimal digits");
        check(!Pattern.compile("[0-9]+").matcher("١٢٣").matches(),
              "ASCII-only digits");
        check(!Pattern.compile("\\d+").matcher("١٢٣").matches(),
              "default shorthand d is ASCII");
        check(Pattern.compile("\\d+", Pattern.UNICODE_CHARACTER_CLASS)
              .matcher("١٢٣").matches(), "Unicode d with UCC");
        check(Pattern.compile("école",
              Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE)
              .matcher("ÉCOLE").matches(), "Unicode case folding");

        String emoji = "👩‍💻";
        check(emoji.length() == 5, "UTF-16 length");
        check(emoji.codePointCount(0, emoji.length()) == 3, "code points");
        check(Pattern.compile("\\X").matcher(emoji).matches(),
              "extended grapheme cluster");

        System.out.println("PASS: " + checks + " checks");
    }
}
```

Biên dịch và chạy (với JDK 17 trở lên):

```bash
javac --release 17 -encoding UTF-8 UnicodeRegexInputTest.java
java UnicodeRegexInputTest
```

Kết quả chuẩn khi mọi kiểm tra đều đạt:

```text
PASS: 34 checks
```

Nếu có sai lệch, chương trình ném `AssertionError` với nhãn ca thất bại. Ví dụ này **chủ động** chỉ nhận tên không có dấu nháy/gạch nối, giới hạn 40 code point và không làm phép phân tích chính tả đa ngôn ngữ. Khi thay chính sách, cập nhật đồng thời matcher **và** các kỳ vọng trong bộ test.

## 6. Quy trình kiểm thử thực tế trong dự án

1. **Lập bảng hợp đồng dữ liệu** cho từng trường: mã Unicode được phép, normalization, chiều dài, dấu cách, quy tắc locale, mức nhạy cảm bảo mật; tách trường tên người, tên tài khoản và mã định danh.
2. **Xây corpus nhiều script**: dữ liệu NFC/NFD, chữ có dấu, chữ không dùng Latin, chữ số nhiều hệ, emoji, dấu kết hợp, ký tự vô hình, newline và dữ liệu rỗng. Ghi rõ kỳ vọng; tránh chỉ dùng ví dụ ASCII.
3. **Kiểm tra các biên**: 0, 1, max, max+1 code point; cùng một từ ở NFC/NFD; ký tự ngoài BMP; khoảng trắng đầu/cuối; dãy dấu kết hợp. Với regex tìm kiếm, kiểm cả `matches()`/`find()` theo đúng nghiệp vụ.
4. **Kiểm thử lỗi compile** độc lập với lỗi dữ liệu. Duy trì danh sách biểu thức lỗi và bảo đảm hệ thống báo lỗi cấu hình ở vị trí phù hợp mà không làm sập luồng xử lý.
5. **Kiểm thử literal injection** bằng dữ liệu chứa `[](){}.*+?$^\`. Dùng `Pattern.quote` / `Matcher.quoteReplacement` khi người dùng cung cấp **văn bản** thay vì biểu thức.
6. **Kiểm thử tài nguyên với giới hạn rõ ràng**: đặt trần kích thước chuỗi/regex, kiểm thử timeout trong môi trường cô lập có thể dừng tiến trình, tránh tạo mẫu backtracking nặng trong test thông thường. Không dùng kết quả biên dịch thành công làm bằng chứng an toàn.
7. **Tích hợp CI và tái kiểm sau nâng JDK**: khóa bộ fixture gồm chính các code point (`U+...`), dùng test tham số hoặc test sinh dữ liệu có seed cố định, kiểm lại những phân loại có thể thay đổi theo phiên bản bảng Unicode của JDK.

Đối với đầu vào dạng byte, cần test riêng lớp decoding (UTF-8 không hợp lệ, byte cắt giữa ký tự); đối với kho dữ liệu cần test cả chuẩn hóa trước lưu và truy vấn lại. Regex **không** thay thế kiểm tra ngữ nghĩa như email, số điện thoại quốc gia, tên miền quốc tế hay định danh bảo mật.

## 7. Các lỗi phổ biến cần phát hiện trong review

- Viết `[A-Za-z]+` hoặc mặc định `\w+` rồi kết luận mọi tiếng Việt, Arabic, Devanagari đều hợp lệ.
- Chỉ test chữ dựng sẵn mà bỏ chuỗi NFD; hoặc dùng NFKC mà không có yêu cầu thay đổi tương đương tương thích.
- Lấy `String.length()` làm số ký tự người dùng nhìn thấy, cắt giữa surrogate pair, hoặc giả định `\X` và một code point luôn tương đương.
- Dùng `find()` để kiểm tra dữ liệu phải khớp toàn bộ; sử dụng `\d` mà không xác định ASCII hay Unicode.
- Chỉ test regex cú pháp sai mà không test regex đúng cú pháp nhưng sai phạm vi hoặc có chi phí không kiểm soát.
- Ghép văn bản do người dùng nhập trực tiếp vào pattern hoặc replacement; xem mọi `PatternSyntaxException` như lỗi của dữ liệu đầu vào.
- Áp quy tắc một script hoặc cấm mọi ký tự nối cho **tất cả** tên người, dù dữ liệu quốc tế của sản phẩm cần các hệ chữ phức tạp.
- Viết assertion dựa vào nguyên văn `PatternSyntaxException.getMessage()`, khiến test phụ thuộc chi tiết hiển thị thay vì hành vi.

## 8. Checklist hoàn thành bài

- [ ] Có ca dương và âm cho ít nhất tiếng Việt (NFC/NFD), chữ Latin mở rộng, Cyrillic, Arabic/Han và một hệ chữ dùng dấu kết hợp.
- [ ] Có ca biên về độ dài code point, ký tự ngoài BMP, tổ hợp emoji, khoảng trắng và ký tự vô hình.
- [ ] Có kiểm tra khác biệt `matches()`/`find()`, `\d` ASCII/Unicode, cờ so khớp chữ hoa/thường và quá trình normalization.
- [ ] Có kiểm tra độc lập cho regex compile lỗi và xử lý `PatternSyntaxException`.
- [ ] Dữ liệu literal được escape đúng; regex động có chính sách tài nguyên và phạm vi rõ ràng.
- [ ] Ví dụ biên dịch với JDK mục tiêu, stdout khớp và CI theo dõi thay đổi phiên bản Unicode/JDK.

**Tài liệu API và Unicode hiện hành:** [Java Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java PatternSyntaxException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/PatternSyntaxException.html), [Java Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html), [Unicode UAX #15 — Normalization](https://www.unicode.org/reports/tr15/), [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/), [Unicode UTS #39 — Security Mechanisms](https://www.unicode.org/reports/tr39/).