# Ngày giờ và số thập phân

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua hợp đồng sự kiện. Khi event được externalize sang broker hoặc hệ thống khác, dữ liệu phải đi qua một ranh giới serialization. Hai nhóm giá trị thường gây sai lệch nhất là ngày giờ và số thập phân: thời điểm có thể đổi do timezone hoặc mất độ chính xác, còn số tiền có thể bị làm tròn khi một consumer chuyển JSON number sang kiểu floating point.

Một hợp đồng event đáng tin cậy phải mô tả rõ kiểu dữ liệu, định dạng, timezone, độ chính xác và quy tắc làm tròn. Producer và consumer cần hiểu cùng một ý nghĩa cho mỗi trường, kể cả khi chúng được viết bằng ngôn ngữ hoặc nền tảng khác nhau.

## 1. Serialization là một phần của event contract

Serialization chuyển object trong ứng dụng thành biểu diễn có thể truyền qua transport, thường là JSON. Consumer deserialize biểu diễn đó thành kiểu dữ liệu mà nó sử dụng. Ví dụ event nghiệp vụ:

~~~java
public record PaymentCaptured(
    UUID eventId,
    Instant occurredAt,
    BigDecimal amount,
    String currencyCode
) {}
~~~

Các kiểu Java trong object không tự động bảo đảm consumer bên ngoài hiểu đúng ý nghĩa. Contract phải chỉ rõ:

- **eventId** là định danh ổn định của cùng một sự kiện qua mọi lần retry.
- **occurredAt** là thời điểm tuyệt đối, được biểu diễn theo UTC.
- **amount** là số thập phân chính xác, có quy tắc về scale và rounding.
- **currencyCode** là mã tiền tệ theo một quy ước được thống nhất, ví dụ ISO 4217.

Ví dụ JSON minh họa contract dùng timestamp ISO-8601 và amount dưới dạng chuỗi thập phân:

~~~json
{
  "eventId": "7f90c6e0-5e1f-4c8c-9a72-2df2c7d74e2a",
  "occurredAt": "2026-11-25T13:30:45.123Z",
  "amount": "1234.50",
  "currencyCode": "USD"
}
~~~

Trong ví dụ này, **amount** là JSON string để giữ nguyên biểu diễn thập phân và scale. Một contract khác có thể dùng JSON number hoặc số nguyên theo minor unit, nhưng phải công bố lựa chọn đó và yêu cầu consumer xử lý chính xác.

Với Spring Modulith, annotation **@Externalized** đánh dấu event cần được externalize và cung cấp target logic. Việc chuyển object thành JSON hoặc định dạng khác thuộc integration/transport được ứng dụng sử dụng. Vì vậy, hãy kiểm tra serializer thực tế được outbound adapter dùng; cấu hình một ObjectMapper không có tác dụng nếu adapter đang dùng mapper khác.

## 2. Biểu diễn ngày giờ đúng ý nghĩa

Java cung cấp nhiều kiểu ngày giờ trong java.time. Chọn kiểu theo ý nghĩa nghiệp vụ, không chỉ theo định dạng mong muốn:

| Kiểu Java | Ý nghĩa | Trường hợp phù hợp |
|---|---|---|
| **Instant** | Một thời điểm tuyệt đối trên timeline UTC | Thời điểm event xảy ra, thanh toán được ghi nhận, trạng thái được cập nhật |
| **OffsetDateTime** | Ngày giờ kèm UTC offset | Cần giữ offset mà nguồn gửi đã cung cấp |
| **ZonedDateTime** | Ngày giờ gắn với timezone và quy tắc vùng | Lập lịch theo vùng như **Asia/Ho_Chi_Minh** |
| **LocalDate** | Một ngày lịch, không có giờ hoặc timezone | Ngày sinh, ngày hóa đơn, ngày hiệu lực |
| **LocalDateTime** | Ngày và giờ địa phương, không có offset | Giờ mở cửa hoặc thời gian địa phương chưa gắn với timezone |
| **Duration** | Khoảng thời gian | Thời lượng xử lý hoặc thời gian chờ |

Với event ghi nhận một việc đã xảy ra, thường nên dùng **Instant**. **LocalDateTime** không xác định được một thời điểm duy nhất: cùng giá trị 2026-11-25T09:00:00 có thể chỉ các thời điểm khác nhau ở những timezone khác nhau.

Nếu nghiệp vụ cần lưu giờ địa phương, ví dụ lịch hẹn tại một chi nhánh, hãy gửi cả ngày giờ và timezone ID. Offset như +07:00 chỉ cho biết độ lệch tại thời điểm đó; timezone ID như **Asia/Ho_Chi_Minh** còn mang quy tắc lịch sử và thay đổi giờ theo vùng. Với ngày lịch như ngày đáo hạn, dùng **LocalDate** và không tự thêm Z hoặc timezone.

### Dùng ISO-8601 và UTC cho thời điểm event

Một **Instant** có thể được biểu diễn bằng chuỗi ISO-8601 có hậu tố Z:

~~~java
Instant occurredAt = Instant.now();

String serialized = DateTimeFormatter.ISO_INSTANT.format(occurredAt);
// Ví dụ: 2026-11-25T13:30:45.123Z
~~~

Consumer có thể parse lại:

~~~java
Instant occurredAt = Instant.parse("2026-11-25T13:30:45.123Z");
~~~

Không nên serialize thời điểm event thành chuỗi phụ thuộc locale như 25/11/2026 20:30. Consumer ở locale khác có thể diễn giải khác hoặc không parse được. Cũng không nên bỏ offset rồi mong consumer tự đoán timezone.

Nếu contract dùng epoch timestamp, phải quy định đơn vị là giây, mili giây hay micro giây. Một số hệ thống dùng epoch seconds dạng số nguyên, một số API lại dùng milliseconds. Cùng một con số nhưng khác đơn vị có thể tạo ra thời điểm lệch hàng nghìn lần. ISO-8601 thường dễ đọc và ít mơ hồ hơn đối với event contract.

### Cấu hình Jackson

Với Jackson, hỗ trợ kiểu java.time thường được cung cấp bởi module Java Time. Spring Boot thường tự cấu hình mapper và module tương ứng khi có dependency phù hợp. Cấu hình thường dùng để serialize ngày giờ thành chuỗi thay vì timestamp dạng số:

~~~yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
    time-zone: UTC
~~~

Cấu hình trên áp dụng cho Jackson mapper được Spring Boot quản lý. Nếu externalization adapter dùng serializer riêng, hãy cấu hình mapper của adapter theo cùng contract. Không tạo mapper mới tùy tiện trong từng listener vì các mapper khác nhau có thể sinh payload khác nhau.

Khi cần cấu hình thủ công trong một ứng dụng không dùng auto-configuration, có thể đăng ký **JavaTimeModule**:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Đây là ví dụ cấu hình mapper. Trong ứng dụng Spring Boot, ưu tiên sử dụng bean ObjectMapper đã được cấu hình chung và inject vào integration thay vì tự tạo thêm một mapper không đồng nhất.

## 3. Quy định độ chính xác của timestamp

**Instant** trong Java hỗ trợ độ chính xác tới nanosecond, nhưng không phải hệ thống nào cũng giữ được độ chính xác đó. Database column, broker, serializer hoặc consumer có thể chỉ lưu milliseconds hoặc microseconds. Nếu producer gửi nanoseconds mà consumer chỉ lưu milliseconds, phần lẻ sẽ bị cắt hoặc làm tròn.

Ví dụ:

| Giá trị nguồn | Độ chính xác |
|---|---|
| **2026-11-25T13:30:45Z** | Giây |
| **2026-11-25T13:30:45.123Z** | Mili giây |
| **2026-11-25T13:30:45.123456Z** | Micro giây |
| **2026-11-25T13:30:45.123456789Z** | Nano giây |

Contract cần chốt độ chính xác tối đa và hành vi khi một thành phần không hỗ trợ độ chính xác đó. Nếu hệ thống chỉ cần milliseconds, có thể chuẩn hóa trước khi tạo payload:

~~~java
Instant normalized = occurredAt.truncatedTo(ChronoUnit.MILLIS);
~~~

Không chuẩn hóa tùy tiện nếu nghiệp vụ cần thứ tự hoặc độ chính xác cao hơn. Khi cần thứ tự event, timestamp không nên là cơ chế duy nhất: hai event có thể có cùng timestamp hoặc đồng hồ giữa các instance có thể lệch. Dùng sequence/version theo aggregate hoặc một cơ chế ordering riêng nếu nghiệp vụ yêu cầu.

## 4. Vì sao nên dùng BigDecimal cho số thập phân

**double** và **float** dùng biểu diễn nhị phân dấu phẩy động. Nhiều số thập phân thông thường không thể biểu diễn chính xác bằng dạng nhị phân hữu hạn. Ví dụ:

~~~java
System.out.println(0.1 + 0.2);
// Có thể in ra 0.30000000000000004
~~~

Với tiền tệ, thuế, tỷ lệ hoặc số lượng cần độ chính xác thập phân, nên dùng **BigDecimal**:

~~~java
BigDecimal first = new BigDecimal("0.1");
BigDecimal second = new BigDecimal("0.2");

BigDecimal total = first.add(second);
// 0.3
~~~

Tạo **BigDecimal** từ chuỗi thập phân hoặc từ nguồn decimal chính xác. Tránh **new BigDecimal(0.1)** vì giá trị double đã bị xấp xỉ trước khi được chuyển thành BigDecimal.

~~~java
BigDecimal amount = new BigDecimal("1234.50");
~~~

**BigDecimal** giữ giá trị thập phân cùng scale. 1234.50 và 1234.5 có cùng giá trị số học nhưng scale khác nhau. Một số contract cần giữ scale để biểu thị số chữ số thập phân có ý nghĩa; contract khác chỉ quan tâm giá trị. Hãy quyết định rõ có chuẩn hóa scale hay không.

## 5. Chọn cách serialize decimal

JSON có kiểu number nhưng không quy định consumer phải dùng kiểu số thập phân chính xác. Một consumer JavaScript có thể parse JSON number thành IEEE-754 Number; với số lớn hoặc nhiều chữ số có nghĩa, giá trị có thể bị làm tròn.

Có ba cách biểu diễn thường gặp:

| Cách biểu diễn | Ví dụ | Ưu điểm và giới hạn |
|---|---|---|
| JSON number | **"amount": 1234.50** | Tự nhiên với JSON; consumer phải dùng decimal type chính xác, không parse qua floating point |
| JSON string | **"amount": "1234.50"** | Giữ chính xác chữ số và scale; consumer phải parse theo contract |
| Integer minor unit | **"amountMinor": 123450** | Dễ biểu diễn chính xác bằng integer; cần định nghĩa exponent của currency và giới hạn số nguyên |

Với dữ liệu tài chính đi qua nhiều ngôn ngữ, biểu diễn decimal dạng string thường là lựa chọn rõ ràng. Nếu chọn JSON number, yêu cầu consumer dùng kiểu decimal chính xác như **BigDecimal** hoặc decimal library tương ứng. Không để một phía hiểu là decimal còn phía kia tự động chuyển thành double.

### Serialize BigDecimal thành JSON string

Có thể khai báo rõ cách biểu diễn trên field bằng Jackson:

~~~java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;

public record PaymentCaptured(
    UUID eventId,
    Instant occurredAt,
    @JsonSerialize(using = ToStringSerializer.class)
    BigDecimal amount,
    String currencyCode
) {}
~~~

Với serializer này, **BigDecimal("1234.50")** được ghi thành chuỗi "1234.50" trong JSON. Hãy xác nhận serializer được dùng bởi externalization adapter và test payload thực tế, vì annotation chỉ có tác dụng nếu adapter serialize object bằng Jackson có hỗ trợ annotation đó.

Nếu dùng DTO riêng cho external contract, có thể chuyển đổi rõ ràng:

~~~java
public record PaymentCapturedPayload(
    String eventId,
    String occurredAt,
    String amount,
    String currencyCode
) {
    static PaymentCapturedPayload from(PaymentCaptured event) {
        return new PaymentCapturedPayload(
            event.eventId().toString(),
            DateTimeFormatter.ISO_INSTANT.format(event.occurredAt()),
            event.amount().toPlainString(),
            event.currencyCode()
        );
    }
}
~~~

**toPlainString()** tạo biểu diễn thập phân không dùng exponent notation. Điều này hữu ích khi contract muốn chuỗi như 0.000001 thay vì 1E-6. Không dùng **stripTrailingZeros()** nếu scale có ý nghĩa đối với nghiệp vụ hoặc hợp đồng.

## 6. Scale, rounding và currency

Không phải mọi phép tính đều cho kết quả có scale đúng theo nghiệp vụ. Chia hai **BigDecimal** có thể tạo ra số thập phân vô hạn, vì vậy phải chỉ rõ scale và rounding mode:

~~~java
BigDecimal taxRate = new BigDecimal("0.10");
BigDecimal subtotal = new BigDecimal("19.99");

BigDecimal tax = subtotal
    .multiply(taxRate)
    .setScale(2, RoundingMode.HALF_UP);
~~~

Chọn rounding mode theo quy tắc nghiệp vụ hoặc quy định kế toán. **HALF_UP**, **HALF_EVEN**, **DOWN** và **CEILING** có ý nghĩa khác nhau; không nên để mỗi module tự chọn một cách làm tròn.

Currency cũng ảnh hưởng tới scale. Không nên mặc định mọi currency đều có hai chữ số thập phân. Ví dụ, có currency thường được biểu diễn với 0, 2 hoặc 3 chữ số thập phân. Nếu dùng integer minor unit, contract phải xác định exponent theo currency. Nếu dùng decimal string, contract vẫn nên quy định scale hợp lệ hoặc cách xử lý số chữ số thập phân vượt quá quy tắc tiền tệ.

Nên truyền amount và currency thành hai trường độc lập:

~~~json
{
  "amount": "1234.50",
  "currencyCode": "USD"
}
~~~

Không gửi chuỗi định dạng theo locale như 1.234,50 € hoặc USD 1,234.50 trong trường amount. Dấu phân cách hàng nghìn, dấu thập phân và ký hiệu tiền tệ thay đổi theo locale. Consumer cần parse giá trị máy đọc được rồi tự định dạng cho giao diện.

## 7. Một event contract hoàn chỉnh

Ví dụ sau kết hợp thời điểm UTC và decimal string:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
import org.springframework.modulith.events.Externalized;

@Externalized("billing.payment-captured.v1")
public record PaymentCaptured(
    UUID eventId,
    UUID paymentId,
    Instant occurredAt,
    @JsonSerialize(using = ToStringSerializer.class)
    BigDecimal amount,
    String currencyCode
) {}
~~~

Payload JSON tương ứng:

~~~json
{
  "eventId": "7f90c6e0-5e1f-4c8c-9a72-2df2c7d74e2a",
  "paymentId": "d78e11d9-bae8-42bb-a1a5-9d2e0c2dbdd8",
  "occurredAt": "2026-11-25T13:30:45.123Z",
  "amount": "1234.50",
  "currencyCode": "USD"
}
~~~

Hợp đồng này xác định event ID, thời điểm tuyệt đối, decimal string và mã tiền tệ. Khi thay đổi format, chẳng hạn chuyển amount từ string sang JSON number hoặc đổi timestamp từ ISO-8601 sang epoch milliseconds, đó là thay đổi contract cần được version hóa hoặc triển khai theo chiến lược tương thích.

## 8. Schema evolution và tương thích consumer

Một event có thể được nhiều module hoặc hệ thống bên ngoài sử dụng. Khi thay đổi kiểu hoặc định dạng trường, producer cần xem xét các consumer đang triển khai phiên bản cũ.

Một số nguyên tắc:

- Thêm trường mới chỉ khi consumer cũ có thể bỏ qua trường chưa biết hoặc schema cho phép trường tùy chọn.
- Không đổi **occurredAt** từ ISO-8601 sang epoch mà không version hóa contract.
- Không đổi **amount** từ string sang number trong cùng version nếu consumer đã dựa vào kiểu string.
- Không đổi scale hoặc rounding semantics mà không thông báo rõ.
- Không tái sử dụng tên trường cũ cho ý nghĩa khác.
- Duy trì event ID ổn định khi retry hoặc replay.

Nếu cần thay đổi không tương thích, tạo version mới của contract hoặc target, chẳng hạn **billing.payment-captured.v2**. Consumer mới có thể được triển khai trước, producer chuyển dần theo kế hoạch, sau đó mới ngừng version cũ khi backlog và consumer cũ đã được xử lý.

## 9. Kiểm thử serialization và round-trip

Kiểm thử object trong bộ nhớ chưa đủ. Cần serialize thành payload và deserialize bằng cùng contract mà consumer thực sự dùng. Một số kiểm tra quan trọng:

1. **Timestamp:** parse lại thành Instant và xác nhận cùng thời điểm sau khi chuẩn hóa precision.
2. **Timezone:** payload chứa Z hoặc offset rõ ràng; không có chuỗi thời gian phụ thuộc locale.
3. **Precision:** xác nhận timestamp không bị mất phần lẻ vượt ngoài precision đã cam kết.
4. **Decimal:** xác nhận "1234.50" vẫn giữ chữ số và scale theo contract.
5. **Giá trị biên:** kiểm tra số rất lớn, số âm nếu hợp lệ, số có nhiều chữ số thập phân và giá trị bằng zero.
6. **Rounding:** kiểm tra kết quả ở đúng ranh giới làm tròn theo rounding mode đã chọn.
7. **Cross-language:** dùng consumer hoặc schema validator đại diện để xác nhận kiểu trường và cách parse.
8. **Externalization path:** kiểm tra payload thực sự được integration gửi ra broker/endpoint, không chỉ kiểm tra một mapper độc lập.

Ví dụ kiểm thử Jackson cho timestamp và decimal string:

~~~java
@Test
void serializesTimestampAndDecimalAccordingToContract() throws Exception {
    PaymentCaptured event = new PaymentCaptured(
        UUID.fromString("7f90c6e0-5e1f-4c8c-9a72-2df2c7d74e2a"),
        UUID.fromString("d78e11d9-bae8-42bb-a1a5-9d2e0c2dbdd8"),
        Instant.parse("2026-11-25T13:30:45.123Z"),
        new BigDecimal("1234.50"),
        "USD"
    );

    String json = objectMapper.writeValueAsString(event);
    JsonNode payload = objectMapper.readTree(json);

    assertEquals(
        "2026-11-25T13:30:45.123Z",
        payload.get("occurredAt").asText()
    );
    assertEquals("1234.50", payload.get("amount").asText());
    assertTrue(payload.get("amount").isTextual());
}
~~~

Đây là ví dụ kiểm thử contract; **objectMapper** cần là mapper được cấu hình giống đường đi externalization trong ứng dụng. Nếu adapter sử dụng một serializer khác, kiểm thử phải đi qua adapter hoặc transport test để phát hiện khác biệt.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Dùng **LocalDateTime** cho thời điểm event toàn cục | Consumer không biết timezone để xác định instant | Dùng **Instant** hoặc gửi offset/timezone rõ ràng |
| Dùng chuỗi ngày giờ theo locale | Không parse ổn định giữa môi trường | Dùng ISO-8601 |
| Không công bố đơn vị epoch | Timestamp lệch giây/mili giây | Ghi rõ unit trong schema |
| Dùng **double** cho tiền | Sai số thập phân tích lũy | Dùng **BigDecimal** |
| Dùng **new BigDecimal(double)** | Mang sai số từ double vào decimal | Khởi tạo từ chuỗi hoặc nguồn decimal |
| Để consumer parse JSON number thành floating point | Mất chữ số có nghĩa | Dùng decimal type hoặc decimal string |
| Không quy định scale và rounding | Các module cho kết quả tiền khác nhau | Chốt scale, currency và rounding mode |
| Cấu hình mapper không được adapter sử dụng | Payload thực tế khác test | Kiểm tra serializer của đường externalization thực tế |

## 11. Checklist cho event serialization

Trước khi công bố một event contract, hãy xác nhận:

- Thời điểm biểu diễn bằng **Instant**, **OffsetDateTime** hay kiểu ngày lịch đúng với ý nghĩa nghiệp vụ.
- Timestamp dùng ISO-8601 hay epoch; nếu epoch thì đơn vị đã được ghi rõ.
- Timezone/offset có được giữ và chuẩn hóa đúng không.
- Độ chính xác timestamp được thống nhất giữa producer, transport và consumer.
- Decimal dùng **BigDecimal**, không đi qua **float** hoặc **double**.
- Contract quy định JSON number, decimal string hay integer minor unit.
- Scale, rounding mode và currency code được xác định.
- Jackson mapper mà externalization adapter sử dụng đã được cấu hình và kiểm thử.
- Thay đổi định dạng có tương thích với consumer cũ hay cần version mới.
- Event ID và correlation metadata vẫn ổn định qua retry và replay.

Serialization chính xác giữ cho ý nghĩa nghiệp vụ không thay đổi khi event rời khỏi module và đi qua các hệ thống khác nhau. Khi chuẩn hóa timestamp, decimal, currency và schema ngay từ contract, các module Spring Modulith có thể trao đổi sự kiện đáng tin cậy mà không phụ thuộc vào timezone, locale hoặc cách biểu diễn số riêng của từng nền tảng.

