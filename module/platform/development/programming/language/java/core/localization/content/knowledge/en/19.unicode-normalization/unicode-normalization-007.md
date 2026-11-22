# Giữ dữ liệu gốc khi phép biến đổi Unicode làm mất thông tin

## 1. Vấn đề: chuẩn hóa hữu ích nhưng không luôn đảo ngược được

Trong ứng dụng Java đa ngôn ngữ, chúng ta thường muốn chuẩn hóa văn bản trước khi tìm kiếm, so sánh hoặc lập chỉ mục. Các ví dụ quen thuộc:

- Chuỗi `e\u0301` (chữ e + dấu sắc kết hợp) và `é` (U+00E9) có thể về cùng một biểu diễn NFC.
- Ký tự `①` có thể trở thành `1` sau NFKC.
- Chữ fullwidth `ＡＢＣ` có thể trở thành `ABC` sau NFKC.
- `Café` và `Cafe` có thể cùng thành `cafe` nếu một khóa tìm kiếm được hạ chữ thường và bỏ dấu.

Các biến đổi đó có thể tốt cho **so khớp**, nhưng nếu thay thế luôn văn bản gốc trong cơ sở dữ liệu thì ứng dụng có thể không còn biết người dùng đã thực sự nhập gì. Từ kết quả `"1"` sau NFKC, không thể suy ra nguồn từng là `"1"` hay `"①"`.

**Nguyên tắc xuyên suốt:** giữ **dữ liệu gốc** (original) riêng với **dữ liệu dẫn xuất đã biến đổi** (normalized/index/search key). Khi phép biến đổi nhiều-đến-một, dữ liệu dẫn xuất không đủ để tái lập nguyên văn.

Bài này giải thích tính mất thông tin của các phép biến đổi Unicode, cách dùng `java.text.Normalizer` trong Java 17+, các ví dụ code chạy được, thiết kế model lưu original, xử lý va chạm sau chuẩn hóa, version hóa chỉ mục và kiểm thử.

## 2. Ba dạng dữ liệu cần phân biệt

| Trường | Mục đích | Ví dụ |
| --- | --- | --- |
| `originalText` | Văn bản được nhập/tiếp nhận theo hợp đồng nguồn | `①` |
| `normalizedText` | Biểu diễn sau một form chuẩn hóa cụ thể | `1` sau NFKC |
| `searchKey` | Giá trị dùng để tìm kiếm, có thể gồm nhiều bước | `abc` từ `ＡＢＣ` sau NFKC + lowercase |

Một bản ghi minh họa:

~~~text
recordId:       1007
originalText:   ①
searchKey:      1
searchRule:     nfkc-lower-root-v1
~~~

Ở đây, ID định danh bản ghi; original dành cho hiển thị và lưu trữ nội dung; searchKey dành cho tra cứu. `searchRule` cho biết thuật toán và phiên bản đã tạo khóa đó.

**Không coi searchKey là dữ liệu gốc**, kể cả khi nhìn bề ngoài hai chuỗi đôi lúc giống nhau. Cũng không mặc nhiên coi searchKey là khóa duy nhất: nhiều đầu vào khác nhau có thể cho cùng một đầu ra.

## 3. Vì sao biến đổi không đơn ánh gây mất thông tin?

Một hàm `f` có thể được đảo ngược duy nhất trên tập đầu vào nếu các giá trị đầu vào khác nhau không bị gộp thành một giá trị đầu ra. Ngược lại, khi có `x != y` nhưng `f(x) == f(y)`, việc biết đầu ra không đủ để tìm lại đầu vào.

Với NFKC:

~~~text
NFKC("①") = "1"
NFKC("1") = "1"
~~~

Với một pipeline bỏ dấu và chữ hoa:

~~~text
key("Café") = "cafe"
key("Cafe") = "cafe"
key("CAFE") = "cafe"
~~~

Cả ba đầu vào có thể có ý nghĩa hoặc hình thức mong muốn khác nhau. Nếu chỉ giữ `"cafe"`, không có hàm nghịch đảo xác định duy nhất để phục hồi cách người dùng đã viết.

Tính “mất thông tin” phụ thuộc mục tiêu. Nếu một hệ thống cố ý định nghĩa tất cả các biến thể là cùng username, việc gộp có thể được cho phép theo chính sách. Nhưng nếu phải tái hiện tên hiển thị, nội dung văn bản, bằng chứng hoặc tệp gốc, thì không thể lặng lẽ ghi đè nguồn.

## 4. NFC và NFD: tương đương chuẩn tắc không có nghĩa giống hệt raw

Unicode có thể biểu diễn một số chữ cùng hình thức theo nhiều dãy code point. Ví dụ chữ `é`:

~~~text
Dựng sẵn:   U+00E9
Phân rã:    U+0065 U+0301
~~~

Trong Java, hai chuỗi này có thể nhìn như một chữ nhưng khác nhau về cấu trúc:

- `String.equals` trả false trước khi normalize.
- `String.length()` lần lượt là 1 và 2 UTF-16 code unit.
- Khi encode UTF-8, chúng lần lượt dài 2 và 3 byte.
- `Normalizer.normalize(..., Normalizer.Form.NFC)` có thể đưa cả hai về cùng biểu diễn dựng sẵn.

`NFC` bảo toàn **tương đương chuẩn tắc** của văn bản Unicode, nhưng không bảo toàn **cách biểu diễn gốc**. Khi mất bản đầu vào, chuỗi NFC không cho biết nó đến từ một code point dựng sẵn hay từ chữ cơ sở cộng dấu kết hợp.

`NFD` phân rã chuẩn tắc, cũng không lưu dấu vết dãy code point ban đầu. Nói “NFC/NFD không mất thông tin” chỉ hợp lý nếu điều muốn giữ là **quan hệ tương đương chuẩn tắc**, không phải **chuỗi code unit hoặc bytes ban đầu**.

Nếu hợp đồng yêu cầu chứng minh bytes nguồn hoàn toàn không thay đổi, cần lưu chính bytes đó (cùng encoding/metadata cần thiết) trước khi decode/normalize. Một Java `String` đã decode thường không thể tái hiện mọi chi tiết BOM, encoding hoặc byte sequence lỗi của nguồn.

## 5. NFKC/NFKD còn có ánh xạ tương thích

Java cung cấp bốn `Normalizer.Form`:

| Form | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `NFC` | Canonical composition | Các biểu diễn tương đương chuẩn tắc được chuẩn hóa |
| `NFD` | Canonical decomposition | Phân rã chuẩn tắc |
| `NFKC` | Compatibility composition | Có thể gộp những ký tự có biểu diễn tương thích |
| `NFKD` | Compatibility decomposition | Phân rã cả các tương thích theo quy tắc Unicode |

Ví dụ:

~~~text
NFKC("①")   -> "1"
NFKC("ＡＢＣ") -> "ABC"
NFC("①")    -> "①"
~~~

Vì NFKC xử lý thêm compatibility mappings, nó có thể rất hữu ích cho chỉ mục tìm kiếm hoặc một số loại định danh, nhưng không phải “NFC tốt hơn” để áp dụng tùy tiện trên mọi dữ liệu nguồn.

Nếu người dùng cố tình dùng `①` trong bài viết hoặc fullwidth trong nhãn sản phẩm, biến đổi NFKC trên trường gốc sẽ thay đổi hình thức. Một hệ thống cần bảo toàn dữ liệu tác giả không nên làm như vậy chỉ vì thuận tiện cho tìm kiếm.

## 6. Java 17+: chứng minh biến đổi có va chạm

Tạo file `NormalizationCollisionDemo.java`:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

public class NormalizationCollisionDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equal raw="
                + composed.equals(decomposed));

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("equal NFC="
                + nfcA.equals(nfcB));
        System.out.println("raw lengths="
                + composed.length() + ","
                + decomposed.length());
        System.out.println("raw bytes="
                + composed.getBytes(StandardCharsets.UTF_8).length
                + ","
                + decomposed.getBytes(StandardCharsets.UTF_8).length);

        String circled = "\u2460";
        System.out.println("circled NFC="
                + Normalizer.normalize(circled, Normalizer.Form.NFC));
        System.out.println("circled NFKC="
                + Normalizer.normalize(circled, Normalizer.Form.NFKC));

        String fullwidth = "\uFF21\uFF22\uFF23";
        System.out.println("full NFKC="
                + Normalizer.normalize(fullwidth, Normalizer.Form.NFKC));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NormalizationCollisionDemo.java
java NormalizationCollisionDemo
~~~

Stdout đã đối chiếu với JVM:

~~~text
equal raw=false
equal NFC=true
raw lengths=1,2
raw bytes=2,3
circled NFC=①
circled NFKC=1
full NFKC=ABC
~~~

Kết quả đầu tiên cho thấy `String.equals` đang so sánh giá trị chuỗi Java trước chuẩn hóa, khác với phép kiểm tra tương đương chuẩn tắc. Hai chuỗi trở nên giống nhau dưới NFC nhưng bản NFC **không cho biết độ dài và cách viết Unicode của bản gốc**.

Ví dụ `①` và `ＡＢＣ` cho thấy NFKC có thể tạo ra các biểu diễn khác hẳn hình thức đầu vào. Nếu giao diện phải hiện nguyên nội dung do người dùng nhập, hãy đọc từ original, không phải từ bản NFKC.

## 7. Không chỉ normalization: lowercase, bỏ dấu, gộp khoảng trắng

Các bước khác thường xuất hiện trong một pipeline tìm kiếm:

- **Lowercasing:** `ABC` và `abc` cùng thành `abc`.
- **Case folding:** các quy tắc Unicode phục vụ caseless matching, không hoàn toàn đồng nghĩa `String.toLowerCase`.
- **Bỏ dấu:** dùng NFD rồi xóa combining marks theo chính sách tìm kiếm; `Café` và `Cafe` có thể cùng khóa.
- **Gộp whitespace:** khác biệt giữa một và nhiều dấu cách, dấu xuống dòng hoặc tab có thể biến mất.
- **Loại punctuation:** mã, tên hoặc văn bản có dấu câu khác nhau có thể trở thành cùng một khóa.
- **Transliteration:** chuyển chữ từ script này sang script khác có thể gộp nhiều cách viết.

Đừng gọi tất cả những thao tác này là “Unicode normalization”. NFC/NFD/NFKC/NFKD là những form Unicode cụ thể; các bước xóa dấu, đổi chữ, xóa khoảng trắng hoặc dịch âm cần có **hợp đồng riêng** và có thể mang ý nghĩa ngôn ngữ khác nhau.

**Ví dụ ngữ cảnh ngôn ngữ:**

- `"Straße".toUpperCase(Locale.ROOT)` có thể tạo `"STRASSE"`. Việc chuyển đổi này không hứa bảo tồn cách viết gốc.
- `"I".toLowerCase(Locale.forLanguageTag("tr-TR"))` thành chữ `ı` (dotless i) theo quy tắc Thổ Nhĩ Kỳ. Một chiến lược `Locale.ROOT` có thể cho khóa kỹ thuật ổn định, nhưng không tự nhiên cho mọi trường hợp tìm kiếm ngôn ngữ.
- `"Café"` sau NFD và xóa `\\p{M}` cho `"Cafe"`. Đây là bước *diacritic stripping*, không phải tác dụng mặc định của NFD.

Với tiếng Việt, dấu phụ/âm điệu có thể phân biệt nhiều từ và tên; bỏ dấu thường chỉ nên làm trên **khóa truy vấn hoặc chỉ mục** khi có yêu cầu tìm kiếm không dấu, không làm trên bản hiển thị.

## 8. Thiết kế record giữ original và searchKey

Một mô hình đơn giản sử dụng Java `record` để giữ hai trường tách biệt. Trong ví dụ, khóa tìm kiếm dùng NFKC và lowercase với `Locale.ROOT`; đây là **một chính sách ví dụ**, không phải quy tắc bắt buộc cho mọi ngôn ngữ.

Tạo `OriginalAndKeyDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public class OriginalAndKeyDemo {
    record TextEntry(String original, String searchKey) {
        static TextEntry from(String original) {
            Objects.requireNonNull(original, "original");
            String key = Normalizer.normalize(
                    original, Normalizer.Form.NFKC)
                    .toLowerCase(Locale.ROOT);
            return new TextEntry(original, key);
        }
    }

    public static void main(String[] args) {
        TextEntry a = TextEntry.from("\u2460");
        TextEntry b = TextEntry.from("1");

        System.out.println("sameKey="
                + a.searchKey().equals(b.searchKey()));
        System.out.println("rawEqual="
                + a.original().equals(b.original()));
        System.out.println("a=" + a.original()
                + "|" + a.searchKey());
        System.out.println("b=" + b.original()
                + "|" + b.searchKey());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OriginalAndKeyDemo.java
java OriginalAndKeyDemo
~~~

Stdout:

~~~text
sameKey=true
rawEqual=false
a=①|1
b=1|1
~~~

`TextEntry` giữ **hai giá trị khác nhau** dù chỉ mục tra cứu trùng nhau. Khi cần hiển thị nhãn đã nhập, dùng `original()`; khi cần tra cứu theo chính sách đã định, dùng `searchKey()`.

Java `record` và `String` immutable thuận tiện cho mô hình dữ liệu này, nhưng tính toàn vẹn lưu trữ vẫn cần được kiểm soát ở database/service. Khi original thay đổi có chủ đích, khóa dẫn xuất phải được tính lại tương ứng.

## 9. Cùng một searchKey có thể trỏ tới nhiều original

Ví dụ một chỉ mục tìm kiếm không nên tự động mất các giá trị gốc khác nhau:

~~~text
original   normalized key
①          1
1          1
ＡＢＣ      abc
ABC        abc
~~~

Tạo `SearchIndexCollisionDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class SearchIndexCollisionDemo {
    static String searchKey(String original) {
        return Normalizer.normalize(
                original, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Map<String, List<String>> index =
                new LinkedHashMap<>();

        List<String> originals = List.of(
                "\u2460", "1", "\uFF21\uFF22\uFF23", "ABC");

        for (String original : originals) {
            String key = searchKey(original);
            index.computeIfAbsent(key,
                    k -> new ArrayList<>()).add(original);
        }

        System.out.println("1 matches="
                + index.get("1").size());
        System.out.println("abc matches="
                + index.get("abc").size());
        System.out.println("first raw="
                + index.get("1").get(0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SearchIndexCollisionDemo.java
java SearchIndexCollisionDemo
~~~

Stdout:

~~~text
1 matches=2
abc matches=2
first raw=①
~~~

Trong ví dụ, một searchKey có thể chứa **danh sách các nguồn**. Với hệ thống lớn, nên cho chỉ mục trỏ đến các `recordId` thay vì lưu nhân bản văn bản gốc ở nhiều nơi.

**Không đặt unique constraint theo searchKey một cách tự động.** Chỉ làm vậy khi sản phẩm **cố ý** định nghĩa các giá trị cùng khóa chuẩn hóa thuộc một định danh duy nhất, ví dụ một chính sách username được công bố rõ. Dù có quy tắc unique, nếu muốn giữ hình thức hiển thị do người dùng chọn, vẫn cần trường riêng cho bản gốc.

## 10. Khi nào được phép chỉnh sửa bản gốc?

Một số hệ thống định nghĩa đầu vào **phải** tuân theo canonical form:

- Mã định danh kỹ thuật chỉ gồm ASCII lowercase.
- Một giao thức yêu cầu chuẩn hóa cụ thể trước khi ký hoặc lưu.
- Username có quy tắc không phân biệt một số ký tự, được công bố trước.
- Một trường do hệ thống sinh ra, không phải văn bản tự do của người dùng.

Khi ấy, chuẩn hóa lúc nhận có thể là một phần **hợp đồng dữ liệu chính thức**, chứ không phải lỗi. Nhưng phải nêu rõ:

1. Những biến đổi nào được phép, ví dụ NFC hay NFKC.
2. Trường đó dùng để hiển thị, định danh hay chỉ tìm kiếm?
3. Người dùng có được xem và chấp nhận kết quả thay đổi không?
4. Có cần audit hoặc bản gốc theo chính sách lưu trữ không?
5. Có tình huống va chạm cần từ chối hoặc yêu cầu đổi tên không?

Sự khác biệt là **biến đổi có chủ đích theo hợp đồng** so với **thay đổi ngầm dữ liệu không được phép mất**. Không bắt buộc mọi trường phải lưu raw mãi mãi; nhưng trường cần bảo toàn thì không được chỉ lưu bản dẫn xuất.

## 11. Pipeline lưu trữ an toàn

Một luồng xử lý rõ ràng:

~~~text
Nguồn nhập (text hoặc bytes)
          |
          v
Decode + validation theo hợp đồng
          |
          +----> original được bảo toàn
          |
          +----> normalize theo mục đích
                    |
                    v
               case handling
                    |
                    v
               searchKey + ruleVersion
~~~

Khi người dùng yêu cầu tìm kiếm:

1. Tạo khóa truy vấn theo **chính sách tương ứng với index**.
2. Tra cứu khóa có thể khớp nhiều bản ghi.
3. Trả về ID và **original** để hiển thị.
4. Nếu người dùng sửa bản gốc, cập nhật original và mọi derived fields trong cùng một thao tác nhất quán.

Đây là ví dụ schema tối thiểu:

~~~text
id              PRIMARY KEY
original_text   TEXT
search_key      TEXT
key_version     TEXT
~~~

Nếu doanh nghiệp cần lưu bytes y nguyên tệp tải lên, có thể cần một trường/blob/file lưu dữ liệu bytes gốc và metadata encoding. Một Java `String` không thay thế yêu cầu lưu byte-level provenance.

Không xây dựng SQL bằng cách nối trực tiếp giá trị original/searchKey. Dùng prepared statements và cơ chế encoding/escaping đầu ra thích hợp; normalization không phải giải pháp SQL injection/XSS.

## 12. Version hóa pipeline để dựng lại chỉ mục

Quy tắc tạo khóa tìm kiếm có thể thay đổi theo thời gian:

- Chuyển từ NFC sang NFKC hoặc ngược lại.
- Thêm/bỏ diacritic stripping.
- Đổi cách case handling.
- Cập nhật thư viện i18n, Unicode data hoặc locale provider.
- Đổi quy tắc về khoảng trắng, dấu câu, kết hợp script.

Ghi một phiên bản rõ ràng, ví dụ `"nfkc-lower-root-v1"`. Khi chuyển sang `v2`, tổ chức triển khai có thể:

1. Giữ original **không thay đổi**.
2. Recompute khóa mới từ original, không từ khóa v1.
3. Phát hiện các cặp bản ghi vừa mới va chạm.
4. Xây lại chỉ mục và chạy regression tests.
5. Chuyển truy vấn sang index v2 theo kế hoạch.
6. Có phương án quay lại index v1 khi cần.

Nếu chỉ có khóa v1, nhiều phân biệt nguồn đã bị gộp và không thể dựng đầy đủ khóa v2. Đây là một lợi ích lớn của việc giữ dữ liệu gốc: **khả năng đổi thuật toán** mà không phá hủy nội dung.

## 13. Hash và chứng minh tính toàn vẹn

Hai chuỗi có thể tương đương chuẩn tắc nhưng khác byte UTF-8:

~~~text
"é" dạng U+00E9       -> C3 A9
"e\u0301"              -> 65 CC 81
~~~

Nếu hash trên **bytes gốc**, kết quả thông thường sẽ khác. Nếu trước khi hash bạn chuẩn hóa cả hai về NFC rồi encode, chúng có thể tạo **cùng bytes sau chuẩn hóa** và vì vậy cùng hash.

Ba mục tiêu phải tách:

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Bytes nguồn còn nguyên không? | Hash/so sánh đúng **bytes nguồn đã lưu** |
| Hai văn bản tương đương chuẩn tắc không? | Chuẩn hóa NFC/NFD theo hợp đồng rồi so sánh |
| Hai bản ghi khớp theo tìm kiếm không dấu/không phân biệt hoa? | Áp dụng riêng **search rule** |

**Không dùng hash của bản normalized để chứng minh raw bytes không đổi.** Với chữ ký số, thứ tự canonicalization, encoding, byte serialization và phạm vi dữ liệu ký phải theo chuẩn giao thức; không tự chuẩn hóa trước khi kiểm tra chữ ký trên dữ liệu gốc.

## 14. Dữ liệu không hợp lệ và chính sách decode

Java `String` dùng các code unit UTF-16; về mặt kỹ thuật nó có thể chứa surrogate đứng lẻ. Dữ liệu bytes đầu vào cũng có thể chứa chuỗi UTF-8 lỗi. Các decoder/encoder có những chế độ báo lỗi hoặc thay ký tự; nếu dữ liệu bị thay trước khi lưu, `String` mới có thể không cho phép khôi phục nguồn bytes.

Vì vậy cần xác định “original” là gì:

- **Chuỗi ký tự hợp lệ đã decode**, nếu hợp đồng nguồn là dữ liệu Unicode text.
- **Bytes và charset gốc**, nếu yêu cầu tái xuất tệp/kiểm tra chữ ký hoặc bảo toàn byte-for-byte.
- **Giá trị đã được người dùng xác nhận sau validation**, nếu chính sách đầu vào cho phép chuyển đổi trước khi lưu.

Không gọi `Normalizer.normalize` là công cụ “sửa mọi Unicode lỗi”. Cũng không tự động xóa mọi ký tự trông kỳ lạ: dấu kết hợp, ZWJ, ký tự định hướng hoặc ký tự đặc biệt có thể mang ý nghĩa thật sự. Với identifier nhạy cảm bảo mật, việc chặn một số ký tự là **chính sách validation riêng**, không phải thuộc tính của normalization.

## 15. Unicode normalization khác so khớp ngôn ngữ tự nhiên

`java.text.Normalizer` hỗ trợ NFC/NFD/NFKC/NFKD. Nó không tự:

- Dịch hoặc phiên âm tất cả chữ viết.
- Thực hiện stemming/lemmatization.
- Xử lý đầy đủ Unicode case folding.
- Sắp xếp từ ngữ tự nhiên theo mọi locale.
- Nhận diện và ngăn chặn toàn bộ confusable/homoglyph attacks.
- Xử lý mọi cách gõ thiếu dấu theo ngữ nghĩa ngôn ngữ.

Khi cần collation theo ngôn ngữ, có thể dùng `java.text.Collator` hoặc thư viện i18n như ICU. Khi cần search nâng cao, có thể sử dụng text analyzer chuyên biệt. Dù dùng thuật toán nào, cần phân biệt **kết quả so sánh** với **giá trị được lưu để hiển thị**.

Không dùng cùng một pipeline chỉ mục cho mọi trường nếu mục đích khác nhau: tên người, username, văn bản tự do, mã SKU, số điện thoại và tài liệu pháp lý có yêu cầu rất khác nhau.

## 16. Phân quyền và thời gian lưu trữ bản gốc

Giữ dữ liệu gốc đúng kỹ thuật không đồng nghĩa được phép lưu dữ liệu không giới hạn. Với thông tin cá nhân, dữ liệu nhạy cảm và nội dung người dùng:

- Chỉ lưu những trường original cần thiết cho mục đích sản phẩm.
- Dùng quyền truy cập, mã hóa và kiểm soát audit theo chính sách.
- Có thời gian lưu trữ, quyền sửa/xóa và cách cập nhật index khi original bị xóa.
- Không in bản gốc nhạy cảm ra log chỉ để debug normalization.
- Khi xóa bản gốc theo yêu cầu hoặc chính sách, phải xử lý bản sao, chỉ mục và bản dẫn xuất liên quan.

Quy tắc “giữ original” là để **tránh mất thông tin ngoài ý muốn**, không phải lý do bỏ qua quyền riêng tư và data minimization.

## 17. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ lưu kết quả NFKC | Không phục hồi `①` từ `1` | Lưu original riêng |
| Lấy searchKey làm tên hiển thị | Mất dấu, chữ hoa hoặc hình thức văn bản | Render original |
| Nghĩ NFC giữ nguyên UTF-8 bytes | Mất dãy code point/byte ban đầu | Phân biệt canonical equivalence và raw identity |
| Dùng lowercasing không kiểm soát locale | Kết quả không phù hợp hoặc không ổn định | Quy định rõ locale/case policy |
| Cho searchKey là unique mặc định | Gộp nhầm nhiều original | Xác định quy tắc identity và xử lý collision |
| Bỏ dấu trực tiếp trên tên gốc | Mất phân biệt ngữ nghĩa/ngôn ngữ | Chỉ tạo derived key khi được phép |
| Thay đổi index rule mà không rebuild | Khóa cũ/mới không tương thích | Lưu ruleVersion và recompute từ original |
| Dùng normalized hash chứng minh nguồn không đổi | Không chứng minh byte-for-byte integrity | Hash bytes nguồn cần bảo vệ |
| Chỉ giữ `String` khi cần giữ file gốc | Không tái hiện encoding/BOM hoặc bytes lỗi | Lưu bytes cùng metadata cần thiết |
| Dùng Normalizer làm bộ lọc bảo mật hoàn chỉnh | Vẫn có confusables/validation risks | Thiết kế validation và security controls riêng |
| Giữ original vô thời hạn | Rủi ro dữ liệu cá nhân tăng | Retention/access/deletion policy |

## 18. Kiểm thử

Các trường hợp nên có trong bộ regression tests:

1. **Canonical:** `"\u00E9"` và `"e\u0301"` khác raw, bằng nhau sau NFC.
2. **Compatibility:** `"①"` và `"1"` cùng NFKC thành `"1"`.
3. **Fullwidth:** `"ＡＢＣ"` trở thành `"ABC"` trong derived key, original còn nguyên.
4. **Case:** `"ABC"` và `"abc"` có thể trùng lowercase key.
5. **Locale:** `"I"` tiếng Thổ Nhĩ Kỳ khi lowercasing khác một số locale khác.
6. **Diacritics:** `"Café"` và `"Cafe"` có thể trùng nếu pipeline chủ đích bỏ dấu.
7. **Identity:** nhiều record IDs có thể cùng searchKey, và quyết định gộp phải thuộc nghiệp vụ.
8. **Display:** sau mọi truy vấn, UI render original, không render searchKey.
9. **Version:** khi đổi thuật toán, có thể dựng lại khóa mới từ bản gốc.
10. **Integrity:** byte-level hash thử trên bytes đúng mà hợp đồng yêu cầu bảo toàn.
11. **Malformed input:** decode/validation có chính sách rõ.
12. **Privacy:** xóa original cũng xử lý index và bản dẫn xuất theo chính sách.
13. **Đa ngôn ngữ:** test với tiếng Việt, emoji, script khác và các cách viết tên có dấu.
14. **Backward compatibility:** thay thuật toán index không tự thay đổi bản hiển thị.

### Bài tập

- Thêm `①`, `1`, `ＡＢＣ`, `ABC` vào danh sách và đếm số nhóm searchKey sau NFKC + lowercase. Giải thích tại sao số nhóm nhỏ hơn số original.
- Tạo hàm search bỏ dấu riêng, dùng `Normalizer.Form.NFD` và thao tác xử lý combining marks, nhưng tuyệt đối không lưu kết quả vào trường tên hiển thị.
- Viết migration giả định từ `nfkc-lower-v1` sang `nfkc-lower-strip-v2`: recompute từ original, tạo báo cáo các collision mới và kế hoạch rollback.
- So sánh bytes UTF-8 của `"\u00E9"` và `"e\u0301"` trước/sau NFC. Chọn phương pháp đúng cho kiểm toán byte-level.
- Thiết kế quy tắc username không phân biệt hoa/thường nhưng vẫn giữ display name nguyên văn; mô tả cách phát hiện va chạm khi đăng ký.
- Thảo luận một tình huống bản gốc được phép thay đổi theo hợp đồng và một tình huống phải giữ nguyên (văn bản tác giả hoặc dữ liệu pháp lý).

## 19. Tổng kết

**Dữ liệu gốc** và **dữ liệu dẫn xuất** phải được phân biệt ngay trong mô hình lưu trữ. NFC/NFD có thể làm mất thông tin về dãy code point/bytes ban đầu dù giữ tương đương chuẩn tắc; NFKC/NFKD có thể gộp các ký tự tương thích; lowercasing, bỏ dấu, transliteration hoặc giản lược khoảng trắng còn có thể xóa thêm những khác biệt.

Hãy lưu original ở dạng đúng với hợp đồng, tạo searchKey bằng thuật toán tường minh, giữ quan hệ một-nhiều khi có va chạm, version hóa pipeline và chỉ thay original theo chính sách được chấp nhận. Nếu phải giữ byte-for-byte identity, bản gốc cần được bảo quản ở mức bytes, không chỉ dựa vào Java `String`.

**Ghi nhớ:** dùng normalize để **hỗ trợ so sánh và tìm kiếm**, không vì thuận tiện mà đánh đổi **khả năng tái hiện nguyên văn** ngoài ý muốn.

## Tài liệu tham khảo

- [Oracle JDK 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Oracle JDK 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle JDK 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Unicode UAX #15 — Normalization Forms](https://www.unicode.org/reports/tr15/)
