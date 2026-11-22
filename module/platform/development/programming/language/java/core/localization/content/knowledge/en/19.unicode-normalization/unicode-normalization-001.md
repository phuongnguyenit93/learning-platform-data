# Chuẩn hóa Unicode là gì và khác với dịch hoặc phiên âm?

Khi xây phần mềm Java phục vụ nhiều ngôn ngữ, một đoạn văn bản trông giống nhau trên màn hình vẫn có thể chứa những **dãy mã Unicode khác nhau**. Kết quả là phép so sánh chuỗi, tìm kiếm, khóa trong `Map`, đối chiếu dữ liệu nhập và kiểm thử có thể hoạt động ngoài mong đợi. **Chuẩn hóa Unicode (Unicode normalization)** giải quyết một phần vấn đề này bằng cách đưa các cách biểu diễn tương đương của văn bản Unicode về một dạng có quy tắc.

Tuy nhiên, **chuẩn hóa không phải dịch thuật** và cũng **không phải phiên âm/chuyển tự**. Nó không đổi câu tiếng Việt thành tiếng Anh, không biến mọi chữ Cyrillic thành Latin, không tự xóa dấu và không hiểu nghĩa của câu. Chuẩn hóa tác động lên **cách biểu diễn các ký tự**; dịch và phiên âm là những quá trình khác, có mục tiêu và giới hạn khác.

Bài trình bày cách nhận biết các vấn đề Unicode, phân biệt bốn dạng chuẩn hóa NFC/NFD/NFKC/NFKD, sử dụng `java.text.Normalizer` trong Java 17+, hiểu các trường hợp tiếng Việt và tránh sai lầm khi áp dụng vào tìm kiếm, tên người, mã định danh và bảo mật.

## 1. Unicode và ba mức biểu diễn cần phân biệt

Để hiểu tại sao cần chuẩn hóa, tách ba khái niệm:

1. **Ký tự trừu tượng / grapheme**: thứ người đọc nhận thấy như một chữ có dấu, ví dụ `é`.
2. **Unicode code point**: giá trị như `U+00E9` hoặc một chuỗi gồm `U+0065` (`e`) và `U+0301` (combining acute accent).
3. **Đơn vị mã hóa lưu trữ**: Java `String` dùng các đơn vị mã UTF-16, mỗi đơn vị là `char` 16-bit; UTF-8 là cách mã hóa các code point thành byte khi ghi/truyền văn bản.

Ví dụ hai chuỗi có thể nhìn giống nhau:

~~~text
A (precomposed): U+00E9             → é
B (decomposed):  U+0065 U+0301      → e + ◌́
~~~

Dòng B là chữ `e` cộng dấu sắc **kết hợp** (combining mark). Nếu font và bộ hiển thị hỗ trợ, hai chuỗi có thể tạo hình ảnh gần như đồng nhất. Nhưng chúng chứa **code point khác nhau** và số đơn vị UTF-16 cũng khác nhau.

Trong Java:

~~~java
String a = "\u00E9";       // U+00E9: é
String b = "e\u0301";      // U+0065 U+0301: e + dấu sắc

System.out.println(a.equals(b)); // false
System.out.println(a.length());  // 1
System.out.println(b.length());  // 2
~~~

Đây là **đoạn minh họa** bên trong một phương thức Java. `String.equals` so sánh đúng dãy ký tự UTF-16, không tự thực hiện chuẩn hóa Unicode. Số ký tự người dùng *nhìn thấy* cũng không nhất thiết trùng với kết quả `length()`.

Đặc biệt, emoji có thể dùng surrogate pair, dấu kết hợp hoặc chuỗi nối bằng ZWJ; vì vậy **số code point, số UTF-16 code unit và số grapheme cluster** là ba đại lượng khác nhau. Chuẩn hóa Unicode **không phải** thuật toán đếm grapheme hoặc phân đoạn từ.

## 2. Chuẩn hóa Unicode thực hiện việc gì?

Chuẩn hóa được Unicode Standard mô tả bằng các phép **phân rã** (decomposition), **sắp xếp chuẩn các dấu kết hợp** (canonical ordering), và với một số dạng, **tổ hợp lại** (composition).

Một số ký tự có **tương đương chuẩn tắc (canonical equivalence)**, tức có thể được biểu diễn bằng một ký tự mã sẵn hoặc bằng chuỗi gồm ký tự cơ sở + dấu kết hợp. Chuẩn hóa đưa các chuỗi tương đương về cùng cách biểu diễn chuẩn.

~~~text
Nhập 1: é        (U+00E9)
Nhập 2: e + ◌́   (U+0065 U+0301)
         |
         | NFC
         v
Cả hai: é        (U+00E9)
~~~

Điểm quan trọng: **chỉ một số biến đổi được tiêu chuẩn Unicode xem là tương đương chuẩn tắc hoặc tương đương tương thích**. Chuẩn hóa không biến mọi chữ trông giống nhau thành một, không đảm bảo mọi cách viết đồng nghĩa đều bằng nhau và không dịch nội dung.

Một hàm chuẩn hóa theo một dạng cố định thường có tính **idempotent**:

~~~text
normalize(normalize(s, NFC), NFC) = normalize(s, NFC)
~~~

Nếu input đã chuẩn theo NFC, tiếp tục áp NFC không làm thay đổi chuỗi. Nhưng nếu chuyển sang một dạng khác, ví dụ từ NFC sang NFD, hình thức biểu diễn có thể thay đổi.

### Chuẩn hóa không sửa ý nghĩa ngôn ngữ

Chuẩn hóa không thể biết “bank” đang chỉ ngân hàng hay bờ sông; không thể biết từ nào cần dịch. Việc xóa dấu tiếng Việt để tạo khóa tìm kiếm có thể làm nhiều từ khác nghĩa nhập làm một; đó là phép xử lý **mất thông tin**, không phải định nghĩa của NFC.

## 3. Bốn dạng chuẩn hóa: NFC, NFD, NFKC, NFKD

Java `java.text.Normalizer.Form` có bốn giá trị:

| Dạng | Tên | Cơ chế | Đặc điểm |
| --- | --- | --- | --- |
| `NFD` | Canonical Decomposition | Phân rã chuẩn tắc và sắp dấu kết hợp theo thứ tự chuẩn | Thường tách ký tự có dấu thành base + combining marks |
| `NFC` | Canonical Decomposition followed by Composition | Chuẩn hóa chuẩn tắc rồi kết hợp khi hợp lệ | Thường được chọn để lưu/so sánh văn bản tự nhiên |
| `NFKD` | Compatibility Decomposition | Phân rã tương thích, bao gồm các khác biệt biểu diễn tương thích | Có thể thay đổi những phân biệt mang tính hình thức |
| `NFKC` | Compatibility Decomposition followed by Composition | Phân rã tương thích rồi tổ hợp chuẩn tắc | Hữu ích trong một số chính sách định danh/tìm kiếm, **không phải mặc định an toàn cho mọi văn bản** |

Chữ `K` trong `NFKC` và `NFKD` chỉ **compatibility** (tương thích). Hai dạng này có thể loại bỏ sự phân biệt giữa một số ký tự có hình thức đặc biệt và chuỗi tương đương tương thích. **Chúng không phải một dạng “NFC mạnh hơn và luôn tốt hơn”.**

### Ví dụ 1: chữ é

~~~text
Input: "é" (U+00E9)
NFD:   "e" + U+0301
NFC:   "é" (U+00E9)
~~~

Cả hai hình thức đều có thể hiển thị tương tự. Đối với cặp chuỗi tương đương chuẩn tắc, NFC sẽ tạo kết quả bằng nhau; NFD cũng làm như vậy nhưng thiên về dạng phân rã.

### Ví dụ 2: ligature ﬃ

Ký tự ligature `ﬃ` (U+FB03) biểu diễn hình thức liên kết của ba chữ Latin `f`, `f`, `i`:

~~~text
Input:      ﬃ (U+FB03)
NFC:        ﬃ
NFKC:       ffi
~~~

`NFC` không nhất thiết thay ligature này vì nó thuộc nhóm tương đương **tương thích**, không phải tương đương chuẩn tắc. `NFKC` có thể mở rộng nó thành ba ký tự. Kết quả dùng ít ký tự đặc biệt hơn nhưng đã đánh mất sự khác biệt giữa glyph ligature và cách viết ba chữ độc lập.

### Ví dụ 3: chữ Latin fullwidth

~~~text
Input:  Ａ (U+FF21, FULLWIDTH LATIN CAPITAL LETTER A)
NFKC:   A (U+0041)
~~~

Đây là ví dụ điển hình cho compatibility normalization. Nó hữu ích nếu chính sách mã định danh muốn coi hai cách viết là tương đương, nhưng cũng có thể làm mất thông tin kiểu chữ/cách trình bày mà người dùng mong giữ.

### Vì sao không tự dùng NFKC với tên người, bài viết hoặc dữ liệu gốc?

Văn bản gốc có thể chứa các phân biệt hình thức hoặc ký hiệu được chủ ý sử dụng. Nếu tự áp NFKC cho mọi chuỗi trước khi lưu, một số dữ liệu có thể không khôi phục nguyên bản. Hãy quyết định theo **loại trường dữ liệu** và yêu cầu sản phẩm.

Đối với nội dung người dùng viết, có thể **lưu bản gốc** cùng một bản chuẩn hóa dùng cho tìm kiếm hoặc so sánh. Nếu cần bảo toàn chính xác byte ký tên/đã ký số, thậm chí NFC cũng có thể làm thay đổi byte nguồn; tuyệt đối không tự chuẩn hóa sau khi đã ký/đối chiếu hash mà không có quy định giao thức.

## 4. NFC và NFD không giống chuyển mã UTF-8/UTF-16

Ba thao tác thường bị nhầm:

- **Encoding**: Unicode code point được biểu diễn thành byte, ví dụ UTF-8 hoặc UTF-16. Chọn sai charset khi đọc byte có thể tạo văn bản hỏng (*mojibake*).
- **Normalization**: sau khi có `String` Unicode hợp lệ, đưa các chuỗi tương đương chuẩn tắc/tương thích về một dạng.
- **Font shaping/rendering**: quyết định glyph thể hiện ra màn hình, bao gồm font, dấu kết hợp và nhiều đặc điểm hiển thị.

Một chuỗi đã là NFC có thể vẫn bị hiển thị sai nếu font không hỗ trợ ký tự. Một tệp đọc sai charset không tự được “chữa” bằng NFC. Và một chuỗi đúng UTF-8 không nhất thiết đã ở NFC.

Một pipeline dễ hiểu:

~~~text
Byte input --[đọc đúng charset]--> Java String
                |
                v
         [kiểm tra hợp lệ]
                |
                v
        [normalize theo policy]
                |
                v
       [so sánh / lưu / index]
                |
                v
        [render bằng font/UI]
~~~

Các bước có thể diễn ra ở những ranh giới khác nhau tùy hệ thống. Đừng dùng chuẩn hóa Unicode để bù lỗi giải mã byte.

## 5. Chuẩn hóa khác dịch, phiên âm và chuyển tự như thế nào?

| Công việc | Mục tiêu | Ví dụ | Có tự làm bằng `Normalizer` không? |
| --- | --- | --- | --- |
| Chuẩn hóa Unicode | Đưa cách biểu diễn tương đương về dạng xác định | `e + U+0301` → `é` theo NFC | **Có** |
| Dịch thuật (*translation*) | Đổi thông điệp sang ngôn ngữ khác, giữ ý nghĩa phù hợp | “Xin chào” → “Hello” | **Không** |
| Chuyển tự (*transliteration*) | Viết lại âm/chữ từ hệ chữ này sang hệ chữ khác theo quy tắc | Cyrillic → Latin trong một quy ước chuyển tự | **Không** |
| Phiên âm (*phonetic transcription*) | Biểu diễn âm thanh/cách phát âm theo hệ ký hiệu | Một từ → ký hiệu phiên âm IPA | **Không** |
| Bỏ dấu/đơn giản hóa tìm kiếm | Giảm biến thể để tìm kiếm linh hoạt | `á` → `a` theo quy tắc riêng | **Không mặc định** |
| Case folding / xử lý chữ hoa-thường | Chuẩn hóa cách so sánh chữ hoa/chữ thường | `A` / `a` theo policy | **Không phải NFC/NFD** |
| Locale-sensitive collation | Sắp xếp/so sánh văn bản theo ngôn ngữ | Quy tắc so sánh chữ có dấu theo ngôn ngữ | **Không** |

Một ví dụ rõ ràng:

~~~text
"Xin chào" --dịch sang tiếng Anh--> "Hello"
"Xin chào" --bỏ dấu đơn giản-->   "Xin chao"
"Xin chào" --NFC-->              vẫn cùng câu tiếng Việt, ở dạng NFC
~~~

Việc bỏ dấu có thể giúp người dùng gõ tìm kiếm không dấu, nhưng làm **mất khác biệt từ vựng**. Với tiếng Việt, `ma`, `má`, `mà`, `mạ`, `mã`, `mả` là những chuỗi khác nhau; ép về cùng “ma” không phải chuẩn hóa chính tả hay dịch nghĩa.

**Chuyển tự cũng không nhất thiết là một-một hoặc không mất thông tin.** Cách chuyển tên người giữa các hệ chữ có thể phụ thuộc quy ước, ngôn ngữ và mục đích (hộ chiếu, thư viện, bản đồ). NFC không thể tự chọn những quy ước đó.

### NFD + xóa combining mark không phải “chuyển mọi tiếng Việt thành ASCII”

Một mẹo thường thấy là phân rã bằng NFD rồi xóa ký tự có Unicode General Category `Mark`, nhưng đây là **thuật toán bỏ dấu riêng** và làm mất thông tin. Nó còn không tự biến mọi chữ như `đ` thành `d`; không xử lý tổng quát các hệ chữ/đặc điểm phát âm. Không gọi nó là “Unicode normalization” theo nghĩa bảo toàn tương đương.

Trong ứng dụng thật, chỉ dùng thao tác bỏ dấu khi yêu cầu tìm kiếm đã được xác nhận và phải kiểm thử rõ ảnh hưởng đến precision/recall, tên người, mã hàng, dữ liệu pháp lý.

## 6. Java 17+ dùng java.text.Normalizer thế nào?

API chuẩn:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        input,
        Normalizer.Form.NFC);

boolean already = Normalizer.isNormalized(
        input,
        Normalizer.Form.NFC);
~~~

Đây là **đoạn minh họa** có biến `String input` đã được định nghĩa. Hai phương thức được dùng:

- `Normalizer.normalize(CharSequence src, Normalizer.Form form)` trả chuỗi ở dạng được chọn.
- `Normalizer.isNormalized(CharSequence src, Normalizer.Form form)` kiểm tra chuỗi có sẵn ở dạng đó hay chưa.

Đối số null không phải một cách thể hiện “văn bản chưa có”; nên xác nhận đầu vào và dạng normalization trước khi gọi. Phép chuẩn hóa không nên được dùng như “bộ lọc mọi ký tự nguy hiểm”; nó chỉ thực hiện thuật toán được nêu trong hợp đồng.

### Tạo khóa tìm kiếm ổn định

Nếu sản phẩm quyết định tìm kiếm bằng NFC, chuẩn hóa **cả khi lập index và khi nhận truy vấn**:

~~~java
String storedKey = Normalizer.normalize(
        displayName, Normalizer.Form.NFC);
String queryKey = Normalizer.normalize(
        query, Normalizer.Form.NFC);

boolean same = storedKey.equals(queryKey);
~~~

Đây là đoạn minh họa với `String displayName` và `String query` đã có. Chuẩn hóa một phía nhưng không chuẩn hóa phía kia khiến kết quả không nhất quán.

Điều này **không** làm cho `"Alice"` bằng `"alice"`, không tự đồng nhất dấu tiếng Việt khác nhau, và cũng không thay thế công cụ full-text search. Nếu cần so khớp không phân biệt hoa-thường hoặc thứ tự ngôn ngữ, phải thêm chính sách riêng, ví dụ `Collator` hoặc công cụ indexing thích hợp.

## 7. Ví dụ Java 17+ chạy được, với stdout kiểm chứng

Ví dụ dùng Unicode escape để mã nguồn dễ trao đổi giữa các console khác nhau. Nó kiểm tra tương đương chuẩn tắc, chiều dài chuỗi, ligature, chữ fullwidth, tiếng Việt và việc NFC không đổi chữ thường thành chữ hoa.

Tạo tệp **`UnicodeNormalizationDemo.java`**:

~~~java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        String nfcA = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String nfcB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("Raw equals: "
                + composed.equals(decomposed));
        System.out.println("UTF-16 lengths: "
                + composed.length() + " / " + decomposed.length());
        System.out.println("NFC equals: " + nfcA.equals(nfcB));
        System.out.println("NFC idempotent: "
                + nfcA.equals(Normalizer.normalize(
                        nfcA, Normalizer.Form.NFC)));

        String nfd = Normalizer.normalize(
                composed, Normalizer.Form.NFD);
        System.out.println("NFD code points: "
                + nfd.codePointCount(0, nfd.length()));

        String ligature = "\uFB03";
        System.out.println("NFC keeps ligature: "
                + ligature.equals(Normalizer.normalize(
                        ligature, Normalizer.Form.NFC)));
        System.out.println("NFKC expands ligature: "
                + "ffi".equals(Normalizer.normalize(
                        ligature, Normalizer.Form.NFKC)));

        String fullwidthA = "\uFF21";
        System.out.println("NFKC folds fullwidth: "
                + "A".equals(Normalizer.normalize(
                        fullwidthA, Normalizer.Form.NFKC)));

        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        String vietnameseNfd = Normalizer.normalize(
                vietnamese, Normalizer.Form.NFD);
        System.out.println("Vietnamese NFC round-trip: "
                + vietnamese.equals(Normalizer.normalize(
                        vietnameseNfd, Normalizer.Form.NFC)));

        System.out.println("NFC changes case: "
                + "A".equals(Normalizer.normalize(
                        "a", Normalizer.Form.NFC)));
    }
}
~~~

Lưu tệp và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Stdout đã đối chiếu bằng JDK:

~~~text
Raw equals: false
UTF-16 lengths: 1 / 2
NFC equals: true
NFC idempotent: true
NFD code points: 2
NFC keeps ligature: true
NFKC expands ligature: true
NFKC folds fullwidth: true
Vietnamese NFC round-trip: true
NFC changes case: false
~~~

### Giải thích chương trình

1. `composed` là code point `U+00E9`, còn `decomposed` là hai code point `U+0065 U+0301`. Vì vậy `String.equals` chưa chuẩn hóa trả `false`.
2. Hai chuỗi có độ dài UTF-16 lần lượt 1 và 2. Sau NFC, chúng tương đương theo chuỗi ký tự Java, nên `NFC equals` là `true`.
3. Chuẩn hóa NFC lần thứ hai không đổi chuỗi; kết quả `NFC idempotent` là `true`.
4. NFD tách `é` thành hai code point, in `NFD code points: 2`.
5. NFC giữ `ﬃ`, còn NFKC phân rã ký tự đó thành `ffi`; điều này minh họa canonical và compatibility khác nhau.
6. NFKC biến fullwidth `Ａ` thành Latin `A` thường dùng trong ASCII.
7. Chuỗi tiếng Việt chứa dấu được chuyển sang NFD rồi NFC trở lại và bằng chuỗi ban đầu.
8. NFC không thay `"a"` thành `"A"`. Chuẩn hóa không tự xử lý chữ hoa/thường.

Chương trình cố tình in kết quả boolean/ASCII thay vì phụ thuộc font terminal. Unicode escape trong literal Java là một cách viết code point; nó **không** có nghĩa nội dung sau normalize trở thành ASCII.

## 8. Tiếng Việt: dấu thanh, dấu mũ và dấu kết hợp

Tiếng Việt dùng nhiều ký tự có dấu. Ví dụ chữ `ế` có thể được biểu diễn bằng một code point đã được tổ hợp, hoặc dưới dạng chữ cơ sở và những dấu kết hợp theo quy tắc Unicode. Với một số tổ hợp, Unicode còn quy định thứ tự chuẩn của dấu kết hợp để các chuỗi canonically equivalent được xử lý nhất quán.

Ví dụ ở cấp ý tưởng:

~~~text
Hiển thị: “Tiếng Việt”
NFC: ưu tiên cách biểu diễn đã được tổ hợp khi có dạng chuẩn
NFD: dạng phân rã chuẩn tắc, có thể nhiều code point hơn
NFKC/NFKD: có thêm quy tắc compatibility (tùy ký tự)
~~~

Không phải mọi chuỗi tiếng Việt đều có một ký tự duy nhất cho mỗi grapheme. Không dùng quy tắc `String.length() == số chữ nhìn thấy`.

### Nên lưu NFC cho text tiếng Việt?

Trong nhiều hệ thống ứng dụng, **NFC là lựa chọn hợp lý cho dữ liệu văn bản Unicode đã được xác thực**, giúp các chuỗi canonically equivalent so sánh đồng nhất mà vẫn giữ khác biệt giữa các ký tự chỉ tương đương theo compatibility.

Tuy vậy, đó là **một quyết định chính sách dữ liệu**, không phải mệnh lệnh bắt buộc cho mọi ứng dụng. Đặc biệt:

- Dữ liệu cần giữ nguyên văn để phục vụ pháp lý, chữ ký số hoặc kiểm toán có thể phải lưu bản gốc.
- Các hệ thống có chính sách normalization riêng phải thỏa thuận cùng một dạng trên mọi service.
- Không xóa dấu để coi là NFC. Xóa dấu là biến đổi khác và có thể làm sai tên/ý nghĩa.
- Với khóa tra cứu và uniqueness constraint, cần kiểm soát cả normalizer ở ứng dụng lẫn collation của database.

Trong Java, `Normalizer.normalize(text, Form.NFC)` không tự phiên âm `"Đà Nẵng"` thành `"Da Nang"`; việc tạo alias không dấu nếu cần là bước bổ sung, có quy tắc riêng.

## 9. Nên chuẩn hóa tại bước nào của hệ thống?

Cần chọn **ranh giới chuẩn hóa** nhất quán. Một quy trình gợi ý cho dữ liệu văn bản thông thường:

1. Nhận byte từ HTTP/file/database và **giải mã đúng charset** (thường UTF-8 theo hợp đồng).
2. **Kiểm tra input hợp lệ** theo mục đích: giới hạn chiều dài, ký tự điều khiển, trường bắt buộc; xử lý các trường hợp không phải chuỗi Unicode hợp lệ.
3. Áp dạng normalization đã chọn, thường NFC cho nội dung text; có thể dùng NFKC ở những trường định danh chỉ khi đã phê duyệt.
4. Áp các quy tắc **riêng của trường dữ liệu** nếu cần: chuẩn hóa khoảng trắng, case folding, lọc ký tự không cho phép, tạo alias tìm kiếm.
5. Kiểm tra lại các ràng buộc nhạy cảm sau phép biến đổi và lưu dữ liệu theo chính sách.
6. Khi tìm kiếm hoặc đối chiếu, dùng cùng quy tắc chuẩn hóa cho giá trị query và giá trị được index.

Tại sao phải kiểm tra **sau** normalization? Một phép biến đổi tương thích có thể làm thay đổi số code point và kiểu ký tự, chẳng hạn `ﬃ` → `ffi`. Nếu validation chỉ áp trước biến đổi, một số điều kiện về độ dài, ký tự cho phép hoặc uniqueness có thể trở nên sai sau khi chuẩn hóa.

Đừng đưa tất cả xử lý vào một phương thức tên `sanitize` mà không nói rõ từng phép biến đổi. Những bước như NFKC, lowercase, trim, chặn ký tự điều khiển và escape HTML có **mục tiêu khác nhau**; thứ tự của chúng có thể ảnh hưởng kết quả.

### Lưu bản gốc hay bản chuẩn?

| Trường dữ liệu | Chính sách thường cân nhắc |
| --- | --- |
| Nội dung bài viết, văn bản pháp lý | Lưu bản gốc; tạo phiên bản chuẩn hóa riêng cho tìm kiếm nếu cần |
| Tên hiển thị người dùng | Cân nhắc NFC cho so sánh, nhưng bảo toàn bản hiển thị nếu sản phẩm yêu cầu |
| Khóa tra cứu Unicode | Chọn dạng chuẩn hóa cố định và áp ở cả lưu lẫn truy vấn |
| Username/identifier | Thiết kế profile cho phép ký tự, case mapping, normalization, confusables, uniqueness |
| Mã giao dịch do hệ thống tạo | Thường có cú pháp máy cố định; không tự NFKC tùy tiện |
| Chuỗi đã ký/hash | Tuân thủ chính xác giao thức canonicalization; không sửa nội dung sau ký |
| Password | Theo chuẩn/xác thực của hệ thống; không tự normalize nếu hợp đồng không quy định |

Đối với mật khẩu, những biến đổi không được công bố có thể khiến người dùng không đăng nhập được dù họ nhập đúng chuỗi đã đăng ký. Cần xác định một chính sách rõ, nhất quán và phù hợp tiêu chuẩn sử dụng; không áp NFKC tùy hứng.

## 10. Chuẩn hóa không phải bộ giải quyết bảo mật ký tự

Unicode hỗ trợ rất nhiều chữ và ký hiệu có hình thức gần nhau. Ví dụ chữ Latin `a` và một ký tự nhìn tương tự ở hệ chữ khác có thể không canonically equivalent. Chuẩn hóa **không đảm bảo** phát hiện toàn bộ **confusable/homoglyph** và không ngăn mọi tấn công giả mạo tên hiển thị.

Ngoài ra:

- NFKC có thể làm mất phân biệt compatibility mà một số giao thức muốn giữ nguyên.
- NFC không tự xóa ký tự zero-width, không tự loại bỏ ký tự điều khiển và không thay thế kiểm tra script.
- Normalization không thay thế HTML escaping, SQL parameterization, URL encoding hoặc kiểm soát input.
- Kết hợp NFKC với case folding/IDNA hoặc quy tắc username phải tuân thủ **profile cụ thể**; `java.text.Normalizer` không cung cấp một API “NFKC_Casefold toàn diện” tương đương mọi chuẩn định danh.
- Việc chuẩn hóa hai chuỗi thành cùng dạng có thể ảnh hưởng **uniqueness** và quyền sở hữu tên tài khoản; cần xử lý collision có chủ đích.

Nếu sản phẩm hỗ trợ domain name quốc tế hóa, email quốc tế hóa hoặc identifier có yêu cầu an ninh, hãy xem các chuẩn tương ứng như IDNA và Unicode security profiles. Không áp dụng quy tắc của dữ liệu text thông thường cho mọi giao thức định danh.

**Một kết luận sai:** “Đã chuẩn hóa NFC nên tên đăng nhập an toàn”. **Kết luận đúng:** “NFC giúp ổn định các biểu diễn tương đương chuẩn tắc; kiểm tra an ninh tên đăng nhập là bài toán riêng”.

## 11. So sánh, sắp xếp và tìm kiếm theo Locale là việc khác

Nếu cần so sánh văn bản theo **quy tắc ngôn ngữ**, chẳng hạn chữ có dấu và thứ tự sắp xếp, hãy xem `java.text.Collator` với locale phù hợp. `Collator` giải quyết **collation** theo cấu hình; nó không có nghĩa mọi bài toán so khớp đều được giải chỉ bằng NFC.

Nếu cần tìm kiếm linh hoạt:

- NFC giúp hợp nhất một số biểu diễn tương đương chuẩn tắc.
- Case folding/so khớp không phân biệt chữ hoa-thường là một quyết định riêng.
- Bỏ dấu (accent-insensitive search) là một quyết định riêng, có thể làm nhiều từ trùng nhau.
- Phân tách token, stem, từ đồng nghĩa và truy vấn đa ngôn ngữ là các bài toán tìm kiếm khác.
- Dịch query sang ngôn ngữ khác là chức năng **dịch** hoặc truy xuất đa ngôn ngữ, không phải normalization.

Ví dụ `café` và `cafe` **không trở thành một chuỗi bằng nhau chỉ bằng NFC**. Nếu muốn người dùng gõ “cafe” vẫn tìm được “café”, thiết kế một **search key** phù hợp và giữ bản text nguyên gốc để hiển thị.

Không dùng chuỗi đã “ASCII hóa” làm bằng chứng chính tả hoặc bản dịch chuẩn.

## 12. Dữ liệu chuẩn hóa, Unicode version và kiểm thử hồi quy

Cách chuẩn hóa dựa trên dữ liệu Unicode được runtime hỗ trợ. Khi cập nhật JDK, dữ liệu Unicode có thể thay đổi theo phiên bản. Các quy tắc ổn định Unicode được thiết kế để bảo đảm tương thích chuẩn hóa cho các ký tự đã được gán trong những điều kiện nhất định, nhưng một hệ thống nghiêm ngặt vẫn nên kiểm thử tập dữ liệu và phiên bản JDK thực tế.

Các điều nên chú ý:

- Unicode có thể cập nhật bảng ký tự và metadata; hệ thống cần chính sách nâng cấp.
- Kết quả `Normalizer` không chứng minh chuỗi đã qua bộ kiểm tra ngôn ngữ.
- Khi dữ liệu được lưu bởi nhiều service, phải đồng nhất **normalization form** và chính sách ở mọi bên.
- Database có collation riêng: unique index có thể so sánh/đối chiếu khác với `String.equals` của Java.
- Nhập/export CSV/JSON/XML phải quy định charset (byte) và normalization (ký tự) **riêng biệt** nếu cần tương thích tuyệt đối.

### Test nên có

| Nhóm | Ca kiểm thử |
| --- | --- |
| Tương đương chuẩn tắc | `é` vs `e + U+0301`: raw khác, sau NFC bằng |
| Tính idempotent | `NFC(NFC(s)) == NFC(s)` |
| Phân rã | `NFD(é)` gồm `e` và dấu kết hợp |
| Compatibility | `NFKC(ﬃ) == "ffi"`, còn NFC giữ ligature |
| Fullwidth | `NFKC(Ａ) == "A"` |
| Tiếng Việt | Chuỗi có nhiều dấu được NFD rồi NFC round-trip |
| Chữ hoa/thường | NFC không làm `"a"` bằng `"A"` |
| Bỏ dấu | NFC không tự làm `"má"` bằng `"ma"` |
| Khác hệ chữ | Ký tự hình dạng giống nhau không nhất thiết được NFC hợp nhất |
| Độ dài | Đừng giả định `String.length()` bằng số grapheme nhìn thấy |
| Null/input bất thường | Kiểm tra trước khi gọi, validation rõ |
| Tìm kiếm | Query/index dùng cùng form; uniqueness theo chính sách |
| Bảo toàn dữ liệu | Bản gốc không bị ghi đè nếu cần kiểm toán/chữ ký |

Nên viết **test cho các bất biến** thay vì chỉ nhìn hai chuỗi hiển thị có vẻ giống nhau. In code point hoặc hex trong test/debug giúp phát hiện nguyên nhân khác biệt mà mắt thường không phân biệt được.

## 13. Lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `String.equals` để kỳ vọng canonical equivalence tự động | So sánh chuỗi mã UTF-16 trực tiếp | Normalize cả hai phía theo policy |
| Coi NFC là dịch sang tiếng Anh | NFC không hiểu nghĩa | Dùng hệ thống dịch thuật |
| Coi NFC là phiên âm hoặc chuyển tự | Không có quy tắc âm thanh/chữ viết | Dùng transliteration/transcription phù hợp |
| Dùng NFD rồi xóa dấu và gọi là “chuẩn hóa không mất dữ liệu” | Là biến đổi mất thông tin | Tách search alias và văn bản gốc |
| Dùng NFKC cho mọi trường vì “mạnh hơn” | Compatibility folding có thể làm mất khác biệt | Chọn form theo trường và kiểm thử |
| Nghĩ UTF-8 tự bảo đảm NFC | Encoding khác normalization | Xác định cả charset và form |
| Nghĩ NFC chữa được mojibake | Byte đã bị giải mã sai | Sửa charset/nguồn dữ liệu |
| Nghĩ NFC ngăn mọi homoglyph | Confusables không nhất thiết tương đương Unicode | Có identifier/security policy riêng |
| Dùng `length()` làm số chữ hiển thị | UTF-16 code unit khác grapheme cluster | Dùng API phân đoạn grapheme phù hợp |
| Normalize chỉ một phía truy vấn | Bỏ sót match | Áp cùng policy ở index/query |
| Bỏ qua database collation | Uniqueness trong DB có thể khác Java | Kiểm thử và quy định khóa canonical |
| Áp normalization sau khi tạo chữ ký số | Thay đổi bytes/hash | Canonicalize trước ký theo giao thức |
| Nhầm chuyển tự với xóa dấu | Các hệ chữ có quy tắc chuyển khác nhau | Tách yêu cầu và chọn công cụ phù hợp |

## 14. Bài tập tự đánh giá

**Câu 1.** Hai chuỗi cùng hiển thị “é” nhưng `equals` trả `false`. Tình huống nào có thể xảy ra?

**Đáp án:** Một chuỗi chứa `U+00E9`, chuỗi kia chứa `U+0065 U+0301`. Chúng canonically equivalent nhưng không có cùng chuỗi UTF-16. Chuẩn hóa cả hai theo NFC hoặc NFD trước so sánh.

**Câu 2.** Nếu ứng dụng muốn chuyển “Xin chào” thành “Hello”, có dùng `Normalizer.Form.NFKC` không?

**Đáp án:** Không. Đó là bài toán dịch ngôn ngữ, không phải Unicode normalization.

**Câu 3.** Vì sao NFKC có thể đổi ligature `ﬃ` thành `ffi`, còn NFC thường giữ nguyên?

**Đáp án:** `ﬃ` có compatibility decomposition; NFC chỉ xử lý tương đương chuẩn tắc, NFKC thêm tương đương tương thích.

**Câu 4.** Một người dùng nhập “má” và “ma”. NFC có làm chúng bằng nhau không?

**Đáp án:** Không. Dấu thanh ở đây là khác biệt nội dung chữ viết. Việc bỏ dấu để tìm kiếm là chính sách riêng và mất thông tin.

**Câu 5.** Có thể dùng kết quả `Normalizer.isNormalized(text, NFC)` để tuyên bố username an toàn không?

**Đáp án:** Không. Điều đó chỉ cho biết dạng chuẩn hóa, không xác nhận confusables, chính sách script, độ dài, ký tự cấm, quyền sở hữu hoặc các kiểm tra bảo mật khác.

**Bài thực hành:** Viết chương trình nhận hai `String` từ các nguồn khác nhau; in dãy code point dưới dạng hex, so sánh trước/sau NFC, so sánh NFKC và kiểm thử trường hợp chữ fullwidth. Thiết kế schema gồm `displayText` (giữ nguyên bản hiển thị khi cần) và `searchKey` (chuẩn hóa theo chính sách), sau đó viết testcase phát hiện collision khi hai chuỗi nguồn trở thành cùng key.

## 15. Tài liệu tham khảo

- [Normalizer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): `normalize`, `isNormalized` và bốn dạng chuẩn hóa.
- [Normalizer.Form — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.Form.html): NFC, NFD, NFKC, NFKD.
- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `equals` và `codePointCount`.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): định nghĩa chuẩn hóa và tương đương chuẩn tắc/tương thích.
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://unicode.org/reports/tr39/): vấn đề confusables và bảo mật Unicode.
- [Collator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): so sánh ngôn ngữ và sắp xếp, khác với normalization.

**Ghi nhớ:** Chuẩn hóa Unicode làm ổn định **biểu diễn của ký tự**, chứ không đổi **ý nghĩa/ngôn ngữ** và không nhất thiết đổi **hệ chữ**. NFC/NFD bảo toàn tương đương chuẩn tắc; NFKC/NFKD còn xử lý tương đương tương thích và có thể làm mất khác biệt biểu diễn. Hãy chọn form cho từng trường dữ liệu, thống nhất tại các ranh giới hệ thống và giữ các chức năng dịch, phiên âm/chuyển tự, bỏ dấu, tìm kiếm và bảo mật thành những trách nhiệm riêng.
