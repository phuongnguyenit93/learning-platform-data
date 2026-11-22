# Ảnh hưởng của compatibility normalization đến ý nghĩa văn bản trong Java

## 1. Vấn đề: hai cách viết giống nhau có chắc mang cùng ý nghĩa?

Trong ứng dụng quốc tế hóa, cùng một thông tin có thể được nhập bằng nhiều dạng Unicode. Có những khác biệt chỉ là **cách mã hóa** của cùng một ký tự trừu tượng; lại có những khác biệt biểu thị **kiểu chữ, chức năng trình bày, toán học, ký hiệu đơn vị hoặc cấu trúc**. Unicode gọi hai nhóm này là:

- **Canonical equivalence:** hai chuỗi được Unicode coi là tương đương về ký tự cơ bản; chẳng hạn `é` có thể là một code point `U+00E9` hoặc `e` + combining acute accent `U+0065 U+0301`.
- **Compatibility equivalence:** một ký tự hoặc chuỗi có thể có dạng “tương thích” gần với dạng khác, nhưng khác biệt đó **có thể có ý nghĩa**. Ví dụ `①` (số 1 được khoanh) và `1` (chữ số 1), `²` (số mũ 2) và `2`, ký tự `Ⅳ` và hai chữ `IV`.

**Compatibility normalization** là quá trình chọn một dạng đại diện chung **bằng cách bỏ những khác biệt tương thích**. Các dạng Unicode thực hiện điều đó là **NFKC** và **NFKD**.

Đây là công cụ hữu ích cho **tra cứu gần đúng, khớp định danh theo quy tắc đã chọn, kiểm tra một số nhóm ký tự**. Nhưng nó là phép biến đổi **nhiều-đến-một và mất thông tin**. Áp dụng NFKC/NFKD bừa bãi lên văn bản gốc có thể khiến công thức, thứ tự đánh số, cách trình bày hoặc ngữ nghĩa của ký hiệu bị thay đổi.

Trong Java 17+, API chuẩn còn dùng là `java.text.Normalizer` với bốn giá trị `Normalizer.Form`. Bài sẽ chỉ rõ:

1. Khi nào canonical và compatibility normalization cho kết quả khác nhau.
2. Những ký tự nào bị gộp và **vì sao khác biệt đó quan trọng**.
3. Cách thực thi/kiểm thử bằng Java, kể cả các ký tự ngoài BMP.
4. Tác động lên tìm kiếm, mã định danh, dữ liệu lưu trữ, bảo mật và di chuyển dữ liệu.
5. Cách chọn chính sách normalization mà không vô tình làm mất bản gốc.

## 2. Bốn Unicode Normalization Forms

Unicode Standard Annex #15 (UAX #15) xác định bốn dạng chuẩn:

| Dạng | Nguyên lý | Loại tương đương được gộp | Đặc trưng |
| --- | --- | --- | --- |
| **NFC** | Canonical decomposition, rồi canonical composition | Canonical | Giữ phần lớn ký tự ở dạng ghép khi có thể; thường phù hợp để lưu văn bản thông thường |
| **NFD** | Canonical decomposition | Canonical | Tách base letter và combining marks ở những trường hợp có phân rã canonical |
| **NFKC** | **Compatibility** decomposition, rồi canonical composition | Cả canonical và compatibility | Có thể biến ký hiệu khác biệt thành chữ/số thông thường, gộp những chuỗi trước đây không giống nhau |
| **NFKD** | **Compatibility** decomposition | Cả canonical và compatibility | Vừa phân rã các compatibility characters, vừa để ở dạng decomposed; không tự xóa dấu |

Trong API Java:

~~~java
import java.text.Normalizer;

String nfc  = Normalizer.normalize(value, Normalizer.Form.NFC);
String nfd  = Normalizer.normalize(value, Normalizer.Form.NFD);
String nfkc = Normalizer.normalize(value, Normalizer.Form.NFKC);
String nfkd = Normalizer.normalize(value, Normalizer.Form.NFKD);
~~~

Đây là **đoạn minh họa trong một method** với biến `value` đã khai báo. Nếu `value == null`, phải xử lý theo hợp đồng của ứng dụng thay vì tự truyền null vào API. `Normalizer.normalize` không sửa chuỗi `String` ban đầu; nó trả một `String` chứa dạng chuẩn hóa.

**Ý nghĩa chữ K:** trong `NFKC` và `NFKD`, `K` biểu thị **compatibility**; không có nghĩa “kiểu nén mạnh hơn” hay “luôn tốt hơn NFC”. Cả NFKC/NFKD đều sử dụng compatibility mappings, còn NFC/NFD chỉ dùng canonical mappings. NFC và NFKC là các dạng **composed**; NFD và NFKD là các dạng **decomposed**.

Với dữ liệu văn bản cần giữ ý nghĩa và hình thức, NFC là lựa chọn cơ sở phổ biến; với **một phạm vi định danh cụ thể và quy tắc rõ ràng**, NFKC có thể hữu ích. Không có một normalization form duy nhất luôn đúng cho tất cả trường hợp.

### Canonical normalization không đồng nghĩa bỏ dấu

Ví dụ:

~~~text
Chuỗi 1: U+00E9           (é)
Chuỗi 2: U+0065 U+0301    (e + COMBINING ACUTE ACCENT)

NFC(chuỗi 1) = NFC(chuỗi 2) = U+00E9
NFD(chuỗi 1) = NFD(chuỗi 2) = U+0065 U+0301
~~~

Đây là **ví dụ mô tả code points**, không phải chuỗi literal để biên dịch. Với tiếng Việt, các thanh điệu và dấu chữ cái cũng có thể được biểu diễn qua precomposed characters hoặc combining sequences. NFC giúp thống nhất những chuỗi tương đương canonical mà **không chủ động biến chữ có dấu thành chữ không dấu**.

Ví dụ, `Normalizer.normalize("ế", Form.NFD)` có thể trả về chuỗi gồm ký tự cơ sở và combining marks, **không phải** chữ `e` trơn. NFKD cũng **không** có chức năng tổng quát “xóa dấu tiếng Việt”. Việc bỏ dấu bằng cách loại combining marks là **một phép biến đổi khác, có thể làm thay đổi nghĩa từ** và phải có chính sách riêng.

## 3. Compatibility normalization thay đổi dữ liệu ra sao?

Bảng sau dùng các ánh xạ theo Unicode; kết quả có thể được kiểm tra bằng `Normalizer.normalize(s, Normalizer.Form.NFKC)`:

| Trước chuẩn hóa | NFKC | Điều có thể mất |
| --- | --- | --- |
| `①` (U+2460) | `1` (U+0031) | Dấu khoanh thể hiện mục đánh số, nhãn hoặc ký hiệu chuyên dụng |
| `²` (U+00B2) | `2` (U+0032) | Ý nghĩa **số mũ** trong biểu thức toán học/đơn vị |
| `ﬁ` (U+FB01) | `fi` (U+0066 U+0069) | Đặc điểm ligature/typography |
| `Ａ` (U+FF21) | `A` (U+0041) | Khác biệt fullwidth/halfwidth trong bố cục Đông Á |
| `Ⅳ` (U+2163) | `IV` (U+0049 U+0056) | Khác biệt giữa **ký tự số La Mã** và hai ký tự Latin |
| `½` (U+00BD) | `1⁄2` (U+0031 U+2044 U+0032) | Hình thức **vulgar fraction**; kết quả chứa fraction slash, không phải ASCII `/` |
| ` ` (U+00A0, NO-BREAK SPACE) | ` ` (U+0020) | Thuộc tính **không cho ngắt dòng** |
| `µ` (U+00B5, MICRO SIGN) | `μ` (U+03BC, GREEK SMALL LETTER MU) | Phân biệt ký hiệu đơn vị với chữ cái Hy Lạp |
| `𝑥` (U+1D465, MATHEMATICAL ITALIC SMALL X) | `x` (U+0078) | Ý nghĩa kiểu chữ toán học có thể gắn với ký hiệu |

*Dòng NO-BREAK SPACE khó nhìn bằng mắt vì cả hai ký tự đều là khoảng trắng. So sánh theo code point mới thấy khác biệt: `U+00A0` không giống `U+0020`.*

**Cảnh báo về `½`:** NFKC không biến `½` thành chữ `"1/2"` với ký tự slash ASCII `U+002F`; nó dùng `FRACTION SLASH U+2044`. Nếu dữ liệu chứa phân số, không tự dùng phép so sánh chuỗi sau normalization thay cho parser số học.

### Cùng kết quả NFKC, khác ý nghĩa trước đó

Ví dụ hai chuỗi:

~~~text
"room①"  = r o o m + U+2460 (CIRCLED DIGIT ONE)
"room1"  = r o o m + U+0031 (DIGIT ONE)
~~~

Sau NFKC, **cả hai cùng trở thành `"room1"`**. Đó là một **collision do normalization**: hai giá trị nguồn khác nhau nay có cùng key.

Với mục lục có các biểu tượng thứ tự, `①` có thể là dữ liệu cần giữ nguyên. Với hệ thống mã sản phẩm mà người dùng được phép gõ fullwidth digits, việc gộp một số biến thể có thể hữu ích. Không quyết định bằng việc “trông giống nhau”; phải dựa vào **hợp đồng dữ liệu của lĩnh vực**.

### Mất phân biệt định dạng có thể ảnh hưởng nghĩa

- `x²` trong toán học có thể biểu thị bình phương của `x`; NFKC đưa ký tự số mũ xuống dạng chữ số thường, nên một phép phân tích text sơ sài có thể nhầm `x²` với `x2`. Nếu là tài liệu toán, giữ nguyên ký hiệu hoặc dùng mô hình toán có cấu trúc.
- `Ⅳ` có thể biểu thị số La Mã thứ tư; `IV` có thể là hai chữ viết tắt. Hai chuỗi trở thành cùng một chuỗi sau NFKC.
- `①` có thể đánh dấu mục số một của danh sách; `1` không chứa thông tin dấu khoanh.
- `U+00A0` làm văn bản không ngắt dòng tại vị trí đó; chuyển thành space thông thường có thể làm thay đổi layout.
- Ký tự toán học trong bảng chữ in đậm/nghiêng (`𝑥`, `𝐴`, ...) đôi khi chỉ phục vụ typography, nhưng cũng có thể biểu thị các biến khác nhau trong một công thức. Compatibility normalization không thể tự suy ra mục đích của tác giả.
- Với đơn vị đo, ký hiệu có thể là một phần của chuẩn biểu diễn; đừng quy mọi ký tự Unicode về “ASCII gần giống” trước khi xác thực đơn vị và số lượng.

Điều quan trọng là **NFKC/NFKD không phải những phép biến đổi ngữ nghĩa có khả năng hiểu ngữ cảnh**. Chúng tuân theo bảng ánh xạ Unicode được tiêu chuẩn hóa, không biết chuỗi đang nằm trong phương trình, địa chỉ, chú thích ảnh hay mã đăng nhập.

## 4. Vì sao đây là phép mất thông tin và không đảo ngược được?

Một ánh xạ NFKC có thể đưa **nhiều nguồn khác nhau về một kết quả**:

~~~text
NFKC("①")  → "1"
NFKC("1")  → "1"

NFKC("ﬁ")  → "fi"
NFKC("fi") → "fi"

NFKC("²")  → "2"
NFKC("2")  → "2"
~~~

Không có hàm chung `inverseNFKC("1")` nào biết trước đó người dùng đã nhập `①` hay `1`. Vì mất thông tin ngay ở bước gộp, lưu **duy nhất giá trị NFKC** sẽ khiến ứng dụng không phục hồi được bản gốc từ normalized value.

Đây là lý do một kiến trúc an toàn thường tách:

- **`originalText`**: bản gốc cần lưu để hiển thị, dẫn nguồn, ký số hoặc audit theo yêu cầu.
- **`displayText`**: có thể dùng NFC hoặc biểu diễn UI theo policy, nhưng không tự coi đó là original.
- **`matchKey`**: dạng đã biến đổi (ví dụ NFKC) **chỉ dùng để tìm kiếm/đối chiếu trong domain cụ thể**.
- **`normalizationPolicyVersion`**: thông tin định nghĩa quy tắc tạo key khi hệ thống cần duy trì qua các lần thay đổi Unicode/runtime.

NFKC có tính **idempotent** đối với một phiên bản thuật toán/bảng dữ liệu cố định: chuẩn hóa chuỗi đã ở NFKC lần nữa không tiếp tục thay đổi nó. Điều đó **không** đồng nghĩa với khả năng đảo ngược, và cũng không có nghĩa bạn nên chạy thêm những phép biến đổi khác một cách tùy tiện.

## 5. Java 17+: API hiện hành và những giới hạn cần biết

`java.text.Normalizer` đã có từ Java 6, vẫn được hỗ trợ trong Java SE 25 và hoạt động trên Java 17+. Hai method thường gặp:

~~~java
String normalized = Normalizer.normalize(input, Normalizer.Form.NFKC);
boolean already = Normalizer.isNormalized(input, Normalizer.Form.NFKC);
~~~

Đây là **đoạn ghép vào method**, cần import `java.text.Normalizer` và kiểm soát `input` không null. `isNormalized` kiểm tra chuỗi đã ở form được chỉ định hay chưa, không “sửa” dữ liệu. Dùng `isNormalized` khi chỉ cần xác thực input đã đúng form trước khi chấp nhận, còn `normalize` khi policy cho phép biến đổi.

### NFKC KHÔNG làm các việc sau

1. **Không tự lower-case/case-fold.** `"A"` và `"a"` vẫn là hai chuỗi khác nhau sau NFKC.
2. **Không xóa dấu tiếng Việt.** Đừng xem NFKC như phép “bỏ accent”.
3. **Không đổi mọi ký tự nhìn giống nhau.** Chữ Latin `a` (`U+0061`) và Cyrillic `а` (`U+0430`) gần giống về hình dạng trong nhiều font, nhưng NFKC **không gộp chúng**.
4. **Không kiểm chứng tính hợp lệ của username, email, domain hay password.** Các miền này có grammar, normalization profile, validation và security policy riêng.
5. **Không biến text thành nguồn dữ liệu an toàn cho HTML/SQL/shell.** Escape, parametrized queries và các biện pháp xử lý đầu vào vẫn bắt buộc.
6. **Không hiểu được phép toán.** `½` được chuẩn hóa thành ba code points nhưng đó chưa phải kiểu số `0.5`.
7. **Không có tác dụng dịch ngôn ngữ.** Chữ và ký hiệu trong các hệ viết khác nhau không được tự “dịch” qua nhau.

Nếu cần **case-insensitive matching**, phải dùng thêm một quy tắc case mapping/case folding phù hợp với giao thức, ngôn ngữ và dữ liệu. `String.toLowerCase(Locale.ROOT)` có thể hữu ích trong một số ứng dụng, nhưng **không hoàn toàn tương đương với full Unicode case folding**. Tương tự, dạng `NFKC_Casefold` được nhắc đến trong một số tiêu chuẩn định danh không phải enum thứ năm của `java.text.Normalizer.Form`; bốn enum chuẩn vẫn là `NFC`, `NFD`, `NFKC`, `NFKD`. Không tự mô phỏng một profile bảo mật phức tạp chỉ bằng `normalize(..., NFKC).toLowerCase(...)` rồi khẳng định đã đạt chuẩn của profile ấy.

### Java `String.length()` khác số code point

NFKC có thể làm thay đổi số code point và số UTF-16 code unit trong chuỗi. Ví dụ `ﬁ` là **một code point** trước normalization nhưng biến thành **hai code points** `f` + `i`; một ký tự toán học ngoài BMP như `𝑥` cần **hai UTF-16 code units** trong Java `String` nhưng NFKC biến nó thành `x` (một code unit).

- `String.length()` đếm **UTF-16 code units**, không đếm Unicode code points hay grapheme clusters.
- `String.codePointCount(...)` / `String.codePoints()` hữu ích khi muốn xét code point.
- Số grapheme người dùng thấy là một khái niệm khác; một grapheme có thể gồm nhiều code points.
- Khi có giới hạn độ dài input hoặc username, cần quyết định rõ giới hạn được đo trên **dữ liệu gốc, dữ liệu sau normalization, bytes UTF-8, code points** hay grapheme clusters; nhiều hệ thống cần giới hạn **cả trước và sau khi biến đổi** để phòng mở rộng kích thước.

## 6. Ví dụ Java 17+ chạy được và stdout được kiểm thử

Chương trình sau sử dụng `Normalizer.Form.NFC` và `NFKC` để in **code points** thay vì dựa vào font hiển thị ký tự. Cách đó làm sự khác biệt giữa các chuỗi rõ ràng, kiểm thử dễ hơn và tránh nhầm lẫn do terminal không hỗ trợ glyph.

Tạo một file **`CompatibilityNormalizationDemo.java`** với nội dung đầy đủ:

~~~java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public final class CompatibilityNormalizationDemo {
    private static String codePoints(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    private static void show(String label, String original) {
        String nfc = Normalizer.normalize(original, Form.NFC);
        String nfkc = Normalizer.normalize(original, Form.NFKC);
        System.out.printf("%s | raw=%s | NFC=%s | NFKC=%s%n",
                label, codePoints(original), codePoints(nfc), codePoints(nfkc));
    }

    public static void main(String[] args) {
        show("combining-e", "e\u0301");
        show("circled-one", "\u2460");
        show("superscript-two", "\u00B2");
        show("ligature-fi", "\uFB01");
        show("fullwidth-A", "\uFF21");
        show("roman-IV", "\u2163");
        show("one-half", "\u00BD");
        show("nonbreaking-space", "\u00A0");
        show("micro-sign", "\u00B5");
        show("math-italic-x", new String(Character.toChars(0x1D465)));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("NFC unifies accent forms: "
                + Normalizer.normalize(composed, Form.NFC)
                        .equals(Normalizer.normalize(decomposed, Form.NFC)));
        System.out.println("NFC keeps circled/ASCII distinct: "
                + !Normalizer.normalize("\u2460", Form.NFC)
                        .equals(Normalizer.normalize("1", Form.NFC)));
        System.out.println("NFKC collides circled/ASCII: "
                + Normalizer.normalize("\u2460", Form.NFKC)
                        .equals(Normalizer.normalize("1", Form.NFKC)));
        System.out.println("NFKC keeps case distinct: "
                + !Normalizer.normalize("A", Form.NFKC)
                        .equals(Normalizer.normalize("a", Form.NFKC)));
        System.out.println("NFKC keeps Latin/Cyrillic a distinct: "
                + !Normalizer.normalize("a", Form.NFKC)
                        .equals(Normalizer.normalize("\u0430", Form.NFKC)));
        System.out.println("Circled-one already NFKC: "
                + Normalizer.isNormalized("\u2460", Form.NFKC));

        String normalized = Normalizer.normalize("\u2460\uFF21", Form.NFKC);
        System.out.println("NFKC idempotent: "
                + normalized.equals(Normalizer.normalize(normalized, Form.NFKC)));
    }
}
~~~

Lệnh biên dịch/chạy với **JDK 17 trở lên** trong thư mục có file:

~~~bash
javac --release 17 CompatibilityNormalizationDemo.java
java CompatibilityNormalizationDemo
~~~

**Stdout chính xác** của chương trình (đã biên dịch và chạy bằng JDK 24 với `--release 17`):

~~~text
combining-e | raw=U+0065 U+0301 | NFC=U+00E9 | NFKC=U+00E9
circled-one | raw=U+2460 | NFC=U+2460 | NFKC=U+0031
superscript-two | raw=U+00B2 | NFC=U+00B2 | NFKC=U+0032
ligature-fi | raw=U+FB01 | NFC=U+FB01 | NFKC=U+0066 U+0069
fullwidth-A | raw=U+FF21 | NFC=U+FF21 | NFKC=U+0041
roman-IV | raw=U+2163 | NFC=U+2163 | NFKC=U+0049 U+0056
one-half | raw=U+00BD | NFC=U+00BD | NFKC=U+0031 U+2044 U+0032
nonbreaking-space | raw=U+00A0 | NFC=U+00A0 | NFKC=U+0020
micro-sign | raw=U+00B5 | NFC=U+00B5 | NFKC=U+03BC
math-italic-x | raw=U+1D465 | NFC=U+1D465 | NFKC=U+0078
NFC unifies accent forms: true
NFC keeps circled/ASCII distinct: true
NFKC collides circled/ASCII: true
NFKC keeps case distinct: true
NFKC keeps Latin/Cyrillic a distinct: true
Circled-one already NFKC: false
NFKC idempotent: true
~~~

### Giải thích kết quả

- `combining-e`: NFC xử lý hai biểu diễn canonically equivalent của `é`; cả NFC và NFKC cho dạng ghép `U+00E9`.
- `circled-one` và `superscript-two`: NFC giữ nguyên những khác biệt compatibility, NFKC biến thành chữ số ASCII. Điều này **có thể phá ý nghĩa** khi ký tự khoanh hay số mũ không chỉ dùng để trang trí.
- `ligature-fi` và `fullwidth-A`: NFKC gộp lựa chọn typography/width vào ký tự thông thường; có thể hữu ích trong search key, nhưng không nên xóa bản gốc của tài liệu có ý nghĩa trình bày.
- `roman-IV`: NFKC đổi **một** ký tự số La Mã thành **hai** chữ Latin, nên không phù hợp nếu hệ thống cần giữ phân biệt ký hiệu số với chữ viết tắt.
- `one-half`: fraction slash là `U+2044`, không phải slash ASCII `U+002F`. Kiểm thử theo code points tránh nhầm lẫn hình dạng.
- `nonbreaking-space`: mất nonbreaking property làm thay đổi khả năng ngắt dòng.
- `micro-sign`: micro sign được gộp vào Greek mu; đôi khi có lợi cho tìm kiếm đơn vị, nhưng parser cần hiểu đơn vị theo đúng chính sách.
- `math-italic-x`: U+1D465 nằm ngoài BMP; `Character.toChars` giúp tạo đúng surrogate pair. NFKC cho chữ `x` thông thường.
- `NFC unifies accent forms: true`: canonical equivalence được đưa về chung một chuỗi; `NFC keeps circled/ASCII distinct: true` cho thấy canonical không xóa phân biệt compatibility.
- `NFKC keeps case distinct: true`: NFKC không biến `A` thành `a`. `Latin/Cyrillic a distinct: true`: NFKC không giải bài toán confusable/homoglyph.
- `Normalizer.isNormalized("①", NFKC) == false`: original chưa ở dạng NFKC. `NFKC idempotent: true`: áp dụng lần hai cho output đã chuẩn hóa không thay đổi kết quả trong cùng môi trường.

**Vì sao in code points?** Một terminal có thể hiển thị `①` và `1` hoặc `Ａ` và `A` theo cách rất gần nhau; font không nói lên code point. `String.codePoints()` và `String.format("U+%04X", ...)` giúp quan sát đúng dữ liệu. Với Unicode ngoài BMP, `String.charAt(...)` trả từng UTF-16 code unit, dễ làm bạn tưởng một ký tự là hai “ký tự”; vì vậy code dùng `codePoints()`.

## 7. Phân biệt normalize để lưu trữ, hiển thị và tìm kiếm

### 7.1. Văn bản giàu ý nghĩa (nội dung gốc, công thức, tài liệu)

Với tài liệu, ghi chú học tập, ký hiệu toán, đơn vị và bản chép văn bản, hãy ưu tiên **giữ nguyên nguồn** khi cần tái hiện chính xác. NFC có thể là một phép chuẩn hóa lưu trữ phù hợp nếu hợp đồng yêu cầu canonical text, nhưng vẫn cần biết rằng chuỗi code point gốc có thể thay đổi. NFKC/NFKD sẽ đánh mất các compatibility distinctions.

Ví dụ lưu một bài toán chứa `x²`: thay thành `x2` rồi chỉ lưu output sẽ làm văn bản không còn mang cùng cách viết ban đầu. Nếu cần tìm kiếm `x²` bằng truy vấn `x2`, hãy xây một **search key phụ** và vẫn hiển thị chính ký hiệu gốc.

### 7.2. Tìm kiếm rộng, tra cứu hoặc autocomplete

Trong domain có chủ đích, có thể tính:

~~~java
String displayName = original;  // Giữ theo chính sách hiển thị.
String searchKey = Normalizer.normalize(original, Normalizer.Form.NFKC);
// Lưu searchKey riêng; search query cũng qua cùng policy.
~~~

Đây là **mã minh họa trong method**. Người tìm có thể gõ `Ａ` hoặc `A`, `①` hoặc `1` và nhận cùng nhóm kết quả. Đây là mục tiêu hợp lệ của **loose matching** nếu domain chấp nhận gộp khác biệt.

Nhưng:
- Không coi search match là bằng chứng hai bản ghi **thực sự giống nhau về nghĩa**.
- Khi nhiều nguồn tạo cùng key, search nên trả nhiều kết quả hoặc ranking rõ ràng thay vì chọn ngầm một bản.
- Tokenization, locale/case handling, accent handling, loại dấu câu và thông tin ngôn ngữ **không tự có trong NFKC**.
- Với quy tắc case-insensitive, định nghĩa một pipeline riêng và test theo ngôn ngữ, không giả định NFKC đủ.
- Bản gốc và key có thể có độ dài khác; giới hạn/kiểm tra riêng từng trường.

### 7.3. Username, slug, mã sản phẩm và các định danh unique

Một hệ thống có thể chọn NFKC cho **identifier key** để tránh đăng ký hai tên chỉ khác các ký tự kiểu fullwidth/circled. Nhưng đó là **quy tắc nhận dạng**, không phải phép định nghĩa ý nghĩa văn bản phổ quát. Cần chọn ngay từ đầu:

- Những code points/script nào được chấp nhận?
- Sau NFKC, ký tự nào có thể xuất hiện và có hợp lệ trong định danh đó không?
- Có xử lý case, accent, khoảng trắng, separators hoặc punctuation không? Theo tiêu chuẩn/profile nào?
- Việc hai original khác nhau tạo cùng normalized key được **từ chối, gộp, hay coi là alias**?
- Quy tắc uniqueness được thực thi **atomically trong database** hay chỉ kiểm tra ở UI?
- Có cần lưu original cho display, audit, undo và migration không?

Ví dụ input `"user①"` và `"user1"` cho cùng NFKC key. Nếu policy nói **unique by NFKC**, lần đăng ký sau phải bị coi là xung đột; không được ghi đè tài khoản hiện có. Nếu policy cho phép tên hiển thị khác nhau, dùng **stable internal ID** và tách display name khỏi login handle.

Định danh bảo mật thường đòi hỏi các profile chuẩn hóa/ngữ pháp chuyên dụng. Dạng `NFKC_Casefold` hoặc các profile Unicode/PRECIS có thể đề cập các bước bổ sung; không tự áp dụng `Normalizer.Form.NFKC` rồi tuyên bố hệ thống tuân thủ tất cả profile đó.

## 8. Bảo mật: NFKC không phải bộ lọc chống spoofing

Đừng nhầm **normalization equivalence** với **visual confusability**.

~~~text
LATIN SMALL LETTER A       "a" = U+0061
CYRILLIC SMALL LETTER A    "а" = U+0430

NFKC("a")  = "a"
NFKC("а")  = "а"

Hai chuỗi vẫn khác nhau, dù một số font hiển thị chúng rất giống.
~~~

Unicode Technical Standard #39 (UTS #39) mô tả các cơ chế **confusable detection** và mixed-script analysis. Nó là một lớp kiểm tra khác với UAX #15 normalization. Không dùng `String.equals` trên NFKC strings để kết luận đã chặn mọi kiểu giả mạo bằng ký tự trông giống nhau.

Nếu cần bảo vệ login handle, tên tổ chức, domain hay URL, hãy dùng đúng chuẩn/profile áp dụng cho miền đó và thiết lập chính sách chấp nhận script, confusables, độ dài, uniqueness. Đối với domain names, các quy tắc IDNA/UTS #46 là vấn đề riêng; đừng tự NFKC toàn bộ URL hoặc email address rồi nghĩ đã xử lý đúng các quy định chuẩn. Một URL có phần path, query hoặc fragment nơi byte encoding, percent-encoding và ý nghĩa ứng dụng có thể đòi hỏi giữ nguyên.

**Không được đồng nhất “normalized” với “safe”:**

- NFKC không escape HTML và không thay thế SQL prepared statements.
- NFKC không ngăn injection bằng mã Unicode hoặc control characters.
- NFKC không cho phép so sánh bảo mật bằng chuỗi mà không xem xét timing/secret handling nếu giao thức đòi hỏi.
- NFKC không là parser dữ liệu có cấu trúc (số, toán, đơn vị, ngôn ngữ đánh dấu).
- NFKC không thay thế kiểm tra ký tự được phép, mixed-script policy hoặc confusable detection.

### Password và chữ ký số

Không **âm thầm** chạy NFKC trên password mà người dùng đã thiết lập, bởi `"①"` và `"1"` sẽ bị coi như cùng bí mật sau biến đổi. Nếu một giao thức xác thực cụ thể **yêu cầu** normalization profile, phải làm theo chính xác profile đó **cả lúc tạo lẫn lúc xác minh**, và có kế hoạch xử lý tài khoản cũ; không tự phát minh “password chuẩn hóa” tùy tiện.

Tương tự, một chữ ký/hash tính trên **bytes gốc** không còn khớp nếu bạn chuẩn hóa chuỗi trước hoặc sau ký theo quy tắc không nhất quán. Các hệ thống ký số cần một canonicalization protocol rõ ràng ở cấp dữ liệu/byte và áp dụng cùng phía gửi/nhận. Không dùng NFKC làm “bước chung” trước mọi phép ký số.

## 9. Thiết kế pipeline không làm mất thông tin

Một mô hình thường hữu ích cho searchable user-generated text:

~~~text
Input UTF-8 bytes
    │ decode theo encoding xác định, reject malformed input theo policy
    ▼
originalText (bản gốc, giữ nếu hợp đồng cần)
    │ kiểm tra kích thước/giới hạn ký tự và tính hợp lệ của domain
    ├────────────────────────────────────────────────────┐
    │                                                    │
    ▼                                                    ▼
displayText (giữ nguyên hoặc NFC theo policy)      matchKey (NFKC chỉ khi policy cho phép)
    │                                                    │
    │                                                    ├─ kiểm tra sau khi biến đổi
    │                                                    ├─ phát hiện collision
    │                                                    └─ index/unique constraint
    ▼                                                    ▼
Hiển thị nguyên ý nghĩa/lựa chọn kiểu chữ          Tra cứu theo cùng phiên bản policy
~~~

Trong database, các trường **có ý nghĩa khác nhau** nên được đặt tên khác nhau. `originalText` không nhất thiết phải tồn tại trong mọi dự án, nhưng nếu yêu cầu có khả năng tái hiện nguyên văn thì **bắt buộc** phải giữ trước khi chuẩn hóa mất thông tin.

### Mã minh họa tạo khóa tìm kiếm, không tự ý sửa bản gốc

~~~java
import java.text.Normalizer;

record StoredText(String original, String lookupKey) {}

static StoredText prepare(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Thiếu input");
    }
    if (input.length() > 10_000) {
        throw new IllegalArgumentException("Input quá lớn");
    }

    String key = Normalizer.normalize(input, Normalizer.Form.NFKC);
    if (key.length() > 10_000) {
        throw new IllegalArgumentException("Output sau normalize quá lớn");
    }
    return new StoredText(input, key);
}
~~~

Đây là **đoạn ghép vào class/file thích hợp**, dùng record của Java 17 và không phải chương trình độc lập. Con số `10_000` chỉ minh họa kiểm soát kích thước; ứng dụng thật cần giới hạn theo UTF-8 bytes, code points và nghiệp vụ tùy trường dữ liệu. Phải dùng **cùng normalize policy** với cả giá trị đăng ký và truy vấn; nếu so sánh key đã chuẩn hóa với query nguyên bản, kết quả dễ không nhất quán.

Với trường unique như account handle, thực thi uniqueness bằng **constraint/transaction trong database**, không chỉ lệnh `SELECT` kiểm tra tồn tại rồi `INSERT`; hai request đồng thời có thể vượt qua kiểm tra phía ứng dụng. Khi phát hiện hai original có cùng key, nên yêu cầu người dùng chọn lại hoặc dùng chính sách alias đã được công bố, **không overwrite** record trước.

## 10. Thay đổi chính sách và migration dữ liệu cũ

Khi một hệ thống trước đây lưu hoặc so sánh Unicode theo cách khác, việc thêm NFKC không phải chỉ là đổi một dòng code:

1. **Xác định dữ liệu nào có semantics:** nội dung học thuật, bài toán, mã thiết bị, username, tài liệu có ký số, password, display names, query strings.
2. **Viết và đóng phiên bản policy:** dùng NFC hay NFKC? Có thêm case folding, whitespace mapping, script checks, length checks hay không? Đừng để các microservices tự chọn từng loại form.
3. **Tính thử key mới trên bản sao read-only:** đo số **collisions** giữa các bản ghi đang tồn tại, ví dụ `①` và `1`. Không tự động gộp tài khoản hoặc ghi đè hồ sơ.
4. **Đánh giá mất mát thông tin:** xem vị trí số mũ, số khoanh, nonbreaking space, biến thể kiểu chữ có còn cần để hiển thị/khôi phục không.
5. **Chốt quy tắc giải quyết collision:** giữ ID gốc, thông báo người dùng, tạo alias có kiểm soát hoặc từ chối thay đổi nếu không thể phân biệt một cách công bằng.
6. **Triển khai đọc/ghi nhất quán:** backfill match key, build index mới, chuyển dần query path/unique constraint, thiết lập rollback. Tránh trạng thái cùng hệ thống có nơi so original, nơi so NFKC.
7. **Kiểm thử cross-platform và nâng cấp JDK/Unicode:** bản Unicode data của runtime/library và sự thay đổi profile trong thời gian dài có thể ảnh hưởng một số kết quả edge case. Xác định test vectors/compatibility policy khi nâng cấp; không suy luận rằng mọi bản JDK dùng đúng một bản Unicode mới nhất.
8. **Giữ nguyên dữ liệu có chữ ký và audit:** nếu phải thay đổi byte representation, cập nhật protocol/canonicalization và thông báo nơi tiêu thụ, không sửa âm thầm dữ liệu đã ký.

Với dữ liệu mới, hạn chế dùng NFKC để **viết lại mọi original text ngay tại điểm nhập**. Thay vào đó, xác định các **derived fields** có thể tính lại khi policy hoặc search engine được nâng cấp.

### Việc normalized key khác đi không đồng nghĩa bản ghi khác đi

Ứng dụng có thể sử dụng `normalizedKey` để matching nhưng vẫn định danh thực thể bằng `UUID` hoặc primary key ổn định. Khi hai raw values gộp vào cùng search key, ứng dụng vẫn có hai record. Search phải **xử lý nhiều kết quả**; uniqueness chỉ nên áp dụng khi domain đã công bố rằng chúng thật sự thuộc cùng một không gian định danh duy nhất.

## 11. Các phép biến đổi dễ bị nhầm với compatibility normalization

| Phép biến đổi | Có tự được NFKC thực hiện? | Ghi chú |
| --- | --- | --- |
| Gộp dạng canonical `é` và `e + ◌́` | Có | NFC cũng làm được |
| Gộp ligature `ﬁ` với `fi` | Có | Chỉ compatibility forms; NFC không làm |
| Gộp fullwidth `Ａ` với `A` | Có | Có thể cần thiết cho certain search keys |
| Gộp số khoanh `①` với `1` | Có | Có thể gây collision có ý nghĩa |
| Biến `²` thành `2` | Có | Làm mất chức năng số mũ |
| Biến `½` thành `1/2` với slash ASCII | **Không chính xác** | NFKC dùng `U+2044 FRACTION SLASH` |
| Biến mọi chữ hoa thành chữ thường | Không | Cần case mapping/case folding riêng |
| Loại bỏ mọi dấu tiếng Việt | Không | Không phải chức năng của NFKC/NFKD |
| Đồng nhất chữ Latin `a` và Cyrillic `а` | Không | Đây là confusable detection vấn đề khác |
| Kiểm chứng URL, email hoặc IDNA | Không | Cần protocol/domain-specific logic |
| Escape HTML/SQL/shell hay kiểm tra injection | Không | Là lớp an toàn dữ liệu khác |
| Khôi phục chính xác input từ NFKC output | Không | NFKC many-to-one và mất thông tin |

**Lưu ý thêm:** Cùng là Unicode normalization nhưng `NFD` và `NFKD` đưa chuỗi về dạng decomposed. Nếu bạn thấy sau `NFKD` có combining marks rồi tự xóa những marks ấy, việc xóa đó là **logic thêm của ứng dụng**, không phải tính chất của NFKD. Nó có thể làm hai từ khác nghĩa trong tiếng Việt trở thành cùng một text. Không gọi cả pipeline đó chỉ bằng tên “NFKD” rồi đánh giá như API chuẩn.

## 12. Kiểm thử cần có khi triển khai NFKC/NFKD

Bài test tốt phải đánh giá **cả đúng chức năng matching lẫn nguy cơ mất thông tin**.

### Bộ test cốt lõi

- Canonical equivalence: `"\u00E9"` và `"e\u0301"` cho cùng NFC; NFD cũng cho cùng decomposed sequence.
- Compatibility collision: `"①"` và `"1"` cho cùng NFKC, nhưng **khác NFC**.
- Superscript: `"²"` → `"2"` (nếu chọn NFKC); kiểm tra hiển thị original không bị ghi đè.
- Fraction: `"½"` → code points `U+0031 U+2044 U+0032`; không tự đổi thành ASCII `1/2`.
- Fullwidth và ligature: `"Ａ"` → `"A"`; `"ﬁ"` → `"fi"`.
- Nonbreaking space: `U+00A0` → `U+0020`; thử layout/word boundaries nếu ứng dụng yêu cầu giữ không ngắt dòng.
- Confusable: Latin `a` và Cyrillic `а` vẫn khác sau NFKC.
- Case: `"A"` và `"a"` vẫn khác sau NFKC.
- Outside BMP: `U+1D465` → `U+0078`; dùng `codePoints()` thay vì giả định một char Java = một code point.
- Idempotence: `normalize(normalize(s, NFKC), NFKC)` bằng `normalize(s, NFKC)` trong cùng runtime/version.
- Invalid/unusual input: null, chuỗi rất dài, combining marks, text có nhiều script và input có control characters — theo policy ứng dụng, không tự cho rằng normalize thay validation.
- Database uniqueness: hai request tạo same normalized key phải được phát hiện atomically; không được overwrite một record.
- Regression qua upgrade: test vectors đi kèm policy trước và sau nâng cấp JDK/Unicode data để phát hiện thay đổi ngoài dự kiến.

### Test assertion minh họa

~~~java
import java.text.Normalizer;

String circled = Normalizer.normalize("\u2460", Normalizer.Form.NFKC);
String plain = Normalizer.normalize("1", Normalizer.Form.NFKC);

if (!circled.equals(plain)) {
    throw new AssertionError("NFKC phải gộp ① và 1");
}

String latinA = Normalizer.normalize("a", Normalizer.Form.NFKC);
String cyrillicA = Normalizer.normalize("\u0430", Normalizer.Form.NFKC);

if (latinA.equals(cyrillicA)) {
    throw new AssertionError("NFKC không được coi là confusable folding");
}
~~~

Đây là **mã minh họa trong một method**, không phải file chạy riêng. Chương trình hoàn chỉnh ở phần 6 đã in kết quả tương ứng, nhưng trong unit test thực nên dùng assertion để báo fail ngay khi kết quả thay đổi.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Vì sao gây vấn đề? | Hướng đúng |
| --- | --- | --- |
| Áp NFKC lên mọi text trước khi lưu | Mất khác biệt số mũ, số khoanh, kiểu chữ, không ngắt dòng | Giữ original và chỉ tạo match key ở domain được phép |
| Nghĩ NFKC chỉ sửa “kí tự đẹp mắt” | Một số compatibility characters có ý nghĩa toán học, kỹ thuật hoặc ngôn ngữ | Đánh giá semantics của dữ liệu trước khi normalize |
| Nghĩ NFKC có thể đảo ngược | Nhiều nguồn ánh xạ đến cùng output | Lưu original nếu phải khôi phục |
| Dùng normalized key làm ID duy nhất mà không xử lý collision | Hai người/tài liệu có thể bị gộp nhầm | Định danh ổn định, unique constraint và collision policy |
| Xem `Normalizer.normalize` như bộ lọc bảo mật đầy đủ | Không xử lý homoglyph, injection, URL/IDNA hoặc grammar | Dùng thêm validation và profile chuẩn theo domain |
| Dùng NFKC thay case folding | `A` và `a` vẫn khác | Chính sách case folding rõ ràng và test riêng |
| Sau NFKD xóa tất cả combining marks để “chuẩn hóa” | Có thể làm mất dấu phân biệt nghĩa tiếng Việt | Chỉ bỏ dấu cho search opt-in, giữ text gốc |
| Cho rằng `String.length()` là số ký tự hiển thị | UTF-16, code points và grapheme clusters khác nhau | Dùng phép đo đúng và giới hạn trước/sau normalization |
| So sánh input raw với key đã normalized | Các truy vấn không nhất quán | Dùng cùng version policy cho cả record lẫn query |
| Không kiểm soát nâng cấp JDK/Unicode | Edge cases có thể khác nhau giữa Unicode data versions | Regression tests và policy/versioning |
| Normalize password sau khi đã có tài khoản cũ | Có thể thay đổi điều kiện xác thực, gây collision bí mật | Chỉ theo protocol rõ và có migration plan |
| Dùng `½` như thể normalize sẽ cho ASCII `1/2` | U+2044 FRACTION SLASH không phải U+002F | Dùng parser chuyên dụng hoặc so code points |

## 14. Câu hỏi tự kiểm tra

1. **NFC và NFKC khác gì ở `①`?** NFC giữ `①`; NFKC biến thành `1` vì đây là compatibility mapping.
2. **Vì sao gộp `²` thành `2` có thể sai?** Dấu số mũ có thể là một phần ý nghĩa toán học, không chỉ là trang trí.
3. **NFKC có xóa dấu tiếng Việt hay lower-case không?** Không; đó là các phép biến đổi khác, cần policy riêng.
4. **NFKC biến `½` thành ASCII `1/2` không?** Không. Chuỗi NFKC dùng FRACTION SLASH `U+2044`.
5. **Vì sao `"room①"` và `"room1"` có thể gây lỗi unique key?** Cả hai cho cùng NFKC key; phải có quy tắc collision chứ không ghi đè.
6. **Nếu cần hiển thị chính xác tài liệu gốc, có nên chỉ lưu NFKC không?** Không; phải lưu original hoặc nguồn có khả năng tái tạo nguyên văn.
7. **NFKC có phát hiện mọi chữ trông giống nhau giữa các script không?** Không; UTS #39 confusables là cơ chế khác.
8. **`Normalizer.isNormalized(s, NFKC)` trả `false` nghĩa là input nguy hiểm không?** Không. Chỉ nghĩa `s` không ở dạng NFKC; nguy hiểm/hợp lệ phụ thuộc domain.
9. **Tại sao kiểm tra kích thước sau normalize?** Mapping có thể mở rộng số code points/code units; cần giới hạn cả hai phía khi phù hợp.
10. **Có nên chuẩn hóa một chữ ký số đã tính từ bytes nguyên bản?** Không, trừ khi giao thức quy định canonicalization chính xác và hai bên tuân theo.
11. **Một search key giống nhau có đồng nghĩa hai bản ghi cùng ý nghĩa không?** Không. Matching là một quy tắc tra cứu, không phải phán quyết ngữ nghĩa.
12. **NFKD có tự biến chữ `ế` thành `e` trơn không?** Không; dạng decomposed vẫn giữ combining marks.

## 15. Tài liệu chính thức, còn áp dụng

- [Unicode Standard Annex #15 — Unicode Normalization Forms (bản hiện hành)](https://www.unicode.org/reports/tr15/): canonical vs compatibility equivalence, bảng ánh xạ, NFC/NFD/NFKC/NFKD, tính mất thông tin.
- [Unicode — FAQ: Normalization](https://www.unicode.org/faq/normalization.html): khi nào NFC phù hợp cho văn bản chung, khi nào NFKC dùng cho identifier/restricted matching.
- [Java SE 25 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized` và các giới hạn API.
- [Java SE 25 — Normalizer.Form](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.Form.html): bốn Unicode normalization forms.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/): confusables, mixed-script risks và các cơ chế kiểm tra bảo mật khác với normalization.
- [Unicode Standard Annex #31 — Unicode Identifiers and Syntax](https://www.unicode.org/reports/tr31/): các chính sách/giới hạn liên quan Unicode identifiers.
- [Java SE 25 — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `length`, `codePoints`, `codePointCount`, case mapping và text operations.

**Kết luận:** Compatibility normalization **rất hữu ích nếu được định nghĩa như một chính sách matching rõ ràng**, nhưng **không bảo toàn mọi ý nghĩa văn bản**. `NFKC/NFKD` có thể gộp những ký tự mà người viết dùng để biểu đạt thứ tự, số mũ, đơn vị, bố cục hoặc kiểu chữ toán học. Hãy lựa chọn normalization theo domain, giữ original khi cần, xử lý collisions và kiểm thử kết quả bằng code points — thay vì áp dụng NFKC đại trà rồi cho rằng mọi văn bản được “làm sạch” mà không mất mát.