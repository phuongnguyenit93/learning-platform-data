# Tách dữ liệu nguyên bản, dữ liệu chuẩn hóa và bản hiển thị khi thiết kế API String

## Mục tiêu

Trong ứng dụng thực tế, cùng một chuỗi có thể đảm nhận ba vai trò khác nhau: bằng chứng về những gì người dùng gửi, giá trị đã được chuẩn hóa để tìm kiếm/đối chiếu, và văn bản được hiển thị cho người đọc. Khi gộp cả ba vào một biến `String` rồi liên tục ghi đè, ứng dụng dễ mất dữ liệu, đối chiếu sai hoặc hiển thị không đúng ý người dùng.

Sau bài này, bạn sẽ biết cách:

- Phân biệt **giá trị nguyên bản (raw/original)**, **giá trị chuẩn hóa (normalized/canonical key)** và **giá trị hiển thị (display)**.
- Chọn rõ chính sách cho `strip()`, chuẩn hóa Unicode bằng `Normalizer`, chuyển hoa/thường bằng `Locale` và giới hạn của các phép biến đổi này.
- Thiết kế API Java 17 với dữ liệu bất biến, không đánh mất nguồn gốc.
- Xử lý các tình huống tìm kiếm, kiểm tra trùng, lưu trữ, thay đổi chính sách và bảo mật mà không tự làm hỏng văn bản.
- Viết kiểm thử cho chuỗi Unicode trông giống nhau, khoảng trắng và các giá trị đặc biệt.

## 1. Ba vai trò dữ liệu không nên bị trộn lẫn

Ví dụ người dùng nhập tên hiển thị có dấu cách đầu/cuối và chữ `é` theo dạng chữ `e` cộng dấu kết hợp:

~~~text
Dữ liệu nhận được: "  Café  "
                      ↓
Raw/original:     "  Café  "      // giữ nguyên bản String đã nhận
                      ↓
Normalized key:   "café"          // chính sách ví dụ: strip + NFC + lowercase ROOT
                      ↓
Display value:    "Café"          // chính sách ví dụ: strip + NFC, giữ chữ hoa ban đầu
~~~

Trong ví dụ, `"Café"` dùng hai code point cho `e` và dấu sắc, còn `"Café"` dùng một code point `é`. Mắt thường có thể thấy giống nhau dù chuỗi mã khác nhau.

| Tầng | Câu hỏi mà giá trị trả lời | Điều thường cần bảo toàn |
| --- | --- | --- |
| **Raw** | “Hệ thống đã nhận đúng những gì?” | Ký tự, khoảng trắng, chữ hoa/thường, dấu, thứ tự code unit sau khi giải mã |
| **Normalized** | “Hai giá trị có được coi tương đương cho nghiệp vụ này không?” | Quy tắc chuẩn hóa xác định, có thể tái lập, phù hợp khóa tra cứu |
| **Display** | “Người đọc nên thấy gì trong ngữ cảnh này?” | Dễ đọc, phù hợp locale/ngữ cảnh, không phá dữ liệu gốc |

Đây là **các vai trò**, không phải ba bước bắt buộc cho mọi trường dữ liệu. Một số trường hiển thị đúng nguyên bản; một số khóa định danh không được phép bỏ chữ hoa; một số dữ liệu nhạy cảm phải so khớp chính xác từng byte. API cần định nghĩa chính sách riêng cho từng loại trường.

**Raw trong bài này là `String` sau khi ứng dụng đã giải mã đầu vào.** Nếu yêu cầu là lưu nguyên byte phục vụ chữ ký số, kiểm tra mã hóa hoặc pháp lý, hãy giữ thêm byte gốc và thông tin charset. Một `String` đã được giải mã không bảo đảm tái tạo 100% byte ban đầu khi nguồn có dữ liệu không hợp lệ hoặc dùng nhiều cách mã hóa.

## 2. Vì sao không nên chuẩn hóa đè lên biến gốc?

Cách viết dễ gây mất thông tin:

~~~java
String name = requestName;
name = name.strip();
name = name.toLowerCase();
save(name); // Chỉ còn phiên bản biến đổi; dữ liệu người dùng nhập đã mất.
~~~

Các vấn đề có thể xảy ra:

- `strip()` bỏ khoảng trắng theo `Character.isWhitespace` ở hai đầu. Điều này có thể đúng với tên hiển thị, nhưng sai với nội dung văn bản tự do, mã bảo mật hoặc trường có khoảng trắng mang ý nghĩa.
- `toLowerCase()` không chỉ thay chữ hoa thành chữ thường một cách đơn giản; hành vi mặc định phụ thuộc `Locale.getDefault()` của môi trường, có thể tạo kết quả khác nhau giữa máy hoặc người dùng.
- Chuẩn hóa Unicode có thể thay đổi chuỗi code unit; một số phép chuẩn hóa tương thích còn thay đổi cách trình bày ký tự.
- Khi người dùng muốn xem lại hoặc chỉnh sửa chính xác phần họ đã nhập, bạn không còn nguồn ban đầu.

Mô hình dễ kiểm soát hơn:

~~~java
String raw = requestName;
String normalized = normalizeForLookup(raw);
String display = prepareForDisplay(raw);
~~~

Không nên coi `normalized` là “chuỗi đúng” trong mọi tình huống. Nó là kết quả **theo một chính sách cụ thể**, chẳng hạn khóa tìm người dùng hoặc khóa so sánh tên nhãn. Mỗi chính sách cần mục đích, thứ tự biến đổi và kiểm thử rõ ràng.

## 3. Ví dụ Java 17+: raw, normalized và display

Chính sách minh họa cho **tên nhãn không rỗng**:

1. Giữ nguyên `String` người dùng nhập.
2. Khi tạo giá trị hiển thị, loại khoảng trắng theo `strip()` ở hai đầu và chuẩn hóa Unicode về **NFC**; vẫn giữ cách viết hoa/thường người dùng chọn.
3. Khi tạo khóa tìm kiếm, lấy giá trị đã xử lý ở bước 2 rồi gọi `toLowerCase(Locale.ROOT)` để có khóa ổn định theo locale trung lập.

Lưu chương trình sau vào `TextLayersDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class TextLayersDemo {
    static String toDisplay(String raw) {
        return Normalizer.normalize(raw.strip(), Normalizer.Form.NFC);
    }

    static String toLookupKey(String raw) {
        return toDisplay(raw).toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String raw = "  Cafe\u0301  ";

        String display = toDisplay(raw);
        String key = toLookupKey(raw);

        System.out.println("Raw length: " + raw.length());
        System.out.println("Display: " + display);
        System.out.println("Lookup key: " + key);
        System.out.println("Raw retained: " + raw.equals("  Cafe\u0301  "));
        System.out.println("Same key: "
                + key.equals(toLookupKey("CAFÉ")));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TextLayersDemo.java
java TextLayersDemo
~~~

Kết quả:

~~~text
Raw length: 9
Display: Café
Lookup key: café
Raw retained: true
Same key: true
~~~

Giải thích:

- `"  Cafe\u0301  "` có 9 đơn vị mã UTF-16: hai dấu cách, `C`, `a`, `f`, `e`, một dấu kết hợp và hai dấu cách.
- `strip()` bỏ khoảng trắng đầu/cuối theo chính sách ví dụ.
- `Normalizer.normalize(..., Normalizer.Form.NFC)` hợp nhất dạng `e` + dấu sắc thành `é` khi có dạng tổ hợp chuẩn tương ứng.
- `toLowerCase(Locale.ROOT)` cho `"café"` từ `"Café"`, không phụ thuộc locale mặc định của máy.
- Giá trị `raw` **không bị thay đổi**, vì `String` bất biến; mọi phép biến đổi trả về `String` mới hoặc giá trị có thể dùng lại nếu không cần thay đổi.
- `"CAFÉ"` và `"  Cafe\u0301  "` có cùng khóa theo chính sách hiện tại, nhưng bản hiển thị của chúng vẫn có thể khác nhau.

`Locale.ROOT` phù hợp cho nhiều chính sách khóa không gắn với ngôn ngữ. Nó **không** đồng nghĩa với phép *full Unicode case folding* hoàn chỉnh hay so sánh ngôn ngữ học. Khi tìm kiếm tên người theo tiếng Việt, Thổ Nhĩ Kỳ hoặc ngôn ngữ cụ thể, hãy đánh giá chính sách dựa trên yêu cầu tìm kiếm và collation thực tế.

## 4. Chuẩn hóa Unicode: NFC và NFKC khác nhau thế nào?

Java cung cấp `java.text.Normalizer` với các dạng `NFC`, `NFD`, `NFKC` và `NFKD`:

| Dạng | Mục đích tổng quát | Ví dụ giá trị sử dụng |
| --- | --- | --- |
| `NFC` | Phân rã chuẩn tắc rồi tổ hợp chuẩn tắc | Chuẩn hóa biểu diễn chuỗi văn bản khi muốn bảo toàn tương đương chuẩn tắc |
| `NFD` | Phân rã chuẩn tắc | Phân tích dấu kết hợp hoặc xử lý có yêu cầu riêng |
| `NFKC` | Phân rã tương thích rồi tổ hợp | Khóa có chính sách gộp cả ký tự tương thích |
| `NFKD` | Phân rã tương thích | Xử lý đặc thù cần tách các ký tự tương thích |

**NFC** thường là điểm bắt đầu an toàn hơn cho văn bản thông thường vì hướng tới tương đương chuẩn tắc. **NFKC** có thể gộp các ký tự vốn khác nhau về dạng trình bày/chức năng, nên cần quyết định nghiệp vụ trước khi sử dụng.

Ví dụ Java 17:

~~~java
import java.text.Normalizer;

public class UnicodeFormDemo {
    public static void main(String[] args) {
        String decomposed = "Cafe\u0301";
        String composed = "Café";

        System.out.println(decomposed.equals(composed));
        System.out.println(Normalizer.normalize(
                decomposed, Normalizer.Form.NFC).equals(composed));

        String circledOne = "①";
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFC));
        System.out.println(Normalizer.normalize(
                circledOne, Normalizer.Form.NFKC));
    }
}
~~~

Lưu `UnicodeFormDemo.java` và chạy:

~~~bash
javac -encoding UTF-8 UnicodeFormDemo.java
java UnicodeFormDemo
~~~

Kết quả:

~~~text
false
true
①
1
~~~

Hai cách viết `é` không `equals` nhau ban đầu nhưng bằng nhau sau NFC; `NFKC` biến ký tự số một trong vòng tròn thành `1`, trong khi `NFC` giữ nguyên. Nếu `①` và `1` là hai mã sản phẩm khác nhau, NFKC làm chúng va chạm khóa — vì vậy không áp dụng NFKC rộng rãi mà thiếu chính sách.

### Thứ tự biến đổi có quan trọng không?

Có. `strip`, chuẩn hóa Unicode, chuyển hoa/thường, xóa dấu và thay khoảng trắng không tự động giao hoán trong mọi trường hợp. Hãy **định nghĩa một pipeline chính thức**, kiểm thử nhiều loại dữ liệu và giữ phiên bản của pipeline nếu khóa đã được lưu lâu dài. Ví dụ, nếu chuyển hoa/thường tạo thêm ký tự Unicode, có hệ thống chọn chuẩn hóa về NFC một lần nữa ở cuối để bảo đảm dạng đầu ra mong muốn.

Với ví dụ đơn giản của bài:

~~~text
raw
  ├── raw: giữ nguyên
  ├── display: strip → NFC
  └── lookupKey: strip → NFC → lowercase(Locale.ROOT)
~~~

Đây là một **quy tắc ứng dụng minh họa**, không phải thứ tự bắt buộc do Java áp đặt.

## 5. Tách biến đổi để dùng đúng mục đích

### Trường hợp A: tên hiển thị và khóa tìm kiếm

Một ứng dụng danh mục có thể muốn hiển thị `"Café"` nhưng tìm được khi người dùng gõ `"café"`. Hãy lưu bản đã nhập, hiển thị theo chính sách của sản phẩm và đối chiếu bằng khóa riêng.

~~~text
original    = "  Café "
display     = "Café"
searchKey   = "café"
~~~

Không xóa dấu theo mặc định. Nếu cần tìm không phân biệt dấu, hãy thiết kế thêm **một chỉ mục tìm kiếm** riêng và kiểm thử với ngôn ngữ được hỗ trợ. Xóa toàn bộ dấu kết hợp sau NFD có thể làm thay đổi danh tính từ trong nhiều ngôn ngữ, không bảo đảm tạo cách viết phù hợp cho mọi chữ có dấu.

### Trường hợp B: mã định danh có định dạng quy định

Nếu mã hàng yêu cầu chính xác `[A-Z0-9_-]+`, quy tắc có thể là từ chối khoảng trắng, chữ thường hoặc Unicode không hợp lệ thay vì âm thầm `strip` và viết hoa. Với trường như mã đơn hàng, **validate trước và canonicalize có chủ đích** để tránh hai mã hợp lệ khác nhau bị gộp ngoài ý muốn.

~~~java
static boolean isValidCode(String candidate) {
    return candidate != null
            && candidate.matches("[A-Z0-9_-]+");
}
~~~

Chính sách này coi `"ID_42"` là hợp lệ, còn `" id_42 "` không hợp lệ; đây là **quyết định nghiệp vụ**, không phải giới hạn của API `String`.

### Trường hợp C: nội dung văn bản tự do

Tin nhắn, chú thích, địa chỉ hoặc ghi chú có thể cần bảo toàn xuống dòng, dấu cách và cách viết hoa. Khi đó, raw và display có thể cùng là chuỗi gốc. Một khóa tìm kiếm hoặc chỉ mục全文 có thể được tạo độc lập nhưng không nên ghi đè nội dung tác giả.

### Trường hợp D: mật khẩu, token và dữ liệu ký

Không tự động `trim`, `strip`, chuyển lowercase hoặc Unicode normalize mật khẩu/token nếu giao thức xác thực không quy định rõ. Thay đổi ký tự có thể biến hai bí mật khác nhau thành một, khiến chữ ký không kiểm tra được hoặc phá tương thích. Nơi nào cần xử lý ở mức byte thì giữ đúng biểu diễn byte/protocol; mật khẩu phải được xử lý và lưu bằng cơ chế băm chuyên dụng, không lưu raw trong trường hợp không cần thiết.

## 6. Thiết kế kiểu giá trị bất biến để tránh nhầm lớp dữ liệu

Một cách giảm sai sót là cho đối tượng chứa các lớp thông tin với tên rõ nghĩa. Ví dụ này chọn chính sách của **nhãn danh mục**; không dùng nguyên xi cho mọi loại chuỗi trong hệ thống.

Lưu thành `LabelValueDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

final class LabelValue {
    private final String raw;
    private final String normalizedKey;
    private final String display;

    private LabelValue(String raw) {
        this.raw = Objects.requireNonNull(raw, "raw");

        String prepared = Normalizer.normalize(
                raw.strip(), Normalizer.Form.NFC);

        if (prepared.isEmpty()) {
            throw new IllegalArgumentException("Label must not be blank");
        }

        this.display = prepared;
        this.normalizedKey = prepared.toLowerCase(Locale.ROOT);
    }

    public static LabelValue of(String raw) {
        return new LabelValue(raw);
    }

    public String raw() {
        return raw;
    }

    public String normalizedKey() {
        return normalizedKey;
    }

    public String display() {
        return display;
    }
}

public class LabelValueDemo {
    public static void main(String[] args) {
        LabelValue first = LabelValue.of("  Cafe\u0301 ");
        LabelValue second = LabelValue.of("CAFÉ");

        System.out.println(first.raw().length());
        System.out.println(first.display());
        System.out.println(first.normalizedKey());
        System.out.println(second.display());
        System.out.println(first.normalizedKey()
                .equals(second.normalizedKey()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LabelValueDemo.java
java LabelValueDemo
~~~

Kết quả:

~~~text
8
Café
café
CAFÉ
true
~~~

Ở đây `raw()` luôn trả về dữ liệu ứng dụng đã nhận. `display()` chuẩn bị để hiển thị theo chính sách nhãn; `normalizedKey()` phục vụ đối chiếu, không thay thế bản hiển thị. Các trường `final` giúp giữ ba giá trị nhất quán từ lúc khởi tạo. Không có setter âm thầm đổi một lớp dữ liệu trong khi các lớp còn lại chưa cập nhật.

Đối tượng ví dụ minh họa quy tắc kiểm tra `prepared.isEmpty()`. Trong API thật, bạn còn phải quyết định về độ dài tối đa, ký tự điều khiển, dấu cách không ngắt dòng, các định dạng Unicode đặc biệt và lỗi xác thực. `String.strip()` không loại mọi loại khoảng trắng theo cách con người có thể tưởng tượng; ví dụ một số ký tự `NO-BREAK SPACE` không được `Character.isWhitespace` xem là khoảng trắng để bỏ đi.

**Đừng dùng `normalizedKey` thay cho khóa định danh toàn cục một cách vô điều kiện.** Nếu hai nhãn khác nhau tạo cùng normalized key, chúng có thể được coi trùng trong chức năng tìm kiếm nhưng vẫn là hai bản ghi khác nhau cần định danh riêng bằng ID.

## 7. Thiết kế hợp đồng API: đặt tên và phân tách rõ ràng

Tránh một trường tên chung chung `value` khi sản phẩm có ba mục đích khác nhau. Có thể dùng DTO:

~~~java
public record LabelResponse(
        String original,
        String normalizedKey,
        String displayText) {}
~~~

Đoạn trên là khai báo record Java 17 hợp lệ để minh họa **cấu trúc dữ liệu**; nó không phải chương trình chạy độc lập và không bắt buộc mọi trường đều được trả về cho client.

Một số nguyên tắc thiết kế:

- **Request đầu vào:** dùng tên như `submittedText` hoặc `rawText` khi cần lưu chính xác phần người dùng gửi.
- **Domain/value object:** một factory có chính sách rõ tạo `normalizedKey`; coi chính sách đó là một phần của hợp đồng nghiệp vụ.
- **Response cho giao diện:** thường chỉ gửi `displayText` và ID; không gửi raw nếu raw có thể chứa dữ liệu nhạy cảm hoặc hệ thống không cho phép người xem truy cập.
- **Search/lookup:** có thể nhận truy vấn của người dùng, chuẩn hóa **truy vấn bằng cùng phiên bản chính sách** rồi so khớp với khóa lưu.
- **Audit:** nếu cần chứng minh nguồn nhập, lưu raw theo quy định và kiểm soát truy cập/retention; không nhét dữ liệu bí mật vào log chỉ vì muốn “bảo toàn nguyên bản”.

Một API cũng nên ghi rõ: trả về Unicode theo dạng nào, khóa có phân biệt hoa/thường và dấu hay không, có cho phép chuỗi rỗng không, và chuẩn hóa xảy ra tại thời điểm nhận dữ liệu hay khi tìm kiếm.

## 8. Lưu trữ và tính nhất quán lâu dài

Khi cùng lưu raw, normalized và display trong cơ sở dữ liệu, cần quyết định tầng nào là nguồn gốc và khi nào tái tính:

| Trường dữ liệu | Ví dụ | Nên dùng cho |
| --- | --- | --- |
| `raw_text` | `"  Café  "` | Truy vết dữ liệu đã nhập; chỉnh sửa/cập nhật |
| `normalized_key` | `"café"` | Tìm kiếm, lọc, kiểm tra trùng theo chính sách |
| `display_text` | `"Café"` | Xuất giao diện nếu giá trị đã chuẩn bị được lưu |
| `normalization_version` | `"label-v1"` | Biết khóa được tạo theo chính sách nào khi thay đổi thuật toán |

Trong nhiều hệ thống, có thể **không cần lưu riêng display** nếu nó luôn được suy ra nhanh, xác định từ raw cùng một chính sách. Ngược lại, nếu bản hiển thị là nội dung do biên tập viên chỉnh tay, bản dịch theo `Locale` hoặc kết quả từ dữ liệu nguồn khác, cần mô hình rõ nguồn và vòng đời của nó.

### Khi thay đổi chính sách

Giả sử trước đây khóa chỉ được `strip`, sau này thêm lowercase và NFC:

1. Xác định các khóa mới có tạo **va chạm** hay không: `"Café"`, `"Café"`, `"CAFÉ"` có thể cùng thành `"café"`.
2. Kiểm tra các ràng buộc duy nhất (*unique constraints*) và quyết định cách giải quyết bản ghi va chạm trước khi triển khai.
3. Tái tạo `normalized_key` hoặc xây chỉ mục mới theo phiên bản mới, đồng thời đảm bảo các luồng ghi/đọc dùng đúng phiên bản.
4. Không ghi đè `raw_text` chỉ để cập nhật khóa tìm kiếm.
5. Nếu logic truy vấn và logic lưu dùng khác chính sách, kết quả tìm kiếm sẽ không đáng tin; cần đồng bộ và kiểm thử migration.

**Idempotence** là đặc tính hữu ích: chuẩn hóa một khóa đã chuẩn hóa bằng cùng chính sách nên cho cùng kết quả khi có thể. Tuy nhiên, đừng mặc định mọi chuỗi thao tác tùy biến đều idempotent; hãy kiểm thử, nhất là khi trộn nhiều lần thay dấu/khoảng trắng và chuyển chữ.

### Khoảng cách giữa Java và cơ sở dữ liệu

Java `String.equals` so sánh nội dung code unit; cơ sở dữ liệu có thể dùng collation không phân biệt hoa/thường hoặc dấu. Vì vậy, ngay cả khi `normalizedKey` khác nhau theo Java, unique index theo collation của database vẫn có thể xem chúng như nhau (hoặc ngược lại). Chọn rõ ràng cách lưu, collation, ràng buộc unique và việc chuẩn hóa ở phía ứng dụng. Nếu khóa thực sự yêu cầu so sánh nhị phân xác định, cần cấu hình storage/index phù hợp với hệ quản trị cụ thể.

## 9. Bản hiển thị còn phụ thuộc ngữ cảnh

`displayText` không nhất thiết chỉ là `strip()` rồi NFC. Nó có thể cần:

- Ngôn ngữ hoặc locale người xem: tên ngôn ngữ, số, ngày, tiền tệ và thông điệp có thể khác nhau.
- Quy tắc định dạng giao diện: thêm dấu phân cách, rút gọn chuỗi dài, định dạng đa dòng, hiển thị phiên bản song ngữ.
- Phân quyền: có trường cần che một phần khi hiển thị, trong khi raw được giữ trong vùng dữ liệu bảo vệ.
- Bối cảnh HTML, JSON hay log: mỗi nơi có quy tắc **escaping khi xuất** khác nhau.

Nên phân biệt **biến đổi nội dung mang ý nghĩa hiển thị** với **escape cho ngữ cảnh đầu ra**. Ví dụ, khi đưa `displayText` lên web, giao diện phải bảo đảm dữ liệu văn bản được escape phù hợp để tránh HTML/script injection. Không lưu chuỗi HTML đã escape làm dạng “chuẩn hóa” chung; khi đó hiển thị trên nhiều kênh khác có thể bị double escaping.

Tương tự, dùng prepared statement để truyền giá trị khi truy vấn SQL. Unicode normalization hoặc lowercase không thay thế kiểm soát dữ liệu đầu ra, validation hay phân quyền.

## 10. Các lỗi thường gặp

**1. Chỉ giữ normalized và mất raw.** Người dùng không thể khôi phục cách họ nhập; hệ thống khó truy vết lỗi hoặc áp dụng chính sách mới. Giữ raw khi sản phẩm và quy định lưu trữ cho phép, đồng thời kiểm soát quyền truy cập.

**2. Dùng normalized key để hiển thị.** Nếu `"Nguyễn Văn An"` thành lowercase hoặc bỏ dấu ở khóa tra cứu, hiển thị chính khóa đó sẽ làm sai tên người. Dùng display theo chính sách riêng.

**3. Coi trim/strip là thao tác vô hại.** Khoảng trắng có thể có ý nghĩa trong ghi chú, mã hoặc token; `strip` còn khác `trim` ở tập ký tự xử lý. Xác định quy tắc theo trường dữ liệu, không tạo một hàm `normalizeEverything` cho cả ứng dụng.

**4. Không chỉ định Locale khi chuyển hoa/thường.** `toLowerCase()` dùng locale mặc định và có thể khác nhau giữa môi trường. Với khóa trung lập theo locale, dùng `toLowerCase(Locale.ROOT)`; với văn bản ngôn ngữ cụ thể, đánh giá đúng `Locale` và collation.

**5. Nhầm NFC với NFKC.** NFKC có thể biến ký tự tương thích như `①` thành `1`, làm mất phân biệt không mong muốn. Chọn dạng Unicode theo chính sách, kiểm thử ví dụ gần giống nhưng mang ý nghĩa khác.

**6. Coi lowercasing là case folding/collation đầy đủ.** `toLowerCase(Locale.ROOT)` không tự giải mọi tình huống Unicode/ngôn ngữ. Khi cần so khớp theo ngôn ngữ, cân nhắc `Collator` hoặc công nghệ chỉ mục tìm kiếm phù hợp.

**7. Áp dụng chính sách mới mà không phát hiện khóa trùng.** Việc thêm Unicode normalization và lowercase có thể làm nhiều bản ghi khác nhau cùng khóa. Kiểm tra va chạm, unique index và quá trình chuyển đổi trước khi thay chính sách.

**8. Chuẩn hóa mật khẩu/token/chữ ký tự phát.** Làm vậy thay dữ liệu bí mật hoặc phá chữ ký. Chỉ biến đổi khi đặc tả giao thức yêu cầu.

**9. Tách raw/normalized/display nhưng quên đồng bộ sau khi edit.** Khi người dùng cập nhật raw, phải cập nhật hoặc vô hiệu hóa mọi dẫn xuất tương ứng. Factory bất biến và logic chuyển đổi tập trung giúp giảm lỗi này.

**10. Log cả dữ liệu người dùng mà không chọn lọc.** Raw có thể chứa thông tin cá nhân. Khi cần đo lỗi chuẩn hóa, ưu tiên log mã lỗi, loại biến đổi và thông tin an toàn; quyết định lưu raw theo phân quyền và chính sách dữ liệu.

## 11. Bài tập thực hành và kiểm thử

Với chính sách `strip() → NFC → toLowerCase(Locale.ROOT)` cho lookup, còn display là `strip() → NFC`, dự đoán kết quả:

| Raw đầu vào | Display | Lookup key | Ghi chú |
| --- | --- | --- | --- |
| `"  Café  "` | `"Café"` | `"café"` | Bỏ dấu cách đầu/cuối |
| `"Cafe\u0301"` (dạng tách dấu) | `"Café"` | `"café"` | NFC hợp nhất dạng chuẩn tắc |
| `"CAFÉ"` | `"CAFÉ"` | `"café"` | Giữ hoa ở display |
| `"  "` | `""` | `""` | Ví dụ value object ở trên từ chối display rỗng |
| `"Alice"` | `"Alice"` | `"alice"` | Không phân biệt hoa/thường trong lookup |
| `"alice"` | `"alice"` | `"alice"` | Trùng lookup key với `Alice` |

Có thể dùng chương trình tự kiểm tra sau (lưu vào `TextLayerChecks.java`):

~~~java
import java.text.Normalizer;
import java.util.Locale;

public class TextLayerChecks {
    static String display(String raw) {
        return Normalizer.normalize(raw.strip(), Normalizer.Form.NFC);
    }

    static String key(String raw) {
        return display(raw).toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        String[] inputs = {"  Café  ", "Cafe\u0301", "CAFÉ",
                "  ", "Alice", "alice"};

        for (String input : inputs) {
            System.out.println("[" + display(input) + "] -> ["
                    + key(input) + "]");
        }
    }
}
~~~

Chạy bằng `javac -encoding UTF-8 TextLayerChecks.java` và `java TextLayerChecks`. Kết quả:

~~~text
[Café] -> [café]
[Café] -> [café]
[CAFÉ] -> [café]
[] -> []
[Alice] -> [alice]
[alice] -> [alice]
~~~

Bài mở rộng: tạo một bộ kiểm thử bổ sung cho `null`, dấu cách không ngắt dòng, mã định danh phân biệt hoa/thường, ký tự `①` khi dùng NFC/NFKC, và dữ liệu tiếng Việt có dấu tách. Ghi rõ trường nào được chuẩn hóa, trường nào phải giữ nguyên, trường nào được hiển thị khác raw.

## Checklist trước khi công bố API

1. Định nghĩa chính xác **raw** là chuỗi đã giải mã hay cả byte gốc, dữ liệu đó có cần lưu/audit hay không.
2. Đặt tên và kiểu riêng cho **normalized key**; viết tài liệu về thứ tự pipeline, Unicode form, Locale và phiên bản chính sách.
3. Quyết định **display** dựa trên raw, trên giá trị do người dùng biên tập, hay trên tài nguyên dịch; đảm bảo không vô tình hiển thị khóa lookup.
4. Kiểm tra trùng lặp và collation ở cả Java và database; chuẩn bị cách xử lý va chạm khi thay thuật toán.
5. Đồng bộ dẫn xuất sau khi cập nhật raw, kiểm thử idempotence, Unicode, khoảng trắng, null, giá trị rỗng và chuỗi tương đương.
6. Với mật khẩu, token, dữ liệu ký và thông tin nhạy cảm, tuân thủ hợp đồng bảo mật riêng; không áp dụng pipeline tên hiển thị một cách máy móc.
7. Escape theo ngữ cảnh xuất (HTML/JSON/SQL), phân quyền dữ liệu raw, và tránh log nội dung không cần thiết.

## Tham khảo chính thức

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — Normalizer và các Unicode normalization form](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
