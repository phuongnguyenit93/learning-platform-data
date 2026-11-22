# Phạm vi lưu giữ entity trong persistence context của JPA

Trong **Jakarta Persistence (JPA)**, sau khi một entity được nạp vào **persistence context**, JPA không chỉ trả về một Java object rồi bỏ qua nó. Provider còn theo dõi **danh tính entity, trạng thái quản lý và những thay đổi cần đồng bộ với database**. Cơ chế này thường được gọi là **first-level cache (L1 cache)**.

Điểm dễ nhầm là chữ *cache*: persistence context **không phải bộ nhớ đệm dùng chung toàn ứng dụng**. Nó có ranh giới rõ ràng, phụ thuộc vào cách `EntityManager` và transaction được quản lý.

Một entity có thể đang managed trong context này, detached ở context khác, hoặc là một managed instance hoàn toàn khác trong context khác dù cùng trỏ tới một database row.

Bài học thuộc chương **Bộ nhớ đệm** của chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào **phạm vi lưu giữ entity trong persistence context**: thời điểm một entity được giữ, lý do identity map quan trọng, các thao tác `flush`, `clear`, `detach`, `refresh`, `close` và `commit` tác động ra sao, khác biệt giữa transaction-scoped với extended/application-managed contexts, cùng những hệ quả về stale data, bộ nhớ, lazy loading, concurrency và kiểm thử.

**Nguyên tắc chính:** *persistence context giữ những managed entities trong phạm vi vòng đời của chính context đó; transaction kết thúc, flush và clear không phải ba khái niệm đồng nghĩa.*

---

## 1. Persistence context là gì?

Persistence context là môi trường quản lý những entity instances được JPA provider nhận diện theo entity identity. Khi đã quản lý một entity, provider có thể:

- Bảo đảm một managed instance đại diện cho một entity identity trong cùng context.
- Theo dõi thay đổi để đồng bộ khi flush/commit.
- Giữ snapshot hoặc metadata phục vụ dirty checking tùy implementation.
- Quản lý trạng thái entity và các association được tải.
- Duy trì phiên bản `@Version` để kiểm soát optimistic updates.
- Phối hợp insert, update và delete theo quy tắc JPA.

Sơ đồ:

~~~text
                  Persistence context A
+-------------------------------------------------------+
| Entity identity            Java managed instance       |
| InventoryItem#101 -------> object A                    |
| Customer#7        -------> object B                    |
| PurchaseOrder#50  -------> object C                    |
|                                                       |
| Tracking state / collections / metadata tùy provider  |
+-------------------------------------------------------+
                           |
                      flush / query
                           |
                           v
                        Database
~~~

Đây là **identity map** chứ không chỉ một kho dữ liệu immutable. Những objects trong context có thể tiếp tục bị sửa bởi Java code và được provider theo dõi.

### 1.1. Một entity identity trong một context

~~~java
InventoryItem first =
    em.find(InventoryItem.class, 101L);

InventoryItem second =
    em.find(InventoryItem.class, 101L);

System.out.println(first == second); // true trong cùng context
~~~

Với một managed entity identity xác định, JPA duy trì một managed instance trong context đó. Assertion phù hợp:

~~~java
assertSame(first, second);
~~~

Không dùng `equals()` thay cho identity test: entity có thể override `equals()`/`hashCode()` theo nhiều cách, nhất là khi ID được sinh sau `persist`.

### 1.2. Context có thể chứa nhiều entity types

Một context có thể giữ `InventoryItem#101`, `Customer#7` và `PurchaseOrder#50` cùng lúc. Entity không được quản lý chỉ vì chúng có cùng bảng; provider phân biệt bằng **entity identity** trong persistence unit.

Không nên suy ra kích thước context bằng số bảng đang được truy vấn. Một truy vấn có thể materialize hàng chục nghìn entity instances dù chỉ liên quan một table.

## 2. Phạm vi L1 cache: theo persistence context, không theo toàn app

Hai EntityManagers độc lập thường có hai contexts độc lập:

~~~text
Request / unit of work A              Request / unit of work B
            |                                     |
            v                                     v
     EntityManager A                       EntityManager B
            |                                     |
      Context A                               Context B
            |                                     |
 InventoryItem#101                       InventoryItem#101
     Java object A                          Java object B
            |                                     |
            +---------------+---------------------+
                            |
                            v
                         Database
~~~

Ví dụ:

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    InventoryItem first =
        em1.find(InventoryItem.class, 101L);

    InventoryItem second =
        em2.find(InventoryItem.class, 101L);

    assertNotSame(first, second);
    assertTrue(em1.contains(first));
    assertTrue(em2.contains(second));

} finally {
    em2.close();
    em1.close();
}
~~~

Hai instances có thể cùng đại diện cho database row ID 101, nhưng **không phải cùng object trong Java heap**. Mỗi EntityManager quản lý state riêng, và hai contexts có thể nhìn thấy version khác nhau của dữ liệu.

### 2.1. EntityManagerFactory khác EntityManager

| Thành phần | Trách nhiệm | Phạm vi thông thường |
| --- | --- | --- |
| `EntityManagerFactory` | Factory, mapping metadata và tài nguyên cấp factory | Chia sẻ lâu dài trong ứng dụng |
| `EntityManager` | API làm việc với persistence context | Theo unit of work/transaction tùy kiến trúc |
| Persistence context | Quản lý managed entity identity/state | Theo lifecycle context |
| First-level cache | Identity map của context | Không chia sẻ managed objects tùy ý |
| Second-level cache | Shared cache tùy provider/cấu hình | Có thể chia sẻ qua nhiều contexts |
| Query cache | Tối ưu query results theo provider | Không phải identity map |

`EntityManagerFactory` thường được dùng chung giữa threads. **`EntityManager` không thread-safe**; không giữ một EntityManager singleton rồi cho mọi request cùng sử dụng.

## 3. Entity mẫu để theo dõi lifecycle

Các ví dụ dùng Java 17+, `jakarta.persistence` và entity đơn giản:

~~~java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                "quantity cannot be negative"
            );
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public void changeQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException(
                "quantity cannot be negative"
            );
        }
        this.quantity = next;
    }
}
~~~

Schema minh họa theo PostgreSQL:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(255) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_quantity_nonnegative
        CHECK (quantity >= 0)
);
~~~

Schema thực tế phải khớp migration và provider/dialect. Không hardcode giá trị version khởi tạo vì chiến lược version và type có thể khác nhau.

## 4. Bốn trạng thái entity trong JPA

Để biết persistence context giữ object nào, cần phân biệt bốn trạng thái.

### 4.1. NEW

~~~java
InventoryItem item =
    new InventoryItem("SKU-100", 10);
~~~

Đây là Java object mới. Nó chưa được context quản lý và chưa phải row đã được JPA persist.

### 4.2. MANAGED

~~~java
em.getTransaction().begin();

em.persist(item);

assertTrue(em.contains(item));

em.getTransaction().commit();
~~~

`persist` chuyển entity mới thành managed. SQL INSERT có thể xảy ra sớm hoặc khi flush tùy ID generation và provider.

Entity managed được theo dõi để đồng bộ với database khi transaction cho phép.

### 4.3. DETACHED

~~~java
em.detach(item);

assertFalse(em.contains(item));
~~~

Object vẫn tồn tại trong Java, có thể giữ những giá trị đã tải, nhưng context không còn dirty-check nó.

Detach có thể xảy ra do:

- `em.detach(entity)`.
- `em.clear()`.
- `em.close()`.
- Transaction-scoped persistence context kết thúc.
- Một entity object được truyền ra ngoài scope quản lý tương ứng.

### 4.4. REMOVED

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

em.remove(item);
~~~

Entity chuyển sang trạng thái chờ xóa. SQL DELETE có thể được gửi khi flush. `remove` không đồng nghĩa row đã bị xóa bền vững ở thời điểm method trả về.

### 4.5. Sơ đồ giản lược

~~~text
   new Entity()
        |
        | persist()
        v
     MANAGED
        |
        +-- field mutation --> dirty checking --> UPDATE khi flush
        |
        +-- remove() ------> REMOVED -------> DELETE khi flush
        |
        +-- detach()/clear()/context end
                              |
                              v
                           DETACHED
                              |
                              | merge()
                              v
                        managed copy
~~~

Điều quan trọng: `merge(detached)` **trả một managed instance** chứa state được hợp nhất. Không mặc định chính tham số detached trở thành managed object.

---

## 5. Persistence context tồn tại trong bao lâu?

Câu trả lời chính xác là: **theo lifecycle của context**. Tùy cách tạo/điều phối EntityManager, context có thể gắn với một transaction hoặc sống qua nhiều transactions.

| Mô hình | Phạm vi context điển hình | Khi transaction commit |
| --- | --- | --- |
| Jakarta EE transaction-scoped `@PersistenceContext` | Theo transaction | Context transaction-scoped kết thúc |
| Jakarta EE extended `@PersistenceContext` | Theo lifecycle thành phần sở hữu | Có thể tiếp tục quản lý entity qua nhiều transactions |
| Application-managed `emf.createEntityManager()` | Từ tạo EntityManager đến close | Có thể tiếp tục giữ managed entities nếu EntityManager còn mở |
| Spring-managed transaction-scoped EntityManager | Theo transaction infrastructure | Context thường được cleanup khi transaction kết thúc |
| Spring OSIV | Có thể mở EM qua cả HTTP request | Context có thể sống sau service transaction, dù transaction đã kết thúc |

**Không áp dụng câu “commit sẽ clear tất cả” cho mọi mô hình.** Commit là thao tác transaction, còn lifecycle persistence context phụ thuộc cách nó được quản lý.

## 6. Transaction-scoped context trong Jakarta EE

Container-managed EntityManager:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@jakarta.ejb.Stateless
public class InventoryService {

    @PersistenceContext(
        unitName = "inventoryPU",
        type = PersistenceContextType.TRANSACTION
    )
    private EntityManager em;

    public InventoryItem find(Long id) {
        return em.find(InventoryItem.class, id);
    }
}
~~~

Context loại **TRANSACTION** gắn với JTA transaction. Trong cùng context:

~~~java
InventoryItem first = em.find(InventoryItem.class, id);
InventoryItem second = em.find(InventoryItem.class, id);
~~~

sẽ dùng managed identity theo JPA.

Khi transaction-scoped context kết thúc cùng transaction, entities không còn được context đó quản lý.

### 6.1. Trả entity khỏi service không kéo dài context

~~~text
JTA transaction begins
        |
        v
Transaction-scoped context
  - find InventoryItem#101
  - changeQuantity()
  - flush/commit
        |
        v
JTA transaction completes
        |
        v
Context ends
        |
        v
Returned Java object may be detached
~~~

Một controller giữ reference tới object không làm transaction-scoped context tự sống tiếp.

### 6.2. Cùng transaction không phải luôn cùng Java variable EM

Nhiều container-managed proxies có thể trỏ tới context gắn với cùng transaction/persistence unit. Điều cần xác định là **context thực**, không phải một field Java có tên `em`.

Các ranh giới transaction propagation, persistence unit và container configuration đều quan trọng khi lý giải identity.

## 7. Extended persistence context

**Extended persistence context** có thể giữ managed state qua nhiều transaction. Ví dụ thường gặp trong Jakarta EE là một **stateful session bean**:

~~~java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class InventoryDraftWorkflow {

    @PersistenceContext(
        unitName = "inventoryPU",
        type = PersistenceContextType.EXTENDED
    )
    private EntityManager em;

    private InventoryItem draft;

    public void open(Long id) {
        draft = em.find(InventoryItem.class, id);
    }

    public void editQuantity(int quantity) {
        draft.changeQuantity(quantity);
    }

    public void save() {
        // Transaction/container quản lý thời điểm đồng bộ.
    }
}
~~~

Đoạn ví dụ minh họa **lifecycle**; method `save()` chưa phải triển khai use case hoàn chỉnh. Cần transaction semantics, validation và xử lý concurrency theo container/project.

### 7.1. Extended không có nghĩa global

~~~text
Stateful workflow A              Stateful workflow B
        |                                |
  Extended PC A                    Extended PC B
        |                                |
  Item#101 object A                Item#101 object B
        |                                |
        +------------ DB ----------------+
~~~

Hai workflows có contexts riêng, không dùng một entity Java object chung.

### 7.2. Những đánh đổi

Lợi ích:

- Duy trì state khi workflow nhiều bước.
- Identity nhất quán bên trong cùng workflow.
- Có thể giảm nhu cầu merge giữa các bước.

Rủi ro:

- Long-lived managed state dễ stale.
- Nhiều entity được giữ lâu làm tăng memory.
- Optimistic conflicts xuất hiện khi commit sau nhiều bước.
- Khó xử lý đồng thời từ nhiều requests.
- Phải quản lý lifecycle, rollback, passivation và cleanup theo container.

Một API HTTP stateless thông thường không cần extended context chỉ để tránh gọi `find` ở request sau.

## 8. Application-managed EntityManager có thể sống qua nhiều transactions

Với Java SE/`RESOURCE_LOCAL`:

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    InventoryItem item =
        em.find(InventoryItem.class, itemId);

    item.changeQuantity(15);

    em.getTransaction().commit();

    // EntityManager chưa close.
    boolean stillManaged = em.contains(item);

    System.out.println(stillManaged);

} finally {
    em.close();
}
~~~

Một application-managed EntityManager bình thường giữ context cho tới khi `close()`, trừ các thao tác detach/clear hoặc lifecycle transitions khác. Do đó sau transaction commit, `em.contains(item)` có thể vẫn là true.

### 8.1. Commit không tương đương clear

Hai lời gọi khác nhau:

~~~java
em.getTransaction().commit();
~~~

và:

~~~java
em.clear();
~~~

`commit` kết thúc transaction. `clear` detach các managed entities trong context. Chúng không thể thay thế cho nhau.

### 8.2. Context còn mở không đồng nghĩa transaction đang active

~~~text
EntityManager created
    |
    +-- Transaction 1 begin -> commit
    |
    +-- Context still exists
    |
    +-- Transaction 2 begin -> commit
    |
    +-- Context still exists
    |
    +-- EntityManager.close()
    |
    v
Context lifecycle ends
~~~

Tồn tại managed state giữa hai transactions không có nghĩa các thao tác ghi yêu cầu transaction đã được phép commit ngoài transaction.

**Đừng dùng một EntityManager sống vô hạn làm cache ứng dụng.** Nó có thể tích lũy entity references, dữ liệu cũ và trở thành nguồn lỗi concurrency.

---

## 9. Spring và transaction-scoped EntityManager proxy

Trong Spring:

~~~java
@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public InventoryDto getItem(Long id) {
        InventoryItem item =
            em.find(InventoryItem.class, id);

        return new InventoryDto(
            item.getId(),
            item.getSku(),
            item.getQuantity(),
            item.getVersion()
        );
    }
}
~~~

Trong cấu hình Spring JPA thường gặp, field inject có thể là **shared EntityManager proxy**. Proxy điều phối tới EntityManager/context hiện hành theo transaction/thread binding. Nó không đồng nghĩa toàn bộ requests dùng một persistence context.

### 9.1. Cùng một field nhưng context khác

Hai request độc lập có thể gọi cùng `InventoryService.getItem`, cùng dùng field `em`, nhưng thực tế được transaction manager gắn với **hai contexts riêng**.

Không dựa vào tên biến `em` hoặc identity của proxy để suy luận hai thao tác dùng chung L1 state.

### 9.2. REQUIRES_NEW có context riêng

Khi một transaction thực sự dùng `REQUIRES_NEW`, transaction trước có thể bị tạm ngưng; transaction mới sử dụng tài nguyên/context tương ứng. Vì vậy một proxy field có thể đại diện cho các contexts khác nhau theo transaction.

### 9.3. Open EntityManager in View

Nếu bật OSIV:

~~~text
HTTP request begins
        |
        v
EntityManager/context opens
        |
        +-- @Transactional service begins and ends
        |
        +-- JSON serializer may still see an open context
        |
        v
HTTP response completes
        |
        v
EntityManager closes
~~~

Điều này giải thích tại sao một lazy relationship đôi khi còn được tải trong serializer sau khi service transaction đã kết thúc.

Nhưng context mở **không đồng nghĩa transaction vẫn active**. OSIV có thể giấu N+1, tạo SQL ngoài service và khiến latency khó kiểm soát. Tốt hơn là thiết kế fetch plan và trả DTO hoàn chỉnh từ service.

### 9.4. Không chia sẻ EntityManager giữa threads

EntityManager không thread-safe. Với background jobs hoặc async tasks, truyền ID/DTO rồi mở unit of work riêng khi cần DB access. Không chia sẻ một managed entity graph đang biến đổi giữa nhiều threads.

## 10. find() và identity map

Trong cùng context:

~~~java
InventoryItem first =
    em.find(InventoryItem.class, id);

InventoryItem second =
    em.find(InventoryItem.class, id);

assertSame(first, second);
~~~

Nếu entity đã nằm trong context, provider thường không cần SELECT lại cho `find` lần hai.

Nhưng điều này **không có nghĩa mọi JPQL query đều được cache**.

### 10.1. JPQL query có thể vẫn chạy SQL

~~~java
List<InventoryItem> rows = em.createQuery(
    """
    SELECT i
    FROM InventoryItem i
    WHERE i.quantity >= :threshold
    """,
    InventoryItem.class
)
.setParameter("threshold", 5)
.getResultList();
~~~

JPQL có thể thực thi SQL để xác định rows khớp filter. Khi kết quả chứa entity identity đã managed, provider duy trì managed instance trong context.

- L1 quản lý **entity identity và state**.
- Query result caching là cơ chế khác.
- Một JPQL query có thể phát SQL dù L1 đang giữ entity.
- Query không mặc định refresh toàn bộ field của managed instance đang cũ.

### 10.2. L1 không đảm bảo đọc dữ liệu mới nhất

Nếu transaction khác sửa DB nhưng context hiện tại đã managed entity, lần `find(id)` tiếp theo có thể trả object cũ. Đó là identity consistency, không phải một lần forced refresh.

## 11. contains() chỉ kiểm tra managed membership

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

assertTrue(em.contains(item));

em.detach(item);

assertFalse(em.contains(item));
~~~

`contains` trả lời: **Entity object này có đang được EntityManager/context này quản lý không?**

Nó không trả lời:

- Database có row ID này không?
- L2 cache có chứa entity data không?
- Field `lines` của entity có được lazy-loaded chưa?
- Entity có phải bản ghi mới nhất của database không?

Không gọi `contains` cho DTO thông thường; nó không phải entity được JPA mapping.

---

## 12. flush(): đồng bộ SQL, không giải phóng context

~~~java
em.getTransaction().begin();

InventoryItem item =
    em.find(InventoryItem.class, id);

item.changeQuantity(15);

em.flush();

assertTrue(em.contains(item));

em.getTransaction().commit();
~~~

`flush` có thể gửi pending INSERT/UPDATE/DELETE xuống database trong transaction hiện tại. Nó không tự detach entity, không đóng EntityManager và **không tự commit**.

~~~text
managed entity
     |
     | Java field change
     v
pending state
     |
     | flush
     v
SQL in current transaction
     |
     | commit
     v
durable change according to database transaction
~~~

Nếu transaction rollback sau flush, SQL chưa commit có thể bị rollback theo database semantics.

### 12.1. Flush không phải memory cleanup

Khi context đang quản lý 50.000 entities, gọi `flush()` không tự làm nó quên 50.000 managed objects. Nếu mục tiêu là giảm memory, cần xem `clear()`, `detach()` hoặc scope context ngắn.

### 12.2. Flush cần transaction thích hợp

Các thao tác đồng bộ thay đổi yêu cầu active transaction/context tham gia phù hợp. Không gọi `em.flush()` tùy tiện khi transaction chưa mở rồi kỳ vọng JPA tự commit.

## 13. clear(): detach toàn bộ managed entities

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

assertTrue(em.contains(item));

em.clear();

assertFalse(em.contains(item));
~~~

`clear()` ngừng quản lý các entities trong context. Nó **không xóa database rows**.

### 13.1. Pending changes có thể bị bỏ

Sai:

~~~java
em.getTransaction().begin();

InventoryItem item =
    em.find(InventoryItem.class, id);

item.changeQuantity(50);

em.clear();
em.getTransaction().commit();
~~~

Nếu provider chưa flush, entity đã detach trước khi dirty changes được đồng bộ. Application có thể nghĩ commit đã save nhưng thực tế không.

Khi cần giữ thay đổi và giải phóng context:

~~~java
em.getTransaction().begin();

InventoryItem item =
    em.find(InventoryItem.class, id);

item.changeQuantity(50);

em.flush();
em.clear();

em.getTransaction().commit();
~~~

**Flush vẫn chưa commit**, nên phải xử lý rollback/exception đúng. Đừng sao chép cách này vào mọi use case; nó làm các references tới entity cũ trở thành detached.

### 13.2. find sau clear có thể tạo instance khác

~~~java
InventoryItem before =
    em.find(InventoryItem.class, id);

em.clear();

InventoryItem after =
    em.find(InventoryItem.class, id);

assertNotSame(before, after);
assertFalse(em.contains(before));
assertTrue(em.contains(after));
~~~

`before` vẫn tồn tại ở Java heap, nhưng không còn là managed entity của context đó. `after` là managed instance mới.

## 14. detach(entity): detach chọn lọc

~~~java
InventoryItem first =
    em.find(InventoryItem.class, firstId);

InventoryItem second =
    em.find(InventoryItem.class, secondId);

em.detach(first);

assertFalse(em.contains(first));
assertTrue(em.contains(second));
~~~

`detach` chỉ yêu cầu ngừng quản lý một entity; cascade detach sang association tùy mapping `CascadeType.DETACH` và semantics JPA. Không mặc định một lời gọi detach root làm toàn object graph tách hoàn toàn.

### 14.1. Detach không flush

Nếu `first` có pending updates, detach có thể khiến những updates đó không tự được đồng bộ. Khi cần giữ thay đổi, tổ chức transaction/flush theo ý định rồi mới detach.

### 14.2. Merge trả managed copy

~~~java
em.detach(first);

first.changeQuantity(25);

InventoryItem managedCopy =
    em.merge(first);
~~~

Tiếp tục làm việc trên `managedCopy`, không giả định `first` đã tự reattach. Cần kiểm tra optimistic version và các invariants khi hợp nhất detached state.

## 15. close(): kết thúc lifecycle application-managed EntityManager

~~~java
EntityManager em = emf.createEntityManager();

try {
    InventoryItem item =
        em.find(InventoryItem.class, id);

    // Làm việc với managed entity / map DTO.
} finally {
    em.close();
}
~~~

Sau `close()`, context do EntityManager đó sở hữu kết thúc. Java references có thể vẫn tồn tại nhưng không còn được context đã đóng theo dõi.

**Không gọi close trên container-managed EntityManager để “dọn cache chung”**; container/framework chịu trách nhiệm lifecycle của nó.

### 15.1. Close không thay commit/rollback

Một mẫu resource-local chuẩn:

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    // Thao tác với managed entities.

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

Nếu transaction đã thất bại, đừng cố tiếp tục với cùng persistence context như thể không có lỗi.

## 16. refresh(): nạp state mới cho managed entity

Một context có thể giữ state cũ:

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

// Transaction khác commit một thay đổi trên row.
~~~

Khi ứng dụng cần đọc lại entity hiện đang managed:

~~~java
em.refresh(item);
~~~

`refresh` nạp lại state cho managed instance theo semantics JPA/context/transaction hợp lệ. Nó **không phải clear toàn bộ context**.

### 16.1. Refresh có thể ghi đè pending changes

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

item.changeQuantity(99);

em.refresh(item);
~~~

Nếu chưa flush, thay đổi 99 trên Java object có thể bị ghi đè bởi database state. Không dùng refresh như một lệnh vô hại trong workflow đang có edits chưa lưu.

### 16.2. Refresh và clear khác nhau

| Phương thức | Tác động chính |
| --- | --- |
| `refresh(item)` | Nạp state cho cùng managed instance |
| `detach(item)` | Ngừng quản lý một instance |
| `clear()` | Ngừng quản lý mọi managed entities trong context |
| `find(id)` sau clear | Tải/lấy managed instance mới |
| `close()` | Kết thúc application-managed context |

---

## 17. Bảng tổng hợp các thao tác

| Thao tác | Có thể phát SQL? | Còn managed? | Tự commit? |
| --- | --- | --- | --- |
| `find` | Có nếu cần | Có | Không |
| `persist` | Có thể INSERT tùy ID/flush | Có | Không |
| Sửa field managed | Thường chưa ngay | Có | Không |
| `flush` | Có thể INSERT/UPDATE/DELETE | Thường có | Không |
| `commit` | Có thể flush | **Tùy scope context** | Có |
| `detach` | Không nhằm ghi | Entity đó không | Không |
| `clear` | Không nhằm ghi | Không đối với entities đã detach | Không |
| `refresh` | Có thể SELECT | Có nếu entity hợp lệ/managed | Không |
| `remove` | DELETE có thể trì hoãn | Chuyển removed state | Không |
| `close` | Cleanup | Context kết thúc | Không thay commit |
| `merge` | Có thể query/flush | Managed copy trả về | Không |

Không nên đơn giản hóa hàng `commit` thành “luôn managed” hoặc “luôn detached”. Đó là điểm khác biệt quan trọng giữa transaction-scoped và application-managed/extended contexts.

## 18. L1 và L2 là hai bộ nhớ đệm khác nhau

~~~text
EntityManager A               EntityManager B
      |                             |
      v                             v
L1 context A                  L1 context B
      |                             |
      +--------------+--------------+
                     |
                     v
             L2 shared cache
                (optional)
                     |
                     v
                  Database
~~~

### 18.1. First-level cache

- Một phần của persistence context.
- Quản lý identity và managed entity state.
- Không phải một cache dùng chung tùy ý giữa EntityManagers.
- Không tự mất hiệu lực chỉ vì tắt shared L2 cache.
- Có cơ chế detach/clear/close theo context lifecycle.

### 18.2. Second-level cache

- Shared cache tùy provider/configuration.
- Có thể giảm các lần đọc database giữa contexts.
- Không có nghĩa hai contexts sử dụng cùng một managed Java object.
- Không thay thế concurrency control, transaction isolation và versioning.
- Evict L2 **không tự detach L1 entities**.

### 18.3. Query cache

Query-result cache nếu có thường là một khả năng riêng của provider; nó không đồng nghĩa với first-level identity map. JPQL query có thể chạy SQL dù managed entities đã nằm trong L1.

### 18.4. So sánh nhanh

| Tiêu chí | L1/persistence context | L2 shared cache | Query cache |
| --- | --- | --- | --- |
| Scope | Một context | Có thể nhiều contexts | Theo provider |
| Managed Java identity | Có | Không theo cùng nghĩa | Không |
| Dirty checking | Có theo managed state | Không | Không |
| `em.contains` | Liên quan trực tiếp | Không | Không |
| `em.clear` | Có tác động | Không trực tiếp | Không trực tiếp |
| `emf.getCache().evict` | Không trực tiếp | Có | Tùy provider |
| Cần bật riêng? | Không theo nghĩa JPA identity map | Có thể | Thường có |

## 19. CacheRetrieveMode.BYPASS không bỏ qua L1 identity

JPA có cache hints:

~~~java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        jakarta.persistence.CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        jakarta.persistence.CacheStoreMode.BYPASS
    )
);
~~~

Những hints này hướng tới **shared-cache semantics**. Nếu entity ID đã managed trong L1, không mặc định gọi `BYPASS` sẽ làm provider bỏ object đó và tạo object mới.

Khi cần state mới cho managed entity, cân nhắc `refresh` hoặc dùng một context phù hợp khác.

### 19.1. Evict L2 không evict L1

~~~java
emf.getCache().evict(
    InventoryItem.class,
    itemId
);
~~~

Lời gọi tác động tới shared cache. Entity managed trong `em` có thể vẫn được giữ:

~~~java
assertTrue(em.contains(item));
~~~

Muốn detach entity đó khỏi context hiện tại, dùng `detach` hoặc `clear` có chủ đích, không thay bằng L2 eviction.

---

## 20. Vì sao một managed entity có thể giữ dữ liệu cũ?

Kịch bản:

~~~text
Context A: find Item#101 -> quantity=10
Context B: find Item#101 -> quantity=10
Context B: update quantity=20, commit
Context A: find Item#101 một lần nữa
~~~

Trong Context A, `find` có thể trả lại managed instance đã có quantity=10:

~~~java
InventoryItem before =
    emA.find(InventoryItem.class, id);

// Context B commit quantity=20.

InventoryItem again =
    emA.find(InventoryItem.class, id);

assertSame(before, again);
~~~

Đây là tính nhất quán identity của context, không phải bằng chứng database không commit.

### 20.1. Ba lựa chọn

- `refresh(before)` nếu muốn nạp lại state của managed entity.
- Kết thúc unit of work hiện tại, mở context mới cho lần đọc mới.
- Thiết kế scope ngắn ngay từ đầu nếu không cần giữ state qua nhiều requests.

Mọi lựa chọn vẫn phải xét **transaction isolation**. Một transaction có snapshot isolation có thể không thấy dữ liệu mới chỉ bằng cách đổi cách lấy managed object.

### 20.2. L1 và transaction isolation là hai lớp khác nhau

- L1 trả lời entity instance nào được context quản lý.
- Database isolation quy định transaction nhìn thấy row versions nào.
- `@Version` giúp phát hiện stale update lúc ghi.

Không quy mọi trường hợp giá trị cũ về lỗi cache.

## 21. @Version không tự refresh L1

Ví dụ entity có `@Version`:

~~~text
Context A read quantity=10, version=3
Context B read quantity=10, version=3

Context B change quantity=20, commit -> version=4

Context A still holds quantity=10, version=3
Context A tries update
    -> optimistic conflict
~~~

JPA dùng version để **ngăn stale write**, không đẩy state mới vào mọi persistence contexts ngay khi transaction khác commit.

Sau optimistic failure, rollback và không tiếp tục dùng context lỗi như một unit of work hợp lệ. Khi retry, mở transaction/context mới, đọc version mới và xem xét ý định nghiệp vụ.

## 22. Bulk JPQL/native DML có thể làm context stale

~~~java
InventoryItem item =
    em.find(InventoryItem.class, id);

System.out.println(item.getQuantity()); // 10
~~~

Sau đó:

~~~java
int affected = em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = :value
    WHERE i.id = :id
    """
)
.setParameter("value", 50)
.setParameter("id", id)
.executeUpdate();
~~~

Bulk UPDATE có thể đã đổi database nhưng **managed item vẫn giữ quantity=10**. Bulk DML không tự điều chỉnh mọi managed instances qua dirty checking.

### 22.1. Đồng bộ trước và làm sạch sau nếu phù hợp

~~~java
em.flush();

int affected = em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = :value
    WHERE i.id = :id
    """
)
.setParameter("value", 50)
.setParameter("id", id)
.executeUpdate();

em.clear();
~~~

`flush` tránh bỏ sót pending changes trước bulk operation; `clear` detach managed state cũ sau đó. Tuy nhiên đây không phải công thức luôn đúng:

- Clear có tác động tới **mọi** managed entities trong context.
- DML có thể ảnh hưởng `@Version`/callbacks/cache theo cách khác entity updates.
- Nếu cần giữ các entities khác managed, `refresh` hoặc tách transaction có thể phù hợp hơn.
- Khi transaction rollback, ứng dụng cần xử lý theo semantics giao dịch.

---

## 23. Lazy associations và phạm vi context

Entity có:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Một entity managed không nhất thiết đã tải toàn bộ associations. Khi application truy cập chúng trong context hợp lệ, provider có thể phát SELECT bổ sung.

Nếu context đã đóng:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

em.close();

order.getLines().size();
~~~

một collection chưa initialized có thể gây lỗi lazy loading, chẳng hạn `LazyInitializationException` của Hibernate.

Những field đã nạp trước detach vẫn tồn tại ở object; detached không có nghĩa dữ liệu Java bị xóa.

### 23.1. DTO mapping trong ranh giới hợp lệ

~~~java
@Transactional(readOnly = true)
public OrderDetailDto detail(Long id) {
    PurchaseOrder order =
        repository.findWithFetchPlan(id);

    return mapper.toDetailDto(order);
}
~~~

`findWithFetchPlan` đại diện cho truy vấn tải association cần thiết; code đầy đủ tùy model/project.

DTO nên chứa scalar hoặc nested DTO, không mang entity/proxy ra serializer. Điều này làm response không phụ thuộc context còn mở sau service.

### 23.2. L1 không tự chữa N+1

L1 có thể tránh SELECT lặp lại cho cùng một Customer ID đã managed. Nhưng với 100 Orders và 100 collections khác nhau, mapper vẫn có thể phát 100 SELECT lines.

Cần fetch plan như `JOIN FETCH`, `EntityGraph`, DTO projection hoặc batch fetching theo use case, không chỉ dựa vào persistence context cache.

## 24. PersistenceUnitUtil.isLoaded khác EntityManager.contains

~~~java
jakarta.persistence.PersistenceUnitUtil util =
    em.getEntityManagerFactory().getPersistenceUnitUtil();

boolean managed = em.contains(order);
boolean linesLoaded =
    util.isLoaded(order, "lines");
~~~

`managed` nói entity thuộc context hiện tại hay không. `linesLoaded` nói attribute được xem là đã tải theo provider hay chưa.

Managed entity vẫn có thể có `linesLoaded == false`.

`isLoaded` không tự load association và không đếm SQL. Nó là công cụ quan sát trạng thái tải, không thay fetch plan.

---

## 25. Batch import: context giữ nhiều entity gây tăng bộ nhớ

Ví dụ import 100.000 items trong một transaction:

~~~java
em.getTransaction().begin();

for (int i = 1; i <= 100_000; i++) {
    em.persist(
        new InventoryItem("SKU-" + i, 10)
    );
}

em.getTransaction().commit();
~~~

JPA provider có thể giữ nhiều entity instances, metadata và state trong context. Hệ quả:

- Memory và garbage collection tăng.
- Flush/dirty checking tốn nhiều công hơn.
- Một transaction rất dài có thể rủi ro.
- JDBC batching phụ thuộc ID strategy/provider.
- Nếu application không cần sửa lại 100.000 entities, không nên giữ tất cả managed đến cuối.

### 25.1. Flush + clear theo batch

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    int batchSize = 100;

    for (int i = 1; i <= 100_000; i++) {
        InventoryItem item =
            new InventoryItem("SKU-" + i, 10);

        em.persist(item);

        if (i % batchSize == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
    em.clear();
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

Ở đây:

- Flush đồng bộ SQL của batch hiện tại.
- Clear detach entities đã đồng bộ.
- Commit hoàn tất transaction.

**Flush/clear theo batch không tự biến một transaction lớn thành nhiều transactions nhỏ.** Nếu cần commit theo chunk để giảm thời gian transaction, phải thiết kế unit of work/transaction boundaries khác.

### 25.2. Cẩn thận entity graph và cascades

Nếu đang persist parent với children, gọi clear ở giữa có thể khiến object references trở thành detached và ảnh hưởng cascade/relationship operations. Phải xác định graph ownership trước khi áp dụng batch pattern.

### 25.3. IDENTITY và JDBC batching

`GenerationType.IDENTITY` có thể khiến provider INSERT sớm để nhận generated ID. Điều này ảnh hưởng hiệu quả JDBC batching theo provider/database. `flush+clear` giới hạn context size, **không bảo đảm** batch insert performance theo một số statement cố định.

## 26. Bulk read và DTO projection

Một read query:

~~~java
List<InventoryItem> all = em.createQuery(
    "SELECT i FROM InventoryItem i",
    InventoryItem.class
).getResultList();
~~~

có thể materialize rất nhiều managed objects nếu bảng lớn.

Khi chỉ cần báo cáo, dùng DTO/scalar projection:

~~~java
public record InventoryRow(
    Long id,
    String sku,
    int quantity
) {
}
~~~

~~~java
List<InventoryRow> rows = em.createQuery(
    """
    SELECT new com.example.inventory.dto.InventoryRow(
        i.id,
        i.sku,
        i.quantity
    )
    FROM InventoryItem i
    WHERE i.quantity < :threshold
    ORDER BY i.id
    """,
    InventoryRow.class
)
.setParameter("threshold", 10)
.setMaxResults(500)
.getResultList();
~~~

Projection chỉ gồm scalar fields thường không cần tạo managed entity graph cho mỗi row.

Các lựa chọn khi dữ liệu lớn:

- Projection theo đúng cột cần.
- Pagination/chunks theo key ổn định.
- Context ngắn theo batch.
- `detach`/`clear` khi xử lý managed entities.
- Streaming với quản lý connection/cursor/transaction rõ.
- Đo số rows, memory và SQL thay vì chỉ đếm number of statements.

---

## 27. Tại sao không dùng một EntityManager singleton như cache?

Anti-pattern:

~~~java
public class GlobalInventoryCache {

    private final EntityManager em =
        emf.createEntityManager();

    public InventoryItem get(Long id) {
        return em.find(InventoryItem.class, id);
    }
}
~~~

Nếu class sống suốt ứng dụng và được nhiều requests gọi:

- EntityManager không thread-safe.
- Context có thể tích lũy hàng nghìn managed entities.
- Giá trị có thể stale rất lâu.
- Transaction ownership khó điều phối.
- Cleanup không rõ ràng.
- Đồng thời thay đổi entity có thể gây lỗi nghiêm trọng.

First-level cache được thiết kế cho **unit of work**, không phải thay Redis, application caching hoặc shared second-level cache.

Nếu cần cache toàn cục, thiết kế tầng caching riêng có TTL, invalidation, security và consistency rõ ràng.

## 28. Persistence context khác JDBC connection lifetime

Một context mở không bắt buộc cùng một JDBC connection được giữ từ đầu tới cuối. Provider/transaction manager có thể lấy và trả connection theo chính sách cụ thể.

~~~text
EntityManager/context lifetime
|--------------------------------------|

Transaction 1         Transaction 2
|-------------|       |-------------|

Connection use
    |-----|               |----|
~~~

Sơ đồ chỉ minh họa. Connection acquisition/release phụ thuộc provider, pool và transaction manager.

Đừng suy luận số entity trong context chỉ bằng số JDBC connections đang mở, hoặc mặc định EntityManager mở lâu luôn giữ một connection liên tục.

---

## 29. Kiểm thử first-level identity

Một integration test nên dùng JPA provider và database hoặc fixture thích hợp. Tránh mock nếu mục tiêu là chứng minh context identity.

### 29.1. Setup fixture

~~~java
private Long createFixture(EntityManagerFactory emf) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item = new InventoryItem(
            "SKU-" + java.util.UUID.randomUUID(),
            10
        );

        em.persist(item);
        em.flush();

        Long id = item.getId();

        em.getTransaction().commit();
        return id;

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Fixture được commit và context tạo fixture đã đóng. Mỗi test dùng SKU riêng để tránh xung đột khi chạy song song.

### 29.2. find cùng context

~~~java
@Test
void sameContextReturnsSameManagedInstance() {
    Long id = createFixture(emf);
    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem a =
            em.find(InventoryItem.class, id);

        InventoryItem b =
            em.find(InventoryItem.class, id);

        assertSame(a, b);
        assertTrue(em.contains(a));
        assertTrue(em.contains(b));

    } finally {
        em.close();
    }
}
~~~

Test chứng minh entity identity map, không cần assert chính xác SELECT count.

### 29.3. Hai contexts khác nhau

~~~java
@Test
void differentContextsHaveDifferentManagedInstances() {
    Long id = createFixture(emf);

    EntityManager em1 = emf.createEntityManager();
    EntityManager em2 = emf.createEntityManager();

    try {
        InventoryItem a =
            em1.find(InventoryItem.class, id);

        InventoryItem b =
            em2.find(InventoryItem.class, id);

        assertNotSame(a, b);
        assertTrue(em1.contains(a));
        assertTrue(em2.contains(b));
        assertFalse(em1.contains(b));
        assertFalse(em2.contains(a));

    } finally {
        em2.close();
        em1.close();
    }
}
~~~

Shared L2 cache có thể ảnh hưởng số lần SELECT, nhưng không làm hai contexts dùng chung một managed Java object.

## 30. Test clear và find lại

~~~java
@Test
void clearDetachesAndFindLoadsManagedInstanceAgain() {
    Long id = createFixture(emf);
    EntityManager em = emf.createEntityManager();

    try {
        InventoryItem before =
            em.find(InventoryItem.class, id);

        assertTrue(em.contains(before));

        em.clear();

        assertFalse(em.contains(before));

        InventoryItem after =
            em.find(InventoryItem.class, id);

        assertNotSame(before, after);
        assertTrue(em.contains(after));

    } finally {
        em.close();
    }
}
~~~

Đây là test trực quan về **scope của L1**: clear không xóa database row nhưng thay đổi managed identity đang được giữ.

## 31. Test flush không detach

~~~java
@Test
void flushKeepsManagedEntityInContext() {
    Long id = createFixture(emf);
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item =
            em.find(InventoryItem.class, id);

        item.changeQuantity(15);
        em.flush();

        assertTrue(em.contains(item));

        em.getTransaction().commit();

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Kết quả cần chứng minh: flush **đồng bộ** nhưng không tự detach entity.

## 32. Test commit trong application-managed context

~~~java
@Test
void applicationManagedContextSurvivesCommitUntilClose() {
    Long id = createFixture(emf);
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item =
            em.find(InventoryItem.class, id);

        item.changeQuantity(15);

        em.getTransaction().commit();

        assertTrue(em.contains(item));

    } finally {
        em.close();
    }
}
~~~

Đây là test cho application-managed `RESOURCE_LOCAL` context. **Không dùng để suy ra** container-managed transaction-scoped context phải còn managed sau một JTA transaction.

## 33. Test detach loại khỏi dirty checking

~~~java
@Test
void detachedChangeIsNotAutomaticallyPersisted() {
    Long id = createFixture(emf);
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        InventoryItem item =
            em.find(InventoryItem.class, id);

        em.detach(item);
        item.changeQuantity(99);

        assertFalse(em.contains(item));

        em.getTransaction().commit();

    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        InventoryItem result =
            verify.find(InventoryItem.class, id);

        assertEquals(10, result.getQuantity());

    } finally {
        verify.close();
    }
}
~~~

Sau detach, sửa object Java không tự được context cũ flush. Phải có bước update/merge được thiết kế riêng nếu muốn ghi state đó.

## 34. Đo SQL mà không nhầm L1 với L2

Để so sánh:

| Case | Context | L2 | Điều cần quan sát |
| --- | --- | --- | --- |
| A | EM mới | Tắt | Lần đầu materialize entity |
| B | Cùng EM | Tùy | `find` cùng ID trả cùng object |
| C | EM khác | Bật | Có thể ít SQL nhờ shared cache, nhưng object khác |
| D | Cùng EM sau clear | Tùy | New managed instance; SQL phụ thuộc L2 |
| E | JPQL query | Tùy | Query có thể chạy SQL dù entity đã managed |

Nếu đang test **scope**, dùng `assertSame`, `assertNotSame`, `contains`. Nếu đang test **query performance**, đo SQL/rows/latency với config cache rõ ràng.

Với Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger là provider-specific; bind logs có thể chứa dữ liệu nhạy cảm, chỉ bật trong môi trường kiểm soát.

---

## 35. Lựa chọn context scope theo use case

| Use case | Scope nên cân nhắc | Lý do |
| --- | --- | --- |
| HTTP CRUD stateless | Transaction-scoped | Boundary rõ, giảm stale state |
| Read API DTO | Theo service/query | Không đẩy managed entities ra ngoài |
| Batch import | Theo chunk/transaction được kiểm soát | Giới hạn memory và transaction duration |
| Wizard nhiều bước | Thường DTO/draft; extended nếu thực sự cần | Tránh giữ managed state quá lâu |
| Stateful Jakarta EE workflow | Extended context nếu đúng yêu cầu | Duy trì identity qua nhiều transaction |
| Long-running admin session | Không mặc định giữ EM mở | Stale/concurrency/memory |
| Cache reference data toàn app | Shared/application cache | L1 không phải global cache |
| Async/background job | Context riêng theo job/chunk | Thread safety và cleanup |

Đừng giữ một EntityManager mở nhiều phút chỉ để tránh gọi lại `find`. Thường tốt hơn là lưu command/DTO, rồi mở transaction mới khi người dùng thực sự save.

## 36. Các ngộ nhận thường gặp

**“L1 cache tồn tại trong EntityManagerFactory.”** Không. EntityManagerFactory tạo/quản lý factories/resources; managed identity thuộc persistence context.

**“Commit luôn clear context.”** Không đúng với application-managed/extended contexts. Phải biết scope.

**“Flush sẽ giải phóng bộ nhớ.”** Không. Flush đồng bộ SQL, entities vẫn managed.

**“Clear lưu hết thay đổi trước khi detach.”** Không. Pending changes chưa flush có thể bị bỏ.

**“Gọi find lại chắc chắn đọc DB mới nhất.”** Không. Context có thể trả managed instance đang giữ.

**“Evict L2 làm entity đang managed biến mất khỏi L1.”** Không. Hai lớp cache khác nhau.

**“CacheRetrieveMode.BYPASS chắc chắn bỏ L1.”** Không. Hints shared-cache không thay thế entity identity semantics.

**“Có @Version thì entity tự refresh khi transaction khác commit.”** Không. Version giúp kiểm soát ghi, không push state vào các contexts.

**“Entity detached không còn dữ liệu.”** Không. Nó giữ những giá trị đã được nạp; chỉ không còn managed.

**“EntityManager singleton có thể thay application cache.”** Không. Nó không thread-safe và giữ state stale/memory không kiểm soát.

**“JPQL không bao giờ chạy SQL nếu entity ở L1.”** Sai. L1 không phải query-result cache.

**“OSIV nghĩa là transaction vẫn mở đến khi JSON được serialize.”** Không. Context có thể mở ngoài phạm vi transaction.

## 37. Bảng lỗi và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `find` trả quantity cũ | Managed instance trong L1 | Refresh hoặc context/scope mới |
| Cùng ID nhưng Java object khác | Hai contexts hoặc clear rồi find | Identity theo context |
| `clear` rồi commit không lưu | Dirty state đã detach trước flush | Flush trước clear hoặc đổi workflow |
| `flush` xong memory vẫn cao | Managed entities còn trong context | Clear/detach/chunk |
| Lazy getter lỗi sau close | Association chưa initialized | Fetch/map DTO trong context |
| DTO vẫn kích hoạt SQL | DTO chứa proxy/entity | Dùng nested DTO/scalar |
| Sửa object không ghi DB | Object detached | Reattach bằng merge/command đúng |
| Merge xong sửa object cũ | Không dùng managed copy | Dùng giá trị merge trả về |
| Bulk UPDATE nhưng entity vẫn cũ | Bulk DML bypass managed state | Refresh/clear theo kế hoạch |
| Evict L2 rồi find vẫn ra object cũ | L1 vẫn quản lý entity | Xem L1 scope, refresh |
| BYPASS nhưng không có SELECT | L1 identity map | Phân biệt L1 và L2 |
| Memory tăng trong batch | Context giữ nhiều entities | Flush+clear/chunk |
| Lỗi khi dùng EM ở nhiều threads | EntityManager không thread-safe | Context riêng per thread/unit |
| Spring field EM có state khó hiểu | Proxy và transaction binding | Kiểm tra scope/OSIV |
| Optimistic conflict sau workflow dài | Extended context stale | Đọc lại/retry trong context mới |
| Test không thấy SQL vì cache | Fixture còn L1/L2 | New context, cache config |
| Query vẫn chạy SQL với entity managed | L1 không cache tất cả query results | Phân biệt query và identity |
| State khác giữa hai reads | Isolation và context state | Quy định consistency |
| EntityManager bị leak | Không close application-managed EM | try/finally/lifecycle ownership |

---

## 38. Bài tập có lời giải

### Bài 1. Hai lần find

~~~java
InventoryItem a = em.find(InventoryItem.class, id);
InventoryItem b = em.find(InventoryItem.class, id);
~~~

**Đáp án:** Trong cùng context, `a == b` thường true vì JPA quản lý entity identity.

### Bài 2. Hai EntityManagers

**Đáp án:** Hai managed instances độc lập dù cùng ID và factory. Shared L2 có thể giúp đọc nhưng không biến chúng thành cùng Java object.

### Bài 3. Flush rồi contains

**Đáp án:** Flush không detach, entity vẫn có thể managed.

### Bài 4. Clear rồi find

**Đáp án:** Object trước clear detached; object sau find là managed instance mới.

### Bài 5. Thay đổi rồi clear ngay

**Đáp án:** Pending update có thể bị bỏ nếu chưa flush. Clear không tự commit.

### Bài 6. Commit application-managed EM

**Đáp án:** Context có thể tiếp tục tồn tại nếu EntityManager chưa close.

### Bài 7. Commit transaction-scoped context

**Đáp án:** Context transaction-scoped thường kết thúc cùng transaction, khác extended/application-managed.

### Bài 8. @Version có tự refresh?

**Đáp án:** Không. Version giúp phát hiện stale write, không làm context nhận update từ nơi khác ngay lập tức.

### Bài 9. Bulk JPQL UPDATE

**Đáp án:** Managed entities trong context có thể vẫn giữ state cũ; cân nhắc flush/clear/refresh và versioning.

### Bài 10. Detached update

**Đáp án:** Sửa detached object không tự được dirty checking. Dùng managed entity hoặc merge/command theo transaction.

### Bài 11. CacheRetrieveMode.BYPASS

**Đáp án:** Hướng tới shared cache; không bảo đảm bỏ qua managed instance trong L1.

### Bài 12. Evict L2

**Đáp án:** Không detach managed entity trong context đang mở.

### Bài 13. Lazy sau close

**Đáp án:** Values đã nạp vẫn có thể dùng, lazy association chưa nạp có thể lỗi. Map DTO trước khi rời boundary.

### Bài 14. Nhiều entities trong batch

**Đáp án:** Context có thể giữ nhiều objects/snapshots gây tăng memory. Dùng projection/chunk hoặc flush+clear phù hợp.

### Bài 15. Flush nhưng không clear

**Đáp án:** Entity vẫn managed; memory chưa chắc giảm.

### Bài 16. Clear mà vẫn muốn sửa entity cũ

**Đáp án:** Entity đã detached, cần tải lại/merge hoặc đổi thiết kế scope.

### Bài 17. OSIV

**Đáp án:** Có thể giữ EntityManager qua HTTP request, nhưng service transaction không nhất thiết còn active trong serializer.

### Bài 18. Spring @PersistenceContext

**Đáp án:** Thường inject proxy điều phối theo transaction/thread, không phải một persistence context global.

### Bài 19. Query JPQL với entity đã ở L1

**Đáp án:** Query có thể chạy SQL, nhưng entity materialization tôn trọng managed instance cùng identity.

### Bài 20. Transaction isolation

**Đáp án:** L1 state và database snapshot là hai cơ chế khác nhau; clear/context mới không tự bảo đảm thấy latest state dưới mọi isolation modes.

### Bài 21. Application-managed EM dùng trong nhiều threads

**Đáp án:** Không an toàn vì EntityManager không thread-safe. Sử dụng context riêng theo task/request.

### Bài 22. contains và isLoaded

**Đáp án:** `contains` kiểm tra managed membership; `isLoaded` kiểm tra load state của entity/attribute.

### Bài 23. Clear có xóa row DB không?

**Đáp án:** Không. Clear detach entity khỏi persistence context, không thực hiện DELETE.

### Bài 24. Tại sao DTO thường an toàn sau service?

**Đáp án:** Một DTO không chứa entity/proxy đã được tạo hoàn chỉnh có thể dùng mà không cần context tiếp tục mở.

## 39. Checklist thiết kế persistence context scope

Trước khi hoàn tất một use case JPA, hãy hỏi:

1. EntityManager được tạo bởi application, container hay Spring?
2. Persistence context là transaction-scoped, extended hay application-managed?
3. Context bắt đầu và kết thúc khi nào?
4. Entity nào thực sự managed?
5. Có transaction active khi flush/ghi không?
6. Sau commit, context còn sống không?
7. Có pending changes trước clear/detach không?
8. Có dùng merge và xử lý managed copy đúng không?
9. Có lazy associations được truy cập sau close không?
10. DTO có chứa entity/proxy JPA không?
11. Có N+1 trong mapper không?
12. Có concurrent transactions làm context stale không?
13. `@Version` có đáp ứng yêu cầu concurrent updates không?
14. Có bulk DML/native SQL làm L1 stale không?
15. Khi cần mới nhất, dùng refresh hay một context mới?
16. Đã phân biệt L1 với shared L2 cache chưa?
17. Có dùng CacheRetrieveMode và kỳ vọng sai về L1 không?
18. Có batch import/read giữ quá nhiều entities không?
19. Có cần flush+clear hoặc chunk transaction không?
20. EntityManager có bị chia sẻ giữa threads không?
21. Có cleanup/rollback/close rõ ràng không?
22. Test có dùng context sạch và fixture committed không?
23. OSIV có đang che giấu lazy-loading ngoài service không?
24. Query performance có được đo với cache settings rõ không?
25. Long-lived context có thật sự cần thiết hơn một unit of work ngắn không?

## 40. Kết luận

**Persistence context là ranh giới quản lý entity của JPA**, đồng thời cung cấp first-level cache/identity map.

~~~text
                      EntityManagerFactory
                               |
                +--------------+--------------+
                |                             |
                v                             v
         EntityManager A               EntityManager B
                |                             |
                v                             v
         Persistence PC A              Persistence PC B
                |                             |
         Item#101 object A              Item#101 object B
         identity + state               identity + state
                |                             |
                +--------------+--------------+
                               |
                               v
                            Database

Trong cùng một context:
    cùng entity identity -> cùng managed instance

Giữa hai contexts:
    managed instances độc lập, có thể khác snapshot

Khi context kết thúc/clear/detach:
    object không còn được context đó dirty-check
~~~

Các nguyên tắc quan trọng:

- **L1 là theo persistence context**, không phải cache toàn cục.
- **`find()` có thể trả instance đã managed**, không bắt buộc SELECT lại.
- **`flush()` đồng bộ SQL nhưng không detach**.
- **`clear()` và `detach()` ngừng quản lý**, không tự flush/commit.
- **`close()` kết thúc application-managed context**.
- **`commit()` có tác động tới transaction, còn managed lifecycle phụ thuộc context scope**.
- **`refresh()` có thể nạp lại managed state**, nhưng có thể ghi đè pending edits.
- **`@Version` bảo vệ stale writes**, không tự làm mới những contexts khác.
- **Bulk DML, lazy loading, large batches và long-lived contexts** đòi hỏi kế hoạch quản lý state/memory nhất quán.
- **L2 cache/query cache không thay thế identity và dirty checking của L1**.
- EntityManager cần ownership, transaction scope, thread safety và cleanup rõ ràng.

**Hãy xem persistence context là phạm vi lưu giữ và quản lý entity của một đơn vị công việc, không phải kho cache toàn ứng dụng. Biết chính xác nó tồn tại đến khi nào là điều kiện để ứng dụng JPA đúng dữ liệu, tránh stale state và kiểm soát bộ nhớ.**
