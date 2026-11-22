# Kiểm thử surrogate pair, surrogate đơn và dấu kết hợp trong Java String

Một chuỗi có thể hiển thị bình thường nhưng chứa các cấu trúc Unicode khiến phép đếm độ dài, cắt chuỗi, mã hóa UTF-8, so sánh và kiểm thử hoạt động ngoài dự đoán. Ba nhóm đầu vào cần kiểm tra riêng là **surrogate pair hợp lệ**, **surrogate đứng đơn** và **dấu kết hợp** (combining mark). Chúng không đồng nghĩa:

- Surrogate pair hợp lệ là cách UTF-16 biểu diễn **một Unicode code point ngoài BMP** bằng **hai đơn vị mã**.
- Surrogate đứng đơn (unpaired surrogate) là một đơn vị mã surrogate thiếu phần ghép tương ứng, tạo thành **chuỗi UTF-16 không hợp lệ** dù Java `String` vẫn có thể chứa nó.
- Dấu kết hợp là Unicode code point hợp lệ có thể kết hợp với ký tự đứng trước để tạo một chữ nhìn thấy; nhiều code point có thể thuộc **cùng một cụm chữ** (*grapheme cluster*).

Mục tiêu của bài là lập được bộ ca kiểm thử phân biệt ba trường hợp, xác nhận hành vi của `String`/`Character`, xử lý đầu vào mã hóa không hợp lệ một cách chủ động và tránh phá vỡ văn bản khi cắt hoặc chuẩn hóa.

## 1. Bốn đơn vị phải phân biệt trước khi viết test

| Đơn vị | API điển hình | Ví dụ với `"A😀B"` |
| --- | --- | ---: |
| **UTF-16 code unit** (đơn vị mã) | `s.length()`, `s.charAt(i)`, chỉ số `substring` | 4 |
| **Unicode code point** | `s.codePointCount(0, s.length())`, `s.codePoints()` | 3 |
| **Grapheme cluster** (cụm chữ hiển thị) | Bộ phân đoạn Unicode phù hợp, ví dụ `BreakIterator` trong phạm vi nó hỗ trợ | 3 trong ví dụ đơn giản này |
| **Byte sau mã hóa** | `s.getBytes(StandardCharsets.UTF_8).length` | 6 byte UTF-8 |

`String.length()` đếm đơn vị mã UTF-16 theo hợp đồng Java, **không đếm code point, cụm chữ hay byte UTF-8**. Java có thể tối ưu cách lưu trữ `String` bên trong JVM, nhưng ý nghĩa của `length()` không đổi.

Một bộ test đáng tin nên quyết định ngay từ đầu yêu cầu đang đặt giới hạn lên đơn vị nào. Ví dụ: “tối đa 20 byte UTF-8” cần đo byte đã mã hóa, “không cắt giữa emoji” đòi hỏi giữ ranh giới cụm chữ, còn “vị trí `charAt`” là chỉ số đơn vị mã UTF-16.

## 2. Surrogate pair hợp lệ

Các giá trị surrogate được chia thành:

- **High surrogate:** `U+D800`–`U+DBFF`.
- **Low surrogate:** `U+DC00`–`U+DFFF`.

Một high surrogate theo ngay sau bởi một low surrogate đúng thứ tự biểu diễn một Unicode code point từ `U+10000` đến `U+10FFFF`. Ví dụ `😀` (`U+1F600`) được viết trong một literal Java là `"\uD83D\uDE00"`. Hai `char` liên tiếp này tạo thành **một** code point.

Đoạn mã minh họa (đặt trong phương thức Java):

~~~java
String s = "A\uD83D\uDE00B";

System.out.println(s.length());                       // 4
System.out.println(s.codePointCount(0, s.length()));   // 3
System.out.println(Character.isHighSurrogate(s.charAt(1))); // true
System.out.println(Character.isLowSurrogate(s.charAt(2)));  // true
System.out.println(Character.isSurrogatePair(
        s.charAt(1), s.charAt(2)));                    // true
System.out.printf("U+%X%n", s.codePointAt(1));         // U+1F600
~~~

Ở đây chỉ số `1` trỏ đến high surrogate và `2` trỏ đến low surrogate. `codePointAt(1)` ghép hai đơn vị mã thành `U+1F600`, còn `charAt(1)` chỉ trả về **một** `char` (high surrogate).

**Lỗi cần bắt khi cắt chuỗi:**

~~~java
String broken = s.substring(1, 2); // chỉ chứa high surrogate
String intact = s.substring(1, 3); // chứa đủ cặp surrogate
~~~

`substring(begin, end)` dùng chỉ số đơn vị mã UTF-16. Vì vậy cả hai câu lệnh đều hợp lệ về mặt chỉ số, nhưng `broken` có UTF-16 không hợp lệ. Nếu cắt tại ranh giới code point, hãy cân nhắc `offsetByCodePoints`:

~~~java
int end = s.offsetByCodePoints(0, 2); // end == 3
String firstTwoCodePoints = s.substring(0, end); // "A😀"
~~~

Đây vẫn là thao tác theo **code point**. Với emoji gồm nhiều code point nối bằng ZWJ, code point boundary chưa chắc trùng ranh giới grapheme cluster.

## 3. Surrogate đứng đơn: `String` vẫn có thể chứa đầu vào sai

Hai chuỗi sau được Java cho phép tạo, dù chúng không đại diện cho chuỗi Unicode scalar value hợp lệ:

~~~java
String highOnly = "\uD83D";
String lowOnly = "\uDE00";
~~~

Cả hai có `length() == 1`. Bất ngờ hơn, `codePointCount(0, 1)` vẫn trả về `1`, và `codePointAt(0)` có thể trả về giá trị surrogate chưa ghép, ví dụ `0xD83D`. **Không được dùng `codePointCount` như bộ xác thực UTF-16.** `Character.isHighSurrogate` và `Character.isLowSurrogate` giúp kiểm tra loại đơn vị mã; cần xác nhận chúng xuất hiện thành cặp đúng thứ tự.

| Đầu vào | UTF-16 hợp lệ? | `length()` | `codePointCount(...)` | Điều đáng kiểm thử |
| --- | --- | ---: | ---: | --- |
| `"\uD83D\uDE00"` | Có | 2 | 1 | Cặp high/low đúng thứ tự |
| `"\uD83D"` | Không | 1 | 1 | High không có low theo sau |
| `"\uDE00"` | Không | 1 | 1 | Low đứng đơn |
| `"\uD83D\uD83D"` | Không | 2 | 2 | High theo sau bởi high |
| `"\uDE00\uD83D"` | Không | 2 | 2 | Low trước high |
| `"X\uD83D\uDE00Y"` | Có | 4 | 3 | Surrogate pair nằm giữa chuỗi |

Một bộ kiểm tra đơn giản duyệt từng `char`: khi thấy high surrogate phải có low surrogate ngay sau, rồi bỏ qua cả cặp; nếu gặp low surrogate khi không đang ghép, đầu vào sai. Chương trình đầy đủ ở phần 6 triển khai chính xác quy tắc này.

### Điều gì xảy ra khi mã hóa UTF-8?

`String.getBytes(StandardCharsets.UTF_8)` có thể **thay thế dữ liệu mã hóa không hợp lệ** bằng chuỗi byte thay thế; đó không phải giải pháp kiểm tra đầu vào nghiêm ngặt và có thể làm mất thông tin. Nếu yêu cầu từ chối surrogate đứng đơn, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để nhận `CharacterCodingException`.

~~~java
StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(CharBuffer.wrap(highOnly)); // báo CharacterCodingException
~~~

Đoạn mã này thuộc ví dụ trong phương thức có import phù hợp ở phần 6. Tránh khẳng định mảng byte thu được từ mã hóa thay thế “vẫn chứa ký tự cũ”: surrogate chưa ghép **không có biểu diễn UTF-8 hợp lệ**. Cần xác định chính sách ứng dụng: từ chối, làm sạch bằng quy tắc đã thống nhất, hoặc thay thế có thông báo.

## 4. Dấu kết hợp và Unicode normalization

Ví dụ chữ `é` có ít nhất hai biểu diễn Unicode phổ biến:

- **Composed/precomposed:** `"\u00E9"` gồm một code point `U+00E9`.
- **Decomposed:** `"e\u0301"` gồm `U+0065` (e) và `U+0301` (dấu sắc kết hợp).

Hai chuỗi thường **hiển thị giống nhau**, nhưng `String.equals` so sánh biểu diễn các đơn vị mã và trả về `false`:

~~~java
String decomposed = "e\u0301";
String composed = "\u00E9";

System.out.println(decomposed.length()); // 2
System.out.println(composed.length());   // 1
System.out.println(decomposed.equals(composed)); // false
System.out.println(Normalizer.normalize(
        decomposed, Normalizer.Form.NFC
).equals(composed)); // true
~~~

Đây là đoạn mã minh họa dùng `java.text.Normalizer`. Khi được mã hóa UTF-8, `decomposed` chiếm 3 byte còn `composed` chiếm 2 byte. Việc chuẩn hóa theo NFC có thể làm thay đổi cả số đơn vị mã và số byte trong khi hình thức hiển thị gần như giữ nguyên.

**Surrogate pair và dấu kết hợp cần các kiểm thử khác nhau.** `"e\u0301"` là UTF-16 hoàn toàn hợp lệ, gồm hai code point nhưng thường tạo thành **một cụm chữ**. Cắt theo `substring(0, 1)` giữ lại `"e"` không tạo UTF-16 sai, nhưng làm **mất dấu sắc**. Ngược lại, cắt giữa high/low surrogate tạo UTF-16 không hợp lệ.

`Normalizer.Form.NFC` thực hiện canonical composition; nếu hệ thống cần canonical decomposition, dùng `NFD`. `NFKC`/`NFKD` còn bao gồm biến đổi tương thích có thể làm đổi ý nghĩa biểu diễn với nhiều ký tự; không dùng tùy tiện. Chuẩn hóa **không phải bước sửa tất cả malformed surrogate**; cần kiểm tra UTF-16 hợp lệ riêng.

Khi chuẩn hóa trước lưu trữ, so sánh, tìm kiếm, tạo checksum hoặc ký số, các bên phải thống nhất **chính xác dạng chuẩn hóa và thời điểm áp dụng**. Không âm thầm normalize sau khi tính hash hoặc chữ ký.

## 5. Ma trận kiểm thử nên có

| Trường hợp | Chuỗi kiểm thử | Cần xác nhận |
| --- | --- | --- |
| ASCII | `"ABC"` | `length` = code point count = số byte UTF-8 |
| Pair hợp lệ | `"A\uD83D\uDE00B"` | 4 units, 3 code points, 6 byte UTF-8; cả cặp hợp lệ |
| Pair bị cắt | `"A\uD83D\uDE00B".substring(1, 2)` | Tạo high surrogate đứng đơn, bộ kiểm tra phải báo sai |
| High đơn | `"\uD83D"` | Chuỗi UTF-16 sai; strict UTF-8 encoder phải từ chối |
| Low đơn | `"\uDE00"` | Chuỗi UTF-16 sai; strict UTF-8 encoder phải từ chối |
| Sai thứ tự | `"\uDE00\uD83D"` | Không ghép được; phát hiện low đứng đơn và high đứng đơn |
| Hai high | `"\uD83D\uD83D"` | Không phải cặp hợp lệ |
| Dấu kết hợp | `"e\u0301"` | 2 code points, một cụm chữ trong tình huống này; 3 byte UTF-8 |
| Chữ dựng sẵn | `"\u00E9"` | 1 code point, 2 byte UTF-8; so với dạng decomposed |
| Chuỗi rỗng | `""` | Không lỗi, các phép đếm bằng 0 |
| Ranh giới đầu/cuối | `"\uD83D\uDE00A"` và `"A\uD83D\uDE00"` | Không sai chỉ số; tránh cắt nửa cặp |
| Emoji nối / variation | Các chuỗi có ZWJ, variation selector hoặc regional indicator | Test phân đoạn **grapheme cluster** riêng, không giả định một code point là một emoji |

Nhóm kiểm thử đầu tiên kiểm tra đúng hợp đồng Java UTF-16. Nhóm thứ hai kiểm tra chính sách xử lý dữ liệu hỏng. Nhóm thứ ba kiểm tra hành vi hiển thị/chuẩn hóa. Khi viết test tự động, nên có cả ví dụ cố định và ca đầu vào được tạo có kiểm soát.

## 6. Chương trình Java 17+ kiểm thử tự động

Tạo file `UnicodeEdgeCasesTest.java`. Đây là chương trình **độc lập, không cần JUnit**: mỗi phép `check` tăng biến đếm và ném `AssertionError` khi một điều kiện sai, nên test vẫn hoạt động ngay cả khi không bật JVM flag `-ea`. Ngoài các phép đếm, chương trình kiểm tra valid/invalid UTF-16, strict UTF-8 encoding, NFC, phân đoạn dấu kết hợp và khả năng round trip.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.BreakIterator;
import java.text.Normalizer;
import java.util.Locale;

public class UnicodeEdgeCasesTest {
    private static int assertions;

    public static void main(String[] args) throws Exception {
        testSurrogatePair();
        testUnpairedSurrogates();
        testCombiningMarks();
        testUtf8RoundTrip();
        System.out.println("PASS: " + assertions + " checks");
    }

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }

    private static boolean wellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= s.length() ||
                        !Character.isLowSurrogate(s.charAt(i + 1))) return false;
                i++;
            } else if (Character.isLowSurrogate(c)) {
                return false;
            }
        }
        return true;
    }

    private static int strictUtf8Size(String s) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(s));
        return buffer.remaining();
    }

    private static void expectMalformed(String s) throws Exception {
        try {
            strictUtf8Size(s);
            throw new AssertionError("Expected malformed UTF-16");
        } catch (CharacterCodingException expected) {
            check(true, "Malformed UTF-16 rejected by encoder");
        }
    }

    private static int graphemes(String s) {
        BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(s);
        int count = 0;
        for (int end = iterator.first(), next = iterator.next();
                next != BreakIterator.DONE;
                end = next, next = iterator.next()) {
            count++;
        }
        return count;
    }

    private static void testSurrogatePair() {
        String text = "A\uD83D\uDE00B";
        check(text.length() == 4, "UTF-16 units");
        check(text.codePointCount(0, text.length()) == 3, "Code points");
        check(Character.isHighSurrogate(text.charAt(1)), "High surrogate");
        check(Character.isLowSurrogate(text.charAt(2)), "Low surrogate");
        check(Character.isSurrogatePair(text.charAt(1), text.charAt(2)), "Pair");
        check(text.codePointAt(1) == 0x1F600, "Combined code point");
        check(text.offsetByCodePoints(0, 2) == 3, "Code point index");
        check(wellFormedUtf16(text), "Valid text");
        check(wellFormedUtf16(text.substring(1, 3)), "Safe substring");
        check(!wellFormedUtf16(text.substring(1, 2)), "Split pair");
    }

    private static void testUnpairedSurrogates() throws Exception {
        String high = "\uD83D";
        String low = "\uDE00";
        check(high.length() == 1 && low.length() == 1, "Single units");
        check(high.codePointCount(0, 1) == 1, "High counted");
        check(low.codePointCount(0, 1) == 1, "Low counted");
        check(high.codePointAt(0) == 0xD83D, "Unpaired high codePointAt");
        check(low.codePointAt(0) == 0xDE00, "Unpaired low codePointAt");
        check(!wellFormedUtf16(high) && !wellFormedUtf16(low), "Invalid UTF-16");
        expectMalformed(high);
        expectMalformed(low);
    }

    private static void testCombiningMarks() {
        String decomposed = "e\u0301";
        String composed = "\u00E9";
        check(decomposed.length() == 2, "Two UTF-16 units");
        check(decomposed.codePointCount(0, decomposed.length()) == 2, "Two points");
        check(composed.length() == 1, "Single precomposed code unit");
        check(!decomposed.equals(composed), "Different code units");
        check(Normalizer.normalize(decomposed, Normalizer.Form.NFC).equals(composed), "NFC");
        check(decomposed.getBytes(StandardCharsets.UTF_8).length == 3, "3 bytes");
        check(composed.getBytes(StandardCharsets.UTF_8).length == 2, "2 bytes");
        check(wellFormedUtf16(decomposed), "Combining well-formed");
        check(graphemes(decomposed) == 1, "One grapheme");
        check(decomposed.substring(0, 1).equals("e"), "Split combining sequence");
    }

    private static void testUtf8RoundTrip() throws Exception {
        String valid = "A\uD83D\uDE00B";
        byte[] bytes = valid.getBytes(StandardCharsets.UTF_8);
        check(bytes.length == 6, "UTF-8 encoded bytes");
        check(new String(bytes, StandardCharsets.UTF_8).equals(valid), "Round trip");
        check(strictUtf8Size(valid) == 6, "Strict encoding");
        String loneHigh = "\uD83D";
        check(!new String(loneHigh.getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8).equals(loneHigh), "Replacement loses malformed unit");
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 UnicodeEdgeCasesTest.java
java UnicodeEdgeCasesTest
~~~

Đầu ra chính xác khi tất cả điều kiện đều đạt:

~~~text
PASS: 32 checks
~~~

**Giải thích cách test hoạt động:**

1. `testSurrogatePair` xác nhận `charAt` trả từng phần high/low, `Character.isSurrogatePair` nhận diện cặp, `codePointAt` trả `U+1F600`, và `substring(1, 2)` gây surrogate đứng đơn. `offsetByCodePoints(0, 2)` trả chỉ số UTF-16 là `3`.
2. `testUnpairedSurrogates` cố ý tạo high và low đơn. `codePointCount` vẫn đếm chúng nhưng `wellFormedUtf16` trả `false`, và encoder UTF-8 cấu hình `REPORT` từ chối.
3. `testCombiningMarks` tách biệt “hợp lệ về mặt Unicode” với “cùng hình thức hiển thị”: `decomposed` và `composed` không `equals`; NFC đưa chúng về cùng dạng, kích thước UTF-8 ban đầu khác nhau.
4. `testUtf8RoundTrip` xác nhận chuỗi có surrogate pair hợp lệ có thể đi qua UTF-8 và giải mã trở lại nguyên vẹn; với high surrogate đứng đơn, đường mã hóa có thay thế không giữ lại chuỗi gốc.

Hàm `wellFormedUtf16` duyệt từng đơn vị mã, **bỏ qua low surrogate khi đã xác thực một high surrogate**, và từ chối low đứng đơn. Phương thức `strictUtf8Size` mã hóa sang UTF-8 bằng `CharsetEncoder`: với dữ liệu hợp lệ, `ByteBuffer.remaining()` là số byte; với dữ liệu hỏng, `CharacterCodingException` cho phép test xác nhận lỗi thay vì bỏ qua.

Hàm `graphemes` minh họa `BreakIterator.getCharacterInstance(Locale.ROOT)` trên **trường hợp đơn giản** `e` + dấu sắc kết hợp. `BreakIterator` phụ thuộc dữ liệu/quy tắc phân đoạn của phiên bản JDK và không mặc nhiên là lời giải đầy đủ cho tất cả chuỗi emoji ZWJ hoặc những quy tắc grapheme Unicode mới nhất. Nếu sản phẩm yêu cầu cắt/đếm cụm chữ cho emoji phức tạp, hãy chọn công cụ phân đoạn đáp ứng phiên bản Unicode và các ca kiểm thử thực tế (ví dụ một thư viện như ICU4J khi phù hợp), rồi kiểm thử chéo với dữ liệu mẫu.

## 7. Kiểm thử chỉ số và ranh giới khi cắt chuỗi

Với chuỗi `"A😀B"`, phép thử hữu ích nhất là tạo **cả kết quả đúng và kết quả hỏng**:

~~~java
String input = "A\uD83D\uDE00B";

String bad = input.substring(1, 2);  // chỉ high surrogate
String good = input.substring(1, 3); // đủ surrogate pair
~~~

Cả hai lời gọi `substring` đều hợp lệ về mặt API và **không tự ném exception**. Lỗi xuất hiện khi dữ liệu hỏng được chuyển mã hoặc xử lý sau này. Với chỉ số do người dùng/chương trình tính toán, cần kiểm tra:

- Không vượt `0..length()` và không đảo thứ tự `begin/end`.
- Không nằm giữa high và low surrogate khi yêu cầu bảo toàn code point.
- Không tách dấu kết hợp khỏi ký tự cơ sở hoặc tách một chuỗi ZWJ khi yêu cầu bảo toàn **cụm chữ hiển thị**.
- Phép round trip `UTF-16 String → UTF-8 bytes → String` giữ nguyên với đầu vào hợp lệ và charset đúng; xử lý có quy tắc với đầu vào không hợp lệ.

Có thể tính ranh giới theo code point bằng `offsetByCodePoints` nhưng cần hiểu rằng **lời gọi này không xác thực surrogate đơn** và cũng không đảm bảo ranh giới grapheme. Chính sách hiển thị và chính sách mã hóa là hai tầng kiểm thử riêng.

## 8. Kiểm thử mã hóa: `getBytes`, encoder nghiêm ngặt và decoder nghiêm ngặt

Đối với văn bản hợp lệ:

~~~java
String input = "A\uD83D\uDE00B";
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);
String restored = new String(utf8, StandardCharsets.UTF_8);

// utf8.length == 6; restored.equals(input) == true
~~~

Mã ví dụ này nằm trong phương thức có import `StandardCharsets`. Nó kiểm tra kết quả theo **byte UTF-8**, không dựa vào `String.length()`.

Khi mã hóa surrogate đứng đơn, `getBytes(StandardCharsets.UTF_8)` thông thường thực hiện thay thế, dẫn đến **không bảo toàn** giá trị ban đầu. Khi yêu cầu dữ liệu Unicode phải hợp lệ, dùng encoder `REPORT` như chương trình ở phần 6.

Tương tự, khi **nhận byte UTF-8 từ ngoài**, `new String(bytes, UTF_8)` có thể thay thế byte sai bằng ký tự thay thế. Để từ chối, sử dụng decoder nghiêm ngặt:

~~~java
String strictDecoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

Đây là đoạn mã trong phương thức đã có `bytes` và các import cần thiết; nếu byte đầu vào hỏng, nó có thể ném `CharacterCodingException`. Không nhầm hai trường hợp: **surrogate đứng đơn trong Java String là UTF-16 hỏng**, còn **byte sequence UTF-8 hỏng** là lỗi tại bước giải mã; cả hai đều cần ca kiểm thử thích hợp tại ranh giới nhận/xuất dữ liệu.

## 9. Kiểm thử tương đương ngữ nghĩa và normalization

`String.equals` so sánh biểu diễn chuỗi, vì vậy:

~~~java
String a = "e\u0301";
String b = "\u00E9";
boolean rawEqual = a.equals(b); // false

String nfcA = Normalizer.normalize(a, Normalizer.Form.NFC);
String nfcB = Normalizer.normalize(b, Normalizer.Form.NFC);
boolean normalizedEqual = nfcA.equals(nfcB); // true
~~~

Đây là đoạn mã minh họa dùng `Normalizer`. Test nên xác định rõ một trong các chính sách:

- **So sánh byte/biểu diễn chính xác:** hai cách viết không tương đương nếu các đơn vị mã khác nhau; ví dụ dữ liệu đã ký hoặc định danh được đặc tả theo byte.
- **So sánh sau chuẩn hóa Unicode:** thống nhất dạng (NFC/NFD/... theo hợp đồng), chuẩn hóa trước khi so sánh và trước các thao tác liên quan như tạo khóa hay checksum.
- **So sánh gần đúng cho tìm kiếm người dùng:** có thể cần nhiều quy tắc thêm ngoài normalization, ví dụ case folding hoặc collator theo locale; không lấy `Normalizer` làm bộ so sánh ngôn ngữ hoàn chỉnh.

Đừng cho rằng hai chuỗi hiển thị giống nhau luôn có cùng `length()`, cùng byte UTF-8 hoặc cùng thứ tự code point. Test cần thể hiện đúng hợp đồng của hệ thống thay vì áp một quy tắc chung cho mọi dữ liệu.

## 10. Những lỗi thường gặp trong test Unicode

**Lỗi 1 — Chỉ chạy test với ASCII.** ASCII khiến `length()`, code point count và số byte UTF-8 thường bằng nhau, nên bỏ sót đa số vấn đề Unicode. Bổ sung emoji, ký tự ngoài Latin-1 và dấu kết hợp.

**Lỗi 2 — Test `codePointCount` để khẳng định “UTF-16 hợp lệ”.** Surrogate đơn vẫn được đếm như một code point theo hành vi của các API duyệt chuỗi Java. Cần bộ kiểm tra cặp surrogate hoặc encoder cấu hình `REPORT`.

**Lỗi 3 — Thấy `substring` không lỗi thì coi văn bản vẫn nguyên vẹn.** Cắt giữa surrogate pair có thể tạo chuỗi hỏng dù lời gọi thành công. Cắt giữa base và dấu kết hợp có thể tạo chuỗi hợp lệ nhưng mất ý nghĩa hiển thị.

**Lỗi 4 — Chuẩn hóa trong test nhưng không chuẩn hóa ở production.** Kết quả test không phản ánh hành vi thật. Xác định rõ normalization đặt ở bước nào và kiểm thử chính đường xử lý đó.

**Lỗi 5 — Coi một code point là một ký tự trên màn hình.** `e\u0301` gồm 2 code point nhưng thường hiện như một chữ. Emoji phức tạp cũng có thể nhiều code point; cần test phân đoạn grapheme cluster khi liên quan đến con trỏ, chiều dài hiển thị hay cắt văn bản.

**Lỗi 6 — Đếm ký tự bằng `String.length()` cho hạn mức byte UTF-8.** Với `"A😀B"`, `length()` là 4 nhưng UTF-8 cần 6 byte. Hãy đo mảng byte thực sự sau khi áp dụng cách mã hóa của giao thức.

**Lỗi 7 — Kiểm thử decoder thay thế mà nghĩ hệ thống đã từ chối byte sai.** Chế độ thay thế và chế độ `REPORT` là hai hợp đồng khác nhau; cần test cả kết quả thành công và trường hợp ném lỗi theo đúng yêu cầu.

**Lỗi 8 — Phụ thuộc font, terminal hoặc ảnh chụp màn hình để kết luận.** Hiển thị phụ thuộc font và renderer. Test các code point, độ dài, byte UTF-8 và normalization bằng giá trị có thể so sánh; chỉ dùng kiểm thử hiển thị bổ sung cho nhu cầu UI.

## 11. Câu hỏi tự kiểm tra

**1.** Với `"\uD83D\uDE00"`, `length()` và `codePointCount` trả bao nhiêu?

**Đáp án:** Lần lượt **2** đơn vị mã UTF-16 và **1** code point (`U+1F600`).

**2.** Với `"\uD83D"`, vì sao `codePointCount(0, 1) == 1` không chứng minh dữ liệu hợp lệ?

**Đáp án:** API có thể tính surrogate đứng đơn như một phần tử khi duyệt; một high surrogate không có low ghép cặp là UTF-16 không hợp lệ. Cần kiểm tra cấu trúc surrogate.

**3.** Vì sao `"e\u0301".substring(0, 1)` khác với việc cắt giữa surrogate pair?

**Đáp án:** `"e"` vẫn là chuỗi Unicode hợp lệ nhưng mất dấu kết hợp; nửa surrogate là **UTF-16 không hợp lệ**. Đúng về encoding và đúng về grapheme là hai tiêu chí riêng.

**4.** Có nên dùng `String.equals` để khẳng định `"e\u0301"` và `"\u00E9"` bằng nhau?

**Đáp án:** Không: `equals` trực tiếp trả `false`. Nếu hợp đồng cho phép canonical equivalence, chuẩn hóa cùng dạng, ví dụ NFC, rồi so sánh.

**5.** Khi ứng dụng từ chối surrogate không ghép cặp trước khi xuất UTF-8, chọn `String.getBytes(UTF_8)` hay `CharsetEncoder` cấu hình `REPORT`?

**Đáp án:** Chọn encoder nghiêm ngặt với `REPORT` để phát hiện lỗi thay vì âm thầm thay thế.

## 12. Checklist áp dụng vào dự án

Khi sửa lỗi ký tự hỏng, độ dài sai, search không tìm ra văn bản hoặc emoji bị cắt, hãy xác định lần lượt: nguồn dữ liệu ở dạng UTF-16 hay byte UTF-8; quy tắc từ chối/thay thế đầu vào sai; đơn vị đo mong muốn (code unit, code point, grapheme hay byte); thời điểm chuẩn hóa; ranh giới cắt; và các ca kiểm thử bằng giá trị Unicode cụ thể. Bộ kiểm thử ở phần 6 có thể chạy bằng JDK 17+, sau đó bổ sung trường hợp đặc trưng của dữ liệu ứng dụng.

Tài liệu tham khảo: [`String` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html), [`Character` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html), [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html), [`Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html), [`BreakIterator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html).