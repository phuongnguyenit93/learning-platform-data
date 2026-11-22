# Cấu hình gợi ý thời gian chờ khóa và kiểm tra hỗ trợ

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Khóa bi quan

Trong hệ thống đặt hàng, hai giao dịch có thể cùng muốn sửa một sản phẩm, ví tiền hoặc bản ghi công việc. Giao dịch thứ nhất đã khóa hàng dữ liệu; giao dịch thứ hai phải quyết định **chờ khóa được giải phóng**, **thất bại ngay**, hay **chờ trong một khoảng thời gian giới hạn**. Nếu chờ quá lâu, request HTTP có thể hết thời gian, hàng đợi kết nối cạn dần, hoặc một job định kỳ bị treo lâu hơn dự kiến.

Jakarta Persistence (JPA) cung cấp **gợi ý thời gian chờ khóa bi quan** thông qua tên hint chuẩn:

~~~java
"jakarta.persistence.lock.timeout"
~~~

Giá trị thường được biểu diễn bằng **số mili giây**. Ví dụ, đặt 750 nghĩa là **yêu cầu** việc chờ lấy khóa được giới hạn khoảng 750 ms, khi JPA provider, JDBC driver và hệ quản trị cơ sở dữ liệu có thể thực thi yêu cầu đó:

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.lock.timeout", 750
);

Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE,
    properties
);
~~~

Tuy nhiên, từ **gợi ý (hint)** là điểm mấu chốt. **JPA không bảo đảm mọi provider/driver/database hỗ trợ hoặc tuân thủ thời gian chờ chính xác**. Một hint không được nhận diện hoặc không được hỗ trợ có thể bị bỏ qua; database cũng có thể giới hạn cách quy đổi từ milliseconds sang đơn vị timeout mà nó hỗ trợ. Không được coi setHint thành công là bằng chứng thời gian chờ đã có hiệu lực.

Bài này hướng dẫn cả hai phần của đề bài:

1. **Cấu hình:** đặt lock timeout đúng API, đúng đơn vị, đúng transaction và đúng loại khóa.
2. **Kiểm tra hỗ trợ:** quan sát SQL/driver/database, tạo hai transaction cạnh tranh thật, đo kết quả và phân loại exception.

Nội dung dùng **Jakarta Persistence**; các dự án cũ còn ở namespace **javax.persistence** cần dùng tên hint tương ứng với API/provider của chúng. SQL trong các ví dụ có ghi rõ hệ quản trị; cú pháp điều khiển khóa không hoàn toàn portable giữa PostgreSQL, SQL Server, Oracle, MySQL và các database khác.

## 1. Bối cảnh: một hàng dữ liệu bị khóa

Giả sử có bảng sản phẩm với số lượng tồn kho. Khi quyết định trừ tồn kho, service cần tránh để hai giao dịch cùng đọc và ghi dựa trên trạng thái không phù hợp.

~~~text
Transaction A                        Transaction B
─────────────                        ─────────────
BEGIN                                BEGIN
find(Product#42, PESSIMISTIC_WRITE)
  → lấy khóa trên row #42
                                     find(Product#42, PESSIMISTIC_WRITE)
                                       → phải chờ khóa của A
Đọc tồn kho
Trừ tồn kho
Flush / Commit
  → giải phóng khóa
                                     → lấy được khóa nếu chưa hết timeout
                                     Đọc trạng thái mới và quyết định
                                     Commit / Rollback
~~~

Nếu A giữ transaction trong 8 giây nhưng B chỉ được phép chờ 500 ms theo yêu cầu nghiệp vụ, B nên nhận được một tín hiệu timeout **khi khả năng database/provider hỗ trợ điều đó**. Nếu không có thời gian chờ được kiểm soát, B có thể tiếp tục đợi theo chính sách mặc định của database.

### 1.1. Vì sao khóa bi quan được sử dụng?

**Pessimistic locking** đặt yêu cầu khóa ở database khi giao dịch đọc/sử dụng dữ liệu. Nó phù hợp với các trường hợp:
- Nhiều writers thường xuyên cạnh tranh trên cùng một row;
- Business invariant cần được kiểm tra trong một transaction ngắn;
- Không muốn mỗi writer phải phát hiện xung đột muộn rồi chạy lại toàn bộ nghiệp vụ;
- Cần đảm bảo một worker xử lý một công việc tại một thời điểm theo chiến lược có khóa;
- Việc chờ khóa ngắn có thể chấp nhận được hơn việc retry lặp lại.

Không mặc định khóa bi quan tốt hơn khóa lạc quan cho mọi bài toán. Nếu người dùng mở biểu mẫu trong nhiều phút, không nên giữ khóa DB trong suốt thời gian họ nhập liệu. Với những cập nhật theo điều kiện đơn giản, một atomic UPDATE có WHERE cũng có thể phù hợp hơn.

### 1.2. Khóa giữ đến khi nào?

Trong các giao dịch SQL thông dụng, khóa được giữ đến **commit/rollback**, không phải chỉ đến lúc dòng em.find trả về. Lock timeout giới hạn **thời gian cố gắng lấy khóa**, chứ **không giới hạn thời gian giao dịch giữ khóa sau khi lấy được**.

~~~text
Chờ lấy khóa    = thời gian trước khi B được cấp khóa
Giữ khóa        = thời gian B giữ khóa cho đến commit/rollback
Thời gian query = thời gian thực thi truy vấn, có thể gồm nhiều yếu tố
Thời gian HTTP  = toàn bộ xử lý request ở tầng ứng dụng
~~~

Một giao dịch B có thể lấy khóa sau 200 ms, rồi giữ nó 30 giây do code gọi dịch vụ bên ngoài. Lock timeout 500 ms **không tự hủy transaction B sau 500 ms**.

### 1.3. Đúng transaction trước khi xét timeout

JPA pessimistic lock thường yêu cầu **transaction đang hoạt động**. Nếu dùng khóa bi quan ngoài transaction phù hợp, JPA có thể ném **TransactionRequiredException** trước khi xét timeout.

Ví dụ trong Spring:

~~~java
@Transactional
public void reserveProduct(Long id, int quantity) {
    // Lời gọi PESSIMISTIC_WRITE phải diễn ra trong
    // transaction được Spring thực sự quản lý.
}
~~~

Không nên cố dùng em.find(..., PESSIMISTIC_WRITE, ...) trong một service không có transaction rồi quy mọi exception thành “khóa đang bị giữ”.

## 2. Entity Product dùng xuyên suốt bài

Các ví dụ sử dụng một Product tối giản:

~~~java
package com.example.inventory;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    protected Product() {}

    public Product(String sku, int initialStock) {
        this.sku = Objects.requireNonNull(sku);
        if (initialStock < 0) {
            throw new IllegalArgumentException(
                "Tồn kho không được âm"
            );
        }
        this.stockQuantity = initialStock;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public int getStockQuantity() { return stockQuantity; }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Số lượng đặt phải dương"
            );
        }
        if (stockQuantity < quantity) {
            throw new IllegalStateException(
                "Không đủ tồn kho"
            );
        }
        stockQuantity -= quantity;
    }
}
~~~

Có **@Version** để JPA hỗ trợ optimistic checks khi cần. Nhưng việc chọn **PESSIMISTIC_WRITE** trong một transaction là một yêu cầu khóa tại database; hai cơ chế không phải một.

### 2.1. Schema ví dụ cho PostgreSQL

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL UNIQUE,
    stock_quantity INTEGER NOT NULL
        CHECK (stock_quantity >= 0)
);
~~~

DDL chỉ minh họa, việc INSERT/init version phải tương thích với provider và migration thực tế. Ràng buộc CHECK bảo vệ trạng thái tồn kho trước mọi SQL writer, nhưng không thay thế kiểm soát thao tác reserve mang tính nguyên tử trong điều kiện concurrency.

### 2.2. Một Product không có nghĩa chỉ có một lock

Database có thể giữ nhiều loại locks như row locks, key-range/gap locks, table intention locks, advisory locks tùy DB và isolation. JPA chỉ mô tả **lock mode yêu cầu**; không kiểm soát chính xác từng lock primitive của mọi DBMS.

Ví dụ, câu SQL tương đương có thể sử dụng FOR UPDATE ở PostgreSQL nhưng chiến lược lock khác ở SQL Server.

### 2.3. Tại sao chọn phương thức reserve?

Phương thức này thể hiện business invariant:
- quantity > 0;
- stockQuantity còn đủ;
- sau trừ không âm.

Nếu hai transactions cùng đọc stock=5 trước khi trừ 4, cả hai có thể tưởng đủ nếu không bảo vệ concurrency đúng. Pessimistic locking giúp tuần tự hóa việc đọc/ghi row tương ứng khi được sử dụng đúng; lock timeout quyết định tình huống transaction thứ hai phải chờ quá lâu.

## 3. Các LockModeType liên quan

JPA cung cấp các kiểu lock khác nhau; phần này tập trung vào **pessimistic modes**.

| Lock mode | Ý nghĩa chính | Lưu ý |
|---|---|---|
| PESSIMISTIC_READ | Yêu cầu khóa đọc bi quan | DB/provider có thể dùng shared lock hoặc chiến lược mạnh hơn |
| PESSIMISTIC_WRITE | Yêu cầu khóa ghi bi quan | Thường dùng cho read-modify-write của một entity |
| PESSIMISTIC_FORCE_INCREMENT | Khóa bi quan, đồng thời buộc tăng version theo semantics JPA | Cần entity versioned phù hợp và đánh giá tác động |
| OPTIMISTIC | Kiểm tra version theo khóa lạc quan | Không tương đương chờ row lock |
| OPTIMISTIC_FORCE_INCREMENT | Kiểm tra và yêu cầu tăng version | Không phải biện pháp đặt wait timeout của lock bi quan |
| NONE | Không yêu cầu lock mode bổ sung | Không có nghĩa DB không bao giờ lấy bất kỳ lock nào |

### 3.1. PESSIMISTIC_READ không phải luôn shared SQL lock

Không phải RDBMS nào cũng hỗ trợ shared row lock hoặc áp cùng cách cho isolation level. JPA provider được phép quy đổi PESSIMISTIC_READ thành một locking strategy khả dụng (có thể mạnh hơn dự kiến) khi DB thiếu hỗ trợ tương ứng.

Không suy ra chính xác SQL từ tên Java enum. Muốn biết hành vi thực, quan sát SQL/DB và chạy test cạnh tranh.

### 3.2. PESSIMISTIC_WRITE thường dùng cho trạng thái sẽ sửa

~~~java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);

product.reserve(2);
~~~

Transaction phải bao quanh **cả quá trình lấy khóa, kiểm tra stock và commit**, không tách bước lấy khóa ra một transaction riêng rồi mới sửa trong transaction khác.

### 3.3. PESSIMISTIC_FORCE_INCREMENT không phải “timeout mạnh hơn”

~~~java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
~~~

Mode này còn có semantics về **version increment**. Nó không phải lựa chọn để giảm thời gian chờ; dùng khi chiến lược concurrency của aggregate thực sự cần tăng version.

### 3.4. Locking có thể liên quan entity versioned

JPA kết hợp version checking với pessimistic locking theo các điều kiện của spec/provider. Nhưng không nên cho rằng chỉ thêm PESSIMISTIC_WRITE là đã thay toàn bộ chính sách @Version, hoặc rằng lock timeout giúp phát hiện optimistic conflicts. Đây là hai loại vấn đề khác nhau:
- Optimistic conflict: snapshot/version không còn hợp lệ;
- Pessimistic lock timeout: không lấy được lock trong giới hạn.

### 3.5. Trường hợp không dùng pessimistic lock

Một atomic conditional UPDATE:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :quantity,
    version = version + 1
WHERE id = :id
  AND stock_quantity >= :quantity;
~~~

có thể làm phép trừ tồn kho trong một câu SQL. Nếu affected rows = 1 là thành công; nếu 0 có thể do sản phẩm không tồn tại hoặc không đủ hàng. Đây là một thiết kế khác, có thể tránh một vòng SELECT + giữ lock lâu, nhưng vẫn chịu locks/transaction và cần xử lý writer/version policy.

Không mặc định mọi bài toán tồn kho bắt buộc phải dùng em.find PESSIMISTIC_WRITE.

## 4. Hint chuẩn jakarta.persistence.lock.timeout

Tên hint chuẩn trong Jakarta Persistence:

~~~java
"jakarta.persistence.lock.timeout"
~~~

Giá trị mô tả **thời gian chờ để lấy pessimistic lock**, thường được biểu diễn bằng số **mili giây**.

### 4.1. Dương: yêu cầu chờ có giới hạn

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.lock.timeout",
    1500
);
~~~

1500 nghĩa là **1,5 giây**, không phải 1500 giây. Tuy nhiên thời gian thực không được bảo đảm chính xác đến từng mili giây: driver, DB và cách provider dịch hint có thể làm tròn, giới hạn hoặc bỏ qua gợi ý.

### 4.2. Bằng 0: yêu cầu không chờ

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.lock.timeout",
    0
);
~~~

Khi DB/provider hỗ trợ, **0** thường tương ứng hành vi **NOWAIT**: nếu row đang bị khóa không tương thích, yêu cầu lấy khóa thất bại ngay thay vì chờ.

NOWAIT không có nghĩa “bỏ qua row bị khóa và trả row khác” — đó là semantics **SKIP LOCKED**, một khả năng khác và phụ thuộc DB/provider.

### 4.3. Giá trị âm không portable

Một số thư viện/provider có constants đặc biệt cho **WAIT_FOREVER**, **SKIP_LOCKED** hoặc những chế độ khóa riêng, có thể dùng giá trị âm. **Không coi giá trị âm tùy ý là hợp đồng portable của jakarta.persistence.lock.timeout.**

Nếu thấy ví dụ dùng -1 hoặc -2:
1. Xác định đó là quy ước của thư viện/provider nào;
2. Kiểm tra phiên bản, dialect và tài liệu chính thức của API đó;
3. Không suy rằng mọi JPA provider đều hiểu -2 là SKIP LOCKED;
4. Chạy integration test trên database mục tiêu.

### 4.4. Chọn kiểu value phù hợp

Với Map-based properties:

~~~java
Map<String, Object> hints = new HashMap<>();
hints.put("jakarta.persistence.lock.timeout", 750);
~~~

Một **Integer** là kiểu quen thuộc cho thời gian milliseconds trong JPA hints. Với annotation @QueryHint, value được biểu diễn dưới dạng **String**, chẳng hạn "750".

Không gửi "750s" hoặc Duration.ofMillis(750) tùy tiện cho hint chuẩn nếu provider không công bố hỗ trợ kiểu ấy.

### 4.5. Hint không phải command được đảm bảo hỗ trợ

Một provider có thể:
- Không hỗ trợ timeout cho dialect hiện tại;
- Hỗ trợ NOWAIT nhưng không hỗ trợ mốc chờ dương tùy ý;
- Làm tròn tới giây;
- Chỉ áp cho câu SELECT khóa, không áp mọi trường hợp join/follow-on locking;
- Bỏ qua hint không được nhận diện hoặc không được hỗ trợ;
- Phụ thuộc database session-level lock wait configuration.

**setHint không ném exception** không chứng minh DB đã thực thi timeout. Đó là lý do phần lớn bài học dành cho cách **kiểm tra hỗ trợ bằng thực nghiệm**.

### 4.6. Bảng các giá trị và ngữ nghĩa

| Giá trị ví dụ | Mong muốn của caller | Cần xác minh |
|---:|---|---|
| 0 | Không đợi khóa (NOWAIT) | DB/provider có thật sự sinh NOWAIT/biện pháp tương đương? |
| 250 | Giới hạn chờ khoảng 250 ms | Có được áp hay làm tròn? |
| 1000 | Giới hạn chờ khoảng 1 giây | Có mapping đúng milliseconds? |
| 5000 | Giới hạn chờ khoảng 5 giây | DB có giới hạn/setting riêng không? |
| Không đặt hint | Theo mặc định provider/DB | Không mặc định luôn chờ vô hạn |
| Giá trị âm | Không portable nếu không có tài liệu riêng | Kiểm tra extension provider cụ thể |

Không lấy con số 250 ms làm cam kết SLA cho cả HTTP request. Nó chỉ hướng tới **một đoạn chờ lấy lock**.

## 5. Áp dụng timeout cho EntityManager.find

Đây là API phổ biến và dễ đọc nhất khi cần lấy pessimistic lock cho **một entity theo ID**.

### 5.1. Dùng overload find có lock mode và properties

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import java.util.Map;

Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 750)
);
~~~

Giải thích:
- Product.class là entity type;
- productId là khóa chính;
- PESSIMISTIC_WRITE yêu cầu pessimistic write lock;
- Map cung cấp lock timeout hint;
- Lời gọi phải nằm trong transaction phù hợp.

### 5.2. Ví dụ service Spring hoàn chỉnh hơn

~~~java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserve(
            long productId, int quantity) {

        Product product = em.find(
            Product.class,
            productId,
            LockModeType.PESSIMISTIC_WRITE,
            Map.of(
                "jakarta.persistence.lock.timeout",
                750
            )
        );

        if (product == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy sản phẩm"
            );
        }

        product.reserve(quantity);
        // Dirty checking + flush/commit do JPA/Spring xử lý.
    }
}
~~~

Trong mô hình Spring proxy thông dụng, method @Transactional phải được gọi qua transaction boundary thực sự (không tự gọi nội bộ rồi giả định advice đã chạy). Phần chính là **lock, kiểm tra business rule, mutate và commit cùng transaction**.

### 5.3. Không thực hiện external I/O khi đang giữ khóa

Không nên:

~~~java
@Transactional
public void reserveAndNotify(...) {
    Product product = em.find(
        Product.class, id,
        LockModeType.PESSIMISTIC_WRITE,
        Map.of("jakarta.persistence.lock.timeout", 750)
    );

    product.reserve(quantity);

    externalPaymentApi.call(); // Có thể mất nhiều giây.
}
~~~

Lời gọi HTTP bên ngoài khi transaction còn giữ lock có thể làm các transactions khác phải chờ lâu. Cân nhắc đặt external interaction ngoài critical section hoặc dùng outbox/saga/compensation theo nghiệp vụ.

### 5.4. Null result không phải lock timeout

Nếu em.find trả **null**, đó là tình huống không tìm thấy entity tương ứng (theo semantics lookup), không phải bằng chứng lock timeout. Lock acquisition failure thường dẫn đến exception theo JPA/driver behavior.

Không viết xử lý:
- product == null → “Đang có người khóa sản phẩm”;
- mọi RuntimeException → “Không tìm thấy sản phẩm”.

Phải phân loại missing resource, lock failure, optimistic conflict và database connection errors riêng.

## 6. Áp timeout khi khóa managed entity bằng EntityManager.lock

Nếu entity **đã managed** trong persistence context, có thể yêu cầu lock rõ:

~~~java
Product product =
    em.find(Product.class, productId);

em.lock(
    product,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 750)
);
~~~

### 6.1. Có một bước đọc trước lock

Lưu ý quy trình này:
1. find tải Product mà chưa yêu cầu pessimistic lock;
2. lock sau đó yêu cầu khóa.

Giữa hai bước, một transaction khác có thể sửa Product; provider phải thực hiện các kiểm tra version phù hợp cho versioned entity. Khi mục tiêu là read-modify-write có khóa ngay từ đầu, **find với lock mode** thường đơn giản hơn.

### 6.2. Entity phải managed

~~~java
em.lock(
    detachedProduct,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

với detached entity là không đúng contract của EntityManager.lock đối với managed entity; JPA có thể ném IllegalArgumentException cho detached entity. Muốn xử lý detached, phải thiết kế merge/reload phù hợp, không gọi lock trực tiếp lên object không được context quản lý.

### 6.3. Không dùng em.lock như một lệnh kéo dài khóa qua nhiều transactions

Sau khi transaction commit/rollback, DB lock không còn được giữ như một lease lâu dài cho worker. Nếu cần ownership qua nhiều transaction, dùng trạng thái business/lease expiry trong database và protocol riêng, không dùng JPA lock mode như distributed lock có thời hạn.

### 6.4. refresh với lock mode

EntityManager cũng có các overload refresh với lock mode/properties, ví dụ:

~~~java
em.refresh(
    managedProduct,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of("jakarta.persistence.lock.timeout", 750)
);
~~~

Refresh còn mang semantics nạp lại state và có thể ghi đè pending in-memory changes. Không chọn refresh chỉ để đặt timeout nếu mục tiêu chỉ yêu cầu lock mà không cần làm mới state.

## 7. Áp lock timeout cho JPQL TypedQuery

Không phải mọi thao tác tìm entity đều là em.find theo ID. Khi cần chọn một hàng theo điều kiện business, có thể dùng **query.setLockMode(...)** cùng hint.

### 7.1. Ví dụ query chọn Product theo SKU

~~~java
TypedQuery<Product> query = em.createQuery(
    """
    select p
    from Product p
    where p.sku = :sku
    """,
    Product.class
);

query.setParameter("sku", "KB-001");
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.setHint("jakarta.persistence.lock.timeout", 1000);

Product product = query.getSingleResult();

product.reserve(2);
~~~

Toàn bộ luồng chạy trong một transaction. Việc gọi **setLockMode** phải có ý nghĩa đối với query trả entity; câu query chỉ select scalar hoặc DTO không tự trở thành một entity locking operation.

### 7.2. Thứ tự cấu hình hợp lý

Một sequence dễ đọc:

~~~java
TypedQuery<Product> query = em.createQuery(
    "select p from Product p where p.sku = :sku",
    Product.class
);

query.setParameter("sku", sku);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.setHint("jakarta.persistence.lock.timeout", 500);

Product product = query.getSingleResult();
~~~

Hint cần được thiết lập **trước khi query thực thi**. Đặt setHint sau getSingleResult không thay đổi kết quả lock acquisition đã xảy ra.

### 7.3. Query nhiều entity với khóa bi quan

~~~java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    where p.id in :ids
    order by p.id
    """,
    Product.class
)
.setParameter("ids", ids)
.setLockMode(LockModeType.PESSIMISTIC_WRITE)
.setHint("jakarta.persistence.lock.timeout", 1000)
.getResultList();
~~~

Trong query này, database có thể phải khóa nhiều rows. **Lock timeout không có nghĩa mỗi row được chờ 1000 ms độc lập hoặc cả câu lệnh chắc chắn kết thúc đúng 1000 ms**. Cách DB tính lock wait và độ chính xác timeout khác nhau. Một câu query có thể còn chịu query timeout, network delay, disk I/O hoặc những locks khác.

Đặt **ORDER BY id** có thể giúp áp một trật tự business nhất quán, nhưng không tự bảo đảm engine lấy locks chính xác theo ORDER BY hoặc loại trừ deadlock. Cần đánh giá execution plan và chiến lược khóa thực tế.

### 7.4. Phân biệt getSingleResult và timeout

Với getSingleResult:
- Không có kết quả có thể ném **NoResultException**.
- Nhiều kết quả có thể ném **NonUniqueResultException**.
- Không lấy được khóa có thể ném **LockTimeoutException** hoặc **PessimisticLockException**, tùy phạm vi lỗi.
- Query/DB có thể ném exception khác, không phải mọi lỗi đều do lock wait.

Không bắt chung rồi trả "không tìm thấy sản phẩm", vì như vậy che giấu contention.

### 7.5. Query có JOIN FETCH cần cẩn trọng

~~~java
select o
from PurchaseOrder o
join fetch o.lines
where o.id = :id
~~~

Nếu gắn lock mode, scope của những rows/associations bị khóa có thể khác giữa provider và database; một số dialect giới hạn việc áp FOR UPDATE với JOIN/FETCH và có thể dùng **follow-on locking** (khóa bằng query bổ sung).

Khi cần lock nhiều quan hệ, phải kiểm tra SQL và DB lock footprint. Không khẳng định graph/JOIN FETCH + setLockMode sẽ luôn khóa toàn bộ entity graph trong một statement portable.

### 7.6. Lock query không thay thế điều kiện thay đổi dữ liệu

Một query chọn Product bằng SKU và lấy lock không bảo đảm user được phép reserve số hàng đó. Quy tắc authorization, tenant scope, stock validation và database constraints phải được áp dụng độc lập. Nếu quyền truy cập bị kiểm soát theo tenant, query khóa cũng phải giới hạn tenant phù hợp.

## 8. Named query và Spring Data JPA

### 8.1. @NamedQuery với @QueryHint

JPA cho phép khai báo query hints trong named query:

~~~java
@NamedQuery(
    name = "Product.bySkuForReserve",
    query = """
        select p
        from Product p
        where p.sku = :sku
        """,
    lockMode = LockModeType.PESSIMISTIC_WRITE,
    hints = {
        @QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "750"
        )
    }
)
~~~

Phần annotation minh họa cần được đặt tại nơi metadata JPA hợp lệ, ví dụ entity Product. Chú ý:
- Trong **@QueryHint**, value là chuỗi "750".
- Đây vẫn là **hint**, không phải bảo đảm provider/DB luôn xử lý 750 ms.
- Khi gọi named query, phải có transaction phù hợp.

~~~java
Product product = em.createNamedQuery(
    "Product.bySkuForReserve",
    Product.class
)
.setParameter("sku", sku)
.getSingleResult();
~~~

### 8.2. Spring Data @Lock

Spring Data JPA cung cấp annotation **@Lock** để khai báo lock mode của repository query.

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select p
        from Product p
        where p.sku = :sku
        """)
    Product lockBySku(@Param("sku") String sku);
}
~~~

Đây là một repository query có yêu cầu khóa bi quan. Nhưng chỉ có @Lock **chưa cấu hình thời gian chờ cụ thể**.

### 8.3. Spring Data @QueryHints

Kết hợp @Lock với @QueryHints:

~~~java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    value = {
        @QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "750"
        )
    }
)
@Query("""
    select p
    from Product p
    where p.id = :id
    """)
Product lockForReserve(@Param("id") Long id);
~~~

Đặt đoạn này bên trong interface ProductRepository đã khai báo phù hợp. **@QueryHints** ở đây là annotation Spring Data JPA, khác với **jakarta.persistence.QueryHint** dùng bên trong nó.

### 8.4. Service chứa transaction

~~~java
@Service
public class InventoryRepositoryService {

    private final ProductRepository products;

    public InventoryRepositoryService(
            ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void reserve(Long id, int quantity) {
        Product product = products.lockForReserve(id);

        if (product == null) {
            throw new IllegalArgumentException(
                "Product không tồn tại"
            );
        }

        product.reserve(quantity);
    }
}
~~~

**@Lock không tự tạo transaction dài đúng ý nghĩa khi service không có transaction**, nên transaction boundary vẫn quan trọng. Các repository method có thể có những semantics transaction khác nhau; nên đặt thao tác business read-modify-write trong một transaction service có kiểm soát.

### 8.5. @Transactional(timeout) khác lock timeout

Spring:

~~~java
@Transactional(timeout = 5)
public void performWork() {
    // ...
}
~~~

thường đặt **transaction timeout theo giây** ở tầng transaction manager; trong khi:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 750);
~~~

là **lock acquisition timeout hint theo mili giây**.

Không dùng:

~~~java
@Transactional(timeout = 750)
~~~

rồi tưởng đó là 750 ms. Nó thường mang nghĩa 750 **giây** cho transaction timeout.

Transaction timeout còn phụ thuộc transaction manager/DB và mức enforce; nó không bảo đảm dịch sang NOWAIT/WAIT trên câu SELECT FOR UPDATE.

### 8.6. Repository save không tự cho lock mode

~~~java
repository.save(product);
~~~

không có nghĩa JPA tự lấy PESSIMISTIC_WRITE lock theo timeout đã khai báo ở một query khác. Nếu nghiệp vụ yêu cầu lock, phải gọi lock/query có lock mode trong cùng transaction rồi thay đổi managed entity.

### 8.7. Các namespace khác nhau dễ nhầm

| API | Package hoặc key |
|---|---|
| Jakarta LockModeType | jakarta.persistence.LockModeType |
| Jakarta QueryHint | jakarta.persistence.QueryHint |
| JPA hint name | jakarta.persistence.lock.timeout |
| Spring Data @Lock | org.springframework.data.jpa.repository.Lock |
| Spring Data @QueryHints | org.springframework.data.jpa.repository.QueryHints |
| Spring @Transactional | org.springframework.transaction.annotation.Transactional |

Trong dự án Java EE/JPA cũ, property key tương ứng thường là **javax.persistence.lock.timeout**. Việc chuyển Jakarta cần đồng bộ dependencies/imports/hints, không chỉ đổi một string.

## 9. Lock timeout, query timeout, statement timeout và transaction timeout

Một lỗi thiết kế phổ biến là cấu hình một timeout rồi kỳ vọng nó giới hạn **mọi thời gian chờ trong request**.

### 9.1. Sơ đồ các lớp timeout

~~~text
HTTP client timeout
  |
  +-- API service / @Transactional timeout
        |
        +-- Chờ connection pool
        |     |
        |     +-- JDBC connection timeout
        |
        +-- Query execution
              |
              +-- Query / statement timeout
              |     |
              |     +-- DB lock acquisition timeout
              |     |
              |     +-- CPU / I/O / plan execution
              |
              +-- Fetch results / network I/O
        |
        +-- Transaction commit / rollback
~~~

Chúng khác nhau về phạm vi, đơn vị, cách báo lỗi và khả năng được thực thi.

### 9.2. Bảng so sánh

| Cơ chế | Ví dụ cấu hình | Phạm vi mong muốn | Đơn vị phổ biến |
|---|---|---|---|
| JPA lock timeout | jakarta.persistence.lock.timeout=750 | Chờ lấy pessimistic lock | ms |
| JPA query timeout | jakarta.persistence.query.timeout=3000 | Thời gian thực thi query | ms |
| Spring transaction timeout | @Transactional(timeout=5) | Thời hạn transaction theo manager | giây |
| JDBC Statement timeout | Statement.setQueryTimeout(3) | Giới hạn statement execution | giây |
| Database lock wait setting | PostgreSQL lock_timeout / SQL Server LOCK_TIMEOUT | Chờ khóa theo DB/session/statement | Phụ thuộc DB |
| Connection pool acquisition timeout | Hikari connectionTimeout=2000 | Chờ lấy JDBC connection từ pool | ms |
| HTTP timeout | API gateway/client configuration | Request/response | Phụ thuộc stack |

Các ví dụ là định hướng, không phải lời bảo đảm mọi platform áp tất cả cơ chế đồng nhất.

### 9.3. JPA query timeout

~~~java
query.setHint(
    "jakarta.persistence.query.timeout",
    3000
);
~~~

Query timeout hướng tới tổng thời gian thực thi một query và có thể bao gồm việc chờ lock trong nhiều DB/driver, nhưng không thay cho lock timeout chuyên biệt. Nếu một query tốn 10 giây vì sort/join I/O mà không chờ lock, **lock timeout có thể không giúp gì**.

### 9.4. Timeout nào “thắng”?

Giả sử:
- Lock timeout = 1500 ms;
- Query timeout = 1000 ms;
- Transaction timeout = 10 s.

Không nên khẳng định “chắc chắn query timeout luôn xảy ra trước lock timeout”. Provider/driver/DB có thể có granularity, cancellation semantics và scheduling khác nhau. Loại exception quan sát được cũng có thể phụ thuộc việc timeout nào được thực thi đầu tiên.

Muốn biết hành vi, **phải kiểm thử trên tổ hợp provider + driver + DB + transaction manager thực tế**.

### 9.5. Connection pool timeout không phải lock timeout

Nếu B không lấy được JDBC connection vì pool đã cạn, nó chưa chắc gửi câu SQL nào xuống DB. Lỗi có thể đến từ HikariCP hoặc datasource, không phải LockTimeoutException của JPA.

Chỉ nhìn vào request “đợi lâu rồi timeout” không đủ để kết luận bị cạnh tranh row lock.

### 9.6. Deadline phía HTTP không tự rollback database

Client đóng kết nối sau 2 giây không nhất thiết khiến DB transaction của server tự dừng đúng thời điểm đó. Phải có timeout/cancel/rollback policy ở service/transaction/driver và kiểm soát idempotency để tránh kết quả “client tưởng thất bại nhưng server đã commit”.

### 9.7. Không giữ khóa trong lúc chờ external API

Dù đặt lock timeout của transaction B rất ngắn, transaction A có thể giữ khóa lâu nếu gọi payment/email/HTTP bên ngoài. Tối ưu **thời gian giữ lock** thường đem lại tác động lớn hơn việc chỉ giảm timeout của bên chờ.

## 10. Exception khi không lấy được pessimistic lock

Hai loại exception JPA chuẩn cần phân biệt:

- **jakarta.persistence.LockTimeoutException**
- **jakarta.persistence.PessimisticLockException**

### 10.1. LockTimeoutException

Theo semantics JPA, **LockTimeoutException** đại diện tình huống pessimistic lock acquisition failure chỉ làm rollback **statement** tương ứng, không yêu cầu transaction bị đánh dấu rollback do chính exception loại này.

Nó thường được dùng khi provider có thể xác định rằng lỗi giới hạn ở statement. Nhưng một database cụ thể có thể đã đưa transaction vào trạng thái lỗi; **không suy rằng cứ bắt LockTimeoutException là an toàn tiếp tục ghi trên transaction đó**.

### 10.2. PessimisticLockException

**PessimisticLockException** liên quan pessimistic lock failure khiến transaction cần bị rollback hoặc bị đánh dấu rollback theo JPA semantics. Khi thấy exception này, không tiếp tục xử lý như transaction vẫn khỏe.

### 10.3. Khác biệt về phạm vi rollback

| Loại lỗi | Semantics JPA | Hành động service an toàn thường dùng |
|---|---|---|
| LockTimeoutException | Không tự buộc mark toàn transaction rollback theo spec | Thường rollback unit of work và trả lỗi retryable theo policy |
| PessimisticLockException | Transaction-level rollback/failure | Rollback, mở transaction mới nếu retry |
| OptimisticLockException | Version conflict, không phải lock wait | Rollback, reload/resolve snapshot |
| QueryTimeoutException | Query quá thời hạn, không nhất thiết do khóa | Xem cause/transaction/DB, rollback phù hợp |
| TransactionRequiredException | Không có transaction cho lock operation | Sửa transaction boundary |
| NoResultException | Query không thấy row | Không báo nhầm là lock timeout |

### 10.4. PostgreSQL có thể làm transaction không thể tiếp tục

Ở PostgreSQL, một statement error do lock wait timeout/NOWAIT thường làm transaction hiện tại rơi vào trạng thái **aborted** cho đến khi rollback (trừ khi có savepoint/khôi phục được thiết kế riêng).

Vì vậy dù framework dịch lỗi thành LockTimeoutException, service vẫn nên **rollback transaction hiện tại** thay vì tiếp tục các câu SQL khác một cách lạc quan.

### 10.5. Code xử lý lỗi có giới hạn

Trong Spring, cách đơn giản là để exception thoát khỏi @Transactional method và rollback:

~~~java
@Transactional
public void reserve(Long productId, int quantity) {
    Product product = em.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE,
        Map.of("jakarta.persistence.lock.timeout", 500)
    );

    if (product == null) {
        throw new ProductNotFoundException(productId);
    }

    product.reserve(quantity);
}
~~~

**ProductNotFoundException** là application exception minh họa. Một controller advice hoặc application boundary phía ngoài transaction có thể chuyển LockTimeoutException/PessimisticLockException (hay Spring-translated exceptions phù hợp) thành phản hồi **retry later** mà không che các lỗi khác.

### 10.6. Không retry ngay trong transaction đã lỗi

Sai:

~~~java
try {
    Product product = em.find(
        Product.class, id,
        LockModeType.PESSIMISTIC_WRITE,
        hints
    );
} catch (LockTimeoutException ex) {
    // Thử lại em.find trên cùng transaction ngay?
}
~~~

Một transaction có thể đã bị DB đánh dấu aborted, hoặc chưa được rollback đúng. Retry đúng cần:
1. Phân loại lỗi;
2. Rollback transaction lỗi;
3. Tạo transaction mới nếu policy cho phép;
4. Có giới hạn attempts và backoff;
5. Bảo đảm operation idempotent hoặc có request ID chống xử lý trùng.

### 10.7. Phản hồi HTTP phù hợp

- **409 Conflict**: có thể phù hợp với xung đột resource/state theo contract API.
- **423 Locked**: có thể được API chọn trong một số trường hợp, nhưng không phải mã bắt buộc của JPA và thuộc semantics HTTP cụ thể.
- **503 Service Unavailable** kèm retry hint: có thể phù hợp với contention/tải hệ thống tạm thời theo policy.
- **504 Gateway Timeout**: có semantics gateway upstream timeout, không nên trả mặc định chỉ vì DB lock timeout.

Đừng ánh xạ mọi LockTimeoutException thành 404 hoặc 500 chung chung; đồng thời không trả thời gian retry chắc chắn nếu chưa có cơ sở. Cách chọn status phụ thuộc contract của API và tính chất lỗi.

## 11. Khi nào phải kiểm tra hỗ trợ?

Cấu hình:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 750);
~~~

chỉ chứng minh **ứng dụng đã gửi một yêu cầu tới JPA provider**, không chứng minh database sẽ ngừng chờ đúng 750 ms.

### 11.1. Chuỗi các lớp liên quan

~~~text
Ứng dụng
  setHint(lock.timeout=750)
         |
         v
JPA provider (Hibernate/EclipseLink/...)
  nhận diện hint?
  dịch sang dialect?
         |
         v
JDBC driver
  hỗ trợ SQL/call/timeout API?
         |
         v
Database dialect + phiên bản
  NOWAIT / WAIT n / lock_timeout?
         |
         v
Giao dịch thực tế
  có row bị khóa từ session khác?
  thời gian chờ và exception thực tế?
~~~

Một lớp không hỗ trợ có thể làm toàn bộ mong muốn timeout không đạt được, dù Java code compile.

### 11.2. Các câu hỏi cần trả lời

1. Dự án dùng phiên bản **Jakarta Persistence** nào?
2. Provider là Hibernate, EclipseLink hay implementation khác? Phiên bản?
3. JDBC driver version nào?
4. Database type/version/dialect là gì?
5. PESSIMISTIC_READ, WRITE, FORCE_INCREMENT có được hỗ trợ trên target DB không?
6. Hint **jakarta.persistence.lock.timeout** có được provider nhận diện không?
7. Giá trị **0** có được dịch sang NOWAIT hoặc tương đương không?
8. Giá trị **dương** có thực thi được giới hạn chờ, hay bị bỏ qua/làm tròn?
9. Lock timeout áp cho find, lock, TypedQuery theo các path có dùng thật không?
10. Có join, pagination, inheritance hoặc secondary locking ảnh hưởng không?
11. Khi timeout, exception nào được ném/được framework translate?
12. Transaction còn usable hay cần rollback ngay theo DB?
13. Có settings session/DB đang override hành vi không?
14. Có metrics/SQL logs chứng minh contention và thời gian chờ không?

### 11.3. Không chỉ kiểm tra metadata API

JPA không có một phương thức portable đơn giản kiểu **provider.supportsExactLockTimeout(750)** bảo đảm kết quả trên mọi database.

Cần phối hợp:
- Kiểm tra tài liệu provider/dialect đang dùng;
- Bật SQL logging/driver logging;
- Quan sát lệnh SQL và database configuration;
- Chạy integration test contention với hai connections/transactions;
- Xác minh exceptions và rollback;
- Giám sát ứng dụng thật ở staging/production.

### 11.4. Query.getHints không phải bằng chứng database đã áp dụng

Nếu API trả lại một Map chứa:

~~~text
jakarta.persistence.lock.timeout = 750
~~~

điều đó chủ yếu phản ánh hint đã được gắn với query. Không thể từ đó kết luận SQL thực thi timeout đúng, nhất là với provider không hỗ trợ dialect-specific wait controls.

### 11.5. Hành vi có thể đổi theo nâng cấp

Nâng cấp Hibernate, EclipseLink, JDBC driver hoặc database version có thể thay:
- Cách dịch 0 thành NOWAIT;
- Cách làm tròn milliseconds;
- Việc sử dụng statement-level vs session-level timeout;
- SQL follow-on locking;
- Exception translation;
- Khả năng SKIP LOCKED;
- Tương tác với pagination/joins.

Nên giữ integration test kiểm chứng lock timeout qua các lần upgrade, không chỉ kiểm tra một lần khi bắt đầu dự án.

## 12. Đặc điểm riêng của PostgreSQL, SQL Server, Oracle và MySQL

JPA chuẩn hóa tên API, nhưng phần điều khiển lock wait được thực thi bởi **database dialect**. Dưới đây là các minh họa về **SQL phía database**, không phải những SQL mà JPA bắt buộc phải sinh ra.

### 12.1. PostgreSQL: SELECT FOR UPDATE NOWAIT

Một transaction A lấy khóa:

~~~sql
BEGIN;

SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE;

-- Giữ transaction mở để transaction khác gặp contention.
-- Kết thúc bằng COMMIT hoặc ROLLBACK sau khi test.
~~~

Một kết nối/transaction B khác thử không chờ:

~~~sql
BEGIN;

SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE NOWAIT;

-- Nếu row đang có lock không tương thích,
-- PostgreSQL có thể trả lỗi lock_not_available.

ROLLBACK;
~~~

Đây là cách kiểm chứng **database trực tiếp** có NOWAIT. Nó chưa chứng minh JPA provider sẽ dịch lock.timeout=0 thành FOR UPDATE NOWAIT; bước đó cần quan sát SQL của JPA.

### 12.2. PostgreSQL: lock_timeout ở cấp statement/session

PostgreSQL có setting **lock_timeout**, ví dụ:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '750ms';

SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE;

COMMIT;
~~~

**SET LOCAL** áp trong transaction hiện tại. Nếu timeout xảy ra và statement lỗi, transaction PostgreSQL thường vào trạng thái aborted, cần **ROLLBACK** thay vì tiếp tục COMMIT như không có gì. Vì vậy đoạn SQL trên minh họa đường thành công; ở nhánh lỗi phải rollback.

Lợi ích của **SET LOCAL** so với cấu hình session lâu dài là tránh để timeout thay đổi ngoài ý muốn cho connection được trả về pool. Nhưng đây là **cơ chế PostgreSQL-specific**, không thể dùng nguyên văn trên SQL Server hoặc Oracle.

### 12.3. SQL Server: SET LOCK_TIMEOUT

SQL Server hỗ trợ:

~~~sql
SET LOCK_TIMEOUT 750;
~~~

Con số là milliseconds theo cú pháp của SQL Server. Một transaction có thể:

~~~sql
SET LOCK_TIMEOUT 750;

BEGIN TRANSACTION;

SELECT id, sku, stock_quantity
FROM dbo.products WITH (UPDLOCK, ROWLOCK)
WHERE id = 42;

COMMIT TRANSACTION;

SET LOCK_TIMEOUT -1;
~~~

Những câu SQL trên chỉ là ví dụ cho một đường thành công; khi lỗi, phải rollback thích hợp và khôi phục session setting. **-1** ở đây là quy ước **SQL Server SET LOCK_TIMEOUT**, không phải giá trị portable của **jakarta.persistence.lock.timeout**.

**UPDLOCK/ROWLOCK** là table hints của SQL Server, không phải trực tiếp những tên LockModeType của JPA. ROWLOCK là gợi ý và database vẫn có thể dùng lock strategy khác trong một số trường hợp. Không suy ra SQL Server sẽ sinh chính xác cú pháp này từ mọi provider.

Nếu ứng dụng dùng connection pool và tự thay đổi session setting, phải bảo đảm cleanup/reset ngay cả khi exception xảy ra. Tránh “rò” session-level timeout sang request khác.

### 12.4. Oracle: FOR UPDATE NOWAIT/WAIT

Trong những phiên bản Oracle hỗ trợ tương ứng:

~~~sql
SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE NOWAIT;
~~~

Hoặc chờ có giới hạn theo cú pháp dialect:

~~~sql
SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE WAIT 5;
~~~

**WAIT 5** ở ví dụ Oracle được hiểu theo **giây** trong cú pháp đó, không phải 5 milliseconds. JPA hint **5000** milliseconds có thể cần provider quy đổi sang đơn vị database. Phải xác nhận quy đổi và mức làm tròn khi kiểm thử.

### 12.5. MySQL/InnoDB: thời gian chờ và NOWAIT

MySQL/InnoDB có những cơ chế riêng như **innodb_lock_wait_timeout** (thường theo giây), còn cú pháp NOWAIT/SKIP LOCKED phụ thuộc phiên bản và câu SELECT.

Ví dụ định hướng:

~~~sql
START TRANSACTION;

SELECT id, sku, stock_quantity
FROM products
WHERE id = 42
FOR UPDATE NOWAIT;

ROLLBACK;
~~~

Không dùng đoạn này nếu DB/version không hỗ trợ. Hơn nữa, cấu hình InnoDB lock wait timeout có thể khác biệt so với PostgreSQL lock_timeout: đơn vị, phạm vi locks và hành vi khi statement thất bại cần được xác minh.

### 12.6. Bảng so sánh định hướng

| Database | Ví dụ cơ chế lock wait | Cần xác nhận |
|---|---|---|
| PostgreSQL | FOR UPDATE NOWAIT, SET LOCAL lock_timeout | Provider translation, transaction aborted sau error |
| SQL Server | SET LOCK_TIMEOUT, UPDLOCK/READPAST | Session cleanup, driver, SQL hints, lock escalation |
| Oracle | FOR UPDATE NOWAIT / WAIT n | Đơn vị giây, dialect và query shape |
| MySQL/InnoDB | NOWAIT ở phiên bản hỗ trợ, innodb_lock_wait_timeout | Version, engine, granularity, statement failure |
| MariaDB/khác | Cú pháp/cấu hình tùy DB | Không suy từ MySQL hoặc JPA API mà kết luận |

**Bảng không phải cam kết rằng mọi JPA provider trên những DB này hỗ trợ cùng một timeout value.** Những khả năng DB có thể được dùng bằng SQL trực tiếp nhưng chưa chắc đã được provider nối với JPA hint.

### 12.7. Khi cần fallback database-specific

Nếu hint JPA không được áp và yêu cầu thời gian chờ là bắt buộc, có thể cân nhắc:
- Session/transaction-local lock timeout;
- Native SQL FOR UPDATE NOWAIT/WAIT;
- JDBC CallableStatement/Statement timeout phù hợp;
- Repository implementation riêng cho từng dialect;
- Một atomic conditional update thay cho read-lock-modify;
- Thay đổi thiết kế concurrency/queue.

Bất kỳ fallback nào cũng phải **được kiểm thử đúng trên DB mục tiêu**, giữ transaction boundary và lifecycle connection pool. Không dùng tùy tiện nhiều mechanisms xung đột trong cùng transaction.

## 13. SKIP LOCKED không phải một giá trị chờ thông thường

**SKIP LOCKED** là một cơ chế đặc biệt: thay vì đợi row đang bị khóa, database có thể **bỏ qua row đó** và trả các rows khác chưa bị khóa.

~~~text
NOWAIT:
    Row A đang locked → thất bại ngay khi cố lấy A

WAIT 750ms:
    Row A đang locked → chờ có giới hạn nếu hỗ trợ

SKIP LOCKED:
    Row A đang locked → không lấy A;
    có thể lấy Row B nếu B đủ điều kiện và không bị khóa
~~~

### 13.1. Use case của SKIP LOCKED

Một worker queue có thể chọn công việc **chưa bị worker khác giữ**, nhờ đó xử lý tasks khác mà không chờ một row nóng.

~~~sql
-- PostgreSQL minh họa:
SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority DESC, id
FOR UPDATE SKIP LOCKED
LIMIT 10;
~~~

SQL này là dialect-specific. Tất cả thao tác claim/update status phải nằm trong transaction phù hợp, và cần chiến lược idempotency, retries, lease/visibility timeout khi job kéo dài.

### 13.2. Không dùng SKIP LOCKED cho phép chuyển tiền sai semantics

Nếu người dùng yêu cầu trừ tiền **Account#42**, việc bỏ qua Account#42 vì đang khóa rồi thao tác trên tài khoản khác là sai nghiệp vụ.

SKIP LOCKED chỉ phù hợp khi nghiệp vụ cho phép **lựa chọn item thay thế**. Còn cập nhật một row cố định cần NOWAIT, WAIT có giới hạn hoặc một cơ chế khác rõ ràng.

### 13.3. Các giá trị âm của Hibernate không phải JPA portable

Một số phiên bản Hibernate có hỗ trợ constants/giá trị đặc biệt để yêu cầu SKIP LOCKED qua cơ chế lock options. Không coi bất kỳ giá trị âm như -2 là phần bảo đảm của hint chuẩn trong mọi provider/version/dialect.

Nếu muốn dùng:
1. Ghi rõ provider/version;
2. Dùng API/constant chính thức của phiên bản đó;
3. Kiểm tra SQL thật;
4. Test nhiều workers cùng claim jobs;
5. Test job không bị mất và không xử lý trùng.

### 13.4. SKIP LOCKED không bảo đảm công bằng

Một job bị khóa liên tục có thể bị bỏ qua nhiều lần. Nếu queue cần fairness hoặc deadline, phải bổ sung:
- Priority aging;
- Retry/checkpoint;
- Lease expiry;
- Monitoring số jobs bị bỏ qua;
- Cơ chế xử lý những jobs có nguy cơ starvation.

Không mặc định SKIP LOCKED tương đương FIFO queue.

## 14. Quy trình kiểm tra hỗ trợ một cách có hệ thống

Một checklist kiểm chứng thực tế nên tách rõ **API**, **SQL**, **DB wait** và **ứng dụng**.

### 14.1. Bước 1 — Ghi lại môi trường

Ví dụ một bản ghi thử nghiệm:

~~~text
JDK:                   phiên bản đang chạy
Jakarta Persistence:   phiên bản API
JPA provider:          Hibernate/EclipseLink và phiên bản
JDBC driver:           tên + phiên bản
Database:              PostgreSQL/SQL Server/... và phiên bản
Database dialect:      dialect được provider sử dụng
Connection pool:       Hikari/... + pool size
Transaction manager:   resource-local/JTA/Spring
Lock mode:             PESSIMISTIC_WRITE
Timeout hint:          0 / 750 / không cấu hình
Query path:            em.find / em.lock / JPQL / repository
~~~

Không ghi lại các thông số này sẽ khó giải thích vì sao kết quả test thay đổi sau nâng cấp.

### 14.2. Bước 2 — Xác minh row tồn tại

Trước khi tạo contention, xác minh Product#42 tồn tại và được commit. Nếu em.find trả null do sai ID, test có thể “kết thúc nhanh” nhưng không phải vì NOWAIT hoạt động.

### 14.3. Bước 3 — Cần hai physical DB connections

Một transaction A phải giữ lock, transaction B ở **một kết nối khác** mới bị chặn. Nếu cả hai thao tác dùng cùng EntityManager/connection/transaction, B có thể truy cập row do chính nó đã khóa và không tạo contention thật.

Với connection pool size=1, B có thể chờ lấy **connection** thay vì chờ row lock; đó là test sai mục tiêu. Nên có ít nhất hai physical connections độc lập trong môi trường thử nghiệm.

### 14.4. Bước 4 — Transaction A lấy lock và giữ

~~~java
EntityManager a = emf.createEntityManager();
a.getTransaction().begin();

Product held = a.find(
    Product.class, id,
    LockModeType.PESSIMISTIC_WRITE
);

// Không commit/rollback A trước khi B thực sự thử lấy lock.
~~~

Trong một test thực tế, không để EntityManager a dùng chung nhiều threads; thread A sở hữu context/transaction của nó và dùng tín hiệu điều phối để giữ lock.

### 14.5. Bước 5 — B thử lock với hint 0

~~~java
EntityManager b = emf.createEntityManager();
b.getTransaction().begin();

long begin = System.nanoTime();

try {
    b.find(
        Product.class, id,
        LockModeType.PESSIMISTIC_WRITE,
        Map.of("jakarta.persistence.lock.timeout", 0)
    );
} finally {
    long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - begin
        );

    System.out.println(
        "elapsedMs=" + elapsedMs
    );

    if (b.getTransaction().isActive()) {
        b.getTransaction().rollback();
    }
    b.close();
}
~~~

Đây là **khung mã để quan sát**; chưa khẳng định exception nào sẽ xảy ra. Khi hint 0 được hỗ trợ và row đang bị giữ khóa không tương thích, B nên thất bại nhanh theo NOWAIT semantics. Nếu B đợi đến khi A nhả lock rồi thành công, cần nghi ngờ hint không áp dụng hoặc test chưa tạo contention đúng.

### 14.6. Bước 6 — Lặp lại với thời gian dương

~~~java
Map.of(
    "jakarta.persistence.lock.timeout",
    750
)
~~~

Giữ A khóa lâu hơn khoảng thời gian kỳ vọng, rồi đo:
- B có thất bại do lock timeout không?
- Thời gian thực gần giới hạn nào?
- Nó có chờ đến khi A commit không?
- Driver/provider có làm tròn sang 1 giây không?
- Khi timeout, exception type/cause là gì?
- Transaction B còn active nhưng DB đã aborted không?

Không dùng một phép đo đơn lẻ trong môi trường CI quá tải để khẳng định độ chính xác tới 1 ms.

### 14.7. Bước 7 — Chạy control case không timeout hint

Thử cùng query nhưng **bỏ hint** để quan sát mặc định:
- Nếu B chờ đến khi A nhả khóa, có cơ sở để so sánh;
- Nếu B cũng thất bại rất nhanh, có thể database session đang có lock_timeout mặc định hoặc có một timeout khác;
- Nếu B không bị chặn, khả năng A chưa giữ đúng lock, B dùng cùng transaction, hoặc câu query không nhắm đúng row.

Một test hữu ích cần có **control** để tránh false positives.

### 14.8. Bước 8 — Quan sát SQL và database

Kiểm tra provider SQL logs, JDBC traces và DB views:
- Có SELECT ... FOR UPDATE hoặc cú pháp tương đương không?
- Có NOWAIT/WAIT n hoặc session setting tương ứng không?
- B đang chờ lock, chờ connection, hay chờ query I/O?
- A và B có đúng hai DB session IDs khác nhau không?

Với PostgreSQL, có thể quan sát **pg_stat_activity**, **pg_locks**, **pg_blocking_pids(pid)** khi có quyền; với SQL Server có DMVs và wait types phù hợp; với Oracle có dynamic performance views. Không đưa credentials hoặc dữ liệu nhạy cảm vào logs.

### 14.9. Bước 9 — Ghi kết quả hỗ trợ thực tế

Mẫu báo cáo:

~~~text
Scenario:      Two concurrent transactions, same Product#42
Lock mode:     PESSIMISTIC_WRITE
Path:          EntityManager.find(...)
Hint:          jakarta.persistence.lock.timeout = 750
Provider/DB:   [versions]
Holder:        Held lock until test released
Waiter:        [exception / acquired after release]
Observed wait: [ms, with tolerance]
SQL evidence:  [NOWAIT / WAIT / session setting / none]
Transaction:   [rolled back / status after failure]
Conclusion:    [supported / ignored / inconclusive]
~~~

Nếu waiter chờ vài giây và thành công sau khi A nhả khóa, trong khi timeout=750 được kỳ vọng, kết luận hợp lý là **chưa chứng minh hint hoạt động**; có thể nó bị bỏ qua hoặc mapping không đúng. Điều chỉnh test trước khi coi đó là một bug của database.

### 14.10. Kiểm tra mọi đường dùng thật

Provider có thể hỗ trợ em.find khác với JPQL query khi có JOIN/FETCH/pagination, hoặc có giới hạn với PESSIMISTIC_READ so với WRITE. Nếu application thực sự dùng repository @Lock + @QueryHints, test **chính repository method đó**, không chỉ một em.find mẫu.

### 14.11. Dùng kết quả để quyết định fallback

Kết luận nên là dữ kiện:

| Kết quả thực nghiệm | Quyết định |
|---|---|
| NOWAIT thực thi đúng trên target stack | Có thể dùng khi nghiệp vụ chấp nhận fail fast |
| Positive wait hoạt động gần kỳ vọng | Dùng với tolerance, monitoring và timeout layers khác |
| Positive wait bị bỏ qua nhưng NOWAIT hoạt động | Cân nhắc fail fast hoặc database-specific setting |
| Lock hint bị bỏ qua toàn bộ | Không đặt correctness/SLA lên hint; chọn giải pháp khác |
| Exception/rollback khác mong đợi | Thiết kế boundary rollback/retry theo DB |
| JOIN/fetch làm lock SQL không khả dụng | Tách query IDs, lock root rows rồi đọc graph có kiểm soát |

Không biến “support được trên laptop” thành giả định production nếu DB/driver/version hoặc connection pool behavior khác.

## 15. Integration test: hai transaction cạnh tranh thực sự

Để kiểm tra lock timeout, cần **một transaction đang giữ khóa** và **một transaction khác đang cố lấy khóa không tương thích trên cùng row**. Không dùng mock EntityManager hoặc một EntityManager duy nhất rồi kết luận database hỗ trợ NOWAIT.

### 15.1. Điều kiện test

- Product test tồn tại, đã commit và có ID cố định trong fixture.
- Database thật hoặc container cùng loại/version với production.
- Connection pool có tối thiểu hai connections có thể hoạt động đồng thời.
- JPA provider và JDBC driver giống cấu hình cần kiểm tra.
- Hai EntityManagers độc lập; không chia sẻ EntityManager giữa threads.
- Test có timeout guard, signal giải phóng khóa và cleanup trong finally.
- Không có job ngoài test đang giữ cùng row hoặc thay đổi fixture.
- Ghi lại SQL và elapsed time để phân biệt hỗ trợ thật với ngẫu nhiên.

### 15.2. Test NOWAIT bằng CountDownLatch

Ví dụ JUnit 5 với resource-local EntityManager; đây là mẫu tương đối đầy đủ, cần điều chỉnh exception type/tolerance theo provider/DB thực tế:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceException;

import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.concurrent.*;

import static org.junit.jupiter.api.Assertions.*;

class LockTimeoutIntegrationTest {

    private EntityManagerFactory emf;
    private Long productId;

    @Test
    void nowaitMustNotWaitForHolderToCommit()
            throws Exception {

        ExecutorService executor =
            Executors.newSingleThreadExecutor();

        CountDownLatch lockAcquired =
            new CountDownLatch(1);

        CountDownLatch releaseLock =
            new CountDownLatch(1);

        Future<?> holder = executor.submit(() -> {
            EntityManager a = emf.createEntityManager();

            try {
                a.getTransaction().begin();

                Product row = a.find(
                    Product.class,
                    productId,
                    LockModeType.PESSIMISTIC_WRITE
                );

                if (row == null) {
                    throw new IllegalStateException(
                        "Fixture Product không tồn tại"
                    );
                }

                lockAcquired.countDown();

                // Không giữ lock vô hạn nếu waiter hỏng.
                if (!releaseLock.await(
                        6, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Test không giải phóng khóa kịp"
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(ex);
            } finally {
                if (a.getTransaction().isActive()) {
                    a.getTransaction().rollback();
                }
                a.close();
            }
        });

        try {
            assertTrue(
                lockAcquired.await(3, TimeUnit.SECONDS),
                "Holder chưa lấy được lock"
            );

            EntityManager b = emf.createEntityManager();

            try {
                b.getTransaction().begin();

                long started = System.nanoTime();

                assertThrows(
                    PersistenceException.class,
                    () -> b.find(
                        Product.class,
                        productId,
                        LockModeType.PESSIMISTIC_WRITE,
                        Map.of(
                            "jakarta.persistence.lock.timeout",
                            0
                        )
                    )
                );

                long elapsedMs =
                    TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started
                    );

                // Ngưỡng là tiêu chí kiểm tra stack
                // đang dùng, KHÔNG phải cam kết JPA.
                assertTrue(
                    elapsedMs < 2000,
                    "NOWAIT có thể chưa được áp dụng"
                );
            } finally {
                if (b.getTransaction().isActive()) {
                    b.getTransaction().rollback();
                }
                b.close();
            }
        } finally {
            releaseLock.countDown();

            try {
                holder.get(10, TimeUnit.SECONDS);
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Cần khởi tạo **emf** và **productId** bằng fixture trước test; ví dụ không dùng Spring TestTransaction để giả định toàn bộ DB setup tự commit.

**Điểm quan trọng:** assertion này là **bài thử tính năng/hành vi theo môi trường**, không phải điều kiện của spec bắt mọi provider phải ném trong 2000 ms. Nếu hint không hỗ trợ, bài test nên **fail hoặc được đánh dấu environment capability unsupported**, không nên sửa assertion thành một lời khẳng định JPA buộc hỗ trợ NOWAIT.

### 15.3. Vì sao không dùng Thread.sleep mù quáng?

Một test như:

~~~java
Thread.sleep(1000);
startSecondTransaction();
~~~

không chứng minh holder đã lấy lock. Nếu thread A chậm vì CI/scheduling/connection pool, B có thể đi trước và test sai kết luận.

Dùng **CountDownLatch lockAcquired** chỉ được signal **sau khi câu lock hoàn tất**, nhờ đó B bắt đầu khi A đã thực sự giữ lock. Latch thứ hai giữ A ở transaction mở cho đến khi B đo xong.

### 15.4. Vì sao holder rollback thay vì commit?

Mục đích test là kiểm tra **lock wait**, không cần thay đổi stock. Rollback của A đủ để nhả khóa. Nếu test đồng thời kiểm tra dữ liệu thay đổi sau commit, có thể dùng một test khác với phạm vi rõ hơn.

### 15.5. Tại sao cần ngưỡng thử nghiệm rộng hơn 0?

NOWAIT không có nghĩa toàn lời gọi Java mất đúng **0 ms**. Vẫn có:
- Network/JDBC overhead;
- Thời gian parse/execute SQL;
- JPA provider preparation;
- Thread scheduling;
- Exception construction/translation.

Ta kỳ vọng không **đợi đến khi A commit**, chứ không kỳ vọng zero elapsed time. Ngưỡng đo nên được thiết kế rộng hợp lý dựa trên test environment, không ghi nó thành bảo đảm JPA.

### 15.6. Test timeout dương

Thay hint 0 bằng 750 và để holder giữ khóa lâu hơn khoảng đó:

~~~java
Map<String, Object> properties = Map.of(
    "jakarta.persistence.lock.timeout", 750
);
~~~

Đo elapsedMs, exception và holder state. Có thể có các kết quả:

| Quan sát | Diễn giải ban đầu |
|---|---|
| B lỗi lock timeout xấp xỉ 750 ms, A vẫn giữ khóa | Có dấu hiệu positive timeout hoạt động |
| B lỗi ngay tức khắc | Có thể provider làm tròn thành NOWAIT hoặc setting DB khác |
| B chờ tới lúc A nhả khóa rồi thành công | Positive hint có thể bị bỏ qua |
| B thất bại vì connection pool | Không phải kiểm chứng lock timeout |
| B lỗi ở query timeout/transaction timeout | Cần tách các timeout layers |
| B không bị chặn dù A đang giữ lock | Có thể không cùng row, không lock thật hoặc cách DB xử lý khác |

Đừng assert chính xác 750 ms. Khi provider chỉ hỗ trợ đơn vị giây, chênh lệch có thể đáng kể.

### 15.7. Test unsupported behavior cũng có giá trị

Nếu kiểm thử xác nhận hint bị bỏ qua ở cấu hình production, đây là thông tin quan trọng để quyết định:
- Sử dụng database-native lock timeout;
- Chọn NOWAIT thay positive wait;
- Thiết kế conditional update;
- Cắt ngắn critical section;
- Không hứa với caller về deadline lock wait không được đảm bảo.

Không che kết quả unsupported bằng cách bỏ qua test và giữ API SLA sai.

### 15.8. Test lỗi ở một statement không có nghĩa transaction khỏe

Sau timeout, một DB như PostgreSQL có thể abort transaction. Test nên:
1. Bắt exception;
2. Rollback B;
3. Mở EntityManager C với transaction mới;
4. Thử một query đơn giản;
5. Đảm bảo connection pool không bị rò trạng thái.

Không viết test “catch LockTimeoutException rồi tiếp tục UPDATE khác trong B” như là điều mặc định an toàn.

### 15.9. Lặp lại với query và repository thật

Sau khi em.find hoạt động, cần test:

~~~java
TypedQuery<Product> q = em.createQuery(
    "select p from Product p where p.id = :id",
    Product.class
);
q.setParameter("id", productId);
q.setLockMode(LockModeType.PESSIMISTIC_WRITE);
q.setHint("jakarta.persistence.lock.timeout", 750);
q.getSingleResult();
~~~

Và nếu production dùng Spring Data:

~~~java
repository.lockForReserve(productId);
~~~

trong transaction độc lập. Mục tiêu là xác nhận **đường code sản xuất**, không chỉ API minh họa.

## 16. Kiểm tra SQL, khóa và dữ liệu đo đạc

### 16.1. Bật SQL logging có giới hạn

Trong môi trường thử nghiệm Hibernate, có thể bật SQL logging qua logger thích hợp của phiên bản Hibernate; ví dụ Spring Boot:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Logger cho bind parameters và statistics khác giữa các phiên bản Hibernate; tra cấu hình tương ứng trước khi bật. Không bật log bind values chứa thông tin cá nhân/secret trên production thiếu kiểm soát.

### 16.2. Tìm chứng cứ lệnh khóa

Với PostgreSQL, có thể thấy SQL kiểu:

~~~sql
SELECT ...
FROM products p
WHERE p.id = ?
FOR UPDATE NOWAIT;
~~~

hoặc query tương đương. Nhưng provider có thể dùng SQL khác. Nếu statement chỉ là SELECT không khóa trong môi trường mà đáng lẽ cần PESSIMISTIC_WRITE, cần xem:
- Entity đã managed trước query?
- Có secondary/follow-on locking không?
- Hint được áp đúng query không?
- Transaction hoạt động không?
- Dialect có hỗ trợ locking không?

Không lấy việc không thấy chuỗi FOR UPDATE trong **một dòng log** làm bằng chứng duy nhất khóa chưa được lấy.

### 16.3. PostgreSQL: xem sessions đang chờ

Một query chẩn đoán (cần quyền thích hợp):

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database();
~~~

Khi transaction B đang đợi, wait_event_type có thể cho thấy loại wait và pg_blocking_pids có thể chỉ ra session đang chặn. Đây là cách phân biệt lock contention với query I/O hoặc chờ lấy connection (trường hợp không xuất hiện dưới dạng một DB backend đang chờ lock).

Không để production dashboard expose các SQL query texts chứa dữ liệu nhạy cảm cho người không có quyền.

### 16.4. SQL Server và Oracle cũng có wait diagnostics riêng

SQL Server có dynamic management views về requests/waits/locks; Oracle có các views về sessions, blocking sessions và waits. Tên/cột/quyền thay đổi theo version, nên dùng query phù hợp hệ thống đang vận hành.

Đừng copy câu SQL pg_stat_activity sang Oracle hoặc SQL Server.

### 16.5. Đo nhiều metric cùng nhau

| Metric | Ý nghĩa |
|---|---|
| Lock acquisition attempts | Số yêu cầu lấy pessimistic locks |
| Lock wait duration | Thời gian chờ lock |
| Lock timeout count | Tần suất không lấy được lock đúng hạn |
| DB deadlock count | Các giao dịch khóa nhau theo vòng |
| Transaction duration | Thời gian mở transaction, không chỉ wait |
| Connection pool active/waiting | Phân biệt DB locks và pool starvation |
| Query execution time | Thời gian SQL tổng thể |
| Retry count | Tải phát sinh từ retries |
| User-facing error rate | Tác động thực đến nghiệp vụ |
| Hot row/entity key | Xác định điểm tranh chấp, không log secrets |

Một p95 lock wait tăng có thể cho thấy traffic tập trung trên vài rows, transaction giữ khóa quá lâu hoặc DB có vấn đề. Không giải quyết chỉ bằng tăng timeout nếu nguyên nhân là critical section không hợp lý.

### 16.6. Quan sát “success sau chờ” cũng quan trọng

Một request B có thể chờ được lock 700 ms rồi reserve thành công. Nếu chỉ đếm exceptions, hệ thống bỏ qua latency do contention. Cần theo dõi cả **wait duration của những lần thành công**, nếu DB/provider instrumentation cho phép.

### 16.7. Tránh logging nguyên ID/parameters nhạy cảm

Trong hệ thống có customer financial account, raw account numbers, payment tokens hoặc PII không nên bị đưa thẳng vào logs. Dùng correlation IDs và key hashing/safe tags nếu cần phân tích hot keys.

## 17. Kiến trúc xử lý timeout và retry

### 17.1. Timeout là một kết quả bình thường của cạnh tranh

Nếu nhiều writers hợp lệ tranh một row, lock acquisition timeout không nhất thiết là lỗi code. Tuy nhiên ứng dụng phải có contract xử lý:
- Người dùng được thông báo thử lại hoặc request được tự retry có kiểm soát;
- Transaction bị rollback an toàn;
- Request không bị xử lý trùng;
- Dịch vụ không làm cạn connection pool vì retry quá nhiều.

### 17.2. Retry sau rollback với transaction mới

~~~text
Try #1:
  begin tx
  lock Product#42 with timeout
  → LockTimeoutException
  rollback tx

Backoff có giới hạn

Try #2:
  begin NEW tx
  lock Product#42
  read CURRENT stock
  apply business rule
  commit
~~~

Không giữ version/stock cũ từ transaction thất bại và áp trực tiếp mà không đọc lại khi bắt đầu attempt mới.

### 17.3. Không retry vô hạn

Nếu 100 requests cùng lock một row, tất cả timeout rồi retry ngay lập tức, contention có thể tệ hơn (thundering herd).

Nên có:
- Giới hạn retries;
- Backoff ngẫu nhiên/jitter phù hợp;
- Retry budgets;
- Circuit breaker/load shedding khi hệ thống quá tải;
- Monitoring số lần retry trên mỗi operation;
- Idempotency key cho những thao tác có side effects.

### 17.4. Tách optimistic conflict khỏi pessimistic contention

| Tình huống | Cách phản hồi thường phù hợp |
|---|---|
| Row đang bị khóa, fail-fast | Retry sau backoff hoặc báo bận |
| Lock wait đã vượt giới hạn | Rollback và retry hạn chế nếu phù hợp |
| Optimistic version conflict của form cũ | Reload/compare; không retry y nguyên |
| Deadlock victim | Rollback; retry có giới hạn nếu operation an toàn |
| Constraint violation do input sai | Không retry tự động |
| Thiếu database connection | Chẩn đoán pool/DB availability, không gọi lại liên tục |

### 17.5. Idempotency của reserve

Nếu request trừ tồn kho 2 đơn vị, caller timeout và tự gửi lại, không thể chỉ dựa vào row lock để bảo đảm trừ đúng một lần. Một request có thể đã commit trước khi response bị mất.

Thiết kế có thể dùng:
- Reservation request ID;
- UNIQUE constraint cho request ID;
- Transaction vừa ghi reservation vừa sửa stock;
- Trả lại kết quả cũ nếu request ID đã xử lý;
- Không tự retry side effects bên ngoài transaction.

**Lock timeout không phải cơ chế exactly-once processing.**

### 17.6. Chọn giá trị timeout theo mục tiêu nghiệp vụ

Không có một con số đúng cho mọi tác vụ:
- UI tương tác có thể ưu tiên fail fast và thông báo thử lại;
- Batch job có thể chờ lâu hơn nếu giảm retries;
- Hot account có thể cần thiết kế partitioning/queue;
- Tác vụ quản trị có thể chấp nhận lock wait dài nhưng cần cancellation/monitoring;
- Job queue có thể dùng SKIP LOCKED nếu được phép chọn item khác.

Hãy đo phân phối lock wait và xác định budget cùng các timeout layers khác, không chọn 5.000 ms chỉ vì dễ nhớ.

### 17.7. Giảm thời gian giữ khóa thường tốt hơn tăng timeout

Các cải tiến có thể có:
1. Không gọi external APIs trong transaction giữ lock.
2. Chỉ đọc những dữ liệu thật sự cần trước khi khóa khi business cho phép.
3. Lấy khóa trễ nhưng vẫn trước thao tác phải bảo vệ.
4. Giữ các transactions nhỏ và commit/rollback sớm.
5. Thống nhất thứ tự lấy nhiều khóa khi có thể để giảm deadlocks.
6. Giảm số rows bị khóa mỗi transaction.
7. Xem xét atomic SQL update thay cho select-lock-update khi phù hợp.
8. Cân nhắc shard/partition hoặc serialization per key ở tầng application khi traffic tập trung.

### 17.8. Không dùng lock timeout để che deadlock

Deadlock là quan hệ chờ vòng giữa các transactions:

~~~text
Tx A giữ Product#1, muốn Product#2
Tx B giữ Product#2, muốn Product#1
             → vòng chờ
~~~

Database có thể phát hiện deadlock và chọn một transaction làm victim, thường trước hoặc độc lập với timeout bạn đặt. Giải pháp có thể là thứ tự khóa nhất quán và transaction ngắn, không chỉ tăng hint lock.timeout.

### 17.9. Một transaction có thể giữ nhiều locks

Khi service khóa Product rồi sau đó sửa Reservation và Account, số locks trong transaction có thể lớn hơn một row Product. Lock timeout ở một thao tác find không tự áp một deadline thống nhất cho mọi lock acquisition phát sinh sau đó ở các SQL statements khác.

Muốn SLA tổng thể, cần transaction/query/DB configuration thích hợp và quan sát toàn bộ đường thực thi.

## 18. Những lỗi thường gặp khi cấu hình lock timeout

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Đặt 5000 nhưng vẫn đợi rất lâu | Provider/dialect bỏ qua positive hint | Kiểm tra SQL, chạy two-connection test |
| Đặt 750 nhưng timeout sau 1 giây | DB/provider làm tròn theo giây | Xác nhận granularity thực |
| Đặt 5 nhưng nghĩ là 5 giây | JPA lock.timeout dùng milliseconds | Dùng 5000 cho mục tiêu 5 s |
| @Transactional(timeout=500) bị hiểu 500 ms | Spring transaction timeout thường theo giây | Phân biệt timeout layers |
| setHint thành công nhưng không NOWAIT | Hint chỉ được ghi nhận, không được thực thi | Quan sát SQL + lock contention thật |
| LockTimeoutException không xuất hiện khi dùng hint 0 | Row không bị khóa hoặc provider bỏ hint | Hai sessions, đúng row, PESSIMISTIC_WRITE |
| Test lock timeout chạy thành công quá nhanh | A chưa lấy khóa hoặc B dùng cùng transaction | Dùng CountDownLatch sau khi A đã khóa |
| Test treo trước SQL | Connection pool chỉ có 1 connection | Tăng pool tối thiểu 2 trong test |
| find trả null | ID không tồn tại | Kiểm tra fixture, không coi null là timeout |
| Query ném NoResultException | Không có row theo WHERE | Xử lý missing data khác timeout |
| Query ném TransactionRequiredException | Không có transaction cho pessimistic lock | Mở transaction thực sự |
| Spring @Transactional không tác dụng | Self-invocation/proxy boundary | Gọi qua Spring bean/proxy phù hợp |
| Locked read làm app giữ lock lâu | Transaction chứa external API hoặc xử lý lâu | Thu ngắn critical section |
| B chờ dù A vừa gọi em.find | A có thể chưa lấy đúng lock hoặc path khác | Kiểm tra SQL/session/transaction |
| PESSIMISTIC_READ không chặn READ khác | Shared/read locks có thể tương thích | Test WRITE vs WRITE cho contention |
| NOWAIT bị hiểu như SKIP LOCKED | Hai semantics khác nhau | Chọn theo business meaning |
| SKIP LOCKED làm bỏ qua job mãi | Starvation/fairness | Theo dõi age, retry/lease |
| Giá trị -2 được coi JPA chuẩn | Provider-specific extension | Dùng API docs và kiểm chứng dialect |
| SQL Server LOCK_TIMEOUT vẫn ảnh hưởng request sau | Session setting trên pooled connection chưa reset | Reset trong finally/cách pool an toàn |
| PostgreSQL báo transaction aborted sau timeout | Statement error gây trạng thái lỗi | Rollback transaction rồi mở mới |
| Bắt LockTimeoutException rồi tiếp tục lưu | Transaction/DB có thể không còn usable | Rollback, retry bằng transaction mới |
| QueryTimeoutException bị coi là lock contention | Query chậm vì I/O/sort/network | Quan sát DB wait events |
| Client timeout nhưng DB vẫn commit | HTTP timeout khác transaction cancel | Idempotency và timeout policy |
| Rollback A rồi B vẫn chờ | Có transaction khác hoặc lock khác giữ | DB blocking sessions/locks diagnostics |
| Hành vi đổi sau upgrade ORM | Dialect/provider/driver semantics đổi | Chạy lại capability tests |
| @Lock đặt trên repository nhưng không hiệu quả | Đường query khác hoặc context sai | Test đúng repository method |
| Lock trên entity đã detached | em.lock yêu cầu managed entity | Load/merge đúng flow |
| Đặt @Version và tưởng đó là timeout | Optimistic check khác pessimistic wait | Dùng LockModeType + hint |
| PESSIMISTIC_WRITE gây deadlock nhiều hơn | Các transactions lấy khóa đảo thứ tự | Thống nhất lock order |
| Query JOIN FETCH có lock SQL lỗi | Database giới hạn FOR UPDATE với joins | Tách query IDs/root lock và fetch |
| Positive lock timeout không bảo vệ SLA | Query/connection/commit vẫn có thể chậm | Tổ chức nhiều timeout layers |
| Rows không đúng tenant bị khóa | Thiếu tenant/security predicate | Bổ sung scope khi query |
| Retry khiến reserve trừ hai lần | Operation không idempotent khi response mất | Request ID + unique constraint |
| Nhiều updates lớn làm nghẽn | Lock scope và transaction dài | Chunking/atomic SQL/batch redesign |

## 19. Tình huống thiết kế: chọn WAIT, NOWAIT hay kỹ thuật khác

### 19.1. Tồn kho nóng trong checkout

Khách A và B cùng mua Product#42, stock=1. Một service read-modify-write có thể dùng PESSIMISTIC_WRITE trong transaction:

~~~java
@Transactional
public void reserveOne(Long productId) {
    Product p = em.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE,
        Map.of("jakarta.persistence.lock.timeout", 500)
    );

    if (p == null) {
        throw new ProductNotFoundException(productId);
    }

    p.reserve(1);
}
~~~

Khi B timeout, API có thể trả trạng thái bận và yêu cầu retry có kiểm soát. Nhưng nếu read-modify-write chỉ liên quan một row và một phép trừ đơn giản, **atomic conditional UPDATE** có thể tiết kiệm một lượt đọc/lấy khóa mà vẫn bảo vệ stock >= 0.

Đừng chọn pessimistic locking chỉ vì có race; hãy so sánh với optimistic version check và atomic DML theo workloads.

### 19.2. Một job queue có nhiều công việc thay thế

Có hàng nghìn Jobs READY và nhiều workers. Nếu Job#1 đang locked, worker khác được phép chọn Job#2. Ở database hỗ trợ tương ứng, SKIP LOCKED có thể phù hợp hơn chờ 500 ms vào Job#1.

Cần thêm:
- Claim status/lease;
- Chuyển READY → RUNNING trong transaction;
- Idempotent processing;
- Xử lý worker crash;
- Retry expiration;
- Starvation monitoring.

**Lock không được giữ suốt thời gian chạy một job nhiều phút** nếu muốn thông lượng cao và tránh long-running transaction. Sử dụng lease/state thay vì giữ DB transaction.

### 19.3. Chuyển tiền giữa hai tài khoản

Khi chuyển tiền từ Account A sang B, giao dịch có thể phải khóa hai rows. Nếu transaction thứ nhất khóa A rồi B, transaction thứ hai khóa B rồi A, có thể deadlock.

Giải pháp thường cân nhắc:
- Thứ tự lấy khóa nhất quán theo account ID;
- Atomic database operations và constraints;
- Transaction ngắn;
- Deadlock retry có kiểm soát;
- Idempotency key cho transfer request;
- Ledger/audit đồng bộ.

Chỉ đặt lock.timeout=5000 không tự loại bỏ deadlocks hoặc bảo đảm số tiền được chuyển đúng một lần.

### 19.4. Một form chỉnh sửa hồ sơ lâu

User mở hồ sơ, sửa 10 phút rồi Save. **Không giữ PESSIMISTIC_WRITE trong suốt thời gian mở form**. Dùng optimistic locking với @Version/ETag và chỉ tạo transaction ngắn tại thời điểm Save là lựa chọn thường hợp lý.

Lock timeout không giúp nếu ứng dụng đã khóa row liên tục theo phiên chỉnh sửa dài.

### 19.5. Báo cáo chỉ đọc

Một endpoint tổng hợp dữ liệu không sửa rows thường không cần PESSIMISTIC_WRITE. Đặt khóa ghi trên hàng triệu rows để “cho chắc dữ liệu” có thể làm contention nghiêm trọng.

Cân nhắc transaction isolation/snapshot consistency, DTO projection hoặc report replica tùy yêu cầu. Không đổi mọi SELECT thành locked SELECT chỉ vì muốn dữ liệu mới nhất.

### 19.6. Admin action cần fail-fast

Một admin đang chạy thao tác chỉnh sửa cấu hình duy nhất; người khác cùng thực hiện hành động trên row đó. Nếu nghiệp vụ cho phép từ chối ngay:
- PESSIMISTIC_WRITE + lock.timeout=0 khi được hỗ trợ;
- Trả phản hồi “Tài nguyên đang được thao tác, hãy thử lại”;
- Không giữ transaction chờ vô hạn;
- Ghi trace để chẩn đoán hot row.

Khi provider không hỗ trợ NOWAIT, dùng fallback DB-specific hoặc protocol quản lý state rõ ràng.

### 19.7. Bulk maintenance job

Một job chạy hàng giờ cập nhật hàng triệu rows. Nếu nó giữ transaction lớn, các OLTP requests có thể timeout dù họ cấu hình lock.timeout đúng.

Nên cân nhắc:
- Chia batch có checkpoint;
- Chạy ngoài giờ cao điểm;
- Giảm lock footprint;
- Thống nhất lock order;
- Sử dụng update theo keyset;
- Đo replication lag/WAL/logging;
- Chấp nhận partial success nếu nghiệp vụ cho phép.

Không lấy việc tăng timeout của các OLTP services làm giải pháp chính cho một maintenance transaction không hợp lý.

### 19.8. Bảng quyết định

| Nhu cầu | Công cụ cân nhắc | Đánh đổi |
|---|---|---|
| Fail fast nếu row đang locked | PESSIMISTIC_WRITE + timeout 0 | Có thể trả lỗi khi contention |
| Chờ một chút để tránh retry | Timeout dương nếu provider hỗ trợ | Không có độ chính xác portable |
| Chờ theo mặc định DB | Không đặt timeout hint | Có thể chờ lâu, cần monitoring |
| Chọn row khác trong queue | SKIP LOCKED trên DB hỗ trợ | Bỏ qua rows, fairness |
| Chỉ ghi nếu stock đủ | Atomic conditional UPDATE | Không có domain callback của entity bulk |
| Stale user edit | @Version/ETag | Cần conflict resolution |
| Nhiều rows khóa theo thứ tự | Deterministic lock order + transaction | Vẫn có deadlock tùy DB |
| Query báo cáo dài | Snapshot isolation/read model | Không khóa ghi tùy tiện |
| Hệ DB không hỗ trợ JPA timeout | Native DB settings/DAO riêng | Phụ thuộc dialect, cần test |
| Multi-DB product | Interface + implementations được kiểm chứng | Chi phí bảo trì các dialect |

## 20. Bài tập thực hành

Những bài tập yêu cầu **viết code, dự đoán hành vi và kiểm tra hỗ trợ**. Không nên trả lời chỉ bằng cách trích lại tên hint; cần giải thích điều gì **được chuẩn JPA yêu cầu** và điều gì **phụ thuộc provider/database**.

### Bài 1. Cấu hình cơ bản

Viết EntityManager.find tìm Product theo ID với:
- LockModeType.PESSIMISTIC_WRITE;
- jakarta.persistence.lock.timeout=1000;
- Transaction đang hoạt động.

Giải thích giá trị 1000 là milliseconds hay seconds.

### Bài 2. NOWAIT

Viết lại bài 1 với timeout=0. Khi một transaction khác đã giữ khóa không tương thích trên row:
- Caller mong muốn gì?
- Có thể nhận exception nào?
- Tại sao không thể khẳng định tất cả providers phải fail chính xác trong 0 ms?

### Bài 3. Không có hint

Bỏ lock timeout nhưng giữ PESSIMISTIC_WRITE. Thời gian chờ được quyết định bởi những tầng nào? Vì sao không nên kết luận “không đặt hint luôn chờ vô hạn”?

### Bài 4. Đơn vị timeout

Cho:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 5);
~~~

Một developer viết tài liệu rằng “wait 5 seconds”. Hãy sửa và đề xuất cách viết nếu muốn yêu cầu khoảng 5 giây.

### Bài 5. Giá trị âm

Một ví dụ online dùng:

~~~java
query.setHint("jakarta.persistence.lock.timeout", -2);
~~~

Hãy giải thích vì sao không được tự nhận đây là portable SKIP LOCKED của JPA và cần kiểm tra provider/version/DB như thế nào.

### Bài 6. EntityManager.lock

Một Product đã managed. Viết em.lock(product, PESSIMISTIC_WRITE, properties). Điều gì xảy ra nếu Product thực ra đã detached? So sánh với find(Class, id, lockMode, props).

### Bài 7. refresh và lock

Viết em.refresh(managed, PESSIMISTIC_WRITE, properties). Giải thích rủi ro nếu managed entity có pending changes chưa flush.

### Bài 8. JPQL TypedQuery

Viết query chọn Product bằng sku, gọi setLockMode(PESSIMISTIC_WRITE) và setHint(lock.timeout=750), rồi getSingleResult. Kể tên các lỗi riêng biệt khi không có row, nhiều rows và không lấy được lock.

### Bài 9. Spring Data @Lock

Tạo repository method find Product theo ID/SKU với **@Lock(PESSIMISTIC_WRITE)**. Chỉ annotation ấy đã đặt wait timeout 500 ms chưa? Nếu chưa, bổ sung cấu hình phù hợp.

### Bài 10. Spring @QueryHints

Viết @QueryHints chứa **jakarta.persistence.QueryHint** name="jakarta.persistence.lock.timeout", value="750". Vì sao value trong annotation là String mà Map hints thường dùng Integer?

### Bài 11. Namespace migration

Dự án từ javax.persistence chuyển sang jakarta.persistence. Hãy liệt kê import và hint names cần đổi. Một string "javax.persistence.lock.timeout" còn sót có thể gây điều gì?

### Bài 12. Lock timeout khác query timeout

Một query không bị lock nhưng mất 10 giây để sort. Lock timeout 500 ms có chắc cắt query sau 500 ms không? Khi nào nên xét jakarta.persistence.query.timeout?

### Bài 13. Transaction timeout đơn vị

So sánh:

~~~java
@Transactional(timeout = 5)
~~~

với:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 5000);
~~~

Cùng con số 5 giây nhưng khác phạm vi thế nào? Chúng có được đảm bảo enforce chính xác như nhau không?

### Bài 14. Pool starvation

Test có connection pool size=1. A giữ một connection và row lock, B cố thực thi query nhưng chờ pool. B có thật sự đang chờ row lock tại database không? Hãy sửa môi trường test.

### Bài 15. Test hai EntityManagers

Thiết kế:
- Transaction A khóa Product#42 và giữ;
- Transaction B ở connection khác thử timeout=0;
- Dùng CountDownLatch để B bắt đầu sau khi A chắc chắn đã lấy lock;
- Đo elapsed time và exception;
- Rollback cả hai trong finally.

Vì sao không dùng cùng EntityManager hoặc cùng transaction?

### Bài 16. Test positive timeout

A giữ khóa 5 giây, B yêu cầu 750 ms. Liệt kê những kết quả quan sát có thể xảy ra và cách phân biệt:
- Hint được thực thi;
- Hint bị bỏ qua;
- Query timeout xảy ra;
- B chờ lấy connection;
- Cả hai không thật sự cạnh tranh cùng row.

### Bài 17. LockTimeoutException và PessimisticLockException

Giải thích khác nhau về scope rollback theo semantics JPA. Tại sao trên PostgreSQL vẫn nên rollback sau một lock timeout dù gặp một exception có nghĩa statement-level rollback?

### Bài 18. PostgreSQL SET LOCAL

Viết SQL trong transaction dùng:

~~~sql
SET LOCAL lock_timeout = '750ms';
~~~

rồi SELECT FOR UPDATE. Tại sao dùng SET LOCAL thích hợp hơn thay session setting lâu dài với pooled connections? Khi statement lỗi, transaction phải làm gì?

### Bài 19. SQL Server LOCK_TIMEOUT

Viết SQL Server SET LOCK_TIMEOUT 750 trước locked read và reset về -1 sau khi hoàn tất. Giải thích vì sao **-1** ở SET LOCK_TIMEOUT không được tự coi là giá trị chuẩn của JPA hint.

### Bài 20. Oracle đơn vị WAIT

Với Oracle SQL FOR UPDATE WAIT 5, đó là năm giây theo syntax minh họa. Nếu JPA hint=5000 ms, provider cần làm gì để dịch tương ứng? Vì sao hint=5 có thể không hợp đồng như mong đợi?

### Bài 21. NOWAIT so với SKIP LOCKED

Có jobs #1, #2, #3 đều READY; #1 locked. So sánh:
- NOWAIT khi cố khóa #1;
- WAIT 750 ms;
- SKIP LOCKED khi worker được phép chọn jobs khác.

Trường hợp nào phù hợp queue worker? Khi nào SKIP LOCKED không an toàn?

### Bài 22. PESSIMISTIC_READ có tương thích với READ khác?

Hai transactions đều yêu cầu PESSIMISTIC_READ. Có chắc transaction B phải chờ A? Tại sao test timeout đáng tin thường dùng hai PESSIMISTIC_WRITE locks trên cùng row?

### Bài 23. SQL logging có giới hạn

Bật Hibernate SQL logs và quan sát lock query. Nếu không thấy NOWAIT, những khả năng nào cần kiểm tra trước khi khẳng định provider không hỗ trợ? Vì sao chỉ thấy SQL text trong một dòng log chưa đủ chứng minh lock scope?

### Bài 24. Deadlock

A khóa Product#1 rồi muốn #2; B khóa #2 rồi muốn #1. Vẽ wait-for graph và đề xuất:
- Thứ tự khóa thống nhất;
- Transaction ngắn;
- Deadlock retry có giới hạn;
- Idempotency;
- Monitoring.

Vì sao chỉ tăng lock timeout không khắc phục nguyên nhân vòng chờ?

### Bài 25. HTTP timeout

Client timeout sau 2 giây, nhưng transaction server có thể commit sau 2,5 giây. Nếu client gửi lại reserve request, hệ thống làm sao tránh trừ tồn kho hai lần?

### Bài 26. Retry policy

Viết pseudo-code retry khi lock timeout:
- Max 3 attempts;
- Rollback mỗi lần thất bại;
- Transaction mới cho mỗi attempt;
- Backoff có jitter;
- Đọc lại Product stock;
- Không retry constraint violations hay stale HTTP forms y nguyên.

### Bài 27. Transaction quá rộng

Một service khóa Product#42 rồi chờ external payment API 10 giây. Hãy thiết kế flow giảm thời gian giữ khóa và đảm bảo trạng thái reservation/payment không mất consistency khi lỗi.

### Bài 28. Xử lý nhiều rows

Query khóa 500 Products trong một transaction với timeout=1000. Có đảm bảo cả query hoàn tất sau đúng 1 giây không? Xác định vấn đề về lock acquisition nhiều rows, SQL execution, driver/DB granularity và transaction duration.

### Bài 29. Capability matrix

Một sản phẩm hỗ trợ PostgreSQL và SQL Server, deploy Hibernate qua nhiều versions. Tạo bảng xác minh:
- Provider/driver/DB version;
- find vs repository @Lock;
- Timeout=0;
- Timeout=750;
- LockTimeoutException/PessimisticLockException;
- SQL evidence;
- Transaction behavior;
- Kết luận supported/unsupported/inconclusive.

### Bài 30. Chọn giải pháp

Cho sáu nghiệp vụ:
1. Checkout cần giảm stock atomically;
2. Form chỉnh sửa sản phẩm offline nhiều phút;
3. Job queue có hàng nghìn items thay thế;
4. Admin action cần fail fast;
5. Batch maintenance update hàng triệu rows;
6. Chuyển tiền giữa hai Accounts.

Chọn giữa pessimistic lock với timeout, optimistic @Version, atomic conditional SQL, SKIP LOCKED và kiến trúc transaction/job phù hợp. Giải thích ưu/nhược và cách test.

### Bài 31. Phân biệt timeout layers từ log

Giả sử một request bị timeout; log có:
- Connection pool pending=20;
- DB không ghi nhận lock wait;
- Query timeout=3000;
- Lock timeout=500.

Hãy giải thích tại sao lỗi có thể ở connection pool, không phải lock wait. Đề xuất metrics cần thu thập và cách test độc lập từng lớp.

### Bài 32. Unsupported provider

Một integration test cho thấy timeout=0 và timeout=750 đều chờ tới lúc holder commit, nhưng SQL có FOR UPDATE không có NOWAIT và DB hỗ trợ NOWAIT.

Hãy phân tích:
- Hint có thể không được dịch sang SQL;
- Khả năng cấu hình dialect sai;
- Cần xác minh phiên bản provider;
- Các fallback database-native;
- Cách báo rõ giới hạn trong tài liệu hệ thống.

Không tự quảng cáo timeout đã được hỗ trợ chỉ vì code setHint chạy qua không exception.

## 21. Bảng tra cứu nhanh

### 21.1. Các API và gợi ý quan trọng

| Nhu cầu | API hoặc cấu hình |
|---|---|
| Yêu cầu pessimistic read lock | LockModeType.PESSIMISTIC_READ |
| Yêu cầu pessimistic write lock | LockModeType.PESSIMISTIC_WRITE |
| Khóa bi quan và buộc tăng version | LockModeType.PESSIMISTIC_FORCE_INCREMENT |
| Hint chuẩn Jakarta | "jakarta.persistence.lock.timeout" |
| Hint cho code JPA cũ | "javax.persistence.lock.timeout" theo API/version cũ |
| Yêu cầu NOWAIT nếu hỗ trợ | lock.timeout = 0 |
| Yêu cầu chờ khoảng 750 ms | lock.timeout = 750 |
| Tìm entity bằng ID với khóa | em.find(Entity.class, id, lockMode, properties) |
| Khóa entity đã managed | em.lock(managed, lockMode, properties) |
| Refresh entity và yêu cầu lock | em.refresh(managed, lockMode, properties) |
| Đặt lock cho TypedQuery | query.setLockMode(PESSIMISTIC_WRITE) |
| Đặt timeout cho query | query.setHint("jakarta.persistence.lock.timeout", 750) |
| Đặt query execution timeout | query.setHint("jakarta.persistence.query.timeout", 3000) |
| Named JPQL query | @NamedQuery với lockMode/hints khi phù hợp |
| Spring Data lock mode | @Lock(PESSIMISTIC_WRITE) |
| Spring Data query hints | @QueryHints({@QueryHint(name=..., value="750")}) |
| Transaction service Spring | @Transactional |
| Spring transaction timeout | @Transactional(timeout=5) (giây, theo manager) |
| Statement-level lock failure | LockTimeoutException |
| Transaction-level pessimistic lock failure | PessimisticLockException |
| Version conflict | OptimisticLockException |
| Không có transaction | TransactionRequiredException |
| SQL PostgreSQL NOWAIT | SELECT ... FOR UPDATE NOWAIT |
| SQL PostgreSQL chờ giới hạn | SET LOCAL lock_timeout = '750ms' |
| SQL Server lock wait | SET LOCK_TIMEOUT 750 |
| Oracle chờ có giới hạn | FOR UPDATE WAIT n |
| Bỏ qua locked rows nếu nghiệp vụ cho phép | SKIP LOCKED theo DB/provider |
| Test contention đúng | 2 EntityManagers + 2 physical connections + 2 transactions |
| Đồng bộ test threads | CountDownLatch/Barrier sau khi A đã lấy khóa |
| Chẩn đoán PostgreSQL | pg_stat_activity, pg_locks, pg_blocking_pids |
| Đánh giá khả năng hỗ trợ | SQL log + elapsed time + exception + DB wait diagnostics |
| Khi hint bị bỏ qua | Fallback dialect-specific hoặc thiết kế concurrency khác |

### 21.2. Bảng phân biệt nhanh các thời gian

| Giá trị | Tầng | Diễn giải |
|---|---|---|
| lock.timeout=0 | JPA | Yêu cầu không chờ khóa nếu hỗ trợ |
| lock.timeout=750 | JPA | Yêu cầu chờ khoảng 750 milliseconds |
| query.timeout=3000 | JPA | Yêu cầu giới hạn thời gian query khoảng 3 seconds |
| @Transactional(timeout=5) | Spring | Transaction timeout 5 seconds theo manager |
| SET LOCAL lock_timeout='750ms' | PostgreSQL | Cấu hình chờ lock trong transaction hiện tại |
| SET LOCK_TIMEOUT 750 | SQL Server | Cấu hình chờ khóa theo session; cần cleanup |
| FOR UPDATE WAIT 5 | Oracle | Cú pháp chờ khoảng 5 seconds theo dialect |
| innodb_lock_wait_timeout=5 | MySQL/InnoDB | Setting thường theo seconds; kiểm tra DB version |

**Không chuyển đổi các giá trị chỉ bằng cách so tên timeout.** Unit, scope, granularity và cơ chế cancel khác nhau.

## 22. Checklist trước khi triển khai lock timeout

### 22.1. Business và transaction

1. **Vì sao cần khóa bi quan?** Có thể dùng @Version hoặc atomic conditional UPDATE không?
2. **Tài nguyên nào được khóa?** Một row Product hay nhiều rows?
3. **Đã chọn lock mode phù hợp chưa?** READ, WRITE, FORCE_INCREMENT có mục đích khác nhau.
4. **Transaction có thực sự active không?** Không bị Spring self-invocation?
5. **Transaction giữ lock trong bao lâu?** Có external HTTP call khi đang giữ lock không?
6. **Có nhiều locks và nguy cơ deadlock không?** Có thứ tự khóa nhất quán không?
7. **Có tenant/authorization predicates phù hợp không?** Không khóa/sửa ngoài phạm vi quyền.
8. **DB constraints có bảo vệ invariant cốt lõi không?** Lock không thay CHECK/UNIQUE/FK.
9. **Nếu API request bị retry, operation có idempotent không?**
10. **Có side effects nào cần thực hiện sau commit hoặc qua outbox không?**

### 22.2. Cấu hình JPA

11. **Sử dụng đúng hint namespace chưa?** jakarta hay javax theo phiên bản?
12. **Timeout được tính bằng milliseconds chưa?** 750 nghĩa khoảng 0,75 giây.
13. **Giá trị 0 có semantics NOWAIT được kiểm chứng chưa?**
14. **Positive wait có được provider/dialect hỗ trợ không?**
15. **Có dùng giá trị âm provider-specific mà chưa ghi rõ extension không?**
16. **Có phân biệt SKIP LOCKED với NOWAIT không?**
17. **Hint được đặt trước khi query thực thi chưa?**
18. **Có đặt setLockMode(PESSIMISTIC_WRITE) cho query không?** Chỉ setHint chưa tự yêu cầu lock.
19. **Nếu dùng em.lock, entity đã managed chưa?**
20. **Nếu dùng @QueryHints trong Spring, có đúng imports/value kiểu String không?**
21. **Nếu dùng @Transactional(timeout), có hiểu đơn vị giây và scope khác không?**
22. **Có query timeout/connection timeout khác ảnh hưởng kết quả không?**
23. **Có JOIN FETCH/pagination khiến locking SQL provider-specific không?**

### 22.3. Kiểm tra hỗ trợ và vận hành

24. **Đã ghi nhận versions của JPA provider, driver và database chưa?**
25. **Đã test đúng môi trường DB mục tiêu chưa?** Không chỉ mock/H2.
26. **Test có hai EntityManagers và hai physical connections không?**
27. **Holder có chắc chắn đã lấy lock trước khi waiter bắt đầu không?**
28. **Test có latches/cleanup/guard để không treo CI không?**
29. **Có thử timeout=0 và positive timeout riêng không?**
30. **Có thử control case không hint để đối chiếu không?**
31. **Có quan sát SQL NOWAIT/WAIT hoặc DB session setting tương ứng không?**
32. **Có đo elapsed time với tolerance hợp lý không?** Không đòi chính xác 1 ms.
33. **Có phân biệt lock wait với connection pool wait không?**
34. **Có phân biệt LockTimeoutException và PessimisticLockException không?**
35. **Có xử lý PostgreSQL transaction aborted hoặc DB error state tương ứng không?**
36. **Sau timeout có rollback và dùng transaction mới không?**
37. **Có giới hạn retry, backoff, jitter và retry budget không?**
38. **Có tránh thay đổi session settings tồn dư trên pooled connections không?**
39. **Có metrics lock wait, deadlock, pool saturation và long transaction không?**
40. **Có kiểm tra lại sau nâng cấp Hibernate/driver/database không?**
41. **Nếu hint không hỗ trợ, đã chọn fallback được kiểm chứng chưa?**
42. **Tài liệu API có phân biệt yêu cầu timeout với bảo đảm SLA không?**

### 22.4. Sơ đồ quyết định

~~~text
Có nhiều transactions cạnh tranh trên dữ liệu?
                     |
              +------+------+
              |             |
             Không          Có
              |             |
        Không cần lock      v
        chỉ vì thói quen   Cần giữ khóa row khi đọc/sửa?
                            |
                  +---------+---------+
                  |                   |
                 Không                Có
                  |                   |
          @Version / CAS        Dùng PESSIMISTIC_WRITE
          hoặc transaction        trong transaction ngắn
          strategy phù hợp                |
                                         v
                            Business cần phản ứng thế nào
                            nếu row đang bị khóa?
                                 |
             +-------------------+-------------------+
             |                   |                   |
         Fail fast         Chờ có giới hạn    Được chọn item khác
             |                   |                   |
         timeout=0           timeout>0           SKIP LOCKED
         (nếu hỗ trợ)        (nếu hỗ trợ)         (DB/provider-specific)
             |                   |                   |
             +-------------------+-------------------+
                                 |
                                 v
                   Test hai transactions thật
                                 |
                 +---------------+---------------+
                 |                               |
          Provider hỗ trợ                 Không hỗ trợ / không rõ
                 |                               |
         Theo dõi latency              SQL DB-native fallback hoặc
         + exceptions                  đổi concurrency design
                 |                               |
                 +---------------+---------------+
                                 |
                                 v
                    Rollback/retry/idempotency
                    và monitor trên production
~~~

## 23. Tổng kết

**Cấu hình gợi ý thời gian chờ khóa** trong Jakarta Persistence được thực hiện chủ yếu bằng hint:

~~~java
"jakarta.persistence.lock.timeout"
~~~

Có thể áp nó tại **EntityManager.find**, **EntityManager.lock**, **EntityManager.refresh**, **TypedQuery.setHint**, named queries hoặc thông qua **Spring Data JPA @Lock + @QueryHints**.

~~~java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE,
    Map.of(
        "jakarta.persistence.lock.timeout",
        750
    )
);
~~~

Cần ghi nhớ bốn nguyên tắc:

1. **Lock timeout là gợi ý về thời gian chờ lấy pessimistic lock**, thông thường tính theo milliseconds. Giá trị 0 hướng tới NOWAIT; giá trị dương hướng tới chờ giới hạn. Không đồng nhất với query/transaction/HTTP timeout.
2. **Không có cam kết portable tuyệt đối về hỗ trợ và độ chính xác.** Provider, JDBC driver, dialect và database có thể giới hạn, làm tròn hoặc bỏ qua hint. Giá trị âm và SKIP LOCKED cần kiểm tra API extension riêng.
3. **Chỉ kiểm tra bằng code setHint là chưa đủ.** Muốn biết hỗ trợ thật, phải dựng hai transactions giữ/cố lấy cùng row trên hai connections, quan sát SQL/DB wait, đo elapsed time và exception, rồi xác nhận transaction cleanup.
4. **Xử lý timeout là một phần của thiết kế concurrency.** Rollback khi phù hợp, retry có giới hạn trong transaction mới, bảo vệ idempotency và giảm thời gian giữ khóa. Khi hint không hỗ trợ, dùng fallback database-specific đã kiểm thử hoặc thiết kế khác thay vì tin rằng cấu hình đã hoạt động.

Sơ đồ ngắn:

~~~text
PESSIMISTIC_WRITE + lock.timeout hint
                   |
                   v
             Provider/dialect
                   |
                   v
            JDBC / Database
                   |
         +---------+----------+
         |                    |
    Lấy được khóa        Không lấy được khóa
         |                    |
    Kiểm tra logic       Timeout/lock exception
    Dirty checking             |
         |                    v
    Commit/rollback       Rollback phù hợp
                              |
                              v
                       Retry có giới hạn
                       hoặc trả lỗi rõ ràng

Cách chứng minh hỗ trợ:
2 independent DB connections + real lock contention
+ SQL evidence + wait duration + exception classification.
~~~

**Nguyên tắc thực hành cuối cùng:** cấu hình timeout phải được xem là **yêu cầu cần xác minh trên môi trường thực**, không phải một tính năng đã được bảo đảm chỉ vì Java code biên dịch thành công. Khi xác định rõ khả năng hỗ trợ, giới hạn transaction và cách ứng dụng phản ứng với contention, pessimistic locking mới phục vụ được tính đúng đắn và độ ổn định của hệ thống JPA.











