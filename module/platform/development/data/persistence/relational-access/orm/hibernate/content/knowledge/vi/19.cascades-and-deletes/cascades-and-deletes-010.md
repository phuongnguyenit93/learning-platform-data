# Kiểm chứng tác động xóa bằng số hàng và SQL thực tế trong Hibernate

Khi một entity bị xóa trong Hibernate, một lời gọi `remove()` hoặc thao tác xóa collection có thể dẫn tới nhiều SQL khác nhau. Xóa một `PurchaseOrder` có thể xóa các `OrderLine` qua cascade, xóa row trong bảng nối, kích hoạt khóa ngoại `ON DELETE CASCADE` hoặc chỉ cập nhật cờ `deleted` nếu hệ thống dùng soft delete. Vì vậy, nhìn thấy một dòng `DELETE` trong log **chưa đủ để kết luận toàn bộ tác động dữ liệu**.

Muốn kiểm chứng chính xác, cần kết hợp ba loại bằng chứng:

1. **Số lượng bản ghi theo từng bảng trước và sau thao tác** để biết dữ liệu thực sự còn lại.
2. **SQL Hibernate/JDBC đã thực thi** để biết ORM gửi câu lệnh nào, điều kiện nào và tham số nào được bind.
3. **Số hàng bị tác động và trạng thái transaction** để biết câu lệnh ảnh hưởng bao nhiêu hàng, có commit hay rollback, có xung đột optimistic locking hay không.

Bài học hướng dẫn cách kiểm tra xóa entity, cascade, orphan removal, many-to-many, bulk JPQL/native SQL, database cascade và soft delete. Đồng thời, cần phân biệt số entity Hibernate xử lý với số row SQL thực sự bị database thay đổi, vì hai con số này không phải lúc nào cũng giống nhau.

## 1. Trước tiên phải xác định “xóa” đang có nghĩa gì

Trong JPA/Hibernate, có nhiều cơ chế có thể làm dữ liệu biến mất khỏi kết quả truy vấn. Chúng có semantics và SQL khác nhau.

| Cơ chế | Hành vi chính | SQL thường gặp |
| --- | --- | --- |
| `EntityManager.remove(entity)` | Đánh dấu entity managed để xóa theo lifecycle | `DELETE` khi flush |
| `CascadeType.REMOVE` | Truyền thao tác remove sang entity liên quan theo mapping | Nhiều `DELETE` |
| `orphanRemoval = true` | Xóa entity con khi nó bị loại khỏi quan hệ sở hữu | `DELETE` entity con |
| Xóa liên kết many-to-many | Gỡ row trong bảng nối; entity dùng chung vẫn tồn tại | `DELETE` bảng nối |
| Foreign key `ON DELETE CASCADE` | Database tự xóa row con khi row cha bị xóa | Có thể chỉ thấy `DELETE` cha |
| JPQL bulk delete | Xóa hàng loạt trực tiếp qua bulk DML, bỏ qua lifecycle từng entity | Một hoặc nhiều SQL bulk |
| Native SQL delete | Ứng dụng tự gửi SQL tới database | Câu SQL được viết |
| Soft delete | Đánh dấu bản ghi đã xóa nhưng giữ row | Thường là `UPDATE` |

Trước khi đo số hàng, hãy viết rõ kỳ vọng:

- Xóa một đơn hàng có phải xóa tất cả dòng hàng không?
- Xóa một bài viết có phải xóa các tag dùng chung không, hay chỉ xóa liên kết?
- Xóa một task khỏi project có phải xóa task khỏi database không?
- Hệ thống dùng hard delete hay soft delete?
- Database có FK cascade hay Hibernate phát từng câu DELETE?
- Có bảng audit/history cần giữ lại không?

Nếu không xác định đúng semantics, số hàng “đã xóa” sẽ không có tiêu chuẩn để đối chiếu.

## 2. Phân biệt entity bị xóa, liên kết bị xóa và row bị xóa

Xét mô hình đơn hàng:

```text
PurchaseOrder
    id = 100
    |
    +-- OrderLine #1
    +-- OrderLine #2
    +-- OrderLine #3
```

Giả sử các bảng:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
);
```

Nếu xóa `PurchaseOrder#100`, kết quả phụ thuộc mapping và constraint:

- Không có cascade và không xóa child trước: database có thể từ chối vì FK.
- Có `CascadeType.REMOVE`: Hibernate có thể xóa các `OrderLine` rồi mới xóa `PurchaseOrder`.
- Có FK `ON DELETE CASCADE`: database có thể tự xóa row `order_lines` khi parent bị xóa.
- Có soft delete: parent có thể chỉ được đánh dấu, còn child có thể được giữ hoặc xử lý theo policy riêng.

**Không suy ra hành vi chỉ từ tên method trong service.** Hãy đọc mapping, DDL thực tế và SQL đã chạy.

## 3. Lập baseline số hàng trước khi xóa

Cách kiểm chứng trực tiếp nhất là đếm dữ liệu liên quan trước và sau thao tác. Ví dụ, trước khi xóa đơn hàng 100:

```sql
SELECT COUNT(*) AS order_count
FROM purchase_orders
WHERE id = 100;

SELECT COUNT(*) AS line_count
FROM order_lines
WHERE purchase_order_id = 100;
```

Kết quả giả định:

| Bảng | Số hàng trước xóa |
| --- | ---: |
| `purchase_orders` | 1 |
| `order_lines` | 3 |

Sau khi thực hiện thao tác xóa và transaction đã commit, chạy lại:

```sql
SELECT COUNT(*) AS order_count
FROM purchase_orders
WHERE id = 100;

SELECT COUNT(*) AS line_count
FROM order_lines
WHERE purchase_order_id = 100;
```

Nếu hard delete thành công và chính sách yêu cầu xóa cả dòng con, kỳ vọng là:

| Bảng | Số hàng sau commit | Chênh lệch |
| --- | ---: | ---: |
| `purchase_orders` | 0 | -1 |
| `order_lines` | 0 | -3 |

### Vì sao phải đếm theo từng bảng?

Một query chỉ đếm bảng cha có thể trả 0 trong khi các row con vẫn còn nếu mapping/constraint cho phép. Ngược lại, nếu child bị database cascade xóa, một câu DELETE cha có thể làm biến mất nhiều row ở bảng con mà log SQL không hiển thị từng câu DELETE con.

Hãy liệt kê toàn bộ bảng thuộc phạm vi use case:

- Bảng entity cha và entity con.
- Bảng nối many-to-many.
- Bảng `@ElementCollection`.
- Bảng phụ do inheritance mapping hoặc `@SecondaryTable`.
- Bảng audit/history/outbox nếu quy tắc xóa có tác động tới chúng.
- Bảng soft-delete nếu dữ liệu chỉ được đánh dấu.

### Đếm theo khóa cụ thể, không chỉ đếm toàn bảng

Đếm toàn bảng:

```sql
SELECT COUNT(*) FROM order_lines;
```

có thể bị các transaction khác thêm/xóa dòng làm sai lệch kết quả. Với kiểm tra một đơn hàng, hãy lọc theo khóa của aggregate:

```sql
SELECT COUNT(*)
FROM order_lines
WHERE purchase_order_id = :order_id;
```

Nếu dữ liệu có tenant, đưa tenant vào điều kiện theo mô hình:

```sql
SELECT COUNT(*)
FROM order_lines
WHERE tenant_id = :tenant_id
  AND purchase_order_id = :order_id;
```

Điều này giúp kiểm tra đúng phạm vi dữ liệu và tránh trộn các bản ghi cùng local ID giữa tenant.

### Baseline phải được so sánh trong điều kiện nhất quán

Nếu baseline và kết quả sau xóa được lấy ở hai thời điểm khác nhau, transaction khác có thể thay đổi dữ liệu xen giữa. Với kiểm thử integration, dùng fixture riêng và transaction boundaries rõ. Với production, dùng ID/tenant/correlation ID hoặc audit event để liên kết thao tác thay vì dựa vào tổng số row của toàn bảng.

## 4. Xóa entity bằng `EntityManager.remove()`

Ví dụ entity:

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.REMOVE
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }
}
```

Trong transaction:

```java
@Transactional
public void deleteOrder(Long orderId) {
    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        return;
    }

    em.remove(order);
}
```

`remove` yêu cầu JPA chuyển entity managed sang trạng thái removed. SQL thường được thực hiện khi flush hoặc commit, không nhất thiết ngay ở dòng `em.remove(order)`.

### Kiểm tra số hàng trước và sau trong một transaction

```java
@Transactional
public DeleteResult deleteOrderAndCount(Long orderId) {
    long linesBefore = em.createQuery(
        "select count(l) from OrderLine l " +
        "where l.purchaseOrder.id = :id",
        Long.class
    )
    .setParameter("id", orderId)
    .getSingleResult();

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        return new DeleteResult(false, 0, linesBefore);
    }

    em.remove(order);
    em.flush();

    long linesAfter = em.createQuery(
        "select count(l) from OrderLine l " +
        "where l.purchaseOrder.id = :id",
        Long.class
    )
    .setParameter("id", orderId)
    .getSingleResult();

    return new DeleteResult(
        true,
        linesBefore - linesAfter,
        linesAfter
    );
}
```

Ví dụ giả định `DeleteResult` là DTO có constructor tương ứng. Cần lưu ý:

- `flush` gửi SQL pending xuống DB trong transaction hiện tại; **không commit**.
- Query count sau flush quan sát trạng thái trong transaction theo isolation và database.
- Nếu transaction rollback sau khi method trả kết quả, các thay đổi đã flush vẫn có thể bị hủy. DTO tính trước commit chưa phải bằng chứng cuối cùng về dữ liệu đã bền vững.
- Nếu có FK cascade ở database, count query sau flush có thể thấy child đã bị xóa, dù Hibernate không phát từng câu DELETE child.
- Nếu dùng soft delete, count query không có điều kiện active có thể vẫn đếm row; cần kiểm tra cột cờ/xóa theo semantics ứng dụng.

Với kiểm thử xác nhận sau commit, nên mở transaction/context mới hoặc dùng truy vấn độc lập sau khi transaction xóa đã hoàn tất.

## 5. Cascade REMOVE: kiểm chứng số entity con bị xóa

`CascadeType.REMOVE` truyền thao tác remove từ entity cha sang association được cấu hình cascade.

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines = new ArrayList<>();
```

Nếu đơn hàng có ba dòng, Hibernate có thể xóa các entity con rồi xóa entity cha. SQL minh họa:

```sql
DELETE FROM order_lines
WHERE id = ?;

DELETE FROM order_lines
WHERE id = ?;

DELETE FROM order_lines
WHERE id = ?;

DELETE FROM purchase_orders
WHERE id = ?;
```

Đây là một hình dạng có thể gặp khi Hibernate phát delete từng entity; SQL thực tế có thể được batch hoặc khác theo mapping/dialect.

### Cần xác minh cascade được cấu hình ở đúng association

Nếu entity con có:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "purchase_order_id")
private PurchaseOrder purchaseOrder;
```

thì cascade REMOVE thường được đặt ở phía parent quản lý lifecycle con. Không nên đặt cascade REMOVE tùy tiện ở `@ManyToOne` vì xóa một child có thể lan ngược và xóa parent hoặc dữ liệu được chia sẻ.

### Cascade REMOVE không đồng nghĩa database FK cascade

Hai cơ chế độc lập:

- `CascadeType.REMOVE` là lifecycle cascade ở tầng JPA/provider.
- `ON DELETE CASCADE` là hành vi referential action ở database.

Một dự án có thể dùng một trong hai hoặc phối hợp chúng theo mapping/DDL. Khi đo SQL, phải biết cơ chế nào thực sự đang xử lý child rows.

## 6. `orphanRemoval = true`: xóa con khi bị loại khỏi quan hệ

Với quan hệ composition, entity con có thể không tồn tại độc lập khỏi parent. Ví dụ, một `OrderLine` bị xóa khỏi danh sách của đơn hàng cũng phải bị xóa khỏi database.

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Phương thức domain:

```java
public void removeLine(OrderLine line) {
    lines.remove(line);
    line.setPurchaseOrder(null);
}
```

Trong một transaction:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
OrderLine line = findLine(order, lineId);

order.removeLine(line);
em.flush();
```

Hibernate có thể phát DELETE cho entity con bị orphan. Việc xóa khỏi collection **không có nghĩa** entity con chỉ bị detach khỏi Persistence Context; với orphan removal, lifecycle semantics yêu cầu xóa nó.

### Kiểm chứng đúng phạm vi

Trước khi xóa một dòng:

```sql
SELECT COUNT(*)
FROM order_lines
WHERE id = :line_id
  AND purchase_order_id = :order_id;
```

Sau flush/commit:

```sql
SELECT COUNT(*)
FROM order_lines
WHERE id = :line_id;
```

Kỳ vọng hard delete: 1 trước, 0 sau. Đồng thời xác nhận parent vẫn còn:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE id = :order_id;
```

Kỳ vọng: 1. Đây là cách kiểm tra thao tác loại bỏ child không vô tình xóa parent.

### Đừng dùng orphan removal cho entity được chia sẻ

Nếu cùng một entity con được nhiều parent dùng chung, việc một parent bỏ liên kết không nên tự động xóa entity khỏi database. Orphan removal phù hợp khi child thuộc quyền sở hữu vòng đời của parent. Với dữ liệu shared, thường chỉ cần xóa liên kết.

## 7. Many-to-many: xóa liên kết, không nhất thiết xóa entity đích

Giả sử `Article` và `Tag` có quan hệ many-to-many:

```java
@ManyToMany
@JoinTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Một tag có thể được nhiều article dùng chung. Khi xóa một tag khỏi article:

```java
article.removeTag(tag);
```

thông thường tác động mong muốn là xóa row trong bảng nối `article_tags`, không xóa entity `Tag`.

SQL minh họa:

```sql
DELETE FROM article_tags
WHERE article_id = ?
  AND tag_id = ?;
```

Số hàng mong đợi:

| Bảng | Trước | Sau |
| --- | ---: | ---: |
| `articles` | 1 | 1 |
| `tags` | 1 | 1 |
| `article_tags` cho cặp tương ứng | 1 | 0 |

Nếu xóa article hoàn toàn, có thể xóa các row liên kết của article; nhưng tag dùng chung vẫn phải tồn tại nếu còn được article khác tham chiếu.

### Không cascade REMOVE qua entity shared một cách tùy tiện

`CascadeType.REMOVE` trên many-to-many có thể gây xóa entity đích đang được nhiều owner dùng. Thông thường, xóa liên kết là đủ. Chỉ xóa entity đích khi nghiệp vụ thực sự yêu cầu và đã xử lý tất cả tham chiếu.

### Đếm bảng nối riêng

Đếm `tags` không cho biết số quan hệ đã bị xóa. Hãy kiểm tra bảng nối:

```sql
SELECT COUNT(*)
FROM article_tags
WHERE article_id = :article_id;
```

Nếu article có ba tag và chỉ gỡ một tag, số row bảng nối giảm từ 3 xuống 2; số row `tags` vẫn giữ nguyên.

## 8. `@ElementCollection`: xóa row giá trị phụ thuộc owner

`@ElementCollection` lưu các giá trị hoặc embeddable không có entity identity độc lập.

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "user_phone_numbers",
    joinColumns = @JoinColumn(name = "user_id")
)
@Column(name = "phone_number")
private Set<String> phoneNumbers = new HashSet<>();
```

Khi xóa owner, các row trong collection table được xử lý theo mapping/lifecycle của collection. Khi gỡ một số điện thoại khỏi Set, Hibernate xóa row tương ứng.

SQL có thể là:

```sql
DELETE FROM user_phone_numbers
WHERE user_id = ?
  AND phone_number = ?;
```

Kiểm tra:

```sql
SELECT COUNT(*)
FROM user_phone_numbers
WHERE user_id = :user_id;
```

Đừng đếm entity phone number bằng JPA entity count vì giá trị collection không phải entity độc lập. Kiểm tra trực tiếp collection table hoặc truy vấn collection tương ứng.

## 9. Database foreign key `ON DELETE CASCADE`

Database có thể tự động xóa child rows khi parent bị xóa:

```sql
CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
        ON DELETE CASCADE
);
```

Ứng dụng chỉ gửi:

```sql
DELETE FROM purchase_orders
WHERE id = ?;
```

Database tự xử lý các row con theo FK.

### Vì sao SQL log không hiện DELETE cho từng child?

Hibernate SQL logger thường ghi câu lệnh mà Hibernate gửi. Nếu database tự cascade, child DELETE diễn ra bên trong database engine, không phải từng câu SQL JDBC do Hibernate gửi. Vì vậy log có thể chỉ có một câu DELETE parent.

Để xác minh tác động:

1. Kiểm tra DDL/FK thực tế trong database, không chỉ annotation Java.
2. Đếm child rows theo parent trước khi xóa.
3. Thực hiện parent delete và commit.
4. Đếm lại child rows trong context/transaction mới.
5. Nếu cần xác nhận chi tiết, kiểm tra audit/trigger hoặc công cụ quan sát của DBMS.

### JDBC update count có tính child rows do FK cascade không?

Thông thường, số hàng trả về cho câu DELETE parent phản ánh hàng trực tiếp bị tác động bởi câu lệnh, **không nên coi đó là tổng số row bị xóa qua mọi FK cascade**. Chi tiết có thể phụ thuộc DBMS/driver, nhưng không được suy rằng `executeUpdate()` trả 4 chỉ vì parent và ba child bị xóa.

Đây là lý do phải kết hợp row count của câu SQL với truy vấn xác minh từng bảng.

### Hibernate `@OnDelete`

Hibernate có annotation riêng `org.hibernate.annotations.OnDelete` để khai báo ý định dùng hành vi cascade tại database cho association trong những mapping được hỗ trợ:

```java
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@OneToMany(mappedBy = "purchaseOrder")
@OnDelete(action = OnDeleteAction.CASCADE)
private List<OrderLine> lines = new ArrayList<>();
```

Annotation này là **Hibernate-specific**. Nó có thể ảnh hưởng DDL mà Hibernate sinh và cách provider xử lý association; nhưng không tự sửa schema production đã được quản lý bằng migration. Cần xác minh FK thực tế có `ON DELETE CASCADE`. Nếu constraint trong DB không có hành vi đó, chỉ thêm annotation không đủ để database xóa child.

## 10. Bulk JPQL DELETE: số lượng entity và lifecycle khác nhau

JPQL bulk delete tác động trực tiếp lên dữ liệu database:

```java
int affected = em.createQuery(
    "delete from OrderLine l " +
    "where l.purchaseOrder.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
```

`executeUpdate()` trả về số lượng entity bị ảnh hưởng theo semantics bulk operation của JPA. Con số này không nhất thiết là tổng physical rows bị thay đổi bởi trigger, FK cascade hoặc các chi tiết mapping nhiều bảng.

### Bulk delete không tương đương gọi remove từng entity

Bulk DML:

- Không tải từng entity vào Persistence Context để gọi lifecycle remove.
- Không thực thi cascade REMOVE JPA như thao tác `EntityManager.remove(entity)` trên từng instance.
- Không gọi entity lifecycle callbacks theo cách remove từng entity.
- Không tự đồng bộ những entity đã được tải trong L1.
- Có thể bỏ qua business logic nằm trong helper của entity.

Ví dụ, nếu `OrderLine` có `@PreRemove` để ghi logic audit, bulk delete không gọi callback đó cho từng entity như remove lifecycle thông thường.

### Cần xử lý Persistence Context

Giả sử đã tải:

```java
OrderLine line = em.find(OrderLine.class, lineId);
```

Sau đó bulk delete xóa row tương ứng. Object `line` vẫn có thể nằm trong L1 và không tự chuyển sang trạng thái đồng bộ với database.

Một mẫu có chủ ý:

```java
em.flush(); // Gửi thay đổi pending trước bulk DML.
int deleted = em.createQuery(
        "delete from OrderLine l " +
        "where l.purchaseOrder.id = :orderId")
    .setParameter("orderId", orderId)
    .executeUpdate();

em.clear(); // Loại managed state có thể stale.
```

`clear` tác động toàn bộ Persistence Context hiện tại. Nếu caller còn entity managed cần sử dụng, phải tính tới việc chúng sẽ trở thành detached. Một lựa chọn khác là kết thúc unit of work hoặc refresh các entity cụ thể nếu thích hợp.

### Bulk delete có thể vướng FK

Nếu `OrderLine` có entity con khác tham chiếu tới nó, câu bulk delete có thể bị database từ chối vì FK. Bulk DML không tự đi qua đồ thị cascade entity. Cần xóa theo thứ tự phù hợp, dùng database cascade nếu được thiết kế hoặc chọn remove lifecycle theo đúng yêu cầu.

## 11. Spring Data JPA `@Modifying` và số hàng trả về

Spring Data JPA có thể khai báo modifying query:

```java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query(
        "delete from OrderLine l " +
        "where l.purchaseOrder.id = :orderId"
    )
    int deleteAllByOrderId(@Param("orderId") Long orderId);
}
```

`executeUpdate()` được phản ánh thành số lượng entity bị ảnh hưởng theo bulk query semantics. Các tùy chọn:

- `flushAutomatically = true`: flush Persistence Context trước khi chạy modifying query.
- `clearAutomatically = true`: clear Persistence Context sau query để giảm nguy cơ dùng entity stale.

Cần một transaction phù hợp, thường đặt `@Transactional` ở application service hoặc cấu hình trên method repository theo policy. `clearAutomatically` có thể detach mọi entity đang managed trong context, không chỉ các OrderLine bị xóa.

Nếu method trả 3, điều đó thường có nghĩa bulk query ảnh hưởng ba entity `OrderLine` theo provider/JPA semantics. Không suy ra rằng:

- Database chỉ chạy đúng một physical SQL trên mọi mapping.
- Không có trigger xóa thêm row.
- Không có row nào khác bị cascade.
- Persistence Context ở các request khác đã được cập nhật.
- Transaction đã commit thành công chỉ vì query trả số 3.

Commit vẫn có thể thất bại sau khi method repository trả về.

## 12. Native SQL DELETE và JDBC update count

Khi dùng native SQL hoặc JDBC thuần, ứng dụng chịu trách nhiệm về câu lệnh và ý nghĩa tham số.

Ví dụ:

```java
int affected = em.createNativeQuery(
    "DELETE FROM order_lines WHERE purchase_order_id = :id"
)
.setParameter("id", orderId)
.executeUpdate();
```

Ở JDBC thuần:

```java
String sql =
    "DELETE FROM order_lines WHERE purchase_order_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, orderId);
    int affectedRows = statement.executeUpdate();

    System.out.println("Rows affected: " + affectedRows);
}
```

`executeUpdate()` trả về số row bị ảnh hưởng theo JDBC driver/database cho statement đó. Cần hiểu giới hạn:

- Đây là số row của statement, không phải số entity Java đã từng được load.
- FK cascade và trigger có thể tác động thêm row mà update count không phản ánh như tổng mọi bảng.
- Semantics có thể là row matched hoặc changed tùy loại statement, DBMS và driver.
- Với batch, kết quả từ `executeBatch()` có thể chứa `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED`, không phải lúc nào cũng là số nguyên chính xác cho từng lệnh.
- Native SQL không tự áp dụng cascade REMOVE/orphanRemoval của JPA.
- Entity đã managed trong L1 có thể stale sau khi SQL trực tiếp chạy.

### Không tự suy diễn `affectedRows == 0` là một lỗi duy nhất

`affectedRows == 0` có thể có nhiều nghĩa:

- ID không tồn tại.
- Điều kiện WHERE không khớp.
- Entity đã bị xóa bởi transaction khác.
- Optimistic version predicate không còn đúng.
- Driver báo số row changed thay vì matched.
- Câu SQL chỉ update khi giá trị khác.

Phải xem predicate, version, DBMS và mục tiêu câu lệnh trước khi diễn giải.

## 13. Optimistic locking và số hàng DELETE bằng 0

Entity có `@Version` có thể được xóa bằng câu SQL kèm version cũ:

```sql
DELETE FROM products
WHERE id = ?
  AND version = ?;
```

Nếu một transaction khác đã cập nhật version, predicate không còn khớp và database xóa 0 row. Hibernate dùng row count để nhận biết stale state/optimistic locking conflict theo cơ chế provider.

Ví dụ entity:

```java
@Entity
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;
}
```

Kịch bản:

```text
Transaction A đọc Product#10, version=4
Transaction B đọc Product#10, version=4
Transaction B cập nhật và commit, version=5
Transaction A xóa theo id=10 AND version=4
Database: 0 row bị xóa
Hibernate: phát hiện stale/optimistic locking conflict
```

Vì vậy, DELETE ảnh hưởng 0 row không phải lúc nào cũng là “không có dữ liệu cần xóa”; nó có thể là dấu hiệu transaction đang thao tác trên snapshot cũ.

Không bắt exception rồi tiếp tục sử dụng cùng Persistence Context như chưa có lỗi. Hãy rollback unit of work và nếu use case có thể retry, tải lại state trong transaction mới.

## 14. SQL log của Hibernate: xem câu lệnh thật

Để hiểu Hibernate thực sự gửi SQL gì, có thể bật logging trong môi trường development.

### Hibernate 6 với Spring Boot

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`org.hibernate.SQL` hiển thị SQL được sinh. Logger `org.hibernate.orm.jdbc.bind` của Hibernate 6 hiển thị tham số JDBC được bind.

### Hibernate 5

Logger bind thường dùng khác Hibernate 6, ví dụ:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
```

Tên logger cụ thể phụ thuộc phiên bản. Hãy đối chiếu cấu hình logging của Hibernate đang dùng, không sao chép tên logger của phiên bản khác rồi kết luận logging bind bị lỗi.

### SQL minh họa

Khi xóa một đơn hàng với cascade entity, log có thể gần giống:

```sql
delete from order_lines
where id = ?;

delete from purchase_orders
where id = ?;
```

Bind parameters có thể cho thấy các ID được dùng. Nếu Hibernate batching, log có thể thể hiện lệnh chuẩn bị và tham số theo batch; nếu DB cascade, không nhất thiết thấy child DELETE.

### SQL log cho biết gì và không cho biết gì?

| Có thể quan sát | Không thể kết luận chỉ từ SQL log |
| --- | --- |
| Bảng nào được nhắc trong statement | Tổng row bị FK cascade xóa |
| Điều kiện WHERE | Transaction cuối cùng đã commit |
| Placeholder và tham số bind nếu bật logger | Mọi trigger đã thực thi |
| Thứ tự statement Hibernate gửi | Toàn bộ side effect ở DB |
| Có UPDATE soft delete hay DELETE hard delete | Dữ liệu có bị xóa ở cache ngoài ORM |
| Câu lệnh bulk hay delete từng entity | Mọi managed entity ở session khác đã cập nhật |

**Cẩn thận với bind logging:** tham số có thể chứa email, địa chỉ, ID khách hàng, thông tin thanh toán hoặc dữ liệu nhạy cảm. Chỉ bật TRACE trong môi trường được kiểm soát và tắt sau khi chẩn đoán.

## 15. Dùng Hibernate Statistics để đo hoạt động ORM

Hibernate có cơ chế Statistics để quan sát số hoạt động ORM ở cấp SessionFactory. Có thể bật:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Hoặc cấu hình tương ứng trong persistence unit/Hibernate properties.

Lấy statistics từ `SessionFactory`:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();

statistics.clear();

// Thực hiện use case xóa ở đây.

System.out.println(
    "Entity delete count = " +
    statistics.getEntityDeleteCount()
);

System.out.println(
    "Collection remove count = " +
    statistics.getCollectionRemoveCount()
);

System.out.println(
    "Prepared statement count = " +
    statistics.getPrepareStatementCount()
);
```

Các chỉ số hữu ích tùy phiên bản Hibernate gồm:

- `getEntityDeleteCount()`: số thao tác xóa entity mà Hibernate ghi nhận trong statistics.
- `getCollectionRemoveCount()`: số thao tác remove collection được ghi nhận.
- `getPrepareStatementCount()`: số prepared statements được chuẩn bị.
- `getEntityInsertCount()`/`getEntityUpdateCount()`: hữu ích để phát hiện thao tác ngoài dự kiến.
- Thống kê query/cache nếu được bật và provider hỗ trợ.

### Statistics không phải báo cáo row count vật lý

Một entity có thể ánh xạ nhiều bảng; một câu SQL có thể tác động nhiều row; database cascade có thể xóa child rows mà Hibernate không phát lệnh xóa riêng; trigger có thể thay đổi bảng khác. Bulk DML cũng có semantics riêng.

Do đó, `entityDeleteCount` **không đồng nghĩa tổng số row database bị xóa**. Dùng Statistics để quan sát hành vi ORM, và dùng SQL/JDBC/DB query để kiểm tra row count thật.

Statistics thường được chia sẻ ở phạm vi SessionFactory và có thể bao gồm hoạt động từ nhiều request/transaction đồng thời. Gọi `statistics.clear()` trong ứng dụng đang phục vụ traffic có thể xóa số liệu của luồng khác. Trong production, không dùng reset statistics toàn cục để đo riêng một request nếu không có kiểm soát. Trong integration test chạy tuần tự ở môi trường riêng, việc clear trước/sau test có thể hữu ích.

## 16. `StatementInspector`: quan sát SQL trước khi thực thi

Hibernate cung cấp `org.hibernate.resource.jdbc.spi.StatementInspector` để kiểm tra hoặc biến đổi SQL statement trước khi JDBC thực thi, tùy cấu hình.

Ví dụ chỉ quan sát:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class LoggingStatementInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        System.out.println("Hibernate SQL: " + sql);
        return sql; // Trả nguyên câu lệnh, không thay đổi.
    }
}
```

Có thể cấu hình qua property tương ứng:

```properties
hibernate.session_factory.statement_inspector=com.example.LoggingStatementInspector
```

`StatementInspector` hữu ích để thu thập câu SQL Hibernate chuẩn bị, phân loại DELETE/UPDATE/SELECT và kiểm tra có câu SQL nào bất ngờ nhắm tới bảng khác không.

Nhưng inspector nhận **chuỗi SQL**, không phải JDBC update count sau khi statement thực thi. Nó không tự cho biết có bao nhiêu row bị xóa. Muốn đo affected rows, cần quan sát ở tầng JDBC/driver hoặc truy vấn database sau thao tác.

Không chỉnh sửa SQL trong inspector chỉ để log. Việc thay statement có thể làm thay đổi semantics, parameter positions, caching hoặc tính đúng đắn ORM.

## 17. Quan sát JDBC update count bằng proxy

Nếu cần biết số row của từng statement, có thể dùng JDBC/DataSource proxy để quan sát lời gọi `executeUpdate`, `executeLargeUpdate` hoặc `executeBatch` và kết quả trả về. Các thư viện như datasource-proxy hoặc P6Spy có thể hỗ trợ logging/metrics tùy cấu hình.

Instrumentation có thể ghi lại:

```text
SQL statement
Bind parameters (được che dữ liệu nhạy cảm)
Execution time
Update count / batch result nếu driver cung cấp
Transaction/correlation context
```

Một bản ghi log minh họa:

```text
statement = DELETE FROM order_lines WHERE id = ?
parameter = [masked-or-safe-id]
updateCount = 1
durationMs = 3
transactionId = ...
```

Khi dùng proxy, bảo đảm nó không thay đổi transaction semantics, không log plaintext nhạy cảm và không tạo overhead quá lớn.

### Batch result có thể không phải con số chính xác

JDBC `executeBatch()` trả mảng kết quả. Giá trị có thể là:

- Số hàng bị ảnh hưởng.
- `Statement.SUCCESS_NO_INFO`: lệnh thành công nhưng không có số hàng chính xác.
- `Statement.EXECUTE_FAILED`: lệnh thất bại trong batch nếu driver tiếp tục thực thi.

Vì vậy, nếu Hibernate batching DELETE, một log chỉ có tổng số statement hoặc số batch không nhất thiết đủ để khẳng định từng entity row đã bị xóa bao nhiêu.

JDBC update count thường mô tả statement trực tiếp. FK cascade, trigger, stored procedure và thao tác phát sinh bên trong database có thể không được cộng vào con số đó theo cách mong muốn. Truy vấn lại các bảng liên quan là bước xác minh cần thiết.

## 18. Kiểm chứng hard delete và soft delete

### Hard delete

Hard delete loại bỏ row vật lý:

```sql
DELETE FROM products
WHERE id = 10;
```

Sau commit, truy vấn theo ID không còn trả row:

```sql
SELECT COUNT(*)
FROM products
WHERE id = 10;
```

Kỳ vọng: 0.

### Soft delete

Soft delete giữ row nhưng đánh dấu trạng thái:

```sql
UPDATE products
SET deleted = TRUE
WHERE id = 10;
```

Sau commit:

```sql
SELECT COUNT(*)
FROM products
WHERE id = 10;
```

Kết quả vẫn là 1. Query active:

```sql
SELECT COUNT(*)
FROM products
WHERE id = 10
  AND deleted = FALSE;
```

Kết quả là 0.

Do đó, câu hỏi “xóa được bao nhiêu row?” phải phân biệt số row bị xóa vật lý, số row được đánh dấu deleted, số row active giảm và số row audit/history vẫn được giữ.

### Hibernate soft delete mapping

Hibernate hỗ trợ nhiều cách triển khai soft delete tùy phiên bản, ví dụ custom SQL qua `@SQLDelete` kết hợp restriction/filter, hoặc annotation `@SoftDelete` trong các phiên bản mới hỗ trợ.

Ví dụ khái niệm custom delete SQL:

```java
@SQLDelete(
    sql = "UPDATE products SET deleted = true WHERE id = ?"
)
@Entity
@Table(name = "products")
public class Product {
    // ...
}
```

Đây là minh họa Hibernate-specific; SQL phải khớp schema và mapping thực tế, đặc biệt nếu entity dùng `@Version` vì delete SQL có thể cần version predicate. Cơ chế lọc bản ghi deleted khi đọc phải được cấu hình riêng; chỉ thay DELETE thành UPDATE không tự ẩn row khỏi mọi truy vấn.

Khi đo soft delete, hãy tìm **UPDATE** trong SQL log và đếm cột cờ, không chờ thấy DELETE.

## 19. Kiểm tra trigger, audit và FK cascade ở database

Một câu DELETE có thể kích hoạt thêm hành động database:

- Trigger ghi lịch sử.
- Trigger xóa dữ liệu phụ.
- FK cascade xóa child.
- FK set null cập nhật khóa ngoại.
- Stored procedure thực hiện nhiều statement.
- Rule hoặc cơ chế DBMS riêng.

Ví dụ, trigger audit có thể chèn một row:

```sql
INSERT INTO product_delete_audit(product_id, deleted_at)
VALUES (OLD.id, CURRENT_TIMESTAMP);
```

Sau khi xóa một product, số row trong `products` giảm 1 nhưng số row trong `product_delete_audit` tăng 1. Đây là tác động có chủ đích, không phải lỗi đếm.

Hibernate log câu statement gửi xuống DB; trigger chạy bên trong database engine. Nếu cần biết trigger đã chạy, xem định nghĩa trigger, audit table hoặc công cụ theo dõi của DBMS.

Để xác minh kết quả, hãy đảm bảo transaction xóa đã commit; mở transaction/connection đọc mới theo routing phù hợp; truy vấn các bảng cha, con, bảng nối và audit. Nếu đọc replica, kiểm tra replication lag. Một truy vấn trong chính transaction xóa trước commit không chứng minh dữ liệu đã bền vững sau commit.

## 20. Thứ tự SQL và khóa ngoại

Khi xóa parent có child FK mà không có cascade, database yêu cầu xử lý đúng thứ tự:

```sql
DELETE FROM order_lines
WHERE purchase_order_id = 100;

DELETE FROM purchase_orders
WHERE id = 100;
```

Nếu xóa parent trước, database có thể trả lỗi foreign key constraint vì child còn tham chiếu.

Hibernate thường sắp xếp các action trong flush theo dependency và mapping, nhưng không nên phụ thuộc vào một thứ tự SQL cụ thể khi không cần. Nếu có nhiều association, vòng tham chiếu hoặc constraint deferred, hãy kiểm tra SQL thực tế và DDL.

Ví dụ một use case có ba child rows bị xóa, một parent row bị xóa, ba join rows bị xóa và một audit row được tạo. Báo cáo nên ghi theo bảng và loại thao tác, không chỉ một tổng duy nhất.

## 21. Kiểm thử integration: xác nhận cả dữ liệu và SQL

Một kiểm thử tốt cho delete cần xác minh:

1. Trạng thái dữ liệu trước thao tác.
2. Thao tác xóa được gọi trong transaction đúng.
3. Kết quả sau commit từ một context mới.
4. Số row ở các bảng liên quan.
5. SQL/log nếu test cần xác nhận chiến lược ORM cụ thể.
6. Trường hợp lỗi/rollback nếu use case yêu cầu.

### Ví dụ kiểm thử bằng JPA

```java
@Test
void deletingOrderRemovesItsLines() {
    Long orderId = createOrderWithThreeLines();

    long before = countLines(orderId);
    assertEquals(3L, before);

    deleteOrderInTransaction(orderId);

    // Đọc trong context/transaction mới.
    assertEquals(0L, countOrder(orderId));
    assertEquals(0L, countLines(orderId));
}
```

Đây là pseudo-test minh họa; helper `createOrderWithThreeLines`, `deleteOrderInTransaction` và count methods phải thực sự mở/commit các transaction tương ứng. Không dùng cùng một managed instance để kết luận dữ liệu DB đã bị xóa.

Nếu mục tiêu là xác minh Hibernate phát delete từng child hay dựa vào database cascade, có thể kết hợp SQL logger hoặc StatementInspector, Hibernate Statistics, JDBC proxy và truy vấn SQL sau commit.

Không nên khóa test vào đúng số câu SQL nếu batching, dialect hoặc Hibernate version có thể thay đổi mà semantics dữ liệu vẫn đúng. Chỉ assert SQL shape khi đó thực sự là yêu cầu kiến trúc/performance của hệ thống.

### Kiểm tra rollback

Ví dụ một thao tác xóa child rồi gặp lỗi trước commit. Nếu transaction rollback, row phải còn:

```text
Before: order_lines = 3
Delete operation + later failure
Rollback
After in new transaction: order_lines = 3
```

Đây là phép kiểm chứng atomicity. SQL DELETE có thể đã xuất hiện trong log trước rollback; điều đó **không có nghĩa dữ liệu đã bị xóa bền vững**.

## 22. Đếm số hàng qua JPA query

JPQL count query:

```java
long count = em.createQuery(
    "select count(l) from OrderLine l " +
    "where l.purchaseOrder.id = :orderId",
    Long.class
)
.setParameter("orderId", orderId)
.getSingleResult();
```

Nếu dùng Spring Data repository:

```java
long countByPurchaseOrderId(Long orderId);
```

Cần chú ý:

- `count(entity)` đếm entity theo query semantics, không phải mọi physical row trong tất cả bảng mapping.
- Nếu entity dùng inheritance strategy nhiều bảng, một entity có thể tương ứng nhiều physical rows.
- Nếu query có join làm nhân dòng, dùng `count(distinct ...)` khi mục tiêu là đếm entity duy nhất.
- Nếu soft delete/filter được áp dụng, query có thể chỉ đếm active entities.
- Nếu tenant filter được bật, count có thể chỉ thuộc tenant hiện tại.
- Nếu cần kiểm tra physical rows, SQL trực tiếp vào từng bảng là bằng chứng rõ hơn.

Ví dụ join có thể nhân kết quả:

```sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN order_lines l ON l.purchase_order_id = o.id;
```

Sử dụng count đúng mục tiêu, tránh nhầm số dòng kết quả join với số entity hoặc số row bảng gốc.

## 23. Bulk delete trong Spring Data: flush và clear là một phần của kiểm chứng

Ví dụ repository:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("delete from OrderLine l where l.purchaseOrder.id = :orderId")
int deleteLines(@Param("orderId") Long orderId);
```

Service:

```java
@Transactional
public int removeLines(Long orderId) {
    long before = repository.countByPurchaseOrderId(orderId);

    int affected = repository.deleteLines(orderId);

    long after = repository.countByPurchaseOrderId(orderId);

    return affected;
}
```

Trong ví dụ này, `clearAutomatically` có thể khiến entity khác đang managed trong cùng Persistence Context cũng bị detach. Ngoài ra, query count sau bulk delete vẫn chịu transaction isolation và query semantics. Nếu cần dùng các entity khác sau thao tác, hãy xem xét thiết kế service/transaction hoặc tránh clear toàn bộ context.

Không trả `before - after` như một “số row SQL chính xác” nếu query filter, concurrent writers hoặc DB cascade làm thay đổi phạm vi. Hãy nêu rõ đó là **chênh lệch entity được đếm theo JPQL**.

## 24. Batching DELETE và cách đọc số liệu

Hibernate có thể gom nhiều câu DELETE vào JDBC batch nếu cấu hình batching và mapping cho phép. Khi đó:

- SQL logger có thể cho thấy statement được chuẩn bị và bind nhiều bộ tham số.
- JDBC driver trả kết quả batch.
- Một số driver trả số hàng cụ thể, số khác có thể trả `SUCCESS_NO_INFO`.
- Một lần flush có thể gửi nhiều batch.
- Thứ tự batch chịu ảnh hưởng dependency giữa entity và FK.

Ví dụ cấu hình Hibernate:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_updates=true
hibernate.order_inserts=true
```

Các property này minh họa cấu hình batching/sắp xếp DML; khả năng batch DELETE cụ thể còn phụ thuộc Hibernate version, identifier strategy, driver và mapping. `order_updates` không phải lời bảo đảm mọi DELETE sẽ được sắp xếp theo ý muốn.

### Vì sao số statement khác số row?

Một batch có 50 executions có thể xóa 50 rows, nhưng cũng có thể có execution ảnh hưởng 0 hoặc nhiều row tùy câu lệnh. Ngược lại, một DELETE theo điều kiện có thể xóa hàng trăm row chỉ với một statement.

Phân biệt:

- Số SQL statement được gửi.
- Số execution trong batch.
- Số row được báo cáo bởi driver.
- Số entity lifecycle delete Hibernate ghi nhận.
- Số physical rows thực tế còn lại sau commit.

## 25. Các trường hợp mapping đặc biệt

### Inheritance

Với `InheritanceType.JOINED`, một entity subclass có thể có dữ liệu trong bảng base và bảng subclass. Xóa một entity có thể cần xóa nhiều physical rows. Đếm entity bằng JPQL không nhất thiết bằng tổng số row SQL.

### Secondary table

Entity dùng `@SecondaryTable` có thể có dữ liệu ở nhiều bảng. Xóa một entity có thể tác động tới row của bảng chính và bảng phụ. Hãy đếm cả hai.

### Collection table

`@ElementCollection` lưu giá trị trong bảng riêng. Xóa owner hoặc clear collection có thể xóa các row đó. Kiểm tra collection table trực tiếp.

### Many-to-many join table

Xóa một association xóa row bảng nối; entity ở hai đầu có thể vẫn tồn tại. Đừng cộng số join rows thành số entity đã xóa.

### Soft delete

SQL có thể là UPDATE; row vật lý vẫn còn. Đếm active/deleted theo cột trạng thái.

### Database trigger và FK action

Các thay đổi phát sinh bên trong DB có thể không được hiển thị như statement JDBC riêng. Truy vấn bảng liên quan/audit để xác minh.

## 26. Những lỗi thường gặp khi kiểm chứng tác động xóa

### Lỗi 1: chỉ xem log có DELETE hay không

Có DELETE trong log không chứng minh transaction đã commit; không thấy child DELETE cũng không chứng minh child còn tồn tại nếu database cascade xử lý.

**Cách sửa:** kiểm tra SQL, trạng thái commit và số row sau commit ở từng bảng.

### Lỗi 2: chỉ đếm bảng cha

Parent count về 0 nhưng child/join/collection rows có thể còn hoặc đã được cascade theo cách không nhìn thấy.

**Cách sửa:** lập danh sách tất cả bảng liên quan và đếm theo foreign key/owner ID.

### Lỗi 3: nhầm cascade REMOVE với FK ON DELETE CASCADE

Một cơ chế do JPA/provider điều phối, một cơ chế do database thực thi.

**Cách sửa:** kiểm tra cả annotation/mapping và DDL FK thật.

### Lỗi 4: dùng bulk JPQL rồi mong callback chạy

Bulk DML không gọi lifecycle remove cho từng entity như `EntityManager.remove`.

**Cách sửa:** nếu cần callback/cascade, dùng entity lifecycle hoặc triển khai bulk side effects tường minh.

### Lỗi 5: quên Persistence Context sau bulk delete

Entity đã tải trong L1 có thể vẫn giữ state cũ.

**Cách sửa:** flush trước, clear/refresh hoặc kết thúc context theo phạm vi phù hợp.

### Lỗi 6: coi `executeUpdate()` là tổng row của mọi bảng

JDBC update count và JPQL affected entity count không bao gồm chắc chắn mọi FK cascade/trigger.

**Cách sửa:** xác minh từng bảng bằng query hoặc audit.

### Lỗi 7: cho rằng DELETE log nghĩa là dữ liệu đã bị xóa vĩnh viễn

Transaction có thể rollback sau khi DELETE đã chạy.

**Cách sửa:** xác nhận commit và truy vấn trong transaction mới.

### Lỗi 8: kiểm tra trước/sau trong cùng Persistence Context rồi tin cache

L1, query cache hoặc filter có thể ảnh hưởng kết quả; object managed có thể stale.

**Cách sửa:** dùng truy vấn physical SQL hoặc EntityManager mới sau commit khi cần xác minh DB.

### Lỗi 9: đếm toàn bảng trong môi trường có traffic

Transaction khác có thể thêm/xóa dữ liệu trong lúc đo.

**Cách sửa:** lọc theo ID/tenant/business key và dùng fixture hoặc snapshot nhất quán.

### Lỗi 10: nhầm xóa liên kết với xóa entity

Gỡ tag khỏi article chỉ xóa row bảng nối; tag vẫn tồn tại.

**Cách sửa:** đếm riêng bảng nối và bảng entity đích.

### Lỗi 11: soft delete nhưng truy vấn chỉ đếm row vật lý

Row vẫn còn nên count không giảm.

**Cách sửa:** đếm active/deleted theo cờ hoặc timestamp và xác nhận SQL là UPDATE.

### Lỗi 12: bỏ qua FK constraint khi bulk delete

Bulk DML không đi qua cascade entity, có thể bị FK từ chối.

**Cách sửa:** xử lý child trước, dùng FK cascade đã cấu hình hoặc chọn entity lifecycle đúng.

### Lỗi 13: dùng Hibernate Statistics làm số row chính xác

Statistics phản ánh sự kiện/hoạt động ORM, không phải tổng physical row của DB.

**Cách sửa:** kết hợp Statistics với JDBC row counts và DB queries.

### Lỗi 14: log bind parameter nhạy cảm

TRACE có thể làm lộ dữ liệu cá nhân hoặc token.

**Cách sửa:** mask/ẩn parameter, chỉ bật log trong môi trường an toàn và tắt sau chẩn đoán.

### Lỗi 15: nghĩ row count 0 chỉ có nghĩa không tồn tại

DELETE với `WHERE id=? AND version=?` có thể ảnh hưởng 0 row vì version đã đổi.

**Cách sửa:** phân loại stale state/conflict thay vì luôn báo “không tồn tại”.

### Lỗi 16: giả định batch luôn trả số row cụ thể

Driver có thể trả `SUCCESS_NO_INFO` hoặc kết quả batch khác.

**Cách sửa:** diễn giải batch count theo JDBC driver; dùng kiểm tra dữ liệu sau commit làm bằng chứng cuối.

## 27. Quy trình kiểm chứng một thao tác xóa từ đầu đến cuối

Có thể áp dụng quy trình sau trong development hoặc integration test:

**Bước 1 — Viết rõ kỳ vọng nghiệp vụ**

Ví dụ: xóa một PurchaseOrder phải xóa 1 parent, 3 OrderLine, 3 association rows; giữ nguyên các Product/Tag được chia sẻ.

**Bước 2 — Xác định mapping và DDL**

Kiểm tra `CascadeType.REMOVE`, `orphanRemoval`, owning side, join table, FK, `ON DELETE CASCADE` và soft-delete policy.

**Bước 3 — Lấy baseline**

Đếm theo ID/tenant ở từng bảng có liên quan, lưu kết quả.

**Bước 4 — Thực hiện trong transaction đúng**

Gọi API JPA/Hibernate hoặc bulk/native SQL đúng với mục tiêu. Ghi correlation ID nếu cần liên kết log.

**Bước 5 — Quan sát SQL**

Bật SQL logging/StatementInspector hoặc JDBC proxy trong môi trường kiểm thử. Xem câu lệnh, predicate, tham số đã che dữ liệu nhạy cảm và batch behavior.

**Bước 6 — Quan sát row/entity count**

Dùng Hibernate Statistics để biết ORM ghi nhận bao nhiêu entity/collection operation; dùng JDBC update count khi cần số row statement; không đánh đồng hai loại.

**Bước 7 — Xác nhận transaction**

Đảm bảo commit thành công. Nếu rollback, dữ liệu có thể vẫn còn dù SQL DELETE đã xuất hiện trong log.

**Bước 8 — Đọc lại từ DB**

Trong transaction/context mới, đếm từng bảng và kiểm tra row cha, con, bảng nối, collection table, audit/soft-delete.

**Bước 9 — So sánh với kỳ vọng**

Ghi rõ chênh lệch theo bảng và giải thích row phát sinh do trigger/FK/soft delete nếu có.

**Bước 10 — Kiểm tra lỗi và concurrency**

Thử rollback, FK violation, optimistic conflict và hai thao tác xóa đồng thời khi đó là rủi ro của use case.

## 28. Ví dụ báo cáo kết quả kiểm chứng

Một báo cáo kỹ thuật nên tách từng loại số liệu:

```text
Use case: delete PurchaseOrder#100
Transaction: committed
Deletion policy: hard delete
ORM mapping: cascade REMOVE from PurchaseOrder to OrderLine

Database row counts:
    purchase_orders: 1 -> 0 (deleted 1)
    order_lines:     3 -> 0 (deleted 3)
    order_tags:      2 -> 0 (deleted 2)
    products:        2 -> 2 (unchanged)
    tags:            2 -> 2 (unchanged)
    delete_audit:    0 -> 1 (inserted 1)

Observed SQL:
    DELETE order_lines ... (batched)
    DELETE order_tags ...
    DELETE purchase_orders ...
    INSERT delete_audit ...

Hibernate statistics:
    entityDeleteCount: ...
    collectionRemoveCount: ...
    prepareStatementCount: ...

Conclusion:
    Parent, child and join rows were removed as intended.
    Shared Product/Tag entities remain.
    Audit row was created.
```

Các dấu ba chấm là chỗ điền số đo thực tế. Không tạo số giả để báo cáo. Nếu database FK cascade thực hiện child deletion, phần Observed SQL phải ghi rõ chỉ thấy parent DELETE trong JDBC log và child count được xác minh bằng truy vấn sau commit.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao một câu DELETE trong SQL log chưa chứng minh toàn bộ entity graph đã bị xóa?**

Vì child có thể còn, được xóa bởi FK cascade, bị giữ lại theo mapping hoặc transaction có thể rollback. Cần kiểm tra từng bảng và commit outcome.

**2. `CascadeType.REMOVE` khác `ON DELETE CASCADE` thế nào?**

Cascade REMOVE là lifecycle propagation ở tầng JPA/Hibernate; ON DELETE CASCADE là referential action ở database.

**3. `orphanRemoval = true` có tác động gì khi xóa child khỏi collection?**

Child bị orphan có thể được xóa khỏi database theo lifecycle semantics, thay vì chỉ bị gỡ khỏi collection trong bộ nhớ.

**4. Gỡ một Tag khỏi Article many-to-many có cần xóa Tag entity không?**

Thông thường không. Nó chỉ xóa row association trong bảng nối; Tag có thể được các Article khác dùng.

**5. `executeUpdate()` của bulk JPQL trả về điều gì?**

Số entity bị ảnh hưởng theo semantics bulk operation của JPA/provider, không phải tổng mọi physical rows do trigger/FK cascade.

**6. Bulk JPQL DELETE có gọi `@PreRemove` cho từng entity không?**

Không theo lifecycle remove từng entity. Bulk DML bỏ qua callback/cascade entity thông thường.

**7. Vì sao cần clear/refresh sau native hoặc bulk delete?**

Entity đã tải trong Persistence Context có thể vẫn giữ state cũ sau khi database bị thay đổi trực tiếp.

**8. `em.flush()` có đồng nghĩa transaction đã commit không?**

Không. Flush gửi SQL pending trong transaction; rollback vẫn có thể hủy các thay đổi đó.

**9. JDBC update count có chắc bao gồm child rows do FK cascade không?**

Không nên giả định vậy. Update count thường mô tả statement trực tiếp; hãy truy vấn từng bảng để xác minh.

**10. Hibernate Statistics có phải tổng số physical rows bị xóa không?**

Không. Nó phản ánh hoạt động ORM, ví dụ entity delete/collection remove, không phải mọi row thay đổi ở database.

**11. Nếu DELETE có `WHERE id=? AND version=?` trả 0 row thì có thể là gì?**

Có thể entity không tồn tại hoặc version đã đổi, gây optimistic locking conflict/stale state.

**12. Soft delete có làm row count vật lý giảm không?**

Không nhất thiết. Soft delete thường UPDATE cờ hoặc timestamp; row vẫn tồn tại nhưng không còn active.

**13. Vì sao phải đọc lại trong transaction/context mới sau commit?**

Để tránh dựa vào managed state/cache của Persistence Context cũ và xác minh dữ liệu đã được commit thực sự.

**14. `StatementInspector` có cho biết số row bị xóa không?**

Không. Nó quan sát/kiểm tra SQL trước khi thực thi; cần JDBC instrumentation hoặc truy vấn DB để biết affected rows.

**15. Vì sao số statement không bằng số row?**

Một statement có thể xóa nhiều row, nhiều statement có thể xóa một row mỗi lần, và batching/trigger/FK cascade làm số liệu khác nhau.

## 30. Ghi nhớ

- **Xác định semantics xóa trước khi đo:** entity delete, cascade, orphan removal, unlink, database cascade, bulk delete và soft delete là các hành vi khác nhau.
- **Đếm theo từng bảng và theo khóa cụ thể:** parent count không đại diện child, join table hoặc collection table.
- **SQL log cho biết câu lệnh Hibernate gửi**, không chứng minh transaction đã commit hoặc tổng tác động bên trong database.
- **Hibernate Statistics đo hoạt động ORM**, không phải tổng physical row count.
- **JDBC update count đo kết quả statement/batch theo driver**, không mặc nhiên bao gồm mọi trigger/FK cascade.
- **Bulk JPQL/native SQL bỏ qua lifecycle từng entity** và có thể làm Persistence Context stale; cần xử lý flush/clear/refresh có chủ đích.
- **FK cascade và trigger phải được xác minh ở database**, không suy ra từ annotation.
- **Optimistic version predicate có thể làm DELETE ảnh hưởng 0 row**, báo hiệu stale state thay vì chỉ đơn giản là không tồn tại.
- **Flush khác commit:** SQL DELETE đã chạy vẫn có thể rollback.
- **Bằng chứng cuối cùng cho dữ liệu đã xóa là trạng thái database sau commit**, được đọc lại trong context phù hợp.

Muốn biết một thao tác xóa trong Hibernate có đúng hay không, hãy đối chiếu **ý nghĩa nghiệp vụ, mapping, SQL thực tế, số hàng và kết quả sau commit**. Không một chỉ số đơn lẻ nào mô tả đầy đủ toàn bộ tác động. Khi mỗi bảng có kỳ vọng rõ ràng và số liệu được đo đúng tầng, việc kiểm chứng cascade và delete trở nên minh bạch, có thể giải thích và tái hiện trong kiểm thử.
