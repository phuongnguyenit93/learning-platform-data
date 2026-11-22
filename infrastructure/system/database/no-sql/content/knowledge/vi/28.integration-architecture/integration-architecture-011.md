# Quản lý hợp đồng dữ liệu giữa bên phát, bên nhận và hệ lưu trữ

## 1. Bài toán mở đầu: thay một trường nhỏ, ba hệ thống cùng lỗi

Một ứng dụng thương mại điện tử có ba thành phần:

- **Order Service** nhận và xác nhận đơn hàng, là bên phát sự kiện.
- **Notification Service** và **Analytics Service** nhận sự kiện để gửi thông báo và tạo báo cáo.
- **NoSQL storage** lưu đơn hàng, idempotency ledger và các read model của từng dịch vụ.

Ban đầu, Order Service phát:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "orderId": "ord-9001",
  "customerId": "cus-42",
  "amount": 450000,
  "currency": "VND"
}
~~~

Một lập trình viên muốn “đặt tên rõ hơn” nên đổi `amount` thành `totalAmount`, đồng thời đổi số tiền từ **VND đơn vị nhỏ nhất** sang **số thực thể hiện tiền theo đơn vị chính**. Producer mới phát:

~~~json
{
  "eventId": "evt-1002",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "orderId": "ord-9002",
  "customerId": "cus-42",
  "totalAmount": 450000.0,
  "currency": "VND"
}
~~~

Nếu consumer cũ vẫn đọc `amount`, các kết quả có thể rất khác nhau:

1. Consumer từ chối thông điệp vì thiếu field bắt buộc.
2. Consumer âm thầm mặc định `amount = 0`, khiến doanh thu sai.
3. Consumer lưu document thiếu số tiền nhưng báo ACK với broker.
4. Consumer retry vô hạn một message không thể đọc.
5. Consumer nhận được field mới nhưng hiểu sai đơn vị tiền.
6. Read model NoSQL nhận dữ liệu mới song index, query API hoặc bộ tổng hợp cũ chưa được cập nhật.

Đây **không chỉ là lỗi schema**. Đây là lỗi **hợp đồng dữ liệu (data contract)**: bên phát, bên nhận và hệ lưu trữ không cùng hiểu cấu trúc, ý nghĩa, thời gian hiệu lực và cam kết xử lý.

Một hệ NoSQL thường linh hoạt về schema lưu trữ. Nhưng **schema linh hoạt không đồng nghĩa các hệ tích hợp tự tương thích**.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Xác định các bên tham gia và phạm vi của một data contract.
2. Phân biệt **transport schema**, **domain semantics**, **delivery contract** và **storage/query contract**.
3. Thiết kế envelope sự kiện có ID, version, thời gian và định danh aggregate.
4. Phân tích backward/forward/full compatibility qua ví dụ cụ thể.
5. Quản lý null, missing fields, enum, rename, đổi kiểu, đơn vị đo và precision.
6. Chuyển đổi event sang document NoSQL mà không rò rỉ cấu trúc nội bộ của producer.
7. Xác định partition/shard key, index, TTL, consistency và idempotency trong hợp đồng.
8. Dùng schema registry/catalog và consumer-driven contract testing đúng phạm vi.
9. Thiết kế quy trình rollout nhiều phiên bản, migration, backfill và rollback.
10. Xây test Java và ma trận tình huống tích hợp có thể tái hiện.

---

## 2. Data contract là gì?

**Data contract** là thỏa thuận có thể kiểm tra được giữa các hệ thống về dữ liệu chúng trao đổi hoặc lưu trữ: **trường nào tồn tại, kiểu gì, mang ý nghĩa gì, thay đổi ra sao, ai chịu trách nhiệm và điều gì được bảo đảm trong lúc truyền/đọc/ghi**.

Nó có thể bao gồm JSON Schema, Avro, Protobuf, OpenAPI, AsyncAPI, CQL/DDL, versioning policy, README và những quy tắc nghiệp vụ không biểu đạt được bằng kiểu dữ liệu.

Ví dụ một bản hợp đồng hoàn chỉnh cho `OrderConfirmed` cần trả lời:

- **Bên phát:** dịch vụ nào có thẩm quyền xác nhận đơn?
- **Bên nhận:** ai đang phụ thuộc vào event?
- **Khi nào phát:** trước hay sau khi transaction của đơn hàng commit?
- **Định danh:** `eventId`, `orderId`, `tenantId` có phạm vi duy nhất nào?
- **Schema:** field required/optional, type, format, default?
- **Ý nghĩa:** `totalMinor` bao gồm thuế/phí/giảm giá hay chưa?
- **Delivery:** có thể đến trùng, trễ hay đảo thứ tự không?
- **Consistency:** notification/report cần mới đến mức nào?
- **Storage:** dữ liệu được lưu ở collection/table nào, với khóa và index nào?
- **Evolution:** consumer cũ có đọc được event mới không?
- **Retention:** event, source record và read model sống bao lâu?
- **Security:** field nào là PII, ai được đọc, lưu ở region nào?
- **Operations:** nếu message không tương thích, hệ báo lỗi và xử lý ra sao?

### 2.1. Contract không phải chỉ là “mẫu JSON”

JSON cho biết cấu trúc. Nó **không tự giải thích**:

- `amount=100` là 100 đồng hay 100 xu?
- `status=PAID` là payment authorized hay captured?
- `occurredAt` do client hay server cấp?
- `customerId` có được đổi khi merge account?
- Một event có được phát lại sau broker failover không?
- Một field bị xóa khỏi event có nghĩa null, unknown hay “không còn tồn tại”?

Do đó cần cả **cú pháp, ngữ nghĩa và bảo đảm xử lý**.

### 2.2. Producer schema khác consumer expectation

Một producer có thể định nghĩa field `phone` là optional. Nhưng nếu một consumer có code:

~~~java
String phone = event.phone();
smsGateway.send(phone, message);
~~~

thì về mặt thực tế consumer đang coi `phone` là bắt buộc. Hai bên có thể tương thích theo schema nhưng **không tương thích theo hành vi**.

### 2.3. Sơ đồ phụ thuộc

~~~mermaid
flowchart LR
    P["Order Service - producer"] --> O["Transactional outbox"]
    O --> B["Broker / CDC"]
    B --> C1["Notification consumer"]
    B --> C2["Analytics consumer"]
    B --> C3["Search indexer"]
    P --> S["Orders source NoSQL"]
    C1 --> N["Notification state"]
    C2 --> A["Analytics NoSQL projection"]
    C3 --> I["Search index"]
    K["Data contract + registry/catalog"] -.-> P
    K -.-> C1
    K -.-> C2
    K -.-> C3
    K -.-> S
~~~

Sơ đồ chỉ minh họa kiến trúc; không phải mọi dự án đều cần broker, outbox và ba read model. Dù dùng HTTP đồng bộ hoặc import file theo batch, các nguyên tắc hợp đồng vẫn có ý nghĩa.

---

## 3. Bốn lớp hợp đồng cần tách biệt

| Lớp | Quy định | Ví dụ thay đổi có thể gây lỗi |
|---|---|---|
| **Cấu trúc / serialization** | Field, type, format, required, codec | `amount` đổi tên thành `totalAmount` |
| **Ngữ nghĩa / domain** | Đơn vị, công thức, trạng thái, ý nghĩa | `totalMinor` chuyển từ trước thuế sang sau thuế |
| **Delivery / processing** | Ordering, retry, duplicate, idempotency, timeout | Broker có thể redeliver một event |
| **Storage / query** | Partition key, schema, index, TTL, consistency | Đổi `PK=TENANT#...` làm consumer không tìm được data |

Một thay đổi có thể **giữ nguyên JSON Schema** nhưng phá ngữ nghĩa. Ví dụ `amount` vẫn là integer nhưng từ VND đổi sang USD cents. Schema validator không phát hiện.

Ngược lại, một thay đổi storage nội bộ như đổi tên MongoDB collection có thể **không ảnh hưởng consumer** nếu producer vẫn giữ API/event contract và dịch vụ tự quản projection của mình.

### 3.1. Không để storage schema trở thành public contract vô tình

Sai:

~~~text
Producer lấy nguyên MongoDB document
  -> gửi toàn bộ qua Kafka
  -> consumer truy cập nested fields và _id
~~~

Khi producer đổi cách embed dữ liệu, consumer vỡ dù ý nghĩa nghiệp vụ không thay đổi.

Tốt hơn:

~~~text
Source document nội bộ
  -> domain event mapper
  -> public event schema được version
  -> consumer mapper
  -> consumer-owned storage projection
~~~

Điều này giúp các dịch vụ độc lập thay đổi mô hình NoSQL riêng.

### 3.2. Data contract là một “giao diện” giữa nhóm

Tương tự một Java interface được sử dụng bởi code khác, một event schema/semantic contract là giao diện của dữ liệu. Đổi public interface cần tính người dùng phụ thuộc, không chỉ đảm bảo unit test của producer xanh.

---

## 4. Vai trò và quyền sở hữu

Một data contract tốt có các trách nhiệm rõ ràng:

| Vai trò | Trách nhiệm điển hình |
|---|---|
| **Producer owner** | Định nghĩa ý nghĩa event, bảo đảm chỉ phát từ state đã hợp lệ |
| **Consumer owner** | Nêu field và SLA thực sự phụ thuộc, kiểm tra phiên bản mới |
| **Schema/contract steward** | Quản trị registry, policy compatibility và tài liệu |
| **Storage owner** | Định nghĩa key/index/TTL/retention/query semantics của bảng mình |
| **Platform team** | Broker/CDC, auth, monitoring, replay, schema tooling |
| **Security/privacy** | PII, retention, residency, access control |
| **On-call operator** | Theo dõi DLQ, lag, replay và incident runbook |

Một service có thể kiêm nhiều vai trò. Quan trọng là **không có hợp đồng “vô chủ”**.

### 4.1. Producer không được quyết định thay mọi consumer

Ví dụ producer muốn xóa `customerId` vì đã chuyển nội bộ sang UUID khác. Nếu Notification còn phụ thuộc field này, producer cần:

- Biết consumer đang dùng gì.
- Đề xuất mapping/field mới.
- Thông báo thời hạn migration.
- Kiểm thử tương thích.
- Chỉ gỡ field cũ khi các consumer đã chuyển.

### 4.2. Consumer cũng có trách nhiệm

Consumer không nên dựa vào field chưa công bố, thứ tự JSON keys, MongoDB internal IDs hay dữ liệu PII “tiện có” trong event. Nó nên khai báo **những trường thực sự cần**.

---

## 5. Hợp đồng mẫu cho event `OrderConfirmed`

Một event envelope có thể gồm:

~~~json
{
  "eventId": "evt-5b2f",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "producer": "order-service",
  "tenantId": "tenant-7",
  "aggregateId": "ord-9001",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-14T09:30:00Z",
  "publishedAt": "2026-11-14T09:30:02Z",
  "correlationId": "checkout-1001",
  "payload": {
    "orderId": "ord-9001",
    "currency": "VND",
    "totalMinor": 450000,
    "customerRef": "cus-42",
    "lines": [
      {
        "productId": "prd-10",
        "quantity": 2,
        "unitPriceMinor": 225000
      }
    ]
  }
}
~~~

Đây là **schema minh họa**, không phải chuẩn bắt buộc của mọi kiến trúc event-driven.

### 5.1. Ý nghĩa của từng trường

| Field | Vai trò | Lưu ý |
|---|---|---|
| `eventId` | Định danh **một event logic** để dedup | Retry gửi lại event cũ phải giữ cùng ID |
| `eventType` | Phân loại loại sự kiện | Không tùy tiện tái sử dụng tên với nghĩa khác |
| `schemaVersion` | Phiên bản hợp đồng serialization | Khác aggregate version |
| `producer` | Nguồn phát có trách nhiệm | Không đồng nghĩa identity đã xác thực nếu trường tùy ý |
| `tenantId` | Phạm vi tenant | Phải authorization/filter, không chỉ routing |
| `aggregateId` | Entity nguồn event thuộc về | Cần nêu uniqueness scope |
| `aggregateVersion` | Thứ tự thay đổi trên **một aggregate** nếu source đảm bảo | Không là global sequence |
| `occurredAt` | Thời điểm business event xảy ra theo source | Khác ingestion/publish time |
| `publishedAt` | Thời điểm phát theo hệ | Có thể trễ so với business event |
| `correlationId` | Liên kết workflow/trace | Không phải idempotency key thay thế |
| `payload.totalMinor` | Số tiền nguyên theo đơn vị nhỏ nhất đã định nghĩa | Cần currency rules và phạm vi tính |
| `payload.customerRef` | Reference, không tự là thông tin liên lạc | Quyền truy cập/PII vẫn cần |
| `payload.lines` | Snapshot của order lines theo contract | Có thể khác bảng sản phẩm hiện tại |

### 5.2. Tên không quyết định semantics

`aggregateVersion=18` chỉ có ích cho ordering/dedup nếu source thực sự tăng nó một cách nhất quán khi commit thay đổi. Nếu mỗi producer replica tự tăng counter không phối hợp, giá trị có thể trùng hoặc đi lùi.

### 5.3. Tách thời gian

- `occurredAt`: business event time.
- `recordedAt`: khi source authoritative ghi nhận (nếu có).
- `publishedAt`: khi outbox/broker publish.
- `consumedAt`: khi consumer nhận.
- `projectedAt`: khi read model được cập nhật.

Đo lag cần chọn **cặp mốc thời gian tương ứng**, không chỉ lấy `now - occurredAt` rồi gán lỗi hết cho broker.

---

## 6. Định nghĩa cấu trúc bằng JSON Schema

Ví dụ rút gọn dùng **JSON Schema Draft 2020-12** cho envelope phía trên:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderConfirmedV2",
  "type": "object",
  "required": [
    "eventId",
    "eventType",
    "schemaVersion",
    "tenantId",
    "aggregateId",
    "aggregateVersion",
    "occurredAt",
    "payload"
  ],
  "properties": {
    "eventId": {
      "type": "string",
      "minLength": 1
    },
    "eventType": {
      "const": "OrderConfirmed"
    },
    "schemaVersion": {
      "const": 2
    },
    "tenantId": {
      "type": "string",
      "minLength": 1
    },
    "aggregateId": {
      "type": "string",
      "minLength": 1
    },
    "aggregateVersion": {
      "type": "integer",
      "minimum": 1
    },
    "occurredAt": {
      "type": "string",
      "format": "date-time"
    },
    "payload": {
      "type": "object",
      "required": [
        "orderId",
        "currency",
        "totalMinor"
      ],
      "properties": {
        "orderId": {
          "type": "string",
          "minLength": 1
        },
        "currency": {
          "type": "string",
          "pattern": "^[A-Z]{3}$"
        },
        "totalMinor": {
          "type": "integer",
          "minimum": 0
        },
        "customerRef": {
          "type": "string"
        },
        "lines": {
          "type": "array",
          "items": {
            "type": "object",
            "required": [
              "productId",
              "quantity",
              "unitPriceMinor"
            ],
            "properties": {
              "productId": {
                "type": "string"
              },
              "quantity": {
                "type": "integer",
                "minimum": 1
              },
              "unitPriceMinor": {
                "type": "integer",
                "minimum": 0
              }
            },
            "additionalProperties": true
          }
        }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
~~~

### 6.1. Vì sao `additionalProperties: true`?

Nó cho phép producer bổ sung optional fields mà validator schema này không từ chối chỉ vì gặp field lạ. **Nhưng không đảm bảo consumer parser cũ bỏ qua field lạ**; cần kiểm tra deserializer thật.

Một hợp đồng strict có thể dùng `additionalProperties: false` để bắt lỗi chính tả, nhưng điều đó tạo yêu cầu thay đổi schema/consumer đồng bộ hơn. Chọn theo chính sách compatibility.

### 6.2. Schema chưa kiểm tra hết semantics

Schema trên chưa chứng minh:

- `totalMinor` bằng tổng line items sau giảm giá, thuế và phí.
- `customerRef` có tồn tại và tenant sở hữu.
- `aggregateVersion` tăng đúng một sau commit.
- `eventId` chưa từng được xử lý.
- `currency` được hỗ trợ cho giao dịch cụ thể.
- Event chỉ phát khi Order thực sự `CONFIRMED`.

Cần **domain validation, referential checks, database constraints và contract tests** bên cạnh structural validation.

### 6.3. `format` cần hiểu validator

Trong JSON Schema, việc `format` có được dùng như assertion thực thi hay chỉ annotation phụ thuộc dialect/vocabulary và cấu hình validator. Không cho rằng khai báo `"format":"date-time"` tự khiến mọi runtime reject timestamp sai.

---

## 7. Backward, forward và full compatibility

Các thuật ngữ cần nêu theo góc đọc **schema mới/cũ**, vì dùng mơ hồ dễ gây hiểu nhầm.

| Loại | Kiểm tra cái gì? | Tình huống điển hình |
|---|---|---|
| **Backward compatibility** | **Reader/consumer mới** đọc được dữ liệu được viết theo schema cũ | Consumer được nâng cấp trước, replay dữ liệu lịch sử |
| **Forward compatibility** | **Reader/consumer cũ** đọc được dữ liệu được viết theo schema mới | Producer được nâng cấp trước consumer |
| **Full compatibility** | Cả hai hướng đọc đều phù hợp | Các phiên bản chạy song song lâu |
| **Transitive compatibility** | Kiểm với **nhiều phiên bản lịch sử**, không chỉ bản gần nhất | Replay event nhiều năm, consumers lùi phiên bản |

Đây là định nghĩa thường dùng trong quản trị schema/serialization. **Schema-compatibility checker và semantic compatibility không giống nhau.**

### 7.1. Producer mới, consumer cũ

Producer thêm một optional field:

~~~json
{
  "orderId": "ord-9001",
  "totalMinor": 450000,
  "promotionCode": "FALL10"
}
~~~

Consumer cũ có thể hoạt động nếu:

- Nó bỏ qua unknown field.
- Không phụ thuộc vào việc “object chỉ có đúng N keys”.
- Field mới không đổi semantics của trường cũ.
- Có thể decode codec/schema framing mới theo contract.

Đây là một mục tiêu **forward compatibility**, nhưng không được coi nó là chắc chắn chỉ vì field mới optional.

### 7.2. Consumer mới đọc dữ liệu cũ

Nếu consumer mới bắt buộc `promotionCode` và không có default/logic xử lý missing, nó có thể không đọc được event cũ. Để backward-compatible, consumer phải xử lý trường vắng mặt theo quy tắc công bố.

### 7.3. Thêm field có điều kiện

Một field có thể optional về schema nhưng bắt buộc theo business state:

~~~text
If paymentState=CAPTURED:
    providerPaymentId must be present.
~~~

Khi triển khai, cần test **conditional semantic requirement** này, không chỉ `required` ở top-level.

### 7.4. Full compatibility không phải “mọi thứ đều an toàn”

Nếu producer vẫn gửi `totalMinor` integer nhưng thay ý nghĩa từ giá trước thuế sang giá sau thuế, schema có thể full-compatible trong khi Analytics tính sai. **Ý nghĩa là phần của hợp đồng.**

---

## 8. Ma trận thay đổi schema

| Thay đổi | Rủi ro cho consumer cũ | Rủi ro đọc dữ liệu cũ | Chính sách khuyến nghị |
|---|---|---|---|
| Thêm field optional | Parser strict có thể lỗi | Thường thấp nếu consumer mới xử lý missing | Bật tolerant reader có kiểm soát, test |
| Thêm field required | Consumer cũ có thể bỏ qua nếu tolerant | Consumer mới không đọc được event thiếu field | Default/migration hoặc version mới |
| Xóa field optional | Consumer cũ có thể đang dùng | Consumer mới không thấy field cũ tùy policy | Deprecate, thống kê dependency |
| Xóa field required | Consumer cũ hỏng | Reader mới có thể đọc nếu không yêu cầu | Breaking, migration có kiểm soát |
| Đổi tên field | Field cũ biến mất | Dữ liệu cũ thiếu tên mới | Add-new → dual-populate → remove-old |
| Đổi `int` thành `string` | Decode/logic có thể lỗi | New reader cần hỗ trợ cũ | Version mới/dual field |
| Đổi đơn vị tiền | Dữ liệu sai âm thầm | Dữ liệu lịch sử cần diễn giải khác | Field mới kèm unit/version |
| Thêm enum value | Exhaustive `switch` có thể lỗi | Thường cần default branch | Test unknown enum |
| Đổi timezone/format | Parse hoặc sort sai | Historical parse khác | Format thống nhất, version |
| Đổi optional sang non-null | Một số consumer không ảnh hưởng | Old records chứa null/missing | Backfill và test |
| Đổi nested object sang array | Mapping vỡ | Không tự chuyển đổi | Version mới/adapter |
| Thêm metadata envelope | Có thể an toàn nếu không strict | Reader mới xử lý missing | Theo chuẩn tiến hóa |
| Thay eventType/name | Subscription/filter không còn match | Old messages vẫn có type cũ | Parallel publish hoặc routing migration |
| Đổi key/partition | Consumer không route được | Historical key lookup sai | Read model migration/lookup map |
| Đổi TTL | Có thể xóa dữ liệu sớm hơn | Replay/reconciliation không còn data | Review contract retention |
| Đổi ordering guarantee | Các trạng thái đến đảo thứ tự | Read model có thể ghi lùi | Sequence/version/idempotency |

**Không có bảng nào thay thế kiểm thử cụ thể của serializer, schema registry và consumer.** Những hệ dùng Avro, Protobuf, JSON, CBOR hay raw BSON có các quy tắc tương thích khác nhau.

---

## 9. Null, absent, empty và default là bốn trạng thái khác nhau

Ví dụ cập nhật hồ sơ:

~~~json
{
  "customerId": "cus-42",
  "phone": null
}
~~~

Và:

~~~json
{
  "customerId": "cus-42"
}
~~~

Hai payload này có thể mang ý nghĩa khác:

- `phone` **không xuất hiện**: không cập nhật số điện thoại.
- `phone: null`: xóa số điện thoại.
- `phone: ""`: người dùng gửi chuỗi rỗng (có thể invalid).
- `phone: "090..."`: đặt giá trị mới.

### 9.1. PATCH khác sự kiện snapshot

Một **PATCH command** có thể mang semantics “chỉ field xuất hiện mới được thay”. Một **snapshot event** có thể hứa “toàn bộ trạng thái có mặt”, field thiếu là bất thường.

Không để consumer tự đoán contract từ JSON.

### 9.2. Default có thể làm sai dữ liệu

Nếu message cũ không có `discountMinor`, mặc định 0 có thể đúng khi trước đây luôn không hỗ trợ discount. Nhưng nếu field vắng mặt vì producer lỗi, mặc định 0 khiến hệ sai âm thầm.

Default phải được giải thích theo **version và business semantics**, không chỉ tiện cho deserialization.

### 9.3. Database NoSQL có biểu diễn null khác nhau

MongoDB document có thể thiếu field hoặc có `null`. DynamoDB attribute có thể không có hoặc mang kiểu `NULL`; Cassandra `null` trong một số mutation context liên quan xóa dữ liệu/tombstone, không giống SQL `NULL` theo mọi khía cạnh.

Mapping phải nêu rõ, nhất là khi consumer thực hiện **partial update**.

---

## 10. Enum, trạng thái nghiệp vụ và unknown values

Giả sử Order state có:

~~~text
CREATED
PAID
CANCELLED
~~~

Phiên bản mới thêm `REFUNDED`.

Consumer cũ dùng:

~~~java
switch (orderState) {
    case CREATED -> handleCreated();
    case PAID -> handlePaid();
    case CANCELLED -> handleCancelled();
}
~~~

Nếu enum parser hoặc switch không có nhánh unknown, một giá trị mới có thể gây lỗi hoặc làm consumer bỏ qua hành động cần thiết.

### 10.1. Thiết kế resilient reader

Có thể:

- Phân biệt unknown enum và malformed payload.
- Lưu unknown raw value để điều tra nếu an toàn.
- Không tự diễn giải `REFUNDED` là `CANCELLED`.
- Cảnh báo khi producer phát trạng thái mới.
- Tạm đưa message vào xử lý có giám sát.
- Chỉ bỏ qua nếu contract cho phép.

### 10.2. State machine khác enum schema

Schema cho phép `"PAID"` không có nghĩa transition `REFUNDED -> PAID` hợp lệ. Khi business status thay đổi, cần kiểm tra **transition constraints** và thứ tự event.

---

## 11. Tiền tệ, decimal, timezone và đơn vị đo

Những field dễ tạo “schema-compatible data corruption”:

- Số tiền.
- Khối lượng và đơn vị kg/g.
- Nhiệt độ °C/°F.
- Khoảng thời gian ms/s.
- Timestamp/zone.
- Tỷ lệ phần trăm 0–1 hay 0–100.
- Số lượng tồn kho gồm reserved hay available.
- Giá trước/sau thuế.

### 11.1. Tiền theo đơn vị nhỏ nhất

Thay vì một `double amount`, có thể dùng:

~~~json
{
  "totalMinor": 450000,
  "currency": "VND"
}
~~~

Nếu dùng `BigDecimal` hay decimal BSON, phải quy định **scale, rounding mode, currency precision** và cách serialize.

Không mặc định mọi đồng tiền có hai chữ số thập phân. Những quy ước “minor unit” cần căn theo currency contract của hệ.

### 11.2. Timestamp

Ví dụ:

~~~json
{
  "occurredAt": "2026-11-14T09:30:00Z"
}
~~~

Quy định:

- ISO 8601/RFC 3339 hay epoch milliseconds?
- Timestamp UTC hay kèm offset?
- Precision giây, millisecond hay nanosecond?
- Nó đại diện event time, commit time hay ingest time?
- Có được do thiết bị offline cấp không?
- Ordering có dựa vào timestamp này không?

Một field string parse được **không tự đảm bảo causal order** giữa hai region.

---

## 12. Contract cho delivery: at-most-once, at-least-once và unknown outcome

Một producer phát event không có nghĩa mỗi consumer nhận **đúng một lần** trong mọi failure mode.

### 12.1. At-most-once

Có thể bị mất event trong một số lỗi nếu không có cơ chế redelivery phù hợp. Được chọn khi mất một số message được chấp nhận theo business contract.

### 12.2. At-least-once

Consumer có thể nhận lại một event. Cần **deduplication/idempotent handler** nếu tác động không được phép nhân lên.

~~~text
Event E1 -> Consumer applies DB update.
Consumer crashes before broker ACK.
Broker redelivers E1.
~~~

Nếu consumer cập nhật counter bằng increment mỗi lần nhận, số liệu có thể bị cộng hai lần.

### 12.3. “Exactly-once” có phạm vi

Một broker/stream processor có thể cung cấp transactional semantics trong phạm vi nhất định. Nhưng điều đó **không tự tạo exactly-once business side effects xuyên** broker, source NoSQL, payment, email và search index.

Luôn hỏi: exactly-once ở đâu, với những resource nào, dưới mô hình lỗi nào?

### 12.4. Timeout khi ghi là UNKNOWN

Nếu consumer gửi write tới NoSQL, DB đã commit nhưng ACK bị mất, client có thể timeout. Retry với event ID mới hoặc phép cộng không idempotent sẽ nguy hiểm.

Một contract xử lý phải nêu:

- `eventId` ổn định qua redelivery.
- Idempotency scope.
- Đường đọc authoritative để xác minh kết quả.
- Có transaction/conditional write cho projection và inbox không?
- Số attempts và DLQ policy.
- Cách đối soát `UNKNOWN` outcome.

---

## 13. Contract cho ordering và aggregate version

Không phải mọi broker giữ **thứ tự toàn cục**. Nhiều hệ chỉ giữ một thứ tự xác định trong partition/stream key, và producer cũng phải phát theo thứ tự hợp lệ.

Ví dụ:

~~~text
Order ord-9001:
  version 10: CREATED
  version 11: PAID
  version 12: REFUNDED
~~~

Nếu consumer nhận:

~~~text
v12 trước v11
~~~

mà ghi đè state theo arrival order, read model có thể **đi lùi** về PAID.

### 13.1. Quy tắc per-aggregate version

Một projection có thể lưu:

~~~json
{
  "orderId": "ord-9001",
  "lastAppliedVersion": 12,
  "status": "REFUNDED"
}
~~~

Và áp dụng:

- Nếu event version đã xử lý hoặc cũ hơn: duplicate/stale, không ghi lùi.
- Nếu version bằng expected next: áp event.
- Nếu có gap: chờ/re-fetch/rebuild theo protocol.
- Nếu event là snapshot đầy đủ: có thể bỏ qua một số delta nếu contract cho phép.

### 13.2. Version không tự đủ cho partial events

Nếu v12 là `OrderRefunded` delta cần dữ liệu từ v11, consumer không được bỏ qua v11 chỉ vì v12 lớn hơn. Nó phải có state/logic để tái dựng đúng.

### 13.3. Không tự tạo global order

Hai Order khác nhau có `aggregateVersion=12` không liên quan thứ tự toàn hệ. Nếu một báo cáo cần snapshot across aggregates, phải có cơ chế watermark/transactional snapshot hoặc reconcile, không chỉ so `max(aggregateVersion)`.

---

## 14. Contract giữa event và mô hình lưu trữ NoSQL

Một event là **thông điệp về domain**, còn document lưu trữ là **projection phục vụ truy vấn**.

Ví dụ source event:

~~~json
{
  "eventType": "OrderConfirmed",
  "tenantId": "tenant-7",
  "aggregateId": "ord-9001",
  "aggregateVersion": 18,
  "payload": {
    "orderId": "ord-9001",
    "currency": "VND",
    "totalMinor": 450000
  }
}
~~~

Read model MongoDB của Notification có thể là:

~~~json
{
  "_id": "tenant-7:ord-9001",
  "tenantId": "tenant-7",
  "orderId": "ord-9001",
  "notificationState": "PENDING",
  "orderTotalMinor": 450000,
  "currency": "VND",
  "sourceVersion": 18,
  "sourceEventId": "evt-5b2f"
}
~~~

Analytics read model có thể chọn khóa theo ngày:

~~~json
{
  "_id": "tenant-7:2026-11-14",
  "tenantId": "tenant-7",
  "dayUtc": "2026-11-14",
  "confirmedOrderCount": 138,
  "confirmedTotalMinor": 104500000,
  "projectionWatermark": "source-checkpoint-xyz"
}
~~~

Hai projections khác nhau **không cần có cùng document schema**. Tuy nhiên chúng cần nhất quán về nghĩa của `totalMinor`, tenant, event type và xử lý duplicate.

### 14.1. Storage key là thành phần contract nội bộ

Ví dụ:

~~~text
Notification document ID = tenantId + ":" + orderId
Analytics partition key   = tenantId + ":" + UTC_DAY
~~~

Cần thống nhất:

- Cách encode separator (tránh collision).
- Uniqueness scope.
- Tenant isolation.
- Normalization/case-sensitivity.
- Độ dài khóa.
- Thay đổi khóa khi rename/merge tenant.
- Truy vấn nào bắt buộc biết key.
- TTL và index theo access pattern.

### 14.2. Không dùng event payload làm DB insert mù quáng

Nếu consumer làm:

~~~java
collection.insertOne(event.payloadAsDocument());
~~~

mà không có mapper, validation, idempotency và version guard, producer có thể vô tình thêm PII, phá index, đổi storage key hoặc ghi đè state nội bộ của consumer.

---

## 15. MongoDB: document schema validation và contract mapper

MongoDB cho phép document không đồng nhất schema, nhưng ứng dụng có thể thiết kế các rule bằng **collection validation** và indexes khi phù hợp.

Ví dụ minh họa tạo validation cho projection:

~~~javascript
db.runCommand({
  collMod: "order_notifications",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "orderId",
        "notificationState", "sourceVersion"
      ],
      properties: {
        _id: {
          bsonType: "string"
        },
        tenantId: {
          bsonType: "string"
        },
        orderId: {
          bsonType: "string"
        },
        sourceVersion: {
          bsonType: ["long", "int"]
        },
        notificationState: {
          enum: ["PENDING", "SENT", "FAILED"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đoạn này chỉ minh họa cho một collection **đã tồn tại**; `collMod` có yêu cầu quyền và giới hạn theo MongoDB version/deployment. Cần kiểm tra dữ liệu hiện có, kiểu BSON thực tế, index và đường migration trước khi áp vào production.

### 15.1. Validator không phải event contract đầy đủ

Nó bảo vệ dữ liệu lưu tại collection theo những quy tắc đã khai báo. Nó **không biết** event đã được phép phát chưa, số tiền thuộc phiên bản semantics nào hoặc payment side effect đã xảy ra chưa.

### 15.2. Unique index và tenant scope

Một read model nhiều tenant có thể cần unique constraint cho `(tenantId, orderId)` hoặc một `_id` đã canonicalize tương ứng. Với sharded collections, các ràng buộc index/uniqueness phụ thuộc shard key và topology; không tự coi unique index nào cũng có tính duy nhất toàn cluster trong mọi cấu hình.

### 15.3. Atomic update theo version

Một consumer có thể cập nhật document theo điều kiện source version chưa bị ghi mới hơn, nhưng cách thiết kế phải xử lý **create-if-absent và concurrent updates** chính xác. Đừng tách “read version rồi write” thành hai thao tác rời mà gọi là atomic.

---

## 16. DynamoDB: hợp đồng khóa và attribute dù dịch vụ schemaless

Một model DynamoDB thường sử dụng **primary key** để phục vụ access pattern:

~~~text
PK = TENANT#tenant-7
SK = ORDER#ord-9001
~~~

Item:

~~~json
{
  "PK": "TENANT#tenant-7",
  "SK": "ORDER#ord-9001",
  "status": "CONFIRMED",
  "totalMinor": 450000,
  "sourceVersion": 18,
  "sourceEventId": "evt-5b2f"
}
~~~

### 16.1. Schema-on-write ở ứng dụng

DynamoDB không bắt toàn bộ item có cùng các thuộc tính phi-key. Nhưng producer/consumer vẫn phải xác định:

- Key format.
- Data types.
- Required attributes theo entity.
- Attribute existence/missing semantics.
- Index keys của GSI.
- Độ mới của GSI so với base table.
- TTL attribute và xóa bất đồng bộ.
- Conditional write/version semantics.

### 16.2. Idempotent conditional update

Một `UpdateItem` có thể sử dụng `ConditionExpression` để không ghi lùi `sourceVersion`.

~~~javascript
const input = {
  TableName: "OrderProjection",
  Key: {
    PK: "TENANT#tenant-7",
    SK: "ORDER#ord-9001"
  },
  UpdateExpression: [
    "SET #s = :status",
    "totalMinor = :total",
    "sourceVersion = :version"
  ].join(", "),
  ConditionExpression:
    "attribute_not_exists(sourceVersion) OR sourceVersion < :version",
  ExpressionAttributeNames: {
    "#s": "status"
  },
  ExpressionAttributeValues: {
    ":status": "CONFIRMED",
    ":total": 450000,
    ":version": 18
  }
};
~~~

Đây là **một partial code object**, không phải đoạn tự chạy; cần AWS SDK và error classification. Nó giả định version tăng đơn điệu theo cùng item, event có đủ snapshot fields và update được phép bỏ qua versions cũ. Nếu event là delta có thứ tự bắt buộc, policy phải xử lý gap.

### 16.3. GSI là một contract đọc khác

GSI cập nhật với eventual consistency. Một consumer verify write qua GSI có thể chưa thấy bản mới dù base-table write đã commit. Contract phải nêu **read path để đối soát**.

### 16.4. Đổi key là migration, không chỉ rename field

Nếu thay `PK=TENANT#...` thành `PK=ORDER#...`, các query và consumer mapping phải thay đổi. Có thể cần dual-read, backfill và cutover, khác xa việc thêm một field optional.

---

## 17. Cassandra: partition key và query-driven schema

Cassandra định hình bảng theo truy vấn. Một read model:

~~~sql
CREATE TABLE orders_by_tenant_day (
  tenant_id text,
  order_day date,
  created_at timestamp,
  order_id text,
  status text,
  total_minor bigint,
  source_version bigint,
  PRIMARY KEY (
    (tenant_id, order_day),
    created_at,
    order_id
  )
) WITH CLUSTERING ORDER BY (
  created_at DESC,
  order_id ASC
);
~~~

### 17.1. Key contract phục vụ truy vấn

Consumer phải biết:

- `tenant_id` và `order_day` là partition key.
- `created_at, order_id` quyết định clustering order.
- Field `order_day` theo UTC/event time hay ingest time.
- Một order được giữ ở bucket nào khi correction/backfill.
- Bảng phục vụ “đơn theo tenant và ngày”, không tự phục vụ “đơn theo payment ID”.

### 17.2. Thêm field so với thay key

Thêm cột thường có độ ảnh hưởng khác với thay partition/clustering key. Đổi key có thể cần **tạo bảng mới và backfill** theo access pattern.

### 17.3. Upsert không tự idempotent mọi nghiệp vụ

Cassandra mutation vào cùng row có thể được gửi lại, nhưng timestamp/tombstone/conflict semantics và các counter operations phải được hiểu riêng. Nếu consumer increment aggregate mỗi lần nhận event, duplicate delivery vẫn có thể làm đếm sai.

### 17.4. LWT khi cần điều kiện

Nếu phải thực hiện compare-and-set để tránh ghi lùi version, có thể cần LWT trong phạm vi phù hợp. Chi phí và throughput của LWT khác regular write; thiết kế contract không được mặc định mọi ghi có tính atomic điều kiện xuyên nhiều partition.

---

## 18. Hợp đồng lưu trữ không chỉ gồm field: index, TTL và consistency

### 18.1. Index là phần của performance contract

Producer mới phát query yêu cầu lọc theo `customerRef` nhưng read model chỉ có index `(tenantId, createdAt)`. API có thể đúng kết quả nhưng scan rộng, làm p99 tăng.

Một storage contract nên ghi:

~~~text
Access pattern: list recent orders of one tenant
Required key/filter: tenantId
Sort: createdAt DESC, orderId DESC
Max page size: 100
Expected index/access path: tenantId + createdAt + orderId
~~~

Cấu trúc index cụ thể tùy DBMS. Không hứa SLO nếu không đo plan thực tế.

### 18.2. TTL là semantics nghiệp vụ

Nếu consumer dùng idempotency record để dedup callback trong 30 ngày mà storage TTL chỉ 24 giờ, retry muộn có thể bị coi là request mới.

Vì vậy contract retention gồm:

- Source data retention.
- Broker replay retention.
- Idempotency ledger retention.
- Tombstone/deletion horizon.
- Audit/legal hold.
- Search/read model retention.
- Backup retention.

Các thời hạn phải **phù hợp nhau**, không nhất thiết bằng nhau.

### 18.3. Consistency là phần của đường đọc

Nếu consumer cần read-your-writes nhưng đọc GSI/secondary/search eventual, một record mới có thể chưa xuất hiện. Phải chỉ rõ đường nào authoritative và độ trễ/staleness được phép.

### 18.4. Partition key là hợp đồng về khả năng scale

Một key định tuyến theo tenant có thể tối ưu tenant-scoped queries nhưng tạo hot tenant. Một key theo order ID có thể phân tán writes nhưng tăng fan-out khi xem toàn tenant.

Thay đổi access pattern có thể buộc thay key/index/read model. **Đánh giá schema contract và performance contract cùng nhau.**

---

## 19. Transactional outbox: giữ event phù hợp trạng thái đã commit

Một lỗi kinh điển:

~~~text
1. DB insert order CONFIRMED.
2. Publish OrderConfirmed to broker.
~~~

Nếu bước 1 thành công nhưng bước 2 thất bại, Order tồn tại nhưng consumer không nhận event.

Đổi thứ tự:

~~~text
1. Publish OrderConfirmed.
2. DB insert order CONFIRMED.
~~~

Nếu publish thành công nhưng insert thất bại, consumer thấy sự kiện cho một Order chưa commit.

### 19.1. Outbox giải quyết ranh giới DB–message

Khi database hỗ trợ transaction cần thiết:

~~~text
Single local transaction:
  UPDATE Order state to CONFIRMED
  INSERT Outbox(eventId, eventType, payload, version)
COMMIT

Later:
  Relay reads committed outbox event
  -> publishes to broker
  -> marks relay progress
~~~

Relay có thể publish trùng khi crash sau publish trước checkpoint, do đó consumer vẫn cần idempotency.

### 19.2. Outbox payload và source record

Có hai hướng:

- Lưu payload event đã được serialize/versioned trong transaction.
- Lưu reference/metadata rồi relay xây event theo quy tắc kiểm soát.

Cách thứ hai có rủi ro nếu source object thay đổi giữa commit và publish, khiến event không phản ánh state tại thời điểm business action. Cần snapshot/versioned read hoặc kỹ thuật tương ứng.

### 19.3. Không nhầm outbox với exactly-once business effect

Outbox giúp không tách rời việc commit business state và ghi **ý định phát event** trong cùng local transaction. Nó không tự bảo đảm broker và consumer nhận một lần, cũng không bao phủ payment provider ngoài DB.

### 19.4. CDC cũng cần hợp đồng

Change Data Capture có thể phát raw database changes. Nếu downstream đọc trực tiếp op-log/document delta, storage schema thay đổi có thể phá consumer. Một tầng mapping CDC sang domain event giúp giảm coupling, nhưng cần quản lý snapshot, schema, ordering, retention và replay.

---

## 20. CDC snapshot, stream và ranh giới cutover

Khi dựng read model mới, có thể cần:

~~~text
T0: Snapshot Orders.
T1: Đồng thời Orders tiếp tục thay đổi.
T2: CDC stream được phát.
T3: Consumer apply snapshot rồi delta.
~~~

Nếu snapshot và CDC không có một điểm nhất quán liên kết, có thể xảy ra:

- Bỏ sót write giữa hai giai đoạn.
- Áp duplicate một write trong cả snapshot và stream.
- Snapshot cũ ghi đè event mới hơn.
- Consumer chưa có row gốc khi nhận delta.
- Schema version thay đổi giữa snapshot và stream.

### 20.1. Checkpoint contract

Cần định nghĩa snapshot position/checkpoint, event offsets hoặc watermark mà engine cung cấp. Không tự dùng thời gian máy tính làm ranh giới nếu source có transaction ordering khác.

### 20.2. Apply idempotent và version-aware

Consumer nên áp events theo một chiến lược nhất quán:

- Event IDs để dedup.
- Version hoặc checkpoint để chống ghi lùi.
- Gap detection nếu event là delta.
- Snapshot version nếu event là trạng thái đầy đủ.
- Reconciliation khi stream bị mất do retention.

### 20.3. Read model mới chỉ được đưa vào phục vụ khi đạt tiêu chí

Ví dụ:

~~~text
Backfill complete for expected key scope.
CDC applied through required watermark.
Contract tests pass.
Queries match old read model within approved tolerance.
Critical business invariants hold.
~~~

Không chỉ kiểm “collection đã có dữ liệu”.

---

## 21. Consumer-driven contract testing

Producer có thể nghĩ event hợp lệ vì schema registry chấp nhận. Nhưng consumer còn có các kỳ vọng thực tế:

~~~text
Notification:
  expects tenantId and orderId,
  needs customerRef to retrieve contact preference,
  must not send twice for same eventId.

Analytics:
  requires totalMinor non-negative,
  currency known,
  order version monotonic,
  supports replay.
~~~

**Consumer-driven contract testing** cho phép consumer công bố kỳ vọng và producer kiểm tra phiên bản mới có đáp ứng hay không.

### 21.1. Một contract có thể biểu diễn qua tests

Ví dụ:

~~~text
Given an OrderConfirmed event v2:
  eventType == OrderConfirmed
  aggregateId is stable order ID
  totalMinor is integer minor units
  tenantId is not empty
  eventId unique per logical event
  event emitted only after source commit
  unknown optional fields tolerated
~~~

Một phần được kiểm bằng schema; phần khác cần integration tests hoặc business tests.

### 21.2. Không để mỗi consumer áp schema riêng vô hạn

Consumer-driven contract không có nghĩa mỗi consumer tự áp đặt cấu trúc mâu thuẫn lên producer. Cần thương lượng một **public contract có ownership**, với compatibility policy và thời hạn deprecation.

### 21.3. Công cụ không thay quy trình

Một nhóm có thể dùng Pact, JSON Schema validators, Avro/Protobuf compatibility tools, OpenAPI/AsyncAPI tooling hoặc tests tự xây. Chọn công cụ dựa trên giao thức và build pipeline thực, không mặc định chỉ một tool giải mọi semantic compatibility.

---

## 22. Java: DTO cho event và mapping có ranh giới rõ

Ví dụ Java 17 record mô tả một event đã được decode và được validation:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record OrderConfirmedV2(
    String eventId,
    String tenantId,
    String aggregateId,
    long aggregateVersion,
    Instant occurredAt,
    OrderPayload payload
) {
    public OrderConfirmedV2 {
        requireNonBlank(eventId, "eventId");
        requireNonBlank(tenantId, "tenantId");
        requireNonBlank(aggregateId, "aggregateId");
        if (aggregateVersion < 1) {
            throw new IllegalArgumentException(
                "aggregateVersion must be positive"
            );
        }
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(payload);
    }

    private static void requireNonBlank(
            String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " must be present"
            );
        }
    }

    public record OrderPayload(
        String orderId,
        String currency,
        long totalMinor,
        String customerRef,
        List<OrderLine> lines
    ) {
        public OrderPayload {
            requireNonBlank(orderId, "orderId");
            requireNonBlank(currency, "currency");
            if (totalMinor < 0) {
                throw new IllegalArgumentException(
                    "totalMinor cannot be negative"
                );
            }
            lines = lines == null
                ? List.of()
                : List.copyOf(lines);
        }
    }

    public record OrderLine(
        String productId,
        long quantity,
        long unitPriceMinor
    ) {
        public OrderLine {
            requireNonBlank(productId, "productId");
            if (quantity <= 0 || unitPriceMinor < 0) {
                throw new IllegalArgumentException(
                    "Invalid order line"
                );
            }
        }
    }
}
~~~

### 22.1. Bảo vệ DTO khác bảo vệ storage

Record constructor giúp chặn một số dữ liệu bất hợp lệ trong JVM; nó không đảm bảo:

- JSON decoder chọn đúng field/format/version.
- Event chưa duplicate.
- `totalMinor` đúng tổng line items.
- `tenantId` được ủy quyền.
- Event đã commit ở nguồn.
- Storage update là atomic.

### 22.2. Có cần luôn dùng record?

Không. Có thể dùng class, Avro-generated types, Protobuf messages hoặc types khác. Điều cần giữ là **mapping tường minh và validation**, không phụ thuộc một cú pháp Java cụ thể.

### 22.3. Tránh trả DTO event trực tiếp qua API nếu nghĩa khác

Public HTTP response `OrderView` có thể có lifecycle, field security và deprecation khác `OrderConfirmedV2`. Dùng cùng class cho mọi boundary có thể khiến thay đổi ở một nơi phá nơi khác.

---

## 23. Java: tách transport mapping khỏi consumer projection

Thay vì đưa raw event vào database, sử dụng mapping:

~~~java
import java.time.Instant;

public record NotificationProjection(
    String key,
    String tenantId,
    String orderId,
    long sourceVersion,
    long totalMinor,
    String currency,
    String notificationState,
    Instant orderOccurredAt
) {}

public final class NotificationMapper {

    public NotificationProjection map(
            OrderConfirmedV2 event) {
        String key = event.tenantId()
            + ":" + event.aggregateId();

        return new NotificationProjection(
            key,
            event.tenantId(),
            event.payload().orderId(),
            event.aggregateVersion(),
            event.payload().totalMinor(),
            event.payload().currency(),
            "PENDING",
            event.occurredAt()
        );
    }
}
~~~

### 23.1. Không nên bỏ `schemaVersion` ở transport layer

Ví dụ DTO trên biểu diễn **sau khi** decoder đã nhận diện event type/version. Production transport envelope phải nhận diện schema version/subject trước khi mapping vào `OrderConfirmedV2`.

### 23.2. Không tự tin vào separator của storage key

`tenantId + ":" + orderId` là ví dụ ngắn. Nếu IDs có thể chứa `:`, cần escaping/canonical encoding để tránh collision. Có thể dùng composite primary key native hoặc length-prefixing phù hợp DBMS.

### 23.3. Projection mapper phải xác định “đủ dữ liệu”

Nếu `OrderConfirmed` chỉ có `orderId` mà thiếu dữ liệu cần gửi notification, consumer có thể query source API hoặc nhận event payload đã thiết kế. Nhưng **không lấy thêm dữ liệu hiện tại** rồi coi đó chắc chắn là snapshot ở thời điểm event nếu nghiệp vụ yêu cầu historical value.

---

## 24. Java: áp dụng event idempotent và chống ghi lùi

Một thiết kế repository có thể công bố operation:

~~~java
public sealed interface ApplyResult
    permits Applied, Duplicate, Gap, Conflict {
}

public record Applied(long version)
    implements ApplyResult {
}

public record Duplicate(long version)
    implements ApplyResult {
}

public record Gap(
    long expectedNextVersion,
    long receivedVersion
) implements ApplyResult {
}

public record Conflict(String reason)
    implements ApplyResult {
}

public interface OrderProjectionStore {

    ApplyResult applyIfNextVersion(
        String tenantId,
        String orderId,
        long eventVersion,
        String eventId,
        NotificationProjection projection
    );
}
~~~

`applyIfNextVersion()` là **hợp đồng trừu tượng**. Để implementation đúng cần atomic conditional update, transaction hoặc per-key serial processing theo khả năng DBMS. Code Java `getCurrentVersion(); if (...) write(...)` trong hai calls riêng **không đảm bảo atomicity** khi có nhiều consumers.

### 24.1. Phân biệt full snapshot và delta

Nếu event là **snapshot đầy đủ**, một chính sách cho phép `eventVersion > currentVersion` có thể hợp lý trong một số projection. Nếu event là **delta**, cần đúng `expectedNextVersion` hoặc cơ chế tái tạo từ source để tránh bỏ qua thay đổi giữa chừng.

### 24.2. Duplicate event không phải luôn là duplicate version

Hai event khác nhau có thể cùng aggregateVersion nếu producer không đảm bảo uniqueness hoặc mỗi state change tạo nhiều event types. Contract phải làm rõ khi dùng key `(aggregateId, eventId)` và khi dùng `aggregateVersion`.

### 24.3. Thứ tự không được áp bằng arrival time

Một event version 17 tới muộn sau version 18 không được ghi đè projection của 18, trừ khi domain có quy tắc bù trừ được version hóa rõ.

---

## 25. Inbox, idempotency ledger và xử lý lại sau crash

Tình huống:

~~~text
1. Consumer nhận event E.
2. Consumer ghi projection.
3. Consumer crash trước broker ACK.
4. Broker redelivers E.
~~~

Nếu chỉ có inbox record ghi riêng sau projection update, crash giữa hai bước vẫn có nguy cơ ghi projection lần nữa.

### 25.1. Hợp đồng idempotency đúng boundary

Nếu DBMS hỗ trợ, dùng một transaction local gồm:

~~~text
BEGIN
  IF inbox(eventId) exists:
      no-op / return duplicate
  ELSE:
      apply business projection
      insert inbox(eventId, appliedAt)
COMMIT
~~~

Nếu projection là increment aggregate, yêu cầu atomicity càng quan trọng. Nếu DBMS không hỗ trợ transaction giữa các item/partition cần thiết, phải thiết kế projection có tính idempotent tự nhiên, conditional writes hoặc recovery workflow.

### 25.2. Inbox retention

Giữ inbox ID bao lâu? Nó phải bao phủ thời gian replay/redelivery có thể xảy ra theo contract. Nếu broker lưu event 30 ngày nhưng inbox TTL 1 ngày, replay sau một tuần có thể bị xử lý lần nữa.

### 25.3. Quá nhiều event IDs

Một inbox vô hạn tăng storage. Có thể dùng version/high-watermark per aggregate khi event ordering và replay semantics cho phép, nhưng không tự bỏ idempotency khi có gaps hoặc nhiều events cùng version.

### 25.4. Poison message

Nếu message luôn vi phạm schema, retry vô hạn không giúp. Cần typed error, dead-letter hoặc quarantine, cảnh báo owner producer và cơ chế replay sau khi sửa.

---

## 26. Phân loại lỗi contract khi consumer nhận dữ liệu

Một consumer nên phân biệt:

| Lỗi | Ví dụ | Hành động khái niệm |
|---|---|---|
| Serialization invalid | JSON malformed | Quarantine/DLQ, không retry nóng vô hạn |
| Unsupported schema version | Consumer v1 gặp v3 | Dừng, alert/migrate/adapter |
| Semantic validation | Currency không hỗ trợ | Domain rejection/quarantine |
| Unauthorized scope | Tenant mismatch | Security incident, không ghi |
| Stale/duplicate | Event đã apply | No-op idempotent |
| Version gap | Nhận v12, thiếu v11 | Buffer/replay/rebuild theo policy |
| Temporary DB outage | Connection timeout | Bounded retry với backoff |
| Unknown write outcome | DB commit có thể thành công | Read/ledger/conditional retry |
| Downstream throttling | Rate/capacity limit | Backpressure, retry budget |
| Business conflict | Order bị cancel trước confirm | Workflow/reconciliation |
| Deleted resource | PII đã xóa, event cũ replay | Retention/deletion policy |
| Mixed schema migration | V1 document đọc bằng mapper V2 | Compatibility adapter/backfill |

Không gửi toàn bộ errors vào một retry loop giống nhau. Một event không parse được **không tự trở nên parse được** khi retry 1.000 lần.

---

## 27. Phiên bản hóa hợp đồng: schema version khác event version

Có ít nhất ba khái niệm:

1. `schemaVersion`: representation/contract version.
2. `aggregateVersion`: thứ tự business changes cho một entity theo source.
3. `eventId`: identity của một event logic để dedup.

Ví dụ:

~~~json
{
  "eventId": "evt-100",
  "schemaVersion": 3,
  "aggregateId": "ord-9001",
  "aggregateVersion": 27,
  "eventType": "OrderConfirmed"
}
~~~

Không so `schemaVersion=3` với `aggregateVersion=27` để quyết định event nào mới hơn.

### 27.1. Khi nào phải tạo event type/version mới?

Khi ý nghĩa breaking:

- `amount` đổi đơn vị.
- `OrderConfirmed` được phát trước commit thay vì sau commit.
- `customerId` đổi uniqueness scope.
- `status=PAID` đổi nghĩa từ captured sang authorized.
- Một event snapshot biến thành delta không có metadata tương thích.
- Giá trị còn giữ tên nhưng không thể được consumer cũ hiểu đúng.

Khi đó cân nhắc một version mới có adapter/dual-publish, không âm thầm tái sử dụng cùng hợp đồng.

### 27.2. Không phát mọi thứ lên một topic chung nếu không quản trị nổi

Một topic chứa nhiều event types/versions có thể hợp lệ, nhưng cần metadata định tuyến, schema subjects, partitioning, auth và consumer deserialization rõ. Không trộn message không có type metadata rồi bắt consumer đoán cấu trúc.

---

## 28. Schema registry, catalog và kiểm tra compatibility

Một **schema registry** có thể quản lý:

- Schema definitions.
- Subject/event names.
- Version history.
- Compatibility mode.
- References/imports.
- ID hoặc fingerprint để encoder/decoder tìm schema.

Một **data catalog** có thể lưu thêm:

- Data owner.
- Ý nghĩa nghiệp vụ và field descriptions.
- Consumer dependencies.
- SLA/SLO/freshness.
- PII classification.
- Retention and lineage.
- Contact/on-call.
- Deprecation status.

### 28.1. Registry không thay producer validation

Một producer có thể đăng schema hợp lệ nhưng publish một payload sai do mapper bug nếu runtime không validate/serialize theo schema đã đăng.

### 28.2. Schema check không thay semantic check

Registry có thể chấp nhận `totalMinor` từ int32 lên int64 tùy codec compatibility rules, nhưng nó không biết nghĩa “sau thuế” đã đổi.

### 28.3. Transitive policy cần xem lịch sử

Nếu consumer đôi khi replay dữ liệu hai năm trước, kiểm tra v10 chỉ so với v9 có thể bỏ qua việc v10 không đọc được v1. Cần transitive checks hoặc legacy adapters phù hợp replay horizon.

### 28.4. Không phụ thuộc registry availability vào mọi message nếu không cần

Một số serialization frameworks cache schema IDs/definitions hoặc bundle codegen. Cần thiết kế failure behavior khi registry tạm lỗi; tránh làm một control-plane outage biến thành data-plane outage quá rộng.

---

## 29. Quy trình thay đổi hợp đồng theo hướng expand–migrate–contract

Một cách triển khai rename `amount` → `totalMinor`:

### Pha 1 — Expand

Producer có thể phát cả field cũ và mới:

~~~json
{
  "amount": 450000,
  "totalMinor": 450000,
  "currency": "VND"
}
~~~

Điều kiện: semantics của hai field phải tương thích hoặc được mô tả rõ; không đặt cùng số nếu thực tế đơn vị khác.

Consumer mới phải đọc được field mới, đồng thời có fallback xử lý old events. Cần tránh logic mâu thuẫn nếu hai field có giá trị khác.

### Pha 2 — Migrate

- Tìm consumer còn đọc field cũ.
- Cập nhật và triển khai consumers.
- Backfill dữ liệu lịch sử nếu cần.
- Chạy contract tests và production-safe metrics.
- So kết quả read model cũ/mới.
- Quan sát DLQ và schema errors.

### Pha 3 — Contract

Khi đã có bằng chứng không còn consumer/reader cần field cũ và replay horizon đã được xử lý, producer có thể ngừng phát field cũ ở một phiên bản phù hợp.

### 29.1. Vì sao không gỡ field ngay khi consumer mới đã deploy?

Vì có thể vẫn có:

- Consumer instance cũ chưa rollout hết.
- Một job batch chạy hàng tuần.
- DLQ/replay dùng payload cũ.
- Mobile/offline clients.
- Một external partner không theo lịch deploy.
- Backup/restore cần parse dữ liệu lịch sử.

### 29.2. Deprecation cần ngày và bằng chứng

Một hợp đồng nên ghi:

~~~text
Field: amount
Status: deprecated
Replacement: totalMinor
Deprecated since: schema v2
Earliest removal: after confirmed consumer migration
Owner: order-service
Migration guide: OrderConfirmed v1 -> v2
~~~

Thời hạn cụ thể phải được thống nhất từ thực tế, không tự áp một khoảng chung cho mọi hệ.

---

## 30. Dual-read, dual-write và shadow projection

Khi đổi storage key hoặc database:

~~~text
Old: OrdersByTenant
New: OrdersByOrderId
~~~

Không thể chỉ thay tên collection rồi kỳ vọng mọi consumers chuyển ngay.

### 30.1. Dual-read

Reader thử mô hình mới rồi fallback mô hình cũ nếu cần. Phải phân biệt:

- Không tìm thấy do chưa backfill.
- Không tìm thấy do quyền truy cập.
- Không tìm thấy do delete.
- Không tìm thấy do replica/index stale.

Fallback bừa có thể phục hồi dữ liệu đã xóa hoặc trả kết quả stale.

### 30.2. Dual-write

Ứng dụng ghi cả old/new stores trong migration. Có rủi ro:

~~~text
Old write committed.
New write failed.
Client timeout.
Retry duplicates one side.
~~~

Cần stable IDs, version, reconciliation và cutover policy. Hai independent writes **không tự là atomic transaction**.

### 30.3. Shadow projection

Có thể xây projection mới bằng CDC/outbox mà chưa phục vụ read traffic:

~~~text
Source events -> old projection (serving)
              -> new projection (shadow)
~~~

Sau đó so:

- Count/record-level values.
- Query results.
- Error rates.
- Gaps/version watermarks.
- Storage/index costs.
- Latency.
- Business invariants.

### 30.4. Cutover

Chỉ switch read path khi:

- Backfill hoàn tất trong phạm vi cần.
- CDC đã bắt kịp checkpoint.
- Critical queries đúng theo contract.
- Không còn schema errors chủ đạo.
- Có rollback/read fallback được thiết kế.
- Retention/TTL/delete behavior đúng.

Một shadow projection có count bằng nhau chưa chứng minh mọi record hoặc quyền xóa đều đúng.

---

## 31. Backfill dữ liệu lịch sử và khái niệm “thời gian đúng”

Giả sử producer thêm `shippingCountryCode` vào event v2. Analytics phải xử lý 2 năm đơn hàng cũ.

Có ba lựa chọn khác nhau:

1. **Suy ra từ historical snapshot** nếu nguồn còn dữ liệu đã được ghi ở thời điểm Order.
2. **Dùng current profile** để điền thiếu (có thể sai lịch sử nếu khách đổi địa chỉ).
3. **Đánh dấu unknown** nếu không có bằng chứng đúng.

Không tự backfill bằng current profile rồi báo đó là quốc gia giao hàng lúc mua.

### 31.1. Backfill là một workload riêng

Quét NoSQL toàn table, xây index và phát lại hàng triệu events có thể gây:

- Capacity/IOPS tăng.
- Compaction.
- CDC lag.
- Retry amplification.
- Throttle hoặc ảnh hưởng checkout.
- Lặp side effects nếu consumer không có chế độ replay an toàn.

Cần giới hạn concurrency/batch, checkpoint/idempotency và quan sát p99.

### 31.2. Replay phải phân biệt side effect

Replaying `OrderConfirmed` để xây lại Analytics **không được gửi lại email xác nhận hoặc charge payment**. Cần consumer behavior riêng hoặc idempotency để phân biệt reconstruction với user-facing effect.

### 31.3. Idempotency horizon phải đủ

Nếu event cũ được replay sau 6 tháng, inbox record hết TTL sau 7 ngày, một notification consumer có thể gửi lại email. Contract phải quy định replay policy hoặc bảo vệ ở domain layer.

---

## 32. Bảo mật và quyền riêng tư trong data contract

Một field hợp lệ về schema vẫn có thể bị cấm phát cho consumer nhất định.

### 32.1. Phân loại dữ liệu

| Nhóm | Ví dụ | Chính sách cần xác định |
|---|---|---|
| Public metadata | Event type, schema version | Visibility bình thường |
| Tenant-scoped | Tenant ID, order reference | Tenant authorization |
| Personal data | Email, phone, address | Minimization, encryption, retention |
| Sensitive business | Giá hợp đồng, risk score | ACL, audit |
| Secrets | API keys, tokens, passwords | Không phát trong event |
| Derived fields | Hashed identifiers, analytics cohort | Đánh giá khả năng tái nhận dạng |

### 32.2. Data minimization

Notification cần `customerRef`, chưa chắc cần toàn bộ địa chỉ/billing data. Analytics có thể cần tổng tiền và region aggregate, không cần tên và số điện thoại.

Giảm field công bố giúp giảm coupling và surface bảo mật.

### 32.3. PII delete và replay

Nếu một user yêu cầu xóa dữ liệu theo chính sách áp dụng, chỉ xóa source document có thể chưa đủ:

- Events cũ vẫn ở broker hoặc archive.
- Read models còn bản sao.
- Search index còn document.
- Backup/restore có dữ liệu cũ.
- Offline consumers có thể replay và tái tạo PII.

Contract phải mô tả deletion propagation, retention và các ràng buộc pháp lý liên quan. Không có một cơ chế xóa chung phù hợp mọi hệ.

### 32.4. Tenant ID không thay authentication

Một event mang `"tenantId":"tenant-7"` không tự chứng minh producer được phép gửi data của tenant đó. Broker ACL, producer identity, consumer permissions và input validation vẫn cần thiết.

### 32.5. Không log payload thô khi có PII

Schema validation errors có thể log event ID, field path, schema version và loại lỗi thay vì dump toàn bộ payload chứa thông tin cá nhân.

---

## 33. SLO và dữ liệu có chất lượng: contract vận hành

Một data contract tốt nên nêu độ trễ và độ hoàn chỉnh.

Ví dụ:

~~~yaml
contract:
  eventType: OrderConfirmed
  producer: order-service
  ownerTeam: order-platform
  schemaVersion: 2
  delivery:
    expectedMode: at-least-once
    orderingScope: per-order-when-source-guaranteed
    duplicateKey: eventId
  freshness:
    notificationTarget: "business-defined latency SLO"
    analyticsTarget: "business-defined watermark SLO"
  retention:
    source: "defined by source policy"
    eventReplay: "defined by broker policy"
    idempotencyLedger: "covers agreed replay horizon"
  privacy:
    tenantScoped: true
    piiFields: []
  changeManagement:
    compatibility: "producer-consumer matrix"
    deprecationRequiresConsumerEvidence: true
~~~

Đây là ví dụ **contract manifest**, không phải file cấu hình broker/registry tự hiểu.

### 33.1. Chỉ số cần đo

- Schema decode failure rate.
- Unknown enum/version count.
- Invalid semantic payload count.
- Events with missing required identifiers.
- Duplicate event rate.
- Consumer lag/time-to-project.
- DLQ volume và age.
- Replay success/failure.
- Source/projection mismatch count.
- Event time → published time lag.
- Published time → applied time lag.
- Per-tenant failure rate.
- Sensitive field leakage alerts.
- Field deprecation usage.

### 33.2. Tại sao cần tính completeness?

Consumer có thể xử lý nhanh những messages đọc được, nhưng bỏ 2% lỗi schema vào DLQ. Latency p99 của những messages thành công vẫn đẹp, trong khi báo cáo thiếu doanh thu.

Phải đo **completed / expected / invalid / pending / dropped** theo logical event scope, không chỉ tốc độ consumer.

---

## 34. Data lineage: ai phụ thuộc vào field nào?

Một bản lineage đơn giản:

~~~text
Order Service
  source Orders.totalMinor
      |
      +-> OrderConfirmed.payload.totalMinor
                |
                +-> Analytics.dailyRevenue
                |
                +-> MerchantDashboard.totalRevenue
                |
                +-> FinanceExport.totalMinor
~~~

Nếu muốn đổi `totalMinor` từ trước giảm giá sang sau giảm giá, lineage cho thấy những consumer cần được xem xét.

### 34.1. Field-level dependencies

Tìm “dịch vụ đăng ký topic” chưa đủ: một consumer có thể subscribe nhưng chỉ dùng `orderId`, consumer khác dùng `totalMinor` để quyết toán.

Cần biết **field được đọc và invariant nó phục vụ**, qua code search, declarations, tests, data catalog hoặc runtime metadata.

### 34.2. Không phụ thuộc quá mức vào runtime metrics

Một job chạy hàng tháng có thể không đọc field trong tuần quan sát; metric “không có access” không phải bằng chứng an toàn để xóa field.

### 34.3. Owner và escalation

Khi contract breaking mà consumer không còn owner, phải có quy trình quyết định: chuyển ownership, sunset có thông báo, hoặc giữ adapter. Không tùy tiện gỡ field vì không ai phản hồi.

---

## 35. Contract testing trong CI/CD

Một pipeline tối thiểu có thể gồm:

~~~mermaid
flowchart TD
    A["Producer changes schema/mapper"] --> B["Structural schema validation"]
    B --> C["Compatibility check with historical versions"]
    C --> D["Consumer contract tests"]
    D --> E["Semantic invariant tests"]
    E --> F["Integration test with NoSQL projection"]
    F --> G["Replay/duplicate/out-of-order tests"]
    G --> H["Security/PII checks"]
    H --> I["Canary + metrics"]
    I --> J["Gradual rollout"]
~~~

### 35.1. Structural tests

- Required fields tồn tại.
- Type và nullability đúng.
- Serialization/deserialization round-trip.
- Codec/schema ID/version nhận diện đúng.
- Unknown optional fields xử lý theo policy.
- Old/new producer fixture compatibility.

### 35.2. Semantic tests

- Currency/unit/rounding.
- Domain state transitions.
- Tổng tiền và line totals.
- Timezone/event time.
- Identity uniqueness scope.
- Tenant isolation.
- Delete semantics.

### 35.3. Delivery tests

- Duplicate E1.
- Retry sau DB timeout.
- Event v12 tới trước v11.
- Consumer crash sau DB commit trước broker ACK.
- Schema version cũ xuất hiện sau rollout.
- Changelog gap/retention expiration.
- Rebuild projection từ snapshot + stream.

### 35.4. Storage tests

- Query theo key/index được thiết kế.
- Conditional write/idempotency.
- TTL/retention.
- Stale secondary/GSI behavior.
- Backfill và rollout mixed-schema documents.
- Performance dưới representative load.

### 35.5. Không chạy test “có dữ liệu thật” thiếu quyền

Nếu cần dữ liệu thực để kiểm biến dạng schema, dùng dataset ẩn danh/được cho phép với retention và access controls. Không tự sao chép PII production vào repo/tests.

---

## 36. Java/JUnit 5: các test semantic contract đơn giản

Đoạn sau minh họa **unit tests** của mapper và DTO đã giới thiệu ở các phần trước:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

public final class OrderContractTest {

    private OrderConfirmedV2 validEvent() {
        return new OrderConfirmedV2(
            "evt-1001",
            "tenant-7",
            "ord-9001",
            18L,
            Instant.parse("2026-11-14T09:30:00Z"),
            new OrderConfirmedV2.OrderPayload(
                "ord-9001",
                "VND",
                450000L,
                "cus-42",
                List.of(
                    new OrderConfirmedV2.OrderLine(
                        "prd-10", 2L, 225000L
                    )
                )
            )
        );
    }

    @Test
    void mapsIntoConsumerOwnedProjection() {
        NotificationProjection result =
            new NotificationMapper().map(validEvent());

        assertEquals(
            "tenant-7:ord-9001", result.key()
        );
        assertEquals(
            450000L, result.totalMinor()
        );
        assertEquals(
            18L, result.sourceVersion()
        );
        assertEquals(
            "PENDING", result.notificationState()
        );
    }

    @Test
    void rejectsMissingTenant() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new OrderConfirmedV2(
                "evt-1001",
                "",
                "ord-9001",
                18L,
                Instant.now(),
                validEvent().payload()
            )
        );
    }

    @Test
    void rejectsNegativeTotal() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new OrderConfirmedV2.OrderPayload(
                "ord-9001",
                "VND",
                -1L,
                "cus-42",
                List.of()
            )
        );
    }

    @Test
    void requiresPositiveAggregateVersion() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new OrderConfirmedV2(
                "evt-1001",
                "tenant-7",
                "ord-9001",
                0L,
                Instant.now(),
                validEvent().payload()
            )
        );
    }
}
~~~

### 36.1. Chưa test deserialization JSON

Unit tests constructor không kiểm parser với `schemaVersion`, unknown fields hay schema registry. Cần thêm fixture-based serialization tests cho codec đang dùng.

### 36.2. Chưa test duplicate và DB atomicity

`NotificationMapper` đúng không chứng minh `OrderProjectionStore` có conditional update atomically. Cần integration test với DB thật hoặc môi trường mô phỏng có semantics phù hợp.

### 36.3. Chưa kiểm tổng line items

Bài tập mở rộng: tính tổng line items với overflow-safe arithmetic và đối chiếu business rules về thuế/phí/discount. Không nên mặc nhiên mọi `OrderConfirmed` đều có line items đầy đủ nếu contract cho phép payload rút gọn.

---

## 37. Ma trận kiểm thử contract khi producer và consumer nhiều phiên bản

| ID | Producer | Consumer | Storage | Expected |
|---|---|---|---|---|
| V01 | V1 | V1 | Old projection | Baseline thành công |
| V02 | V2 thêm optional | V1 tolerant | Old projection | Forward-compatible khi semantics giữ |
| V03 | V1 | V2 có default | New projection | Backward-compatible khi mapping đúng |
| V04 | V2 đổi tên breaking | V1 | Old projection | Phát hiện contract violation |
| V05 | V2 đổi đơn vị | V1 | Old projection | Semantic failure dù parse được |
| V06 | V1 historical replay | V3 | New projection | Legacy adapter/backfill |
| V07 | V2 new enum | V1 exhaustive parser | Old projection | Alert, không bỏ âm thầm |
| V08 | V2 `null` | V1 không nhận null | Old projection | Typed schema violation |
| V09 | V2 event duplicate | V2 | New projection | Idempotent result |
| V10 | V2 out of order | V2 | New projection | Không ghi lùi sourceVersion |
| V11 | V2 concurrent consumer workers | V2 | New projection | Atomic version guard |
| V12 | V2 event publish timeout | V2 | New projection | Retry cùng eventId |
| V13 | V2 DB commit/ACK lost | V2 | New projection | Outcome reconciliation |
| V14 | V2 CDC snapshot + stream | V2 | New projection | Không gap/duplicate effect |
| V15 | V2 tombstone/delete | V1/V2 | Old/new stores | Không resurrect PII |
| V16 | V2 new PK | V1 consumer | Dual-read | Migration/lookup đúng |
| V17 | V2 shadow projection | V2 | New storage | Compare result/watermark |
| V18 | V2 partial failure | V2 | GSI stale | Verify qua authoritative store |
| V19 | V2 with PII field | Unauthorized consumer | Any | Không lộ PII |
| V20 | V2 replay after TTL | V2 | Inbox expired | Không tạo side effect trùng |
| V21 | V2 gap in versions | V2 | New projection | Gap handling/rebuild |
| V22 | V2 multiple tenants | V2 | Shared storage | Isolation/uniqueness đúng |
| V23 | V2 event time drift | V2 | Time-bucket store | Bucket/window semantics đúng |
| V24 | V2 producer rollback | V3 consumer | Mixed data | Hỗ trợ version cũ |
| V25 | V2 broker DLQ replay | V2 | New projection | Correct failure classification |
| V26 | V2 large payload | V2 | New projection | Size limits/backpressure |
| V27 | V2 field deprecated | Legacy consumer | Old/new | Field chưa bị gỡ sớm |
| V28 | V2 index missing | V2 | New storage | Plan/performance regression detected |

Các expected phụ thuộc chính sách cụ thể. Ví dụ V02 chỉ pass nếu **consumer thực sự tolerant và field mới không đổi nghĩa field cũ**.

---

## 38. Thử một thay đổi thực tế: `customerId` → `customerRef`

### 38.1. Bài toán

Trước đây producer phát raw `customerId` dùng bởi ba dịch vụ. Nay producer muốn thay bằng `customerRef` để tách domain identity khỏi database key.

### 38.2. Các bước thiết kế

1. Xác định `customerId` cũ có nghĩa gì: tenant-scoped hay global?
2. Xác định `customerRef` mới có mapping một–một không?
3. Kiểm consumer nào dựa vào format cũ.
4. Thêm field mới theo contract rõ.
5. Giữ field cũ trong giai đoạn overlap nếu được phép.
6. Triển khai consumer mapper dùng `customerRef` và fallback lịch sử.
7. Tạo backfill/lookup mapping nếu cần.
8. Kiểm PII/permission cho reference mới.
9. Quan sát field usage trong window đủ dài.
10. Deprecate/remove có version và migration guide.

### 38.3. Nếu ID là một phần shard key

Đây không chỉ là event schema rename. Nếu DynamoDB PK hoặc Cassandra partition key được tạo từ `customerId`, đổi sang `customerRef` có thể làm các query cũ không tìm ra record. Cần chiến lược **storage migration** riêng.

### 38.4. Nếu consumer lưu historical snapshots

Một Order đã chốt có thể tham chiếu customer identity tại thời điểm mua. Backfill toàn bộ lịch sử bằng current merged customer ID có thể thay đổi ý nghĩa audit. Contract phải mô tả historical identity policy.

---

## 39. Xử lý lỗi schema ở production: runbook

### Bước 1 — Nhận diện loại lỗi

- Deserialize failure?
- Unknown schema version?
- Semantic invalid data?
- Storage key/index mismatch?
- Version gap?
- CDC/replication lag?
- Idempotency duplicate?
- Security/PII issue?

### Bước 2 — Bảo toàn bằng chứng

Ghi:

~~~text
eventId
eventType
schemaVersion
producer build/version
consumer build/version
tenant scope (redacted when needed)
storage projection version
broker topic/partition/offset or equivalent
error class and field path
correlation ID
retry count
~~~

Không log nguyên payload nhạy cảm để điều tra cho tiện.

### Bước 3 — Ngừng khuếch đại

Nếu lỗi permanent schema mismatch, không retry nóng vô hạn. Quarantine/DLQ có giới hạn, cảnh báo on-call và tách khỏi transient transport errors.

### Bước 4 — Chặn dữ liệu xấu lan rộng

Có thể tạm dừng producer rollout, dùng feature flag hoặc adapter khi được phép. Không tự xóa broker messages để làm dashboard xanh.

### Bước 5 — Chọn nguồn sự thật

Source authoritative order record và published event cần được so theo version/commit point. Một read model eventual hoặc search index có thể stale; không dùng nó duy nhất để tuyên bố producer chưa phát event.

### Bước 6 — Quyết định recovery

- Consumer upgrade.
- Schema-compatible adapter.
- Producer rollback nếu vẫn tương thích với data đã phát.
- Reprocess DLQ với same event IDs.
- Backfill missing projection records.
- Reconcile business side effects.
- Correct historical semantic mapping.

### Bước 7 — Kiểm kết quả

- Decode errors giảm.
- DLQ backlog drain.
- Projection watermark bắt kịp.
- Record counts/aggregate values được đối soát.
- Không có duplicate side effects.
- Tenant isolation và PII policies vẫn đúng.

### Bước 8 — Postmortem

Phân biệt root cause:

~~~text
Structural incompatibility
Semantic contract change
Storage key migration
Delivery/idempotency failure
Out-of-order event handling
Data-quality defect
Governance/deprecation miss
~~~

Một bản postmortem chỉ nói “JSON thay đổi” chưa đủ để ngăn tái diễn.

---

## 40. Các ngộ nhận thường gặp

| Ngộ nhận | Điều đúng hơn |
|---|---|
| “NoSQL schemaless nên không cần contract.” | Consumer và queries vẫn phụ thuộc cấu trúc/semantics |
| “Đã có JSON Schema là đủ.” | Còn domain rules, ordering, delivery, storage, privacy |
| “Producer deploy xanh thì consumer sẽ xanh.” | Producer unit tests không biết mọi consumer |
| “Thêm field optional luôn an toàn.” | Parser strict và semantic dependency có thể lỗi |
| “Full schema compatibility nghĩa không mất dữ liệu.” | Logic/units/business invariants vẫn có thể đổi |
| “Field thiếu và null giống nhau.” | Patch và snapshot có thể khác nghĩa |
| “Dùng double cho tiền tiện hơn.” | Precision/rounding và unit cần hợp đồng |
| “Mỗi timestamp là thứ tự thật.” | Clock skew và semantics của thời gian khác nhau |
| “Event ID và aggregate version là một.” | Identity và order là hai khái niệm |
| “Kafka giữ thứ tự mọi event trên toàn hệ.” | Ordering scope phụ thuộc partition/producer/protocol |
| “Consumer ACK broker nghĩa NoSQL commit.” | Hai hệ có transaction boundary riêng |
| “Retry event không tạo trùng.” | Handler phải idempotent |
| “Outbox đảm bảo consumer nhận đúng một lần.” | Relay/consumer vẫn có redelivery |
| “CDC raw document là domain event ổn định.” | Storage schema thay đổi có thể phá coupling |
| “DynamoDB không schema nên không cần validate.” | Attribute/key/index types vẫn là contract |
| “MongoDB validator bảo đảm nghiệp vụ.” | Validator chỉ bao phủ quy tắc đã khai báo |
| “Cassandra upsert nghĩa mọi counter retry idempotent.” | Counter/timestamp semantics cần xem riêng |
| “GSI chưa có record tức nguồn chưa commit.” | GSI có eventual consistency |
| “Đổi primary key chỉ là rename.” | Thường phải migrate và reindex |
| “Schema registry biết mọi consumer.” | Field semantics/dependency cần catalog/tests |
| “Bỏ field sau một tuần không thấy traffic.” | Consumer định kỳ/offline/replay có thể tồn tại |
| “Backfill current profile tạo historical truth.” | Giá trị hiện tại có thể khác quá khứ |
| “Shadow count khớp là cutover an toàn.” | Cần kiểm values, versions, invariants |
| “Đổi TTL chỉ giảm chi phí lưu trữ.” | Có thể làm retry/dedup/replay thất bại |
| “PII đã xóa khỏi source thì không ở đâu khác.” | Events, backups, indexes có thể giữ bản |
| “Rollback producer luôn đơn giản.” | Consumer đã nhận event v2, storage đã migrate |
| “Thông điệp không parse được nên retry liên tục.” | Permanent schema lỗi cần quarantine |
| “Contract test thay performance test.” | Query/index/capacity là ràng buộc khác |

---

## 41. Bài tập 1: phân loại breaking changes

Cho `OrderConfirmedV1`:

~~~json
{
  "orderId": "ord-1",
  "amount": 100000,
  "currency": "VND",
  "status": "CONFIRMED"
}
~~~

Đánh giá các thay đổi:

1. Thêm optional `promotionCode`.
2. Xóa `amount` và thêm `totalMinor`.
3. Giữ tên `amount` nhưng chuyển từ VND sang cents USD.
4. Thêm enum `PARTIALLY_CONFIRMED`.
5. Đổi `orderId` từ string sang object.
6. Thêm `schemaVersion`.
7. Đổi `CONFIRMED` từ “đã commit” thành “đang xử lý”.
8. Đổi `customerId` sang reference mới với format khác.
9. Thay timestamp từ epoch milliseconds sang RFC 3339 string.
10. Giảm TTL idempotency ledger từ 30 ngày còn 24 giờ.

Với mỗi thay đổi, ghi: **structural hay semantic**, backward/forward risks, consumer cần migration gì, và test nào phát hiện.

---

## 42. Bài tập 2: thiết kế contract cho `InventoryReserved`

Một hệ inventory nhiều tenant có:

~~~text
Resource: sku-42
Tenant: tenant-7
Available: 5
Consumer: Checkout, Billing, Analytics
~~~

Hãy thiết kế contract gồm:

- Event envelope.
- `reservationId`, `requestId`, `skuId`, `tenantId`.
- Quantity và đơn vị đo.
- Khi nào event được phát so với transaction commit.
- Idempotency key.
- Per-resource ordering/version.
- `expiresAt` và TTL semantics.
- Cách xử lý duplicate event.
- Cách xử lý confirm/expire cạnh tranh.
- Business invariant `confirmed + held <= capacity` theo model.
- Read model NoSQL và partition key.
- PII/access controls.
- Replay/retention SLO.

Giải thích tại sao dù event hội tụ trên mọi read model, một reservation double-confirm vẫn là lỗi.

---

## 43. Bài tập 3: xây consumer version-aware

Consumer nhận lần lượt:

~~~text
E12: Order version 12, status=REFUNDED
E10: Order version 10, status=CREATED
E11: Order version 11, status=PAID
E12: Redelivery of E12
~~~

1. Nếu events là **full snapshots**, policy có thể cập nhật projection thế nào?
2. Nếu events là **deltas phụ thuộc các version trước**, cần xử lý ra sao?
3. `eventId` và `aggregateVersion` dùng vào việc gì?
4. Vì sao dùng arrival time sẽ làm state đi lùi?
5. Nếu v11 mãi không đến, cần phục hồi từ đâu?
6. Nếu DB timeout lúc áp v12, outcome unknown được xử lý thế nào?
7. Viết `applyIfNextVersion()` atomic theo DBMS bạn chọn.

---

## 44. Bài tập 4: thiết kế migration hai schema

Giả sử Analytics cần đổi `amount` → `totalMinor` và thêm currency precision.

Hãy tạo kế hoạch:

~~~text
Expand:
  producer dual-populate
  consumer đọc cả hai

Migrate:
  deploy consumers
  backfill old data
  reconcile aggregates

Contract:
  remove old field after evidence
~~~

Yêu cầu:

- Danh sách consumer và owner.
- Backward/forward compatibility matrix.
- Historical data parsing.
- Semantic unit test.
- Outbox/replay policy.
- DLQ recovery.
- Shadow projection checks.
- Deprecation window.
- Rollback strategy khi một consumer chưa nâng cấp.

---

## 45. Bài tập 5: schema-on-read NoSQL có thật sự linh hoạt?

Một MongoDB collection chứa ba đời dữ liệu:

~~~json
{
  "_id": "old-1",
  "amount": 100000
}
~~~

~~~json
{
  "_id": "mid-2",
  "amount": 200000,
  "currency": "VND"
}
~~~

~~~json
{
  "_id": "new-3",
  "totalMinor": 300000,
  "currency": "VND",
  "schemaVersion": 3
}
~~~

Hãy thiết kế **reader adapter**:

1. Đọc đúng ba phiên bản.
2. Không mặc định currency khi không có cơ sở.
3. Không trộn đơn vị.
4. Trả typed error nếu không giải thích được record.
5. Có migration/backfill path.
6. Không âm thầm ghi lại mọi record khi chỉ đang đọc.
7. Có metrics đo số records thuộc mỗi phiên bản.

---

## 46. Bài tập 6: producer–consumer contract test bằng Java

Dựa trên `OrderConfirmedV2` và `NotificationProjection`:

1. Viết JSON fixture v1 và v2.
2. Viết decoder phân biệt `schemaVersion`.
3. Viết mapper v1→v2 với default có căn cứ.
4. Test unknown optional field.
5. Test required field missing.
6. Test `totalMinor < 0`.
7. Test enum value chưa hỗ trợ.
8. Test duplicate `eventId`.
9. Test version gap và stale event.
10. Test consumer restart sau DB commit trước broker ACK.
11. Test mapper với dữ liệu tenant khác.
12. Test historical replay không gửi notification lần hai.

Không tự tạo payment/email side effects trong unit test mapper; dùng fake/fixture hoặc integration harness được kiểm soát.

---

## 47. Bài tập 7: build read model bằng CDC

Một dữ liệu nguồn có 10 triệu Orders, cần tạo bảng query mới theo `(tenantId, createdAt)`.

Yêu cầu:

- Chọn snapshot watermark/checkpoint.
- Backfill theo batch có giới hạn tải.
- Đồng thời nhận CDC changes.
- Xử lý duplicate/gaps/out-of-order.
- Chống snapshot cũ ghi đè delta mới.
- Tạo index phù hợp access pattern.
- Giữ tenant isolation.
- So shadow query results.
- Đặt cutover gate.
- Có rollback và replay khi data mismatch.

Giải thích vì sao chỉ dựa vào “10 triệu bản ghi đã copy” không chứng minh projection hoàn chỉnh hoặc cập nhật.

---

## 48. Bài tập 8: incident vì field bị xóa sớm

Một producer bỏ `customerId` khỏi event v3. Sau rollout:

~~~text
Notification consumer mới: OK.
Analytics consumer mới: OK.
Legacy weekly export: lỗi mỗi Chủ nhật.
DLQ tăng.
Một số events đã được ACK nhưng không lưu vào export DB.
~~~

Hãy thiết kế runbook:

1. Xác định contract đã vi phạm gì.
2. Tìm các event bị ảnh hưởng bằng IDs/offsets.
3. Tại sao “2 consumers OK” chưa đủ bằng chứng?
4. Rollback producer có giúp khi đã có v3 events?
5. Xây adapter/dual field an toàn ra sao?
6. Replay vào export DB mà không tạo trùng?
7. Đối soát records ACK nhưng không được lưu.
8. Thêm contract test nào vào CI?
9. Cập nhật catalog/ownership thế nào?
10. Điều kiện đóng incident là gì?

---

## 49. Checklist thiết kế một data contract NoSQL

Trước khi công bố một hợp đồng:

- [ ] Producer owner, consumer owners và storage owners được xác định.
- [ ] Event/API type, version và schema ID rõ.
- [ ] Required/optional/null/absent/default semantics rõ.
- [ ] Tiền tệ, đơn vị đo, timezone, precision và rounding có mô tả.
- [ ] `eventId`, business request ID và aggregate ID không bị trộn.
- [ ] Event chỉ phát vào điểm hợp lệ so với source commit.
- [ ] Duplicate, ordering, retry, timeout và unknown outcome có policy.
- [ ] Consumer mapping không lưu raw payload mù quáng.
- [ ] Storage partition/shard key, index và query contracts được ghi.
- [ ] TTL, replay horizon, idempotency retention và delete semantics tương thích.
- [ ] Read consistency và projection freshness có SLA/SLO.
- [ ] Backward/forward/transitive compatibility được kiểm theo công cụ và semantic tests.
- [ ] Unknown enums/fields/version được xử lý minh bạch.
- [ ] Consumer-driven tests bao phủ dependencies thực.
- [ ] Producer/consumer/schema registry/catalog có quy trình ownership.
- [ ] Rollout hỗ trợ mixed-version và legacy replay.
- [ ] Rename/remove fields có expand–migrate–contract.
- [ ] Backfill/CDC snapshot có checkpoint, idempotency và gap detection.
- [ ] Shadow projection được đối soát trước cutover.
- [ ] PII, auth, retention, region residency và deletion propagation đúng chính sách.
- [ ] DLQ, poison message và recovery runbook có sẵn.
- [ ] Monitoring đo schema errors, semantic anomalies, lag và completeness.
- [ ] Performance test xác nhận index/query plan dưới tải thực.
- [ ] Các side effects (email/payment) không được replay tùy tiện.
- [ ] Những breaking changes có deprecation guide và evidence consumers đã chuyển.

---

## 50. Tổng kết

**Hợp đồng dữ liệu không kết thúc tại ranh giới JSON hoặc schema registry.** Nó nối **ý định nghiệp vụ**, **bên phát**, **bên nhận** và **đường lưu trữ/truy vấn**, kể cả khi mỗi dịch vụ dùng một mô hình NoSQL khác nhau.

Những nguyên tắc quan trọng:

1. **Phân biệt structure, semantics, delivery và storage.** Một message parse được vẫn có thể sai tiền, sai quyền hoặc ghi sai partition.
2. **Producer và consumer cùng chịu trách nhiệm**, nhưng phải có owner và policy rõ ràng cho từng contract.
3. **Versioning cần kiểm hai chiều**: consumer mới đọc dữ liệu cũ và consumer cũ đọc dữ liệu mới, kể cả replay lịch sử.
4. **Null, missing, default, enum và đơn vị đo** là nguồn lỗi âm thầm nếu chỉ kiểm kiểu dữ liệu.
5. **Event schema không nên là bản sao raw storage schema.** Consumer nên có projection và key/index/TTL phục vụ truy vấn của chính mình.
6. **Retry, duplicate và ordering là phần của hợp đồng.** Outbox/CDC giúp phân phối nhưng không tự tạo exactly-once business side effects.
7. **Thay đổi storage key/index/TTL cần migration**, không chỉ thêm/sửa field serialization.
8. **Expand–migrate–contract** cho phép nhiều phiên bản chạy song song và loại bỏ field cũ dựa trên bằng chứng.
9. **Contract tests phải bao gồm ngữ nghĩa, idempotency, replay, privacy và performance**, không chỉ JSON Schema valid.
10. **Một migration chỉ hoàn tất khi đã đối soát dữ liệu, đọc đúng qua đường mới và còn khả năng phục hồi** trong các trường hợp sự cố được thiết kế.

**Câu cần nhớ: “Một hợp đồng dữ liệu đáng tin phải giúp producer biết mình đang hứa gì, consumer biết mình được quyền giả định điều gì, và hệ lưu trữ biết phải bảo vệ những khóa, phiên bản, dữ liệu và bất biến nào — kể cả khi ba bên được triển khai ở những thời điểm khác nhau.”**
