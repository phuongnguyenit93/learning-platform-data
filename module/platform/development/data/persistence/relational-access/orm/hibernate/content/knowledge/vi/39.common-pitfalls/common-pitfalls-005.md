# Chỉ sửa phía không quản lý liên kết rồi kỳ vọng khóa ngoại tự đổi

Trong một quan hệ hai chiều của JPA/Hibernate, hai object có thể cùng tham chiếu nhau trong Java, nhưng **chỉ một phía sở hữu việc ghi quan hệ xuống database**. Với mapping phổ biến `@OneToMany(mappedBy = "order")` và `@ManyToOne`, phía `@ManyToOne` của entity con thường là owning side vì nó ánh xạ cột foreign key. Collection `order.lines` là inverse side: nó giúp điều hướng từ cha sang con, nhưng tự nó không quyết định giá trị `order_id` được ghi.

Một lỗi thường gặp:

```java
order.getLines().add(line);
```

Lập trình viên thấy `line` nằm trong collection của `order`, nên kỳ vọng Hibernate tự đổi `order_lines.order_id`. Nhưng nếu `line.getOrder()` vẫn trỏ tới parent cũ hoặc vẫn là `null`, owning side chưa đổi. Hibernate có thể không phát câu `UPDATE` cần thiết, hoặc INSERT child với FK không đúng và để database từ chối.

Chiều ngược lại cũng cần chú ý: chỉ gọi `line.setOrder(order)` có thể làm foreign key được cập nhật, nhưng collection `order.getLines()` đang nằm trong Persistence Context có thể vẫn chưa phản ánh thay đổi. Vì vậy, với quan hệ hai chiều, domain method nên cập nhật đồng thời cả hai phía Java; owning side mới là phía quyết định quan hệ được ghi xuống DB.

Bài học giải thích cách xác định owning/inverse side cho `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany` và các kiểu join table; cách viết helper methods; sự khác nhau giữa ownership, cascade và `orphanRemoval`; ảnh hưởng của `merge`, flush và persistence context; cùng cách kiểm thử để chứng minh foreign key thực sự thay đổi.

---

## 1. Phân biệt object reference và quan hệ trong database

Giả sử schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

Trong database, quan hệ được biểu diễn bởi giá trị:

```text
order_lines.order_id -> purchase_orders.id
```

Trong Java, có thể biểu diễn hai chiều:

```text
PurchaseOrder.lines  ----> OrderLine
PurchaseOrder        <---- OrderLine.order
```

Hai reference Java không tự động là hai lệnh SQL. Hibernate dựa trên mapping để xác định property nào ghi FK hoặc join table.

Có ba trạng thái cần tách biệt:

1. **Java object graph:** các field và collections đang trỏ tới object nào trong bộ nhớ.
2. **Persistence Context:** Hibernate đang theo dõi state nào của các entity managed.
3. **Database state:** FK/join-table rows thực sự có giá trị gì sau khi SQL chạy và transaction commit.

Một object graph nhìn đúng không chứng minh database relationship đã đổi. Và database relationship đã đổi cũng không bảo đảm mọi collection đang managed lập tức được đồng bộ lại.

## 2. Owning side là gì?

**Owning side** là phía association mapping mà JPA dùng để xác định thay đổi quan hệ cần ghi xuống database. Tùy loại quan hệ, phía này thường khai báo `@JoinColumn` hoặc `@JoinTable`.

**Inverse side** là phía tham chiếu lại owning side bằng `mappedBy`. Nó cung cấp navigation trong object model nhưng không sở hữu cập nhật FK/join table.

Ví dụ bidirectional one-to-many:

```java
// Parent
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();

// Child
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Ở đây:
- `OrderLine.order` là owning side.
- `PurchaseOrder.lines` là inverse side.
- `mappedBy = "order"` trỏ tới **tên thuộc tính Java** `order` trên `OrderLine`.
- `mappedBy` không phải tên cột SQL `order_id`.

Khi đổi parent của một `OrderLine`, phải thay `OrderLine.order` để Hibernate có thông tin ghi `order_id` mới.

### 2.1. Quy tắc ghi nhớ

Với mapping hai chiều phổ biến:

| Association | Owning side thường gặp | Inverse side |
| --- | --- | --- |
| `@ManyToOne` / `@OneToMany` | `@ManyToOne` | `@OneToMany(mappedBy=...)` |
| `@OneToOne` | Side khai báo FK `@JoinColumn` | Side có `mappedBy` |
| `@ManyToMany` | Side khai báo `@JoinTable` hoặc không có `mappedBy` | Side có `mappedBy` |

Đây là quy tắc theo mapping cụ thể. Không kết luận mọi `@OneToMany` đều là inverse side: một unidirectional `@OneToMany` có thể sở hữu quan hệ qua `@JoinColumn` hoặc `@JoinTable`. Phần sau sẽ chỉ rõ ngoại lệ này.

## 3. Lỗi điển hình: chỉ thêm child vào inverse collection

Mapping:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    public PurchaseOrder getOrder() {
        return order;
    }

    public void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

Code lỗi:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
OrderLine line = em.find(OrderLine.class, lineId);

order.getLines().add(line);

em.flush();
```

Nếu `line.order` vẫn trỏ tới parent khác, Hibernate thấy owning side chưa đổi. Collection inverse có thể đã thay đổi trong Java, nhưng FK trong `order_lines` vẫn theo `line.order`.

Nếu child mới có `order == null`, việc thêm vào collection inverse không tự điền `order_id`. Tùy schema/mapping, INSERT có thể gửi `NULL` và bị `NOT NULL`/FK constraint từ chối.

### 3.1. Điều gì thực sự xảy ra?

Giả sử ban đầu:

```text
Order A (id=10)
Order B (id=20)

Line X (id=100, order_id=10)
```

Code chỉ làm:

```java
orderB.getLines().add(lineX);
```

Object graph có thể trông như:

```text
Order A.lines: [Line X]  // có thể vẫn giữ X nếu chưa remove
Order B.lines: [Line X]
Line X.order: Order A
```

Mapping vẫn chỉ ra `Line X.order = Order A`, nên FK tiếp tục là `10`.

Ngay cả khi code cũng remove `Line X` khỏi collection A, nhưng không đổi `Line X.order`, owning side vẫn trỏ tới A. Collection không ghi FK thay cho child.

## 4. Chỉ sửa owning side cũng có thể để object graph không nhất quán

Đoạn sau có thể cập nhật FK:

```java
line.setOrder(orderB);
em.flush();
```

Vì `line.order` là owning side, Hibernate có thể phát:

```sql
UPDATE order_lines
SET order_id = 20
WHERE id = 100;
```

Nhưng nếu `orderA.lines` và `orderB.lines` đã được load trước đó trong cùng Persistence Context:
- `orderA.lines` có thể vẫn chứa `line`.
- `orderB.lines` có thể chưa chứa `line`.
- `line.order` lại trỏ tới `orderB`.

Database có thể đúng sau flush, trong khi hai collection Java đang stale.

Đó là lý do nên cập nhật cả hai phía bằng một method miền nghiệp vụ. **Owning side quyết định SQL; helper method giữ object graph nhất quán.**

## 5. Helper method cho bidirectional `@OneToMany` / `@ManyToOne`

Parent:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");

        PurchaseOrder currentOrder = line.getOrder();

        if (currentOrder != null && currentOrder != this) {
            throw new IllegalStateException(
                "Line already belongs to another order"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
        }

        line.assignOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.assignOrder(null);
        }
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public Long getId() {
        return id;
    }
}
```

Child:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private String sku;

    protected OrderLine() {}

    public OrderLine(String sku) {
        this.sku = Objects.requireNonNull(sku);
    }

    PurchaseOrder getOrder() {
        return order;
    }

    void assignOrder(PurchaseOrder order) {
        this.order = order;
    }

    public Long getId() {
        return id;
    }
}
```

Các điểm quan trọng:
- `addLine()` thêm vào collection và set owning side.
- `removeLine()` bỏ khỏi collection và cập nhật reference trong memory.
- Setter/assign method của owning side nên được giới hạn quyền truy cập để code ngoài aggregate không tùy tiện làm hai phía lệch nhau.
- `getLines()` không cho caller thay đổi collection trực tiếp.
- `orphanRemoval=true` có thể xóa child khi nó bị loại khỏi quan hệ sở hữu; đây là semantics riêng, không phải điều kiện để FK update hoạt động.

Ví dụ cần imports và các constructor/field khác theo ứng dụng. Khi dùng `orphanRemoval`, hãy test riêng thao tác remove và quy tắc reparenting; không dùng helper trên như một API chuyển child từ parent này sang parent khác nếu mapping coi child là orphan ngay khi bị tháo khỏi parent cũ.

## 6. Tại sao helper nên nằm ở entity/aggregate?

Nếu mọi service đều phải nhớ hai dòng:

```java
order.getLines().add(line);
line.setOrder(order);
```

thì sớm muộn sẽ có một call site chỉ làm một phía.

Đóng gói trong:

```java
order.addLine(line);
```

giúp:
- Giữ hai phía Java đồng bộ.
- Đặt validation ở đúng nơi.
- Ngăn add trùng.
- Kiểm soát child thuộc parent nào.
- Tập trung xử lý orphan/removal.
- Giảm lỗi khi nhiều use cases thao tác cùng association.

Nếu dự án dùng domain service thay vì entity method, service vẫn cần một operation duy nhất chịu trách nhiệm cập nhật cả hai phía. Điều quan trọng là invariant được giữ tại một điểm có thể kiểm soát.

## 7. `mappedBy` không có nghĩa parent collection ghi foreign key

Xem:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

`mappedBy = "order"` nói rằng quan hệ được map bởi thuộc tính `order` của child. Hibernate dùng thông tin mapping đó để biết collection là inverse.

Không có chuyện `mappedBy` chỉ ra một cột khác để Hibernate tự suy luận khi collection đổi. Nó liên kết hai Java attributes của một association bidirectional.

Nếu đổi tên field child:

```java
private PurchaseOrder purchaseOrder;
```

thì phải đổi:

```java
@OneToMany(mappedBy = "purchaseOrder")
```

Nếu vẫn giữ `mappedBy = "order"`, metadata có thể lỗi khi bootstrap vì attribute đó không tồn tại.

### 7.1. `mappedBy` không phải `@JoinColumn`

Sai cách hiểu:

```java
@OneToMany(mappedBy = "order_id")
```

nếu `order_id` chỉ là tên database column.

Đúng theo mapping ví dụ:

```java
@OneToMany(mappedBy = "order")
```

vì `order` là persistent attribute trên child.

## 8. Unidirectional `@OneToMany` là ngoại lệ quan trọng

Không có `mappedBy`:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany
    @JoinColumn(name = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
```

Trong mapping unidirectional này, association được khai báo ở parent và `@JoinColumn` xác định FK trong bảng child. Parent-side collection là phía sở hữu association theo mapping.

Vì vậy, quy tắc “ManyToOne luôn là owning side” chỉ áp dụng cho quan hệ bidirectional phổ biến có `mappedBy` ở `@OneToMany`. Nếu không có `mappedBy`, hãy đọc mapping thực tế.

### 8.1. SQL có thể khác mapping bidirectional

Với một số Hibernate mapping unidirectional one-to-many bằng FK, provider có thể:
- Insert child rows.
- Sau đó phát UPDATE để gán FK.
- Hoặc dùng SQL shape khác theo mapping/provider version.

Không viết test phụ thuộc cứng vào số câu UPDATE nội bộ nếu không phải contract cần giữ. Hãy xác nhận FK cuối cùng đúng và collection round-trip đầy đủ.

### 8.2. Khi nào chọn unidirectional?

Nếu domain không cần đi từ child về parent trong object model, unidirectional mapping có thể đơn giản hơn. Nếu child luôn cần biết parent và nhiều use cases truy cập theo cả hai chiều, bidirectional mapping thường tự nhiên hơn.

Không thêm quan hệ hai chiều chỉ vì “ORM cần”; nó làm tăng trách nhiệm giữ state nhất quán.

## 9. `@OneToOne`: phía nào sở hữu?

Ví dụ hồ sơ và tài khoản:

```java
@Entity
class UserAccount {

    @Id
    @GeneratedValue
    private Long id;

    @OneToOne(mappedBy = "account", cascade = CascadeType.PERSIST)
    private UserProfile profile;

    public void setProfile(UserProfile profile) {
        this.profile = profile;
        if (profile != null) {
            profile.setAccount(this);
        }
    }
}
```

```java
@Entity
class UserProfile {

    @Id
    @GeneratedValue
    private Long id;

    @OneToOne
    @JoinColumn(name = "account_id", unique = true)
    private UserAccount account;

    void setAccount(UserAccount account) {
        this.account = account;
    }
}
```

`UserProfile.account` sở hữu FK `account_id`. `UserAccount.profile` là inverse side vì `mappedBy = "account"`.

Nếu chỉ làm:

```java
account.setProfile(profile);
```

nhưng không set `profile.account`, FK có thể không được cập nhật.

### 9.1. Unique constraint mới bảo đảm one-to-one ở database

Annotation `@OneToOne` mô tả cardinality cho ORM. Database cũng cần unique constraint/index trên FK để ngăn nhiều profiles cùng tham chiếu một account:

```sql
ALTER TABLE user_profiles
ADD CONSTRAINT uk_user_profiles_account UNIQUE (account_id);
```

Test mapping và test constraint riêng. Một association Java có thể được khai báo one-to-one nhưng dữ liệu DB vẫn vi phạm nếu schema không có uniqueness.

## 10. `@ManyToMany`: join table do owning side quản lý

Ví dụ Student và Course:

```java
@Entity
class Student {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    public void enroll(Course course) {
        courses.add(course);
        course.addStudentInternal(this);
    }
}
```

```java
@Entity
class Course {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    void addStudentInternal(Student student) {
        students.add(student);
    }
}
```

Ở đây:
- `Student.courses` là owning side vì khai báo `@JoinTable`.
- `Course.students` là inverse side vì `mappedBy = "courses"`.
- Thay đổi owning collection điều khiển rows trong `student_courses`.
- Chỉ thêm Student vào `course.students` không yêu cầu Hibernate tạo join-table row.

Helper nên được thiết kế ở một domain service hoặc một aggregate boundary rõ ràng nếu cả hai entity không cùng ownership. Tránh để hai entity gọi lẫn nhau vô hạn hoặc expose mutable collections.

### 10.1. Đừng cascade REMOVE tới shared many-to-many target

Student và Course thường có lifecycle độc lập. Xóa một Student thường chỉ nên xóa membership rows, không xóa Course được nhiều Student dùng chung.

Không dùng `CascadeType.REMOVE`/`ALL` một cách máy móc trên many-to-many.

## 11. `@JoinTable` và `@JoinColumn` cho biết nơi lưu liên kết

Hai dạng mapping phổ biến:

**Foreign key ở bảng child:**

```java
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

**Join table riêng:**

```java
@ManyToMany
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses;
```

Khi sửa association, hãy hỏi:
1. FK nằm ở bảng nào?
2. Join table nào lưu membership?
3. Property nào khai báo mapping sở hữu cột đó?
4. Có `mappedBy` không?
5. Method đang sửa đúng owning property chưa?

Đây là cách nhanh nhất để chẩn đoán “collection đã đổi nhưng SQL không đổi”.

## 12. Cascade không quyết định owning side

Một mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

không làm `lines` trở thành owning side. Cascade trả lời câu hỏi **thao tác lifecycle nào được lan truyền**; ownership trả lời câu hỏi **phía nào ghi association**.

| Cơ chế | Câu hỏi được trả lời |
| --- | --- |
| Owning side | Property nào quyết định FK/join-table update? |
| `CascadeType.PERSIST` | Persist parent có lan truyền persist tới child không? |
| `CascadeType.MERGE` | Merge parent có lan truyền merge tới child không? |
| `CascadeType.REMOVE` | Remove parent có lan truyền remove tới child không? |
| `orphanRemoval` | Child bị tách khỏi quan hệ private ownership có bị remove không? |
| Database FK | DB có cho phép reference tới parent không tồn tại không? |

Thêm `CascadeType.ALL` không sửa lỗi chỉ cập nhật inverse side. Nếu owning field vẫn giữ giá trị cũ, cascade không tự suy ra ý định đổi FK.

## 13. `CascadeType.PERSIST`: child được lưu, nhưng FK vẫn phải đúng

Giả sử parent mới và child mới:

```java
PurchaseOrder order = new PurchaseOrder();
OrderLine line = new OrderLine("SKU-A");

order.getLines().add(line); // chỉ inverse side
em.persist(order);
em.flush();
```

`cascade = PERSIST` có thể làm Hibernate persist child. Nhưng nếu child owning field `order` chưa được gán, cascade không tự thay thế việc cập nhật association owner.

Với FK `NOT NULL`, flush có thể thất bại. Nếu FK nullable, child có thể được lưu với `order_id = NULL`, khiến dữ liệu không biểu diễn quan hệ mong muốn.

Cách đúng là gọi helper:

```java
order.addLine(line);
em.persist(order);
em.flush();
```

Test phải kiểm tra FK thực tế sau reload, không chỉ `order.getLines().contains(line)`.

## 14. `CascadeType.MERGE`: merge detached graph không chữa mọi inconsistency

`merge()` sao chép state từ detached object sang một managed instance và **trả về instance managed đó**:

```java
PurchaseOrder managed = em.merge(detachedOrder);
```

Object truyền vào không tự trở thành managed. Vì vậy, code nên tiếp tục làm việc với `managed`.

Nếu detached graph có:
```text
detachedOrder.lines contains line
line.order still points to old order
```

thì graph đã không nhất quán trước merge. Cascade MERGE không phải một quy tắc nghiệp vụ để tự chọn bên nào là ý định đúng. Owning side mapping vẫn quyết định association state được đồng bộ.

### 14.1. Test merge bằng cả hai chiều

Một test detached graph nên:
1. Load parent và child.
2. Detach/đóng EntityManager.
3. Thay đổi association qua domain helper trên detached graph.
4. Mở transaction mới và gọi `merge`.
5. Dùng object được trả về từ merge.
6. Flush/commit.
7. Reload bằng EntityManager mới.
8. Assert FK và collections hai phía.

Đừng chỉ assert detached object graph sau `merge`; nó không chứng minh database đã đổi.

## 15. `orphanRemoval` là lifecycle rule, không phải cách ghi owning side thay thế

Mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Nếu bỏ child khỏi collection, `orphanRemoval=true` có thể làm child được remove tại flush. Nhưng nó không có nghĩa bất kỳ thay đổi nào của inverse collection sẽ được diễn giải như một FK reassignment.

Phân biệt:
- **Xóa child khỏi aggregate:** có thể là orphan removal.
- **Chuyển child sang parent khác:** là thay đổi association/ownership, cần workflow phù hợp.
- **Đổi owning reference:** quyết định FK mới.
- **Cascade REMOVE:** lan truyền remove khi parent bị remove.

### 15.1. Reparenting với orphanRemoval cần đặc biệt thận trọng

Nếu child bị bỏ khỏi parent cũ trong một association có orphan removal, provider có thể coi nó là orphan cần xóa. Không giả định sau đó thêm child vào parent mới sẽ biến thao tác thành move an toàn.

Nếu domain cần chuyển child:
- Cân nhắc không dùng orphanRemoval cho association đó.
- Tạo một command move có semantics rõ.
- Dùng surrogate child ID nếu identity cần độc lập.
- Kiểm thử chính xác Hibernate version và transaction behavior.
- Nếu không cho phép move, từ chối ngay ở domain layer.

## 16. `mappedBy` và field access/property access

Hibernate đọc mapping từ persistent attributes. Với field access:

```java
@Access(AccessType.FIELD)
@Entity
class OrderLine {
    @ManyToOne
    private PurchaseOrder order;
}
```

`mappedBy = "order"` tham chiếu field persistent `order`.

Với property access, annotation nằm trên getter và tên property theo JavaBeans conventions. Đừng trộn access strategy tùy tiện giữa ID và association mapping; điều đó có thể khiến provider không nhận attribute như bạn nghĩ.

Khi đổi tên field/getter:
- Cập nhật `mappedBy`.
- Cập nhật JPQL paths.
- Cập nhật entity graphs.
- Cập nhật criteria queries.
- Cập nhật tests/reflection code.

Tên cột SQL có thể giữ nguyên dù tên property Java đổi, nhưng `mappedBy` vẫn cần trỏ đúng property.

## 17. `insertable=false, updatable=false` không biến một field thành owning side

Một số mapping dùng chung column:

```java
@Column(name = "order_id", insertable = false, updatable = false)
private Long orderId;

@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Ở đây scalar `orderId` là read-only view của cùng column; association `order` mới điều khiển ghi FK.

Nếu code chỉ làm:

```java
line.setOrderId(newOrderId);
```

thì không có UPDATE FK vì column mapping này không insertable/updatable.

Cập nhật association:

```java
line.setOrder(newOrder);
```

và kiểm tra mapping trùng column đúng theo design. Không cho hai writable attributes cùng ghi một column.

## 18. `@MapsId`: association cung cấp một phần khóa chính

Với dependent entity có khóa dẫn xuất:

```java
@EmbeddedId
private OrderLineId id;

@MapsId("orderId")
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

Association `order` vừa là owning side của FK vừa cung cấp thành phần `orderId` trong embedded ID.

Nếu chỉ sửa collection inverse:
- `OrderLine.order` chưa đổi.
- FK chưa đổi.
- Derived ID có thể chưa được đồng bộ theo parent mới.

Với `@MapsId`, thay parent còn có thể đồng nghĩa thay primary key. Primary key của entity đã persistent không nên bị thay như một thuộc tính thông thường. Nếu domain cho phép chuyển, cân nhắc delete/create hoặc surrogate ID; không chỉ set reference rồi hy vọng Hibernate di chuyển row.

## 19. `@OneToMany` có `@JoinColumn`: xác định owner theo mapping thực tế

Ví dụ:

```java
@OneToMany
@JoinColumn(name = "department_id")
private List<Employee> employees;
```

Không có `mappedBy`. Association được khai báo ở parent và `@JoinColumn` xác định FK trong bảng employee. Đây không phải trường hợp bidirectional `mappedBy` mà child `@ManyToOne` là owner.

Nếu chuyển sang bidirectional:

```java
@OneToMany(mappedBy = "department")
private List<Employee> employees;
```

và:

```java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

thì child association mới là owner.

Đây là lý do không nên học thuộc “OneToMany luôn inverse” mà không đọc mapping annotations cụ thể.

## 20. Kiểm tra SQL được phát khi đổi association

Với bidirectional `OrderLine.order` là owner, khi chuyển Line#100 từ Order#10 sang Order#20, SQL mong đợi về mặt logic:

```sql
UPDATE order_lines
SET order_id = 20
WHERE id = 100;
```

SQL thực tế có thể thêm version predicate:

```sql
UPDATE order_lines
SET order_id = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu chỉ sửa inverse collection, thường không có UPDATE FK tương ứng.

Đừng assert SQL string đầy đủ nếu không cần; alias, placeholder, version columns và statement ordering có thể thay đổi. Hãy assert:
- Có đúng FK cuối cùng.
- Không tạo duplicate child.
- Parent cũ không còn child.
- Parent mới có child.
- Constraint được giữ.

## 21. Kiểm thử cơ bản: helper method ghi đúng FK

Một integration test nên có transaction thật:

```java
@Test
void addingLineThroughHelperPersistsOwningSide() {
    Long orderId;
    Long lineId;

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = new PurchaseOrder();
        OrderLine line = new OrderLine("SKU-A");

        order.addLine(line);
        em.persist(order);
        em.flush();

        orderId = order.getId();
        lineId = line.getId();

        tx.commit();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        OrderLine loadedLine = verify.find(OrderLine.class, lineId);
        PurchaseOrder loadedOrder =
            verify.find(PurchaseOrder.class, orderId);

        assertEquals(orderId, loadedLine.getOrder().getId());
        assertTrue(
            loadedOrder.getLines().stream()
                .anyMatch(line -> line.getId().equals(lineId))
        );
    } finally {
        verify.close();
    }
}
```

Fixture cần ID strategy, schema và imports tương ứng. Việc verify trong EntityManager mới giúp tránh chỉ kiểm tra các references đang có sẵn trong bộ nhớ.

## 22. Test chứng minh chỉ sửa inverse side không đổi FK

Có thể tạo hai orders và một line thuộc Order A, commit. Sau đó trong transaction mới:

```java
PurchaseOrder orderA = em.find(PurchaseOrder.class, orderAId);
PurchaseOrder orderB = em.find(PurchaseOrder.class, orderBId);
OrderLine line = em.find(OrderLine.class, lineId);

orderA.getLines().remove(line);
orderB.getLines().add(line);

// Cố ý không thay line.order (owning side).
em.flush();
```

Sau đó kiểm tra qua native SQL hoặc context mới rằng `order_lines.order_id` vẫn là `orderAId`.

Test này có mục tiêu minh họa lỗi. Trong code production, collection getter nên có thể read-only; test có thể dùng một fixture cố ý expose collection hoặc một method sai riêng để chứng minh behavior. Không đưa API mutable sai này vào domain chỉ để test.

### 22.1. Không kết luận từ một lần `find()` trong cùng Persistence Context

Nếu entity/collection đã được load, `find()` có thể trả cùng managed instance. Dùng `clear()` khi chỉ cần ép load lại trong cùng transaction, hoặc tốt hơn đóng context và mở một transaction/context mới khi kiểm tra committed state.

## 23. Test owning side thay đổi nhưng collection cũ stale

Một test khác có thể chỉ gọi:

```java
line.setOrder(orderB);
em.flush();
```

Sau flush:
- DB FK có thể đã đổi sang Order B.
- `orderA.getLines()` trong memory có thể vẫn chứa line.
- `orderB.getLines()` có thể chưa chứa line.

Sau `em.clear()`/EntityManager mới, collections sẽ được load theo FK mới (nếu mapping/filter không thay đổi).

Test này cho thấy hai invariant khác nhau:
1. Owning-side write đúng.
2. Object graph hai chiều đồng bộ.

Production code nên giữ cả hai bằng helper method, không chỉ dựa vào việc DB cuối cùng đúng.

## 24. Test chuyển child giữa hai parents

Nếu association không dùng orphanRemoval và domain cho phép reparent:

```java
public void moveLineTo(
        OrderLine line,
        PurchaseOrder target
) {
    PurchaseOrder previous = line.getOrder();

    if (previous != null) {
        previous.removeReferenceOnly(line);
    }

    target.addReferenceOnly(line);
    line.assignOrder(target);
}
```

Đây chỉ là phác thảo; các helper nội bộ phải tránh orphan semantics ngoài ý muốn và cần quản lý hai aggregate theo transaction boundary phù hợp.

Test:
1. Tạo Order A, Order B và Line X thuộc A.
2. Commit.
3. Load cả ba trong context mới.
4. Gọi move operation.
5. Flush/commit.
6. Reload.
7. Assert FK trỏ B.
8. Assert A không còn X.
9. Assert B có X.
10. Assert không có duplicate rows.

Nếu child ID chứa `orderId` bằng `@MapsId`, không dùng workflow UPDATE FK đơn giản vì parent change có thể đổi primary key.

## 25. Test `@ManyToMany` join-table ownership

Giả sử `Student.courses` là owner. Test:
1. Persist Student và Course.
2. Gọi helper `student.enroll(course)` cập nhật cả hai collections.
3. Flush/commit.
4. Query `student_courses`.
5. Reload cả Student và Course.
6. Assert cả hai sides đều chứa đối tượng còn lại.

Sau đó tạo một test âm có chủ đích: chỉ sửa `course.students` inverse collection. Join table không nên được kỳ vọng thay đổi.

Không assert chỉ `course.getStudents().contains(student)` trong context đã sửa collection; đó là assertion trên memory state, không phải database membership.

## 26. Test `@OneToOne` owning side và unique constraint

Với `UserProfile.account` là owner:
- Set `account.profile` nhưng bỏ qua `profile.account`: FK không được ghi như mong muốn.
- Set `profile.account` nhưng không đồng bộ `account.profile`: FK có thể đúng nhưng object graph stale.
- Dùng helper đồng bộ cả hai.
- Tạo hai profiles cùng account: unique constraint phải từ chối.
- Xóa profile theo policy: kiểm tra FK/row state.

Test unique constraint ở database, vì chỉ Java validation không chống được hai transactions cạnh tranh.

## 27. Flush, commit và transaction rollback

Association update thường được gửi SQL tại flush:
- explicit `em.flush()`.
- auto-flush trước query phù hợp.
- flush khi transaction commit.

Nhưng flush không phải commit. Nếu:
1. `line.setOrder(orderB)`.
2. `em.flush()` phát UPDATE FK.
3. Code ném exception.
4. Transaction rollback.

thì database committed state vẫn có thể là Order A.

Test cần phân biệt:
- SQL update đã được phát.
- FK thay đổi trong transaction hiện tại.
- Transaction commit thành công.
- Transaction khác nhìn thấy FK mới.

Không kiểm tra bằng một dòng SQL log rồi kết luận liên kết đã được đổi bền vững.

## 28. `clear()` và EntityManager mới khác nhau thế nào?

`em.clear()`:
- Detach mọi managed entities trong Persistence Context hiện tại.
- Buộc lần truy cập sau cần load lại nếu transaction/context vẫn hoạt động.
- Không commit transaction.
- Không tạo connection hoặc transaction mới.

EntityManager mới:
- Có Persistence Context mới.
- Khi kết hợp transaction mới, phù hợp để xác nhận committed state.
- Tránh nhầm lẫn do L1 cache cũ.

Với test association, ưu tiên commit transaction rồi dùng EntityManager mới để xác minh FK và collections.

## 29. Bulk JPQL/native SQL không đồng bộ object graph tự động

Ví dụ:

```java
em.createQuery("""
    update OrderLine l
    set l.order = :newOrder
    where l.id = :lineId
    """)
    .setParameter("newOrder", orderB)
    .setParameter("lineId", lineId)
    .executeUpdate();
```

Bulk DML đi theo đường query execution, không cập nhật từng managed entity đang có trong Persistence Context theo dirty checking thông thường.

Nếu `line`, `orderA` hoặc `orderB` đã managed:
- Field/collection có thể stale.
- Entity callbacks không chạy như per-entity mutation.
- Envers không nhất thiết ghi lịch sử từng row như managed updates.
- Cần clear/refresh phù hợp sau bulk operation.
- Native SQL còn cần tự giữ FK, tenant, version và cache semantics.

Khi có thể, dùng managed entity và helper method cho một association update thông thường. Dùng bulk DML khi có lý do rõ và quản lý state sau đó.

## 30. Association update với optimistic locking

Nếu child có:

```java
@Version
private long version;
```

Hibernate có thể phát UPDATE với version predicate. Nếu transaction khác đã thay đổi child, thao tác chuyển parent có thể gặp optimistic locking failure.

Test concurrency:
1. T1 và T2 cùng load Line X với version 4.
2. T1 chuyển X sang Order B và commit, version tăng.
3. T2 chuyển X sang Order C với version cũ.
4. T2 flush/commit và nhận optimistic locking conflict.
5. Reload trong context mới, xác nhận X vẫn thuộc B.

Nếu chỉ parent có `@Version`, đừng mặc định child FK update tự kiểm tra parent version. Version bảo vệ entity được versioning theo mapping; test aggregate concurrency contract riêng.

## 31. Constraint database là lớp bảo vệ cuối

Một association mapping đúng vẫn cần DDL đúng:
- FK đảm bảo target tồn tại.
- NOT NULL nếu association bắt buộc.
- UNIQUE cho one-to-one.
- Composite FK cho tenant-aware references.
- Join-table composite/unique key để ngăn duplicate membership.
- Index trên FK cho joins và deletes phù hợp workload.

Ví dụ join table:

```sql
CREATE TABLE student_courses (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
```

Hibernate annotations không thay thế migrations/constraints. Raw SQL hoặc một ứng dụng khác có thể ghi vào cùng database; DB constraints phải bảo vệ invariant độc lập với ORM.

## 32. Trường hợp FK nullable và non-nullable

Nếu `order_id NOT NULL`, child không thể tồn tại độc lập. Test cần xác nhận:
- Persist child thiếu parent bị từ chối.
- Xóa association không được phép nếu domain yêu cầu parent.
- `optional=false` và `nullable=false` khớp business/schema semantics.
- Reparenting có transaction hợp lệ.

Nếu FK nullable:
- `line.order = null` có thể là trạng thái hợp lệ.
- Nhưng domain cần định nghĩa child có thể orphan thật hay không.
- `orphanRemoval` có thể xóa child thay vì giữ FK null.
- Query/report phải xử lý rows không có parent.

`optional=false` là mapping-level requirement; database `NOT NULL` là enforcement ở DB. Nên đồng bộ cả hai khi quan hệ bắt buộc.

## 33. Composite FK và quan hệ nhiều tenant

Giả sử Customer có PK `(tenant_id, customer_no)`. Order tham chiếu bằng cả hai columns. Nếu code chỉ đổi `order.customer` inverse property hoặc chỉ đổi `customerNo` scalar read-only, FK composite có thể vẫn cũ hoặc không nhất quán.

Mapping:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumns({
    @JoinColumn(
        name = "tenant_id",
        referencedColumnName = "tenant_id"
    ),
    @JoinColumn(
        name = "customer_no",
        referencedColumnName = "customer_no"
    )
})
private Customer customer;
```

Owning association là `order.customer`. Khi chuyển customer, thay association đó; không chỉ thay một component của composite FK.

Test hai tenants có cùng `customer_no` để chứng minh DB không cho cross-tenant reference. Nếu `tenant_id` cũng được map thành scalar field trên Order, tránh hai writable mappings cùng điều khiển một column; dùng `insertable=false, updatable=false` cho read-only view hoặc một mapping ownership rõ ràng.

## 34. Vì sao query thấy kết quả khác sau khi sửa association?

Có thể do:
- Chỉ inverse collection đổi trong memory.
- Owning side đổi nhưng inverse collection stale.
- Entity đã được load trong L1 cache.
- Query chạy trước auto-flush theo flush mode/configuration.
- Bulk/native SQL thay DB nhưng không đồng bộ managed state.
- Transaction rollback.
- Đang đọc replica hoặc datasource khác.
- Filter/tenant/soft-delete predicate ẩn target.

Khi debug, kiểm tra theo thứ tự:
1. Đọc mapping và xác định owner.
2. Xem giá trị owning property trước flush.
3. Gọi flush và xem SQL/exception.
4. Query FK bằng SQL trong cùng transaction để biết state tại DB transaction.
5. Commit.
6. Mở EntityManager mới và reload hai phía.
7. Xác nhận datasource/schema/tenant.

Đừng bắt đầu bằng cách thêm cascade hoặc gọi `refresh()` ngẫu nhiên; những thao tác đó không sửa sai ownership mapping.

## 35. Một bộ helper methods nên định nghĩa invariant rõ

Một aggregate có thể cung cấp:

```java
public void addLine(OrderLine line) { ... }

public void removeLine(OrderLine line) { ... }

public boolean containsLine(OrderLine line) { ... }
```

Các invariant nên xác định:
- Child có được thuộc nhiều parents không?
- Có cho reparent không?
- Child đã persistent có được chuyển parent không?
- Xóa khỏi collection là physical delete, soft delete hay detach?
- FK nullable hay bắt buộc?
- Có orphanRemoval không?
- Parent/child có shared lifecycle không?
- Có version/tenant constraints không?

Method name nên phản ánh nghiệp vụ. `removeLine()` có thể nghĩa “hủy dòng” chứ không nhất thiết là “đặt FK null”. Nếu cần deactivate/soft-delete, hãy có method riêng với semantics rõ.

## 36. Không để mutable collection phá invariant

Nếu getter trả collection mutable:

```java
public List<OrderLine> getLines() {
    return lines;
}
```

bất kỳ caller nào cũng có thể:

```java
order.getLines().add(line);
order.getLines().clear();
order.getLines().remove(line);
```

mà bỏ qua helper. Với bidirectional association, đây là nguồn lỗi thường gặp.

Có thể trả read-only view:

```java
public List<OrderLine> getLines() {
    return Collections.unmodifiableList(lines);
}
```

hoặc dùng DTO/read-only accessor. Hibernate vẫn quản lý collection field nội bộ theo mapping.

Không thay collection field trực tiếp bằng một collection mới tùy tiện sau khi entity đã managed; Hibernate dùng persistent collection wrappers để theo dõi changes.

## 37. Test cả state trước và sau reload

Một bộ assertions tốt cho quan hệ bidirectional:

```java
assertSame(orderB, line.getOrder());
assertTrue(orderB.getLines().contains(line));
assertFalse(orderA.getLines().contains(line));
```

Đây là assertions trong memory ngay sau helper.

Sau commit, reload trong context mới và assert lại:

```java
assertEquals(orderBId, reloadedLine.getOrder().getId());
assertTrue(
    reloadedOrderB.getLines().stream()
        .anyMatch(x -> x.getId().equals(lineId))
);
assertFalse(
    reloadedOrderA.getLines().stream()
        .anyMatch(x -> x.getId().equals(lineId))
);
```

Hai nhóm kiểm tra trả lời hai câu hỏi khác nhau:
- Helper có giữ object graph nhất quán không?
- ORM có ghi association đúng vào database không?

## 38. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Child xuất hiện trong parent collection nhưng FK không đổi | Chỉ sửa inverse side | Cập nhật owning property |
| Child mới bị lỗi NOT NULL khi flush | `ManyToOne` owning field vẫn null | Set child parent qua helper trước persist |
| FK đổi nhưng collection cũ vẫn chứa child | Chỉ sửa owning side | Đồng bộ cả hai phía |
| Parent mới không thấy child trong memory | Inverse collection chưa được cập nhật | Helper cập nhật parent collection |
| Thêm `CascadeType.ALL` nhưng FK vẫn cũ | Cascade không quyết định ownership | Sửa association owner |
| `mappedBy` bootstrap lỗi | Trỏ tới tên column hoặc field sai | Dùng tên persistent attribute |
| `@OneToOne` FK không đổi | Chỉ sửa inverse property | Set owning side có `@JoinColumn` |
| `@ManyToMany` không tạo join row | Chỉ sửa collection inverse | Cập nhật collection owning side |
| `@OneToMany` không có `mappedBy` nhưng bị kết luận inverse | Bỏ qua `@JoinColumn`/`@JoinTable` mapping | Đọc association mapping đầy đủ |
| `orphanRemoval` xóa child khi move | Child bị coi là orphan ở parent cũ | Thiết kế move riêng hoặc thay lifecycle mapping |
| `merge()` không đổi như mong đợi | Detached graph inconsistent hoặc bỏ qua object trả về | Đồng bộ graph, dùng managed result |
| `clear()` không làm transaction commit | Nhầm detach với commit | Commit và mở transaction mới |
| Native UPDATE đúng nhưng entity stale | Bulk SQL bypass Persistence Context | Clear/refresh sau khi xử lý transaction |
| FK sai tenant | Composite FK thiếu tenant component | Dùng composite FK và test cross-tenant |
| Duplicate many-to-many rows | Join table thiếu PK/UNIQUE | Thêm constraint `(owner_id,target_id)` |
| `find()` vẫn trả association cũ | L1/L2 cache hoặc transaction snapshot | Context mới, kiểm tra cache/datasource |
| UPDATE không chạy ngay sau setter | Hibernate trì hoãn tới flush | Flush ở điểm test phù hợp |
| FK update rollback | Transaction thất bại sau flush | Verify committed state sau rollback |
| Parent remove không xóa child | Cascade/remove policy không phù hợp | Xác định ORM cascade hay DB FK action |
| DB cascade xóa child nhưng callback không chạy | Database tự cascade ngoài ORM | Không dựa Java lifecycle callback |
| `@MapsId` child đổi parent gây lỗi | Parent ID là một phần primary key | Không mutate persistent identity |

## 39. Quy trình chẩn đoán lỗi “sửa collection nhưng FK không đổi”

**Bước 1 — Xác định cột lưu quan hệ.** FK nằm ở bảng child hay association nằm trong join table?

**Bước 2 — Đọc annotation.** Có `mappedBy` không? `@JoinColumn`/`@JoinTable` nằm ở property nào?

**Bước 3 — Xác định owning side.** Property nào thực sự điều khiển FK/join table?

**Bước 4 — Kiểm tra giá trị owning property.** Child có đang trỏ tới parent mong muốn không?

**Bước 5 — Kiểm tra helper.** Method add/remove có đồng bộ cả hai sides Java không?

**Bước 6 — Tách cascade.** Cascade chỉ truyền lifecycle operation; không dùng nó để thay ownership.

**Bước 7 — Flush.** Xác nhận Hibernate phát SQL hay có constraint/optimistic-lock exception.

**Bước 8 — Kiểm tra DB transaction.** Query FK/join table bằng connection phù hợp.

**Bước 9 — Commit và reload.** Dùng EntityManager mới để xác nhận committed relationship.

**Bước 10 — Kiểm tra edge cases.** Orphan removal, reparenting, composite FK, soft delete, tenant và cache.

## 40. Bài tập tình huống

### Bài 1 — `mappedBy`

`PurchaseOrder.lines` khai báo `mappedBy = "order"`. Field nào điều khiển `order_id`?

**Đáp án:** `OrderLine.order`, phía `@ManyToOne` owning side.

### Bài 2 — Chỉ sửa collection

Code `orderB.getLines().add(line)` nhưng `line.getOrder()` vẫn là orderA. FK sẽ trỏ đâu sau flush?

**Đáp án:** Theo owning side `line.order`, vẫn là orderA; inverse collection không tự đổi FK.

### Bài 3 — Chỉ sửa child reference

`line.setOrder(orderB)` đã flush thành công. Vì sao `orderA.getLines()` có thể vẫn chứa line?

**Đáp án:** Collection inverse đã load trong Persistence Context chưa được helper đồng bộ.

### Bài 4 — Cascade ALL

Thêm `CascadeType.ALL` vào parent collection có sửa lỗi chỉ cập nhật inverse side không?

**Đáp án:** Không. Cascade điều khiển lifecycle propagation, không đổi property ownership.

### Bài 5 — New child

Parent có `cascade=PERSIST`; thêm child mới vào inverse collection nhưng child parent vẫn null. Có chắc FK được gán không?

**Đáp án:** Không. Cascade có thể persist child nhưng không tự suy ra owning reference; FK có thể null và bị constraint từ chối.

### Bài 6 — `mappedBy` value

Database column là `order_id`, child property là `purchaseOrder`. Giá trị `mappedBy` nên là gì?

**Đáp án:** `purchaseOrder`, tên persistent Java attribute.

### Bài 7 — OneToOne

`UserAccount.profile` dùng `mappedBy="account"`, `UserProfile.account` dùng `@JoinColumn`. Bên nào owner?

**Đáp án:** `UserProfile.account`.

### Bài 8 — ManyToMany

`Course.students` dùng `mappedBy="courses"`, `Student.courses` khai báo `@JoinTable`. Bên nào ghi membership?

**Đáp án:** `Student.courses`.

### Bài 9 — Unidirectional OneToMany

`@OneToMany` không có `mappedBy`, khai báo `@JoinColumn` trên parent. Có thể gọi nó là inverse side như bidirectional mapping không?

**Đáp án:** Không. Parent collection sở hữu association trong mapping unidirectional này.

### Bài 10 — Orphan removal

Remove child khỏi collection có `orphanRemoval=true`. Có phải đây là cách an toàn để chuyển child sang parent khác không?

**Đáp án:** Không mặc định. Child có thể bị coi là orphan và bị remove; cần move workflow/mapping riêng.

### Bài 11 — Merge

`em.merge(detachedOrder)` trả về object nào cần tiếp tục thao tác?

**Đáp án:** Object managed được trả về; object truyền vào vẫn detached.

### Bài 12 — Read-only scalar FK

`orderId` được map `insertable=false, updatable=false`, association `order` ghi cùng column. Gán `orderId` có cập nhật FK không?

**Đáp án:** Không. Association owning mapping mới điều khiển ghi.

### Bài 13 — Flush

`line.setOrder(orderB); em.flush();` rồi rollback. FK có đổi bền vững không?

**Đáp án:** Không nếu rollback thành công; flush không phải commit.

### Bài 14 — Clear

Gọi `em.clear()` sau UPDATE association có tương đương commit không?

**Đáp án:** Không. Nó chỉ detach managed entities.

### Bài 15 — Native SQL

JDBC đổi `order_id`, nhưng Java collection vẫn cũ. Vì sao?

**Đáp án:** Native/JDBC update không đồng bộ Persistence Context; cần clear/refresh/reload theo transaction boundary.

### Bài 16 — Composite FK

Order tham chiếu Customer bằng `(tenant_id, customer_no)`. Chỉ đổi `customerNo` scalar có đủ không?

**Đáp án:** Không. Cập nhật owning association và giữ cả hai components nhất quán.

### Bài 17 — Shared many-to-many

Xóa Student có nên cascade REMOVE tới Course không?

**Đáp án:** Thường không; chỉ xóa membership row, Course có lifecycle độc lập.

### Bài 18 — FK NOT NULL

Child không có parent và FK NOT NULL. Lỗi thường xuất hiện ở đâu?

**Đáp án:** Khi INSERT/UPDATE được thực thi, thường tại flush hoặc commit tùy timing/constraint semantics.

### Bài 19 — Version

Hai transactions cùng chuyển một child sang hai parents khác nhau. `@Version` giúp gì?

**Đáp án:** Có thể phát hiện stale update trên child nếu child được versioning và update qua ORM; cần test hai transactions thực.

### Bài 20 — Kiểm chứng đúng

Sau khi helper chạy, assertion nào chứng minh DB relationship đã đúng?

**Đáp án:** Commit rồi mở EntityManager mới, reload child/parents và xác nhận FK/collections; có thể kiểm tra FK bằng SQL trực tiếp.

## 41. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): owning side, inverse side, bidirectional relationships, `mappedBy`, join columns, join tables, cascade và orphan removal.
- [Jakarta Persistence API — `OneToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetomany): `mappedBy`, cascade và orphan-removal contract.
- [Jakarta Persistence API — `ManyToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): many-to-one mapping và optionality.
- [Jakarta Persistence API — `OneToOne`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetoone): owning/inverse mapping cho one-to-one.
- [Jakarta Persistence API — `ManyToMany`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytomany): join table và `mappedBy`.
- [Jakarta Persistence API — `JoinColumn`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/joincolumn): FK column mapping.
- [Jakarta Persistence API — `JoinTable`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/jointable): association join-table mapping.
- [Jakarta Persistence API — `MapsId`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/mapsid): derived identity from an association.
- [Hibernate ORM User Guide — Associations](https://docs.hibernate.org/orm/7.2/userguide/html_single/#associations): Hibernate relationship mappings and association management.
- [Hibernate ORM User Guide — Cascading](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc-cascade): lifecycle cascade and orphan removal.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc): managed entities, dirty checking and persistence context behavior.
- [Spring Data JPA — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html): `save`, `persist` and `merge` integration.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): foreign keys, unique constraints and referential integrity.

**Ghi chú phiên bản:** Association ownership và `mappedBy` là contract Jakarta Persistence, nhưng SQL shape, collection synchronization details, flush timing và một số edge cases phụ thuộc Hibernate version, mapping access strategy và DBMS. Ví dụ SQL dùng tên bảng/cột minh họa. Hãy xác nhận bằng integration tests với đúng Hibernate version, migrations và database triển khai.

## Kết luận

Khi quan hệ bidirectional dùng `@OneToMany(mappedBy = "order")` kết hợp `@ManyToOne`, collection ở parent là inverse side còn reference `OrderLine.order` là owning side. Chỉ thêm hoặc xóa child khỏi collection không đủ để đổi `order_id`; chỉ sửa child reference có thể ghi FK đúng nhưng để collection Java ở parent stale. Một helper method nên cập nhật cả hai phía, còn Hibernate dựa vào owning side để đồng bộ quan hệ xuống database.

Đừng dùng cascade như cách sửa ownership. `CascadeType` quyết định lifecycle operations được lan truyền; `orphanRemoval` quyết định xử lý child bị tách khỏi quan hệ sở hữu; FK và unique constraints bảo vệ dữ liệu ở database. Đồng thời, luôn đọc mapping thực tế: unidirectional `@OneToMany` có `@JoinColumn` là một trường hợp khác với bidirectional mapping dùng `mappedBy`.

Khi kiểm tra lỗi, hãy flush, commit và reload bằng Persistence Context mới; xác nhận FK hoặc join-table rows thay vì chỉ nhìn object graph đang có trong memory. Quy tắc đó giúp phát hiện sớm lỗi inverse-side updates, stale collections, cascade assumptions và các association sai tenant.
