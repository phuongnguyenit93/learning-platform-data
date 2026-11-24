# Bài tập thiết kế chiến lược kiểm thử cho hệ thống nhiều dịch vụ

## Mục tiêu bài tập

Bài tập này yêu cầu thiết kế một **chiến lược kiểm thử có thể triển khai** cho hệ thống nhiều dịch vụ sử dụng HTTP và messaging. Bạn sẽ vận dụng **Spring Cloud Contract** để kiểm tra thỏa thuận giữa producer và consumer, sau đó xác định phần nào cần integration test và phần nào cần end-to-end (E2E) test.

Nhiệm vụ không phải liệt kê thật nhiều test, mà là chọn **đúng loại test cho từng rủi ro**, nêu rõ dependency nào phải chạy thật, dependency nào có thể dùng stub, test chạy ở giai đoạn CI nào và bằng chứng nào đủ để cho phép release.

Sau bài, bạn có thể:

- Đọc kiến trúc nhiều dịch vụ và xác định provider-consumer boundaries.
- Phân loại yêu cầu thành contract, integration, E2E hoặc unit test.
- Xác định contract nào nên dùng Groovy/YAML DSL và Stub Runner.
- Thiết kế producer verification và consumer-side stub tests.
- Chọn database, broker, gateway và service thật cho integration/E2E.
- Xác định invariant nghiệp vụ xuyên nhiều dịch vụ.
- Thiết kế test data, correlation ID, isolation và cách chờ eventual consistency.
- Sắp xếp test vào PR, main branch, nightly và pre-release pipeline.
- Giải thích lý do không dùng E2E cho mọi biến thể API.
- Đưa ra kế hoạch kiểm thử có coverage, owner, môi trường và release gates.

> **Nguyên tắc lựa chọn:** bắt đầu từ business risk và invariant cần bảo vệ. Chọn tầng kiểm thử nhỏ nhất có thể chứng minh rủi ro đó; mở rộng sang integration/E2E khi cần các thành phần thật phối hợp.

## 1. Bối cảnh hệ thống: Marketplace Checkout

Bạn là thành viên nhóm nền tảng hỗ trợ một marketplace. Nhóm chuẩn bị phát hành phiên bản mới của luồng checkout. Hệ thống có nhiều service độc lập, mỗi service có database riêng và giao tiếp qua HTTP hoặc Kafka.

| Thành phần | Trách nhiệm | Giao tiếp |
|---|---|---|
| **API Gateway** | Entry point, authentication, routing, rate limit | HTTP |
| **Checkout Service** | Điều phối quy trình checkout và trạng thái checkout | HTTP, Kafka |
| **Inventory Service** | Giữ hàng, giải phóng reservation, quản lý tồn kho | HTTP, Kafka |
| **Payment Service** | Authorize/capture/refund payment | HTTP |
| **Order Service** | Tạo order, quản lý trạng thái đơn | Kafka, HTTP query |
| **Notification Service** | Gửi email/SMS khi order có trạng thái phù hợp | Kafka |
| **Kafka** | Truyền event giữa các service | Topics |
| **PostgreSQL** | Database riêng cho từng service | JDBC |

### Sơ đồ kiến trúc

~~~mermaid
flowchart LR
    U["Web / Mobile client"] --> G["API Gateway"]
    G --> C["Checkout Service"]
    C -->|HTTP reserve/release| I["Inventory Service"]
    C -->|HTTP authorize/capture| P["Payment Service"]
    C -->|Checkout events| K[("Kafka")]
    I -->|Stock events| K
    P -->|Payment events| K
    K --> O["Order Service"]
    O -->|OrderConfirmed| K
    K --> N["Notification Service"]
    C --- DC[("Checkout DB")]
    I --- DI[("Inventory DB")]
    P --- DP[("Payment DB")]
    O --- DO[("Order DB")]
~~~

Sơ đồ thể hiện các luồng chính để thiết kế test. Triển khai thực tế có thể có thêm outbox publisher, schema registry, service discovery hoặc external payment provider.

### Luồng checkout thành công

1. Client gửi request qua Gateway.
2. Gateway xác thực identity và chuyển request tới Checkout.
3. Checkout yêu cầu Inventory giữ hàng.
4. Inventory tạo reservation và trả reservation ID.
5. Checkout yêu cầu Payment authorize/capture.
6. Checkout ghi nhận kết quả và phát event phù hợp.
7. Order Service nhận event, tạo/cập nhật order.
8. Order Service phát event OrderConfirmed.
9. Notification Service nhận event và gửi thông báo.

### Luồng thanh toán thất bại

1. Checkout đã giữ hàng thành công.
2. Payment từ chối hoặc timeout.
3. Checkout yêu cầu Inventory giải phóng reservation.
4. Checkout đánh dấu checkout thất bại hoặc trạng thái cần reconcile.
5. Order không được chuyển sang CONFIRMED.
6. Không gửi email xác nhận đơn hàng thành công.

Luồng này có thể dùng Saga/compensation hoặc orchestration state machine. Bài tập không áp đặt implementation cụ thể; bạn phải xác định behavior nào cần kiểm tra.

## 2. Yêu cầu nghiệp vụ và invariant

Trước khi chọn test, hãy viết ra các quy tắc mà hệ thống phải giữ. Đây là căn cứ để quyết định test nào cần component thật.

### Invariant của checkout

- Một checkout thành công phải có reservation hợp lệ.
- Không xác nhận order nếu payment chưa được capture/authorized theo chính sách.
- Payment thất bại phải dẫn tới release reservation hoặc trạng thái compensation có thể theo dõi.
- Một request có cùng idempotency key không được tạo hai khoản thanh toán.
- Duplicate event không được tạo duplicate order hoặc duplicate notification.
- orderId, checkoutId và correlation ID phải được giữ xuyên qua các service.
- Trạng thái cuối phải hội tụ dù event đến trễ hoặc được retry.
- Checkout đã bị hủy không được chuyển ngược thành confirmed do event cũ.

### Invariant của Inventory

- Reservation không được làm lượng hàng khả dụng âm.
- Không thể giữ nhiều hơn số lượng có thể bán.
- Release reservation chỉ tác động đúng reservation tương ứng.
- Lặp lại cùng release request phải có behavior idempotent đã xác định.
- Reservation hết hạn không được coi là active.

### Invariant của Payment

- Một idempotency key không được capture hai lần.
- Payment declined không được ghi nhận là captured.
- Refund phải tham chiếu đúng payment/order.
- Timeout không đồng nghĩa payment chắc chắn thất bại; cần trạng thái có thể reconcile.

### Invariant của Order và Notification

- Order chỉ confirmed sau khi điều kiện nghiệp vụ được thỏa mãn.
- Event duplicate hoặc out-of-order không làm trạng thái lùi sai.
- Notification thành công chỉ gửi cho trạng thái được phép.
- Notification retry không tạo duplicate message cho người dùng nếu yêu cầu chống trùng.

**Bài học:** HTTP contract kiểm tra status/body và event contract kiểm tra payload/header; transaction, idempotency, concurrency và hội tụ trạng thái cần integration test hoặc workflow test phù hợp.

## 3. Xác định provider-consumer boundaries

Hãy liệt kê từng tương tác và ghi ai là producer, ai là consumer. Vai trò thay đổi theo chiều dữ liệu.

| Boundary | Producer | Consumer | Hình thức | Contract nên bảo vệ |
|---|---|---|---|---|
| Reserve inventory | Inventory | Checkout | HTTP | Request, status, reservation ID, state |
| Release inventory | Inventory | Checkout | HTTP | Idempotency, not found, released state |
| Authorize payment | Payment | Checkout | HTTP | Payment ID, status, decline/error |
| Capture payment | Payment | Checkout | HTTP | Idempotency, amount, captured state |
| Checkout submitted | Checkout | Order | Kafka event | Event type, ID, checkout/order references |
| Stock reserved | Inventory | Checkout/Order nếu subscribe | Kafka event | Schema, headers, correlation |
| Payment captured | Payment | Order/Checkout nếu subscribe | Kafka event | Payment state/reference |
| Order confirmed | Order | Notification | Kafka event | Order ID, recipient reference, event version |

### Contract không cần tồn tại cho mọi internal method

Chỉ tạo contract ở **boundary được nhiều component/service tiêu thụ hoặc cần compatibility độc lập**. Không cần phát hành contract cho mọi method private hoặc từng repository call.

Với mỗi boundary, trả lời:

1. Có consumer độc lập cần biết behavior này không?
2. Consumer và producer có thể deploy khác thời điểm không?
3. Thay đổi schema/path/status có thể phá consumer không?
4. Có error/edge case nào consumer phụ thuộc không?
5. Có message versioning hoặc backward compatibility requirement không?

Nếu câu trả lời chủ yếu là không, unit/integration test nội bộ có thể phù hợp hơn.

## 4. Phân rã test strategy theo rủi ro

| Tầng | Mục tiêu | Ví dụ trong Marketplace |
|---|---|---|
| **Unit** | Business rule thuần, nhanh và cô lập | Tính tổng tiền, xác định eligibility |
| **Contract** | Producer/consumer giữ đúng HTTP/message agreement | Inventory reservation, Payment response, OrderConfirmed event |
| **Integration** | Component thật phối hợp với DB/broker/security/web stack | Transaction/outbox, Kafka ack, DB locking |
| **E2E** | Workflow nghiệp vụ xuyên gateway và nhiều service | Checkout thành công, payment declined + compensation |

Không chọn tầng chỉ vì test đang dễ viết:

- Mock repository để test SQL constraint là sai tầng.
- Dùng Stub Runner để tuyên bố broker delivery đã được xác minh là sai phạm vi.
- Dùng E2E để kiểm tra 50 kiểu validation JSON làm suite chậm và khó chẩn đoán.
- Dùng integration test một service để tuyên bố gateway route và service discovery hoạt động là thiếu bằng chứng.

### Ma trận quyết định cho hệ thống này

| Rủi ro | Unit | Contract | Integration | E2E |
|---|---:|---:|---:|---:|
| Sai business calculation | **Chính** | Có thể | Ít cần | Một số luồng |
| Inventory response schema đổi | Không đủ | **Chính** | Có thể | Không phải đầu tiên |
| Payment client parse declined response | Có thể | **Chính** | Có thể | Có thể |
| DB reservation transaction rollback | Không đủ | Không đủ | **Chính** | Khó chẩn đoán |
| Oversell do concurrency | Không đủ | Không đủ | **Chính** | Một số journey |
| Kafka serialization/delivery/ack | Không đủ | Schema contract | **Chính** | Khi workflow cần |
| Gateway auth/routing | Không đủ | Một phần | Gateway integration | **Chính** cho journey |
| Saga compensation | Unit cho state machine | Contract cho boundary | Integration theo service | **Chính** cho workflow |
| Duplicate notification | Unit/idempotency logic | Event contract | Messaging integration | E2E đại diện |

## 5. Chọn contract để triển khai với Spring Cloud Contract

Bài tập chọn ba contract đại diện: Inventory HTTP, Payment HTTP và Order message.

### Contract A — Inventory reservation HTTP

Inventory là producer, Checkout là consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout can reserve two units of SKU-101'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            quantity: 2
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RSV-1001',
            status: 'ACTIVE'
        )
    }
}
~~~

Contract bảo vệ method/path, request JSON và response thành công. Một contract riêng nên mô tả insufficient stock, unknown SKU hoặc idempotent retry nếu đó là behavior consumer cần dựa vào.

### Contract B — Payment decline HTTP

Payment là producer, Checkout là consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Payment provider reports a declined authorization'

    request {
        method 'POST'
        url '/api/payments/authorize'
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-1001',
            amount: 250000,
            currency: 'VND',
            idempotencyKey: 'checkout-1001'
        )
    }

    response {
        status 402
        headers {
            contentType(applicationJson())
        }
        body(
            paymentId: 'PAY-1001',
            status: 'DECLINED',
            reasonCode: 'INSUFFICIENT_FUNDS'
        )
    }
}
~~~

Status và error body là behavior đã thống nhất trong ví dụ. Nếu API thật dùng 200 với business status hoặc 409/422, contract phải phản ánh agreement thật.

### Contract C — OrderConfirmed message

Order là producer, Notification là consumer.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'order_confirmed'

    input {
        triggeredBy('publishOrderConfirmed()')
    }

    outputMessage {
        sentTo('order-events')
        headers {
            messagingContentType(applicationJson())
        }
        body(
            eventType: 'OrderConfirmed',
            eventId: 'EVT-1001',
            orderId: 'ORD-1001',
            checkoutId: 'CHK-1001'
        )
    }
}
~~~

Đây là minh họa message contract. Producer base class phải cung cấp trigger method và test messaging configuration tương ứng. Destination/header/payload cần khớp broker abstraction thực tế.

## 6. Producer verification và consumer stub tests

Với ba contract trên, thiết kế test hai phía.

### Producer side

- Inventory chạy generated tests cho reservation success/error contracts.
- Payment chạy generated tests cho authorized/declined behavior.
- Order chạy generated message tests cho order_confirmed.
- Base class dựng implementation cần kiểm chứng.
- Producer test report ghi số test thực thi và PASS.
- Stub JAR được tạo từ cùng revision với implementation/contract đã kiểm chứng.

### Consumer side

- Checkout dùng Stub Runner tải Inventory stubs và Payment stubs.
- Notification dùng message stub/StubTrigger để kiểm tra handler với order_confirmed.
- Consumer client/handler thật của ứng dụng được gọi.
- Assertions kiểm tra business-relevant fields/status/error code.
- Test dùng version/classifier cụ thể; không dùng latest để che version drift.

Ví dụ Stub Runner ID:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:2.3.0:stubs:0",
        "com.example:payment-service:1.8.0:stubs:0"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractTest {
    // Dùng @StubRunnerPort hoặc StubFinder để lấy endpoint stub.
}
~~~

Ví dụ giả định artifact coordinates/version đã được publish/install vào Maven local repository. Trong CI nhiều job, có thể dùng REMOTE với repository staging và candidate version được truyền chính xác.

**Contract tests không cần khởi động toàn bộ Order, Notification, Kafka và production DB.** Chúng kiểm tra interface boundary của Checkout với Inventory/Payment và handler Notification với message contract.

## 7. Những rủi ro cần integration test

| Service | Dependency thật | Điều cần kiểm tra |
|---|---|---|
| Checkout | PostgreSQL | Checkout state, idempotency key, transaction |
| Inventory | PostgreSQL | Reservation, locking, stock invariant, rollback |
| Payment | PostgreSQL + payment sandbox/test server | Payment state, idempotency, timeout/reconciliation |
| Order | PostgreSQL + Kafka | Event consume, projection, duplicate/out-of-order |
| Notification | Kafka + email sandbox | Listener, retry, DLQ, duplicate suppression |
| Gateway | Gateway runtime + upstream test service | Routing, auth, path rewrite, headers |

### Integration test Inventory

Dùng DB tương thích production để kiểm tra:

- Reservation thành công cập nhật available quantity.
- Hai reservation đồng thời không oversell.
- Release reservation lặp lại không làm available quantity tăng quá mức.
- DB failure giữa transaction rollback đúng.
- Unique/idempotency constraint hoạt động.

### Integration test Checkout

Dùng HTTP server controllable cho Payment/Inventory hoặc test doubles ở dependency ngoài phạm vi, nhưng giữ Checkout DB và transaction thật. Kiểm tra:

- Cùng idempotency key không tạo checkout/payment duplicate.
- Payment declined kích hoạt release reservation.
- Timeout đưa checkout vào trạng thái có thể reconcile.
- Event/outbox chỉ được publish theo trạng thái commit hợp lệ.

### Integration test messaging

Dùng Kafka/broker thật hoặc container phù hợp để kiểm tra:

- Message được gửi tới topic đúng.
- Consumer group nhận event.
- Deserializer đọc schema/headers.
- Ack/offset/retry/DLQ theo policy.
- Duplicate event không tạo duplicate order/notification.
- Correlation ID được giữ.

## 8. Những rủi ro cần E2E

Chọn ít scenario nhưng có ý nghĩa nghiệp vụ cao.

### E2E 1 — Checkout thành công

Input:

~~~json
{
  "customerId": "CUS-101",
  "sku": "SKU-101",
  "quantity": 2,
  "paymentToken": "tok_test_approved",
  "idempotencyKey": "e2e-checkout-001"
}
~~~

Expected business outcome:

- Gateway chấp nhận request và chuyển đúng service.
- Checkout tạo một order/checkout.
- Inventory có reservation active cho quantity 2.
- Payment được capture/authorized theo flow.
- Order chuyển CONFIRMED.
- Notification event được xử lý.
- Client có thể tra cứu order bằng ID trả về.

### E2E 2 — Payment declined và compensation

Input dùng payment token test bị decline.

Expected:

- Checkout không chuyển order thành confirmed.
- Reservation được release hoặc chuyển trạng thái compensation có thể theo dõi.
- Không phát notification xác nhận thành công.
- Payment có trạng thái declined.
- Trạng thái cuối của workflow có thể quan sát qua API.

### E2E 3 — Duplicate checkout request

Gửi cùng request và cùng idempotency key hai lần.

Expected:

- Chỉ có một business order.
- Không capture payment hai lần.
- Không tạo hai reservation độc lập.
- Response của lần lặp có semantics đã thống nhất (cùng resource hoặc response replay).
- Event/notification không bị gửi duplicate ngoài policy.

Không cần hàng trăm E2E variants cho mọi status code. Contract và integration tests bao phủ chi tiết; E2E xác minh các workflow xuyên service có rủi ro cao.

## 9. Phân biệt test thật và test dùng stub

| Scenario | Thành phần thật | Có thể stub/mock |
|---|---|---|
| Checkout consumer contract | Checkout app/client | Inventory, Payment qua Stub Runner |
| Inventory producer contract | Inventory provider implementation | External dependencies ngoài contract |
| Payment producer contract | Payment provider implementation | External payment processor |
| Inventory DB integration | Inventory + PostgreSQL | Không mock repository/DB |
| Checkout compensation integration | Checkout + DB + controllable downstream | Payment/Inventory HTTP nếu chỉ kiểm tra orchestrator state |
| Kafka delivery integration | Producer/consumer + Kafka | External services ngoài scenario |
| E2E checkout | Gateway + Checkout + Inventory + Payment + Order + broker cần thiết | External email/payment network có thể sandbox nếu không kiểm tra chúng |

Một test có giá trị khi **ghi rõ phần nào thật và phần nào được thay thế**. Đừng gọi test Checkout + Inventory stub là E2E của marketplace.

## 10. Bài tập phần A — Vẽ test portfolio

Dựa trên kiến trúc và invariant ở trên, lập danh sách tối thiểu:

- 5 unit test cho business rules.
- 4 producer contract test groups.
- 3 consumer contract test groups.
- 5 integration test groups.
- 3 E2E journeys.

Với mỗi test, ghi:

| Trường | Câu hỏi |
|---|---|
| Risk | Lỗi gì có thể xảy ra? |
| Boundary | Component/service nào liên quan? |
| Test level | Unit, contract, integration hay E2E? |
| Real dependencies | DB/broker/gateway/service nào phải thật? |
| Test doubles | Có thể stub/mock thành phần nào? |
| Assertion | Invariant/behavior nào phải đúng? |
| CI stage | PR, main, nightly hay pre-release? |
| Owner | Nhóm nào chịu trách nhiệm? |

Gợi ý: test Inventory oversell cần DB thật và concurrency; test JSON field rename ưu tiên contract; test payment decline compensation xuyên Checkout–Inventory–Order cần integration và ít nhất một E2E scenario đại diện.

## 11. Bài tập phần B — Phân loại 12 thay đổi

Chọn test level chính và giải thích. Một thay đổi có thể cần nhiều tầng, nhưng hãy chỉ ra tầng bắt rủi ro trực tiếp nhất.

| # | Thay đổi | Test level ưu tiên |
|---:|---|---|
| 1 | Inventory đổi response quantity từ number sang string | ? |
| 2 | Inventory SQL migration đổi unique constraint reservation | ? |
| 3 | Payment client không retry HTTP 503 theo policy | ? |
| 4 | Kafka consumer group bị cấu hình sai | ? |
| 5 | Gateway rewrite /checkout/** thành path sai | ? |
| 6 | Order event đổi tên field orderId | ? |
| 7 | Duplicate OrderConfirmed gửi hai email | ? |
| 8 | Hai checkout đồng thời giữ cùng lượng hàng cuối | ? |
| 9 | JWT scope checkout.write không được map thành authority | ? |
| 10 | Payment declined nhưng order vẫn confirmed | ? |
| 11 | Notification email template hiển thị sai currency | ? |
| 12 | Checkout request thiếu field bắt buộc | ? |

## 12. Bài tập phần C — Thiết kế CI pipeline

Thiết kế pipeline cho hai repository độc lập: inventory-service (producer) và checkout-service (consumer).

Yêu cầu:

1. Inventory producer tests phải PASS trước khi publish stub.
2. Stub JAR có version/classifier cụ thể.
3. Checkout tải đúng candidate artifact từ staging.
4. Consumer tests chạy trong môi trường sạch.
5. Candidate không được promote nếu consumer compatibility fail.
6. Main branch có integration tests với PostgreSQL/Kafka.
7. Pre-release có E2E checkout success và payment decline.
8. Logs ghi contract revision, producer revision, consumer revision và artifact digest.

### Gợi ý flow

~~~mermaid
flowchart TD
    A["Inventory PR"] --> B["Generate + run producer tests"]
    B --> C{"PASS and test count valid?"}
    C -->|No| X["Block"]
    C -->|Yes| D["Package inventory stubs"]
    D --> E["Publish unique candidate"]
    E --> F["Checkout clean consumer job"]
    F --> G["Stub Runner resolves exact candidate"]
    G --> H["Checkout consumer contract tests"]
    H --> I{"PASS?"}
    I -->|No| X
    I -->|Yes| J["Promote candidate"]
    J --> K["Main/nightly integration suites"]
    K --> L["Pre-release E2E journeys"]
~~~

Không dùng một mutable version hoặc latest để truyền artifact giữa hai repository. Candidate version/digest phải được CI truyền tường minh.

## 13. Đáp án tham khảo: test portfolio

Một chiến lược hợp lý có thể là:

### Unit tests

1. Checkout tính tổng tiền và discount.
2. Inventory kiểm tra available quantity.
3. Payment mapping external decline code sang domain status.
4. Order state machine không cho CANCELLED → CONFIRMED.
5. Notification deduplication key được tạo đúng.

### Producer contract tests

1. Inventory reservation success/error.
2. Inventory release success/idempotent behavior.
3. Payment authorize/capture success/declined.
4. Order OrderConfirmed message payload/header.

Generated tests chạy ở producer build. Base class cần dựng implementation trong test mode phù hợp.

### Consumer contract tests

1. Checkout Inventory client dùng reservation stub.
2. Checkout Payment client xử lý authorized/declined stubs.
3. Notification handler xử lý OrderConfirmed message stub.

Dùng Stub Runner với artifact coordinates cụ thể; không dùng stub để kết luận database/broker production mechanics đúng.

### Integration tests

1. Inventory PostgreSQL transaction/locking/oversell.
2. Checkout idempotency + reservation/payment state transitions.
3. Checkout outbox commit/publish boundary.
4. Order Kafka consumer + database projection + duplicate event.
5. Notification Kafka retry/DLQ/deduplication.

Có thể chia suite nhỏ theo service để giảm thời gian debug.

### E2E tests

1. Checkout success.
2. Payment declined → reservation released, order not confirmed.
3. Duplicate checkout request → one order and one payment.

Đây là portfolio tham khảo. Nếu hệ thống chưa có outbox hoặc Notification không dùng Kafka, hãy điều chỉnh theo kiến trúc thật.

## 14. Đáp án tham khảo: phân loại 12 thay đổi

| # | Thay đổi | Tầng chính | Vì sao |
|---:|---|---|---|
| 1 | quantity number → string | **Contract** | Schema/type thay đổi ở Inventory–Checkout boundary |
| 2 | SQL unique constraint | **Integration** | Cần DB/migration thật |
| 3 | HTTP 503 retry policy | **Integration** | Cần HTTP client/resilience configuration thật |
| 4 | Kafka consumer group sai | **Messaging integration** | Cần broker và listener runtime |
| 5 | Gateway path rewrite sai | **Gateway integration/E2E** | Cần route/filter thật |
| 6 | orderId field rename trong event | **Message contract** | Event schema drift |
| 7 | Duplicate event gửi hai email | **Messaging integration** | Cần delivery/retry/dedup behavior thật |
| 8 | Hai checkout giữ stock cuối | **Concurrency integration** | Cần DB locking/isolation |
| 9 | JWT scope mapping sai | **Security integration** | Cần filter chain/authority mapping |
| 10 | Declined nhưng order confirmed | **E2E + workflow integration** | Compensation/state coordination xuyên service |
| 11 | Email template sai currency | **Component/integration test** | Renderer/template và data mapping |
| 12 | Request thiếu field bắt buộc | **Contract/provider test** | Validation/status/error body ở API boundary |

Test bổ sung: #1 thêm consumer Stub Runner test với candidate mới; #5 có gateway integration và E2E critical journey; #10 vẫn cần contract tests cho từng error boundary.

## 15. Đáp án tham khảo: CI pipeline

### Pull request của producer

- Checkout đúng contract revision.
- Resolve JDK/build tool/plugin đã pin.
- Discover contracts, fail nếu số lượng bất ngờ bằng 0.
- Generate và run producer contract tests.
- Package stub JAR.
- Inspect classifier, mappings và fixtures.
- Publish candidate với version unique vào staging.
- Ghi coordinates, producer SHA, contract SHA và digest.

### Pull request của consumer

- Lấy candidate coordinates/digest từ producer pipeline.
- Dùng REMOTE Stub Runner trong consumer test.
- Tải bằng read-only CI credentials vào clean environment.
- Kiểm tra digest.
- Chạy consumer contract tests và assert behavior.
- Report exact resolved version/digest.

### Main/nightly

- Integration suites với PostgreSQL/Kafka containers.
- Kiểm tra transaction, idempotency, retry, DLQ và projection.
- Chạy compatibility suite cho các consumer quan trọng.
- Ghi traces/logs có correlation ID.

### Pre-release

- Deploy candidate vào environment cô lập.
- Chạy E2E success/declined/duplicate scenarios.
- Xác minh gateway/auth/network và eventual consistency.
- Promote đúng artifact đã được consumer test, giữ digest.
- Chặn release nếu critical invariant fail.

## 16. Đáp án tham khảo: vì sao không dùng E2E cho mọi case?

Giả sử có 30 biến thể request validation, 10 error response, 5 kiểu matcher và 3 business workflows. Nếu tất cả đều E2E:

- Mỗi test cần nhiều service và dữ liệu.
- Một dependency fail làm nhiều test fail.
- Khó biết lỗi do contract, service, broker hay gateway.
- Runtime và maintenance tăng mạnh.
- Feedback cho developer chậm.

Phân bổ hợp lý:

- 30 validation variants: unit/provider/contract tests.
- 10 error response variants: producer contract + consumer stub tests.
- 5 matcher/schema behavior: contract tests.
- 3 workflow quan trọng: E2E.
- DB/broker/security mechanics: integration suites.

**E2E kiểm tra một số journey có ý nghĩa, không tái hiện toàn bộ contract matrix.**

## 17. Anti-pattern cần tránh

### Chỉ có E2E, không có contract tests

API drift chỉ xuất hiện ở suite chậm và khó xác định provider/consumer nào không thống nhất. Giữ contract tests ở boundary.

### Chỉ có Stub Runner, không có integration tests

Consumer có thể xử lý stub đúng trong khi database transaction, broker delivery hoặc security filter chain thật bị lỗi. Stub không chứng minh dependency thật hoạt động.

### Gọi consumer + stub là E2E

Nếu Inventory/Payment được thay bằng stub, test không xác minh workflow qua provider thật. Gọi đúng phạm vi để người đọc hiểu evidence.

### Mock database trong test transaction

Mock repository không kiểm tra SQL, constraint, isolation hoặc rollback. Dùng DB thật khi behavior đó là rủi ro.

### Một E2E test assert quá nhiều chi tiết nội bộ

Assert log, thứ tự internal call hoặc ID tự tăng khiến test brittle. Ưu tiên business state và observable outcomes.

### Dùng sleep cố định cho event

Sleep không bảo đảm event đã xử lý. Dùng correlation ID và bounded condition wait.

### Dùng chung data/topic cho test song song

Tests có thể nhận event của nhau hoặc thay đổi cùng row. Cô lập data, consumer group, topic hoặc namespace.

### Dùng latest trong compatibility pipeline

Consumer có thể tải bản khác nhau giữa hai lần chạy. Pin version/digest cụ thể và truyền candidate tường minh.

## 18. Review một chiến lược do nhóm đề xuất

Một proposal tốt cần trả lời:

1. **Business risks:** invariant nào có thể bị vi phạm?
2. **Service boundaries:** producer/consumer nào cần contract?
3. **Test portfolio:** mỗi risk được bắt ở unit, contract, integration hay E2E?
4. **Real dependencies:** DB/broker/gateway nào phải thật?
5. **Test doubles:** dependency nào được stub và vì sao?
6. **Data isolation:** test ID, seed, cleanup, namespace thế nào?
7. **Asynchronous behavior:** correlation và timeout được kiểm soát ra sao?
8. **CI placement:** PR/main/nightly/pre-release chạy gì?
9. **Ownership:** team nào duy trì contract/integration/E2E?
10. **Release gates:** evidence nào phải PASS trước promotion?

### Mẫu bảng review

| Risk | Test | Level | Real dependencies | CI stage | Owner | Pass evidence |
|---|---|---|---|---|---|---|
| Inventory schema drift | Generated producer + Checkout stub test | Contract | Producer/consumer code, stub artifact | PR | Inventory + Checkout | Reports PASS, exact stub version |
| Reservation oversell | Concurrent reservation test | Integration | Inventory + PostgreSQL | Main/nightly | Inventory | Stock invariant holds |
| Payment decline compensation | Checkout workflow test | Integration + E2E | Checkout, Inventory, Payment, Order | Pre-release | Order not confirmed, reservation released |
| Duplicate OrderConfirmed | Consumer dedup test | Integration | Kafka + Order/Notification persistence | Nightly | One business effect |
| Gateway auth propagation | Gateway test | Integration/E2E | Gateway + identity/test issuer | Pre-release | Auth policy enforced |

## 19. Checklist hoàn thành bài tập

- [ ] Đã vẽ service map và các HTTP/message boundaries.
- [ ] Đã ghi business invariants quan trọng.
- [ ] Đã xác định producer và consumer cho từng contract.
- [ ] Đã chọn contract đại diện để dùng Spring Cloud Contract.
- [ ] Đã thiết kế producer verification và consumer Stub Runner tests.
- [ ] Đã chọn integration tests cho DB/transaction/broker/security.
- [ ] Đã chọn một số E2E journeys trọng yếu.
- [ ] Đã phân biệt dependency thật và test doubles.
- [ ] Đã xác định data isolation, correlation ID và bounded waits.
- [ ] Đã phân bổ test vào PR/main/nightly/pre-release.
- [ ] Đã có negative/failure scenarios.
- [ ] Đã xác định owner và pass evidence.
- [ ] Đã tránh E2E cho biến thể API có thể kiểm tra ở tầng thấp hơn.
- [ ] Đã ghi version/digest stub để consumer test đúng candidate.

## 20. Ghi nhớ và tài liệu tham khảo

Một chiến lược cho hệ thống nhiều dịch vụ không bắt đầu bằng câu hỏi “cần bao nhiêu test?”, mà bắt đầu bằng **“business invariant nào có thể bị phá vỡ và cần thành phần thật nào để chứng minh?”**

- Dùng **Spring Cloud Contract** cho HTTP/message agreements giữa producer và consumer.
- Dùng **integration tests** cho database, transaction, security, broker, retry, idempotency và component interaction thật.
- Dùng **E2E tests** cho một số workflow xuyên gateway/nhiều service, đặc biệt compensation và eventual consistency.
- Dùng **unit tests** cho logic thuần để feedback nhanh.
- Liên kết mọi test với risk, owner, CI stage và evidence rõ ràng.

Contract, integration và E2E bổ sung cho nhau. Contract test giúp service phát triển độc lập; integration test xác minh cơ chế thật; E2E xác minh kết quả nghiệp vụ xuyên hệ thống. Portfolio tốt chọn đúng tầng thay vì đưa mọi thứ vào một suite duy nhất.

### Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): DSL, producer verification và Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML contracts và matchers.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): generated producer tests và stub packaging.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer-side stub testing.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test support.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): tích hợp Testcontainers.
- [Testcontainers for Java](https://java.testcontainers.org/): database, Kafka và dependency containers.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): authentication/authorization tests.
- [Awaitility](https://github.com/awaitility/awaitility): chờ điều kiện bất đồng bộ có deadline.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): HTTP stubs và request matching.

**Kết luận thực hành:** nộp một test strategy trong đó mỗi rủi ro quan trọng có tầng kiểm thử, dependency, owner, CI stage và bằng chứng PASS cụ thể. Nếu một integration/E2E test đang kiểm tra cùng schema assertion mà contract test đã bắt tốt, hãy giải thích giá trị bổ sung của test rộng đó; nếu không có giá trị bổ sung, chuyển assertion về tầng nhanh hơn.
