# Phép đổi hoa–thường có thể đổi độ dài chuỗi trong Java

## 1. Vấn đề cốt lõi: uppercase/lowercase không phải đổi từng char 1:1

Trong một ứng dụng Java hỗ trợ nhiều ngôn ngữ, các phương thức `String.toUpperCase(Locale)` và `String.toLowerCase(Locale)` có thể tạo ra chuỗi **khác độ dài** với chuỗi nguồn. Lý do là Unicode có những quy tắc đổi hoa–thường mà **một ký tự Unicode có thể ánh xạ thành nhiều code point**, hoặc việc ánh xạ thay đổi theo ngôn ngữ và ngữ cảnh đứng trước/sau ký tự.

Ví dụ kinh điển:

~~~text
Đầu vào        : straße
Chữ hoa ROOT   : STRASSE
Độ dài Java    : 6 -> 7 (UTF-16 code units)
Số code point  : 6 -> 7
~~~

Ký tự `ß` (U+00DF, German small sharp s) trong cách viết hoa toàn chuỗi theo Java thường biến thành **hai chữ S**. Vì thế, ý tưởng “đổi từng `char` sang chữ hoa mà không thay đổi số ký tự” là **sai** đối với xử lý chuỗi Unicode.

Một ví dụ chiều ngược lại:

~~~text
Đầu vào               : İ (U+0130, Latin capital I with dot above)
toLowerCase(ROOT)     : i + U+0307 (dấu chấm trên kết hợp)
Độ dài UTF-16         : 1 -> 2
Số code point         : 1 -> 2
toLowerCase(tr-TR)    : i (U+0069), độ dài = 1
~~~

Như vậy, kết quả vừa phụ thuộc **dữ liệu Unicode**, vừa có thể phụ thuộc **Locale**. Người lập trình không nên giả định `uppercase.length() == original.length()`, kể cả khi mã chỉ gọi một phương thức đổi chữ trông đơn giản.

Bài này tập trung vào **phép đổi hoa–thường và ảnh hưởng đến độ dài**: Unicode full case mapping, locale, `String.length()`, code point, vị trí chuỗi, giới hạn dữ liệu và lỗi thường gặp trong ứng dụng localization.

## 2. Hai cấp xử lý: char đơn lẻ và String toàn chuỗi

Java cung cấp nhiều API đổi hoa–thường, nhưng hợp đồng của chúng khác nhau.

| API | Đầu vào/đầu ra | Có thể tạo nhiều code point không? |
| --- | --- | --- |
| `Character.toUpperCase(char)` | Một `char` → một `char` | **Không** |
| `Character.toUpperCase(int)` | Một code point → một code point | **Không** |
| `Character.toLowerCase(int)` | Một code point → một code point | **Không** |
| `String.toUpperCase(Locale)` | Toàn `String` → `String` mới | **Có** |
| `String.toLowerCase(Locale)` | Toàn `String` → `String` mới | **Có** |
| `String.toUpperCase()` / `toLowerCase()` | Toàn chuỗi, dựa vào default Locale | **Có** |

### 2.1. Vì sao Character không đủ cho mọi văn bản?

Các phương thức `Character.toUpperCase(int)` chỉ có thể trả **một giá trị `int`**. Chúng không thể biểu diễn trường hợp một code point thành **hai code point** như ký tự `ß` viết hoa toàn chuỗi. Điều tương tự xảy ra với ánh xạ cần **ngữ cảnh** của cả chuỗi, chẳng hạn sigma trong tiếng Hy Lạp.

Ví dụ minh họa, được đặt trong một phương thức:

~~~java
String whole = "\u00DF".toUpperCase(Locale.ROOT); // "SS"
int simple = Character.toUpperCase(0x00DF);      // U+00DF trong ví dụ
~~~

Đoạn này cần `import java.util.Locale;`. Không được kết luận rằng `Character.toUpperCase` và `String.toUpperCase(Locale)` có cùng hành vi chỉ vì cả hai tên đều là “toUpperCase”.

**Tình huống nguy hiểm:** duyệt bằng vòng `char` rồi viết:

~~~java
for (int i = 0; i < source.length(); i++) {
    out.append(Character.toUpperCase(source.charAt(i)));
}
~~~

Đây chỉ là **snippet minh họa**, giả sử `source` là `String` và `out` là `StringBuilder`. Cách này có thể bỏ qua full mappings, xử lý sai ký tự supplementary nếu tách surrogate, không áp dụng ngữ cảnh ngôn ngữ, và không tương đương với `source.toUpperCase(locale)`.

**Trong phần lớn trường hợp xử lý văn bản**, hãy gọi `String.toUpperCase(locale)` / `String.toLowerCase(locale)` trên **toàn chuỗi**.

### 2.2. String là immutable, không thay đổi giá trị nguồn

~~~java
String original = "Java";
String upper = original.toUpperCase(Locale.ROOT);
~~~

`original` vẫn là `"Java"`; `upper` là `"JAVA"`. Phương thức trả một chuỗi kết quả, không sửa `String` gốc. Khi so sánh length, hãy so giữa hai **biến khác nhau**, không chờ `original.length()` tự đổi.

## 3. Vì sao chữ ß khiến uppercase dài hơn?

Đối với `straße` (tiếng Đức):

~~~text
Các code point gốc:
U+0073 U+0074 U+0072 U+0061 U+00DF U+0065

Các code point viết hoa theo ROOT:
U+0053 U+0054 U+0052 U+0041 U+0053 U+0053 U+0045
~~~

Đầu vào có 6 code point, đầu ra có 7. Vì tất cả code point trong hai chuỗi này đều thuộc BMP và không cần surrogate pair, nên:

~~~java
String original = "stra\u00DFe";
String upper = original.toUpperCase(Locale.ROOT);
System.out.println(original.length()); // 6
System.out.println(upper.length());    // 7
~~~

Ví dụ này nằm trong phương thức, cần import `Locale`. Trong dữ liệu chữ Đức còn tồn tại chữ hoa `ẞ` (U+1E9E), nhưng **không tự suy luận rằng mọi phép đổi chữ hoa toàn chuỗi của Java phải chọn `ẞ`**. Ở chương trình đã kiểm chứng với JDK hiện tại, `String.toUpperCase(Locale.ROOT)` ánh xạ `ß` thành `SS`.

Điều này cũng cho thấy phép đổi không luôn **đảo ngược được**:

~~~text
straße -> STRASSE -> strasse
~~~

Chuỗi cuối `strasse` **khác** `straße`, dù hai chuỗi có thể liên quan về cách đọc và cách viết. Vì vậy không nên dùng uppercase/lowercase rồi kỳ vọng khôi phục lại đúng bản gốc.

### 3.1. Character.toUpperCase không thực hiện phép mở rộng này

~~~java
Character.toUpperCase(0x00DF)
~~~

Trong môi trường Java đã kiểm thử, giá trị trả là `U+00DF`, vì API simple mapping không trả được hai code point `U+0053 U+0053`. Nếu một ứng dụng tự chuyển từng `char`, kết quả có thể khác cách Unicode full mapping đã được `String` thực hiện.

## 4. İ và i: kết quả còn tùy Locale

Một trường hợp nổi tiếng là các chữ I trong tiếng Thổ Nhĩ Kỳ và Azerbaijani. Unicode chứa ít nhất những giá trị cần phân biệt:

| Ký tự | Code point | Ghi chú |
| --- | --- | --- |
| `I` | U+0049 | Latin capital I |
| `i` | U+0069 | Latin small i |
| `İ` | U+0130 | Latin capital I with dot above |
| `ı` | U+0131 | Latin small dotless i |
| Dấu chấm trên kết hợp | U+0307 | Combining dot above |

Với `U+0130`:

- `"\u0130".toLowerCase(Locale.ROOT)` tạo **`U+0069 U+0307`** (hai code point). Phép đổi làm `length()` tăng từ 1 lên 2.
- `"\u0130".toLowerCase(Locale.forLanguageTag("tr-TR"))` tạo **`U+0069`** (một code point).
- `"i".toUpperCase(Locale.ROOT)` tạo **`U+0049`**.
- `"i".toUpperCase(Locale.forLanguageTag("tr-TR"))` tạo **`U+0130`**.

Đây không phải lỗi của Java; nó phản ánh **quy tắc bản địa hóa và full case mapping**. Nếu đổi chữ hoa/thường mà **không truyền `Locale`**, phương thức không tham số dùng default locale của JVM. Một máy chủ đặt `tr-TR` có thể sinh kết quả khác máy đặt `en-US`.

Ví dụ có rủi ro:

~~~java
String normalized = userInput.toLowerCase();
~~~

Trong code minh họa này, việc dựa vào default locale có thể không phù hợp với một khóa dữ liệu cần quy tắc ổn định. Nên lựa chọn:

- Với **văn bản hiển thị theo người dùng**: truyền locale phù hợp, ví dụ `toLowerCase(userLocale)`.
- Với **quy tắc mã định danh cố định**: xác định chính sách chuẩn hóa/canonicalization của hệ thống, thường bắt đầu bằng `Locale.ROOT` nếu cần xử lý chữ hoa/thường kiểu ngôn ngữ trung tính, nhưng **không coi đó là lời giải đầy đủ cho Unicode case folding và bảo mật định danh**.
- Với **giá trị cần giữ nguyên** (mật khẩu, chữ ký, token phân biệt hoa thường, ID có contract case-sensitive): không tự đổi case.

`Locale.ROOT` giúp loại bỏ phụ thuộc vào *default locale*, nhưng không có nghĩa mọi ký tự chuyển đơn giản 1:1 hoặc mọi ngôn ngữ đều có kết quả đúng ý nghĩa văn hóa.

## 5. Ngữ cảnh ký tự cũng ảnh hưởng đến kết quả

Unicode có các ánh xạ đổi case phụ thuộc vị trí trong từ. Một ví dụ là chữ sigma viết hoa của tiếng Hy Lạp:

~~~text
Đầu vào code point : U+039F U+03A3   (ΟΣ)
Viết thường ROOT   : U+03BF U+03C2   (ος)
~~~

Ở cuối từ, sigma thường được đổi thành **final sigma** `U+03C2` thay vì sigma thường `U+03C3`. Việc đổi case tại từng code point riêng rẽ không có đủ **ngữ cảnh** để luôn chọn quy tắc đúng.

Trong ví dụ này số code point và số UTF-16 code units **không đổi**, nhưng ý nghĩa quan trọng vẫn là: **full case conversion có thể phụ thuộc cả chuỗi**, không phải phép toán độc lập trên từng ký tự.

Một số locale khác như Lithuanian cũng có quy tắc dấu kết hợp trong chuyển case; đặc biệt các ký tự có dấu trên dưới có thể khiến chuỗi kết quả có thêm dấu tổ hợp. Do đó không nên suy luận hành vi của toàn bộ Unicode chỉ từ ASCII A–Z.

## 6. length, codePointCount và độ dài hiển thị khác nhau

`String.length()` của Java đếm **đơn vị mã UTF-16**, không phải số ký tự người dùng nhìn thấy. `String.codePointCount(0, s.length())` đếm **Unicode code point** trong khoảng chỉ số UTF-16 đã chọn. **Grapheme cluster** là cụm ký tự người dùng cảm nhận, có thể gồm nhiều code point.

Khi đổi case, cả ba phép đo có thể thay đổi theo những cách khác nhau:

| Trường hợp | `length()` trước → sau | `codePointCount` trước → sau | Giải thích |
| --- | --- | --- | --- |
| `straße` → `STRASSE` | 6 → 7 | 6 → 7 | `ß` trở thành `SS` |
| `İ` → `i` + U+0307 với ROOT | 1 → 2 | 1 → 2 | Một code point thành hai |
| `İ` → `i` với `tr-TR` | 1 → 1 | 1 → 1 | Locale có quy tắc khác |
| `i` → `İ` với `tr-TR` | 1 → 1 | 1 → 1 | Code point đổi, độ dài giữ |
| `ΟΣ` → `ος` | 2 → 2 | 2 → 2 | Thay code point theo ngữ cảnh |

**Lưu ý với Unicode supplementary:** một code point ngoài BMP chiếm **hai `char`** trong UTF-16. Nếu phép đổi case thay thế code point có số đơn vị UTF-16 khác, `length()` có thể thay đổi **không cùng mức** với thay đổi số code point. Hai độ đo này không đồng nhất.

**Lưu ý với dấu tổ hợp:** `i` + `U+0307` có hai code point nhưng có thể được người dùng nhận thức như một chữ có dấu chấm; `codePointCount` không phải bộ đếm grapheme cluster. Với các chuỗi emoji có ZWJ/variation selector hoặc ký tự có dấu, cần chính sách phân đoạn grapheme riêng nếu ứng dụng thật sự giới hạn theo số ký tự nhìn thấy.

### 6.1. Độ dài byte cũng không thể suy từ length()

Khi lưu hay truyền qua UTF-8, số byte được tính riêng:

~~~java
int bytes = value.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
~~~

Đây là đoạn minh họa, `value` là `String` đã khai báo. Với `straße`:

- Có **6** code unit UTF-16.
- Trong UTF-8, năm chữ ASCII và một `ß` (hai byte) tạo **7 byte**.
- `STRASSE` có **7** code unit UTF-16 và **7 byte UTF-8**.

Ví dụ này minh họa thú vị rằng **độ dài Java tăng nhưng số byte UTF-8 không đổi**. Với `U+0130` chuyển thành `i` + `U+0307`, độ dài Java tăng từ 1 đến 2, trong khi UTF-8 tăng từ 2 byte lên 3 byte.

Đừng xem byte count, code unit count, code point count hay grapheme count là các phép đo tương đương. Nếu dữ liệu chứa surrogate lẻ hoặc encoding đầu ra có chính sách thay thế ký tự, việc tính byte còn tùy cách encoder được cấu hình.

## 7. Chương trình Java 17 hoàn chỉnh: đo đầu ra chính xác

Để không phụ thuộc cách terminal gõ chữ Đức, Thổ Nhĩ Kỳ và Hy Lạp, chương trình dùng **Unicode escape trong Java source** và in **mã code point dạng `U+...`**. Ví dụ này có thể chạy với JDK 17 trở lên và không cần thư viện ngoài.

**Tệp `CaseLengthDemo.java`:**

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class CaseLengthDemo {
    static String points(String value) {
        return value.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static void show(String label, String value) {
        System.out.println(label + ": length=" + value.length()
                + ", codePoints=" + value.codePointCount(0, value.length())
                + ", hex=" + points(value));
    }

    public static void main(String[] args) {
        Locale turkish = Locale.forLanguageTag("tr-TR");

        String german = "stra\u00DFe";
        show("german original", german);
        show("german upper ROOT", german.toUpperCase(Locale.ROOT));

        String dottedI = "\u0130";
        show("dotted I original", dottedI);
        show("dotted I lower ROOT", dottedI.toLowerCase(Locale.ROOT));
        show("dotted I lower Turkish", dottedI.toLowerCase(turkish));

        show("i upper ROOT", "i".toUpperCase(Locale.ROOT));
        show("i upper Turkish", "i".toUpperCase(turkish));

        String greek = "\u039F\u03A3";
        show("greek lower ROOT", greek.toLowerCase(Locale.ROOT));
        System.out.println("sharp s vs SS equalsIgnoreCase: "
                + "\u00DF".equalsIgnoreCase("SS"));
        System.out.println("Character.toUpperCase(sharp s): "
                + points(new String(Character.toChars(
                        Character.toUpperCase(0x00DF)))));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CaseLengthDemo.java
java CaseLengthDemo
~~~

**Stdout đã kiểm tra** với dữ liệu Unicode của JDK đã thử:

~~~text
german original: length=6, codePoints=6, hex=U+0073 U+0074 U+0072 U+0061 U+00DF U+0065
german upper ROOT: length=7, codePoints=7, hex=U+0053 U+0054 U+0052 U+0041 U+0053 U+0053 U+0045
dotted I original: length=1, codePoints=1, hex=U+0130
dotted I lower ROOT: length=2, codePoints=2, hex=U+0069 U+0307
dotted I lower Turkish: length=1, codePoints=1, hex=U+0069
i upper ROOT: length=1, codePoints=1, hex=U+0049
i upper Turkish: length=1, codePoints=1, hex=U+0130
greek lower ROOT: length=2, codePoints=2, hex=U+03BF U+03C2
sharp s vs SS equalsIgnoreCase: false
Character.toUpperCase(sharp s): U+00DF
~~~

**Giải thích theo từng nhóm:**

1. **German:** chuỗi gồm 6 code point, `ß` trở thành `SS`, kết quả 7 code point. Phương thức `Character.toUpperCase(0x00DF)` không thực hiện mở rộng `SS`.
2. **Dotted I:** ký tự `U+0130` thành `U+0069 U+0307` khi lower theo ROOT, tăng từ 1 đến 2. Cùng đầu vào lower theo Thổ Nhĩ Kỳ chỉ ra `U+0069`.
3. **i:** viết hoa theo ROOT ra `U+0049`, theo Thổ Nhĩ Kỳ ra `U+0130`. Cả hai có độ dài 1 nhưng **khác code point**.
4. **Greek:** `U+039F U+03A3` chuyển thành `U+03BF U+03C2`, chứng minh tính phụ thuộc ngữ cảnh cuối từ.
5. **equalsIgnoreCase:** `"ß".equalsIgnoreCase("SS")` là `false` trong Java vì `equalsIgnoreCase` không phải phép chuẩn hóa full Unicode case folding để ghép một code point thành hai chữ.
6. **Hex output:** dùng `Locale.ROOT` khi format mã hex và in code point rõ ràng, tránh nhầm do terminal font hoặc thiết lập ngôn ngữ.

Đây là ví dụ kiểm tra **Unicode case mapping**, không phải tài liệu liệt kê mọi quy tắc Unicode. Các ánh xạ Unicode có thể được cập nhật giữa các phiên bản JDK; nên ghim phiên bản runtime trong kiểm thử snapshot nếu ứng dụng phụ thuộc đầu ra chính xác của mọi ký tự.

## 8. Vì sao chuyển case có thể gây lỗi khi cắt và đánh dấu văn bản?

Nhiều API `String` nhận **chỉ số UTF-16**, trong đó có:

- `substring(begin, end)`
- `charAt(index)`
- `codePointAt(index)` (tham số vẫn là chỉ số UTF-16)
- `indexOf(...)` (giá trị trả về vẫn là chỉ số UTF-16)

Giả sử bạn tìm từ khóa trong `straße`, rồi biến đổi toàn chuỗi thành `STRASSE`:

~~~text
Original:  s t r a ß e
UTF-16:    0 1 2 3 4 5
Uppercase: S T R A S S E
UTF-16:    0 1 2 3 4 5 6
~~~

Vị trí chữ `e` đã chuyển từ **index 5 sang index 6**. Nếu ứng dụng giữ offset/selection/annotation từ chuỗi cũ mà đem áp dụng lên chuỗi mới, vùng được tô sáng có thể sai.

### 8.1. Index được tính trên chuỗi nào thì dùng trên chuỗi đó

Các lựa chọn an toàn:

1. Chỉ tìm kiếm và hiển thị trên cùng một **phiên bản văn bản** mà index được sinh ra.
2. Nếu phải hiển thị văn bản đã chuyển case, hãy tính lại index trên kết quả **hoặc** duy trì bảng ánh xạ vị trí từ bản gốc sang bản được chuyển đổi; không suy đoán offset theo phép cộng cố định.
3. Khi nhận offset từ UI hoặc thư viện khác, xác định đó là **UTF-16 offset**, **code point index**, **grapheme index** hay **byte offset**.
4. Với highlight dựa trên so khớp không phân biệt hoa thường, dùng công cụ tìm kiếm/collation và cơ chế theo dõi nguồn phù hợp; đừng chỉ uppercase hai chuỗi rồi dùng index kết quả như index gốc.

**Ngay cả khi code point count không đổi**, chữ viết ngoài BMP hoặc việc chuẩn hóa Unicode có thể tạo thay đổi UTF-16 offsets. Một phép biến đổi văn bản bất kỳ phải được xem là có thể làm lệch index đã lưu.

### 8.2. Không cắt chuỗi trước rồi case-convert tùy tiện

Nếu tách chuỗi ngay trước một ký tự có ngữ cảnh (ví dụ sigma), kết quả case mapping của mỗi mảnh có thể khác việc xử lý toàn câu. Chia văn bản thành từng `char`, từng code point hoặc từng đoạn tùy tiện trước khi đổi case có thể khiến ngữ cảnh **không còn đầy đủ**.

Đặc biệt với giao diện đa ngôn ngữ, hãy quyết định rõ thứ tự: chuẩn hóa theo chính sách, chuyển case phù hợp locale, tìm/đánh dấu, rồi tính giới hạn vị trí sau biến đổi nếu mục tiêu là chuỗi kết quả. Không mặc nhiên dựa vào thao tác từng `char`.

## 9. Độ dài tối đa, lưu trữ và validation

### 9.1. Giới hạn nên áp dụng trước hay sau chuyển case?

Điều này phụ thuộc **dữ liệu nào được lưu và dùng làm canonical value**.

Ví dụ tài khoản có tên hiển thị giới hạn `6` code points trước khi đổi case:

~~~text
Input       : straße   -> 6 code points
Upper ROOT  : STRASSE  -> 7 code points
~~~

Nếu hệ thống lưu **bản uppercase** vào cột/field có giới hạn 6 đơn vị UTF-16, validate input ở trước phép đổi case không đủ: kết quả 7 đơn vị sẽ vượt giới hạn. Ngược lại, nếu hệ thống lưu nguyên văn và chỉ uppercase để **hiển thị**, không cần bắt người dùng đổi tên chỉ vì chuỗi hiển thị tăng độ dài.

Quy tắc thực hành:

- **Nếu lưu bản đã chuẩn hóa:** validate **sau** khi chuẩn hóa/case mapping, theo đúng đơn vị giới hạn của storage/contract.
- **Nếu lưu bản gốc:** kiểm tra bản gốc theo giới hạn nhập; bản hiển thị là sản phẩm phụ cần được render/layout phù hợp.
- **Nếu có giới hạn UTF-8 byte:** đo byte của chính chuỗi sẽ lưu/trao đổi.
- **Nếu giới hạn UI theo ký tự người dùng cảm nhận:** áp dụng Unicode grapheme segmentation, không dùng `length()` làm đại diện.
- **Nếu cần Unicode scalar values hợp lệ:** kiểm tra surrogate lẻ trước khi chuyển đổi/encode; việc đổi chữ không tự xác thực dữ liệu malformed.

Đừng cắt bản uppercase thành 6 `char` để “cho vừa”: ngoài việc làm mất dữ liệu, với ký tự supplementary còn có nguy cơ cắt đôi surrogate pair.

### 9.2. Tính Unicode normalization trước hay sau?

Các biểu diễn Unicode khác nhau có thể trông giống nhau nhưng có số code point và byte khác nhau. `java.text.Normalizer` hỗ trợ NFC, NFD và các dạng chuẩn hóa khác. Khi thiết kế canonicalization:

1. Xác định **chính sách chuẩn hóa** (nếu có), ví dụ NFC, cho loại dữ liệu cụ thể.
2. Chọn **Locale** hoặc quy tắc case folding rõ ràng.
3. Quy định thứ tự biến đổi, kiểm thử các ký tự có dấu/tổ hợp/locale đặc thù.
4. Validate kết quả cuối cùng theo **đúng đại lượng** và giới hạn của storage.
5. Giữ bản gốc nếu nghiệp vụ cần hiển thị hay audit nguyên văn.

Không khẳng định “cứ NFC trước rồi toLowerCase là đảm bảo mọi đầu vào có cùng cách viết sẽ bằng nhau”. Unicode normalization và Unicode **full case folding** là hai quá trình khác nhau; Java `String.toLowerCase(Locale)` không triển khai trọn vẹn toàn bộ case folding cho mọi nhu cầu định danh.

## 10. Case-insensitive comparison không tự động giải quyết mọi bài toán

Java có `String.equalsIgnoreCase(String)`, `compareToIgnoreCase` và `String.CASE_INSENSITIVE_ORDER`. Chúng có ích cho một số so sánh không phân biệt hoa/thường, nhưng **không phải một phép so sánh ngôn ngữ học đầy đủ**.

Ví dụ đã kiểm tra:

~~~java
System.out.println("\u00DF".equalsIgnoreCase("SS")); // false
~~~

Lý do: `equalsIgnoreCase` dùng quy tắc so sánh ký tự theo hợp đồng Java, không tự thực hiện full case folding nhiều-code-point như `ß` → `SS`.

Do đó:

- `a.toUpperCase(locale).equals(b.toUpperCase(locale))` không phải phép thay thế tổng quát cho **Unicode collation/case folding**: còn nhiều chuyện về normalization, dấu, tương đương ký tự, version và chính sách ngôn ngữ.
- `String.equalsIgnoreCase` không hỗ trợ locale như một tham số và không đại diện cho mọi quy tắc tra từ, sắp xếp hoặc so khớp tên người dùng.
- Với việc **sắp xếp/tra cứu từ ngữ theo ngôn ngữ**, nghiên cứu `java.text.Collator` với locale và strength phù hợp. `Collator` giải quyết bài toán collation, nhưng chính sách duy nhất/tính toàn vẹn ID trong database vẫn cần định nghĩa rõ.
- Với **username, email, domain, URL, token, đường dẫn và khóa giao thức**, mỗi miền có quy tắc chuẩn hóa riêng. Không tự áp `toLowerCase(Locale.ROOT)` cho tất cả; có thể gây collision, lỗi bảo mật hoặc phá tương thích.
- Với **password, chữ ký và chuỗi định danh case-sensitive**, phải giữ chính xác giá trị nguyên gốc theo hợp đồng, không biến đổi ngầm.

Việc một phép so sánh bỏ qua case trở thành `true` cũng **không có nghĩa** mọi phiên bản Unicode hoặc locale sẽ diễn giải hai chuỗi giống nhau cho mọi tác vụ. Chuẩn duy nhất trong hệ thống nên được xác định và thử với các trường hợp mở rộng, có dấu và các ký tự khó.

## 11. Locale mặc định, concurrency và tính ổn định

`String.toUpperCase()` và `String.toLowerCase()` không truyền tham số dùng **locale mặc định** của JVM. Trên máy dev, CI, container hoặc server đa ngôn ngữ, default locale có thể khác nhau và có thể bị thay đổi bởi code khác.

~~~java
String key = raw.toLowerCase(Locale.ROOT);
String display = raw.toUpperCase(userLocale);
~~~

Đây là đoạn minh họa, `raw` là `String`, `userLocale` là `Locale`, cần import `Locale`. Với khóa kỹ thuật có chính sách case-insensitive cụ thể, dùng một locale tường minh (thường `ROOT`) giúp tránh sai lệch vì máy chạy. Với văn bản UI, locale theo người dùng có thể cần thiết.

**Không gọi `Locale.setDefault(...)` trên từng request** để đổi ngôn ngữ hiển thị: default locale là trạng thái chung của JVM và có thể làm request khác xử lý văn bản không nhất quán. Hãy truyền locale tường minh và giữ chính sách canonicalization nhất quán.

`String` là immutable và thread-safe khi đọc; tạo chuỗi uppercase/lowercase mới không sửa dữ liệu nguồn. Tuy nhiên nếu **cache một key sau canonicalization**, cần giữ cùng thuật toán/locale/Unicode version theo contract; khi nâng JDK có thể phải kiểm thử lại dữ liệu đã chuẩn hóa.

## 12. Những lỗi thường gặp và cách tránh

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Giả định uppercase luôn giữ nguyên `length()` | `ß` có thể thành `SS` | Kiểm tra length của **kết quả** |
| Giả định lower luôn giữ nguyên số code point | `İ` theo ROOT thành `i` + dấu chấm tổ hợp | Xem locale và full mapping |
| Đổi từng `char` qua `Character.toUpperCase` rồi so với `String.toUpperCase` | Simple mapping không thể mở rộng 1→N | Dùng API toàn chuỗi |
| Dùng default locale cho key kỹ thuật | `I`/`i` sai khác theo `tr-TR` | Chọn locale/canonicalization tường minh |
| Cắt hoặc giữ index từ trước khi đổi case | Vị trí UTF-16 có thể dịch chuyển | Tính lại offset/bảng ánh xạ |
| Dùng `String.length()` để đếm grapheme | Một chữ hiển thị có thể nhiều code point | Dùng grapheme segmentation phù hợp |
| Kiểm tra độ dài trước khi lưu chuỗi đã upper | Kết quả có thể dài hơn | Validate bản thực tế được lưu |
| Nghĩ uppercase rồi lowercase khôi phục nguyên văn | `straße` → `STRASSE` → `strasse` | Giữ bản gốc nếu cần |
| Cho rằng `equalsIgnoreCase` là Unicode full folding | `ß` với `SS` không được coi bằng | Chọn chiến lược comparison theo domain |
| Dùng `toLowerCase` để xử lý password/token tùy tiện | Phá case-sensitive semantics | Theo contract, thường giữ nguyên |
| Đồng nhất code unit với byte UTF-8 | Kích thước byte và Java length khác nhau | Đo bằng charset thực |
| Không có test Unicode/locale sau nâng JDK | Unicode mappings có thể thay đổi | Test hành vi trên runtime hỗ trợ |

## 13. Kiểm thử và bài tập thực hành

Một bộ kiểm thử có ích nên bao gồm:

1. **German sharp s:** `straße` → `STRASSE`, kiểm tra `length` 6 → 7 và `codePointCount` 6 → 7.
2. **Turkish dotted I:** `U+0130` lower theo ROOT ra hai code point `U+0069 U+0307`, theo `tr-TR` ra một `U+0069`.
3. **Turkish small i:** uppercase theo ROOT ra `U+0049`, theo `tr-TR` ra `U+0130`.
4. **Greek final sigma:** một chuỗi toàn chữ hoa kết thúc bằng sigma; kiểm tra lower theo ngữ cảnh không giống thao tác ký tự đơn.
5. **Simple vs full mapping:** `Character.toUpperCase(0x00DF)` không tạo `SS`, còn `String.toUpperCase(Locale.ROOT)` có.
6. **Immutability:** chuỗi nguồn không đổi sau chuyển case.
7. **Byte limit:** so `getBytes(UTF_8).length` trên chuỗi trước/sau.
8. **Index drift:** lưu index của `e` ở `straße`; sau uppercase, kiểm tra index mới.
9. **Grapheme:** `İ` lower ROOT tạo `i` + combining mark; thử bộ phân đoạn grapheme được chọn.
10. **Locale default:** kiểm tra logic dùng locale tường minh không phụ thuộc config máy dev và CI.
11. **Storage:** xác minh giới hạn chuỗi được lưu **sau** canonicalization, không chỉ trước.
12. **Case insensitive semantics:** đối chiếu `equalsIgnoreCase`, uppercase normalization và collation với dữ liệu khó.
13. **Normalization:** tạo chuỗi chữ có dấu ở NFC/NFD; kiểm thử chiến lược chuẩn hóa/case trong hệ thống.
14. **Unicode version:** nếu dữ liệu sản phẩm phụ thuộc mapping chính xác, kiểm thử lại khi nâng Java.

### Bài tập 1 — index bị dịch chuyển

Với `String s = "stra\u00DFe";`:

~~~java
int oldIndex = s.indexOf('e');                     // 5
String changed = s.toUpperCase(Locale.ROOT);       // "STRASSE"
int newIndex = changed.indexOf('E');               // 6
~~~

Đây là snippet minh họa, cần import `Locale`. Giải thích vì sao dùng `oldIndex` trên `changed` sẽ trỏ đến chữ `S` thứ hai, thay vì `E`.

### Bài tập 2 — phép biến đổi không đối xứng

Tạo ba chuỗi:

~~~java
String a = "stra\u00DFe";
String b = a.toUpperCase(Locale.ROOT);
String c = b.toLowerCase(Locale.ROOT);
~~~

So sánh `a.equals(c)`, `a.length()`, `b.length()`, `c.length()`. Kết quả cho thấy chiều biến đổi không đảm bảo khôi phục mã Unicode ban đầu.

### Bài tập 3 — giới hạn kho dữ liệu

Xây hàm nhận một tên hiển thị dài tối đa 6 code point, nhưng lưu bản uppercase. Chứng minh vì sao `straße` vượt giới hạn lưu trữ nếu cột chỉ cho phép 6 code units. Đề xuất quy tắc mới: lưu bản gốc, hoặc kiểm tra chuỗi sau chuẩn hóa, và nêu rõ thông báo cho người dùng.

### Bài tập 4 — locale cố định và locale người dùng

Dùng `Locale.ROOT` và `Locale.forLanguageTag("tr-TR")` đổi case cho `I`, `i`, `İ`, `ı`. So code point/length; đừng so ký tự chỉ bằng mắt. Viết test trong đó locale dùng **tham số tường minh** thay vì thay default JVM.

## 14. Kết luận

**Phép đổi hoa–thường trong Unicode không nhất thiết là phép thay thế một-một.** `String.toUpperCase(Locale)` và `String.toLowerCase(Locale)` có thể **mở rộng một code point thành nhiều code point**, và một số quy tắc tùy thuộc locale hoặc ngữ cảnh toàn chuỗi. Vì Java `String.length()` đếm đơn vị mã UTF-16, độ dài có thể đổi sau phép chuyển case; code point count, grapheme count và byte count cũng là các khái niệm khác nhau.

Trong mã đa ngôn ngữ, hãy truyền `Locale` rõ ràng, dùng API cấp `String` thay vì chỉ đổi từng `char`, không tái sử dụng index cũ sau biến đổi và validate giới hạn trên **chuỗi thực tế sẽ lưu**. Với định danh, truy vấn, so khớp hay bảo mật, chọn đúng chính sách canonicalization/collation theo domain thay vì giả định `toLowerCase` hoặc `equalsIgnoreCase` là giải pháp Unicode tổng quát.

**Tài liệu tham khảo:**

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Character`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html
- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Normalizer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- Java SE 17, `Collator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Unicode Standard, Default Case Algorithms: https://www.unicode.org/versions/latest/core-spec/chapter-3/#G34078
