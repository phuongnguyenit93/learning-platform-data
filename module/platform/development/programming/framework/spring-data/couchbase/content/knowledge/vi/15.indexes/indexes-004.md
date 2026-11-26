# Chỉ mục có điều kiện theo loại entity hoặc điều kiện nghiệp vụ trong Spring Data Couchbase

Một collection Couchbase có thể chứa nhiều loại document: đơn hàng, hoàn tiền, sự kiện hoặc các phiên bản dữ liệu cũ. Ngay cả khi collection chỉ chứa đơn hàng, hầu hết màn hình thường xuyên đọc một tập nhỏ như **đơn đang mở**, **đơn chưa xóa mềm** hoặc **đơn của tenant hiện tại**. Đánh chỉ mục toàn bộ document trong mọi trường hợp có thể làm index phình to và tăng chi phí cập nhật.

**Chỉ mục có điều kiện** (*partial index*, hay *filtered secondary index*) chỉ chứa các entry ứng với document thỏa một điều kiện `WHERE` được định nghĩa khi tạo index. Trong **Spring Data Couchbase**, nó đặc biệt hữu ích khi truy vấn repository có điều kiện theo loại entity (ví dụ `_class`) hoặc có bộ lọc nghiệp vụ cố định.

Bài thuộc chương **Chỉ mục** của module **SPRING_DATA_COUCHBASE**. Các ví dụ gắn với document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời phân tích tác động lên thiết kế bucket/scope/collection, chi phí ghi, TTL, CAS, giao dịch, tính nhất quán và API reactive. Tên bucket/scope/collection và lớp Java trong bài là minh họa; phải đối chiếu với cấu hình và document thực tế của dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cơ chế của partial index và điểm khác nhau giữa **điều kiện tạo index** với **khóa lưu trong index**.
2. Thiết kế index cho collection chứa nhiều loại entity, dựa trên trường phân biệt kiểu như `_class` và metadata mapping thực tế.
3. Thiết kế index cho điều kiện nghiệp vụ ổn định như `status = "OPEN"`, `deleted = FALSE` hoặc một tập trạng thái cụ thể.
4. Hiểu khi nào một SQL++ query có thể dùng partial index, tại sao tham số động hoặc bộ lọc kiểu không khớp có thể làm optimizer bỏ qua index.
5. Kiểm tra bằng `EXPLAIN` và cân nhắc hiệu năng, chi phí duy trì, phân trang, cập nhật và scan consistency trước khi triển khai.

## 2. Bối cảnh: một collection, nhiều nhóm document

Giả sử hệ thống bán hàng lưu ở:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Bucket | `commerce` |
| Scope | `sales` |
| Collection | `business_docs` |
| Document ID đơn hàng | `order::2001` |
| Document ID hoàn tiền | `refund::3301` |

Collection `commerce.sales.business_docs` lưu cả đơn hàng lẫn hoàn tiền. Một đơn hàng được lưu như sau:

```json
{
  "_class": "salesOrder",
  "tenantId": "T-A",
  "customerId": "C-42",
  "status": "OPEN",
  "deleted": false,
  "createdAt": "2026-11-20T08:15:00Z",
  "total": 1500000
}
```

Một document hoàn tiền trong cùng collection:

```json
{
  "_class": "refund",
  "tenantId": "T-A",
  "orderId": "order::2001",
  "status": "APPROVED",
  "createdAt": "2026-11-21T09:00:00Z",
  "amount": 300000
}
```

Trong ví dụ, `_class` lưu alias kiểu `salesOrder` hoặc `refund`. Spring Data Couchbase có thể dùng khóa phân biệt kiểu để biết class Java cần ánh xạ. **Không được giả định mọi dự án đều lưu nguyên các giá trị minh họa:** project có thể lưu tên class đầy đủ, alias từ `@TypeAlias`, hoặc dùng cấu hình type key riêng. Trước khi viết điều kiện index, phải xem document thực và SQL++ thực sự do repository tạo.

Màn hình “Đơn đang mở” chỉ cần các document có:

```sql
WHERE _class = "salesOrder"
  AND status = "OPEN"
  AND deleted = FALSE
  AND tenantId = "T-A"
```

Nếu tập đơn đang mở chỉ chiếm một phần nhỏ dữ liệu, index có điều kiện có thể nhỏ và tập trung hơn index ghi nhận cả đơn đã đóng, đơn xóa mềm và hoàn tiền.

## 3. Cơ chế của partial index

Cú pháp cơ bản của một secondary index có điều kiện:

```sql
CREATE INDEX index_name
ON `commerce`.`sales`.`business_docs`(expression1, expression2)
WHERE some_condition;
```

Ở đây có **hai phần khác nhau**:

- **Khóa index**, đặt trong dấu ngoặc sau tên collection: quyết định entry được tổ chức theo trường/biểu thức nào và thứ tự ra sao.
- **Predicate của index**, đặt sau `WHERE`: quyết định **document nào được đưa vào index**.

Ví dụ:

```sql
CREATE INDEX ix_open_orders_tenant_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`,
    `createdAt` DESC
)
WHERE `_class` = "salesOrder"
  AND `status` = "OPEN"
  AND `deleted` = FALSE;
```

Chỉ các document đồng thời thỏa **ba điều kiện cố định** mới có entry trong index. Bên trong tập đó, index được tổ chức theo `tenantId` và `createdAt DESC`. Không bắt buộc đưa `_class`, `status` và `deleted` vào danh sách khóa nếu giá trị của chúng đã được cố định bằng predicate. Tuy nhiên, khả năng *covering* và cách optimizer xử lý projection vẫn cần kiểm chứng riêng.

Ví dụ diễn giải logic:

```text
Collection business_docs
 ├─ salesOrder / OPEN   / deleted=false / tenant=T-A   -> CÓ entry
 ├─ salesOrder / PAID   / deleted=false / tenant=T-A   -> KHÔNG
 ├─ salesOrder / OPEN   / deleted=true  / tenant=T-A   -> KHÔNG
 ├─ salesOrder / OPEN   / deleted=false / tenant=T-B   -> CÓ entry
 └─ refund     / OPEN   / deleted=false / tenant=T-A   -> KHÔNG

Index entries (tenantId, createdAt DESC) của những document được chọn
```

Lưu ý: index trên không chỉ dành cho tenant `T-A`; nó nhận mọi tenant miễn document thỏa điều kiện về loại, trạng thái và xóa mềm. Truy vấn vẫn phải có predicate `tenantId = ?` nếu ứng dụng cần tách dữ liệu theo tenant.

### Partial index khác gì composite index?

**Composite index** mô tả index có nhiều khóa; **partial index** mô tả index chỉ chứa một phần document. Hai đặc điểm này kết hợp được: `(tenantId, createdAt DESC) WHERE status = "OPEN"` vừa là composite index, vừa là partial index. Một index chỉ có khóa `email` nhưng kèm `WHERE active = TRUE` cũng là partial index.

### Partial index không phải cơ chế kiểm soát quyền truy cập

Điều kiện `WHERE` của index nhằm **tối ưu đường truy cập dữ liệu**. Nó không chặn các truy vấn khác đọc document ngoài index nếu người dùng có quyền query và có đường truy cập khác. Với hệ thống đa tenant, ứng dụng vẫn phải kiểm tra quyền và đưa điều kiện tenant phù hợp vào từng truy vấn; không thể dùng partial index thay thế authorization.

## 4. Chỉ mục theo loại entity: dùng đúng discriminator

### 4.1. Khi nào cần phân biệt loại entity?

Một collection có thể chứa nhiều kiểu document khi ứng dụng dùng mô hình lưu chung, khi chuyển đổi schema hoặc khi có dữ liệu lịch sử. Giả sử repository chuyên truy vấn `SalesOrder` mà không cần document `Refund`. Nếu tất cả các truy vấn đều có bộ lọc discriminator, một index giới hạn theo kiểu có thể giảm số entry.

Ví dụ:

```sql
CREATE INDEX ix_sales_orders_tenant_status_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`, `status`, `createdAt` DESC
)
WHERE `_class` = "salesOrder";
```

Truy vấn tương ứng:

```sql
SELECT META(d).id AS id, d.tenantId, d.status, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.tenantId = "T-A"
  AND d.status = "OPEN"
ORDER BY d.createdAt DESC
LIMIT 20;
```

Predicate của truy vấn xác định đúng kiểu `salesOrder`, vì vậy về mặt logic nó **hàm ý được** điều kiện `WHERE _class = "salesOrder"` của index. Khi các điều kiện còn lại và chi phí phù hợp, optimizer có cơ sở sử dụng index này.

### 4.2. Phân biệt `@TypeAlias`, type key và giá trị đã lưu

Entity minh họa:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("business_docs")
@TypeAlias("salesOrder")
public class SalesOrder {
    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private boolean deleted;
    private Instant createdAt;
    private long total;

    // Constructor, getter và setter được lược bỏ.
}
```

`@TypeAlias("salesOrder")` minh họa cách dùng alias thay vì tên Java class đầy đủ trong hệ thống mapping hỗ trợ alias. Tuy nhiên, **định nghĩa Java không đủ để bảo đảm index đúng**: trước hết hãy đọc một document đã được persist và xem câu SQL++ repository đã gửi. Đặc biệt khi chuyển đổi từ dữ liệu cũ, cùng một loại nghiệp vụ có thể còn nhiều giá trị type key khác nhau.

| Dữ liệu lưu thật | Predicate index cần cân nhắc |
| --- | --- |
| `"_class": "salesOrder"` | `WHERE _class = "salesOrder"` |
| `"_class": "com.example.sales.SalesOrder"` | `WHERE _class = "com.example.sales.SalesOrder"` |
| Type key được cấu hình tên khác | Dùng **tên field thật** của cấu hình; xác minh SQL++ |
| Nhiều giá trị discriminator cùng tồn tại khi migration | Lập chiến lược chuyển đổi dữ liệu hoặc một predicate phục vụ được các giá trị đang có |

Với kế hoạch migration, có thể phải dùng predicate chấp nhận nhiều giá trị kiểu, ví dụ:

```sql
CREATE INDEX ix_orders_migration_tenant_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`, `createdAt` DESC
)
WHERE `_class` IN [
    "salesOrder",
    "com.example.sales.SalesOrder"
];
```

Nhưng **chỉ mục này không bảo đảm có thể dùng cho mọi truy vấn từ repository**. Bộ lọc mà repository phát ra phải hàm ý được predicate của index. Nếu repository chỉ tìm alias mới, nên kiểm tra dữ liệu cũ có cần hiển thị hay không; nếu có, phải thiết kế việc đọc và chuyển đổi dữ liệu chủ động. Đừng dựa vào index để “sửa” một mapping không nhất quán.

### 4.3. Khi không cần partial index theo loại

Nếu một collection chỉ chứa duy nhất một loại entity và không tồn tại document khác, predicate theo `_class` có thể không giảm đáng kể số entry. Nếu mọi truy vấn đã lọc theo `tenantId` với độ chọn lọc rất cao, một composite index thông thường có thể đã đủ tốt. Chỉ bổ sung predicate theo kiểu khi có **lợi ích thực tế về kích thước, scan hoặc chi phí**, thay vì áp dụng như quy tắc bắt buộc.

## 5. Chỉ mục theo điều kiện nghiệp vụ

### 5.1. Đơn đang mở: điều kiện ổn định

Giả sử dashboard chỉ hiển thị đơn `OPEN`, không xóa mềm:

```sql
CREATE INDEX ix_orders_open_tenant_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`,
    `createdAt` DESC
)
WHERE `_class` = "salesOrder"
  AND `status` = "OPEN"
  AND `deleted` = FALSE;
```

Truy vấn:

```sql
SELECT META(d).id AS id, d.tenantId, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.status = "OPEN"
  AND d.deleted = FALSE
  AND d.tenantId = "T-A"
ORDER BY d.createdAt DESC
LIMIT 20;
```

Đặt `status = "OPEN"` và `deleted = FALSE` trong predicate giúp index không lưu đơn đã hoàn tất hoặc đã xóa mềm. `tenantId` ở đầu danh sách khóa giúp giới hạn phạm vi quét trong từng tenant, `createdAt DESC` hỗ trợ lấy đơn mới nhất.

**Không đưa `tenantId = "T-A"` vào predicate** chỉ để phục vụ một tenant cụ thể nếu hệ thống có nhiều tenant tương tự. Việc tạo một index cho từng tenant dễ dẫn tới số lượng index lớn, khó quản lý. Một index theo `tenantId` làm khóa thường phù hợp hơn với workload đa tenant.

### 5.2. Chỉ lọc xóa mềm, không ràng buộc trạng thái

Một endpoint khác trả mọi đơn chưa bị xóa:

```sql
SELECT META(d).id, d.status, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.deleted = FALSE
  AND d.tenantId = "T-A"
ORDER BY d.createdAt DESC;
```

Index chỉ chứa đơn `OPEN` **không thể dùng làm toàn bộ nguồn dữ liệu cho truy vấn mọi trạng thái**. Hệ thống phải có một đường truy cập khác nếu vẫn cần đơn `PAID`, `CANCELLED`, v.v.

Ứng viên cho endpoint này:

```sql
CREATE INDEX ix_orders_not_deleted_tenant_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`, `createdAt` DESC
)
WHERE `_class` = "salesOrder"
  AND `deleted` = FALSE;
```

Predicate này rộng hơn: nhận cả đơn `OPEN`, `PAID` hay `CANCELLED` miễn chưa xóa mềm. Nó có thể phục vụ nhiều endpoint hơn nhưng cũng tạo nhiều entry hơn index chỉ cho `OPEN`.

### 5.3. Khi cần cả tập “đang xử lý” gồm nhiều trạng thái

Giả sử nghiệp vụ coi `OPEN` và `PROCESSING` là hai trạng thái cần theo dõi. Có thể xét predicate:

```sql
CREATE INDEX ix_active_workflow_tenant_status_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`, `status`, `createdAt` DESC
)
WHERE `_class` = "salesOrder"
  AND `status` IN ["OPEN", "PROCESSING"]
  AND `deleted` = FALSE;
```

Truy vấn cần bao phủ đúng phạm vi nghiệp vụ:

```sql
SELECT META(d).id, d.status, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.status IN ["OPEN", "PROCESSING"]
  AND d.deleted = FALSE
  AND d.tenantId = "T-A"
ORDER BY d.createdAt DESC;
```

Khi có nhiều trạng thái, index `(tenantId, status, createdAt DESC)` tổ chức thời gian **bên trong từng nhóm status**. Nó không tự bảo đảm các kết quả của mọi nhóm có thứ tự `createdAt DESC` toàn cục. `EXPLAIN` có thể vẫn chứa bước sắp xếp; cần đánh giá theo truy vấn thật.

### 5.4. Predicate nên dựa trên trạng thái ổn định, tránh “cửa sổ thời gian động”

Một yêu cầu kiểu “chỉ giữ các đơn của 7 ngày gần nhất” thay đổi liên tục theo đồng hồ. Thay vì cố tạo predicate index chứa thời điểm “hiện tại” biến đổi theo từng phút, hãy cân nhắc:

- Đưa `createdAt` vào khóa index để truy vấn dùng giới hạn khoảng thời gian có tham số.
- Dùng TTL nếu nghiệp vụ thật sự cho phép **hết hạn và xóa document** sau một thời điểm.
- Dùng trạng thái lưu sẵn hoặc tiến trình chuyển trạng thái được kiểm soát khi cần chỉ mục cho các giai đoạn nghiệp vụ ổn định.

TTL quyết định vòng đời dữ liệu, không đồng nghĩa partial index tự động hoạt động như một “index 7 ngày gần nhất” bất biến. Khi document hết hạn hoặc thay đổi trạng thái, các index liên quan sẽ cần cập nhật theo cơ chế của Couchbase.

## 6. Khi nào optimizer có thể dùng partial index?

Đây là quy tắc quan trọng nhất của bài:

> Truy vấn phải **hàm ý được** điều kiện lọc của index. Nếu index chỉ chứa các đơn `OPEN`, một truy vấn muốn lấy *mọi* trạng thái không thể chỉ đọc index đó mà vẫn cho kết quả đầy đủ.

Giả sử index có predicate:

```sql
WHERE _class = "salesOrder"
  AND status = "OPEN"
  AND deleted = FALSE
```

Hãy so sánh:

| Predicate trong truy vấn | Có hàm ý predicate của index? | Giải thích |
| --- | --- | --- |
| `_class = "salesOrder" AND status = "OPEN" AND deleted = FALSE` | Có | Khớp đầy đủ điều kiện cố định |
| Các điều kiện trên cộng `tenantId = ?` | Có | Chặt hơn index, phù hợp lọc theo khóa |
| `_class = "salesOrder" AND status = "OPEN"` | Không | Vẫn cần các document có `deleted = TRUE` |
| `_class = "salesOrder" AND deleted = FALSE` | Không | Cần cả các trạng thái khác `OPEN` |
| `_class = "refund" AND status = "OPEN" AND deleted = FALSE` | Không | Sai loại entity |
| `_class = "salesOrder" AND status IN ["OPEN", "PAID"] AND deleted = FALSE` | Không | Cần cả đơn `PAID` |
| `_class = "salesOrder" AND status = $status AND deleted = FALSE` | Phụ thuộc kế hoạch và giá trị | Giá trị tham số chưa chắc luôn là `OPEN` |

**Phân biệt điều kiện logic với kế hoạch tối ưu:** Hàng “Có” chỉ nói rằng truy vấn **có thể** dùng index về mặt ý nghĩa dữ liệu. Couchbase còn đánh giá điều kiện trên các khóa index, giá trị bị thiếu, khả năng covering, số lượng entry và chi phí kế hoạch. Hãy xem `EXPLAIN` để biết index có thật sự được chọn.

### 6.1. Vấn đề tham số động trong repository và prepared query

Ứng dụng thường gọi:

```java
repository.findByTenantIdAndStatusAndDeletedFalse(
    "T-A", "OPEN"
);
```

Trong derived query, giá trị `"OPEN"` thường được truyền như **tham số**, nên SQL++ có thể có điều kiện tương tự `status = $2`. Optimizer không nhất thiết chứng minh được `status` luôn là `"OPEN"` cho mọi lần chạy cùng prepared statement. Vì vậy không nên mặc định một partial index có predicate `status = "OPEN"` sẽ được dùng ổn định chỉ vì lần gọi hiện tại truyền `"OPEN"`.

Nếu endpoint có nghiệp vụ **luôn chỉ lấy đơn OPEN**, một truy vấn cố định điều kiện đó có thể dễ phù hợp với partial index hơn:

```sql
SELECT META(d).id, d.tenantId, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.status = "OPEN"
  AND d.deleted = FALSE
  AND d.tenantId = $tenantId
ORDER BY d.createdAt DESC
LIMIT 20;
```

Khi dùng `@Query`, có thể cố định điều kiện nghiệp vụ và chỉ bind các giá trị thay đổi như `tenantId`. Tuy nhiên, câu truy vấn cuối cùng, cách chuẩn bị statement và kết quả `EXPLAIN` vẫn phải được kiểm tra trong phiên bản Couchbase đang triển khai.

### 6.2. Sai khác về `NULL`, `MISSING` và giá trị mặc định

Truy vấn `deleted = FALSE` **không tương đương** với ý nghĩa nghiệp vụ “chưa từng được đánh dấu deleted” nếu dữ liệu cũ không có trường `deleted`. Document thiếu trường (giá trị `MISSING`), document có `NULL` và document có Boolean `FALSE` là các trường hợp khác nhau trong SQL++.

Nếu dữ liệu cũ chưa có `deleted`, bạn có hai hướng:

1. **Chuẩn hóa dữ liệu:** bổ sung `deleted = FALSE` cho các document thuộc diện đang hoạt động, rồi dùng predicate rõ ràng.
2. **Đổi định nghĩa truy vấn và index:** xử lý rõ trường bị thiếu, ví dụ với logic phù hợp nghiệp vụ như `deleted = FALSE OR deleted IS MISSING`; cần thử `EXPLAIN` vì biểu thức phức tạp có thể ảnh hưởng khả năng dùng index.

Đừng chỉ tạo index `WHERE deleted = FALSE` rồi kỳ vọng truy vấn phải lấy cả document thiếu `deleted` có thể dùng index đó và vẫn đầy đủ kết quả.

## 7. Liên hệ với Spring Data Couchbase

### 7.1. Repository truy vấn loại entity

Định nghĩa repository:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    List<SalesOrder> findByTenantIdAndStatusAndDeletedFalseOrderByCreatedAtDesc(
        String tenantId,
        String status
    );
}
```

Lời gọi:

```java
var result = repository
    .findByTenantIdAndStatusAndDeletedFalseOrderByCreatedAtDesc(
        "T-A", "OPEN"
    );
```

Spring Data Couchbase tạo SQL++ từ tên phương thức đối với truy vấn thuộc tính. Truy vấn có thể thêm bộ lọc theo loại entity dựa trên thông tin mapping, chẳng hạn `_class`, để không trả nhầm kiểu document trong collection dùng chung.

Cần xem bản SQL++ thực được gửi để biết:

- Bộ lọc kiểu dùng `_class`, alias khác, hay một điều kiện phức tạp hơn?
- `status` là literal `"OPEN"` hay tham số của prepared query?
- `deleted` được hiểu là Boolean `FALSE` hay logic chấp nhận `MISSING`?
- Truy vấn lấy một projection nhỏ hay toàn bộ entity cùng metadata?

Đặc biệt, tên Java method không thể thay thế `EXPLAIN`: việc có `AndDeletedFalse` không chứng minh index predicate đã tương thích với mọi phần khác của câu SQL++.

### 7.2. Dùng `@Query` cho điều kiện nghiệp vụ cố định

Một endpoint chỉ hiển thị đơn `OPEN` có thể khai báo câu truy vấn với literal:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface SalesOrderRepository
        extends CouchbaseRepository<SalesOrder, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
           "AND tenantId = $1 " +
           "AND status = \"OPEN\" AND deleted = FALSE " +
           "ORDER BY createdAt DESC LIMIT 20")
    List<SalesOrder> findLatestOpenOrders(String tenantId);
}
```

`#{#n1ql.selectEntity}` và `#{#n1ql.filter}` là biểu thức hỗ trợ truy vấn ánh xạ entity của Spring Data Couchbase. Trong ngữ cảnh phù hợp, chúng giúp chọn các trường cho mapping và thêm bộ lọc kiểu. Chúng **không** tự động tạo index hoặc bảo đảm một index cụ thể được chọn.

Chỉ có `tenantId` là tham số biến đổi; trạng thái `OPEN` được cố định ở câu truy vấn. Điều này làm điều kiện nghiệp vụ rõ hơn so với dùng `status = $2` cho một endpoint chuyên biệt. Dẫu vậy, phải so sánh SQL++ thực tế với predicate index `_class = "salesOrder" AND status = "OPEN" AND deleted = FALSE` để xác minh khả năng dùng index.

### 7.3. Khi dùng `CouchbaseTemplate`

`CouchbaseTemplate` cho phép xây dựng truy vấn linh hoạt và nhận kết quả được mapping thành entity. Nếu truy vấn đi qua SQL++, nó vẫn phải có đủ predicate cố định của partial index.

Ví dụ, một template query tương đương:

```sql
SELECT META(d).id AS id, d.*
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.status = "OPEN"
  AND d.deleted = FALSE
  AND d.tenantId = $tenantId
ORDER BY d.createdAt DESC
LIMIT 20;
```

Đây là **SQL++ minh họa về mặt điều kiện**. Cấu trúc `SELECT` và các trường metadata để mapping trong `CouchbaseTemplate` phụ thuộc phiên bản và API sử dụng; không sao chép nguyên truy vấn vào ứng dụng rồi giả định nó mapping đúng mọi entity.

Nếu template tạo truy vấn dùng tham số `status` tự do, cần kiểm tra lại kế hoạch khi muốn tối ưu bằng partial index chỉ cho `OPEN`. API truy vấn thay đổi nhưng quy tắc logic của optimizer không thay đổi.

### 7.4. Reactive API

`ReactiveCouchbaseRepository` hay API reactive của template giúp ứng dụng xử lý I/O bất đồng bộ, nhưng Query Service vẫn phải chọn và quét index. Nếu câu SQL++ không hàm ý predicate, reactive không khiến partial index trở nên hợp lệ. Hãy tối ưu câu truy vấn, index, projection, `LIMIT` và cách phân trang trước khi đánh giá hiệu năng tải đồng thời của `Mono`/`Flux`.

## 8. `EXPLAIN` và những dấu hiệu cần xem

### 8.1. Kiểm tra trước khi triển khai

Sau khi tạo:

```sql
CREATE INDEX ix_open_orders_tenant_created
ON `commerce`.`sales`.`business_docs`(
    `tenantId`, `createdAt` DESC
)
WHERE `_class` = "salesOrder"
  AND `status` = "OPEN"
  AND `deleted` = FALSE;
```

Chạy:

```sql
EXPLAIN
SELECT META(d).id AS id, d.tenantId, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.status = "OPEN"
  AND d.deleted = FALSE
  AND d.tenantId = "T-A"
ORDER BY d.createdAt DESC
LIMIT 20;
```

Kiểm tra các chi tiết:

| Dấu hiệu | Câu hỏi thực tế |
| --- | --- |
| `IndexScan` / `IndexScan3` | Có chọn `ix_open_orders_tenant_created` không? |
| `spans` / phạm vi scan | Có giới hạn được theo `tenantId` và thứ tự thời gian không? |
| `index_key` và `condition` | Khóa và predicate index có đúng như thiết kế không? |
| `Fetch` | Có phải lấy JSON từ Data Service để đủ trường kết quả hay kiểm tra điều kiện không? |
| `Filter` | Có nhiều entry bị loại sau khi index scan không? |
| `Order` | `ORDER BY createdAt DESC` có cần sort bổ sung không? |
| `Limit` | Đã giới hạn kết quả có hiệu quả trong kế hoạch chưa? |

Tên operator hoặc chi tiết JSON thay đổi theo phiên bản; hãy đọc ý nghĩa kế hoạch thay vì chỉ tìm một trường tên cố định.

### 8.2. Thử truy vấn khác đúng một điều kiện

So sánh truy vấn trên với:

```sql
EXPLAIN
SELECT META(d).id AS id, d.tenantId, d.createdAt
FROM `commerce`.`sales`.`business_docs` AS d
WHERE d._class = "salesOrder"
  AND d.tenantId = "T-A"
ORDER BY d.createdAt DESC
LIMIT 20;
```

Truy vấn thứ hai **không lọc `status` và `deleted`**; do đó partial index chỉ chứa `OPEN AND deleted=FALSE` không đủ dữ liệu để trả mọi đơn. Đây là cách kiểm tra tại sao một index rất hiệu quả cho dashboard có thể không phục vụ màn hình “lịch sử toàn bộ đơn”.

### 8.3. Xem thông tin index và trạng thái build

```sql
SELECT name, state, index_key, condition, is_primary
FROM system:indexes
WHERE bucket_id = "commerce"
  AND scope_id = "sales"
  AND keyspace_id = "business_docs";
```

Xác nhận index đã được build và ở trạng thái sử dụng được (thường là `online`). Một `CREATE INDEX` hoàn tất về mặt câu lệnh không có nghĩa index luôn sẵn sàng ngay trên lượng dữ liệu lớn.

Nếu index không được chọn, rà soát theo thứ tự:

1. Có đúng bucket/scope/collection và đúng môi trường chạy query không?
2. Giá trị discriminator thực có khớp `"salesOrder"` không?
3. Truy vấn có hàm ý **toàn bộ** điều kiện `WHERE` của index không?
4. Có `MISSING`/`NULL`/kiểu dữ liệu khác nhau giữa document cũ và mới không?
5. Câu query là literal hay prepared statement với tham số động?
6. Index đã `online` chưa, các khóa dẫn đầu có phù hợp predicate không?
7. Optimizer có kế hoạch khác rẻ hơn không?

Sau `EXPLAIN`, hãy đo Query Profile/metrics: entry được quét, document `Fetch`, thời gian query, độ trễ p95/p99 và mức sử dụng Index Service. Chỉ mục chỉ có giá trị nếu tác động của nó phù hợp với dữ liệu và tải thực.

## 9. Tác động của cập nhật, TTL, CAS, giao dịch và nhất quán

### 9.1. Document đi vào hoặc rời khỏi partial index

Khi đơn hàng từ `OPEN` chuyển sang `PAID`, nó không còn thỏa predicate `status = "OPEN"`; index phải được cập nhật để không còn entry của đơn đó. Khi document mới được tạo với `OPEN`, index cần thêm entry. Khi đặt `deleted = TRUE` hoặc document hết hạn bởi TTL, các index cũng phải phản ánh sự thay đổi tương ứng.

Do đó, dù partial index có ít entry hơn một index toàn phần, việc cập nhật trên trường điều kiện như `status` và `deleted` vẫn có chi phí. Với hệ thống chuyển trạng thái rất thường xuyên, hãy đo thêm write throughput và tải Index Service thay vì chỉ nhìn tốc độ đọc.

### 9.2. Partial index không bảo đảm nhìn thấy cập nhật tức thì

GSI được cập nhật bất đồng bộ so với thao tác KV. Sau khi lưu:

```java
// Minh họa logic nghiệp vụ, không phải implementation hoàn chỉnh.
order.setStatus("OPEN");
repository.save(order);
// Một SQL++ query theo status ngay sau đó có thể chưa thấy mutation mới.
```

Trong ứng dụng dùng API bất đồng bộ hoặc reactive, còn phải đợi thao tác lưu hoàn tất đúng cách trước khi đánh giá hành vi read-after-write.

| Scan consistency của SQL++ | Hành vi cần hiểu |
| --- | --- |
| `NOT_BOUNDED` | Không yêu cầu index bắt kịp các mutation trước khi quét; thường ít chờ hơn nhưng kết quả có thể tạm cũ |
| `REQUEST_PLUS` | Đợi index bắt kịp các mutation có liên quan tại thời điểm truy vấn; tăng độ mới của dữ liệu nhưng có thể tăng thời gian chờ |

Nếu cần đọc lại một document theo ID đã biết, KV `findById` là đường truy cập trực tiếp và không phụ thuộc GSI. Nếu cần truy vấn danh sách theo điều kiện, lựa chọn scan consistency phải dựa trên yêu cầu nghiệp vụ và phiên bản Spring Data Couchbase/SDK hiện dùng.

### 9.3. CAS và giao dịch giải quyết vấn đề khác

- **CAS** hỗ trợ cập nhật có kiểm tra phiên bản document, tránh ghi đè xung đột không mong muốn.
- **Giao dịch** xử lý tính nguyên tử theo phạm vi thao tác và cơ chế giao dịch được sử dụng.
- **Partial index** quyết định tập document có entry trong chỉ mục SQL++; **scan consistency** quyết định mức đồng bộ dữ liệu của truy vấn đối với index.

Các cơ chế này phối hợp để xây dựng ứng dụng nhất quán nhưng không thể thay thế nhau. Ví dụ, dùng CAS khi chuyển trạng thái `OPEN → PAID` không đảm bảo SQL++ ở mức `NOT_BOUNDED` ngay lập tức loại đơn đó khỏi mọi kết quả.

## 10. Lựa chọn partial index hay index toàn phần

Khi thiết kế cho một collection, có thể dùng bảng quyết định sau:

| Tình huống | Giải pháp đáng cân nhắc | Lý do |
| --- | --- | --- |
| Collection dùng chung nhiều entity, repository chỉ hỏi một loại | Partial index theo discriminator thực tế | Giảm entry của các entity khác |
| Dashboard luôn xem đơn `OPEN` và chưa xóa mềm | Partial index theo `status` + `deleted` | Tập đọc cố định, có thể nhỏ hơn tập đầy đủ |
| API tìm nhiều trạng thái do người dùng chọn | Composite index toàn phần hoặc partial rộng hơn | Dynamic status có thể không hàm ý predicate cố định |
| Hầu như toàn bộ document cùng loại và cùng trạng thái | Composite index thông thường | Partial predicate có thể tiết kiệm không đáng kể |
| Nhiều màn hình cần cả đơn cũ/đã đóng | Index phục vụ truy vấn tổng quát | Partial index cho `OPEN` không chứa đủ dữ liệu |
| Muốn tìm khách hàng chỉ theo ID | KV `findById` | Không cần SQL++ index |
| Cần giữ “7 ngày gần nhất” bằng đồng hồ | Index theo thời gian + query range, cân nhắc TTL | Trạng thái thời gian động không phù hợp predicate cố định |

Đừng tạo index riêng cho mọi biến thể kết hợp loại entity/trạng thái. Trước hết hãy gom các truy vấn quan trọng theo predicate, cân nhắc tỷ lệ document thỏa điều kiện, tần suất đọc/ghi và đo sự khác biệt giữa một index rộng với vài index chuyên biệt.

### Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tạo index `WHERE _class = "salesOrder"` nhưng repository không chọn | Giá trị thực là tên class đầy đủ hoặc query sinh bộ lọc khác | Xem document thực, logging SQL++ và `EXPLAIN` |
| Index `WHERE status = "OPEN"` ít khi dùng | Endpoint dùng `status = $1` hoặc hỏi nhiều trạng thái | Kiểm tra prepared query; cân nhắc literal cho endpoint cố định hoặc index toàn phần |
| Một số document cũ không xuất hiện | Thiếu trường `deleted` hoặc type key khác với predicate | Kiểm tra dữ liệu legacy, xử lý `MISSING`/migration |
| Index dùng được nhưng phải `Fetch` nhiều | Truy vấn trả toàn entity, index không cover projection | Thử projection hợp lý, đo trước khi tăng số khóa index |
| Query vẫn phải sort | Nhiều trạng thái hoặc thứ tự khóa không tương thích `ORDER BY` | Xem `Order` trong `EXPLAIN`, thiết kế lại khóa và hướng sort |
| Index rất nhỏ nhưng endpoint lịch sử lỗi hoặc chậm | Partial index thiếu đơn đã đóng, cần đường truy cập khác | Tạo index đáp ứng mẫu lịch sử, không ép dùng index `OPEN` |
| Dữ liệu vừa đổi trạng thái vẫn xuất hiện thoáng qua | Index update bất đồng bộ, scan consistency | Đánh giá `REQUEST_PLUS` hoặc KV theo ID cho trường hợp cần tính mới |

## 11. Bài thực hành: chọn điều kiện index cho ba endpoint

Giả sử collection `commerce.sales.business_docs` có 2 triệu document: 1,4 triệu `salesOrder`, 600 nghìn `refund`. Trong nhóm đơn hàng, 8% có `status = "OPEN"`, 3% được đánh dấu `deleted = TRUE`; các tỷ lệ chỉ mang tính minh họa.

Hệ thống cung cấp:

1. `GET /tenants/{id}/orders/open`: xem 20 đơn `OPEN` chưa xóa mềm mới nhất.
2. `GET /tenants/{id}/orders`: xem toàn bộ đơn của tenant, bất kể trạng thái, chưa xóa mềm.
3. `GET /tenants/{id}/refunds`: xem lịch sử hoàn tiền của tenant.

**Bước 1 — Viết predicate đúng cho từng endpoint.**

```sql
-- A: đơn mở
WHERE _class = "salesOrder"
  AND status = "OPEN"
  AND deleted = FALSE
  AND tenantId = $tenantId

-- B: mọi đơn chưa xóa
WHERE _class = "salesOrder"
  AND deleted = FALSE
  AND tenantId = $tenantId

-- C: hoàn tiền
WHERE _class = "refund"
  AND tenantId = $tenantId
```

**Bước 2 — Thiết kế index ứng viên.** Chọn `(tenantId, createdAt DESC)` cho A với predicate kết hợp theo loại, trạng thái, xóa mềm. B cần index rộng hơn với predicate `_class = "salesOrder" AND deleted = FALSE`. C có thể dùng index chỉ theo `_class = "refund"` với khóa phù hợp truy vấn của lịch sử hoàn tiền.

**Bước 3 — So sánh kích thước và khả năng dùng lại.** A có thể ít entry hơn B, nhưng A không thể làm nguồn dữ liệu hoàn chỉnh cho B. Với tỷ lệ `OPEN` chỉ 8%, việc giới hạn phạm vi có thể đáng giá nếu A là endpoint nóng; nếu A ít gọi, có thể chỉ giữ index B để giảm số index phải bảo trì.

**Bước 4 — Kiểm tra SQL++ phát sinh từ Spring Data.** Nếu `@TypeAlias` không khớp `_class` của document thật hoặc repository dùng tham số động cho trạng thái, kế hoạch có thể khác dự tính. Chạy `EXPLAIN` trên từng câu SQL++ thực tế và quan sát `IndexScan`, `Fetch`, `Order`.

**Bước 5 — Đo vận hành.** Theo dõi latency endpoint, số index entry quét, thời gian cập nhật khi chuyển `OPEN → PAID`, kích thước index, và ảnh hưởng của scan consistency khi UI yêu cầu thấy trạng thái mới.

### Câu hỏi tự kiểm tra

1. Trong `CREATE INDEX ... ON (...) WHERE ...`, phần khóa index khác phần predicate ở vai trò nào?
2. Vì sao `WHERE _class = "salesOrder"` chỉ phù hợp nếu document và bộ lọc kiểu từ repository thực sự dùng giá trị `"salesOrder"`?
3. Với index `WHERE status = "OPEN" AND deleted = FALSE`, truy vấn chỉ lọc `status = "OPEN"` có thể dùng index để trả **mọi** đơn đang mở không? Vì sao?
4. Khi một derived repository method nhận `status` là tham số, vì sao không nên mặc định partial index cho `"OPEN"` sẽ luôn được sử dụng?
5. Một document cũ không có trường `deleted` có thỏa `deleted = FALSE` không? Điều này ảnh hưởng index và kết quả truy vấn thế nào?
6. Tại sao partial index không thay thế kiểm tra quyền tenant hoặc cấu hình scan consistency?

**Kết luận:** Chỉ mục có điều kiện giúp Spring Data Couchbase tập trung tài nguyên index vào **đúng tập document được truy vấn thường xuyên**. Để dùng hiệu quả, cần xác nhận discriminator và giá trị lưu thật, thiết kế predicate cho điều kiện nghiệp vụ ổn định, bảo đảm SQL++ của repository hoặc template **hàm ý được** predicate của index, rồi xác minh kế hoạch bằng `EXPLAIN`. Chỉ chọn partial index khi lợi ích đọc và chi phí lưu trữ đủ bù cho công việc cập nhật, vận hành và nhu cầu phục vụ những truy vấn rộng hơn.
