# Kiểm thử tiếng Việt, ký tự bổ sung và các locale khác nhau trong Java

## 1. Mục tiêu

Ứng dụng đa ngôn ngữ phải giữ đúng dữ liệu từ khi nhập, lưu trữ, truyền tải, tìm kiếm, sắp xếp đến khi hiển thị. Tiếng Việt có nhiều ký tự có dấu và nhiều cách biểu diễn Unicode tương đương. Emoji, chữ Hán mở rộng và các ký tự ngoài Basic Multilingual Plane (BMP) có thể chiếm hai đơn vị UTF-16. Khi đổi locale, quy tắc chữ hoa/chữ thường, chữ số, dấu phân cách, ngày tháng và thứ tự sắp xếp cũng có thể đổi.

Bài này hướng dẫn kiểm thử những tình huống đó trong Java, tập trung vào kiến thức và API **vẫn đang áp dụng trong ứng dụng hiện đại**. Ví dụ dùng **Java 17+**, có thể chạy bằng JDK mới hơn; không dựa vào API định dạng ngày tháng hoặc charset mặc định theo cách cũ.

Sau khi học, bạn có thể:
- Phân biệt **byte UTF-8**, **UTF-16 code unit**, **Unicode code point** và **grapheme cluster**.
- Kiểm thử dữ liệu tiếng Việt ở dạng NFC/NFD, chữ `đ`/ `Đ`, dấu kết hợp và các lỗi làm mất dấu.
- Bao phủ emoji ghép bằng ZWJ, ký tự ngoài BMP, surrogate pair và chuỗi surrogate lỗi.
- Kiểm thử `Locale` cho chữ hoa/thường, số, ngày và sắp xếp ngôn ngữ.
- Viết assertion bền vững khi nâng cấp JDK, dữ liệu Unicode hoặc CLDR.

## 2. Những đơn vị dễ nhầm lẫn

| Khái niệm | Đơn vị | Ví dụ/hệ quả kiểm thử |
| --- | --- | --- |
| UTF-8 byte | Byte khi lưu/truyền | Một code point cần 1–4 byte; phải chỉ định charset ở biên dữ liệu. |
| UTF-16 code unit | Một `char` 16 bit | `String.length()` đếm code unit; không phải số chữ người dùng nhìn thấy. |
| Unicode code point | Mã Unicode U+XXXX hoặc U+XXXXX | Một ký tự ngoài BMP chiếm hai code unit, gọi là surrogate pair. |
| Grapheme cluster | Cụm hiển thị theo quy tắc Unicode | Có thể gồm nhiều code point: chữ + dấu kết hợp, emoji ZWJ, cờ. |
| Locale | Ngôn ngữ/vùng theo BCP 47 | Điều chỉnh hành vi ngôn ngữ, không tự chọn UTF-8 hoặc timezone. |

Các trường hợp phải phân biệt:

- `"😀"`: `length() == 2`, số code point bằng 1, thường một grapheme cluster.
- `"a\u0301"`: chữ `a` cộng dấu sắc U+0301 có 2 code point, thường hiển thị thành một cụm; NFC có thể tạo `"á"`.
- `"ắ"`: có biểu diễn tiền tổ hợp; NFD tương ứng `a + U+0306 + U+0301`.
- `"👩‍💻"`: emoji phụ nữ + ký tự nối U+200D (ZWJ) + máy tính; nhiều code point nhưng thường một cụm hiển thị.
- `"🇻🇳"`: hai regional indicator code point, thường là một hình cờ.
- `"𠀀"` (U+20000): một code point ngoài BMP, hai UTF-16 code unit.

Dùng `String.codePoints()`, `codePointAt()`, `codePointCount()` và `offsetByCodePoints()` để làm việc ở mức code point. Java `Pattern` hỗ trợ biểu thức `\\X` cho extended grapheme cluster. Khi UI yêu cầu xóa một chữ theo cảm nhận người dùng, kiểm tra ranh giới grapheme; khi giao thức yêu cầu giới hạn byte, tính byte của encoding thực tế. Số grapheme không đồng nghĩa với chiều rộng pixel hay số glyph mà font vẽ ra.

**Surrogate lẻ:** một `String` có thể chứa high/low surrogate không ghép cặp, dù chuỗi đó không biểu diễn Unicode scalar value hợp lệ. `String.codePointCount()` vẫn có thể đếm surrogate lẻ; nếu cần dữ liệu hợp lệ, phải kiểm tra hoặc mã hóa bằng encoder báo lỗi tường minh.

## 3. Ma trận dữ liệu kiểm thử

Hãy tạo fixture phản ánh dữ liệu thực tế thay vì chỉ thử ASCII.

| Nhóm | Dữ liệu mẫu | Kỳ vọng nên kiểm tra |
| --- | --- | --- |
| Dấu tiếng Việt | `Tiếng Việt`, `Trường học`, `Đà Nẵng`, `thủy điện` | Giữ đủ dấu, chữ hoa/thường, thứ tự code point sau round-trip. |
| Chữ khác nhau | `d`, `đ`, `D`, `Đ` | NFC/NFD không biến `đ` thành `d` hoặc xóa dấu. |
| Biểu diễn Unicode tương đương | `"ế"` và `"e\u0302\u0301"`; `"ắ"` và `"a\u0306\u0301"` | Chuẩn hóa NFC về cùng chuỗi chuẩn tắc. |
| Dấu kết hợp | `"a\u0301"`, chữ + nhiều combining mark | Không tách dấu khi thao tác ở mức grapheme. |
| Ký tự bổ sung | `"😀"`, `"𠀀"` | Code point đúng; không cắt giữa surrogate pair. |
| Emoji ghép | `"👩‍💻"`, `"🇻🇳"`, emoji có màu da | Không coi mỗi code point là một đơn vị hiển thị. |
| Encoding lỗi | UTF-8 sai `C3 28`, high surrogate lẻ | Strict decoder/encoder báo lỗi, không làm mất dữ liệu âm thầm. |
| Casing theo locale | `I/i/İ/ı` ở `tr-TR`, ký tự `ß` ở `de-DE` | Quy tắc chữ hoa/thường phụ thuộc ngôn ngữ; có thể đổi độ dài. |
| Số, ngày, tiền | `1234.5`, ngày 2026-11-05; các locale hỗ trợ | Format rồi parse lại bằng cùng locale, giữ ngữ nghĩa và độ chính xác. |
| Sắp xếp chữ | `Đà`, `đỏ`, `Dũng`, `Dung`, `résumé` | Kiểm thử quy tắc collation, tính phản xứng và thứ tự nghiệp vụ. |
| Nhiều hệ chữ | `東京`, `مرحبا`, văn bản RTL trộn số | Kiểm tra dữ liệu logic; kiểm tra bidi/font riêng ở tầng UI. |

Với tiếng Việt, cần bao phủ tối thiểu các chữ **ă, â, ê, ô, ơ, ư, đ**, dạng chữ hoa, các thanh **sắc, huyền, hỏi, ngã, nặng** và tổ hợp nhiều dấu. Đặc biệt, `đ` không phải dạng chuẩn hóa của `d`: chuẩn hóa Unicode không đồng nghĩa với bỏ dấu.

Với locale, tối thiểu thử `vi-VN`, `en-US`, `tr-TR`, `de-DE`, `fr-FR`, `ja-JP`, `ar-EG` nếu phần mềm hỗ trợ chúng. Không suy diễn một kiểu dấu phân cách hay cấu trúc ngày tháng áp dụng cho mọi vùng.

## 4. Chương trình kiểm thử chạy độc lập

Lưu toàn bộ đoạn dưới đây vào tệp **`UnicodeLocaleChecks.java`**. Đây là chương trình Java 17+ đầy đủ, chỉ dùng thư viện chuẩn. Mỗi kiểm tra thất bại sẽ ném `AssertionError`; khi tất cả thành công, kết quả được in ra ở cuối.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Collator;
import java.text.Normalizer;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class UnicodeLocaleChecks {
    private static int passed = 0;

    @FunctionalInterface
    interface Check {
        void execute() throws Exception;
    }

    private static void run(String label, Check check) throws Exception {
        check.execute();
        passed++;
        System.out.println("PASS " + label);
    }

    private static void require(boolean condition, String detail) {
        if (!condition) {
            throw new AssertionError(detail);
        }
    }

    private static void vietnameseNfcNfd() {
        String composed = "Tiếng Việt, Đà Nẵng";
        String decomposed = Normalizer.normalize(composed, Normalizer.Form.NFD);
        require(!composed.equals(decomposed), "Fixture must contain accents");
        require(
            Normalizer.normalize(composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)),
            "Canonical equivalents must normalize to the same NFC value"
        );
        require(
            !Normalizer.normalize("đ", Normalizer.Form.NFC).equals(
                Normalizer.normalize("d", Normalizer.Form.NFC)),
            "NFC must not erase the Vietnamese letter đ"
        );
    }

    private static void supplementaryCodePoint() {
        String smile = "😀";
        require(smile.length() == 2, "Emoji occupies two UTF-16 units");
        require(smile.codePointCount(0, smile.length()) == 1,
                "Emoji is one code point");
        require(smile.codePointAt(0) == 0x1F600, "Wrong code point");
        require(smile.offsetByCodePoints(0, 1) == 2,
                "Code-point offset must skip both surrogate units");
    }

    private static void graphemeClusters() {
        String combining = "a\u0301";
        String joinedEmoji = "👩‍💻";
        Pattern grapheme = Pattern.compile("\\X");
        require(combining.codePointCount(0, combining.length()) == 2,
                "Combining fixture should have two code points");
        require(grapheme.matcher(combining).results().count() == 1,
                "Base letter and combining accent form one cluster");
        require(joinedEmoji.codePointCount(0, joinedEmoji.length()) == 3,
                "Joined emoji contains three code points");
        require(grapheme.matcher(joinedEmoji).results().count() == 1,
                "ZWJ emoji should form one extended cluster");
    }

    private static void utf8RoundTrip() {
        String original = "Hà Nội, tiếng Việt 😀 𠀀";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(encoded, StandardCharsets.UTF_8);
        require(original.equals(decoded), "UTF-8 round trip changed text");
    }

    private static void strictCodec() {
        boolean decoderRejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(new byte[] {(byte) 0xC3, 0x28}));
        } catch (CharacterCodingException expected) {
            decoderRejected = true;
        }
        require(decoderRejected, "Malformed UTF-8 bytes should be rejected");

        boolean encoderRejected = false;
        try {
            StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap("\uD83D"));
        } catch (CharacterCodingException expected) {
            encoderRejected = true;
        }
        require(encoderRejected, "Unpaired high surrogate should be rejected");
    }

    private static void localeSensitiveCase() {
        Locale turkish = Locale.forLanguageTag("tr-TR");
        require("I".toLowerCase(turkish).equals("ı"), "Turkish dotted-I rule");
        require("i".toUpperCase(turkish).equals("İ"), "Turkish uppercase rule");
        require("I".toLowerCase(Locale.ROOT).equals("i"),
                "Root casing must not depend on system locale");
    }

    private static void numberAndDateRoundTrip() throws Exception {
        LocalDate expectedDate = LocalDate.of(2026, 11, 5);
        for (String tag : new String[] {
                "vi-VN", "en-US", "de-DE", "fr-FR", "ja-JP", "ar-EG"
        }) {
            Locale locale = Locale.forLanguageTag(tag);
            NumberFormat numbers = NumberFormat.getNumberInstance(locale);
            numbers.setMinimumFractionDigits(1);
            numbers.setMaximumFractionDigits(1);
            String formattedNumber = numbers.format(1234.5);
            double parsedNumber = numbers.parse(formattedNumber).doubleValue();
            require(Math.abs(parsedNumber - 1234.5) < 0.000001,
                    "Number round trip failed for " + tag);

            DateTimeFormatter dates =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);
            String formattedDate = expectedDate.format(dates);
            require(LocalDate.parse(formattedDate, dates).equals(expectedDate),
                    "Date round trip failed for " + tag);
        }
    }

    private static void vietnameseCollation() {
        Collator collation =
            Collator.getInstance(Locale.forLanguageTag("vi-VN"));
        collation.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
        require(collation.compare("ế", "e\u0302\u0301") == 0,
                "Canonical variants should compare equally");

        int forward = Integer.signum(collation.compare("Đà", "đỏ"));
        int reverse = Integer.signum(collation.compare("đỏ", "Đà"));
        require(forward == -reverse, "Comparator must be antisymmetric");
    }

    public static void main(String[] args) throws Exception {
        run("Vietnamese-NFC-NFD", UnicodeLocaleChecks::vietnameseNfcNfd);
        run("Supplementary-code-point", UnicodeLocaleChecks::supplementaryCodePoint);
        run("Grapheme-clusters", UnicodeLocaleChecks::graphemeClusters);
        run("UTF8-round-trip", UnicodeLocaleChecks::utf8RoundTrip);
        run("Strict-encoding", UnicodeLocaleChecks::strictCodec);
        run("Locale-case", UnicodeLocaleChecks::localeSensitiveCase);
        run("Locale-number-date", UnicodeLocaleChecks::numberAndDateRoundTrip);
        run("Locale-collation", UnicodeLocaleChecks::vietnameseCollation);
        System.out.println("ALL PASS (" + passed + "/8)");
    }
}
~~~

Chạy từ thư mục chứa file:

~~~bash
javac -encoding UTF-8 UnicodeLocaleChecks.java
java UnicodeLocaleChecks
~~~

Stdout kỳ vọng (các nhãn PASS không phụ thuộc ngôn ngữ mặc định của máy):

~~~text
PASS Vietnamese-NFC-NFD
PASS Supplementary-code-point
PASS Grapheme-clusters
PASS UTF8-round-trip
PASS Strict-encoding
PASS Locale-case
PASS Locale-number-date
PASS Locale-collation
ALL PASS (8/8)
~~~

**Vì sao những assertion này đáng tin?**

1. **NFC/NFD:** `String.equals()` so sánh code unit, nên hai chuỗi hiện ra giống nhau vẫn có thể khác byte/code point. `Normalizer.normalize(text, Normalizer.Form.NFC)` giúp kiểm thử canonical equivalence khi đó là chính sách của hệ thống.
2. **Code point:** emoji ngoài BMP có `length() == 2` là hành vi UTF-16 đúng. Duyệt/xử lý code point cần API tương ứng.
3. **Grapheme:** `Pattern.compile("\\X")` nhận biết ranh giới cụm mở rộng, trong đó có chữ + dấu và nhiều chuỗi emoji ZWJ; quy tắc Unicode có thể được bổ sung trong các bản JDK mới.
4. **UTF-8:** kiểm tra round-trip nội dung còn nguyên. Test byte sai và surrogate lẻ phải dùng `CodingErrorAction.REPORT` khi yêu cầu không được phép thay thế dữ liệu âm thầm.
5. **Locale:** quy tắc `I/i` của tiếng Thổ Nhĩ Kỳ cho thấy không có một cách viết hoa/thường đúng cho mọi ngôn ngữ. Mã xử lý khóa máy thường cần `Locale.ROOT`; chữ hiển thị có thể cần locale người dùng.
6. **Number/date:** cùng formatter, locale và độ chính xác thì parse lại phải ra cùng giá trị. Không nên đóng đinh cách hiển thị của từng JDK trong kiểm thử logic nền tảng.
7. **Collator:** so sánh có nhận thức ngôn ngữ, dùng canonical decomposition khi yêu cầu. Kết quả `compare(a,b)==0` không tương đương `a.equals(b)` trong mọi trường hợp.

## 5. Cách viết assertion bền vững với Unicode và locale

### 5.1. Kiểm thử theo tính chất, không chỉ snapshot ký tự

**Tại biên lưu trữ/truyền tải:** kiểm tra `decode(encode(text)) == text` với chuỗi hợp lệ. Bao gồm dữ liệu có dấu, dạng tổ hợp, emoji, CJK ngoài BMP, ký tự xuống dòng và text thực tế của người dùng. Nếu hệ thống chủ ý chuẩn hóa khi nhập, khẳng định với dạng đã quy định, không so sánh mù với dữ liệu thô.

**Tại tầng chuẩn hóa:** kiểm thử tính lũy đẳng `NFC(NFC(s)) == NFC(s)`; kiểm tra NFC của chuỗi NFD và NFC tương ứng bằng nhau. Dùng NFC để ổn định biểu diễn, không tự chuyển thành xóa dấu, không thay chính sách xác thực định danh. NFKC/NFKD là chuẩn hóa tương thích có thể biến đổi thêm ký tự; chỉ dùng khi nghiệp vụ có chủ đích rõ ràng.

**Tại tầng cắt/đếm:** xác định yêu cầu là byte, code point, grapheme hay số ký tự hiển thị có giới hạn pixel. Ví dụ, thao tác xóa một ký tự ở UI phải tránh để lại ZWJ/dấu kết hợp mồ côi; cắt theo số code point chỉ giải quyết được surrogate pair, chưa đủ cho mọi grapheme.

**Tại tầng ngôn ngữ:** dùng `Locale.forLanguageTag("vi-VN")`, `Locale.forLanguageTag("tr-TR")`, ... thay vì ngầm dùng `Locale.getDefault()`. Dùng `String.toLowerCase(locale)`/`toUpperCase(locale)` phù hợp mục tiêu. Không coi quy tắc lower/upper là ánh xạ từng `char` một vì một số phép đổi dạng có thể thay số code point.

**Tại tầng sắp xếp:** `String.compareTo()` sắp theo thứ tự UTF-16, không tự hiểu thứ tự chữ trong các ngôn ngữ. Dùng `Collator.getInstance(locale)`; xem xét `setStrength()` và `setDecomposition()` theo đặc tả nghiệp vụ. Kiểm tính phản xứng, bắc cầu, nhất quán; với kết quả sắp xếp cụ thể phải có bộ dữ liệu chuẩn từ sản phẩm. Đừng dùng collation equality làm khóa cho hash map hoặc làm so sánh danh tính.

**Tại tầng format:** `NumberFormat`, `Currency`, `DateTimeFormatter` cần locale rõ ràng. Với số thập phân/tiền có yêu cầu chính xác, dùng chính sách làm tròn và biểu diễn số phù hợp như `BigDecimal`, rồi test cùng chính sách; không giả định toàn cầu chỉ có dấu phẩy hoặc dấu chấm. Đừng bắt test phải ra cùng dấu cách U+0020/U+00A0/U+202F trên mọi phiên bản CLDR nếu hợp đồng không yêu cầu.

### 5.2. Locale không phải encoding hoặc timezone

Ba khái niệm tách biệt:
- `Locale.forLanguageTag("vi-VN")`: chọn quy tắc bản địa hóa.
- `StandardCharsets.UTF_8`: chọn mã hóa byte khi đọc/ghi dữ liệu.
- `ZoneId.of("Asia/Ho_Chi_Minh")`: chọn timezone khi chuyển đổi thời điểm.

Đối với `LocalDate`, ngày lịch không tự chứa giờ hoặc múi giờ. Đối với `Instant` hay lịch hẹn, kiểm thử timezone/DST và định dạng locale độc lập. Để kết quả test lặp lại được, truyền locale/timezone vào đối tượng xử lý; tránh sửa `Locale.setDefault()` giữa các kiểm thử chạy song song.

### 5.3. Dữ liệu locale có thể thay đổi theo JDK/CLDR

Bản JDK hoặc runtime image mới có thể đi kèm dữ liệu Unicode/CLDR khác. Cùng `Locale` vẫn có thể xuất hiện thay đổi hợp lệ về dấu phân cách, ký hiệu, cách viết ngày hoặc quy tắc hiển thị. Do đó chia test thành:

1. **Bất biến nền tảng:** UTF-8 round-trip, canonical equivalence, đếm code point, format/parse cùng locale và độ chính xác.
2. **Hợp đồng ngôn ngữ:** ví dụ quy tắc `tr-TR`, phân biệt `đ`/`d`, thứ tự tên tiếng Việt theo yêu cầu sản phẩm.
3. **Snapshot UI/định dạng bắt buộc:** chỉ chốt chuỗi hiển thị chính xác khi thực sự là hợp đồng; ghi lại phiên bản JDK/CLDR, timezone, numbering system, locale provider và đánh giá thay đổi khi nâng cấp.

Đặc biệt, dữ liệu collation mà JDK dùng có thể không giống hoàn toàn engine collation của database hoặc hệ thống tìm kiếm. Nếu yêu cầu thứ tự tiếng Việt phải giống nhau giữa Java, DB và search index, hãy viết test hợp đồng xuyên hệ thống và thống nhất thuật toán/dữ liệu collation thay vì giả định chúng mặc nhiên tương đương.

### 5.4. ResourceBundle, thông điệp và giao diện

Với `ResourceBundle`, kiểm tra:
- Locale lựa chọn đúng file/tài nguyên; fallback sang ngôn ngữ mặc định khi thiếu bản dịch là hành vi có chủ đích.
- Các key bắt buộc đều tồn tại, dấu tiếng Việt không bị biến dạng, placeholder/tham số đúng kiểu và số lượng.
- File tài nguyên được đóng gói UTF-8 phù hợp quy trình build hiện đại, không dựa vào chuyển đổi dấu thủ công.
- Văn bản dài, chữ viết phải-sang-trái, font fallback, ngắt dòng, IME, copy/paste, accessibility và emoji được xác minh ở UI thực.

Java unit test có thể xác minh nội dung logic, nhưng **không chứng minh** văn bản sẽ hiện thành một glyph, đúng chiều bidi hay có kích thước pixel mong muốn trên mọi font/trình duyệt.

## 6. Thêm kiểm thử tham số hóa vào dự án

Nếu dự án đã dùng **JUnit Jupiter**, có thể chạy cùng bộ hợp đồng trên từng locale. Đây là **trích đoạn phương thức test**, cần đặt trong test class có thư viện JUnit Jupiter và import phù hợp; không phải chương trình độc lập:

~~~java
@ParameterizedTest
@ValueSource(strings = {
    "vi-VN", "en-US", "de-DE", "fr-FR", "ja-JP", "ar-EG"
})
void numberRoundTripForSupportedLocales(String languageTag)
        throws java.text.ParseException {
    Locale locale = Locale.forLanguageTag(languageTag);
    NumberFormat format = NumberFormat.getNumberInstance(locale);
    format.setMinimumFractionDigits(1);
    format.setMaximumFractionDigits(1);

    String displayed = format.format(1234.5);
    double parsed = format.parse(displayed).doubleValue();

    org.junit.jupiter.api.Assertions.assertEquals(1234.5, parsed, 0.000001);
}
~~~

Các import được dùng gồm `org.junit.jupiter.params.ParameterizedTest`, `org.junit.jupiter.params.provider.ValueSource`, `java.util.Locale`, `java.text.NumberFormat`. Nếu từng locale có quy tắc riêng phải được kiểm thử, thêm case riêng theo đặc tả. Tạo đối tượng formatter/collator riêng mỗi lần chạy hoặc quản lý truy cập đồng thời đúng cách; không chia sẻ một instance có trạng thái tùy biến giữa các test chạy song song.

Trong CI, nên chạy trên các JDK còn được hỗ trợ của sản phẩm, với các locale mặc định khác nhau và runtime image tương ứng production. Một lệnh kiểm tra độc lập với locale hệ thống:

~~~bash
java -Duser.language=tr -Duser.country=TR UnicodeLocaleChecks
~~~

Kết quả của chương trình mẫu vẫn phải là `ALL PASS (8/8)` vì mỗi thao tác phụ thuộc ngôn ngữ đều truyền locale một cách tường minh.

Khi có lỗi, log **locale tag**, JDK version, chuỗi ở dạng escaped hoặc mã U+..., số code unit/code point/grapheme, normalization form và (nếu liên quan) byte UTF-8 dạng hex. Hai chuỗi có thể nhìn như nhau nhưng khác code point; việc log riêng những đơn vị này giúp xác định lỗi mà mắt thường không thấy.

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Kiểm thử và hướng xử lý |
| --- | --- | --- |
| `substring(0, 1)` trên emoji | Có thể trả một high surrogate lẻ | Cắt theo ranh giới code point hoặc grapheme phù hợp nghiệp vụ. |
| Coi `String.length()` là số chữ hiển thị | Dấu kết hợp, emoji ZWJ có nhiều code unit | So sánh code point count và grapheme count trong fixture. |
| So sánh NFC/NFD trực tiếp | Code unit khác nhưng tương đương chuẩn tắc | Chuẩn hóa có chủ đích trước so sánh, test round-trip. |
| Bỏ dấu tất cả tên tiếng Việt để so sánh định danh | Có thể gộp các tên khác nhau | Tách tìm kiếm gần đúng khỏi dữ liệu gốc và khóa định danh. |
| Gọi `toLowerCase()` không truyền locale | Kết quả phụ thuộc cấu hình máy/CI | Truyền locale người dùng hoặc `Locale.ROOT` đúng mục đích. |
| Dùng `String.compareTo()` sắp tên người | Thứ tự UTF-16 không đại diện thứ tự ngôn ngữ | Dùng `Collator`, đối chiếu quy tắc sản phẩm. |
| Hard-code dấu chấm/phẩy trong số | Locale và CLDR khác nhau | Format/parse với đúng locale và cấu hình độ chính xác. |
| Dùng charset ngầm định khi đọc/ghi file hoặc API | Có thể mất ký tự khi chuyển môi trường | Chỉ định UTF-8 tại biên dữ liệu; test strict codec. |
| Test bằng ảnh chụp rồi kết luận dữ liệu giống nhau | NFC/NFD nhìn giống nhau | Kiểm code point, byte, normalization. |
| Cho rằng locale tự quyết timezone hoặc hướng chữ | Các khía cạnh độc lập | Test timezone, bidi, font fallback riêng. |

## 8. Checklist nghiệm thu

- [ ] Có fixture tiếng Việt đủ nguyên âm, thanh, chữ hoa, `đ/Đ`, NFC và NFD.
- [ ] Có fixture emoji, ZWJ, cờ, chữ ngoài BMP và surrogate không hợp lệ.
- [ ] API/file/DB giữ nguyên văn bản hợp lệ qua UTF-8 round-trip hoặc chuẩn hóa đã công bố.
- [ ] Thao tác cắt/xóa/giới hạn độ dài sử dụng đúng đơn vị (byte/code point/grapheme/pixel).
- [ ] Casing, collation, number/date formatting luôn nhận locale đúng yêu cầu.
- [ ] Có kiểm thử trên mọi locale hỗ trợ, cấu hình JDK/Unicode/CLDR và runtime image của production.
- [ ] Có kiểm thử UI cho chữ có dấu, IME, emoji ghép, font fallback, văn bản RTL và accessibility.
- [ ] Khi nâng cấp JDK, phân biệt thay đổi hợp lệ của dữ liệu bản địa hóa với lỗi logic thực sự.

## Tài liệu tham khảo hiện hành

- [Java String: code points, offset và UTF-16 (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java Pattern: `\\X` Unicode extended grapheme cluster (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Java Normalizer: NFC, NFD, NFKC, NFKD (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Java Collator: so sánh theo locale (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Collator.html)
- [Oracle Java Internationalization Overview (JDK 24)](https://docs.oracle.com/en/java/javase/24/intl/internationalization-overview.html)

**Nguyên tắc:** kiểm tra **byte** ở biên lưu/truyền, **code point** khi xử lý Unicode, **grapheme** cho thao tác theo ký tự người dùng nhìn thấy, và **locale** khi hành vi phụ thuộc ngôn ngữ/vùng.