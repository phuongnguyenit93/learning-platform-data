# Kiểm thử dữ liệu đa ngôn ngữ, ký tự kết hợp và ký tự mới

Một chuỗi Java không phải là một dãy “ký tự hiển thị” đơn giản. String lưu văn bản bằng UTF-16 code unit; một ký tự Unicode có thể chiếm một hoặc hai code unit, một grapheme mà người dùng cảm nhận là một ký tự có thể gồm nhiều code point, và cùng một chữ có thể có nhiều cách mã hóa Unicode tương đương. Nếu kiểm thử chỉ dùng String.length(), charAt() hoặc so sánh chuỗi thô, ứng dụng dễ cắt đôi ký tự, đếm sai độ dài, từ chối dữ liệu hợp lệ hoặc xử lý sai tên đa ngôn ngữ.

JDK 26 nâng dữ liệu Unicode mà Java hỗ trợ lên **Unicode 17.0**. Bản nâng cấp này bổ sung 4.803 ký tự, nâng tổng số ký tự được mã hóa lên 159.801, thêm bốn hệ chữ viết mới và cập nhật các thuật toán về hướng văn bản, chuẩn hóa và phân đoạn grapheme. Bài học này xây dựng bộ kiểm thử thực tế cho tiếng Việt, chữ ngoài BMP, dấu kết hợp, emoji, văn bản RTL và các code point mới.

Các API được sử dụng đều là API Java SE tiêu chuẩn, không phải preview và không cần --enable-preview. Hãy chạy bằng JDK 26 hoặc JDK 27 để kiểm tra dữ liệu Unicode 17.0.

## 1. Những thay đổi Unicode quan trọng trong JDK 26

JDK 26 nâng phiên bản Unicode mà Character và các API liên quan sử dụng từ Unicode 16.0 lên Unicode 17.0. Những phần chính được cập nhật:

| Thành phần Java | Nội dung cập nhật |
|---|---|
| java.lang.Character | Dữ liệu Unicode Character Database 17.0: tên, category, script, chữ hoa/thường, chữ số và thuộc tính ký tự |
| java.text.Bidi | Cập nhật theo Unicode Standard Annex #9 về thuật toán văn bản hai chiều |
| java.text.Normalizer | Cập nhật theo Unicode Standard Annex #15 về chuẩn hóa Unicode |
| java.util.regex | Cập nhật dữ liệu và quy tắc Extended Grapheme Cluster theo Unicode Standard Annex #29 |

Unicode 17.0 bổ sung 4.803 ký tự mới, nâng tổng số ký tự được mã hóa lên 159.801. Bốn hệ chữ viết mới là:

- **Sidetic**: hệ chữ cổ được dùng ở Anatolia.
- **Tolong Siki**: hệ chữ hiện đại được cộng đồng Kurukh sử dụng ở vùng đông bắc Ấn Độ.
- **Beria Erfe**: hệ chữ hiện đại được cộng đồng Zaghawa sử dụng ở Trung Phi.
- **Tai Yo**: hệ chữ truyền thống của cộng đồng Tai Yo ở miền Bắc Việt Nam.

Unicode 17.0 cũng bổ sung CJK Unified Ideographs Extension J với 4.298 chữ tượng hình mới và thêm nhiều ký tự ở các block đã tồn tại. Những thay đổi này có ý nghĩa với kiểm tra tên người, địa danh, dữ liệu nghiên cứu, hồ sơ đa ngôn ngữ và nội dung do người dùng nhập.

Lưu ý: hỗ trợ Unicode trong JDK chỉ có nghĩa API nhận biết thuộc tính và xử lý code point theo dữ liệu Unicode mới. Nó không tự cung cấp font có glyph, bàn phím nhập liệu, shaping engine hay khả năng hiển thị chính xác trên mọi hệ điều hành.

## 2. Phân biệt code unit, code point và grapheme cluster

Đây là ba đơn vị khác nhau và mỗi đơn vị phục vụ một mục đích.

| Đơn vị | Ý nghĩa | API Java thường dùng |
|---|---|---|
| UTF-16 code unit | Một giá trị 16 bit trong String hoặc char[] | String.length(), charAt(), chars() |
| Unicode code point | Một giá trị Unicode từ U+0000 đến U+10FFFF | codePointAt(), codePoints(), Character |
| Extended grapheme cluster | Một chuỗi code point được phân đoạn thành một đơn vị gần với ký tự người dùng cảm nhận | BreakIterator, regex \X |

Java lưu String dưới dạng chuỗi UTF-16. Code point trong Basic Multilingual Plane (BMP), từ U+0000 đến U+FFFF, thường chiếm một char. Code point supplementary, lớn hơn U+FFFF, chiếm một cặp surrogate gồm high surrogate và low surrogate.

Một grapheme cluster có thể gồm nhiều code point. Ví dụ:

| Văn bản | UTF-16 code unit | Code point | Grapheme cluster |
|---|---:|---:|---:|
| A | 1 | 1 | 1 |
| ắ (U+1EAF) | 1 | 1 | 1 |
| a + combining breve + combining acute | 3 | 3 | 1 |
| Emoji người phụ nữ + ZWJ + máy tính | 5 | 3 | 1 |
| Cờ Việt Nam gồm hai Regional Indicator | 4 | 2 | 1 |

Vì vậy, String.length() không phải số ký tự mà người dùng nhìn thấy. String.codePointCount() đếm code point nhưng vẫn không đếm grapheme cluster. Nếu cần giới hạn số ký tự trong ô nhập liệu, vị trí con trỏ hoặc cắt chuỗi cho giao diện, hãy chọn đơn vị phù hợp với yêu cầu hiển thị.

## 3. Không duyệt Unicode bằng char đơn lẻ

Một lỗi thường gặp là duyệt từng char rồi gọi Character.isLetter(char). Cách này không xử lý đúng code point supplementary vì mỗi nửa surrogate được nhìn như một giá trị char riêng.

Ví dụ:

~~~java
String text = "A𠀀B"; // U+20000 là một CJK supplementary code point

for (int i = 0; i < text.length(); i++) {
    char ch = text.charAt(i);
    System.out.println(Character.isLetter(ch));
}
~~~

Vòng lặp trên nhìn thấy hai code unit surrogate của U+20000. Không code unit nào tự nó đại diện cho chữ cái supplementary hoàn chỉnh.

Hãy duyệt theo code point:

~~~java
String text = "A𠀀B";

text.codePoints().forEach(codePoint -> {
    System.out.printf(
            "U+%04X %s letter=%s%n",
            codePoint,
            Character.getName(codePoint),
            Character.isLetter(codePoint));
});
~~~

Các overload nhận int của Character hỗ trợ supplementary code point. Với dữ liệu đa ngôn ngữ, ưu tiên:

- Character.isLetter(int codePoint).
- Character.isDigit(int codePoint).
- Character.isWhitespace(int codePoint).
- Character.getType(int codePoint).
- Character.UnicodeScript.of(int codePoint).
- Character.getName(int codePoint).

String.chars() trả từng UTF-16 code unit, không ghép surrogate pair. String.codePoints() ghép các cặp surrogate hợp lệ thành code point; các surrogate đơn lẻ vẫn được đưa ra như giá trị code unit. Nếu dữ liệu phải là Unicode scalar value hợp lệ, cần kiểm tra chuỗi UTF-16 không chứa surrogate đơn lẻ.

## 4. Kiểm thử độ dài bằng cả ba đơn vị

Ví dụ sau tạo một chuỗi có tiếng Việt, emoji ZWJ, emoji modifier và cờ quốc gia:

~~~java
import java.text.BreakIterator;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeLengthCheck {

    static int countGraphemesWithBreakIterator(String text) {
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.ROOT);

        iterator.setText(text);

        int count = 0;
        iterator.first();

        while (iterator.next() != BreakIterator.DONE) {
            count++;
        }

        return count;
    }

    static int countGraphemesWithRegex(String text) {
        Matcher matcher = Pattern.compile("\\X").matcher(text);

        int count = 0;
        while (matcher.find()) {
            count++;
        }

        return count;
    }

    public static void main(String[] args) {
        String text =
                "\u1EAF"                       // ắ
                + "\uD83D\uDC69\u200D\uD83D\uDCBB" // woman technologist
                + "\uD83D\uDC4D\uD83C\uDFFD"       // thumbs up, medium skin tone
                + "\uD83C\uDDFB\uD83C\uDDF3";      // flag Vietnam

        System.out.println("UTF-16 units: " + text.length());
        System.out.println(
                "Code points: " +
                text.codePointCount(0, text.length()));

        System.out.println(
                "Graphemes (BreakIterator): " +
                countGraphemesWithBreakIterator(text));

        System.out.println(
                "Graphemes (regex): " +
                countGraphemesWithRegex(text));
    }
}
~~~

Với các chuỗi mẫu trong ví dụ, kết quả mong đợi là:

~~~text
UTF-16 units: 14
Code points: 8
Graphemes (BreakIterator): 4
Graphemes (regex): 4
~~~

BreakIterator.getCharacterInstance() phân đoạn ranh giới ký tự theo Extended Grapheme Cluster trong implementation mặc định của JDK 26. Regex matcher \X cũng khớp một Extended Grapheme Cluster. Cả hai dựa trên quy tắc UAX #29 được cập nhật theo Unicode 17.0 trong JDK 26.

Không dùng codePointCount() thay cho grapheme count khi kiểm tra độ dài mà người dùng cảm nhận. Một emoji gia đình hoặc một chữ có nhiều dấu kết hợp có thể là một grapheme nhưng chứa nhiều code point.

## 5. Dùng BreakIterator để cắt chuỗi an toàn

Khi cắt chuỗi cho giao diện, không lấy một số char cố định rồi substring() nếu điểm cắt có thể rơi vào giữa surrogate pair hoặc giữa grapheme cluster.

Ví dụ cắt tối đa ba grapheme:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

static String firstGraphemes(String text, int maximum) {
    if (maximum < 0) {
        throw new IllegalArgumentException("maximum must be non-negative");
    }

    BreakIterator iterator =
            BreakIterator.getCharacterInstance(Locale.ROOT);

    iterator.setText(text);

    int boundary = iterator.first();

    for (int count = 0; count < maximum; count++) {
        int next = iterator.next();

        if (next == BreakIterator.DONE) {
            return text;
        }

        boundary = next;
    }

    return text.substring(0, boundary);
}
~~~

Phương thức này trả về chuỗi không vượt quá số grapheme cluster yêu cầu. Nếu text ngắn hơn giới hạn, nó trả về toàn bộ text.

Đối với giới hạn dữ liệu lưu trữ, vẫn phải kiểm tra thêm số byte sau khi encode UTF-8 và giới hạn cột database. Một giới hạn 20 grapheme không có nghĩa dữ liệu chiếm tối đa 20 byte hoặc 20 UTF-16 code unit.

## 6. Chuẩn hóa ký tự kết hợp bằng NFC và NFD

Một chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng chữ cái cơ sở cộng với combining mark. Hai chuỗi có thể hiển thị giống nhau nhưng String.equals() trả về false vì dãy code point khác nhau.

Ví dụ tiếng Việt:

~~~java
import java.text.Normalizer;

String composed = "\u1EAF";       // ắ: một code point
String decomposed = "a\u0306\u0301"; // a + breve + acute

System.out.println(composed.equals(decomposed)); // false

String composedNfc =
        Normalizer.normalize(composed, Normalizer.Form.NFC);

String decomposedNfc =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(composedNfc.equals(decomposedNfc)); // true
~~~

NFC thực hiện canonical composition, ghép các chuỗi có thể kết hợp thành dạng dựng sẵn. NFD thực hiện canonical decomposition, phân rã ký tự thành các thành phần tương đương.

Bốn dạng chuẩn hóa:

| Form | Hành vi | Trường hợp thường gặp |
|---|---|---|
| NFC | Canonical decomposition rồi composition | Lưu trữ và so sánh văn bản theo dạng dựng sẵn nhất quán |
| NFD | Canonical decomposition | Xử lý hoặc phân tích dấu kết hợp |
| NFKC | Compatibility decomposition rồi composition | Chuẩn hóa tương thích cho một số quy trình tìm kiếm/identifier |
| NFKD | Compatibility decomposition | Phân tích dạng tương thích |

Ví dụ kiểm tra chuẩn hóa:

~~~java
String input = "a\u0306\u0301";

if (!Normalizer.isNormalized(input, Normalizer.Form.NFC)) {
    input = Normalizer.normalize(input, Normalizer.Form.NFC);
}
~~~

NFC/NFD xử lý tương đương canonical. NFKC/NFKD còn có thể làm mất một số khác biệt tương thích như dạng ligature hoặc full-width. Không áp dụng NFKC cho toàn bộ văn bản hiển thị một cách tùy tiện vì có thể làm thay đổi phân biệt mà ứng dụng cần giữ.

Chọn một chính sách chuẩn hóa nhất quán cho dữ liệu cần so sánh, tìm kiếm hoặc làm khóa. Nếu thay đổi chính sách của dữ liệu đã lưu, phải lập kế hoạch migration và kiểm tra xung đột sau chuẩn hóa.

## 7. Chuẩn hóa không thay thế kiểm tra bảo mật

Hai chuỗi nhìn gần giống nhau không nhất thiết là cùng một chuỗi Unicode. Ví dụ, chữ Latin a và chữ Cyrillic а là hai code point khác nhau; NFC không biến chúng thành một ký tự.

Với username, domain nội bộ, tên tài khoản hoặc identifier có ý nghĩa bảo mật:

- Quy định rõ các script được phép.
- Cân nhắc chính sách một script hoặc tập script được phép kết hợp.
- Kiểm tra ký tự vô hình, ký tự điều khiển và ký tự định hướng hai chiều.
- Dùng Unicode Security Mechanisms/UTS #39 để phát hiện confusable và rủi ro identifier.
- Không coi Character.isUnicodeIdentifierStart() hoặc regex \p{L} là một bộ lọc bảo mật hoàn chỉnh.
- Không dùng việc hai chuỗi có cùng NFC để kết luận chúng an toàn hoặc cùng một danh tính.

Unicode 17.0 cập nhật dữ liệu Identifier_Type và khuyến nghị identifier trong UTS #39. Nếu ứng dụng cần kiểm soát tên đăng nhập đa ngôn ngữ, hãy dùng chính sách bảo mật phù hợp với sản phẩm thay vì tự xây dựng danh sách ký tự dựa trên một vài block Unicode.

## 8. Kiểm tra ký tự mới của Unicode 17.0

JDK 26 cập nhật Character để nhận biết các ký tự Unicode 17.0. Bốn block script mới có phạm vi code point:

| Script | Phạm vi block |
|---|---|
| Sidetic | U+10940–U+1095F |
| Tolong Siki | U+11DB0–U+11DEF |
| Beria Erfe | U+16EA0–U+16EDF |
| Tai Yo | U+1E6C0–U+1E6FF |

Không phải mọi vị trí trong một block đều đã được gán ký tự. Hãy kiểm tra Character.isDefined(codePoint), Character.getName(codePoint) và Character.UnicodeScript.of(codePoint), thay vì giả định mọi giá trị trong phạm vi đều là ký tự đã được gán.

~~~java
import java.util.stream.IntStream;

public class Unicode17ScriptCheck {

    record ScriptRange(String name, int start, int end) {}

    static void inspect(ScriptRange range) {
        int firstAssigned = IntStream.rangeClosed(
                        range.start(), range.end())
                .filter(Character::isDefined)
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No assigned code point in " + range.name()));

        System.out.printf(
                "%s: U+%X, %s, script=%s%n",
                range.name(),
                firstAssigned,
                Character.getName(firstAssigned),
                Character.UnicodeScript.of(firstAssigned));
    }

    public static void main(String[] args) {
        inspect(new ScriptRange("Sidetic", 0x10940, 0x1095F));
        inspect(new ScriptRange("Tolong Siki", 0x11DB0, 0x11DEF));
        inspect(new ScriptRange("Beria Erfe", 0x16EA0, 0x16EDF));
        inspect(new ScriptRange("Tai Yo", 0x1E6C0, 0x1E6FF));
    }
}
~~~

Bộ kiểm thử này xác nhận JDK nhận biết ít nhất một code point đã gán trong từng block và trả về tên cùng script tương ứng. Khi cần kiểm tra chính xác toàn bộ dữ liệu, đối chiếu với Unicode Character Database 17.0 thay vì chỉ kiểm tra một code point.

Unicode 17.0 còn bổ sung CJK Unified Ideographs Extension J. Với các ký tự CJK supplementary, tiếp tục dùng API nhận int và String.codePoints(); không quay lại cách duyệt char đơn lẻ.

## 9. Kiểm tra ký tự mới không đồng nghĩa kiểm tra hiển thị

Một code point có thể được JDK nhận biết nhưng font trên máy người dùng chưa có glyph tương ứng. Khi đó Character.isDefined() có thể trả true nhưng giao diện vẫn hiển thị ô vuông hoặc glyph thay thế.

Tách kiểm thử thành ba lớp:

1. **Dữ liệu Unicode:** Character nhận diện code point, tên, category và script.
2. **Xử lý văn bản:** normalize, phân đoạn grapheme, regex, Bidi và encode/decode hoạt động đúng.
3. **Hiển thị:** font có glyph, shaping đúng, thứ tự RTL đúng, dấu kết hợp đặt đúng và hệ điều hành có hỗ trợ nhập liệu.

Đặc biệt với Tai Yo, Unicode xác nhận script đã được mã hóa, nhưng việc hiển thị phụ thuộc font có glyph và shaping phù hợp. Không kết luận ứng dụng hỗ trợ Tai Yo hoàn chỉnh chỉ vì Character.UnicodeScript nhận diện được code point.

## 10. Kiểm thử UTF-8 và dữ liệu byte không hợp lệ

Khi nhận dữ liệu từ HTTP, file, database hoặc message broker, cần kiểm tra cả encoding ở ranh giới byte. UTF-8 có thể biểu diễn toàn bộ Unicode scalar values, nhưng một chuỗi byte không hợp lệ không phải là văn bản UTF-8 hợp lệ.

Khi cần từ chối dữ liệu sai định dạng, dùng CharsetDecoder với CodingErrorAction.REPORT:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {

    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Nếu ứng dụng chấp nhận thay thế byte sai bằng U+FFFD REPLACEMENT CHARACTER, đó là quyết định chính sách dữ liệu khác với từ chối. Không âm thầm bỏ byte lỗi khi dữ liệu dùng làm khóa, chữ ký, identifier hoặc dữ liệu tài chính.

Kiểm tra encode/decode round-trip:

~~~java
import java.nio.charset.StandardCharsets;

String original = "Tiếng Việt: ắ, ộ, ữ; Tai Yo: test";
byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
String decoded = decodeUtf8Strict(bytes);

if (!original.equals(decoded)) {
    throw new AssertionError("UTF-8 round-trip failed");
}
~~~

Đối với byte đầu vào từ bên ngoài, kiểm tra:

- Content-Type và charset của giao thức.
- Charset thực tế của file hoặc stream.
- Byte sequence UTF-8 có hợp lệ không.
- Dữ liệu có bị cắt giữa một multi-byte sequence không.
- Có bước chuyển mã trung gian làm mất dữ liệu hay không.
- Database, driver và cột lưu trữ có hỗ trợ toàn bộ ký tự cần dùng không.

Không giả định mọi nguồn byte đều là UTF-8 chỉ vì phần lớn hệ thống hiện đại sử dụng UTF-8.

## 11. Phát hiện surrogate đơn lẻ trong String

Java String có thể chứa một high surrogate không có low surrogate đi kèm hoặc low surrogate không có high surrogate đứng trước. Những giá trị này không tạo thành Unicode scalar value hợp lệ.

Có thể kiểm tra bằng CharsetEncoder cấu hình REPORT:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static void validateUtf16ForUtf8(String text)
        throws CharacterCodingException {

    StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(text));
}
~~~

Nếu text có surrogate đơn lẻ, encoder báo lỗi malformed input. Cách này hữu ích khi dữ liệu được tạo từ API char[], ghép chuỗi, parser hoặc nguồn không đảm bảo well-formed UTF-16.

Không coi String.codePoints() là phép xác thực scalar value. API này ghép cặp surrogate hợp lệ; surrogate đơn lẻ vẫn được đưa ra dưới dạng giá trị int tương ứng với code unit.

## 12. Kiểm thử văn bản RTL và thuật toán Bidi

Tiếng Ả Rập và tiếng Hebrew có hướng hiển thị từ phải sang trái. Một đoạn văn có thể trộn ký tự RTL, chữ Latin, số và dấu câu. Thứ tự lưu trữ trong String là logical order; thứ tự hiển thị do thuật toán Bidirectional xác định.

Không tự đảo ngược String để hiển thị RTL. Việc đảo chuỗi có thể phá surrogate pair, combining mark, emoji ZWJ và logic của thuật toán Bidi.

JDK 26 cập nhật java.text.Bidi theo Unicode 17.0/UAX #9. Khi kiểm thử:

- Dùng chuỗi có cả Arabic/Hebrew, Latin và chữ số.
- Kiểm tra layout trong thành phần UI thực tế.
- Kiểm tra dấu ngoặc, dấu câu và số trong đoạn RTL.
- Kiểm tra nội dung copy/paste và thứ tự logical khi lưu.
- Kiểm tra ký tự điều khiển hướng văn bản và chính sách bảo vệ dữ liệu.

Có thể dùng Bidi để kiểm tra các run hướng văn bản:

~~~java
import java.text.Bidi;

String text = "Order رقم 123 - ABC";

Bidi bidi = new Bidi(
        text,
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

System.out.println("Mixed: " + bidi.isMixed());
System.out.println("Runs: " + bidi.getRunCount());
~~~

Đây là kiểm tra cấu trúc hướng văn bản. Nó không thay thế kiểm thử render bằng font và component UI mà ứng dụng thực sự sử dụng.

## 13. Regex Unicode: property, grapheme và word class

Java regex hỗ trợ Unicode property như:

- \p{L}: nhóm chữ cái.
- \p{M}: nhóm combining mark.
- \p{N}: nhóm số.
- \p{IsLatin}: ký tự thuộc script Latin.
- \p{IsArabic}: ký tự thuộc script Arabic.
- \X: một Extended Grapheme Cluster.
- \b{g}: ranh giới Extended Grapheme Cluster.

Ví dụ đếm chữ cái Unicode và combining mark:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String text = "Tiếng Việt ắ 𠀀";

Matcher matcher =
        Pattern.compile("[\\p{L}\\p{M}]+").matcher(text);

while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Lưu ý: lớp ký tự viết tắt như \w mặc định có phạm vi ASCII nếu không bật Pattern.UNICODE_CHARACTER_CLASS. Nếu muốn hành vi Unicode cho \w, \d, \s và các POSIX class tương ứng, bật flag đó hoặc dùng Unicode property tường minh như \p{L}, \p{N}.

Ví dụ:

~~~java
Pattern unicodeWord = Pattern.compile(
        "\\w+",
        Pattern.UNICODE_CHARACTER_CLASS);

Pattern explicitLettersAndMarks =
        Pattern.compile("[\\p{L}\\p{M}\\p{N}_]+");
~~~

Không dùng regex \w đơn giản làm bộ kiểm tra tên người đa ngôn ngữ. Tên có dấu kết hợp, dấu nối, apostrophe, khoảng trắng và nhiều script cần một chính sách sản phẩm rõ ràng.

## 14. So sánh, tìm kiếm và sắp xếp văn bản theo locale

String.equals() so sánh chuỗi code unit chính xác. String.compareTo() so sánh theo thứ tự từ điển của UTF-16 code unit; hai API này không thực hiện chuẩn hóa hoặc sắp xếp theo ngôn ngữ.

Nếu cần so sánh văn bản theo quy tắc ngôn ngữ, dùng Collator với locale phù hợp:

~~~java
import java.text.Collator;
import java.util.Locale;

Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi"));

int result = vietnamese.compare("a", "á");
~~~

Quy tắc so sánh phụ thuộc locale và strength của Collator. Với danh sách lớn được sắp xếp nhiều lần, có thể tạo CollationKey theo cùng một Collator để tối ưu so sánh, nhưng key phải được tạo lại khi thay đổi locale hoặc cấu hình collation.

Tách rõ các phép toán:

| Nhu cầu | Cách xử lý |
|---|---|
| So sánh chính xác chuỗi | String.equals() |
| So sánh văn bản theo canonical equivalence | Chuẩn hóa cùng form, thường là NFC, rồi so sánh |
| Sắp xếp theo quy tắc ngôn ngữ | Collator với Locale phù hợp |
| Tìm kiếm không phân biệt hoa/thường | Quy định locale và chính sách case mapping rõ ràng |
| Phát hiện ký tự giả mạo/confusable | Chính sách Unicode Security Mechanisms/UTS #39 |

Không dùng một phép lower-case chung cho mọi ngôn ngữ để thay thế Unicode case folding hoặc collation. Locale có thể ảnh hưởng đến chuyển đổi chữ hoa/thường; ví dụ một số chữ cái có quy tắc đặc biệt theo ngôn ngữ.

## 15. Bộ dữ liệu kiểm thử đa ngôn ngữ nên có gì?

Một bộ kiểm thử Unicode không nên chỉ có ASCII và vài chữ có dấu. Hãy lưu fixture có chủ đích để bao phủ các loại dữ liệu sau:

| Nhóm dữ liệu | Ví dụ kiểm thử | Điều cần xác nhận |
|---|---|---|
| Tiếng Việt dựng sẵn | ắ, ộ, ữ, ấ | Đọc, ghi, normalize và hiển thị đúng |
| Tiếng Việt dấu kết hợp | a + U+0306 + U+0301 | NFC/NFD, grapheme count và cursor boundary |
| Chữ supplementary | CJK U+20000 hoặc code point ngoài BMP khác | Duyệt code point, không tách surrogate |
| Emoji modifier | 👍🏽 | Một grapheme cluster |
| Emoji ZWJ | 👩‍💻 | Không cắt giữa các code point trong sequence |
| Cờ quốc gia | 🇻🇳 | Hai Regional Indicator được phân đoạn đúng |
| Script RTL | Arabic và Hebrew | Bidi, dấu câu, số và thứ tự logical |
| Script kết hợp | Devanagari hoặc Thai | Combining mark và shaping |
| Unicode 17 mới | Sidetic, Tolong Siki, Beria Erfe, Tai Yo | Character data, regex property và font |
| CJK mới | Extension J | Code point supplementary và font fallback |
| Chuỗi lỗi | UTF-8 malformed hoặc surrogate đơn lẻ | Decoder/encoder từ chối theo chính sách |
| Chuỗi giả mạo | Latin/Cyrillic look-alike, dấu định hướng | Chính sách identifier và security |

Với mỗi fixture, lưu kỳ vọng rõ ràng: số code unit, số code point, số grapheme cluster, kết quả normalization, script, category, byte length UTF-8 và khả năng render. Không chỉ lưu ảnh chụp màn hình vì ảnh không cho biết chuỗi có cùng code point hay không.

## 16. Kiểm thử end-to-end qua toàn bộ hệ thống

Unicode lỗi thường xuất hiện ở ranh giới giữa các thành phần, không chỉ trong Java String. Hãy kiểm tra theo đường đi thực tế:

~~~text
Input method / Browser / File
          |
          v
      UTF-8 bytes
          |
          v
 CharsetDecoder + validation
          |
          v
       Java String
          |
          +--> Code point validation
          |
          +--> NFC/NFD policy
          |
          +--> Grapheme segmentation
          |
          +--> Bidi / regex / locale
          |
          v
    JDBC / JSON / HTTP
          |
          v
    Database / Message Store
          |
          v
       Read back
          |
          v
   Decode + render + compare
~~~

Các điểm kiểm thử:

1. Nhập văn bản bằng bàn phím hoặc paste từ trình duyệt.
2. Gửi qua HTTP với charset xác định.
3. Parse JSON/form body và xác nhận không mất dấu.
4. Validate theo code point/grapheme đúng yêu cầu.
5. Normalize ở đúng tầng và nhất quán.
6. Ghi qua JDBC driver vào cột hỗ trợ Unicode.
7. Đọc lại và so sánh byte/code point sau decode.
8. Hiển thị bằng font thực tế trên Windows, macOS, Linux và mobile nếu sản phẩm hỗ trợ.
9. Kiểm tra copy/paste, tìm kiếm, sắp xếp và phân trang.
10. Kiểm tra log, tracing và export để không làm mất hoặc biến đổi ký tự.

Không dựa vào một unit test Character để kết luận database hoặc frontend hỗ trợ Unicode 17. Hãy kiểm tra mọi ranh giới trong kiến trúc.

## 17. Khác biệt Unicode giữa các JDK

| JDK | Unicode Character Database |
|---|---|
| JDK 25 | Unicode 16.0 |
| JDK 26 | Unicode 17.0 |
| JDK 27 | Unicode 17.0 |

Khi nâng từ JDK 25 lên JDK 26, những code point mới được gán trong Unicode 17 có thể thay đổi kết quả của Character.isDefined(), Character.getType(), Character.isLetter(), regex property và các phép xử lý Unicode liên quan.

JDK 27 tiếp tục sử dụng Unicode 17.0 theo tài liệu API hiện hành. Không giả định mỗi bản JDK mới đều thay đổi phiên bản Unicode.

Nếu kết quả validation, phân loại hoặc index phụ thuộc vào Unicode property, hãy đưa JDK version vào ma trận tương thích và chạy lại bộ test khi nâng cấp. Với hệ thống phân tán chạy nhiều phiên bản JDK, các node có thể phân loại code point mới khác nhau nếu chúng dùng dữ liệu Unicode khác phiên bản.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| String.length() lớn hơn số ký tự nhìn thấy | Đang đếm UTF-16 code unit | Dùng codePointCount hoặc grapheme segmentation tùy yêu cầu |
| Ký tự ngoài BMP bị tách đôi | Duyệt từng char | Dùng codePoints() và Character API nhận int |
| Tên hiển thị giống nhau nhưng equals() là false | Hai chuỗi có dạng composed/decomposed khác nhau | Chuẩn hóa cùng form nếu nghiệp vụ yêu cầu canonical equality |
| Cắt mất dấu hoặc emoji | Cắt theo char index giữa grapheme cluster | Dùng BreakIterator hoặc regex \X |
| Ký tự mới hiện thành ô vuông | Font hoặc shaping engine chưa có glyph | Kiểm tra font fallback và môi trường render |
| Một số code point bị coi là UNASSIGNED | Runtime dùng dữ liệu Unicode cũ hoặc code point chưa được gán | Xác định JDK và Unicode version; kiểm tra Character.getName() |
| Regex không nhận chữ Unicode | Dùng \w mặc định ASCII | Dùng Pattern.UNICODE_CHARACTER_CLASS hoặc property như \p{L} |
| Văn bản RTL bị đảo hoặc dấu câu sai | Tự reverse String hoặc không chạy Bidi/layout đúng | Giữ logical order và dùng thành phần hỗ trợ Bidi |
| UTF-8 round-trip mất dữ liệu | Charset sai hoặc byte sequence không hợp lệ | Dùng UTF-8 rõ ràng và decoder REPORT khi cần từ chối dữ liệu lỗi |
| Identifier trông giống nhau nhưng khác code point | Confusable giữa script hoặc ký tự vô hình | Áp dụng chính sách UTS #39 và script restriction |
| Dữ liệu lớn bị cắt khi lưu DB | Giới hạn cột tính theo byte/code unit khác grapheme | Kiểm tra byte length, cột và charset thực tế |

## 19. Bài thực hành tổng hợp

Thực hiện bằng JDK 26 hoặc JDK 27:

1. Tạo fixture tiếng Việt gồm dạng NFC và NFD của ắ, ộ, ữ; kiểm tra equals trước và sau normalize.
2. Tạo chuỗi có CJK supplementary code point; so sánh String.length(), codePointCount() và kết quả codePoints().
3. Dùng Character.isLetter(int), getType(int), getName(int) và UnicodeScript.of(int) để kiểm tra ký tự ngoài BMP.
4. Đếm grapheme cluster của chuỗi chứa combining marks, emoji ZWJ, skin tone modifier và cờ Việt Nam bằng BreakIterator.
5. Lặp lại phép đếm bằng regex \X và so sánh kết quả.
6. Cắt chuỗi theo grapheme cluster; xác nhận không cắt giữa dấu kết hợp hoặc emoji sequence.
7. Dùng Normalizer NFC/NFD/NFKC/NFKD trên các fixture phù hợp; ghi rõ khác biệt kết quả.
8. Kiểm tra code point trong bốn block script mới của Unicode 17 bằng Character.isDefined(), getName() và UnicodeScript.of().
9. Decode một UTF-8 byte sequence hợp lệ và một byte sequence malformed với CodingErrorAction.REPORT.
10. Kiểm tra String có surrogate đơn lẻ bằng CharsetEncoder REPORT.
11. Kiểm tra Arabic/Hebrew trộn với Latin và số bằng Bidi và UI thực tế.
12. Kiểm tra font có glyph cho Tai Yo, Sidetic, Tolong Siki, Beria Erfe và CJK Extension J.
13. Chạy end-to-end từ HTTP input qua Java, JDBC, database và đọc lại.
14. Chạy cùng bộ test trên JDK 25 và JDK 26 để xác nhận thay đổi Unicode 16.0 lên 17.0; sau đó kiểm tra JDK 27.

**Tiêu chí hoàn thành:** phân biệt code unit, code point và grapheme cluster; duyệt supplementary characters đúng cách; chuẩn hóa tiếng Việt composed/decomposed; phân đoạn combining sequence và emoji; nhận diện ký tự Unicode 17; phát hiện malformed UTF-8 và surrogate đơn lẻ; hiểu Bidi, regex Unicode và locale collation; phân biệt dữ liệu Unicode với khả năng render của font; kiểm thử end-to-end qua database và HTTP; xác định tác động khi nâng từ JDK 25 lên JDK 26/27.

## 20. Tài liệu tham khảo chính thức

- [JDK 26 Release Notes – Support for Unicode 17.0](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — cập nhật Character, Bidi, Normalizer và regex theo Unicode 17.0.
- [Java 26 Character API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html) — Unicode version, UTF-16 representation, code point và các thuộc tính ký tự.
- [Java 26 String API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html) — length, codePointCount, chars và codePoints.
- [Java 26 BreakIterator API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/BreakIterator.html) — phân đoạn character boundary theo Extended Grapheme Cluster.
- [Java 26 Pattern API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html) — Unicode property, \X, \b{g} và UNICODE_CHARACTER_CLASS.
- [Java 26 Normalizer API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html) — các dạng NFC, NFD, NFKC và NFKD.
- [Java 26 Bidi API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Bidi.html) — xử lý hướng văn bản hai chiều.
- [Java 26 CharsetDecoder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html) — decode byte sequence và xử lý malformed/unmappable input.
- [Unicode 17.0.0](https://www.unicode.org/versions/Unicode17.0.0/) — ký tự mới, block mới, script mới và thay đổi Unicode Standard Annex.
- [Unicode Standard Annex #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/) — định nghĩa các dạng chuẩn hóa Unicode.
- [Unicode Standard Annex #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/) — quy tắc grapheme, word và sentence boundary.
- [Unicode Standard Annex #9: Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/) — thuật toán hiển thị văn bản hỗn hợp RTL/LTR.
- [Unicode Technical Standard #39: Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/) — identifier profile, mixed-script và confusable detection.
- [Java 27 Character API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html) — xác nhận JDK 27 tiếp tục dùng Unicode 17.0.

Unicode 17.0 mở rộng khả năng nhận biết ký tự và cập nhật phân đoạn văn bản trong JDK 26. Để xử lý dữ liệu đa ngôn ngữ chính xác, hãy kiểm tra đúng đơn vị dữ liệu ở từng bước: byte, UTF-16 code unit, code point, grapheme cluster và glyph hiển thị.
