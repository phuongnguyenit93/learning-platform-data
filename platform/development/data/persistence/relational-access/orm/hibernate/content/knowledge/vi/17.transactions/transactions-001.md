# Giao dịch nghiệp vụ, giao dịch Hibernate và giao dịch cơ sở dữ liệu

## 1. Ba khái niệm cùng được gọi là “transaction”

Trong ứng dụng Java sử dụng Hibernate ORM, từ **giao dịch** có thể chỉ ba phạm vi khác nhau:

1. **Giao dịch nghiệp vụ (business transaction)**: một mục tiêu có ý nghĩa với người dùng, như “đặt hàng và thanh toán thành công”. Nó được định nghĩa bởi trạng thái nghiệp vụ, quy tắc và kết quả cuối cùng.
2. **Giao dịch ở tầng Hibernate/JPA**: phạm vi thao tác mà EntityManager/Session tham gia, nơi Hibernate theo dõi entity, thực hiện dirty checking, flush các câu SQL và phối hợp commit/rollback qua transaction API.
3. **Giao dịch cơ sở dữ liệu (database transaction)**: đơn vị nguyên tử thực sự do hệ quản trị cơ sở dữ liệu thực hiện, bao gồm SQL, lock, isolation, commit và rollback.

Ba phạm vi có quan hệ với nhau nhưng **không mặc nhiên trùng nhau**. Ví dụ quy trình khách đặt hàng, hệ thống giữ hàng, thu tiền qua cổng thanh toán và gửi email có thể kéo dài nhiều giây hoặc phút và liên quan đến nhiều hệ thống. Ta không nên giữ một JDBC transaction mở suốt toàn bộ thời gian ấy.

Ngược lại, một thao tác nghiệp vụ nhỏ như “đổi địa chỉ giao hàng của một đơn nháp” có thể được thực hiện trong **một transaction DB ngắn** thông qua **một @Transactional service method**.

~~~mermaid
flowchart TD
    B["Giao dịch nghiệp vụ: đặt hàng đến khi hoàn tất"] --> U1["Bước 1: tạo đơn và giữ tồn kho"]
    B --> U2["Bước 2: yêu cầu thanh toán"]
    B --> U3["Bước 3: nhận kết quả, xác nhận hoặc hủy"]
    U1 --> H1["Hibernate/JPA transaction #1"]
    U3 --> H2["Hibernate/JPA transaction #2"]
    H1 --> DB1["Database transaction #1 - commit"]
    H2 --> DB2["Database transaction #2 - commit"]
    U2 --> X["Cổng thanh toán - hệ thống bên ngoài"]
~~~

**Ý chính:** transaction nghiệp vụ có thể bao gồm nhiều transaction database, nhiều thông điệp và những bước bù trừ. Hibernate không thể tự biến toàn bộ quy trình xuyên dịch vụ thành một transaction ACID duy nhất.

Bài học nằm trong chương **Giao dịch** của module Data Persistence / Relational Access / ORM Hibernate. Các ví dụ dùng **Java 17+**, **Jakarta Persistence (jakarta.persistence.*)**, **Hibernate ORM 6.x**, **Spring Boot 3.x/Spring Data JPA** và **PostgreSQL**. Các nguyên lý ranh giới giao dịch cũng áp dụng khi dùng Hibernate trực tiếp; cách cấu hình cụ thể có thể khác theo transaction manager, ứng dụng và cơ sở dữ liệu.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Vẽ ranh giới business transaction và phân rã thành các bước database transaction hợp lý.
- Giải thích quan hệ giữa **EntityManager/Session**, **persistence context**, **flush**, **commit** và **rollback**.
- Hiểu **@Transactional** của Spring định nghĩa những gì, và những gì nó **không** bảo đảm.
- Nhận biết tác động của **isolation**, **lock**, **@Version** và constraint DB trong các giao dịch đồng thời.
- Thiết kế nghiệp vụ đặt hàng mà không gọi API thanh toán chậm trong transaction giữ lock.
- Dùng **transactional outbox**, idempotency và compensation khi phải phối hợp database với hệ thống bên ngoài.
- Chẩn đoán các lỗi như **save nhưng chưa commit**, **flush nhưng vẫn rollback**, **self-invocation**, **bắt exception làm transaction không rollback**, và **bulk update làm entity managed bị cũ**.

## 2. Phân biệt ba tầng theo trách nhiệm

| Tiêu chí | Giao dịch nghiệp vụ | Giao dịch Hibernate/JPA | Giao dịch cơ sở dữ liệu |
|---|---|---|---|
| Định nghĩa | Mục tiêu và quy tắc nghiệp vụ | Phạm vi làm việc với entity và transaction API | Đơn vị SQL được DB xử lý nguyên tử |
| Ai quyết định ranh giới? | Domain/application workflow | Service, framework transaction manager hoặc code JPA | BEGIN/COMMIT/ROLLBACK trên DB connection, hoặc transaction manager phối hợp |
| Có thể kéo dài qua nhiều request? | Có | Có thể về kỹ thuật nhưng thường không nên | Nói chung tránh giữ lâu; mỗi giao dịch DB nên ngắn |
| Bao gồm API bên ngoài? | Thường có | Không tự quản lý tính nguyên tử của HTTP/email | Không rollback được HTTP/email thông thường |
| Cơ chế khôi phục khi lỗi | Retry, trạng thái, compensation, saga | Đánh dấu rollback-only, rollback API, xử lý exception | Undo các thay đổi chưa commit trong transaction |
| Tính nguyên tử | Phụ thuộc workflow được thiết kế | Dựa trên transaction resource được phối hợp | ACID trong phạm vi DB transaction |
| Ví dụ | Đặt hàng → thanh toán → giao hàng | @Transactional placeDraftOrder() | INSERT order, UPDATE stock, INSERT outbox rồi COMMIT |

Trên hệ thống dùng **một datasource và một local resource transaction**, phương thức **@Transactional** thông thường tham gia **một giao dịch DB vật lý**. Hibernate transaction ở đây không phải “một tầng ACID bổ sung chạy độc lập”; nó là API/cơ chế phối hợp làm việc với transaction của database.

Tuy nhiên, trong ứng dụng có nhiều resource, transaction propagation, JTA hoặc callback bất đồng bộ, quan hệ “mỗi @Transactional đúng một DB transaction” có thể thay đổi. Vì vậy phải hỏi **transaction manager nào được sử dụng** và **những resource nào thực sự tham gia**.

## 3. Giao dịch nghiệp vụ: thành công được định nghĩa bởi điều gì?

Giả sử use case **đặt hàng** có các bước:

1. Khách gửi request với mã yêu cầu duy nhất.
2. Kiểm tra sản phẩm và số lượng.
3. Giữ số lượng tồn kho, lưu đơn chờ thanh toán.
4. Yêu cầu cổng thanh toán xử lý số tiền.
5. Nhận kết quả, chuyển đơn sang PAID hoặc giải phóng hàng đã giữ.
6. Gửi email và đưa đơn vào quy trình giao hàng.

Đối với khách hàng, đây là **một giao dịch nghiệp vụ**: “Tôi đã đặt được hàng hay chưa?”. Nhưng các bước không nhất thiết chạy trong một transaction cơ sở dữ liệu.

### 3.1. Định nghĩa trạng thái thay vì dựa vào một hàm rất dài

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_PAYMENT: Tạo đơn và giữ tồn kho
    PENDING_PAYMENT --> PAID: Thanh toán thành công
    PENDING_PAYMENT --> CANCELLED: Thanh toán thất bại hoặc hết hạn
    PAID --> FULFILLING: Bắt đầu giao hàng
    FULFILLING --> COMPLETED: Giao xong
    PAID --> REFUND_PENDING: Bắt đầu hoàn tiền
    REFUND_PENDING --> REFUNDED: Hoàn tiền thành công
~~~

Mỗi trạng thái cần quy tắc:

- Không thanh toán hai lần cho cùng một yêu cầu.
- Không xác nhận hai lần để trừ tồn kho hai lần.
- Không chuyển CANCELLED thẳng thành PAID nếu quy tắc đã cấm.
- Khi thanh toán thất bại, lượng hàng đã giữ cần được giải phóng một cách idempotent.
- Gửi email thất bại không nhất thiết được phép “rollback” một khoản tiền đã thu thành công.

Những quy tắc này không thể diễn đạt đầy đủ chỉ bằng **@Transactional**. Annotation chỉ giúp xác định **một đoạn làm việc với resource giao dịch**, không tự xác định workflow trạng thái hoặc xử lý bước bên ngoài.

### 3.2. Một nghiệp vụ có thể cần nhiều lần commit

~~~text
T0  POST /orders          -> DB transaction A: giữ stock, tạo PENDING_PAYMENT, outbox
T1  Commit A              -> Đơn và reservation tồn tại bền vững
T2  Worker gọi payment API -> Không giữ transaction A
T3  Payment trả kết quả
T4  DB transaction B      -> Cập nhật đơn PAID hoặc CANCELLED
T5  Commit B              -> Trạng thái có hiệu lực
T6  Worker gửi email      -> Có thể retry độc lập
~~~

**Giao dịch nghiệp vụ thành công** khi các trạng thái cuối và tác vụ liên quan đạt điều kiện đã thống nhất, không phải khi transaction A commit. Sau A, khách có thể chỉ nhận **đơn đang chờ thanh toán**.

Nếu việc giữ tồn kho nhiều phút không phù hợp, có thể dùng reservation có **expiresAt**, hoặc trì hoãn giữ tồn kho đến khi gần thanh toán. Đó là quyết định nghiệp vụ/sức chứa hàng hóa, không phải tính năng tự động của Hibernate.

## 4. Giao dịch database: BEGIN, COMMIT, ROLLBACK và ACID

Tại tầng PostgreSQL, một transaction DB có thể gồm nhiều câu SQL:

~~~sql
BEGIN;

UPDATE products
SET stock_quantity = stock_quantity - 2
WHERE id = 101 AND stock_quantity >= 2;

INSERT INTO purchase_orders (request_id, customer_id, status, total_amount)
VALUES ('req-abc', 45, 'PENDING_PAYMENT', 500000);

INSERT INTO outbox_events (id, aggregate_type, aggregate_id, event_type)
VALUES ('d50b68a2-9258-43e6-987e-5f6b0d4e9a20', 'PurchaseOrder',
        9001, 'OrderPlaced');

COMMIT;
~~~

SQL chỉ minh họa trình tự; trong hệ thống thật cần **kiểm tra số hàng UPDATE stock**, lấy ID order được sinh và xây payload outbox đúng định dạng. Không được trừ tồn kho rồi commit khi điều kiện UPDATE không cập nhật hàng nào.

Nếu có lỗi trước COMMIT và transaction rollback:

~~~sql
ROLLBACK;
~~~

DB hủy những thay đổi chưa commit thuộc transaction ấy. Các thuộc tính ACID thường được tóm tắt như sau:

| Thuộc tính | Ý nghĩa trong ngữ cảnh đơn hàng |
|---|---|
| **Atomicity** | Hoặc cả bộ thao tác DB thuộc transaction được commit, hoặc chúng bị rollback; không lưu nửa chừng |
| **Consistency** | Constraint/invariant DB được duy trì qua transition hợp lệ; tính đúng nghiệp vụ còn phụ thuộc code và isolation |
| **Isolation** | Các transaction đồng thời nhìn thấy và tác động dữ liệu theo mức isolation/lock đã chọn |
| **Durability** | Khi COMMIT được xác nhận theo cấu hình DB, thay đổi được lưu bền vững theo bảo đảm của DB |

### 4.1. “Database transaction” không bao gồm mọi side effect

Một transaction PostgreSQL **không tự rollback**:

- HTTP POST đã gửi sang cổng thanh toán.
- Email đã gửi.
- File đã upload lên object storage.
- Thông điệp đã publish vào broker ngoài DB mà không tham gia cùng distributed transaction.
- Tác vụ đã chạy ở thread/process khác.

Vì thế cách sau có thể tạo trạng thái sai:

~~~java
@Transactional
public void checkout() {
    saveOrder();
    paymentGateway.chargeCard();  // Side effect bên ngoài DB.
    updateStock();
}
~~~

Nếu charge thành công nhưng updateStock lỗi và transaction DB rollback, **tiền có thể đã được trừ nhưng đơn không còn trong DB**. Rollback DB không biến API thanh toán thành chưa từng xảy ra.

### 4.2. Isolation không phải phép màu ngăn mọi race condition

Giả sử tồn kho bằng 1. Hai transaction cùng đọc 1 rồi cùng quyết định đặt 1 sản phẩm. Nếu chỉ đọc rồi tính trong Java mà không có lock/version/SQL có điều kiện, hai request có thể chấp nhận cùng một mặt hàng và gây overselling.

Constraint, row lock, optimistic locking và câu UPDATE atomic là các công cụ phối hợp với isolation. Việc chọn mức isolation mạnh hơn có thể giúp một số hiện tượng, nhưng thường cần **retry khi xung đột** và đánh giá hiệu năng.

## 5. Hibernate Session và persistence context tham gia giao dịch thế nào?

Hibernate quản lý entity bên trong **persistence context**. Một entity **managed** được theo dõi thay đổi; khi flush, Hibernate sinh SQL tương ứng và chuyển SQL đến DB thông qua connection đang tham gia transaction.

~~~mermaid
sequenceDiagram
    participant App as Application service
    participant EM as EntityManager / Hibernate Session
    participant PC as Persistence context
    participant DB as Database transaction
    App->>EM: begin / @Transactional
    App->>EM: find(Product, 101)
    EM->>DB: SELECT product
    DB-->>EM: row
    EM->>PC: Managed Product
    App->>PC: product.reserve(2)
    Note over PC: State thay đổi trong Java
    App->>EM: persist(PurchaseOrder)
    App->>EM: flush hoặc commit
    EM->>PC: Dirty checking và action queue
    EM->>DB: UPDATE products, INSERT orders
    App->>EM: commit
    EM->>DB: COMMIT
    DB-->>App: Transaction hoàn tất
~~~

### 5.1. Entity managed không phải hàng đã commit

~~~java
Product product = entityManager.find(Product.class, 101L);
product.reserve(2);
// Object Java đã có stockQuantity mới.
// DB có thể chưa nhận UPDATE cho đến khi flush.
~~~

Trong persistence context, **product.getStockQuantity()** phản ánh thay đổi Java ngay lập tức. Nhưng DB chỉ được đồng bộ khi Hibernate flush SQL. Giao dịch khác có được thấy giá trị đó hay không phụ thuộc commit và isolation.

### 5.2. Persist, save, flush và commit không đồng nghĩa

| Thao tác | Tác động chính | Có bảo đảm commit không? |
|---|---|---|
| **entityManager.persist(entity)** | Đưa entity mới vào persistence context; Hibernate lên lịch INSERT hoặc thực hiện sớm nếu cần ID | Không |
| **repository.save(entity)** | Spring Data JPA quyết định persist/merge tùy trạng thái entity | Không tự bảo đảm commit nếu đã ở transaction bao ngoài |
| **entityManager.flush()** | Đồng bộ pending SQL với DB trong transaction | Không |
| **repository.saveAndFlush(entity)** | Save rồi yêu cầu flush trong transaction | Không |
| **transaction commit** | Hoàn tất transaction DB sau khi flush cần thiết | Có, nếu commit thành công |
| **rollback** | Hủy các thay đổi chưa commit trong DB transaction | Không đảo mọi thay đổi trong object Java hoặc side effect bên ngoài |

Ví dụ:

~~~java
@Transactional
public Long createOrder(PurchaseOrder order) {
    entityManager.persist(order);
    entityManager.flush();
    return order.getId();
}
~~~

Khi phương thức trả về, interceptor transaction của Spring mới thực hiện bước commit. Vì thế **flush thành công trong method chưa có nghĩa commit chắc chắn thành công**. Constraint deferred, lỗi connection hay các công việc khác trong transaction vẫn có thể khiến commit thất bại.

Với IDENTITY, Hibernate thường cần thực hiện INSERT sớm để lấy generated ID; với SEQUENCE, có thể lấy ID trước INSERT. Không suy luận “đã có ID” đồng nghĩa “đã commit”.

### 5.3. Auto flush trước query

Hibernate có thể flush trước một câu query khi cần đảm bảo kết quả query phù hợp các thay đổi pending, tùy flush mode, query space và transaction. Ví dụ:

~~~java
product.changePrice(new BigDecimal("120.00"));
List<Product> expensive = entityManager.createQuery(
    "select p from Product p where p.price > :min",
    Product.class
).setParameter("min", new BigDecimal("100.00"))
 .getResultList();
~~~

SQL UPDATE có thể xuất hiện **trước SELECT** dù chưa gọi flush tường minh. Điều này không biến UPDATE thành committed. Để hiểu thứ tự SQL thật, cần xem log của mapping/dialect/flush mode hiện tại.

### 5.4. Persistence context và DB transaction có thể có vòng đời khác nhau

EntityManager/Session không đồng nghĩa JDBC transaction. Session có thể mở trước transaction và đóng sau nó; với **extended persistence context**, entity có thể managed qua nhiều transaction. Đây là lý do không nên giữ Session quá lâu trong REST/service stateless:

- Dữ liệu trong managed entity có thể bị cũ so với transaction khác.
- Entity/collection/snapshot tích lũy trong bộ nhớ.
- Ranh giới thay đổi và khả năng rollback khó suy luận.

Mẫu thông thường là **một unit of work ngắn**, với transaction được service quản lý và context được framework đóng đúng scope.

## 6. Transaction trực tiếp với JPA và Hibernate

Khi không dùng Spring, ứng dụng dùng **resource-local EntityManager** có thể điều khiển transaction bằng **EntityTransaction**:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, productId);
    if (product == null) {
        throw new IllegalArgumentException("Không có sản phẩm");
    }
    product.reserve(quantity);

    PurchaseOrder order = new PurchaseOrder(customerId);
    em.persist(order);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Đoạn ví dụ giả định Product có **reserve()** và PurchaseOrder có constructor phù hợp; mục tiêu là làm rõ API giao dịch. **EntityTransaction** dành cho persistence unit resource-local; với môi trường container-managed JTA, transaction được điều phối bởi JTA manager và không tự gọi **em.getTransaction()** theo cách trên.

Với Hibernate native API:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Product product = session.get(Product.class, productId);
        product.reserve(quantity);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Đây là **Hibernate transaction API**. Trong cấu hình local JDBC điển hình, nó bắt đầu/điều phối **database transaction** chứ không tạo một “bản sao giao dịch” lưu độc lập trong Hibernate.

Trong ứng dụng Spring, phần lớn service không cần mở Session thủ công; Spring transaction manager xử lý EntityManager/connection và giới hạn scope qua **@Transactional**.

## 7. @Transactional trong Spring: một logical boundary do framework điều phối

Ví dụ:

~~~java
@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Không có sản phẩm"));
        product.changePrice(newPrice);
        // Dirty checking phát sinh UPDATE khi flush/commit.
    }
}
~~~

Khi method được gọi **qua Spring proxy** và transaction manager được cấu hình đúng, interceptor:

1. Xác định transaction hiện tại hoặc mở transaction mới theo propagation.
2. Gắn resource như EntityManager/connection vào scope transaction.
3. Gọi business method.
4. Commit khi method thành công, hoặc đánh dấu rollback/rollback khi exception theo rollback rules.
5. Dọn resource/binding theo lifecycle.

Annotation không có nghĩa:

- Framework sẽ retry mọi deadlock tự động.
- Code bên ngoài transaction (email, HTTP) cũng được rollback.
- Mọi method trong class đều có transaction độc lập.
- Mọi lỗi đều rollback theo cùng chính sách.
- Kết quả entity tự động được đồng bộ khi có transaction khác commit.

### 7.1. Spring transaction boundary và persistence context

Trong ứng dụng Spring Boot dùng JpaTransactionManager với một datasource, **@Transactional** thường gắn EntityManager vào thread đang xử lý transaction. Repository dùng cùng transaction sẽ tham gia unit of work đó.

~~~text
HTTP Controller
      |
      v
Service @Transactional    <-- logical transaction boundary
      |
      +--> CustomerRepository.findById()
      +--> ProductRepository.lockById()
      +--> OrderRepository.save()
      +--> OutboxRepository.save()
      |
      v
Spring JpaTransactionManager
      |
Hibernate EntityManager / Session
      |
JDBC connection -> DB transaction -> COMMIT / ROLLBACK
~~~

Nếu tất cả repository sử dụng **cùng transaction manager, datasource và resource**, các thao tác thuộc một database transaction. Nếu một repository dùng datasource khác, không được mặc định chúng tự tham gia cùng một atomic commit. JTA/XA có thể điều phối nhiều resource trong một số hệ thống, nhưng tăng độ phức tạp và không biến HTTP API thông thường thành resource XA.

### 7.2. Lỗi self-invocation

Code dưới đây dễ làm developer tưởng có hai transaction:

~~~java
@Service
public class OrderJob {
    public void run() {
        processBatch(); // Gọi trực tiếp method cùng object.
    }

    @Transactional
    public void processBatch() {
        // Logic cập nhật database.
    }
}
~~~

Với **Spring proxy-based transaction** thông thường, lời gọi **this.processBatch()** không đi qua proxy nên annotation trên processBatch có thể không được áp dụng. Hãy tách method transactional sang một bean khác và gọi qua bean đó, hoặc dùng TransactionTemplate trong nơi cần ranh giới được điều khiển rõ.

### 7.3. Không truyền Session giữa các thread

EntityManager/Session **không thread-safe**. Một method **@Async** chạy ở thread khác không tự thừa hưởng transaction-bound EntityManager của thread cha theo cơ chế thread-local thông thường. Nếu muốn worker ghi DB, mở transaction mới trong worker và truyền các ID/DTO cần thiết, không truyền managed entity graph với kỳ vọng nó vẫn thuộc cùng context.

## 8. Một ví dụ đồng bộ: tạo đơn và giữ tồn kho trong một DB transaction

Mô hình cụ thể sau cố ý giới hạn **giao dịch Hibernate/DB** ở bước tạo đơn chờ thanh toán. Không gọi cổng thanh toán bên trong bước này.

### 8.1. Schema PostgreSQL

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    price NUMERIC(19,2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount NUMERIC(19,2) NOT NULL CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(19,2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_item_product UNIQUE (order_id, product_id)
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events(occurred_at, id) WHERE published_at IS NULL;
~~~

Trong production, dùng migration như Flyway/Liquibase để tạo schema; Hibernate mapping không thay thế migration có kiểm soát. Ví dụ này không triển khai quy tắc thanh toán, expiry và chi tiết khách hàng để giữ trọng tâm ở ranh giới transaction.

### 8.2. Product và khóa optimistic

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Version
    private long version;

    protected Product() {}

    public void reserve(int quantity) {
        if (quantity <= 0 || quantity > stockQuantity) {
            throw new IllegalStateException("Không đủ tồn kho");
        }
        stockQuantity -= quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        stockQuantity += quantity;
    }

    public Long getId() { return id; }
    public BigDecimal getPrice() { return price; }
}
~~~

Trong ví dụ, **reserve()** giảm stockQuantity như một hình thức giữ hàng đơn giản. Hệ thống thật có thể tách **availableStock**, **reservedStock** và **physicalStock** cùng bản ghi reservation có expiry, để không đồng nhất “giữ” với “bán”.

### 8.3. Đơn hàng là aggregate được quản lý

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public enum OrderStatus {
    PENDING_PAYMENT, PAID, CANCELLED
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, unique = true)
    private String requestId;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private OrderStatus status = OrderStatus.PENDING_PAYMENT;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(String requestId, Long customerId, Instant createdAt) {
        if (requestId == null || requestId.isBlank() || customerId == null) {
            throw new IllegalArgumentException("Yêu cầu không hợp lệ");
        }
        this.requestId = requestId;
        this.customerId = customerId;
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public void addItem(Product product, int quantity) {
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new IllegalStateException("Không thể sửa đơn đã xử lý");
        }
        Objects.requireNonNull(product);
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        BigDecimal price = product.getPrice();
        items.add(new OrderItem(this, product, quantity, price));
        totalAmount = totalAmount.add(
            price.multiply(BigDecimal.valueOf(quantity)));
    }

    public void markPaid() {
        if (status == OrderStatus.PAID) return;
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new IllegalStateException("Không thể thanh toán đơn đã hủy");
        }
        status = OrderStatus.PAID;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED) return;
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new IllegalStateException("Phải xử lý hoàn tiền riêng");
        }
        status = OrderStatus.CANCELLED;
    }

    public Long getId() { return id; }
    public String getRequestId() { return requestId; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public List<OrderItem> getItems() {
        return java.util.Collections.unmodifiableList(items);
    }
}
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_items",
       uniqueConstraints = @UniqueConstraint(
           columnNames = {"order_id", "product_id"}))
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

    @Column(name = "unit_price", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {}

    OrderItem(PurchaseOrder order, Product product,
              int quantity, BigDecimal unitPrice) {
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
~~~

Trong project Java thật, đặt mỗi top-level public type ở file riêng. Đoạn code gộp nhiều class để giải thích, không phải một file Java đơn lẻ có thể biên dịch nguyên xi. **OrderItem** là entity liên kết có giá chốt; **Product** độc lập nên không cascade remove tới Product.

### 8.4. Outbox event được ghi trong cùng transaction

~~~java
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_events")
public class OutboxEvent {
    @Id
    private UUID id;

    @Column(name = "aggregate_type", nullable = false, length = 80)
    private String aggregateType;

    @Column(name = "aggregate_id", nullable = false)
    private Long aggregateId;

    @Column(name = "event_type", nullable = false, length = 100)
    private String eventType;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected OutboxEvent() {}

    public OutboxEvent(String aggregateType, Long aggregateId,
                       String eventType, Instant occurredAt) {
        this.id = UUID.randomUUID();
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.occurredAt = occurredAt;
    }
}
~~~

Ví dụ tối giản lưu loại event và aggregateId; thực tế có thể cần **payload JSONB, schema version, correlationId, tenantId** và metadata để consumer xử lý mà không phải query lại dữ liệu đã thay đổi.

### 8.5. Repository và transaction service

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> lockById(@Param("id") Long id);
}

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
    Optional<PurchaseOrder> findByRequestId(String requestId);
}

public interface OutboxRepository extends JpaRepository<OutboxEvent, UUID> {}
~~~

Đây là ba interface riêng trong package repository, cần import các kiểu entity, **JpaRepository**, **Optional**, **UUID**, **@Lock**, **LockModeType**, **@Query** và **@Param**. Lock PESSIMISTIC_WRITE dùng khi reserve để tránh hai giao dịch cùng trừ từ số lượng tồn kho cũ.

~~~java
public record OrderLineRequest(Long productId, int quantity) {}
public record PlaceOrderRequest(
    String requestId, Long customerId, List<OrderLineRequest> lines
) {}
~~~

~~~java
@Service
public class PlaceOrderService {
    private final ProductRepository products;
    private final PurchaseOrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderService(ProductRepository products,
                             PurchaseOrderRepository orders,
                             OutboxRepository outbox) {
        this.products = products;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Long placeOrder(PlaceOrderRequest request) {
        if (request == null || request.requestId() == null
                || request.requestId().isBlank()
                || request.customerId() == null
                || request.lines() == null || request.lines().isEmpty()) {
            throw new IllegalArgumentException("Yêu cầu đặt hàng không hợp lệ");
        }

        var existing = orders.findByRequestId(request.requestId());
        if (existing.isPresent()) {
            return existing.get().getId();
        }

        var sorted = request.lines().stream()
            .sorted(java.util.Comparator.comparing(OrderLineRequest::productId))
            .toList();

        java.util.Set<Long> seen = new java.util.HashSet<>();
        PurchaseOrder order = new PurchaseOrder(
            request.requestId(), request.customerId(), Instant.now());

        for (OrderLineRequest line : sorted) {
            if (line == null || line.productId() == null
                    || line.quantity() <= 0
                    || !seen.add(line.productId())) {
                throw new IllegalArgumentException("Dòng hàng trùng hoặc sai");
            }

            Product product = products.lockById(line.productId())
                .orElseThrow(() ->
                    new IllegalArgumentException("Sản phẩm không tồn tại"));
            product.reserve(line.quantity());
            order.addItem(product, line.quantity());
        }

        PurchaseOrder saved = orders.save(order);
        outbox.save(new OutboxEvent(
            "PurchaseOrder", saved.getId(), "OrderPlaced", Instant.now()));
        return saved.getId();
    }
}
~~~

Các import Java và Spring được lược bớt trong service để nhấn vào transaction boundary; khi đặt vào project, bổ sung **@Service**, **@Transactional**, entity/repository, **Instant**, **List** và các kiểu record tương ứng. Các dòng được xử lý theo **productId tăng dần** để các giao dịch cùng khóa nhiều Product theo thứ tự nhất quán, giảm nguy cơ deadlock do thứ tự lock đảo ngược.

**Lưu ý thực hành với ví dụ:** trước khi gọi **sorted()**, request cần validate mọi phần tử không null và productId không null; ở đây nên xem phép kiểm tra đầu vào như bước validation riêng của API/service để không để comparator nhận null. Trong code production, hãy đưa validation danh sách lên trước bước sort, sau đó mới khóa và xử lý dữ liệu.

Transaction gồm:

1. Kiểm tra requestId để nhận diện request lặp.
2. Khóa từng Product, kiểm tra và trừ tồn kho.
3. Tạo PurchaseOrder và OrderItem với giá chốt.
4. Lưu OutboxEvent.
5. Commit **cả stock, order, items và outbox** hoặc rollback tất cả nếu một bước lỗi.

**Không có** HTTP call tới cổng thanh toán trong method này. Sau commit, worker độc lập sẽ xử lý outbox.

### 8.6. Idempotency và cuộc đua request trùng

**findByRequestId() trước insert không đủ chống concurrency.** Hai request cùng requestId có thể đều không thấy đơn và cùng cố INSERT. **UNIQUE(request_id)** tại DB là lớp bảo vệ cuối.

Khi một transaction nhận unique constraint violation, đừng bắt exception rồi tiếp tục query qua transaction đã bị đánh dấu rollback-only. Hãy để transaction thất bại, sau đó tại **một transaction mới** đọc lại order theo requestId và trả kết quả đã tồn tại, nếu nội dung request tương thích với request ban đầu. Một requestId trùng nhưng payload khác phải được từ chối theo contract.

Mục tiêu idempotency là **nhiều lần gọi cùng yêu cầu chỉ tạo một đơn logic**, không phải “không bao giờ có exception” khi cạnh tranh.

## 9. Từ database commit tới thanh toán: outbox và business transaction nhiều bước

### 9.1. Vì sao không publish trực tiếp sau khi save?

Một cách tưởng đơn giản:

~~~java
@Transactional
public void placeOrder(...) {
    saveOrder();
    eventBroker.publish("OrderPlaced");
}
~~~

Hai lỗi có thể xuất hiện:

- Broker nhận event rồi DB transaction rollback: consumer xử lý một đơn **chưa tồn tại**.
- DB commit thành công nhưng process crash trước khi gửi event: đơn đã tồn tại nhưng **không bao giờ có event**.

**Transactional outbox** giải quyết phần nhất quán giữa **dữ liệu nghiệp vụ và ý định phát event** bằng cách ghi event như một hàng trong **cùng transaction DB**.

~~~mermaid
sequenceDiagram
    participant API as PlaceOrderService
    participant DB as PostgreSQL
    participant PUB as Outbox publisher
    participant BR as Message broker
    participant PAY as Payment worker
    API->>DB: BEGIN; update stock; insert order; insert outbox
    API->>DB: COMMIT
    DB-->>API: Đơn và outbox cùng được commit
    PUB->>DB: Đọc outbox chưa publish
    PUB->>BR: Publish OrderPlaced với event ID
    BR->>PAY: Giao event
    PAY->>PAY: Gọi payment provider với idempotency key
    PAY->>DB: Transaction mới: cập nhật trạng thái và outbox
~~~

Publisher có thể bị crash sau khi gửi event nhưng trước khi đánh dấu **published_at**. Khi chạy lại, nó có thể publish **cùng event lần nữa**. Vì vậy outbox thường cho **at-least-once delivery**; **consumer phải idempotent** theo eventId hoặc business key, không được giả định exactly-once end-to-end.

Trong môi trường nhiều publisher, cần cơ chế claim row an toàn, chẳng hạn **SELECT ... FOR UPDATE SKIP LOCKED**, trạng thái leased/processing hoặc giải pháp CDC; tránh hai worker cùng xử lý một row không có coordination. Thiết kế cụ thể còn phải xử lý retry, dead-letter và thời gian lease.

### 9.2. Sự kiện thanh toán và transaction xác nhận

Khi gateway trả kết quả, service nhận callback:

~~~java
@Transactional
public void markPaid(Long orderId, String gatewayEventId) {
    // 1. Kiểm tra gatewayEventId đã được xử lý chưa trong DB.
    // 2. Load và lock PurchaseOrder; kiểm tra trạng thái hiện tại.
    // 3. Chuyển PENDING_PAYMENT -> PAID đúng một lần.
    // 4. Ghi PaymentProcessed / OrderPaid vào outbox.
    // 5. Commit cùng transaction.
}
~~~

Đây là skeleton thuật toán, không phải implementation hoàn chỉnh. Để tránh xử lý callback lặp, cần bảng/inbox hoặc unique constraint theo **gatewayEventId** và kiểm tra transition nghiệp vụ. Không chỉ dựa trên việc callback đã vào method một lần.

Khi payment thất bại:

~~~text
Transaction B:
  - Nhận và deduplicate PaymentFailed
  - Lock đơn PENDING_PAYMENT
  - Đổi trạng thái sang CANCELLED
  - Giải phóng phần stock đã giữ (mỗi đơn tối đa một lần)
  - Ghi outbox OrderCancelled
  - Commit
~~~

Nếu gateway đã thu tiền rồi trả kết quả trễ sau khi đơn bị hủy, không tự đổi đơn thành PAID bỏ qua quy tắc. Cần workflow đối soát, hoàn tiền/compensation và quản lý trạng thái bất thường.

### 9.3. Saga là gì trong ngữ cảnh này?

**Saga** là cách phối hợp một business transaction qua nhiều local transaction, thường có **compensating actions** khi bước sau thất bại:

| Bước đã commit | Bước sau thất bại | Hành động bù |
|---|---|---|
| Giữ tồn kho và tạo đơn PENDING_PAYMENT | Thanh toán bị từ chối | Hủy đơn, giải phóng tồn kho |
| Thu tiền thành công | Không thể giao hàng | Tạo quy trình hoàn tiền, thông báo khách |
| Đã tạo shipment | Khách hủy theo quy tắc cho phép | Hủy vận đơn hoặc xử lý hoàn hàng |

**Compensation không phải rollback vật lý** của transaction DB đã commit. Nó là một hành động nghiệp vụ mới, có thể thất bại, cần retry và audit. Chuyển trạng thái phải có idempotency, version/lock, timeout và đối soát để bảo đảm workflow cuối cùng hội tụ về trạng thái hợp lệ.

## 10. Isolation: transaction đồng thời nhìn thấy gì?

Isolation level thuộc DB transaction, không phải một annotation Hibernate “giữ bản sao dữ liệu” độc lập. PostgreSQL hỗ trợ các mức có semantics cụ thể; trong thực tế **READ COMMITTED** là mặc định của PostgreSQL, còn **REPEATABLE READ** và **SERIALIZABLE** có đặc tính mạnh hơn và có thể buộc giao dịch retry.

| Mức isolation | Mục tiêu/semantics khái quát | Điểm cần lưu ý |
|---|---|---|
| READ UNCOMMITTED | Chuẩn SQL cho phép một số hiện tượng đọc chưa commit | PostgreSQL xử lý tương đương READ COMMITTED |
| READ COMMITTED | Mỗi statement thường nhìn thấy dữ liệu đã commit trước khi statement bắt đầu | Hai SELECT trong cùng transaction có thể nhìn thấy kết quả khác nhau |
| REPEATABLE READ | Giữ snapshot nhất quán hơn cho một transaction | PostgreSQL snapshot isolation vẫn cần hiểu write conflict; không ngăn mọi bất biến cross-row |
| SERIALIZABLE | Cố gắng bảo đảm kết quả tương đương thứ tự tuần tự | Có thể từ chối/abort transaction do serialization failure; cần retry toàn bộ |

### 10.1. First-level cache và database isolation là hai lớp khác

Giả sử Session A đã load Product #101 với stock=10. Session B trừ tồn kho và commit stock=8.

Trong Session A, gọi **entityManager.find(Product.class, 101L)** lần nữa có thể trả **chính managed object stock=10** mà không query DB. Kết quả đó đến từ **persistence context**, dù database ở READ COMMITTED có thể cho một SELECT mới thấy stock=8.

Nếu A gọi **refresh()**, Hibernate yêu cầu đọc lại DB, nhưng giá trị thấy được vẫn phụ thuộc snapshot/isolation hiện tại. Vì thế không suy luận rằng “đã READ COMMITTED thì entity managed luôn tự cập nhật”.

### 10.2. Lost update và optimistic locking

Thêm:

~~~java
@Version
private long version;
~~~

cho Product/Order để Hibernate kiểm tra version khi cập nhật managed entity. SQL có thể có dạng:

~~~sql
UPDATE products
SET stock_quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Khi transaction khác đã tăng version, UPDATE không còn khớp hàng và Hibernate báo optimistic locking failure. Ứng dụng phải rollback rồi **retry toàn bộ use case trong transaction mới**, hoặc trả thông báo xung đột cho người dùng.

**@Version không tự làm mới dữ liệu đọc**, và không áp dụng giống hệt cho mọi bulk JPQL/native SQL. Nếu một service dùng bulk UPDATE, cần xem lại cơ chế version/lock để không phá quy tắc cạnh tranh.

### 10.3. Pessimistic locking

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select p from Product p where p.id = :id")
Optional<Product> lockById(@Param("id") Long id);
~~~

Với DB hỗ trợ, Hibernate dùng cơ chế khóa tương ứng (ví dụ SELECT ... FOR UPDATE trong những trường hợp PostgreSQL phù hợp). Transaction khác muốn khóa/cập nhật cùng row có thể phải chờ hoặc lỗi timeout/deadlock theo cấu hình.

Khóa giúp bảo vệ thao tác reserve ở transaction ngắn, nhưng **không nên giữ lock khi gọi gateway thanh toán qua mạng**. Thời gian chờ I/O bên ngoài làm lock và connection bị giữ lâu, giảm thông lượng.

### 10.4. Atomic conditional UPDATE

Một lựa chọn khác cho tồn kho:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :qty,
    version = version + 1
WHERE id = :id
  AND stock_quantity >= :qty;
~~~

Nếu số hàng bị ảnh hưởng bằng 1, việc giữ hàng thành công; bằng 0, sản phẩm không tồn tại hoặc không đủ kho (phân biệt bằng query bổ sung khi cần). Đây là ví dụ thao tác **atomic ở DB**, không phải “đọc trong Java rồi hy vọng không có race”. Nếu dùng JPQL bulk/native SQL, nhớ rằng entity Product đã managed có thể bị cũ và phải xử lý sự không đồng bộ đó; nếu cập nhật version bằng SQL thì phải giữ đúng contract với entity-managed update.

## 11. Propagation: một business operation có thể tạo nhiều physical transaction

Spring cung cấp **@Transactional(propagation = ...)**. Propagation định nghĩa khi method được gọi trong hoặc ngoài transaction hiện có, nó tham gia hay mở một transaction khác.

| Propagation | Ý nghĩa thường gặp | Ghi nhớ |
|---|---|---|
| REQUIRED (mặc định) | Tham gia transaction hiện có; nếu không có thì mở mới | Các service method gọi nhau có thể dùng **cùng physical transaction** |
| REQUIRES_NEW | Tạm dừng transaction hiện có, mở transaction độc lập | Commit/rollback riêng; có thể cần thêm connection/resource |
| NESTED | Tạo phạm vi lồng dựa trên savepoint khi transaction manager hỗ trợ | Không đồng nghĩa mở transaction DB độc lập; JPA support tùy transaction manager |
| SUPPORTS | Có transaction thì tham gia, không có thì chạy không transaction | Không bảo đảm write atomic nếu không có transaction ngoài |
| MANDATORY | Yêu cầu transaction đã tồn tại | Báo lỗi nếu caller không có transaction |
| NOT_SUPPORTED | Chạy không transaction, tạm dừng transaction hiện có | Hữu ích cho tác vụ không nên giữ transaction, nhưng cần hiểu context/resource |
| NEVER | Không được gọi khi có transaction | Báo lỗi nếu caller có transaction |

### 11.1. REQUIRED: nhiều logical scope, một physical transaction

~~~java
@Transactional
public void placeOrder() {
    reserveStockService.reserve(); // Cũng @Transactional REQUIRED.
    orderRepository.save(order);
}
~~~

Nếu reserve() được gọi qua Spring proxy và cùng transaction manager, nó thường **tham gia transaction đang mở**. Không có commit riêng khi reserve() trả về: commit xảy ra khi outer transaction hoàn tất.

Một tình huống dễ nhầm:

~~~java
@Transactional
public void outer() {
    try {
        innerService.requiredOperation();
    } catch (RuntimeException ex) {
        // Bắt lỗi và tưởng có thể commit tiếp.
    }
    saveSomethingElse();
}
~~~

Nếu interceptor của inner REQUIRED đánh dấu physical transaction là **rollback-only**, outer method có thể chạy tiếp nhưng lúc commit nhận **UnexpectedRollbackException** thay vì commit. Bắt exception không xóa rollback-only flag. Hãy quyết định rõ logic phục hồi và ranh giới transaction, không dùng catch trống để “ép commit”.

### 11.2. REQUIRES_NEW: transaction độc lập, không phải cứu vãn mọi lỗi

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit(String action) {
    auditRepository.save(new AuditEntry(action));
}
~~~

Nếu được gọi qua bean proxy khác trong lúc transaction ngoài đang chạy, audit có thể commit độc lập kể cả khi transaction ngoài rollback.

Nhưng điều này tạo ra sự không nhất quán **có chủ đích**: audit “đã thử đặt hàng” tồn tại dù đặt hàng thất bại. Nó có thể đúng với audit attempt, nhưng **không phù hợp** nếu audit bị hiểu là “đơn hàng đã tạo thành công”.

REQUIRES_NEW có chi phí thêm: transaction khác, có thể cần connection mới trong khi transaction ngoài đang giữ connection và lock. Nếu pool quá nhỏ, nhiều thread cùng REQUIRES_NEW có thể chờ connection/đe dọa deadlock tài nguyên. Đừng lạm dụng để “ghi được log dù transaction lỗi” khi chưa rõ semantics.

### 11.3. NESTED và savepoint

Với transaction manager JDBC có hỗ trợ savepoint, **NESTED** có thể rollback một phần công việc về savepoint mà không rollback toàn bộ outer transaction. Tuy nhiên với **JpaTransactionManager**, savepoint và persistence context không tự có semantics giống nhau cho mọi entity managed; cần xem khả năng của transaction manager và database. **Không dùng NESTED như một thay thế mặc định cho REQUIRES_NEW** nếu chưa kiểm chứng trên cấu hình thật.

## 12. Rollback rules: exception nào gây rollback?

Trong cấu hình Spring proxy-based thông dụng:

- Exception kiểu **RuntimeException** và **Error** mặc định làm transaction rollback.
- **Checked exception** không mặc định làm rollback, trừ khi cấu hình rollback rules như **rollbackFor**.
- Nếu method bắt exception rồi trả về bình thường, interceptor có thể **commit**, trừ khi transaction đã được đánh dấu rollback-only.
- Một số transaction có thể bị đánh dấu rollback-only sau lỗi persistence/DB dù code đã catch.

Ví dụ cần rollback với checked exception:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void approveOrder(Long orderId) throws BusinessRuleException {
    // Thao tác entity...
    if (someRuleIsBroken()) {
        throw new BusinessRuleException("Không thể phê duyệt");
    }
}
~~~

Ví dụ này giả định **BusinessRuleException extends Exception**, và **someRuleIsBroken()** là điều kiện nghiệp vụ. Với code production, thường lựa chọn exception và rollback semantics nhất quán ngay từ service design.

### 12.1. Catch exception để log không phải là xử lý rollback

~~~java
@Transactional
public void dangerousExample() {
    repository.save(newOrder);
    try {
        validateWithRemoteService();
    } catch (Exception ex) {
        log.warn("Remote service failed", ex);
    }
    // Method kết thúc bình thường => có thể commit.
}
~~~

Ở ví dụ này, nếu nghiệp vụ yêu cầu remote validation thành công trước khi tạo đơn, cách viết là sai vì exception bị nuốt. Nhưng nếu remote validation là nhiệm vụ tùy chọn, thì transaction có thể commit — phải là quyết định nghiệp vụ rõ ràng.

Đặc biệt với **PersistenceException**, lỗi flush/constraint/connection có thể khiến transaction đã không còn hợp lệ. Thường nên rollback và mở transaction mới thay vì bắt rồi tiếp tục thao tác trên EntityManager đang lỗi.

### 12.2. Rollback DB không rollback object Java

Nếu Product trong Java đã giảm stockQuantity từ 10 xuống 8, nhưng DB transaction rollback, object Java đó **không tự quay về stockQuantity=10 bằng phép gán ngược của Hibernate**. Sau rollback, persistence context/managed state có thể không còn đáng tin để tiếp tục. Kết thúc unit of work, bỏ object cũ và đọc lại trong transaction mới khi cần.

Tương tự, biến Java, log đã ghi, bộ đếm metric, event nội bộ hay HTTP request không tự quay về trạng thái trước khi rollback.

## 13. Transaction timeout và độ dài ranh giới nghiệp vụ

Giao dịch DB dài có chi phí:

- Giữ lock lâu, gây chờ ở các giao dịch khác.
- Giữ snapshot MVCC lâu, ảnh hưởng vacuum/cleanup trong PostgreSQL.
- Giữ connection hoặc resource transaction trong thời gian dài tùy cấu hình.
- Làm transaction log/undo hoặc WAL tăng trong tác vụ ghi lớn.
- Tăng công việc cần rollback khi lỗi muộn.

Vì vậy phương thức sau có thể gây rủi ro:

~~~java
@Transactional
public void processAllOrders() {
    for (PurchaseOrder order : repository.findAll()) {
        callShippingApi(order);  // Remote I/O, không tham gia DB transaction.
        updateOrder(order);
    }
}
~~~

Thay bằng:

1. Chia việc thành batch có giới hạn.
2. Mỗi batch một transaction DB ngắn.
3. Ghi event/outbox cho công việc bên ngoài.
4. Để worker xử lý API ngoài transaction DB dài.
5. Lưu checkpoint và dùng idempotency để retry.

~~~java
@Transactional(timeout = 10)
public void processOneBatch(List<Long> orderIds) {
    // Chỉ đọc/sửa dữ liệu DB trong batch nhỏ.
}
~~~

**timeout** là cấu hình giới hạn theo transaction manager/DB/driver và không bảo đảm mọi blocking call Java bên ngoài sẽ bị dừng đúng khi hết hạn. Đừng dùng timeout thay cho thiết kế ranh giới ngắn.

## 14. Read-only transaction và consistency

~~~java
@Transactional(readOnly = true)
public OrderView findOrder(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();
    return toView(order);
}
~~~

**readOnly = true** thường là hint giúp Spring/Hibernate điều chỉnh flush/transaction behavior, có thể giảm một số overhead khi chỉ đọc. Nó **không phải ràng buộc bảo mật hoặc bảo đảm tuyệt đối không ghi** trong mọi database và không thay thế user permission/DB grants.

Một use case đọc có thể cần nhất quán nhiều câu query. Ví dụ:

~~~text
SELECT order
SELECT items
SELECT payments
~~~

Ở READ COMMITTED, các query riêng có thể thấy commit khác giữa chừng. Nếu ứng dụng cần snapshot nhất quán của một báo cáo, có thể xem xét REPEATABLE READ/read model/chạy query gộp; song transaction dài giữ snapshot lâu cũng có chi phí. **Không tăng isolation chỉ vì muốn dữ liệu “chắc chắn chính xác hơn” mà không định nghĩa anomaly cần ngăn.**

## 15. Bulk JPQL, native SQL và đồng bộ persistence context

Một bulk JPQL update:

~~~java
int updated = em.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
    .setParameter("status", OrderStatus.CANCELLED)
    .setParameter("id", orderId)
    .executeUpdate();
~~~

có thể trực tiếp UPDATE database mà **không đồng bộ state entity đã managed** trong persistence context và không đi qua vòng đời dirty checking/@Version thông thường của từng entity. Nếu một Order đã load trước bulk update, **order.getStatus()** có thể còn giá trị cũ.

Các chiến lược:

- Với một entity, thường ưu tiên **load managed + business method**.
- Với bulk job lớn, chạy DML trong transaction/context riêng, kiểm soát version nếu cần.
- **flush** pending changes trước bulk DML khi cần, rồi **clear** hoặc **refresh** entity phù hợp.
- Không gọi clear khi còn các thay đổi chưa flush mà ứng dụng cần giữ.

Spring Data JPA có:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
int updateStatus(@Param("id") Long id,
                 @Param("status") OrderStatus status);
~~~

Các cờ này ảnh hưởng toàn persistence context trong transaction, không chỉ riêng entity của query. Xác định rõ các entity khác có thể đang được quản lý trước khi dùng.

## 16. Open Session in View và nơi transaction thực sự kết thúc

Một ứng dụng web có thể bật **Open Session/EntityManager in View (OSIV)**, giữ persistence context mở tới giai đoạn controller/serialization, ngay cả sau khi service transaction kết thúc.

Điều đó **không** có nghĩa có một DB transaction duy nhất kéo dài đến cuối HTTP response. Persistence context và DB transaction có vòng đời khác nhau.

Các rủi ro:

- JSON serializer truy cập LAZY association ngoài service và tạo query bất ngờ.
- N+1 trên danh sách entity.
- Dữ liệu đã load trước đó vẫn managed trong context mà không tự refresh.
- Khó giải thích ranh giới truy cập DB của một request.

Một chính sách phổ biến:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Rồi service tạo DTO trong transaction:

~~~java
@Transactional(readOnly = true)
public OrderDetailView getOrder(Long id) {
    PurchaseOrder order = repository.findDetailById(id)
        .orElseThrow(() -> new IllegalArgumentException("Không có đơn"));
    return mapToView(order);
}
~~~

Code ví dụ giả định các DTO/method đã có trong project. Tắt OSIV đòi hỏi fetch plan/DTO hợp lý; không sửa **LazyInitializationException** bằng cách bật EAGER trên mọi quan hệ.

## 17. Đơn vị giao dịch và giới hạn số lượng entity

Một công việc 200.000 đơn hàng không nên dùng một persistence context/transaction chỉ vì đó là “một tác vụ nghiệp vụ” trên màn hình quản trị.

~~~text
Business task: đối soát toàn bộ tháng 10
  ├─ DB txn #1: đối soát đơn 1..200
  ├─ DB txn #2: đối soát đơn 201..400
  ├─ ...
  └─ DB txn #1000: đối soát batch cuối
~~~

Mỗi batch nên có:

- Điều kiện chọn ổn định (ví dụ keyset theo ID hoặc checkpoint).
- Transaction riêng; entity context kết thúc sau batch.
- Kết quả ghi nhận bền vững để retry không xử lý sai.
- Giới hạn độ lớn graph được load.
- Error handling tách biệt theo batch, không nuốt lỗi rồi tiếp tục transaction đã rollback-only.

Trong một transaction xử lý nhiều entity, **flush + clear** định kỳ có thể giảm số object managed, nhưng **không làm transaction DB ngắn hơn**. Khi cần toàn bộ việc xảy ra nguyên tử và dữ liệu rất lớn, phải xem lại thiết kế nghiệp vụ/locking hoặc dùng giải pháp chuyên biệt, không đơn giản đặt transaction kéo dài hàng giờ.

## 18. Quan sát ranh giới transaction bằng log và SQL

### 18.1. Cấu hình logging khi học

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
    org.springframework.transaction: TRACE
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Trong môi trường học tập, transaction logs giúp thấy khi nào Spring bắt đầu/tham gia/hoàn tất một transaction; SQL logs giúp thấy DML thực thi ở flush. **TRACE bind parameters có thể chứa thông tin nhạy cảm**, chỉ bật ở môi trường phù hợp và không dùng mặc định production.

Log SQL **không phải** lúc nào cũng in SQL BEGIN/COMMIT theo cùng định dạng; JDBC driver, connection pool và transaction manager có các nguồn log riêng. Vì thế để chứng minh commit, hãy dựa vào transaction lifecycle, dữ liệu quan sát từ transaction khác và DB instrumentation, không suy luận chỉ từ sự xuất hiện của UPDATE.

### 18.2. Hibernate Statistics

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sf = emf.unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

long flushCount = stats.getFlushCount();
long entityInsertCount = stats.getEntityInsertCount();
long entityUpdateCount = stats.getEntityUpdateCount();
long preparedCount = stats.getPrepareStatementCount();
~~~

Ví dụ giả định biến **emf** là EntityManagerFactory đã được inject. Các counter là dữ liệu tích lũy của toàn SessionFactory; không tự đại diện một request nếu có nhiều transaction đồng thời. Đặc biệt **flushCount không bằng commitCount** và **preparedCount không đồng nghĩa số dòng DB đã commit**.

### 18.3. Đo thứ thực sự quan trọng

Đối với service tạo đơn:

- Độ dài transaction và thời gian chờ lock.
- Số câu SELECT/UPDATE/INSERT và số hàng ảnh hưởng.
- Tỷ lệ lỗi optimistic locking, deadlock, lock timeout.
- Tỷ lệ retry của requestId và số outbox event được publish lặp.
- Thời gian từ PENDING_PAYMENT đến PAID/CANCELLED.
- Số đơn bị giữ hàng quá hạn và số trường hợp cần đối soát thanh toán.

Đo **business outcomes** bên cạnh DB metrics. Một hệ thống có SQL nhanh nhưng thanh toán thành công mà đơn bị mất là hệ thống sai.

## 19. Kiểm thử các tình huống transaction quan trọng

Integration test nên sử dụng cùng loại database triển khai, ví dụ PostgreSQL qua Testcontainers, khi kiểm tra row lock, isolation, unique constraint và deadlock. H2 tiện cho test nhỏ nhưng không bảo đảm hành vi concurrency giống PostgreSQL.

### 19.1. Các phép thử nên có

| Kịch bản | Kỳ vọng |
|---|---|
| Tạo đơn và outbox trong một transaction | Cả order, items, stock và outbox cùng được commit |
| Tồn kho không đủ sau khi đã trừ một sản phẩm khác | Rollback toàn bộ: không mất stock, không có order/outbox |
| Flush rồi throw RuntimeException | DB rollback dù SQL đã gửi trước đó |
| Method @Transactional ném checked exception | Kiểm tra rollback rules; thêm rollbackFor nếu nghiệp vụ yêu cầu |
| Hai request trùng requestId | Một order logic nhờ unique constraint/idempotency |
| Hai request cùng giữ sản phẩm cuối | Không bán vượt tồn kho; lock hoặc version báo xung đột thích hợp |
| Thanh toán thành công nhưng email lỗi | Order vẫn PAID; email có thể retry theo workflow |
| Outbox publish rồi process crash | Event có thể được publish lại; consumer xử lý idempotent |
| Bulk update trong context có entity loaded | Entity managed có thể stale; cần clear/refresh |
| REQUIRES_NEW audit commit, outer rollback | Audit có thể còn tồn tại; đúng nếu ghi “attempt” |
| Self-invocation @Transactional | Quan sát transaction thực tế và sửa bằng bean/proxy boundary |
| Hai transaction đồng thời cập nhật entity @Version | Một cập nhật bị conflict nếu dựa trên version cũ |

### 19.2. Skeleton test: rollback sau flush

~~~java
@Service
public class FailingOrderService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void createThenFail(PurchaseOrder order) {
        em.persist(order);
        em.flush();
        throw new IllegalStateException("Thử rollback");
    }
}
~~~

Một integration test gọi method này **qua Spring bean proxy**, bắt exception, sau đó query ở **transaction/persistence context mới** để khẳng định order không tồn tại. Đừng dùng test method được bao bởi transaction rollback tự động rồi tưởng đã chứng minh việc service commit/rollback riêng, vì transaction test có thể bao ngoài hoặc che kết quả.

### 19.3. Skeleton test: hai transaction riêng

~~~java
// Transaction 1:
Product firstRead = emA.find(Product.class, productId);

// Transaction 2 độc lập:
Product modified = emB.find(Product.class, productId);
modified.changePrice(new BigDecimal("200.00"));
// emB commit

// Quay lại context A:
Product sameManaged = emA.find(Product.class, productId);
// Có thể vẫn là firstRead với giá cũ.
~~~

Để code chạy, phải khởi tạo hai EntityManager và transaction đúng cách, thiết kế Product.changePrice(), commit B rồi quản lý A theo isolation phù hợp. Mục tiêu là làm rõ rằng **database commit** và **persistence context refresh** là hai sự kiện khác nhau.

### 19.4. Kiểm thử concurrency không chỉ bằng hai thread chạy nhanh

Đối với overselling hoặc unique requestId, kiểm thử nên dùng synchronization barrier để hai transaction **thật sự chạm vùng xung đột**, chứ không chỉ gửi hai HTTP requests ngẫu nhiên rồi kết luận “chưa từng lỗi”. Xác nhận kết quả cuối tại DB: stock >= 0, một order theo requestId, một lần chuyển trạng thái, outbox đúng số event logic.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân gốc thường gặp | Cách sửa |
|---|---|---|
| Lệnh save chạy nhưng DB chưa thấy dữ liệu | Transaction chưa commit, flush/commit khác nhau hoặc isolation | Kiểm tra ranh giới transaction và trạng thái commit |
| Đã flush nhưng vẫn không có record sau lỗi | Transaction rollback sau flush | Đây là ACID đúng; không coi flush là commit |
| HTTP charge thành công nhưng đơn rollback | Side effect ngoài DB nằm giữa local transaction | Outbox/saga, idempotency và compensation |
| @Transactional không có hiệu lực | Self-invocation, method không qua proxy, transaction manager sai | Tách bean và gọi qua proxy; kiểm tra config |
| Catch exception nhưng dữ liệu vẫn commit | Interceptor thấy method trả bình thường | Định nghĩa rollback rule, rethrow hoặc xử lý transaction có chủ đích |
| Catch lỗi DB xong vẫn thao tác, commit thất bại | Transaction đã rollback-only hoặc connection lỗi | Rollback, mở transaction mới |
| Outer bắt exception của inner REQUIRED nhưng nhận UnexpectedRollbackException | Inner đã đánh dấu rollback-only | Thiết kế lại propagation/error handling |
| REQUIRES_NEW làm pool thiếu connection | Outer và inner giữ tài nguyên/connection đồng thời | Xem lại propagation và cỡ pool |
| Hai request cùng trừ tồn kho dẫn tới âm kho | Race condition, thiếu lock/atomic UPDATE | Pessimistic lock, @Version, conditional UPDATE và CHECK DB |
| Đơn được tạo hai lần khi HTTP retry | Không có idempotency key/unique constraint | UNIQUE request_id và xử lý retry transaction mới |
| Entity có giá cũ sau khi DB commit | First-level cache của persistence context | Context/transaction mới hoặc refresh |
| Bulk UPDATE thành công nhưng object cũ | Bulk DML bypass entity state | Flush/clear hoặc refresh thích hợp |
| Query chỉ đọc nhưng tạo lock hoặc giữ snapshot lâu | Transaction dài/isolation cao | Rút ngắn scope, chọn isolation theo anomaly cần ngăn |
| Job lớn hết RAM và commit rất chậm | Một persistence context/transaction giữ quá nhiều entity | Batch transaction + pagination/keyset |
| Event broker có bản tin trùng | Outbox at-least-once và retry publisher | Deduplicate theo eventId, consumer idempotent |
| Gửi email trong AFTER_COMMIT nhưng bị mất khi crash | Callback in-process không durable | Outbox + worker retry |
| @Version không chặn bulk UPDATE ghi đè | Query không đi qua dirty checking/version chuẩn | Bổ sung điều kiện version hoặc thiết kế lại |

## 21. Bài thực hành tổng hợp

### Bài 1 — Phân rã transaction

Vẽ sơ đồ business transaction “đặt hàng → thanh toán → giao hàng”. Chia ít nhất ba database transaction:

1. Tạo PENDING_PAYMENT, giữ tồn kho, ghi outbox.
2. Xử lý callback thanh toán, đổi trạng thái, ghi outbox.
3. Ghi shipment/fulfillment sau khi nhận event phù hợp.

Cho biết **bước nào có thể rollback vật lý** và **bước nào phải compensation**.

### Bài 2 — Chứng minh flush khác commit

Viết method @Transactional persist một Order rồi gọi flush. Sau flush, ném RuntimeException. Trong test sử dụng transaction mới, xác nhận DB không có Order và stock không đổi. Quan sát SQL log vẫn có thể có INSERT/UPDATE trước rollback.

### Bài 3 — Tạo race condition tồn kho

Tạo Product còn 1 chiếc, cho hai transaction độc lập cùng đặt mua. Trước tiên thử phương án đọc rồi cập nhật không lock, quan sát rủi ro; sau đó sửa bằng **PESSIMISTIC_WRITE** hoặc **atomic conditional UPDATE**. Kiểm tra stock không âm và chỉ một request giữ thành công.

### Bài 4 — Idempotency khi retry HTTP

Gửi hai lần cùng requestId (lần lượt và đồng thời). Kiểm tra unique constraint tại DB, cách ứng dụng đọc lại kết quả ở transaction mới sau conflict, và việc payload thay đổi dưới cùng requestId có bị từ chối hay không.

### Bài 5 — Exception và propagation

Tạo outer REQUIRED gọi inner REQUIRED ném RuntimeException; thử bắt exception ở outer và xem **rollback-only/UnexpectedRollbackException**. Sau đó thử chuyển inner sang REQUIRES_NEW trong một use case audit có ý nghĩa rõ, quan sát sự độc lập của commit. Không áp dụng propagation mới chỉ để làm exception biến mất.

### Bài 6 — Outbox và crash recovery

Giả lập publisher gửi xong event nhưng crash trước khi đánh dấu published. Sau restart, nó gửi lại event. Viết consumer deduplicate theo eventId để không thu tiền hoặc xác nhận đơn hai lần.

### Bài 7 — Dữ liệu cũ và bulk DML

Mở persistence context, nạp Order, thực thi bulk JPQL UPDATE, quan sát object cũ rồi clear/refresh. Lặp phép thử với hai transaction và isolation phù hợp; phân biệt stale do cache cấp một với snapshot DB.

### Bài 8 — Thiết kế lại tác vụ lớn

Một job cần cập nhật 100.000 đơn và gọi dịch vụ bên ngoài. Viết thiết kế per-batch transaction với checkpoint, outbox, retry và timeouts. Giải thích vì sao không giữ một @Transactional bao cả job và vì sao flush+clear không tự giải quyết lock/transaction age.

## 22. Checklist trước khi đưa một use case dùng Hibernate vào production

- **Business outcome:** hệ thống định nghĩa thành công/thất bại bằng trạng thái gì?
- **DB atomicity:** những UPDATE/INSERT/DELETE nào bắt buộc commit hoặc rollback cùng nhau?
- **Transaction manager:** các repository có thật sự dùng cùng datasource và transaction manager không?
- **Scope:** transaction có đủ ngắn, tránh external I/O và thao tác chờ lâu không?
- **Validation/constraints:** có FK, UNIQUE, NOT NULL, CHECK và business validation phù hợp không?
- **Concurrency:** có version, row lock hoặc SQL atomic cho tranh chấp quan trọng không?
- **Exception policy:** lỗi nào rollback, lỗi nào cần retry, có catch nào nuốt exception không?
- **Idempotency:** request lặp, callback lặp và event lặp có tạo double charge/overselling không?
- **External systems:** đã có outbox/compensation khi cần, thay vì giả định DB rollback cả HTTP chưa?
- **Persistence context:** có ai giữ Session lâu, merge detached graph tùy tiện hoặc kỳ vọng entity tự refresh không?
- **Monitoring:** có transaction duration, lock wait, deadlock/serialization failure, outbox lag và business state metrics không?
- **Integration tests:** các ca rollback, commit, cạnh tranh và crash đã chạy trên database/dialect đại diện chưa?

## 23. Kết luận

Một mô hình tư duy có thể mang sang mọi ứng dụng Hibernate:

**Giao dịch nghiệp vụ** nói về **việc người dùng cần hoàn thành**. Nó có thể kéo dài qua nhiều bước, service và lần commit, được quản lý bằng trạng thái, idempotency, retry và compensation.

**Giao dịch Hibernate/JPA** nói về **cách ứng dụng quản lý entity và SQL trong một unit of work**. Session/EntityManager giữ persistence context, Hibernate thực hiện dirty checking và flush, còn transaction API/framework điều phối commit hoặc rollback.

**Giao dịch cơ sở dữ liệu** nói về **ranh giới ACID thực sự của các thao tác dữ liệu**. Nó cung cấp commit/rollback/isolation/locking cho những statement thuộc transaction, nhưng không tự quay ngược tác động bên ngoài như thu tiền, gửi email hay publish message.

Với nghiệp vụ nhỏ, một service method **@Transactional** có thể bao trọn cả mục tiêu nghiệp vụ lẫn database transaction. Với nghiệp vụ lớn, nên **chia thành những transaction DB ngắn và đáng tin cậy**, lưu state bền vững giữa các bước, phối hợp qua outbox và xử lý bù khi cần.

**Câu hỏi quan trọng nhất không phải “đã có @Transactional chưa?” mà là “những thay đổi nào phải nguyên tử với nhau, hệ thống ngoài DB được phối hợp ra sao, và khi một bước thất bại thì trạng thái nghiệp vụ hợp lệ tiếp theo là gì?”** Khi trả lời rõ, bạn sẽ dùng Hibernate transaction đúng chỗ, bảo vệ dữ liệu dưới cạnh tranh và tránh nhầm lẫn giữa việc flush object Java với việc toàn bộ quy trình kinh doanh đã hoàn thành.
