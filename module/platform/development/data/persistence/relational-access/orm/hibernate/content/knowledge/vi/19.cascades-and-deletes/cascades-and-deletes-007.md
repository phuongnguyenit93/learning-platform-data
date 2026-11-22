# Cascade ở ORM khác với ON DELETE CASCADE ở cơ sở dữ liệu

Khi xóa một đơn hàng có nhiều dòng hàng trong Hibernate, hai cơ chế thường bị nhầm lẫn là **cascade ở ORM** và **foreign key action ON DELETE CASCADE ở database**. Cả hai có thể làm cho các dòng hàng biến mất khi đơn hàng bị xóa, nhưng chúng hoạt động ở hai tầng khác nhau.

- ORM cascade (`CascadeType.REMOVE`, `CascadeType.ALL`) truyền một lifecycle operation từ entity cha sang entity liên quan. Hibernate/JPA quản lý các entity con, có thể tải chúng, chạy callbacks và phát SQL.
- Database `ON DELETE CASCADE` là quy tắc của foreign key. Khi DB thực thi DELETE trên parent row, DB tự xóa các child rows tham chiếu parent đó.

~~~text
ORM cascade:
  entityManager.remove(order)
       |
       +--> Hibernate cascade REMOVE tới OrderLine entities
       +--> quản lý lifecycle/state của child objects
       +--> phát DELETE cho child rows
       +--> phát DELETE cho parent row

Database ON DELETE CASCADE:
  DELETE FROM purchase_order WHERE id = 42
       |
       +--> FK action được kích hoạt
       +--> database tự xóa order_line rows có order_id = 42
~~~

Phân biệt đúng giúp tránh lỗi foreign key, tránh xóa nhầm entity được chia sẻ, hiểu tại sao số SQL khác nhau và giữ persistence context/cache nhất quán.

> **Phạm vi:** Bài sử dụng Jakarta Persistence (`jakarta.persistence`) và Hibernate ORM 6.x. Hibernate 5 thường dùng `javax.persistence`. `@OnDelete`/`OnDeleteAction` là API riêng của Hibernate (`org.hibernate.annotations`). SQL minh họa theo PostgreSQL; DDL, thứ tự SQL, cache integration và chi tiết provider có thể khác theo Hibernate version, dialect và DBMS.

## 1. Hai tầng cascade khác nhau

| Tiêu chí | ORM cascade | Database ON DELETE CASCADE |
|---|---|---|
| Nằm ở đâu? | Entity association mapping và persistence provider. | Foreign key constraint trong schema DB. |
| Ai thực hiện? | Hibernate/JPA khi xử lý lifecycle operation. | Database engine khi parent row bị DELETE. |
| Kích hoạt bởi | PERSIST, MERGE, REMOVE, REFRESH, DETACH theo cascade types. | Parent row bị xóa vật lý và FK có ON DELETE CASCADE. |
| Có cascade persist/merge? | Có, nếu khai báo PERSIST/MERGE. | Không. FK action chỉ phản ứng với parent DELETE. |
| Có gọi child @PreRemove? | Có thể, nếu child đi qua ORM remove lifecycle. | Không. Database không gọi Java callbacks. |
| Có biết managed entities? | Có; provider quản lý state và identity. | Không biết Java objects trong Hibernate Session. |
| Có hiệu lực khi xóa bằng SQL trực tiếp? | Không chạy ORM cascade. | Có, nếu FK thật được cấu hình. |
| Cần FK ON DELETE CASCADE? | Không bắt buộc. | Bắt buộc. |

**ORM cascade là truyền thao tác giữa entity objects; database cascade là quy tắc tham chiếu giữa rows.** Kết quả cuối có thể giống nhau, nhưng semantics không giống nhau.

## 2. Ví dụ domain PurchaseOrder và OrderLine

Một đơn hàng có nhiều dòng:

~~~mermaid
classDiagram
    class PurchaseOrder {
        Long id
        String orderNumber
    }
    class OrderLine {
        Long id
        String sku
        int quantity
    }
    PurchaseOrder "1" --> "0..*" OrderLine : contains
~~~

Schema ban đầu:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(id)
);
~~~

Entity cha:

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachTo(null);
        }
    }
}
~~~

Entity con:

~~~java
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
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    void attachTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

`OrderLine.order` là **owning side** vì nó ánh xạ FK `order_id`; `PurchaseOrder.lines` là inverse side do `mappedBy = "order"`. Domain methods cập nhật cả hai phía để object graph và FK mapping nhất quán.

## 3. ORM cascade là gì?

JPA cascade quy định khi một lifecycle operation được thực hiện trên entity, thao tác đó có được truyền sang entity liên quan hay không. Cascade được khai báo trên association:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi gọi `entityManager.persist(order)`, provider có thể cascade PERSIST tới các child transient. Khi gọi `entityManager.remove(order)`, provider cascade REMOVE đến child entities theo mapping.

### Các cascade type của JPA

| Cascade type | Khi nào truyền thao tác? | Ý nghĩa |
|---|---|---|
| PERSIST | Parent được persist. | Lưu các child transient thuộc cùng aggregate. |
| MERGE | Parent được merge. | Merge state của associated entities theo cascade. |
| REMOVE | Parent được remove. | Xóa associated entities theo lifecycle ORM. |
| REFRESH | Parent được refresh. | Refresh state của associated entities. |
| DETACH | Parent được detach. | Detach associated entities. |
| ALL | Mọi cascade operation JPA định nghĩa. | Shorthand cho các thao tác trên. |

`CascadeType.ALL` **không có nghĩa database cascade mọi thứ**. Nó không tự tạo FK ON DELETE CASCADE, không thêm trigger và không tự thiết lập constraint.

### Cascade persist

~~~java
PurchaseOrder order = new PurchaseOrder("PO-1001");
order.addLine(new OrderLine("BOOK-01", 2));
order.addLine(new OrderLine("PEN-02", 5));

entityManager.persist(order);
~~~

Nếu association có cascade PERSIST, Hibernate có thể persist parent và các child transient trong cùng unit of work. Nếu không có cascade, application phải persist child riêng hoặc có quy trình lưu rõ ràng khác. DB ON DELETE CASCADE không giúp lưu child khi tạo parent.

## 4. Cascade REMOVE: xóa theo lifecycle ORM

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines = new ArrayList<>();
~~~

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
entityManager.remove(order);
~~~

Hibernate áp dụng remove cascade đến child entities. Với FK không cho xóa parent trước child, provider phải sắp xếp các thao tác để không vi phạm constraint, thường là xóa child rows trước rồi xóa parent row.

SQL minh họa:

~~~sql
DELETE FROM order_line WHERE id = ?;
DELETE FROM order_line WHERE id = ?;
DELETE FROM purchase_order WHERE id = ?;
~~~

SQL thật có thể được batch và thay đổi theo số child, collection fetch state, mapping và Hibernate version. Provider có thể cần tải collection để thực hiện cascade lifecycle; không giả định remove(parent) luôn là một câu SQL duy nhất.

### Lifecycle callback

~~~java
@Entity
public class OrderLine {
    @PreRemove
    void beforeDelete() {
        // Ví dụ: ghi log nghiệp vụ nội bộ.
    }
}
~~~

Khi child được remove qua JPA/Hibernate lifecycle, callback `@PreRemove` của child có thể được gọi. Callback hữu ích cho hành vi ở cấp entity, nhưng không nên chứa external side effects khó rollback như gửi email hoặc gọi dịch vụ thanh toán.

## 5. Database ON DELETE CASCADE là gì?

Thêm hành động vào foreign key:

~~~sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
        ON DELETE CASCADE
);
~~~

Khi chạy `DELETE FROM purchase_order WHERE id = 42`, database tự xóa các hàng `order_line` có `order_id = 42` theo FK action. Application không cần gửi DELETE riêng cho từng child.

### DB cascade không phải cascade persist

- INSERT purchase_order: không tự insert order_line.
- UPDATE purchase_order: không tự merge state Java của child.
- DELETE purchase_order: database xóa child rows tham chiếu parent nếu FK có ON DELETE CASCADE.

Nó không biết CascadeType.PERSIST, MERGE, REFRESH hay DETACH.

### Các FK action thường gặp

| FK action | Khi xóa parent | Ý nghĩa |
|---|---|---|
| NO ACTION | Kiểm tra FK; có thể từ chối nếu còn child. | Hành vi mặc định phổ biến. |
| RESTRICT | Từ chối xóa khi còn child tham chiếu (timing tùy DB). | Bảo vệ parent. |
| CASCADE | Tự xóa child rows tham chiếu. | Xóa vật lý theo chuỗi FK. |
| SET NULL | Đặt FK của child thành NULL. | Chỉ phù hợp nếu cột nullable và domain cho phép. |
| SET DEFAULT | Đặt FK về giá trị mặc định nếu DB hỗ trợ. | Giá trị mặc định phải thỏa FK. |

Không dùng SET NULL với order_id NOT NULL; không dùng CASCADE nếu child cần được giữ lại như bản ghi độc lập.

## 6. So sánh luồng SQL

### ORM cascade REMOVE

~~~text
entityManager.remove(order)
       |
       v
Hibernate duyệt association có cascade REMOVE
       |
       v
Child entities được xử lý như lifecycle removals
       |
       v
DELETE child rows (có thể batching)
       |
       v
DELETE parent row
       |
       v
COMMIT
~~~

### Database ON DELETE CASCADE

~~~text
DELETE parent row
       |
       v
Database kiểm tra FK action
       |
       v
Database tự DELETE các child rows liên quan
       |
       v
COMMIT
~~~

| Câu hỏi | ORM cascade REMOVE | DB ON DELETE CASCADE |
|---|---|---|
| Child row bị xóa? | Có, qua thao tác ORM. | Có, do FK action. |
| Hibernate biết từng child lifecycle? | Có, nếu child được cascade remove qua ORM. | Không tự biết nếu DB xóa trực tiếp ngoài ORM. |
| Child @PreRemove? | Có thể chạy. | Không chạy. |
| Có cần FK ON DELETE CASCADE? | Không. | Có. |
| Xóa parent bằng SQL ngoài Hibernate? | Không chạy ORM cascade. | DB cascade vẫn hoạt động nếu FK được cấu hình. |
| SQL do ORM phát ra? | Có thể nhiều child DELETE và parent DELETE. | Có thể chỉ một DELETE parent từ client. |

## 7. @OnDelete: Hibernate annotation liên quan DB cascade

Hibernate cung cấp:

~~~java
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;
~~~

Khai báo trên association:

~~~java
@OneToMany(mappedBy = "order")
@OnDelete(action = OnDeleteAction.CASCADE)
private List<OrderLine> lines = new ArrayList<>();
~~~

`@OnDelete(action = CASCADE)` diễn tả rằng **database foreign key nên có hành động ON DELETE CASCADE**. Khi Hibernate tạo schema bằng DDL generation, annotation có thể được dùng để sinh FK với hành động đó. Đây là tính năng Hibernate, không phải annotation JPA portable.

### Annotation không thay thế migration schema

Trong production, schema thường được quản lý bằng Flyway, Liquibase hoặc migration SQL riêng. Nếu chỉ thêm @OnDelete vào Java nhưng database FK hiện tại vẫn là:

~~~sql
FOREIGN KEY (order_id) REFERENCES purchase_order(id)
~~~

thì DB **không tự suy ra** phải cascade. Cần migration thực sự thay constraint:

~~~sql
ALTER TABLE order_line
DROP CONSTRAINT fk_order_line_order;

ALTER TABLE order_line
ADD CONSTRAINT fk_order_line_order
FOREIGN KEY (order_id)
REFERENCES purchase_order(id)
ON DELETE CASCADE;
~~~

Tên constraint tùy schema thật. Phải kiểm tra dữ liệu hiện có và đảm bảo migration có thể áp dụng.

### @OnDelete không đồng nghĩa CascadeType.REMOVE

`cascade = CascadeType.REMOVE` là ORM lifecycle cascade. `@OnDelete(action = OnDeleteAction.CASCADE)` là yêu cầu DB xử lý FK cascade khi parent row bị xóa, với Hibernate-specific mapping/schema support.

Nếu cần cả lifecycle cascade ở JPA lẫn DB cascade cho SQL ngoài ORM, có thể kết hợp hai cơ chế, nhưng phải hiểu Hibernate version xử lý fetch/evict/cache ra sao và kiểm tra SQL thật.

## 8. Kết hợp @OnDelete và CascadeType.REMOVE

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
@OnDelete(action = OnDeleteAction.CASCADE)
private List<OrderLine> lines = new ArrayList<>();
~~~

Ý định:

- CascadeType.REMOVE: biểu đạt lifecycle remove của JPA đối với child entities.
- @OnDelete(CASCADE): DB FK tự xóa child rows khi parent row bị xóa vật lý.

Trong Hibernate, khi @OnDelete được dùng cùng cascade remove, provider có thể cần **tải child entities và xử lý chúng trong persistence context để đồng bộ trạng thái/cache**, trong khi database đảm nhận việc xóa rows qua FK action thay vì Hibernate phát từng child DELETE. Chi tiết thực thi và cache behavior phụ thuộc Hibernate version, mapping và cache configuration; cần xác minh bằng integration test.

Database chỉ xóa rows. Hibernate có thể còn cần biết child entities nào bị ảnh hưởng để thực hiện lifecycle bookkeeping theo mapping/provider, đánh dấu hoặc loại child entities khỏi second-level cache khi cơ chế hỗ trợ, và giữ persistence context nhất quán hơn.

Không nên mặc định mọi managed child objects ở mọi context đều được đồng bộ tự động. Context khác hoặc ứng dụng khác có thể đang giữ child state stale; DB không broadcast thông báo đến tất cả Hibernate sessions.

| Nhu cầu | Mapping thường cân nhắc |
|---|---|
| Muốn ORM thực hiện child lifecycle/callback | CascadeType.REMOVE, FK bình thường. |
| Muốn DB xóa child rows hiệu quả; không cần ORM child callbacks | FK ON DELETE CASCADE, có thể dùng @OnDelete. |
| Muốn DB cascade và Hibernate phối hợp lifecycle/cache | @OnDelete(CASCADE) kết hợp CascadeType.REMOVE, kiểm chứng theo Hibernate version. |
| Muốn giữ child độc lập khi parent bị xóa | Không cascade remove; dùng FK RESTRICT/NO ACTION hoặc xử lý theo domain. |

## 9. ORM cascade không tự tạo ON DELETE CASCADE trong DB

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
~~~

`CascadeType.ALL` không đồng nghĩa DDL:

~~~sql
FOREIGN KEY (order_id)
REFERENCES purchase_order(id)
ON DELETE CASCADE
~~~

ORM cascade không phải FK action. Hibernate có thể xóa child rows bằng SQL trước parent, nhưng database FK vẫn có thể là NO ACTION.

Nếu xóa parent bằng SQL trực tiếp:

~~~sql
DELETE FROM purchase_order WHERE id = 42;
~~~

JPA CascadeType.REMOVE không được chạy. Nếu FK không có ON DELETE CASCADE, DB có thể từ chối xóa vì còn order_line tham chiếu.

Tương tự, FK có ON DELETE CASCADE không giúp `entityManager.persist(order)` tự persist các child transient. Muốn lưu graph, phải cấu hình CascadeType.PERSIST/ALL hoặc persist child riêng.

## 10. Cascade và hướng quan hệ: owning side khác cascade direction

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.REMOVE)
private List<OrderLine> lines;

@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

Owning side quyết định mapping ghi FK. Cascade side quyết định lifecycle operation được truyền theo hướng association đã khai báo. Chúng không bắt buộc cùng một hướng trong mọi mapping.

Với association hai chiều, thêm child vào inverse collection mà không gán owning side có thể làm FK không đúng, dù đã khai báo cascade.

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.attachTo(this);
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.attachTo(null);
    }
}
~~~

Nếu FK order_id là NOT NULL, attachTo(null) chỉ phù hợp khi schema/domain cho phép. Với child bắt buộc phải thuộc parent, cách remove phù hợp thường là orphan removal hoặc delete child, không phải ghi FK null.

## 11. orphanRemoval khác ORM REMOVE cascade và DB ON DELETE CASCADE

`orphanRemoval = true` xử lý tình huống **child bị loại khỏi association của parent**, dù parent vẫn còn tồn tại.

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 42L);
OrderLine line = order.getLines().get(0);

order.removeLine(line);
// Khi flush, Hibernate có thể DELETE orphan OrderLine.
// PurchaseOrder vẫn tồn tại.
~~~

| Cơ chế | Điều kiện kích hoạt | Kết quả |
|---|---|---|
| CascadeType.REMOVE | Parent được remove(). | Truyền remove đến child. |
| orphanRemoval = true | Child bị loại khỏi quan hệ được mapping hỗ trợ. | Child được coi là orphan và bị xóa theo lifecycle ORM khi flush. |
| FK ON DELETE CASCADE | Parent row bị xóa vật lý trong DB. | DB xóa child rows tham chiếu. |

ON DELETE CASCADE **không** xóa child chỉ vì application bỏ nó khỏi Java collection khi parent vẫn còn. DB không thấy parent DELETE nên FK cascade không chạy.

orphanRemoval cũng không phải ON DELETE SET NULL. Nếu muốn child tồn tại nhưng không còn parent, cần quan hệ optional và cập nhật FK null nếu schema/domain cho phép.

Không dùng orphanRemoval cho entity được chia sẻ bởi nhiều parents; nó có thể xóa dữ liệu mà parent khác còn cần.

## 12. CascadeType.ALL có thể nguy hiểm

~~~java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
~~~

Nếu xóa PurchaseOrder, remove cascade có thể truyền đến Customer được tham chiếu. Nhưng một customer có thể có nhiều orders hoặc được chia sẻ bởi nhiều aggregate. Xóa order không nên xóa customer.

| Quan hệ | Cascade thường cân nhắc | Lý do |
|---|---|---|
| Order → OrderLine thuộc riêng order | PERSIST, MERGE, đôi khi REMOVE, orphanRemoval | Child có vòng đời phụ thuộc parent. |
| Order → Customer (ManyToOne) | Thường không cascade REMOVE. | Customer được chia sẻ. |
| Order → Product reference | Thường không cascade REMOVE. | Product là catalog entity. |
| User → Profile một-một riêng biệt | Có thể cascade phù hợp ownership. | Profile có thể phụ thuộc user. |
| Entity → lookup/reference | Thường không cascade REMOVE. | Lookup không nên bị xóa theo entity tham chiếu. |

Theo JPA portability rules, ứng dụng portable nên dùng cascade REMOVE cho OneToOne/OneToMany; không nên cascade REMOVE qua ManyToOne/ManyToMany đến entities có thể được chia sẻ.

## 13. Many-to-many: DB cascade trên join table khác xóa entity đích

~~~java
@ManyToMany
@JoinTable(
    name = "student_course",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();
~~~

Schema:

~~~sql
CREATE TABLE student_course (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE CASCADE
);
~~~

Khi xóa Student, DB cascade từ student có thể xóa **các hàng association trong student_course**. Nó không có nghĩa xóa Course rows. Course là target entity có thể được nhiều students dùng chung.

Không cascade REMOVE tới target của ManyToMany một cách máy móc:

~~~java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Course> courses;
~~~

Xóa một student có thể yêu cầu Hibernate xóa các course entities dùng chung, vi phạm FK từ students khác hoặc xóa catalog đang được sử dụng.

Thông thường, xóa parent trong many-to-many chỉ cần xóa join rows liên quan; target entities vẫn tồn tại. DB ON DELETE CASCADE trên FK join table có thể giúp tự dọn association rows khi một bên bị xóa vật lý.

## 14. One-to-many dùng join table và phạm vi DB cascade

Một unidirectional OneToMany có thể được map qua join table:

~~~java
@OneToMany
@JoinTable(
    name = "order_line_link",
    joinColumns = @JoinColumn(name = "order_id"),
    inverseJoinColumns = @JoinColumn(name = "line_id")
)
private List<OrderLine> lines;
~~~

Nếu FK order_id tham chiếu purchase_order(id) với ON DELETE CASCADE, xóa order có thể tự xóa **các rows trong order_line_link**. Nó không tự xóa order_line nếu FK từ link table đến order_line không có ON DELETE CASCADE và không có ORM remove cascade.

Cần phân biệt parent entity row, child entity row và join/association row. FK cascade chỉ tác động đến **table chứa FK tham chiếu row bị xóa**; nó không suy luận từ Java object graph để xóa tất cả bảng có liên quan.

## 15. DB cascade hoạt động cả khi xóa ngoài Hibernate

~~~sql
DELETE FROM purchase_order WHERE id = 42;
~~~

Lệnh có thể đến từ Hibernate/JPA, JDBC trực tiếp, service khác viết bằng ngôn ngữ khác, script quản trị hoặc stored procedure. Miễn là thao tác thực sự xóa parent row trong database và FK constraint được cấu hình đúng, DB sẽ thực thi cascade.

ORM CascadeType.REMOVE không được chạy trong những đường SQL trực tiếp đó.

Nếu database tự xóa OrderLine, nó không gọi Java @PreRemove hoặc entity listener. DB trigger có thể chạy nếu schema có trigger, nhưng đó là cơ chế DB riêng, không phải JPA lifecycle callback.

Nếu cần audit mọi physical deletion bất kể caller, database trigger/audit table/CDC có thể phù hợp hơn. Nếu cần domain event, thiết kế outbox hoặc phát sự kiện sau commit; không gửi external message trực tiếp trong @PreRemove vì transaction có thể rollback.

## 16. Persistence context có thể stale khi DB xóa child ngoài ORM

Giả sử Hibernate đang quản lý:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 42L);
OrderLine line = order.getLines().get(0);
~~~

Một native SQL hoặc service khác xóa parent, DB cascade xóa child row:

~~~sql
DELETE FROM purchase_order WHERE id = 42;
~~~

Nhưng Java objects order và line trong persistence context hiện tại không tự biến mất khỏi bộ nhớ. Chúng có thể trở thành **stale managed state**:

- line vẫn là một Java object có ID.
- order.getLines() có thể vẫn giữ reference.
- Getter có thể trả state cũ.
- Một thao tác update/flush sau đó có thể cố ghi row không còn tồn tại, dẫn tới stale-state exception hoặc kết quả phụ thuộc SQL.

Database không biết EntityManager nào đang mở và không broadcast event để cập nhật mọi persistence contexts.

Sau native/bulk/external delete, cần chủ động đồng bộ context theo phạm vi: refresh(entity) nếu entity vẫn tồn tại và cần tải state DB mới; detach(entity) hoặc clear() khi chấp nhận bỏ managed state; hoặc đóng transaction/context và bắt đầu unit of work mới.

clear() tác động toàn context và có thể bỏ pending changes chưa flush; không gọi theo thói quen. Nếu chỉ một aggregate bị ảnh hưởng, cân nhắc phạm vi hẹp hơn hoặc kết thúc unit of work.

## 17. Second-level cache: DB cascade không tự evict mọi child entry

Nếu bật Hibernate second-level cache, child entity có thể đã được cache:

~~~text
Session A -> load OrderLine#100
             |
             +--> L2 cache stores OrderLine#100

Session B -> DELETE purchase_order#42
             |
             +--> DB ON DELETE CASCADE deletes order_line#100

L2 cache may still contain stale OrderLine#100
~~~

Database không biết cache region của Hibernate nên không tự invalidates entity/collection cache entries. Nếu delete đi qua SQL ngoài ORM hoặc bulk operation, cache có thể cần evict/invalidate theo cách provider hỗ trợ.

### @OnDelete và cache behavior trong Hibernate

`@OnDelete(action = CASCADE)` cho Hibernate biết mapping dựa vào FK action của database. Hibernate có thể phối hợp xử lý khi parent được xóa qua ORM. Tuy nhiên, cách child entities được fetch/đánh dấu và cách cache entries được evict phụ thuộc việc association có cascade REMOVE và Hibernate version/configuration.

Trong các phiên bản Hibernate hỗ trợ semantics này, kết hợp `@OnDelete(CASCADE)` với ORM REMOVE có thể khiến provider xử lý child entity state/cache trong khi để DB thực hiện việc xóa rows. Nếu chỉ dựa vào FK cascade mà Hibernate không biết child lifecycle, không được giả định mọi L2 cache entry đều tự bị xóa.

Hãy kiểm tra tài liệu đúng Hibernate version và viết integration test với cache đang bật. Không coi annotation là thông báo toàn cục tới mọi SessionFactory/process đang chạy. Cache collection và query regions cũng cần được tính đến.

## 18. Bulk JPQL DELETE không chạy ORM cascade như remove từng entity

Entity lifecycle remove:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 42L);
entityManager.remove(order);
~~~

Bulk JPQL DELETE:

~~~java
int deleted = entityManager.createQuery(
    "delete from PurchaseOrder o where o.id = :id"
).setParameter("id", 42L)
 .executeUpdate();
~~~

Bulk JPQL DELETE thực hiện DML trực tiếp ở mức query; nó không lần lượt load từng entity rồi gọi EntityManager.remove() cho từng row. Vì thế:

- JPA CascadeType.REMOVE không được thực thi như entity lifecycle cascade.
- Entity callbacks như @PreRemove không được gọi cho từng entity bị bulk delete.
- Persistence context có thể chứa entities stale sau bulk DML.
- Database FK ON DELETE CASCADE vẫn có thể chạy khi câu DELETE parent được DB thực thi.

Nếu schema có FK ON DELETE CASCADE, bulk query xóa parent có thể khiến DB xóa child rows. Nếu schema không có FK cascade, bulk delete có thể thất bại vì còn child rows, dù mapping Java có cascade REMOVE.

Đây là khác biệt thường gây lỗi khi ứng dụng chuyển từ entityManager.remove(order) sang bulk query chỉ để tăng hiệu năng.

## 19. Native SQL DELETE và database cascade

~~~java
entityManager.createNativeQuery(
    "delete from purchase_order where id = :id"
).setParameter("id", 42L)
 .executeUpdate();
~~~

Lệnh này không đi qua JPA remove(parent) lifecycle, nên không thực hiện ORM cascade remove. Nhưng nếu FK thật trong database có ON DELETE CASCADE, database vẫn xóa child rows.

Sau native DML, cần xử lý persistence context/cache nếu entities liên quan đang được quản lý hoặc cache. Việc dùng EntityManager cho native SQL không biến câu SQL thành entity lifecycle operation.

## 20. Khi nào DB cascade có thể tốt hơn về hiệu năng?

Giả sử một đơn hàng có 10.000 dòng. ORM cascade remove có thể tải/đi qua collection và child entities theo mapping, duy trì entity entries/lifecycle state, kiểm tra cascade graph và callbacks, phát các delete statements cho children (có thể batching), rồi xóa parent.

DB cascade có thể cho phép:

~~~sql
DELETE FROM purchase_order WHERE id = 42;
~~~

Database tự xóa child rows qua FK. DB engine có thể tối ưu thao tác nội bộ và không cần truyền 10.000 IDs lên application.

Nhưng DB cascade không phải lúc nào cũng nhanh hơn tổng thể:

- DB vẫn phải tìm và xóa child rows; index trên FK có thể rất quan trọng.
- Trigger, FK checks và nhiều cấp cascade vẫn có chi phí.
- Nếu application cần callback/audit/event cho từng child, DB cascade có thể đòi thiết kế bổ sung.
- Nếu Hibernate phải tải child để evict L2 cache/lifecycle tracking theo mapping, một phần lợi ích tránh load có thể giảm.
- Một lệnh xóa lớn có thể giữ locks, generate WAL/undo và tạo transaction dài.

Đo trên database và dữ liệu thực tế. Không chọn DB cascade chỉ vì nhìn thấy ít dòng SQL hơn trong log Hibernate.

## 21. Index trên foreign key và chi phí cascade

Khi DB xóa parent với ON DELETE CASCADE, nó cần tìm các child rows tham chiếu parent. Index trên FK có thể giúp:

~~~sql
CREATE INDEX ix_order_line_order_id
ON order_line(order_id);
~~~

Một số DBMS không tự tạo index cho FK phía child; PostgreSQL chẳng hạn không tự động tạo index chỉ vì có FK. Cần xem execution plan và workload để quyết định index. Với bảng child rất lớn, thiếu index có thể khiến parent deletion tốn kém do tìm rows liên quan.

Nếu cascade nhiều cấp:

~~~text
purchase_order
   |
   +-- order_line
          |
          +-- line_discount
~~~

và mỗi FK có ON DELETE CASCADE, xóa order có thể kéo theo line và discount rows theo chuỗi. Điều này hữu ích khi tất cả child thực sự thuộc vòng đời parent, nhưng cũng làm một lệnh DELETE có tác động lớn hơn nhiều so với nhìn thấy trong SQL client.

## 22. FK action, vòng phụ thuộc và self-reference

Database phải xử lý dependency của các foreign keys. Một schema có nhiều FK cascade vòng quanh nhau có thể bị DB từ chối tạo constraint hoặc tạo hành vi khó kiểm soát. Các DBMS có quy tắc khác nhau cho cascading paths, cycles, trigger recursion và constraint timing.

~~~text
Department -> Employee
Employee -> DepartmentManager (Employee)
~~~

Không nên đặt ON DELETE CASCADE ở mọi FK chỉ để tránh lỗi constraint. Xóa Department có thể xóa Employee, trong khi Employee lại là manager của Department hoặc được tham chiếu từ nơi khác. Phải xác định ownership và hành vi khi xóa theo domain.

Một bảng cây cũng có thể dùng self-referencing FK:

~~~sql
CREATE TABLE category (
    id BIGINT PRIMARY KEY,
    parent_id BIGINT,
    name VARCHAR(100) NOT NULL,
    FOREIGN KEY (parent_id)
        REFERENCES category(id)
        ON DELETE CASCADE
);
~~~

Xóa một category có thể cascade xuống descendants. Nếu cây lớn, một DELETE có thể xóa nhiều rows và giữ locks lâu. ORM cascade cũng có thể duyệt graph lớn và tốn memory.

## 23. Soft delete: ON DELETE CASCADE không tự chạy khi chỉ UPDATE trạng thái

~~~sql
UPDATE purchase_order
SET deleted = TRUE
WHERE id = 42;
~~~

FK ON DELETE CASCADE **không chạy**, vì không có parent row nào bị DELETE. Child rows vẫn tồn tại và FK vẫn trỏ tới parent.

Tương tự, Hibernate @SQLDelete hoặc một cơ chế soft-delete có thể thay lệnh DELETE bằng UPDATE. Khi đó DB FK action ON DELETE CASCADE không được kích hoạt.

Nếu domain muốn soft-delete cả aggregate, ORM có thể cập nhật cờ deleted cho child qua một quy trình entity/domain hoặc bulk update có chủ đích; DB có thể dùng trigger nếu thiết kế cho phép; hoặc child rows vẫn được giữ và lọc theo trạng thái parent.

Đừng kỳ vọng CascadeType.REMOVE/ON DELETE CASCADE tự có cùng semantics với soft delete. Cần xác định chính xác provider phát DELETE hay UPDATE và DB action nào được kích hoạt.

## 24. Mapping ORM cascade REMOVE mà không DB cascade

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REMOVE
        },
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Schema có FK thông thường:

~~~sql
FOREIGN KEY (order_id)
REFERENCES purchase_order(id)
~~~

Khi remove parent qua ORM, Hibernate cascade remove child và sắp xếp SQL để thỏa FK. Khi xóa parent bằng SQL trực tiếp, ORM cascade không chạy; FK có thể từ chối nếu còn children.

Chọn phương án này khi child cần @PreRemove/entity listeners, application cần xử lý child state theo lifecycle, child count vừa phải và mọi deletion paths được kiểm soát trong application service.

## 25. Mapping DB cascade qua Hibernate @OnDelete

~~~java
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@OneToMany(mappedBy = "order")
@OnDelete(action = OnDeleteAction.CASCADE)
private List<OrderLine> lines = new ArrayList<>();
~~~

DDL mong muốn:

~~~sql
ALTER TABLE order_line
ADD CONSTRAINT fk_order_line_order
FOREIGN KEY (order_id)
REFERENCES purchase_order(id)
ON DELETE CASCADE;
~~~

Trong ví dụ, @OnDelete là Hibernate-specific metadata. Nếu application dùng migration-managed schema, phải đảm bảo DDL migration thật sự tạo FK action tương ứng. Chỉ thêm annotation rồi deploy Java code không sửa một FK đã tồn tại.

Nếu chỉ cần DB physical cascade và không yêu cầu ORM remove lifecycle cho child, có thể mapping dựa vào @OnDelete mà không cascade REMOVE; kiểm tra cache/persistence-context behavior theo Hibernate version. Nếu cần Hibernate phối hợp child lifecycle/cache, cân nhắc thêm CascadeType.REMOVE cùng @OnDelete và kiểm tra việc child được fetch/evict và SQL phát ra.

Nếu application cần child callbacks chắc chắn chạy cho từng child, không giả định DB cascade thay thế ORM remove callbacks.

## 26. Spring Data JPA: delete entity khác bulk delete

Trong Spring Data JPA, các cách xóa cũng có thể có semantics khác:

- repository.delete(entity) thường đi qua EntityManager.remove() trên entity phù hợp, nên JPA remove cascade có thể chạy.
- repository.deleteById(id) trong nhiều cách triển khai sẽ tìm entity rồi remove, nhưng cần xem version/repository implementation và transaction behavior cụ thể.
- Một method @Modifying @Query("delete from PurchaseOrder ...") là bulk DML, bỏ qua entity lifecycle cascade.
- Native delete query bỏ qua ORM lifecycle, nhưng DB FK cascade vẫn có thể chạy.

~~~java
@Modifying
@Query("delete from PurchaseOrder o where o.id = :id")
int deleteDirectly(@Param("id") Long id);
~~~

Đừng dựa vào tên method delete... để suy luận lifecycle. Kiểm tra implementation/query type. Nếu method là bulk DML, cần chiến lược FK và persistence context riêng.

## 27. Database cascade có bỏ qua business validation không?

Có thể. DB FK chỉ bảo đảm referential action, không tự thực hiện các quy tắc domain nằm trong Java methods:

~~~java
public void cancel() {
    if (status == OrderStatus.SHIPPED) {
        throw new IllegalStateException("Shipped order cannot be deleted");
    }
    status = OrderStatus.CANCELLED;
}
~~~

Nếu một DBA hoặc service khác chạy DELETE FROM purchase_order WHERE id = 42, Java cancel() và validation của domain không chạy. DB có thể cascade xóa rows nếu FK được cấu hình. Nếu nghiệp vụ yêu cầu “không bao giờ xóa đơn đã giao”, cần bảo vệ ở database (permissions, trigger, procedure/constraint phù hợp) hoặc kiểm soát mọi writers ở application; chỉ dựa vào Java validation không bảo vệ được các đường SQL trực tiếp.

Đơn hàng, hóa đơn, giao dịch và hồ sơ kiểm toán thường cần giữ lại. Xóa vật lý parent cùng hàng loạt children có thể vi phạm yêu cầu lưu trữ lịch sử. Cascade là công cụ kỹ thuật, không phải quyết định retention policy.

## 28. Transaction và rollback áp dụng cho cả hai cơ chế

~~~text
BEGIN
  DELETE child rows (ORM cascade)
  DELETE parent row
ROLLBACK
~~~

hoặc:

~~~text
BEGIN
  DELETE parent row
  DB FK cascade DELETE child rows
ROLLBACK
~~~

Với transaction DB hỗ trợ atomicity cho các bảng liên quan, rollback hủy cả thao tác xóa parent lẫn child. Điều này không có nghĩa mọi side effect ngoài database tự rollback: email, HTTP request, message gửi trực tiếp hoặc thao tác filesystem không tự được hoàn nguyên.

Nếu parent/child nằm ở các DB khác nhau hoặc ứng dụng dùng distributed transaction không được cấu hình, FK không thể cascade qua database khác như một quan hệ JPA object graph. ORM cascade cũng không tự tạo một distributed atomic transaction an toàn. Cần thiết kế saga/outbox hoặc workflow nhất quán theo hệ thống phân tán.

## 29. Kiểm thử ORM cascade bằng integration test

~~~java
@Test
void removingOrderCascadesToLines() {
    EntityTransaction tx = entityManager.getTransaction();
    tx.begin();

    PurchaseOrder order = new PurchaseOrder("PO-TEST-1");
    order.addLine(new OrderLine("SKU-A", 1));
    order.addLine(new OrderLine("SKU-B", 2));
    entityManager.persist(order);
    tx.commit();

    Long id = order.getId();

    tx.begin();
    PurchaseOrder managed = entityManager.find(
        PurchaseOrder.class, id
    );
    entityManager.remove(managed);
    tx.commit();

    entityManager.clear();
    Long remaining = entityManager.createQuery(
        "select count(l) from OrderLine l where l.order.id = :id",
        Long.class
    ).setParameter("id", id)
     .getSingleResult();

    assertEquals(0L, remaining);
}
~~~

Ví dụ giả định association có cascade REMOVE và test dùng application-managed RESOURCE_LOCAL EntityManager/JUnit. Trong test Spring/JTA, transaction setup khác. Nếu muốn xác nhận callback, thêm counter/test listener được thiết kế an toàn.

Bật SQL logging để xác nhận Hibernate có load child collection không, có phát child DELETE statements không, parent DELETE chạy ở thời điểm nào và có batching không. Đây là test ORM lifecycle path, không chứng minh database FK đã có ON DELETE CASCADE.

## 30. Kiểm thử DB ON DELETE CASCADE bằng SQL trực tiếp

Để chứng minh DB FK thực sự cascade, test nên xóa parent qua JDBC/native SQL hoặc DB client trong transaction:

~~~sql
BEGIN;

DELETE FROM purchase_order WHERE id = 42;

SELECT COUNT(*)
FROM order_line
WHERE order_id = 42;
-- Kỳ vọng 0 nếu FK ON DELETE CASCADE được cấu hình.

ROLLBACK;
~~~

Nếu chỉ kiểm thử bằng entityManager.remove(order) với CascadeType.REMOVE, child rows vẫn có thể biến mất **dù FK không có ON DELETE CASCADE**. Vì vậy test này không chứng minh DB cascade.

Trên PostgreSQL có thể xem FK definition:

~~~sql
SELECT
    conname,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'order_line'::regclass
  AND contype = 'f';
~~~

Kiểm tra kết quả có ON DELETE CASCADE. Query catalog là PostgreSQL-specific; dùng câu lệnh/công cụ tương ứng nếu DB là MySQL, Oracle hoặc SQL Server.

Nếu production dùng PostgreSQL, không chỉ dựa vào H2 in-memory để xác nhận FK cascade, trigger, deferred constraint hay cache behavior. H2 có semantics và dialect riêng; dùng Testcontainers hoặc DB test cùng loại/phiên bản gần production khi tính đúng đắn phụ thuộc DB behavior.

## 31. Bulk DELETE và stale persistence context

Một test riêng:

1. Load parent và child entities trong cùng EntityManager.
2. Thực hiện bulk JPQL DELETE parent.
3. Xác nhận DB rows bị xóa theo FK action nếu có.
4. Kiểm tra những object Java đã load vẫn có thể giữ state cũ.
5. Clear/đóng context và load lại trong context mới để xác nhận DB state.

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 42L);
OrderLine line = order.getLines().get(0);

entityManager.createQuery(
    "delete from PurchaseOrder o where o.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

// order/line không tự biến thành null hay tự biến mất khỏi heap.
// DB state và managed Java state có thể không còn đồng bộ.
entityManager.clear();
~~~

Đừng dereference proxy/collection chưa initialized sau khi clear rồi kết luận DB cascade lỗi; đó có thể là LazyInitializationException do object đã detached. Reload bằng một persistence context mới để kiểm tra dữ liệu.

## 32. Migration schema và ownership của FK

Khi chuyển từ ORM cascade sang DB cascade, migration cần:

1. Xác định tất cả FK liên quan parent/child/join tables.
2. Kiểm tra orphan/invalid references trước khi thay constraint.
3. Xác định DB có hỗ trợ hành động cascade trên FK đó không.
4. Drop/recreate constraint đúng tên và đúng columns.
5. Kiểm tra index trên FK child.
6. Deploy application mapping phù hợp (@OnDelete nếu dùng Hibernate).
7. Test cả ORM remove, bulk/native SQL delete và cache invalidation.
8. Có kế hoạch rollback migration nếu schema change ảnh hưởng dữ liệu.

Không để Hibernate hbm2ddl.auto=update trở thành cơ chế duy nhất thay đổi FK cascade trong production nếu schema được quản lý bằng migration. DDL do provider sinh có thể không phản ánh đầy đủ yêu cầu vận hành, dữ liệu và compatibility của hệ thống.

Một kiến trúc rõ ràng nên chọn owner:

- Application/ORM lifecycle là owner: mọi delete đi qua service/EntityManager, child lifecycle được xử lý rõ.
- Database referential action là owner: FK constraint là nguồn sự thật cho physical row deletion, mọi clients đều tuân theo.
- Kết hợp: ORM khai báo @OnDelete/REMOVE để provider phối hợp, DB FK thực thi physical cascade; cache/audit rules được định nghĩa rõ.

## 33. Chọn cơ chế theo mục tiêu

| Mục tiêu | ORM cascade REMOVE | DB ON DELETE CASCADE |
|---|---|---|
| Child có lifecycle/callback Java cần chạy | Phù hợp hơn. | Không chạy callback Java. |
| Xóa nhiều child rows rất lớn | Có thể tốn tải entities/SQL; batching giúp một phần. | Thường giảm round trips từ application. |
| Xóa parent từ nhiều ứng dụng/ngôn ngữ | Không bao phủ đường SQL ngoài ORM. | Có hiệu lực ở DB cho mọi DELETE parent. |
| Giữ cache ORM đồng bộ | Hibernate biết lifecycle entities, nhưng vẫn cần xét context khác. | DB không tự evict cache; cần provider integration/invalidation. |
| Cần audit physical delete bất kể caller | Cần mọi callers đi qua ORM hoặc audit riêng. | Có thể dùng DB trigger/audit/CDC. |
| Schema phải portable JPA | JPA cascade portable hơn. | FK action là DB DDL, cú pháp/capability phụ thuộc DBMS. |
| Child là thành phần riêng của parent | Thường phù hợp. | Cũng phù hợp nếu DB-level delete là policy. |
| Child được nhiều parents chia sẻ | REMOVE cascade có thể nguy hiểm. | FK direction có thể xóa association rows, nhưng phải cấu hình đúng bảng. |

Trước khi chọn, hỏi: child có vòng đời phụ thuộc parent không; có cần Java callbacks không; có đường xóa ngoài Hibernate không; child count lớn đến đâu; có L2 cache không; có audit/soft-delete/retention không; FK trong schema thật đã được cấu hình đúng chưa?

## 34. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Có CascadeType.REMOVE nhưng SQL trực tiếp xóa parent bị lỗi FK | ORM cascade không chạy qua SQL trực tiếp. | Dùng ORM remove, xóa child bằng SQL hoặc thêm DB FK cascade. |
| Có ON DELETE CASCADE nhưng persist parent không lưu child | DB cascade chỉ chạy khi parent bị xóa. | Cấu hình CascadeType.PERSIST hoặc persist child riêng. |
| CascadeType.ALL làm xóa Customer khi xóa Order | REMOVE cascade đi qua ManyToOne tới entity được chia sẻ. | Bỏ REMOVE cascade ở association đó. |
| DB đã xóa child nhưng Java getter vẫn thấy child | Persistence context/L2 cache đang giữ state cũ. | Refresh/detach/clear hoặc kết thúc unit of work phù hợp. |
| @PreRemove không chạy khi DB cascade xóa child | DB không đi qua JPA lifecycle. | ORM cascade nếu callback là yêu cầu; hoặc DB trigger/audit/CDC. |
| orphanRemoval không chạy khi parent bị bulk delete | Bulk DML bỏ qua entity lifecycle. | ORM remove hoặc FK ON DELETE CASCADE. |
| Thêm @OnDelete nhưng DB không xóa child | Production FK chưa được migration sang ON DELETE CASCADE. | Kiểm tra FK thật và migration. |
| Chỉ xóa join rows, child entity còn nguyên | FK cascade chỉ tác động đến bảng chứa FK tham chiếu parent. | Phân biệt association row với entity row. |
| Cascade xóa dữ liệu lịch sử | Dùng cascade trên quan hệ có vòng đời độc lập. | Restrict delete, soft delete hoặc archive. |
| Cache vẫn stale sau DB cascade | Cache ngoài ORM không được invalidation. | Xác định cache regions và chính sách eviction. |

## 35. Checklist trước khi chọn cascade

**Về domain**

- Child có được chia sẻ bởi nhiều parents không?
- Child có vòng đời độc lập hay chỉ tồn tại như thành phần của parent?
- Xóa parent có được phép xóa vật lý child không?
- Có cần giữ lịch sử, audit, soft delete hoặc retention không?

**Về ORM**

- Association nào được khai báo cascade và theo hướng nào?
- Có thật sự cần REMOVE hay chỉ PERSIST/MERGE?
- Có cần orphanRemoval khi child bị gỡ khỏi collection?
- Owning side/FK đã được đồng bộ trong domain methods chưa?
- Child callbacks/listeners có yêu cầu chạy không?
- Managed entities/proxies và second-level cache sẽ được đồng bộ thế nào?

**Về database và kiểm thử**

- FK thật có ON DELETE CASCADE hay không?
- DDL do migration quản lý đã được cập nhật chưa?
- FK action có lan sang join table hay child entity table?
- Index trên FK đã phù hợp chưa?
- Có cycles, nhiều cascade paths, trigger hoặc soft-delete behavior không?
- Test có phân biệt ORM cascade với DB cascade không?
- Bulk JPQL/native/JDBC delete có đường đi riêng không?
- Cache first-level/second-level/collection/query có thể stale không?

## 36. Mô hình ghi nhớ cuối bài

~~~mermaid
flowchart TD
    A["Muốn xóa một entity cha"] --> B{"Xóa qua EntityManager.remove()?"}
    B -- "Có" --> C["Hibernate chạy entity lifecycle"]
    C --> D{"Association có CascadeType.REMOVE?"}
    D -- "Có" --> E["Cascade remove child entities trong ORM"]
    D -- "Không" --> F["Child lifecycle không tự cascade"]
    E --> G["Hibernate phát SQL phù hợp"]
    F --> H["DB FK kiểm tra parent DELETE"]
    G --> H
    B -- "Không: bulk/native/JDBC" --> H
    H --> I{"FK có ON DELETE CASCADE?"}
    I -- "Có" --> J["Database tự xóa child rows"]
    I -- "Không" --> K["Có thể bị FK violation nếu còn child"]
    J --> L["Kiểm tra persistence context / L2 cache"]
    K --> M["Rollback hoặc xử lý quan hệ theo domain"]
    L --> N["Commit transaction"]
    M --> N
~~~

**ORM cascade** truyền lifecycle operations giữa các entity objects trong persistence context. **Database ON DELETE CASCADE** là hành động của foreign key khi parent row bị xóa vật lý. CascadeType.REMOVE có thể chạy child lifecycle callbacks và khiến Hibernate phát các SQL child deletes; FK cascade cho phép database tự xóa rows mà không cần ORM quản lý từng child. orphanRemoval là quy tắc xóa child khi child bị tách khỏi quan hệ, còn @OnDelete là Hibernate-specific mapping giúp biểu đạt DB FK action.

Chọn cơ chế theo **vòng đời domain, số lượng child, các đường xóa ngoài ORM, callbacks, cache và schema thật**. Đừng coi CascadeType.ALL là ON DELETE CASCADE, đừng mong FK cascade lưu hoặc merge child, và đừng quên bulk/native SQL bỏ qua ORM lifecycle. Khi hai tầng được thiết kế rõ ràng và kiểm thử độc lập, thao tác xóa sẽ giữ được referential integrity mà không vô tình xóa entity được chia sẻ hoặc để persistence context/cache chứa dữ liệu cũ.
