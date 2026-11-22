# Pipeline làm sạch văn bản không làm mất ý nghĩa dữ liệu (Java 11+)

## 1. Làm sạch văn bản đúng nghĩa là gì?

Dữ liệu văn bản có thể trông giống nhau trên màn hình nhưng khác chuỗi Unicode, dấu cách, kiểu xuống dòng hoặc cách viết hoa. Một **pipeline làm sạch văn bản** là chuỗi bước nhận đầu vào, kiểm tra và biến đổi có chủ đích để dữ liệu có thể hiển thị, so sánh hoặc tìm kiếm nhất quán.

Mục tiêu **không làm mất ý nghĩa dữ liệu** không có nghĩa “xóa càng nhiều ký tự càng tốt”. Không có hàm `clean(String)` nào an toàn cho mọi loại dữ liệu. Tính an toàn phụ thuộc vào **ngữ nghĩa của từng trường dữ liệu** và quy tắc nghiệp vụ đã xác định.

Ví dụ:

- Với **tên hiển thị** do người dùng nhập, bỏ khoảng trắng thông thường ở hai đầu và chuẩn hóa Unicode về NFC thường hữu ích nếu hợp đồng dữ liệu cho phép.
- Với **mật khẩu, token, chữ ký số, khóa truy cập, mã định danh phân biệt từng ký tự hoặc văn bản pháp lý**, một ký tự hay một dấu cách cũng có thể là dữ liệu quan trọng: **không tự động `strip()`, đổi chữ hoa/thường hoặc chuẩn hóa nội dung dùng để xác thực**.
- Với **đoạn mã, Markdown, thơ, bảng căn cột, địa chỉ nhiều dòng**, dấu cách bên trong, thụt lề và xuống dòng có thể mang ý nghĩa.
- Với tiếng Việt, `ma`, `má`, `mà`, `mã` là những từ khác nhau; xóa dấu để “làm sạch” đã làm mất thông tin.

Hãy phân biệt ba dạng dữ liệu:

| Dạng | Vai trò | Có thể thay đổi? |
| --- | --- | --- |
| **Raw/original** | Bản nhập gốc phục vụ kiểm chứng, đối soát hoặc khôi phục | Giữ nguyên nếu cần toàn vẹn dữ liệu |
| **Canonical/display** | Bản hiển thị đã áp dụng các biến đổi mà nghiệp vụ cho phép | Có, nhưng chỉ theo chính sách cụ thể |
| **Search key** | Bản phụ trợ để tìm kiếm gần đúng, so khớp không phân biệt hoa/thường | Có thể mất thông tin; không thay thế bản gốc |

**Nguyên tắc nền tảng:** Không dùng chuỗi đã biến đổi để thay thế bản gốc khi việc thay đổi đó có thể ảnh hưởng danh tính, chữ ký, cách trình bày hoặc quyền truy cập.

## 2. Hiểu đúng Unicode và `String` trong Java

`String` của Java biểu diễn nội dung bằng các đơn vị mã **UTF-16**. Một ký tự người dùng thấy trên màn hình không nhất thiết ứng với đúng một `char` hay một mã Unicode (code point).

- `String.length()` đếm **đơn vị mã UTF-16**, không phải số “chữ” theo cảm nhận.
- `String.codePointCount(beginIndex, endIndex)` đếm **code point**, không phải số cụm ký tự hiển thị (grapheme cluster).
- `String.codePoints()` duyệt code point; không tự nhóm dấu kết hợp hoặc chuỗi emoji có zero-width joiner thành một cụm hiển thị.
- Các thao tác cắt chuỗi theo chỉ số `char` có thể cắt giữa một **surrogate pair**. Không tự cắt Unicode theo “độ dài ký tự” nếu yêu cầu là giữ nguyên những ký tự người dùng nhìn thấy.

Ví dụ một chữ có dấu có thể được mã hóa theo hai cách:

~~~text
"Hà" = U+0048 'H' + U+00E0 'à'               (dạng dựng sẵn)
"Hà" = U+0048 'H' + U+0061 'a' + U+0300        (dạng dấu kết hợp)
~~~

Hai chuỗi có thể hiển thị tương đương nhưng `String.equals()` trả về `false` nếu dãy đơn vị mã khác nhau. **Chuẩn hóa Unicode dạng NFC** có thể đưa chúng về cùng biểu diễn chuẩn tắc để so sánh nhất quán.

Lưu ý: `String` đã tồn tại lâu trước Java 11. Những API `strip()`, `isBlank()` và `lines()` được thêm ở Java 11 và vẫn áp dụng trên các Java hiện hành. `java.text.Normalizer` cũng tiếp tục được hỗ trợ; các quy tắc chuẩn hóa cụ thể đến từ chuẩn Unicode.

## 3. Pipeline đề xuất: xác định chính sách rồi mới biến đổi

Một pipeline có kiểm soát cho **trường tên hiển thị** có thể là:

~~~text
Nguồn văn bản
    |
    v
Giải mã chính xác (nếu nguồn là byte) và kiểm tra đầu vào
    |
    v
Giữ bản gốc khi cần truy vết
    |
    v
Áp dụng quy tắc riêng của trường: strip() ở hai đầu (nếu cho phép)
    |
    v
Normalizer.normalize(text, Normalizer.Form.NFC)
    |
    v
Kiểm tra kết quả: không rỗng, độ dài hợp lệ, quy tắc nghiệp vụ
    |
    +--> Chuỗi hiển thị/canonical
    |
    +--> Search key tách biệt, nếu thực sự cần
~~~

Thứ tự trên là ví dụ chính sách cho **tên hiển thị**. Với ghi chú nhiều dòng hoặc mã định danh, các bước được phép có thể khác hẳn.

### Bước A — Đầu vào và giải mã

Nếu dữ liệu ban đầu là **byte** (từ tệp, mạng, hàng đợi), cần biết đúng bảng mã. Thường dùng UTF-8 theo hợp đồng. Tránh “thử nhiều encoding cho đến khi nhìn có vẻ đúng” vì có thể biến dữ liệu thành ký tự sai.

Khi hệ thống bắt buộc phát hiện dữ liệu UTF-8 không hợp lệ thay vì âm thầm thay bằng ký tự `�` (U+FFFD), dùng `CharsetDecoder` với `CodingErrorAction.REPORT` hoặc validation theo giao thức. `String` sau khi đã giải mã không cho biết chắc trước đó byte nguồn có bị thay thế hay không. Nếu cần toàn vẹn byte, phải lưu/kiểm tra byte gốc trước.

### Bước B — Giữ bản gốc trước khi biến đổi

Trong Java, `String` là immutable: `strip()`, `replace()`, `Normalizer.normalize(...)` trả về kết quả mới, không sửa chính đối tượng chuỗi cũ.

~~~java
String raw = "  An  ";
String display = raw.strip();
// raw vẫn là "  An  "; display là "An".
~~~

Tuy nhiên tính immutable **không tự động lưu bản gốc vào cơ sở dữ liệu**. Nếu luồng xử lý chỉ ghi `display` và bỏ `raw`, vẫn không thể khôi phục chính xác đầu vào. Thiết kế lưu trữ theo yêu cầu nghiệp vụ và bảo mật, không lưu mọi dữ liệu nhạy cảm tùy tiện.

### Bước C — Chỉ loại bỏ khoảng trắng khi được phép

Java 11 cung cấp:

- `strip()`: loại khoảng trắng ở **đầu và cuối** theo định nghĩa `Character.isWhitespace(int)`.
- `stripLeading()` / `stripTrailing()`: chỉ loại ở một phía tương ứng.
- `isBlank()`: kiểm tra chuỗi rỗng hoặc toàn ký tự được `Character.isWhitespace` nhận diện.
- `trim()`: cơ chế cũ kiểm tra các đơn vị mã `<= U+0020`; không tương đương `strip()` với Unicode.

**Điểm dễ sai:** Java **không xem** một số dấu cách không ngắt dòng như U+00A0 NO-BREAK SPACE, U+2007 FIGURE SPACE, U+202F NARROW NO-BREAK SPACE là `Character.isWhitespace`. Vì vậy:

~~~java
"\u2003".isBlank();        // true: EM SPACE
"\u00A0".isBlank();        // false: NO-BREAK SPACE
"\u00A0x\u00A0".strip();   // vẫn còn U+00A0 ở hai đầu
~~~

Không nên từ kết quả trên suy ra U+00A0 là “ký tự rác”: khoảng trắng không ngắt dòng có thể phục vụ định dạng và quy tắc ngôn ngữ. Nếu trường dữ liệu của bạn coi chúng là khoảng trắng có thể xóa, hãy **đặc tả rõ danh sách ký tự và trường được phép áp dụng**; đừng thay đổi hàng loạt mọi bản ghi.

Quan trọng hơn: `strip()` **không xóa khoảng trắng giữa chuỗi**. Hai dấu cách trong `"Mã  07"` vẫn được giữ; đây thường là điều bạn muốn ở bước làm sạch chung.

### Bước D — Chuẩn hóa Unicode bằng NFC khi phù hợp

Java hỗ trợ:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

**NFC** gộp các chuỗi tương đương **theo chuẩn tắc Unicode** vào dạng chuẩn, giúp so sánh và lưu trữ nhất quán mà vẫn bảo toàn tương đương chuẩn tắc. Ví dụ `"Ha\u0300"` và `"H\u00E0"` trở thành cùng chuỗi NFC.

Phân biệt các dạng:

| Dạng | Đặc điểm | Dùng khi nào |
| --- | --- | --- |
| `NFC` | Phân rã chuẩn tắc rồi tổ hợp lại | Thường phù hợp cho văn bản hiển thị/tìm kiếm chính xác theo chuẩn tắc |
| `NFD` | Phân rã chuẩn tắc | Xử lý chuyên biệt cần phân tách ký tự cơ sở và dấu kết hợp |
| `NFKC` | Phân rã tương thích rồi tổ hợp | So khớp tương thích có chính sách riêng; **có thể xóa khác biệt có ý nghĩa** |
| `NFKD` | Phân rã tương thích | Xử lý đặc thù, cũng có thể làm mất khác biệt tương thích |

Ví dụ **không nên mặc định dùng NFKC**:

~~~java
Normalizer.normalize("\u2460", Normalizer.Form.NFC);   // "①"
Normalizer.normalize("\u2460", Normalizer.Form.NFKC);  // "1"
~~~

`①` và `1` có thể mang ý nghĩa trình bày hoặc danh mục khác nhau. NFC là phép biến đổi chuẩn tắc nhưng **không bảo đảm chuỗi byte/UTF-16 giữ nguyên**; nếu cần tái hiện đúng đầu vào hoặc kiểm chữ ký, vẫn phải giữ raw.

### Bước E — Xuống dòng và khoảng trắng nội bộ: bảo toàn mặc định

Đối với ghi chú nhiều dòng, nội dung như:

~~~text
Tên mục
    Mô tả đã thụt lề
Một dòng có hai khoảng trắng ở cuối  
~~~

có thể chứa thụt lề, dòng trống và khoảng trắng mang ý nghĩa. Không mặc định:

~~~java
text.replaceAll("\\s+", " "); // Ví dụ CẦN TRÁNH khi phải giữ cấu trúc văn bản.
~~~

Biểu thức trên có thể gộp nhiều dấu cách, tab và một số dấu kết thúc dòng thành một khoảng trắng, từ đó phá hỏng bố cục; phạm vi `\\s` trong regex còn phụ thuộc cấu hình Unicode của `Pattern`. Tương tự, `replaceAll("[^\\p{ASCII}]", "")` xóa tiếng Việt, nhiều ngôn ngữ và emoji; tuyệt đối không coi đó là làm sạch Unicode không mất dữ liệu.

Khi **quy tắc nghiệp vụ xác định CRLF, CR và LF chỉ là các biến thể xuống dòng tương đương**, có thể chuẩn hóa chúng về LF mà vẫn giữ **số dòng, thứ tự nội dung và dấu cách nội bộ**:

~~~java
String normalizedLines = input
        .replace("\r\n", "\n")
        .replace('\r', '\n');
~~~

Đây vẫn là **thay đổi biểu diễn dữ liệu**, vì mất thông tin kiểu ký tự xuống dòng ban đầu. Không dùng cho chữ ký byte, các định dạng quy định xuống dòng chính xác hoặc trường cần giữ nguyên nguồn.

`String.lines()` (Java 11+) rất hữu ích để **đọc** các dòng, nhưng các phần tử stream **không chứa ký tự xuống dòng**, và không tạo một dòng rỗng bổ sung sau dấu kết thúc dòng cuối cùng. Vì thế, `text.lines().collect(Collectors.joining("\n"))` **không bảo toàn chính xác** việc có hay không có dấu xuống dòng cuối; đừng dùng làm phương pháp làm sạch mặc định nếu cần giữ cấu trúc.

## 4. Ví dụ Java 11+ hoàn chỉnh: giữ raw, tạo display và search key riêng

Tạo tệp **UnicodeCleaningPipeline.java**:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public class UnicodeCleaningPipeline {
    public static void main(String[] args) {
        // Chữ "Hà Nội" viết bằng các dấu Unicode kết hợp.
        // Không dùng ký tự có dấu trong source để dễ kiểm thử trên nhiều máy.
        String rawName = "  Ha\u0300 No\u0323\u0302i  ";

        String display = cleanDisplayName(rawName);
        System.out.println("displayMatches=" +
                display.equals("H\u00E0 N\u1ED9i"));
        System.out.println("nfc=" +
                Normalizer.isNormalized(display, Normalizer.Form.NFC));
        System.out.println("rawPreserved=" +
                rawName.startsWith("  "));
        System.out.println("idempotent=" +
                cleanDisplayName(display).equals(display));

        // Dùng chỉ cho tìm kiếm, không thay thế display hoặc raw.
        System.out.println("searchKeyMatches=" +
                searchKey(display).equals("h\u00E0 n\u1ED9i"));

        // Chỉ chuẩn hóa xuống dòng vì trường ghi chú cho phép.
        String note = normalizeLineEndings("Line 1\r\nLine 2  \r\n");
        System.out.println("twoLines=" + (note.lines().count() == 2));
        System.out.println("finalNewlinePreserved=" +
                note.endsWith("\n"));
        System.out.println("spacesPreserved=" +
                note.contains("Line 2  \n"));

        // Chú ý: U+00A0 không thuộc Character.isWhitespace.
        String noBreak = "\u00A0Hello\u00A0";
        System.out.println("nbspUntouched=" +
                noBreak.strip().equals(noBreak));
        System.out.println("emSpaceBlank=" + "\u2003".isBlank());
        System.out.println("nbspBlank=" + "\u00A0".isBlank());
    }

    // Chỉ dùng cho field tên hiển thị đã cho phép bỏ biên trắng.
    static String cleanDisplayName(String input) {
        Objects.requireNonNull(input, "input");
        String cleaned = Normalizer.normalize(
                input.strip(), Normalizer.Form.NFC);
        if (cleaned.isBlank()) {
            throw new IllegalArgumentException("name is blank");
        }
        return cleaned;
    }

    // Không gộp nhiều khoảng trắng hoặc xóa dòng trống.
    static String normalizeLineEndings(String input) {
        Objects.requireNonNull(input, "input");
        return input.replace("\r\n", "\n").replace('\r', '\n');
    }

    // Phép so khớp phụ trợ; KHÔNG bảo toàn chữ hoa/thường.
    static String searchKey(String displayName) {
        return Normalizer.normalize(
                displayName, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);
    }
}
~~~

Biên dịch với JDK hỗ trợ Java 11 và chạy:

~~~bash
javac --release 11 UnicodeCleaningPipeline.java
java UnicodeCleaningPipeline
~~~

Kết quả **chính xác**:

~~~text
displayMatches=true
nfc=true
rawPreserved=true
idempotent=true
searchKeyMatches=true
twoLines=true
finalNewlinePreserved=true
spacesPreserved=true
nbspUntouched=true
emSpaceBlank=true
nbspBlank=false
~~~

**Giải thích kết quả:**

1. `displayMatches=true`: chuỗi chứa dấu kết hợp được `NFC` đưa về biểu diễn tương đương với `"Hà Nội"` (dùng Unicode escapes trong mã). Hai dấu cách ở biên được bỏ theo chính sách của tên hiển thị.
2. `nfc=true` và `idempotent=true`: sau lần làm sạch đầu, chạy lại cùng bước không đổi kết quả trong ví dụ. Tính **idempotent** là phẩm chất nên kiểm tra ở pipeline.
3. `rawPreserved=true`: biến `rawName` vẫn chứa khoảng trắng ban đầu vì `String` là immutable. Để lưu raw qua nhiều phiên chạy phải có quyết định lưu trữ riêng.
4. `searchKeyMatches=true`: khóa tìm kiếm được chuyển về chữ thường bằng `Locale.ROOT` và vẫn giữ dấu tiếng Việt; khóa này **không dùng để xác định hai tên chắc chắn thuộc cùng một người**.
5. `twoLines=true`, `finalNewlinePreserved=true`, `spacesPreserved=true`: đổi CRLF thành LF **không xóa** dòng cuối, newline cuối hay hai dấu cách trước newline trong ví dụ. Khi dùng `lines()` chỉ để **đếm/đọc**, không tự ghép rồi ghi đè văn bản.
6. `nbspUntouched=true`, `emSpaceBlank=true`, `nbspBlank=false`: minh họa khác biệt giữa dấu cách không ngắt dòng U+00A0 và EM SPACE U+2003 theo định nghĩa khoảng trắng của Java.

Đây là một **pipeline ví dụ có chính sách rõ ràng cho từng field**: `cleanDisplayName` dành cho tên; `normalizeLineEndings` dành cho văn bản nhiều dòng khi cho phép; `searchKey` chỉ cho nhu cầu tìm kiếm. Không đem cả ba hàm áp dụng theo chuỗi cho mọi đầu vào.

### Giới hạn có chủ ý của ví dụ

- `cleanDisplayName` chỉ nhận biết “blank” theo `Character.isWhitespace`, vì vậy tên chỉ có U+00A0 **không được xem là blank**. Nếu hệ thống quy định U+00A0 không hợp lệ cho trường tên, cần kiểm tra riêng một cách minh bạch.
- `searchKey` dùng `Locale.ROOT` để tránh phụ thuộc locale mặc định của máy, nhưng `toLowerCase` không phải **Unicode full case folding**, không thay thế so khớp theo ngôn ngữ, và cũng không phải phép chuẩn hóa để bảo toàn danh tính.
- `normalizeLineEndings` thay đổi chuỗi gốc nếu ban đầu dùng CR/CRLF, nên chỉ gọi ở nơi cho phép. Ví dụ không thực hiện loại bỏ ký tự điều khiển, dấu câu hay các khoảng trắng nội bộ.

## 5. Bảng chính sách: không phải chuỗi nào cũng “làm sạch” như nhau

| Đầu vào/ngữ cảnh | Biến đổi được cân nhắc | Không nên tự động làm |
| --- | --- | --- |
| `"  Hà Nội  "`, tên hiển thị | `strip()` nếu UX quy định bỏ dấu cách biên; `NFC` | Bỏ dấu, xóa khoảng trắng giữa từ, đổi họ tên |
| `"Ha\u0300"`, Unicode tương đương | `NFC` cho dạng canonical | Kết luận một chuỗi raw byte-for-byte giống chuỗi đã chuẩn hóa |
| `"má"` và `"ma"` | Giữ nguyên phân biệt có dấu | Xóa dấu vì cho rằng dấu là “nhiễu” |
| `"  0012  "`, mã định danh | Áp dụng đúng quy tắc ID được chủ sở hữu dữ liệu quy định | Chuyển thành số `12`, mất số 0 đầu |
| `"A  B"`, chuỗi tự do | Mặc định giữ cả hai dấu cách | Gộp thành `"A B"` vô điều kiện |
| `"Line 1\r\nLine 2\r\n"`, note | Đổi line ending nếu định dạng đích cho phép | Bỏ dòng trống/newline cuối nếu tài liệu cần giữ |
| `"①"` và `"1"` | Bảo toàn nếu ký hiệu khác nhau quan trọng | NFKC toàn hệ thống khiến hai giá trị nhập thành một |
| Password/token/chữ ký | Không sửa nội dung; kiểm tra theo giao thức | `strip()`, `toLowerCase()`, `NFC` tự ý |
| Markdown/source code | Giữ dấu cách, thụt lề, ký tự xuống dòng khi cần | `replaceAll("\\s+", " ")` |

**Lưu ý:** Bảng là ví dụ ra quyết định, không phải quy chuẩn áp dụng cho mọi sản phẩm. Với một định danh cụ thể, có thể có quy tắc kiểm tra và chuẩn hóa bắt buộc do tiêu chuẩn định danh quy định. Khi đó **theo đúng tiêu chuẩn của định danh**, không theo “clean text” chung.

## 6. Chữ hoa/thường, ngôn ngữ và dấu: đặc biệt cẩn thận

**Đừng dùng `toLowerCase()` không tham số** khi ý định là tạo khóa tìm kiếm ổn định giữa các máy: kết quả có thể phụ thuộc `Locale.getDefault()`. Một số ngôn ngữ như tiếng Thổ Nhĩ Kỳ có quy tắc chữ I khác với tiếng Anh.

Nếu chỉ cần một khóa tìm kiếm kỹ thuật **không phụ thuộc locale mặc định**, có thể dùng:

~~~java
String key = Normalizer.normalize(input, Normalizer.Form.NFC)
        .toLowerCase(Locale.ROOT);
~~~

Nhưng cần hiểu chính xác:

- `Locale.ROOT` là locale trung tính, **không đại diện đầy đủ cho mọi quy tắc ngôn ngữ**.
- So khớp không phân biệt chữ hoa/thường theo người dùng có thể cần `Collator` với locale phù hợp hoặc thư viện Unicode chuyên dụng tùy yêu cầu.
- Chuẩn hóa chữ thường **làm mất khác biệt chữ hoa**, và không cho phép suy ra hai tên người, mã hàng hoặc ID có cùng danh tính.
- **Không xóa dấu tiếng Việt mặc định.** Loại dấu có thể khiến hai từ khác nghĩa trở thành cùng chuỗi; nếu cần tìm kiếm không dấu thì chỉ tạo **chỉ mục tìm kiếm riêng**, giữ bản hiển thị và raw.
- **Không xóa mọi ký tự độ rộng bằng không.** Một số ký tự như ZERO WIDTH JOINER (U+200D) góp phần tạo chuỗi emoji hoặc cách biểu diễn của ngôn ngữ; xóa bừa có thể đổi cách hiển thị và ý nghĩa.
- **Không mặc định thay NFKC cho NFC.** NFKC đưa nhiều ký hiệu tương thích về dạng khác, có thể mong muốn ở một số trường định danh theo chuẩn cụ thể nhưng không an toàn cho mọi văn bản.

## 7. Khi muốn lọc ký tự bất thường, hãy kiểm tra có mục đích

Trong dữ liệu thực tế có thể xuất hiện ký tự điều khiển, kí tự thay thế U+FFFD, surrogate không ghép đôi, ký tự ngoài bảng chữ cái dự kiến hoặc ký tự dùng để giả mạo hiển thị. **Phát hiện bất thường** và **xóa bất thường** là hai việc khác nhau.

Ví dụ, nếu hệ thống yêu cầu chuỗi Java phải là UTF-16 well-formed (không có surrogate lẻ), có thể kiểm tra theo từng `char` trước khi tiếp tục. Hàm dưới đây là **đoạn mã bổ trợ**, đặt vào một lớp Java nếu cần dùng; nó không sửa dữ liệu:

~~~java
static boolean isWellFormedUtf16(String s) {
    for (int i = 0; i < s.length(); i++) {
        char current = s.charAt(i);
        if (Character.isHighSurrogate(current)) {
            if (i + 1 >= s.length()
                    || !Character.isLowSurrogate(s.charAt(i + 1))) {
                return false;
            }
            i++; // Bỏ qua low surrogate đi cùng high surrogate.
        } else if (Character.isLowSurrogate(current)) {
            return false;
        }
    }
    return true;
}
~~~

Hàm kiểm tra một thuộc tính kỹ thuật của UTF-16, **không chứng minh văn bản đúng ngữ pháp, đúng chính tả, được phép lưu hay không chứa ký tự gây nhầm lẫn**. Nếu định dạng đầu vào đã quy định UTF-8 hợp lệ, cần kiểm tra lỗi ngay ở bước giải mã; không trông chờ một bước “xóa ký tự lạ” sau đó sẽ khôi phục dữ liệu.

Cách xử lý khi gặp ký tự không hợp lệ phụ thuộc vào trường dữ liệu: từ chối và yêu cầu nhập lại, ghi thông báo validation, hoặc áp dụng quy tắc thay thế đã được thiết kế. Không che giấu vấn đề bằng cách lặng lẽ xóa.

## 8. Kiểm thử pipeline: đúng nghĩa và có thể lặp lại

Một pipeline dùng trong ứng dụng nên có bộ kiểm thử sát dữ liệu thực. Những thuộc tính đáng kiểm tra:

1. **Bảo toàn raw** khi cần đối soát: pipeline không ghi đè bản gốc.
2. **Tương đương chuẩn tắc:** hai cách mã hóa Unicode tương đương theo NFC cho kết quả canonical giống nhau.
3. **Không gộp nhầm:** những chuỗi phải phân biệt theo nghiệp vụ (ví dụ `"ma"` / `"má"`, `"0012"` / `"12"`) vẫn khác nhau.
4. **Idempotence:** `clean(clean(x)).equals(clean(x))` với các đầu vào thuộc miền hợp lệ.
5. **Biên trắng:** thử space, tab, EM SPACE, NBSP, NARROW NBSP, dòng trống và input chỉ chứa khoảng trắng.
6. **Dấu xuống dòng:** thử `\n`, `\r\n`, `\r`, dòng trống và newline cuối; đừng đoán rằng `lines()` có thể ghép lại nguyên văn.
7. **Unicode đa ngôn ngữ:** tiếng Việt có dấu dựng sẵn/dấu kết hợp, chữ khác bảng, emoji có biến thể trình bày, ký tự supplementary.
8. **Null, dữ liệu rỗng và độ dài lớn:** xác định lỗi phù hợp, giới hạn theo đúng **đơn vị** (byte UTF-8, UTF-16 code unit, code point, grapheme hay số ký tự hiển thị) mà nghiệp vụ yêu cầu.
9. **Tính ổn định giữa môi trường:** nếu dùng lowercase/collation, kiểm soát `Locale`; chú ý phiên bản Unicode được JDK cung cấp có thể ảnh hưởng một số quy tắc ký tự.
10. **Tương tác với nơi lưu/truy vấn:** kiểm tra chuẩn hóa theo ứng dụng, database collation, chỉ mục và validation cùng tuân thủ một hợp đồng. Không dùng search key làm khóa định danh nếu có thể xảy ra va chạm.

Ví dụ kiểm thử mang tính ý tưởng:

~~~java
String a = "Ha\u0300";
String b = "H\u00E0";

assert Normalizer.normalize(a, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(b, Normalizer.Form.NFC));

// Không được áp dụng hàm xóa dấu không kiểm soát:
// "má" và "ma" khác nhau theo chính tả/ngữ nghĩa.
~~~

Đoạn này là mã minh họa tính chất chuẩn tắc; nếu dùng `assert` trong chương trình Java, nhớ bật với `java -ea`. Trong ứng dụng, nên dùng JUnit/test framework phù hợp để kiểm thử tự động, bao gồm trường hợp lỗi.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao có vấn đề | Cách thay |
| --- | --- | --- |
| “Một hàm clean cho tất cả các field” | Token, tên, note và ID có ngữ nghĩa khác nhau | Chính sách theo field, hàm và test riêng |
| `trim()` đủ cho mọi Unicode | Khác định nghĩa `strip()` và nhiều khoảng trắng Unicode | Chọn API/danh sách ký tự theo hợp đồng |
| Gộp mọi khoảng trắng bằng regex | Mất thụt lề, dòng, dấu cách quan trọng | Giữ nguyên nội bộ trừ khi có yêu cầu rõ |
| Bỏ dấu “để chuẩn hóa” | Mất khác biệt tiếng Việt và nhiều ngôn ngữ | Dùng NFC; chỉ tạo chỉ mục tìm kiếm không dấu nếu cần |
| Đổi hoa/thường ngay trên dữ liệu gốc | Có thể đổi định danh hoặc văn bản | Tạo search key phụ và kiểm soát Locale |
| Chuẩn hóa NFKC toàn bộ văn bản | Một số ký hiệu tương thích bị gộp | NFC làm mặc định có điều kiện; NFKC theo chính sách chuyên biệt |
| Dùng `lines().joining("\n")` để “giữ nguyên dòng” | Mất dấu kết thúc dòng và loại line ending gốc | Chỉ đọc/đếm lines; nếu được phép, thay CRLF/CR có kiểm soát |
| So sánh `length()` với số ký tự hiển thị | UTF-16 length không bằng grapheme count | Xác định rõ đơn vị độ dài |
| Xóa mọi ký tự vô hình hoặc emoji | Có thể thay đổi hiển thị/ngữ nghĩa | Phát hiện, phân loại, xử lý có chính sách |
| Thấy `isBlank()==false` và suy ra “không chỉ có dấu cách” | NBSP không phải `Character.isWhitespace` | Tạo validation riêng theo định nghĩa trường |

## 10. Checklist trước khi triển khai

Trước khi đưa pipeline vào xử lý dữ liệu thật, hãy trả lời:

- **Dữ liệu là gì?** Tên, nội dung tự do, mã định danh, mật khẩu hay payload có chữ ký?
- **Thế nào là “cùng ý nghĩa” đối với trường đó?** Unicode canonical equivalence, cách hiển thị, so khớp theo locale hay byte-for-byte?
- **Dữ liệu gốc có cần giữ không?** Nếu có, lưu/bảo vệ raw theo đúng nhu cầu, quyền truy cập và thời hạn lưu trữ.
- **Bước biến đổi nào được cho phép?** `strip`, NFC, chuẩn hóa newline, lowercase cho search key — mỗi bước phải có lý do nghiệp vụ riêng.
- **Có những dữ liệu đặc biệt nào?** Tiếng Việt có dấu, NBSP, emoji, tab, line break, định dạng Markdown, số 0 đầu trong mã.
- **Đo lường mất mát ra sao?** Test các cặp khác nghĩa, idempotence, chiều ngược/khôi phục khi cần, đồng nhất giữa môi trường.
- **Sau khi làm sạch, có cần validate lại không?** Có: giá trị có thể thành rỗng, vượt/giảm độ dài theo đơn vị đo hoặc va chạm khóa tìm kiếm.

**Ghi nhớ:** Pipeline bảo toàn ý nghĩa là **chính sách có điều kiện**, không phải tập lệnh xóa ký tự. Với Java 11+, hãy dùng `strip()`/`isBlank()` để xử lý khoảng trắng *theo định nghĩa của Java*, `Normalizer.Form.NFC` cho tương đương Unicode chuẩn tắc khi phù hợp, và xử lý xuống dòng/locale như **các bước riêng có kiểm soát**. Luôn phân biệt **raw**, **display/canonical** và **search key**.

## Tài liệu chuẩn, còn áp dụng

- [Java SE 11 — `String`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): định nghĩa `strip()`, `isBlank()`, `lines()`, `length()` và các API liên quan.
- [Java SE 11 — `Character`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html): định nghĩa Unicode whitespace, `isSpaceChar`, surrogate, code point.
- [Java SE 26 — `Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): API Java hiện hành về Unicode normalization.
- [The Unicode Consortium — Normalization FAQ](https://unicode.org/faq/normalization.html): vì sao NFC/NFD giữ tương đương chuẩn tắc và NFKC/NFKD có thể mất phân biệt tương thích.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): đặc tả chuẩn Unicode.
- [Java SE 11 — `Locale`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Locale.html): chính sách locale và xử lý văn bản phụ thuộc ngôn ngữ.

Bài học tập trung vào các API và nguyên tắc vẫn được dùng trong Java hiện nay; không dựa vào kỹ thuật legacy hoặc giả định rằng một phép “clean” có thể an toàn cho mọi kiểu dữ liệu.