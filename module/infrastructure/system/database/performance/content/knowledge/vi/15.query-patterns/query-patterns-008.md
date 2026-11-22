# Giảm lượt trao đổi bằng xử lý theo tập hợp thay cho từng bản ghi

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Nhận diện mẫu xử lý từng bản ghi và hiện tượng N+1 làm tăng số lượt trao đổi giữa ứng dụng với cơ sở dữ liệu.
- Chuyển vòng lặp đọc/ghi thành một câu SQL xử lý theo tập hợp khi ngữ nghĩa nghiệp vụ cho phép.
- Chọn giữa một câu lệnh set-based, multi-row statement, JDBC batch và công cụ bulk load.
- Thiết kế transaction, kích thước batch và chiến lược xử lý lỗi phù hợp với khối lượng dữ liệu.
- Đo số lượt round trip, throughput, độ trễ, khóa, log và tài nguyên để xác nhận hiệu quả.

## 1. Vì sao số lượt trao đổi ảnh hưởng hiệu năng?

Ứng dụng thường giao tiếp với cơ sở dữ liệu qua mạng hoặc qua một lớp giao thức. Mỗi lần gửi câu lệnh và chờ kết quả có thể phát sinh chi phí cố định: mã hóa request, truyền dữ liệu, xử lý giao thức, lập kế hoạch hoặc tra cứu kế hoạch, thực thi, truyền kết quả và chuyển đổi dữ liệu trong driver.

Khi ứng dụng xử lý hàng nghìn bản ghi bằng cách gửi một câu lệnh cho từng bản ghi, chi phí cố định này lặp lại nhiều lần. Ngay cả khi mỗi câu SQL chỉ mất vài mili giây, tổng thời gian chờ round trip có thể chiếm phần lớn thời gian nghiệp vụ.

Ví dụ, ứng dụng cần cập nhật trạng thái cho 1.000 đơn hàng. Cách làm tuần tự có thể gửi 1.000 câu UPDATE riêng biệt. Nếu mỗi lần trao đổi có độ trễ mạng và giao thức trung bình 2 ms, riêng phần chờ tuần tự có thể tiêu tốn khoảng 2 giây, chưa tính thời gian thực thi và xử lý kết quả. Đây là phép tính minh họa; thời gian thực tế phụ thuộc driver, kết nối, mạng, máy chủ và khả năng pipeline.

Xử lý theo tập hợp (set-based processing) mô tả thay đổi mong muốn trên một tập hàng và để bộ máy cơ sở dữ liệu thực hiện công việc gần nơi dữ liệu được lưu. Thay vì yêu cầu ứng dụng điều khiển từng hàng, ứng dụng gửi một câu lệnh hoặc một số batch có kích thước hợp lý.

Trong phạm vi DATABASE_PERFORMANCE, giảm round trip là một phần của tối ưu SQL và workload. Lợi ích cần được đánh giá cùng số hàng xử lý, lượng dữ liệu truyền, thời gian giữ khóa, log giao dịch và mức tải đồng thời.

## 2. Xử lý từng bản ghi và mẫu N+1

### Vòng lặp truy vấn từng hàng

Ví dụ ứng dụng lấy danh sách đơn hàng rồi truy vấn riêng từng khách hàng:

```java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    Customer customer = customerRepository.findById(order.getCustomerId());
    order.setCustomerName(customer.getName());
}
```

Nếu danh sách có N đơn hàng, ứng dụng có thể gửi một truy vấn lấy đơn và thêm N truy vấn lấy khách hàng. Tổng số truy vấn gần bằng `1 + N`. Đây là mẫu N+1.

Vấn đề không chỉ là số câu SQL. Vòng lặp có thể:

- Tạo nhiều round trip và chuyển đổi giao thức.
- Lặp lại cùng một phép tìm kiếm cho các khóa đã xuất hiện trước đó.
- Giữ connection lâu hơn vì ứng dụng liên tục gửi lệnh.
- Tạo tải lập kế hoạch, logging và quản lý statement ở mức cao.
- Làm độ trễ tăng theo số bản ghi và dễ bùng nổ khi dữ liệu tăng.

### Dùng JOIN để lấy dữ liệu liên quan trong một lần

```sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.created_at >= ?
ORDER BY o.created_at DESC;
```

Truy vấn này lấy thông tin cần thiết bằng một phép JOIN. Bộ tối ưu có thể chọn nested loop, hash join hoặc merge join tùy kích thước dữ liệu, thống kê và chỉ mục. Ứng dụng không cần gửi thêm một câu lệnh cho từng khách hàng.

Nếu chỉ cần kiểm tra một hàng liên quan tồn tại, EXISTS có thể diễn đạt ý định rõ hơn JOIN và tránh nhân bản hàng. Nếu cần lấy danh sách con, có thể dùng JOIN, truy vấn theo tập khóa hoặc một truy vấn thứ hai theo batch thay vì một truy vấn cho mỗi bản ghi.

### Batch theo tập khóa

Khi không thể hoặc không muốn JOIN toàn bộ dữ liệu, ứng dụng có thể thu thập các khóa rồi gửi một truy vấn dùng `IN` hoặc bảng tham số:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id IN (?, ?, ?, ?, ?);
```

Đây là một truy vấn cho một nhóm khách hàng. Với số lượng khóa lớn, cần chia batch để tránh giới hạn số tham số, câu SQL quá dài hoặc kế hoạch kém. Một số hệ quản trị hỗ trợ array parameter, table-valued parameter, temporary table hoặc staging table phù hợp hơn danh sách IN rất lớn.

## 3. Chuyển vòng lặp UPDATE thành một câu lệnh set-based

Giả sử ứng dụng cần tăng phí giao hàng cho các đơn thuộc một khu vực và đang chờ xử lý.

Cách lặp từng đơn:

```java
for (Long orderId : orderIds) {
    orderRepository.increaseShippingFee(orderId, 5000);
}
```

Mỗi lần lặp có thể tạo một câu UPDATE. Nếu quy tắc giống nhau cho cả tập, có thể biểu đạt trực tiếp trong SQL:

```sql
UPDATE orders
SET shipping_fee = shipping_fee + 5000
WHERE region_id = ?
  AND status = 'PENDING';
```

Chỉ một câu lệnh mô tả toàn bộ tập hàng. Cơ sở dữ liệu có thể lọc, khóa và cập nhật các hàng theo kế hoạch của nó, tránh round trip riêng cho từng ID.

### Cập nhật theo giá trị khác nhau của từng hàng

Nếu mỗi đơn có mức điều chỉnh riêng, có thể truyền một tập dữ liệu vào câu lệnh. Ví dụ PostgreSQL dùng `VALUES`:

```sql
UPDATE orders AS o
SET shipping_fee = v.new_fee
FROM (VALUES
    (101, 15000),
    (102, 18000),
    (103, 12000)
) AS v(order_id, new_fee)
WHERE o.order_id = v.order_id;
```

Mỗi `order_id` trong nguồn cần xuất hiện tối đa một lần. Nếu nguồn có nhiều hàng cùng khóa, kết quả cập nhật có thể không xác định theo cách ứng dụng mong đợi hoặc phụ thuộc hệ quản trị. Hãy loại trùng hoặc bảo đảm tính duy nhất trước khi cập nhật.

Với danh sách rất lớn, không nên tạo một câu VALUES khổng lồ. Hãy nạp dữ liệu vào temporary/staging table, tạo ràng buộc khóa phù hợp rồi JOIN bảng đích với staging table.

## 4. INSERT nhiều hàng và bulk load

### Multi-row INSERT

Thay vì gửi một INSERT cho mỗi hàng:

```sql
INSERT INTO order_items (order_id, product_id, quantity)
VALUES (?, ?, ?);
```

có thể chèn nhiều hàng trong một câu lệnh nếu hệ quản trị và driver hỗ trợ:

```sql
INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (1001, 501, 2),
    (1001, 502, 1),
    (1002, 503, 4);
```

Multi-row INSERT giảm số câu lệnh và round trip. Tuy nhiên, câu lệnh lớn có thể vượt giới hạn số tham số, kích thước packet hoặc giới hạn parser. Nó cũng tạo một đơn vị lỗi lớn hơn: nếu một hàng vi phạm ràng buộc, cách xử lý toàn câu lệnh tùy hệ quản trị và cấu hình.

### Bulk load

Khi nạp lượng dữ liệu lớn, công cụ bulk thường hiệu quả hơn INSERT thông thường vì có thể tối ưu truyền dữ liệu, parse và ghi theo lô.

| Hệ quản trị/công cụ | Cơ chế thường dùng |
| --- | --- |
| PostgreSQL | `COPY` từ file hoặc stream vào bảng |
| SQL Server | `BULK INSERT`, `bcp` hoặc `SqlBulkCopy` trong ứng dụng .NET |
| MySQL | `LOAD DATA` từ file hoặc luồng dữ liệu phù hợp |

Bulk load thường phù hợp cho nhập dữ liệu định kỳ, đồng bộ, nạp staging hoặc ETL. Cần hiểu cách công cụ xử lý trigger, constraint, identity, lỗi từng hàng, transaction và logging; không mặc định bulk load bỏ qua mọi ràng buộc.

### Ví dụ PostgreSQL COPY

```sql
COPY staging_order_items (order_id, product_id, quantity)
FROM STDIN WITH (FORMAT CSV, HEADER TRUE);
```

Ứng dụng hoặc công cụ gửi nội dung theo giao thức COPY. Sau khi nạp staging, có thể kiểm tra dữ liệu rồi chèn vào bảng chính bằng một câu lệnh:

```sql
INSERT INTO order_items (order_id, product_id, quantity)
SELECT order_id, product_id, quantity
FROM staging_order_items
WHERE is_valid = TRUE;
```

Cách này tách bước vận chuyển dữ liệu khỏi bước kiểm tra và áp dụng vào bảng nghiệp vụ.

## 5. JDBC batch và giới hạn của batching

Không phải lúc nào cũng có thể viết lại thành một câu SQL set-based. Ví dụ mỗi hàng có logic kiểm tra riêng, cần gọi stored procedure hoặc phải giữ cấu trúc lệnh đã chuẩn bị. JDBC batch cho phép gửi nhiều lần thực thi của cùng một PreparedStatement theo nhóm.

```java
String sql = "UPDATE orders SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    connection.setAutoCommit(false);

    int batchSize = 500;
    int pending = 0;

    for (OrderUpdate update : updates) {
        ps.setString(1, update.status());
        ps.setLong(2, update.orderId());
        ps.addBatch();
        pending++;

        if (pending == batchSize) {
            ps.executeBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
    }

    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

Đoạn mã minh họa batch trong một transaction. Trong ứng dụng thật, cần khôi phục trạng thái auto-commit hoặc dùng transaction manager phù hợp, đóng statement/connection đúng vòng đời và xử lý lỗi theo quy tắc của driver.

JDBC `executeBatch()` không bảo đảm mọi driver sẽ gộp toàn bộ lệnh thành đúng một round trip hoặc một câu SQL. Một số driver có tùy chọn rewrite batch INSERT thành multi-row INSERT; hành vi phụ thuộc driver và cấu hình. Hãy kiểm tra tài liệu driver và đo số request thực tế.

Batching giảm số lần gọi API và có thể giảm round trip, nhưng vẫn thực thi nhiều thao tác logic. Nếu tất cả hàng có thể được cập nhật bằng một câu UPDATE, set-based SQL thường giúp optimizer nhìn toàn bộ tập dữ liệu và có cơ hội chọn kế hoạch tốt hơn.

## 6. Chọn giữa set-based SQL, batch và bulk load

| Phương án | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| Một câu set-based SQL | Cùng một quy tắc áp dụng cho tập hàng; có thể JOIN, UPDATE, DELETE hoặc INSERT ... SELECT | Kế hoạch có thể xử lý tập lớn; cần kiểm soát phạm vi khóa và số hàng ảnh hưởng |
| Multi-row INSERT/UPDATE | Dữ liệu được gửi theo lô vừa phải và mỗi hàng có giá trị riêng | Giới hạn tham số, packet, kích thước SQL và xử lý lỗi |
| JDBC/driver batch | Cùng một statement chạy nhiều lần, khó gộp thành một câu lệnh | Số round trip thực tế phụ thuộc driver; transaction và batch size cần kiểm soát |
| Temporary/staging table | Tập đầu vào lớn, cần JOIN, kiểm tra hoặc biến đổi trước khi áp dụng | Chi phí nạp staging, index, cleanup và vòng đời session/transaction |
| Bulk load | Nạp dữ liệu khối lượng lớn hoặc ETL | Chính sách constraint, trigger, logging, lỗi và tính nhất quán |

Chọn phương án theo số hàng, tính đồng nhất của thao tác, yêu cầu atomicity, khả năng hỗ trợ của hệ quản trị và mức độ phức tạp của logic. Không phải cứ batch lớn nhất là nhanh nhất.

## 7. Dùng staging table cho tập dữ liệu lớn

Staging table hữu ích khi ứng dụng có hàng chục nghìn hoặc hàng triệu bản ghi đầu vào. Thay vì đưa mọi giá trị vào một câu SQL rất dài, ứng dụng nạp dữ liệu theo luồng hoặc batch, sau đó thực hiện JOIN set-based.

Ví dụ PostgreSQL:

```sql
CREATE TEMP TABLE incoming_order_updates (
    order_id BIGINT PRIMARY KEY,
    new_status VARCHAR(20) NOT NULL
) ON COMMIT DROP;

-- Nạp nhiều hàng vào incoming_order_updates bằng COPY

UPDATE orders AS o
SET status = u.new_status
FROM incoming_order_updates AS u
WHERE o.order_id = u.order_id
  AND o.status <> u.new_status;
```

Khóa chính trên staging bảo đảm mỗi order_id chỉ xuất hiện một lần và có thể hỗ trợ JOIN. `ON COMMIT DROP` khiến bảng tạm bị xóa khi transaction commit trong PostgreSQL; cần giữ đúng transaction và connection trong suốt quá trình nạp rồi cập nhật.

Staging table cũng cho phép kiểm tra trước khi áp dụng:

- Số hàng nhận được và số khóa trùng.
- Khóa không tồn tại ở bảng đích.
- Giá trị không hợp lệ hoặc vi phạm quy tắc nghiệp vụ.
- Số hàng dự kiến sẽ cập nhật.
- Các thay đổi xung đột với trạng thái hiện tại.

Với SQL Server có thể dùng temporary table hoặc table-valued parameter; MySQL có thể dùng temporary table hoặc staging table thường theo kiến trúc nạp. Cú pháp và vòng đời khác nhau theo sản phẩm.

## 8. UPSERT và đồng bộ tập dữ liệu

Khi cần chèn hàng mới hoặc cập nhật hàng đã tồn tại, một câu lệnh UPSERT có thể thay thế vòng lặp kiểm tra rồi INSERT/UPDATE.

### PostgreSQL

```sql
INSERT INTO inventory (product_id, quantity)
VALUES
    (501, 20),
    (502, 35),
    (503, 12)
ON CONFLICT (product_id)
DO UPDATE
SET quantity = EXCLUDED.quantity;
```

`ON CONFLICT` dùng unique constraint hoặc unique index làm căn cứ xác định xung đột. Nếu nguồn có nhiều hàng cùng khóa trong một câu lệnh, PostgreSQL có thể báo lỗi vì cùng một hàng đích bị tác động nhiều lần; cần khử trùng và xác định quy tắc ưu tiên trước khi UPSERT.

### MySQL

MySQL hỗ trợ `INSERT ... ON DUPLICATE KEY UPDATE` cho các xung đột trên unique key hoặc primary key:

```sql
INSERT INTO inventory (product_id, quantity)
VALUES
    (501, 20),
    (502, 35),
    (503, 12)
ON DUPLICATE KEY UPDATE
    quantity = VALUES(quantity);
```

Cú pháp tham chiếu giá trị hàng mới đã thay đổi giữa các phiên bản MySQL; `VALUES(column)` bị deprecated trong các phiên bản mới và có thể dùng alias cho hàng được chèn theo cú pháp của phiên bản. Hãy kiểm tra tài liệu đúng phiên bản trước khi triển khai.

### SQL Server

Với SQL Server, có thể dùng staging table rồi thực hiện UPDATE các hàng khớp và INSERT các hàng chưa tồn tại trong một transaction phù hợp. Khi nhiều phiên đồng thời có thể chèn cùng khóa, cần thiết kế unique constraint và locking/isolation để xử lý race condition. Không nên giả định mẫu `IF NOT EXISTS THEN INSERT` an toàn nếu không có bảo vệ đồng thời.

MERGE có các chi tiết về concurrency, trigger và hành vi theo phiên bản cần đánh giá kỹ. Với logic đơn giản, UPDATE và INSERT tách biệt trong transaction có ràng buộc duy nhất thường dễ kiểm soát hơn; chọn mẫu cụ thể theo tài liệu và kiểm thử.

UPSERT giảm số round trip nhưng không tự giải quyết xung đột nghiệp vụ. Cần xác định rõ cập nhật ghi đè, cộng dồn, chỉ cập nhật khi phiên bản mới hơn hay từ chối khi dữ liệu đã thay đổi.

## 9. DELETE theo tập hợp và xử lý khối lượng lớn

Nếu cần xóa tất cả bản ghi đã hết hạn, một câu DELETE có điều kiện có thể hiệu quả hơn vòng lặp xóa từng ID:

```sql
DELETE FROM session_records
WHERE expires_at < CURRENT_TIMESTAMP;
```

Tuy nhiên, xóa hàng triệu bản ghi trong một transaction lớn có thể giữ khóa lâu, tạo transaction log/WAL lớn, làm tăng replication lag, tạo nhiều dead tuple hoặc gây áp lực lên hệ thống lưu trữ.

Khi cần chia nhỏ, dùng batch theo khóa ổn định và điều kiện xác định, ví dụ PostgreSQL:

```sql
WITH batch AS (
    SELECT session_id
    FROM session_records
    WHERE expires_at < CURRENT_TIMESTAMP
    ORDER BY session_id
    LIMIT 5000
)
DELETE FROM session_records AS s
USING batch AS b
WHERE s.session_id = b.session_id;
```

Ứng dụng có thể lặp lại câu lệnh theo batch, commit từng nhóm và dừng khi không còn hàng. `session_id` cần là khóa ổn định và điều kiện chọn batch phải phù hợp với chỉ mục. Cần thiết kế cách tránh nhiều worker cùng xử lý một hàng, chẳng hạn dùng `SKIP LOCKED` khi phù hợp với hệ quản trị và ngữ nghĩa tác vụ.

Batch delete giảm thời gian giữ transaction và kích thước mỗi đợt log, nhưng làm thay đổi tính nguyên tử: các batch trước có thể đã commit dù batch sau thất bại. Nếu nghiệp vụ yêu cầu tất cả hoặc không gì cả, phải cân nhắc transaction lớn hoặc thiết kế quy trình bù/khôi phục.

## 10. Transaction và kích thước batch

Batch size là số bản ghi hoặc số thao tác gửi trong một nhóm. Batch quá nhỏ làm tăng round trip và overhead; batch quá lớn làm tăng bộ nhớ, kích thước request, thời gian transaction, khóa, log và khả năng rollback.

Chọn kích thước batch dựa trên:

- Số byte mỗi hàng và tổng payload gửi qua mạng.
- Giới hạn tham số, packet và kích thước statement của driver/hệ quản trị.
- Thời gian thực thi và thời gian giữ transaction.
- Số hàng bị khóa và mức độ tranh chấp.
- Tốc độ ghi log, I/O và replication.
- Khả năng xử lý lỗi, retry và resume.

Có thể bắt đầu thử với các cỡ như 100, 500, 1.000 hoặc 5.000 hàng tùy kích thước bản ghi, sau đó đo. Đây là điểm thử nghiệm, không phải giá trị mặc định chung.

### Một transaction hay nhiều transaction?

Giữ tất cả batch trong một transaction duy trì atomicity cho toàn bộ tập, nhưng transaction có thể rất dài. Commit từng batch làm giảm thời gian giữ tài nguyên và cho phép tiến độ được lưu, nhưng dữ liệu có thể ở trạng thái cập nhật một phần.

Quyết định dựa trên yêu cầu nghiệp vụ:

- Nếu mọi hàng phải thay đổi cùng nhau, dùng transaction bao trọn và chuẩn bị đủ tài nguyên.
- Nếu có thể chấp nhận tiến độ từng phần, commit theo batch và ghi nhận checkpoint.
- Nếu cần chạy lại an toàn, thiết kế thao tác idempotent hoặc lưu trạng thái xử lý.
- Nếu có nhiều worker, phân chia khóa hoặc phạm vi dữ liệu để tránh xử lý trùng và giảm tranh chấp.

## 11. Xử lý lỗi và retry trong batch

Batch có thể thất bại do vi phạm constraint, deadlock, timeout, mất kết nối hoặc lỗi dữ liệu ở một hàng. Cần xác định phạm vi rollback và cách tìm hàng lỗi.

Những nguyên tắc quan trọng:

- Ghi lại batch ID, phạm vi khóa, số hàng dự kiến và số hàng đã xử lý.
- Không giả định `executeBatch()` luôn trả kết quả giống nhau trên mọi driver; JDBC có `BatchUpdateException` và mảng update counts có thể chứa giá trị thành công, không xác định hoặc lỗi tùy driver.
- Nếu transaction thất bại, rollback theo đúng ranh giới transaction; không tiếp tục dùng connection ở trạng thái lỗi nếu chưa rollback/khôi phục.
- Chỉ retry lỗi tạm thời như deadlock victim hoặc lỗi kết nối theo chính sách; không retry vô hạn lỗi dữ liệu hoặc vi phạm constraint.
- Retry phải an toàn khi một phần thao tác có thể đã được commit hoặc kết quả commit không rõ do mất kết nối.

Idempotency có thể đạt được bằng khóa nghiệp vụ duy nhất, upsert có quy tắc rõ ràng, bảng ghi nhận batch, hoặc cập nhật có điều kiện theo version. Ví dụ `SET status = 'PAID'` có thể lặp lại an toàn hơn thao tác `SET balance = balance + amount`, vốn sẽ cộng lặp nếu request được thực thi hai lần.

## 12. Khi set-based không phải lựa chọn tốt nhất

Xử lý theo tập hợp thường giảm round trip, nhưng có trường hợp cần giữ logic theo từng bản ghi hoặc chia nhỏ công việc:

- Mỗi hàng cần gọi một dịch vụ ngoài hoặc một quy trình nghiệp vụ khác nhau.
- Quy tắc xử lý phụ thuộc kết quả của bước trước và không thể biểu diễn an toàn trong SQL.
- Một transaction set-based sẽ khóa quá nhiều hàng hoặc gây log lớn không thể chấp nhận.
- Cần cô lập lỗi theo từng hàng và tiếp tục các hàng hợp lệ.
- Tập dữ liệu quá lớn cần streaming hoặc chia partition để giới hạn bộ nhớ.

Trong các trường hợp đó, có thể dùng batch hoặc worker theo nhóm. Mục tiêu vẫn là giảm số lần trao đổi và kiểm soát kích thước công việc, thay vì ép mọi nghiệp vụ vào một câu SQL khổng lồ.

## 13. Đo lường hiệu quả giảm round trip

Không chỉ đo tổng thời gian của một lần chạy. Cần phân tách các thành phần:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số round trip hoặc số lần execute | Số lần ứng dụng trao đổi với cơ sở dữ liệu |
| Rows affected / rows per second | Khối lượng công việc hoàn thành |
| p50/p95/p99 latency | Độ trễ điển hình và phần đuôi chậm |
| CPU và logical reads | Chi phí xử lý ở máy chủ |
| Physical I/O và bytes transferred | Chi phí đọc/ghi lưu trữ và mạng |
| Transaction duration | Thời gian giữ transaction và tài nguyên |
| Lock wait/deadlock | Tranh chấp do cập nhật theo tập hoặc batch |
| Log/WAL generation | Khối lượng ghi log do thay đổi dữ liệu |
| Replication lag | Ảnh hưởng của lượng ghi lên bản sao |
| Error/retry rate | Độ ổn định khi batch gặp lỗi |

Ví dụ so sánh:

| Phương án | Số lần gửi lệnh | Thời gian tổng (minh họa) |
| --- | ---: | ---: |
| UPDATE từng hàng | 1.000 | 2.800 ms |
| JDBC batch 100 hàng | 10 batch | 620 ms |
| Một UPDATE theo điều kiện | 1 | 180 ms |

Các số liệu chỉ minh họa. Một câu UPDATE set-based có thể nhanh nhất khi tất cả hàng cùng quy tắc, nhưng nếu cập nhật khóa rộng và gây lock contention, batch có thể đem lại throughput tổng thể tốt hơn.

### Thiết kế benchmark công bằng

1. Dùng cùng tập dữ liệu, trạng thái ban đầu và số hàng cần xử lý.
2. Dùng cùng mức concurrency và kết nối tương đương.
3. Tách warm-up khỏi cửa sổ đo và chạy nhiều lần.
4. Ghi số round trip thực tế, không suy ra từ số lần gọi API.
5. Đo cả phía ứng dụng lẫn máy chủ cơ sở dữ liệu.
6. Xác nhận kết quả dữ liệu sau mỗi phương án giống nhau.
7. Đánh giá cả thời gian đơn lẻ và throughput khi nhiều worker cùng chạy.

## 14. Quy trình chuyển từ row-by-row sang set-based

1. **Tìm vòng lặp truy vấn.** Dùng log, trace hoặc thống kê để phát hiện cùng một query fingerprint được gọi lặp lại theo từng hàng.
2. **Xác định mục tiêu nghiệp vụ.** Ghi rõ tập hàng, điều kiện, quy tắc cập nhật và kết quả cần trả về.
3. **Kiểm tra quan hệ dữ liệu.** Xác định khóa duy nhất, quan hệ một-nhiều, khả năng trùng và NULL.
4. **Viết câu SQL theo tập hợp.** Thử JOIN, EXISTS, UPDATE FROM, INSERT SELECT, multi-row INSERT hoặc staging table.
5. **Kiểm chứng ngữ nghĩa.** So sánh số hàng, giá trị, hàng trùng, thứ tự nếu có yêu cầu và hành vi với dữ liệu biên.
6. **Đọc execution plan.** Kiểm tra access path, join algorithm, estimated/actual rows, số trang đọc và operator spill.
7. **Chọn transaction và batch size.** Cân bằng round trip, atomicity, lock, log và khả năng retry.
8. **Đo workload.** So sánh round trip, throughput, p95/p99, CPU, I/O, log, lock wait và replication lag.
9. **Triển khai có kiểm soát.** Theo dõi số hàng tác động, lỗi, thời gian transaction và tính đúng của dữ liệu.
10. **Giữ khả năng phục hồi.** Ghi checkpoint hoặc thiết kế idempotency nếu xử lý nhiều batch và commit từng phần.

## 15. Ví dụ tổng hợp: cập nhật trạng thái hàng loạt

Giả sử một file đầu vào chứa trạng thái mới cho 200.000 đơn hàng. Mỗi đơn có order_id và new_status.

Phương án row-by-row:

```java
for (OrderUpdate u : updates) {
    orderRepository.updateStatus(u.orderId(), u.status());
}
```

Phương án batch:

```java
for (List<OrderUpdate> batch : partition(updates, 500)) {
    orderRepository.batchUpdateStatus(batch);
}
```

Phương án staging và set-based:

```sql
-- Nạp file vào staging_order_status bằng công cụ bulk load

UPDATE orders AS o
SET status = s.new_status
FROM staging_order_status AS s
WHERE s.order_id = o.order_id
  AND o.status IS DISTINCT FROM s.new_status;
```

`IS DISTINCT FROM` là cú pháp PostgreSQL so sánh có xử lý NULL; hệ quản trị khác có thể dùng cú pháp khác. Staging cần unique constraint trên order_id để bảo đảm mỗi đơn có một trạng thái đầu vào duy nhất.

Để chọn phương án, hãy đo:

- Thời gian nạp staging và thời gian UPDATE riêng.
- Số round trip, rows affected và bytes truyền.
- Lock wait, deadlock và transaction log/WAL.
- Replication lag và thời gian vacuum hoặc bảo trì phát sinh nếu có.
- Hành vi khi một order_id không tồn tại hoặc trạng thái không hợp lệ.

Nếu 200.000 đơn cần cập nhật như một thay đổi nguyên tử, một transaction set-based có thể phù hợp nhưng cần đánh giá log và lock. Nếu có thể xử lý từng phần, chia staging theo batch khóa và lưu checkpoint giúp giới hạn tài nguyên.

## 16. Những sai lầm thường gặp

- **Chỉ đổi vòng lặp thành một câu SQL khổng lồ.** Statement quá lớn có thể vượt giới hạn packet/tham số và tạo transaction nặng.
- **Cho rằng JDBC batch luôn là một round trip.** Hành vi phụ thuộc driver và cấu hình; cần đo hoặc xem trace giao thức.
- **Tăng batch size mà không đo.** Batch lớn có thể tăng lock duration, memory, log và rollback cost.
- **Dùng JOIN khi chỉ cần tồn tại.** Có thể nhân bản hàng; EXISTS thường diễn đạt đúng ý định.
- **Không khử trùng khóa đầu vào.** Nhiều dòng staging cùng khóa có thể làm UPDATE/UPSERT không xác định hoặc lỗi.
- **Không kiểm tra số hàng bị ảnh hưởng.** Một điều kiện WHERE sai có thể cập nhật quá nhiều hoặc quá ít hàng.
- **Commit từng batch mà không lưu checkpoint.** Khi lỗi, không biết phần nào đã hoàn tất và retry có thể xử lý lặp.
- **Retry mọi lỗi.** Lỗi dữ liệu cố định không tự hết; retry vô hạn làm tăng tải.
- **Bỏ qua deadlock và khóa.** Một UPDATE set-based có thể khóa tập hàng lớn và cạnh tranh với giao dịch khác.
- **Đánh giá chỉ bằng thời gian một truy vấn.** Cần đo throughput và p95/p99 khi tải đồng thời.

## 17. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định vòng lặp gây N+1 hoặc số round trip lớn.
- [ ] Đã xem xét JOIN/EXISTS hoặc set-based UPDATE/DELETE/INSERT.
- [ ] Câu SQL mới bảo toàn cardinality, NULL và quy tắc nghiệp vụ.
- [ ] Dữ liệu đầu vào được khử trùng và kiểm tra khóa.
- [ ] Đã chọn multi-row statement, JDBC batch, staging hay bulk load theo kích thước.
- [ ] Batch size được đo với payload và concurrency đại diện.
- [ ] Transaction boundary đáp ứng yêu cầu atomicity và khả năng phục hồi.
- [ ] Có quy tắc xử lý lỗi, retry, idempotency và checkpoint.
- [ ] Execution plan và chỉ mục hỗ trợ truy vấn set-based đã được kiểm tra.
- [ ] Đã đo round trip, throughput, p50/p95/p99, CPU, I/O và log.
- [ ] Đã theo dõi lock wait, deadlock, replication lag và lỗi sau triển khai.
- [ ] Đã xác nhận dữ liệu cuối cùng đúng và số hàng bị tác động như dự kiến.

## Kết luận

Xử lý theo tập hợp giúp cơ sở dữ liệu thực hiện công việc gần nơi dữ liệu được lưu và giảm các lượt trao đổi lặp lại giữa ứng dụng với máy chủ. Hãy thay mẫu N+1 bằng JOIN, EXISTS hoặc câu lệnh set-based khi ngữ nghĩa phù hợp; dùng multi-row statement, driver batch, staging table hoặc bulk load cho tập đầu vào lớn. Chọn batch size và ranh giới transaction dựa trên round trip, atomicity, lock, log và khả năng retry. Cuối cùng, kiểm chứng bằng execution plan và workload đại diện, đo cả throughput, độ trễ, tài nguyên và tính đúng của dữ liệu.
