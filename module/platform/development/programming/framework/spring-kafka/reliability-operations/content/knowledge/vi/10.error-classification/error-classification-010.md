# Lỗi do dữ liệu độc hại trong Spring Kafka

Trong hệ thống Kafka, dữ liệu đầu vào có thể đến từ producer lỗi, phiên bản ứng dụng không tương thích, hệ thống tích hợp bên ngoài hoặc một nguồn đã bị xâm nhập. Một record không hợp lệ có thể làm listener ném exception, khiến consumer đọc lại cùng offset nhiều lần, giữ partition không tiến lên hoặc làm tăng tải toàn hệ thống. Dữ liệu được tạo có chủ ý để khai thác điểm yếu của consumer còn có thể gây lỗi bảo mật như injection, lộ thông tin nhạy cảm hoặc tiêu thụ tài nguyên quá mức.

Trong chương phân loại lỗi của Spring Kafka, cần nhận diện **lỗi do dữ liệu độc hại** như một nhóm lỗi đầu vào có thể tái diễn mỗi lần đọc. Cách xử lý thường là xác thực dữ liệu, phân loại lỗi không thể phục hồi, chuyển record sang dead-letter topic (DLT) hoặc vùng quarantine, ghi nhận đủ thông tin để điều tra và bảo vệ consumer khỏi xử lý không giới hạn.

Một record độc hại thường không tự biến thành hợp lệ sau vài lần retry. Vì vậy, retry phải được dùng cho lỗi tạm thời; lỗi cấu trúc, kiểu dữ liệu hoặc quy tắc nghiệp vụ cố định cần được xử lý theo luồng phục hồi riêng.

## 1. Dữ liệu độc hại trong luồng Kafka là gì?

Kafka broker lưu record gồm key, value, timestamp và headers. Broker không hiểu đầy đủ ý nghĩa nghiệp vụ của payload. Việc giải mã, chuyển đổi kiểu, xác thực và thực thi nghiệp vụ thường diễn ra ở consumer.

Một record có thể gây hại theo nhiều cách:

| Nhóm dữ liệu | Ví dụ | Tác động có thể xảy ra |
|---|---|---|
| Payload sai định dạng | JSON bị cắt, thiếu dấu ngoặc, encoding sai | Deserialization exception |
| Schema không tương thích | Trường bắt buộc bị thiếu, kiểu field thay đổi | Conversion hoặc validation failure |
| Giá trị ngoài miền hợp lệ | Số tiền âm, ngày hết hạn sai, trạng thái không tồn tại | Lỗi nghiệp vụ hoặc dữ liệu sai |
| Payload quá lớn | Chuỗi, mảng hoặc blob vượt giới hạn | Tốn bộ nhớ, tăng latency hoặc vượt giới hạn broker/client |
| Dữ liệu lồng sâu hoặc phức tạp | Cấu trúc JSON/XML nhiều tầng, số phần tử quá lớn | CPU/memory tăng, parser chậm |
| Header không đáng tin | Type header, tenant ID hoặc routing header giả mạo | Sai kiểu deserialize hoặc định tuyến sai |
| Chuỗi có nội dung nguy hiểm | Nội dung được nối vào SQL, shell, log hoặc HTML | Injection, log forging hoặc XSS ở hệ thống downstream |
| URL hoặc đường dẫn do nguồn gửi | URL nội bộ, path không được phép | SSRF hoặc path traversal nếu consumer sử dụng trực tiếp |
| Dữ liệu nhạy cảm | Token, mật khẩu, thông tin cá nhân | Lộ dữ liệu qua log, DLT hoặc công cụ replay |

Không phải mọi record sai đều là tấn công. Một producer cũ có thể gửi schema cũ hoặc một dịch vụ có bug có thể phát dữ liệu không hợp lệ. Tuy vậy, consumer cần coi dữ liệu từ Kafka là input cần kiểm tra, kể cả khi topic chỉ được ghi bởi các producer nội bộ.

## 2. Poison pill và vì sao partition có thể bị kẹt

**Poison pill** là record mà consumer không thể xử lý thành công lặp đi lặp lại. Ví dụ, một payload không deserialize được hoặc một giá trị luôn vi phạm validation. Nếu consumer retry cùng record mà không có cách recovery, offset có thể không tiến lên.

~~~text
Consumer poll()
      |
      v
Record offset 120
      |
      v
Deserialize / validate
      |
      +--> thất bại
              |
              v
        Error handler
              |
              +--> retry record 120
              |       |
              |       v
              |   vẫn thất bại
              |       |
              |       +----> retry tiếp
              |
              +--> hết retry
                      |
                      v
                 DLT / quarantine
                      |
                      v
              recovery thành công
                      |
                      v
             commit offset theo policy
                      |
                      v
               tiếp tục record sau
~~~

Với blocking retry, record lỗi có thể giữ partition chờ cho đến khi retry hoặc recovery hoàn tất. Điều này giúp giữ thứ tự trong partition nhưng có thể làm các record phía sau bị chặn.

Nếu lỗi là do payload cố định, retry thêm không làm dữ liệu thay đổi. Consumer có thể liên tục tiêu thụ CPU, tạo log dày đặc và làm consumer lag tăng. Khi có nhiều partition cùng chứa poison pill, toàn bộ consumer group có thể suy giảm đáng kể.

Cần phân biệt poison pill với lỗi dependency tạm thời. Database mất kết nối trong vài giây có thể phục hồi khi retry. JSON sai cú pháp sẽ vẫn sai khi gửi lại cùng bytes.

## 3. Những giai đoạn consumer có thể gặp lỗi dữ liệu

Dữ liệu có thể thất bại trước, trong hoặc sau khi listener được gọi.

~~~text
Kafka record bytes
      |
      v
Key/value deserializer
      |
      +--> lỗi deserialize
      |       |
      |       v
      |  ErrorHandlingDeserializer
      |
      v
Message conversion / type mapping
      |
      +--> lỗi convert hoặc resolve method argument
      |
      v
Bean validation / domain validation
      |
      +--> dữ liệu không hợp lệ
      |
      v
Business logic
      |
      +--> lỗi quy tắc nghiệp vụ hoặc dependency
      |
      v
Database / HTTP / downstream system
~~~

Các lớp lỗi khác nhau cần cách xử lý khác nhau:

- **Deserialization:** bytes không thể chuyển thành key/value hoặc object.
- **Message conversion:** object có thể đã deserialize nhưng không chuyển được sang kiểu tham số listener.
- **Validation:** object đúng cú pháp nhưng vi phạm constraint hoặc schema nghiệp vụ.
- **Business rule:** object hợp lệ về cấu trúc nhưng không hợp lệ theo trạng thái nghiệp vụ.
- **Downstream failure:** dữ liệu hợp lệ nhưng database hoặc dịch vụ bên ngoài đang lỗi.

Không nên gộp tất cả vào một exception chung rồi retry theo cùng một lịch. Hãy giữ nguyên nguyên nhân gốc và phân loại rõ lỗi có thể phục hồi hay không.

## 4. ErrorHandlingDeserializer để xử lý lỗi deserialize

Một vấn đề quan trọng là deserializer thông thường có thể ném exception ngay trong quá trình consumer poll. Khi đó, listener chưa được gọi và logic bắt exception bên trong method @KafkaListener không thể xử lý record đó.

Spring Kafka cung cấp **ErrorHandlingDeserializer** để bọc deserializer thực tế. Khi delegate deserializer thất bại, wrapper lưu thông tin exception vào header của record và cho phép container error handler xử lý.

Ví dụ cấu hình JSON consumer trong Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

Trong ví dụ:

- ErrorHandlingDeserializer bọc deserializer cho key và value.
- StringDeserializer xử lý key.
- JsonDeserializer chuyển value thành OrderCreated.
- Default type và trusted package cần khớp với model thực tế của ứng dụng.
- Trusted packages nên được giới hạn vào package của các kiểu event được phép.

Nếu dùng application.properties:

~~~properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
~~~

Tên property và cách bind cần được đối chiếu với phiên bản Spring Boot/Spring Kafka đang sử dụng. Nếu ứng dụng có nhiều loại event, hãy dùng type mapping rõ ràng hoặc cấu hình consumer theo contract cụ thể thay vì tin mọi class name trong header.

### Xử lý record deserialize thất bại

Khi deserialization thất bại, listener có thể không nhận được object hợp lệ. ErrorHandlingDeserializer đặt exception metadata trong header; error handler và recoverer có thể dùng thông tin này để chuyển record sang DLT.

Cần lưu ý:

- Value của record lỗi có thể không phải object domain; tùy trường hợp, dữ liệu gốc có thể được giữ dưới dạng bytes trong metadata hoặc header.
- DLT publisher cần serializer tương thích với cả payload đã deserialize và payload gốc dạng byte[].
- Không giả định listener có thể đọc object bị lỗi hoặc gọi getter trên payload null.
- Khi điều tra, giữ topic, partition, offset, timestamp, key và exception type.
- Không log toàn bộ raw payload nếu có thể chứa bí mật hoặc dữ liệu cá nhân.

## 5. Xác thực schema và quy tắc nghiệp vụ

Deserialization thành công chỉ chứng minh bytes có thể chuyển thành một kiểu object. Nó không chứng minh record hợp lệ về nghiệp vụ.

Ví dụ một event OrderCreated có thể cần:

- eventId không rỗng và có định dạng được chấp nhận.
- orderId hợp lệ.
- amount lớn hơn hoặc bằng 0 theo quy tắc nghiệp vụ.
- currency nằm trong danh sách được hỗ trợ.
- createdAt có định dạng và khoảng thời gian hợp lý.
- Các trường bắt buộc có mặt.
- Kích thước chuỗi và số phần tử nằm trong giới hạn.

Có thể dùng Jakarta Bean Validation trong listener service:

~~~java
@Service
public class OrderEventValidator {

    private final Validator validator;

    public OrderEventValidator(Validator validator) {
        this.validator = validator;
    }

    public void validate(OrderCreated event) {
        Set<ConstraintViolation<OrderCreated>> violations =
                validator.validate(event);

        if (!violations.isEmpty()) {
            throw new InvalidEventException(
                    "OrderCreated violates event constraints"
            );
        }
    }
}
~~~

Exception InvalidEventException đại diện lỗi dữ liệu cố định, không nên retry cùng payload liên tục. Trong hệ thống thực tế, có thể lưu danh sách tên field và mã lỗi validation vào metadata quarantine. Tránh đưa giá trị field nhạy cảm vào exception message.

Nếu dùng schema registry với Avro, Protobuf hoặc JSON Schema, hãy thiết lập schema compatibility phù hợp giữa producer và consumer. Schema compatibility giúp kiểm soát thay đổi cấu trúc, nhưng không thay thế validation nghiệp vụ như amount, quyền sở hữu hoặc trạng thái đơn hàng.

### Phân biệt schema validation và business validation

| Kiểm tra | Ví dụ | Lỗi được phát hiện |
|---|---|---|
| Syntax | JSON hợp lệ, bytes đúng encoding | Payload không đọc được |
| Schema | Field có đúng kiểu và bắt buộc không | Contract không tương thích |
| Domain validation | Amount trong giới hạn, currency hợp lệ | Giá trị ngoài miền nghiệp vụ |
| Authorization | Event có thuộc tenant hoặc nguồn được phép không | Nguồn gửi không có quyền thực hiện |
| State transition | Đơn hàng có thể chuyển từ trạng thái hiện tại sang trạng thái mới không | Event không phù hợp trạng thái hệ thống |

Một event có schema đúng vẫn có thể là dữ liệu độc hại nếu cố tình gửi tenant ID của người khác, URL nội bộ hoặc một trạng thái không được phép. Consumer phải xác thực cả danh tính nguồn và quyền của hành động.

## 6. Không tin type header và dữ liệu điều khiển từ producer

Spring Kafka JsonDeserializer có thể sử dụng type information từ header để xác định class đích. Header do producer gửi có thể bị giả mạo nếu producer có quyền ghi topic hoặc có một nguồn dữ liệu không đáng tin đi vào pipeline.

Các nguyên tắc an toàn:

- Chỉ cho phép các package/class event đã được ứng dụng định nghĩa.
- Dùng type mapping rõ ràng cho các event contract được hỗ trợ.
- Không dùng wildcard trusted package rộng trong môi trường production nếu không cần thiết.
- Cân nhắc tắt sử dụng type header và cấu hình default type cụ thể khi topic chỉ mang một loại event.
- Không deserialize Java native object từ nguồn không tin cậy.
- Không cho payload quyết định class tùy ý được khởi tạo.
- Version hóa event contract và kiểm soát schema evolution.

Nếu topic chứa nhiều loại event, hãy dùng discriminator có danh sách allowlist, rồi map từng giá trị sang kiểu domain cụ thể. Không dùng tên class tự do từ payload làm cơ chế chọn kiểu.

## 7. Injection và dữ liệu có thể gây tác động downstream

Một payload có thể deserialize và validate cấu trúc thành công nhưng vẫn chứa chuỗi nguy hiểm đối với hệ thống đích. Rủi ro phụ thuộc vào cách consumer sử dụng field.

| Nơi sử dụng dữ liệu | Rủi ro | Biện pháp phòng vệ |
|---|---|---|
| SQL query | SQL injection | Prepared statement/parameterized query |
| Shell/process invocation | Command injection | Tránh gọi shell; dùng API có tham số riêng và allowlist |
| Log | Log forging, lộ bí mật | Sanitize CR/LF, cấu trúc log, không log secret |
| HTML/UI | Cross-site scripting ở dashboard hoặc portal | Output encoding tại nơi render |
| URL fetch | SSRF | Allowlist scheme/host, chặn địa chỉ nội bộ, kiểm soát redirect và DNS |
| File path | Path traversal | Chuẩn hóa path, giới hạn thư mục gốc, không tin filename |
| Regex/parser | ReDoS hoặc parser quá tải | Giới hạn kích thước/độ phức tạp, dùng parser an toàn |
| Tenant/account routing | Truy cập chéo tenant | Kiểm tra quyền bằng danh tính đã xác thực, không tin tenant ID trong payload |

Ví dụ truy vấn database nên dùng parameter binding:

~~~java
jdbcTemplate.update(
        "update orders set status = ? where order_id = ?",
        event.status(),
        event.orderId()
);
~~~

Không ghép chuỗi từ event vào câu SQL:

~~~java
// Không an toàn: dữ liệu từ event được nối trực tiếp vào câu truy vấn.
String sql = "update orders set status = '" + event.status()
        + "' where order_id = '" + event.orderId() + "'";
statement.execute(sql);
~~~

Nếu consumer lấy URL từ event để gọi dịch vụ, hãy kiểm tra host và scheme bằng allowlist, chặn truy cập tới metadata endpoint hoặc mạng nội bộ không được phép, kiểm soát redirect và không dựa vào một lần kiểm tra DNS duy nhất. Tốt nhất, event chỉ nên mang một identifier nghiệp vụ; ứng dụng tự tra cứu endpoint tin cậy từ cấu hình.

## 8. Giới hạn kích thước và độ phức tạp của payload

Payload lớn hoặc cấu trúc quá phức tạp có thể làm consumer tốn nhiều heap, CPU và thời gian deserialize. Một nguồn gửi nhiều record nặng có thể làm consumer lag tăng hoặc gây OutOfMemoryError.

Nên giới hạn ở nhiều lớp:

1. **Producer contract:** quy định kích thước payload và số phần tử tối đa.
2. **Broker/topic:** cấu hình message size phù hợp và quota cho principal nếu cần.
3. **Consumer fetch:** cấu hình fetch limits tương thích với message size hợp lệ.
4. **Deserializer/parser:** giới hạn độ sâu, số token, độ dài chuỗi và thời gian xử lý nếu thư viện hỗ trợ.
5. **Domain validation:** từ chối số phần tử, số lượng hoặc độ dài field vượt ngưỡng nghiệp vụ.
6. **Concurrency/backpressure:** giới hạn số record/batch đang được xử lý cùng lúc.

Các giới hạn broker và client cần tương thích. Ví dụ, một record hợp lệ theo broker nhưng lớn hơn khả năng xử lý của consumer vẫn có thể làm consumer gặp vấn đề. Ngược lại, giảm fetch limit tùy tiện có thể khiến consumer không đọc được message hợp lệ lớn nhất.

Không nên chỉ tăng heap hoặc message size để làm lỗi biến mất. Hãy đo kích thước thực tế, đặt giới hạn theo use case và chuyển payload lớn sang object storage có quyền truy cập kiểm soát nếu phù hợp.

## 9. Phân loại lỗi: retry hay không retry?

Lỗi do dữ liệu độc hại hoặc không hợp lệ thường là **non-retryable** đối với cùng payload. Lỗi hạ tầng có thể retry.

| Tình huống | Phân loại thường dùng | Hành động |
|---|---|---|
| JSON sai cú pháp | Non-retryable | DLT/quarantine và ghi metadata |
| Field bắt buộc thiếu | Non-retryable | DLT, sửa producer/contract |
| Giá trị vượt giới hạn cố định | Non-retryable | DLT hoặc reject theo nghiệp vụ |
| Type header không nằm trong allowlist | Non-retryable/security event | Quarantine, cảnh báo |
| Tenant hoặc actor không có quyền | Non-retryable/security event | Reject, audit, cảnh báo |
| Database tạm mất kết nối | Retryable | Backoff có giới hạn |
| Broker/network tạm lỗi khi publish DLT | Retryable | Retry recovery theo chính sách, không commit record nguồn quá sớm |
| Schema registry tạm không truy cập được | Có thể retry | Giới hạn retry và deadline |
| Consumer bị thiếu cấu hình cố định | Cần khắc phục cấu hình | Cảnh báo; tránh retry vô hạn record |

Không nên phân loại chỉ dựa trên class exception nếu cùng class được dùng cho cả lỗi tạm thời và lỗi dữ liệu. Dùng exception domain rõ ràng hoặc error code ổn định.

## 10. Cấu hình DefaultErrorHandler để đưa dữ liệu lỗi vào DLT

Với record listener, DefaultErrorHandler có thể retry các lỗi được phép, rồi gọi recoverer khi hết retry. Với dữ liệu không hợp lệ, có thể đánh dấu exception domain là non-retryable để chuyển sang DLT ngay.

~~~java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class,
                UnauthorizedEventException.class
        );

        return handler;
    }
}
~~~

Ví dụ trên có hai lần retry với backoff một giây cho các lỗi retryable. InvalidEventException và UnauthorizedEventException được chuyển sang recovery mà không retry lặp. Cần đăng ký handler vào listener container factory thực tế.

Spring Kafka có phân loại mặc định cho một số lỗi không thể retry, trong đó có các lỗi deserialization/conversion phổ biến. Hãy kiểm tra default classification theo phiên bản đang dùng và bổ sung exception nghiệp vụ của ứng dụng một cách tường minh.

### Chọn DLT topic và partition

DeadLetterPublishingRecoverer mặc định thường định tuyến record tới topic nguồn với hậu tố .DLT và giữ partition tương ứng nếu cấu hình phù hợp. Nếu định tuyến cùng partition, DLT cần có đủ số partition tương ứng với topic nguồn. Có thể dùng destination resolver để chuyển các loại lỗi tới topic quarantine khác nhau.

~~~text
orders
   |
   +--> JSON không hợp lệ ------> orders.DLT
   |
   +--> Unauthorized event ----> security-quarantine
   |
   +--> Lỗi tạm thời
             |
             +--> retry có giới hạn
~~~

Nếu publish DLT thất bại, recovery chưa hoàn tất. Cần cấu hình và kiểm tra hành vi lỗi của recoverer để container không commit offset nguồn trong khi record chưa được lưu an toàn vào DLT. Theo dõi DLT publish result, exception và số record recovery thất bại.

### Serializer cho DLT

DLT có thể nhận record đã deserialize thành object hoặc record không deserialize được. Trong trường hợp lỗi deserialize, dữ liệu gốc có thể được giữ ở dạng byte[]. Vì vậy, DLT producer cần serializer có thể xử lý các loại payload tương ứng, ví dụ byte[] và domain object, hoặc dùng template riêng cho từng loại. Không giả định một JsonSerializer cho object sẽ luôn xử lý đúng raw bytes.

Cũng cần giữ metadata lỗi trong headers, nhưng kiểm soát kích thước và loại dữ liệu lưu trong header. Không đưa stack trace quá lớn hoặc bí mật vào header một cách tùy tiện.

## 11. DLT và quarantine phải được vận hành an toàn

DLT không phải thùng rác để đẩy mọi record lỗi vào rồi quên đi. Nó là vùng lưu dữ liệu cần điều tra hoặc phục hồi.

Một quy trình vận hành nên có:

- **Retention:** thời gian lưu phù hợp với thời gian điều tra và yêu cầu pháp lý.
- **Access control:** chỉ service/operator được phép đọc và phát lại.
- **Encryption:** bảo vệ dữ liệu khi lưu và truyền.
- **Monitoring:** cảnh báo khi DLT tăng nhanh hoặc có record thuộc nhóm security violation.
- **Metadata:** lưu topic nguồn, partition, offset, timestamp, exception class, error code và event ID.
- **Replay approval:** kiểm tra và sửa nguyên nhân trước khi phát lại.
- **Idempotency:** consumer nhận lại event cần chịu được replay.
- **Audit:** ghi nhận ai đã xem, sửa hoặc phát lại record khi dữ liệu nhạy cảm.

Nếu record chứa token, password, personal data hoặc secret, DLT có thể trở thành nơi lưu dữ liệu nhạy cảm lâu hơn topic chính. Hạn chế quyền truy cập, không log payload thô và áp dụng retention/data deletion phù hợp.

Không nên tự động replay tất cả record từ DLT vào topic gốc. Một record không hợp lệ có thể lại trở thành poison pill; một event không có quyền có thể kích hoạt lại hành động bị cấm.

## 12. Bảo vệ log và thông tin chẩn đoán

Khi log lỗi, đừng ghi nguyên payload hoặc toàn bộ headers một cách mặc định. Dữ liệu độc hại có thể chứa ký tự điều khiển, newline, dữ liệu cá nhân hoặc secret.

Nên log các trường có cấu trúc:

~~~text
event_id=evt-123
topic=orders
partition=2
offset=12045
error_code=INVALID_ORDER_AMOUNT
exception=InvalidEventException
action=QUARANTINE
~~~

Các nguyên tắc:

- Sanitize ký tự CR/LF và ký tự điều khiển nếu log sink không tự xử lý.
- Giới hạn độ dài trường log.
- Không ghi token, password, authorization header hoặc dữ liệu cá nhân không cần thiết.
- Ghi event ID và vị trí Kafka để có thể truy vết record.
- Lưu exception class và error code; stack trace chỉ ghi ở mức cần thiết.
- Tách log security event khỏi log nghiệp vụ nếu quy trình vận hành yêu cầu.

Không dùng dữ liệu từ record làm tên logger, tên file, metric label hoặc tag có cardinality không giới hạn. Một producer độc hại có thể tạo vô số event ID khác nhau và làm hệ thống monitoring quá tải.

## 13. Schema evolution và hợp đồng event

Một phần đáng kể lỗi dữ liệu xuất phát từ producer và consumer không đồng bộ phiên bản. Ví dụ, producer thêm field bắt buộc nhưng consumer cũ không biết cách xử lý; hoặc producer đổi kiểu field từ số sang chuỗi.

Để giảm lỗi:

- Version hóa event contract.
- Xác định field bắt buộc, optional và default rõ ràng.
- Dùng schema compatibility policy phù hợp với cách triển khai producer/consumer.
- Thêm field theo hướng tương thích khi có thể.
- Không đổi ý nghĩa field mà giữ nguyên tên.
- Kiểm thử producer mới với consumer cũ và ngược lại.
- Có quy trình deprecate và loại bỏ field.
- Gắn schema version hoặc event type theo một contract được kiểm soát.

Schema registry giúp kiểm soát schema và compatibility nhưng không xác thực quyền của actor, tenant hoặc tính hợp lệ của trạng thái nghiệp vụ. Những kiểm tra đó vẫn thuộc consumer/domain layer.

## 14. Kiểm soát nguồn gửi và quyền truy cập topic

Dữ liệu độc hại có thể xuất phát từ principal có quyền ghi topic nhưng bị xâm nhập hoặc cấu hình sai. Chỉ dùng TLS hoặc SASL không làm payload tự động đáng tin cậy.

Các biện pháp phòng vệ:

- Cấp ACL tối thiểu: producer chỉ được ghi vào topic cần thiết.
- Tách principal giữa producer, consumer, operator và service replay.
- Dùng TLS để bảo vệ dữ liệu trên đường truyền.
- Dùng SASL hoặc cơ chế xác thực phù hợp để xác định principal.
- Giới hạn quota và tốc độ gửi theo principal/topic nếu cần.
- Theo dõi thay đổi ACL, credential và nguồn phát bất thường.
- Không cho mọi service quyền ghi vào mọi topic.
- Xác thực quyền của event ở domain service; không coi Kafka ACL là authorization cho từng hành động nghiệp vụ.

Nếu một event mang tenant ID hoặc actor ID, không tin giá trị đó chỉ vì nó nằm trong payload. Hãy kiểm tra nó có phù hợp với principal, signature hoặc nguồn đã xác thực theo mô hình bảo mật của hệ thống hay không.

## 15. Batch listener và dữ liệu độc hại

Với batch listener, một poll có thể trả nhiều record. Một record độc hại có thể làm cả callback thất bại nếu listener không xác định được vị trí record gây lỗi.

Nếu có thể xác định index lỗi, ném BatchListenerFailedException để error handler xử lý đúng record:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        try {
            orderValidator.validate(records.get(index).value());
            orderService.process(records.get(index).value());
        }
        catch (InvalidEventException ex) {
            throw new BatchListenerFailedException(
                    "Invalid event in batch",
                    ex,
                    index
            );
        }
    }
}
~~~

Nếu listener không chỉ ra record lỗi, error handler có thể phải retry toàn batch hoặc áp dụng recovery cho nhiều record hơn cần thiết. Các record hợp lệ đã xử lý trước đó có thể được xử lý lại. Hãy thiết kế idempotency cho batch và kiểm tra hành vi của error handler theo phiên bản Spring Kafka.

Nếu nhiều record cùng lỗi do một schema change, cân nhắc dừng consumer có kiểm soát và cảnh báo thay vì để mọi partition liên tục gửi record vào DLT mà không có kế hoạch xử lý.

## 16. Backpressure và bảo vệ consumer khỏi dữ liệu gây quá tải

Một nguồn gửi record quá lớn hoặc quá nhanh có thể khiến consumer không theo kịp. Retry và logging quá nhiều còn làm tăng tải.

Các biện pháp:

- Giới hạn payload size, array length, string length và nesting depth.
- Giới hạn số record trong mỗi poll/batch theo bộ nhớ và thời gian xử lý.
- Giới hạn concurrency theo năng lực CPU, heap và dependency.
- Pause/resume hoặc giảm tốc độ lấy việc khi downstream quá tải.
- Dùng quota/rate limit ở producer hoặc gateway.
- Đặt deadline cho validation và downstream calls.
- Dùng bounded executor/queue thay vì hàng đợi vô hạn.
- Theo dõi heap, GC pause, listener latency và consumer lag.
- Cảnh báo khi cùng một error code tăng đột biến.

Nếu listener xử lý một record mất quá lâu, consumer có thể vượt max.poll.interval.ms và bị rebalance. Tăng poll interval có thể giúp xử lý workload dài hơn trong một số trường hợp, nhưng không giải quyết parser tiêu thụ CPU vô hạn hoặc payload cố ý làm cạn bộ nhớ.

## 17. Các tình huống vận hành thường gặp

### JSON không hợp lệ làm listener không được gọi

Kiểm tra consumer có dùng ErrorHandlingDeserializer hay không. Nếu chỉ dùng JsonDeserializer trực tiếp, exception có thể xảy ra trong poll trước khi listener method chạy. Bọc delegate deserializer bằng ErrorHandlingDeserializer để container error handler có thể xử lý lỗi.

### Cùng một offset bị retry liên tục

Kiểm tra exception gốc và classification của DefaultErrorHandler. Nếu lỗi do payload cố định, đánh dấu non-retryable và chuyển DLT/quarantine. Xác nhận recovery thành công trước khi offset nguồn được commit.

### DLT publish thất bại

Kiểm tra broker, ACL, serializer, topic tồn tại, partition count và kết quả send. Không đánh dấu record nguồn đã recovery nếu DLT record chưa được lưu an toàn. Cảnh báo riêng cho lỗi publish DLT.

### Payload lớn làm consumer thiếu bộ nhớ

Đo kích thước record và heap. Đặt giới hạn ở producer, broker và consumer; xem xét lưu file/object lớn ở object storage rồi chỉ gửi reference có quyền truy cập kiểm soát qua Kafka.

### Consumer xử lý được JSON nhưng dữ liệu gây SQL lỗi

Kiểm tra validation và cách truy vấn. Dùng parameterized query, không nối chuỗi từ payload. Phân loại lỗi dữ liệu không retryable và lưu metadata cần thiết để sửa producer/contract.

### DLT chứa dữ liệu nhạy cảm

Giới hạn ACL, encryption, retention và quyền replay. Không log payload hoặc headers thô. Áp dụng quy trình xóa dữ liệu theo chính sách lưu trữ.

### Một tenant gửi event thuộc tenant khác

Không tin tenant ID trong payload. Kiểm tra danh tính nguồn và quyền của actor/tenant trước khi thực hiện side effect. Ghi security event có event ID và vị trí Kafka, không đưa dữ liệu nhạy cảm vào log.

## 18. Theo dõi lỗi dữ liệu và cảnh báo

Các chỉ số nên quan sát:

| Metric/tín hiệu | Ý nghĩa |
|---|---|
| Deserialization failure count | Số record không giải mã được |
| Validation failure count | Số record vi phạm contract/domain rule |
| Non-retryable exception count | Số lỗi được phân loại không retry |
| DLT publish rate | Tốc độ chuyển record sang DLT |
| DLT backlog/oldest age | Record lỗi tồn đọng lâu |
| Retry count theo error class | Phân biệt lỗi tạm thời và lỗi cố định |
| Consumer lag | Partition bị chậm hoặc bị poison pill giữ lại |
| Listener processing latency | Phát hiện payload gây xử lý chậm |
| Record size distribution | Phát hiện payload bất thường |
| Heap/GC/CPU | Phát hiện áp lực tài nguyên |
| Security rejection count | Số event bị từ chối do nguồn/actor/tenant không hợp lệ |

Tránh dùng event ID, raw key hoặc tenant ID tùy ý làm metric label nếu cardinality có thể tăng không giới hạn. Hãy dùng error code, topic, consumer group và các dimension có tập giá trị hữu hạn.

Một số cảnh báo hữu ích:

- Deserialization failures tăng đột ngột sau khi producer deploy.
- Một partition có lag tăng trong khi các partition khác bình thường.
- DLT publish thất bại.
- Một principal gửi record vượt kích thước hoặc tần suất bất thường.
- Tỷ lệ validation failure vượt ngưỡng.
- Consumer heap/GC tăng cùng lúc với payload size.
- Security rejection tăng hoặc có nhiều event từ tenant không hợp lệ.

## 19. Quy trình xử lý một record độc hại

Khi phát hiện record lỗi, có thể đi theo quy trình:

1. **Xác định vị trí:** topic, partition, offset, timestamp, key và event ID.
2. **Phân loại lỗi:** deserialize, conversion, schema, domain validation, authorization hay downstream.
3. **Quyết định retry:** chỉ retry nếu lỗi có thể thay đổi theo thời gian và còn trong deadline.
4. **Quarantine:** chuyển record không retryable sang DLT hoặc topic cách ly.
5. **Bảo vệ dữ liệu:** hạn chế payload thô trong log, kiểm soát quyền truy cập DLT.
6. **Điều tra nguồn:** xác định producer version, principal, schema version và lịch sử deploy.
7. **Khắc phục:** sửa producer/contract hoặc cập nhật dữ liệu theo quy trình được phê duyệt.
8. **Replay có kiểm soát:** xác thực lại record, giữ event ID và bảo đảm consumer idempotent.
9. **Theo dõi sau phục hồi:** kiểm tra lag, DLT backlog và tỷ lệ lỗi có giảm hay không.

Không sửa trực tiếp offset để bỏ qua record mà không có quyết định nghiệp vụ và audit. Việc skip có thể làm mất một sự kiện quan trọng và khiến hệ thống downstream không thể tái dựng trạng thái.

## 20. Checklist bảo vệ Spring Kafka consumer

- Consumer dùng ErrorHandlingDeserializer khi cần xử lý lỗi deserialize qua container error handler.
- Delegate deserializer chỉ hỗ trợ kiểu dữ liệu và schema được cho phép.
- Trusted packages/type mapping được giới hạn.
- Không deserialize Java native object từ nguồn không tin cậy.
- Schema contract có version và compatibility policy.
- Validation kiểm tra cú pháp, schema, domain và quyền.
- Lỗi dữ liệu cố định được phân loại non-retryable.
- Retry có số lần, backoff và deadline hữu hạn.
- DLT/quarantine được bảo vệ bằng ACL, encryption và retention phù hợp.
- DLT serializer hỗ trợ cả payload hợp lệ và raw bytes của record deserialize thất bại.
- Recovery publish thất bại không làm offset nguồn tiến như thể đã lưu thành công.
- SQL dùng parameterized query; URL/path/shell/log đều xử lý input an toàn.
- Payload size, string length, collection size và nesting depth có giới hạn.
- Không log raw payload, secret hoặc header nhạy cảm.
- Consumer có idempotency để chịu redelivery và replay.
- Có metric cho deserialize/validation failure, DLT, lag, payload size và tài nguyên.
- Replay DLT có quy trình kiểm tra, phân quyền và audit.
- Đã thử record sai định dạng, schema cũ, payload quá lớn và lỗi validation trong môi trường kiểm thử.

Dữ liệu độc hại cần được xử lý như một lỗi đầu vào có thể lặp lại và có thể ảnh hưởng đến bảo mật. Spring Kafka cung cấp ErrorHandlingDeserializer, error handler và DLT để đưa record lỗi ra khỏi luồng chính. Ứng dụng cần bổ sung schema/domain validation, giới hạn tài nguyên, authorization, idempotency và quy trình quarantine/replay để consumer tiếp tục tiến lên mà vẫn giữ được khả năng điều tra và phục hồi.
