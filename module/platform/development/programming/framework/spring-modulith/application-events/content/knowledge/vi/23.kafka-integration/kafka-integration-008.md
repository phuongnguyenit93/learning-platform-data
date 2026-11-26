# Kafka schema

## Mục tiêu

Khi application event của Spring Modulith được chuyển ra Kafka, producer và consumer có thể được triển khai ở những thời điểm khác nhau, dùng các phiên bản ứng dụng khác nhau và thậm chí được viết bằng ngôn ngữ khác nhau. Nếu payload chỉ là một cấu trúc Java được serialize theo class hiện tại, thay đổi field hoặc kiểu dữ liệu có thể làm consumer cũ không đọc được message đã phát.

**Kafka schema** là hợp đồng mô tả cấu trúc và kiểu dữ liệu của message được gửi qua topic. Schema giúp producer và consumer hiểu cùng một payload, kiểm soát thay đổi theo phiên bản và phát hiện sớm những thay đổi không tương thích. Trong hệ thống Spring Modulith, schema của integration event cần được quản lý như hợp đồng giữa các hệ thống; nó độc lập với class nội bộ dùng để xử lý application event.

Sau bài học, bạn có thể:

- Thiết kế hợp đồng Kafka event ổn định với event type, schema version và metadata.
- Chọn JSON, Avro hoặc Protobuf theo yêu cầu của hệ thống.
- Hiểu vai trò của Schema Registry và các chế độ compatibility.
- Thay đổi schema an toàn khi producer và consumer triển khai lệch phiên bản.
- Tích hợp application event của Spring Modulith với Kafka mà vẫn giữ ranh giới module.
- Kiểm thử schema, serialization, deserialization và quá trình nâng cấp producer/consumer.

## 1. Vì sao cần schema cho Kafka?

Kafka lưu message dưới dạng key và value là byte array, có thể kèm headers. Broker không tự hiểu `OrderPlaced` có field nào hoặc `amount` là decimal hay string. Producer chịu trách nhiệm serialize dữ liệu thành bytes; consumer phải deserialize những bytes đó theo một hợp đồng tương thích.

Giả sử producer gửi:

```json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "totalAmount": 125000,
  "currency": "VND"
}
```

Một phiên bản consumer mới có thể cần thêm `salesChannel`. Nếu producer bắt đầu gửi field mới, consumer cũ có thể bỏ qua hoặc gặp lỗi tùy serializer/deserializer và cấu hình. Nếu producer đổi `totalAmount` từ số nguyên sang object hoặc đổi `orderId` thành một cấu trúc lồng nhau, consumer cũ có thể không đọc được message.

Schema làm rõ:

- Tên field và kiểu dữ liệu.
- Field bắt buộc, field tùy chọn và giá trị mặc định.
- Enum, cấu trúc lồng nhau, logical type và quy tắc biểu diễn thời gian/tiền tệ.
- Phiên bản hợp đồng và cách consumer đọc phiên bản cũ.
- Quy tắc tương thích khi producer hoặc consumer được nâng cấp.

Schema không thay thế validation nghiệp vụ. Một message có thể hợp lệ theo schema nhưng vẫn chứa `orderId` không tồn tại, số tiền âm hoặc trạng thái không được phép. Schema xác nhận cấu trúc; module nghiệp vụ xác nhận ý nghĩa và tính hợp lệ của dữ liệu.

## 2. Thiết kế integration event contract

Không nên đưa trực tiếp entity JPA hoặc object nội bộ của domain vào Kafka. Hãy định nghĩa một integration event riêng, chỉ chứa dữ liệu consumer cần và có thể tiến hóa độc lập với implementation.

Ví dụ hợp đồng ở mức khái niệm:

```java
public record OrderPlacedV1(
        UUID eventId,
        String orderId,
        String customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        String correlationId) {}
```

Một số nguyên tắc:

- Dùng `eventId` ổn định để deduplicate khi message được giao lại.
- Dùng `eventType` có tên rõ ràng, không phụ thuộc package/class Java.
- Có `schemaVersion` hoặc version được xác định qua schema subject/version.
- Biểu diễn tiền bằng đơn vị nhỏ nhất (minor unit) hoặc decimal có scale được quy định; tránh floating point cho số tiền.
- Dùng UTC cho thời điểm và thống nhất độ chính xác timestamp.
- Giữ `aggregateId`, `correlationId` và `causationId` khi cần theo dõi quy trình.
- Chỉ đưa dữ liệu cần thiết; tránh phát thông tin cá nhân hoặc bí mật không có lý do nghiệp vụ.

Có thể đặt metadata trong payload envelope hoặc Kafka headers. Hãy chọn một quy ước rõ ràng để consumer biết `eventType`, schema version, content type, correlation ID và message ID nằm ở đâu. Không duy trì cùng một metadata ở nhiều nơi nếu không định nghĩa nguồn nào là chuẩn.

Ví dụ envelope JSON:

```json
{
  "eventId": "3d842a47-c21c-4d5f-bb84-06b4e5cc2b92",
  "eventType": "com.example.orders.order-placed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:15:30Z",
  "aggregateId": "ORD-1001",
  "correlationId": "b4c55f1d-90f2-4c2c-9c8d-82a8bbfbe8bd",
  "payload": {
    "customerId": "CUS-42",
    "totalAmountMinor": 125000,
    "currency": "VND"
  }
}
```

Trong thực tế, envelope có thể được biểu diễn bằng Avro/Protobuf hoặc một định dạng khác thay vì JSON. Điều quan trọng là metadata và payload phải có quy tắc ổn định, được mô tả và kiểm thử.

## 3. Chọn định dạng serialization

Kafka không bắt buộc một định dạng schema duy nhất. Lựa chọn phụ thuộc vào hệ sinh thái, hiệu năng, khả năng tương thích và công cụ của tổ chức.

| Định dạng | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| JSON | Dễ đọc, dễ debug, phổ biến; cần quy ước schema/validation riêng hoặc JSON Schema Registry. | Tích hợp đơn giản, lưu lượng vừa phải, nhiều hệ thống cần đọc trực tiếp. |
| Avro | Schema rõ ràng, hỗ trợ writer/reader schema và thường dùng cùng Schema Registry; payload nhị phân gọn. | Hệ sinh thái Kafka cần quản lý schema và tương thích giữa nhiều phiên bản. |
| Protobuf | Định nghĩa message và field number, hiệu quả, hỗ trợ nhiều ngôn ngữ. | Hệ thống đa ngôn ngữ cần hợp đồng có kiểu và code generation. |

Đừng chọn định dạng chỉ dựa trên kích thước message. Cần cân nhắc khả năng debug, tooling, quy trình review schema, khả năng đọc message lịch sử và mức độ quen thuộc của các đội consumer.

### JSON và JSON Schema

JSON tự thân chỉ mô tả dữ liệu, không bắt buộc consumer kiểm tra cấu trúc. JSON Schema có thể định nghĩa field, kiểu, required, enum và constraint. Khi dùng Schema Registry hỗ trợ JSON Schema, producer/consumer có thể đăng ký và tra cứu schema theo subject/version. Cú pháp và mức hỗ trợ keyword phụ thuộc phiên bản registry.

Ví dụ JSON Schema rút gọn:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["eventId", "orderId", "currency"],
  "properties": {
    "eventId": { "type": "string", "format": "uuid" },
    "orderId": { "type": "string", "minLength": 1 },
    "currency": { "type": "string", "minLength": 3, "maxLength": 3 },
    "totalAmountMinor": { "type": "integer", "minimum": 0 }
  },
  "additionalProperties": false
}
```

`additionalProperties: false` có thể khiến việc thêm field làm consumer validator cũ từ chối payload mới. Vì vậy, constraint này cần được cân nhắc theo chiến lược compatibility. Một consumer cần bỏ qua field chưa biết thường phải cho phép additional properties hoặc dùng schema/validator được nâng cấp đồng bộ.

### Avro

Avro mô tả record, field và default trong schema. Ví dụ:

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "com.example.orders.events",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "totalAmountMinor", "type": "long" },
    { "name": "currency", "type": "string" },
    { "name": "salesChannel", "type": ["null", "string"], "default": null }
  ]
}
```

Trong Avro, union `null` và `string` cùng default `null` cho phép field mới được đọc khi message cũ không có field này trong các tình huống tương thích phù hợp. Default là một phần của quy tắc đọc schema, không phải thao tác tự động ghi giá trị vào message cũ.

### Protobuf

Protobuf dùng field number để định danh field trên wire. Field number đã phát hành phải được xem như bất biến; khi xóa field, nên `reserved` cả number và tên để tránh tái sử dụng nhầm.

```proto
syntax = "proto3";

package com.example.orders.events.v1;

message OrderPlaced {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_amount_minor = 4;
  string currency = 5;
  string sales_channel = 6;
}
```

Không đổi field number để đổi ý nghĩa hoặc kiểu dữ liệu. Một số thay đổi có thể tương thích ở mức wire nhưng vẫn làm thay đổi ý nghĩa nghiệp vụ; vì vậy cần kiểm tra cả tương thích kỹ thuật lẫn semantic compatibility.

## 4. Schema Registry và Kafka

Schema Registry là dịch vụ quản lý schema và phiên bản schema được producer/consumer sử dụng. Nó thường lưu schema theo *subject*, kiểm tra compatibility khi đăng ký schema mới và cung cấp schema cho serializer/deserializer.

Schema Registry không phải thành phần tự có trong mọi Kafka cluster và không đồng nghĩa với Kafka broker. Nó là một dịch vụ/hạ tầng bổ sung; cách triển khai và API phụ thuộc nhà cung cấp. Một số hệ sinh thái hỗ trợ Avro, JSON Schema và Protobuf; cần xác nhận loại serializer, deserializer và tính năng compatibility của registry đang dùng.

### Subject và version

Subject xác định nhóm schema được quản lý cùng nhau. Với một số serializer phổ biến, subject mặc định cho value thường theo dạng `<topic>-value`, key theo `<topic>-key`. Các chiến lược đặt subject khác có thể dựa vào record name hoặc topic kết hợp record name. Quy tắc cụ thể phụ thuộc serializer và cấu hình.

Ví dụ:

- Topic `orders.events` có subject value `orders.events-value`.
- Key của topic có thể có subject riêng `orders.events-key`.
- Nếu nhiều event type cùng nằm trên một topic, chiến lược subject theo record name có thể phù hợp hơn topic-only, nhưng cần thống nhất giữa producer và consumer.

Đừng thay đổi subject naming strategy tùy tiện giữa các service. Thay đổi có thể khiến registry xem schema là một subject khác, làm mất kiểm tra compatibility xuyên các phiên bản trước đó hoặc khiến consumer không tìm được schema theo cách mong đợi.

### Serializer và deserializer

Producer dùng serializer để chuyển object thành bytes và có thể đính kèm schema identifier theo wire format của serializer. Consumer dùng deserializer tương ứng để lấy schema và chuyển bytes thành object. Với Avro, reader schema có thể được dùng để đọc dữ liệu được ghi theo writer schema; registry và deserializer phối hợp tìm schema cần thiết.

Schema Registry giúp kiểm soát hợp đồng nhưng không thay thế việc kiểm tra payload ở tầng nghiệp vụ, kiểm tra quyền publish hoặc bảo đảm message được giao đúng một lần. Registry cũng cần được bảo vệ bằng TLS, authentication và quyền truy cập phù hợp.

## 5. Compatibility khi thay đổi schema

Producer và consumer thường không deploy cùng lúc. Trong thời gian rollout, có thể tồn tại producer mới cùng consumer cũ, hoặc producer cũ cùng consumer mới. Compatibility mode mô tả những hướng nâng cấp được phép.

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| BACKWARD | Consumer dùng schema mới có thể đọc dữ liệu được ghi theo schema cũ. |
| FORWARD | Consumer dùng schema cũ có thể đọc dữ liệu được ghi theo schema mới. |
| FULL | Hỗ trợ cả hai chiều BACKWARD và FORWARD. |
| *_TRANSITIVE | Kiểm tra compatibility với tất cả phiên bản trước trong subject thay vì chỉ phiên bản gần nhất. |
| NONE | Không áp dụng kiểm tra compatibility tự động; đội phát triển tự chịu trách nhiệm kiểm soát thay đổi. |

Định nghĩa chi tiết phụ thuộc định dạng schema và nhà cung cấp registry. Hãy đọc semantics của registry thực tế; một thay đổi được registry chấp nhận không đồng nghĩa mọi consumer đều hiểu đúng ý nghĩa nghiệp vụ mới.

### Ví dụ thay đổi tương thích

Giả sử V1 có `orderId` và `totalAmountMinor`. V2 thêm `salesChannel` là field optional có default phù hợp với định dạng schema. Consumer mới có thể đọc message V1 và nhận default cho field mới nếu schema format/reader xử lý đúng. Đây thường là kiểu thay đổi thuận lợi cho triển khai cuốn chiếu.

Các thay đổi cần đặc biệt thận trọng:

- Xóa field bắt buộc hoặc đổi tên field.
- Đổi kiểu dữ liệu, đơn vị đo hoặc ý nghĩa của field.
- Thêm field bắt buộc không có default cho dữ liệu lịch sử.
- Thay đổi enum theo cách consumer cũ không nhận diện được giá trị mới.
- Đổi Protobuf field number hoặc tái sử dụng number đã xóa.
- Đổi subject naming strategy hoặc serialization format mà không có migration.

Một thay đổi có thể tương thích về cú pháp nhưng không tương thích về nghiệp vụ. Ví dụ `totalAmountMinor` vẫn là `long` nhưng producer bắt đầu gửi đơn vị đồng thay vì đơn vị nhỏ nhất đã quy định; consumer sẽ đọc thành công nhưng tính sai tiền. Contract phải mô tả đơn vị, timezone, precision và ý nghĩa field, không chỉ kiểu dữ liệu.

### Quy trình rollout schema

1. Thiết kế schema mới theo compatibility mode đã thống nhất.
2. Chạy kiểm tra compatibility trong CI trước khi đăng ký/phát hành schema.
3. Nâng cấp consumer để đọc được cả schema cũ và mới.
4. Chờ consumer mới được triển khai đủ và theo dõi lỗi deserialization.
5. Nâng cấp producer để bắt đầu phát schema mới.
6. Theo dõi consumer lag, lỗi, DLQ và tỷ lệ message theo version.
7. Chỉ loại bỏ hỗ trợ schema cũ sau thời gian retention/replay và thời gian hỗ trợ đã công bố.

Nếu cần thay đổi không tương thích, cân nhắc topic/version mới hoặc một giai đoạn dual-read/dual-publish có thời hạn. Không phát song song vô thời hạn vì điều đó làm tăng số hợp đồng cần duy trì và có thể tạo side effect trùng.

## 6. Key, partition và headers

Schema value mô tả nội dung event; key và headers cũng là một phần quan trọng của hợp đồng Kafka.

- **Key** thường xác định partition và ảnh hưởng thứ tự message trong một partition. Dùng `aggregateId` làm key nếu cần giữ thứ tự event của cùng aggregate.
- **Headers** phù hợp với metadata như correlation ID, trace context, content type hoặc loại event, nếu tổ chức đã có quy ước thống nhất.
- **Partition** quyết định khả năng song song và phạm vi thứ tự. Kafka không bảo đảm thứ tự toàn cục giữa các partition.
- **Null value/tombstone** có ý nghĩa đặc biệt trong compacted topic; không nên nhầm tombstone với payload event thông thường.

Nếu thay đổi key schema hoặc cách tính partition, message của cùng aggregate có thể đi tới partition khác nhau và làm thay đổi thứ tự quan sát được. Hãy xem thay đổi key như thay đổi hợp đồng, nhất là khi consumer dựa vào thứ tự để cập nhật trạng thái.

## 7. Tích hợp Kafka với Spring Modulith

Spring Modulith giúp module giao tiếp bằng application event và giữ ranh giới module. Khi cần đưa event ra Kafka, có thể đánh dấu event cần externalize và cấu hình integration tương ứng. Ví dụ khái niệm:

```java
@Externalized("orders")
public record OrderPlaced(
        UUID eventId,
        String orderId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt) {}
```

Đích `orders` được ánh xạ qua cấu hình externalization và integration module Kafka tương ứng với phiên bản Spring Modulith đang dùng. Event được chuyển đổi/serialize theo cấu hình serializer và schema contract đã chọn. Tên annotation, khả năng tích hợp và cấu hình cụ thể cần khớp phiên bản dependency của dự án; không nên sao chép cấu hình từ một phiên bản khác mà chưa kiểm tra.

Luồng trách nhiệm nên được tách rõ:

1. Module nghiệp vụ phát application event mô tả điều đã xảy ra.
2. Spring Modulith quản lý publication và theo dõi trạng thái publication theo Event Publication Registry khi được cấu hình.
3. Integration adapter chuyển event thành Kafka record, chọn topic/key/headers và serializer.
4. Serializer sử dụng schema/Schema Registry theo hợp đồng tích hợp.
5. Consumer bên ngoài deserialize theo schema tương thích và xử lý event theo idempotency policy.

**Event Publication Registry và Schema Registry giải quyết hai bài toán khác nhau:**

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Modulith Event Publication Registry | Theo dõi publication tới listener/externalization được Spring Modulith quản lý và trạng thái hoàn tất của publication. |
| Kafka Schema Registry | Quản lý schema, subject, version và compatibility của message key/value. |

Event Publication Registry không kiểm tra schema Avro/JSON/Protobuf. Schema Registry không biết listener nội bộ nào đã xử lý application event hoặc publication nào chưa hoàn tất. Hai cơ chế có thể bổ trợ nhau nhưng không thay thế nhau.

Nếu event được publish ra Kafka, cần xác định rõ thời điểm publication được coi là hoàn tất theo integration đang dùng, ý nghĩa broker acknowledgement và cách xử lý khi publish thành công nhưng cập nhật trạng thái registry thất bại. Đây là một crash window có thể tạo duplicate; consumer nên idempotent theo event ID.

### Không để schema bên ngoài rò vào domain model

Một module có thể phát `OrderPlaced` nội bộ với kiểu dữ liệu phong phú, sau đó mapper chuyển sang `OrderPlacedIntegrationV1` có schema ổn định. Cách này cho phép domain model thay đổi mà không buộc mọi consumer bên ngoài cập nhật cùng lúc.

```java
public record OrderPlacedIntegrationV1(
        String eventId,
        String orderId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt) {}

@Component
class OrderIntegrationEventMapper {

    OrderPlacedIntegrationV1 toV1(OrderPlaced event) {
        return new OrderPlacedIntegrationV1(
                event.eventId().toString(),
                event.orderId().toString(),
                event.totalAmountMinor(),
                event.currency().getCurrencyCode(),
                event.occurredAt());
    }
}
```

Mapper là ranh giới chuyển đổi giữa hợp đồng nội bộ và hợp đồng tích hợp. Hãy kiểm thử mapper để tránh lỗi đơn vị tiền, timezone, null/default hoặc làm mất correlation metadata.

## 8. Schema governance trong CI/CD

Schema cần được review như code. Một quy trình CI có thể gồm:

1. Lưu schema trong version control cùng tài liệu event contract.
2. Kiểm tra syntax và lint schema.
3. So sánh schema mới với version đã phát hành theo compatibility mode.
4. Sinh code hoặc kiểm tra serializer/deserializer nếu định dạng hỗ trợ code generation.
5. Chạy contract test với payload mẫu của các version đang hỗ trợ.
6. Kiểm tra consumer có thể đọc message cũ và producer tạo message mới đúng schema.
7. Chỉ đăng ký schema mới vào registry sau khi kiểm tra và review đạt.

Không nên để mọi developer tự ý đổi compatibility mode hoặc xóa subject/version. Quyền đăng ký schema production, thay đổi compatibility và xóa schema cần được kiểm soát. Lưu schema ID/version cùng build metadata để truy vết phiên bản producer đã phát message.

## 9. Bảo mật và quản trị dữ liệu

Schema Registry và Kafka đều nằm trong ranh giới tích hợp cần được bảo vệ. Cấu hình TLS, authentication, ACL cho topic và quyền truy cập registry theo nguyên tắc tối thiểu. Producer chỉ nên đăng ký/ghi schema theo quyền được cấp; consumer chỉ cần đọc schema và topic tương ứng.

Không đưa token, password hoặc dữ liệu cá nhân không cần thiết vào event. Message trong Kafka có thể tồn tại theo retention, được replay hoặc sao chép sang hệ thống khác. Trước khi thêm field nhạy cảm, cần xác định mục đích, quyền truy cập, thời hạn lưu trữ và cách xử lý yêu cầu xóa dữ liệu. Nếu cần ẩn danh hóa hoặc mã hóa field, hãy định nghĩa rõ trách nhiệm mã hóa/giải mã và cách quản lý key.

Schema Registry không tự bảo đảm payload đúng nguồn gửi hoặc hợp lệ về nghiệp vụ. Consumer vẫn cần xác thực nguồn theo kiến trúc bảo mật, kiểm tra dữ liệu và giới hạn kích thước/độ phức tạp message.

## 10. Kiểm thử schema và Kafka integration

Nên kiểm thử theo nhiều lớp:

| Loại kiểm thử | Điều cần xác minh |
| --- | --- |
| Schema validation | Schema hợp lệ, field/type/default/enum đúng hợp đồng. |
| Compatibility test | Schema mới đạt compatibility mode với các version trước. |
| Serialization test | Producer serialize object thành message theo schema đã chọn. |
| Deserialization test | Consumer đọc được payload của các schema version còn hỗ trợ. |
| Contract test | Payload mẫu giữa producer và consumer có cùng ý nghĩa field, đơn vị và timestamp. |
| Integration test | Topic, key, headers, serializer, deserializer và registry hoạt động cùng nhau. |
| Failure test | Schema Registry unavailable, schema ID không tồn tại, payload malformed, message version không hỗ trợ. |
| Rollout test | Consumer mới đọc message cũ; consumer cũ xử lý được message mới theo compatibility contract. |

Ví dụ kiểm thử mapper:

```java
@Test
void mapsInternalEventToStableIntegrationContract() {
    OrderPlaced event = new OrderPlaced(
            eventId,
            orderId,
            125000L,
            Currency.getInstance("VND"),
            occurredAt);

    OrderPlacedIntegrationV1 result = mapper.toV1(event);

    assertThat(result.eventId()).isEqualTo(eventId.toString());
    assertThat(result.orderId()).isEqualTo(orderId.toString());
    assertThat(result.totalAmountMinor()).isEqualTo(125000L);
    assertThat(result.currency()).isEqualTo("VND");
    assertThat(result.occurredAt()).isEqualTo(occurredAt);
}
```

Ngoài unit test, nên lưu payload mẫu của các version đã phát hành và chạy consumer compatibility test trên chúng. Khi dùng Schema Registry thật hoặc container, kiểm tra cả cấu hình authentication, subject naming strategy, compatibility mode và behavior khi registry tạm thời không truy cập được. Không chỉ kiểm tra producer đăng ký schema thành công; cần chứng minh consumer thực tế đọc được dữ liệu.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Serialize trực tiếp entity/domain object | Thay đổi nội bộ làm hỏng hợp đồng consumer. | Tạo integration event schema riêng và mapper. |
| Không có schema version/compatibility policy | Producer và consumer deploy lệch phiên bản gây lỗi. | Dùng version và kiểm tra compatibility trong CI. |
| Đổi field type hoặc ý nghĩa nhưng giữ tên | Consumer deserialize được nhưng hiểu sai dữ liệu. | Xem semantic compatibility là một phần của contract review. |
| Tái sử dụng Protobuf field number | Dữ liệu cũ có thể bị diễn giải sai. | Reserve field number/name đã xóa. |
| Đổi subject naming strategy tùy tiện | Compatibility history bị chia tách hoặc consumer tra schema sai. | Chuẩn hóa subject strategy theo topic/event contract. |
| Nhầm Event Publication Registry với Schema Registry | Bỏ sót một trong hai loại trạng thái cần theo dõi. | Tách trách nhiệm publication và schema governance. |
| Chỉ test producer | Consumer thực tế có thể không đọc được payload. | Test cả deserialize và payload lịch sử. |
| Đưa dữ liệu nhạy cảm vào event không kiểm soát | Tăng phạm vi rò rỉ qua retention/replay. | Tối thiểu hóa payload và kiểm soát quyền truy cập. |

## 12. Quy trình áp dụng

Khi thiết kế Kafka schema cho application events trong Spring Modulith:

1. Xác định event nghiệp vụ cần externalize và consumer bên ngoài.
2. Tạo integration contract riêng, có event ID, event type, schema version và metadata tương quan.
3. Chọn JSON/JSON Schema, Avro hoặc Protobuf theo tooling và nhu cầu compatibility.
4. Chọn subject naming strategy và compatibility mode; ghi rõ quy tắc trong tài liệu contract.
5. Tạo mapper từ application event sang integration event để bảo vệ domain model.
6. Cấu hình serializer/deserializer và Schema Registry theo phiên bản integration thực tế.
7. Kiểm thử compatibility, payload lịch sử, key/headers, transaction publication và consumer idempotency.
8. Triển khai consumer trước khi producer phát schema mới nếu cần rollout tương thích.
9. Theo dõi schema version, lỗi serialization/deserialization, consumer lag, DLQ và publication status.
10. Quản lý retention, bảo mật, quyền đăng ký schema và quy trình loại bỏ version cũ.

Kafka schema là hợp đồng dài hạn giữa producer và consumer. Khi quản lý schema có version, kiểm tra compatibility và tách integration event khỏi domain model, các module Spring Modulith có thể externalize application events mà vẫn cho phép từng hệ thống tiến hóa độc lập và xử lý message cũ một cách an toàn.
