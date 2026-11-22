# Kết hợp `@Modifying` với `@Query` cho `UPDATE` và `DELETE`

Trong **Spring Data Relational JDBC**, `@Query` cho phép khai báo SQL trực tiếp trên repository method. Khi câu SQL thay đổi dữ liệu bằng `INSERT`, `UPDATE`, `DELETE` hoặc một lệnh DDL không trả về bảng kết quả, cần đánh dấu method bằng **`@Modifying`** để Spring Data biết đây là truy vấn ghi.

Ví dụ:

```java
@Modifying
@Query("UPDATE person SET lastname = :lastname WHERE id = :id")
int updateLastname(@Param("id") Long id, @Param("lastname") String lastname);
```

`@Modifying` khiến Spring Data JDBC thực thi câu SQL trực tiếp và trả về số hàng bị ảnh hưởng (`int`), kết quả có/không có hàng thay đổi (`boolean`) hoặc bỏ qua kết quả (`void`). Đây là con đường ghi dữ liệu cấp SQL: nó **không gọi entity callbacks hoặc lifecycle events**, vì vậy các trường auditing không tự cập nhật nếu câu SQL không ghi chúng.

Bài này trình bày cách khai báo `UPDATE`/`DELETE`, bind named parameters, chọn kiểu trả về, quản lý transaction, và những tác động đến aggregate, auditing, optimistic locking cùng khóa ngoại.

## 1. Phân biệt `@Query` và `@Modifying`

Hai annotation có nhiệm vụ khác nhau:

| Annotation | Vai trò |
|---|---|
| `@Query` | Cung cấp câu SQL được dùng khi gọi repository method |
| `@Modifying` | Báo cho Spring Data rằng câu query là lệnh thay đổi dữ liệu, không phải query đọc result set |
| `@Param` | Gắn tên tham số method với named parameter trong SQL |
| `@Transactional` | Xác định ranh giới transaction cho thao tác ghi |

Các import dành cho Spring Data JDBC:

```java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;
```

Không nhầm `org.springframework.data.jdbc.repository.query.Modifying` với annotation `@Modifying` của Spring Data JPA (`org.springframework.data.jpa.repository.Modifying`). Spring Data JDBC có annotation riêng trong package `org.springframework.data.jdbc.repository.query`.

### Khi nào cần `@Modifying`?

- `@Query("SELECT ...")`: query đọc, không đánh dấu `@Modifying`.
- `@Modifying` + `@Query("UPDATE ...")`: cập nhật hàng.
- `@Modifying` + `@Query("DELETE ...")`: xóa hàng.
- `@Modifying` + `@Query("INSERT ...")`: chèn dữ liệu bằng SQL tường minh nếu không cần nhận generated key/result row.
- `@Modifying` + lệnh DDL: chỉ dùng khi có lý do quản trị schema đặc biệt; thông thường schema được quản lý bằng migration.

`@Modifying` chỉ có ý nghĩa khi đi cùng `@Query`. Các derived delete methods như `deleteByStatus(...)` được Spring Data phân tích theo tên method và không cần `@Modifying`.

## 2. Ví dụ `UPDATE` bằng `@Modifying` và `@Query`

Giả sử bảng `person` có các cột `id`, `firstname`, `lastname`, `status` và `updated_at`. Repository có thể khai báo:

```java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Query("UPDATE person SET lastname = :lastname WHERE id = :id")
    int updateLastname(
            @Param("id") Long id,
            @Param("lastname") String lastname
    );
}
```

Gọi method:

```java
int updated = personRepository.updateLastname(42L, "Nguyen");

if (updated == 1) {
    System.out.println("Person was updated");
} else {
    System.out.println("No matching row was updated");
}
```

`int` là số hàng database báo đã bị ảnh hưởng. Giá trị `0` thường có nghĩa không có hàng khớp điều kiện `WHERE`, hoặc không có thay đổi được ghi nhận theo semantics của database/driver. Không nên luôn diễn giải `0` là lỗi; đó có thể là kết quả nghiệp vụ hợp lệ.

### Cập nhật nhiều cột

```java
@Modifying
@Query("""
    UPDATE person
    SET firstname = :firstname,
        lastname = :lastname,
        status = :status,
        updated_at = :updatedAt
    WHERE id = :id
    """)
int updateProfile(
        @Param("id") Long id,
        @Param("firstname") String firstname,
        @Param("lastname") String lastname,
        @Param("status") String status,
        @Param("updatedAt") Instant updatedAt
);
```

SQL trong `@Query` là SQL của database, vì vậy phải dùng **tên bảng và tên cột** (`updated_at`), không dùng tên property Java (`updatedAt`) trừ khi chúng trùng nhau. Named parameters (`:id`, `:status`) được bind từ method arguments.

## 3. Ví dụ `DELETE` bằng `@Modifying` và `@Query`

Xóa một hàng theo ID:

```java
@Modifying
@Query("DELETE FROM person WHERE id = :id")
int deletePerson(@Param("id") Long id);
```

Xóa theo điều kiện:

```java
@Modifying
@Query("DELETE FROM person WHERE status = :status")
int deletePeopleWithStatus(@Param("status") String status);
```

Gọi method:

```java
int deleted = personRepository.deletePeopleWithStatus("INACTIVE");
System.out.println("Deleted rows: " + deleted);
```

Một lệnh `DELETE` trực tiếp xóa những hàng khớp với `WHERE`. Hãy đặc biệt cẩn thận với câu SQL không có `WHERE`: nó có thể xóa toàn bộ dữ liệu trong bảng.

Nếu query xóa nhiều hàng, return type `int` giúp ghi nhận số hàng bị ảnh hưởng. Nếu chỉ cần biết thao tác hoàn tất, dùng `void`. Nếu chỉ cần biết có ít nhất một hàng bị tác động, dùng `boolean`.

## 4. Chọn kiểu trả về: `int`, `boolean` hay `void`

Spring Data JDBC hỗ trợ ba kiểu trả về cho modifying query:

| Kiểu trả về | Ý nghĩa | Khi phù hợp |
|---|---|---|
| `int` | Số hàng được cập nhật/xóa | Cần kiểm tra có đúng một hàng hay bao nhiêu hàng bị ảnh hưởng |
| `boolean` | Có ít nhất một hàng được thay đổi hay không | Chỉ cần kết quả thành công/có tác động |
| `void` | Bỏ qua update count | Không cần biết số hàng bị ảnh hưởng |

Ví dụ:

```java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
boolean changeStatus(@Param("id") Long id, @Param("status") String status);

@Modifying
@Query("DELETE FROM person WHERE status = :status")
void deleteAllWithStatus(@Param("status") String status);
```

Với nghiệp vụ cần phân biệt “không tìm thấy hàng” và “cập nhật đúng một hàng”, `int` thường hữu ích nhất:

```java
int affected = repository.changeStatus(id, "ACTIVE");

if (affected == 0) {
    // Không có hàng phù hợp hoặc không có thay đổi được ghi nhận.
} else if (affected == 1) {
    // Một hàng đã được cập nhật.
} else {
    // Điều kiện WHERE không duy nhất hoặc dữ liệu có vấn đề.
}
```

Không khai báo `Person` hoặc `Optional<Person>` làm return type của modifying query thông thường. `@Modifying` được thiết kế cho lệnh không trả về result table. Nếu cần lấy hàng đã cập nhật, generated key hoặc kết quả từ `RETURNING`, dùng custom repository với JDBC operations và `ResultSet`/`RowMapper` phù hợp với database, thay vì mong `@Modifying` tự map result set.

## 5. Named parameters và binding an toàn

Spring Data JDBC hỗ trợ **named parameters** trong string-based `@Query`. Tên trong SQL phải khớp tên khai báo bởi `@Param`:

```java
@Modifying
@Query("UPDATE person SET status = :newStatus WHERE id = :personId")
int updateStatus(
        @Param("personId") Long id,
        @Param("newStatus") String status
);
```

Ở đây:

- `:personId` được bind từ argument có `@Param("personId")`.
- `:newStatus` được bind từ argument có `@Param("newStatus")`.
- Tên biến Java (`id`, `status`) không bắt buộc giống tên parameter SQL nếu `@Param` đã chỉ rõ.

Nếu dự án bật compiler option `-parameters`, Spring có thể khám phá tên parameter Java và cho phép bỏ `@Param` trong một số cấu hình. Với tài liệu học tập và code cần rõ ràng giữa nhiều build environment, dùng `@Param` tường minh thường dễ đọc hơn.

### Bind giá trị, không nối chuỗi SQL

Đúng:

```java
@Modifying
@Query("DELETE FROM person WHERE email = :email")
int deleteByEmail(@Param("email") String email);
```

Không nên tạo SQL bằng cách nối input:

```java
// Không làm như vậy: dữ liệu đầu vào bị biến thành một phần SQL.
String sql = "DELETE FROM person WHERE email = '" + email + "'";
```

Named parameters được bind như giá trị, giúp tránh việc dữ liệu người dùng trở thành cú pháp SQL. Tuy nhiên, parameter không thể đại diện cho tên bảng, tên cột hoặc từ khóa SQL. Nếu cần chọn cột sort hay bảng động, ánh xạ input qua danh sách identifier được phép (whitelist) hoặc viết các method/query cố định.

## 6. Quản lý transaction cho modifying query

`@Modifying` **không tự mở transaction** chỉ vì câu SQL là lệnh ghi. Query method cần được chạy trong một transaction phù hợp: có thể đặt `@Transactional` trực tiếp trên repository method, hoặc gọi nó từ application service đã mở transaction.

Ví dụ khai báo tại repository:

```java
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Transactional
    @Query("UPDATE person SET status = :status WHERE id = :id")
    int updateStatus(
            @Param("id") Long id,
            @Param("status") String status
    );
}
```

Hoặc đặt transaction ở application service khi use case có nhiều thao tác:

```java
@Service
public class PersonMaintenanceService {

    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonMaintenanceService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void deactivatePerson(Long id) {
        int updated = personRepository.updateStatus(id, "INACTIVE");

        if (updated != 1) {
            throw new IllegalStateException("Person was not updated");
        }

        auditRepository.save(new AuditEntry(id, "PERSON_DEACTIVATED"));
    }
}
```

Trong ví dụ, update và ghi audit cùng tham gia transaction JDBC nếu repository dùng chung DataSource/transaction manager. Nếu bước ghi audit lỗi và exception gây rollback, update trạng thái person cũng được rollback.

### Khi repository mặc định `readOnly = true`

Một repository interface có thể được đặt `@Transactional(readOnly = true)` ở cấp interface cho các query đọc. Method modifying cần override bằng `@Transactional` ghi:

```java
@Transactional(readOnly = true)
public interface PersonRepository extends CrudRepository<Person, Long> {

    @Modifying
    @Transactional
    @Query("DELETE FROM person WHERE active = false")
    int deleteInactivePeople();
}
```

`@Transactional` ở method ghi ghi đè thiết lập read-only của interface. Nếu method được gọi trong một transaction ngoài đang hoạt động, propagation mặc định `REQUIRED` khiến nó tham gia transaction đó; thuộc tính transaction thực tế chịu ảnh hưởng của transaction ngoài.

Spring mặc định rollback với `RuntimeException` và `Error`. Checked exception không tự động rollback trừ khi cấu hình `rollbackFor` phù hợp. Không bắt exception rồi nuốt lỗi bên trong transaction nếu nghiệp vụ yêu cầu rollback.

## 7. Modifying query bỏ qua aggregate lifecycle

Đây là khác biệt quan trọng nhất giữa `repository.save(entity)` và `@Modifying @Query`.

| Đặc điểm | `repository.save(root)` | `@Modifying @Query` |
|---|---|---|
| Đường ghi | Spring Data JDBC lập kế hoạch ghi aggregate | SQL chạy trực tiếp trên database |
| Aggregate children | Framework xử lý các entity được sở hữu theo mapping | Không tự đồng bộ collection/child |
| Entity callbacks | Có thể được gọi theo lifecycle | Không được gọi |
| Lifecycle events | Có thể được phát theo lifecycle | Không được phát |
| Auditing annotations | Có thể được xử lý qua auditing callbacks | Không tự cập nhật nếu SQL không ghi các cột audit |
| Optimistic locking | Hỗ trợ theo `@Version` khi lưu aggregate | Không tự thêm điều kiện version hay tăng version |
| Object trong bộ nhớ | Trả về aggregate đã lưu theo cơ chế repository | Object đã tải trước đó không tự đổi theo SQL |

Ví dụ một entity có:

```java
@LastModifiedDate
private Instant lastModifiedAt;

@LastModifiedBy
private String lastModifiedBy;
```

Nếu dùng `@Modifying`:

```java
@Modifying
@Query("UPDATE person SET status = :status WHERE id = :id")
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

`last_modified_at` và `last_modified_by` không tự được cập nhật bởi auditing callback. Nếu cần, thêm chúng trực tiếp vào SQL và truyền giá trị tương ứng:

```java
@Modifying
@Query("""
    UPDATE person
    SET status = :status,
        last_modified_at = :modifiedAt,
        last_modified_by = :modifiedBy
    WHERE id = :id
    """)
int updateStatusAndAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("modifiedBy") String modifiedBy
);
```

Nếu cần lấy người dùng hiện tại, có thể lấy ở application service/security context rồi truyền thành parameter. Không dựa vào `@LastModifiedBy` để tự điền trong direct DML.

## 8. Tác động đến `@Version` và optimistic locking

Spring Data JDBC dùng `@Version` trong quy trình lưu aggregate để phát hiện cập nhật đồng thời. Nhưng `@Modifying @Query` chạy SQL trực tiếp, nên framework không tự:

- Thêm `AND version = :oldVersion` vào `WHERE`.
- Tăng cột version.
- Ném `OptimisticLockingFailureException` chỉ vì câu UPDATE ảnh hưởng zero row.

Nếu direct update phải giữ optimistic locking, hãy viết điều kiện và tăng version tường minh:

```java
@Modifying
@Query("""
    UPDATE inventory
    SET available = available - :quantity,
        version = version + 1
    WHERE product_id = :productId
      AND version = :expectedVersion
      AND available >= :quantity
    """)
int reserveStock(
        @Param("productId") Long productId,
        @Param("quantity") int quantity,
        @Param("expectedVersion") Long expectedVersion
);
```

Diễn giải kết quả:

- `1`: cập nhật thành công; quantity hợp lệ, version còn khớp và đủ tồn kho.
- `0`: không có hàng phù hợp; có thể do ID không tồn tại, version đã thay đổi hoặc tồn kho không đủ.

Nếu cần phân biệt ba nguyên nhân, thực hiện truy vấn đọc phù hợp sau khi update không thành công hoặc thiết kế kết quả nghiệp vụ riêng. Không tự tăng version trong Java rồi gọi `save()` với một object stale để bỏ qua optimistic lock.

Direct DML cũng có thể làm object đã tải trước đó trở nên stale:

```java
Person person = personRepository.findById(id).orElseThrow();
personRepository.updateStatus(id, "INACTIVE");

// Object person trong bộ nhớ vẫn có status cũ.
```

Sau direct update, hãy đọc lại entity nếu cần trạng thái mới. Spring Data JDBC không có persistence context kiểu JPA để tự đồng bộ mọi object đang được giữ trong memory.

## 9. Tác động đến aggregate và collection con

Giả sử `PurchaseOrder` sở hữu `List<OrderLine>`. Nếu trực tiếp chạy:

```java
@Modifying
@Query("UPDATE purchase_order SET status = :status WHERE id = :id")
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

SQL chỉ cập nhật hàng trong `purchase_order`. Nó không gọi quy trình save aggregate và không đồng bộ `order_line`.

Nếu direct DML sửa bảng child:

```java
@Modifying
@Query("DELETE FROM order_line WHERE order_id = :orderId AND line_no = :lineNo")
int deleteLine(
        @Param("orderId") Long orderId,
        @Param("lineNo") Integer lineNo
);
```

thao tác này có thể làm thay đổi cấu trúc collection mà aggregate root quản lý. Nếu sau đó ứng dụng tải root và gọi `save()`, Spring Data JDBC sẽ làm việc theo trạng thái aggregate hiện tại; cần đảm bảo invariant của root vẫn đúng.

**Khi nào direct DML phù hợp?**

- Một bulk update đơn giản, không cần chạy domain behavior trên từng aggregate.
- Một thao tác bảo trì có điều kiện rõ ràng và được bao trong transaction.
- Một cập nhật nguyên tử dựa trên biểu thức SQL, ví dụ giảm tồn kho nếu còn đủ.
- Một lệnh xóa dữ liệu cũ theo retention policy, sau khi đã xác định quan hệ FK và cascade.

**Khi nào nên dùng `save()`?**

- Thay đổi phải đi qua domain method để bảo vệ invariant.
- Cần đồng bộ owned entities/collections của aggregate.
- Cần lifecycle callbacks, auditing hoặc optimistic locking tự động.
- Cần entity state và kết quả lưu được phản ánh trong object trả về.

## 10. Khóa ngoại và thứ tự xóa khi dùng `DELETE`

Một câu `DELETE` trực tiếp không tự áp dụng quy tắc aggregate ownership. Database vẫn kiểm tra foreign key theo schema.

Giả sử:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id)
);
```

Nếu còn `order_line` tham chiếu đến đơn hàng, lệnh sau có thể thất bại:

```sql
DELETE FROM purchase_order WHERE id = :id;
```

Có thể xử lý theo một trong các cách sau, tùy ownership và schema:

1. Xóa child trước rồi xóa root, trong cùng transaction.
2. Dùng `ON DELETE CASCADE` nếu child thực sự có vòng đời phụ thuộc hoàn toàn vào root và schema đã quy định rõ.
3. Không xóa root độc lập nếu còn dữ liệu lịch sử cần giữ; dùng soft delete hoặc trạng thái archive.

Ví dụ hai modifying query:

```java
@Modifying
@Query("DELETE FROM order_line WHERE order_id = :orderId")
int deleteLines(@Param("orderId") Long orderId);

@Modifying
@Query("DELETE FROM purchase_order WHERE id = :orderId")
int deleteOrder(@Param("orderId") Long orderId);
```

Application service điều phối trong một transaction:

```java
@Transactional
public void permanentlyDeleteOrder(Long orderId) {
    orderRepository.deleteLines(orderId);
    int deleted = orderRepository.deleteOrder(orderId);

    if (deleted != 1) {
        throw new IllegalStateException("Order not found");
    }
}
```

Nếu một FK từ aggregate độc lập khác vẫn tham chiếu `purchase_order`, database có thể tiếp tục từ chối xóa root. Không dùng cascade một cách tùy tiện để xóa dữ liệu của aggregate khác.

## 11. SQL constraint và kết quả update/delete

Direct DML vẫn chịu các ràng buộc database:

- **Primary key/unique:** cập nhật một cột thành giá trị đã được dùng có thể gây duplicate key.
- **Foreign key:** đổi FK sang ID không tồn tại hoặc xóa parent đang được tham chiếu có thể thất bại.
- **Check constraint:** đặt quantity/available thành giá trị không hợp lệ có thể bị từ chối.
- **NOT NULL:** gán `NULL` vào cột bắt buộc sẽ gây lỗi.
- **Trigger:** database trigger vẫn có thể chạy theo DML; đây là cơ chế của database, không phải Spring Data callback.

Ví dụ cập nhật trạng thái có điều kiện:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = :newStatus
    WHERE id = :id
      AND status = :expectedStatus
    """)
int transitionStatus(
        @Param("id") Long id,
        @Param("expectedStatus") String expectedStatus,
        @Param("newStatus") String newStatus
);
```

Điều kiện `expectedStatus` giúp thực hiện chuyển trạng thái có kiểm tra trạng thái hiện tại. Nếu số hàng cập nhật là 0, trạng thái có thể đã thay đổi hoặc ID không tồn tại. Đây là một dạng compare-and-set ở database; nếu cần kiểm soát concurrency mạnh hơn, có thể bổ sung cột version vào điều kiện.

## 12. Kiểm thử modifying query

Một integration test nên kiểm tra cả số hàng bị tác động và dữ liệu sau thao tác.

```java
@DataJdbcTest
class PersonRepositoryTest {

    @Autowired PersonRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void updatesAndDeletesRows() {
        jdbcTemplate.update(
                "INSERT INTO person(id, firstname, lastname, status) VALUES (?, ?, ?, ?)",
                1L, "An", "Tran", "ACTIVE"
        );

        int updated = repository.updateLastname(1L, "Nguyen");
        assertThat(updated).isEqualTo(1);

        String lastname = jdbcTemplate.queryForObject(
                "SELECT lastname FROM person WHERE id = ?",
                String.class,
                1L
        );
        assertThat(lastname).isEqualTo("Nguyen");

        int deleted = repository.deletePerson(1L);
        assertThat(deleted).isEqualTo(1);
        assertThat(repository.findById(1L)).isEmpty();
    }
}
```

Test cần schema `person` phù hợp với DDL. `@DataJdbcTest` thường chạy trong transaction test và rollback khi kết thúc; nếu cần xác minh transaction boundary của application service qua nhiều transaction, thiết kế test riêng với commit/rollback rõ ràng.

### Những trường hợp nên bổ sung

- ID không tồn tại: `UPDATE`/`DELETE` trả 0.
- Nhiều hàng khớp điều kiện: update count đúng số hàng.
- `WHERE` không đủ chặt: xác nhận không cập nhật nhầm hàng.
- Unique/FK/check constraint vi phạm: exception được ném và transaction rollback.
- `@Version`: query direct DML tự kiểm tra version và tăng version nếu nghiệp vụ yêu cầu.
- Auditing: cột audit được cập nhật trong SQL nếu cần, vì callback không chạy.
- FK child: delete root khi còn child bị từ chối hoặc cascade theo đúng schema.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Method `@Query("UPDATE ...")` bị xử lý như query đọc | Thiếu `@Modifying` | Thêm `org.springframework.data.jdbc.repository.query.Modifying` |
| Không bind được parameter | Tên `:name` không khớp `@Param("name")` | Đồng bộ tên named parameter |
| SQL báo không tìm thấy cột | Dùng property Java thay tên cột SQL hoặc sai schema | Kiểm tra DDL và tên identifier trong câu SQL |
| `int` trả 0 | Không có row khớp `WHERE`, version/status không khớp hoặc driver/database báo không có row thay đổi | Kiểm tra predicate và dữ liệu; phân biệt 0 với exception |
| `@LastModifiedDate` không đổi | Direct DML không gọi entity callbacks/auditing | Cập nhật cột audit ngay trong SQL |
| `@Version` không phát hiện xung đột | Direct DML không tự kiểm tra/tăng version | Thêm điều kiện version và tăng version tường minh |
| Delete parent bị FK violation | Còn child hoặc root khác tham chiếu | Xóa child trước, xử lý FK/cascade theo ownership |
| Object trong memory vẫn có dữ liệu cũ | SQL trực tiếp không cập nhật object đã tải | Reload entity sau DML |
| Bulk update phá invariant | Bỏ qua domain methods và aggregate lifecycle | Dùng `save()`/domain behavior hoặc thiết kế SQL bảo vệ invariant |
| DML nhiều bước chỉ ghi một phần | Không có transaction chung hoặc exception bị nuốt | Đặt `@Transactional` ở service và xác nhận rollback |

## 14. Quy trình chọn `@Modifying @Query` hay `save()`

1. **Xác định mục tiêu:** thay đổi một aggregate theo nghiệp vụ hay chạy một lệnh SQL trực tiếp?
2. **Nếu cần aggregate lifecycle:** tải root, gọi domain method và `save(root)`.
3. **Nếu DML trực tiếp phù hợp:** khai báo `@Modifying` cùng `@Query` và dùng named parameters.
4. **Chọn return type:** `int` để biết số hàng, `boolean` để biết có tác động, `void` nếu bỏ qua kết quả.
5. **Đặt transaction:** dùng `@Transactional` trên repository method hoặc application service; bảo đảm cùng DataSource/transaction manager.
6. **Kiểm tra concurrency:** nếu dùng `@Version`, tự đưa version vào điều kiện và cập nhật nó trong SQL.
7. **Kiểm tra lifecycle side effects:** audit fields, events, callbacks và child collections cần được xử lý rõ ràng.
8. **Kiểm tra constraints:** FK, unique, check, nullability và hành động cascade.
9. **Kiểm thử:** xác nhận update count, dữ liệu sau thao tác, rollback và trường hợp không có row phù hợp.

### Bảng quyết định nhanh

| Nhu cầu | Cách phù hợp |
|---|---|
| Sửa entity theo domain rule và đồng bộ child | `repository.save(root)` |
| Cập nhật trực tiếp một vài cột bằng SQL | `@Modifying` + `@Query` |
| Xóa nhiều hàng theo điều kiện đơn giản | `@Modifying` + `@Query` hoặc derived `deleteBy...` |
| Cần số hàng bị ảnh hưởng | Return `int` |
| Chỉ cần biết có hàng bị thay đổi | Return `boolean` |
| Cần lifecycle callbacks/auditing tự động | Dùng aggregate persistence; direct DML phải tự ghi cột audit |
| Cần optimistic locking tự động | Dùng `save()` với `@Version`; nếu direct DML thì tự kiểm tra/tăng version |
| Cần trả về generated key hoặc row từ `RETURNING` | Custom JDBC repository/operations, không dùng modifying return type thông thường |

**Điểm cốt lõi:** `@Modifying` đánh dấu câu `@Query` là DML để Spring Data JDBC thực thi trực tiếp. Dùng named parameters để bind giá trị và chọn `int`, `boolean` hoặc `void` theo nhu cầu. Đặt transaction ở ranh giới use case khi có nhiều bước. Vì direct DML bỏ qua aggregate callbacks, lifecycle events, auditing và optimistic locking tự động, ứng dụng phải chủ động xử lý các side effects, version, FK và invariant liên quan.

## Tài liệu tham khảo chính thức

- [Spring Data JDBC — Query Methods: Modifying Queries](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): cú pháp `@Modifying` kết hợp `@Query`, return types và việc không gọi callbacks/events.
- [Spring Data JDBC — `@Modifying` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Modifying.html): annotation đánh dấu method là modifying query.
- [Spring Data JDBC — `@Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): SQL string và named parameters.
- [Spring Data JDBC — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction cho repository query methods và ví dụ modifying query.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, propagation và rollback rules.
