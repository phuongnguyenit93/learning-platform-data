# Lập bảng lựa chọn API và tự đánh giá các tình huống xử lý chuỗi Java

## 1. Mục tiêu thực hành

Trong Java, cùng một tác vụ xử lý văn bản có thể thực hiện bằng nhiều API: `String`, `StringBuilder`, `StringBuffer`, `CharSequence`, `String.split`, `Pattern`/`Matcher`, `String.lines`, `Stream`, `Charset`, `Normalizer`, `Comparator`... Chọn đúng API phụ thuộc vào **yêu cầu thực tế**, không chỉ vào việc viết ít dòng code.

Sau bài này, bạn cần có khả năng:

1. Chuyển một yêu cầu xử lý chuỗi thành các tiêu chí: có dùng regex không, cần giữ dữ liệu rỗng không, yêu cầu Unicode ở mức nào, có thay đổi/ghép nhiều lần không, có lưu làm khóa không, có lưu lâu hay chia sẻ giữa luồng không.
2. Dùng **bảng quyết định** để chọn API phù hợp và giải thích vì sao các lựa chọn khác có thể sai.
3. Tự giải các tình huống về tách chuỗi, tìm/thay, xây dựng văn bản, Unicode, kiểm tra bằng nhau, sắp xếp, đọc dòng và mã hóa.
4. Chạy chương trình Java 17+ có kiểm tra kết quả thật, sau đó tự chấm bằng đáp án và thang đánh giá.

Đây là bài thực hành tổng hợp theo ngữ cảnh **Java Core — String**. Các đoạn minh họa ngắn trong bảng là biểu thức hoặc mảnh code đặt trong phương thức Java; chương trình hoàn chỉnh nằm ở phần 5.

## 2. Trước khi lựa chọn: xác định hợp đồng xử lý

Hãy trả lời các câu hỏi sau trước khi chọn API:

- **Tìm nguyên văn hay theo mẫu?** Ví dụ dấu chấm trong dữ liệu là dấu chấm thật hay wildcard trong regex?
- **Chỉ cần đọc, hay tạo kết quả mới nhiều lần?** Một phép `replace` trả `String` mới có thể đủ; nối nhiều đoạn trong vòng lặp phù hợp với `StringBuilder`.
- **Đối tượng có mutable không?** `CharSequence` có thể là `StringBuilder` hoặc view của `CharBuffer`; muốn lưu giá trị ổn định phải định nghĩa snapshot.
- **Thế nào là “một ký tự”?** UTF-16 code unit, Unicode code point hay cụm grapheme hiển thị? `String.length()` không luôn là số ký tự người dùng nhìn thấy.
- **Chuỗi rỗng, null, khoảng trắng và xuống dòng có ý nghĩa không?** Ví dụ CSV giản lược cần giữ trường rỗng cuối thì dùng `split(delimiter, -1)`.
- **Bình đẳng và thứ tự có cùng quy tắc không?** `equals` phân biệt hoa/thường, trong khi `CASE_INSENSITIVE_ORDER` có thể coi hai chuỗi khác nhau là cùng khóa trong `TreeSet`.
- **Tập ký tự và locale là gì?** Mã hóa bytes cần nêu `Charset`; so sánh/định dạng theo ngôn ngữ có thể cần `Locale` và `Collator`.

Khi đề chưa nói rõ một điều kiện quan trọng, hãy **đặt giả định tường minh** hoặc hỏi người thiết kế yêu cầu. Ví dụ “tách dữ liệu CSV” không đủ để kết luận có thể dùng `split(",")` vì CSV đầy đủ có dấu nháy kép, dấu phẩy bên trong trường và quy tắc escape.

## 3. Bảng lựa chọn API theo nhiệm vụ

| Nhu cầu cụ thể | API nên cân nhắc | Điều kiện và điểm dễ sai |
| --- | --- | --- |
| Giữ một giá trị văn bản ổn định | `String` | Immutable; phù hợp trả về, cache, khóa map; `StringBuilder`/`CharSequence` không tự bất biến |
| Ghép nhiều mảnh trong **một luồng xử lý** | `StringBuilder.append(...)`, `toString()` | Tránh tạo chuỗi trung gian liên tiếp; builder mutable, không thread-safe |
| Ghép trên đối tượng có nhiều phương thức đồng bộ hóa | `StringBuffer` | Có đồng bộ hóa từng phương thức; không thay cho giao thức đồng bộ toàn thuật toán nhiều bước |
| API chỉ đọc văn bản từ nhiều implementation | `CharSequence` | Không bảo đảm immutable hay `equals` theo nội dung; snapshot bằng `toString()` khi cần lưu ổn định |
| So sánh chính xác hai `String` | `equals`, `Objects.equals` khi có null | Phân biệt hoa/thường; `Objects.equals` không biến mọi `CharSequence` thành so sánh nội dung |
| So sánh String với một `CharSequence` | `String.contentEquals(...)` | Thích hợp khi muốn so sánh ký tự hiện tại, vẫn phải xét thay đổi đồng thời |
| Bỏ qua hoa/thường với String | `equalsIgnoreCase`, `compareToIgnoreCase` | Không phải quy tắc collation theo mọi locale; không thay đổi `String.equals` |
| Sắp xếp bỏ qua hoa/thường | `String.CASE_INSENSITIVE_ORDER` | `compare == 0` có thể xảy ra khi `equals == false`; `TreeSet`/`TreeMap` coi đó là cùng khóa |
| Sắp xếp bỏ qua hoa/thường **nhưng giữ mọi String khác nhau** | `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` | Tie-breaker làm comparator nhất quán với `String.equals` |
| So sánh theo ngôn ngữ cụ thể | `Collator.getInstance(locale)` | Cần cấu hình mức độ nhạy dấu/chữ hoa và kiểm thử ngôn ngữ mục tiêu |
| Tìm chuỗi con nguyên văn | `contains`, `indexOf`, `startsWith`, `endsWith` | Không diễn giải regex; `indexOf` trả `-1` nếu không tìm thấy |
| Lấy một đoạn có chỉ số UTF-16 | `substring(start, end)` | `start` bao gồm, `end` không bao gồm; kiểm tra giới hạn |
| Thay văn bản nguyên văn | `String.replace(target, replacement)` | Không cần escape dấu `.`, `$` hoặc `\` theo regex/replacement |
| Thay theo regex có chủ đích | `replaceAll(regex, replacement)`, `replaceFirst(...)` | Regex và replacement có **cú pháp khác nhau**; `$1` có thể tham chiếu nhóm |
| Thay bằng `replaceAll` nhưng dữ liệu hai phía là văn bản nguyên văn | `Pattern.quote(target)` và `Matcher.quoteReplacement(value)` | Quote **cả hai phía**; chỉ quote regex chưa bảo vệ replacement chứa `$` hoặc `\` |
| Kiểm tra regex nhiều lần trên nhiều đầu vào | `Pattern.compile(regex)`, `pattern.matcher(text)` | `Pattern` tái sử dụng được; `Matcher` có trạng thái, không chia sẻ tùy tiện giữa luồng |
| Tách đơn giản theo regex | `split(regex)` hoặc `split(regex, limit)` | `limit=0` bỏ token rỗng cuối; `-1` giữ chúng; regex có thể khớp zero-width |
| Phân tích **CSV đầy đủ** | Thư viện CSV chuyên dụng | `split(",")` không xử lý dấu phẩy trong trường được quote, dấu nháy escape hoặc newline trong trường |
| Ghép các phần với một separator | `String.join(separator, ...)`, `Collectors.joining(...)` | `joining` thuận tiện khi đã có stream; kiểm tra dữ liệu null theo hợp đồng |
| Tách các dòng văn bản | `String.lines()` | Nhận `\n`, `\r`, `\r\n`; không tự sinh dòng rỗng cuối chỉ vì có ký tự kết thúc dòng |
| Bỏ whitespace hai đầu | `strip()`, `stripLeading()`, `stripTrailing()` | Dựa theo `Character.isWhitespace`; khác `trim()` (các code unit ≤ U+0020) |
| Kiểm tra toàn khoảng trắng | `isBlank()` | Khác `isEmpty()`: chuỗi có space không rỗng nhưng có thể blank |
| Duyệt UTF-16 code unit | `chars()`, `charAt(...)` | Surrogate pair bị biểu diễn thành hai `char` |
| Duyệt Unicode code point | `codePoints()`, `codePointAt(...)` | Code point có thể cần hai code unit; dựng lại bằng `StringBuilder.appendCodePoint(...)` |
| Chuẩn hóa biểu diễn Unicode | `Normalizer.normalize(s, Form.NFC)` | Chuỗi hiển thị giống nhau có thể khác chuỗi code point; không tự thay cho so sánh theo ngôn ngữ |
| Chuyển bytes và String | `getBytes(StandardCharsets.UTF_8)`, `new String(bytes, StandardCharsets.UTF_8)` | Chỉ rõ charset ở cả hai chiều; đừng dựa vào charset mặc định để trao đổi dữ liệu |
| Tạo biểu diễn có tham số | `String.format(Locale,...)` hoặc `"..." .formatted(...)` | Cân nhắc locale khi có số/ngày; với text nối đơn giản `StringBuilder`/`join` có thể rõ ràng hơn |

Bảng không có nghĩa mỗi API chỉ phục vụ một loại bài toán; điều cần đánh giá là **hợp đồng đúng với dữ liệu thực tế**. Ví dụ `replaceAll` hoàn toàn dùng được để thay dấu chấm thật nếu regex escape đúng, nhưng khi không cần regex, `replace` ngắn và ít nguy cơ lỗi hơn.

## 4. Bảng tình huống để tự chọn API

Trước khi xem đáp án ở phần 6, hãy tự điền **API, lý do, rủi ro/kiểm thử** cho mỗi tình huống. Độ khó tăng dần.

| Mã | Tình huống | Câu hỏi cần tự trả lời |
| --- | --- | --- |
| T1 | Bạn có chuỗi `"a.b.c"`, muốn thay mọi **dấu chấm nguyên văn** thành dấu `/`. | Chọn hàm nào? Vì sao `replaceAll(".", "/")` không đúng? |
| T2 | Người dùng tìm từ khóa có dấu `[` hoặc `$`, thay bằng chuỗi chứa `$1` và backslash, nhưng tất cả đều là văn bản nguyên văn. Hệ thống bắt buộc dùng `replaceAll`. | Phải quote phía tìm kiếm và phía thay thế bằng hàm nào? |
| T3 | Chuỗi dữ liệu `"a,b,,"` biểu diễn 4 trường, trong đó hai trường cuối rỗng. | Dùng `split` với limit bao nhiêu? Có nên dùng làm parser CSV đầy đủ không? |
| T4 | Muốn loại emoji 🚀 khỏi `"A🚀B"` mà không làm hỏng surrogate pair. | Dùng `chars()` hay `codePoints()`? Dựng lại String thế nào? |
| T5 | Cần ghép hàng nghìn mảnh text theo vòng lặp ở một luồng. | Dùng phép `+` tích lũy hay `StringBuilder`? Vì sao? |
| T6 | API nhận `CharSequence` để lưu làm tiêu đề trong cache. Người gọi có thể truyền `StringBuilder` rồi sửa. | Phải giữ tham chiếu hay tạo `String` snapshot? |
| T7 | Cần so sánh `"Java"` và `"java"` như cùng một từ khóa, nhưng hệ thống khác cần phân biệt hai khóa theo `equals`. | Khi nào dùng `equalsIgnoreCase`, khi nào dùng `String.equals`? |
| T8 | Dùng `TreeSet` sắp xếp không phân biệt hoa/thường nhưng vẫn muốn giữ cả `"Java"` và `"java"`. | Cần thêm comparator phụ nào? |
| T9 | Nhập hai giá trị `"é"` và `"e"` + dấu sắc kết hợp; cần chuẩn hóa dạng lưu trước khi so sánh chính xác. | Chọn công cụ nào? Có nên chỉ gọi `toLowerCase()` không? |
| T10 | Gửi văn bản tiếng Việt qua mạng, hai phía phải giải mã thống nhất. | Cần khai báo Charset ở API nào? |
| T11 | Muốn tách nhiều dòng có thể dùng CRLF hoặc LF, loại bỏ ký tự kết thúc dòng. | `lines()` hay `split("\n")` dễ diễn đạt hơn? |
| T12 | Muốn kiểm tra trường nhập chỉ gồm space/tab/newline là không có dữ liệu hữu ích. | Chọn `isEmpty()` hay `isBlank()`? |
| T13 | Muốn sắp xếp tên người theo quy tắc tiếng Việt hoặc một locale xác định. | Dùng `CASE_INSENSITIVE_ORDER` đã đủ chưa? |
| T14 | Dữ liệu nhận từ người dùng thật ra là một biểu thức regex có nhóm bắt, cần thay số `42` bằng `[42]`. | Khi nào phải **giữ** `(\\d+)` và `$1` thay vì quote chúng? |

**Cách làm:** ghi câu trả lời độc lập trước, rồi đối chiếu phần 6. Với mỗi tình huống cần nói cả lựa chọn **và điều kiện khiến lựa chọn đúng**. Ví dụ T3 phải nêu “giữ trường rỗng cuối” thay vì chỉ viết `split(",")`.

## 5. Chương trình kiểm thử Java 17+ chạy độc lập

Lưu tệp **StringApiDecisionPractice.java**. Đây là bài kiểm tra các lựa chọn cốt lõi, không cần JUnit hoặc thư viện ngoài. Các hàm `same` và `check` ném `AssertionError` nếu kết quả không đúng; không dựa vào lệnh Java `assert` có thể bị tắt khi thiếu cờ `-ea`.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class StringApiDecisionPractice {
    private static int passed = 0;

    static void same(String caseName, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(caseName + ": expected <" + expected
                    + "> but got <" + actual + ">");
        }
        passed++;
    }

    static void check(String caseName, boolean condition) {
        if (!condition) throw new AssertionError(caseName);
        passed++;
    }

    public static void main(String[] args) {
        same("strip", "Java", " \tJava \n".strip());
        check("isBlank", " \t\n".isBlank());

        same("literal replace", "a/b/c", "a.b.c".replace(".", "/"));
        same("quoted regex and replacement", "a$1\\tmpb",
                "a.b".replaceAll(Pattern.quote("."),
                        Matcher.quoteReplacement("$1\\tmp")));

        check("split preserving empties",
                Arrays.equals(new String[]{"a", "b", "", ""},
                        "a,b,,".split(",", -1)));
        check("split dropping trailing empties",
                Arrays.equals(new String[]{"a", "b"},
                        "a,b,,".split(",")));

        same("join", "a-b-c", String.join("-", List.of("a", "b", "c")));
        same("lines", List.of("one", "two"), "one\ntwo\n".lines().toList());

        StringBuilder builder = new StringBuilder();
        "A\uD83D\uDE80B".codePoints()
                .filter(cp -> cp != 0x1F680)
                .forEach(builder::appendCodePoint);
        same("code point filter", "AB", builder.toString());

        String message = "C\u00E0 ph\u00EA";
        byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
        same("UTF-8 round trip", message,
                new String(encoded, StandardCharsets.UTF_8));

        same("Unicode NFC", "\u00E9",
                Normalizer.normalize("e\u0301", Normalizer.Form.NFC));

        check("equalsIgnoreCase", "Java".equalsIgnoreCase("java"));
        check("String.equals case sensitive", !"Java".equals("java"));

        TreeSet<String> folded = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        folded.add("Java");
        folded.add("java");
        same("TreeSet collapses keys", 1, folded.size());

        StringBuilder mutable = new StringBuilder("x");
        CharSequence reference = mutable;
        String snapshot = mutable.toString();
        mutable.append("y");
        same("immutable snapshot", "x", snapshot);
        same("mutable CharSequence reference", "xy", reference.toString());

        check("contentEquals", "cat".contentEquals(new StringBuilder("cat")));
        same("regex capture", "id=[42]", "id=42".replaceAll("(\\d+)", "[$1]"));
        same("indexOf literal", 2, "a.b.c".indexOf("b"));
        same("substring bounds", "b.c", "a.b.c".substring(2, 5));

        System.out.println("splitCount=" + "a,b,,".split(",", -1).length);
        System.out.println("treeSetSize=" + folded.size());
        System.out.println("codePointsFiltered=" + builder);
        System.out.println("utf8RoundTrip=" + message.equals(
                new String(encoded, StandardCharsets.UTF_8)));
        System.out.println("snapshot=" + snapshot);
        System.out.println("PASS: " + passed + " checks");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringApiDecisionPractice.java
java StringApiDecisionPractice
~~~

Kết quả stdout chính xác nếu 20 phép kiểm tra thành công:

~~~text
splitCount=4
treeSetSize=1
codePointsFiltered=AB
utf8RoundTrip=true
snapshot=x
PASS: 20 checks
~~~

Những kiểm tra này chứng minh nhiều lựa chọn quan trọng hơn việc chương trình chỉ không gặp lỗi: `split(",", -1)` thật sự giữ 4 trường; `Pattern.quote` kết hợp `Matcher.quoteReplacement` giữ nguyên cả dấu `$` lẫn `\`; `codePoints()` lọc trọn emoji; `UTF-8` round-trip đúng; `TreeSet` xác định khóa tương đương theo comparator, và snapshot `String` giữ giá trị cũ khi builder thay đổi.

## 6. Đáp án và lý giải từng tình huống

| Tình huống | Đáp án/API phù hợp | Giải thích ngắn gọn |
| --- | --- | --- |
| **T1** | `"a.b.c".replace(".", "/")` | Dấu `.` trong `replaceAll` là wildcard, còn `replace` tìm đúng văn bản. Kết quả `a/b/c`. |
| **T2** | `text.replaceAll(Pattern.quote(target), Matcher.quoteReplacement(value))` | Target và replacement có **hai cú pháp độc lập**. Không quote replacement có thể khiến `$1` bị hiểu là group reference. |
| **T3** | `"a,b,,".split(",", -1)` | Kết quả `["a", "b", "", ""]`. Mặc định `split(",")` bỏ token rỗng cuối. CSV đầy đủ cần parser chuyên dụng. |
| **T4** | `text.codePoints().filter(cp -> cp != 0x1F680).forEach(builder::appendCodePoint)` | Một emoji bổ sung là một code point nhưng có hai UTF-16 code unit; xử lý theo `chars()` dễ cắt nửa surrogate pair. |
| **T5** | `StringBuilder.append(...)` rồi `toString()` | Mutable buffer giảm việc tạo String trung gian trong vòng lặp nhiều lần; không đưa cùng builder vào `parallel()` để append đồng thời. |
| **T6** | `String snapshot = Objects.requireNonNull(input).toString()` | `CharSequence` có thể mutable. Snapshot giúp nội dung ổn định sau khi phương thức trả về; đồng bộ hóa nếu nguồn bị sửa đồng thời. |
| **T7** | `equalsIgnoreCase` cho tương đương bỏ qua hoa/thường; `equals` để phân biệt khóa chính xác | Hai quy tắc này không thay thế nhau; `HashMap`/`HashSet` sử dụng `equals` và `hashCode`. |
| **T8** | `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` | So sánh phụ giải quyết trường hợp compare bỏ qua hoa/thường bằng 0; hai String khác nhau theo `equals` vẫn khác khóa. |
| **T9** | `Normalizer.normalize(s, Normalizer.Form.NFC)` rồi so sánh theo hợp đồng | Hai cách biểu diễn Unicode có thể khác code point. `toLowerCase` không phải phép chuẩn hóa Unicode NFC. |
| **T10** | `text.getBytes(StandardCharsets.UTF_8)` và `new String(bytes, StandardCharsets.UTF_8)` | Hai chiều dùng cùng charset; cần thỏa thuận giao thức về UTF-8. |
| **T11** | `String.lines()` | Nêu trực tiếp ý định duyệt các dòng và xử lý các dấu kết thúc dòng thông dụng; `split("\n")` đơn giản có thể để sót `\r` với CRLF. |
| **T12** | `isBlank()` | `" \t\n".isEmpty()` là false còn `isBlank()` là true. `isBlank` dựa theo `Character.isWhitespace`, không phải mọi ký tự Unicode trông giống dấu cách đều được coi là whitespace. |
| **T13** | Xem xét `Collator.getInstance(locale)` và kiểm thử locale thực tế | `CASE_INSENSITIVE_ORDER` là so sánh bỏ qua hoa/thường của String, không đồng nghĩa với sắp xếp theo ngôn ngữ. |
| **T14** | `"id=42".replaceAll("(\\d+)", "[$1]")` | Đây là regex và tham chiếu nhóm **được dùng có chủ đích**; không được quote regex hay replacement khi cần chức năng nhóm bắt. Kết quả `id=[42]`. |

Đối với **T4**, ví dụ mã là một mảnh pipeline bên trong phương thức sau khi có biến `text` và một `StringBuilder builder`; thao tác loại emoji và kết quả `AB` đã được kiểm tra trong chương trình hoàn chỉnh.

Đối với **T13**, một `Collator` có thể coi các chuỗi khác nhau theo `String.equals` là tương đương theo mức độ nhạy. Nếu dùng làm comparator của `TreeMap`/`TreeSet`, vẫn phải quyết định xem `compare(a,b)==0` có được phép gộp khóa hay không.

## 7. Thang tự đánh giá và cách ôn lại

Mỗi tình huống từ T1 đến T14 tối đa **2 điểm**:

- **1 điểm**: chọn đúng API (hoặc phương án tương đương đúng) với ví dụ khớp yêu cầu.
- **1 điểm**: giải thích được **cơ chế/rủi ro liên quan**, ví dụ zero-width regex, token rỗng cuối, độ rộng UTF-16, mutable snapshot, comparator không nhất quán với equals, hoặc lỗi do không quote replacement.

Tổng tối đa **28 điểm**. Đây là thang học tập gợi ý, không phải chứng nhận năng lực:

| Điểm | Gợi ý diễn giải | Hành động tiếp theo |
| --- | --- | --- |
| 0–13 | Cần củng cố khái niệm và cú pháp API | Thực hành lại các ví dụ đầu, chạy chương trình và dự đoán output trước khi xem |
| 14–21 | Đã chọn được phần lớn API nhưng còn thiếu giải thích điều kiện biên | Ôn nhóm có câu sai, viết thêm test thay vì học thuộc tên phương thức |
| 22–26 | Nắm chắc nhiều tình huống phổ biến | Thử biến thể dữ liệu Unicode, null, regex đặc biệt, collection và charset |
| 27–28 | Tự lý giải đầy đủ bảng lựa chọn này | Tự đề xuất API cho một chức năng nhỏ, nêu hợp đồng và tự thiết kế test |

### Tự mở rộng bài tập

1. Thay dữ liệu `"a,b,,"` bằng `",,a,"`. Dự đoán kết quả `split(",", 0)`, `split(",", -1)` và `split(",", 2)`; đối chiếu mảng thực tế.
2. Thay dấu chấm bằng ký tự `|` hoặc `[` trong target, replacement bằng `$1\log`. Thử lựa chọn `replace` và lựa chọn quote cả hai phía trong `replaceAll`; kiểm tra kết quả `equals`.
3. Thay `TreeSet` từ `CASE_INSENSITIVE_ORDER` sang comparator có tie-breaker; kiểm tra số phần tử và thứ tự với `"JAVA"`, `"Java"`, `"java"`.
4. Thay emoji 🚀 bằng emoji khác có code point bổ sung; kiểm tra `length()`, `codePoints().count()` và việc lọc/bổ sung bằng `appendCodePoint`.
5. Thử đầu vào có `CharSequence` là `StringBuilder` mutable: nhận tham chiếu so với chụp `String` rồi sửa builder; mô tả khác biệt.
6. Thử text có cả `\r\n`, `\n` và `\r` bằng `lines()`. Tự định nghĩa rõ trường hợp dòng trống ở đầu/cuối.
7. Đưa một chuỗi tiếng Việt có dấu về NFC; đoán xem `equals` trước và sau chuẩn hóa có thể khác nhau thế nào.

Mỗi bài mở rộng nên được ghi thành **input → API được chọn → expected output → actual output → lý do**. Đó là cách xác định lựa chọn API đã đúng với hợp đồng, không chỉ đúng tên hàm.

## 8. Những bẫy thường khiến chọn API sai

- **Đồng nhất văn bản và regex:** `replace`/`contains` tìm nguyên văn, còn `replaceAll`/`split` nhận regex. Dấu `.` hoặc `|` có thể đổi hoàn toàn ý nghĩa.
- **Quên tham số limit của split:** `split(regex)` là `split(regex, 0)`; các trường rỗng ở cuối bị loại. Ngoài ra, khớp regex có độ rộng 0 tại đầu chuỗi không tạo token rỗng đầu, khác với khớp có độ rộng dương.
- **Coi `String.length()` là số chữ hiển thị:** Java dùng UTF-16; code point khác grapheme cluster. API `codePoints()` vẫn không nhóm các cụm emoji nối hoặc ký tự kết hợp dấu.
- **Coi tất cả CharSequence có equals theo nội dung:** `StringBuilder` không override `equals` như String, còn CharBuffer có trạng thái view; phải định nghĩa snapshot và so sánh.
- **Dùng comparator bỏ qua hoa/thường cho TreeSet mà không muốn gộp khóa:** `compare == 0` có thể làm mất các biến thể chữ hoa/thường.
- **Dùng `toLowerCase()` như một phép chuẩn hóa cho mọi ngôn ngữ:** vấn đề locale, Unicode normalization và case folding là các yêu cầu khác nhau.
- **Xử lý bytes không nêu charset:** dữ liệu có dấu có thể bị đọc sai nếu hai phía dùng bộ mã khác nhau. Ghi rõ `UTF-8` tại biên chuyển mã.
- **Chỉ kiểm tra output bằng mắt:** chuỗi rỗng, dấu backslash, dấu kết hợp Unicode và sự tương đương comparator cần phép assert/số phần tử cụ thể.

## 9. Kết luận thực hành

Không có một API String duy nhất tối ưu cho mọi tình huống. Chọn API phải bắt đầu từ **hợp đồng dữ liệu**: văn bản nguyên văn hay regex; mutable hay snapshot; mã UTF-16 hay code point; tương đương theo nội dung hay comparator; có giữ dữ liệu rỗng không; charset/locale nào áp dụng. Sau khi chọn, kiểm thử ít nhất một trường hợp thường và một **trường hợp biên có thể làm sai giả định**. Khi giải thích được cả lựa chọn lẫn rủi ro, bạn đã có thể dùng bảng này để tự đánh giá và thiết kế những đoạn xử lý chuỗi Java dễ kiểm chứng.
