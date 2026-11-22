# Quan sát vòng đời thực thể qua Session và SQL được sinh

Hibernate quản lý entity trong một persistence context gắn với `Session`. Khi một object chuyển từ transient sang persistent, được sửa, detach hoặc remove, Hibernate ghi nhận những thay đổi đó và quyết định thời điểm gửi SQL xuống database. Quan sát đồng thời object state và SQL giúp giải thích Hibernate đang làm gì, vì sao một câu lệnh xuất hiện muộn hơn lời gọi API, và vì sao đọc lại entity đôi khi không tạo SELECT.

Bài thực hành này theo dõi một entity xuyên suốt vòng đời: tạo mới, persist, tìm kiếm, sửa, flush, clear, detach, merge, refresh, remove, commit và rollback. Bạn sẽ bật SQL logging, xem bind parameters, dùng Session/SessionFactory statistics và đối chiếu kết quả bằng JDBC hoặc một Session mới.

Sau bài này, bạn có thể:

- Phân biệt trạng thái transient, persistent, detached và removed.
- Nhận biết vai trò của Session, SessionFactory và persistence context.
- Dự đoán thao tác nào tạo INSERT, SELECT, UPDATE và DELETE.
- Giải thích dirty checking, flush, commit và rollback.
- Quan sát SQL và bind values do Hibernate sinh.
- Phân biệt dữ liệu trong object Java, first-level cache và database.
- Dùng log và statistics để tìm hiểu lazy loading, N+1 và batching.

---

## 1. Bối cảnh thực hành

Ta dùng một ứng dụng nhỏ quản lý đơn hàng. Một PurchaseOrder có mã, trạng thái, tổng tiền và danh sách OrderLine. Phần đầu chỉ thao tác PurchaseOrder; phần sau mở rộng sang quan hệ.

### 1.1. Entity mẫu

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false, precision = 12, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            String status,
            BigDecimal totalAmount) {
        this.orderNumber = orderNumber;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public void changeStatus(String status) {
        this.status = status;
    }

    public void changeTotal(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Các điểm cần chú ý:

- Entity có no-argument constructor với visibility phù hợp để provider tạo instance.
- `@Id` xác định identity trong persistence context.
- `GenerationType.IDENTITY` yêu cầu database sinh ID khi INSERT. Hibernate thường phải thực hiện INSERT sớm để lấy generated key.
- `orderNumber` có unique constraint và không nullable.
- Các method thay đổi field giúp ví dụ thể hiện dirty checking mà không cần setter công khai.

Ví dụ dùng Jakarta Persistence imports phù hợp các bản Hibernate hiện đại. Ứng dụng dùng Hibernate/JPA cũ có thể còn dùng namespace `javax.persistence`; hãy thống nhất namespace với dependency của dự án.

### 1.2. SessionFactory và Session

- `SessionFactory` là đối tượng nặng, thread-safe, thường tạo một lần khi ứng dụng khởi động và đóng khi ứng dụng dừng.
- `Session` đại diện cho một persistence context/unit of work. Nó không thread-safe và thường được mở cho một request, transaction hoặc tác vụ ngắn.
- Persistence context giữ managed entities, identity map và snapshot cần cho dirty checking.
- `Transaction` xác định ranh giới commit/rollback của công việc database.

```text
Application
    |
    v
SessionFactory (shared, long-lived)
    |
    +---- openSession() ----> Session A
    |                           |
    |                           +-- persistence context
    |                           +-- Transaction A
    |                           +-- managed entities
    |
    +---- openSession() ----> Session B
                                |
                                +-- persistence context riêng
                                +-- Transaction B
                                +-- managed entities riêng
```

Hai Session độc lập có thể cùng load một row nhưng giữ hai Java instances khác nhau. Thay đổi trong Session A không tự cập nhật object đang nằm trong Session B.

---

## 2. Bật SQL logging trước khi chạy lab

Muốn quan sát Hibernate sinh SQL, cần bật log ở tầng SQL và bind parameters. Thuộc tính show_sql có thể in SQL nhanh, nhưng logger linh hoạt hơn vì cho phép chọn mức log và đưa output vào test report.

### 2.1. Cấu hình properties

Ví dụ cấu hình Hibernate 6 với H2 trong môi trường local:

```properties
hibernate.connection.driver_class=org.h2.Driver
hibernate.connection.url=jdbc:h2:mem:lifecycle;DB_CLOSE_DELAY=-1
hibernate.connection.username=sa
hibernate.connection.password=

hibernate.dialect=org.hibernate.dialect.H2Dialect
hibernate.hbm2ddl.auto=create-drop

hibernate.show_sql=false
hibernate.format_sql=true
hibernate.highlight_sql=false
hibernate.use_sql_comments=true

hibernate.generate_statistics=true
```

Nếu ứng dụng dùng Spring Boot, có thể đặt các thuộc tính tương ứng dưới `spring.jpa.properties.*` trong cấu hình test. Không cấu hình database in-memory nếu mục tiêu là so sánh dialect/behavior production; dùng database engine phù hợp khi cần kiểm tra SQL đặc thù.

### 2.2. Logback logger

Với Hibernate 6, các logger thường hữu ích:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.hibernate.SQL" level="DEBUG"/>
    <logger name="org.hibernate.orm.jdbc.bind" level="TRACE"/>
    <logger name="org.hibernate.orm.jdbc.extract" level="TRACE"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

- `org.hibernate.SQL`: câu SQL Hibernate gửi qua JDBC.
- `org.hibernate.orm.jdbc.bind`: giá trị bind vào parameter marker `?`.
- `org.hibernate.orm.jdbc.extract`: dữ liệu được đọc từ ResultSet; hữu ích khi debug nhưng có thể tạo log rất lớn.

Logger category có thể khác giữa các phiên bản Hibernate. Nếu không thấy bind values, kiểm tra version và logging backend trước khi kết luận Hibernate không bind parameter.

### 2.3. So sánh các cách quan sát

| Cách | Mục đích | Hạn chế |
|---|---|---|
| `hibernate.show_sql` | In SQL nhanh ra console | Ít khả năng lọc theo logger |
| `org.hibernate.SQL` | Thu SQL qua logging framework | Cần cấu hình logger |
| `org.hibernate.orm.jdbc.bind` | Quan sát bind values | Có thể lộ dữ liệu nhạy cảm |
| `hibernate.generate_statistics` | Đếm entity/query/collection activity | Không thay thế SQL log chi tiết |

Chỉ bật bind logging trong môi trường phát triển hoặc test có dữ liệu an toàn. Parameter có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Không để TRACE bind parameters tồn tại tùy tiện ở production.

---

## 3. Khởi tạo SessionFactory

Một bootstrap đơn giản bằng Hibernate native API:

```java
StandardServiceRegistry registry =
    new StandardServiceRegistryBuilder()
        .applySetting("hibernate.connection.driver_class", "org.h2.Driver")
        .applySetting(
            "hibernate.connection.url",
            "jdbc:h2:mem:lifecycle;DB_CLOSE_DELAY=-1"
        )
        .applySetting("hibernate.connection.username", "sa")
        .applySetting("hibernate.connection.password", "")
        .applySetting("hibernate.dialect", "org.hibernate.dialect.H2Dialect")
        .applySetting("hibernate.hbm2ddl.auto", "create-drop")
        .applySetting("hibernate.show_sql", "false")
        .applySetting("hibernate.generate_statistics", "true")
        .build();

SessionFactory sessionFactory = new MetadataSources(registry)
    .addAnnotatedClass(PurchaseOrder.class)
    .buildMetadata()
    .buildSessionFactory();
```

Imports bootstrap có thể thay đổi nhẹ theo Hibernate version. Trong ứng dụng thật, giữ SessionFactory ở application scope và đóng đúng lifecycle:

```java
try {
    // Run application or integration tests.
} finally {
    sessionFactory.close();
    StandardServiceRegistryBuilder.destroy(registry);
}
```

Không mở một SessionFactory cho mỗi repository call. Việc tạo factory tốn chi phí vì Hibernate phải xử lý mapping metadata, services, connection provider và nhiều thành phần dùng chung.

---

## 4. Các trạng thái entity và thao tác Session

Một entity thường đi qua bốn trạng thái:

| Trạng thái | Mô tả | Session theo dõi? |
|---|---|---|
| Transient | Object mới, chưa được persist | Không |
| Persistent / managed | Object gắn với persistence context hiện tại | Có |
| Detached | Object từng managed nhưng không còn gắn với context | Không |
| Removed | Managed object được đánh dấu xóa, chờ đồng bộ | Có |

Các thao tác phổ biến trong Hibernate Session:

| API | Tác động chính |
|---|---|
| `session.persist(entity)` | Đưa entity mới vào managed state |
| `session.find(Entity.class, id)` | Tìm entity, có thể lấy từ first-level cache |
| `session.get(Entity.class, id)` | API Hibernate để lấy entity theo ID; đối chiếu semantics theo version |
| `session.remove(entity)` | Đánh dấu entity managed để xóa |
| `session.detach(entity)` | Detach một entity |
| `session.clear()` | Detach toàn bộ managed entities |
| `session.merge(entity)` | Copy state vào managed instance và trả instance đó |
| `session.refresh(entity)` | Reload state của managed entity từ database |
| `session.flush()` | Đồng bộ pending changes thành SQL |
| `session.contains(entity)` | Kiểm tra entity có managed trong Session này không |

Trong Hibernate native API, Session cung cấp các khả năng tương ứng với JPA EntityManager. Chọn một API style nhất quán trong một đoạn code để người đọc dễ nhận ra lifecycle đang được thao tác qua abstraction nào.

---

## 5. Lab 1 — Tạo entity và persist

Bắt đầu với một object Java thuần:

```java
PurchaseOrder order = new PurchaseOrder(
    "PO-1001",
    "NEW",
    new BigDecimal("125.50")
);
```

Tại thời điểm này object là transient. Hibernate chưa biết nó tồn tại.

Mở Session và transaction:

```java
Long orderId;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder order = new PurchaseOrder(
        "PO-1001",
        "NEW",
        new BigDecimal("125.50")
    );

    System.out.println("before persist: " + session.contains(order));

    session.persist(order);

    System.out.println("after persist: " + session.contains(order));
    orderId = order.getId();

    tx.commit();
}
```

Kết quả quan sát:

- Trước persist, `session.contains(order)` trả false.
- Sau persist, instance truyền vào là managed trong Session đó.
- Với IDENTITY, Hibernate thường INSERT sớm để lấy ID; thời điểm chính xác còn phụ thuộc provider/dialect và batching.
- Commit hoàn tất transaction. Session được đóng khi ra khỏi try-with-resources.

SQL có dạng minh họa:

```sql
insert into purchase_order
    (order_number, status, total_amount, id)
values
    (?, ?, ?, default)
```

Dialect thực tế có thể sinh cú pháp khác, chẳng hạn omit cột identity hoặc dùng returning/generated keys. Không hard-code một SQL string làm hợp đồng cho mọi database.

Bind values có thể trông như:

```text
binding parameter (1:VARCHAR) <- [PO-1001]
binding parameter (2:VARCHAR) <- [NEW]
binding parameter (3:NUMERIC) <- [125.50]
```

Log thực tế có format phụ thuộc Hibernate version. Điều quan trọng là tách câu SQL với các giá trị bind.

### 5.1. Vì sao không nối giá trị trực tiếp vào SQL?

Hibernate dùng prepared statements và bind parameters:

```sql
insert into purchase_order (order_number, status, total_amount)
values (?, ?, ?)
```

Các parameter marker giúp driver xử lý kiểu dữ liệu và tránh việc tự nối chuỗi tạo SQL không an toàn. Khi debug, bind logger giúp nhìn giá trị thực được gửi mà không cần biến SQL thành chuỗi literal.

### 5.2. IDENTITY và sequence

Với IDENTITY, Hibernate thường cần INSERT để database trả generated key. Với sequence, Hibernate có thể lấy sequence value trước và trì hoãn INSERT tới flush/commit. Vì vậy đừng suy luận entity chưa được persist chỉ vì chưa thấy INSERT ngay sau API call.

---

## 6. Lab 2 — find và first-level cache

Mở Session mới và load order:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder first =
        session.find(PurchaseOrder.class, orderId);

    PurchaseOrder second =
        session.find(PurchaseOrder.class, orderId);

    System.out.println(first == second); // true
    System.out.println(session.contains(first)); // true

    tx.commit();
}
```

Ở lần find đầu, Hibernate thường cần SELECT nếu entity chưa có trong persistence context. Lần find thứ hai với cùng ID trong cùng Session thường trả cùng Java instance và không phát SELECT thứ hai.

SQL lần đầu có dạng:

```sql
select
    po1_0.id,
    po1_0.order_number,
    po1_0.status,
    po1_0.total_amount
from purchase_order po1_0
where po1_0.id = ?
```

### 6.1. First-level cache là gì?

First-level cache là persistence context của Session. Nó bảo đảm identity trong phạm vi Session: cùng entity type và identifier thường map tới cùng managed instance.

Nó không phải một cache tùy chọn để bật/tắt. Nó là một phần cốt lõi của Session.

### 6.2. Thay đổi object không tạo SELECT mới

```java
PurchaseOrder order =
    session.find(PurchaseOrder.class, orderId);

order.changeStatus("PROCESSING");

PurchaseOrder same =
    session.find(PurchaseOrder.class, orderId);

assert same == order;
assert "PROCESSING".equals(same.getStatus());
```

Không có lý do để Hibernate SELECT lại row chỉ vì field trong Java object vừa thay đổi. Session đã quản lý instance đó.

### 6.3. Session khác có persistence context khác

```java
try (Session sessionA = sessionFactory.openSession();
     Session sessionB = sessionFactory.openSession()) {

    PurchaseOrder a =
        sessionA.find(PurchaseOrder.class, orderId);

    PurchaseOrder b =
        sessionB.find(PurchaseOrder.class, orderId);

    System.out.println(a == b); // false
}
```

Hai object có thể đại diện cùng row nhưng là hai Java instances riêng. Khi cả hai cùng sửa một row, cần transaction/locking/version strategy để xử lý concurrency.

---

## 7. Lab 3 — Dirty checking và UPDATE

Dirty checking là cơ chế Hibernate so sánh managed entity state với snapshot hoặc cơ chế tracking tương ứng để phát hiện thay đổi.

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder order =
        session.find(PurchaseOrder.class, orderId);

    order.changeStatus("PROCESSING");
    order.changeTotal(new BigDecimal("140.00"));

    System.out.println(session.contains(order)); // true

    tx.commit();
}
```

Không cần gọi update cho một entity đã managed. Hibernate theo dõi thay đổi và phát UPDATE khi flush.

SQL minh họa:

```sql
update purchase_order
set order_number = ?,
    status = ?,
    total_amount = ?
where id = ?
```

Hibernate có thể chỉ update những cột dirty tùy DynamicUpdate, mapping và configuration. SQL cụ thể có thể gồm nhiều cột hơn field vừa đổi; đừng suy luận số field đổi bằng số cột trong UPDATE nếu chưa xem mapping.

### 7.1. Khi nào UPDATE xuất hiện?

Thường ở một trong các điểm:

- Khi gọi session.flush().
- Trước một query cần auto-flush theo flush mode/query spaces.
- Khi transaction commit kích hoạt flush.

Gán field không nhất thiết phát SQL ngay:

```java
order.changeStatus("SHIPPED");
// Thường chưa có UPDATE ở đúng dòng này.
session.flush();
// Hibernate đồng bộ thay đổi xuống JDBC tại đây.
```

### 7.2. Explicit flush

```java
order.changeStatus("SHIPPED");

session.flush();

System.out.println("SQL đã được đồng bộ trong transaction");
```

Sau flush, database connection đã nhận câu UPDATE trong transaction hiện tại. Nhưng transaction vẫn có thể rollback. Flush không tương đương commit.

### 7.3. Auto-flush trước query

Với flush mode AUTO, Hibernate có thể flush pending changes trước query nếu query có thể bị ảnh hưởng bởi các thay đổi đó.

```java
order.changeStatus("READY");

List<PurchaseOrder> readyOrders = session.createQuery(
    "from PurchaseOrder p where p.status = :status",
    PurchaseOrder.class
).setParameter("status", "READY")
 .getResultList();
```

Trước khi chạy query, Hibernate có thể flush thay đổi để kết quả query phản ánh state nhất quán. Không dùng thứ tự log giữa UPDATE và SELECT làm quy tắc bất biến cho mọi flush mode/provider version.

---

## 8. Lab 4 — clear và detach

### 8.1. Detach một entity

```java
PurchaseOrder order =
    session.find(PurchaseOrder.class, orderId);

session.detach(order);

System.out.println(session.contains(order)); // false

order.changeStatus("LOCAL_ONLY");

session.flush();
```

Sau detach, Session không còn dirty-check object đó. Thay đổi LOCAL_ONLY không tự được persist bởi Session này.

Để quan sát database, clear context rồi load lại:

```java
session.clear();

PurchaseOrder reloaded =
    session.find(PurchaseOrder.class, orderId);

System.out.println(reloaded.getStatus());
```

Nếu transaction đã có thay đổi khác cần giữ, hãy flush trước khi clear. clear() không rollback SQL đã flush.

### 8.2. Clear toàn bộ persistence context

```java
session.clear();
```

clear() detach toàn bộ managed entities trong Session. Object references vẫn còn trong Java code nhưng Hibernate không còn quản lý chúng.

### 8.3. SQL được sinh khi detach/clear?

Bản thân detach/clear không yêu cầu UPDATE hoặc DELETE. Chúng thay đổi trạng thái quản lý trong memory.

Nếu có thay đổi managed entity trước detach nhưng chưa flush, thay đổi đó không tự được đồng bộ sau khi entity đã detached. Nếu đã flush, SQL vẫn thuộc transaction và có thể commit/rollback.

---

## 9. Lab 5 — merge một detached entity

Giả sử load entity trong Session A, đóng Session đó, sau đó sửa detached object:

```java
PurchaseOrder detached;

try (Session session = sessionFactory.openSession()) {
    detached = session.find(PurchaseOrder.class, orderId);
}

// Session đóng; detached không còn managed.
detached.changeStatus("REOPENED");
```

Mở Session B và merge:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder managed = session.merge(detached);

    System.out.println(session.contains(managed)); // true
    System.out.println(session.contains(detached)); // false
    System.out.println(managed == detached); // thường false

    tx.commit();
}
```

merge() copy state từ input vào một managed instance trong context đích và trả instance managed đó. Input vẫn detached.

SQL có thể bao gồm SELECT để lấy managed instance hiện có và UPDATE khi flush nếu state khác. SQL chính xác phụ thuộc entity state, identifier, version, unsaved-value detection, cascade và provider version.

**Luôn dùng giá trị trả về của merge.** Sửa tiếp detached input sau khi merge không tự được dirty-check trong Session B.

### 9.1. Merge không phải PATCH

Nếu detached object được tạo từ DTO thiếu fields, các field không được gửi có thể trở thành null/default. Merge có thể copy những giá trị đó vào managed state.

Trong ứng dụng cập nhật một phần, thường load entity managed trong transaction rồi apply những field caller được phép thay đổi. Dùng merge cho một object graph không đầy đủ có thể gây ghi đè ngoài ý muốn.

### 9.2. Merge và version

Nếu entity có @Version, Hibernate dùng version để phát hiện stale updates. Merge một detached instance từ version cũ sau khi transaction khác đã commit có thể dẫn đến optimistic locking failure ở merge, flush hoặc commit.

---

## 10. Lab 6 — refresh và đọc lại từ database

Giả sử một entity managed đã có local changes:

```java
PurchaseOrder order =
    session.find(PurchaseOrder.class, orderId);

order.changeStatus("LOCAL_EDIT");

session.refresh(order);

System.out.println(order.getStatus());
```

refresh() yêu cầu Session reload state của managed entity theo dữ liệu database mà transaction hiện tại nhìn thấy. Local changes chưa flush có thể bị ghi đè.

### 10.1. Quan sát SELECT

refresh() thường phát SELECT để tải lại entity:

```sql
select
    po1_0.id,
    po1_0.order_number,
    po1_0.status,
    po1_0.total_amount
from purchase_order po1_0
where po1_0.id = ?
```

Không dùng refresh trên detached entity để reattach. Nếu entity không managed, cần load lại trong Session phù hợp hoặc merge theo use case.

### 10.2. Refresh sau JDBC update

Một test có thể dùng JDBC cập nhật row rồi refresh managed entity:

```java
PurchaseOrder order =
    session.find(PurchaseOrder.class, orderId);

jdbcTemplate.update(
    "update purchase_order set status = ? where id = ?",
    "UPDATED_BY_JDBC",
    orderId
);

session.refresh(order);

assert "UPDATED_BY_JDBC".equals(order.getStatus());
```

JDBC và Hibernate phải dùng cùng transaction manager/connection khi ví dụ muốn cập nhật trong cùng transaction. Nếu transaction khác cập nhật, transaction hiện tại phải nhìn thấy commit đó theo isolation level. Với snapshot/repeatable-read isolation, refresh không đảm bảo vượt qua snapshot hiện tại.

---

## 11. Lab 7 — remove và DELETE

Load một managed entity rồi gọi remove:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder order =
        session.find(PurchaseOrder.class, orderId);

    session.remove(order);

    System.out.println(session.contains(order));

    tx.commit();
}
```

remove() đánh dấu entity managed để xóa. DELETE thường được thực hiện khi flush/commit, không nhất thiết ngay tại dòng gọi remove.

SQL minh họa:

```sql
delete from purchase_order
where id = ?
```

Nếu transaction rollback, DELETE không được commit. Nếu có foreign-key references, thứ tự DELETE hoặc constraint behavior phụ thuộc mapping/cascade và database.

### 11.1. Remove entity detached

JPA remove yêu cầu managed entity. Nếu có detached instance, load entity theo ID hoặc merge theo semantics cần thiết trước khi remove. Không dùng remove(detached) như cách xóa một object Java bất kỳ.

### 11.2. Kiểm tra sau remove

Sau transaction commit, mở Session mới và tìm lại:

```java
try (Session session = sessionFactory.openSession()) {
    PurchaseOrder deleted =
        session.find(PurchaseOrder.class, orderId);

    assert deleted == null;
}
```

Đây là kiểm tra bằng context mới. Không dùng một reference cũ đang nằm trong Session trước đó để kết luận row đã bị xóa.

---

## 12. Lab 8 — Rollback và object state

Một ví dụ quan trọng:

```java
PurchaseOrder order;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    order = session.find(PurchaseOrder.class, orderId);
    order.changeStatus("WILL_ROLLBACK");

    session.flush();

    tx.rollback();
}

// order vẫn là một Java object và có thể giữ "WILL_ROLLBACK".
System.out.println(order.getStatus());
```

Database transaction rollback hoàn tác UPDATE đã flush, nhưng Java object trong heap không tự được khôi phục về snapshot ban đầu. Session có thể không còn phù hợp để tiếp tục sử dụng sau rollback; đóng context và đọc bằng Session mới.

Xác minh database:

```java
try (Session session = sessionFactory.openSession()) {
    PurchaseOrder reloaded =
        session.find(PurchaseOrder.class, orderId);

    System.out.println(reloaded.getStatus());
}
```

Giá trị từ Session mới phản ánh database state đã commit. Đây là nguồn sự thật khi kiểm tra rollback.

### 12.1. Rollback trước flush và sau flush

| Tình huống | SQL đã gửi? | Database sau rollback |
|---|---|---|
| Sửa managed entity, rollback trước flush | Có thể chưa | Giữ state đã commit trước đó |
| Sửa, explicit flush, rồi rollback | Có | Giữ state đã commit trước đó |
| Insert rồi rollback | INSERT có thể đã chạy | Row mới không được commit |
| Delete rồi rollback | DELETE có thể đã chạy | Row vẫn tồn tại nếu trước transaction đã tồn tại |

Thời điểm SQL xuất hiện có thể khác nhưng transaction outcome cuối cùng mới quyết định dữ liệu có commit hay không.

### 12.2. Generated ID có thể có gap

Sequence và nhiều cơ chế identity không đảm bảo thu hồi số đã cấp sau rollback. Không viết test yêu cầu ID tiếp theo phải bằng ID vừa rollback cộng một.

---

## 13. Quan sát SQL với StatementInspector

SQL logger cho thấy câu lệnh được gửi. Nếu cần thu thập SQL trong code test, Hibernate cung cấp `StatementInspector`.

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class CollectingStatementInspector
        implements StatementInspector {

    private final List<String> statements =
        new CopyOnWriteArrayList<>();

    @Override
    public String inspect(String sql) {
        statements.add(sql);
        return sql;
    }

    public List<String> getStatements() {
        return List.copyOf(statements);
    }

    public void clear() {
        statements.clear();
    }
}
```

Đăng ký inspector khi bootstrap:

```java
CollectingStatementInspector inspector =
    new CollectingStatementInspector();

StandardServiceRegistry registry =
    new StandardServiceRegistryBuilder()
        .applySetting(
            "hibernate.session_factory.statement_inspector",
            inspector
        )
        // Các settings khác...
        .build();
```

StatementInspector nhận SQL string trước khi Hibernate gửi xuống JDBC. Nó không phải nơi để đọc parameter values đã bind; bind logger hoặc JDBC-level instrumentation phù hợp hơn cho mục đích đó.

Không sửa SQL trong inspector nếu chỉ muốn quan sát. Nếu thay đổi SQL, phải hiểu tác động tới parameter positions, dialect và caching.

### 13.1. Assert SQL theo mục tiêu

Một test có thể xác nhận thao tác persist tạo INSERT hoặc thao tác merge tạo SELECT/UPDATE trong một kịch bản cụ thể. Hạn chế assert toàn bộ SQL string vì alias, whitespace, column order và dialect có thể thay đổi theo Hibernate version.

Ưu tiên assert loại operation, table/column quan trọng hoặc dùng database state để xác nhận behavior. Nếu exact SQL là yêu cầu của native query, hãy test query đó riêng.

---

## 14. Quan sát Hibernate Statistics

Bật `hibernate.generate_statistics=true`, sau đó truy cập statistics từ SessionFactory:

```java
Statistics statistics =
    sessionFactory.getStatistics();

statistics.clear();

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    PurchaseOrder order =
        new PurchaseOrder(
            "PO-2001",
            "NEW",
            new BigDecimal("90.00")
        );

    session.persist(order);
    session.flush();

    tx.commit();
}

System.out.println(
    "entity inserts = " + statistics.getEntityInsertCount()
);
System.out.println(
    "entity updates = " + statistics.getEntityUpdateCount()
);
System.out.println(
    "entity deletes = " + statistics.getEntityDeleteCount()
);
System.out.println(
    "prepared statements = " + statistics.getPrepareStatementCount()
);
```

Các counters giúp nhìn tổng quan số entity inserts/updates/deletes, query executions, collection fetches và prepared statements. API statistics cụ thể có thể thay đổi theo Hibernate version.

### 14.1. Statistics không phải SQL trace

- Statistics cho biết số lượng/sự kiện ở mức tổng hợp.
- SQL logger cho biết statement text.
- Bind logger cho biết parameter values.
- Database query log/profiler cho biết hoạt động ở phía database.

Dùng kết hợp khi cần tìm nguyên nhân một hành vi. Reset statistics trước một đoạn test cô lập; nếu nhiều tests chạy song song trên cùng SessionFactory, counters có thể chứa hoạt động từ tests khác.

### 14.2. Entity counts và statement counts không nhất thiết bằng nhau

Một entity operation có thể cần nhiều statements do secondary tables, cascades, collection tables hoặc identifier generation. Một JDBC batch có thể gom nhiều DML statements vào batch. Đừng giả định một entity insert luôn bằng đúng một prepared statement trong mọi mapping.

---

## 15. Quan sát quan hệ và cascade

Mở rộng Order với OrderLine:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }
}
```

```java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String productCode, int quantity) {
        this.productCode = productCode;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Khi persist Order với cascade PERSIST/ALL, Hibernate có thể persist các OrderLine mới. Owning side là `OrderLine.order`, vì vậy helper `addLine` cập nhật cả collection và reference child.

SQL thường cần INSERT parent trước để có ID, rồi INSERT child với foreign key:

```sql
insert into purchase_order (...) values (...);
insert into order_line (order_id, product_code, quantity, ...) values (?, ?, ?, ...);
```

Thứ tự và cú pháp cụ thể phụ thuộc identifier strategy và database.

### 15.1. Thay đổi collection

Thêm một line vào managed Order và flush có thể tạo INSERT cho child. Xóa line khỏi collection với orphanRemoval có thể tạo DELETE cho child khi flush.

Nếu chỉ xóa khỏi collection inverse side mà không cập nhật owning side, FK có thể không thay đổi như mong muốn. Hãy đồng bộ cả hai phía trong domain helper.

### 15.2. Cascade không đồng nghĩa owning side

Cascade quyết định lifecycle operation có lan qua association hay không. Owning side quyết định nơi Hibernate lấy thông tin để ghi relationship/FK. Đây là hai khái niệm riêng biệt.

---

## 16. Quan sát lazy loading và N+1

Với association LAZY, Hibernate có thể trì hoãn SELECT cho đến khi code truy cập association.

```java
List<PurchaseOrder> orders = session.createQuery(
    "from PurchaseOrder",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu mỗi order có một collection chưa initialized, vòng lặp có thể phát thêm một SELECT cho từng order. Đây là mẫu N+1:

```text
1 query: load N orders
N queries: load lines for each order

total ~= 1 + N SELECT statements
```

SQL log cho thấy SELECT đầu tải orders, sau đó nhiều SELECT theo order_id. Statistics như collection fetch count hoặc prepared statement count hỗ trợ xác định pattern.

### 16.1. Cách quan sát có kiểm soát

- Reset statistics trước query.
- Chỉ load parent list.
- Ghi số prepared statements.
- Truy cập collection trong vòng lặp.
- Ghi counters lần nữa.
- So sánh với fetch join/entity graph/batch fetching.

### 16.2. Fetch join

```java
List<PurchaseOrder> orders = session.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines",
    PurchaseOrder.class
).getResultList();
```

Fetch join có thể giảm round trips cho một use case cụ thể. Cẩn thận khi phân trang parent cùng fetch một collection vì join làm nhân số rows và ảnh hưởng pagination semantics. Chọn fetch plan theo query/use case, không bật EAGER mọi association.

### 16.3. Batch fetching

Hibernate có thể gom lazy loads thành batches khi cấu hình `@BatchSize` hoặc default batch fetch size. SQL có thể chuyển từ nhiều câu SELECT một ID sang ít câu SELECT dùng `IN (?, ?, ...)`. Bind logger giúp nhìn danh sách ID được tải theo batch.

---

## 17. Quan sát batching khi insert nhiều entities

Một vòng lặp persist nhiều rows:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    for (int i = 1; i <= 100; i++) {
        session.persist(new PurchaseOrder(
            "BATCH-" + i,
            "NEW",
            new BigDecimal("10.00")
        ));

        if (i % 25 == 0) {
            session.flush();
            session.clear();
        }
    }

    tx.commit();
}
```

flush() gửi pending actions; clear() giải phóng managed entities khỏi persistence context. Pattern này giúp kiểm soát memory khi xử lý batch lớn.

Cấu hình JDBC batch size, ví dụ:

```properties
hibernate.jdbc.batch_size=25
hibernate.order_inserts=true
hibernate.order_updates=true
```

Batching phụ thuộc driver, dialect và identifier generator. IDENTITY generation thường hạn chế khả năng JDBC insert batching vì Hibernate cần kết quả generated key theo từng insert. Kiểm tra SQL/batch logs thay vì giả định chỉ cần đặt batch_size là mọi insert tự gom thành một batch.

Không gọi clear trước flush nếu còn pending changes cần được ghi. clear() detach các entity; pending changes chưa flush có thể không còn được context quản lý để đồng bộ.

---

## 18. First-level cache và second-level cache

### 18.1. First-level cache

First-level cache thuộc Session. Hai lần find cùng ID trong một Session thường trả cùng instance:

```java
PurchaseOrder a = session.find(PurchaseOrder.class, id);
PurchaseOrder b = session.find(PurchaseOrder.class, id);

assert a == b;
```

session.clear() loại managed instances khỏi first-level cache. Một lần find sau đó có thể phát SELECT mới, trừ khi provider có cache tầng khác đáp ứng.

### 18.2. Second-level cache

Second-level cache thuộc SessionFactory và có thể chia sẻ entity state giữa Sessions nếu được cấu hình và entity/region được cache. Một Session mới không đồng nghĩa chắc chắn database phải nhận SELECT.

Khi test cần xác nhận SQL database thực sự:

- Kiểm tra L2 cache có được bật không.
- Evict entity/region hoặc tắt cache cho test.
- Dùng SQL logger/Statistics.
- Đọc qua JDBC khi phù hợp.

Không nhầm session.clear() với evict L2 cache. Clear chỉ ảnh hưởng persistence context của Session hiện tại.

---

## 19. Bulk update và SQL không đi qua dirty checking từng entity

JPQL/HQL bulk DML tác động trực tiếp tới rows:

```java
int updated = session.createMutationQuery(
    "update PurchaseOrder p " +
    "set p.status = :status " +
    "where p.status = :oldStatus"
)
.setParameter("status", "EXPIRED")
.setParameter("oldStatus", "NEW")
.executeUpdate();
```

Bulk update không tải từng entity rồi dirty-check từng instance. Các managed instances đang tồn tại trong Session có thể stale sau bulk operation.

Một pattern an toàn là flush trước nếu có pending changes cần giữ, chạy bulk DML, rồi clear/refresh managed state liên quan trước khi tiếp tục dùng:

```java
session.flush();

int count = session.createMutationQuery(
    "update PurchaseOrder p set p.status = :status"
)
.setParameter("status", "ARCHIVED")
.executeUpdate();

session.clear();
```

Bulk DML có transaction semantics riêng và có thể bỏ qua entity callbacks/cascade/orphan removal như thao tác entity-by-entity. Kiểm thử riêng nếu ứng dụng dựa vào những behavior đó.

---

## 20. @Version và SQL optimistic locking

Thêm version column:

```java
@Version
private long version;
```

Khi entity được update, SQL thường bao gồm version cũ trong WHERE và tăng version:

```sql
update purchase_order
set status = ?, version = ?
where id = ? and version = ?
```

Nếu row đã được transaction khác cập nhật, affected row count có thể bằng 0. Hibernate nhận ra stale update và ném optimistic locking exception.

### 20.1. Cách quan sát

1. Mở Session A và Session B.
2. Cả hai load cùng Order/version.
3. A đổi trạng thái và commit.
4. B đổi trạng thái từ object stale rồi flush/commit.
5. Quan sát optimistic lock exception.
6. Mở Session C và đọc state thắng từ database.

Hai lần load trong cùng Session không mô phỏng concurrency vì first-level cache trả cùng managed instance.

---

## 21. Đọc SQL theo vòng đời: bảng tham chiếu

| Thao tác | Trạng thái trước | SQL có thể quan sát | Ghi chú |
|---|---|---|---|
| new PurchaseOrder(...) | Không có entity trong Session | Không | Object transient |
| session.persist(order) | Transient | INSERT có thể chạy sớm hoặc chờ flush | ID strategy ảnh hưởng timing |
| session.find(type, id) | Chưa có trong L1 | SELECT | Có thể hit L2 cache |
| find(type, id) lần hai | Đã managed | Thường không có SQL | Trả cùng instance |
| Sửa field managed | Managed | Chưa nhất thiết có SQL | Dirty checking ở flush |
| session.flush() | Có pending changes | INSERT/UPDATE/DELETE | Transaction chưa commit |
| commit() | Pending changes có thể còn | Flush nếu cần, rồi commit | Transaction kết thúc |
| detach(entity) | Managed | Không tự tạo DML | Ngừng dirty checking |
| clear() | Có managed entities | Không tự tạo DML | Detach toàn context |
| merge(detached) | Detached input | SELECT/INSERT/UPDATE tùy state | Dùng return value |
| refresh(managed) | Managed | SELECT | Ghi đè local state |
| remove(managed) | Managed | DELETE khi flush | Chờ transaction outcome |
| rollback() | Transaction active | Rollback trên connection | DB rollback; Java fields có thể giữ state mới |

Bảng là hướng dẫn dự đoán, không phải hợp đồng exact SQL. Generator, mapping, cascade, flush mode, cache, dialect và Hibernate version đều có thể thay đổi câu lệnh và thời điểm phát sinh.

---

## 22. Một kịch bản lab xuyên suốt

Chạy lần lượt các bước dưới đây với cùng một orderId. Mỗi bước mở Session mới nếu cần kiểm tra state sau transaction trước.

| Bước | Hành động | Quan sát mong đợi |
|---|---|---|
| 1 | Tạo object bằng new | Transient, chưa có SQL |
| 2 | persist() | Managed; INSERT theo ID strategy |
| 3 | find() cùng Session | Cùng instance, không SELECT lần hai |
| 4 | find() Session mới | SELECT hoặc cache hit |
| 5 | Đổi status trên managed object | Chưa nhất thiết có UPDATE |
| 6 | flush() | UPDATE được gửi trong transaction |
| 7 | Commit | Thay đổi được commit |
| 8 | Load, detach(), sửa field | Không dirty-check thay đổi sau detach |
| 9 | merge() vào Session khác | Managed copy; input vẫn detached |
| 10 | refresh() managed entity | SELECT và ghi đè local edits |
| 11 | remove() rồi commit | DELETE được commit |
| 12 | Load trong Session mới | Không còn row |
| 13 | Tạo/update rồi rollback | Database không giữ transaction changes |
| 14 | Đọc object reference cũ | Java object có thể vẫn chứa giá trị mới |
| 15 | Load bằng Session mới | Thấy database state đã commit |

### 22.1. Ghi lại quan sát

Với mỗi thao tác, ghi:

- Tên API đã gọi.
- session.contains(entity) trước và sau.
- entity.getId() và các field liên quan.
- Có gọi flush không.
- Transaction commit hay rollback.
- SQL statement được log.
- Bind values.
- Kết quả đọc bằng Session mới.

Ghi lại sequence theo từng transaction giúp xác định SQL thuộc thao tác nào.

---

## 23. Phân biệt log ORM với hoạt động database

Một dòng org.hibernate.SQL cho biết Hibernate đã chuẩn bị/gửi SQL qua JDBC, nhưng không tự chứng minh transaction đã commit. Một dòng bind logger cho biết parameter Hibernate bind; nó cũng không chứng minh row còn tồn tại sau rollback.

Để xác nhận kết quả:

1. Kết thúc transaction bằng commit hoặc rollback.
2. Đóng Session cũ.
3. Mở Session/transaction mới.
4. Load entity hoặc query row count.
5. Nếu cần, đọc trực tiếp bằng JDBC/DB console.
6. So sánh database state với object reference cũ.

Với database có read replicas, replication lag có thể làm một connection đọc replica thấy dữ liệu muộn hơn primary. Khi kiểm tra commit ngay lập tức, dùng datasource/connection phù hợp với consistency requirement.

---

## 24. Lỗi thường gặp khi quan sát Session và SQL

| Quan sát | Kết luận sai | Cách hiểu đúng |
|---|---|---|
| Không thấy INSERT ngay sau persist | Persist không hoạt động | INSERT có thể chờ flush; IDENTITY có thể khác sequence |
| Gọi find lần hai không thấy SELECT | Hibernate bỏ qua database hoàn toàn | Có thể trả L1 managed instance |
| Sửa field nhưng chưa thấy UPDATE | Dirty checking không chạy | UPDATE có thể chờ flush/commit |
| Đã thấy UPDATE trong log | Dữ liệu chắc chắn đã commit | Transaction vẫn có thể rollback |
| clear rồi find vẫn không có SELECT | clear không hiệu lực | L2 cache có thể trả state |
| merge xong input vẫn contains=false | Merge thất bại | Input vẫn detached; dùng managed return value |
| refresh làm mất local edits | Hibernate mất dữ liệu | Refresh chủ động reload và ghi đè state |
| rollback nhưng object cũ vẫn đổi | Rollback lỗi | Java heap không tự được database rollback |
| Một parent query nhưng nhiều child SELECT | Hibernate chạy query ngẫu nhiên | Có thể là lazy loading/N+1 |
| Batch size bật nhưng thấy nhiều INSERT | Batching không hoạt động | Generator/driver/flush pattern có thể hạn chế batch |
| SQL alias thay đổi giữa version | Query semantics thay đổi | Alias/format có thể khác nhưng SQL meaning tương đương |
| Statement count khác entity count | Statistics sai | Một entity operation có thể sinh nhiều statements |

---

## 25. Quy trình debug một câu SQL bất ngờ

Khi thấy Hibernate sinh SQL không như dự đoán:

1. **Xác định Session:** SQL xuất hiện trong Session/transaction nào?
2. **Xác định trigger:** API trực tiếp, explicit flush, auto-flush, commit hay lazy access?
3. **Kiểm tra entity state:** object đang managed, detached hay removed?
4. **Kiểm tra cache:** L1/L2 có đáp ứng find mà không cần SQL không?
5. **Xem bind values:** parameter ID, status, version hoặc FK có đúng không?
6. **Xem mapping:** cascade, fetch, owning side, generated ID và dynamic update có ảnh hưởng?
7. **Xem transaction:** SQL đã commit hay transaction còn active?
8. **Đọc bằng context mới:** database state cuối có khớp kỳ vọng?

Nếu SQL bị phát nhiều lần, đếm statement theo transaction và kiểm tra vòng lặp/lazy association. Nếu không có SQL, kiểm tra entity có đang managed và field thực sự có thay đổi so với persistent state không.

---

## 26. Lưu ý về logging và môi trường

SQL/bind logging rất hữu ích trong lab, nhưng cần dùng có giới hạn:

- Bind values có thể chứa dữ liệu nhạy cảm.
- TRACE logging làm tăng output, I/O và dung lượng log.
- SQL formatting/highlighting chỉ phục vụ đọc log, không thay đổi execution semantics.
- SQL sinh ra phụ thuộc dialect và Hibernate version.
- show_sql và logger có thể tạo output trùng nếu bật cùng lúc.
- Statistics dùng chung SessionFactory có thể bị ảnh hưởng bởi các tests chạy song song.
- StatementInspector thấy SQL string, không phải toàn bộ thông tin JDBC execution hoặc transaction outcome.
- Production observability nên cân nhắc sampling, redaction và quyền truy cập log.

Đừng để debug logging làm lộ dữ liệu thật trong log tập trung.

---

## 27. Bài tập tự thực hiện

### Bài 1 — Persist

Tạo PurchaseOrder mới, gọi persist, kiểm tra contains() trước/sau. Quan sát INSERT và generated ID. Giải thích tại sao IDENTITY có thể làm INSERT xuất hiện sớm.

### Bài 2 — First-level cache

Load cùng ID hai lần trong một Session. So sánh object identity và số SELECT. Mở Session thứ hai và lặp lại.

### Bài 3 — Dirty checking

Load managed entity, đổi status, quan sát log trước flush và sau flush. Rollback transaction rồi đọc bằng Session mới.

### Bài 4 — Detach

Load entity, detach, sửa field và flush. Mở Session mới để xác nhận thay đổi sau detach không được ghi.

### Bài 5 — Merge

Tạo detached entity, sửa field, merge vào Session khác. Kiểm tra contains() cho input và return value; đọc database sau commit.

### Bài 6 — Refresh

Load entity, sửa local field, gọi refresh. Quan sát SELECT và ghi nhận field nào bị ghi đè.

### Bài 7 — Remove

Load entity, remove, flush, sau đó rollback. Đọc bằng Session mới và xác nhận row vẫn tồn tại. Lặp lại với commit và xác nhận row bị xóa.

### Bài 8 — Lazy loading

Load danh sách orders, truy cập lines trong vòng lặp. Đếm SELECT và thử fetch join/batch fetching để so sánh.

### Bài 9 — Optimistic locking

Tạo hai Sessions, load cùng version, cập nhật và commit theo thứ tự. Quan sát version predicate và exception của transaction stale.

### Bài 10 — StatementInspector

Thu SQL qua StatementInspector. Viết test chỉ xác nhận statement type/table cần thiết thay vì khóa toàn bộ SQL formatting.

---

## 28. Checklist đọc vòng đời entity qua Session

- SessionFactory được tạo một lần và đóng đúng lifecycle?
- Mỗi Session có scope ngắn và không được chia sẻ giữa threads?
- Transaction bắt đầu trước các thao tác ghi?
- Entity có được nhận diện transient/managed/detached/removed đúng?
- persist() có đưa đúng instance vào context?
- Identifier strategy có giải thích được thời điểm INSERT?
- find() có thể trả từ first-level cache?
- Session khác có persistence context độc lập?
- Thay đổi field managed có được dirty-check?
- Đã xác định thời điểm flush?
- Đã phân biệt flush với commit?
- detach() và clear() có được phân biệt?
- Sau detach có tránh kỳ vọng dirty checking?
- merge() có dùng return value?
- refresh() có thể ghi đè local state?
- remove() được kiểm tra sau commit/rollback bằng Session mới?
- Rollback có được xác minh từ database thay vì object cũ?
- SQL logger và bind logger có được cấu hình đúng version?
- Bind logging có được giới hạn ở môi trường an toàn?
- Statistics có được reset và cô lập theo test?
- StatementInspector có chỉ quan sát SQL, không vô tình sửa SQL?
- Cascade và owning side có được phân biệt?
- Lazy loading/N+1 có được kiểm tra qua statement counts?
- Batch fetching/JDBC batching có được xác minh trên dialect/driver thực?
- L2 cache có được tính đến khi muốn buộc database read?
- Bulk DML có được tách khỏi entity dirty checking?
- Optimistic locking dùng các Session độc lập?
- Kết quả cuối có được xác nhận qua transaction/context mới?

---

## 29. Ghi nhớ

- Session là persistence context và unit of work; SessionFactory được chia sẻ lâu dài.
- Transient object chưa được Session quản lý; persist đưa instance vào managed state.
- find lần đầu có thể SELECT; find lại cùng ID trong cùng Session thường trả first-level cache instance.
- Dirty checking phát hiện thay đổi của managed entities và đồng bộ khi flush.
- Flush gửi SQL trong transaction; commit mới hoàn tất transaction.
- Detach loại một entity khỏi dirty checking; clear detach toàn bộ entities trong Session.
- Merge copy state vào managed instance và trả instance đó; input vẫn detached.
- Refresh reload state của managed entity từ database mà transaction hiện tại nhìn thấy.
- Remove đánh dấu managed entity để xóa; DELETE thường xảy ra khi flush.
- Rollback hoàn tác database transaction, không tự khôi phục Java object fields.
- SQL logger cho statement, bind logger cho parameter values, Statistics cho counters, StatementInspector cho SQL interception.
- Không suy luận commit chỉ từ việc đã thấy INSERT/UPDATE/DELETE trong log.
- Session mới không đảm bảo SELECT nếu second-level cache được bật.
- Lazy associations có thể sinh N+1; fetch join và batch fetching cần được chọn theo use case.
- Batching phụ thuộc generator, driver, dialect và flush pattern.
- Bulk DML bypass dirty checking từng entity; context có thể stale sau operation.
- Optimistic locking cần hai persistence contexts và version column để phát hiện lost updates.

**Kết luận:** Cách quan sát Hibernate rõ nhất là theo dõi cùng một entity qua từng Session và transaction, đồng thời ghi lại contains(), object state, SQL, bind values và kết quả đọc từ context mới. Session cho biết Hibernate đang quản lý object nào; SQL log cho biết Hibernate gửi thao tác gì; transaction outcome và lần đọc mới xác nhận dữ liệu cuối cùng trong database.
