# Kiểm thử supplementary code point, chuỗi rỗng và dữ liệu Unicode

## Mục tiêu

Khi kiểm thử chuỗi trong Java 21, chỉ kiểm tra `String.length()` hoặc so sánh chuỗi trực tiếp thường chưa đủ. Java lưu nội dung `String` theo UTF-16, vì vậy một ký tự Unicode ngoài Basic Multilingual Plane có thể chiếm hai `char` nhưng chỉ là một code point. Dữ liệu nhập từ nhiều nguồn còn có thể khác cách biểu diễn Unicode, chứa dấu kết hợp, khoảng trắng Unicode hoặc chuỗi UTF-16 không hợp lệ.

Bài học này xây dựng bộ kiểm thử cho các trường hợp quan trọng: supplementary code point, chuỗi rỗng và chuỗi chỉ có khoảng trắng, chỉ số theo code point, Unicode normalization, surrogate không ghép cặp và mã hóa/giải mã UTF-8. Các ví dụ dùng JUnit Jupiter và API chuẩn của Java 21.

## 1. Phân biệt `char`, UTF-16 code unit và Unicode code point

Kiểu `char` trong Java biểu diễn một UTF-16 code unit 16 bit. Một code point trong vùng BMP thường được lưu bằng một `char`; một supplementary code point được biểu diễn bằng một cặp surrogate gồm high surrogate và low surrogate.

Ví dụ emoji U+1F600 (GRINNING FACE):

```java
class SupplementaryCodePointExample {
    public static void main(String[] args) {
        int codePoint = 0x1F600;
        String emoji = new String(Character.toChars(codePoint));

        System.out.println(emoji);                              // 😀
        System.out.println(emoji.length());                     // 2 UTF-16 code units
        System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
        System.out.printf("U+%X%n", emoji.codePointAt(0));      // U+1F600
    }
}
```

Các API nên dùng tùy mục đích:

| API | Đơn vị hoặc kết quả | Khi sử dụng |
|---|---|---|
| `length()` | Số UTF-16 code unit | Cần biết độ dài theo đơn vị chỉ số của `String` |
| `charAt(index)` | Một UTF-16 code unit | Cần đọc code unit; không bảo đảm là cả code point |
| `codePointAt(index)` | Một code point tại UTF-16 index | Cần đọc ký tự Unicode tại vị trí hợp lệ |
| `codePointCount(begin, end)` | Số code point trong đoạn UTF-16 | Cần đếm code point thay vì `char` |
| `codePoints()` | `IntStream` các code point | Cần duyệt, lọc hoặc kiểm tra từng code point |
| `offsetByCodePoints(index, offset)` | UTF-16 index sau khi dịch theo số code point | Cần di chuyển qua chuỗi mà không cắt giữa một cặp surrogate |

Các tham số index của `String` vẫn là chỉ số UTF-16, kể cả khi dùng `codePointAt()` hoặc `offsetByCodePoints()`. Kết quả của `offsetByCodePoints()` cũng là UTF-16 index để truyền tiếp cho các API như `substring()`.

## 2. Kiểm thử supplementary code point

Một test nên xác nhận đồng thời số code unit, số code point và giá trị code point thực tế. Không nên chỉ kiểm tra chuỗi hiển thị đúng trên console, vì font và môi trường terminal có thể ảnh hưởng cách hiển thị.

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class SupplementaryCodePointTest {
    @Test
    void emojiIsTwoCodeUnitsButOneCodePoint() {
        int expectedCodePoint = 0x1F600;
        String emoji = new String(Character.toChars(expectedCodePoint));

        assertEquals(2, emoji.length());
        assertEquals(1, emoji.codePointCount(0, emoji.length()));
        assertEquals(expectedCodePoint, emoji.codePointAt(0));
        assertArrayEquals(new int[] { expectedCodePoint },
                emoji.codePoints().toArray());
    }
}
```

`Character.toChars(codePoint)` chuyển một code point hợp lệ thành một hoặc hai `char` tương ứng. Cách tạo chuỗi này làm rõ rằng test đang kiểm tra một code point cụ thể, không phụ thuộc việc editor hoặc encoding của file nguồn có xử lý emoji trực tiếp hay không.

### Kiểm thử duyệt và tính chỉ số theo code point

Giả sử chuỗi có ký tự BMP ở trước và sau emoji. Chỉ số code unit và vị trí code point sẽ khác nhau:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CodePointOffsetTest {
    @Test
    void offsetByCodePointsDoesNotStopInsideSurrogatePair() {
        String emoji = new String(Character.toChars(0x1F680));
        String value = "A" + emoji + "B";

        assertEquals(4, value.length());
        assertEquals(3, value.codePointCount(0, value.length()));

        int indexOfB = value.offsetByCodePoints(0, 2);
        assertEquals(3, indexOfB);
        assertEquals("B", value.substring(indexOfB));
    }
}
```

Trong chuỗi `A + emoji + B`, có bốn UTF-16 code unit nhưng chỉ ba code point. Sau khi đi qua hai code point đầu tiên, index tương ứng là `3`, vì emoji chiếm hai code unit.

Khi cần duyệt toàn bộ code point, có thể dùng `codePoints()`:

```java
class CodePointIterationExample {
    public static void main(String[] args) {
        String value = "A" + new String(Character.toChars(0x1F680)) + "B";

        value.codePoints().forEach(codePoint ->
                System.out.printf("U+%04X%n", codePoint));
    }
}
```

Không dùng `for (int i = 0; i < value.length(); i++)` rồi coi `value.charAt(i)` là một ký tự hoàn chỉnh nếu dữ liệu có thể chứa supplementary code point. Cách duyệt đó đi qua từng code unit và có thể tách cặp surrogate.

## 3. Kiểm thử chuỗi rỗng, chuỗi trắng và `null`

Chuỗi rỗng (`""`) là một đối tượng `String` có độ dài bằng 0. Chuỗi chỉ chứa khoảng trắng không rỗng, nhưng có thể được xem là blank theo `String.isBlank()`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class EmptyAndBlankStringTest {
    @Test
    void emptyStringHasNoCodeUnitsOrCodePoints() {
        String value = "";

        assertTrue(value.isEmpty());
        assertTrue(value.isBlank());
        assertEquals(0, value.length());
        assertEquals(0, value.codePointCount(0, value.length()));
        assertEquals(0, value.codePoints().count());
        assertThrows(StringIndexOutOfBoundsException.class,
                () -> value.charAt(0));
    }

    @Test
    void whitespaceOnlyStringIsBlankButNotEmpty() {
        String value = "\u2003\t\n";

        assertFalse(value.isEmpty());
        assertTrue(value.isBlank());
        assertEquals("", value.strip());
    }
}
```

`isEmpty()` chỉ kiểm tra độ dài có bằng 0 hay không. `isBlank()` trả về `true` nếu chuỗi rỗng hoặc chỉ chứa các code point được `Character.isWhitespace()` xem là khoảng trắng. `strip()` loại bỏ khoảng trắng theo cùng quy tắc Unicode đó ở hai đầu chuỗi.

`null` khác với chuỗi rỗng: `null` không phải một đối tượng `String`, nên gọi `value.isEmpty()` khi `value == null` sẽ ném `NullPointerException`. Nếu API cho phép null, hãy kiểm thử riêng quy tắc nullability thay vì gộp null với empty hoặc blank.

### Chú ý với non-breaking space

Không phải mọi ký tự có hình thức giống dấu cách đều được `Character.isWhitespace()` xem là whitespace. Ví dụ U+00A0 NO-BREAK SPACE là ký tự phân cách nhưng không được `isWhitespace()` nhận diện như khoảng trắng thông thường. Có thể kiểm thử riêng bằng `Character.isSpaceChar()`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class NonBreakingSpaceTest {
    @Test
    void nonBreakingSpaceHasItsOwnWhitespaceSemantics() {
        String value = "\u00A0";

        assertFalse(value.isBlank());
        assertEquals(value, value.strip());
        assertTrue(Character.isSpaceChar(value.codePointAt(0)));
    }
}
```

Quy tắc kiểm tra khoảng trắng nên phản ánh hợp đồng của dữ liệu. Nếu ứng dụng muốn coi non-breaking space là khoảng trắng cần loại bỏ, hãy định nghĩa và kiểm thử quy tắc chuẩn hóa riêng; không giả định `isBlank()` bao phủ mọi ký tự có hình thức là dấu cách.

## 4. Kiểm thử Unicode normalization

Một ký tự nhìn giống nhau có thể có nhiều cách biểu diễn bằng code point. Ví dụ chữ `é` có thể được biểu diễn bằng:

- U+00E9: một code point LATIN SMALL LETTER E WITH ACUTE.
- U+0065 U+0301: chữ `e` theo sau bởi COMBINING ACUTE ACCENT.

Hai chuỗi có thể hiển thị giống nhau nhưng `String.equals()` vẫn trả về `false` nếu chuỗi code point khác nhau. `java.text.Normalizer` cung cấp các dạng chuẩn hóa Unicode để chuyển dữ liệu về dạng thống nhất khi hợp đồng ứng dụng yêu cầu.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

class UnicodeNormalizationTest {
    @Test
    void canonicalEquivalentStringsMatchAfterNfcNormalization() {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        assertNotEquals(composed, decomposed);

        String normalizedComposed =
                Normalizer.normalize(composed, Normalizer.Form.NFC);
        String normalizedDecomposed =
                Normalizer.normalize(decomposed, Normalizer.Form.NFC);

        assertEquals(normalizedComposed, normalizedDecomposed);
    }
}
```

Các dạng chuẩn hóa được cung cấp gồm:

| Dạng | Ý nghĩa tổng quát |
|---|---|
| `NFC` | Phân rã chuẩn tắc rồi kết hợp về dạng chuẩn tổng hợp khi có thể |
| `NFD` | Phân rã chuẩn tắc |
| `NFKC` | Phân rã tương thích rồi kết hợp |
| `NFKD` | Phân rã tương thích |

`NFC` thường được chọn khi cần so sánh các chuỗi tương đương chuẩn tắc. `NFKC` và `NFKD` có thể làm mất các khác biệt mang ý nghĩa tương thích, vì vậy chỉ dùng khi hợp đồng dữ liệu cho phép. Không nên chuẩn hóa tùy tiện mọi chuỗi, đặc biệt với dữ liệu opaque identifier, chữ ký, token hoặc mật khẩu mà quy tắc so sánh đã được xác định riêng.

## 5. Phân biệt code point với grapheme cluster

Một code point không phải lúc nào cũng tương ứng với một ký tự mà người dùng cảm nhận trên màn hình. Chữ có dấu kết hợp có thể gồm nhiều code point nhưng hiển thị như một cụm ký tự. Emoji ghép bằng zero-width joiner cũng có thể gồm nhiều code point nhưng được hiển thị thành một hình tượng.

Ví dụ chữ `é` dạng phân rã:

```java
class CombiningMarkExample {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
    }
}
```

Ví dụ chuỗi emoji gia đình ghép bằng zero-width joiner:

```java
class JoinedEmojiExample {
    public static void main(String[] args) {
        String family = "\uD83D\uDC68\u200D\uD83D\uDC69\u200D\uD83D\uDC67\u200D\uD83D\uDC66";
        System.out.println(family.codePointCount(0, family.length())); // 7
    }
}
```

Hai ví dụ này cho thấy `codePointCount()` đếm code point, không đếm grapheme cluster (cụm ký tự mà người dùng nhận biết). Nếu yêu cầu sản phẩm liên quan đến giới hạn ký tự hiển thị, vị trí con trỏ hoặc xóa một emoji hoàn chỉnh, cần xử lý grapheme boundary theo Unicode Text Segmentation (UAX #29). Không dùng `length()` hoặc `codePointCount()` như số lượng ký tự hiển thị. Có thể sử dụng thư viện Unicode chuyên dụng như ICU4J khi cần hỗ trợ đầy đủ các quy tắc grapheme hiện đại.

## 6. Kiểm thử surrogate pair và chuỗi UTF-16 không hợp lệ

Supplementary code point hợp lệ trong UTF-16 được biểu diễn bằng high surrogate theo sau bởi low surrogate. Một `String` Java vẫn có thể chứa surrogate đơn lẻ không ghép cặp, chẳng hạn khi dữ liệu được tạo thủ công hoặc đến từ nguồn không hợp lệ.

`codePoints()` không tự xác thực chuỗi UTF-16. Nếu gặp surrogate không ghép cặp, stream trả giá trị của code unit đó như một giá trị số. Vì vậy, nếu ứng dụng yêu cầu dữ liệu Unicode well-formed, cần kiểm tra hoặc dùng encoder nghiêm ngặt trước khi gửi dữ liệu ra ngoài.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class UnpairedSurrogateTest {
    @Test
    void unpairedHighSurrogateIsNotSilentlyTreatedAsSupplementaryCharacter() {
        String malformed = "\uD800";

        assertEquals(1, malformed.length());
        assertEquals(1, malformed.codePointCount(0, malformed.length()));
        assertEquals(0xD800, malformed.codePointAt(0));
        assertTrue(Character.isSurrogate(malformed.charAt(0)));
    }
}
```

`Character.isValidCodePoint()` chỉ kiểm tra giá trị có nằm trong miền số code point từ U+0000 đến U+10FFFF. Nó không tự xác nhận một chuỗi UTF-16 có các cặp surrogate hợp lệ, cũng không kiểm tra một chuỗi có tuân thủ quy tắc dữ liệu của ứng dụng hay không. Đối với một chuỗi, cần kiểm tra cấu trúc surrogate hoặc thử mã hóa bằng encoder có chế độ báo lỗi.

## 7. Kiểm thử UTF-8 round-trip

Khi trao đổi dữ liệu giữa hệ thống, UTF-8 là một charset phổ biến. Test round-trip nên xác nhận dữ liệu Unicode sau khi encode và decode vẫn bằng chuỗi ban đầu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class Utf8RoundTripTest {
    @Test
    void supplementaryAndVietnameseTextSurviveUtf8RoundTrip() {
        String emoji = new String(Character.toChars(0x1F600));
        String original = "Tiếng Việt và emoji " + emoji;

        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
        String decoded = StandardCharsets.UTF_8
                .decode(ByteBuffer.wrap(encoded))
                .toString();

        assertEquals(original, decoded);
    }
}
```

Luôn chỉ định charset rõ ràng như `StandardCharsets.UTF_8`; không phụ thuộc charset mặc định của máy chạy test. Test round-trip với dữ liệu hợp lệ xác nhận cả tiếng Việt có dấu lẫn supplementary code point được bảo toàn.

### Báo lỗi khi dữ liệu UTF-8 không hợp lệ

Các API tiện ích chuyển đổi chuỗi/byte thường thay thế dữ liệu malformed bằng ký tự thay thế thay vì báo lỗi. Nếu giao thức yêu cầu từ chối dữ liệu không hợp lệ, cấu hình `CharsetDecoder` hoặc `CharsetEncoder` với `CodingErrorAction.REPORT`.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class StrictUtf8Test {
    @Test
    void decoderReportsMalformedUtf8Bytes() {
        byte[] malformedUtf8 = { (byte) 0xC3, 0x28 };

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(CharacterCodingException.class,
                () -> decoder.decode(ByteBuffer.wrap(malformedUtf8)));
    }

    @Test
    void encoderReportsUnpairedSurrogate() {
        String malformedUtf16 = "\uD800";

        var encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(CharacterCodingException.class,
                () -> encoder.encode(CharBuffer.wrap(malformedUtf16)));
    }
}
```

Test thứ nhất dùng byte sequence không hợp lệ trong UTF-8. Test thứ hai dùng high surrogate không có low surrogate tương ứng. Với chế độ `REPORT`, decoder/encoder ném `CharacterCodingException` thay vì âm thầm thay thế dữ liệu. Trong production, hãy quyết định rõ nên từ chối, ghi log, làm sạch hay thay thế dữ liệu theo hợp đồng giao tiếp; không để hành vi mặc định quyết định chính sách dữ liệu ngoài ý muốn.

## 8. Bộ test tổng hợp cho các trường hợp Unicode quan trọng

Một bộ kiểm thử chuỗi nên bao phủ tối thiểu các nhóm dữ liệu sau:

| Dữ liệu đầu vào | Điều cần kiểm tra | API hoặc kỹ thuật |
|---|---|---|
| `""` | Rỗng, không có code unit/code point | `isEmpty()`, `length()`, `codePointCount()` |
| Chỉ có tab, newline hoặc em space | Blank theo quy tắc whitespace của Java | `isBlank()`, `strip()` |
| Non-breaking space | Khác biệt giữa whitespace và space separator | `isWhitespace()`, `isSpaceChar()` |
| Supplementary code point | Hai UTF-16 code unit nhưng một code point | `toChars()`, `codePointAt()`, `codePointCount()` |
| Chuỗi có dấu kết hợp | Khác biệt biểu diễn nhưng tương đương chuẩn tắc | `Normalizer.normalize()` |
| Emoji có ZWJ | Một grapheme có thể gồm nhiều code point | Grapheme segmentation theo UAX #29 |
| Surrogate không ghép cặp | Phát hiện UTF-16 malformed | `Character.isSurrogate()`, encoder strict |
| Byte sequence UTF-8 sai | Từ chối dữ liệu malformed | `CharsetDecoder` với `REPORT` |
| Tiếng Việt và supplementary code point | Dữ liệu được bảo toàn khi encode/decode | `StandardCharsets.UTF_8` |

Khi viết test, nên tạo dữ liệu bằng escape Unicode hoặc `Character.toChars()` nếu muốn kiểm soát chính xác code point. Có thể dùng ký tự hiển thị trực tiếp trong fixture UTF-8, nhưng cần bảo đảm encoding của source file và pipeline build nhất quán.

## 9. Tổ chức test với JUnit Jupiter

Các ví dụ trên sử dụng `org.junit.jupiter.api.Test` và các assertion của JUnit Jupiter. Trong project, hãy đặt test trong source set kiểm thử, thông thường là `src/test/java`, và dùng cấu hình JUnit Jupiter mà build của dự án đang quản lý.

Một số nguyên tắc giúp test Unicode đáng tin cậy:

1. **Kiểm tra giá trị số:** với supplementary code point, assert mã `int` như `0x1F600`, không chỉ assert chuỗi hiển thị.
2. **Kiểm tra cả hai đơn vị:** xác nhận `length()` và `codePointCount()` khi test surrogate pair.
3. **Tách empty, blank và null:** đây là ba trạng thái khác nhau trong hợp đồng dữ liệu.
4. **Dùng fixture có chủ đích:** tạo chuỗi composed/decomposed, non-breaking space và surrogate malformed bằng escape rõ ràng.
5. **Chỉ định charset:** dùng `StandardCharsets.UTF_8` trong mọi test byte/string.
6. **Kiểm tra lỗi malformed:** cấu hình encoder/decoder với `REPORT` nếu ứng dụng phải từ chối dữ liệu sai định dạng.
7. **Không đồng nhất code point với ký tự hiển thị:** nếu sản phẩm giới hạn ký tự người dùng nhìn thấy, bổ sung test grapheme cluster.

## 10. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao không đủ | Cách kiểm tra phù hợp |
|---|---|---|
| Dùng `length()` để đếm ký tự Unicode | Supplementary code point chiếm hai UTF-16 code unit | Dùng `codePointCount()` nếu cần đếm code point |
| Duyệt chuỗi bằng `charAt()` và coi mỗi `char` là một ký tự | Có thể tách cặp surrogate | Dùng `codePoints()` hoặc `offsetByCodePoints()` |
| Coi `isEmpty()` và `isBlank()` là tương đương | Chuỗi chỉ có whitespace không rỗng nhưng có thể blank | Test riêng cả hai điều kiện |
| Cho rằng mọi dấu cách đều bị `strip()` loại bỏ | `strip()` dựa trên `Character.isWhitespace()` | Kiểm thử riêng ký tự như non-breaking space theo yêu cầu |
| So sánh trực tiếp chuỗi Unicode mà không xét normalization | Chuỗi tương đương chuẩn tắc có thể có dãy code point khác nhau | Chuẩn hóa nhất quán khi hợp đồng dữ liệu yêu cầu |
| Cho rằng `codePoints()` xác thực UTF-16 | Surrogate không ghép cặp vẫn được trả như giá trị code unit | Kiểm tra surrogate hoặc dùng encoder strict |
| Dùng charset mặc định trong test | Kết quả có thể khác giữa môi trường | Chỉ định `StandardCharsets.UTF_8` |
| Chỉ kiểm tra UTF-8 round-trip với ASCII | Không bao phủ tiếng Việt, dấu kết hợp hoặc supplementary code point | Thêm fixture Unicode đa dạng |

## Kết luận

Kiểm thử Unicode trong Java 21 cần phân biệt UTF-16 code unit, code point và grapheme cluster. Với supplementary code point, hãy kiểm tra cả `length()`, `codePointCount()` và giá trị từ `codePointAt()` hoặc `codePoints()`. Kiểm thử riêng chuỗi rỗng, chuỗi blank, null, khoảng trắng Unicode, normalization và surrogate không hợp lệ. Khi trao đổi dữ liệu, chỉ định UTF-8 rõ ràng và dùng encoder/decoder với `CodingErrorAction.REPORT` nếu cần từ chối dữ liệu malformed. Những kiểm tra này giúp chuỗi Unicode được xử lý nhất quán từ đầu vào, xử lý nghiệp vụ đến lúc lưu trữ hoặc truyền qua mạng.
