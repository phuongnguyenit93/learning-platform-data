# Ánh xạ enum, ngày giờ, tiền tệ và kiểu giá trị tùy chỉnh

Spring Data REST nhận và trả JSON thông qua cơ chế HTTP message conversion của Spring MVC, thường dùng Jackson để chuyển đổi giữa JSON và Java object. Các kiểu đơn giản như String hoặc Boolean thường ánh xạ trực tiếp; enum, ngày giờ, tiền tệ và value object cần một hợp đồng biểu diễn rõ ràng để client và server hiểu cùng một ý nghĩa.

Thiết kế mapping nên trả lời ba câu hỏi: JSON có hình dạng nào, Java biểu diễn giá trị ra sao và quy tắc hợp lệ được kiểm tra ở đâu. Serializer/deserializer quyết định cách chuyển đổi; validation quyết định giá trị có được chấp nhận; persistence mapping quyết định cách lưu xuống database. Đây là các trách nhiệm liên quan nhưng không thay thế nhau.

## 1. Jackson nằm ở đâu trong luồng Spring Data REST?

Ở chiều request, Spring MVC chọn một `HttpMessageConverter` dựa trên media type và kiểu tham số của endpoint. Với JSON, converter thường dùng Jackson để deserialize request body thành entity hoặc object đầu vào. Spring Data REST tiếp tục xử lý repository, validation và lifecycle events.

Ở chiều response, Spring Data REST tạo representation của tài nguyên, bao gồm các thuộc tính và hypermedia links. Jackson serialize representation thành JSON để gửi về client.

```text
Request JSON
    |
    v
HttpMessageConverter + Jackson
    |
    v
Java object / entity
    |
    v
Spring Data REST + repository
    |
    v
Resource representation + HAL links
    |
    v
Jackson + HttpMessageConverter
    |
    v
Response JSON
```

Jackson annotations, custom serializers, deserializers và modules có thể điều chỉnh việc chuyển đổi ở hai chiều. Cấu hình thực tế phụ thuộc phiên bản Spring Boot, Spring Data REST và ObjectMapper mà ứng dụng sử dụng. Khi tùy chỉnh ObjectMapper, cần bảo đảm cấu hình đó áp dụng cho converter đang phục vụ Spring Data REST, không chỉ cho một ObjectMapper tự tạo trong một service khác.

## 2. Ánh xạ enum

Enum thường biểu diễn một tập giá trị hữu hạn, ví dụ trạng thái đơn hàng:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Với cấu hình Jackson thông dụng, enum được biểu diễn bằng tên hằng dưới dạng JSON string:

```json
{
  "status": "PAID"
}
```

Khi nhận JSON, Jackson chuyển chuỗi tương ứng thành enum constant. Giá trị không khớp với enum có thể gây lỗi deserialize trước khi repository thực hiện thao tác.

Nên dùng tên enum như một phần của API contract một cách có chủ đích. Đổi tên hằng Java có thể làm client cũ gửi giá trị không còn được nhận. Nếu tên nội bộ cần thay đổi mà API phải giữ ổn định, có thể định nghĩa giá trị JSON riêng.

### Dùng @JsonValue và @JsonCreator

`@JsonValue` chỉ ra giá trị được dùng khi serialize enum. `@JsonCreator` xác định cách chuyển JSON value trở lại enum:

```java
public enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    SHIPPED("shipped"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unknown order status: " + code
        );
    }
}
```

JSON lúc này dùng mã ổn định, chẳng hạn `"paid"`, dù tên hằng Java là `PAID`. Nếu muốn chấp nhận chữ hoa/chữ thường khác nhau, hãy định nghĩa quy tắc chuẩn hóa rõ ràng trong factory method; đừng để client phải đoán.

Không nên serialize enum thành ordinal như `0`, `1`, `2`. Thứ tự hằng có thể thay đổi khi thêm hoặc sắp xếp lại enum, làm client hiểu sai dữ liệu. Nếu dùng JPA, `@Enumerated(EnumType.STRING)` cũng thường an toàn hơn `ORDINAL` cho persistence, nhưng đây là cấu hình lưu database độc lập với JSON mapping.

## 3. Ánh xạ ngày và giờ

Các kiểu ngày giờ Java không mang cùng một ý nghĩa. Chọn đúng kiểu trước khi quyết định JSON format:

| Java type | Ý nghĩa | JSON thường dùng |
|---|---|---|
| `LocalDate` | Một ngày lịch, không có giờ hoặc múi giờ | `"2026-11-11"` |
| `LocalTime` | Giờ trong ngày, không có ngày hoặc múi giờ | `"09:30:00"` |
| `LocalDateTime` | Ngày và giờ địa phương, không có offset/múi giờ | `"2026-11-11T09:30:00"` |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | `"2026-11-11T09:30:00+07:00"` |
| `Instant` | Một thời điểm tuyệt đối trên timeline | `"2026-11-11T02:30:00Z"` |
| `ZonedDateTime` | Ngày giờ cùng zone ID, ví dụ `Asia/Ho_Chi_Minh` | Thường cần thống nhất format/zone policy |

Dùng `LocalDate` cho ngày sinh hoặc ngày hiệu lực nếu chỉ quan tâm ngày lịch. Dùng `Instant` cho thời điểm sự kiện cần so sánh nhất quán giữa các hệ thống. Dùng `OffsetDateTime` khi API cần giữ offset được gửi lên. `LocalDateTime` không đủ thông tin để xác định một thời điểm duy nhất nếu client và server ở các múi giờ khác nhau.

Với ứng dụng Spring Boot hiện đại, Jackson thường được cấu hình để hỗ trợ Java Time qua `JavaTimeModule`. Nếu ứng dụng tự tạo ObjectMapper hoặc dùng cấu hình tùy chỉnh, cần xác nhận module đã được đăng ký.

### Dùng ISO-8601 làm format trao đổi

Ví dụ entity:

```java
@Entity
public class Appointment {

    private LocalDate appointmentDate;

    private Instant createdAt;

    private OffsetDateTime startsAt;

    // getters and setters
}
```

JSON tương ứng có thể là:

```json
{
  "appointmentDate": "2026-11-11",
  "createdAt": "2026-11-11T02:30:00Z",
  "startsAt": "2026-11-11T09:30:00+07:00"
}
```

ISO-8601 giúp thể hiện rõ thành phần ngày, giờ và offset. Với `Instant`, giá trị thường được biểu diễn ở UTC bằng hậu tố `Z`. Với `OffsetDateTime`, offset được giữ trong chuỗi.

Nếu cần format riêng, có thể dùng `@JsonFormat`:

```java
public class Person {

    @JsonFormat(shape = JsonFormat.Shape.STRING,
                pattern = "yyyy-MM-dd")
    private LocalDate birthDate;
}
```

Pattern phải phù hợp với Java type và hợp đồng API. Không nên dùng format chỉ có ngày giờ mà bỏ offset cho một sự kiện cần xác định thời điểm tuyệt đối.

### Múi giờ và daylight saving time

Một chuỗi `"2026-11-11T09:30:00"` không nói rõ đó là 09:30 ở múi giờ nào. Nếu server diễn giải theo timezone mặc định của máy, cùng payload có thể thành thời điểm khác khi triển khai ở môi trường khác.

Với lịch hẹn, có thể cần lưu cả giờ địa phương và zone ID để xử lý quy tắc múi giờ. Với timestamp của sự kiện đã xảy ra, `Instant` thường phù hợp hơn. Hãy xác định rõ server chuẩn hóa về UTC hay giữ offset ban đầu, và áp dụng nhất quán ở API, database và client.

## 4. Ánh xạ tiền tệ và độ chính xác

Không dùng `float` hoặc `double` cho số tiền cần tính toán chính xác. Các kiểu dấu phẩy động nhị phân có thể không biểu diễn chính xác nhiều giá trị thập phân. Trong Java, `BigDecimal` phù hợp hơn cho amount.

Một giá trị tiền tệ cần cả số tiền và đơn vị tiền tệ. Chỉ gửi `100.00` là chưa đủ nếu client không biết đó là VND, USD hay EUR.

Một value object đơn giản:

```java
public record Money(
    BigDecimal amount,
    String currency
) {}
```

JSON có thể biểu diễn như sau:

```json
{
  "amount": 125000.00,
  "currency": "VND"
}
```

Dùng mã tiền tệ ISO 4217, chẳng hạn `VND`, `USD` hoặc `EUR`, thay vì ký hiệu hiển thị như `$` hoặc `đ`. Ký hiệu có thể mơ hồ hoặc phụ thuộc locale.

### Scale và rounding

`BigDecimal` giữ độ chính xác thập phân, nhưng nghiệp vụ vẫn phải xác định scale và rounding policy. Ví dụ:

```java
BigDecimal tax = amount
    .multiply(new BigDecimal("0.10"))
    .setScale(2, RoundingMode.HALF_UP);
```

Không nên tạo BigDecimal từ literal double như `new BigDecimal(0.1)`, vì giá trị double đã có sai số nhị phân. Dùng chuỗi thập phân hoặc `BigDecimal.valueOf(...)` khi đầu vào phù hợp.

Số chữ số thập phân hợp lệ phụ thuộc currency và quy tắc nghiệp vụ. Không mặc định mọi currency đều có hai chữ số thập phân. Với VND, hệ thống thường dùng đơn vị đồng nguyên; một số currency khác có quy tắc fraction digits khác nhau. Hãy xác định rounding ở domain/service layer và validate amount ở ranh giới request.

JSON number có thể được một số client JavaScript chuyển thành kiểu Number với giới hạn chính xác. Nếu amount rất lớn hoặc client cần bảo toàn toàn bộ decimal precision, API có thể chọn biểu diễn amount dưới dạng string thập phân và tài liệu hóa rõ contract:

```json
{
  "amount": "125000.00",
  "currency": "VND"
}
```

Không trộn hai kiểu biểu diễn number và string cho cùng một field giữa các endpoint nếu không có lý do tương thích được tài liệu hóa.

## 5. Kiểu giá trị tùy chỉnh (custom value types)

Domain model thường có các kiểu bao bọc một giá trị đơn nhưng mang ý nghĩa riêng, ví dụ `EmailAddress`, `PhoneNumber`, `ProductCode` hoặc `Money`. Dùng value type giúp domain thể hiện ý nghĩa và gom validation vào đúng chỗ.

Ví dụ:

```java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email address"
            );
        }
    }
}
```

Nếu muốn JSON biểu diễn trực tiếp bằng string thay vì object lồng:

```json
{
  "email": "an@example.test"
}
```

Có thể dùng `@JsonValue` và `@JsonCreator`:

```java
public record EmailAddress(String value) {

    @JsonValue
    public String jsonValue() {
        return value;
    }

    @JsonCreator
    public static EmailAddress fromJson(String value) {
        return new EmailAddress(value);
    }
}
```

Jackson serialize object thành JSON string và gọi factory method khi deserialize. Constructor/factory có thể từ chối dữ liệu không hợp lệ; ứng dụng nên ánh xạ lỗi này thành response client phù hợp thay vì để lộ stack trace.

Cách này thích hợp cho kiểu có cấu trúc JSON đơn giản. Với kiểu phức tạp hơn, cần nhiều field hoặc có format đặc biệt, custom serializer/deserializer thường dễ kiểm soát hơn.

## 6. Viết custom serializer và deserializer

Khi JSON contract khác với cách Jackson mặc định biểu diễn Java type, có thể tạo serializer và deserializer.

Ví dụ custom type `Money` được biểu diễn thành object có amount và currency. Serializer:

```java
public class MoneySerializer
        extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money money,
            JsonGenerator generator,
            SerializerProvider serializers)
            throws IOException {

        generator.writeStartObject();
        generator.writeNumberField(
            "amount",
            money.amount()
        );
        generator.writeStringField(
            "currency",
            money.currency()
        );
        generator.writeEndObject();
    }
}
```

Deserializer:

```java
public class MoneyDeserializer
        extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context)
            throws IOException {

        JsonNode node = parser.getCodec()
            .readTree(parser);

        JsonNode amountNode = node.get("amount");
        JsonNode currencyNode = node.get("currency");

        if (amountNode == null || currencyNode == null) {
            throw JsonMappingException.from(
                parser,
                "Money requires amount and currency"
            );
        }

        BigDecimal amount = amountNode.decimalValue();
        String currency = currencyNode.asText();

        return new Money(amount, currency);
    }
}
```

Có thể gắn trực tiếp vào type:

```java
@JsonSerialize(using = MoneySerializer.class)
@JsonDeserialize(using = MoneyDeserializer.class)
public record Money(
    BigDecimal amount,
    String currency
) {}
```

Hoặc đăng ký qua Jackson module nếu muốn tách cấu hình khỏi domain class. Ví dụ với Spring Boot:

```java
@Bean
Module moneyModule() {
    SimpleModule module = new SimpleModule("money-module");
    module.addSerializer(Money.class, new MoneySerializer());
    module.addDeserializer(Money.class, new MoneyDeserializer());
    return module;
}
```

Spring Boot thường tự đăng ký các bean Jackson `Module` vào ObjectMapper được auto-configure. Nếu ứng dụng tùy chỉnh ObjectMapper hoặc Spring Data REST dùng converter riêng, hãy kiểm tra module đã được áp dụng đúng converter. Tránh tạo ObjectMapper mới trong từng controller vì cấu hình đó có thể khác cấu hình của REST API.

Serializer/deserializer chỉ chuyển đổi representation. Chúng không tự bảo đảm currency code hợp lệ, amount không âm hay scale đúng nghiệp vụ. Những điều kiện đó vẫn cần được kiểm tra trong constructor/value object, Bean Validation hoặc domain service.

## 7. Phân biệt JSON mapping với persistence mapping

Một kiểu Java có thể được biểu diễn khác nhau ở JSON và database:

| Lớp | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| JSON request/response | Client gửi và nhận hình dạng nào? | Jackson annotations, serializers, deserializers, modules |
| Domain model | Giá trị có hợp lệ và mang đúng ý nghĩa không? | Constructor, value object, Bean Validation, domain logic |
| Database | Giá trị được lưu trong cột nào và theo dạng nào? | JPA mapping, `AttributeConverter`, column definition |
| HTTP | Media type nào được chấp nhận/trả về? | `HttpMessageConverter`, Spring MVC content negotiation |

Ví dụ `OrderStatus` có thể được lưu trong database bằng `@Enumerated(EnumType.STRING)` và đồng thời serialize thành mã `"paid"` qua `@JsonValue`. Hai biểu diễn này độc lập: một bên phục vụ persistence, bên kia phục vụ API contract.

Tương tự, `Money` có thể được serialize thành object JSON nhưng lưu bằng hai cột `amount` và `currency`. Nếu dùng JPA `AttributeConverter`, converter đó không tự thay đổi JSON representation của Jackson.

Không dùng Jackson serializer để giải quyết cách lưu database; cũng không mong đợi JPA converter thay đổi request body mà client gửi.

## 8. Lỗi mapping và validation

Các lỗi thường xuất hiện ở những giai đoạn khác nhau:

| Tình huống | Giai đoạn | Hướng xử lý |
|---|---|---|
| Enum code không được nhận diện | Deserialize request | Công bố tập giá trị hợp lệ và xử lý mã không biết |
| Ngày giờ sai format | Deserialize request | Thống nhất ISO-8601 hoặc `@JsonFormat` |
| Timestamp thiếu offset khi cần thời điểm tuyệt đối | Contract/domain semantics | Dùng `Instant` hoặc `OffsetDateTime` phù hợp |
| Amount không phải decimal hợp lệ | Deserialize/validation | Dùng `BigDecimal`, kiểm tra scale và range |
| Currency code không hợp lệ | Domain validation | Kiểm tra theo danh sách currency được hỗ trợ |
| Custom value object thiếu field | Custom deserializer | Trả lỗi mapping có thông tin rõ ràng |
| JSON hợp lệ nhưng vi phạm nghiệp vụ | Bean Validation/domain layer | Trả lỗi validation trước khi lưu |

Lỗi parse hoặc deserialize thường xảy ra trước repository lifecycle. Lỗi validation xảy ra sau khi object đã được tạo nhưng không thỏa quy tắc. Lỗi database constraint có thể chỉ xuất hiện khi ghi. Phân biệt các giai đoạn giúp client hiểu nên sửa payload, giá trị hay trạng thái nghiệp vụ.

Không đưa thông tin nhạy cảm hoặc stack trace nội bộ vào response. Có thể trả mã lỗi ổn định, tên field và mô tả ngắn để client sửa dữ liệu.

## 9. Kiểm thử mapping hai chiều

Mỗi custom mapping nên có kiểm thử serialize và deserialize. Ví dụ:

```java
@Test
void moneyRoundTripsAsJson() throws Exception {
    Money original = new Money(
        new BigDecimal("125000.00"),
        "VND"
    );

    String json = objectMapper.writeValueAsString(original);

    Money restored = objectMapper.readValue(
        json,
        Money.class
    );

    assertEquals(original, restored);
}
```

Nên kiểm tra thêm:

- Enum hợp lệ, enum không biết và quy tắc chữ hoa/chữ thường.
- `LocalDate`, `Instant` và `OffsetDateTime` ở các giá trị biên.
- Timestamp có offset khác nhau nhưng biểu diễn cùng một instant.
- Amount có scale, precision lớn và rounding.
- Currency không được hỗ trợ.
- Custom type thiếu field hoặc chứa giá trị không hợp lệ.
- Response thực tế của Spring Data REST, không chỉ ObjectMapper được tạo riêng trong unit test.

Kiểm thử ở tầng web/repository giúp xác nhận đúng ObjectMapper và HttpMessageConverter đang được endpoint sử dụng. Điều này đặc biệt quan trọng khi ứng dụng có nhiều converter hoặc cấu hình Jackson tùy chỉnh.

## 10. Checklist thiết kế JSON contract

1. Chọn JSON representation ổn định cho enum; ưu tiên string code có ý nghĩa thay vì ordinal.
2. Dùng Java Time type theo đúng semantics: `LocalDate` cho ngày lịch, `Instant` cho thời điểm tuyệt đối, `OffsetDateTime` khi cần giữ offset.
3. Thống nhất timezone và format, ưu tiên ISO-8601 cho trao đổi ngày giờ.
4. Dùng `BigDecimal` cho amount và gửi currency code cùng số tiền.
5. Định nghĩa rõ precision, scale và rounding policy trong domain.
6. Dùng value object cho các giá trị có ý nghĩa nghiệp vụ riêng; chọn `@JsonCreator`/`@JsonValue` hoặc custom serializer/deserializer theo độ phức tạp.
7. Đăng ký Jackson module vào đúng ObjectMapper phục vụ Spring Data REST.
8. Tách JSON mapping khỏi JPA persistence mapping và validation nghiệp vụ.
9. Kiểm thử round-trip và request/response thực tế qua endpoint.

Khi enum, ngày giờ, tiền tệ và custom value type có JSON contract rõ ràng, client và Spring Data REST có thể trao đổi dữ liệu nhất quán. Jackson đảm nhiệm chuyển đổi representation, domain model bảo vệ ý nghĩa và tính hợp lệ của giá trị, còn JPA đảm nhiệm cách lưu trữ. Phân định đúng ba lớp giúp thay đổi format API có kiểm soát mà không làm lẫn logic nghiệp vụ với chi tiết serialization.
