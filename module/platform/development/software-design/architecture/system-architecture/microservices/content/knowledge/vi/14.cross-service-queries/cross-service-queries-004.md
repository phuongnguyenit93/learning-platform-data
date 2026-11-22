# CQRS khi nhu cầu đọc và ghi có cấu trúc khác nhau

> **Nguyên tắc:** CQRS (Command Query Responsibility Segregation) tách trách nhiệm **xử lý lệnh thay đổi trạng thái** khỏi trách nhiệm **truy vấn dữ liệu**. Mô hình ghi được thiết kế quanh bất biến và quy tắc nghiệp vụ; mô hình đọc được thiết kế theo hình dạng mà người dùng, báo cáo hoặc client cần. CQRS đáng cân nhắc khi hai loại nhu cầu khác nhau rõ rệt, nhưng **không mặc định đòi hai database, hai microservice, message broker hay event sourcing**.

Bài thuộc nhóm **Truy vấn liên dịch vụ** của kiến trúc microservices. Mục tiêu là hiểu cách xây read view từ nhiều bounded context mà không phá data ownership, không tạo hàng trăm lời gọi đồng bộ cho một màn hình và không hy sinh tính đúng đắn của command.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt command, query, write model, read model, projection và source of truth.
2. Giải thích khi nào CRUD truyền thống là đủ, khi nào CQRS giúp giảm coupling hoặc tải query.
3. Phân biệt CQRS ở mức code với CQRS dùng read store riêng.
4. Thiết kế ví dụ Order: write side bảo vệ trạng thái đơn, read side phục vụ danh sách và dashboard.
5. Tổ chức cập nhật projection bằng event và transactional outbox.
6. Xử lý eventual consistency, read-after-write gap, retry, deduplication, out-of-order và rebuild.
7. Nhận diện sự khác nhau giữa CQRS, event sourcing, database replica, CDC và API composition.
8. Xây API/handler minh họa bằng Java/Spring Boot và đánh giá chi phí vận hành trước khi áp dụng.

## 2. Vấn đề: đọc và ghi có mục tiêu khác nhau

Trong một nền tảng bán hàng, hành vi **đặt hàng** phải giữ những điều kiện như:
- Không xác nhận đơn đã bị hủy.
- Chỉ chấp nhận báo giá còn hiệu lực theo chính sách.
- Không sử dụng dữ liệu tồn kho ước lượng để thay việc giữ hàng chính thức.
- Không xử lý cùng một yêu cầu thanh toán hai lần.
- Ghi nhận chuyển trạng thái của Order theo transaction và version phù hợp.

Trong khi đó, màn hình **Lịch sử đơn hàng** muốn thấy:
- Order ID, thời gian tạo, trạng thái tổng hợp và số tiền đã chốt.
- Tên/ảnh sản phẩm, tracking vận chuyển, trạng thái thanh toán.
- Lọc theo khách hàng, trạng thái, ngày, phân trang và sắp xếp.
- Một trang danh sách dài nhưng phản hồi nhanh, ít round trip.
- Dữ liệu có thể được hiển thị bằng một projection thay vì JOIN mọi hệ thống.

Mô hình viết để xử lý một command và bảo vệ bất biến thường khác với hình dạng read view tối ưu cho lọc và hiển thị.

### 2.1. Khi dùng cùng một mô hình cho tất cả

~~~text
POST /orders ------+
GET /orders/{id} --+--> OrderEntity + ORM --> SQL database
GET /dashboard ----+
~~~

Với ứng dụng CRUD nhỏ, ít truy vấn đặc biệt, một mô hình có thể đơn giản và hiệu quả. Không có lý do bắt buộc tách chỉ vì một bài giảng DDD nhắc tới CQRS.

Khi nhiều màn hình bắt đầu cần những trường và phép tổng hợp khác xa write aggregate, việc ép entity nghiệp vụ vào mọi API có thể dẫn đến:
- Entity quá nhiều quan hệ chỉ để phục vụ UI.
- N+1 database queries hoặc remote N+1 calls.
- Query nặng tranh chấp tài nguyên với transaction ghi.
- Mọi thay đổi giao diện kéo theo thay đổi domain model.
- Rò rỉ JPA entity hoặc schema nội bộ sang consumer.
- Truy vấn từ nhiều context chạm trực tiếp bảng của nhau.

### 2.2. Phân tách theo CQRS

~~~text
POST /orders
    |
    v
[Order Command Handler] -> [Order Write Model] -> [Order Write DB]
                                                     |
                                           event / outbox / CDC
                                                     |
                                                     v
                                            [Projection Builder]
                                                     |
                                                     v
                                                 [Read Store]
                                                     |
                       GET /my-orders ---------------+
                       GET /dashboard ---------------+
~~~

Write side sở hữu các quyết định nghiệp vụ; read side trả query theo hợp đồng. Read store có thể là cùng database, một view/SQL projection, một read replica hoặc một database/index riêng tùy nhu cầu.

## 3. Từ vựng và ranh giới khái niệm

### 3.1. Command

**Command** là yêu cầu thực hiện hành vi có thể làm thay đổi trạng thái, chẳng hạn:
- PlaceOrder
- ConfirmOrder
- CancelOrder
- ReserveStock
- CapturePayment

Command có thể được chấp nhận, bị từ chối vì quy tắc, hoặc có kết quả không xác định khi timeout. Command handler phải kiểm tra điều kiện nghiệp vụ trong phạm vi context sở hữu. Không có đảm bảo rằng một HTTP 200 từ proxy nghĩa là mọi giao dịch xuyên service đã commit.

### 3.2. Query

**Query** yêu cầu dữ liệu mà không thay đổi trạng thái nghiệp vụ, ví dụ:
- GetOrderDetail
- ListMyOrders
- SearchOrders
- GetDailySales
- GetShipmentOverview

Một query có thể ghi logs/metrics hoặc cập nhật cache kỹ thuật, nhưng không nên vô tình thu tiền, tạo đơn hoặc thực hiện state transition như một side effect của thao tác đọc.

### 3.3. Write model

Write model thể hiện luật, bất biến, trạng thái, aggregate và transaction. Nó ưu tiên **consistency và tính đúng đắn** của quyết định. Dữ liệu có thể được chuẩn hóa để giảm việc ghi mâu thuẫn.

### 3.4. Read model

Read model là hình dạng được tối ưu cho query: DTO, SQL view, bảng denormalized, materialized view, search index, cache hoặc dashboard projection. Nó được thiết kế theo access pattern, pagination, filter và thời gian phản hồi cần thiết.

**Read model phái sinh không mặc định là nguồn sự thật.** Nếu Payment sở hữu trạng thái giao dịch, projection OrderView không được quyền tự chuyển Payment từ PENDING thành CAPTURED.

### 3.5. Projection

Projection là quy trình tính và cập nhật read view từ dữ liệu nguồn, thường qua domain event, change stream hoặc API export có kiểm soát. Projector có thể phải xử lý event trùng, đến muộn, sai thứ tự và schema phiên bản cũ.

## 4. CQRS không phải một topology cố định

| Lựa chọn | Thành phần | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Command/query handlers trong một ứng dụng | Cùng process, cùng DB | Rõ trách nhiệm, ít hạ tầng | Read/Write có thể tranh chấp DB |
| Query SQL/DTO chuyên dụng | Cùng DB, schema đọc tối ưu | Giảm ORM loading và N+1 | Chưa scale data store độc lập |
| Read replica | Write primary, read replica | Phân tải đọc | Replica lag, failover/consistency |
| Read projection riêng | Write DB → event/outbox → read store | Read schema, index, scale độc lập | Eventual consistency, consumer/rebuild |
| Search projection | Write DB → events → search engine | Text search, ranking, filter | Index lag, schema/index migration |
| Analytics projection | Events/CDC → warehouse | Tổng hợp nhiều chiều/lịch sử | Freshness, đối soát và chi phí data |

CQRS là **phân chia trách nhiệm**; dùng thêm database và broker là **quyết định triển khai**. Không nên để cách vẽ sơ đồ ép dự án phải chọn công nghệ.

## 5. Ví dụ xuyên suốt: màn hình lịch sử đơn

Khách cần xem danh sách đơn gồm tổng tiền chốt, trạng thái thanh toán và giao hàng. Nguồn dữ liệu có thể thuộc các bounded context:

| Dữ liệu | Owner | Điều cần lưu ý |
| --- | --- | --- |
| Order ID, dòng hàng, tổng tiền chốt, trạng thái Order | Ordering | Snapshot giá giao dịch không được tự đổi khi giá hiện tại đổi |
| Thông tin catalog hiện tại | Catalog | Tên/ảnh hiện tại khác snapshot lúc mua |
| Payment captured/refunded | Payment | Payment là nguồn quyết định trạng thái thu tiền |
| Shipment dispatched/delivered | Fulfillment | Shipping status khác Order lifecycle |
| Return request | Returns | Quy tắc trả hàng thuộc Returns |

Một cách dùng API composition:

~~~text
Browser -> BFF -> Ordering
              -> Payment
              -> Fulfillment
              -> Catalog
              -> Assemble response
~~~

Với một đơn lẻ, cách này có thể hợp lý. Nhưng nếu màn hình hiển thị 100 đơn và mỗi đơn phải gọi nhiều API nhỏ, có thể phát sinh hàng trăm RPC đồng bộ.

Read projection là một lựa chọn khác:

~~~text
Ordering   -- OrderConfirmed --------+
Payment    -- PaymentCaptured -------+--> OrderView Projector
Fulfillment-- ShipmentDispatched ----+         |
Catalog    -- ProductPublished ------+         v
                                         OrderView DB
                                             |
                                             v
                                         GET /my-orders
~~~

Trong projection có thể giữ:

~~~json
{
  "orderId": "O-1001",
  "customerId": "C-77",
  "createdAt": "2026-11-11T09:00:00Z",
  "orderStatus": "CONFIRMED",
  "currency": "VND",
  "totalMinorUnits": 390000,
  "paymentStatus": "CAPTURED",
  "shippingStatus": "PACKED",
  "projectionUpdatedAt": "2026-11-11T09:00:02Z",
  "lines": [
    {
      "sku": "SKU-9",
      "productTitleAtPurchase": "Áo cotton",
      "quantity": 2,
      "unitPriceMinorUnits": 195000
    }
  ]
}
~~~

Ví dụ dùng giá trị minh họa. Hợp đồng tiền tệ cần quy định đơn vị, chính sách làm tròn và quan hệ giữa currency với giá trị.

### 5.1. Tại sao Order lưu snapshot giá?

Catalog/Pricing có thể đổi giá ngày mai. Đơn đã được khách đồng ý mua cần phản ánh giá ở thời điểm giao dịch. Đừng lấy current catalog price rồi tính lại các đơn lịch sử trong read view.

### 5.2. Tại sao không ghi Payment bằng cách sửa OrderView?

OrderView là projection dùng để đọc. Nếu người quản trị muốn hoàn tiền, phải gửi RefundPayment tới Payment owner. Payment kiểm tra quyền và bất biến, ghi trạng thái, rồi phát sự kiện cập nhật view. Sửa read store để trông như đã hoàn tiền sẽ làm sai nguồn dữ liệu thật.

## 6. Write side: ranh giới bất biến

Một command PlaceOrder có thể đi qua:

~~~text
POST /orders
     |
     v
Validate request and identity
     |
     v
PlaceOrder Command Handler
     |
     v
Order Aggregate
  - enforce state transitions
  - validate accepted quote
  - validate invariant
     |
     v
Local transaction
  - insert/update Order
  - insert outbox message
     |
     v
Return committed Order state
~~~

Khi một bước thực sự đòi xác nhận từ Inventory/Payment, có thể phải dùng RPC hoặc workflow nhiều bước và trạng thái PENDING. Đừng coi @Transactional trong Spring là một distributed transaction cho HTTP calls sang service khác.

### 6.1. Concurrency ở write side

Ví dụ CancelOrder và ConfirmOrder đến đồng thời. Có thể dùng optimistic locking bằng version:

~~~sql
UPDATE orders
SET status = 'CONFIRMED', version = version + 1
WHERE id = 'O-1001'
  AND status = 'PENDING'
  AND version = 7;
~~~

Nếu không cập nhật được dòng nào, write handler phải xem lại trạng thái/phiên bản và trả conflict hoặc kết quả nghiệp vụ phù hợp. Không dựa vào OrderView có thể trễ để quyết định điều kiện ghi.

### 6.2. Command có tên theo ý định nghiệp vụ

Tên PlaceOrder/CancelOrder làm rõ luật và điều kiện. Một lệnh UpdateOrderStatus(status) cho phép bất kỳ trạng thái nào dễ bỏ qua state machine. CQRS có ích khi phân tách cách **quyết định** với cách **đọc để hiển thị**.

## 7. Query side: tối ưu query thực tế

Một query danh sách đơn theo khách:

~~~text
GET /my-orders?status=CONFIRMED&pageSize=20
    |
    v
OrderReadQueryHandler
    |
    v
SELECT order_id, created_at, status,
       total_minor_units, currency,
       payment_status, shipping_status
FROM order_views
WHERE customer_id = :customerId
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT :limit;
~~~

Có thể thiết kế index:

~~~sql
CREATE INDEX idx_order_views_customer_status_created
ON order_views (
  customer_id,
  status,
  created_at DESC,
  order_id DESC
);
~~~

Query thực tế nên có pagination, giới hạn page size, authorization, cơ chế cursor khi dữ liệu lớn và kế hoạch xử lý query được kiểm tra bằng EXPLAIN/metrics.

**Không mặc định đọc nguyên entity JPA với mọi association** khi endpoint chỉ cần một DTO danh sách. Read side có thể dùng JDBC/jOOQ/SQL projection hoặc cách khác theo workload, trong khi write side dùng aggregate/JPA nếu phù hợp.

### 7.1. Một read model không cần chứa tất cả dữ liệu

Đừng tạo bảng “everything_view” với mọi field từ mọi context. Hãy thiết kế view theo nhu cầu rõ như OrderListItem, OrderDetailView, DailySalesSummary. Càng nhiều bản sao và index, chi phí cập nhật/cleanup càng lớn.

## 8. Đồng bộ write → read: vấn đề dual write

Một thiết kế ngây thơ:

~~~text
1. Commit Order to Ordering DB.
2. Publish OrderConfirmed to broker.
~~~

Nếu DB commit thành công nhưng broker publish lỗi, Order tồn tại mà read store không nhận message. Nếu publish trước rồi DB rollback, projection có thể hiển thị sự kiện chưa từng commit.

### 8.1. Transactional outbox

Ghi trạng thái và một outbox record trong cùng transaction local:

~~~sql
BEGIN;

UPDATE orders
SET status='CONFIRMED'
WHERE id='O-1001';

INSERT INTO outbox (
  event_id, aggregate_id, event_type,
  event_version, payload, created_at
) VALUES (
  'evt-1001', 'O-1001', 'OrderConfirmed', 1,
  '{"orderId":"O-1001","status":"CONFIRMED"}',
  CURRENT_TIMESTAMP
);

COMMIT;
~~~

Publisher đọc outbox, phát broker rồi checkpoint/mark sent. Khi publish thành công nhưng publisher chết trước khi đánh dấu, event có thể phát lại. **Outbox giúp không mất ý định phát event nhưng không bảo đảm chỉ nhận một lần**.

Consumer cần idempotent processing.

### 8.2. Event không phải CRUD row change

Nên phát OrderConfirmed khi Order được xác nhận theo định nghĩa Ordering; không đơn giản phát EntityUpdated chứa toàn bộ JPA entity. Consumer cần hiểu ý nghĩa sự kiện và semantics của từng version, không phụ thuộc cấu trúc bảng nội bộ.

## 9. Idempotent projector và event trùng

Trong nhiều broker, message có thể được phát lại khi consumer xử lý xong nhưng ACK bị mất. Nếu một event PaymentCaptured bị tính doanh thu hai lần, dashboard sẽ sai dù broker vẫn vận hành như thiết kế.

Một mô hình local transaction:

~~~text
Begin transaction in Read DB
  if processed_events contains (consumerName, eventId):
      no-op
  else:
      validate schema and state/version
      apply projection update
      insert processed_events(consumerName, eventId)
Commit
ACK broker message
~~~

Processed-event key phải có unique constraint, và việc cập nhật projection + đánh dấu processed phải ở **cùng transaction read-side**. Trong production, cần xử lý race condition bằng cơ chế insert-if-absent/unique key nguyên tử, không chỉ đọc rồi ghi tách rời.

### 9.1. Thứ tự sự kiện

OrderConfirmed version 9 có thể đến sau OrderCancelled version 10. Nếu projector ghi đè mỗi lần, view có thể hiển thị CONFIRMED dù Order đã CANCELLED.

Có thể lưu sourceVersion/sequence trong projection:

~~~text
Incoming event v10:
  current sourceVersion = 9
  apply v10 and set sourceVersion = 10

Incoming event v9 delayed:
  current sourceVersion = 10
  reject/ignore stale update
~~~

Tuy nhiên nếu event là **delta** (tăng 10, giảm 4), không thể luôn bỏ qua một event bị trễ vì có thể mất một phần phép cộng. Cần policy đảm bảo xử lý đủ sự kiện theo thứ tự hoặc rebuild từ snapshot.

Message broker chỉ đảm bảo ordering theo những phạm vi nhất định (ví dụ partition key), không đồng nghĩa mọi consumer nhận đúng thứ tự toàn cục trong mọi điều kiện replay và retry.

## 10. Eventual consistency: phản hồi đã ghi nhưng view còn trễ

Ví dụ:

~~~text
10:00:00.000  POST /orders commits Order O-1001
10:00:00.100  Browser GET /my-orders
10:00:01.200  Read projection receives OrderPlaced
10:00:01.300  GET /my-orders includes O-1001
~~~

Khoảng 1,2 giây là ví dụ minh họa. Nếu UI không có kế hoạch, người dùng tưởng đơn đã mất và đặt lại.

### 10.1. Chiến lược read-your-writes

**Trả kết quả của command:** POST có thể trả orderId, trạng thái đã commit và thông tin cần hiển thị ngay; client không cần chờ read projection để biết kết quả tạo đơn.

**Đọc trực tiếp từ owner trong tình huống đặc biệt:** GET /orders/{id} dùng write-side API có thẩm quyền cho thao tác đọc ngay sau ghi, còn GET /my-orders dùng read projection.

**Version/read barrier:** command trả aggregateVersion/commit marker; query chờ projection đạt ít nhất version đó trong một deadline được giới hạn, nếu chưa đạt thì báo đang cập nhật.

**Optimistic UI/PENDING:** hiển thị “đơn đang được xử lý” khi quy trình chưa CONFIRMED; cập nhật sau qua polling, SSE hoặc WebSocket.

**Idempotency cho command:** PlaceOrder retry với cùng idempotency key phải không tạo đơn thứ hai. Đây là cơ chế của write side, không phải vấn đề mà read store giải quyết hộ.

### 10.2. Stale window khác nhau theo use case

| Use case | Eventual consistency phù hợp đến đâu? |
| --- | --- |
| Dashboard marketing | Thường có thể trễ vài giây/phút nếu ghi rõ thời điểm cập nhật |
| Search index | Có thể trễ tùy nghiệp vụ publish/unpublish |
| Danh sách đơn của khách | Có thể trễ ngắn nếu UX có read-after-write strategy |
| Xác nhận số lượng còn hàng | Phải dựa vào Inventory owner, không dựa mù vào projection |
| Quyết định thu/hoàn tiền | Payment owner phải xác nhận, projection có thể phục vụ hiển thị |
| Báo cáo tài chính | Cần watermark, đối soát và chốt kỳ theo yêu cầu kinh doanh |

Không nên nói chung “read model được phép eventual consistent”. Phải chỉ ra stale window chấp nhận được **cho từng quyết định** mà consumer đưa ra.

## 11. CQRS khác Event Sourcing

Hai mẫu hay được dùng cùng nhau nhưng không đồng nghĩa.

**CQRS** chia trách nhiệm đọc/ghi. Write DB có thể lưu current-state tables giống hệ thống CRUD bình thường.

**Event Sourcing** dùng lịch sử domain events làm nguồn sự thật để tái tạo aggregate state.

~~~text
CQRS without Event Sourcing:
  Commands -> Write DB (current Order state)
                    |
                 Outbox events
                    |
                 Read projection

CQRS with Event Sourcing:
  Commands -> Event Store as source of truth
                    |
              Replay events
                    |
            Aggregate state / read projections
~~~

Một hệ thống lưu orders trong PostgreSQL rồi gửi OrderConfirmed qua outbox **không tự trở thành event sourcing**. Event sourcing có chi phí riêng về event evolution, snapshots, rebuild, audit, compliance và migration.

### 11.1. CDC khác event sourcing

Change Data Capture đọc thay đổi database ở mức row/log. Nó có thể vận chuyển outbox event hoặc đồng bộ read store. Nhưng một event CDC “row updated” không tự là domain event có ý nghĩa. Thiết kế CDC phải xem ownership, schema changes, retention, reprocessing và privacy.

## 12. CQRS ở modular monolith

CQRS có thể bắt đầu bằng cấu trúc package:

~~~text
commerce/
  ordering/
    command/
      PlaceOrderHandler
      CancelOrderHandler
    query/
      FindMyOrdersHandler
      FindOrderDetailHandler
    domain/
      Order
      OrderPolicy
    infrastructure/
      OrderRepository
      OrderReadRepository
  inventory/
  pricing/
~~~

Một Spring Boot JAR vẫn có thể chạy toàn hệ thống. Command/query handlers có interface rõ, cùng database transaction nếu thích hợp. Khi chưa có bằng chứng read scale riêng hoặc query chậm, đây thường là cách tiếp cận ít chi phí hơn event-driven projection riêng.

CQRS **không yêu cầu tách query service thành một process**, và một bounded context không bắt buộc có read/write service riêng.

## 13. Java/Spring Boot: command handler minh họa

Dùng command biểu diễn ý định nghiệp vụ:

~~~java
package example.ordering.application;

import java.util.List;
import java.util.UUID;

public record PlaceOrderCommand(
        UUID customerId,
        List<OrderLineInput> lines,
        String idempotencyKey) {}

public record OrderLineInput(String sku, int quantity) {}

public record PlaceOrderResult(
        UUID orderId,
        String status,
        long version) {}
~~~

Handler khái niệm:

~~~java
package example.ordering.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderHandler {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderHandler(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        // Authorization, quote validation và idempotency cần
        // được thực thi đúng contract trong code production.
        var order = Order.place(
                command.customerId(), command.lines());

        orders.save(order);
        outbox.save(order.toOrderPlacedEvent());

        return new PlaceOrderResult(
                order.id(), order.status().name(), order.version());
    }
}
~~~

Ví dụ chưa định nghĩa đầy đủ Order, repositories, security, transaction ID generation hoặc nghiệp vụ kiểm tra quote. Nó minh họa **write state + outbox trong cùng transaction cục bộ**. Nếu Order cần Inventory/Payment, các lệnh xuyên mạng không được coi là cùng transaction chỉ nhờ @Transactional.

### 13.1. Command HTTP response đúng semantics

~~~text
201 Created:
  orderId = O-1001
  status = CONFIRMED
  meaning: Order resource được tạo và đủ điều kiện xác nhận

202 Accepted:
  operationId = OP-1001
  orderStatus = PENDING
  meaning: yêu cầu đã tiếp nhận, workflow vẫn tiếp tục
~~~

Một Order resource có thể được tạo với status PENDING và trả 201 nếu contract diễn đạt đúng ý nghĩa “resource created”. Nhưng không được nói “thanh toán thành công” khi chỉ mới đưa một message vào queue.

## 14. Java/Spring Boot: query handler

Read DTO:

~~~java
package example.ordering.query;

import java.time.Instant;
import java.util.UUID;

public record OrderListItem(
        UUID orderId,
        Instant createdAt,
        String status,
        String paymentStatus,
        String shippingStatus,
        long totalMinorUnits,
        String currency) {}
~~~

Query handler:

~~~java
package example.ordering.query;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class FindMyOrdersHandler {
    private final OrderReadRepository views;

    public FindMyOrdersHandler(OrderReadRepository views) {
        this.views = views;
    }

    public List<OrderListItem> handle(
            UUID authenticatedCustomerId, int requestedLimit) {
        int limit = Math.max(1, Math.min(requestedLimit, 100));
        return views.findRecentByCustomer(authenticatedCustomerId, limit);
    }
}
~~~

Query endpoint phải xác định authenticatedCustomerId từ security context/token đã được xác minh, không tin vào customerId tùy ý của client. Read model denormalized vẫn phải tuân thủ tenant authorization và bảo vệ dữ liệu cá nhân.

## 15. Spring Boot: projector minh họa

Event hợp đồng:

~~~java
package example.contracts.ordering;

import java.time.Instant;
import java.util.UUID;

public record OrderPlacedEvent(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        String status,
        long orderVersion,
        Instant occurredAt,
        int schemaVersion) {}
~~~

Read-model updater:

~~~java
package example.ordering.readmodel;

import example.contracts.ordering.OrderPlacedEvent;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPlacedProjector {
    private final ProcessedEventRepository processed;
    private final OrderViewRepository views;

    public OrderPlacedProjector(
            ProcessedEventRepository processed,
            OrderViewRepository views) {
        this.processed = processed;
        this.views = views;
    }

    @Transactional
    public void apply(OrderPlacedEvent event) {
        // insertIfAbsent dùng UNIQUE(consumer_name, event_id).
        if (!processed.insertIfAbsent("order-view", event.eventId())) {
            return;
        }

        // Implementation phải chống ghi đè phiên bản mới
        // bằng message cũ hoặc sai thứ tự.
        views.upsertIfNewer(
                event.orderId(), event.customerId(),
                event.status(), event.orderVersion());
    }
}
~~~

Đây là thiết kế minh họa, không phải consumer đầy đủ. Để an toàn:
- Dedup record và projection update phải commit cùng một transaction read DB.
- Broker ACK sau khi transaction commit.
- Nếu process chết trước ACK, event có thể được gửi lại; dedup bỏ qua.
- Upsert phải xử lý version, event type, missing gap và race condition.
- Nếu event version mới không parse được, cần DLQ/alert và recovery.
- Không tự gọi gửi email/thu tiền khi replay projection.

## 16. Read model schema và index

Write schema có thể chuẩn hóa:

~~~text
orders(order_id, customer_id, status, version, created_at)
order_lines(order_id, sku, quantity, accepted_unit_price)
order_transitions(order_id, from_state, to_state, occurred_at)
~~~

Read schema phục vụ một màn:

~~~text
order_views(
  tenant_id,
  order_id,
  customer_id,
  created_at,
  status,
  payment_status,
  shipping_status,
  total_minor_units,
  currency,
  source_order_version,
  projection_updated_at
)
~~~

Có thể index theo query:

~~~sql
CREATE INDEX idx_order_views_lookup
ON order_views(
  tenant_id,
  customer_id,
  status,
  created_at DESC,
  order_id DESC
);
~~~

Một read model có thể denormalize để truy vấn nhanh nhưng cần bảo đảm không chứa dữ liệu không được phép, có lifecycle/retention và xử lý stale updates. Với danh sách lớn, cân nhắc keyset pagination, composite index và query plan thực tế trước khi thêm công nghệ lưu trữ mới.

## 17. API composition hay projection?

**API composition** gọi các owner khi query xảy ra:

~~~text
Frontend -> BFF
               |-> Ordering GET Order
               |-> Payment GET Payment
               +-> Shipping GET Tracking
             -> Assemble response
~~~

Ưu điểm: ít moving parts, dễ đọc dữ liệu tương đối mới, hợp lý với một vài nguồn và ít request. Nhược điểm: synchronous fan-out, availability coupling, tail latency và remote N+1 khi danh sách dài.

**CQRS projection** cập nhật trước dữ liệu đọc:

~~~text
Ordering, Payment, Shipping -> Events -> Read Projector
                                         |
                                         v
                                     OrderView DB
                                         |
                                         v
                                    GET /my-orders
~~~

Ưu điểm: query chỉ cần đọc một store có index phù hợp, dễ scale read, tránh gọi nhiều service mỗi request. Nhược điểm: eventual consistency, event schema/versioning, lag, replay, dedup, rebuild, data privacy.

| Nhu cầu | Hướng khởi đầu thường hợp lý |
| --- | --- |
| Xem một Order, cần trạng thái mới nhất | Query tới owner hoặc composition |
| Xem 100 Order với nhiều nguồn, request lặp liên tục | Projection hoặc batch API |
| Dashboard tổng hợp theo ngày, cho phép trễ | Projection/materialized view |
| Sửa trạng thái thanh toán | Command tới Payment owner |
| Search full-text trên hàng triệu sản phẩm | Search projection/index nếu có giá trị |
| Form CRUD nhỏ, query nhanh | Chung DB + query DTO/index |

Không có quy tắc phải chọn một mô hình giao tiếp cho toàn hệ thống.

## 18. Rebuild read projection

Một read model có thể cần rebuild khi:
- Thêm field vào view.
- Sửa bug projector đã làm sai số liệu quá khứ.
- Chuyển database/search engine.
- Tiếp nhận event schema mới.
- Dữ liệu bị lệch sau outage hoặc xử lý message sai.

Quy trình:
1. Định nghĩa schema/projection v2, không vội xóa v1 đang phục vụ.
2. Xác định nguồn bootstrap: event history, snapshot, export từ owner hoặc CDC.
3. Backfill dữ liệu theo batch và ghi watermark/version.
4. Catch up các event phát sinh trong thời gian backfill.
5. Đối soát record count, totals, status, tenant scope và source version.
6. Chuyển traffic read qua flag/canary.
7. Theo dõi error, stale lag và kết quả nghiệp vụ.
8. Chỉ xóa v1 sau khi đã chứng minh v2 đúng và không còn consumer cần v1.

### 18.1. Event retention có thể không đủ

Nếu broker chỉ giữ 7 ngày event nhưng read store cần lịch sử 3 năm, xóa read store rồi replay broker sẽ **mất dữ liệu lịch sử**. Cần snapshot/historical event storage hoặc export có quản trị. Không tuyên bố read model có thể rebuild trước khi chứng minh nguồn phục hồi đầy đủ.

### 18.2. Replay không được tạo side effect

Projector replay OrderConfirmed để dựng bảng OrderView; nó không được gửi email xác nhận lần nữa, thu tiền hoặc reserve stock. Những consumer nghiệp vụ có side effect phải có idempotency và phạm vi xử lý riêng.

## 19. Versioning cho event và query contract

Một event OrderPlaced v1 không có currency, còn v2 có currency. Consumer v2 có thể gặp v1 trong broker backlog, replay hoặc khi producer cũ vẫn chạy. Cần adapter/fallback với semantics đúng, không tự đoán currency khi không có cơ sở.

Tương tự, một event v2 mang OrderConfirmed với ý nghĩa mới “chỉ tiếp nhận yêu cầu” sẽ phá consumer cũ dù JSON vẫn parse được. Hãy dùng event type mới hoặc đường chuyển đổi được kiểm soát thay vì đổi ngầm business meaning.

Read API cũng có contract version: thêm field có thể tương thích nếu client bỏ qua unknown fields, nhưng đổi đơn vị tiền, timezone hoặc enum semantics cần đánh giá breaking change. CQRS không làm biến mất nhu cầu API compatibility.

## 20. Observability và đối soát

Những metrics quan trọng khi CQRS có read store riêng:

- **Write command latency/error rate** và business rejection rate.
- **Query latency p50/p95/p99** và request throughput.
- **Projection lag theo thời gian**, từ event commit đến view update.
- **Consumer backlog** và tốc độ xử lý message.
- **Outbox records quá tuổi** hoặc publisher failure.
- **Parse errors, DLQ, missing-event gaps** và số message trùng bị bỏ.
- **Reconciliation mismatches** giữa source of truth và projection.
- **Read store CPU/IO, index cost, storage growth** và rebuild duration.
- **Authentication/authorization failures** trên read path.

Ví dụ SLO giả định:

~~~text
GET /my-orders p95 <= 250 ms
Projection freshness p99 <= 5 seconds
Missing event count after reconciliation = 0
Write invariants violated = 0
~~~

Số chỉ minh họa; không phải ngưỡng CQRS chuẩn cho mọi ngành. Dashboard có thể chấp nhận trễ phút, còn một màn hiển thị đơn vừa tạo nên có read-after-write strategy.

### 20.1. Queue lag bằng 0 chưa đủ

Một event bị mất vì publisher lỗi có thể khiến queue không có backlog nhưng read store vẫn sai. Cần outbox monitoring và đối soát source dữ liệu, không chỉ metric consumer lag.

## 21. Failure modes điển hình

**Write thành công, read chưa thấy:** dùng response command, read authoritative, version barrier hoặc trạng thái PENDING; monitor lag.

**Outbox publisher lỗi:** giữ event bền trong outbox, retry theo policy và cảnh báo backlog quá tuổi.

**Event được gửi hai lần:** dedup eventId trong read store cùng transaction, không nhân đôi số liệu.

**Event sai thứ tự:** dùng aggregateVersion, partition key thích hợp, xử lý gap hoặc snapshot/rebuild.

**Event không parse được:** schema evolution, compatibility tests, DLQ, runbook replay; không bỏ message im lặng.

**Read store unavailable:** trả lỗi phù hợp hoặc fallback có giới hạn; tránh chuyển toàn bộ tải đọc đột ngột sang write DB làm ảnh hưởng command.

**Projection sai:** đối soát, cô lập lỗi, rebuild từ nguồn chuẩn. Không “sửa tay” read view rồi coi nguồn sự thật đã đúng.

**Read model rò rỉ dữ liệu nhiều tenant:** kiểm tra tenant_id và quyền ở mọi query, dữ liệu nhạy cảm, audit và security tests.

**Command timeout sau khi xử lý:** dùng idempotency key/operation ID và tra trạng thái; timeout không đồng nghĩa command thất bại.

## 22. Bảo mật và dữ liệu cá nhân

Projection thường sao chép dữ liệu, có thể làm tăng bề mặt rủi ro:
- Read view có thực sự cần họ tên, địa chỉ, số điện thoại đầy đủ không?
- Có tenant/merchant scope trong schema và mọi query không?
- Dữ liệu có được mã hóa khi truyền/lưu theo yêu cầu không?
- Khi người dùng cập nhật hoặc yêu cầu xóa thông tin, projection nào phải cập nhật?
- Event replay có thể khôi phục dữ liệu đáng ra đã được xóa không?
- Access logs/tracing có vô tình chứa PII không?
- Backup, retention và quyền truy cập của read store do ai sở hữu?

Read-only không đồng nghĩa “không có rủi ro”. Query service phải tuân thủ quyền xem dữ liệu như write owner.

## 23. Lộ trình áp dụng có kiểm soát

### Bước 1 — Xác định query có pain rõ

Ví dụ GET /my-orders p95 cao vì 300 RPC nội bộ khi hiển thị 100 đơn. Thu trace/metrics trước khi đề nghị event-driven projection.

### Bước 2 — Thử phương án đơn giản

Tối ưu index/SQL, query DTO, batch API, API composition có giới hạn, cache hoặc read replica nếu phù hợp. Nếu đạt SLO, không cần thêm read store riêng.

### Bước 3 — Làm rõ bounded context và data owner

Order, Payment, Fulfillment có nghĩa trạng thái và quyền thay đổi riêng. Chọn event contracts công bố business facts chứ không rò rỉ JPA schema.

### Bước 4 — Thiết kế read model và freshness

Chỉ lưu field cần, tenant scope, index, sourceVersion và updatedAt. Ghi rõ stale window và read-after-write UX.

### Bước 5 — Xây outbox/projector

Áp unique eventId, idempotency, xử lý version/order, retry/DLQ, schema evolution và telemetry. Không cho projector thực hiện side effect nghiệp vụ khi replay.

### Bước 6 — Backfill và đối soát

Dựng view v2, catch up event trong thời gian backfill, so sánh trạng thái/tổng tiền/record counts với owner và sửa mismatch.

### Bước 7 — Chuyển read traffic

Feature flag/canary cho query endpoint. Đo latency, errors, lag, business output và tải read/write. Có kế hoạch rollback read path phù hợp với capacity.

### Bước 8 — Quyết định có mở rộng không

CQRS đáng giữ nếu lợi ích về latency, tải hoặc độc lập phát triển bù cho chi phí hệ thống mới. Không nhân rộng CQRS sang tất cả module chỉ vì pilot đầu tiên thành công.

## 24. Những ngộ nhận cần tránh

**“CQRS bắt buộc hai DB.”** Không. Tách command/query handlers trong cùng database vẫn là một dạng CQRS.

**“CQRS đồng nghĩa event sourcing.”** Không. Write side có thể lưu current state, dùng outbox event để đồng bộ projection.

**“Dùng CQRS là luôn nhanh hơn.”** Không. Projection, broker và data duplication có overhead; với CRUD nhỏ có thể chậm và phức tạp hơn.

**“Read store luôn đồng bộ ngay.”** Không nếu dùng async projection. Phải thiết kế UX, freshness SLO và reconciliation.

**“Read model có thể ghi để cập nhật nhanh.”** Không nếu nó là projection của nguồn chuẩn khác. Command phải đi về owner.

**“Kafka bảo đảm exactly-once cho mọi nghiệp vụ.”** Không. Cần idempotency và phạm vi transaction phù hợp.

**“Chỉ cần event lên broker là không mất.”** Dual write sau DB commit có thể mất event; outbox hoặc giải pháp đồng bộ đáng tin cậy là cần thiết.

**“Event nào đến cũng được ghi đè view.”** Không. Event sai thứ tự có thể làm state quay lùi.

**“Có read projection thì không cần API của owner.”** Không. Quyết định nghiệp vụ và các query cần authoritative data vẫn có thể phải gọi owner.

**“Projection chỉ có dữ liệu đọc nên không cần authorization.”** Sai. Đây là bản sao dữ liệu có thể nhạy cảm và đa tenant.

## 25. Bài tập và gợi ý lời giải

### Bài 1 — Ứng dụng CRUD nhỏ

Một hệ thống quản trị có 5 bảng và 20 người dùng, query đơn giản. Có nên đưa Kafka + MongoDB vào để tách read/write?

**Gợi ý:** Chưa có bằng chứng. Dùng cùng database, query DTO/index và tách handler khi thật sự cần; không thêm hạ tầng chỉ để theo pattern.

### Bài 2 — Remote N+1 trong lịch sử đơn

Một trang 100 đơn gọi Catalog, Payment, Shipping cho từng đơn, gây 300 RPC. Phương án nào?

**Gợi ý:** Batch API hoặc BFF composition trước; nếu query lặp nhiều và cho phép stale ngắn, thiết kế OrderView projection từ sự kiện của các owner.

### Bài 3 — POST xong GET không thấy đơn

Command đã commit nhưng read view trễ 2 giây, khách bấm đặt lại.

**Gợi ý:** Trả orderId/trạng thái trong POST, dùng read-after-write path hoặc UX PENDING, và idempotency cho PlaceOrder.

### Bài 4 — Event mất sau DB commit

Order state đã thay đổi nhưng read store không cập nhật do broker unavailable.

**Gợi ý:** Transactional outbox, publisher retry, monitor backlog và consumer idempotent.

### Bài 5 — Analytics cộng doanh thu gấp hai

Một PaymentCaptured event được nhận hai lần. Vì sao và khắc phục?

**Gợi ý:** At-least-once delivery/retry có thể tạo duplicate. Unique processed event IDs trong transaction read store, business reconciliation và replay an toàn.

### Bài 6 — Event version 10 đến trước version 9

Projection sau cùng hiển thị trạng thái cũ. Xử lý?

**Gợi ý:** Source version, ordering key, gap handling và không ghi đè dữ liệu mới bằng event cũ.

### Bài 7 — Admin sửa trực tiếp read table

Một nhân viên cập nhật OrderView.paymentStatus thành CAPTURED và nghĩ đã thu tiền.

**Gợi ý:** Sai ownership. CapturePayment là command tới Payment, Payment xác nhận/commit rồi phát event để read view cập nhật.

### Bài 8 — CQRS và Event Sourcing

Write side lưu orders table trong PostgreSQL rồi phát OrderConfirmed qua outbox sang read store. Đây có phải event sourcing?

**Gợi ý:** Không; nguồn sự thật vẫn là current state trong orders table. Đó là CQRS có event-driven projection.

### Bài 9 — Không đủ retention để rebuild

Broker giữ 7 ngày event, dashboard cần dữ liệu 3 năm. Có thể xóa read DB rồi replay topic để phục hồi đầy đủ không?

**Gợi ý:** Không. Cần historical event store, snapshot hoặc export có kiểm soát từ owner và catch-up.

### Bài 10 — Sai quyền đa tenant

Read projection chứa đơn của nhiều merchant, GET chỉ lọc status mà quên tenantId. Hậu quả?

**Gợi ý:** Lộ dữ liệu cross-tenant. Read-side phải enforce identity/tenant scope và có security tests, audit, retention.

### Bài 11 — Read store lag lâu

Dashboard hiển thị doanh thu cũ dù HTTP status 200 và consumer backlog đang tăng. Có nên im lặng?

**Gợi ý:** Không. Hiển thị thời gian dữ liệu gần nhất, lag warning khi vượt ngưỡng và vận hành xử lý backlog/đối soát.

### Bài 12 — Quyết định giữ hàng từ projection

Read view nói còn 5 sản phẩm; hai khách đồng thời đặt mỗi người 4. Có được xác nhận cả hai chỉ dựa trên read view?

**Gợi ý:** Không. Inventory write owner phải thực hiện reservation atomic và quyết định accepted/rejected, vì projection có thể stale.

## 26. Checklist đánh giá CQRS

### Domain và scope
- [ ] Read và write thật sự có access pattern hoặc mô hình khác nhau.
- [ ] Command đi tới owner bảo vệ bất biến.
- [ ] Query không làm side effect nghiệp vụ.
- [ ] Read view không trở thành nguồn ghi sai quyền.
- [ ] Đã so sánh với CRUD/query DTO/index và batching.

### Consistency và data
- [ ] Đã quyết định dùng chung DB hay read store riêng theo bằng chứng.
- [ ] Nếu async có stale window và read-your-writes strategy.
- [ ] Có outbox hoặc cơ chế không mất event sau commit.
- [ ] Projector idempotent và có xử lý out-of-order/version.
- [ ] Event schema/versioning được quản trị.
- [ ] Có backfill, replay, retention và rebuild plan.
- [ ] Có reconciliation với source of truth.

### API và vận hành
- [ ] Contract command response phân biệt accepted/confirmed.
- [ ] Query DTO/index/pagination phù hợp màn hình.
- [ ] Có projection lag, DLQ, error, outbox backlog metrics.
- [ ] Có query p95/p99 và write SLO.
- [ ] Có incident/runbook và đường rollback đọc an toàn.
- [ ] Có auth/tenant/PII controls ở mọi bản sao read.
- [ ] Đã đo lợi ích so với chi phí broker/store/nhân sự vận hành.

## 27. Ghi nhớ

1. **CQRS tách trách nhiệm command và query, không bắt buộc tách database hoặc microservice.**
2. **Write model ưu tiên bất biến và tính đúng đắn; read model ưu tiên hình dạng query và hiệu năng đọc.**
3. **Read projection là dữ liệu phái sinh**, không thể thay nguồn sự thật của các bounded context.
4. **Chỉ áp dụng event-driven read store khi nhu cầu đọc thật sự khác**, ví dụ danh sách tổng hợp lớn, fan-out cao hoặc scale đọc độc lập.
5. **Eventual consistency phải được thiết kế và diễn đạt rõ**, đặc biệt đọc ngay sau ghi, trạng thái thanh toán và tồn kho.
6. **Outbox, dedup, versioning và reconciliation** quan trọng hơn việc đơn giản đưa event vào broker.
7. **CQRS khác event sourcing** và có thể tồn tại trong modular monolith.
8. **Đừng bỏ qua bảo mật của read models:** quyền theo tenant, dữ liệu cá nhân, retention và deletion vẫn áp dụng.
9. **Đo kết quả với latency, throughput, lag, sai lệch dữ liệu và chi phí**, không chỉ bằng số lượng service hoặc database.
10. **Kiến trúc vừa đủ là kiến trúc tốt:** query DTO/index hoặc batch API có thể giải quyết bài toán mà không cần thêm broker và projection riêng.