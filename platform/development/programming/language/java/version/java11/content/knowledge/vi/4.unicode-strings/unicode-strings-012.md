# Kiểm thử tiếng Việt, ký tự bổ sung và khoảng trắng đặc biệt trong Java 11

## Mục tiêu học tập

Khi xử lý chuỗi Unicode, kiểm thử thành công với `"hello"` hoặc `"abc"` chưa đủ. Một trường văn bản hiển thị đúng trên màn hình có thể mang nhiều chuỗi mã Unicode khác nhau; một ký tự biểu tượng có thể chiếm hai đơn vị `char` trong Java; một dấu cách không ngắt dòng có thể làm `isBlank()` trả về `false`. Những khác biệt này ảnh hưởng đến so sánh, tìm kiếm, kiểm tra dữ liệu, cắt chuỗi và lưu/đọc dữ liệu.

Sau bài học, bạn sẽ biết cách xây dựng **bộ kiểm thử hồi quy có kết quả xác định**, bao phủ ba nhóm đầu vào:

1. **Tiếng Việt có dấu:** ký tự tạo sẵn (precomposed), chuỗi dấu kết hợp (combining marks), so sánh trước/sau chuẩn hóa Unicode.
2. **Ký tự bổ sung (supplementary code points):** khác biệt giữa UTF-16 `char`, Unicode code point, và ký tự người dùng nhìn thấy; biên của surrogate pair.
3. **Khoảng trắng đặc biệt:** khoảng trắng Java, non-breaking spaces, zero-width characters, và khác biệt giữa `isBlank()`, `isEmpty()`, `strip()`, `trim()`.

Các API sử dụng (`String`, `Character`, `Normalizer`, `StandardCharsets.UTF_8` và `Files.readString/writeString`) là API công khai, tiếp tục được hỗ trợ. Ví dụ sử dụng **Java 11**, có thể biên dịch với `--release 11` và áp dụng trên JDK mới hơn.

## 1. Xác định chính xác đơn vị được kiểm thử

### 1.1. `char`, code point và grapheme không phải một khái niệm

Java `String` biểu diễn chuỗi theo **UTF-16**:

- `String.length()` trả số **UTF-16 code units**, không phải số «chữ cái hiển thị».
- `String.charAt(index)` truy cập một `char` (16 bit); ký tự ngoài BMP (`U+10000` đến `U+10FFFF`) sử dụng **surrogate pair** gồm hai `char`.
- `String.codePointCount(begin, end)` đếm Unicode code points trong một đoạn (các index vẫn tính bằng `char`).
- `String.codePointAt(index)` đọc code point tại index của **UTF-16 code unit**; `String.offsetByCodePoints(index, amount)` giúp di chuyển theo code point mà không tự cắt đôi cặp surrogate hợp lệ.
- Một **grapheme cluster** (đơn vị văn bản người dùng thường cảm nhận là một ký tự) có thể chứa **nhiều code points**: chữ có dấu kết hợp, hoặc chuỗi emoji với dấu nối `U+200D`. Vì vậy `codePointCount()` cũng không phải bộ đếm grapheme.

Ví dụ với `"A" + U+1F642 + "B"`, trong đó `U+1F642` là ký tự biểu tượng ngoài BMP:

| Phép kiểm thử | Kết quả |
| --- | --- |
| `s.length()` | `4` code units: `A` (1) + biểu tượng (2) + `B` (1). |
| `s.codePointCount(0, s.length())` | `3` code points. |
| `s.codePointAt(1)` | `0x1F642`. |
| `s.offsetByCodePoints(0, 2)` | `3` — index `char` ngay trước `B`. |
| `s.substring(1, 3)` | Trả đúng cặp surrogate của biểu tượng. |

**Lỗi dễ gặp:** gọi `substring(1, 2)` sẽ chỉ lấy **một nửa** cặp surrogate, khiến chuỗi chứa một surrogate lẻ. Không dùng `charAt()` hay `length()` một cách máy móc để cắt «một ký tự nhìn thấy». Ngoài ra, Java `String` **có thể chứa surrogate lẻ**; `codePointCount()` vẫn đếm chúng như một phần tử. Việc đếm code point không tự chứng minh chuỗi UTF-16 hợp lệ.

### 1.2. Tiếng Việt có thể có nhiều dạng mã hóa hợp lệ

Ví dụ chữ **ắ** có thể là:

- **NFC / dạng soạn sẵn:** `"\u1EAF"`, một code point `U+1EAF` (LATIN SMALL LETTER A WITH BREVE AND ACUTE).
- **NFD / dạng tách:** `"a\u0306\u0301"`, ba code points `U+0061 U+0306 U+0301` (chữ a, dấu breve, dấu sắc).

Hai cách có thể nhìn giống nhau nhưng `String.equals()` so sánh chuỗi code units nên **không bằng nhau nếu chưa chuẩn hóa**. `java.text.Normalizer` cung cấp `NFC` và `NFD` để đưa văn bản về dạng chuẩn hóa nhất quán:

- `Normalizer.normalize(text, Normalizer.Form.NFC)` tạo dạng ghép chuẩn (canonical composition).
- `Normalizer.normalize(text, Normalizer.Form.NFD)` tạo dạng tách chuẩn (canonical decomposition).
- `Normalizer.isNormalized(text, form)` kiểm tra một chuỗi đã ở dạng yêu cầu hay chưa.

**NFC/NFD không có nghĩa là xóa dấu tiếng Việt.** Ví dụ `đ` (`U+0111`) **không** phải dạng NFC tương đương với `d`. Việc bỏ dấu hoặc gộp các chữ cái khác nhau là một quy tắc nghiệp vụ khác, không tự động phát sinh từ chuẩn hóa canonical. Nếu hệ thống cần so khớp không phân biệt hoa/thường, dấu hoặc có quy tắc ngôn ngữ, hãy định nghĩa và kiểm thử chính sách đó riêng; không được coi `equalsIgnoreCase()` hoặc `Normalizer` là bộ so sánh đầy đủ theo ngôn ngữ tiếng Việt.

## 2. Thiết kế ma trận kiểm thử trước khi viết code

Một ma trận nhỏ nhưng rõ *input → hành vi mong đợi → loại lỗi phát hiện* hiệu quả hơn danh sách chuỗi ngẫu nhiên.

### 2.1. Tiếng Việt và chuẩn hóa

| Dữ liệu đầu vào | Kỳ vọng | Điều đang kiểm tra |
| --- | --- | --- |
| `"\u1EAF"` và `"a\u0306\u0301"` | `equals() == false` trước chuẩn hóa, bằng nhau sau khi cả hai về NFC. | Phân biệt tương đương hiển thị và bằng nhau theo code units. |
| `"\u1EAF"` | `length() == 1`, `codePointCount() == 1`. | Ký tự tiếng Việt precomposed. |
| `"a\u0306\u0301"` | `length() == 3`, `codePointCount() == 3`. | Dấu kết hợp vẫn là những code points riêng. |
| `"\u0111"` (đ) và `"d"` | Không bằng nhau sau NFC. | Chuẩn hóa canonical không được tự bỏ dấu hay đổi chữ. |
| `"Ti\u1EBFng Vi\u1EC7t"` | Giữ nguyên sau round-trip UTF-8. | Tệp chứa tiếng Việt không mất dấu. |

Khi so sánh khóa văn bản với Unicode, áp dụng **cùng dạng chuẩn hóa và cùng chính sách** cho cả giá trị nhập và giá trị lưu; nếu dùng cho tìm kiếm hoặc lưu trữ, xác định bước chuẩn hóa ngay tại ranh giới dữ liệu. Đừng tự biến `NFD` thành `NFC` nếu hợp đồng yêu cầu **bảo toàn chính xác** bytes hoặc code points.

### 2.2. Ký tự bổ sung, dấu nối và surrogate pair

| Dữ liệu | Kỳ vọng | Loại lỗi cần phát hiện |
| --- | --- | --- |
| `U+1F642` | `length() == 2`, `codePointCount() == 1`. | Giả định mỗi ký tự = một `char`. |
| `"A" + U+1F642 + "B"` | `length() == 4`, `codePointCount() == 3`. | Nhầm UTF-16 index và code-point index. |
| Hai `char` của `U+1F642` | `Character.isSurrogatePair(high, low) == true`. | Cắt sai ranh giới surrogate pair. |
| Một `char` high surrogate đứng một mình | Không phải cặp surrogate hoàn chỉnh, dù `String` vẫn chứa được. | Đầu vào UTF-16 bị hỏng cần phát hiện riêng. |
| Chuỗi emoji nối với `U+200D` | Có thể hiển thị thành một grapheme dù có nhiều code points. | Đồng nhất code-point count với số ký tự trực quan. |

`U+200D` (ZERO WIDTH JOINER) không đồng nghĩa với khoảng trắng; dấu nối có thể tham gia vào các chuỗi biểu tượng hợp lệ. Không tự động xóa mọi ký tự vô hình khi làm sạch chuỗi.

### 2.3. Khoảng trắng đặc biệt

Theo hợp đồng `String.isBlank()`, một chuỗi blank là chuỗi rỗng hoặc có mọi code point thỏa `Character.isWhitespace(int)`. `Character.isSpaceChar(int)` dùng nhóm Unicode separator, có tập kết quả khác. **Unicode White_Space** của tiêu chuẩn Unicode cũng không mặc nhiên đồng nhất với «Java whitespace».

| Input Java | Tên Unicode | `isBlank()` | Điều cần nhớ |
| --- | --- | --- | --- |
| `""` | Empty string | `true` | Chuỗi rỗng cũng là blank. |
| `" \t\n"` | SPACE + TAB + LF | `true` | Không chỉ có dấu cách thông thường. |
| `"\u2003"` | EM SPACE | `true` | `strip()` loại bỏ được; `trim()` không. |
| `"\u3000"` | IDEOGRAPHIC SPACE | `true` | Dấu cách Unicode trong BMP. |
| `"\u2028"` | LINE SEPARATOR | `true` | `Character.isWhitespace` nhận diện. |
| `"\u00A0"` | NO-BREAK SPACE | **`false`** | Là `isSpaceChar` nhưng không là `isWhitespace`. |
| `"\u2007"` | FIGURE SPACE | **`false`** | Một trong ba non-breaking exceptions. |
| `"\u202F"` | NARROW NO-BREAK SPACE | **`false`** | Một trong ba non-breaking exceptions. |
| `"\u200B"` | ZERO WIDTH SPACE | **`false`** | Vô hình không có nghĩa Java blank. |
| `"\u0085"` | NEXT LINE (NEL) | **`false`** | Không thỏa định nghĩa Java whitespace dù có liên hệ đến phân loại Unicode White_Space. |
| `"\u0000"` | NULL control | **`false`** | `trim()` và `isBlank()` khác nghĩa. |
| `"A\u2003"` | Chữ A + EM SPACE | **`false`** | Có nội dung, không phải chuỗi toàn khoảng trắng. |

Ba non-breaking spaces `U+00A0`, `U+2007` và `U+202F` được `Character.isWhitespace` **loại trừ rõ ràng**. Đừng viết một bài test khẳng định «mọi Unicode separator đều được `isBlank` xem là blank» vì kỳ vọng đó trái Javadoc.

## 3. Bộ kiểm thử tự chạy trên Java 11, không cần thư viện bổ sung

Tạo tệp **UnicodeRegressionTest.java** dưới đây. Các chuỗi Unicode quan trọng được ghi bằng `\uXXXX`, còn ký tự bổ sung được tạo bằng `Character.toChars(int)`. Điều này giúp cố định **chính xác code points trong đầu vào**, kể cả khi editor hoặc font hiển thị khác nhau.

Bộ kiểm thử sử dụng hàm `check` ném `AssertionError` khi sai; vì vậy có hiệu lực khi chạy `java` thông thường, **không phụ thuộc tùy chọn `-ea`** (khác với câu lệnh Java `assert` mặc định có thể bị tắt).

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;

public class UnicodeRegressionTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void testVietnamese() {
        String composed = "\u1EAF";       // a with breve and acute
        String decomposed = "a\u0306\u0301";
        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        String dWithStroke = "\u0111";

        check(!composed.equals(decomposed), "raw equality differs");
        check(Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                .equals(composed), "NFC equivalence");
        check(Normalizer.normalize(composed, Normalizer.Form.NFD)
                .equals(decomposed), "NFD equivalence");
        check(Normalizer.isNormalized(composed, Normalizer.Form.NFC),
                "composed string is NFC");
        check(!Normalizer.isNormalized(decomposed, Normalizer.Form.NFC),
                "decomposed string is not NFC");
        check(composed.length() == 1, "precomposed UTF-16 length");
        check(decomposed.length() == 3, "decomposed UTF-16 length");
        check(decomposed.codePointCount(0, decomposed.length()) == 3,
                "decomposed code point count");
        check(!Normalizer.normalize(dWithStroke, Normalizer.Form.NFC)
                .equals("d"), "NFC must not erase Vietnamese letters");
        check(vietnamese.contains("\u1EC7"), "Vietnamese phrase fixture");
    }

    private static void testSupplementary() {
        int emojiCodePoint = 0x1F642;
        String emoji = new String(Character.toChars(emojiCodePoint));
        String mixed = "A" + emoji + "B";

        check(Character.isSupplementaryCodePoint(emojiCodePoint),
                "supplementary code point");
        check(emoji.length() == 2, "emoji uses two UTF-16 code units");
        check(emoji.codePointCount(0, emoji.length()) == 1,
                "emoji represents one code point");
        check(Character.isSurrogatePair(emoji.charAt(0), emoji.charAt(1)),
                "valid surrogate pair");
        check(mixed.length() == 4, "mixed UTF-16 length");
        check(mixed.codePointCount(0, mixed.length()) == 3,
                "mixed code point count");
        check(mixed.codePointAt(1) == emojiCodePoint,
                "codePointAt begins at UTF-16 index");
        check(mixed.offsetByCodePoints(0, 2) == 3,
                "offsetByCodePoints returns UTF-16 index");
        check(mixed.substring(1, 3).equals(emoji),
                "substring uses complete surrogate pair");
        check(Arrays.equals(mixed.codePoints().toArray(),
                new int[] { 'A', emojiCodePoint, 'B' }),
                "code point traversal");

        String loneHigh = String.valueOf((char) 0xD83D);
        check(loneHigh.length() == 1, "unpaired high surrogate length");
        check(loneHigh.codePointCount(0, loneHigh.length()) == 1,
                "unpaired surrogate still counts");
        check(Character.isHighSurrogate(loneHigh.charAt(0)),
                "detect an unpaired surrogate");
    }

    private static void expectBlank(String input, boolean expected, String label) {
        check(input.isBlank() == expected, "isBlank: " + label);
    }

    private static void testSpecialWhitespace() {
        expectBlank("", true, "empty");
        expectBlank(" \t\n", true, "space-tab-newline");
        expectBlank("\u2003", true, "em-space");
        expectBlank("\u3000", true, "ideographic-space");
        expectBlank("\u2028", true, "line-separator");
        expectBlank("\u00A0", false, "no-break-space");
        expectBlank("\u2007", false, "figure-space");
        expectBlank("\u202F", false, "narrow-no-break-space");
        expectBlank("\u200B", false, "zero-width-space");
        expectBlank("\u0085", false, "next-line");
        expectBlank("\u0000", false, "null-control");
        expectBlank("A\u2003", false, "has-letter");

        for (int cp : new int[] { 0x00A0, 0x2007, 0x202F }) {
            check(Character.isSpaceChar(cp), "spaceChar: " + cp);
            check(!Character.isWhitespace(cp), "not Java whitespace: " + cp);
        }
        check("\u2003".strip().isEmpty(), "strip removes em-space");
        check(!"\u2003".trim().isEmpty(), "trim retains em-space");
        check(!"\u0000".isBlank() && "\u0000".trim().isEmpty(),
                "trim and isBlank have different contracts");
    }

    private static void testUtf8RoundTrip() throws IOException {
        String emoji = new String(Character.toChars(0x1F642));
        String original =
                "Ti\u1EBFng Vi\u1EC7t|\u1EAF|a\u0306\u0301|" + emoji + "|\u00A0";
        Path path = Files.createTempFile("unicode-regression-", ".txt");
        try {
            Files.writeString(path, original, StandardCharsets.UTF_8);
            String actual = Files.readString(path, StandardCharsets.UTF_8);

            check(original.equals(actual), "UTF-8 text round trip");
            check(Arrays.equals(original.getBytes(StandardCharsets.UTF_8),
                    Files.readAllBytes(path)), "exact UTF-8 bytes");
            check(actual.contains("a\u0306\u0301"),
                    "decomposed sequence preserved");
            check(actual.contains(emoji), "supplementary code point preserved");
            check(actual.endsWith("\u00A0"), "NBSP preserved in file");
        } finally {
            Files.deleteIfExists(path);
        }
    }

    public static void main(String[] args) throws IOException {
        testVietnamese();
        System.out.println("PASS Vietnamese NFC/NFD");

        testSupplementary();
        System.out.println("PASS supplementary code points");

        testSpecialWhitespace();
        System.out.println("PASS special whitespace");

        testUtf8RoundTrip();
        System.out.println("PASS UTF-8 round trip");

        System.out.println("ALL TESTS PASSED");
    }
}
~~~

### Chạy và đọc kết quả

Dùng JDK 11 hoặc JDK mới hỗ trợ `--release 11`:

~~~bash
javac --release 11 -encoding UTF-8 UnicodeRegressionTest.java
java UnicodeRegressionTest
~~~

**Đầu ra mong đợi khi tất cả kiểm thử thành công:**

~~~text
PASS Vietnamese NFC/NFD
PASS supplementary code points
PASS special whitespace
PASS UTF-8 round trip
ALL TESTS PASSED
~~~

Khi bất kỳ điều kiện nào sai, `check` ném `AssertionError`, chương trình kết thúc với lỗi và **không** in dòng `ALL TESTS PASSED`. Đây là cách đơn giản để dùng với build hoặc CI mà không phụ thuộc thư viện test. `--release 11` hạn chế cú pháp, class files và API công khai theo Java 11 ngay cả khi bạn đang cài một JDK mới; khi sản phẩm thực sự triển khai trên Java 11, CI cũng cần có một lượt chạy bằng **runtime Java 11 thực**.

Bộ kiểm thử chủ động tạo một tệp tạm trong hệ thống, dùng `Files.writeString`/`Files.readString` với `StandardCharsets.UTF_8`, sau đó xóa trong `finally`. File không được ghi vào mã nguồn dự án và không bị phụ thuộc vào hệ mã mặc định của máy. `Files.writeString` và `Files.readString` là API được giới thiệu ở Java 11, vẫn phù hợp với bài toán đọc/ghi file văn bản nhỏ. Đối với tệp lớn, cần mô hình đọc/ghi theo luồng thay vì tải toàn bộ vào một `String`.

### Vì sao dùng các so sánh như vậy?

- **So sánh trước và sau NFC:** chứng minh hai cách biểu diễn của `ắ` không bằng nhau theo chuỗi gốc nhưng bằng nhau sau chuẩn hóa canonical.
- **Kiểm tra `length()` và `codePointCount()` độc lập:** buộc kiểm thử bắt được lỗi giả định `char == code point`.
- **Kiểm tra `offsetByCodePoints`:** phòng lỗi lấy substring cắt giữa hai `char` của ký tự bổ sung.
- **Kiểm tra surrogate lẻ:** chứng minh `codePointCount()` không tự bảo đảm mọi code point là Unicode scalar value hợp lệ.
- **Bảng `isBlank`:** thể hiện cả giá trị `true` và `false` với ký tự nhìn giống khoảng trắng, tránh trường hợp chỉ kiểm thử dấu cách ASCII.
- **Round-trip UTF-8:** kiểm tra giữ nguyên **chuỗi code units và bytes đầu ra**, bao gồm tiếng Việt, dạng NFD, ký tự bổ sung và NBSP; không lặng lẽ chuẩn hóa lại dữ liệu.

## 4. Cách chọn thêm test case cho dự án thật

### 4.1. Nhóm dữ liệu tiếng Việt

Khi hệ thống xử lý tên người, tên đường, trường tìm kiếm hay dữ liệu sao chép từ nhiều nguồn, tối thiểu nên có:

- **Chuỗi rỗng, `null` và chuỗi chỉ có dấu cách:** xem hợp đồng nghiệp vụ đang dùng; các trường hợp này không đồng nhất.
- **Dấu tiếng Việt kết hợp:** `ắ` dạng `U+1EAF` và `a + U+0306 + U+0301`; các nguyên âm khác như `ế`, `ệ`; chữ `đ/Đ`.
- **Thứ tự dấu kết hợp và chuẩn hóa:** xác nhận dạng NFC/NFD theo tiêu chuẩn thay vì giả định chuỗi hiển thị bằng nhau sẽ có `equals() == true`.
- **Chữ hoa/chữ thường và dấu:** chỉ test so khớp không dấu, không phân biệt hoa/thường hoặc sắp xếp theo tiếng Việt **nếu nghiệp vụ yêu cầu**; đừng trộn các tiêu chí này với NFC/NFD.
- **Nguồn vào ngoài editor:** fixture UTF-8 từ API, tệp, form nhập và copy/paste; kiểm tra chuỗi thật theo code points khi báo cáo lỗi.

Nên duy trì vài fixture có literal tiếng Việt thật để phát hiện lỗi cấu hình encoding ở tập tin mã nguồn/test resource; đồng thời giữ các fixture viết bằng `\uXXXX` để xác nhận chính xác các code point mong đợi. Với Java compiler, cấu hình rõ `-encoding UTF-8` thay vì dựa vào encoding mặc định của máy.

### 4.2. Nhóm ký tự bổ sung

Bên cạnh một code point ngoài BMP đơn lẻ, cần kiểm thử ở **biên** của chuỗi:

- Ký tự bổ sung đứng đầu, ở giữa và cuối chuỗi; truy cập bằng `codePointAt`.
- Lấy đoạn trước/sau emoji bằng `offsetByCodePoints` hoặc tính index UTF-16 đúng; tránh cắt surrogate pair.
- Chuỗi nhiều code points nhưng hiển thị như một cụm (chữ có dấu kết hợp, emoji có `U+200D`, modifier): yêu cầu «độ dài = số grapheme» là một quy tắc khác với `codePointCount`.
- Surrogate lẻ do dữ liệu hỏng hoặc thao tác cắt sai. Nếu đường dữ liệu yêu cầu Unicode hợp lệ, phải chọn cách **phát hiện và xử lý** theo hợp đồng (từ chối, thay thế theo quy định, hoặc báo lỗi), không coi kết quả `length()/codePointCount()` là xác nhận hợp lệ.

**Lưu ý:** các phép thao tác chuỗi Java cơ bản không tự thực hiện đầy đủ phân tách *extended grapheme clusters* mới nhất của Unicode. Nếu sản phẩm có thao tác «xóa một ký tự mà người dùng nhìn thấy», kiểm thử theo đặc tả grapheme đang áp dụng và lựa chọn thư viện/công cụ có bảo đảm tương ứng.

### 4.3. Nhóm khoảng trắng đặc biệt

Một bộ test tối thiểu nên có cả **mẫu đối chứng** và **mẫu âm**:

- SPACE, TAB, CR/LF, EM SPACE, IDEOGRAPHIC SPACE, LINE SEPARATOR → `isBlank() == true` khi chỉ chứa các ký tự đó.
- NO-BREAK SPACE `U+00A0`, FIGURE SPACE `U+2007`, NARROW NO-BREAK SPACE `U+202F` → `isBlank() == false`, dù `Character.isSpaceChar` là `true`.
- ZERO WIDTH SPACE `U+200B`, NEXT LINE `U+0085` và NULL control `U+0000` → `isBlank() == false`.
- Chuỗi pha trộn chữ thật với whitespace như `"A\t"` → `false`.
- Kiểm tra `"\u2003".strip().isEmpty() == true` nhưng `"\u2003".trim().isEmpty() == false`.

**Không nên đặt tên bài kiểm thử «loại bỏ toàn bộ khoảng trắng Unicode» nếu chỉ dùng `strip` hoặc `trim`.** Mỗi API có hợp đồng cụ thể. Với dữ liệu có NBSP, có thể cần chính sách riêng dựa trên yêu cầu nhập liệu; quy tắc đó phải có test cases riêng và không được áp dụng bừa cho toàn bộ dữ liệu văn bản.

## 5. Gỡ lỗi Unicode bằng code point, không bằng mắt

Hai chuỗi trông giống nhau có thể có độ dài và code points khác nhau. Khi một test thất bại, in danh sách mã thay vì chỉ in chuỗi hiển thị.

Đoạn helper dưới đây **đặt bên trong một class Java** (không phải chương trình độc lập):

~~~java
private static String codePointSequence(String text) {
    return text.codePoints()
            .mapToObj(cp -> String.format("U+%04X", cp))
            .collect(java.util.stream.Collectors.joining(" "));
}
~~~

Ví dụ nếu gọi với `"\u1EAF"` và `"a\u0306\u0301"`, chuỗi trả về lần lượt là:

~~~text
U+1EAF
U+0061 U+0306 U+0301
~~~

Phương thức hiển thị cho việc điều tra, **không** dùng làm thuật toán chuẩn hóa. Khi log dữ liệu thực tế, chỉ log những đoạn kiểm thử không nhạy cảm và ưu tiên các giá trị code point do bạn chủ động tạo; không cần ghi toàn bộ thông tin người dùng.

Phân biệt ba lớp lỗi khi phân tích:

1. **Mã Unicode khác nhau:** hai chuỗi code points khác nhau dù nhìn giống; dùng `Normalizer` đúng chính sách nếu cần so sánh canonical.
2. **Biểu diễn UTF-16 khác nhau:** một code point supplementary là hai `char`; dùng các API dựa trên code point khi cần.
3. **Chuyển mã qua I/O:** code points bị thay đổi khi mã hóa/giải mã file, truyền qua API hoặc lưu vào cơ sở dữ liệu; chỉ định `UTF-8` rõ ràng và kiểm tra round-trip.

## 6. Đưa kiểm thử vào CI và tránh test dễ vỡ

Khi chuyển từ chương trình độc lập sang framework kiểm thử như JUnit Jupiter, có thể tổ chức ba nhóm test thành các phương thức riêng hoặc các test có tham số lấy từ bảng case. Những **đầu ra đã có hợp đồng rõ** như `isBlank`, `isWhitespace`, `Normalizer NFC/NFD` và `codePointCount` nên được kiểm bằng giá trị kỳ vọng cụ thể thay vì kiểm «không ném exception». Kiểm thử các giá trị mã `U+XXXX` rõ ràng để tránh trường hợp hai fixture vô tình được editor lưu giống nhau.

Với dự án yêu cầu chạy trên **Java 11**, cấu hình kiểm tra:

- Biên dịch bằng `javac --release 11` hoặc cấu hình tương đương trong build.
- Chạy test trên JDK 11 thật ít nhất trong một job của CI; có thể thêm một JDK mới để phát hiện khác biệt giữa các bản, đặc biệt nếu dự án cần hỗ trợ nhiều runtime.
- Đặt encoding tệp nguồn/test resource thành UTF-8 và kiểm tra round-trip ở ranh giới có file, DB hoặc HTTP.
- Không phụ thuộc vào font, locale mặc định hoặc cách terminal vẽ emoji để quyết định PASS/FAIL; dùng mã Unicode, boolean và giá trị String có thể so sánh chính xác.
- Nếu yêu cầu nghiệp vụ có liên quan đến thuộc tính Unicode hoặc grapheme segmentation thay đổi theo phiên bản dữ liệu Unicode, ghi rõ **JDK, phiên bản Unicode và đặc tả** được kiểm thử. Không kỳ vọng một bộ Unicode metadata bất biến trên mọi bản JDK.
- Giữ test của **hợp đồng sản phẩm** riêng với test minh họa **hợp đồng Java**. Ví dụ nghiệp vụ có thể xem NBSP là giá trị rỗng, nhưng không được sửa kỳ vọng chuẩn của `String.isBlank()` thành `true`.

### Các lỗi kiểm thử phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ nhập ký tự qua bàn phím bằng mắt. | Bỏ qua NFD, NBSP, zero-width và dấu kết hợp. | Dùng `\uXXXX`/`Character.toChars`, in code points. |
| Gộp `length`, code point và grapheme thành một số đếm. | Cắt surrogate pair, sai giới hạn nhập liệu. | Kiểm riêng từng đơn vị, dùng `offsetByCodePoints` khi phù hợp. |
| So sánh tiếng Việt bằng `equals` mà không xác định dạng chuẩn hóa. | Hai chuỗi hiển thị giống nhau vẫn không bằng. | Xác định chuẩn hóa canonical ở ranh giới dữ liệu và test trước/sau. |
| Chỉ kiểm thử `" "` cho `isBlank`. | Bỏ qua EM SPACE, NBSP, ZERO WIDTH SPACE. | Thêm bảng true/false với từng code point. |
| Dùng `trim` như phép kiểm tra Unicode whitespace. | Sai trên nhiều ký tự Unicode, bao gồm `U+2003`. | Đọc đúng hợp đồng `trim` và `strip`; kiểm thử theo chính sách cần dùng. |
| Dùng Java `assert` rồi quên bật `-ea`. | Test có thể bị bỏ qua khi chạy mặc định. | Dùng framework test hoặc hàm kiểm tra ném `AssertionError` luôn hoạt động. |
| Chạy test trên một JDK rồi mặc định mọi JDK giống nhau. | Bỏ qua khác biệt Unicode database hoặc cấu hình runtime. | Chạy CI theo các JDK sản phẩm thực sự phải hỗ trợ. |

## 7. Câu hỏi tự luyện

**Câu 1.** Hai chuỗi `"\u1EAF"` và `"a\u0306\u0301"` hiển thị gần giống nhau. Vì sao `equals()` là `false` nhưng so sánh sau `Normalizer.Form.NFC` là `true`?

**Đáp án:** Chúng có dãy code points/code units khác nhau; chuẩn hóa canonical NFC chuyển các dạng tương đương về cùng biểu diễn. NFC **không** phải xóa dấu.

**Câu 2.** Một biểu tượng có code point `U+1F642`. `String.length()` và `codePointCount(0, length())` lần lượt là gì?

**Đáp án:** `2` UTF-16 code units và `1` Unicode code point.

**Câu 3.** Có được dùng `substring(index, index + 1)` để lấy một ký tự emoji supplementary không?

**Đáp án:** Không. Nó có thể trả một surrogate lẻ; phải xác định biên code point hoặc grapheme tùy mục đích.

**Câu 4.** `"\u00A0".isBlank()` và `Character.isSpaceChar(0x00A0)` trả về gì?

**Đáp án:** `false` và `true`. NBSP là Unicode separator nhưng được loại trừ khỏi định nghĩa `Character.isWhitespace`.

**Câu 5.** Vì sao kiểm thử round-trip của chuỗi `"a\u0306\u0301"` quan trọng dù giao diện hiển thị chữ `ắ`?

**Đáp án:** Round-trip **bảo toàn dữ liệu** phải giữ đúng các code points ban đầu, trừ khi hệ thống có hợp đồng cho phép chuẩn hóa. Chỉ nhìn màn hình không chứng minh byte hoặc code-point sequence còn nguyên.

**Câu 6.** Tại sao phải chạy test trên Java 11 nếu đã biên dịch bằng `javac --release 11` và chạy thành công trên JDK mới?

**Đáp án:** `--release 11` kiểm tra khả năng biên dịch với tập API và class-file target Java 11, nhưng không thay thế việc xác nhận hành vi trên runtime Java 11 thực tế, cấu hình encoding và dữ liệu Unicode của môi trường phải hỗ trợ.

## Checklist hoàn thành bài

- [ ] Có test **cả NFC và NFD**, bao gồm dấu tiếng Việt và một trường hợp không được đổi chữ như `đ` so với `d`.
- [ ] Có test **UTF-16 length, code point count, surrogate pair, index boundary** cho một ký tự ngoài BMP.
- [ ] Có case **surrogate lẻ** để biết đếm code point không đủ xác nhận đầu vào hợp lệ.
- [ ] Có test `isBlank()` trả cả `true` và `false` với **EM SPACE, NBSP, FIGURE SPACE, NARROW NBSP, ZERO WIDTH SPACE**.
- [ ] Có test **UTF-8 round-trip** với tiếng Việt, dấu kết hợp và ký tự supplementary.
- [ ] Có thể chạy chương trình bằng `javac --release 11` và biết kết quả chuẩn; khi sai, test phải tạo lỗi rõ ràng.
- [ ] Biết khi nào chỉ sử dụng API Java chuẩn, khi nào cần một **quy tắc Unicode/ngôn ngữ của sản phẩm** được thiết kế và kiểm thử riêng.

## Nguồn tham khảo chính thức

- [Java SE 11 — String: UTF-16, length, codePointCount, codePointAt, offsetByCodePoints, isBlank, strip](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html)
- [Java SE 11 — Character: Unicode code point, surrogate pair, isWhitespace và isSpaceChar](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html)
- [Java SE 11 — java.text.Normalizer: NFC, NFD và các dạng chuẩn hóa](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 11 — Files: readString/writeString và charset](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://unicode.org/reports/tr29/)
- [Java SE API Specification của JDK hiện hành](https://docs.oracle.com/en/java/javase/27/docs/api/)
