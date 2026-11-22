# Thay đổi hợp đồng khi bên sử dụng chưa thể nâng cấp đồng thời

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Bài tập và tình huống.  
> **Mục tiêu:** thiết kế cách thay đổi API, event, schema và shared contract khi producer và consumer được triển khai ở các thời điểm khác nhau; bảo đảm các phiên bản cũ/mới có thể cùng tồn tại trong một khoảng thời gian; áp dụng backward/forward compatibility, expand–migrate–contract, contract testing, deprecation, rollout và rollback có kiểm soát.

## 1. Tình huống: producer đã phát hành, consumer chưa thể nâng cấp

Một nền tảng có Order Service cung cấp API cho Payment, Shipping, Reporting và ứng dụng mobile. Nhóm Order muốn đổi response để bổ sung trạng thái mới, đổi tên một field và loại bỏ field cũ.

Order Service có thể deploy trong vài phút, nhưng các consumer có vòng đời khác nhau:

- Payment Service đang trong đợt release lớn và chưa thể nâng trong tuần này.
- Mobile app có người dùng giữ phiên bản cũ nhiều tháng.
- Đối tác vận chuyển chỉ phát hành tích hợp theo lịch hàng quý.
- Reporting chạy batch job và chỉ được cập nhật vào cửa sổ bảo trì.
- Một consumer nội bộ đang dùng generated SDK cũ.
- Message từ broker có thể nằm trong backlog và được xử lý sau khi producer đã deploy bản mới.

Nếu Order chỉ thay đổi contract rồi deploy, một số consumer có thể parse thất bại, hiểu sai trạng thái hoặc bỏ qua giao dịch. Nếu buộc mọi consumer nâng cùng lúc, tiến độ release bị khóa bởi team chậm nhất.

**Đây là bài toán tương thích phiên bản trong hệ phân tán:** producer và consumer không cùng thời điểm nâng cấp, nên hệ thống phải hỗ trợ một khoảng thời gian nhiều phiên bản cùng hoạt động.

Nguyên tắc quan trọng là thay đổi theo hướng mở rộng trước, chuyển consumer dần, chỉ loại bỏ contract cũ sau khi có bằng chứng không còn ai sử dụng.

## 2. Contract là gì?

Contract là thỏa thuận có thể kiểm chứng giữa bên cung cấp và bên sử dụng một capability. Nó không chỉ là cấu trúc JSON.

Một contract API có thể gồm:

- HTTP method, path và headers.
- Request/response schema.
- Status code và error model.
- Authentication, authorization và tenant context.
- Nullability, default values và enum semantics.
- Ordering, pagination và filtering.
- Idempotency và concurrency behavior.
- Timeout, rate limit và retry guidance.
- Version support và deprecation policy.

Một event contract còn gồm:

- Event name/type và schema.
- Event ID, aggregate ID và sequence.
- Thời điểm xảy ra và thời điểm phát.
- Ordering guarantee và partition key.
- Duplicate delivery semantics.
- Schema compatibility rules.
- Retention, replay và consumer expectations.

Một database contract giữa các ứng dụng có thể bao gồm schema, constraints, views, stored procedures và cách migration tương thích. Tuy nhiên, truy cập trực tiếp database của service khác thường là dấu hiệu ownership chưa rõ.

**Contract là cả syntax lẫn semantics.** Hai bên có thể parse cùng JSON nhưng vẫn bất đồng về ý nghĩa của trạng thái, đơn vị tiền hoặc thời điểm hiệu lực.

## 3. Producer, consumer và hướng tương thích

- **Producer/provider:** bên tạo API response, event hoặc dữ liệu.
- **Consumer/client:** bên gọi API hoặc đọc event.
- **Backward compatibility:** phiên bản mới của provider vẫn hỗ trợ consumer cũ theo contract đã cam kết.
- **Forward compatibility:** consumer cũ có thể xử lý dữ liệu được tạo bởi producer mới trong phạm vi đã thiết kế.
- **Source compatibility:** source code consumer có thể biên dịch với API library mới.
- **Binary compatibility:** bytecode đã biên dịch vẫn link và chạy với library mới.
- **Behavioral compatibility:** hành vi quan sát được vẫn đáp ứng kỳ vọng cũ.
- **Operational compatibility:** timeout, throughput, resource usage và deployment behavior vẫn trong giới hạn consumer có thể chịu.

Một thay đổi có thể backward-compatible về JSON nhưng không source-compatible với Java SDK, hoặc giữ nguyên schema nhưng thay semantics. Vì vậy phải xác định rõ contract layer đang nói tới.

## 4. Vì sao không thể deploy đồng thời?

Trong microservices, release cadence khác nhau vì:

- Team có lịch và quy trình phê duyệt riêng.
- Một số service cần regression test hoặc certification lâu.
- Mobile clients không thể được cập nhật tức thì.
- Partner systems nằm ngoài quyền kiểm soát.
- Batch consumers chỉ chạy theo lịch.
- Queue giữ event cũ qua nhiều phiên bản.
- Có nhiều region và deployment wave.
- Rollback có thể đưa consumer cũ trở lại sau khi producer mới đã deploy.

Do đó, hệ thống cần một **compatibility window**: khoảng thời gian mà contract cũ và mới cùng được hỗ trợ.

Compatibility window phải đủ dài để consumer nâng cấp, deploy, xử lý backlog, kiểm tra và có thể rollback. Không thể chỉ tính thời gian từ lúc merge đến lúc deploy.

## 5. Phân loại thay đổi: additive và breaking

Các thay đổi thường có mức rủi ro khác nhau.

| Thay đổi | Thường an toàn hơn khi | Rủi ro |
| --- | --- | --- |
| Thêm optional field | Consumer bỏ qua field chưa biết | Parser strict có thể fail |
| Thêm endpoint mới | Endpoint cũ vẫn hoạt động | Auth/routing/config mới |
| Thêm enum value | Consumer xử lý unknown value | Switch/parser có thể fail |
| Đổi tên field | Chỉ sau giai đoạn chuyển tiếp | Consumer cũ không tìm thấy field |
| Xóa field | Sau deprecation và adoption evidence | Consumer cũ mất dữ liệu |
| Đổi type | Có field mới và migration path | Parse hoặc semantic mismatch |
| Đổi units | Không đổi ngầm semantics cũ | Sai số hoặc sai nghiệp vụ |
| Đổi default | Có policy và consumer review | Hành vi thay đổi không nhìn thấy |
| Siết validation | Dữ liệu cũ vẫn hợp lệ hoặc đã migrate | Request trước đây hợp lệ bị từ chối |
| Đổi error code | Consumer cũ vẫn xử lý được | Retry/alert/business flow sai |
| Đổi ordering | Contract cho phép và consumer thích ứng | Race, out-of-order processing |
| Đổi authentication | Có overlap credentials/protocol | Outage diện rộng |

“Chỉ thêm field” không tự động an toàn nếu consumer dùng schema validation nghiêm ngặt hoặc generated code không cho phép unknown fields.

## 6. Backward compatibility trong API

Giả sử phiên bản cũ trả:

~~~json
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 150000
}
~~~

Phiên bản mới bổ sung field:

~~~json
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 150000,
  "currency": "VND",
  "version": 7
}
~~~

Nếu consumer cũ bỏ qua unknown fields, response mới có thể tương thích. Nhưng nếu consumer dùng JSON Schema với additionalProperties=false hoặc DTO parser strict, việc thêm field vẫn có thể làm hỏng.

Trước khi thêm field, kiểm tra:

- JSON parser settings của các consumer.
- OpenAPI/JSON Schema validation.
- Generated SDK behavior.
- API gateway transformations.
- Cache serialization.
- Signature/canonicalization nếu payload được ký.
- Contract tests với phiên bản consumer đang chạy.

Không dựa vào giả định rằng mọi JSON client đều tolerant.

## 7. Forward compatibility của consumer

Một consumer forward-compatible có thể nhận dữ liệu mới mà vẫn xử lý an toàn.

Ví dụ, khi đọc enum status, không nên mặc định mọi giá trị đều nằm trong tập đã biết nếu producer có quyền thêm giá trị.

~~~java
public enum OrderStatus {
    CREATED,
    PENDING,
    CONFIRMED,
    CANCELLED,
    UNKNOWN
}

public static OrderStatus parseStatus(String value) {
    try {
        return OrderStatus.valueOf(value);
    } catch (IllegalArgumentException | NullPointerException ex) {
        return OrderStatus.UNKNOWN;
    }
}
~~~

Đây là ví dụ đơn giản. Việc map giá trị lạ thành UNKNOWN chỉ an toàn nếu consumer có thể giữ nguyên raw value, ghi telemetry và không đưa ra quyết định nghiệp vụ nguy hiểm.

Nếu consumer nhận một trạng thái payment mới mà không hiểu semantics, không được tự map thành PAID hoặc FAILED. Có thể lưu trạng thái unknown, tạm dừng workflow hoặc yêu cầu xử lý theo policy.

**Tolerant reader không có nghĩa bỏ qua mọi dữ liệu không hiểu.** Nó có nghĩa chấp nhận cấu trúc mở rộng trong khi giữ an toàn cho business rules.

## 8. Expand–migrate–contract

Đây là chiến lược phổ biến khi thay đổi contract mà không thể nâng cấp mọi consumer đồng thời.

~~~text
EXPAND
  Provider hỗ trợ field/endpoint/schema mới.
  Contract cũ vẫn được giữ.

MIGRATE
  Consumers nâng cấp dần.
  Telemetry xác nhận consumer mới dùng contract mới.

CONTRACT
  Ngừng consumer cũ sau support window.
  Loại bỏ field/endpoint cũ trong release phù hợp.
~~~

### 8.1. Expand

- Thêm field mới hoặc endpoint mới.
- Giữ field/endpoint cũ.
- Nếu cần, provider ghi song song hai representation.
- Consumer cũ tiếp tục hoạt động.
- Consumer mới có thể đọc representation mới.
- Tài liệu và contract tests cập nhật.

### 8.2. Migrate

- Nâng consumer theo thứ tự ưu tiên.
- Có thể phát hành SDK mới nhưng consumer tự chọn thời điểm nâng.
- Đo request/traffic theo client version.
- Kiểm tra event backlog và batch jobs.
- Xử lý consumer không thuộc quyền kiểm soát.
- Có rollback path nếu consumer mới gặp lỗi.

### 8.3. Contract

Chỉ xóa contract cũ khi:

- Consumer inventory đã được xác minh.
- Không còn traffic sử dụng field/endpoint cũ trong thời gian đủ dài.
- Batch/queue retention đã qua.
- Partner đã xác nhận nâng cấp.
- Có bằng chứng từ logs/metrics hoặc sign-off.
- Rollback window không còn phụ thuộc representation cũ.
- Quy trình khôi phục đã được kiểm chứng.

Không xóa field chỉ vì “các team đã được thông báo”.

## 9. Ví dụ đổi tên field mà không gây downtime

Giả sử field cũ là customerName và muốn chuyển sang displayName.

**Bước 1 — Expand provider**

~~~json
{
  "customerName": "Nguyen An",
  "displayName": "Nguyen An"
}
~~~

Provider phát cả hai field, cùng một semantics được document.

**Bước 2 — Migrate consumer**

Consumer mới ưu tiên displayName và fallback sang customerName khi response cũ chưa có field mới:

~~~java
String displayName = response.displayName() != null
    ? response.displayName()
    : response.customerName();
~~~

Cần xác định rõ behavior khi cả hai cùng tồn tại nhưng giá trị khác nhau. Không nên âm thầm chọn một giá trị nếu divergence có thể làm sai nghiệp vụ.

**Bước 3 — Observe**

Theo dõi client versions, field usage và lỗi parse. Đảm bảo tất cả consumers quan trọng đã nâng.

**Bước 4 — Contract**

Ngừng phát customerName sau deprecation window. Việc xóa field phải đi cùng API/schema version phù hợp và migration note.

## 10. Đổi type: thêm field mới thay vì đổi tại chỗ

Giả sử API cũ trả total dạng number, nhưng team muốn chuyển sang object Money có currency:

~~~json
{
  "total": 150000
}
~~~

Không nên đổi ngay total thành object vì consumer cũ có thể parse thất bại.

Có thể mở rộng:

~~~json
{
  "total": 150000,
  "money": {
    "amountMinor": 150000,
    "currency": "VND"
  }
}
~~~

Sau khi consumer nâng, provider có thể deprecate total và sau đó loại bỏ trong major version hoặc contract revision được công bố.

Cần xác định total cũ biểu diễn major units hay minor units. Nếu semantics trước đây không rõ, phải kiểm tra consumer thực tế trước khi chuyển; thêm field mới không tự giải quyết sự mơ hồ cũ.

## 11. Thêm enum value và unknown values

Enum là điểm dễ phá vỡ tương thích.

Provider cũ chỉ có:

~~~text
CREATED
PENDING
CONFIRMED
CANCELLED
~~~

Provider mới thêm:

~~~text
PARTIALLY_FULFILLED
~~~

Consumer cũ có thể:

- Throw exception khi deserialize.
- Rơi vào default branch sai.
- Bỏ qua event.
- Hiển thị trạng thái rỗng.
- Chuyển workflow sang trạng thái không hợp lệ.

Trước khi phát enum mới:

1. Kiểm kê consumers.
2. Nâng parser để chấp nhận unknown values.
3. Giữ raw string nếu cần audit.
4. Định nghĩa safe behavior cho unknown state.
5. Deploy consumer trước nếu provider có thể phát giá trị mới sau đó.
6. Chỉ bật producer behavior sau khi consumers sẵn sàng.

Với các state ảnh hưởng payment, inventory hoặc authorization, consumer có thể cần fail closed hoặc giữ operation pending thay vì đoán.

## 12. Null, missing và default là ba trường hợp khác nhau

JSON có thể phân biệt:

~~~json
{}
~~~

Field không xuất hiện.

~~~json
{"middleName": null}
~~~

Field có mặt với giá trị null.

~~~json
{"middleName": ""}
~~~

Field có mặt với chuỗi rỗng.

Chúng có thể có semantics khác nhau:

- Missing: producer không gửi hoặc consumer không yêu cầu.
- Null: producer biết giá trị hiện chưa có.
- Empty: giá trị đã được cung cấp nhưng rỗng.
- Default: consumer/provider tự áp dụng khi không có giá trị.

Khi thay đổi contract, phải ghi rõ nullability và default behavior. Một field chuyển từ optional sang required có thể phá request cũ; một field null được đổi thành empty string có thể làm validation hoặc business logic khác đi.

## 13. Thay đổi semantics nguy hiểm hơn thay đổi schema

Một field giữ nguyên tên và type nhưng đổi ý nghĩa vẫn là breaking change.

Ví dụ:

- total trước đây gồm tax, nay không gồm tax.
- availableStock trước đây là số có thể bán, nay là physical stock.
- createdAt trước đây là UTC, nay trả local time.
- status CONFIRMED trước đây nghĩa đã authorize, nay nghĩa đã capture.
- retryable=true trước đây chỉ dành cho timeout, nay bao gồm mọi 5xx.
- discountAmount trước đây là tổng discount, nay là discount trước tax.

Consumer có thể parse thành công và tạo kết quả sai. Semantic changes cần:

- Tên field mới nếu semantics thay đổi đáng kể.
- Documentation và examples.
- Contract tests với business assertions.
- Metric để phát hiện hành vi khác.
- Compatibility period.
- Migration guide cho consumer.

Không dùng cùng field name cho hai ý nghĩa trong một thời gian chuyển đổi nếu consumer không thể phân biệt.

## 14. Versioning API: khi nào cần version mới?

Có nhiều cách quản lý API evolution:

- **Additive evolution:** thêm field/endpoint tương thích, không cần major version mới nếu policy cho phép.
- **URI versioning:** /v1/orders và /v2/orders.
- **Header/media type versioning:** version được xác định qua header hoặc content negotiation.
- **Separate operation:** endpoint mới phục vụ use case mới.
- **Parallel schema:** giữ schema cũ và mới đồng thời.

Versioning là công cụ quản lý contract, không phải cách tránh thiết kế tương thích.

Nếu thay đổi nhỏ, additive evolution thường đơn giản hơn tạo /v2. Nếu semantics hoặc structure thay đổi lớn, version mới có thể làm migration rõ hơn.

Một API version không tự nói rằng version cũ còn được hỗ trợ bao lâu. Cần công bố lifecycle: active, deprecated, sunset, unsupported.

## 15. URI versioning và header versioning

Ví dụ URI:

~~~text
GET /v1/orders/ORD-100
GET /v2/orders/ORD-100
~~~

Ưu điểm là dễ nhìn trong logs, routing và documentation. Nhược điểm là có thể tạo hai bộ endpoint cần duy trì.

Ví dụ header:

~~~http
GET /orders/ORD-100
Accept: application/vnd.example.order-v2+json
~~~

Header versioning giúp giữ resource URI nhưng cần tooling, cache key và observability đúng. CDN/cache phải phân biệt representation theo header nếu nội dung khác nhau.

Không trộn nhiều chiến lược versioning thiếu quy tắc; consumer phải biết chính xác contract nào đang sử dụng và cách chọn version.

## 16. OpenAPI và generated clients

OpenAPI mô tả HTTP API và có thể sinh client/server code. Tuy nhiên generated client là một consumer có behavior riêng:

- Unknown fields có thể bị bỏ qua hoặc fail tùy generator/runtime.
- Enum có thể tạo Java enum strict.
- Nullable/optional có thể khác nhau giữa generator versions.
- Required fields mới có thể làm client cũ không tạo được request.
- Một generator update có thể đổi method signatures hoặc package names.

Quy trình:

1. Version hóa OpenAPI document.
2. Chạy breaking-change diff.
3. Generate client ở các version được hỗ trợ.
4. Compile consumer fixture với generated code.
5. Contract test request/response thật.
6. Publish SDK version mới.
7. Giữ server tương thích với SDK cũ trong support window.
8. Theo dõi consumer adoption.

Đừng coi “OpenAPI file hợp lệ” là bằng chứng tất cả client chạy được.

## 17. Consumer-driven contract testing

Consumer-driven contract tests mô tả interaction mà consumer thực sự cần. Provider xác minh implementation vẫn đáp ứng các expectations đó.

Một luồng điển hình:

1. Order consumer định nghĩa request và response fields mà nó sử dụng.
2. Contract được publish vào broker/repository.
3. Payment provider chạy provider verification.
4. CI báo consumer nào bị ảnh hưởng khi provider đổi.
5. Release pipeline chỉ cho phép deploy khi các contract bắt buộc được xác minh.

Lợi ích:

- Thấy consumer thực sự dùng phần nào của API.
- Bắt breaking change trước deploy.
- Không cần dựng toàn bộ production topology cho mọi test.
- Hỗ trợ nhiều consumer version cùng tồn tại.

Giới hạn:

- Contract test không thay integration, load, security hoặc end-to-end tests.
- Test chỉ phản ánh interactions đã khai báo.
- Consumer có thể có behavior ngầm chưa được ghi.
- Provider phải kiểm tra đúng environment/configuration.
- Contract broker cần quản lý version và ownership.

Pact là một lựa chọn phổ biến; có thể dùng tooling khác miễn là semantics và pipeline rõ.

## 18. Provider verification và deployment matrix

Không chỉ kiểm tra provider với consumer latest. Phải kiểm tra các phiên bản consumer còn nằm trong support window.

Ví dụ:

| Provider | Consumer | Trạng thái kiểm thử |
| --- | --- | --- |
| Order API v3 | Payment adapter 2.4 | Supported |
| Order API v3 | Shipping client 1.8 | Supported |
| Order API v3 | Mobile app 5.x | Supported |
| Order API v3 | Reporting job 1.2 | Pending verification |
| Order API v2 | Consumer legacy 1.5 | Deprecated window |

Bảng chỉ là ví dụ. Matrix thực tế nên tự động lấy từ consumer inventory và deployment manifests.

Nếu provider thay đổi response, test với mọi consumer được cam kết hỗ trợ. Không bắt buộc test mọi version từng tồn tại; cần một policy rõ về minimum supported version và thời gian sunset.

## 19. Event contract evolution

Trong event-driven architecture, consumer có thể đọc event muộn nhiều giờ hoặc nhiều ngày. Một producer deploy schema mới không có nghĩa mọi consumer đã nâng.

Ví dụ event cũ:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "total": 150000
}
~~~

Event mới thêm currency:

~~~json
{
  "eventType": "OrderPlaced",
  "eventId": "evt-100",
  "orderId": "ORD-100",
  "total": 150000,
  "currency": "VND"
}
~~~

Nếu currency optional và consumer cũ bỏ qua unknown field, cấu trúc có thể tương thích. Nhưng consumer mới cần biết cách xử lý event cũ không có currency. Không được mặc định VND nếu producer trước đây phục vụ nhiều currency.

### 19.1. Schema compatibility modes

Schema registry thường cung cấp các policy như:

- **Backward:** schema mới có thể đọc dữ liệu được ghi theo schema cũ theo định nghĩa registry.
- **Forward:** consumer/schema cũ có thể đọc dữ liệu mới theo policy.
- **Full:** thỏa cả backward và forward.
- **Transitive:** kiểm tra với nhiều version trước đó, không chỉ version liền kề.

Tên và semantics cụ thể phụ thuộc registry/format. Avro, Protobuf và JSON Schema có quy tắc khác nhau; phải kiểm tra documentation của công cụ.

Schema compatibility không tự chứng minh business semantics đúng hoặc consumer side effects idempotent.

## 20. Protobuf và thay đổi field an toàn

Với Protobuf, field number là một phần của wire contract. Không tái sử dụng field number đã xóa.

Ví dụ:

~~~proto
message Order {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;

  reserved 4;
  reserved "legacy_note";
}
~~~

Khi bỏ field 4, reserve số và tên để tránh một version tương lai vô tình dùng lại và diễn giải bytes cũ theo field mới.

Các lưu ý:

- Không đổi field number.
- Cân nhắc wire type khi đổi field.
- Thêm field mới với number mới.
- Xử lý unknown fields theo library/runtime.
- Không thay semantics mà giữ nguyên field number.
- Test old/new producer và consumer combinations.
- Xem xét generated code behavior.

Protobuf có compatibility rules riêng; không suy ra rằng mọi đổi type đều an toàn chỉ vì field number giữ nguyên.

## 21. Avro và JSON Schema

Avro thường dùng schema writer và reader để resolve khác biệt. Default values có vai trò trong schema evolution, nhưng default không phải cách tự động khôi phục ý nghĩa nghiệp vụ bị thiếu.

JSON Schema có thể quy định required fields, additionalProperties, enum và nullable behavior. Một schema mới thêm required field có thể làm producer cũ không tạo được document hợp lệ.

Cần test theo format thực tế:

- Writer schema cũ với reader schema mới.
- Writer schema mới với reader schema cũ.
- Dữ liệu historical replay.
- Default/null behavior.
- Unknown fields/enum.
- Schema registry compatibility policy.
- Generated model/runtime versions.

Không copy compatibility assumptions từ Avro sang JSON Schema hoặc Protobuf.

## 22. Event naming và semantic versioning

Event type biểu diễn một fact đã xảy ra, ví dụ OrderPlaced hoặc PaymentCaptured. Không nên đổi nghĩa của event hiện tại mà vẫn giữ cùng event name.

Nếu semantics thay đổi lớn:

- Tạo event type mới.
- Giữ producer phát event cũ trong migration window.
- Consumer mới hỗ trợ cả hai.
- Có mapping adapter hoặc upcaster.
- Theo dõi consumer lag và adoption.
- Sau retention/replay window mới ngừng event cũ.

Event version có thể nằm trong schema registry subject/version, envelope field hoặc event type naming. Chọn một convention và document rõ.

Không version mọi event chỉ vì thêm optional field; cũng không giữ nguyên version khi semantics đã thay đổi không tương thích.

## 23. Database schema evolution khi nhiều phiên bản ứng dụng cùng chạy

Trong rolling deployment, một số application instances cũ vẫn chạy khi database schema mới đã được áp dụng.

Mẫu expand–migrate–contract cho database:

1. **Expand:** thêm nullable column/table/index mới, giữ cấu trúc cũ.
2. Deploy code có thể đọc cấu trúc cũ và mới.
3. Backfill dữ liệu.
4. Deploy code ghi/đọc field mới.
5. Xác minh mọi instance và batch job đã chuyển.
6. Ngừng ghi field cũ.
7. Sau support/rollback window, mới drop field cũ.

Không rename/drop column trong cùng release mà app cũ vẫn chạy. Không thêm NOT NULL constraint trước khi dữ liệu cũ được backfill và mọi writer cung cấp giá trị.

### 23.1. Migration phải tương thích với rolling deploy

Giả sử phiên bản app A đọc column old_name, app B đọc new_name. Nếu migration drop old_name trước khi A biến mất, A sẽ lỗi.

Một deploy an toàn có thể gồm:

- DB migration expand.
- App version hỗ trợ cả hai field.
- Backfill.
- Chuyển writes sang new_name.
- Verify.
- App version không còn đọc old_name.
- DB migration contract ở release sau.

## 24. Thay đổi write contract và read contract

Read contract và write contract có rủi ro khác nhau.

**Read response:** thêm field thường dễ hơn xóa field, nhưng parser strict và semantic changes vẫn có thể phá.

**Write request:** thêm required field thường phá consumer cũ ngay. Provider cần optional field/default có semantics hợp lệ, hoặc endpoint/version mới.

Ví dụ request cũ:

~~~json
{
  "orderId": "ORD-100",
  "total": 150000
}
~~~

Nếu provider yêu cầu currency mới, không thể tự suy ra currency khi hệ thống đa tiền tệ. Có thể:

- Thêm currency optional trong giai đoạn đầu và lấy từ order context đáng tin.
- Tạo endpoint mới yêu cầu currency.
- Chỉ bật validation bắt buộc sau khi consumers migrate.
- Theo dõi requests thiếu currency và owner của chúng.

Không dùng default giả để biến request thiếu thông tin thành một giao dịch sai.

## 25. Idempotency và concurrency trong thời gian chuyển contract

Khi producer hỗ trợ hai dạng request, cả hai phải ánh xạ về cùng logical operation nếu nghiệp vụ giống nhau.

Ví dụ consumer cũ gửi total, consumer mới gửi Money object. Nếu retry tạo cùng order/payment, idempotency key phải nhận diện operation giống nhau.

Cần:

- Stable idempotency key.
- Canonical request semantics.
- Mapping rõ giữa field cũ/mới.
- Duplicate detection.
- Optimistic concurrency/version nếu cần.
- Không thực hiện side effect hai lần chỉ vì request đi qua adapter khác.
- Audit representation/version của request.

Nếu old/new contract tạo ra hai hash payload khác nhau nhưng cùng operation, idempotency implementation phải dựa trên logical command đã chuẩn hóa hoặc lưu mapping tương ứng.

## 26. Compatibility adapter và anti-corruption layer

Khi nhiều consumer nâng cấp theo lịch khác nhau, provider hoặc gateway có thể cung cấp adapter:

~~~text
Consumer v1 --> V1 adapter --\
                              -> Canonical domain command
Consumer v2 --> V2 adapter --/            |
                                           v
                                      Domain service
~~~

Adapter chịu trách nhiệm:

- Parse version-specific request.
- Validate fields theo contract tương ứng.
- Chuyển thành canonical command.
- Map response/error về representation cũ/mới.
- Ghi telemetry về version đang sử dụng.

Domain logic chỉ nên có một semantics authoritative. Không copy business rules sang từng adapter.

Adapter là giải pháp chuyển tiếp có lifecycle. Nếu giữ v1 mãi mãi, hệ thống sẽ mang theo nhiều code path, test matrix và security burden.

## 27. Mobile và external partner clients

Mobile app có thể ở ngoài quyền deploy của backend. Partner có quy trình certification và lịch release riêng.

Cần:

- Support window công bố theo client type.
- Version/identity trong request hoặc user-agent/client metadata.
- Compatibility tests với minimum supported client.
- Feature flags theo cohort.
- Sunset policy và thông báo trước.
- Telemetry đủ nhận diện traffic cũ.
- Graceful error khi client hết hỗ trợ.
- Không dùng IP address làm cách duy nhất nhận diện version.

Với partner, có thể cần sandbox, test credentials, migration guide, changelog và thời gian certification. Không xóa contract trước ngày sunset đã cam kết.

## 28. Version negotiation và capability detection

Không phải lúc nào cũng cần một API version lớn. Có thể negotiate capability qua:

- API version/header.
- Explicit feature capability.
- Client version.
- Accept media type.
- Event schema version.
- Server capability endpoint.

Capability flag nên mô tả khả năng cụ thể, không tạo hàng trăm boolean mơ hồ.

Ví dụ client có thể khai báo hỗ trợ partial fulfillment. Provider chỉ gửi representation đó khi consumer xác nhận capability. Cần mặc định an toàn cho client không khai báo.

Không dựa vào user-agent string không đáng tin để quyết định quyền nghiệp vụ hoặc bảo mật.

## 29. Feature flags hỗ trợ migration, nhưng không thay contract

Feature flag có thể bật behavior mới theo tenant/cohort:

1. Deploy code hỗ trợ cả behavior cũ và mới.
2. Giữ flag off.
3. Chạy internal/canary consumers.
4. Quan sát metrics và contract outcomes.
5. Tăng cohort.
6. Bật mặc định khi đủ bằng chứng.
7. Gỡ code/flag cũ sau support window.

Cần tránh flag sống mãi và tạo ma trận tổ hợp không kiểm thử được. Ghi owner, ngày review, kill switch và điều kiện xóa.

Feature flag không giúp consumer cũ parse một schema đã bị thay đổi đột ngột. Provider vẫn phải giữ representation tương thích.

## 30. Deprecation và sunset

**Deprecation** thông báo contract sẽ ngừng hỗ trợ; **sunset** là thời điểm support kết thúc theo policy.

Một kế hoạch deprecation nên công bố:

- Contract/field/endpoint/event nào bị deprecated.
- Lý do và rủi ro.
- Replacement/migration guide.
- Phiên bản thay thế.
- Ngày bắt đầu deprecation.
- Ngày sunset dự kiến.
- Consumer bị ảnh hưởng.
- Cách yêu cầu extension/exception.
- Contact và support process.

Có thể dùng response headers như Deprecation hoặc Sunset theo chuẩn/hạ tầng phù hợp, nhưng phải kiểm tra client/gateway có chuyển tiếp header không.

Không tuyên bố sunset chỉ dựa trên một email. Cần traffic evidence, consumer inventory và xác nhận với owner.

## 31. Observability theo contract version

Để biết còn consumer cũ hay không, cần đo:

- Request count theo API version/client version.
- Field cũ được sử dụng trong request bao nhiêu lần.
- Response field cũ có consumer nào đọc được xác nhận hay không.
- Event schema version đang được produce/consume.
- Consumer lag và tuổi event cũ nhất.
- Error/parse failure theo version.
- Contract verification status.
- SDK version trong deployment inventory.
- Partner/client adoption.
- Deprecated endpoint traffic.

Không log toàn bộ payload chỉ để tìm field usage; có thể dùng sanitized metadata, schema version và counters. Tránh đưa customer ID, token hoặc PII vào metrics labels.

Với field response, provider không thể luôn biết consumer có đọc field hay không. Có thể cần consumer attestation, SDK telemetry hoặc contract inventory thay vì suy đoán từ request logs.

## 32. Testing strategy cho nhiều phiên bản cùng tồn tại

Một test matrix nên bao gồm:

| Provider | Consumer | Mục tiêu |
| --- | --- | --- |
| Old | Old | Baseline |
| New | Old | Backward compatibility |
| Old | New | Forward compatibility nếu được cam kết |
| New | New | Target behavior |
| New | Minimum supported | Support boundary |
| Rollback provider | Current consumer | Recovery path |
| Historical event | New consumer | Replay compatibility |

Không phải mọi cặp đều có ý nghĩa với mọi protocol. Với event stream, cần test historical payload; với HTTP, cần test request/response; với database, cần test rolling deploy old/new app trên expanded schema.

Ngoài contract tests, cần integration tests, security tests, load tests và failure tests theo mức độ rủi ro.

### 32.1. Consumer fixture

Giữ một số fixture đại diện cho payload từ các version đã phát hành:

- Response API v1.
- Response API v2.
- Event schema v1.
- Event schema v2.
- Request cũ thiếu field mới.
- Enum value chưa biết.
- Null/missing/default cases.
- Error payload.

Consumer mới chạy tests trên fixtures cũ để bảo đảm có thể xử lý dữ liệu còn trong queue hoặc từ client cũ.

## 33. Release order: deploy consumer trước hay provider trước?

Không có thứ tự duy nhất cho mọi thay đổi; dùng expand–migrate–contract.

Với việc **thêm field optional**:

1. Deploy provider phát field mới nhưng vẫn giữ field cũ.
2. Deploy consumer có thể đọc field mới và fallback field cũ.
3. Chuyển consumer sang field mới.
4. Theo dõi adoption.
5. Ngừng field cũ sau support window.

Với việc **producer bắt đầu gửi enum mới**:

1. Deploy consumer có khả năng xử lý unknown/new enum.
2. Verify tất cả consumers quan trọng.
3. Bật producer phát giá trị mới.
4. Theo dõi errors và workflow outcomes.

Với **thêm required request field**:

1. Provider trước tiên chấp nhận field optional/legacy path.
2. Consumer nâng và bắt đầu gửi field mới.
3. Đo requests còn thiếu field.
4. Chỉ sau khi adoption đạt mới enforce required.
5. Gỡ fallback cũ theo policy.

Điều kiện tiên quyết là provider có thể triển khai compatibility code trước khi thay đổi behavior thực tế.

## 34. Rollback khi contract mới đã được sử dụng

Một rollback có thể làm provider cũ gặp dữ liệu mới. Ví dụ consumer mới gửi field currency, provider mới lưu nó, sau đó rollback về provider cũ không hiểu field đó.

Trước release phải hỏi:

- Data/schema có thể được đọc bởi version cũ không?
- Consumer mới có thể fallback về contract cũ không?
- Event mới đã được publish chưa, và consumer cũ có đọc được không?
- Có thể disable behavior mới mà không mất data?
- API gateway route có thể quay lại không?
- Queue có giữ message mới qua rollback window không?
- Có roll-forward path nếu rollback không an toàn?

Có thể giữ compatibility adapter và schema cũ trong thời gian rollback. Nếu dữ liệu mới không thể biểu diễn trong hệ cũ, rollback application version nhưng giữ database/schema mới có thể an toàn hơn rollback toàn bộ data format.

**Rollback không phải lúc nào cũng là quay lại trạng thái cũ.** Có lúc cần roll-forward và sửa implementation trong khi giữ contract/data mới.

## 35. Governance: ai quyết định contract thay đổi?

Mỗi contract cần owner. Quy trình thay đổi nên xác định:

- Producer owner.
- Consumer inventory/owners.
- API/event/schema reviewer.
- Compatibility policy.
- Support window.
- Deprecation/sunset authority.
- Security/privacy review khi payload đổi.
- Changelog và migration guide.
- Exception process.
- Metrics chứng minh adoption.

Không để một platform team tự xóa field mà không biết ai đang sử dụng. Cũng không để một consumer bất kỳ chặn mọi evolution vô thời hạn; cần support policy, sunset process và escalation.

## 36. Runbook thay đổi contract an toàn

### Pha A — Discover

1. Xác định contract và version hiện tại.
2. Tìm tất cả consumers, gồm batch, mobile, partner và replay.
3. Kiểm tra actual traffic/version.
4. Xác định thay đổi additive hay breaking cả syntax lẫn semantics.
5. Định nghĩa compatibility window và rollback requirements.

### Pha B — Design

1. Ưu tiên thêm field/endpoint mới.
2. Viết mapping giữa old và new representation.
3. Định nghĩa null/default/enum behavior.
4. Cập nhật OpenAPI/schema/event docs.
5. Tạo consumer/provider contract tests.
6. Chuẩn bị telemetry và deprecation communication.

### Pha C — Expand

1. Deploy provider hỗ trợ old và new.
2. Chưa bật behavior mới nếu consumer chưa sẵn sàng.
3. Kiểm tra old clients vẫn hoạt động.
4. Bật shadow/canary nếu phù hợp.
5. Xác nhận rollback code path.

### Pha D — Migrate

1. Nâng consumer theo owner và lịch.
2. Chạy contract/integration tests.
3. Theo dõi request/event versions.
4. Xử lý lagging consumers.
5. Bật behavior mới theo cohort.
6. Theo dõi business correctness.

### Pha E — Contract

1. Xác nhận không còn consumer dùng contract cũ.
2. Chờ queue/backlog và replay retention phù hợp.
3. Thực hiện deprecation/sunset theo cam kết.
4. Loại bỏ adapter/field cũ.
5. Chạy full compatibility tests còn lại.
6. Cập nhật inventory, docs và support matrix.

## 37. Anti-pattern thường gặp

1. Đổi tên hoặc xóa field ngay trong một deploy.
2. Thêm required field vào request khi consumer cũ chưa nâng.
3. Thêm enum value nhưng consumer deserialize strict.
4. Coi thêm field luôn backward-compatible.
5. Đổi semantics nhưng giữ field name/type.
6. Dùng default giả cho dữ liệu không thể suy ra.
7. Publish event mới mà consumer cũ không hiểu.
8. Reuse Protobuf field number đã xóa.
9. Xóa schema cũ khi event backlog vẫn chứa payload cũ.
10. Chỉ test latest consumer, bỏ minimum supported.
11. Coi OpenAPI validation là bằng chứng runtime compatibility.
12. Generated SDK đổi method signatures nhưng không có migration guide.
13. Deploy producer và consumer theo big-bang.
14. Không giữ rollback window.
15. Không đo consumer adoption.
16. Gửi deprecation email rồi xóa endpoint.
17. Giữ v1 mãi mà không có sunset owner.
18. Tạo /v2 cho mọi additive change.
19. Version hóa API nhưng để shared domain semantics mơ hồ.
20. Bật feature flag mới trước khi consumer hỗ trợ.
21. Retry lỗi parse/validation như lỗi transient.
22. Log toàn bộ payload để đo field usage, gây lộ PII.
23. Không test historical event replay.
24. Không kiểm tra batch jobs, partner integrations và mobile apps.
25. Không biết service nào đang chạy SDK version nào.
26. Coi rollback image là rollback được database và event stream.

## 38. Checklist trước khi phát hành contract change

### Contract và compatibility

- [ ] Xác định producer/provider và toàn bộ consumer.
- [ ] Phân loại thay đổi syntax, binary và semantics.
- [ ] Kiểm tra null, missing, default, enum và unknown fields.
- [ ] Có backward/forward compatibility requirement rõ.
- [ ] Có mapping old/new representation.
- [ ] Có support window và deprecation/sunset policy.

### Testing

- [ ] Breaking-change/schema diff chạy trong CI.
- [ ] Consumer-driven contract tests.
- [ ] Provider verification với consumers được hỗ trợ.
- [ ] Test old consumer với new provider.
- [ ] Test new consumer với historical payload.
- [ ] Test generated SDK và runtime parser.
- [ ] Test event replay/queue backlog.
- [ ] Integration/security/load tests theo rủi ro.

### Rollout và vận hành

- [ ] Expand–migrate–contract có owner và timeline.
- [ ] Có feature flag/canary nếu cần.
- [ ] Telemetry theo version và consumer.
- [ ] Batch/partner/mobile clients được tính đến.
- [ ] Rollback/roll-forward đã xem xét data compatibility.
- [ ] Chỉ contract sau khi có adoption evidence.
- [ ] Docs, changelog và migration guide đã công bố.

## 39. Câu hỏi tự kiểm tra

**1. Vì sao microservices không thể giả định mọi consumer nâng cấp cùng lúc?**  
Vì mỗi service/team/client có release cadence, deployment window, ownership và thời gian tồn tại khác nhau; event backlog còn giữ dữ liệu cũ.

**2. Backward compatibility là gì?**  
Provider mới vẫn đáp ứng contract mà consumer cũ dựa vào trong support window.

**3. Forward compatibility của consumer là gì?**  
Consumer có thể xử lý dữ liệu mới trong phạm vi được thiết kế, ví dụ bỏ qua optional field chưa biết nhưng vẫn giữ business safety.

**4. Thêm field JSON có luôn an toàn?**  
Không. Parser/schema strict, generated clients hoặc signature logic có thể fail.

**5. Vì sao thêm enum value nguy hiểm?**  
Consumer có thể deserialize strict hoặc rơi vào default branch sai.

**6. Expand–migrate–contract gồm những gì?**  
Mở rộng provider/schema, chuyển consumers dần, rồi mới loại bỏ contract cũ sau khi xác minh adoption.

**7. Vì sao semantics change có thể breaking dù schema không đổi?**  
Consumer parse được nhưng hiểu sai giá trị, đơn vị, trạng thái hoặc business rule.

**8. Có nên dùng /v2 cho mọi thay đổi?**  
Không. Additive changes có thể evolution trong version hiện tại; thay đổi lớn cần version/contract mới theo policy.

**9. Consumer-driven contract test chứng minh điều gì?**  
Provider đáp ứng các interactions mà consumer đã khai báo; nó không thay mọi loại integration/load/security test.

**10. Vì sao phải giữ historical event fixtures?**  
Consumer mới có thể nhận event cũ từ backlog, replay hoặc retention archive.

**11. Khi nào nên phát enum mới?**  
Sau khi các consumer quan trọng có thể xử lý unknown/new values và có safe behavior.

**12. Vì sao không reuse Protobuf field number?**  
Bytes cũ có thể bị diễn giải thành field mới, gây lỗi tương thích và dữ liệu sai.

**13. Có thể xóa field sau khi gửi thông báo deprecation không?**  
Không. Cần traffic/adoption evidence, consumer inventory, retention và sunset policy.

**14. Rollback app có luôn an toàn sau khi contract mới được sử dụng?**  
Không. Data/event mới có thể không được version cũ hiểu; cần rollback compatibility hoặc roll-forward.

**15. Làm sao biết đã có thể contract?**  
Không còn consumer được hỗ trợ dùng contract cũ, backlog/replay window đã qua, telemetry và owner sign-off xác nhận.

## 40. Tài liệu tham khảo

- Martin Fowler — Evolutionary Database Design: https://martinfowler.com/articles/evodb.html
- Martin Fowler — Parallel Change: https://martinfowler.com/bliki/ParallelChange.html
- Martin Fowler — Consumer-Driven Contracts: https://martinfowler.com/articles/consumerDrivenContracts.html
- Google Cloud — API design and evolution: https://cloud.google.com/apis/design
- Microsoft — API design best practices: https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design
- Microsoft — API implementation: https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-implementation
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- Pact — Consumer-driven contract testing: https://docs.pact.io/
- Protocol Buffers — Updating a Message Type: https://protobuf.dev/programming-guides/proto3/#updating
- Apache Avro — Specification: https://avro.apache.org/docs/current/specification/
- JSON Schema — Understanding JSON Schema: https://json-schema.org/understanding-json-schema/
- Confluent Schema Registry — Schema Evolution: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
- RFC 9745 — Deprecation HTTP Header: https://www.rfc-editor.org/rfc/rfc9745
- RFC 8594 — The Sunset HTTP Header: https://www.rfc-editor.org/rfc/rfc8594

**Ghi nhớ:** Khi consumer không thể nâng cấp đồng thời, hãy **mở rộng contract trước, giữ phiên bản cũ trong compatibility window, migrate từng consumer có telemetry và contract tests, rồi mới contract**. Tương thích phải được xét cả syntax, binary, semantics, event backlog và rollback. Versioning chỉ hữu ích khi ownership, support window và bằng chứng adoption được quản lý rõ.
