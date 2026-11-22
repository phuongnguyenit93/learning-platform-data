# Khác biệt giữa xóa suy diễn, xóa qua CRUD và SQL DELETE trực tiếp trong Spring Data JDBC

## 1. Ba cách xóa dữ liệu, ba mức abstraction

Spring Data JDBC cho phép xóa dữ liệu theo nhiều cách. Cùng là xóa hàng trong database, nhưng cách gọi repository, cách framework hiểu aggregate và trách nhiệm xử lý quan hệ có thể khác nhau.

Ba nhóm thường gặp:

1. **Xóa suy diễn (derived delete):** khai báo method như `deleteByStatus(...)` hoặc `removeByCreatedAtBefore(...)`. Spring Data suy ra điều kiện từ tên method và property Java.
2. **Xóa qua CRUD repository:** gọi các method chuẩn như `delete(entity)`, `deleteById(id)`, `deleteAll(...)`. Đây là thao tác repository trên entity/aggregate root.
3. **SQL DELETE trực tiếp:** tự viết câu `DELETE FROM ...` bằng `@Modifying @Query` hoặc `JdbcTemplate`. Ứng dụng kiểm soát SQL và điều kiện xóa.

Điều cần cân nhắc không chỉ là cú pháp ngắn hay dài. Hãy xem xét **đơn vị bị xóa, cách xử lý các hàng con của aggregate, lifecycle callback, foreign key, transaction và số hàng bị tác động**.

## 2. Xóa suy diễn bằng deleteBy và removeBy

Derived delete là query method được suy ra từ tên phương thức. Phần sau `By` mô tả predicate theo property Java của entity.

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String customerCode;

    private String status;

    @Column("created_at")
    private Instant createdAt;

    // constructors, getters...
}
~~~

Repository có thể khai báo:

~~~java
import java.time.Instant;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    void deleteByStatus(String status);

    void removeByCreatedAtBefore(Instant cutoff);

    void deleteByCustomerCode(String customerCode);
}
~~~

Các tên method được hiểu như sau:

| Method | Điều kiện suy ra |
|---|---|
| `deleteByStatus(status)` | Property `status` bằng tham số |
| `removeByCreatedAtBefore(cutoff)` | Property `createdAt` nhỏ hơn mốc thời gian |
| `deleteByCustomerCode(code)` | Property `customerCode` bằng tham số |

`delete...By` và `remove...By` là hai cách đặt tên cho derived delete. Method name dùng **property Java**, không dùng tên cột vật lý. Trong ví dụ, `createdAt` được ánh xạ tới cột `created_at` qua `@Column`.

### 2.1. Khi nào dùng derived delete?

Dùng derived delete khi:

- Điều kiện đơn giản, dựa trên property của một entity.
- Tên method vẫn ngắn và dễ hiểu.
- Không cần viết SQL riêng.
- Phạm vi xóa được xác định rõ bằng predicate.
- Ứng dụng đã xác nhận hành vi của derived delete phù hợp với aggregate và schema đang dùng.

Ví dụ xóa các session đã hết hạn:

~~~java
void deleteByExpiresAtBefore(Instant cutoff);
~~~

Đây là cách khai báo gọn. Tuy nhiên, không nên xem tên method là bằng chứng rằng framework sẽ xóa cả mọi bảng con của aggregate theo cùng semantics với CRUD delete. Derived delete là query theo điều kiện; cần hiểu SQL mà phiên bản Spring Data JDBC tạo ra và cách schema xử lý foreign key.

### 2.2. Return type và số hàng bị xóa

Một derived delete có thể được khai báo với kiểu không trả dữ liệu, ví dụ `void`. Một số dạng query/phiên bản cho phép trả số lượng hàng bị tác động. Hãy xác nhận contract của Spring Data JDBC mà dự án đang dùng trước khi chọn kiểu số.

Ví dụ đơn giản:

~~~java
void deleteByStatus(String status);
~~~

Nếu nghiệp vụ cần báo số lượng đã xóa, không nên tự giả định method nào cũng hỗ trợ cùng kiểu return type. Có thể dùng một modifying query trả update count hoặc dùng API SQL tường minh khi cần kiểm soát chính xác.

### 2.3. Derived delete không đồng nghĩa với kiểm tra trước rồi xóa

Method:

~~~java
void deleteByCustomerCode(String customerCode);
~~~

là thao tác xóa theo điều kiện. Nó không có nghĩa là repository tự kiểm tra business key đã unique. Nếu nhiều hàng cùng mã, điều kiện có thể khớp nhiều hàng.

Nếu yêu cầu xóa đúng một khách hàng theo mã, hãy bảo vệ mã bằng unique constraint trong database. Không dựa vào giả định dữ liệu “thường chỉ có một hàng”.

## 3. Xóa qua CRUD repository

CRUD repository cung cấp các method xóa dựa trên identifier hoặc entity:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Các method thường dùng:

| Method | Ý nghĩa |
|---|---|
| `delete(entity)` | Xóa entity được truyền vào |
| `deleteById(id)` | Xóa entity theo identifier |
| `deleteAll(entities)` | Xóa các entity trong tập được truyền vào |
| `deleteAllById(ids)` | Xóa các entity có identifier trong tập |
| `deleteAll()` | Xóa toàn bộ dữ liệu thuộc repository |

Tên và contract cụ thể dựa trên repository interface mà ứng dụng kế thừa. Ví dụ trên dùng `CrudRepository`.

### 3.1. delete(entity)

Dùng khi ứng dụng đã có aggregate root và muốn xóa chính entity đó:

~~~java
Customer customer = customerRepository
        .findById(customerId)
        .orElseThrow();

customerRepository.delete(customer);
~~~

Cách này thể hiện rõ entity nào được xóa. Nó hữu ích khi trước lúc xóa cần kiểm tra quyền, trạng thái hoặc quy tắc nghiệp vụ:

~~~java
@Transactional
public void closeCustomer(Long id) {
    Customer customer = customers.findById(id)
            .orElseThrow(CustomerNotFoundException::new);

    if ("ACTIVE".equals(customer.getStatus())) {
        throw new IllegalStateException(
                "Không thể xóa khách hàng đang hoạt động"
        );
    }

    customers.delete(customer);
}
~~~

Không phải lúc nào cũng cần tải entity trước khi xóa. Nếu chỉ có ID và không cần kiểm tra trạng thái ở application, `deleteById` có thể đơn giản hơn.

### 3.2. deleteById(id)

~~~java
customerRepository.deleteById(customerId);
~~~

Method này nhắm tới identifier của aggregate root. Nó phù hợp khi caller đã biết ID và muốn dùng repository CRUD để thực hiện thao tác xóa.

Theo contract CRUD repository thông dụng, yêu cầu xóa một ID không tồn tại thường không được xem là lỗi “không tìm thấy” bắt buộc. Nếu nghiệp vụ cần phân biệt “đã xóa” và “không tồn tại”, hãy kiểm tra kết quả theo một cách tường minh hoặc dùng query trả số hàng bị tác động.

### 3.3. deleteAll và deleteAllById

Các method này hữu ích cho thao tác theo tập đã xác định:

~~~java
customerRepository.deleteAll(customersToRemove);

customerRepository.deleteAllById(customerIds);
~~~

Cần cẩn trọng với:

~~~java
customerRepository.deleteAll();
~~~

Method này có phạm vi rất rộng: xóa toàn bộ dữ liệu thuộc repository. Chỉ dùng khi đó thực sự là yêu cầu nghiệp vụ hoặc thao tác quản trị có kiểm soát. Với dữ liệu lớn, hãy xem xét thời gian transaction, khóa, constraint và lượng transaction log.

### 3.4. CRUD delete và aggregate

Spring Data JDBC quản lý dữ liệu theo aggregate. Repository được định nghĩa cho aggregate root; các thành phần con được lưu trong các bảng liên quan theo mapping như `@MappedCollection`.

Khi xóa aggregate root qua CRUD repository, Spring Data JDBC xử lý các hàng thuộc aggregate theo mapping và thứ tự cần thiết để giữ toàn vẹn quan hệ. Điều này khác với việc chỉ gửi một câu DELETE trực tiếp vào bảng root.

Ví dụ:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;

    // constructors, getters...
}
~~~

Nếu xóa `PurchaseOrder` qua repository, các hàng `OrderLine` thuộc aggregate cần được xử lý theo chiến lược persistence của Spring Data JDBC. Ứng dụng không nên giả định chỉ xóa hàng trong `purchase_orders` là đủ.

Chi tiết SQL được thực thi phụ thuộc phiên bản và mapping, nhưng khi cần semantics aggregate, CRUD repository là abstraction phù hợp hơn một lệnh DELETE bảng đơn.

## 4. SQL DELETE trực tiếp bằng @Modifying và @Query

Khi cần điều khiển chính xác SQL, có thể khai báo modifying query:

~~~java
import java.time.Instant;

import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface AuditEventRepository
        extends CrudRepository<AuditEvent, Long> {

    @Modifying
    @Query("""
        DELETE FROM audit_events
        WHERE created_at < :cutoff
        """)
    int deleteOlderThan(@Param("cutoff") Instant cutoff);
}
~~~

`@Query` cung cấp SQL tường minh; `@Modifying` đánh dấu method thực hiện thay đổi dữ liệu thay vì chỉ đọc. Câu SQL được gửi tới database theo dialect/schema của ứng dụng.

Với cách này, ứng dụng kiểm soát:

- Bảng bị xóa.
- Predicate và điều kiện tenant.
- Có dùng subquery hoặc biểu thức SQL đặc thù hay không.
- Có trả số hàng bị tác động hay không, nếu method contract hỗ trợ.
- Cách xử lý bảng con, foreign key và cascade.

### 4.1. Direct DELETE không tự hiểu aggregate

Ví dụ:

~~~sql
DELETE FROM purchase_orders
WHERE id = :orderId;
~~~

Câu SQL chỉ nhắm tới bảng `purchase_orders`. Nó không tự đọc metadata `@MappedCollection` để xóa `order_lines`.

Nếu bảng con có foreign key:

~~~sql
FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
~~~

database có thể từ chối xóa root vì vẫn còn hàng con. Nếu foreign key được cấu hình `ON DELETE CASCADE`, database có thể tự xóa hàng con. Nếu không có foreign key hoặc cascade, có nguy cơ để lại dữ liệu mồ côi.

Khi viết direct DELETE cho aggregate, cần chủ động chọn một chiến lược:

1. Xóa các bảng con trước rồi xóa root, trong cùng transaction.
2. Dùng foreign key cascade nếu đó là chính sách được thiết kế và kiểm thử rõ.
3. Dùng CRUD repository để framework xử lý aggregate theo mapping.

Không nên dựa vào việc một câu DELETE ở bảng root sẽ tự động xử lý quan hệ object.

### 4.2. Direct DELETE bỏ qua entity mapping

SQL trực tiếp không tạo entity Java rồi gọi thao tác xóa CRUD trên từng aggregate. Vì vậy, không nên kỳ vọng nó tự áp dụng các bước phụ thuộc vào object mapping như:

- Kiểm tra business rule trong service.
- Xác minh trạng thái entity trước khi xóa.
- Xử lý child collection theo metadata aggregate.
- Thực thi lifecycle callback gắn với thao tác xóa entity.
- Tạo audit record ở tầng ứng dụng.

Nếu hệ thống cần audit, có thể ghi audit một cách tường minh trong cùng transaction hoặc dùng cơ chế database phù hợp như trigger, tùy yêu cầu. Trigger cũng có semantics và khả năng quan sát riêng; không thay thế việc thiết kế nghiệp vụ.

## 5. SQL DELETE trực tiếp bằng JdbcTemplate

Với SQL động hoặc thao tác nằm ngoài repository, có thể dùng `JdbcTemplate`:

~~~java
@Repository
public class AuditEventDao {

    private final JdbcTemplate jdbc;

    public AuditEventDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int deleteBefore(Instant cutoff) {
        return jdbc.update(
                "DELETE FROM audit_events WHERE created_at < ?",
                Timestamp.from(cutoff)
        );
    }
}
~~~

`JdbcTemplate.update` trả về số hàng bị tác động trong trường hợp DML thông thường. Tham số được bind qua PreparedStatement, giúp tách giá trị dữ liệu khỏi câu SQL.

Nếu dùng `NamedParameterJdbcTemplate`, có thể dùng named parameter:

~~~java
public int deleteForTenantBefore(UUID tenantId, Instant cutoff) {
    String sql = """
            DELETE FROM audit_events
            WHERE tenant_id = :tenantId
              AND created_at < :cutoff
            """;

    var params = new MapSqlParameterSource()
            .addValue("tenantId", tenantId)
            .addValue("cutoff", cutoff);

    return namedParameterJdbcTemplate.update(sql, params);
}
~~~

Không nối input người dùng vào chuỗi SQL. Bind parameter chỉ dành cho giá trị; tên bảng, tên cột và keyword phải được kiểm soát bằng SQL cố định hoặc allowlist.

## 6. So sánh ba cách xóa

| Tiêu chí | Derived delete | CRUD delete | SQL DELETE trực tiếp |
|---|---|---|---|
| Cách khai báo | Tên method như `deleteByStatus` | Method CRUD như `deleteById` | Viết SQL trong `@Query` hoặc DAO |
| Điều kiện | Suy ra từ property Java | Theo entity hoặc identifier | SQL predicate do ứng dụng định nghĩa |
| Mapping entity | Dùng metadata để suy ra query | Là thao tác repository trên entity/root | Không tự map entity |
| Aggregate child | Không nên giả định semantics giống CRUD; xác nhận SQL và phiên bản | Phù hợp khi cần xóa aggregate qua repository | Ứng dụng/DB phải xử lý rõ |
| Lifecycle entity | Là query delete; không mặc định coi như gọi `delete(entity)` từng object | Theo đường CRUD/entity persistence | Không tự chạy lifecycle của repository |
| SQL control | Giới hạn theo derived predicate | Framework quyết định SQL theo CRUD | Kiểm soát trực tiếp |
| Số hàng bị xóa | Theo return contract được hỗ trợ | API CRUD thường không trả count | Có thể lấy update count |
| Tính portable | Phụ thuộc parser và dialect | Cao hơn ở tầng repository | Phụ thuộc SQL/dialect |
| Dùng khi | Điều kiện đơn giản và semantics đã rõ | Xóa entity/aggregate theo ID hoặc object | Bulk delete, điều kiện SQL phức tạp, bảng kỹ thuật |

Một lưu ý quan trọng: derived delete là query theo điều kiện, còn CRUD delete là thao tác trên entity/identifier. Không nên coi hai cách này có cùng hành vi chỉ vì cùng kết quả cuối là một số hàng bị xóa. Với derived delete trên aggregate có child, hãy xác nhận SQL được tạo và kiểm thử foreign key/cascade của database đang dùng.

## 7. Transaction và xóa nhiều bảng

Xóa root và child thường gồm nhiều câu SQL. Nếu một câu thành công nhưng câu tiếp theo thất bại, dữ liệu có thể ở trạng thái dở dang nếu không có transaction chung.

Ví dụ service xóa bằng SQL tường minh:

~~~java
@Service
public class PurchaseOrderDeletionService {

    private final JdbcTemplate jdbc;

    public PurchaseOrderDeletionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void deleteOrder(Long orderId) {
        jdbc.update(
                "DELETE FROM order_lines WHERE order_id = ?",
                orderId
        );

        jdbc.update(
                "DELETE FROM purchase_orders WHERE id = ?",
                orderId
        );
    }
}
~~~

Hai lệnh tham gia cùng transaction nếu chúng dùng cùng DataSource và transaction manager. Nếu lệnh xóa root thất bại, exception thoát khỏi method thì transaction có thể rollback các thay đổi trước đó theo rollback policy.

Với nghiệp vụ cần xóa toàn aggregate, dùng CRUD repository thường dễ bảo trì hơn vì thể hiện đúng aggregate boundary. Ví dụ:

~~~java
@Transactional
public void deleteOrder(Long orderId) {
    purchaseOrderRepository.deleteById(orderId);
}
~~~

Cần phân biệt **transaction** với **cascade**:

- Transaction bảo đảm các thao tác trong phạm vi được commit/rollback cùng nhau.
- Cascade là quy tắc xử lý hàng liên quan khi xóa hàng được tham chiếu.
- CRUD aggregate deletion là hành vi persistence của Spring Data JDBC dựa trên mapping.
- Direct SQL DELETE chỉ thực hiện những thao tác SQL được viết hoặc những hành vi database đã cấu hình.

Không có transaction không có nghĩa cascade tự biến mất; có transaction cũng không tự tạo cascade.

## 8. Xóa theo điều kiện có an toàn không?

Xóa theo predicate có thể tác động nhiều hàng. Trước khi triển khai, hãy kiểm tra:

- Predicate có giới hạn đúng tenant hoặc chủ sở hữu không?
- Có thể xóa nhầm dữ liệu đang hoạt động không?
- Business key có unique hay không?
- Các bảng con có foreign key hoặc cascade gì?
- Có cần lưu audit/history trước khi xóa không?
- Có cần soft delete thay vì hard delete không?
- Số lượng hàng có thể quá lớn cho một transaction không?

Ví dụ thiếu điều kiện tenant:

~~~sql
DELETE FROM sessions
WHERE expires_at < :cutoff;
~~~

Nếu session thuộc nhiều tenant và chính sách xóa chỉ cho phép trong một tenant, câu SQL cần thêm điều kiện:

~~~sql
DELETE FROM sessions
WHERE tenant_id = :tenantId
  AND expires_at < :cutoff;
~~~

Điều kiện tenant nên được lấy từ context đã xác thực ở server, không tin tenant ID do caller tự ý cung cấp nếu không có kiểm tra quyền.

### 8.1. Preview trước khi xóa

Có thể kiểm tra phạm vi bằng count:

~~~sql
SELECT COUNT(*)
FROM audit_events
WHERE created_at < :cutoff;
~~~

Hoặc lấy một tập ID mẫu để kiểm tra. Tuy nhiên, preview và delete là hai câu truy vấn riêng; dữ liệu có thể thay đổi giữa hai lần chạy. Nếu cần phạm vi chính xác, hãy thiết kế transaction isolation/locking hoặc dùng một chiến lược đánh dấu dữ liệu cần xóa.

### 8.2. Delete hàng loạt và chunking

Xóa hàng triệu hàng trong một transaction có thể tạo transaction log lớn, giữ lock lâu và ảnh hưởng workload khác. Có thể chia nhỏ theo ID hoặc khoảng thời gian:

~~~sql
DELETE FROM audit_events
WHERE created_at < :cutoff
  AND id IN (
      SELECT id
      FROM audit_events
      WHERE created_at < :cutoff
      ORDER BY id
      LIMIT 1000
  );
~~~

Cú pháp subquery/limit phụ thuộc database. Một số hệ quản trị cần CTE hoặc cú pháp khác. Khi chia chunk, cần xác định transaction boundary, checkpoint, retry và cách tránh bỏ sót dữ liệu.

Không nên thêm `LIMIT` vào DELETE mà không kiểm tra dialect. Cũng không nên giả định chia chunk trong một method có `@Transactional` sẽ commit mỗi chunk riêng; toàn method vẫn có thể nằm trong một transaction.

## 9. Hard delete, soft delete và audit

SQL DELETE là **hard delete**: hàng bị xóa khỏi bảng theo semantics database. Nếu nghiệp vụ cần giữ lịch sử, có thể dùng soft delete:

~~~sql
UPDATE customers
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

Entity có property `deletedAt`, repository cung cấp method cập nhật phù hợp hoặc dùng modifying query. Khi soft delete:

- Các truy vấn đọc cần lọc bỏ bản ghi đã xóa.
- Unique constraint có thể cần thiết kế lại nếu business key được phép tái sử dụng.
- Foreign key vẫn trỏ tới hàng còn tồn tại.
- Chính sách khôi phục phải được xác định.
- Audit có thể giữ lịch sử trạng thái thay đổi.

Soft delete không phải thao tác DELETE. Đừng đặt tên method `delete...` nếu nó thực chất chỉ cập nhật cờ trạng thái, trừ khi abstraction của ứng dụng đã định nghĩa rõ semantics đó.

## 10. Khi nào chọn cách nào?

### Chọn CRUD delete khi

- Xóa một aggregate root theo ID hoặc entity.
- Cần Spring Data JDBC xử lý quan hệ aggregate theo mapping.
- Muốn giữ repository abstraction và tránh tự viết SQL nhiều bảng.
- Có business validation trước khi xóa.
- Cần code thể hiện rõ entity nào bị xóa.

Ví dụ:

~~~java
@Transactional
public void removeCustomer(Long id) {
    Customer customer = customers.findById(id)
            .orElseThrow(CustomerNotFoundException::new);

    customerDeletionPolicy.checkCanDelete(customer);
    customers.delete(customer);
}
~~~

### Chọn derived delete khi

- Predicate đơn giản, dựa trên property.
- Không cần SQL tùy biến.
- Đã xác nhận hành vi delete của phiên bản Spring Data JDBC đang dùng.
- Schema và aggregate không yêu cầu xử lý child đặc biệt.
- Xóa theo điều kiện là ý định nghiệp vụ rõ ràng.

Ví dụ:

~~~java
void deleteByExpiresAtBefore(Instant cutoff);
~~~

### Chọn SQL DELETE trực tiếp khi

- Cần xóa theo predicate SQL phức tạp.
- Cần bulk delete với update count rõ ràng.
- Đang thao tác bảng kỹ thuật không phải aggregate.
- Cần CTE/subquery hoặc cú pháp database đặc thù.
- Ứng dụng chủ động quản lý child rows, constraint, audit và transaction.

Ví dụ:

~~~java
@Modifying
@Query("""
    DELETE FROM audit_events
    WHERE tenant_id = :tenantId
      AND created_at < :cutoff
    """)
int purgeTenantEvents(UUID tenantId, Instant cutoff);
~~~

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Derived delete xóa nhiều hàng | Predicate không unique hoặc thiếu điều kiện tenant | Bổ sung predicate và constraint phù hợp |
| Xóa root bị foreign key từ chối | Bảng con vẫn tham chiếu root | Dùng CRUD aggregate delete, xóa child trước hoặc thiết kế cascade |
| Direct DELETE để lại child mồ côi | Không có FK/cascade và SQL chỉ xóa bảng root | Xóa child tường minh hoặc sửa schema |
| Nghĩ `deleteBy...` giống `delete(entity)` | Nhầm query delete với CRUD entity operation | Xác nhận SQL và semantics của phiên bản |
| Không nhận được số hàng đã xóa | Method return type không được query contract hỗ trợ | Dùng return type được hỗ trợ hoặc JDBC update count |
| Xóa xong không có audit event | SQL trực tiếp không chạy logic audit của service/callback | Ghi audit tường minh hoặc dùng cơ chế DB có chủ đích |
| Một phần dữ liệu đã xóa khi bước sau lỗi | Không có transaction chung | Đặt `@Transactional` ở service |
| Xóa nhầm tenant khác | Predicate thiếu tenant/security scope | Lấy tenant từ context xác thực và thêm điều kiện |
| Query DELETE chậm | Predicate không có index phù hợp hoặc xóa quá nhiều hàng | Xem query plan, chunking và index |
| Soft-deleted record vẫn xuất hiện | Truy vấn đọc không lọc trạng thái xóa | Chuẩn hóa repository/query policy |
| Xóa dữ liệu con bị cascade ngoài dự kiến | FK có `ON DELETE CASCADE` | Kiểm tra DDL và chính sách cascade trước khi xóa |

## 12. Bài tập thực hành

### Bài 1 — Derived delete

Tạo `CustomerRepository` với `deleteByStatus` và `removeByCreatedAtBefore`. Chèn dữ liệu có nhiều trạng thái và thời điểm, chạy từng method rồi kiểm tra số hàng còn lại. Bật SQL logging để quan sát câu SQL được tạo.

### Bài 2 — CRUD delete

Tạo aggregate `PurchaseOrder` có `List<OrderLine>`. Xóa root bằng `deleteById` và kiểm tra hàng con. Quan sát thứ tự thao tác SQL và ảnh hưởng của foreign key.

### Bài 3 — Direct DELETE

Viết `@Modifying @Query` xóa event theo tenant và cutoff. So sánh với `JdbcTemplate.update`. Xác nhận update count và transaction behavior.

### Bài 4 — Child rows và cascade

Tạo schema có foreign key không cascade, sau đó thử direct DELETE root. Tiếp tục thử xóa child trước rồi root trong cùng transaction. Tạo thêm biến thể `ON DELETE CASCADE` và so sánh.

### Bài 5 — Race condition và dữ liệu thay đổi

Chạy xóa theo predicate trong lúc request khác cập nhật trạng thái hàng. Quan sát kết quả theo isolation level và xác định quy tắc nghiệp vụ mong muốn.

### Bài 6 — Bulk delete

Tạo lượng lớn audit event cũ. So sánh một lệnh DELETE lớn với xóa theo chunk. Đo thời gian, transaction log, lock và ảnh hưởng đến truy vấn đồng thời.

### Bài 7 — Soft delete

Thay hard delete bằng cập nhật `deleted_at`. Bảo đảm các truy vấn đọc loại bỏ hàng đã xóa mềm và kiểm tra quy tắc unique key khi khôi phục.

## 13. Ghi nhớ

- **Derived delete** dùng tên method như `deleteBy...` hoặc `removeBy...` để suy ra predicate theo property Java.
- **CRUD delete** dùng entity hoặc identifier để xóa qua repository; phù hợp khi cần thao tác trên aggregate root theo mapping Spring Data JDBC.
- **SQL DELETE trực tiếp** bằng `@Modifying @Query` hoặc `JdbcTemplate` cho phép kiểm soát câu SQL và update count, nhưng ứng dụng phải chủ động xử lý các bảng liên quan và quy tắc nghiệp vụ.
- Không mặc định derived delete có cùng semantics với CRUD delete trên aggregate có child; xác nhận SQL, version và foreign key thực tế.
- `@MappedCollection` mô tả dữ liệu con của aggregate; một câu DELETE chỉ nhắm bảng root không tự hiểu mapping này.
- Transaction gom nhiều thao tác commit/rollback cùng nhau; cascade là quy tắc xóa hàng liên quan ở database. Hai khái niệm này khác nhau.
- Trước khi xóa theo điều kiện, kiểm tra tenant scope, predicate, unique constraint, child rows, audit và số lượng dữ liệu.
- Với thao tác bulk lớn, đánh giá chunking, checkpoint, index và transaction log; đừng giả định một lệnh xóa khổng lồ luôn phù hợp.
