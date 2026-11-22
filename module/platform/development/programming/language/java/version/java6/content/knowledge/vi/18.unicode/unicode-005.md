# Chuẩn hóa Unicode trước tìm kiếm, so sánh hoặc lưu khóa trong Java

## 1. Vấn đề thực tế: nhìn giống nhau chưa chắc là cùng chuỗi

Một hệ thống nhận tên người dùng, nhãn sản phẩm, từ khóa tìm kiếm hoặc mã định danh từ trình duyệt, điện thoại và tệp nhập khẩu có thể gặp **nhiều biểu diễn Unicode cho văn bản nhìn giống nhau**. Ví dụ ký tự `é` có thể biểu diễn bằng:

- `U+00E9`: một code point **LATIN SMALL LETTER E WITH ACUTE**.
- `U+0065 U+0301`: chữ `e` rồi dấu sắc kết hợp (**COMBINING ACUTE ACCENT**).

Chúng là **canonically equivalent** theo Unicode, nhưng biểu diễn trong `String` không nhất thiết giống nhau:

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";
System.out.println(composed.equals(decomposed)); // false
~~~

Đây là **snippet** Java hợp lệ đặt trong method; mã chạy đầy đủ nằm ở mục 7. `String.equals(...)` so sánh nội dung chuỗi UTF-16, không tự thực hiện Unicode normalization. Nếu chỉ lưu raw text làm khóa của `HashMap`, index hay cột có unique constraint, những biểu diễn tương đương có thể bị xem là hai giá trị khác nhau.

Vấn đề có thể xuất hiện cả với tiếng Việt: các nguyên âm có dấu như `ắ`, `ệ` hoặc `ộ` có thể có dạng ký tự dựng sẵn và dạng gồm chữ cơ sở cùng các combining marks. Khi nhập từ những hệ thống khác nhau, **đừng dựa vào vẻ ngoài hoặc độ dài chuỗi để xác nhận bằng nhau**.

**Giải pháp:** định nghĩa một **quy tắc tạo khóa chuẩn (normalization policy)** cho từng miền dữ liệu, áp dụng **cùng một phép biến đổi** ở lúc lưu và lúc truy vấn, rồi so sánh hoặc lập index trên kết quả chuẩn.

~~~text
Input từ UI / API / import
         |
         v
   Xác nhận ngữ cảnh, kiểu dữ liệu
         |
         v
 Normalization policy thống nhất
         |
         +--> Dữ liệu hiển thị gốc (nếu cần giữ)
         |
         +--> Canonical/search key
                    |
       +------------+------------+
       |                         |
       v                         v
 So sánh/HashMap            DB index/UNIQUE
       |                         |
       +----------+--------------+
                  |
           Query cũng chuẩn hóa
                  |
                  v
              Match nhất quán
~~~

**Unicode normalization không tự động thay thế mọi loại so sánh.** Nó giải quyết tương đương chuẩn tắc/compatibility theo Unicode. Còn phân biệt chữ hoa-thường, accent-insensitive search, collation theo ngôn ngữ và nhận diện ký tự dễ nhầm là **những chính sách độc lập** cần thiết kế riêng.

## 2. API Java hiện hành: `java.text.Normalizer`

Java SE cung cấp lớp `java.text.Normalizer` trong module `java.base`, có mặt trên Java 17+ và vẫn được duy trì hiện nay.

~~~java
import java.text.Normalizer;

String key = Normalizer.normalize(input, Normalizer.Form.NFC);
boolean alreadyNfc =
        Normalizer.isNormalized(input, Normalizer.Form.NFC);
~~~

Đây là **snippet**, giả sử biến `input` là `String` không `null`. `normalize(CharSequence, Form)` trả về một `String` đã chuẩn hóa. `isNormalized(CharSequence, Form)` kiểm tra chuỗi có sẵn ở dạng được chọn hay chưa. Cả hai yêu cầu nguồn và form không `null`; nếu vi phạm, API ném `NullPointerException`.

### 2.1. Bốn normalization forms

| Form | Tên đầy đủ | Tác dụng | Khi cân nhắc |
| --- | --- | --- | --- |
| `Normalizer.Form.NFC` | Canonical Decomposition, rồi Composition | Hợp nhất các biểu diễn **tương đương chuẩn tắc**, ưu tiên dạng composed khi có thể | **Mặc định hợp lý cho văn bản tự nhiên, khóa chính tắc và so sánh exact theo canonical equivalence** |
| `Normalizer.Form.NFD` | Canonical Decomposition | Phân rã dạng dựng sẵn thành chữ cơ sở và combining marks | Thuật toán xử lý dấu/code point, kiểm tra chi tiết |
| `Normalizer.Form.NFKC` | Compatibility Decomposition, rồi Composition | Ngoài canonical equivalence còn **gộp các khác biệt compatibility** | Một số loại identifier hoặc search policy cần collapse width/ligature/compatibility |
| `Normalizer.Form.NFKD` | Compatibility Decomposition | Phân rã canonical và compatibility | Xử lý nội bộ khi yêu cầu phân tích các thành phần |

`NFC` và `NFD` bảo toàn **canonical equivalence**; `NFKC` và `NFKD` có thể **làm mất khác biệt compatibility** theo nghĩa người dùng hoặc nghiệp vụ coi là khác nhau. Ví dụ, ký tự số khoanh tròn `①` có thể biến thành `1` qua `NFKC`; ký tự Latin full-width có thể trở về ASCII tương ứng. Đây không chỉ là “chuẩn hóa dấu”.

Theo Unicode Normalization Forms (UAX #15), chọn form cần dựa vào miền dữ liệu. Unicode khuyến nghị **NFC cho văn bản tổng quát**; NFKC/NFKD thích hợp với những miền cần quy tắc matching rộng hơn, không phải thay thế NFC vô điều kiện cho mọi trường dữ liệu.

### 2.2. Ví dụ kinh điển về sự khác biệt

~~~java
String a = "\u00E9";
String b = "e\u0301";

boolean rawSame = a.equals(b); // false
boolean canonicalSame =
        Normalizer.normalize(a, Normalizer.Form.NFC)
                .equals(Normalizer.normalize(b, Normalizer.Form.NFC));
// true
~~~

Mã trên là **snippet** để minh họa canonical equivalence, không phải một chương trình có `main`. Nếu chuẩn hóa cả hai đầu vào về `NFD` thay vì `NFC` thì cặp này cũng bằng nhau. Điểm quan trọng là **cùng một form** ở tất cả vị trí so sánh.

Đối với full-width Latin:

~~~java
String fullWidth = "\uFF2A\uFF41\uFF56\uFF41";
boolean withNfc = Normalizer.normalize(
        fullWidth, Normalizer.Form.NFC).equals("Java");   // false
boolean withNfkc = Normalizer.normalize(
        fullWidth, Normalizer.Form.NFKC).equals("Java");  // true
~~~

Đây là minh họa **compatibility normalization**, không phải lý do để ép mọi tên riêng hoặc văn bản hiển thị về NFKC.

## 3. Định nghĩa đúng “bằng nhau” trước khi viết hàm khóa

Một ứng dụng có thể cần nhiều loại tương đương:

| Chính sách | Ví dụ mong muốn | Cách tiếp cận |
| --- | --- | --- |
| **Exact code-unit equality** | Nội dung byte/code-unit của token, dấu vết xử lý phải trùng tuyệt đối | `String.equals` trên chuỗi đầu vào theo hợp đồng |
| **Canonical equality** | `é` dựng sẵn bằng `e` + combining acute | Cùng `Normalizer.Form.NFC` hoặc `NFD` rồi `equals` |
| **Case-insensitive key đơn giản** | `École` tương ứng `E\u0301COLE` | NFC + case mapping bằng `Locale.ROOT` + NFC theo policy |
| **Full Unicode caseless matching** | `Straße` và `STRASSE` có thể cần coi là tương đương | **Unicode full case folding**, không chỉ `toLowerCase` |
| **Compatibility-insensitive matching** | Full-width `Ｊａｖａ` và ASCII `Java` | Chọn `NFKC` theo policy rõ ràng |
| **Accent-insensitive search** | `cafe` tìm `café` | Search/index rule riêng, có xét ngôn ngữ |
| **Locale-aware collation** | Sắp xếp từ ngữ tự nhiên theo vùng/ngôn ngữ | `Collator` và cấu hình locale/strength |
| **Security-sensitive identifier** | Username không giả mạo nhau | Normalization + quy tắc identifier/confusable/allowlist riêng |

**Không có một normalization form nào tự thực hiện tất cả các chính sách này.** Ví dụ `NFC` không đổi `A` thành `a`; `NFKC` không giải quyết mọi ký tự nhìn giống nhau ở các hệ chữ khác nhau; `toLowerCase(Locale.ROOT)` không tương đương với full Unicode case folding.

Trước khi triển khai, xác nhận với nghiệp vụ:

1. Các dấu tiếng Việt có phải là phần bắt buộc của danh tính không? Với tên người dùng, `ma` và `má` thường **không nên** tự động coi là cùng một giá trị.
2. Phân biệt chữ hoa/thường có ý nghĩa không? Với mã nội bộ có thể chọn case-sensitive; với search UI có thể không.
3. Có muốn hợp nhất full-width, ligature, số khoanh tròn không? Đây là quyết định của **compatibility matching**, không phải chỉ “Unicode sạch”.
4. Có yêu cầu so sánh theo ngôn ngữ cụ thể không? Ví dụ tiếng Thổ Nhĩ Kỳ có quy tắc chữ `I/i` đặc biệt.
5. Chuỗi là text hiển thị, ID, token, password, path hay dữ liệu chữ ký? **Không áp dụng cùng một key function cho mọi trường**.

## 4. Pipeline thực tiễn cho exact key và search key

### 4.1. Chọn “canonical key” dựa trên NFC

Nếu yêu cầu là **khác biệt biểu diễn Unicode nhưng không khác nội dung theo chuẩn tắc**, quy tắc đơn giản:

~~~java
static String canonicalKey(String input) {
    return Normalizer.normalize(input, Normalizer.Form.NFC);
}
~~~

Đây là **snippet trong class có import `java.text.Normalizer`**. Hàm vẫn **phân biệt chữ hoa/thường**, không gộp `cafe` với `café`, không thay đổi compatibility như số khoanh tròn.

**Sử dụng nhất quán ở mọi nơi:** tạo khóa khi insert/update; tạo khóa truy vấn khi select; tạo khóa khi lookup cache; chạy cùng chính sách ở batch import và service khác. Nếu chỉ chuẩn hóa dữ liệu khi lưu mà không chuẩn hóa query, kết quả tra cứu có thể vẫn sai.

### 4.2. Search key đơn giản không phân biệt chữ hoa/thường trên Java 17+

Một ví dụ policy cho tìm kiếm **locale-independent đơn giản**:

~~~java
static String lookupKey(String value) {
    String canonical = Normalizer.normalize(
            value, Normalizer.Form.NFC);
    return Normalizer.normalize(
            canonical.toLowerCase(Locale.ROOT),
            Normalizer.Form.NFC);
}
~~~

Đây là snippet với import `java.util.Locale` và `Normalizer`. Các bước:

1. **NFC lần đầu:** đưa source về canonical form thống nhất.
2. **`toLowerCase(Locale.ROOT)`:** xử lý case theo locale trung tính, tránh kết quả bất ngờ phụ thuộc locale mặc định của máy.
3. **NFC lần nữa:** đưa kết quả case mapping quay về canonical form khi phép mapping có thể thêm hoặc biến đổi combining marks.

Ví dụ, `"École"` và `"E\u0301COLE"` có cùng key sau pipeline; nhưng `"cafe"` và `"café"` **vẫn khác key**. Đây là lựa chọn tốt cho **matching giản đơn theo sản phẩm** khi không yêu cầu full case folding hoặc collation theo ngôn ngữ.

**Giới hạn quan trọng:** `String.toLowerCase(Locale.ROOT)` **không phải Unicode full case folding**. Ví dụ `Straße` và `STRASSE` không nhất thiết có cùng key dưới pipeline này, vì lowercase không thay `ß` thành hai chữ `ss`. Nếu nghiệp vụ đòi **Unicode-compliant caseless matching** (gồm mapping 1→n), cần cơ chế full case folding như API `String.equalsFoldCase(...)` trên **Java 26+** cho so sánh trực tiếp, hoặc thư viện có chức năng casefold key phù hợp cho Java 17.

**Không chuyển bản thân display string thành lowercase nếu phải giữ cách viết người dùng.** Duy trì song song:

~~~text
display_text = "École"
lookup_key   = "école"  (NFC + lower ROOT + NFC)
~~~

Việc key có thể khác display là đúng chủ đích. Nếu sản phẩm muốn hiển thị phiên bản user nhập, cần lưu bản gốc/bản hiển thị riêng; không dùng normalized key làm nhãn UI thay thế một cách mù quáng.

### 4.3. Đừng nhầm normalize với trim hoặc làm sạch whitespace

`Normalizer.normalize(...)` **không tự xóa dấu cách đầu/cuối**, không tự thu gọn các loại whitespace, không sửa dấu câu, không transliterate từ chữ có dấu thành chữ không dấu.

Nếu policy yêu cầu loại bỏ khoảng trắng đầu/cuối, có thể thêm `strip()` ở một vị trí được xác định. Nếu yêu cầu “nhiều whitespace thành một dấu cách”, phải thiết kế quy tắc riêng cho các ký tự whitespace được phép, không mặc định `String.trim()`, `strip()` hay một regex đơn lẻ giải quyết mọi ký tự Unicode (ví dụ NBSP).

Điều đặc biệt quan trọng với dữ liệu nhạy cảm: password, token, chữ ký hoặc nội dung mà khoảng trắng là một phần giá trị **không được tự ý strip/normalize** khi hợp đồng của chúng yêu cầu so sánh nguyên văn.

## 5. Tính chất cần có của một normalization policy

Một hàm tạo khóa tốt phải đáp ứng các thuộc tính nghiệp vụ thiết yếu.

### 5.1. Deterministic và idempotent

Với cùng version/rules/inputs, một policy phải sinh cùng output. `Normalizer.normalize(s, Form.NFC)` có tính **idempotent**:

~~~java
String once = Normalizer.normalize(s, Normalizer.Form.NFC);
String twice = Normalizer.normalize(once, Normalizer.Form.NFC);
boolean same = once.equals(twice); // true
~~~

Đây là snippet với `s` không `null`. Idempotence giúp tránh một chuỗi bị đổi vô hạn qua nhiều tầng hệ thống. Mặt khác, pipeline tùy biến ghép nhiều phép biến đổi phải được **tự kiểm thử tính idempotent**, không nên suy luận tự động chỉ vì `Normalizer` có tính chất đó.

### 5.2. Không gộp hơn policy cho phép

Khi hai giá trị gốc biến thành cùng key, đó là một **collision theo chính sách**. Ví dụ `École` và `E\u0301COLE` trở thành cùng search key là mong muốn. Nhưng `①` và `1` bằng nhau sau `NFKC` có thể là **collision không mong muốn** nếu dữ liệu mang tính biểu tượng/kỹ thuật.

Vì vậy, chọn form **trước khi có dữ liệu thật**, ghi nó thành hợp đồng rõ ràng và lập test cho các cặp “phải bằng/không được bằng”.

### 5.3. Ổn định giữa các dịch vụ và thời gian

Trong môi trường nhiều service, nếu một service dùng NFC, một service dùng NFKC và một service dùng lowercase theo default locale, cùng dữ liệu sẽ tạo ra các khóa khác nhau. Cần một **policy version** được chia sẻ giữa Java backend, mobile app, batch import, công cụ di trú và các hệ thống index.

Khi thay policy, không chỉ đổi một method rồi deploy: cần xem dữ liệu cũ, unique constraints, cache keys, các hệ thống downstream và trường hợp collision. Một khóa đã lưu trong DB là **một giá trị vật lý có lịch sử**, không tự động cập nhật khi code ứng dụng thay đổi.

## 6. Một số lưu ý về ký tự Unicode và mô hình `String`

### 6.1. UTF-16 code units, code points và grapheme clusters

`String` trong Java là chuỗi UTF-16 code units. Một code point Unicode ngoài BMP có thể chiếm **hai `char`** (surrogate pair). Một biểu tượng người dùng nhìn thành một ký tự có thể gồm **nhiều code points** (chữ + combining mark hoặc emoji có sequence).

`String.length()` đếm code units; `String.codePointCount(...)` đếm code points; cả hai **không trực tiếp đếm grapheme clusters**. Normalization có thể làm thay đổi số code point và `String.length()` mà không đổi cách hiển thị trực quan.

Ví dụ `"\u00E9"` có một code point và `"e\u0301"` có hai code points, nhưng sau NFC cả hai có thể thành cùng một biểu diễn. Đừng đặt chính sách giới hạn độ dài username theo `String.length()` rồi tưởng đó luôn là “số ký tự nhìn thấy”.

### 6.2. Thứ tự combining marks

Normalization có thể **sắp xếp lại các combining marks theo canonical combining class** và/hoặc kết hợp chúng với ký tự cơ sở. Không nên tự sắp xếp dấu theo thứ tự xuất hiện, hoặc xóa dấu mà không hiểu quy tắc Unicode.

Điều này quan trọng với tiếng Việt vì nhiều nguyên âm có thể kết hợp dấu âm học (như mũ, móc, breve) với dấu thanh. `NFC` xử lý canonical equivalence đúng theo Unicode; một thuật toán “đổi bảng chữ cái” tự viết rất dễ bỏ sót trường hợp.

### 6.3. Normalization không phải phép phiên âm

NFC/NFD/NFKC/NFKD **không dịch chữ Hán thành pinyin, không đổi tiếng Việt có dấu sang tiếng Việt không dấu, không biến mọi chữ nhìn giống nhau thành ASCII**. Nếu sản phẩm cần tìm “Ha Noi” ra “Hà Nội”, phải có search rule/diacritic folding độc lập, và cần định nghĩa cách xử lý `đ/Đ`, các combining marks, tên riêng và chữ của ngôn ngữ khác.

Không xóa tất cả dấu khi lưu **khóa duy nhất** cho tên người nếu nghiệp vụ vẫn phân biệt các từ có dấu. Có thể tạo một **search-only auxiliary field** phục vụ tìm kiếm mở rộng, nhưng vẫn duy trì canonical key đủ chặt chẽ để tránh trộn các thực thể khác nhau.

## 7. Ví dụ Java 17+ hoàn chỉnh: chuẩn hóa để so sánh và tra cứu

Ví dụ sau kiểm chứng bằng code:

1. Raw `String.equals` không coi `é` dựng sẵn và `e + combining acute` là giống nhau.
2. NFC làm hai biểu diễn tương đương bằng nhau; normalize lần hai không đổi kết quả.
3. Search key dùng NFC + `Locale.ROOT` lowercase + NFC giúp hai cách viết `École` và `E\u0301COLE` tra cứu cùng một entry.
4. NFC **không** gộp ký tự Latin full-width với ASCII; NFKC có thể gộp.
5. NFKC biến số khoanh tròn thành số thường, cho thấy compatibility normalization có tính nhiều-một.
6. Accent vẫn được bảo toàn trong search key đơn giản.
7. Lowercase vẫn **khác** full Unicode case folding.

Lưu file tên **`UnicodeKeyDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class UnicodeKeyDemo {
    private static String nfc(String value) {
        return Normalizer.normalize(
                Objects.requireNonNull(value, "value"), Normalizer.Form.NFC);
    }

    public static String lookupKey(String value) {
        String canonical = nfc(value);
        return nfc(canonical.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Raw equal: " + precomposed.equals(decomposed));
        System.out.println("NFC equal: "
                + nfc(precomposed).equals(nfc(decomposed)));
        System.out.println("NFC idempotent: "
                + nfc(precomposed).equals(nfc(nfc(precomposed))));

        String title = "\u00C9cole";
        String query = "E\u0301COLE";
        System.out.println("Search keys equal: "
                + lookupKey(title).equals(lookupKey(query)));

        String wide = "\uFF2A\uFF41\uFF56\uFF41";
        System.out.println("NFC width equal: " + nfc(wide).equals("Java"));
        System.out.println("NFKC width equal: "
                + Normalizer.normalize(wide, Normalizer.Form.NFKC)
                        .equals("Java"));
        System.out.println("NFKC circled digit equals 1: "
                + Normalizer.normalize("\u2460", Normalizer.Form.NFKC)
                        .equals("1"));

        Map<String, Integer> counts = new HashMap<>();
        counts.merge(lookupKey(title), 1, Integer::sum);
        counts.merge(lookupKey(query), 1, Integer::sum);
        System.out.println("Distinct keys: " + counts.size());
        System.out.println("Matched count: "
                + counts.get(lookupKey("e\u0301cole")));

        System.out.println("Accent is preserved: "
                + !lookupKey("cafe").equals(lookupKey("caf\u00E9")));
        System.out.println("Lowercase is not full case folding: "
                + !lookupKey("Stra\u00DFe").equals(lookupKey("STRASSE")));
    }
}
~~~

Đây là chương trình **độc lập hoàn chỉnh**, không yêu cầu thư viện bên ngoài. Các literal `\uXXXX` giúp mã nguồn dễ copy và tái hiện được byte-for-byte ở môi trường editor/terminal chưa cấu hình Unicode nhất quán; Java dịch chúng thành ký tự Unicode tương ứng trong quá trình xử lý source.

Chạy trong thư mục chứa file:

~~~sh
javac --release 17 UnicodeKeyDemo.java
java UnicodeKeyDemo
~~~

**Stdout chính xác** (đã biên dịch/chạy trên JDK 24 với `--release 17`):

~~~text
Raw equal: false
NFC equal: true
NFC idempotent: true
Search keys equal: true
NFC width equal: false
NFKC width equal: true
NFKC circled digit equals 1: true
Distinct keys: 1
Matched count: 2
Accent is preserved: true
Lowercase is not full case folding: true
~~~

### 7.1. Vì sao `Distinct keys: 1`?

Hai câu lệnh:

~~~java
counts.merge(lookupKey(title), 1, Integer::sum);
counts.merge(lookupKey(query), 1, Integer::sum);
~~~

lưu vào `HashMap` theo **cùng một normalized key**, nên hai lần tăng counter chỉ tạo **một key**, tổng bằng `2`. Dòng `counts.get(lookupKey("e\u0301cole"))` tiếp tục tra cứu bằng cùng policy và nhận giá trị `2`.

Nếu dùng raw input trực tiếp làm key, hai hình thức khác nhau có thể tạo hai entry mặc dù user cho rằng đang tìm cùng một từ. Khi normalization policy thống nhất, cả insert và lookup trở nên dự đoán được.

### 7.2. Vì sao code không dùng `NFKC` cho mọi lookup?

Chương trình chủ ý chỉ demo `NFKC` **ở phép so sánh riêng**. Nếu áp dụng nó không phân biệt ngữ cảnh, cả `①` và `1` trở thành một khóa, điều có thể không phù hợp với mã sản phẩm, phiên bản tài liệu hoặc tên hiển thị. Chọn NFC cho canonical key là quyết định **bảo thủ hơn** với nhiều văn bản tự nhiên.

Nếu ứng dụng thực sự muốn compatibility-insensitive search, hãy tạo **một loại search key riêng** có ghi rõ tên policy, giới hạn miền dữ liệu và kiểm thử collision. Không “nâng cấp” mọi khóa duy nhất từ NFC sang NFKC mà không phân tích dữ liệu hiện có.

### 7.3. Vì sao vẫn dùng `Locale.ROOT`?

`String.toLowerCase()` không có tham số dùng **default locale của JVM**. Ví dụ locale tiếng Thổ Nhĩ Kỳ có mapping đặc biệt cho chữ `I`; nếu cùng dữ liệu chạy trên các server với default locale khác nhau, khóa có thể khác.

`toLowerCase(Locale.ROOT)` đặt locale trung tính cho phép **case conversion đơn giản, không phụ thuộc cấu hình người dùng**. Nhưng nó vẫn không tương đương Unicode full case folding. Nếu bài toán có yêu cầu ngôn ngữ thực sự (ví dụ search tiếng Thổ), locale cụ thể hoặc bộ máy collation thích hợp có thể đúng hơn `Locale.ROOT`.

## 8. Chọn đúng phép so sánh: `equals`, `equalsIgnoreCase`, case folding và `Collator`

### 8.1. `String.equals` sau normalization

Với canonical key cố định, `String.equals(...)` là cách kiểm tra **chính xác biểu diễn normalized key**. `HashMap`/`HashSet` dùng `equals` và `hashCode` nên hoạt động nhất quán khi chỉ đưa **key đã normalize** vào cấu trúc dữ liệu.

Không cần dùng `Collator` cho khóa hash đơn giản nếu quy tắc chỉ là canonical equivalence (NFC) cộng với lowercase được chọn rõ. Quan trọng là cả hai chuỗi được xử lý bằng **cùng function**, không chỉ một phía.

### 8.2. `equalsIgnoreCase` không thực hiện normalization

`"É".equalsIgnoreCase("e\u0301")` không phải cách đáng tin để giải quyết canonical equivalence. `equalsIgnoreCase` tập trung vào so sánh chữ hoa/thường đơn giản theo code point; **không tự đưa chuỗi về NFC/NFD**.

Ngay cả khi cả hai chuỗi được NFC, quy tắc `equalsIgnoreCase` cũng không tương đương **full Unicode case folding** với các mapping một ký tự thành nhiều ký tự. Do đó, nếu cần một key lưu trữ/lookup ổn định, hãy ghi rõ policy thay vì đặt mọi kỳ vọng vào `equalsIgnoreCase`.

### 8.3. Full case folding và Java 26+

**Java 26** bổ sung `String.equalsFoldCase(String)` và `String.compareToFoldCase(String)` cho so sánh theo **Unicode full case folding**. API hỗ trợ mapping 1→n như ký tự `ß` thành `ss` theo quy tắc Unicode.

~~~java
boolean equal = "Fu\u00DF".equalsFoldCase("FUSS"); // true trên Java 26+
~~~

Đây là **snippet dành riêng cho Java 26 trở lên**, **không** chạy với `javac --release 17`; vì vậy không nằm trong chương trình mẫu Java 17. Nếu cần canonical equivalence **và** full case folding, vẫn phải xử lý normalization như một bước được định nghĩa riêng khi cần — **case folding không thay thế mọi normalization**.

Nếu cần tạo **chuỗi key dạng full case-folded** và vẫn phải chạy Java 17, có thể dùng thư viện Unicode phù hợp, ví dụ ICU4J, với một phiên bản/contract rõ ràng. Không tự chế bảng thay ký tự Unicode vài dòng để giả làm full case folding; không thể bao phủ đầy đủ những mapping và version Unicode khác nhau một cách đáng tin.

### 8.4. `Collator` cho so sánh theo ngôn ngữ

`java.text.Collator` dùng cho **so sánh và sắp xếp văn bản tự nhiên theo locale**, khác với binary key equality:

~~~java
Collator collator = Collator.getInstance(Locale.forLanguageTag("vi"));
collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
int order = collator.compare("A", "B");
~~~

Đây là **snippet** cần import `java.text.Collator` và `java.util.Locale`. Kết quả `order` âm/dương/0 phản ánh thứ tự collation theo cấu hình. Khi muốn accent-insensitive matching, xem xét `Collator.PRIMARY` (chi tiết khác biệt ở từng mức và từng locale do collation rules quyết định), thay vì xóa dấu theo regex tùy tiện.

**`Collator` không phải mã hóa khóa lưu trữ vĩnh viễn.** `CollationKey` có thể giúp tối ưu so sánh lặp lại trong một context collation, nhưng không mặc định serialize/persist nó như ID bất biến hoặc so trực tiếp các key tạo từ **những Collator khác nhau**. Cấu hình locale/strength/decomposition và provider/runtime là một phần của hành vi cần quản lý.

Nếu index/sort trong DB dùng collation của database, đó có thể là **một hệ quy tắc khác** với Java `Collator`. Hãy bảo đảm business semantics thống nhất giữa application và DB; đặc biệt nếu dùng unique constraint dựa trên case-insensitive/accent-insensitive collation.

## 9. Chuẩn hóa trước tìm kiếm

### 9.1. Tìm kiếm exact bằng canonical key

Giả sử có dataset:

~~~text
raw_title:     "École"
canonical_key: NFC(raw_title)
search_key:    NFC(lowerRoot(NFC(raw_title)))
~~~

Khi user gửi query `E + combining acute + COLE`, áp dụng **cùng `searchKey`** cho query, rồi tra index `search_key`. Đó là mô hình dễ giải thích cho một tìm kiếm exact không phân biệt chữ hoa-thường đơn giản.

Nếu chỉ cần tìm kiếm prefix/contains, quy trình cũng cần chuẩn hóa **cả document lẫn query** trước khi áp dụng prefix/substring; tuy nhiên có những vấn đề riêng:

- Vị trí code-unit offset trong normalized string có thể khác vị trí trong raw string, nên **không dùng offset normalized để highlight UI raw text** mà không có ánh xạ vị trí.
- Tokenization tách từ phụ thuộc ngôn ngữ; NFC không tự tách từ cho mọi ngôn ngữ.
- Regex trên normalized string có thể khớp khác trên raw text do combining marks được ghép/tách.
- Độ dài normalized string có thể thay đổi; limit độ dài query cần thực hiện trên một cơ sở đo rõ ràng.

Với search toàn văn và nhiều ngôn ngữ, thường nên để search engine xây analyzer/normalizer/tokenizer của riêng nó, và **kiểm thử sự tương thích giữa analyzer của index và analyzer của query**. Không xem một phép NFC đơn lẻ là hệ thống full-text search hoàn chỉnh.

### 9.2. Tìm kiếm không phân biệt dấu là một tính năng riêng

Một sản phẩm có thể muốn query `"Ha Noi"` tìm `"Hà Nội"`. Đây **không phải** tác dụng của NFC. Cần có một secondary search index, ví dụ với chiến lược chuyển diacritics và ký tự đặc thù ngôn ngữ thành dạng so khớp được.

Một ý tưởng phổ biến là NFD rồi loại bỏ Unicode combining marks; nhưng không được tuyên bố phép đó xử lý mọi trường hợp:

- Một số chữ như `đ`/`Đ` không chỉ là “d + combining mark”, nên bỏ marks **không tự biến chúng thành `d`**.
- Xóa dấu có thể khiến hai từ khác nghĩa trong tiếng Việt thành cùng search key, làm tăng false positives.
- Nếu index là nguồn để **xác nhận duy nhất một danh tính**, accent folding quá mạnh có thể tạo collision không được phép.
- Kết quả search nên được xếp hạng và/hoặc hiển thị raw string, không thay raw display bằng folded key.

Định nghĩa rõ **search-only matching** và **identifier uniqueness** là hai mục tiêu khác nhau. Một sản phẩm có thể dùng khóa NFC+lower cho uniqueness nhưng thêm index phụ mở rộng để tìm gần đúng theo dấu.

## 10. Chuẩn hóa trước so sánh và kiểm tra điều kiện

Không chỉ tìm kiếm, normalized representation còn quan trọng khi:

- Kiểm tra một label có **trùng** với label đã tồn tại trong `Set<String>`.
- So sánh giá trị nhập từ nhiều thiết bị trước khi merge.
- Lập khóa `Map<String, Value>` trong bộ nhớ và cache.
- Kiểm tra tên import có trùng với tên trong DB.
- Dedupe file metadata/title trong công cụ xử lý tài liệu.

Mẫu so sánh canonically equivalent:

~~~java
boolean same = Normalizer.normalize(left, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(right, Normalizer.Form.NFC));
~~~

Đây là snippet với `left`/`right` là `String` khác `null`; nếu một phía có thể `null` thì cần chính sách riêng trước khi gọi normalization. Đừng “cứ normalize cả chuỗi” trong các miền cần phân biệt chính xác từng code point, ví dụ nội dung dùng trong chữ ký số hoặc khóa giao thức đã quy định byte sequence.

### 10.1. So sánh với chuỗi rỗng và null

Phải phân biệt:

- `null`: dữ liệu không có mặt.
- `""`: chuỗi rỗng hợp lệ hoặc không tùy trường.
- `" "`: chỉ có khoảng trắng ASCII.
- Các whitespace Unicode khác: có nhiều tính chất khác nhau.

`Normalizer.normalize(null, ...)` ném `NullPointerException`; không tự gán `null` thành chuỗi rỗng nếu nghiệp vụ không đồng ý. Với key duy nhất, hãy kiểm tra null/blank/length theo schema trước hoặc sau normalization theo chính sách được document, và thực hiện **kiểm tra cuối cùng trên biểu diễn chuẩn** trước khi lưu.

### 10.2. Validation trước/sau biến đổi

Một luồng xử lý an toàn thường cần:

1. Kiểm tra dữ liệu đầu vào có mặt và không vượt giới hạn tài nguyên ở mức thô.
2. Áp dụng normalization/case mapping theo đúng policy.
3. **Validate normalized value** theo tập ký tự, độ dài, định dạng, reserved words và uniqueness.
4. Lưu raw/display và canonical key nếu schema yêu cầu.
5. Đảm bảo mọi consumer dùng cùng policy.

Tại sao cần validate sau normalize? Vì phép biến đổi có thể thay đổi biểu diễn hoặc làm lộ dạng ASCII/compatibility của ký tự vốn trông khác trước. Nhưng cũng phải có **giới hạn input thô** để tránh xử lý chuỗi cực lớn trước khi kịp áp chính sách tài nguyên.

## 11. Chuẩn hóa trước lưu khóa trong database

### 11.1. Mẫu schema lưu riêng giá trị hiển thị và khóa

Ý tưởng schema độc lập loại DB:

~~~sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(256) NOT NULL,
    name_key VARCHAR(256) NOT NULL,
    UNIQUE (name_key)
);
~~~

Đây là **ví dụ SQL minh họa**, không ràng buộc hoàn toàn vào một database cụ thể. Cần chọn kiểu dữ liệu, collation, encoding, index và độ dài thực tế phù hợp với hệ quản trị. `display_name` dùng để hiển thị, `name_key` được tạo bằng **một normalization policy được version hóa**.

Ví dụ:

~~~text
display_name = "École"
name_key     = "école"
~~~

Cả create và update phải cập nhật `name_key`. Truy vấn exact cũng phải chuẩn hóa user query bằng cùng key function.

### 11.2. Unique index phải chặn collision tại database

Không chỉ kiểm tra:

~~~text
if (!exists(name_key)) insert(...)
~~~

Vì hai request đồng thời có thể cùng thấy “chưa tồn tại” và cùng insert. **Unique index/constraint ở DB** là tầng ngăn race condition sau cùng. Ứng dụng phải bắt lỗi uniqueness và chuyển thành thông báo phù hợp.

Nếu database dùng case-insensitive hoặc accent-insensitive collation, so sánh/uniqueness của DB có thể **khác** Java `String.equals` trên normalized key. Hãy kiểm tra:

- DB đang so `name_key` theo collation nào?
- Có cần **binary/code-unit-aware collation** để DB coi chính xác các key do ứng dụng phát ra hay không?
- DB và Java có đang đồng thuận về việc gộp chữ hoa, dấu và compatibility không?
- Input được stored/encoded bằng charset nào (thường UTF-8 tại DB, nhưng cần xác nhận)?
- Index có giới hạn length tính theo byte khác với Java code unit không?

Đừng xem `UNIQUE(name_key)` tự nhiên là “unique theo chính sách Java”; điều đó còn phụ thuộc collation và cấu hình DB.

### 11.3. Không dùng normalized display text làm ID bất biến nếu chưa cân nhắc

Nếu `name_key` là **business lookup key**, có thể thay khi đổi tên hoặc policy. Một row ID ổn định (UUID/numeric ID) thường phù hợp hơn cho foreign keys, audit trail và URL nội bộ. Dùng normalized name để lookup, nhưng dùng immutable ID làm identity của thực thể khi cần bền vững qua thời gian.

Đối với các giá trị vốn đã là ID ASCII theo giao thức (UUID chuẩn, mã máy đọc có quy tắc riêng), **không thêm Unicode normalization tùy ý** chỉ vì công cụ hỗ trợ. Mỗi loại ID phải theo đúng specification của miền đó.

## 12. Đổi normalization policy khi hệ thống đã có dữ liệu

Giả sử hệ thống ban đầu lưu raw title; sau đó muốn chuyển sang `NFC + toLowerCase(Locale.ROOT) + NFC`. Đây là **migration dữ liệu và hợp đồng nghiệp vụ**, không chỉ là refactor một hàm.

Quy trình an toàn:

1. **Đóng băng policy version mới** (ví dụ `lookup-v2`), mô tả chính xác form, locale, case mapping, whitespace, length và điều kiện validation.
2. **Tính key mới cho toàn bộ dữ liệu hiện có** trong một bảng staging/column mới; không ghi đè display text nếu chưa được cho phép.
3. **Nhóm collision theo key mới**. Ví dụ hai tên đã tồn tại ở dạng composed/decomposed hoặc khác case có thể giờ trở thành một key.
4. **Giải quyết collision bằng quyết định nghiệp vụ**: merge, đổi alias, từ chối một tài khoản, hoặc giữ ngoại lệ. Không tự chọn bản ghi “đầu tiên” khi đây là danh tính người dùng.
5. **Dual-read hoặc cutover có kiểm soát** trong giai đoạn triển khai: tránh service dùng key v1 và service khác dùng key v2 gây lookup không nhất quán.
6. **Tạo unique index đúng collation** sau khi dữ liệu đã được reconcile; chạy migration trong transaction/batch phù hợp với DB.
7. **Cập nhật cache, search index, message consumer và batch job**; có cơ chế rollback/redirect nếu key cũ đã xuất hiện trong đường dẫn hoặc integration.
8. **Quan sát metrics:** số collision, lỗi uniqueness, mismatch lookup, số bản ghi chưa được index lại.

Nếu chỉ chạy normalization ở middleware mới mà không reindex dữ liệu cũ, các query mới có thể không tìm được key lưu theo chính sách cũ. Cũng không nên xóa key cũ trước khi xác minh những hệ thống downstream không còn tham chiếu nó.

## 13. Bảo mật: Unicode normalization giúp giảm nhập nhằng nhưng không chống giả mạo đầy đủ

Normalization hữu ích để loại bớt **một loại biểu diễn tương đương**. Tuy nhiên nó **không phát hiện mọi ký tự trông giống nhau**:

- Latin `a` và một ký tự tương tự thuộc hệ chữ khác vẫn có thể là **code point khác nhau** và không được NFC gộp.
- Chữ hoa/thường, chữ có dấu, compatibility characters có thể có semantics riêng.
- Chuỗi có bidirectional controls, zero-width characters hoặc combining marks bất thường cần **validation hiển thị/identifier** theo miền dữ liệu.
- Ký tự nhìn giống nhau xuyên các script được xử lý bằng chính sách **confusable detection/identifier restriction** theo các chuẩn liên quan như Unicode Security Mechanisms (UTS #39), không phải bằng Normalizer đơn độc.

Với username, tên miền, identifier truy cập hoặc khóa ủy quyền:

1. Xác định tập ký tự/script được phép và chuẩn hóa **trước validation cuối**.
2. Kiểm tra collision/đồng nhất theo chính sách canonical key.
3. Nếu cần chống mạo danh, bổ sung kiểm tra confusable và các quy tắc identifier phù hợp.
4. Hiển thị giá trị gốc hợp lý để người dùng có thể nhận biết những ký tự bất thường; có thể cảnh báo các tên gần giống nhau.
5. Không dùng kết quả normalization làm bằng chứng một nội dung đã được xác thực.

**Không tự ý normalize password, cryptographic token, chữ ký số, hash input, URL canonicalization hay IDN/domain name** nếu chuẩn giao thức không cho phép. Với URL và tên miền, phải áp dụng đúng quy tắc của thành phần đó (ví dụ IDNA cho domain), không thay bằng “`Normalizer.NFKC` rồi lưu”.

## 14. Version Unicode, JDK và tính tái lập

`Normalizer` của JDK dựa trên Unicode normalization rules; thuộc tính Unicode và **case mapping** mà runtime hỗ trợ phụ thuộc vào phiên bản Unicode của JDK. Các hệ thống đồng thời chạy nhiều JDK hoặc nhiều thư viện Unicode có thể có sự khác biệt ở các ký tự mới được đưa vào các phiên bản Unicode sau này.

Unicode có các bảo đảm ổn định normalization cho những dữ liệu đã được định nghĩa, nhưng không nên suy ra rằng **mọi phép lower/case fold, collation, tokenization và phân loại ký tự** bất biến giữa mọi JDK và provider. Đặc biệt:

- `toLowerCase(Locale.ROOT)` dựa trên Unicode case mappings được runtime hỗ trợ.
- `Collator` có thể chịu ảnh hưởng của provider/CLDR, locale và cấu hình strength/decomposition.
- Một service dùng ICU4J có thể không dùng chính xác cùng version dữ liệu Unicode với JDK khác.
- Những feature mới như `String.equalsFoldCase` chỉ có từ Java 26; code Java 17 phải dùng API tương thích hoặc thư viện có chính sách rõ ràng.

Với key đã persist, **ghi lại policy version** và kiểm thử golden cases trên phiên bản JDK/DB/search engine được triển khai. Nếu thay runtime có thể ảnh hưởng key, hãy chạy test và chuẩn bị kế hoạch reindex/migration trước khi cutover.

### 14.1. Ví dụ test matrix cần có

| Nhóm | Cặp dữ liệu | Mong đợi theo NFC + lowercase ROOT + NFC |
| --- | --- | --- |
| Canonical equivalent | `é` và `e\u0301` | Cùng key |
| Case đơn giản | `École` và `E\u0301COLE` | Cùng key |
| Dấu tiếng Việt | `ma` và `má` | **Khác** key |
| Compatibility width | Full-width `Ｊａｖａ` và `Java` | **Khác** key |
| Compatibility symbol | `①` và `1` | **Khác** key |
| Full case folding | `Straße` và `STRASSE` | **Khác** key với policy đơn giản này |
| Null | `null` | Reject hoặc xử lý theo schema, không truyền vô điều kiện vào Normalizer |
| Empty | `""` | Xác định rõ có được dùng làm key không |
| Combining order | Các dấu Unicode có thứ tự canonical tương đương | Cùng key sau NFC |
| Supplementary characters | Ký tự ngoài BMP | Không cắt giữa surrogate pairs; bảo toàn theo rules |
| Nhiều JDK/service | Cùng input chạy ở các bản triển khai | Test golden output trước release |

Đây là **test contract của chính sách ví dụ**, không phải một định nghĩa “mọi chuỗi Unicode cần phải được coi giống nhau” cho mọi ứng dụng.

## 15. Hiệu năng, cache và xử lý khối lượng lớn

`Normalizer.normalize(...)` tốn công việc CPU và có thể tạo chuỗi mới. Trong hệ thống tìm kiếm hoặc import lượng lớn:

- **Normalize khi đi vào pipeline**, lưu key trong index; tránh normalize lại toàn bộ document mỗi lần query.
- Truy vấn chỉ normalize **input truy vấn** và tra key đã được index.
- Dùng `Normalizer.isNormalized(s, Form.NFC)` nếu phép kiểm tra có ý nghĩa trong workload cụ thể; **đừng giả định luôn nhanh hơn gọi normalize** mà không benchmark.
- Tránh normalize cùng chuỗi hàng trăm lần trong một request; cache key ở scope phù hợp hoặc truyền key theo dữ liệu đã chuẩn hóa.
- Đừng cache vô hạn mọi chuỗi user nhập; tính toán lợi ích so với RAM/GC và privacy.
- Giới hạn kích thước input và tổng ngân sách xử lý trước khi normalization để tránh input dài gây tiêu thụ tài nguyên không kiểm soát.
- Với batch migration, log collision và progress theo ID; không giữ mọi raw string/normalized key đồng thời trong memory nếu dữ liệu quá lớn.

Không tối ưu bằng cách tự viết quy tắc Unicode rút gọn nếu chưa đo và chưa hiểu chuẩn. Chi phí bug đồng nhất dữ liệu thường lớn hơn phần CPU tiết kiệm được.

## 16. Những lỗi hay gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `String.equals` trên raw Unicode và tưởng đúng canonical equality | Bỏ sót các cặp composed/decomposed | NFC/NFD ở **cả hai vế** |
| Chỉ chuẩn hóa khi lưu, không chuẩn hóa query | Lookup miss | Một key function dùng xuyên cả insert/query/cache |
| Dùng `NFKC` cho mọi text | Mất khác biệt compatibility mà nghiệp vụ cần giữ | Chọn policy theo field; NFC cho text tổng quát |
| Nghĩ NFC chuyển chữ hoa thành chữ thường | Case mismatch | Case policy riêng |
| Nghĩ `toLowerCase(Locale.ROOT)` là full case folding | Bỏ sót mapping như `ß` ↔ `ss` | Full case-fold API/library nếu cần |
| Dùng `toLowerCase()` không locale trong khóa đa môi trường | Khóa khác nhau theo default locale | `Locale.ROOT` hoặc locale được xác định |
| Xóa mọi dấu để làm unique username | Collision, gộp tên khác nghĩa | Giữ canonical key chặt; accent-insensitive ở search index phụ |
| Dùng Java `Collator` rồi tin rằng DB unique index cùng logic | Dữ liệu trùng/mismatch giữa tầng | Kiểm thử DB collation, index và policy |
| Dùng normalized offset để highlight raw text | Vị trí ký tự sai | Mapping offset/index UI thích hợp |
| Sửa policy không migration dữ liệu | Key cũ và key mới không cùng miền | Policy version, collision audit, reindex |
| Tin Normalizer phát hiện homoglyph/confusable | Nguy cơ giả mạo identifier | Unicode security controls riêng |
| Normalize password/token/hash input tùy tiện | Thay đổi bí mật hoặc sai chữ ký | Giữ đúng semantics của giao thức |
| Dùng API Java 26 trong build `--release 17` | Compile fail | Phân biệt rõ API theo mức Java |
| So `String.length()` với số ký tự người nhìn thấy | Giới hạn độ dài sai | Chọn code units/code points/graphemes theo yêu cầu |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng nhập `é` dựng sẵn, còn DB lưu `e + combining acute`. Chỉ gọi `String.equals` có đủ không?

**Đáp:** Không. Hai chuỗi có code units khác nhau. Nếu nghiệp vụ muốn canonical equality, hãy áp dụng `Normalizer.normalize(..., NFC)` cho cả lúc ghi key và lúc lookup.

**Câu 2.** Khi nào có thể cân nhắc `NFKC` thay `NFC`?

**Đáp:** Khi miền dữ liệu **chủ ý** muốn gộp các compatibility distinctions, chẳng hạn một loại identifier/search key đã quy định rõ. Không chọn NFKC cho toàn bộ văn bản tự nhiên hoặc dữ liệu hiển thị mà chưa kiểm tra collision.

**Câu 3.** `toLowerCase(Locale.ROOT)` có biến mọi chuỗi Unicode thành case-folded key đầy đủ không?

**Đáp:** Không. Nó là locale-neutral lowercase, không phải full case folding. Từ Java 26 có `String.equalsFoldCase(...)` cho so sánh full case-folded; Java 17 cần giải pháp/library riêng nếu cần chính sách đó.

**Câu 4.** Muốn query `"Ha Noi"` tìm `"Hà Nội"`, chỉ dùng NFC là đủ?

**Đáp:** Không. Canonical normalization bảo toàn sự khác biệt dấu có nghĩa. Cần search rule riêng có thể hỗ trợ accent-insensitive matching và tránh dùng key mở rộng ấy làm định danh duy nhất.

**Câu 5.** Có thể lưu `CollationKey` như ID bất biến dùng trên mọi JDK/locale không?

**Đáp:** Không nên. Collation depends on locale, provider và configuration. Dùng `Collator` cho so sánh/sắp xếp theo ngôn ngữ; identity storage phải có policy rõ ràng và được kiểm thử.

**Câu 6.** Đổi key policy từ NFC sang NFKC khi đang có dữ liệu cần làm gì?

**Đáp:** Tính lại key, phát hiện collision, giải quyết dữ liệu trùng, kiểm tra unique constraints và collation, reindex, cập nhật mọi consumer, cutover/rollback có kiểm soát.

**Câu 7.** Normalization có làm mất hoàn toàn rủi ro tên người dùng trông giống nhau nhưng có code points khác nhau?

**Đáp:** Không. Confusables giữa script, ký tự ẩn và các vấn đề Unicode security khác cần quy tắc identifier/validation chuyên biệt; NFC/NFKC không đủ.

**Câu 8.** Tại sao ví dụ sử dụng thêm `NFC` sau lowercase?

**Đáp:** Case mapping có thể thay đổi các code points/combining marks; NFC lần cuối giúp đầu ra key tuân thủ canonical form đã chọn. Toàn bộ pipeline phải được áp dụng giống nhau khi insert và lookup.

**Ghi nhớ:** **Chuẩn hóa Unicode phải được thực hiện theo một policy cụ thể trước khi tìm kiếm, so sánh hoặc lưu khóa**. Với văn bản tự nhiên, **NFC là lựa chọn mặc định thực dụng**; với tìm kiếm không phân biệt case đơn giản trên Java 17+, có thể dùng **NFC → lowercase `Locale.ROOT` → NFC**, nhưng đó **không phải full case folding**. Phân biệt canonical/compatibility, accent/case, locale-aware collation và identifier security; lưu key tách display text, kiểm soát unique collision và version hóa policy khi dữ liệu đã tồn tại.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — java.text.Normalizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized`, NFC/NFD/NFKC/NFKD.
- [Oracle Java SE 26 — String](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): `equals`, `equalsIgnoreCase`, `toLowerCase(Locale)`, `equalsFoldCase` (Java 26+).
- [Oracle Java SE 26 — java.text.Collator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Collator.html): locale-aware comparison, strength, decomposition và `CollationKey`.
- [Unicode Consortium — UAX #15: Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): đặc tả normalization hiện hành.
- [Unicode Consortium — Normalization FAQ](https://www.unicode.org/faq/normalization.html): so sánh canonical/compatibility và chọn form phù hợp.
- [Unicode Consortium — Unicode Security Mechanisms (UTS #39)](https://www.unicode.org/reports/tr39/): các cơ chế bổ sung cho identifier/confusable security.
