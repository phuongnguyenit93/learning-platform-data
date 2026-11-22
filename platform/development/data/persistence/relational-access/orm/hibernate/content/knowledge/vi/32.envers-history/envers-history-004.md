# Đọc thực thể tại một revision bằng AuditReader

## 1. Mục tiêu của bài học

Trong ứng dụng Hibernate, một thực thể thường thay đổi nhiều lần trong suốt vòng đời. Ví dụ, đơn hàng có thể được tạo ở trạng thái `DRAFT`, xác nhận thành `CONFIRMED`, rồi chuyển sang `PAID`. Khi một người dùng hỏi “đơn hàng này trông như thế nào tại lần thay đổi số 12?”, truy vấn bảng `orders` hiện tại không trả lời được vì bảng này thường chỉ chứa trạng thái mới nhất.

**Hibernate Envers** bổ sung khả năng lưu và truy vấn lịch sử thay đổi cho những entity được cấu hình audit. API trung tâm để đọc lịch sử là `AuditReader`.

Sau bài này, bạn có thể:

- Hiểu revision trong Envers là gì và nó khác với entity ID hoặc optimistic-locking version ra sao.
- Dùng `AuditReaderFactory.get(...)` lấy `AuditReader` trong Hibernate/JPA.
- Gọi `AuditReader.find(EntityClass.class, entityId, revision)` để dựng trạng thái entity **tại một revision**.
- Biết tại sao có thể đọc được entity ở revision mà entity đó không có bản ghi thay đổi trực tiếp.
- Phân biệt “không tồn tại ở thời điểm đó” với “bị xóa ở thời điểm đó”.
- Lấy danh sách revisions, đối chiếu thời gian và đọc lịch sử trong một Spring service.
- Tránh những giả định sai về association, trường không audit, bulk SQL, transaction và security.
- Thiết kế integration test và tối ưu query đọc lịch sử theo DBMS đích.

Đây là bài về **đọc lịch sử**. Envers không biến lịch sử thành một database backup, không tự theo dõi mọi thay đổi từ công cụ ngoài Hibernate, và không cho phép dùng historical entity như một managed entity bình thường mà không cân nhắc.

## 2. Envers tham gia vào Hibernate như thế nào?

Trong một ứng dụng JPA thông thường:

```text
Application service
       |
       v
EntityManager / Hibernate Session
       |
       v
Current entity table: orders
       |
       v
COMMIT transaction
```

Khi bật Envers và đánh dấu entity được audit, Hibernate tích hợp các audit listeners với entity lifecycle. Các thay đổi được xử lý qua ORM sẽ được ghi vào những audit tables theo mapping:

```text
Application service
       |
       v
Hibernate Session / entity changes
       |
       +-- Current data ----------> orders
       |
       +-- Envers audit entries --> orders_AUD
       |                              |
       |                              +--> REV / REVTYPE
       |
       +-- Revision metadata ------> REVINFO
       |
       v
One local database transaction
       |
       v
COMMIT / ROLLBACK cả dữ liệu và audit rows
```

Tên bảng audit và revision table ở sơ đồ là ví dụ theo naming convention phổ biến. Chúng có thể được đổi bằng cấu hình, `@AuditTable` hoặc custom revision entity.

Envers chỉ lưu lịch sử của những entity/property được cấu hình audit và những thay đổi đi qua cơ chế Hibernate phù hợp. Một `UPDATE` chạy trực tiếp bằng native JDBC hoặc bulk HQL có thể không tạo audit event Envers cho từng entity.

## 3. Revision là gì?

**Revision** là một mốc thay đổi được Envers đánh số để mô tả lịch sử audit. Một transaction sửa nhiều audited entities có thể tạo **một revision identifier** dùng chung cho các thay đổi của transaction đó.

Ví dụ:

```text
Revision 1:
  Order #10 được tạo với status=DRAFT

Revision 2:
  Product #7 đổi giá
  (Order #10 không thay đổi)

Revision 3:
  Order #10 đổi status=CONFIRMED
  Order #20 được tạo

Revision 4:
  Customer #5 đổi tên

Revision 5:
  Order #10 đổi status=PAID
```

Ta có thể hỏi:

```java
Order historical = reader.find(Order.class, 10L, 4);
```

Trạng thái của Order #10 tại revision 4 là `CONFIRMED`, vì thay đổi gần nhất của Order này **ở hoặc trước** revision 4 là revision 3. Order #10 không cần có hàng `orders_AUD` tại revision 4.

### 3.1. Revision không phải ID của entity

| Giá trị | Ví dụ | Ý nghĩa |
|---|---|---|
| Entity ID | `Order.id = 10` | Xác định một Order |
| Revision number | `REV = 4` | Xác định một mốc trong lịch sử audit |
| Entity version | `@Version = 2` | Dùng cho optimistic locking khi cập nhật |
| Business status | `CONFIRMED` | Trạng thái nghiệp vụ |

Không dùng `@Version` thay cho revision Envers. Version có thể tăng theo một quy tắc riêng, có thể không được audit như một field thông thường, và không thể hiện lịch sử của toàn hệ thống.

### 3.2. Revision thường thuộc phạm vi persistence unit

Trong một thiết lập Envers thông thường, revision IDs được phát sinh và dùng chung cho các audited entities thuộc cơ chế audit tương ứng. Không hiểu chúng như “revision số 4 của riêng Order #10”. Danh sách revisions mà Order #10 trực tiếp thay đổi có thể chỉ là `[1, 3, 5]`, trong khi bạn vẫn có thể đọc state của nó tại revision 4.

Khi ứng dụng có nhiều `EntityManagerFactory`, nhiều database hoặc cơ chế audit riêng, không giả định revision 4 ở DB A tương ứng cùng một thời điểm/giao dịch với revision 4 ở DB B.

## 4. Cấu trúc bảng dữ liệu hiện tại và bảng audit

Giả sử bảng hiện tại:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount NUMERIC(19, 2) NOT NULL
);
```

Với Envers, dữ liệu audit về mặt khái niệm có thể như:

```text
purchase_orders
+----+--------------+--------+--------------+
| id | order_number | status | total_amount |
+----+--------------+--------+--------------+
| 10 | PO-001       | PAID   | 100.00       |
+----+--------------+--------+--------------+

purchase_orders_AUD
+----+-----+---------+--------------+-----------+--------------+
| id | REV | REVTYPE | order_number | status    | total_amount |
+----+-----+---------+--------------+-----------+--------------+
| 10 | 1   | ADD     | PO-001       | DRAFT     | 100.00       |
| 10 | 3   | MOD     | PO-001       | CONFIRMED | 100.00       |
| 10 | 5   | MOD     | PO-001       | PAID      | 100.00       |
+----+-----+---------+--------------+-----------+--------------+

REVINFO
+-----+--------------------+
| REV | REVTSTMP           |
+-----+--------------------+
| 1   | timestamp          |
| 2   | timestamp          |
| 3   | timestamp          |
| 4   | timestamp          |
| 5   | timestamp          |
+-----+--------------------+
```

Các chuỗi `ADD`, `MOD` và `DEL` ở sơ đồ chỉ giúp đọc; cột `REVTYPE` vật lý của Envers thường lưu mã số/giá trị theo mapping/provider, không nhất thiết là ba chuỗi đó. Cấu trúc thật còn phụ thuộc audit strategy, naming conventions, ID mapping và schema migration.

Với cách lưu này, `AuditReader.find(Order.class, 10L, 4)` dùng hàng lịch sử của Order #10 ở revision 3 để dựng state tại revision 4.

## 5. Thêm Hibernate Envers vào dự án

Trong Maven, có thể sử dụng:

```xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
```

Đây là tọa độ artifact cho các thế hệ Hibernate ORM hiện đại. Phiên bản Envers cần **tương thích với Hibernate ORM core** đang sử dụng; nếu dùng Spring Boot dependency management, nên để Boot hoặc BOM tương thích quản lý phiên bản thay vì tự ghép các versions khác nhau.

Với một số thế hệ Hibernate cũ, group ID và API/integration details có thể khác. Trước khi áp dụng mã ví dụ, cần xác định Hibernate major version của dự án.

Trong Gradle:

```kotlin
dependencies {
    implementation("org.hibernate.orm:hibernate-envers")
}
```

Ví dụ Gradle giả định dự án có dependency management hoặc version catalog cung cấp version tương thích.

### 5.1. Phân biệt Envers với Hibernate ORM

- `hibernate-core` cung cấp cơ chế ORM, `Session`, mapping và dirty checking.
- `hibernate-envers` cung cấp audit integration và `AuditReader`.
- Jakarta Persistence quy định `EntityManager` và lifecycle chuẩn nhưng **không định nghĩa `AuditReader`**.
- `AuditReader` là API của Hibernate Envers, không portable sang JPA provider khác.

## 6. Đánh dấu entity bằng @Audited

Ví dụ một entity có trạng thái được audit:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import org.hibernate.envers.Audited;

@Entity
@Table(name = "purchase_orders")
@Audited
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String orderNumber, BigDecimal totalAmount) {
        this.orderNumber = orderNumber;
        this.totalAmount = totalAmount;
        this.status = OrderStatus.DRAFT;
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not draft");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void markPaid() {
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException("Order is not confirmed");
        }
        status = OrderStatus.PAID;
    }
}

enum OrderStatus {
    DRAFT, CONFIRMED, PAID, CANCELLED
}
```

`@Audited` ở class áp dụng cho những persistent properties thuộc phạm vi audit theo mapping và cấu hình Envers. Những field được `@NotAudited` sẽ không được lưu đầy đủ trong snapshot lịch sử. Một số field đặc biệt như optimistic-locking version có chính sách audit riêng; không tự giả định `@Version` tương đương `REV` hoặc luôn hiện diện trong audit table.

### 6.1. Vì sao cần no-arg constructor?

Entity JPA cần constructor không tham số có visibility phù hợp; Hibernate sử dụng cơ chế instantiation/proxy khi đọc dữ liệu và dựng historical state. Ví dụ dùng `protected PurchaseOrder()` để tránh client code tự tạo entity rỗng tùy ý.

### 6.2. Mapping hiện tại và mapping lịch sử là hai hợp đồng

Thêm `@Audited` không làm thay đổi business behavior của `PurchaseOrder.confirm()`; nó bổ sung audit persistence cho những thay đổi qua Hibernate. Nhưng khi schema phát triển, audit tables cũng cần migration tương ứng để có thể đọc lịch sử cũ và mới.

## 7. Các hành động tạo nên revision

Ví dụ service:

```java
@Service
public class PurchaseOrderWriteService {
    private final EntityManager em;

    public PurchaseOrderWriteService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public Long create(String number, BigDecimal total) {
        PurchaseOrder order = new PurchaseOrder(number, total);
        em.persist(order);
        return order.getId();
    }

    @Transactional
    public void confirm(Long id) {
        PurchaseOrder order = em.find(PurchaseOrder.class, id);
        if (order == null) {
            throw new IllegalArgumentException("Unknown order");
        }
        order.confirm();
    }

    @Transactional
    public void markPaid(Long id) {
        PurchaseOrder order = em.find(PurchaseOrder.class, id);
        if (order == null) {
            throw new IllegalArgumentException("Unknown order");
        }
        order.markPaid();
    }
}
```

Đoạn code giả định Spring quản lý transaction bằng JPA, Envers đã được bật và schema audit đã sẵn sàng. Mỗi method được gọi qua Spring proxy trong transaction riêng và khi thay đổi audited state được flush/commit, Envers có thể tạo revision mới. Chỉ gọi một setter mà không có dữ liệu thay đổi thực sự không có nghĩa chắc chắn sẽ xuất hiện audit row mới.

### 7.1. Revision được tạo theo transaction audit

Nếu một transaction thay đổi hai audited entities, chúng có thể dùng chung revision. Nếu transaction bị rollback, cả thay đổi hiện tại và audit rows trong cùng local database transaction cũng bị rollback.

```text
Transaction T
  UPDATE Order #10
  UPDATE Customer #5
  INSERT related audit rows
  INSERT revision metadata
COMMIT

Both changes reference revision R
```

Không giả định mỗi SQL UPDATE hay mỗi method call tạo đúng một revision riêng. Chính lifecycle, flush và phạm vi transaction quyết định những audited work units được commit.

## 8. Lấy AuditReader từ EntityManager

Trong ứng dụng Spring JPA:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

@Repository
public class PurchaseOrderHistoryRepository {

    @PersistenceContext
    private EntityManager em;

    public PurchaseOrder findAtRevision(
            Long orderId, Number revision) {
        AuditReader reader = AuditReaderFactory.get(em);
        return reader.find(
            PurchaseOrder.class, orderId, revision);
    }
}
```

`AuditReaderFactory.get(em)` tạo/trả về AuditReader gắn với JPA/Hibernate persistence context phù hợp. `EntityManager` phải thuộc Hibernate provider và còn hợp lệ cho các thao tác query; không dùng AuditReader từ một factory để đọc audit data của entity được quản lý bởi factory khác.

Cũng có thể dùng Hibernate `Session`:

```java
Session session = entityManager.unwrap(Session.class);
AuditReader reader = AuditReaderFactory.get(session);
```

Đường EntityManager thuận tiện trong Spring Data JPA; đường Session phù hợp khi ứng dụng sử dụng Hibernate API trực tiếp.

### 8.1. Không tự tạo một AuditReader toàn cục

Không lưu `AuditReader` làm singleton dùng chung cho mọi request. Nó dựa trên session/persistence context và không được xem là đối tượng thread-safe dùng toàn cục. Lấy reader trong phạm vi transaction/unit of work đang đọc lịch sử.

## 9. Cú pháp chính: AuditReader.find()

Mẫu quan trọng nhất:

```java
T historical = reader.find(
    EntityClass.class,
    entityId,
    revisionNumber);
```

Ví dụ:

```java
AuditReader reader = AuditReaderFactory.get(em);

PurchaseOrder orderAtRevision3 = reader.find(
    PurchaseOrder.class,
    10L,
    3);
```

Các tham số:

| Đối số | Ý nghĩa |
|---|---|
| `PurchaseOrder.class` | Entity class được Envers audit |
| `10L` | Identifier của instance |
| `3` | Revision toàn cục mà bạn muốn quan sát trạng thái tại đó |

Kết quả là trạng thái entity theo dữ liệu audit **có hiệu lực tại revision được yêu cầu**, không nhất thiết là một audit row được tạo đúng revision ấy.

### 9.1. Hình dung thuật toán ở mức khái niệm

```text
find(Order #10, revision R)
           |
           v
Tìm audit record gần nhất của Order #10
có REV <= R, theo audit strategy đã cấu hình
           |
       Có bản ghi?
         /     \
       KHÔNG    CÓ
         |       |
         v       v
       null    Bản ghi gần nhất là DEL?
                     /       \
                    CÓ       KHÔNG
                     |         |
                     v         v
                    null    Dựng historical state
```

Đây là cách hiểu semantics, không phải SQL chính xác Hibernate luôn sinh. SQL phụ thuộc `DefaultAuditStrategy`, `ValidityAuditStrategy`, identifier mapping và DBMS dialect.

## 10. Đọc đúng một revision hay đọc chính xác hàng thay đổi?

Hai câu hỏi sau khác nhau:

1. “**Trạng thái Order #10 tại revision 4 là gì?**”
2. “**Order #10 có thay đổi trong revision 4 không?**”

Với timeline:

```text
Global revision       1         2         3         4         5
Order #10 event       ADD       --        MOD       --        MOD
Order #10 status      DRAFT     DRAFT     CONFIRMED CONFIRMED PAID
```

`reader.find(PurchaseOrder.class, 10L, 4)` trả về snapshot `CONFIRMED`. Nó **không chứng minh** Order #10 từng được sửa ở revision 4.

Muốn biết những revisions mà Order #10 có audit entry trực tiếp, dùng `reader.getRevisions(...)` hoặc AuditQuery API.

## 11. Đọc lịch sử khi entity không tồn tại ở revision được hỏi

Giả sử Order #20 chỉ được tạo ở revision 7:

```java
PurchaseOrder at5 = reader.find(
    PurchaseOrder.class, 20L, 5);
```

Kết quả sẽ là `null` vì tại revision 5 chưa có historical state của Order #20.

Đây không nhất thiết là lỗi:

- Entity có thể chưa được tạo tại revision ấy.
- Entity có thể đã bị xóa trước revision ấy.
- Entity ID có thể không tồn tại hoặc dữ liệu audit không bao phủ lịch sử.

Trong repository/service, không trả thông báo “entity hiện tại không tồn tại” chỉ dựa trên `null` khi đang đọc lịch sử; cần tách semantics của lịch sử và hiện tại.

### 11.1. Validate revision đầu vào

Người dùng có thể truyền revision âm, 0, chuỗi không parse được hoặc revision quá lớn. Ở API boundary nên kiểm tra:

```java
if (revision == null || revision.longValue() <= 0) {
    throw new IllegalArgumentException(
        "Revision must be positive");
}
```

Envers có thể ném exception khi revision không hợp lệ. Đừng để stack trace provider lộ trực tiếp ra HTTP response. Với revision số dương nhưng chưa từng được commit, `find()` có thể trả null nếu không có dữ liệu hiệu lực theo yêu cầu.

## 12. Đọc sau khi entity bị xóa

Giả sử:

```text
Revision 2: Order #10 ADD
Revision 5: Order #10 MOD
Revision 8: Order #10 DEL
```

Ta hỏi:

```java
PurchaseOrder at7 = reader.find(
    PurchaseOrder.class, 10L, 7);

PurchaseOrder at8 = reader.find(
    PurchaseOrder.class, 10L, 8);

PurchaseOrder at9 = reader.find(
    PurchaseOrder.class, 10L, 9);
```

Thông thường:

- `at7` có snapshot trước khi xóa.
- `at8` là `null` vì entity đã bị xóa tại revision 8.
- `at9` tiếp tục là `null` nếu không được tái tạo.

Envers có thể lưu bản ghi `REVTYPE=DEL` vào audit table. Nhưng phương thức `AuditReader.find()` được dùng để hỏi **entity tồn tại tại revision đó hay không**, không dùng trực tiếp để lấy một “deleted entity object” tại thời điểm sau xóa.

### 12.1. Muốn xem bản ghi deletion?

Hãy dùng AuditQuery với `selectDeletedEntities=true` hoặc đọc revision trước khi xóa. Những field có được giữ ở bản ghi xóa hay không còn phụ thuộc cấu hình Envers.

Ví dụ:

```properties
spring.jpa.properties.org.hibernate.envers.store_data_at_delete=true
```

Cấu hình `store_data_at_delete` cho phép lưu thêm data tại deletion revision trong các phiên bản Envers có hỗ trợ. Mặc định có thể chỉ có identifier/revision metadata và các audited fields còn lại ở trạng thái null. Cần kiểm tra cấu hình và schema thực tế, và không nhầm tính năng này với việc `find()` trả historical entity còn sống sau deletion.

## 13. Lấy các revisions một entity từng thay đổi

Envers cung cấp:

```java
AuditReader reader = AuditReaderFactory.get(em);

List<Number> revisions =
    reader.getRevisions(PurchaseOrder.class, 10L);
```

Ví dụ:

```text
revisions = [1, 3, 5, 8]
```

Danh sách này gồm những revision có audit record của entity, thường theo thứ tự tăng dần. Nó không bao gồm những global revisions chỉ sửa entity khác.

Một cách đọc toàn bộ các điểm thay đổi:

```java
for (Number revision : reader.getRevisions(
        PurchaseOrder.class, orderId)) {

    PurchaseOrder snapshot = reader.find(
        PurchaseOrder.class,
        orderId,
        revision);

    // Nếu đây là deletion revision,
    // snapshot có thể là null.
}
```

Với entity có hàng nghìn revisions, không nên làm vòng lặp này không giới hạn trên API request vì có thể phát nhiều SQL và tạo object lớn. Dùng AuditQuery/pagination khi cần một timeline dài.

## 14. Lấy revision gần nhất ở hoặc trước mốc được yêu cầu

Đôi khi API cần hiển thị cả “state đang dùng” và “lần cuối entity thay đổi”.

Ví dụ helper:

```java
static Number lastRevisionAtOrBefore(
        List<Number> entityRevisions,
        long requestedRevision) {

    Number last = null;
    for (Number candidate : entityRevisions) {
        if (candidate.longValue() > requestedRevision) {
            break;
        }
        last = candidate;
    }
    return last;
}
```

Ví dụ `getRevisions() = [1, 3, 5]` và requested revision là 4 thì last changed revision = 3.

Đây là logic minh họa cho danh sách đã có sẵn và được sắp xếp tăng. Với history lớn, cách lấy toàn bộ danh sách để tìm một giá trị là không tối ưu; dùng AuditQuery với revision predicate, descending order và giới hạn một result.

Lưu ý: “last changed revision” không luôn mang ý nghĩa entity vẫn tồn tại; nếu entry gần nhất là `DEL` thì trạng thái tại revision sau xóa là không tồn tại.

## 15. Revision entity và thời gian revision

Envers lưu metadata của revision, thông thường bao gồm revision ID và timestamp.

```java
Number revision = 5;
Date changedAt = reader.getRevisionDate(revision);
```

Ví dụ hiển thị:

```java
Instant instant = changedAt.toInstant();
String utcTime = instant.toString();
```

`getRevisionDate()` giúp chuyển revision number thành thời gian được lưu trong revision metadata. Cẩn trọng:

- Timestamp là metadata lúc revision được tạo, không tự động là “thời điểm commit chính xác” theo đồng hồ toàn hệ thống.
- Transaction có thể kéo dài từ lúc revision được tạo đến lúc commit.
- Nhiều revisions có timestamp rất gần nhau hoặc cùng precision.
- Đồng hồ trên nhiều nodes có thể có sai lệch; cần thiết kế logging/clock synchronization phù hợp.
- Không coi timestamp của hai database Envers độc lập là một global distributed snapshot.

### 15.1. Tìm revision theo ngày giờ

Envers có API:

```java
Number revision = reader.getRevisionNumberForDate(
    Date.from(requestedInstant));
```

API này liên hệ thời điểm với revision metadata theo semantics của Envers/provider. Khi thiết kế endpoint “xem tại thời gian T”, hãy xác định rõ cách chọn revision cho ranh giới thời gian, múi giờ và trường hợp chưa có revision phù hợp.

Không giả định timestamp order luôn đồng nghĩa commit order tuyệt đối trong hệ thống concurrent hoặc phân tán. Nếu yêu cầu “trạng thái đã được commit đúng tại T” là hợp đồng kiểm toán nghiêm ngặt, cần xác minh semantics timestamp/transaction của giải pháp audit, không chỉ gọi API theo ngày.

## 16. Đọc revision metadata trực tiếp

Envers cung cấp một revision entity mặc định hoặc revision entity do ứng dụng tự định nghĩa. Với schema/default mapping phù hợp, có thể dùng:

```java
import org.hibernate.envers.DefaultRevisionEntity;

DefaultRevisionEntity metadata = reader.findRevision(
    DefaultRevisionEntity.class,
    5);
```

Revision metadata có thể cho biết ID, timestamp và những field custom nếu đã được cấu hình. Tên class và kiểu revision entity thực tế phụ thuộc cấu hình. Không gọi `findRevision(DefaultRevisionEntity.class, ...)` nếu ứng dụng đã dùng custom revision entity khác mà không tương thích.

### 16.1. Global revision khác entity-specific revision

`getRevisionDate(5)` hỏi metadata của global revision 5; `getRevisions(PurchaseOrder.class, 10L)` hỏi Order #10 có những revision nào. Đó là hai tập câu hỏi khác nhau.

## 17. Tạo service đọc lịch sử với Spring Boot

Một API service nên:

1. Kiểm tra revision và ID.
2. Kiểm tra quyền truy cập lịch sử.
3. Lấy `AuditReader` trong transaction đọc.
4. Gọi `find()`.
5. Chuyển snapshot sang DTO ở **trong** transaction, tránh đưa proxy/lazy graph ra tầng web.
6. Trả kết quả có semantics rõ ràng khi snapshot không tồn tại.

Ví dụ DTO:

```java
public record PurchaseOrderRevisionView(
    Long id,
    String orderNumber,
    String status,
    BigDecimal totalAmount,
    long requestedRevision
) {}
```

Service:

```java
@Service
public class PurchaseOrderHistoryService {

    @PersistenceContext
    private EntityManager em;

    private final PurchaseOrderAuthorization authorization;

    public PurchaseOrderHistoryService(
            PurchaseOrderAuthorization authorization) {
        this.authorization = authorization;
    }

    @Transactional(readOnly = true)
    public Optional<PurchaseOrderRevisionView> findAt(
            Long orderId, long revision) {

        if (orderId == null || revision <= 0) {
            throw new IllegalArgumentException(
                "Order ID and positive revision required");
        }

        authorization.requireHistoryReadAccess(orderId);

        AuditReader reader = AuditReaderFactory.get(em);
        PurchaseOrder historical = reader.find(
            PurchaseOrder.class, orderId, revision);

        if (historical == null) {
            return Optional.empty();
        }

        return Optional.of(new PurchaseOrderRevisionView(
            historical.getId(),
            historical.getOrderNumber(),
            historical.getStatus().name(),
            historical.getTotalAmount(),
            revision));
    }
}
```

Ví dụ giả định `PurchaseOrderAuthorization` là một service của ứng dụng có khả năng kiểm tra quyền với cả dữ liệu lịch sử. Nó phải được triển khai thực tế; không được coi một method giả chưa có code như bằng chứng security đã hoàn chỉnh.

### 17.1. Vì sao @Transactional(readOnly = true)?

Annotation này giúp xác định rõ read service boundary, tạo persistence context phù hợp với JPA query và có thể ảnh hưởng flush mode/hints theo integration. Nhưng:

- Nó không bảo đảm rằng truy vấn chỉ đọc một consistent snapshot nếu transaction isolation không đủ.
- Nó không tự cấm mọi câu SQL ghi ở DB.
- Nó không tự áp dụng authorization hay tenant filtering lên audit tables.

Muốn consistency giữa nhiều reads, xác định isolation và DBMS semantics cụ thể. Muốn security, kiểm tra quyền ở application hoặc dùng database permissions/RLS phù hợp.

## 18. Viết controller trả response rõ ràng

Ví dụ:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderHistoryController {
    private final PurchaseOrderHistoryService history;

    public OrderHistoryController(PurchaseOrderHistoryService history) {
        this.history = history;
    }

    @GetMapping("/{id}/revisions/{revision}")
    public ResponseEntity<PurchaseOrderRevisionView> getRevision(
            @PathVariable Long id,
            @PathVariable long revision) {

        return history.findAt(id, revision)
            .map(ResponseEntity::ok)
            .orElseGet(() ->
                ResponseEntity.notFound().build());
    }
}
```

API này coi “không có snapshot tại revision được hỏi” là 404, nhưng một ứng dụng có thể cần semantics khác: phân biệt order chưa tạo, order đã xóa, thiếu audit history hoặc yêu cầu revision vượt hiện tại. Quyết định này thuộc API contract và không nên được suy ra tùy tiện từ `null`.

Nên kiểm tra authorization **trước khi trả bất kỳ dữ liệu lịch sử nào**. Với tài nguyên nhạy cảm, có thể chủ đích không tiết lộ sự tồn tại của ID mà người dùng không được phép truy cập.

## 19. Tại sao không trả entity lịch sử trực tiếp qua REST?

Không nên để controller:

```java
return auditReader.find(PurchaseOrder.class, id, revision);
```

rồi giao toàn bộ entity cho Jackson serialize. Rủi ro:

- Lazy associations có thể phát thêm SQL sau khi transaction đọc kết thúc.
- Jackson có thể đi theo graph hai chiều gây vòng lặp hoặc dữ liệu quá lớn.
- Entity có field nội bộ mà client không được xem.
- Mapping thay đổi làm API JSON contract thay đổi không kiểm soát.
- Historical data có thể chứa PII vốn không còn hiện diện trong current entity.

DTO tại service boundary giúp kiểm soát các field lịch sử được công bố, chuẩn hóa enum/number/time và giới hạn graph cần đọc.

## 20. Historical entity không phải managed current state

Một đối tượng lấy qua Envers biểu diễn **trạng thái lịch sử**. Không nên coi nó như entity hiện tại để sửa rồi gọi `save()` hoặc `merge()`:

```java
PurchaseOrder historical = reader.find(
    PurchaseOrder.class, id, oldRevision);

// Không làm theo phản xạ:
// em.merge(historical);
```

Nếu `merge()` chép state cũ vào current managed entity, ứng dụng có thể vô tình **ghi đè dữ liệu mới**, vi phạm version/invariant, bỏ qua domain transitions, hoặc tạo audit entry khác nhưng không có ý nghĩa phục hồi đúng.

Nếu cần chức năng “khôi phục trạng thái ở revision X”, hãy tạo một **business command mới**:

1. Đọc snapshot lịch sử.
2. Tải current managed entity.
3. Kiểm tra quyền và business invariant hiện tại.
4. Chọn rõ những fields được phép phục hồi.
5. Áp dụng thay đổi thông qua domain methods hoặc logic version-aware.
6. Commit một transaction hiện tại; Envers ghi **revision mới** thể hiện hành động khôi phục.

Phục hồi trạng thái là một thay đổi mới, không phải quay ngược global revision clock.

## 21. Sự khác biệt giữa các revisions và audit query

Nếu chỉ cần một entity ở một mốc, `AuditReader.find()` là API đơn giản nhất.

Nếu cần:

- Liệt kê các lần thay đổi gần nhất.
- Lọc theo `RevisionType.ADD/MOD/DEL`.
- Phân trang timeline.
- Lấy cả revision metadata.
- Lọc nhiều IDs hoặc thuộc tính audited.
- Tìm audit rows đúng một revision cụ thể.

thì `AuditReader.createQuery()` và `AuditEntity` thường phù hợp hơn.

```java
AuditReader reader = AuditReaderFactory.get(em);

List<?> results = reader.createQuery()
    .forRevisionsOfEntity(
        PurchaseOrder.class,
        false, // selectEntitiesOnly
        true)  // selectDeletedEntities
    .add(AuditEntity.id().eq(orderId))
    .addOrder(AuditEntity.revisionNumber().desc())
    .setMaxResults(20)
    .getResultList();
```

Với `selectEntitiesOnly=false`, một result thường là bộ ba:

```java
for (Object value : results) {
    Object[] row = (Object[]) value;

    PurchaseOrder entityState = (PurchaseOrder) row[0];
    Object revisionEntity = row[1];
    RevisionType changeType = (RevisionType) row[2];

    // Đọc changeType và revision metadata.
}
```

Kiểu `revisionEntity` cụ thể phụ thuộc cấu hình revision entity. `selectDeletedEntities=true` cho phép nhận audit entries của deletion; không có nghĩa mọi property của deleted snapshot đều được lưu.

## 22. Tìm một audit entry đúng revision đã chỉ định

Khi muốn biết “Order #10 có đổi ở revision 4 không?”, ta lọc **bằng** revision:

```java
List<?> changes = reader.createQuery()
    .forRevisionsOfEntity(PurchaseOrder.class, false, true)
    .add(AuditEntity.id().eq(10L))
    .add(AuditEntity.revisionNumber().eq(4))
    .getResultList();
```

Nếu Order #10 không sửa tại revision 4, danh sách có thể rỗng dù:

```java
reader.find(PurchaseOrder.class, 10L, 4)
```

vẫn trả một historical Order hợp lệ. Đây là khác biệt cốt lõi giữa **trạng thái tại revision** và **sự kiện thay đổi ở revision**.

Không xây API “xem state tại R” bằng cách bắt buộc có audit entry `REV = R`; cách đó sẽ báo “không có dữ liệu” sai cho những mốc chỉ sửa entity khác.

## 23. Dùng AuditQuery để xác định change gần nhất

Ví dụ truy vấn các audit rows ở hoặc trước revision yêu cầu:

```java
List<?> rows = reader.createQuery()
    .forRevisionsOfEntity(PurchaseOrder.class, false, true)
    .add(AuditEntity.id().eq(orderId))
    .add(AuditEntity.revisionNumber().le(requestedRevision))
    .addOrder(AuditEntity.revisionNumber().desc())
    .setMaxResults(1)
    .getResultList();

if (!rows.isEmpty()) {
    Object[] record = (Object[]) rows.get(0);
    RevisionType type = (RevisionType) record[2];
    // type có thể là ADD, MOD hoặc DEL.
}
```

Query này hữu ích khi ngoài state, bạn cần metadata của thay đổi gần nhất. Khi chỉ cần entity tồn tại tại R, thường nên dùng `reader.find()` trực tiếp để giảm code và tránh tự tái hiện thuật toán audit strategy.

## 24. Đọc liên tiếp hai revision để so sánh state

Giả sử muốn hiển thị “trước và sau”:

```java
PurchaseOrder before = reader.find(
    PurchaseOrder.class, orderId, revisionBefore);

PurchaseOrder after = reader.find(
    PurchaseOrder.class, orderId, revisionAfter);
```

Sau đó so sánh các audited fields:

```java
public record OrderChangeView(
    String statusBefore,
    String statusAfter,
    BigDecimal totalBefore,
    BigDecimal totalAfter
) {}

static OrderChangeView diff(
        PurchaseOrder before,
        PurchaseOrder after) {
    return new OrderChangeView(
        before == null ? null : before.getStatus().name(),
        after == null ? null : after.getStatus().name(),
        before == null ? null : before.getTotalAmount(),
        after == null ? null : after.getTotalAmount());
}
```

Đây là ví dụ so sánh một tập field được chọn, không phải một diff engine tổng quát. Cần định nghĩa semantics cho create/delete, numerical precision, associations và fields không audit.

### 24.1. Revision trước/sau không nhất thiết là hai số liên tiếp

Nếu Order #10 có revisions `[1, 3, 5]`, so sánh thay đổi thứ hai thường là snapshot 1 với snapshot 3, không phải 2 với 3. Revision 2 có thể thuộc Product khác và không làm Order thay đổi.

Lấy `getRevisions(Order.class,id)` trước để xác định cặp mốc thay đổi entity, hoặc dùng AuditQuery phục vụ timeline.

## 25. Association trong historical snapshot cần hiểu thế nào?

Một entity thường tham chiếu entity khác:

```java
@Entity
@Audited
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}

@Entity
@Audited
public class Customer {
    @Id
    private Long id;

    private String name;
}
```

Khi association được audit hợp lệ, Envers có thể dựng quan hệ theo trạng thái lịch sử tại revision tương ứng. Tuy nhiên không nên coi bất kỳ graph nào được load là đầy đủ hoặc luôn được cache.

### 25.1. Trường hợp cả hai entity đều được audit

Giả sử:

```text
Revision 1: Customer #5 name="An"
Revision 2: Order #10 points to Customer #5
Revision 3: Customer #5 name="An Nguyễn"
```

Khi đọc Order #10 tại revision 2 và truy cập Customer lịch sử phù hợp, mục tiêu của Envers là thể hiện snapshot quan hệ ở mốc được hỏi theo mapping. Nhưng việc lazy load, cách dựng proxy hoặc query và khả năng mapping relation còn tùy phiên bản/cấu hình.

Không test duy nhất scalar `order.status` rồi khẳng định association history đã đúng; phải có integration test cho quan hệ thực sự cần hiển thị.

### 25.2. Trường hợp target không được audit

Một entity audited tham chiếu bảng danh mục không audited có thể sử dụng:

```java
@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
@ManyToOne(fetch = FetchType.LAZY)
private Country country;
```

Ví dụ này giả định `Country` không được audit và mapping relation phù hợp. Với `RelationTargetAuditMode.NOT_AUDITED`, phần target có thể được giải quyết theo **state hiện tại** của entity danh mục, chứ không phải lịch sử của Country tại revision cũ.

Vì vậy, một Order lịch sử có thể hiển thị tên Country mới nhất thay vì tên Country ở thời điểm đặt hàng. Nếu yêu cầu chính xác lịch sử, phải audit target hoặc lưu snapshot value phù hợp tại lúc giao dịch.

### 25.3. Delete target và referential integrity

Nếu historical Order tham chiếu một non-audited entity đã bị xóa ở current database, việc load relation có thể thất bại hoặc không trả object mong đợi tùy mapping. Đừng xây API audit phụ thuộc mù vào current target nếu retention policy cho phép xóa target.

## 26. Collection history không phải lúc nào cũng rẻ

Ví dụ:

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
```

Khi `PurchaseOrder` và `OrderLine` được audit đầy đủ, việc dựng collection tại revision có thể cần nhiều truy vấn vào audit tables và bảng quan hệ, tùy mapping. Nếu Order có 3.000 lines nhưng UI chỉ cần trạng thái và tổng tiền, không nên load cả collection.

Các điểm cần cân nhắc:

- Collections có thể dùng audit join table riêng.
- `@ManyToMany` và quan hệ sở hữu có mapping khác `@OneToMany`.
- Fetch lazy cần Session/EntityManager còn hợp lệ.
- Một API list 100 historical orders có thể tạo N+1 audit queries khi duyệt association.
- Audit collections lớn theo thời gian có thể tốn storage và query cost.

Thiết kế DTO chỉ lấy field cần hiển thị. Nếu cần timeline các lines hoặc diffs của collection, xây query/endpoint riêng có pagination/limits.

## 27. @NotAudited làm snapshot lịch sử không đầy đủ

Ví dụ:

```java
@Entity
@Audited
public class Customer {
    @Id
    private Long id;

    private String displayName;

    @NotAudited
    private String currentSupportNote;
}
```

Khi đọc Customer ở revision cũ, `displayName` có thể được phục hồi từ audit history; còn `currentSupportNote` không được lưu như một historical field. Không kỳ vọng field ấy thể hiện giá trị ở quá khứ.

Điều này ảnh hưởng đến:

- DTO so sánh revisions.
- Hệ thống xuất báo cáo kiểm toán.
- Khôi phục dữ liệu.
- Các quy tắc bảo mật/retention.

Trước khi quyết định audit một entity, cần xác định **field nào phải có chứng cứ lịch sử** và field nào không nên lưu vì privacy hoặc dung lượng.

## 28. Soft delete khác hard delete như thế nào?

Hard delete:

```java
em.remove(order);
```

Thường tạo audit deletion entry cho entity audited theo lifecycle.

Soft delete:

```java
order.setDeleted(true);
```

Là một update của field `deleted`, có thể tạo `MOD` audit record thay vì `DEL` nếu field ấy được audit. Lúc này:

```java
reader.find(PurchaseOrder.class, id, revisionAfterSoftDelete)
```

có thể vẫn trả historical entity với `deleted=true`, vì row vật lý vẫn tồn tại và Envers ghi nhận update, không phải entity deletion.

Đừng kết luận rằng API `find()` luôn trả null sau “xóa” theo nghiệp vụ. Cần biết hệ thống dùng soft delete flag, Hibernate-specific soft-delete feature hay `EntityManager.remove()` thật.

### 28.1. Query restriction của dữ liệu hiện tại

Một Hibernate filter hoặc query restriction được dùng để ẩn soft-deleted entities khỏi câu query thông thường không tự chứng minh rằng AuditReader đang áp dụng cùng restriction. Bảo mật và semantics lịch sử phải được kiểm thử riêng.

## 29. AuditReader không tự áp dụng business authorization

Một API đọc lịch sử có thể tiết lộ dữ liệu hơn API đọc trạng thái hiện tại:

- Tên cũ, email cũ và địa chỉ từng lưu.
- Những thông tin đã xóa khỏi bảng hiện tại.
- Giá bán trước đây, chính sách chiết khấu.
- Trạng thái đơn hàng trước khi hủy.
- Người thực hiện thay đổi nếu custom revision metadata có lưu.

Vì vậy cần:

1. Xác thực người gọi.
2. Kiểm tra quyền xem lịch sử của entity.
3. Xác định quyền áp dụng theo **trạng thái hiện tại**, trạng thái lịch sử, hoặc cả hai, tùy nghiệp vụ.
4. Giới hạn field trả về bằng DTO.
5. Ghi audit access event khi dữ liệu nhạy cảm.
6. Áp dụng retention và xóa dữ liệu lịch sử theo chính sách/pháp luật phù hợp.

Không suy rằng vì repository thông thường có `WHERE tenant_id = ...` nên `AuditReader.find()` tự thêm tenant predicate như mong đợi.

### 29.1. Tenant isolation

Nếu nhiều tenants chia sẻ audit tables, cần kiểm tra mapping, tenant discriminator, DB-level RLS và cách reader truy vấn. Những giải pháp có session-level tenant filters hoặc schema-based multi-tenancy phải được test với actual audited mappings.

Tenant ID và security context phải lấy từ nguồn đáng tin ở server; không dùng `tenantId` tùy ý từ query parameter làm quyền truy cập. Một historical ID có thể tiết lộ dữ liệu nhạy cảm nếu thiếu xác thực scope, kể cả khi bản ghi hiện tại không còn tồn tại.

## 30. Transaction scope khi đọc lịch sử

Khuyến nghị đọc nhiều audit values trong một service:

```java
@Transactional(readOnly = true)
public OrderHistoryView view(Long id, long revision) {
    AuditReader reader = AuditReaderFactory.get(em);

    PurchaseOrder state = reader.find(
        PurchaseOrder.class, id, revision);

    Date revisionTime = reader.getRevisionDate(revision);

    return toView(state, revision, revisionTime);
}
```

Trong một transaction đọc:

- Persistence context và JDBC resources có lifecycle rõ.
- Các lazy audited relations cần thiết có thể được khởi tạo trước khi service trả DTO.
- Exception và timeout được quản lý bởi Spring.

Nhưng `readOnly=true` không tự quyết định isolation. Nếu service đọc nhiều audit tables cùng lúc có writes cạnh tranh, cần hiểu consistency guarantees theo DBMS và transaction isolation.

### 30.1. Không giữ Session mở trong response streaming quá lâu

Nếu xuất một báo cáo lịch sử hàng trăm nghìn dòng và giữ một transaction mở trong suốt thời gian người dùng download, database resources/locks có thể bị giữ lâu. Cần pagination, streaming strategy và transaction boundaries được thiết kế riêng, thay vì đưa toàn bộ entities vào memory.

## 31. Không dùng entity revision như “bản snapshot toàn hệ thống”

Một revision giúp Envers đặt state audit theo mốc logic của cơ chế audit đó. Nó không tự tạo:

- Snapshot transactionally consistent của **mọi database** trong microservices.
- Snapshot của những bảng không được audit.
- Snapshot của dữ liệu viết qua JDBC/native SQL bên ngoài listener.
- Snapshot của file/object storage, message broker hoặc external API.
- Bản sao đầy đủ của tất cả entity properties nếu dùng `@NotAudited`.

Nếu cần tái hiện một business decision lịch sử, có thể phải kết hợp Envers với domain events, immutable snapshots, audit logs ở hệ khác và thông tin revision metadata. Đừng quảng bá `AuditReader.find()` như giải pháp backup/restore toàn hệ thống.

## 32. Ảnh hưởng của bulk HQL, native SQL và JDBC

Ví dụ:

```hql
update PurchaseOrder o
set o.status = :status
where o.createdAt < :cutoff
```

Bulk HQL update không tải từng managed entity và không kích hoạt full per-entity lifecycle/callbacks như sửa từng entity. Envers dựa trên audit event integration của Hibernate, vì vậy **không nên giả định bulk HQL mutation sẽ tạo các `*_AUD` rows tương ứng cho từng row được update**.

Tương tự:

```sql
UPDATE purchase_orders
SET status = 'CANCELLED'
WHERE id = 10;
```

khi chạy trực tiếp bằng JDBC/admin SQL, không tự tạo revision Envers theo cơ chế listener của Hibernate.

### 32.1. Hậu quả khi đọc AuditReader

Giả sử:

```text
Revision 10: Order #10 status=CONFIRMED (Envers)
Native SQL:   Order #10 status=PAID      (không có audit entry)
Revision 11: Customer #5 đổi tên        (Envers)
```

Lúc này:

```java
reader.find(PurchaseOrder.class, 10L, 11)
```

có thể tiếp tục trả `CONFIRMED` theo lịch sử audit, dù current table đang là `PAID`. Đó không phải lỗi của `find()`; lịch sử audit chưa ghi nhận thay đổi đi ngoài Envers.

Nếu batch mutation là yêu cầu bắt buộc, cần thiết kế audit riêng (database trigger, explicit audit writes, CDC/event log...) và xác định khả năng đồng bộ với Envers. Không tự chèn `_AUD` rows tùy tiện mà không hiểu revision metadata, audit strategy, composite keys và transaction semantics.

## 33. Dùng AuditTable và custom naming

Envers thường dùng suffix như `_AUD` cho audit table, nhưng có thể chỉnh:

```java
@Entity
@Audited
@AuditTable(name = "purchase_orders_history")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

Khi đọc qua `AuditReader`, ứng dụng vẫn dùng entity class và revision, **không phải viết trực tiếp tên bảng history vào API**. Hibernate/Envers đọc mapping metadata để sinh query tương ứng.

Nếu migration đổi tên audit table mà mapping không đổi, AuditReader có thể lỗi “relation/table not found”. Do đó cần quản lý schema Envers có version đồng bộ với entity mappings.

## 34. Hai audit strategies ảnh hưởng SQL đọc lịch sử

Envers có các strategy như:

- **DefaultAuditStrategy:** xác định state hợp lệ tại R bằng một cách dựa trên revision gần nhất ở hoặc trước R, thường có subquery để chọn audit row phù hợp.
- **ValidityAuditStrategy:** lưu thêm thông tin kết thúc hiệu lực của audit row, cho phép query theo khoảng hiệu lực ở những tình huống thích hợp.

Mô hình khái niệm:

```text
Default:
   ID=10, REV=1, status=DRAFT
   ID=10, REV=3, status=CONFIRMED
   ID=10, REV=5, status=PAID

  read at REV 4 -> select highest REV <= 4

Validity:
   ID=10, REV=1, REVEND=3, status=DRAFT
   ID=10, REV=3, REVEND=5, status=CONFIRMED
   ID=10, REV=5, REVEND=NULL, status=PAID

  read at REV 4 -> interval REV <= 4 < REVEND
```

Chi tiết cấu trúc `REVEND`, timestamp end column và SQL của provider phụ thuộc version/configuration. Không thay audit strategy trên hệ thống đã có history chỉ bằng đổi một property rồi bỏ qua migration dữ liệu cũ; có thể cần backfill validity range và điều chỉnh indexes.

### 34.1. Chọn strategy theo workload đọc

Nếu API thường xuyên xem historical snapshot của bảng có hàng triệu audit entries, cấu trúc index và strategy có thể ảnh hưởng đáng kể. Nhưng không có strategy nào mặc định thắng trong mọi DBMS/khối lượng; phải benchmark với phân bố entity revisions và concurrency thực tế.

## 35. Index cho truy vấn theo entity và revision

Một mẫu truy vấn Envers thường cần lọc:

```text
entity_id = ?
revision <= ?
order by revision desc
```

Một index đáng cân nhắc:

```sql
CREATE INDEX idx_order_aud_id_rev
ON purchase_orders_AUD (id, REV);
```

Đây là ví dụ cho một schema audit thật có tên bảng/cột tương ứng; index có thể đã được tạo bởi PK hoặc migration hiện tại. Không tạo index trùng mà không kiểm tra schema/DBMS.

Một audit table thường có composite key liên quan `entity ID + revision`. Với composite entity ID, cần xem chính xác cột khóa. Với ValidityAuditStrategy, index trên end-revision/range có thể cần thiết cho truy vấn interval.

Khi query history chậm, hãy đo:

- SQL Envers thực sinh ra.
- Execution plan và index usage.
- Audit rows trên một entity.
- Total audit table size và skew.
- Number of historical association fetches.
- Connection pool wait, query time và memory.

Một index cho current table `purchase_orders` không nhất thiết giúp query trên `purchase_orders_AUD`.

## 36. Số SQL và N+1 khi dựng historical associations

Nếu API:

```java
List<PurchaseOrder> snapshots = ...;
for (PurchaseOrder order : snapshots) {
    System.out.println(order.getCustomer().getName());
}
```

có thể làm phát nhiều truy vấn audit cho Customer hoặc join tables. Đây là dạng N+1 của đường đọc lịch sử.

Giải pháp không phải bật `EAGER` cho mọi association:

1. Chỉ trả DTO fields cần thiết.
2. Phân trang timeline, không load mọi revisions.
3. Batch nhiều lookups phù hợp hoặc thiết kế projection theo use case.
4. Nếu cần đọc graph lớn, đo query counts và thiết kế cách hydrate riêng.
5. Với historical reports lớn, có thể cần read model/ETL ngoài endpoint tương tác.

Audit query performance thường khác current entity query performance; dữ liệu lịch sử dài theo thời gian và nhiều bản ghi sửa lặp cùng entity.

## 37. Read cache và lịch sử

Hibernate first-level cache giúp quản lý entities trong một persistence context, còn Envers có cơ chế caching/identity riêng ở đường đọc audit. Không nên dựa vào cùng một giả định rằng current entity trong Hibernate L2 cache có thể thay thế historical snapshot.

Một `PurchaseOrder` hiện tại với status PAID không thể dùng để phục vụ yêu cầu revision 1 khi status là DRAFT.

Nếu ứng dụng đặt Spring Cache quanh historical DTOs:

```java
@Cacheable(cacheNames = "order-history-view", key = "#id + ':' + #revision")
public OrderRevisionView read(Long id, long revision) {
    // ...
}
```

Đây là ví dụ ý tưởng; phải quyết định:

- Cache key bao gồm tenant/security scope nếu cần.
- Có lưu kết quả chưa được authorization kiểm tra không?
- Có trường hợp history bị sửa/backfill/migrate khiến cache stale?
- Cache không được vô tình chia sẻ snapshot nhạy cảm giữa các tenants/users.
- Dữ liệu lịch sử thường bất biến theo nghĩa audit, nhưng retention/redaction policy có thể yêu cầu xóa khỏi cache.

Không mặc định dùng `@Cacheable` với mọi lịch sử; trước hết đo tần suất đọc lại cùng revision và memory cost.

## 38. Tính bất biến và những gì Envers không chứng minh

Audit tables có thể cung cấp bằng chứng về thay đổi đã đi qua Hibernate; nhưng Envers không mặc nhiên tạo một tamper-proof ledger có chữ ký mật mã hay ngăn DBA sửa trực tiếp bảng audit.

Nếu hệ thống có yêu cầu pháp lý nghiêm ngặt:

- Bảo vệ permissions trên audit tables.
- Ghi rõ người thực hiện/nguồn thay đổi bằng custom revision metadata khi phù hợp.
- Có retention/archival policy.
- Cân nhắc immutable storage, signatures hoặc external audit trails.
- Giám sát DDL/direct SQL vào history tables.
- Kiểm thử khả năng khôi phục và đối chiếu.

`AuditReader.find()` giải quyết truy vấn trạng thái trong dữ liệu audit; tính toàn vẹn kiểm toán ở mức pháp lý còn phụ thuộc kiến trúc và vận hành.

## 39. Custom revision entity để biết ai thay đổi

Khi cần hiển thị “ai đã tạo revision?”, Envers cho phép custom revision entity.

Ví dụ:

```java
@Entity
@RevisionEntity(AuditRevisionListener.class)
public class AuditRevision {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    private String actor;

    public void setActor(String actor) {
        this.actor = actor;
    }
}
```

Revision listener:

```java
public class AuditRevisionListener implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevision revision = (AuditRevision) revisionEntity;
        String actor = AuditActorContext.currentActorOrSystem();
        revision.setActor(actor);
    }
}
```

`AuditActorContext` trong ví dụ là một abstraction của ứng dụng, không phải class có sẵn của Envers. Nó cần cung cấp actor đáng tin cậy ở HTTP requests, background jobs và message consumers. Tránh lưu raw tokens hoặc thông tin nhạy cảm không cần thiết vào revision table.

Sau đó có thể đọc:

```java
AuditRevision metadata = reader.findRevision(
    AuditRevision.class, revision);
```

Không cần tạo custom revision entity chỉ để đọc entity ở một revision. Nó hữu ích khi yêu cầu provenance/audit metadata ngoài ID và thời gian.

## 40. Entity history khi đổi schema

Giả sử revision cũ lưu:

```text
order status = NEW
```

Sau nhiều phiên bản, enum trong Java bỏ `NEW` và chỉ còn `DRAFT`, `CONFIRMED`. Hibernate có thể không deserialize đúng historical value `NEW`.

Các thay đổi schema/mapping cần xem xét:

- Đổi tên cột/bảng audit.
- Đổi enum values.
- Đổi converter hoặc column SQL type.
- Tách entity thành nhiều bảng hay đổi inheritance mapping.
- Đổi loại identifier.
- Đổi cách mapping association.
- Thêm NOT NULL constraint cho audit rows cũ.

Hãy migration audit schema cùng với current schema và thiết kế backward compatibility. Với enum dữ liệu lịch sử, có thể duy trì mapping hợp lệ hoặc migrate historical representation theo quy trình có kiểm soát.

**Đọc audit cũ thành công là một hợp đồng cần kiểm thử sau khi nâng cấp**, không chỉ kiểm tra ứng dụng ghi dữ liệu mới.

## 41. Kiểm thử AuditReader.find() với nhiều transactions

Test cần chứng minh đúng semantics tại revision, không chỉ entity hiện tại đúng.

Một kịch bản:

1. Transaction A: tạo Order #10, commit.
2. Transaction B: sửa Order #10 sang CONFIRMED, commit.
3. Transaction C: sửa một entity khác được audit, commit.
4. Đọc danh sách revisions của Order #10.
5. Assert Order #10 tại revision B và revision C có cùng state CONFIRMED.
6. Transaction D: Order #10 sang PAID, commit.
7. Assert các snapshots ở A, B, D khác nhau đúng như dữ liệu.

```text
After transaction A: Order #10 = DRAFT
After transaction B: Order #10 = CONFIRMED
After transaction C: only Customer changed
After transaction D: Order #10 = PAID

Assertions:
  find(Order #10, revisionA).status == DRAFT
  find(Order #10, revisionB).status == CONFIRMED
  find(Order #10, revisionC).status == CONFIRMED
  find(Order #10, revisionD).status == PAID
```

Không hard-code rằng revision IDs phải chính xác là 1, 2, 3, 4 nếu test suite có schema seeding, nhiều tests hoặc database đã có lịch sử. Đọc revision numbers thực tế rồi assert quan hệ giữa chúng.

## 42. Tránh một @Transactional test che mất revision boundaries

Trong Spring, `@DataJpaTest` thường chạy mỗi test trong một transaction có rollback sau test. Nếu tạo entity và sửa nó nhiều lần trong **cùng transaction**, rồi kỳ vọng có ba audit revisions độc lập, test đang sai thiết kế.

Envers thường tạo revision theo audited transaction, không theo mỗi `flush()` hoặc mỗi lời gọi setter. Để test lịch sử, cần thực hiện **nhiều transactions đã commit**.

Ví dụ dùng `TransactionTemplate`:

```java
@SpringBootTest
class PurchaseOrderHistoryIT {

    @Autowired
    TransactionTemplate tx;

    @PersistenceContext
    EntityManager em;

    @Test
    void readsTheStateAtEarlierRevision() {
        Long id = tx.execute(status -> {
            PurchaseOrder order =
                new PurchaseOrder("PO-TEST", new BigDecimal("100"));
            em.persist(order);
            em.flush();
            return order.getId();
        });

        List<Number> firstRevisions = tx.execute(status ->
            AuditReaderFactory.get(em)
                .getRevisions(PurchaseOrder.class, id));
        Number revisionCreated = firstRevisions.get(0);

        tx.executeWithoutResult(status -> {
            PurchaseOrder order =
                em.find(PurchaseOrder.class, id);
            order.confirm();
        });

        PurchaseOrder oldState = tx.execute(status ->
            AuditReaderFactory.get(em).find(
                PurchaseOrder.class, id, revisionCreated));

        assertEquals(OrderStatus.DRAFT, oldState.getStatus());
    }
}
```

Ví dụ giả định JUnit 5, Spring Boot Test, transaction infrastructure, schema audit và imports thích hợp. Test không đặt `@Transactional` bao trùm lên test method; `TransactionTemplate` tạo các transaction riêng. Nó vẫn cần fixture isolation và cleanup để không phụ thuộc vào dữ liệu test khác.

### 42.1. Đừng lấy revision khi transaction chưa commit

Sau khi `persist()` và `flush()` nhưng trước khi commit, audit work chưa nhất thiết có semantics “revision đã được mọi transaction khác đọc thấy”. Test/history API nên truy vấn các revisions đã commit bằng transaction độc lập, trừ khi chủ động kiểm tra behavior bên trong cùng transaction.

## 43. Kiểm thử deletion và thời gian revision

Một test deletion:

```text
TX 1: create Order
TX 2: update Order
TX 3: delete Order

Expect:
  Snapshot at TX 1 revision exists
  Snapshot at TX 2 revision exists
  Snapshot at TX 3 revision is absent
  Query including deleted entities finds DEL audit record
```

Một test timestamp:

```java
Date revisionDate = reader.getRevisionDate(revision);
assertNotNull(revisionDate);
```

Không assert một millisecond chính xác bằng cách so với `Instant.now()` nếu hệ thống chạy concurrent, database có precision khác hoặc việc tạo revision/commit bị trì hoãn. Chỉ xác định khoảng chấp nhận dựa trên clock và test environment.

## 44. Test hành vi khi entity không có audit history

Những trường hợp cần đưa vào integration tests:

| Tình huống | Điều cần xác nhận |
|---|---|
| Entity tạo sau revision yêu cầu | `find()` trả null |
| Entity bị hard delete | `find()` trước xóa có state; tại/sau xóa không còn |
| Entity chỉ dùng soft delete | Snapshot có cờ deleted thay vì biến mất |
| Revision sửa entity khác | `find()` vẫn trả state gần nhất của entity cần xem |
| Entity không có `@Audited` | API báo lỗi/không hỗ trợ theo Envers contract |
| Field `@NotAudited` | Không tự có lịch sử của field |
| Association target không audited | Xác nhận có đọc state hiện tại không |
| HQL bulk update | Không giả định có audit revision per entity |
| Database direct SQL | Không tự tạo Envers entries |
| User không có quyền xem lịch sử | Trả lỗi phù hợp, không lộ snapshot |
| Sai tenant | Không thấy history ngoài tenant |
| Audit schema migration | Đọc được cả old và new revisions |

Các test này giúp phát hiện chỗ mà lịch sử không bao phủ toàn bộ dữ liệu, thay vì chỉ chứng minh API đọc một case đơn giản.

## 45. Tối ưu API lịch sử có số revisions lớn

Với một tài khoản được sửa hàng nghìn lần, endpoint không nên:

```java
List<Number> all = reader.getRevisions(
    Customer.class, customerId);

for (Number r : all) {
    reader.find(Customer.class, customerId, r);
}
```

rồi trả mọi state về client. Cách này có thể gây nhiều queries và tăng memory.

Thay vào đó:

1. Trang timeline revisions theo mốc/limit.
2. Chỉ hiển thị metadata trong danh sách.
3. Khi user chọn một revision, gọi `find()` cho snapshot cụ thể.
4. Giới hạn associations và fields.
5. Có index phù hợp trên entity ID/revision.
6. Cân nhắc caching DTO cho những revision truy cập lặp nhiều và có authorization.

Ví dụ endpoint:

```text
GET /api/orders/10/revisions?limit=20&beforeRevision=600

GET /api/orders/10/revisions/587
```

Endpoint thứ nhất dùng AuditQuery để lấy metadata/timeline có giới hạn; endpoint thứ hai dùng AuditReader.find() để dựng snapshot.

## 46. Phân biệt “đọc hiện tại” và “đọc tại revision”

| Câu hỏi | API phù hợp | Kết quả |
|---|---|---|
| Order hiện tại có trạng thái gì? | `EntityManager.find(Order.class,id)` | Current DB/entity state |
| Order tại revision 14 có trạng thái gì? | `AuditReader.find(Order.class,id,14)` | Historical state as-of revision |
| Order thay đổi ở những revisions nào? | `AuditReader.getRevisions(Order.class,id)` | Danh sách mốc có audit entry |
| Một revision xảy ra khi nào? | `AuditReader.getRevisionDate(rev)` | Revision timestamp metadata |
| Ai tạo revision? | `findRevision(CustomRevisionEntity.class,rev)` | Custom revision metadata |
| Order có thay đổi đúng rev 14 không? | AuditQuery với `revisionNumber().eq(14)` | Rows thay đổi đúng rev |
| Muốn xem deletion entry? | AuditQuery có `selectDeletedEntities=true` | Audit row với `RevisionType.DEL` |
| Muốn phục hồi state cũ? | Business command ghi revision mới | Không phải gọi `merge()` trực tiếp trên historical object |

## 47. Những lỗi dễ gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `AuditReader.find()` luôn null | Entity chưa được audit, không có historical state tại mốc, sai ID/revision/EMF | Kiểm tra `@Audited`, audit data và revision timeline |
| Đọc revision 4 nhưng entity chỉ có [1,3] | Hiểu nhầm revision là lần sửa riêng của entity | `find()` dùng state gần nhất ở hoặc trước mốc |
| Đọc sau xóa ra null | `DEL` là deletion, không phải live state | AuditQuery xem deletion record |
| Không thấy value của field | Field `@NotAudited` hoặc mapping/schema khác | Xác định audit scope, không suy ra lịch sử ngoài phạm vi |
| Association hiển thị tên mới | Target được cấu hình not audited/current resolution | Audit target hoặc lưu snapshot value |
| `LazyInitializationException` | Graph lịch sử được truy cập ngoài persistence context | DTO trong read transaction |
| Không có revision mới sau native UPDATE | Bulk/JDBC bypass ORM audit listeners | Thiết kế audit mechanism khác |
| Chỉ thấy một revision sau nhiều flush | Cùng một transaction audit | Dùng nhiều committed transactions để test |
| `ClassCastException` ở revision metadata | Assumed `DefaultRevisionEntity` nhưng dùng custom entity | Dùng đúng revision class |
| History query rất chậm | Audit table lớn, thiếu index, N+1 | EXPLAIN, indexes, pagination và DTO |
| 404 cho revision có thật | Trộn `getRevisions()` với as-of semantics | Dùng `find()` để đọc state tại R |
| Lộ lịch sử tenant khác | Thiếu authorization/tenant scope trong read path | Kiểm tra security và DB RLS/filters thực tế |
| Current entity bị ghi đè | Merge nhầm historical object | Dùng business restore command |
| Mismatch sau nâng version | Schema/enum/converter của audit data chưa migrate | Migration và backward-compatibility tests |

## 48. Quy trình đọc một historical entity an toàn

**Bước 1 — Xác định entity và identifier.** Entity phải nằm trong persistence unit có Envers audit.

**Bước 2 — Xác định revision.** Revision number dương do API/client hoặc một timeline đã được kiểm chứng cung cấp.

**Bước 3 — Kiểm tra quyền truy cập.** Không chỉ xem quyền của current entity; lịch sử có thể có dữ liệu nhạy cảm đã bị xóa.

**Bước 4 — Mở read transaction phù hợp.** Dùng EntityManager/Session đúng Hibernate provider và persistence unit.

**Bước 5 — Lấy reader.** `AuditReader reader = AuditReaderFactory.get(em);`.

**Bước 6 — Đọc snapshot.** `reader.find(EntityClass.class, id, revision);`.

**Bước 7 — Xử lý null rõ ràng.** Entity có thể chưa được tạo, đã hard delete hoặc không có state hiệu lực ở mốc ấy.

**Bước 8 — Giới hạn graph.** Chỉ lấy field/association thực sự cần; không serialize nguyên entity qua REST.

**Bước 9 — Trả DTO.** Đính kèm requested revision, revision metadata nếu phù hợp, và thông tin về source/freshness theo API contract.

**Bước 10 — Kiểm thử.** Multi-transaction revisions, deletion, association, security, schema migration và hiệu năng trên DBMS đích.

## 49. Sơ đồ lựa chọn API Envers

```text
                      Cần xem lịch sử entity?
                                |
                                v
                    Muốn trạng thái tại revision R?
                         /                 \
                        CÓ                 KHÔNG
                        |                    |
                        v                    v
               AuditReader.find()    Muốn các lần thay đổi?
                        |                /           \
                        v              CÓ            KHÔNG
                  Snapshot null?        |              |
                    /     \             v              v
                   CÓ     KHÔNG   getRevisions()   Metadata thời gian?
                   |       |             |              |
                   v       v             v              v
               Chưa tạo/  Dựng DTO    AuditQuery        getRevisionDate()
               đã xóa    an toàn     nếu cần details   findRevision()
                   \       /             |              |
                    \     /              |              |
                     v   v               v              v
                    Authorization / tenant isolation
                                |
                                v
                        Transaction/read consistency
                                |
                                v
                        Response giới hạn dữ liệu
```

## 50. Tổng kết

`AuditReader.find(EntityClass.class, entityId, revision)` là API trọng tâm của Hibernate Envers để **đọc trạng thái của một audited entity tại một revision**. Revision là một mốc audit trong phạm vi cơ chế Envers, không phải lần sửa thứ N của từng entity và không phải `@Version`. Vì thế, `find()` có thể trả snapshot hợp lệ tại revision mà entity đó không trực tiếp thay đổi: nó sử dụng state gần nhất còn hiệu lực ở hoặc trước revision được hỏi.

Nếu entity chưa được tạo hoặc đã hard delete ở revision yêu cầu, `find()` thường trả null. Muốn xem lần thay đổi, deletion entry hoặc metadata, dùng `getRevisions()`, `getRevisionDate()`, `findRevision()` và AuditQuery API phù hợp. Với associations, non-audited targets và `@NotAudited` fields, historical snapshot chỉ phản ánh phạm vi lịch sử thực sự được lưu.

Trong Spring Boot, nên đọc Envers trong một service có transaction đọc, lấy AuditReader từ `EntityManager` đúng persistence unit và chuyển historical object sang DTO trước khi trả API. Đừng `merge()` state cũ trực tiếp vào current entity để “khôi phục”. Việc restore phải là business command có version checks và tạo thay đổi mới.

Cuối cùng, Envers chỉ phản ánh những thay đổi mà cơ chế audit ghi được: bulk HQL/native SQL và writers ngoài Hibernate không tự tạo audit rows. Hãy kiểm tra security/tenant isolation, schema migration, index/performance, nhiều committed transactions và delete behavior bằng integration tests thực tế.

**Nguyên tắc cần nhớ:** Đọc state tại revision là một truy vấn “as-of” trên lịch sử đã được Envers ghi nhận, không phải truy vấn bảng hiện tại và cũng không phải tìm đúng một audit row ở số revision đó.
