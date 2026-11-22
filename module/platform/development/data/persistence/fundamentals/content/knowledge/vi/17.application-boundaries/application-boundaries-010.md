# Phân biệt trừu tượng hóa hữu ích với che giấu chi phí truy vấn

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích vai trò của repository/DAO, ORM và các giao diện truy cập dữ liệu trong việc tách logic nghiệp vụ khỏi chi tiết lưu trữ.
2. Nhận diện lúc một API “đơn giản” tạo ra **nhiều câu SQL, đọc thừa hàng/cột, truy vấn ẩn hoặc transaction kéo dài**.
3. Phân tích **N+1 query**, lazy/eager loading, join có số hàng nhân lên, phân trang, streaming, cache và các giới hạn của abstraction.
4. Thiết kế phương thức persistence công khai rõ về kết quả, giới hạn số hàng, phạm vi transaction và kỳ vọng chi phí.
5. Quan sát SQL thực, dùng `EXPLAIN (ANALYZE, BUFFERS)`, metrics và integration test để chọn phương án phù hợp với workload.
6. Giữ tính đúng đắn và bảo mật khi tối ưu: ràng buộc tenant, tính nhất quán giữa nhiều lần đọc, transaction, retry và giới hạn dữ liệu nhạy cảm.

Bài thuộc chương **Ranh giới ứng dụng** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module nghiên cứu lưu trữ bền vững từ mô hình dữ liệu, lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập và kiểm soát đồng thời. Trong Java, người học cần thiết kế ranh giới persistence sao cho mã nghiệp vụ dễ hiểu **và** người vận hành vẫn nhìn thấy chi phí, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Trừu tượng hóa hữu ích là gì?

Một abstraction tốt giúp thành phần gọi tập trung vào điều nghiệp vụ muốn làm, thay vì biết mọi chi tiết JDBC và SQL. Chẳng hạn, service chỉ cần yêu cầu:

~~~java
List<OrderSummary> recentOrders(long tenantId, int limit);
~~~

Thay vì tự mở connection, bind tham số, quản lý `ResultSet` và chuyển hàng thành DTO ở nhiều vị trí trong code. Giao diện này che giấu **cách thực thi**, nhưng vẫn nói rõ:

- Loại dữ liệu được trả về: `OrderSummary`, không phải toàn bộ cây entity.
- Phạm vi: đơn hàng của một tenant đã được xác thực quyền truy cập.
- Giới hạn: số hàng tối đa do tham số `limit` quy định và phía server phải kiểm tra.
- Ngữ nghĩa: “recent” cần một thứ tự ổn định, ví dụ `created_at DESC, id DESC`.

Repository có thể dùng JDBC, JPA/Hibernate hoặc công nghệ khác. Nếu nhiều thành phần trong hệ thống phải biết cách đóng statement, xử lý `SQLException` hoặc ánh xạ schema, abstraction chưa thực hiện tốt trách nhiệm cô lập hạ tầng.

Tuy nhiên, **che giấu chi phí truy vấn** là khi cùng một lời gọi trông như thao tác rẻ nhưng có thể tạo hàng trăm truy vấn, tải hàng triệu bản ghi, hoặc giữ kết nối trong khi xử lý dữ liệu ở tầng ứng dụng.

| Abstraction hữu ích | Abstraction che giấu chi phí |
| --- | --- |
| `findRecentSummaries(tenantId, limit)` trả DTO và có giới hạn | `findAll()` rồi dùng Java lọc, sắp xếp và lấy 20 phần tử |
| `countPending(tenantId)` trả một giá trị tổng hợp | Đọc toàn bộ đơn hàng, dựng entity rồi đếm trong heap |
| `loadOrderDetails(orderId)` nói rõ lấy chi tiết | `getOrder()` trả entity rồi serialization tự duyệt nhiều quan hệ lazy |
| `reserveStock(id, quantity)` dùng UPDATE có điều kiện | `getStock()` rồi sửa object và ngầm hy vọng không có lost update |
| Phương thức nêu rõ ranh giới transaction hoặc giao cho service sở hữu | Repository âm thầm mở/commit transaction phụ trong một nghiệp vụ lớn |
| SQL và số hàng/cột có thể đo, giải thích được | Chi phí thay đổi bất ngờ khi tăng số phần tử, thêm serializer hoặc bật cache |

**Mục tiêu không phải viết càng nhiều SQL thuần càng tốt.** Mục tiêu là API cung cấp đúng hành vi nghiệp vụ, đồng thời giữ khả năng xem xét số lần round trip, lượng dữ liệu và tác động của câu SQL tới database.

## 2. Chi phí một truy vấn gồm những phần nào?

Độ trễ đọc dữ liệu thường không chỉ là thời gian “DB chạy SELECT”. Một mô hình trực giác:

~~~text
Thời gian gọi persistence
    = chờ mượn connection
    + truyền request / response qua mạng
    + parse/plan/execute SQL ở DB
    + CPU, I/O, sort, join, lock wait
    + truyền các hàng kết quả
    + chuyển dữ liệu thành object/DTO
    + thời gian giữ connection và xử lý liên quan
~~~

Các phần có thể chồng lấp trong thực tế; đây là danh mục cần quan sát, không phải công thức cộng chính xác cho mọi driver. Khi một operation gọi nhiều SQL nối tiếp, **round-trip latency** có thể lặp lại ở từng lần gọi, ngay cả khi từng SQL riêng lẻ rất nhanh.

Chi phí cũng có nhiều chiều:

| Chi phí | Câu hỏi cần đặt |
| --- | --- |
| Số câu SQL | Một API call tạo bao nhiêu statement trên mỗi đường đi, trong trường hợp cache lạnh và ấm? |
| Số hàng được DB đọc/xử lý | SQL scan bao nhiêu hàng, join và sort bao nhiêu dữ liệu trước khi áp dụng LIMIT? |
| Số hàng/cột truyền về | Có trả nhiều thông tin hơn màn hình/API cần không? |
| I/O và bộ nhớ cache | Có dùng index phù hợp, buffer hit/read ra sao? |
| Phân bố độ trễ | p95/p99 có tăng khi tenant lớn hoặc tải đồng thời cao không? |
| Chi phí ghi | ORM có phát nhiều INSERT/UPDATE, flush không cần thiết, hay duy trì quá nhiều chỉ mục không? |
| Tài nguyên kết nối/transaction | Connection có bị giữ lâu, gây cạn pool hoặc tăng lock contention không? |
| Độ đúng đắn | Hai lần đọc có cần cùng snapshot? Điều kiện bảo mật theo tenant còn được áp dụng không? |

Một lời gọi repository không tương đương một truy vấn. Ngược lại, **một SQL duy nhất cũng không bảo đảm rẻ**: có thể join nhân số hàng, sort tập dữ liệu khổng lồ, chạy hàm đắt tiền, hoặc trả lượng dữ liệu quá lớn.

## 3. Ví dụ xuyên suốt: API danh sách đơn hàng

Giả sử hệ thống Java có lược đồ PostgreSQL đơn giản:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

API yêu cầu trả về **20 đơn mới nhất của một tenant**, mỗi đơn gồm ID, thời điểm, tổng tiền và số dòng hàng. Màn hình **không cần** từng `OrderItem` riêng lẻ.

Một truy vấn hiệu quả cần thể hiện đúng nhu cầu: giới hạn 20 đơn trước, sau đó tính số item của những đơn này, chỉ trả bốn trường cần thiết. Chúng ta sẽ so sánh những cách abstraction có thể thực hiện yêu cầu đó.

### 3.1. Cách dễ viết nhưng có thể tải thừa dữ liệu

~~~java
// Pseudocode Java; findAll() ở đây giả định tải toàn bộ entity.
return orderRepository.findAll().stream()
        .filter(order -> order.getTenantId() == tenantId)
        .sorted(comparingCreatedAtAndIdDescending())
        .limit(20)
        .map(this::toSummary)
        .toList();
~~~

Ngay cả khi mã chỉ vài dòng, nó có thể:

- Nạp mọi đơn hàng của mọi tenant từ DB vào Java, tiêu tốn bộ nhớ và băng thông.
- Lọc, sắp xếp và giới hạn **sau** khi dữ liệu đã được tải.
- Gây lỗi phân quyền nếu code path khác vô tình trả entity trước khi lọc tenant.
- Gây thêm truy vấn từ `toSummary()` khi hàm này gọi `order.getItems()` trên quan hệ lazy.
- Giữ transaction/connection lâu hơn, giảm năng lực xử lý request đồng thời.

Số lượng dòng Java không đại diện cho số lượng công việc database phải làm. Điều kiện `WHERE tenant_id = ?`, `ORDER BY` và `LIMIT` nên được đẩy xuống truy vấn DB khi semantics cho phép.

## 4. N+1 query: một abstraction gọi tiếp nhiều truy vấn

Giả sử JPA có `OrderEntity` với tập `items` được ánh xạ lazy. Code dạng sau rất dễ xuất hiện:

~~~java
List<OrderEntity> orders = entityManager.createQuery(
        """
        SELECT o
        FROM OrderEntity o
        WHERE o.tenantId = :tenantId
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderEntity.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(20)
    .getResultList();

for (OrderEntity order : orders) {
    int count = order.getItems().size();
    // Đưa count và thông tin order vào DTO...
}
~~~

Nếu các collection chưa được nạp và cấu hình fetch thông thường yêu cầu truy vấn riêng, có thể phát sinh:

~~~text
1  SELECT tìm 20 đơn mới nhất
20 SELECT tìm items theo từng order_id
--------------------------------------
21 lượt SQL cho một API request
~~~

Đây là **N+1 query**: một truy vấn lấy danh sách cha, thêm N truy vấn để lấy dữ liệu liên quan từng cha. Khi màn hình lấy 50 đơn, số lượt có thể tăng lên 51. Số thực tế phụ thuộc mapping, fetch strategy, cache, batch size và cách provider hiện thực; **không phải lúc nào cũng đúng N+1**. Vì vậy cần quan sát SQL thực thay vì kết luận chỉ từ annotation `LAZY`.

Nếu mỗi round trip DB mất 3 ms, riêng 21 lượt truy vấn tuần tự có thể gây độ trễ mạng đáng kể so với một vài lượt truy vấn. Đây là con số **minh họa**, không phải phép đo và không bao gồm CPU, join, truyền payload hoặc trạng thái cache.

### 4.1. Vì sao lazy loading vẫn hữu ích?

Lazy loading trì hoãn tải dữ liệu quan hệ cho đến khi thật sự cần. Với trang chỉ hiển thị thông tin đơn hàng mà **không đọc items**, nó có thể tránh tải thừa rất hiệu quả. Vấn đề là **vị trí và số lần** dữ liệu lazy được kích hoạt có thể không rõ ràng ở tầng gọi.

Ví dụ, serialization JSON tự đi qua `order.getItems()` có thể kích hoạt truy vấn ngoài dự kiến, hoặc ném lỗi khi persistence context đã đóng. Bật Open Session in View để tránh lỗi lazy-loading có thể khiến DB access xảy ra ngay khi controller/serializer dựng response, làm ranh giới truy vấn và thời gian giữ session khó quan sát.

Không nên mặc định đổi tất cả quan hệ thành `EAGER`. Cách đó có thể tải quá nhiều dữ liệu, sinh join rộng, nhiều truy vấn phụ hoặc các vấn đề khác theo mapping/provider.

### 4.2. Có thể sửa N+1 bằng những cách nào?

| Phương án | Ý nghĩa | Cần đánh giá |
| --- | --- | --- |
| DTO/projection theo truy vấn | Chỉ lấy các trường và aggregate cần cho màn hình | SQL phức tạp hơn, mapping DTO phải được quản lý |
| Fetch join/entity graph | Tải trước quan hệ cần dùng | Với collection có thể nhân số hàng, trùng dữ liệu; phân trang cần đặc biệt cẩn thận |
| Batch fetching | Gom tải nhiều quan hệ lazy thành một số ít SELECT theo nhóm ID | Phụ thuộc provider, cấu hình và kích thước batch |
| Hai bước: lấy IDs đã phân trang, rồi tải quan hệ bằng `IN (...)` | Tách giới hạn tập cha và tải dữ liệu liên quan | Hai lượt SQL, cần xử lý sắp xếp và snapshot |
| Cache theo khóa | Giảm truy vấn lặp cho dữ liệu ít đổi | Invalidation, TTL, tính nhất quán và áp lực bộ nhớ |

Không phải phương án nhiều bảng JOIN luôn nhanh nhất. Một `JOIN FETCH` qua collection có thể trả một hàng SQL cho mỗi item, lặp dữ liệu của order. Với nhiều collection, join fan-out có thể bùng nổ; việc phân trang trực tiếp trên collection fetch join trong JPA/Hibernate còn có thể khiến provider cảnh báo hoặc phân trang trong bộ nhớ tùy cấu hình. **Không suy ra `setMaxResults(20)` chắc chắn chỉ tải 20 order ở DB nếu có collection fetch join.**

## 5. Một phương án SQL theo nhu cầu của màn hình

Với mục tiêu chỉ lấy **số dòng item** cho mỗi đơn, không cần dựng toàn bộ `OrderItem`. Trong PostgreSQL có thể giới hạn đơn hàng trước rồi aggregate:

~~~sql
SELECT o.id,
       o.created_at,
       o.total_amount,
       COUNT(oi.id) AS item_count
FROM (
    SELECT id, created_at, total_amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY created_at DESC, id DESC
    LIMIT ?
) AS o
LEFT JOIN order_items AS oi ON oi.order_id = o.id
GROUP BY o.id, o.created_at, o.total_amount
ORDER BY o.created_at DESC, o.id DESC;
~~~

Ưu điểm:

- `tenant_id` được lọc ở DB.
- Chọn 20 order gần nhất **trước** khi join với `order_items`.
- Không chuyển mọi trường của `order_items` về Java.
- Chỉ trả các trường cần cho response; `COUNT(oi.id)` là 0 với order không có item nhờ `LEFT JOIN`.

Một vài chỉ mục **ứng viên** đáng đo:

~~~sql
CREATE INDEX idx_orders_recent_per_tenant
ON orders (tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_order_items_by_order
ON order_items (order_id);
~~~

Khóa chính `orders.id` đã được lập chỉ mục ở PostgreSQL. Chỉ mục trên `order_items.order_id` có thể giúp DB truy cập các item theo order ID; nó **không tự được tạo trong PostgreSQL chỉ vì cột này là khóa ngoại**. Các chỉ mục vẫn tăng chi phí ghi và dung lượng, nên cần đo workload thực trước khi thêm.

SQL trên là **một lựa chọn**. Nếu 20 đơn mỗi đơn có hàng trăm nghìn item, việc đếm trực tiếp từ bảng item có thể vẫn tốn nhiều đọc; khi dữ liệu và yêu cầu phù hợp, có thể cân nhắc lưu số đếm được duy trì có kiểm soát, materialized view hoặc chiến lược tổng hợp riêng. Mỗi cách đổi chi phí đọc lấy chi phí ghi và phức tạp nhất quán.

### 5.1. Repository Java/JDBC có chi phí rõ ràng

Ví dụ sử dụng Java 17, `DataSource` và một truy vấn chứa điều kiện lọc, sắp xếp, giới hạn:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderSummaryRepository {
    public record OrderSummary(
            long id,
            Instant createdAt,
            BigDecimal totalAmount,
            long itemCount) {}

    private final DataSource dataSource;

    public OrderSummaryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> recent(long tenantId, int requestedLimit)
            throws SQLException {
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        String sql = """
            SELECT o.id, o.created_at, o.total_amount,
                   COUNT(oi.id) AS item_count
            FROM (
                SELECT id, created_at, total_amount
                FROM orders
                WHERE tenant_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            ) AS o
            LEFT JOIN order_items AS oi ON oi.order_id = o.id
            GROUP BY o.id, o.created_at, o.total_amount
            ORDER BY o.created_at DESC, o.id DESC
            """;

        List<OrderSummary> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setInt(2, limit);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    result.add(new OrderSummary(
                            rows.getLong("id"),
                            rows.getTimestamp("created_at").toInstant(),
                            rows.getBigDecimal("total_amount"),
                            rows.getLong("item_count")));
                }
            }
        }
        return result;
    }
}
~~~

Repository này làm rõ rằng API trả **tối đa 100 bản tóm tắt**, không sinh entity collection cần được lazy load sau đó. `try-with-resources` giải phóng `ResultSet`, statement và connection sau khi dữ liệu đã được materialize. Không nên trả `ResultSet` hoặc stream gắn trực tiếp với connection ra controller nếu chưa thiết kế vòng đời tài nguyên rõ ràng.

Ví dụ không có mã xác thực quyền: phía service phải bảo đảm người gọi được phép truy cập tenant đó, hoặc áp dụng cơ chế phân quyền ở DB. Bind tham số SQL chống injection, **không thay thế authorization**.

### 5.2. Chi phí của một SQL cũng cần được kiểm chứng

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at, o.total_amount,
       COUNT(oi.id) AS item_count
FROM (
    SELECT id, created_at, total_amount
    FROM orders
    WHERE tenant_id = 42
    ORDER BY created_at DESC, id DESC
    LIMIT 20
) AS o
LEFT JOIN order_items AS oi ON oi.order_id = o.id
GROUP BY o.id, o.created_at, o.total_amount
ORDER BY o.created_at DESC, o.id DESC;
~~~

Quan sát plan có thể thấy `Index Scan`, `Nested Loop`, `Hash Join`, `Aggregate` và các bước `Sort`; không nên dự đoán chắc engine sẽ chọn loại nào. Đánh giá `actual rows`, `Buffers: shared hit/read`, `Execution Time`, ước lượng số hàng và việc truy cập bảng. `EXPLAIN ANALYZE` **thực thi truy vấn thật**; ví dụ là SELECT, nhưng vẫn tốn tài nguyên và cần sử dụng cẩn thận trên hệ thống đang chịu tải.

Điều cần đo là tổng chi phí **của API**, gồm thời gian mượn connection, statement, network và object mapping, không chỉ thời gian DB của một SQL.

## 6. Trừu tượng hóa làm mất khả năng nhìn thấy phân trang

Một kiểu mã nguy hiểm:

~~~java
List<OrderEntity> orders = repository.findAll();
return orders.stream()
        .filter(o -> o.getTenantId() == tenantId)
        .limit(20)
        .toList();
~~~

`limit(20)` ở Java chỉ áp dụng sau khi `findAll()` trả kết quả. Nó không giới hạn số hàng cơ sở dữ liệu phải tải. Với dữ liệu lớn, nó có thể tăng heap, tạo GC pressure và giữ connection lâu.

Ở DB, cần `WHERE`, `ORDER BY`, `LIMIT`/paging tương ứng. Thứ tự phải ổn định khi nhiều hàng có cùng thời gian, ví dụ:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000;
~~~

`OFFSET` cao có thể khiến DB vẫn phải duyệt/bỏ qua nhiều hàng trước khi trả kết quả, và dữ liệu được thêm/xóa giữa các lần lấy trang có thể gây trùng/bỏ sót. Với danh sách “mới nhất” có thể dùng **keyset pagination**:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Đối với PostgreSQL, phép so sánh hàng `(created_at, id) < (?, ?)` phù hợp thứ tự giảm dần ở ví dụ khi khóa so sánh không NULL; các tham số biểu diễn **cursor** của hàng cuối trên trang trước. Trang đầu không dùng điều kiện cursor. Nếu nghiệp vụ đòi một snapshot cố định trong suốt quá trình phân trang, keyset tự nó **không tạo một snapshot xuyên nhiều request**; cần xác định riêng hành vi khi có dữ liệu mới hoặc được sửa.

Repository hữu ích có thể công khai `findRecentAfter(tenantId, cursor, pageSize)`, thay vì chỉ `findAll()` và buộc caller tự phân trang theo object.

## 7. Một abstraction ngắn có thể làm dữ liệu bị tải lặp nhiều lần

### 7.1. ORM dirty checking và flush

Trong transaction do JPA quản lý, thay đổi field của managed entity có thể được ORM theo dõi và đồng bộ xuống DB khi flush. Điều này giảm mã UPDATE thủ công và giúp mô hình domain tự nhiên hơn. Tuy nhiên:

- `persist()` không đồng nghĩa SQL đã được gửi hoặc transaction đã commit.
- `flush()` có thể phát nhiều INSERT/UPDATE tùy persistence context và mapping.
- `flush()` không tương đương COMMIT và không bảo đảm durability sau crash.
- Một thao tác với cascade và quan hệ lớn có thể sinh nhiều SQL hơn người gọi dự đoán.
- Nếu bật tính năng tạo log SQL, **cần kiểm tra số statement thực** thay vì chỉ số entity được thao tác.

Ví dụ một request “cập nhật đơn” có thể thay đổi trạng thái một hàng, nhưng nếu code thay cả collection item rồi gọi `save()`, ORM có thể phát nhiều câu SQL trên bảng con tùy mapping/cascade/orphan removal. Phải xét các câu SQL phát ra và lượng dữ liệu thực sự đổi.

### 7.2. `save()` không phải bản hợp đồng “một UPDATE”

Tùy ORM/provider, `save(entity)` có thể liên quan đến tra cứu trạng thái, merge entity graph, kiểm tra phiên bản, flush và câu SQL khác. Không nên tuyên bố `save()` luôn phát một INSERT hay UPDATE. Với hành động cộng số lượng hoặc đặt trạng thái theo điều kiện, một **câu SQL cập nhật nguyên tử** có thể vừa rõ logic vừa giảm round trip:

~~~sql
UPDATE products
SET stock = stock - ?
WHERE id = ?
  AND stock >= ?;
~~~

Repository trả số hàng cập nhật để service biết thao tác có được chấp nhận hay không. Nếu nghiệp vụ gồm nhiều bảng thì cần đặt các câu lệnh liên quan trong cùng transaction. Trừ tồn kho bằng cách load entity, tính giá trị mới trong Java và `save()` có thể gây lost update nếu không có cơ chế bảo vệ phù hợp.

## 8. Transaction là một ranh giới nghiệp vụ, không phải chi tiết vô hình

Một thiết kế thường gặp:

~~~text
HTTP request
    -> Service xử lý nghiệp vụ
        -> Repository đọc trạng thái
        -> Repository cập nhật tồn kho
        -> Repository tạo đơn
        -> COMMIT
    -> HTTP response
~~~

Nếu mỗi repository tự mở connection và autocommit riêng, thao tác trừ tồn kho có thể commit trước khi tạo đơn. Lỗi ở bước tạo đơn làm dữ liệu bị lệch. **Trừu tượng hóa tốt** cho phép service sở hữu transaction của cả nghiệp vụ, còn repository tham gia cùng transaction/connection do tầng trên quản lý.

Trong Spring, một ví dụ mang tính khái niệm:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final InventoryRepository inventory;
    private final OrderRepository orders;

    public CheckoutService(
            InventoryRepository inventory,
            OrderRepository orders) {
        this.inventory = inventory;
        this.orders = orders;
    }

    @Transactional
    public void checkout(CheckoutCommand command) {
        boolean reserved = inventory.reserve(command);
        if (!reserved) {
            throw new IllegalStateException("Insufficient stock");
        }
        orders.create(command);
    }
}
~~~

Các kiểu `InventoryRepository`, `OrderRepository` và `CheckoutCommand` là thành phần ứng dụng giả định. Đoạn code minh họa vị trí khai báo transaction, **chưa là chương trình có thể biên dịch độc lập**. Cần kiểm tra rằng mọi repository dùng cùng transaction manager/datasource; self-invocation trong cấu hình proxy thông dụng có thể không kích hoạt `@Transactional`, và quy tắc rollback của checked exception cần cấu hình phù hợp.

Lời gọi `checkout()` có thể trả từ thân method trước khi transaction interceptor hoàn tất commit. Không phát sự kiện hoặc gửi email như thể commit đã chắc chắn thành công khi vẫn nằm trong transaction; cần dùng after-commit synchronization, outbox hoặc cơ chế phối hợp phù hợp.

### 8.1. Một hay nhiều SELECT: tính nhất quán có khác

Giải quyết N+1 bằng **hai câu SQL** (truy vấn order IDs rồi truy vấn items theo các ID đó) có thể giảm round trip, nhưng ở PostgreSQL READ COMMITTED, hai SELECT thông thường có thể thấy **hai snapshot khác nhau** nếu transaction khác commit ở giữa.

Nếu màn hình chấp nhận dữ liệu gần đúng theo thời điểm đọc, đây có thể là đánh đổi hợp lý. Nếu báo cáo phải nhìn thấy một trạng thái nhất quán, cân nhắc một SQL duy nhất, snapshot phù hợp như `REPEATABLE READ` hoặc cách thiết kế tổng hợp khác. Đừng giả định nhiều câu SQL trong cùng transaction READ COMMITTED tạo một ảnh chụp duy nhất.

## 9. Cache làm API nhanh nhưng thay đổi ngữ nghĩa dữ liệu

Một phương thức `getById()` có thể không gửi SQL ở lần gọi thứ hai vì ORM first-level cache, second-level cache hoặc cache ứng dụng. Đây là cải thiện có ích khi đúng với yêu cầu về độ mới dữ liệu, nhưng có một số hệ quả:

- Chạy test khi cache đã ấm có thể che N+1 hoặc làm sai ước lượng query count.
- Cache có thể trả dữ liệu cũ sau transaction ở instance khác đã commit.
- Dữ liệu của các tenant phải được phân vùng và kiểm tra quyền đúng cách trong cache key/policy.
- Invalidation có thể phức tạp hơn query database.
- Một cache miss stampede có thể khiến nhiều request cùng tải lại dữ liệu, gây đột biến SQL.

Đánh giá cả **cache hit** và **cache miss**, nhất là khi service khởi động lại hoặc cache đồng thời hết hạn. Chi phí thấp ở trường hợp cache hit không chứng minh cấu trúc persistence bên dưới hiệu quả.

## 10. Giao diện persistence nên công khai thông tin gì?

Không nhất thiết đưa chi tiết SQL vào mọi tên phương thức. Nhưng một API tốt nên giúp caller và reviewer thấy các ràng buộc quan trọng.

| Thành phần hợp đồng | Cách thể hiện tốt | Rủi ro nếu ẩn |
| --- | --- | --- |
| Kiểu kết quả | DTO/projection nhỏ, entity chỉ khi cần mutation graph | Serialize/lazy-load quan hệ ngoài dự kiến |
| Kích thước kết quả | `limit`, page size, cursor, giới hạn server | Unbounded scan và memory pressure |
| Phạm vi tenant/quyền | `tenantId` hoặc policy được kiểm tra trong transaction | Truy vấn rộng hoặc rò dữ liệu tenant |
| Ranh giới transaction | Service sở hữu nghiệp vụ nguyên tử, repository tham gia đúng manager | Một nghiệp vụ tạo nhiều commit riêng |
| Độ mới dữ liệu | Hợp đồng snapshot/cache/staleness phù hợp | Số liệu giữa các câu đọc không nhất quán |
| Thao tác ghi | Trả số hàng ảnh hưởng, version hoặc kết quả có xung đột | Không thấy lost update/vi phạm bất biến |
| Lỗi và retry | Phân loại lỗi, idempotency key, outcome chưa xác định | Retry tạo bản ghi lặp hoặc che lỗi schema |
| Chi phí dự kiến | Quan sát query count, rows/bytes, p95 theo operation | Thêm field API vô tình nhân tải DB |

**Ví dụ đặt tên theo mục đích**, không theo bảng:

~~~java
public interface OrdersReadPort {
    List<OrderSummary> recentSummaries(
            long tenantId, int limit);

    Optional<OrderDetails> loadDetails(
            long tenantId, long orderId);
}

public interface InventoryWritePort {
    boolean reserveIfAvailable(
            long tenantId, long productId, int quantity);
}
~~~

Những interface trên chỉ nêu hợp đồng, không chứa implementation. Không phải mọi nghiệp vụ cần CQRS hay tách thành nhiều interface; ở module nhỏ, một repository thống nhất vẫn có thể đủ. Tuy nhiên, phân biệt **đường đọc tối ưu cho DTO** với **đường ghi giữ bất biến** thường giúp tránh dùng một entity graph cho mọi use case.

## 11. Đo và kiểm chứng abstraction bằng bằng chứng

### 11.1. Xem SQL thực sự được phát ra

Khi dùng JPA/Hibernate, bật logging/tracing SQL ở môi trường kiểm thử phù hợp và đo số statement cho **một request thực**, không chỉ nhìn vào JPQL. Quan sát các câu SQL xuất hiện khi truy cập lazy properties, serialization hoặc gọi repository trong vòng lặp.

Trong PostgreSQL có thể dùng `pg_stat_statements` nếu extension đã được bật và được cấu hình phù hợp, kết hợp `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn quan trọng. Phía Java cần ghi nhận độ trễ mượn connection, thời gian giữ connection, số truy vấn, số hàng đọc và p95/p99 của endpoint.

Giới hạn logging: SQL có thể chứa thông tin cá nhân, identifier hoặc dữ liệu nhạy cảm trong tham số. Chỉ bật log cần thiết, che hoặc loại dữ liệu nhạy cảm và tôn trọng chính sách retention.

### 11.2. Đề xuất một phép thử N+1 có ý nghĩa

Trong integration test có database thử nghiệm:

1. Chuẩn bị **20 đơn hàng**, mỗi đơn có ít nhất một item, với một tenant lớn và một tenant nhỏ.
2. Xóa/khống chế cache theo cấu hình test để thấy đường DB thực khi chưa có cache.
3. Gọi API tóm tắt đơn hàng; đếm số SQL ở lớp truy cập DB hoặc công cụ metrics của ORM.
4. So sánh implementation gọi lazy collection lần lượt với implementation projection/aggregate hoặc batch fetch.
5. Kiểm tra **tính đúng đắn của DTO**, không chỉ số query: đơn không có item phải trả count 0, order sắp xếp ổn định, không trả dữ liệu của tenant khác.
6. Đo nhiều kích thước danh sách như 1, 20 và 100; xác nhận số SQL và thời gian không tăng theo cách ngoài dự kiến.
7. Kiểm tra thêm p95/p99 và lượng byte/row khi workload lớn; một SQL nặng chưa chắc tốt hơn vài SQL vừa phải.

Test “một request chỉ được thực thi đúng một SQL” có thể quá cứng và khiến thiết kế bị bó hẹp. Mục đích là phát hiện **tăng trưởng chi phí không mong muốn**, tránh regression và giữ SLA/SLO, thay vì cố tối thiểu tuyệt đối số statement.

### 11.3. Nhìn vào dữ liệu phân bố lệch

Trong hệ thống nhiều tenant, một tenant có 50 đơn nhưng tenant khác có hàng triệu đơn. Một API có thể hoạt động tốt với tenant nhỏ và rất chậm với tenant lớn dù cùng SQL. Cần kiểm tra thống kê, chỉ mục, độ chọn lọc, thứ tự khóa và kế hoạch thực thi cho nhiều phân bố khác nhau.

Khi thêm index, đo cả chi phí INSERT/UPDATE và dung lượng. Khi thêm cache, đo độ mới và invalidation. Khi đổi sang bulk query, kiểm tra transaction isolation. **Mỗi tối ưu hiệu năng phải giữ nguyên ngữ nghĩa nghiệp vụ đã cam kết.**

## 12. Các ngộ nhận thường gặp

**“Ít dòng Java nghĩa là ít thao tác database.”** Một getter trên entity lazy hoặc `findAll()` có thể dẫn đến rất nhiều SQL hoặc chuyển nhiều dữ liệu.

**“Một repository call luôn là một SQL.”** ORM có thể sinh nhiều câu SQL vì quan hệ, flush, merge, cascade hoặc fetch strategy.

**“Lazy loading luôn chậm.”** Khi không cần dữ liệu quan hệ, lazy loading tiết kiệm. Vấn đề là truy vấn ẩn trong vòng lặp và vị trí dùng dữ liệu.

**“Đổi mọi association sang EAGER sẽ sửa N+1.”** Có thể làm dữ liệu bị tải thừa, sinh join fan-out hoặc thêm truy vấn phụ. Cần chọn fetch theo use case.

**“JOIN FETCH collection cộng LIMIT luôn trả đúng 20 order.”** Phân trang qua quan hệ một-nhiều có thể tạo vấn đề; phải kiểm tra SQL và cảnh báo của provider.

**“Một SQL lúc nào cũng nhanh hơn hai SQL.”** Một SQL có thể thực thi join/sort rất nặng; hai SQL có thể làm dữ liệu không đồng nhất ở READ COMMITTED. Phải so sánh tổng chi phí và yêu cầu nhất quán.

**“Có transaction thì mọi lần SELECT cùng snapshot.”** Ở PostgreSQL READ COMMITTED, SELECT thông thường dùng snapshot theo statement. Khi cần dữ liệu nhất quán xuyên nhiều query, phải xét isolation.

**“Có cache thì không cần tối ưu query.”** Cache miss, cold start, eviction và thundering herd vẫn cần đường truy vấn tốt; cache còn đòi chính sách độ mới dữ liệu.

**“Thêm index là sửa được mọi abstraction chậm.”** Index không khắc phục N+1 network round trips, tải thừa hàng/cột hay giữ transaction lâu.

**“DAO phải ẩn hết mọi chi tiết để tầng trên không cần suy nghĩ.”** DAO nên ẩn JDBC và schema kỹ thuật, nhưng cần công khai những ràng buộc nghiệp vụ ảnh hưởng đến kết quả, chi phí và tính nhất quán.

## 13. Bài tập áp dụng

**Bài 1 — phân tích một repository method.** Có phương thức `findAllOrders()` trả mọi `OrderEntity`, sau đó controller lọc theo tenant, gọi `order.getItems().size()` và lấy 20 đơn mới nhất. Hãy liệt kê chi phí truy vấn, bộ nhớ, phân quyền và tính nhất quán có thể phát sinh. Thiết kế lại API với projection, filter và limit ở database.

**Bài 2 — đề xuất hai cách sửa N+1.** Với 20 order, mỗi order có trung bình 10 item, so sánh phương án aggregate SQL trả count với phương án tải 20 order và batch load items. Nếu màn hình chỉ cần `itemCount`, phương án nào đơn giản hơn về payload và vì sao? Nếu màn hình phải hiển thị toàn bộ item, quyết định có thay đổi không?

**Bài 3 — phân trang.** Cho truy vấn `ORDER BY created_at DESC LIMIT 20 OFFSET 100000`. Giải thích vì sao OFFSET cao có thể tốn kém. Viết lại bằng cursor `(created_at, id)` và phân tích hành vi khi có đơn mới chèn giữa các request.

**Bài 4 — transaction boundary.** Service lần lượt gọi `reserveStock()` và `createOrder()`; mỗi repository tự lấy connection và autocommit. Nếu tạo đơn lỗi, trạng thái nào có thể tồn tại? Thiết kế transaction do service sở hữu, xử lý rollback và trả lời khi mất phản hồi commit.

**Bài 5 — đọc EXPLAIN.** Với SQL ở phần 5, hãy chạy `EXPLAIN (ANALYZE, BUFFERS)` trên PostgreSQL thử nghiệm trước và sau khi tạo các chỉ mục đề xuất. Ghi số hàng, số trang đọc, thời gian, lựa chọn JOIN và truy vấn nào hưởng lợi. Đo thêm throughput ghi để thấy chi phí duy trì index.

**Bài 6 — ngân sách truy vấn.** Chọn một endpoint thật trong ứng dụng Java: liệt kê các đường đi cache hit/miss, SQL count, rows transferred, p95 query time, p95 API time và số connection đang bận. Đặt ngưỡng cảnh báo chi phí theo nhu cầu SLO; giải thích vì sao không nên áp một con số query count cố định cho mọi endpoint.

## Ghi nhớ

**Trừu tượng hóa hữu ích giấu chi tiết triển khai mà vẫn giữ rõ ràng ngữ nghĩa, giới hạn dữ liệu, ranh giới transaction và những chi phí quan trọng.** Repository, ORM, DTO, cache và các giao diện Java giúp mã dễ bảo trì; nhưng nếu abstraction khiến N+1, over-fetching, lazy loading ngoài dự kiến, phân trang trong bộ nhớ hay commit riêng lẻ trở nên vô hình thì nó đang che giấu chi phí và rủi ro.

Khi thiết kế persistence, hãy bắt đầu từ dữ liệu và bất biến mà một use case thực sự cần, đưa lọc/giới hạn/tổng hợp về database khi phù hợp, đo SQL thực và kế hoạch thực thi, rồi kiểm tra lại tính đúng đắn ở tầng Java. API tốt cho phép thay cách lưu trữ mà không làm người dùng ứng dụng phải trả chi phí bất ngờ.
