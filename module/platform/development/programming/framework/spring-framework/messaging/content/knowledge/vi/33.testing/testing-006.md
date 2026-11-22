# Định dạng thời gian, múi giờ, số và giá trị enum

## Mục tiêu

Sau bài này, bạn có thể:

- Thiết kế biểu diễn wire cho thời điểm, ngày lịch, giờ địa phương và lịch hẹn theo timezone.
- Phân biệt Instant, OffsetDateTime, ZonedDateTime, LocalDateTime, Duration và Period.
- Quy định precision, scale, đơn vị và cách làm tròn cho số trong message.
- Tránh mất chính xác với long, BigInteger, BigDecimal và consumer JavaScript.
- Thiết kế enum code ổn định, xử lý giá trị mới và duy trì tương thích giữa các phiên bản service.
- Cấu hình Jackson cho Spring Messaging và RSocket.
- Viết contract test để phát hiện thay đổi serialization trước khi phát hành.

Bài này thuộc chủ đề **Spring Framework - messaging**, nhánh **Hợp đồng thông điệp**. Một message là hợp đồng giữa producer và consumer. Kiểu Java nội bộ không tự động trở thành định dạng wire ổn định: hai phía có thể dùng ngôn ngữ, phiên bản thư viện, locale và quy tắc xử lý khác nhau.

## 1. Định dạng wire là một phần của hợp đồng

Khi một object được gửi qua messaging, encoder chuyển dữ liệu thành byte theo một format như JSON hoặc CBOR. Consumer dùng decoder để chuyển byte thành object của chính nó.

Cùng một dữ liệu có thể được hiểu khác nhau nếu hợp đồng không quy định rõ:

- 2026-11-07T09:30:00 là giờ UTC hay giờ địa phương?
- 1,234.50 là một nghìn hai trăm ba mươi tư phẩy năm mươi hay một phẩy hai ba bốn?
- 9007199254740993 có thể được JavaScript giữ nguyên khi parse thành Number không?
- 2 là enum nào nếu producer và consumer có thứ tự khai báo enum khác nhau?
- Trường bị thiếu có nghĩa là giữ nguyên, đặt default hay xóa giá trị?

Một message contract nên xác định:

1. Tên trường và kiểu dữ liệu wire.
2. Đơn vị đo, precision, scale và quy tắc rounding.
3. Ý nghĩa thời gian, timezone và format.
4. Mã enum ổn định cùng chính sách xử lý giá trị chưa biết.
5. Quy tắc trường bắt buộc, null, trường thiếu và default.
6. Chính sách versioning và tương thích producer/consumer.

Không nên coi hai service đang dùng cùng một DTO Java là bằng chứng rằng hợp đồng đã ổn định. DTO có thể thay đổi theo release; message đã phát hành có thể vẫn được lưu trong broker hoặc được consumer cũ xử lý.

## 2. Chọn kiểu thời gian theo ý nghĩa nghiệp vụ

Java Time API có nhiều kiểu vì một ngày giờ trên đồng hồ không phải lúc nào cũng là một thời điểm tuyệt đối.

| Kiểu | Thông tin mang theo | Trường hợp phù hợp |
|---|---|---|
| Instant | Điểm trên timeline UTC | Thời điểm event đã xảy ra |
| OffsetDateTime | Ngày giờ cùng offset UTC | Cần giữ offset đã được nguồn cung cấp |
| ZonedDateTime | Ngày giờ cùng ZoneId và quy tắc vùng | Lịch hẹn hoặc lịch vận hành theo vùng địa lý |
| LocalDateTime | Ngày và giờ, không có zone/offset | Giờ địa phương trong ngữ cảnh đã biết |
| LocalDate | Ngày lịch | Ngày sinh, ngày hiệu lực |
| LocalTime | Giờ trong ngày | Giờ mở cửa, giờ chạy tác vụ định kỳ |
| Duration | Khoảng thời gian theo giây/nanosecond | Timeout, thời lượng đã trôi qua |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | Chu kỳ lịch như một tháng |

### 2.1. Event đã xảy ra: ưu tiên Instant

Một event như thanh toán thành công, đơn hàng được tạo hoặc message được phát hành cần một thời điểm không phụ thuộc timezone của server. Instant là lựa chọn phù hợp.

Ví dụ JSON:

~~~json
{
  "eventId": "evt-901",
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

Z biểu thị UTC. Consumer ở một timezone khác có thể chuyển Instant sang giờ địa phương khi hiển thị, nhưng không thay đổi thời điểm gốc.

Không nên gửi LocalDateTime cho trường occurredAt nếu consumer không có cách xác định timezone. Một chuỗi như 2026-11-07T21:17:00 không nói đó là giờ Việt Nam hay UTC.

### 2.2. Lịch hẹn tương lai: giữ giờ địa phương và ZoneId

Một lịch hẹn lúc 09:30 tại một thành phố thường có ý nghĩa theo đồng hồ địa phương. Nếu chỉ chuyển thành offset hiện tại, hệ thống có thể mất quy tắc timezone khi lịch hẹn nằm trong tương lai.

Có thể gửi:

~~~json
{
  "appointmentId": "apt-42",
  "localDateTime": "2026-12-15T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Consumer có thể tạo ZonedDateTime từ LocalDateTime và ZoneId. Nếu nghiệp vụ cần xác nhận chính xác một instant, hãy resolve lịch hẹn và lưu thêm Instant tương ứng.

### 2.3. Offset không phải ZoneId

+07:00 là một offset cố định tại thời điểm được xét. Asia/Ho_Chi_Minh là một ZoneId trong cơ sở dữ liệu timezone IANA. ZoneId có thể chứa lịch sử và quy tắc thay đổi offset của vùng.

Nếu chỉ cần biết một event xảy ra lúc nào, Instant thường đủ. Nếu cần biết người dùng đã chọn timezone nào cho một lịch hẹn, lưu ZoneId riêng. Không thể khôi phục ZoneId từ một offset đơn lẻ.

### 2.4. DST và giờ địa phương mơ hồ

Ở vùng có Daylight Saving Time (DST), đồng hồ có thể nhảy tới hoặc lùi khỏi một khoảng thời gian:

- **Gap:** một số giờ địa phương không tồn tại khi đồng hồ nhảy tới.
- **Overlap:** một số giờ địa phương xuất hiện hai lần khi đồng hồ lùi lại.

Với lịch hẹn trong tương lai, hợp đồng cần quy định cách xử lý cả hai trường hợp. Có thể từ chối giờ không hợp lệ và yêu cầu chọn lại; hoặc dịch tới thời điểm hợp lệ tiếp theo. Với overlap, cần quy định chọn offset sớm hay muộn.

Không nên tự động dùng timezone mặc định của JVM để giải quyết gap/overlap. Producer và consumer phải cùng áp dụng một chính sách nghiệp vụ.

### 2.5. Duration và Period không thể thay thế nhau

Duration.ofDays(1) là một khoảng 24 giờ. Period.ofDays(1) là một ngày lịch. Khi cộng một ngày lịch vào ZonedDateTime qua thời điểm chuyển DST, khoảng thời gian thực tế có thể không phải 24 giờ.

Tương tự, "một tháng" là một khoảng lịch có độ dài khác nhau theo tháng, không phải một số giây cố định. Hợp đồng cần phân biệt timeout kỹ thuật với chu kỳ lịch nghiệp vụ.

## 3. Chọn format thời gian trên wire

JSON không định nghĩa kiểu date/time riêng. Hợp đồng thường dùng ISO-8601 string hoặc epoch number.

### 3.1. ISO-8601 string

Với event timestamp, chuỗi UTC dễ đọc và có offset rõ ràng:

~~~json
{
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

Nếu hợp đồng cần giữ offset nguồn, có thể gửi OffsetDateTime dạng 2026-11-07T21:17:00+07:00. Nếu cần giữ vùng địa lý, gửi thêm ZoneId như Asia/Ho_Chi_Minh.

Hãy quy định precision. Java Instant có thể chứa nanosecond; một consumer khác có thể chỉ giữ millisecond. Nếu producer gửi 9 chữ số phần thập phân nhưng consumer cắt còn 3 chữ số, dữ liệu đã thay đổi. Hợp đồng phải quyết định precision tối đa và cách truncate/round.

### 3.2. Epoch number

Epoch là số thời gian tính từ 1970-01-01T00:00:00Z. Thông dụng nhất là epoch seconds hoặc epoch milliseconds.

Tên trường cần chỉ rõ đơn vị:

~~~json
{
  "createdAtEpochMillis": 1794061020000
}
~~~

Không dùng tên mơ hồ như timestamp nếu schema không nói rõ giây hay mili giây. Instant.toEpochMilli() chỉ giữ độ chính xác đến millisecond. Nếu cần precision cao hơn, dùng ISO-8601 string hoặc quy ước số riêng.

### 3.3. Jackson và Java Time

Jackson cần module JSR-310 để xử lý các kiểu java.time. Cấu hình phổ biến để ghi thời gian thành chuỗi thay vì timestamp dạng số/mảng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Các import:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

Cấu hình này không tự biến LocalDateTime thành UTC. LocalDateTime vẫn không có timezone. Nếu hợp đồng yêu cầu instant, dùng Instant hoặc một kiểu có offset/zone phù hợp.

Không nên dựa vào timezone mặc định của JVM để parse chuỗi không có offset. Hãy quy định rõ format và ngữ nghĩa ở schema.

## 4. Locale chỉ dành cho hiển thị

Locale thay đổi cách con người đọc số, ngày tháng và tên enum. Wire format máy-to-máy phải độc lập với locale.

Ví dụ số tiền có thể hiển thị khác nhau:

| Locale | Chuỗi hiển thị |
|---|---|
| en-US | 1,234.50 |
| de-DE | 1.234,50 |
| vi-VN | 1.234,50 |

JSON number dùng dấu chấm làm dấu thập phân và không có dấu phân tách hàng nghìn:

~~~json
{
  "quantity": 1234.5
}
~~~

Không gửi 1.234,50 như một số nếu không có quy tắc parse locale rõ ràng. Cũng không dùng tên tháng hoặc enum đã dịch làm mã máy. Chỉ format theo locale ở presentation layer.

## 5. Số nguyên và độ chính xác qua nhiều ngôn ngữ

Java long có thể giữ số nguyên 64 bit. Nhưng consumer không nhất thiết có kiểu tương đương.

JavaScript Number dùng IEEE-754 binary64 và chỉ biểu diễn chính xác mọi số nguyên trong phạm vi an toàn:

\[
-(2^{53}-1) \le n \le 2^{53}-1
\]

Một ID lớn hơn giới hạn này có thể bị làm tròn nếu parse thành Number. Vì ID là giá trị định danh, thường nên gửi dưới dạng string:

~~~json
{
  "accountId": "9007199254740993"
}
~~~

Nếu trường cần phép tính số học, schema phải quy định kiểu và phạm vi. Consumer JavaScript có thể dùng BigInt hoặc thư viện phù hợp; không nên âm thầm chuyển sang Number.

Các trường số có đơn vị cũng nên ghi rõ trong tên hoặc schema, ví dụ durationMillis, sizeBytes, amountMinor. Không dùng một con số không có đơn vị rồi để từng service tự suy đoán.

## 6. Số thập phân và tiền tệ

### 6.1. Vì sao không dùng double cho tiền?

double biểu diễn số dấu phẩy động nhị phân. Một số thập phân như 0.1 không có biểu diễn nhị phân hữu hạn, nên phép tính có thể tạo sai số:

~~~java
System.out.println(0.1 + 0.2);
~~~

Output:

~~~text
0.30000000000000004
~~~

Với tiền hoặc đại lượng cần độ chính xác thập phân, dùng BigDecimal. Tạo BigDecimal từ chuỗi để giữ đúng giá trị thập phân:

~~~java
BigDecimal amount = new BigDecimal("1234.50");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate);
~~~

Tránh new BigDecimal(0.1), vì giá trị double đã xấp xỉ trước khi được chuyển sang BigDecimal.

### 6.2. Decimal string hay integer minor units?

Một hợp đồng có thể chọn decimal string:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Quy tắc string cần nói rõ: dùng dấu chấm thập phân, không có dấu nhóm, không có ký hiệu currency, scale theo nghiệp vụ và không dùng ký pháp locale.

Hoặc dùng integer minor units:

~~~json
{
  "amountMinor": 123450,
  "currency": "USD"
}
~~~

Cách này tránh số thập phân, nhưng phải xác định số chữ số minor unit của từng currency. Không mặc định mọi currency đều có hai chữ số thập phân. Ví dụ JPY thường không có minor unit, còn KWD dùng ba chữ số thập phân theo ISO 4217.

Không gửi amount mà thiếu currency. Giá trị 100 không đủ thông tin để biết đó là 100 USD, 100 JPY hay 100 đơn vị khác.

### 6.3. Scale và rounding

BigDecimal giữ scale. new BigDecimal("1.0") và new BigDecimal("1.00") có giá trị số học bằng nhau nhưng equals() trả false vì scale khác nhau; compareTo() trả 0.

Nếu scale có ý nghĩa hợp đồng, hãy giữ và validate. Nếu chỉ cần so sánh số học, dùng compareTo hoặc chuẩn hóa theo quy tắc đã định.

Khi làm tròn, chọn RoundingMode rõ ràng:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

Không tự ý chọn HALF_UP hay HALF_EVEN. Chính sách rounding có thể ảnh hưởng hóa đơn, thuế và sổ cái; phải thống nhất giữa các service.

### 6.4. JSON number và decimal string

JSON number có cú pháp thập phân, nhưng consumer có thể parse thành double. Nếu consumer phải giữ chính xác decimal qua nhiều ngôn ngữ, decimal string là lựa chọn dễ kiểm soát. Nếu dùng JSON number, hợp đồng phải yêu cầu consumer parse vào kiểu decimal chính xác như BigDecimal.

NaN và Infinity không phải JSON number hợp lệ. Hãy biểu diễn trạng thái đặc biệt bằng null, status hoặc một mã riêng theo schema.

## 7. Enum: mã wire ổn định thay vì ordinal

Enum Java có ordinal là vị trí của hằng trong khai báo. Nếu serializer gửi ordinal, thêm một hằng ở giữa có thể làm thay đổi ý nghĩa của mọi giá trị phía sau.

Ví dụ:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

Nếu PAID được gửi dưới dạng 1, việc thêm CANCELLED trước PAID có thể làm consumer cũ và mới hiểu cùng số 1 khác nhau.

Dùng string code ổn định:

~~~json
{
  "status": "paid"
}
~~~

Không dùng tên hiển thị đã dịch như "Đã thanh toán" làm wire code. Tên hằng Java có thể đổi vì refactor; label có thể đổi theo UX hoặc ngôn ngữ. Mã wire cần ổn định và có ý nghĩa nghiệp vụ.

### 7.1. Ánh xạ enum bằng Jackson

Có thể định nghĩa code độc lập với tên hằng:

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

@JsonValue chọn giá trị khi serialize; @JsonCreator định nghĩa cách chuyển wire value về enum. Có thể đổi tên hằng Java mà vẫn giữ code paid.

### 7.2. Giá trị chưa biết và forward compatibility

Consumer cũ có thể nhận enum code mới từ producer đã nâng cấp. Có ba chiến lược:

- **Strict:** từ chối message với lỗi rõ ràng. Dùng khi không biết trạng thái thì không thể xử lý an toàn.
- **Fallback:** ánh xạ về UNKNOWN hoặc UNSUPPORTED. Chỉ dùng nếu nghiệp vụ cho phép xử lý giá trị chưa biết.
- **Preserve raw value:** lưu chuỗi gốc để có thể ghi log, chuyển tiếp hoặc round-trip mà không làm mất thông tin.

Nếu chỉ ánh xạ enum lạ về UNKNOWN rồi serialize lại thành unknown, consumer đã làm mất code ban đầu. Nếu cần proxy hoặc replay event, hãy giữ raw code.

Không tái sử dụng một code cũ cho ý nghĩa mới. Nếu trạng thái nghiệp vụ thay đổi bản chất, phát hành code mới và quy định migration.

## 8. Null, trường thiếu và default

JSON phân biệt trường bị thiếu với trường có giá trị null:

~~~json
{
  "status": null
}
~~~

khác với:

~~~json
{}
~~~

Consumer có thể map cả hai về null tùy DTO và cấu hình, nhưng hợp đồng vẫn cần quy định:

- Trường bắt buộc có được phép null không?
- Trường thiếu có nghĩa là dùng default, giữ giá trị cũ hay lỗi?
- Null có nghĩa là xóa giá trị, chưa biết hay không áp dụng?
- Consumer cũ có thể bỏ qua trường mới không?
- Producer có thể ngừng gửi một trường đã phát hành không?

Không nên tự đặt default cho timezone, currency hoặc amount khi trường bị thiếu. Default sai có thể làm message hợp lệ về cú pháp nhưng sai nghiệp vụ.

Với event, trường mới thường nên được thêm theo cách optional và có quy tắc cho consumer cũ. Với command, trường bắt buộc thiếu cần được validate trước khi thực hiện side effect.

## 9. Cấu hình Jackson trong Spring Messaging và RSocket

Spring Messaging cung cấp Message và MessageConverter abstraction. Cấu hình converter phụ thuộc transport:

- Với STOMP/WebSocket, MappingJackson2MessageConverter có thể chuyển object payload sang JSON và ngược lại.
- Với RSocket, RSocketStrategies quản lý Encoder/Decoder cho data và metadata. Có thể đăng ký Jackson2JsonEncoder và Jackson2JsonDecoder dùng ObjectMapper đã cấu hình.
- Với transport khác, adapter tương ứng có thể có converter riêng. Không giả định cấu hình STOMP tự động áp dụng cho RSocket hoặc mọi broker.

Ví dụ tạo ObjectMapper có hỗ trợ Java Time và format chuỗi:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
    .build();
~~~

Đăng ký mapper vào RSocketStrategies:

~~~java
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

Dùng strategies này khi cấu hình RSocketRequester hoặc server. Producer và consumer cần thống nhất MIME type, ObjectMapper, schema và cách validate. Nếu có nhiều encoder/decoder, hãy kiểm tra thứ tự và MIME type để chắc chắn codec đúng được chọn.

Với STOMP, có thể đăng ký MappingJackson2MessageConverter trong cấu hình broker và truyền cùng ObjectMapper. Kiểm tra API cấu hình theo phiên bản Spring đang dùng, đặc biệt nếu muốn thay thế default converter hay bổ sung converter.

Trong Spring Boot, ưu tiên dependency management và cơ chế customizer/bean được phiên bản Boot hỗ trợ. Không pin Jackson version riêng một cách tùy tiện nếu BOM của dự án đã quản lý phiên bản. Tránh tạo ObjectMapper mới cho từng message; mapper nên được cấu hình và tái sử dụng.

## 10. Ví dụ Java 17: message có format rõ ràng

Ví dụ sau dùng Jackson 2, Java Time và enum wire code. Amount được gửi dưới dạng decimal string để consumer không phải parse qua floating point.

### Maven dependencies

Thêm các dependency sau trong một project Maven độc lập. Trong Spring Boot, dùng BOM tương ứng của dự án để quản lý phiên bản thay vì tự chọn version khác:

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

Lưu thành **MessageFormatDemo.java**:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.math.BigDecimal;
import java.time.Instant;

public class MessageFormatDemo {

    enum PaymentStatus {
        PENDING("pending"),
        SETTLED("settled"),
        REJECTED("rejected");

        private final String wireCode;

        PaymentStatus(String wireCode) {
            this.wireCode = wireCode;
        }

        @JsonValue
        public String wireCode() {
            return wireCode;
        }

        @JsonCreator
        public static PaymentStatus fromWireCode(String value) {
            for (PaymentStatus status : values()) {
                if (status.wireCode.equals(value)) {
                    return status;
                }
            }
            throw new IllegalArgumentException(
                "Unknown payment status: " + value
            );
        }
    }

    record PaymentMessage(
        int schemaVersion,
        String paymentId,
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

        PaymentMessage original = new PaymentMessage(
            1,
            "9007199254740993",
            Instant.parse("2026-11-07T14:17:00Z"),
            "1234.50",
            "USD",
            PaymentStatus.SETTLED
        );

        String json = mapper.writeValueAsString(original);
        PaymentMessage restored =
            mapper.readValue(json, PaymentMessage.class);

        BigDecimal amount = new BigDecimal(restored.amount());

        System.out.println(json);
        System.out.println("same-instant="
            + original.occurredAt().equals(restored.occurredAt()));
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("status=" + restored.status().wireCode());
    }
}
~~~

### Biên dịch và chạy

Với Maven, có thể dùng exec-maven-plugin để chạy class sau khi compile:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=MessageFormatDemo
~~~

Output chính xác:

~~~text
{"schemaVersion":1,"paymentId":"9007199254740993","occurredAt":"2026-11-07T14:17:00Z","amount":"1234.50","currency":"USD","status":"settled"}
same-instant=true
amount=1234.50
status=settled
~~~

Ví dụ chứng minh:

- Instant được serialize thành ISO-8601 UTC string.
- paymentId là string nên không phụ thuộc giới hạn safe integer của JavaScript.
- amount giữ scale qua decimal string.
- status dùng code settled, không dùng ordinal hoặc tên enum Java.
- Sau deserialize, các giá trị có thể được so sánh lại.

Đây là demo Jackson độc lập, không cần Spring container. Trong ứng dụng thực tế, cùng ObjectMapper có thể được dùng trong converter/codec Spring sau khi kiểm tra MIME type và cấu hình phù hợp.

## 11. Schema evolution và tương thích

Producer và consumer thường được triển khai độc lập. Một consumer cũ có thể nhận message từ producer mới; consumer mới có thể đọc message cũ đã lưu trong broker.

Các quy tắc hữu ích:

1. Thêm trường optional trước khi phụ thuộc vào nó.
2. Quy định default khi đọc message cũ thiếu trường mới.
3. Không đổi kiểu wire của trường đang được sử dụng.
4. Không đổi đơn vị hoặc precision của trường tại chỗ.
5. Không đổi enum code đã phát hành.
6. Không tái sử dụng enum code cũ cho ý nghĩa mới.
7. Với thay đổi không tương thích, phát hành schemaVersion mới hoặc field mới.
8. Giữ consumer có thể đọc các version còn nằm trong thời hạn hỗ trợ.
9. Kiểm thử producer mới với consumer cũ và consumer mới với payload cũ.

Ví dụ nếu occurredAt trước đây là epoch milliseconds nhưng muốn đổi sang ISO string, không đổi kiểu ngay trên cùng field nếu consumer cũ còn hoạt động. Có thể phát hành occurredAtIso, đọc cả hai trong giai đoạn chuyển tiếp, rồi ngừng trường cũ theo lịch đã thống nhất.

## 12. Contract test và golden payload

Test serializer/deserializer nội bộ chỉ chứng minh một phiên bản code đọc được chính dữ liệu do chính nó ghi. Nó chưa chứng minh producer và consumer khác phiên bản vẫn hiểu nhau.

Nên lưu một số golden payload trong test resources và kiểm tra:

- Payload cũ được deserialize bởi consumer mới.
- Payload mới vẫn chứa đúng wire code và format.
- Trường thiếu/null được xử lý theo schema.
- Enum code lạ tuân theo strict/fallback/preserve policy.
- Instant không bị đổi timezone hoặc precision ngoài quy định.
- Decimal string không bị đổi scale hoặc parse qua double.
- Long ID giữ nguyên từng chữ số.
- JSON number không chứa NaN/Infinity.
- Message MIME type và codec thực tế được chọn đúng trong integration test.

Nếu message được ký số hoặc hash toàn bộ byte, cần thêm canonicalization: UTF-8, quy tắc escape, cách biểu diễn số và thứ tự property. JSON object không nên được xem là có thứ tự trường mang ý nghĩa nếu hợp đồng không quy định canonical form.

## 13. Lỗi thường gặp

- Dùng LocalDateTime cho thời điểm event và dựa vào timezone server.
- Chỉ gửi UTC offset nhưng cần khôi phục ZoneId.
- Dùng epoch không ghi rõ seconds hay milliseconds.
- Mất nanosecond khi một consumer chỉ giữ millisecond mà không có quy tắc precision.
- Format số theo locale trước khi serialize.
- Dùng double cho tiền hoặc phép tính decimal chính xác.
- Gửi long ID dưới dạng JSON number cho consumer JavaScript.
- Gửi BigDecimal dưới dạng JSON number nhưng consumer parse thành floating point.
- Không gửi currency cùng amount.
- Dùng enum ordinal hoặc tên label đã dịch làm wire value.
- Không có chính sách khi consumer nhận enum code mới.
- Đổi tên, đổi đơn vị hoặc đổi kiểu trường mà không migration.
- Dựa vào default timezone, locale hoặc ObjectMapper cấu hình ngầm của từng môi trường.
- Chỉ kiểm tra round-trip trong cùng một phiên bản producer/consumer.

## 14. Checklist phát hành hợp đồng

- [ ] Trường thời gian phân biệt rõ instant, local date/time và lịch theo vùng.
- [ ] Event timestamp dùng UTC ISO-8601 hoặc epoch có đơn vị được ghi rõ.
- [ ] ZoneId được giữ nếu nghiệp vụ cần lịch địa phương/DST.
- [ ] Precision thời gian và quy tắc truncate/round đã thống nhất.
- [ ] Locale không làm thay đổi wire representation.
- [ ] ID lớn có biểu diễn an toàn qua mọi consumer.
- [ ] Số thập phân có precision, scale và rounding policy.
- [ ] Tiền luôn đi cùng currency và quy tắc minor unit.
- [ ] Enum dùng code ổn định, có unknown-value policy.
- [ ] Null, trường thiếu và default có ngữ nghĩa rõ.
- [ ] Spring converter/codec dùng đúng ObjectMapper và MIME type.
- [ ] Có golden payload và contract test giữa các version.
- [ ] Breaking change có version/migration plan.

## Kết luận

Một message chỉ đáng tin cậy khi producer và consumer thống nhất không chỉ kiểu dữ liệu mà cả ý nghĩa của nó. Hãy dùng Instant cho event time, ZoneId cho lịch địa phương, format số độc lập locale, decimal chính xác cho tiền và enum code ổn định. Jackson và Spring Messaging cung cấp công cụ chuyển đổi; tính tương thích lâu dài vẫn phụ thuộc vào schema, validation và quy trình evolution mà hệ thống quy định.

## Tài liệu tham khảo

- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/messaging.html)
- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Jackson Datatype JSR-310](https://github.com/FasterXML/jackson-modules-java8/tree/2.17/datetime)
- [Java 17 Date-Time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [JSON Data Interchange Syntax (RFC 8259)](https://www.rfc-editor.org/rfc/rfc8259)
- [IANA Time Zone Database](https://www.iana.org/time-zones)
