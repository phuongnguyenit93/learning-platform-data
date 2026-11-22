# Quan hệ giữa mô hình miền, mô hình lưu trữ và mô hình trao đổi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **mô hình miền** (*domain model*), **mô hình lưu trữ** (*storage/persistence model*) và **mô hình trao đổi** (*exchange/integration model*) theo trách nhiệm, nguồn có thẩm quyền và mức độ ổn định.
- Giải thích vì sao một aggregate có thể lưu bằng nhiều bảng hoặc document, đồng thời được công bố qua nhiều API DTO, command và integration event **không cùng hình dạng**.
- Chuyển bất biến nghiệp vụ thành hành vi miền kết hợp khóa, transaction, version và constraint ở nơi lưu.
- Thiết kế ánh xạ domain ↔ storage và domain → exchange cho danh tính, tiền tệ, thời gian, trạng thái và dữ liệu dẫn xuất.
- Phân biệt command với event, API request với persistence row, domain event với CDC và fact phân tích.
- Dùng transactional outbox, consumer idempotency và anti-corruption layer để tích hợp giữa bounded context mà không nhầm quyền sở hữu.
- Đánh giá lựa chọn quan hệ, document, đồ thị và phân tích; lập kế hoạch migration/schema version không làm hỏng consumer.
- Kiểm thử ranh giới qua lỗi nghiệp vụ, concurrent writes, retry, dữ liệu đến muộn và thay đổi hợp đồng.

Trong **DATABASE_DATA_MODELING**, mô hình hóa dữ liệu không chỉ là liệt kê thực thể, quan hệ, khóa và chỉ mục. Ta còn phải biết **ai có quyền thay đổi sự thật nghiệp vụ**, dữ liệu được lưu **ra sao để đúng và hiệu quả**, và các hệ thống khác **được biết hoặc yêu cầu điều gì**. Một sai lầm phổ biến là dùng cùng một class Java làm entity miền, entity ORM và JSON API, rồi gửi nguyên object đó làm message event. Điều này khiến refactor bảng phá API, làm lộ dữ liệu không cần thiết và đẩy ý nghĩa cột storage sang consumer.

Trong chương **Ranh giới và tích hợp**, mục tiêu không phải tạo nhiều lớp cho đẹp: **ba mô hình phải nhất quán về ý nghĩa nhưng không cần giống nhau về cấu trúc**.

## 1. Một đơn hàng, ba cách nhìn

Xét quy trình bán hàng: khách tạo Order; Sales xác nhận; Inventory giữ hàng; Payment thu tiền; Notification báo kết quả; Analytics tổng hợp.

| Câu hỏi | Trách nhiệm | Mô hình |
| --- | --- | --- |
| Đơn rỗng có được xác nhận? | Sales bảo vệ quy tắc của Order | **Domain** |
| Order và các dòng lưu ở đâu, có khóa gì? | Sales repository/database | **Storage** |
| Client gửi lệnh xác nhận và nhận kết quả nào? | REST API của Sales | **Exchange** đồng bộ |
| Inventory biết Order vừa xác nhận thế nào? | Producer/consumer có hợp đồng event | **Exchange** bất đồng bộ |
| Bao nhiêu đơn được thanh toán theo sản phẩm/tháng? | Analytics với grain và metric rõ | **Read/analytical model** |

Lệnh UPDATE status từ DRAFT sang CONFIRMED là cách **lưu** chuyển trạng thái. Phương thức confirm() là **hành vi miền** có điều kiện. OrderConfirmed là **sự thật đã xảy ra** sau commit. Một hàng FactPaidOrderLine là **phép đo** dùng cho phân tích; nó không có quyền thay trạng thái Order.

~~~mermaid
flowchart TB
    CLIENT["Client / API request"] --> APP["Application service<br/>auth + use case"]
    APP --> DOMAIN["Domain model<br/>Order aggregate"]
    DOMAIN <-->|"Repository mapping"| DB[("Storage<br/>order_header + order_line")]
    APP --> OUT[("Outbox cùng transaction")]
    OUT --> BUS["Event broker"]
    BUS --> ACL["Consumer adapter / ACL"]
    ACL --> INV["Inventory / Notification<br/>mô hình miền riêng"]
    DB --> READ["Read model / Analytics"]
~~~

Sơ đồ là ranh giới **logic**. Một monolith vẫn có thể áp dụng, không cần tách microservice. Ngược lại, dù có nhiều service, việc chúng cùng sửa một bảng nội bộ của nhau không tạo được ranh giới an toàn.

## 2. So sánh ba mô hình theo trách nhiệm

| Tiêu chí | Mô hình miền | Mô hình lưu trữ | Mô hình trao đổi |
| --- | --- | --- | --- |
| Mục tiêu | Diễn đạt khái niệm, hành vi và bất biến | Ghi/đọc bền vững, transaction, hiệu năng | Chuyển ý định hoặc sự thật qua ranh giới |
| Đơn vị | Entity, value object, aggregate, domain service | Table/row, document, index, partition, edge | Request, response, command, integration event |
| Câu hỏi | Hành vi nào hợp lệ? Ai có quyền quyết định? | Khóa nào, constraint nào, ghi nguyên tử ra sao? | Bên nhận cần biết gì và hiểu field thế nào? |
| Thay đổi theo | Quy tắc nghiệp vụ | Workload và cấu trúc dữ liệu | Hợp đồng client/consumer |
| Nhất quán | Bất biến trong phạm vi root/context | Constraint, lock, isolation, version | Không phát sự thật chưa commit; retry an toàn |
| Mức công khai | Chủ yếu nội bộ bounded context | Thường riêng của chủ dữ liệu | Công bố có chủ đích |
| Ví dụ Order | addLine(), confirm(), totalVnd() | order_header, order_line, outbox_event | ConfirmOrderRequest, OrderView, OrderConfirmedV1 |

Một class Order có thể chứa List<OrderLine>, nhưng storage là **một header và nhiều row line**. API có thể trả một trường totalVnd dưới dạng chuỗi; storage giữ BIGINT. Event có eventId, schemaVersion, correlationId, những trường **không nhất thiết là thuộc tính kinh doanh của Order**.

Đừng ép tất cả có một DTO duy nhất chỉ để giảm số dòng code. Cũng đừng tạo lớp mapping vô ích: mỗi lớp cần giải quyết sự khác biệt thật về **ngữ nghĩa, quyền truy cập hoặc vòng đời thay đổi**.

## 3. Bounded context và nguồn có thẩm quyền

Các từ giống nhau có thể có nghĩa khác nhau:

- **Sales:** Order là cam kết mua hàng, gồm trạng thái và giá đã chốt.
- **Inventory:** Reservation là quyền giữ số lượng SKU trong kho với thời hạn.
- **Payment:** PaymentAttempt là một lần thử thu tiền; Order có thể có nhiều attempt.
- **Fulfillment:** Shipment là một kiện hoặc một lần giao, có thể nhiều Shipment cho một Order.
- **Analytics:** FactOrderLine là dữ kiện theo grain dòng bán, không phải aggregate có hành vi.

| Quy tắc/sự thật | Nguồn có thẩm quyền | Bên ngoài được phép |
| --- | --- | --- |
| Order có thể CONFIRM không? | Sales/Order | Gửi command; đọc kết quả được công bố |
| Kho có thể giữ SKU không? | Inventory | Gửi ReserveStock; nhận Reserved/Rejected |
| Thanh toán đã CAPTURED chưa? | Payment | Nhận sự kiện/truy vấn theo hợp đồng |
| Shipment đã giao thành công chưa? | Fulfillment | Gửi chứng cứ; đọc trạng thái đã xác nhận |
| Tổng giá trị hàng đã bán theo tháng? | Analytical model có metric rõ | Tổng hợp/đối soát, không sửa nguồn nghiệp vụ |

**Shared database không trao quyền sở hữu.** Việc hai bounded context chạy cùng PostgreSQL không có nghĩa Inventory được sửa order_header. Các context nên trao đổi qua API, event hoặc read model được công bố. Khi cần cùng một giao dịch cục bộ giữa nhiều aggregate, phải nói rõ phụ thuộc và ranh giới, không âm thầm gộp thành một root khổng lồ.

Order thường giữ customerId, skuId như **tham chiếu bằng danh tính**, không nhúng toàn bộ Customer hoặc Product aggregate. Nếu cần giá tại thời điểm mua, lưu **snapshot đơn giá đã chốt**, vì giá Catalog hiện tại không được thay đổi cam kết cũ. Khi identity của nguồn chỉ duy nhất theo tenant hoặc đối tác, mọi mapping phải giữ namespace ấy.

## 4. Bất biến miền khác ràng buộc storage

Giả sử chính sách Sales:

1. Chỉ Order ở trạng thái DRAFT và có ít nhất một dòng mới được confirm.
2. Quantity của dòng là số nguyên dương; đơn giá VND không âm theo chính sách ví dụ.
3. Tổng tiền bằng tổng quantity × unitPriceVnd của các dòng.
4. Khi Order đã CONFIRMED, không sửa dòng bằng thao tác thường.
5. Hai request confirm cùng một version không được tạo hai lần chuyển trạng thái thành công.

| Quy tắc | Domain | Storage | Exchange |
| --- | --- | --- | --- |
| Quantity > 0 | OrderLine constructor | CHECK(quantity > 0) | Input schema validation |
| Chỉ DRAFT mới sửa dòng | Aggregate root | Root version/lock cho mọi đường ghi | Không mở setLines tùy ý |
| Order ID duy nhất | OrderId | PK(tenantId, orderId) | orderId có namespace ổn định |
| Tổng tiền khớp dòng | totalVnd() | Cập nhật cùng transaction; kiểm tra đối soát | Chỉ công bố total đã xác minh |
| Không confirm trùng | Điều kiện chuyển trạng thái | UPDATE có điều kiện, optimistic version | Idempotency key cho retry |
| Không cấp vượt tồn | **Inventory** | Transaction giữ tồn tại Inventory | Event StockReserved riêng |

**Domain validation không thay thế kiểm soát đồng thời.** Hai JVM có thể cùng nạp Order DRAFT và cùng thấy confirm hợp lệ. Database phải ngăn hai transaction cùng ghi dựa trên phiên bản cũ. Ngược lại, CHECK thông thường không diễn đạt được mọi quy tắc nhiều row hay quyền duyệt theo cấp bậc. Ba lớp hỗ trợ nhau.

## 5. Ví dụ Java 17: Domain model không phụ thuộc SQL/HTTP

Đoạn mã rút gọn sau dùng số nguyên đồng VND. Đa tiền tệ nên có Money(value, currency) và quy tắc scale/làm tròn riêng; không dùng double cho tiền.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderId(UUID value) {
    OrderId { Objects.requireNonNull(value); }
}

record OrderLine(UUID lineId, UUID skuId,
                 int quantity, long unitPriceVnd) {
    OrderLine {
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(skuId);
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid line");
        }
    }
    long amountVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

record OrderConfirmed(UUID eventId, OrderId orderId,
                      long orderVersion, Instant occurredAt,
                      long totalVnd) {}

final class Order {
    private final OrderId id;
    private final UUID customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;
    private long version;

    private Order(OrderId id, UUID customerId,
                  OrderStatus status, long version) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = Objects.requireNonNull(status);
        if (version < 0) throw new IllegalArgumentException("version");
        this.version = version;
    }

    static Order newDraft(OrderId id, UUID customerId) {
        return new Order(id, customerId, OrderStatus.DRAFT, 0);
    }

    // Repository phục hồi dữ liệu đã lưu, không tái phát command/event.
    static Order restore(OrderId id, UUID customerId,
            OrderStatus status, long version, List<OrderLine> stored) {
        var order = new Order(id, customerId, status, version);
        for (var line : List.copyOf(stored)) {
            Objects.requireNonNull(line);
            if (order.lines.stream()
                    .anyMatch(x -> x.lineId().equals(line.lineId()))) {
                throw new IllegalArgumentException("Duplicate line");
            }
            order.lines.add(line);
        }
        if (status == OrderStatus.CONFIRMED && order.lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid persisted order");
        }
        order.totalVnd();
        return order;
    }

    void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Not editable");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(
                x -> x.lineId().equals(line.lineId()))) {
            throw new IllegalArgumentException("Duplicate line");
        }
        Math.addExact(totalVnd(), line.amountVnd());
        lines.add(line);
        version++;
    }

    OrderConfirmed confirm(UUID eventId, Instant occurredAt) {
        if (status != OrderStatus.DRAFT || lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm");
        }
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(occurredAt);
        long total = totalVnd();
        status = OrderStatus.CONFIRMED;
        version++;
        return new OrderConfirmed(eventId, id, version, occurredAt, total);
    }

    long totalVnd() {
        long total = 0;
        for (var line : lines) {
            total = Math.addExact(total, line.amountVnd());
        }
        return total;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderId id() { return id; }
    UUID customerId() { return customerId; }
    OrderStatus status() { return status; }
    long version() { return version; }
}
~~~

Order có **hành vi nghiệp vụ**, không có setter tự do đổi status/total. Version tăng trong bộ nhớ theo hành vi, nhưng repository phải giữ **originalVersion** lúc nạp rồi so sánh nó khi ghi finalVersion. Phương thức restore không tăng version hoặc tạo event và cần giới hạn quyền gọi.

**OrderConfirmed trả về từ confirm chỉ là object trong bộ nhớ.** Chưa thể coi nó đã xảy ra bền vững nếu transaction lưu Order rollback. Aggregate không gửi HTTP/email hay publish message trực tiếp. Ứng dụng/repository phải ghi state cùng ý định công bố trong transaction rồi mới coi event là sự thật đã commit.

## 6. Mô hình lưu trữ: một aggregate trải trên nhiều bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    total_vnd BIGINT NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_id UUID NOT NULL,
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);

CREATE TABLE sales.outbox_event (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, aggregate_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);

CREATE INDEX orders_by_customer
    ON sales.order_header (tenant_id, customer_id, created_at DESC);

CREATE INDEX outbox_unpublished
    ON sales.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;
~~~

FK bảo vệ sự tồn tại của Order cho mỗi OrderLine. CHECK bảo vệ quantity và giá không âm. Nhưng CHECK trên header **không thể tự kiểm tra tổng qua nhiều dòng con** theo cách thông thường. Nếu lưu total_vnd vì hiệu năng, mọi đường ghi sửa dòng phải cập nhật tổng trong cùng transaction hoặc dùng trigger/procedure/đối soát được thiết kế riêng. Không cho script ngoài bypass root tùy ý.

### Transaction xác nhận và ghi outbox

Giả sử repository nạp Order DRAFT version 6, gọi confirm() và nhận version 7; các dòng đã tồn tại và đã được kiểm tra:

~~~sql
BEGIN;

UPDATE sales.order_header
SET status = 'CONFIRMED',
    total_vnd = :verified_total_vnd,
    confirmed_at = :occurred_at,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
RETURNING version;

-- Nếu không có đúng 1 hàng: ROLLBACK, không ghi outbox.
-- verified_total_vnd được tính từ các dòng của aggregate.

INSERT INTO sales.outbox_event (
    event_id, tenant_id, aggregate_id, aggregate_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-confirmed', 1, :occurred_at,
    jsonb_build_object(
        'orderId', :order_id,
        'totalVnd', :verified_total_vnd_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~

Chỉ COMMIT khi UPDATE trả đúng một hàng và INSERT outbox thành công. Tổng dạng BIGINT và dạng chuỗi trong payload phải lấy từ **cùng kết quả domain**; không nhận hai con số độc lập từ client. Nếu command thay đổi cả OrderLine trong cùng use case, các thay đổi đó phải được ghi trong transaction này, bảo vệ expectedVersion ban đầu.

Việc Order và outbox cùng commit ngăn tình huống Order đã CONFIRMED nhưng crash làm mất **ý định công bố sự kiện**. Nó **không tự bảo đảm** broker/consumer nhận hoặc áp dụng event đúng một lần. Và transaction ở Sales **không thể tự bao phủ** Inventory/Payment nằm ở database khác.

## 7. Mapping domain ↔ storage và domain → DTO

| Miền | Storage | Quy tắc |
| --- | --- | --- |
| OrderId | order_header.order_id UUID | Giữ ID, kết hợp tenant_id |
| CustomerId tham chiếu | order_header.customer_id UUID | Không nhúng Customer aggregate |
| OrderStatus | order_header.status VARCHAR | Ánh xạ trạng thái hợp lệ, không tự tạo enum mới |
| OrderLine | order_line nhiều row | Kiểm tra danh tính, quantity, đơn giá khi nạp |
| totalVnd | total_vnd BIGINT | Nếu cache phải đồng bộ với sum dòng |
| Version | order_header.version | expectedVersion khi nạp, finalVersion sau command |
| OrderConfirmed | outbox_event | Ánh xạ event nội bộ sang hợp đồng công bố |
| confirmedAt | order_header.confirmed_at | Mốc nghiệp vụ, không phải giờ consumer nhận |

**Đường ghi** dùng repository nạp aggregate, gọi hành vi và commit. **Đường đọc** có thể map thẳng SQL/query model sang DTO để hiển thị, không nhất thiết phục hồi toàn bộ aggregate khi không định thay đổi trạng thái.

~~~java
import java.util.List;
import java.util.UUID;

record OrderLineView(UUID skuId, int quantity, String unitPriceVnd) {}

record OrderView(UUID orderId, String status, String totalVnd,
                 String currency, List<OrderLineView> lines) {
    OrderView { lines = List.copyOf(lines); }
}

final class OrderViewMapper {
    static OrderView fromDomain(Order order) {
        var views = order.lines().stream()
            .map(line -> new OrderLineView(
                line.skuId(), line.quantity(),
                Long.toString(line.unitPriceVnd())))
            .toList();
        return new OrderView(
            order.id().value(),
            order.status().name(),
            Long.toString(order.totalVnd()),
            "VND",
            views);
    }
}
~~~

Ví dụ dùng số tiền dạng **chuỗi số nguyên VND** để tránh mất chính xác ở client JavaScript với số nguyên vượt giới hạn an toàn. Hợp đồng thực tế phải nói rõ đơn vị, currency, scale và cách làm tròn. Đổi tên cột total_vnd không buộc client đổi tên field totalVnd.

Mapper không được âm thầm bỏ OrderLine lỗi để dựng một aggregate trông hợp lệ. Nếu storage chứa status lạ, dòng trùng, giá âm hoặc sai tenant, cần báo và xử lý dữ liệu hỏng theo quy trình kiểm soát.

## 8. Mô hình trao đổi đồng bộ: REST command và response

Một API không nên biến storage thành một bảng cho người ngoài sửa. Thay vì để client gửi PATCH status=CONFIRMED, có thể cung cấp command có ý nghĩa:

~~~http
POST /v1/orders/6cb1d299-4fd0-4f39-ab95-195db8ffed82/confirm HTTP/1.1
Authorization: Bearer [access-token]
Idempotency-Key: 18f2fe65-b7ee-4d9f-9f9e-65f560125d52
Content-Type: application/json

{}
~~~

Ví dụ phản hồi sau transaction thành công:

~~~json
{
  "orderId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
  "status": "CONFIRMED",
  "totalVnd": "1250000",
  "currency": "VND",
  "version": 7
}
~~~

**Idempotency-Key** định danh **ý định command của caller** khi họ retry sau timeout, không phải orderId và không phải eventId. Hệ thống phải gắn key với caller/tenant, loại thao tác và nội dung tương ứng, lưu kết quả bền vững trong thời hạn hợp đồng. Retry với cùng key và payload không tạo transition mới; cùng key nhưng payload khác phải được báo xung đột.

| Tình huống | Phản hồi/ngữ nghĩa phù hợp | Sai lầm cần tránh |
| --- | --- | --- |
| Caller không có quyền xem/xác nhận Order | Authorization/tenant scope error | Chỉ tin orderId/tenantId do client gửi |
| Order đang CANCELLED | Domain conflict | Dùng setter chuyển thẳng CONFIRMED |
| Order không có dòng | Rule violation | Ghi event rồi để consumer tự kiểm tra |
| Hai confirm cạnh tranh cùng version | Một commit; request khác conflict/đã xử lý | Ghi đè state không kiểm soát |
| Client timeout sau khi commit | Retry hoặc truy vấn theo key ổn định | Coi mọi retry là command mới |
| Inventory chưa có kết quả giữ hàng | Pending/trạng thái workflow phù hợp | Tuyên bố hàng đã giữ chỉ vì Sales confirm |

Phiên bản API **v1** khác hoàn toàn với **Order version=7**. v1 mô tả hợp đồng HTTP; version=7 có thể là phiên bản aggregate để hỗ trợ optimistic concurrency. Thay đổi cách phân trang API không nhất thiết sửa Order; Order từ version 7 lên 8 không làm URL phải tăng v8.

### API request không phải entity

Nhận JSON hợp lệ là bước **kiểm tra định dạng đầu vào**, chưa phải quyết định nghiệp vụ. Application service xác thực actor, tenant, permission, nạp Order từ repository, gọi confirm() rồi lưu. API DTO không được có một trường totalMoney do client tự đặt rồi bỏ qua giá từ các dòng đã chốt.

Một response có thể cố ý thiếu customerId, thông tin địa chỉ và cấu trúc khóa nội bộ nếu người dùng không được phép thấy hoặc không cần để hoàn thành use case.

## 9. Mô hình trao đổi bất đồng bộ: event và outbox

Từ domain event OrderConfirmed, producer có thể ánh xạ ra integration event dành cho consumer:

~~~json
{
  "eventId": "a74acf66-f904-4f90-a82b-1716ad0c7a16",
  "eventType": "sales.order-confirmed",
  "schemaVersion": 1,
  "producer": "sales",
  "tenantId": "8b15ae84-f427-45d4-a949-1a6fcb3f5b17",
  "aggregateId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-22T03:00:00Z",
  "correlationId": "4f77ce91-8352-463d-b4be-29a353a1c029",
  "payload": {
    "orderId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
    "totalVnd": "1250000",
    "currency": "VND"
  }
}
~~~

**Tại sao cần envelope?**

| Trường | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| eventId | Định danh duy nhất của một sự thật đã phát sinh | orderId, broker messageId |
| aggregateId | Đối tượng Order có thay đổi | eventId |
| aggregateVersion | Thứ tự thay đổi của một Order theo chính sách nguồn | Thứ tự toàn hệ thống |
| schemaVersion | Phiên bản hợp đồng event | Phiên bản state của Order |
| occurredAt | Mốc nghiệp vụ theo nguồn có thẩm quyền | receivedAt, publishedAt |
| correlationId | Liên hệ các bước của cùng một quy trình | Idempotency key hoặc dedup key |
| tenantId / producer | Namespace và nguồn phát | Bằng chứng caller được quyền truy cập |
| payload | Những dữ kiện được công bố | Serialization của mọi cột nội bộ |

**OrderConfirmed ≠ StockReserved ≠ PaymentCaptured.** Sự kiện của Sales không chứng minh kho có hàng hoặc tiền đã được thu. Inventory tiếp nhận một sự thật và tự ra quyết định giữ hàng theo quy tắc riêng; nếu không đủ hàng có thể phản hồi StockReservationRejected. Payment giữ một vòng đời giao dịch riêng.

### Commit trước, công bố sau

~~~mermaid
sequenceDiagram
    participant S as Sales Application
    participant DB as Sales DB
    participant R as Outbox Relay
    participant B as Broker
    participant N as Notification

    S->>DB: Transaction: Order CONFIRMED + outbox E1
    DB-->>S: COMMIT thành công
    R->>DB: Đọc sự kiện chưa gửi
    R->>B: Publish eventId E1
    B->>N: Deliver E1
    N->>N: Dedup + áp dụng tác động cục bộ
    N-->>B: ACK sau khi commit cục bộ
    B->>N: Có thể redeliver E1
    N->>N: Bỏ qua tác động trùng
~~~

Nếu relay publish thành công rồi crash trước khi đánh dấu published, broker/consumer có thể nhận **lặp cùng eventId**. Outbox thường giúp truyền theo mô hình **at-least-once**, không tự tạo exactly-once end-to-end.

Một consumer có thể lưu processed_event(consumer_name, eventId) với khóa duy nhất; bản ghi đã xử lý và **thay đổi nghiệp vụ cục bộ** phải commit trong cùng transaction. Nếu tác động là gửi email hoặc gọi payment gateway nằm ngoài transaction, vẫn cần idempotency/giao thức phù hợp tại dịch vụ ngoài. Không có bảng dedup nào có thể biến một HTTP call vào hệ thống khác thành ACID cục bộ.

### Thứ tự và thời gian

Hai event cùng Order có thể tới consumer ngược thứ tự do retry, nhiều partition hoặc relay song song. AggregateVersion giúp phát hiện bản cũ/lỗ hổng **trong phạm vi một Order**, nhưng phải có quy tắc khi thiếu event và không được coi mọi thay đổi version đều sinh đúng một integration event. Có thể partition theo aggregateId hoặc dùng snapshot nguồn có thẩm quyền để tái dựng projection. Timestamp đơn thuần không chứng minh thứ tự toàn cầu.

## 10. Không tráo command, domain event, CDC và analytical fact

| Đối tượng | Diễn đạt gì? | Có ý nghĩa gì với bên nhận? |
| --- | --- | --- |
| **Command ConfirmOrder** | Mong muốn hệ thống làm một việc | Chưa chắc thành công |
| **Domain event OrderConfirmed** | Sự thật nghiệp vụ vừa xảy ra | Chỉ coi là bền vững sau commit |
| **Integration event sales.order-confirmed** | Sự thật được công bố theo hợp đồng ngoài Sales | Consumer phản ứng theo ngữ nghĩa đã cam kết |
| **API response OrderView** | Một snapshot trạng thái được phép hiển thị | Có thể đổi do command sau đó |
| **Persistence row order_header** | Trạng thái trong cách lưu vật lý | Không được đồng nhất với toàn bộ aggregate |
| **CDC row update** | INSERT/UPDATE/DELETE của bảng đã commit | Không tự là một domain event |
| **Audit record** | Ai làm gì, khi nào, vì sao theo chính sách kiểm toán | Không nhất thiết là nguồn tái dựng state |
| **Analytical fact** | Một phép đo ở grain xác định | Không có quyền thực thi command |

Một command có thể tạo nhiều event hoặc không tạo event nếu bị từ chối. Một lần UPDATE có thể là bước kỹ thuật nhỏ trong nhiều thay đổi cùng một giao dịch nghiệp vụ. Change Data Capture (CDC) hữu ích để đồng bộ bảng, nhưng một câu UPDATE làm đổi version mà không đổi trạng thái nghiệp vụ không tự trở thành OrderConfirmed.

Nếu hệ thống dùng **event sourcing**, chuỗi event là nguồn sự thật để tái dựng trạng thái theo thiết kế; đó là quyết định khác với việc có một outbox và vài domain event. Không gắn nhãn event sourcing cho một ứng dụng chỉ vì nó lưu lịch sử trạng thái hoặc phát message.

## 11. Anti-corruption layer: chuyển nghĩa khi tích hợp đối tác

Một đối tác vận chuyển có API:

~~~json
{
  "shipmentNo": "SHP-1020",
  "state": "DONE",
  "trackingStatus": "SIGNED",
  "eventTime": "2026-11-22T10:00:00+07"
}
~~~

Chỉ từ state=DONE, ta chưa biết đó là **đã giao tới khách**, **đã bàn giao cho hãng** hay **đã đóng hồ sơ**. Nếu trong domain Fulfillment, DELIVERED đòi bằng chứng nhận hàng, ánh xạ mù quáng DONE → DELIVERED sẽ tạo một sự thật giả.

**Anti-corruption layer (ACL)** là lớp chuyển đổi ngữ nghĩa bảo vệ mô hình nội bộ khỏi từ vựng, ID và cấu trúc ngoài. Nó cần:

1. Xác định nguồn/phiên bản API đối tác, phạm vi định danh shipmentNo và tenant.
2. Tra tài liệu ngữ nghĩa DONE/SIGNED để biết có thật là giao hoàn tất không.
3. Quy đổi eventTime có offset sang Instant và giữ receivedAt riêng.
4. Ánh xạ externalShipmentId sang ShipmentId nội bộ qua quan hệ đã xác minh.
5. Tạo **command có điều kiện**, ví dụ RecordProofOfDelivery, để Shipment root tự kiểm tra trạng thái.
6. Khi gặp trạng thái mới hoặc thiếu chứng cứ, trả lỗi/quarantine/đối soát; không tự gán DELIVERED.

~~~mermaid
flowchart LR
    EXT["Partner event<br/>DONE / SIGNED"] --> ACL["Adapter / ACL<br/>validate + translate"]
    ACL --> CMD["Internal command<br/>RecordProofOfDelivery"]
    CMD --> DOM["Shipment aggregate<br/>bất biến giao hàng"]
    DOM --> DB[("Repository + transaction")]
~~~

ACL còn xử lý:

- **Đơn vị:** gram → kilogram, đồng → xu hoặc ngoại tệ theo định nghĩa; không đổi số mà giữ nhãn.
- **Danh tính:** cùng externalId có thể trùng giữa hai đối tác.
- **Trạng thái:** một trạng thái ngoài có thể tương ứng nhiều trạng thái nội bộ theo chứng cứ bổ sung.
- **Thời gian:** local datetime không có offset có thể mơ hồ; không tự coi là UTC.
- **Null/missing:** trường không gửi không mặc định bằng 0 hoặc nghĩa là giá trị đã bị xóa.
- **Phiên bản:** response v2 của đối tác có thể thay nghĩa dù tên field giống v1.

ACL phù hợp cả khi tích hợp một hệ thống **legacy trong cùng monolith**; network boundary không phải điều kiện bắt buộc.

## 12. Tính nhất quán qua ranh giới và trạng thái trung gian

Một thao tác đơn giản trong UI có thể là quy trình nhiều nguồn có thẩm quyền:

~~~mermaid
sequenceDiagram
    participant U as Customer
    participant S as Sales
    participant I as Inventory
    participant P as Payment
    U->>S: PlaceOrder
    S->>S: Ghi Order PENDING_STOCK
    S->>I: ReserveStock(requestId, sku, qty)
    I->>I: Transaction giữ kho nếu đủ
    I-->>S: StockReserved / Rejected
    S->>S: Chuyển STOCK_HELD nếu Reserved
    S->>P: AuthorizePayment(commandId)
    P-->>S: PaymentAuthorized / Rejected
    S->>S: Confirm nếu các điều kiện đúng
    S-->>U: Kết quả workflow
~~~

Đây là **một phương án điều phối minh họa**, không phải quy trình thương mại duy nhất. Có hệ thống xác nhận Order trước khi giữ kho, có hệ thống bắt buộc giữ kho trước khi xác nhận. Mỗi lựa chọn phải chỉ ra **trạng thái mà hệ thống cam kết tại mỗi bước**.

Không thể dùng transaction cục bộ của Sales để rollback việc Inventory đã giữ kho ở database khác. Nếu Payment thất bại sau ReserveStock, cần **ReleaseReservation** như một command bù có quyền và idempotency, không gọi đó là SQL ROLLBACK xuyên service.

| Rủi ro | Thiết kế cần có |
| --- | --- |
| Sales gửi ReserveStock rồi timeout, không biết đã thành công? | Idempotency key ổn định, truy vấn trạng thái theo key/reservationId |
| Inventory giữ thành công nhưng phản hồi bị mất | Retry an toàn, không giữ thêm hàng |
| Payment báo thành công trễ sau khi Order bị hủy | Trạng thái quy trình, chính sách hoàn/bù, đối soát |
| Event cùng Order đến ngược thứ tự | Sequence/version theo Order và xử lý gap |
| Worker chết giữa ghi state và gửi message | Transactional outbox/inbox hoặc cơ chế bền vững tương đương |
| Hai service tin mình sở hữu cùng một field | Phân lại nguồn có thẩm quyền, không dual write tự do |

**Eventual consistency không đồng nghĩa bất biến có thể sai tạm.** Inventory phải giữ bất biến không cấp vượt tồn **ngay tại nguồn cấp quyền**. Read model của Sales có thể chậm biết StockReserved; đó là vấn đề độ tươi của bản sao, không phải lý do cho phép kho vượt giới hạn.

## 13. Mô hình đọc và phân tích: thêm một góc nhìn có grain riêng

Một hệ thống có thể tối ưu đường đọc/analytics tách khỏi đường ghi:

| Nhu cầu | Grain thích hợp | Nguồn và giới hạn |
| --- | --- | --- |
| Xem trạng thái Order hiện hành | Một OrderSummary | Đọc projection hoặc Order source, nêu độ tươi |
| Đếm số lần Order được confirm | Một OrderConfirmed event duy nhất | Dedup eventId; xác định ngày nghiệp vụ |
| Giá trị hàng đã thanh toán theo SKU | Một dòng bán đủ điều kiện ghi nhận | Cần Payment/Order facts, snapshot đơn giá |
| Phân tích số lần thử thu tiền | Một PaymentAttempt | Không đếm attempt như một đơn mới |
| Thời gian giao hàng | Một fulfillment instance | Các milestone requested/packed/delivered |

**OrderConfirmed không phải doanh thu đã thanh toán.** Nếu lấy tổng OrderConfirmed làm doanh thu, các đơn chưa captured, đơn hủy, hoàn tiền hay giao hàng từng phần có thể khiến KPI sai. Mỗi fact phải có **grain, measure, thời điểm và trạng thái ghi nhận** rõ.

~~~mermaid
flowchart LR
    SRC["Order / Payment nguồn có thẩm quyền"]
    MSG["Committed events / CDC"]
    STG["Staging<br/>validate, dedup, map grain"]
    MART["Fact + Dimension<br/>historical read model"]
    BI["Dashboard<br/>metric version + freshness"]
    SRC --> MSG
    MSG --> STG
    STG --> MART
    MART --> BI
~~~

Một warehouse có thể lưu SCD Type 2 hoặc snapshot giá, dùng lưu trữ cột và partition để tổng hợp nhanh. Điều này **không buộc** storage của Order OLTP hoặc API OrderView có cùng cấu trúc. Đường đọc có thể denormalize, nhưng đường ghi vẫn phải theo owner của bất biến.

## 14. So sánh cách mô hình hóa theo công nghệ lưu trữ

Ba mô hình miền–lưu trữ–trao đổi **không phải ba loại cơ sở dữ liệu bắt buộc**. Cùng một domain có thể dùng quan hệ, document, đồ thị hoặc bản sao phân tích; quyết định lưu trữ cần dựa trên bất biến và workload thật.

| Kiểu lưu | Biểu diễn ứng viên | Điểm mạnh | Điều phải đánh giá |
| --- | --- | --- | --- |
| **Quan hệ** | OrderHeader, OrderLine, FK, UNIQUE, CHECK, outbox | Transaction nhiều hàng, constraint, truy vấn có cấu trúc | Lock/isolation, index, contention, vòng đời schema |
| **Document** | Một Order document chứa lines, version và metadata | Truy xuất thành viên cùng aggregate thuận tiện | Giới hạn document, atomic update, thay đổi nhiều document |
| **Đồ thị** | Node Order/Customer/Product và quan hệ giữa chúng | Truy vấn nhiều bước, đường đi, quan hệ phong phú | Edge không tự trao quyền ghi aggregate hay ACID toàn hệ |
| **Phân tích/cột** | FactOrderLine, DimProduct, DimDate, snapshot | Scan, nhóm, nén, lịch sử dài | Grain, late data, CDC, không là nơi bảo vệ command |

### 14.1. Quan hệ: một aggregate có thể trải nhiều bảng

Một Order có thể gồm row header và nhiều row line, nhưng vẫn là **một aggregate logic** do root quyết định hành vi. Repository dùng transaction bảo vệ thay đổi chung. Ngược lại, dù hai aggregate lưu trong cùng database, không nhất thiết chúng phải nằm trong cùng object graph hoặc cùng transaction cho mọi thao tác.

**Quan hệ vật lý không đồng nghĩa quan hệ quyền sở hữu.** Một FK từ order_line đến order_header cho biết dòng thuộc Order, còn một trường customer_id tham chiếu Customer thuộc context khác có thể chỉ cần giữ ID và hợp đồng liên kết; không phải lúc nào FK xuyên database/service cũng phù hợp hoặc có thể thực thi.

### 14.2. Document: một document không mặc nhiên là một aggregate

Một document chứa danh sách line hữu hạn có thể thuận tiện nếu các hành vi đọc/ghi theo Order và engine hỗ trợ cập nhật nguyên tử cần thiết. Nhưng nếu một đơn có lịch sử vô hạn hoặc các dòng được cập nhật cạnh tranh thường xuyên, document lớn có thể trở thành điểm tranh chấp và tốn băng thông.

Nếu Inventory và Payment ở document khác hoặc cluster khác, việc cập nhật một Order document không tự bảo đảm kho đã được giữ và tiền đã thu. Tính nhất quán phải được xác định bằng khả năng transaction thực tế của sản phẩm hoặc quy trình liên context.

### 14.3. Đồ thị: traversal không đồng nghĩa mutation authority

Một đồ thị Customer → Order → Product giúp tìm chuỗi quan hệ. Nó không có nghĩa Customer aggregate được phép sửa tất cả Order hay Product theo đường edge. Domain vẫn quy định root chịu trách nhiệm bất biến, còn graph là một phương án lưu/đọc quan hệ phù hợp với nhu cầu.

### 14.4. Analytics: denormalization cho đọc, không trả quyền quyết định

Một fact có thể lưu snapshot của giá, vùng kinh doanh và phân khúc khách hàng để truy vấn nhanh. Điều này không chứng minh các chiều ấy nằm trong cùng aggregate bán hàng. Trên đường ghi, Sales vẫn phải bảo vệ giá đã chốt và trạng thái đơn; Warehouse chỉ cung cấp cách diễn giải có version, thời điểm và độ tươi rõ ràng.

**Câu hỏi thiết kế không phải "chọn SQL hay NoSQL rồi tạo domain tương ứng"**, mà là "bất biến nào cần giữ, truy vấn nào chủ đạo và engine nào thực hiện an toàn với chi phí phù hợp".

## 15. Tiến hóa độc lập domain, storage và contract

Ba loại thay đổi có thể xảy ra độc lập:

1. **Domain change:** thêm bước phê duyệt hoặc trạng thái AWAITING_STOCK; phải đánh giá hành vi và bất biến.
2. **Storage change:** tách bảng, thêm index, partition dữ liệu, đổi cách lưu total; có thể giữ nguyên API.
3. **Contract change:** thêm trường API/event, sửa một enum công khai hoặc đổi cách định dạng thời gian; phải xét consumer cũ.

| Thay đổi | Cái gì có thể giữ ổn định? | Rủi ro nổi bật |
| --- | --- | --- |
| Chuyển OrderLine từ một bảng sang nhiều partition | Domain Order và REST OrderView | Repository mapping, khóa/transaction |
| Thêm field confirmedAt tùy chọn cho response | Hành vi Order và schema nếu đã lưu | Client xử lý field chưa biết |
| Event bổ sung currency | Domain nếu đã có Money | Consumer cũ và giá trị mặc định |
| Đổi nghĩa CONFIRMED từ Sales chấp nhận sang Payment captured | **Không** nên giữ tên mà âm thầm đổi nghĩa | Phá toàn bộ quy trình và KPI |
| Đổi totalVnd từ đồng sang nghìn đồng nhưng giữ tên | **Không** tương thích | Sai tiền và dữ liệu lịch sử |
| Analytics chuyển dim_product từ Type 1 sang Type 2 | Có thể giữ domain Sales | Ánh xạ lịch sử và fact key |

### 15.1. Expand → migrate → contract

Khi cần migration không làm gián đoạn hệ thống nhiều phiên bản:

1. **Expand:** thêm cột/bảng/contract mới ở dạng tương thích; chưa xóa trường cũ.
2. **Migrate/backfill:** chuyển dữ liệu, kiểm tra count, khóa, số tiền, trạng thái và bản NULL.
3. **Adapt:** nếu cần dual-read/dual-write trong giai đoạn chuyển tiếp, chỉ định nguồn chân lý, cách đối soát và xử lý xung đột; tránh ghi song song tự do.
4. **Switch:** chuyển repository/query sang mô hình mới; đo lỗi, độ trễ, dữ liệu chênh lệch và khả năng rollback.
5. **Contract:** gỡ cấu trúc cũ chỉ sau khi toàn bộ producer/consumer cần thiết đã chuyển.

Với event contract, **thêm trường optional** thường ít phá hơn xóa/đổi tên trường bắt buộc, nhưng chỉ khi consumer xử lý trường lạ/default theo hợp đồng. Đổi **nghĩa** hoặc **đơn vị** của một field là thay đổi không tương thích ngay cả khi schema JSON vẫn parse được.

### 15.2. Không serialize ORM entity như API contract

Một entity JPA/Hibernate có thể chứa quan hệ lazy, cờ xóa mềm, audit nội bộ, password hash hoặc cấu trúc phụ thuộc database. Trả thẳng entity có thể:

- phơi bày dữ liệu vượt phạm vi quyền;
- gây N+1 query khi serializer đi qua quan hệ;
- tạo vòng lặp tham chiếu hoặc response rất lớn;
- làm refactor schema trở thành thay đổi breaking API;
- để thời gian/tiền được serializer mặc định xử lý sai hợp đồng.

DTO riêng giúp kiểm soát nội dung công bố và thích ứng khi domain/storage thay đổi. Tuy nhiên không cần mỗi method một DTO mới nếu cùng một contract có nghĩa, quyền và vòng đời ổn định.

## 16. Các quy ước xuyên ranh giới: ID, thời gian, tiền, bảo mật

### 16.1. Định danh và namespace

- orderId, paymentAttemptId, shipmentId, eventId và requestId là các định danh **khác vai trò**.
- ID có thể chỉ duy nhất theo tenant hoặc producer. Khi tích hợp nhiều nguồn, cần namespace hoặc mapping rõ.
- Surrogate key trong warehouse không mặc định là business ID công khai. Nếu nạp lại dimension làm key thay đổi, event/API bên ngoài không nên bị ảnh hưởng.
- Quan hệ cross-context qua ID phải được kiểm tra tồn tại/quyền theo giao thức, không mặc định FK luôn có thể trải qua nhiều database độc lập.

### 16.2. Các mốc thời gian khác nhau

| Trường | Định nghĩa | Không thay bằng |
| --- | --- | --- |
| occurredAt | Sự kiện nghiệp vụ được xác nhận xảy ra | Thời điểm broker nhận |
| recordedAt | Nguồn ghi lại sự kiện | Ngày báo cáo theo múi giờ |
| publishedAt | Relay công bố thông điệp | Thời điểm domain quyết định |
| receivedAt | Consumer nhận thông điệp | occurredAt |
| businessDate | Ngày theo lịch/cutoff phân tích | Ngày UTC nếu quy ước là giờ địa phương |

Một đơn được thanh toán lúc 23:59 giờ Việt Nam nhưng được CDC xử lý lúc 00:05 ngày sau vẫn thuộc **ngày thanh toán đã định nghĩa** theo paidAt, trừ khi metric chủ đích dùng ngày xử lý. Mọi contract cần chỉ rõ format, offset, timezone và chính sách correction.

### 16.3. Tiền và số đo

- Dùng amount + currency, chỉ rõ VND nguyên, đơn vị nhỏ nhất hay decimal.
- Tránh double/float trong tính tiền; chọn kiểu chính xác và quy tắc làm tròn.
- Không cộng doanh thu từ hai currency trước khi có tỷ giá và mốc áp dụng rõ ràng.
- Không đồng nhất authorized, captured, refunded, gross và net chỉ vì đều là số tiền.
- Khi một DTO nêu total, phải xác định total của **trạng thái nào** và từ snapshot giá nào.

### 16.4. Quyền truy cập, tenant và dữ liệu nhạy cảm

TenantId là một trường **phân phạm vi**, không phải bằng chứng caller có quyền. Phải xác thực producer/caller, kiểm tra quyền sở hữu và hạn chế dữ liệu trả về theo vai trò. Không tự đưa số thẻ, địa chỉ, số điện thoại hay thông tin nhân sự vào event phát cho nhiều subscriber nếu không có nhu cầu và quyền rõ ràng.

Outbox, broker, log, warehouse và backup có thể giữ nhiều bản sao; mỗi nơi cần chính sách retention, mã hóa/truy cập và quy trình xóa/ẩn danh thích hợp. Một hợp đồng trao đổi ổn định nhưng làm rò rỉ dữ liệu cá nhân là ranh giới thiết kế thất bại.

## 17. Kiểm thử theo ranh giới, không chỉ test getter/setter

| Mức thử | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Domain unit | Confirm Order rỗng | Bị từ chối, không tạo sự thật Confirmed |
| Domain unit | AddLine sau CONFIRMED | Không đổi state/version |
| Domain unit | Quantity âm hoặc nhân tiền tràn long | Lỗi rõ, dữ liệu nội bộ không bị sửa |
| Repository integration | Lưu rồi nạp Order nhiều dòng | Đúng ID, dòng, total, state và version |
| Concurrency integration | Hai request confirm dựa cùng expectedVersion | Tối đa một transaction thành công |
| Transaction integration | INSERT outbox lỗi sau UPDATE header | Rollback Order, không có event đã commit |
| API contract | Client cố gửi status/total không được hỗ trợ | Không cho sửa vượt use case |
| Event contract | Consumer v1 gặp payload thiếu field bắt buộc | Phản hồi lỗi hợp đồng hoặc adapter được định nghĩa |
| Consumer integration | Broker redeliver cùng eventId | Không nhân đôi tác động nghiệp vụ |
| ACL integration | Đối tác gửi DONE thiếu chứng cứ giao | Không tự cho Shipment DELIVERED |
| Analytics | Một Order có ba line, hai PaymentAttempt | Không nhân doanh số khi JOIN |
| Security | Caller tenant B biết orderId tenant A | Bị từ chối, không lộ dữ liệu |
| Migration | Storage đổi cấu trúc nhưng API chưa đổi | Contract còn hoạt động, dữ liệu đối soát khớp |

**Test hợp đồng không chỉ kiểm tra JSON parse được.** Nó còn kiểm tra ý nghĩa enum, currency/đơn vị, format timestamp, ID namespace, idempotency, dữ liệu bắt buộc/tùy chọn, trường không được công bố và cách xử lý phiên bản mới.

Test concurrency phải chạy với **database thật và isolation thực tế** vì mock repository chạy tuần tự không bộc lộ lost update, deadlock hay trường hợp xung đột UNIQUE. Nếu một giao dịch sửa nhiều row, test cần kiểm tra **trạng thái cuối** của tất cả bảng và outbox, không chỉ HTTP status.

### Đề xuất test chiến lược thay đổi contract

Một kỹ thuật hiệu quả là có **producer/consumer contract tests**. Producer xác minh payload mới vẫn đáp ứng hợp đồng đã công bố; consumer xác minh có thể đọc các phiên bản còn được hỗ trợ. Trong giai đoạn migration, chạy test trên dữ liệu hiện có có giá trị hơn việc chỉ kiểm tra một object mẫu đủ đẹp.

Ngoài test tự động, cần theo dõi tỷ lệ message bị quarantine, mapping fail, idempotency conflict, outbox lag và data-reconciliation difference để phát hiện lỗi ngoài đời thực.

## 18. Bài tập thực hành: đặt phòng khách sạn

**Bối cảnh:** Nền tảng đặt phòng có các bounded context Booking, Inventory (RoomAvailability), Payment và Analytics. Khách giữ phòng ba đêm, thanh toán rồi nhận Booking được xác nhận. Giá thay đổi theo mùa, một Booking có thể chia nhiều phòng hoặc bị hủy/hoàn tiền. Một đối tác cũ gọi trạng thái PAID=Y ngay sau **ủy quyền** thanh toán chứ chưa chắc đã thu tiền.

### Yêu cầu

1. Liệt kê entity/value object của domain Booking, ba bất biến Booking phải bảo vệ và một bất biến thuộc Inventory.
2. Đề xuất bảng booking_header và booking_night với PK, FK, tenant, snapshot giá từng đêm, status và version. Nếu khách đặt **hai phòng cùng loại cho một đêm**, grain và khóa thay đổi ra sao?
3. Phác thảo REST command ConfirmBooking, response DTO và integration event booking.confirmed có schemaVersion. Trường nào không nên gửi cho mọi subscriber?
4. RoomsReserved từ Inventory có chứng minh PaymentCaptured không? Nếu Payment event đến muộn hoặc lặp, Booking xử lý thế nào?
5. ACL nên chuyển nghĩa PAID=Y của legacy thành trạng thái nào, và khi thiếu chứng cứ thì làm gì?
6. Nếu chuyển BookingNight từ row SQL sang danh sách nhúng trong document Booking, domain và API có phải đổi cùng schema không? Cần kiểm tra gì về atomicity, kích thước document và đồng thời?
7. Analytics muốn tính số booking đã xác nhận theo ngày và giá trị đêm phòng **đã thực sự lưu trú** theo ngày. Có cùng grain không? Có được lấy ngay booking.confirmed.totalVnd làm doanh thu lưu trú không?
8. Nêu ít nhất bốn test về tranh chấp phòng cuối, retry cùng command/event, giá thay đổi sau chốt, nhầm tiền tệ và truy cập xuyên tenant.

### Hướng giải tham khảo

**Domain Booking:** Booking root có BookingNight/StayPeriod/PriceSnapshot, trạng thái DRAFT, HELD, CONFIRMED, CANCELLED và hành vi có kiểm tra điều kiện. Booking bảo vệ ngày nhận phòng trước ngày trả, số đêm hợp lệ, snapshot giá đã chấp nhận và chuyển trạng thái hợp lệ. **Inventory** là nơi bảo vệ không cấp phòng vượt khả dụng theo (hotel, roomType, stayDate); Booking không tự trừ tồn của Inventory.

**Storage:** booking_header(tenantId, bookingId, guestId, status, currency, version), booking_night(tenantId, bookingId, nightLineId, stayDate, roomTypeId, quantity, nightlyPrice). Nếu mỗi booking được phép chỉ một loại phòng mỗi đêm thì một khóa tự nhiên có thể dùng stayDate+roomTypeId; khi có nhiều phân bổ riêng, lineId tránh gộp sai. Giá snapshot đã chấp nhận không đổi khi Catalog cập nhật giá hôm sau.

**Exchange:** ConfirmBooking là command. BookingConfirmed là sự thật chỉ công bố sau commit và có bookingId, tenantId, eventId, schemaVersion, occurredAt, amount/currency đã kiểm tra. Không tự phát giấy tờ cá nhân, số thẻ hoặc toàn bộ hồ sơ khách cho mọi consumer.

**Phối hợp:** RoomsReserved chứng minh Inventory đã giữ phòng theo chính sách, **không** chứng minh PaymentCaptured. Event lặp cần dedup và command retry cần idempotency. Nếu PaymentConfirmed đến trễ sau khi booking đã hủy, cần trạng thái/phương án đối soát và bù theo quy tắc, không âm thầm chuyển booking thành CONFIRMED.

**ACL:** Nếu legacy PAID=Y nghĩa là đã authorized, chỉ map thành AUTHORIZED; không map thành CAPTURED. Khi tài liệu nguồn không rõ, đưa vào trạng thái chưa xác định và xác minh thay vì đoán.

**Analytics:** fact_booking_confirmed có grain một lần xác nhận hợp lệ của một Booking; fact_stayed_room_night có grain một đêm phòng/đơn vị ở thực tế. Ngày xác nhận và ngày lưu trú khác nhau; giá trị BookingConfirmed không tự là doanh thu dịch vụ đã cung cấp. Hủy/hoàn/điều chỉnh có nguồn và phép đo riêng.

## 19. Quy trình thiết kế và checklist bàn giao

Khi nhận yêu cầu "lưu và chia sẻ dữ liệu X", nên làm theo thứ tự:

1. Viết **ngôn ngữ nghiệp vụ** và bounded context: X nghĩa gì, nguồn nào có thẩm quyền.
2. Ghi **bất biến và thời điểm phải đúng**, rồi tìm aggregate root/domain service chịu trách nhiệm.
3. Chọn **storage** theo transaction và truy vấn: bảng, document, khóa, FK, CHECK, version, index, partition.
4. Viết **repository mapping** cho danh tính, trạng thái, dữ liệu dẫn xuất; không để persistence entity trở thành public contract.
5. Thiết kế **exchange** theo consumer/use case: command, response, event, schemaVersion và error contract.
6. Quy định **đồng bộ/bất đồng bộ**: commit, outbox, retry, idempotency, sequence, pending state và bù.
7. Bổ sung **ACL** cho các mô hình ngoài dùng ngữ nghĩa, đơn vị hoặc ID khác.
8. Tách **read/analytics** theo grain, metric, freshness, quyền và lineage.
9. Lập kế hoạch tiến hóa domain, storage và contract độc lập có migration/test.
10. Thử các trường hợp lỗi đồng thời, dữ liệu đến muộn, caller sai quyền và contract cũ.

Checklist:

- Domain có hành vi bảo vệ bất biến hay chỉ là các setter trên cấu trúc dữ liệu?
- Aggregate/bounded context nào **sở hữu quyết định** và nguồn nào chỉ là bản sao?
- Storage có transaction, constraint, isolation, khóa và đường ghi được kiểm soát?
- Mapping có giữ chính xác ID, tenant, currency, timestamp, trạng thái và version?
- REST DTO/event được thiết kế theo mục đích bên nhận hay chỉ serialize ORM?
- Command, event, CDC, audit và analytic fact đã phân biệt đúng chưa?
- Outbox và consumer có xử lý retry, duplicate, out-of-order và rollback?
- Giao thức nhiều service có trạng thái trung gian và quy trình bù rõ?
- ACL có chuyển **nghĩa** thay vì chỉ đổi tên field?
- Schema migration có thể diễn ra mà không bắt buộc đổi đồng thời mọi client?
- Read model có grain, metric, freshness, lineage và quyền riêng tư tương xứng?
- Đã kiểm thử những ranh giới dễ gây lỗi nhất với dữ liệu và engine thật?

**Kết luận:** **Mô hình miền** bảo vệ **ý nghĩa và bất biến nghiệp vụ**; **mô hình lưu trữ** hiện thực **khóa, ràng buộc, transaction và hiệu năng**; **mô hình trao đổi** duy trì **hợp đồng ổn định, rõ ngữ nghĩa và có kiểm soát quyền** giữa các bên. Chúng có thể dùng những kiểu dữ liệu và cấu trúc khác nhau, miễn là ánh xạ đúng và nguồn quyết định không bị đánh tráo. Bằng ranh giới sở hữu rõ, transaction đúng phạm vi, hợp đồng có phiên bản, ACL và kiểm thử tương thích, hệ thống có thể tích hợp nhiều mô hình dữ liệu mà vẫn tiến hóa linh hoạt và kiểm chứng được.


