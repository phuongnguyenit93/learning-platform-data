# Phát hiện số lần truy cập vượt nhu cầu nghiệp vụ

Trong chương **Hiệu năng** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một ứng dụng Java có thể chạy chậm dù từng câu SQL riêng lẻ đều mất rất ít thời gian. Nguyên nhân thường gặp là **một thao tác nghiệp vụ tạo ra nhiều lượt truy cập database hơn mức cần thiết**: lấy danh sách đơn hàng rồi đọc chi tiết từng đơn, kiểm tra cùng một điều kiện lặp lại ở nhiều tầng, hoặc thực thi hàng trăm câu `INSERT` từng dòng thay vì xử lý theo lô.

Phát hiện vấn đề này đòi hỏi nhìn từ **một use case có kết quả nghiệp vụ cụ thể** xuống các lần gọi persistence, chứ không chỉ tìm “câu SQL chậm nhất”. Một truy vấn mất 2 ms nhưng bị gọi 500 lần trong một request có thể tạo ra chi phí lớn hơn một truy vấn phù hợp mất 30 ms. Ngược lại, ép mọi công việc vào một SQL khổng lồ cũng có thể gây tải dữ liệu thừa, khóa lâu hoặc làm sai điều kiện nghiệp vụ.

Mục tiêu là tìm **truy cập dư thừa so với dữ liệu và bảo đảm mà use case thật sự cần**, rồi giảm chúng mà vẫn giữ đúng transaction, isolation, phân quyền, kết quả ghi, retry và khả năng vận hành. Bài học minh họa bằng JDBC, Spring JDBC, JPA/Hibernate, PostgreSQL và các kỹ thuật quan sát thực tế.

## 1. Truy cập “vượt nhu cầu” nghĩa là gì?

Không tồn tại một ngưỡng cố định như “mỗi HTTP request chỉ được phép chạy tối đa ba SQL”. Một thao tác xác thực đơn giản có thể chỉ cần một lần đọc, trong khi giao dịch ghi nhiều bảng cần nhiều câu SQL để đảm bảo atomicity và lưu lịch sử.

**Số lần truy cập vượt nhu cầu nghiệp vụ** là phần công việc đọc/ghi/phối hợp database có thể được giảm hoặc gộp mà **không làm mất**:

- Dữ liệu thực sự cần để trả kết quả.
- Bất biến nghiệp vụ và quyền truy cập.
- Tính nguyên tử của các thay đổi.
- Kiểm soát đồng thời, isolation và khả năng phát hiện xung đột.
- Cơ chế idempotency, kiểm toán và đối soát khi commit không rõ kết quả.
- Hợp đồng nhất quán/độ mới mà khách hàng sử dụng API mong đợi.

Ví dụ một API trả 20 đơn hàng, mỗi đơn có tên khách và tổng tiền:

| Cách thực hiện | Số lượt SQL gần đúng | Nhận xét |
| --- | ---: | --- |
| 1 SQL lấy danh sách + 20 SQL lấy khách + 20 SQL lấy dòng hàng | 41 | Nghi vấn **N+1 ở hai quan hệ**. |
| 1 SQL lấy danh sách + 1 SQL tải khách + 1 SQL lấy tổng theo các đơn | 3 | Có thể đáp ứng cùng dữ liệu nếu thiết kế đúng. |
| 1 SQL join mọi bảng và trả hàng nghìn dòng trùng lặp | 1 | Ít round-trip, nhưng có thể **over-fetch** rất nặng. |
| 2–4 SQL có phân trang và projection phù hợp | 2–4 | Có thể tốt hơn một SQL join lớn. |

**Ít SQL hơn không tự động đồng nghĩa hiệu năng tốt hơn.** Định nghĩa cần xét tổng thời gian, dữ liệu truyền, công việc máy chủ, concurrency và tính đúng đắn.

## 2. Đo đúng đơn vị: truy vấn, round-trip, hàng và thao tác nghiệp vụ

Một câu “ứng dụng truy cập database 100 lần” dễ gây nhầm lẫn. Cần thống nhất đang đếm gì.

| Đơn vị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Use-case invocation** | Một lần thực hiện nghiệp vụ. | `GET /orders?customerId=...`. |
| **SQL execution** | Một lần thực thi statement. | `SELECT ... WHERE order_id=?`. |
| **Network round-trip** | Một lượt trao đổi cần chờ mạng. | Một hoặc nhiều statement tùy driver/protocol/batching. |
| **Prepared-statement execution** | Một statement đã chuẩn bị được thực thi. | Một query lặp trong vòng `for`. |
| **Rows returned** | Số hàng đi từ database về ứng dụng. | Join trả 20.000 hàng để tạo 20 DTO. |
| **Rows examined/visited** | Công việc quét dữ liệu trong execution plan. | Quét hàng triệu hàng để trả 20 hàng. |
| **Logical block accesses** | Trang dữ liệu/index engine xử lý. | Cache hit trong buffer pool. |
| **Physical I/O** | Đọc/ghi thực tới thiết bị lưu trữ. | Miss từ DB buffer và OS cache. |
| **Connection acquisitions** | Số lần mượn JDBC connection từ pool. | Một transaction giữ một connection cho nhiều SQL. |

Các đơn vị này **không thay thế nhau**. Một transaction dùng một connection có thể chạy 100 SQL; một SQL có thể đọc rất nhiều trang; một batch API có thể giảm round-trip nhưng server vẫn phải xử lý mỗi hàng. Cần đo riêng số lần query, độ trễ query, lượng dữ liệu và chi phí server.

### Nhìn theo đường đi của một request

```text
Client gọi GET /customers/42/orders
                 |
                 v
            Controller
                 |
                 v
        OrderApplicationService
                 |
        +--------+---------+
        |                  |
   OrderRepository    CustomerRepository
        |                  |
        v                  v
      SQL A          SQL B, C, D ...
        |
        v
      ORM ánh xạ Order
        |
        +-- foreach Order: lazy-load lines
        |       SQL E, F, G ... (N+1)
        |
        v
      JSON response
```

Nếu chỉ xem tên phương thức `findAllByCustomerId(...)`, lập trình viên có thể nghĩ một lệnh repository tương ứng một query. Lazy loading khi mapping DTO hoặc serialize JSON có thể thực thi thêm SQL **sau đó**, thậm chí khi business service đã kết thúc nếu cấu hình session cho phép.

## 3. Đặt “ngân sách truy cập” theo use case, không theo cảm tính

Một cách thực dụng là lập **query budget** cho các use case quan trọng. Đây là tiêu chí để **phát hiện hồi quy**, không phải một giới hạn phổ quát độc lập với yêu cầu.

Ví dụ một hệ thống giả định:

| Use case | Dữ liệu cần có | Mô hình truy vấn cần khảo sát | Tín hiệu bất thường |
| --- | --- | --- | --- |
| Xem chi tiết một sản phẩm | SKU, tên, giá hiển thị, trạng thái | Một projection hoặc vài đọc có lý do rõ. | Mỗi thuộc tính lại kéo thêm query. |
| Danh sách 25 đơn | 25 phần tử, tổng tiền, tên khách | Truy vấn trang + truy vấn gộp dữ liệu liên quan; count nếu hợp đồng cần. | Tăng page size 25→50 làm SQL tăng thêm khoảng 25. |
| Giữ tồn kho | Kiểm tra điều kiện và ghi nguyên tử | Cập nhật có điều kiện, ghi kết quả/idempotency trong transaction. | Đọc–kiểm tra lại nhiều lần rồi update không có guard. |
| Import 2.000 dòng | Validation, ghi dữ liệu, báo cáo lỗi | Batch/chunk theo tài nguyên và tính đúng đắn. | 2.000 lượt mạng riêng cho câu SQL có thể gộp. |
| Báo cáo tổng hợp | Nhóm theo chiều dữ liệu, tổng/count | SQL aggregate/projection hoặc pipeline được thiết kế. | Tải toàn bộ entity vào JVM chỉ để cộng một cột. |

Cần quyết định rõ **mục đích của từng truy cập**: đọc để hiển thị, kiểm tra quyền, khóa bảo vệ concurrency, ghi audit, outbox hay đối soát. Các lượt dùng để bảo vệ bất biến **không phải tự động dư thừa**, ngay cả khi cùng đụng một bảng.

Ngân sách nên được xác minh theo **kích thước đầu vào**. Với endpoint trang 20/50/100 phần tử, đường cong query count cho biết liệu chi phí có tăng theo số entity hay không.

## 4. N+1 query: dấu hiệu điển hình của truy cập tăng theo dữ liệu

**N+1** xuất hiện khi lấy một tập N đối tượng bằng một query, sau đó phát sinh thêm một query cho từng đối tượng.

```text
1 SQL tải 100 orders
  + 1 SQL tải lines của order #1
  + 1 SQL tải lines của order #2
  ...
  + 1 SQL tải lines của order #100
  = 101 SQL executions
```

Một ví dụ minh họa với JPA/Hibernate:

```java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReadService {
    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findSummaries(long customerId) {
        return orders.findByCustomerId(customerId).stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getLines().size()
                ))
                .toList();
    }
}
```

Giả định `OrderRepository.findByCustomerId(...)` trả danh sách entity `Order`, quan hệ `Order.lines` được tải lazy và chưa có batch fetching/second-level cache phù hợp. Mỗi lời gọi `getLines().size()` **có thể** kích hoạt một SQL riêng. Cơ chế cụ thể còn phụ thuộc mapping, cache, phiên bản ORM và fetch strategy.

Không nên kết luận chỉ từ code rằng chắc chắn có 101 câu SQL. Phải **đo SQL thực thi** với mapping, dữ liệu và cấu hình đang chạy. Nếu collection đã được nạp bằng entity graph hoặc batch fetching, số query thực tế có thể khác.

### Vì sao N+1 trở nên nghiêm trọng khi tăng tải?

Giả sử một request hiển thị 50 đơn và ORM phát 51 SQL. Với **200 request/giây**, riêng use case này có thể tạo khoảng:

```text
51 SQL/request × 200 request/giây = 10.200 SQL executions/giây
```

Nếu thiết kế lại để còn 3 SQL/request trên cùng workload giả định:

```text
3 SQL/request × 200 request/giây = 600 SQL executions/giây
```

Đây chỉ là phép nhân minh họa, **không phải benchmark đo được**. Tổng chi phí còn phụ thuộc số hàng, execution plan và dữ liệu truyền. Nhưng nó cho thấy vì sao SQL nhanh 1–2 ms vẫn gây áp lực lớn nếu gọi lặp.

## 5. Tìm N+1 bằng tương quan giữa số SQL và số phần tử

Thử cùng một endpoint với N = 1, 5, 20, 50 đơn có dữ liệu quan hệ tương tự. Ghi lại số SQL và độ trễ:

| N đơn | Số SQL giả định | Biểu thức gần đúng | Khả năng |
| ---: | ---: | --- | --- |
| 1 | 2 | 1 + N | Query danh sách rồi query từng đơn. |
| 5 | 6 | 1 + N | Có thể N+1. |
| 20 | 21 | 1 + N | Cần kiểm tra call site trong vòng lặp. |
| 50 | 51 | 1 + N | N+1 có bằng chứng định lượng. |

Nếu còn quan hệ `customer` được đọc riêng cho mỗi đơn, số query có thể thành `1 + 2N`, hoặc thấp hơn nếu nhiều đơn cùng trỏ tới một customer được identity map/cache phục vụ.

Các vị trí dễ phát sinh N+1:

- Vòng `for` gọi repository cho từng ID.
- ORM lazy collection khi tạo DTO.
- Chuyển entity thẳng sang JSON khiến serializer gọi getter tải thêm dữ liệu.
- Mapping `@ManyToOne` mặc định eager ở JPA mà thiếu fetch plan chủ đích.
- Validation theo từng dòng gọi `existsBy...` hoặc `findBy...`.
- GraphQL resolver truy vấn mỗi field/record thay vì gom bằng batch loader.
- Gọi SQL function hoặc stored procedure cho từng item từ application.

**Dấu hiệu quan sát mạnh nhất** là số SQL tăng tỷ lệ với số phần tử được xử lý, trong khi nghiệp vụ chủ yếu cần một tập dữ liệu có thể đọc theo lô.

## 6. Giảm N+1: chọn đúng cách tải dữ liệu

Không có một cách sửa cho mọi quan hệ. Những lựa chọn thường gặp:

| Chiến lược | Cách làm | Điểm cần cân nhắc |
| --- | --- | --- |
| **Fetch join** | Tải entity cùng quan hệ bằng join trong một query. | Nhân số hàng khi join collection; pagination có thể sai/kém hiệu năng. |
| **Entity graph** | Khai báo các quan hệ cần tải cho use case. | Cần đo SQL thực tế và kiểm soát kích thước graph. |
| **Batch fetching** | ORM tải nhiều quan hệ lazy bằng số ít query theo batch. | Vẫn có nhiều query và có thể nạp dư; tùy provider. |
| **DTO projection** | Truy vấn đúng trường cần cho response. | Mapping và group/aggregate phải chính xác. |
| **Bulk fetch by IDs** | Query danh sách ID rồi query dữ liệu con theo tập ID. | Chia chunk, xử lý thứ tự/kết quả trống, số tham số và giới hạn DB. |
| **Aggregate SQL** | Tính count/sum/group trong database. | Kiểm tra bộ lọc và định nghĩa nghiệp vụ; không dùng aggregate sai phạm vi tenant. |

### Giải pháp hai pha khi phân trang collection

Với endpoint trả **một trang đơn hàng và số lượng dòng mỗi đơn**, có thể:

1. Chọn 25 order ID phù hợp bộ lọc, sắp xếp ổn định và phân trang trên **bảng order**.
2. Truy vấn số dòng hoặc dữ liệu liên quan cho **chính tập ID đã chọn**.
3. Ghép theo order ID trong Java và duy trì thứ tự của trang đầu.

Ví dụ SQL PostgreSQL:

```sql
-- Bước 1: phân trang đơn hàng theo bộ lọc và thứ tự xác định.
SELECT id, created_at, status
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, id DESC
LIMIT :page_size OFFSET :offset;

-- Bước 2: lấy số dòng cho các ID thực sự nằm trong trang.
SELECT order_id, COUNT(*) AS line_count
FROM order_lines
WHERE order_id IN (:order_ids)
GROUP BY order_id;
```

`:order_ids` đại diện một tập tham số do thư viện truy vấn mở rộng/bind an toàn; JDBC thuần không tự hiểu cú pháp `IN (:order_ids)`. Với tập ID rỗng, bỏ qua bước 2; với danh sách lớn, có thể dùng array binding hoặc chunk theo khả năng driver/DB.

Đừng cố `LEFT JOIN FETCH order.lines` một collection rồi áp dụng pagination mà không kiểm tra cách ORM xử lý. Join làm nhân số hàng, và một số cấu hình ORM có thể phải phân trang trong bộ nhớ hoặc từ chối/hỏi lỗi khi fetch collection kết hợp limit. **Phân trang trên parent IDs rồi tải children theo IDs** thường dễ kiểm soát hơn.

### DTO projection cho trường hợp chỉ cần tổng

Nếu response chỉ cần `lineCount`, không nhất thiết tải mọi `OrderLine` object vào heap. Có thể dùng SQL tổng hợp:

```sql
SELECT o.id,
       o.created_at,
       COUNT(ol.id) AS line_count
FROM orders AS o
LEFT JOIN order_lines AS ol ON ol.order_id = o.id
WHERE o.customer_id = :customer_id
GROUP BY o.id, o.created_at
ORDER BY o.created_at DESC, o.id DESC
LIMIT :page_size;
```

Đây là một phương án nếu filter/group/order semantics phù hợp và query plan chấp nhận được. Khi thêm nhiều quan hệ 1-N, join có thể **nhân bản các dòng con và làm COUNT/SUM sai** nếu không xử lý. Không phải cứ một query tổng hợp là luôn tốt hơn hai query rõ ràng.

## 7. Truy vấn lặp nhưng không phải N+1: đọc cùng một dữ liệu nhiều lần

Một use case có thể đọc cùng bản ghi nhiều lần vì các tầng không chia sẻ thông tin đã lấy:

```text
Controller:  existsById(orderId)       → SQL 1
Service:     findById(orderId)         → SQL 2
Policy:      loadOrderStatus(orderId)  → SQL 3
Repository:  SELECT status ...         → SQL 4
             UPDATE orders ...         → SQL 5
```

Một phần có thể cần thiết tùy isolation, bảo mật và transaction. Nhưng thường có những truy cập chỉ để kiểm tra sự tồn tại trước khi đọc cùng hàng, rồi tiếp tục đọc lại vì dữ liệu đã bị chuyển thành một `boolean` quá sớm.

Hướng xử lý:

- Cho application service đọc **một bản dữ liệu đủ phục vụ domain policy**, thay vì mỗi policy lại tự mở repository.
- Đưa những điều kiện cần đảm bảo **ngay tại thời điểm ghi** vào một `UPDATE ... WHERE ...` nguyên tử.
- Định nghĩa rõ kết quả `not found`, `forbidden`, `condition failed` và `concurrent modification`.
- Không dùng một cache in-memory thiếu chính sách nhất quán để che giấu việc đọc lặp.

Ví dụ muốn kiểm tra “có bản ghi nào thỏa điều kiện hay không” có thể cân nhắc `EXISTS` thay vì tải mọi hàng hoặc đếm chính xác số hàng:

```sql
-- Khi chỉ cần biết có ít nhất một dòng:
SELECT EXISTS (
    SELECT 1
    FROM active_sessions
    WHERE user_id = :user_id
      AND expires_at > CURRENT_TIMESTAMP
);

-- COUNT(*) phù hợp khi thật sự cần số lượng chính xác.
SELECT COUNT(*)
FROM active_sessions
WHERE user_id = :user_id
  AND expires_at > CURRENT_TIMESTAMP;
```

Không giả định `EXISTS` luôn nhanh hơn trong mọi execution plan; thường nó thể hiện ý định **chỉ cần tìm thấy một dòng**, cho planner khả năng dừng sớm khi phù hợp.

## 8. Đọc trước khi ghi: truy cập thừa hay bảo vệ nghiệp vụ?

Một mẫu dễ gây cả dư query **và race condition**:

```text
SELECT available FROM inventory WHERE sku = :sku
nếu available >= quantity:
    UPDATE inventory
    SET available = available - :quantity
    WHERE sku = :sku
```

Hai request có thể cùng đọc tồn kho = 5 rồi cùng trừ 4. Việc giảm số query từ hai xuống một không chỉ tối ưu hiệu năng mà còn có thể **làm bất biến chắc chắn hơn** khi chuyển sang một câu cập nhật có điều kiện:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND status = 'ACTIVE'
  AND available >= :quantity;
```

Ứng dụng phải kiểm tra **số hàng cập nhật = 1**. Kết quả 0 chỉ có nghĩa điều kiện tổng không thỏa tại lúc ghi; chưa đủ để kết luận sản phẩm hết hàng hay bị ngừng bán.

Nếu yêu cầu còn phải tạo `reservations` và ghi idempotency key, các bước cần chung một transaction:

```text
BEGIN
  chặn trùng bằng UNIQUE(request_id) hoặc giao thức tương đương
  UPDATE tồn kho có điều kiện
  INSERT reservation / business result / outbox nếu cần
COMMIT
```

**Không được bỏ lượt đọc thực sự cần thiết** để tính toán chính sách phức tạp, kiểm tra quyền hoặc đối chiếu dữ liệu nếu câu `UPDATE` không thể bảo vệ đầy đủ ngữ nghĩa. Với bất biến trải nhiều hàng, cần xem isolation, lock chung hoặc transaction `SERIALIZABLE` và retry; một cập nhật tối ưu cục bộ không tự ngăn *write skew*.

Mục tiêu là **tối thiểu hóa truy cập không cần thiết mà vẫn giữ đúng quyết định nghiệp vụ**, không phải bỏ kiểm tra để đạt con số query đẹp.

## 9. Batch: tránh một network round-trip cho mỗi dòng

Một tác vụ nhập 2.000 bản ghi qua JDBC có thể thực thi 2.000 câu `INSERT` riêng biệt. Mỗi lần gửi có thể tạo overhead driver, parse/bind, mạng và database, tùy cách driver thực thi.

JDBC hỗ trợ batching:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import javax.sql.DataSource;

public final class ProductBatchWriter {
    private final DataSource dataSource;

    public record Item(String sku, String name) {}

    public ProductBatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insertItems(List<Item> items) throws SQLException {
        if (items.isEmpty()) {
            return;
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO products(sku, name) VALUES (?, ?)")) {

                int queued = 0;
                for (Item item : items) {
                    statement.setString(1, item.sku());
                    statement.setString(2, item.name());
                    statement.addBatch();

                    if (++queued == 200) {
                        statement.executeBatch();
                        statement.clearBatch();
                        queued = 0;
                    }
                }
                if (queued > 0) {
                    statement.executeBatch();
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Ví dụ dùng **batch kích thước 200 trong một transaction** cho toàn bộ danh sách; số 200 chỉ là giá trị minh họa. Driver/database có thể gửi batch theo các cách khác nhau nên **200 lượt addBatch không đồng nghĩa chắc chắn một network packet hay một SQL statement**. Phải đo round-trip và throughput thực tế.

Điểm đánh đổi:

- Transaction quá lớn có thể giữ khóa, tăng WAL/redo, memory, độ trễ commit và chi phí rollback.
- Chia transaction thành nhiều chunk giúp giảm phạm vi lỗi nhưng có thể làm thay đổi yêu cầu atomicity: import không còn “tất cả hoặc không có gì”.
- Khi gặp `BatchUpdateException`, cần xử lý kết quả theo hợp đồng driver và trạng thái transaction; không tự giả định mọi dòng đã hoặc chưa được ghi.
- Retry sau kết quả commit không rõ cần **khóa idempotency**; chạy lại cả batch với ID mới có thể tạo trùng dữ liệu.
- Trong JPA/Hibernate, chiến lược sinh ID, thứ tự insert/update, cơ chế flush và persistence context có thể ảnh hưởng khả năng batching; cần đo generated SQL và bộ nhớ.

Batching tối ưu cách **chuyển nhiều thao tác hợp lệ xuống database**, không thay thế validation, unique constraint hoặc transaction.

## 10. Chuyển vòng lặp truy vấn sang thao tác theo tập

Giả sử dịch vụ cần kiểm tra trạng thái của 300 SKU. Cách tốn kém:

```java
for (String sku : skus) {
    ProductStatus status = repository.findStatusBySku(sku);
    // ...
}
```

Nếu mỗi `findStatusBySku` là một SQL, 300 SKU tạo khoảng 300 SQL. Một cách đọc theo tập:

```sql
SELECT sku, status, available
FROM inventory
WHERE sku IN (:sku_list);
```

Ứng dụng ánh xạ kết quả sang `Map<String, ProductStatus>`, rồi đối chiếu từng SKU. Với danh sách dài, cần chia chunk hoặc dùng kỹ thuật bind tập/temporary table phù hợp DBMS và driver.

Phải xử lý chính xác:

- SKU không tồn tại: query theo tập chỉ trả hàng **được tìm thấy**, không tự tạo kết quả cho key mất.
- SKU trùng trong đầu vào: có thể trả một hàng; nếu nghiệp vụ cần nhiều vị trí đầu vào, phải giữ mapping.
- Thứ tự: SQL với `IN` không cam kết giữ thứ tự danh sách đầu vào nếu không có `ORDER BY`/cách ghép thích hợp.
- Tenant/quyền: thêm điều kiện tenant và quyền đúng phạm vi; không để batch vượt quyền giữa nhiều đối tượng.
- Dữ liệu thay đổi đồng thời: một lần truy vấn theo tập thường cho góc nhìn nhất quán hơn nhiều query rải thời gian, nhưng mức snapshot vẫn phụ thuộc isolation và DBMS.

Trong GraphQL có nhiều resolver cần dữ liệu theo ID, cơ chế tương tự *DataLoader/batch loading* giúp gom các yêu cầu trong cùng đợt xử lý. Tuy nhiên, cache/batch loader cần phạm vi request hoặc ngữ cảnh phân quyền rõ; không được lưu dữ liệu người dùng này cho người dùng khác.

## 11. Over-fetching: ít query nhưng đọc quá nhiều dữ liệu

Tối ưu đếm query mà bỏ qua lượng dữ liệu có thể đưa hệ thống từ một lỗi sang lỗi khác.

Ví dụ API chỉ cần `id, title, price` nhưng repository trả:

```sql
SELECT *
FROM products
WHERE category_id = :category_id;
```

Nếu bảng có cột mô tả rất dài, metadata JSON lớn hoặc hàng chục nghìn sản phẩm, ứng dụng sẽ đọc và deserialize nhiều dữ liệu không dùng. Một projection có giới hạn:

```sql
SELECT id, title, price
FROM products
WHERE category_id = :category_id
  AND status = 'ACTIVE'
ORDER BY updated_at DESC, id DESC
LIMIT :page_size;
```

Chi phí thường cần đo: số hàng, số byte phản hồi, thời gian driver đọc dữ liệu, heap allocation, GC và số block database phải xử lý. Câu SQL vẫn có thể phải đọc thêm dữ liệu nội bộ tùy index/plan, nhưng giảm payload là lợi ích có thể kiểm chứng.

### Join nhiều quan hệ 1-N

Giả sử 100 đơn, mỗi đơn có 10 dòng hàng và 5 ghi chú. Một query join hai collection có thể tạo:

```text
100 orders × 10 lines × 5 notes = 5.000 joined rows
```

Những dòng này lặp lại phần dữ liệu order và line, có thể gây **Cartesian product amplification**. Hai hoặc ba truy vấn theo tập có thể chuyển ít dữ liệu hơn một truy vấn cực lớn.

Khi join để tính tổng, nhớ rằng `COUNT` hoặc `SUM` cũng có thể bị nhân bởi các quan hệ 1-N khác, làm **sai kết quả nghiệp vụ**, không chỉ chậm. Giảm query count không được đánh đổi bằng đếm sai.

## 12. Cache giúp giảm truy cập, nhưng phải xét tính nhất quán

Cache ở JVM/Redis hoặc second-level cache của ORM có thể giảm số lần SQL. Tuy nhiên, **tối ưu query thừa** và **tạo một bản dữ liệu cũ** là hai quyết định khác nhau.

Ví dụ dữ liệu danh mục công khai có thể cache theo key và TTL hợp lý; nhưng tồn kho để xác nhận đơn hoặc số dư để chi tiền **không được tin từ cache hiển thị** nếu database là nguồn có thẩm quyền cho quyết định đó.

| Loại truy cập | Cache có thể giúp? | Điều phải giữ |
| --- | --- | --- |
| Danh mục ít đổi, nhiều lượt đọc | Thường có. | TTL, invalidation và fallback khi cache lỗi. |
| Một projection được nhiều request đọc lại | Có thể. | Key chứa đủ tham số, tenant và phiên bản dữ liệu cần thiết. |
| Kiểm tra tồn kho trước khi trừ | Chỉ giúp hiển thị/tham khảo. | Quyết định cuối phải được bảo vệ trong transaction/conditional write. |
| Đối soát kết quả commit không rõ | Cần đọc nguồn có thẩm quyền. | Không suy ra “chưa commit” từ cache miss hoặc replica chậm. |
| Kiểm tra quyền nhạy cảm | Cân nhắc thận trọng. | Thu hồi quyền và cách cô lập tenant; cache hit không bypass authorization. |

Cache có thể tạo **stampede**: khi key hết hạn, nhiều request đồng thời miss rồi dồn query xuống DB. Thay vì chỉ giảm số SQL ở tải bình thường, cần thử cả cache cold, eviction, Redis timeout, nhiều pod cùng miss và race nạp dữ liệu cũ sau invalidation.

### DB buffer pool không thay thế cache ứng dụng

Một query đọc block có sẵn trong PostgreSQL `shared_buffers` vẫn là **một SQL execution**. DB buffer hit giảm I/O lưu trữ, không làm query trở thành “không truy cập DB”. Vì vậy metric `blks_hit` cao không thể được dùng làm bằng chứng rằng N+1 đã biến mất.

Ngược lại, giảm SQL ở ứng dụng có thể giảm CPU DB, round-trip và số connection active ngay cả khi buffer hit ratio vốn đã rất cao.

## 13. Quan sát tại Java: đếm truy cập theo request/use case

Để tìm truy cập vượt nhu cầu, nên đo ở **ranh giới persistence** rồi gắn về một use case:

```text
HTTP / message / batch span
      |
      +-- useCase = listCustomerOrders
      +-- requestId / traceId / tenant (đã xử lý bảo mật)
      |
      +-- JDBC call #1  SELECT orders
      +-- JDBC call #2  SELECT order_lines...
      +-- JDBC call #3  SELECT order_lines...
      ...
      +-- JDBC call #51 SELECT order_lines...
      |
      +-- metrics:
             sql.executions = 51
             sql.duration.total = ...
             sql.rows.fetched = ...
             app.response.p95 = ...
```

Các hướng công cụ phù hợp:

- **SQL logging** của Hibernate, driver hoặc công cụ proxy để thấy mẫu câu SQL lặp; bật ở môi trường có kiểm soát hoặc sampling vì log đầy đủ có thể tốn chi phí.
- **Hibernate Statistics** để đo prepared statement count và entity/collection fetch trong phạm vi thích hợp.
- **DataSource instrumentation/proxy** để đếm execution, batch, thời gian SQL ở JDBC và gắn trace ID.
- **Micrometer/OpenTelemetry** để kết nối số liệu request/use case với span database; kiểm tra phiên bản instrumentation và hệ thống trace.
- **Application-level counters** cho đường đọc repository có ngữ nghĩa rõ, ví dụ `orders.loaded`, `orderLines.batchFetch`.

**Đừng log giá trị bind nhạy cảm** như mật khẩu, token, số thẻ hoặc dữ liệu cá nhân. Có thể lưu dạng query được chuẩn hóa và số lượng tham số/hàng. Cardinality của metric phải được kiểm soát: không nên dùng `requestId` hoặc SQL đầy đủ làm label của metric thời gian dài vì số series có thể bùng nổ.

### Ba lớp số liệu nên đặt cạnh nhau

| Tầng | Dữ liệu muốn biết | Lý do |
| --- | --- | --- |
| Application/JDBC | SQL executions trên một use case, round-trip, duration, rows, transaction boundary. | Phát hiện N+1, truy cập lặp và số lượng query tỷ lệ với kích thước đầu vào. |
| Connection pool | Active, idle, pending, acquisition latency, hold time. | Phân biệt xếp hàng chờ connection với SQL chạy nhiều/chậm. |
| DBMS/storage | Calls theo mẫu SQL, rows, CPU, I/O, lock waits, buffer reads, WAL. | Xác định hậu quả phía server và loại nút nghẽn. |

Một HTTP request có thể thực thi SQL từ nhiều thread hoặc nhiều service. Nếu chỉ đếm trên thread hiện tại, async callbacks có thể bị bỏ sót; nếu chỉ đếm trên DB toàn cục, khó gán số liệu cho đúng use case. Tracing và span context giúp ghép chúng nhưng cần thiết kế truyền context phù hợp.

## 14. Hibernate Statistics: công cụ phát hiện hồi quy trong test

Hibernate cung cấp API thống kê cho SessionFactory khi được bật. Ví dụ với Spring Boot và Hibernate, có thể bật thu thập thống kê trong môi trường test:

```yaml
spring:
  jpa:
    properties:
      hibernate.generate_statistics: true
```

Với ứng dụng kiểm thử tuần tự và một SessionFactory, có thể dùng:

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderQueryBudgetTest {
    // Các field này được khởi tạo/inject trong cấu hình test.
    private EntityManagerFactory entityManagerFactory;
    private OrderReadService orderReadService;

    @Test
    void listOrdersShouldNotGrowLinearlyWithOrderCount() {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics stats = sessionFactory.getStatistics();
        stats.clear();

        orderReadService.findSummaries(42L);

        long statements = stats.getPrepareStatementCount();
        assertTrue(statements <= 4,
                "Unexpected SQL executions: " + statements);
    }
}
```

Đoạn này là **khung minh họa**, không phải test chạy độc lập: cần Spring test context, dữ liệu fixture, injection, transaction boundary và chuẩn bị SessionFactory. `getPrepareStatementCount()` phản ánh số prepared statements được thống kê theo provider và cấu hình, không phải đo chính xác mọi round-trip mạng.

**Quan trọng:** Hibernate Statistics thường thuộc phạm vi **SessionFactory, không riêng một request**. Gọi `clear()` rồi đo trong test chạy song song hoặc khi thread khác cũng truy cập DB có thể cho kết quả sai. Chỉ dùng cách này trong test cô lập/tuần tự, hoặc dùng instrumentation theo từng request/span để có số liệu tốt hơn.

Một test mạnh hơn chạy cùng nghiệp vụ với **5, 20 và 50 order**, rồi khẳng định số SQL **không tăng tuyến tính với N** ngoài phạm vi được chấp nhận. Ngưỡng 4 ở trên chỉ là ví dụ cho một use case cụ thể, không phải chuẩn chung của JPA.

### Lưu ý về lazy loading và test

Trong môi trường test, cache đã được “làm nóng” hoặc persistence context đã quản lý sẵn entity có thể che mất N+1. Cần tạo dữ liệu đại diện, clear/đóng context khi phù hợp, thử cold/warm path và quan sát query thật. Trong Spring web, Open Session in View có thể khiến SQL xảy ra **lúc serialize response**, ngoài method service; phải đo cả request chứ không chỉ đoạn service.

## 15. PostgreSQL: tìm mẫu truy vấn bị gọi quá nhiều

Ở phía database, tiện ích **`pg_stat_statements`** (khi được cài đặt và kích hoạt phù hợp) giúp tổng hợp số lần thực thi, thời gian và một số bộ đếm theo mẫu câu SQL. Truy vấn minh họa:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    LEFT(query, 160) AS sample_query
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;
```

Điều cần diễn giải:

- `calls` lớn + `mean_exec_time` nhỏ có thể phản ánh một query **rất thường xuyên**; nếu là một truy vấn theo từng hàng do N+1 thì tổng chi phí đáng chú ý.
- `total_exec_time` giúp xếp thứ tự công việc database đã dùng thời gian, nhưng không đo đầy đủ **network latency hoặc thời gian chờ connection pool** phía Java.
- `rows` là tổng số dòng trả hoặc chịu tác động theo thống kê statement; cần xem đơn vị và ý nghĩa của từng loại SQL.
- `shared_blks_hit/read` giúp xem hoạt động buffer của PostgreSQL; `read` không nhất thiết đồng nghĩa physical disk I/O vì OS page cache.
- Mẫu SQL đã được chuẩn hóa giúp nhận diện truy vấn cùng hình dạng với tham số khác nhau; cần đối chiếu đúng DB/user và khoảng thời gian.

Các bộ đếm này **tích lũy** từ lần reset/thời điểm khởi tạo thống kê phù hợp. Để so sánh trước và sau tối ưu, đo delta trên cùng khoảng tải. Phiên bản PostgreSQL, extension, quyền truy cập và chính sách thu thập có thể ảnh hưởng cột/khả năng xem. Không tự bật extension hay nâng quyền production khi chưa theo quy trình vận hành.

**Giới hạn:** database thấy nhiều calls cho một query không tự chứng minh query đó là dư thừa. Có thể đây là truy vấn đúng do hệ thống phục vụ rất nhiều request. Cần **ghép với trace/use case và N đầu vào** để xác nhận nguyên nhân.

### EXPLAIN cho câu SQL nghi vấn

Nếu đã xác nhận một SQL vừa bị gọi nhiều vừa đắt:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

Đọc execution plan, hàng ước lượng/thực tế, thời gian, hoạt động buffer và index. `ANALYZE` **thực thi câu SQL thật**; với `UPDATE/DELETE/INSERT`, phải dùng môi trường hoặc transaction kiểm soát để tránh tác dụng phụ ngoài ý muốn.

Giảm số query và tối ưu **mỗi query còn lại** là hai việc bổ sung cho nhau. Sửa N+1 nhưng query tải theo tập thiếu index vẫn có thể chậm.

## 16. Phân biệt lượt truy cập nhiều với connection pool quá nhỏ

Hai dấu hiệu dễ bị nhầm:

**Trường hợp A — N+1:** mỗi request thực hiện 100 SQL liên tiếp trên một connection. Thời gian giữ connection kéo dài, số query/giây tăng và pool có thể hết slot khi tải cao.

**Trường hợp B — database bão hòa:** mỗi request chỉ chạy một truy vấn nặng nhưng rất nhiều request đồng thời; pool vẫn có thể chờ vì DB CPU, I/O hoặc khóa chậm.

Nếu chỉ tăng `maximumPoolSize`, trường hợp A có thể tạm giảm thời gian chờ mượn nhưng lại đưa **nhiều chuỗi 100 SQL** vào DB; trường hợp B có thể tăng tranh chấp hơn nữa.

Một số dấu hiệu:

| Quan sát | Giả thuyết cần kiểm tra | Ưu tiên |
| --- | --- | --- |
| SQL/request tăng gần bằng số phần tử | N+1 hoặc truy vấn trong vòng lặp. | Trace theo use case, batch/fetch đúng phạm vi. |
| SQL/request ít nhưng DB CPU cao | Query nặng, plan/index hoặc số hàng lớn. | EXPLAIN, indexing, projection, resource profile. |
| Pool pending cao, hold time dài, SQL count cao | Nhiều round-trip hoặc transaction quá dài. | Giảm truy cập thừa, rút ngắn transaction. |
| Pool pending cao, SQL count thấp, nhiều lock wait | Contention hoặc giao dịch giữ khóa. | Xem lock/transaction design, không chỉ tăng pool. |
| Redis hit cao nhưng DB vẫn bị dồn tải lúc TTL hết | Cache stampede hoặc cache miss đồng loạt. | Coalescing, jitter, giới hạn fallback. |
| DB buffer hit cao nhưng request chậm | SQL vẫn tốn CPU/round-trip/mapping. | Đo query count, rows, CPU và network. |

**Một connection đang active không đồng nghĩa một SQL đang chạy.** Connection có thể bị giữ khi code Java xử lý kết quả hoặc chờ một API khác. Do đó thời gian giữ connection và số SQL thực thi phải được đo riêng.

## 17. Một quy trình điều tra có thể lặp lại

Khi một endpoint chậm và nghi truy cập database quá nhiều, hãy đi theo thứ tự:

1. **Xác định use case và kết quả cần trả.** Ví dụ “trang 25 đơn, ID, trạng thái, số dòng”; không bắt đầu bằng ý định “bỏ ORM”.
2. **Đo baseline dưới dữ liệu đại diện.** SQL count/request, round-trip, latency p50/p95/p99, rows, DB CPU/I/O, pool wait và hold time.
3. **Phân loại SQL.** Đọc cần thiết, ghi nghiệp vụ, kiểm tra cạnh tranh, audit/outbox, truy vấn lặp, lazy load hoặc dữ liệu không dùng.
4. **Thử N khác nhau.** Với trang 5/25/50 phần tử, SQL count có tăng theo N không?
5. **Tìm call site.** Ghép normalized SQL với trace/span và đoạn gọi repository, mapper DTO hoặc serializer.
6. **Chọn phép biến đổi nhỏ nhất an toàn.** Projection, fetch plan, batch fetch, bulk-by-ID, query aggregate hay conditional update.
7. **Kiểm chứng tính đúng đắn.** So JSON/ngữ nghĩa, quyền, pagination, count, kết quả khi dữ liệu đổi đồng thời, retry/idempotency.
8. **Đo lại trên cùng workload và topology.** So cả query count, rows/bytes, throughput, latency và CPU/heap.
9. **Thêm regression test và metric.** Query budget gắn use case, cảnh báo theo tỷ lệ SQL/record hoặc p95 tăng bất thường.

Trong quá trình thử, nên giữ nguyên index/schema/dữ liệu/số pod/connection budget để giảm nhiễu. Nếu đồng thời thay cache, index, code và hạ tầng, rất khó biết thay đổi nào đem lại hiệu quả hoặc tạo lỗi.

### Ví dụ bảng kết quả thử nghiệm giả định

| Phương án | SQL/request | Rows trả từ DB | p95 request | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| ORM lazy từng order | 51 | 170 | 340 ms | N+1 rõ với 50 đơn. |
| Join tất cả order + lines | 1 | 1.900 | 290 ms | Ít SQL nhưng payload quá lớn. |
| Trang parent + bulk aggregate | 3 | 100 | 95 ms | Giữ số SQL thấp và payload vừa đủ. |

Đây là **dữ liệu minh họa, không phải phép đo thực tế**. Cần thay số bằng kết quả benchmark từ môi trường của dự án trước khi khẳng định một phương án tốt hơn.

## 18. Kiểm thử đúng đắn sau khi gộp truy vấn

Tối ưu hiệu năng không phải chỉ là phép biến đổi cú pháp. Những lỗi có thể phát sinh:

- **Bỏ sót phân quyền:** bulk query bỏ điều kiện `tenant_id` hoặc trả thông tin mà repository từng lọc ở từng hàng.
- **Sai phân trang:** join collection làm duplicate parent hoặc áp dụng `LIMIT` lên hàng join thay vì số entity gốc.
- **Sai aggregation:** join nhiều bảng 1-N làm nhân bản các phần tử khi `COUNT/SUM`.
- **Thiếu hàng kết quả:** query `IN (...)` bỏ qua ID không tồn tại, ứng dụng ngầm giả định thứ tự và đủ số hàng.
- **Thay đổi độ mới dữ liệu:** nhiều query trong `READ COMMITTED` có thể thấy snapshot khác nhau; gộp thành một query thay đổi thời điểm quan sát.
- **Bỏ kiểm soát đồng thời:** bỏ lượt đọc/câu khóa cần thiết mà không có guard hoặc isolation tương ứng.
- **Giao dịch quá dài:** một SQL lớn hoặc batch lớn giữ khóa và connection lâu hơn.
- **Cập nhật sai version:** bulk JPQL/native SQL không tự vận hành `@Version` như update entity thông thường.
- **Mất trạng thái commit:** tự retry sau timeout mà không có idempotency key hoặc đối soát.

Nên có **integration test với database thật** cho những thay đổi liên quan concurrency, isolation, unique constraint và transaction. Unit test của repository mock không tái hiện đầy đủ khóa, snapshot hoặc lỗi commit không rõ.

### Mẫu test nhận diện N+1 theo đầu vào

```text
Fixture:
  tạo 5, 25, 50 orders, mỗi order có lines/customer

For each N:
  làm sạch context/cache kiểm thử theo chính sách
  bắt đầu đo SQL executions trong phạm vi use case
  gọi API/service để lấy N orders
  xác nhận DTO đúng và phân trang đúng
  ghi number_of_queries(N), rows(N), duration(N)

Kỳ vọng của thiết kế bulk:
  number_of_queries(50) không tăng gần tuyến tính so với (5)

Kỳ vọng nghiệp vụ:
  không thiếu/cộng trùng orders hoặc lines,
  không rò rỉ dữ liệu tenant,
  trạng thái và tổng tính đúng.
```

Hãy dùng ngưỡng test có lý do theo fetch plan. Việc dùng `@DataJpaTest` hoặc in-memory database không tự bảo đảm behavior của PostgreSQL/MySQL giống production; khi kiểm thử SQL dialect, locking, plan hoặc JDBC batching, cần môi trường tích hợp chạy đúng DBMS mục tiêu.

## 19. Case study: từ một trang đơn hàng 101 SQL xuống mô hình ổn định

Một nhóm nhận phản ánh trang “50 đơn gần đây” chậm khi khách có nhiều đơn. Ban đầu:

```text
1 SQL: SELECT 50 orders
50 SQL: SELECT customer info cho từng order
50 SQL: SELECT line count cho từng order
---------------------------------------------
101 SQL executions / trang 50 đơn
```

**Bước 1 — xác định dữ liệu cần:** response chỉ chứa order ID, thời gian tạo, trạng thái, tên khách và tổng số dòng. Không cần toàn bộ object Customer hoặc tất cả OrderLine.

**Bước 2 — đo theo quy mô:** trang 10 đơn ≈ 21 SQL, trang 50 đơn ≈ 101 SQL. Đây là tín hiệu truy vấn tăng theo N, không phải chỉ một query chậm.

**Bước 3 — phân tách phần truy vấn có thể gộp:** tìm 50 order IDs bằng một query trang; lấy tên khách qua join/projection phù hợp; lấy `COUNT(*) GROUP BY order_id` cho tập ID đã chọn.

**Bước 4 — giữ điều kiện:** mọi query vẫn lọc đúng customer/tenant, sắp xếp ổn định và dùng mapping theo ID; số dòng bằng 0 được biểu diễn 0 thay vì bỏ mất đơn khỏi response.

**Bước 5 — xác minh:** thêm integration test cho các trang 10/50, order không có dòng, nhiều order cùng customer, tenant khác và dữ liệu thay đổi đồng thời theo hợp đồng đọc đã định nghĩa.

Kết quả có thể giảm xuống khoảng **2–3 SQL/trang**, tùy cách triển khai và việc API có cần tổng số trang hay không. Nhưng chỉ chấp nhận thay đổi khi đo được p95, bytes, DB work và kết quả nghiệp vụ không bị suy giảm.

Một đoạn service dùng port có ngữ nghĩa:

```java
public record OrderRow(long id, long customerId, String status) {}
public record OrderPageLineCount(long orderId, long lineCount) {}

public interface OrderPageReader {
    java.util.List<OrderRow> loadOrderPage(long customerId, int limit);

    // Một thao tác theo tập, không gọi từng orderId.
    java.util.Map<Long, Long> countLinesForOrders(
            java.util.List<Long> orderIds);
}

public final class OrderPageUseCase {
    private final OrderPageReader reader;

    public OrderPageUseCase(OrderPageReader reader) {
        this.reader = reader;
    }

    public java.util.Map<Long, Long> loadCounts(long customerId) {
        var orders = reader.loadOrderPage(customerId, 50);
        if (orders.isEmpty()) {
            return java.util.Map.of();
        }

        var ids = orders.stream().map(OrderRow::id).toList();
        var counts = reader.countLinesForOrders(ids);

        var result = new java.util.LinkedHashMap<Long, Long>();
        for (OrderRow order : orders) {
            result.put(order.id(), counts.getOrDefault(order.id(), 0L));
        }
        return result;
    }
}
```

Đây là **mẫu thiết kế port/use case**, không phải ứng dụng hoàn chỉnh. Repository hiện thực `countLinesForOrders(...)` bằng một query group theo tập ID; nếu method đó lén gọi một query cho từng ID, N+1 vẫn tồn tại dù giao diện nhìn có vẻ “bulk”. Cần test ở tầng adapter thật.

## 20. Checklist nhanh trước khi kết luận một query là dư thừa

| Câu hỏi | Vì sao cần hỏi? |
| --- | --- |
| Query này phục vụ dữ liệu nào trong response hoặc bất biến nào? | Tránh bỏ một kiểm tra đúng đắn. |
| Nó có chạy trong vòng lặp theo số entity không? | Tìm N+1 hoặc truy cập tuyến tính. |
| Có bị gọi lại với cùng key trong một use case không? | Tìm đọc trùng giữa controller/service/repository. |
| Có thể dùng projection/aggregate/bulk fetch không? | Giảm payload hoặc round-trip. |
| Một query join có nhân số hàng hoặc làm sai `COUNT/SUM` không? | Tránh over-fetch và sai kết quả. |
| Đường ghi có cần conditional update, version hoặc lock không? | Bảo vệ concurrency trước khi tối ưu. |
| DataSource/proxy/ORM có thực sự gửi SQL ở runtime không? | Không suy từ số method call. |
| Có nhầm cache hit với DB buffer hit không? | Biết tầng nào giảm công việc. |
| Có đo p95/p99, rows/bytes, pool wait và server resource không? | Tránh tối ưu một chỉ số mà làm chậm hệ thống. |
| Có test tenant, pagination, retry, commit không rõ và concurrency không? | Bảo đảm kết quả nghiệp vụ sau thay đổi. |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** API lấy 100 đơn hàng bằng một query, rồi gọi một query lấy chi tiết cho từng đơn. Đây là dấu hiệu gì?

**N+1 query**: khoảng 101 SQL executions. Cần đo runtime và xem bulk loading, projection hoặc fetch strategy phù hợp.

**Câu 2.** Sau khi tối ưu, số SQL giảm từ 101 xuống 1 nhưng rows trả về tăng từ 300 lên 30.000. Có chắc đã tốt hơn không?

**Không.** Query join có thể làm nhân hàng và tăng dữ liệu truyền, CPU mapping và memory. Phải đo tổng chi phí và xác minh kết quả không sai.

**Câu 3.** PostgreSQL buffer hit ratio là 99%. Có thể kết luận ứng dụng không gặp N+1 không?

**Không.** Buffer hit đo truy cập block trong database, còn N+1 là nhiều SQL phát sinh từ ứng dụng. Một trăm query đều đọc buffer hit vẫn là một trăm query.

**Câu 4.** Vì sao chỉ mock repository trong unit test thường không chứng minh được đã sửa N+1?

Vì mock không thực thi SQL thực, ORM lazy loading, fetch plan, pagination hoặc mapping. Cần đo trong integration test có database phù hợp.

**Câu 5.** Có nên bỏ `SELECT` trước `UPDATE` trong mọi trường hợp để giảm một query?

**Không.** Có trường hợp cần dữ liệu để đánh giá chính sách hoặc lấy khóa. Nếu chỉ cần bảo vệ điều kiện trên một hàng, conditional update có thể giảm round-trip và ngăn race; vẫn phải xác nhận kết quả và giữ transaction phù hợp.

**Câu 6.** Tại sao batch 2.000 dòng không có nghĩa là 2.000 dòng đã được commit ngay sau `executeBatch()`?

Vì còn phụ thuộc transaction và thời điểm `commit()`; batch có thể gặp lỗi, rollback hoặc kết quả commit chưa rõ. Mức giảm round-trip cũng phụ thuộc driver/database.

**Câu 7.** Một truy vấn được gọi 1 triệu lần/giờ trong `pg_stat_statements` có chắc là truy cập dư thừa không?

**Chưa chắc.** Đó có thể là một truy vấn hợp lệ cho lượng request lớn. Cần tương quan theo use case, số SQL/request, kích thước đầu vào và mục đích của query.

**Câu 8.** Tối ưu query count có thể gây vi phạm bảo mật như thế nào?

Ví dụ một truy vấn bulk thiếu điều kiện `tenant_id` hoặc cache dùng chung trả dữ liệu khác tenant. Mọi đường query mới phải giữ đủ bộ lọc quyền và được kiểm thử.

## Kết luận

**Phát hiện số lần truy cập vượt nhu cầu nghiệp vụ** là quá trình so sánh **dữ liệu/bảo đảm mà một use case cần** với **số lần SQL, round-trip, hàng và tài nguyên thực sự tiêu thụ**. Những dấu hiệu như N+1, kiểm tra lặp, truy vấn trong vòng lặp và ghi từng dòng thường chỉ lộ rõ khi đo ở ranh giới request/use case kết hợp quan sát database.

Trong Java, hãy dùng SQL instrumentation, Hibernate Statistics, tracing và thống kê DBMS để xác định nguyên nhân; sau đó cân nhắc projection, bulk fetch, aggregate, batch và cập nhật có điều kiện. Không chạy theo mục tiêu “càng ít query càng tốt” nếu làm sai pagination, phân quyền, concurrency, transaction hoặc kết quả ghi. **Tối ưu persistence tốt là giảm công việc không cần thiết trong khi vẫn chứng minh được tính đúng đắn và lợi ích hiệu năng bằng phép đo có thể lặp lại.**
