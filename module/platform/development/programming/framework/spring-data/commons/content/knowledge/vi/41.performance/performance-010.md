# Chọn index hoặc tối ưu câu truy vấn tại đúng mô-đun lưu trữ

Một phương thức repository có tên đúng, kiểu trả về hợp lệ và kết quả chính xác vẫn có thể chậm. Nó có thể sinh truy vấn phải quét nhiều bản ghi, sort một tập lớn, tải dữ liệu không cần thiết hoặc thực hiện quá nhiều lượt truy cập kho dữ liệu.

Trong chương **Hiệu năng** của module **SPRING_DATA_COMMONS**, bài học này trình bày cách đưa vấn đề hiệu năng từ abstraction repository xuống đúng module và hệ lưu trữ chịu trách nhiệm thực thi. Repository, derived query, QBE, phân trang, sắp xếp, projection và auditing giúp tổ chức mã nguồn; việc chọn index và kế hoạch truy vấn còn phụ thuộc store, mapping, driver, dữ liệu và workload thực tế.

## 1. Xác định trách nhiệm của từng tầng

Không có một loại “index Spring Data Commons” áp dụng giống nhau cho mọi database.

```text
Yêu cầu nghiệp vụ và hợp đồng API
                 |
                 v
Repository, Pageable, Sort, Example, projection
                 |
                 v
Store module: JPA, MongoDB, JDBC, R2DBC hoặc module khác
                 |
                 v
SQL, document query, pipeline hoặc ngôn ngữ truy vấn của store
                 |
                 v
Optimizer, index, partition, cache và tài nguyên của hệ lưu trữ
```

| Tầng | Quyết định thường thuộc tầng đó |
| --- | --- |
| API và dịch vụ | Điều kiện, phạm vi tenant, dữ liệu trả về, giới hạn kết quả và tính nhất quán |
| Abstraction Commons | Hình thức hợp đồng repository, phân trang, sắp xếp và các interface dùng chung |
| Store module | Cách dịch phương thức và mapping thành truy vấn, khả năng projection, custom query và hint |
| Hệ lưu trữ | Cấu trúc index, kế hoạch scan, join, sort, thống kê và chi phí thực thi |

Khi chọn giải pháp, phải tìm đúng tầng đang tạo chi phí. Đổi một entity sang DTO không tự sửa index; thêm index không tự loại bỏ hàng trăm lời gọi repository phát sinh trong một vòng lặp.

## 2. Bắt đầu từ một workload cụ thể

Giả sử màn hình cần xem đơn hàng đã thanh toán của một tenant, mới nhất trước, trong một khoảng thời gian gần đây. Mỗi lần trả khoảng 50 dòng gồm ID, thời gian tạo và tổng tiền.

Một hợp đồng repository minh họa:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

import java.math.BigDecimal;
import java.time.Instant;

public interface SalesOrderRepository
        extends Repository<SalesOrder, Long> {

    Slice<OrderSummary> findByTenantIdAndStatusAndCreatedAtGreaterThanEqual(
            Long tenantId,
            OrderStatus status,
            Instant since,
            Pageable pageable);

    interface OrderSummary {
        Long getId();
        Instant getCreatedAt();
        BigDecimal getTotalAmount();
    }
}
```

Các kiểu domain `SalesOrder` và `OrderStatus` do ứng dụng định nghĩa. Ví dụ giả định module lưu trữ được chọn hỗ trợ cách thực thi và projection tương ứng; không coi mọi store có repository đều thực hiện được nguyên xi chữ ký này.

Cách gọi với thứ tự ổn định:

```java
Pageable first = PageRequest.of(0, 50, Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")));

Slice<SalesOrderRepository.OrderSummary> result = orders
        .findByTenantIdAndStatusAndCreatedAtGreaterThanEqual(
                42L, OrderStatus.PAID, since, first);
```

Đoạn gọi dùng `PageRequest` và `Sort` từ `org.springframework.data.domain`. ID là khóa phân xử khi nhiều đơn có cùng thời gian tạo.

### 2.1. Thông tin cần biết trước khi thiết kế index

Không chỉ biết bảng có những cột nào. Cần biết:

- Truy vấn xuất hiện bao nhiêu lần và trên tenant lớn hay nhỏ.
- Tỷ lệ trạng thái PAID trong từng nhóm dữ liệu.
- Khoảng thời gian thường dùng và số dòng thực sự khớp.
- Có luôn lọc status không, hay giao diện còn cho chọn mọi trạng thái.
- Có cần tổng số kết quả, nhảy tới trang sâu hoặc đọc tuần tự không.
- Tốc độ ghi, cập nhật status và dung lượng lưu trữ cho index.

Một index phục vụ tốt mẫu truy vấn này chưa chắc phù hợp cho báo cáo toàn bộ tenant, tìm theo email hoặc tổng hợp dữ liệu của cả năm.

## 3. Quan sát truy vấn thật trước khi quyết định

Tên phương thức repository mô tả ý định, nhưng chưa cho biết đầy đủ:

- Tên cột hoặc field sau mapping.
- Cách enum, thời gian và tham số được biểu diễn.
- Join phát sinh từ đường dẫn thuộc tính.
- Những trường được chọn do entity hoặc projection.
- Count query do `Page` yêu cầu.
- Query phụ khi truy cập quan hệ hoặc serialize kết quả.

Với JPA, cần xem SQL và kiểu tham số thực tế, không dừng ở JPQL hoặc tên derived query. Với MongoDB, xem filter, sort, projection và pipeline được gửi đi. Với JDBC hoặc R2DBC, xem SQL mà thành phần thực thi dùng, gồm cả phần custom query.

### 3.1. Đừng nhầm thời gian API với thời gian ở database

Độ trễ người dùng nhìn thấy có thể bao gồm chờ connection pool, thực thi nhiều query, truyền dữ liệu, mapping, CPU ứng dụng và serialization.

Nếu database thực thi nhanh nhưng ứng dụng chờ pool hoặc tải thêm dữ liệu từng dòng, việc tạo thêm index có thể không làm độ trễ tổng giảm đáng kể. Cần liên kết quan sát từ request đến các lượt truy cập dữ liệu liên quan.

### 3.2. Dữ liệu và tham số phải có tính đại diện

Một truy vấn chạy nhanh trên vài trăm dòng không dự báo được hành vi trên hàng triệu dòng. Một tenant chiếm phần lớn dữ liệu cũng có thể có kế hoạch phù hợp khác với tenant nhỏ.

Đo nhiều nhóm tham số có ý nghĩa, kể cả trường hợp trả rỗng, trả ít và trả nhiều. Khi ứng dụng dùng prepared statement, kế hoạch với tham số thực tế còn cần được đối chiếu với cách database chọn và tái sử dụng plan.

## 4. Ví dụ PostgreSQL: chọn index từ điều kiện và thứ tự

Phần này chỉ áp dụng cho ví dụ cơ sở dữ liệu quan hệ PostgreSQL. Giả định mapping SQL:

```text
sales_order
    id
    tenant_id
    status
    created_at
    total_amount
```

`status` được lưu theo chuỗi của ví dụ, `created_at` có kiểu thời gian phù hợp tham số ứng dụng, và các trường dùng cho thứ tự không null trong hợp đồng này.

Một dạng truy vấn nội dung có thể quan sát:

```sql
SELECT id, created_at, total_amount
FROM sales_order
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
ORDER BY created_at DESC, id DESC
LIMIT 51;
```

Giới hạn 51 minh họa kỹ thuật lấy dư một dòng để xác định còn dữ liệu cho một Slice kích thước 50. Câu lệnh chính xác, tham số và cách giới hạn vẫn phải kiểm tra trên implementation đang dùng.

### 4.1. Một index ứng viên cho mẫu truy vấn này

```sql
CREATE INDEX sales_order_tenant_status_time_id_idx
ON sales_order (tenant_id, status, created_at DESC, id DESC);
```

Lý do xem xét:

1. tenant và status là các điều kiện bằng trong mẫu truy vấn đã chọn.
2. `created_at` tham gia khoảng thời gian và là khóa sort chính.
3. `id` tiếp tục thứ tự khi thời gian tạo bằng nhau.
4. Sau khi giới hạn phạm vi phù hợp, engine có cơ hội đọc theo thứ tự cần thiết và dừng theo limit.

Đây là ứng viên để kiểm chứng, không phải index mặc định cho mọi bảng đơn hàng. Phải đối chiếu index hiện có, phân bố dữ liệu và các truy vấn khác trước khi chấp nhận chi phí thêm index.

Đối với B-tree nhiều cột, điều kiện trên các cột đầu có ảnh hưởng lớn tới phần index cần duyệt. Các chiến lược optimizer, kể cả skip scan khi phù hợp, còn phụ thuộc phiên bản và dữ liệu. Không biến nguyên tắc thứ tự cột thành kết luận tuyệt đối rằng mọi truy vấn thiếu cột đầu đều không thể dùng index. Xem [multicolumn index của PostgreSQL](https://www.postgresql.org/docs/current/indexes-multicolumn.html).

### 4.2. Khi một bộ lọc biến mất, mẫu truy vấn đã đổi

Nếu bỏ điều kiện status và vẫn cần tất cả đơn của tenant theo thời gian, index trên có thứ tự status nằm trước created_at. Không được mặc định nó còn cung cấp cùng đường đọc thuận lợi như trường hợp status cố định.

Cần xem plan của biến thể đó và cân nhắc tần suất sử dụng. Có thể phải chọn một index khác hoặc điều chỉnh thiết kế truy vấn; không thêm một index cho mọi tổ hợp tùy chọn một cách tự động.

### 4.3. Covering hoặc index-only không phải bảo đảm chỉ từ projection

Nếu query chỉ lấy các trường nằm trong index, có thể có cơ hội giảm truy cập dữ liệu ngoài index theo khả năng engine. PostgreSQL có cơ chế cột INCLUDE để phục vụ một số nhu cầu dữ liệu đọc.

Nhưng thêm mọi cột projection vào index không phải tối ưu miễn phí: index rộng hơn, ghi tốn hơn và có thể chiếm nhiều cache. Index-only scan còn phụ thuộc điều kiện thực thi của PostgreSQL, không chỉ danh sách cột Java.

Trước khi mở rộng index, phải xác nhận phần chi phí cần giảm thực sự nằm ở lượt đọc dữ liệu còn lại và lợi ích đủ lớn so với workload ghi.

## 5. Đọc execution plan thay vì chỉ nhìn thấy tên index

Ví dụ công cụ phân tích trong PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM sales_order
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
ORDER BY created_at DESC, id DESC
LIMIT 51;
```

`EXPLAIN` cho biết kế hoạch; khi có `ANALYZE`, truy vấn được thực thi để thu thập số liệu thực tế. Ví dụ dùng SELECT trên môi trường đo phù hợp. Các chỉ số và cách đọc được giải thích trong [Using EXPLAIN của PostgreSQL](https://www.postgresql.org/docs/current/using-explain.html).

Những câu hỏi cần trả lời:

| Quan sát | Câu hỏi phân tích |
| --- | --- |
| Scan và điều kiện index | Engine giới hạn phạm vi từ đâu hay đọc rộng rồi mới lọc? |
| Rows thực tế và ước lượng | Optimizer có ước lượng sai lớn do thống kê hoặc phân bố dữ liệu không? |
| Rows bị loại bởi filter | Có đọc nhiều dữ liệu không cần thiết không? |
| Sort và tài nguyên sort | Có sort riêng, dữ liệu lớn hoặc tràn ra lưu trữ tạm không? |
| Join và số vòng lặp | Có khuếch đại số dòng hoặc thao tác lặp tốn kém không? |
| Buffers và thời gian | Chi phí nghiêng về đọc, cache hay xử lý khác? |
| Limit | Engine có dừng sớm được hay vẫn làm nhiều việc trước khi trả vài dòng? |

### 5.1. Index được dùng vẫn có thể chậm

Một index scan có thể phải duyệt rất nhiều entry rồi loại gần hết. Một nested loop có thể lặp một phép tìm nhỏ hàng trăm nghìn lần. Việc tên index xuất hiện trong plan không tự chứng minh query đã tối ưu.

Ngược lại, sequential scan có thể là lựa chọn hợp lý khi bảng nhỏ hoặc query cần phần lớn dữ liệu. Không ép engine dùng index chỉ để plan trông giống kỳ vọng.

### 5.2. Cost không phải thời gian request tính bằng mili giây

Cost trong plan là thước đo nội bộ của optimizer. Số liệu thực thi cũng không bao gồm toàn bộ chi phí ứng dụng và mạng theo cùng cách một phép đo API nhìn thấy.

So sánh các plan và số liệu trong cùng điều kiện, đồng thời quan sát end-to-end nếu mục tiêu là cải thiện thời gian đáp ứng người dùng.

## 6. Khi nên sửa câu truy vấn thay vì thêm index

### 6.1. Tránh bọc cột trong phép biến đổi không phù hợp index hiện có

Ví dụ tìm một ngày theo cách:

```sql
WHERE DATE(created_at) = :day
```

có thể cần xử lý khác với một range trực tiếp trên cột. Nếu nghiệp vụ là khoảng thời gian của một ngày đã được xác định đúng theo múi giờ, có thể biểu diễn:

```sql
WHERE created_at >= :start_inclusive
  AND created_at < :end_exclusive
```

Cách viết này giúp làm rõ hai cận và có thể thuận lợi cho index thời gian thông thường. Nó chỉ là thay thế đúng khi việc tính cận giữ nguyên ngữ nghĩa ngày và múi giờ; không lấy 24 giờ cố định để thay mọi khái niệm ngày địa phương.

Nếu workload thật sự cần biểu thức trên cột, có thể đánh giá index biểu thức theo engine. Phải khớp đúng phép biến đổi và kiểu dữ liệu.

### 6.2. IgnoreCase phải đối chiếu SQL thật

Một phương thức như `findByEmailIgnoreCase` có thể được module dịch thành biểu thức chuẩn hóa case. Nếu SQL dùng `upper(email)`, một index được tạo trên `lower(email)` không tự tương đương cho optimizer chỉ vì người viết cùng nghĩ là “không phân biệt hoa thường”.

Cần xem hàm, collation, kiểu so sánh và cách chuẩn hóa dữ liệu. Chính sách Unicode hoặc bỏ dấu cũng không tự phát sinh từ tên IgnoreCase.

### 6.3. Contains không mặc định phù hợp B-tree thông thường

Tìm chuỗi nằm ở giữa, chẳng hạn một dạng LIKE có ký tự đại diện ở đầu, có đặc tính khác tìm theo giá trị chính xác hoặc prefix. Không tự chọn một B-tree đơn giản rồi kỳ vọng mọi kiểu tìm kiếm chuỗi được giải quyết.

Nếu nghiệp vụ cần tìm văn bản hoặc mẫu chuỗi phức tạp, đánh giá khả năng tìm kiếm và loại index chuyên biệt của store. Thay đổi cơ chế tìm kiếm phải giữ đúng quy tắc case, dấu, token và ký tự đặc biệt mà ứng dụng yêu cầu.

### 6.4. Offset sâu có thể là chi phí còn lại

Một trang rất sâu có thể yêu cầu engine duyệt hoặc bỏ qua nhiều bản ghi trước khi trả vài dòng, dù có index. Nếu giao diện chấp nhận đọc tiếp theo cursor, có thể xem xét keyset pagination.

Ví dụ PostgreSQL cho thứ tự cả hai khóa đều giảm dần:

```sql
AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
```

Điều kiện này phải được ghép cùng phạm vi tenant, status và các filter ban đầu. Nó giả định các khóa không null, kiểu dữ liệu phù hợp và cursor lấy từ đúng thứ tự đã định. Không đổi phân trang mà bỏ mất hợp đồng lọc hoặc mặc định mọi dataset biến động đều được đọc đúng một lần.

### 6.5. Loại bỏ những lượt truy vấn không cần thiết

Nếu một endpoint chạy một query danh sách rồi thêm một query cho mỗi dòng, tổng chi phí có thể nằm ở số lượt truy cập, không chỉ index của query đầu.

Cần xem lại fetch plan, projection, phép tổng hợp hoặc custom query phù hợp module. Tương tự, nếu API chỉ cần biết còn trang sau, một count tổng đắt có thể không cần thiết; chọn Slice hay kiểu kết quả khác chỉ khi hợp đồng API cho phép.

## 7. Ví dụ MongoDB: compound index theo filter và sort của document

Không mang nguyên câu lệnh CREATE INDEX của PostgreSQL sang MongoDB. Giả định document có field `tenantId`, `status`, `createdAt`, `totalAmount` và `_id`.

Một truy vấn mong muốn trong mongosh:

```javascript
db.orders.find(
  {
    tenantId: 42,
    status: "PAID",
    createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
  },
  { _id: 1, createdAt: 1, totalAmount: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(51);
```

Các kiểu giá trị BSON phải khớp dữ liệu và mapping thực tế. Ví dụ shell minh họa ý tưởng; cần quan sát query được driver của ứng dụng gửi đi, kể cả kiểu số và thời gian.

Một index ứng viên:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "orders_tenant_status_time_id_idx" }
);
```

Ở đây, hai điều kiện bằng tạo phạm vi trước phần thứ tự thời gian và ID. Đây vẫn là lựa chọn cho mẫu query đã xác định, không phải cách xếp field tối ưu cho mọi nhu cầu.

### 7.1. ESR là hướng dẫn theo workload, không phải câu thần chú

MongoDB mô tả hướng Equality, Sort, Range cho compound index. Nếu ưu tiên tránh sort trong bộ nhớ, việc đặt phần sort trước phần range có thể phù hợp; nếu range rất chọn lọc, cần cân nhắc lựa chọn khác. Xem [ESR guideline của MongoDB](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).

Trong ví dụ trên, createdAt vừa là field range vừa là sort chính. Đối với một workload khác, chẳng hạn range trên tổng tiền nhưng sort theo thời gian, phải đánh giá lại sự đánh đổi đó thay vì sao chép nguyên index.

### 7.2. Quan sát explain trên query thật

```javascript
db.orders.find(
  {
    tenantId: 42,
    status: "PAID",
    createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
  },
  { _id: 1, createdAt: 1, totalAmount: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(51)
 .explain("executionStats");
```

Cần xem kế hoạch được chọn, số kết quả, số key và document được kiểm tra, cùng công việc sort hoặc các stage khác. Projection nhỏ không có nghĩa query đã được covered: nếu còn cần đọc field không có trong index, engine vẫn có thể phải đọc document.

Tỷ lệ key hoặc document được xét so với kết quả giúp nhận diện mức công việc dư, nhưng không có một ngưỡng cố định đúng cho mọi truy vấn. Khi không có kết quả, cần đọc các số tuyệt đối và phạm vi được xét thay vì dùng một phép chia thiếu ý nghĩa.

## 8. Khai báo index phải nằm trong cơ chế quản lý của store

### 8.1. Với JPA và cơ sở dữ liệu quan hệ

Metadata như index trong mapping JPA có ý nghĩa trong cơ chế schema generation tương ứng. Nó không tự chứng minh rằng index đã được tạo trên database triển khai, nơi schema có thể được quản lý bằng migration riêng.

Quy trình ứng dụng cần biết thay đổi schema được áp dụng bởi ai, ở môi trường nào và theo cách nào. Xác nhận index tồn tại trong catalog thực tế, không chỉ tồn tại dưới dạng annotation trong Java.

### 8.2. Với Spring Data MongoDB

Spring Data MongoDB có các annotation và API quản lý index của chính module. Từ phiên bản 3.0, tự động tạo index cần được bật rõ ràng; chỉ có annotation trên document không có nghĩa mọi cấu hình đều tự tạo index khi chạy. Xem [quản lý index của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html).

Cũng phải xét vòng đời collection: một collection được tạo lại trong lúc ứng dụng chạy không tự được bảo đảm có đầy đủ index chỉ vì metadata Java vẫn còn.

Không đưa annotation MongoDB vào một entity JPA rồi kỳ vọng nó tạo index SQL, hoặc xem hai annotation có tên giống nhau là cùng một hợp đồng.

### 8.3. Với các store khác

| Module hoặc hệ lưu trữ | Điều cần đánh giá ở đúng tài liệu và công cụ |
| --- | --- |
| Spring Data JDBC hoặc R2DBC | SQL, schema và index của database quan hệ bên dưới |
| Spring Data MongoDB | Filter, aggregation, compound index, collation và explain của MongoDB |
| Elasticsearch | Query DSL, mapping, analyzer và cách field phục vụ tìm kiếm hoặc sort |
| Cassandra | Partition key, clustering key và mô hình dữ liệu theo đường truy cập |
| Redis | Thiết kế key, cấu trúc dữ liệu và cơ chế lập chỉ mục mà module sử dụng |
| JPA | SQL provider thực sự sinh, mapping quan hệ và optimizer của database |

Bảng này chỉ định nơi cần tìm giải pháp, không khẳng định mọi module có cùng loại secondary index hoặc cùng cách tối ưu. Đặc biệt, thay API imperative bằng reactive không tự thay đổi đường truy cập dữ liệu tại server.

## 9. Tính chi phí của index trên toàn bộ workload

Một index thêm vào có thể giảm chi phí đọc nhưng làm tăng:

- Dung lượng lưu trữ và lượng dữ liệu cần nằm trong cache.
- Công việc khi insert, update và delete.
- Chi phí xây dựng, bảo trì và thay đổi schema.
- Khả năng trùng lặp với index hiện có mà chưa tạo lợi ích tương ứng.

Với ví dụ trạng thái đơn hàng thay đổi thường xuyên, cần tính cả chi phí cập nhật những index chứa status. Với một field Boolean, không kết luận “không bao giờ nên index” chỉ vì ít giá trị; vai trò của nó trong một compound hoặc partial index và phân bố workload mới là điều cần xem xét.

Tương tự, không luôn đặt field “chọn lọc nhất” lên đầu rồi bỏ qua các mẫu equality, sort, range và các truy vấn dùng chung prefix.

### 9.1. Partial index và index chuyên biệt cần điều kiện sử dụng rõ

Một số engine hỗ trợ index chỉ cho tập dữ liệu có điều kiện hoặc các loại index chuyên biệt. Chúng có thể phù hợp workload hẹp, nhưng query phải tương thích với điều kiện và khả năng planner nhận ra sự tương thích đó.

Nếu ứng dụng truyền trạng thái bằng tham số và có cơ chế plan tái sử dụng, cần kiểm tra đúng đường thực thi đó. Không suy ra một kết quả explain với literal sẽ luôn đại diện cho mọi lần gọi prepared query.

### 9.2. Chỉ giữ index có giá trị được xác nhận

Đánh giá index mới cùng mức sử dụng của các index cũ. Một index có prefix tương tự không mặc định thay thế hoàn toàn index khác: còn khác sort, uniqueness, điều kiện, collation hoặc kích thước.

Mọi quyết định bỏ index phải dựa trên tập truy vấn cần phục vụ và cách quản lý thay đổi của store, không chỉ dựa vào một endpoint vừa đo.

## 10. Một quy trình tối ưu có thể kiểm chứng

1. Ghi rõ hợp đồng query: filter, tenant, sort, kiểu kết quả và giới hạn.
2. Đo độ trễ và xác định phần chi phí đáng chú ý của đường đi request.
3. Quan sát truy vấn, tham số và các lượt truy cập phát sinh.
4. Dùng công cụ plan hoặc explain của đúng hệ lưu trữ với dữ liệu đại diện.
5. Đưa ra một giả thuyết cụ thể: index, cấu trúc query, projection, fetch hoặc phân trang.
6. Thử thay đổi có phạm vi rõ ràng trong môi trường đo phù hợp.
7. Đo lại cả đọc lẫn ảnh hưởng lên ghi và tài nguyên.
8. Kiểm tra kết quả nghiệp vụ không thay đổi ngoài phần API đã chủ động thiết kế lại.

Một bản ghi kết quả thử nghiệm nên giải thích được:

```text
Mẫu truy vấn nào được tối ưu?
Dữ liệu và nhóm tham số nào được dùng?
Chi phí trước thay đổi nằm ở đâu?
Điều gì đã thay đổi trong query hoặc kế hoạch thực thi?
Số liệu quan sát có cải thiện theo mục tiêu không?
Ảnh hưởng tới ghi, dung lượng và các query khác thế nào?
Các giả định nào còn giới hạn kết luận?
```

Không dùng thời gian duy nhất của một lần chạy để kết luận. Cache, cạnh tranh và dữ liệu có thể làm chênh lệch đáng kể giữa các lần đo.

## 11. Giữ nguyên tính đúng đắn trong khi tối ưu

| Thay đổi | Điều cần xác nhận lại |
| --- | --- |
| Thêm hoặc đổi compound index | Query thực tế và các biến thể còn được phục vụ phù hợp |
| Đổi điều kiện ngày sang khoảng | Múi giờ và hai cận có cùng ngữ nghĩa |
| Chuyển sang projection | Đủ trường cần dùng, đúng null và mapping |
| Tối ưu join hoặc fetch | Không mất bản ghi hoặc tạo trùng entity ngoài hợp đồng |
| Đổi Page thành Slice | API không còn hứa tổng số phần tử nếu không tính tổng |
| Chuyển sang keyset | Cursor chứa đúng khóa, giữ filter và thứ tự ổn định |
| Tối ưu case-insensitive search | Quy tắc case, collation và Unicode vẫn phù hợp |
| Đưa truy vấn về custom repository | Giữ phạm vi dữ liệu, transaction và xử lý lỗi cần thiết |

Một kế hoạch nhanh hơn vì bỏ mất tenant hoặc thay inner join làm loại bản ghi không có quan hệ không phải tối ưu đúng cho cùng yêu cầu. Hiệu năng phải đi cùng ngữ nghĩa kết quả được xác định trước.

Chọn index hoặc sửa câu truy vấn là quyết định tại nơi dữ liệu được tổ chức và thực thi. Spring Data Commons giúp biểu đạt hợp đồng truy cập; để cải thiện hiệu năng, cần lần theo hợp đồng đó đến đúng store module, quan sát query và plan, rồi chấp nhận thay đổi dựa trên số liệu cùng tác động của toàn bộ workload.
