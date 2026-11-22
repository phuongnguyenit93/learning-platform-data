# Thiết kế ví dụ đặt hàng, tồn kho và thanh toán theo ranh giới rõ ràng với Java và Spring

Một luồng đặt hàng thường liên quan đến nhiều quy tắc khác nhau: xác nhận đơn, giữ tồn kho, ủy quyền thanh toán, xử lý từ chối, hoàn tác khi một bước thất bại và thông báo kết quả cho khách hàng. Nếu tất cả logic, bảng dữ liệu và tích hợp bên ngoài được đặt trong một service lớn, hệ thống ban đầu có thể dễ viết nhưng nhanh chóng trở nên khó thay đổi. Nếu chia quá nhỏ mà các service vẫn truy cập chung database hoặc phải deploy cùng nhau, kiến trúc phân tán cũng không tạo được sự độc lập.

Bài học này xây dựng một ví dụ Microservices bằng Java và Spring, tập trung vào ba năng lực: **Order**, **Inventory** và **Payment**. Mỗi năng lực có trách nhiệm nghiệp vụ, dữ liệu và contract riêng. Order điều phối hành trình mua hàng; Inventory quản lý số lượng có thể bán và việc giữ hàng; Payment quản lý authorization, capture, refund và tương tác với cổng thanh toán.

Thiết kế cần giữ được các ranh giới sau:

- **Order Service** sở hữu đơn hàng, trạng thái đơn và tiến trình checkout.
- **Inventory Service** sở hữu số lượng tồn, reservation và quy tắc giữ/giải phóng hàng.
- **Payment Service** sở hữu payment intent, authorization, capture, void và refund.
- Các service giao tiếp qua API hoặc event contract đã công bố. Service consumer không truy cập trực tiếp database của provider.
- Không tạo một transaction ACID xuyên ba database. Workflow dùng saga, idempotency, outbox/inbox và các thao tác bù trừ.

Bài viết thuộc nhóm **Java và Spring** trong kiến trúc hệ thống Microservices. Các đoạn mã là ví dụ thiết kế để giải thích ranh giới và cách phối hợp; cần bổ sung cấu hình, validation, exception mapping, bảo mật, migration và test theo ứng dụng thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định trách nhiệm và quyền sở hữu dữ liệu của Order, Inventory và Payment.
- Phân biệt domain model, DTO/API contract, persistence entity và event schema.
- Thiết kế luồng đặt hàng có giữ hàng và thanh toán mà không dùng transaction phân tán.
- Sử dụng saga orchestration để điều phối các bước và compensation khi lỗi.
- Hiểu vai trò của idempotency key, transactional outbox, inbox/deduplication và retry.
- Tổ chức code Spring Boot theo domain/application/adapter/infrastructure.
- Thiết kế endpoint, request/response, event và trạng thái nghiệp vụ rõ ràng.
- Xử lý timeout không rõ kết quả, duplicate event, message đến trễ và eventual consistency.
- Kiểm thử từng service, contract giữa service và toàn bộ workflow.
- Triển khai quan sát, bảo mật, versioning và vận hành phù hợp.

## 2. Bài toán nghiệp vụ

Một khách hàng gửi yêu cầu tạo đơn hàng gồm các mặt hàng và phương thức thanh toán. Hệ thống cần:

1. Kiểm tra request và xác định giá trị đơn theo chính sách đáng tin cậy.
2. Tạo bản ghi đơn hàng với trạng thái ban đầu.
3. Yêu cầu Inventory giữ số lượng cho từng SKU.
4. Nếu giữ hàng thành công, yêu cầu Payment authorization.
5. Nếu payment bị từ chối, giải phóng reservation.
6. Nếu cả hai bước thành công, xác nhận đơn hàng.
7. Nếu một thao tác có kết quả không rõ do timeout, truy vấn trạng thái bằng idempotency key trước khi quyết định retry hoặc compensation.
8. Gửi event để các luồng Fulfillment, Notification và Analytics tiếp tục xử lý.

Không nên hiểu “đặt hàng thành công” là mọi thao tác bên dưới đã hoàn tất đồng thời trong một transaction database. Hệ thống phân tán cần trạng thái trung gian có ý nghĩa và khả năng phục hồi.

### 2.1. Các giả định của ví dụ

- Một order có thể chứa nhiều SKU.
- Inventory quản lý số lượng khả dụng theo SKU và có thể giữ hàng tạm thời.
- Payment gateway hỗ trợ một cơ chế tham chiếu/idempotency phù hợp hoặc Payment Service có lớp chống lặp riêng.
- Order Service điều phối saga.
- Các service có database riêng về mặt ownership.
- Message broker được dùng cho event/command bất đồng bộ.
- Checkout có thể trả về trạng thái PENDING trong khi workflow hoàn tất.

Trong hệ thống thật, cần quyết định khi nào capture tiền: ngay sau khi authorization, khi giao hàng hoặc theo chính sách fulfillment. Ví dụ này dùng authorization trước; capture có thể là bước sau khi đơn được xác nhận hoặc khi nghiệp vụ cho phép.

## 3. Xác định ranh giới trách nhiệm

### 3.1. Order Service

Order Service sở hữu:

- Order ID và tenant/customer reference phù hợp.
- Danh sách item đã được chấp nhận cho đơn.
- Snapshot giá và currency tại thời điểm đặt.
- Trạng thái nghiệp vụ của đơn.
- Lịch sử các bước saga và correlation ID.
- Quyết định khi nào order được xác nhận hoặc hủy.
- API để khách hàng/nhân viên tra cứu đơn.
- Event OrderPlaced, OrderConfirmed, OrderCancelled hoặc trạng thái tương ứng.

Order Service **không** sở hữu:

- Số lượng tồn kho chính thức.
- Logic trừ tồn kho trong database của Inventory.
- Payment account, gateway token hoặc trạng thái giao dịch chính thức.
- Schema nội bộ của Inventory/Payment.

Order lưu thông tin cần thiết để mô tả đơn tại thời điểm mua. Nó có thể lưu SKU, tên sản phẩm, đơn giá, currency và quantity như snapshot, nhưng snapshot này không biến Order thành owner của catalog hay inventory.

### 3.2. Inventory Service

Inventory Service sở hữu:

- Stock theo SKU và location/warehouse.
- Available quantity, reserved quantity hoặc ledger tương ứng.
- Reservation ID, order reference và thời hạn giữ hàng.
- Quy tắc không cho số lượng khả dụng xuống dưới mức cho phép.
- Thao tác reserve, commit/consume và release.
- Event InventoryReserved, InventoryRejected, ReservationReleased.

Inventory Service không cần biết chi tiết giao diện checkout hoặc cách Payment gateway hoạt động. Nó chỉ cần biết yêu cầu giữ một số lượng cho một order với mã tham chiếu duy nhất.

### 3.3. Payment Service

Payment Service sở hữu:

- Payment ID và payment attempt.
- Trạng thái authorization/capture/void/refund.
- Idempotency key và external transaction reference.
- Token/payment method reference theo chính sách bảo mật.
- Tích hợp gateway, retry và reconciliation.
- Audit trail và kết quả giao dịch.

Payment Service không đọc bảng Order để tự suy ra số tiền. Nó nhận amount/currency và order reference qua contract đã được xác thực. Order là nơi xác định khoản tiền cần thanh toán; Payment là nơi chịu trách nhiệm xử lý giao dịch và trạng thái payment.

### 3.4. Bảng ownership

| Khái niệm | Owner | Consumer |
|---|---|---|
| Order status | Order | Web/Mobile, Fulfillment |
| Order item snapshot | Order | Notification, Reporting |
| Available stock | Inventory | Order qua API/command |
| Reservation | Inventory | Order qua API/event |
| Payment authorization | Payment | Order qua API/event |
| Gateway transaction ID | Payment | Support qua Payment API |
| Checkout saga state | Order | Operations/Support qua API |
| Customer identity | Identity/Customer context | Ba service theo nhu cầu |

Nếu hai service cần cùng một thông tin, hãy xác định ai là nguồn sự thật và consumer nhận dữ liệu qua contract hoặc projection. Không chia sẻ JPA entity hoặc quyền ghi database để tiết kiệm vài dòng code.

## 4. Sơ đồ kiến trúc tổng thể

~~~text
                         Client
                           |
                           v
                    API Gateway / BFF
                           |
                           v
                  +-------------------+
                  |   Order Service   |
                  | API + Saga        |
                  | Order DB + Outbox |
                  +----+----------+---+
                       |          |
            Reserve    |          | Authorize
            Inventory  |          | Payment
                       v          v
              +----------------+  +----------------+
              | Inventory      |  | Payment        |
              | Service        |  | Service        |
              | Stock DB       |  | Payment DB     |
              | Reservation    |  | Gateway Adapter|
              +-------+--------+  +-------+--------+
                      |                   |
                      v                   v
                Inventory Event      Gateway Provider

           Order / Inventory / Payment Outbox
                           |
                           v
                     Message Broker
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
        Fulfillment    Notification    Analytics
~~~

Sơ đồ mô tả các ranh giới logic. Một triển khai có thể dùng REST cho thao tác cần phản hồi ngay và broker cho event/retry. Có thể dùng message broker cho cả command và event nếu có correlation, reply channel và timeout policy rõ. Tránh đồng thời duy trì nhiều cách giao tiếp không có lý do.

## 5. Luồng đặt hàng và trạng thái nghiệp vụ

Một luồng saga minh họa:

~~~text
Client
  |
  | POST /orders + Idempotency-Key
  v
Order Service
  |
  | 1. Create order PENDING
  | 2. Save saga state + outbox command
  v
Inventory Service
  |
  | 3. Reserve stock
  |
  +---- rejected ------------------------------+
  |                                             |
  v                                             v
Reserved                                  Order CANCELLED
  |
  | 4. Request payment authorization
  v
Payment Service
  |
  +---- declined/failed ----------------------+
  |                                           |
  v                                           v
Authorized                              Release reservation
  |                                           |
  | 5. Confirm order                          v
  v                                     Order CANCELLED
Order CONFIRMED
  |
  v
OrderConfirmed event
~~~

Một triển khai bất đồng bộ có thể trả HTTP 202 Accepted cùng orderId và trạng thái PENDING, rồi client polling hoặc nhận notification. Một triển khai đồng bộ có thể đợi một khoảng thời gian giới hạn nhưng vẫn cần trả trạng thái “đang xử lý” nếu workflow chưa xong.

### 5.1. State machine của Order

| Trạng thái | Ý nghĩa | Chuyển trạng thái hợp lệ thường gặp |
|---|---|---|
| PENDING | Đã nhận yêu cầu, đang kiểm tra các bước | INVENTORY_RESERVED, CANCELLED |
| INVENTORY_RESERVED | Đã giữ đủ số lượng | PAYMENT_PENDING, CANCELLED |
| PAYMENT_PENDING | Đang xử lý authorization | PAYMENT_AUTHORIZED, PAYMENT_FAILED, PAYMENT_UNKNOWN |
| PAYMENT_UNKNOWN | Kết quả gateway chưa xác định | PAYMENT_AUTHORIZED, PAYMENT_FAILED, MANUAL_REVIEW |
| PAYMENT_AUTHORIZED | Tiền đã được authorize | CONFIRMED, COMPENSATION_PENDING |
| CONFIRMED | Đơn được xác nhận | FULFILLING, CANCEL_REQUESTED |
| CANCELLED | Đơn đã hủy theo quy tắc nghiệp vụ | Terminal hoặc trạng thái xử lý hủy riêng |
| COMPENSATION_PENDING | Đang hoàn tác reservation/payment | CANCELLED, MANUAL_REVIEW |

Tên và số trạng thái có thể đơn giản hóa tùy sản phẩm. Điều quan trọng là mọi chuyển trạng thái phải được kiểm tra từ trạng thái hiện tại, tránh một event cũ làm order đã CONFIRMED quay về PENDING.

### 5.2. State machine của Inventory Reservation

| Trạng thái | Ý nghĩa |
|---|---|
| REQUESTED | Đã nhận yêu cầu reserve |
| RESERVED | Đã giữ số lượng trong thời hạn |
| COMMITTED | Reservation đã được dùng cho đơn/fulfillment |
| RELEASED | Đã giải phóng số lượng |
| EXPIRED | Hết thời hạn giữ theo policy |
| REJECTED | Không đủ hàng hoặc request không hợp lệ |

### 5.3. State machine của Payment

| Trạng thái | Ý nghĩa |
|---|---|
| CREATED | Đã tạo payment attempt |
| AUTHORIZING | Đang gọi gateway |
| AUTHORIZED | Gateway xác nhận authorization |
| DECLINED | Gateway từ chối rõ ràng |
| UNKNOWN | Timeout hoặc kết quả chưa thể kết luận |
| CAPTURED | Đã capture tiền |
| VOIDED | Authorization đã được hủy |
| REFUND_PENDING | Đang xử lý refund |
| REFUNDED | Đã hoàn tiền |
| FAILED | Lỗi cuối cùng theo chính sách |

Không gom tất cả lỗi vào FAILED. Timeout có thể xảy ra sau khi gateway đã xử lý thành công; gọi lại một cách mù quáng có thể tạo giao dịch trùng.

## 6. Thiết kế repository theo ranh giới

Một mono-repository vẫn có thể giữ service boundaries rõ:

~~~text
commerce-platform/
  order-service/
    src/main/java/.../order/
      api/
      application/
      domain/
      infrastructure/
    src/test/...
  inventory-service/
    src/main/java/.../inventory/
      api/
      application/
      domain/
      infrastructure/
  payment-service/
    src/main/java/.../payment/
      api/
      application/
      domain/
      infrastructure/
  contracts/
    openapi/
    events/
  platform/
    compose/
    observability/
~~~

Thư mục contracts chỉ chứa schema/giao diện công khai có version. Không đưa entity JPA, repository hoặc internal domain classes của service vào thư viện dùng chung.

Một cách tổ chức package trong mỗi service:

- **api:** Controller, request/response DTO, exception mapping.
- **application:** Use case, command handler, transaction orchestration cục bộ.
- **domain:** Entity/aggregate, value object, domain service, invariant.
- **infrastructure:** JPA repository implementation, HTTP client, broker adapter, outbox relay.

Không bắt buộc dùng đúng tên package. Điều quan trọng là domain không phụ thuộc framework và các adapter là nơi chuyển đổi giữa thế giới bên ngoài với mô hình nghiệp vụ.

## 7. Contract của Order API

Một endpoint tạo đơn:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 6b8c2b2e-unique-client-request

{
  "customerId": "customer-100",
  "items": [
    {
      "sku": "SKU-001",
      "quantity": 2
    },
    {
      "sku": "SKU-002",
      "quantity": 1
    }
  ],
  "paymentMethodToken": "token-reference"
}
~~~

Token trong ví dụ là reference do một quy trình thanh toán an toàn cấp, không phải số thẻ thô. Không lưu hoặc log thông tin thẻ nhạy cảm trong Order Service.

Order Service nên lấy giá từ Catalog/Pricing context hoặc snapshot đã được xác minh ở backend. Không tin unitPrice do client tự gửi. Response có thể là:

~~~json
{
  "orderId": "order-9001",
  "status": "PENDING",
  "createdAt": "2026-11-12T02:30:00Z",
  "statusUrl": "/api/v1/orders/order-9001"
}
~~~

Với HTTP 202, response chỉ xác nhận yêu cầu đã được tiếp nhận. Client cần tra trạng thái qua statusUrl hoặc nhận thông báo. Nếu workflow hoàn tất nhanh, API có thể trả 201/200 theo semantics được công bố; không hứa đơn đã CONFIRMED khi các bước bất đồng bộ chưa hoàn tất.

### 7.1. DTO không phải domain entity

Request:

~~~java
public record PlaceOrderRequest(
    String customerId,
    List<OrderItemRequest> items,
    String paymentMethodToken
) {}

public record OrderItemRequest(
    String sku,
    int quantity
) {}
~~~

Response:

~~~java
public record PlaceOrderResponse(
    String orderId,
    String status,
    Instant createdAt,
    String statusUrl
) {}
~~~

Các DTO này thuộc API layer. Domain model có thể có kiểu OrderId, Money, Quantity, OrderLine và trạng thái dạng enum/value object. Không dùng request DTO làm JPA entity chỉ để giảm số class.

## 8. Domain model của Order

Một ví dụ rút gọn:

~~~java
public enum OrderStatus {
    PENDING,
    INVENTORY_RESERVED,
    PAYMENT_PENDING,
    PAYMENT_UNKNOWN,
    PAYMENT_AUTHORIZED,
    CONFIRMED,
    COMPENSATION_PENDING,
    CANCELLED
}
~~~

~~~java
public record Money(long amountMinor, String currency) {
    public Money {
        if (amountMinor < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency is required");
        }
    }
}
~~~

Dùng đơn vị tiền nhỏ nhất (ví dụ VND đồng hoặc cents tùy currency) và currency code rõ ràng giúp tránh sai số floating point. Với currency có quy tắc số lẻ khác nhau, cần thư viện/chính sách tiền tệ phù hợp thay vì mặc định mọi currency có hai chữ số thập phân.

Aggregate Order nên bảo vệ các invariant của chính Order:

- Order phải có ít nhất một item hợp lệ.
- Quantity dương và có giới hạn.
- Currency thống nhất theo quy tắc.
- Tổng tiền được tính từ snapshot giá đáng tin cậy.
- Không cho transition từ trạng thái terminal về trạng thái ban đầu.
- Chỉ xác nhận khi điều kiện nghiệp vụ được thỏa mãn.

Domain Order không tự trừ tồn kho hoặc gọi gateway. Nó phát sinh ý định nghiệp vụ; application layer điều phối các capability bên ngoài.

## 9. Order application service trong Spring

Controller chỉ tiếp nhận HTTP, validate cấu trúc request và gọi use case:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<PlaceOrderResponse> place(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody PlaceOrderRequest request) {

        PlaceOrderResult result = placeOrder.execute(key, request);

        URI statusUri = URI.create(
            "/api/v1/orders/" + result.orderId()
        );

        return ResponseEntity.accepted()
            .location(statusUri)
            .body(new PlaceOrderResponse(
                result.orderId(),
                result.status().name(),
                result.createdAt(),
                statusUri.toString()
            ));
    }
}
~~~

Use case ghi Order, saga state và outbox command trong **một transaction cục bộ của Order DB**:

~~~java
@Service
class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;
    private final SagaRepository sagas;
    private final OutboxRepository outbox;
    private final OrderFactory orderFactory;

    PlaceOrderService(
            OrderRepository orders,
            SagaRepository sagas,
            OutboxRepository outbox,
            OrderFactory orderFactory) {
        this.orders = orders;
        this.sagas = sagas;
        this.outbox = outbox;
        this.orderFactory = orderFactory;
    }

    @Transactional
    public PlaceOrderResult execute(
            String idempotencyKey,
            PlaceOrderRequest request) {

        var existing = orders.findByIdempotencyKey(idempotencyKey);
        if (existing.isPresent()) {
            return PlaceOrderResult.from(existing.get());
        }

        Order order = orderFactory.createFrom(request, idempotencyKey);
        CheckoutSaga saga = CheckoutSaga.start(order.id());

        orders.save(order);
        sagas.save(saga);

        outbox.append(ReserveInventoryCommand.from(order, saga));

        return PlaceOrderResult.from(order);
    }
}
~~~

Đây là pseudocode có kiểu dữ liệu và method minh họa; cần triển khai uniqueness constraint cho idempotency key và xử lý race condition khi hai request cùng key đến đồng thời. Nếu transaction commit thất bại, cả order và outbox record phải rollback cùng nhau.

**Không gọi Inventory hoặc Payment qua HTTP bên trong transaction database dài.** Gọi mạng trong transaction có thể giữ connection/lock lâu và không thể rollback side effect đã xảy ra ở service khác.

## 10. Order database và outbox

Order Service có thể sở hữu các bảng:

~~~sql
CREATE TABLE orders (
    order_id            VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(64) NOT NULL,
    status              VARCHAR(32) NOT NULL,
    total_minor         BIGINT NOT NULL,
    currency            CHAR(3) NOT NULL,
    idempotency_key     VARCHAR(128) NOT NULL UNIQUE,
    version             BIGINT NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id            VARCHAR(64) NOT NULL,
    line_number         INTEGER NOT NULL,
    sku                 VARCHAR(128) NOT NULL,
    product_name        VARCHAR(255),
    quantity            INTEGER NOT NULL,
    unit_price_minor    BIGINT NOT NULL,
    currency            CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_number)
);

CREATE TABLE checkout_sagas (
    saga_id             VARCHAR(64) PRIMARY KEY,
    order_id            VARCHAR(64) NOT NULL UNIQUE,
    state               VARCHAR(40) NOT NULL,
    inventory_reservation_id VARCHAR(64),
    payment_id          VARCHAR(64),
    last_error_code     VARCHAR(64),
    version             BIGINT NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE outbox_messages (
    message_id          VARCHAR(64) PRIMARY KEY,
    aggregate_id        VARCHAR(64) NOT NULL,
    event_type          VARCHAR(128) NOT NULL,
    payload             TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    published_at        TIMESTAMP
);
~~~

Schema là ví dụ; chọn kiểu cột, index, JSON/JSONB và timestamp theo database thực tế. Outbox relay đọc các record chưa publish và gửi lên broker. Việc publish có thể lặp lại nếu relay crash sau khi gửi nhưng trước khi đánh dấu published; consumer cần idempotency.

### 10.1. Transactional outbox giải quyết điều gì?

Nếu code làm:

1. Commit Order vào database.
2. Publish OrderPlaced lên broker.

Process có thể chết giữa hai bước, tạo order nhưng không có event. Nếu publish trước commit, consumer có thể nhận event cho order chưa tồn tại.

Outbox ghi business state và message trong cùng transaction local. Một publisher độc lập gửi message sau commit. Đây là đảm bảo ghi nhận ý định phát event cùng dữ liệu; nó **không** tự bảo đảm message chỉ được giao đúng một lần.

### 10.2. Outbox relay

Có thể triển khai bằng polling, CDC hoặc connector phù hợp. Khi polling:

- Chọn record chưa publish theo batch có giới hạn.
- Gửi message có messageId ổn định.
- Đánh dấu published sau khi broker xác nhận.
- Retry có backoff khi broker lỗi.
- Theo dõi tuổi record chưa publish và tốc độ backlog.
- Có chính sách retention/cleanup.
- Không xóa record chưa có bằng chứng đã publish.

Nếu dùng CDC, cần quản lý offset, schema và quyền truy cập log thay đổi database.

## 11. Inventory API và reservation

Inventory không chỉ có một endpoint “trừ stock”. Nó cần mô hình reservation để tránh giữ hàng vô thời hạn và để saga có thể compensation.

Một contract:

~~~http
POST /api/v1/reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: reserve-order-9001

{
  "reservationId": "res-order-9001",
  "orderId": "order-9001",
  "expiresAt": "2026-11-12T02:45:00Z",
  "items": [
    {"sku": "SKU-001", "quantity": 2},
    {"sku": "SKU-002", "quantity": 1}
  ]
}
~~~

Response khi thành công:

~~~json
{
  "reservationId": "res-order-9001",
  "status": "RESERVED",
  "expiresAt": "2026-11-12T02:45:00Z"
}
~~~

Response từ chối cần mã lỗi ổn định, ví dụ INSUFFICIENT_STOCK, SKU_NOT_SELLABLE hoặc RESERVATION_EXPIRED. Không để consumer phải parse message text để quyết định nghiệp vụ.

### 11.1. Schema Inventory

~~~sql
CREATE TABLE inventory_stock (
    sku                 VARCHAR(128) NOT NULL,
    warehouse_id        VARCHAR(64) NOT NULL,
    available_quantity  INTEGER NOT NULL,
    reserved_quantity   INTEGER NOT NULL,
    version              BIGINT NOT NULL,
    PRIMARY KEY (sku, warehouse_id),
    CHECK (available_quantity >= 0),
    CHECK (reserved_quantity >= 0)
);

CREATE TABLE inventory_reservations (
    reservation_id      VARCHAR(64) PRIMARY KEY,
    order_id            VARCHAR(64) NOT NULL UNIQUE,
    status              VARCHAR(32) NOT NULL,
    expires_at          TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE inventory_reservation_items (
    reservation_id      VARCHAR(64) NOT NULL,
    sku                 VARCHAR(128) NOT NULL,
    warehouse_id        VARCHAR(64) NOT NULL,
    quantity            INTEGER NOT NULL,
    PRIMARY KEY (reservation_id, sku, warehouse_id)
);
~~~

Inventory DB là nguồn sự thật của stock/reservation. Order chỉ lưu reservation ID và kết quả cần thiết để mô tả tiến trình.

### 11.2. Giữ hàng phải atomic ở Inventory

Một thao tác cập nhật có điều kiện:

~~~sql
UPDATE inventory_stock
SET available_quantity = available_quantity - :quantity,
    reserved_quantity = reserved_quantity + :quantity,
    version = version + 1
WHERE sku = :sku
  AND warehouse_id = :warehouseId
  AND available_quantity >= :quantity;
~~~

Nếu số row được cập nhật bằng 1, thao tác giữ hàng cho SKU đó thành công; nếu bằng 0, cần xác định không đủ hàng hoặc SKU không tồn tại theo contract. Với nhiều item, toàn bộ reservation cần được xử lý trong một transaction cục bộ của Inventory để tránh giữ được một nửa giỏ hàng mà không có trạng thái rõ.

Nếu cùng một SKU xuất hiện nhiều lần trong request, nên gộp quantity trước khi reserve. Với nhiều warehouse, thuật toán phân bổ phải được quyết định trong Inventory, không để Order tự truy cập từng kho.

### 11.3. Reservation và expiry

Reservation cần TTL hoặc thời điểm hết hạn. Một scheduled job có thể tìm reservation RESERVED quá hạn và giải phóng stock. Nhưng job có thể chạy lặp hoặc race với commit/release; chuyển trạng thái cần conditional update/version để chỉ một bên thắng.

Nếu payment timeout và saga đang ở trạng thái UNKNOWN, không nên tự giải phóng reservation quá sớm khi kết quả thanh toán chưa được xác minh. Thời hạn giữ hàng phải phối hợp với deadline, retry và reconciliation của Payment.

## 12. Inventory application service

Use case reserve phải bảo vệ invariant trong transaction local:

~~~java
@Service
class ReserveInventoryService {
    private final InventoryReservationRepository reservations;
    private final StockRepository stock;
    private final InventoryOutbox outbox;

    ReserveInventoryService(
            InventoryReservationRepository reservations,
            StockRepository stock,
            InventoryOutbox outbox) {
        this.reservations = reservations;
        this.stock = stock;
        this.outbox = outbox;
    }

    @Transactional
    public ReservationResult reserve(ReserveInventoryCommand command) {
        var existing = reservations.findById(command.reservationId());
        if (existing.isPresent()) {
            return ReservationResult.from(existing.get());
        }

        var items = normalizeAndValidate(command.items());
        var reservation = InventoryReservation.requested(
            command.reservationId(),
            command.orderId(),
            command.expiresAt()
        );

        reservations.save(reservation);

        for (var item : items) {
            int changed = stock.reserve(
                item.sku(),
                item.warehouseId(),
                item.quantity()
            );
            if (changed != 1) {
                throw new InsufficientStockException(item.sku());
            }
            reservation.addReservedItem(item);
        }

        reservation.markReserved();
        reservations.save(reservation);
        outbox.append(InventoryReservedEvent.from(reservation));

        return ReservationResult.from(reservation);
    }
}
~~~

Nếu một SKU không đủ, exception phải làm rollback mọi cập nhật stock trong transaction Inventory. Khi dùng JPA, kiểm tra transaction rollback rules; checked exception có thể không rollback mặc định tùy cấu hình. Với bulk SQL, cần xử lý số row cập nhật và lock/version phù hợp.

Không đặt logic giữ stock trong Order Service bằng cách cho Order gọi repository Inventory. Điều đó phá data ownership và tạo transaction coupling.

## 13. Payment API và authorization

Payment Service cung cấp một contract tách khỏi gateway cụ thể:

~~~http
POST /api/v1/payment-authorizations HTTP/1.1
Content-Type: application/json
Idempotency-Key: authorize-order-9001

{
  "paymentId": "pay-order-9001",
  "orderId": "order-9001",
  "amountMinor": 44800,
  "currency": "VND",
  "paymentMethodToken": "provider-token-reference"
}
~~~

Response:

~~~json
{
  "paymentId": "pay-order-9001",
  "status": "AUTHORIZED",
  "authorizedAmountMinor": 44800,
  "currency": "VND",
  "providerReference": "provider-ref-abc"
}
~~~

Token phải được quản lý theo chuẩn bảo mật của nhà cung cấp. Không gửi PAN/CVV qua Order Service nếu có thể dùng tokenization; không ghi payment token hoặc dữ liệu nhạy cảm vào log.

### 13.1. Payment không phụ thuộc schema Order

Payment nhận orderId làm reference để đối soát, nhưng không truy vấn Order DB để tính tiền hoặc kiểm tra trạng thái. Nếu Payment cần biết lệnh có hợp lệ, contract phải mang đủ thông tin và có cơ chế authorization/service-to-service trust phù hợp.

### 13.2. Gateway adapter

Application service nên phụ thuộc một port:

~~~java
public interface PaymentGateway {
    GatewayAuthorization authorize(AuthorizationRequest request);
    GatewayResult voidAuthorization(String providerReference);
    GatewayResult capture(String providerReference, Money amount);
    GatewayResult refund(String providerReference, Money amount);
}
~~~

Adapter triển khai giao thức của provider:

~~~java
@Component
class ExternalPaymentGatewayAdapter implements PaymentGateway {
    private final ProviderHttpClient client;

    ExternalPaymentGatewayAdapter(ProviderHttpClient client) {
        this.client = client;
    }

    @Override
    public GatewayAuthorization authorize(AuthorizationRequest request) {
        // Map domain request to provider request.
        // Use provider idempotency/reference when supported.
        // Map provider response into a stable domain result.
        throw new UnsupportedOperationException("Provider adapter example");
    }

    @Override
    public GatewayResult voidAuthorization(String reference) {
        throw new UnsupportedOperationException("Provider adapter example");
    }

    @Override
    public GatewayResult capture(String reference, Money amount) {
        throw new UnsupportedOperationException("Provider adapter example");
    }

    @Override
    public GatewayResult refund(String reference, Money amount) {
        throw new UnsupportedOperationException("Provider adapter example");
    }
}
~~~

Các method có phần thân minh họa để thể hiện port/adapter boundary; production code cần gọi SDK/HTTP client thật, timeout, authentication, error mapping, idempotency và observability. Domain/application không nên biết tên field hoặc exception riêng của gateway.

## 14. Saga orchestration trong Order

Một saga là chuỗi thao tác local của nhiều service. Mỗi thao tác có kết quả và có thể có **compensating action** để bù lại khi workflow không thể tiếp tục.

Trong ví dụ:

| Bước | Service | Thao tác | Compensation |
|---|---|---|---|
| 1 | Order | Tạo order PENDING và saga | Hủy order nếu chưa phát sinh side effect |
| 2 | Inventory | Reserve stock | Release reservation |
| 3 | Payment | Authorize payment | Void authorization |
| 4 | Order | Confirm order | Quy trình cancel theo chính sách |
| 5 | Fulfillment | Bắt đầu thực hiện | Có thể cần cancel/return riêng, không luôn đảo ngược được |

Không phải mọi thao tác đều có thể đảo ngược hoàn toàn. Một email đã gửi không thể “thu hồi”; một shipment đã bàn giao cần quy trình return. Compensation là nghiệp vụ mới có kết quả riêng, không phải rollback ACID.

### 14.1. Vì sao chọn orchestration?

Trong ví dụ này, Order là nơi sở hữu trạng thái checkout và có thể điều phối bước Inventory/Payment. Một saga orchestrator tách riêng cũng có thể hợp lý khi workflow rất phức tạp hoặc nhiều domain dùng chung.

Orchestration giúp:

- Nhìn thấy trạng thái toàn workflow ở một nơi.
- Quy định thứ tự và điều kiện chuyển bước.
- Quản lý timeout, retry, compensation và manual review.
- Dễ truy vấn tiến trình cho support.

Đổi lại, Order/Saga component cần được thiết kế có HA, lưu trạng thái bền vững và không trở thành nơi chứa toàn bộ domain logic của Inventory/Payment.

### 14.2. Saga state machine

~~~text
STARTED
   |
   v
WAITING_FOR_INVENTORY
   |
   +---- InventoryRejected ----> CANCELLED
   |
   v
WAITING_FOR_PAYMENT
   |
   +---- PaymentDeclined ------> COMPENSATING_INVENTORY
   |                                  |
   |                                  v
   |                              CANCELLED
   |
   +---- PaymentUnknown ------> RECONCILING_PAYMENT
   |
   v
PAYMENT_AUTHORIZED
   |
   v
CONFIRMING_ORDER
   |
   +---- success -------------> CONFIRMED
   |
   +---- failure -------------> COMPENSATING_PAYMENT
                                      |
                                      v
                              COMPENSATING_INVENTORY
                                      |
                                      v
                                 CANCELLED
~~~

State machine thực tế cần xử lý event trùng, event đến sai thứ tự, timeout, worker restart và trạng thái không xác định.

## 15. Compensation phải được thiết kế như use case riêng

Ví dụ khi Payment từ chối:

1. Order saga nhận PaymentDeclined.
2. Saga chuyển sang COMPENSATING_INVENTORY.
3. Gửi lệnh ReleaseReservation với reservationId ổn định.
4. Inventory kiểm tra reservation đang RESERVED và release đúng một lần.
5. Inventory phát ReservationReleased.
6. Saga chuyển Order thành CANCELLED với reason PAYMENT_DECLINED.

Nếu release thất bại tạm thời, saga giữ COMPENSATION_PENDING và retry có giới hạn. Không được đánh dấu CANCELLED như thể stock đã được trả lại khi Inventory chưa xác nhận.

Nếu Payment authorization thành công nhưng bước xác nhận order gặp lỗi, Payment Service cần thực hiện void authorization theo idempotency key. Nếu authorization đã capture, có thể phải refund; hai thao tác có semantics và thời gian khác nhau.

### 15.1. Timeout không đồng nghĩa thất bại

Giả sử Payment gateway đã authorize nhưng response bị mất trên mạng. Payment Service thấy timeout. Order không nhận được PaymentAuthorized nên không biết kết quả.

Hành vi an toàn:

- Payment Service đánh dấu trạng thái UNKNOWN/RECONCILIATION_REQUIRED.
- Dùng cùng idempotency key khi truy vấn hoặc retry theo contract của provider.
- Kiểm tra provider reference/transaction status.
- Phát kết quả cuối khi đã xác định.
- Order giữ trạng thái PAYMENT_UNKNOWN và chưa tạo đơn mới cùng key.
- Nếu không thể xác định trong thời hạn, chuyển MANUAL_REVIEW theo runbook.

Nếu coi timeout là DECLINED rồi retry authorization bằng key mới, có thể tạo hai lần authorize.

## 16. Idempotency xuyên các service

Message broker và HTTP client có thể retry. Consumer có thể nhận cùng event nhiều lần. Vì vậy mỗi thao tác có side effect cần idempotency.

Ví dụ key:

~~~text
Order create:          create-order:{client-key}
Inventory reservation: reserve:{orderId}
Payment authorization: authorize:{orderId}:{attempt}
Inventory release:     release:{reservationId}
Payment void:           void:{paymentId}
~~~

Đây là cách đặt tên minh họa; key cần unique trong phạm vi provider/service, không chứa thông tin nhạy cảm và có retention phù hợp.

### 16.1. Idempotency trong database

Có thể tạo unique constraint:

~~~sql
CREATE UNIQUE INDEX uq_orders_idempotency
ON orders(idempotency_key);

CREATE UNIQUE INDEX uq_payment_operation_key
ON payment_operations(idempotency_key);

CREATE UNIQUE INDEX uq_reservation_order
ON inventory_reservations(order_id);
~~~

Khi nhận request trùng key:

- Nếu payload hash giống và thao tác đã hoàn tất, trả kết quả trước đó.
- Nếu thao tác đang xử lý, trả trạng thái hiện tại hoặc response có thể retry.
- Nếu cùng key nhưng payload khác, trả lỗi conflict.
- Không tạo operation mới chỉ vì client timeout và gửi lại.

### 16.2. Inbox/deduplication cho event

Consumer có thể lưu messageId đã xử lý:

~~~sql
CREATE TABLE inbox_messages (
    consumer_name VARCHAR(128) NOT NULL,
    message_id VARCHAR(64) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Trong cùng transaction local, consumer ghi inbox record và cập nhật business state. Nếu messageId đã tồn tại, bỏ qua side effect và xác nhận message theo semantics broker.

Inbox cần retention/cleanup và chiến lược replay. Nếu xóa record quá sớm trong khi broker có thể replay message cũ, duplicate side effect có thể xuất hiện lại.

## 17. Event contract giữa các service

Một event OrderPlaced có thể là:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-12T02:30:00Z",
  "correlationId": "checkout-9001",
  "aggregateId": "order-9001",
  "payload": {
    "orderId": "order-9001",
    "customerId": "customer-100",
    "items": [
      {"sku": "SKU-001", "quantity": 2}
    ],
    "totalMinor": 44800,
    "currency": "VND"
  }
}
~~~

Event nên biểu diễn sự kiện nghiệp vụ đã xảy ra, không phải object persistence dump. Chỉ đưa field consumer cần và được phép sử dụng.

### 17.1. Command và event khác nhau

- **Command:** yêu cầu một hành động, ví dụ ReserveInventory hoặc AuthorizePayment.
- **Event:** thông báo một sự kiện đã xảy ra, ví dụ InventoryReserved hoặc PaymentAuthorized.

Command có thể bị từ chối vì trạng thái nghiệp vụ hiện tại. Event mô tả sự thật đã được ghi nhận. Không đặt tên command theo kiểu event hoàn tất vì consumer sẽ hiểu sai semantics.

### 17.2. Schema evolution

Khi thêm field:

- Xác định default/null/presence semantics.
- Consumer cũ phải bỏ qua field lạ hoặc xử lý theo contract.
- Không đổi ý nghĩa field hiện có.
- Version/schema compatibility cần được kiểm thử.
- Breaking change cần migration hoặc event version mới.
- Giữ đủ metadata để điều tra producer version và correlation.

Không dùng một shared Java class làm event contract giữa service viết bằng nhiều ngôn ngữ.

## 18. Transaction boundary trong từng service

Mỗi service quản lý transaction với database của mình:

~~~text
Order DB:
  Order + Saga + Outbox

Inventory DB:
  Stock + Reservation + Outbox + Inbox

Payment DB:
  Payment operation + Provider reference + Outbox + Inbox
~~~

Transaction local có thể đảm bảo các thay đổi trong cùng database nhất quán. Giữa các service, saga điều phối eventual consistency.

### 18.1. Không dùng distributed transaction cho luồng này theo mặc định

2-phase commit/XA có thể tạo coupling vận hành, giữ resource trong thời gian dài và không giải quyết được side effect ở cổng thanh toán bên ngoài. Với giao dịch thương mại, saga cùng idempotency/reconciliation thường thực tế hơn.

Có trường hợp nghiệp vụ cần strong consistency trong một bounded context; khi đó giữ transaction bên trong service sở hữu dữ liệu. Không mở rộng transaction qua service chỉ vì muốn trạng thái cuối cùng “cập nhật cùng lúc”.

### 18.2. Optimistic locking cho Order/Saga

Nhiều event có thể đến gần như đồng thời. Dùng version để ngăn hai handler ghi đè trạng thái:

~~~sql
UPDATE checkout_sagas
SET state = :nextState,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE saga_id = :sagaId
  AND version = :expectedVersion;
~~~

Nếu số row update bằng 0, state đã đổi hoặc request stale. Handler cần reload và đánh giá event có duplicate, out-of-order hay xung đột thật. Không tự ghi đè state mới bằng event cũ.

## 19. Spring package structure và dependency direction

Một cấu trúc gợi ý trong Order Service:

~~~text
order/
  api/
    OrderController.java
    PlaceOrderRequest.java
    OrderResponse.java
    OrderExceptionHandler.java
  application/
    PlaceOrderUseCase.java
    PlaceOrderService.java
    CheckoutSagaHandler.java
    port/
      InventoryPort.java
      PaymentPort.java
      OrderRepository.java
      OutboxPort.java
  domain/
    Order.java
    OrderId.java
    OrderLine.java
    Money.java
    OrderStatus.java
    CheckoutSaga.java
  infrastructure/
    persistence/
      JpaOrderRepository.java
      OrderJpaEntity.java
      SagaJpaEntity.java
      OutboxJpaEntity.java
    inventory/
      InventoryHttpAdapter.java
    payment/
      PaymentHttpAdapter.java
    messaging/
      OrderEventPublisher.java
~~~

Dependency direction:

~~~text
API / Messaging Adapter
        |
        v
Application Use Case
        |
        v
Domain Model

Infrastructure Adapters ---> Application Ports
Infrastructure Adapters ---> External systems
~~~

Domain không import Spring Web, JPA entity hoặc HTTP client. Application có thể dùng Spring transaction annotation; nếu muốn domain/application thuần Java hơn, có thể đặt transaction boundary trong adapter/use case configuration.

## 20. Port cho Inventory và Payment

Order application layer phụ thuộc interface do Order định nghĩa:

~~~java
public interface InventoryPort {
    ReservationResult reserve(ReserveInventoryRequest request);
    void release(String reservationId, String idempotencyKey);
}

public interface PaymentPort {
    AuthorizationResult authorize(AuthorizePaymentRequest request);
    void voidAuthorization(String paymentId, String idempotencyKey);
}
~~~

Adapter triển khai bằng HTTP client hoặc publish command lên broker. Interface chỉ chứa contract mà Order cần; không expose repository hay entity của Inventory/Payment.

### 20.1. Chọn HTTP hay message broker

| Tiêu chí | HTTP/gRPC | Message broker |
|---|---|---|
| Phản hồi ngay | Phù hợp | Cần reply pattern hoặc async status |
| Coupling thời gian | Caller chờ provider | Producer/consumer tách thời gian |
| Retry | Client cần policy rõ | Broker có redelivery, consumer vẫn phải idempotent |
| Backpressure | Connection/concurrency limits | Queue/backlog, consumer lag |
| Quan sát | Trace request-response | Trace context trong message |
| Failure handling | Timeout/5xx | Retry/DLQ/replay |
| Phù hợp | Query/command cần phản hồi tức thì | Workflow dài, event fan-out, tải burst |

Không có lựa chọn duy nhất. Có thể reserve inventory qua API đồng bộ để trả kết quả nhanh rồi xử lý payment bất đồng bộ; hoặc dùng command/event toàn bộ khi checkout có thể trả PENDING. Cần thống nhất semantics với client và SLO.

## 21. HTTP adapter và timeout

Ví dụ adapter giả lập:

~~~java
@Component
class InventoryHttpAdapter implements InventoryPort {
    private final RestClient restClient;

    InventoryHttpAdapter(RestClient.Builder builder) {
        this.restClient = builder
            .baseUrl("http://inventory-service")
            .build();
    }

    @Override
    public ReservationResult reserve(ReserveInventoryRequest request) {
        return restClient.post()
            .uri("/api/v1/reservations")
            .header("Idempotency-Key", request.idempotencyKey())
            .body(request)
            .retrieve()
            .body(ReservationResult.class);
    }

    @Override
    public void release(String reservationId, String key) {
        restClient.post()
            .uri("/api/v1/reservations/{id}/release", reservationId)
            .header("Idempotency-Key", key)
            .retrieve()
            .toBodilessEntity();
    }
}
~~~

Cần cấu hình connect/read/response timeout ở HTTP client factory theo phiên bản Spring và implementation. Không đặt timeout vô hạn. Với command có side effect, timeout phải đi cùng idempotency và khả năng truy vấn kết quả; retry POST không có key có thể tạo duplicate.

## 22. Error mapping và retry policy

Không phải mọi lỗi đều nên retry.

| Lỗi | Hành vi gợi ý |
|---|---|
| Validation 400 | Không retry |
| Unauthorized/Forbidden | Không retry; xử lý auth |
| Insufficient stock | Kết quả nghiệp vụ cuối cho attempt hiện tại |
| 409 idempotency conflict | Không retry mù; điều tra key/payload |
| 429 rate limited | Retry có backoff/jitter theo Retry-After |
| 5xx transient | Retry giới hạn nếu thao tác idempotent |
| Connection timeout trước khi gửi | Có thể retry theo policy |
| Read timeout sau khi gửi side effect | Kết quả UNKNOWN; query bằng idempotency key |
| Circuit open | Tạm không gọi dependency; giữ workflow ở trạng thái phù hợp |
| Schema/contract error | Không retry liên tục; alert và sửa tương thích |

Retry nên có số lần giới hạn, exponential backoff và jitter. Không retry đồng thời ở nhiều tầng mà không tính tổng số lần gọi; gateway retry ba lần, service retry ba lần và broker redelivery năm lần có thể nhân số request rất lớn.

## 23. Bảo mật service-to-service

Ba service giao tiếp nội bộ vẫn cần xác thực và phân quyền:

- mTLS hoặc cơ chế workload identity phù hợp.
- OAuth2 client credentials/service token khi thích hợp.
- Scope/audience giới hạn theo API.
- Network policy là lớp bổ sung, không thay authentication.
- Secret và gateway token lưu trong secret manager.
- Không log payment token, credential hoặc dữ liệu thẻ.
- Validate tenant/customer authorization ở boundary.
- Không tin orderId hoặc tenantId trong message nếu producer không được phép phát event đó.
- Audit thao tác authorization, capture, void và refund.
- Có chính sách rotation và thu hồi credential.

Payment Service nên có quyền tối thiểu để gọi provider; Order Service không cần credential của provider. Inventory không cần biết payment token.

## 24. Kiểm thử từng ranh giới

### 24.1. Unit test domain

Kiểm tra các invariant mà không cần Spring context:

- Order không thể confirm nếu thiếu inventory reservation hoặc payment authorization.
- Quantity phải dương.
- Không cho transition từ CANCELLED về CONFIRMED.
- Reservation chỉ release một lần.
- Payment authorization không được capture vượt amount được phép.
- Money phải có currency hợp lệ.

Ví dụ test transition:

~~~java
@Test
void cannotConfirmOrderBeforePaymentAuthorization() {
    Order order = Order.pending(OrderId.of("order-1"));

    assertThrows(
        InvalidOrderTransitionException.class,
        order::confirm
    );
}
~~~

Đây là test minh họa; API domain thực tế cần được triển khai theo mô hình đã chọn.

### 24.2. Repository/integration tests

Dùng database tương thích môi trường thật hoặc Testcontainers để kiểm tra:

- Unique idempotency key.
- Transaction rollback khi một item không đủ stock.
- Optimistic locking và concurrent reservation.
- Outbox được ghi cùng business state.
- Migration hoạt động với dữ liệu hiện hữu.
- Inbox deduplication.

Không chỉ dùng H2 nếu production database có semantics SQL/locking khác biệt ảnh hưởng đến correctness.

### 24.3. Contract tests

Kiểm tra:

- Order request mà Inventory nhận.
- Reservation result/error codes.
- Payment authorization request/response.
- Event schema và compatibility.
- Consumer xử lý field mới/optional.
- Authentication scopes và timeout/error semantics.

Provider verification phải chạy trên contract được version hóa. Contract test giảm rủi ro integration nhưng không thay thế end-to-end workflow.

### 24.4. Saga integration tests

Các tình huống bắt buộc nên có:

1. Reserve thành công, authorize thành công, order CONFIRMED.
2. Inventory từ chối, payment không được gọi.
3. Payment từ chối, reservation được release.
4. Payment timeout nhưng gateway đã authorize, reconciliation tìm ra kết quả.
5. Broker gửi event hai lần, side effect chỉ xảy ra một lần.
6. Consumer nhận event sai thứ tự, state không bị lùi.
7. Order Service restart sau khi ghi outbox, workflow vẫn tiếp tục.
8. Inventory release timeout, saga ở COMPENSATION_PENDING và retry an toàn.
9. Payment authorization thành công nhưng Order confirm gặp lỗi, void được xử lý.
10. Một reservation hết hạn trong khi saga còn chờ payment; kết quả được điều phối đúng.

## 25. Local development với Spring Boot

Có thể chạy ba service và broker/database trong môi trường local bằng Docker Compose hoặc test containers. Mỗi service dùng database riêng hoặc database instance riêng/schema riêng theo mức fidelity cần kiểm thử. Nếu dùng một PostgreSQL local, có thể tạo ba database riêng để mô phỏng ownership, dù failure domain vật lý vẫn chung trong local.

Ví dụ danh mục service:

~~~text
order-service       :8081  -> order_db
inventory-service   :8082  -> inventory_db
payment-service     :8083  -> payment_db
message-broker      :9092
~~~

Cấu hình local chỉ phục vụ phát triển; production cần secrets, network policy, TLS, HA, resource limits và backup phù hợp. Không commit credential thật vào repository.

### 25.1. Configuration theo environment

Dùng environment variables hoặc secret manager cho:

- Database URL/username/password.
- Broker bootstrap servers.
- Service endpoints.
- Timeout/retry settings.
- Payment provider credentials.
- Feature flags và workflow deadlines.

Không đưa production credential vào application.yml. Phân biệt config công khai và secret.

## 26. Observability xuyên ba service

Mỗi request/order cần correlationId hoặc trace context xuyên qua:

~~~text
API Gateway
    |
    v
Order Service
    |---- HTTP/Command ---> Inventory
    |---- HTTP/Command ---> Payment
    |
    +---- Outbox ---> Broker ---> Consumers
~~~

Metric hữu ích:

| Service | Metric |
|---|---|
| Order | order create rate, pending age, saga duration, cancellation rate |
| Inventory | reservation success/reject, reserve latency, expiry count |
| Payment | authorization success/decline/unknown, gateway latency, void/refund backlog |
| Outbox | oldest unpublished message, publish failures |
| Broker | consumer lag, redelivery, DLQ depth |
| End-to-end | time from request to CONFIRMED/CANCELLED, workflow timeout |

Log nên có orderId, sagaId, messageId, correlationId và service name ở mức được phép; không log payment token hoặc dữ liệu nhạy cảm. Với metric label, tránh dùng orderId/customerId có cardinality rất cao.

### 26.1. Alert theo nghiệp vụ

- Pending orders vượt ngưỡng tuổi.
- Payment UNKNOWN tồn tại quá lâu.
- Reservation sắp hết hạn trong khi saga vẫn chờ.
- Outbox oldest age tăng.
- Compensation pending backlog tăng.
- Payment void/refund thất bại.
- Inventory reservation rejection tăng đột biến.
- Consumer DLQ tăng.
- Saga duration p95/p99 vượt SLO.

Alert chỉ theo CPU có thể bỏ lỡ workflow bị treo dù tài nguyên còn dư.

## 27. SLO và trải nghiệm người dùng

Định nghĩa SLO theo hành vi khách hàng:

- Tỷ lệ request tạo order được tiếp nhận hợp lệ.
- Tỷ lệ workflow hoàn tất trong thời hạn mục tiêu.
- p95/p99 thời gian từ submit đến trạng thái cuối.
- Tỷ lệ payment có trạng thái xác định trong thời gian cho phép.
- Tỷ lệ inventory reservation chính xác.
- Số đơn ở trạng thái không rõ hoặc cần manual review.

Không tính tất cả PENDING là lỗi nếu sản phẩm đã công bố xử lý bất đồng bộ; nhưng phải có SLO cho thời gian hoàn tất và giới hạn trạng thái pending. Nếu gateway provider có outage, cần phân biệt lỗi dependency và lỗi do ứng dụng, đồng thời thông báo trạng thái trung thực cho người dùng.

## 28. Triển khai và tiến hóa schema

Mỗi service có thể deploy độc lập nếu contract tương thích.

### 28.1. Expand–Migrate–Contract

Khi thêm một cột:

1. **Expand:** thêm cột nullable/default tương thích.
2. Deploy code mới có thể đọc cả schema cũ và mới.
3. **Migrate:** backfill dữ liệu theo batch có giới hạn.
4. Chuyển ghi/đọc sang trường mới.
5. Xác nhận không còn consumer dùng trường cũ.
6. **Contract:** loại bỏ trường cũ trong một release riêng.

Không deploy một thay đổi phá vỡ database schema trước khi các consumer còn dùng schema đó được cập nhật.

### 28.2. Event versioning

Consumer có thể cần đọc event version cũ trong thời gian producer rollout. Định nghĩa compatibility policy và test fixtures. Không đổi nghĩa trường totalMinor từ đơn vị đồng sang đơn vị khác mà giữ nguyên tên/version.

### 28.3. Rollout saga behavior

Thay đổi thứ tự saga hoặc compensation cần đặc biệt cẩn thận vì saga đang chạy có thể được tạo bởi version cũ. Có thể cần lưu workflow version và đảm bảo handler mới hiểu các state version cũ trong thời gian chuyển tiếp.

## 29. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Order truy cập Inventory DB | Phá data ownership | Inventory API/command |
| Payment truy vấn Order DB | Coupling schema và quyền | Payment contract rõ |
| Một transaction xuyên ba service | Lock dài, coupling và khó phục hồi | Saga + local transaction |
| Trừ stock ngay khi nhận request không có reservation | Không có cách giữ/giải phóng rõ | Reservation lifecycle |
| Retry payment bằng key mới sau timeout | Có thể authorize trùng | Idempotency + reconciliation |
| Publish event sau commit bằng hai thao tác rời | Có thể mất event | Transactional outbox |
| Tin broker giao đúng một lần | Duplicate side effect | Inbox/idempotent consumer |
| Gọi mạng trong DB transaction | Giữ connection/lock và side effect không rollback | Commit local rồi dispatch |
| Dùng shared JPA entity giữa service | Domain coupling | DTO/schema contract |
| Trả CONFIRMED trước khi saga hoàn tất | Trạng thái người dùng sai | Pending/async status rõ |
| Release reservation khi payment UNKNOWN | Có thể vừa thu tiền vừa mất hàng | Reconcile trước compensation |
| Không có timeout | Request treo và cạn tài nguyên | Deadline và bounded waits |
| Saga không có trạng thái bền vững | Restart làm mất tiến trình | Persist state/outbox |
| Event cũ ghi đè state mới | Order quay về trạng thái cũ | Version/state transition guard |
| Không có manual review path | Workflow treo vô thời hạn | Reconciliation queue/runbook |

## 30. Lộ trình triển khai từng bước

1. **Làm rõ domain:** thống nhất Order, Reservation, Payment và các trạng thái nghiệp vụ.
2. **Chốt ownership:** database và API của mỗi service do ai sở hữu.
3. **Định nghĩa contract:** request/response, event, error codes và idempotency semantics.
4. **Xây service độc lập:** domain/application/adapter, persistence riêng.
5. **Hoàn thiện local transaction:** giữ invariant trong từng service.
6. **Thêm outbox/inbox:** bảo đảm phát event bền vững và xử lý duplicate.
7. **Triển khai saga:** state machine, timeout, compensation và reconciliation.
8. **Bảo mật:** workload identity, secrets, least privilege và redaction.
9. **Observability:** trace, metrics, logs, dashboard và alert nghiệp vụ.
10. **Test failure paths:** duplicate, timeout, restart, out-of-order, gateway unknown.
11. **Canary:** triển khai theo wave, theo dõi SLO và backlog.
12. **Vận hành:** runbook, backup/restore, support và quy trình manual review.

Có thể bắt đầu bằng một modular monolith nếu team chưa sẵn sàng vận hành ba service. Điều quan trọng là giữ module và data ownership rõ, sau đó tách deployment khi có nhu cầu thật.

## 31. Bài tập thực hành

### Bài tập A — Vẽ ownership

Với ba năng lực Order, Inventory, Payment:

- Liệt kê dữ liệu chính và owner.
- Liệt kê API/event mỗi service công bố.
- Chỉ rõ dữ liệu consumer được phép giữ snapshot.
- Xác định nơi có transaction local.
- Tìm mọi đường truy cập DB chéo service và đề xuất thay thế.

### Bài tập B — Phân tích lỗi

Cho luồng: Inventory đã reserve; Payment gateway timeout; sau 5 giây provider trả kết quả authorization thành công nhưng response ban đầu bị mất.

Hãy thiết kế:

- Trạng thái Order/Saga trong thời gian chưa rõ.
- Idempotency key và thao tác truy vấn Payment.
- Cách tránh tạo authorization thứ hai.
- Khi nào được confirm order.
- Nếu reservation hết hạn trước reconciliation, cần xử lý nghiệp vụ nào?
- Metric/alert nào phát hiện workflow bị treo?

### Bài tập C — Duplicate event

Broker giao PaymentAuthorized hai lần. Consumer Order phải đảm bảo:

- Một payment attempt không được cộng hai lần.
- Order chỉ chuyển trạng thái hợp lệ.
- Saga version không bị lùi.
- Event duplicate được acknowledge theo semantics.
- Có metric/log để quan sát duplicate.

### Bài tập D — Compensation

Payment đã authorize nhưng bước xác nhận order lỗi do database tạm thời không khả dụng. Thiết kế:

- Retry confirm local nếu an toàn.
- Khi nào chuyển sang void authorization?
- Làm sao đảm bảo void không gọi lặp side effect?
- Nếu void thất bại, trạng thái compensation được lưu ở đâu?
- Khi nào chuyển manual review?
- Support tra cứu trạng thái thế nào?

### Bài tập E — Contract evolution

Inventory thêm trường warehouseId trong response. Xác định:

- Field có bắt buộc không?
- Consumer cũ xử lý ra sao?
- Provider và consumer contract tests thế nào?
- Có cần event version mới không?
- Khi nào có thể loại bỏ response field cũ?

## 32. Checklist trước production

### Ranh giới và ownership

- [ ] Order sở hữu order state, snapshot item và checkout saga.
- [ ] Inventory sở hữu stock và reservation.
- [ ] Payment sở hữu payment lifecycle và gateway integration.
- [ ] Không service nào truy cập trực tiếp database của service khác.
- [ ] Domain entity, persistence entity và API/event DTO được phân biệt.
- [ ] Mỗi API/event có owner, version và compatibility policy.

### Tính đúng đắn nghiệp vụ

- [ ] Reservation có TTL, commit/release/expiry rõ.
- [ ] Stock update có atomic guard và concurrency control.
- [ ] Payment có authorization/capture/void/refund state.
- [ ] Timeout được phân biệt với decline/failure cuối.
- [ ] Saga có persistent state và transition hợp lệ.
- [ ] Compensation là use case có idempotency và kết quả theo dõi được.
- [ ] Có manual reconciliation cho trạng thái không xác định.

### Tính bền vững và phục hồi

- [ ] Order, saga và outbox được ghi trong một transaction local.
- [ ] Inventory/Payment có outbox cho event phát ra.
- [ ] Consumer có inbox/deduplication hoặc xử lý idempotent.
- [ ] Retry có backoff/jitter, giới hạn và phân loại lỗi.
- [ ] Có timeout, circuit breaker và bounded concurrency.
- [ ] Restart/rebalance không làm mất workflow.
- [ ] Duplicate và out-of-order event đã được kiểm thử.

### Vận hành và bảo mật

- [ ] Service-to-service authentication và authorization được cấu hình.
- [ ] Payment token/secret không xuất hiện trong log hoặc database không cần thiết.
- [ ] Có trace/correlation ID xuyên HTTP và message.
- [ ] Có dashboard cho pending saga, reservation, payment unknown và outbox lag.
- [ ] Có SLO cho thời gian hoàn tất workflow và trạng thái pending.
- [ ] Có backup/restore, runbook, on-call và quy trình manual review.
- [ ] Migration/schema rollout tương thích với phiên bản consumer đang chạy.
- [ ] Có canary và rollback plan.

## 33. Kết luận

Một thiết kế Order–Inventory–Payment rõ ràng bắt đầu từ **quyền sở hữu nghiệp vụ và dữ liệu**. Order điều phối checkout và giữ trạng thái đơn; Inventory là nguồn sự thật về stock/reservation; Payment là nguồn sự thật về giao dịch và làm việc với gateway. Mỗi service giữ transaction trong database của mình và giao tiếp qua API/event contract đã định nghĩa.

Khi một workflow đi qua nhiều service, không nên dựa vào một transaction ACID xuyên hệ thống. Saga lưu trạng thái tiến trình, điều phối các bước và thực hiện compensation khi cần. Transactional outbox giúp ghi event cùng business state; inbox/idempotency giúp chịu được duplicate; timeout và reconciliation xử lý kết quả không xác định. Spring Boot cung cấp nền tảng triển khai controller, use case, transaction, persistence và HTTP adapter, nhưng tính đúng đắn vẫn nằm ở domain rule, state machine và contract.

Thiết kế tốt không chỉ giúp ba service chạy riêng. Nó còn giúp mỗi team thay đổi và vận hành phần mình sở hữu, trong khi toàn bộ hành trình đặt hàng vẫn có trạng thái minh bạch, khả năng phục hồi và dữ liệu nhất quán theo quy tắc nghiệp vụ.