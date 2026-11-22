# Schema evolution

Trong hệ thống Kafka, cùng một topic có thể tồn tại rất lâu, trong khi producer và consumer liên tục được nâng cấp. Một producer mới có thể bắt đầu phát thêm trường dữ liệu trước khi toàn bộ consumer kịp cập nhật; ngược lại, consumer mới cần đọc cả dữ liệu cũ còn nằm trong topic. **Schema evolution** là quá trình thay đổi cấu trúc message qua nhiều phiên bản mà vẫn duy trì khả năng đọc, xử lý và vận hành an toàn.

Đây không chỉ là câu chuyện thêm hoặc xóa field trong Java DTO. Mọi thay đổi đều ảnh hưởng tới **serialization**, **deserialization**, **khả năng tương thích giữa các phiên bản**, **thứ tự triển khai**, **replay dữ liệu** và cách hệ thống phục hồi record lỗi. Trong Spring Kafka, cần xem schema evolution như một phần của chiến lược độ tin cậy cho cả producer và listener.

## 1. Vấn đề khi producer và consumer không nâng cấp cùng lúc

Giả sử hệ thống có topic `orders.created`. Phiên bản đầu của event chỉ có mã đơn hàng và số tiền:

```json
{
  "orderId": "O-1001",
  "totalAmount": 125000
}
```

Ở phiên bản mới, producer cần bổ sung tiền tệ:

```json
{
  "orderId": "O-1001",
  "totalAmount": 125000,
  "currency": "VND"
}
```

Trong giai đoạn rollout, có thể đồng thời tồn tại:

```text
Producer v1 ----------> Kafka topic <---------- Producer v2
                         |
                         +---- Consumer v1
                         +---- Consumer v2
                         +---- Consumer v3 (replay dữ liệu cũ)
```

Kafka lưu record dưới dạng byte, không tự hiểu Java class hoặc business schema của payload. Việc đọc thành công phụ thuộc vào serializer/deserializer, schema hoặc metadata để xác định schema, và logic xử lý nghiệp vụ.

Một consumer dùng DTO mới có thể không đọc được record cũ nếu `currency` là trường bắt buộc mà không có default. Một consumer cũ có thể lỗi khi thấy field mới nếu deserializer được cấu hình từ chối trường không biết. Dù payload deserialize thành công, nghiệp vụ vẫn có thể xử lý sai nếu ý nghĩa của field thay đổi.

**Schema evolution an toàn** cần làm rõ hai câu hỏi: phiên bản nào có thể đọc dữ liệu của phiên bản nào, và thứ tự triển khai nào không tạo khoảng thời gian gián đoạn?

## 2. Schema compatibility: backward, forward và full

Khả năng tương thích thường được mô tả từ góc nhìn **reader schema** (schema của bên đọc) và **writer schema** (schema được dùng để tạo dữ liệu).

| Chế độ | Quan hệ cần bảo đảm | Tình huống điển hình |
|---|---|---|
| **Backward compatible** | Reader mới đọc được dữ liệu do writer cũ tạo | Consumer mới cần replay event cũ. |
| **Forward compatible** | Reader cũ đọc được dữ liệu do writer mới tạo | Producer mới được deploy trước consumer cũ. |
| **Full compatible** | Hai chiều backward và forward | Có thể đồng thời chạy nhiều phiên bản producer/consumer. |
| **None** | Không kiểm tra compatibility ở registry | Chỉ dùng khi đã có kế hoạch chuyển đổi và cô lập rủi ro rõ ràng. |

Ví dụ, phiên bản `v2` thêm field `currency` có default. Với định dạng như Avro, reader `v2` có thể dùng default khi đọc record `v1` không có trường này; đây là một dạng backward compatibility. Reader `v1` thường có thể bỏ qua field mới do writer `v2` phát; đây là hướng forward compatibility trong trường hợp đơn giản.

### 2.1. Transitive và non-transitive

Nhiều Schema Registry hỗ trợ hai nhóm kiểm tra:

- `BACKWARD`, `FORWARD`, `FULL`: thường so schema mới với phiên bản liền trước hoặc phiên bản được áp dụng theo quy tắc registry.
- `BACKWARD_TRANSITIVE`, `FORWARD_TRANSITIVE`, `FULL_TRANSITIVE`: yêu cầu schema mới tương thích với **tất cả** các phiên bản trước trong phạm vi subject.

Ví dụ có chuỗi `v1 -> v2 -> v3`. `BACKWARD` thông thường không đủ để khẳng định reader `v3` có thể đọc mọi record từng ghi bằng `v1`. Nếu retention lâu, có log compaction hoặc cần replay nhiều năm dữ liệu, kiểm tra **transitive** thường đáng cân nhắc.

**Lưu ý:** compatibility không đồng nghĩa với giữ nguyên *ngữ nghĩa nghiệp vụ*. Schema có thể hợp lệ ở mức field/type nhưng consumer vẫn hiểu sai nếu đơn vị, enum meaning, thời gian hoặc cách tính tiền thay đổi.

## 3. Ví dụ tiến hóa schema với Avro

Avro là định dạng thường được dùng cùng Schema Registry. Một record Avro có thể được giải mã theo cặp writer schema và reader schema: writer schema mô tả dữ liệu đã ghi; reader schema mô tả những trường ứng dụng hiện tại muốn đọc.

Schema `v1`:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" }
  ]
}
```

Schema `v2` thêm `currency` có default:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
```

Khi reader `v2` gặp dữ liệu `v1`, Avro có thể dùng `"VND"` cho trường chưa tồn tại. Khi reader `v1` gặp dữ liệu `v2`, nó có thể bỏ qua `currency`. Đây là một thay đổi thường phù hợp cho rollout nhiều phiên bản, miễn là giả định tiền tệ mặc định đúng với tất cả record lịch sử.

Default là **quyết định nghiệp vụ**, không chỉ là mẹo để schema check đi qua. Nếu đơn hàng cũ có cả USD và VND mà schema không ghi tiền tệ, tự mặc định mọi record là VND sẽ làm sai dữ liệu khi replay.

### 3.1. Optional field và default

Với Avro, một field có thể cho phép giá trị null bằng union:

```json
{
  "name": "couponCode",
  "type": ["null", "string"],
  "default": null
}
```

Field này có thể vắng mặt trong record cũ và reader mới sẽ điền `null`. Nếu ứng dụng xử lý `null`, cần xác định hành vi hợp lệ: không giảm giá, giảm giá mặc định, hay từ chối record. Schema compatibility không tự xác định quy tắc đó.

### 3.2. Các thay đổi Avro cần cẩn trọng

- **Thêm field bắt buộc nhưng không có default:** reader mới có thể không đọc được record cũ.
- **Xóa field:** reader cũ có thể vẫn cần trường đó; tùy default và schema resolution, forward compatibility có thể bị phá.
- **Đổi kiểu field:** không phải mọi thay đổi type đều hợp lệ; một số kiểu số có promotion được Avro hỗ trợ nhưng có thể gây rủi ro nghiệp vụ.
- **Đổi tên field:** có thể cần aliases cùng với reader schema phù hợp; không nên giả định rename là tương thích.
- **Đổi namespace hoặc record name:** ảnh hưởng đến khả năng resolve record và subject naming, cần đánh giá riêng.
- **Đổi enum:** thêm/xóa symbol có thể ảnh hưởng reader cũ; kiểm tra compatibility và default/fallback thích hợp.

Việc schema registry chấp nhận một thay đổi không bảo đảm mã Java hiện tại đã sẵn sàng cho mọi nhánh xử lý của event mới.

## 4. Protobuf và JSON Schema có quy tắc khác

Compatibility phải được đánh giá theo **schema format** chứ không chỉ theo tên mode. Avro, Protobuf và JSON Schema có cơ chế diễn giải field khác nhau.

### 4.1. Protobuf: field number là danh tính quan trọng

Ví dụ Protobuf:

```proto
syntax = "proto3";

package com.example.events;

message OrderCreated {
  string order_id = 1;
  int64 total_amount = 2;
  string currency = 3;
}
```

Field `1`, `2`, `3` được mã hóa theo number. Đổi tên field có thể ít ảnh hưởng tới wire format hơn đổi field number; tuy nhiên, đổi tên vẫn có thể ảnh hưởng JSON mapping, generated code hoặc business API.

Nguyên tắc quan trọng:

- Không tự ý **tái sử dụng field number** từng được cấp cho trường khác.
- Khi xóa field, cân nhắc khai báo `reserved` cho number và tên cũ.
- Không đổi kiểu wire-incompatible hoặc làm thay đổi ý nghĩa của trường hiện tại.
- Xem xét semantics của field presence, default values và enum ở phiên bản Protobuf cụ thể.

Ví dụ:

```proto
message OrderCreated {
  string order_id = 1;
  int64 total_amount = 2;

  reserved 3;
  reserved "legacy_currency";

  string currency_code = 4;
}
```

`reserved` giúp ngăn việc vô tình gán lại number hoặc tên đã loại bỏ. Tuy nhiên, nó không tự chuyển dữ liệu từ trường cũ sang trường mới; migration dữ liệu và logic đọc vẫn cần được thiết kế.

### 4.2. JSON Schema: required, additionalProperties và kiểu dữ liệu

Với JSON Schema, các từ khóa như `required`, `type`, `enum` và `additionalProperties` quyết định dữ liệu nào được chấp nhận.

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "number" },
    "currency": { "type": "string", "default": "VND" }
  },
  "required": ["orderId", "totalAmount"],
  "additionalProperties": true
}
```

Một schema cho phép `additionalProperties` có thể chấp nhận field mới mà reader cũ chưa biết, nhưng ứng dụng Java vẫn có thể cấu hình Jackson nghiêm ngặt và từ chối unknown properties. Ngược lại, một schema registry check pass không có nghĩa consumer sẽ tự thực thi default trong mọi deserializer.

**Khác biệt quan trọng:** từ khóa `default` trong JSON Schema có thể chỉ là annotation; nó không bắt buộc mọi JSON Schema validator hoặc JSON deserializer tự thêm trường thiếu. Không áp dụng máy móc semantics của Avro default cho JSON Schema.

## 5. Schema Registry làm gì và không làm gì?

Một Schema Registry lưu trữ schema theo **subject** và phiên bản, quản lý schema ID cùng quy tắc compatibility. Trong cách tích hợp phổ biến của Confluent Schema Registry, serializer ghi schema ID vào wire format để deserializer biết schema writer của record.

```text
Producer
  | 1. Đăng ký hoặc tra schema writer
  | 2. Serialize payload + schema identifier
  v
Kafka topic (opaque bytes)
  |
  | 3. Consumer lấy schema writer theo ID
  | 4. Deserialize/resolve theo reader model
  v
Spring Kafka listener
```

Đây là mô hình minh họa cho serializer tích hợp Registry theo wire format tương ứng. Kafka broker **không tự gọi Registry để xác thực từng record**; serializer/deserializer và tooling của hệ sinh thái đảm nhận phần đó.

Registry giúp:

- Lưu và tra cứu schema theo subject/version/ID.
- Chặn đăng ký schema không phù hợp với compatibility policy.
- Giúp consumer xác định writer schema trong các định dạng tích hợp.
- Hỗ trợ CI kiểm tra schema trước khi deploy.

Registry **không** tự bảo đảm:

- Dữ liệu cũ có ý nghĩa nghiệp vụ phù hợp với reader mới.
- Consumer cũ thực sự chấp nhận unknown field hoặc enum mới.
- Side effect với database/API được rollback khi deserialization thất bại.
- Record bị lỗi được retry, gửi DLT hoặc replay đúng.
- Tất cả client và serializer đều dùng Registry đúng cách.

## 6. Subject naming và phạm vi compatibility

Trong mô hình Schema Registry, **subject** là phạm vi quản lý phiên bản và compatibility. Subject không nhất thiết đồng nghĩa với một topic vật lý.

Các chiến lược đặt tên subject phổ biến:

| Chiến lược | Ý nghĩa khái quát | Khi dùng |
|---|---|---|
| Topic-based (ví dụ `TopicNameStrategy`) | Subject theo topic và key/value, chẳng hạn `orders.created-value` | Một loại event chính trên mỗi topic. |
| Record-based (`RecordNameStrategy`) | Subject theo tên record/schema | Chia sẻ loại record trên nhiều topic. |
| Topic + record (`TopicRecordNameStrategy`) | Kết hợp topic và record name | Nhiều event type trong một topic, kiểm soát theo topic. |

Tên và hỗ trợ cụ thể tùy serializer/registry vendor. Cần áp dụng nhất quán trên cả producer, consumer và pipeline CI.

Nếu hai event type khác nhau vô tình cùng subject và policy compatibility không phù hợp, việc đăng ký schema có thể bị chặn hoặc dẫn đến governance khó hiểu. Nếu một type có nhiều subject độc lập, compatibility được kiểm tra theo các lịch sử version khác nhau; điều này có thể làm giảm tính nhất quán nếu không có quy định.

Đừng nhầm **topic naming** với **subject naming**. Retry/DLT topic của Spring Kafka là topic Kafka; schema subject phụ thuộc chiến lược serializer. Khi record được chuyển sang DLT, cần xác định serializer dùng schema nào và liệu subject trong DLT có được tổ chức mong muốn hay không.

## 7. Cấu hình Spring Kafka với schema-aware serializer/deserializer

Với Spring Boot và Confluent Avro SerDes, cấu hình minh họa:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        schema.registry.url: http://localhost:8081
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        schema.registry.url: http://localhost:8081
        specific.avro.reader: true
```

Ví dụ trên yêu cầu thư viện Avro SerDes tương ứng trong classpath và model generated code phù hợp. URL chỉ là môi trường local minh họa. Trong production, cần bảo vệ Registry bằng TLS/authentication và cấu hình serializer với credentials theo quy định.

Khi `specific.avro.reader: true`, consumer dùng specific Avro class khi phù hợp. Nếu muốn đọc `GenericRecord`, chiến lược model có thể khác. Hãy giữ cùng quy tắc serializer, subject và schema evolution giữa các service tham gia.

### 7.1. Tích hợp ErrorHandlingDeserializer

Nếu deserializer ném exception trước khi Spring Kafka gọi listener, business listener **không nhận được payload** để tự xử lý lỗi. Spring Kafka cung cấp `ErrorHandlingDeserializer` để ghi lại lỗi deserialize, giúp error handler/recoverer xử lý record theo chính sách.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: io.confluent.kafka.serializers.KafkaAvroDeserializer
        schema.registry.url: http://localhost:8081
        specific.avro.reader: true
```

Khi delegate deserializer thất bại do schema không hợp lệ, thiếu schema writer, Registry không khả dụng hoặc dữ liệu hỏng, `ErrorHandlingDeserializer` giúp container nhận diện lỗi để error handler quyết định recovery.

Không mặc định retry vô hạn cho lỗi schema: một record sai format vĩnh viễn sẽ không tự sửa sau mỗi lần retry. Một số lỗi Registry/network tạm thời có thể phục hồi, nhưng lỗi payload/schema không tương thích thường cần cách ly và điều tra.

### 7.2. Publish record lỗi tới DLT

Khi record deserialize thất bại, recoverer có thể cần phát **raw bytes** tới DLT thay vì Java object thông thường. Vì vậy, KafkaTemplate dùng cho DLT phải có serializer tương thích với các kiểu dữ liệu mà recoverer có thể gửi.

Nếu chỉ cấu hình `KafkaAvroSerializer` nhưng recoverer gửi `byte[]` từ record lỗi deserialization, serialization khi publish DLT có thể thất bại tùy cấu hình. Có thể dùng `DelegatingByTypeSerializer` hoặc KafkaTemplate riêng với serializer phù hợp để xử lý cả object bình thường lẫn raw bytes. Thiết kế này cần được kiểm thử với chính loại lỗi mà production có thể gặp.

DLT nên bảo tồn key, raw data hoặc payload cần thiết, topic/partition/offset gốc và exception metadata. Hạn chế log toàn bộ dữ liệu nếu có thông tin nhạy cảm. Phân biệt lỗi dữ liệu vĩnh viễn với lỗi kết nối Registry để tránh đưa nhầm sự cố tạm thời thành lỗi nghiệp vụ cuối cùng.

## 8. Quy trình rollout an toàn cho một thay đổi schema

Một migration tốt thường theo hướng **expand -> migrate -> contract**, tức là mở rộng khả năng đọc trước khi producer gửi định dạng mới, sau đó mới loại bỏ hỗ trợ cũ khi chắc chắn không còn cần.

Ví dụ muốn thêm `currency`:

1. **Thiết kế schema v2 tương thích:** field mới có default hoặc optional semantics phù hợp.
2. **Kiểm tra ở CI:** xác thực tương thích schema với Registry và kiểm tra reader của ứng dụng.
3. **Deploy consumer chấp nhận cả v1 và v2:** listener/DTO không giả định chỉ có dữ liệu mới.
4. **Deploy producer ghi v2:** theo dõi lỗi serialize và deserialize trên từng service.
5. **Theo dõi thời gian chuyển tiếp:** còn consumer cũ, retry/DLT listener cũ hoặc job replay cũ hay không?
6. **Chỉ contract khi đủ điều kiện:** bỏ field cũ hoặc nâng compatibility policy cần kế hoạch rõ ràng, đặc biệt nếu dữ liệu cũ còn trong retention.

Sơ đồ:

```text
Giai đoạn A:   Producer v1 ---> topic ---> Consumer v1
Giai đoạn B:   Producer v1 ---> topic ---> Consumer v2 (đọc v1 + v2)
Giai đoạn C:   Producer v2 ---> topic ---> Consumer v2
Giai đoạn D:   Consumer v2 vẫn đọc được bản ghi cũ khi replay
```

Với hệ thống nhiều consumer group, không chỉ nâng cấp consumer chính. Các service phụ, analytics job, retry/DLT consumer và tool replay cũng là reader của topic; một consumer ít dùng nhưng vẫn chạy production có thể là điểm gây lỗi khi producer đổi format.

Nếu không có cách làm schema tương thích, cân nhắc **event type hoặc topic mới**, dual-write trong giai đoạn chuyển đổi và một chiến lược cutover/rollback minh bạch. Không ép dữ liệu không tương thích vào cùng luồng rồi hy vọng mọi consumer tự xử lý.

## 9. Replay, retention và log compaction

Kafka thường giữ dữ liệu theo retention hoặc log compaction; record cũ có thể được đọc lại khi:

- Consumer group reset offset.
- Tạo consumer group mới cho analytics hoặc migration.
- DLT được sửa nguyên nhân và replay về topic nghiệp vụ.
- Khôi phục state của một stateful consumer.
- Reprocess lịch sử sau khi phát hiện lỗi tính toán.

Vì vậy, compatibility không chỉ cần đúng trong lúc rolling deployment. **Reader mới phải có chiến lược đọc record cũ còn tồn tại**, đặc biệt với `BACKWARD_TRANSITIVE` nếu topic chứa nhiều schema version lâu dài.

Tombstone trong topic compacted thường có value null. Hãy thiết kế listener và serializer xử lý tombstone rõ ràng; đừng diễn giải value null là record bị hỏng schema trong mọi trường hợp.

Nếu schema cũ bị xóa khỏi Registry trong khi Kafka vẫn giữ record tham chiếu schema ID đó, deserializer có thể không resolve được dữ liệu lịch sử. Quản lý lifecycle của schema ID, subject và registry retention cẩn thận; tránh xóa schema khi còn cần replay hoặc DLT recovery.

## 10. Schema compatibility khác semantic compatibility

Một số thay đổi hợp lệ về cấu trúc vẫn phá vỡ nghiệp vụ:

| Thay đổi | Schema có thể chấp nhận? | Nguy cơ nghiệp vụ |
|---|---|---|
| Thêm trường `currency` có default | Có thể | Default sai với dữ liệu lịch sử. |
| Giữ kiểu `long` nhưng đổi đơn vị tiền từ đồng sang cent | Có thể | Consumer tính sai số tiền. |
| Thêm enum value mới | Tùy format/policy | Reader cũ không biết nhánh enum mới. |
| Đổi `orderId` thành ID có ý nghĩa khác nhưng vẫn là string | Có thể | Deduplication, partitioning và join bị sai. |
| Thay đổi meaning của timestamp, vẫn dùng long | Có thể | Lệch timezone, event-time hoặc retention logic. |
| Bỏ một field cũ ít dùng | Tùy policy | Job batch hoặc DLT replay vẫn phụ thuộc vào field. |

Vì vậy, event contract nên mô tả cả **đơn vị, tính bắt buộc, ý nghĩa null, enum semantics, nguồn tạo dữ liệu và invariants nghiệp vụ**. Không xem việc registry trả về “compatible” là đủ để triển khai.

Với thay đổi có ý nghĩa nghiệp vụ khác hẳn, việc tạo event type mới (`OrderCreatedV2`) hoặc topic mới có thể an toàn hơn việc giữ tên nhưng đổi semantics.

## 11. Schema ID, cache và Registry availability

SerDes tích hợp Schema Registry thường cache schema metadata trong client để tránh phải gọi Registry cho từng record. Điều này cải thiện hiệu năng nhưng có các hệ quả:

- Một producer có thể vẫn gửi dữ liệu với schema ID đã cache trong lúc Registry tạm gián đoạn.
- Một consumer nhận schema ID chưa từng thấy có thể cần truy vấn Registry; lỗi network khiến deserialization thất bại tạm thời.
- Schema ID hoặc subject không tồn tại đúng môi trường có thể gây lỗi không thể xử lý bằng retry đơn thuần.
- Rollout thêm schema mới cần đảm bảo Registry và quyền truy cập sẵn sàng ở môi trường đích.

Không mặc định coi mọi exception liên quan Schema Registry là lỗi payload vĩnh viễn. Hãy phân loại: timeout/authentication/connection, subject/version không tồn tại, schema không tương thích, payload không đúng wire format và lỗi ứng dụng.

Theo dõi cả Kafka consumer lag lẫn tình trạng Registry. Nếu Registry gặp sự cố, nhiều consumer có thể cùng lỗi deserialize khi gặp schema ID mới, dẫn đến retry storm hoặc DLT tăng đột biến.

## 12. CI/CD và contract testing

Để ngăn lỗi schema xuất hiện ở production, nên kiểm tra **trước khi deploy**:

1. Validate cú pháp schema Avro/Protobuf/JSON Schema.
2. Kiểm tra compatibility với subject và policy đúng môi trường.
3. Tạo serializer/deserializer thực tế của ứng dụng để thử đọc/ghi.
4. Dùng **golden messages** từ các schema version cũ; xác nhận code mới đọc và xử lý đúng.
5. Kiểm tra code cũ đọc dữ liệu mới nếu rollout cần forward compatibility.
6. Kiểm tra các giá trị null, field thiếu, enum không biết, record malformed.
7. Kiểm tra deserialization failure đi vào recovery/DLT đúng, không mất raw data.
8. Thử replay record cũ và record từ DLT bằng phiên bản consumer mới.

Ví dụ bộ case:

| Writer schema | Reader code | Kỳ vọng |
|---|---|---|
| v1 | consumer v1 | Đọc như hiện tại. |
| v1 | consumer v2 | Đọc được và áp dụng default hợp lệ. |
| v2 | consumer v1 | Không lỗi nếu yêu cầu forward compatibility. |
| v2 | consumer v2 | Đọc đủ field mới. |
| Unknown schema ID | consumer v2 | Bắt lỗi deserialize, có recovery/alert. |
| Malformed payload | consumer v2 | Không làm container lỗi vô hạn; đi vào DLT phù hợp. |

Không chỉ mock Java DTO. Cần kiểm tra **bytes được serialize thực tế** vì lỗi wire format, schema ID, enum và type resolution có thể không xuất hiện trong unit test gọi thẳng listener method.

## 13. Quan sát schema evolution trong vận hành

Khi deploy schema version mới, theo dõi:

- Số record theo schema ID/version ở producer và consumer nếu có công cụ thống kê phù hợp.
- Tỷ lệ lỗi serialize/deserialize, đặc biệt sau rollout.
- Lỗi Schema Registry (timeout, authorization, subject not found).
- Consumer lag theo topic/partition và phiên bản ứng dụng.
- Số record vào retry/DLT và loại exception đi kèm.
- Tỷ lệ event phải dùng default/fallback của schema cũ.
- Thời gian hoàn tất rollout của tất cả consumer group phụ thuộc.

Logging nên liên kết `topic`, `partition`, `offset`, `eventId`, consumer version và thông tin schema cần thiết. Tránh log payload hoặc raw bytes nếu chứa dữ liệu nhạy cảm.

Một đợt tăng `SerializationException`, `RecordDeserializationException` hoặc exception từ delegate deserializer sau khi producer mới triển khai là tín hiệu cần kiểm tra schema/wire format ngay. Tuy nhiên, exception cụ thể phụ thuộc library và việc dùng `ErrorHandlingDeserializer`.

Khi cần rollback, hãy phân biệt rollback **producer code** với rollback **schema trong Registry**. Record đã ghi bằng schema mới vẫn còn trong Kafka; đưa producer về code cũ không xóa chúng. Registry subject/version cũng không nên bị xóa bừa bãi vì consumer có thể cần schema ID cũ và mới để giải mã dữ liệu tồn.

## 14. Lỗi thường gặp khi thay đổi schema

- **Thêm field bắt buộc không có default:** consumer mới không đọc được record cũ.
- **Thay đổi semantics nhưng giữ nguyên kiểu:** schema check pass, nghiệp vụ vẫn sai.
- **Chỉ kiểm tra version liền trước:** replay record rất cũ vẫn có thể lỗi nếu không bảo đảm transitive.
- **Nâng producer trước khi reader sẵn sàng:** consumer cũ có thể không đọc được dữ liệu mới.
- **Tăng số field enum mà không có fallback:** consumer cũ có thể gặp giá trị không biết.
- **Thay đổi Protobuf field number hoặc tái sử dụng number cũ:** nguy cơ giải mã sai và phá tương thích.
- **Giả định JSON Schema default tự chèn field:** behavior phụ thuộc validator và deserializer.
- **Không test DLT/retry:** record lỗi schema có thể không được publish vì serializer của DLT không hỗ trợ raw bytes.
- **Xóa schema trong Registry khi còn dữ liệu cũ:** mất khả năng resolve schema ID khi replay.
- **Chỉ test happy path DTO:** bỏ sót lỗi wire format, schema ID và compatibility thật.
- **Nhầm topic với subject:** áp policy sai phạm vi hoặc không kiểm soát cùng một record type trên nhiều topic.
- **Rollback code rồi coi mọi thứ trở về v1:** record v2 đã ghi vẫn tồn tại và được đọc lại.

## 15. Hướng dẫn chọn chiến lược trong production

| Bối cảnh | Chiến lược nên cân nhắc |
|---|---|
| Consumer phải replay toàn bộ lịch sử | Backward transitive, golden message tests nhiều version. |
| Producer deploy trước consumer | Cần forward compatibility hoặc rollout reader trước. |
| Nhiều producer và consumer cùng tồn tại | Full/full transitive nếu format và business contract cho phép. |
| Bổ sung field mới | Optional/default hợp lệ, triển khai reader tolerant trước. |
| Thay đổi ý nghĩa hoặc kiểu dữ liệu lớn | Event type/topic mới và migration có kiểm soát. |
| Dữ liệu schema lỗi hoặc unknown ID | `ErrorHandlingDeserializer`, phân loại lỗi và DLT phù hợp. |
| DLT/replay chứa dữ liệu nhiều version | Bảo tồn schema ID/wire bytes, dùng serializer/recoverer đúng loại. |
| Schema Registry là dependency quan trọng | Giám sát availability, authentication, cache và registry governance. |

**Schema evolution** thành công không phải chỉ là đăng ký schema mới. Đó là khả năng để writer cũ và mới, reader cũ và mới, DLT/retry consumer và công cụ replay cùng xử lý dữ liệu một cách có thể dự đoán. Khi kết hợp compatibility policy, rollout theo hướng expand-contract, kiểm thử serialized bytes và recovery có chủ đích, Spring Kafka có thể thay đổi event contract mà vẫn duy trì độ tin cậy trong toàn bộ vòng đời dữ liệu.
