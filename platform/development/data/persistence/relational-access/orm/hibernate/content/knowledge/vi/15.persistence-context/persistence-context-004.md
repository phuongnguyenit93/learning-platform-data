# Tải đối tượng, lưu ảnh trạng thái và theo dõi thay đổi trong Hibernate Persistence Context

Khi gọi `entityManager.find(Product.class, 42L)`, Hibernate không chỉ thực hiện một câu `SELECT` rồi chuyển từng cột thành giá trị Java. Với một entity được quản lý, Hibernate còn nhận diện đối tượng bằng khóa định danh, liên kết nó với **persistence context**, giữ các thông tin cần thiết về trạng thái đã tải và theo dõi những thay đổi tiếp theo. Đến thời điểm thích hợp, Hibernate quyết định có cần phát sinh `UPDATE`, `INSERT`, `DELETE` hay SQL phục vụ quan hệ/collection hay không.

Đó là nền tảng của cơ chế **dirty checking**: ứng dụng làm việc với Java objects như đối tượng nghiệp vụ, còn Hibernate thực hiện công việc đối chiếu và đồng bộ thay đổi với database trong phạm vi transaction.

~~~java
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("125.00"));

// Không gọi entityManager.update(product).
// Nếu product là managed và transaction được commit,
// Hibernate có thể tự phát hiện giá trị price đã thay đổi và gửi UPDATE.
~~~

Để dự đoán đúng hành vi, phải phân biệt:

1. **Tải đối tượng (loading/hydration):** lấy dữ liệu hoặc trạng thái từ DB/cache và dựng managed entity.
2. **Ảnh trạng thái đã tải (loaded-state snapshot):** thông tin Hibernate lưu để có cơ sở phát hiện thay đổi, kiểm tra version và lập kế hoạch ghi. Tùy loại thuộc tính và cơ chế enhanced dirty tracking, cách lưu/kiểm tra khác nhau.
3. **Theo dõi thay đổi (dirty checking):** so trạng thái hiện tại hoặc dấu hiệu dirty với trạng thái nền, rồi xác định hành động cần đưa xuống SQL.
4. **Flush:** thực hiện đồng bộ những hành động cần thiết từ persistence context xuống database, **không đồng nghĩa transaction đã commit**.

> **Phạm vi:** Ví dụ sử dụng Jakarta Persistence (`jakarta.persistence`), Hibernate ORM 6.x và cơ chế transaction thông thường. Hibernate 5 dùng `javax.persistence`. Tên class nội bộ, cách giữ snapshot, thời điểm SELECT/UPDATE và SQL chính xác có thể khác theo phiên bản, mapping, Hibernate bytecode enhancement, dialect, fetch plan và database. Các câu SQL trong bài là minh họa về ý nghĩa thao tác, không phải giao kèo Hibernate luôn sinh đúng từng ký tự.

## 1. Persistence context là gì?

**Persistence context** là môi trường quản lý các entity instances mà `EntityManager` hoặc Hibernate `Session` đang theo dõi. Nó thực hiện nhiều chức năng liên quan:

- Nhận diện managed entity bằng entity type và identifier, bảo đảm tính nhất quán của object identity trong context.
- Duy trì state/metadata cần thiết để phát hiện thay đổi và lập các hành động SQL.
- Theo dõi vòng đời transient, managed, detached và removed.
- Quản lý proxies, lazy associations và persistent collections.
- Điều phối các thao tác theo một **unit of work** qua cơ chế flush.

~~~text
Java application
    |
    | find / persist / remove / setters
    v
EntityManager / Session
    |
    +-- Persistence Context
    |     |
    |     +-- identity map:   (Product, 42) -> Product object #A
    |     +-- entity state:   loaded fields / status / version / dirty metadata
    |     +-- collections:    wrappers / snapshots / queued operations
    |     +-- pending work:   inserts, updates, deletes, collection changes
    |
    +-- Flush / SQL generation / JDBC
              |
              v
           Database
~~~

Không nên hình dung persistence context chỉ là một `Map<ID, Object>` đơn giản. Identity map là một phần quan trọng, nhưng Hibernate còn có metadata về trạng thái entity, thuộc tính, collection, proxy, cascade và các hành động cần đồng bộ.

### `Session` và `EntityManager`

Trong Hibernate, `Session` là API native đồng thời thực hiện vai trò persistence context. Trong Jakarta Persistence, `EntityManager` là API chuẩn trừu tượng hóa các khả năng như `find()`, `persist()`, `remove()`, `merge()`, `flush()`, `clear()` và `detach()`.

~~~java
// JPA:
Product product = entityManager.find(Product.class, 42L);

// Hibernate native:
try (Session session = sessionFactory.openSession()) {
    Product other = session.find(Product.class, 42L);
}
~~~

Hai ví dụ dùng hai persistence contexts khác nhau, nên không nên giả định `product == other` dù cùng ID. Nếu ứng dụng dùng Spring/JTA, container hoặc transaction manager có thể quản lý `EntityManager`/`Session`; không tự đóng context thuộc quyền sở hữu của framework.

## 2. Mô hình trạng thái: transient, managed, detached, removed

Dirty checking đối với field thông thường được hiểu rõ nhất khi phân biệt trạng thái entity:

| Trạng thái | Được context quản lý? | Hibernate có tự theo dõi setter để cập nhật row? | Tình huống thường gặp |
|---|---|---|---|
| **Transient/new** | Chưa | Không; cần `persist()` hoặc cascade phù hợp để trở thành managed. | `new Product(...)`. |
| **Managed/persistent** | Có | Có, theo mapping và chế độ quản lý entity. | `find()`, query trả entity, `persist()` thành công. |
| **Detached** | Không trong context hiện tại | Không tự đồng bộ thay đổi của chính instance detached. | Context đóng, `clear()` hoặc `detach()`. |
| **Removed** | Vẫn được context theo dõi ở trạng thái xóa | Dự kiến xóa row khi flush/commit, không phải cập nhật như entity bình thường. | `remove(managedEntity)`. |

~~~mermaid
stateDiagram-v2
    [*] --> Transient: new Product()
    Transient --> Managed: persist()
    Managed --> Detached: detach() / clear() / close()
    Detached --> Managed: merge() tạo hoặc chọn managed copy
    Managed --> Removed: remove()
    Removed --> [*]: DELETE khi flush, commit
~~~

Sơ đồ đơn giản hóa ngữ nghĩa `merge()`: **instance detached ban đầu không biến thành managed**; phương thức trả về một managed instance chứa state được sao chép. Các thao tác remove, persist và rollback có những ngoại lệ/điều kiện theo chuẩn JPA. Mục đích là thấy **dirty checking gắn với managed state trong persistence context**, không gắn vĩnh viễn với một Java object chỉ vì nó có `@Entity`.

### Managed khác “đã commit”

Một entity mới sau `persist()` có thể đã managed và có ID nhưng hàng database chưa được `INSERT`, hoặc đã insert nhưng transaction chưa commit. Tương tự, một entity tải từ DB có thể bị chỉnh trong Java mà chưa gửi `UPDATE`. **Managed** mô tả quan hệ giữa object và persistence context, không phải trạng thái commit của một row.

## 3. Ví dụ xuyên suốt: Product và cơ sở dữ liệu

Một entity có ID được sinh bằng sequence, giá, tên và cột version:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "product")
@SequenceGenerator(
    name = "product_id_gen",
    sequenceName = "product_seq",
    allocationSize = 1
)
public class Product {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_id_gen"
    )
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 80)
    private String sku;

    @Column(name = "display_name", nullable = false, length = 200)
    private String displayName;

    @Column(name = "unit_price", nullable = false, precision = 15, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "active", nullable = false)
    private boolean active;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Product() {}

    public Product(String sku, String displayName, BigDecimal unitPrice) {
        this.sku = Objects.requireNonNull(sku);
        this.displayName = Objects.requireNonNull(displayName);
        setPrice(unitPrice);
        this.active = true;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public BigDecimal getUnitPrice() { return unitPrice; }

    public void rename(String newName) {
        this.displayName = Objects.requireNonNull(newName);
    }

    public void changePrice(BigDecimal newPrice) {
        setPrice(newPrice);
    }

    public void deactivate() {
        this.active = false;
    }

    private void setPrice(BigDecimal price) {
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        this.unitPrice = price;
    }
}
~~~

Schema PostgreSQL tương ứng:

~~~sql
CREATE SEQUENCE product_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO product (
    id, sku, display_name, unit_price, active, version
) VALUES (
    42, 'BK-042', 'Java Book', 100.00, TRUE, 0
);
~~~

Giả định sequence đang được quản lý phù hợp với ID có sẵn (ví dụ đã điều chỉnh để không cấp lại 42). Trong ứng dụng production, migration tool cần quản lý bảng, index và sequence; không nên dựa vào Hibernate tự sửa DDL khi đang có dữ liệu.

## 4. Một lần `find()` diễn ra những gì?

~~~java
Product product = entityManager.find(Product.class, 42L);
~~~

Một luồng khái niệm khi entity chưa có trong persistence context:

1. Hibernate xác định entity mapping `Product` và khóa `42`.
2. Kiểm tra entity có đang managed trong persistence context hay không.
3. Nếu chưa có, tùy cấu hình có thể kiểm tra **second-level cache** trước khi cần database.
4. Khi cần DB, phát sinh `SELECT` theo mapping và fetch plan.
5. JDBC trả dữ liệu cột; Hibernate chuyển giá trị SQL thành các kiểu Java thích hợp (*hydration*).
6. Hibernate tạo hoặc hoàn thiện instance entity, đặt giá trị mapped fields và xác lập trạng thái managed.
7. Provider duy trì entity entry/metadata và thông tin loaded state cần cho các bước kiểm tra thay đổi.

~~~mermaid
flowchart TD
    A["find(Product.class, 42)"] --> B{"Có managed Product/42 trong context?"}
    B -- "Có" --> C["Trả existing managed instance"]
    B -- "Không" --> D{"Cache cấp hai có dữ liệu phù hợp?"}
    D -- "Có" --> E["Hydrate state từ cache"]
    D -- "Không / Không bật" --> F["SELECT dữ liệu từ DB"]
    F --> G["Hydrate Java values"]
    E --> G
    G --> H["Đăng ký managed instance + loaded-state metadata"]
    H --> I["Trả Product"]
~~~

Đây là sơ đồ **khái niệm**. Thứ tự nội bộ có thêm proxy handling, entity loaders, batch fetching, locking và cache rules. Không mặc định mọi `find()` chạy `SELECT` hoặc mọi entity đều dùng second-level cache.

SQL minh họa khi DB thực sự được truy vấn:

~~~sql
SELECT
    p.id,
    p.sku,
    p.display_name,
    p.unit_price,
    p.active,
    p.version
FROM product p
WHERE p.id = ?;
~~~

Sau khi nhận row, Hibernate dựng managed object chứa trạng thái tương ứng và chuẩn bị thông tin để xác định sau này field nào cần ghi lại.

## 5. Identity map: tại sao tải hai lần có thể là cùng object?

~~~java
Product a = entityManager.find(Product.class, 42L);
Product b = entityManager.find(Product.class, 42L);

System.out.println(a == b); // thông thường true trong cùng context
~~~

Hibernate không muốn hai objects managed độc lập cùng đại diện `Product#42` trong **một** persistence context. Nếu có hai managed copies cùng ID nhưng state khác nhau, dirty checking và cập nhật sẽ mơ hồ. Vì thế identity map liên kết entity key với managed instance.

~~~text
Persistence Context của EntityManager A
-------------------------------------
Entity key                Managed object
(Product, 42)     ------> Product instance #A

Lần find thứ nhất ------+
                       +----> Product instance #A
Lần find thứ hai -------+
~~~

Trong cùng context, một HQL query trả entity `Product#42` thường cũng cho cùng managed instance:

~~~java
Product a = entityManager.find(Product.class, 42L);

Product b = entityManager.createQuery(
    "select p from Product p where p.id = :id",
    Product.class
).setParameter("id", 42L)
 .getSingleResult();

System.out.println(a == b); // thông thường true
~~~

HQL query có thể vẫn phát sinh `SELECT`, nhưng khi giải kết quả ORM dùng identity map để nhận diện đối tượng đang managed. Đây là điểm khác biệt giữa **query cache/DB query** và **entity identity trong persistence context**.

### Hai context, hai instances

~~~java
Product first;
Product second;

try (Session s1 = sessionFactory.openSession();
     Session s2 = sessionFactory.openSession()) {
    first = s1.find(Product.class, 42L);
    second = s2.find(Product.class, 42L);
}

System.out.println(first == second); // thông thường false
~~~

Hai instances có thể cùng persistence identity nhưng không cùng Java reference; snapshot của chúng cũng có thể khác nhau do thời điểm tải/transaction isolation. Dirty checking của context A không theo dõi object managed ở context B.

## 6. Loaded-state snapshot là gì?

Để hiểu dirty checking dựa trên snapshot, hình dung sau khi load row `Product#42`, Hibernate có:

~~~text
Managed Java object (hiện tại)          Loaded-state snapshot (nền)
---------------------------------     ---------------------------------
id          = 42                        id/identifier = 42
sku         = "BK-042"                  sku            = "BK-042"
displayName = "Java Book"               displayName    = "Java Book"
unitPrice   = 100.00                    unitPrice      = 100.00
active      = true                      active         = true
version     = 0                         version        = 0
~~~

Snapshot là **biểu diễn internal** của state lúc tải hoặc lúc đồng bộ gần nhất mà Hibernate cần giữ để so sánh. Nó không nhất thiết là một bản sao nguyên object Java, cũng không nhất thiết là một cấu trúc `Map<String, Object>`. Trong Hibernate các metadata như `EntityEntry`/loaded state và các bộ so sánh của mapping góp phần thực hiện việc này; với bytecode enhancement, cách nhận diện field dirty có thể khác với việc đối chiếu toàn bộ snapshot.

### Snapshot có thể là các giá trị đã hydrate

Với các basic types bất biến như `String`, `Long` hoặc `BigDecimal`, việc giữ tham chiếu hoặc giá trị theo type system có thể đủ để so sánh. Với mutable types như `Date`, các mutable embeddables hay custom JSON mapping, Hibernate cần quy tắc sao chép và so sánh phù hợp để biết dữ liệu đã thay đổi. Các chi tiết đó phụ thuộc `JavaType`, `MutabilityPlan`/custom type và bytecode enhancement.

**Đừng suy luận Hibernate luôn `clone()` sâu mọi object.** Việc quản lý state dựa trên metadata của từng thuộc tính, loại dữ liệu và kế hoạch mutability. Một custom mutable type khai báo sai tính bất biến có thể khiến dirty checking không phát hiện được in-place mutation.

### Snapshot không phải lịch sử thay đổi vĩnh viễn

Snapshot là một phần của **unit of work đang hoạt động**, không phải audit log “giá trước – giá sau” tồn tại vĩnh viễn. Khi flush thành công, Hibernate có thể cập nhật state nền hoặc thay đổi metadata; khi context đóng/clear, metadata quản lý cũng bị giải phóng. Muốn lịch sử thay đổi lâu dài cần audit events, audit tables hoặc công cụ như Hibernate Envers theo yêu cầu ứng dụng.

## 7. Dirty checking: điều gì xảy ra khi setter được gọi?

Sau khi tải entity:

~~~java
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("125.00"));
~~~

State Java:

~~~text
Thuộc tính        Snapshot đã tải    Giá trị hiện tại    Có thay đổi?
-------------     ----------------   ----------------    -------------
sku               "BK-042"           "BK-042"            Không
displayName       "Java Book"        "Java Book"         Không
unitPrice         100.00             125.00              Có
active            true               true                Không
version           0                  0                   Chưa đổi trong code
~~~

Khi flush, Hibernate kiểm tra các entity managed thuộc diện cần đồng bộ. Trong cách dirty checking dựa trên snapshot, nó đối chiếu thuộc tính hiện tại với trạng thái nền theo cơ chế equality của từng mapping. Với entity sử dụng **enhanced dirty tracking**, Hibernate có thể biết field đã được đánh dấu thay đổi, giúp giảm chi phí so mọi property trong những trường hợp thích hợp.

Nếu phát hiện `unitPrice` dirty, Hibernate lên lịch xử lý update theo mapping và phiên bản. Một SQL có thể là:

~~~sql
UPDATE product
SET display_name = ?,
    unit_price = ?,
    active = ?,
    sku = ?,
    version = ?
WHERE id = ? AND version = ?;
~~~

Ví dụ này minh họa SQL update có thể chứa nhiều cột **dù chỉ price được sửa**. Hibernate thường tái sử dụng SQL shape cố định theo entity mapping để hỗ trợ statement caching/batching. Nếu bật `@DynamicUpdate`, provider có thể sinh statement chỉ chứa một số cột thực sự dirty. Chi tiết tùy mapping/generated values/optimistic locking.

### Không cần gọi `update()` sau mỗi setter

Với object managed:

~~~java
Product product = entityManager.find(Product.class, 42L);
product.rename("Hibernate Book");
// Không cần entityManager.merge(product) hay session.update(product).
~~~

Hibernate tự thực hiện dirty checking ở ranh giới flush phù hợp. `Session.update()` là API Hibernate lịch sử liên quan reassociation của detached objects, không phải lời gọi cần thực hiện sau mỗi thay đổi managed entity.

### Không phải mọi setter đều tạo SQL UPDATE

~~~java
Product product = entityManager.find(Product.class, 42L);
product.rename("Java Book"); // trùng với giá trị hiện tại trong DB/snapshot
~~~

Khi giá trị cuối cùng bằng snapshot theo comparison semantics và không có trường hợp đặc biệt khác, Hibernate thường không cần update cột này. Tương tự, nếu đặt 125 rồi lại đặt về 100 trước flush, snapshot-based dirty checking có thể thấy state cuối trùng state nền.

Với inline enhanced dirty tracking, các thay đổi qua setter có thể đã đánh dấu field dirty ngay cả khi được gán lại giá trị cũ; Hibernate có các bước tối ưu/kiểm tra tùy implementation. Vì vậy không nên dùng “setter đã chạy” làm bằng chứng chắc chắn có hoặc không có SQL update trong mọi cấu hình.

## 8. Luồng thời gian: từ SELECT đến UPDATE và COMMIT

~~~mermaid
sequenceDiagram
    participant App as Java Service
    participant EM as EntityManager
    participant PC as Persistence Context
    participant DB as Database

    App->>EM: begin transaction / find(Product, 42)
    EM->>PC: lookup entity key
    PC-->>EM: chưa có managed instance
    EM->>DB: SELECT product WHERE id=42
    DB-->>EM: row: price=100, version=0
    EM->>PC: register entity + loaded state
    EM-->>App: managed Product
    App->>App: product.changePrice(125)
    Note over App,PC: Java state đổi; SQL UPDATE có thể chưa chạy
    App->>EM: flush() / commit()
    EM->>PC: dirty checking
    PC-->>EM: price dirty
    EM->>DB: UPDATE product ... WHERE version=0
    DB-->>EM: affected rows = 1
    EM-->>App: flush hoàn thành
    App->>EM: commit transaction
    EM->>DB: COMMIT
~~~

Trình tự minh họa dùng entity đã có trong DB và flush xảy ra trước commit. Trong môi trường Hibernate/JPA, các hành động nội bộ có thể xen kẽ khác, flush có thể xảy ra trước một query, hoặc update có thể được phát sinh theo một thứ tự được tối ưu bởi ActionQueue.

### Ba trạng thái dễ bị nhầm

| Mốc | Trạng thái |
|---|---|
| Sau `changePrice(125)` | Java object có giá mới; DB có thể vẫn đang ở 100. |
| Sau `flush()` thành công | SQL thay đổi đã được gửi theo transaction; DB chưa chắc commit. |
| Sau `commit()` thành công | Transaction đã được xác nhận; các thay đổi thành công trở thành dữ liệu đã commit. |

Nếu transaction rollback sau flush, giá 125 có thể bị hủy ở DB dù Java object trong bộ nhớ vẫn đang giữ 125. Sau rollback, không nên tiếp tục coi state managed context ấy là nguồn dữ liệu đáng tin để ghi tiếp; kết thúc/clear context tùy ownership và tạo unit of work mới.

## 9. Flush là gì, khác commit thế nào?

**Flush** đồng bộ các thay đổi đang chờ trong persistence context thành SQL cần thiết. **Commit** xác nhận transaction của database.

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("125.00"));

entityManager.flush(); // SQL UPDATE có thể chạy tại đây
// Vẫn có thể rollback.
tx.commit();            // Xác nhận transaction.
~~~

Hibernate có thể tự flush khi transaction commit hoặc trước một số query; application không cần gọi `flush()` sau từng setter. Gọi flush quá thường xuyên làm mất cơ hội gom nhiều thay đổi, tăng round trips và giảm batching.

### Flush mode

JPA/Hibernate cung cấp các chế độ điều khiển thời điểm flush. Hai chế độ JPA quan trọng:

- `FlushModeType.AUTO`: provider có trách nhiệm đảm bảo kết quả query phù hợp những cập nhật pending mà query có thể bị ảnh hưởng, và thường flush trước commit. Hibernate có thể quyết định flush trước query liên quan theo query spaces.
- `FlushModeType.COMMIT`: hoãn flush trong các tình huống query theo semantics JPA; mức độ thay đổi của query result khi chưa flush là không xác định theo đặc tả, trong khi các cập nhật vẫn cần được đồng bộ khi commit.

Hibernate native còn các chế độ như `ALWAYS`, `COMMIT` và `MANUAL` tùy API/phiên bản. Không coi `FlushModeType.COMMIT` là cách tắt hoàn toàn dirty checking hoặc bảo đảm mọi query không thấy thay đổi pending trong cùng context.

### AUTO flush trước query

~~~java
tx.begin();
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("125.00"));

long count = entityManager.createQuery(
    "select count(p) from Product p where p.unitPrice >= :min",
    Long.class
).setParameter("min", new BigDecimal("120.00"))
 .getSingleResult();

tx.commit();
~~~

Với flush mode thích hợp, Hibernate có thể flush `UPDATE product` trước `SELECT count` vì query đọc bảng chứa những pending changes liên quan. Nhưng không nên kết luận mọi query gây flush; phụ thuộc flush mode, loại query, native/JPA API, transaction và cách Hibernate xác định overlap.

## 10. Khi flush, Hibernate so sánh state bằng cách nào?

Trong cơ chế snapshot-based thông thường, Hibernate có thể thực hiện một chuỗi logic:

1. Duyệt các entity entries managed cần kiểm tra.
2. Lấy các mapped property values hiện tại.
3. Xác định các property dirtiness theo type/mutability metadata và loaded state.
4. Xác định có cần update entity/table, version và optimistic-locking fields.
5. Tạo/cập nhật hành động mutation (thường qua ActionQueue).
6. Phát sinh SQL thông qua JDBC trong thứ tự phù hợp constraint/cascade/batching.

~~~text
Loaded State         Current State
--------------       --------------
name = "Book"         name = "Book"
price = 100           price = 125
active = true         active = true
      \                 /
       \---- compare --/
              |
          Dirty: price
              |
        UPDATE necessary?
              |
          SQL mutation
~~~

Đây không phải một vòng `equals()` thô cho mọi Java field. Hibernate biết field nào là persistent, type nào dùng converter/custom type, association nào là entity reference, field nào generated/read-only/non-updatable và collection nào có lifecycle riêng. Một property `@Transient` không thuộc dirty checking ORM.

### Ví dụ field không được lưu

~~~java
@Transient
private String formattedPrice;
~~~

Nếu chỉ sửa `formattedPrice`, Hibernate không có lý do ghi cột này vì nó không mapped vào database. Tương tự, biến cục bộ ngoài entity không liên quan dirty checking.

### Chỉ những properties có thể ghi mới tác động SQL

~~~java
@Column(name = "created_at", updatable = false)
private Instant createdAt;
~~~

Nếu field `createdAt` bị thay trong Java, Hibernate sẽ không tự đưa nó vào update cột theo metadata `updatable = false`; nhưng Java object vẫn có thể chứa giá trị mới cho đến khi refresh/reload. **Thay đổi state Java** và **thay đổi được phép ghi DB** là hai việc khác nhau.

## 11. Chỉ định @DynamicUpdate: dirty checking và danh sách cột SQL

Ví dụ:

~~~java
@Entity
@org.hibernate.annotations.DynamicUpdate
@Table(name = "product")
public class ProductDynamic {
    @Id
    private Long id;

    private String displayName;
    private BigDecimal unitPrice;
    private boolean active;
}
~~~

`@DynamicUpdate` là annotation riêng của Hibernate yêu cầu tạo SQL update động theo dirty properties được phát hiện, khi phù hợp. So sánh:

~~~sql
-- Không dùng dynamic update, ví dụ shape cố định:
UPDATE product
SET display_name=?, unit_price=?, active=?, version=?
WHERE id=? AND version=?;

-- Có @DynamicUpdate, khi chỉ unit_price đổi:
UPDATE product
SET unit_price=?, version=?
WHERE id=? AND version=?;
~~~

Các SQL này chỉ để minh họa. SQL thật còn phụ thuộc naming, table mappings, generated fields, lock style và versioning. `@DynamicUpdate` **không phải công tắc bật dirty checking**; entity managed thông thường đã được kiểm tra dirty. Annotation ảnh hưởng việc xây `UPDATE` cho những thuộc tính dirty, không có nghĩa Hibernate ngừng theo dõi các field khác.

### Trade-off

- Update ít cột có thể giảm ghi thừa và thuận lợi trong một số workload nhiều cột lớn.
- Mỗi tổ hợp dirty fields có thể tạo SQL shape khác nhau, làm giảm khả năng tái sử dụng prepared statement và JDBC batch.
- Cần đo trên database/workload cụ thể; không mặc định thêm `@DynamicUpdate` cho mọi entity.

## 12. @Version: snapshot không thay thế optimistic locking

Giả sử hai transactions tải product với version 0:

~~~text
Session A                        Session B
Load price=100, version=0       Load price=100, version=0
Change price=120                Change price=130
Flush/commit                    Flush/commit
~~~

Nếu không có cơ chế concurrency phù hợp, transaction sau có thể ghi đè thay đổi của transaction trước (**lost update**). `@Version` giúp Hibernate thực hiện optimistic locking bằng cách kiểm tra version đã tải:

~~~sql
UPDATE product
SET unit_price = 120.00, version = 1
WHERE id = 42 AND version = 0;
~~~

Nếu transaction A đã commit version 1, SQL của B với `WHERE version=0` thường ảnh hưởng 0 rows. Hibernate sẽ phát hiện và ném optimistic locking exception (loại exception cụ thể tùy API và tình huống).

### Snapshot và version có nhiệm vụ khác nhau

| Thành phần | Vai trò |
|---|---|
| **Loaded snapshot** | Xác định field/property nào đã thay đổi trong context (và hỗ trợ SQL mutation theo mapping). |
| **@Version** | Phát hiện tình huống row đã bị transaction khác cập nhật kể từ version đã tải. |
| **Transaction isolation** | Quy định cách transaction nhìn thay đổi đồng thời của database. |
| **DB constraints** | Bảo vệ uniqueness, FK, check và các invariant mà ORM không thể thay thế. |

Snapshot được giữ **trong persistence context**, không phải khóa đồng bộ toàn database. `@Version` cũng không bảo vệ mọi điều kiện nghiệp vụ ở bảng khác nếu mapping không đưa chúng vào cơ chế version check; những invariant theo tập nhiều rows có thể cần locking/constraint/atomic SQL riêng.

### Version không nhất thiết cập nhật với mọi thay đổi không thuộc entity

Thêm một child vào inverse `@OneToMany(mappedBy = "...")` có thể tác động ở bảng child, còn version của parent có cập nhật hay không phụ thuộc mapping và optimistic locking semantics. Không kết luận “cứ thay đổi trong aggregate là `@Version` trên root luôn tăng” nếu chưa thiết kế và kiểm chứng.

## 13. Dirty checking cho collection phức tạp hơn field đơn

Một parent entity:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

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

@Entity
public class OrderLine {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    void attachTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Code rút gọn chỉ tập trung vào relationship; bản đầy đủ cần constructor không tham số, import và domain invariants phù hợp.

Hibernate thường gắn các wrapper như `PersistentBag`, `PersistentList` hoặc `PersistentSet` (tùy mapping/phiên bản) để theo dõi collection. Nó có thể giữ snapshot về membership/order hoặc cơ chế riêng cho thao tác queued, chứ không chỉ so một biến Java `List` với một snapshot của entity root.

~~~text
Order.lines loaded snapshot: [line #1, line #2]
Order.lines current:         [line #1, line #2, line #3]
                                               + new
~~~

Tùy cascade, ownership, orphanRemoval và trạng thái con, Hibernate có thể:

- Persist con mới.
- Chèn/update FK tại bảng con.
- Xóa child orphan.
- Update bảng collection hoặc cột thứ tự nếu dùng `@OrderColumn`.

### Owning side vẫn quyết định FK

Với `@OneToMany(mappedBy = "order")`, phía `OrderLine.order` là owning side của quan hệ. Thêm child vào list nhưng không gán `line.order = parent` có thể khiến FK không được ghi đúng, dù Hibernate thấy collection Java thay đổi. Vì vậy domain helper phải đồng bộ **cả hai hướng**.

### Collection snapshot không phải object snapshot của từng child

Một child có field `quantity` thay đổi có thể được Hibernate dirty-check như một entity managed riêng. Còn việc thêm/xóa child khỏi collection là thao tác thay đổi quan hệ/collection. Hai nhóm thay đổi có thể phát sinh SQL khác nhau trong cùng flush.

## 14. Lazy loading: chưa tải thì có snapshot gì?

Không phải mọi association được đọc ngay lúc load root:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi `PurchaseOrder` được tải, Hibernate có thể giữ một **lazy collection wrapper chưa initialized**. Nó có metadata đủ để biết owner/key/loader, nhưng chưa nhất thiết có các `OrderLine` concrete objects hay snapshot đầy đủ của collection elements.

~~~text
find(PurchaseOrder, 10)
    |
    +-- PurchaseOrder managed
    +-- lines = lazy collection wrapper (not initialized)

order.getLines().size()
    |
    +-- có thể kích hoạt SELECT order_line WHERE order_id=10
    +-- hydrate OrderLine instances
    +-- thiết lập tracking/snapshot phù hợp
~~~

Hành vi `size()` có thể phụ thuộc extra-lazy collection support/kiểu mapping, không phải lúc nào cũng cần tải toàn bộ elements. Không coi “context đã load parent” là “toàn bộ collection đã được tải và có snapshot từng child”.

### LazyInitializationException

~~~java
PurchaseOrder order;
try (Session session = sessionFactory.openSession()) {
    order = session.find(PurchaseOrder.class, 10L);
}

// Session đã đóng, lines chưa tải:
int count = order.getLines().size();
// Có thể ném LazyInitializationException.
~~~

Để lấy dữ liệu cần cho API, thiết kế fetch plan/projection trong transaction còn hoạt động. Không bật tất cả relationship thành `EAGER` chỉ để tránh lỗi; EAGER có thể làm nhiều SQL hoặc N+1.

## 15. Hibernate proxy và thời điểm thực sự tải entity state

`getReference()` có thể tạo reference/proxy mà chưa query database:

~~~java
Product ref = entityManager.getReference(Product.class, 42L);
// Hibernate có thể chưa SELECT product ở bước này.

String name = ref.getDisplayName();
// Truy cập thuộc tính có thể làm proxy initialize và SELECT.
~~~

Đừng giả định tại thời điểm `getReference()` trả về đã có đầy đủ entity state/snapshot. Proxy có thể chỉ biết entity type và identifier, còn việc initialize sẽ diễn ra khi dữ liệu thực sự được cần.

Một số mapping dùng bytecode enhancement thay vì proxy truyền thống hoặc có entity already managed, khiến hành vi khác. `getReference()` cũng có thể không xác minh row tồn tại ngay; lỗi có thể xuất hiện khi proxy được truy cập.

### Bản chất của proxy khác bản chất dirty checking

Proxy giải quyết **khi nào cần tải state**. Dirty checking giải quyết **làm sao phát hiện state của managed entity đã thay đổi**. Hai cơ chế liên hệ nhau nhưng không giống nhau. Nếu proxy chưa initialized và không có field thay đổi, Hibernate không nhất thiết phải tải toàn bộ entity chỉ để flush.

### Basic fields có thể LAZY không?

~~~java
@Basic(fetch = FetchType.LAZY)
@Column(name = "large_description")
private String largeDescription;
~~~

`FetchType.LAZY` trên basic field là hint theo JPA; Hibernate có thể cần bytecode enhancement hoặc cách mapping đặc thù để load thuộc tính cơ bản trễ. Do vậy state snapshot/tracking cho field chưa tải có các marker/methods riêng, không nên suy luận Hibernate đã copy mọi cột ngay lúc root entity được truy vấn.

## 16. Dirty checking dựa trên snapshot và bytecode enhancement

Hibernate thường dùng **diff-based dirty checking**: tại flush so state managed hiện tại với trạng thái đã tải. Với entity nhiều field, việc so tất cả thuộc tính trên nhiều managed entities có chi phí CPU/bộ nhớ.

Hibernate cũng hỗ trợ **bytecode enhancement** để thêm khả năng theo dõi những thuộc tính đã thay đổi trực tiếp vào class. Khi được cấu hình/hỗ trợ, enhanced entity có thể ghi nhận field assignment và giúp provider biết những field nào là ứng viên dirty:

~~~text
Không enhancement:
  flush -> lấy state hiện tại -> so với loaded state -> tìm dirty fields

Có enhancement phù hợp:
  setter / field write -> dấu hiệu dirty được ghi nhận
  flush -> đọc metadata dirty và xử lý tiếp theo theo mapping
~~~

### Không đồng nhất mọi thay đổi với setter assignment

Đối với mutable object:

~~~java
product.getTags().add("new");          // collection mutation
product.getLastCheckedAt().setTime(0); // mutable Date mutation
~~~

Không phải mọi thay đổi đều qua setter của entity. Enhanced dirty tracking chỉ quan sát được những kiểu thao tác mà instrumentation và provider hỗ trợ; mutable basic types, custom types, embeddables và collection wrappers vẫn cần semantics snapshot/mutability phù hợp.

### Có phải bytecode enhancement loại bỏ toàn bộ snapshot?

Không nên khẳng định như vậy. Hibernate còn cần nhiều thông tin phục vụ versioning, loading, optimistic locking, collections, loaded associations, callbacks và internal state management. Enhanced dirty tracking **có thể giảm công việc so sánh đối với một số entity/properties**, nhưng không biến persistence context thành một tập các setters mà không còn snapshot hay metadata.

### Cách bật enhancement

Hibernate có các cách bytecode enhancement thông qua build-time plugin hoặc runtime mechanisms theo phiên bản và framework. Cú pháp cấu hình/những tính năng được enhancement thực tế thay đổi theo Hibernate release, nên cần đọc tài liệu của đúng Hibernate ORM đang dùng. Không kết luận chỉ vì application chạy Hibernate 6 là mọi entity đều được enhanced theo cùng một cách.

## 17. Mutable basic types và custom value types

Một field Java có thể chứa object mutable:

~~~java
@Temporal(TemporalType.TIMESTAMP)
private java.util.Date lastCheckedAt;
~~~

Nếu code sửa in place:

~~~java
product.getLastCheckedAt().setTime(System.currentTimeMillis());
~~~

Dirty checking chỉ hoạt động đúng khi Hibernate hiểu loại dữ liệu này có thể thay đổi và dùng cách snapshot/copy/compare phù hợp. Nếu một custom `UserType` hoặc JSON type bị khai báo nhầm là immutable, Hibernate có thể dùng cùng reference hoặc không phát hiện mutation như người viết code kỳ vọng.

### So sánh bằng giá trị không luôn giống so Java reference

Một số types có quy tắc equality đặc biệt. Ví dụ:

~~~java
new BigDecimal("10.0").equals(new BigDecimal("10.00")) // false
new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0 // true
~~~

Hibernate dùng type system và mapping để quyết định value equality/dirty semantics; không nên tự suy luận mọi trường hợp từ `==` hoặc `Object.equals()` của field. Với tiền tệ, nên chuẩn hóa precision/scale theo domain/schema để tránh ghi thừa hoặc sai lệch định dạng.

### JSON hoặc mutable embeddable

~~~java
@Embeddable
public class ProductDimensions {
    private BigDecimal width;
    private BigDecimal height;
    // ...
}
~~~

Khi các field embeddable thay đổi, Hibernate cần theo dõi state embedded vào entity owner. Với JSON columns/custom converters, việc gọi `product.getSettings().put(...)` có được nhận biết hay không phụ thuộc mutability metadata và implementation. Một cách an toàn hơn trong nhiều trường hợp là tạo **immutable value object** mới rồi thay field mapped thông qua domain method, nhưng điều đó vẫn cần mapping hỗ trợ đúng.

## 18. Read-only entity: tải được không đồng nghĩa sẽ dirty-check để UPDATE

Có những đơn vị công việc chỉ đọc:

~~~java
@Transactional(readOnly = true)
public ProductView viewProduct(long id) {
    Product product = entityManager.find(Product.class, id);
    return new ProductView(
        product.getId(),
        product.getDisplayName(),
        product.getUnitPrice()
    );
}
~~~

Trong Spring, `@Transactional(readOnly = true)` là một gợi ý cho transaction manager/provider và có thể điều chỉnh flush mode hoặc read-only hints. Nó **không phải bảo đảm cứng ở database** rằng mọi nỗ lực ghi đều bị chặn trong mọi cấu hình; đặc biệt không nên dùng annotation này thay kiểm soát quyền/constraint.

Hibernate native còn có tùy chọn read-only trên Session/entity/query:

~~~java
try (Session session = sessionFactory.openSession()) {
    session.setDefaultReadOnly(true);
    Product product = session.find(Product.class, 42L);
    // product được load theo chế độ read-only mặc định phù hợp.
}
~~~

Đối với Hibernate read-only entity theo semantics thích hợp, provider có thể bỏ snapshot phục vụ kiểm tra dirty của các simple properties hoặc không dirty-check các field đó, giảm overhead. Nhưng **read-only entity không nhất thiết có nghĩa mọi collection association hoặc cascade đều không gây bất kỳ SQL nào**, và thay đổi trong Java object vẫn có thể xảy ra mà không được persist.

### @Immutable

~~~java
@Entity
@org.hibernate.annotations.Immutable
@Table(name = "country_reference")
public class CountryReference {
    @Id
    private String code;

    @Column(name = "display_name")
    private String displayName;
}
~~~

`@Immutable` là annotation riêng của Hibernate biểu đạt rằng entity không được update theo cơ chế thông thường. Hibernate có thể tối ưu snapshot/dirty checking cho entity immutable; nếu application sửa field Java, đừng kỳ vọng Hibernate ghi `UPDATE`. Dùng khi domain thật sự không cho phép sửa entity, không dùng để “cải thiện hiệu năng” rồi lại sửa dữ liệu bằng entity methods.

### Read-only khác detached

Read-only entity vẫn có thể **gắn với persistence context** và được tra cứu theo identity; detached object thì không còn thuộc context. Không dùng `Session.setDefaultReadOnly(true)` như cách “detach” mọi object.

## 19. Detach, clear, close: snapshot và dirty checking đi đâu?

~~~java
Product product = entityManager.find(Product.class, 42L);
entityManager.detach(product);
product.changePrice(new BigDecimal("140.00"));
~~~

Sau `detach(product)`, context hiện tại không còn theo dõi dirty changes của instance này. Nếu sau đó commit transaction mà không có thao tác reattach/merge thích hợp, giá 140 của detached instance không tự được ghi vào DB.

Các thao tác:

| Thao tác | Phạm vi | Hệ quả chính |
|---|---|---|
| `detach(entity)` | Một entity (và cascade DETACH nếu khai báo) | Đối tượng không còn managed trong context hiện tại. |
| `clear()` | Toàn persistence context | Mọi managed entities bị tách; pending changes chưa flush có thể không được ghi. |
| `close()` | EntityManager/Session application-managed | Giải phóng context/tài nguyên, các instance trở thành detached. |
| `flush()` | Đồng bộ pending changes | Gửi SQL, nhưng vẫn giữ entities managed; không detach. |
| `refresh(entity)` | Managed entity được chỉ định | Lấy lại state từ DB và thay state trong context theo semantics refresh. |

### Cẩn thận với `clear()` trước flush

~~~java
tx.begin();
Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("150.00"));

entityManager.clear();
tx.commit();
~~~

Nếu không có flush trước khi clear, thay đổi pending có thể bị loại khỏi unit of work. Sau `clear()`, `product` là detached; Hibernate không còn theo dõi setter hay state hiện tại của nó trong context.

### Flush rồi clear có tương đương commit không?

Không:

~~~java
product.changePrice(new BigDecimal("150.00"));
entityManager.flush();  // SQL UPDATE đã được gửi trong transaction
entityManager.clear();  // detach tất cả
tx.rollback();          // DB rollback update
~~~

Clear chỉ tác động state đang quản lý trong Java, không commit transaction. Sau rollback, không nên tiếp tục tin snapshot cũ hoặc giả định application heap tự trở về giá đã commit.

## 20. Merge: snapshot nào được dùng sau khi detached object quay lại?

Một entity detached có thể được gửi qua nhiều tầng xử lý:

~~~java
Product detached = loadProductFromPreviousSession(42L);
detached.changePrice(new BigDecimal("160.00"));

EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product managed = entityManager.merge(detached);
tx.commit();
~~~

`merge()` trả về một **managed instance**. Hibernate sao chép state từ detached object vào managed instance tương ứng (có thể load row hiện tại hoặc tái sử dụng instance đã managed). Dirty checking của context sau đó dựa trên state/metadata của **managed instance**, không phải tiếp tục theo dõi setter của detached object ban đầu.

~~~java
System.out.println(detached == managed); // thường false
System.out.println(
    detached.getId().equals(managed.getId())
); // cùng persistence identity nếu row tồn tại
~~~

Sau merge:

~~~java
managed.changePrice(new BigDecimal("170.00"));  // managed, được theo dõi
detached.changePrice(new BigDecimal("180.00")); // detached, không tự theo dõi
~~~

Với DTO từ API, thường an toàn hơn là **tải entity managed hiện tại rồi áp dụng từng thay đổi có chủ đích** thay vì merge nguyên một detached graph từ client. Điều này tránh vô tình sao chép field null/stale, cascade qua relationship ngoài ý muốn và xóa orphan do collection thiếu phần tử.

### Có nhiều bản detached cùng ID thì sao?

Nếu một graph chứa nhiều detached copies của cùng entity identity với state khác nhau, merge có thể gặp lỗi hoặc hành vi phụ thuộc chính sách Hibernate về entity copy observer. Không cố giải quyết xung đột bằng cách “copy object cuối thắng” mà không có quy tắc nghiệp vụ. Sử dụng version/concurrency control và một nguồn thay đổi được kiểm soát.

## 21. Refresh: DB có thể ghi đè thay đổi chưa flush trong Java

~~~java
tx.begin();

Product product = entityManager.find(Product.class, 42L);
product.changePrice(new BigDecimal("175.00"));

entityManager.refresh(product);

System.out.println(product.getUnitPrice());
// Giá có thể trở về giá DB được đọc lại.

tx.commit();
~~~

`refresh()` yêu cầu Hibernate lấy lại state từ database cho managed entity theo mapping/fetch behavior, thay state hiện có. Nó hữu ích khi cần đồng bộ lại dữ liệu bị cập nhật ngoài context, nhưng **có thể làm mất những thay đổi chưa flush** của object.

Phân biệt:

- `refresh`: tái tải managed entity từ DB, cập nhật state của object hiện có.
- `clear`: bỏ quản lý tất cả entities, không tự reload.
- `merge`: sao chép state từ detached object vào managed instance.
- `flush`: đẩy thay đổi từ context xuống DB, không phải làm mới từ DB.

### Với transaction isolation và cache

`refresh()` không đảm bảo “nhìn thấy giá trị mới nhất toàn hệ thống” nếu isolation của transaction giữ snapshot riêng hoặc concurrent transaction chưa commit. Có thể cần kết thúc transaction và mở transaction mới để quan sát trạng thái mới nhất, tùy DB isolation và nghiệp vụ.

## 22. Query bình thường không nhất thiết cập nhật managed object đã có

Giả sử `Product#42` đang managed, giá 100. Transaction khác commit giá 120. Nếu context hiện tại tiếp tục chạy:

~~~java
Product first = entityManager.find(Product.class, 42L);

List<Product> rows = entityManager.createQuery(
    "select p from Product p where p.id = :id",
    Product.class
).setParameter("id", 42L)
 .getResultList();
~~~

Hibernate có thể chạy SQL query, nhưng khi row được materialize, identity map tìm thấy entity managed đã có và thường không ghi đè tùy tiện state của nó bằng dữ liệu query mới. Kết quả query có thể vẫn là reference `first` với snapshot cũ trong context. **Thực hiện HQL query không phải một lệnh refresh tự động cho managed objects**.

Đây là một nguyên nhân khiến developer ngạc nhiên khi SQL log thấy `SELECT` nhưng getter vẫn trả giá trước đó. Để quyết định hành động phải xem:

- Persistence context có entity managed trước query không?
- Transaction isolation cho phép nhìn phiên bản DB nào?
- Entity có pending changes trong Java không?
- Có cần `refresh`, detach/clear rồi load lại hoặc transaction mới không?

Không giải quyết bằng cách tùy ý `clear()` giữa một transaction có pending writes; có thể làm mất thay đổi.

## 23. Bulk HQL/JPQL UPDATE bỏ qua dirty checking theo từng managed entity

Một khác biệt rất quan trọng:

~~~java
int count = entityManager.createQuery(
    """
    update Product p
    set p.active = false
    where p.unitPrice <= :limit
    """
).setParameter("limit", new BigDecimal("10.00"))
 .executeUpdate();
~~~

Bulk update là một lệnh dữ liệu mức query, được Hibernate dịch thành SQL phù hợp. Nó **không lần lượt gọi `product.deactivate()` trên từng managed entity** và không làm dirty checking/callbacks/version update giống việc sửa từng entity bình thường.

Nếu context hiện có:

~~~java
Product managed = entityManager.find(Product.class, 42L);
// active = true trong Java

entityManager.createQuery(
    "update Product p set p.active = false where p.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

// managed.active có thể vẫn true vì context chưa được đồng bộ lại.
~~~

SQL database có thể đã thay đổi row, nhưng managed object vẫn giữ state/snapshot cũ. Đây là **stale persistence context**.

### Cách quản lý sau bulk DML

Một cách có chủ đích:

1. Flush những thay đổi pending cần giữ trước bulk DML.
2. Thực hiện bulk `UPDATE`/`DELETE` trong transaction phù hợp.
3. `clear()` hoặc `refresh()` những entity bị ảnh hưởng trước khi dựa vào state của chúng, khi nghiệp vụ cho phép.
4. Cân nhắc invalidation/cache và versioning của các entity bị tác động.

~~~java
entityManager.flush();

int affected = entityManager.createQuery(
    "update Product p set p.active = false where p.id = :id"
).setParameter("id", 42L)
 .executeUpdate();

entityManager.clear();
Product reloaded = entityManager.find(Product.class, 42L);
~~~

**Không có công thức “luôn clear sau mọi bulk DML”** cho mọi hệ thống: clear có thể loại bỏ managed changes chưa flush và làm detached các object mà code sau vẫn dùng. Cần thiết kế transaction boundary và dữ liệu được cập nhật chính xác.

### Bulk DML và @Version

JPA bulk update thông thường không tự tăng/check version theo cách dirty checking từng managed entity có `@Version`. Hibernate HQL có cú pháp/khả năng đặc biệt như versioned update trong những trường hợp phù hợp, nhưng không nên coi bulk DML mặc nhiên tương đương với việc sửa từng managed entity. Nếu cần optimistic-locking semantics, hãy thiết kế explicit predicates/version handling và kiểm chứng SQL.

## 24. Native SQL và thay đổi ngoài Hibernate có thể làm snapshot cũ

Native SQL:

~~~java
entityManager.createNativeQuery(
    "update product set unit_price = 200.00 where id = 42"
).executeUpdate();
~~~

Hoặc một application khác update DB có thể khiến entity managed trong context hiện tại không còn phản ánh giá trị DB. Hibernate không tự biết mọi thay đổi bên ngoài persistence context để sửa state và snapshot đã tải.

Ví dụ:

~~~text
Context A:
  managed Product/42: price=100, loaded snapshot=100

External SQL:
  UPDATE product SET price=200 WHERE id=42

Context A:
  object vẫn có price=100 (nếu chưa refresh)
~~~

Nếu context A sau đó chỉnh một field khác và Hibernate phát sinh UPDATE nhiều cột, có nguy cơ ghi đè giá 200 bằng state cũ nếu không có optimistic locking, SQL dynamics hoặc concurrency control phù hợp. Với `@Version`, external writer cũng cần tuân thủ version protocol nếu muốn ORM phát hiện xung đột; update SQL bỏ qua version có thể phá vỡ giả định optimistic locking.

### Cache cấp hai còn có thể cũ

Nếu second-level cache được bật, bulk/native/external updates cần có chính sách vô hiệu hóa cache phù hợp. Hibernate có thể quản lý một số invalidation cho query spaces đã biết, nhưng không thể tự phát hiện mọi lệnh SQL của công cụ ngoài. Không dùng cache như thay thế transaction isolation/versioning.

## 25. First-level cache, second-level cache và query cache khác nhau

| Cơ chế | Phạm vi | Tác động với load và dirty checking |
|---|---|---|
| **Persistence context / first-level cache** | Một `Session`/`EntityManager` | Giữ managed instances, entity identity và metadata state; dirty checking vận hành ở đây. |
| **Second-level cache** | Có thể chia sẻ giữa nhiều sessions qua SessionFactory/provider | Lưu state entity/collections theo cấu hình để giảm đọc DB; mỗi context vẫn tạo/quản lý các instances riêng. |
| **Query cache** | Kết quả query theo cơ chế cache Hibernate | Có thể lưu identifiers/scalars/query result metadata; không thay thế first-level managed objects và dirty checking. |

Một object `Product` trong Session A và object `Product` trong Session B có thể được hydrate từ cùng cached state nhưng vẫn là **hai Java instances khác nhau**. State snapshot của mỗi context liên quan đến dữ liệu được load vào context ở thời điểm của nó.

### Cache hit không đồng nghĩa dữ liệu “bất biến”

Nếu application yêu cầu strong freshness, cần phối hợp cache concurrency strategy, DB transaction isolation và cache invalidation. Dirty checking vẫn dựa trên state mà context đang quản lý, chứ không tự đọc lại database ở mọi flush chỉ để xác nhận mọi field không thay đổi.

## 26. StatelessSession: khi không có cơ chế quản lý state thông thường

Hibernate cung cấp `StatelessSession` cho một số trường hợp thao tác dữ liệu mà không có persistence context giống `Session` thông thường. Cơ chế này không có automatic dirty checking của managed entities, không có first-level entity cache theo kiểu stateful session và các quy tắc cascade/collection handling khác đáng kể.

~~~java
try (StatelessSession session = sessionFactory.openStatelessSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Product product = session.get(Product.class, 42L);
        product.changePrice(new BigDecimal("210.00"));
        session.update(product); // thao tác ghi phải được yêu cầu tường minh
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
~~~

Ví dụ minh họa cú pháp Hibernate native theo API phiên bản phù hợp. `StatelessSession` là công cụ khác `EntityManager`/stateful `Session`; không tự giả định cascade, lazy collection, events, write-behind và batching hoạt động giống hệt nhau.

**Ý nghĩa để so sánh:** trong stateful session, `product.changePrice(...)` trên managed object đủ để được dirty checking khi flush. Trong stateless session, bạn phải gọi operation explicit phù hợp để ghi thay đổi.

### Khi nào cân nhắc StatelessSession?

Các bài toán batch/ETL hoặc xử lý dữ liệu đơn giản với yêu cầu thấp về entity graph, cascade và persistence context có thể cân nhắc. Nhưng phải thiết kế rõ các thao tác insert/update/delete, transaction, cache, version và cách đồng bộ dữ liệu. Không sử dụng stateless chỉ vì muốn “tắt dirty checking cho nhanh” mà vẫn kỳ vọng toàn bộ semantics managed entity.

## 27. Hạn chế bộ nhớ khi tải rất nhiều entity

Identity map và snapshots có chi phí bộ nhớ. Nếu tải 100.000 products trong một persistence context:

~~~java
List<Product> products = entityManager.createQuery(
    "select p from Product p",
    Product.class
).getResultList();
~~~

ứng dụng có thể giữ nhiều Java entity instances, loaded state, association wrappers và metadata cho đến khi context được clear/close. Dirty checking khi flush cũng có thể phải xử lý số lượng managed entities lớn hơn.

### Xử lý theo lô

Một mẫu cho batch update:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

for (int i = 0; i < productIds.size(); i++) {
    Product product = entityManager.find(
        Product.class, productIds.get(i)
    );
    product.deactivate();

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
tx.commit();
~~~

Ý nghĩa:

- `flush()` ghi pending changes theo transaction.
- `clear()` giải phóng managed references/metadata của context, giảm tăng trưởng bộ nhớ.
- Những entity cũ sau clear trở thành detached; không tiếp tục sửa chúng với kỳ vọng auto dirty checking.

Nếu xử lý cực nhiều dữ liệu, một transaction duy nhất dài có thể gây locking/undo log lớn; cần thiết kế batch transactions/chunk commit phù hợp business atomicity. Đồng thời xem query paging/streaming, connection pool và JDBC batch settings.

### Đừng clear trước khi flush

~~~java
product.deactivate();
entityManager.clear(); // pending change có thể bị bỏ!
~~~

Đây là lỗi dễ mắc khi cố tối ưu memory. Nếu có cascade/collection graph phức tạp, flush/clear giữa chừng cần xem xét ownership và các object vẫn cần managed ở những bước tiếp theo.

## 28. Phát hiện thay đổi không đồng nghĩa lưu từng setter ngay lập tức

Một code path:

~~~java
Product product = entityManager.find(Product.class, 42L);

product.rename("New title");
product.changePrice(new BigDecimal("225.00"));
product.deactivate();
~~~

Hibernate không bắt buộc gửi ba `UPDATE` riêng ngay sau ba setter. Khi dirty checking tại flush, provider thường tạo **một entity UPDATE** phù hợp với state cuối và mapping:

~~~sql
UPDATE product
SET display_name=?, unit_price=?, active=?, version=?
WHERE id=? AND version=?;
~~~

Điều này là một phần của **transactional write-behind** và unit of work. Hibernate có thể gom cập nhật vào SQL action rồi execute theo thứ tự/batching phù hợp.

### Có thể có UPDATE ngay giữa code không?

Có những hoàn cảnh làm SQL chạy sớm hơn commit, như explicit `flush()`, query cần AUTO flush, lock/ID generation/callbacks hoặc các API đặc thù. Không dựa vào “chỉ có SQL khi commit” như quy tắc tuyệt đối.

### Đổi rồi đổi lại

~~~java
product.changePrice(new BigDecimal("225.00"));
product.changePrice(new BigDecimal("100.00"));
~~~

Nếu snapshot ban đầu là 100 và không có property khác dirty, snapshot-based dirty checking thường thấy state cuối không khác và có thể không cập nhật product. Cơ chế enhanced dirty flags, version, callbacks và custom types có thể dẫn tới biến thể. Nguyên tắc là **ORM quan tâm state cần đồng bộ**, không log tất cả setter invocations theo thứ tự như event sourcing.

## 29. Transaction ranh giới và lỗi flush

Một đơn vị công việc nên xử lý exception và rollback rõ:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    Product product = entityManager.find(Product.class, 42L);
    if (product == null) {
        throw new IllegalArgumentException("Product not found");
    }

    product.changePrice(new BigDecimal("250.00"));
    entityManager.flush();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }
    throw failure;
}
~~~

Ví dụ dùng application-managed `RESOURCE_LOCAL` EntityManager. Với Spring `@Transactional` hoặc JTA/container-managed transaction, framework sở hữu transaction; không tự dùng `getTransaction()`/`commit()`/`rollback()` như trên.

Nếu `flush()` gặp constraint violation/optimistic-locking error, transaction thường cần rollback và persistence context có thể không còn an toàn để tiếp tục công việc. Không cố sửa vài field rồi commit tiếp trên cùng Session vừa gặp SQL exception; tạo unit of work mới sau rollback theo framework.

### Lỗi commit có thể khác lỗi flush

Database có thể kiểm tra deferred constraints khi commit, hoặc mạng bị lỗi khiến client không biết chắc commit đã thành công chưa. Vì vậy `flush()` thành công **không bảo đảm** transaction commit sẽ thành công. Những nghiệp vụ nhạy cảm cần idempotency/recovery hoặc xác minh outcome theo transaction semantics.

## 30. Theo dõi bằng SQL logging và statistics

Trong môi trường thử nghiệm với Spring Boot + Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger bind parameters của Hibernate 5 khác Hibernate 6; không giữ TRACE bind values ở production nếu có dữ liệu nhạy cảm.

Có thể bật:

~~~properties
hibernate.generate_statistics=true
~~~

để lấy những thống kê Hibernate hỗ trợ như số entity loads, fetches, updates, flushes và statements (các counters cụ thể khác theo phiên bản). Có thể xem qua `SessionFactory.getStatistics()` trong Hibernate native hoặc công cụ monitoring framework.

### Thực hành quan sát

1. Bật log SQL trong môi trường học tập.
2. Trong một transaction, `find(Product.class, id)` và xem `SELECT`.
3. Gọi lại `find` cùng ID và quan sát thường không thêm `SELECT` nhờ first-level cache.
4. Đổi một field managed, nhưng chưa flush; quan sát chưa nhất thiết có `UPDATE`.
5. Gọi `flush()`, quan sát SQL update/affected row và version.
6. Gọi `clear()` rồi find lại; có thể SELECT/second-level cache load mới.
7. Thực hiện `refresh()`, `merge()` và bulk update để thấy sự khác nhau giữa quản lý state và thay đổi SQL trực tiếp.

Không nên suy luận số JDBC round trips hoàn toàn từ số dòng log SQL: driver có thể batch statements, còn statement logging và actual network activity là hai tầng khác nhau.

## 31. Debug tại sao Hibernate không UPDATE?

Các nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách xem xét |
|---|---|---|
| Sửa field nhưng không có UPDATE | Entity đã detached, clear/close context, hoặc transaction không flush/commit | Kiểm tra `entityManager.contains(entity)`, transaction và flush mode. |
| Sửa field nhưng giá DB không đổi | Field là `@Transient`, `updatable=false`, entity read-only/`@Immutable` | Kiểm tra mapping và read-only flags. |
| Không có UPDATE khi đặt cùng giá trị | Snapshot hiện tại giống state cuối | Quan sát loaded/current values và SQL tại flush. |
| UPDATE đã chạy nhưng thay đổi không tồn tại sau đó | Transaction rollback/commit fail | Kiểm tra logs transaction và exception. |
| Mutable JSON/Date đổi nhưng không phát hiện | Custom mutability metadata/dirty tracking không phù hợp | Xem type mapping, snapshot copying và enhanced tracking. |
| Đổi child collection nhưng FK không đổi | Chỉ sửa inverse `@OneToMany(mappedBy)`, chưa sửa owning `@ManyToOne` | Đồng bộ hai hướng qua domain helper. |
| HQL bulk update xong getter vẫn trả giá cũ | Managed context stale | Clear/refresh/reload theo transaction và business requirements. |
| UPDATE xảy ra dù chỉ sửa một field | SQL shape không dùng `@DynamicUpdate`, hoặc version/other generated fields | Đọc SQL và mapping; dirty checking vẫn có thể chỉ thấy một field. |
| SELECT hai lần nhưng vẫn cùng old state | Identity map trả managed instance | Dùng refresh/transaction mới khi thật sự cần state DB mới. |
| Flush tốn nhiều CPU/memory | Quá nhiều managed entities và collection snapshots | Xem batch strategy, projection, flush/clear và read-only mode. |

### Đừng debug bằng cách so `entity == detachedCopy`

Hai objects đại diện cùng DB row có thể là hai Java instances khác nhau. Dirty checking chỉ theo dõi **instance managed** ở context hiện tại. Sử dụng `entityManager.contains()` và identifier/entity type để xác định state, không dựa đơn thuần vào reference equality khi đi qua nhiều sessions.

## 32. Các sai lầm về snapshot và dirty checking

### 32.1. “Hibernate tạo bản sao đầy đủ của entity Java”

Không nhất thiết. Snapshot là representation của persistent state theo metadata từng property, có thể là mảng giá trị/nội bộ hoặc dirty flags đã enhancement; không nên hình dung luôn có một bản sao sâu y hệt object graph.

### 32.2. “Snapshot là dữ liệu mới nhất trong DB”

Không. Snapshot thường phản ánh dữ liệu/context ở thời điểm load hoặc đồng bộ gần nhất. External updates, transaction isolation, caches và native SQL có thể khiến nó lệch database hiện tại.

### 32.3. “Chỉ field có setter công khai mới dirty-check được”

Không. Hibernate hỗ trợ field access và có thể dirty-check persistent fields được ghi bằng domain methods, reflection/enhanced access hoặc các phương thức khác theo mapping. Điều quan trọng là field mapped của managed entity có state thay đổi đúng cách.

### 32.4. “Phải gọi update() sau setter”

Không với managed entity. Setter làm đổi state; dirty checking ở flush xử lý update. Với detached entity, việc setter không được theo dõi mới là vấn đề cần merge/tải managed entity.

### 32.5. “Flush xong thì đã commit”

Không. Flush gửi SQL trong transaction đang hoạt động; rollback vẫn có thể hủy thay đổi.

### 32.6. “@DynamicUpdate mới cho phép Hibernate phát hiện dirty field”

Không. Dirty checking là cơ chế core; `@DynamicUpdate` ảnh hưởng SQL update shape theo dirty fields khi phù hợp.

### 32.7. “Mọi property change đều tăng version”

Version handling phụ thuộc loại field, mapping, optimistic locking exclusions, dirty rules, collections và thao tác trực tiếp bên ngoài ORM. Đừng dùng `@Version` để suy luận mọi dữ liệu trong DB đã được khóa ở cấp nghiệp vụ.

### 32.8. “Bulk update sẽ cập nhật managed objects”

Không. Bulk HQL/JPQL DML không đồng bộ từng object trong context như dirty checking. Cần chiến lược clear/refresh hoặc transaction separation.

### 32.9. “Session.setDefaultReadOnly(true) làm entity thành detached”

Không. Entity read-only có thể vẫn managed, identity map vẫn hoạt động; chỉ là chính sách snapshot/dirty checking và persistence khác.

### 32.10. “Cứ gọi clear() là tiết kiệm bộ nhớ mà không mất dữ liệu”

Không. Clear có thể bỏ các pending changes chưa flush và tách mọi entity khỏi context; phải thiết kế batch boundaries rõ ràng.

## 33. Bài thực hành A: một entity, một snapshot, một UPDATE

Mục tiêu: quan sát state loaded và state hiện tại:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Product p = entityManager.find(Product.class, 42L);
BigDecimal before = p.getUnitPrice();

p.changePrice(before.add(new BigDecimal("5.00")));

// In trạng thái trong Java:
System.out.println("before = " + before);
System.out.println("current = " + p.getUnitPrice());

entityManager.flush();
tx.commit();
~~~

Quan sát `SELECT` và `UPDATE` trong log, xem version tăng khi update thành công. Sau commit, tạo EntityManager mới (hoặc clear context theo ownership phù hợp), tải lại Product#42 và kiểm tra giá mới.

Thử biến thể: đặt giá về đúng giá ban đầu trước flush. Quan sát SQL có còn UPDATE trong cấu hình Hibernate hiện tại không.

## 34. Bài thực hành B: cùng context, khác context và refresh

Trong context A:

~~~java
Product a1 = emA.find(Product.class, 42L);
Product a2 = emA.find(Product.class, 42L);
System.out.println(a1 == a2); // thường true
~~~

Trong context B:

~~~java
Product b1 = emB.find(Product.class, 42L);
System.out.println(a1 == b1); // thường false
~~~

Nếu transaction B commit một thay đổi, quan sát context A trước/sau `refresh(a1)` theo transaction isolation. Ghi rõ:

- `a1`/`a2` có dùng chung Java reference?
- `b1` có cùng ID?
- A có thấy thay đổi của B ngay không?
- `refresh` đã tải state nào?

Mục tiêu không phải dự đoán mọi isolation behavior giống nhau, mà phân biệt **identity map theo context** với **dữ liệu DB ở thời điểm transaction đọc**.

## 35. Bài thực hành C: detached object không được dirty-check

~~~java
tx.begin();

Product p = entityManager.find(Product.class, 42L);
entityManager.detach(p);
System.out.println(entityManager.contains(p)); // false

p.changePrice(new BigDecimal("300.00"));
tx.commit();
~~~

Tải lại row trong context mới để thấy việc sửa detached object tự nó không tạo SQL update. Sau đó thực hành:

~~~java
tx.begin();
Product managed = entityManager.merge(p);
entityManager.flush();
tx.commit();
~~~

Quan sát instance trả về từ `merge`, SQL update và transaction. Trên schema có `@Version`, nếu row đã bị sửa đồng thời, merge/flush có thể ném optimistic-lock exception; đó là hành vi cần xử lý chứ không nên bỏ qua.

## 36. Bài thực hành D: flush, clear và rollback

~~~java
tx.begin();

Product p = entityManager.find(Product.class, 42L);
p.changePrice(new BigDecimal("350.00"));

entityManager.flush();
entityManager.clear();
tx.rollback();
~~~

Mặc dù `flush()` có thể đã gửi `UPDATE`, DB row chưa được commit và rollback hủy thay đổi. Object `p` trong Java vẫn có thể có giá 350 và đã detached. Ở transaction mới, query DB để xác nhận giá đã commit theo trạng thái trước.

Thử lại với `clear()` **trước** `flush()` và không có thay đổi khác: quan sát vì sao pending update không được ghi.

## 37. Bài thực hành E: bulk DML tạo stale context

~~~java
tx.begin();

Product p = entityManager.find(Product.class, 42L);
System.out.println("old = " + p.getUnitPrice());

entityManager.createQuery(
    "update Product p set p.unitPrice = :price where p.id = :id"
).setParameter("price", new BigDecimal("400.00"))
 .setParameter("id", 42L)
 .executeUpdate();

System.out.println("managed = " + p.getUnitPrice());

entityManager.refresh(p);
System.out.println("refreshed = " + p.getUnitPrice());

tx.commit();
~~~

Quan sát SQL từ bulk update và refresh, kiểm tra khác biệt giữa current managed state với database state. Với `@Version`, chú ý bulk update có thể không tăng version tự động; nên thực hiện trên dữ liệu test và reset trạng thái trước khi lặp lại với optimistic locking.

## 38. Bài thực hành F: collection và owning side

Tạo một đơn hàng có hai lines, commit, sau đó trong transaction mới:

1. Tải `PurchaseOrder`; quan sát `lines` lazy hay đã initialized.
2. Truy cập `order.getLines()` và ghi nhận SQL collection load.
3. Dùng helper thêm một `OrderLine` mới (cập nhật cả collection và `line.order`).
4. Flush, quan sát INSERT/UPDATE FK và snapshot/dirty tracking của collection.
5. Dùng helper xóa một line khi mapping có `orphanRemoval = true`; flush và xem DELETE.
6. Lặp lại trường hợp chỉ sửa inverse list mà không sửa owning side trong môi trường thử nghiệm để thấy FK không được điều khiển đúng.

Không tự thay nguyên collection field bằng `new ArrayList<>()` khi entity đang managed mà không hiểu dirty tracking; với cascade/orphanRemoval, thay wrapper collection có thể gây lỗi ownership hoặc làm ORM hiểu là thay thế toàn bộ collection.

## 39. Bảng quyết định nhanh

| Nhu cầu | API/cơ chế phù hợp | Lưu ý |
|---|---|---|
| Đọc managed entity theo ID | `find()` | Ưu tiên first-level identity map; SQL có thể không chạy. |
| Có reference trước khi thật sự cần state | `getReference()` | Lazy proxy có thể chưa initialize; kiểm tra row tồn tại tùy lúc. |
| Sửa một field của managed entity | Domain setter/method | Dirty checking ở flush, không cần update thủ công. |
| Gửi các thay đổi đang chờ xuống DB | `flush()` | Không commit; rollback vẫn có thể hủy. |
| Xác nhận toàn transaction | Transaction `commit()` | Flush thường tham gia, nhưng commit còn có thể fail. |
| Bỏ quản lý một entity | `detach()` | Các sửa đổi sau detach không tự ghi. |
| Xóa metadata quản lý của cả context | `clear()` | Tránh mất pending changes; flush trước nếu cần. |
| Đồng bộ managed entity từ DB | `refresh()` | Có thể ghi đè sửa đổi chưa flush. |
| Sao chép detached state vào context | `merge()` | Dùng managed instance trả về. |
| Đọc nhiều entity nhưng không muốn tracking update | Read-only mode/projection/DTO | Tùy API và mapping; không tự biến entity thành detached. |
| Tải dữ liệu rất lớn | Batch flush/clear, streaming/projection, hoặc `StatelessSession` khi phù hợp | Cân nhắc transaction boundaries/cascade/locking. |
| Update hàng loạt trực tiếp | Bulk HQL/JPQL/native SQL | Không tự đồng bộ managed snapshots; cần clear/refresh/transaction strategy. |
| Tối ưu cột UPDATE | `@DynamicUpdate` khi workload phù hợp | Dirty checking có sẵn; dynamic SQL có trade-off batching. |

## 40. Mô hình ghi nhớ

~~~text
       LOAD
         |
         v
    SELECT / CACHE STATE
         |
         v
   HYDRATE MANAGED ENTITY
         |
         +--> identity map: EntityKey -> Java instance
         |
         +--> loaded-state metadata / snapshot / dirty tracking
         |
         v
   APPLICATION MUTATES FIELDS
         |
         v
    FLUSH BOUNDARY
         |
         +--> dirty checking: current vs loaded/enhanced state
         |
         +--> INSERT / UPDATE / DELETE / collection actions
         |
         v
      JDBC SQL
         |
         v
   COMMIT or ROLLBACK
~~~

**Tải đối tượng** là bước biến dữ liệu lưu trữ thành Java entity và đăng ký managed identity. **Lưu ảnh trạng thái** là cách Hibernate giữ thông tin nền để quản lý thay đổi, không phải một hệ thống lịch sử độc lập. **Dirty checking** so current state với trạng thái đã được biết hoặc sử dụng metadata enhanced dirty tracking để quyết định SQL cần ghi. **Flush** đẩy các hành động đó xuống database nhưng **commit** mới xác nhận transaction.

Khi entity còn managed, một domain method như `product.changePrice(...)` thường đủ để Hibernate theo dõi update. Khi entity đã detached/read-only, khi sửa dữ liệu bằng bulk/native SQL, hoặc khi lazy collection chưa load, cơ chế có những ranh giới rất khác. Hiểu rõ **identity map, snapshot, lifecycle và transaction boundaries** giúp viết code Hibernate chính xác, xử lý những trường hợp “sửa rồi không lưu” hoặc “SQL đã chạy nhưng getter vẫn cũ”, và chọn được các tối ưu phù hợp thay vì gọi `flush()`, `merge()` hay `clear()` theo thói quen.
