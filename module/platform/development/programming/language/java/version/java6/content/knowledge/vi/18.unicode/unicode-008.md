# Kiểm thử nhiều cách biểu diễn cùng nội dung trong Unicode với Java

## 1. Vấn đề: nhìn giống nhau không nhất thiết là cùng chuỗi

Trong ứng dụng Java, dữ liệu Unicode đến từ trình duyệt, bàn phím, API, cơ sở dữ liệu hoặc file có thể **hiển thị giống nhau** nhưng chứa **những chuỗi code point khác nhau**. Ví dụ chữ **é** trong từ “café” có thể được biểu diễn bằng:

- `U+00E9` — LATIN SMALL LETTER E WITH ACUTE (một code point đã kết hợp sẵn).
- `U+0065 U+0301` — chữ `e` thường theo sau bởi COMBINING ACUTE ACCENT (hai code points).

Hai chuỗi được Unicode xác định là **tương đương chuẩn tắc (canonical equivalence)**, nhưng Java `String.equals` so sánh chuỗi `char`, nên trả `false` nếu một bên giữ bản tổ hợp và bên kia giữ bản phân rã.

Điều tương tự có thể xảy ra với tiếng Việt như **“Việt”**, các dấu kết hợp có thứ tự lưu trữ khác nhau, âm tiết Hangul, chữ có dấu được nhập từ nhiều bộ gõ hoặc dữ liệu nhập xuất qua nhiều hệ thống. Một kiểm thử chỉ so văn bản *nhìn trên màn hình* sẽ bỏ sót lỗi.

Mục tiêu của bài **“Kiểm thử nhiều cách biểu diễn cùng nội dung”** trong nhóm **Unicode** là thiết lập một **hợp đồng tương đương rõ ràng** rồi kiểm tra nó bằng các phép đo **bytes – UTF-16 code units – Unicode code points – grapheme clusters – normalization – so sánh theo ngôn ngữ**.

Sau bài, bạn có thể:

1. Tạo test fixtures mà hai `String` nhìn gần như hệt nhau nhưng raw `equals` và UTF-8 bytes khác nhau.
2. Dùng `java.text.Normalizer` cho NFC/NFD/NFKC/NFKD, phân biệt **canonical** với **compatibility**.
3. Kiểm tra sự nhất quán của normalization ở input, persistence, HashMap, tìm kiếm và serialization.
4. Phân biệt `String.length()`, `codePointCount(...)` và các **grapheme clusters** bằng regex `\\X`.
5. Chứng minh những thứ **không nên tự động coi là bằng nhau**: chữ hoa/thường, ký tự tương tự hình dạng ở các script khác, invisible characters hoặc khác biệt có ý nghĩa nghiệp vụ.
6. Viết chương trình Java 17+ có **21 assertions thực chạy**, cùng danh sách kiểm thử tích cực/tiêu cực để dùng trong CI.

**Special Note:** Các API được nêu ở đây đều còn áp dụng trong Java hiện đại. Ví dụ sử dụng Java 17 trở lên, được biên dịch với `javac --release 17` và thực thi thành công trên OpenJDK 24; phần lý thuyết đã đối chiếu Javadoc Java SE 26 và Unicode Standard Annex #15 phiên bản hiện hành.

## 2. Đầu tiên phải định nghĩa “cùng nội dung” nghĩa là gì

“Giống nhau” có nhiều cấp độ. Không thể dùng một phép `equalsIgnoreCase` hoặc một quy tắc normalize cho tất cả.

| Quan hệ | Ví dụ | Có nên xem là cùng một chuỗi? | Cơ chế kiểm tra |
| --- | --- | --- | --- |
| **Chính xác theo code units** | Hai chuỗi cùng dãy UTF-16 `char` | Có theo `String.equals` | `a.equals(b)` |
| **Tương đương chuẩn tắc** | `é` (`U+00E9`) và `e + ◌́` | Thường **có** khi nghiệp vụ coi là cùng văn bản | Normalize **cả hai** về NFC hoặc NFD rồi so raw |
| **Tương đương tương thích** | `ﬃ` và `ffi`; `Ａ` và `A` | **Tùy miền dữ liệu**, có thể mất ý nghĩa phân biệt | NFKC/NFKD theo policy |
| **Không phân biệt hoa/thường** | `A` và `a`; `İ` và `i` | Tùy locale, chính sách identifier/tìm kiếm | Case handling được chỉ định tường minh |
| **So sánh ngôn ngữ** | `cafe` và `café` | Tùy locale, cấp độ collation | `Collator` hoặc cơ chế tìm kiếm phù hợp |
| **Nhìn tương tự** | Latin `a` và Cyrillic `а` | **Không mặc định**: khác code point/script | Unicode confusable analysis chuyên dụng |
| **Các chuỗi thành một cụm hiển thị** | `e + ◌́`, emoji ZWJ family | Có thể là **một grapheme**, không nhất thiết một code point | Quy tắc phân đoạn Unicode/`Pattern "\\X"` |
| **Cùng ý nghĩa nghiệp vụ** | `"1"` và `"①"`, một số whitespace khác nhau | Do **schema sản phẩm** quy định | Chuỗi transform được thiết kế và test |

Có ít nhất ba câu hỏi khác nhau:

- **Storage equality:** Có đúng cùng chuỗi code units/bytes không? Dùng cho chữ ký số, hash, kiểm tra thay đổi nguyên văn và một số khóa chính xác.
- **Text equivalence:** Có thuộc cùng lớp tương đương Unicode theo chuẩn tắc không? NFC/NFD giúp chọn biểu diễn thống nhất.
- **User-facing match:** Người dùng có xem chúng là cùng từ, tên hoặc kết quả tìm kiếm không? Cần thêm locale, mục đích, luật nghiệp vụ và có thể một search engine.

**Không được rút ra kết luận** “nội dung giống nhau về hình ảnh nên an toàn gộp làm một định danh”. Các ký tự khác script có thể gây giả mạo, và NFKC có thể xóa phân biệt định dạng vốn cần được giữ.

## 3. Ba tầng đếm độ dài: UTF-16, code point và grapheme

Java `String` được mô hình hóa như một dãy **UTF-16 code units** (mỗi `char` 16 bit). Biểu diễn bộ nhớ nội bộ có thể được JVM tối ưu hóa, nhưng hợp đồng `String.length()` vẫn đếm các đơn vị `char`.

### 3.1. UTF-16 code units và Unicode code points

Ví dụ:

```java
String smile = "\uD83D\uDE42";  // 🙂 U+1F642, surrogate pair
System.out.println(smile.length());                            // 2
System.out.println(smile.codePointCount(0, smile.length()));  // 1
```

Đây là **đoạn minh họa tự chạy được khi đặt trong `main`**, không phải một file Java đầy đủ. `length() == 2` vì ký tự supplementary dùng **hai UTF-16 code units**; `codePointCount(...) == 1` vì đó là **một Unicode code point**.

Ngược lại, với chữ `e` theo sau dấu kết hợp:

```java
String decomposedE = "e\u0301";

System.out.println(decomposedE.length());             // 2
System.out.println(decomposedE.codePointCount(
        0, decomposedE.length()));                     // 2
```

Chuỗi này có **hai code points**, dù nhiều bộ render hiển thị chúng như **một ký tự thấy trên màn hình**.

### 3.2. Grapheme cluster là một tầng khác

**Extended grapheme cluster** là một cách mô hình hóa đơn vị ký tự hiển thị/người dùng cảm nhận, theo các quy tắc phân đoạn Unicode (UAX #29). Nó không đồng nhất với một code point.

Java regex hỗ trợ `\\X` để match **một Unicode extended grapheme cluster**:

```java
import java.util.regex.Pattern;

String text = "e\u0301";
long graphemes = Pattern.compile("\\X")
        .matcher(text)
        .results()
        .count();

System.out.println(graphemes); // 1
```

Đây là **các dòng minh họa**, imports cần đặt đầu file khi lắp vào một class. Regex source `"\\X"` dùng **hai dấu gạch chéo ngược** trong Java string literal để tạo pattern `\X` thực tế.

Một emoji gia đình nối bằng `U+200D ZERO WIDTH JOINER` có thể chứa **nhiều code points** nhưng là **một grapheme cluster** theo quy tắc hiện hành. Chương trình phần 8 kiểm tra ví dụ có bảy code points nhưng một grapheme cluster.

### 3.3. Vì sao cần test cả ba?

Nếu ứng dụng giới hạn **“tối đa 20 ký tự”**, phải xác định chính xác là:

- 20 UTF-16 code units (đơn giản theo `String.length` nhưng có thể cắt surrogate pair).
- 20 Unicode code points (không cắt cặp surrogate khi thao tác đúng, nhưng có thể tách dấu kết hợp khỏi chữ gốc).
- 20 grapheme clusters theo Unicode (gần với điều người dùng thấy hơn, nhưng quy tắc segment có thể cập nhật theo phiên bản Unicode).

Một ứng dụng chat nhập tên hoặc editor có thể quan tâm grapheme clusters; một protocol quy định byte length của UTF-8 phải đo **bytes**, không dùng bất kỳ cấp đếm nào ở trên. **Không dùng `substring(0, n)` trực tiếp theo `char` để cắt text Unicode mà không kiểm tra ranh giới**.

## 4. Canonical equivalence: NFC và NFD

Unicode cho phép một nội dung văn bản có nhiều cách biểu diễn code point nhưng thuộc cùng lớp tương đương **chuẩn tắc**.

### 4.1. NFC: Canonical Decomposition followed by Composition

`Normalizer.Form.NFC` quy chuẩn text về dạng tổng hợp khi thích hợp.

```java
import java.text.Normalizer;

String composed = "caf\u00E9";
String decomposed = "cafe\u0301";

System.out.println(composed.equals(decomposed));  // false

String left = Normalizer.normalize(composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(left.equals(right));            // true
```

NFC **không được định nghĩa là** “luôn ít code points nhất”. Có những chuỗi không có precomposed code point tương ứng hoặc chịu composition exclusion; chuẩn normalization có quy tắc chính xác cho decomposition, canonical ordering và composition. Hãy dùng `Normalizer`, **không tự viết bảng thay dấu**.

### 4.2. NFD: Canonical Decomposition

`Normalizer.Form.NFD` chuyển những thành phần có canonical decomposition thành chuỗi phân rã và sắp xếp combining marks theo canonical combining class.

```java
String a = Normalizer.normalize("caf\u00E9",
        Normalizer.Form.NFD);
String b = Normalizer.normalize("cafe\u0301",
        Normalizer.Form.NFD);

System.out.println(a.equals(b)); // true
```

Nếu nghiệp vụ yêu cầu lưu dạng phân rã, chọn NFD nhất quán. Nhưng trong nhiều ứng dụng văn bản thông thường, **NFC là lựa chọn thực tế phổ biến** vì chuẩn Unicode khuyến nghị nó để trao đổi và xử lý text thông thường; lựa chọn cuối cùng phải tuân theo protocol/schema.

### 4.3. Normalize cả hai vế, dùng cùng một Form

Định nghĩa hàm kiểm tra tương đương chuẩn tắc:

```java
static boolean canonicallyEquivalent(String a, String b) {
    return Normalizer.normalize(a, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(b, Normalizer.Form.NFC));
}
```

Đây là method minh họa trong class có import `Normalizer`. **Không normalize chỉ bên trái** rồi so với raw bên phải, trừ khi hệ thống bảo đảm bên phải đã ở cùng form.

`Normalizer.isNormalized(text, Form.NFC)` giúp kiểm tra dữ liệu **đã** ở NFC hay chưa:

```java
boolean validNfc =
        Normalizer.isNormalized(text, Normalizer.Form.NFC);
```

Đừng nhầm `isNormalized` với so sánh hai chuỗi. Nó kiểm tra **một** chuỗi có tuân theo form đang chọn không.

### 4.4. Tính idempotent quan trọng cho test

Một normalization đúng có tính:

```text
NFC(NFC(s)) = NFC(s)
NFD(NFD(s)) = NFD(s)
NFKC(NFKC(s)) = NFKC(s)
NFKD(NFKD(s)) = NFKD(s)
```

Đây là các **bất biến có thể test tự động**. Nếu một pipeline chuẩn hóa lặp hai lần nhưng dữ liệu thay đổi lần thứ hai, có thể bạn đã trộn thêm các transform không idempotent hoặc thao tác sai ở ranh giới.

Với hai chuỗi *thực sự* canonically equivalent, `NFC(a).equals(NFC(b))` và `NFD(a).equals(NFD(b))` đều phải đúng.

## 5. Ví dụ tiếng Việt và thứ tự dấu kết hợp

Tiếng Việt có nhiều ký tự vừa mang dấu phụ/biến thể nguyên âm vừa mang thanh điệu. Một chữ cái có thể có dạng dựng sẵn hoặc tổ hợp từ base letter và các combining marks.

### 5.1. “Việt” với hai biểu diễn

Trong Java:

```java
String precomposed = "Vi\u1EC7t";
String decomposed = "Vie\u0323\u0302t";

System.out.println(precomposed.equals(decomposed)); // false
System.out.println(Normalizer.normalize(
        precomposed, Normalizer.Form.NFC).equals(
        Normalizer.normalize(
                decomposed, Normalizer.Form.NFC)));  // true
```

Ý nghĩa:

- `U+1EC7` là **LATIN SMALL LETTER E WITH CIRCUMFLEX AND DOT BELOW** (ệ).
- `U+0065 U+0323 U+0302` là `e + COMBINING DOT BELOW + COMBINING CIRCUMFLEX ACCENT`.
- Cả hai là một cách thể hiện từ “Việt” thuộc cùng lớp tương đương chuẩn tắc.

**Tại sao đưa tiếng Việt vào kiểm thử?** Vì bộ gõ, bàn phím trên nhiều OS, font/text editors, copy-paste và dữ liệu import có thể tạo các chuỗi combining marks khác nhau. Chỉ kiểm thử chữ Latin không dấu sẽ bỏ sót lỗi thực tế của người dùng tiếng Việt.

### 5.2. Thứ tự combining marks cũng có quy tắc

Hai chuỗi:

```java
String marks1 = "a\u0301\u0323";
String marks2 = "a\u0323\u0301";

boolean rawEqual = marks1.equals(marks2);
boolean nfcEqual = Normalizer.normalize(
        marks1, Normalizer.Form.NFC).equals(
        Normalizer.normalize(marks2, Normalizer.Form.NFC));
```

Ở đây raw equality là **false**, còn NFC equality là **true** theo canonical ordering. Dấu sắc `U+0301` và dấu chấm dưới `U+0323` có **canonical combining classes khác nhau**, nên chuẩn có quy tắc sắp xếp.

Đừng tự “sort combining marks theo code point” vì canonical ordering dựa trên thuộc tính Unicode, không phải thứ tự numeric tùy ý. Một số dấu có cùng combining class không thể hoán vị tùy tiện mà vẫn coi là tương đương chuẩn tắc.

### 5.3. Các test tiếng Việt cần có

| Fixture | Dữ liệu | Điều cần khẳng định |
| --- | --- | --- |
| Ký tự precomposed vs decomposed | `Vi\u1EC7t` / `Vie\u0323\u0302t` | Raw khác, NFC bằng |
| Thứ tự dấu hợp lệ | `a\u0301\u0323` / `a\u0323\u0301` | NFC bằng |
| Thiếu dấu | `Viet` / `Việt` | NFC **không** làm chúng bằng nhau |
| Thay thanh điệu | `má` / `mà` | NFC **không** biến chúng thành một từ |
| Chữ hoa/thường | `Á` / `á` | NFC **không** tự case-fold |
| Dấu kết hợp đứng đơn lẻ | `\u0301` | Không coi là chữ cái nguyên vẹn chỉ vì render có dấu |
| Code unit split | Cắt giữa `e` và `\u0301` | Có thể làm text hiển thị sai |

Unicode normalization **không phải bộ bỏ dấu tiếng Việt**. Việc tìm kiếm không phân biệt dấu, transliteration hoặc chuyển đổi kiểu gõ là các yêu cầu khác, phải thiết kế riêng.

## 6. Compatibility equivalence: NFKC và NFKD có thể làm mất khác biệt

Hai Form có chữ `K`:

- `Normalizer.Form.NFKC`: compatibility decomposition rồi canonical composition.
- `Normalizer.Form.NFKD`: compatibility decomposition.

Chúng áp dụng **nhiều ánh xạ hơn NFC/NFD**, không chỉ gộp các dạng dấu tổ hợp chuẩn tắc.

| Cặp ví dụ | Raw/NFC | Sau NFKC | Hệ quả |
| --- | --- | --- | --- |
| Ligature `ﬃ` (`U+FB03`) và `ffi` | Khác | Bằng | Phân biệt hình thức ligature bị mất |
| Fullwidth `Ａ` (`U+FF21`) và ASCII `A` | Khác | Bằng | Mất khác biệt kiểu trình bày |
| Circled digit `①` (`U+2460`) và `1` | Khác | Bằng | Mất cách đánh số được khoanh |
| `é` và `e + ◌́` | Khác raw, bằng NFC | Bằng | Vẫn giữ canonical equivalence |
| Latin `a` và Cyrillic `а` | Khác | **Vẫn khác** | Không phải mọi ký tự nhìn giống nhau đều NFKC-equivalent |

Ví dụ code:

```java
String ligature = "\uFB03"; // ﬃ
String letters = "ffi";

boolean nfcEqual = Normalizer.normalize(
        ligature, Normalizer.Form.NFC).equals(
        Normalizer.normalize(letters, Normalizer.Form.NFC));

boolean nfkcEqual = Normalizer.normalize(
        ligature, Normalizer.Form.NFKC).equals(
        Normalizer.normalize(letters, Normalizer.Form.NFKC));

// nfcEqual == false
// nfkcEqual == true
```

**Không thay NFC bằng NFKC một cách vô điều kiện.** Compatibility normalization cố ý loại bỏ một số khác biệt có thể mang ý nghĩa trong văn bản, ký hiệu khoa học, pháp lý, nghệ thuật, mã số hay sản phẩm. Tương đương tương thích là **quan hệ rộng hơn**, không phải phép “làm sạch an toàn cho mọi string”.

### Chọn Form theo mục tiêu

- **Lưu trữ/giao tiếp text thông thường:** NFC là lựa chọn tốt khi muốn thống nhất canonical equivalents nhưng vẫn giữ những khác biệt compatibility.
- **Xử lý nội bộ cần phân rã:** NFD có thể phù hợp nếu thuật toán xử lý combining marks và form được quy định rõ.
- **Chuẩn hóa định danh/tìm kiếm đặc thù:** NFKC có thể hữu ích nếu **domain policy** chủ ý xem fullwidth, ligature hoặc circled digits là cùng giá trị. Phải kiểm tra collision và ảnh hưởng người dùng.
- **Không thay thế kiểm soát định danh Unicode:** NFKC một mình không phát hiện homoglyphs, mixed scripts hoặc các chiến thuật spoofing.

**Một phép test đúng phải có cả cặp được gộp và cặp không được gộp**. Nếu chỉ có positive tests, một phép transform làm mất quá nhiều thông tin cũng có thể “pass” mà gây lỗi nghiệp vụ.

## 7. Bytes UTF-8 khác nhau dù màn hình gần như giống nhau

UTF-8 là cách mã hóa **Unicode code points thành bytes**, còn Java `String` biểu diễn logic UTF-16 code units. Chuỗi canonically equivalent không bắt buộc có cùng UTF-8 bytes trước normalization.

Với “café”:

```text
Composed:    c  a  f  é
Code points: U+0063 U+0061 U+0066 U+00E9
UTF-8 hex:   63 61 66 C3 A9

Decomposed:  c  a  f  e  ◌́
Code points: U+0063 U+0061 U+0066 U+0065 U+0301
UTF-8 hex:   63 61 66 65 CC 81
```

Đo bằng Java 17+:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

byte[] raw = "caf\u00E9".getBytes(StandardCharsets.UTF_8);
System.out.println(HexFormat.of().formatHex(raw));
// 636166c3a9
```

**Ý nghĩa đối với test:**

- `String.equals` và `Arrays.equals(bytesA, bytesB)` là hai phép kiểm tra chính xác ở các tầng khác nhau.
- `Normalizer.normalize(..., NFC)` thay đổi code points khi cần; **chỉ sau đó** encode bằng cùng charset mới có cùng UTF-8 bytes đối với các chuỗi canonically equivalent.
- UTF-8 round-trip `new String(s.getBytes(UTF_8), UTF_8)` thường trả lại cùng `String` khi văn bản gồm những Unicode scalar values hợp lệ. Với malformed input bytes hoặc unpaired UTF-16 surrogates, cần policy xử lý lỗi, không xem round-trip là phép “sửa unicode” kỳ diệu.
- Đừng dùng platform default charset khi test byte-level; truyền `StandardCharsets.UTF_8` rõ ràng.

### Khi byte-level equality là yêu cầu bắt buộc

Có những workflow cần bytes chính xác:

- Chữ ký số/HMAC/hashing hoặc caching có key là bytes.
- Giao thức truyền tin quy định canonical serialized payload.
- Kiểm tra checksum tệp, diff nhị phân.
- Đồng bộ giữa các nền tảng yêu cầu so bytes đúng từng byte.

Nếu hệ thống **muốn** coi hai biểu diễn canonically equivalent như nhau, hãy quy định **thời điểm normalization trước encoding và hashing**. Nếu giao thức bắt buộc giữ nguyên dữ liệu gốc, tuyệt đối không tự thay bytes sau khi ký. Mục tiêu nghiệp vụ quyết định “bằng nhau” ở tầng nào.

## 8. Ví dụ Java 17+ đầy đủ: 21 phép kiểm tra Unicode

Chương trình dưới đây dùng **Java SE API**, không thêm thư viện ngoài. Các trường hợp bao gồm canonical normalization, Unicode tiếng Việt, dấu kết hợp, compatibility mappings, homoglyphs, UTF-16/codepoint/grapheme, hash key, locale và strict UTF-8 decoding.

### 8.1. Lưu thành `UnicodeEquivalenceDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.HashMap;
import java.util.regex.Pattern;

public final class UnicodeEquivalenceDemo {
    private static int passed;

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("FAIL: " + name);
        }
        System.out.println("PASS " + name);
        passed++;
    }

    private static String nfc(String s) {
        return Normalizer.normalize(s, Form.NFC);
    }

    private static String nfkc(String s) {
        return Normalizer.normalize(s, Form.NFKC);
    }

    private static long graphemes(String s) {
        return Pattern.compile("\\X")
                .matcher(s).results().count();
    }

    public static void main(String[] args) throws Exception {
        String precomposed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        check("raw-different",
                !precomposed.equals(decomposed));
        check("nfc-equal",
                nfc(precomposed).equals(nfc(decomposed)));
        check("nfd-equal",
                Normalizer.normalize(precomposed, Form.NFD).equals(
                        Normalizer.normalize(decomposed, Form.NFD)));
        check("nfc-idempotent",
                nfc(nfc(decomposed)).equals(nfc(decomposed)));
        check("is-nfc",
                Normalizer.isNormalized(
                        nfc(decomposed), Form.NFC));

        check("utf8-different", !Arrays.equals(
                precomposed.getBytes(StandardCharsets.UTF_8),
                decomposed.getBytes(StandardCharsets.UTF_8)));
        System.out.println("utf8-pre="
                + HexFormat.of().formatHex(
                        precomposed.getBytes(StandardCharsets.UTF_8)));
        System.out.println("utf8-decomp="
                + HexFormat.of().formatHex(
                        decomposed.getBytes(StandardCharsets.UTF_8)));
        check("utf8-after-nfc", Arrays.equals(
                nfc(precomposed).getBytes(StandardCharsets.UTF_8),
                nfc(decomposed).getBytes(StandardCharsets.UTF_8)));

        String vietnamese1 = "Vi\u1EC7t";
        String vietnamese2 = "Vie\u0323\u0302t";
        check("vietnamese", !vietnamese1.equals(vietnamese2)
                && nfc(vietnamese1).equals(nfc(vietnamese2)));

        String ordered1 = "a\u0301\u0323";
        String ordered2 = "a\u0323\u0301";
        check("combining-order",
                nfc(ordered1).equals(nfc(ordered2)));

        check("compat-ligature",
                !nfc("\uFB03").equals(nfc("ffi"))
                && nfkc("\uFB03").equals(nfkc("ffi")));
        check("compat-fullwidth",
                !nfc("\uFF21").equals(nfc("A"))
                && nfkc("\uFF21").equals(nfkc("A")));
        check("compat-circled",
                nfkc("\u2460").equals(nfkc("1")));

        check("lookalike-distinct",
                !nfkc("a").equals(nfkc("\u0430")));
        check("not-case-folding",
                !nfc("A").equals(nfc("a")));

        check("utf16-vs-codepoints",
                "\uD83D\uDE42".length() == 2
                && "\uD83D\uDE42".codePointCount(0, 2) == 1);

        check("grapheme-vs-codepoints",
                decomposed.substring(3).codePointCount(
                        0, decomposed.substring(3).length()) == 2
                && graphemes(decomposed.substring(3)) == 1);

        String family =
                "\uD83D\uDC68\u200D\uD83D\uDC69\u200D"
                + "\uD83D\uDC67\u200D\uD83D\uDC66";
        check("grapheme-family",
                family.codePointCount(0, family.length()) == 7
                && graphemes(family) == 1);

        Map<String, Integer> cache = new HashMap<>();
        cache.put(nfc(precomposed), 42);
        check("canonical-map-lookup",
                Integer.valueOf(42).equals(
                        cache.get(nfc(decomposed)))
                && cache.get(decomposed) == null);

        check("utf8-roundtrip",
                decomposed.equals(new String(
                        decomposed.getBytes(StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8)));

        check("locale-is-not-normalization",
                !"\u0130".toLowerCase(Locale.ROOT).equals(
                        "\u0130".toLowerCase(
                                Locale.forLanguageTag("tr"))));

        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(
                            new byte[] {(byte) 0xC3, 0x28}));
        } catch (CharacterCodingException expected) {
            rejected = true;
        }
        check("invalid-utf8-rejected", rejected);

        System.out.println("passed=" + passed);
    }
}
```

**Các quyết định trong ví dụ:**

- `"\u00E9"` và `"e\u0301"` được ghi dưới dạng Unicode escapes để **người đọc source nhìn thấy từng cách biểu diễn**. Không dựa vào text editor âm thầm đổi normalization của ký tự literal.
- `HexFormat` là API được hỗ trợ từ Java 17, nên phù hợp với `--release 17`.
- `Normalizer` hỗ trợ đủ bốn forms; helper `nfc`/`nfkc` được dùng nhất quán.
- `Pattern.compile("\\X")` kiểm tra một **extended grapheme cluster**, không nhầm với `String.length`.
- `HashMap` minh họa phải normalize **cả lúc put lẫn lúc get**, vì chính `String.equals/hashCode` không tự hiểu canonical equivalence.
- `Locale.ROOT` và `Locale.forLanguageTag("tr")` minh họa case mapping là một quy trình độc lập với normalization.
- `CharsetDecoder` cấu hình `REPORT` kiểm tra malformed UTF-8. Không âm thầm thay bytes sai bằng replacement characters khi protocol yêu cầu dữ liệu hợp lệ.

### 8.2. Lệnh biên dịch và chạy

Đặt terminal tại thư mục chứa `UnicodeEquivalenceDemo.java`:

```bash
javac --release 17 UnicodeEquivalenceDemo.java
java UnicodeEquivalenceDemo
```

Lệnh tương tự dùng được trong PowerShell khi `javac` và `java` thuộc JDK 17+ trên `PATH`. File và class cần có tên đúng `UnicodeEquivalenceDemo`.

### 8.3. Stdout chính xác đã kiểm thử

```text
PASS raw-different
PASS nfc-equal
PASS nfd-equal
PASS nfc-idempotent
PASS is-nfc
PASS utf8-different
utf8-pre=636166c3a9
utf8-decomp=63616665cc81
PASS utf8-after-nfc
PASS vietnamese
PASS combining-order
PASS compat-ligature
PASS compat-fullwidth
PASS compat-circled
PASS lookalike-distinct
PASS not-case-folding
PASS utf16-vs-codepoints
PASS grapheme-vs-codepoints
PASS grapheme-family
PASS canonical-map-lookup
PASS utf8-roundtrip
PASS locale-is-not-normalization
PASS invalid-utf8-rejected
passed=21
```

Bộ test này được **biên dịch thành công bằng `javac --release 17`** và chạy trên OpenJDK 24; tất cả **21 assertions PASS**. Nếu bất kỳ assertion nào sai, chương trình ném `AssertionError("FAIL: ...")`, không in dòng `passed=21` và tiến trình kết thúc không thành công.

### 8.4. Phân tích các nhóm assertion

| Nhóm | Tên assertion | Điều được xác minh |
| --- | --- | --- |
| Canonical | `raw-different` / `nfc-equal` / `nfd-equal` | Hai biểu diễn có raw bytes/code units khác nhưng cùng canonical class |
| Tính ổn định | `nfc-idempotent` / `is-nfc` | Normalize lần hai không thay kết quả; form có thể kiểm tra |
| Encoding | `utf8-different` / `utf8-after-nfc` | UTF-8 bytes khác trước NFC và giống nhau sau NFC |
| Tiếng Việt | `vietnamese` | Dạng dựng sẵn và tổ hợp của `ệ` được hợp nhất bằng NFC |
| Dấu kết hợp | `combining-order` | Canonical ordering cho ra cùng kết quả |
| Compatibility | `compat-ligature` / `compat-fullwidth` / `compat-circled` | NFKC cố ý gộp một số cặp NFC vẫn phân biệt |
| Negative | `lookalike-distinct` / `not-case-folding` | NFKC không gộp homoglyph khác script; NFC không tự lower-case |
| Đơn vị ký tự | `utf16-vs-codepoints` / `grapheme-vs-codepoints` / `grapheme-family` | Độ dài code units, code points và graphemes khác nhau |
| Storage keys | `canonical-map-lookup` | HashMap vẫn tra được dữ liệu sau khi cả key vào/ra đều NFC |
| Round-trip | `utf8-roundtrip` | Chuỗi hợp lệ qua encode/decode UTF-8 được giữ nguyên |
| Locale | `locale-is-not-normalization` | Chuyển chữ hoa/thường phụ thuộc locale |
| Input validation | `invalid-utf8-rejected` | Strict decoder phát hiện bytes UTF-8 sai |

Lưu ý `"passed=21"` là **số phép kiểm tra**, không phải số ký tự hoặc số trường hợp dữ liệu đầu vào. Các ví dụ trực quan trong bảng có thể phát sinh nhiều thuộc tính trong một assertion.

## 9. Testing canonical text với HashMap, Set và dữ liệu lưu trữ

### 9.1. HashMap không tự chuẩn hóa chuỗi

`String.equals` dùng so sánh theo chuỗi `char`, và `String.hashCode` phù hợp với định nghĩa equality đó; cả hai **không** tự chuyển NFC/NFD. Vì vậy:

```java
Map<String, String> names = new HashMap<>();

names.put("caf\u00E9", "record");
System.out.println(names.get("cafe\u0301"));  // null
```

Đây là đoạn minh họa cần import `Map` và `HashMap`. Nếu domain xác định canonical equivalents là cùng key, phải canonicalize **trước khi ghi và trước khi tra**:

```java
static String canonicalKey(String s) {
    return Normalizer.normalize(s, Normalizer.Form.NFC);
}

Map<String, String> names = new HashMap<>();
names.put(canonicalKey("caf\u00E9"), "record");
System.out.println(names.get(canonicalKey("cafe\u0301")));
// record
```

Đoạn này minh họa cần đặt trong class/method phù hợp, không phải file tự chạy. **Bất biến chính:** `key(x) == key(y)` theo `String.equals` đối với những giá trị mà domain coi là tương đương.

### 9.2. Một chuỗi là “cùng tên” tùy chính sách dữ liệu

Đối với người dùng lưu tên tiếng Việt, có thể lưu **hai trường**:

- `displayName`: text người dùng đã nhập hoặc đã xử lý theo yêu cầu hiển thị, bảo toàn chi tiết cần thiết.
- `normalizedSearchKey`: text được chuẩn hóa theo chính sách tìm kiếm/so khớp đã tài liệu hóa.

Nhưng **không** tự gộp các đăng nhập, usernames hoặc account identifiers chỉ vì NFKC map chúng về cùng value. Phải thiết kế **collision policy**: nếu hai bản ghi trước đây khác nhau nhưng canonical key trùng sau migration, cần quyết định hợp nhất, báo lỗi hoặc duy trì alias; không được lặng lẽ ghi đè.

### 9.3. Unicode normalization không phải database collation

Database có thể có collation riêng cho so sánh và unique index. Java `Normalizer.Form.NFC` chỉ tạo dạng code point chuẩn tắc, không quyết định quy tắc không phân biệt hoa/thường hoặc dấu của DB.

Test integration nên đưa **hai canonical-equivalent inputs** qua đúng đường ghi/truy vấn thật, sau đó kiểm tra:

1. DB có lưu cùng key normalized không?
2. Unique constraint có phát hiện xung đột nếu domain yêu cầu không?
3. Query bằng dạng NFD có tìm thấy bản ghi đã lưu dạng NFC không?
4. Search index có áp dụng **đúng** cùng transform không?
5. Khi trả về API, hệ thống có giữ nguyên display text hoặc policy đã công bố không?

Đừng chỉ kiểm thử helper `Normalizer` rồi kết luận toàn bộ hệ thống đã nhất quán. Bug thường xuất hiện ở **một boundary không được normalize**: import CSV, background job, webhook, message queue, cache lookup hoặc migration.

## 10. Tìm kiếm và Collator: gần bằng không đồng nghĩa giống hệt

`java.text.Collator` dùng so sánh văn bản **theo ngôn ngữ và mức độ khác biệt cần quan tâm**. Nó phù hợp cho sắp xếp và nhiều kiểu search locale-sensitive.

```java
import java.text.Collator;
import java.util.Locale;

Collator collator = Collator.getInstance(Locale.FRENCH);
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
collator.setStrength(Collator.TERTIARY);

int cmp = collator.compare("caf\u00E9", "cafe\u0301");
```

Đây là đoạn minh họa không standalone; `cmp == 0` dự kiến cho hai dạng canonical equivalent trong môi trường locale có collation data thích hợp. `CANONICAL_DECOMPOSITION` yêu cầu decomposition chuẩn tắc khi so, `TERTIARY` xét nhiều khác biệt ngôn ngữ hơn `PRIMARY`.

Đừng dùng `Collator.PRIMARY` làm phép định nghĩa **cùng một raw String** hoặc một global identifier key: với một số locale, primary-strength collation có thể bỏ qua khác biệt chữ hoa/thường và dấu. Điều đó hữu ích cho tìm kiếm nhưng **khác** với Unicode canonical equivalence.

### Tại sao test Collator theo locale và phiên bản?

- Collation rules có thể phụ thuộc `Locale` và provider data của JDK.
- `Collator.getInstance()` không chỉ định locale sẽ dùng default locale của hệ thống; CI trên hai máy có thể so khác.
- Các mức `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL` có semantics theo ngôn ngữ, không phải bốn Unicode normalization forms.
- `CANONICAL_DECOMPOSITION` tương ứng tính phân rã canonical khi so; `FULL_DECOMPOSITION` bao gồm compatibility decomposition. Không mặc định biến một Collator thành global normalization pipeline của sản phẩm.
- Nếu test thứ tự sắp xếp có golden output, hãy pin locale và cấu hình provider; với yêu cầu deterministic đa JDK, hạn chế assert những thứ có thể đổi khi dữ liệu collation được cập nhật.

**Ranh giới rõ ràng:** `Normalizer` tạo ra **một String mới trong form được chọn**; `Collator` thực hiện **phép so sánh theo quy tắc ngôn ngữ**, không tạo canonical key chung để mọi hệ thống tự hiểu.

## 11. Case mapping, case-insensitive và tiếng Việt

Unicode normalization **không tự chuyển hoa/thường**:

```java
String upper = Normalizer.normalize(
        "A", Normalizer.Form.NFC);
String lower = Normalizer.normalize(
        "a", Normalizer.Form.NFC);

System.out.println(upper.equals(lower)); // false
```

Nếu ứng dụng cần tìm kiếm không phân biệt hoa/thường, phải xác định thêm quy tắc case mapping/folding.

### 11.1. Locale là một phần của hành vi

Ví dụ chữ **LATIN CAPITAL LETTER I WITH DOT ABOVE**, `U+0130`:

```java
String source = "\u0130";

String root = source.toLowerCase(Locale.ROOT);
String turkish = source.toLowerCase(
        Locale.forLanguageTag("tr"));

System.out.println(root.equals(turkish)); // false
```

Trường hợp này được xác minh trong chương trình phần 8. Locale ROOT có thể dùng chữ `i` kèm combining dot above, còn locale Turkish có mapping phù hợp ngôn ngữ. Không thay `toLowerCase(Locale.ROOT)` bằng `toLowerCase()` nếu kết quả cần ổn định giữa các máy có default locale khác nhau.

### 11.2. Lowercase không có nghĩa “full case folding”

`String.toLowerCase(Locale.ROOT)` là **chuyển chữ thường theo quy tắc locale**, không phải một mô tả đầy đủ mọi Unicode case-folding policy mà mọi hệ thống ID/search đều phải dùng. `equalsIgnoreCase` cũng không thay thế việc thiết kế canonicalization hoặc collation theo domain.

Nếu ứng dụng cần **NFKC_Casefold** theo Unicode cho định danh, phải sử dụng một implementation và quy trình có contract rõ ràng, ví dụ Unicode/ICU APIs phù hợp với policy sản phẩm và phiên bản Unicode đang áp dụng. Đừng tự ghép `toLowerCase` + `NFKC` rồi khẳng định bằng mọi trường hợp của chuẩn NFKC_Casefold.

### 11.3. Thứ tự các phép biến đổi quan trọng

Một pipeline có thể làm:

```text
Input
  → validate encoding / parse theo schema
  → normalize canonical (NFC)
  → case transform nếu domain yêu cầu
  → normalize lại nếu transform tạo combining sequences
  → validate allowed characters/script policy
  → compare/store/search
```

Đây là **sơ đồ thiết kế minh họa**, không phải quy tắc toàn cầu. Với security-sensitive identifiers, cần dùng chuẩn identifier profile đã được quy định, không tự chọn từng bước trên.

Một test đúng cần kiểm tra **đầu ra cuối cùng** sau tất cả transform, không chỉ mỗi bước riêng lẻ. Nếu thay đổi thứ tự dẫn đến key khác, phải có regression test chứng minh lý do.

## 12. Visual confusables, khoảng trắng và ký tự vô hình

### 12.1. Latin a và Cyrillic а

Hai chuỗi sau có hình dáng gần nhau nhưng **không phải cùng code point**:

```java
String latin = "a";         // U+0061 LATIN SMALL LETTER A
String cyrillic = "\u0430";  // U+0430 CYRILLIC SMALL LETTER A

boolean same = Normalizer.normalize(
        latin, Normalizer.Form.NFKC).equals(
        Normalizer.normalize(
                cyrillic, Normalizer.Form.NFKC));

// same == false
```

Đây là negative test quan trọng. Kết quả **false** là điều mong đợi: Unicode normalization không cố xóa mọi khác biệt hình dạng giữa các script.

### 12.2. Zero-width và format controls

Một chuỗi có thể chứa:

- `U+200B ZERO WIDTH SPACE`.
- `U+200C ZERO WIDTH NON-JOINER`.
- `U+200D ZERO WIDTH JOINER`.
- `U+FE0F VARIATION SELECTOR-16`.
- Một số Unicode bidi controls.

Chúng có thể làm text hiển thị khác hoặc gần như giống nhau, nhưng không nhất thiết nên xóa. Ví dụ `U+200D` cần thiết cho nhiều emoji sequences; xóa nó có thể làm vỡ một grapheme thành nhiều emoji hiển thị. Ký tự bidi controls có thể ảnh hưởng cách render dù thứ tự lưu trữ không đổi.

**Đừng xây sanitizer kiểu “xóa mọi code point không nhìn thấy”.** Hãy xác định allowed code points và quy tắc riêng theo schema/loại dữ liệu, đồng thời test emoji và ngôn ngữ cần supported.

### 12.3. Whitespace và line endings

`"a b"` với U+0020 SPACE khác `"a\u00A0b"` với U+00A0 NO-BREAK SPACE. NFKC có thể map một số compatibility spaces, nhưng không có nghĩa mọi whitespace đều tương đương trong mọi miền dữ liệu.

Tương tự:

- `"\n"` là LF.
- `"\r\n"` là CRLF.
- `"\r"` là CR.

Unicode normalization không phải line-ending normalization. Với file/protocol cần LF, tạo **một transform line ending riêng** có test. Đừng vô tình thay đổi bytes của payload đã ký hoặc log chính xác.

### 12.4. Confusable detection là một bài toán chuyên biệt

Nếu định danh công khai, domain name hoặc username có nguy cơ spoofing, cần tham chiếu **Unicode Security Mechanisms (UTS #39)**, chính sách mixed-script và kiểm soát bảng chữ cái cho phép. Tương đương chuẩn tắc NFC không tự phát hiện confusables. Ngược lại, **trông giống nhau trên một font** không tự định nghĩa danh tính bằng nhau trên mọi font và locale.

## 13. Mã hóa/giải mã UTF-8 và lỗi dữ liệu không hợp lệ

### 13.1. Round-trip cho text hợp lệ

`StandardCharsets.UTF_8` được Java SE hỗ trợ bắt buộc:

```java
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(encoded, StandardCharsets.UTF_8);
```

Với text chứa các Unicode scalar values hợp lệ, phép round-trip này giữ chuỗi. Nhưng **không tự normalize**: nếu `text` là NFD trước encode, `decoded` cũng có thể là NFD sau decode.

### 13.2. Decoder mặc định có thể thay bytes lỗi

Nếu input có bytes UTF-8 malformed, các convenience decoding APIs có thể **thay chuỗi lỗi bằng replacement character** theo chính sách mặc định, khiến test so văn bản không phát hiện dữ liệu nguồn đã bị hỏng.

Khi giao thức yêu cầu UTF-8 chuẩn, dùng decoder strict:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String data = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
```

Đây là đoạn minh họa có biến `byte[] bytes` và cần xử lý `CharacterCodingException`. Với bytes `C3 28`, fixture phần 8 kiểm tra decoder strict **ném exception** và test `invalid-utf8-rejected` PASS.

### 13.3. Đừng nhầm UTF-8 BOM với normalization

File có hoặc không có UTF-8 BOM là **khác biệt ở cấp bytes/file protocol**, không phải hai Unicode normalization forms. Java `String` có thể chứa `U+FEFF` ở đầu tùy decoder/file reader; đừng giả định Normalizer NFC sẽ “tẩy BOM” đúng cho mọi input.

Nếu cần hỗ trợ BOM, định nghĩa policy trong lớp đọc file: cho phép/chặn/xử lý duy nhất vị trí đầu file, rồi test byte-level riêng. Không gom việc xử lý BOM vào helper `normalizeText`.

### 13.4. Java String có thể chứa unpaired surrogates

Mặc dù `String` tuân theo UTF-16 semantics, một chuỗi Java có thể chứa **unpaired high/low surrogate** do dữ liệu sai hoặc thao tác substring/cắt code units. Code point APIs có quy tắc xử lý chúng, nhưng chúng **không phải Unicode scalar values hợp lệ** để encode UTF-8 như ký tự thông thường.

Khi làm protocol nghiêm ngặt, test lỗi surrogate và định nghĩa reject/replace policy. Không xem `String.length()` hoặc `Normalizer.isNormalized(...)` đơn lẻ như một phép xác thực toàn bộ dữ liệu Unicode.

## 14. Thiết kế test fixtures dễ hiểu và kiểm tra được

### 14.1. Dùng escapes thay vì chỉ nhìn glyph

Với một cặp visually identical, việc ghi trực tiếp cả hai glyph vào source test khiến reviewer khó nhận ra difference. Nên định nghĩa explicit:

```java
String composed = "\u00E9";
String decomposed = "e\u0301";
```

Sau đó debug bằng **code points**:

```java
import java.util.stream.Collectors;

static String codePoints(String s) {
    return s.codePoints()
            .mapToObj(cp -> String.format("U+%04X", cp))
            .collect(Collectors.joining(" "));
}

// codePoints(composed)   -> U+00E9
// codePoints(decomposed) -> U+0065 U+0301
```

Đây là helper minh họa cần đặt trong class Java và import `Collectors`. `String.format` ở đây chỉ format **hex digits của số nguyên**, không phụ thuộc biến đổi chữ.

**Cảnh báo Java source escapes:** Java xử lý `\uXXXX` escapes sớm trong quá trình lexing source. Đừng chèn một sequence như Unicode escape của newline vào comment/string theo cách làm vỡ cú pháp ngoài ý muốn. Dùng `"\n"` cho line break trong Java string thông thường và kiểm thử source được compiler đọc đúng.

### 14.2. Debug từng tầng

Khi hai chuỗi nhìn giống nhau nhưng compare sai, ghi report tối thiểu:

| Trường | Để biết |
| --- | --- |
| Code points dạng `U+...` | Thực sự là ký tự nào |
| `String.length()` | Bao nhiêu UTF-16 code units |
| `codePointCount` | Bao nhiêu code points |
| Grapheme count | Người dùng có thể thấy bao nhiêu cụm |
| `Normalizer.isNormalized(s, NFC)` | Chuỗi đã ở form được yêu cầu chưa |
| UTF-8 hex hoặc checksum | Bytes khác nhau ở tầng transport/storage không |
| Locale/collation settings | Quy tắc search/sort có phụ thuộc nơi chạy không |
| Phiên bản Java/Unicode algorithm | Giúp tái lập một lỗi hiếm gặp sau upgrade |

**Không log nguyên dữ liệu bí mật** nếu text là password, token, PII hoặc payload nhạy cảm. Với các trường hợp này dùng test fixture tổng hợp hoặc chỉ ghi thông tin được phép, có giới hạn và đã giảm dữ liệu nhận dạng.

### 14.3. Test dương phải có test âm đối xứng

Nếu chỉ kiểm tra:

```java
check("canon", nfc("\u00E9").equals(nfc("e\u0301")));
```

thì một hàm xóa mọi dấu hoặc mọi ký tự lạ cũng có thể qua test nhưng gây mất thông tin. Thêm:

```java
check("accent-distinct",
        !nfc("cafe").equals(nfc("caf\u00E9")));
check("case-distinct",
        !nfc("A").equals(nfc("a")));
check("script-distinct",
        !nfc("a").equals(nfc("\u0430")));
```

Đây là các dòng minh họa trong test có `check` và `nfc` đã được định nghĩa. Các negative assertions ngăn việc “normalizer” thực tế vô tình trở thành phép bỏ dấu, bỏ case hoặc gộp scripts.

## 15. Ma trận test nên có cho một dự án Java

| Nhóm | Input A / B | Kỳ vọng |
| --- | --- | --- |
| Canonical Latin | `café` precomposed / decomposed | Raw khác; NFC và NFD bằng |
| Canonical tiếng Việt | `Vi\u1EC7t` / `Vie\u0323\u0302t` | NFC bằng |
| Dấu kết hợp đảo thứ tự | `a\u0301\u0323` / `a\u0323\u0301` | NFC bằng theo canonical ordering |
| Hangul syllable | `가` / `가` | NFC/NFD đưa về cùng biểu diễn theo form |
| NFKC ligature | `ﬃ` / `ffi` | NFC khác; NFKC bằng |
| NFKC fullwidth | `Ａ` / `A` | NFC khác; NFKC bằng |
| NFKC circled digit | `①` / `1` | NFKC bằng |
| Homoglyph scripts | Latin `a` / Cyrillic `а` | NFKC **vẫn khác** |
| Dấu có ý nghĩa | `ma` / `má` | NFC khác |
| Case | `A` / `a` | NFC khác; case matching riêng |
| Locale | Turkish dotted I và `Locale.ROOT` / `tr` | Case transform có thể khác |
| Grapheme tiếng Việt | Precomposed / combining marks | Code point counts có thể khác, grapheme count thể hiện cụm |
| Emoji supplementary | `🙂` | `length=2`, code points=1 |
| Emoji ZWJ family | Nhiều code points nối ZWJ | Một grapheme trong fixture |
| Storage key | Put NFC, get NFC | Bằng; lookup bằng raw NFD không tự bằng |
| UTF-8 encoding | Hai canonical variants chưa normalize | Raw UTF-8 bytes khác |
| UTF-8 normalized | NFC cả hai rồi UTF-8 | Bytes bằng |
| UTF-8 malformed | Bytes `C3 28` | Strict decoder reject |
| Unpaired surrogate | Invalid UTF-16 sequence | Xử lý theo policy; không coi là scalar value hợp lệ |
| Whitespace | U+0020 vs NBSP U+00A0 | Chỉ gộp nếu policy chủ ý |
| Line endings | LF vs CRLF | Xử lý độc lập, không gọi NFC là đủ |
| Invisible controls | ZWJ/ZWNJ/bidi controls | Không xóa hàng loạt; test allowed-set |
| Database/API integration | Nhập NFD, đọc NFC | Dữ liệu và key nhất quán qua boundary |
| Migration collision | Hai record khác raw nhưng cùng canonical key | Collision được phát hiện/giải quyết công khai |
| Search/collation | Locale cụ thể, accent/case policy | Kết quả phù hợp policy, không suy từ NFC alone |

Mỗi test nên nêu rõ **quan hệ tương đương đang kiểm tra**. Đừng để expectation chung là “chữ nhìn giống” vì đó không phải một định nghĩa có thể áp dụng chắc chắn trong máy tính.

## 16. Property-based và metamorphic testing cho Unicode

Ngoài ví dụ cố định, có thể sinh nhiều chuỗi hợp lệ rồi kiểm tra **bất biến**. Không cần biết từng output normalized cụ thể mới kiểm được các tính chất quan trọng.

### 16.1. Các bất biến cơ bản

Với mọi chuỗi Unicode hợp lệ `s`:

```text
NFC(NFC(s)) == NFC(s)
NFD(NFD(s)) == NFD(s)
NFKC(NFKC(s)) == NFKC(s)
NFKD(NFKD(s)) == NFKD(s)
```

Với mọi cặp `a` và `b` đã biết là canonical equivalents:

```text
NFC(a) == NFC(b)
NFD(a) == NFD(b)
```

Với các chuỗi random, **không** mặc định hai biến thể sinh bằng cách thêm/xóa marks là canonical-equivalent. Phải dùng phép biến đổi hợp lệ để tạo cặp, ví dụ `s` và `NFD(s)`; hoặc dùng dữ liệu chuẩn `NormalizationTest.txt` của Unicode.

### 16.2. Ví dụ property test

```java
import java.text.Normalizer;
import java.util.List;

List<String> samples = List.of(
        "caf\u00E9", "cafe\u0301",
        "Vi\u1EC7t", "Vie\u0323\u0302t",
        "\uFB03", "\uFF21", "\u2460",
        "\uD83D\uDE42"
);

for (String s : samples) {
    String nfc = Normalizer.normalize(
            s, Normalizer.Form.NFC);
    if (!nfc.equals(Normalizer.normalize(
            nfc, Normalizer.Form.NFC))) {
        throw new AssertionError("NFC not idempotent");
    }

    String nfd = Normalizer.normalize(
            s, Normalizer.Form.NFD);
    if (!nfc.equals(Normalizer.normalize(
            nfd, Normalizer.Form.NFC))) {
        throw new AssertionError(
                "NFC after NFD differs from NFC");
    }
}
```

Đây là **đoạn minh họa bên trong một method**; không phải chương trình Java standalone. Nó kiểm tra hai bất biến với sample strings, không tự kết luận mọi cặp sample là tương đương.

### 16.3. Dữ liệu kiểm thử chuẩn Unicode

Unicode Consortium xuất bản conformance data cho normalization (ví dụ **`NormalizationTest.txt`**), mô tả các cột input và expected forms. Một test suite nghiêm túc có thể nạp chính xác file từ một **phiên bản Unicode được xác định**, so đầu ra của implementation theo các quy tắc kiểm thử trong UAX #15.

Lưu ý:

- JDK và Unicode Standard có thể hỗ trợ phiên bản Unicode **khác nhau ở một thời điểm**. Không gắn một dataset có characters mới hơn vào JDK cũ rồi giả định mọi điểm đều có mapping mới.
- Unicode đảm bảo sự ổn định normalization trên những code points đã được gán trong các phiên bản liên quan, nhưng **điểm chưa gán ở JDK cũ** có thể tạo hành vi khác khi chúng được gán ở bản mới.
- Khi nâng JDK, chạy lại normalization conformance test với dataset phù hợp; pin Unicode data version của bất kỳ thư viện ngoài nào nếu nghiệp vụ dựa trên nó.
- Không thay toàn bộ conformance suite bằng vài ví dụ tự chế về dấu tiếng Việt; các combining sequences, composition exclusions, Hangul và edge cases đều quan trọng.

## 17. Tối ưu hóa và phạm vi xử lý

### 17.1. Chuẩn hóa ở ranh giới hệ thống

Nếu mọi phép so sánh đều gọi `Normalizer.normalize` nhiều lần, ứng dụng có thể tốn CPU và cấp phát. Một thiết kế thường dùng:

```text
Nhận input → decode strict → validate → NFC → store/index
                                             │
Request query → decode/validate → NFC ────────┘
                            │
                            ▼
                     String.equals/index lookup
```

Trong cache/DB, có thể lưu **normalized key** theo schema; giữ display text riêng nếu cần. Nhưng **đừng** chuẩn hóa lại data đã ký, payload binary hay identifier có quy tắc định dạng khác mà không tuân thủ giao thức.

### 17.2. Độ dài và giới hạn input

Unicode normalization có thể thay đổi độ dài code points và UTF-16 units. `NFKC` đặc biệt có thể mở rộng một code point thành nhiều ký tự, ví dụ ligature `ﬃ` thành `ffi`.

Vì vậy khi nhận input không tin cậy:

1. Đặt giới hạn **byte size** trước decoding để tránh dữ liệu quá lớn.
2. Dùng strict decoder nếu protocol yêu cầu UTF-8 hợp lệ.
3. Chuẩn hóa theo form được định nghĩa.
4. Kiểm tra **độ dài sau chuẩn hóa** theo giới hạn của normalized keys/DB schema.
5. Kiểm tra script/allowed characters/collision theo policy.
6. Hạn chế công việc regex/collation đắt đỏ đối với input dài; không tạo normalized copies vô hạn trong vòng lặp.

Không xem `Normalizer` như cơ chế chống DoS độc lập; nó thực hiện transform cần thiết, không thay thế resource limits.

### 17.3. Regex `CANON_EQ` có thể tốn tài nguyên

Java `Pattern.CANON_EQ` cho phép regex matching xét canonical equivalence, nhưng tài liệu JDK hiện hành cảnh báo **hiệu năng và nguy cơ dùng nhiều bộ nhớ**, kể cả trường hợp quá nhiều combining marks.

Ví dụ minh họa:

```java
import java.util.regex.Pattern;

boolean match = Pattern.compile(
        "a\u030A", Pattern.CANON_EQ)
        .matcher("\u00E5")
        .matches();
// true
```

Nếu mục tiêu của bạn chỉ là so sánh/tìm trên text đã xác định dạng, thường **normalize dữ liệu và pattern theo cùng policy trước** dễ kiểm soát và test hơn việc bật `CANON_EQ` cho mọi regex từ người dùng. Không coi `CANON_EQ` là cách thay thế validation input hoặc limit độ dài.

## 18. Cách giải quyết bug thực tế theo từng triệu chứng

### 18.1. “Trên màn hình giống mà HashMap.get trả null”

Đo code point hex của key từ phía `put` và `get`. Nếu một bên có `U+00E9`, bên kia có `U+0065 U+0301`, định nghĩa canonical key bằng NFC ở **cả hai đường**. Viết regression test từ input API thật và data được lưu; không chỉ sửa một phía.

### 18.2. “Tên tiếng Việt nhập từ điện thoại không tìm được”

Đừng vội dùng `replaceAll("\\p{M}", "")` để xóa mọi dấu: có thể làm mất ý nghĩa tiếng Việt. Trước hết thử **NFC input và search key**, kiểm tra DB collation, UTF-8 decode, tiền xử lý whitespace. Nếu sản phẩm thật sự cần search không dấu, thiết kế **một index thứ cấp** có contract rõ và test false positives.

### 18.3. “Đếm ký tự emoji sai”

`String.length()` là UTF-16 unit count, không phải số glyph. Dùng `codePointCount` khi business rule là code points, hoặc grapheme segmentation khi business rule là các cụm người dùng nhận biết. Test emoji supplementary và ZWJ sequences, không chỉ ASCII.

### 18.4. “NFKC gộp hai account names vốn khác nhau”

Đây là **collision do policy** chứ không phải lỗi của Normalizer. Kiểm tra xem domain có thật sự nên dùng compatibility folding không. Với migration, đừng overwrite dữ liệu: phát hiện collisions, quyết định owner/alias/rename theo quy trình sản phẩm, và giữ audit trail phù hợp.

### 18.5. “Đổi JVM locale làm test không còn pass”

Kiểm tra code đang gọi `String.toLowerCase()` hoặc `Collator.getInstance()` không tham số. Pin `Locale` theo yêu cầu sản phẩm. Tách normalization tests (thường deterministic trên code points đã biết) khỏi locale-specific collation tests.

### 18.6. “UTF-8 trông đúng nhưng hash khác”

Hex-dump bytes. Có thể input đã khác canonical form, có BOM, có line ending khác hoặc serialization khác. Khác `hash` của bytes **không tự chứng minh** lỗi mật mã; trước hết xác định đúng canonical payload bytes theo giao thức.

### 18.7. “Một vài Unicode test fail sau nâng JDK”

Ghi rõ `java.version`, Unicode data version (nếu truy xuất qua dữ liệu build/implementation), normalized form, input code points và expected dataset version. Kiểm tra ký tự mới được Unicode gán sau version JDK cũ, grapheme segmentation rules hoặc locale data thay đổi. Không đổi expected chỉ để làm test xanh nếu hợp đồng nghiệp vụ vẫn như cũ.

## 19. Lỗi phổ biến cần tránh

**1. So Unicode bằng cách nhìn glyph trên màn hình.**  
Rendering phụ thuộc font, platform và cách nhập; test phải xem code points và bytes.

**2. Coi `String.equals` tự hiểu canonical equivalence.**  
Nó so chuỗi code units. Normalize về **cùng form** nếu domain yêu cầu canonical equivalence.

**3. Dùng NFC như bộ bỏ dấu hoặc bộ chuyển chữ hoa/thường.**  
NFC không phải accent-stripping hay case-folding; các phép này làm thay đổi quan hệ so sánh.

**4. Dùng NFKC cho mọi text chỉ vì “mạnh hơn”.**  
NFKC làm mất compatibility distinctions như ligature/fullwidth/circled digit; chỉ dùng khi có policy phù hợp.

**5. Coi mọi homoglyph là cùng ký tự.**  
Latin `a` và Cyrillic `а` vẫn khác sau NFKC. Dùng confusable-aware policy nếu có nguy cơ spoofing.

**6. Tự sort combining marks bằng code point.**  
Canonical reordering dựa vào combining class và các quy tắc Unicode, không phải sort numeric tùy ý.

**7. Coi `String.length` là số ký tự hiển thị.**  
Một emoji có thể chiếm hai UTF-16 code units; một grapheme có thể có nhiều code points.

**8. Cắt string giữa surrogate pair hoặc combining sequence.**  
Có thể tạo text lỗi hoặc phá hiển thị. Chọn ranh giới code point/grapheme theo yêu cầu.

**9. Dùng `getBytes()` không chỉ định charset trong test byte-level.**  
Có thể phụ thuộc charset mặc định của môi trường. Dùng `StandardCharsets.UTF_8` và kiểm thử bytes cụ thể.

**10. Cho rằng UTF-8 round-trip tự normalize.**  
Encode/decode hợp lệ giữ nội dung, không chuyển NFD thành NFC trừ khi có bước normalization riêng.

**11. Không validate malformed UTF-8 khi protocol bắt buộc dữ liệu chuẩn.**  
Đặt `CodingErrorAction.REPORT` để phát hiện thay vì âm thầm thay ký tự lỗi.

**12. Chỉ normalize lúc insert, quên normalize lúc lookup.**  
HashMap/DB/cache/search index có thể trả kết quả không đồng nhất.

**13. Đặt locale mặc định ngầm định trong test.**  
Case mapping/collation có thể khác giữa hệ thống. Chỉ định `Locale` khi cần.

**14. Dùng `Collator.PRIMARY` như định nghĩa key equality cho mọi người.**  
Collator là so sánh theo ngôn ngữ, có thể bỏ qua nhiều khác biệt hơn canonical equivalence.

**15. Biến pass positive test thành phép khẳng định sanitizer đúng.**  
Thêm negative tests: accents khác, case khác, khác script, ký tự vô hình và collision.

**16. Xóa ZWJ/ZWNJ hàng loạt.**  
Có thể phá emoji, tiếng viết cần joiner hoặc chính sách ngôn ngữ. Chỉ lọc theo allowed-set có test.

**17. Dùng regex `CANON_EQ` trên input dài không giới hạn.**  
Javadoc nêu rủi ro memory và hiệu năng. Áp resource limits và ưu tiên normalize trước khi so.

**18. Gộp normalization với byte-order mark hoặc line-ending conversion.**  
BOM và newline là những quy tắc khác, cần bước xử lý và test riêng.

**19. Đổi normalization khi dữ liệu đã được ký/hash mà không cập nhật contract.**  
Signature/checksum trên bytes có thể thay đổi. Phải định nghĩa canonicalization **trước bước ký** khi giao thức cho phép.

**20. Không kiểm tra phiên bản Unicode của dữ liệu conformance.**  
Unicode và JDK tiến hóa; khi test code points mới, phải kiểm tra version support và tính ổn định chuẩn.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Hai chuỗi `"\u00E9"` và `"e\u0301"` có `String.equals` bằng nhau không?  
**Không.** Nhưng NFC hoặc NFD của hai chuỗi bằng nhau vì chúng canonically equivalent.

**Câu 2.** Nếu hai chuỗi NFC bằng nhau thì UTF-8 bytes của chúng sau khi encode NFC có bằng nhau không?  
**Có**, khi cùng encoder UTF-8 và input hợp lệ, bởi chuỗi normalized code points giống hệt nhau.

**Câu 3.** NFKC có gộp `ﬃ` với `ffi` không?  
**Có.** Nhưng NFC không làm điều đó; đây là compatibility equivalence, cần policy nghiệp vụ.

**Câu 4.** NFKC có gộp Latin `a` với Cyrillic `а` không?  
**Không.** Visually confusable không đồng nghĩa Unicode compatibility equivalence.

**Câu 5.** `String.length` của `🙂` là bao nhiêu?  
**2** UTF-16 code units; `codePointCount` là **1**.

**Câu 6.** `"e\u0301"` là một hay hai code points?  
**2 code points**, nhưng thường là **1 extended grapheme cluster**.

**Câu 7.** Vì sao `HashMap.get(decomposed)` có thể trả `null` khi `put(composed)` đã lưu cùng chữ hiển thị?  
Vì raw key equality khác. Normalize key theo cùng form ở cả hai thao tác.

**Câu 8.** Có nên chuẩn hóa toàn bộ user-generated text bằng NFKC để “an toàn” không?  
**Không mặc định.** NFKC có thể xóa khác biệt có ý nghĩa; security còn cần confusable/script policies khác.

**Câu 9.** `Normalizer.isNormalized(s, NFC)` và `Normalizer.normalize(s, NFC)` khác gì?  
Phương thức đầu **kiểm tra boolean**; phương thức sau **trả String** đã normalization.

**Câu 10.** `Collator` có thay thế `Normalizer` khi tạo canonical storage key không?  
**Không.** Collator phục vụ so sánh theo locale; normalized key cần quy tắc nhất quán riêng.

**Câu 11.** Khi input UTF-8 malformed, muốn nhận lỗi thay vì replacement char thì làm gì?  
Dùng `CharsetDecoder` với `onMalformedInput(CodingErrorAction.REPORT)`.

**Câu 12.** Một test Unicode tốt nên có các nhóm nào?  
Canonical positive pairs, compatibility pairs **theo policy**, negative pairs không được gộp, length/grapheme, byte round-trip/invalid bytes, locale, storage/search integration và collision regression.

## Nguồn tham khảo chính thức và đang được duy trì

- [Oracle Java SE 26 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): bốn forms NFC/NFD/NFKC/NFKD, `normalize`, `isNormalized`.
- [Oracle Java SE 26 — `java.lang.String`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): UTF-16 semantics, `length`, `codePointCount`, `codePoints`, equality và case mapping.
- [Oracle Java SE 26 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): `\\X` extended grapheme cluster, `CANON_EQ`, các cảnh báo về performance và memory.
- [Oracle Java SE 26 — `java.text.Collator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html): so sánh locale-sensitive, decomposition modes và comparison strengths.
- [Oracle Java SE 26 — `java.nio.charset.CharsetDecoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html), [`CodingErrorAction`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html) và [`StandardCharsets`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): strict UTF-8 decoding và charset xác định.
- [Unicode 18.0 — UAX #15 Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): đặc tả canonical/compatibility equivalence và tính ổn định normalization.
- [Unicode — Normalization FAQ](https://www.unicode.org/faq/normalization.html): giải thích mục tiêu, use cases và khác biệt giữa NFC/NFD với NFKC/NFKD.
- [Unicode — UAX #29 Text Segmentation](https://www.unicode.org/reports/tr29/): quy tắc xác định grapheme cluster boundaries.
- [Unicode — UTS #39 Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): confusables và các biện pháp kiểm soát định danh Unicode khi có yêu cầu bảo mật.

**Ghi nhớ:** “Cùng nội dung” cần được định nghĩa thành **một quan hệ có thể kiểm thử**. Với canonical-equivalent text, dùng NFC/NFD của Java để đưa nhiều biểu diễn về cùng dạng. Với compatibility, case/locale, visual confusables, grapheme hoặc bytes, mỗi tầng có quy tắc riêng. Một bộ kiểm thử tốt không chỉ chứng minh thứ **phải bằng nhau**, mà còn bảo vệ những khác biệt **phải giữ nguyên**.
