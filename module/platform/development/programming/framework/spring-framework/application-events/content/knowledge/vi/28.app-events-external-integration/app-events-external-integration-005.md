# Event contract cho hệ thống khác trong Spring Framework Application Events

## 1. Tại sao domain event nội bộ chưa phải hợp đồng tích hợp?

Trong một ứng dụng Spring, `ApplicationEventPublisher.publishEvent(...)` và `@EventListener` giúp các module trao đổi **sự thật đã xảy ra** trong application context. Tuy nhiên, một hệ thống khác — chẳng hạn Billing, Fulfillment, CRM, Analytics hoặc đối tác ngoài tổ chức — không thể mặc nhiên nhận và hiểu Java object mà Spring vừa phát.

Ví dụ Ordering nhận một yêu cầu thanh toán thành công và phát:

```java
publisher.publishEvent(new PaymentCaptured(
        paymentId, orderId, amountMinor, currency));
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Kiểu `PaymentCaptured` có thể chứa object domain, enum nội bộ hoặc các ràng buộc riêng của Ordering. Nếu gửi thẳng đối tượng này qua JSON/Kafka/RabbitMQ/HTTP webhook và bắt mọi consumer phụ thuộc vào class Java tương ứng, các thay đổi nội bộ dễ vô tình phá hỏng hệ thống bên ngoài.

**Event contract cho hệ thống khác** là một **lời hứa có version** về ý nghĩa, cấu trúc, nguồn tin, cách phân phối và quy tắc xử lý một event. Nó tồn tại ở ranh giới tích hợp, thường độc lập với phiên bản code/domain model của producer.

Một contract đủ tốt trả lời được:

1. **Điều gì đã xảy ra?** Tên event và điều kiện sự thật trở thành đúng.
2. **Ai là nguồn có thẩm quyền?** Producer/service hoặc bounded context sở hữu fact.
3. **Nhận diện occurrence thế nào?** Event ID và phạm vi uniqueness.
4. **Dữ liệu nào luôn có?** Required/optional fields, kiểu và đơn vị.
5. **Thời gian, thứ tự, bản phát lại?** `occurredAt`, aggregate identity/version, ordering scope.
6. **Schema thay đổi thế nào?** Version, compatibility, deprecation.
7. **Cần xử lý lỗi thế nào?** Delivery, retry, duplicate, replay, acknowledgement, idempotency.
8. **Ai được phép xem?** Quyền truy cập, tenant boundary, PII/secrets, retention.
9. **Kiểm chứng tương thích ra sao?** Schema validation, fixtures, contract tests.

> **Nguyên tắc cốt lõi:** domain event diễn đạt sự thật trong model nội bộ; integration event diễn đạt **phần sự thật được phép công bố** theo hợp đồng ổn định cho hệ thống khác. Một bên thay đổi không nên tự động ép bên còn lại triển khai cùng lúc.

## 2. So sánh domain event và integration event

| Khía cạnh | Domain event trong Spring | Integration event bên ngoài |
| --- | --- | --- |
| Mục tiêu | Thông báo fact giữa các phần ứng dụng/domain | Công bố fact cho consumer độc lập |
| Ngữ cảnh | Bounded context và Java code nội bộ | Hợp đồng được nhiều nhóm/hệ thống hiểu |
| Biểu diễn | Record/class/`ApplicationEvent`/POJO | JSON, Avro, Protobuf, CloudEvents hoặc format thống nhất |
| Khả năng thay đổi | Có thể refactor cùng codebase | Cần compatibility và chính sách version |
| Delivery | Mặc định trong application context | Qua broker, outbox relay, webhook, event bus... |
| Reliability | Không tự bền vững khi dùng Spring core | Phải công bố rõ ack, retry, redelivery, replay |
| Security | Quyền trong process và boundary nội bộ | Producer authentication, transport ACL, tenant isolation |
| Payload | Có thể tham chiếu domain types | Nên dùng dữ liệu serializable, tối thiểu và có schema |
| Owner | Module/domain phát sự thật | Producer/contract owner và channel owner |

Không nhất thiết tạo một integration event tương ứng một-một với mỗi domain event. Có thể có domain event chỉ dành nội bộ, một domain event được chuyển thành message cho nhiều audience, hoặc một integration milestone riêng sau khi nhiều điều kiện hoàn tất.

### Ví dụ về đổi ngôn ngữ theo bounded context

```text
Billing domain:
    PaymentCapturedDomain(paymentEntity, policyDetails)
                  |
                  | anti-corruption/translation layer
                  v
Public integration contract:
    payment.captured, schemaVersion=1
    data(paymentId, orderId, amountMinor, currency)
                  |
                  +--> Fulfillment consumer
                  +--> Finance projection
                  +--> Analytics
```

Lớp chuyển đổi chỉ công bố dữ liệu có nghĩa và đã được cho phép; không serialize trực tiếp `paymentEntity` hay repository object. Billing có thể đổi aggregate class mà vẫn giữ hợp đồng `payment.captured/v1`.

## 3. “Sự thật đã xảy ra” phải có điều kiện đúng rõ ràng

Một integration event **không phải command trá hình**.

- `CapturePayment`: yêu cầu *hãy thu tiền*; thao tác có thể thất bại hoặc bị từ chối.
- `PaymentAuthorized`: provider đã cho phép authorization/hold theo hợp đồng.
- `PaymentCaptured`: khoản tiền đã được capture thành công theo nguồn xác nhận có thẩm quyền.
- `PaymentSettled`: tiền đã được settle theo quy tắc kế toán hoặc provider; có thể là mốc khác capture.
- `PaymentDeclined`: provider đã từ chối giao dịch; chỉ phát nếu đây là một fact được domain công nhận.

**Không được** phát `PaymentCaptured` ngay khi vừa gửi request capture. Consumer bên ngoài không thể biết “captured” thật ra nghĩa là “capture đang pending” nếu producer không ghi rõ semantics.

Một bảng contract nên có:

| Mục | Ví dụ cho `payment.captured` |
| --- | --- |
| Business definition | Payment provider xác nhận capture đã thành công |
| Trigger | Producer nhận và xác minh kết quả capture; business state được ghi bền vững |
| Not triggered by | Request được gửi, authorization thành công, timeout chưa rõ kết quả |
| Source of truth | Billing/Payments, không phải Ordering tự suy luận |
| Multiplicity | Mỗi capture transaction hợp lệ là một occurrence |
| Downstream meaning | Có thể cập nhật read model và khởi chạy công việc được phép sau capture |
| Non-guarantees | Không ngụ ý settlement, giao hàng thành công hay không còn refund |

Khi domain expert và các consumer thống nhất **truth condition**, khả năng schema tương thích mới có giá trị. Hai JSON giống nhau nhưng ý nghĩa “capture request accepted” và “funds captured” không phải cùng một contract.

## 4. Thiết kế envelope và business data

Một mẫu **custom integration envelope**:

```json
{
  "eventId": "6f9b27d3-160b-4ff2-a0a8-b58c3ff0ec31",
  "eventType": "payment.captured",
  "schemaVersion": 1,
  "source": "/services/billing",
  "tenantId": "tenant-blue",
  "aggregateId": "O-100",
  "correlationId": "checkout-913",
  "occurredAt": "2026-11-11T02:00:00Z",
  "data": {
    "paymentId": "P-900",
    "orderId": "O-100",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
```

Đây là **format do ví dụ tự định nghĩa**, không phải cấu trúc JSON tự sinh hoặc bắt buộc của Spring Framework hay CloudEvents. Khi chọn một format, tổ chức cần tài liệu hóa trường, owner, tính ổn định và cơ chế serialize/deserialze.

### 4.1. Metadata và data có vai trò khác nhau

| Field | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `eventId` | ID của một occurrence | Retry/redelivery **giữ nguyên** ID; không dùng ID mới cho cùng fact |
| `eventType` | Loại sự thật được công bố | Tên ổn định; không biến thành command như `doPayment` |
| `schemaVersion` | Phiên bản hợp đồng payload/envelope đã định nghĩa | Không đồng nghĩa version của ứng dụng hoặc CloudEvents `specversion` |
| `source` | Nguồn phát sự thật | Nên ổn định và được định danh rõ |
| `tenantId` | Tenant sở hữu dữ liệu nếu sự kiện tenant-scoped | Không phải bằng chứng producer/consumer đã có quyền |
| `aggregateId` | ID aggregate làm căn cứ correlate/order/partition | Không phải mọi event đều có cùng loại aggregate |
| `correlationId` | Liên kết workflow/request | Có thể có nhiều event với cùng correlation ID |
| `occurredAt` | Mốc fact được domain xác nhận theo contract | Khác `publishedAt` và `processedAt` |
| `data.paymentId` | Payment transaction/attempt đã capture | Phải ổn định trong domain |
| `data.amountMinor` | Giá trị tính bằng đơn vị tiền nhỏ nhất theo convention | Không dùng `double` không kiểm soát |
| `data.currency` | Mã tiền tệ, ví dụ ISO 4217 | Cần định nghĩa cách xử lý scale và quy tắc làm tròn |

Nếu event là sự thật **toàn hệ thống** không thuộc tenant, đừng điền tenant giả chỉ để qua validator. Chọn một schema khác hoặc metadata scope tường minh.

### 4.2. Event ID khác business ID

Một order có thể phát nhiều events: `OrderPlaced`, `PaymentCaptured`, `OrderCancelled`. Vì vậy `orderId` **không phải** event ID. Một payment cũng có thể có capture và refund riêng; không dedupe mọi message theo `paymentId` nếu semantics khác nhau.

Nếu consumer chỉ chống **redelivery**, khóa thường là `(source,eventId)` hoặc `(subscriberId,source,eventId)` theo hợp đồng. Nếu cần chống **double charge/double fulfillment**, bổ sung khóa business effect riêng theo invariant.

### 4.3. Time và timezone

Dùng `Instant`/ISO-8601 UTC hoặc format thời gian được thống nhất, chẳng hạn `2026-11-11T02:00:00Z`. Đừng lẫn:

- `occurredAt`: fact nghiệp vụ xảy ra.
- `committedAt`: DB transaction commit, nếu hệ thống có thông tin này.
- `publishedAt`: relay gửi message ra transport.
- `receivedAt`: consumer nhận.
- `processedAt`: consumer hoàn tất.

Nếu producer tạo `occurredAt` trước commit, cần ghi rõ semantics ấy; **không** khẳng định nó là commit timestamp.

## 5. Thiết kế payload có thể phát triển độc lập

Một contract tốt không phụ thuộc vào Java types nội bộ. Ví dụ:

```java
// Domain model nội bộ — có thể thay đổi theo refactoring.
record PaymentCapturedDomain(
        UUID eventId,
        String tenantId,
        String paymentId,
        String orderId,
        long amountMinor,
        String currency,
        Instant occurredAt,
        String correlationId) {}

// Integration data công khai — giữ schema ổn định.
record PaymentCapturedV1(
        String paymentId,
        String orderId,
        long amountMinor,
        String currency) {}
```

Đây là các khai báo **minh họa**, cần import `UUID` và `Instant`. Ví dụ chạy đầy đủ ở phần 11 có toàn bộ imports.

Lưu ý:

1. **Chỉ dữ liệu cần thiết:** consumer có cần email, full name, địa chỉ giao hàng hoặc raw payment response để biết capture thành công không? Nếu không, loại bỏ.
2. **Định danh ổn định:** ID opaque thường ít phụ thuộc domain model hơn username, email hoặc internal DB object graph.
3. **Không gửi secrets:** access token, refresh token, credentials, webhook signature secret, private key và session state không được đưa vào event.
4. **Tiền tệ:** dùng integer minor units/decimal theo convention rõ; không thay thầm nghĩa `amountMinor` từ đồng sang xu.
5. **Null/optional:** trường thiếu và `null` có cùng ý nghĩa không? Không để consumer tự đoán.
6. **Collections:** thứ tự phần tử có ý nghĩa không? Có thể rỗng không? Giới hạn kích thước bao nhiêu?
7. **Enum:** consumer phải làm gì khi producer bổ sung một giá trị chưa biết?
8. **Timestamp:** độ chính xác và timezone phải thống nhất.
9. **ID privacy:** customerId/tenantId có thể liên kết cá nhân/doanh nghiệp; không mặc nhiên “anonymous”.

Cần định nghĩa giới hạn message size và schema validation trước khi vào consumer. Một event vô tình chứa base64 file hay toàn bộ entity graph có thể khiến broker/consumer thất bại và tạo rủi ro lộ dữ liệu.

## 6. Contract schema: JSON Schema ví dụ

Một schema đơn giản theo **JSON Schema Draft 2020-12** cho contract ở phần 4:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.invalid/schemas/payment-captured-v1.json",
  "title": "PaymentCapturedV1",
  "type": "object",
  "required": [
    "eventId",
    "eventType",
    "schemaVersion",
    "source",
    "tenantId",
    "aggregateId",
    "correlationId",
    "occurredAt",
    "data"
  ],
  "properties": {
    "eventId": { "type": "string", "format": "uuid" },
    "eventType": { "const": "payment.captured" },
    "schemaVersion": { "const": 1 },
    "source": { "type": "string", "minLength": 1 },
    "tenantId": { "type": "string", "minLength": 1 },
    "aggregateId": { "type": "string", "minLength": 1 },
    "correlationId": { "type": "string", "minLength": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": [
        "paymentId",
        "orderId",
        "amountMinor",
        "currency"
      ],
      "properties": {
        "paymentId": { "type": "string", "minLength": 1 },
        "orderId": { "type": "string", "minLength": 1 },
        "amountMinor": { "type": "integer", "minimum": 1 },
        "currency": { "type": "string", "pattern": "^[A-Z]{3}$" }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

Địa chỉ `example.invalid` là placeholder để minh họa cách tổ chức schema registry, **không phải URL schema đang hoạt động**. Khi triển khai, thay bằng schema ID/URI có quản trị thực tế.

**Các lưu ý về JSON Schema:**

- `format` như `uuid` và `date-time` có thể chỉ là annotation tùy validator/vocabulary; kiểm tra thư viện validator có bật format-assertion không. Đừng cho rằng mọi validator đều từ chối UUID sai.
- `additionalProperties:false` giúp producer xác định tập field được phép ở bản V1, **nhưng** consumer dùng schema này quá cứng có thể từ chối một optional field mới trong tương lai. Nếu chính sách cho phép additive evolution, consumer nên có cơ chế tolerant reader/compatibility validation phù hợp, hoặc tạo schema version rõ.
- JSON number không tự bảo đảm chính xác `long` ở mọi ngôn ngữ. JavaScript Number không biểu diễn chính xác mọi 64-bit integer; quy định giới hạn giá trị hoặc dùng decimal string khi cần.
- Một field `currency` đúng regex vẫn có thể không phải mã tiền hợp lệ; cần kiểm tra danh mục/currency semantics trong hệ thống.
- Schema chỉ kiểm tra **hình dạng**; không chứng minh tiền thật đã capture, actor có quyền hay tenant đúng.

### Contract documentation cần hơn schema

Một JSON Schema đúng vẫn không nói:

- `PaymentCaptured` là provider capture success hay chỉ provider accepted request?
- Một payment có thể capture nhiều lần/partial capture không?
- Sau chargeback/refund consumer cần làm gì?
- Có bảo đảm ordering theo paymentId/orderId không?
- Producer chỉ phát khi commit thành công hay khi nhận response?
- Consumer có được gọi API ngược lại về Billing ngay trong listener không?

Mỗi event type cần **semantic specification** kèm schema kỹ thuật.

## 7. CloudEvents: chuẩn hóa envelope, không thay business contract

**CloudEvents 1.0** là một lựa chọn tiêu chuẩn cho event envelope. Các attribute **bắt buộc** là:

- `specversion`, ví dụ `"1.0"`.
- `id`.
- `source`.
- `type`.

Các attribute như `time`, `subject` và `datacontenttype` là tùy chọn theo đặc tả; `data` chứa business payload khi có.

Ví dụ **CloudEvents dạng structured JSON**:

```json
{
  "specversion": "1.0",
  "id": "6f9b27d3-160b-4ff2-a0a8-b58c3ff0ec31",
  "source": "/services/billing",
  "type": "com.example.billing.payment.captured.v1",
  "subject": "payments/P-900",
  "time": "2026-11-11T02:00:00Z",
  "datacontenttype": "application/json",
  "tenantid": "tenant-blue",
  "correlationid": "checkout-913",
  "data": {
    "paymentId": "P-900",
    "orderId": "O-100",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
```

Đây là ví dụ do ứng dụng tự chọn naming cho CloudEvents extension attributes `tenantid` và `correlationid`. CloudEvents **không tự định nghĩa** business meaning của hai extension này.

**Phân biệt rõ hai loại version:**

- `specversion="1.0"`: version của **CloudEvents specification**.
- `type="...captured.v1"` hoặc một schema ID/version do team quản trị: version của **business event contract**.

Không đặt `specversion="2"` chỉ vì team có `PaymentCapturedV2`. CloudEvents chuẩn hóa lớp envelope/transport; nó không tự bảo đảm compatible payload, ordering, retry hoặc authorization.

Một ứng dụng có thể dùng custom envelope ở phần 4 **hoặc** CloudEvents. Đừng lắp nửa envelope riêng với nửa CloudEvents rồi khẳng định format phù hợp đặc tả.

### Khi dùng Kafka, RabbitMQ, HTTP hay CloudEvents

| Lựa chọn | Contract cần xác định |
| --- | --- |
| Kafka/Pulsar | Topic name, key/partition, schema registry, consumer group, retry/DLQ, retention |
| RabbitMQ/AMQP | Exchange/routing key, queue binding, publisher confirm, acknowledgement, dead-letter |
| HTTP webhook | URL, authentication/signature, retry response codes, timeout, replay protection, event ID |
| CloudEvents | `specversion/id/source/type` và binding phù hợp transport |
| Custom JSON event bus | Envelope/schema/version/validation tương ứng |
| Batch export | Watermark, snapshot/replay semantics, event ordering và idempotency |

Không có một transport nào tự biến event thành contract bền vững. **Contract là lời hứa về semantics và xử lý**, còn transport là cách chuyển thông điệp.

## 8. Quản lý version và compatibility

Một thay đổi schema cần được đánh giá theo consumer đang hoạt động, không chỉ xem JSON mới “có hợp lệ” hay không.

| Thay đổi | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Thêm field optional có default/consumer bỏ qua unknown | Thường thấp nếu reader tolerant | Test backward/forward compatibility |
| Thêm required field | Consumer/old messages có thể thiếu | Contract mới hoặc migration/default rõ |
| Đổi tên `paymentId` | Consumer cũ không nhận field | Dual-read/dual-write tạm thời hoặc version mới |
| Đổi `amountMinor` từ number sang string | Parse lỗi hoặc sai kiểu | Version mới và migration |
| Đổi đơn vị từ minor sang major | Sai số tiền dù schema vẫn `number` | **Thay đổi semantics nguy hiểm**; contract/version riêng |
| Đổi fact từ “captured” thành “authorized” | Consumer có thể fulfillment sai | Tên event/contract mới; không giữ tên cũ |
| Thêm enum value | Consumer dùng exhaustive switch có thể fail | Unknown fallback hoặc version mới |
| Loại bỏ field được consumer dùng | Downstream break | Deprecation và migration |
| Sửa cách tạo eventId khi retry | Dedupe mất tác dụng | Giữ identity semantics ổn định |
| Đổi meaning của tenantId | Có thể rò dữ liệu/sai routing | Explicit migration, security review |

### Backward và forward compatibility

- **Backward compatible:** consumer/version mới có thể đọc messages cũ theo quy tắc triển khai.
- **Forward compatible:** consumer cũ vẫn đọc được messages mới, ví dụ bỏ qua field mới nếu được cho phép.
- **Full compatible:** đạt cả hai trong phạm vi version/schema được hỗ trợ.

Các thuật ngữ có thể được schema registry định nghĩa thêm theo modes. Cần nêu **ai đọc ai** và testing matrix, không chỉ dán nhãn “compatible”.

**Schema compatibility khác semantic compatibility.** Đổi nghĩa `isPaid` từ “capture thành công” sang “authorization được chấp thuận” có thể không đổi kiểu dữ liệu, nhưng phá vỡ consumer nặng hơn cả thay tên field.

### Quy trình đổi contract thực tế

1. Ghi RFC/ADR về semantics và tập consumer.
2. Kiểm kê version đang sản xuất/tiêu thụ và log usage.
3. Ưu tiên additive change thật sự tương thích; thêm field optional khi hợp lý.
4. Viết producer schema tests và consumer contract tests cho dữ liệu cũ/mới.
5. Triển khai consumer có thể đọc cả định dạng cũ và mới trước khi producer chuyển.
6. Với breaking change, phát contract V2 cạnh V1 trong cửa sổ migration nếu kiến trúc cho phép.
7. Theo dõi consumer acknowledgements và production usage, không tắt V1 chỉ vì code producer đã đổi.
8. Ngừng phát V1 theo mốc cam kết và điều kiện đã thống nhất; document replay/backfill.
9. Giữ historical schema/decoder cho messages có thể được replay.
10. Review bảo mật/PII khi schema mới bổ sung trường.

Không nên hardcode consumer đọc “field đầu tiên” hoặc class name package cụ thể của producer. Dùng schema và semantic contract ổn định.

## 9. Contract owner, discoverability và tài liệu tích hợp

Mỗi public event type nên có metadata quản trị:

```text
Event:          payment.captured
Owner:          Payments/Billing team
Version:        v1
Source:         /services/billing
Audience:       Fulfillment, Finance, Analytics
Truth condition: provider confirmed capture
Transport:      billing.events topic (illustrative)
Key:            paymentId (illustrative)
Retention:      per agreed policy
PII class:      internal, no raw card credentials
Duplicate:      possible; dedupe by source+eventId
Ordering:       only per configured partition/key, if guaranteed
Support:        on-call team and escalation policy
Deprecation:    documented migration window
Schema:         registry URI/version
```

Các giá trị trên chỉ là **contract template minh họa**, không phải tên topic, retention hay SLA của một hệ thống cụ thể.

Tài liệu nên có:

- Một ví dụ message **hợp lệ**.
- Ví dụ fields optional và trường hợp không có giá trị.
- Tối thiểu một **negative example** (ví dụ pending payment **không** phát captured).
- Link schema, owner, changelog, topic/queue, ACL/credentials workflow.
- Event identity, timestamp, key ordering, TTL/replay, retry/DLQ.
- Error classification và side effects consumer có/không được phép thực hiện.
- Quy tắc nhạy cảm dữ liệu và vận hành môi trường dev/staging/prod.
- Tần suất/volume dự kiến, giới hạn payload size, SLA/latency nếu có.

Một API portal, AsyncAPI document hoặc schema registry có thể giúp discover contract, nhưng **cần duy trì bằng code review và CI** để tránh spec và producer drift.

## 10. Độ tin cậy: local publish không bằng remote delivery

Spring core `ApplicationEventPublisher` không phải broker. Mặc định listener chạy đồng bộ trong context và publication không được lưu bền vững. Nếu gọi một webhook trực tiếp trong transaction:

```java
@Transactional
public void markPaymentCaptured(...) {
    repository.markPaid(...);
    publisher.publishEvent(new PaymentCapturedDomain(...));
}
```

Giả sử listener bên trong thực hiện `httpClient.post(...)` đến hệ thống khác. Có những failure windows:

- Request đến hệ thống khác **trước commit**, sau đó transaction local rollback → bên ngoài đã xử lý fact chưa tồn tại bền vững.
- DB commit thành công nhưng process crash **trước khi gửi** → bên ngoài không nhận được.
- Remote xử lý xong nhưng response timeout → producer không biết đã thành công và retry có thể gây duplicate.
- Listener ném exception → kết quả transaction phụ thuộc sync/async, exception handling và transaction manager.
- API đích tạm down → application request bị chặn lâu nếu coupling đồng bộ.

Vì vậy, với event cần phát đáng tin cậy, thường chọn **transactional outbox** hoặc framework/registry có bảo đảm tương đương được cấu hình và kiểm chứng.

### 10.1. Transactional outbox: cùng transaction với state change

```text
Billing service
   |
   +-- BEGIN DB transaction
   |     |
   |     +-- UPDATE payment_orders SET state='PAID'
   |     |
   |     +-- INSERT outbox(eventId, contract JSON, PENDING)
   |
   +-- COMMIT
         |
         v
   Outbox relay (polling hoặc transaction log tailing)
         |
         +-- publish tới broker/webhook
         +-- thấy ACK phù hợp
         +-- mark outbox SENT
         |
         v
   Consumer nhận integration event
         |
         +-- validate source/schema/authorization
         +-- dedupe event
         +-- apply side effect safely
```

Trong mô hình trên, **DB update và outbox insert** phải thành công hoặc rollback cùng nhau. Relay chạy sau commit và có thể retry message chưa được xác nhận.

Outbox **không bảo đảm mỗi message chỉ được phát đúng một lần**. Relay có thể publish thành công rồi crash trước khi đánh dấu SENT, dẫn tới gửi lại khi restart. Vì vậy consumer idempotency vẫn bắt buộc với side effect quan trọng.

### 10.2. Vì sao AFTER_COMMIT không đủ cho atomic outbox insert?

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp callback thực hiện sau commit thành công. Tuy nhiên nếu ứng dụng **chỉ bắt đầu INSERT outbox trong callback sau commit**, outbox insert không còn cùng transaction đã cập nhật business state. Crash giữa commit và callback có thể mất event.

**Với ví dụ ở phần 11, outbox adapter dùng `@EventListener` đồng bộ** để insert outbox **ngay trong transaction đang mở**. Đây là quyết định có chủ đích, không có nghĩa mọi side effect nên xảy ra trước commit.

Nếu dùng Spring Modulith Event Publication Registry hoặc externalization, hãy nắm rõ **phiên bản và transaction/retry semantics** của các module ấy thay vì tự giả định `@TransactionalEventListener` bằng outbox.

## 11. Ví dụ chạy được: domain event → integration contract V1 → transactional outbox

Dự án này dùng:

- Java **17+** và Maven.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`).
- H2 **2.3.232** trong bộ nhớ.
- Jackson Databind **2.17.2** để serialize record thành JSON.

**Mục tiêu minh họa:** một payment capture đã được xác minh bởi nguồn có thẩm quyền làm thay đổi state trong local database; cùng transaction, event adapter chuyển domain event thành **contract V1** và ghi JSON vào outbox. Một lần xác nhận lại cho cùng order bị chặn theo invariant đơn giản của demo.

**Giới hạn rõ ràng:** demo không tích hợp payment provider thật, không publish ra Kafka/RabbitMQ, không có relay, không có HTTP authentication hay schema registry. Nó chỉ chứng minh **phần atomic write của outbox** và cách tách domain type khỏi contract công khai.

### 11.1. Cấu trúc thư mục

```text
integration-event-contract/
├── pom.xml
└── src/main/java/demo/IntegrationContractDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>integration-event-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.IntegrationContractDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/IntegrationContractDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import javax.sql.DataSource;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class IntegrationContractDemo {

    // Event nội bộ thuộc domain Payments.
    public record PaymentCapturedDomain(
            UUID eventId,
            String tenantId,
            String orderId,
            String paymentId,
            long amountMinor,
            String currency,
            Instant occurredAt,
            String correlationId) {
    }

    // Phần data thuộc public contract V1.
    public record PaymentCapturedV1(
            String paymentId,
            String orderId,
            long amountMinor,
            String currency) {
    }

    // Custom envelope (KHÔNG phải CloudEvents).
    public record IntegrationEventV1(
            String eventId,
            String eventType,
            int schemaVersion,
            String source,
            String tenantId,
            String aggregateId,
            String correlationId,
            String occurredAt,
            PaymentCapturedV1 data) {
    }

    // Không final: @Transactional cần proxy method.
    public static class PaymentService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public PaymentService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void recordCapturedPayment(
                String tenantId,
                String orderId,
                String paymentId,
                long amountMinor,
                String currency,
                String correlationId) {

            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(paymentId, "paymentId");
            Objects.requireNonNull(currency, "currency");
            Objects.requireNonNull(correlationId, "correlationId");

            if (amountMinor <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int changed = jdbc.update(
                    "UPDATE payment_orders SET state = 'PAID' "
                    + "WHERE order_id = ? AND tenant_id = ? "
                    + "AND state = 'UNPAID'",
                    orderId, tenantId);

            if (changed != 1) {
                throw new IllegalStateException(
                        "not eligible for capture confirmation");
            }

            // Trong demo, chỉ gọi sau khi provider đã được xác minh.
            publisher.publishEvent(new PaymentCapturedDomain(
                    UUID.randomUUID(),
                    tenantId,
                    orderId,
                    paymentId,
                    amountMinor,
                    currency,
                    Instant.now(),
                    correlationId));
        }
    }

    public static class OutboxAdapter {
        private final JdbcTemplate jdbc;
        private final ObjectMapper mapper;

        public OutboxAdapter(JdbcTemplate jdbc, ObjectMapper mapper) {
            this.jdbc = jdbc;
            this.mapper = mapper;
        }

        @EventListener
        public void on(PaymentCapturedDomain domain) {
            PaymentCapturedV1 data = new PaymentCapturedV1(
                    domain.paymentId(),
                    domain.orderId(),
                    domain.amountMinor(),
                    domain.currency());

            IntegrationEventV1 contract = new IntegrationEventV1(
                    domain.eventId().toString(),
                    "payment.captured",
                    1,
                    "/services/billing",
                    domain.tenantId(),
                    domain.orderId(),
                    domain.correlationId(),
                    domain.occurredAt().toString(),
                    data);

            final String json;
            try {
                json = mapper.writeValueAsString(contract);
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException(
                        "Unable to serialize contract", ex);
            }

            // Đây là @EventListener đồng bộ, trong transaction gốc.
            jdbc.update(
                    "INSERT INTO outbox "
                    + "(event_id, event_type, schema_version, "
                    + "tenant_id, payload_json, dispatch_state) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                    contract.eventId(),
                    contract.eventType(),
                    contract.schemaVersion(),
                    contract.tenantId(),
                    json,
                    "PENDING");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:integration_contract;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        PaymentService paymentService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new PaymentService(jdbc, publisher);
        }

        @Bean
        OutboxAdapter outboxAdapter(
                JdbcTemplate jdbc,
                ObjectMapper mapper) {
            return new OutboxAdapter(jdbc, mapper);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            ObjectMapper mapper = context.getBean(ObjectMapper.class);

            jdbc.execute(
                    "CREATE TABLE payment_orders ("
                    + "order_id VARCHAR(40) PRIMARY KEY, "
                    + "tenant_id VARCHAR(40) NOT NULL, "
                    + "state VARCHAR(20) NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE outbox ("
                    + "event_id VARCHAR(36) PRIMARY KEY, "
                    + "event_type VARCHAR(80) NOT NULL, "
                    + "schema_version INT NOT NULL, "
                    + "tenant_id VARCHAR(40) NOT NULL, "
                    + "payload_json CLOB NOT NULL, "
                    + "dispatch_state VARCHAR(20) NOT NULL)");

            jdbc.update(
                    "INSERT INTO payment_orders "
                    + "(order_id, tenant_id, state) VALUES (?, ?, ?)",
                    "O-100", "tenant-blue", "UNPAID");

            PaymentService service =
                    context.getBean(PaymentService.class);

            service.recordCapturedPayment(
                    "tenant-blue", "O-100", "P-900",
                    125000L, "VND", "checkout-913");

            // Một lần xác nhận lại cho cùng order không tạo event mới.
            boolean secondAttemptBlocked = false;
            try {
                service.recordCapturedPayment(
                        "tenant-blue", "O-100", "P-900",
                        125000L, "VND", "checkout-913");
            } catch (IllegalStateException expected) {
                secondAttemptBlocked = true;
            }

            String state = jdbc.queryForObject(
                    "SELECT state FROM payment_orders "
                    + "WHERE order_id = ?",
                    String.class, "O-100");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox",
                    Integer.class);

            String json = jdbc.queryForObject(
                    "SELECT payload_json FROM outbox",
                    String.class);

            JsonNode contract = mapper.readTree(json);

            System.out.println("ORDER_STATE=" + state);
            System.out.println("OUTBOX_ROWS=" + count);
            System.out.println(
                    "EVENT_TYPE=" + contract.path("eventType").asText());
            System.out.println(
                    "SCHEMA_VERSION="
                    + contract.path("schemaVersion").asInt());
            System.out.println(
                    "TENANT=" + contract.path("tenantId").asText());
            System.out.println(
                    "PAYMENT="
                    + contract.path("data").path("paymentId").asText());
            System.out.println(
                    "AMOUNT_MINOR="
                    + contract.path("data").path("amountMinor").asLong());
            System.out.println(
                    "SECOND_ATTEMPT_BLOCKED=" + secondAttemptBlocked);
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in (không tính log khởi động phụ thuộc môi trường):

```text
ORDER_STATE=PAID
OUTBOX_ROWS=1
EVENT_TYPE=payment.captured
SCHEMA_VERSION=1
TENANT=tenant-blue
PAYMENT=P-900
AMOUNT_MINOR=125000
SECOND_ATTEMPT_BLOCKED=true
```

### 11.2. Tại sao bản ghi outbox nhất quán với business state?

1. `AnnotationConfigApplicationContext` tạo các beans; `@EnableTransactionManagement` kích hoạt transaction proxy cho `PaymentService`.
2. `recordCapturedPayment(...)` được gọi **thông qua Spring bean**, không self-invocation. Transaction manager mở local JDBC transaction trên DataSource.
3. `UPDATE payment_orders` chỉ đổi state từ `UNPAID` sang `PAID` khi tenant/order khớp. Nếu không có row phù hợp, method ném exception và không publish event.
4. Khi update thành công, service tạo `PaymentCapturedDomain` và gọi Spring `publishEvent(...)`. `SimpleApplicationEventMulticaster` mặc định gọi `@EventListener` đồng bộ trên cùng thread.
5. `OutboxAdapter.on(...)` chuyển domain payload sang `IntegrationEventV1` và INSERT JSON vào bảng outbox **trong transaction của service đang mở**.
6. Nếu INSERT fail hoặc serializer ném runtime exception, transaction của service rollback cả update. Nếu transaction commit, business state và outbox row xuất hiện cùng nhau.
7. Lần gọi lại cho order đã `PAID` không khớp điều kiện update nên không phát thêm fact mới. Đây là quy tắc **demo**: một order chỉ xác nhận một capture. Domain có partial/multiple capture cần invariant/key khác.
8. Test đọc lại H2 và in fields của JSON contract. Không in UUID hoặc timestamp runtime để stdout ổn định.

**Điều chưa có trong demo:** gửi message tới broker, xác nhận ACK, retry, DLQ, xử lý duplicate ở consumer, schema validation ở CI và security authentication. Những phần này cần bổ sung trong hệ thống thực theo các mục tiếp theo.

### 11.3. Vì sao không dùng @TransactionalEventListener(AFTER_COMMIT) ở đây?

Mục tiêu là làm **atomic insert outbox** trong transaction đã thay đổi `payment_orders`. Nếu đổi `@EventListener` thành listener chỉ chạy AFTER_COMMIT rồi mới insert outbox, không thể tuyên bố cả hai UPDATE/INSERT nằm trong **cùng transaction** nữa.

Nếu muốn một adapter ghi outbox qua thread khác, cũng phải đánh giá lại context transaction: ThreadLocal của JDBC transaction không mặc nhiên đi qua executor. Một async listener **không** phù hợp khi yêu cầu ghi outbox cùng transaction ở mẫu này.

## 12. Relay sang broker và consumer idempotent

Sau khi outbox đã có row `PENDING`, một worker/relay riêng cần đọc, gửi, xác nhận và đánh dấu hoàn tất. Pseudocode:

```text
repeat:
  rows = claimPendingOutboxRows(limit, lease)
  for row in rows:
      try:
          broker.publish(
              topic="billing.events",
              key=row.aggregateIdOrPaymentId,
              payload=row.payloadJson,
              eventId=row.eventId
          )
          waitForBrokerAcknowledgement()
          markOutboxSent(row.eventId)
      catch retryableError:
          recordAttemptAndBackoff(row.eventId)
      catch terminalError:
          quarantineOrDeadLetter(row.eventId)
```

Đây là **thuật toán minh họa**, không phải API có sẵn của Spring core. Production cần thiết kế tranh chấp nhiều relay workers, lease/locking, retry policy, timeouts và shutdown recovery.

**Cửa sổ duplicate quan trọng:**

```text
Outbox row E-1 committed
  |
  v
Relay publishes E-1 -> broker ACK
  |
  +-- PROCESS CRASH trước mark SENT
         |
         v
Relay restart -> publish lại E-1
         |
         v
Consumer có thể nhận E-1 lần thứ hai
```

Do đó consumer phải idempotent. Ví dụ bảng SQL:

```sql
CREATE TABLE processed_messages (
    subscriber_id VARCHAR(80) NOT NULL,
    source VARCHAR(100) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, source, event_id)
);
```

Trong transaction của consumer:

1. Xác minh nguồn, tenant và schema.
2. Insert processed marker bằng unique constraint.
3. Nếu duplicate key đúng constraint, bỏ qua side effect đã được commit trước.
4. Nếu insert thành công, thực hiện cập nhật DB consumer **trong cùng transaction**.
5. Commit marker và effect; sau đó ACK theo transport semantics.
6. Nếu rollback, marker cũng phải rollback để retry có cơ hội xử lý.

Không dùng chỉ `Set<UUID>` trong bộ nhớ cho durable idempotency nhiều replicas. Với tác dụng ở external payment/email/shipment API, local DB transaction không atomic với dịch vụ ngoài; dùng stable idempotency key tại đích, reconciliation hoặc orchestration phù hợp.

### Event-level dedupe và business-level dedupe

Hai delivery cùng `eventId` là một occurrence được giao lại. Hai event IDs khác nhau có thể vẫn tạo một business effect trùng (ví dụ cùng order tạo hai fulfillment không hợp lệ). Vì vậy có thể cần **hai khóa**:

- `(subscriberId,source,eventId)`: chống redelivery của một event.
- `fulfillment:orderId` hoặc một khóa nghiệp vụ theo invariant cụ thể: chống tạo hai tác dụng ngoài ý muốn.

Không dùng `correlationId` làm event dedupe key: một checkout có thể tạo nhiều events cùng correlation.

## 13. Ordering và replay: không có thứ tự toàn cục mặc định

Các consumer không nên giả định mọi event ở mọi service sẽ tới đúng thứ tự wall-clock. Các yếu tố ảnh hưởng:

- Nhiều producers, threads hoặc instances.
- Broker partitioning và key.
- Retry/dead-letter/redrive.
- Outbox relays chạy song song.
- Consumer group concurrency.
- Network và clock skew.

Nếu state projection yêu cầu thứ tự của **một aggregate**, có thể thêm `aggregateVersion`/sequence và định tuyến các events cùng aggregate vào cùng partition/key khi transport hỗ trợ. Ví dụ:

```text
Order O-100:
  PaymentAuthorized  aggregateVersion=3
  PaymentCaptured    aggregateVersion=4
  PaymentRefunded    aggregateVersion=5
```

Version phải do authoritative store tạo theo cùng quy tắc giao dịch; không lấy một timestamp ngẫu nhiên làm sequence. Consumer có thể từ chối một version cũ hoặc chờ gap theo policy. Không suy từ `aggregateVersion` rằng một broker luôn bảo toàn order nếu key/consumer configuration sai.

### Replay contract cần nói rõ

Replaying events lịch sử có thể nhằm rebuild projection, khôi phục consumer mới hoặc điều tra. Khi replay:

- Giữ identity/provenance của occurrence gốc.
- Đảm bảo consumer biết mình đang replay hoặc có policy idempotent.
- Tránh gọi lại external payment API, gửi email hay shipment side effects không được phép.
- Giữ schema/decoder cũ trong thời gian retention/replay.
- Phân biệt `occurredAt` và thời điểm replay.
- Không tạo eventId mới chỉ vì chuyển lại cùng fact.

## 14. Bảo mật khi phát event cho hệ thống khác

Event contract là một ranh giới dữ liệu. Bên ngoài có thể có quyền, vòng đời và lưu trữ khác với producer. Các biện pháp trọng yếu:

**Producer authentication và transport security.** Broker dùng ACL/service identity, kết nối TLS, và kiểm soát topic. HTTP webhook cần xác minh endpoint, chữ ký/MAC hoặc cơ chế authentication phù hợp. Không tin một trường `source` trong JSON là bằng chứng producer thật.

**Tenant isolation.** `tenantId` phải được xác định từ nguồn nghiệp vụ đã được kiểm tra quyền. Phía nhận không cho event tự chọn datasource/index tenant chỉ bằng một chuỗi không được xác minh. Quy định consumer nào được phép nhận tenant nào.

**PII minimization.** Không gửi raw customer profile, tokens, cookies, card PAN, password hoặc internal security context trừ khi contract đã được phê duyệt và bảo vệ rất đặc thù. Event payload và outbox là nơi **lưu dữ liệu**, không chỉ là đường truyền tạm thời.

**Retention và erasure.** Broker, outbox, DLQ, replay storage, log và backups có retention khác nhau. Cần chính sách pháp lý/hợp đồng theo loại dữ liệu; không giữ PII vô thời hạn vì tiện replay.

**Logging/tracing.** Dùng eventId, eventType, outcome và correlation ID an toàn; không dump raw JSON. Một opaque actor/tenant ID vẫn có thể liên kết đến người/tổ chức. Không đưa event ID/customer ID vào metric labels high-cardinality.

**Webhook security.** Kiểm tra chữ ký trên raw body theo protocol, giới hạn thời gian replay theo timestamp/nonce nếu quy định, và dedupe event. Từng lần retry của cùng occurrence phải giữ identity theo contract. Không đặt secret signing key vào payload.

**Validation và resource limits.** Check schema, size, UTF-8, nesting depth, required fields, message authentication và rate limits. Một payload hợp schema có thể vẫn có amount không hợp lệ hoặc tenant không được phép.

### Không “mượn” quyền của actor lịch sử

Event ghi `actor=user-42` chỉ mô tả ai đã thực hiện fact ở producer. Consumer chạy sau có thể không được phép hành động thay user-42, nhất là khi quyền đã bị thu hồi. Consumer cần chính sách authorization/trust riêng; event metadata không phải access token.

## 15. Contract testing giữa producer và consumer

**Producer contract test** kiểm tra điều producer phát thực tế phù hợp schema/semantics đã công bố.

**Consumer contract test** kiểm tra consumer đọc và phản ứng đúng với ví dụ/hợp đồng đã hỗ trợ, kể cả optional fields và một số failure paths.

Một ma trận thực dụng:

| Tình huống | Điều cần assert |
| --- | --- |
| Captured hợp lệ | Event type, version, source, ID, tenant và dữ liệu capture đúng |
| Request capture còn pending | **Không** phát `payment.captured` |
| Transaction rollback | Không có outbox row committed |
| Outbox serialization lỗi | Business state rollback cùng outbox write |
| Bổ sung field optional | Consumer cũ vẫn đọc theo compatibility policy |
| Thiếu required field | Producer validator/test fail; consumer reject/quarantine |
| Unknown enum value | Consumer xử lý fallback hoặc reject có kiểm soát |
| Amount đổi đơn vị | Test semantic fail, không chỉ schema type |
| EventId trùng (redelivery) | Consumer effect chỉ thực thi một lần |
| Hai events cùng correlation | Không bị dedupe nhầm |
| Tenant không được phép | Consumer không truy cập dữ liệu tenant khác |
| Message giả mạo source | Reject trước khi dùng tenant routing |
| Out-of-order aggregate version | Không ghi đè trạng thái mới bằng event cũ |
| Poison event/invalid JSON | Retry/DLQ policy, không retry vô hạn |
| Relay publish xong rồi crash | Message resend có cùng eventId |
| Schema V1 replay sau deploy V2 | Decoder/consumer vẫn hiểu theo support matrix |
| Provider capture thành công nhưng webhook timeout | Producer reconcile/giữ idempotency và phát fact đúng một lần |
| Audit/log | Không lộ tokens/PII trong lỗi hoặc trace |

### 15.1. Unit test mapper độc lập

Nếu adapter mapping là pure function, kiểm tra các field dễ hơn khi không cần broker:

```java
// Snippet JUnit minh họa, không thuộc project Maven phần 11.
PaymentCapturedV1 data =
        new PaymentCapturedV1("P-900", "O-100", 125000L, "VND");

assertEquals("P-900", data.paymentId());
assertEquals(125000L, data.amountMinor());
assertEquals("VND", data.currency());
```

Snippet cần JUnit Jupiter assertions và kiểu record đã khai báo. Tốt hơn nữa, test rằng Mapper **không** chứa thông tin nhạy cảm không được công bố từ domain event.

### 15.2. Contract fixture và golden JSON

Lưu mẫu JSON V1 vào test resources trong project thực (ở đây chỉ là khuyến nghị), sau đó:

- Parse bằng đúng consumer deserializer.
- Validate bằng đúng schema version.
- Assert field semantics.
- Test backwards/forwards compatibility ở các version support.
- Kiểm tra canonical encoding khi dùng signature.
- Đảm bảo unknown properties xử lý theo policy.
- Không so sánh chuỗi JSON raw nếu field order không phải contract.

Nếu đang ký webhook JSON, chữ ký thường phụ thuộc **raw bytes** theo quy định protocol; không deserialize rồi serialize lại và tự kỳ vọng signature vẫn hợp lệ.

### 15.3. Integration test DB transaction và outbox

Với ví dụ phần 11, các assertion đáng có:

```java
// Pseudocode JUnit với context/jdbc/service đã dựng.
service.recordCapturedPayment(...);
assertEquals("PAID", stateFromDatabase);
assertEquals(1L, countOutboxRows);
assertEquals("payment.captured", parsedEventType);
assertEquals(1, parsedSchemaVersion);
```

Đây là **pseudocode**, không phải Java runnable độc lập; các biến cần định nghĩa trong test. Một test quan trọng khác cố ý làm lỗi insert outbox (ví dụ unique violation) và assert state rollback `UNPAID` sau transaction. Cần test với đúng transaction manager/DB driver giống môi trường sản xuất nếu muốn kết luận về đặc tính đồng thời, locking hoặc isolation.

### 15.4. Consumer-driven contract testing

Khi producer có nhiều consumer, có thể dùng consumer-driven contract tests để thu thập expectation hợp lệ của consumer. Tuy nhiên consumer không được tự ý quyết định truth condition của producer. Contract owner phải duy trì semantics và giai đoạn migration; tool kiểm tra JSON shape không thay thế thỏa thuận nghiệp vụ.

## 16. Monitoring và vận hành contract

Nên có metrics cho:

- Outbox pending rows và tuổi bản ghi cũ nhất.
- Số lần relay publish, retry, failure, DLQ.
- Producer events theo eventType/version.
- Consumer accepted/processed/duplicate/rejected theo eventType/version.
- Schema validation errors và unknown contract versions.
- Consumer lag, processing latency và backlog.
- Tỷ lệ consumer sử dụng V1/V2 trước deprecation.

Đừng dùng mỗi `eventId` hay `customerId` làm metric tag. IDs có cardinality rất cao; dùng labels được chuẩn hóa và lưu chi tiết trong log/traces có kiểm soát.

Một ví dụ log an toàn:

```text
component=billing-outbox
eventType=payment.captured
schemaVersion=1
outcome=RETRY_SCHEDULED
errorCode=BROKER_UNAVAILABLE
```

Các trường có thể mở rộng bằng opaque eventId/correlation ID nếu policy cho phép. Đừng dump toàn bộ payment payload khi broker tạm lỗi.

### Quy trình ứng cứu khi consumer không đọc được V2

1. Xác nhận event type/schema ID/version và sample đã được sanitize.
2. Xác định consumer nào lỗi, từ deploy nào, message nào và schema registry mode nào.
3. Phân loại: parse/type, missing field, semantic change hay authentication/tenant rejection.
4. Tạm quarantine/retry có giới hạn; tránh loop vô hạn hoặc mất message.
5. Nếu breaking change, khôi phục V1 hoặc bật dual-publish/adapter theo kế hoạch đã duyệt.
6. Kiểm tra những side effects đã xảy ra để tránh duplicate khi replay.
7. Viết regression contract test trước khi rollout lại.
8. Cập nhật owner/changelog/support matrix và mốc deprecation.

## 17. Những anti-pattern cần tránh

1. **Gửi thẳng JPA entity qua broker.** Consumer phụ thuộc lazy fields, internal model và dữ liệu thừa.
2. **Tái sử dụng Java class của producer làm public contract bắt buộc.** Coupling vào package/deployment của service khác.
3. **Đặt event tên kỹ thuật `EntityUpdated` nhưng muốn consumer suy ra business fact.** Semantics không ổn định.
4. **Phát `PaymentCaptured` khi mới gửi command capture.** Nói sai sự thật.
5. **Đưa access token/credentials vào payload để consumer dùng lại.** Rò bí mật và sai trust boundary.
6. **Không có eventId ổn định hoặc tạo UUID mới mỗi retry gửi lại.** Dedupe thất bại.
7. **Đổi nghĩa field nhưng không đổi contract.** Có thể gây lỗi nghiệp vụ dù JSON vẫn parse.
8. **Chỉ kiểm tra JSON Schema mà bỏ qua truth condition.** Producer phát fact sai vẫn pass validator.
9. **Dùng `specversion` CloudEvents làm business schema version.** Trộn hai tiêu chuẩn khác nhau.
10. **Bắt mọi consumer update cùng một lúc.** Phá ưu thế independent deployment.
11. **Thêm required field vào V1 rồi gọi là additive.** Consumer cũ và lịch sử message có thể lỗi.
12. **Dùng strict unknown-field parser nhưng vẫn hứa forward compatibility.** Lời hứa và implementation mâu thuẫn.
13. **Không có schema owner, changelog, fixtures.** Consumer đoán field theo ví dụ log.
14. **Cho rằng `@EventListener` tự gửi ra Kafka/HTTP.** Spring core chỉ dispatch nội bộ.
15. **Gọi webhook trực tiếp bên trong DB transaction.** Có cửa sổ external side effect trước commit.
16. **Đặt INSERT outbox chỉ trong callback AFTER_COMMIT rồi tin là atomic với business state.** Sai ranh giới giao dịch.
17. **Tin rằng transactional outbox tạo exactly-once end-to-end.** Relay vẫn có thể resend.
18. **Dùng correlationId làm khóa dedupe.** Một workflow thường có nhiều facts.
19. **Giả định ordering toàn cục của broker.** Tùy key/partition/retry/concurrency.
20. **Không phân quyền DLQ/replay storage.** Payload nhạy cảm bị lưu ở nhiều nơi ngoài chính sách.
21. **Replay event cũ rồi gọi API thu tiền thêm lần nữa.** Side effect cần idempotency/business policy.
22. **Ghi raw event JSON vào log khi deserialization fail.** Rò dữ liệu ngay trên error path.
23. **Bỏ qua event validity ở consumer.** Một JSON có tenant ID không chứng minh nó đáng tin.
24. **Không giới hạn size/depth/retention.** Một message lớn có thể gây nghẽn hệ thống.
25. **Không hỗ trợ old schema khi replay.** Nâng version xong làm consumer mới không đọc lịch sử.
26. **Chuyển public format mà không có migration window.** Các consumer đang chạy bị gãy đột ngột.

## 18. Checklist thiết kế trước khi công bố event

### Semantics

- [ ] Event diễn đạt **sự thật đã xảy ra**, không phải command chưa thực hiện?
- [ ] Truth condition, owner và thời điểm xác nhận được tài liệu hóa?
- [ ] Không nhầm captured với authorized/settled/refunded?
- [ ] Multiplicity và business identity rõ ràng?

### Contract

- [ ] Public envelope có event ID, source, type và version cần thiết?
- [ ] Schema/payload có field required/optional, units và constraints?
- [ ] Không gửi domain entity/runtime object/secrets?
- [ ] Event ID ổn định khi resend một occurrence?
- [ ] Correlation, tenant, aggregate ID và occurredAt có semantics nhất quán?
- [ ] Nếu dùng CloudEvents, `specversion` đúng với specification, schema version riêng?

### Reliability

- [ ] Ghi state và outbox atomically hoặc có guarantee thay thế được kiểm chứng?
- [ ] Relay có ACK, retry/backoff, concurrency control và failure monitoring?
- [ ] Consumer idempotent khi redelivery và có business effect key nếu cần?
- [ ] Ordering scope và xử lý out-of-order được xác định?
- [ ] Replay/retention/DLQ không gọi lại side effect nguy hiểm?

### Governance và bảo mật

- [ ] Có owner, schema registry/AsyncAPI hoặc tài liệu duy trì bằng CI?
- [ ] Compatibility policy, changelog, migration và deprecation window rõ?
- [ ] Producer identity, broker/webhook auth và tenant isolation được xác minh?
- [ ] PII/retention/encryption/access logging đạt policy áp dụng?
- [ ] Có test contract ở producer, consumer, transaction/outbox và backward compatibility?

**Kết luận:** Khi một Spring domain event cần đến hệ thống khác, đừng xuất nguyên Java object hay chỉ “thêm một topic”. Hãy xây **integration event contract độc lập**, mô tả đúng fact đã xảy ra, schema có version, metadata có ý nghĩa và payload tối thiểu. Ghi business state và outbox trong cùng transaction nếu cần reliable publication, còn consumer phải xác minh nguồn, xử lý duplicate/replay và tương thích schema theo thỏa thuận. Hợp đồng tốt cho phép mỗi hệ thống phát triển riêng mà vẫn hiểu **cùng một sự thật nghiệp vụ**.

## Tài liệu tham khảo

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [CloudEvents Specification 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [JSON Schema — Draft 2020-12](https://json-schema.org/draft/2020-12)
- [AsyncAPI — Specification](https://www.asyncapi.com/docs/reference/specification/latest)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
