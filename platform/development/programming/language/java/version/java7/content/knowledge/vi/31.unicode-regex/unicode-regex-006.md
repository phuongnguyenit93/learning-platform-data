# Phân biệt xử lý chữ hoa, chữ thường với chuẩn hóa văn bản Unicode trong Java Regex

Khi so khớp văn bản Unicode, **không phân biệt chữ hoa/chữ thường** và **chuẩn hóa Unicode** giải quyết hai vấn đề khác nhau. Regex có thể bỏ qua sự khác biệt hoa/thường nhưng vẫn không khớp hai chuỗi nhìn giống hệt nhau nếu chúng được mã hóa Unicode khác cách. Nội dung áp dụng với Java hiện đại (Java 17+), chỉ dùng các API JDK hiện được hỗ trợ.

## 1. Ba loại “giống nhau” cần phân biệt

| Nhu cầu | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Bỏ qua chữ hoa/chữ thường | `Java` và `JAVA`; `CAFÉ` và `café` | Dùng chính sách đổi case rõ ràng hoặc kết hợp hai cờ regex `CASE_INSENSITIVE` và `UNICODE_CASE` |
| Coi các biểu diễn Unicode chính tắc là một | `é` (U+00E9) và `e` + dấu sắc U+0301 | Dùng `Normalizer.normalize(..., Normalizer.Form.NFC)` ở **cả hai phía** |
| Tìm kiếm không phân biệt dấu | `má` và `ma` | Xây dựng chính sách tìm kiếm bỏ dấu riêng; **không** phải tác dụng của NFC hay cờ case |

Ví dụ:

- `"CAF\u00C9"` và `"caf\u00E9"` khác hoa/thường nhưng cùng dạng Unicode NFC.
- `"caf\u00E9"` và `"cafe\u0301"` có cùng cách hiển thị “café” nhưng khác dãy mã Unicode; đổi sang chữ thường **không tự ghép** dấu kết hợp.
- `"café"` và `"cafe"` khác dấu, nên NFC, NFD và regex không phân biệt hoa/thường **không** khiến chúng tự động tương đương.

Đầu tiên hãy xác định độc lập: *Có cần bỏ qua hoa/thường không? Có cần coi các biểu diễn Unicode tương đương là một không?* Một ứng dụng có thể cần một trong hai, cả hai hoặc không cần cái nào.

## 2. Unicode normalization thực sự làm gì?

Unicode cho phép cùng một ký tự hiển thị được biểu diễn bằng một mã điểm (*precomposed*) hoặc nhiều mã điểm (*decomposed*). Chẳng hạn:

- `"\u00E9"` = U+00E9, LATIN SMALL LETTER E WITH ACUTE.
- `"e\u0301"` = U+0065 LATIN SMALL LETTER E + U+0301 COMBINING ACUTE ACCENT.

`String.equals` so chính xác các đơn vị UTF-16, nên hai chuỗi trên không bằng nhau trước khi chuẩn hóa. `String.length()` cũng có thể khác nhau dù người dùng nhìn thấy cùng một chữ; độ dài UTF-16 không nhất thiết bằng số ký tự người dùng nhận biết (*grapheme clusters*).

Java cung cấp `java.text.Normalizer` với bốn dạng:

| Dạng | Cơ chế | Trường hợp sử dụng |
| --- | --- | --- |
| **NFC** | Phân rã chính tắc, sắp lại dấu kết hợp rồi ghép lại khi có thể | Lựa chọn thông dụng cho lưu và so sánh văn bản, vẫn bảo toàn khác biệt ngữ nghĩa |
| **NFD** | Phân rã chính tắc, không ghép | Phân tích mã điểm và dấu kết hợp |
| **NFKC** | Phân rã tương thích rồi ghép | Khóa so khớp đặc biệt nếu nghiệp vụ cho phép gộp các ký tự tương thích |
| **NFKD** | Phân rã tương thích, không ghép | Xử lý tương thích chuyên biệt |

“Chính tắc” là những biểu diễn Unicode coi là tương đương; “tương thích” còn có thể gộp những dạng trình bày khác nhau. Chữ **Ａ** (U+FF21, fullwidth A) vẫn là **Ａ** sau NFC, nhưng thành **A** sau NFKC. Một số chữ số khoanh tròn, số mũ hay ligature cũng có thể đổi dạng khi dùng NFKC. **Không dùng NFKC cho mọi văn bản theo thói quen**: cần xác nhận các khác biệt đó có được phép biến mất hay không.

`Normalizer.normalize(input, Normalizer.Form.NFC)` trả về chuỗi đã chuẩn hóa; `Normalizer.isNormalized(input, Normalizer.Form.NFC)` dùng để kiểm tra. Chuẩn hóa Unicode **không** tự viết thường, xóa dấu, bỏ khoảng trắng, sửa dấu câu, phiên âm, dịch ngôn ngữ hay phát hiện ký tự giả mạo nhìn giống nhau.

## 3. Xử lý hoa/thường: biến đổi chữ khác với so khớp không phân biệt chữ

### Đổi dạng chữ bằng String

- `s.toLowerCase(Locale.ROOT)` hoặc `s.toUpperCase(Locale.ROOT)` giúp xây dựng khóa kỹ thuật độc lập ngôn ngữ khi nghiệp vụ đã định nghĩa quy tắc như vậy.
- `s.toLowerCase(locale)` phù hợp khi thực sự cần quy tắc theo ngôn ngữ người dùng. Ví dụ trong tiếng Thổ Nhĩ Kỳ, chữ `I` thường chuyển thành `ı` (i không dấu chấm), khác `Locale.ROOT`.
- Tránh `toLowerCase()` hay `toUpperCase()` không tham số trong logic cần kết quả ổn định giữa máy chủ, vì chúng sử dụng locale mặc định của tiến trình.
- Ánh xạ case có thể phụ thuộc ngữ cảnh và thay đổi độ dài chuỗi; đừng cố xử lý Unicode bằng cách duyệt từng `char` rồi đổi chữ tại từng vị trí.

**Giới hạn quan trọng:** `toLowerCase(Locale.ROOT)` không đồng nghĩa với **Unicode full case folding**. Việc coi tiếng Đức `ß` và `ss` tương đương không được bảo đảm chỉ bằng `toLowerCase` hay `equalsIgnoreCase`. Nếu định danh đa ngôn ngữ đòi hỏi *caseless matching* đầy đủ, hãy đặc tả Unicode case folding hoặc NFKC casefold và cân nhắc thư viện Unicode chuyên dụng như ICU4J; không suy đoán rằng viết thường là đủ.

### So sánh bằng String

- `a.equals(b)`: yêu cầu các đơn vị ký tự giống hệt nhau.
- `a.equalsIgnoreCase(b)`: bỏ qua hoa/thường theo quy tắc Java; **không** tự làm NFC/NFKC, không nhận locale và không thay thế thuật toán full case folding cho mọi ngôn ngữ.
- So sánh và sắp thứ tự theo ngôn ngữ người dùng có thể cần `java.text.Collator` với locale phù hợp. `Collator` là công cụ so sánh theo ngôn ngữ, không phải hàm chuẩn hóa chung cho mọi ứng dụng.

Không dùng một “chuỗi đã viết thường” duy nhất để thay thế mọi kiểu so sánh. Khóa dữ liệu, phép tìm kiếm và chữ hiển thị có thể có chính sách khác nhau.

## 4. Regex trong Java: hiểu đúng từng cờ

Trong `java.util.regex.Pattern`:

1. `Pattern.CASE_INSENSITIVE` (inline: `(?i)`) bật so khớp không phân biệt hoa/thường. Theo tài liệu JDK, **mặc định việc nhận biết case trong chế độ này chỉ áp dụng kiểu US-ASCII**.
2. Kết hợp `Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE` (inline: `(?iu)`) để nhận biết case Unicode. `UNICODE_CASE` **một mình** không bật case-insensitive.
3. `Pattern.UNICODE_CHARACTER_CLASS` (inline: `(?U)`, chữ U viết hoa) thay đổi các lớp ký tự dựng sẵn như `\w`, `\d`, `\s` theo Unicode và ngầm bật `UNICODE_CASE`; nó **không** tự bật `CASE_INSENSITIVE` và cũng không chuẩn hóa văn bản. Phân biệt `(?u)` và `(?U)`.
4. `Pattern.CANON_EQ` hỗ trợ đối sánh tương đương chính tắc, nhưng có chi phí hiệu năng và rủi ro tốn bộ nhớ đáng kể với mẫu phức tạp. Thông thường nên **chuẩn hóa cả mẫu và đầu vào về NFC trước khi dùng regex** để dễ kiểm thử và kiểm soát.

Ví dụ `Pattern.compile("^café$", Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE)` có thể khớp `"CAFÉ"`, nhưng không có bảo đảm khớp `"CAFE\u0301"` nếu chưa chuẩn hóa. Cờ case xử lý hoa/thường; khác biệt U+00C9 so với E + U+0301 là vấn đề normalization.

Đối với regex tiếng Việt, không mặc định xem `[a-zA-Z]` là “mọi chữ cái”. Có thể dùng thuộc tính Unicode `\p{L}` cho chữ cái và `\p{M}` cho dấu kết hợp nếu phù hợp. Trong **Java string literal**, cần escape dấu gạch chéo ngược: `"\\p{L}"` và `"\\p{M}"`. Một chuỗi NFD có dấu kết hợp thuộc `\p{M}`, nên mẫu chỉ nhận “chữ cái” có thể bỏ sót dấu.

## 5. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu tệp **UnicodeTextDemo.java** dưới mã hóa UTF-8:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeTextDemo {
    private static final Normalizer.Form NFC = Normalizer.Form.NFC;

    // Khóa so sánh cơ bản theo chính sách NFC + lowercase độc lập locale.
    // Đây chưa phải Unicode full case folding cho mọi ngôn ngữ.
    private static String basicCaseKey(String input) {
        String nfc = Normalizer.normalize(input, NFC);
        String lowered = nfc.toLowerCase(Locale.ROOT);
        return Normalizer.normalize(lowered, NFC);
    }

    // Tìm chuỗi literal, bỏ qua hoa/thường và khác biệt Unicode chính tắc.
    private static boolean containsLiteralIgnoreCaseNfc(
            String text, String query) {
        String normalizedText = Normalizer.normalize(text, NFC);
        String normalizedQuery = Normalizer.normalize(query, NFC);
        Pattern regex = Pattern.compile(
                Pattern.quote(normalizedQuery),
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
        return regex.matcher(normalizedText).find();
    }

    public static void main(String[] args) {
        String composed = "CAF\u00C9";    // CAFÉ: chữ É dựng sẵn
        String decomposed = "CAFE\u0301"; // CAFE + dấu sắc kết hợp

        System.out.println("rawEquals=" + composed.equals(decomposed));
        System.out.println("caseOnlyEquals=" +
                composed.toLowerCase(Locale.ROOT)
                        .equals(decomposed.toLowerCase(Locale.ROOT)));
        System.out.println("nfcAndCaseEquals=" +
                basicCaseKey(composed).equals(basicCaseKey(decomposed)));

        Pattern asciiCase = Pattern.compile(
                "^caf\u00E9$", Pattern.CASE_INSENSITIVE);
        Pattern unicodeCase = Pattern.compile(
                "^caf\u00E9$",
                Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

        System.out.println("asciiCaseFlag=" +
                asciiCase.matcher(composed).matches());
        System.out.println("unicodeCaseFlag=" +
                unicodeCase.matcher(composed).matches());
        System.out.println("regexDecomposed=" +
                unicodeCase.matcher(decomposed).matches());
        System.out.println("regexAfterNfc=" +
                unicodeCase.matcher(
                        Normalizer.normalize(decomposed, NFC)).matches());

        System.out.println("literalSearch=" +
                containsLiteralIgnoreCaseNfc(
                        "Xin chào CAFE\u0301!", "caf\u00E9"));

        String fullwidthA = "\uFF21"; // Ａ
        System.out.println("nfcFullwidthIsA=" +
                Normalizer.normalize(fullwidthA, NFC).equals("A"));
        System.out.println("nfkcFullwidthIsA=" +
                Normalizer.normalize(
                        fullwidthA, Normalizer.Form.NFKC).equals("A"));

        boolean turkishDifferent =
                !"TITLE".toLowerCase(Locale.ROOT).equals(
                        "TITLE".toLowerCase(Locale.forLanguageTag("tr")));
        System.out.println("turkishDifferent=" + turkishDifferent);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 UnicodeTextDemo.java
java UnicodeTextDemo
~~~

Kết quả chuẩn của chương trình:

~~~text
rawEquals=false
caseOnlyEquals=false
nfcAndCaseEquals=true
asciiCaseFlag=false
unicodeCaseFlag=true
regexDecomposed=false
regexAfterNfc=true
literalSearch=true
nfcFullwidthIsA=false
nfkcFullwidthIsA=true
turkishDifferent=true
~~~

Giải thích:

- Hai biểu diễn chữ É khác mã, nên `equals` và phép chỉ viết thường trả `false`; NFC kết hợp xử lý case cho kết quả `true`.
- Chỉ bật `CASE_INSENSITIVE` chưa đủ cho É/é; thêm `UNICODE_CASE` mới có `unicodeCaseFlag=true`.
- Ngay cả regex Unicode-aware vẫn không khớp dạng decomposed cho đến khi chuẩn hóa.
- `Pattern.quote(normalizedQuery)` biến truy vấn thành **văn bản literal**, tránh `.`, `*`, `[` từ người dùng bị hiểu là toán tử regex. `find()` tìm chuỗi con, `matches()` kiểm tra toàn bộ chuỗi.
- NFC giữ nguyên chữ fullwidth A, NFKC đổi nó thành A; locale có thể thay đổi kết quả viết thường.

## 6. Thiết kế xử lý văn bản trong ứng dụng

Một quy trình bền vững thường gồm:

1. **Định nghĩa phép tương đương theo nghiệp vụ.** Phân biệt hoa/thường hay không? Có coi NFC/NFD như nhau không? Có chủ đích gộp ký tự tương thích bằng NFKC không? Có cần tìm kiếm bỏ dấu không?
2. **Giữ văn bản gốc** cho hiển thị, kiểm toán và chỉnh sửa. Tạo khóa tra cứu/so khớp phụ theo chính sách đã thống nhất, tránh làm mất nội dung người dùng nhập.
3. **Áp dụng cùng quy trình cho cả hai phía.** Nếu truy vấn được NFC + case processing mà chỉ mục không làm tương tự, kết quả tìm kiếm có thể sai. Với regex không phân biệt hoa/thường, có thể NFC cả mẫu và đầu vào rồi để `Pattern` xử lý case.
4. **Đồng bộ cơ sở dữ liệu và chỉ mục.** Quy tắc so sánh của DB có thể khác Java. Nếu đổi thuật toán chuẩn hóa khi đã có dữ liệu, kiểm tra các khóa từng khác nhau nay bị gộp và xử lý xung đột trước khi tạo ràng buộc duy nhất.
5. **Kiểm thử dữ liệu biên và hiệu năng.** Bao gồm NFC/NFD, tiếng Việt có dấu, Turkish I, ký tự nhiều mã điểm, truy vấn có toán tử regex, và đầu vào dài có nhiều dấu kết hợp. Mẫu regex cố định nên được biên dịch một lần và tái sử dụng.

| Tình huống | Cách tiếp cận |
| --- | --- |
| So chính xác tuyệt đối | `a.equals(b)`, không biến đổi |
| Coi hai biểu diễn Unicode chính tắc là một, vẫn phân biệt hoa/thường | Chuẩn hóa `NFC` ở cả hai phía rồi dùng `equals` |
| Tìm từ khóa Unicode, không phân biệt hoa/thường | NFC ở văn bản và truy vấn; `Pattern.quote(query)`, hai cờ `CASE_INSENSITIVE` và `UNICODE_CASE`, rồi `find()` |
| Khóa kỹ thuật cần một dạng chữ nhất quán | Quy định NFC + `Locale.ROOT` hoặc Unicode case folding đầy đủ nếu nghiệp vụ yêu cầu; đồng bộ ở mọi đầu vào |
| Sắp xếp theo ngôn ngữ người dùng | `Collator` với locale và cấp so sánh phù hợp |
| Tìm kiếm “không dấu” | Chỉ mục/tầng tìm kiếm riêng có quy tắc mất dấu được thống nhất |

### Tìm kiếm không dấu là một bài toán khác

Nếu sản phẩm **thực sự** cần tìm `"ma"` ra cả `"má"`, một kỹ thuật là NFD rồi bỏ các mã dấu kết hợp `\p{M}`. Đây là **biến đổi mất thông tin**, không phải “chuẩn hóa về NFC”. Nó có thể khiến nhiều từ tiếng Việt khác nghĩa trở thành một, và không nhất thiết đổi được `đ` thành `d` vì hai ký tự không phải một cặp phân rã chính tắc. Chỉ dùng khi nghiệp vụ yêu cầu và kiểm thử trên dữ liệu thật.

Đối với định danh và an toàn dữ liệu, NFC/NFKC hoặc case-insensitive **không giải quyết toàn bộ** vấn đề chữ thuộc bảng chữ khác nhau nhưng nhìn giống nhau (*confusables/homoglyphs*). Không tự động viết thường, xóa dấu hay NFKC mật khẩu nếu đặc tả xác thực không quy định cách xử lý nhất quán từ lúc đăng ký đến lúc xác minh.

## 7. Lỗi thường gặp

- **“Bật (?i) thì regex Java tự hiểu mọi chữ Unicode.”** Sai: khi cần nhận biết Unicode case phải phối hợp `CASE_INSENSITIVE` và `UNICODE_CASE`; `(?U)` là cờ khác.
- **“Case-insensitive cũng khớp NFC/NFD.”** Sai: case không tự gộp dấu kết hợp.
- **“NFC làm mất dấu tiếng Việt.”** Sai: NFC giữ dấu; bỏ dấu là một phép biến đổi khác.
- **“NFKC luôn tốt hơn NFC.”** Sai: NFKC còn gộp dạng tương thích và có thể làm mất khác biệt có ý nghĩa.
- **“Viết thường là full Unicode case folding.”** Sai: `toLowerCase`, `equalsIgnoreCase` và full case folding có phạm vi khác nhau.
- **“Dùng locale mặc định trên mọi máy là ổn.”** Sai: truyền `Locale.ROOT` hoặc locale cụ thể để kiểm soát quy tắc.
- **“`[a-z]` hoặc `\w` luôn bao phủ mọi chữ cái.”** Sai: xem thuộc tính `\p{L}`, `\p{M}` và cờ `UNICODE_CHARACTER_CLASS` khi cần.
- **“Chỉ chuẩn hóa dữ liệu lưu, không cần chuẩn hóa đầu vào tìm kiếm.”** Sai: hai phía phải dùng cùng chính sách, kể cả khi truy vấn hoặc chỉ mục xây từ dữ liệu cũ.

## 8. Tự kiểm tra nhanh

| Hai chuỗi | Điều kiện để coi là tương đương |
| --- | --- |
| `"hello"` và `"HELLO"` | Bỏ qua hoa/thường |
| `"caf\u00E9"` và `"cafe\u0301"` | Chuẩn hóa NFC, không cần đổi hoa/thường |
| `"CAF\u00C9"` và `"cafe\u0301"` | Cần cả normalization và xử lý case |
| `"má"` và `"ma"` | Không tương đương bằng NFC/case; chỉ khi nghiệp vụ cố ý tìm kiếm bỏ dấu |
| `"Ａ"` và `"A"` | NFKC có thể gộp; NFC không gộp |

**Quy tắc nhớ:** *case handling* xử lý hoa/thường; *Unicode normalization* xử lý các biểu diễn mã Unicode tương đương; *accent-insensitive search* là quy tắc riêng, có thể làm mất thông tin. Chọn từng phép theo mục đích và áp dụng nhất quán ở mọi nơi nhập/so sánh.

### Tài liệu đối chiếu hiện hành

- [Java SE 25 — String, toLowerCase và equalsIgnoreCase](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [Java SE 25 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 26 — java.util.regex.Pattern và các cờ Unicode](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
- [Unicode Standard Annex #31 — Unicode Identifiers and Syntax](https://www.unicode.org/reports/tr31/)
