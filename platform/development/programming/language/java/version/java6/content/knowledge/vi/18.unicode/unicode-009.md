# Unicode: Giới hạn chuẩn hóa đối với bảo mật tên và ký tự dễ nhầm

## Mục tiêu học tập

Tên đăng nhập, tên tài khoản, tên miền, định danh tổ chức và tên hiển thị có thể chứa Unicode. Việc hai tên **trông giống nhau** nhưng có dãy ký tự khác nhau tạo ra các rủi ro như mạo danh, đăng ký tên gần giống thương hiệu, nhầm lẫn trong giao diện hoặc va chạm khóa dữ liệu sau khi chuyển đổi.

Sau bài này, bạn sẽ:

- Phân biệt **canonical equivalence**, **compatibility equivalence** và **visual confusability**. Chúng không phải một bài toán.
- Giải thích giới hạn của `java.text.Normalizer.normalize(...)` và `isNormalized(...)`: **NFC/NFKC không phải bộ phát hiện mọi tên gây nhầm lẫn hay lớp phòng vệ bảo mật đầy đủ**.
- Nhận ra homograph giữa chữ Latin và Cyrillic, ký tự fullwidth, ligature, ký tự có thể biến mất trong cách hiển thị, ký tự định dạng vô hình và những khác biệt giữa các hệ chữ viết.
- Thiết kế **identifier profile** (tập ký tự được phép, độ dài, chữ hoa/thường, normalization form, ký tự cấm, quy tắc uniqueness), xử lý rủi ro Unicode theo ngữ cảnh thay vì áp dụng một mẹo chung.
- Hiểu cách **Unicode Technical Standard #39 (UTS #39)** cung cấp cơ chế confusable detection, mixed-script checks và restriction levels; nhận biết rằng skeleton dành cho **so sánh nội bộ**, không dùng làm tên hiển thị hoặc tự động thay tên tài khoản.
- Viết ví dụ Java 17+ chạy được, kiểm thử thực tế các ca **Unicode tương đương**, **ký tự nhìn giống nhưng không tương đương**, **chuẩn hóa có thể thay đổi ký tự**, **kiểm tra raw input trước khi biến đổi**, và một profile đăng nhập ASCII có giới hạn rõ ràng.
- Lập checklist kiểm thử dữ liệu tên, chính sách migration/collision và bảo vệ giao diện, đồng thời **không loại trừ tùy tiện các ngôn ngữ hợp lệ** nếu sản phẩm có nhu cầu hỗ trợ Unicode.

**Ngữ cảnh:** chủ đề *Unicode*. Bài học dùng những API và tiêu chuẩn **hiện hành**, bao gồm `java.text.Normalizer` của Java SE 26, Unicode Standard Annex #15, Unicode Standard Annex #31 và Unicode Technical Standard #39 bản Unicode 18.0. Không áp dụng giải pháp không còn phù hợp với Java/Unicode hiện đại.

## 1. Vì sao Unicode normalization chưa đủ bảo vệ tên?

Một hệ thống chỉ dùng:

```java
String key = Normalizer.normalize(input, Normalizer.Form.NFC);
```

đã giải quyết **một phần quan trọng**: những dãy ký tự Unicode *canonically equivalent* có thể đi về cùng dạng NFC. Nhưng nó **không** trả lời được:

- Người dùng nhập một chữ **Cyrillic а** (`U+0430`) trông rất giống chữ **Latin a** (`U+0061`) hay không?
- Chuỗi có ký tự **ZERO WIDTH JOINER** (`U+200D`) hoặc những control/format characters khó quan sát hay không?
- Chuỗi có trộn hai hệ chữ viết bất thường, hoặc tạo tên rất giống tài khoản đã tồn tại, hay không?
- Tên có phù hợp quy tắc riêng của **username**, **display name**, **domain name** hay **mật khẩu** hay không?
- Chuẩn hóa có làm hai tài khoản đang khác nhau thành **một khóa duy nhất**, gây collision hay không?
- Hai chuỗi có giống nhau khi hiển thị bằng font, trình duyệt và thứ tự bidirectional (bidi) đang sử dụng không?

```text
Input Unicode
    |
    +--> Normalization (UAX #15)
    |       canonical / compatibility equivalence
    |
    +--> Identifier profile (UAX #31 / policy ứng dụng)
    |       tập ký tự, độ dài, case, dấu, quy tắc loại trừ
    |
    +--> Unicode security checks (UTS #39)
    |       confusables, restriction levels, script mixing...
    |
    +--> Business/security checks
            uniqueness, tên được bảo vệ, cảnh báo mạo danh,
            màn hình hiển thị, quy trình xử lý xung đột
```

**Không thay thế toàn bộ sơ đồ bằng một lệnh `normalize`.** Normalization chỉ là một phép biến đổi Unicode; bảo mật tên là việc xác định **những tên nào được chấp nhận, được gán cho ai và được hiển thị/so sánh ra sao**.

## 2. Ba khái niệm dễ nhầm: canonical, compatibility và confusable

### 2.1. Canonical equivalence

Một chữ có dấu có thể được biểu diễn bằng ký tự dựng sẵn hoặc bằng base letter + combining mark:

```text
U+00E9        "é"
U+0065 U+0301 "e" + COMBINING ACUTE ACCENT
```

Hai dạng này **canonically equivalent**. Ví dụ:

```java
String one = "caf\u00E9";
String two = "cafe\u0301";

System.out.println(one.equals(two)); // false

boolean sameNfc =
        Normalizer.normalize(one, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(two, Normalizer.Form.NFC));
// sameNfc == true
```

Đây là đoạn minh họa trong method, không phải một chương trình `main` độc lập. `String.equals` so nội dung code units; nó **không tự normalize**.

Canonical normalization còn phải xử lý thứ tự các dấu kết hợp theo Unicode. Không nên tự “xóa dấu rồi ghép lại” để mô phỏng NFC/NFD.

### 2.2. Compatibility equivalence

Có những ký tự không tương đương canonical nhưng được Unicode khai báo **tương đương theo mục đích tương thích** (compatibility). Ví dụ:

- `U+FF21 FULLWIDTH LATIN CAPITAL LETTER A` (Ａ) và `U+0041 LATIN CAPITAL LETTER A` (A).
- `U+FB03 LATIN SMALL LIGATURE FFI` (ﬃ) và chuỗi `ffi`.

```java
String fullwidthA = "\uFF21";
String asciiA = "A";

boolean sameNfc =
        Normalizer.normalize(fullwidthA, Normalizer.Form.NFC)
            .equals(asciiA); // false

boolean sameNfkc =
        Normalizer.normalize(fullwidthA, Normalizer.Form.NFKC)
            .equals(asciiA); // true
```

**NFKC/NFKD có thể làm mất những khác biệt** mà NFC/NFD giữ nguyên. Với một hệ thống muốn gộp chữ fullwidth/ASCII khi lập khóa tìm kiếm, đây có thể là đặc tính hữu ích. Với tên pháp lý, dữ liệu cần bảo toàn hoặc những không gian tên có semantics riêng, việc gộp có thể là thay đổi không mong muốn.

Bốn form vẫn được Java hỗ trợ:

| Form | Tương đương được xử lý | Kết quả |
| --- | --- | --- |
| `NFC` | Canonical | Phân rã rồi kết hợp canonical khi có thể |
| `NFD` | Canonical | Phân rã canonical và chuẩn hóa thứ tự dấu |
| `NFKC` | Compatibility (bao gồm canonical) | Phân rã compatibility rồi kết hợp canonical |
| `NFKD` | Compatibility (bao gồm canonical) | Phân rã compatibility |

Không có một form duy nhất đảm bảo phù hợp **mọi loại định danh**. Unicode UAX #15 và UAX #31 trình bày những lựa chọn theo mục đích.

### 2.3. Visual confusability / homoglyph

Tên `paypal` (toàn chữ Latin) và `p\u0430ypal` (ký tự thứ hai **U+0430 CYRILLIC SMALL LETTER A**) có thể trông gần như nhau trong nhiều font. Nhưng `a` Latin và `а` Cyrillic là những ký tự **khác nhau**, không canonically hay compatibility equivalent trong ví dụ này.

```java
String genuine = "paypal";
String lookalike = "p\u0430ypal";

boolean sameNfc =
        Normalizer.normalize(genuine, Normalizer.Form.NFC)
            .equals(Normalizer.normalize(lookalike, Normalizer.Form.NFC));
// false

boolean sameNfkc =
        Normalizer.normalize(genuine, Normalizer.Form.NFKC)
            .equals(Normalizer.normalize(lookalike, Normalizer.Form.NFKC));
// false
```

Đó là rủi ro **visual confusable** mà chỉ gọi `normalize` không nhận diện được. Trong UTS #39, confusable detection là một cơ chế riêng; không nên tự suy luận “NFKC không sửa được thì không có rủi ro”.

**Vì sao chúng vẫn khác?** Một chữ cái Cyrillic thực sự có vai trò ngôn ngữ riêng, không phải một bản copy lỗi của chữ Latin. Chỉ vì nét chữ có thể giống nhau không có nghĩa Unicode phải biến chúng thành cùng một code point. Bảo vệ tên phải **không làm hỏng nội dung đa ngôn ngữ**.

### 2.4. So sánh nhanh

| Cặp / hiện tượng | `NFC` gộp? | `NFKC` gộp? | Cần thêm chính sách bảo mật? |
| --- | --- | --- | --- |
| `é` và `e + U+0301` | Có | Có | Vẫn cần quy tắc tên/uniqueness |
| `Ａ` và `A` | Không | Có | Có, vì có thể gây collision |
| `ﬃ` và `ffi` | Không | Có | Có, vì mất compatibility distinction |
| Latin `a` và Cyrillic `а` | Không | Không | Có, cần confusable/mixed-script policy |
| Chuỗi có `U+200D` vô hình | Không tự loại bỏ | Không tự loại bỏ | Có, theo ngữ cảnh của hệ chữ viết |
| Tên khác chữ hoa/thường | Không tự case-fold | Không thay hoàn toàn full case-fold | Có, nếu tên được thiết kế case-insensitive |

**NFKC không phải “phát hiện confusable”**. Ngay cả khi một số ký tự được gộp, những trường hợp khác vẫn là các tên khác nhau ở mức code points nhưng dễ bị người dùng nhìn nhầm.

## 3. Giới hạn của `java.text.Normalizer`

`java.text.Normalizer` là API chuẩn hiện hành trong `java.base`, với hai phương thức quan trọng:

```java
Normalizer.isNormalized(text, Normalizer.Form.NFC);
Normalizer.normalize(text, Normalizer.Form.NFC);
```

- `isNormalized(...)` kiểm tra chuỗi đã ở một normal form cụ thể hay chưa; không xác nhận chuỗi **an toàn** để làm username.
- `normalize(...)` biến đổi dãy ký tự theo form; không kiểm tra tên được cấp phép, script, lịch sử quyền sở hữu hay danh sách tên được bảo vệ.
- `String` bất biến: normalize trả chuỗi đầu ra, **không sửa input**.
- Có thể normalize Unicode đúng quy tắc mà kết quả **vẫn chứa ký tự nguy hiểm hoặc khó hiểu trong một ngữ cảnh cụ thể**.
- Normalization không phải case folding hoàn chỉnh, không phải spell checking, không phải transliteration tiếng Việt, không phải bộ lọc HTML/SQL và không phải bộ xử lý bidi.
- Dữ liệu đã normalized có thể đổi sau khi nối với đoạn Unicode khác; nếu quy tắc đòi hỏi normal form thì cần normalize lại **giá trị hoàn chỉnh** khi cần.

Ví dụ một chuỗi có `ZERO WIDTH JOINER`:

```java
String invisible = "us\u200Der";
String nfc = Normalizer.normalize(invisible, Normalizer.Form.NFC);

boolean remains =
        nfc.contains("\u200D"); // true
```

`U+200D` không tự biến mất trong trường hợp này. **Không nên tự động xóa tất cả ký tự format vô hình trong mọi ngôn ngữ**: joiners có vai trò hợp lệ trong một số hệ chữ viết và emoji sequences. Chính sách phải phụ thuộc loại trường nhập và người dùng cần hỗ trợ.

### `isNormalized == true` không phải một điều kiện bảo mật

Một nickname có chữ Cyrillic nhìn giống Latin có thể hoàn toàn NFC, đồng thời vẫn tạo nguy cơ mạo danh. Vì vậy:

```java
if (Normalizer.isNormalized(input, Normalizer.Form.NFC)) {
    // Chỉ biết input đã NFC.
    // KHÔNG suy ra input an toàn hoặc không gây nhầm lẫn.
}
```

Đây là ví dụ minh họa luồng logic. Không gộp “đã NFC” và “được cấp phát làm username” thành cùng một boolean.

## 4. Tại sao phải nghĩ đến normalization *trước và sau* validation?

Một bẫy tinh vi: **ngay NFC cũng có thể thay đổi một số ký tự không phải ASCII thành ASCII** theo canonical mapping. Ví dụ **`U+212A KELVIN SIGN` (K)** có canonical decomposition về chữ **K** (`U+004B`).

```java
String raw = "\u212Aen";
String afterNfc = Normalizer.normalize(raw, Normalizer.Form.NFC);

// afterNfc.equals("Ken") == true
```

Giả sử mục tiêu an ninh là **chỉ chấp nhận đầu vào gõ từ tập chữ ASCII**. Nếu ứng dụng chỉ normalize rồi kiểm tra:

```java
String key = Normalizer.normalize(input, Normalizer.Form.NFC);

if (key.matches("[A-Za-z0-9_]{3,20}")) {
    // ĐÃ BỎ QUA việc input ban đầu có thật sự ASCII không.
}
```

thì `"\u212Aen"` có thể qua được kiểm tra vì đã biến thành `"Ken"`. Đó là **khác biệt giữa “chỉ cho phép ký tự ASCII trong kết quả canonical” và “chỉ cho phép ASCII trong đầu vào gốc”**.

**Cả hai lựa chọn có thể hợp lệ tùy sản phẩm**, nhưng phải ghi rõ lựa chọn nào là contract:

- **Profile A — raw ASCII-only:** reject đầu vào ngoài ASCII **trước** khi có phép biến đổi có thể thu hẹp ký tự. Phù hợp với một số username máy móc/quản trị, nhưng hạn chế người dùng đa ngôn ngữ.
- **Profile B — canonical-key ASCII:** có thể chấp nhận một số ký tự Unicode ánh xạ thành ASCII, nếu policy đã công bố và các trường hợp collision được xử lý. Không được gọi đây là “raw ASCII-only”.
- **Profile C — Unicode user names:** chọn subset ký tự Unicode, normalization/case handling, confusable checks và quy trình xử lý tên đã tồn tại. Không thể được xây đúng chỉ bằng regex ASCII.

Khi áp dụng validation nhiều bước, cần xem xét **cả biểu diễn thô lẫn biểu diễn canonical**, bởi một phép biến đổi có thể làm xuất hiện hoặc che đi điều kiện mà một bước kiểm tra khác coi là quan trọng.

## 5. Xác định đối tượng bảo vệ và namespace trước khi chọn quy tắc

Cùng một chuỗi có thể hợp lệ ở trường này và không hợp lệ ở trường khác:

| Loại chuỗi | Mục tiêu | Chính sách gợi ý |
| --- | --- | --- |
| **Username/login handle** | Phân biệt tài khoản, tránh mạo danh, uniqueness | Identifier profile rõ; normalization và case policy nhất quán; protected names, collision/confusable warnings |
| **Display name** | Hiển thị tên người dùng theo ngôn ngữ thực tế | Hỗ trợ Unicode rộng hơn; bảo toàn cách viết hợp lệ; xử lý ký tự điều khiển/hiển thị, báo giả mạo nhãn chính thức |
| **Tên tổ chức/nhãn đã xác thực** | Chống người khác mạo danh nhãn đáng tin | Quy trình cấp quyền, verified badge, reserved names và các cảnh báo confusable |
| **Domain/hostname** | Nhận diện đích network đúng với chuẩn domain | Dùng IDNA/UTS #46 tùy giao thức và thư viện phù hợp; không tự gọi NFKC rồi gán là domain an toàn |
| **Email address** | Xác định hộp thư chính xác | Phân biệt phần local và domain; không tự áp dụng một luật lowercase/normalize chung cho toàn địa chỉ |
| **Password/secret/token** | Kiểm tra chính xác dữ liệu xác thực | Theo giao thức/chuẩn xử lý secret; không tự normalize hay casefold làm mất phân biệt khi chưa có contract |
| **Filename/path** | Truy cập đúng tài nguyên trên filesystem | Cân nhắc cách so tên của hệ thống đích; xử lý path traversal/permission riêng, không dựa vào NFC/NFKC để chống traversal |

Đặc biệt, **display name Unicode không nên bị ép vào ASCII** chỉ vì một ví dụ minh họa security profile. Người Việt cần được viết tên có dấu; người dùng các hệ chữ viết khác cũng có nhu cầu tương tự. Một sản phẩm có thể dùng **username kỹ thuật hẹp** và **display name Unicode rộng** với những biện pháp bảo vệ hiển thị riêng.

### Bài học về nguyên tắc “không gây hại cho người dùng hợp lệ”

- Một tên Cyrillic **hoàn toàn hợp lệ** trong ngôn ngữ sử dụng Cyrillic.
- Một chuỗi trộn Latin và Han/Kana có thể là cách viết bình thường của một số ngôn ngữ.
- Một joiner có thể cần cho một chữ viết nhất định; cấm vô điều kiện khiến người dùng không nhập được tên đúng.
- Những tên có hình thức gần nhau không nhất thiết là cùng tài khoản hoặc hành vi tấn công.

Cảnh báo confusable là **tín hiệu rủi ro**, không tự động là bằng chứng ý định xấu. Cách xử lý (cảnh báo, yêu cầu lựa chọn tên khác, xác minh bổ sung, hạn chế dùng nhãn chính thức) nên dựa vào loại dịch vụ và chi phí false positives.

## 6. Ví dụ Java 17+ hoàn chỉnh: normalization và một ASCII username profile

Ví dụ chạy độc lập sau dùng duy nhất **Java SE**, không cần ICU4J hay thư viện ngoài. Mục đích là chứng minh:

1. Canonical equivalents khác raw bytes nhưng giống nhau sau NFC.
2. Latin/Cyrillic confusables có thể **vẫn khác** sau cả NFC và NFKC.
3. NFKC chuyển fullwidth A và ligature theo compatibility mapping.
4. NFC có thể chuyển Kelvin sign về K.
5. Một **strict raw ASCII profile** từ chối ký tự ngoài tập cho phép **trước** khi normalize và lowercase.
6. Zero width joiner không bị NFC xóa.
7. Chính sách username tiếng Anh hẹp không đồng nghĩa một tên Unicode tiếng Việt có dấu “không an toàn”; nó chỉ **nằm ngoài profile chủ động chọn**.

Tạo file **`SecureNamesDemo.java`** với toàn bộ nội dung dưới đây:

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public final class SecureNamesDemo {
    private static final Pattern ASCII_INPUT =
            Pattern.compile("[A-Za-z0-9_]{3,20}");

    private static String strictAsciiKey(String candidate) {
        Objects.requireNonNull(candidate, "candidate");
        if (!ASCII_INPUT.matcher(candidate).matches()) {
            throw new IllegalArgumentException("Outside ASCII username profile");
        }
        String normalized = Normalizer.normalize(candidate, Form.NFC);
        return normalized.toLowerCase(Locale.ROOT);
    }

    private static boolean accepted(String text) {
        try {
            strictAsciiKey(text);
            return true;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";
        check("canonicalRawDifferent", !composed.equals(decomposed));
        check("canonicalEqualAfterNfc",
                Normalizer.normalize(composed, Form.NFC).equals(
                Normalizer.normalize(decomposed, Form.NFC)));

        String genuine = "paypal";
        String lookalike = "p\u0430ypal";
        check("confusableStillDifferentNfc",
                !Normalizer.normalize(genuine, Form.NFC).equals(
                 Normalizer.normalize(lookalike, Form.NFC)));
        check("confusableStillDifferentNfkc",
                !Normalizer.normalize(genuine, Form.NFKC).equals(
                 Normalizer.normalize(lookalike, Form.NFKC)));
        check("lookalikeContainsCyrillic",
                lookalike.codePoints().anyMatch(cp ->
                  Character.UnicodeScript.of(cp) == Character.UnicodeScript.CYRILLIC));

        String fullwidth = "\uFF21lice";
        check("fullwidthStillDifferentNfc",
                !Normalizer.normalize(fullwidth, Form.NFC).equals("Alice"));
        check("fullwidthEqualAfterNfkc",
                Normalizer.normalize(fullwidth, Form.NFKC).equals("Alice"));
        check("ligatureChangedNfkc",
                Normalizer.normalize("\uFB03", Form.NFKC).equals("ffi"));

        String kelvin = "\u212Aen";
        check("kelvinMapsAfterNfc",
                Normalizer.normalize(kelvin, Form.NFC).equals("Ken"));

        check("asciiKeyCasePolicy",
                strictAsciiKey("ALICE_7").equals("alice_7"));
        check("asciiNameAllowed", accepted("Alice_7"));
        check("mixedScriptDeniedByProfile", !accepted(lookalike));
        check("fullwidthDeniedByProfile", !accepted(fullwidth));
        check("kelvinDeniedByRawProfile", !accepted(kelvin));
        String invisible = "us\u200Der";
        check("zwjPreservedByNfc",
                Normalizer.normalize(invisible, Form.NFC).contains("\u200D"));
        check("invisibleDeniedByProfile", !accepted(invisible));
        check("unicodeWordDeniedByAsciiPolicy", !accepted("Nguy\u1EC5n"));
        check("normalizedKeyStable",
                strictAsciiKey(strictAsciiKey("ALICE_7")).equals("alice_7"));
    }
}
```

### 6.1. Cách chạy

Đứng ở thư mục chứa file `SecureNamesDemo.java`. Dùng **JDK 17 hoặc cao hơn**:

```bash
javac --release 17 SecureNamesDemo.java
java SecureNamesDemo
```

Tên file phải là `SecureNamesDemo.java` vì lớp public có tên `SecureNamesDemo`. Mã chỉ dùng `java.text`, `java.util`, `java.util.regex` và các lớp trong `java.lang` có sẵn, không cần cấu hình dependency.

### 6.2. Kết quả đã kiểm thử thực tế trên OpenJDK 24

```text
canonicalRawDifferent=true
canonicalEqualAfterNfc=true
confusableStillDifferentNfc=true
confusableStillDifferentNfkc=true
lookalikeContainsCyrillic=true
fullwidthStillDifferentNfc=true
fullwidthEqualAfterNfkc=true
ligatureChangedNfkc=true
kelvinMapsAfterNfc=true
asciiKeyCasePolicy=true
asciiNameAllowed=true
mixedScriptDeniedByProfile=true
fullwidthDeniedByProfile=true
kelvinDeniedByRawProfile=true
zwjPreservedByNfc=true
invisibleDeniedByProfile=true
unicodeWordDeniedByAsciiPolicy=true
normalizedKeyStable=true
```

Đây là **18 phép kiểm tra** từ chương trình đã được biên dịch bằng `javac --release 17` và chạy với JDK 24. `check(...)` ném `AssertionError` nếu điều kiện sai, nên mỗi dòng `...=true` là một điều kiện thật sự đã đạt chứ không chỉ là kết quả được in mặc định. Chương trình không cần in những ký tự dễ nhầm lên console; các mẫu nhạy về hiển thị được biểu diễn bằng Unicode escape trong Java source.

### 6.3. Cách đọc kết quả

| Kết quả | Ý nghĩa |
| --- | --- |
| `canonicalRawDifferent`, `canonicalEqualAfterNfc` | Hai cách mã hóa của é khác nhau trước, giống nhau sau NFC. |
| `confusableStillDifferentNfc/Nfkc` | Cyrillic а không bị NFC/NFKC biến thành Latin a trong ví dụ. |
| `lookalikeContainsCyrillic` | Có thể xem code point `U+0430` thuộc Unicode script CYRILLIC. |
| `fullwidthStillDifferentNfc` | NFC không gộp fullwidth A với ASCII A. |
| `fullwidthEqualAfterNfkc` | NFKC gộp A fullwidth với ASCII A theo compatibility mapping. |
| `ligatureChangedNfkc` | Ligature `ﬃ` được NFKC chuyển thành `ffi`. |
| `kelvinMapsAfterNfc` | Ngay NFC cũng có canonical mapping `K` → `K`. |
| `asciiKeyCasePolicy` | Profile username đã chọn biến các chữ ASCII hoa thành thường. |
| `mixedScriptDeniedByProfile` | Strict raw ASCII policy từ chối tên có Cyrillic а. |
| `fullwidthDeniedByProfile` | Raw ASCII policy từ chối fullwidth ngay từ input. |
| `kelvinDeniedByRawProfile` | Dù có thể trở thành ASCII sau NFC, ký tự `K` vẫn bị từ chối trước biến đổi. |
| `zwjPreservedByNfc` | NFC không tự loại bỏ `U+200D`. |
| `invisibleDeniedByProfile` | Strict ASCII profile từ chối tên có joiner. |
| `unicodeWordDeniedByAsciiPolicy` | Tên có dấu không thuộc **profile ASCII đã chọn**, không có nghĩa tên đó là độc hại. |
| `normalizedKeyStable` | Một username đã canonical hóa theo policy trở lại cùng key khi xử lý lại. |

**Giới hạn chủ đích của demo:** `strictAsciiKey` là một **profile tên đăng nhập ASCII minh họa**, không phải hệ thống phát hiện homoglyph Unicode tổng quát. Nó chỉ cho phép `[A-Za-z0-9_]`, dài từ 3–20 UTF-16 code units (vì chỉ ASCII nên cũng là 3–20 ký tự), và định nghĩa tên không phân biệt hoa/thường theo lowercase ASCII. Chính sách thật còn phải có uniqueness, tên dự trữ, quyền sở hữu và xử lý cạnh tranh khi đăng ký.

## 7. Phân tích thứ tự xử lý trong `strictAsciiKey`

```java
private static String strictAsciiKey(String candidate) {
    Objects.requireNonNull(candidate, "candidate");
    if (!ASCII_INPUT.matcher(candidate).matches()) {
        throw new IllegalArgumentException("Outside ASCII username profile");
    }
    String normalized = Normalizer.normalize(candidate, Form.NFC);
    return normalized.toLowerCase(Locale.ROOT);
}
```

### Bước 1 — Xác định input policy trên giá trị thô

Regex `[A-Za-z0-9_]{3,20}` yêu cầu **đầu vào ban đầu** chỉ chứa ASCII chữ cái, số và dấu gạch dưới. Không chấp nhận fullwidth A, Cyrillic а, Kelvin sign, dấu kết hợp hoặc emoji.

**Quan trọng:** regex này cố ý chỉ phù hợp một namespace hẹp. Nó không phải phép đánh giá một chữ viết khác có hợp lệ hay an toàn hay không. Một ứng dụng quốc tế hóa không nên bê nguyên rule này áp cho tên hiển thị người dùng.

### Bước 2 — Chuẩn hóa NFC

Vì toàn bộ ký tự được cho phép đều nằm trong tập ASCII đơn giản, `Normalizer.normalize(candidate, NFC)` **không thay đổi giá trị** trong profile này. Gọi nó ở đây để thể hiện rõ contract/pipeline; trong code production chỉ cho ASCII, bước này có thể được lược bỏ sau khi chứng minh policy thực sự không cho phép bất kỳ ký tự nào có mapping ảnh hưởng.

Không nên hiểu việc có lệnh normalize là thành phần ngăn mạo danh: **bảo vệ chủ yếu trong ví dụ là allowlist đầu vào** và quy tắc namespace.

### Bước 3 — Tạo key không phân biệt chữ hoa/thường

`toLowerCase(Locale.ROOT)` biến những chữ hoa ASCII thành chữ thường trong trường hợp này; `"ALICE_7"` thành `"alice_7"`. Vì đã giới hạn input ASCII, kết quả dễ dự đoán và không cần xử lý toàn bộ Unicode casefold.

Với tên Unicode rộng, **`String.toLowerCase(Locale.ROOT)` không đồng nghĩa với đầy đủ Unicode case folding hay NFKC_Casefold**. Đừng thay một chuẩn identifier protocol bằng cách ghép tùy tiện `NFKC` và `toLowerCase` nếu giao thức quy định thuật toán khác.

### Bước 4 — Uniqueness phải dựa vào key đã thống nhất

Đăng ký tên `ALICE_7` rồi `alice_7` phải được xem là trùng trong profile này nếu hệ thống cho phép unique usernames case-insensitive. Cần enforce bằng **ràng buộc nguyên tử ở storage**, không chỉ:

```text
SELECT xem có tên chưa
  |
  +--> nếu không có: INSERT
```

Hai request có thể cùng thấy chưa tồn tại rồi cùng ghi. Một unique constraint theo normalized key (cùng chính sách), thao tác transaction và xử lý xung đột là phần thiết yếu.

### Đổi thứ tự có thể làm đổi quyền truy cập

Nếu validate **chỉ sau** NFC, `"Ken"` có thể thành `"Ken"` rồi lọt qua regex ASCII. Nếu chuẩn hóa theo NFKC rồi validate, cả fullwidth `Ａlice` có thể thành `Alice` và được chấp nhận. Điều đó không tự động là “lỗ hổng” trong mọi hệ thống, nhưng **sai** với một contract yêu cầu raw input ASCII-only.

Đừng xây các lớp xác thực/định danh với **thứ tự transform khác nhau** giữa frontend, backend, database và các phiên đăng nhập.

## 8. UTS #39: cơ chế hiện hành để phát hiện confusables

**Unicode Technical Standard #39 — Unicode Security Mechanisms** cung cấp những cơ chế cho các bài toán bảo mật Unicode. Bản Unicode **18.0.0, revision 34 (27/08/2026)** là tài liệu hiện hành tại thời điểm viết bài; xem [UTS #39](https://www.unicode.org/reports/tr39/).

Trong UTS #39, cần phân biệt:

- **Confusable detection:** kiểm tra các chuỗi có thể bị nhầm về hình thức hiển thị, dựa trên dữ liệu mapping của Unicode.
- **Mixed-script detection:** phân tích cách ký tự thuộc các hệ chữ viết được dùng trong một định danh.
- **Restriction levels:** phân loại mức giới hạn script của identifier (ASCII-Only, Single Script, Highly Restrictive, v.v.).
- **Identifier profile:** xác định tập ký tự có thể sử dụng làm identifier theo quy tắc chuẩn/giao thức và tùy biến ứng dụng.
- **Invisible/mixed-number/bidi-related concerns:** những vấn đề khác cần xử lý theo chính sách hiển thị và threat model.

### 8.1. Skeleton dùng để so sánh, không phải “tên được chuẩn hóa”

UTS #39 xây dựng một dạng xử lý trung gian gọi là **skeleton** (và trong định nghĩa hiện hành có cơ chế có xét hướng hiển thị bidi) để đánh giá tính confusable. Một cặp có skeleton tương ứng được so sánh theo cơ chế của tiêu chuẩn có thể được coi là confusable.

**Nhưng skeleton không phải Normalizer NFC/NFKC.** Nó không phải dữ liệu người dùng nên thấy, cũng không phải phép chuẩn hóa nên dùng làm một username chính thức.

UTS #39 hiện hành lưu ý:

- Skeleton là dữ liệu **so sánh nội bộ**.
- Kết quả **không thích hợp hiển thị** cho người dùng.
- Dữ liệu và skeleton có thể thay đổi giữa những phiên bản Unicode; nếu hệ thống lưu/caching kết quả để đánh giá confusable, cần có quy trình cập nhật/recompute theo phiên bản.
- Cặp chuỗi bị đánh dấu tương tự không phải bằng chứng tuyệt đối rằng hai người dùng là một hoặc có ý định tấn công.

Đừng tự tạo “confusable skeleton” bằng cách thay các chữ Cyrillic trông như Latin trong một bảng nhỏ thủ công. Phương pháp này dễ bỏ sót case và có thể làm sai văn bản hợp lệ. Hãy dùng tiêu chuẩn và dữ liệu Unicode được cập nhật nếu sản phẩm thực sự cần chống spoofing.

### 8.2. Phân biệt các loại confusables

UTS #39 phân biệt những trường hợp như:

| Nhóm | Ý tưởng |
| --- | --- |
| **Single-script confusable** | Hai chuỗi bị nhầm về hình thức nhưng thuộc phạm vi script có quan hệ tương ứng theo tiêu chuẩn. |
| **Mixed-script confusable** | Chuỗi bị nhầm về hình thức giữa các script hoặc tổ hợp script không cùng resolved script set. |
| **Whole-script confusable** | Trường hợp đặc biệt: từng chuỗi là single-script nhưng hai chuỗi thuộc các script khác nhau và dễ bị nhầm. |

Một tên toàn Cyrillic có thể vẫn là whole-script confusable với tên toàn Latin. Vì vậy **chỉ cấm mixed-script trong từng chuỗi không tự loại bỏ mọi giả mạo**.

### 8.3. Restriction levels không tương đương “an toàn tuyệt đối”

UTS #39 mô tả các mức như:

1. **ASCII-Only** — các ký tự đều trong vùng ASCII.
2. **Single Script** — một hệ chữ viết theo quy tắc resolved script set.
3. **Highly Restrictive** — cho phép một số tổ hợp script đã được tiêu chuẩn thiết kế cho ngôn ngữ đa hệ chữ viết.
4. **Moderately Restrictive** — cho phép thêm một số tổ hợp.
5. **Minimally Restrictive** — giới hạn thấp hơn.
6. **Unrestricted** — trường hợp không đáp ứng những profile giới hạn trên.

Không nên đơn giản áp dụng “một script duy nhất” cho toàn cầu rồi coi tên người dùng đa ngôn ngữ là không hợp lệ. Các ngôn ngữ như tiếng Nhật có thể dùng Han, Hiragana và Katakana cùng nhau một cách bình thường. Chọn restriction level cần dựa vào mục tiêu sản phẩm và tập người dùng thực tế.

## 9. Java `Character.UnicodeScript.of(...)` hữu ích nhưng chưa đủ

Java có API chuẩn:

```java
Character.UnicodeScript script =
        Character.UnicodeScript.of(codePoint);
```

và để đi qua mọi code points trong `String`, dùng:

```java
boolean hasCyrillic = input.codePoints()
        .anyMatch(cp -> Character.UnicodeScript.of(cp)
                == Character.UnicodeScript.CYRILLIC);
```

Đây là **đoạn minh họa**, cần biến `input` đã định nghĩa. Chương trình chạy đầy đủ ở mục 6 dùng chính cách này để chứng minh có ký tự Cyrillic trong chuỗi giả lập.

**Đừng lấy `UnicodeScript.of` rồi tuyên bố đã triển khai UTS #39.** Phát hiện mixed-script đúng theo tiêu chuẩn có thêm các vấn đề:

- Thuộc tính Unicode **Script_Extensions** có thể chứa nhiều scripts, khác với một giá trị Script được nhìn theo cách đơn giản.
- Các ký tự `Common` và `Inherited`, dấu kết hợp và quy tắc của nhiều hệ chữ viết cần được xử lý thích hợp.
- Unicode data thay đổi theo phiên bản; một regex/script enum không tự bao gồm tất cả các thuật toán và dữ liệu confusable.
- Ký tự cùng script cũng có thể confusable; restriction theo script chỉ giải quyết một lát cắt.
- Giao diện hiển thị có thể bị ảnh hưởng bởi bidirectional text, ký tự điều khiển/format và font.

Vì vậy `UnicodeScript.of` **hữu ích để quan sát hoặc làm diagnostic sơ bộ**, nhưng không được trình bày như một giải pháp phát hiện Unicode spoofing hoàn chỉnh.

## 10. Dùng công cụ confusable checking chuyên dụng khi hỗ trợ tên Unicode

Nếu sản phẩm cho phép Unicode usernames và cần phát hiện visual spoofing ở mức có thể triển khai, cân nhắc thư viện Unicode được bảo trì như **ICU4J** với `com.ibm.icu.text.SpoofChecker`.

ICU4J cung cấp các hướng kiểm tra hiện hành như:

- `failsChecks(text)` theo một tập checks đã cấu hình.
- `areConfusable(s1, s2)` để so sánh một cặp chuỗi.
- Các checks liên quan **mixed-script**, **restriction level**, **invisible characters** hoặc **mixed-number systems** theo phiên bản API.
- Chính sách allowed characters/restriction level qua cấu hình của checker.

**Lưu ý:** Đây là một thư viện ngoài Java SE; **không có sẵn trong `java.base`**. Bài không gán nhầm API `SpoofChecker` vào `java.text.Normalizer` và không đưa một ví dụ phụ thuộc ICU vào chương trình Java SE chạy độc lập. Nếu sử dụng ICU4J trong sản phẩm, chọn bản được bảo trì, đọc Javadoc đúng phiên bản và kiểm thử config với tên thực tế của người dùng.

Cơ chế skeleton/confusable vẫn có **false positives và các ranh giới nhận diện**. Một kết quả bị cảnh báo có thể được dùng để gợi ý đổi tên, kiểm tra against protected names, yêu cầu xác minh thêm hoặc đưa vào hàng đợi review. Việc **tự động hợp nhất tài khoản** hay thay tên người dùng dựa trên confusable skeleton là thiết kế nguy hiểm.

Đọc thêm: [ICU4J SpoofChecker — API hiện hành](https://unicode-org.github.io/icu-docs/apidoc/released/icu4j/com/ibm/icu/text/SpoofChecker.html).

## 11. Invisibility, bidi và hiển thị không đáng tin

Không phải mọi vấn đề visual spoofing đều là “chữ a trông giống chữ а”.

### 11.1. Format characters, zero-width và dấu kết hợp

Các code points không hiển thị rõ ràng, như một số **format controls**, combining marks hoặc joiners, có thể tạo nhầm lẫn về một phần của tên. Chương trình trong mục 6 chứng minh `U+200D ZERO WIDTH JOINER` còn nguyên sau NFC.

**Không suy ra:** “Cứ xóa tất cả `Cf` là an toàn”. Có scripts và emoji sequences dùng các ký tự định dạng theo chuẩn. Thay vì xóa bừa, định nghĩa một **profile** theo loại tên; nếu cần hỗ trợ ngôn ngữ sử dụng joiners, áp dụng các context rules phù hợp.

### 11.2. Bidirectional (bidi) display

Unicode cho phép văn bản trái-sang-phải và phải-sang-trái. Một số tổ hợp ký tự/điều khiển hướng có thể làm giao diện hiển thị khác thứ tự lưu trữ hoặc làm nhầm phạm vi các đoạn ký tự.

Do đó, tên hiển thị gần email, URL, quyền quản trị hoặc nhãn bảo mật cần cân nhắc **bidi isolation**, cách ghép tên vào UI và quy tắc render phù hợp. Normalizer không đảm bảo “hiển thị cùng thứ tự” hoặc “không thể giả mạo tên” trong mọi ngữ cảnh bidi.

### 11.3. Cách giúp người dùng nhận diện tài khoản thật

Ngoài kiểm tra ở server, giao diện có thể dùng:

- **ID tài khoản ổn định, bất biến** trong thao tác nhạy cảm; display name chỉ là một thuộc tính trình bày.
- **Nhãn xác minh** hoặc thông báo thuộc tổ chức đã xác thực khi nghiệp vụ yêu cầu; không dùng font/color giống dấu xác minh cho tên do người dùng tự đặt.
- **Hiển thị thuộc tính bổ sung** (handle, domain xác thực, avatar đã xác minh, ID) khi chuyển tiền, cấp quyền hoặc xác nhận người nhận.
- **Cảnh báo tên dễ nhầm với protected names** tại thời điểm đăng ký hoặc đổi tên, nhưng có cơ chế xử lý hợp lệ cho người dùng mang tên gần giống.
- **Không dựa vào dấu cách/zero-width hay một nét chữ duy nhất** để người dùng phân biệt hai tài khoản có quyền truy cập khác nhau.

Normalizer có thể làm một phần của khóa so sánh, nhưng bảo vệ **người dùng khi ra quyết định trên giao diện** cũng rất quan trọng.

## 12. Chính sách đăng ký tên: một pipeline có thể kiểm thử

Một hệ thống hỗ trợ Unicode usernames có thể tổ chức pipeline theo các bước sau, nhưng thứ tự và thuật toán phải được **định nghĩa thành contract** trước khi đưa vào vận hành:

```text
Nhận raw name + context (username/display-name/domain...)
             |
             v
Kiểm tra giới hạn đầu vào & encoding
             |
             v
Áp dụng các điều kiện RAW bắt buộc
(ví dụ cấm raw non-ASCII nếu profile raw ASCII-only)
             |
             v
Canonicalization theo chính sách:
NFC hoặc NFKC / case handling / protocol profile...
             |
             v
Kiểm tra canonical form:
độ dài, ký tự, cấu trúc, những chuỗi không hợp lệ
             |
             v
Tính unique key và kiểm tra trùng
(transaction + unique index)
             |
             v
Tùy nhu cầu: UTS #39 confusable/restriction checks,
protected names, nhãn xác minh, review
             |
             v
Lưu raw/display value (nếu cần),
canonical key và phiên bản policy phù hợp
```

### Không được làm mất phân biệt khi business policy yêu cầu giữ

Nếu bạn dùng NFKC và `toLowerCase(Locale.ROOT)` cho mọi loại tên mà không phân biệt trường, hai giá trị trước đó khác nhau có thể bị coi là trùng. Nếu tên đó là khóa tài khoản, việc đổi quy tắc còn có thể ảnh hưởng đăng nhập và khôi phục.

Một **schema hợp lý** trong một số hệ thống có thể chứa:

| Cột ý tưởng | Vai trò |
| --- | --- |
| `account_id` | Khóa nội bộ **không phụ thuộc tên hiển thị**. |
| `display_name_raw` | Tên người dùng muốn hiển thị theo ngôn ngữ của họ. |
| `username_key` | Khóa canonical phục vụ uniqueness/login theo policy. |
| `username_policy_version` | Giúp biết key được tính bằng quy tắc/Unicode version nào nếu có migration. |
| `confusable_review_status` | Trạng thái review hoặc cảnh báo nội bộ, không thay thế tài khoản thật. |

Đây là **schema khái niệm**, không phải yêu cầu phải dùng đúng tên cột. Một hệ thống nhỏ chỉ có ASCII usernames có thể đơn giản hơn; hệ thống Unicode đa ngôn ngữ và có nhiều miền an toàn có thể cần thêm dữ liệu.

### Bảo vệ uniqueness dưới cạnh tranh

Ngay cả khi việc normalize, validate và kiểm tra trùng đều đúng, hai yêu cầu có thể **đồng thời** xin một key. Không được chỉ làm:

```text
if (findByKey(key) == null) {
    insertAccount(key);
}
```

rồi nghĩ uniqueness đã được đảm bảo. Thao tác tìm rồi thêm không phải một khối nguyên tử. Cần **unique constraint/index** trên key đã tính theo cùng policy, kết hợp transaction và xử lý lỗi đăng ký trùng.

### Vì sao cần versioning cho confusable checks?

Dữ liệu của Unicode UTS #39 có thể được cập nhật. **Không nên lưu skeleton như một loại tên cố định được công bố rộng rãi** và giả định kết quả bất biến giữa các Unicode versions. Nếu dùng dữ liệu skeleton phục vụ review hoặc cảnh báo, ghi version, có quy trình recompute và thử collision/migration khi nâng thư viện/dữ liệu.

## 13. Rủi ro khi nâng chính sách normalization trên hệ thống đang có dữ liệu

Giả sử hệ thống cũ lưu raw usernames và chưa thực hiện normalization. Có thể tồn tại:

- `"caf\u00E9"` và `"cafe\u0301"` dưới hai account IDs khác nhau.
- `"\uFF21lice"` và `"Alice"`, vốn khác nhau trước khi chọn NFKC.
- `"ALICE_7"` và `"alice_7"` nếu tên trước đây phân biệt hoa/thường.
- Hai tên được UTS #39 đánh giá dễ nhầm nhưng vẫn có chủ sở hữu hợp lệ khác nhau.

Nếu bật một **quy tắc canonical mới** mà không migration:

1. Hai username cũ có thể **đụng unique key**.
2. User A có thể đăng nhập bằng tên giờ map sang key của User B.
3. Một chức năng đổi tên hoặc khôi phục tài khoản có thể chọn **sai tài khoản** nếu dựa vào tên thay vì account ID bất biến.
4. Dịch vụ có thể khóa nhầm tên hợp pháp khi cập nhật confusables data.
5. Frontend và backend chạy policy khác phiên bản có thể cho kết quả chấp nhận khác nhau.

**Quy trình an toàn hơn:** thử tính key mới trên **bản sao dữ liệu**, lập báo cáo tất cả collisions, phân loại/giải quyết từng trường hợp theo business policy, kiểm thử đường login/recovery/rename, rồi mới triển khai có kiểm soát. Không tự ghép, đổi ownership hoặc ghi đè account vì hai tên có normal form hay skeleton trùng nhau.

### Không thay đổi secret một cách tùy tiện

Đối với password, passphrase hoặc cryptographic secrets, normalization có thể **làm đổi bytes**. Nếu giao thức xác thực không quy định sẵn bước xử lý đó, việc bổ sung `NFKC` hay lowercase có thể làm đổi ý nghĩa secret hoặc khiến dữ liệu cũ không còn xác thực được.

Không áp một hàm `normalizeAndLowercase(...)` chung lên mọi chuỗi người dùng vì tiện tái sử dụng. Phân biệt rõ **identity strings**, **display strings** và **secrets**.

## 14. Tên miền, URL và confusables

Internationalized Domain Names (IDNs) và URL có những yêu cầu riêng:

- Domain names phải được xử lý theo **IDNA và các tiêu chuẩn/giao thức liên quan**, với thư viện tương ứng. Không phải chỉ cần `Normalizer.normalize(domain, NFKC)` rồi coi mọi thứ hợp lệ.
- Việc render domain thành Unicode hay ASCII-compatible representation ảnh hưởng cảm nhận của người dùng. Client/browser có cơ chế hiển thị và hạn chế riêng; không phải trình duyệt nào cũng hành xử giống nhau trong mọi trường hợp.
- URL còn có scheme, host, path, query, percent-encoding và các quy tắc phân tách. Normalization văn bản đơn thuần không giải quyết hết những vấn đề parsing hoặc phishing.
- Email có phần local và domain với quy tắc khác nhau; không tự lower/normalize toàn bộ địa chỉ thành một khóa duy nhất khi không có contract.

Đối với một ứng dụng chống phishing, nên xác định rõ **đâu là authority thực sự** (host được phân tích đúng bởi thư viện URL/IDNA phù hợp, danh tính nguồn gửi được xác thực) và đâu chỉ là một chuỗi được **hiển thị** cho người dùng.

Các chữ viết hỗ trợ Unicode là một tính năng quan trọng, không phải lỗi bảo mật. Vấn đề là **khi hai mã định danh khác nhau có thể bị người dùng nhầm là một trong một thao tác nhạy cảm**.

## 15. Phân loại đúng khi thấy các dấu hiệu đáng ngờ

### 15.1. Kết quả normalize khác input

`!Normalizer.isNormalized(name, Form.NFC)` **không chứng minh có hành vi tấn công**. Một bộ gõ tiếng Việt có thể tạo combining sequences hợp lệ nhưng chưa NFC. Quy trình thông thường có thể normalize theo policy hoặc yêu cầu người dùng xác nhận thay đổi; không nên mặc định gắn nhãn nguy hiểm.

### 15.2. Tên có trộn script

Một tên hỗn hợp Latin/Cyrillic có thể là dấu hiệu đáng chú ý trong một namespace bảo mật; nhưng cũng có những câu chữ, tên gọi và tổ chức đa ngữ hợp lệ. Quyết định reject/warn/review phụ thuộc **restriction level, ngữ cảnh, danh sách protected names và chính sách quốc tế hóa**.

### 15.3. Hai tên có confusable skeleton tương ứng

Đây là **tín hiệu dễ nhầm**, không phải kết luận hai tên bằng nhau ở mức Unicode canonical equality, không phải bằng chứng hai tài khoản cùng chủ, và không phải lý do tự merge/delete account.

### 15.4. Có ký tự vô hình

Không phải mọi kí tự `Default_Ignorable_Code_Point` hoặc joiner đều độc hại. Một số phục vụ cách viết và trình bày hợp lệ. Nên dùng rules của profile và yêu cầu giao thức; UI có thể làm nổi bật hoặc cảnh báo trong ngữ cảnh nhạy cảm.

### 15.5. Một chuỗi đã NFC/NFKC

Đây chỉ là trạng thái **normal form**. Phải tiếp tục các bước kiểm tra tên, quyền cấp phát, uniqueness, hiển thị và chính sách đặc biệt của hệ thống.

## 16. Những sai lầm phổ biến khi lập trình Java

| Sai lầm | Hậu quả | Thay thế đúng |
| --- | --- | --- |
| `normalize(name, NFC)` rồi coi là chống homograph | Bỏ sót Cyrillic/Latin lookalike | Dùng identifier policy, UTS #39 checks và kiểm tra tên được bảo vệ |
| `normalize(name, NFKC)` cho mọi dữ liệu | Gộp fullwidth/ligatures, có thể gây collisions hoặc mất phân biệt | Chọn NFKC theo domain/protocol, kiểm thử các mappings |
| Validate raw ASCII **sau** NFC mà tưởng đã kiểm tra raw | `U+212A` có thể map sang ASCII K | Validate raw input trước transform khi policy đòi raw ASCII |
| Xóa mọi `U+200D`/format character | Phá hỏng một số tên/emoji/scripts hợp lệ | Contextual rules và profile phù hợp |
| Chỉ cấm mixed script trong một chuỗi | Bỏ sót whole-script confusables | Dùng phân tích/rule theo UTS #39 nếu yêu cầu |
| Tự thay bảng nhỏ Cyrillic → Latin | Không đầy đủ, dễ false positive, phá dữ liệu ngôn ngữ | Dùng bộ dữ liệu confusables và implementation được duy trì |
| So sánh `String` chưa normalize khi domain cần canonical equality | Hai cách mã hóa cùng chữ bị coi khác | Normalize **cả hai** theo cùng policy |
| Gọi `String.toLowerCase()` không locale rồi cho mọi identifier | Phụ thuộc locale mặc định, thiếu chính sách case | Dùng thuật toán case của protocol; ASCII profile có thể dùng `Locale.ROOT` |
| Coi `toLowerCase(Locale.ROOT)` là Unicode casefold đầy đủ | Một số mappings không đúng contract identifier | Dùng quy tắc Unicode case folding/identifier profile phù hợp |
| Dùng `Character.UnicodeScript.of` và tuyên bố đủ UTS #39 | Bỏ qua Script_Extensions, confusable data và các checks khác | Dùng UTS #39/ICU4J khi cần chống spoofing thực sự |
| Dùng skeleton làm username chính thức | Làm sai tên, phụ thuộc dữ liệu Unicode, gây collision | Dùng skeleton **chỉ cho đánh giá confusable** |
| Dùng tên hiển thị làm khóa cấp quyền | Tên có thể đổi/nhầm/gần giống | Dùng account ID bất biến, tên chỉ là thuộc tính |
| Chỉ kiểm tra uniqueness bằng query rồi insert | Race condition | Unique constraint/transaction trên canonical key |
| Tự nâng Unicode/normalization policy không kiểm tra dữ liệu cũ | Va chạm tên và thay đổi đường login | Migration plan, collision report và test |
| Áp NFKC/lowercase lên password tùy tiện | Thay đổi bytes secret, có thể gây lỗi xác thực | Tuân theo protocol xác thực đã định nghĩa |

## 17. Chiến lược test cho namespace và security

Ngoài những 18 checks của chương trình mẫu, hệ thống thực cần một **ma trận test** theo policy.

| Loại test | Fixture gợi ý | Điều phải khẳng định |
| --- | --- | --- |
| Canonical equivalence | `"caf\u00E9"` và `"cafe\u0301"` | Key cùng nhau **nếu** policy sử dụng NFC/NFD |
| Compatibility mapping | `"\uFF21lice"` và `"Alice"` | Khác hoặc trùng **đúng theo** policy NFC/NFKC |
| Canonical singleton | `"\u212Aen"` và `"Ken"` | Raw ASCII rule không vô tình bị bỏ qua |
| Cross-script lookalike | `"paypal"` và `"p\u0430ypal"` | Normalize không gộp; kiểm tra spoof policy riêng |
| Whole-script confusable | Tên Latin và tên Cyrillic trông tương tự | Không phụ thuộc chỉ vào mixed-script detection |
| Invisible characters | `"us\u200Der"` | Quy tắc identifier xử lý đúng; hiển thị không gây nhầm |
| Chữ có dấu hợp lệ | Tên tiếng Việt dựng sẵn và tách | Unicode display policy chấp nhận và giữ dấu |
| Case policy | `"ALICE_7"` và `"alice_7"` | Username key thống nhất/uniqueness đúng |
| Multiscript hợp lệ | Tên dùng những script theo ngôn ngữ hỗ trợ | Không chặn người dùng hợp lệ trái với profile |
| Bidi display | Chuỗi kết hợp RTL/LTR được cho phép | UI thể hiện rõ danh tính trong màn hình nhạy cảm |
| Idempotence | Key sau khi áp policy lần 1/lần 2 | Kết quả không thay đổi nếu policy được định nghĩa idempotent |
| Database collision | Hai giá trị raw khác nhưng canonical key giống | Phát hiện và giải quyết đúng, không chiếm quyền |
| Concurrency | Hai request đăng ký cùng một canonical key | Chỉ một giao dịch thành công |
| Version migration | Unicode/ICU version thay đổi | Không âm thầm đổi ownership hoặc xóa tên |
| Limits | Chuỗi rất dài, combining marks lặp, surrogate bất thường | Giới hạn tài nguyên và validation ở ranh giới phù hợp |

### Test nên phân biệt ba loại kết quả

1. **Equality:** hai giá trị canonical key thực sự bằng nhau theo contract.
2. **Confusability:** hai giá trị có thể bị nhầm trong hiển thị theo cơ chế kiểm tra riêng.
3. **Authorization:** người nào được phép dùng một tên hoặc được quyền với một account ID.

Ba câu hỏi đó có thể trả lời khác nhau. Hai chuỗi confusable không nhất thiết equal; hai user có cùng display name cũng có thể là hai tài khoản độc lập; một user có tên giống tổ chức đã xác minh không đương nhiên được dùng dấu xác minh.

### Test cả trạng thái “không phát hiện rủi ro”

Không nên viết bộ test chỉ gồm tên tấn công. Cần tên hợp lệ có dấu, nhiều scripts được policy cho phép, emoji/display names khi sản phẩm cho phép, và các kiểu chữ quốc tế. Nếu bộ lọc bắt quá nhiều false positives, người dùng thật có thể không đăng ký được hoặc buộc phải đổi tên không đúng ngôn ngữ.

## 18. Câu hỏi tự kiểm tra

**1. Tại sao `Normalizer.normalize(name, Form.NFKC)` không đủ chống giả mạo “paypal”?**

Vì một chữ `а` Cyrillic (`U+0430`) có thể trông như `a` Latin nhưng không bị NFC/NFKC gộp thành cùng code point. Cần confusable detection/identifier policy riêng.

**2. Vì sao `"caf\u00E9"` và `"cafe\u0301"` có thể được coi là cùng tên sau NFC?**

Chúng canonically equivalent; cùng normal form NFC sẽ tạo cùng dãy Unicode trong ví dụ. Raw `String.equals` ban đầu vẫn có thể `false`.

**3. NFKC và NFC khác nhau thế nào về mặt bảo mật tên?**

NFKC có compatibility mappings làm thêm các chuỗi như fullwidth A/ASCII A hoặc ligature/letters trở nên giống nhau; NFC chỉ xử lý canonical equivalence. Việc dùng NFKC có thể hữu ích hoặc gây collision tùy contract.

**4. `U+212A KELVIN SIGN` có thể chứng minh bẫy nào?**

Ngay NFC cũng có thể biến một ký tự không phải ASCII thành ASCII K. Nếu requirement là raw ASCII-only, phải kiểm tra raw input trước khi normalize, không chỉ kiểm tra kết quả đã biến đổi.

**5. Một tên đã `isNormalized(name, NFC) == true` có an toàn không?**

Không thể kết luận. NFC chỉ xác nhận normal form, không kiểm tra confusables, uniqueness, quyền sở hữu hay giao diện.

**6. Có nên loại mọi tên có dấu, ký tự Cyrillic hoặc joiner khỏi mọi ứng dụng không?**

Không. Nhiều tên và hệ chữ viết hợp lệ cần các ký tự đó. Quy tắc phải theo sản phẩm và ngôn ngữ cần hỗ trợ, với kiểm tra phù hợp thay vì chặn Unicode vô điều kiện.

**7. Skeleton theo UTS #39 có nên được hiển thị làm tên đăng nhập chuẩn hóa không?**

Không. Nó là dạng trung gian cho so sánh confusables, không phải username; không bảo đảm thích hợp để hiển thị và có thể thay đổi theo phiên bản dữ liệu Unicode.

**8. `Character.UnicodeScript.of(cp)` có phải implementation đầy đủ của UTS #39 không?**

Không. Đó chỉ là một API cho script value của code point; UTS #39 còn sử dụng Script_Extensions, dữ liệu confusable, restriction levels và các cơ chế khác.

**9. Tại sao phải có unique index cho canonical username key?**

Vì hai request có thể đăng ký cùng một key đồng thời. Query kiểm tra tồn tại rồi insert không đảm bảo nguyên tử; storage phải enforce uniqueness.

**10. Nếu chuyển từ raw-name equality sang NFKC + lowercase thì cần làm gì trước?**

Chạy thử quy tắc trên toàn bộ dữ liệu, xác định collisions, kiểm thử login/rename/recovery và thống nhất contract giữa mọi tầng, sau đó triển khai migration có xử lý tranh chấp. Không tự gộp account.

**11. Bài demo từ chối tên tiếng Việt có dấu. Có chứng minh tên đó không an toàn không?**

Không. Demo dùng **strict ASCII input profile** nhằm minh họa một chính sách hẹp. Một hệ thống cho phép tên hiển thị hoặc username Unicode cần profile đa ngôn ngữ riêng.

**12. Có nên normalize hoặc lowercase password trước khi hash chỉ vì Java hỗ trợ Normalizer không?**

Không. Secret phải tuân theo policy/giao thức xác thực được công bố. Tùy tiện chuyển đổi có thể làm đổi bytes và khả năng xác thực.

## 19. Checklist triển khai an toàn

1. **Phân loại chuỗi**: username, display name, domain, email, filename hay secret.
2. **Viết rõ threat model**: mạo danh nhãn đã xác minh, protected brand, nhầm người nhận, uniqueness hay chỉ canonical comparison.
3. **Chọn identifier profile**: tập ký tự cho phép, độ dài, script/context rules và hình thức quốc tế hóa.
4. **Định nghĩa normalization form**: NFC/NFKC hoặc form theo giao thức; không để các tầng tự chọn khác nhau.
5. **Chọn case handling riêng**: case-sensitive, ASCII lowercase hay một Unicode identifier folding được quy định; đừng nhầm với normalization.
6. **Xác định kiểm tra raw vs canonical**: yêu cầu raw ASCII-only thì validate raw trước khi transform; kiểm tra kết quả cuối cho điều kiện post-transform.
7. **Dùng thư viện Unicode security đúng mục đích** nếu cần confusables/restriction checks, với version/test dữ liệu rõ ràng.
8. **Không dùng skeleton làm tên hiển thị** hoặc tên khóa đăng nhập; nó chỉ là một tín hiệu so sánh nội bộ.
9. **Bảo vệ tên đã xác minh** và quản lý cách hiển thị ở các thao tác nhạy cảm, kể cả bidi/invisible controls.
10. **Tách account ID khỏi display name**; hạn chế dùng một chuỗi hiển thị làm authorization identity.
11. **Dùng unique index + transaction** theo canonical key và kiểm tra race conditions.
12. **Có migration/collision plan** khi nâng Unicode, ICU version, normalization/case policy hoặc namespace rules.
13. **Kiểm thử đa ngôn ngữ** với cả tên hợp lệ và tên dễ nhầm; xử lý false positives như một yêu cầu sản phẩm thật.
14. **Không normalize secret tùy tiện**; kiểm tra byte/protocol/case mapping theo loại dữ liệu.
15. **Giới hạn tài nguyên**: độ dài chuỗi, số combining marks và chi phí xử lý confusable trong request lớn.
16. **Giám sát kết quả**: log có bảo vệ dữ liệu cá nhân, phát hiện va chạm tên và cập nhật rules dựa trên kết quả kiểm thử thực tế.

## Tài liệu chính thức đang có hiệu lực

- [Oracle Java SE 26 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized` và bốn `Normalizer.Form`.
- [Unicode UAX #15 — Unicode Normalization Forms, Unicode 18.0](https://www.unicode.org/reports/tr15/): các khái niệm canonical/compatibility và sự ổn định normalization.
- [Unicode UTS #39 — Unicode Security Mechanisms, Unicode 18.0](https://www.unicode.org/reports/tr39/): confusable detection, skeleton, mixed-script/restriction level và giới hạn bảo mật.
- [Unicode UAX #31 — Unicode Identifiers and Syntax, Unicode 18.0](https://www.unicode.org/reports/tr31/): thiết kế identifier profile, normalization và case handling.
- [ICU4J — `SpoofChecker` Javadoc](https://unicode-org.github.io/icu-docs/apidoc/released/icu4j/com/ibm/icu/text/SpoofChecker.html): một API chuyên biệt để thực hiện một số Unicode spoof checks; là thư viện ngoài Java SE.
- [Oracle Java SE 26 — `Character.UnicodeScript`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.UnicodeScript.html): thuộc tính script cơ bản trong Java, không tự thay thế UTS #39.

**Ghi nhớ:** **Normalization không đồng nghĩa bảo mật tên.** NFC/NFD giải quyết canonical equivalence; NFKC/NFKD xử lý cả compatibility mappings nhưng vẫn không tự phát hiện homoglyph Latin–Cyrillic, ký tự khó nhìn, bidi spoofing hoặc tên mạo danh. Để bảo vệ identifier, cần **chính sách rõ ràng về input/canonical form, kiểm thử Unicode security, uniqueness nhất quán, bảo vệ tên quan trọng và giao diện không gây hiểu nhầm**. Đồng thời phải bảo toàn khả năng dùng tên hợp lệ của người dùng đa ngôn ngữ.
