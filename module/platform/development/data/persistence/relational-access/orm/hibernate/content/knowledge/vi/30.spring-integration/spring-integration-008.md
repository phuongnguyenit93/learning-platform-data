# Phân biệt save, saveAndFlush, persist và merge trong Spring Data JPA và Hibernate

## 1. Bốn tên phương thức, nhưng không phải bốn cách ghi dữ liệu giống nhau

Trong ứng dụng Spring Boot dùng Spring Data JPA và Hibernate ORM, bốn lệnh sau xuất hiện rất thường xuyên:

~~~java
entityManager.persist(order);
entityManager.merge(order);
orderRepository.save(order);
orderRepository.saveAndFlush(order);
~~~

Chúng đều có thể tham gia vào việc đưa thay đổi của entity xuống cơ sở dữ liệu, nhưng **khác nhau ở đối tượng truyền vào, đối tượng được trả về, trạng thái entity trong persistence context, thời điểm đồng bộ SQL và trách nhiệm giao dịch**.

Những câu hỏi thực tế thường gặp:

- Tạo đơn hàng mới nên gọi persist hay save?
- Đã lấy entity bằng repository.findById(), sửa một field rồi có cần save nữa không?
- Vì sao save trả về object khác object truyền vào?
- Vì sao sau save chưa thấy câu INSERT/UPDATE trong SQL log?
- saveAndFlush có làm transaction commit và dữ liệu được ứng dụng khác nhìn thấy ngay không?
- Vì sao entity có ID tự gán lại bị merge hoặc phát SELECT trước INSERT?
- Vì sao merge một DTO chuyển thành entity có thể xóa nhầm field/collection?
- Khi nào dùng flush để phát hiện lỗi database sớm?

Bài học thuộc chương **Tích hợp Spring** của module Hibernate ORM. Các ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x, Spring Data JPA và PostgreSQL. Chi tiết SQL và thời điểm cấp ID phụ thuộc generator, flush mode, provider và transaction; không coi các truy vấn minh họa là một cam kết về số statement.

### Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích vòng đời transient/new, managed, detached và removed.
2. Mô tả chính xác persist, merge, save và saveAndFlush.
3. Phân biệt **đưa entity vào persistence context**, **flush SQL** và **commit transaction**.
4. Hiểu quy tắc Spring Data JPA xác định entity mới: ID, @Version và Persistable.isNew().
5. Viết service @Transactional đúng ranh giới nghiệp vụ.
6. Tránh merge detached graph hoặc dữ liệu đầu vào không đầy đủ làm mất dữ liệu.
7. Phân biệt dirty checking với thao tác gọi save nhiều lần.
8. Hiểu cascade, optimistic locking, generated ID, batch writes và lỗi constraint.
9. Kiểm thử identity/state và SQL thực tế bằng Hibernate/PostgreSQL.
10. Chọn đúng API cho từng tình huống, thay vì gọi saveAndFlush theo thói quen.

## 2. Bảng so sánh nhanh

| Phương thức | API sở hữu | Vai trò chính | Đối tượng trả về | Có luôn flush ngay không? | Có commit không? |
|---|---|---|---|---|---|
| persist(entity) | Jakarta Persistence EntityManager | Đưa **entity mới** vào trạng thái managed | void | Không bảo đảm; INSERT có thể xảy ra sớm tùy ID generator | Không |
| merge(entity) | Jakarta Persistence EntityManager | Sao chép state từ entity new/detached vào instance managed | Instance managed | Không bảo đảm | Không |
| save(entity) | Spring Data JPA repository | Chọn persist hoặc merge dựa trên nhận diện entity mới | T trả về từ persist path hoặc merge path | Không chủ động gọi flush | Không tự commit nếu đang ở outer transaction; repository có transaction của nó |
| saveAndFlush(entity) | Spring Data JPA repository | save rồi flush persistence context | T được trả từ save | Có gọi flush một cách tường minh | Không tự biến thành commit của outer transaction |

**Quy tắc then chốt:** save là API cấp repository, persist và merge là API quản lý entity state, còn flush là hành động đồng bộ persistence context với database trong transaction. Commit là một ranh giới khác.

### 2.1. Bốn dòng không tương đương nhau

~~~java
entityManager.persist(order);       // order trở thành managed nếu hợp lệ.

PurchaseOrder managed =
    entityManager.merge(order);     // managed mới là instance phải dùng tiếp.

PurchaseOrder saved =
    orderRepository.save(order);    // Có thể persist hoặc merge.

PurchaseOrder flushed =
    orderRepository.saveAndFlush(order);
// save trước, rồi flush cả persistence context.
~~~

Không suy ra từ việc tên phương thức chứa chữ save rằng SQL UPDATE đã được chạy. Cũng không suy ra từ chữ Flush rằng transaction đã được commit.

## 3. Entity lifecycle: nền tảng để hiểu sự khác biệt

JPA/Hibernate quản lý entity theo trạng thái:

| Trạng thái | Ý nghĩa | Tự được dirty checking? |
|---|---|---|
| New / transient | Java object chưa được quản lý bởi persistence context | Không |
| Managed / persistent | Object có identity gắn với EntityManager/Session hiện tại | Có, theo mapping và flush mode |
| Detached | Từng managed nhưng không còn thuộc context hiện tại | Không |
| Removed | Được đánh dấu xóa trong persistence context hiện tại | Delete được đồng bộ khi flush |

Sơ đồ đơn giản:

~~~mermaid
flowchart LR
    A[New / transient] -->|persist| B[Managed]
    A -->|merge; trả instance khác hoặc managed| B
    B -->|clear / detach / close| C[Detached]
    C -->|merge; sao chép state| B
    B -->|remove| D[Removed]
    B -->|commit/flush| E[(Database SQL)]
    D -->|flush| E
~~~

Merge **không làm đối tượng detached ban đầu tự trở thành managed**; nó tìm hoặc tạo một instance managed và sao chép state vào instance đó. Đường từ detached qua merge trong sơ đồ biểu diễn dữ liệu được chuyển sang instance managed, không phải object identity được chuyển trạng thái tại chỗ.

### 3.1. Persistence context là identity map

Trong một EntityManager:

~~~java
PurchaseOrder first = em.find(PurchaseOrder.class, 101L);
PurchaseOrder second = em.find(PurchaseOrder.class, 101L);

assert first == second;
assert em.contains(first);
~~~

Với cùng entity type và primary key, Hibernate thường trả cùng managed instance trong context. Nếu first được sửa, dirty checking có thể phát hiện thay đổi khi flush.

### 3.2. Đối tượng detached không được tự theo dõi

~~~java
PurchaseOrder order;
try (EntityManager em = emf.createEntityManager()) {
    order = em.find(PurchaseOrder.class, 101L);
}

// EntityManager đã đóng; order detached.
order.changeNote("Đã kiểm tra");
~~~

Chỉ sửa object detached không khiến Hibernate tự update database. Muốn áp dụng thay đổi phải đi qua một transaction và instance managed, có thể bằng việc load lại rồi sửa, hoặc merge với hiểu biết rõ về state được sao chép.

## 4. Entity mẫu xuyên suốt

Giả sử có đơn hàng:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "order_id_gen")
    @SequenceGenerator(
        name = "order_id_gen",
        sequenceName = "purchase_order_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 40)
    private String status;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String status,
            BigDecimal totalAmount,
            Instant createdAt) {
        this.status = status;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public List<OrderItem> getItems() { return items; }

    public void markPaid() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Chỉ đơn DRAFT mới có thể chuyển PAID");
        }
        status = "PAID";
    }
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    protected OrderItem() {}
}
~~~

Các public class nên nằm trong file Java riêng. Mã chỉ minh họa lifecycle, không phải model thương mại hoàn chỉnh. Ví dụ parent dùng SEQUENCE để tách rõ thời điểm có ID và thời điểm INSERT; child dùng IDENTITY để minh họa rằng thời điểm thực thi SQL phụ thuộc generator.

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
    extends JpaRepository<PurchaseOrder, Long> {
}
~~~

## 5. persist(): thêm đối tượng mới vào persistence context

API JPA:

~~~java
void persist(Object entity);
~~~

Với entity **new/transient**, EntityManager.persist() khiến entity trở thành managed. Hibernate theo dõi nó để tạo INSERT phù hợp khi đồng bộ SQL.

~~~java
@Transactional
public Long createOrder(EntityManager em) {
    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("150.00"), Instant.now()
    );

    em.persist(order);

    assert em.contains(order);
    return order.getId();
}
~~~

Nếu generator là SEQUENCE như entity mẫu, Hibernate có thể xin/đặt ID trước INSERT, kể cả INSERT thật được trì hoãn tới flush. Vì vậy **ID khác null không chứng minh row đã được commit**.

### 5.1. persist là thao tác trên chính instance truyền vào

~~~java
PurchaseOrder original = new PurchaseOrder(
    "DRAFT", new BigDecimal("10.00"), Instant.now());

em.persist(original);
assert em.contains(original);
~~~

Khác merge, persist không trả instance thay thế; chính original là managed trong persistence context sau lời gọi thành công.

### 5.2. persist không có nghĩa INSERT phải chạy ở đúng dòng gọi

Với SEQUENCE, có thể quan sát:

~~~text
persist(order)
  -> Hibernate lấy ID từ sequence nếu cần
  -> Order ở managed state
  -> INSERT được đưa vào action queue
  -> flush hoặc commit: INSERT
~~~

Với GenerationType.IDENTITY, nhiều phiên bản/cấu hình Hibernate thường cần thực thi INSERT sớm để lấy generated key từ DB. Timing còn phụ thuộc transaction và flush mode. **Không viết logic nghiệp vụ dựa trên giả định mọi persist đều hoàn toàn trì hoãn SQL tới commit.**

### 5.3. persist trên detached entity có thể lỗi

~~~java
PurchaseOrder detached = /* entity đã được tải từ context cũ */;
em.persist(detached);
~~~

Đây không phải cách “ghi cập nhật detached”. JPA có thể ném EntityExistsException hoặc PersistenceException tại persist/flush/commit; Hibernate có thể báo detached entity passed to persist. Nếu muốn sửa dữ liệu hiện có, thường tải lại managed entity rồi thay đổi, hoặc sử dụng merge khi hiểu rõ toàn bộ state.

### 5.4. persist trên object có ID không luôn đồng nghĩa insert thành công

Với assigned ID hoặc mapping đặc biệt, instance có ID không null có thể vẫn new. Ngược lại, ID trùng hàng hiện có có thể gây PK conflict hoặc lỗi từ provider. Không dùng persist như một cách đảm bảo insert-idempotent/upsert.

## 6. merge(): sao chép state vào một instance managed

API JPA:

~~~java
<T> T merge(T entity);
~~~

Merge nhận state của một entity new hoặc detached và phối hợp với persistence context để đưa state đó vào một instance managed. Giá trị trả về mới là instance cần dùng tiếp.

~~~java
PurchaseOrder detached = /* object thuộc context cũ */;

PurchaseOrder managed = em.merge(detached);

System.out.println(em.contains(detached)); // Thường false
System.out.println(em.contains(managed));  // true
~~~

Nếu detached chưa managed ở context hiện tại, managed thường là object **khác reference**. Nếu merge nhận ngay một entity đã managed, nó có thể trả lại cùng instance; không dựa vào điều đó để nói merge luôn copy hoặc luôn trả instance mới.

### 6.1. Bản sao state, không phải chuyển ownership

~~~mermaid
flowchart TD
    A[Detached Order id=101, status=PAID] -->|merge| B[Persistence context]
    B --> C{Có managed Order id=101?}
    C -->|Có| D[Copy state lên managed instance hiện có]
    C -->|Không| E[Load hoặc tạo managed instance phù hợp]
    E --> D
    D --> F[Trả managed reference]
    F --> G[Dirty checking / flush -> SQL]
    A --> H[Detached input vẫn detached]
~~~

Hibernate có thể phát SELECT để tìm state hiện có, nhưng **không bảo đảm mọi merge luôn SELECT**. Điều đó phụ thuộc persistence context đã có entity chưa, kiểu ID, version, cache, mapping và provider.

### 6.2. Sau merge phải dùng return value

Sai:

~~~java
em.merge(detached);
detached.markPaid(); // Sửa tiếp object không managed.
~~~

Đúng:

~~~java
PurchaseOrder managed = em.merge(detached);
managed.markPaid();
~~~

Tương tự, với Spring Data save có thể chạy nhánh merge:

~~~java
PurchaseOrder saved = repository.save(detached);
saved.markPaid();
~~~

Điều quan trọng là giữ đối tượng trả về, đặc biệt khi input có thể detached.

### 6.3. Merge không có nghĩa “UPDATE ngay”

Merge có thể:

- Sao chép state vào một managed instance đã có.
- Gây lookup SELECT hoặc không, tùy tình huống.
- Tạo managed copy của một entity new và cuối cùng INSERT.
- Chưa tạo SQL UPDATE ngay, vì dirty checking và flush quyết định thời điểm.
- Không UPDATE nếu không phát hiện khác biệt cần đồng bộ.

Vì vậy merge không đồng nghĩa trực tiếp với JDBC UPDATE, và cũng không phải một SQL UPSERT.

### 6.4. Cảnh báo khi merge detached entity không đầy đủ

Giả sử request JSON chỉ có:

~~~json
{
  "id": 101,
  "status": "PAID"
}
~~~

Code chuyển request thành PurchaseOrder:

~~~java
PurchaseOrder order = new PurchaseOrder();
// Giả sử mapper đặt id=101, status=PAID,
// còn totalAmount, createdAt, items không có hoặc mặc định.

repository.save(order);
~~~

Nếu save chọn merge, các field không được client cung cấp có thể được hiểu là **state mới** của object và được copy lên managed entity. Những giá trị null/mặc định có thể ghi đè dữ liệu cũ hoặc gây constraint violation. Collection bị thay thế/trống còn có thể gây xóa orphan khi cascade và orphanRemoval được cấu hình.

**Không merge một “entity stub” từ request PATCH** rồi kỳ vọng Hibernate chỉ cập nhật những thuộc tính có trong JSON. JPA merge sao chép entity state, không phải JSON Patch semantics.

### 6.5. Cách an toàn hơn cho update từng trường

~~~java
@Transactional
public void markPaid(
        Long orderId,
        PurchaseOrderRepository repository) {

    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow(() -> new IllegalArgumentException(
            "Không tìm thấy đơn"));

    order.markPaid();
    // Không cần repository.save(order) nếu vẫn managed.
}
~~~

Với cách này:

1. Load entity managed ở transaction hiện tại.
2. Kiểm tra state/quyền/nghiệp vụ.
3. Thay đổi đúng field cần sửa.
4. Hibernate dirty-check khi flush/commit.

Việc thực hiện có thể cần tenant/authorization checks và handling optimistic locking; không chỉ tin ID từ client.

## 7. save(): Spring Data JPA quyết định persist hay merge

Spring Data JPA repository.save(entity) thường được triển khai bởi SimpleJpaRepository. Logic khái quát:

~~~java
@Transactional
public <S extends T> S save(S entity) {
    if (entityInformation.isNew(entity)) {
        entityManager.persist(entity);
        return entity;
    } else {
        return entityManager.merge(entity);
    }
}
~~~

Đây là **pseudocode tương ứng ý nghĩa triển khai phổ biến** của Spring Data JPA, không phải mã nguồn nguyên văn được cam kết cho mọi phiên bản. Điểm quan trọng là **isNew(entity)**, không phải tên save.

### 7.1. Nhánh new

~~~java
PurchaseOrder order = new PurchaseOrder(
    "DRAFT", new BigDecimal("125.00"), Instant.now());

PurchaseOrder saved = repository.save(order);
~~~

Với ID được generate và chưa có giá trị, Spring Data thường nhận diện entity mới rồi gọi persist. saved là chính instance mới được persist.

### 7.2. Nhánh existing/detached

~~~java
PurchaseOrder detached = /* entity từ persistence context khác */;
PurchaseOrder managed = repository.save(detached);
~~~

Với entity được nhận diện là existing, save gọi merge và trả instance managed của transaction hiện tại. Không nên tiếp tục sửa detached khi đã gọi save mà bỏ qua return value.

### 7.3. save không tự biết ý định INSERT hay UPDATE

Không có một tham số ngầm kiểu:

~~~text
save(..., mode = INSERT_ONLY)
save(..., mode = UPDATE_ONLY)
~~~

Spring Data dựa trên metadata và isNew để chọn API JPA. Một entity có ID không null có thể là một bản ghi mới dùng assigned ID; một entity detached có ID trỏ đến hàng đã bị xóa cũng có behavior phụ thuộc @Version/provider. **Không dùng save để xác nhận row có tồn tại hay không hoặc làm upsert atomic.**

### 7.4. save trả về T, nhưng không chắc cùng reference

~~~java
PurchaseOrder returned = repository.save(input);

boolean sameObject = returned == input;
~~~

Với persist path, thường cùng object. Với merge path của detached input, thường khác. Khi code có thể nhận cả new và detached, hãy sử dụng returned để tránh bug tùy nhánh.

## 8. Spring Data xác định entity mới bằng cách nào?

Cách phổ biến của Spring Data JPA là kiểm tra các dấu hiệu do EntityInformation cung cấp. Quy tắc cơ bản:

1. Nếu có thuộc tính @Version **không phải primitive**, Spring Data JPA thường dùng version null để xác định new.
2. Nếu không có version non-primitive phù hợp, thường dùng ID null/không null.
3. Nếu entity implement Persistable, Spring Data có thể dùng chính phương thức isNew().
4. Với custom EntityInformation/repository factory, ứng dụng có thể định nghĩa behavior khác.

Các quy tắc này là behavior của Spring Data JPA, **không phải** quy tắc chung cho mọi provider của EntityManager.persist/merge.

### 8.1. Generated ID null

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

Một entity vừa new có id=null nên thường được save nhận là new.

### 8.2. Assigned ID đã có trước persist

~~~java
@Entity
public class Country {
    @Id
    private String isoCode;

    private String displayName;
}
~~~

Ứng dụng tạo:

~~~java
Country country = new Country("VN", "Việt Nam");
repository.save(country);
~~~

ID "VN" không null dù row chưa tồn tại. Nếu không có cơ chế isNew khác, Spring Data có thể xem entity là existing và gọi merge. Hibernate có thể phải kiểm tra state hiện có hoặc thực hiện SQL không cần thiết so với persist path. Không thể kết luận rằng ID assigned tự động có nghĩa entity detached.

### 8.3. Nullable @Version giúp xác định new

~~~java
@Entity
public class ReferenceCode {
    @Id
    private String code;

    @Version
    private Long version;
}
~~~

Với code đã có giá trị nhưng version=null, Spring Data JPA thường nhận diện new. Sau persist/flush, provider sẽ quản lý giá trị version theo mapping.

**Không dùng primitive long version cho mục đích phân biệt null và đã tồn tại**, vì primitive long có giá trị mặc định 0 nên không có dấu hiệu null. Spring Data thường fallback sang ID trong tình huống version primitive.

### 8.4. Implement Persistable khi cần chủ động isNew

Một entity dùng assigned ID có thể:

~~~java
import jakarta.persistence.*;
import org.springframework.data.domain.Persistable;

@Entity
public class ReferenceCode implements Persistable<String> {
    @Id
    private String code;

    private String label;

    @Transient
    private boolean isNew = true;

    protected ReferenceCode() {}

    public ReferenceCode(String code, String label) {
        this.code = code;
        this.label = label;
    }

    @Override
    public String getId() {
        return code;
    }

    @Override
    public boolean isNew() {
        return isNew;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        isNew = false;
    }
}
~~~

Ở đây @Transient là jakarta.persistence.Transient, không phải Java transient keyword. Flag khởi tạo true cho object mới trong Java; @PostPersist và @PostLoad chuyển flag sang false sau khi đã được persist/load.

Lưu ý:

- isNew chỉ phục vụ **nhận diện nhánh của repository.save**. Nó không khóa uniqueness hoặc kiểm tra atomic existence.
- Nếu serialize/deserialize entity qua các tầng, flag có thể không giữ state đúng.
- Nếu application tự tạo detached copy với assigned ID nhưng isNew=true, save có thể gọi persist sai.
- Không dùng Persistable.isNew() như một lời bảo đảm row chắc chắn chưa tồn tại ở database.

### 8.5. Không dựa vào equals/hashCode để xác định new

Lombok @Data hoặc equals/hashCode dựa trên ID mutable có thể gây vấn đề với Set/collection trước và sau khi entity được cấp ID. Những phương thức này không phải cơ chế chính thức Spring Data dùng thay cho entityInformation.isNew. Hãy thiết kế entity identity ổn định theo domain và Hibernate proxy semantics.

## 9. saveAndFlush(): save rồi flush, không phải commit

Spring Data JPA triển khai phổ biến tương đương:

~~~java
@Transactional
public <S extends T> S saveAndFlush(S entity) {
    S result = save(entity);
    flush();
    return result;
}
~~~

Vì vậy:

- saveAndFlush vẫn gọi nhánh persist/merge tùy isNew.
- Nó trả instance phù hợp như save.
- Sau save, nó yêu cầu EntityManager.flush().
- Nó **không định nghĩa một transaction commit độc lập** nếu caller đã mở transaction.

### 9.1. Flush đồng bộ action queue

Trong một persistence context, Hibernate có thể giữ các thao tác INSERT/UPDATE/DELETE để gửi đến DB khi cần. flush yêu cầu đồng bộ các pending changes, với thứ tự SQL theo action queue và constraints của provider.

~~~java
@Transactional
public void example(PurchaseOrderRepository repository) {
    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("250.00"), Instant.now());

    repository.save(order);
    // Không bảo đảm mọi INSERT đều đã chạy ngay ở dòng này.

    repository.flush();
    // Các thay đổi pending được đồng bộ với DB trong transaction.
}
~~~

### 9.2. Flush của **toàn persistence context**

Một bẫy quan trọng:

~~~java
@Transactional
public void example(
        CustomerRepository customers,
        PurchaseOrderRepository orders) {

    Customer customer = customers.findById(10L).orElseThrow();
    customer.changeName("Tên mới"); // managed, đang dirty.

    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("20.00"), Instant.now());

    orders.saveAndFlush(order);
}
~~~

saveAndFlush(order) không có nghĩa “chỉ flush đúng order”. Lời gọi EntityManager.flush() đồng bộ **mọi thay đổi managed pending** trong persistence context liên quan, bao gồm Customer đang dirty.

Nếu Customer vi phạm constraint, exception có thể phát sinh tại saveAndFlush(order), khiến developer tưởng Order gây lỗi. Cần xem SQL và constraint thực sự thất bại.

### 9.3. Flush không làm dữ liệu được transaction khác nhìn thấy ngay

Timeline:

~~~mermaid
sequenceDiagram
    participant S as Spring Service
    participant EM as EntityManager
    participant DB as Database
    participant O as Transaction khác
    S->>EM: saveAndFlush(order)
    EM->>DB: INSERT/UPDATE trong transaction T1
    DB-->>EM: SQL hoàn tất
    O->>DB: SELECT cùng row
    DB-->>O: Theo isolation; thường chưa thấy uncommitted của T1
    S->>DB: COMMIT T1
    DB-->>S: Commit thành công
    O->>DB: SELECT mới
    DB-->>O: Có thể thấy dữ liệu đã commit
~~~

Ở PostgreSQL READ COMMITTED, một transaction khác không đọc các thay đổi chưa commit của T1. Ngay cả sau commit, snapshot của transaction khác có thể khác tùy isolation. **flush ≠ commit ≠ visibility toàn hệ thống**.

### 9.4. Rollback sau flush vẫn có thể hủy SQL

~~~java
@Transactional
public void createAndAbort(
        PurchaseOrderRepository repository) {
    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("10.00"), Instant.now());

    repository.saveAndFlush(order);

    throw new IllegalStateException("Hủy giao dịch");
}
~~~

Theo mặc định phổ biến của Spring @Transactional, unchecked exception khiến transaction rollback. Dù INSERT đã được gửi xuống DB ở flush, row có thể không tồn tại sau rollback. Các hiệu ứng **ngoài DB transaction** như gửi email hoặc HTTP call không tự rollback theo, nên không kích hoạt side effect chỉ dựa vào flush.

### 9.5. Lỗi vẫn có thể xuất hiện ở commit

saveAndFlush thường giúp phát hiện sớm một số lỗi SQL/constraints, nhưng không đảm bảo mọi lỗi DB đã lộ:

- Deferred constraint có thể được kiểm tra tại commit.
- Transaction serialization/deadlock có thể thất bại muộn.
- Trigger, stored procedure hoặc transaction coordination có behavior riêng.
- Sau flush vẫn có code khác tạo thay đổi mới trước commit.

Không dùng saveAndFlush như một lời bảo đảm “giao dịch chắc chắn thành công”.

## 10. Flush mode: Hibernate có thể tự flush khi cần

JPA có FlushModeType.AUTO và COMMIT; Hibernate còn có các flush modes provider-specific như ALWAYS hoặc MANUAL tùy API/version.

### 10.1. AUTO không có nghĩa chỉ flush ở commit

Với flush mode AUTO, Hibernate có thể flush trước một số query để bảo đảm query nhìn thấy state phù hợp theo contract. Ví dụ:

~~~java
@Transactional
public long countPaid(
        EntityManager em,
        PurchaseOrderRepository repository) {

    PurchaseOrder order = new PurchaseOrder(
        "PAID", new BigDecimal("99.00"), Instant.now());
    repository.save(order);

    return em.createQuery("""
        select count(o)
        from PurchaseOrder o
        where o.status = 'PAID'
        """, Long.class).getSingleResult();
}
~~~

Hibernate có thể quyết định flush trước query vì query phụ thuộc table có changes pending. Không phụ thuộc saveAndFlush chỉ để làm một SELECT cùng transaction thấy dữ liệu mới, trừ khi yêu cầu và flush mode cụ thể đòi hỏi.

### 10.2. FlushModeType.COMMIT không phải “không bao giờ flush”

COMMIT chủ yếu điều chỉnh lúc synchronization trước query; transaction commit vẫn thường cần flush pending changes. JPA có những trường hợp effect của changes với query trước commit không được bảo đảm như AUTO. Khi cần hành vi cụ thể, kiểm thử với Hibernate version/DB thực tế.

### 10.3. Read-only và MANUAL

Spring @Transactional(readOnly=true) có thể áp dụng các tối ưu Hibernate như flush mode/read-only handling tùy phiên bản và configuration. Nó **không phải giấy phép sửa entity rồi mong flush tự diễn ra như transaction ghi**.

Nếu service thực hiện update, dùng @Transactional phù hợp và không phụ thuộc vào một read-only context để save/flush. readOnly không phải constraint bảo mật tuyệt đối của database trong mọi môi trường.

## 11. Transaction boundary của Spring quyết định commit

Spring Data JpaRepository thường áp dụng transaction semantics cho các phương thức CRUD: phương thức đọc thường read-only và các write methods như save/saveAndFlush có transaction được định nghĩa ở repository implementation.

Tuy nhiên nếu một service đã có @Transactional, repository method **tham gia outer transaction** theo propagation mặc định.

### 11.1. Gọi repository trực tiếp không có outer transaction

~~~java
PurchaseOrder saved = repository.save(order);
~~~

Trong cấu hình Spring Data JPA thông thường, save sẽ chạy trong repository transaction. Khi repository method hoàn tất, nếu đó là transaction được tạo bởi repository và không bị lỗi, Spring sẽ commit transaction; flush có thể xảy ra tại commit.

Vì thế sau khi save trả về ở tầng không có transaction bao ngoài, database thường đã được commit — nhưng **đó là do transaction interceptor của repository**, không phải bản thân API save định nghĩa “commit ngay”.

### 11.2. Có outer transaction: cả hai save cùng commit hoặc rollback

~~~java
@Service
public class OrderApplicationService {
    private final PurchaseOrderRepository orders;
    private final AuditRepository audits;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            AuditRepository audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public Long placeOrder(PurchaseOrder order) {
        PurchaseOrder saved = orders.save(order);
        audits.save(AuditEntry.forNewOrder(saved.getId()));
        return saved.getId();
    }
}
~~~

Hai repository thường tham gia cùng transaction. Nếu Audit insert hoặc một validation cuối transaction thất bại, cả hai write có thể rollback. Không gọi saveAndFlush chỉ để cố commit Order trước Audit; làm vậy phá vỡ mục tiêu atomicity nếu thật sự tách transaction.

### 11.3. self-invocation và @Transactional

~~~java
@Service
class PaymentService {
    public void execute() {
        persistPayment(); // Self-invocation.
    }

    @Transactional
    public void persistPayment() {
        // ...
    }
}
~~~

Trong cấu hình Spring proxy-based thông thường, lời gọi từ this tới method cùng bean không đi qua transaction proxy, nên annotation có thể không được áp dụng như mong muốn. Hãy đặt transaction boundary trên public service method được gọi qua Spring bean/proxy hoặc sử dụng thiết kế transaction rõ khác.

### 11.4. Transaction REQUIRES_NEW thay đổi bài toán

Nếu một write được bọc trong @Transactional(propagation = REQUIRES_NEW), nó có transaction/commit độc lập với caller theo semantics Spring. Đây là **quyết định transaction propagation**, không phải khác biệt giữa save và saveAndFlush. Không dùng REQUIRES_NEW chỉ để “save chắc chắn xuống DB” khi nghiệp vụ cần atomic transaction.

## 12. Dirty checking: entity managed không nhất thiết phải save lại

Một cách update phổ biến:

~~~java
@Transactional
public void pay(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();

    order.markPaid();
}
~~~

Khi order đang managed trong persistence context, Hibernate phát hiện thay đổi và phát UPDATE khi flush/commit nếu mapping và trạng thái transaction phù hợp.

### 12.1. Không bắt buộc thêm save ở cuối

~~~java
@Transactional
public void pay(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow();

    order.markPaid();
    repository.save(order); // Thường không cần để dirty checking hoạt động.
}
~~~

Gọi save trên một managed entity có thể không tạo thêm UPDATE nếu dirty checking thấy state giống nhau, nhưng nó không đem lại điều kiện bắt buộc để entity được đồng bộ. Đừng biến save thành một lệnh “đánh dấu dirty” thủ công.

### 12.2. Nhưng khi nào vẫn cần save?

Nếu order là **new/transient** và chưa được persist, gọi save là cách thông thường ở repository layer. Nếu bạn chủ ý dùng detached entity và muốn merge, save có thể phù hợp, nhưng phải sử dụng returned managed instance và cân nhắc dữ liệu đầy đủ/concurrency.

### 12.3. L1 context có ranh giới

~~~java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.markPaid();
~~~

Nếu code chạy ngoài một service transaction và transaction đọc của repository đã kết thúc, order có thể detached. Thay đổi sau findById() **không được đảm bảo sẽ tự flush**. Đó là lý do service @Transactional quan trọng hơn việc gọi save liên tục theo thói quen.

### 12.4. Đừng để Open Session in View che lỗi thiết kế

Spring Boot có thể bật Open Session/EntityManager in View trong web app tùy cấu hình. Điều đó kéo dài thời gian persistence context gắn với request, nhưng không biến mọi thao tác sau service trở thành transaction ghi đúng. Nên map DTO và xử lý mutation trong service @Transactional, không phụ thuộc vào việc serializer còn truy cập được lazy association.

## 13. So sánh dòng thời gian save, flush và commit

Một ví dụ:

~~~java
@Transactional
public void create(PurchaseOrderRepository repository) {
    PurchaseOrder a = new PurchaseOrder(
        "DRAFT", new BigDecimal("10.00"), Instant.now());
    repository.save(a);             // A được persist/merge tùy isNew.

    PurchaseOrder b = new PurchaseOrder(
        "DRAFT", new BigDecimal("20.00"), Instant.now());
    repository.saveAndFlush(b);     // Đồng bộ cả A lẫn B nếu cùng context.

    // Code tiếp tục chạy; transaction chưa kết thúc.
}
// Proxy transaction manager có thể flush/commit khi method return.
~~~

Một timeline minh họa với SEQUENCE:

~~~text
T0  Begin transaction
T1  save(A)
    - Lấy/gán ID theo sequence nếu cần
    - A trở thành managed
    - INSERT có thể đang pending

T2  saveAndFlush(B)
    - B trở thành managed
    - Hibernate.flush()
    - INSERT A và INSERT B có thể được gửi đi

T3  Vẫn trong transaction; có thể rollback

T4  Commit
    - Flush nốt pending actions nếu có
    - Database commit, các thay đổi trở thành committed
~~~

Nếu B dùng IDENTITY, insert của B có thể xảy ra sớm hơn T2 để lấy khóa; đây là lý do không mô tả SQL timing bằng một sơ đồ cứng cho mọi generator.

### 13.1. Tại sao SQL log có INSERT trước saveAndFlush?

Với IDENTITY, cần generated key. Với AUTO flush, một query cũng có thể kích hoạt flush trước. Với SQL custom hoặc cascades, provider có thể chủ động thực hiện thao tác sớm hơn. **Đọc SQL log cùng generator/transaction/flush mode**, không chỉ nhìn tên phương thức repository.

### 13.2. Tại sao không có UPDATE dù gọi saveAndFlush?

Nếu trạng thái managed không thay đổi (không dirty) hoặc update không thực sự cần thiết, flush có thể không tạo UPDATE cho entity đó. saveAndFlush yêu cầu đồng bộ pending changes, không bắt buộc phát một câu SQL cho đúng object truyền vào.

## 14. IDENTITY, SEQUENCE, assigned ID và thời điểm có khóa

### 14.1. IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Database phát sinh ID trong INSERT. Hibernate thường phải đưa INSERT tới DB để biết giá trị ID, có thể ảnh hưởng khả năng JDBC batch inserts. Một số timing đặc thù thay đổi theo transaction/flush.

### 14.2. SEQUENCE

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_gen")
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
private Long id;
~~~

Hibernate có thể xin ID từ sequence/optimizer trước INSERT; việc có ID thường không chứng minh SQL INSERT đã chạy hoặc commit.

### 14.3. Assigned ID

~~~java
@Id
private UUID id;
~~~

Ứng dụng tự đặt ID. Đó không phải bằng chứng entity đã tồn tại. Spring Data isNew theo ID đơn thuần có thể chọn merge; cân nhắc nullable @Version hoặc Persistable nếu mô hình cần.

### 14.4. Không kiểm tra tồn tại bằng cách nhìn ID

Sai:

~~~java
if (order.getId() != null) {
    // Chắc chắn row đã tồn tại?
}
~~~

Không đúng: ID có thể đã được gán nhưng transaction chưa commit, hoặc UUID đã tự sinh trước persist. Muốn xác định business identity cần unique constraints, transaction checks hoặc query có chủ đích.

## 15. Optimistic locking và @Version

Với entity:

~~~java
@Version
private Long version;
~~~

Hibernate có thể dùng version trong UPDATE/DELETE để phát hiện xung đột giữa các transaction.

### 15.1. Kịch bản hai người sửa cùng đơn

~~~text
T1 đọc Order #101 version=3
T2 đọc Order #101 version=3
T1 đổi status và commit -> version=4
T2 đổi totalAmount và flush/commit
  -> UPDATE với version=3 không khớp hàng hiện tại
  -> optimistic-lock conflict
~~~

JPA/Hibernate có thể ném OptimisticLockException hoặc Hibernate-specific stale-object exception; Spring có thể chuyển thành một DataAccessException thuộc nhóm optimistic locking. Thời điểm phát hiện thường ở flush/commit.

### 15.2. saveAndFlush có thể giúp phát hiện xung đột sớm hơn

~~~java
@Transactional
public void update(PurchaseOrder detached) {
    repository.saveAndFlush(detached);
    // Nếu update version conflict được thực hiện trong flush,
    // exception có thể xuất hiện tại đây.
}
~~~

Nhưng không bảo đảm mọi conflict đều được phát hiện tại saveAndFlush, vì còn constraints/transaction behavior và những thay đổi tiếp sau. Gọi flush sớm chỉ có ý nghĩa khi cần thực thi SQL trước một bước có phụ thuộc cụ thể.

### 15.3. merge không tự giải quyết conflict

Nếu client gửi entity detached từ lâu, merge có thể cố sao chép state cũ. @Version giúp phát hiện một số stale updates, nhưng không chọn được conflict-resolution business. Không tự retry merge bằng cách bỏ version, vì có thể ghi đè thay đổi của người khác.

### 15.4. Nếu không có @Version

Tùy mapping và SQL, hai transaction cùng update một entity có thể dẫn tới lost update, đặc biệt khi một state stale được merge. Cần đánh giá optimistic locking, explicit locking hoặc cập nhật có điều kiện theo nghiệp vụ; việc chọn save hay merge không phải cơ chế đồng bộ concurrency.

## 16. Cascade: persist và merge có thể lan sang association

Mapping:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderItem> items = new ArrayList<>();
~~~

CascadeType.PERSIST cho phép persist Order lan sang OrderItem new theo quan hệ đã cấu hình. CascadeType.MERGE cho phép merge state của child liên quan khi merge parent.

### 16.1. Tạo aggregate mới

~~~java
PurchaseOrder order = new PurchaseOrder(
    "DRAFT", new BigDecimal("200.00"), Instant.now());
OrderItem item = new OrderItem(/* ... */);

order.addItem(item); // Thiết lập cả hai phía association.
entityManager.persist(order);
~~~

Nếu cascade PERSIST hợp lệ và owning side item.order đã được gán, Hibernate có thể insert Order và Item theo phụ thuộc FK. Nếu không cascade, persist parent không tự động persist mọi new child. Chỉ thêm cascade đúng theo lifecycle ownership, không thêm CascadeType.ALL cho mọi association vì tiện.

### 16.2. Merge detached graph có rủi ro cao hơn merge một scalar

Nếu một Order detached chứa danh sách items không đầy đủ:

~~~text
DB:       [Item A, Item B, Item C]
Detached: [Item A]
~~~

Với cascade MERGE và orphanRemoval, việc merge có thể dẫn đến logic đồng bộ collection loại bỏ child không có trong state truyền vào (tùy collection initialization/mapping). Nếu request chỉ muốn đổi status, **không tạo detached aggregate với items bị thiếu** rồi merge.

### 16.3. Tạo helper giữ association nhất quán

~~~java
public void addItem(OrderItem item) {
    items.add(item);
    item.setOrder(this);
}
~~~

Đây là ví dụ helper trong PurchaseOrder; cần có setter/constructor hợp lệ cho OrderItem. Với bidirectional OneToMany/ManyToOne, Item là owning side giữ FK. Chỉ thêm vào collection inverse mà quên item.order có thể làm INSERT sai/null FK.

### 16.4. Persist và merge cùng cascade không phải copy sâu thông thường

Hibernate xử lý entity identity, state, proxy, cascading rules và action queue. Merge detached graph phức tạp có thể gặp nhiều detached representations của cùng ID, transient references hoặc conflict state. Tránh coi merge là hàm deepClone đơn giản.

## 17. Xử lý update từ REST DTO thay vì merge entity do client xây

Một controller nhận request:

~~~java
public record UpdateOrderRequest(String status) {}
~~~

Service:

~~~java
@Service
public class OrderService {
    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void payOrder(
            Long orderId,
            Long authenticatedTenantId) {

        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (!orderBelongsToTenant(order, authenticatedTenantId)) {
            throw new AccessDeniedException("Không có quyền");
        }

        order.markPaid();
        // Managed -> dirty checking khi transaction flush.
    }
}
~~~

Các helper orderBelongsToTenant, OrderNotFoundException và AccessDeniedException cần được định nghĩa/import theo dự án; đoạn này minh họa ranh giới application service.

### 17.1. Lợi ích của load-modify pattern

- Bảo toàn những field không nằm trong request.
- Không vô ý thay đổi collection.
- Cho phép kiểm tra business invariants từ state hiện tại.
- Có thể kiểm tra tenant/authorization rõ ràng.
- Kết hợp thuận tiện với @Version/optimistic locking.
- Giảm nhầm lẫn giữa entity detached và managed.

### 17.2. Không để client chọn ID/version tùy tiện

Với REST update, thường ID lấy từ route và version từ ETag/version field có contract rõ; không bind toàn bộ JSON vào entity và cho client sửa tenantId, ownerId, version hoặc internal flags. Những thuộc tính này không phải “trường update” thông thường.

### 17.3. Partial update với null cần ngữ nghĩa riêng

Một request PATCH có field không gửi và field gửi null có thể có nghĩa khác nhau. JPA merge không có semantics “chỉ copy field được gửi”. Sử dụng DTO/patch command phân biệt absent/null/present rồi áp dụng lên entity managed theo business rules.

## 18. saveAll và saveAllAndFlush

Spring Data JPA cung cấp các thao tác theo collection như saveAll và saveAllAndFlush (tùy repository interface/version).

~~~java
List<PurchaseOrder> saved =
    repository.saveAll(orders);
~~~

Trong triển khai JpaRepository phổ biến, saveAll gọi save cho từng entity trong collection:

~~~java
for (PurchaseOrder order : orders) {
    result.add(save(order));
}
~~~

Nó **không tự đồng nghĩa với một SQL INSERT nhiều hàng hoặc JDBC batching**. Hibernate batching phụ thuộc ID generator, transaction, dialect, JDBC batch size, ordering và flush behavior.

### 18.1. saveAllAndFlush vẫn flush context

~~~java
List<PurchaseOrder> saved =
    repository.saveAllAndFlush(orders);
~~~

Phương thức có ý nghĩa save các entity rồi flush. Không đồng nghĩa “commit từng row” và không bảo đảm chi phí thấp hơn saveAll.

### 18.2. Insert số lượng lớn theo batch

Với 100.000 rows, nếu dùng một transaction/context giữ toàn bộ entity managed, memory và dirty-checking có thể tăng.

Một hướng dùng EntityManager:

~~~java
@Transactional
public void insertBatch(
        List<ImportRow> rows,
        EntityManager em) {

    int batchSize = 100;
    for (int i = 0; i < rows.size(); i++) {
        em.persist(toEntity(rows.get(i)));

        if ((i + 1) % batchSize == 0) {
            em.flush();
            em.clear();
        }
    }
    em.flush();
    em.clear();
}
~~~

Đây là ví dụ chung. Flush/clear chỉ quản lý persistence context; nó không chia transaction thành nhiều commit. Nếu transaction bao cả 100.000 rows, rollback vẫn có thể hủy toàn bộ inserts. Với import lớn, cân nhắc mỗi batch một transaction riêng thông qua service được Spring proxy gọi đúng ranh giới.

### 18.3. Cẩn thận với clear

em.clear() detach **toàn bộ** entity managed của EntityManager, không riêng entity vừa persist. Nếu service còn giữ các object khác cần sửa trước commit, clear có thể làm mất đường dirty-checking tiếp theo. Đặt batch import trong transaction/context riêng khi có thể.

### 18.4. Batching và IDENTITY

IDENTITY thường làm Hibernate cần INSERT từng entity để lấy ID, ảnh hưởng đến JDBC insert batching. Nếu workload cần throughput insert cao, xem lại ID strategy (SEQUENCE/pooling), batching properties và database behavior. Không hứa saveAllAndFlush tự giải quyết hiệu năng.

## 19. saveAndFlush để kiểm tra constraint sớm: khi nào đáng dùng?

Giả sử email có unique constraint trong database và service cần phát hiện lỗi trước khi thực hiện thao tác tiếp theo:

~~~java
@Transactional
public void register(Customer customer) {
    customerRepository.saveAndFlush(customer);
    // Unique violation (nếu DB kiểm tra ngay) có thể lộ ở đây.
}
~~~

Việc gọi flush giúp ép những INSERT/UPDATE pending xuống DB trong transaction; nếu UNIQUE được kiểm tra tức thì, exception có thể xuất hiện trước khi method thực hiện bước tiếp theo.

### 19.1. Vẫn phải có constraint thật trong database

Code:

~~~java
if (!repository.existsByEmail(email)) {
    repository.save(customer);
}
~~~

không tránh race: hai transaction cùng thấy email chưa có rồi cùng insert. Database UNIQUE mới bảo đảm tính duy nhất. Có thể xử lý conflict thành lỗi nghiệp vụ phù hợp, nhưng cần kiểm soát transaction state sau exception.

### 19.2. Bắt exception khi transaction đã fail

Nếu JDBC/constraint exception xảy ra trong flush, transaction có thể bị đánh dấu rollback-only hoặc PostgreSQL transaction đã ở trạng thái aborted. Không catch exception rồi tiếp tục gọi repository trong cùng transaction như không có lỗi.

Tùy use case:

- Cho exception propagate, rollback và map sang HTTP 409/validation ở tầng ngoài.
- Thiết kế transaction riêng cho thao tác có thể thất bại nếu cần retry độc lập.
- Dùng native upsert/insert-on-conflict khi business thật sự cần idempotency/UPSERT.

Không coi saveAndFlush là giải pháp race condition: nó chỉ tác động thời điểm SQL được gửi.

### 19.3. Side effect sau flush không bảo đảm đã commit

Sai về kiến trúc:

~~~java
@Transactional
public void createAndNotify(PurchaseOrder order) {
    repository.saveAndFlush(order);
    mailGateway.sendConfirmation(order.getId());
    // Sau đó transaction có thể rollback.
}
~~~

Email đã gửi không được tự rollback khi transaction DB thất bại. Nếu cần phát sự kiện sau commit, dùng transaction synchronization/after-commit hoặc transactional outbox theo độ tin cậy yêu cầu.

### 19.4. Khi nào flush thật sự cần thiết?

Có thể hợp lý khi:

- Cần DB kiểm tra immediate constraint trước bước sau.
- Cần SQL được thực thi trước một operation native/JDBC đặc biệt không được provider tự đồng bộ phù hợp.
- Cần giải phóng pending batch theo chu kỳ trong import lớn.
- Một workflow có dependency trên DB-generated value mà provider hỗ trợ sau flush/refresh.

Không gọi saveAndFlush trong mọi CRUD endpoint chỉ để “chắc chắn lưu”; nhiều flush làm mất cơ hội batch và tăng round-trip.

## 20. Merge và INSERT khi row bị thiếu: không phải upsert đáng tin cậy

Một quan niệm sai:

~~~java
repository.save(entityWithId);
// Có row thì UPDATE, chưa có row thì INSERT, chắc chắn atomic?
~~~

Không đúng. save chọn persist/merge theo isNew; merge có thể đọc hoặc xử lý detached/new state tùy mapping/version. Với Hibernate mới hơn, một detached entity có generated ID hoặc non-primitive @Version chỉ ra nó đã từng persisted nhưng DB row không còn, merge có thể ném optimistic-lock exception thay vì INSERT.

Quan trọng hơn, **không có bảo đảm atomic UPSERT** như một SQL INSERT ... ON CONFLICT DO UPDATE.

### 20.1. Race khi kiểm tra tồn tại rồi save

~~~text
T1: findByBusinessKey("X") -> không có
T2: findByBusinessKey("X") -> không có
T1: save(new entity) -> INSERT
T2: save(new entity) -> INSERT
~~~

Nếu không có unique constraint, hai row trùng business key có thể được tạo. Nếu có constraint, một transaction phải xử lý conflict.

### 20.2. Khi cần UPSERT thật

Với PostgreSQL, có thể dùng:

~~~sql
INSERT INTO reference_codes(code, label)
VALUES (:code, :label)
ON CONFLICT (code)
DO UPDATE SET label = EXCLUDED.label;
~~~

Đây là SQL native của PostgreSQL, không phải semantics của merge. Nếu dùng native DML, phải cân nhắc entity hiện có trong persistence context, @Version/lifecycle callbacks và synchronization cache. Chọn upsert theo business contract và tests, không dùng nó như mẹo thay save cho mọi entity.

## 21. Khi trộn repository save với EntityManager.persist/merge

Trong cùng transaction được cấu hình với cùng EntityManagerFactory, repository và injected EntityManager thường tham gia chung persistence context.

~~~java
@Service
public class OrderPersistenceService {
    @PersistenceContext
    private EntityManager em;

    private final PurchaseOrderRepository repository;

    public OrderPersistenceService(
            PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOne() {
        PurchaseOrder order = new PurchaseOrder(
            "DRAFT", new BigDecimal("50.00"), Instant.now());
        em.persist(order);
        // Không cần repository.save(order) lần nữa.
        return order.getId();
    }
}
~~~

Không gọi cả persist và save cho cùng entity chỉ vì muốn tăng độ tin cậy. Cả hai cùng nhằm đưa entity vào persistence context; đối với managed entity, dirty checking xử lý thay đổi. Nếu cần flush, có em.flush hoặc repository.flush, nhưng phải hiểu đó là flush toàn context.

### 21.1. Repository là abstraction của use case dữ liệu

Ưu điểm của Spring Data repository:

- CRUD đơn giản, phương thức query rõ tên.
- Dễ tích hợp paging/sorting/specification.
- Transaction defaults và exception translation trong Spring.
- Giảm mã lặp ở persistence layer.

Ưu điểm của EntityManager trực tiếp:

- Kiểm soát persist vs merge có chủ đích.
- Tạo CriteriaQuery/named query/custom operation.
- Flush/clear/detach/refresh và lifecycle thao tác rõ.
- Thực hiện những batch/workflow phức tạp.

Không có quy tắc “EntityManager luôn nhanh hơn repository” hoặc ngược lại. Khác biệt chính là API abstraction và cách bạn quản lý context/transaction.

### 21.2. Nhiều EntityManagerFactory

Nếu dự án có hai DataSource/EntityManagerFactory, một repository có thể thuộc persistence unit A còn EntityManager đang dùng là của B. Khi đó thao tác/transaction/cache không tự động chia sẻ. Phải xác minh @EnableJpaRepositories, transactionManager, @PersistenceContext(unitName=...) và datasource wiring; không giả định mọi EntityManager đều trỏ cùng DB.

## 22. Bulk update và SQL native có bypass dirty checking

Một lệnh:

~~~java
@Modifying
@Query("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
int updateStatus(@Param("id") Long id,
                 @Param("status") String status);
~~~

là bulk HQL DML, khác với:

~~~java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.markPaid();
~~~

Bulk DML tác động database trực tiếp, có thể bypass lifecycle callbacks, entity dirty checking và xử lý @Version thông thường nếu câu DML không tăng/check version có chủ đích.

### 22.1. Managed entity có thể bị stale

~~~java
@Transactional
public void bulkUpdateThenRead() {
    PurchaseOrder order = repository.findById(id).orElseThrow();

    repository.updateStatus(id, "PAID");

    // order vẫn có thể chứa status cũ trong persistence context.
    System.out.println(order.getStatus());
}
~~~

Do persistence context là identity map, query tiếp theo có thể trả object managed cũ. Cần quyết định flush/clear/refresh với scope phù hợp hoặc tránh mix bulk DML và loaded entities.

### 22.2. @Modifying tùy chọn

Spring Data JPA có:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("update PurchaseOrder o set o.status = :status where o.id = :id")
int updateStatusAndClear(...);
~~~

flushAutomatically yêu cầu flush trước bulk DML; clearAutomatically detach context sau query. Cả hai có tác động tới **toàn context**, có thể ảnh hưởng những entity khác đang được sửa. Không bật tự động như một mặc định cho mọi repository method nếu chưa đánh giá boundary.

### 22.3. saveAndFlush không sửa stale context sau native DML

Nếu một native query vừa update DB mà object managed cũ vẫn nằm trong L1, gọi saveAndFlush(object) không tự có nghĩa “reload object từ DB”. Với dữ liệu cần làm mới, dùng refresh/clear hoặc transaction mới theo nghiệp vụ, tránh ghi ngược state cũ lên DB.

## 23. Sự khác nhau khi làm việc với @Transactional(readOnly = true)

Ví dụ:

~~~java
@Transactional(readOnly = true)
public void readOnlyExample() {
    PurchaseOrder order =
        repository.findById(101L).orElseThrow();
    order.markPaid();
}
~~~

Đây là code có chủ đích sai: nó làm mutation bên trong transaction được khai báo chỉ đọc. Tùy Spring/Hibernate configuration, thay đổi có thể không được flush như kỳ vọng hoặc vẫn có SQL khác phát sinh, nhưng không thể dựa vào readOnly để bảo đảm một thao tác ghi hợp lệ.

Đúng hơn:

~~~java
@Transactional
public void pay(Long id) {
    PurchaseOrder order =
        repository.findById(id).orElseThrow();
    order.markPaid();
}
~~~

### 23.1. @Transactional không chỉ là annotation trang trí

Nếu service method chưa thực sự đi qua Spring transaction interceptor (ví dụ tự gọi nội bộ/self-invocation, bean không được Spring quản lý, method không phù hợp proxy rules), code có thể không chạy với transaction mong muốn. Cần quan sát TransactionSynchronizationManager/test transactional behavior theo configuration.

### 23.2. Open Session in View không thay service transaction

Khi OSIV còn mở persistence context cho web request, controller có thể đọc lazy association sau service. Nhưng mutation sau transaction boundary không nên dựa vào OSIV để tự ghi dữ liệu. Đặt write use case trong @Transactional service và trả DTO.

## 24. Những bẫy đặc biệt của merge và version

### 24.1. Detached được load trước khi dữ liệu thay đổi

~~~text
Session A đọc Order #101, version 1 -> detached snapshot A
Session B sửa Order #101, commit -> version 2
Session C merge snapshot A (version 1)
~~~

Nếu @Version và mapping đúng, provider phải xử lý stale state theo optimistic-lock semantics. Không tự xóa version hoặc ghi version hiện tại vào detached input để né conflict.

### 24.2. Có hai detached objects cùng ID

~~~java
PurchaseOrder left = /* detached #101 với status=PAID */;
PurchaseOrder right = /* detached #101 với status=CANCELLED */;
~~~

Nếu cùng merge qua cascade vào một persistence context, hai representations của cùng entity có thể gây xung đột/cảnh báo hoặc behavior phụ thuộc cấu hình Hibernate. Không thiết kế workflow sao chép graph với nhiều object cùng primary key rồi hy vọng merge tự chọn dữ liệu đúng. Nên quản lý một aggregate managed rõ ràng.

### 24.3. Merge detached object không phải replacement cho diff

Nếu business yêu cầu “chỉ sửa quantity của item #20”, hãy load Order/Item managed và thay đúng quantity. Dùng detached graph từ client với thiếu items khác dễ làm sai orphanRemoval. Nếu cần áp dụng một graph update phức tạp, định nghĩa diff algorithm (add/update/remove) ở service dựa trên identity và quyền được phép thao tác.

### 24.4. Version là một field kỹ thuật có ngữ nghĩa

Khi dùng optimistic locking, version nên được đọc đúng từ DB, không cho client tự quyết định. Đối với API concurrency, có thể đưa version vào ETag và yêu cầu If-Match rồi kiểm tra ở service. Không coi @Version chỉ là cách giúp Spring Data isNew; vai trò chính là phát hiện cập nhật đồng thời.

## 25. SQL logging để nhìn thấy điều gì thật sự xảy ra

Trong môi trường development/test:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind parameter có thể ghi dữ liệu đơn hàng, email, số tiền hoặc thông tin nhạy cảm. Không bật TRACE mặc định trong production.

### 25.1. Một số timeline SQL có thể gặp

| Hành động | SQL có thể xuất hiện | Cần hiểu |
|---|---|---|
| persist new SEQUENCE | SELECT nextval, INSERT khi flush | ID có thể có trước INSERT |
| persist new IDENTITY | INSERT sớm để lấy key | Không chờ flush một cách cứng |
| save new | Tương tự persist path | Phụ thuộc isNew |
| save detached | SELECT/load và UPDATE khi flush | Phụ thuộc merge state/context |
| saveAndFlush managed không dirty | Có thể không có UPDATE cho entity đó | Flush không đồng nghĩa một SQL riêng |
| saveAndFlush cùng lúc context có nhiều dirty entities | Nhiều INSERT/UPDATE/DELETE | Flush toàn context |
| repository.findById rồi sửa trong @Transactional | UPDATE tại flush/commit | Dirty checking |
| bulk @Modifying UPDATE | SQL UPDATE trực tiếp | Persistence context có thể stale |

### 25.2. Hibernate Statistics

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

long before = stats.getPrepareStatementCount();

// Chạy một use case đã cô lập.

long statements =
    stats.getPrepareStatementCount() - before;
~~~

Statistics thuộc SessionFactory, nhiều thread có thể ảnh hưởng bộ đếm. Dùng test cô lập và SQL capture nếu cần số câu SQL chính xác cho một use case. Số statements không tự cho biết commit đã xảy ra hoặc toàn bộ transaction succeeded.

### 25.3. Quan sát version trong SQL

Với @Version, SQL minh họa:

~~~sql
UPDATE purchase_orders
SET status = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu UPDATE tác động 0 rows do version không khớp, Hibernate có thể phát optimistic-lock exception. Hình dạng SQL thực tế còn tùy dialect, dirty fields và optimistic lock strategy.

## 26. Kiểm thử sự khác biệt bằng integration test

Mục tiêu là kiểm tra **state, identity, SQL và transaction**, không chỉ assert row count.

### 26.1. Test persist trả chính instance managed

~~~java
@Test
void persistMakesNewEntityManaged() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("10.00"), Instant.now());
    em.persist(order);

    assertTrue(em.contains(order));

    tx.rollback();
    em.close();
}
~~~

Ví dụ dùng JUnit assertions và EntityManagerFactory đã được khởi tạo. Nếu Spring dùng container-managed EntityManager, nên kiểm thử qua @Transactional service hoặc TestEntityManager tương ứng thay vì tự bắt đầu transaction trên injected shared proxy.

### 26.2. Test merge detached trả managed copy

~~~java
@Test
void mergeReturnsManagedInstance() {
    Long id = createAndCommitOrder();

    EntityManager first = emf.createEntityManager();
    PurchaseOrder detached = first.find(PurchaseOrder.class, id);
    first.close();

    EntityManager second = emf.createEntityManager();
    EntityTransaction tx = second.getTransaction();
    tx.begin();

    PurchaseOrder merged = second.merge(detached);

    assertFalse(second.contains(detached));
    assertTrue(second.contains(merged));
    assertNotSame(detached, merged);

    tx.rollback();
    second.close();
}
~~~

Test trên giả định detached đến từ EntityManager khác và chưa có cùng instance managed ở second. Cần fixture createAndCommitOrder thực thi commit thật. Không kiểm tra reference identity bằng equals vì equals/hashCode có thể được override.

### 26.3. Test save quyết định new/existing

Đối với entity ID tự sinh:

1. Tạo entity id=null.
2. Gọi repository.save trong service transaction.
3. Kiểm tra entity được quản lý và row được tạo sau commit.
4. Mở EntityManager khác, đọc rồi detach.
5. Gọi repository.save(detached), sử dụng giá trị trả về.
6. Xác nhận update đúng fields và optimistic-lock behavior.

Không viết test chỉ dựa vào số SELECT cố định vì JDBC batching, cache và ID generator có thể thay đổi SQL timing.

### 26.4. Test assigned ID và isNew

Tạo ReferenceCode có ID "VN" ngay từ constructor và:

- Chạy save với detection mặc định.
- Quan sát có merge path hay không.
- Bổ sung Persistable.isNew() hoặc nullable version theo thiết kế.
- Kiểm tra trạng thái marker sau @PostLoad/@PostPersist.
- Chứng minh isNew=true không tự bảo đảm ID chưa có ở database.

### 26.5. Test saveAndFlush rồi rollback

~~~java
@Test
void flushDoesNotCommit() {
    Long id;
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    PurchaseOrder order = new PurchaseOrder(
        "DRAFT", new BigDecimal("15.00"), Instant.now());
    em.persist(order);
    em.flush();
    id = order.getId();

    tx.rollback();
    em.close();

    EntityManager verify = emf.createEntityManager();
    assertNull(verify.find(PurchaseOrder.class, id));
    verify.close();
}
~~~

Test dùng em.flush để chứng minh semantics nền tảng; saveAndFlush của Spring gọi save rồi flush trong transaction, nên cùng nguyên tắc không commit. Dùng test giao dịch thực tế (không bọc cả test trong rollback transaction ngoài) để tránh bị L1/transaction test che mất hành vi.

### 26.6. Test @Version conflict

1. Commit Order version 0.
2. Mở hai EntityManager/transactions độc lập.
3. Cả hai đọc cùng ID.
4. Transaction A update và commit.
5. Transaction B update và flush/commit.
6. Assert có optimistic-lock conflict và B rollback.
7. Kiểm tra database giữ state của A.

Một test chạy tất cả trong cùng @Transactional test method sẽ không mô phỏng hai transaction độc lập.

### 26.7. Test cascade và partial update

- Persist parent với child qua cascade PERSIST.
- Merge detached aggregate với toàn bộ children và xác nhận behavior.
- Tránh dùng test partial DTO như detached entity một cách vô tình.
- Test update một field bằng load-modify để giữ nguyên items.
- Test orphanRemoval bằng thao tác remove có chủ đích.

## 27. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| save không thấy INSERT ngay trong SQL log | Persist/merge chưa flush hoặc generator đặc thù | Xác định transaction/flush mode; không nhầm save với SQL |
| saveAndFlush xong vẫn rollback được | Flush không commit | Xác định transaction boundary rõ |
| save detached trả object khác | Merge tạo/trả managed instance | Dùng return value |
| Sửa input sau merge mà DB không update | Input vẫn detached | Sửa managed return |
| persist báo detached entity passed to persist | Truyền object đã có identity/lifecycle trước | Load managed hoặc merge khi phù hợp |
| save entity assigned ID gây SELECT/merge | isNew dựa ID khác null | Nullable @Version/Persistable hoặc persist có chủ đích |
| save(new) không luôn INSERT | isNew không phản ánh new hoặc merge behavior | Kiểm tra metadata/version/ID |
| Update từ PATCH xóa field cũ | Merge object thiếu field | Load managed entity rồi apply đúng fields |
| merge làm collection thiếu item | Detached graph/cascade/orphanRemoval | Diff aggregate trên managed graph |
| Gọi save trên managed entity nhưng không thay SQL | Dirty checking không thấy thay đổi | Không ép UPDATE chỉ vì save |
| Update entity sau findById ngoài transaction không được lưu | Entity có thể detached | Dùng service @Transactional |
| SQL lỗi ở saveAndFlush của Order nhưng nguyên nhân Customer | Flush toàn persistence context | Xem toàn pending changes/constraint |
| UNIQUE violation sau save | Lỗi có thể xuất hiện lúc flush/commit | Constraint DB và xử lý transaction rollback |
| Gửi email rồi rollback DB | Side effect không theo DB transaction | After-commit/outbox |
| Transaction self-invocation không hoạt động | Không đi qua Spring proxy | Thiết kế service boundary hợp lệ |
| Test hai lượt find không có SQL rồi tưởng L2 | L1 cache trả managed entity | Dùng context độc lập để test |
| merge không update đúng dưới ghi đồng thời | Stale state/lost update | @Version và conflict handling |
| saveAll rất chậm | Không có JDBC batching, IDENTITY, huge context | Batch config, SEQUENCE, flush/clear/transaction split |
| Bulk update xong entity vẫn cũ | Bypass L1/dirty checking | Refresh/clear hoặc transaction mới |
| Gọi saveAndFlush mọi nơi làm query chậm | Quá nhiều flush, giảm batching | Chỉ flush theo nhu cầu thực tế |

## 28. Bài thực hành theo từng cấp độ

### Bài A — Quan sát persist

1. Tạo PurchaseOrder với ID SEQUENCE.
2. Bắt đầu transaction, gọi em.persist().
3. In em.contains(order), order.getId().
4. Kiểm tra SQL trước và sau em.flush().
5. Rollback và kiểm tra row không tồn tại.
6. Đổi sang IDENTITY, so sánh thời điểm INSERT.

### Bài B — Thực hành merge

1. Commit một PurchaseOrder.
2. Load ở EntityManager A rồi đóng A.
3. Sửa detached object.
4. Merge trong EntityManager B.
5. So sánh detached == managed và em.contains().
6. Sửa tiếp detached, kiểm tra thay đổi này không tự đồng bộ.
7. Sửa managed return rồi commit, xác nhận dữ liệu cuối.

### Bài C — save và isNew

1. Tạo JpaRepository<PurchaseOrder, Long>.
2. Save entity ID null, quan sát persist path.
3. Save detached entity, quan sát merge path.
4. Tạo entity assigned ID không null.
5. Implement Persistable.isNew() hoặc thêm nullable @Version.
6. Kiểm tra case entity có ID nhưng DB row bị xóa.
7. Giải thích vì sao save không phải atomic upsert.

### Bài D — saveAndFlush và transaction

1. Viết service @Transactional gọi saveAndFlush.
2. Sau lệnh đó cố ý throw unchecked exception.
3. Xác nhận transaction rollback dù INSERT đã được flush.
4. Trong cùng context sửa thêm Customer trước saveAndFlush(Order).
5. Quan sát cả hai entity có thể được flush.
6. Cho database immediate UNIQUE constraint fail để xem exception tại flush.

### Bài E — Dirty checking

1. Dùng repository.findById trong @Transactional service.
2. Sửa status và kết thúc method **không gọi save**.
3. Kiểm tra UPDATE tại commit.
4. Lặp lại ngoài transaction và giải thích detached state.
5. Test readOnly transaction và xác định behavior thực tế.

### Bài F — DTO update và cascade

1. Xây request PATCH chỉ có status.
2. Tránh bind thẳng vào PurchaseOrder entity.
3. Load managed entity, apply status và validate state.
4. Tạo Order có nhiều Items và cấu hình orphanRemoval.
5. So sánh update đúng một field với merge detached graph thiếu items.
6. Thiết kế helper add/remove bảo toàn owning side.

### Bài G — Optimistic locking

1. Thêm @Version Long vào PurchaseOrder.
2. Mở hai transaction, đọc cùng entity.
3. Commit transaction A trước.
4. Flush transaction B và xác nhận conflict.
5. Chuyển exception thành response nghiệp vụ (ví dụ HTTP 409).
6. Không tự retry bằng cách bỏ version hoặc overwrite state cũ.

### Bài H — Batching

1. Import vài nghìn Orders bằng saveAll.
2. Bật Hibernate statistics và SQL log ở test.
3. So sánh SEQUENCE và IDENTITY.
4. Cấu hình JDBC batch size phù hợp.
5. Đo heap và số SQL với/không có flush+clear theo batch.
6. Thử mỗi batch một transaction riêng và mô tả rollback semantics.

## 29. Bảng quyết định khi triển khai

| Tình huống | Lựa chọn thường phù hợp | Tại sao |
|---|---|---|
| Tạo entity mới qua Spring Data repository | save(newEntity) | Spring Data chọn persist nếu nhận diện new |
| Tạo entity mới, muốn API JPA tường minh | entityManager.persist(newEntity) | Chính instance trở thành managed |
| Đã load managed entity trong @Transactional service | Sửa entity, để dirty checking | Không cần gọi save ở cuối |
| Nhận detached entity đầy đủ, chủ động muốn merge state | merge hoặc repository.save, dùng return value | Copy state vào managed instance |
| Nhận PATCH DTO chỉ vài fields | findById rồi mutate managed entity | Tránh ghi đè field/collection không có trong request |
| Cần immediate SQL trước bước phụ thuộc DB | flush hoặc saveAndFlush có chủ đích | Đồng bộ SQL nhưng không commit |
| Cần transaction atomic qua nhiều repository | Service @Transactional | Commit/rollback ở use case boundary |
| Cần UPSERT atomic theo unique key | Cơ chế DB upsert/constraint được thiết kế riêng | save/merge không phải atomic upsert |
| Import số lượng lớn | Batching, kiểm soát context/transaction | saveAll không tự batch tối ưu |
| Cần kiểm tra uniqueness | UNIQUE DB + xử lý conflict | exists + save có race |
| Cần tránh lost update | @Version và conflict handling | Không phải chọn saveAndFlush |
| Bulk update hàng loạt | @Modifying/native DML với quản lý L1 | Không phải save từng managed entity trong mọi trường hợp |

## 30. Checklist trước khi dùng một trong bốn API

1. Entity đang **new, managed hay detached**?
2. Có @Id generated, assigned hay @Version không?
3. Spring Data isNew() sẽ chọn persist hay merge?
4. Có cần dùng **return value** của save/merge không?
5. Mutation có nằm trong **service @Transactional thật sự** không?
6. Có cần flush ngay không, hay commit sẽ đủ?
7. Nếu gọi saveAndFlush, có entity khác đang dirty trong cùng context không?
8. Có hiểu flush không phải commit và dữ liệu có thể rollback không?
9. Entity có cascade và orphanRemoval không?
10. Input có phải **partial DTO** hoặc detached graph không đầy đủ không?
11. Có business invariant hoặc quyền truy cập phải kiểm tra trước mutation không?
12. Có @Version/optimistic locking để phát hiện concurrent writes không?
13. Có unique constraint/DB constraint thay vì kiểm tra ứng dụng dễ race không?
14. Nếu dùng IDENTITY/SEQUENCE, có hiểu thời điểm SQL và ID được cấp không?
15. Nếu gọi saveAll, có đo batching, memory và transaction size không?
16. Có trộn bulk DML/native SQL với managed state không?
17. Đã kiểm thử rollback, generated ID, merge identity và update patch trên DB thực tế chưa?
18. Có tránh side effect ngoài transaction chỉ dựa vào flush không?

## 31. Tổng kết bằng bốn câu

~~~mermaid
flowchart LR
    A[Entity truyền vào] --> B{Spring Data isNew?}
    B -->|Có| C[save -> persist]
    B -->|Không| D[save -> merge]
    C --> E[Managed entity]
    D --> E
    E --> F{saveAndFlush?}
    F -->|Có| G[Flush pending SQL]
    F -->|Không| H[Đợi flush theo transaction/query]
    G --> I[Transaction vẫn chưa chắc commit]
    H --> I
    I --> J[Commit hoặc Rollback]
~~~

**persist**: đăng ký **entity mới** với persistence context; chính object truyền vào trở thành managed nếu thao tác hợp lệ. INSERT có thể được gửi sớm hoặc muộn tùy generator/flush.

**merge**: sao chép state của entity new/detached vào **instance managed được trả về**; object detached ban đầu không tự trở thành managed. Nó không đồng nghĩa UPDATE tức thì hoặc atomic upsert.

**save**: API Spring Data JPA chọn **persist hoặc merge** bằng cơ chế nhận diện entity mới. Không hiểu được save nếu chưa hiểu isNew(), @Id, @Version và Persistable.

**saveAndFlush**: thực hiện **save rồi flush** persistence context; không đồng nghĩa **commit**, không tự làm transaction khác thấy dữ liệu chưa commit và không chỉ flush duy nhất entity được truyền vào.

Trong service nghiệp vụ, chiến lược đơn giản và an toàn thường là: **tạo mới thì save/persist; cập nhật entity đang managed thì sửa đúng field trong @Transactional; chỉ merge detached khi thật sự cần và hiểu đầy đủ state; chỉ flush chủ động khi có phụ thuộc cụ thể về SQL timing.** Hibernate quản lý SQL bằng persistence context và transaction, không phải bằng việc gọi tên phương thức “lưu” càng nhiều càng chắc chắn.
