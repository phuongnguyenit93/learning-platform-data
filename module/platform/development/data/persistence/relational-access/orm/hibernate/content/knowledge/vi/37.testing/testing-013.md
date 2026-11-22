# Đối soát kết quả qua SQL độc lập khi cần kiểm chứng ràng buộc thực tế trong Hibernate ORM

## 1. Vì sao cần kiểm tra database bằng một câu SQL độc lập?

Một service tạo đơn hàng:

~~~java
PurchaseOrder order = orderService.create(command);
assertNotNull(order.getId());
assertEquals("DRAFT", order.getStatus());
~~~

Test pass. Nhưng điều đó mới cho biết object Java có ID và trạng thái như kỳ vọng. Nó chưa chứng minh:

- Row đã thực sự được ghi xuống database.
- Foreign key đang trỏ đúng Customer.
- Order và Customer thuộc cùng organization.
- UNIQUE constraint ngăn mã đơn bị trùng.
- Trigger hoặc default value của database đã chạy.
- Một native SQL writer khác có thể tạo dữ liệu sai hay không.
- Query do Hibernate sinh ra và query độc lập trên database trả cùng kết quả.

Trong một số tình huống, kiểm tra kết quả bằng chính repository/mapping đang được test có thể tạo ra một **vòng kiểm chứng khép kín**. Nếu mapping sai theo cùng một cách ở cả write và read, test vẫn có thể pass.

Ví dụ code ghi `organization_id = 7` nhưng association mapping lại đọc nhầm cột hoặc query repository vô tình bỏ điều kiện tenant. Nếu chỉ gọi lại cùng entity/repository trong persistence context, first-level cache có thể trả object cũ mà không phát SQL. Test tưởng rằng database đã lưu đúng, trong khi chưa kiểm tra trạng thái thực tế.

Một câu SQL độc lập qua JDBC/JdbcTemplate có thể kiểm tra trực tiếp rows và constraints ở database:

~~~sql
SELECT
    o.id,
    o.organization_id,
    o.customer_id,
    c.organization_id AS customer_organization_id,
    o.order_number,
    o.status
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = :orderId;
~~~

Kết quả có thể được đối chiếu với business invariant:

~~~text
order.organization_id = customer.organization_id
~~~

Đây là mục tiêu của **đối soát bằng SQL độc lập**: xác nhận dữ liệu đã được database lưu và thực thi các ràng buộc như hợp đồng yêu cầu, bằng một đường đọc không phụ thuộc vào chính mapping/query đang được kiểm chứng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt assertion trên entity trong persistence context với assertion trên row thực tế.
2. Giải thích vì sao `flush()`, `clear()`, `refresh()` và commit có ý nghĩa khác nhau.
3. Dùng JDBC/JdbcTemplate để kiểm tra dữ liệu trực tiếp.
4. Viết SQL độc lập nhằm đối chiếu khóa ngoại, khóa nghiệp vụ, tenant và soft delete.
5. Kiểm chứng UNIQUE, CHECK, FK, trigger, default, generated column và precision.
6. Xác nhận native SQL/bulk DML thực sự cập nhật đúng rows.
7. Phát hiện lỗi mapping, association và query bị che bởi first-level cache.
8. Phân biệt lỗi dữ liệu với lỗi do transaction visibility hoặc isolation.
9. Kiểm tra SQLSTATE/constraint metadata mà không phụ thuộc message không ổn định.
10. Thiết kế fixtures và integration tests trên đúng database production.
11. Tránh việc SQL kiểm chứng lặp lại nguyên giả định sai của ORM.
12. Chọn mức đối soát phù hợp với rủi ro và chi phí test.

Ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA, Spring JDBC, PostgreSQL và Testcontainers. SQL cụ thể cần điều chỉnh theo database production của dự án.

## 2. ORM assertion và database assertion chứng minh hai điều khác nhau

| Cách kiểm tra | Điều được xác nhận | Giới hạn |
|---|---|---|
| Assert trên object vừa tạo | Domain method/state trong memory | Có thể chưa flush; chưa chứng minh DB |
| Gọi lại getter trên entity managed | State hiện tại trong persistence context | Có thể không phát SQL |
| Gọi repository query | Hành vi ORM/repository | Có thể dùng cache hoặc cùng mapping sai |
| Flush rồi đọc qua entity mới | ORM ghi và đọc qua context khác | Vẫn dùng Hibernate mapping ở đường đọc |
| JDBC query độc lập | Giá trị row/SQL join trực tiếp trong DB | Cần tự kiểm soát SQL và transaction visibility |
| Đọc database catalogs | Constraint/index/trigger/policy được khai báo | Cần kiểm tra runtime behavior riêng |
| Thử ghi dữ liệu vi phạm | Database thực thi constraint | Phải dùng đúng engine và transaction độc lập |

### 2.1. Không phải mọi test đều cần SQL độc lập

Unit test cho domain method:

~~~java
order.cancel();
assertEquals(OrderStatus.CANCELLED, order.getStatus());
~~~

có thể chỉ cần kiểm tra object state. Không cần JDBC nếu câu hỏi chỉ là domain transition.

SQL độc lập hữu ích khi câu hỏi là:

- Hibernate đã ghi đúng các cột chưa?
- Database có thực sự chặn quan hệ cross-tenant không?
- Trigger đã cập nhật audit row chưa?
- Native SQL có ảnh hưởng đúng tập rows không?
- Dữ liệu sau commit có khớp invariant không?

### 2.2. SQL độc lập không thay thế assertion nghiệp vụ

Một câu SQL có thể xác nhận `status = 'DRAFT'`, nhưng không tự chứng minh user có quyền tạo đơn. Application authorization vẫn cần test ở service/API boundary.

### 2.3. Hai đường kiểm chứng bổ sung cho nhau

~~~text
Application command
      |
      v
Domain + Hibernate write
      |
      v
Database constraints / triggers
      |
      +----------------------+
      |                      |
      v                      v
ORM read assertion     Independent SQL assertion
      |                      |
      +----------+-----------+
                 |
                 v
         Business invariant
~~~

ORM assertion xác nhận contract của application. SQL assertion xác nhận trạng thái database bằng một đường đọc độc lập.

## 3. First-level cache có thể làm test “đọc lại” mà không đọc database

Hibernate Session/EntityManager có persistence context (first-level cache). Một entity đã managed được lưu theo entity type và identifier.

Ví dụ:

~~~java
PurchaseOrder order = entityManager.find(
    PurchaseOrder.class, orderId);

order.setStatus("CONFIRMED");

PurchaseOrder again = entityManager.find(
    PurchaseOrder.class, orderId);

assertSame(order, again);
assertEquals("CONFIRMED", again.getStatus());
~~~

Lệnh `find()` thứ hai có thể chỉ trả cùng Java object, không phát SELECT. Assertion không kiểm tra database.

### 3.1. Thay đổi object chưa chắc đã được ghi

~~~java
order.setStatus("CONFIRMED");
assertEquals("CONFIRMED", order.getStatus());
~~~

Dirty checking chỉ phát SQL khi flush. Nếu transaction rollback, database không giữ thay đổi.

### 3.2. Query repository cũng có thể không chứng minh toàn bộ object state

Một JPQL query có thể chạy SQL để lấy IDs, nhưng Hibernate tái sử dụng entity instance đã managed. Những thuộc tính của instance có thể vẫn là state hiện có trong context. Vì vậy query list trả đúng ID chưa chứng minh mọi scalar field đang khớp row hiện tại.

### 3.3. Đọc qua JDBC bỏ qua identity map

~~~java
String status = jdbcTemplate.queryForObject(
    "select status from purchase_orders where id = ?",
    String.class,
    orderId
);
~~~

JDBC query thực thi SQL trực tiếp qua DataSource, không yêu cầu Hibernate lấy entity từ L1. Nó là một cách đơn giản để xác minh giá trị row.

## 4. Phân biệt flush, clear, refresh và commit

Các API này thường bị dùng lẫn nhau khi viết test.

| Thao tác | Tác dụng | Có commit transaction? |
|---|---|---|
| `entityManager.flush()` | Đồng bộ pending changes của persistence context xuống DB trong transaction | Không |
| `entityManager.clear()` | Detach toàn bộ managed entities | Không |
| `entityManager.detach(entity)` | Detach một entity | Không |
| `entityManager.refresh(entity)` | Reload state entity từ database | Không |
| `transaction.commit()` | Hoàn tất transaction và làm changes bền vững theo DB semantics | Có |
| Mở transaction/context mới | Đọc theo transaction/persistence context khác | Tùy transaction mới |

### 4.1. flush() buộc SQL được gửi, nhưng chưa bền vững

~~~java
order.setStatus("CONFIRMED");
entityManager.flush();
~~~

Sau flush, Hibernate đã gửi UPDATE trong transaction hiện tại. Một JDBC query trên **cùng connection/transaction** có thể nhìn thấy thay đổi đó. Nhưng nếu transaction rollback, row sẽ trở về state trước đó.

### 4.2. clear() tránh đọc entity cũ từ L1

~~~java
entityManager.flush();
entityManager.clear();
~~~

Sau `clear()`, lần `find()` tiếp theo không thể dùng managed instance cũ từ L1. Tuy nhiên nó vẫn đọc qua Hibernate mapping; nếu mục tiêu là kiểm tra cột vật lý hoặc trigger, JDBC query độc lập có thể phù hợp hơn.

### 4.3. clear() trước flush có thể làm mất pending changes

~~~java
order.setStatus("CONFIRMED");
entityManager.clear(); // Entity detached trước khi flush.
~~~

Thay đổi chưa flush có thể không được ghi. Khi cần xác minh dữ liệu vừa sửa, flush trước rồi mới clear.

### 4.4. refresh() không tương đương SQL độc lập

~~~java
entityManager.refresh(order);
~~~

Refresh yêu cầu provider đọc lại entity state, nhưng vẫn dùng mapping Hibernate và có thể ảnh hưởng collection/lock semantics. Nó không xác nhận trigger, cột, join hoặc constraint theo một query độc lập.

### 4.5. Commit tạo ranh giới bền vững rõ hơn

Đối với test cần kiểm tra dữ liệu mà transaction khác sẽ thấy, commit transaction ghi rồi mở transaction đọc mới. Một JDBC query trong transaction ghi không chứng minh transaction khác đã nhìn thấy dữ liệu sau commit.

## 5. Một JDBC query độc lập qua JdbcTemplate

Spring JDBC có thể dùng cùng DataSource với JPA:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSqlVerifier {
    private final JdbcTemplate jdbcTemplate;

    public OrderSqlVerifier(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public OrderRowSnapshot findSnapshot(Long id) {
        return jdbcTemplate.queryForObject("""
            SELECT id, organization_id, customer_id,
                   order_number, status, total_amount
            FROM purchase_orders
            WHERE id = ?
            """,
            (rs, rowNum) -> new OrderRowSnapshot(
                rs.getLong("id"),
                rs.getLong("organization_id"),
                rs.getLong("customer_id"),
                rs.getString("order_number"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount")
            ),
            id
        );
    }
}
~~~

DTO kiểm chứng:

~~~java
public record OrderRowSnapshot(
    Long id,
    Long organizationId,
    Long customerId,
    String orderNumber,
    String status,
    BigDecimal totalAmount
) {}
~~~

Đây là một đường đọc độc lập với entity mapping, nhưng vẫn dùng cùng DataSource/connection infrastructure. Cần nhớ Spring có thể bind JdbcTemplate vào cùng transaction nếu đang có transaction được quản lý.

### 5.1. Parameter binding

Luôn dùng `?` hoặc named parameters:

~~~java
jdbcTemplate.queryForObject(
    "select status from purchase_orders where id = ?",
    String.class,
    id
);
~~~

Không nối ID hoặc text từ input vào SQL string. Test code cũng cần giữ thói quen an toàn để không vô tình kiểm thử một pattern dễ bị SQL injection.

### 5.2. RowMapper phải ánh xạ rõ

RowMapper chỉ nên lấy các cột cần đối chiếu. Không dùng entity mapper của Hibernate trong đường kiểm chứng, vì điều đó làm mất tính độc lập của assertion.

### 5.3. SQL độc lập có thể dùng NamedParameterJdbcTemplate

~~~java
MapSqlParameterSource params =
    new MapSqlParameterSource()
        .addValue("orderId", orderId)
        .addValue("organizationId", organizationId);

List<Map<String, Object>> rows =
    namedParameterJdbcTemplate.queryForList("""
        SELECT id, organization_id, status
        FROM purchase_orders
        WHERE id = :orderId
          AND organization_id = :organizationId
        """, params);
~~~

Named parameters giúp query nhiều điều kiện dễ đọc hơn và giảm lỗi thứ tự bind.

## 6. Đối soát quan hệ bằng JOIN độc lập

Giả sử Order phải tham chiếu Customer cùng organization. SQL:

~~~sql
SELECT
    o.id AS order_id,
    o.organization_id AS order_org_id,
    o.customer_id,
    c.id AS customer_id_found,
    c.organization_id AS customer_org_id
FROM purchase_orders o
LEFT JOIN customers c
    ON c.id = o.customer_id
WHERE o.id = :orderId;
~~~

Assertion:

~~~java
assertEquals(snapshot.orderOrganizationId(),
             snapshot.customerOrganizationId());
assertEquals(snapshot.customerId(),
             snapshot.joinedCustomerId());
~~~

### 6.1. Vì sao LEFT JOIN?

LEFT JOIN giữ lại Order ngay cả khi Customer không tồn tại. Nếu dùng INNER JOIN, một Order bị orphan có thể biến mất khỏi result set và test chỉ thấy “không có row”, khó phân biệt Order không tồn tại với Customer missing.

### 6.2. Phát hiện orphan rows

~~~sql
SELECT o.id, o.customer_id
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Kết quả phải rỗng nếu customer_id bắt buộc và FK được kỳ vọng thực thi. Đây là một query đối soát dữ liệu, hữu ích cho migration/legacy cleanup.

### 6.3. Phát hiện cross-organization references

~~~sql
SELECT
    o.id,
    o.organization_id AS order_org,
    c.organization_id AS customer_org
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id <> c.organization_id;
~~~

Kết quả phải rỗng. Query này trực tiếp kiểm tra invariant, không dựa vào cách Hibernate ánh xạ association.

### 6.4. Kiểm tra toàn bộ graph

Với Order → Customer, OrderItem → Order, OrderItem → Product, Shipment → Warehouse, cần query riêng hoặc một query join có đầy đủ predicates cho từng cạnh. Không chỉ kiểm tra root Order và suy ra toàn bộ graph đúng.

## 7. Đối soát khóa nghiệp vụ và tính duy nhất

Một business key thường unique trong phạm vi organization:

~~~sql
UNIQUE (organization_id, order_number)
~~~

Kiểm tra duplicate:

~~~sql
SELECT organization_id, order_number, COUNT(*) AS row_count
FROM purchase_orders
GROUP BY organization_id, order_number
HAVING COUNT(*) > 1;
~~~

Kết quả phải rỗng nếu business rule yêu cầu unique toàn bộ rows.

### 7.1. Nếu mã chỉ unique trên rows active

Với soft delete:

~~~sql
SELECT organization_id, order_number, COUNT(*) AS row_count
FROM purchase_orders
WHERE deleted_at IS NULL
GROUP BY organization_id, order_number
HAVING COUNT(*) > 1;
~~~

Đối soát cần dùng đúng phạm vi business key. Nếu unique constraint áp dụng toàn bảng nhưng test chỉ kiểm tra active rows, nó bỏ sót duplicate giữa các rows deleted.

### 7.2. Test constraint bằng cách cố ý INSERT duplicate

~~~java
assertThrows(DataIntegrityViolationException.class, () ->
    jdbcTemplate.update("""
        INSERT INTO purchase_orders(
            organization_id, customer_id, order_number,
            status, created_at, total_amount, version
        ) VALUES (?, ?, ?, 'DRAFT', CURRENT_TIMESTAMP, 10.00, 0)
        """,
        organizationId, customerId, existingOrderNumber
    )
);
~~~

Đây là test database constraint độc lập. Dùng đúng schema và engine có constraint thật; nếu test chạy trên H2, nó chỉ chứng minh H2 đã từ chối.

### 7.3. Unique check trước insert không thay constraint

Application:

~~~java
if (!repository.existsByOrganizationIdAndOrderNumber(orgId, number)) {
    repository.save(order);
}
~~~

không chống được hai transactions đồng thời. SQL kiểm chứng phải test race/constraint thật nếu uniqueness quan trọng.

## 8. Đối soát composite foreign key bằng SQL

Với schema:

~~~sql
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id)
~~~

Một câu INSERT sai:

~~~sql
INSERT INTO purchase_orders(
    organization_id, customer_id, order_number,
    status, created_at, total_amount, version
)
VALUES (
    7, 82, 'SO-CROSS',
    'DRAFT', CURRENT_TIMESTAMP, 10.00, 0
);
~~~

Nếu Customer 82 thuộc organization 8, database phải từ chối.

### 8.1. Phân biệt application guard và database guard

Constructor có thể từ chối:

~~~java
if (!orderOrgId.equals(customer.getOrganizationId())) {
    throw new IllegalArgumentException();
}
~~~

Đó là kiểm tra domain. Để chứng minh FK, test phải bypass constructor/service bằng JDBC hoặc native SQL có chủ đích.

### 8.2. Constraint violation phải rollback

Một statement vi phạm FK không nên được catch rồi tiếp tục dùng transaction như bình thường. PostgreSQL thường đánh dấu transaction aborted sau lỗi statement; cần rollback transaction hoặc xử lý savepoint được thiết kế rõ.

### 8.3. Kiểm tra dữ liệu sau khi constraint đã tồn tại

Constraint có thể bị disable/NOT VALID trong migration hoặc bị bỏ sót ở một environment. Có thể đối soát:

~~~sql
SELECT o.id
FROM purchase_orders o
LEFT JOIN customers c
  ON c.organization_id = o.organization_id
 AND c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Kết quả phải rỗng. Query này phát hiện cả orphan lẫn sai organization theo composite key.

## 9. Kiểm tra CHECK constraints và dữ liệu ngoài miền

Ví dụ:

~~~sql
CHECK (total_amount >= 0)
CHECK (quantity > 0)
CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
~~~

SQL đối soát:

~~~sql
SELECT id, total_amount
FROM purchase_orders
WHERE total_amount < 0;
~~~

~~~sql
SELECT id, status
FROM purchase_orders
WHERE status NOT IN ('DRAFT', 'CONFIRMED', 'CANCELLED');
~~~

### 9.1. NULL semantics

Trong SQL, CHECK expression trả TRUE hoặc UNKNOWN có thể được chấp nhận tùy database semantics; CHECK `quantity > 0` không thay `quantity NOT NULL`. Nếu quantity bắt buộc, phải có cả NOT NULL.

### 9.2. Kiểm tra null và out-of-range riêng

~~~sql
SELECT COUNT(*)
FROM order_items
WHERE quantity IS NULL OR quantity <= 0;
~~~

Đây là đối soát dữ liệu. Constraint thực thi lúc write và query đối soát kiểm tra rows hiện hữu; hai mục đích bổ sung nhau.

### 9.3. Test constraint không chỉ assert exception

Sau khi cố tình insert invalid data, xác nhận transaction rollback và database không còn row invalid. Nếu test transaction bị abort, đọc lại trong một transaction mới.

## 10. Đối soát soft delete

Soft delete thường dùng `deleted_at` hoặc boolean `is_deleted`. Ví dụ:

~~~sql
UPDATE purchase_orders
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = :orderId;
~~~

Kiểm tra:

~~~sql
SELECT id, deleted_at
FROM purchase_orders
WHERE id = :orderId;
~~~

### 10.1. Entity state có thể khác database state

Sau bulk/native UPDATE, entity đang managed có thể giữ `deletedAt = null` trong L1. JDBC query độc lập trên cùng transaction có thể thấy giá trị mới nếu nó chạy trên cùng transaction/connection sau statement.

### 10.2. Kiểm tra rows active và deleted

~~~sql
SELECT
    COUNT(*) FILTER (WHERE deleted_at IS NULL) AS active_count,
    COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_count
FROM purchase_orders
WHERE organization_id = :orgId;
~~~

Đây là cú pháp PostgreSQL. Nếu cần SQL portable, dùng SUM(CASE WHEN ... THEN 1 ELSE 0 END). Test native aggregate theo database đích.

### 10.3. Soft delete không đồng nghĩa physical delete

~~~sql
SELECT COUNT(*)
FROM purchase_orders
WHERE id = :orderId;
~~~

vẫn có thể trả 1 sau soft delete. Nếu repository filter active trả empty, SQL độc lập giúp xác nhận row vẫn tồn tại và deleted_at đã được set.

### 10.4. Kiểm tra unique key active

Nếu business cho phép tái sử dụng order_number sau soft delete, kiểm tra duplicate active rows và thử insert/restore theo partial unique index. Một query chỉ đếm tất cả rows không thể xác minh partial uniqueness.

## 11. Đối soát generated values và database defaults

Một bảng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Sau persist/flush:

~~~java
entityManager.persist(order);
entityManager.flush();
~~~

Đọc trực tiếp:

~~~java
OffsetDateTime createdAt = jdbcTemplate.queryForObject(
    "select created_at from purchase_orders where id = ?",
    OffsetDateTime.class,
    order.getId()
);
~~~

### 11.1. Kiểm tra default thực sự từ database

Nếu Hibernate đã gửi created_at do entity có giá trị, DB default không được sử dụng. Để kiểm tra default, INSERT qua JDBC và **bỏ qua cột created_at**:

~~~sql
INSERT INTO purchase_orders(order_number)
VALUES ('SO-DEFAULT')
RETURNING id, created_at;
~~~

`RETURNING` là PostgreSQL-specific. Có thể dùng GeneratedKeyHolder/JDBC hoặc query lại theo key nếu database/driver phù hợp.

### 11.2. Kiểm tra trigger

Nếu trigger thay đổi status hoặc tạo audit row, query trực tiếp cả bảng chính và bảng audit sau INSERT/UPDATE. Không chỉ assert entity field trong memory, vì trigger chạy ở database.

### 11.3. Generated value có thể cần refresh

Hibernate có thể cần mapping generated-value phù hợp hoặc refresh để đồng bộ object state sau trigger/default. SQL độc lập giúp phân biệt:

- DB đã ghi đúng nhưng entity chưa refresh.
- Hibernate đã ghi giá trị khác kỳ vọng.
- Trigger/default không chạy.

## 12. Đối soát timestamp, timezone và precision

Với PostgreSQL:

~~~sql
SELECT
    created_at,
    created_at AT TIME ZONE 'UTC' AS created_at_utc
FROM purchase_orders
WHERE id = :id;
~~~

### 12.1. So sánh theo contract

Nếu column `timestamptz` lưu một instant, test nên so sánh Instant tương đương, không dựa vào chuỗi hiển thị timezone của session.

### 12.2. Precision

Database có thể lưu microseconds trong khi Java Instant có nanoseconds. Nếu ghi:

~~~java
Instant value = Instant.parse(
    "2026-11-15T10:20:30.123456789Z");
~~~

giá trị đọc lại có thể bị làm tròn/cắt theo column precision. SQL độc lập cho biết database thực sự lưu gì.

### 12.3. Decimal

~~~sql
SELECT total_amount,
       scale(total_amount) AS stored_scale
FROM purchase_orders
WHERE id = :id;
~~~

`scale()` là function PostgreSQL. Nếu test portable, đọc BigDecimal rồi kiểm tra `scale()`/compareTo theo contract. Không dùng equals khi scale không phải một phần semantics.

### 12.4. Không so sánh text format thay cho value

Timestamp, numeric, UUID có cách serialize khác nhau. Đọc typed JDBC values khi có thể; nếu dùng raw string, normalize format và timezone trước assertion.

## 13. Kiểm tra native SQL và bulk DML

Một service dùng Hibernate bulk update:

~~~java
int updated = entityManager.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    where o.organizationId = :orgId
      and o.status = 'DRAFT'
    """)
    .setParameter("status", "CONFIRMED")
    .setParameter("orgId", organizationId)
    .executeUpdate();
~~~

Đối soát trực tiếp:

~~~sql
SELECT id, status
FROM purchase_orders
WHERE organization_id = :orgId
  AND status = 'CONFIRMED';
~~~

### 13.1. Affected row count không đủ

`updated == 10` cho biết 10 rows bị tác động theo statement semantics. Nó chưa chứng minh đúng 10 Orders dự kiến. SQL độc lập có thể so sánh tập IDs hoặc điều kiện trạng thái sau update.

### 13.2. Bulk DML có thể bypass entity callbacks

JPQL bulk update không đi qua từng entity lifecycle như dirty checking thông thường. Nếu audit field chỉ được set trong @PreUpdate, bulk update có thể không cập nhật nó. SQL đối soát audit columns sẽ phát hiện.

### 13.3. Native SQL có thể bypass Hibernate Filter

Nếu SQL native không có organization predicate, filter Session không tự chèn điều kiện. Đối soát tập rows bị ảnh hưởng để xác nhận query chỉ tác động scope dự kiến.

### 13.4. L1 có thể stale sau bulk update

Sau bulk DML, entity managed có thể giữ state cũ. Đừng assert bằng getter cũ; dùng clear/refresh phù hợp hoặc JDBC query độc lập. Nếu clear, đảm bảo pending changes đã flush trước.

## 14. Kiểm tra trigger và bảng audit

Giả sử database trigger ghi lịch sử:

~~~sql
CREATE TABLE order_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    old_status VARCHAR(30),
    new_status VARCHAR(30),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Sau update:

~~~sql
UPDATE purchase_orders
SET status = 'CONFIRMED'
WHERE id = :id;
~~~

Đối soát:

~~~sql
SELECT old_status, new_status, changed_at
FROM order_audit
WHERE order_id = :id
ORDER BY id DESC
LIMIT 1;
~~~

### 14.1. Kiểm tra đúng một audit event

~~~sql
SELECT COUNT(*)
FROM order_audit
WHERE order_id = :id
  AND new_status = 'CONFIRMED';
~~~

Nếu trigger phải tạo đúng một row mỗi lần chuyển trạng thái, test cần xác định transaction có retry/duplicate không và trigger timing.

### 14.2. Hibernate callback khác database trigger

@PostUpdate chạy theo lifecycle ORM; trigger chạy theo database statement. JDBC/native writer vẫn kích hoạt DB trigger nhưng không kích hoạt JPA callback. SQL độc lập là cách phù hợp để xác minh behavior của trigger.

### 14.3. Transaction rollback

Nếu trigger ghi audit trong cùng transaction và transaction rollback, audit row cũng thường rollback. Test cần xác minh cả bảng chính và audit sau rollback trong transaction mới.

## 15. Kiểm tra UNIQUE và FK thực sự tồn tại trong schema

Đối soát dữ liệu không chứng minh constraint đã được khai báo. Nếu database hiện tại tình cờ chưa có duplicate, một UNIQUE constraint thiếu vẫn không bị phát hiện.

Cần kiểm tra catalog/schema metadata.

### 15.1. PostgreSQL: constraints

~~~sql
SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition,
    convalidated
FROM pg_constraint
WHERE conrelid = 'purchase_orders'::regclass
ORDER BY conname;
~~~

Các giá trị contype phổ biến:

- `p`: primary key.
- `u`: unique.
- `f`: foreign key.
- `c`: check.

`convalidated` cho biết constraint đã được validate theo trạng thái PostgreSQL.

### 15.2. PostgreSQL: indexes

~~~sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'purchase_orders'
ORDER BY indexname;
~~~

Với partial index, `indexdef` thể hiện predicate. Có thể kiểm tra tên/index definition trong migration integration test.

### 15.3. PostgreSQL: triggers

~~~sql
SELECT
    trigger_name,
    event_manipulation,
    action_timing,
    action_statement
FROM information_schema.triggers
WHERE event_object_table = 'purchase_orders';
~~~

### 15.4. Catalog assertion và runtime assertion là hai thứ

Catalog xác nhận constraint/index/trigger được khai báo. Một test insert/update thực tế xác nhận database thực thi nó trong điều kiện đang chạy. Cả hai hữu ích khi constraint là yêu cầu quan trọng.

## 16. SQL độc lập phải độc lập về giả định, không chỉ độc lập về API

Một test dễ mắc lỗi:

1. Hibernate query sai vì quên organization predicate.
2. JDBC query copy nguyên WHERE clause sai đó.
3. Cả hai trả cùng kết quả.
4. Test pass dù invariant vẫn bị vi phạm.

Một SQL assertion tốt bắt đầu từ **business invariant**, không copy query implementation.

### 16.1. Ví dụ invariant same-organization

Business rule:

~~~text
Mỗi Order và Customer được tham chiếu phải thuộc cùng organization.
~~~

SQL kiểm chứng:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id <> c.organization_id;
~~~

Kỳ vọng count = 0.

### 16.2. Ví dụ invariant tổng tiền

Nếu totalAmount phải bằng tổng line totals:

~~~sql
SELECT
    o.id,
    o.total_amount,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS computed_total
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :id
GROUP BY o.id, o.total_amount;
~~~

Đây là phép đối soát độc lập với Java calculation. Nếu discount, tax, shipping hoặc rounding có quy tắc riêng, SQL phải tái hiện **đúng contract** hoặc kiểm tra một subset invariant. Không tạo một phép tính SQL đơn giản rồi gọi nó là source of truth khi domain có logic phức tạp hơn.

### 16.3. Tránh tautological assertion

Nếu cả service và SQL assertion cùng gọi một helper `calculateTotal()`, test không độc lập. Đối với quy tắc tài chính quan trọng, dùng các input/output fixtures được xác định độc lập và kiểm tra row/ledger/aggregate theo contract.

## 17. Đối soát aggregate và phép tính

Ví dụ Order phải có tổng quantity bằng tổng các line:

~~~sql
SELECT
    o.id,
    o.total_quantity,
    COALESCE(SUM(i.quantity), 0) AS actual_quantity
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :orderId
GROUP BY o.id, o.total_quantity;
~~~

### 17.1. JOIN nhiều bảng có thể nhân tổng

Nếu join Items và Shipments cùng lúc, mỗi Item có thể lặp theo số Shipments; SUM(i.quantity) có thể bị nhân. Đối soát nên:

- Aggregate mỗi bảng con riêng.
- Dùng subquery/CTE theo từng association.
- Hoặc tính trên query chỉ join một tập child.

Ví dụ:

~~~sql
WITH item_totals AS (
    SELECT order_id, SUM(quantity) AS total_quantity
    FROM order_items
    GROUP BY order_id
),
shipment_totals AS (
    SELECT order_id, COUNT(*) AS shipment_count
    FROM shipments
    GROUP BY order_id
)
SELECT
    o.id,
    COALESCE(i.total_quantity, 0) AS total_quantity,
    COALESCE(s.shipment_count, 0) AS shipment_count
FROM purchase_orders o
LEFT JOIN item_totals i ON i.order_id = o.id
LEFT JOIN shipment_totals s ON s.order_id = o.id
WHERE o.id = :orderId;
~~~

### 17.2. NULL và COALESCE

SUM không có rows thường trả NULL. Nếu business semantics là 0, dùng COALESCE. Nhưng không dùng COALESCE để che dữ liệu thiếu bắt buộc; xác định rõ absence có nghĩa zero hay violation.

### 17.3. Rounding

SQL NUMERIC arithmetic và Java BigDecimal có thể khác nếu một bên scale/rounding sớm hơn. Đối soát tài chính cần quy định scale, rounding mode và thời điểm làm tròn ở từng line/order.

## 18. Đối soát dữ liệu multi-tenant

Một truy vấn:

~~~sql
SELECT
    o.id,
    o.organization_id,
    c.organization_id AS customer_org
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id = :orgId;
~~~

kiểm tra dữ liệu trong organization cụ thể.

### 18.1. Đối soát toàn database

~~~sql
SELECT o.id
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id <> c.organization_id;
~~~

Hữu ích cho migration, audit và kiểm tra constraint toàn cục.

### 18.2. Không chỉ kiểm tra row trả về bởi repository

Repository đã lọc tenant có thể bỏ sót các rows sai tenant. SQL kiểm tra toàn bảng có thể phát hiện dữ liệu cross-tenant mà query repository không bao giờ trả.

### 18.3. RLS ảnh hưởng SQL verifier

Nếu PostgreSQL RLS được bật và test chạy bằng app role, SQL verifier cũng có thể chỉ thấy rows trong tenant scope. Điều đó tốt khi kiểm tra runtime isolation, nhưng nếu cần audit toàn bảng, dùng một test role được kiểm soát riêng có quyền phù hợp; không dùng superuser để test RLS enforcement.

### 18.4. Tách hai mục tiêu test

- Runtime role: xác minh user/tenant không đọc hoặc ghi ngoài scope.
- Audit/admin test role: xác minh invariant toàn database, constraint và dữ liệu lịch sử.

Không dùng một role duy nhất rồi kết luận cả hai mục tiêu đều đã được kiểm tra.

## 19. Đối soát soft-delete và dữ liệu liên quan

Một invariant có thể là:

> Không tạo Order mới cho Customer đã soft-delete.

SQL kiểm tra dữ liệu đã tồn tại:

~~~sql
SELECT o.id, o.customer_id
FROM purchase_orders o
JOIN customers c
  ON c.id = o.customer_id
 AND c.organization_id = o.organization_id
WHERE c.deleted_at IS NOT NULL
  AND o.created_at >= :policyStart;
~~~

Query này tìm những Orders trong khoảng thời gian policy mà tham chiếu Customer đã deleted.

### 19.1. Xác định semantics thời gian

Nếu Customer bị xóa hôm nay nhưng Order được tạo năm trước, đó có thể là quan hệ hợp lệ. Cần so sánh created_at và deleted_at theo đúng business rule; không đơn giản yêu cầu mọi Order luôn trỏ Customer active ở thời điểm hiện tại.

### 19.2. Constraint không dễ enforce trạng thái ở bảng khác

FK chỉ kiểm tra row tồn tại/khóa tham chiếu. Nó không kiểm tra `customers.deleted_at IS NULL`. Muốn bảo đảm ở mọi writer có thể cần trigger, schema model khác hoặc transaction logic có locking. Test SQL độc lập giúp xác nhận invariant sau workflow.

### 19.3. Restore

Khi restore Customer, kiểm tra các business key/relationships và rows liên quan. Một Customer được restore không có nghĩa mọi Orders lịch sử tự trở nên hợp lệ theo trạng thái hiện tại.

## 20. Đối soát optimistic locking và version

Entity:

~~~java
@Version
private long version;
~~~

Sau update:

~~~sql
SELECT id, status, version
FROM purchase_orders
WHERE id = :id;
~~~

### 20.1. Kiểm tra version tăng

Nếu một lần update thành công qua Hibernate, version thường tăng theo provider strategy. Assert giá trị DB sau flush/commit, không chỉ đọc field trong entity trước flush.

### 20.2. Kiểm tra stale update

1. T1 và T2 load cùng row/version.
2. T1 update/commit.
3. T2 cố update/flush.
4. T2 phải nhận optimistic conflict.
5. JDBC query trong transaction mới xác nhận chỉ update của T1 được giữ.

### 20.3. Bulk DML có thể không tăng version tự động

Bulk JPQL/native UPDATE không đi qua dirty checking từng entity như thường. Nếu version phải tăng, query phải được thiết kế rõ:

~~~sql
UPDATE purchase_orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND organization_id = :orgId
  AND version = :expectedVersion;
~~~

Đối soát row count và version mới qua SQL độc lập.

## 21. Đối soát transaction rollback

Một test:

~~~java
@Transactional
@Test
void rollbackDoesNotPersistOrder() {
    PurchaseOrder order = repository.save(newOrder());
    entityManager.flush();

    assertNotNull(order.getId());
}
~~~

Nếu test framework rollback transaction sau method, SQL query trong cùng transaction vẫn thấy row. Điều đó **không chứng minh row đã commit**.

### 21.1. Đọc trong transaction mới

Muốn kiểm tra rollback/commit visibility, transaction ghi và transaction đọc phải được tách rõ:

~~~text
T1: INSERT -> FLUSH -> ROLLBACK
T2: SELECT -> không thấy row
~~~

hoặc:

~~~text
T1: INSERT -> FLUSH -> COMMIT
T2: SELECT -> thấy row
~~~

### 21.2. Spring TransactionTemplate

~~~java
Long id = transactionTemplate.execute(status -> {
    PurchaseOrder order = repository.save(newOrder());
    entityManager.flush();
    return order.getId();
});

Integer count = transactionTemplate.execute(status ->
    jdbcTemplate.queryForObject(
        "select count(*) from purchase_orders where id = ?",
        Integer.class,
        id
    )
);
~~~

Ví dụ này giả định TransactionTemplate đầu tiên commit thành công khi callback kết thúc bình thường. Transaction thứ hai đọc trong transaction khác. Cần bảo đảm EntityManager/JdbcTemplate được Spring bind đúng transaction manager/DataSource.

### 21.3. Test rollback chủ động

~~~java
transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "insert into audit_probe(id) values (?)",
        probeId
    );
    status.setRollbackOnly();
});

Integer count = jdbcTemplate.queryForObject(
    "select count(*) from audit_probe where id = ?",
    Integer.class,
    probeId
);
assertEquals(0, count);
~~~

### 21.4. Không query bằng cùng transaction rồi gọi là commit assertion

Một SELECT cùng transaction thấy uncommitted writes của chính transaction. Nó không chứng minh transaction khác đã được phép thấy row.

## 22. Isolation và snapshot khi đối soát

Một test dùng hai connections:

~~~text
T1: UPDATE order status
T2: SELECT order status
T1: COMMIT
T2: SELECT lại
~~~

Kết quả T2 nhìn thấy phụ thuộc isolation và statement timing.

### 22.1. READ COMMITTED

Trên PostgreSQL, mỗi statement READ COMMITTED có snapshot mới. T2 có thể không thấy update trước commit, rồi thấy ở SELECT sau commit.

### 22.2. REPEATABLE READ

Transaction T2 có thể tiếp tục nhìn snapshot đã có từ statement đầu. SQL độc lập trên cùng T2 không nhất thiết nhìn state mới nhất.

### 22.3. Đối soát sau commit nên dùng transaction mới

Nếu mục tiêu là xác minh trạng thái đã commit, mở transaction mới với isolation phù hợp. Không dùng một transaction snapshot cũ để kết luận dữ liệu chưa được ghi.

### 22.4. Read replica

Nếu ứng dụng đọc từ replica có replication lag, một SQL verifier dùng read replica ngay sau commit primary có thể chưa thấy row. Test write/read consistency cần kết nối primary hoặc chờ replication theo cơ chế rõ; không nhầm lag với lỗi persist.

## 23. SQL độc lập cho pagination và thứ tự

Một repository trả Page:

~~~java
Page<PurchaseOrder> page =
    repository.findByOrganizationId(
        organizationId,
        PageRequest.of(0, 20,
            Sort.by(DESC, "createdAt").and(
                Sort.by(DESC, "id")
            )
        )
    );
~~~

SQL đối soát:

~~~sql
SELECT id, created_at
FROM purchase_orders
WHERE organization_id = :orgId
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

### 23.1. Stable order

Thêm ID làm tie-breaker để tránh thứ tự không xác định khi nhiều rows có cùng timestamp.

### 23.2. Count query

~~~sql
SELECT COUNT(*)
FROM purchase_orders
WHERE organization_id = :orgId;
~~~

So sánh total elements với Page metadata. Nếu repository join to-many, count query cần kiểm tra duplicate root và DISTINCT semantics.

### 23.3. Không copy chính query Hibernate

SQL đối soát nên viết độc lập dựa trên expected scope/order. Nếu copy nguyên query generated SQL rồi so với chính nó, test có thể không phát hiện thiếu predicate hoặc join sai.

## 24. Đối soát mapping cột và association

Một entity:

~~~java
@Column(name = "organization_id")
private Long organizationId;

@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

SQL độc lập:

~~~sql
SELECT
    id,
    organization_id,
    customer_id,
    status,
    total_amount
FROM purchase_orders
WHERE id = :id;
~~~

### 24.1. Kiểm tra column names

Nếu annotation vô tình map `organization_id` sang column khác hoặc column cũ, SQL đọc physical schema sẽ phát hiện giá trị không như mong muốn.

### 24.2. Kiểm tra association join

Đọc cả customer_id từ Order và Customer.id trực tiếp. Nếu Hibernate association trả Customer khác vì mapping sai JoinColumn, SQL độc lập giúp tách vấn đề mapping khỏi dữ liệu.

### 24.3. Kiểm tra nullability

Một field Java primitive `long` không thể giữ null, nhưng database column có thể null nếu schema sai. JDBC `getLong()` trả 0 cho SQL NULL; phải gọi `wasNull()` hoặc dùng wrapper mapping để không nhầm NULL thành 0.

~~~java
long raw = rs.getLong("organization_id");
Long organizationId = rs.wasNull() ? null : raw;
~~~

### 24.4. Kiểm tra enum conversion

Nếu entity dùng converter/STRING/ORDINAL, SQL query đọc raw column để xác nhận code thực tế. Đừng chỉ assert Java enum sau một converter có thể sai đồng nhất ở cả read/write.

## 25. Đối soát row count và duplicate do JOIN

Một query repository có JOIN:

~~~hql
select o
from PurchaseOrder o
join o.items i
where i.sku = :sku
~~~

có thể trả root entities theo semantics Hibernate nhưng SQL result rows có thể có duplicate root IDs nếu nhiều Items cùng SKU.

SQL độc lập:

~~~sql
SELECT o.id, COUNT(i.id) AS matching_items
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.sku = :sku
GROUP BY o.id;
~~~

### 25.1. So sánh root count và row count

~~~sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.id) AS distinct_orders
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.sku = :sku;
~~~

Nếu hai con số khác nhau, join có nhiều rows trên mỗi Order. Đây có thể là đúng, nhưng phải hiểu trước khi pagination/count.

### 25.2. DISTINCT ở ORM không thay SQL invariant

Hibernate có thể deduplicate root entity instances. SQL độc lập giúp kiểm tra actual joined rows, duplicate keys và aggregate semantics.

## 26. Đối soát dữ liệu do cascade/orphan removal tạo ra

Một aggregate:

~~~java
order.getItems().remove(item);
~~~

với `orphanRemoval = true` có thể làm child row bị DELETE khi flush.

SQL:

~~~sql
SELECT COUNT(*)
FROM order_items
WHERE id = :itemId;
~~~

### 26.1. Xóa vật lý hay soft delete?

Nếu mapping `@SQLDelete`/soft-delete behavior, row có thể vẫn tồn tại với deleted marker. SQL assertion cần kiểm tra đúng cột, không chỉ COUNT(*).

### 26.2. Cascade REMOVE

Xóa Order có thể cascade xóa Items tùy mapping/DB FK behavior. SQL độc lập kiểm tra cả parent và child sau commit/rollback.

### 26.3. FK ON DELETE khác JPA cascade

Database ON DELETE CASCADE chạy khi parent row bị xóa vật lý. JPA CascadeType.REMOVE chạy qua ORM lifecycle. Bulk/native delete có thể kích hoạt DB cascade nhưng không chạy entity callbacks. Test phải xác minh cơ chế thực sự được dùng.

## 27. Đối soát bằng CTE để kiểm tra nhiều invariant

PostgreSQL CTE:

~~~sql
WITH orphan_orders AS (
    SELECT o.id
    FROM purchase_orders o
    LEFT JOIN customers c
      ON c.id = o.customer_id
     AND c.organization_id = o.organization_id
    WHERE c.id IS NULL
),
duplicate_numbers AS (
    SELECT organization_id, order_number
    FROM purchase_orders
    WHERE deleted_at IS NULL
    GROUP BY organization_id, order_number
    HAVING COUNT(*) > 1
),
negative_totals AS (
    SELECT id
    FROM purchase_orders
    WHERE total_amount < 0
)
SELECT
    (SELECT COUNT(*) FROM orphan_orders) AS orphan_count,
    (SELECT COUNT(*) FROM duplicate_numbers) AS duplicate_count,
    (SELECT COUNT(*) FROM negative_totals) AS negative_count;
~~~

### 27.1. Dùng CTE trong migration verification

Sau backfill dữ liệu, CTE có thể tổng hợp số vi phạm trước khi thêm FK/UNIQUE/CHECK. Nếu bất kỳ count nào khác 0, migration pipeline có thể dừng và yêu cầu xử lý dữ liệu.

### 27.2. Không biến test thành một câu SQL khổng lồ khó hiểu

Tách query theo invariant giúp thông báo lỗi rõ hơn: orphan, cross-org, duplicate business key, invalid total. CTE tổng hợp phù hợp cho audit/report hoặc migration gate.

### 27.3. Đối soát toàn bộ dataset có thể tốn

Test integration thường seed dữ liệu nhỏ; production audit có thể cần indexes, chunking và read replica. Không chạy full table scans trong mỗi unit test.

## 28. SQL độc lập khi test migration

Migration tạo composite FK:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT fk_order_customer_same_org
FOREIGN KEY (organization_id, customer_id)
REFERENCES customers(organization_id, id);
~~~

Test migration cần hai loại assertion:

1. Constraint được khai báo trong schema.
2. Constraint thực sự chặn dữ liệu vi phạm.

### 28.1. Catalog assertion

~~~sql
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'fk_order_customer_same_org';
~~~

### 28.2. Runtime assertion

Thử insert Order organization 7 tham chiếu Customer organization 8 bằng JDBC. Kỳ vọng DataIntegrityViolationException/SQLSTATE FK violation.

### 28.3. Dữ liệu cũ

Migration có thể tạo constraint NOT VALID. Catalog assertion phải kiểm tra `convalidated`; runtime assertion xác nhận writes mới bị enforce; data audit xác nhận rows lịch sử không còn vi phạm trước khi validate.

### 28.4. Hibernate validate không thay catalog check

Hibernate schema validation không xác minh mọi constraint definition, partial index predicate, trigger body hoặc RLS policy. SQL catalog query là đường kiểm tra độc lập cho các objects này.

## 29. SQLSTATE và constraint name khi kiểm tra lỗi

PostgreSQL có SQLSTATE:

- `23505`: unique_violation.
- `23503`: foreign_key_violation.
- `23514`: check_violation.
- `23502`: not_null_violation.

### 29.1. Không assert error message dài

Message có thể thay đổi theo database version, locale, driver hoặc constraint name. Nếu application mapping dựa vào SQLSTATE, test đúng database engine và kiểm tra code đó.

### 29.2. Constraint name có thể giúp map lỗi

Một tên như `uq_orders_org_number` giúp nhận diện duplicate order number. Nhưng Hibernate/Spring có thể bọc exception nhiều tầng; code cần traverse root cause có kiểm soát.

### 29.3. Đừng catch mọi DataIntegrityViolationException rồi báo duplicate

Lỗi có thể là FK, CHECK, NOT NULL hoặc UNIQUE. Chỉ map đúng lỗi theo constraint/SQLSTATE; lỗi khác cần xử lý/log phù hợp.

### 29.4. Transaction sau lỗi

PostgreSQL transaction thường không thể tiếp tục query sau statement error cho tới rollback. Test phải mở transaction mới để kiểm tra database state, không query tiếp trong transaction đã abort.

## 30. JDBC verifier có thể dùng cùng transaction với JPA

Trong Spring, JPA EntityManager và JdbcTemplate có thể tham gia cùng transaction nếu chúng dùng cùng DataSource và transaction manager được cấu hình phù hợp.

Ví dụ:

~~~java
@Transactional
public void updateAndVerify(Long id) {
    PurchaseOrder order = entityManager.find(
        PurchaseOrder.class, id);
    order.confirm();

    entityManager.flush();

    String status = jdbcTemplate.queryForObject(
        "select status from purchase_orders where id = ?",
        String.class,
        id
    );

    assertEquals("CONFIRMED", status);
}
~~~

### 30.1. Cùng transaction thấy uncommitted changes

JDBC query chạy sau flush trong cùng transaction thường nhìn thấy update do chính transaction ghi. Đây là xác nhận row-level state trước commit.

### 30.2. Không phải mọi cấu hình đều tự động chia sẻ connection

Nếu JPA và JDBC dùng DataSource khác nhau, transaction manager khác nhau hoặc transaction propagation khác, query có thể chạy connection/transaction riêng. Kiểm tra cấu hình thật; không giả định cùng `@Transactional` là đủ.

### 30.3. Transaction synchronization

Spring transaction manager có thể bind connection/resource theo thread. Không truyền EntityManager/Jdbc Connection sang thread khác. Async worker cần transaction/context riêng.

### 30.4. Test commit visibility bằng transaction mới

Nếu cần chứng minh dữ liệu đã commit và được transaction khác nhìn thấy, không chỉ query cùng transaction. Dùng TransactionTemplate hoặc service proxy tạo transaction thứ hai sau khi transaction ghi kết thúc.

## 31. JDBC verifier không nên phụ thuộc mapping Hibernate

Một verifier:

~~~java
public boolean orderAndCustomerShareOrganization(
        Long orderId) {
    Integer violations = jdbcTemplate.queryForObject("""
        SELECT COUNT(*)
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = ?
          AND o.organization_id <> c.organization_id
        """,
        Integer.class,
        orderId
    );
    return violations != null && violations == 0;
}
~~~

SQL dùng physical table/column names. Nó không gọi `PurchaseOrder.getCustomer()`, không dựa vào @JoinColumn hoặc EntityGraph.

### 31.1. Dùng SQL verifier trong test, không nhất thiết production

Verifier có thể là test helper đặt trong `src/test`, không cần trở thành production repository thứ hai. Điều này giữ đường kiểm chứng độc lập và tránh nhân đôi data-access code không cần thiết.

### 31.2. Nếu dùng chung production helper

Nếu một SQL verifier được dùng cả production và test, test có thể chỉ chứng minh helper hoạt động theo cách của chính nó. Với invariant quan trọng, nên có assertion SQL trực tiếp hoặc một test độc lập khác để tránh vòng kiểm chứng.

### 31.3. SQL assertion phải dễ đọc

Một câu query ngắn có tên rõ như `findOrderStorageSnapshot` thường tốt hơn một lớp abstraction tổng quát cho mọi test. Tránh framework test tự động tạo SQL khó audit.

## 32. So sánh kết quả ORM với kết quả SQL độc lập

Ví dụ:

~~~java
PurchaseOrder order = repository
    .findByIdAndOrganizationId(orderId, organizationId)
    .orElseThrow();

entityManager.flush();

OrderRowSnapshot stored =
    sqlVerifier.findSnapshot(orderId);

assertEquals(order.getId(), stored.id());
assertEquals(order.getOrganizationId(), stored.organizationId());
assertEquals(order.getCustomerId(), stored.customerId());
assertEquals(order.getOrderNumber(), stored.orderNumber());
assertEquals(order.getStatus(), stored.status());
assertEquals(0, order.getTotalAmount()
    .compareTo(stored.totalAmount()));
~~~

### 32.1. Cẩn thận vì ORM entity có thể đã thay đổi

Ở đây object được so với database row sau flush trong cùng transaction. Đây là mục tiêu phù hợp nếu muốn xác nhận Hibernate đã ghi đúng state. Nếu trigger thay đổi một field, entity có thể chưa tự refresh; khi đó kỳ vọng phải phân biệt DB-generated state và in-memory state.

### 32.2. Không so sánh field không có cùng semantics

Ví dụ:

- Instant nanoseconds so với timestamp microseconds.
- BigDecimal scale.
- Enum Java so với code DB.
- Boolean so với integer flag.
- UUID Java so với JDBC type representation.

Normalize theo contract trước khi so sánh.

### 32.3. So sánh association bằng FK value

Nếu chỉ cần kiểm tra association persisted, so sánh customer_id và composite organization IDs bằng SQL. Không nhất thiết load cả Customer entity qua Hibernate.

## 33. Đối soát generated IDs và sequence

Sau:

~~~java
entityManager.persist(order);
entityManager.flush();
Long id = order.getId();
~~~

JDBC:

~~~java
Integer count = jdbcTemplate.queryForObject(
    "select count(*) from purchase_orders where id = ?",
    Integer.class,
    id
);
assertEquals(1, count);
~~~

### 33.1. Không giả định sequence liên tục

Sequence/identity có thể có gaps do rollback, caching hoặc allocation. Đối soát row tồn tại theo generated ID, không assert ID tiếp theo phải là ID trước + 1.

### 33.2. Sequence state là một kiểm tra riêng

Nếu cần kiểm tra generator, query sequence metadata bằng cú pháp database-specific; không suy ra sequence state chỉ từ IDs đã persist. Sequence có thể được cache/allocate theo Hibernate generator.

### 33.3. Assigned ID

Nếu ứng dụng tự gán UUID, SQL verifier xác nhận đúng UUID được ghi. Test generator/application code riêng nếu UUID phải có format/version/namespace cụ thể.

## 34. Đối soát với database view hoặc materialized view

Một hệ thống có view tổng hợp:

~~~sql
CREATE VIEW active_order_totals AS
SELECT organization_id, COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM purchase_orders
WHERE deleted_at IS NULL
GROUP BY organization_id;
~~~

Test có thể so sánh:

1. Kết quả repository query.
2. Kết quả SQL trực tiếp từ view.
3. Aggregate độc lập từ bảng gốc.

### 34.1. View là một read model khác

Nếu view được dùng để báo cáo, SQL query view xác nhận mapping và permissions của view. Aggregate từ bảng gốc kiểm tra view definition có đúng không.

### 34.2. Materialized view có refresh semantics

Materialized view có thể stale cho tới khi REFRESH. Test phải gọi refresh theo workflow hoặc xác định eventual consistency; không mong nó cập nhật ngay như ordinary view.

### 34.3. View security

PostgreSQL view owner/security_invoker behavior và RLS có thể ảnh hưởng dữ liệu nhìn thấy. Test với đúng database role.

## 35. Đối soát bằng SQL khi kiểm tra multi-query consistency

Một service thực hiện:

1. Query Order.
2. Query Items.
3. Update Shipment.

SQL độc lập có thể kiểm tra sau commit:

~~~sql
SELECT
    o.id,
    o.total_amount,
    COUNT(i.id) AS item_count,
    COALESCE(SUM(i.quantity), 0) AS total_quantity
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
WHERE o.id = :id
GROUP BY o.id, o.total_amount;
~~~

### 35.1. Chạy sau commit

Nếu service dùng nhiều statements trong transaction, đọc sau commit bằng transaction mới giúp xác nhận trạng thái cuối cùng mà caller khác sẽ thấy theo isolation.

### 35.2. Snapshot khác nhau trong cùng transaction

Với READ COMMITTED, các statement có thể nhìn snapshots khác nhau. Nếu business yêu cầu invariant giữa nhiều tables tại commit, test bằng query tổng hợp sau commit hoặc constraints/triggers thích hợp.

### 35.3. Không nhầm query cuối với invariant mọi thời điểm

Một query sau commit xác nhận trạng thái tại lúc đọc. Nó không chứng minh không có race condition ở khoảng thời gian trước đó. Concurrency tests cần điều phối transactions độc lập.

## 36. Đối soát concurrency bằng hai transactions

Ví dụ hai request tạo cùng business key:

~~~text
T1: SELECT kiểm tra order_number SO-001 -> không có
T2: SELECT kiểm tra order_number SO-001 -> không có
T1: INSERT SO-001 -> commit
T2: INSERT SO-001 -> UNIQUE violation
~~~

SQL verifier sau hai transactions:

~~~sql
SELECT organization_id, order_number, COUNT(*)
FROM purchase_orders
WHERE organization_id = :orgId
  AND order_number = 'SO-001'
GROUP BY organization_id, order_number;
~~~

Kỳ vọng một row với count = 1.

### 36.1. Không dùng một connection cho cả hai transactions

Hai transactions phải dùng hai connections/EntityManagers độc lập. Nếu dùng cùng thread-bound EntityManager, test không mô phỏng concurrency.

### 36.2. Dùng barrier/latch để điều khiển race

Test nên đồng bộ hai workers sau bước check-before-insert để tạo race có chủ đích. Dùng timeout để tránh test treo.

### 36.3. Đối soát state cuối bằng JDBC

Sau khi cả hai transactions kết thúc, dùng transaction đọc mới để đếm rows và xác nhận chỉ một key tồn tại.

### 36.4. Test database phải là engine production

Unique conflict, lock waiting và SQLSTATE có thể khác giữa H2 và PostgreSQL. Nếu correctness phụ thuộc concurrency, chạy test trên DB đích.

## 37. Test dữ liệu sau rollback và exception

Khi insert vi phạm FK:

1. Statement ném exception.
2. Transaction bị đánh dấu rollback-only/aborted.
3. Test phải rollback.
4. Một transaction mới đọc lại row count.

Ví dụ:

~~~java
assertThrows(RuntimeException.class, () ->
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into purchase_orders(...) values (...)"
        );
    })
);

Integer count = transactionTemplate.execute(status ->
    jdbcTemplate.queryForObject(
        "select count(*) from purchase_orders where order_number = ?",
        Integer.class,
        "SO-INVALID"
    )
);
assertEquals(0, count);
~~~

Đây là skeleton; dùng câu INSERT và exception type thực tế của project. Nếu exception bị Spring transaction manager wrap, assert root cause/SQLSTATE phù hợp.

### 37.1. Không đọc tiếp trên transaction đã lỗi

PostgreSQL transaction aborted sau constraint error thường không cho SELECT tiếp cho tới rollback. Query verifier phải chạy sau transaction rollback, không đặt ngay sau statement lỗi trong cùng transaction.

### 37.2. Rollback test framework

Test method có @Transactional và rollback cuối method có thể vẫn đọc thấy dữ liệu trong cùng transaction. Muốn xác minh rollback, dùng transaction mới sau khi test transaction đã kết thúc hoặc thiết kế TransactionTemplate rõ.

## 38. SQL verifier với Testcontainers

Khi production là PostgreSQL, SQL độc lập cần chạy trên PostgreSQL nếu đang xác minh PostgreSQL constraint/trigger/type behavior.

~~~java
@Testcontainers
@SpringBootTest
class OrderStorageInvariantTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderService orderService;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void persistedOrderReferencesCustomerInSameOrganization() {
        // Arrange fixtures.
        // Call application service.
        // Flush/commit as required.

        Integer violations = jdbcTemplate.queryForObject("""
            SELECT COUNT(*)
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.id = ?
              AND o.organization_id <> c.organization_id
            """,
            Integer.class,
            orderId
        );

        assertEquals(0, violations);
    }
}
~~~

### 38.1. Container version

Pin image version theo production support matrix. Không dùng `latest` để test có thể thay đổi bất ngờ khi image được cập nhật.

### 38.2. Migrations

Đảm bảo Flyway/Liquibase chạy trên container trước khi test. Hibernate `create-drop` không nên thay migration nếu mục tiêu là kiểm tra production schema.

### 38.3. ServiceConnection

`@ServiceConnection` yêu cầu Spring Boot version có hỗ trợ và Testcontainers integration module tương ứng. Nếu không, dùng `@DynamicPropertySource` để cung cấp URL/user/password.

### 38.4. RLS và runtime role

Nếu cần kiểm tra RLS, SQL verifier chạy bằng app role sẽ chỉ thấy dữ liệu trong policy scope. Dùng role kiểm tra toàn cục riêng cho invariant audit và role runtime riêng cho authorization tests.

## 39. SQL độc lập khi test migration từ schema cũ

Một migration thêm organization_id và composite FK cần đối soát dữ liệu trước/sau:

~~~sql
SELECT o.id
FROM purchase_orders o
LEFT JOIN customers c
  ON c.organization_id = o.organization_id
 AND c.id = o.customer_id
WHERE c.id IS NULL;
~~~

### 39.1. Trước migration

Query legacy để phát hiện Order tham chiếu Customer không tồn tại hoặc mapping organization suy ra không rõ.

### 39.2. Sau backfill

Chạy query cross-org/orphan; kết quả phải rỗng trước khi validate FK.

### 39.3. Sau khi thêm constraint

Kiểm tra catalog có FK ghép đúng cột/thứ tự, convalidated = true và thử insert vi phạm.

### 39.4. Đọc row samples

Không chỉ assert COUNT = 0; khi có lỗi, lấy một số IDs mẫu để diagnostic. Trong test có thể assert count và hiển thị IDs trong assertion message.

### 39.5. Migration dữ liệu lớn

SQL audit toàn bảng có thể nặng. Trong migration pipeline, chạy theo batch/partition hoặc trên replica/snapshot phù hợp; performance/lock impact cần được đánh giá riêng.

## 40. Đối soát với database catalog: một số query PostgreSQL hữu ích

### 40.1. Xem cột và kiểu

~~~sql
SELECT
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

### 40.2. Xem constraint

~~~sql
SELECT
    conname,
    contype,
    pg_get_constraintdef(oid),
    convalidated
FROM pg_constraint
WHERE conrelid = 'purchase_orders'::regclass;
~~~

### 40.3. Xem index

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'purchase_orders';
~~~

### 40.4. Xem trigger

~~~sql
SELECT trigger_name, action_timing, event_manipulation,
       action_statement
FROM information_schema.triggers
WHERE event_object_table = 'purchase_orders';
~~~

### 40.5. Xem RLS

~~~sql
SELECT
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class c
WHERE c.oid = 'purchase_orders'::regclass;
~~~

Policy definitions có thể xem trong `pg_policies`. Catalog queries này là PostgreSQL-specific và cần chạy với role có quyền xem metadata tương ứng.

## 41. Đối soát kết quả query với EXPLAIN

SQL độc lập có hai mục tiêu khác nhau:

- **Correctness:** row/relationship/constraint có đúng không?
- **Performance:** database thực thi query như thế nào?

### 41.1. Correctness query

~~~sql
SELECT COUNT(*)
FROM purchase_orders
WHERE organization_id = :orgId
  AND deleted_at IS NULL;
~~~

### 41.2. Performance query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at
FROM purchase_orders
WHERE organization_id = 7
  AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

### 41.3. Không assert thời gian chính xác trong unit test

Execution time phụ thuộc CPU, cache, container, concurrent load và CI host. Có thể lưu plan/metrics trong benchmark suite, nhưng test correctness thông thường không nên fail vì query chậm hơn vài milliseconds.

### 41.4. Dữ liệu test nhỏ không thể chứng minh index hiệu quả

PostgreSQL có thể chọn Seq Scan trên bảng nhỏ dù index đúng. Performance test cần dataset đủ lớn và phân bố đại diện.

## 42. SQL verifier cần cẩn trọng với tenant security

Một câu SQL kiểm chứng:

~~~sql
SELECT *
FROM purchase_orders
WHERE id = :id;
~~~

có thể đọc dữ liệu ngoài organization nếu test dùng database role bypass RLS. Đây có thể là chủ đích để kiểm tra invariant toàn cục, nhưng không chứng minh runtime access policy.

### 42.1. Tách test role

- `app_runtime`: permissions và RLS giống ứng dụng.
- `test_auditor`: quyền đọc các rows cần đối soát toàn cục, chỉ dùng trong test/audit scope.

Không dùng quyền rộng của auditor để chạy application repository test.

### 42.2. Kiểm tra query ứng dụng không lộ rows

Gọi service/API bằng principal organization 7, thử ID organization 8 và xác nhận response không tiết lộ dữ liệu.

### 42.3. Kiểm tra database policy

Dùng app_runtime, thiết lập organization context theo transaction và thử SQL trực tiếp đọc/ghi organization khác. Đây là test RLS thực sự.

### 42.4. Cache có thể bypass SQL policy

Entity đã managed hoặc application cache hit có thể không phát SQL. Vì vậy test RLS phải kiểm tra cả persistence context/cache boundaries, không chỉ câu SELECT trực tiếp.

## 43. Tránh SQL assertion mong manh

Một số kiểu assertion dễ vỡ:

- So sánh nguyên văn SQL string do Hibernate sinh ra.
- Assert alias cụ thể như `purchaseor1_0`.
- Assert thứ tự cột SELECT không phải contract.
- Assert exception message đầy đủ.
- Assert ID sequence liên tục.
- Assert timestamp nanoseconds chính xác hơn DB precision.
- Assert một query count duy nhất trong khi Hibernate version có thể đổi SQL strategy.

### 43.1. Assert dữ liệu và invariant

Ưu tiên:

- Cột vật lý có giá trị đúng.
- Foreign key join tới row đúng.
- Duplicate count bằng 0.
- Vi phạm constraint bị từ chối.
- Row count/affected IDs đúng.
- Commit/rollback visibility đúng.

### 43.2. Khi cần kiểm tra SQL shape

Nếu SQL shape là yêu cầu (ví dụ native query phải dùng partial index predicate hoặc tenant filter), capture SQL và kiểm tra những đặc tính quan trọng, nhưng tránh phụ thuộc alias/formatting không ổn định. Execution plan cần test riêng.

### 43.3. Một verifier không được lặp logic implementation

Viết SQL từ business invariant và schema contract. Nếu verifier copy nguyên query repository, cả hai có thể cùng sai.

## 44. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Entity getter đúng nhưng DB row sai | Chỉ assert object trong memory | Flush rồi JDBC query |
| find() lần hai không phát SQL | Entity đã managed trong L1 | SQL độc lập hoặc context mới |
| Test thấy row dù method rollback | Query trong cùng transaction | Đọc bằng transaction mới sau rollback |
| JDBC query không thấy vừa persist | Chưa flush hoặc connection/transaction khác | Flush và xác nhận transaction binding |
| SQL verifier và repository cùng trả sai | Copy nguyên WHERE/join assumption | Viết SQL từ invariant độc lập |
| Order join Customer không cùng org | FK chỉ theo ID hoặc dữ liệu legacy | Composite FK + cross-org audit query |
| INNER JOIN không phát hiện orphan | Orphan row bị loại khỏi result | LEFT JOIN và kiểm tra parent null |
| Duplicate business key bị bỏ sót | Query kiểm tra thiếu namespace/soft-delete scope | GROUP BY đúng organization và predicate |
| Trigger không tạo audit row | Trigger/migration thiếu hoặc timing khác | Catalog assertion + runtime SQL test |
| Entity state khác row sau trigger | Entity chưa refresh/generated-value mapping | JDBC đọc raw row và kiểm tra mapping |
| Native update ảnh hưởng nhiều tenant | SQL thiếu org predicate | Kiểm tra affected IDs và row state |
| Bulk DML xong getter vẫn cũ | L1 stale | Clear/refresh đúng lúc hoặc JDBC |
| CHECK violation không bị bắt | Column nullable/UNKNOWN hoặc constraint thiếu | NOT NULL + catalog/runtime assertion |
| Unique violation nổ tại commit thay save | Flush/deferred constraint timing | Assert transaction outcome |
| SQLState test sai trên H2 | Vendor code khác | Chạy đúng DB production |
| Timestamp assertion lệch | Precision/timezone conversion | Normalize theo column contract |
| Aggregate SQL cho tổng sai | Join nhiều collection nhân rows | Aggregate child tables riêng |
| RLS verifier không thấy mọi rows | SQL chạy bằng app role | Dùng auditor role riêng cho global audit |
| RLS test không chặn cross-tenant | Test dùng owner/superuser | Runtime role và transaction-local context |
| Catalog query pass nhưng constraint không enforce | Constraint NOT VALID/disabled hoặc sai definition | Check convalidated + insert violation |
| Count query lệch page | Join to-many tạo duplicate | COUNT(DISTINCT) hoặc count query riêng |
| Query độc lập nhìn dữ liệu cũ | Transaction snapshot/replica lag | Transaction mới, primary hoặc consistency policy |
| Test concurrent không tạo race | Dùng chung connection/transaction | Hai transactions/connections và barrier |

## 45. Bài thực hành

### Bài A — Phát hiện first-level cache che dữ liệu

1. Load Order bằng EntityManager.
2. Thay đổi status nhưng chưa flush.
3. Gọi find() lại và quan sát cùng instance.
4. Flush, query bằng JdbcTemplate trong cùng transaction.
5. Clear context rồi đọc lại bằng Hibernate.
6. So sánh ba kết quả.

### Bài B — Đối soát composite foreign key

1. Seed Organizations 7 và 8.
2. Tạo Customer thuộc organization 8.
3. Gọi service tạo Order organization 7 cho Customer đó và xác nhận domain guard.
4. Dùng JDBC INSERT trực tiếp cross-org.
5. Xác nhận PostgreSQL FK từ chối.
6. Chạy SQL LEFT JOIN audit để kiểm tra không có orphan/cross-org rows.

### Bài C — Kiểm tra unique business key

1. Tạo hai Orders cùng order_number ở hai organizations.
2. Xác nhận hợp lệ nếu business key scoped by org.
3. Thử duplicate trong cùng organization bằng JDBC.
4. Xác nhận unique violation.
5. Query GROUP BY/HAVING để kiểm tra duplicate rows.
6. Thử soft-delete/restore theo partial unique policy nếu có.

### Bài D — Trigger và generated values

1. Migration tạo default created_at và audit trigger.
2. Insert qua Hibernate, flush.
3. Query raw row bằng JDBC.
4. Insert qua JDBC bỏ qua created_at.
5. Xác nhận DB default.
6. Update qua native SQL và xác nhận trigger vẫn chạy.
7. Rollback transaction và kiểm tra audit row không tồn tại.

### Bài E — Transaction visibility

1. T1 insert/flush một Order.
2. SQL verifier cùng T1 đọc thấy row.
3. T1 rollback.
4. T2 đọc không thấy row.
5. Thực hiện lại nhưng T1 commit.
6. T2 đọc thấy row.

### Bài F — Multi-query aggregate

1. Seed Order với Items và Shipments.
2. Viết query join cả hai collections và quan sát tổng bị nhân.
3. Viết CTE aggregate mỗi bảng riêng.
4. Đối chiếu totalQuantity/ShipmentCount.
5. So sánh với Java domain calculation bằng fixtures độc lập.

### Bài G — SQLSTATE và schema catalog

1. Query pg_constraint để kiểm tra FK/UNIQUE/CHECK.
2. Query pg_indexes để kiểm tra partial index.
3. Query triggers và RLS metadata.
4. Thử insert vi phạm từng constraint.
5. Kiểm tra SQLSTATE/root cause.
6. Không assert message dài phụ thuộc locale.

### Bài H — RLS và SQL verifier

1. Tạo app_runtime và auditor roles.
2. Bật RLS theo organization.
3. Chạy query bằng app_runtime cho org 7 và org 8.
4. Thử insert/update cross-org.
5. Dùng auditor để đối soát invariant toàn bảng.
6. Xác nhận cache/L1 không bị dùng qua security scopes.

### Bài I — Testcontainers và migration

1. Khởi động PostgreSQL container đúng version.
2. Chạy Flyway/Liquibase từ schema sạch.
3. Hibernate validate mapping.
4. Chạy repository/service test.
5. Chạy SQL độc lập xác nhận dữ liệu và constraint.
6. Chạy upgrade từ migration version cũ.

## 46. Checklist chọn SQL độc lập

1. Điều cần xác minh là domain state, ORM mapping, persisted row hay database constraint?
2. Assertion hiện tại có thể chỉ đọc object đang managed trong L1 không?
3. Đã flush pending changes trước khi query chưa?
4. Test cần xác minh trong cùng transaction, sau commit hay từ transaction khác?
5. Có cần clear/close persistence context không?
6. SQL verifier có dùng JDBC/JdbcTemplate độc lập với entity mapping không?
7. Query được viết từ business invariant hay copy repository SQL?
8. LEFT JOIN có cần thiết để phát hiện orphan rows không?
9. Business key được group theo đúng organization/namespace không?
10. Soft-delete predicate có đúng với unique policy không?
11. Composite FK có được kiểm tra cả bằng catalog và insert vi phạm không?
12. CHECK/NOT NULL có được kiểm tra riêng, bao gồm NULL semantics không?
13. Trigger/default/generated columns có được xác nhận trực tiếp trong DB không?
14. Timestamp/decimal/UUID được so sánh theo precision/type contract không?
15. Bulk/native DML có ảnh hưởng đúng tập IDs không?
16. SQL aggregate có bị nhân rows khi join nhiều collections không?
17. Transaction có bị aborted sau lỗi constraint không?
18. Test rollback có đọc từ transaction mới không?
19. Concurrency test có hai connections/transactions thật không?
20. RLS test có dùng runtime role và auditor role đúng mục đích không?
21. Catalog assertion có kiểm tra constraint validated/index predicate/trigger tồn tại không?
22. Database engine trong test có phải engine production khi cần xác minh vendor semantics không?
23. SQLSTATE assertion có phụ thuộc đúng database version/driver không?
24. Test có vô tình phụ thuộc message, alias, ID sequence hoặc thời gian quá chính xác không?
25. SQL audit toàn bảng có được giới hạn phạm vi/chi phí hợp lý không?

## 47. Tổng kết: kiểm chứng row thực tế bằng một đường đọc độc lập

~~~mermaid
flowchart TD
    A[Thực thi use case qua Hibernate] --> B[Flush theo yêu cầu]
    B --> C{Cần xác minh mức nào?}
    C -->|Object state| D[Assert domain/entity]
    C -->|Persisted values| E[JDBC SELECT độc lập]
    C -->|Relationship integrity| F[SQL JOIN / orphan / cross-scope query]
    C -->|Constraint definition| G[Database catalogs]
    C -->|Constraint enforcement| H[Thử INSERT/UPDATE vi phạm]
    C -->|Commit visibility| I[Transaction đọc mới]
    D --> J[Đối chiếu business invariant]
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
~~~

Những nguyên tắc cần nhớ:

1. **Getter trên entity không chứng minh row đã được ghi.** Entity có thể chỉ nằm trong persistence context.
2. **`flush()` gửi SQL nhưng không commit.** Đọc trong cùng transaction xác nhận state đang ghi; đọc transaction mới xác nhận commit visibility.
3. **`clear()` loại managed instances khỏi L1, còn `refresh()` vẫn đọc theo Hibernate mapping.** JDBC query độc lập hữu ích khi cần xác nhận physical columns/joins/triggers.
4. **SQL verifier phải độc lập về giả định.** Viết từ business invariant, không copy nguyên query implementation đang được test.
5. **LEFT JOIN giúp phát hiện orphan**, GROUP BY/HAVING giúp phát hiện duplicate business keys, và JOIN theo đầy đủ organization keys giúp kiểm tra cross-scope relationships.
6. **Database constraints cần hai kiểu kiểm chứng:** catalog xác nhận constraint đã khai báo; insert/update vi phạm xác nhận engine thực thi nó.
7. **Bulk/native SQL, trigger và database defaults cần được đọc trực tiếp.** Entity state có thể stale hoặc lifecycle callback ORM không chạy.
8. **Transaction rollback, isolation và read replica có thể làm verifier nhìn state khác kỳ vọng.** Chọn đúng connection, transaction và thời điểm đọc.
9. **Aggregate query phải tránh row multiplication.** Join nhiều to-many tables có thể làm tổng bị nhân; aggregate từng child relation riêng khi cần.
10. **SQLSTATE và constraint names có giá trị khi test đúng engine**, nhưng tránh phụ thuộc error message không ổn định.
11. **RLS và tenant scope yêu cầu đúng database role.** Runtime authorization test khác global data audit.
12. **Testcontainers với database production là nơi xác minh vendor-specific behavior**, migration, native SQL, locking và constraints quan trọng.

Đối soát SQL độc lập không phải việc chạy thêm một câu SELECT cho mọi assertion. Hãy dùng nó ở những điểm mà object state hoặc ORM read chưa đủ chứng minh điều cần biết: **database đã lưu gì, quan hệ có hợp lệ không, constraint có thật sự bảo vệ dữ liệu không và transaction khác có nhìn thấy kết quả đã commit không**. Một đường đọc độc lập, được viết từ invariant và chạy trên đúng database, giúp test phát hiện những lỗi mà chính ORM path có thể vô tình che khuất.
