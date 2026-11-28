# Kiểm tra định dạng đầu vào — Format validation

## 1. Kiểm tra định dạng trả lời câu hỏi nào?

**Format validation** kiểm tra một giá trị có tuân theo cách biểu diễn mà hệ thống đã công bố hay không. Ví dụ, một mã đơn có phải dạng `ORD-` theo sau bởi đúng tám chữ số ASCII, hoặc một ngày có được viết theo dạng năm-tháng-ngày đã quy định hay không.

Đây là một phần của yêu cầu kiểm tra dữ liệu đầu vào. Nó giúp hệ thống nhận một tập biểu diễn rõ ràng, giảm cách hiểu khác nhau giữa các thành phần và từ chối dữ liệu không thể xử lý đúng hợp đồng.

Tuy nhiên, đúng định dạng không đồng nghĩa với được phép sử dụng:

| Giá trị | Kết luận về định dạng | Điều chưa được chứng minh |
| --- | --- | --- |
| `ORD-00004217` | Đúng mẫu mã đơn trong ví dụ | Mã đã tồn tại, chưa bị dùng lại hoặc thuộc quyền người gọi |
| `2028-02-29` | Là ngày hợp lệ theo hợp đồng lịch trong ví dụ | Ngày đó có nằm trong kỳ giao dịch được phép không |
| `0.00` | Đúng biểu diễn số tiền hai chữ số thập phân | Nghiệp vụ có cho phép tổng tiền bằng 0 không |
| `ZZZ` | Đúng hình dạng ba chữ cái ASCII viết hoa | Đây có phải mã tiền tệ dịch vụ hỗ trợ không |

Một đặc tả chỉ ghi “kiểm tra mã đơn hợp lệ” khiến người triển khai phải đoán đang kiểm tra định dạng, sự tồn tại hay quyền truy cập. Trong thiết kế yêu cầu bảo mật, cần tách các kết luận này để đặt đúng điểm thực thi và bằng chứng nghiệm thu.

OWASP phân biệt tính hợp lệ về cú pháp với tính hợp lệ về ngữ nghĩa, đồng thời khuyến nghị xác định miền đầu vào được chấp nhận. Quy tắc định dạng là một phần của miền đó. [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

Bài học này sử dụng một API nhận đơn từ đối tác làm ví dụ. Mã yêu cầu, endpoint, định dạng và giới hạn được chọn để minh họa việc đặc tả; chúng không phải chính sách mặc định bắt buộc cho mọi ứng dụng.

## 2. Định dạng không chỉ là một biểu thức chính quy

Một chuỗi có thể vượt qua regex nhưng không tạo được một giá trị mà ứng dụng sử dụng được.

Chẳng hạn:

~~~text
[0-9]{4}-[0-9]{2}-[0-9]{2}
~~~

Mẫu này kiểm tra được cấu trúc chữ số và dấu gạch nối. Nó vẫn nhận `2027-02-31` khi được dùng để khớp toàn chuỗi, dù tháng 2 không có ngày 31.

Do đó, nên phân biệt ba tầng:

| Tầng | Mục đích | Ví dụ |
| --- | --- | --- |
| Biểu diễn | Chốt tập ký tự, dấu phân cách, độ dài và quy tắc khoảng trắng | Ngày có đúng 10 ký tự ASCII |
| Cấu trúc | Kiểm tra toàn bộ chuỗi theo ngữ pháp hoặc mẫu | Bốn chữ số, `-`, hai chữ số, `-`, hai chữ số |
| Diễn giải nghiêm ngặt | Tạo được giá trị kiểu dữ liệu theo chính sách đã chọn | Parse thành ngày lịch tồn tại, không tự sửa ngày sai |

Những dự án khác nhau có thể đặt tên “ngày tồn tại” là kiểm tra kiểu hay kiểm tra ngữ nghĩa cơ bản. Tên gọi ít quan trọng hơn việc hợp đồng ghi rõ điều kiện và có ai chịu trách nhiệm thực hiện.

Sau ba tầng này vẫn còn kiểm tra nghiệp vụ, ví dụ “ngày đơn không được nằm trong kỳ đã khóa sổ”. Không nên ép toàn bộ lịch, kỳ giao dịch và quyền thao tác vào một regex lớn.

Có thể diễn đạt điều kiện chấp nhận của một trường dưới dạng:

~~~text
Chấp nhận về định dạng khi:
    kiểu đầu vào đúng
    AND chiều dài trong giới hạn
    AND toàn bộ giá trị tuân cấu trúc
    AND parser nghiêm ngặt tạo được giá trị
    AND không có phép sửa ngầm ngoài hợp đồng.
~~~

Với mã đơn ASCII đơn giản, bước khớp mẫu có thể đã đủ cho phần định dạng. Với ngày, số hoặc địa chỉ có cú pháp phức tạp, parser chuyên dụng thường là một phần cần thiết.

## 3. Viết hợp đồng định dạng đủ rõ

Một yêu cầu định dạng nên trả lời ít nhất các câu hỏi sau:

1. Giá trị được kiểm tra ở đâu: byte trên đường truyền, token của parser hay chuỗi sau giải mã?
2. Kiểu dữ liệu gốc là gì: string, number hay một cấu trúc khác?
3. Trường có bắt buộc không; null và chuỗi rỗng được xử lý thế nào?
4. Tập ký tự và độ dài được phép là gì?
5. Có phân biệt hoa/thường, trim hoặc chuẩn hóa Unicode không?
6. Mẫu phải khớp toàn bộ giá trị hay chỉ một phần?
7. Nếu cần parse, dùng lịch, locale hoặc quy tắc số nào?
8. Khi không đạt, trả lỗi gì và phải dừng trước tác dụng phụ nào?

So sánh hai cách viết:

> Mơ hồ: Ngày phải theo ISO, mã đơn phải đúng regex.

> Có thể kiểm chứng: Trường `orderDate` phải là string sau giải mã JSON, dài đúng 10 ký tự ASCII theo dạng `uuuu-MM-dd`. Năm được phép từ 0001 đến 9999, tháng và ngày phải tạo được một ngày trong lịch ISO. Không nhận giờ, múi giờ, khoảng trắng, dạng rút gọn hoặc ngày được parser tự điều chỉnh.

Cách viết thứ hai không đòi người đọc tự suy ra “ISO” đang chỉ ngày, timestamp, tuần hay ordinal date. Nó cũng loại bỏ một số cách biểu diễn mà thư viện đa dụng có thể hỗ trợ nhưng API không nhận.

Yêu cầu không nhất thiết phải cố định tên một thư viện. Tuy nhiên, nếu hành vi phụ thuộc cấu hình parser, cần ghi cấu hình hoặc tính chất bắt buộc, chẳng hạn “từ chối ngày không tồn tại thay vì điều chỉnh về ngày gần nhất”.

## 4. Hợp đồng minh họa cho đơn từ đối tác

Giả sử `POST /partner-orders` nhận bốn trường bắt buộc dưới dạng JSON string:

~~~json
{
  "externalOrderId": "ORD-00004217",
  "orderDate": "2028-02-29",
  "totalAmount": "1250.00",
  "currency": "USD"
}
~~~

`totalAmount` được thiết kế là string để API kiểm soát chính xác biểu diễn số thập phân. Đây là một lựa chọn hợp đồng của ví dụ, không phải quy định rằng API nào cũng phải biểu diễn tiền bằng JSON string.

### 4.1. Quy tắc cho từng trường

| Trường | Quy tắc định dạng minh họa | Giá trị bị từ chối tiêu biểu |
| --- | --- | --- |
| `externalOrderId` | Đúng 12 ký tự ASCII; literal `ORD-` và tám chữ số `[0-9]` | `ord-00004217`, `ORD-4217`, `ORD-00004217 ` |
| `orderDate` | Đúng `uuuu-MM-dd`, năm 0001–9999, ngày lịch tồn tại | `29/02/2028`, `2027-02-29`, `2028-2-29` |
| `totalAmount` | Phần nguyên 1–9 chữ số; không có số 0 thừa ở đầu; dấu chấm; đúng hai chữ số thập phân | `01.00`, `1,00`, `1.0`, `1e2`, `+1.00` |
| `currency` | Đúng ba chữ cái ASCII viết hoa `[A-Z]{3}` | `usd`, `US`, `USD ` |

Quy tắc áp dụng cho **giá trị string đã được JSON parser giải mã**, không áp dụng trực tiếp bằng regex lên toàn bộ văn bản JSON.

Ví dụ, hai biểu diễn JSON sau tạo cùng giá trị `externalOrderId`:

~~~json
"ORD-00004217"
~~~

~~~json
"\u004FRD-00004217"
~~~

Theo hợp đồng kiểm tra ở cấp giá trị của ví dụ, cả hai đều có thể qua format validation vì `\u004F` được JSON giải mã thành chữ `O`. Điều này không có nghĩa byte của hai request giống nhau. Nếu hệ thống xác minh chữ ký trên byte gốc, phải làm theo giao thức chữ ký riêng, không coi kiểm tra format là canonicalization của tài liệu JSON.

Ngược lại, `"%4FRD-00004217"` là string có ký tự phần trăm sau giải mã JSON. API không tự URL-decode trường này để biến nó thành một mã được chấp nhận.

### 4.2. Điều kiện chung

Cả bốn trường đều không nhận null, thiếu trường, string rỗng hoặc kiểu khác string. Máy chủ không tự chuyển JSON number `1250.00` thành string để cho qua hợp đồng `totalAmount`.

Không trim, đổi hoa/thường, bỏ dấu hoặc chuẩn hóa Unicode cho bốn trường này. Do hợp đồng yêu cầu ASCII, chữ số full-width và chữ cái trông giống từ bộ chữ khác đều nằm ngoài miền chấp nhận.

Các giới hạn được áp dụng trên string đã giải mã:

| Trường | Độ dài tối đa trước regex hoặc parse |
| --- | --- |
| `externalOrderId` | 12 |
| `orderDate` | 10 |
| `totalAmount` | 12 |
| `currency` | 3 |

Trong miền ASCII, số ký tự, số code point và số đơn vị UTF-16 của giá trị bằng nhau. Điều đó không có nghĩa kích thước body trên đường truyền bằng tổng chiều dài các giá trị: escape JSON, tên trường và whitespace vẫn chiếm thêm byte.

Giới hạn body, độ sâu JSON, trường dư và tên trường lặp thuộc hợp đồng cấu trúc của endpoint. Chúng phải được xử lý tại tầng đọc request; validator định dạng trường không thay thế các kiểm soát đó.

## 5. Khớp toàn chuỗi và sai khác giữa các engine

Một lỗi phổ biến là hỏi “chuỗi có chứa một đoạn đúng định dạng không?” trong khi yêu cầu là “toàn bộ chuỗi có đúng định dạng không?”.

Trong Java:

~~~java
Pattern orderId = Pattern.compile("ORD-[0-9]{8}");

boolean contains = orderId.matcher("prefix-ORD-00004217-suffix").find();
boolean complete = orderId.matcher("prefix-ORD-00004217-suffix").matches();
~~~

`contains` cho kết quả true, nhưng `complete` cho kết quả false. Đối với hợp đồng mã đơn ở ví dụ, cần kết luận thứ hai.

Theo tài liệu Java, `matches()` kiểm tra toàn region hiện hành của matcher; region mặc định là toàn input. `find()` tìm một subsequence, còn `lookingAt()` kiểm tra từ đầu region mà không bắt buộc dùng hết nó. [Java SE 21 — Matcher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html).

Do đó, một yêu cầu triển khai có thể ghi:

> Validator phải kiểm tra toàn bộ string sau giải mã. Trong triển khai Java minh họa, tạo matcher mới trên string gốc và gọi `matches()`, không thu hẹp region và không dùng `find()` làm điều kiện chấp nhận.

Không nên sao chép regex từ Java sang frontend, gateway hoặc schema rồi mặc định hành vi giữ nguyên:

- Các engine có thể hỗ trợ tập cú pháp và cờ khác nhau.
- Cách xử lý đầu/cuối dòng phụ thuộc engine, API và chế độ.
- Lớp ký tự viết tắt có thể thay đổi theo cờ Unicode.
- Một số nơi tìm đoạn khớp thay vì yêu cầu toàn bộ giá trị khớp.

Trong Java, ý nghĩa của `\d` và `\w` có liên quan đến cờ `UNICODE_CHARACTER_CLASS`. Nếu hợp đồng yêu cầu chữ số ASCII, ghi `[0-9]` trực tiếp giúp thể hiện đúng ý định hơn là để người đọc suy ra cờ hiện hành. `Pattern` có thể được tái sử dụng; `Matcher` là đối tượng mang trạng thái và không được chia sẻ tùy ý giữa các thread. [Java SE 21 — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html).

JSON Schema cũng là một trường hợp cần chú ý: từ khóa `pattern` có thể khớp ở bất kỳ vị trí nào trong string. Việc chuyển một hợp đồng Java dùng `matches()` sang schema cần bảo toàn điều kiện toàn chuỗi, giới hạn độ dài và các trường hợp newline, thay vì chỉ chép nội dung mẫu. [JSON Schema — String, Regular Expressions](https://json-schema.org/understanding-json-schema/reference/string).

## 6. Parse nghiêm ngặt ngày và số

### 6.1. Ngày: hình dạng đúng chưa đủ

Đối với `orderDate`, regex chỉ giới hạn hình dạng. Sau đó cần tạo `LocalDate` theo cấu hình nghiêm ngặt.

Trong Java, `DateTimeFormatter` phân biệt `u` là year, `y` là year-of-era và `Y` là week-based-year. Đối với hợp đồng ngày trong ví dụ, chọn `uuuu-MM-dd`, không thay bằng `YYYY-MM-dd`. [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

Chế độ resolve cũng là một phần của hành vi. `ResolverStyle.STRICT` từ chối ngày không hợp lệ cho tháng/năm; chế độ `SMART` có thể điều chỉnh ngày vượt quá ngày cuối tháng. Vì vậy, không để chế độ mặc định quyết định thay yêu cầu bảo mật. [Java SE 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).

Một ngày như `2027-02-29` phải thất bại. Validator không được biến nó thành ngày cuối tháng rồi tiếp tục, vì giá trị đó không còn là ý định đã gửi.

Hợp đồng này không chứa giờ hay múi giờ. Không tự lấy múi giờ của máy chủ để diễn giải ngày thành thời điểm. Nếu nghiệp vụ cần timestamp, phải tạo một hợp đồng khác cho offset, độ chính xác, phạm vi và các dạng được chấp nhận.

### 6.2. Số: parser có thể nhận nhiều dạng hơn API

Một parser số đa dụng có thể hỗ trợ biểu diễn mà API không muốn nhận. Vì thế, việc `parse` thành công không luôn chứng minh đúng format.

Với `totalAmount`, ngữ pháp minh họa là:

~~~text
(?:0|[1-9][0-9]{0,8})\.[0-9]{2}
~~~

Mẫu nhận `0.00`, `12.30` và `999999999.99`. Nó không nhận số mũ, dấu cộng, dấu trừ, dấu phân nhóm hàng nghìn hoặc dấu phẩy thập phân.

Sau khi xác nhận toàn bộ chuỗi tuân ngữ pháp và chiều dài, ứng dụng có thể tạo `BigDecimal` trực tiếp từ string. `BigDecimal` biểu diễn giá trị thập phân bằng unscaled value và scale, hỗ trợ parse từ string; parser này tự nó có miền cú pháp rộng hơn hợp đồng số tiền vừa nêu. [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

Không parse qua `double` rồi chuyển sang `BigDecimal` để kiểm tra lại biểu diễn ban đầu: một bước như vậy đã làm mất thông tin về string gốc và có thể thay đổi giá trị thập phân mong muốn.

Tương tự, không làm tròn `"1.234"` về `"1.23"` rồi coi input đạt yêu cầu “đúng hai chữ số thập phân”. Làm tròn là một chính sách nghiệp vụ cần đặc tả riêng; format validation của ví dụ phải từ chối chuỗi gốc.

## 7. Minh họa validator Java theo hợp đồng

Đoạn mã sau dùng các kiểu và API có trong Java 21. Nó minh họa validator của bốn trường sau khi JSON parser đã xác nhận cấu trúc và kiểu string. Đây không phải HTTP server và không thay thế cấu hình parser ở đường vào.

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public final class PartnerOrderFormats {
    private static final Pattern ORDER_ID =
            Pattern.compile("ORD-[0-9]{8}");
    private static final Pattern DATE_SHAPE =
            Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}");
    private static final Pattern AMOUNT =
            Pattern.compile("(?:0|[1-9][0-9]{0,8})\\.[0-9]{2}");
    private static final Pattern CURRENCY =
            Pattern.compile("[A-Z]{3}");

    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public record Raw(
            String externalOrderId,
            String orderDate,
            String totalAmount,
            String currency) {
    }

    public record Parsed(
            String externalOrderId,
            LocalDate orderDate,
            BigDecimal totalAmount,
            String currency) {
    }

    public static Parsed validate(Raw raw) {
        if (raw == null) {
            throw invalid("body");
        }

        requireMatch(raw.externalOrderId(), 12, ORDER_ID,
                "externalOrderId");
        requireMatch(raw.orderDate(), 10, DATE_SHAPE, "orderDate");
        requireMatch(raw.totalAmount(), 12, AMOUNT, "totalAmount");
        requireMatch(raw.currency(), 3, CURRENCY, "currency");

        LocalDate date;
        try {
            date = LocalDate.parse(raw.orderDate(), DATE);
        } catch (DateTimeParseException ex) {
            throw invalid("orderDate");
        }
        if (date.getYear() < 1 || date.getYear() > 9999) {
            throw invalid("orderDate");
        }

        BigDecimal amount = new BigDecimal(raw.totalAmount());

        return new Parsed(
                raw.externalOrderId(), date, amount, raw.currency());
    }

    private static void requireMatch(
            String value, int maximumLength,
            Pattern pattern, String field) {
        if (value == null
                || value.isEmpty()
                || value.length() > maximumLength
                || !pattern.matcher(value).matches()) {
            throw invalid(field);
        }
    }

    private static IllegalArgumentException invalid(String field) {
        return new IllegalArgumentException("INVALID_FORMAT:" + field);
    }
}
~~~

Mẫu và giới hạn chiều dài cùng thực hiện phần biểu diễn. Bộ parse ngày giải quyết tính hợp lệ lịch; bước kiểm tra năm áp dụng chính sách 0001–9999, thay vì nhận năm 0000 mà kiểu lịch có thể biểu diễn.

Mẫu số tiền đã giới hạn cú pháp và chiều dài trước khi tạo `BigDecimal`. Validator trả kiểu có cấu trúc để phần sau không phải parse string lại bằng locale hoặc thư viện khác.

`IllegalArgumentException` chỉ minh họa cách báo lỗi trong phạm vi hàm. Tầng API phải chuyển lỗi thành hợp đồng phản hồi của endpoint, không mặc định trả stack trace hoặc exception message chưa được kiểm soát cho client.

Quan trọng hơn, phương thức `validate` chưa quyết định:

- Mã đơn đã tồn tại hay có được dùng bởi đối tác này không.
- Ngày đơn có nằm trong kỳ được phép không.
- Số tiền có phải lớn hơn 0 hoặc nằm trong hạn mức giao dịch không.
- Mã tiền tệ có thuộc tập được dịch vụ và đối tác hỗ trợ không.

Các điều kiện đó phải được xử lý ở tầng chịu trách nhiệm tương ứng. Không đặt tên kiểu `Parsed` hoặc validator theo cách khiến nhóm hiểu nhầm rằng một đối tượng vượt qua format là đã được phân quyền.

## 8. Unicode, khoảng trắng và sửa đổi ngầm

Quy tắc ASCII trong ví dụ không thích hợp để áp dụng hàng loạt cho họ tên, địa chỉ hoặc ghi chú. Một dịch vụ phục vụ người dùng Việt Nam không nên biến “chỉ nhận ASCII” thành chính sách chung cho mọi trường văn bản.

Cần chọn chính sách theo ý nghĩa dữ liệu:

| Loại trường | Lựa chọn đặc tả hợp lý cần xem xét |
| --- | --- |
| Định danh giao thức do máy cấp | Tập ASCII và biểu diễn cố định nếu giao thức đã quy định như vậy |
| Họ tên hoặc ghi chú | Unicode phù hợp nghiệp vụ, giới hạn tài nguyên và chính sách ký tự điều khiển |
| Bí mật hoặc dữ liệu được ký | Bảo toàn đúng biểu diễn theo giao thức; không tự trim hay biến đổi |
| Mã do người dùng gõ nhưng không phân biệt hoa/thường | Công bố rõ phép chuẩn hóa và cách so sánh |

Ví dụ, `ORD-00004217` và `ＯＲＤ-00004217` trông tương tự nhưng không cùng chuỗi. Nếu hệ thống tự áp dụng một phép chuẩn hóa tương thích trước kiểm tra, nó có thể mở rộng miền input được nhận. Điều đó chỉ phù hợp khi hợp đồng đã cho phép, không phải một thao tác “làm sạch” vô hại.

Tương tự, thêm U+200B ở giữa mã đơn phải bị từ chối theo hợp đồng ASCII, thay vì bị xóa âm thầm rồi nhận. Lỗi trả về chỉ cần chỉ ra trường sai định dạng; không cần phản chiếu ký tự khó nhìn hoặc toàn chuỗi vào log.

Đối với khoảng trắng, yêu cầu nên nêu cụ thể:

> Mã đơn không nhận khoảng trắng trước, sau hoặc bên trong. Giá trị có khoảng trắng không được trim thành mã khác trong quá trình validation.

Nếu sản phẩm muốn hỗ trợ người dùng paste dữ liệu có khoảng trắng, có thể thiết kế bước hỗ trợ trên giao diện hoặc một phiên bản hợp đồng cho phép chuẩn hóa. Khi đó, cần thống nhất giá trị được hiển thị, gửi, kiểm tra, lưu và so sánh.

Việc decode cũng phải theo ngữ cảnh. String trong JSON không tự trở thành URL chỉ vì chứa `%`; một tên file không được decode lặp nhiều lần trước mỗi thao tác. Yêu cầu định dạng phải chỉ ra biểu diễn nào đã được kiểm tra để thành phần sau không tiếp tục biến đổi thành một giá trị khác.

## 9. Các định dạng phức tạp cần hợp đồng chuyên biệt

Không nên mở rộng regex mã đơn thành một “regex an toàn cho mọi trường”. Một số định dạng đòi hỏi quyết định riêng:

| Trường | Kết luận format có thể cung cấp | Kiểm soát khác vẫn cần |
| --- | --- | --- |
| Email | Cú pháp phù hợp tập địa chỉ dịch vụ hỗ trợ | Khả năng nhận thư và quyền sở hữu qua quy trình xác minh |
| URL | Parser tạo được URL với cấu trúc được phép | Chính sách truy cập đích, redirect và bảo vệ SSRF nếu server đi tới URL |
| UUID | Chuỗi tuân biến thể biểu diễn mà API nhận | Phiên bản/variant nếu giao thức yêu cầu, sự tồn tại và quyền truy cập |
| Số điện thoại | Chuỗi tuân quy ước biểu diễn đã chốt | Tính khả dụng, quốc gia hỗ trợ và xác minh chủ thuê bao nếu cần |
| Tên file | Tên tuân chính sách ký tự và chiều dài | Đường dẫn lưu, quyền ghi, nội dung file và cách phục vụ file |

Bảng này là cách phân ranh yêu cầu, không cung cấp một validator hoàn chỉnh cho từng loại. Khi chọn parser hoặc thư viện, phải đối chiếu tập biểu diễn mà nó nhận với hợp đồng ứng dụng.

Ví dụ, viết “URL hợp lệ” không nói ứng dụng có nhận URL tương đối hay không, có bắt buộc HTTPS không và có được nhận user-info không. Những lựa chọn ấy phải được làm rõ trước khi triển khai.

Với email, một regex chỉ kiểm tra có một dấu `@` không đủ để tuyên bố đã hỗ trợ mọi cú pháp cần thiết. Ngược lại, cố viết regex bao phủ mọi dạng địa chỉ mà không xét khả năng gửi thư của hệ thống cũng tạo một hợp đồng thiếu thực tế. Cần chốt tập hỗ trợ, giới hạn và bước xác minh riêng.

Với UUID, cần phân biệt “thư viện parse được” với “đúng dạng canonical mà API công bố”. Nếu API yêu cầu chữ hex thường và dấu gạch nối tại vị trí cố định, phải có điều kiện bảo toàn yêu cầu đó; không chỉ dựa vào việc parser không ném exception.

## 10. Chi phí xử lý là một phần của thiết kế định dạng

Một validator định dạng chạy trên đầu vào do bên ngoài điều khiển cũng là một phần của bề mặt tiêu thụ CPU và bộ nhớ. Đặc tả không nên chỉ hỏi kết quả true hay false.

Ví dụ, dùng mẫu có nhiều lớp lặp chồng lên nhau trên string rất dài có thể tạo chi phí khớp không mong muốn trong một engine backtracking. Hợp đồng nên đặt giới hạn chiều dài trước regex, chọn mẫu đơn giản và kiểm chứng hành vi với dữ liệu gần khớp. OWASP nêu các biện pháp này trong hướng dẫn kiểm tra regex. [OWASP Input Validation — Regular Expressions](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

Đối với ví dụ đơn đối tác:

- Mã đơn có độ dài tối đa 12 và cấu trúc cố định.
- Ngày chỉ có 10 ký tự trước khi parse.
- Số tiền chỉ có tối đa 12 ký tự trước khi tạo giá trị số.
- Mã tiền tệ chỉ có 3 ký tự.

Những giới hạn này được chọn từ miền dữ liệu mong muốn, không từ việc regex có thể xử lý được một chuỗi dài bao nhiêu.

Cũng cần giới hạn request trước khi parser tạo các string. Việc gọi `value.length()` sau khi toàn body đã được đọc không thay thế giới hạn body ở tầng transport.

Không nhận mẫu regex tùy ý từ client để sử dụng như chính sách kiểm tra trên đường xử lý request này. Nếu sản phẩm thật sự có chức năng cấu hình mẫu, đó là một tính năng khác cần phạm vi quyền, giới hạn engine, phiên bản và ngân sách xử lý riêng.

Nếu đặt mục tiêu thời gian kiểm tra, phải nêu môi trường, kích thước dữ liệu và cách đo. Câu “regex phải nhanh” không thể dùng để nghiệm thu. Mục tiêu hiệu năng nên được xác định cùng yêu cầu tải của dịch vụ, không lấy một thời gian duy nhất làm bảo đảm cho mọi máy chủ.

## 11. Chuyển hợp đồng thành yêu cầu bảo mật

Các yêu cầu dưới đây liên kết những quyết định format với rủi ro và cách xác minh:

| ID minh họa | Rủi ro cần xử lý | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| FMT-001 | Chấp nhận tiền tố/hậu tố ngoài mã hợp lệ | Khớp toàn string `externalOrderId`, không chỉ tìm đoạn mã | Chuỗi có tiền tố hoặc hậu tố đều thất bại |
| FMT-002 | Các hệ thống hiểu khác kiểu dữ liệu | Chỉ nhận bốn trường ở kiểu string theo hợp đồng | JSON number, boolean, array và object không bị ép thành string |
| FMT-003 | Parser tự sửa ngày sai | Parse ngày nghiêm ngặt; không điều chỉnh về ngày khác | `2027-02-29` thất bại; không tạo đơn ngày 28/02 |
| FMT-004 | Locale làm đổi ý nghĩa số | Chỉ nhận dấu chấm và hai chữ số thập phân | `1,00`, `1.0`, `1e2` bị từ chối |
| FMT-005 | Chuỗi tương tự bị coi nhầm định danh | Không trim, đổi case hoặc chuẩn hóa mã ASCII ngoài hợp đồng | Khoảng trắng, chữ full-width và ký tự ẩn bị từ chối |
| FMT-006 | Một trường gây chi phí parse không giới hạn | Giới hạn chiều dài trước regex và parser giá trị | Chuỗi quá dài bị từ chối trước bước parse trường |
| FMT-007 | Dữ liệu bị kiểm tra rồi được diễn giải khác | Dùng giá trị đã parse hoặc cùng chính sách trong phần xử lý tiếp | Không parse lại số/ngày theo locale khác |
| FMT-008 | Request sai vẫn tạo thay đổi | Dừng trước tạo đơn và phát sự kiện nghiệp vụ | Số bản ghi và sự kiện tạo đơn cho request thất bại bằng 0 |

Phân công cần gắn với nơi có thể quan sát điều kiện. Ví dụ, khi mapper đã chuyển một JSON number thành string, validator phía sau không còn biết kiểu gốc. FMT-002 phải được bảo đảm tại parser/mapper chứ không thể chỉ kiểm tra lại nội dung string.

Tương tự, kiểm tra định dạng trong frontend giúp phản hồi sớm nhưng không chứng minh endpoint tuân hợp đồng khi request được gửi trực tiếp. Máy chủ là nơi phải thực thi điều kiện chấp nhận của API.

Đối với đường nhập message hoặc file, cần ánh xạ lại cùng hợp đồng giá trị vào cơ chế tiếp nhận tương ứng. Không kết luận mọi đường vào đã được bảo vệ chỉ vì một controller HTTP gọi validator.

## 12. Hành vi lỗi và khả năng quan sát

Trong API minh họa, nhóm chọn trả `400` với mã `INVALID_FORMAT` khi một trường sai định dạng. Đây là lựa chọn hợp đồng của ví dụ; dự án cần dùng quy ước lỗi nhất quán của mình.

~~~json
{
  "code": "INVALID_FORMAT",
  "requestId": "server-generated-id",
  "errors": [
    {
      "field": "orderDate",
      "expected": "DATE_YYYY_MM_DD"
    }
  ]
}
~~~

Mã `DATE_YYYY_MM_DD` trong response chỉ là mã hiển thị cho hợp đồng ngày; nó không phải chuỗi pattern Java để lập trình viên sao chép. Pattern Java của ví dụ vẫn là `uuuu-MM-dd`.

Phản hồi nên giúp client sửa lỗi nhưng không cần lặp lại nguyên giá trị bị từ chối. Với trường có thể chứa dữ liệu nhạy cảm hoặc ký tự điều khiển, phản chiếu input còn tạo thêm vấn đề cho log hoặc giao diện hiển thị lỗi.

Bản ghi vận hành có thể chứa:

~~~json
{
  "event": "format_validation_failed",
  "ruleId": "FMT-003",
  "field": "orderDate",
  "reason": "INVALID_CALENDAR_DATE",
  "contractVersion": "partner-orders-v1",
  "requestId": "server-generated-id"
}
~~~

Tên trường và reason code lấy từ tập hữu hạn của hợp đồng, không lấy tùy ý từ client. Không đưa raw input làm tên metric hoặc nhãn có số lượng giá trị không giới hạn.

Đặc tả cũng cần quyết định trả lỗi đầu tiên hay một tập lỗi bị giới hạn. Nếu trả lỗi đầu tiên như đoạn Java minh họa, không được dùng thứ tự lỗi để suy ra request đã hợp lệ ở các bước chưa chạy. Một field sai đủ để từ chối request; các field còn lại có thể chưa được đánh giá.

Khi dịch thông báo lỗi sang ngôn ngữ khác, mã hợp đồng cần ổn định để client tích hợp. Không dùng nội dung exception của parser làm API công khai vì nội dung đó có thể thay đổi khi nâng phiên bản thư viện.

## 13. Tiêu chí nghiệm thu và ca biên

Bảng dưới đây mô tả các ca cần thiết để nghiệm thu hợp đồng minh họa. Nó là đặc tả kiểm thử, không phải kết quả đã thực thi.

| Ca | Dữ liệu | Kết quả mong đợi |
| --- | --- | --- |
| T01 | `ORD-00004217` | Qua định dạng mã |
| T02 | `prefix-ORD-00004217` | Bị từ chối; không dùng substring hợp lệ |
| T03 | `ORD-00004217-suffix` | Bị từ chối |
| T04 | `ord-00004217` | Bị từ chối; không đổi hoa ngầm |
| T05 | Mã có một space, tab hoặc newline ở cuối | Bị từ chối |
| T06 | `ORD-` với 7 hoặc 9 chữ số | Bị từ chối |
| T07 | Chữ số full-width hoặc U+200B trong mã | Bị từ chối theo miền ASCII |
| T08 | JSON escape `\u004F` thay cho `O` ở đầu mã | Qua định dạng giá trị sau giải mã |
| T09 | Literal `%4F` thay cho `O` trong JSON string | Bị từ chối; không URL-decode |
| T10 | `2028-02-29` | Parse được ngày lịch hợp lệ |
| T11 | `2027-02-29` hoặc `2028-04-31` | Bị từ chối; không tự điều chỉnh |
| T12 | `2028-2-9`, `29/02/2028` | Bị từ chối do biểu diễn khác |
| T13 | `0000-01-01` | Bị từ chối do chính sách năm |
| T14 | `0001-01-01`, `9999-12-31` | Qua hợp đồng định dạng ngày; còn kiểm tra nghiệp vụ |
| T15 | Ngày nối thêm giờ hoặc offset | Bị từ chối; field không phải timestamp |
| T16 | `0.00`, `1.00`, `999999999.99` | Qua định dạng số tiền |
| T17 | `1000000000.00` | Bị từ chối do phần nguyên vượt giới hạn |
| T18 | `01.00`, `+1.00`, `-1.00`, `1e2` | Bị từ chối |
| T19 | `1,00`, `1.0`, `1.000` | Bị từ chối; không đổi locale hoặc làm tròn |
| T20 | JSON number thay vì string số tiền | Bị từ chối ở tầng kiểm tra kiểu |
| T21 | `USD` và `usd` | `USD` qua format; `usd` bị từ chối |
| T22 | `ZZZ` | Qua hình dạng currency; tập hỗ trợ được kiểm tra riêng |
| T23 | Thiếu/null/rỗng ở một trường bắt buộc | Bị từ chối |
| T24 | Một trường rất dài nhưng có tiền tố đúng | Bị từ chối trước regex hoặc parse trường |
| T25 | Payload sai định dạng chứa dữ liệu nhạy cảm | Không có bản ghi đơn; response/log không phản chiếu raw value |

Với ngày, thêm ca kiểm thử ở thời điểm chuyển năm giúp phát hiện việc vô tình dùng year theo tuần. Với số, kiểm tra trên các locale triển khai khác nhau giúp chứng minh cấu hình máy chủ không làm thay đổi miền chấp nhận.

Để xác nhận tính nhất quán, nhóm có thể kiểm tra tính chất: với giá trị đã được chấp nhận, định dạng lại theo **chính formatter và hợp đồng canonical đã chốt** phải cho biểu diễn mong muốn. Không áp dụng tính chất “string gốc luôn giống string đã format” cho mọi parser mà chưa định nghĩa canonical form.

Những ca trên cần đi qua cả validator đơn vị và đường vào thật ở mức thích hợp. Chẳng hạn, chỉ gọi phương thức Java bằng một `String` không kiểm chứng được việc JSON mapper có từ chối kiểu number ở T20 hay không.

Đối với FMT-008, chỉ xem HTTP status chưa đủ. Bằng chứng cần quan sát được đơn hàng và sự kiện nghiệp vụ tương ứng trong môi trường kiểm thử.

## 14. Quản lý thay đổi và giới hạn bảo vệ

Thay đổi một regex có thể thay đổi tập dữ liệu được chấp nhận như một thay đổi API thực sự. Ví dụ, mở mã từ tám lên mười chữ số ảnh hưởng producer, schema, UI, database và các nơi dùng mã làm khóa. Siết từ “không phân biệt hoa/thường” sang “chỉ viết hoa” có thể làm client cũ thất bại.

Một thay đổi định dạng nên chỉ ra:

- Hợp đồng cũ và mới khác nhau ở biểu diễn nào.
- Ai đang phát sinh những biểu diễn bị ảnh hưởng.
- Thứ tự cập nhật producer và consumer.
- Cách phân biệt phiên bản nếu hai dạng cùng tồn tại.
- Dữ liệu cũ được so sánh, hiển thị và tra cứu như thế nào.
- Ca biên nào bảo vệ quyết định mới.

Không chấp nhận đồng thời mọi định dạng lịch sử bằng một chuỗi fallback không được công bố. Nếu một API cần hỗ trợ hai dạng, phải xác định rõ cách phân biệt và ưu tiên; tránh trường hợp cùng chuỗi được diễn giải thành hai ngày hoặc hai số khác nhau.

Cuối cùng, format validation chỉ chứng minh một giá trị thuộc miền biểu diễn đã chốt. Nó không thay thế truy vấn tham số hóa, bảo vệ ngữ cảnh hiển thị, phân quyền đối tượng, kiểm tra nghiệp vụ hoặc bảo đảm tính nhất quán khi ghi dữ liệu.

Một yêu cầu tốt nêu được định dạng nào được nhận, kiểm tra ở biểu diễn nào, dùng toàn bộ chuỗi hay parser nào, có phép biến đổi nào được phép và phải dừng ở đâu nếu thất bại. Những chi tiết đó giúp nhóm chuyển một câu “input phải đúng format” thành kiểm soát có thể triển khai, truy vết và nghiệm thu.
