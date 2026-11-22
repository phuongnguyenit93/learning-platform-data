# Kiểm tra hợp đồng tự động trong quy trình phát hành

Trong kiến trúc microservices, một thay đổi nhỏ ở API, event, message hoặc schema có thể làm consumer đang chạy trên production ngừng hoạt động hoặc — nguy hiểm hơn — tiếp tục chạy nhưng hiểu sai dữ liệu. **Kiểm tra hợp đồng tự động (automated contract testing)** đưa các cam kết tích hợp giữa các thành phần vào hệ thống kiểm thử và CI/CD để phát hiện thay đổi không tương thích **trước khi triển khai hoặc kích hoạt hành vi mới**.

Mục tiêu không phải bắt mọi service cùng nâng cấp. Mục tiêu là cho phép producer/provider và consumer triển khai theo nhịp riêng, trong khi những phiên bản có khả năng gặp nhau ở production vẫn tương thích về **cấu trúc, ý nghĩa và hành vi**.

Bài này trình bày cách xây một quy trình từ xác định owner hợp đồng, tạo test, kiểm tra consumer–provider, kiểm tra version đang triển khai, quyết định release gate và xác minh sau deploy. Ví dụ xuyên suốt gồm Ordering, Pricing, Inventory, Payments và Notifications. Các công cụ như Pact, Spring Cloud Contract, OpenAPI/AsyncAPI và schema registry được giới thiệu theo vai trò; tên command cụ thể phụ thuộc phiên bản được cài trong dự án.

## 1. Hợp đồng tích hợp là gì?

Hợp đồng (contract) mô tả những gì hai thành phần có thể dựa vào khi giao tiếp. Nó không chỉ là một file schema, cũng không chỉ là một mock HTTP.

Một hợp đồng hữu ích có thể chứa:

- **Endpoint, method, status code** và định dạng request/response của REST hoặc RPC.
- **Field và kiểu dữ liệu:** bắt buộc/tùy chọn, nullable, enum, định dạng ngày giờ, đơn vị tiền, giới hạn số.
- **Ý nghĩa nghiệp vụ:** PAID nghĩa là đã authorize hay đã capture? Amount là trước hay sau giảm giá?
- **Error contract:** lỗi validation, conflict, quota, not found, timeout có semantics nào?
- **Authentication/authorization:** ai được gọi endpoint hoặc publish/consume destination?
- **Đặc tính xử lý:** idempotency, pagination, ordering, correlation ID, thời gian hết hạn.
- **Message/event contract:** tên event, schemaVersion, topic, key, fields và thời điểm phát.
- **Tương thích phiên bản:** những producer/consumer cũ nào còn được hỗ trợ và trong bao lâu?
- **Giới hạn phi chức năng liên quan:** timeout, kích thước message, rate limit, retention nếu consumer dựa vào.

Ví dụ Pricing trả báo giá:

~~~json
{
  "sku": "A100",
  "price": {
    "amountMinor": 159900,
    "currency": "VND"
  },
  "quoteVersion": "pv-32",
  "validUntil": "2026-11-12T10:00:00Z"
}
~~~

Ordering có thể cam kết chỉ cần sku, price.amountMinor và price.currency. Nếu Pricing đổi amountMinor từ số nguyên thành chuỗi có ký hiệu tiền, consumer cũ có thể hỏng. Nếu Pricing giữ kiểu nhưng đổi ý nghĩa thành số tiền trước giảm giá, contract vẫn có thể bị phá ở **mức ngữ nghĩa** dù công cụ schema diff không phát hiện.

## 2. Phân biệt các loại kiểm thử

| Loại kiểm thử | Câu hỏi chính | Độ bao phủ/giới hạn |
| --- | --- | --- |
| Unit test | Logic trong một module đúng không? | Không chứng minh provider và consumer hiểu cùng hợp đồng |
| Schema validation | Payload phù hợp JSON Schema, OpenAPI, Avro/Protobuf không? | Bắt kiểu/trường, không chứng minh semantics |
| Consumer contract test | Consumer kỳ vọng những request/response hoặc message nào? | Tạo kỳ vọng có thể chia sẻ; không tự chứng minh provider thật đáp ứng |
| Provider verification | Provider triển khai hiện tại có đáp ứng các kỳ vọng consumer đang hỗ trợ không? | Chứng minh trên test/config cụ thể, không phải mọi tình huống production |
| Compatibility/diff check | Hợp đồng mới có phá phiên bản trước không? | Phân tích thay đổi cấu trúc, cần bổ sung kiểm tra hành vi |
| Integration test | Các thành phần thật kết nối, serialization, auth, DB, broker có đúng không? | Tốn tài nguyên hơn, cần môi trường và dữ liệu |
| End-to-end test | Luồng nghiệp vụ xuyên nhiều service vận hành đúng không? | Quan trọng cho luồng cốt lõi nhưng chậm/khó chẩn đoán |
| Synthetic/smoke sau deploy | Phiên bản được triển khai có thực sự phục vụ được trên môi trường đích? | Phát hiện lỗi cấu hình/vận hành, không thay thế contract tests |

Một pipeline hiệu quả kết hợp các lớp. **Mock consumer test chỉ chứng minh consumer chạy với một mock; provider verification mới nối kỳ vọng đó với implementation thật.** Ngược lại, chỉ chạy end-to-end với toàn bộ phiên bản mới có thể bỏ sót lỗi consumer cũ vẫn còn trên production.

## 3. Ai sở hữu hợp đồng và ai kiểm chứng?

Trong REST:

- **Provider** là service cung cấp API, ví dụ Pricing.
- **Consumer** là service gọi API, ví dụ Ordering.
- **Contract owner** cần xác định theo tổ chức: provider chịu trách nhiệm công bố API công khai và chính sách thay đổi; consumer chịu trách nhiệm mô tả những phần thật sự dùng.
- **Registry/Broker hợp đồng** lưu phiên bản contract, verification results và trạng thái phiên bản đang deployed, nếu chọn nền tảng hỗ trợ.
- **CI/CD** kiểm tra kết quả và quyết định có cho phép artifact đi đến môi trường kế tiếp.

Trong event-driven:

- **Producer** sở hữu fact và schema của event, ví dụ Inventory phát StockReserved.
- **Consumer** là service đọc event, ví dụ Ordering workflow.
- **Schema registry** có thể kiểm tra tương thích cấu trúc của schema theo subject và chính sách, nhưng không thay provider/consumer integration tests.
- **Broker thông điệp** vận chuyển message; không nên nhầm nó với Pact Broker dùng để lưu contract và kết quả verification.

Một service có thể vừa là consumer của API A vừa là producer của event B. Nó cần test cả hai phía phù hợp trách nhiệm.

## 4. Cần bảo vệ những tổ hợp phiên bản nào?

Giả sử đang chạy:

- Pricing v1 trên production.
- Ordering v1 trên production.

Team phát triển Pricing v2 và Ordering v2. Trong rolling deployment, canary, multi-region hoặc rollback, có thể xảy ra:

| Consumer / Provider | Pricing v1 | Pricing v2 |
| --- | --- | --- |
| Ordering v1 | Đang hoạt động | **Phải tương thích** khi deploy Pricing v2 trước |
| Ordering v2 | **Phải tương thích** nếu deploy Ordering v2 trước/rollback Pricing | Dự kiến hoạt động |

Một test “Ordering v2 với Pricing v2 thành công” chỉ kiểm tra ô cuối. Điều kiện để phát hành độc lập là tất cả những ô có thể cùng tồn tại theo chiến lược rollout đều hoạt động an toàn. Không nhất thiết hỗ trợ mọi phiên bản mãi mãi; phải ghi **cửa sổ tương thích** và thời điểm deprecation.

Ví dụ breaking change:

~~~json
// Pricing v1
{
  "sku": "A100",
  "amountMinor": 159900,
  "currency": "VND"
}
~~~

~~~json
// Pricing v2 nếu thay ngay
{
  "sku": "A100",
  "price": { "amountMinor": 159900, "currency": "VND" }
}
~~~

Ordering v1 có thể chỉ đọc amountMinor ở top-level nên thất bại khi Pricing v2 bỏ field đó. Một thay đổi an toàn hơn thường trải qua **expand → migrate → contract**:

1. Pricing thêm price mới nhưng **giữ field cũ** trong giai đoạn chuyển tiếp.
2. Ordering v2 học cách đọc price, có fallback khi gặp Pricing cũ nếu cần.
3. CI xác nhận Ordering v1 và v2 tương thích với những bản Pricing có thể gặp.
4. Quan sát consumer còn dùng hợp đồng cũ; thông báo deprecation.
5. Chỉ bỏ amountMinor cũ khi hết cửa sổ hỗ trợ và không còn consumer phụ thuộc.

Kiểm tra hợp đồng tự động là bằng chứng để quyết định qua từng pha, thay vì đoán rằng tất cả service đã nâng cấp.

## 5. Thiết kế danh mục hợp đồng

Trước khi viết test, kiểm kê **những đường giao tiếp thật sự tồn tại**.

| Contract | Provider/producer | Consumer | Transport | Dữ liệu cốt lõi | Chính sách version |
| --- | --- | --- | --- | --- | --- |
| GetPriceQuote | Pricing | Ordering, Checkout | REST | sku, amountMinor, currency | Hỗ trợ v1 đến khi consumer chuyển |
| ReserveStock | Inventory | Ordering workflow | Async command | commandId, sku, quantity | Schema version + idempotency |
| StockReserved | Inventory | Ordering, Analytics | Event | eventId, orderId, reservationId | Additive fields, retention |
| AuthorizePayment | Payments | Ordering workflow | REST/async command | paymentId, amount, currency | Backward-compatible |
| PaymentAuthorized | Payments | Ordering, Ledger | Event | paymentId, status, occurredAt | Semantics tài chính bất biến |
| CustomerUpdated | Customer | Marketing, Reporting | Event | customerId, version, fields | Quy định dữ liệu nhạy cảm |

Mỗi hợp đồng nên có:

- Tên canonical, mô tả semantics và owner.
- Link đến OpenAPI, Proto, AsyncAPI hoặc schema source of truth.
- Consumer đang hoạt động và các environment/version liên quan.
- Quy định breaking change, deprecation và phạm vi tương thích.
- Test tự động và artifact kiểm chứng.
- Người liên hệ khi có contract break.
- Phương án rollout, rollback và khôi phục khi consumer cũ còn tồn tại.

Không chỉ tìm consumer qua source code hiện tại. Cần tính đến batch job, mobile client, đối tác, cron, consumer đang tạm offline và những record cũ còn trong queue/broker.

## 6. Consumer-driven contract testing (CDC)

Trong CDC, **consumer mô tả những tương tác nó thực sự cần**, rồi provider kiểm tra implementation của mình đối với những kỳ vọng đang được hỗ trợ. Một công cụ tiêu biểu là Pact; một số nhóm dùng Spring Cloud Contract hoặc cách công bố contract riêng.

Ví dụ Ordering sử dụng Pricing:

~~~text
Consumer: Ordering
Provider: Pricing
Interaction: Get quote for known SKU

Given: SKU A100 có báo giá hợp lệ
When:
  GET /v1/prices/A100?currency=VND
Then:
  status = 200
  body.sku = "A100"
  body.amountMinor là integer không âm
  body.currency = "VND"
~~~

Consumer test chạy với mock provider theo contract, kiểm chứng rằng client Ordering tạo đúng request và xử lý response đúng.

Sau đó producer/provider Pricing nhận contract artifact, dựng provider states tương ứng và chạy verification:

~~~text
Ordering contract test
  -> tạo contract artifact
  -> publish contract version cho registry

Pricing verification
  -> lấy contract của consumer được hỗ trợ
  -> thiết lập provider state
  -> gửi request tới implementation Pricing
  -> so response/status/headers/body với contract
  -> publish verification result
~~~

Cần chú ý:

1. **Consumer contract không phải API schema toàn bộ.** Nó mô tả những tương tác consumer quan tâm.
2. **Provider verification không được dựa vào mock của chính provider.** Test phải chạy implementation thực, có fixture/test data ổn định.
3. **Provider state** cần độc lập, deterministic, không phải dữ liệu bí mật hay shared mutable database của production.
4. **Kết quả phải gắn với phiên bản artifact** của provider và consumer. Một kết quả PASS của nhánh cũ không chứng minh commit mới an toàn.
5. **Những consumer không có mặt trong registry không tự được bảo vệ.** Cần chính sách onboard, inventory và loại bỏ orphan contracts.
6. Contract test tốt không buộc tất cả service deploy cùng lúc; nó cung cấp bằng chứng để chúng deploy độc lập.

## 7. Provider-driven/OpenAPI-first

Một mô hình khác là provider công bố OpenAPI/Proto chuẩn hóa và consumer sinh client hoặc kiểm thử theo mô tả đó. CI có thể so sánh hợp đồng mới với phiên bản đã phát hành để phát hiện breaking change.

Ví dụ đoạn OpenAPI:

~~~yaml
openapi: 3.0.3
info:
  title: Pricing API
  version: 1.0.0
paths:
  /v1/prices/{sku}:
    get:
      parameters:
        - name: sku
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Price quote
          content:
            application/json:
              schema:
                type: object
                required: [sku, amountMinor, currency]
                properties:
                  sku:
                    type: string
                  amountMinor:
                    type: integer
                    format: int64
                    minimum: 0
                  currency:
                    type: string
                    enum: [VND, USD]
~~~

Các thay đổi thường cần cảnh giác:

| Thay đổi | Nguy cơ với consumer cũ |
| --- | --- |
| Xóa endpoint hoặc đổi method | Client nhận 404/405 |
| Đổi tên path hoặc query param bắt buộc | Request cũ không còn hợp lệ |
| Thêm field request bắt buộc | Client cũ bị reject |
| Xóa field response đang được sử dụng | Consumer cũ không parse/thiếu dữ liệu |
| Đổi integer sang string/object | Serializer/logic bị phá |
| Thắt chặt enum/format/range đầu vào | Request hợp lệ cũ bị từ chối |
| Thêm enum response mới | Consumer có thể fail khi switch exhaustive |
| Thay mã lỗi hoặc ý nghĩa error response | Retry và xử lý UI sai |
| Đổi đơn vị tiền hoặc semantics status | Nguy cơ xử lý sai dù schema hợp lệ |
| Giảm timeout/giới hạn đột ngột | Sự cố runtime dù OpenAPI vẫn hợp lệ |

Một công cụ diff schema có thể không phát hiện thay đổi **ý nghĩa** hoặc lỗi tương thích khi consumer dùng enum khác dự tính. Vì vậy, cần bổ sung behavioral/contract tests mô tả giá trị và bất biến thật, đặc biệt đối với tiền, kho, quyền truy cập và state transition.

## 8. Kiểm thử hợp đồng sự kiện và message bất đồng bộ

API request–response không phải loại hợp đồng duy nhất. Với event-driven, producer phát schema còn consumer xử lý message sau thời điểm producer commit.

Ví dụ event StockReserved v1:

~~~json
{
  "eventId": "evt-9001",
  "eventType": "StockReserved",
  "schemaVersion": 1,
  "orderId": "ord-1001",
  "sku": "A100",
  "quantity": 2,
  "occurredAt": "2026-11-11T09:00:00Z"
}
~~~

Một kiểm thử hợp đồng event nên xác nhận:

- Event type, version và các field bắt buộc có đúng không?
- quantity có nguyên dương, đơn vị và semantics đã được mô tả không?
- Producer chỉ phát StockReserved **sau khi reservation commit** không?
- Consumer cũ có đọc được event từ producer mới trong cửa sổ hỗ trợ không?
- Consumer mới có đọc message cũ còn trong broker/queue/DLQ không?
- Có eventId hoặc business key để dedup và aggregateVersion khi cần ordering không?
- Có thay đổi ý nghĩa field khiến consumer xử lý sai dù parser không lỗi không?
- Tình huống event đến trùng, đến muộn, thiếu hoặc sai thứ tự được xử lý thế nào?

Schema registry cho Avro/Protobuf/JSON Schema có thể thực thi policy compatibility. AsyncAPI mô tả channel/message và quan hệ producer/consumer; nó hữu ích cho tài liệu và thiết lập checks. Tuy nhiên **schema hợp lệ không chứng minh business fact đúng**. Test cần bao quát cả producer behavior và consumer behavior.

### 8.1. Backward, forward, full compatibility

Khái niệm phụ thuộc loại schema và cơ chế reader/writer của công cụ:

- **Backward compatibility** thường nhấn mạnh *consumer/reader mới* có thể đọc dữ liệu viết theo schema cũ.
- **Forward compatibility** thường nhấn mạnh *consumer/reader cũ* có thể đọc dữ liệu viết theo schema mới.
- **Full compatibility** kết hợp cả hai chiều theo định nghĩa của nền tảng.
- Các biến thể **transitive** kiểm tra với nhiều schema version trước đó chứ không chỉ bản liền kề.

Đối với producer mới đang được rollout khi còn consumer cũ, phải kiểm tra chiều **consumer cũ đọc producer mới**. Đối với consumer mới có thể replay event cũ, kiểm tra chiều **consumer mới đọc schema cũ**.

Các tên policy không thay thế việc xác minh trên serializer thật. Tùy Protobuf/Avro/JSON Schema và các công cụ, quy tắc thêm trường bắt buộc, default, enum, null và tên field khác nhau. Test bằng payload mẫu thật thuộc các version cần hỗ trợ.

### 8.2. Thay đổi additive cũng có thể phá semantics

Nếu Inventory thêm warehouseId tùy chọn, parser cũ có thể bỏ qua. Nhưng nếu Ordering bắt buộc biết kho cụ thể để quyết định Shipping, việc bỏ qua warehouseId có thể sinh giao hàng sai kho. Hợp đồng cần mô tả **nghĩa và điều kiện bắt buộc của trường**, không chỉ việc JSON có parse được không.

Nếu cần thay đổi lớn, cân nhắc version mới hoặc event mới với giai đoạn dual-read/dual-publish. Nếu cùng fact phát ở cả v1 và v2, dùng identity chung hoặc quy tắc dedup để consumer không nhân đôi side effect.

## 9. Ma trận version và môi trường triển khai

Một verification result phải gắn với **phiên bản có thể xác định**, thường là commit SHA hoặc artifact digest, không chỉ nhãn latest.

Hãy theo dõi:

- Consumer version đang chạy tại dev/staging/production.
- Provider version đang chạy tại từng environment.
- Contract artifact do consumer version nào công bố.
- Provider version nào đã verify contract nào, với kết quả gì.
- Lịch sử deployment và release theo environment.
- Những version còn được hỗ trợ vì mobile/partner, queue retention hay rollback.

Khi muốn deploy Pricing commit P-42 lên production, release gate phải hỏi: **P-42 có tương thích với Ordering và những consumer khác đang hoặc sắp chạy tại production không?**

Khi muốn deploy Ordering commit O-21, phải hỏi: **O-21 có thể tương tác với Pricing version hiện có không?**

Các nền tảng CDC có thể cung cấp khả năng tương tự “can-I-deploy” dựa trên ma trận verification và records của environment. Nếu không sử dụng công cụ này, team có thể xây policy tương đương bằng registry artifact và CI metadata, nhưng tránh gate chỉ dựa trên một nhánh latest.

### 9.1. Ví dụ ma trận

| Consumer version | Provider version | Kiểm chứng | Ý nghĩa |
| --- | --- | --- | --- |
| Ordering O-20 | Pricing P-40 | PASS | Cặp đang chạy |
| Ordering O-20 | Pricing P-42 | PASS | Có thể rollout Pricing mới |
| Ordering O-21 | Pricing P-40 | PASS | Có thể rollout Ordering trước |
| Ordering O-21 | Pricing P-42 | PASS | Cặp mục tiêu |
| Checkout C-10 | Pricing P-42 | FAIL | Chưa được deploy P-42 nếu C-10 còn được hỗ trợ |
| Partner API client chưa nhận diện | Pricing P-42 | UNKNOWN | Cần đánh giá phạm vi/đường kiểm chứng bổ sung |

**UNKNOWN không nên bị mặc định thành PASS.** Trong đường giao tiếp quan trọng, thiếu verification có thể phải chặn hoặc yêu cầu risk acceptance có người phê duyệt và thời hạn. Nhưng cũng tránh cấu hình gate yêu cầu mọi repo không liên quan đều phải có test đối với một provider không được chúng sử dụng.

## 10. Luồng CI/CD đề xuất

Tách các bước kiểm tra theo nơi phát triển và nơi triển khai.

~~~text
CHANGE / PULL REQUEST
   |
   +-- lint OpenAPI/AsyncAPI/schema
   +-- unit tests và compile
   +-- consumer contract tests -> publish contract artifact
   +-- provider verifies relevant consumer contracts
   +-- schema compatibility diff với bản đang hỗ trợ
   +-- static security checks / dependency checks
   |
   v
BUILD VERSIONED ARTIFACT
   |
   +-- publish immutable image/package
   +-- lưu contract hash và verification metadata
   |
   v
PRE-DEPLOYMENT RELEASE GATE
   |
   +-- xác định các consumer/provider đang có trên target env
   +-- kiểm tra ma trận compatible với candidate version
   +-- kiểm tra migrations, feature flag, rollback window
   |
   v
DEPLOY CANARY / ROLLING UPDATE
   |
   +-- smoke test API/broker/auth/config
   +-- đo lỗi contract runtime và consumer lag
   +-- quyết định tiến tiếp, tắt flag hoặc rollback
   |
   v
RECORD DEPLOYMENT
   |
   +-- ghi artifact digest/version vào registry
   +-- giữ lịch sử version để gate lần sau chính xác
~~~

**Lưu ý:** một hệ thống chỉ chạy unit tests ở PR và smoke test ở staging chưa có kiểm tra hợp đồng tự động thực sự nếu thiếu provider verification và quyết định tương thích với version đang được hỗ trợ.

## 11. Kiểm thử ở pull request của consumer

Khi Ordering đổi code gọi Pricing:

1. Chạy unit tests để biết hành vi nội bộ hợp lệ.
2. Chạy consumer contract tests với các tương tác Pricing mà Ordering thực sự sử dụng.
3. Sinh contract artifact gắn với commit/version của Ordering.
4. Publish contract vào registry với branch/tag/environment metadata phù hợp.
5. Dùng provider verification của version đang hỗ trợ hoặc một workflow được kích hoạt tại Pricing để biết hợp đồng mới có được đáp ứng hay không.
6. Nếu Ordering cần trường mới chưa có trong Pricing production, phải thiết kế fallback, feature flag hoặc triển khai theo pha; không coi mock consumer PASS là bằng chứng deploy an toàn.
7. Trả trạng thái kiểm chứng về PR để reviewer biết breaking change nào được yêu cầu.

Một consumer test cần kiểm tra **cả request tạo ra và logic đọc response**, không chỉ snapshot của JSON response.

Ví dụ mô tả:

~~~text
Ordering gọi GET /v1/prices/A100?currency=VND
Pricing được kỳ vọng trả:
  200 OK
  sku: A100
  amountMinor: integer >= 0
  currency: VND

Ordering phải:
  - đọc amountMinor theo đúng đơn vị nhỏ nhất
  - không tự coi timeout là giá bằng 0
  - xử lý 404/409/5xx theo hợp đồng
~~~

Provider cần verify tương tác do consumer công bố. Nếu contract cho phép price null nhưng business không cho phép, cần sửa hợp đồng trước; không tăng độ “linh hoạt” bằng cách chấp nhận dữ liệu không an toàn.

## 12. Kiểm thử ở pull request của provider

Khi Pricing đổi implementation:

1. Chạy static schema diff so với contract đã publish.
2. Tải các consumer contracts còn được hỗ trợ, kể cả các version vẫn chạy ở production.
3. Dựng provider states có dữ liệu test xác định, tách biệt, không dùng production.
4. Verify provider implementation thực với mỗi interaction.
5. Công bố verification result gắn với chính commit/image candidate.
6. Kiểm tra behavioral expectations không nằm trong OpenAPI: nghĩa của amount, currency, status và exception.
7. Nếu fail, chặn merge/release theo policy hoặc tạo giai đoạn compatibility có chủ đích.
8. Nếu consumer từ bên ngoài chưa có contract, dùng public API compatibility policies và smoke test client đại diện.

Provider verification không nên chỉ lấy hợp đồng từ nhánh main mới nhất của consumer. Bản consumer thực tế đang chạy có thể cũ hơn và chỉ nó mới quyết định rollout có an toàn hay không.

## 13. Một ví dụ test provider với Java

Để minh họa tư duy, một test HTTP dùng JUnit và REST Assured có thể kiểm tra các ràng buộc provider. Mã giả định test environment đã chạy Pricing API tại port 8080; dependencies và test setup cần được cấu hình trong dự án.

~~~java
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.*;

import org.junit.jupiter.api.Test;

class PricingContractSmokeTest {

    @Test
    void knownSkuProvidesRequiredFields() {
        given()
            .port(8080)
            .queryParam("currency", "VND")
        .when()
            .get("/v1/prices/{sku}", "A100")
        .then()
            .statusCode(200)
            .body("sku", equalTo("A100"))
            .body("amountMinor", anInstanceOf(Number.class))
            .body("amountMinor", greaterThanOrEqualTo(0))
            .body("currency", equalTo("VND"));
    }
}
~~~

Đoạn test này giúp kiểm tra một hành vi provider trong môi trường test, **chưa tự trở thành CDC đầy đủ** nếu không có artifact consumer expectation và ma trận version. Trong hệ thống thực, dữ liệu A100 phải do test fixture/provider state chuẩn bị để kết quả deterministic.

Đối với security contract, thêm trường hợp không có token, token không đủ quyền, token hết hạn; không chỉ kiểm tra happy path của một user có mọi quyền.

## 14. Mẫu hợp đồng sự kiện và kiểm thử consumer

Ví dụ message OrderPlaced:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "aggregateId": "ord-1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-11T09:21:15Z",
  "payload": {
    "orderId": "ord-1001",
    "totalMinor": 159900,
    "currency": "VND"
  }
}
~~~

Consumer Notifications có thể chỉ cần orderId và eventId để tạo job gửi email, trong khi Analytics cần totalMinor và currency để tính báo cáo. Không nên bắt Notifications phụ thuộc mọi field nội bộ của Order.

Các nhóm kiểm thử:

- **Schema:** eventId, eventType, schemaVersion, payload.orderId đúng kiểu.
- **Consumer decoding:** thêm optional field không làm parser cũ crash nếu hợp đồng hứa bỏ qua unknown fields.
- **Semantic:** totalMinor vẫn có nghĩa như đã công bố; số âm không hợp lệ nếu nghiệp vụ yêu cầu không âm.
- **Delivery:** cùng eventId hai lần không tạo hai job gửi email.
- **Ordering:** event version cũ không ghi đè trạng thái mới.
- **Retention/replay:** consumer mới đọc được event cũ cần hỗ trợ.
- **Producer timing:** OrderPlaced chỉ được phát sau transaction tạo Order thành công.

Với consumer chạy song song version cũ/mới trong rolling deployment, test bằng cả payload từ producer cũ lẫn mới. Không giả định schema registry kiểm tra được idempotency hay thời điểm commit business fact.

## 15. Release gate: điều kiện cho phép triển khai

Một gate tốt có **đầu vào cụ thể, trạng thái rõ ràng và hành động xác định**.

Đầu vào:

- Artifact candidate có digest/commit SHA.
- Danh sách contracts do candidate cung cấp hoặc tiêu thụ.
- Đích triển khai: staging, production hoặc một region cụ thể.
- Inventory phiên bản đang hoạt động của consumer/provider liên quan.
- Verification result và schema compatibility status mới nhất cho từng version.
- Chính sách phạm vi hỗ trợ và exception/risk acceptance.

Đầu ra có thể là:

| Gate status | Ý nghĩa | Hành động |
| --- | --- | --- |
| PASS | Mọi cặp version bắt buộc đã có bằng chứng tương thích | Có thể chuyển bước tiếp |
| FAIL | Có breaking change hoặc test vi phạm contract | Chặn release; sửa hoặc chuyển sang migration nhiều pha |
| UNKNOWN | Thiếu mapping/version/verification cần thiết | Chặn với luồng quan trọng; triage thiếu dữ liệu |
| WAIVED | Có phê duyệt ngoại lệ có hạn, có kế hoạch giảm rủi ro | Cho phép theo chính sách, lưu audit |
| NOT_APPLICABLE | Artifact không tham gia đường hợp đồng trong phạm vi gate | Không tạo chặn giả |

Không nên cho phép FAIL biến thành PASS chỉ vì test suite bị skip, timeout hoặc registry không truy cập được. **Test không chạy không phải là test đã qua.** Các tình huống hạ tầng như registry tạm lỗi có thể được retry theo ngân sách, sau đó báo UNKNOWN cùng lý do.

### 15.1. Chính sách ưu tiên theo rủi ro

Với Payments hoặc nghiệp vụ tồn kho, thiếu contract verification có thể là chặn cứng. Với analytics nội bộ ít tác động, tổ chức có thể chấp nhận triển khai canary kèm owner và rollback. Chính sách phải được ghi rõ trước, không quyết định tùy tiện lúc có deadline.

Nguyên tắc là minh bạch: ai cho ngoại lệ, vì sao, phạm vi environment nào, kéo dài đến bao giờ, ai chịu trách nhiệm khôi phục contract coverage.

## 16. Ví dụ pipeline dạng khung

Cú pháp bên dưới là **khung quy trình minh họa**, không phải file pipeline chạy ngay. Command thực tế tùy build tool, Pact CLI/provider plugin, registry, broker và CI đã chọn.

~~~yaml
stages:
  - validate
  - contract
  - build
  - release-gate
  - deploy
  - verify

validate:
  script:
    - ./gradlew test
    - ./scripts/lint-api-schema.sh
    - ./scripts/check-api-compatibility.sh

contract:
  script:
    - ./gradlew contractTest
    - ./scripts/publish-contract-artifacts.sh
    - ./scripts/verify-provider-contracts.sh
    - ./scripts/publish-verification-results.sh

build:
  script:
    - ./scripts/build-versioned-artifact.sh

release-gate:
  script:
    - ./scripts/can-deploy-to-target-environment.sh

deploy:
  script:
    - ./scripts/deploy-canary.sh

verify:
  script:
    - ./scripts/smoke-and-observe.sh
    - ./scripts/record-successful-deployment.sh
~~~

Phân tách stage giúp dễ chẩn đoán:

- Validate fail: lỗi cấu trúc, lint, unit test.
- Contract fail: provider không còn đáp ứng một interaction, event break hoặc migration không tương thích.
- Release gate fail: candidate chưa được chứng minh tương thích với version tại environment đích.
- Deploy fail: lỗi cấu hình, secret, networking, artifact hoặc tài nguyên.
- Verify fail: hệ thống thực tế lỗi contract runtime hay metrics xấu dù test trước đã qua.

Không gắn release gate với latest main thay vì artifact đã build. Tránh tình trạng PR kiểm chứng commit A nhưng pipeline lại deploy artifact B.

## 17. Sử dụng Pact Broker hoặc registry tương đương

Một workflow CDC thường cần lưu:

1. Consumer contract được publish theo version/branch.
2. Provider verification result cho version provider.
3. Deployment/release record cho các version tại từng environment.
4. Quyết định can-deploy đối với candidate và môi trường đích.

Ví dụ các **lệnh minh họa** (tham số có thể khác theo Pact CLI phiên bản triển khai):

~~~bash
# Consumer công bố contract gắn với version build
pact-broker publish ./pacts --consumer-app-version "$GIT_SHA"

# Trước deployment, kiểm tra candidate có thể tương thích
# với ứng dụng đang hoạt động ở môi trường đích.
pact-broker can-i-deploy \
  --pacticipant pricing \
  --version "$GIT_SHA" \
  --to-environment production

# Sau khi deployment thành công, cập nhật thông tin version thực tế.
pact-broker record-deployment \
  --pacticipant pricing \
  --version "$GIT_SHA" \
  --environment production
~~~

Các lệnh này **không thay thế** việc cài đặt provider verification và publish kết quả. Một registry không biết consumer version đang chạy sẽ không tự suy ra được target matrix. Cần thiết lập authentication/permissions, version naming ổn định và quy trình ghi deployment thành công.

Nếu không dùng Pact Broker, có thể áp dụng cùng ý tưởng qua contract artifacts trong artifact registry, manifest environment và job kiểm tra ma trận, nhưng phải tránh kết quả verification không có provenance.

### 17.1. Kiểm tra theo environment, không chỉ theo branch

Một consumer có thể đang chạy trên production từ release ba tuần trước dù main đã đổi. Bản contract cần bảo vệ là của **consumer thực tế đang chạy và còn được hỗ trợ**. Đồng thời staging/production có thể khác version trong thời gian rollout.

CI có thể kiểm tra candidate với phiên bản “đang hoạt động hoặc chuẩn bị deploy” thay vì mọi commit lịch sử. Phạm vi đúng cần gồm rollback window và các deployment region nếu chúng có thể tương tác.

## 18. Kiểm tra database/schema compatibility cũng là một phần release safety

Contract testing liên service không tự bảo vệ migration database. Nếu hai service cùng truy cập bảng Orders hoặc ứng dụng mới và cũ cùng chạy trên một schema, release có thể hỏng dù OpenAPI vẫn tương thích.

Ví dụ cần thêm shippingCountryCode:

~~~sql
-- Expand: thêm cột mới, không xóa cột cũ ngay
ALTER TABLE orders
ADD COLUMN shipping_country_code VARCHAR(2) NULL;

-- Migrate/backfill: thực hiện từng lô có checkpoint
-- Contract: chỉ drop field cũ sau khi không còn consumer/code cũ
~~~

Các checks nên có:

- Migrations chạy được trên schema đại diện của môi trường đích.
- Old application vẫn hoạt động sau migration expand.
- New application đọc được dữ liệu cũ hoặc có fallback/backfill.
- Dual-write (nếu dùng) không gây sai lệch hoặc có cơ chế reconcile.
- Không drop/rename sớm cột mà code đang chạy còn sử dụng.
- Rollback code có xử lý dữ liệu do version mới ghi không?
- Migration dài không lock bảng gây downtime vượt SLA.

Cần thêm test theo các tổ hợp **old app/new schema**, **new app/old schema khi rollout yêu cầu**, **new app/new schema**. Các migration nguy hiểm vẫn có thể cần kế hoạch riêng và bước vận hành được phê duyệt.

## 19. Phân biệt breaking change do cú pháp và do nghiệp vụ

Các công cụ diff phát hiện đổi kiểu field, remove endpoint, required property, Protobuf field number, v.v. Nhưng nhiều lỗi gây thiệt hại không đổi hình dạng dữ liệu:

- Pricing giữ trường amountMinor nhưng chuyển nghĩa từ giá cuối sang giá trước discount.
- Payments giữ status PAID nhưng giờ chỉ là authorized, chưa capture.
- Inventory vẫn phát StockReserved nhưng không bảo đảm thời hạn reservation như trước.
- API vẫn trả 200 với field total nhưng đổi rounding mode khiến tổng tiền khác.
- Error response vẫn là 409 nhưng client được hướng dẫn retry vô hạn.
- Event vẫn là CustomerDeleted nhưng thực tế chỉ đánh dấu inactive.
- Timezone của timestamp không còn là UTC dù schema string date-time không đổi.

Bảo vệ những tình huống này bằng **behavioral examples**, property tests và invariant tests trong hợp đồng. Dùng fixture có ý nghĩa (đơn có giảm giá, rounding, hết hạn, quyền truy cập, conflict đồng thời), không chỉ ví dụ happy path dữ liệu trống.

Ví dụ hợp đồng nghiệp vụ:

~~~text
Given:
  một đơn có hai sản phẩm và mã giảm giá hợp lệ
When:
  Ordering yêu cầu Pricing tính tổng
Then:
  totalMinor = sum(lineSubtotal) - allowedDiscountMinor + taxMinor
  currency = VND
  totalMinor >= 0
  mọi khoản tiền dùng đơn vị nhỏ nhất và quy tắc rounding đã công bố
~~~

Công thức là ví dụ cho một chính sách cụ thể; business rule thật phải được owner mô tả bằng contract đang áp dụng, không mặc định phù hợp mọi tổ chức.

## 20. Kiểm tra khả năng rollback và rolling deployment

Release gate không chỉ bảo vệ đi lên phiên bản mới; rollback cũng cần tương thích:

1. New producer có tạo dữ liệu/event mà old consumer còn đọc được không?
2. New consumer có đọc được event cũ đang tồn tại trong broker không?
3. Old application có chạy được trên schema đã expand/backfill không?
4. Feature flag có thể tắt hành vi mới mà không mất dữ liệu không?
5. Các event phát ra trong quá trình canary có làm consumer cũ crash không?
6. Nếu rollback candidate, registry ghi lại version đang deployed đúng không?
7. Multi-region có thời gian tồn tại của phiên bản cũ dài hơn một deployment đơn vùng không?
8. Mobile/third-party clients có thể còn ở v1 trong vài tháng không?

Ví dụ triển khai an toàn đổi response từ amountMinor sang price object:

~~~text
T0: Pricing v1 (trả amountMinor)
T1: Pricing v1.1 (trả cả amountMinor và price)
T2: Ordering v2 (đọc price, fallback amountMinor)
T3: Pricing v2 (ngừng field cũ sau thời hạn hỗ trợ)
~~~

Mỗi thời điểm phải có contract tests và gate tương ứng. Không bắt buộc mọi service deploy cùng đêm nếu có **trạng thái trung gian tương thích**.

## 21. Hợp đồng với third-party và mobile client

Trong microservices nội bộ, có thể biết phần lớn consumer version. Nhưng public API, mobile và đối tác có thể không publish CDC artifact:

- Giữ chính sách backward compatibility công khai.
- Version endpoint/protocol khi thay đổi không tương thích.
- Theo dõi usage theo client version, API key hoặc capability khi phù hợp và tôn trọng quyền riêng tư.
- Công bố deprecation, sunset, migration guide và thời hạn hỗ trợ.
- Chạy synthetic tests đại diện cho client cũ.
- Không drop v1 chỉ vì nội bộ tất cả service đã nâng cấp.
- Nếu có client không thể kiểm soát version, có thể cần duy trì adapter/translation layer lâu hơn.

**Thiếu contract của đối tác không có nghĩa đối tác không tồn tại.** Release inventory phải mô tả phạm vi bảo vệ và các lỗ hổng coverage.

## 22. Security contract trong CI/CD

Tương thích không chỉ về dữ liệu mà còn về quyền:

- Bỏ yêu cầu auth có thể làm lộ API.
- Thêm yêu cầu scope mới có thể khiến consumer cũ bị 403.
- Thay audience/token claim hoặc mTLS identity có thể chặn kết nối.
- Event topic đổi ACL khiến consumer không đọc được.
- Message có thêm PII không cần thiết khiến vi phạm dữ liệu dù schema vẫn đúng.

Kiểm thử hợp đồng security nên có cả positive và negative cases: thiếu token, token sai quyền, dữ liệu tenant khác, expired credential, giới hạn truy cập destination. Kiểm tra secrets, TLS và network policies tại staging/canary theo mô hình của hạ tầng.

Không đưa secrets thật vào Pact files, sample payloads hay CI logs; contract artifacts có thể được chia sẻ rộng hơn source code dịch vụ.

## 23. Kiểm tra sau triển khai

Dù pre-deployment gate PASS, môi trường thật vẫn có thể lỗi vì configuration drift, security rules, routing, service discovery, broker ACL, schema registry hoặc rollout sai version.

Sau deployment:

1. Kiểm tra artifact digest/commit đúng candidate đã được verify.
2. Chạy smoke test cho endpoint/destination quan trọng ở environment đích.
3. Kiểm tra status code, response schema và semantics đại diện.
4. Theo dõi deserialization errors, enum unknown, missing fields và contract violations.
5. Theo dõi consumer lag, DLQ, retry rate, outbox backlog và API 4xx/5xx theo version.
6. Quan sát tỷ lệ business rejection bất thường, ví dụ PaymentDeclined tăng do sai contract.
7. Canary theo cohort/traffic với ngưỡng dừng rõ.
8. Nếu lỗi, tắt feature hoặc rollback/roll forward theo chính sách và cập nhật deployment registry.
9. Ghi kết quả cùng incident/verification evidence để cải thiện test coverage.

**PASS trước deployment là bằng chứng có giới hạn, không phải bảo đảm hệ thống không gặp bất kỳ sự cố nào.** Smoke/canary giúp kiểm tra phần cấu hình và vận hành mà mock contract không thể mô phỏng hết.

## 24. Tổ chức hợp đồng trong repository

Một cấu trúc minh họa:

~~~text
pricing-service/
  src/
    main/
    test/
      contract/
      integration/
  api/
    openapi.yaml
    examples/
      quote-success.json
      quote-not-found.json
  scripts/
    check-api-compatibility.sh
    publish-verification.sh
  .ci/
    contract-check.yml

ordering-service/
  src/
    main/
    test/
      consumer-contract/
      integration/
  contracts/
    pricing-consumer/
  .ci/
    contract-check.yml

contracts-registry/
  immutable artifacts, versions, environment metadata
~~~

Có thể dùng monorepo hoặc multi-repo. Điều quan trọng là contract có **đường sở hữu rõ, có version, có automation và không chỉnh tay artifact đã dùng để verify**. OpenAPI, schema và generated client phải đồng bộ với implementation, tránh tài liệu đẹp nhưng runtime khác.

Contract fixtures nên độc lập, deterministic, không trỏ vào dữ liệu production. API examples cần tránh thông tin khách hàng thật.

## 25. Chỉ số để biết release gate có hiệu quả

Đo ít nhất:

| Metric | Mục đích |
| --- | --- |
| Contract coverage | Bao nhiêu integration quan trọng có contract + provider verification |
| Breaking changes caught pre-prod | Có phát hiện vi phạm trước khi release hay không |
| Verification freshness | Kết quả gắn với artifact/commit gần nhất hay đã cũ |
| Unknown gate rate | Bao nhiêu release thiếu version mapping hoặc hợp đồng |
| Compatibility incidents | Sự cố production do API/event/schema mismatch |
| Deploy independence | Số thay đổi có thể phát hành không buộc service khác deploy đồng thời |
| Mean time to diagnose | Xác định đúng provider/consumer/contract khi fail mất bao lâu |
| Deprecated contract debt | Hợp đồng/adapter v1 còn tồn tại quá hạn |
| Waiver count/age | Ngoại lệ nào chưa được xử lý dứt điểm |
| Consumer lag / DLQ after deploy | Event consumers có bị lỗi khi producer mới xuất hiện không |

Đừng đặt mục tiêu chỉ là “100% test PASS” nếu test không gắn với version thực tế hoặc phạm vi hợp đồng quan trọng còn thiếu.

## 26. Các lỗi thường gặp khi tự động hóa

### 26.1. Consumer dùng mock rồi tuyên bố toàn hệ thống tương thích

Mock có thể phản hồi bất kỳ dữ liệu nào do test đặt ra. Nếu provider thật không verify tương tác, không có bằng chứng tích hợp. Cần publish consumer contract và provider chạy verification trên implementation thật.

### 26.2. Chỉ kiểm tra main với main

Production có thể chạy consumer từ nhiều commit cũ. Gate phải kiểm tra candidate với các version thực tế của target environment và rollback window.

### 26.3. Chỉ chạy schema diff

Schema không phát hiện thay đổi rounding, currency semantics, state transition hoặc authorization. Cần behavioral cases và integration tests.

### 26.4. Cho kết quả UNKNOWN mặc định qua

Registry lỗi, artifact không tìm được hoặc provider verification chưa chạy không phải PASS. Cần chính sách UNKNOWN rõ; với integration quan trọng nên fail-closed có phân loại lỗi và cách khắc phục.

### 26.5. Contract quá chi tiết và gắn với nội bộ provider

Consumer assertions toàn bộ response gồm field không sử dụng khiến mọi thay đổi nhỏ trở thành breaking change. CDC nên khẳng định các field/semantics consumer thực sự cần, nhưng không nới lỏng các quy tắc an toàn cốt lõi.

### 26.6. Không version contract artifacts

Một file pact hoặc OpenAPI bị overwrite dưới tên latest khiến test result không chứng minh artifact đang deploy. Lưu immutable version/commit và verification matrix.

### 26.7. Bỏ test bất đồng bộ

API hợp lệ nhưng event đổi schema hoặc event mới đến consumer cũ gây DLQ. Phải kiểm tra producer message, consumer decoding, redelivery và compatibility.

### 26.8. Coi schema registry là hệ thống kiểm chứng toàn bộ nghiệp vụ

Registry giúp phát hiện thay đổi schema theo policy, không biết event được phát trước commit hoặc business amount bị đổi nghĩa. Thêm test owner, outbox và semantics.

### 26.9. Không ghi nhận deployment thực tế

Registry vẫn tưởng production đang chạy P-40 trong khi đã deploy P-42, nên lần gate tiếp có thể ra kết luận sai. Record deployment/release thành công và rollback, kèm nguồn version đáng tin cậy.

### 26.10. Bỏ qua contract khi cleanup

Sau khi feature flag chuyển xong, team xóa field cũ quá sớm; mobile hoặc queue backlog còn dữ liệu cũ. Cần deprecation window, quan sát traffic và khả năng replay.

### 26.11. Biến contract testing thành release train

Gate chặn chỉ vì một repo không liên quan chưa deploy; team bèn deploy mọi service cùng nhau. Điều này đi ngược mục tiêu độc lập. Chỉ yêu cầu compatibility của các cặp có giao tiếp và có thể đồng tồn tại.

### 26.12. Không có owner khi verification FAIL

Pipeline báo FAIL nhưng không nêu contract nào, consumer nào, case nào và phương án migration. Kết quả phải cho developer thấy diff, request/response case, source artifact và nơi sửa.

## 27. Bài thực hành: đổi API Pricing mà không phát hành đồng bộ

Hiện trạng:

- Pricing v1 trả amountMinor và currency.
- Ordering v1 đọc hai field trên.
- Checkout v1 dùng amountMinor để hiển thị.
- Payments đọc số tiền đã chốt trong Order; không gọi Pricing trực tiếp.

Yêu cầu mới: Pricing phải trả object price chứa amountMinor, currency, taxIncluded, cùng discountBreakdown. Team muốn bỏ amountMinor top-level ngay.

### Nhiệm vụ

1. Liệt kê owner, consumer và các hợp đồng thực tế.
2. Vẽ ma trận old/new của Ordering, Checkout với Pricing.
3. Viết một consumer interaction cho Ordering đọc quote.
4. Viết một provider verification case cho Pricing giữ amountMinor tương thích.
5. Đề xuất cách kiểm tra OpenAPI diff và behavior khi đổi nghĩa taxIncluded.
6. Xác định điều kiện release gate khi Ordering v1 và Checkout v1 vẫn còn ở production.
7. Viết kế hoạch expand/migrate/contract không ép các service deploy cùng giờ.
8. Đề xuất dữ liệu mẫu gồm giảm giá, thuế, currency, rounding và lỗi pricing unavailable.
9. Định nghĩa ai quyết định có thể drop field cũ; dựa trên bằng chứng nào.
10. Nêu ba metric cần giám sát sau canary Pricing v2.

### Một phương án an toàn

~~~text
Pha 1: Pricing v1.1
  - giữ amountMinor + currency ở top-level
  - thêm price và discountBreakdown
  - xác minh consumer contracts của Ordering v1, Checkout v1
  - deploy Pricing v1.1

Pha 2: Ordering v2, Checkout v2
  - đọc price nếu có, fallback field cũ theo cửa sổ cần hỗ trợ
  - publish consumer contract mới
  - provider verification PASS cả old/new
  - triển khai theo thời gian riêng

Pha 3: ngừng v1
  - xác nhận không còn consumer sử dụng field cũ
  - xác nhận traffic/version/rollback window
  - kiểm tra schema diff và verification cho phạm vi còn hỗ trợ
  - mới bỏ field cũ hoặc chuyển sang endpoint/version mới
~~~

Bằng chứng cần có: test result gắn với artifact, môi trường thực tế, consumer versions và quan sát runtime. Chỉ có lời xác nhận “team Checkout đã merge code” là chưa đủ vì code merge có thể chưa deployed.

## 28. Checklist đưa vào Definition of Done

Trước khi approve một thay đổi ở service boundary:

1. **Owner:** Có provider/producer owner và danh sách consumer liên quan.
2. **Contract source:** OpenAPI/Proto/AsyncAPI/schema được version hóa.
3. **Change classification:** Đã chỉ ra additive/breaking và semantic impact.
4. **Consumer expectations:** Test có những interaction/field consumer thực sự dùng.
5. **Provider verification:** Implementation mới đã verify contract đang hỗ trợ.
6. **Async compatibility:** Event cũ/mới, consumer cũ/mới và queue retention được kiểm tra.
7. **Behavior:** Cases cho currency, error, state transition, permission, idempotency.
8. **Version identity:** Kết quả gắn commit/image digest không thể nhầm.
9. **Deployment inventory:** Biết version hiện hữu ở môi trường đích.
10. **Release gate:** PASS/FAIL/UNKNOWN/WAIVED với lý do tường minh.
11. **Rollout:** Có kế hoạch mixed-version, canary, feature flag khi cần.
12. **Database:** Migrations được chia pha tương thích với old/new code.
13. **Rollback:** Đã xác định phiên bản nào có thể trở lại an toàn.
14. **Post-deploy:** Có smoke test và metric contract violations.
15. **Deprecation:** Có owner, deadline và bằng chứng để xóa hợp đồng cũ.
16. **Observability:** Log/trace có correlation ID nhưng không lộ dữ liệu nhạy cảm.
17. **Documentation:** Changelog, migration guide và hướng xử lý FAIL được cập nhật.
18. **Recovery:** Nếu registry unavailable hay consumer lag tăng, ai quyết định tiếp tục/dừng?

---

**Nguyên tắc cần ghi nhớ:** Kiểm tra hợp đồng tự động hiệu quả không dừng ở việc “file OpenAPI đúng schema” hay “Pact test xanh”. Nó phải nối **kỳ vọng consumer → verification của provider → version/artifact thực tế → quyết định release → quan sát production**. Khi quy trình này bao phủ các tổ hợp phiên bản có thể đồng tồn tại, microservices mới có cơ sở triển khai độc lập mà không đánh đổi tính đúng đắn nghiệp vụ.