# Khác biệt giữa chuẩn hóa Unicode với đổi hoa, thường trong Java

**Chuẩn hóa Unicode (Unicode normalization)** và **đổi chữ hoa/chữ thường (case conversion)** là hai phép biến đổi **khác mục đích, khác quy tắc và khác hệ quả**. Một phép giải quyết các cách biểu diễn Unicode tương đương ở mức ký tự; phép kia thay đổi dạng chữ theo quy tắc chữ hoa/chữ thường, có thể phụ thuộc ngôn ngữ. Không nên thay thế chúng cho nhau.

Ví dụ, `"é"` (ký tự `U+00E9`) và `"e\u0301"` (chữ `e` rồi dấu sắc kết hợp `U+0301`) trông giống nhau nhưng là hai chuỗi mã khác nhau. `Normalizer.normalize(..., NFC)` có thể đưa chúng về cùng dạng. Trong khi đó, `"TITLE".toLowerCase(Locale.ROOT)` biến thành `"title"`, nhưng **không tự đưa các dấu kết hợp về dạng NFC**, và việc chuẩn hóa NFC **không tự đổi chữ hoa thành chữ thường**.

Trong Java hiện hành, sử dụng `java.text.Normalizer` cho NFC/NFD/NFKC/NFKD, `String.toLowerCase(Locale)`/`toUpperCase(Locale)` cho biến đổi dạng chữ, và các API so sánh thích hợp cho ý định của ứng dụng. **Từ JDK 26**, `String.equalsFoldCase` còn hỗ trợ *full Unicode case folding* cho so sánh không phân biệt hoa/thường. Các API cơ bản đã có trong Java 17+, vẫn được sử dụng trên JDK 27.

Bài học tập trung vào sự khác nhau, kết quả thực tế trên Java 17+, thứ tự áp dụng khi cần cả hai, trường hợp tiếng Việt/Turkish/ß, và rủi ro khi dùng các phép biến đổi để tạo khóa định danh hoặc tìm kiếm.

## 1. Mục tiêu

Sau bài này, bạn sẽ:

1. Giải thích được vì sao hai chuỗi hiển thị giống nhau vẫn có thể `equals()==false`.
2. Phân biệt **canonical equivalence** và **compatibility equivalence**; chọn đúng NFC, NFD, NFKC hoặc NFKD.
3. Phân biệt chuẩn hóa với `toLowerCase`, `toUpperCase` và **case folding**.
4. Chọn đúng `Locale.ROOT` hay locale của người dùng khi đổi hoa/thường.
5. Biết giới hạn của `equalsIgnoreCase` trên Java 17+ và API `equalsFoldCase` từ JDK 26.
6. Thiết kế so sánh/tìm kiếm có chính sách rõ ràng, tránh mất dấu tiếng Việt, xung đột khóa và lỗi bảo mật.
7. Tự biên dịch/chạy chương trình Java 17+ kiểm tra trực tiếp các trường hợp dễ nhầm.

## 2. Mô hình tư duy: mã Unicode, cách biểu diễn, kiểu chữ

Một `String` Java chứa dãy **UTF-16 code units**. Unicode còn có khái niệm **code point**, **combining mark** và **grapheme cluster** (đơn vị mà người dùng cảm nhận như một ký tự). Những mức này không phải lúc nào cũng là một:

- `"é"` dựng sẵn: một code point `U+00E9`.
- `"e\u0301"`: hai code points `U+0065 U+0301`.
- Cả hai có thể hiển thị giống `é` trong font/giao diện hỗ trợ.
- `String.equals` so **đúng dãy UTF-16 code units**, không so nét chữ nhìn thấy hay equivalence Unicode.
- `String.length()` đếm **UTF-16 code units**, không phải số “chữ” trong ngôn ngữ tự nhiên.
- Một code point ngoài Basic Multilingual Plane thường được biểu diễn bằng **surrogate pair** (hai `char`), còn một grapheme có thể gồm nhiều code points.

Ba thao tác cần tách biệt:

| Thao tác | Câu hỏi giải quyết | Ví dụ |
| --- | --- | --- |
| **Unicode normalization** | Hai dãy code points có biểu diễn cùng nội dung theo một **normalization form** không? | `"é"` so với `"e\u0301"` bằng NFC/NFD. |
| **Case conversion** | Dạng hoa/thường của chữ này theo quy tắc ngôn ngữ là gì? | `"Java"` → `"java"`, `"straße"` → `"STRASSE"` khi uppercase. |
| **Caseless comparison / case folding** | Hai chuỗi được coi là giống nhau nếu bỏ qua khác biệt về case theo quy tắc nào? | `"Fuß"` và `"FUSS"` có full case-fold equivalence từ JDK 26. |

Một chuỗi có thể đã ở NFC mà vẫn chứa chữ hoa; một chuỗi đã lowercase vẫn có thể chưa ở NFC. Việc “nhìn giống nhau” cũng không đảm bảo là Unicode canonical equivalence: các ký tự giống hình nhưng thuộc script khác nhau có thể vẫn khác về mã và ý nghĩa.

## 3. Unicode normalization là gì?

Unicode chuẩn định nghĩa nhiều cách biểu diễn một số ký tự hoặc chuỗi có thể được quy về dạng chuẩn. `java.text.Normalizer` triển khai quy tắc **Unicode Standard Annex #15 (UAX #15)** bằng bốn giá trị của `Normalizer.Form`.

| Form | Tên | Đặc điểm | Tình huống hữu ích |
| --- | --- | --- | --- |
| **NFD** | Canonical Decomposition | Tách ký tự dựng sẵn thành các thành phần canonical; sắp xếp dấu kết hợp theo quy tắc. | Phân tích code points, xử lý combining marks có chủ đích. |
| **NFC** | Canonical Decomposition rồi Composition | Quy về dạng canonical **ghép khi có thể**; giữ khác biệt compatibility. | Biểu diễn ổn định cho dữ liệu văn bản thông thường, so sánh canonical. |
| **NFKD** | Compatibility Decomposition | Bao gồm phân rã compatibility, có thể biến ligature/kiểu chữ trang trí thành dạng khác. | Một số công cụ tìm kiếm/đối chiếu có policy chấp nhận mất phân biệt compatibility. |
| **NFKC** | Compatibility Decomposition rồi Composition | Quy về dạng ghép, đồng thời hợp nhất cả một số compatibility characters. | Chuẩn hóa đầu vào theo profile quy định rõ, ví dụ một số quy tắc tìm kiếm/định danh. |

**Canonical** không có nghĩa “xóa dấu”. Với `"é"` và `"e\u0301"`, NFC đưa về một dạng, NFD đưa về dạng phân tách. Cả hai vẫn **giữ dấu sắc**.

**Compatibility** có thể làm thay đổi sự phân biệt có ý nghĩa với ứng dụng. Ví dụ ký tự ligature `"ﬃ"` (`U+FB03`) có compatibility decomposition là chuỗi `"ffi"`; NFC thường **không** biến `ﬃ` thành `ffi`, nhưng NFKC thì có. Unicode normalization **không phải phép mã hóa có thể đảo ngược** từ bất kỳ dữ liệu gốc nào: nếu cần đúng từng code point ban đầu, giữ nguyên bản gốc.

### 3.1. Dùng `Normalizer` trong Java

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;

// Mảnh code tích hợp vào một method có biến String input:
String nfc  = Normalizer.normalize(input, Form.NFC);
String nfd  = Normalizer.normalize(input, Form.NFD);
String nfkc = Normalizer.normalize(input, Form.NFKC);
String nfkd = Normalizer.normalize(input, Form.NFKD);

boolean alreadyNfc = Normalizer.isNormalized(input, Form.NFC);
```

- `normalize(CharSequence, Form)` trả `String` sau biến đổi theo form.
- `isNormalized(CharSequence, Form)` kiểm tra dữ liệu đã ở đúng form hay chưa.
- `null` cho input hoặc form sẽ gây `NullPointerException`; validator API nên xác định policy cho input thiếu trước khi gọi.
- Phần lớn use case cần **chọn một form nhất quán** thay vì lần nào cũng chuyển tất cả các form.
- `Normalizer.normalize` không tự chuyển case, bỏ dấu, transliteration, làm sạch HTML hay kiểm tra Unicode spoofing.

### 3.2. Kiểm thử bằng mã Unicode để không phụ thuộc font

```java
// Hai dãy code points khác nhau cùng biểu diễn ký tự é.
String composed   = "\u00E9";   // U+00E9
String decomposed = "e\u0301";  // U+0065 U+0301

System.out.println(composed.equals(decomposed)); // false

String canonicalA = Normalizer.normalize(composed, Form.NFC);
String canonicalB = Normalizer.normalize(decomposed, Form.NFC);
System.out.println(canonicalA.equals(canonicalB)); // true
```

Đây là **mảnh code**, cần import `Normalizer` và `Form`; chương trình độc lập nằm ở mục 8. Lưu ý `Normalizer` làm việc trên **dữ liệu Unicode đã giải mã**. Nếu file đã bị đọc sai charset, chuẩn hóa **không sửa được** những code points bị hỏng do decoding.

### 3.3. Độ dài và chỉ số có thể thay đổi

NFD có thể tăng số code points/code units vì tách ký tự dựng sẵn; NFC có thể giảm. NFKC/NFKD có thể thay đổi số lượng ký tự theo compatibility mapping. Không áp dụng những offset/cursor selection của chuỗi gốc lên chuỗi đã normalized như thể độ dài giữ nguyên.

Ví dụ vị trí con trỏ trong editor dùng UTF-16 offsets; nếu bạn lưu vị trí ở bản chưa chuẩn rồi gửi cho bản NFC, vị trí có thể lệch. Cần mapping hoặc chỉ chuẩn hóa ở ranh giới lưu trữ/so sánh, bảo toàn text mà editor đang hiển thị tùy thiết kế.

## 4. Đổi chữ hoa và chữ thường giải quyết vấn đề khác

`String.toLowerCase(Locale)` và `String.toUpperCase(Locale)` làm **case mapping**. Chúng không phải Unicode normalization:

```java
import java.util.Locale;

// Mảnh minh họa Java 17+:
String lower = "TITLE".toLowerCase(Locale.ROOT); // "title"
String upper = "Stra\u00DFe".toUpperCase(Locale.ROOT); // "STRASSE"
```

Case mapping có thể:

- Chuyển một ký tự thành nhiều ký tự: `ß` uppercase có thể thành `SS`.
- Phụ thuộc **locale**: tiếng Thổ Nhĩ Kỳ có quy tắc riêng cho chữ `I`, `i`, `İ`, `ı`.
- Phụ thuộc **ngữ cảnh trong chuỗi**: ví dụ lowercase của sigma Hy Lạp có thể khác theo vị trí trong từ.
- Thay đổi số lượng UTF-16 code units. Không có bảo đảm lowercase/uppercase là một phép biến đổi 1:1.
- Không nhất thiết bảo đảm chuỗi sau case mapping ở NFC, NFD hay bất kỳ form nào.

Không nên đổi case theo từng `char` bằng `Character.toLowerCase(char)` rồi coi đó tương đương `String.toLowerCase(Locale)`: dạng xử lý theo code point của `Character` cũng không thay thế đầy đủ case mapping cả chuỗi, đặc biệt với mapping 1:N hoặc phụ thuộc ngữ cảnh.

### 4.1. Tại sao cần `Locale`?

Overload không có tham số `"TITLE".toLowerCase()` sử dụng **`Locale.getDefault()` của tiến trình**. Điều đó khiến kết quả phụ thuộc môi trường. Trong locale Turkish:

```java
String tr = "TITLE".toLowerCase(Locale.forLanguageTag("tr"));
String root = "TITLE".toLowerCase(Locale.ROOT);
```

- `root` là `"title"`.
- `tr` chứa ký tự **`ı`** (`U+0131`, dotless i), không giống `"title"` trong root locale.
- `Locale.forLanguageTag("tr")` hoạt động trên Java 17+; không cần dùng API locale mới hơn.

**Chọn đúng policy:**

- **Nội dung hiển thị cho người dùng**: dùng locale tương ứng ngôn ngữ/người dùng khi ý nghĩa chuyển hoa/thường cần tự nhiên.
- **Các khóa giao thức, field name, cấu hình hoặc mã máy dùng quy tắc không phụ thuộc ngôn ngữ**: nếu thực sự cần lowercase, dùng `Locale.ROOT` thay vì locale mặc định.
- **So sánh tên/chuỗi bất kỳ không phân biệt hoa/thường**: cân nhắc case folding hoặc collator, không mặc định `toLowerCase(Locale.ROOT)` là thuật toán full Unicode caseless equivalence.

**Không dùng `Locale.ROOT` như lời khẳng định rằng lowercase là Unicode full case folding.** Hai khái niệm và tập quy tắc khác nhau.

## 5. Case conversion không đồng nghĩa case-insensitive comparison

Khi yêu cầu “không phân biệt hoa/thường”, nhiều developer nghĩ ngay:

```java
a.toLowerCase(Locale.ROOT).equals(b.toLowerCase(Locale.ROOT))
```

Đó là một **quy ước tự chọn**: bạn đang so sánh **các kết quả của một phép lowercase cụ thể**. Nó không đảm bảo làm đúng mọi phép đối chiếu caseless theo Unicode, cũng không phải phép so sánh ngôn ngữ tự nhiên.

### 5.1. `equalsIgnoreCase` (Java 17+)

`String.equalsIgnoreCase(String)` thực hiện so sánh đơn giản bỏ qua khác biệt case, **không dùng locale**. Nó không chuẩn hóa NFC/NFD trước khi so sánh, và không hỗ trợ mọi trường hợp full Unicode case folding, đặc biệt mapping nhiều code points.

Ví dụ:

```java
String x = "Stra\u00DFe";
String y = "STRASSE";
System.out.println(x.equalsIgnoreCase(y)); // false trên JDK 24 kiểm thử
```

`"ß"` và `"SS"` không thể được coi tương đương chỉ bằng phép đối chiếu từng code point như `equalsIgnoreCase`. Ngoài ra `equalsIgnoreCase` trên `"É"` và `"e\u0301"` cũng trả `false` do khác dạng biểu diễn. Từ đó thấy có **hai trục khác biệt độc lập**: Unicode canonical representation và case.

### 5.2. Full Unicode case folding: API Java 26+

**JDK 26** bổ sung các API `String.equalsFoldCase(String)`, `compareToFoldCase(String)` và comparator `String.UNICODE_CASEFOLD_ORDER`; JDK 27 tiếp tục hỗ trợ. Chúng áp dụng **Unicode full case folding** (có mapping một code point thành nhiều code points), dùng cho so sánh không phân biệt case một cách **không phụ thuộc locale**.

```java
// Mảnh code dành riêng cho JDK 26+, KHÔNG biên dịch với --release 17.
String a = "Fu\u00DF";
String b = "FUSS";

boolean simple = a.equalsIgnoreCase(b); // false
boolean folded = a.equalsFoldCase(b);   // true
int ordering = a.compareToFoldCase(b);  // 0
```

Kết quả trên được xác nhận theo **tài liệu API JDK 26/27**; môi trường ví dụ chạy thực tế ở mục 8 dùng JDK 24 nên **không kiểm thử thực thi** các method chỉ xuất hiện từ 26. Không trình bày `equalsFoldCase` như method có trên Java 17, 21, 24 hay 25.

**Quan trọng:** Unicode case folding không tự có nghĩa là **normalization**. Nếu bài toán còn muốn canonical-equivalent sequences như `"é"` và `"e\u0301"` được coi bằng nhau, hãy có **bước normalize riêng với form nhất quán** rồi mới so sánh caseless, theo chính sách của hệ thống. Để tạo ra **chuỗi key đã case-folded** (không chỉ kiểm tra equality), hãy chọn thư viện/quy tắc mã hóa có hỗ trợ full Unicode folding phù hợp; `equalsFoldCase` chỉ là phép so sánh, không cung cấp `String.toFoldCase()`.

### 5.3. Locale-aware comparison không giống case folding

`java.text.Collator` là API cho so sánh/sắp xếp chuỗi nhạy với locale. Với giao diện người dùng, khi tìm kiếm/sắp xếp tên theo quy tắc văn hóa, cân nhắc `Collator.getInstance(locale)` và cấu hình strength/decomposition phù hợp.

```java
// Mảnh minh họa Java 17+, không phải chương trình độc lập.
java.text.Collator collator = java.text.Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
collator.setStrength(java.text.Collator.PRIMARY);
int order = collator.compare("A", "a");
```

- `PRIMARY` có thể gộp các khác biệt case/diacritics theo quy tắc collator của locale; đây là **chính sách đối chiếu ngôn ngữ tự nhiên**, không phải `String.equals()`.
- Kết quả thứ tự/so sánh có thể phụ thuộc bộ dữ liệu collation, locale và JDK/CLDR; không dùng nó làm hash key định danh nếu bạn chưa định nghĩa một quy tắc bền vững.
- Đừng dùng `equalsIgnoreCase` hoặc `equalsFoldCase` thay `Collator` khi yêu cầu thứ tự sắp xếp tự nhiên của người dùng.

## 6. So sánh bốn mục đích phổ biến

| Mục đích | Hướng chọn | Không phù hợp khi |
| --- | --- | --- |
| **Giữ nguyên nội dung từng code unit** | `String.equals` với chuỗi gốc. | Muốn gộp composed/decomposed equivalents. |
| **Canonical-equivalent matching, giữ khác biệt case** | Normalize cả hai về **NFC** rồi `equals`. | Muốn bỏ qua hoa/thường. |
| **Bỏ qua case theo chính sách đơn giản** | Java 17+: normalize trước, rồi xét `equalsIgnoreCase` hoặc lowercase `Locale.ROOT` với giới hạn đã biết. | Cần full Unicode case folding/locale-specific rules. |
| **Full Unicode caseless matching** | JDK 26+: normalize NFC hai phía, rồi `equalsFoldCase` theo chính sách đã kiểm thử. | Cần sắp xếp ngôn ngữ tự nhiên, hoặc hệ đang dùng Java thấp hơn 26. |
| **Biến đổi compatibility** | `NFKC` hoặc `NFKD` chỉ khi product spec chấp nhận hợp nhất compatibility characters. | Muốn giữ sự phân biệt ký tự gốc/kiểu trình bày. |
| **Sắp xếp/tìm kiếm theo ngôn ngữ** | `Collator` với locale/strength/decomposition thích hợp. | Cần khóa identity byte-for-byte ổn định trên nhiều runtime. |
| **Tìm kiếm “không dấu”** | Thiết kế **một index tìm kiếm phụ** có xử lý combining marks và các ngoại lệ ngôn ngữ. | Cần lưu/gán lại giá trị nguồn không mất dấu. |

**Thứ tự tư duy:** xác định “bằng nhau” theo **ý nghĩa nghiệp vụ** trước, rồi mới chọn biến đổi và API. “Chuẩn hóa trước, lowercase sau” không phải giải pháp vạn năng cho mọi language/script hoặc security profile.

## 7. Vì sao đổi hoa/thường có thể làm lệch normalization?

Giả sử chuỗi có chữ hoa có dấu, ký tự kết hợp và các quy tắc case không 1:1. Case mapping là một phép biến đổi dãy code points, và kết quả **không được `String.toLowerCase` bảo đảm** luôn ở form NFC. Vì thế, với một index/lookup mà bạn chọn policy **NFC + lowercase**, nên **chuẩn hóa lại NFC ở cuối** nếu cần bảo đảm key luôn canonical:

```java
// Mảnh code Java 17+, cố ý là chính sách lowercase đơn giản,
// không phải full Unicode case folding:
static String simpleSearchKey(String input) {
    String nfc = Normalizer.normalize(input, Normalizer.Form.NFC);
    String lower = nfc.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
```

Để dùng, cần import `java.text.Normalizer`, `java.util.Locale`. Helper tạo một **key phụ** cho những use case chấp nhận quy tắc đơn giản này; không bảo đảm phù hợp với mọi hệ chữ, không thay thế case folding đầy đủ từ JDK 26 và không thay bản gốc hiển thị.

**Các nguyên tắc cần xác định thành hợp đồng dữ liệu:**

1. Form nào? NFC hay NFKC? Không thay đổi ngầm theo yêu cầu cảm tính.
2. Có bỏ qua case không? Nếu có, dùng thuật toán nào và phiên bản dữ liệu Unicode nào?
3. Có phụ thuộc locale không? Nếu có, locale nào được áp dụng cho từng giá trị?
4. Có bỏ dấu không? Nếu có, đây là thay đổi **lossy**, không còn là normalization canonical.
5. Khóa có được dùng cho authentication, uniqueness và database indexes không? Nếu có, collision policy phải rõ ràng.
6. Khi nâng JDK/thư viện, hành vi mapping Unicode có thể thay đổi; cần regression tests và migration plan cho những key lưu lâu dài.

Khi dữ liệu đi qua nhiều service (Java, JavaScript, Python, database collation), cùng một chữ có thể được normalize/case-fold khác nhau nếu mỗi nơi tự đặt policy. Tốt nhất có một lớp xử lý chuẩn hóa được dùng và kiểm thử chung tại ranh giới nhập/indexing.

## 8. Chương trình Java 17+ đầy đủ: kiểm chứng 13 kết quả

Tạo file **`UnicodeNormalizationVsCaseDemo.java`**. Chương trình sau không phụ thuộc terminal, font hiển thị tiếng Việt hay thư viện bên ngoài. Chúng ta dùng Unicode escapes để kiểm tra chính xác code points; code có thể chạy với Java 17+.

```java
import java.text.Normalizer;
import java.text.Normalizer.Form;
import java.util.Locale;
import java.util.stream.Collectors;

public final class UnicodeNormalizationVsCaseDemo {
    private static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("raw.equals=" + composed.equals(decomposed));
        System.out.println("nfc.equals=" + Normalizer.normalize(composed, Form.NFC)
                .equals(Normalizer.normalize(decomposed, Form.NFC)));
        System.out.println("nfd.codepoints=" +
                points(Normalizer.normalize(composed, Form.NFD)));
        System.out.println("nfc.check.decomposed=" +
                Normalizer.isNormalized(decomposed, Form.NFC));

        String ffiLigature = "\uFB03";
        System.out.println("ligature.nfcEqualsFfi=" +
                Normalizer.normalize(ffiLigature, Form.NFC).equals("ffi"));
        System.out.println("ligature.nfkcEqualsFfi=" +
                Normalizer.normalize(ffiLigature, Form.NFKC).equals("ffi"));

        System.out.println("turkish.lower.points=" +
                points("TITLE".toLowerCase(Locale.forLanguageTag("tr"))));
        System.out.println("root.lower=" +
                "TITLE".toLowerCase(Locale.ROOT));
        System.out.println("sharp.upper=" +
                "Stra\u00DFe".toUpperCase(Locale.ROOT));
        System.out.println("sharp.equalsIgnoreCase=" +
                "Stra\u00DFe".equalsIgnoreCase("STRASSE"));

        String capitalAccent = "\u00C9";
        System.out.println("case.only.equals=" +
                capitalAccent.equalsIgnoreCase(decomposed));
        System.out.println("nfc.then.case.equals=" +
                Normalizer.normalize(capitalAccent, Form.NFC)
                        .equalsIgnoreCase(
                                Normalizer.normalize(decomposed, Form.NFC)));
        System.out.println("nfc.keeps.case=" +
                Normalizer.normalize("CAF\u00C9", Form.NFC));
        System.out.println("removeMarks.Dang=" +
                Normalizer.normalize("\u0110\u1EB7ng", Form.NFD)
                        .replaceAll("\\p{M}+", ""));
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 UnicodeNormalizationVsCaseDemo.java
java UnicodeNormalizationVsCaseDemo
```

**Stdout đã thực sự kiểm chứng bằng `javac/java` trên JDK 24:**

```text
raw.equals=false
nfc.equals=true
nfd.codepoints=U+0065 U+0301
nfc.check.decomposed=false
ligature.nfcEqualsFfi=false
ligature.nfkcEqualsFfi=true
turkish.lower.points=U+0074 U+0131 U+0074 U+006C U+0065
root.lower=title
sharp.upper=STRASSE
sharp.equalsIgnoreCase=false
case.only.equals=false
nfc.then.case.equals=true
nfc.keeps.case=CAFÉ
removeMarks.Dang=Đang
```

### Đọc kết quả theo từng nhóm

**Các dòng 1–4: canonical equivalence**

- `raw.equals=false`: `é` dựng sẵn và `e + U+0301` không có cùng dãy UTF-16 units.
- `nfc.equals=true`: chuẩn hóa cả hai về NFC xử lý khác biệt biểu diễn canonical.
- `nfd.codepoints=U+0065 U+0301`: NFD tách `U+00E9` thành chữ `e` và combining acute accent.
- `nfc.check.decomposed=false`: dãy `e\u0301` chưa ở NFC, dù hiển thị giống một chữ có dấu.

**Các dòng 5–6: canonical vs compatibility**

- `ligature.nfcEqualsFfi=false`: NFC không có nhiệm vụ hợp nhất compatibility ligature `ﬃ` thành `ffi`.
- `ligature.nfkcEqualsFfi=true`: NFKC có compatibility mapping cho ký tự này. Không được kết luận NFKC phù hợp với mọi trường hợp lưu trữ.

**Các dòng 7–10: chữ hoa/thường**

- `turkish.lower.points` chứa `U+0131` là chữ `ı` không có chấm; uppercase/lowercase locale-specific là quyết định riêng.
- `root.lower=title` với `Locale.ROOT`.
- `sharp.upper=STRASSE`: case mapping có thể mở rộng một code point thành nhiều ký tự.
- `sharp.equalsIgnoreCase=false`: phép so sánh đơn giản không tương đương full Unicode case folding.

**Các dòng 11–13: hai trục khác nhau và mất dấu**

- `case.only.equals=false`: chỉ bỏ case bằng `equalsIgnoreCase` chưa giải quyết `É` vs `e\u0301`.
- `nfc.then.case.equals=true`: sau khi NFC, so sánh case-insensitive đơn giản đủ cho ví dụ cụ thể.
- `nfc.keeps.case=CAFÉ`: NFC **không lowercase**, giữ chữ hoa.
- `removeMarks.Dang=Đang`: bỏ combining marks khỏi NFD của `Đặng` **không** tự đổi chữ `Đ` thành `D`. Việc xóa dấu là một phép biến đổi khác, không phải normalization canonical.

### Vì sao ví dụ dùng `codePoints()`?

`String.codePoints()` tạo `IntStream` các Unicode code points, tránh nhầm giữa một Unicode code point và một UTF-16 `char`. Cặp surrogate vẫn được xử lý thành một code point. `String.length()` không phải phép đo số grapheme mà người dùng nhìn thấy, đặc biệt với combining marks và emoji sequences.

### Kết quả có phụ thuộc môi trường không?

Trong test, các trường hợp có Unicode escapes và `Locale.ROOT`/`Locale.forLanguageTag("tr")` cho ra kết quả như đã in. Các trường hợp mapping/đối chiếu khác có thể bị ảnh hưởng bởi phiên bản Unicode data của JDK, vì vậy **cần kiểm thử lại khi đổi runtime nếu key persisted phụ thuộc vào chúng**. Chương trình này không sử dụng API mới chỉ có ở JDK 26, nên tương thích Java 17+.

## 9. Tiếng Việt: dấu, chữ đ và chuẩn hóa đúng

Tiếng Việt có nhiều tổ hợp dấu phụ (ví dụ dấu mũ, dấu móc, dấu thanh). Unicode có thể biểu diễn một số chữ có dấu bằng một code point dựng sẵn hoặc nhiều code points ghép dấu.

Ví dụ:

```text
"ấ"                  (một code point được dựng sẵn)
"a" + U+0302 + U+0301  (a + mũ + sắc, dạng phân tách)
```

NFC chuẩn hóa về dạng ghép khi Unicode định nghĩa ánh xạ canonical phù hợp. NFD tách thành thành phần, sắp xếp combining marks theo quy tắc. **Cả hai vẫn giữ nghĩa và dấu**.

**Bỏ dấu để tìm kiếm là một thao tác thứ ba**, thường làm bằng: NFD → xóa combining marks → xử lý ngoại lệ nếu product yêu cầu, chẳng hạn `đ/Đ`. Ví dụ `Đặng` sau bỏ combining marks theo `\p{M}` trở thành `Đang`; `Đ` không tự biến thành `D`. Nếu muốn `Dang`, bạn phải **tự quy định thêm phép biến đổi `Đ` → `D`** và quyết định có chấp nhận mất phân biệt giữa các từ hay không.

```java
// Mảnh code minh họa có chủ đích LOSSY cho search index phụ.
// Không dùng để thay tên người đã lưu.
static String stripCombiningMarks(String value) {
    return Normalizer.normalize(value, Normalizer.Form.NFD)
            .replaceAll("\\p{M}+", "");
}
```

- `\p{M}` là nhóm Unicode combining marks, không phải “mọi thứ trông như dấu” hay mapping transliteration.
- Xóa marks có thể làm **nhiều từ khác nhau biến thành cùng dạng**, gây nhầm lẫn/đụng khóa.
- Với văn bản đa ngôn ngữ, combining marks đôi khi là phần thiết yếu chứ không phải decoration.
- Search UI có thể có index “không dấu” riêng, còn bản gốc cho hiển thị, lưu hồ sơ và audit phải được bảo toàn.

**Đừng coi đổi hoa/thường là phép xóa dấu.** `"ĐẶNG".toLowerCase(Locale.forLanguageTag("vi"))` tạo lowercase phù hợp nhưng không nhất thiết làm mất dấu, còn `Normalizer.normalize("ĐẶNG", NFC)` không tự lowercase hoặc xóa dấu.

## 10. Case folding, collation và các quy tắc tìm kiếm khác

### 10.1. Case folding là phép biến đổi phục vụ matching

Case folding dùng để loại bỏ khác biệt chữ hoa/thường theo Unicode. Nó có **định nghĩa kỹ thuật riêng** trong dữ liệu Unicode `CaseFolding.txt`. JDK 26+ `String.equalsFoldCase` làm so sánh full folding; đây không phải `toLowerCase(Locale.ROOT)` với một cái tên mới.

Nếu vẫn hỗ trợ Java 17, có hai lựa chọn:

- Với tập ký tự/locale đã kiểm soát và các case được test, dùng pipeline NFC + `equalsIgnoreCase`/lowercase có giới hạn.
- Nếu cần **Unicode full folding** trên các JDK cũ, sử dụng thư viện Unicode phù hợp (ví dụ ICU4J) cùng phiên bản/quy tắc được xác định, thay vì tự dựng bảng cho mọi ngôn ngữ bằng vài phép `replace`.

Không tạo normalized lowercase “canonical identifier” một cách vô tình rồi đổi chính sách ở phiên bản sau: nó có thể làm hai tài khoản hoặc hai tên file vốn khác nhau va vào cùng khóa.

### 10.2. Collation phục vụ sắp xếp ngôn ngữ tự nhiên

Người dùng muốn tìm/sắp xếp tên người trong tiếng Việt hoặc Turkish không chỉ yêu cầu bỏ case. Họ còn quan tâm accent weight, thứ tự chữ cái và tùy chọn văn hóa.

`Collator` có thể được cấu hình `PRIMARY`, `SECONDARY`, `TERTIARY` và decomposition mode, nhưng nó có mục đích **locale-sensitive sorting/comparison**, không phải Unicode normalization algorithm, không tự tạo ra khóa String chuẩn hóa bền vững cho database. Cần test với locale và JDK data thực tế.

**Không so sánh các chuỗi theo kết quả nhìn thấy của GUI**: fonts có thể render cùng hình cho các code points khác nhau; Unicode confusables (kí tự Latin và Cyrillic giống hình, v.v.) không được NFC hay lowercase mặc định hợp nhất.

### 10.3. NFKC không phải bộ lọc an ninh hoàn chỉnh

NFKC có thể hợp nhất những ký tự compatibility, nhưng **không giải quyết tất cả Unicode spoofing/confusables, mixed-script attacks hay bidi controls**. Nếu bạn định nghĩa username, domain, identifier hoặc dữ liệu chịu ràng buộc bảo mật, hãy áp dụng **profile tiêu chuẩn phù hợp domain** (ví dụ quy định cho username/domain) và validation cụ thể, thay vì mặc định `NFKC + toLowerCase` sẽ chống giả mạo.

Dấu tiếng Việt hoặc ký tự đặc thù ngôn ngữ có thể mang ý nghĩa. Việc bỏ dấu/hợp nhất tùy tiện có thể tạo ra **false positives**, **false negatives** hoặc lỗi cấp quyền.

## 11. Ứng dụng thực tế: lưu trữ, so sánh, index và UI

### 11.1. Chuỗi hiển thị và chuỗi khóa là hai tầng dữ liệu

Một thiết kế thường hữu ích:

```text
Input từ người dùng
    |
    +----------------------------> originalDisplayName
    |                              (bảo toàn nội dung nhập)
    |
    +--> validation theo domain
             |
             +--> normalization có policy rõ ràng
                       |
                       +--> comparison/search key
                                  (có version + collision checks)
```

Giữ `originalDisplayName` để hiển thị hoặc audit khi cần; tạo search key phụ theo policy đã công bố. Nếu muốn dữ liệu được lưu duy nhất ở NFC, cần xác định rõ đây là hợp đồng của hệ thống và áp dụng nhất quán trước khi ghi, không chỉ ở chỗ tìm kiếm.

### 11.2. Khóa máy độc lập với locale

Một số khóa giao thức hoặc cấu hình chỉ chấp nhận ASCII: nếu vậy tốt nhất **validate ASCII theo quy tắc của giao thức** rồi xử lý case trong miền được phép, không cần dùng thuật toán Unicode quá rộng cho một domain vốn không cho phép Unicode.

Với khóa cho phép Unicode, cần xem xét:

- Unicode normalization form nào được chấp nhận?
- Có chính sách case-insensitive hay không?
- Case folding là full Unicode hay xử lý đơn giản?
- Chấp nhận compatibility forms không?
- Thông tin phiên bản policy nào được lưu để migration?
- Hai giá trị khác nhau sau normalization/folding lại thành cùng một key thì báo lỗi hay hợp nhất?

Lưu key nhất quán trong database và cùng cách tính trong lookup, uniqueness constraints, cache, job deduplication. Không normalize ở API nhưng quên ở DB constraint.

### 11.3. Database collation khác `Normalizer`

Nhiều database có collation case-insensitive hoặc accent-insensitive riêng. Nó có thể không tương đương hoàn toàn với Java Normalizer, `equalsIgnoreCase` hay JDK 26 `equalsFoldCase`. Nếu ứng dụng chuẩn hóa tại Java còn DB so sánh theo collation khác, uniqueness/query behavior có thể không nhất quán. Cần test end-to-end.

### 11.4. Thứ tự và idempotence

Unicode normalization với một form cố định là **idempotent**: áp dụng lại cùng form trên dữ liệu đã normalized không tạo thay đổi mới.

```java
// Mảnh minh họa Java 17+:
String once  = Normalizer.normalize(input, Normalizer.Form.NFC);
String twice = Normalizer.normalize(once, Normalizer.Form.NFC);
boolean same = once.equals(twice); // true
```

Không được suy ra mỗi phép biến đổi trong pipeline có thể tráo thứ tự tùy ý hoặc toàn bộ pipeline tự idempotent trong mọi trường hợp. Khi kết hợp compatibility normalization, locale-aware case mapping, stripping marks và biến đổi ứng dụng, hãy **chốt thứ tự** và viết test về tính ổn định trước khi dùng làm key.

## 12. Các lỗi phổ biến

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `toLowerCase()` “chuẩn hóa Unicode” | Nó đổi case theo default locale, không làm NFC/NFD. | Dùng `Normalizer` cho canonical/compatibility forms. |
| `Normalizer.normalize(..., NFC)` “không phân biệt hoa/thường” | NFC vẫn giữ khác biệt case. | Thêm bước caseless comparison theo policy. |
| `equalsIgnoreCase` xử lý mọi Unicode case | Nó là so sánh đơn giản, không full 1:N folding. | Trên JDK 26+ cân nhắc `equalsFoldCase`; JDK cũ dùng công cụ phù hợp. |
| `toLowerCase(Locale.ROOT)` luôn giống full Unicode folding | Case mapping và case folding có định nghĩa khác. | Chỉ dùng đơn giản khi đáp ứng spec của sản phẩm. |
| Dùng `toLowerCase()` mặc định cho protocol key | Kết quả phụ thuộc default locale (ví dụ Turkish). | Dùng `Locale.ROOT` nếu policy là locale-neutral và case mapping được cho phép. |
| Nghĩ NFKC và NFC giống nhau | NFKC xử lý compatibility, NFC chủ yếu canonical. | Chọn form theo mức độ bảo toàn thông tin cần thiết. |
| NFD tự xóa dấu | NFD **phân tách** nhưng vẫn giữ combining marks. | Xóa marks là thao tác riêng và **lossy** nếu nghiệp vụ yêu cầu. |
| Bỏ dấu tiếng Việt xong mọi `đ` thành `d` | `đ` không tự phân rã thành `d + mark`. | Quy định mapping riêng nếu search index cần và chấp nhận mất nghĩa. |
| Chỉ kiểm tra UTF-16 `length()` như số ký tự hiển thị | Có surrogate pair và combining marks. | Phân biệt code units, code points và grapheme clusters. |
| Dựa vào glyph/font để so sánh identity | Hai mã khác nhau có thể trông giống nhau. | Dùng domain-aware validation, không dựa vào render. |
| Chuẩn hóa sau khi tính text offsets rồi dùng offsets cũ | Độ dài và vị trí có thể đổi. | Chuẩn hóa ở thời điểm phù hợp hoặc mapping vị trí. |
| Áp NFKC cho tất cả user input | Có thể hợp nhất các ký tự trước đó có ý nghĩa khác. | Cần policy định danh/search rõ ràng và collision test. |
| Đổi policy mà không migration | Các key đã lưu có thể thay đổi khi nâng JDK/Unicode data. | Version hóa policy, test và có quy trình migration. |
| Dùng `Collator.PRIMARY` làm khóa identity | Locale/collation data có thể thay đổi. | Dùng key/collation được định nghĩa cho domain, không trộn nghĩa. |
| Nghĩ `equalsFoldCase` có trên Java 17 | API này chỉ mới có từ **JDK 26**. | Giữ mẫu Java 17 với API hiện có; nâng toolchain hoặc dùng thư viện nếu cần. |

## 13. Checklist khi triển khai

- [ ] Đã phân biệt canonical equivalence, compatibility equivalence và case-insensitive matching?
- [ ] Đã xác định form NFC/NFD/NFKC/NFKD cho mục đích cụ thể?
- [ ] Đã biết input/output có đúng UTF-8 hoặc encoding contract trước khi normalize?
- [ ] Đã chọn `Locale.ROOT` hay locale của người dùng có chủ đích?
- [ ] Đã kiểm tra các trường hợp Turkish `I/İ/ı` và tiếng Đức `ß` nếu hỗ trợ đa ngôn ngữ?
- [ ] Đã cân nhắc Java 17 `equalsIgnoreCase` so với Java 26+ `equalsFoldCase`?
- [ ] Đã quyết định có cần normalize **trước khi** so sánh caseless?
- [ ] Đã không coi xóa dấu/transliterate là Unicode normalization canonical?
- [ ] Đã giữ text gốc khi normalization hoặc accent-folding có nguy cơ mất thông tin?
- [ ] Đã test conflict/collision của index/uniqueness sau mọi biến đổi?
- [ ] Đã đồng bộ policy giữa Java application, database, search engine và client?
- [ ] Đã kiểm tra text offsets sau biến đổi nếu editor UI cần highlight/chọn vùng?
- [ ] Đã có regression tests khi thay JDK/Unicode data/library collation?
- [ ] Đã dùng policy chống spoofing phù hợp domain nếu chuỗi liên quan đến tài khoản/định danh bảo mật?

## 14. Bài tập thực hành

**Bài tập A — Canonical equivalence:** thay `"é"` bằng một chữ tiếng Việt như `"ấ"` và dạng decomposed tương đương. In code points trước/sau `NFD` và `NFC`; xác nhận hai dạng cho `equals()==false` trước nhưng bằng nhau sau NFC.

**Bài tập B — Compatibility:** thử ký tự full-width Latin hoặc Roman numeral dạng compatibility. So sánh `NFC` và `NFKC`; ghi rõ những khác biệt về nghĩa có thể xuất hiện trong dữ liệu thật.

**Bài tập C — Locale:** với `"TITLE"`, dùng `Locale.ROOT` và locale Turkish. In `codePoints()`, đừng chỉ nhìn font.

**Bài tập D — Case folding:** nếu có JDK 26+, thử `"Fuß".equalsFoldCase("FUSS")` và `equalsIgnoreCase`. Trên JDK 17, giải thích vì sao không thể gọi method mới; không tự viết bảng case folding một vài ký tự rồi tuyên bố hỗ trợ toàn Unicode.

**Bài tập E — Index phụ:** viết `simpleSearchKey(...)` với NFC + lowercase ROOT + NFC; test composed/decomposed, input chữ hoa và kết quả khác biệt với full case folding. Giữ bản gốc hiển thị.

**Bài tập F — Tiếng Việt:** NFD `"Đặng"` rồi xóa `\p{M}`, quan sát `"Đang"`. Giải thích vì sao cần thêm mapping riêng nếu muốn `"Dang"`; nói rõ rủi ro collision khi tìm kiếm không dấu.

**Bài tập G — Dữ liệu ổn định:** thiết kế một migration plan khi muốn chuyển khóa tìm kiếm từ NFC + lowercase ROOT sang NFKC + full Unicode folding. Mô tả cách phát hiện xung đột và cập nhật index mà không làm mất tên gốc.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** NFC có làm `"CAFÉ"` trở thành `"café"` không?

**Đáp án:** Không. NFC thống nhất biểu diễn canonical, không đổi case. Muốn lowercase phải có case conversion riêng.

**Câu 2.** NFD của `"é"` có xóa dấu sắc không?

**Đáp án:** Không. Nó tạo chuỗi `U+0065 U+0301` — dấu sắc vẫn có mặt dưới dạng combining mark.

**Câu 3.** Khi nào `"é".equals("e\u0301")` có thể trở thành `true`?

**Đáp án:** Bản thân `equals` là false với hai dãy code units khác nhau. Sau khi chuẩn hóa **cả hai** bằng cùng form NFC hoặc NFD, so sánh `equals` sẽ true.

**Câu 4.** Vì sao không nên dùng `"TITLE".toLowerCase()` cho một protocol key đa ngôn ngữ?

**Đáp án:** Overload không đối số dùng default locale; ví dụ Turkish tạo chữ dotless `ı`. Nếu spec yêu cầu locale-neutral lowercase, chọn `Locale.ROOT`.

**Câu 5.** NFC và NFKC có đồng nhất ký tự ligature `ﬃ` với `ffi` như nhau không?

**Đáp án:** Không. NFC giữ khác biệt compatibility này; NFKC hợp nhất chúng.

**Câu 6.** `equalsIgnoreCase` có phải full Unicode case folding không?

**Đáp án:** Không. Java 17+ `equalsIgnoreCase` dùng quy tắc đơn giản trên code points. JDK 26+ có `equalsFoldCase` hỗ trợ full Unicode folding, bao gồm mapping `ß` thành `ss` khi so sánh.

**Câu 7.** `equalsFoldCase` tự chuẩn hóa NFC mọi dữ liệu đầu vào không?

**Đáp án:** Đừng giả định như vậy. Nó mô tả phép so sánh dựa trên case folding; nếu muốn gộp composed/decomposed theo canonical equivalence, xác định thêm bước normalize thống nhất.

**Câu 8.** Vì sao bỏ `\p{M}` sau NFD của tiếng Việt không phải chuẩn hóa Unicode?

**Đáp án:** Vì đó là phép **xóa thông tin dấu**, có thể thay đổi từ/nghĩa và gây collision; NFD không xóa marks.

**Câu 9.** Có nên chuẩn hóa tên hiển thị bằng NFKC rồi bỏ luôn bản gốc khi làm ứng dụng quản lý người dùng?

**Đáp án:** Chỉ khi policy dữ liệu công khai cho phép và đã xem xét tác động mất thông tin. Thường nên giữ original display name và index/key phụ được chuẩn hóa theo yêu cầu tìm kiếm/identity.

## 16. Tài liệu chính thức hiện hành

- [Normalizer — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized` và hợp đồng chuẩn hóa.
- [Normalizer.Form — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.Form.html): NFC/NFD/NFKC/NFKD.
- [String — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): `toLowerCase`, `toUpperCase`, `equalsIgnoreCase` và case folding APIs (từ JDK 26).
- [Character — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html): code points, Unicode categories và case information.
- [Collator — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Collator.html): locale-sensitive collation.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): cơ sở tiêu chuẩn cho bốn dạng.
- [Unicode Default Case Algorithms](https://www.unicode.org/versions/latest/core-spec/chapter-3/#G33992): khác biệt case mapping và folding.
- [Java SE 26 new APIs](https://docs.oracle.com/en/java/javase/26/docs/api/new-list.html): xác nhận `String.equalsFoldCase`/`compareToFoldCase` được thêm từ Java 26.

**Ghi nhớ:** Unicode normalization giải quyết **biểu diễn canonical/compatibility**, case conversion giải quyết **dạng chữ hoa/thường**, còn case folding giải quyết **caseless equivalence**. Chúng không đồng nghĩa và không thể hoán đổi tùy ý. Dùng `Normalizer` cho NFC/NFD/NFKC/NFKD, `String.toLowerCase/toUpperCase(Locale)` theo ngôn ngữ hoặc `Locale.ROOT` đúng chỗ, và API caseless phù hợp với Java version. Trước khi dùng kết quả làm khóa đăng nhập/tìm kiếm/database, hãy định nghĩa collision policy, giữ dữ liệu gốc nếu cần và kiểm thử với Unicode thực tế.
