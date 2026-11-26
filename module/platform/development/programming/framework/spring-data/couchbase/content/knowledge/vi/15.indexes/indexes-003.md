# Chỉ mục ghép và thứ tự các trường trong Spring Data Couchbase

Khi một truy vấn SQL++ vừa lọc theo khách hàng, trạng thái, thời gian, vừa sắp xếp và phân trang, chỉ mục đơn trên từng trường thường chưa đủ hiệu quả. **Chỉ mục ghép (composite index)** cho phép Couchbase tổ chức các entry theo nhiều khóa được sắp xếp theo một thứ tự xác định. Thứ tự đó quyết định truy vấn nào có thể thu hẹp phạm vi quét, tận dụng sắp xếp từ index và tránh đọc thừa document.

Bài thuộc chương **Chỉ mục** của module **SPRING_DATA_COUCHBASE**. Nội dung bám sát cách phát triển tầng truy cập dữ liệu bằng Spring Data Couchbase: ánh xạ document trong bucket/scope/collection, repository, `CouchbaseTemplate` và SQL++; đồng thời liên hệ đến hiệu năng ghi, TTL, CAS, giao dịch, scan consistency và reactive API khi vận hành thực tế.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích cách composite index được sắp theo thứ tự khóa và vì sao hai index chứa cùng trường nhưng khác thứ tự không tương đương.
2. Phân tích **khóa dẫn đầu (leading key)**, **tiền tố khóa (leftmost prefix)**, điều kiện bằng, khoảng, `IN` và `ORDER BY`.
3. Đề xuất chỉ mục cho truy vấn repository/SQL++ nhiều điều kiện, phân biệt tác động của thứ tự khóa lọc với hướng `ASC`/`DESC`.
4. Dùng `EXPLAIN`, Query Profile và thống kê truy vấn để xác nhận việc quét index, `Fetch` và sắp xếp.
5. Cân bằng lợi ích đọc với chi phí lưu trữ, cập nhật chỉ mục, phân trang và mức nhất quán của ứng dụng.

## 2. Bối cảnh: mẫu truy vấn quyết định cấu trúc index

Giả sử hệ thống quản lý đơn hàng đa khách thuê lưu các document trong:

| Thành phần | Tên minh họa |
| --- | --- |
| Bucket | `commerce` |
| Scope | `sales` |
| Collection | `orders` |
| Document ID | `order::1001` |

Document `order::1001`:

```json
{
  "_class": "com.example.sales.SalesOrder",
  "tenantId": "T-A",
  "customerId": "C-42",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "total": 1500000,
  "currency": "VND"
}
```

Trong ví dụ, `createdAt` là chuỗi ISO-8601 UTC với định dạng nhất quán để việc so sánh và sắp xếp chuỗi tương ứng với thứ tự thời gian. Khi dùng `Instant` hoặc bộ chuyển đổi của Spring Data, cần xác nhận **giá trị thực được lưu trong Couchbase** trước khi tạo index; cách biểu diễn có thể phụ thuộc mapping/conversion.

Xem hai yêu cầu nghiệp vụ:

- **Danh sách đơn hàng của tenant:** `WHERE tenantId = ? AND status = ? ORDER BY createdAt DESC LIMIT 20`.
- **Báo cáo toàn hệ thống:** `WHERE status = ? AND createdAt >= ? ORDER BY createdAt DESC`.

Hai câu cùng dùng `status` và `createdAt`, nhưng câu thứ nhất có bộ lọc `tenantId` còn câu thứ hai không có. Một index được thiết kế tốt cho câu thứ nhất chưa chắc tốt cho câu thứ hai. Đây là lý do **không chọn thứ tự khóa chỉ từ danh sách trường trong entity**.

## 3. Composite index là gì?

Một secondary index ghép bao gồm nhiều khóa, thường là các đường dẫn/biểu thức trên document. Ví dụ:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `status`,
    `createdAt` DESC
);
```

Về mặt khái niệm, các entry của index được sắp theo **bộ khóa**:

```text
(tenantId, status, createdAt DESC) -> document

("T-A", "CANCELLED", "2026-11-23T07:00:00Z") -> order::...
("T-A", "PAID",      "2026-11-25T09:00:00Z") -> order::...
("T-A", "PAID",      "2026-11-20T08:15:00Z") -> order::1001
("T-A", "SHIPPED",   "2026-11-24T10:00:00Z") -> order::...
("T-B", "PAID",      "2026-11-25T11:00:00Z") -> order::...
```

Bảng trên chỉ minh họa thứ tự logic; không phải cấu trúc lưu trữ vật lý chính xác hay kết quả trả về của Couchbase. Trong mỗi nhóm cùng `tenantId`, các giá trị `status` đứng cạnh nhau; trong mỗi nhóm cùng hai khóa đầu, `createdAt` được sắp giảm dần.

Vì vậy, khi biết cả `tenantId = "T-A"` và `status = "PAID"`, Query Service có thể tìm một phạm vi rất hẹp chứa các đơn trả tiền của tenant A, đọc theo thứ tự mới nhất trước.

Nếu đổi thứ tự:

```sql
CREATE INDEX ix_orders_status_tenant_created
ON `commerce`.`sales`.`orders`(
    `status`,
    `tenantId`,
    `createdAt` DESC
);
```

Tập trường giống nhau, nhưng index được tổ chức trước tiên theo `status`, sau đó mới đến `tenantId`. Cả hai thường có thể đáp ứng truy vấn **cố định cả hai khóa bằng điều kiện `=`**; chúng khác biệt rõ với truy vấn chỉ lọc theo một trong hai trường và với các biến thể khác của workload.

> **Quy tắc nền tảng:** Chọn thứ tự khóa dựa trên *tập mẫu truy vấn cần phục vụ*, không dựa trên thứ tự các thuộc tính trong class Java hoặc thứ tự viết điều kiện trong `WHERE`.

## 4. Khóa dẫn đầu và quy tắc tiền tố trái

### 4.1. Tại sao khóa đầu quan trọng?

Với index:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);
```

Hãy xem các truy vấn sau:

| Điều kiện truy vấn | Khả năng tận dụng index | Giải thích |
| --- | --- | --- |
| `tenantId = ?` | Thường tốt | Giới hạn theo khóa đầu |
| `tenantId = ? AND status = ?` | Thường rất tốt | Giới hạn liên tiếp theo hai khóa đầu |
| `tenantId = ? AND status = ? AND createdAt >= ?` | Thường tốt | Hai khóa bằng trước khóa khoảng |
| `tenantId = ? AND createdAt >= ?` | Có thể tận dụng phần tenant, nhưng chưa tối ưu khoảng thời gian | Không cố định `status` nằm giữa |
| `status = ?` | Thường không hiệu quả với index này | Thiếu điều kiện cho khóa dẫn đầu `tenantId` |
| `createdAt >= ?` | Thường không hiệu quả với index này | Hai khóa dẫn đầu đều chưa được giới hạn |

Đây là **nguyên tắc thiết kế phổ biến**, không phải lời hứa optimizer luôn chọn hoặc bỏ qua index nào đó. Couchbase có thể dùng index để quét một phạm vi rộng hay đẩy một số điều kiện vào quá trình lọc, nhưng không nên xem những trường ở phía sau như một đường tra cứu độc lập hiệu quả khi thiếu khóa đầu.

Tư duy dễ nhớ:

```text
Index: (tenantId, status, createdAt DESC)

Tốt:     tenantId = ?  ->  status = ?  ->  createdAt range
Vừa:     tenantId = ?  ->  [thiếu status]  ->  lọc createdAt
Kém:     [thiếu tenantId]  ->  status = ?
```

### 4.2. Thứ tự viết các điều kiện trong `WHERE` có quan trọng không?

Hai truy vấn sau tương đương về điều kiện lọc:

```sql
-- Câu 1
SELECT META(o).id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A" AND o.status = "PAID";

-- Câu 2
SELECT META(o).id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.status = "PAID" AND o.tenantId = "T-A";
```

Optimizer phân tích biểu thức truy vấn; không cần đảo vị trí `AND` trong `WHERE` để “khớp” thứ tự index. Điều cần quan tâm là **thứ tự khóa trong định nghĩa index** và **loại điều kiện áp dụng lên mỗi khóa**.

### 4.3. Index có thể dùng chung đến đâu?

Index `(tenantId, status, createdAt DESC)` có thể phục vụ nhiều truy vấn dùng tiền tố `tenantId`, thậm chí `tenantId + status`. Nhưng không nên suy rằng nó thay thế hoàn toàn index `(tenantId, createdAt DESC)`: truy vấn `WHERE tenantId = ? ORDER BY createdAt DESC` thường không có cùng thứ tự `createdAt` trên **toàn tenant**, bởi trong index thứ nhất các entry còn phân thành những nhóm `status`.

Nếu cả hai mẫu đều quan trọng, phải đo và cân nhắc có cần hai index không. Một index ghép có nhiều khóa hơn không có nghĩa luôn tốt hơn một index ngắn hơn.

## 5. Thứ tự điều kiện bằng, khoảng và sắp xếp

### 5.1. Đặt nhóm lọc bằng trước khoảng trong mẫu truy vấn chính

Ví dụ API cần đơn hàng có:

```sql
SELECT META(o).id AS id, o.tenantId, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
  AND o.status = "PAID"
  AND o.createdAt >= "2026-11-01T00:00:00Z"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Ứng viên hợp lý:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `status`,
    `createdAt` DESC
);
```

Trước tiên index có thể giới hạn các nhóm `tenantId`, `status` bằng điều kiện bằng. Kế đó Query Service quét phạm vi thời gian phù hợp, có khả năng dùng thứ tự `createdAt DESC` từ index.

Nếu đổi sang `(tenantId, createdAt DESC, status)`, hệ thống vẫn có thể giới hạn tenant và thời gian, nhưng khi đã bước vào phạm vi `createdAt`, điều kiện `status` ở sau thường khó tạo một dải quét liên tục hẹp như với index có `status` trước `createdAt`. Kết quả là có thể phải xét nhiều entry không cùng trạng thái hơn.

**Cách nghĩ thực dụng:** Với mẫu `equality + equality + range + ORDER BY range-key`, thử index có các điều kiện bằng ở đầu, sau đó mới đến khóa khoảng/sắp xếp. Cuối cùng phải kiểm chứng trong `EXPLAIN` và dữ liệu thật vì optimizer còn nhiều lựa chọn khác.

### 5.2. Nhiều điều kiện bằng: trường nào đứng trước?

So sánh:

```sql
CREATE INDEX ix_a ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC
);

CREATE INDEX ix_b ON `commerce`.`sales`.`orders`(
    `status`, `tenantId`, `createdAt` DESC
);
```

Với `tenantId = ? AND status = ?`, cả hai index đều có khả năng áp dụng điều kiện bằng lên hai khóa đầu. Quyết định thứ tự nên xét:

- **Khả năng dùng lại tiền tố:** Nếu nhiều endpoint chỉ lọc theo tenant, `tenantId` đứng trước thường có lợi; nếu nhiều báo cáo lọc theo status toàn hệ thống, `status` đứng trước có thể có lợi.
- **Độ chọn lọc và phân bố dữ liệu:** Một tenant có thể có ít đơn nhưng một số tenant lại cực lớn; trạng thái `PAID` có thể chiếm đa số. Phân bố thực tế tác động đến số entry quét và kế hoạch chọn index.
- **Bảo đảm truy vấn nghiệp vụ:** Nếu mọi truy vấn phải ràng buộc tenant để phân vùng dữ liệu logic, đặt tenant đầu index giúp phản ánh mẫu truy cập đó.
- **Tác động đến các điều kiện về sau:** Khi có thêm khoảng hoặc sắp xếp, kiểm tra xem các khóa đứng trước chúng có được cố định bằng điều kiện bằng hay không.

Không có quy tắc tuyệt đối **“đặt trường có độ chọn lọc cao nhất lên đầu”** cho mọi composite index. Nếu câu query luôn có điều kiện bằng trên cả hai khóa đầu, sự khác biệt có thể chủ yếu nằm ở các truy vấn khác tận dụng tiền tố. Chọn theo **cả tập workload**.

### 5.3. `IN` khác một điều kiện bằng đơn

Giả sử muốn lấy đơn có hai trạng thái:

```sql
SELECT META(o).id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
  AND o.status IN ["PAID", "SHIPPED"]
ORDER BY o.createdAt DESC
LIMIT 20;
```

Index `(tenantId, status, createdAt DESC)` tổ chức kết quả theo **từng nhóm status**. Mỗi nhóm có thể được sắp `createdAt DESC`, nhưng hai nhóm ghép lại **không tự tạo thứ tự thời gian giảm dần trên toàn bộ kết quả**. Vì vậy kế hoạch có thể cần thêm operator `Order` hoặc bước hợp nhất có sắp xếp, tùy khả năng của phiên bản và cách optimizer lập kế hoạch.

Đừng khẳng định cứ có `createdAt DESC` trong index là `ORDER BY createdAt DESC` sẽ không phải sort. Hãy kiểm tra `EXPLAIN` trên đúng điều kiện `IN` và số giá trị thực.

## 6. Hướng khóa `ASC`/`DESC` và sự tương thích với `ORDER BY`

Khi định nghĩa index, mỗi khóa có thể được chỉ định hướng sắp:

```sql
CREATE INDEX ix_orders_tenant_created_desc
ON `commerce`.`sales`.`orders`(
    `tenantId` ASC,
    `createdAt` DESC
);
```

Với truy vấn:

```sql
SELECT META(o).id AS id, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Do `tenantId` được cố định bằng `=`, `createdAt DESC` là thứ tự trong phần dữ liệu tenant đã chọn. Nếu truy vấn/index đáp ứng các điều kiện pushdown khác, Query Service có thể bỏ được bước sắp xếp bổ sung và giới hạn sớm số kết quả.

Ngược lại:

```sql
SELECT META(o).id AS id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Truy vấn này **không cố định `status`**. Nếu chỉ có index `(tenantId, status, createdAt DESC)`, các entry sẽ được nhóm theo `status` trước; vì vậy index đó không cung cấp sẵn đúng thứ tự `createdAt` trên toàn tenant.

Các điểm cần phân biệt:

- `ORDER BY` phải tương thích với thứ tự của các khóa index còn biến thiên sau các khóa đã được cố định.
- Chỉ định `DESC` là hữu ích khi mẫu truy vấn cần mới nhất trước, nhưng **không có nghĩa** mọi truy vấn `DESC` đều buộc phải tạo index riêng; khả năng quét theo hướng ngược và pushdown phụ thuộc kế hoạch, hướng các khóa, và phiên bản.
- Với `ORDER BY createdAt DESC, orderNumber DESC`, nếu cần tối ưu cả hai trường, hãy cân nhắc đưa các khóa sắp xếp vào index theo thứ tự tương ứng sau các khóa bằng.
- Những document có cùng `createdAt` có thể không có thứ tự ổn định giữa các lần truy vấn nếu chỉ sort theo thời gian. Đối với phân trang ổn định, cần thêm khóa phụ có tính duy nhất hoặc thứ tự xác định, rồi kiểm tra index phục vụ đủ `ORDER BY` đó.

## 7. Kết nối với repository và `CouchbaseTemplate`

### 7.1. Document mapping và derived query

Entity minh họa:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;

    private String tenantId;
    private String customerId;
    private String status;
    private Instant createdAt;
    private long total;

    // Constructor, getter và setter được lược bỏ.
}
```

Repository:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    List<SalesOrder> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status
    );

    List<SalesOrder> findByTenantIdAndStatusAndCreatedAtGreaterThanEqualOrderByCreatedAtDesc(
        String tenantId, String status, Instant from
    );
}
```

Ví dụ gọi:

```java
var orders = repository.findByTenantIdAndStatusOrderByCreatedAtDesc(
    "T-A", "PAID"
);
```

Spring Data sẽ xây dựng truy vấn SQL++ theo các thuộc tính và phép lọc của tên phương thức (tùy phiên bản và cấu hình mapping). Composite index `(tenantId, status, createdAt DESC)` là một **ứng viên**, nhưng cần biết truy vấn thực tế có thêm `_class`, projection hoặc các điều kiện khác không.

> **Chú ý:** Phương thức trả `List<SalesOrder>` như trên có thể trả rất nhiều document nếu không giới hạn. Ở API thực, nên áp dụng giới hạn/phân trang phù hợp và xem xét projection khi chỉ cần một vài trường.

### 7.2. `@Query` minh họa giới hạn và phép lọc chính xác

```java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND tenantId = $1 AND status = $2 " +
           "ORDER BY createdAt DESC LIMIT 20")
    List<SalesOrder> findLatestPaidOrders(String tenantId, String status);
}
```

`#{#n1ql.selectEntity}` và `#{#n1ql.filter}` là biểu thức hỗ trợ tạo truy vấn phù hợp với mapping entity. Mẫu dùng `$1` và `$2` để truyền giá trị truy vấn thay vì ghép trực tiếp đầu vào thành chuỗi.

Trong Spring Data Couchbase, một truy vấn entity có thể cần bộ lọc kiểu `_class` hoặc alias đã cấu hình. Nếu Query Service phải lọc thêm `_class`, thứ tự khóa và khả năng covering có thể khác truy vấn SQL++ viết tay. Chỉ đánh giá index dựa trên câu SQL++ **thực sự được gửi từ ứng dụng**.

### 7.3. `CouchbaseTemplate` và reactive API

`CouchbaseTemplate` cho phép viết truy vấn linh hoạt thay vì dựa vào tên repository method; khi lệnh chạy qua SQL++, các quy tắc về khóa dẫn đầu, khoảng và thứ tự index vẫn giữ nguyên.

Tương tự, `ReactiveCouchbaseRepository` hoặc template reactive thay đổi cách ứng dụng xử lý I/O và stream kết quả, **không thay đổi thực tế** Query/Index Service phải quét bao nhiêu entry. Một query bị sắp xếp hoặc quét thừa vẫn có thể chậm dù API trả `Flux`. Hãy tối ưu đúng chỉ mục trước khi kiểm tra lợi ích xử lý reactive ở tải đồng thời cao.

## 8. `EXPLAIN`: kiểm chứng composite index và thứ tự khóa

### 8.1. Xem truy vấn có sử dụng index mong đợi không

```sql
EXPLAIN
SELECT META(o).id AS id, o.tenantId, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
  AND o.status = "PAID"
  AND o.createdAt >= "2026-11-01T00:00:00Z"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Trong kế hoạch, kiểm tra:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| `IndexScan` / `IndexScan3` | Optimizer chọn composite index nào? Có đúng `ix_orders_tenant_status_created` không? |
| `spans` hoặc range của index | `tenantId` và `status` đã được dùng để giới hạn dải quét chưa? `createdAt` có áp dụng range không? |
| `index_key` / `index_order` | Index có thứ tự và hướng khóa tương thích `ORDER BY` không? |
| `Filter` | Có điều kiện nào chỉ được lọc sau scan, làm tăng lượng dữ liệu cần xét? |
| `Fetch` | Query Service có phải đọc document gốc vì index chưa chứa đủ trường cần trả không? |
| `Order` | Có bước sort bổ sung hay có thể dùng thứ tự từ index? |
| `Limit` | Giới hạn kết quả có được áp dụng hiệu quả trong kế hoạch không? |

Tên toán tử và trường JSON thay đổi theo phiên bản Couchbase; thay vì phụ thuộc một tên tuyệt đối, hãy đọc **chức năng** trong kế hoạch cụ thể.

### 8.2. So sánh hai truy vấn chỉ khác điều kiện `status`

Truy vấn A:

```sql
EXPLAIN
SELECT META(o).id, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A" AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Truy vấn B:

```sql
EXPLAIN
SELECT META(o).id, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Đối với index `(tenantId, status, createdAt DESC)`, A cố định hai khóa đầu, còn B chỉ cố định `tenantId`. Vì vậy B có thể cần sort bổ sung hoặc chọn index khác. B là ứng viên cho index `(tenantId, createdAt DESC)` nếu đây là endpoint quan trọng.

Đây là cách thử nghiệm thực tế để thấy **một trường lọc thiếu đi có thể làm thay đổi cả phương án sắp xếp**.

### 8.3. Kiểm tra trạng thái chỉ mục

```sql
SELECT name, state, index_key, condition
FROM system:indexes
WHERE bucket_id = "commerce"
  AND scope_id = "sales"
  AND keyspace_id = "orders";
```

Chỉ mục cần được tạo và hoàn tất build, thường ở trạng thái `online`, trước khi optimizer có thể dùng. Để đánh giá thời gian thực, cần quan sát Query Profile/metrics trên dữ liệu có phân bố đại diện: số entry quét, document fetch, thời gian sort, độ trễ p95/p99 và tài nguyên Index Service.

Có thể dùng gợi ý `USE INDEX` để **chẩn đoán** hai index khi tìm hiểu kế hoạch:

```sql
EXPLAIN
SELECT META(o).id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
USE INDEX (ix_orders_tenant_status_created USING GSI)
WHERE o.tenantId = "T-A" AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Hint cho phép thử một đường truy cập, nhưng **không nên mặc định ép index trong mọi truy vấn production**: hint có thể trở nên không tối ưu khi dữ liệu, cardinality hoặc danh sách index thay đổi. So sánh kế hoạch có/không có hint cùng metrics trước khi quyết định.

## 9. Mở rộng: covering index, biểu thức và partial index

### 9.1. Thứ tự khóa và covering là hai mục tiêu khác nhau

Giả sử bảng danh sách chỉ cần `tenantId`, `status`, `createdAt` và `total`:

```sql
CREATE INDEX ix_orders_list_cover
ON `commerce`.`sales`.`orders`(
    `tenantId`, `status`, `createdAt` DESC, `total`
);

SELECT o.tenantId, o.status, o.createdAt, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A" AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Ba khóa đầu phục vụ lọc và sắp xếp; `total` ở sau giúp truy vấn có cơ hội lấy đủ thông tin từ index mà không phải `Fetch` JSON gốc. Một index được gọi là **covering** đối với *truy vấn cụ thể*, không phải mọi query dùng index đó.

Nếu repository trả đầy đủ entity, gồm các trường ngoài index và metadata mapping, kế hoạch có thể vẫn phải `Fetch`. Tăng số trường trong index để cover mọi entity thường không kinh tế; hãy đo lợi ích trên các projection nhỏ, đọc nhiều.

### 9.2. Khi trường lọc là một biểu thức

Truy vấn:

```sql
SELECT META(o).id, o.customerId
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "T-A"
  AND LOWER(o.customerId) = "c-42";
```

Một index chỉ chứa `customerId` thuần túy không đồng nghĩa khớp hoàn toàn phép so sánh `LOWER(customerId)`. Có thể thiết kế **expression index** theo mẫu dùng thật:

```sql
CREATE INDEX ix_orders_tenant_customer_lower
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    LOWER(`customerId`)
);
```

Biểu thức trong query phải tương thích với biểu thức index để optimizer có thể sử dụng. Nếu có thể chuẩn hóa dữ liệu ngay khi ghi, cũng nên cân nhắc tránh áp dụng hàm ở mọi truy vấn; chọn dựa trên yêu cầu dữ liệu và đo lường.

### 9.3. Khi chỉ truy vấn một tập document có điều kiện cố định

Nếu dashboard luôn lọc `status = "OPEN"` và `tenantId = ?`, có thể dùng partial index:

```sql
CREATE INDEX ix_orders_open_tenant_created
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `createdAt` DESC
)
WHERE `status` = "OPEN";
```

Index này gồm những entry thỏa predicate `status = "OPEN"`. Nó có thể nhỏ hơn index chứa tất cả trạng thái; nhưng chỉ phù hợp khi truy vấn **hàm ý được điều kiện partial index**. Nếu `status` là tham số động, phải xác minh prepared query và kế hoạch thực tế, không mặc định index được chọn cho mọi giá trị.

## 10. Lưu ý vận hành: nhiều index hơn không luôn tốt hơn

Composite index thường giúp giảm số entry quét, nhưng mỗi index là cấu trúc phải được duy trì khi document thay đổi. Thêm nhiều index gần giống nhau có thể làm:

- Tăng dung lượng index, tài nguyên Index Service và thời gian build.
- Tăng công việc cập nhật khi insert, update, delete hoặc document hết hạn theo TTL.
- Phức tạp hóa lựa chọn của optimizer và quy trình triển khai, điều chỉnh, gỡ bỏ.

Do đó, khi hai endpoint có thể dùng chung index, hãy đo xem việc dùng chung có đủ hiệu năng không trước khi tạo thêm index. Khi các mẫu truy vấn có **thứ tự khóa dẫn đầu khác nhau** hoặc yêu cầu sắp xếp không tương thích, nhiều index chuyên biệt đôi khi cần thiết.

**Tính nhất quán không do thứ tự index quyết định.** GSI được cập nhật bất đồng bộ với KV write; truy vấn SQL++ dùng `NOT_BOUNDED` có thể tạm đọc dữ liệu cũ sau khi `save(...)`. `REQUEST_PLUS` yêu cầu chờ index bắt kịp cập nhật có liên quan, giúp kết quả mới hơn nhưng có thể tăng độ trễ. Đọc lại một document đã biết ID bằng KV là trường hợp khác với lọc tập document qua SQL++.

CAS hỗ trợ cập nhật có điều kiện theo version document, giao dịch cung cấp phạm vi nguyên tử theo cơ chế giao dịch, còn TTL liên quan vòng đời document. Cả ba không thể sửa một truy vấn bị quét index rộng do đặt sai thứ tự trường. Ngược lại, index phù hợp cũng không tự giải quyết xung đột ghi hoặc yêu cầu nhất quán của nghiệp vụ.

## 11. Bài thực hành thiết kế thứ tự khóa từ workload

Giả sử có bốn endpoint cùng dùng `commerce.sales.orders`:

| API | SQL++ cốt lõi | Index khởi đầu đáng thử |
| --- | --- | --- |
| A. Danh sách theo tenant và trạng thái | `tenantId = ? AND status = ? ORDER BY createdAt DESC` | `(tenantId, status, createdAt DESC)` |
| B. Đơn mới của tenant, mọi trạng thái | `tenantId = ? ORDER BY createdAt DESC` | `(tenantId, createdAt DESC)` |
| C. Báo cáo đơn trả tiền toàn hệ thống | `status = ? AND createdAt >= ?` | `(status, createdAt DESC)` |
| D. Lịch sử của một khách trong tenant | `tenantId = ? AND customerId = ? ORDER BY createdAt DESC` | `(tenantId, customerId, createdAt DESC)` |

Các index trong bảng là **ứng viên** cần kiểm chứng, không phải danh sách bắt buộc phải tạo. Nếu B ít dùng và chấp nhận độ trễ cao hơn, nhóm có thể cân nhắc chưa tạo index riêng. Nếu C quét phần lớn đơn toàn hệ thống, cần đo độ chọn lọc của `status` và giới hạn ngày trước khi kỳ vọng một index sẽ giải quyết hết chi phí truy vấn.

### Thực hiện từng bước

**Bước 1 — Ghi lại SQL++ thực.** Kiểm tra câu lệnh phát sinh từ repository, `@Query` hoặc `CouchbaseTemplate`, bao gồm `_class`, `ORDER BY`, `LIMIT`, bộ lọc khoảng và projection.

**Bước 2 — Phân nhóm khóa theo vai trò.** Đánh dấu trường được so bằng, trường được so khoảng, trường sắp xếp và trường chỉ nằm trong `SELECT`. Đặc biệt, không đặt một trường chỉ để hiển thị lên trước trường dùng lọc chỉ vì nó xuất hiện đầu tiên trong entity.

**Bước 3 — Đề xuất ít nhất hai thứ tự khi có nhiều mẫu truy vấn.** Chẳng hạn so sánh `(tenantId, status, createdAt DESC)` với `(status, tenantId, createdAt DESC)`. Đối chiếu số endpoint có thể dùng tiền tố của mỗi cách.

**Bước 4 — Kiểm tra kế hoạch.** Chạy `EXPLAIN` cho A, B, C, D với từng index. Kiểm tra `IndexScan`, spans, `Order`, `Fetch` và các điều kiện không được đẩy xuống scan.

**Bước 5 — Đo trên dữ liệu đại diện.** Dùng Query Profile/metrics ở tập dữ liệu đủ lớn, có phân bố tenant lớn/nhỏ và trạng thái phổ biến/hiếm. Đo cả thời gian response và chi phí insert/update khi thêm index.

**Bước 6 — Giữ lại index thật sự cần.** Tài liệu hóa endpoint sử dụng index, đặt tên rõ ràng và xác minh kế hoạch của các endpoint trước khi loại bỏ index cũ.

### Câu hỏi tự kiểm tra

1. Với index `(tenantId, status, createdAt DESC)`, vì sao `WHERE tenantId = ? AND status = ?` có lợi hơn `WHERE status = ?`?
2. Vì sao `WHERE tenantId = ? ORDER BY createdAt DESC` có thể cần một index khác nếu index hiện có chèn `status` giữa `tenantId` và `createdAt`?
3. Khi cả `tenantId` và `status` đều được so bằng, trường nào nên đứng trước? Cần xem thêm mẫu truy vấn gì trước khi quyết định?
4. Vì sao `status IN ["PAID", "SHIPPED"]` có thể cần sắp xếp bổ sung dù khóa `createdAt DESC` nằm trong index?
5. Sự khác nhau giữa “index có chứa trường `total`” và “index cover được truy vấn” là gì?
6. Vì sao cần phân tích SQL++ được Spring Data thực sự phát ra, thay vì chỉ nhìn tên phương thức repository?

**Kết luận:** Composite index phát huy sức mạnh khi **thứ tự khóa phản ánh cách truy vấn thu hẹp dữ liệu và sắp xếp kết quả**. Trong Spring Data Couchbase, bắt đầu từ SQL++ thật của repository/template, đặt các khóa bằng thường xuyên dùng chung trước khóa khoảng hoặc sắp xếp, xem xét khả năng dùng lại tiền tố và kiểm tra `EXPLAIN`. Một thiết kế tốt luôn cân đối hiệu năng truy vấn với chi phí duy trì chỉ mục và yêu cầu nhất quán của hệ thống.
