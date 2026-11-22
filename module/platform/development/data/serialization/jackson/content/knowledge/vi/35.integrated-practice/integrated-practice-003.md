# Bảo toàn số tiền, thời điểm và mã định danh qua vòng đọc ghi

Trong một ứng dụng Java, Jackson thường chuyển DTO thành JSON để lưu trữ hoặc trao đổi, rồi đọc JSON trở lại thành object. Một vòng đọc ghi tưởng như đơn giản vẫn có thể làm sai dữ liệu nếu ứng dụng không quy định rõ cách biểu diễn số tiền, thời điểm và mã định danh. Các lỗi thường gặp gồm dùng double cho tiền, mất precision khi client JavaScript đọc số nguyên lớn, biến mã có số 0 đầu thành số, hoặc làm thời điểm thay đổi do timezone và độ chính xác phần giây.

Muốn dữ liệu giữ nguyên ý nghĩa qua vòng đọc ghi, cần thiết kế hợp đồng JSON cho từng nhóm giá trị, chọn kiểu Java phù hợp, cấu hình Jackson nhất quán và kiểm thử bằng dữ liệu biên. **Serialization thành công không đồng nghĩa dữ liệu được bảo toàn.** Cần so sánh giá trị theo đúng semantics: tiền theo số học và scale được quy định, thời điểm theo instant/offset/precision, còn định danh theo chuỗi ký tự chính xác.

Bài học này tập trung vào ba nhóm dữ liệu thường gây lỗi trong hệ thống nghiệp vụ: tiền, thời điểm và mã định danh. Các ví dụ dùng Jackson Databind với JSON, nhưng nguyên tắc hợp đồng cũng áp dụng khi dữ liệu được lưu trong database, gửi qua message broker hoặc được tiêu thụ bởi client không phải Java.

## 1. Vòng đọc ghi cần bảo toàn điều gì?

Một vòng đọc ghi cơ bản:

```text
Java object
    │
    ▼
ObjectMapper.writeValueAsString(...)
    │
    ▼
JSON payload
    │
    ▼
ObjectMapper.readValue(...)
    │
    ▼
Java object mới
```

Có thể biểu diễn bằng code:

```java
String json = mapper.writeValueAsString(original);
Payment restored = mapper.readValue(json, Payment.class);
```

Với một object đơn giản, ta thường kiểm tra equals. Nhưng phép so sánh này chỉ có ý nghĩa nếu equals của model phản ánh đúng semantics. Ví dụ BigDecimal.equals phân biệt scale; byte array trong record được so sánh theo identity; LocalDateTime không chứa timezone; một ID dạng số có thể đã mất số 0 đầu trước khi được tạo object.

Vì vậy cần xác định điều kiện bảo toàn riêng cho từng field:

| Nhóm dữ liệu | Điều cần giữ |
| --- | --- |
| Số tiền | Giá trị chính xác, currency, scale/quy tắc làm tròn và đơn vị |
| Thời điểm | Instant, offset/timezone theo hợp đồng và độ chính xác |
| Mã định danh | Toàn bộ ký tự, kể cả số 0 đầu, chữ hoa/thường và dấu phân cách |
| Số nguyên lớn | Toàn bộ giá trị, không bị làm tròn bởi consumer |
| Giá trị tùy chọn | Phân biệt missing, null, zero và empty nếu nghiệp vụ yêu cầu |

Không nên mặc định JSON number, JSON string và Java type là các biểu diễn thay thế tương đương. Kiểu wire là một phần của hợp đồng API.

## 2. Chọn kiểu Java đúng trước khi cấu hình Jackson

Jackson chỉ có thể bảo toàn dữ liệu mà kiểu Java còn giữ được. Nếu dữ liệu đã bị làm tròn hoặc mất thông tin trước khi gọi writeValue, serializer không thể khôi phục lại.

Ví dụ tiền:

```java
double amount = 0.1 + 0.2;
System.out.println(amount); // Có thể hiển thị 0.30000000000000004
```

Sai số đã xuất hiện trong phép tính binary floating point. Chuyển giá trị đó thành JSON không làm nó trở thành số thập phân chính xác.

Dùng BigDecimal cho số tiền và số thập phân cần precision xác định:

```java
BigDecimal amount = new BigDecimal("0.30");
```

Không tạo BigDecimal từ một biểu thức double nếu muốn giữ giá trị thập phân dự kiến:

```java
// Không nên dùng cho tiền:
BigDecimal wrong = new BigDecimal(0.1);

// Dùng chuỗi thập phân hoặc value đã được parse chính xác:
BigDecimal correct = new BigDecimal("0.1");
```

Với thời điểm, chọn kiểu theo ý nghĩa:

- **Instant**: một điểm duy nhất trên UTC timeline, phù hợp event timestamp và thời điểm tạo record.
- **OffsetDateTime**: thời điểm kèm offset UTC cụ thể, ví dụ +07:00.
- **ZonedDateTime**: thời điểm gắn với vùng timezone có quy tắc lịch sử như Asia/Ho_Chi_Minh.
- **LocalDate**: ngày lịch không có giờ.
- **LocalDateTime**: ngày và giờ địa phương không chứa offset/timezone.

Với định danh, ưu tiên String hoặc value object chứa String nếu ID là mã, không phải đại lượng dùng để tính toán. Ví dụ "0001042" và "1042" có thể là hai mã khác nhau dù cùng giá trị số học.

## 3. Bảo toàn số tiền bằng BigDecimal

### 3.1. Vì sao không dùng float hoặc double?

float và double lưu số theo biểu diễn nhị phân dấu phẩy động. Nhiều số thập phân hữu hạn không thể được biểu diễn chính xác trong hệ nhị phân. Điều này có thể tạo sai số tích lũy khi cộng, trừ, nhân hoặc chia.

Ví dụ:

```java
double total = 0.1 + 0.2;
System.out.println(total); // 0.30000000000000004
```

Nếu serialize giá trị này, JSON có thể chứa một số dài hơn giá trị nghiệp vụ mong muốn. Nếu client parse sang binary floating point, sai số tiếp tục tồn tại.

Với tiền, dùng:

```java
BigDecimal unitPrice = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");

BigDecimal total = unitPrice.multiply(quantity);
```

Kết quả số học thập phân chính xác theo giá trị và scale của các operand.

### 3.2. Không tạo BigDecimal từ double

Hai cách tạo sau không tương đương:

```java
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
```

fromText giữ đúng decimal 0.1. fromDouble nhận giá trị binary floating point đã được làm tròn trước khi tạo BigDecimal và có thể chứa nhiều chữ số ngoài dự kiến.

Nếu nguồn đầu vào là JSON decimal, deserialize trực tiếp vào field BigDecimal:

```java
public record InvoiceLine(
    String sku,
    BigDecimal unitPrice,
    int quantity
) {}
```

```java
InvoiceLine line = mapper.readValue(json, InvoiceLine.class);
```

Không đọc giá trị thành double rồi mới chuyển sang BigDecimal.

### 3.3. BigDecimal có cả value và scale

BigDecimal biểu diễn một giá trị bằng unscaled integer và scale. Vì vậy hai giá trị có thể bằng nhau về số học nhưng không bằng nhau theo equals:

```java
BigDecimal a = new BigDecimal("19.9");
BigDecimal b = new BigDecimal("19.90");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(a.scale());           // 1
System.out.println(b.scale());           // 2
```

Cần quyết định scale có thuộc hợp đồng hay không:

- Nếu chỉ quan tâm giá trị số học, dùng compareTo trong assertion.
- Nếu tiền luôn phải có hai chữ số thập phân, validate scale hoặc chuẩn hóa tại boundary nghiệp vụ.
- Nếu scale thể hiện độ chính xác đo lường, không tự ý loại bỏ trailing zero.
- Nếu hệ thống lưu scale gốc để audit, cần giữ lexical/scale theo chính sách đã chọn.

Không dùng stripTrailingZeros một cách vô điều kiện nếu scale là thông tin cần bảo toàn. Phương thức này có thể thay đổi scale và đôi khi tạo biểu diễn exponent.

### 3.4. Chọn JSON number hay JSON string cho tiền

Có hai cách biểu diễn thường gặp.

JSON number:

```json
{
  "amount": 19.95,
  "currency": "USD"
}
```

JSON string:

```json
{
  "amount": "19.95",
  "currency": "USD"
}
```

JSON number phù hợp khi hợp đồng xác định decimal semantics và consumer có parser giữ precision. JavaScript Number dùng binary floating point, vì vậy consumer có thể mất độ chính xác khi xử lý các số thập phân hoặc số lớn. JSON string có thể phù hợp khi cần bảo toàn lexical decimal qua nhiều hệ thống, nhưng consumer phải parse theo decimal type và schema phải công bố field là string.

Không đổi number thành string tùy tiện vì đó là thay đổi wire type. Chọn một dạng theo consumer và version hóa nếu cần đổi.

### 3.5. Money phải chứa cả amount và currency

Một số 19.95 không đủ để mô tả tiền nếu không biết currency. 19.95 USD, 19.95 EUR và 19.95 VND có ý nghĩa khác nhau.

Có thể dùng value object:

```java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }
}
```

DTO response:

```java
public record MoneyResponse(
    BigDecimal amount,
    String currency
) {}
```

Mapping:

```java
MoneyResponse toResponse(Money money) {
    return new MoneyResponse(
        money.amount(),
        money.currency().getCurrencyCode()
    );
}
```

JSON:

```json
{
  "amount": 1250.00,
  "currency": "VND"
}
```

Nếu ứng dụng cần một quy tắc scale theo currency, hãy định nghĩa ở domain layer hoặc money policy. Không giả định mọi currency đều có hai chữ số thập phân. Cũng không dùng format hiển thị theo locale như 1.250,00 ₫ làm dữ liệu trao đổi máy đọc được.

### 3.6. Làm tròn là quyết định nghiệp vụ

Các phép chia có thể tạo decimal vô hạn. Cần chỉ định scale và rounding mode ở đúng bước nghiệp vụ:

```java
BigDecimal taxRate = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("19.95")
    .multiply(taxRate)
    .setScale(2, RoundingMode.HALF_UP);
```

Không để serializer tự làm tròn số tiền. Serialization nên biểu diễn giá trị đã được domain quyết định. Nếu làm tròn trong custom serializer, các đường ghi khác như database, message hoặc export có thể tạo kết quả khác nhau.

### 3.7. Cấu hình Jackson cho BigDecimal

Với field có kiểu BigDecimal, Jackson Databind có thể serialize thành JSON number và deserialize trực tiếp về BigDecimal:

```java
ObjectMapper mapper = JsonMapper.builder()
    .build();

public record Payment(
    String paymentId,
    BigDecimal amount,
    String currency
) {}

Payment payment = mapper.readValue(
    """
    {
      "paymentId": "pay-1001",
      "amount": 19.9500,
      "currency": "USD"
    }
    """,
    Payment.class
);
```

Với untyped data như Object hoặc Map<String, Object>, JSON floating number có thể được ánh xạ thành Double theo mặc định. Nếu cần dùng BigDecimal cho floating values trong untyped binding, cân nhắc USE_BIG_DECIMAL_FOR_FLOATS:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .build();
```

Cấu hình này ảnh hưởng untyped number handling; nó không thay thế việc khai báo field nghiệp vụ bằng BigDecimal. Hãy kiểm tra kiểu thực tế khi đọc vào Map hoặc Object.

### 3.8. Kiểm thử số tiền

Fixture cần có các trường hợp:

- Giá trị nhỏ như 0.01.
- Giá trị có trailing zero như 19.9500.
- Giá trị lớn.
- Giá trị âm nếu nghiệp vụ cho phép.
- Zero.
- Scale khác nhau.
- Số có exponent notation nếu producer có thể phát.
- Giá trị vượt giới hạn hoặc sai kiểu.

Ví dụ:

```java
@Test
void preservesMoneyValueAndScaleThroughJson() throws Exception {
    Payment original = new Payment(
        "pay-1001",
        new BigDecimal("19.9500"),
        "USD"
    );

    String json = mapper.writeValueAsString(original);
    Payment restored = mapper.readValue(json, Payment.class);

    assertEquals(original.paymentId(), restored.paymentId());
    assertEquals(0, original.amount().compareTo(restored.amount()));
    assertEquals(original.amount().scale(), restored.amount().scale());
    assertEquals(original.currency(), restored.currency());
}
```

Nếu scale không thuộc contract, bỏ assertion scale và dùng compareTo. Nếu scale có ý nghĩa, giữ assertion riêng như ví dụ.

## 4. Bảo toàn thời điểm và timezone

### 4.1. Phân biệt Instant, OffsetDateTime và LocalDateTime

Ba kiểu thường bị nhầm:

```java
Instant instant = Instant.parse("2026-11-12T03:30:00Z");

OffsetDateTime offset = OffsetDateTime.parse(
    "2026-11-12T10:30:00+07:00"
);

LocalDateTime local = LocalDateTime.parse(
    "2026-11-12T10:30:00"
);
```

- Instant xác định một điểm duy nhất trên UTC timeline.
- OffsetDateTime xác định thời điểm cùng offset.
- LocalDateTime chỉ là ngày/giờ trên đồng hồ địa phương; nó không xác định duy nhất một instant.

2026-11-12T03:30:00Z và 2026-11-12T10:30:00+07:00 là cùng một instant. Nhưng nếu hợp đồng cần giữ offset ban đầu, chỉ so sánh instant là chưa đủ.

LocalDateTime không nên dùng cho event timestamp toàn hệ thống nếu consumer cần biết chính xác thời điểm xảy ra. Nó phù hợp với giờ hẹn địa phương hoặc thời gian trên lịch chưa gắn timezone, nhưng cần một timezone rule riêng khi chuyển thành instant.

### 4.2. Chọn biểu diễn JSON cho timestamp

Dạng ISO-8601 string dễ đọc:

```json
{
  "occurredAt": "2026-11-12T03:30:00Z"
}
```

Dạng timestamp số:

```json
{
  "occurredAt": 1794454200
}
```

Số timestamp cần quy định rõ epoch và đơn vị:

- Epoch seconds.
- Epoch milliseconds.
- Có fractional seconds hay không.
- Giá trị có phải UTC không.

Nếu consumer không biết đơn vị, cùng một số có thể bị hiểu thành thời điểm khác nhau hàng nghìn lần. Với API công khai, ISO-8601 UTC string thường dễ hiểu hơn và tránh mơ hồ đơn vị epoch.

### 4.3. Đăng ký JavaTimeModule

Jackson dùng module jackson-datatype-jsr310 để hỗ trợ các kiểu java.time.

Maven dependency khi dùng Jackson BOM:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
```

Cấu hình mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Với cấu hình này, các kiểu Java Time thường được ghi dưới dạng chuỗi ISO thay vì timestamp dạng số/array. Hình dạng chính xác tùy kiểu dữ liệu và version/module; hãy lưu fixture cho từng kiểu được dùng.

Nếu dùng Spring Boot, mapper có thể được auto-configure và module được tự đăng ký qua dependency. Tránh tạo mapper mới ngoài cấu hình ứng dụng nếu muốn giữ cùng behavior.

### 4.4. Instant là lựa chọn tốt cho thời điểm sự kiện

Ví dụ DTO:

```java
public record AuditEvent(
    String eventId,
    Instant occurredAt
) {}
```

JSON:

```json
{
  "eventId": "evt-2001",
  "occurredAt": "2026-11-12T03:30:00Z"
}
```

Instant không lưu timezone vùng hoặc offset ban đầu; nó lưu thời điểm trên timeline. Nếu nghiệp vụ cần biết người dùng nhập giờ ở vùng nào, lưu thêm zone ID hoặc offset như một field riêng.

Ví dụ lịch hẹn:

```java
public record Appointment(
    LocalDateTime localStart,
    String zoneId
) {}
```

JSON:

```json
{
  "localStart": "2026-11-12T10:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Khi chuyển thành Instant, dùng ZoneId tương ứng và xác định chính sách cho thời điểm ambiguous hoặc nonexistent do daylight saving time ở những vùng có DST. Không giả định LocalDateTime tự mang timezone.

### 4.5. Offset không giống timezone region

Offset như +07:00 chỉ là độ lệch so với UTC tại một thời điểm. Zone ID như Asia/Ho_Chi_Minh đại diện cho bộ quy tắc thời gian của vùng, có thể bao gồm thay đổi lịch sử hoặc chính sách tương lai.

Nếu chỉ cần biết instant, lưu Instant. Nếu cần giữ offset do client gửi, lưu OffsetDateTime. Nếu cần tái tạo lịch địa phương theo quy tắc vùng, lưu zone ID cùng local date/time hoặc mô hình thời gian phù hợp.

Đừng chỉ lưu +07:00 nếu nghiệp vụ cần quy tắc vùng. Cũng đừng dùng timezone của máy chủ làm timezone mặc định ngầm cho mọi payload.

### 4.6. Precision phần giây

Java Instant hỗ trợ nanosecond precision. Hệ thống khác có thể chỉ giữ milliseconds hoặc microseconds. Khi serialize rồi deserialize trong Jackson, cần xác định precision hợp đồng và kiểm thử.

Ví dụ:

```java
Instant original = Instant.parse("2026-11-12T03:30:00.123456789Z");
```

Nếu database column chỉ giữ milliseconds, dữ liệu có thể bị truncate trước khi Jackson đọc lại. Nếu client parse timestamp thành kiểu chỉ giữ milliseconds, precision cũng có thể mất ở client.

Không dùng string comparison nếu hợp đồng chỉ yêu cầu cùng instant sau khi làm tròn đến precision đã công bố. Nhưng nếu API phải giữ nanoseconds, kiểm tra cả fractional digits và giá trị sau parse.

### 4.7. @JsonFormat và định dạng tường minh

Có thể dùng @JsonFormat khi contract yêu cầu một pattern cụ thể:

```java
public record LegacyEvent(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime occurredAt
) {}
```

Cần cẩn thận với pattern không chứa offset/timezone. Một timestamp chỉ có ngày giờ không thể tự xác định instant. Nếu pattern custom được dùng, hãy ghi rõ timezone/offset policy và test parse/serialize hai chiều.

Không trộn nhiều format cho cùng field mà không có migration policy. Nếu cần đọc cả timestamp số cũ và ISO string mới, dùng DTO version hoặc custom deserializer có kiểm soát.

### 4.8. Kiểm thử thời điểm

Một test cho Instant:

```java
@Test
void preservesInstantThroughJson() throws Exception {
    AuditEvent original = new AuditEvent(
        "evt-2001",
        Instant.parse("2026-11-12T03:30:00.123456789Z")
    );

    String json = mapper.writeValueAsString(original);
    AuditEvent restored = mapper.readValue(json, AuditEvent.class);

    assertEquals(original.eventId(), restored.eventId());
    assertEquals(original.occurredAt(), restored.occurredAt());
}
```

Với OffsetDateTime, nếu cần giữ offset ban đầu, kiểm tra cả offset:

```java
assertEquals(
    original.occurredAt().getOffset(),
    restored.occurredAt().getOffset()
);
```

Nếu chỉ cần cùng instant, so sánh toInstant. Nếu cần cùng local wall time và zone ID, kiểm tra các thành phần đó riêng. Assertion phải phản ánh contract thay vì chọn phép so sánh tiện nhất.

## 5. Bảo toàn mã định danh

### 5.1. ID là mã, không phải số học

Các giá trị như:

- Customer code "0001042".
- Account number "001234567890".
- Postal code "700000".
- Product SKU "000-A12".
- UUID "8f14e45f-ea4a-4f2b-9a3b-8c0e2f4d6a10".

thường là định danh. Không cộng, trừ hoặc nhân chúng. Dùng String giúp giữ nguyên số 0 đầu, dấu gạch nối và chữ cái.

Nếu đọc "0001042" thành integer 1042, thông tin ban đầu đã mất. Khi serialize lại, Jackson không thể biết có bao nhiêu số 0 cần thêm.

### 5.2. Số nguyên lớn và JavaScript Number

Java long có thể chứa số nguyên lớn hơn giới hạn integer an toàn của JavaScript Number. JavaScript Number chỉ biểu diễn chính xác mọi integer trong khoảng:

```text
-(2^53 - 1) đến +(2^53 - 1)
```

Nếu API gửi ID dạng JSON number vượt giới hạn này, client JavaScript có thể làm tròn khi parse JSON. Ví dụ:

```json
{
  "id": 9007199254740993
}
```

Một Java backend có thể deserialize chính xác vào long, nhưng trình duyệt hoặc Node.js dùng JSON.parse có thể không giữ nguyên integer đó.

Với ID lớn được trao đổi qua nhiều ngôn ngữ, JSON string thường an toàn hơn:

```json
{
  "id": "9007199254740993"
}
```

Đây là quyết định wire contract. Nếu field hiện tại là number, đổi thành string là breaking change đối với client cần migration/versioning.

### 5.3. Serialize Long thành string khi contract yêu cầu

Nếu domain dùng Long nhưng JSON contract yêu cầu ID dạng string, có thể dùng DTO String:

```java
public record CustomerResponse(
    String id,
    String displayName
) {}
```

Mapping:

```java
new CustomerResponse(
    Long.toString(customer.getId()),
    customer.getDisplayName()
);
```

Hoặc dùng serializer ToStringSerializer cho field:

```java
public record CustomerResponse(
    @JsonSerialize(using = ToStringSerializer.class)
    Long id,
    String displayName
) {}
```

Cách DTO String thường làm wire type rõ ràng hơn. Khi đọc lại, dùng Long.parseLong ở boundary nếu domain thật sự cần Long; validate range và format trước khi chuyển đổi.

### 5.4. UUID và mã có format cố định

UUID nên được trao đổi dưới dạng string canonical:

```java
UUID id = UUID.fromString(
    "8f14e45f-ea4a-4f2b-9a3b-8c0e2f4d6a10"
);
```

Jackson có thể serialize UUID thành chuỗi. Nếu ứng dụng yêu cầu chữ thường, dạng có dấu gạch nối hoặc một representation riêng, hãy quy định trong contract và test output.

Đừng chuẩn hóa ID bằng cách trim, uppercase/lowercase hoặc bỏ dấu phân cách nếu hệ thống nguồn xem các ký tự đó có ý nghĩa. Một số loại identifier không phân biệt hoa thường, nhưng đó phải là quy tắc của chính identifier chứ không phải giả định chung.

### 5.5. Value object cho ID

Có thể tạo kiểu riêng để tránh truyền nhầm các loại ID:

```java
public record CustomerId(String value) {
    public CustomerId {
        Objects.requireNonNull(value);
        if (value.isBlank()) {
            throw new IllegalArgumentException("CustomerId is blank");
        }
    }
}
```

Một cách ánh xạ scalar JSON string là dùng @JsonValue và @JsonCreator:

```java
public record CustomerId(String value) {

    @JsonValue
    public String value() {
        return value;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static CustomerId fromJson(String value) {
        return new CustomerId(value);
    }
}
```

JSON:

```json
{
  "customerId": "0001042"
}
```

Field Java có thể dùng CustomerId, nhưng wire representation vẫn là string. Cần kiểm thử cả deserialize và serialize, đặc biệt với null, empty, whitespace và mã không hợp lệ.

### 5.6. Không dùng ID làm key số nếu cần giữ lexical form

JSON object property name luôn là string. Tuy nhiên, nếu code parse Map key thành Integer hoặc Long, lexical form có thể bị mất.

Ví dụ:

```json
{
  "accounts": {
    "0012": "active",
    "12": "closed"
  }
}
```

Nếu chuyển key sang integer, hai key có thể trở thành cùng giá trị số 12. Dùng Map<String, ...> nếu key là mã. Nếu cần custom key type, viết key deserializer giữ nguyên chuỗi và validate format.

## 6. Đặt tiền, thời điểm và ID trong cùng một DTO

Một model payment có thể định nghĩa:

```java
public record PaymentEvent(
    String paymentId,
    String customerId,
    BigDecimal amount,
    String currency,
    Instant occurredAt
) {}
```

JSON contract:

```json
{
  "paymentId": "pay-0001042",
  "customerId": "cus-9007199254740993",
  "amount": 1250.00,
  "currency": "VND",
  "occurredAt": "2026-11-12T03:30:00Z"
}
```

Các lựa chọn có chủ đích:

- ID là string để giữ format và tránh giới hạn integer an toàn của client.
- Amount là decimal, không qua double.
- Currency là mã ISO 4217.
- Timestamp là ISO-8601 UTC string để tránh mơ hồ đơn vị epoch.

DTO không nên chứa format hiển thị theo locale. Ví dụ 1.250,00 ₫ phù hợp UI nhưng không phù hợp làm wire value nếu consumer cần tính toán.

## 7. Cấu hình ObjectMapper nhất quán

Một mapper cho model trên:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
```

Nếu ứng dụng có Spring Boot, hãy dùng mapper do application context quản lý và đăng ký module theo cơ chế cấu hình chung. Không tạo mapper riêng cho một controller nếu nó có feature khác với mapper được dùng ở nơi khác.

Sau khi mapper được sử dụng, tránh thay đổi cấu hình tùy tiện. Tạo mapper, đăng ký module và cấu hình feature trong startup; sau đó tái sử dụng thread-safe mapper.

Có thể tạo ObjectReader/ObjectWriter theo type hoặc feature riêng nếu endpoint có contract khác:

```java
ObjectWriter paymentWriter =
    mapper.writerFor(PaymentEvent.class);

ObjectReader paymentReader =
    mapper.readerFor(PaymentEvent.class);
```

Reader/writer giúp đóng gói kiểu đích và một số cấu hình cho boundary cụ thể. Chúng không thay thế việc xác định schema.

## 8. Custom serializer/deserializer chỉ khi hợp đồng cần

Nếu Money có wire format đặc biệt, có thể viết serializer/deserializer. Tuy nhiên, không nên tạo custom code khi BigDecimal và DTO đơn giản đã đáp ứng contract.

Ví dụ serializer Money thành object có amount và currency:

```java
public final class MoneySerializer
        extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider provider) throws IOException {

        generator.writeStartObject();
        generator.writeNumberField("amount", value.amount());
        generator.writeStringField(
            "currency",
            value.currency().getCurrencyCode()
        );
        generator.writeEndObject();
    }
}
```

Deserializer cần đọc đúng kiểu decimal, không chuyển qua double:

```java
public final class MoneyDeserializer
        extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode node = parser.getCodec().readTree(parser);

        BigDecimal amount = node.get("amount").decimalValue();
        Currency currency = Currency.getInstance(
            node.get("currency").textValue()
        );

        return new Money(amount, currency);
    }
}
```

Ví dụ này minh họa mapping cơ bản; code production cần kiểm tra field thiếu/null, node sai kiểu, precision, currency hợp lệ và exception message. Nếu cần hỗ trợ schema cũ, deserializer phải có policy rõ thay vì âm thầm đoán.

Với timestamp custom, tránh dùng timezone mặc định của JVM. Với ID custom, giữ chuỗi gốc và validate thay vì parse thành số nếu mã không có semantics số học.

## 9. Round-trip test cho toàn bộ DTO

Một test tổng hợp:

```java
class PaymentEventSerializationTest {

    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    @Test
    void preservesMoneyTimeAndIdentifiers() throws Exception {
        PaymentEvent original = new PaymentEvent(
            "pay-0001042",
            "cus-9007199254740993",
            new BigDecimal("1250.00"),
            "VND",
            Instant.parse("2026-11-12T03:30:00.123456789Z")
        );

        String json = mapper.writeValueAsString(original);
        PaymentEvent restored =
            mapper.readValue(json, PaymentEvent.class);

        assertEquals(original.paymentId(), restored.paymentId());
        assertEquals(original.customerId(), restored.customerId());
        assertEquals(0, original.amount().compareTo(restored.amount()));
        assertEquals(original.amount().scale(), restored.amount().scale());
        assertEquals(original.currency(), restored.currency());
        assertEquals(original.occurredAt(), restored.occurredAt());
    }
}
```

Test này kiểm tra:

- ID có số 0 đầu được giữ nguyên.
- ID lớn hơn giới hạn integer an toàn của JavaScript vẫn là string.
- BigDecimal giữ value và scale theo contract.
- Currency không bị bỏ.
- Instant giữ đúng nanosecond precision.

Nếu hợp đồng chỉ yêu cầu giữ giá trị tiền mà không yêu cầu scale, có thể bỏ assertion scale. Nếu timestamp chỉ giữ milliseconds, hãy chuẩn hóa expected đến milliseconds trước khi so sánh và ghi rõ giới hạn đó.

## 10. Kiểm thử lexical JSON và semantic value

Có hai loại kiểm thử khác nhau.

**Lexical/contract test** kiểm tra JSON có đúng kiểu và hình dạng đã công bố:

- paymentId là string.
- amount là number hoặc string theo contract.
- currency là string.
- occurredAt là ISO string hoặc timestamp số theo contract.
- Không xuất hiện field ngoài ý muốn.

**Semantic round-trip test** đọc JSON trở lại object và so sánh ý nghĩa:

- Decimal đúng giá trị/scale.
- Instant đúng thời điểm/precision.
- ID giữ nguyên ký tự.
- Currency giữ đúng mã.

Ví dụ kiểm tra tree:

```java
JsonNode tree = mapper.readTree(json);

assertTrue(tree.get("paymentId").isTextual());
assertTrue(tree.get("customerId").isTextual());
assertTrue(tree.get("amount").isNumber());
assertTrue(tree.get("currency").isTextual());
assertTrue(tree.get("occurredAt").isTextual());
```

Tree test xác nhận wire types. Nó không thay thế deserialize test. Một field có thể là string đúng kiểu nhưng chứa ID đã bị chuẩn hóa sai; semantic assertion mới phát hiện được điều đó.

## 11. Test dữ liệu biên và trường hợp lỗi

Không chỉ test một payment mẫu. Nên lưu fixture cho:

| Nhóm | Dữ liệu cần thử |
| --- | --- |
| Money | zero, âm, số lớn, scale 0/2/4, trailing zero, decimal exponent |
| Currency | mã hợp lệ, mã không hỗ trợ, thiếu currency |
| Instant | UTC, offset, fractional seconds, thời điểm trước epoch |
| LocalDate | cuối tháng, năm nhuận, ngày không hợp lệ |
| LocalDateTime | thiếu zone, zone ID sai, giờ ambiguous nếu có chuyển DST |
| ID | số 0 đầu, chữ hoa/thường, dấu gạch nối, Unicode nếu contract cho phép |
| Long ID | giá trị sát và vượt ±(2^53−1) |
| Missing/null | field thiếu, null tường minh, empty string |
| Invalid | number sai kiểu, timestamp sai format, ID rỗng |

Ví dụ test ID không được trim:

```java
@Test
void preservesIdentifierCharacters() throws Exception {
    IdentifierDto original = new IdentifierDto(" 000-A12 ");

    String json = mapper.writeValueAsString(original);
    IdentifierDto restored =
        mapper.readValue(json, IdentifierDto.class);

    assertEquals(original.id(), restored.id());
}
```

Nếu contract không cho phép whitespace đầu/cuối, test đúng phải xác nhận input bị từ chối hoặc được normalize theo quy tắc công khai. Không để serializer tự thay đổi ID.

## 12. Đừng nhầm null, zero và missing

Với tiền, các trạng thái sau có thể khác nhau:

```json
{}
```

```json
{
  "amount": null
}
```

```json
{
  "amount": 0
}
```

```json
{
  "amount": 0.00
}
```

- Missing có thể nghĩa là field chưa được cung cấp.
- Null có thể nghĩa là không xác định hoặc không áp dụng.
- Zero là giá trị tiền bằng không.
- 0.00 có thể mang scale 2 theo contract.

Với timestamp, missing khác null và khác epoch zero. Với ID, empty string không tương đương với null hoặc field bị thiếu.

Không dùng primitive long hoặc double nếu cần phân biệt missing/null với zero. Dùng wrapper type hoặc DTO có presence semantics phù hợp, rồi validate tại boundary.

## 13. Kiểm tra dữ liệu qua nhiều hệ thống

Một vòng Java-to-Java không đủ nếu JSON được tiêu thụ bởi JavaScript, Python, Go, database JSON column hoặc message broker.

Các consumer có thể khác nhau về:

- Precision của số.
- Kiểu integer/decimal.
- Timezone và timestamp parser.
- Cách xử lý fractional seconds.
- Chuẩn hóa UUID.
- String Unicode.
- Missing/null/default.
- Kiểu Map key.

Vì vậy, nếu API có nhiều consumer, hãy lưu contract fixture dùng chung hoặc tạo contract test ở mỗi client. Với JavaScript, test đặc biệt các ID lớn và decimal. Nếu dùng decimal library phía client, bảo đảm parser không chuyển qua Number trước khi tạo decimal object.

Với database, kiểm tra column type và precision/scale. Lưu BigDecimal vào column decimal phù hợp; nếu column là floating type, dữ liệu có thể mất precision trước khi Jackson đọc lại.

Với timestamp database, kiểm tra column type có timezone hay không và driver/JPA mapping có chuyển đổi theo session timezone không. Với ID, giữ column kiểu string/varchar nếu mã có lexical format hoặc số 0 đầu.

## 14. Migration khi hợp đồng hiện tại đã sai

Nếu API trước đây đã phát tiền dưới dạng double, timestamp không có timezone hoặc ID dưới dạng number lớn, thay đổi trực tiếp có thể làm client cũ lỗi.

Quy trình an toàn:

1. Ghi lại wire format cũ và các lỗi đã tồn tại.
2. Xác định dữ liệu nào đã được lưu hoặc consumer nào đang dùng.
3. Định nghĩa schema mới với decimal, timestamp và ID semantics rõ.
4. Tạo DTO/version mới hoặc endpoint version mới nếu wire type thay đổi.
5. Hỗ trợ đọc payload cũ trong giai đoạn chuyển tiếp.
6. Viết migration test bằng fixture lịch sử.
7. Cập nhật client và tài liệu contract.
8. Theo dõi consumer cũ trước khi ngừng phát format cũ.

Không đổi JSON number thành string, milliseconds thành ISO string hoặc Long thành String mà không xem đó là thay đổi hợp đồng. JsonAlias chỉ giải quyết tên property; nó không tự giải quyết đổi kiểu hoặc đổi semantics.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tổng tiền thành 0.30000000000000004 | Dùng double cho decimal | Dùng BigDecimal từ string hoặc JSON decimal |
| BigDecimal round-trip không bằng equals | Scale khác nhau | Xác định scale contract; dùng compareTo nếu chỉ cần numeric equality |
| Tiền mất currency | Chỉ serialize amount | Dùng Money gồm amount và currency |
| Decimal bị làm tròn ở client | Client parse JSON number thành binary Number | Dùng decimal parser hoặc string contract có version |
| Timestamp lệch nhiều giờ | LocalDateTime hoặc timezone mặc định | Dùng Instant/offset và contract timezone rõ |
| Timestamp mất phần lẻ giây | Database/client/parser giới hạn precision | Chốt precision và test end-to-end |
| Timestamp số bị hiểu sai | Không quy định seconds hay milliseconds | Công bố epoch unit hoặc dùng ISO string |
| ID mất số 0 đầu | Parse ID thành number | Dùng String/value object |
| ID lớn bị đổi ở JavaScript | Number vượt integer safe range | Gửi ID dưới dạng JSON string |
| UUID đổi format | Normalize không theo contract | Chốt canonical representation và test |
| Map key "0012" bị gộp với "12" | Parse key thành integer | Giữ key là String |
| Missing và null bị gộp | DTO/default/coercion không rõ | Test presence semantics và validate |
| Round-trip pass nhưng client vẫn sai | Chỉ test Java mapper | Contract test với wire type và consumer thực tế |

## 16. Quy trình thiết kế và kiểm thử

Khi xây dựng DTO JSON có tiền, thời điểm và ID:

1. Xác định semantics nghiệp vụ của từng field.
2. Chọn kiểu Java chính xác: BigDecimal, Instant/OffsetDateTime và String/value object cho ID.
3. Chốt JSON type cho từng field: number hay string.
4. Chốt currency, scale, rounding và decimal precision.
5. Chốt timestamp format, timezone/offset, epoch unit và fractional precision.
6. Chốt lexical form của ID, bao gồm số 0 đầu và case.
7. Cấu hình ObjectMapper cùng JavaTimeModule và date feature trong startup.
8. Dùng DTO/value object thay vì format hiển thị theo locale.
9. Viết round-trip test cho semantic values.
10. Viết contract test cho JSON token types và property names.
11. Lưu fixture cho giá trị biên, missing/null và invalid input.
12. Kiểm thử với consumer ngoài Java nếu API được chia sẻ.
13. Kiểm tra database column precision/scale, timezone và identifier type.
14. Version hóa nếu cần đổi wire type hoặc semantics.
15. Lưu lại contract và fixture để tránh regression trong lần nâng Jackson tiếp theo.

## 17. Bài thực hành tổng hợp

Tạo DTO:

```java
public record TransferEvent(
    String transferId,
    String sourceAccountId,
    String destinationAccountId,
    BigDecimal amount,
    String currency,
    Instant requestedAt
) {}
```

Dùng dữ liệu:

```java
TransferEvent original = new TransferEvent(
    "trf-000042",
    "000012345678",
    "9007199254740993",
    new BigDecimal("1250.0000"),
    "VND",
    Instant.parse("2026-11-12T03:30:00.123456789Z")
);
```

Thực hiện:

1. Cấu hình ObjectMapper với JavaTimeModule.
2. Tắt WRITE_DATES_AS_TIMESTAMPS nếu contract dùng ISO string.
3. Serialize TransferEvent thành JSON.
4. Kiểm tra ba ID đều là JSON string.
5. Kiểm tra amount là JSON number nếu contract chọn decimal number.
6. Kiểm tra currency là mã ISO.
7. Kiểm tra requestedAt là ISO UTC string có precision theo contract.
8. Deserialize JSON về TransferEvent.
9. So sánh ID bằng exact string equality.
10. So sánh BigDecimal bằng compareTo và kiểm tra scale riêng.
11. So sánh Instant chính xác đến nanoseconds.
12. Thử thay amount bằng số rất lớn và số có nhiều chữ số thập phân.
13. Thử amount null, missing, zero và 0.00.
14. Thử ID có số 0 đầu, khoảng trắng và dấu phân cách.
15. Thử ID lớn hơn 2^53−1 qua một client JavaScript.
16. Thử timestamp có offset +07:00 và xác nhận cùng instant.
17. Thử LocalDateTime không có zone và xác định policy.
18. Thử payload sai kiểu và xác nhận lỗi được báo rõ.
19. Lưu JSON fixture làm contract sample.
20. Chạy lại test sau khi thay đổi Jackson version hoặc DTO.

Bài thực hành hoàn thành khi dữ liệu sau vòng đọc ghi giữ đúng amount/currency/scale, đúng instant/precision và nguyên vẹn từng ký tự ID; đồng thời JSON phát ra đúng wire type mà consumer đã thống nhất.

## 18. Nguyên tắc ghi nhớ

- Jackson không thể phục hồi precision hoặc ký tự đã mất trước khi serialization.
- Dùng BigDecimal cho tiền; tạo từ string hoặc deserialize trực tiếp, tránh đi qua double.
- BigDecimal có value và scale; chọn compareTo hay equals theo contract.
- Tiền cần currency cùng amount; rounding là quyết định nghiệp vụ, không phải việc của serializer.
- JSON number và string là hai wire type khác nhau; chọn theo khả năng của consumer.
- Dùng Instant cho thời điểm tuyệt đối; OffsetDateTime khi cần giữ offset; LocalDateTime không tự xác định instant.
- Công bố timezone, epoch unit và precision phần giây.
- Dùng JavaTimeModule và cấu hình date serialization nhất quán.
- ID là mã, thường nên là String/value object; giữ số 0 đầu, case và dấu phân cách.
- ID lớn hơn giới hạn integer an toàn của JavaScript nên được truyền dưới dạng string.
- Không parse Map key dạng mã thành number nếu lexical form có ý nghĩa.
- Phân biệt missing, null, zero và empty.
- Kiểm tra cả semantic round-trip lẫn JSON contract/token type.
- Test với consumer ngoài Java và database thực tế khi dữ liệu đi qua nhiều hệ thống.
- Thay đổi wire type cần versioning/migration, không chỉ sửa annotation.
- Lưu fixture biên để phát hiện regression khi nâng Jackson hoặc thay DTO.

Bảo toàn dữ liệu qua vòng đọc ghi bắt đầu từ việc chọn đúng kiểu và định nghĩa đúng hợp đồng. Khi tiền giữ decimal chính xác cùng currency, thời điểm giữ đúng instant và precision, còn ID giữ nguyên chuỗi ký tự, Jackson có thể thực hiện vai trò của nó một cách nhất quán: chuyển dữ liệu giữa Java và JSON mà không làm thay đổi ý nghĩa nghiệp vụ.
