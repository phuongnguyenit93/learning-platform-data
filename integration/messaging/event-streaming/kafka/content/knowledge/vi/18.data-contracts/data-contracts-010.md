# Chiến lược triển khai producer và consumer khi đổi hợp đồng

## Mục tiêu bài học

Producer và consumer Kafka thường được phát triển, triển khai và mở rộng độc lập. Khi đổi data contract, các phiên bản cũ và mới có thể cùng chạy trong một khoảng thời gian; record cũ vẫn còn trong topic và có thể được đọc lại sau nhiều ngày. Vì vậy, một thay đổi schema hợp lệ về mặt cú pháp vẫn có thể làm consumer đang chạy lỗi hoặc khiến dữ liệu bị diễn giải sai.

Sau bài học, bạn có thể:

- Phân loại thay đổi contract thành additive, tương thích có điều kiện và breaking change.
- Phân biệt backward, forward, full và transitive compatibility.
- Chọn thứ tự triển khai producer/consumer theo khả năng tương thích của thay đổi.
- Áp dụng chiến lược expand-and-contract để đổi field mà không dừng toàn bộ hệ thống.
- Thiết kế dual-read, dual-write và migration sang topic/version mới.
- Kiểm thử producer mới với consumer cũ và consumer mới với dữ liệu cũ.
- Lập kế hoạch rollback, replay, theo dõi lỗi deserialization và consumer lag.
- Phối hợp schema registry, Java/Spring Kafka, Kafka Connect và Kafka Streams trong một đợt migration.

## 1. Vì sao đổi contract cần kế hoạch rollout?

Trong một hệ thống event streaming, producer ghi record vào topic còn một hoặc nhiều consumer group đọc dữ liệu theo tiến độ riêng. Các thành phần này không nhất thiết được deploy cùng thời điểm.

Ví dụ một lần release có thể diễn ra như sau:

```text
Thời điểm T0: producer v1  ---> topic orders ---> consumer v1
                                      |
                                      +--------> analytics v3

Thời điểm T1: consumer v2 bắt đầu deploy, producer vẫn là v1
                                      |
Thời điểm T2: consumer v1 và v2 cùng tồn tại
                                      |
Thời điểm T3: toàn bộ consumer đã lên v2, producer vẫn là v1
                                      |
Thời điểm T4: producer v2 bắt đầu ghi contract mới
                                      |
Thời điểm T5: dữ liệu cũ và mới cùng tồn tại trong topic
```

Trong khoảng T4 đến khi dữ liệu cũ hết retention, consumer mới có thể phải đọc cả record cũ lẫn record mới. Nếu consumer bị rollback, phiên bản cũ có thể gặp record mới. Một migration an toàn phải tính đến cả hai hướng đọc, thời gian chạy song song và khả năng replay.

Các rủi ro chính khi thay đổi contract:

- Consumer cũ không hiểu field mới, enum mới hoặc kiểu dữ liệu mới.
- Consumer mới yêu cầu field mà record cũ không có.
- Producer mới gửi dữ liệu theo ý nghĩa khác nhưng vẫn hợp lệ về kiểu.
- Một số instance đã nâng cấp, một số instance vẫn dùng version cũ.
- Topic còn record cũ sau khi producer đã chuyển sang schema mới.
- Replay hoặc reset offset đưa record cũ đến một consumer vừa được nâng cấp.
- Key thay đổi làm record của cùng entity đi sang partition khác, ảnh hưởng ordering.

## 2. Phân loại thay đổi trước khi chọn thứ tự triển khai

Không nên bắt đầu bằng việc sửa DTO rồi deploy. Trước hết hãy xác định thay đổi thuộc nhóm nào.

| Loại thay đổi | Ví dụ | Mức rủi ro | Hướng triển khai thường dùng |
|---|---|---|---|
| Additive | Thêm field tùy chọn có default | Thấp đến trung bình | Consumer-first, sau đó producer |
| Nới lỏng contract | Cho phép null hoặc thêm giá trị enum mà consumer có thể bỏ qua | Trung bình | Nâng consumer chịu được giá trị mới trước |
| Đổi tên field | `customerName` thành `fullName` | Trung bình đến cao | Dual-read/dual-write qua giai đoạn chuyển tiếp |
| Đổi kiểu | `amount` từ integer sang string/decimal | Cao | Field mới hoặc contract/topic v2 |
| Đổi ý nghĩa | `amount` từ VND sang USD nhưng giữ kiểu số | Rất cao | Field/version mới, migration dữ liệu và consumer |
| Xóa field | Loại bỏ `legacyCode` | Cao nếu còn consumer cũ | Ngừng phụ thuộc, chờ hết replay window rồi mới xóa |
| Đổi key hoặc partitioning | Key từ `orderId` sang `customerId` | Rất cao | Migration riêng, đánh giá ordering và trạng thái theo partition |
| Đổi wire format | JSON sang Avro/Protobuf | Cao | Topic/version hoặc giai đoạn chuyển đổi có kiểm soát |

Một thay đổi có thể tương thích ở tầng schema nhưng vẫn breaking ở tầng nghiệp vụ. Ví dụ trường `amount` vẫn là `long` nhưng đổi đơn vị từ đồng sang xu; schema registry có thể chấp nhận nhưng consumer sẽ tính sai nếu không biết semantics đã đổi.

## 3. Hiểu đúng các hướng compatibility

Compatibility thường được mô tả theo khả năng đọc dữ liệu giữa writer schema và reader schema.

| Chế độ | Ý nghĩa | Tình huống rollout liên quan |
|---|---|---|
| Backward | Schema mới có thể đọc dữ liệu được ghi theo schema cũ | Nâng consumer trước, sau đó producer bắt đầu ghi schema mới |
| Forward | Schema cũ có thể đọc dữ liệu được ghi theo schema mới | Producer mới và consumer cũ có thể cùng tồn tại trong giai đoạn chuyển tiếp |
| Full | Đáp ứng cả backward và forward | Hữu ích khi producer/consumer cũ và mới cùng chạy |
| Transitive | Kiểm tra tương thích với nhiều hoặc toàn bộ version trước đó theo policy | Phù hợp khi topic còn dữ liệu của nhiều thế hệ schema |

Tên mode và chi tiết kiểm tra phụ thuộc Schema Registry. Với Confluent Schema Registry, cần xác nhận compatibility mode ở global hoặc subject level, đồng thời kiểm tra cách registry so sánh schema mới với version trước đó.

### 3.1. Compatibility không đồng nghĩa consumer code chắc chắn chạy đúng

Registry kiểm tra các quy tắc schema mà format hỗ trợ. Nó không biết:

- Consumer có xử lý enum lạ hay không.
- Field có đúng đơn vị tiền tệ hay timezone không.
- Consumer có giả định thứ tự field hoặc thứ tự event không.
- Side effect có an toàn khi record replay không.
- Một field mới có được business logic bắt buộc dù schema khai báo optional không.

Do đó cần cả schema compatibility check, contract test và kiểm thử hành vi ứng dụng.

### 3.2. Compatibility policy phải khớp rollout

Nếu muốn deploy consumer mới trước và consumer mới phải đọc record cũ, cần backward compatibility. Nếu muốn producer mới phát record trước trong khi consumer cũ còn chạy, cần forward compatibility và consumer cũ phải thực sự xử lý unknown field/enum an toàn. Nếu hai phiên bản cùng tồn tại và cả hai hướng đều cần hỗ trợ, dùng full compatibility khi format và contract cho phép.

Đừng dựa riêng vào nhãn `BACKWARD` hoặc `FULL` mà bỏ qua thứ tự deploy thực tế. Hãy viết rõ ma trận producer/consumer version cần tương tác và kiểm thử đúng các cặp đó.

## 4. Nguyên tắc rollout an toàn

Một quy trình thay đổi contract nên tuân thủ các nguyên tắc:

1. **Mở rộng trước, thu hẹp sau:** thêm khả năng mới trước khi xóa khả năng cũ.
2. **Consumer chịu được dữ liệu cũ và mới:** trong giai đoạn chuyển tiếp, consumer nên đọc được cả hai dạng.
3. **Producer chỉ phát dữ liệu mới khi consumer đã sẵn sàng:** tránh phát field hoặc enum mới khi còn consumer không hiểu.
4. **Giữ semantics ổn định:** nếu ý nghĩa thay đổi, biểu diễn thay đổi đó bằng field/version mới.
5. **Không đổi key tùy tiện:** key có thể quyết định partition và ordering.
6. **Để dữ liệu cũ có đường đọc:** retention và replay window có thể kéo dài hơn thời gian deploy.
7. **Có điểm dừng và rollback:** biết điều kiện nào phải dừng rollout, quay lại producer cũ hoặc chuyển sang topic v2.
8. **Đo kết quả:** theo dõi lỗi deserialize, DLQ, consumer lag, throughput và business invariant.

## 5. Chiến lược consumer-first cho thay đổi additive

Đây thường là lựa chọn đơn giản nhất khi thêm field tùy chọn và giữ nguyên ý nghĩa field hiện tại.

### 5.1. Trình tự triển khai

Giả sử event `OrderCreated` có `orderId` và `totalAmount`; phiên bản mới bổ sung `salesChannel`.

```text
Bước 1: Consumer v2 được triển khai
        - Đọc được record cũ không có salesChannel
        - Đọc được record mới có salesChannel

Bước 2: Chờ tất cả consumer instance/group liên quan lên v2

Bước 3: Producer v2 bắt đầu ghi salesChannel

Bước 4: Theo dõi deserialize error, business validation và lag

Bước 5: Chỉ sau thời gian tương thích/replay mới cân nhắc thay đổi tiếp
```

Consumer-first bảo đảm producer chưa phát field mới trong lúc consumer đang nâng cấp. Consumer v2 phải xử lý trường hợp field vắng mặt bằng default hoặc nhánh nghiệp vụ rõ ràng.

### 5.2. Ví dụ JSON: thêm field tùy chọn

Payload cũ:

```json
{
  "eventId": "evt-1001",
  "orderId": "ORD-101",
  "totalAmount": 250000
}
```

Payload mới:

```json
{
  "eventId": "evt-1002",
  "orderId": "ORD-102",
  "totalAmount": 320000,
  "salesChannel": "MOBILE"
}
```

Consumer mới không được giả định `salesChannel` luôn tồn tại:

```java
JsonNode channelNode = payload.path("salesChannel");
String salesChannel = channelNode.isMissingNode() || channelNode.isNull()
    ? "UNKNOWN"
    : channelNode.asText();

processOrder(payload.path("orderId").asText(), salesChannel);
```

Giá trị `UNKNOWN` phải có ý nghĩa nghiệp vụ được thống nhất. Nếu không có default hợp lệ, consumer nên giữ null hoặc đưa record vào luồng xử lý cần bổ sung dữ liệu thay vì tự gán một giá trị gây hiểu sai.

### 5.3. Ví dụ Avro: thêm field có default

Schema cũ:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "totalAmount", "type": "long"}
  ]
}
```

Schema mới:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "eventId", "type": "string"},
    {"name": "orderId", "type": "string"},
    {"name": "totalAmount", "type": "long"},
    {
      "name": "salesChannel",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
```

Reader schema mới có default để đọc record được ghi theo schema cũ không có field này. Trước khi đăng ký schema, chạy compatibility check theo policy của subject. Đừng nhầm default trong Avro reader schema với việc producer tự động ghi giá trị default vào mọi record mới.

## 6. Chiến lược producer-first có kiểm soát

Có tình huống producer cần phát dữ liệu mới trước khi tất cả consumer được nâng cấp, ví dụ nhiều team triển khai độc lập. Chỉ dùng cách này nếu consumer cũ có thể đọc record mới và contract được kiểm tra theo hướng forward compatibility.

### 6.1. Điều kiện cần

- Field mới là additive và consumer cũ có thể bỏ qua field không biết.
- Enum mới không làm consumer cũ throw exception hoặc rơi vào nhánh xử lý sai.
- JSON deserializer không bật chế độ fail khi gặp unknown property, hoặc DTO được cấu hình rõ ràng.
- Protobuf reader giữ khả năng bỏ qua unknown field theo wire format.
- Avro/schema registry policy cho phép hướng writer mới, reader cũ.
- Producer mới không thay đổi semantics của field hiện có.

Nếu không chắc chắn các điều kiện này, hãy dùng consumer-first hoặc triển khai topic/version mới.

### 6.2. Unknown enum là một rủi ro riêng

Consumer cũ có thể bỏ qua field lạ nhưng vẫn thất bại khi gặp enum value mới. Ví dụ producer thêm `salesChannel=PARTNER`, trong khi consumer cũ chỉ có `WEB` và `MOBILE`.

Consumer cần một nhánh unknown/fallback rõ ràng hoặc rollout consumer trước khi producer phát enum mới. Không nên mặc định mọi thư viện JSON/Avro/Protobuf xử lý enum lạ giống nhau.

## 7. Expand-and-contract khi đổi tên hoặc loại bỏ field

Đổi tên field trực tiếp thường là breaking change vì consumer cũ có thể chỉ đọc tên cũ. Cách an toàn là giữ hai field trong giai đoạn chuyển tiếp.

Giả sử đổi `customerName` thành `fullName`.

### 7.1. Giai đoạn expand

Producer tạm thời ghi cả hai field với cùng ý nghĩa:

```json
{
  "eventId": "evt-2001",
  "customerName": "Nguyen An",
  "fullName": "Nguyen An"
}
```

Consumer mới ưu tiên field mới và fallback về field cũ:

```java
JsonNode nameNode = payload.path("fullName");
if (nameNode.isMissingNode() || nameNode.isNull()) {
    nameNode = payload.path("customerName");
}

if (nameNode.isMissingNode() || nameNode.isNull()) {
    throw new IllegalArgumentException("Missing customer name");
}

String fullName = nameNode.asText();
```

Trong giai đoạn này:

- Consumer cũ tiếp tục đọc `customerName`.
- Consumer mới đọc `fullName`, fallback về `customerName` để đọc record cũ.
- Producer mới ghi cả hai field.
- Dashboard theo dõi số record thiếu `fullName` và số consumer còn dùng field cũ.

### 7.2. Chuyển đổi toàn bộ consumer

Triển khai consumer mới đến tất cả service, connector, stream topology, batch job và công cụ replay liên quan. Chờ các instance cũ dừng hoàn toàn và xác nhận không còn client nào phụ thuộc field cũ.

Consumer mới vẫn cần đọc record lịch sử chỉ có `customerName` trong suốt retention/replay window. Không được bỏ fallback chỉ vì producer hiện tại đã ghi `fullName`.

### 7.3. Giai đoạn contract

Khi tất cả consumer đã dùng field mới và dữ liệu cũ không còn nằm trong phạm vi replay cần hỗ trợ, producer có thể ngừng ghi field cũ. Sau đó, trong một release riêng, schema mới mới được phép loại bỏ field cũ theo compatibility policy.

```text
Release A: producer ghi old + new; consumer đọc new, fallback old
Release B: tất cả consumer đã dùng logic mới
Release C: producer ngừng ghi old field
Release D: sau replay window, contract schema loại bỏ old field
```

Không gộp cả bốn giai đoạn vào một lần deploy nếu hệ thống có nhiều consumer độc lập.

## 8. Thay đổi kiểu dữ liệu hoặc semantics: cân nhắc version mới

Một thay đổi như `totalAmount` từ integer sang decimal, hoặc đổi đơn vị từ VND sang USD, có thể không tương thích dù tên field giữ nguyên.

### 8.1. Thêm field mới thay vì đổi nghĩa field cũ

Ví dụ giữ `totalAmountVnd` và bổ sung `totalAmountUsd` hoặc `totalAmountMinorUnits` với semantics được định nghĩa rõ. Consumer mới ưu tiên field mới; producer có thể dual-write trong giai đoạn chuyển tiếp nếu việc chuyển đổi có quy tắc chính xác.

Không ghi cùng một giá trị vào field mới nếu chưa định nghĩa rõ conversion, rounding, scale, currency và timestamp tỷ giá.

### 8.2. Tạo contract hoặc topic v2

Nếu cấu trúc hoặc semantics thay đổi lớn, tạo topic mới như `orders.v2` hoặc subject/schema version riêng. Cách này giúp consumer v1 tiếp tục đọc contract cũ trong khi consumer v2 được triển khai độc lập.

Chọn versioning theo topic khi:

- Nhiều field đổi kiểu hoặc đổi semantics cùng lúc.
- Key/partitioning thay đổi.
- Wire format thay đổi và consumer cũ không thể đọc.
- Cần migration/replay độc lập.
- Có yêu cầu giữ v1 trong thời gian dài cho hệ thống chưa thể nâng cấp.

Không tạo topic v2 chỉ vì thêm một field tùy chọn nếu schema evolution hiện tại xử lý được an toàn. Topic version mới làm tăng chi phí vận hành, ACL, retention, monitoring và migration.

## 9. Dual-write và dual-read khi chuyển topic/version

### 9.1. Dual-read

Consumer có thể đọc cả v1 và v2 trong giai đoạn migration, sau đó chuẩn hóa về một domain model nội bộ. Cần có adapter riêng cho từng version để logic nghiệp vụ không phải liên tục kiểm tra version ở mọi nơi.

```java
sealed interface OrderEvent permits OrderEventV1, OrderEventV2 {}

OrderEvent normalize(String topic, byte[] value) {
    return switch (topic) {
        case "orders.v1" -> decodeV1(value);
        case "orders.v2" -> decodeV2(value);
        default -> throw new IllegalArgumentException("Unsupported topic: " + topic);
    };
}
```

Đây là mã giả minh họa adapter. Cần giữ event ID và source version để deduplicate khi cùng event xuất hiện ở cả hai topic.

### 9.2. Dual-write

Producer có thể publish cùng một event logic sang cả `orders.v1` và `orders.v2` trong một giai đoạn. Việc này cần xử lý:

- Hai lần publish có thể thành công/thất bại không đồng thời nếu không có transaction phù hợp.
- Consumer có thể nhận cùng event từ hai topic và xử lý duplicate.
- Ordering giữa hai topic không được bảo đảm tổng thể.
- Cần event ID ổn định để đối chiếu hai bản biểu diễn.
- Tăng network, disk, replication và consumer load trong thời gian migration.

Nếu cả hai topic nằm trong cùng Kafka cluster, transactional producer có thể ghi hai output topic trong cùng Kafka transaction. Consumer cần `read_committed` để chỉ nhìn thấy cả transaction đã commit. Nếu nguồn dữ liệu là database, transactional outbox thường phù hợp để đảm bảo event phát ra từ trạng thái DB đã commit; Kafka transaction không tạo transaction phân tán tự động giữa database và Kafka.

### 9.3. Không dual-write tùy tiện trong nhiều service

Nếu mỗi service tự publish hai phiên bản theo cách riêng, rất dễ xảy ra một service quên cập nhật v2, một service phát hai event với ID khác nhau hoặc hai topic lệch dữ liệu. Hãy tập trung logic migration ở producer boundary, outbox publisher hoặc bridge được quản lý, có metric xác nhận parity.

### 9.4. Cutover và dừng v1

Một kế hoạch cutover có thể gồm:

1. Tạo topic v2, schema/subject, ACL, retention và monitoring.
2. Deploy consumer có thể đọc v1/v2 hoặc consumer v2 riêng.
3. Bật dual-write/bridge và xác minh parity theo event ID.
4. Chuyển traffic nghiệp vụ sang consumer v2.
5. Theo dõi lag, lỗi và business reconciliation.
6. Dừng v1 producer sau khi mọi consumer cần thiết đã chuyển.
7. Giữ v1 trong thời gian rollback/replay được thống nhất.
8. Sau thời gian đó, dừng v1 consumer và lên lịch xóa topic theo chính sách lưu trữ.

## 10. Tác động của key, partition và headers

Đổi value schema thường dễ kiểm soát hơn đổi key. Key thường được dùng để chọn partition, vì vậy thay đổi encoding hoặc giá trị key có thể chuyển record của cùng entity sang partition khác.

Ví dụ:

```text
Trước: key = orderId
  ORD-101 -> orders partition 2

Sau: key = customerId
  CUS-42  -> orders partition 5
```

Hai event liên tiếp của cùng đơn hàng có thể đi đến hai partition khác nhau. Kafka không bảo đảm thứ tự giữa các partition, nên consumer có thể quan sát event theo thứ tự khác trước đây.

Khi đổi key:

- Xác định ordering cần giữ theo entity nào.
- Đánh giá partitioner và số partition.
- Xem xét tạo topic v2 để tránh trộn hai chiến lược partitioning.
- Có kế hoạch rebuild state store hoặc projection nếu key là khóa state.
- Không thay đổi key serializer/normalization trong một rolling deploy nếu các instance producer có thể tạo partition mapping khác nhau ngoài dự kiến.

Headers như `event-type`, `content-type`, `schema-version` và `traceparent` cũng là một phần contract. Nếu đổi tên header hoặc cách mã hóa bytes, cần rollout consumer tương tự field trong value. Kafka không tự dùng header để chọn deserializer cho mọi consumer.

## 11. Triển khai với Java và Spring Kafka

### 11.1. Producer ghi đồng thời field cũ và mới

Ví dụ Spring service phát JSON trong giai đoạn expand:

```java
public void publishCustomerUpdated(Customer customer) {
    ObjectNode payload = objectMapper.createObjectNode();
    payload.put("eventId", customer.eventId());
    payload.put("customerId", customer.id());

    // Transitional contract: ghi cả field cũ và field mới.
    payload.put("customerName", customer.fullName());
    payload.put("fullName", customer.fullName());

    kafkaTemplate.send("customers", customer.id(), payload);
}
```

Sau khi xác nhận mọi consumer đã đọc `fullName` và replay window cũ đã được xử lý, producer có thể ngừng ghi `customerName` trong một release riêng.

### 11.2. Consumer đọc tương thích cả hai field

```java
@KafkaListener(topics = "customers", groupId = "customer-projection")
public void consume(JsonNode payload) {
    String name = readText(payload, "fullName");
    if (name == null) {
        name = readText(payload, "customerName");
    }
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Customer name is missing");
    }

    updateProjection(payload.path("customerId").asText(), name);
}

private String readText(JsonNode payload, String field) {
    JsonNode node = payload.get(field);
    return node == null || node.isNull() ? null : node.asText();
}
```

Trong production, cần phân biệt field không tồn tại, null và chuỗi rỗng nếu ba trường hợp có ý nghĩa nghiệp vụ khác nhau. Không dùng `asText()` mà không validate kiểu nếu payload không đáng tin cậy.

### 11.3. Deserialization error và DLT

Trong giai đoạn migration, consumer có thể gặp record không đúng schema hoặc field có kiểu không mong đợi. Cần có cơ chế quan sát và xử lý lỗi:

- Log topic, partition, offset, event ID và schema/version nếu có.
- Phân biệt lỗi tạm thời với payload không hợp lệ.
- Dùng error handler và Dead Letter Topic (DLT) theo chính sách ứng dụng.
- Không retry vô hạn một poison message làm partition bị kẹt.
- Có quy trình sửa dữ liệu hoặc replay từ DLT sau khi consumer hỗ trợ contract mới.

DLT không thay thế compatibility. Nó là nơi cách ly record lỗi để điều tra và phục hồi có kiểm soát.

## 12. Kiểm thử ma trận producer/consumer

Không chỉ test producer mới với consumer mới. Cần test các cặp phiên bản có thể cùng tồn tại trong rollout và replay.

| Producer ghi | Consumer đọc | Câu hỏi cần xác minh |
|---|---|---|
| v1 | v1 | Hành vi baseline có còn đúng không? |
| v1 | v2 | Consumer mới đọc record cũ, field thiếu/default có đúng không? |
| v2 | v1 | Consumer cũ có chịu được field/enum/format mới không? |
| v2 | v2 | Luồng mới hoạt động đúng và business invariant được giữ không? |
| v1 đã lưu trong topic | consumer v2 sau replay | Consumer mới có đọc được dữ liệu lịch sử không? |
| v2 đã lưu trong topic | consumer rollback v1 | Rollback có thể đọc dữ liệu đã phát chưa? |

Nếu cặp v2 producer/v1 consumer không tương thích, rollout phải bảo đảm v1 consumer đã dừng trước khi producer v2 phát dữ liệu mới. Nếu không thể bảo đảm điều đó, cần forward/full compatibility hoặc tách topic/version.

### 12.1. Contract test

Contract test nên xác minh:

- Field bắt buộc, kiểu, nullability, default và enum.
- Đơn vị tiền tệ, timezone, timestamp semantics và range.
- Key và headers.
- Consumer cũ đọc payload mới khi rollout yêu cầu.
- Consumer mới đọc payload cũ và record replay.
- Schema Registry chấp nhận/từ chối schema theo policy dự kiến.
- Deserialization failure được định tuyến và quan sát đúng.

### 12.2. Test với dữ liệu thực tế đã lưu

Tạo fixture từ nhiều schema version còn trong retention, không chỉ sinh record mới theo schema hiện tại. Với topic lâu đời, có thể tồn tại record được ghi từ nhiều thế hệ producer. Consumer mới phải đọc được tất cả version mà hệ thống cam kết hỗ trợ.

## 13. Rollback và phục hồi sau rollout lỗi

Rollback consumer và rollback producer có rủi ro khác nhau.

### 13.1. Rollback consumer

Nếu producer đã phát field/enum/format mới, consumer cũ có thể không đọc được dữ liệu đó. Trước khi rollback consumer, xác nhận consumer cũ vẫn tương thích với mọi record đã được ghi kể từ lúc producer mới bật.

Nếu không tương thích:

- Giữ consumer mới và rollback producer về chế độ dual-write tương thích nếu có thể.
- Tạm dừng phát dữ liệu mới hoặc route sang topic v2 riêng.
- Triển khai hotfix consumer có khả năng đọc cả hai dạng.
- Cách ly record không đọc được vào DLT và replay sau khi sửa.

Không reset offset ngay lập tức để né lỗi deserialization; việc đó có thể bỏ qua record nghiệp vụ.

### 13.2. Rollback producer

Producer có thể quay về schema cũ nếu consumer mới vẫn đọc được record cũ. Nhưng nếu consumer mới đã phụ thuộc field mới là bắt buộc, producer cũ có thể khiến consumer lỗi business validation.

Trong giai đoạn expand, consumer nên giữ fallback để producer cũ vẫn hoạt động. Đây là một lợi ích quan trọng của việc chỉ contract sau khi rollout ổn định.

### 13.3. Replay và offset

Replay có thể làm consumer xử lý lại record cũ, do đó:

- Giữ event ID ổn định qua các phiên bản.
- Làm side effect idempotent hoặc có inbox/deduplication.
- Xác định rõ group nào được reset và topic/partition nào bị ảnh hưởng.
- Dùng `--dry-run` trước khi reset offset bằng Kafka CLI.
- Theo dõi lag, throughput và downstream load trong thời gian replay.

Schema mới cần đọc được dữ liệu cũ trong suốt khoảng thời gian hệ thống cho phép replay, không chỉ trong thời gian rollout.

## 14. Theo dõi migration bằng metric và log

Trong một đợt đổi contract, theo dõi tối thiểu:

- Producer version và schema ID/version đang phát.
- Số record theo từng version/format.
- Deserialization error và validation error theo consumer group.
- Số record vào DLT và tuổi của record lỗi lâu nhất.
- Consumer lag, throughput và processing latency.
- Tỷ lệ record thiếu field mới hoặc vẫn dùng field cũ.
- Số consumer instance còn chạy version cũ.
- Parity giữa topic v1/v2 theo event ID khi dual-write.
- Business invariant như số đơn hàng, tổng tiền hoặc trạng thái cuối.

Log cần có event ID, topic, partition, offset, producer/service version và schema version. Tránh log toàn bộ payload nếu chứa dữ liệu cá nhân hoặc bí mật.

## 15. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Deploy producer mới trước khi consumer sẵn sàng | Consumer cũ có thể lỗi hoặc bỏ qua dữ liệu | Consumer-first hoặc xác minh forward compatibility |
| Thêm field nhưng consumer coi field luôn bắt buộc | Record cũ không có field làm handler lỗi | Consumer mới xử lý missing/null/default |
| Đổi tên field trực tiếp | Consumer cũ không tìm thấy field | Dual-write và dual-read trong giai đoạn expand |
| Xóa field ngay khi producer đã ngừng ghi | Replay record cũ vẫn có thể chứa field/thiếu field mới | Chờ hết replay window và kiểm tra mọi consumer |
| Dựa vào Schema Registry compatibility như bảo đảm nghiệp vụ | Đơn vị/semantics có thể đổi mà schema vẫn hợp lệ | Contract test và business invariant |
| Cho phép consumer cũ nhận enum mới mà không có fallback | Runtime exception hoặc nhánh xử lý sai | Unknown enum policy hoặc nâng consumer trước |
| Dual-write hai topic không có event ID chung | Không deduplicate hoặc reconcile được | Dùng event ID ổn định và kiểm tra parity |
| Giả định hai topic có ordering chung | Event có thể đến khác thứ tự | Dùng version/sequence hoặc migration có điều phối |
| Đổi key trong rolling deploy | Cùng entity có thể đi sang partition khác | Migration key/partition riêng, thường dùng topic v2 |
| Rollback consumer mà không kiểm tra record mới | Consumer cũ không đọc được dữ liệu đã phát | Kiểm tra compatibility trước rollback |
| Reset offset để vượt qua poison message | Bỏ qua dữ liệu chưa xử lý | DLT, sửa consumer và replay có kiểm soát |
| Xóa schema/version đang được record tham chiếu | Consumer không thể giải mã record lịch sử | Giữ schema trong toàn bộ retention/replay window |

## 16. Quy trình rollout mẫu

Với thay đổi additive hoặc rename có thể expand, dùng quy trình sau:

1. **Inventory:** liệt kê producer, consumer group, Kafka Connect connector, Streams topology, batch job và công cụ đọc topic.
2. **Contract:** xác định field/key/header thay đổi, semantics, default và compatibility mode.
3. **Schema check:** đăng ký thử schema mới trên môi trường kiểm thử và chạy compatibility check.
4. **Consumer-first:** deploy consumer có thể đọc cả schema cũ và mới; giữ logic fallback.
5. **Verify consumers:** xác nhận không còn instance hoặc ứng dụng phụ thuộc field cũ nếu bước tiếp theo cần loại bỏ nó.
6. **Producer expand:** phát field mới hoặc dual-write old/new field.
7. **Observe:** theo dõi schema ID, deserialize error, DLT, lag và business invariant.
8. **Contract:** ngừng field cũ sau khi hết consumer cũ và replay window đã được xử lý.
9. **Cleanup:** xóa code fallback/schema field cũ trong release sau; giữ schema version cần thiết để đọc record lịch sử.
10. **Document:** cập nhật owner, version, thời điểm deprecate và quy trình rollback.

Với breaking change lớn, thay bước producer expand bằng tạo topic/subject v2, dual-publish hoặc bridge, cutover consumer và deprecate v1 theo một lịch riêng.

## 17. Checklist trước khi phát hành

- Đã liệt kê mọi producer, consumer group và connector/stream job sử dụng topic chưa?
- Đã phân loại thay đổi là additive, rename, semantic hay breaking chưa?
- Đã xác định backward/forward/full compatibility theo thứ tự deploy chưa?
- Consumer mới đọc được record cũ trong retention/replay window chưa?
- Consumer cũ có cần đọc record mới trong thời gian overlap không?
- Unknown field, unknown enum, null và default đã được kiểm thử chưa?
- Key, partition mapping và ordering có thay đổi không?
- Schema Registry compatibility check đã chạy trên đúng subject chưa?
- Có contract test cho ma trận producer/consumer version chưa?
- Có event ID ổn định và idempotency cho replay/dual-write chưa?
- Có DLT và runbook cho deserialization error không?
- Có metric theo dõi schema version, lag, DLT, parity và business invariant không?
- Đã xác định điều kiện dừng rollout và rollback producer/consumer chưa?
- Chỉ contract/xóa field sau khi consumer cũ và replay window không còn phụ thuộc chưa?

## 18. Câu hỏi tự kiểm tra

1. Vì sao producer và consumer không nên được xem như một đơn vị deploy duy nhất?
2. Backward compatibility và forward compatibility khác nhau như thế nào?
3. Khi thêm field tùy chọn, vì sao thường triển khai consumer trước producer?
4. Khi nào producer-first có thể chấp nhận được?
5. Vì sao Schema Registry compatibility không thể phát hiện việc đổi đơn vị từ VND sang USD?
6. Chiến lược expand-and-contract giải quyết rủi ro nào khi đổi tên field?
7. Consumer dual-read nên ưu tiên field mới và fallback field cũ như thế nào?
8. Vì sao phải chờ replay window trước khi xóa field cũ?
9. Khi nào nên tạo topic v2 thay vì tiếp tục evolution trên topic hiện tại?
10. Dual-write hai topic có những rủi ro duplicate và ordering nào?
11. Vì sao đổi key có thể làm thay đổi ordering theo entity?
12. Cần kiểm thử những cặp producer/consumer version nào trong rollout?
13. Vì sao rollback consumer có thể nguy hiểm sau khi producer đã phát schema mới?
14. DLT giúp migration an toàn như thế nào và giới hạn của nó là gì?
15. Những metric nào giúp xác nhận migration đã hoàn tất?

## Kết luận

Đổi data contract Kafka là một quá trình phối hợp nhiều phiên bản producer, consumer và dữ liệu đã tồn tại trong topic. Với thay đổi additive, thường nâng consumer để đọc được dữ liệu cũ và mới trước khi producer phát field mới. Với rename, dùng dual-read/dual-write rồi loại bỏ field cũ sau replay window. Với thay đổi kiểu, semantics, key hoặc wire format mang tính breaking, cân nhắc topic/contract v2 và cutover có kiểm soát. Compatibility check, contract test, event ID, DLT, metric và kế hoạch rollback giúp migration diễn ra có thể quan sát và phục hồi.
