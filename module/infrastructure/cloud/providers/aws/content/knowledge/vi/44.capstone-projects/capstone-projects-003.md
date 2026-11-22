# Xây dựng hệ thống đơn hàng hướng sự kiện với saga

## Mục tiêu capstone

Bạn sẽ thiết kế và triển khai một hệ thống xử lý đơn hàng trên AWS. Một yêu cầu đặt hàng đi qua nhiều dịch vụ độc lập: tạo đơn, giữ tồn kho, xác thực thanh toán, tạo vận đơn, thu tiền và xác nhận đơn. Nếu một bước thất bại sau khi các bước trước đã ghi dữ liệu, hệ thống phải thực hiện các hành động bù trừ để đưa nghiệp vụ về trạng thái hợp lệ.

Dự án kết hợp **Saga orchestration** bằng AWS Step Functions với **event-driven integration** qua Amazon EventBridge và Amazon SQS. Step Functions điều phối giao dịch nghiệp vụ; EventBridge phân phối domain events tới các hệ thống quan tâm; SQS hấp thụ burst và tách tốc độ xử lý của consumer.

Sau capstone, bạn có thể:

- Phân rã order workflow thành các service boundaries và local transactions.
- Chọn saga orchestration hoặc choreography theo độ phức tạp của workflow.
- Thiết kế state machine có retry, timeout, catch và compensation.
- Ngăn oversell bằng conditional writes và optimistic concurrency.
- Xử lý duplicate requests/events bằng idempotency keys.
- Tránh dual-write bằng transactional outbox và DynamoDB Streams.
- Tách domain events khỏi commands và side effects.
- Thiết kế DLQ, redrive, reconciliation và manual review.
- Bảo vệ API, payment credentials, dữ liệu khách hàng và IAM permissions.
- Kiểm thử failure paths, compensation và eventual consistency.
- Đặt tiêu chí nghiệm thu, vận hành và kiểm soát chi phí cho hệ thống.

## 1. Bối cảnh và bài toán kinh doanh

Một cửa hàng trực tuyến nhận đơn từ web/mobile app. Một đơn hàng có nhiều sản phẩm, số lượng, địa chỉ giao và phương thức thanh toán. Các bước xử lý nằm ở những service và datastore khác nhau.

Ví dụ đơn hàng có ba sản phẩm:

1. Order Service tạo đơn ở trạng thái PENDING.
2. Inventory Service giữ số lượng sản phẩm.
3. Payment Service authorize phương thức thanh toán.
4. Shipping Service tạo shipment với đơn vị vận chuyển.
5. Payment Service capture khoản tiền đã authorize.
6. Order Service xác nhận đơn ở trạng thái CONFIRMED.
7. Notification/Analytics nhận domain events để gửi thông báo và cập nhật báo cáo.

Không có một transaction ACID duy nhất bao trùm các database và payment provider. Nếu thanh toán thất bại sau khi tồn kho đã được giữ, hệ thống phải trả tồn kho. Nếu tạo shipment thành công nhưng capture payment thất bại, cần hủy shipment và void authorization. Nếu capture đã thành công nhưng bước xác nhận order gặp lỗi, có thể cần refund.

Đây là bài toán distributed transaction. Saga chia giao dịch dài thành nhiều local transactions và định nghĩa hành động bù trừ tương ứng. Mỗi service tự quản lý dữ liệu của mình; orchestrator theo dõi tiến trình và quyết định bước tiếp theo.

## 2. Phạm vi dự án

### Chức năng bắt buộc

- Tạo đơn hàng với Idempotency-Key.
- Kiểm tra dữ liệu và giá sản phẩm từ nguồn đáng tin cậy.
- Giữ tồn kho có điều kiện, tránh bán vượt số lượng khả dụng.
- Authorize và capture payment qua adapter giả lập hoặc sandbox provider.
- Tạo và hủy shipment qua adapter.
- Điều phối saga và các compensation.
- Phát domain events cho Order, Inventory, Payment và Shipping.
- Gửi notifications bất đồng bộ qua SQS.
- Lưu trạng thái workflow và cho phép truy vấn tiến trình đơn hàng.
- Xử lý duplicate delivery, retry, timeout, DLQ và manual review.

### Ngoài phạm vi của phiên bản đầu

- Lưu hoặc xử lý trực tiếp dữ liệu thẻ thanh toán thô.
- Tính thuế, vận chuyển và giá khuyến mãi phức tạp.
- Multi-currency settlement và đối soát kế toán đầy đủ.
- Tối ưu tuyến đường giao hàng.
- Event sourcing toàn bộ domain.
- Multi-Region active-active cho mọi service.

Giữ phạm vi đầu tiên đủ nhỏ để có thể chứng minh cả happy path và failure/compensation paths. Sau khi các invariants hoạt động, mới mở rộng thêm participants.

## 3. Kiến trúc AWS được chọn

| Năng lực | AWS service / thành phần | Trách nhiệm |
|---|---|---|
| API ingress | Amazon API Gateway | Nhận yêu cầu đặt hàng, xác thực và giới hạn request |
| Business adapter | AWS Lambda | Xác thực command, ghi order + idempotency + outbox trong một transaction và trả 202 |
| Saga starter | AWS Lambda | Nhận OrderCreated, deduplicate theo sagaId và gọi StartExecution với execution name ổn định |
| Orchestration | AWS Step Functions Standard | Điều phối các bước và compensation |
| Event routing | Amazon EventBridge custom event bus | Định tuyến OrderCreated tới Saga Starter và domain events tới consumers |
| Buffering | Amazon SQS standard queues | Tách tốc độ producer/consumer |
| Failure isolation | SQS DLQs và EventBridge target DLQ | Giữ message/event không xử lý được |
| Service data | Amazon DynamoDB | Lưu order, inventory, payment, shipment và idempotency records |
| Change capture | DynamoDB Streams | Phát hiện outbox records đã commit |
| Compute | AWS Lambda | Triển khai từng service participant và consumers |
| Secrets | AWS Secrets Manager | Lưu credential của payment/shipping provider |
| Encryption | AWS KMS | Mã hóa dữ liệu và secrets theo policy |
| Logs/metrics | Amazon CloudWatch | Theo dõi request, saga, queue và Lambda |
| Tracing | AWS X-Ray / Step Functions execution history | Theo dõi đường đi của một order |
| Infrastructure | AWS CDK hoặc AWS SAM | Khai báo hạ tầng có thể tái tạo |

Đây là một kiến trúc serverless phù hợp cho capstone và tải biến động. Nếu service cần xử lý liên tục, runtime dài hoặc kiểm soát network chuyên sâu, có thể thay Lambda bằng ECS/Fargate mà vẫn giữ nguyên saga contracts.

## 4. Sơ đồ kiến trúc tổng thể

~~~mermaid
flowchart TD
    C["Web / Mobile client"] --> AP["API Gateway"]
    AP --> OAPI["Order API Lambda"]
    OAPI --> OD[("Orders + Idempotency + Outbox")]
    OD --> OST["Order Outbox Stream"]
    ID --> IST["Inventory Outbox Stream"]
    PD --> PST["Payment Outbox Stream"]
    SD --> SST["Shipping Outbox Stream"]
    OST --> PUB["Outbox Publisher Lambda"]
    IST --> PUB
    PST --> PUB
    SST --> PUB
    PUB --> EB["EventBridge: orders-domain"]
    EB --> STARTER["Saga Starter Lambda"]
    STARTER --> SF["Step Functions Standard Saga"]
    SF --> OS["Order Service Lambda"]
    SF --> IS["Inventory Service Lambda"]
    SF --> PS["Payment Service Lambda"]
    SF --> SS["Shipping Service Lambda"]
    IS --> ID[("Inventory + Reservations + Outbox")]
    PS --> PD[("Payment records + Outbox")]
    SS --> SD[("Shipment records + Outbox")]
    EB --> Q1["Notifications SQS"]
    EB --> Q2["Analytics SQS"]
    EB --> Q3["Fraud Review SQS"]
    Q1 --> N["Notification Lambda"]
    Q2 --> A["Analytics Consumer"]
    Q3 --> F["Fraud Consumer"]
    Q1 --> D1["Notifications DLQ"]
    Q2 --> D2["Analytics DLQ"]
    EB -. delivery failure .-> ED["EventBridge Target DLQ"]
    SF --> CW["CloudWatch / X-Ray"]
    PUB --> CW
~~~

Order API chỉ ghi order PENDING, idempotency record và OrderCreated outbox event; API không thực hiện một dual-write riêng để gọi StartExecution. Sau khi transaction commit, DynamoDB Streams kích hoạt outbox publisher, publisher gửi OrderCreated lên EventBridge và rule chuyển event tới Saga Starter Lambda để khởi chạy Step Functions Standard. Cách khởi chạy này bảo đảm việc tạo order và yêu cầu bắt đầu saga có một outbox record bền vững làm điểm nối.

Step Functions gọi các participants để thực hiện các bước thuộc giao dịch đặt hàng. Mỗi participant ghi thay đổi nghiệp vụ cùng outbox event trong local transaction của chính service đó. Outbox publisher đưa domain event lên EventBridge. Các consumer độc lập xử lý notification, analytics hoặc fraud signals.

EventBridge không phải nơi lưu trạng thái saga. Trạng thái workflow nằm trong Step Functions và các service databases. SQS là buffer cho consumer; queue backlog không nên làm thay đổi trạng thái payment hoặc inventory đã commit.

EventBridge target gọi Saga Starter Lambda. Lambda này dùng sagaId làm execution name ổn định và có role chỉ được states:StartExecution trên state machine mục tiêu. Với Standard workflow, StartExecution cùng tên và cùng input khi execution còn chạy có tính idempotent; nếu execution đã kết thúc, API trả ExecutionAlreadyExists và tên không thể được tái sử dụng trong 90 ngày. Starter phải tra cứu execution hiện có và xác nhận input/sagaId tương ứng; không tạo execution name mới cho mỗi lần redelivery. Có thể lưu SagaRegistry record theo sagaId với trạng thái STARTING/RUNNING để phục hồi trường hợp starter crash giữa lúc ghi nhận và gọi StartExecution. EventBridge target role chỉ cần lambda:InvokeFunction trên Saga Starter.

OrderConfirmed được ghi vào outbox trong cùng transaction với transition CONFIRMED. Publisher phát event sau đó; EventBridge route event tới notification, analytics hoặc CRM consumers. Step Functions không cần thực hiện một lần publish riêng sau khi state đã commit.

## 5. Vì sao chọn saga orchestration?

Saga có hai biến thể chính:

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Điều phối | Mỗi service phản ứng với event từ service khác | Một orchestrator quyết định bước tiếp theo |
| Luồng nghiệp vụ | Phân tán trong các consumers | Tập trung trong state machine |
| Theo dõi | Phải ghép event logs giữa các services | Có execution history và trạng thái từng bước |
| Compensation | Mỗi participant phát event bù trừ | Orchestrator gọi compensation theo thứ tự |
| Phù hợp | Ít participants, luồng đơn giản | Nhiều bước, nhánh lỗi và compensation rõ |
| Rủi ro | Khó nhìn toàn bộ luồng khi số event tăng | Workflow definition cần được quản lý và version |

Capstone chọn orchestration vì order workflow có nhiều bước tuần tự và cần bù trừ theo thứ tự ngược. EventBridge vẫn được dùng cho tích hợp ngoài saga. Cách kết hợp này tránh việc mỗi service tự suy luận toàn bộ giao dịch, nhưng vẫn giữ các consumers ngoài luồng đặt hàng độc lập.

AWS Step Functions Standard phù hợp với saga dài và cần execution history. Standard workflow có thời lượng tối đa một năm; execution history có thể truy xuất qua API trong 90 ngày sau khi execution hoàn tất. Express workflow phù hợp với event processing ngắn, khối lượng lớn; thời lượng tối đa năm phút và semantics phụ thuộc loại Express. Chọn Standard cho order saga và đánh giá lại khi có workload khác. https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html

## 6. Domain boundaries và quyền sở hữu dữ liệu

Không để mọi Lambda ghi trực tiếp vào cùng một bảng Orders hoặc Inventory. Mỗi service sở hữu dữ liệu và API nghiệp vụ của nó.

| Service | Dữ liệu sở hữu | Các thao tác chính |
|---|---|---|
| Order | Order, OrderStatus, order version | Create, Confirm, Cancel, Get |
| Inventory | SKU stock, Reservation | Reserve, Release, Commit |
| Payment | Authorization, Capture, Refund | Authorize, Capture, Void, Refund |
| Shipping | Shipment, carrier reference | Create, Cancel, Track |
| Notification | Delivery attempts, preferences | Send, retry, suppress duplicate |

Orchestrator truyền orderId, sagaId, các reference và command metadata. Participant không truy cập database nội bộ của service khác. Ví dụ, Order Service không tự trừ tồn kho; nó gọi Inventory Service qua task được định nghĩa trong saga.

Mỗi service cần có contract version, validation và idempotency policy. Thay đổi schema phải tương thích với event consumers đang chạy.

Order Service sở hữu order status và timeline; Inventory sở hữu stock và reservation; Payment sở hữu authorization/capture/refund references; Shipping sở hữu carrier booking. Các participant không ghi trực tiếp vào database của nhau. Saga chỉ truyền identifiers, command metadata và operation references cần thiết để bù trừ.

## 7. Vòng đời của order

Dùng trạng thái nghiệp vụ rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> INVENTORY_RESERVED
    INVENTORY_RESERVED --> PAYMENT_AUTHORIZED
    PAYMENT_AUTHORIZED --> SHIPMENT_CREATED
    SHIPMENT_CREATED --> PAYMENT_CAPTURED
    PAYMENT_CAPTURED --> CONFIRMED
    PENDING --> REJECTED
    PENDING --> CANCELLING
    INVENTORY_RESERVED --> CANCELLING
    PAYMENT_AUTHORIZED --> CANCELLING
    SHIPMENT_CREATED --> CANCELLING
    PAYMENT_CAPTURED --> REFUND_PENDING
    CANCELLING --> CANCELLED
    CANCELLING --> COMPENSATION_PENDING
    COMPENSATION_PENDING --> CANCELLED
    COMPENSATION_PENDING --> MANUAL_REVIEW
    REFUND_PENDING --> CANCELLED
    REFUND_PENDING --> MANUAL_REVIEW
    CONFIRMED --> [*]
    CANCELLED --> [*]
    MANUAL_REVIEW --> [*]
~~~

Trạng thái là góc nhìn nghiệp vụ của Order Service. Các service participants vẫn giữ trạng thái chi tiết riêng như RESERVED, AUTHORIZED, CAPTURED, VOIDED, REFUNDED hoặc SHIPMENT_CANCELLED.

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING | Đã tiếp nhận order, chưa hoàn tất các bước phân bổ |
| INVENTORY_RESERVED | Đã giữ hàng |
| PAYMENT_AUTHORIZED | Provider đã authorize |
| SHIPMENT_CREATED | Carrier đã nhận yêu cầu tạo shipment |
| PAYMENT_CAPTURED | Khoản tiền đã capture |
| CONFIRMED | Order được xác nhận với khách hàng |
| REJECTED | Bị từ chối do business rule như hết hàng hoặc payment declined |
| CANCELLING | Đang chạy các compensation |
| CANCELLED | Các compensation bắt buộc đã hoàn tất |
| COMPENSATION_PENDING | Còn side effect chưa bù trừ xong |
| MANUAL_REVIEW | Cần operator xác minh và xử lý có audit |

Order state và saga execution state là hai góc nhìn khác nhau: order phản ánh trạng thái nghiệp vụ; saga phản ánh task, retry và compensation đang chạy.

Không cho client gửi trực tiếp status=CONFIRMED. Chỉ workflow/service có quyền thực hiện transition hợp lệ sau khi các điều kiện nghiệp vụ được thỏa.

## 8. Happy path và compensation path

| Bước thành công | Local transaction | Compensation khi bước sau thất bại |
|---|---|---|
| CreateOrder | Tạo order PENDING | CancelOrder |
| ReserveInventory | Giữ số lượng theo reservation ID | ReleaseInventory |
| AuthorizePayment | Giữ hạn mức thanh toán | VoidAuthorization |
| CreateShipment | Tạo shipment với carrier | CancelShipment |
| CapturePayment | Capture khoản tiền đã authorize | RefundPayment |
| ConfirmOrder | Chuyển order sang CONFIRMED | Xử lý exception/manual review theo chính sách |

Nếu ReserveInventory trả về out-of-stock, không authorize payment và đánh dấu order REJECTED. Nếu AuthorizePayment bị từ chối, release inventory rồi REJECTED. Nếu CreateShipment thất bại, void authorization, release inventory rồi REJECTED. Nếu CapturePayment thất bại, cancel shipment, void authorization và release inventory. Nếu ConfirmOrder lỗi sau capture, xác minh provider state rồi refund, cancel shipment và release inventory; nếu một compensation không hoàn tất, giữ COMPENSATION_PENDING/MANUAL_REVIEW.

Luồng thành công:

1. Tạo order.
2. Giữ tồn kho.
3. Authorize payment.
4. Tạo shipment.
5. Capture payment.
6. Confirm order.
7. Phát OrderConfirmed.

Nếu CreateShipment thất bại, workflow void authorization, release inventory và cancel order. Nếu CapturePayment thất bại, workflow cancel shipment, void authorization, release inventory và cancel order. Nếu ConfirmOrder lỗi sau khi capture, workflow phải xác định trạng thái payment từ provider trước khi refund, rồi hủy shipment và giải phóng tồn kho theo chính sách.

Compensation là một business operation mới, không phải rollback database toàn cục. Ví dụ refund có thể mất thời gian, carrier có thể đã nhận yêu cầu shipment, hoặc một bên thứ ba có thể từ chối hủy. Nếu compensation thất bại, ghi COMPENSATION_PENDING, lưu nguyên nhân và chuyển manual review. Không đánh dấu đơn CANCELLED như thể mọi side effects đã được đảo ngược.

## 9. API contract cho việc tạo order

Các endpoint tối thiểu:

| Method | Path | Mục đích |
|---|---|---|
| POST | /orders | Tạo order và phát yêu cầu khởi chạy saga qua outbox |
| GET | /orders/{orderId} | Đọc trạng thái hiện tại |
| GET | /orders/{orderId}/events | Đọc timeline đã được phép hiển thị |
| POST | /orders/{orderId}/cancel | Yêu cầu hủy nếu transition hiện tại cho phép |

Client gọi:

~~~http
POST /orders
Authorization: Bearer <access-token>
Idempotency-Key: 6a0d4d58-8f9c-4c3f-bb52-6c8f1c5d2f11
Content-Type: application/json
~~~

Payload ví dụ:

~~~json
{
  "customerId": "customer-1001",
  "items": [
    {
      "sku": "SKU-RED-01",
      "quantity": 2
    },
    {
      "sku": "SKU-BLUE-03",
      "quantity": 1
    }
  ],
  "shippingAddressId": "address-22",
  "paymentMethodRef": "pmref-customer-1001-01"
}
~~~

Backend không tin customerId, giá hoặc tổng tiền do client gửi. Lấy customer/tenant identity từ JWT đã xác thực; lấy giá từ catalog/pricing service hoặc fixture phía server; tính lại total từ giá server và quantity đã validate; kiểm tra paymentMethodRef thuộc customer đã xác thực. Đây là opaque reference để Payment Service tra cứu provider token trong vault; không đưa provider token vào Order, Step Functions state, event hoặc log. Không lưu PAN/CVV hoặc dữ liệu thẻ thô.

Response nên trả 202 Accepted cùng orderId, sagaId và URL/status endpoint:

~~~json
{
  "orderId": "ord-2026-00042",
  "sagaId": "saga-2026-00042",
  "status": "PENDING",
  "statusUrl": "/orders/ord-2026-00042"
}
~~~

Không giữ HTTP request mở trong suốt thời gian carrier hoặc payment provider xử lý. Client truy vấn status hoặc nhận push notification khi saga kết thúc.

## 10. Idempotency ở API boundary

Client có thể gửi lại request khi timeout, mất kết nối hoặc không nhận response. Nếu mỗi lần retry tạo một order mới, khách hàng có thể bị đặt hàng và tính phí nhiều lần.

Thiết kế idempotency:

1. Client gửi Idempotency-Key ổn định cho một ý định đặt hàng.
2. API chuẩn hóa request và tính request hash.
3. Lưu key, customer ID, request hash, order ID và trạng thái xử lý.
4. Nếu key đã tồn tại với cùng request hash, trả lại cùng order/saga reference.
5. Nếu key tồn tại nhưng payload khác, trả 409 Conflict.
6. Nếu request đang xử lý, trả lại trạng thái hiện tại thay vì tạo saga mới.

Idempotency record cần có thời hạn lưu phù hợp với chính sách business, nhưng không xóa khi saga còn đang chạy hoặc có dispute cần đối soát. Không dùng execution name của Step Functions làm lớp idempotency duy nhất.

DynamoDB ClientRequestToken chỉ làm idempotent cho cùng một TransactWriteItems request trong cửa sổ 10 phút; nó không thay thế idempotency key nghiệp vụ có thời gian lưu dài hơn ở API boundary.

| Operation | Idempotency key gợi ý |
|---|---|
| POST /orders | tenantId + Idempotency-Key |
| ReserveInventory | orderId + sku + reservationVersion |
| ReleaseInventory | orderId + sku + compensationId |
| AuthorizePayment | orderId + paymentAttempt |
| CapturePayment | orderId + authorizationId |
| VoidAuthorization | orderId + authorizationId + compensationId |
| RefundPayment | orderId + captureId + compensationId |
| CreateShipment | orderId + shipmentVersion |
| Event consumer | consumerName + eventId |

AWS Lambda Powertools for Java có Idempotency utility với persistent store như DynamoDB. Utility hỗ trợ lưu trạng thái xử lý, nhưng key và hành vi phục hồi vẫn phải phản ánh business operation cụ thể.

## 11. Event contract và correlation

Domain event mô tả điều đã xảy ra, không phải yêu cầu consumer thực hiện một lệnh tùy ý. Dùng envelope EventBridge chuẩn:

~~~json
{
  "source": "com.example.orders",
  "detail-type": "OrderCreated",
  "detail": {
    "eventId": "evt-ord-00042-v1",
    "schemaVersion": "1.0",
    "aggregateType": "Order",
    "aggregateId": "ord-2026-00042",
    "aggregateVersion": 1,
    "sagaId": "saga-2026-00042",
    "correlationId": "req-6a0d4d58",
    "causationId": "cmd-create-order-00042",
    "occurredAt": "2026-11-20T08:00:00Z",
    "customerId": "customer-1001",
    "total": {
      "amountMinor": 125000,
      "currency": "VND"
    }
  }
}
~~~

Các field quan trọng:

- eventId: định danh domain event ổn định để consumer deduplicate.
- schemaVersion: phiên bản payload.
- aggregateId: order hoặc entity phát event.
- aggregateVersion: thứ tự thay đổi của aggregate.
- sagaId: định danh workflow phân tán.
- correlationId: nối request với log, trace và events.
- causationId: chỉ ra command/event dẫn tới thay đổi này.
- occurredAt: thời điểm nghiệp vụ xảy ra.

Không đưa access token, payment token, địa chỉ đầy đủ hoặc dữ liệu cá nhân không cần thiết vào event bus. Consumer có thể lấy dữ liệu chi tiết qua API được authorize.

EventBridge bổ sung envelope fields như id, account, region, time và version. eventId trong detail là business event ID ổn định do producer tạo để deduplicate khi publisher phát lại; EventBridge-generated id có thể khác nếu cùng event được PutEvents lần nữa. Consumer nên dùng detail.eventId cho deduplication nghiệp vụ.

## 12. Domain events cần có

| Event | Nguồn | Consumer ví dụ |
|---|---|---|
| OrderCreated | Order Service | Fraud, analytics |
| InventoryReserved | Inventory Service | Order projection |
| InventoryReservationFailed | Inventory Service | Saga/error reporting |
| PaymentAuthorized | Payment Service | Order projection |
| PaymentFailed | Payment Service | Fraud, support |
| ShipmentCreated | Shipping Service | Notification |
| PaymentCaptured | Payment Service | Finance, analytics |
| OrderConfirmed | Order Service | Email/SMS, CRM |
| OrderCancellationStarted | Order/Saga | Support |
| OrderCancelled | Order Service | Notification, analytics |
| CompensationFailed | Saga/participant | Operations/manual review |

Phân biệt OrderConfirmed với SendConfirmationEmail. Event thứ nhất mô tả sự kiện nghiệp vụ; event thứ hai là command. EventBridge rules nên lọc domain events theo source và detail-type.

## 13. Transactional outbox: tránh dual-write

Một lỗi phổ biến là service ghi database thành công rồi gọi EventBridge. Nếu Lambda crash giữa hai thao tác, database đã đổi nhưng event không được phát. Nếu phát event trước rồi database rollback, consumer nhận một sự kiện không có thật.

Transactional outbox ghi entity change và event record trong cùng một database transaction:

~~~mermaid
sequenceDiagram
    participant S as Service Lambda
    participant D as DynamoDB
    participant T as DynamoDB Streams
    participant P as Outbox Publisher
    participant E as EventBridge
    S->>D: TransactWriteItems (entity + outbox)
    D-->>S: Commit atomically
    D->>T: Stream records
    T->>P: Invoke publisher
    P->>E: PutEvents
    E-->>P: Per-entry result
~~~

Với DynamoDB, có thể dùng TransactWriteItems để ghi order/inventory/payment record và outbox item atomically. Bật DynamoDB Streams trên outbox table hoặc table chứa outbox records. Lambda publisher đọc stream và gọi PutEvents.

Lưu ý:

- Stream consumer có thể nhận lại record; publisher cần xử lý duplicate.
- PutEvents response cần kiểm tra FailedEntryCount và từng entry result; HTTP success không có nghĩa mọi event đều được publish.
- Publisher có thể crash sau khi EventBridge nhận event nhưng trước khi đánh dấu outbox đã phát. Consumer vẫn phải deduplicate bằng eventId.
- Ghi aggregateVersion hoặc sequence để consumer phát hiện event đến sai thứ tự.
- Không giả định các record từ nhiều item trong cùng DynamoDB transaction xuất hiện đồng thời hoặc liên tiếp trong stream.
- Outbox record nên có trạng thái PENDING/PUBLISHED, eventId và aggregate sequence. Publisher cập nhật PUBLISHED sau khi EventBridge chấp nhận entry; nếu crash giữa PutEvents và cập nhật trạng thái, duplicate vẫn có thể xảy ra nên consumer phải deduplicate.
- Có scheduled sweeper tìm PENDING outbox records quá tuổi để khôi phục khi stream consumer bị gián đoạn hoặc record không được xử lý đúng hạn.
- EventBridge rule nhận OrderCreated cần retry policy, target DLQ, quyền lambda:InvokeFunction trên Saga Starter và alarm. Saga Starter role mới có states:StartExecution trên state machine cụ thể. Có thể bật archive/replay để điều tra hoặc phát lại theo quy trình; replay vẫn phải đi qua idempotent consumers.

DynamoDB Streams chỉ giữ stream records trong 24 giờ. Outbox item là bản ghi bền vững để publisher sweeper có thể khôi phục sau khi stream retention hết hạn hoặc consumer bị gián đoạn lâu hơn dự kiến.

Transactional outbox giải quyết dual-write giữa local database và event notification. Nó không biến nhiều service databases thành một transaction toàn cục. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

## 14. DynamoDB data model gợi ý

Có thể bắt đầu bằng một table cho mỗi bounded context hoặc một table multi-tenant với key design rõ ràng.

| Table / item | Partition key | Sort key | Nội dung |
|---|---|---|---|
| Orders | ORDER#<orderId> | META | customer/tenant, totals, status, version, sagaId |
| OrderItems | ORDER#<orderId> | ITEM#<sku> | SKU, quantity, server-side price snapshot |
| OrderOutbox | ORDER#<orderId> | EVENT#<sequence>#<eventId> | event type, schema version, payload, PENDING/PUBLISHED |
| Idempotency | TENANT#<tenantId>#KEY#<key> | REQUEST | request hash, orderId, response, status, expiry |
| SagaRegistry | SAGA#<sagaId> | META | executionName, inputHash, executionArn, STARTING/RUNNING/terminal state |
| Inventory | SKU#<sku> | STOCK | available, reserved, version |
| Reservations | ORDER#<orderId> | SKU#<sku> | reservationId, quantity, state, expiry |
| Payments | ORDER#<orderId> | PAYMENT#<operation> | provider reference, amount, status, idempotency key |
| Shipments | ORDER#<orderId> | SHIPMENT | carrier reference, status, trackingId |
| ProcessedEvents | CONSUMER#<name>#EVENT#<eventId> | META | processedAt, result, expiry |

Với DynamoDB transaction, các thao tác có thể cập nhật nhiều items/tables trong cùng account và Region theo kiểu all-or-nothing. Giữ transaction nhỏ và trong một service boundary. Không dùng TransactWriteItems để cố điều phối payment provider hoặc database của service khác. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html

Trong production, chọn một table cho mỗi bounded context hoặc single-table design dựa trên access patterns thực tế. Bảng trên là logical model để chỉ rõ ownership; không bắt buộc mỗi dòng phải là một physical table.

## 15. Reserve inventory bằng conditional write

Để tránh oversell, thao tác reserve cần kiểm tra số lượng khả dụng trong cùng update:

~~~text
Update Inventory item:
  SET available = available - :qty,
      reserved = reserved + :qty,
      version = version + 1
  CONDITION available >= :qty
            AND version = :expectedVersion
~~~

Cùng transaction có thể tạo reservation record với condition attribute_not_exists cho khóa reservation. Với order có nhiều SKU, gộp các dòng trùng SKU trước khi tạo TransactWriteItems và update mỗi SKU đúng một lần; nếu một condition không thỏa thì toàn transaction thất bại, không giữ một phần hàng.

Release inventory cũng cần idempotent: chỉ chuyển reservation từ RESERVED sang RELEASED một lần; nếu đã RELEASED thì trả kết quả trước đó; nếu reservation chưa tồn tại thì no-op an toàn. Nếu reservation đã COMMITTED/SHIPPED, không release bằng compensation thông thường; dùng quy trình return/restock riêng.

## 16. Payment adapter và idempotency

Payment Service không nên để saga workflow gọi trực tiếp payment provider từ nhiều Lambda khác nhau. Dùng một adapter sở hữu:

- Payment authorization.
- Capture.
- Void authorization.
- Refund.
- Query/reconciliation transaction state.
- Secret rotation và provider-specific error mapping.

Dùng idempotency key ổn định, ví dụ:

- authorize:<orderId>:<paymentAttempt>
- capture:<orderId>:<authorizationId>
- refund:<orderId>:<captureId>:<compensationId>

Lưu provider transaction ID và trạng thái trong Payment table. Nếu request timeout sau khi provider xử lý, không gửi charge mới ngay. Trước tiên query provider bằng idempotency key/reference để xác định kết quả đã commit hay chưa.

Payment providers có semantics, thời hạn idempotency key và trạng thái khác nhau. Adapter phải chuyển các khác biệt này thành contract nội bộ nhất quán. Không ghi thông tin thẻ hoặc provider secrets vào Step Functions input/output.

### Shipping participant

Shipping Service nhận orderId, địa chỉ đã validate, package details và shipment idempotency key. CreateShipment phải trả lại cùng carrier reference khi nhận lại cùng business request. Nếu carrier timeout, query carrier bằng merchant reference trước khi tạo booking mới.

CancelShipment là compensation có điều kiện: shipment chưa tạo thì trả no-op thành công; shipment CREATED/BOOKED có thể hủy theo carrier policy; nếu parcel đã bàn giao hoặc carrier từ chối cancel, tạo exception case để operator xử lý return/refund. HTTP 200 từ carrier không có nghĩa hàng đã giao.

## 17. Saga state machine với Step Functions

Chọn Standard workflow cho saga vì quy trình có nhiều bước, compensation và cần execution history. Workflow input chỉ nên chứa IDs, correlation metadata và các business references cần thiết. Không truyền toàn bộ hồ sơ khách hàng hoặc dữ liệu payment qua state payload.

Luồng chính:

~~~mermaid
flowchart TD
    A["CreateOrder"] --> B["ReserveInventory"]
    B --> C["AuthorizePayment"]
    C --> D["CreateShipment"]
    D --> E["CapturePayment"]
    E --> F["ConfirmOrder + outbox commit"]
    F --> H["Succeed"]
    B -. failure .-> X["Compensation"]
    C -. failure .-> X
    D -. failure .-> X
    E -. failure .-> X
    F -. failure .-> X
    X --> Y["Cancel shipment if created"]
    Y --> Z["Refund capture or void authorization"]
    Z --> R["Release inventory"]
    R --> O["Cancel order"]
    O --> M["Failed / Manual review"]
~~~

Mỗi Task gọi participant Lambda qua optimized integration arn:aws:states:::lambda:invoke. ResultPath giữ lại các reference như reservationId, authorizationId, shipmentId và captureId để compensation dùng lại. Dùng Retry cho lỗi tạm thời; Catch chuyển sang compensation khi bước nghiệp vụ thất bại.

Business rejection nên là kết quả có cấu trúc để Choice state rẽ nhánh, ví dụ reserved=false hoặc authorized=false; lỗi hạ tầng mới dùng Retry/Catch. Saga Starter Lambda nhận OrderCreated từ EventBridge và gọi StartExecution. Tạo execution name ổn định từ sagaId; duplicate delivery phải tra execution hiện có hoặc coi ExecutionAlreadyExists là duplicate đã được nhận diện, không khởi chạy saga thứ hai.

Standard workflow có exactly-once execution model ở cấp workflow state trừ khi bạn cấu hình Retry. Điều đó không loại bỏ nhu cầu idempotency ở participant: external provider có thể đã thực hiện side effect dù caller chưa nhận được response, và event delivery có thể lặp. https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html

## 18. Ví dụ ASL: retry và catch cho một participant

Đây là một trích đoạn state machine minh họa cách gọi Inventory Service. Thay Lambda ARN và state names bằng tài nguyên của môi trường triển khai. Các bước khác dùng cùng nguyên tắc, với compensation phù hợp.

~~~json
{
  "Comment": "Order saga - inventory step example",
  "StartAt": "ReserveInventory",
  "States": {
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:reserve-inventory",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "reservationId.$": "$.Payload.reservationId",
        "status.$": "$.Payload.status"
      },
      "ResultPath": "$.inventory",
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2,
          "JitterStrategy": "FULL"
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.failure",
          "Next": "CompensateOrder"
        }
      ],
      "Next": "ContinueSaga"
    },
    "ContinueSaga": {
      "Type": "Succeed"
    },
    "CompensateOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:cancel-order",
        "Payload.$": "$"
      },
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "ManualReview"
        }
      ],
      "Next": "Failed"
    },
    "ManualReview": {
      "Type": "Fail",
      "Error": "CompensationFailed",
      "Cause": "Order requires operator review"
    },
    "Failed": {
      "Type": "Fail",
      "Error": "OrderSagaFailed",
      "Cause": "Inventory reservation failed"
    }
  }
}
~~~

Trong workflow đầy đủ, compensation phải kiểm tra những bước đã thực sự commit. Không gọi ReleaseInventory nếu chưa có reservation; không RefundPayment nếu payment chưa capture. Nếu kết quả payment không rõ do timeout, query provider trước khi quyết định void/refund. Định nghĩa error names nghiệp vụ ổn định như OutOfStock, PaymentDeclined, CarrierUnavailable để phân biệt lỗi business với lỗi hạ tầng.

Đây là fragment để minh họa một Task và error path, không phải state machine deployable hoàn chỉnh. Compensation coordinator cần đọc các operation references đã có, chỉ chạy các bước bù trừ tương ứng và lưu kết quả của từng compensation. Nếu một compensation độc lập thất bại, vẫn có thể tiếp tục các compensation an toàn khác rồi tổng hợp MANUAL_REVIEW.

## 19. Thiết kế compensation theo tiến trình đã commit

Orchestrator cần lưu output/reference của mỗi bước thành công. Khi có lỗi, đi ngược qua các bước đã hoàn thành:

1. Nếu có shipmentId, gọi CancelShipment.
2. Nếu có captureId, query payment rồi gọi RefundPayment; nếu chỉ có authorizationId, gọi VoidAuthorization.
3. Nếu có reservationId, gọi ReleaseInventory.
4. Nếu có orderId, gọi CancelOrder.
5. Nếu một compensation thất bại, ghi COMPENSATION_PENDING, lưu error và phát cảnh báo manual review.

Compensation cần idempotent và có timeout riêng. Một lỗi ở bước CancelShipment không nên khiến hệ thống bỏ qua mọi compensation khác nếu các thao tác còn lại vẫn an toàn. Có thể ghi nhận từng compensation result rồi tiếp tục các hành động độc lập; cuối workflow tổng hợp trạng thái COMPENSATED hoặc MANUAL_REVIEW.

Không xóa order record để rollback. Giữ lịch sử CANCELLED, REFUND_PENDING, COMPENSATION_FAILED và audit metadata để hỗ trợ customer service và đối soát.

## 20. Retry, timeout và error taxonomy

Phân loại lỗi trước khi đặt Retry:

| Nhóm | Ví dụ | Xử lý |
|---|---|---|
| Transient infrastructure | Lambda throttling, network error, provider 5xx | Retry có exponential backoff và jitter |
| Business rejection | OutOfStock, PaymentDeclined, address invalid | Không retry tự động; đi compensation hoặc trả lỗi nghiệp vụ |
| Permanent configuration | AccessDenied, invalid secret, missing resource | Fail nhanh, alarm và sửa cấu hình |
| Ambiguous outcome | Provider timeout sau khi có thể đã charge | Query/reconcile trước khi retry side effect |
| Compensation failure | Carrier không hủy được shipment, refund pending | Manual review và retry compensation có kiểm soát |

Ví dụ Retry:

~~~json
{
  "ErrorEquals": [
    "Lambda.ServiceException",
    "Lambda.SdkClientException",
    "States.Timeout"
  ],
  "IntervalSeconds": 2,
  "MaxAttempts": 4,
  "BackoffRate": 2,
  "MaxDelaySeconds": 30,
  "JitterStrategy": "FULL"
}
~~~

Đặt TimeoutSeconds cho từng Task dựa trên latency của participant/provider. Đặt timeout tổng cho workflow theo SLA order. Không retry States.ALL một cách mù quáng: lỗi nghiệp vụ và lỗi cấu hình có thể không bao giờ tự hết.

Step Functions hỗ trợ Retry và Catch trên Task/Parallel/Map states. Retry có thể dùng IntervalSeconds, BackoffRate, MaxAttempts, MaxDelaySeconds và JitterStrategy; Catch chuyển workflow sang state xử lý lỗi. https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html

## 21. EventBridge routing và SQS consumers

Tạo custom event bus, ví dụ orders-domain-bus. Đặt rules theo event source và detail-type:

~~~json
{
  "source": ["com.example.orders"],
  "detail-type": [
    "OrderConfirmed",
    "OrderCancelled"
  ]
}
~~~

Rule này có thể chuyển events tới SQS order-notifications. Rule khác có thể gửi PaymentCaptured tới queue cho analytics hoặc finance. Mỗi consumer chỉ nhận event cần thiết.

SQS standard queue phù hợp khi throughput và decoupling quan trọng hơn strict ordering. Consumer phải chấp nhận at-least-once delivery và deduplicate. Nếu cần thứ tự theo order, dùng thiết kế FIFO có MessageGroupId theo aggregate và kiểm tra khả năng tích hợp EventBridge/target tương ứng.

Không để Notification Service quyết định payment hoặc inventory compensation. Notifications là side effect sau khi trạng thái nghiệp vụ được commit.

Standard queue cho throughput cao nhưng không bảo đảm thứ tự tuyệt đối. FIFO giữ thứ tự trong từng MessageGroupId; dùng orderId làm group key nếu các message của cùng order phải tuần tự, còn các order khác vẫn xử lý song song. FIFO deduplication window hữu hạn không thay thế idempotency trong database/provider.

Notification consumer nên ghi delivery attempts và trạng thái gửi riêng. Nếu email/SMS provider lỗi, queue retry hoặc DLQ xử lý; order vẫn giữ CONFIRMED. Một read model có thể subscribe OrderCreated/OrderConfirmed/OrderCancelled để phục vụ dashboard, nhưng API GET /orders nên đọc nguồn dữ liệu có thẩm quyền khi cần trạng thái mới nhất.

## 22. DLQ, retry delivery và redrive

Có hai tầng lỗi khác nhau:

| Tầng | Lỗi | DLQ |
|---|---|---|
| EventBridge → SQS target | EventBridge không gửi được event tới target | EventBridge target DLQ, là standard SQS queue |
| SQS → Lambda consumer | Consumer nhận message nhưng xử lý thất bại nhiều lần | SQS source queue DLQ cùng loại queue |

Với SQS source queue, cấu hình maxReceiveCount phù hợp và đặt retention của DLQ đủ dài để điều tra. Khi message vào DLQ, kiểm tra exception, schema version, consumer deployment và dependency trước khi redrive.

EventBridge có retry policy riêng và có thể đưa event delivery failures vào target DLQ. Một số lỗi cấu hình như thiếu permission hoặc target không tồn tại có thể đi thẳng vào DLQ mà không retry. https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html

SQS DLQ giúp cô lập message consumer không xử lý được và hỗ trợ redrive sau khi sửa nguyên nhân. Với FIFO queues, cân nhắc tác động tới thứ tự khi dùng DLQ. https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html

Đặt visibility timeout lớn hơn thời gian xử lý tối đa dự kiến của consumer. Với Lambda SQS event source mapping, AWS khuyến nghị visibility timeout ít nhất bằng sáu lần function timeout cộng maximum batching window. Cấu hình maxReceiveCount để message poison không lặp vô hạn; với batch processing, bật ReportBatchItemFailures để chỉ retry các records thất bại thay vì toàn batch. DLQ cần retention, encryption, alarm và owner rõ ràng.

## 23. Concurrency, semantic lock và optimistic concurrency

Saga không cung cấp isolation toàn cục. Hai saga có thể đồng thời thay đổi cùng một order, SKU hoặc payment reference. Dùng các cơ chế sau:

- version tăng sau mỗi transition.
- Conditional update yêu cầu version/state hiện tại đúng kỳ vọng.
- Reservation record có trạng thái và ID riêng.
- Payment capture chỉ được thực hiện khi authorization còn hợp lệ và chưa capture.
- Cancel chỉ hợp lệ trước một số business milestones.
- Dùng idempotency key cho command và event.
- Có semantic lock như order.status = PROCESSING hoặc activeSagaId để chặn command xung đột.

Ví dụ update order chỉ khi đang PENDING và version bằng 3. Nếu một saga khác đã cập nhật version 4, thao tác cũ phải thất bại với conflict và được xử lý theo business rule, không ghi đè trạng thái mới.

Không giữ distributed lock dài hạn trong DynamoDB để mô phỏng transaction toàn cục. Dùng conditional writes và lease có expiry nếu thật sự cần lock.

## 24. Xử lý duplicate và event ordering

EventBridge, SQS standard và Lambda event source mappings có thể tạo duplicate delivery. Một consumer idempotent nên:

1. Đọc eventId và aggregateVersion.
2. Kiểm tra event đã xử lý trong Inbox/ProcessedEvents store chưa.
3. Nếu đã xử lý, trả success mà không lặp side effect.
4. Nếu version cũ hơn trạng thái hiện tại, bỏ qua hoặc đưa vào reconciliation.
5. Nếu version bị nhảy, truy vấn nguồn dữ liệu hoặc đợi event thiếu.
6. Ghi processed marker và business update theo một transaction cục bộ.

Không dựa vào timestamp đơn thuần để sắp xếp mọi event. Dùng sequence/version tăng theo aggregate. Nếu cần strict ordering, thiết kế partition/group key và queue type phù hợp; vẫn phải xử lý duplicate.

Ghi ProcessedEvents/Inbox marker cùng business update trong một local transaction nếu consumer ghi DynamoDB. Nếu consumer phải gọi external provider, lưu operation state trước khi gọi, dùng provider idempotency key và reconcile kết quả mơ hồ trước khi thử lại. Không đánh dấu event hoàn tất trước khi side effect có kết quả xác định.

## 25. Observability và audit

Mỗi request cần có:

- orderId
- sagaId
- correlationId
- causationId
- eventId
- aggregateVersion
- paymentReference hoặc shipmentReference đã được làm sạch dữ liệu nhạy cảm

CloudWatch Logs ghi structured JSON. Step Functions execution history cho biết state nào thành công/thất bại và error output. X-Ray giúp nối API Gateway, Lambda và downstream calls. CloudWatch alarms theo dõi:

| Metric / tín hiệu | Ý nghĩa |
|---|---|
| Saga success/failure rate | Tỷ lệ order hoàn tất |
| Saga duration p50/p95/p99 | Thời gian xử lý end-to-end |
| Compensation count/failure | Số giao dịch phải bù trừ |
| Payment authorize/capture/void/refund failures | Sức khỏe payment integration |
| Inventory reservation conflicts | Áp lực tồn kho và oversell protection |
| SQS ApproximateAgeOfOldestMessage | Consumer backlog |
| DLQ visible messages | Message không xử lý được |
| EventBridge failed invocations | Lỗi delivery đến target |
| Lambda errors/throttles/duration | Lỗi và capacity |
| Step Functions timed out/aborted | Saga không kết thúc đúng SLA |

Theo dõi thêm các tín hiệu vận hành:

| Metric / tín hiệu | Mục đích |
|---|---|
| OrdersCreated | Volume order mới |
| CompensationStarted / CompensationFailed | Tần suất và độ tin cậy của bù trừ |
| OrdersManualReview | Số case cần operator |
| InventoryReservationRejected | Tỷ lệ hết hàng hoặc conditional conflict |
| PaymentDeclined / PaymentUnknown | Phân biệt decline với kết quả provider chưa rõ |
| DynamoDB ThrottledRequests / TransactionConflict | Capacity và contention |
| EventBridge DLQ depth / failed invocations | Event delivery đang bị chặn |
| SQS DLQ depth / ApproximateAgeOfOldestMessage | Poison messages và consumer backlog |

Tạo alarms cho queue age vượt SLA, DLQ có message, saga failed/timed out, compensation/manual review tăng, transaction conflict/throttle tăng và PaymentUnknown tồn tại quá lâu. Mỗi alarm cần runbook và owner.

Không ghi bearer token, payment token, CVV, PAN, secret hoặc địa chỉ đầy đủ vào logs. Audit record cần giữ trạng thái trước/sau, actor, timestamp và lý do thay đổi theo retention policy.

## 26. Security và IAM boundaries

Tách execution roles theo thành phần:

| Role | Quyền tối thiểu điển hình |
|---|---|
| API/Order API Lambda | Xác thực request; ghi Orders, Idempotency và Outbox |
| Step Functions role | Invoke đúng participant Lambda ARNs; publish đúng EventBridge bus nếu workflow tự phát event |
| Order Lambda role | Đọc/ghi Orders và Outbox |
| Inventory Lambda role | Đọc/ghi Inventory và Reservations |
| Payment Lambda role | Đọc/ghi Payments, đọc secret provider cần thiết |
| Shipping Lambda role | Đọc/ghi Shipments, đọc secret carrier cần thiết |
| Outbox publisher role | Đọc DynamoDB Stream và events:PutEvents trên bus cụ thể |
| Saga Starter role | states:StartExecution trên đúng Step Functions state machine |
| EventBridge target role | lambda:InvokeFunction trên Saga Starter Lambda |
| Consumer role | Consume queue riêng và ghi datastore riêng |

Các biện pháp bổ sung:

- API Gateway dùng JWT/Cognito/OIDC authorizer và throttling.
- WAF có thể bảo vệ public API khỏi một số request abuse.
- Dùng Secrets Manager cho provider credentials; không hard-code secret trong Lambda environment variables nếu có thể tránh.
- KMS encryption cho DynamoDB, SQS, Secrets Manager và log groups theo yêu cầu.
- Dùng resource policies cho cross-account integrations và scope theo source ARN/account.
- Chỉ đặt Lambda vào VPC khi cần truy cập private resources; kiểm tra NAT/VPC endpoints để tránh egress cost và connectivity errors.
- Dùng CloudTrail để audit control-plane changes.
- Giữ payload EventBridge/SQS tối thiểu và áp dụng data retention phù hợp.

Lambda không cần VPC attachment chỉ vì gọi DynamoDB, EventBridge hoặc SQS qua AWS service endpoints. Nếu cần truy cập private database hoặc private service, thiết kế subnet, security groups, VPC endpoints/NAT và DNS rõ ràng; NAT Gateway/data processing có thể tạo chi phí đáng kể. Không đưa payment token, bearer token, PAN/CVV hoặc địa chỉ đầy đủ vào logs và event payload.

## 27. Hạ tầng dưới dạng mã và deployment

Dùng AWS CDK hoặc AWS SAM để tạo:

- API Gateway routes và authorizer.
- Lambda functions và execution roles.
- Step Functions Standard state machine.
- DynamoDB tables, indexes, TTL và Streams.
- EventBridge custom bus, rules và targets.
- SQS queues, DLQs, redrive policies và queue policies.
- CloudWatch log groups, dashboards và alarms.
- KMS keys và Secrets Manager references.
- IAM policies được scope theo resource.

Tách môi trường dev, test và prod bằng account hoặc stack configuration. Không dùng cùng payment secret hoặc queue giữa test và production. State machine ARN, table names và bus ARN nên được inject qua deployment outputs/configuration.

Một cấu trúc repository tham khảo:

~~~text
order-saga/
  README.md
  infra/
    template.yaml
    parameters/
      dev.json
      test.json
  contracts/
    events/
      order-created-v1.json
      inventory-reserved-v1.json
      payment-authorized-v1.json
      order-confirmed-v1.json
  workflows/
    order-saga.asl.json
  services/
    order-api/
    outbox-publisher/
    inventory/
    payment/
    shipping/
    order-state/
    notification/
  tests/
    unit/
    integration/
    contract/
    saga-failure/
    load/
  runbooks/
    payment-unknown.md
    compensation-failed.md
    eventbridge-dlq.md
    sqs-dlq.md
~~~

## 28. CI/CD và versioning contracts

Pipeline nên gồm:

1. Lint và unit tests cho từng service.
2. Validate OpenAPI/API schemas và event JSON schemas.
3. Validate ASL definition trước deploy.
4. Build Lambda artifacts/container images.
5. Deploy infrastructure vào dev.
6. Chạy integration tests và failure injection.
7. Promote immutable artifact sang test/staging.
8. Manual approval trước production nếu quy trình yêu cầu.
9. Deploy backward-compatible schema changes trước consumer rollout.
10. Theo dõi alarms và rollback theo release plan.

Step Functions state machine definition cũng cần version control. Dùng alias/version hoặc chiến lược deployment phù hợp để execution đang chạy không bị thay đổi ngoài ý muốn. Event consumers phải đọc được event versions đang tồn tại trong retention/replay window.

## 29. Kế hoạch kiểm thử

### Unit tests

- Validate order items, quantity và currency.
- Inventory conditional reserve/release.
- Payment state transitions.
- Idempotency key và request hash.
- Compensation functions.
- Event schema validation.

### Integration tests

- API → Step Functions → participants.
- DynamoDB transaction + outbox stream.
- Outbox publisher → EventBridge.
- EventBridge rule → SQS.
- SQS → Lambda consumer.
- Secrets/KMS/IAM permissions.

### Failure injection

| Kịch bản | Kết quả cần đạt |
|---|---|
| SKU hết hàng | Order bị cancel, không authorize payment |
| Payment declined | Release inventory, cancel order |
| Carrier timeout | Retry giới hạn, sau đó void payment và release stock |
| Capture timeout nhưng provider đã capture | Query provider, không charge lần hai |
| ConfirmOrder lỗi sau capture | Refund/reconciliation và manual review nếu cần |
| Duplicate API request | Trả cùng order reference |
| Duplicate EventBridge/SQS event | Consumer không lặp side effect |
| Consumer poison message | Message vào DLQ, alarm được kích hoạt |
| Compensation API lỗi | COMPENSATION_PENDING, tạo manual review |
| Hai order mua SKU cuối cùng | Chỉ một reservation thành công |
| Outbox publisher crash sau PutEvents | Duplicate được deduplicate bằng eventId |
| Saga execution timeout | Alert và reconciliation, không xóa trạng thái |
| Inventory timeout sau commit | Retry trả reservation cũ theo idempotency key |
| Payment timeout sau authorize | Query provider, không authorize lần hai |
| EventBridge target delivery failure | Retry, sau đó DLQ và alarm |
| ConfirmOrder và cancel đồng thời | Conditional status/version chỉ cho một transition hợp lệ |
| Event consumer xử lý batch có một record lỗi | Partial batch failure retry đúng record, không nhân side effect các record đã thành công |

Kiểm thử cả success path lẫn từng điểm thất bại. Chỉ kiểm thử Lambda handler riêng lẻ là chưa đủ để chứng minh saga có thể phục hồi.

## 30. Quy trình triển khai capstone theo giai đoạn

### Giai đoạn 1: thiết kế domain

- Viết order lifecycle và invariants.
- Xác định service boundaries.
- Định nghĩa event contracts và idempotency keys.
- Vẽ success/compensation flows.

**Deliverable:** context diagram, state diagram, API contract và event catalog.

### Giai đoạn 2: Order API và outbox

- Xây POST /orders và GET /orders/{id}.
- Validate request, xác thực customer và tính total phía server.
- Ghi order, idempotency record và outbox event bằng DynamoDB TransactWriteItems.
- Bật DynamoDB Streams và viết Outbox Publisher Lambda.
- Xử lý PutEvents partial failure và thêm scheduled sweeper cho PENDING outbox cũ.

**Deliverable:** tạo order một lần về mặt nghiệp vụ dù client retry; OrderCreated không bị mất khi publisher tạm lỗi.

### Giai đoạn 3: EventBridge và Step Functions

- Tạo custom event bus và rule OrderCreated target Saga Starter Lambda.
- Chọn Standard workflow, viết Task/Choice states và Retry/Catch.
- Lưu operation references vào workflow state.
- Tạo execution name ổn định từ sagaId và xử lý duplicate StartExecution.

**Deliverable:** một order có một saga execution có thể theo dõi.

### Giai đoạn 4: xây dựng participants

- Implement Order, Inventory, Payment và Shipping handlers.
- Tạo DynamoDB tables và conditional writes.
- Viết idempotency logic.
- Viết outbox record trong local transaction.

**Deliverable:** unit tests và service contracts.

### Giai đoạn 5: compensation và manual review

- Viết compensation theo thứ tự ngược và bảo đảm no-op khi lặp.
- Phân biệt business failure và technical failure.
- Thêm bounded retry/backoff.
- Khi compensation lỗi, ghi COMPENSATION_PENDING/MANUAL_REVIEW và cảnh báo.

**Deliverable:** compensation workflow và operator runbook.

### Giai đoạn 6: notification, security và observability

- Route OrderConfirmed/OrderCancelled tới SQS và xây consumer độc lập.
- Scope IAM roles, bật KMS, Secrets Manager và API authorizer.
- Thêm structured logs, metrics, tracing, alarms và dashboard.
- Kiểm tra PII/secret redaction và cost budget.

**Deliverable:** security review, dashboard và runbook.

### Giai đoạn 7: kiểm thử và phát hành

- Chạy acceptance tests.
- Mô phỏng lỗi từng participant.
- Kiểm tra compensation và manual review.
- Đối chiếu order, inventory và payment state.
- Demo duplicate handling và DLQ redrive.

**Deliverable:** demo, test report, architecture decision records, deployment instructions và cost estimate.

## 31. Tiêu chí nghiệm thu

Capstone được xem là đạt khi:

- Tạo order trả 202 và có orderId/sagaId.
- Một request lặp với cùng idempotency key không tạo order mới.
- Happy path đưa order tới CONFIRMED.
- Inventory reservation không cho oversell khi có concurrent requests.
- Payment authorize/capture không tạo giao dịch duplicate khi retry.
- Payment failure giải phóng inventory và cập nhật order state.
- Shipment failure kích hoạt compensation theo đúng thứ tự.
- Compensation failure chuyển COMPENSATION_PENDING và tạo cảnh báo.
- Domain events được phát sau khi local transaction commit.
- Outbox publisher xử lý partial PutEvents failure, duplicate và pending-event recovery.
- EventBridge rule gọi Saga Starter; Starter deduplicate và khởi chạy Step Functions Standard theo sagaId.
- Consumer deduplicate event lặp.
- SQS poison messages vào DLQ và có hướng dẫn redrive.
- PaymentUnknown được reconcile với provider trước khi retry side effect.
- Compensation failure chuyển MANUAL_REVIEW và có audit record.
- CloudWatch dashboard truy vết được một saga bằng sagaId.
- IAM roles chỉ có quyền trên tài nguyên cần thiết.
- Logs và event payload không chứa payment secrets hoặc thẻ thô.
- Có tài liệu triển khai, kiểm thử, cleanup và ước lượng chi phí.

## 32. Chi phí và giới hạn vận hành

Các thành phần tính phí theo cách khác nhau:

- API Gateway theo số request và loại API.
- Lambda theo invocation, duration và memory.
- Step Functions Standard theo state transitions.
- DynamoDB theo read/write capacity hoặc on-demand requests, storage và Streams.
- EventBridge theo events/operations.
- SQS theo requests, payload và tính năng sử dụng.
- CloudWatch theo logs ingestion/storage, metrics và alarms.
- X-Ray theo traces.
- KMS theo key và API requests.
- NAT Gateway hoặc data transfer có thể trở thành chi phí đáng kể nếu Lambda trong VPC gọi internet.

Kiểm soát chi phí:

- Dùng on-demand DynamoDB cho workload demo có lưu lượng khó dự báo.
- Giữ payload nhỏ, tránh gọi service thừa.
- Đặt log retention thay vì giữ log vô hạn.
- Giới hạn retry và timeout.
- Không retry business errors.
- Tạo budget notifications cho sandbox account.
- Dọn queue messages, test records và secrets không còn dùng.
- Theo dõi NAT data processing nếu Lambda cần outbound provider access.

Không đưa một giá cố định vào thiết kế. Tính chi phí theo Region, request volume, state transitions, duration, payload size và retention thực tế bằng AWS Pricing Calculator.

| Dịch vụ | Cost driver chính | Cách kiểm soát |
|---|---|---|
| API Gateway | Requests và data transfer | Throttling; cache read path khi phù hợp |
| Lambda | Invocation, duration, memory và concurrency | Tối ưu handler, timeout và reserved concurrency |
| Step Functions Standard | State transitions | Tránh polling/state transitions không cần thiết |
| DynamoDB | Read/write requests, storage, Streams và backups | Chọn access patterns, On-Demand cho tải khó dự báo, tránh hot partition |
| EventBridge | Events ingested/processed, archive và replay | Payload gọn, rule patterns chính xác, retention có chủ đích |
| SQS | Requests, payload và DLQ retention | Batch receive, visibility timeout và consumer throughput |
| CloudWatch/X-Ray | Log ingestion/storage, metrics, alarms và traces | Redaction, sampling và retention theo môi trường |
| KMS/Secrets Manager | Key, secret storage và API requests | Cache secret an toàn, reuse SDK clients |

Để scale, giới hạn concurrency của Payment adapter theo quota provider; đặt reserved concurrency cho participant quan trọng; dùng SQS buffer cho burst; chọn partition key phân tán; theo dõi hot SKU và contention. Inventory SKU có traffic rất cao có thể cần sharded counters hoặc reservation strategy riêng sau khi conditional-write design cơ bản đã được kiểm chứng.

## 33. Runbook vận hành

### Saga bị kẹt

1. Tra cứu sagaId trong Step Functions.
2. Xác định state đang chạy hoặc lỗi.
3. Đọc error name/cause và participant logs.
4. Kiểm tra dependency: Lambda throttling, DynamoDB condition conflict, provider timeout.
5. Không start saga mới bằng key khác trước khi xác định trạng thái side effects.

### Payment outcome không rõ

1. Lấy payment idempotency key và provider reference.
2. Query provider transaction status.
3. Nếu đã capture, ghi nhận capture reference và tiếp tục reconciliation.
4. Nếu chưa capture, quyết định retry theo provider contract.
5. Không gửi một charge mới chỉ vì Lambda timeout.

### Queue có DLQ messages

1. Xem DLQ depth và oldest message age.
2. Kiểm tra error metadata, schema version, consumer deployment.
3. Sửa lỗi schema/permission/dependency.
4. Chạy thử một message trong test.
5. Redrive theo batch nhỏ.
6. Theo dõi duplicate handling và business state sau redrive.

### EventBridge target DLQ

1. Kiểm tra event envelope, target ARN, target role và delivery error.
2. Xác định saga/consumer đã nhận event trước đó chưa bằng sagaId/eventId.
3. Sửa permission, target configuration hoặc dependency.
4. Replay/redrive theo batch nhỏ; giữ nguyên business eventId để deduplicate.
5. Theo dõi target delivery metrics và DLQ depth sau recovery.

### Compensation thất bại

1. Giữ order ở COMPENSATION_PENDING hoặc MANUAL_REVIEW.
2. Lưu compensation action, request ID, provider reference và error.
3. Query trạng thái thực tế của payment/carrier/inventory.
4. Chỉ retry compensation với idempotency key cũ và trạng thái đã xác minh.
5. Đối soát order, stock và payment trước khi đóng case.

## 34. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi nhiều database trong một Lambda rồi giả định ACID toàn cục | Partial commits | Saga với local transactions và compensation |
| Publish event sau DB write nhưng không có outbox | Event bị mất hoặc event giả | Transactional outbox |
| Không có idempotency key | Duplicate orders/charges | Stable keys ở API và participants |
| Chỉ dựa vào Step Functions exactly-once | External side effect bị lặp khi outcome mơ hồ | Idempotency và provider reconciliation |
| Compensation chỉ là xóa record | Mất audit, không đảo external side effect | Business compensation rõ ràng |
| Dùng một queue cho mọi consumer | Consumer chậm ảnh hưởng nhau | Queue riêng theo consumer |
| Không có DLQ | Poison messages lặp vô hạn hoặc bị mất dấu | DLQ, alarms và redrive runbook |
| Event chứa quá nhiều PII | Rủi ro data exposure | Minimal event payload |
| Không version event schema | Deploy consumer mới làm hỏng message cũ | Schema version và backward compatibility |
| Retry tất cả errors | Tăng cost, kéo dài failure | Error taxonomy và bounded retry |
| Không dùng conditional stock update | Oversell | Conditional writes/transactions |
| Không có semantic lock | Hai saga ghi đè nhau | Optimistic concurrency và valid transitions |

## 35. Bài tập tự luyện

1. Vì sao order workflow cần saga khi các service sở hữu database riêng?
2. Saga orchestration khác choreography thế nào?
3. Vì sao chọn Step Functions Standard cho order saga?
4. Domain event khác command như thế nào?
5. EventBridge và SQS có trách nhiệm khác nhau ra sao?
6. Vì sao API create order nên trả 202 Accepted?
7. Idempotency key giải quyết lỗi gì ở API boundary?
8. Vì sao không tin giá và customer ID do client gửi?
9. Inventory reservation cần conditional write nào?
10. Vì sao payment adapter cần provider idempotency key?
11. Compensation khác database rollback thế nào?
12. Nếu capture payment timeout, vì sao không retry charge ngay?
13. Transactional outbox giải quyết dual-write ra sao?
14. Vì sao outbox consumer vẫn cần deduplication?
15. aggregateVersion giúp xử lý vấn đề nào?
16. Vì sao không lưu toàn bộ order payload trong Step Functions state?
17. EventBridge target DLQ khác SQS consumer DLQ thế nào?
18. Khi nào nên dùng FIFO queue?
19. Semantic lock bảo vệ order workflow ra sao?
20. Nếu compensation thất bại, order nên ở trạng thái nào?
21. Vì sao Standard workflow exactly-once không thay thế participant idempotency?
22. Các metric nào giúp phát hiện queue backlog?
23. Làm thế nào redrive DLQ an toàn?
24. Những dữ liệu nào không nên xuất hiện trong event/log payload?
25. Tiêu chí nào chứng minh hệ thống không oversell?
26. Vì sao SQS FIFO deduplication window không thay thế idempotency trong consumer?
27. Vì sao lỗi gửi email/SMS không nên tự động hủy order đã CONFIRMED?

### Gợi ý đáp án

1. Không có một ACID transaction bao trùm các datastore/provider; saga điều phối local transactions và compensation.
2. Orchestration có coordinator trung tâm; choreography để participants phản ứng với events.
3. Workflow dài, cần durable execution, Retry/Catch và execution history.
4. Event mô tả điều đã xảy ra; command yêu cầu thực hiện một hành động.
5. EventBridge định tuyến events; SQS buffer và tách tốc độ consumer.
6. Workflow bất đồng bộ có thể kéo dài; client nhận order reference rồi truy vấn status.
7. Ngăn request retry tạo nhiều orders hoặc payment attempts.
8. Client có thể sửa payload; server phải lấy identity và price từ nguồn tin cậy.
9. Update available quantity chỉ khi available >= requested, kết hợp version/reservation condition.
10. Retry có thể lặp request sau timeout; provider key giúp nhận diện cùng một ý định thanh toán.
11. Compensation là business operation mới, có thể thất bại và cần audit.
12. Provider có thể đã capture dù response bị mất; phải query status trước.
13. Entity và outbox event được ghi trong cùng local transaction.
14. Stream/publisher có thể giao record lại hoặc crash sau khi publish.
15. Phát hiện event cũ, thiếu hoặc đến sai thứ tự cho cùng aggregate.
16. Payload có quota, dễ chứa PII và tăng chi phí; chỉ truyền IDs/references.
17. EventBridge DLQ giữ lỗi delivery tới target; SQS DLQ giữ message consumer xử lý thất bại.
18. Khi strict ordering theo message group là yêu cầu thật sự.
19. Chặn transition xung đột và bảo vệ state/version.
20. COMPENSATION_PENDING hoặc MANUAL_REVIEW, không giả vờ đã rollback hoàn tất.
21. Side effect bên ngoài có thể đã commit nhưng caller chưa nhận response; retry/duplicate vẫn cần được xử lý.
22. ApproximateAgeOfOldestMessage, visible messages, DLQ depth và Lambda throttles/errors.
23. Sửa nguyên nhân, thử message, redrive batch nhỏ và deduplicate.
24. Tokens, PAN/CVV, secrets, bearer credentials và PII không cần thiết.
25. Concurrent test chứng minh tổng reservations không vượt stock khả dụng.
26. Deduplication window của FIFO có giới hạn; consumer vẫn có thể nhận lại message sau timeout, redrive hoặc side effect không rõ kết quả.
27. Notification là side effect sau commit; lỗi gửi thông báo cần retry/DLQ riêng và không làm thay đổi trạng thái giao dịch đã hoàn tất.

## 36. Câu hỏi phỏng vấn

### Saga có cung cấp ACID transaction trên nhiều microservices không?

Không. Saga tạo eventual consistency bằng chuỗi local transactions và compensating actions. Business phải chấp nhận các trạng thái trung gian và có quy trình xử lý compensation thất bại.

### Vì sao Step Functions orchestration phù hợp với order saga?

Workflow có nhiều bước, nhánh lỗi và compensation. Step Functions Standard cung cấp durable orchestration, retry/catch và execution history để vận hành.

### EventBridge có thay SQS được không?

EventBridge phù hợp routing theo event patterns và fan-out. SQS phù hợp buffer, consumer-controlled polling và backpressure. Nhiều kiến trúc dùng cả hai.

### Transactional outbox có bảo đảm event chỉ phát đúng một lần không?

Không. Outbox bảo đảm entity và event record được commit cùng nhau. Publisher có thể phát lại sau crash; consumers vẫn cần idempotency/deduplication.

### Vì sao cần idempotency ở cả API, saga participant và event consumer?

Mỗi boundary có nguồn retry riêng. API client, Step Functions, provider adapter, EventBridge và SQS đều có thể lặp request/message; idempotency phải được enforce ở nơi side effect xảy ra.

### Nếu payment đã capture nhưng order confirmation thất bại thì sao?

Query provider để xác nhận capture, sau đó thực hiện refund theo business policy hoặc chuyển manual review. Không xóa order và giả định payment đã rollback.

### Làm thế nào tránh oversell khi hai order cùng mua SKU cuối cùng?

Dùng conditional update/transaction kiểm tra available quantity và version. Chỉ một transaction có thể reserve thành công; request còn lại nhận conflict/out-of-stock.

### Vì sao không nên dùng một Lambda role cho tất cả services?

Role rộng làm tăng blast radius. Mỗi service nên chỉ đọc/ghi datastore và secret mà nó sở hữu.

### Khi nào dùng choreography thay orchestration?

Khi có ít participants, event flow đơn giản và các services độc lập phản ứng với event. Khi cần điều phối nhiều bước, timeout, branch và compensation rõ ràng, orchestration dễ quan sát hơn.

### Làm thế nào redrive DLQ mà không tạo duplicate shipment/refund?

Sửa nguyên nhân, kiểm tra business state, dùng idempotency keys cũ và consumer deduplication. Redrive theo batch nhỏ rồi đối soát kết quả.

### Vì sao SQS FIFO không loại bỏ nhu cầu idempotency?

FIFO giữ thứ tự theo MessageGroupId và có deduplication window hữu hạn. Consumer vẫn cần persistent idempotency vì retry, visibility timeout, redrive hoặc timeout sau side effect có thể khiến cùng một business operation được xử lý lại.

## 37. Checklist bàn giao capstone

### Business và architecture

- [ ] Order lifecycle và invariants được định nghĩa.
- [ ] Saga success path và compensation path có sơ đồ.
- [ ] Service boundaries và data ownership rõ ràng.
- [ ] Domain events và commands được phân biệt.
- [ ] API và event schemas có version.
- [ ] EventBridge OrderCreated trigger đi qua outbox và Saga Starter có idempotency theo sagaId.

### Reliability

- [ ] API idempotency hoạt động.
- [ ] Participant operations idempotent.
- [ ] Payment provider reconciliation có sẵn.
- [ ] Inventory dùng conditional writes.
- [ ] Outbox ngăn dual-write.
- [ ] Outbox sweeper khôi phục PENDING records cũ.
- [ ] Event consumers deduplicate và kiểm tra aggregate version.
- [ ] Retry có backoff, timeout và error taxonomy.
- [ ] Compensation failure có manual review.
- [ ] EventBridge và SQS DLQs có alarm/redrive runbook.
- [ ] Visibility timeout, maxReceiveCount và partial batch response được cấu hình phù hợp.

### Security

- [ ] API authentication/authorization hoạt động.
- [ ] IAM roles tách theo service.
- [ ] Secrets lưu trong Secrets Manager.
- [ ] DynamoDB/SQS/log encryption phù hợp.
- [ ] Payment card data thô không được lưu/log.
- [ ] Event payload tối thiểu và không lộ PII.
- [ ] CloudTrail và audit records được cấu hình.

### Operations và delivery

- [ ] Correlation ID xuyên API, saga, events và consumers.
- [ ] Dashboard có saga duration, failure, compensation và queue age.
- [ ] Alerts cho DLQ, payment failures và stuck sagas.
- [ ] Unit/integration/failure-injection tests pass.
- [ ] Có IaC, CI/CD và versioned state machine.
- [ ] Có hướng dẫn deploy, rollback, cleanup và ước lượng chi phí.
- [ ] Demo chứng minh happy path, duplicate request, payment failure và compensation failure.
- [ ] Có dashboard cho PaymentUnknown, compensation failures, DynamoDB conflicts và queue age.

## 38. Tài liệu tham khảo chính thức

### Saga và microservices

- [Saga orchestration pattern - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html)
- [Saga choreography pattern - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-choreography.html)
- [Saga patterns - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-patterns.html)
- [Choosing your coordination approach](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-integrating-microservices/choosing-approach.html)
- [Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

### Step Functions

- [Choosing workflow type](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
- [Handling errors in Step Functions workflows](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [Redrive Step Functions executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)
- [Invoke Lambda with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html)
- [Amazon States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html)

### EventBridge, SQS và DynamoDB

- [EventBridge event buses](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus.html)
- [EventBridge retry policies](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [EventBridge dead-letter queues](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html)
- [Archive and replay EventBridge events](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive.html)
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [SQS FIFO delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html)
- [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)

### Lambda reliability và security

- [Powertools for AWS Lambda Java - Idempotency](https://docs.aws.amazon.com/powertools/java/latest/utilities/idempotency/)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [CloudWatch Logs for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [X-Ray with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS KMS best practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)


