# Chuẩn hóa văn bản bằng java.text.Normalizer

## 1. Vì sao Java cần chuẩn hóa văn bản Unicode?

Hai chuỗi nhìn như nhau trên giao diện có thể chứa các **dãy Unicode code point khác nhau**. Ví dụ ký tự `é` có thể được lưu bằng một code point `U+00E9`, hoặc bằng hai code points `U+0065` (chữ `e`) và `U+0301` (combining acute accent).

~~~text
"Café"         = U+0043 U+0061 U+0066 U+00E9
"Cafe\u0301"   = U+0043 U+0061 U+0066 U+0065 U+0301

Hai chuỗi trông tương tự, nhưng:
    String.equals(...)               -> false
    equals sau khi cả hai được NFC   -> true
~~~

Hai dạng này là **canonically equivalent** theo Unicode; tuy nhiên `String.equals`, `HashMap` và các phép so sánh key chính xác không tự làm Unicode normalization.

`java.text.Normalizer` cung cấp cách biến đổi text sang **một Unicode normalization form được xác định rõ**. API này đã được cung cấp từ Java 6 và vẫn nằm trong **Java SE hiện hành**. Bài học sử dụng những API được hỗ trợ và ví dụ Java **17+**, không phụ thuộc công cụ lỗi thời hay thư viện ngoài.

### Phân biệt những bài toán thường bị trộn lẫn

| Nhiệm vụ | Có phải Unicode normalization? |
| --- | --- |
| Đưa `é` và `e + ◌́` về cùng biểu diễn | Có, bằng NFC hoặc NFD |
| Đưa ligature `ﬃ` về `ffi` | Có, bằng NFKC/NFKD, **mất compatibility distinction** |
| Chuyển chữ hoa về chữ thường | Không, đây là case conversion/folding |
| Bỏ dấu để tìm kiếm “cafe” khớp “café” | Không, là một biến đổi phụ có thể mất nghĩa |
| Chuẩn hóa byte UTF-8 đã decode sai | Không, cần xử lý encoding trước |
| Chống Unicode spoofing, SQL injection, path traversal | Không, cần các quy tắc bảo mật độc lập |

**Nguyên tắc:** normalize làm nhất quán **biểu diễn Unicode**, không tự động “làm sạch” mọi trường dữ liệu.

## 2. Bốn Normalizer.Form

`java.text.Normalizer.Form` có bốn enum constants theo [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/):

| Form | Thuật toán | Tính chất |
| --- | --- | --- |
| `NFD` | Canonical Decomposition | Tách canonical components, sắp combining marks |
| `NFC` | Canonical Decomposition + Composition | Tạo dạng canonical composed khi có thể |
| `NFKD` | Compatibility Decomposition | Tách cả compatibility characters |
| `NFKC` | Compatibility Decomposition + Composition | Gộp các compatibility mappings rồi compose |

Có thể dùng tên đầy đủ `Normalizer.Form.NFC`, `Normalizer.Form.NFD`, `Normalizer.Form.NFKC`, `Normalizer.Form.NFKD` hoặc import `Normalizer.Form` và viết `Form.NFC`, v.v.

### 2.1. Canonical và compatibility khác nhau

- **Canonical equivalence:** hai biểu diễn được Unicode xem là cùng nội dung văn bản. `Café` có `U+00E9` và `Cafe\u0301` có `U+0065 U+0301` thuộc nhóm này.
- **Compatibility equivalence:** các dạng tương tự nhau về một mặt biểu diễn nhưng có thể khác về ý nghĩa bố cục/ký hiệu. Ví dụ ligature `ﬃ`, số khoanh tròn `①`, full-width `Ａ`.

Ví dụ:

~~~text
NFC("ﬃ")  = "ﬃ"
NFKC("ﬃ") = "ffi"

NFC("①")  = "①"
NFKC("①") = "1"

NFC("Ａ")  = "Ａ"
NFKC("Ａ") = "A"
~~~

NFKC/NFKD **không phải phiên bản luôn tốt hơn** của NFC/NFD. Chúng làm mất những khác biệt compatibility. Điều đó có thể đúng với search key, nhưng không đúng nếu dữ liệu gốc cần bảo tồn glyph/biểu tượng, nhãn hiệu hay ký hiệu khoa học.

### 2.2. Chọn form theo nhu cầu

- **Văn bản thông thường/trao đổi text:** NFC là lựa chọn phổ biến để giữ canonical equality và khả năng tương thích với nhiều hệ thống.
- **Phân tích combining marks:** NFD khi cần làm việc ở mức base + mark.
- **Search key/identifier có chính sách compatibility:** NFKC có thể được chọn có chủ đích, sau khi chấp nhận collision.
- **Xử lý nội bộ cần compatibility decomposition:** NFKD.
- **Tên người dùng, mật khẩu, chữ ký số hoặc giao thức định danh:** phải làm theo **quy định riêng của hệ thống/giao thức**, không tự ý thay form trong khi đang vận hành.

Normalization có thể thay số code points, nhưng NFC **không nhất thiết ghép mọi chuỗi dấu thành một code point**. Có các tổ hợp không tồn tại dạng precomposed duy nhất. NFD/NFKD cũng thực hiện **canonical ordering** cho combining marks, không đơn giản thay thế từng ký tự bằng một bảng ánh xạ.

## 3. Hai phương thức chuẩn của Normalizer

~~~java
public static String normalize(CharSequence src, Normalizer.Form form);
public static boolean isNormalized(CharSequence src, Normalizer.Form form);
~~~

Đây là **chữ ký API**, không phải Java source file độc lập.

### 3.1. normalize

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;

String canonical = Normalizer.normalize("Cafe\u0301", Form.NFC);
String decomposed = Normalizer.normalize("Caf\u00E9", Form.NFD);
String compatibility = Normalizer.normalize("\uFB03", Form.NFKC);
~~~

Đây là **đoạn minh họa**. `normalize` nhận `CharSequence`, trả về `String` đã được đưa về form đã chọn; nó không sửa `String` gốc vì `String` bất biến.

### 3.2. isNormalized

~~~java
boolean alreadyNfc = Normalizer.isNormalized("Cafe\u0301", Form.NFC);
~~~

Kết quả của fixture này là `false`. `isNormalized` kiểm tra **đúng form yêu cầu**, không đánh giá tính hợp lệ của filename, username, ký tự điều khiển hoặc an toàn bảo mật.

Trong code đơn giản, có thể gọi `normalize` trực tiếp mà không kiểm tra `isNormalized` trước. Chỉ tối ưu thêm bước kiểm tra khi có số liệu hiệu năng trên workload thật.

### 3.3. Các hợp đồng API cần nhớ

- `normalize(null, Form.NFC)`, `isNormalized(null, Form.NFC)` hoặc truyền `null` làm form: **`NullPointerException`**.
- Phải chuẩn hóa **cả hai chuỗi** hoặc đảm bảo dữ liệu đã chuẩn hóa nhất quán trước `equals`/`hashCode`/index.
- Các form đều có tính **idempotence**: chuẩn hóa cùng form thêm lần nữa không đổi kết quả đã normalized.
- `Form.NFC` không tương đương `Form.NFKC`; chuyển từ form này sang form kia là **đổi chính sách dữ liệu**, không chỉ thay cách viết code.

## 4. Ví dụ chạy được Java 17+: NormalizeDemo.java

File này quan sát raw equality, NFC/NFD, NFKC compatibility, chuỗi tiếng Việt và giới hạn của phương pháp bỏ dấu.

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public final class NormalizeDemo {
    static String nfc(String text) {
        return Normalizer.normalize(text, Form.NFC);
    }

    static String searchKey(String text) {
        return Normalizer.normalize(text, Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }

    static String looseLatinSearch(String text) {
        return Normalizer.normalize(text, Form.NFD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);
    }

    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";
        System.out.println("raw-equal=" + composed.equals(decomposed));
        System.out.println("nfc-equal=" + nfc(composed).equals(nfc(decomposed)));
        System.out.println("nfd-equal=" + Normalizer.normalize(composed, Form.NFD)
                .equals(Normalizer.normalize(decomposed, Form.NFD)));
        System.out.println("already-nfc=" + Normalizer.isNormalized(decomposed, Form.NFC));
        System.out.println("nfc-idempotent=" + nfc(nfc(decomposed)).equals(nfc(decomposed)));
        System.out.println("nfd-codepoints=" + codePoints(
                Normalizer.normalize(composed, Form.NFD)));

        String ligature = "\uFB03";
        System.out.println("ligature-nfc-unchanged=" +
                Normalizer.normalize(ligature, Form.NFC).equals(ligature));
        System.out.println("ligature-nfkc=" + Normalizer.normalize(ligature, Form.NFKC));
        System.out.println("circled-nfkc=" + Normalizer.normalize("\u2460", Form.NFKC));
        System.out.println("fullwidth-nfkc=" + Normalizer.normalize("\uFF21", Form.NFKC));
        System.out.println("vietnamese-nfc-equal=" +
                nfc("Vi\u1EC7t").equals(nfc("Vie\u0323\u0302t")));
        System.out.println("search-key-match=" +
                searchKey("\uFF21BC").equals(searchKey("abc")));
        System.out.println("key-collision=" +
                searchKey("o\uFB03ce").equals(searchKey("office")));
        System.out.println("loose-cafe=" + looseLatinSearch("Caf\u00E9"));
        System.out.println("loose-d-stroke=" + looseLatinSearch("\u0111"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac -encoding UTF-8 --release 17 NormalizeDemo.java
java NormalizeDemo
~~~

**Stdout chính xác đã kiểm chứng** trên OpenJDK 24 và `--release 17`:

~~~text
raw-equal=false
nfc-equal=true
nfd-equal=true
already-nfc=false
nfc-idempotent=true
nfd-codepoints=U+0043 U+0061 U+0066 U+0065 U+0301
ligature-nfc-unchanged=true
ligature-nfkc=ffi
circled-nfkc=1
fullwidth-nfkc=A
vietnamese-nfc-equal=true
search-key-match=true
key-collision=true
loose-cafe=cafe
loose-d-stroke=đ
~~~

### Giải thích kết quả

**Raw và canonical equality.** `raw-equal=false` vì chuỗi `composed` kết thúc bằng `U+00E9`, còn `decomposed` bằng `U+0065 U+0301`. `nfc-equal=true` và `nfd-equal=true` chứng minh hai phía có cùng canonical-normalized result khi dùng **một form nhất quán**.

**isNormalized.** `already-nfc=false` cho biết bản decomposed chưa ở NFC. Nó không có nghĩa text “sai Unicode” hay không hợp lệ làm tiếng Việt.

**Idempotence.** `nfc-idempotent=true` nghĩa NFC của kết quả NFC không đổi nữa. Khi viết test cho tính chất này, dùng `String.equals` thay vì toán tử `==` của Java, vốn kiểm tra tham chiếu.

**Quan sát code points.** `nfd-codepoints` có `U+0065 U+0301` ở cuối: canonical decomposition của `é`. Hàm `String.codePoints()` giúp debug chính xác, không phụ thuộc glyph terminal.

**Compatibility mappings.** `ﬃ` được NFC giữ lại, nhưng NFKC biến thành `ffi`; `①` thành `1`, `Ａ` thành `A`. Cần đánh giá lossiness trước khi dùng NFKC vào dữ liệu gốc.

**Tiếng Việt.** `vietnamese-nfc-equal=true` vì chữ `ệ` đã ghép sẵn và chuỗi `e + dấu nặng + dấu mũ` được NFC đưa về cùng dạng. Điều này đặc biệt quan trọng với dữ liệu nhập từ nhiều hệ điều hành, bàn phím hoặc file.

**Key collision.** `search-key-match=true` là hành vi mong muốn trong ví dụ search key dùng NFKC + lowercase. `key-collision=true` nhắc rằng hai bản khác nhau `"oﬃce"` và `"office"` có thể trở thành **cùng key**.

**Bỏ dấu không hoàn chỉnh.** `loose-cafe=cafe` nhưng `loose-d-stroke=đ`: normalization không phải công cụ transliteration đầy đủ.

## 5. Unit test cho chính sách chuẩn hóa

Thêm file `NormalizerPolicyTest.java`, độc lập với file demo:

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;

public final class NormalizerPolicyTest {
    static String canonicalKey(String text) {
        return Normalizer.normalize(text, Form.NFC);
    }

    static String compatibilityKey(String text) {
        return Normalizer.normalize(text, Form.NFKC).toLowerCase(Locale.ROOT);
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        String composed = "Caf\u00E9", decomposed = "Cafe\u0301";
        check(!composed.equals(decomposed), "fixture should differ");
        check(canonicalKey(composed).equals(canonicalKey(decomposed)),
                "canonical equivalents must share key");
        check(Normalizer.isNormalized(canonicalKey(decomposed), Form.NFC),
                "key must be NFC");
        check(canonicalKey(canonicalKey(decomposed))
                .equals(canonicalKey(decomposed)), "NFC must be idempotent");
        System.out.println("canonical-tests=PASS");

        String ligature = "o\uFB03ce";
        String letters = "office";
        check(!canonicalKey(ligature).equals(canonicalKey(letters)),
                "NFC must not collapse compatibility characters");
        check(compatibilityKey(ligature).equals(compatibilityKey(letters)),
                "NFKC should collapse ligature");
        check(compatibilityKey("\uFF21BC").equals("abc"),
                "NFKC and ROOT lowercase should fold fullwidth A");
        System.out.println("compatibility-tests=PASS");

        check(!Normalizer.normalize("Caf\u00E9", Form.NFC).equals("Cafe"),
                "NFC is not accent removal");
        check(Normalizer.normalize("\u0111", Form.NFD).equals("\u0111"),
                "NFD should not rewrite d with stroke");
        System.out.println("limitations-tests=PASS");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 --release 17 NormalizerPolicyTest.java
java NormalizerPolicyTest
~~~

**Kết quả chính xác** (đã chạy trên OpenJDK 24):

~~~text
canonical-tests=PASS
compatibility-tests=PASS
limitations-tests=PASS
~~~

Ba nhóm test nhắm tới ba hợp đồng riêng: **canonical equality và idempotence**, **compatibility collapse theo policy** và **những điều normalization không nên làm**. Một assertion sai sẽ ném `AssertionError`, không giả vờ in kết quả đạt.

Khi đưa lên JUnit, có thể thay `check` bằng `assertTrue/assertFalse/assertEquals` nhưng nên giữ nguyên fixture Unicode bằng `\uXXXX` để tests không phụ thuộc font/IME.

## 6. Dùng Normalizer với HashMap, Set và database

`String.equals`/`hashCode` không biết canonical equivalence. Nếu một `HashMap<String, Integer>` nhận tên `Café` dạng composed và decomposed mà không normalize, chúng có thể thành **hai keys khác nhau**.

Ví dụ một đoạn code trong hàm xử lý input (biến `nameFromInput` do ứng dụng cung cấp):

~~~java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
String key = java.text.Normalizer.normalize(
        nameFromInput, java.text.Normalizer.Form.NFC);
counts.merge(key, 1, Integer::sum);
~~~

Đây là **đoạn minh họa không độc lập**. Khi hai bản canonical-equivalent đều qua NFC, các lượt đếm sẽ vào cùng entry.

### 6.1. Cùng policy ở write và read/query

Một pipeline hợp lý:

~~~text
Input (web/API/import)
    |
    v
Kiểm tra kích thước đầu vào/null
    |
    v
Normalize theo policy của field (ví dụ NFC)
    |
    v
Validation của giá trị thực tế sẽ lưu
    |
    +--> displayValue (giữ raw nếu cần audit)
    +--> canonicalKey
    +--> searchKey riêng nếu cần matching rộng
    |
    v
Database / search index

Query cũng phải đi qua CÙNG key normalization policy.
~~~

Nếu chỉ normalize lúc lưu mà lookup dùng raw input, một cách biểu diễn khác vẫn có thể miss bản ghi. Nếu chỉ normalize query mà dữ liệu cũ chưa chuẩn hóa, cũng có thể miss.

### 6.2. Unique index và compatibility collision

Một khi NFKC được dùng làm key unique, `"oﬃce"` và `"office"` có thể collide. Trong một số hệ thống đó là mong muốn; với dữ liệu khác đó là một thay đổi phá vỡ semantics.

Nếu migrate từ NFC sang NFKC: tính key mới cho **toàn bộ dữ liệu**, kiểm tra collisions, định nghĩa cách giải quyết, reindex rồi mới đổi chính sách ghi/đọc. Đừng âm thầm đổi code mà bỏ qua dữ liệu đã tồn tại.

Database collation và search analyzer có thể khác cách Java so sánh; `Normalizer` không đồng nghĩa database tự dùng cùng Unicode version hoặc cùng quy tắc index. Cần test end-to-end.

### 6.3. Giữ bản gốc để hiển thị

Khi ứng dụng muốn search không phân biệt compatibility, có thể lưu **original text cho display** và một **derived search key**. Không hiển thị search key NFKC thay cho tên người dùng nếu việc thay ligature, full-width hay ký hiệu gây mất nghĩa.

## 7. Normalizer khác chữ hoa/chữ thường

`Normalizer.normalize` **không tự lowercase/case fold**. Demo dùng:

~~~java
static String searchKey(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFKC)
            .toLowerCase(java.util.Locale.ROOT);
}
~~~

Đây là đoạn trích của `NormalizeDemo`. `Locale.ROOT` hữu ích với key kỹ thuật khi không muốn phụ thuộc default locale của máy.

Nhưng `String.toLowerCase(Locale.ROOT)` **không phải full Unicode case folding** cho mọi trường hợp. Tiếng Thổ Nhĩ Kỳ có các quy tắc chữ `I` khác biệt; một số ngôn ngữ có biến thể chữ hoa/thường phụ thuộc ngữ cảnh. Nếu mục đích là so sánh/ngôn ngữ học, nên xem **locale-aware collation** hoặc thư viện Unicode/casefold thích hợp.

**Không coi “NFKC + lowercase” là một sanitizer bảo mật hay tương đương hoàn chỉnh với Unicode `NFKC_Casefold`.** Nó chỉ là một search policy mẫu.

## 8. NFD + regex bỏ dấu là một phép biến đổi *khác*

Hàm trong demo:

~~~java
static String looseLatinSearch(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFD)
            .replaceAll("\\p{M}+", "")
            .toLowerCase(java.util.Locale.ROOT);
}
~~~

Nó có hai bước:

1. `NFD` là **Unicode normalization**, tách canonical components.
2. `replaceAll("\\p{M}+", "")` chủ động **xóa mọi Unicode marks**. Đó là **phép bỏ thông tin**, không nằm trong bản thân `Normalizer`.

Với `Café`, kết quả là `cafe`, có thể giúp tìm kiếm lỏng cho một số trường Latin. Nhưng dấu tiếng Việt và combining marks của nhiều ngôn ngữ có ý nghĩa, vì vậy **không nên sửa display text hoặc dữ liệu gốc** theo cách này.

Chữ `đ` không canonical-decompose thành `d` + mark, nên `NFD("đ")` vẫn là `đ`. Nếu nghiệp vụ thực sự muốn `đ→d`, cần **transliteration rule riêng** và tests riêng. `NFKD` cũng không tự chuyển mọi hệ chữ sang ASCII.

Đối với tìm kiếm nhiều ngôn ngữ, có thể cân nhắc search analyzer hoặc `java.text.Collator` theo locale. `Collator` quản lý so sánh/sắp xếp theo quy tắc ngôn ngữ, **khác** `Normalizer`.

## 9. Unicode code point không phải UTF-16 char hay grapheme

Trong Java:

| Phép đo | Ý nghĩa |
| --- | --- |
| `s.length()` | Số UTF-16 **code units** |
| `s.codePointCount(0, s.length())` | Số Unicode **code points** |
| `s.codePoints()` | Duyệt Unicode code points |
| Grapheme segmentation (Unicode UAX #29) | Các **ký tự người dùng cảm nhận** |

Sau normalization, số code points/code units có thể thay đổi dù glyph nhìn như nhau. Một emoji hay chữ có combining marks có thể là **nhiều code points nhưng một grapheme cluster**. Vì vậy `String.length()` không phải số chữ nhìn thấy.

### 9.1. Không normalize các chunk độc lập một cách mù quáng

Nếu một chuỗi bị chia:

~~~text
Chunk A = "e"
Chunk B = "\u0301"

NFC(A) + NFC(B) có thể KHÁC NFC(A + B).
~~~

Combining mark ở đầu chunk B có thể phải ghép với base letter ở cuối chunk A. Nếu cần streaming, phải dùng algorithm nhận biết **Unicode normalization boundaries**; nếu không, normalize sau khi ghép chuỗi đủ dữ liệu. Khi cắt UTF-16 cũng tránh cắt giữa surrogate pair; khi cắt để hiển thị cần xét grapheme boundaries.

### 9.2. Normalization không chữa lỗi encoding

`java.text.Normalizer` nhận **chuỗi Unicode đã decode**. Nếu dữ liệu UTF-8 bị đọc bằng sai charset và trở thành mojibake, việc gọi NFC không khôi phục được byte gốc. Sửa decoder/encoding ở khâu ingestion trước khi normalize.

## 10. Security: normalization không phải cơ chế chống giả mạo

Normalization có ích để giảm các biểu diễn canonical không nhất quán, nhưng có giới hạn:

- **Unicode confusables/homoglyphs:** ký tự Latin và Cyrillic có thể trông giống nhau mà không canonical/compatibility-equivalent. NFKC không phải bộ lọc chống mọi spoofing.
- **Invisible/bidirectional/control characters:** normalization không tự loại tất cả ký tự format có thể ảnh hưởng UI hoặc chính sách đặt tên.
- **Path/URL/SQL/HTML:** vẫn cần input validation, parameterized SQL, output escaping, path restrictions và authorization đúng chuẩn.
- **NFKC collision:** các giá trị trước đây khác nhau có thể trở thành cùng một key; đó là quyết định nghiệp vụ và bảo mật cần xét.
- **Mật khẩu và chữ ký số:** không âm thầm thêm NFC/NFKC vào input trước khi hash/ký nếu giao thức hoặc phiên bản đã triển khai không quy định rõ.
- **Check one string, use another:** nếu validate một biến thể nhưng authorization/file lookup dùng biến thể đã normalize khác, có thể tạo mismatch. Pipeline phải kiểm tra **giá trị cuối cùng thực sự được dùng**.

Khi phải bảo vệ tên đăng nhập/identifier trước Unicode spoofing, xem [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/) và security profile phù hợp; đừng chỉ gọi `Normalizer.normalize(..., NFKC)` rồi cho rằng đủ.

## 11. Versioning và tính ổn định

Unicode quy định các **normalization stability guarantees** quan trọng cho những code points đã được gán. Tuy vậy một hệ thống nhiều JVM hoặc nhiều Unicode data versions cần đánh giá trường hợp các code points chưa được gán trong phiên bản cũ.

Ngoài ra, **case conversion, collation, segmentation và confusables** không phải cùng một vấn đề với normalization. Nếu ứng dụng đổi từ NFC sang NFKC, thêm lowercase hoặc bỏ dấu thì đó là **đổi chính sách dữ liệu**, cần migration và test cho các collisions mới.

Trong dự án production:

1. Ghim JDK/toolchain phù hợp và test Unicode fixtures quan trọng.
2. Định nghĩa form theo từng field; không dùng một kiểu normalization cho mọi dữ liệu.
3. Áp dụng cùng policy ở lưu trữ, tra cứu và index.
4. Kiểm tra null, giới hạn input và giới hạn độ dài trên dạng dữ liệu được lưu.
5. Giữ bản gốc khi cần audit/hiển thị chính xác.
6. Test tiếng Việt nhiều dấu, compatibility characters, case conversion đa ngôn ngữ và multi-script.
7. Khi đổi policy, kiểm tra collisions rồi reindex/migrate.
8. Đo hiệu năng thực tế trước khi thêm cache hay `isNormalized` ở hot path.

## 12. Bảng lỗi thường gặp

| Hiện tượng | Vì sao? | Cách xử lý |
| --- | --- | --- |
| Hai text nhìn giống nhưng `equals` trả `false` | Khác canonical representation | Normalize cả hai về cùng NFC/NFD |
| NFC vẫn giữ dấu tiếng Việt | NFC không phải bỏ dấu | Dùng policy search riêng nếu thật sự cần |
| `đ` không thành `d` sau NFD | Không có canonical decomposition tương ứng | Transliteration theo domain |
| Ligature bị đổi thành ba chữ | NFKC/NFKD compatibility folding | Dùng NFC để giữ phân biệt |
| Username trùng sau migration | Key NFKC tạo collision | Kiểm tra/migrate/giải quyết trùng |
| `isNormalized` trả true nhưng vẫn có ký tự lạ | Kiểm tra form, không kiểm tra tính hợp lệ | Validation/sanitization riêng |
| `NullPointerException` | `src` hoặc `form` null | Validate null theo contract |
| Case-insensitive key sai ngôn ngữ | Locale/case mapping không phù hợp | Locale-aware handling |
| Database match khác JVM | Khác collation/normalization policy | Test end-to-end |
| Normalize từng chunk cho kết quả khác | Cắt qua combining sequence | Normalize toàn chuỗi/boundary-safe |
| `String.length` gây hiểu nhầm | UTF-16 khác code points/graphemes | Dùng đúng metric |
| Ký tự nhìn giống vẫn là hai key | Confusables không phải normalization | Dùng Unicode security checks |
| Text hỏng encoding không được sửa | Decode bytes sai | Sửa charset ở input |

## 13. Câu hỏi ôn tập

**1.** Vì sao `"Café".equals("Cafe\u0301")` có thể trả `false`? — Vì hai chuỗi chứa code points khác nhau. Cần cùng form trước khi so sánh canonical equality.

**2.** NFC khác NFKC thế nào? — NFC giữ compatibility distinctions; NFKC có thể đổi `ﬃ→ffi`, `①→1`, `Ａ→A` và mất một số khác biệt hình thức.

**3.** `isNormalized(..., NFC) == true` có bảo đảm username an toàn không? — Không. Nó không kiểm tra confusables, ký tự cấm, authorization hay các quy tắc nghiệp vụ.

**4.** NFD có tự bỏ dấu không? — Không. `NFD` tách các thành phần canonical; xóa marks bằng regex là một phép biến đổi bổ sung, thường mất thông tin.

**5.** Vì sao `đ` không thành `d` sau NFD? — Không có canonical decomposition `đ → d + combining mark`. Transliteration cần quy tắc khác.

**6.** Làm sao để tra cứu database nhất quán? — Tính cùng normalization key cho dữ liệu ghi và input tìm kiếm; kiểm tra luôn database collation/index.

**7.** NFKC + lowercase ROOT có chống Unicode spoofing đầy đủ không? — Không; full case folding, confusables và identifier security là các bài toán khác.

**8.** Normalize chunk A và chunk B rồi ghép có luôn bằng normalize chuỗi ghép không? — Không. Combining mark có thể nằm qua ranh giới hai chunk.

### Bài tập tự thực hành

1. Thêm `"A\u030A"` và `"\u00C5"`, in code points trước/sau NFC/NFD và assert equality.
2. So sánh `"①"` với `"1"` dưới NFC và NFKC; giải thích tại sao kết quả khác.
3. Tạo `HashMap<String, Integer>` dùng key NFC, nhập cả `"Café"` và `"Cafe\u0301"`; yêu cầu một key và tổng count bằng 2.
4. Chuẩn hóa hai cách biểu diễn `"Việt"` rồi kiểm tra idempotence.
5. Thiết kế `displayName`, `canonicalName` và `searchKey` cho một hệ thống, mô tả collisions khi thay policy.
6. Viết test `Normalizer.normalize(null, Form.NFC)` ném `NullPointerException`, không âm thầm đổi thành `""`.

## 14. Tài liệu chính thức còn áp dụng

- [Java SE 26 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized`, canonical và compatibility equivalence.
- [Java SE 26 — Normalizer.Form](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.Form.html): NFC, NFD, NFKC, NFKD.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): API cho ví dụ `--release 17`.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/): thuật toán và normalization forms.
- [Unicode FAQ — Normalization](https://www.unicode.org/faq/normalization.html): form choice, stability và compatibility.
- [Java SE 26 — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): `equals` và `codePoints`.
- [Java SE 26 — Pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): Unicode marks `\p{M}`.
- [Java SE 26 — Collator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html): locale-aware comparison.
- [Unicode Technical Standard #39](https://www.unicode.org/reports/tr39/): Unicode security và confusables.

**Ghi nhớ:** `Normalizer` là công cụ chuẩn hóa **biểu diễn Unicode**. Dùng NFC khi muốn canonical equality mà giữ compatibility distinctions; dùng NFKC có chủ đích khi chấp nhận compatibility folding. Bỏ dấu, case folding, locale matching và bảo mật phải được thiết kế riêng, không đánh đồng với normalization.
