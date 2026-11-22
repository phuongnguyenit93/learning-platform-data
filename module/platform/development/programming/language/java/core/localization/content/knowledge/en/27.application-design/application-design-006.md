# Giữ mã lỗi, tên trường kỹ thuật và định dạng máy ổn định trong Java localization

## 1. Quy tắc nền tảng

Trong ứng dụng đa ngôn ngữ, **thứ con người đọc được bản địa hóa; thứ máy phân tích phải tuân theo một hợp đồng ổn định**. Khi giao diện chuyển từ `vi-VN` sang `en-US`, nhãn và câu thông báo có thể đổi, nhưng error code, tên trường JSON, kiểu dữ liệu, tên trạng thái và định dạng trao đổi không được tự động đổi theo.

Ví dụ, khi người dùng nhập số tiền không dương:

~~~text
Dữ liệu kỹ thuật (cả hai ngôn ngữ):
  code  = AMOUNT_NOT_POSITIVE
  field = amount

vi-VN: Số tiền phải lớn hơn 0
en-US: Amount must be greater than zero
~~~

Nếu API thay `amount` bằng `soTien` khi chọn tiếng Việt, client và validator phụ thuộc schema `amount` sẽ thất bại. Tương tự, không thể phát hiện lỗi bằng cách so nguyên văn câu tiếng Anh vì câu dịch được phép sửa mà ý nghĩa lỗi không đổi.

Tách ít nhất ba trách nhiệm: **domain** xác định giá trị và điều kiện nghiệp vụ; **machine contract** xác định code/field/types/format; **presentation** biến chúng thành câu chữ, nhãn, cách định dạng phù hợp locale.

## 2. Bảng phân loại dữ liệu

| Thành phần | Ví dụ | Ổn định hay bản địa hóa? |
| --- | --- | --- |
| Mã lỗi API | `AMOUNT_NOT_POSITIVE` | Ổn định |
| Tên property JSON | `amount`, `createdAt` | Ổn định |
| Đường dẫn field bị lỗi | `items[0].quantity` | Ổn định |
| Tên khóa ResourceBundle | `error.amount.notPositive` | Ổn định |
| Trạng thái/enum công khai | `PENDING`, `APPROVED` | Ổn định |
| HTTP status, correlation ID | `422`, `req-1042` | Ổn định |
| JSON boolean | `true`, `false` | Cú pháp máy |
| Số JSON | `1234.50` | Cú pháp máy |
| Thời điểm giao tiếp | `2024-10-28T09:30:00Z` | Format theo contract |
| Currency code | `VND`, `USD` | Ý nghĩa nghiệp vụ |
| Nhãn field | “Số tiền” / “Amount” | Bản địa hóa |
| Thông báo lỗi | “Số tiền phải lớn hơn 0” | Bản địa hóa |
| Ngày/số tiền trên màn hình | `28/10/2024`, `1.234,50` | Bản địa hóa khi phù hợp |

Cần phân biệt **nhãn** và **định danh**. `customerName` là JSON property; “Tên khách hàng” là nhãn UI. Hai giá trị phục vụ mục đích khác nhau, không phải hai bản dịch của cùng một key máy.

## 3. Error code khác message

Hai phản hồi cùng lỗi có thể là:

~~~json
{
  "code": "AMOUNT_NOT_POSITIVE",
  "field": "amount",
  "message": "Số tiền phải lớn hơn 0"
}
~~~

~~~json
{
  "code": "AMOUNT_NOT_POSITIVE",
  "field": "amount",
  "message": "Amount must be greater than zero"
}
~~~

Tên property `code`, `field`, `message` giống nhau. Giá trị `code` và `field` giống nhau. **Chỉ** giá trị `message` đổi ngôn ngữ.

Một khai báo kiểu trong Java 17:

~~~java
public record ApiError(String code, String field, String message) {}
~~~

Đây là một top-level public record hợp lệ nếu đặt trong file riêng `ApiError.java`. Trong chương trình độc lập ở mục 9, record được khai báo lồng trong class.

### 3.1. Vì sao không so sánh theo câu lỗi?

Một client có thể gặp lỗi nếu thực hiện:

~~~java
if ("Amount must be greater than zero".equals(error.message())) {
    System.out.println("Invalid amount");
}
~~~

Đây là đoạn minh họa trong một phương thức, với `error` là đối tượng có accessor `message()`. Chỉ cần sửa bản dịch hoặc thêm ngôn ngữ là nhánh xử lý này không còn đúng.

Thay bằng:

~~~java
if ("AMOUNT_NOT_POSITIVE".equals(error.code())) {
    System.out.println("Invalid amount");
}
~~~

`AMOUNT_NOT_POSITIVE` là **định danh có ý nghĩa nghiệp vụ ổn định**. `message` là dữ liệu để đọc, có thể chứa dấu câu, tham số, lời giải thích hoặc ngôn ngữ khác nhau.

### 3.2. Thiết kế danh mục mã lỗi

Một danh mục mã lỗi nên có: code, mô tả nghiệp vụ, phạm vi áp dụng, HTTP status hoặc status domain, technical field/arguments và translation key. Nên dùng mã ASCII và quy ước nhất quán, ví dụ `UPPER_SNAKE_CASE`. Không đưa thông tin cá nhân hoặc stack trace vào code.

Khi một câu dịch được viết hay hơn, **không cần đổi code**. Khi nguyên nhân nghiệp vụ thay đổi đáng kể, không tái sử dụng code cũ cho một điều kiện không tương thích. Có cơ chế xử lý code chưa biết ở client và versioning/deprecation cho mã public.

HTTP status và application error code bổ sung nhau: status mô tả tình trạng request tổng quát, error code diễn đạt nguyên nhân cụ thể. Chọn 400/422 theo API contract, không theo locale.

## 4. Tên field, khóa ResourceBundle và field path

Một đơn hàng có thể truyền dưới dạng:

~~~json
{
  "amount": 1250.50,
  "currencyCode": "VND",
  "createdAt": "2024-10-28T09:30:00Z",
  "status": "PENDING"
}
~~~

Màn hình Việt hiển thị “Số tiền”, “Loại tiền”, “Thời gian tạo”, “Trạng thái”. Màn hình Anh hiển thị “Amount”, “Currency”, “Created at”, “Status”. Nhưng property names vẫn là `amount`, `currencyCode`, `createdAt`, `status`.

Nếu dùng ResourceBundle, hãy giữ **cùng tên key** ở các file:

~~~properties
error.amount.notPositive=Amount must be greater than zero
label.amount=Amount
label.createdAt=Created at
~~~

Bản tiếng Việt:

~~~properties
error.amount.notPositive=Số tiền phải lớn hơn 0
label.amount=Số tiền
label.createdAt=Thời gian tạo
~~~

Đây là nội dung minh họa của hai file properties khác locale. `error.amount.notPositive` là key kỹ thuật; **chỉ value bên phải dấu bằng được dịch**. Một error code có thể ánh xạ đến key dịch riêng; chúng không nhất thiết trùng tên.

### 4.1. Field path trong validation

Ví dụ lỗi của mục hàng đầu tiên:

~~~json
{
  "code": "QUANTITY_NOT_POSITIVE",
  "field": "items[0].quantity",
  "message": "Số lượng phải lớn hơn 0"
}
~~~

`items[0].quantity` là technical field path; không nên biến thành `matHang[0].soLuong` theo locale. UI dùng path này để highlight input, sau đó tra nhãn “Số lượng” hoặc “Quantity” riêng. Nếu API dùng JSON Pointer như `/items/0/quantity`, hãy công bố rõ cú pháp, escaping và cách map tới trường, không trộn lẫn hai định dạng path.

Tương tự, tên cột database `customer_id`, tên message queue event `ORDER_CREATED`, GraphQL property, public enum value và metric key không nên được dịch trong giao thức.

## 5. Số, ngày và kiểu dữ liệu máy

### 5.1. Decimal máy không phải số hiển thị

~~~java
BigDecimal amount = new BigDecimal("1234.50");
String decimal = amount.toPlainString();
~~~

Đây là đoạn Java minh họa trong một phương thức, cần `import java.math.BigDecimal;`. `decimal` là `"1234.50"`, không thay theo Locale. Khi contract yêu cầu **decimal string**, nó là một biểu diễn phù hợp.

Nếu contract yêu cầu **JSON number**, hãy dùng JSON serializer ghi number token:

~~~json
{"amount":1234.50}
~~~

Không viết số máy thành chuỗi đã format cho giao diện:

~~~json
{"amount":"1.234,50"}
~~~

`"1.234,50"` là JSON **string**, không phải JSON number. Việc đổi loại thành string cũng là thay đổi schema, không phải chỉ khác dấu decimal. Khi giao thức cố ý dùng string decimal để giữ precision, hãy ghi `"1234.50"` và nêu rõ kiểu trong schema.

Với formatting kiểu `String.format`, truyền `Locale.ROOT` nếu cần kết quả machine theo một quy tắc không phụ thuộc locale mặc định:

~~~java
String machineText = String.format(Locale.ROOT, "%.2f", 1234.5);
~~~

Đây là snippet, cần import `java.util.Locale`; kết quả `"1234.50"`. Tuy nhiên không nên dùng `double` để tính số tiền cần chính xác. `BigDecimal` cộng serializer hoặc một decimal-string contract sẽ thích hợp hơn.

**Cẩn trọng:** các client JavaScript có thể làm mất precision với một số JSON number. Đối với số tiền lớn/chính xác, lựa chọn decimal string, integer minor units hoặc hỗ trợ decimal chính xác phải là quyết định toàn hệ thống.

### 5.2. Thời điểm và ngày lịch khác nhau

~~~java
Instant createdAt = Instant.parse("2024-10-28T09:30:00Z");
String timestamp = DateTimeFormatter.ISO_INSTANT.format(createdAt);
~~~

Đây là đoạn minh họa, cần import `Instant` và `DateTimeFormatter`. Kết quả `2024-10-28T09:30:00Z` là một instant theo UTC.

UI có thể hiển thị `28/10/2024 16:30` ở múi giờ Việt Nam hoặc `10/28/2024 9:30 AM` ở UTC. Nhưng một thời điểm absolute **không tự thay đổi** khi locale giao diện đổi.

Nếu dữ liệu thật là ngày sinh hay ngày hết hạn dạng calendar date, dùng `LocalDate` và format máy như `2024-10-28`; không tự biến ngày lịch thành instant lúc 00:00 UTC mà không có quy tắc zone. Nếu API dùng datetime với offset thay cho UTC, contract phải xác định dạng ISO 8601/RFC 3339, precision và cách kiểm tra.

### 5.3. Boolean, currency, trạng thái và CSV

JSON boolean luôn `true` hoặc `false`, JSON null dùng `null`. Giá trị enum như `PENDING` là định danh máy; nhãn “Đang chờ” chỉ nên render ở UI.

Lưu currency code `VND`, `USD` cùng amount. Đổi locale không phải đổi đơn vị tiền hoặc quy đổi tỷ giá. `NumberFormat.getCurrencyInstance(locale)` chỉ định dạng cách hiển thị, không biến 100 USD thành 100 VND.

CSV có nhiều dialect. Khi một CSV machine dùng dấu phẩy phân cách cột, cần biết delimiter, quoting, decimal, encoding và newline. Đừng ghi `1.234,50` rồi hy vọng hệ thống khác tự hiểu đó là một số mà không có schema; dấu phẩy có thể bị hiểu là separator.

## 6. Tách request locale khỏi quyết định nghiệp vụ

Một luồng API nên như sau:

~~~text
HTTP request + JSON payload
          |
          v
Parse theo schema cố định
          |
          v
Domain validation -> errorCode, field, typed arguments
          |
          v
Chọn Locale trình bày theo ngôn ngữ được hỗ trợ
          |
          v
ResourceBundle / message lookup
          |
          v
Serialize response với JSON keys và data types cố định
~~~

`Accept-Language` là một sở thích ngôn ngữ, không phải thông tin đã xác minh về vị trí, quốc tịch, thuế, currency hoặc quyền truy cập. Nếu người dùng chọn ngôn ngữ không hỗ trợ, ứng dụng fallback có chủ đích (ví dụ tiếng Anh) nhưng **không được thay error code và schema**.

Không gọi `Locale.setDefault` theo từng request web: default locale có phạm vi JVM, có thể gây rò ngôn ngữ giữa hai request đồng thời. Truyền `Locale` tường minh vào tầng presentation và formatter.

### 6.1. Thông điệp có tham số

Có thể trả lỗi kèm tham số máy:

~~~json
{
  "code": "AMOUNT_BELOW_MINIMUM",
  "field": "amount",
  "arguments": {
    "minimum": 100.00,
    "currencyCode": "VND"
  },
  "message": "Số tiền tối thiểu là 100 VND"
}
~~~

`arguments.minimum` giữ kiểu số; `currencyCode` giữ mã tiền. Chỉ message đổi khi dùng locale khác. Không định dạng `minimum` thành `"100,00"` rồi giả làm JSON number. Khi dùng `MessageFormat`, placeholder/argument indexes trong các bản dịch cần được quản lý theo một contract ổn định, dù thứ tự từ trong câu khác nhau.

## 7. Domain model và wire DTO không phải UI model

Một lớp domain có thể lưu:

~~~java
record Money(BigDecimal amount, String currencyCode) {}
record ApiError(String code, String field, String message) {}
~~~

Đây là các khai báo record minh họa nằm trong một class hoặc compilation unit không có public top-level declarations, yêu cầu import `BigDecimal`. Trong ứng dụng thật cần validate null, currency code và giới hạn nghiệp vụ.

**Domain** giữ amount và currency rõ ràng. **Validation** trả code và field path. **Presentation** tra bản dịch. **Serialization** ghi JSON theo schema. Khi một phần thay đổi, các phần khác có thể giữ nguyên.

Không lưu câu lỗi đã dịch như nguồn sự thật cho một lỗi, không ghi `"1.234,50"` làm số tiền trong domain, không dùng nhãn field làm tên column/JSON key. Nếu phải lưu cả thông điệp phục vụ audit, lưu kèm mã lỗi và context, đồng thời không dùng message làm primary identity của loại lỗi.

### 7.1. Dùng serializer thay vì nối JSON thủ công

Các JSON snippets ở đây minh họa contract. Một ứng dụng thực nên dùng JSON serializer có xử lý quoting, escaping, types và mapping tên field. Không tự nối message hoặc chuỗi do người dùng cung cấp thành JSON mà không escape. Việc chạy demo ở mục 9 **không sinh JSON**, mà in ra thuộc tính để kiểm tra nguyên tắc locale.

## 8. Tương thích và vòng đời phát hành

### 8.1. Thay đổi bản dịch thường không phải breaking change

Có thể sửa lời giải thích trong message, thêm locale hoặc thay nhãn màn hình mà không cần đổi code/field/schema. Một client hợp lệ không nên phụ thuộc câu dịch để thực hiện logic.

### 8.2. Những thay đổi cần schema migration

- Đổi `createdAt` thành `created_at` khi field đã public.
- Đổi `AMOUNT_NOT_POSITIVE` thành code khác mà không có phương án tương thích.
- Đổi kiểu `amount` từ number thành string.
- Đổi instant ISO sang chuỗi ngày theo locale không có offset.
- Dùng nhãn đã dịch như `Đang chờ` thay cho enum value `PENDING`.
- Đổi cú pháp technical field path mà client phụ thuộc.

Những thay đổi này cần tài liệu, API versioning/deprecation, rollout và regression tests. Thêm error code mới cũng cần client fallback cho unknown code; không giả định mọi client sẽ nâng cấp đồng thời.

### 8.3. Chủ sở hữu của error catalog

Nên duy trì danh mục code có mô tả, rule phát sinh, HTTP status, field/arguments, translation key, hướng xử lý và chính sách deprecation. Không tái sử dụng mã cho nghĩa mới chỉ vì câu thông báo giống nhau.

## 9. Chương trình Java 17 hoàn chỉnh

Chương trình độc lập dùng `Map` như một nguồn dịch nhỏ. Trong sản phẩm, `ResourceBundle` hoặc message source framework thường phù hợp hơn. Ví dụ in stdout ASCII và kiểm chứng thông điệp Việt bằng Unicode escapes, nên không phụ thuộc font console.

**Tệp `StableContractDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Map;

public class StableContractDemo {
    private static final String ERROR_CODE = "AMOUNT_NOT_POSITIVE";
    private static final String FIELD = "amount";

    record ApiError(String code, String field, String message) {}
    record Transfer(BigDecimal amount, Instant createdAt) {}

    static ApiError validate(Transfer transfer, Locale locale) {
        if (transfer.amount().signum() > 0) {
            throw new IllegalArgumentException(
                    "This demo expects a nonpositive amount");
        }
        Map<String, String> templates = Map.of(
                "vi", "S\u1ED1 ti\u1EC1n ph\u1EA3i l\u1EDBn h\u01A1n 0",
                "en", "Amount must be greater than zero");
        String message = templates.getOrDefault(
                locale.getLanguage(), templates.get("en"));
        return new ApiError(ERROR_CODE, FIELD, message);
    }

    public static void main(String[] args) {
        Transfer transfer = new Transfer(new BigDecimal("0.00"),
                Instant.parse("2024-10-28T09:30:00Z"));
        ApiError vi = validate(
                transfer, Locale.forLanguageTag("vi-VN"));
        ApiError en = validate(transfer, Locale.US);

        System.out.println("vi: code=" + vi.code()
                + ", field=" + vi.field());
        System.out.println("en: code=" + en.code()
                + ", field=" + en.field());
        System.out.println("same technical identity=" +
                (vi.code().equals(en.code())
                && vi.field().equals(en.field())));
        System.out.println("localized messages differ=" +
                !vi.message().equals(en.message()));
        System.out.println("vi message verified=" +
                vi.message().equals(
                        "S\u1ED1 ti\u1EC1n ph\u1EA3i l\u1EDBn h\u01A1n 0"));
        System.out.println("machine amount=" +
                transfer.amount().toPlainString());
        System.out.println("machine time=" +
                DateTimeFormatter.ISO_INSTANT.format(
                        transfer.createdAt()));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 StableContractDemo.java
java StableContractDemo
~~~

**Stdout đã kiểm tra:**

~~~text
vi: code=AMOUNT_NOT_POSITIVE, field=amount
en: code=AMOUNT_NOT_POSITIVE, field=amount
same technical identity=true
localized messages differ=true
vi message verified=true
machine amount=0.00
machine time=2024-10-28T09:30:00Z
~~~

**Giải thích:** `code` và `field` giữ nguyên ở cả hai locale, thông điệp thì khác. Dòng `vi message verified=true` xác nhận nội dung Unicode Việt mà không cần render tiếng Việt trên console. `BigDecimal.toPlainString` in `0.00` không bị format theo locale; `ISO_INSTANT` in mốc `2024-10-28T09:30:00Z`. Đây là ví dụ minh họa validation cho **amount không dương**, không phải thư viện JSON hoặc giải pháp đầy đủ để xử lý tiền thật.

## 10. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dịch error code theo locale | Client không nhận dạng được lỗi | Giữ mã ổn định |
| Dùng message trong if/switch | Sửa bản dịch làm vỡ logic | Dùng code |
| Dịch JSON keys | Serializer/schema client không tương thích | Cố định property names |
| Trả nhãn UI như technical field | Client không map được field | Trả field path chuẩn |
| Dùng `NumberFormat` cho JSON number | Dấu nhóm/decimal theo locale | Serializer số máy |
| Gửi ngày UI như datetime machine | Mơ hồ ngày/tháng, zone và offset | ISO theo contract |
| Đổi currency vì đổi language | Thay nghĩa của tiền | Currency là domain |
| Dùng `Locale.setDefault` per request | Rò ngôn ngữ giữa request | Truyền locale tường minh |
| So sánh lỗi bằng text message | Không hỗ trợ đa ngôn ngữ | Error code + typed args |
| Dùng default locale cho logs/schema | Kết quả khác nhau giữa server | Locale-neutral contract |
| Không có fallback cho code mới | Client cũ crash | Unknown-code handler |
| Nối chuỗi JSON tùy tiện | Escaping/injection/kiểu sai | Dùng serializer |
| Thiếu test Unicode/locale | Lỗi dấu, font, charset | Test vi/en/RTL/emoji |
| Đổi schema mà chỉ coi là dịch | Breaking change ngầm | Versioning và migration |

## 11. Kiểm thử cần viết

Một bộ kiểm thử tốt chạy cùng dữ liệu trên nhiều locale (`vi-VN`, `en-US`, `de-DE`, `tr-TR` và locale không hỗ trợ) rồi xác minh:

1. `code`, `field`, HTTP status không đổi.
2. JSON property names và types không đổi.
3. Amount và currency có giá trị/domain semantics nhất quán.
4. ISO timestamp có cùng instant và precision theo contract.
5. Enum values, IDs và log fields không đổi.
6. Các bản dịch khác nhau hoặc fallback được chọn có chủ đích.
7. `BigDecimal` được serialize không phụ thuộc `Locale.getDefault()`.
8. Schema test bắt được `createdAt` vô tình đổi sang `thoiGianTao`.
9. Unknown error code được xử lý an toàn, không crash.
10. Nested field path `items[0].quantity` không đổi theo UI language.
11. Message Unicode được encode/decode UTF-8 đúng; JSON escaping an toàn.
12. Concurrent requests với các locale khác nhau không làm nhiễm ngôn ngữ của nhau.

Ngoài kiểm tra Java objects, cần kiểm tra **serialized HTTP response thật**, vì một serializer/framework có thể bị cấu hình khác với code domain.

## 12. Bài tập thực hành

1. Cho demo chạy với `fr-FR`, nhận message fallback sang tiếng Anh nhưng technical identity vẫn đúng.
2. Thêm `CURRENCY_UNSUPPORTED` với field `currencyCode`; tạo nhãn và message theo vi/en mà không dịch field.
3. Tạo `Order(BigDecimal amount, String currencyCode, Instant createdAt)`, định nghĩa schema JSON cố định và hai UI presentations.
4. So `BigDecimal("1234.50").toPlainString()` với `NumberFormat.getNumberInstance(Locale.GERMANY)`; giải thích khác biệt.
5. Viết test thay `Accept-Language` nhưng `code` và `field` không đổi.
6. Viết response nhiều lỗi gồm array `errors`; mỗi phần tử có code/field/message cố định kiểu.
7. Tạo error message có `minimum` kiểu number và currency code; format theo locale chỉ tại lớp hiển thị.
8. Thử default locale `tr-TR` ở môi trường test riêng; kiểm tra machine decimal/timestamp.
9. Viết client fallback cho error code không biết mà vẫn hiển thị thông điệp an toàn.
10. So sánh việc đổi câu dịch với việc đổi JSON key: thay đổi nào cần API version?

## 13. Tổng kết

**Bản địa hóa không được làm thay đổi ý nghĩa hoặc hình dạng dữ liệu máy.** Mã lỗi, tên field, field path, JSON schema, enum values, timestamp và decimal representation phải theo contract ổn định. `Locale` được dùng để chọn `ResourceBundle`, ngôn ngữ message, nhãn và format giao diện. Với số/ngày trên wire, dùng `BigDecimal`, `Instant`, formatter/serializer phù hợp; `Locale.ROOT` hữu ích cho một số trường hợp format kỹ thuật, nhưng không thay thế schema hoặc precision.

Tách domain, API contract và presentation giúp ứng dụng thêm ngôn ngữ, sửa thông điệp và cải thiện giao diện mà không làm hỏng client, báo cáo, DB hay quy tắc nghiệp vụ.

**Tài liệu tham khảo:**

- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `Instant`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- JSON syntax: https://www.rfc-editor.org/rfc/rfc8259
