# Tách trách nhiệm đọc–ghi mà chưa cần tách cơ sở dữ liệu

Trong nhiều ứng dụng, cùng một mô hình đối tượng được dùng cho cả thao tác thay đổi dữ liệu và truy vấn dữ liệu. Cách làm này đơn giản khi nghiệp vụ còn nhỏ. Nhưng khi quy tắc ghi ngày càng phức tạp trong khi màn hình đọc cần dữ liệu tổng hợp, lọc, sắp xếp hoặc báo cáo theo nhiều cách, một mô hình duy nhất có thể trở nên khó tối ưu và khó hiểu.

**CQRS (Command Query Responsibility Segregation)** là cách tách trách nhiệm xử lý command và query. Command thể hiện ý định làm thay đổi trạng thái; query yêu cầu thông tin và không làm thay đổi trạng thái nghiệp vụ. Hai phía có thể dùng những mô hình, lớp và cách truy cập dữ liệu khác nhau để phục vụ đúng mục đích.

CQRS không bắt buộc phải tách thành hai cơ sở dữ liệu. Nhóm có thể bắt đầu bằng hai đường xử lý riêng trong cùng ứng dụng, dùng chung một relational database và thậm chí cùng schema. Phần ghi tiếp tục bảo vệ invariant qua aggregate và transaction; phần đọc có thể dùng DTO projection, query service, SQL tối ưu hoặc read model riêng trong cùng database. Việc tách database, đồng bộ bất đồng bộ và Event Sourcing là các lựa chọn kiến trúc nâng cao, không phải điều kiện để áp dụng CQRS.

## 1. Vì sao tách trách nhiệm đọc và ghi?

Một use case ghi thường cần bảo vệ quy tắc nghiệp vụ. Ví dụ, xác nhận đơn hàng phải kiểm tra trạng thái, dòng hàng, giá đã chốt và điều kiện xác nhận. Thao tác này nên đi qua aggregate root để bảo vệ invariant.

Trong khi đó, một màn hình danh sách đơn hàng có thể cần:

- Mã đơn, tên khách hàng và trạng thái.
- Tổng tiền và loại tiền.
- Thời điểm đặt, xác nhận và giao hàng.
- Tên nhân viên phụ trách.
- Bộ lọc theo khoảng ngày, trạng thái, khu vực và phân khúc.
- Sắp xếp theo tổng tiền hoặc thời gian cập nhật.

Nếu mọi query đều tải đầy đủ aggregate `Order`, `Customer`, `Shipment` rồi ghép dữ liệu trong bộ nhớ, hệ thống có thể tạo nhiều truy vấn, tải quá nhiều object và khó tối ưu cho từng màn hình. Ngược lại, nếu dùng một mô hình đọc đơn giản để ghi, các quy tắc nghiệp vụ có thể bị bỏ qua.

CQRS tách hai mục tiêu:

- **Write side (phía ghi):** thực hiện hành vi nghiệp vụ, kiểm tra invariant và thay đổi trạng thái.
- **Read side (phía đọc):** truy xuất và trình bày dữ liệu theo nhu cầu tiêu thụ.

Hai phía vẫn làm việc trên cùng một miền nghiệp vụ và có thể dùng chung database. Sự tách biệt trước hết là về trách nhiệm và mô hình xử lý.

## 2. Command và Query khác nhau thế nào?

**Command** là yêu cầu hệ thống thực hiện một hành động có thể làm thay đổi trạng thái. Tên command thường diễn đạt ý định, chẳng hạn `PlaceOrder`, `ConfirmOrder`, `CancelOrder` hoặc `ChangeDeliveryAddress`.

**Query** là yêu cầu đọc thông tin, chẳng hạn `GetOrderDetails`, `SearchOrders` hoặc `GetCustomerOrderHistory`. Query không được thực hiện thay đổi trạng thái nghiệp vụ như một tác dụng phụ của việc đọc.

| Tiêu chí | Command | Query |
| --- | --- | --- |
| Mục đích | Yêu cầu một hành động | Lấy thông tin |
| Tác động trạng thái | Có thể thay đổi trạng thái | Không thay đổi trạng thái nghiệp vụ |
| Cách mô hình hóa | Theo ý định và quy tắc nghiệp vụ | Theo dữ liệu consumer cần xem |
| Thành phần chính | Command handler, aggregate, domain service, repository | Query handler, query service, projection/read model |
| Kết quả | Xác nhận, ID, kết quả nghiệp vụ hoặc lỗi | DTO/read model phù hợp với truy vấn |
| Ví dụ | `ConfirmOrder(orderId)` | `GetOrderSummary(orderId)` |

### 2.1. Command không phải CRUD tổng quát

Một command nên diễn đạt hành động nghiệp vụ thay vì chỉ nói “cập nhật bản ghi”. Ví dụ, `ConfirmOrder` rõ ý định hơn `UpdateOrderStatus`. Command handler tải aggregate, gọi hành vi và lưu kết quả.

Không phải mọi command đều thành công. Đơn có thể không ở trạng thái cho phép xác nhận; số lượng tồn có thể không đủ; người dùng có thể không có quyền. Kết quả phải phản ánh rõ việc command đã được chấp nhận hay bị từ chối.

### 2.2. Query không nên gây tác dụng phụ nghiệp vụ

Một query có thể ghi log kỹ thuật, cập nhật metrics hoặc sử dụng cache nội bộ, nhưng không nên thay đổi trạng thái miền như tự xác nhận đơn, đánh dấu đã thanh toán hoặc giảm tồn kho. Nếu một thao tác vừa đọc vừa thay đổi trạng thái, hãy mô hình hóa phần thay đổi thành command riêng.

### 2.3. HTTP method không tự tạo ra CQRS

REST thường dùng `GET` cho query và `POST`, `PUT`, `PATCH`, `DELETE` cho các thao tác thay đổi. Đây là quy ước giao thức. CQRS là cách tổ chức trách nhiệm trong ứng dụng. Một API dùng `GET` và `POST` chưa chắc đã có hai mô hình đọc/ghi được tách rõ.

## 3. CQRS là tách mô hình, không phải bắt buộc tách database

Điểm quan trọng nhất của bài học này là: CQRS có thể được triển khai trong một ứng dụng và một database.

Ví dụ, một ứng dụng Spring Boot có thể có:

- `ConfirmOrderCommandHandler` xử lý xác nhận đơn.
- `OrderRepository` tải và lưu aggregate.
- `GetOrderDetailsQueryHandler` truy vấn thông tin đơn.
- `OrderReadRepository` dùng projection hoặc SQL để lấy DTO.
- Một database PostgreSQL duy nhất lưu các bảng ghi và cung cấp dữ liệu cho query.

```text
                    Application
                         |
              +----------+----------+
              |                     |
              v                     v
         COMMAND SIDE           QUERY SIDE
              |                     |
      Command Handler         Query Handler
              |                     |
       Aggregate Root          Read Model / DTO
              |                     |
      Write Repository        Query Repository
              |                     |
              +----------+----------+
                         |
                         v
                 One Database
             (same database/schema)
```

Sơ đồ cho thấy hai đường xử lý khác nhau nhưng vẫn có thể dùng cùng database. Write side không cần query side là một dịch vụ riêng; query side cũng không cần một database riêng.

### 3.1. Các mức độ tách biệt

Nhóm có thể áp dụng CQRS theo nhiều mức:

| Mức | Cách tổ chức | Database |
| --- | --- | --- |
| 1. Tách trách nhiệm | Command handler và query handler riêng | Dùng chung |
| 2. Tách mô hình ứng dụng | Write model và read DTO/projection riêng | Dùng chung |
| 3. Tách schema hoặc cấu trúc đọc | Bảng read model, view hoặc materialized view riêng | Cùng một database server/instance |
| 4. Tách kho dữ liệu | Write database và read database riêng, đồng bộ projection | Khác database hoặc storage |

Có thể dừng ở mức 1 hoặc 2 nếu đã giải quyết được vấn đề. Không cần tiến lên mức cao hơn chỉ vì muốn “làm CQRS đầy đủ”.

### 3.2. Cùng database không có nghĩa phải dùng cùng mô hình

Hai phía có thể đọc/ghi các bảng khác nhau hoặc cùng một bảng theo quy tắc riêng. Ví dụ write side thao tác aggregate qua ORM, trong khi query side dùng SQL projection để lấy một DTO. Cùng một database không bắt buộc hai phía phải dùng cùng entity class hoặc repository abstraction.

## 4. Write model: bảo vệ quy tắc nghiệp vụ

Write model là mô hình phục vụ thay đổi trạng thái. Trong DDD, nó thường gồm aggregate, entity, value object, domain service và repository.

Một command handler điển hình:

1. Nhận command và kiểm tra dữ liệu cấu trúc.
2. Xác thực actor và quyền thực hiện use case.
3. Tải aggregate qua repository.
4. Gọi hành vi trên aggregate hoặc domain service.
5. Lưu aggregate trong transaction.
6. Ghi nhận domain event hoặc outbox nếu cần.
7. Trả kết quả command.

Ví dụ, `ConfirmOrder` không nên cập nhật trực tiếp cột `status` bằng query tổng quát nếu việc xác nhận có nhiều invariant. Nó nên gọi `order.confirm()` để aggregate kiểm tra trạng thái và các điều kiện liên quan.

### 4.1. Command thể hiện ý định

```java
public record ConfirmOrderCommand(
        OrderId orderId,
        ActorId actorId
) {}
```

Command không cần chứa mọi trường của `Order`. Nó mang đủ dữ liệu để xác định hành động và chủ thể yêu cầu. Các dữ liệu khác được tải hoặc kiểm tra qua use case phù hợp.

### 4.2. Command handler điều phối write model

```java
@Service
public class ConfirmOrderCommandHandler {
    private final OrderRepository orders;

    public ConfirmOrderCommandHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderId handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        order.confirm(command.actorId());
        orders.save(order);

        return order.id();
    }
}
```

Đây là ví dụ minh họa. Trong một ứng dụng JPA, nếu aggregate đã được quản lý trong persistence context, việc gọi `save` có thể không cần thiết tùy repository implementation. Transaction cần bao trùm việc tải, thực hiện hành vi và lưu thay đổi.

### 4.3. Invariant vẫn nằm trong domain model

CQRS không có nghĩa chuyển toàn bộ validation sang command handler. Command handler điều phối; aggregate hoặc domain service bảo vệ quy tắc miền. Một command có thể được gọi từ HTTP, message consumer, batch job hoặc CLI nhưng invariant vẫn phải được giữ.

## 5. Read model: phục vụ truy vấn và trình bày

Read model là hình dạng dữ liệu tối ưu cho một hoặc nhiều query. Nó có thể là DTO projection, database view, materialized view, bảng tổng hợp hoặc document được tạo từ dữ liệu ghi.

Read model không cần có cùng cấu trúc với aggregate. Một màn hình danh sách đơn hàng có thể cần một hàng dữ liệu đã kết hợp tên khách, tổng tiền, trạng thái thanh toán và trạng thái giao hàng. Query side có thể lấy dữ liệu bằng một câu SQL join hoặc projection mà không tải cả object graph.

Ví dụ DTO:

```java
public record OrderSummaryView(
        UUID orderId,
        String customerName,
        String orderStatus,
        BigDecimal totalAmount,
        String currency,
        Instant placedAt
) {}
```

DTO này phục vụ màn hình danh sách. Nó không phải aggregate và không nên được dùng để thay đổi trạng thái đơn hàng.

### 5.1. Query handler có thể dùng SQL trực tiếp

```java
@Repository
public class OrderReadRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderSummaryView> findSummary(UUID orderId) {
        String sql = """
                SELECT o.id AS order_id,
                       c.display_name AS customer_name,
                       o.status AS order_status,
                       o.total_amount AS total_amount,
                       o.currency AS currency,
                       o.placed_at AS placed_at
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.id = :orderId
                """;

        var rows = jdbc.query(sql, Map.of("orderId", orderId), (rs, rowNum) ->
                new OrderSummaryView(
                        rs.getObject("order_id", UUID.class),
                        rs.getString("customer_name"),
                        rs.getString("order_status"),
                        rs.getBigDecimal("total_amount"),
                        rs.getString("currency"),
                        rs.getTimestamp("placed_at").toInstant()
                ));

        return rows.stream().findFirst();
    }
}
```

Đoạn SQL chỉ minh họa projection đọc. Tên bảng/cột và kiểu dữ liệu cần khớp schema thật. Query side có thể dùng JDBC, JPA projection, jOOQ hoặc công cụ truy vấn khác; CQRS không bắt buộc một thư viện cụ thể.

### 5.2. Query handler không cần tải aggregate

```java
public record GetOrderSummaryQuery(UUID orderId) {}

@Service
public class GetOrderSummaryQueryHandler {
    private final OrderReadRepository readRepository;

    public GetOrderSummaryQueryHandler(OrderReadRepository readRepository) {
        this.readRepository = readRepository;
    }

    @Transactional(readOnly = true)
    public OrderSummaryView handle(GetOrderSummaryQuery query) {
        return readRepository.findSummary(query.orderId())
                .orElseThrow(() -> new OrderNotFoundException(
                        new OrderId(query.orderId())));
    }
}
```

Query handler trả về dữ liệu phù hợp với yêu cầu đọc. Nó không gọi `order.confirm()` hoặc cập nhật aggregate. Annotation `readOnly = true` có thể giúp framework/database tối ưu hoặc ngăn một số thao tác ghi, nhưng bản thân annotation không thay thế nguyên tắc thiết kế query không làm thay đổi trạng thái nghiệp vụ.

## 6. Dùng chung database nhưng tách đường đọc/ghi

Một triển khai thực tế có thể giữ một schema quan hệ duy nhất:

```text
                  Application Layer
                         |
              +----------+----------+
              |                     |
              v                     v
          Write Side             Read Side
              |                     |
      Order Aggregate          OrderSummaryView
              |                     |
      JPA Repository           JDBC / Projection
              |                     |
              +----------+----------+
                         |
                         v
                 PostgreSQL Database
       +--------------------------------------+
       | orders                               |
       | order_lines                          |
       | customers                            |
       | payments                             |
       | shipments                            |
       | (optional) order_summary_projection  |
       +--------------------------------------+
```

Trong ví dụ, write side dùng JPA để tải và lưu aggregate. Query side dùng JDBC để đọc dữ liệu đã join. Cả hai dùng cùng database và có thể đọc cùng các bảng nền. Nếu cần, query side có thể dùng thêm view hoặc bảng projection riêng.

### 6.1. Lợi ích của cách bắt đầu này

- Không cần vận hành thêm database hoặc message broker.
- Không phát sinh đồng bộ dữ liệu giữa hai storage độc lập.
- Có thể dùng transaction database hiện tại.
- Cho phép tối ưu query mà không làm write model phức tạp.
- Có thể chuyển từng query nặng sang projection riêng khi cần.
- Dễ thử nghiệm CQRS trên một use case cụ thể.

### 6.2. Giới hạn cần hiểu

- Query nặng vẫn có thể tranh chấp tài nguyên với transaction ghi.
- Cùng database có nghĩa là write và read dùng chung giới hạn CPU, I/O, connection và lock.
- Nếu query side cần schema riêng hoặc workload rất khác, việc dùng chung database có thể không đủ.
- Nếu read model được cập nhật bất đồng bộ, có thể xuất hiện độ trễ dù hai phía ở cùng ứng dụng.

CQRS giải quyết sự tách biệt trách nhiệm và mô hình; nó không tự động giải quyết mọi vấn đề về hiệu năng hoặc cách ly tải.

## 7. Các cách triển khai read model trong cùng database

Không phải mọi ứng dụng CQRS đều cần một bảng projection riêng. Có nhiều mức lựa chọn.

### 7.1. DTO projection từ bảng hiện có

Query dùng `SELECT` chỉ lấy những trường cần thiết, có thể join nhiều bảng và trả DTO. Đây là cách đơn giản, không cần đồng bộ projection riêng.

Phù hợp khi query có thể được tối ưu bằng index, join và projection thông thường.

### 7.2. Database view

View đóng gói một truy vấn thường dùng. Query side có thể đọc view thay vì lặp lại join ở nhiều repository.

View thông thường không nhất thiết lưu dữ liệu kết quả riêng; database thực hiện query khi view được truy cập. Cần kiểm tra hiệu năng và khả năng tối ưu của database.

### 7.3. Materialized view

Materialized view lưu kết quả truy vấn đã tính trước. Nó có thể tăng tốc đọc nhưng cần cơ chế refresh. Tùy database, refresh có thể tốn tài nguyên hoặc khiến dữ liệu cũ trong một khoảng thời gian.

### 7.4. Bảng read projection

Một bảng như `order_summary_projection` lưu dữ liệu đã tổng hợp theo nhu cầu đọc. Nó có thể được cập nhật đồng bộ trong cùng transaction hoặc bất đồng bộ qua event.

Nếu cập nhật đồng bộ trong cùng database transaction, read model có thể nhất quán ngay sau commit nhưng command phải làm thêm công việc ghi projection. Nếu cập nhật bất đồng bộ, write side nhẹ hơn nhưng query có thể đọc dữ liệu trễ.

### 7.5. Không tạo read table chỉ để đổi tên DTO

Nếu một projection có thể lấy dễ dàng từ các bảng hiện tại với hiệu năng tốt, một bảng riêng có thể chỉ làm tăng chi phí đồng bộ và migration. Hãy đo query thực tế trước khi thêm read model lưu trữ.

## 8. Cập nhật read model khi vẫn dùng một database

Nếu read side dùng bảng projection riêng, cần chọn cách cập nhật projection. Có hai cách phổ biến.

### 8.1. Cập nhật đồng bộ trong cùng transaction

Sau khi aggregate thay đổi, application layer hoặc một thành phần nội bộ cập nhật projection trong cùng transaction database. Nếu transaction rollback, cả thay đổi write model và projection đều rollback.

Ưu điểm:

- Query có thể thấy dữ liệu mới ngay sau commit.
- Không cần broker để đồng bộ projection.
- Không có khoảng trễ do consumer xử lý event.

Giới hạn:

- Transaction ghi có thêm thao tác cập nhật projection.
- Write path phụ thuộc vào cấu trúc read model.
- Nếu một command phải cập nhật nhiều projection lớn, thời gian transaction tăng.
- Cần tránh đưa logic query/reporting vào domain aggregate.

### 8.2. Cập nhật bất đồng bộ bằng event

Write side ghi aggregate và domain event/outbox. Một handler đọc event và cập nhật bảng projection sau đó.

Ưu điểm:

- Write path ít phụ thuộc vào từng projection.
- Có thể xây dựng nhiều read model độc lập.
- Có thể xử lý lại event để tái tạo projection nếu thiết kế hỗ trợ.

Giới hạn:

- Read model có độ trễ.
- Cần xử lý duplicate, retry, thứ tự và lỗi projection.
- Cần quan sát lag và có quy trình rebuild.

Việc dùng event để cập nhật projection không bắt buộc phải dùng Event Sourcing. Event có thể được phát ra từ ứng dụng CRUD thông thường sau khi transaction commit hoặc qua Transactional Outbox.

## 9. Consistency khi đọc sau khi ghi

Nếu write side và read side cùng truy cập bảng nguồn trong một database, query có thể đọc trạng thái mới sau khi transaction ghi đã commit, tùy isolation và cách kết nối. Nhưng nếu query đọc một projection được cập nhật bất đồng bộ, có thể xảy ra **eventual consistency**.

Ví dụ, khách vừa xác nhận đơn thành công nhưng màn hình danh sách đọc từ projection chưa được cập nhật. Trong vài trăm mili giây hoặc vài giây, danh sách có thể vẫn hiển thị trạng thái cũ.

Nhóm cần quyết định theo use case:

- Màn hình xác nhận kết quả command có cần trả trạng thái mới ngay không?
- Query có thể chấp nhận dữ liệu trễ không?
- Có thể đọc trực tiếp từ write database sau command để hiển thị kết quả tức thời không?
- Có cần gửi `commandId`/`version` để client đợi projection đạt tới phiên bản mong muốn không?
- Khi projection chậm, UI sẽ hiển thị trạng thái chờ hay tải lại?

### 9.1. Read-your-writes

Read-your-writes là kỳ vọng người dùng có thể đọc lại thay đổi mình vừa thực hiện. Nếu read model bất đồng bộ, hệ thống có thể hỗ trợ bằng một số cách:

- Trả kết quả cần thiết trực tiếp từ command response.
- Sau command, query tạm thời từ write model hoặc nguồn nhất quán.
- Trả version/sequence và cho client chờ projection đạt đến version đó.
- Hiển thị trạng thái “đang cập nhật” cho đến khi projection sẵn sàng.

Không nên giả định projection đã cập nhật ngay chỉ vì command đã trả HTTP 200.

### 9.2. Không dùng eventual consistency khi nghiệp vụ cần quyết định tức thời

Một query phục vụ báo cáo có thể chấp nhận trễ. Nhưng kiểm tra hạn mức trước khi giải ngân hoặc xác nhận tồn kho cuối cùng có thể cần đọc dữ liệu nhất quán hơn. Query model không nên trở thành nguồn quyết định cho invariant quan trọng nếu dữ liệu của nó có thể trễ mà nghiệp vụ không chấp nhận.

## 10. CQRS không đồng nghĩa với Event Sourcing

Hai khái niệm thường được nhắc cùng nhau nhưng giải quyết các vấn đề khác nhau.

**CQRS** tách trách nhiệm mô hình đọc và ghi. Write side có thể lưu trạng thái hiện tại bằng cách cập nhật hàng trong database như ứng dụng thông thường.

**Event Sourcing** lưu chuỗi event như nguồn dữ liệu chính để tái dựng trạng thái aggregate. Thay vì chỉ ghi trạng thái cuối, hệ thống lưu các fact như `OrderPlaced`, `OrderLineAdded`, `OrderConfirmed`.

| Tiêu chí | CQRS | Event Sourcing |
| --- | --- | --- |
| Vấn đề giải quyết | Tách mô hình/luồng đọc và ghi | Lưu lịch sử thay đổi dưới dạng event làm nguồn dữ liệu |
| Write storage | Có thể cập nhật bảng trạng thái hiện tại | Ghi event vào event store |
| Read model | Có thể là DTO/query trực tiếp hoặc projection | Thường dựng từ event stream hoặc projection |
| Có bắt buộc đi cùng nhau? | Không | Không |
| Có thể dùng cùng database? | Có | Event store có thể nằm trong database hiện có hoặc storage riêng |

Có thể áp dụng CQRS mà không Event Sourcing: command cập nhật bảng `orders`, query dùng SQL projection. Cũng có thể dùng Event Sourcing và CQRS cùng nhau: command tạo event, projection xây read model. Không nên triển khai Event Sourcing chỉ vì đã tách command và query.

## 11. CQRS và kiến trúc nhiều bounded context

CQRS có thể giúp một bounded context tổ chức riêng các use case đọc và ghi. Nó không tự động tạo ra bounded context mới và cũng không thay thế Context Map.

Ví dụ, context Sales sở hữu aggregate `Order`. Query màn hình đơn hàng có thể lấy dữ liệu từ read model Sales. Context Shipping chỉ cần thông tin vận chuyển được công bố qua integration contract; nó không nên truy vấn trực tiếp các bảng nội bộ của Sales chỉ vì hai context đang dùng chung database server.

Ranh giới sở hữu dữ liệu vẫn cần được tôn trọng. Việc dùng chung hạ tầng database không có nghĩa các context được quyền đọc/ghi tùy ý bảng của nhau.

### 11.1. Read model liên context

Một dashboard tổng hợp có thể cần dữ liệu từ Sales, Billing và Shipping. Có thể tạo projection dành cho báo cáo, được cập nhật từ các integration event hoặc query API của từng context. Projection đó phục vụ đọc và không trở thành nguồn sự thật cho các aggregate gốc.

### 11.2. ACL và mapping

Khi một context tiêu thụ dữ liệu từ context khác, cần chuyển đổi hợp đồng ngoài thành mô hình phù hợp với context tiêu thụ. Không dùng chung domain entity hoặc repository nội bộ giữa các context chỉ để giảm mapping.

## 12. CQRS trong API và application layer

Một API có thể tách route đọc và ghi theo use case:

```text
GET    /orders/{id}          -> GetOrderDetailsQuery
GET    /orders               -> SearchOrdersQuery
POST   /orders               -> PlaceOrderCommand
POST   /orders/{id}/confirm  -> ConfirmOrderCommand
POST   /orders/{id}/cancel   -> CancelOrderCommand
```

Controller chỉ chuyển request thành command/query và chuyển kết quả thành response DTO. Quy tắc nghiệp vụ không nên nằm trong controller.

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final ConfirmOrderCommandHandler confirmHandler;
    private final GetOrderSummaryQueryHandler summaryHandler;

    public OrderController(
            ConfirmOrderCommandHandler confirmHandler,
            GetOrderSummaryQueryHandler summaryHandler
    ) {
        this.confirmHandler = confirmHandler;
        this.summaryHandler = summaryHandler;
    }

    @PostMapping("/{id}/confirm")
    public ResponseEntity<Void> confirm(@PathVariable UUID id) {
        confirmHandler.handle(new ConfirmOrderCommand(
                new OrderId(id), currentActorId()));
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{id}/summary")
    public OrderSummaryView summary(@PathVariable UUID id) {
        return summaryHandler.handle(new GetOrderSummaryQuery(id));
    }
}
```

Đoạn mã chỉ minh họa phân chia luồng. Cơ chế lấy actor, xác thực, authorization, error mapping và response contract cần được triển khai theo ứng dụng thực tế.

## 13. Tối ưu hiệu năng đọc mà không làm phức tạp write side

Một lợi ích thực tế của CQRS là query model có thể được thiết kế theo cách đọc thay vì cấu trúc aggregate.

Ví dụ, báo cáo doanh thu theo tháng có thể cần dữ liệu đã nhóm theo thời gian và khu vực. Thay vì tải hàng nghìn `Order` rồi tính trong Java, query có thể dùng SQL aggregation hoặc bảng summary.

Các kỹ thuật có thể dùng:

- Chọn đúng cột thay vì `SELECT *`.
- Dùng projection DTO thay vì tải entity graph.
- Tạo index theo bộ lọc và thứ tự truy vấn thường dùng.
- Dùng database view cho query lặp lại.
- Dùng materialized view hoặc summary table khi phép tính đắt.
- Phân trang và giới hạn kết quả.
- Cache kết quả đọc nếu semantics cho phép.

CQRS không thay thế việc đo query plan và tối ưu database. Query side cần được tối ưu dựa trên workload thực tế.

### 13.1. Read model có thể phi chuẩn hóa

Read model có thể lặp một số dữ liệu như tên khách hàng hoặc tổng tiền để giảm join. Điều đó có thể chấp nhận vì read model phục vụ truy vấn. Nhưng cần có cơ chế cập nhật khi dữ liệu nguồn thay đổi và phải xác định giá trị nào là snapshot lịch sử.

### 13.2. Không tối ưu sớm

Nếu query trực tiếp từ bảng hiện tại đã đủ nhanh, không cần tạo projection riêng. Bắt đầu với command/query handler tách biệt và DTO projection; chỉ thêm read store khi metrics cho thấy nhu cầu.

## 14. Bảo mật và quyền trên hai phía

Tách read/write không làm mất yêu cầu authorization. Một actor có thể được phép xem thông tin nhưng không được phép sửa; hoặc được phép sửa một số trường nhưng không được xem dữ liệu nhạy cảm.

Nên kiểm tra quyền theo use case:

- Command side kiểm tra quyền thực hiện hành động và điều kiện của đối tượng.
- Query side kiểm tra quyền xem dữ liệu, phạm vi tenant và field-level access nếu cần.
- Response projection chỉ trả trường được phép công bố.
- Query không nên truy cập dữ liệu nhạy cảm chỉ vì join thuận tiện.
- Audit log ghi nhận những hành động ghi quan trọng theo chính sách.

Không nên giả định quyền đọc một đơn đồng nghĩa quyền xác nhận hoặc hủy đơn. Tương tự, command handler không nên trả toàn bộ aggregate chỉ vì actor được phép thực hiện một hành động.

## 15. Kiểm thử CQRS

Kiểm thử nên xác nhận hai phía thực hiện đúng trách nhiệm và dữ liệu được quan sát đúng theo consistency model.

### 15.1. Kiểm thử command side

- Command hợp lệ làm thay đổi aggregate đúng cách.
- Command không hợp lệ bị từ chối.
- Invariant vẫn được giữ.
- Transaction rollback khi lỗi xảy ra.
- Domain event/outbox được ghi đúng khi có thay đổi.
- Concurrency conflict được xử lý phù hợp.

### 15.2. Kiểm thử query side

- Query trả đúng DTO và chỉ các trường được công bố.
- Bộ lọc, sắp xếp và phân trang hoạt động đúng.
- Query không làm thay đổi trạng thái nghiệp vụ.
- Query xử lý đúng dữ liệu vắng mặt và quyền truy cập.
- Projection hoặc view được cập nhật theo cơ chế đã chọn.

### 15.3. Kiểm thử consistency

Nếu read model được cập nhật đồng bộ trong cùng transaction, xác nhận cả write model và projection commit/rollback cùng nhau.

Nếu read model được cập nhật bất đồng bộ, kiểm thử:

- Event được xử lý thành công.
- Duplicate event không tạo projection sai.
- Event đến sai thứ tự được xử lý theo chính sách.
- Projection lag được đo và cảnh báo.
- Có thể rebuild hoặc đối soát projection nếu cần.

### 15.4. Integration test trên database mục tiêu

Query plan, transaction isolation, locking và projection có thể khác giữa các database. Với các hành vi quan trọng, nên kiểm thử trên database thực tế hoặc môi trường tương đương thay vì chỉ dựa vào mock repository.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Cho rằng CQRS bắt buộc có hai database | Tăng chi phí vận hành và đồng bộ không cần thiết | Bắt đầu bằng hai luồng trong cùng database |
| Cho rằng CQRS đồng nghĩa Event Sourcing | Đưa event store và replay vào hệ thống khi chưa cần | Phân biệt tách model đọc/ghi với lưu lịch sử event làm nguồn dữ liệu |
| Dùng aggregate cho mọi query | Tải object graph lớn và khó tối ưu | Dùng DTO projection/query service |
| Dùng query để thay đổi trạng thái nghiệp vụ | Hành vi khó dự đoán và phá semantics query | Tách phần thay đổi thành command |
| Để command handler chứa toàn bộ domain rule | Application layer phình to, invariant bị phân tán | Đặt hành vi trong aggregate/domain service phù hợp |
| Tạo read model riêng cho mọi màn hình | Nhiều projection và chi phí đồng bộ | Dùng projection trực tiếp trước, đo rồi tối ưu |
| Dùng chung database nên bỏ qua ownership giữa context | Các context phụ thuộc schema nội bộ của nhau | Tôn trọng bounded context và contract dữ liệu |
| Cập nhật projection bất đồng bộ nhưng giả định dữ liệu tức thời | UI và quyết định nghiệp vụ có thể dùng dữ liệu cũ | Công bố consistency/lag và thiết kế read-your-writes |
| Không xử lý duplicate khi cập nhật projection | Tổng hợp hoặc số liệu bị nhân đôi | Dùng event ID, inbox và handler idempotent |
| Phi chuẩn hóa mà không có quy tắc đồng bộ | Read model bị stale hoặc sai | Xác định nguồn sự thật và cách cập nhật/rebuild |
| Chỉ kiểm thử handler bằng mock | Không phát hiện lỗi SQL, transaction hoặc isolation | Bổ sung integration test trên database mục tiêu |

## 17. Quy trình áp dụng CQRS từng bước

Nhóm có thể áp dụng CQRS một cách tăng dần thay vì tái cấu trúc toàn bộ ứng dụng.

### Bước 1: Chọn một use case có nhu cầu rõ

Tìm một nơi write model có nhiều invariant trong khi query cần hình dạng dữ liệu khác hoặc đang tải quá nhiều entity. Không bắt đầu bằng việc chuyển mọi endpoint.

### Bước 2: Xác định command và query

Liệt kê hành động thay đổi trạng thái và nhu cầu đọc. Đặt tên theo ý định nghiệp vụ và dữ liệu consumer cần.

### Bước 3: Giữ write path qua domain model

Command handler tải aggregate, gọi hành vi và lưu trong transaction. Đảm bảo invariant không bị chuyển ra controller hoặc SQL tùy tiện.

### Bước 4: Tạo query handler và DTO projection

Tách query khỏi aggregate. Dùng projection/SQL để lấy đúng dữ liệu cần thiết. Ban đầu có thể truy vấn trực tiếp các bảng hiện có.

### Bước 5: Dùng chung database

Giữ nguyên database và transaction hiện tại. Chưa cần tạo broker hoặc read database riêng nếu chưa có nhu cầu về tải, scale hoặc isolation.

### Bước 6: Đo và đánh giá query

Theo dõi thời gian phản hồi, số truy vấn, lock wait, CPU/I/O và connection pool. Xác định query nào thực sự cần view hoặc projection riêng.

### Bước 7: Chọn cơ chế cập nhật read model

Nếu cần bảng projection, quyết định cập nhật đồng bộ trong transaction hay bất đồng bộ qua event/outbox. Công bố rõ consistency và xử lý duplicate/lag nếu có.

### Bước 8: Kiểm thử command, query và consistency

Kiểm tra invariant, response DTO, quyền truy cập, transaction và hành vi sau khi ghi. Nếu có projection bất đồng bộ, kiểm thử retry và rebuild.

### Bước 9: Mở rộng có chọn lọc

Chỉ tách schema, database hoặc service khi workload và yêu cầu vận hành chứng minh lợi ích. Đừng tách chỉ để làm kiến trúc trông phức tạp hơn.

## 18. Nguyên tắc thực hành

Khi tách trách nhiệm đọc–ghi bằng CQRS mà chưa tách cơ sở dữ liệu, nhóm nên nhớ:

- **Command diễn đạt ý định thay đổi.** Gọi hành vi trên aggregate để bảo vệ invariant.
- **Query chỉ đọc.** Trả dữ liệu theo nhu cầu consumer và không tạo tác dụng phụ nghiệp vụ.
- **Tách trách nhiệm trước, tách hạ tầng sau.** Hai handler và hai mô hình có thể dùng chung một database.
- **Write model giữ ngôn ngữ miền.** Không biến aggregate thành DTO hoặc bảng dữ liệu thuần.
- **Read model tối ưu cho truy vấn.** Dùng projection, SQL, view hoặc summary khi có lý do.
- **Không tải aggregate cho mọi query.** Query side có thể dùng JDBC hoặc projection riêng.
- **Không cần Event Sourcing.** CQRS có thể hoạt động với persistence CRUD thông thường.
- **Chọn consistency có chủ đích.** Projection đồng bộ và bất đồng bộ có trade-off khác nhau.
- **Tôn trọng bounded context.** Cùng database không có nghĩa context được đọc/ghi bảng nội bộ của nhau tùy ý.
- **Giữ authorization ở cả hai phía.** Quyền đọc và quyền ghi là hai quyết định riêng.
- **Đo trước khi tách database.** CQRS không tự động cải thiện hiệu năng nếu query và write vẫn tranh chấp tài nguyên.
- **Áp dụng từng bước.** Bắt đầu ở use case có vấn đề rõ và chỉ mở rộng khi có bằng chứng.

CQRS giúp mô hình ghi tập trung vào hành vi và invariant, còn mô hình đọc tập trung vào dữ liệu mà consumer cần. Việc tách này có thể bắt đầu hoàn toàn trong một ứng dụng và một database: command handler làm việc với aggregate, query handler trả DTO projection, và hai phía dùng chung transaction/storage khi phù hợp. Khi có nhu cầu thực sự về workload, scale hoặc cách ly, nhóm mới cân nhắc read store riêng và cơ chế đồng bộ. Cách tiếp cận tăng dần giữ được lợi ích của CQRS mà không buộc hệ thống gánh thêm hạ tầng và consistency phức tạp quá sớm.

## 19. Câu hỏi tự kiểm tra

1. CQRS tách những trách nhiệm nào và vì sao nó hữu ích khi write model và read model có nhu cầu khác nhau?
2. Phân biệt command với query về ý định, tác động trạng thái và kết quả.
3. Vì sao một command như `ConfirmOrder` tốt hơn một thao tác `UpdateOrderStatus` tổng quát trong domain model?
4. Vì sao CQRS không bắt buộc phải có hai database hoặc hai service?
5. Write model trong DDD thường gồm những thành phần nào và aggregate root bảo vệ điều gì?
6. Read model có thể khác aggregate như thế nào? Hãy nêu một DTO projection cho màn hình danh sách đơn hàng.
7. So sánh DTO projection, database view, materialized view và bảng read projection.
8. Hai phía dùng chung database có những lợi ích và giới hạn nào?
9. Phân biệt cập nhật read model đồng bộ trong transaction với cập nhật bất đồng bộ qua event.
10. Read-your-writes là gì và có thể hỗ trợ nó như thế nào khi projection cập nhật trễ?
11. CQRS khác Event Sourcing như thế nào? Có thể dùng CQRS với CRUD persistence thông thường không?
12. Hãy chọn một use case trong hệ thống của bạn, xác định command, query, write model, read DTO và cách triển khai ban đầu trên cùng database.
