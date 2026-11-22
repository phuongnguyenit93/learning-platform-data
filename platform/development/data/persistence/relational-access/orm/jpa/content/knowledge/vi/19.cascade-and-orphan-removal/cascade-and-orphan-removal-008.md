# Vai trò của orphanRemoval trong quan hệ phù hợp trong JPA

Trong mô hình ORM của **Jakarta Persistence (JPA)**, không phải mọi entity được liên kết với nhau đều có vòng đời độc lập. Một **đơn hàng** có các **dòng hàng**; một **tài khoản** có thể có **hồ sơ phụ thuộc**; một **bài viết** có nhiều **bình luận**. Khi một phần tử bị gỡ khỏi quan hệ, câu hỏi không chỉ là “còn liên kết khóa ngoại hay không?”, mà còn là:

> **Entity con có còn ý nghĩa tồn tại độc lập khi không thuộc entity cha nữa không?**

Annotation **`orphanRemoval = true`** giải quyết trường hợp **entity con phụ thuộc vào quan hệ sở hữu**: nếu một entity con bị loại khỏi quan hệ `@OneToMany` hoặc `@OneToOne` phù hợp, JPA sẽ áp dụng thao tác **remove** cho entity con khi đồng bộ persistence context theo quy tắc của đặc tả.

Ví dụ: xóa dòng “Bút xanh” khỏi đơn hàng không đơn thuần là đổi `order_id` thành `NULL`; dòng hàng đó không còn là phần của đơn, nên cần **xóa hàng child trong database**.

Bài học tập trung vào ý nghĩa nghiệp vụ, phạm vi áp dụng, hành vi flush, tương tác với cascade, owning side, khóa ngoại, chuyển entity giữa cha và các tình huống không nên bật orphan removal.

## 1. Khái niệm orphan trong quan hệ cha–con

Xét mô hình:

~~~text
PurchaseOrder #1001
      |
      +---- OrderLine #11: BOOK-01
      +---- OrderLine #12: PEN-02
      +---- OrderLine #13: BAG-03
~~~

Một `OrderLine` là một phần của `PurchaseOrder`. Nếu người dùng xóa dòng `#12` khỏi đơn:

~~~text
Trước:
PurchaseOrder #1001
      +---- OrderLine #11
      +---- OrderLine #12  <--- remove from collection
      +---- OrderLine #13

Sau:
PurchaseOrder #1001
      +---- OrderLine #11
      +---- OrderLine #13

OrderLine #12?
      └── Không còn vai trò nghiệp vụ: phải DELETE.
~~~

Trong ngữ cảnh này, **`OrderLine#12` trở thành orphan** vì đã bị loại khỏi quan hệ sở hữu mà nó phụ thuộc. Khi `orphanRemoval = true`, ý định “bỏ child khỏi aggregate” được ánh xạ thành ý định “xóa entity child”.

So sánh với trường hợp **Employee** thuộc **Department**:

~~~text
Department A
    +--- Employee #7

Chuyển công tác:
Department A            Department B
    (không còn #7)           +--- Employee #7
~~~

Nhân viên không bị xóa chỉ vì chuyển phòng ban. Tại đây, entity con có định danh và vòng đời **độc lập**, nên `orphanRemoval = true` thường **không phù hợp**. Nghiệp vụ muốn **UPDATE khóa ngoại**, không DELETE nhân viên.

### 1.1. Những câu hỏi quyết định

Trước khi bật orphan removal, hãy trả lời:

1. Child có thể tồn tại hợp lệ khi không có parent không?
2. Child có thể được chuyển sang parent khác mà vẫn giữ cùng identity không?
3. Khi bỏ child khỏi collection hoặc thay association, nghiệp vụ muốn **xóa child** hay chỉ **ngắt liên kết**?
4. Có entity khác đang tham chiếu hoặc dùng child như dữ liệu độc lập không?
5. Parent có chịu trách nhiệm quản lý toàn bộ vòng đời của child không?

Nếu **child không có ý nghĩa độc lập và việc rời khỏi parent phải xóa child**, orphan removal thường phù hợp.

## 2. Phạm vi áp dụng trong JPA

JPA chuẩn cho phép cấu hình thuộc tính `orphanRemoval` trên:

~~~java
@OneToOne(orphanRemoval = true)
private UserProfile profile;
~~~

và:

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;
~~~

**Không có `orphanRemoval` trên `@ManyToOne` hoặc `@ManyToMany`** trong JPA chuẩn.

| Quan hệ | Có thuộc tính `orphanRemoval`? | Ý nghĩa thường gặp |
| --- | --- | --- |
| `@OneToOne` | Có | Child phụ thuộc 1–1 được xóa khi bị loại khỏi association |
| `@OneToMany` | Có | Child bị xóa khi rời collection của parent |
| `@ManyToOne` | Không | Nhiều child có thể cùng tham chiếu một parent; không xóa parent chỉ vì một child đổi tham chiếu |
| `@ManyToMany` | Không | Hai phía có thể chia sẻ entity; gỡ liên kết thường chỉ xóa hàng join table |
| `@ElementCollection` | Không có thuộc tính `orphanRemoval` | Phần tử là basic/embeddable value, không phải entity riêng; provider quản lý hàng collection table theo nội dung collection |

Điểm đặc biệt: orphan removal là **chính sách vòng đời của entity đích** trong association một-một hoặc một-nhiều. Nó không phải cú pháp chung cho mọi dạng collection Java.

### 2.1. Ví dụ phù hợp

- `PurchaseOrder` chứa `OrderLine`: xóa một dòng khỏi đơn đồng nghĩa xóa dòng.
- `BlogPost` chứa `PostRevisionDraft`: bản nháp revision chỉ thuộc bài viết và không còn ý nghĩa khi bị loại bỏ.
- `UserAccount` có `AccountPreferences` độc lập về bảng nhưng phụ thuộc tài khoản: bỏ preferences có thể được định nghĩa là xóa bản ghi preferences.
- `Workflow` chứa `WorkflowStep` có ID riêng nhưng không được phép chuyển sang workflow khác: bỏ bước là xóa bước.

### 2.2. Ví dụ không phù hợp

- `Department` – `Employee`: nhân viên chuyển phòng ban.
- `Category` – `Product`: sản phẩm có thể được phân loại lại.
- `Teacher` – `Course`: khóa học có thể đổi giảng viên mà không bị xóa.
- `Playlist` – `Song` kiểu many-to-many: xóa bài hát khỏi playlist không được xóa bài hát khỏi thư viện.
- `User` – `Role`: một role có thể dùng chung cho nhiều user.

**Đánh giá theo vòng đời nghiệp vụ chứ không chỉ theo tên “cha/con” hay bội số quan hệ.**

## 3. Ví dụ cơ sở dữ liệu: đơn hàng và dòng hàng

Giả sử database có:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_lines_purchase_orders
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT ck_order_lines_quantity
        CHECK (quantity > 0)
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines (order_id);
~~~

Dữ liệu:

| `purchase_orders.id` | `order_code` |
| ---: | --- |
| 1001 | PO-1001 |

| `order_lines.id` | `order_id` | `product_code` | `quantity` |
| ---: | ---: | --- | ---: |
| 11 | 1001 | BOOK-01 | 2 |
| 12 | 1001 | PEN-02 | 4 |
| 13 | 1001 | BAG-03 | 1 |

Cột `order_lines.order_id` là **FK NOT NULL**. Nếu child `#12` bị gỡ khỏi đơn nhưng vẫn tồn tại ở bảng `order_lines` với `order_id = NULL`, database sẽ từ chối vì ràng buộc `NOT NULL`. Trong domain của ví dụ, trạng thái child không có order cũng không hợp lệ.

Với orphan removal, thao tác mong muốn là:

~~~sql
DELETE FROM order_lines WHERE id = 12;
~~~

Thao tác này giữ các child khác và giữ parent `PurchaseOrder#1001`.

### 3.1. Orphan removal không phải điều kiện FK của database

Một ràng buộc FK bảo vệ điều kiện “child tham chiếu parent có tồn tại”. Nó **không tự quyết định** rằng bỏ child khỏi Java collection phải xóa child. Chính mapping JPA `orphanRemoval` kết nối thay đổi quan hệ ở object model với vòng đời remove của target entity.

Do đó, có thể có schema PK/FK đúng nhưng ứng dụng vẫn xử lý sai nếu không đồng bộ owning side, không cấu hình orphan removal khi nghiệp vụ cần, hoặc thao tác lên detached entity ngoài context.

## 4. Ánh xạ @OneToMany với orphanRemoval

Ví dụ Java 17+ dùng Jakarta Persistence 3.x. Những dự án dùng JPA 2.x cũ có các annotation tương ứng trong namespace `javax.persistence.*`.

### 4.1. Entity cha: PurchaseOrder

~~~java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        this.orderCode = Objects.requireNonNull(orderCode);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line");

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException(
                "Line already belongs to a different order");
        }

        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.attachToOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
~~~

Ý nghĩa của mapping:

- `@OneToMany` thể hiện parent quản lý một tập các child.
- `mappedBy = "order"` chỉ field `OrderLine.order` là **owning side** của quan hệ hai chiều.
- `cascade = {PERSIST, MERGE}` cho phép một số thao tác trên parent lan truyền tới child theo cascade được chọn.
- `orphanRemoval = true` nói rằng **target entity bị gỡ khỏi association phải được xử lý theo lifecycle remove**.
- Việc không liệt kê `CascadeType.REMOVE` trong ví dụ **không làm mất ý nghĩa orphan removal**.

Phương thức `getLines()` trả về view không chỉnh sửa được để code bên ngoài không vô tình gọi `getLines().remove(...)` mà quên cập nhật mặt còn lại của association. Nên cung cấp các thao tác nghiệp vụ rõ ràng như `addLine` và `removeLine`.

### 4.2. Entity con: OrderLine

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false, length = 80)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String productCode, int quantity) {
        this.productCode = Objects.requireNonNull(productCode);
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be greater than zero");
        }
        this.quantity = quantity;
    }

    void attachToOrder(PurchaseOrder parent) {
        this.order = Objects.requireNonNull(parent);
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }

    public void changeQuantity(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                "quantity must be greater than zero");
        }
        this.quantity = value;
    }
}
~~~

`OrderLine.order` là **owning side** vì nó chứa `@JoinColumn(name = "order_id")`. Field này cung cấp giá trị FK cho DB. `PurchaseOrder.lines` là inverse side vì có `mappedBy`.

Bản thân `@ManyToOne` **không có thuộc tính `orphanRemoval`**. Annotation đó nằm trên quan hệ `@OneToMany` ở parent.

### 4.3. Vì sao phải đồng bộ cả hai phía?

Một quan hệ hai chiều có **hai tham chiếu ở Java** nhưng **một khóa ngoại trong SQL**:

~~~text
PurchaseOrder.lines ------------> OrderLine
                                      |
                                      | OrderLine.order
                                      v
                                 PurchaseOrder

DB: order_lines.order_id  ------> purchase_orders.id
~~~

Nếu chỉ xóa khỏi `lines` mà vẫn giữ `line.order = parent`, hai phía của object graph không còn nhất quán. Nếu chỉ đặt `line.order = null` mà không xóa khỏi `lines`, collection ở parent vẫn chứa child; provider có thể không nhận diện đúng thao tác orphan theo mapping hoặc cố ghi FK null.

Dùng helper:

~~~java
order.removeLine(line);
~~~

để cập nhật **cả collection lẫn field owning side** trong bộ nhớ.

Trong ví dụ, `line.detachFromOrder()` làm `order` tạm bằng null trong object đã được gỡ. Với orphan removal, ngữ nghĩa cuối cùng là **xóa child khỏi DB**. Không suy luận rằng provider phải phát `UPDATE order_lines SET order_id = NULL` rồi mới `DELETE`. Cách sinh SQL và thứ tự thao tác cụ thể tùy provider, mapping, flush và ràng buộc DB.

## 5. Thực hiện xóa orphan trong một transaction

Giả sử `EntityManagerFactory emf` đã được cấu hình với transaction `RESOURCE_LOCAL`. Ta cần xóa dòng `#12` khỏi đơn hàng `#1001` mà không xóa parent.

~~~java
import jakarta.persistence.EntityManager;
import java.util.Objects;

EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    PurchaseOrder order =
        em.find(PurchaseOrder.class, 1001L);

    if (order == null) {
        throw new IllegalArgumentException("Order not found");
    }

    OrderLine target = order.getLines()
        .stream()
        .filter(line -> Objects.equals(line.getId(), 12L))
        .findFirst()
        .orElseThrow(() ->
            new IllegalArgumentException("Order line not found"));

    order.removeLine(target);

    // Không cần gọi em.remove(target) nữa:
    // orphanRemoval = true biểu diễn việc xóa target.
    em.getTransaction().commit();

} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Provider nhận diện `OrderLine#12` bị loại khỏi association. Khi đồng bộ context và hoàn tất transaction phù hợp, thao tác logic tương đương:

~~~sql
DELETE FROM order_lines
WHERE id = 12;
~~~

Đối tượng `PurchaseOrder#1001` vẫn tồn tại. Dòng `#11` và `#13` vẫn tồn tại và vẫn tham chiếu `order_id = 1001`.

### 5.1. Thời điểm DELETE có thể khác thời điểm gọi removeLine

Trong transaction:

~~~text
begin transaction
     |
     | order.removeLine(line)
     v
Java collection đã bỏ phần tử
     |
     | JPA nhận diện thay đổi quan hệ
     |
     | flush (tường minh hoặc tự động)
     v
SQL DELETE orphan nếu thuộc phạm vi áp dụng
     |
     | commit
     v
Xóa được xác nhận nếu transaction thành công
~~~

Việc gọi `order.removeLine(line)` **không tự thực hiện commit**. Provider có thể hoãn SQL tới flush/commit. Nếu transaction rollback, thao tác xóa chưa commit sẽ không trở thành thay đổi bền vững trong DB.

### 5.2. Kiểm chứng dữ liệu sau commit

Nếu cần kiểm tra tại một transaction/EntityManager mới:

~~~java
EntityManager verifyEm = emf.createEntityManager();

try {
    OrderLine deleted = verifyEm.find(OrderLine.class, 12L);
    PurchaseOrder remaining =
        verifyEm.find(PurchaseOrder.class, 1001L);

    System.out.println(deleted == null);   // true nếu xóa thành công
    System.out.println(remaining != null); // true
} finally {
    verifyEm.close();
}
~~~

Đoạn này mô tả kết quả mong muốn; dữ liệu thực tế phải tồn tại trước đó như trong ví dụ. Không nên chỉ dựa vào giá trị của một reference Java cũ sau `remove` để kết luận database đã commit.

## 6. CascadeType.REMOVE và orphanRemoval khác nhau thế nào?

Hai khái niệm đều có thể dẫn tới xóa entity đích, nhưng **tác nhân kích hoạt khác nhau**.

- **CascadeType.REMOVE**: khi ứng dụng gọi `em.remove(parent)`, thao tác remove có thể được **lan truyền tới child** nếu quan hệ khai báo cascade REMOVE.
- **orphanRemoval = true**: khi child **không còn thuộc quan hệ sở hữu** vì bị gỡ khỏi collection hoặc association, JPA áp dụng remove cho child vào lúc đồng bộ theo ngữ nghĩa orphan removal.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
~~~

Khai báo này xử lý tình huống **xóa toàn bộ parent**. Nó **không thay thế** `orphanRemoval` cho thao tác chỉ bỏ một child khỏi `lines` trong khi parent còn tồn tại.

Ngược lại:

~~~java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

cho phép child bị xóa khi bị gỡ khỏi association. Theo quy tắc JPA, nếu thao tác remove được áp dụng lên **managed source entity**, thao tác remove còn được cascade tới target của quan hệ `orphanRemoval = true` theo ngữ nghĩa tương ứng, **ngay cả khi không khai báo riêng `cascade = REMOVE`**.

Vì vậy không nên nói “orphanRemoval chỉ hoạt động khi xóa phần tử, không bao giờ liên quan lúc xóa parent”. Điều đúng là **orphan removal bổ sung ngữ nghĩa xóa child khi quan hệ bị phá vỡ, đồng thời có quy tắc cascade khi parent bị remove**.

### 6.1. Bảng quyết định

| Nghiệp vụ | `cascade=REMOVE`, không orphanRemoval | `orphanRemoval=true` |
| --- | --- | --- |
| Xóa một child khỏi List, parent còn tồn tại | Không tự bảo đảm child bị DELETE chỉ nhờ cascade REMOVE | Child thuộc phạm vi orphan removal sẽ bị remove |
| Xóa parent đang managed | Remove được cascade tới các child liên quan | Remove cũng được cascade theo ngữ nghĩa orphan removal |
| Chỉ thay đổi một trường của child | Không liên quan tới xóa | Không tự xóa child |
| Chuyển child sang parent khác | Không được giải quyết chỉ bằng cascade REMOVE | **Không phù hợp** nếu child bị coi là orphan; không được dựa vào reparenting |
| Truy vấn bulk DELETE bằng JPQL | Không áp dụng lifecycle cascade thông thường | Không áp dụng orphan detection thông thường |
| Xóa child qua `em.remove(child)` | Xóa trực tiếp theo lời gọi | Có thể không cần orphan detection nhưng phải giữ object graph nhất quán |

### 6.2. CascadeType.ALL có chứa orphanRemoval không?

Không. `CascadeType.ALL` tương đương nhóm các kiểu cascade JPA như `PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH`, nhưng **không phải thuộc tính orphanRemoval**.

~~~java
// Cascade ALL không tự bật orphanRemoval.
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<OrderLine> lines;
~~~

Nếu nghiệp vụ muốn cả cascade đầy đủ và xóa orphan:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Tuy nhiên, **`ALL` không phải mặc định cần thiết**. Hãy khai báo các loại cascade theo vòng đời nghiệp vụ và dùng orphanRemoval độc lập khi cần. Cascade quá rộng có thể gây xóa dữ liệu ngoài ý muốn, nhất là trên quan hệ không thực sự sở hữu vòng đời child.

## 7. Orphan removal không giống ON DELETE CASCADE của database

Ràng buộc database có thể khai báo:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_order_lines_order_cascade
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE;
~~~

Đây là **một biến thể schema**. Nếu dùng ví dụ này, phải thay thế constraint FK cũ chứ không thêm trùng cả hai ràng buộc trên cùng mục đích.

`ON DELETE CASCADE` làm database xóa các child **khi parent row bị DELETE**. Nhưng nó không biết chương trình Java vừa gọi `order.getLines().remove(line)` để gỡ một phần tử khỏi collection. Lời gọi đó không phải là một SQL DELETE parent để kích hoạt DB cascade.

| Cơ chế | Nơi quyết định | Kích hoạt điển hình |
| --- | --- | --- |
| `orphanRemoval = true` | Mapping JPA | Child bị bỏ khỏi quan hệ sở hữu |
| `CascadeType.REMOVE` | Mapping JPA | Entity source được `em.remove(...)` |
| `ON DELETE CASCADE` | Constraint database | Database thực thi DELETE parent |
| `ON DELETE SET NULL` | Constraint database | Database xóa parent và gán FK child bằng NULL, nếu schema cho phép |

Các cơ chế không hoàn toàn thay thế nhau:

- Database cascade có thể xóa row child mà không chạy đầy đủ JPA entity callbacks như một lệnh `em.remove(child)` riêng.
- Provider cascade remove có thể thực thi SQL xóa child trước parent để thỏa FK.
- Nếu trộn ORM cascade và DB cascade, cần xét cache, callback, trạng thái các entity đang managed và thứ tự SQL.

**Không bật `ON DELETE CASCADE` chỉ để mong thao tác gỡ một phần tử khỏi Java collection được đồng bộ**. Đó là nhiệm vụ của ORM mapping/logic nghiệp vụ.

## 8. @OneToOne và orphanRemoval

Orphan removal cũng phù hợp với quan hệ **1–1 mà entity phụ thuộc chỉ có một owner**.

Ví dụ tài khoản và hồ sơ mở rộng:

~~~text
UserAccount #42
     |
     +--- AccountProfile #42

user_accounts           account_profiles
-------------           ----------------
id (PK) <-------------- user_id (PK + FK)
email                   display_name
~~~

Khi người dùng quyết định xóa phần hồ sơ mở rộng nhưng giữ tài khoản, nghiệp vụ muốn xóa `AccountProfile#42`.

### 8.1. Quan hệ hai chiều với khóa chính chia sẻ

Giả sử `UserAccount` là entity chính có `Long id`:

~~~java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private AccountProfile profile;

    protected UserAccount() {
    }

    public void setProfile(AccountProfile next) {
        if (this.profile == next) {
            return;
        }

        if (this.profile != null) {
            this.profile.unlinkAccount();
        }

        this.profile = next;

        if (next != null) {
            next.linkAccount(this);
        }
    }

    public Long getId() {
        return id;
    }

    public AccountProfile getProfile() {
        return profile;
    }
}
~~~

Entity phụ thuộc:

~~~java
@Entity
@Table(name = "account_profiles")
public class AccountProfile {

    @Id
    @Column(name = "user_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private UserAccount account;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected AccountProfile() {
    }

    public AccountProfile(String displayName) {
        this.displayName = displayName;
    }

    void linkAccount(UserAccount account) {
        this.account = account;
    }

    void unlinkAccount() {
        this.account = null;
    }

    public Long getId() {
        return id;
    }
}
~~~

Ở đây `@MapsId` cho biết `AccountProfile.id` dùng cùng định danh với `UserAccount.id`. `orphanRemoval` nằm ở phía parent `UserAccount.profile` vì profile có vòng đời phụ thuộc vào account.

### 8.2. Xóa profile nhưng giữ account

~~~java
em.getTransaction().begin();

UserAccount account = em.find(UserAccount.class, 42L);

if (account != null && account.getProfile() != null) {
    account.setProfile(null);
}

em.getTransaction().commit();
~~~

Ý nghĩa:

- Reference `account.profile` không còn trỏ tới profile.
- Phía owning `profile.account` cũng được đồng bộ trong object graph.
- Orphan removal yêu cầu provider xóa profile khi đồng bộ.
- `UserAccount#42` vẫn tồn tại.

SQL logic:

~~~sql
DELETE FROM account_profiles WHERE user_id = 42;
~~~

### 8.3. Cần thận trọng khi thay profile bằng instance khác

Với shared primary key, việc thay thế profile có thể liên quan tới **DELETE profile cũ rồi INSERT profile mới với cùng khóa chính**. Nếu provider thực thi insert trước delete, unique/PK constraint có thể phát sinh lỗi.

Không nên xem:

~~~java
account.setProfile(new AccountProfile("New profile"));
~~~

là thao tác thay child luôn portable và an toàn trong cùng một flush, đặc biệt khi hai entity có chung identity. Nếu chỉ muốn đổi nội dung, **cập nhật profile đang managed**. Nếu thật sự cần thay bản ghi, thiết kế transaction, thứ tự xóa/tạo và schema cần được kiểm soát rõ.

Ngoài ra, sau khi orphan removal đã áp dụng lên một profile, không được “tái sử dụng” đối tượng đó bằng cách gán ngay sang một parent khác như thể nó vẫn là entity mới.

## 9. Vì sao @ManyToMany không có orphanRemoval?

Giả sử bài hát có thể được dùng trong nhiều playlist:

~~~text
Playlist A ----\
                \---- Song #7
Playlist B ----/
~~~

Ánh xạ:

~~~java
@ManyToMany
@JoinTable(
    name = "playlist_songs",
    joinColumns = @JoinColumn(name = "playlist_id"),
    inverseJoinColumns = @JoinColumn(name = "song_id")
)
private Set<Song> songs = new HashSet<>();
~~~

Nếu gọi:

~~~java
playlistA.getSongs().remove(song7);
~~~

nghiệp vụ thường là **xóa hàng liên kết** giữa playlist A và song 7 khỏi `playlist_songs`, không xóa `Song#7`. Bởi vì playlist B và những thực thể khác vẫn có thể dùng song đó.

~~~sql
DELETE FROM playlist_songs
WHERE playlist_id = :playlistA
  AND song_id = 7;
~~~

**Không dùng `CascadeType.REMOVE` bừa bãi trên many-to-many** để mô phỏng orphan removal. Nó có thể làm ORM cố xóa `Song` được dùng chung, gây mất dữ liệu hoặc vi phạm FK.

Nếu thật sự cần “xóa liên kết thì xóa luôn đối tượng liên kết có ID và dữ liệu riêng”, hãy mô hình hóa join table thành một **association entity**:

~~~text
Playlist 1--N PlaylistEntry N--1 Song
                 |
                 +-- entryId, position, addedAt
~~~

`PlaylistEntry` có thể thuộc vòng đời `Playlist` và dùng `@OneToMany(orphanRemoval=true)`. `Song` vẫn độc lập và không bị xóa khi PlaylistEntry biến mất.

## 10. @ElementCollection đã quản lý phần tử như value

Giả sử entity có tập các chuỗi số điện thoại phụ:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag_value")
    private Set<String> tags = new HashSet<>();
}
~~~

`String` là **basic value** trong element collection, không phải entity có `@Id`. Khi một giá trị bị loại khỏi collection, JPA đồng bộ dữ liệu collection table theo mapping, có thể thực hiện DELETE hàng tương ứng.

Không cần và không thể viết:

~~~java
// @ElementCollection không có thuộc tính orphanRemoval.
// @ElementCollection(orphanRemoval = true)  // Sai API
~~~

`orphanRemoval` dành cho relationship tới **entity** qua `@OneToOne` và `@OneToMany`, không phải cơ chế bắt buộc cho mọi thao tác xóa hàng collection table.

## 11. Gỡ liên kết, xóa entity và chuyển owner là ba nghiệp vụ khác nhau

Xét ba thao tác với `OrderLine#12`:

### 11.1. Bỏ một dòng hàng khỏi đơn

~~~java
order.removeLine(line);
~~~

Với `orphanRemoval=true`: mong muốn **DELETE child**.

### 11.2. Xóa toàn bộ đơn hàng

~~~java
em.remove(order);
~~~

Với quan hệ orphanRemoval phù hợp: remove được lan truyền tới các child theo ngữ nghĩa của JPA; có thể cần SQL DELETE child trước parent nếu FK không có database cascade.

### 11.3. Chuyển nhân viên sang phòng ban khác

~~~java
employee.changeDepartment(newDepartment);
~~~

Với `Department.employees` **không orphanRemoval**, mong muốn **UPDATE employees.department_id**, giữ nguyên employee.

Bảng so sánh:

| Nghiệp vụ | Child có tồn tại sau thao tác? | Dạng thay đổi SQL logic |
| --- | --- | --- |
| Bỏ `OrderLine` ra khỏi đơn | Không | DELETE child |
| Xóa đơn cùng các dòng phụ thuộc | Không | DELETE child và parent |
| Chuyển `Employee` từ A sang B | Có | UPDATE FK từ A sang B |
| Gỡ `Song` khỏi playlist | Có | DELETE một join-table row |
| Bỏ `String` khỏi `@ElementCollection` | Không phải entity riêng | Đồng bộ collection table |

**Không chọn orphanRemoval chỉ vì quan hệ là 1–N.** Hãy chọn nó khi thao tác rời association mang đúng ý nghĩa delete child.

## 12. Không “reparent” entity đã trở thành orphan

Theo quy tắc JPA, khi một entity đã bị xử lý theo orphan removal, ứng dụng không nên gán lại nó sang một relationship khác hay cố “giữ sống” bằng cách tiếp tục persist. Với một số trạng thái entity, hành vi cố chuyển orphan có thể không được xác định portable.

Ví dụ nên tránh:

~~~java
// Mapping ở Order A bật orphanRemoval=true.
orderA.removeLine(line);

// Không nên cho cùng instance line được "cứu" bằng:
orderB.addLine(line);
~~~

Đoạn code trên ngụ ý **chuyển ownership** nhưng mapping của order A nói rằng child bị gỡ phải **bị xóa**. Đây là hai ý định mâu thuẫn.

Nếu nghiệp vụ thực sự cần chuyển:

1. **Không dùng orphan removal** cho quan hệ có child độc lập.
2. Giữ child managed, đổi owning side `line.parent` sang parent mới.
3. Cập nhật collection của cả hai parent cho nhất quán.
4. Đánh giá NOT NULL, FK, unique key và concurrency.

Nếu child được định danh bằng khóa ghép có chứa ID parent, chuyển owner còn có thể đồng nghĩa **đổi primary key**, vốn không phải thao tác sửa managed entity thông thường. Khi đó cần xem lại identity model hoặc tạo child mới theo nghiệp vụ.

## 13. Flush, transaction và thời điểm orphan bị xóa

Lời gọi:

~~~java
order.removeLine(line);
~~~

thường mới thay đổi trạng thái managed graph. JPA có thể thực hiện DELETE lúc:

- Gọi `em.flush()` tường minh.
- Provider tự flush theo yêu cầu khi thực hiện truy vấn phù hợp.
- Transaction được commit và còn các thay đổi phải đồng bộ.

Ví dụ:

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

OrderLine toRemove =
    order.getLines().get(0);

order.removeLine(toRemove);

em.flush(); // Yêu cầu đồng bộ thao tác xóa orphan.

em.getTransaction().commit();
~~~

**Flush không commit.** Nếu transaction rollback sau khi SQL DELETE đã chạy, thay đổi delete chưa commit có thể bị hủy bởi DB.

### 13.1. Nếu child mới vừa được tạo rồi bị bỏ đi?

Đặc tả JPA lưu ý semantics orphan removal được áp dụng cho **target entity phù hợp**, và **không bắt buộc** áp dụng theo cùng cách với entity **new, detached hoặc đã removed**. Đối với các đối tượng trong những trạng thái này, không dựa vào một hành vi xóa cụ thể để thiết kế nghiệp vụ portable.

Ví dụ:

~~~java
OrderLine draft = new OrderLine("DRAFT-SKU", 1);

order.addLine(draft);
order.removeLine(draft);

// Không nên viết nghiệp vụ phụ thuộc vào một câu SQL DELETE
// cho draft vốn có thể chưa từng được INSERT vào database.
~~~

Nếu draft chưa được persist, có thể không có hàng DB để DELETE. Mục tiêu ở đây là kết quả nghiệp vụ hợp lý, không phải “mỗi remove khỏi collection luôn phát ra DELETE”.

### 13.2. Sau flush lỗi thì làm gì?

Orphan removal có thể gây lỗi vì child đang được bảng khác tham chiếu:

~~~text
order_lines.id = 12
shipment_items.order_line_id = 12 (FK NOT NULL)
~~~

Khi JPA xóa `OrderLine#12` nhưng vẫn còn `ShipmentItem` tham chiếu, database có thể báo **foreign key violation**. Không xử lý bằng cách tắt FK hoặc giữ lại child “ma” không thuộc order.

Cần quyết định nghiệp vụ:

- Có cho phép xóa dòng hàng đã tạo shipment không?
- Có cần xóa/điều chỉnh các entity phụ thuộc trước không?
- Có nên ngăn xóa bằng validation, trạng thái đơn hoặc permission?
- Có phải `OrderLine` sau khi có shipment thực chất đã có vòng đời/identity độc lập hơn dự tính?

Nếu flush lỗi, transaction có thể bị đánh dấu rollback-only; phải rollback hoặc để transaction manager xử lý, không tiếp tục ghi bừa trên cùng transaction.

## 14. Orphan removal với collection lazy

Một `@OneToMany` mặc định là **LAZY**. Khi service tải parent:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
~~~

có thể `order.lines` chưa được khởi tạo. Code:

~~~java
OrderLine line = order.getLines().stream()
    .filter(x -> java.util.Objects.equals(x.getId(), lineId))
    .findFirst()
    .orElseThrow();

order.removeLine(line);
~~~

có thể khiến provider tải collection trước khi tìm phần tử. Điều này không sai, nhưng với đơn hàng có hàng nghìn dòng, chỉ để xóa một item có thể tốn tài nguyên.

Các phương án tùy use case:

1. Query child theo ID và kiểm tra nó thuộc đúng parent, rồi xóa child bằng cách dùng API vòng đời phù hợp.
2. Query có chủ đích để lấy parent và tập phần tử cần thao tác.
3. Nếu thao tác là bulk delete, hiểu rõ rằng bulk JPQL không áp dụng orphan detection/callback tương tự thao tác managed association.
4. Cân nhắc batching, query strategy và quyền truy cập dữ liệu khi xóa.

Orphan removal là **ngữ nghĩa vòng đời**, không tự bảo đảm truy vấn xóa một phần tử là tối ưu trong mọi workload.

### 14.1. Tìm child đúng theo owner

Trong ứng dụng nhiều người dùng, không được lấy bất kỳ `OrderLine` nào theo ID rồi xóa mà không xác thực nó thuộc đơn hàng được phép thao tác.

Ví dụ query:

~~~java
List<OrderLine> matches = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    WHERE l.id = :lineId
      AND l.order.id = :orderId
    """,
    OrderLine.class
)
.setParameter("lineId", lineId)
.setParameter("orderId", orderId)
.getResultList();
~~~

Việc query theo parent và child cùng lúc giúp giới hạn dữ liệu về đúng aggregate. Điều kiện quyền truy cập vẫn phải được kiểm tra theo security context, không chỉ dựa vào ID được client gửi.

Sau khi có child phù hợp, nếu cần thực hiện **orphanRemoval thông qua collection**, vẫn phải cập nhật đúng association trên managed parent theo cách provider nhận diện. Nếu logic quyết định `em.remove(child)` trực tiếp, đó là **explicit remove**, không phải việc “tự kích hoạt orphanRemoval mà không đổi association”.

## 15. Bulk JPQL DELETE không kích hoạt orphanRemoval như collection mutation

Ví dụ:

~~~java
int deleted = em.createQuery(
    """
    DELETE FROM OrderLine l
    WHERE l.order.id = :orderId
    """
)
.setParameter("orderId", orderId)
.executeUpdate();
~~~

Đây là **bulk JPQL DELETE**, không phải gọi `order.removeLine(line)` trên từng managed entity.

Theo ngữ nghĩa của JPA, bulk DML tác động trực tiếp tới database và không vận hành giống entity lifecycle/remove cascade thông thường. Vì vậy:

- Không kỳ vọng `orphanRemoval` tự áp dụng cho các association khác.
- Không kỳ vọng lifecycle callback `@PreRemove` trên từng child được thực thi như khi provider remove từng managed entity.
- Managed entities đã tải trước bulk delete có thể có trạng thái stale trong persistence context.
- Cần cân nhắc `flush()` trước bulk operation, `clear()`/refresh hoặc dùng một context phù hợp sau đó.

Ví dụ nếu parent collection `lines` đã loaded trước bulk DELETE, Java collection đó không tự xóa các phần tử chỉ vì SQL bulk đã xóa DB rows. Đây là lý do không trộn tùy tiện bulk delete với thao tác orphan removal trên cùng object graph mà không có chiến lược đồng bộ.

## 16. Thao tác trên detached entity và merge

Giả sử một `PurchaseOrder` được tải rồi `EntityManager` đóng. Collection có thể đã được loaded, và một controller sửa List trên object detached:

~~~java
PurchaseOrder detached = loadOrderAndCloseEntityManager();

// Tác động lên object detached, chưa có managed context theo dõi:
detached.removeLine(detached.getLines().get(0));
~~~

Việc sửa detached object **không tự tạo SQL DELETE**. Để đồng bộ một graph detached, có thể dùng `merge` trong transaction với cascade phù hợp:

~~~java
em.getTransaction().begin();

PurchaseOrder managedCopy = em.merge(detached);

em.getTransaction().commit();
~~~

Nhưng có các điểm cần thận trọng:

- `merge` trả về **managed copy**, không biến chính detached instance thành managed.
- Kết quả xử lý collection và orphan phụ thuộc mapping, trạng thái tải, cascade, identity và provider phù hợp.
- Với graph lớn, việc merge một collection stale có thể gây xóa nhầm child đã được người khác tạo sau khi graph được tải.
- Không dựa vào behavior của entity mới hoặc detached như thể orphanRemoval luôn phát cùng SQL trên mọi provider.

Đối với các API chỉnh sửa collection quan trọng, cách dễ kiểm soát thường là **trong transaction, tải managed parent theo ID và thực hiện đúng thao tác domain**:

~~~java
@Transactional
public void removeLine(Long orderId, Long lineId) {
    PurchaseOrder managed = repository.findById(orderId)
        .orElseThrow();

    OrderLine line = managed.getLines().stream()
        .filter(item -> java.util.Objects.equals(item.getId(), lineId))
        .findFirst()
        .orElseThrow();

    managed.removeLine(line);
}
~~~

Đoạn code trên giả định `repository` là Spring Data JPA repository của `PurchaseOrder`; kiểm tra quyền và điều kiện nghiệp vụ cần được bổ sung trong service thực tế.

## 17. Set, List, Map và cách xác định child bị gỡ

`@OneToMany` có thể sử dụng các kiểu collection được JPA hỗ trợ. Với orphan removal, điều quan trọng là **provider có thể xác định phần tử nào bị loại khỏi association**.

### 17.1. List

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
~~~

`List.remove(index)` hoặc `List.remove(object)` làm phần tử rời collection. Nếu ứng dụng cần giữ thứ tự vị trí như dữ liệu, có thể dùng `@OrderColumn` theo mapping phù hợp, nhưng việc cập nhật index là vấn đề khác với orphan deletion.

Một item bị xóa có thể dẫn tới:

- `DELETE` child nhờ orphan removal.
- Các `UPDATE` cột vị trí của những item còn lại nếu có order column.

`orphanRemoval` không tự quản lý thứ tự List và không đồng nghĩa `@OrderColumn`.

### 17.2. Set

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private Set<OrderLine> lines = new HashSet<>();
~~~

`Set` dựa vào `equals/hashCode` để quản lý membership. Nếu entity được đưa vào `HashSet` khi ID chưa có, rồi `hashCode` thay đổi sau khi JPA cấp ID, thao tác `remove` có thể không tìm được phần tử như dự kiến.

Cần thiết kế equality/hashing ổn định phù hợp với entity lifecycle và proxy, hoặc tránh dùng ID sinh muộn làm hash code thay đổi khi object đã ở Set.

**Nếu `remove(child)` trên Set không thực sự loại phần tử ra khỏi collection**, không thể coi child đã orphan chỉ vì application “đã gọi remove”.

### 17.3. Map

Có thể ánh xạ collection entity dưới dạng `Map<K,V>` khi mapping hợp lệ. Nếu một entry có giá trị là một **child entity phụ thuộc vòng đời**, `@OneToMany(orphanRemoval=true)` có thể được dùng theo ngữ nghĩa quan hệ entity. Khi ứng dụng xóa entry và **value entity** không còn trong association, nó có thể trở thành orphan.

Không nhầm giá trị `Map` hoặc `@MapKeyColumn` với identity của entity; map key là cơ chế truy xuất entry, còn `orphanRemoval` áp dụng tới **target entity** tương ứng.

## 18. Concurrency: khi hai người cùng sửa danh sách con

Giả sử user A xóa `OrderLine#12`, user B cùng lúc sửa quantity của chính dòng đó.

~~~text
Transaction A                     Transaction B
--------------------------        --------------------------
LOAD Order #1001, Lines          LOAD Line #12
removeLine(Line #12)             changeQuantity(10)
FLUSH / DELETE #12               FLUSH / UPDATE #12
COMMIT?                           COMMIT?
~~~

Kết quả phụ thuộc mức isolation, thứ tự khóa, optimistic locking và provider. Một transaction có thể thất bại vì optimistic lock, deadlock hoặc hàng không còn tồn tại.

Nếu business muốn phát hiện chỉnh sửa cạnh tranh, cân nhắc:

~~~java
@Version
@Column(name = "version")
private Long version;
~~~

đặt trên entity phù hợp và sử dụng transaction boundary có kiểm soát.

Lưu ý:

- `@Version` trên parent không được mặc định tăng mỗi lần collection đổi trong mọi mapping/provider.
- `@Version` trên child giúp nhận diện một số xung đột khi cập nhật/xóa chính child.
- Việc **xóa và cập nhật trên cùng child** cần quy tắc nghiệp vụ phù hợp: cho phép xóa thắng, hay từ chối xóa nếu child đã được xử lý?
- FK/unique constraint vẫn cần có ở database để bảo vệ tính toàn vẹn, không thay thế bằng optimistic locking.

### 18.1. Đã có shipment thì có được xóa order line?

Nếu một dòng hàng đã được dùng trong hóa đơn hoặc lô hàng, xóa vật lý có thể làm mất lịch sử nghiệp vụ. Khi đó, mô hình **orphanRemoval=true** có thể không còn phù hợp cho phép thao tác xóa tự do.

Các phương án:

1. Chỉ cho phép xóa dòng khi đơn còn `DRAFT`.
2. Đánh dấu dòng `CANCELLED` thay vì xóa vật lý.
3. Tách mô hình dòng nháp và dòng đã chốt.
4. Giữ audit/history trong một bảng/aggregate riêng theo yêu cầu.
5. Ngăn xóa nếu có child khác tham chiếu bằng FK và validation domain.

**Orphan removal là quyết định về vòng đời và retention của dữ liệu, không đơn thuần là tiện ích tiết kiệm một lệnh `em.remove`.**

## 19. Soft delete không tự sinh ra từ orphanRemoval

Một số hệ thống dùng **soft delete**:

~~~text
order_lines:
  id
  order_id
  product_code
  deleted_at
~~~

Thay vì `DELETE FROM order_lines`, nghiệp vụ chỉ cập nhật `deleted_at` để giữ lịch sử.

`orphanRemoval = true` theo semantics JPA có nghĩa **remove entity**. Nó **không tự biến thành cập nhật `deleted_at`** một cách portable.

Một số provider có tính năng soft-delete hoặc SQL delete customization, nhưng đó là cấu hình riêng và có các hệ quả về query filter, uniqueness, cascade, cache và FK. Nếu không sử dụng giải pháp provider-specific có kiểm soát, hãy triển khai thao tác nghiệp vụ `cancelLine`/`archiveLine` rõ ràng, thay vì bật orphanRemoval rồi kỳ vọng một soft-delete xảy ra.

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Bỏ child và xóa vĩnh viễn bản ghi | `orphanRemoval = true` nếu quan hệ phù hợp |
| Bỏ child nhưng giữ bản ghi như lịch sử | Soft delete hoặc archive có chủ đích |
| Chuyển child sang owner khác | Không dùng orphan removal cho thao tác chuyển |
| Chỉ ngắt link, child vẫn tồn tại | FK nullable hoặc join table, không orphan removal |
| Xóa parent cùng toàn bộ child phụ thuộc | Cascade remove/orphanRemoval hoặc policy DB phù hợp |

## 20. Trường hợp OneToMany với join table

Quan hệ một-nhiều có thể được ánh xạ qua một **join table**, đặc biệt khi unidirectional:

~~~java
@OneToMany(
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
@JoinTable(
    name = "order_line_links",
    joinColumns = @JoinColumn(name = "order_id"),
    inverseJoinColumns = @JoinColumn(name = "line_id")
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Ở đây association được lưu qua `order_line_links` thay vì field `order_id` trực tiếp trên `OrderLine`.

Với `orphanRemoval = true`, target `OrderLine` bị gỡ khỏi association được xem là orphan theo mapping: ý định là **xóa target entity**, đồng thời xử lý các row liên kết liên quan. Nếu chỉ muốn **xóa row liên kết nhưng giữ OrderLine**, không nên bật orphan removal.

Cần xem constraint `UNIQUE(line_id)` hoặc thiết kế schema khác để ràng buộc một-nhiều thực sự: một child không được liên kết với nhiều parent nếu đó là invariant. Nếu muốn child được nhiều parent chia sẻ, đó thường là many-to-many và không nên coi child là owned orphan.

## 21. Kiểm tra câu SQL đúng theo mục đích nghiệp vụ

Một log có thể chứa:

~~~text
DELETE FROM order_lines WHERE id = ?
~~~

khi gỡ một dòng khỏi đơn có orphanRemoval.

Hoặc có thể thấy:

~~~text
UPDATE order_lines SET order_id = NULL WHERE id = ?
~~~

khi ngắt quan hệ **không dùng orphanRemoval** và FK nullable. Nếu FK `NOT NULL`, lệnh UPDATE NULL có thể bị từ chối.

Các bước điều tra khi hành vi không như mong muốn:

| Cần xem | Câu hỏi cần trả lời |
| --- | --- |
| `@OneToMany` / `@OneToOne` | Quan hệ có orphanRemoval thực sự hay không? |
| `mappedBy` | Field nào là owning side? |
| Helper method | Cả hai phía được cập nhật nhất quán chưa? |
| Entity state | Child đang managed, new, detached hay removed? |
| Persistence context | Parent/collection có được quản lý trong transaction không? |
| Flush | Lúc nào provider đồng bộ thay đổi? |
| FK | Cột có nullable không, có bảng khác tham chiếu child không? |
| Cascade | Có PERSIST/MERGE/REMOVE đúng với vòng đời không? |
| Bulk SQL | Có thao tác delete/update trực tiếp bỏ qua lifecycle ORM không? |
| Concurrency | Có transaction khác đang sửa child không? |

Không nên chỉ nhìn annotation rồi đoán chính xác SQL hay thời điểm SQL xảy ra. JPA quy định semantics, còn provider có quyền lựa chọn chiến lược đồng bộ trong khuôn khổ đó.

## 22. Những lỗi thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Xóa khỏi List nhưng row vẫn còn | Chưa có orphanRemoval, child chưa bị gỡ thật, hoặc state không managed | Kiểm tra mapping, helper và transaction |
| `UPDATE order_id = NULL` gây lỗi | FK NOT NULL nhưng nghiệp vụ chỉ ngắt liên kết | Nếu child phải bị xóa, dùng lifecycle phù hợp; nếu chuyển owner, UPDATE FK tới owner mới |
| Xóa parent nhưng child còn gây lỗi FK | Chưa có cascade remove hoặc policy DB phù hợp | Thiết kế vòng đời xóa và constraint tương ứng |
| `CascadeType.ALL` nhưng bỏ child không xóa | ALL không bật orphanRemoval | Thêm orphanRemoval nếu child phụ thuộc vòng đời |
| `orphanRemoval` khai báo trên `@ManyToMany` | Annotation không có thuộc tính đó | Không dùng; xóa join link hoặc mô hình association entity |
| Xóa item khỏi Playlist làm Song bị xóa | Cascade REMOVE nhầm trên shared entity | Bỏ cascade remove tới Song; chỉ gỡ association |
| `remove(child)` trên Set không tìm thấy phần tử | `equals/hashCode` không ổn định hoặc khác instance | Thiết kế membership/equality phù hợp |
| Child được chuyển parent rồi bị xóa | Reparenting mâu thuẫn orphan semantics | Không reparent orphan; đổi mô hình hoặc tạo entity mới |
| Xóa dòng đã có shipment gây FK lỗi | Child đang được entity khác tham chiếu | Đánh giá quy tắc xóa lịch sử/phụ thuộc |
| `EntityManager` đã đóng nhưng vẫn sửa collection | Entity detached, thay đổi không tự theo dõi | Làm việc trên managed graph trong transaction |
| Bulk DELETE xong collection vẫn có child | Persistence context stale | Đồng bộ context, dùng transaction/bulk operation có chủ đích |
| Orphan DELETE có nhiều SQL | Provider xử lý collection/index/FK/callback liên quan | Đo SQL thật và tối ưu mapping/workload |
| Có `@OrderColumn`, xóa giữa List cập nhật nhiều dòng | Phải cập nhật lại vị trí còn lại | Cân nhắc chi phí reorder và schema |
| Bật orphanRemoval để mong soft delete | JPA remove không tự bằng UPDATE deleted_at | Thiết kế soft-delete riêng |
| Flushed DELETE nhưng transaction rollback | Flush không phải commit | Xác nhận transaction commit thành công |
| Đồng thời xóa/sửa một child xung đột | Concurrency, locking, isolation | `@Version`/transaction/DB constraint và xử lý lỗi phù hợp |

## 23. Bài tập thực hành có lời giải

### Bài 1. Gỡ một dòng đơn hàng

Entity `PurchaseOrder` có:

~~~java
@OneToMany(mappedBy = "order", orphanRemoval = true)
private List<OrderLine> lines;
~~~

Application gọi `order.removeLine(line)` trên managed parent trong transaction.

**Hỏi:** Mục đích thay đổi database là gì?

**Đáp án:** Xóa child `OrderLine` bị loại khỏi association khi đồng bộ; parent và các child còn lại vẫn tồn tại. Thời điểm SQL DELETE thực tế có thể ở flush hoặc commit.

### Bài 2. Cascade REMOVE có đủ không?

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
~~~

Ứng dụng bỏ một phần tử khỏi List nhưng không gọi `em.remove(order)`.

**Hỏi:** Có chắc child bị xóa không?

**Đáp án:** Không. Cascade REMOVE lan truyền khi parent bị remove, không tự mang semantics orphan removal khi một child bị bỏ khỏi collection.

### Bài 3. Orphan removal có xóa child khi xóa parent?

**Đáp án:** Có ngữ nghĩa cascade remove trong trường hợp managed source bị remove theo quy tắc JPA, dù không khai báo riêng `CascadeType.REMOVE`. Vì vậy không đúng khi nói orphanRemoval “chỉ áp dụng lúc xóa phần tử”.

### Bài 4. Chuyển nhân viên sang phòng khác

`Department.employees` là `@OneToMany`; nhân viên có thể chuyển sang bộ phận khác.

**Hỏi:** Có nên đặt `orphanRemoval = true`?

**Đáp án:** Thường không. Việc bỏ nhân viên khỏi Department A không đồng nghĩa xóa `Employee`. Nghiệp vụ cần cập nhật `employee.department` sang Department B và giữ object graph nhất quán.

### Bài 5. Playlist và bài hát

`Playlist` liên kết với `Song` bằng `@ManyToMany`. Người dùng xóa `Song#9` khỏi một playlist.

**Đáp án:** Xóa liên kết join table tương ứng, không xóa `Song#9`. Không có `orphanRemoval` cho many-to-many trong JPA chuẩn.

### Bài 6. @ElementCollection List<String>

Một `Customer` có `@ElementCollection List<String> notes`. Xóa một note khỏi collection có cần `orphanRemoval = true` không?

**Đáp án:** Không. Các note là basic values trong collection table, không phải entity riêng; `@ElementCollection` không có thuộc tính orphanRemoval.

### Bài 7. OrphanRemoval và FK NOT NULL

Child có `order_id NOT NULL`. Tại sao bật orphanRemoval có thể phù hợp hơn việc set `order_id = NULL` khi bỏ child?

**Đáp án:** Vì domain xác định child không thể tồn tại khi rời parent. Xóa child là trạng thái cuối hợp lệ và không đòi hỏi tồn tại một row có FK null. Nhưng mapping và provider vẫn phải xử lý đúng SQL và các FK khác.

### Bài 8. Entity detached

Đối tượng `PurchaseOrder` được tải ở request trước, rồi detached; code xóa một child khỏi List trên detached object nhưng không thực hiện transaction mới.

**Đáp án:** Thao tác trên detached object không tự xóa row trong DB. Cần xử lý lại trong managed context/transaction, hoặc sử dụng merge với hiểu biết về graph và cascade, tránh merge mù một graph cũ.

### Bài 9. Xóa OrderLine đã xuất kho

Đơn hàng đã tạo bản ghi `ShipmentItem` tham chiếu `OrderLine`; xóa OrderLine gây FK violation.

**Đáp án:** Database đang bảo vệ dữ liệu liên quan. Cần thiết kế chính sách nghiệp vụ: không cho xóa dòng đã xuất kho, xử lý phụ thuộc có kiểm soát, hoặc soft-delete/archive khi thích hợp. Không tắt FK để “làm orphanRemoval chạy”.

### Bài 10. Orphan hay chỉ ngắt liên kết?

Một `Document` có nhiều `Attachment`, nhưng attachment có thể được tái sử dụng ở document khác.

**Đáp án:** Nếu attachment thực sự chia sẻ hoặc chuyển được thì không nên xóa attachment chỉ vì rời document. Dùng mô hình liên kết phù hợp; nếu có metadata liên kết riêng, có thể mô hình hóa association entity với lifecycle phụ thuộc document.

### Bài 11. @OneToOne với AccountProfile

`UserAccount.profile` là `@OneToOne(mappedBy="account", orphanRemoval=true)`. Service gọi `account.setProfile(null)`.

**Đáp án:** Nếu profile là managed target phù hợp và object graph được cập nhật nhất quán, provider sẽ xóa AccountProfile khi flush. Account vẫn tồn tại; không dùng cascade REMOVE từ profile sang account.

### Bài 12. Chuyển một orphan đã remove sang parent khác

Code gỡ child khỏi parent A có orphanRemoval rồi thêm cùng instance vào parent B trước flush.

**Đáp án:** Không phải hành vi portable để reparent; JPA không yêu cầu provider “hủy bỏ quyết định orphan deletion” khi target bị chuyển như thế. Nếu nghiệp vụ chuyển owner hợp lệ, cần thay mapping hoặc cách quản lý identity.

## 24. Hướng dẫn lựa chọn orphanRemoval theo domain

Một quy tắc thiết kế nhanh:

~~~text
       Khi child bị bỏ khỏi parent, child có nên tồn tại?
                           |
                  +--------+--------+
                  |                 |
                 Không              Có
                  |                 |
                  v                 v
     Child thuộc vòng đời     Child có vòng đời
     parent/aggregate         độc lập hoặc có thể
                  |            được chia sẻ/chuyển
                  v                 |
         Quan hệ entity             v
         @OneToMany hoặc       Không orphanRemoval
         @OneToOne?                |
              |                    +--- đổi FK / gỡ join row
         +----+----+                    / sử dụng business state
         |         |
        Có        Không
         |         |
         v         v
    Cân nhắc     Chọn mô hình
    orphanRemoval quan hệ/value phù hợp
         |
         v
    Helper method + transaction
    + FK/constraint + kiểm tra
    lifetime của entity
~~~

Đừng dừng ở “JPA cho phép đặt annotation này không?”. Hãy kiểm tra **quy tắc sở hữu vòng đời**: entity nào chịu trách nhiệm tạo, cập nhật và xóa child; child có được phép bị tham chiếu bởi aggregate khác hay không; business có cần giữ lịch sử không.

## 25. Ghi nhớ

- **`orphanRemoval = true`** là chính sách xóa **entity đích bị gỡ khỏi quan hệ sở hữu**, dành cho `@OneToOne` và `@OneToMany`.
- **CascadeType.REMOVE** kích hoạt khi source entity bị remove; **orphanRemoval** còn xử lý trường hợp child bị bỏ khỏi association trong khi parent vẫn tồn tại.
- **CascadeType.ALL không tự bật orphanRemoval**. Hai cấu hình giải quyết những cơ chế khác nhau.
- Với managed source bị remove, JPA có quy tắc cascade remove tới target của quan hệ orphanRemoval, kể cả không khai báo riêng cascade REMOVE.
- Trong quan hệ hai chiều, **giữ đồng bộ owning side và inverse side** bằng các helper method để object graph phản ánh đúng nghiệp vụ.
- **Không dùng orphanRemoval cho entity chia sẻ hoặc cần reparent** như nhân viên đổi phòng ban hay bài hát được nhiều playlist dùng chung.
- **Không có orphanRemoval trong `@ManyToMany` và `@ElementCollection`**; những quan hệ này có semantics liên kết/giá trị riêng.
- **Orphan removal không đồng nghĩa `ON DELETE CASCADE`**; DB cascade chỉ được kích hoạt bởi thao tác SQL phù hợp ở database.
- **DELETE thường xảy ra khi flush**, vẫn thuộc transaction và có thể rollback; đừng xem thao tác sửa List là commit.
- **New/detached/removed targets không nên bị giả định có cùng hành vi orphan removal portable** như managed target.
- **Soft delete, bulk JPQL DELETE và concurrency** cần chiến lược riêng; annotation này không tự giải quyết những bài toán đó.

Cốt lõi của bài học: **bật `orphanRemoval` khi một entity con là thành phần phụ thuộc của parent và việc loại nó khỏi quan hệ phải đồng nghĩa xóa nó khỏi hệ thống lưu trữ**. Nếu child vẫn có một cuộc đời độc lập, hãy cập nhật liên kết thay vì xóa entity.
