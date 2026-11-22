# Schema Registry trong vận hành

Trong hệ thống Kafka, broker lưu **bytes** của key, value và headers, chứ không tự hiểu các field nghiệp vụ như `orderId`, `amount` hay `createdAt`. Khi dữ liệu được trao đổi bằng Avro, Protobuf hoặc JSON Schema, producer và consumer cần thống nhất cách mã hóa, giải mã và thay đổi cấu trúc thông điệp. **Schema Registry** là dịch vụ quản lý schema, phiên bản và quy tắc tương thích, giúp các ứng dụng thay đổi độc lập mà giảm nguy cơ một lần triển khai làm consumer không thể deserialize dữ liệu.

Ở góc nhìn **Spring Kafka Reliability Operations**, Schema Registry không chỉ là nơi lưu file schema. Đây còn là một **dependency lúc khởi động hoặc khi gặp schema chưa có trong cache**, một ranh giới kiểm soát thay đổi dữ liệu, và một thành phần cần giám sát khi xử lý sự cố consumer. Nếu chỉ kiểm tra pod đã `Ready` mà không quan sát deserialize error, schema registration và consumer lag, một thay đổi schema không tương thích vẫn có thể làm luồng xử lý dừng hoặc đưa nhiều record vào DLT.

Bài học dùng **Confluent Schema Registry và serializer/deserializer tương thích** làm ví dụ. Các sản phẩm registry khác có thể hỗ trợ API, định danh subject hoặc wire format khác; không mặc định mọi Schema Registry đều sử dụng cơ chế giống nhau.

## 1. Các thành phần trong luồng dữ liệu

Một kiến trúc điển hình:

```text
                    +-------------------------+
                    |     Schema Registry     |
                    | subject / version / id  |
                    | compatibility policy    |
                    +------------+------------+
                                 ^
                         lookup / register
                                 |
     +------------------+        |        +---------------------+
     | Producer         |--------+        | Spring Kafka        |
     | KafkaAvro        |                 | KafkaAvro           |
     | Serializer       |                 | Deserializer        |
     +--------+---------+                 +----------+----------+
              |                                      ^
              | bytes + schema ID                    | bytes
              v                                      |
        +-----+--------------------------------------+-----+
        |            Kafka topic: orders                  |
        | partition 0 | partition 1 | partition 2         |
        +------------------------------------------------+
```

Producer dùng schema để serialize record và có thể đăng ký hoặc tra cứu schema ID tại Registry. Kafka broker lưu record đã mã hóa. Consumer nhận bytes, đọc metadata schema ID theo wire format của serializer, tra cứu schema tương ứng khi cần, rồi deserialize thành object hoặc cấu trúc mà listener xử lý.

**Điểm cần nhớ:** Kafka broker thường vẫn có thể lưu và phân phối record khi Registry gặp sự cố. Nhưng producer hoặc consumer có thể thất bại nếu cần đăng ký/tra cứu schema mà không thể kết nối Registry. Đây là lý do một sự cố Schema Registry có thể biểu hiện thành lỗi ứng dụng hoặc consumer lag, dù broker Kafka vẫn healthy.

## 2. Schema, subject, version và schema ID

Bốn khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa vận hành |
|---|---|
| **Schema** | Định nghĩa cấu trúc dữ liệu: tên field, kiểu, quy tắc mã hóa và metadata. |
| **Subject** | Không gian đặt tên để quản lý các phiên bản và quy tắc compatibility của một chuỗi schema. |
| **Version** | Thứ tự phiên bản bên trong **một subject**, ví dụ 1, 2, 3. |
| **Schema ID** | Định danh schema được Registry cấp; serializer có thể nhúng ID vào message để consumer truy xuất schema. |

Ví dụ:

```text
Subject: orders-value
  version 1 -> schema ID 101
  version 2 -> schema ID 117
  version 3 -> schema ID 125

Topic: orders
  partition 0:
    record A -> schema ID 101
    record B -> schema ID 117
    record C -> schema ID 125
```

Các ID trong ví dụ chỉ mang tính minh họa. **Version không phải schema ID**: version gắn với lịch sử của subject, còn ID định danh nội dung schema theo cơ chế của Registry. Một schema có thể được tham chiếu từ nhiều subject hoặc version, nên không được suy ra `schema ID = version`.

Với định dạng wire truyền thống của **Confluent Avro serializer**, payload thường bắt đầu bằng một magic byte và bốn byte schema ID, sau đó là dữ liệu được mã hóa. Consumer dùng ID để tìm writer schema. **Đây là quy ước wire format của Confluent**, không phải quy tắc chung cho mọi message Kafka, không phải JSON thuần và cũng không phải broker tự chèn vào record. Với Protobuf và các định dạng khác, cấu trúc phần metadata đi kèm có thêm chi tiết riêng.

## 3. Subject naming strategy ảnh hưởng đến khả năng vận hành

Theo cấu hình mặc định phổ biến của Confluent serializers, schema của value cho topic `orders` được quản lý dưới subject `orders-value`, còn schema của key ở `orders-key`.

Những strategy thường gặp:

| Strategy | Ý tưởng | Lưu ý |
|---|---|---|
| `TopicNameStrategy` | Subject theo topic và key/value, ví dụ `orders-value`. | Các kiểu record dùng chung subject phải thỏa quy tắc compatibility của subject đó. |
| `RecordNameStrategy` | Subject dựa trên tên đầy đủ của record. | Cho phép mô hình schema theo record, nhưng yêu cầu producer và consumer thống nhất strategy. |
| `TopicRecordNameStrategy` | Subject kết hợp topic và tên record. | Tách compatibility theo record trong phạm vi topic. |

Tên subject không tự nói lên topic thật nếu hệ thống đã thay strategy. Khi xử lý lỗi `subject not found` hoặc schema bị đăng ký sai nơi, hãy kiểm tra cả **topic, key/value side và subject naming strategy**, không chỉ kiểm tra một tên subject dự đoán.

Việc đổi strategy giữa các phiên bản ứng dụng là một thay đổi giao thức dữ liệu, không phải thao tác đổi tên đơn giản. Nó có thể khiến producer đăng ký schema ở subject mới và làm pipeline CI/CD, quyền truy cập Registry hoặc contract validation không còn áp dụng như trước.

## 4. Compatibility là hợp đồng triển khai giữa các phiên bản

Registry có thể kiểm tra schema mới so với lịch sử schema của một subject khi đăng ký. Các chế độ thông dụng:

| Chế độ | Ý nghĩa cơ bản |
|---|---|
| `BACKWARD` | Reader dùng schema **mới** có thể đọc dữ liệu viết bằng schema **trước đó**. |
| `FORWARD` | Reader dùng schema **trước đó** có thể đọc dữ liệu viết bằng schema **mới**. |
| `FULL` | Kết hợp backward và forward. |
| `NONE` | Không yêu cầu kiểm tra compatibility. |
| `BACKWARD_TRANSITIVE`, `FORWARD_TRANSITIVE`, `FULL_TRANSITIVE` | Kiểm tra với **tất cả các phiên bản trước**, thay vì chỉ phiên bản gần nhất. |

Ví dụ với Avro, phiên bản đầu tiên:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amount", "type": "long" }
  ]
}
```

Phiên bản mới muốn bổ sung ghi chú tùy chọn:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amount", "type": "long" },
    {
      "name": "note",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
```

Field `note` có default `null` giúp reader mới xử lý dữ liệu cũ không có trường đó. Đây là một cách thường dùng để phát triển schema theo hướng backward-compatible. Ngược lại, xóa field bắt buộc hoặc đổi kiểu không tương thích có thể bị Registry từ chối tùy policy.

**Thứ tự triển khai cũng quan trọng.** Với backward compatibility, đội phát triển thường có thể triển khai consumer mới trước để đọc dữ liệu cũ, rồi triển khai producer tạo dữ liệu mới. Nếu ứng dụng có nhiều phiên bản chạy song song, cần xác định cả yêu cầu reader cũ đọc writer mới; chỉ kiểm tra một chiều có thể chưa đủ. Các quy tắc compatibility cụ thể khác nhau giữa Avro, Protobuf và JSON Schema; không áp dụng máy móc ví dụ Avro cho mọi định dạng.

## 5. Chính sách compatibility không thay thế contract test

Compatibility ở cấp schema kiểm tra khả năng đọc/ghi theo định nghĩa schema, **không hiểu toàn bộ ý nghĩa nghiệp vụ**. Ví dụ, field `status` vẫn là `string`, nhưng producer bắt đầu gửi giá trị `REFUNDED` mà consumer cũ chưa hỗ trợ; schema vẫn có thể tương thích trong khi listener ném exception.

Các lớp bảo vệ nên kết hợp:

1. **Schema compatibility check:** kiểm tra cú pháp và khả năng tương thích trước khi đăng ký.
2. **Contract test:** bảo đảm consumer xử lý được các giá trị và quy ước nghiệp vụ quan trọng.
3. **Integration test:** dùng serializer/deserializer thực tế và một Registry thử nghiệm.
4. **Rollout có kiểm soát:** triển khai theo thứ tự đã thống nhất, quan sát lỗi deserialize và consumer lag.
5. **DLT/recovery:** giữ bằng chứng về record không xử lý được mà không làm mất dữ liệu một cách âm thầm.

Registry có thể ngăn schema không tương thích được đăng ký **qua API đăng ký có kiểm tra**. Nhưng nếu một producer tự đóng gói bytes sai format hoặc dùng sai schema ID, broker không tự xác nhận tính đúng đắn của payload.

## 6. Cấu hình Spring Boot với Confluent Avro

Ví dụ một service vừa publish vừa consume event Avro do schema compiler tạo class `OrderCreated`:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    properties:
      "[schema.registry.url]": "http://schema-registry:8081"
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        "[auto.register.schemas]": false
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

Các property nằm trong `spring.kafka.properties` áp dụng chung theo cách Spring Boot xây dựng client properties; producer/consumer properties có thể ghi đè theo phạm vi. Dấu ngoặc `"[... ]"` trong ví dụ YAML nhằm giữ nguyên dấu chấm trong key map cấu hình; không truyền dấu ngoặc đó cho Kafka client. Khi đưa vào ứng dụng, dùng đúng cú pháp Spring Boot cho phiên bản đang chạy.

`KafkaAvroSerializer` và `KafkaAvroDeserializer` là thư viện Confluent, cần thêm dependency phù hợp trong build. Spring Kafka không tự tải serializer này chỉ vì khai báo URL Registry. Nếu muốn listener nhận Avro class được generate (`SpecificRecord`), `specific.avro.reader=true` giúp deserializer chọn specific reader; nếu không, nó thường trả về `GenericRecord`.

Khi cấu hình `auto.register.schemas=false` ở producer, schema phải đã được đăng ký trước theo subject naming strategy và cấu hình serializer. Chế độ này phù hợp khi muốn CI/CD là nơi duy nhất có quyền đăng ký schema production. Nếu chưa có schema tương ứng, producer có thể thất bại khi serialize/send; đừng bật chế độ này mà không tạo bước đăng ký schema trước deployment.

## 7. Thêm ErrorHandlingDeserializer cho consumer

Lỗi deserialize xảy ra trong quá trình `poll()`, **trước khi listener được gọi**. Vì vậy `try/catch` bên trong phương thức `@KafkaListener` không bắt được lỗi như schema ID không tồn tại, payload sai định dạng hoặc không tương thích với deserializer.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để chuyển lỗi deserialization thành thông tin mà listener container/error handler có thể xử lý. Có thể bọc Confluent deserializer như sau:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": io.confluent.kafka.serializers.KafkaAvroDeserializer
        "[schema.registry.url]": "http://schema-registry:8081"
        "[specific.avro.reader]": true
```

Nếu key cũng mã hóa bằng Avro hoặc một format có khả năng lỗi deserialization, có thể bọc key deserializer tương tự. `ErrorHandlingDeserializer` đặt thông tin lỗi vào header theo giao thức Spring Kafka và cho phép container chuyển bản ghi thất bại tới error handler, thay vì để lỗi trong `poll()` khiến consumer không tiến triển theo cách mong đợi.

Ví dụ đăng ký `DefaultErrorHandler` với DLT recoverer:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
```

Các exception deserialization thường thuộc nhóm **không nên retry cùng bytes liên tục**; nhiều phiên bản `DefaultErrorHandler` đã phân loại một số exception liên quan là fatal/non-retryable theo mặc định. Hãy kiểm tra classifier thực tế. Một schema ID không tra cứu được do Registry đang tạm thời down có thể có chiến lược xử lý khác với payload thực sự hỏng; tránh gửi mọi record sang DLT quá sớm nếu root cause là dependency outage toàn hệ thống.

**Đặc biệt với DLT của deserialization error:** value có thể cần publish lại dưới dạng bytes gốc, không phải `OrderCreated`. Producer DLT phải có serializer hỗ trợ kiểu dữ liệu nhận được; có thể sử dụng `DelegatingByTypeSerializer`, nhiều `KafkaTemplate` hoặc cấu hình recovery phù hợp. Nếu serializer của DLT chỉ nhận Avro object mà recoverer gửi `byte[]`, chính bước publish DLT có thể thất bại. Cần xác minh pipeline này bằng kiểm thử tích hợp.

## 8. Vận hành khi Registry không khả dụng

Schema Registry là dependency có state và API. Khi Registry bị chậm, trả lỗi 5xx, timeout hoặc không thể xác thực, có thể xuất hiện các tình huống:

| Thành phần | Hành vi có thể gặp |
|---|---|
| Producer dùng schema chưa có trong local cache | Không tra cứu/đăng ký được ID, nên serialize/send thất bại. |
| Consumer gặp schema ID chưa có trong cache | Không lấy được writer schema, nên deserialize thất bại. |
| Consumer đang dùng ID đã cache | Có thể tiếp tục deserialize một thời gian mà không cần gọi Registry cho ID đó. |
| Pod mới khởi động sau outage | Cache thường trống, nên có thể lỗi ngay dù các pod cũ vẫn hoạt động. |

Khả năng cache phụ thuộc thư viện client, cấu hình và nội dung từng schema. Không coi “pod cũ vẫn đọc được” là bằng chứng Registry không quan trọng. Một restart hoặc nhận record từ schema version mới có thể làm lỗi xuất hiện ngay.

Khi điều tra outage, hãy kiểm tra từ **ứng dụng đến Registry**, không chỉ kiểm tra health endpoint của Registry từ máy vận hành. DNS, TLS certificate, Service/Ingress, network policy, auth và quota cũng có thể ngăn client kết nối.

Một quy trình an toàn khi Registry gặp sự cố:

1. Xác định lỗi có nằm ở Registry, network, TLS/auth hay schema ID/subject cụ thể.
2. Tạm dừng rollout producer phát schema mới và rollout consumer mới nếu đang làm tăng lỗi.
3. Kiểm tra độ trễ Registry, tỷ lệ 4xx/5xx, timeout và số instance bị ảnh hưởng.
4. Hạn chế restart hàng loạt các consumer vẫn đang hoạt động nhờ cache.
5. Theo dõi producer send failures, deserialize errors, lag và DLT ingress.
6. Khôi phục Registry và xác nhận client tra cứu schema trở lại trước khi tiếp tục rollout.

Không nên “chữa cháy” bằng cách vô hiệu compatibility hoặc đổi `schema.registry.url` sang một Registry khác không có cùng dữ liệu/ID. Schema ID không mặc nhiên tương đương giữa hai Registry độc lập.

## 9. Cách kiểm tra Registry qua API

Confluent Schema Registry cung cấp HTTP API để kiểm tra subject, version, schema ID và compatibility policy. Từ môi trường có quyền truy cập đến Registry:

```bash
# Liệt kê subject hiện có
curl -fsS http://schema-registry:8081/subjects

# Xem phiên bản mới nhất của subject orders-value
curl -fsS \
  http://schema-registry:8081/subjects/orders-value/versions/latest

# Tra cứu schema theo ID đã thấy trong log
curl -fsS http://schema-registry:8081/schemas/ids/117

# Xem chính sách compatibility của subject
curl -fsS http://schema-registry:8081/config/orders-value
```

Ví dụ kết quả `/subjects/orders-value/versions/latest`:

```json
{
  "subject": "orders-value",
  "version": 3,
  "id": 125,
  "schema": "{...}"
}
```

Output ở trên được rút gọn để dễ đọc; ID, version và nội dung schema thực tế lấy từ Registry. Nếu API trả `404`, cần phân biệt subject không tồn tại với schema ID không tồn tại. Nếu `401/403`, kiểm tra authentication/authorization. Nếu `429` hoặc `5xx`, kiểm tra quota, tài nguyên và độ sẵn sàng của Registry.

Trong môi trường bật HTTPS và xác thực, dùng URL/CA và cơ chế auth tương ứng với tổ chức. Không nhúng token hoặc mật khẩu thật vào script lưu trong git hay command history. Khi cần kiểm tra từ Kubernetes, chạy từ một pod công cụ được cấp quyền phù hợp thay vì mở Registry ra Internet chỉ để debug.

## 10. Kiểm tra compatibility trước khi đăng ký

Một pipeline phát hành nên thực hiện compatibility check trước khi publish schema mới. Với Confluent Registry, endpoint có dạng:

```text
POST /compatibility/subjects/{subject}/versions/latest
```

Body được gửi theo định dạng API; với Avro, trường `schema` chứa **JSON schema đã escape thành một chuỗi**. Ví dụ file `compatibility-request.json`:

```json
{
  "schemaType": "AVRO",
  "schema": "{\"type\":\"record\",\"name\":\"OrderCreated\",\"namespace\":\"com.example.events\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amount\",\"type\":\"long\"},{\"name\":\"note\",\"type\":[\"null\",\"string\"],\"default\":null}]}"
}
```

Gửi yêu cầu kiểm tra:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data-binary @compatibility-request.json \
  http://schema-registry:8081/compatibility/subjects/orders-value/versions/latest
```

Kết quả thường chứa trường `is_compatible`. Một kết quả `true` không thay thế việc kiểm tra nghiệp vụ. Nếu muốn kiểm tra mọi phiên bản cũ, cần cấu hình policy transitive hoặc quy trình kiểm tra tương đương; không chỉ nhìn `latest` rồi suy ra mọi schema cũ đều tương thích.

**Không tự động đăng ký schema ở production chỉ vì compatibility test thành công.** Nên tách bước validate, review và register theo quyền hạn của pipeline. Đăng ký schema là một hành động thay đổi metadata dùng chung giữa nhiều dịch vụ.

## 11. Rollout producer/consumer có kiểm soát

Khi thay đổi một event contract, phải tính đến thời gian mà producer cũ, producer mới, consumer cũ và consumer mới cùng tồn tại.

Ví dụ rollout backward-compatible:

```text
T0: Producer v1 -> Avro schema v1 -> Consumer v1

T1: Đăng ký schema v2 và chạy compatibility check

T2: Deploy Consumer v2
    Consumer v2 có thể đọc dữ liệu do Producer v1 ghi

T3: Deploy Producer v2
    Producer v2 bắt đầu ghi record với schema v2

T4: Quan sát lỗi deserialize, lag, business metrics
```

Trình tự consumer-first thường phù hợp với BACKWARD evolution, nhưng **chỉ an toàn khi phiên bản consumer cũ còn tồn tại có thể xử lý record mới hoặc đã được thay thế đúng thời điểm**. Với group đang rolling update, cả consumer cũ và mới có thể cùng nhận partition; đừng giả định mọi member đã chạy code mới ngay khi một pod mới vừa Ready.

Một kế hoạch rollout cần xác định rõ:

- Subject và compatibility policy đã được áp dụng ở Registry nào.
- Schema mới có thêm/xóa/đổi field gì và giá trị mặc định là gì.
- Consumer cũ có thể đọc record mới trong khoảng giao nhau không.
- Producer mới có bị cache schema cũ hoặc auto-register ngoài dự kiến không.
- Consumer group có lag hay DLT tăng sau mỗi bước không.
- Nếu rollback ứng dụng, schema mới đã ghi vào topic có khiến phiên bản cũ đọc lỗi không.

**Rollback code không hoàn tác các record đã ghi**. Nếu producer v2 đã phát message không tương thích với consumer v1, đưa consumer về v1 có thể khiến nó lỗi tại các offset đã ghi. Vì vậy cần xác định chiến lược rollback dữ liệu/schema, không chỉ rollback image container.

## 12. Đổi schema phải xét retention và replay

Topic Kafka có thể giữ record trong nhiều ngày hoặc nhiều tuần. Khi consumer mới khởi động từ offset cũ, hoặc một group mới dùng `auto.offset.reset=earliest`, nó có thể gặp rất nhiều schema ID lịch sử.

Ví dụ:

```text
orders-0:
  offset 0..999     -> writer schema v1
  offset 1000..1999 -> writer schema v2
  offset 2000..     -> writer schema v3

Consumer mới replay từ offset 0
  phải xử lý các writer schema v1, v2, v3
```

Khi chuẩn bị retention, cleanup và disaster recovery của Registry, cần tính cả thời gian record còn trong Kafka, dữ liệu snapshot, DLT và những bản sao event ở storage khác. **Không xóa schema/subject còn cần cho dữ liệu lịch sử**. Soft delete và hard delete có ý nghĩa khác nhau trong Schema Registry; hard delete có thể gây ảnh hưởng nghiêm trọng đến khả năng decode record cũ nếu metadata bị mất.

Một hệ thống replay tốt cần kiểm thử việc đọc hỗn hợp nhiều writer schema, không chỉ kiểm thử một record vừa mới publish trong môi trường staging.

## 13. Kiểm soát auth, TLS và secret

Với Registry production, kết nối ứng dụng thường phải đi qua HTTPS, certificate validation và một cơ chế xác thực phù hợp. Các thông tin cấu hình có thể bao gồm `schema.registry.url`, `basic.auth.credentials.source`, `basic.auth.user.info`, truststore/keystore hoặc token tùy nhà cung cấp.

Ví dụ về cấu hình dùng environment variable do hệ thống secret cung cấp:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": "${SCHEMA_REGISTRY_URL}"
      "[basic.auth.credentials.source]": USER_INFO
      "[basic.auth.user.info]": "${SCHEMA_REGISTRY_CREDENTIALS}"
```

Đây chỉ là cấu hình minh họa cho cơ chế Basic Auth của Confluent client, không phải khuyến nghị bắt buộc dùng Basic Auth. Cần bổ sung TLS và chính sách cấp phát/rotate credential phù hợp; không đưa giá trị secret thực tế vào YAML được commit lên repository.

Nếu Registry trả `403` trong một số thao tác nhưng không phải tất cả, có thể client có quyền đọc schema nhưng không có quyền đăng ký schema mới. Đây có thể là chính sách chủ đích: producer production chỉ đọc schema đã được pipeline phê duyệt.

## 14. Giám sát Schema Registry và tác động đến Kafka

Khi giám sát một cụm Kafka sử dụng Schema Registry, cần kết hợp tín hiệu từ Registry, producer và consumer:

| Thành phần | Tín hiệu đáng quan sát | Diễn giải |
|---|---|---|
| Registry | Availability, request latency, HTTP `4xx/5xx`, timeout | Registry không phục vụ tra cứu/đăng ký ổn định. |
| Registry | Số lần đăng ký schema, số subject/version thay đổi | Phát hiện rollout schema bất thường, auto registration ngoài ý muốn. |
| Producer | Serialization failure, send failure, publish rate | Producer có thể không mã hóa được record hoặc không tìm được schema. |
| Consumer | Deserialization failure, listener failure | Phân biệt lỗi trước listener và lỗi trong nghiệp vụ. |
| Consumer group | Lag theo partition, rebalance, committed offset | Xác định record không được tiêu thụ hoặc tiến độ bị chậm. |
| DLT | Ingress rate, size, replay backlog | Phát hiện record không thể xử lý đã bị chuyển khỏi topic chính. |

Không chỉ cảnh báo “Registry down”. Một Registry khỏe nhưng subject bị xóa, policy compatibility đổi hoặc credential hết quyền vẫn làm ứng dụng lỗi. Ngược lại, một Registry lỗi ngắn hạn có thể chỉ ảnh hưởng client mới hoặc các ID chưa được cache.

Khi thiết kế alert, ưu tiên mối liên hệ nguyên nhân-kết quả: **Registry latency tăng + deserialization failures tăng + consumer lag tăng** là tín hiệu điều tra có giá trị hơn ba metric riêng lẻ không có bối cảnh.

## 15. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `Unknown schema id` hoặc lookup schema ID thất bại | ID không tồn tại trong Registry được cấu hình, dữ liệu registry không đồng bộ hoặc record ghi sai ID. | Xem `/schemas/ids/{id}`, URL Registry, môi trường/cluster và wire format. |
| Producer báo lỗi đăng ký schema | Schema không tương thích, không có quyền ghi, Registry timeout hoặc `auto.register.schemas=false`. | Kiểm tra subject, compatibility policy, credential và pipeline đăng ký. |
| Consumer lỗi sau deploy schema mới | Consumer cũ không đọc được dữ liệu mới, sai deserializer hoặc thay subject strategy. | Xem schema ID theo record, nhóm member còn chạy phiên bản cũ và deployment order. |
| Pod mới lỗi, pod cũ vẫn chạy | Pod cũ có schema cache; pod mới phải fetch ID qua Registry đang lỗi. | Kiểm tra kết nối Registry từ pod mới, DNS, TLS và auth. |
| `ClassCastException` trong listener | Consumer nhận `GenericRecord` nhưng listener kỳ vọng generated class, hoặc cấu hình reader sai. | Kiểm tra `specific.avro.reader`, class được generate và listener signature. |
| Deserialization failure không đến DLT | Chưa dùng `ErrorHandlingDeserializer` hoặc producer DLT không serialize được bytes lỗi. | Kiểm tra deserializer delegate, error handler, DLT template và serializer. |
| Lag tăng nhưng listener không log exception | Lỗi xảy ra trước listener trong deserializer, poll hoặc metadata lookup. | Kiểm tra container logs, `ErrorHandlingDeserializer` và Kafka client logs. |
| Schema compatibility test pass nhưng nghiệp vụ lỗi | Schema hợp lệ về format nhưng semantics đã thay đổi. | Thêm contract test với payload thật và các phiên bản consumer đang chạy. |
| Replay record cũ bị lỗi | Schema cũ đã bị xóa, reader mới không tương thích hoặc Registry khác ID. | Kiểm tra retention, schema lịch sử, subject và DR strategy. |

## 16. Runbook điều tra lỗi deserialize liên quan Registry

Giả sử sau deployment, consumer group `order-service` tăng lag và log có lỗi liên quan schema.

**Bước 1 — Khoanh vùng.** Xác nhận Kafka broker còn khỏe, các partition vẫn có record, group có member và lỗi xuất hiện từ thời điểm nào. Thu thập topic, partition, offset và client ID của record đầu tiên lỗi.

**Bước 2 — Xác định lỗi xảy ra ở đâu.** Lỗi từ producer serialization, Kafka deserializer, listener nghiệp vụ hay DLT producer? Một stack trace trong `KafkaAvroDeserializer` gợi ý tra cứu/giải mã schema; lỗi trong listener sau khi deserialize thành công thuộc nhóm khác.

**Bước 3 — Tra cứu schema.** Với format Confluent, đọc schema ID từ thông tin diagnostic hoặc công cụ phù hợp rồi gọi Registry API `/schemas/ids/{id}`. Kiểm tra URL Registry thật mà pod sử dụng, không chỉ URL staging trên máy người vận hành.

**Bước 4 — Kiểm tra subject và compatibility.** Xem subject đang dùng, phiên bản mới nhất, naming strategy, policy và thay đổi gần nhất. Đối chiếu log đăng ký schema với thời điểm deployment producer/consumer.

**Bước 5 — Kiểm tra hạ tầng.** Xác minh DNS, TLS, auth, network policy, Registry latency và kết nối từ pod bị ảnh hưởng. Nếu là outage chung, hạn chế restart hàng loạt các consumer còn hoạt động nhờ cache.

**Bước 6 — Bảo vệ dữ liệu.** Nếu dữ liệu thực sự hỏng, dùng `ErrorHandlingDeserializer` cùng recovery/DLT phù hợp. Nếu Registry tạm unavailable, cân nhắc tạm dừng hoặc trì hoãn xử lý để tránh đẩy cả luồng sự kiện hợp lệ vào DLT.

**Bước 7 — Khôi phục và xác nhận.** Sau khi sửa nguyên nhân, kiểm tra decode thành công với record lỗi trước đó, committed offset tiến, lag giảm và không còn lỗi DLT/retry bất thường. Ghi lại schema ID, subject, version, thay đổi đã thực hiện và tác động đến replay.

Không sửa committed offset bằng tay chỉ để bỏ qua một record không deserialize được khi chưa có quy trình giữ lại hoặc xử lý record đó; thao tác này có thể làm mất dữ liệu nghiệp vụ.

## 17. Nguyên tắc vận hành an toàn

- Coi Registry là một dependency của serializer/deserializer, không phải chỉ là kho tài liệu schema.
- Phân biệt schema ID, subject và version; không xem version là ID và không giả định ID giống nhau ở các Registry độc lập.
- Dùng compatibility policy rõ ràng theo từng subject; kiểm tra đúng hướng và đúng lịch sử phiên bản cần hỗ trợ.
- Đưa bước validate/register schema vào CI/CD có kiểm soát; hạn chế auto-register tự do ở production khi cần quản trị contract.
- Triển khai producer và consumer theo thứ tự tương thích; xem cả giai đoạn nhiều phiên bản cùng chạy và tình huống rollback.
- Kiểm tra consumer có thể đọc các writer schema cũ trong thời gian retention/replay.
- Dùng `ErrorHandlingDeserializer` khi cần quản lý lỗi xảy ra trước listener; bảo đảm DLT có thể giữ raw bytes của record hỏng.
- Quan sát Registry availability cùng serialization/deserialization failures, consumer lag và DLT ingress.
- Giữ metadata/schema lịch sử phục vụ dữ liệu còn tồn tại; tránh hard delete subject/schema khi chưa đánh giá replay.
- Bảo vệ Registry bằng TLS/auth, secret rotation và quyền hạn phù hợp; không đặt credential vào source code hoặc log.
- Khi lỗi, phân biệt schema không tồn tại, schema không tương thích, payload hỏng và Registry/network outage trước khi chọn retry hay DLT.

Schema Registry hỗ trợ sự ổn định của hệ thống Spring Kafka bằng cách quản lý hợp đồng dữ liệu xuyên nhiều phiên bản producer và consumer. Để vận hành tin cậy, đội phát triển cần kết hợp compatibility policy, kiểm thử schema, quy trình rollout, cấu hình serializer/deserializer, giám sát dependency và recovery cho record lỗi. Một Registry hoạt động tốt là cần thiết, nhưng **độ tin cậy cuối cùng vẫn phụ thuộc vào cách ứng dụng xử lý thay đổi schema, sự cố mạng và dữ liệu đã được ghi từ các phiên bản trước**.
