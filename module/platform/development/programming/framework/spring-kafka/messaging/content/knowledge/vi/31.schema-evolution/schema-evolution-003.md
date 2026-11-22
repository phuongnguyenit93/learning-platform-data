# Thêm field tương thích ngược

Thêm field vào event là thay đổi schema thường gặp khi nghiệp vụ cần lưu thêm dữ liệu. Thay đổi này có thể an toàn trong quá trình rolling deployment nếu consumer mới vẫn đọc được event cũ và consumer cũ có thể bỏ qua field mới. Muốn đạt điều đó, field mới thường cần có tính tùy chọn, giá trị mặc định rõ ràng và không làm thay đổi ý nghĩa của các field hiện có.

Trong module SPRING_KAFKA_MESSAGING, producer gửi event bằng KafkaTemplate và consumer nhận event bằng @KafkaListener. Kafka lưu byte của record; serializer và deserializer ở hai phía diễn giải byte theo hợp đồng dữ liệu. Vì producer và consumer có thể được triển khai ở các thời điểm khác nhau, schema phải tương thích với những phiên bản đang cùng tồn tại.

## 1. Hai chiều tương thích cần phân biệt

Hai khái niệm thường bị gọi chung là backward compatibility nhưng thực tế mô tả hai hướng khác nhau:

| Chiều tương thích | Câu hỏi | Ví dụ khi thêm field |
|---|---|---|
| Backward compatibility | Consumer dùng schema mới có đọc được dữ liệu do producer cũ ghi không? | Consumer mới đọc event cũ không có field priority |
| Forward compatibility | Consumer dùng schema cũ có đọc được dữ liệu do producer mới ghi không? | Consumer cũ gặp field priority mà nó chưa biết |
| Full compatibility | Cả hai chiều đều đọc được dữ liệu của phía còn lại | Rolling deployment có producer và consumer cũ/mới cùng chạy |

Trong một hệ thống Kafka, producer và consumer thường không được nâng cấp đồng thời. Vì vậy, khi thêm field, nên xác định rõ cần backward, forward hay full compatibility. Thêm một field optional với default phù hợp thường là thay đổi dễ hỗ trợ cả hai chiều, miễn là consumer cũ có chính sách bỏ qua field không biết.

## 2. Ví dụ event trước và sau khi thêm field

Giả sử topic orders.created đang phát event có eventId, orderId và total. Phiên bản mới cần thêm priority để downstream quyết định mức ưu tiên xử lý.

Event cũ:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "total": 1250000
}
~~~

Event mới:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "total": 1250000,
  "priority": 2
}
~~~

Field priority cần có quy tắc khi vắng mặt. Ví dụ, event cũ không có priority được hiểu là mức ưu tiên mặc định 0. Không nên để mỗi consumer tự diễn giải một giá trị khác nhau.

## 3. Quy tắc an toàn khi thêm field

- Thêm field mới theo hướng optional hoặc có default được schema format hỗ trợ.
- Xác định ý nghĩa nghiệp vụ của giá trị mặc định; tránh chọn một giá trị có nghĩa hợp lệ nhưng làm sai hành vi.
- Consumer mới phải xử lý trường hợp field vắng mặt trong event cũ.
- Consumer cũ phải bỏ qua field mới nếu format và thư viện cho phép unknown fields.
- Không đổi tên, kiểu dữ liệu hoặc ý nghĩa của field hiện có trong cùng thay đổi.
- Không làm field mới bắt buộc ngay khi producer cũ vẫn còn phát event.
- Cập nhật schema contract và kiểm thử các phiên bản producer/consumer hỗ trợ.

Một field có default ở schema không nhất thiết được ghi vào mọi payload. Default có thể chỉ được áp dụng khi reader diễn giải dữ liệu cũ. Với JSON, từ khóa default trong JSON Schema thường là annotation; validator không tự chèn giá trị vào JSON. Ứng dụng cần tự áp dụng default khi field bị thiếu.

## 4. Thêm field trong Java DTO và JSON

Ví dụ DTO cũ:

~~~java
import java.math.BigDecimal;

public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal total
) {}
~~~

DTO mới thêm priority:

~~~java
import java.math.BigDecimal;

public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal total,
        Integer priority
) {
    public OrderCreatedV2 {
        priority = priority == null ? 0 : priority;
    }
}
~~~

Sử dụng Integer thay cho int giúp phân biệt field không xuất hiện hoặc có giá trị null với giá trị 0 được gửi rõ ràng. Compact constructor chuẩn hóa cả trường hợp thiếu/null về giá trị nghiệp vụ mặc định. Nếu null là trạng thái nghiệp vụ khác với 0, không gộp hai trạng thái này.

Khi consumer mới đọc JSON cũ, Jackson tạo DTO mới mà field priority chưa có trong payload; constructor áp dụng default 0. Khi consumer cũ đọc JSON mới có priority, ObjectMapper cần được cấu hình bỏ qua unknown property:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper objectMapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

OrderCreatedV1 oldConsumerView = objectMapper.readValue(
        newEventJson,
        OrderCreatedV1.class
);
~~~

Trong Spring Kafka, JsonDeserializer phải dùng ObjectMapper có chính sách tương ứng nếu ứng dụng muốn consumer cũ bỏ qua field mới. Cần cấu hình mapper trên deserializer thực tế của ConsumerFactory; chỉ tạo một ObjectMapper riêng trong test không làm thay đổi mapper đang chạy trong listener container.

Không dựa vào annotation JsonProperty(defaultValue = "0") như cơ chế tự gán default khi deserialize. Thuộc tính defaultValue chủ yếu là metadata cho công cụ/schema; hãy áp dụng default trong constructor, mapper hoặc tầng chuyển đổi dữ liệu một cách rõ ràng.

## 5. Cấu hình JSON deserializer trong Spring Kafka

Với một consumer chỉ nhận OrderCreatedV2, có thể cấu hình target type rõ ràng và tin cậy package event:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedV2
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.orders
~~~

Ví dụ tắt type headers để consumer dùng target type đã cấu hình. Nếu hệ thống dùng type headers hoặc type mapping, giữ cấu hình đó nhất quán giữa producer và consumer. Type header xác định class đích, còn chính sách unknown field của ObjectMapper quyết định cách xử lý property mới trong JSON.

Với ứng dụng cần tùy chỉnh ObjectMapper, cấu hình mapper vào JsonDeserializer được dùng bởi ConsumerFactory. Đảm bảo mapper đó vừa xử lý unknown property theo yêu cầu tương thích, vừa giữ các quy tắc về date/time, number, naming strategy và validation của hợp đồng.

Producer phiên bản mới gửi DTO V2 qua KafkaTemplate:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedV2> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedV2> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedV2>> publish(
            OrderCreatedV2 event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

Consumer mới nhận DTO V2 qua @KafkaListener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService projectionService;

    public OrderProjectionListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(topics = "orders.created", groupId = "orders-projection")
    public void onOrderCreated(OrderCreatedV2 event) {
        projectionService.apply(event);
    }
}
~~~

Application service contract được listener gọi:

~~~java
public interface OrderProjectionService {
    void apply(OrderCreatedV2 event);
}
~~~

Ví dụ giả định producer factory dùng JsonSerializer cho value và consumer factory dùng JsonDeserializer với target type V2 cùng ObjectMapper đã nêu. Kiểu DTO và serializer/deserializer phải được cấu hình đồng bộ; thay DTO Java không tự thay đổi schema hoặc cấu hình của các service khác.

## 6. JSON Schema: field mới nên optional

Với JSON Schema, field mới có thể được khai báo trong properties nhưng không thêm vào danh sách required:

~~~json
{
  "type": "object",
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "total": { "type": "number" },
    "priority": { "type": "integer", "default": 0 }
  },
  "required": ["eventId", "orderId", "total"],
  "additionalProperties": true
}
~~~

Ở đây priority không nằm trong required nên event cũ vẫn hợp lệ theo schema mới. additionalProperties: true cho phép schema cũ chấp nhận field mới khi producer phát event có priority. Nếu contract hiện tại đặt additionalProperties: false, consumer/schema cũ có thể từ chối event mới; cần cân nhắc chính sách unknown fields trước khi rollout.

JSON Schema default không tự sửa payload trong quá trình validation. Consumer cần áp dụng default ở application layer, chẳng hạn chuẩn hóa DTO sau deserialize. Nếu dùng Schema Registry, kiểm tra compatibility mode và kiểm tra schema thực tế bằng công cụ của registry; đừng suy ra compatibility chỉ từ việc JSON Schema có thuộc tính default.

## 7. Avro: thêm field phải có default trong reader schema

Avro hỗ trợ schema resolution giữa writer schema và reader schema. Khi consumer mới đọc record được ghi bằng schema cũ, field có trong reader schema nhưng vắng mặt ở writer schema cần có default trong reader schema.

Schema cũ:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" }
  ]
}
~~~

Schema mới thêm priority:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" },
    { "name": "priority", "type": ["int", "null"], "default": 0 }
  ]
}
~~~

Default 0 phải khớp branch đầu tiên của union type trong ví dụ này. Nếu dùng union ["null", "int"], default phải là null vì branch đầu tiên là null. Quy tắc default của Avro là một phần của schema resolution, khác với JSON Schema default annotation.

Consumer cũ dùng reader schema cũ có thể bỏ qua field priority được writer schema mới thêm. Consumer mới dùng reader schema mới có thể đọc record cũ và nhận default 0 cho priority. Đây là lý do thêm field Avro với default thường là thay đổi tương thích tốt.

## 8. Protobuf: thêm field với field number mới

Với Protobuf, field number là định danh wire quan trọng. Có thể thêm một field optional mới với số chưa từng dùng:

~~~proto
syntax = "proto3";

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total = 3;
  optional int32 priority = 4;
}
~~~

Consumer cũ không biết field number 4 sẽ bỏ qua unknown field theo wire format. Consumer mới đọc message cũ không có field priority sẽ thấy field chưa được set; với scalar proto3, giá trị getter mặc định là 0. Từ khóa optional cho phép kiểm tra presence bằng hasPriority() để phân biệt không được gửi với được gửi giá trị 0.

Proto3 optional được hỗ trợ trong các phiên bản protoc hiện đại (từ 3.12); kiểm tra compiler/plugin của dự án trước khi dùng cú pháp này.

Không tái sử dụng field number đã xóa. Nếu bỏ field, hãy reserve cả number và name trong message schema:

~~~proto
message OrderCreated {
  reserved 4;
  reserved "priority";
}
~~~

Không đổi field number hoặc thay đổi wire type của field hiện có chỉ vì tên field vẫn giữ nguyên. Với Protobuf, đổi số hoặc kiểu có thể làm consumer diễn giải byte sai.

## 9. Thêm field có default không làm field trở thành bắt buộc

Default là giá trị fallback khi dữ liệu cũ không chứa field. Nó không có nghĩa producer mới luôn phải gửi field đó, cũng không chứng minh mọi event mới hợp lệ về nghiệp vụ.

Trước khi thêm field, hãy trả lời:

- Giá trị mặc định là gì và ai sở hữu quyết định nghiệp vụ đó?
- Field có thể null không, hay chỉ có thể vắng mặt?
- 0, false hoặc chuỗi rỗng có phải giá trị hợp lệ thật không?
- Consumer cần phân biệt “không biết” với “giá trị mặc định” không?
- Có cần backfill dữ liệu cũ hay chỉ áp dụng default khi đọc?

Ví dụ, priority = 0 có thể mang nghĩa “normal”, trong khi field vắng mặt có nghĩa “chưa xác định”. Nếu hai trạng thái khác nhau, dùng kiểu nullable/presence-aware thay vì ép mọi trường hợp thành 0.

## 10. Triển khai rolling deployment an toàn

Khi producer và consumer được deploy độc lập, trình tự rollout giảm rủi ro như sau:

1. **Mở rộng consumer trước:** triển khai consumer mới có thể đọc event cũ thiếu field và chịu được field mới nếu có.
2. **Kiểm tra compatibility:** xác minh consumer mới đọc được dữ liệu lịch sử và phiên bản producer hiện tại.
3. **Nâng producer:** chỉ sau khi consumer mới đã sẵn sàng, producer mới bắt đầu gửi field priority.
4. **Theo dõi:** kiểm tra lỗi deserialize, validation failure, tỷ lệ field bị thiếu và hành vi nghiệp vụ mặc định.
5. **Giữ tương thích trong thời gian hỗ trợ:** không xóa fallback khi vẫn còn record cũ trong retention, retry topic hoặc DLT có thể được replay.

Nếu consumer cũ vẫn có thể chạy trong lúc producer mới phát event, phải xác minh consumer cũ bỏ qua unknown field. Nếu không, cần hoàn tất rollout consumer trước khi bật producer mới hoặc dùng versioned topic/contract để tách luồng.

## 11. Schema Registry và compatibility mode

Nếu dùng Schema Registry, compatibility policy kiểm tra quan hệ giữa schema mới và schema đã đăng ký:

| Mode | Hướng kiểm tra khái quát | Ý nghĩa khi thêm field |
|---|---|---|
| BACKWARD | Schema mới đọc dữ liệu theo schema trước đó | Consumer mới đọc record cũ |
| BACKWARD_TRANSITIVE | Schema mới đọc dữ liệu của tất cả version trước | Phù hợp khi còn record lịch sử rất cũ |
| FORWARD | Schema trước đó đọc dữ liệu theo schema mới | Consumer cũ đọc record mới |
| FULL | Kiểm tra cả backward và forward | Hữu ích cho rolling deployment cần cả hai chiều |
| FULL_TRANSITIVE | Cả hai chiều với mọi version trước | Chính sách chặt hơn cho lịch sử nhiều version |

Tên mode và khả năng áp dụng phụ thuộc Schema Registry đang sử dụng. Với Avro, field mới có default là quy tắc quan trọng cho backward compatibility. Với JSON Schema, cần xem required/additionalProperties và cách validator áp dụng schema. Với Protobuf, cần giữ field number/wire type an toàn.

Compatibility check của registry không thay thế integration test. Registry kiểm tra schema theo quy tắc format; nó không biết mọi business invariant, validation trong Java hoặc side effect của listener.

## 12. Những thay đổi không nên gộp cùng thao tác thêm field

Tránh kết hợp việc thêm field với những thay đổi làm phá vỡ contract:

- Đổi tên field cũ mà không giữ alias/mapping tương thích.
- Đổi kiểu số từ int sang string hoặc thay wire type.
- Đổi đơn vị của field, ví dụ total từ đồng sang nghìn đồng, nhưng giữ nguyên tên.
- Thêm field vào required trong JSON Schema khi producer cũ chưa gửi.
- Thêm validation @NotNull cho field mới trước khi mọi event cũ đã được xử lý/backfill.
- Đổi ý nghĩa giá trị mặc định giữa các consumer.
- Xóa field cũ ngay khi producer mới bắt đầu phát field mới.

Nếu cần thay đổi không tương thích, cân nhắc version event rõ ràng, topic version mới hoặc một giai đoạn expand/contract riêng. Không dùng schemaVersion để hợp thức hóa việc consumer không thể đọc payload; vẫn cần logic routing và compatibility cụ thể.

## 13. Kiểm thử tương thích cho Spring Kafka

Tạo ma trận test cho producer/consumer version:

| Producer | Consumer | Kết quả cần xác minh |
|---|---|---|
| Cũ | Cũ | Hành vi hiện tại không đổi |
| Cũ | Mới | Field mới được default đúng |
| Mới | Cũ | Consumer cũ bỏ qua field mới |
| Mới | Mới | Field mới được đọc và xử lý đúng |

Các kiểm thử quan trọng:

- **JSON old-to-new:** deserialize payload cũ vào DTO mới; xác minh priority có default mong muốn.
- **JSON new-to-old:** deserialize payload mới vào DTO cũ; xác minh unknown field được bỏ qua theo cấu hình ObjectMapper thực tế.
- **Avro resolution:** dùng reader schema mới đọc record ghi bằng writer schema cũ.
- **Protobuf compatibility:** consumer cũ đọc message mới có field number mới; consumer mới đọc message cũ và kiểm tra presence/default.
- **Spring Kafka integration:** gửi record qua KafkaTemplate và nhận qua @KafkaListener với serializer/deserializer thực tế.
- **Rolling deployment test:** xác minh các phiên bản consumer/producers cùng tồn tại trong thời gian nâng cấp.
- **Replay test:** đọc lại record cũ từ retry topic/DLT sau khi consumer đã được nâng cấp.

Dùng Embedded Kafka hoặc Testcontainers cho luồng Spring Kafka. Nếu dùng Schema Registry, chạy compatibility check trên schema candidate trước khi publish schema mới và kiểm thử serialization/deserialization qua serializer thực tế.

## 14. Những lỗi thường gặp

- **Nhầm backward với forward compatibility:** new consumer đọc old data và old consumer đọc new data là hai chiều khác nhau.
- **Thêm field bắt buộc ngay lập tức:** event cũ thiếu field sẽ không deserialize hoặc validation thất bại.
- **Tin rằng JSON Schema default tự chèn giá trị:** application phải áp dụng default khi field vắng mặt.
- **Không cấu hình Jackson unknown-property policy:** consumer cũ có thể từ chối JSON chứa field mới.
- **Dùng primitive rồi không phân biệt missing với zero:** chọn kiểu nullable/presence-aware khi nghiệp vụ cần phân biệt.
- **Avro union default không khớp branch đầu:** schema resolution thất bại.
- **Tái sử dụng Protobuf field number:** dữ liệu cũ có thể bị diễn giải sai.
- **Chỉ test DTO bằng ObjectMapper riêng:** cấu hình JsonDeserializer thật của ConsumerFactory có thể khác.
- **Nâng producer trước consumer:** consumer cũ có thể nhận payload mới mà chưa hỗ trợ.
- **Bỏ fallback quá sớm:** record lịch sử, retry và DLT vẫn có thể được replay.
- **Chỉ dựa vào Schema Registry compatibility:** schema hợp lệ chưa bảo đảm business logic tương thích.

## 15. Checklist thêm field tương thích

- [ ] Đã xác định chiều tương thích cần có: backward, forward hay full.
- [ ] Field mới có kiểu và ý nghĩa nghiệp vụ rõ ràng.
- [ ] Có default/fallback được định nghĩa và kiểm thử.
- [ ] JSON Schema không bắt buộc field mới khi còn producer cũ.
- [ ] Consumer JSON cũ xử lý unknown property theo chính sách rõ ràng.
- [ ] Avro field mới có default hợp lệ theo union branch.
- [ ] Protobuf dùng field number mới và không tái sử dụng số đã reserve.
- [ ] Spring Kafka JsonDeserializer/serializer dùng đúng contract và ObjectMapper.
- [ ] Schema Registry compatibility mode phù hợp với chiến lược rollout.
- [ ] Consumer mới được triển khai trước producer mới nếu cần.
- [ ] Có ma trận test producer cũ/mới với consumer cũ/mới.
- [ ] Retry topic, DLT và record lịch sử vẫn đọc được sau rollout.
- [ ] Không gộp rename, type change hoặc semantic change vào cùng migration.

Thêm field tương thích không chỉ là sửa DTO. Cần xác định chiều tương thích, quy tắc default, cách xử lý unknown field và trình tự triển khai producer/consumer. Khi schema và application cùng hỗ trợ dữ liệu cũ lẫn mới, Spring Kafka có thể tiếp tục vận hành trong rolling deployment mà không buộc mọi service phải nâng cấp đồng thời.
