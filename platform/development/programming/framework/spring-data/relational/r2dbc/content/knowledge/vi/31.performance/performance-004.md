# Phân tích N+1, truy vấn đếm và phân trang offset sâu

Một endpoint danh sách có thể trông đơn giản: lấy các đơn hàng, hiển thị tên khách hàng, số dòng hàng, tổng tiền và cho phép chuyển trang. Nhưng nếu mỗi đơn hàng lại phát sinh thêm truy vấn để lấy khách hàng hoặc đếm dòng hàng, ứng dụng có thể rơi vào lỗi N+1. Nếu màn hình đồng thời chạy một câu `COUNT(*)` đắt đỏ và dùng `OFFSET` rất lớn, database phải làm nhiều công việc hơn số hàng thực sự trả về.

Spring Data R2DBC không tự loại bỏ các vấn đề này chỉ vì truy cập database theo kiểu reactive. `Flux.flatMap(...)` có thể phát nhiều truy vấn đồng thời, nhưng số round trip vẫn tăng theo số bản ghi. `Pageable` hoặc câu SQL có `OFFSET` giúp diễn đạt phân trang, nhưng không làm cho offset sâu trở nên rẻ. Muốn cải thiện hiệu năng, cần xem xét số câu SQL, cardinality của join, chi phí đếm, thứ tự phân trang, index và cách client di chuyển qua dữ liệu.

## 1. N+1 là gì?

N+1 xảy ra khi ứng dụng chạy một truy vấn để lấy danh sách N bản ghi, sau đó chạy thêm một truy vấn cho từng bản ghi để lấy dữ liệu liên quan.

Ví dụ: lấy 100 đơn hàng trong một truy vấn, rồi với mỗi đơn hàng gọi `customerRepository.findById(...)` để lấy tên khách hàng. Tổng số query có thể là:

\[
1 + N = 1 + 100 = 101 \text{ queries}
\]

N+1 thường xuất hiện khi code ánh xạ object graph theo từng phần tử, khi tính số lượng con cho từng parent hoặc khi gọi repository bên trong vòng lặp.

| Dữ liệu cần hiển thị | Cách dễ tạo N+1 |
|---|---|
| Tên khách hàng của từng đơn hàng | Mỗi order gọi `findById(customerId)` |
| Số dòng hàng của từng đơn | Mỗi order gọi `countByOrderId(orderId)` |
| Tên sản phẩm trong từng dòng hàng | Mỗi line gọi `findById(productId)` |
| Quyền hoặc trạng thái liên quan | Mỗi user gọi thêm repository để lấy metadata |
| Số lượng bình luận của từng bài viết | Mỗi bài viết chạy một câu `COUNT(*)` riêng |

N+1 không phụ thuộc API đồng bộ hay reactive. Một vòng lặp dùng JDBC có thể tạo N+1; một chuỗi `Flux.flatMap` dùng R2DBC cũng có thể tạo N+1.

## 2. Ví dụ N+1 trong reactive code

Giả sử có các repository:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
    Flux<Order> findByStatus(String status);
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public interface OrderLineRepository
        extends ReactiveCrudRepository<OrderLine, Long> {
    Flux<OrderLine> findByOrderId(Long orderId);
}
```

Một service dễ viết nhưng có thể tạo N+1:

```java
public Flux<OrderListItem> findOrderList(String status) {
    return orderRepository.findByStatus(status)
        .flatMap(order -> customerRepository.findById(order.customerId())
            .flatMap(customer -> orderLineRepository.findByOrderId(order.id())
                .count()
                .map(lineCount -> new OrderListItem(
                    order.id(),
                    order.orderNo(),
                    customer.displayName(),
                    lineCount
                ))));
}
```

Nếu danh sách có N đơn hàng, luồng này có thể thực hiện:

- 1 query lấy danh sách order.
- N query lấy customer.
- N query đếm order line.

Tổng cộng khoảng `1 + 2N` query. Với 100 đơn hàng, đó có thể là 201 round trip.

Reactive chỉ giúp mô tả I/O bất đồng bộ và điều phối tín hiệu. Nó không tự gộp các query độc lập thành một query. `flatMap` có thể chạy nhiều query song song, nhưng số query vẫn là O(N); thậm chí concurrency lớn có thể làm database chịu burst tải.

Đổi `flatMap` thành `concatMap` cũng không loại bỏ N+1. `concatMap` chỉ chạy tuần tự và giảm số thao tác đồng thời; nó vẫn gửi từng query riêng.

## 3. Vì sao N+1 gây chậm dù mỗi query rất nhanh?

Chi phí của một truy vấn không chỉ là thời gian database thực thi SQL. Một round trip còn có:

- Lấy connection hoặc chờ pool cấp connection.
- Mã hóa và gửi request qua network.
- Database parse/plan/execute SQL.
- Gửi kết quả về driver.
- Decode row và map sang object Java.
- Chuyển tín hiệu qua reactive pipeline.

Nếu mỗi query mất trung bình 3 ms nhưng có 200 query tuần tự, tổng thời gian chờ có thể lên hàng trăm mili giây, chưa tính overhead khác. Nếu chạy đồng thời, latency có thể giảm trong một số trường hợp nhưng database phải xử lý nhiều statement, giữ nhiều connection/slot và tạo áp lực lên pool.

N+1 cũng làm latency khó dự đoán: danh sách 10 hàng có thể nhanh, nhưng danh sách 1000 hàng phát sinh hàng nghìn query. Vì vậy, cần kiểm soát số query theo kích thước page thay vì chỉ đo một fixture nhỏ.

## 4. Nhận diện N+1 bằng query count và metrics

Các dấu hiệu thường gặp:

- Log cho thấy cùng một câu SQL được thực hiện nhiều lần với ID khác nhau.
- Số query tăng gần tuyến tính theo số hàng trong response.
- Endpoint có nhiều query ngắn nhưng tổng latency cao.
- Pool acquire hoặc số connection hoạt động tăng mạnh khi page size tăng.
- Truy vấn count hoặc lookup metadata lặp lại trong vòng lặp.

Để phát hiện, có thể:

1. Bật SQL logging có chọn lọc trong môi trường phát triển/test.
2. Thu thập query count, query duration và operation name bằng metrics hoặc instrumentation phù hợp với R2DBC.
3. Dùng R2DBC proxy/instrumentation nếu dự án cần quan sát từng statement.
4. So sánh query count khi page size thay đổi từ 10 lên 50 hoặc 100.
5. Viết integration test xác nhận một endpoint chỉ phát số query cố định hoặc số query theo số batch, không theo từng row.

Không bật log toàn bộ bind parameter nhạy cảm trong production. Log SQL và metrics cần có redaction, sampling và giới hạn cardinality.

## 5. Cách 1: dùng JOIN và projection để lấy dữ liệu cần hiển thị

Nếu màn hình chỉ cần một số trường từ order và customer, có thể dùng một câu JOIN và ánh xạ trực tiếp sang DTO. Không nhất thiết phải tải toàn bộ entity graph.

DTO:

```java
public record OrderListItem(
    Long orderId,
    String orderNo,
    String customerName,
    String status
) {}
```

Query qua `DatabaseClient`:

```java
public Flux<OrderListItem> findOrderList(String status, int limit, long offset) {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   o.order_no,
                   o.status,
                   c.display_name AS customer_name
            FROM purchase_order o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
            """)
        .bind("status", status)
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> new OrderListItem(
            row.get("order_id", Long.class),
            row.get("order_no", String.class),
            row.get("customer_name", String.class),
            row.get("status", String.class)
        ))
        .all();
}
```

Ví dụ SQL dùng cú pháp `LIMIT/OFFSET` phổ biến ở PostgreSQL/MySQL; hệ quản trị khác có thể cần cú pháp phân trang riêng. Điểm chính là một query trả các trường DTO cần thiết, tránh một query customer cho mỗi order.

Projection thường có lợi vì:

- Chỉ đọc cột cần dùng.
- Giảm số round trip.
- Không tạo object graph lớn không cần thiết.
- Hợp đồng API rõ ràng, ít phụ thuộc cấu trúc entity.

Không nên JOIN mọi bảng chỉ vì có thể. Mỗi JOIN làm thay đổi cardinality và có thể nhân bản hàng; cần chọn đúng quan hệ và kiểm tra execution plan.

## 6. Cách 2: batch fetch theo tập ID

Nếu muốn giữ Repository riêng cho từng aggregate hoặc không phù hợp để join, có thể lấy danh sách parent trước, gom các ID liên quan rồi tải dữ liệu con trong một truy vấn `IN`.

Ví dụ lấy order, sau đó gom customer ID duy nhất:

```java
public Mono<List<OrderListItem>> findOrderList(String status) {
    return orderRepository.findByStatus(status)
        .collectList()
        .flatMap(orders -> {
            if (orders.isEmpty()) {
                return Mono.just(List.of());
            }

            Set<Long> customerIds = orders.stream()
                .map(Order::customerId)
                .collect(Collectors.toSet());

            return customerRepository.findAllById(customerIds)
                .collectMap(Customer::id)
                .map(customers -> orders.stream()
                    .map(order -> {
                        Customer customer = customers.get(order.customerId());
                        return new OrderListItem(
                            order.id(),
                            order.orderNo(),
                            customer == null ? null : customer.displayName(),
                            order.status()
                        );
                    })
                    .toList());
        });
}
```

Ở đây query lấy customer theo tập ID thay vì từng customer. Với N orders, thường có hai query chính: một query orders và một query customers. Nếu cần thêm order lines, có thể gom order IDs rồi tải toàn bộ lines cho page bằng một query khác.

Batch fetch phù hợp khi:

- Quan hệ có thể tải độc lập theo tập ID.
- Không muốn viết một JOIN phức tạp.
- Cần tái sử dụng repository mapping.
- Số ID được giới hạn theo page/batch size.

Lưu ý: `collectList()` giữ toàn bộ danh sách trong bộ nhớ. Hãy giới hạn page size trước khi gom. Với danh sách rất lớn, xử lý theo từng batch thay vì gom toàn bộ kết quả.

## 7. Batch fetch một-nhiều để tránh query đếm từng parent

Giả sử màn hình cần số dòng hàng của từng order. Thay vì gọi `count()` cho mỗi order, có thể lấy số lượng cho toàn bộ tập order IDs:

```sql
SELECT order_id, COUNT(*) AS line_count
FROM order_line
WHERE order_id IN (:orderIds)
GROUP BY order_id;
```

Sau đó ánh xạ kết quả thành map `orderId -> lineCount` và ghép với danh sách orders. Những order không có dòng hàng cần nhận giá trị mặc định 0.

Với `R2dbcEntityTemplate`, có thể dùng Criteria `IN`:

```java
Query query = Query.query(Criteria.where("orderId").in(orderIds));

return template.select(query, OrderLine.class)
    .all();
```

Ví dụ minh họa API template; tên property trong Criteria phải khớp mapping metadata của entity và cần xác nhận với phiên bản Spring Data đang dùng. Với truy vấn tổng hợp, `DatabaseClient` thường rõ ràng hơn vì có thể viết `GROUP BY` trực tiếp.

Khi dùng `DatabaseClient` named parameter với collection, hãy xác nhận khả năng mở rộng danh sách bind của phiên bản Spring Framework/driver. Nếu cần portable tuyệt đối giữa các driver, có thể tạo bind marker theo số phần tử bằng helper đã kiểm soát và bind từng giá trị; không nối giá trị người dùng vào SQL.

## 8. Tránh N+1 khi cần tổng hợp nhiều loại dữ liệu

Một trang order có thể cần:

- Thông tin customer.
- Số lượng line.
- Tổng tiền.
- Trạng thái thanh toán mới nhất.

Không nên chạy bốn query cho từng order. Có thể tạo một read query dùng JOIN với các subquery tổng hợp đã nhóm theo order ID:

```sql
SELECT o.id,
       o.order_no,
       c.display_name AS customer_name,
       COALESCE(lines.line_count, 0) AS line_count,
       COALESCE(lines.total_amount, 0) AS total_amount,
       payment.status AS payment_status
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
LEFT JOIN (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity * unit_price) AS total_amount
    FROM order_line
    GROUP BY order_id
) lines ON lines.order_id = o.id
LEFT JOIN latest_payment payment ON payment.order_id = o.id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

`latest_payment` ở đây đại diện cho một subquery/view đã bảo đảm tối đa một hàng cho mỗi order. Nếu JOIN trực tiếp tất cả payment hoặc order line mà không kiểm soát cardinality, kết quả có thể nhân bản order và làm sai tổng tiền.

Với dữ liệu lớn, không nên tổng hợp toàn bộ bảng `order_line` rồi mới lọc page nếu query planner không thể tối ưu. Có thể giới hạn tập parent trước trong CTE/subquery rồi mới aggregate lines của các parent đó.

## 9. Phân trang parent trước khi JOIN collection

Một lỗi phổ biến là phân trang trực tiếp trên kết quả JOIN một-nhiều:

```sql
SELECT o.id, o.order_no, l.id AS line_id
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
```

`LIMIT 20` ở đây giới hạn 20 hàng sau JOIN, không phải 20 order. Một order có 10 lines chiếm 10 hàng kết quả; trang có thể chỉ chứa một vài order dù limit là 20.

Giải pháp là chọn page parent trước, rồi mới JOIN hoặc tải children:

```sql
WITH page_orders AS (
    SELECT id, order_no, customer_id, created_at
    FROM purchase_order
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT p.id AS order_id,
       p.order_no,
       c.display_name AS customer_name,
       l.id AS line_id,
       l.product_id,
       l.quantity
FROM page_orders p
JOIN customer c ON c.id = p.customer_id
LEFT JOIN order_line l ON l.order_id = p.id
ORDER BY p.created_at DESC, p.id DESC, l.id;
```

CTE giúp xác định page của parent trước. Kết quả vẫn có nhiều hàng cho mỗi order nếu có nhiều line, nên ứng dụng cần group rows thành DTO/aggregate hoặc thực hiện thêm một query batch cho lines.

Một cách khác là query page order DTO trước, rồi batch fetch lines bằng danh sách order IDs. Cách này có thể dễ ánh xạ hơn và tránh join nhân hàng trong kết quả chính.

## 10. N+1 có thể ẩn trong truy vấn COUNT

Một vòng lặp có thể chỉ lấy danh sách order một lần nhưng gọi count cho từng order:

```java
return orderRepository.findByStatus(status)
    .flatMap(order -> orderLineRepository.countByOrderId(order.id())
        .map(count -> new OrderSummary(order.id(), order.orderNo(), count)));
```

Đây vẫn là N+1: một query lấy orders và N query đếm lines. Query count có thể rất nhẹ với index phù hợp, nhưng N round trip vẫn tốn chi phí.

Hãy dùng `GROUP BY order_id` cho tập parent hoặc một subquery tổng hợp. Nếu chỉ cần biết có tồn tại line hay không, dùng `EXISTS` thay vì đếm tất cả:

```sql
SELECT o.id,
       o.order_no,
       EXISTS (
           SELECT 1
           FROM order_line l
           WHERE l.order_id = o.id
       ) AS has_lines
FROM purchase_order o
WHERE o.status = :status;
```

`EXISTS` có thể dừng khi tìm thấy một hàng phù hợp và diễn đạt đúng mục đích kiểm tra tồn tại. Cần có index trên `order_line(order_id)` để hỗ trợ truy vấn này.

## 11. Truy vấn đếm dùng để làm gì?

Giao diện phân trang kiểu truyền thống thường hiển thị:

- Tổng số bản ghi phù hợp.
- Tổng số trang.
- Trang hiện tại.
- Số bản ghi trên mỗi trang.

Để tính tổng trang, ứng dụng thường cần `COUNT(*)` trên cùng điều kiện lọc với query lấy dữ liệu. Nếu có 10 triệu hàng phù hợp, câu count có thể phải đọc nhiều index entry hoặc row để xác định tổng chính xác.

Trong reactive application, không nên giả định `Page<T>` được tạo miễn phí. Một `Page` đầy đủ thường cần cả content query và count query. Với reactive repository, `Page<T>` không phải kiểu kết quả reactive thông dụng vì việc tổng hợp tổng số phần tử đòi hỏi thêm thao tác bất đồng bộ; thường dùng `Flux<T>` với `Pageable` hoặc tự kết hợp content và count thành DTO/page model.

Ví dụ dùng `Mono.zip` để lấy content và count:

```java
public Mono<OrderPage> findPage(String status, int limit, long offset) {
    Mono<List<OrderListItem>> content = findOrderList(status, limit, offset)
        .collectList();

    Mono<Long> total = countOrders(status);

    return Mono.zip(content, total)
        .map(tuple -> new OrderPage(
            tuple.getT1(),
            tuple.getT2(),
            limit,
            offset
        ));
}
```

Hai query có thể chạy đồng thời nếu dùng `Mono.zip`, nhưng chúng là hai statement riêng. Cần cân nhắc transaction/isolation nếu yêu cầu content và total phản ánh cùng một snapshot dữ liệu.

## 12. COUNT(*) có luôn đắt không?

Không có câu trả lời chung. Chi phí phụ thuộc:

- Số hàng phù hợp với điều kiện lọc.
- Index có thể hỗ trợ điều kiện và count hay không.
- Database có thể dùng index-only scan hay phải đọc heap/table.
- Visibility map/MVCC và trạng thái vacuum ở PostgreSQL.
- Join, distinct, group by hoặc subquery trong điều kiện.
- Tần suất cập nhật dữ liệu và mức concurrency.
- Kế hoạch thực thi mà optimizer chọn.

`COUNT(*)` trên một bảng nhỏ có thể rất nhanh. `COUNT(*)` trên một bảng lớn với filter không có index có thể phải quét rất nhiều dữ liệu. Không nên kết luận mọi count đều chậm; hãy xem `EXPLAIN`/`EXPLAIN ANALYZE` trên database mục tiêu và dữ liệu gần production.

Một count chính xác có thể tốn thời gian hơn query lấy một trang nhỏ. Ví dụ content query chỉ cần 20 hàng và có thể dừng sớm theo index, trong khi count phải xác định tổng tất cả hàng phù hợp.

## 13. Viết count query đúng semantics

Count query phải đếm đúng đơn vị mà API trả về. Nếu API trả order, count cần đếm order, không phải số hàng sau JOIN.

Ví dụ sai khi join một-nhiều:

```sql
SELECT COUNT(*)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.status = :status;
```

Một order có 5 lines sẽ được đếm 5 lần. Nếu muốn đếm order, có thể dùng:

```sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE o.status = :status;
```

Hoặc nếu điều kiện chỉ cần biết order có line phù hợp, dùng `EXISTS`:

```sql
SELECT COUNT(*)
FROM purchase_order o
WHERE o.status = :status
  AND EXISTS (
      SELECT 1
      FROM order_line l
      WHERE l.order_id = o.id
  );
```

`COUNT(DISTINCT ...)` có thể tốn chi phí sort/hash để loại trùng. Nếu có thể diễn đạt điều kiện bằng `EXISTS`, query có thể đơn giản và dễ tối ưu hơn. Hãy so sánh execution plan và kiểm tra kết quả trên dữ liệu có parent với nhiều child.

## 14. COUNT(*) khác COUNT(column) và COUNT(DISTINCT ...)

Các hàm đếm có semantics khác nhau:

| Biểu thức | Ý nghĩa |
|---|---|
| `COUNT(*)` | Đếm tất cả hàng trong tập kết quả |
| `COUNT(column)` | Đếm hàng có giá trị `column` khác NULL |
| `COUNT(DISTINCT column)` | Đếm số giá trị khác nhau, bỏ NULL |
| `COUNT(DISTINCT parent.id)` | Đếm số parent duy nhất sau JOIN |

Ví dụ `LEFT JOIN`:

```sql
SELECT o.id,
       COUNT(*) AS joined_rows,
       COUNT(l.id) AS line_count
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
GROUP BY o.id;
```

Order không có line vẫn tạo một hàng sau `LEFT JOIN`, nên `COUNT(*)` trả 1 trong khi `COUNT(l.id)` trả 0. Khi đếm child, dùng một cột child không null như primary key.

Nếu JOIN thêm bảng khác có quan hệ một-nhiều, số hàng có thể bị nhân lên. Khi đó `COUNT(l.id)` cũng có thể đếm trùng line; cần pre-aggregate hoặc dùng `COUNT(DISTINCT l.id)` theo semantics phù hợp.

## 15. Tối ưu count bằng điều kiện và index

Giả sử endpoint lọc theo `tenant_id`, `status` và khoảng thời gian:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime;
```

Một index phù hợp có thể giúp database tìm vùng dữ liệu cần đếm nhanh hơn. Ví dụ một composite index có thể bắt đầu bằng các cột equality filter rồi tới cột range/sort:

```sql
CREATE INDEX idx_order_tenant_status_created
ON purchase_order (tenant_id, status, created_at DESC, id DESC);
```

Thứ tự cột index cần dựa trên query workload và selectivity. Không tạo index chỉ vì một câu query có nhiều điều kiện; mỗi index tăng chi phí insert/update và dung lượng lưu trữ.

Đối với PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` giúp xem scan type, số hàng thực tế, buffer hit/read và thời gian. `EXPLAIN ANALYZE` thực thi query, nên cần thận trọng với câu lệnh ghi và môi trường production.

Với MySQL, SQL Server và Oracle, dùng công cụ execution plan tương ứng. Không áp dụng kết luận từ PostgreSQL plan sang database khác.

## 16. Không phải API nào cũng cần tổng số chính xác

Nhiều màn hình chỉ cần biết còn trang tiếp theo hay không. Khi đó, chạy count chính xác cho hàng triệu bản ghi có thể là chi phí không cần thiết.

Một cách phổ biến là lấy `limit + 1` hàng:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize OFFSET :offset;
```

Trong đó `fetchSize = pageSize + 1`. Nếu query trả nhiều hơn `pageSize`, ứng dụng biết còn dữ liệu tiếp theo, bỏ hàng dư và trả `hasNext = true`.

DTO:

```java
public record OrderSlice(
    List<OrderListItem> content,
    boolean hasNext,
    int pageSize,
    long offset
) {}
```

Service:

```java
public Mono<OrderSlice> findSlice(String status, int pageSize, long offset) {
    int fetchSize = pageSize + 1;

    return findOrderList(status, fetchSize, offset)
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > pageSize;
            List<OrderListItem> content = hasNext
                ? rows.subList(0, pageSize)
                : rows;
            return new OrderSlice(content, hasNext, pageSize, offset);
        });
}
```

Đây là slice-style pagination: không có tổng số trang, nhưng tránh count query. Cần validate `pageSize` có giới hạn trên và `offset` không âm.

## 17. Count query và content query có thể nhìn thấy dữ liệu khác nhau

Nếu chạy content query và count query song song bằng `Mono.zip`, một transaction khác có thể insert/delete hàng giữa hai câu lệnh. Khi đó content và total có thể phản ánh hai thời điểm khác nhau.

Ví dụ:

1. Content query đọc 20 hàng.
2. Transaction khác insert thêm 1 hàng.
3. Count query chạy và đếm tổng mới.

Kết quả page có thể hợp lý cho một giao diện thông thường, nhưng không phải snapshot nhất quán tuyệt đối.

Nếu nghiệp vụ yêu cầu content và count phải nhất quán, hãy thực hiện chúng trong transaction với isolation phù hợp và xác nhận database cung cấp snapshot semantics mong muốn. Điều này có thể làm tăng chi phí và thời gian giữ connection. Với nhiều màn hình danh sách, eventual consistency nhỏ giữa count và content thường có thể chấp nhận được.

Không dùng `COUNT(*)` như cơ chế concurrency control. Count có thể thay đổi ngay sau khi trả kết quả.

## 18. Phân trang OFFSET hoạt động như thế nào?

Offset pagination thường dùng:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

`LIMIT 20 OFFSET 0` trả 20 hàng đầu. `LIMIT 20 OFFSET 1000` bỏ qua 1000 hàng đầu theo thứ tự rồi trả 20 hàng tiếp theo.

Ưu điểm:

- Dễ hiểu và dễ ánh xạ với số trang/page number.
- Người dùng có thể nhảy trực tiếp tới trang số bất kỳ.
- Hỗ trợ nhiều giao diện có total pages và page index.
- Thuận tiện cho tập dữ liệu nhỏ hoặc vừa.

Nhược điểm:

- Offset càng lớn, database thường phải tìm/đọc rồi bỏ qua nhiều hàng hơn.
- Dữ liệu thay đổi giữa các request có thể làm trùng hoặc thiếu hàng giữa các trang.
- Page number lớn có thể tạo query latency cao.
- Count query đi kèm có thể còn đắt hơn content query.

## 19. Vì sao offset sâu chậm?

Với `OFFSET 500000 LIMIT 20`, database cần xác định vị trí 500.000 hàng đầu theo thứ tự trước khi trả 20 hàng tiếp theo. Dù có index phù hợp, engine vẫn có thể phải đi qua rất nhiều index entry hoặc row rồi bỏ qua chúng.

Chi phí thường tăng theo offset vì database không tự biết vị trí vật lý của “hàng thứ 500.001” trong một thứ tự động. Query planner có thể chọn index scan, bitmap scan hoặc plan khác, nhưng bỏ qua số lượng lớn hàng vẫn tốn công.

Đây là lý do page đầu nhanh nhưng page 20.000 chậm, dù mỗi trang chỉ trả 20 hàng.

Không nên chỉ tăng timeout cho page sâu. Hãy xác định UX có thật sự cần nhảy tới trang tùy ý hay có thể chuyển sang cursor/keyset pagination.

## 20. OFFSET pagination không ổn định khi dữ liệu thay đổi

Giả sử trang đầu lấy 20 hàng mới nhất, trang hai dùng `OFFSET 20`. Sau khi client xem trang đầu, một hàng mới được insert ở đầu danh sách. Khi query trang hai, vị trí các hàng đã dịch xuống một hàng; client có thể thấy một hàng lặp lại hoặc bỏ lỡ một hàng.

Nếu có delete, các hàng phía sau dịch lên và một số hàng có thể bị bỏ qua. Nếu sort key thay đổi, một hàng có thể di chuyển giữa các trang.

Để giảm vấn đề:

- Dùng thứ tự ổn định, có tie-breaker duy nhất như `created_at, id`.
- Nếu cần snapshot nhất quán, dùng transaction/snapshot phù hợp trong một phiên làm việc ngắn hoặc snapshot token theo thiết kế.
- Với danh sách thay đổi liên tục, ưu tiên keyset/cursor pagination.
- Không giữ một transaction database mở trong suốt thời gian người dùng lật nhiều trang.

Thứ tự ổn định giúp tránh nondeterminism khi các hàng có cùng sort key, nhưng không tự ngăn dịch chuyển do dữ liệu mới được thêm hoặc xóa giữa hai request.

## 21. Keyset pagination là gì?

Keyset pagination (còn gọi là seek pagination) dùng giá trị của hàng cuối cùng ở trang trước làm cursor. Trang tiếp theo truy vấn các hàng nằm sau cursor trong thứ tự đã chọn, thay vì bỏ qua một số lượng hàng bằng `OFFSET`.

Giả sử sắp xếp giảm dần theo `created_at`, rồi `id`:

```sql
ORDER BY created_at DESC, id DESC
```

Trang đầu:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Giả sử hàng cuối có `created_at = :cursorCreatedAt` và `id = :cursorId`. Trang tiếp theo:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Database có thể dùng index để tìm từ vị trí cursor trở đi. Chi phí không tăng tuyến tính theo số trang như offset sâu trong nhiều workload.

## 22. Cursor cần chứa đủ các sort key

Nếu chỉ dùng `created_at` làm cursor, hai hoặc nhiều hàng có cùng timestamp có thể bị bỏ sót hoặc lặp. Vì vậy, cần thêm khóa duy nhất làm tie-breaker.

Với thứ tự `(created_at DESC, id DESC)`, cursor phải chứa cả hai giá trị:

```java
public record OrderCursor(
    Instant createdAt,
    Long id
) {}
```

DTO response:

```java
public record CursorPage<T>(
    List<T> content,
    String nextCursor,
    boolean hasNext
) {}
```

Cursor có thể được serialize thành token opaque, ví dụ JSON được Base64 URL-safe và ký HMAC để client không thể sửa giá trị tùy ý. Không cần tiết lộ toàn bộ SQL sort key nếu API muốn giữ cursor opaque.

Cursor nên chứa hoặc ràng buộc với filter/sort hiện tại. Không dùng cursor tạo cho `status=NEW` để tiếp tục query `status=PAID` nếu hợp đồng không cho phép.

## 23. Ví dụ keyset pagination với DatabaseClient

Repository adapter có thể triển khai hai nhánh: trang đầu không có cursor và trang tiếp theo có cursor.

```java
public Flux<OrderListItem> findNextPage(
        String status,
        Instant cursorCreatedAt,
        Long cursorId,
        int limit) {

    return databaseClient.sql("""
            SELECT id, order_no, status, created_at
            FROM purchase_order
            WHERE status = :status
              AND (
                  created_at < :cursorCreatedAt
                  OR (created_at = :cursorCreatedAt AND id < :cursorId)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """)
        .bind("status", status)
        .bind("cursorCreatedAt", cursorCreatedAt)
        .bind("cursorId", cursorId)
        .bind("limit", limit + 1)
        .map((row, metadata) -> new OrderListItem(
            row.get("id", Long.class),
            row.get("order_no", String.class),
            null,
            row.get("status", String.class)
        ))
        .all();
}
```

Ví dụ dùng `LIMIT` theo PostgreSQL/MySQL; dialect khác cần cú pháp tương ứng. `limit + 1` giúp xác định `hasNext`. Trong triển khai thật, DTO/cursor cần mang `created_at` và `id` của hàng cuối để tạo cursor tiếp theo; không nên bỏ sort key khỏi kết quả nội bộ trước khi tạo token.

Trang đầu dùng query tương tự nhưng bỏ điều kiện cursor. Hãy validate `limit` có giới hạn trên, ví dụ tối đa 100, để client không yêu cầu hàng triệu bản ghi trong một request.

## 24. Keyset pagination với nhiều chiều sort

Nếu sort theo hai trường:

```sql
ORDER BY priority DESC, created_at ASC, id ASC
```

Điều kiện cursor phải phản ánh đúng thứ tự lexicographic và chiều tăng/giảm của từng trường:

```sql
WHERE priority < :cursorPriority
   OR (priority = :cursorPriority AND created_at > :cursorCreatedAt)
   OR (priority = :cursorPriority
       AND created_at = :cursorCreatedAt
       AND id > :cursorId)
```

Vì `priority` giảm dần nên hàng sau cursor có priority nhỏ hơn; `created_at` và `id` tăng dần nên dùng dấu lớn hơn ở phần tie-breaker. Với sort direction phức tạp, hãy tạo predicate tương ứng và kiểm thử các hàng trùng sort key.

Không thể dùng một predicate đơn giản như `id > :cursorId` nếu thứ tự chính là `created_at DESC, id DESC` và ID không đại diện cho thứ tự đó.

## 25. Xử lý NULL trong keyset pagination

Sort key nullable làm cursor phức tạp vì phép so sánh với NULL cho kết quả UNKNOWN. Ví dụ `created_at < :cursor` không chọn được hàng có `created_at IS NULL`.

Các lựa chọn:

- Thiết kế sort key không nullable nếu có thể.
- Xác định rõ `NULLS FIRST`/`NULLS LAST` và viết predicate theo cùng quy tắc.
- Chuẩn hóa giá trị sort bằng biểu thức/cột computed có index nếu phù hợp.
- Dùng một cursor bao gồm trạng thái null và các tie-breaker.

Ví dụ PostgreSQL hỗ trợ `NULLS LAST` trong `ORDER BY`, nhưng predicate cursor phải được viết tương ứng. Không giả định tất cả database có cùng cú pháp null ordering.

Đối với API phân trang hiệu năng cao, sort key không nullable và có index thường đơn giản, ổn định hơn.

## 26. Index cho offset và keyset pagination

Index cần khớp với filter và thứ tự sort. Ví dụ query:

```sql
SELECT id, order_no, created_at
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Một index ứng viên:

```sql
CREATE INDEX idx_order_tenant_status_created_id
ON purchase_order (tenant_id, status, created_at DESC, id DESC);
```

Các cột equality filter thường đứng trước các sort key trong composite index. Nhưng lựa chọn cuối cùng phụ thuộc cardinality, selectivity, workload khác và database optimizer.

Keyset pagination đặc biệt hưởng lợi khi index hỗ trợ cả điều kiện cursor lẫn order. Nếu thiếu index, query keyset vẫn có thể scan nhiều hàng. Hãy xem execution plan thay vì mặc định cursor luôn nhanh.

Không tạo index riêng cho mọi tổ hợp filter. Mỗi index làm tăng dung lượng và chi phí ghi. Theo dõi query phổ biến và chọn index theo workload thực.

## 27. Count query trong API cursor pagination

Cursor pagination thường không cần total count. API có thể trả:

- `content`: các hàng hiện tại.
- `nextCursor`: token của hàng cuối.
- `hasNext`: có thêm dữ liệu hay không.

`hasNext` được xác định bằng cách lấy `limit + 1` hàng. Nếu có hàng dư, bỏ hàng đó khỏi content và đặt `hasNext = true`.

Điều này tránh một câu `COUNT(*)` trên toàn bộ tập dữ liệu cho mỗi trang. Với các danh sách lớn hoặc thay đổi liên tục, đây thường là hợp đồng phù hợp hơn total pages.

Nếu nghiệp vụ thật sự cần tổng số chính xác, có thể cung cấp count riêng, cache trong khoảng thời gian ngắn hoặc tính trong một tác vụ báo cáo. Hãy cân nhắc độ mới của total và chi phí tính toán.

## 28. Khi nào vẫn nên dùng OFFSET?

Offset pagination vẫn phù hợp khi:

- Tập dữ liệu nhỏ hoặc vừa.
- Người dùng cần nhảy trực tiếp tới trang bất kỳ.
- Tổng số trang là yêu cầu bắt buộc.
- Offset lớn không xuất hiện trong workload thực tế.
- Query có index tốt và latency đã được đo ở các page sâu.
- Dữ liệu ít thay đổi trong thời gian người dùng duyệt.

Không cần thay mọi endpoint bằng keyset. Keyset khó hỗ trợ nhảy tới trang thứ 500 nếu không lưu checkpoint hoặc có một cơ chế định vị khác. Hãy chọn pagination theo hành vi người dùng và quy mô dữ liệu.

Một thiết kế thực tế có thể dùng offset cho bảng quản trị nhỏ và cursor cho timeline/feed lớn.

## 29. Keyset pagination không tự bảo đảm snapshot cố định

Keyset giúp tránh chi phí bỏ qua hàng đầu và giảm hiện tượng dịch chuyển do insert mới đứng trước cursor. Tuy nhiên, nó không tự tạo snapshot xuyên nhiều request.

Ví dụ:

- Một hàng cũ được cập nhật `created_at` hoặc sort key khiến nó di chuyển qua cursor.
- Một hàng bị xóa trước khi client tới trang sau.
- Filter thay đổi giữa các request.
- Một bản ghi mới có sort key nằm sau cursor được thêm vào.

Để kết quả nhất quán hơn:

- Dùng sort key bất biến như `created_at` và ID không đổi.
- Giữ filter/sort trong cursor token.
- Nếu cần snapshot cố định, dùng watermark/high-water mark hoặc snapshot/version nghiệp vụ.
- Tránh giữ transaction mở giữa các request HTTP chỉ để giữ MVCC snapshot.

Một cursor có thể chứa `upperBound` của trang đầu để bỏ qua bản ghi được tạo sau thời điểm bắt đầu duyệt. Điều này giúp ổn định tập dữ liệu mới, nhưng không giải quyết mọi update/delete; hợp đồng API cần nói rõ semantics.

## 30. So sánh Offset và Keyset

| Tiêu chí | Offset pagination | Keyset/cursor pagination |
|---|---|---|
| Điều hướng | Page number, nhảy tới trang tùy ý | Đi tiếp/lùi theo cursor; nhảy trang tùy ý khó hơn |
| Chi phí trang sâu | Thường tăng theo số hàng phải bỏ qua | Có thể dùng index để seek tới cursor |
| Thứ tự ổn định | Cần `ORDER BY` có tie-breaker | Cần sort key và tie-breaker trong cursor |
| Dữ liệu thay đổi giữa trang | Có thể lặp/bỏ hàng do vị trí dịch chuyển | Ít bị ảnh hưởng bởi insert trước cursor, nhưng không phải snapshot |
| Tổng số trang | Thường đi cùng count query | Thường không cần count |
| Phù hợp | Admin grid, tập dữ liệu vừa, page jump | Feed, timeline, danh sách lớn và duyệt tuần tự |
| Độ phức tạp triển khai | Đơn giản | Cursor, sort predicate, null và filter cần thiết kế kỹ |

## 31. Phân trang với Spring Data R2DBC

Reactive Repository thường trả `Flux<T>` cho danh sách. Có thể dùng các query method hoặc `@Query` với tham số phân trang tùy tính năng được phiên bản Spring Data R2DBC hỗ trợ. Tuy nhiên, không nên kỳ vọng reactive repository tự trả một `Page<T>` đầy đủ cùng total count như một lời gọi đồng bộ đơn giản.

Với truy vấn tùy chỉnh, có thể nhận `Pageable` ở service rồi chuyển `pageSize` và `offset` thành bind parameter trong `DatabaseClient`, hoặc dùng `R2dbcEntityTemplate` với `Query`/`Criteria` và `limit`/`offset` theo API phiên bản.

Ví dụ service kiểm tra input:

```java
public Mono<OrderPage> search(String status, Pageable pageable) {
    int limit = Math.min(pageable.getPageSize(), 100);
    long offset = pageable.getOffset();

    Mono<List<OrderListItem>> content =
        findOrderList(status, limit, offset).collectList();
    Mono<Long> total = countOrders(status);

    return Mono.zip(content, total)
        .map(tuple -> new OrderPage(
            tuple.getT1(), tuple.getT2(), limit, offset));
}
```

Trong production, cần kiểm tra page size tối thiểu/tối đa, offset không âm, sort field nằm trong allow-list và sort direction hợp lệ. Không đưa tên cột do client gửi trực tiếp vào SQL.

## 32. Xây dựng count query riêng với DatabaseClient

Content query và count query nên được tối ưu độc lập:

```java
public Mono<Long> countOrders(String status) {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM purchase_order
            WHERE status = :status
            """)
        .bind("status", status)
        .map((row, metadata) -> row.get("total", Long.class))
        .one()
        .defaultIfEmpty(0L);
}
```

Dùng `Long` vì số hàng có thể vượt giới hạn `Integer`. Kiểu trả về cụ thể từ driver có thể cần converter nếu database trả numeric type khác; hãy xác nhận mapping trên engine mục tiêu.

Nếu content query có JOIN để lấy tên customer nhưng điều kiện lọc chỉ dựa trên order, count query có thể không cần JOIN customer. Loại bỏ join không cần thiết giúp count đơn giản hơn, miễn là giữ nguyên semantics của filter.

## 33. Cache hoặc ước lượng total count khi phù hợp

Một số màn hình báo cáo không cần total count chính xác tới từng giây. Có thể:

- Cache count trong một khoảng thời gian ngắn.
- Tính count theo batch/background job.
- Dùng số liệu thống kê/ước lượng của database cho dashboard chấp nhận approximate total.
- Chỉ hiển thị “còn dữ liệu” thay vì tổng số trang.
- Tính total trên một read model được tối ưu riêng.

Nếu dùng approximate count, API và UI phải thể hiện rõ đó là ước lượng. Không dùng số liệu thống kê ước lượng để kiểm soát nghiệp vụ như hạn mức, thanh toán hoặc quyền truy cập.

Cache count cần invalidation hoặc TTL phù hợp. Nếu filter có nhiều tổ hợp, cache key phải bao gồm tenant, status, time range và các điều kiện ảnh hưởng kết quả.

## 34. Đo query plan và benchmark với dữ liệu đủ lớn

Một truy vấn chạy nhanh trên 100 hàng không nói lên hiệu năng ở 10 triệu hàng. Tạo dataset test có phân bố gần production:

- Số parent và child đủ lớn.
- Cardinality của quan hệ một-nhiều thực tế.
- Tỷ lệ mỗi status và tenant.
- Sort key trùng nhau và giá trị null nếu được phép.
- Index giống production.
- Tỷ lệ insert/update/delete phù hợp.

Đo riêng:

- Query lấy content.
- Query count.
- Tổng query count của một request.
- Page đầu, page trung bình và offset sâu.
- Keyset page kế tiếp.
- Pool acquire latency và database execution time.

Sử dụng execution plan để xác định query đang scan bao nhiêu hàng, có dùng index đúng không và join có nhân cardinality không. Benchmark phải warm up và chạy nhiều lần; không kết luận từ một lần chạy đơn lẻ.

## 35. Kiểm thử để ngăn N+1 quay lại

Một integration test có thể đo số statement được thực hiện trong một request. Có thể dùng R2DBC proxy hoặc instrumentation của dự án để đếm query theo connection/test scope.

Kịch bản:

1. Tạo 10 order, mỗi order có customer và một số order line.
2. Reset query counter.
3. Gọi service lấy danh sách.
4. Xác nhận DTO có customer name và line count đúng.
5. Kiểm tra query count không tăng theo số order.
6. Tăng fixture lên 50 order và xác nhận số query vẫn cố định hoặc tăng theo số batch, không tăng một query cho mỗi row.

Không nên hard-code số query nếu framework có query metadata hoặc health check phụ; hãy xác định chính xác những statement nghiệp vụ cần đếm. Test cần dùng database/driver thật để đo round trip thực tế.

## 36. Kiểm thử count semantics và pagination

Các trường hợp nên có:

- Parent không có child.
- Parent có một child.
- Parent có nhiều child.
- JOIN thêm hai collection để phát hiện nhân bản hàng.
- Filter chỉ dựa trên parent và filter dựa trên child.
- Hàng có cùng `created_at` để kiểm tra tie-breaker.
- Hàng bị insert/delete giữa hai lần lấy trang.
- Offset bằng 0, offset lớn, trang cuối và page size vượt giới hạn.
- Cursor bằng giá trị sort key trùng nhau.
- Sort key null nếu schema cho phép.

Với count query, so sánh total với số parent duy nhất trong fixture, không so sánh với số hàng sau JOIN. Với keyset, ghép nhiều trang và xác nhận không trùng ID, không thiếu ID trong một dataset cố định.

## 37. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Endpoint chạy hàng trăm query cho một page | N+1 từ repository call trong `flatMap` | JOIN projection hoặc batch fetch theo tập ID |
| Đổi `flatMap` thành `concatMap` nhưng vẫn chậm | Query vẫn là N+1, chỉ chuyển từ song song sang tuần tự | Giảm số query, không chỉ đổi concurrency |
| `COUNT(*)` trả total lớn hơn số parent | Count sau JOIN một-nhiều | `COUNT(DISTINCT parent.id)` hoặc `EXISTS`/pre-aggregate |
| Order không có line lại có count bằng 1 | Dùng `COUNT(*)` sau `LEFT JOIN` | Dùng `COUNT(child.id)` |
| Page đầu nhanh, page sâu rất chậm | Offset lớn phải bỏ qua nhiều hàng | Keyset pagination và index theo filter/sort |
| Hàng lặp hoặc mất giữa các trang | Sort không duy nhất hoặc dữ liệu thay đổi | Thêm tie-breaker, dùng cursor/watermark khi phù hợp |
| Page chỉ có vài parent dù limit lớn | `LIMIT` áp dụng sau JOIN collection | Phân trang parent trước rồi tải child |
| Count và content không khớp tuyệt đối | Hai query đọc ở thời điểm khác nhau | Chấp nhận eventual consistency hoặc dùng snapshot phù hợp |
| Keyset bỏ sót hàng có NULL sort key | Predicate không xử lý null | Sort key non-null hoặc viết predicate theo null ordering |
| Tăng concurrency làm database quá tải | N+1 vẫn tồn tại và nhiều query chạy đồng thời | Batch query, giới hạn concurrency và theo dõi pool |

## 38. Quy trình tối ưu một endpoint danh sách

Khi một endpoint danh sách chậm, hãy thực hiện theo trình tự:

**Bước 1 — Đo query count.** Ghi nhận số statement trên mỗi request và xem query nào lặp theo từng parent.

**Bước 2 — Xác định DTO thực sự cần gì.** Tránh tải toàn bộ object graph nếu chỉ cần vài cột hiển thị.

**Bước 3 — Loại N+1.** Dùng JOIN projection hoặc batch fetch theo tập ID; gom các phép count bằng `GROUP BY`.

**Bước 4 — Kiểm tra cardinality.** Nếu JOIN collection, phân trang parent trước và tránh nhân bản parent/aggregate.

**Bước 5 — Đánh giá count query.** Xác định có cần total chính xác hay chỉ cần `hasNext`; sửa count semantics và index.

**Bước 6 — Đo offset sâu.** Benchmark page đầu, page trung bình và page sâu trên dataset gần production.

**Bước 7 — Chọn pagination.** Giữ offset khi cần page jump và dữ liệu vừa; chuyển keyset khi danh sách lớn và duyệt tuần tự.

**Bước 8 — Thiết kế index.** Khớp filter, sort và cursor predicate; kiểm tra execution plan.

**Bước 9 — Kiểm thử concurrency.** Xác nhận kết quả khi dữ liệu thay đổi và khi nhiều request cùng truy vấn.

**Bước 10 — Thêm regression test.** Đo query count, count semantics và không trùng/mất hàng qua nhiều trang.

## 39. Kết luận

N+1, count query và offset sâu là ba nguyên nhân phổ biến làm endpoint danh sách R2DBC chậm khi dữ liệu tăng. Reactive API không tự gộp query; gọi repository bên trong `flatMap` vẫn có thể tạo một query cho mỗi parent. Hãy dùng JOIN projection hoặc batch fetch theo tập ID, gom count bằng `GROUP BY`/`EXISTS`, và kiểm soát cardinality khi join collection.

Count chính xác có thể tốn chi phí riêng và không phải giao diện nào cũng cần total pages. Nếu chỉ cần biết còn dữ liệu, lấy `limit + 1` để tạo slice. Offset pagination dễ dùng nhưng page sâu phải bỏ qua nhiều hàng và dễ dịch chuyển khi dữ liệu thay đổi; keyset pagination dùng cursor chứa đầy đủ sort key và tie-breaker để seek qua index hiệu quả hơn. Kết hợp query plan, index đúng workload, metrics và integration tests trên database thật giúp hiệu năng danh sách ổn định khi quy mô dữ liệu tăng.
