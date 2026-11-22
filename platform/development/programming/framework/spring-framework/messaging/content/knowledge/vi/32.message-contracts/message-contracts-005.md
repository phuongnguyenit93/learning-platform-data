# Định dạng thời gian, múi giờ, số và giá trị enum

## Mục tiêu

Sau bài này, bạn có thể:

- Chọn kiểu Java phù hợp để biểu diễn thời điểm, ngày lịch, giờ địa phương và múi giờ.
- Thiết kế định dạng thời gian ổn định giữa các service, kể cả khi chạy ở nhiều quốc gia.
- Tránh mất độ chính xác khi trao đổi số nguyên lớn, số thập phân và tiền tệ qua JSON.
- Chọn cách biểu diễn enum có thể tồn tại qua các lần đổi tên, thêm giá trị và nâng cấp service độc lập.
- Cấu hình Jackson codec/converter trong Spring Messaging và RSocket.
- Kiểm thử hợp đồng serialization/deserialization để phát hiện thay đổi không tương thích.

Bài này thuộc chủ đề **Spring Framework - messaging**, trong nhánh **Hợp đồng thông điệp**. Những giá trị gửi qua message là một phần của hợp đồng giữa producer và consumer. Kiểu Java nội bộ không tự động trở thành định dạng wire ổn định: hai phía có thể dùng ngôn ngữ, phiên bản thư viện, locale và quy tắc xử lý khác nhau.

## 1. Vì sao định dạng wire phải được thiết kế rõ ràng?

Một object Java có thể chứa Instant, BigDecimal hoặc enum. Khi gửi qua messaging, object được encoder chuyển thành byte theo một định dạng như JSON, CBOR hoặc một định dạng nhị phân khác. Consumer giải mã byte thành kiểu dữ liệu của chính nó.

Nếu producer và consumer hiểu khác nhau về cùng một trường, message vẫn có thể parse thành công nhưng mang ý nghĩa sai. Ví dụ:

- Producer gửi thời gian địa phương nhưng consumer hiểu đó là UTC.
- Producer gửi số tiền 1.234,50 theo locale, consumer mong đợi JSON number dùng dấu chấm thập phân.
- Producer gửi enum bằng ordinal 2, consumer có thứ tự enum khác sau khi thêm một giá trị mới.
- Producer gửi một số nguyên 64 bit, consumer JavaScript làm tròn vì Number không biểu diễn chính xác số nguyên lớn đó.
- Producer đổi tên enum hoặc đổi kiểu trường nhưng không nâng version hợp đồng.

Vì vậy, hợp đồng message cần quy định tối thiểu:

1. Tên trường và kiểu wire.
2. Đơn vị đo và độ chính xác.
3. Format ngày giờ, timezone và ý nghĩa của giá trị.
4. Mã enum ổn định và cách xử lý giá trị chưa biết.
5. Quy tắc null, trường thiếu, giá trị mặc định và validation.
6. Chính sách tương thích khi producer/consumer được triển khai ở các thời điểm khác nhau.

Không nên dựa vào việc hai service hiện tại cùng dùng một class Java. Hợp đồng phải được hiểu từ nội dung message và schema, độc lập với implementation.

## 2. Thời gian: chọn đúng kiểu trước khi chọn format

Java Time API có nhiều kiểu thời gian vì mỗi kiểu mô tả một ý nghĩa khác nhau. Chọn sai kiểu sẽ khiến thông tin bị mất ngay cả khi serialization hợp lệ.

| Kiểu Java | Ý nghĩa | Dùng khi |
|---|---|---|
| Instant | Một điểm duy nhất trên timeline UTC | Thời điểm tạo event, thanh toán, log, cập nhật |
| OffsetDateTime | Ngày giờ kèm UTC offset như +07:00 | Cần giữ offset được gửi từ nguồn |
| ZonedDateTime | Ngày giờ gắn với ZoneId và quy tắc vùng | Lịch hẹn theo múi giờ địa phương |
| LocalDateTime | Ngày giờ trên đồng hồ nhưng không có offset/zone | Giá trị tạm thời chỉ có ý nghĩa trong một ngữ cảnh địa phương đã biết |
| LocalDate | Ngày lịch, không có giờ và timezone | Ngày sinh, ngày hiệu lực theo lịch |
| LocalTime | Giờ trong ngày, không có ngày và timezone | Giờ mở cửa hoặc giờ lặp hằng ngày |
| Duration | Khoảng thời gian theo số giây/nanosecond | Timeout, thời lượng đã trôi qua |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | Chu kỳ lịch như 1 tháng hoặc 1 năm |

### 2.1. Instant cho thời điểm đã xảy ra

Với event đã xảy ra, thường nên dùng Instant. Nó biểu diễn một điểm duy nhất trên timeline và không phụ thuộc timezone của máy chạy service.

Ví dụ JSON:

~~~json
{
  "eventId": "evt-901",
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

Chuỗi ISO-8601 trên biểu diễn thời điểm UTC. Nếu một consumer ở Việt Nam hiển thị thời điểm đó theo giờ địa phương, nó có thể chuyển thành 21:17 tại Asia/Ho_Chi_Minh. Việc hiển thị theo timezone của người dùng là bước presentation; không nên thay đổi instant đã lưu trong event.

### 2.2. Offset không phải timezone

Offset như +07:00 chỉ cho biết chênh lệch so với UTC tại thời điểm cụ thể. Nó không mang toàn bộ quy tắc lịch sử và tương lai của một vùng địa lý.

Ví dụ:

- Asia/Ho_Chi_Minh là một ZoneId theo cơ sở dữ liệu timezone IANA.
- +07:00 là một ZoneOffset cố định.
- OffsetDateTime giữ ngày giờ và offset.
- ZonedDateTime có thể giữ cả ZoneId và quy tắc chuyển đổi theo vùng.

Nếu nghiệp vụ chỉ cần một thời điểm đã xảy ra, Instant là đủ. Nếu cần hiển thị lại đúng giờ địa phương của vùng đã chọn hoặc tính lịch trong tương lai, hãy giữ ZoneId riêng.

Ví dụ message cho lịch hẹn:

~~~json
{
  "appointmentId": "apt-42",
  "localDateTime": "2026-12-15T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Consumer có thể dựng ZonedDateTime từ localDateTime và ZoneId. Với các vùng có quy tắc DST, cần thêm chính sách xử lý giờ không tồn tại hoặc giờ xuất hiện hai lần.

### 2.3. DST: giờ địa phương có thể mơ hồ hoặc không tồn tại

Khi một vùng chuyển sang giờ mùa hè, đồng hồ có thể nhảy qua một khoảng giờ. Một LocalDateTime nằm trong khoảng bị bỏ qua không ánh xạ tới instant nào. Khi đồng hồ lùi lại, một LocalDateTime có thể ánh xạ tới hai instant khác nhau.

Do đó, nếu message đại diện cho lịch hẹn trong tương lai:

- Gửi LocalDateTime cùng ZoneId, không chỉ gửi offset hiện tại.
- Quy định cách xử lý thời gian nằm trong DST gap, ví dụ từ chối và yêu cầu người dùng chọn lại, hoặc dịch sang thời điểm hợp lệ tiếp theo.
- Quy định cách chọn offset khi thời gian nằm trong DST overlap, ví dụ chọn offset sớm hơn hoặc muộn hơn.
- Nếu lịch hẹn đã được xác nhận thành một thời điểm cụ thể, lưu thêm Instant đã resolve để các service cùng hiểu kết quả.

Không nên tự ý giả định mọi ngày đều có đúng 24 giờ hoặc mọi timezone đều có offset cố định.

### 2.4. Tránh LocalDateTime cho event toàn hệ thống

LocalDateTime như 2026-11-07T21:17:00 không nói đó là giờ Việt Nam, UTC hay một vùng khác. Nếu producer gửi LocalDateTime và consumer tự gắn timezone mặc định của server, kết quả phụ thuộc môi trường triển khai.

Dùng LocalDateTime khi ngữ nghĩa thật sự là giờ trên đồng hồ địa phương và timezone được xác định ở nơi khác trong hợp đồng. Với timestamp của event, ưu tiên Instant.

### 2.5. Đơn vị epoch phải được đặt tên rõ

Một số hệ thống dùng số epoch thay vì chuỗi ISO-8601. Epoch thường là số giây hoặc mili giây kể từ 1970-01-01T00:00:00Z. Hai đơn vị này khác nhau 1.000 lần.

Nếu dùng số, tên trường phải nói rõ đơn vị:

~~~json
{
  "createdAtEpochMillis": 1794061020000
}
~~~

Không dùng tên mơ hồ như timestamp nếu schema không quy định đơn vị. Java Instant.toEpochMilli() chỉ giữ độ chính xác đến mili giây; nếu nghiệp vụ cần nanosecond, hãy dùng chuỗi ISO-8601 hoặc quy ước số có độ chính xác tương ứng.

## 3. Format thời gian trong JSON và Jackson

JSON không định nghĩa một kiểu ngày giờ riêng. Timestamp thường được truyền dưới dạng string hoặc number. Hợp đồng phải quy định format và ý nghĩa.

Với Java Time, Jackson cần module hỗ trợ JSR-310. Cấu hình phổ biến cho timestamp dạng chuỗi:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Các import liên quan:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

Khi WRITE_DATES_AS_TIMESTAMPS bị tắt, Instant được biểu diễn dưới dạng chuỗi ISO-8601 thay vì mảng hoặc số timestamp. Consumer cần cùng hiểu kiểu trường đó là instant UTC.

Không nên dựa vào timezone mặc định của JVM để diễn giải LocalDateTime. Cũng không nên nghĩ rằng gọi ObjectMapper.setTimeZone(UTC) sẽ biến một LocalDateTime thành một thời điểm tuyệt đối; LocalDateTime vốn không chứa timezone.

Nếu dùng java.util.Date hoặc Calendar trong DTO cũ, cần quy định rõ timezone khi chuyển đổi. Với code mới, ưu tiên java.time để ý nghĩa của từng kiểu rõ ràng hơn.

## 4. Locale không thuộc wire format

Locale phục vụ cách con người đọc và nhập dữ liệu. Nó không nên làm thay đổi biểu diễn máy-to-máy.

Ví dụ, cùng một số tiền có thể được hiển thị theo các cách:

| Locale | Chuỗi hiển thị |
|---|---|
| en-US | 1,234.50 |
| de-DE | 1.234,50 |
| vi-VN | 1.234,50 |

Đây là chuỗi hiển thị, không phải định dạng JSON number. JSON number dùng dấu chấm làm dấu thập phân và không có dấu phân tách hàng nghìn:

~~~json
{
  "quantity": 1234.5
}
~~~

Nếu gửi "1.234,50" như một string mà không quy định locale, consumer không biết dấu chấm là dấu nhóm hay dấu thập phân.

Quy tắc:

- Không gửi số đã format theo locale trong trường numeric.
- Không gửi tên tháng, ngày hoặc enum đã dịch sang ngôn ngữ người dùng nếu consumer cần mã máy.
- Không phụ thuộc locale mặc định của JVM hoặc container.
- Chỉ format cho người dùng ở lớp presentation.
- Với chuỗi số theo hợp đồng, quy định dấu thập phân, dấu âm, scale và quy tắc leading zero.

## 5. Số nguyên và giới hạn độ chính xác giữa các ngôn ngữ

Java có byte, short, int, long và BigInteger. JSON có một cú pháp number chung, nhưng các ngôn ngữ có thể chuyển nó thành kiểu khác nhau.

JavaScript Number dùng IEEE-754 binary64. Nó biểu diễn chính xác mọi số nguyên trong phạm vi an toàn từ -(2^53 - 1) đến +(2^53 - 1). Một long Java lớn hơn phạm vi này có thể bị làm tròn khi consumer chuyển thành Number.

Ví dụ, ID số nguyên 64 bit có thể bị mất chữ số ở một consumer JavaScript. Vì ID là định danh, không phải đại lượng để tính toán, thường nên gửi dưới dạng string:

~~~json
{
  "accountId": "9007199254740993"
}
~~~

Nếu trường thực sự là đại lượng cần tính toán, hãy quy định kiểu, phạm vi và độ chính xác ở schema. Với số nguyên rất lớn, consumer cần kiểu BigInt/BigInteger hoặc thư viện tương ứng thay vì Number.

Không nên dùng ordinal, số thứ tự hoặc giá trị có thể thay đổi làm ID ổn định của một đối tượng.

## 6. Số thập phân, BigDecimal và tiền tệ

### 6.1. double không phù hợp cho phép tính tiền chính xác

double dùng số dấu phẩy động nhị phân. Nhiều số thập phân như 0.1 không có biểu diễn nhị phân hữu hạn, nên phép tính có thể xuất hiện sai số.

~~~java
System.out.println(0.1 + 0.2);
~~~

Output điển hình:

~~~text
0.30000000000000004
~~~

Với tiền hoặc số thập phân cần chính xác theo hợp đồng, dùng BigDecimal:

~~~java
BigDecimal amount = new BigDecimal("1234.50");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate);
~~~

Tạo BigDecimal từ chuỗi thập phân đã chuẩn hóa. Tránh new BigDecimal(0.1), vì constructor đó chuyển giá trị double đã xấp xỉ sang BigDecimal.

### 6.2. Chọn biểu diễn tiền tệ

Có hai cách thường dùng:

**Cách A — decimal string**

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Ưu điểm: giữ scale và không bị consumer tự chuyển sang floating point. Hợp đồng phải quy định string là số thập phân chuẩn hóa, không có dấu phân tách hàng nghìn và dùng dấu chấm thập phân.

**Cách B — integer minor units**

~~~json
{
  "amountMinor": 123450,
  "currency": "USD"
}
~~~

Cách này tránh số thập phân trong wire, nhưng phải biết số chữ số thập phân của từng currency. Không được mặc định mọi currency đều có hai chữ số lẻ. Một số currency không có minor unit; một số có ba chữ số. Quy tắc phải dựa trên currency metadata và hợp đồng của hệ thống.

Không gửi một số tiền trần mà thiếu currency. 100 có thể là 100 USD, 100 JPY hoặc 100 đơn vị của một loại tiền khác.

### 6.3. Scale và rounding phải là quy tắc nghiệp vụ

BigDecimal giữ scale. Ví dụ 1.0 và 1.00 có giá trị số học tương đương nhưng BigDecimal.equals() trả về false vì scale khác nhau; compareTo() trả về 0.

Nếu scale có ý nghĩa trong hợp đồng, hãy giữ và kiểm tra nó. Nếu chỉ so sánh giá trị số học, dùng compareTo() hoặc chuẩn hóa theo quy tắc đã thống nhất.

Khi làm tròn, chỉ định RoundingMode rõ ràng:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

Không tự chọn HALF_UP hoặc HALF_EVEN theo cảm tính; chính sách rounding có thể ảnh hưởng tới hóa đơn, thuế và sổ cái. Producer và consumer phải dùng cùng quy tắc nghiệp vụ.

### 6.4. JSON number có giới hạn thực tế

JSON không áp đặt một độ chính xác thập phân cố định, nhưng các parser có thể chuyển number sang double. Nếu cần giữ chính xác thập phân qua nhiều ngôn ngữ, decimal string hoặc integer minor units thường rõ ràng hơn. Nếu schema dùng JSON number, yêu cầu consumer parse thành BigDecimal hoặc kiểu decimal tương đương.

Không gửi NaN hoặc Infinity như JSON number. Đây không phải các giá trị number hợp lệ theo JSON chuẩn. Hãy biểu diễn trạng thái đặc biệt bằng null, một trường status hoặc một mã riêng theo hợp đồng.

## 7. Enum: dùng mã wire ổn định, không dùng ordinal

Enum Java có tên và ordinal. Ordinal là vị trí của hằng trong khai báo enum, bắt đầu từ 0. Nếu serializer gửi ordinal, việc chèn một hằng mới ở giữa có thể làm thay đổi ý nghĩa của các số đã phát hành.

Ví dụ không an toàn:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

Nếu producer gửi ordinal 1 cho PAID, sau này thêm CANCELLED trước PAID thì ordinal 1 có thể mang nghĩa khác. Consumer cũ và mới có thể hiểu cùng một số theo hai cách.

Hợp đồng nên dùng string code ổn định:

~~~json
{
  "status": "paid"
}
~~~

Không nên dùng nhãn hiển thị đã dịch như "Đã thanh toán" làm mã wire. Nhãn có thể thay đổi theo ngôn ngữ hoặc UX; code nên ổn định và độc lập với locale.

### 7.1. Jackson với @JsonValue và @JsonCreator

Có thể ánh xạ enum sang mã wire riêng:

~~~java
enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    SHIPPED("shipped"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String value) {
        for (OrderStatus status : values()) {
            if (status.code.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unsupported order status: " + value
        );
    }
}
~~~

@JsonValue chọn giá trị string khi serialize. @JsonCreator xác định cách dựng enum khi deserialize. Cách này cho phép đổi tên hằng Java nội bộ mà không đổi wire code.

### 7.2. Giá trị enum chưa biết

Khi consumer mới gửi một enum mới, consumer cũ có thể không nhận diện được. Có một số chính sách:

- **Strict:** từ chối message với lỗi rõ ràng. Phù hợp khi giá trị không biết làm cho nghiệp vụ không thể xử lý an toàn.
- **Fallback UNKNOWN:** ánh xạ về một giá trị mặc định. Chỉ phù hợp nếu nghiệp vụ có thể xử lý trạng thái không xác định mà không gây sai lệch.
- **Preserve raw string:** lưu mã gốc dưới dạng string hoặc wrapper để consumer cũ có thể chuyển tiếp/ghi nhận mà không làm mất thông tin.

Chỉ ánh xạ về UNKNOWN rồi serialize lại thành "unknown" có thể làm mất mã ban đầu. Nếu cần round-trip hoặc chuyển tiếp message, hãy giữ raw code.

Khi thêm enum mới, cần xét thứ tự triển khai: producer có thể phát mã mới trước khi tất cả consumer được nâng cấp. Chọn strict hay fallback dựa trên khả năng tương thích thực tế, không dựa vào mong muốn rằng mọi service sẽ deploy đồng thời.

### 7.3. Không đổi mã wire đã phát hành

Nếu Java enum hằng PAID được đổi tên thành SETTLED, giữ wire code "paid" nếu đó vẫn là cùng một khái niệm hợp đồng. Nếu ý nghĩa nghiệp vụ thực sự thay đổi, hãy phát hành code mới và quy định chuyển đổi. Không tái sử dụng code cũ cho ý nghĩa mới.

## 8. Kết hợp thời gian, số và enum trong một message

Một message event có thể có cấu trúc:

~~~json
{
  "schemaVersion": 1,
  "messageId": "9007199254740993",
  "occurredAt": "2026-11-07T14:17:00Z",
  "amount": "1234.50",
  "currency": "USD",
  "status": "paid"
}
~~~

Các quyết định trong hợp đồng này:

- schemaVersion là số nguyên nhỏ và có quy tắc nâng version.
- messageId là string để không bị mất chính xác ở consumer JavaScript.
- occurredAt là ISO-8601 UTC instant.
- amount là decimal string với dấu chấm và scale theo quy tắc currency.
- currency là mã currency ổn định.
- status là mã enum string, không phải ordinal hoặc label.

Một consumer có thể deserialize message vào DTO riêng của mình. DTO là implementation detail; các wire value ở trên mới là hợp đồng.

## 9. Cấu hình Jackson codec cho Spring Messaging/RSocket

Spring Messaging cung cấp abstraction Message và MessageConverter. Transport quyết định cách encode/decode cụ thể:

- Với STOMP/WebSocket message broker, converter trong cấu hình broker thường chuyển object payload thành JSON và ngược lại. MappingJackson2MessageConverter là converter Jackson của Spring Messaging.
- Với RSocket, RSocketStrategies quản lý encoder/decoder được dùng cho data và metadata. Có thể cấu hình Jackson JSON encoder/decoder dùng cùng ObjectMapper.
- Với transport hoặc broker khác, adapter tương ứng có thể có cấu hình converter riêng. Không giả định một cấu hình của STOMP tự động áp dụng cho RSocket hoặc Kafka.

Ví dụ cấu hình RSocketStrategies với ObjectMapper có JavaTimeModule:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(
        new Jackson2JsonEncoder(mapper)
    ))
    .decoders(decoders -> decoders.add(
        new Jackson2JsonDecoder(mapper)
    ))
    .build();
~~~

Các import codec liên quan:

~~~java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
~~~

Dùng strategies này khi tạo RSocketRequester hoặc cấu hình server RSocket. Bảo đảm cả producer và consumer thống nhất MIME type, ObjectMapper và DTO/schema. Nếu application có nhiều codec, hãy kiểm tra thứ tự và MIME type để đúng encoder/decoder được chọn.

Với STOMP, có thể đăng ký MappingJackson2MessageConverter trong configureMessageConverters của WebSocketMessageBrokerConfigurer và truyền cùng ObjectMapper đã cấu hình. Nếu giữ default converters, kiểm tra hành vi return value của phương thức cấu hình theo API phiên bản Spring đang dùng.

Không nên tạo một ObjectMapper toàn cục với các quy tắc riêng cho một message mà không hiểu ảnh hưởng tới HTTP API hoặc các message type khác. Có thể dùng mapper/codec chuyên biệt theo boundary khi các hợp đồng khác nhau.

## 10. Null, trường thiếu và giá trị mặc định

JSON phân biệt trường bị thiếu và trường có giá trị null. Consumer cũng cần biết hai trường hợp này có ý nghĩa gì.

Ví dụ:

~~~json
{
  "status": null
}
~~~

khác với:

~~~json
{}
~~~

Một số DTO có thể map cả hai về null nếu không có cấu hình đặc biệt, nhưng hợp đồng vẫn nên quy định:

- Trường bắt buộc có được phép null không?
- Trường tùy chọn bị thiếu có giá trị mặc định nào?
- Null có nghĩa là xóa giá trị, chưa biết hay không áp dụng?
- Consumer cũ phải xử lý thế nào khi producer thêm trường mới?
- Producer có thể ngừng gửi một trường đã phát hành hay không?

Với message command, trường bắt buộc thiếu nên được validation và trả lỗi có thể chẩn đoán. Không nên âm thầm thay một giá trị tiền tệ hoặc timezone bị thiếu bằng default của server.

Với event, trường mới thường nên được thêm theo cách tương thích: consumer cũ có thể bỏ qua nếu không cần trường đó; consumer mới phải có quy tắc cho event cũ chưa có trường. Việc bật/tắt FAIL_ON_UNKNOWN_PROPERTIES cần là quyết định có chủ đích, nhất quán với chính sách schema evolution.

## 11. Schema evolution và tương thích producer/consumer

Trong hệ thống phân tán, không thể bảo đảm tất cả service nâng cấp cùng một thời điểm. Một producer mới có thể gửi message cho consumer cũ; consumer mới cũng có thể đọc message đã được lưu từ nhiều tháng trước.

Một số quy tắc an toàn:

1. Thêm trường optional trước khi bắt đầu phụ thuộc vào nó.
2. Đặt default có ý nghĩa rõ ràng khi consumer đọc message cũ.
3. Không đổi kiểu wire của một trường đang được sử dụng.
4. Không đổi đơn vị thời gian hoặc đơn vị tiền tệ mà không phát hành version/field mới.
5. Không đổi enum code đã phát hành.
6. Không tái sử dụng giá trị enum cũ cho ý nghĩa khác.
7. Nếu thay đổi không tương thích, version hóa schema hoặc route/event type và có kế hoạch chuyển đổi.
8. Duy trì contract test giữa các phiên bản producer và consumer được hỗ trợ.

Ví dụ, nếu trường occurredAt trước đây là epoch milliseconds và muốn chuyển sang ISO string, không đổi trực tiếp cùng tên trường mà không có migration. Có thể phát hành trường occurredAtIso trong version mới, hỗ trợ đọc cả hai trong giai đoạn chuyển tiếp, rồi ngừng trường cũ theo lịch đã thông báo.

## 12. Ví dụ Java 17: serialize một message có wire contract rõ ràng

Ví dụ sau dùng Jackson 2 và Java Time để serialize/deserialize một DTO. ID, amount và enum có biểu diễn wire ổn định.

### Maven dependencies

Thêm các dependency sau vào pom.xml. Trong dự án Spring Boot, nên dùng dependency management/BOM do phiên bản Boot quản lý thay vì khai báo version khác với nền tảng dự án.

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
~~~

### Source code

Lưu thành **MessageContractDemo.java**:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.math.BigDecimal;
import java.time.Instant;

public class MessageContractDemo {

    enum PaymentStatus {
        PENDING("pending"),
        PAID("paid"),
        CANCELLED("cancelled");

        private final String code;

        PaymentStatus(String code) {
            this.code = code;
        }

        @JsonValue
        public String code() {
            return code;
        }

        @JsonCreator
        public static PaymentStatus fromCode(String value) {
            for (PaymentStatus status : values()) {
                if (status.code.equals(value)) {
                    return status;
                }
            }
            throw new IllegalArgumentException(
                "Unsupported payment status: " + value
            );
        }
    }

    record PaymentEvent(
        int schemaVersion,
        String messageId,
        Instant occurredAt,
        String amount,
        String currency,
        PaymentStatus status
    ) {}

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();

        PaymentEvent event = new PaymentEvent(
            1,
            "9007199254740993",
            Instant.parse("2026-11-07T14:17:00Z"),
            "1234.50",
            "USD",
            PaymentStatus.PAID
        );

        String json = mapper.writeValueAsString(event);
        PaymentEvent restored = mapper.readValue(json, PaymentEvent.class);

        BigDecimal amount = new BigDecimal(restored.amount());

        System.out.println(json);
        System.out.println("instant-preserved="
            + event.occurredAt().equals(restored.occurredAt()));
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("status=" + restored.status().code());
    }
}
~~~

### Biên dịch và chạy

Với Maven, có thể thêm exec-maven-plugin vào pom.xml rồi chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=MessageContractDemo
~~~

Output chính xác:

~~~text
{"schemaVersion":1,"messageId":"9007199254740993","occurredAt":"2026-11-07T14:17:00Z","amount":"1234.50","currency":"USD","status":"paid"}
instant-preserved=true
amount=1234.50
status=paid
~~~

Ví dụ chứng minh:

- Instant được serialize thành ISO-8601 UTC string.
- messageId được giữ nguyên dưới dạng string dù lớn hơn giới hạn số nguyên an toàn của JavaScript.
- amount giữ scale hai chữ số nhờ decimal string.
- PaymentStatus dùng wire code "paid", không dùng tên enum Java hoặc ordinal.
- Sau deserialize, giá trị thời gian, tiền và enum có thể được kiểm tra lại.

Ví dụ này là chương trình demo độc lập với Spring container nhưng dùng cùng Jackson module/codec mà ứng dụng Spring có thể cấu hình. Nó chưa thay thế validation nghiệp vụ như kiểm tra currency, amount scale, schemaVersion hoặc quyền phát event.

## 13. Kiểm thử hợp đồng serialization

Đừng chỉ kiểm tra rằng JSON parse thành công. Hãy kiểm tra chính xác wire value và các trường hợp biên.

Các kiểm thử nên có:

- Instant serialize đúng UTC ISO-8601 và deserialize về cùng instant.
- LocalDate giữ đúng ngày, không bị dịch do timezone.
- LocalDateTime không bị tự gắn timezone mặc định.
- ZoneId được giữ nếu nghiệp vụ cần tính lịch theo vùng.
- Timestamp epoch ghi rõ đơn vị giây/mili giây.
- Số nguyên lớn không bị chuyển thành JavaScript Number nếu vượt safe integer.
- BigDecimal không bị chuyển qua double.
- Tiền luôn đi cùng currency và scale hợp lệ.
- Enum serialize thành code ổn định.
- Enum code không biết được xử lý theo strict/fallback/preserve policy.
- Trường thiếu, null và trường mới được xử lý theo schema.
- Payload cũ vẫn được consumer mới đọc theo chính sách tương thích.

Một golden JSON fixture giúp phát hiện thay đổi ngoài ý muốn. Có thể lưu payload mẫu trong test resources, serialize DTO rồi so sánh JSON theo cấu trúc hoặc canonical form. Nếu cần so sánh byte chính xác để ký số hoặc hashing, phải quy định cả canonical JSON, thứ tự trường, encoding UTF-8 và cách escape; thứ tự property thông thường không nên được coi là ngữ nghĩa của JSON.

## 14. Lỗi thường gặp

- **Dùng LocalDateTime cho thời điểm event:** thiếu offset và timezone nên consumer có thể hiểu sai thời điểm.
- **Gửi +07:00 rồi cho rằng consumer biết vùng địa lý:** offset không chứa ZoneId và quy tắc DST.
- **Dùng timezone mặc định của server:** kết quả có thể khác giữa môi trường triển khai.
- **Gửi ngày giờ theo locale:** chuỗi như 07/11/2026 mơ hồ giữa ngày/tháng và tháng/ngày.
- **Dùng double cho tiền:** phép tính có thể sai số.
- **Gửi long ID như JSON number cho JavaScript:** số nguyên lớn có thể bị làm tròn.
- **Gửi BigDecimal qua JSON number mà không quy định parser:** consumer có thể parse thành floating point.
- **Gửi enum ordinal:** thêm hoặc sắp xếp lại hằng làm thay đổi ý nghĩa wire.
- **Dùng enum label đã dịch:** thay đổi bản dịch làm hỏng contract.
- **Từ chối mọi enum mới mà không có chiến lược rollout:** producer mới có thể làm consumer cũ ngừng xử lý message.
- **Map enum lạ về UNKNOWN rồi làm mất raw code:** message không thể round-trip nguyên vẹn.
- **Thay đổi đơn vị hoặc kiểu trường tại chỗ:** producer và consumer phiên bản khác nhau có thể diễn giải cùng dữ liệu theo hai cách.

## 15. Checklist trước khi phát hành message contract

- [ ] Mỗi trường thời gian có kiểu và ý nghĩa rõ: instant, local date, local time hay lịch theo timezone.
- [ ] Timestamp event dùng UTC/ISO-8601 hoặc epoch có đơn vị được ghi rõ.
- [ ] ZoneId được lưu nếu nghiệp vụ cần quy tắc vùng/DST.
- [ ] Locale không ảnh hưởng wire format.
- [ ] ID lớn được biểu diễn dưới dạng string hoặc kiểu integer an toàn ở mọi consumer.
- [ ] Số thập phân có quy tắc precision, scale và rounding.
- [ ] Tiền luôn có currency; minor-unit scale được xác định theo currency.
- [ ] Enum dùng string code ổn định, không dùng ordinal/label.
- [ ] Có chính sách cho enum value chưa biết.
- [ ] Null, trường thiếu và default được quy định.
- [ ] Producer và consumer dùng codec/MIME type tương thích.
- [ ] Có golden payload và contract test cho phiên bản cũ/mới.
- [ ] Thay đổi không tương thích được version hóa và có kế hoạch migration.

## Kết luận

Định dạng thời gian, số và enum quyết định ý nghĩa của message sau khi đi qua ranh giới service. Hãy dùng Instant cho thời điểm đã xảy ra, giữ ZoneId khi cần lịch địa phương, dùng BigDecimal hoặc decimal string cho độ chính xác thập phân, và dùng enum wire code ổn định. Cấu hình Jackson trong converter/codec Spring chỉ là một phần; producer và consumer vẫn phải thống nhất schema, validation, null semantics và chiến lược evolution.

## Tài liệu tham khảo

- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/messaging.html)
- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Jackson Datatype JSR-310](https://github.com/FasterXML/jackson-modules-java8/tree/2.17/datetime)
- [Java Date-Time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [JSON Data Interchange Syntax (RFC 8259)](https://www.rfc-editor.org/rfc/rfc8259)
- [IANA Time Zone Database](https://www.iana.org/time-zones)
