# Vì sao loại bỏ dấu không phải bước chuẩn hóa trung lập

## 1. Vấn đề: “chuẩn hóa Unicode” và “bỏ dấu” không đồng nghĩa

Hai chuỗi có thể được biểu diễn bằng các mã Unicode khác nhau nhưng vẫn là **cùng một văn bản** theo quy tắc tương đương Unicode. Ngược lại, hai từ khác dấu có thể biểu thị **những từ hoàn toàn khác nghĩa**. Vì thế, trong ứng dụng Java hỗ trợ nhiều ngôn ngữ, cần tách hai thao tác:

1. **Unicode normalization**: đưa chuỗi về một trong các *normalization form* tiêu chuẩn như NFC hoặc NFD, nhằm xử lý các cách biểu diễn tương đương theo quy tắc Unicode.
2. **Diacritic removal / accent stripping**: cố ý **xóa dấu** (thường là ký tự kết hợp thuộc Unicode category Mark), tạo một **biểu diễn đã mất thông tin**, đôi khi hữu ích cho tìm kiếm gần đúng nhưng không phải bản thay thế nguyên nghĩa.

Ví dụ tiếng Việt:

| Chuỗi gốc | Ý nghĩa có thể khác nhau | Sau cách bỏ dấu NFD + xóa Mark |
| --- | --- | --- |
| `ma` | Từ “ma” | `ma` |
| `má` | Từ “má” | `ma` |
| `mà` | Từ “mà” | `ma` |
| `mả` | Từ “mả” | `ma` |
| `mã` | Từ “mã” | `ma` |
| `mạ` | Từ “mạ” | `ma` |

Sau bỏ dấu, nhiều mục nhập **khác nhau** trở thành **cùng một chuỗi**. Không có thuật toán chung nào có thể suy ngược chắc chắn từ `ma` thành đúng từ gốc.

**Kết luận cốt lõi:** bỏ dấu là một phép biến đổi **mất thông tin và phụ thuộc mục tiêu ứng dụng**. Nó không phải một bước “làm sạch” trung lập có thể áp dụng cho tên người, tên địa danh, câu tiếng Việt, mã định danh hoặc văn bản mọi ngôn ngữ mà không thay đổi ý nghĩa.

## 2. Canonical equivalence: cùng ký tự nhìn thấy, nhiều cách mã hóa

Unicode cho phép một số ký tự có dấu được biểu diễn theo hai cách:

- **Precomposed**: ký tự dựng sẵn, ví dụ `é` (U+00E9).
- **Decomposed**: ký tự cơ sở `e` (U+0065) và dấu sắc kết hợp `◌́` (U+0301).

Hai chuỗi dưới đây có thể trông giống hệt nhau:

~~~text
"café"       -> c a f U+00E9
"cafe\u0301" -> c a f U+0065 U+0301
~~~

Ở dòng thứ hai, `\u0301` là cách viết escape của Java cho **COMBINING ACUTE ACCENT**. Đây không phải hai từ khác nghĩa; chúng là những cách biểu diễn **tương đương chuẩn tắc** (*canonically equivalent*).

Tuy nhiên, `String.equals(...)` so sánh chuỗi theo các đơn vị ký tự UTF-16, không tự chuẩn hóa Unicode trước. Vì thế, hai chuỗi tương đương chuẩn tắc có thể **không bằng nhau theo `equals`** nếu mã hóa khác cách.

### Ví dụ Java 17+ chạy độc lập

Lưu `CanonicalNormalizationDemo.java`:

~~~java
import java.text.Normalizer;

public class CanonicalNormalizationDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("Raw lengths: "
                + composed.length() + " and " + decomposed.length());

        String leftNfc = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String rightNfc = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + leftNfc.equals(rightNfc));
        System.out.println("NFC lengths: "
                + leftNfc.length() + " and " + rightNfc.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CanonicalNormalizationDemo.java
java CanonicalNormalizationDemo
~~~

Kết quả:

~~~text
Raw equals: false
Raw lengths: 4 and 5
NFC equals: true
NFC lengths: 4 and 4
~~~

Điểm cần nhớ:

- Chuỗi dựng sẵn `caf\u00E9` dài 4 đơn vị UTF-16; dạng phân rã `cafe\u0301` dài 5.
- `Normalizer.Form.NFC` đưa cả hai về dạng chuẩn tắc tương thích, nên chúng bằng nhau theo `equals` sau khi chuẩn hóa.
- **Dấu sắc vẫn được giữ lại trong `café`**. NFC không biến `café` thành `cafe`.

Đây là minh họa rất rõ vì sao **“chuẩn hóa” không đồng nghĩa “loại bỏ dấu”**.

## 3. Bốn Unicode normalization form và vai trò của chúng

API chuẩn của Java là `java.text.Normalizer`, với `Normalizer.Form`:

| Dạng | Tên | Tác dụng chính | Có chủ ý xóa dấu không? |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Phân rã ký tự theo tương đương chuẩn tắc | **Không** |
| `NFC` | Canonical Decomposition + Composition | Phân rã và tổ hợp chuẩn tắc để tạo dạng đã chuẩn hóa | **Không** |
| `NFKD` | Compatibility Decomposition | Phân rã cả các ký tự tương thích | **Không**, nhưng có thể đổi biểu diễn có ý nghĩa |
| `NFKC` | Compatibility Decomposition + Composition | Dùng phân rã tương thích rồi tổ hợp chuẩn tắc | **Không**, nhưng có thể gộp khác biệt tương thích |

Ví dụ:

~~~java
String nfc = Normalizer.normalize(input, Normalizer.Form.NFC);
String nfd = Normalizer.normalize(input, Normalizer.Form.NFD);
String nfkc = Normalizer.normalize(input, Normalizer.Form.NFKC);
String nfkd = Normalizer.normalize(input, Normalizer.Form.NFKD);
~~~

Đây là **mảnh mã trong method**, cần import `java.text.Normalizer` và biến `input` đã có.

### NFC: thường phù hợp để thống nhất lưu trữ văn bản thông thường

NFC giúp tránh việc cùng một chữ có dấu bị lưu dưới hai cách mã hóa tương đương chuẩn tắc. Nó **không** xóa dấu và thường là lựa chọn hợp lý cho văn bản tiếng Việt cần bảo toàn nội dung.

Tuy nhiên, không có quy tắc “mọi loại dữ liệu đều bắt buộc NFC” trong mọi hệ thống. Mã định danh, giao thức, chữ ký số, tên file, so khớp bảo mật và các chuẩn chuyên ngành có thể có profile Unicode hoặc chính sách byte riêng. Cần tuân thủ hợp đồng của dữ liệu đó.

### NFD: phân rã để xử lý ký tự và dấu kết hợp

Một ký tự có dấu có thể trở thành ký tự cơ sở và một hoặc nhiều dấu kết hợp. Ví dụ một nguyên âm tiếng Việt có dấu có thể tách thành chữ cơ sở và các dấu biểu thị hình dạng nguyên âm, thanh điệu.

**NFD vẫn giữ các dấu.** Chỉ khi bạn thực hiện thao tác xóa Mark **sau đó**, thông tin mới bị loại bỏ.

### NFKC và NFKD: tương đương tương thích không trung lập về nghĩa trình bày

Compatibility normalization có thể đổi các ký tự kiểu:

- Số khoanh tròn `①` thành `1`.
- Ligature `ﬁ` thành hai ký tự `fi`.
- Chữ Latin fullwidth `Ａ` thành `A`.

Đây là các phép biến đổi tương thích hữu ích trong một số hệ thống tra cứu và chuẩn hóa định danh theo quy chuẩn riêng, nhưng **không** được mặc định xem là bảo toàn mọi khác biệt mang tính trình bày hoặc ngữ nghĩa mà người dùng quan tâm.

### Ví dụ NFKC độc lập

Lưu `CompatibilityNormalizationDemo.java`:

~~~java
import java.text.Normalizer;

public class CompatibilityNormalizationDemo {
    public static void main(String[] args) {
        String source = "\u2460 \uFB01 \uFF21";

        System.out.println("Original: " + source);
        System.out.println("NFC: "
                + Normalizer.normalize(source, Normalizer.Form.NFC));
        System.out.println("NFKC: "
                + Normalizer.normalize(source, Normalizer.Form.NFKC));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CompatibilityNormalizationDemo.java
java CompatibilityNormalizationDemo
~~~

Kết quả:

~~~text
Original: ① ﬁ Ａ
NFC: ① ﬁ Ａ
NFKC: 1 fi A
~~~

**Phân biệt:** NFKC là **normalization chuẩn Unicode**, còn bỏ dấu là một quy tắc bổ sung do ứng dụng tự lựa chọn. Nhưng việc NFKC mang tính chuẩn không có nghĩa nó luôn phù hợp với tất cả dữ liệu; chính compatibility equivalence đã có thể bỏ qua những phân biệt hình thức.

## 4. Thao tác “bỏ dấu” phổ biến trong Java thực sự làm gì?

Một công thức thường được chia sẻ:

~~~java
String stripped = Normalizer
        .normalize(input, Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
~~~

Đây là **mảnh mã trong method**, cần import `java.text.Normalizer` và biến `input` kiểu `String`.

Nó thực hiện **hai bước khác nhau**:

1. `Normalizer.Form.NFD` phân rã những ký tự có tương đương chuẩn tắc.
2. Regex `\p{M}` chọn Unicode category **Mark** và xóa toàn bộ các nhóm ký tự thuộc nhóm này.

Unicode general category **M** gồm nhiều loại:

- `Mn`: *Nonspacing Mark*.
- `Mc`: *Spacing Combining Mark*.
- `Me`: *Enclosing Mark*.

Trong ví dụ tiếng Pháp, `é` có thể phân rã thành `e + ◌́`. Khi xóa `◌́`, chữ `é` thành `e`. Nhưng dấu đó có thể là một phần quyết định cách đọc và nghĩa; việc xóa là **cố ý làm mất thông tin**.

**Bẫy thường gặp:** biểu thức `\p{M}` không có nghĩa “chỉ xóa dấu sắc, huyền, hỏi, ngã, nặng trong tiếng Việt”. Nó có thể xóa **các dấu kết hợp thuộc nhiều hệ chữ viết**, bao gồm những dấu không thể coi là trang trí.

## 5. Tiếng Việt: xóa dấu làm thay đổi từ, không chỉ thay hình thức

Tiếng Việt có **thanh điệu** và **dấu tạo dạng nguyên âm**, đều góp phần phân biệt từ. Ví dụ `a`, `ă` và `â` không phải những cách viết tự do của một nguyên âm duy nhất; `má`, `mã`, `mạ` có thể là các từ khác nhau.

### Ví dụ Java 17+ chạy độc lập

Tạo `VietnameseDiacriticLossDemo.java`:

~~~java
import java.text.Normalizer;

public class VietnameseDiacriticLossDemo {
    static String removeMarks(String source) {
        return Normalizer
                .normalize(source, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
    }

    public static void main(String[] args) {
        String[] words = {
                "ma", "má", "mà", "mả", "mã", "mạ"
        };

        for (String word : words) {
            System.out.println(word + " -> " + removeMarks(word));
        }

        System.out.println("Đặng -> " + removeMarks("Đặng"));
    }
}
~~~

Biên dịch/chạy (lưu nguồn Java ở UTF-8):

~~~bash
javac -encoding UTF-8 VietnameseDiacriticLossDemo.java
java VietnameseDiacriticLossDemo
~~~

Kết quả:

~~~text
ma -> ma
má -> ma
mà -> ma
mả -> ma
mã -> ma
mạ -> ma
Đặng -> Đang
~~~

### Phân tích

- Sáu từ trong ví dụ đều trở thành `ma` sau khi xóa dấu kết hợp.
- Khi xóa dấu tạo dạng nguyên âm và thanh điệu trong `Đặng`, phép biến đổi còn để nguyên chữ `Đ`, cho ra `Đang`.
- Đây **không phải** phép chuyển chính tả chính xác từ tiếng Việt sang ASCII. `Đ` và `đ` không trở thành `D`/`d` chỉ bằng NFD + xóa `\p{M}`.

Điều này có hai hệ quả:

1. **Mất nghĩa**: một kết quả không còn đủ thông tin để khôi phục từ gốc.
2. **Chưa chắc đạt mục tiêu kỹ thuật**: nhiều người nghĩ “bỏ dấu” sẽ tạo ASCII, nhưng chuỗi vẫn có thể chứa `Đ/đ` và các ký tự khác không phân rã thành chữ Latin cơ sở.

Nếu một sản phẩm đặt yêu cầu chuyển tên tiếng Việt thành dạng ASCII cho URL hoặc một chuẩn máy cụ thể, nó cần **chính sách transliteration riêng**, có tài liệu và kiểm thử. Không thể lấy `NFD + \p{M}` như một chuẩn chuyển tự phổ quát.

## 6. Không chỉ tiếng Việt: tác động đa ngôn ngữ rất khác nhau

### 6.1. Ngôn ngữ Latin

- Tiếng Pháp: `café` → `cafe`; `côte`, `côté` và `cote` có thể bị gộp lại dù từ gốc khác nhau.
- Tiếng Tây Ban Nha: `ñ` không đơn thuần là cách trang trí của `n` trong chính tả; bỏ dấu có thể làm mất phân biệt chữ cái.
- Tiếng Ba Lan: các ký tự như `ł` không nhất thiết phân rã thành `l + Mark` theo NFD, nên thuật toán bỏ Mark không tạo dạng Latin ASCII mà người viết mong đợi.
- Tiếng Đức: `ß` không trở thành `ss` khi chỉ NFD và xóa Mark; đó là bài toán biến đổi chữ viết/transliteration khác.
- Tiếng Thổ Nhĩ Kỳ: `I`, `İ`, `ı` và `i` liên quan đến quy tắc chữ hoa/thường theo locale. Xóa dấu rồi tự `toLowerCase` sai ngữ cảnh có thể gộp các dạng không mong muốn.

### 6.2. Hệ chữ viết có dấu kết hợp là thành phần cốt lõi

Trong nhiều hệ chữ, Mark có thể biểu diễn **nguyên âm, thanh điệu hoặc thành phần chữ viết**, không chỉ dấu phụ tùy chọn. Xóa `\p{M}` trên văn bản thuộc hệ chữ Ấn Độ, Thái hoặc các hệ chữ khác có thể làm thay đổi cách đọc và cấu trúc từ rất nặng.

Với chữ Ả Rập, các dấu nguyên âm ngắn (*harakat*) có thể được lược bỏ trong một số ngữ cảnh viết, nhưng việc xóa chúng cũng có thể làm mất thông tin để xác định cách đọc/ý nghĩa. Việc chấp nhận hay không phải là **chính sách theo ngôn ngữ và mục tiêu**, không phải quyết định kỹ thuật áp dụng toàn thế giới.

### 6.3. Ký tự đặc biệt, biểu tượng và emoji

Category Mark không chỉ bao gồm các dấu “ngữ pháp” mà người lập trình thường nghĩ đến. Một số ký tự biến thể hiển thị (*variation selector*, chẳng hạn `U+FE0F`) là Mark. Xóa tất cả Mark có thể làm thay đổi **cách trình bày biểu tượng/emoji**.

Ngược lại, nhiều thành phần tạo emoji phức tạp như zero-width joiner hoặc các modifier không thuộc category Mark, nên công thức bỏ Mark cũng **không** phải một “trình chuẩn hóa emoji” hoàn chỉnh.

**Kết luận:** không nên xây dựng một quy tắc xóa mọi `\p{M}` trên toàn bộ nội dung toàn cầu chỉ vì vài ví dụ Latin cho kết quả có vẻ hợp lý.

## 7. Xóa dấu không phải transliteration, case folding hay collation

Ba khái niệm rất dễ nhầm:

| Công việc | Mục tiêu | Có luôn bảo toàn nghĩa/định danh không? |
| --- | --- | --- |
| Unicode normalization (NFC) | Đưa biểu diễn tương đương chuẩn tắc về dạng nhất quán | Giữ phân biệt dấu có ý nghĩa ở ví dụ như `má`/`mã` |
| Diacritic stripping | Cố ý xóa một tập dấu | **Không**, làm mất thông tin |
| Transliteration | Chuyển chữ viết sang một hệ biểu diễn khác theo quy tắc | Có thể mất thông tin, tùy hệ và quy tắc |
| Case conversion/case folding | Xử lý khác biệt chữ hoa/thường theo quy tắc | Có thể gộp phân biệt, cần xét locale/chuẩn |
| Collation | So sánh/sắp xếp chuỗi theo ngôn ngữ, có thể chọn mức độ khác biệt | Không phải biến đổi chuỗi thành bản gốc mới |

### Vì sao `Đ` và `ß` là ví dụ tốt?

`Đ` và `đ` không trở thành `D`/`d` chỉ vì bạn gọi NFD. Tương tự, `ß` thường không trở thành `ss` bằng NFD + xóa Mark. Nếu cần dạng không dấu để tìm kiếm hay slug, phải định nghĩa **bộ chuyển tự** cụ thể, có thể kết hợp thư viện hoặc mapping cho ngôn ngữ mục tiêu.

Không xây dựng phép chuyển tự toàn cầu bằng một vài `replace` cho tiếng Việt rồi dùng nó cho mọi ngôn ngữ. Các quyết định về `Đ`, `ł`, `ø`, `æ` hay chữ viết không Latin cần chính sách khác nhau và kiểm thử riêng.

### Case mapping cũng có bẫy locale

Một bước như:

~~~java
String key = source.toLowerCase(Locale.ROOT);
~~~

là **mảnh mã trong method**, cần import `java.util.Locale` và biến `source`. Nó tạo cách chuyển chữ thường không phụ thuộc locale người dùng, nhưng **không đồng nghĩa với Unicode full case folding cho mọi chuẩn** và không bảo đảm đúng mọi quy tắc tiếng Thổ Nhĩ Kỳ, Hy Lạp hoặc hệ chữ viết khác trong so khớp ngôn ngữ tự nhiên.

Nếu so khớp từ ngữ theo ngôn ngữ cụ thể, cần xác định locale và tiêu chí so sánh, thay vì lấy `lowercase + removeMarks` làm công thức đúng cho mọi trường hợp.

## 8. Tìm kiếm không dấu: một yêu cầu có thể hợp lý nhưng phải có hợp đồng

Có nhiều tình huống người dùng muốn gõ `"cafe"` để tìm `"café"`, hoặc gõ `"dang"` để tìm tên `"Đặng"`. Đây là **tính năng tìm kiếm khoan dung dấu**, không phải lý do để làm mất dấu trong dữ liệu gốc.

Thiết kế thường phù hợp:

~~~text
Nguồn được lưu (giữ nguyên nội dung):
    "Má", "Mã", "Ma", "Đặng", "café"
            |
            +--> NFC để thống nhất biểu diễn chuẩn tắc
            |
            +--> Chỉ mục tìm kiếm riêng:
                  case/diacritic folding, transliteration
                  hoặc collation theo quy tắc sản phẩm
            |
            +--> Khi trả kết quả:
                  luôn hiển thị chuỗi gốc có dấu
~~~

**Tìm kiếm khoan dung dấu cần chấp nhận nhiều kết quả trùng.** Người dùng gõ `ma` có thể nhận nhiều từ như `ma`, `má`, `mà`, `mả`, `mã`, `mạ`. Hệ thống có thể xếp hạng kết quả khớp chính xác cao hơn, nhưng không thể khôi phục khác biệt chỉ từ khóa bỏ dấu.

### Ví dụ Java: giữ nguồn và tạo search key riêng

Lưu `SearchKeyDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class SearchKeyDemo {
    static String nfc(String source) {
        return Normalizer.normalize(
                source, Normalizer.Form.NFC);
    }

    static String approximateKey(String source) {
        String decomposed = Normalizer.normalize(
                source, Normalizer.Form.NFD);
        return decomposed
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String original = nfc("Má");
        String key = approximateKey(original);

        System.out.println("Original: " + original);
        System.out.println("Search key: " + key);
        System.out.println("Original preserved: "
                + original.equals("Má"));

        System.out.println("Ma key: "
                + approximateKey("Ma"));
        System.out.println("Mã key: "
                + approximateKey("Mã"));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SearchKeyDemo.java
java SearchKeyDemo
~~~

Kết quả:

~~~text
Original: Má
Search key: ma
Original preserved: true
Ma key: ma
Mã key: ma
~~~

Đây là **ví dụ học cơ chế**, chưa phải bộ xử lý tìm kiếm đa ngôn ngữ production-ready. Nó cố ý tạo ra collision; nó không tự xử lý `Đ → D`, tiếng Thổ Nhĩ Kỳ hoặc các ngôn ngữ không Latin. Một hệ thống thực tế phải định nghĩa phạm vi ngôn ngữ, quy tắc transliteration, tối ưu chỉ mục và ranking.

### Chính sách ranking hữu ích

Khi tìm tên hoặc địa danh:

1. Ưu tiên khớp **chuỗi gốc chính xác**.
2. Sau đó ưu tiên khớp **NFC/case-insensitive** theo chính sách.
3. Tiếp theo mới xét **accent-insensitive** hoặc transliteration nếu người dùng bật/tính năng hỗ trợ.
4. Hiển thị tên có dấu và các dữ kiện phân biệt để người dùng chọn kết quả đúng.

Không tự biến mọi kết quả tìm kiếm gần đúng thành một định danh duy nhất.

## 9. Collator: so sánh theo locale thay vì tự xóa dấu

`java.text.Collator` hỗ trợ so sánh và sắp xếp văn bản theo quy tắc locale. `Collator` có các mức `strength` quyết định loại khác biệt được xét.

Ví dụ:

- **PRIMARY**: mức khác biệt chính; trong nhiều locale có thể bỏ qua sự khác nhau về dấu và chữ hoa/thường.
- **SECONDARY**: xét thêm một số khác biệt như dấu trong những ngôn ngữ thích hợp.
- **TERTIARY**: xét thêm khác biệt như hoa/thường và các biến thể khác theo locale.

**Điểm quan trọng:** đây là quy tắc **so sánh**, không phải thao tác xóa ký tự trên chuỗi đã lưu.

### Ví dụ đầy đủ

Tạo `CollationDemo.java`:

~~~java
import java.text.Collator;
import java.util.Locale;

public class CollationDemo {
    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.FRENCH);

        collator.setStrength(Collator.PRIMARY);
        System.out.println("Primary equal: "
                + (collator.compare("cafe", "café") == 0));

        collator.setStrength(Collator.TERTIARY);
        System.out.println("Tertiary equal: "
                + (collator.compare("cafe", "café") == 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CollationDemo.java
java CollationDemo
~~~

Kết quả với cách so khớp tiếng Pháp thông dụng trong JDK:

~~~text
Primary equal: true
Tertiary equal: false
~~~

### Giới hạn cần biết

- `Collator.PRIMARY` **không** có nghĩa “chỉ bỏ dấu, giữ nguyên mọi phân biệt khác”; nó còn có thể bỏ qua case và những khác biệt thứ yếu theo locale.
- Quy tắc collation phụ thuộc locale, provider và phiên bản dữ liệu. Không mặc định cùng một mức `PRIMARY` ở mọi ngôn ngữ sẽ coi những cặp chữ như nhau.
- `Collator` là đối tượng có cấu hình thay đổi (ví dụ `setStrength`). Nếu dùng chung giữa nhiều luồng, cần kiểm soát an toàn luồng hoặc tạo instance riêng; không chia sẻ instance mutable đang đổi cấu hình theo từng request.
- Không dùng collation accent-insensitive để quyết định hai tài khoản, tài liệu pháp lý hoặc hai định danh **chắc chắn là cùng một đối tượng**.

Khi mục tiêu chỉ là tìm kiếm/sắp xếp theo ngôn ngữ, collation thường phù hợp hơn việc phá hủy dấu trong bản gốc.

## 10. Bỏ dấu và các hệ thống có yêu cầu an toàn

### 10.1. Username, định danh, khóa và chữ ký số

Nếu hai tên người dùng khác nhau `Má` và `Mã` bị đưa cùng về `ma`, việc dùng chuỗi đó làm **unique key** có thể gây collision. Nguy hiểm hơn, một hệ thống kiểm tra quyền truy cập theo tên đã fold nhưng hệ thống khác kiểm tra theo tên gốc có thể sinh ra **không thống nhất về danh tính**.

Đối với khóa nghiệp vụ, tài khoản, đường dẫn phân quyền, chữ ký hoặc mật khẩu:

- Chọn một **profile Unicode/identifier** hoặc hợp đồng so khớp cụ thể.
- Chuẩn hóa ở đúng ranh giới theo profile ấy.
- Không tự áp dụng `NFD + removeMarks` như một phép kiểm tra “trung lập”.
- Giữ định danh nội bộ độc lập với chuỗi tên hiển thị khi có thể.
- Xác định chính sách xử lý ký tự confusable, Unicode normalization và giới hạn tập ký tự nếu thực sự cần.

**Đặc biệt:** normalize Unicode **không** đồng nghĩa phát hiện ký tự giống hình nhưng khác mã (*homoglyph/confusable*). Chữ Latin `a` và ký tự của hệ chữ khác có hình dạng gần giống vẫn có thể tạo nguy cơ nhầm lẫn, trong khi NFC không tự giải quyết tất cả vấn đề này.

### 10.2. Tên riêng, thông tin pháp lý và bản dịch

Tên người, địa danh, địa chỉ, văn bản pháp lý, nội dung giáo dục và thông điệp được dịch cần bảo toàn dấu. Việc bỏ dấu có thể:

- Làm sai cách viết tên đã đăng ký.
- Thay đổi cách đọc và nghĩa tiếng Việt.
- Làm mất thông tin khi hệ thống xuất dữ liệu lại.
- Khiến việc đối chiếu với chứng từ hoặc nguồn gốc không còn chính xác.

Nếu phải tạo phiên bản không dấu cho một hệ thống bên ngoài chỉ hỗ trợ ASCII, hãy **giữ cả bản gốc** và ghi rõ phiên bản chuyển đổi, thuật toán, ngôn ngữ mục tiêu và giới hạn.

### 10.3. URL slug và đường dẫn

Slug không dấu đôi khi là quyết định sản phẩm hợp lệ. Nhưng hai tiêu đề khác dấu có thể tạo **cùng slug**. Vì thế, bộ tạo slug phải giải quyết collision bằng ID hoặc suffix độc lập, không dựa vào giả định rằng phép bỏ dấu có tính một-một.

Ví dụ ý tưởng:

~~~text
Tên hiển thị:  "Má"    -> khóa tìm kiếm "ma"
Tên hiển thị:  "Mã"    -> khóa tìm kiếm "ma"

Slug riêng:
  /articles/ma-101
  /articles/ma-102
~~~

Không dùng slug bỏ dấu làm **bằng chứng rằng hai tiêu đề là một**.

## 11. Kiểm tra và xử lý Unicode đúng cấp độ ký tự

Java `String` dùng UTF-16. `length()` đếm **code unit**, không phải số grapheme cluster mà người dùng nhận thức là ký tự. Một chữ cái có dấu kết hợp có thể gồm nhiều code point; emoji có thể gồm nhiều code point gắn bằng joiner.

### Quan sát code point thay vì chỉ in chuỗi

Ví dụ độc lập `CodePointDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.stream.Collectors;

public class CodePointDemo {
    static String hex(String input) {
        return input.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String composed = "caf\u00E9";
        String decomposed = Normalizer.normalize(
                composed, Normalizer.Form.NFD);

        System.out.println("Composed: " + hex(composed));
        System.out.println("Decomposed: " + hex(decomposed));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CodePointDemo.java
java CodePointDemo
~~~

Kết quả:

~~~text
Composed: U+0063 U+0061 U+0066 U+00E9
Decomposed: U+0063 U+0061 U+0066 U+0065 U+0301
~~~

Khi thấy `U+0301`, ta biết dấu sắc đang tồn tại như **combining mark**. NFC có thể thay đổi *cách mã hóa* của nó mà vẫn giữ nghĩa; xóa `U+0301` là **thay đổi nội dung**.

Nếu cần xử lý theo *grapheme cluster* của người dùng, không thể chỉ lấy `substring` theo từng code unit rồi xem mỗi đoạn là một chữ cái hoàn chỉnh. Phải dùng thuật toán phân đoạn văn bản phù hợp Unicode/ngôn ngữ; Java có `BreakIterator` hỗ trợ các tác vụ phân đoạn, nhưng hành vi cụ thể và mức hỗ trợ grapheme nên được kiểm thử cho tập dữ liệu mục tiêu.

## 12. Quy trình khuyến nghị: giữ original và giới hạn biến đổi phụ

Một cách tổ chức dữ liệu hợp lý cho ứng dụng Java:

~~~text
Người dùng gửi: "Má"
        |
        v
Xác thực đầu vào (độ dài, ký tự, quy tắc dữ liệu)
        |
        v
Chuẩn hóa NFC nếu phù hợp với schema
        |
        +----> LƯU BẢN GỐC CÓ DẤU: "Má"
        |
        +----> CHỈ MỤC TÌM KIẾM PHỤ:
               case/accent folding theo policy
               (có thể sinh ra "ma")
        |
        +----> Truy vấn gần đúng và ranking
        |
        v
Hiển thị bản gốc: "Má"
~~~

### 12.1. Ví dụ mô hình Java

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public record SearchableName(String displayName, String searchKey) {
    public static SearchableName from(String raw) {
        Objects.requireNonNull(raw, "raw");

        String original = Normalizer.normalize(
                raw, Normalizer.Form.NFC);
        String folded = Normalizer
                .normalize(original, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT);

        return new SearchableName(original, folded);
    }
}
~~~

Lưu thành `SearchableName.java`. Đây chỉ là mô hình minh họa dùng một chính sách fold đơn giản. Nó **không** khẳng định fold này đúng cho mọi locale hoặc làm biến đổi mọi chữ về ASCII.

Trong ứng dụng thật, hãy xem xét:

- Ngôn ngữ nào được hỗ trợ trong search key.
- Có cần mapping thêm cho `Đ/đ`, `ł`, `ø` hoặc hệ chữ khác không.
- Có chấp nhận nhiều kết quả trùng search key không.
- Có cần lưu phiên bản thuật toán tạo search key để tái lập chỉ mục khi thay đổi policy không.
- Có cần ranking theo khớp chính xác và theo ngôn ngữ không.
- Có thể dùng `Collator` hoặc khả năng collation/index của cơ sở dữ liệu hoặc search engine thay vì tự xử lý thủ công không.

### 12.2. Kiểm thử hai lớp khác nhau

**Lớp bảo toàn nội dung:**

- NFC của hai chuỗi tương đương chuẩn tắc phải như nhau.
- `Má` và `Mã` vẫn là hai chuỗi khác nhau sau NFC.
- Dữ liệu hiển thị trả về phải giữ đúng dấu.
- Việc serialize/deserialize không làm thay đổi nội dung Unicode ngoài chính sách đã tài liệu hóa.

**Lớp tìm kiếm gần đúng:**

- Người dùng gõ `ma` có thể tìm `ma`, `má` và `mã` theo policy.
- Kết quả chính xác phải được ưu tiên khi có thể.
- Collision của key không làm mất bản ghi hoặc phá uniqueness của ID.
- Thuật toán được kiểm thử với các ngôn ngữ và hệ chữ thực sự sử dụng.
- Những ký tự chưa hỗ trợ phải được xử lý theo quy tắc rõ, không âm thầm biến mất.

## 13. Các lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu/làm đúng |
| --- | --- | --- |
| “NFC là xóa dấu” | Lưu mất nội dung nếu tự thêm bước stripping | NFC giữ sự phân biệt dấu có nghĩa |
| “NFD không có dấu” | Hiểu sai cấu trúc code point | NFD **giữ** dấu dưới dạng combining mark |
| “`replaceAll("\\p{M}+", "")` là chuẩn hóa Unicode” | Xóa cả dấu thiết yếu nhiều hệ chữ | Đây là phép bỏ Mark mất thông tin, không phải normal form |
| “Bỏ dấu không đổi nghĩa tiếng Việt” | `má`/`mã`/`mạ` trùng nhau | Giữ bản gốc; chỉ fold cho chức năng cần thiết |
| “NFD + Mark tạo ASCII” | `Đ`, `ł`, `ß`... có thể còn | Transliteration cần chính sách riêng |
| “NFKC hoàn toàn trung lập” | Mất phân biệt compatibility, ví dụ `①`→`1` | Chọn NFKC khi đúng profile dữ liệu |
| “Lowercase chuẩn mọi ngôn ngữ” | Sai case mapping trong một số ngữ cảnh | Dùng locale/thuật toán đúng nhu cầu |
| “Collator PRIMARY chỉ bỏ dấu” | Gộp thêm case/các khác biệt khác | Xem strength và dữ liệu locale cụ thể |
| “Search key có thể dùng làm ID duy nhất” | Collision và nhầm bản ghi | Giữ ID độc lập và displayName gốc |
| “String.length là số ký tự nhìn thấy” | Cắt rời grapheme/combining mark | Hiểu UTF-16, code point, grapheme cluster |
| “Bỏ dấu giúp an toàn Unicode tuyệt đối” | Không xử lý confusable/định danh chuẩn | Dùng validation/profile bảo mật riêng |
| “Có thể bỏ dấu trên mọi bản dịch rồi khôi phục” | Không có cách suy ngược duy nhất | Bảo toàn nội dung gốc |

## 14. Bài tập thực hành và câu hỏi tự kiểm tra

1. Viết hai chuỗi Java biểu diễn `é` bằng `\u00E9` và `e\u0301`. Vì sao `equals` trả `false`, nhưng sau `Normalizer.Form.NFC` lại bằng nhau?
2. Format `"má"`, `"mã"` và `"mạ"` qua NFC rồi NFD. Ở bước nào nội dung vẫn còn phân biệt, và bước nào mới làm mất phân biệt nếu bạn xóa category Mark?
3. Chạy `VietnameseDiacriticLossDemo`. Vì sao `"Đặng"` thành `"Đang"` chứ không thành `"Dang"`?
4. Viết hàm bỏ dấu sử dụng `\p{M}` và giải thích tại sao nó không nên được áp dụng cho mọi văn bản Ả Rập/Ấn Độ/Thái.
5. So sánh NFC và NFKC trên `①`, `ﬁ`, `Ａ`. Sự khác biệt này có thể ảnh hưởng tên sản phẩm hoặc mã định danh như thế nào?
6. Dùng `Collator.getInstance(Locale.FRENCH)` với `PRIMARY` và `TERTIARY` để so `"cafe"` và `"café"`. Vì sao không nên lấy kết quả collation để tự kết luận hai tài khoản cùng danh tính?
7. Thiết kế chức năng tìm `"dang"` để thấy tên `"Đặng"`, nhưng khi hiển thị phải giữ `"Đặng"`. Cần những bước nào ngoài `NFD + removeMarks`?
8. Hai bài viết có tiêu đề `"Má"` và `"Mã"` cùng sinh search key `ma`. Hãy thiết kế slug không gây trùng, nhưng vẫn cho phép tìm không dấu.
9. Phân biệt sự khác nhau giữa **canonical normalization**, **compatibility normalization**, **diacritic removal**, **transliteration** và **collation**.
10. Một biểu mẫu nhận thông tin pháp lý phải giữ tên đúng theo chứng từ. Có nên lưu lại duy nhất phiên bản đã bỏ dấu hay không? Vì sao?

**Ghi nhớ:** Unicode normalization (đặc biệt NFC/NFD) nhằm xử lý **các biểu diễn tương đương theo chuẩn Unicode**; nó không có mục tiêu xóa thông tin dấu. Công thức `NFD + replaceAll("\\p{M}+", "")` là một phép **xóa Mark mất thông tin**: nó có thể biến các từ tiếng Việt khác nghĩa thành cùng chuỗi, phá cấu trúc chữ viết khác và vẫn không đảm bảo ASCII. Hãy **giữ văn bản có dấu làm dữ liệu gốc**, chỉ tạo phiên bản tìm kiếm/slug phụ khi có yêu cầu rõ ràng, với chính sách ngôn ngữ, collision, bảo mật và kiểm thử phù hợp.

### Tài liệu tham khảo

- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html) — các dạng NFC, NFD, NFKC, NFKD.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html) — so sánh văn bản theo locale và strength.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — code point và Unicode general category.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html) — Unicode categories và `\p{M}`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/) — chuẩn normal forms, canonical và compatibility equivalence.
- [Unicode Technical Standard #10 — Unicode Collation Algorithm](https://www.unicode.org/reports/tr10/) — collation và các mức so sánh.