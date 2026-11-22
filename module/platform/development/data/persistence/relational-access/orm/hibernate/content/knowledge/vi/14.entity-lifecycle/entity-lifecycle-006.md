# remove và điều kiện để xóa thực thể trong Hibernate ORM

## 1. Xóa một entity không chỉ là gọi một phương thức

Trong ứng dụng bán hàng, giả sử người quản trị muốn xóa một đơn hàng nháp:

~~~java
entityManager.remove(order);
~~~

Lệnh Java này ngắn, nhưng kết quả của nó phụ thuộc nhiều điều kiện:

- **order có đang managed** bởi đúng persistence context không?
- Thao tác có diễn ra trong **transaction** thích hợp không?
- Hibernate đã **flush** để tạo SQL DELETE chưa, transaction đã **commit** chưa?
- Đơn có các **OrderItem** thuộc vòng đời của nó không; quan hệ có cascade/orphanRemoval không?
- Có **Payment**, Shipment hoặc bảng khác giữ foreign key tham chiếu đơn không?
- Đơn đã thanh toán có được phép xóa vật lý theo **quy tắc nghiệp vụ** không?
- Có transaction khác vừa sửa hoặc xóa đơn, gây **optimistic locking conflict** không?
- Người gọi có **quyền** xóa đối tượng này không?

Do đó, chủ đề **remove và điều kiện để xóa thực thể** nằm tại giao điểm của **vòng đời entity**, transaction, quan hệ, tính toàn vẹn dữ liệu và quy tắc nghiệp vụ.

Trong bài này, ta dùng Java 17+, Jakarta Persistence (JPA) với Hibernate ORM 6.x, Spring Boot 3.x và PostgreSQL làm ví dụ. Phần lớn nguyên lý JPA áp dụng cho provider khác; SQL, thứ tự statement và một số extension Hibernate có thể khác theo phiên bản/dialect.

Sau bài, bạn sẽ:

1. Nhận diện đúng các trạng thái **new/transient, managed, detached, removed**.
2. Biết lúc nào **EntityManager.remove()** hợp lệ và cách xóa theo ID an toàn.
3. Giải thích sự khác nhau giữa **đánh dấu removed**, **flush**, **commit** và **rollback**.
4. Xử lý **cascade REMOVE**, **orphanRemoval**, ràng buộc foreign key và quan hệ đến entity dùng chung.
5. Tránh xóa ngoài ý muốn do **merge detached graph**, bulk DELETE hoặc cấu hình cascade sai.
6. Thiết kế xóa có điều kiện nghiệp vụ, kiểm quyền, optimistic locking và lựa chọn **soft delete** khi cần giữ lịch sử.
7. Quan sát và kiểm thử SQL thực tế.

## 2. Ôn bốn trạng thái trong vòng đời entity

JPA quản lý entity theo các trạng thái khái niệm:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **New / transient** | Object mới tạo bằng Java, chưa được persistence context quản lý | new PurchaseOrder(...) |
| **Managed / persistent** | Object đang được một persistence context theo dõi | Kết quả từ entityManager.find(...) trong transaction |
| **Detached** | Object từng được quản lý nhưng không còn gắn với persistence context hiện hành | Entity trả ra sau khi EntityManager đóng, hoặc sau detach/clear |
| **Removed** | Entity đã được yêu cầu xóa trong persistence context; SQL DELETE có thể chưa thực thi | Sau khi gọi remove(managedOrder) |

~~~mermaid
stateDiagram-v2
    [*] --> New: new Entity(...)
    New --> Managed: persist(entity)
    Managed --> Detached: detach / clear / close
    Detached --> Managed: merge(detached) trả về managed copy
    Managed --> Removed: remove(managed)
    Removed --> [*]: flush DELETE + commit
    Managed --> [*]: kết thúc vòng đời quản lý
~~~

Sơ đồ giúp hiểu các chuyển trạng thái chính, **không phải máy trạng thái đầy đủ mọi hành vi JPA**. Chẳng hạn **merge** không biến object detached ban đầu thành managed; nó trả về một managed instance chứa state đã sao chép. Lệnh remove đối với một new entity hoặc entity đã ở trạng thái removed được xử lý khác với detached entity.

### 2.1. Điều kiện quan trọng nhất: phải xóa entity managed

Với JPA, **EntityManager.remove()** được thiết kế để nhận **một entity đang managed**. Ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
if (order != null) {
    em.remove(order);
}
~~~

Trong cùng persistence context, **find()** trả về managed entity nếu bản ghi tồn tại. Hibernate biết entity này có identity gì và có thể đánh dấu nó để xóa.

Ngược lại:

~~~java
PurchaseOrder order = loadOrderInAnotherTransaction();

// order có thể đã detached.
em.remove(order); // Không phải cách portable/hợp lệ để xóa detached entity.
~~~

Theo JPA, việc gọi **remove()** trên một detached entity là không hợp lệ và có thể gây **IllegalArgumentException**. Một provider có thể phát hiện tại lệnh gọi hoặc ở một thời điểm xử lý phù hợp; không nên dựa vào hành vi riêng để xóa đối tượng detached.

### 2.2. Trường hợp entity new

~~~java
PurchaseOrder draft = new PurchaseOrder(...);
em.remove(draft);
~~~

Với entity mới chưa từng được persist, thao tác remove trực tiếp **không tạo SQL DELETE** cho một bản ghi không tồn tại. JPA quy định remove với new entity thường bị bỏ qua đối với chính entity đó; vẫn cần cẩn thận với cascade và quan hệ. Không dùng hành vi này như một thủ thuật để “hủy” toàn bộ object graph phức tạp mà chưa kiểm tra các entity liên quan.

Nếu một entity đã **persist** rồi **remove** trước khi insert thực tế, Hibernate có thể tối ưu và không ghi hàng vào DB; nhưng kết quả phụ thuộc thời điểm flush, ID strategy và cascade. Đặc biệt với IDENTITY, INSERT có thể đã chạy sớm để lấy ID rồi DELETE khi flush.

### 2.3. Trường hợp entity đã được remove

Khi một managed entity đã ở trạng thái removed, gọi remove lần nữa thường không tạo một yêu cầu xóa bổ sung hữu ích. Tuy nhiên đừng thiết kế nghiệp vụ dựa trên việc giữ và sử dụng lâu dài object đã marked removed. Các thao tác truy vấn, cascade, flush và exception sau đó có những quy tắc trạng thái riêng.

**Lý do phải phân biệt:** Java object vẫn còn trong bộ nhớ sau remove, nhưng điều đó không chứng minh bản ghi SQL vẫn còn hoặc sẽ còn sau commit.

## 3. Điều kiện transaction: remove, flush và commit là ba thời điểm khác nhau

Hình dung:

~~~mermaid
sequenceDiagram
    participant App as Application Service
    participant EM as EntityManager
    participant DB as Database
    App->>EM: find(PurchaseOrder, id)
    EM->>DB: SELECT (nếu cần)
    DB-->>EM: Hàng dữ liệu
    EM-->>App: Managed PurchaseOrder
    App->>EM: remove(order)
    Note over EM: Đánh dấu REMOVED, xử lý cascade
    App->>EM: flush() hoặc tới điểm flush
    EM->>DB: DELETE ... WHERE id=?
    DB-->>EM: Statement hoàn tất / constraint error
    App->>DB: COMMIT
    DB-->>App: Giao dịch hoàn tất
~~~

Trong transaction bình thường:

1. **find** nạp entity và gắn vào persistence context.
2. **remove** yêu cầu xóa entity; Hibernate quản lý thay đổi state và cascade.
3. **flush** đồng bộ thay đổi xuống DB bằng SQL.
4. **commit** kết thúc transaction; nếu thành công, xóa trở thành kết quả đã commit và có thể nhìn thấy theo isolation level của transaction khác.

**Gọi remove không đồng nghĩa DELETE đã được gửi ngay.** Hibernate có thể đợi đến flush, hoặc cần thực hiện một số thao tác khác trước để giữ tính toàn vẹn FK. Cũng không nên kết luận một DELETE đã flush là không thể đảo ngược: nếu transaction rollback, thay đổi SQL chưa commit sẽ được database hoàn tác.

Ví dụ service:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderDeletionService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public boolean deleteDraft(Long orderId) {
        PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
        if (order == null) {
            return false;
        }
        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chỉ xóa đơn nháp");
        }
        em.remove(order);
        return true;
    }
}
~~~

Ví dụ giả định entity PurchaseOrder và enum OrderStatus được định nghĩa ở phần sau. **@Transactional** giúp cả bước kiểm tra trạng thái và thao tác xóa diễn ra trong cùng transaction. Với Spring, lỗi khi flush/commit có thể xuất hiện khi phương thức transactional kết thúc, ngay cả khi **em.remove()** không ném exception.

### 3.1. Nếu không có transaction thì sao?

Với persistence context quản lý theo transaction, các thao tác thay đổi database cần transaction hoạt động. Thiếu transaction có thể gây **TransactionRequiredException** hoặc khiến công việc không được đồng bộ như mong đợi theo cách quản lý EntityManager. Trong Spring Boot, không gọi xóa bên trong một hàm thông thường rồi giả định mọi cấu hình đều sẽ commit.

~~~java
@Transactional
public void deleteById(Long id) {
    // Thao tác nạp, kiểm tra, xóa cùng một transaction.
}
~~~

Nếu gọi một phương thức **@Transactional** qua chính **this.method()** bên trong cùng object, Spring proxy transaction mặc định có thể không intercept self-invocation. Vì thế cấu trúc service và điểm gọi cũng ảnh hưởng hiệu quả của annotation, không chỉ sự hiện diện của nó.

### 3.2. Rollback sau remove

~~~java
@Transactional
public void deleteThenFail(Long orderId) {
    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    em.remove(order);
    em.flush();
    throw new IllegalStateException("Hủy transaction để minh họa");
}
~~~

Trong thiết lập Spring transaction thông thường, exception runtime gây rollback. Lệnh DELETE đã gửi ở **flush** nhưng không được commit; hàng vẫn còn sau rollback thành công. Một callback hoặc log chạy trước commit **không được xem là bằng chứng xóa đã thành công vĩnh viễn**.

## 4. Mô hình dữ liệu: đơn hàng, dòng hàng và sản phẩm

Ta dùng quan hệ:

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ PURCHASE_ORDERS : places
    PURCHASE_ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : referenced_by
    PURCHASE_ORDERS ||--o{ PAYMENTS : has
    CUSTOMERS {
        bigint id PK
        varchar email
    }
    PURCHASE_ORDERS {
        bigint id PK
        bigint customer_id FK
        varchar status
        bigint version
    }
    ORDER_ITEMS {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
        int quantity
    }
    PRODUCTS {
        bigint id PK
        varchar sku
    }
    PAYMENTS {
        bigint id PK
        bigint order_id FK
        varchar provider_ref
    }
~~~

DDL PostgreSQL rút gọn:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    provider_ref VARCHAR(128) NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_payments_order ON payments(order_id);
~~~

Hai quy tắc nghiệp vụ:

1. **OrderItem** là phần con có vòng đời gắn với PurchaseOrder; xóa một đơn nháp có thể xóa các dòng của nó.
2. **Product** và **Customer** tồn tại độc lập, không bị xóa chỉ vì một đơn không còn. **Payment** được giữ để đối soát, nên đơn có payment không được xóa vật lý tùy tiện.

Giả sử DB có foreign key mặc định **không ON DELETE CASCADE**. Nếu xóa PurchaseOrder mà vẫn có OrderItem hoặc Payment tham chiếu nó, database có thể bác bỏ DELETE theo ràng buộc FK.

**Điểm quan trọng:** ORM quyết định entity nào bị yêu cầu xóa; database kiểm tra quan hệ và constraint. Có cascade từ Hibernate không nghĩa database bỏ qua FK, và có FK không nghĩa Hibernate tự đoán child nào được phép xóa.

## 5. Entity mapping và quyền xóa theo vòng đời

### 5.1. Các entity độc lập

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {}

    public Customer(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        this.email = email;
    }

    public Long getId() { return id; }
}
~~~

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    protected Product() {}

    public Product(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        this.sku = sku;
    }

    public Long getId() { return id; }
}
~~~

Không đặt **CascadeType.REMOVE** từ OrderItem sang Product hoặc PurchaseOrder sang Customer. Đơn không phải chủ sở hữu vòng đời của customer/product.

### 5.2. PurchaseOrder sở hữu collection dòng hàng

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private OrderStatus status = OrderStatus.DRAFT;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer) {
        this.customer = Objects.requireNonNull(customer);
    }

    public void addItem(Product product, int quantity) {
        requireDraft();
        OrderItem item = new OrderItem(this, product, quantity);
        items.add(item);
    }

    public void removeItem(OrderItem item) {
        requireDraft();
        if (items.remove(item)) {
            item.detachOrder();
        }
    }

    public void confirm() {
        requireDraft();
        if (items.isEmpty()) {
            throw new IllegalStateException("Không thể xác nhận đơn rỗng");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) return;
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException("Không thể hủy theo trạng thái hiện tại");
        }
        status = OrderStatus.CANCELLED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Đơn không còn ở trạng thái nháp");
        }
    }

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }
}
~~~

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}
~~~

### 5.3. OrderItem thuộc vòng đời Order

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderItem() {}

    OrderItem(PurchaseOrder order, Product product, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        this.quantity = quantity;
    }

    void detachOrder() {
        this.order = null;
    }

    public Long getId() { return id; }
}
~~~

Các ví dụ cho phép **OrderItem** bị xóa khi bỏ khỏi collection nhờ **orphanRemoval = true**. Lệnh detachOrder ở phía owning side giúp object graph đồng bộ trong bộ nhớ; vì child sẽ bị xóa theo orphan removal, không phải tồn tại với order_id = NULL. Nếu đổi quy tắc để chuyển OrderItem sang Order khác, cần thiết kế lại helper/cascade/orphanRemoval.

### 5.4. Payment không thuộc phạm vi xóa vật lý tùy tiện

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "payments")
public class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "provider_ref", nullable = false)
    private String providerReference;

    protected Payment() {}
}
~~~

Chúng ta **không thêm CascadeType.REMOVE từ PurchaseOrder sang Payment**, vì lịch sử đối soát cần được bảo vệ. Nếu một đơn có Payment tham chiếu nó, FK trong database cũng giúp ngăn xóa parent. Tuy nhiên **FK là lớp bảo vệ cuối**, không thay thế policy ở service: API nên từ chối ngay với thông báo nghiệp vụ rõ ràng thay vì cố DELETE rồi chỉ trả lỗi database khó hiểu.

## 6. Xóa theo ID: nạp managed entity rồi kiểm tra

Một service cần xử lý:

- ID không tồn tại;
- trạng thái không cho phép xóa;
- user không có quyền;
- có Payment/Shipment tham chiếu;
- transaction khác vừa thay đổi dữ liệu.

Ví dụ repository Spring Data JPA:

~~~java
package com.example.shop.application;

import com.example.shop.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {}
~~~

~~~java
package com.example.shop.application;

import com.example.shop.domain.Payment;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository extends JpaRepository<Payment, Long> {
    boolean existsByOrder_Id(Long orderId);
}
~~~

Service dùng repository:

~~~java
package com.example.shop.application;

import com.example.shop.domain.OrderStatus;
import com.example.shop.domain.PurchaseOrder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final PurchaseOrderRepository orders;
    private final PaymentRepository payments;

    public OrderCommandService(PurchaseOrderRepository orders,
                               PaymentRepository payments) {
        this.orders = orders;
        this.payments = payments;
    }

    @Transactional
    public void deleteDraft(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Đơn hàng không tồn tại"));

        // Ứng dụng thật: kiểm tra chủ sở hữu/role của người gọi tại đây.
        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chỉ được xóa đơn nháp");
        }
        if (payments.existsByOrder_Id(orderId)) {
            throw new IllegalStateException("Đơn có thanh toán, không thể xóa");
        }

        orders.delete(order);
    }
}
~~~

**orders.findById(...)** trả entity managed trong transaction Spring Data JPA thông thường; **orders.delete(order)** thực hiện xóa qua lifecycle của repository/provider khi thích hợp. Với JPA trực tiếp có thể gọi **em.remove(order)**. Hành vi cụ thể của từng phương thức repository phụ thuộc phiên bản Spring Data JPA, nhưng ý nghĩa quan trọng là **nạp → kiểm tra → xóa trên entity managed trong cùng use case transaction**.

### 6.1. Vì sao kiểm tra ở service chưa hoàn toàn chống được cuộc đua?

~~~text
Transaction A: kiểm tra payments.exists... = false
Transaction B: tạo Payment tham chiếu Order và commit
Transaction A: DELETE Order
~~~

Nếu cả hai diễn ra đồng thời, một kiểm tra đơn giản trước DELETE không bảo đảm điều kiện vẫn đúng tại thời điểm commit. FK database sẽ ngăn xóa parent khi Payment đã tồn tại, nhưng yêu cầu nghiệp vụ có thể cần thêm:

- Khóa hoặc cập nhật điều kiện trên Order ở cùng transaction.
- Tất cả luồng tạo Payment phải tuân thủ cùng transaction/locking protocol.
- Optimistic locking với **@Version** khi phù hợp.
- Quy tắc xử lý exception và retry/cảnh báo xung đột.

Chỉ viết **if (exists...)** là validation dễ hiểu, không phải bằng chứng bảo đảm tính nguyên tử trong môi trường nhiều request.

### 6.2. ID không tồn tại: 404 hay thành công idempotent?

Hai API design đều có thể hợp lý:

- **DELETE /orders/{id}** trả 404 nếu đơn không tồn tại; phù hợp khi client cần biết đã nhập sai ID.
- **DELETE /orders/{id}** trả 204 nếu đơn đã vắng mặt; phù hợp một hợp đồng idempotent “bảo đảm tài nguyên không còn”.

Về HTTP, tính **idempotent** nói tới hiệu ứng của việc gọi lặp, không bắt buộc mọi lần gọi trả cùng status code. Hãy chọn contract rõ ràng; đừng dùng **remove(new OrderWithOnlyId(id))** như một cách xóa mà không cần nạp.

## 7. Detached entity: vì sao phải tìm managed instance?

Một tình huống điển hình:

~~~java
PurchaseOrder detached;

try (EntityManager first = emf.createEntityManager()) {
    detached = first.find(PurchaseOrder.class, 42L);
}

try (EntityManager second = emf.createEntityManager()) {
    second.getTransaction().begin();

    // Sai: detached không được second quản lý.
    second.remove(detached);

    second.getTransaction().commit();
}
~~~

Đoạn này minh họa lỗi về trạng thái, **không phải mã nên chạy nguyên xi**: exception tại remove có thể làm transaction cần rollback và dọn EntityManager. Trong ứng dụng thực, luôn quản lý transaction/cleanup khi exception.

Thay bằng:

~~~java
@Transactional
public void deleteUsingEntityManager(Long id) {
    PurchaseOrder managed = em.find(PurchaseOrder.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }
    if (managed.getStatus() != OrderStatus.DRAFT) {
        throw new IllegalStateException("Không được xóa đơn này");
    }
    em.remove(managed);
}
~~~

### 7.1. Có thể merge rồi remove không?

Về mặt API JPA, một thao tác như:

~~~java
PurchaseOrder managed = em.merge(detached);
em.remove(managed);
~~~

có thể tạo ra một managed copy trước khi xóa. Nhưng **không nên coi đây là cách xóa ưu tiên**, đặc biệt với detached object do API gửi tới:

- Merge có thể sao chép state/association không đầy đủ.
- Cascade MERGE có thể nạp hoặc đồng bộ nhiều entity liên quan.
- Một object chỉ mang ID không chứng minh user được phép xóa entity tương ứng.
- Dữ liệu detached có thể cũ hoặc đã bị người khác thay đổi.

Tốt hơn là **tìm entity mới nhất bằng ID trong transaction, kiểm tra điều kiện rồi remove**. Nếu thực sự cần tính năng merge, hãy hiểu rõ graph, cascade và giá trị trả về; object detached ban đầu không trở thành managed chỉ nhờ lời gọi merge.

### 7.2. getReference có dùng để xóa mà không SELECT không?

~~~java
@Transactional
public void deleteKnownId(Long id) {
    PurchaseOrder reference = em.getReference(PurchaseOrder.class, id);
    em.remove(reference);
}
~~~

Trong một số mapping/provider, **getReference** có thể trả proxy mang ID mà chưa cần SELECT toàn entity. Tuy nhiên:

- getReference có thể chưa kiểm tra ngay bản ghi tồn tại hay không; lỗi có thể xuất hiện lúc truy cập hoặc xử lý DELETE.
- Cascade, callback, optimistic version hoặc điều kiện nghiệp vụ có thể buộc Hibernate nạp entity hay liên kết.
- Không thể kiểm tra trạng thái DRAFT, quyền sở hữu hoặc có Payment chỉ bằng một proxy mang ID.
- Không bảo đảm xóa luôn chỉ cần đúng một SQL DELETE.

**Chỉ cân nhắc cách này** khi việc xóa theo ID đã được kiểm soát đầy đủ và bạn chấp nhận xử lý đúng các trường hợp không tồn tại/xung đột. Với đơn hàng có business rule, **find + validate + remove** rõ ràng và an toàn hơn.

## 8. CascadeType.REMOVE: xóa từ parent xuống child

Khi PurchaseOrder có:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

**CascadeType.ALL** bao gồm **REMOVE**. Khi xóa một PurchaseOrder, Hibernate có thể lan truyền remove tới các OrderItem phù hợp.

Ví dụ SQL có thể xuất hiện khi xóa đơn nháp có hai dòng:

~~~sql
DELETE FROM order_items WHERE id = ?;
DELETE FROM order_items WHERE id = ?;
DELETE FROM purchase_orders WHERE id = ? AND version = ?;
~~~

Ví dụ SQL diễn giải nguyên tắc **xóa child trước parent để không vi phạm FK**. Hibernate có action queue, batching, dialect và thứ tự flush riêng; không coi thứ tự literal trong ví dụ là hợp đồng cho mọi cấu hình.

**Product vẫn tồn tại**: trong mapping OrderItem.product ta không khai báo cascade remove. Cũng không có lý do để xóa Customer khi xóa một đơn.

### 8.1. Cascade REMOVE là gì và không phải là gì?

| Hành động | Với cascade REMOVE | Không tự động có nghĩa |
|---|---|---|
| em.remove(parent) | Lan truyền thao tác remove tới entity quan hệ được cascade | Xóa mọi entity trong toàn bộ database có liên hệ gián tiếp |
| Xóa child thuộc parent | Có thể phát sinh DELETE trên child | Xóa entity Product mà child tham chiếu nếu Product không nằm trong cascade đó |
| Xóa parent có nhiều child | Có thể sinh nhiều DELETE, phụ thuộc batching/mapping | Chỉ duy nhất một SQL hoặc database tự xử lý mọi thứ |
| Gọi remove khi chưa commit | Đặt state removed, thực hiện SQL ở điểm flush phù hợp | Dữ liệu được xóa vĩnh viễn ngay lập tức |

**CascadeType.REMOVE** thường có ngữ nghĩa hợp lý trên quan hệ **OneToOne / OneToMany** có vòng đời phụ thuộc. Không cascade remove một **ManyToOne** trỏ đến Customer/Product dùng chung. Với **ManyToMany**, cascade remove sang entity đầu kia rất dễ xóa dữ liệu được nhiều owner sử dụng và không phải lựa chọn portable phù hợp.

### 8.2. Nếu không cấu hình cascade?

Khi còn OrderItem tham chiếu PurchaseOrder, DELETE parent có thể bị từ chối bởi foreign key:

~~~sql
DELETE FROM purchase_orders WHERE id = 42;
-- Có thể lỗi: vẫn tồn tại order_items.order_id = 42
~~~

Để xóa parent hợp lệ, bạn cần một chính sách rõ:

1. ORM xóa child trước qua cascade hoặc thao tác remove tường minh; hoặc
2. FK của database được thiết kế **ON DELETE CASCADE** và ứng dụng biết cách xử lý tác động; hoặc
3. Từ chối xóa parent khi còn child nếu đó là ràng buộc nghiệp vụ.

Không phải FK nào cũng nên có ON DELETE CASCADE. Với Payment và hóa đơn phải giữ lịch sử, khóa ngoại ngăn xóa parent có thể chính là biện pháp bảo vệ mong muốn.

## 9. orphanRemoval: gỡ một phần tử khỏi collection là xóa entity con

**orphanRemoval = true** trên OneToMany hoặc OneToOne diễn đạt rằng child không còn liên kết với owner thì phải bị xóa theo lifecycle của ORM.

Trong ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
OrderItem item = ...; // Tìm phần tử đang thuộc order.
order.removeItem(item);
~~~

Sau flush, Hibernate có thể sinh:

~~~sql
DELETE FROM order_items WHERE id = ?;
~~~

Khác với:

~~~java
em.remove(order);
~~~

Trong trường hợp thứ nhất, **một OrderItem** bị loại khỏi aggregate; trong trường hợp thứ hai, **cả PurchaseOrder** được yêu cầu xóa và cascade có thể xóa tất cả child.

### 9.1. Phân biệt orphanRemoval với CascadeType.REMOVE

| Tình huống | orphanRemoval | CascadeType.REMOVE |
|---|---|---|
| Loại một child khỏi collection của parent vẫn tồn tại | Có thể xóa child | Chỉ cấu hình REMOVE không có nghĩa tự xóa child khi collection thay đổi |
| Gọi remove trên parent | ORM áp dụng quy tắc remove owner/child theo mapping | Lan truyền remove tới child được cascade |
| Chuyển child sang parent khác | Không nên thao tác tùy tiện nếu child có vòng đời phụ thuộc và orphan removal | Cần làm rõ lifecycle và owning side |
| Child tồn tại độc lập | Thường không phù hợp | Thường không cascade remove từ parent |

Không chuyển một child có orphanRemoval từ parent A sang parent B trong cùng transaction rồi mặc định ORM sẽ hiểu đây chỉ là cập nhật FK. Một child đã trở thành orphan có thể bị lên lịch xóa; quy tắc tái gắn child bị orphan không phải con đường portable nên dựa vào. Nếu domain cho phép chuyển owner, hãy mô hình hóa quan hệ và lifecycle phù hợp, thường không dùng orphanRemoval theo cách này.

### 9.2. Tránh thay thế instance collection managed

Không nên:

~~~java
public void replaceItems(List<OrderItem> incoming) {
    this.items = new ArrayList<>(incoming);
}
~~~

Với Hibernate và orphanRemoval, thay tham chiếu collection đang được provider quản lý có thể gây lỗi kiểu **collection with cascade="all-delete-orphan" was no longer referenced** hoặc khiến Hibernate xử lý thay đổi hàng loạt. Nên **giữ collection persistent** và chỉ thêm/xóa những phần tử thật sự thay đổi, qua helper method cập nhật hai phía quan hệ.

Không dùng **items.clear(); items.addAll(request.items())** một cách máy móc khi client chỉ muốn sửa quantity; cách đó có thể xóa rồi tạo lại tất cả OrderItem, phá identity và dữ liệu liên quan.

## 10. Ràng buộc FK: database có quyền từ chối DELETE

Ngay cả khi entity managed và đang trong transaction, **remove không bảo đảm thành công**.

Ví dụ đơn 42 có Payment:

~~~sql
SELECT id, order_id, provider_ref
FROM payments
WHERE order_id = 42;
~~~

Nếu còn Payment giữ FK đến đơn, thao tác:

~~~sql
DELETE FROM purchase_orders WHERE id = 42;
~~~

có thể nhận lỗi constraint. Hibernate thường bọc/chuyển ngoại lệ JDBC sang exception persistence; Spring có thể chuyển tiếp sang một dạng **DataIntegrityViolationException** tùy tầng và thời điểm xử lý. Không viết logic phụ thuộc vào đúng tên exception message của một database cụ thể.

### 10.1. FK RESTRICT/NO ACTION, CASCADE, SET NULL

| Cơ chế FK | Khi xóa parent | Khi nên cân nhắc |
|---|---|---|
| **RESTRICT / NO ACTION** | Ngăn xóa nếu còn child tham chiếu theo semantics của DB/constraint | Bảo vệ lịch sử, thanh toán, đối soát |
| **ON DELETE CASCADE** | DB xóa các hàng child tương ứng | Child thực sự thuộc vòng đời parent và xóa vật lý là policy |
| **ON DELETE SET NULL** | DB bỏ tham chiếu bằng NULL | Child được phép tồn tại độc lập, FK nullable |
| **ON DELETE SET DEFAULT** | DB gán giá trị default nếu hỗ trợ | Có yêu cầu và schema bảo đảm default hợp lệ |

**Không đồng nhất ON DELETE CASCADE với Hibernate CascadeType.REMOVE**:

- Hibernate cascade vận hành ở tầng ORM, có thể kích hoạt lifecycle callbacks/ORM statistics theo các entity được xóa.
- Database cascade diễn ra trong DB, có thể không kích hoạt callback JPA trên từng child bị xóa.
- Một entity đã managed trong persistence context có thể có state cũ nếu DB xóa hàng chỉ bằng trigger/cascade ngoài tầm tracking trực tiếp.
- Cấu hình Hibernate như **@OnDelete** có thể phối hợp với FK nhưng yêu cầu migration/schema tương ứng; cần đọc SQL và đánh giá cache/callback.

**Thiết kế đúng bắt đầu bằng vòng đời dữ liệu**, không bắt đầu bằng chọn CASCADE để tránh exception.

## 11. Điều kiện nghiệp vụ: không phải entity nào cũng nên được xóa vật lý

Giả sử quy tắc quản lý đơn:

| Trạng thái đơn | Có được xóa vật lý? | Lý do |
|---|---|---|
| **DRAFT**, chưa có Payment/Shipment | Có thể cho phép | Dữ liệu còn nháp, không cần giữ lịch sử giao dịch |
| **CONFIRMED** | Thường không | Có giá trị giao dịch, tồn kho, audit, chứng từ |
| **CANCELLED** | Tùy chính sách, nhưng thường giữ | Cần biết vì sao và khi nào đơn bị hủy |
| Đã có Payment | Nên ngăn xóa vật lý | Phải đối soát và lưu lịch sử thanh toán |
| Đang có tranh chấp/hoàn tiền | Không | Cần giữ dấu vết xử lý |

Trong ứng dụng quản lý đơn hàng, yêu cầu từ UI “xóa đơn” đôi khi thực chất là **hủy đơn**, **ẩn khỏi danh sách** hoặc **lưu trữ**. Nếu coi tất cả thành **DELETE**, bạn có thể phá lịch sử.

### 11.1. Hủy đơn là một hành động nghiệp vụ

~~~java
@Transactional
public void cancelOrder(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));

    // Check quyền, tình trạng giao hàng, thanh toán và hoàn tiền.
    order.cancel();
}
~~~

Hành động này không gọi remove. Dirty checking có thể phát sinh:

~~~sql
UPDATE purchase_orders
SET status = 'CANCELLED', version = ?
WHERE id = ? AND version = ?;
~~~

Nghiệp vụ thực tế có thể cần xuất event, hoàn kho, trả tiền hoặc đóng yêu cầu giao hàng; các bước ấy phải được tổ chức trong một workflow giao dịch phù hợp, không thể chỉ thay một enum rồi coi là hoàn tất.

### 11.2. Kiểm tra quyền xóa

Đừng coi việc tìm thấy row theo ID là đủ để xóa nó. Một service trong hệ thống đa người dùng phải kiểm tra:

- Người gọi có đăng nhập và thuộc tenant/đơn vị sở hữu không?
- Đơn có thuộc chính khách hàng này hay vai trò quản trị được phép thao tác không?
- Quyền xóa vật lý có cần phê duyệt, giới hạn hoặc ghi audit không?

Thay vì tìm order bằng ID trên toàn bộ hệ thống rồi mới kiểm tra tùy tiện, một số hệ thống chọn query **findByIdAndTenantId** và luôn áp đặt tenant scope trong use case. Dù chọn cách nào, thiếu kiểm quyền trước DELETE là lỗi bảo mật chứ không chỉ lỗi persistence.

## 12. Soft delete và hard delete

**Hard delete**: hàng vật lý bị xóa khỏi bảng. **Soft delete**: hàng vẫn tồn tại nhưng được đánh dấu ẩn/đã xóa theo policy, chẳng hạn **deleted_at**, **deleted** hoặc một trạng thái nghiệp vụ.

| Tiêu chí | Hard delete | Soft delete |
|---|---|---|
| Hàng vật lý | Bị xóa | Còn trong DB |
| FK tham chiếu | Có thể chặn/cascade | Thường vẫn tham chiếu hợp lệ |
| Truy vấn mặc định | Không thấy row đã xóa | Phải có cơ chế lọc các row bị ẩn |
| Audit/lịch sử | Phải lưu riêng nếu cần | Có thể giữ dữ liệu tại chỗ, vẫn nên có audit |
| Unique constraint | Key có thể được dùng lại tùy DB | Row bị soft-delete vẫn có thể chiếm key |
| Retention và pháp lý | Có thể đáp ứng xóa thực sự | Không thay thế yêu cầu xóa dữ liệu cá nhân khi luật/policy đòi xóa thật |
| Tác động nghiệp vụ | Khó khôi phục nếu không có backup | Có thể thiết kế thao tác phục hồi |

Một schema:

~~~sql
ALTER TABLE purchase_orders
ADD COLUMN deleted_at TIMESTAMPTZ NULL;

CREATE INDEX idx_orders_active
ON purchase_orders(customer_id, id)
WHERE deleted_at IS NULL;
~~~

Một phương thức nghiệp vụ có thể đánh dấu:

~~~java
public void archive(Instant now) {
    if (deletedAt != null) return;
    deletedAt = java.util.Objects.requireNonNull(now);
}
~~~

Trong entity phải khai báo:

~~~java
@Column(name = "deleted_at")
private Instant deletedAt;
~~~

Đoạn này minh họa một phương án soft delete do domain kiểm soát; phải thêm **điều kiện deletedAt IS NULL** vào các query mặc định hoặc cơ chế filter thống nhất. Không được quên query native, báo cáo, join, background job và unique index.

### 12.1. Hibernate hỗ trợ soft delete

Hibernate ORM từ dòng phiên bản 6.4 có **@SoftDelete** dành cho một số kiểu mapping, giúp ORM tự xử lý marker và lọc dữ liệu đã xóa theo khả năng hỗ trợ. Không nên suy luận mọi phiên bản Hibernate 6 đều có annotation này hoặc nó tự giải quyết mọi quy tắc retention/restore/audit. Trước khi chọn, cần đối chiếu version đang dùng, kiểu mapping và migration schema thật.

Các giải pháp kiểu **@SQLDelete** tùy biến và filter/where clause cũng tồn tại trong các dự án cũ, nhưng dễ có góc cạnh về tham số version, bulk DML, association, query native và kỳ vọng row count. Không copy một annotation SQL delete từ dự án khác mà chưa hiểu provider version và binding tham số.

**Soft delete không đồng nghĩa thao tác hủy đơn.** Đơn hủy có thể vẫn hiển thị là CANCELLED cho báo cáo, trong khi soft-delete thường là “ẩn bản ghi khỏi truy vấn thông thường”. Nên định nghĩa hai khái niệm riêng nếu nghiệp vụ cần cả hai.

### 12.2. Unique constraint khi soft delete

Nếu một khách hàng có email UNIQUE nhưng hàng soft-deleted vẫn nằm trong bảng, email đó có thể vẫn bị chiếm theo unique constraint thông thường. Với PostgreSQL, một unique index có điều kiện có thể giới hạn uniqueness trong tập active:

~~~sql
CREATE UNIQUE INDEX uq_active_customers_email
ON customers(email)
WHERE deleted_at IS NULL;
~~~

Ví dụ này giả định bảng customers đã có cột deleted_at và **không còn constraint UNIQUE khác trên email** gây xung đột với yêu cầu cho phép tái sử dụng. Việc sửa constraint trong production phải được migration xử lý có kế hoạch, không thêm index rồi mặc định constraint cũ biến mất.

## 13. Version và xung đột khi xóa

JPA dùng **@Version** để hỗ trợ optimistic locking. Với PurchaseOrder:

~~~java
@Version
private long version;
~~~

Khi xóa entity có version, Hibernate có thể sinh câu:

~~~sql
DELETE FROM purchase_orders
WHERE id = ? AND version = ?;
~~~

Nếu transaction khác vừa UPDATE hoặc DELETE làm version/row thay đổi, số hàng bị tác động có thể không như mong đợi; provider có thể ném **OptimisticLockException** hoặc một exception optimistic locking được bọc qua tầng Spring.

Ví dụ cuộc đua:

~~~text
Transaction A: đọc Order #42, status DRAFT, version 5
Transaction B: xác nhận Order #42, version thành 6, commit
Transaction A: yêu cầu DELETE với id=42 và version=5
              -> Không còn đúng version; transaction A thất bại
~~~

Đây là lý do **kiểm tra status trong cùng transaction** vẫn cần chính sách đồng thời. Nếu bỏ @Version hoặc sử dụng bulk DELETE không kiểm tra version, bạn có thể xóa một row đã thay đổi trạng thái sau lúc đọc.

### 13.1. Có nên retry tự động sau optimistic lock conflict?

Không retry riêng DELETE và giả định quyền xóa vẫn còn. Phải **bắt đầu lại use case/transaction**, nạp trạng thái mới, kiểm tra lại quyền và business rule. Nếu đơn đã CONFIRMED, kết quả đúng có thể là từ chối xóa thay vì thử xóa tiếp.

### 13.2. Pessimistic lock khi nghiệp vụ thật sự cần

Ở một số workflow, bạn có thể cần khóa hàng khi kiểm tra và xóa:

~~~java
@Transactional
public void deleteDraftWithLock(Long id) {
    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        id,
        jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
    );
    if (order == null) return;
    if (order.getStatus() != OrderStatus.DRAFT) {
        throw new IllegalStateException("Đơn đã chuyển trạng thái");
    }
    em.remove(order);
}
~~~

Khóa hàng có chi phí, có thể gây chờ hoặc deadlock và chỉ bảo vệ đầy đủ nếu các workflow liên quan tuân thủ protocol tương ứng. Một khóa trên order không tự chặn mọi thao tác thêm Payment từ client khác nếu schema/isolation/logic không phối hợp. Chọn lock theo mức tranh chấp và tính đúng đắn cần bảo đảm, không mặc định PESSIMISTIC_WRITE cho mọi DELETE.

## 14. JPQL bulk DELETE khác hẳn EntityManager.remove()

JPA hỗ trợ JPQL DELETE:

~~~java
int deletedRows = em.createQuery("""
        delete from PurchaseOrder o
        where o.status = :status
        """)
    .setParameter("status", OrderStatus.DRAFT)
    .executeUpdate();
~~~

Nó là **bulk DML**, không đồng nghĩa chạy EntityManager.remove() trên từng PurchaseOrder.

| Thuộc tính | EntityManager.remove(managed) | JPQL bulk DELETE |
|---|---|---|
| Đơn vị thao tác | Entity managed cụ thể | Các hàng khớp điều kiện truy vấn |
| Entity lifecycle callbacks | Áp dụng theo cơ chế entity removal | Không gọi callback cho từng entity như remove |
| Cascade entity của JPA | Có thể được thực hiện | Không tự thực hiện cascade/orphan theo từng entity |
| Persistence context | Hibernate theo dõi state removed | Entity đang managed có thể trở nên stale |
| @Version | Có thể tham gia optimistic checking | Không mặc định kiểm version từng entity |
| Tính toán SQL | Có thể nhiều SELECT/DELETE theo graph | Thường DML theo tập, nhưng SQL thực tế tùy inheritance/DB |
| FK | Vẫn phải hợp lệ | Vẫn phải hợp lệ, thường cần xử lý child tường minh |
| Phù hợp | Use case nghiệp vụ có rule/callback/cascade | Cleanup theo lô đã được thiết kế riêng |

**Nguy cơ lớn:** nếu PurchaseOrder có OrderItem FK NOT NULL mà bulk DELETE trực tiếp orders trước, DB có thể từ chối xóa. Bulk JPQL **không tự đi từng order xóa child như cascade REMOVE**. Nếu muốn cleanup theo lô, cần thiết kế thứ tự DELETE, FK actions hoặc cơ chế DB riêng một cách có chủ đích.

### 14.1. Bulk DELETE và persistence context bị stale

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);

em.createQuery("delete from PurchaseOrder o where o.id = :id")
    .setParameter("id", id)
    .executeUpdate();

// 'order' trong persistence context vẫn có thể giữ state cũ.
~~~

Sau bulk DML, các managed entity đã được nạp có thể không biết hàng SQL của chúng đã bị xóa. Tùy use case, bạn cần **flush các thay đổi pending trước bulk**, rồi **clear** persistence context hoặc sử dụng EntityManager mới để tránh tiếp tục làm việc với state cũ. Clear làm các object hiện tại detached và có thể làm mất thay đổi chưa flush, vì vậy không gọi bừa.

### 14.2. Bulk DELETE theo bước

Một thao tác quản trị xóa đơn nháp cũ có thể có dạng:

~~~sql
DELETE FROM order_items
WHERE order_id IN (
    SELECT id FROM purchase_orders
    WHERE status = 'DRAFT'
);

DELETE FROM purchase_orders
WHERE status = 'DRAFT';
~~~

Đây chỉ là ý tưởng SQL minh họa. Trong hệ thống thật, cần giới hạn theo tuổi dữ liệu, tenant, không có payment/shipment, khóa, concurrency, batch size và có thể xử lý những FK khác. Hai câu DELETE trong một transaction đơn giản vẫn có thể đua với workflow khác thêm Payment hoặc thay status; chưa có nghĩa đây là giải pháp production an toàn.

Một hệ thống có yêu cầu chặt có thể dùng **CTE chọn ID và khóa**, batch theo ID, xử lý FK/constraint/transaction phù hợp rồi đo ảnh hưởng DB. Không tự triển khai cleanup rộng từ ví dụ rút gọn khi chưa xem data retention policy.

### 14.3. Spring Data JPA: các phương thức delete không giống nhau

Trong Spring Data JPA, bạn có thể gặp:

~~~java
repository.delete(entity);
repository.deleteById(id);
repository.deleteAll(entities);
repository.deleteAllInBatch();
repository.deleteAllByIdInBatch(ids);
~~~

Các phương thức theo entity có thể dùng lifecycle removal; các phương thức **InBatch** thường dùng bulk delete và **bỏ qua JPA entity callbacks/cascade theo từng entity**. Việc triển khai chính xác, số SELECT và exception khi ID không tồn tại phụ thuộc phiên bản Spring Data JPA. Trước khi thay một vòng lặp delete bằng batch để tối ưu, cần xác minh nghiệp vụ có cần cascade/orphan/validation hay không.

## 15. Lifecycle callbacks: @PreRemove và @PostRemove

JPA cung cấp callback:

~~~java
import jakarta.persistence.*;

@Entity
public class AuditExample {
    @Id
    private Long id;

    @PreRemove
    void beforeRemoval() {
        // Hook trước thao tác xóa ở mức entity lifecycle.
    }

    @PostRemove
    void afterRemoval() {
        // Hook sau thao tác xóa ở mức entity lifecycle.
    }
}
~~~

Với EntityManager.remove(), provider có thể gọi callback theo lifecycle của entity. **@PreRemove** được gọi trước thao tác xóa thực tế; **@PostRemove** sau thao tác loại bỏ tương ứng ở cấp ORM, thời điểm cụ thể liên quan flush. Những callback ấy **không bảo đảm transaction đã commit**.

### 15.1. Không gửi email hoặc xóa file ngay trong callback

Giả sử @PostRemove gửi thông báo “Đơn đã bị xóa” hoặc xóa một file khỏi object storage. Nếu transaction DB sau đó rollback, thông báo/file có thể đã thay đổi ở hệ thống ngoài trong khi hàng DB vẫn còn.

Để phối hợp side effect sau commit, có thể dùng event ứng dụng sau commit hoặc **transactional outbox** cho yêu cầu độ tin cậy cao. Callback nên đơn giản, tránh gọi repository, network hoặc logic làm thay đổi graph theo cách không được provider bảo đảm.

### 15.2. Bulk DELETE bỏ qua callback entity

~~~java
em.createQuery("delete from AuditExample a").executeUpdate();
~~~

Lệnh bulk này không tương đương việc nạp từng AuditExample rồi gọi remove. Nếu hệ thống dựa vào @PreRemove để ghi audit, bulk delete có thể bỏ qua nó. Đối với dữ liệu cần lịch sử kiểm toán, phải có cơ chế audit độc lập phù hợp với cả DML trực tiếp, scheduler và client database khác.

## 16. Xóa và quan hệ nhiều-nhiều

Giả sử Customer có tập sản phẩm yêu thích:

~~~java
@ManyToMany
@JoinTable(
    name = "customer_favorite_products",
    joinColumns = @JoinColumn(name = "customer_id"),
    inverseJoinColumns = @JoinColumn(name = "product_id")
)
private Set<Product> favoriteProducts = new HashSet<>();
~~~

Khi xóa **một association**:

~~~java
customer.getFavoriteProducts().remove(product);
~~~

Hibernate có thể xóa **hàng bảng nối**:

~~~sql
DELETE FROM customer_favorite_products
WHERE customer_id = ? AND product_id = ?;
~~~

Điều này **không xóa Product**. Nếu xóa một Customer, các liên kết join table của nó phải được dọn theo ORM hoặc FK DB, nhưng các Product vẫn độc lập.

**Không dùng CascadeType.ALL/REMOVE trên ManyToMany chỉ vì muốn xóa association**, vì REMOVE có thể lan tới entity Product được nhiều Customer tham chiếu. Nếu liên kết có thuộc tính như ngày yêu thích hoặc ghi chú, nên cân nhắc entity liên kết riêng để quản lý vòng đời chính xác.

## 17. Xóa trong hệ thống có kế thừa entity

Giả sử Payment có các subclass CardPayment và WalletPayment. Khi em.remove(cardPayment), Hibernate phải xóa dữ liệu theo **chiến lược @Inheritance**:

- **SINGLE_TABLE:** loại bỏ hàng trong một bảng chung.
- **JOINED:** xóa dữ liệu ở các bảng subclass và root dọc hierarchy, tôn trọng FK.
- **TABLE_PER_CLASS:** xóa hàng ở bảng concrete tương ứng.

Không suy luận rằng xóa một entity luôn bằng đúng một statement. Số bảng và cơ chế kế thừa làm thay đổi DML, ngay cả khi lệnh Java vẫn là remove(entity).

Trong hierarchy có **@Version** trên root, optimistic locking cũng cần được provider xử lý phù hợp với chiến lược. Kiểm tra SQL thực tế thay vì viết một native DELETE nhắm vào đúng một bảng theo phỏng đoán, đặc biệt với JOINED.

## 18. Xóa hàng loạt và hiệu năng

Với vài chục đơn nháp, nạp từng entity và remove có thể chấp nhận được để giữ callback/cascade. Với vài triệu hàng dữ liệu cũ, cách đó có nguy cơ:

- Tải quá nhiều entity/collection vào persistence context.
- Tiêu thụ heap và làm garbage collection tăng.
- Gây nhiều SELECT do cascade/LAZY association.
- Sinh nhiều DELETE đơn lẻ, gây nhiều round-trip.
- Giữ transaction và lock quá lâu.

Nếu vẫn phải dùng entity removal theo lô:

~~~java
@Transactional
public void deleteSmallManagedBatch(List<Long> ids) {
    for (Long id : ids) {
        PurchaseOrder order = em.find(PurchaseOrder.class, id);
        if (order != null && order.getStatus() == OrderStatus.DRAFT) {
            em.remove(order);
        }
    }
    em.flush();
    em.clear();
}
~~~

Đây là minh họa **một batch nhỏ đã được kiểm quyền**, không phải giải pháp tự động xóa hàng triệu đơn. Sau clear, mọi entity đã managed trong context trở thành detached; đừng tiếp tục chỉnh sửa chúng rồi chờ flush.

Với cleanup lớn, hãy thiết kế **batch có giới hạn** và có thể commit theo lô, chọn tiêu chí rõ ràng và đo IO/lock/WAL/replication lag. Có thể dùng native/bulk SQL với quy tắc FK rõ ràng khi không cần callback JPA; cần cơ chế audit riêng, theo dõi lỗi và có khả năng tiếp tục công việc.

### 18.1. Batching JDBC

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 30
        order_updates: true
~~~

JDBC batching có thể gom những statement tương thích trong một số tình huống, nhưng không thay đổi ý nghĩa cascade, không xóa constraint và không biến một use case có N+1 SELECT thành chỉ một SELECT. Khả năng batch DELETE phụ thuộc Hibernate version, ID/version mapping, driver và batch settings; cần đo thực tế. **hibernate.order_updates** hỗ trợ ordering của UPDATE trong bối cảnh phù hợp; không nên coi nó là cấu hình riêng để tối ưu DELETE.

### 18.2. Vì sao cần cân nhắc thứ tự xóa?

Nếu một bảng con trỏ đến bảng cha bằng FK NOT NULL, database thường yêu cầu xóa child trước parent trừ khi FK có action thích hợp. Với quan hệ phức tạp:

~~~text
PurchaseOrder <- OrderItem
PurchaseOrder <- Payment
Payment       <- Refund
OrderItem     <- ShipmentLine
~~~

Thao tác xóa “đơn hàng” không thể tùy tiện DELETE parent trước. Một số child còn phải **giữ lịch sử**, khiến xóa vật lý parent không phải lựa chọn hợp lệ. Thiết kế xóa là bài toán **vòng đời aggregate và luật retention**, không chỉ sắp xếp SQL.

## 19. Theo dõi SQL và Hibernate Statistics

Ở môi trường local dùng Hibernate 6:

~~~yaml
spring:
  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger **org.hibernate.SQL** cho bạn biết:

- DELETE được sinh trên bảng nào?
- Có DELETE OrderItem trước khi DELETE PurchaseOrder không?
- Có UPDATE FK về NULL thay vì DELETE child không?
- Hibernate có phát thêm SELECT để tải association phục vụ cascade/callback không?

Logger bind **org.hibernate.orm.jdbc.bind** hiển thị tham số (Hibernate ORM 6); nó có thể lộ ID, dữ liệu khách hàng hoặc dữ liệu nhạy cảm, nên chỉ bật khi phù hợp, không giữ TRACE đại trà trên production.

Thống kê:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory = emf.unwrap(SessionFactory.class);
Statistics statistics = sessionFactory.getStatistics();

long beforeDeletes = statistics.getEntityDeleteCount();
long beforeStatements = statistics.getPrepareStatementCount();

// Thực hiện remove và flush/commit trong test cô lập.

long entitiesDeleted = statistics.getEntityDeleteCount() - beforeDeletes;
long statements = statistics.getPrepareStatementCount() - beforeStatements;
~~~

Giả định biến **emf** là EntityManagerFactory được inject. Các bộ đếm là **tích lũy toàn SessionFactory**, nên chỉ có thể dùng hiệu before/after cho một phép thử riêng khi không bị request khác xen vào. **EntityDeleteCount** không đồng nghĩa số row do DB cascade xóa; **PrepareStatementCount** cũng không phản ánh toàn bộ round-trip/IO.

Khi cần xác nhận kết quả, sau commit mở transaction hoặc persistence context mới rồi truy vấn database. Đừng chỉ dựa vào entity removed còn nằm trong bộ nhớ Java.

## 20. Kiểm thử remove qua JPA và database

Test nên chứng minh **cả trạng thái trong persistence context lẫn trạng thái DB sau commit**.

### 20.1. Test trạng thái managed và SQL xóa

Một skeleton integration test:

~~~java
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class RemoveLifecycleTest {
    @Autowired EntityManager em;

    @Test
    void removingManagedDraftDeletesOrderAndItsItems() {
        // Arrange: tạo Customer, Product, PurchaseOrder nháp
        // với ít nhất một OrderItem; persist trong test transaction.

        // em.flush();
        // em.clear();
        // PurchaseOrder managed = em.find(PurchaseOrder.class, id);

        // Act:
        // em.remove(managed);
        // em.flush();
        // em.clear();

        // Assert: tìm order bằng ID trả null; tìm OrderItem
        // bằng ID cũng không có, Product và Customer vẫn tồn tại.
    }
}
~~~

Đây là bộ khung mô tả các bước; cần dữ liệu fixture, ID và import/domain phù hợp trước khi chạy. Với **@DataJpaTest**, test transaction thường rollback ở cuối test, nên muốn chứng minh một commit thật và quan sát từ transaction mới cần cấu hình transaction test phù hợp (ví dụ TestTransaction hoặc TransactionTemplate).

### 20.2. Test detached entity

1. Tạo và persist một PurchaseOrder trong transaction A.
2. Đóng EntityManager A hoặc **clear** để đối tượng trở thành detached.
3. Trong transaction B dùng EntityManager khác, gọi remove(detached).
4. Xác nhận lỗi trạng thái phù hợp và rollback B.
5. Nạp lại entity managed theo ID, kiểm business rule rồi remove; xác nhận kết quả sau commit.

Điểm cần hiểu không chỉ là exception, mà là **object identity** trong Java khác với **persistence identity** (class + ID trong context) mà ORM đang quản lý.

### 20.3. Test ràng buộc FK

Tạo PurchaseOrder và Payment tham chiếu nó; sau đó cố xóa order nhưng không xóa Payment. Với FK ràng buộc, transaction phải bị từ chối nếu ORM vẫn gửi DELETE parent. Trong ứng dụng, service tốt nên chặn trước bằng policy và trả lỗi nghiệp vụ, nhưng DB constraint vẫn phải được giữ.

Đừng kết luận FK đúng nếu chỉ xem collection trong memory: phải **flush hoặc commit** để database có cơ hội kiểm tra constraint.

### 20.4. Test orphanRemoval

1. Tạo order có hai OrderItem và commit.
2. Trong transaction mới, load order managed.
3. Dùng helper **removeItem(item1)**, flush/commit.
4. Nạp lại: chỉ item1 bị xóa; item2, Product và Order còn.

Đây là test khác với **em.remove(order)**, không nên gộp hai hành vi thành một test chung.

### 20.5. Test optimistic conflict

Mở hai transaction độc lập:

~~~text
T1: load Order, version = 3
T2: cập nhật Order, commit version = 4
T1: gọi remove trên entity version 3, flush/commit
~~~

Kỳ vọng T1 không xóa được bản ghi dựa trên phiên bản cũ theo optimistic locking. Kiểm tra exception/row state trong database thực tế (PostgreSQL Testcontainers chẳng hạn). Không dùng cùng một persistence context cho cả hai luồng vì nó không mô phỏng concurrency.

### 20.6. Test bulk DELETE khác entity removal

Tạo dữ liệu có lifecycle callback hoặc child quan hệ; thử:

~~~java
em.createQuery("delete from PurchaseOrder o where o.id = :id")
    .setParameter("id", id)
    .executeUpdate();
~~~

Quan sát callbacks/cascade có khác EntityManager.remove hay không, FK có chặn thao tác không, persistence context còn entity cũ không. Chỉ dùng test trên dữ liệu tự tạo, không chạy câu bulk DELETE không có WHERE ở database thật.

## 21. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| remove(entity) ném IllegalArgumentException | Entity detached hoặc không phải entity hợp lệ | Nạp managed entity bằng find trong transaction rồi remove |
| Gọi remove mà không thấy SQL DELETE ngay | Hibernate trì hoãn tới flush/commit | Quan sát ở điểm flush, không suy từ lời gọi Java |
| Có DELETE trong log nhưng dữ liệu vẫn còn | Transaction rollback hoặc query ở thời điểm/isolation khác | Kiểm tra commit, exception và trạng thái DB từ transaction mới |
| DELETE parent lỗi foreign key | Child/Payment vẫn tham chiếu parent | Định nghĩa rõ cascade, xử lý child hoặc từ chối xóa |
| Xóa Order làm mất Product/Customer | Cascade REMOVE/ALL sai sang entity dùng chung | Bỏ cascade xóa ở quan hệ đó |
| Xóa item khỏi collection nhưng DB không xóa | Thiếu orphanRemoval, sửa sai phía owning, entity detached | Kiểm tra mapping, helper và persistence context |
| Loại một child khỏi List gây lỗi orphan collection | Thay reference collection managed bằng list mới | Giữ wrapper, thay đổi bằng add/remove có kiểm soát |
| Xóa bản ghi mới tạo mà không có DELETE | Entity chưa từng được insert | Hiểu new state; không có row DB để xóa |
| Xóa theo ID lỗi vì entity không tồn tại | getReference chưa xác minh row, hoặc conflict sau query | Chọn contract 404/204 và xử lý existence/concurrency rõ |
| Bulk DELETE không gọi @PreRemove | Bulk JPQL bỏ qua lifecycle từng entity | Chọn entity removal hoặc audit riêng cho bulk DML |
| Bulk DELETE khiến object khác giữ dữ liệu cũ | Persistence context không tự được đồng bộ với DML trực tiếp | Flush/clear hoặc EntityManager mới theo use case |
| Xóa trong race condition làm mất dữ liệu mới | Không kiểm version hoặc business state sau concurrent update | @Version, khóa và retry cả use case có kiểm tra lại |
| Soft delete nhưng query vẫn trả hàng đã xóa | Thiếu filter/điều kiện deleted flag | Tạo chính sách lọc thống nhất, kiểm query native |
| Không thể tạo lại unique value đã soft-delete | Constraint cũ vẫn áp dụng cả row ẩn | Thiết kế unique index có điều kiện nếu domain cho phép |
| Xóa qua bulk/batch làm thiếu audit | Lựa chọn API bypass callbacks | Dùng audit ở DB/outbox hoặc quy trình batch có chủ đích |
| Repository.deleteById bất thường với ID không tồn tại | Hành vi API/version và policy chưa thống nhất | Chọn rõ 404/204, kiểm thử đúng version Spring Data |

## 22. Bài thực hành tổng hợp: xóa một đơn nháp đúng cách

Xây dựng một ứng dụng nhỏ với Customer, Product, PurchaseOrder, OrderItem, Payment như phần 4–5. Cấu hình PostgreSQL và SQL logging local. Thực hiện:

1. **Tạo dữ liệu:** một Customer, hai Product, một Order DRAFT và hai OrderItem.
2. **Xóa managed entity:** find Order trong transaction, remove, flush; quan sát DELETE ở order_items và purchase_orders.
3. **Xác minh độc lập:** sau commit, mở EntityManager mới và kiểm tra Customer/Product vẫn tồn tại.
4. **Detached:** tách Order khỏi context rồi gọi remove trong context khác; ghi nhận exception thích hợp và sửa bằng find.
5. **Không có transaction:** thử một ca có chủ đích trong môi trường test, quan sát TransactionRequiredException/hành vi cấu hình; sau đó dùng @Transactional.
6. **Rollback:** remove + flush rồi ném runtime exception; xác minh row còn sau rollback.
7. **Orphan removal:** chỉ bỏ một OrderItem, kiểm tra chỉ child đó bị xóa.
8. **FK Payment:** tạo Payment cho order; kiểm tra service từ chối xóa và DB cũng bảo vệ foreign key.
9. **Confirmed:** đổi status sang CONFIRMED, gọi deleteDraft và xác nhận business exception.
10. **Concurrency:** mở hai transaction, một bên xác nhận/đổi version trong khi bên kia thử xóa; xác minh optimistic locking hoặc policy mới ngăn mất dữ liệu.
11. **Bulk DELETE:** so sánh entity remove với JPQL bulk, ghi khác biệt callback, cascade, trạng thái persistence context.
12. **Soft delete:** thêm deleted_at hoặc dùng workflow CANCELLED; viết query chỉ lấy đơn active và thử unique constraint liên quan.

Ghi kết quả vào bảng:

| Ca thử | Entity state ban đầu | API sử dụng | SQL quan sát | Kết quả sau commit |
|---|---|---|---|---|
| Xóa order DRAFT | Managed | remove | Điền từ log | Order/items không còn |
| Xóa object detached | Detached | remove | Điền từ log | Bị từ chối theo JPA |
| Xóa order có Payment | Managed | remove sau policy check | Điền từ log | Không xóa |
| Bỏ một OrderItem | Managed parent | removeItem | Điền từ log | Chỉ orphan bị xóa |
| Xóa bằng JPQL bulk | Không đi qua từng managed entity | executeUpdate | Điền từ log | Phụ thuộc FK và điều kiện |
| Rollback sau flush | Removed trong transaction | remove + rollback | Điền từ log | Hàng còn |

Không điền số lượng SQL giả định thành kết quả đã chạy. Mục tiêu là **quan sát đúng hành vi trên mapping và database đang dùng**.

## 23. Checklist thiết kế trước khi triển khai DELETE

Trước một use case xóa dữ liệu, hãy trả lời tuần tự:

1. **Đối tượng cần xóa là gì?** Xóa entity, gỡ association, xóa collection value hay hủy một giao dịch?
2. **Đúng entity và quyền truy cập chưa?** ID, tenant, owner, role và business rule được kiểm tra thế nào?
3. **Đối tượng có managed không?** Dùng find/getReference phù hợp, không remove detached object.
4. **Transaction có bao trùm kiểm tra và xóa không?** Hiểu flush, commit, rollback và exception tại thời điểm commit.
5. **Có con phụ thuộc vòng đời?** CascadeType.REMOVE/orphanRemoval có đúng không; Product/Customer nào phải được giữ?
6. **FK database cho phép gì?** RESTRICT/NO ACTION, CASCADE, SET NULL; DB có constraint thực sự không?
7. **Có yêu cầu lịch sử/audit không?** Chọn soft delete, trạng thái CANCELLED hoặc hard delete phù hợp.
8. **Nếu concurrent update xảy ra?** Có version/lock, thông báo xung đột và chính sách retry đúng không?
9. **Có dùng bulk DML không?** Có chấp nhận bỏ qua cascade/callback và xử lý persistence context stale chưa?
10. **Đã đo SQL chưa?** Xác nhận chính xác row bị xóa, số statement, FK và trạng thái DB sau commit.

## 24. Kết luận

Trong Hibernate, **remove** là lời yêu cầu chuyển một **managed entity** sang trạng thái removed trong persistence context. SQL DELETE được phát sinh khi đồng bộ (flush) theo mapping và transaction, còn hiệu lực bền vững của thay đổi phụ thuộc **commit**. Điều kiện để xóa thành công không chỉ là “tìm được object”: phải phù hợp với quan hệ cascade/orphanRemoval, database foreign key, optimistic locking và quy tắc nghiệp vụ.

Với hệ thống đơn hàng, **OrderItem có thể bị xóa khi Order nháp bị xóa**, nhưng **Product và Customer không được xóa theo**. Một Payment tồn tại có thể khiến xóa vật lý phải bị từ chối; với đơn đã xác nhận, **hủy/soft delete** thường diễn đạt nghiệp vụ tốt hơn hard delete. Khi cần xử lý hàng loạt, hãy nhớ bulk DELETE không đi qua vòng đời của từng entity như EntityManager.remove.

Nếu thiết kế rõ **ai sở hữu vòng đời dữ liệu, khi nào cho phép xóa, làm gì với những entity liên quan và cách chứng minh kết quả sau commit**, thao tác remove sẽ an toàn và dễ bảo trì hơn rất nhiều so với chỉ gọi một phương thức ORM.
