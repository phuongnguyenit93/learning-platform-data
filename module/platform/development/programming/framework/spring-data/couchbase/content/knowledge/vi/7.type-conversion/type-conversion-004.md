# Enum, kiểu giá trị nghiệp vụ và dữ liệu nhiều biến thể

## 1. Bài toán: Java có kiểu mạnh, JSON chỉ có cấu trúc dữ liệu

Trong module **SPRING_DATA_COUCHBASE**, tầng truy cập dữ liệu sử dụng Spring Data để ánh xạ entity Java sang Couchbase JSON document, đọc bằng repository hoặc `CouchbaseTemplate`, và truy vấn qua SQL++. Các kiểu đơn giản như số, chuỗi và boolean dễ hình dung. Nhưng dữ liệu nghiệp vụ thường mang ngữ nghĩa chặt hơn:

- Trạng thái đơn hàng là `OrderStatus`, chỉ cho phép một tập giá trị.
- Mã SKU là `SkuCode`, phải đúng định dạng và không thể nhầm với `String` bất kỳ.
- Số tiền là `Money`, cần đồng thời giá trị và đơn vị tiền tệ.
- Phương thức thanh toán có thể là thẻ, ví điện tử hoặc chuyển khoản, mỗi biến thể có thuộc tính riêng.

JSON không có khái niệm **Java enum**, **value object**, **interface**, **sealed hierarchy** hay **subclass**. Vì vậy, `MappingCouchbaseConverter` cần một biểu diễn lưu trữ nhất quán để ghi được dữ liệu hôm nay và đọc lại khi code đã thay đổi.

Bài học trả lời bốn câu hỏi:

1. Enum được ghi thành gì, và đổi tên một enum constant có rủi ro nào?
2. Khi nào nên để value object là JSON object, khi nào nên dùng custom converter sang string/number?
3. Cơ chế thông tin kiểu `_class` và `@TypeAlias` giúp đọc dữ liệu đa hình ra sao?
4. Khi schema có nhiều biến thể và nhiều client cùng truy cập Couchbase, nên dùng discriminator nghiệp vụ hay type metadata của framework?

## 2. Enum: mặc định lưu dưới dạng chuỗi tên hằng

Ví dụ trạng thái xử lý đơn hàng:

```java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
```

Khai báo entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public record OrderDocument(
    @Id String id,
    @Field String customerCode,
    @Field OrderStatus status
) {}
```

Giả sử ứng dụng lưu:

```java
OrderDocument order = new OrderDocument(
    "order::1001",
    "CUS-42",
    OrderStatus.PAID
);
```

JSON body minh họa trong cách mapping thông dụng:

```json
{
  "_class": "com.example.orders.OrderDocument",
  "customerCode": "CUS-42",
  "status": "PAID"
}
```

Các điểm cần nhận diện:

- `PAID` là một **string** JSON. Nó không phải kiểu enum riêng ở Couchbase.
- `OrderStatus` được khôi phục từ giá trị string theo quy tắc chuyển đổi enum của Spring Data.
- `"PAID"` khác `"paid"` và `"Paid"`. Không mặc định rằng converter bỏ qua chữ hoa/chữ thường.
- ID `order::1001` là document key; không bắt buộc phải được lặp thành JSON field `id`.
- `_class` là metadata kiểu phục vụ mapping trong body JSON; nó không phải giá trị enum của property `status`.

**Điểm thiết kế quan trọng:** Chuỗi tên enum trở thành một phần của **hợp đồng dữ liệu lâu dài**. Nếu đổi `PAID` thành `PAYMENT_COMPLETED` trong Java mà không có đường đọc tương thích, document cũ vẫn lưu `"PAID"` và có thể không còn dựng được entity theo code mới.

### 2.1. Vì sao không nên lưu `ordinal()` của enum?

Java enum có số thứ tự theo vị trí khai báo, ví dụ `CREATED.ordinal() == 0` và `PAID.ordinal() == 1`. Nhưng nếu thêm một constant trước `PAID`, ordinal sẽ đổi.

```java
// Trước khi thay đổi
enum StatusV1 { CREATED, PAID, CANCELLED } // PAID = 1

// Sau khi thêm trạng thái
enum StatusV2 { CREATED, REVIEWING, PAID, CANCELLED } // PAID = 2
```

Nếu database lưu `1` để diễn đạt `PAID`, sau lần triển khai mới `1` lại có thể được hiểu thành `REVIEWING`. Đây là sai lệch dữ liệu nghiệp vụ nghiêm trọng nhưng không nhất thiết phát sinh lỗi kỹ thuật.

**Ưu tiên:** dùng tên/giá trị string có hợp đồng ổn định; không tự cài converter dựa trên `ordinal()` cho dữ liệu bền vững.

### 2.2. Enum không thay thế quy tắc chuyển trạng thái

Việc JSON lưu `"PAID"` không ngăn được một client khác ghi `"UNKNOWN"`. Converter chỉ có thể chuyển được các giá trị mà nó hiểu; validation và kiểm tra chuyển trạng thái vẫn phải nằm trong nghiệp vụ.

Ví dụ, `CANCELLED → PAID` có thể là chuyển trạng thái không hợp lệ, ngay cả khi cả hai string đều thuộc enum. Enum giúp giới hạn **tập trạng thái**, nhưng không thay thế state machine, CAS hoặc transaction.

## 3. Xây dựng hợp đồng enum ổn định khi ứng dụng phát triển

Không phải tên Java nào cũng là tên lý tưởng cho JSON. Đặc biệt khi có client bên ngoài, dữ liệu cũ hoặc nhiều ngôn ngữ lập trình, có thể chọn **mã lưu trữ ổn định** tách khỏi tên constant Java.

```java
public enum OrderStatus {
    CREATED("created"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown status: " + code);
    }
}
```

**Lưu ý:** chỉ định nghĩa `code()` **không làm Spring Data Couchbase tự dùng mã đó**. Nếu vẫn đặt một property `OrderStatus status` mà không cấu hình thêm, quy tắc enum mặc định thường tiếp tục lưu tên hằng như `"PAID"`.

Có hai hướng thực hiện hợp đồng riêng:

1. Giữ property persistence dạng `String statusCode` và chuyển đổi ở ranh giới domain. Đường lưu/đọc dễ dự đoán, đặc biệt với nhiều client.
2. Đăng ký custom `@WritingConverter` / `@ReadingConverter` giữa enum và string, rồi xác minh round-trip ở đúng phiên bản Spring Data Couchbase đang dùng.

Một ví dụ converter hai chiều:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}

@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
```

Sau khi **đăng ký thực sự** các converter qua cơ chế custom conversions của ứng dụng, JSON mục tiêu sẽ chứa `"status": "paid"`. Nên kiểm tra việc converter tùy biến được ưu tiên so với converter enum mặc định; hành vi cụ thể còn phụ thuộc cấu hình và phiên bản framework.

### 3.1. Giá trị enum chưa biết: thất bại, gán OTHER hay giữ raw?

Giả sử service mới ghi `"refunded"` trong khi service cũ chỉ biết `created`, `paid` và `cancelled`. Có ba chính sách:

| Chính sách | Lợi ích | Rủi ro |
| --- | --- | --- |
| **Fail fast** khi gặp mã lạ | Không âm thầm hiểu sai trạng thái; dễ phát hiện lỗi contract | Service cũ có thể không xử lý được document mới. |
| Ánh xạ về `UNKNOWN` hoặc `OTHER` | Service có thể tiếp tục đọc | Có nguy cơ che mất ngữ nghĩa, không thể quyết định chuyển trạng thái chính xác. |
| Giữ cả **raw code** và trạng thái đã diễn giải | Bảo toàn dữ liệu chưa biết; phù hợp luồng tương thích nhiều phiên bản | Model và logic nghiệp vụ phức tạp hơn. |

Đối với trạng thái dùng để tính tiền, giao hàng hoặc điều khiển bảo mật, không nên tự động chuyển mọi giá trị lạ thành một trạng thái hợp lệ như `CREATED`. Cần chọn chính sách dựa trên mức độ an toàn nghiệp vụ.

## 4. Value object: dùng kiểu Java để khóa chặt bất biến

Một `String` bất kỳ không nên được dùng thay cho mọi mã nghiệp vụ. Ví dụ:

```java
public record SkuCode(String value) {
    public SkuCode {
        if (value == null || !value.matches("[A-Z0-9-]{3,32}")) {
            throw new IllegalArgumentException("Invalid SKU");
        }
    }
}
```

`SkuCode` là **value object**: giá trị có danh tính theo dữ liệu của nó, được kiểm tra hợp lệ ngay khi tạo, và khó nhầm với email, tên người hay mã quốc gia dù tất cả cùng dùng string để lưu.

Value object có thể bao gồm:

- Mã sản phẩm `SkuCode`, mã đơn hàng `OrderCode`.
- Tiền `Money` gồm amount và currency.
- Phạm vi ngày giờ `DateRange`, tọa độ `GeoPoint`, tỷ lệ `Percentage`.
- Các loại mã có format/độ dài/quy tắc riêng.

Trong Spring Data Couchbase, có hai lựa chọn lưu trữ phổ biến: **object có cấu trúc** hoặc **một giá trị đơn giản**.

## 5. Lựa chọn A: giữ value object thành JSON object

Ví dụ tiền gồm số đơn vị nhỏ nhất và mã tiền tệ:

```java
public record Money(long amountMinor, String currency) {
    public Money {
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}

@Document
public record InvoiceDocument(
    @Id String id,
    @Field Money total
) {}
```

Nếu `Money` được ánh xạ như một object lồng nhau, biểu diễn JSON dự kiến:

```json
{
  "_class": "com.example.billing.InvoiceDocument",
  "total": {
    "amountMinor": 155000,
    "currency": "VND"
  }
}
```

Ở ví dụ này, `amountMinor` là tên theo **hợp đồng ứng dụng**: đơn vị nhỏ nhất của currency tương ứng. Cần xác định quy tắc scale của từng currency và quy ước làm tròn ở tầng nghiệp vụ; tuyệt đối không coi mọi đồng tiền đều có hai chữ số thập phân.

### Ưu điểm

- Dữ liệu giữ cấu trúc có ý nghĩa: amount và currency luôn đi cùng nhau.
- Truy vấn SQL++ có thể lấy `total.currency`, `total.amountMinor` để filter hoặc tổng hợp theo điều kiện rõ ràng.
- Dễ thêm thuộc tính như `pricingSource` hoặc `precisionVersion` khi cần, nếu có kế hoạch versioning.

### Cần cân nhắc

- Class phải có constructor/metadata phù hợp để Spring Data tạo lại object.
- Đổi tên Java property có thể làm đổi tên field JSON nếu không cố định bằng `@Field`.
- Kiểu lồng nhau có thể mang type hint tùy cấu hình và ngữ cảnh; không nên lấy ví dụ JSON minh họa làm cam kết byte-for-byte.
- Nếu có **nhiều currency**, không tổng hợp các `amountMinor` với nhau khi chưa quy đổi cùng đơn vị.

Tổ chức JSON theo cấu trúc thuận tiện khi cần truy vấn field con hoặc đối tượng có nhiều thành phần nghiệp vụ.

## 6. Lựa chọn B: chuyển value object thành giá trị JSON đơn giản

Nếu `SkuCode` chỉ bao một string, một document như:

```json
{ "sku": "BOOK-2026-01" }
```

thường dễ tích hợp hơn biểu diễn lồng nhau:

```json
{ "sku": { "value": "BOOK-2026-01" } }
```

Có thể đăng ký converter:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class SkuCodeToString implements Converter<SkuCode, String> {
    @Override
    public String convert(SkuCode source) {
        return source.value();
    }
}

@ReadingConverter
public class StringToSkuCode implements Converter<String, SkuCode> {
    @Override
    public SkuCode convert(String source) {
        return new SkuCode(source);
    }
}
```

Trong cấu hình kế thừa `AbstractCouchbaseConfiguration`, những phiên bản hỗ trợ phương thức `additionalConverters` cho phép bổ sung:

```java
@Override
protected void additionalConverters(List<Object> converters) {
    converters.add(new SkuCodeToString());
    converters.add(new StringToSkuCode());
}
```

Import `java.util.List` trong lớp cấu hình. Nếu phiên bản dùng cách cấu hình khác, hãy đăng ký thông qua `CouchbaseCustomConversions` tương ứng; **annotation trên class converter không tự đăng ký bean**.

Ví dụ entity:

```java
@Document
public record ProductDocument(
    @Id String id,
    @Field SkuCode sku
) {}
```

Dữ liệu đầu vào:

```java
ProductDocument product = new ProductDocument(
    "product::42",
    new SkuCode("BOOK-2026-01")
);
```

Hợp đồng JSON mục tiêu:

```json
{
  "_class": "com.example.catalog.ProductDocument",
  "sku": "BOOK-2026-01"
}
```

**Một converter toàn kiểu có thể ảnh hưởng đến mọi property `SkuCode` trong entity**, bao gồm các trường lồng nhau. Cần kiểm tra ảnh hưởng trong từng tài liệu và xem có mapping nào từ trước đang mong đợi JSON object hay không. Tránh ghi đè việc chuyển toàn entity nếu chỉ cần thay đổi một property; có thể cân nhắc property converter ở những phiên bản hỗ trợ.

### 6.1. Test cả hai chiều và cả dữ liệu không hợp lệ

```java
SkuCode source = new SkuCode("BOOK-2026-01");

String stored = new SkuCodeToString().convert(source);
SkuCode restored = new StringToSkuCode().convert(stored);

assert source.equals(restored);
```

Phép thử trên xác minh logic converter thuần, chưa chứng minh converter được Spring Data **đăng ký và chọn**. Sau đó cần test `MappingCouchbaseConverter.write/read` hoặc repository round-trip ở cấu hình thật.

Hãy kiểm tra thêm: string rỗng, `null`, SKU dài, ký tự Unicode, SKU đổi format, và JSON từ các client khác. Đừng mặc định dữ liệu trong Couchbase đều đã qua constructor validation của Java.

## 7. Khi nào dùng string, object hay number cho value object?

| Dạng miền | Dạng JSON đề xuất | Điều cần bảo đảm |
| --- | --- | --- |
| Mã SKU, mã quốc gia, mã khách hàng | String với hợp đồng format | Giữ số 0 đầu và ký tự đặc biệt, không dùng số học. |
| Money | Object `{amountMinor, currency}` | Định nghĩa scale/rounding, bảo đảm amount/currency luôn cùng đơn vị. |
| Percentage | Number với precision quy định, hoặc fixed-point integer | Xác định 0.15 là 15% hay 0.15%; tránh sai số không kiểm soát. |
| Email | String sau validation | Có chính sách chuẩn hóa riêng; không được mặc định mọi string là email hợp lệ. |
| DateRange | Object `{start, end}` | Đơn vị, timezone, ranh giới bao hàm và bất biến `start < end`. |
| Tọa độ | Object có hai field số và quy ước trục | Quy định tọa độ, độ chính xác, thứ tự kinh/vĩ độ. |

Một lựa chọn giản đơn có thể là tốt nhất khi giá trị có **một thành phần** và contract rõ. Ngược lại, object thường dễ bảo trì hơn khi có nhiều thành phần không được tách rời.

## 8. Dữ liệu nhiều biến thể: cùng field nhưng cấu trúc khác nhau

Một đơn hàng có thông tin thanh toán thuộc nhiều dạng:

- Thẻ: cần `last4` và `network`.
- Ví điện tử: cần `provider` và mã giao dịch.
- Chuyển khoản: cần `bankCode` và mã tham chiếu.

Trong Java, có thể mô hình hóa bằng interface hoặc sealed interface:

```java
public sealed interface PaymentDetails
    permits CardPayment, WalletPayment, BankTransferPayment {}

public record CardPayment(
    String last4, String network
) implements PaymentDetails {}

public record WalletPayment(
    String provider, String transactionRef
) implements PaymentDetails {}

public record BankTransferPayment(
    String bankCode, String reference
) implements PaymentDetails {}
```

Nhưng một JSON object như:

```json
{
  "payment": {
    "provider": "PAY_WALLET",
    "transactionRef": "TX-42"
  }
}
```

không chứa kiểu Java cụ thể, nên nếu entity chỉ khai báo `PaymentDetails payment`, converter cần **đủ thông tin để chọn subtype**. Có hai chiến lược chính.

## 9. Chiến lược 1: dùng type metadata `_class` / `@TypeAlias`

Trong đường mapping thông dụng, Spring Data ghi thông tin kiểu ở key `_class` để hỗ trợ dựng lại class cụ thể. Ví dụ minh họa khi dữ liệu lưu một subtype `WalletPayment`:

```json
{
  "_class": "com.example.orders.OrderDocument",
  "payment": {
    "_class": "com.example.orders.WalletPayment",
    "provider": "PAY_WALLET",
    "transactionRef": "TX-42"
  }
}
```

Hình dạng thực tế phụ thuộc metadata, phiên bản Spring Data Couchbase, cơ chế type mapper và chiến lược ghi subtype. Ví dụ chỉ diễn giải **vai trò của discriminator**, không phải cam kết mọi object lồng nhau chắc chắn có key `_class`.

Khi entity trong hierarchy có `@TypeAlias`, giá trị type hint có thể là alias thay vì tên class dài:

```java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("wallet-payment")
public record WalletPayment(
    String provider,
    String transactionRef
) implements PaymentDetails {}
```

Nếu mapping context biết subtype và type mapper được cấu hình để ghi alias, JSON có thể có:

```json
{
  "payment": {
    "_class": "wallet-payment",
    "provider": "PAY_WALLET",
    "transactionRef": "TX-42"
  }
}
```

**Điều kiện quan trọng:**

1. `@TypeAlias` chỉ khai báo alias; để đọc ngược, kiểu đích phải được **nhận biết trong mapping context** (ví dụ qua initial entity set, mapping metadata hoặc các thao tác đã thiết lập nó). Không được giả định service mới tự giải mọi alias trong document cũ.
2. Thay tên package/class khi đang dùng class name làm type hint có thể phá khả năng đọc document đã lưu.
3. Thay `@TypeAlias("wallet-payment")` thành alias mới cần xử lý dữ liệu và các service đang dùng alias cũ.
4. Nếu truy vấn SQL++ chỉ trả projection thiếu discriminator, converter có thể không còn đủ thông tin để dựng subtype.
5. `_class` là **metadata do Spring Data sử dụng**. Jackson `@JsonTypeInfo` và subtype annotations không được tự động coi là thay thế cho Couchbase mapping converter.

Khi dữ liệu chủ yếu được thao tác bởi một hệ Java/Spring Data có chính sách migration rõ, type metadata của framework giúp giảm mã chuyển đổi subtype thủ công.

### 9.1. Tránh phụ thuộc quá mức vào tên class Java

Couchbase document có tuổi thọ dài hơn một lần deploy. Nếu body đang chứa `"com.example.orders.WalletPayment"`, việc di chuyển class sang package khác có thể làm nhiều document lịch sử không đọc được. Alias ổn định giúp giảm phụ thuộc vào cấu trúc source code, nhưng alias vẫn phải được xem là **public storage contract**, không được đổi tùy tiện.

## 10. Chiến lược 2: dùng discriminator nghiệp vụ tường minh

Khi có nhiều client, ngôn ngữ hoặc vòng đời schema dài, hãy cân nhắc một field `kind` ổn định:

```json
{
  "payment": {
    "kind": "WALLET",
    "provider": "PAY_WALLET",
    "transactionRef": "TX-42"
  }
}
```

Trong trường hợp này, `kind` thuộc **hợp đồng nghiệp vụ do ứng dụng quản lý**, không phụ thuộc tên class Java. Một luồng đọc thường là:

1. Lấy object JSON hoặc persistence DTO có field `kind`.
2. Kiểm tra `kind` thuộc tập mã hợp lệ và schema các field tương ứng.
3. Ánh xạ sang subtype/domain object phù hợp, ví dụ `WalletPayment`.
4. Xử lý trường hợp biến thể chưa biết bằng chính sách tương thích rõ ràng.

Ví dụ DTO lưu trữ tường minh với dạng payload lồng nhau:

```java
public record PaymentPayload(
    String kind,
    String last4,
    String network,
    String provider,
    String transactionRef,
    String bankCode,
    String reference
) {}
```

Với mô hình này, các field không dùng cho từng biến thể được bỏ trống theo quy ước. Khi số biến thể nhiều, nên chuyển sang cấu trúc `{kind, data}` riêng từng loại hoặc một mapper DTO → domain, để tránh class có quá nhiều field nullable.

Mã giả rõ về ý tưởng:

```java
PaymentDetails decode(PaymentPayload p) {
    return switch (p.kind()) {
        case "CARD" -> new CardPayment(p.last4(), p.network());
        case "WALLET" -> new WalletPayment(
            p.provider(), p.transactionRef());
        case "BANK_TRANSFER" -> new BankTransferPayment(
            p.bankCode(), p.reference());
        default -> throw new IllegalArgumentException(
            "Unsupported payment kind: " + p.kind());
    };
}
```

Đoạn này xử lý mapping **ở ranh giới ứng dụng**. Nếu dựa trực tiếp vào subtype như field của entity Spring Data, phải xác minh cơ chế phân biệt kiểu của converter tương ứng. Một field `kind` trong JSON không tự khiến `MappingCouchbaseConverter` dùng nó để dựng interface bất kỳ.

### 10.1. So sánh hai chiến lược

| Tiêu chí | Spring Data `_class` | Discriminator nghiệp vụ `kind` |
| --- | --- | --- |
| Ai định nghĩa giá trị? | Framework/type mapper và class/alias Java | Nhóm thiết kế schema nghiệp vụ |
| Độ phụ thuộc vào Java | Cao nếu lưu full class name, thấp hơn với `@TypeAlias` | Thấp nếu mã `kind` không thay đổi theo class |
| Tương thích nhiều ngôn ngữ | Client khác phải hiểu metadata Spring Data | Dễ hơn nếu dùng JSON schema/documented codes |
| Khôi phục subtype | Converter có thể xử lý khi metadata/context đầy đủ | Cần mapping tường minh hoặc custom conversions |
| Thay package/refactor | Có thể cần migration type hint | Không ảnh hưởng nếu contract `kind` giữ nguyên |
| Query/index | Có thể lọc `_class` nhưng gắn với framework | Dễ diễn giải `payment.kind` như field nghiệp vụ |
| Dữ liệu lịch sử/unknown subtype | Cần alias/class mapping hợp lệ | Có thể chủ động hỗ trợ `UNKNOWN` hoặc version policy |

Không có lựa chọn áp dụng cho mọi hệ thống. Có thể dùng `_class` cho mục đích nội bộ Spring Data và **đồng thời có `kind`** như một field nghiệp vụ cho báo cáo, liên hệ hệ thống ngoài và kiểm tra schema. Khi dùng cả hai, cần bảo đảm chúng không mâu thuẫn.

## 11. SQL++ truy vấn enum và biến thể

Giả sử dữ liệu được lưu trong bucket `shop`, scope `sales`, collection `orders`.

### 11.1. Lọc theo enum được lưu dưới dạng string

```sql
SELECT META(o).id AS orderId, o.status
FROM `shop`.`sales`.`orders` AS o
WHERE o.status = "PAID";
```

Nếu ứng dụng đã thiết lập enum converter lưu `"paid"`, truy vấn trên phải thay `"PAID"` bằng `"paid"`. SQL++ thao tác trên **giá trị JSON thực**; nó không biết enum Java của ứng dụng được đặt tên ra sao.

### 11.2. Lọc theo discriminator nghiệp vụ

```sql
SELECT META(o).id AS orderId,
       o.payment.provider AS walletProvider
FROM `shop`.`sales`.`orders` AS o
WHERE o.payment.kind = "WALLET";
```

Một index ví dụ cho workload hay lọc ví:

```sql
CREATE INDEX ix_orders_payment_kind
ON `shop`.`sales`.`orders`(payment.kind);
```

Index cần được đánh giá theo predicate thực tế, thêm filter khác, sort và selectivity. `MappingCouchbaseConverter` không tự tạo index.

### 11.3. Kiểu của field khi dữ liệu lệch schema

Có thể kiểm tra dữ liệu chưa chuẩn hóa:

```sql
SELECT META(o).id AS orderId,
       TYPE(o.status) AS statusType,
       TYPE(o.payment.kind) AS paymentKindType
FROM `shop`.`sales`.`orders` AS o
WHERE TYPE(o.status) != "string"
   OR o.payment.kind IS MISSING;
```

SQL++ phân biệt `NULL` với `MISSING`. Trong dữ liệu nhiều biến thể, field riêng cho card có thể **không tồn tại** trong wallet payload và điều đó hoàn toàn hợp lệ. Ngược lại, thiếu `kind` khi hợp đồng bắt buộc field này là một lỗi schema.

**Không nên query toàn bộ order bằng một điều kiện trên field chỉ có ở một số subtype** rồi mặc định những subtype khác là dữ liệu lỗi. Hãy xét `kind` hoặc type hint trước.

## 12. Schema evolution: thêm, đổi tên và loại bỏ biến thể

Hệ thống có thể trải qua các thay đổi:

- Thêm `REFUNDED` vào `OrderStatus`.
- Đổi tên Java constant `PAID` thành `SETTLED`.
- Đổi cấu trúc `Money` từ `{amountMinor, currency}` sang thêm `scaleVersion`.
- Thêm loại `PAY_LATER` cho `PaymentDetails`.
- Di chuyển class `WalletPayment` sang package khác.

Đây là các thay đổi **storage contract**, không chỉ refactor code.

### 12.1. Thiết kế migration từng bước

Một quy trình hữu ích:

1. **Khảo sát JSON đang tồn tại**: giá trị enum, kiểu field, hình dạng object, alias/class discriminator, field thiếu và tần suất từng biến thể.
2. **Định nghĩa đích**: mã enum ổn định, định dạng value object, danh sách `kind`, quy tắc unknown và field bắt buộc.
3. **Triển khai đường đọc tương thích trước**: chấp nhận cả định dạng cũ và mới ở giai đoạn chuyển tiếp, nhưng reject dữ liệu không thể hiểu an toàn.
4. **Chuyển đường ghi sang định dạng mới**: bảo đảm mọi service ghi nhất quán, dùng CAS/optimistic locking hoặc transaction phù hợp khi cập nhật document đồng thời.
5. **Backfill document lịch sử** bằng job có khả năng retry/idempotent. Quan sát lỗi parse và tỷ lệ các biến thể cũ.
6. **Cập nhật query/index** theo field/giá trị mới, kiểm tra kế hoạch SQL++.
7. **Thu hẹp tương thích** sau khi mọi reader và client đã sẵn sàng, có đo lường thay vì đoán.

Thứ tự triển khai reader/writer phải được quyết định cùng với khả năng rollback. Một writer chỉ dùng mã mới có thể khiến reader cũ gặp trạng thái chưa biết ngay cả khi code mới chạy đúng.

### 12.2. Versioning dữ liệu nhiều biến thể

Đối với cấu trúc phức tạp, có thể thêm:

```json
{
  "payment": {
    "kind": "WALLET",
    "schemaVersion": 2,
    "data": {
      "provider": "PAY_WALLET",
      "transactionRef": "TX-42"
    }
  }
}
```

`schemaVersion` là **version schema của payload**, khác hoàn toàn với `@Version` dùng CAS optimistic locking. Một là quy ước ứng dụng; một là metadata đồng bộ ghi. Không dùng số CAS làm schema version.

Khi thay đổi làm mất tương thích, dựa trên cặp `kind + schemaVersion` để chọn parser/migration rõ ràng; hạn chế logic đoán biến thể từ sự hiện diện ngẫu nhiên của một field.

## 13. Kiểm tra bất biến và dữ liệu không đáng tin cậy

Couchbase có thể được ghi bởi SDK trực tiếp, import, script vận hành hay service khác. Không nên dựa vào constructor Java để bảo đảm mọi document đang lưu đều hợp lệ.

Các bất biến quan trọng:

| Dữ liệu | Quy tắc cần kiểm tra |
| --- | --- |
| `OrderStatus` | Mã hợp lệ; chuyển trạng thái theo workflow. |
| `SkuCode` | Độ dài, ký tự, chuẩn hóa và tính duy nhất nếu nghiệp vụ yêu cầu. |
| `Money` | `currency` hợp lệ, amount không overflow và quy tắc scale. |
| `CARD` payload | Có các field card cần thiết; không vô tình chứa dữ liệu nhạy cảm không cần lưu. |
| `WALLET` payload | Có `provider` và transaction reference hợp lệ. |
| `kind`/`schemaVersion` | Kết hợp mã và version được hỗ trợ; parser không bỏ qua field bắt buộc. |
| `_class` | Chỉ sử dụng type mapping đã được ứng dụng biết và kiểm thử; không tự tin nhận mọi type hint lạ từ tài liệu không tin cậy. |

Không ghi toàn bộ số thẻ, CVV hoặc thông tin xác thực thanh toán vào document ví dụ; chỉ lưu token/tham chiếu hoặc dữ liệu tối thiểu phục vụ nghiệp vụ theo chính sách hệ thống.

Một field được Java khai báo `non-null` chưa bảo đảm document cũ luôn có field đó. Với record/immutable entity, lỗi có thể xảy ra khi constructor cần giá trị nhưng dữ liệu thực thiếu. Nên kiểm thử dữ liệu vắng mặt, `null` và unknown variant.

## 14. Lưu ý về repository, template, reactive và giao dịch

Khi làm việc qua `CouchbaseRepository`, `CouchbaseTemplate` hoặc các API reactive để truy cập entity, tầng mapping của Spring Data hỗ trợ chuyển object Java sang biểu diễn document và đọc ngược theo cấu hình. Tuy nhiên:

- **SDK trực tiếp** dùng `JsonObject` hoặc serializer riêng có thể bỏ qua metadata annotation và converter đã đăng ký trong Spring Data.
- **Truy vấn SQL++ projection** chỉ trả một số field có thể thiếu `_class` hoặc `kind`; không nên cố dựng full entity/subtype nếu dữ liệu không đủ.
- **Reactive** thay đổi cách điều phối I/O và kết quả bất đồng bộ, không tự thay đổi hợp đồng enum hay subtype của JSON.
- **CAS/optimistic locking** bảo vệ cập nhật đồng thời nhưng không tự kiểm chứng phép chuyển trạng thái nghiệp vụ.
- **Transaction** bảo vệ tính nguyên tử của chuỗi thao tác đủ điều kiện; nó không tự chuyển định dạng JSON cũ thành mới.
- **Bucket/scope/collection** quy định nơi chứa document; thiết kế khóa và index phải dựa trên query/access pattern thực tế.

Hai service có thể đọc cùng JSON nhưng xử lý khác nếu phiên bản enum/converter khác nhau. Vì vậy, hợp đồng dữ liệu và chính sách rollout có vai trò ngang với việc viết class Java.

## 15. Quy trình debug lỗi enum, value object và đa hình

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Lỗi đọc enum | JSON có mã chưa biết hoặc khác chữ hoa/chữ thường | Kiểm tra raw JSON và chính sách unknown; triển khai parser/migration tương thích. |
| Thêm enum mới làm service cũ lỗi | Reader cũ không hiểu giá trị mới | Triển khai reader tương thích trước khi writer xuất mã mới, hoặc chấp nhận xử lý unknown. |
| Enum lưu thành tên hằng thay vì `code()` | Chưa đăng ký hoặc converter không được chọn | Kiểm tra cấu hình `CouchbaseCustomConversions` và JSON ghi thực tế. |
| `SkuCode` trong JSON là object thay vì string | Mapping đang sử dụng nested object thay vì custom converter mong muốn | Kiểm tra converter đã đăng ký, hướng và thứ tự ưu tiên. |
| Lỗi dựng value object | Dữ liệu lịch sử vi phạm validation hoặc constructor không phù hợp | Làm sạch dữ liệu, chọn constructor persistence và quy tắc migration. |
| Không dựng được subtype `PaymentDetails` | Thiếu `_class`/alias, type chưa được biết hoặc projection thiếu type hint | Kiểm tra payload, mapping context và kiểu đích; dùng DTO/domain mapper tường minh nếu cần. |
| Đổi package làm document cũ lỗi | `_class` đang lưu full class name cũ | Có chiến lược alias/migration, tránh refactor storage contract tùy tiện. |
| Filter SQL++ không khớp enum | Truy vấn `"PAID"` trong khi JSON lưu `"paid"` | Query theo giá trị lưu trữ thực; cập nhật index và code nhất quán. |
| Kết quả SDK khác repository | Hai đường dùng serializer/converter khác nhau | Chuẩn hóa hợp đồng JSON và kiểm thử cả hai đường. |
| Thêm subtype mới gây báo cáo sai | Báo cáo suy loại từ field riêng thay vì discriminator ổn định | Dùng `kind` và schema version, cập nhật query. |

Quy trình xác minh nên theo thứ tự **object đầu vào → `MappingCouchbaseConverter.write` → `CouchbaseDocument`/JSON body → kết quả truy vấn SQL++ → `read` sang entity/domain**. Với lỗi nhiều biến thể, kiểm tra riêng `_class`, `kind` và tên/alias type đã được đăng ký.

## 16. Thực hành có hướng dẫn

### Bài 1 — Enum và rename

1. Tạo `OrderDocument` với `OrderStatus.PAID` và kiểm tra JSON body.
2. Thay tên Java constant thành `PAYMENT_COMPLETED` trên một nhánh thử nghiệm.
3. Đọc lại document cũ, ghi nhận lỗi hoặc hành vi thực tế.
4. Thiết kế một `code` độc lập như `"paid"`; kiểm thử custom converter theo cả hai chiều.
5. Đề xuất trình tự rollout để service cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

### Bài 2 — Value object và custom conversion

1. Tạo `SkuCode` với constructor validation.
2. Đăng ký converter `SkuCode ↔ String`, ghi entity với repository hoặc `CouchbaseTemplate`.
3. Đọc JSON raw và kiểm tra `sku` là string.
4. Tạo document chứa SKU không hợp lệ bằng đường thử nghiệm; quan sát lỗi chuyển đổi lúc đọc.
5. So sánh việc lưu `SkuCode` thành string với một object `{"value": "..."}` về query, validation và migration.

### Bài 3 — Tiền dưới dạng object

1. Tạo `Money` với `amountMinor` và `currency`.
2. Lưu hai document ở hai currency khác nhau.
3. Truy vấn SQL++ lấy `total.currency` và `total.amountMinor`.
4. Giải thích vì sao không thể cộng trực tiếp amount của hai currency.
5. Thêm field `schemaVersion` cho những thay đổi lớn và xác định đường đọc dữ liệu cũ.

### Bài 4 — Polymorphic payment

1. Thiết kế `CardPayment` và `WalletPayment` với một field kiểu interface ở entity chủ.
2. Kiểm tra type hint/alias thực tế bằng `CouchbaseDocument.export()` và round-trip.
3. Tạo phiên bản persistence DTO có `payment.kind` tường minh, chuyển đổi sang domain object bằng switch.
4. So sánh hành vi khi thêm subtype mới mà reader cũ chưa biết.
5. Viết SQL++ thống kê số document theo `payment.kind`; xem xét index theo workload.

### Câu hỏi tự kiểm tra

1. Vì sao tên enum Java cũng có thể trở thành hợp đồng JSON?
2. Điều gì có thể xảy ra khi lưu `enum.ordinal()`?
3. Vì sao `OrderStatus.code()` không tự thay đổi cách mapping Spring Data?
4. Khi nào value object nên được lưu thành scalar, khi nào nên giữ object lồng nhau?
5. Sự khác nhau giữa `@ReadingConverter` và `@WritingConverter` là gì?
6. Vì sao phải test converter trong cấu hình thật thay vì chỉ gọi phương thức `convert`?
7. `_class` có vai trò gì trong việc khôi phục subtype?
8. Khi nào `@TypeAlias` có ích, và vì sao alias cũng cần versioning/migration?
9. Vì sao field `kind` không tự động làm Spring Data dựng đúng interface subtype?
10. Khác biệt giữa `schemaVersion` và `@Version` sử dụng CAS là gì?
11. Một custom SQL++ projection thiếu discriminator có thể gây lỗi gì?
12. Nếu SDK khác ngôn ngữ và Spring Data cùng ghi một collection, cần thống nhất những gì?

## Tài liệu tham khảo

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): mapping entity, enum, `@Field`, cấu trúc object và type information.
- [Spring Data Couchbase — Custom Conversions](https://docs.spring.io/spring-data/couchbase/reference/data-commons/custom-conversions.html): converter theo chiều đọc/ghi và cách cấu hình.
- [Spring Data Commons — Type Mapping](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): cơ chế persistent entity, `@TypeAlias`, constructors và mapping metadata.
- [Spring Data Couchbase — `MappingCouchbaseConverter` API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/convert/MappingCouchbaseConverter.html): đọc/ghi và customization.
- [Couchbase Server — SQL++ Data Types](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/datatypes.html): number, string, object, array, `NULL` và `MISSING`.
- [Couchbase Server — CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): chỉ mục phục vụ truy vấn các field enum và discriminator.

> Với enum, value object và dữ liệu nhiều biến thể, hãy xác định **hợp đồng JSON ổn định trước khi phát hành**. Mapping Java chỉ là một trong các đường đọc/ghi; mọi client, truy vấn SQL++ và job migration đều phải hiểu cùng giá trị và cùng cấu trúc.

