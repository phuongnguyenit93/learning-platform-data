# Normalizer với NFC, NFD, NFKC và NFKD trong Java

Hai chuỗi Unicode có thể **trông giống hệt nhau** nhưng chứa **dãy mã Unicode khác nhau**. Ví dụ chữ `é` có thể là một code point dựng sẵn `U+00E9` hoặc hai code point `U+0065` (chữ e) và `U+0301` (dấu sắc kết hợp). Java `String.equals()` so sánh nội dung chuỗi theo các đơn vị mã UTF-16, nên hai cách biểu diễn này không tự động bằng nhau. Hệ quả xuất hiện khi tìm kiếm, so khóa bản ghi, lưu tên, đối chiếu nội dung từ thiết bị khác nhau và xử lý tiếng Việt có dấu.

`java.text.Normalizer` giải quyết một phần vấn đề bằng **bốn dạng chuẩn hóa Unicode** theo Unicode Standard Annex #15:

- **NFC:** phân rã chuẩn tắc rồi ghép lại khi có thể (*canonical composition*).
- **NFD:** phân rã chuẩn tắc (*canonical decomposition*).
- **NFKC:** phân rã **tương thích** rồi ghép lại khi có thể (*compatibility decomposition + canonical composition*).
- **NFKD:** phân rã **tương thích** (*compatibility decomposition*).

Điều quan trọng hơn việc nhớ tên là **chọn đúng dạng theo ý nghĩa dữ liệu**. NFC/NFD giữ phân biệt theo *canonical equivalence*; NFKC/NFKD có thể **gộp những cách viết chỉ tương đương về tương thích** và làm mất những khác biệt ký tự có ý nghĩa. Normalization **không phải** dịch ngôn ngữ, bỏ dấu tiếng Việt, đổi chữ hoa/thường hay chống giả mạo ký tự một cách toàn diện.

Bài học sử dụng **Java 17+**, các ví dụ chạy độc lập và chuỗi escape Unicode để đầu ra kiểm chứng được trên máy khác nhau.

## 1. Unicode có thể biểu diễn cùng văn bản bằng nhiều dãy code point

Xét chữ Latin `é`:

```text
Cách A: U+00E9               LATIN SMALL LETTER E WITH ACUTE
Cách B: U+0065 U+0301        LATIN SMALL LETTER E
                              + COMBINING ACUTE ACCENT
Cách nhìn trên màn hình:      é      é
So sánh String.equals():     false (khi chưa chuẩn hóa)
```

Dù trình render thường vẽ hai dạng rất giống nhau, máy tính nhìn thấy hai dãy code point khác nhau. Với `String` trong Java, code point ở vùng BMP thường chiếm một **đơn vị mã UTF-16**; ký tự ngoài BMP có thể chiếm **hai đơn vị mã** (một cặp surrogate). Vì thế:

- `String.length()` trả số **đơn vị mã UTF-16**, không nhất thiết là số Unicode code point.
- `String.codePoints()` duyệt theo code point, hữu ích khi kiểm tra biểu diễn Unicode.
- Số code point vẫn **không** đồng nghĩa số ký tự người dùng cảm nhận (*grapheme clusters*), vì một chữ với nhiều dấu kết hợp hoặc một emoji ghép có thể gồm nhiều code point.

Chuẩn hóa tác động lên **dãy Unicode**, không dựa vào việc các glyph có trông giống nhau trong một font cụ thể hay không.

### Canonical equivalence

Unicode xác định một số dãy khác nhau là **tương đương chuẩn tắc** (*canonically equivalent*). Ví dụ `U+00E9` và `U+0065 U+0301`. `NFC` và `NFD` giúp đưa những dãy canonically equivalent vào **cùng một dạng chuẩn**, từ đó có thể so sánh bằng chuỗi thường khi **cả hai phía đã dùng cùng dạng**.

Đừng cố tự liệt kê “chữ có dấu” rồi thay thủ công. Chuẩn Unicode còn có **thứ tự chuẩn của các dấu kết hợp** (*canonical ordering*) và những quy tắc ghép phức tạp, nên hãy dùng bộ chuẩn hóa đã được triển khai theo tiêu chuẩn.

## 2. Bốn dạng chuẩn hóa: C, D và chữ K có ý nghĩa gì?

| Form | Viết đầy đủ | Phân rã | Ghép lại | Loại tương đương |
| --- | --- | --- | --- | --- |
| `NFD` | Normalization Form D | Canonical | Không | Chuẩn tắc |
| `NFC` | Normalization Form C | Canonical | Có, khi quy tắc cho phép | Chuẩn tắc |
| `NFKD` | Normalization Form KD | Compatibility | Không | Tương thích và chuẩn tắc |
| `NFKC` | Normalization Form KC | Compatibility | Có, khi quy tắc cho phép | Tương thích và chuẩn tắc |

- **`D`** = *decomposition*, phân rã.
- **`C`** = *composition*, ghép sau phân rã và sắp xếp theo quy tắc.
- **`K`** = *compatibility*, cho phép nhiều ánh xạ bổ sung vượt ra ngoài canonical equivalence.

Chữ `K` **không** có nghĩa “phân rã sâu hơn một chút nhưng vẫn hoàn toàn giữ nghĩa”. Compatibility mapping có thể thay những ký tự mang phong cách biểu diễn đặc biệt bằng các ký tự thông thường, ví dụ dấu tròn quanh số, chữ fullwidth hay ligature trình bày.

### Bảng quan sát minh họa

| Ký tự nguồn | NFC | NFD | NFKC | NFKD |
| --- | --- | --- | --- | --- |
| `é` (U+00E9) | `é` | `e` + U+0301 | `é` | `e` + U+0301 |
| `ﬁ` (U+FB01, ligature fi) | `ﬁ` | `ﬁ` | `fi` | `fi` |
| `①` (U+2460) | `①` | `①` | `1` | `1` |
| `Ａ` (U+FF21, fullwidth A) | `Ａ` | `Ａ` | `A` | `A` |

Với `é`, tất cả bốn dạng bảo toàn canonical equivalence và các giá trị đầu ra khác nhau về **dãy code point**, không nhất thiết về cách nhìn. Với `ﬁ`, `①` và `Ａ`, chỉ **NFKC/NFKD** xử lý compatibility mapping như trên. Đây là ví dụ rõ về nguy cơ **gộp dữ liệu** nếu chọn NFKC một cách thiếu cân nhắc.

Không có quy tắc “NFKC luôn cho chuỗi ngắn nhất”: việc phân rã/tái ghép có thể làm chuỗi dài hoặc ngắn tùy dữ liệu. Cũng không nên hứa NFC luôn ghép thành một code point: không phải mọi dãy có dấu đều có ký tự dựng sẵn.

## 3. API java.text.Normalizer và các Form

Trong Java 17+, lớp tiêu chuẩn là **`java.text.Normalizer`**, không phải `java.text.NumberFormat` hay một API chuyển charset.

```java
import java.text.Normalizer;

String result = Normalizer.normalize(text, Normalizer.Form.NFC);
boolean already = Normalizer.isNormalized(text, Normalizer.Form.NFC);
```

Đây là **fragment** trong một phương thức: `text` là chuỗi đã khai báo.

Hai phương thức chính:

| API | Công dụng |
| --- | --- |
| `Normalizer.normalize(CharSequence src, Normalizer.Form form)` | Trả về `String` ở dạng chuẩn hóa được yêu cầu |
| `Normalizer.isNormalized(CharSequence src, Normalizer.Form form)` | Kiểm tra một chuỗi đã ở form yêu cầu hay chưa |
| `Normalizer.Form.NFC` | Canonical decomposition + composition |
| `Normalizer.Form.NFD` | Canonical decomposition |
| `Normalizer.Form.NFKC` | Compatibility decomposition + composition |
| `Normalizer.Form.NFKD` | Compatibility decomposition |

`Normalizer` dùng các quy tắc Unicode tích hợp trong runtime Java. Với đầu vào `null`, không coi kết quả là chuỗi rỗng: cần xử lý null theo hợp đồng ứng dụng (API có thể ném `NullPointerException`). Kết quả `String` mới **không làm biến đổi** đối tượng `String` gốc vì `String` immutable.

### Khi nào dùng isNormalized?

Nếu hợp đồng input yêu cầu **đầu vào đã ở NFC**, dùng `isNormalized(...)` để **từ chối** biểu diễn khác hoặc normalize tường minh rồi lưu. Hai chính sách không giống nhau:

- **Accept + normalize:** ứng dụng chấp nhận nhiều biểu diễn canonically equivalent rồi đưa về NFC khi lưu.
- **Require normalized:** giao thức đòi bên gửi đã chuẩn hóa; ứng dụng từ chối input không đúng form, hữu ích cho dữ liệu ký số hoặc khi hợp đồng cần byte ổn định.

Chọn một trong hai và ghi rõ tại ranh giới API. Nếu dữ liệu có chữ ký số hoặc MAC, **không được âm thầm normalize sau bước kiểm chứng chữ ký**: thay đổi code point làm thay đổi byte được ký, dù biểu diễn màn hình tương tự.

## 4. Demo chạy được: NFC và NFD khắc phục khác biệt code point

Lưu file **`CanonicalFormsDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CanonicalFormsDemo {
    private static String codePoints(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equal: "
                + composed.equals(decomposed));
        System.out.println("NFC equal: "
                + Normalizer.normalize(composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));
        System.out.println("NFD composed: "
                + codePoints(Normalizer.normalize(
                        composed, Normalizer.Form.NFD)));
        System.out.println("NFC decomposed: "
                + codePoints(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac -encoding UTF-8 CanonicalFormsDemo.java
java CanonicalFormsDemo
```

Stdout:

```text
Raw equal: false
NFC equal: true
NFD composed: U+0065 U+0301
NFC decomposed: U+00E9
```

Với `NFC`, dãy `e` + dấu sắc được ghép thành `é` dựng sẵn vì Unicode định nghĩa canonical composition phù hợp. Với `NFD`, ký tự dựng sẵn `é` phân rã thành `e` + dấu sắc. Hai đường đều cho kết quả **cùng form** nếu các dãy đầu vào canonically equivalent.

`String.format("U+%04X", cp)` in giá trị số code point dưới dạng hệ thập lục phân, không phải font glyph; cách kiểm tra này tốt hơn chỉ nhìn màn hình khi phát hiện lỗi Unicode.

## 5. NFC và NFD với tiếng Việt có nhiều dấu

Tiếng Việt thường có các nguyên âm với nhiều thành phần dấu. Một ví dụ là **`ắ`**, code point dựng sẵn `U+1EAF` (*LATIN SMALL LETTER A WITH BREVE AND ACUTE*):

```text
Dạng dựng sẵn:       U+1EAF                 ắ
Dạng phân rã NFD:    U+0061 U+0306 U+0301  a + breve + acute
Dạng NFC của NFD:   U+1EAF                 ắ
```

Các thành phần:

- `U+0061`: chữ `a`.
- `U+0306`: **COMBINING BREVE**, dấu trăng.
- `U+0301`: **COMBINING ACUTE ACCENT**, dấu sắc.

Khi render, nhiều font có thể vẽ dãy phân rã giống ký tự dựng sẵn. Nhưng độ dài Java khác nhau: `"\u1EAF".length()` là 1, còn `"a\u0306\u0301".length()` là 3, vì cả ba code point ở vùng BMP.

**File `VietnameseFormsDemo.java`**:

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class VietnameseFormsDemo {
    private static String codePoints(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String word = "\u1EAF";
        String nfd = Normalizer.normalize(
                word, Normalizer.Form.NFD);
        String nfc = Normalizer.normalize(
                nfd, Normalizer.Form.NFC);

        System.out.println("Original: " + codePoints(word));
        System.out.println("NFD: " + codePoints(nfd));
        System.out.println("NFC back: " + codePoints(nfc));
        System.out.println("Lengths: " + word.length()
                + " / " + nfd.length());
        System.out.println("Equal after NFC: "
                + word.equals(nfc));
    }
}
```

```bash
javac -encoding UTF-8 VietnameseFormsDemo.java
java VietnameseFormsDemo
```

Stdout:

```text
Original: U+1EAF
NFD: U+0061 U+0306 U+0301
NFC back: U+1EAF
Lengths: 1 / 3
Equal after NFC: true
```

**Ý nghĩa thực tế:** nếu một người dùng nhập tên tiếng Việt bằng bàn phím tạo tổ hợp dấu, còn bên khác lưu ký tự dựng sẵn, so sánh byte hoặc `String.equals` trực tiếp có thể thất bại. Khi cả hai bên normalize về **NFC**, các trường hợp canonically equivalent được đối chiếu nhất quán hơn.

Đồng thời, **NFD không phải “bỏ dấu tiếng Việt”**: nó **giữ các dấu dưới dạng combining marks**. Xóa những dấu kết hợp sau NFD là một thao tác **khác**, có thể biến `"má"` thành `"ma"`, thay đổi nội dung và nghĩa. Nếu sản phẩm cung cấp tìm kiếm không dấu, đó phải là một **search policy tường minh**, không phải mặc định lưu trữ.

## 6. Demo chạy được: NFKC và NFKD thay đổi ký tự tương thích

Hai ví dụ **`ﬁ`** (ligature hai chữ f-i) và **`①`** (số 1 trong vòng tròn) cho thấy khác biệt rõ. Với NFC/NFD, chúng không bị thay thành chữ thường; NFKC/NFKD cho phép compatibility mapping.

**File `CompatibilityFormsDemo.java`:**

```java
import java.text.Normalizer;
import java.util.stream.Collectors;

public class CompatibilityFormsDemo {
    private static String cps(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String ligature = "\uFB01";
        String circled = "\u2460";
        String fullwidth = "\uFF21";

        System.out.println("Ligature NFC: " + cps(
                Normalizer.normalize(ligature, Normalizer.Form.NFC)));
        System.out.println("Ligature NFKC: " + cps(
                Normalizer.normalize(ligature, Normalizer.Form.NFKC)));
        System.out.println("Circled NFC: " + cps(
                Normalizer.normalize(circled, Normalizer.Form.NFC)));
        System.out.println("Circled NFKD: " + cps(
                Normalizer.normalize(circled, Normalizer.Form.NFKD)));
        System.out.println("Fullwidth NFKC: " + cps(
                Normalizer.normalize(fullwidth, Normalizer.Form.NFKC)));
        System.out.println("NFKC(fi) equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC)
                        .equals("fi"));
    }
}
```

```bash
javac -encoding UTF-8 CompatibilityFormsDemo.java
java CompatibilityFormsDemo
```

Stdout:

```text
Ligature NFC: U+FB01
Ligature NFKC: U+0066 U+0069
Circled NFC: U+2460
Circled NFKD: U+0031
Fullwidth NFKC: U+0041
NFKC(fi) equal: true
```

**Không hiểu đây là phép biến đổi chỉ để tiết kiệm byte.** Nó có thể làm mất phân biệt giữa `ﬁ` và `fi`, giữa ký tự trang trí `①` và chữ số `1`, giữa chữ fullwidth và ASCII. Những phân biệt ấy có thể quan trọng trong văn bản gốc, tên thương hiệu, biểu thức toán học, văn bản pháp lý hoặc yêu cầu lưu giữ nguyên văn.

NFKC hữu ích cho những trường có **chính sách định danh** cho phép gộp các biến thể compatibility, hoặc tạo **khóa tìm kiếm thứ cấp**; nhưng hãy cân nhắc quy tắc Unicode identifier và bảo mật riêng của miền ứng dụng. **Không mặc nhiên đổi mọi dữ liệu sang NFKC khi lưu.**

## 7. NFKC và NFKD không phải lowercasing, transliteration hay bỏ dấu

Một số thao tác khác cần phân biệt:

| Thao tác | Ví dụ | Có thuộc trách nhiệm của Normalizer? |
| --- | --- | --- |
| Canonical normalization | `e` + U+0301 → `é` dưới NFC | Có |
| Compatibility normalization | `ﬁ` → `fi` dưới NFKC | Có |
| Chuyển chữ hoa thành chữ thường | `ABC` → `abc` | Không |
| Bỏ dấu | `má` → `ma` | Không; đây là chuyển đổi khác |
| Chuyển hệ chữ | Chữ Cyrillic sang Latin | Không |
| Phát hiện chữ trông giống nhau | `a` Latin và `а` Cyrillic | Không đầy đủ; cần confusable checks riêng |
| Chuyển encoding | UTF-8 bytes → ký tự Unicode | Không, thuộc decoder |
| Dịch từ ngữ | `hello` → `xin chào` | Không |
| Ghép emoji thành một code point | Emoji nhiều code point → một code point | Không phải mục tiêu |

NFKC **không** tự biến `"ABC"` thành `"abc"`. Nếu cần so sánh không phân biệt hoa/thường, phải xác định một **case policy** riêng. `String.toLowerCase(Locale.ROOT)` hỗ trợ một số nhu cầu case-insensitive kỹ thuật nhưng **không tương đương đầy đủ với Unicode Default Case Folding** và không thay thế chuẩn bảo mật cho username/domain.

Tương tự, NFKD thường được dùng như một **bước đầu** trong pipeline tìm kiếm không dấu, vì nó phân rã chữ và dấu. Nhưng xóa tất cả combining marks có thể làm mất những phân biệt chữ viết quan trọng, không giải quyết đầy đủ mọi dấu/biến thể chữ và không được sử dụng bừa bãi cho dữ liệu gốc.

## 8. Normalizer.isNormalized: kiểm tra và tính idempotent

Một tính chất căn bản của chuẩn hóa Unicode là **idempotence**: với form F nhất định, normalize một chuỗi đã ở form F thêm lần nữa **không làm thay đổi** nó.

```text
F(F(text)) == F(text)
```

Tuy nhiên, **một chuỗi được chuẩn hóa riêng lẻ và một chuỗi khác cũng chuẩn hóa riêng lẻ chưa chắc khi ghép lại vẫn ở cùng form**. Ví dụ `"e"` đã là NFC, dấu sắc kết hợp `"\u0301"` riêng lẻ cũng là NFC; nhưng `"e\u0301"` sau khi ghép **không phải NFC**, vì có thể ghép thành `é`.

**Chương trình `NormalizationCheckDemo.java`:**

```java
import java.text.Normalizer;

public class NormalizationCheckDemo {
    public static void main(String[] args) {
        String base = "e";
        String mark = "\u0301";
        String joined = base + mark;

        System.out.println("Base NFC: "
                + Normalizer.isNormalized(base, Normalizer.Form.NFC));
        System.out.println("Mark NFC: "
                + Normalizer.isNormalized(mark, Normalizer.Form.NFC));
        System.out.println("Joined NFC: "
                + Normalizer.isNormalized(joined, Normalizer.Form.NFC));

        String normalized = Normalizer.normalize(
                joined, Normalizer.Form.NFC);
        System.out.println("Normalized NFC: "
                + Normalizer.isNormalized(
                        normalized, Normalizer.Form.NFC));
        System.out.println("Idempotent: "
                + normalized.equals(Normalizer.normalize(
                        normalized, Normalizer.Form.NFC)));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationCheckDemo.java
java NormalizationCheckDemo
```

Stdout:

```text
Base NFC: true
Mark NFC: true
Joined NFC: false
Normalized NFC: true
Idempotent: true
```

Vì vậy, nếu hệ thống nối những chuỗi Unicode ở thời điểm khác nhau, **không được suy luận** chuỗi tổng vẫn luôn NFC/NFD/NFKC/NFKD chỉ vì các mảnh đã chuẩn hóa riêng. Hãy kiểm tra hoặc normalize ở ranh giới **giá trị cuối cùng** mà ứng dụng xác định.

**Hiệu năng:** `isNormalized` có thể giúp bỏ qua thao tác tạo chuỗi khi input đã ở form mục tiêu, nhưng cũng có chi phí duyệt dữ liệu. Khi cần hiệu năng cao, hãy benchmark với dữ liệu thật; không tự viết một bộ nhận diện đơn giản dựa trên kiểm tra dấu ASCII hoặc dấu kết hợp.

## 9. UTF-8 và normalization là hai tầng khác nhau

Một số nhầm tưởng: “Nếu hai chuỗi đều dùng UTF-8 thì chúng sẽ giống nhau.” Điều này **không đúng**.

UTF-8 xác định cách chuyển **code point** sang **byte**. Unicode normalization xác định cách lựa chọn các **dãy code point tương đương**. Hai chuỗi canonically equivalent có thể cùng là UTF-8 hợp lệ nhưng cho **byte khác nhau**:

```text
"é" dựng sẵn (U+00E9):
  UTF-8: C3 A9

"e" + dấu sắc (U+0065 U+0301):
  UTF-8: 65 CC 81

Cả hai đều là UTF-8 hợp lệ.
So sánh byte thô: khác nhau.
So sánh sau NFC: cùng U+00E9 → cùng UTF-8 C3 A9.
```

**File `NormalizationAndUtf8Demo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

public class NormalizationAndUtf8Demo {
    public static void main(String[] args) {
        String first = "\u00E9";
        String second = "e\u0301";

        boolean before = Arrays.equals(
                first.getBytes(StandardCharsets.UTF_8),
                second.getBytes(StandardCharsets.UTF_8));

        boolean after = Arrays.equals(
                Normalizer.normalize(first, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8),
                Normalizer.normalize(second, Normalizer.Form.NFC)
                        .getBytes(StandardCharsets.UTF_8));

        System.out.println("UTF-8 equal before: " + before);
        System.out.println("UTF-8 equal after NFC: " + after);
    }
}
```

```bash
javac -encoding UTF-8 NormalizationAndUtf8Demo.java
java NormalizationAndUtf8Demo
```

Stdout:

```text
UTF-8 equal before: false
UTF-8 equal after NFC: true
```

**Lời khuyên:** hệ thống mới thường chọn UTF-8 làm encoding và **NFC** làm normalization policy cho văn bản người dùng thông thường. Hai quyết định cần **được khai báo riêng** trong hợp đồng dữ liệu. Không trông đợi việc `Files.readString(path, UTF_8)`, `getBytes(UTF_8)` hay đọc JSON sẽ tự động normalize nội dung.

## 10. Ứng dụng: so sánh, tìm kiếm, khóa database và dữ liệu tên người

### So sánh chuỗi Unicode thông thường

Nếu cần hai cách viết canonically equivalent được xem là cùng văn bản:

```java
static boolean canonicalEquals(String a, String b) {
    return Normalizer.normalize(a, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(b, Normalizer.Form.NFC));
}
```

Đây là **fragment bên trong class Java**, cần import `java.text.Normalizer`; nó giả định `a` và `b` không null. Tốt hơn, nếu có thể chuẩn hóa **một lần tại ranh giới input/storage**, thì những lần so sánh sau không cần lặp normalize mọi khi.

**Không tự thay thế mọi phép so sánh String.equals**: với password, token, giá trị ký số, mã máy, hash hay identifier có hợp đồng byte cụ thể, chuẩn hóa ngoài chính sách có thể **đổi danh tính của chuỗi**. Mỗi miền dữ liệu cần định nghĩa equivalence và collision policy riêng.

### Khóa database và UNIQUE constraint

Nếu ứng dụng dùng NFC làm chuẩn của trường `displayName` hoặc `userHandle`, có hai phương án thường gặp:

1. **Lưu NFC và kiểm tra uniqueness trên cột chuẩn hóa** theo lược đồ/chiến lược collation đã chọn.
2. **Giữ nguyên bản gốc** để hiển thị/audit, và lưu **cột khóa tra cứu** đã normalize theo policy; uniqueness đặt trên cột khóa nếu nghiệp vụ đòi duy nhất.

Cần lưu ý **database collation** có thể thực hiện so sánh khác với `String.equals` hoặc Java Normalizer (theo case/accent/Unicode version). Vì vậy, không khẳng định `UNIQUE` của mọi database tự hiểu Unicode canonical equivalence. Phải kiểm thử với hệ quản trị và collation triển khai thực tế.

### Tìm kiếm “lỏng” và nội dung gốc

Một hệ thống search có thể tạo chỉ mục secondary theo NFKC, lowercasing hoặc quy tắc xử lý dấu riêng. Nhưng chuỗi gốc nên được giữ khi cần fidelity, và **hai đầu vào khác nhau có thể va chạm thành cùng khóa**. Ví dụ `ﬁ` và `fi` có thể trở thành cùng `fi` dưới NFKC. Nếu đó là username hoặc mã định danh, phải quyết định **ai được sở hữu khóa sau chuẩn hóa** và liệu có từ chối/ghi log xung đột.

Không dùng NFKC một cách mù quáng để “làm sạch” văn bản đa ngôn ngữ; việc gộp compatibility có thể ảnh hưởng ngữ nghĩa, ký hiệu toán học, dữ liệu thương hiệu hay văn bản được pháp luật yêu cầu lưu nguyên bản.

## 11. Demo rủi ro va chạm khóa dưới NFKC

**File `NormalizationCollisionDemo.java`:**

```java
import java.text.Normalizer;

public class NormalizationCollisionDemo {
    public static void main(String[] args) {
        String ligature = "\uFB01";
        String plain = "fi";

        System.out.println("Raw equal: "
                + ligature.equals(plain));
        System.out.println("NFC equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                plain, Normalizer.Form.NFC)));
        System.out.println("NFKC equal: "
                + Normalizer.normalize(ligature, Normalizer.Form.NFKC)
                        .equals(Normalizer.normalize(
                                plain, Normalizer.Form.NFKC)));
        System.out.println("Case unchanged: "
                + Normalizer.normalize("ABC", Normalizer.Form.NFKC)
                        .equals("ABC"));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationCollisionDemo.java
java NormalizationCollisionDemo
```

Stdout:

```text
Raw equal: false
NFC equal: false
NFKC equal: true
Case unchanged: true
```

**Diễn giải:** NFKC tạo **cùng khóa** cho hai chuỗi mà NFC vẫn coi là khác. Đây có thể là hành vi được mong muốn khi so tìm kiếm hoặc cho một hệ định danh đã quy định rõ, nhưng cũng có thể tạo **collision** ngoài ý định. Không dùng riêng NFKC như cơ chế chống giả mạo. Với Unicode security, còn cần chính sách giới hạn ký tự, kiểm tra scripts và confusables theo hệ thống như Unicode Technical Standard #39 khi miền ứng dụng yêu cầu.

## 12. Dùng Normalizer ở đâu trong luồng dữ liệu?

Một luồng xử lý văn bản người dùng điển hình:

```text
HTTP / JSON / form / file UTF-8
          |
          v
Decode bytes đúng charset + validate kích thước
          |
          v
Input String (có thể NFC hoặc NFD hoặc dạng khác)
          |
          v
Validate miền dữ liệu + chọn normalization policy
          |
          +-- văn bản thông thường --> NFC
          |
          +-- tìm kiếm/identifier đặc thù --> NFKC/NFKC_Casefold
          |                                  nếu chính sách thật sự yêu cầu
          |
          +-- signed byte/token --> giữ nguyên theo protocol,
          |                         không tự normalize
          v
Storage / index / service boundaries
          |
          v
Hiển thị theo Locale, với text phù hợp người dùng
```

Lưu ý: **`java.text.Normalizer` chỉ cung cấp bốn form NFC/NFD/NFKC/NFKD**, không cung cấp sẵn một API `NFKC_Casefold`. Nếu cần profile chuẩn Unicode phức tạp cho identifier, phải dùng thêm thuật toán/thư viện chuyên dụng (ví dụ ICU4J hoặc quy tắc dựa trên UTS #39) và khóa phiên bản dữ liệu Unicode phù hợp.

### Đặt normalization trước hay sau validation?

Không có một câu trả lời duy nhất cho mọi trường. Hai lựa chọn:

- **Validate raw input trước, rồi normalize và validate lại:** có ích khi cần phát hiện ký tự bị cấm trong input thô, đồng thời bảo đảm kết quả đã normalize tuân thủ chính sách đầu ra.
- **Normalize rồi validate:** có ích khi hợp đồng chính thức coi các biến thể tương đương là một input và validation được định nghĩa trên dạng canonical.

Với NFKC, **bắt buộc đánh giá rủi ro collision**. Ví dụ một ký tự compatibility sau normalize biến thành ký tự ASCII được cho phép; nếu chỉ kiểm tra tập ký tự trước hoặc sau một cách không đúng ý định, có thể mở rộng/thu hẹp input hợp lệ. Trong hệ thống đăng ký username, hãy định nghĩa chuẩn hóa một lần, xử lý uniqueness sau chuẩn hóa và giữ chính sách cố định qua các phiên bản.

Đối với tên người/họ tên tiếng Việt, dùng NFC thường phù hợp để đồng nhất canonical equivalence mà không cố xóa dấu hay thay chữ. Việc đồng nhất dạng Unicode không làm mất những dấu phân biệt trong `đ`, `ă`, `â`, `ơ`, `ư`.

## 13. Đọc/ghi tệp và API: chuẩn hóa phải là hợp đồng tường minh

- **JSON:** JSON strings có thể chứa text ở nhiều dạng Unicode. Parser JSON chủ yếu xử lý escape/encoding; đừng kỳ vọng nó áp dụng NFC cho mọi string. Chọn chính sách sau parse và trước khi ghi dữ liệu nếu cần.
- **CSV/TSV:** khi dữ liệu từ Excel, hệ thống khác hoặc hệ điều hành, tên người và nhãn có thể chứa tổ hợp dấu. Không dùng tách chuỗi bằng regex kết hợp Unicode cẩu thả hoặc so raw bytes nếu mục tiêu là canonical equivalence.
- **Database:** một số collation có thể coi nhiều chuỗi “tương đương” ở mức ngôn ngữ; kết quả không nhất thiết trùng với NFC. Kiểm tra cả Java normalization và collation khi thiết kế khóa/index.
- **File path:** hệ thống tệp có thể áp dụng hành vi hoặc lịch sử chuẩn hóa tên file khác nhau. Không xây file path từ text người dùng bằng cách giả định NFC/NFD duy nhất; còn phải bảo vệ path traversal và ký tự dành riêng cho hệ điều hành.
- **Cache key:** nếu một API dùng NFC làm định danh nhưng cache lưu raw input, hai biến thể canonically equivalent có thể chiếm hai entry. Chuẩn hóa tại cùng ranh giới cache key nếu hợp đồng định danh yêu cầu.
- **Dữ liệu ký số:** chữ ký thường được tính trên byte của một representation cụ thể. Normalize trước/sau ký phải theo **quy tắc canonicalization của protocol**, tuyệt đối không làm ngẫu hứng.
- **Log/audit:** cần cân nhắc giữ lại input thô (theo chính sách privacy) cho chẩn đoán và phiên bản đã normalize cho tra cứu. Việc log tùy tiện mọi input có thể làm lộ dữ liệu cá nhân; không dùng normalization làm lý do ghi thêm thông tin nhạy cảm.

### “Lưu NFC là xong” có luôn đúng không?

Không. NFC giúp giải quyết **canonical equivalence**, nhưng không tự giải quyết:

- Chữ thường/hoa và quy tắc case của ngôn ngữ.
- Ký tự confusable giữa nhiều hệ chữ khác nhau.
- Loại bỏ ký tự zero-width hoặc kí tự điều khiển theo nhu cầu ứng dụng.
- Những glyph khác nhau về phong cách, ngữ nghĩa hoặc chữ tượng hình.
- Độ hợp lệ của ID, email, domain hay định dạng file được quy định bởi RFC riêng.
- Biên giới grapheme của Unicode và thao tác con trỏ, cắt ký tự hiển thị.

Dùng Normalizer như một **thành phần** của text pipeline, không coi nó là bộ lọc bảo mật hoặc công cụ sửa mọi lỗi nhập liệu.

## 14. Chiều dài, hiệu năng và giới hạn tài nguyên

Một chuỗi sau chuẩn hóa có thể **ngắn hơn hoặc dài hơn** chuỗi ban đầu theo đơn vị mã UTF-16 hay byte UTF-8; không giả định NFC luôn giảm kích thước hoặc NFD luôn tăng kích thước. Ký tự compatibility khi NFKD có thể phân rã thành nhiều code point; với input không tin cậy, việc expand có thể tăng đáng kể kích thước dữ liệu.

Kiểm soát các yếu tố:

1. **Giới hạn đầu vào** trước normalize (byte/đơn vị mã/code point theo chính sách).
2. **Giới hạn đầu ra** sau normalize nếu storage hoặc API có quota.
3. **Độ dài trong UI** theo grapheme/cell rendering nếu sản phẩm yêu cầu; `String.length()` không dùng làm số ký tự nhìn thấy.
4. **Hiệu năng** cho batch lớn: normalize ở ranh giới, tránh lặp vô hạn khi so sánh từng cặp.
5. **Phiên bản Unicode/JDK** khi yêu cầu kết quả ổn định cho keys, ký số hoặc hệ thống phân tán lâu dài.
6. **Tính nhất quán** giữa Java, JavaScript, database và các thư viện ICU, vì phiên bản Unicode có thể không giống nhau.

Unicode đặt ra những bảo đảm ổn định cho chuẩn hóa của code point đã được gán, nhưng không có nghĩa mọi runtime cũ/mới, ký tự chưa được gán, profile bổ sung và cách so sánh của database **tự động giống nhau**. Với định danh dài hạn, hãy ghi rõ form, phiên bản/profile liên quan và chiến lược migration khi thay đổi.

### Chuẩn hóa đã thực hiện có cần chạy lại?

Về nguyên lý, normalize lần hai cùng form không đổi kết quả (*idempotent*). Nhưng khi **nối chuỗi**, biến đổi ngoài normalization (lowercase, thêm tiền tố, thay dấu...) hoặc làm việc với dữ liệu từ bên khác, đầu ra có thể không còn ở form mong muốn. Hãy kiểm tra/normalize lại ở **ranh giới cuối cùng**, đặc biệt trước khi tạo khóa định danh.

## 15. Thực hành: kiểm tra hợp đồng NFC cho dữ liệu đầu vào

Có những trường API muốn **chỉ chấp nhận chuỗi NFC** thay vì âm thầm chuyển đổi. Điều này có thể giúp bên gửi phát hiện lỗi sớm khi hợp đồng trao đổi đã quy định rõ.

**File `RequireNfcDemo.java`:**

```java
import java.text.Normalizer;

public class RequireNfcDemo {
    private static String requireNfc(String text) {
        if (text == null) {
            throw new IllegalArgumentException("Missing text");
        }
        if (!Normalizer.isNormalized(text, Normalizer.Form.NFC)) {
            throw new IllegalArgumentException("Not NFC");
        }
        return text;
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Accepted: "
                + requireNfc(composed).length());

        try {
            requireNfc(decomposed);
            System.out.println("Unexpected acceptance");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected non-NFC input");
        }
    }
}
```

```bash
javac -encoding UTF-8 RequireNfcDemo.java
java RequireNfcDemo
```

Stdout:

```text
Accepted: 4
Rejected non-NFC input
```

Ví dụ chỉ xét điều kiện NFC, không tự kiểm tra độ dài tối đa, chữ cấm, HTML injection, dữ liệu có hợp lệ về nghiệp vụ hay không. Trong API production, cần **tách** kiểm tra schema, kích thước, kiểu ký tự, ngôn ngữ và chính sách identity.

Nếu sản phẩm chọn **accept + normalize**, có thể viết:

```java
// Fragment trong phương thức đã có biến String input.
String stored = Normalizer.normalize(
        input, Normalizer.Form.NFC);
```

Nhưng khi làm với identifier hoặc tên cần audit, hãy xem xét giữ bản gốc theo chính sách nếu việc chuẩn hóa làm thay đổi dãy code point có ý nghĩa với người dùng hoặc với hệ thống bên ngoài.

## 16. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng UTF-8 tự động chuẩn hóa Unicode | Encoding và normalization khác tầng | Chọn UTF-8 và form Unicode riêng |
| So sánh trực tiếp hai chuỗi có dấu từ nguồn khác nhau | `String.equals` thấy dãy UTF-16 khác nhau | Chuẩn hóa hai bên theo **cùng form** nếu miền dữ liệu yêu cầu |
| Dùng NFKC cho mọi nội dung | Compatibility mapping có thể gộp ký tự khác nghĩa | Dùng NFC cho text thông thường; NFKC theo chính sách riêng |
| Coi NFD là xóa dấu | NFD **giữ** combining marks | Không xóa dấu trừ khi search policy cho phép |
| Coi NFC là chuyển chữ hoa/thường | Normalizer không làm case folding | Xác định case policy riêng |
| Tin NFKC đủ chống confusables/homoglyph | Nhiều ký tự khác hệ chữ vẫn dễ nhầm | Dùng identifier security profile bổ sung |
| Dựa vào `String.length()` như số chữ nhìn thấy | UTF-16 code units khác code point/grapheme | Chọn phép đo đúng nhu cầu |
| Ghép hai chuỗi NFC rồi mặc định kết quả NFC | Ghép có thể tạo tổ hợp mới | Normalize kết quả cuối |
| Sử dụng `Normalizer.isNormalized` để đánh giá nội dung đúng nghĩa | Nó chỉ kiểm tra form, không kiểm tra ngữ nghĩa | Validate miền dữ liệu riêng |
| Chuẩn hóa token/password/chuỗi đã ký mà không có hợp đồng | Có thể đổi byte và gây sai đối chiếu | Tuân thủ protocol và xử lý chữ ký đúng thứ tự |
| Chuẩn hóa toàn bộ DB hiện có không dự đoán va chạm | Key có thể trùng sau normalization | Dry-run, phát hiện collision, migration có rollback |
| Tưởng database collation = Java Normalizer | Quy tắc so chuỗi có thể khác | Kiểm thử collation và version |
| Lưu cache key khác normalization policy của API | Cùng identity bị chia entry | Normalize nhất quán ở ranh giới |
| Bỏ kiểm tra kích thước sau NFKD | Một số ký tự có thể expand | Kiểm soát cả giới hạn đầu vào và đầu ra |
| Phụ thuộc Unicode version ngầm khi cần định danh bền vững | Runtime nâng cấp có thể thay profile/nhân tố liên quan | Ghi rõ policy/version và test migration |

## 17. Bài tập

**Bài 1 — Canonical equivalence.** Với `"\u00E9"` và `"e\u0301"`, in `equals`, `length` và code point trước/sau NFC, NFD. Giải thích tại sao hai dãy có cùng cách hiển thị thường gặp nhưng `equals` ban đầu sai.

**Bài 2 — Tiếng Việt.** Với `"\u1EAF"`, dùng `Normalizer.Form.NFD` để liệt kê code point, sau đó chuyển về NFC. Chứng minh sự khác nhau giữa **phân rã dấu** và **bỏ dấu**. Thử thêm một chữ tiếng Việt khác có hai dấu kết hợp.

**Bài 3 — Compatibility.** So sánh `"\uFB01"` với `"fi"`, `"\u2460"` với `"1"` ở cả NFC và NFKC. Hãy quyết định xem một hệ thống lưu tên thương hiệu, một chỉ mục tìm kiếm, và một trường username có nên gộp các biến thể này không; giải thích theo chính sách.

**Bài 4 — Ghép chuỗi.** Kiểm tra `isNormalized(..., NFC)` cho `"e"`, `"\u0301"` và tổng của hai chuỗi. Vì sao normalized pieces không bảo đảm normalized concatenation?

**Bài 5 — Ranh giới UTF-8 và API.** Tạo hai chuỗi canonical equivalent, so sánh `getBytes(StandardCharsets.UTF_8)` trước/sau NFC. Đề xuất một rule API: cho phép người gửi NFD rồi normalize tại server hay buộc NFC và từ chối input khác? Nêu rõ hậu quả đối với chữ ký số, cache key và uniqueness.

**Bài 6 — Dữ liệu đã tồn tại.** Giả định database đang có `ﬁ` và `fi` là hai khóa khác nhau. Trước khi chuyển key policy từ NFC sang NFKC, cần phát hiện và giải quyết collision như thế nào để tránh gộp nhầm bản ghi?

## 18. Tài liệu chính thức và thuật ngữ

- [Java SE 21 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): `normalize` và `isNormalized`.
- [Java SE 21 — Normalizer.Form](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.Form.html): định nghĩa `NFC`, `NFD`, `NFKC`, `NFKD`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): thuật toán chuẩn tắc, compatibility, stability và các ví dụ.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html): canonical equivalence, idempotence, nối chuỗi, lựa chọn NFC/NFKC.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): bảo mật identifier, confusable characters và các profile bổ sung.

## 19. Ghi nhớ

**`NFC` = canonical decomposition + composition; `NFD` = canonical decomposition; `NFKC` = compatibility decomposition + composition; `NFKD` = compatibility decomposition.** Dùng `Normalizer.normalize(text, Normalizer.Form.NFC)` để đưa văn bản thông thường về cùng một biểu diễn canonical khi đó là chính sách dữ liệu; dùng `isNormalized` để kiểm tra hợp đồng khi cần.

NFC/NFD hỗ trợ so sánh những chuỗi **canonically equivalent**; NFKC/NFKD còn biến đổi **compatibility variants** và có thể tạo collision hoặc mất phân biệt ý nghĩa. Chuẩn hóa không phải charset conversion, xóa dấu, lowercasing, dịch ngôn ngữ hay bảo mật Unicode hoàn chỉnh. Hãy **xác định form ở ranh giới dữ liệu**, giới hạn kích thước, kiểm thử code point (không chỉ nhìn glyph), chọn policy cho trường định danh/search, và giữ hành vi nhất quán giữa Java, database, API và các phiên bản Unicode.