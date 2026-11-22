# Locale.ROOT và dữ liệu không phụ thuộc ngôn ngữ

## 1. Vấn đề: cùng một dữ liệu nhưng khác locale

Một ứng dụng có thể chạy với locale mặc định khác nhau trên máy phát triển, máy chủ và máy kiểm thử. Với nội dung hiển thị cho người dùng, sự khác biệt về cách viết số, ngày và chữ là điều cần thiết. Với dữ liệu kỹ thuật như khóa cấu hình, tên mã trạng thái, định danh giao thức hay bộ lọc nội bộ, việc phụ thuộc ngôn ngữ của máy thường là lỗi.

Ví dụ, chuỗi `TITLE` chuyển thành `title` theo quy tắc chữ thường thông dụng của tiếng Anh, nhưng thành `tıtle` theo tiếng Thổ Nhĩ Kỳ (ký tự `ı` không dấu chấm). Nếu viết `"TITLE".toLowerCase()` không đối số, Java sẽ dùng locale mặc định, khiến cùng một khóa sinh ra các kết quả khác nhau tùy môi trường.

Điều quan trọng là phân biệt hai bài toán: **nội dung cho người đọc** cần locale phù hợp với người đọc; **dữ liệu cho máy** phải tuân theo hợp đồng dữ liệu xác định, độc lập với cấu hình tùy tiện của tiến trình.

## 2. `Locale.ROOT` là gì?

`java.util.Locale.ROOT` là locale gốc, không gắn ngôn ngữ, quốc gia hay biến thể cụ thể. Trong Java:

- `Locale.ROOT.getLanguage()` và `getCountry()` đều trả chuỗi rỗng.
- `Locale.ROOT.toString()` trả chuỗi rỗng.
- `Locale.ROOT.toLanguageTag()` trả `und`: mã BCP 47 cho ngôn ngữ chưa xác định.

ROOT khác `Locale.getDefault()`: locale mặc định có thể thay đổi theo môi trường hoặc do `Locale.setDefault`. ROOT cũng khác `Locale.ENGLISH`: English là ngôn ngữ xác định, còn ROOT không chọn một ngôn ngữ.

Các API như `String.toLowerCase(Locale)`, `String.format(Locale, ...)`, `NumberFormat` hay `Collator` đều có thể nhận locale, nhưng mỗi API có hợp đồng riêng. Truyền ROOT yêu cầu quy tắc của locale gốc cho thao tác cụ thể; nó **không** bảo đảm mọi chuỗi, định dạng hay thao tác so sánh tự động trở thành chuẩn giao thức bất biến.

## 3. Chuyển chữ hoa/thường cho khóa nội bộ

Khi hợp đồng của hệ thống nói một loại khóa kỹ thuật không phân biệt hoa/thường, có thể dùng `toLowerCase(Locale.ROOT)` để tránh phụ thuộc locale mặc định.

```java
import java.util.Locale;

public class LocaleRootDemo {
    public static void main(String[] args) {
        String key = "TITLE";
        Locale turkish = Locale.forLanguageTag("tr-TR");

        System.out.println(key.toLowerCase(turkish));
        System.out.println(key.toLowerCase(Locale.ROOT));

        System.out.println(String.format(Locale.ROOT, "%.2f", 12.5));
        System.out.println(String.format(Locale.FRANCE, "%.2f", 12.5));

        System.out.println("[" + Locale.ROOT + "]");
        System.out.println(Locale.ROOT.toLanguageTag());
    }
}
```

Lưu tệp `LocaleRootDemo.java` bằng UTF-8 rồi chạy với JDK 17+:

```text
javac -encoding UTF-8 LocaleRootDemo.java
java LocaleRootDemo
```

Kết quả:

```text
tıtle
title
12.50
12,50
[]
und
```

Hai dòng đầu minh họa sự khác nhau của quy tắc chữ thường; hai dòng tiếp theo minh họa cách dấu thập phân thay đổi theo locale trong `String.format`. Hai dòng cuối thể hiện ROOT ở dạng chuỗi và language tag.

Hãy chú ý: bản thân `toLowerCase(Locale.ROOT)` không mang ý nghĩa "mọi chữ đều thành ASCII" hoặc "mọi ký tự Unicode đều chỉ chuyển thành một ký tự". Quy tắc Unicode đôi khi có ánh xạ làm thay đổi số ký tự; chuyển hoa/thường cũng không thay thế Unicode normalization.

Nếu chỉ muốn tạo khóa case-insensitive từ các ký tự ASCII do ứng dụng kiểm soát, hãy kiểm tra tập ký tự trước khi chuyển. Còn đối với tên người, từ ngữ tự nhiên và nội dung tìm kiếm, ROOT có thể không phù hợp: chúng cần quy tắc ngôn ngữ và yêu cầu sản phẩm riêng.

## 4. Thiết kế hợp đồng khóa máy rõ ràng

Giả sử mã cấu hình chỉ được dùng `A-Z`, `a-z`, `0-9`, dấu chấm, gạch dưới và gạch nối. Hợp đồng nói khóa không phân biệt hoa/thường và lưu ở dạng lowercase. Ta có thể triển khai:

```java
import java.math.BigDecimal;
import java.util.Locale;

public class MachineKeyDemo {
    static String normalizeKey(String raw) {
        if (raw == null || !raw.matches("[A-Za-z0-9._-]+")) {
            throw new IllegalArgumentException("Invalid machine key");
        }
        return raw.toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(normalizeKey("SERVER.Port"));
        System.out.println(normalizeKey("LOG_LEVEL"));
        System.out.println(new BigDecimal("12.50").toPlainString());
    }
}
```

Lưu thành `MachineKeyDemo.java`, biên dịch và chạy:

```text
javac -encoding UTF-8 MachineKeyDemo.java
java MachineKeyDemo
```

Kết quả:

```text
server.port
log_level
12.50
```

Bước kiểm tra ASCII chủ động từ chối dữ liệu ngoài hợp đồng thay vì đoán cách xử lý. Tất cả thao tác ghi, đọc, so sánh và tra cứu phải dùng cùng quy tắc. `BigDecimal.toPlainString()` là ví dụ cách lấy biểu diễn số thập phân theo cú pháp được xác định bởi API, không thông qua bộ định dạng số theo locale.

**Không phải mọi định danh đều cần lowercase.** Một giao thức có thể quy định phân biệt chữ hoa/thường; khi đó biến đổi ký tự sẽ làm sai dữ liệu. Hãy kiểm tra đặc tả trước khi chuẩn hóa.

### Khi dữ liệu dùng Unicode

Nếu cho phép các chữ cái thuộc nhiều ngôn ngữ, việc đổi hoa/thường bằng ROOT không bảo đảm không có va chạm, không tự gộp các dạng Unicode tương đương và không thay thế `java.text.Normalizer`. Cần công bố rõ:

- Bộ ký tự được phép; có chấp nhận dấu và ký tự kết hợp hay không.
- Có chuẩn hóa Unicode (NFC hoặc NFKC) không, ở bước nào, vì sao.
- Có phân biệt hoa/thường hay không và xử lý va chạm khóa thế nào.
- Quy tắc so sánh của Java, cơ sở dữ liệu, cache và search index có thống nhất không.

Ví dụ, hai khóa trước đây khác nhau có thể trở thành cùng một khóa sau khi đổi chiến lược normalization. Việc thay đổi quy tắc cho dữ liệu đã lưu cần xét tác động đến migration và tính duy nhất.

## 5. Dữ liệu máy không đồng nghĩa mọi thao tác đều dùng ROOT

### Số và tiền tệ

`String.format(Locale.ROOT, "%.2f", 12.5)` trả `12.50`, nhưng đó là **chuỗi được định dạng**, không phải một giá trị số có schema. Nếu API dùng JSON, hãy để thư viện JSON xuất trường number theo đặc tả JSON. Nếu lưu decimal chính xác hoặc đọc một giá trị trong định dạng kỹ thuật đã quy định, `BigDecimal` và cách chuyển đổi theo hợp đồng thường phù hợp hơn.

`NumberFormat.getInstance(Locale.ROOT)` vẫn là một bộ định dạng theo dữ liệu locale gốc. Nó không mặc nhiên chấp nhận mọi cú pháp số, không bảo đảm quy tắc phân tách giống một giao thức bất kỳ. Khi định dạng số, nhóm hàng nghìn hoặc tiền tệ **cho người dùng**, chọn locale người dùng và quy định tiền tệ, thay vì áp ROOT vô điều kiện.

### Ngày giờ

Ngày hiển thị với tên tháng hoặc thứ cần locale người dùng. Ngày giờ trao đổi giữa dịch vụ nên dùng định dạng có hợp đồng rõ ràng như ISO 8601 / RFC 3339 tùy ngữ cảnh; trong Java Time API có `DateTimeFormatter.ISO_INSTANT` để biểu diễn một `Instant`.

Locale **khác** múi giờ. ROOT không tự gắn UTC, không chọn offset, không xử lý daylight saving time. Phải quy định timezone/offset và biểu diễn của thời điểm hoặc lịch ngày một cách riêng biệt.

### Charset

ROOT không quyết định mã hóa byte. Khi giao tiếp hệ thống, quy định charset rõ ràng, thường là `StandardCharsets.UTF_8`. Hai chuỗi Java giống nhau chỉ tạo ra cùng dãy byte khi dùng cùng quy tắc mã hóa; thay locale không thay thế bước này.

### Sắp xếp và so sánh

`Collator` dành cho so sánh/sắp xếp theo quy tắc văn bản và locale. `Collator.getInstance(Locale.ROOT)` vẫn dùng quy tắc collation; nó không tương đương so sánh byte và không hứa thứ tự cố định qua mọi phiên bản JDK hoặc dữ liệu ngôn ngữ.

Với danh sách hiển thị, chọn collation phù hợp người đọc. Với thứ tự kỹ thuật cần tái lập, chọn comparator dựa trên hợp đồng (ví dụ thứ tự ASCII với khóa đã kiểm soát, hoặc quy tắc byte xác định), rồi kiểm thử tính nhất quán trong các hệ thống liên quan.

### So sánh không phân biệt chữ hoa/thường

`String.equalsIgnoreCase` là một API riêng, không tương đương trong mọi trường hợp Unicode với việc gọi `toLowerCase(Locale.ROOT)` trên hai chuỗi rồi `equals`. Đừng mặc định chúng có cùng hành vi hoặc dùng chúng thay thế cho đối chiếu bảo mật. Token bí mật, chữ ký và khóa xác thực cần tuân thủ quy tắc so sánh chính xác của giao thức, không tự động biến đổi hoa/thường.

## 6. Bảng chọn cách xử lý

| Trường hợp | Nên chọn | Giải thích |
| --- | --- | --- |
| Khóa kỹ thuật ASCII, hợp đồng không phân biệt hoa/thường | Kiểm tra ký tự, rồi `toLowerCase(Locale.ROOT)` | Không phụ thuộc locale mặc định |
| Từ ngữ, tên riêng, tìm kiếm cho người dùng | Locale phù hợp và thuật toán ngôn ngữ | Chữ hoa/thường có ý nghĩa trong từng ngôn ngữ |
| Số, ngày, tiền tệ để hiển thị | API định dạng với locale người dùng; thêm currency/time zone khi cần | Tối ưu cho cách đọc của người dùng |
| JSON, timestamp, số trong giao thức | Serializer / formatter theo đặc tả định dạng | Cú pháp giao thức được ưu tiên |
| Truyền dữ liệu ký tự qua mạng/file | Charset cụ thể, ví dụ UTF-8 | Locale không quyết định bytes |
| Thứ tự khóa kỹ thuật cần ổn định | Comparator được định nghĩa trong hợp đồng | Collator ROOT không phải thứ tự byte |

Một ứng dụng tiếng Việt có thể hiển thị số `12,50`, nhưng trao đổi giá trị số JSON dưới dạng `"amount": 12.50`. Cách hiển thị cho người đọc và schema trao đổi là hai trách nhiệm khác nhau. Không lấy output đã địa phương hóa của giao diện đưa thẳng vào trường số API.

## 7. Lỗi phổ biến cần tránh

1. **Dùng `toLowerCase()` hoặc `toUpperCase()` không đối số cho mã nội bộ.** Hành vi bị ảnh hưởng bởi locale mặc định; kiểm thử trên một máy duy nhất dễ bỏ sót lỗi.
2. **Cho rằng `Locale.ENGLISH` là locale vô ngôn ngữ.** English vẫn chọn ngôn ngữ; ROOT diễn đạt rõ hơn ý định không theo ngôn ngữ người dùng.
3. **Xem ROOT là canonicalization hoàn chỉnh cho Unicode.** ROOT không tự chuẩn hóa NFC/NFKC, loại dấu, phát hiện va chạm hay xác định bộ ký tự hợp lệ.
4. **Dùng ROOT cho toàn bộ văn bản người dùng.** Tên riêng, tìm kiếm và từ ngữ tự nhiên có thể cần cách xử lý theo locale xác định.
5. **Dùng `NumberFormat`/ `Collator` với ROOT làm giao thức máy.** Chúng vẫn là các API locale; đặc tả giao thức và bộ serializer mới quyết định output hợp lệ.
6. **Đổi `Locale.setDefault` để sửa một lời gọi.** Đây là trạng thái cấp tiến trình, có thể ảnh hưởng các luồng, thư viện và bài kiểm thử khác. Hãy truyền locale trực tiếp vào API cần dùng.
7. **Bỏ qua tầng database.** Collation ở database hoặc cách chuẩn hóa của chỉ mục có thể khác Java; cùng một dữ liệu phải có chính sách thống nhất.
8. **Thay quy tắc của khóa đã tồn tại mà không đánh giá dữ liệu cũ.** Hai khóa từng phân biệt có thể va chạm sau khi lowercase hoặc normalization; cần tính đến migration.

## 8. Kiểm thử đúng phạm vi

Đối với hàm normalize khóa ASCII, nên có các ca: chữ hoa/thường, chữ số, dấu được phép, chuỗi rỗng, `null`, khoảng trắng, đầu vào ngoài ASCII, khóa khác nhau nhưng chuẩn hóa thành một, và hoạt động nhất quán tại nơi ghi/truy vấn.

Để minh họa sự khác biệt của tiếng Thổ Nhĩ Kỳ, chỉ cần truyền `Locale.forLanguageTag("tr-TR")` vào hàm. Không cần thay `Locale.setDefault` toàn cục. Điều này tránh tác động phụ và làm test ổn định hơn, đặc biệt khi chạy song song.

Một bài kiểm thử tích hợp cần kiểm chứng cùng chính sách trên Java, cơ sở dữ liệu, cache và dịch vụ nhận dữ liệu. Kiểm thử `String.toLowerCase(Locale.ROOT)` đơn lẻ không chứng minh toàn hệ thống đã thống nhất.

## 9. Cách ra quyết định

Khi gặp một chuỗi trong ứng dụng, lần lượt trả lời:

1. **Ai tiêu thụ chuỗi này?** Người dùng: ưu tiên ngữ cảnh ngôn ngữ của họ. Máy: xác định hợp đồng dữ liệu.
2. **Có cần biến đổi chữ hoa/thường không?** Nếu hợp đồng phân biệt hoa/thường thì giữ nguyên. Nếu không phân biệt, chọn quy tắc một cách tường minh.
3. **Bộ ký tự là ASCII hay Unicode?** ASCII có thể có quy tắc đơn giản với ROOT; Unicode cần xem xét normalization, collation và va chạm.
4. **Có đặc tả truyền tải/lưu trữ không?** Với số, ngày giờ, bytes, định dạng theo đặc tả quan trọng hơn chọn một locale chung.
5. **Quy tắc đã được áp dụng ở mọi tầng chưa?** Ghi, đọc, truy vấn, tìm kiếm và migration phải tương thích.

**Ghi nhớ:** `Locale.ROOT` là lựa chọn hữu ích để loại bỏ sự phụ thuộc ngôn ngữ mặc định, đặc biệt khi chuyển hoa/thường của khóa kỹ thuật có quy tắc rõ ràng. Nó không thay thế chính sách Unicode, đặc tả dữ liệu, charset, timezone hay locale của văn bản dành cho người dùng.