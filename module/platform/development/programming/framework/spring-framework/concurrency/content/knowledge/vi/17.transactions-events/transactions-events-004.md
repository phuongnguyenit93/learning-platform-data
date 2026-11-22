# Không truyền EntityManager hoặc phiên ORM sang luồng xử lý khác

## 1. Ý chính: ranh giới thread cũng là ranh giới persistence context

Trong ứng dụng Spring có xử lý đồng thời, một luồng có thể đang thực thi `@Transactional`, giữ **persistence context** và dùng JPA `EntityManager` hoặc Hibernate `Session`. Nếu method này gửi công việc sang `@Async`/`TaskExecutor`, **không chuyển nguyên instance EntityManager/Session đang hoạt động sang worker mới** để tiếp tục truy vấn hoặc cập nhật dữ liệu.

Lý do: một `EntityManager` thực do provider tạo, hoặc một Hibernate `Session` thực, là thành phần **có trạng thái (stateful), không thread-safe**. Nó theo dõi entity được quản lý, trạng thái dirty checking, flush, lazy loading và transaction. Spring quản lý transaction kiểu imperative thông qua tài nguyên gắn với **thread hiện tại**; khi chuyển việc sang worker, transaction và persistence context của caller **không tự đi theo**.

**Thiết kế khuyến nghị:** chỉ chuyển **ID, giá trị bất biến hoặc DTO đã được materialize** qua ranh giới async. Tại worker, gọi **service/repository bean do Spring quản lý** với transaction riêng; để Spring lấy EntityManager tương ứng từ persistence context **của worker**, đọc/ghi dữ liệu rồi **trả một DTO**, không trả EntityManager, Session hay lazy collection.

~~~text
KHÔNG NÊN

request thread                          async worker thread
  @Transactional
  EntityManager thực / Session thực ────────► em.find(), em.flush()
  persistence context A                         dùng chéo A: không an toàn
  transaction A                                  transaction A không tự truyền


NÊN

request thread                          async worker thread
  lưu entity và commit
  lấy orderId (Long) ─────────────────────────► @Transactional(readOnly = true)
                                               EntityManager của worker
                                               em.find(Order.class, orderId)
                                               DTO snapshot
                  ◄──────────────────────────── CompletableFuture<DTO>
~~~

Ở đây "EntityManager thực" là object quản lý persistence context do provider tạo. Có một **ngoại lệ quan trọng về kiểu reference**: `@PersistenceContext` mặc định của Spring thường inject một **shared EntityManager proxy** vào repository singleton. Proxy **có thể được dùng từ nhiều thread** vì nó chuyển các lời gọi tới EntityManager thích hợp cho transaction/thread đang hoạt động. Điều đó **không** khiến **underlying EntityManager/Session** trở thành thread-safe; cũng **không** phải lý do để truyền reference EM/Session qua API công việc. Phần 3 sẽ giải thích tường minh để không hiểu nhầm lời khuyên của bài.

## 2. EntityManager, Session, EntityManagerFactory và persistence context

| Thành phần | Vai trò | Quy tắc với concurrency |
| --- | --- | --- |
| `EntityManagerFactory` (JPA) | Factory và metadata của persistence unit | Được thiết kế để chia sẻ, thường là bean singleton; tạo EntityManager theo từng unit of work |
| `SessionFactory` (Hibernate) | Factory, cấu hình/mapping Hibernate | Thường chia sẻ qua các thread; mở Session riêng cho unit of work |
| `EntityManager` thực | API thao tác với một persistence context cụ thể | **Không thread-safe**, không dùng đồng thời hoặc chuyển tiếp giữa worker threads |
| `Session` thực | API Hibernate có trạng thái, thường là implementation của EntityManager | **Không thread-safe**, không chia sẻ giữa thread/unit of work |
| `@PersistenceContext` kiểu TRANSACTION của Spring | Reference proxy chuyển lời gọi tới EntityManager của transaction hiện tại | Proxy được inject vào singleton DAO có thể dùng ở các thread khác nhau; **không chia sẻ underlying context** |
| Entity JPA đang managed | Dữ liệu theo dõi bởi một persistence context | Không tự động thread-safe; không để nhiều thread dùng cùng entity đang managed |
| DTO/record bất biến | Bản chụp dữ liệu không gắn ORM persistence context | Phù hợp để chuyển giữa threads nếu các thành phần thực sự immutable/thread-safe |

`EntityManagerFactory` và `EntityManager` không thể đánh đồng: factory dùng chung là bình thường, còn context chứa first-level cache và trạng thái thay đổi entity thuộc về một unit of work. Tương tự, `SessionFactory` chia sẻ được không có nghĩa `Session` do factory mở được chia sẻ.

**Persistence context** quản lý lifecycle của entity: `new` → managed → detached/removed, cùng identity map, tracking thay đổi và flush. Đây không phải cấu trúc được thiết kế để nhiều worker cùng sửa một lúc. Nếu hai task cần thao tác trên cùng bản ghi DB, chúng có thể **có EntityManager riêng** và dùng transaction/locking/versioning để đồng bộ ở database, thay vì cố "chia sẻ một Session cho tiết kiệm".

### 2.1. Vì sao "không thread-safe" là giới hạn nghiêm túc?

Một Session/EntityManager có thể giữ:

- Identity map / first-level cache: theo dõi instance entity tương ứng với database identifier.
- Tập thay đổi cần flush và action queue.
- Trạng thái transaction, kết nối hoặc phối hợp với transaction manager.
- Lazy-loading proxies, collection wrappers và internal persistence state.
- Query context, trạng thái flush mode và cache hints.
- Tài nguyên cần đóng khi transaction/unit of work kết thúc.

Nếu hai thread cùng mutate hoặc flush trên một context, hành vi không được bảo đảm: race, dirty tracking sai, dữ liệu không nhất quán, exception ngẫu nhiên hoặc connection lifecycle sai. Ngay cả khi hai tác vụ chỉ gọi `find()`, việc thực thi cũng có thể thay đổi cache và trạng thái bên trong. **Không coi read-only access là bằng chứng có thể dùng một Session thực đồng thời.**

Một Hibernate `Session` thường cần phạm vi tương đối ngắn theo unit of work. Đừng đặt một Session thực vào singleton field, HTTP session, static field hoặc một executor task rồi giữ nó sống qua nhiều transactions.

## 3. Điểm tinh tế: @PersistenceContext trong Spring là proxy dùng chung, không phải Session thực

Trong một Spring singleton repository:

~~~java
@Repository
public class OrderRepository {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderSummary findSummary(Long id) {
        Order order = em.find(Order.class, id);
        return new OrderSummary(order.getId(), order.getStatus());
    }
}
~~~

Đây là **mảnh code minh họa**, cần các kiểu `Order`, `OrderSummary` và import. `OrderSummary` nên là immutable DTO. Với `PersistenceContextType.TRANSACTION` mặc định, Spring thường inject một **shared transactional EntityManager proxy** vào `em`, không phải một provider Session cố định dành cho mọi lời gọi.

Proxy này xác định **EntityManager gắn với transaction đang hoạt động**; nếu không có transaction, trong một số trường hợp nó tạo EntityManager cho operation thích hợp. Khi hai thread khác nhau gọi vào cùng repository bean, proxy chọn context theo transaction/thread của từng lời gọi, thay vì chia sẻ một persistence context thật. Vì vậy mẫu repository singleton có `@PersistenceContext` là **mẫu được Spring hỗ trợ**, không trái với tiêu đề.

**Điều không được làm:**

- Lấy `em.unwrap(org.hibernate.Session.class)` từ một transaction rồi giữ/đưa **Session thực** sang executor.
- Tạo `emf.createEntityManager()` thủ công rồi chia sẻ instance đó giữa request thread và worker.
- Chuyển persistence context dưới dạng tham số `worker.doWork(em, ...)` với giả định transaction sẽ đi theo.
- Dùng `@PersistenceContext(type = PersistenceContextType.EXTENDED)` trong một singleton bean được truy cập đồng thời; extended context không phải shared transactional proxy an toàn kiểu trên.

**Điều được phép:** inject repository có `@PersistenceContext` proxy vào các Spring-managed services, để mỗi method được gọi với **transaction riêng phù hợp**. Mẫu này dùng **cùng reference proxy** nhưng **không dùng chung một underlying EntityManager thực**.

### 3.1. Shared proxy không phải "tấm vé" để bỏ qua transaction

Dù shared proxy tự chọn EntityManager, nó **không sao chép transaction của caller** sang worker. Tại worker không có active transaction, một số thao tác đọc có thể được thực hiện bằng một EntityManager tạo theo operation; thao tác ghi hoặc lazy loading ngoài phạm vi quản lý thường không có hợp đồng đúng. Thiết kế an toàn hơn là gọi một service/repository `@Transactional` ở thread thực thi công việc.

Sự khác biệt cần nhớ:

~~~text
Field trong singleton repository:
  @PersistenceContext EntityManager em
             |
             +-- reference proxy (có thể dùng từ nhiều thread)
                      |
                      +-- thread A / transaction A -> EntityManager A
                      |
                      +-- thread B / transaction B -> EntityManager B

Không phải:
  singleton repo -> EntityManager thực duy nhất -> mọi thread
~~~

Tài liệu Spring nhấn mạnh `@PersistenceContext` mặc định kiểu `TRANSACTION` và lưu ý `EXTENDED` là cơ chế khác, không thích hợp cho singleton truy cập đồng thời. Điều phân biệt đó quan trọng hơn việc chỉ đọc type `EntityManager` của field.

## 4. @Transactional không được truyền sang luồng mới

Một `@Transactional` imperative do `PlatformTransactionManager` quản lý thường gắn transaction/resources với thread bằng các cơ chế như `TransactionSynchronizationManager`. Khi gọi `@Async`, `Executor.execute(...)`, `CompletableFuture.supplyAsync(...)` hoặc tạo `Thread` mới, code chạy ở **thread khác**, nên **không tự kế thừa**:

- Transaction JPA và persistence context của caller.
- JDBC connection được bind bởi transaction manager.
- Hibernate `Session` của transaction caller.
- Các `ThreadLocal` khác như MDC/security/request context, trừ khi chủ động cấu hình propagation phù hợp.

Ví dụ anti-pattern:

~~~java
@Service
public class OrderCoordinator {
    private final EntityManagerFactory emf;
    private final Executor executor;

    // Constructor injection không hiển thị trong đoạn minh họa.

    @Transactional
    public void unsafe(Long id) {
        EntityManager em = emf.createEntityManager();
        executor.execute(() -> em.find(Order.class, id));
        // Không có protocol ownership, close, transaction hay
        // đồng bộ truy cập phù hợp cho EntityManager này.
    }
}
~~~

Đây là **đoạn sai có chủ đích**, không phải code runnable; còn thiếu constructor, kiểu `Order` và import. `createEntityManager()` trả về application-managed EntityManager thực. Tác vụ được gửi sang thread khác nhưng resource vẫn có lifecycle riêng không rõ ràng; nếu caller dùng/đóng `em` trong lúc worker chạy, còn có concurrent access/lifecycle race. **Đừng xem instance này là một payload hợp lệ cho executor.**

Một ví dụ sai còn rõ hơn:

~~~java
@Transactional
public void wrong(Long id) {
    Session session = entityManager.unwrap(Session.class);
    executor.execute(() -> session.find(Order.class, id));
}
~~~

Mảnh này cần `entityManager`, `executor`, `Order` và Hibernate imports. `unwrap(Session.class)` có thể làm lộ **Session thực gắn với transaction caller**. Khi lambda chạy, transaction caller có thể đã commit/close, hoặc hai thread cùng chạm tới Session không thread-safe. Không giải quyết lỗi bằng cách gọi `session.flush()` trên worker hay tăng kích thước pool.

### 4.1. Lời gọi @Async có thể bắt đầu trước commit

~~~text
request thread                                worker thread
  @Transactional save(order)
  submit async(order.id) --------------------> findById(id)
  chưa commit                                  có thể không thấy row
  commit
~~~

Khi worker có transaction riêng, nó không mặc nhiên nhìn thấy dữ liệu **chưa commit** từ transaction caller. Kết quả phụ thuộc isolation, thời điểm commit, database, lock và operation. Có thể gặp "record not found" hoặc block vì lock ngay cả khi repository và EntityManager đã được quản lý đúng cách. Đây là vấn đề **thời điểm dữ liệu được công bố**, khác với vấn đề thread-safety của EntityManager.

Với việc **bắt buộc chạy sau commit**, xem phần 10 về `@TransactionalEventListener(phase = AFTER_COMMIT)` và transactional outbox.

## 5. Không chỉ EntityManager: managed entity và lazy proxy cũng nguy hiểm khi chuyển thread

Một cách "lách" thường gặp là không truyền `EntityManager`, nhưng chuyển nguyên **entity đang managed** hoặc một **Hibernate lazy collection/proxy** sang worker:

~~~java
@Transactional
public void start(Long orderId) {
    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    asyncWorker.process(order); // Không khuyến nghị dùng managed entity làm payload
}
~~~

Đây là mảnh minh họa với bean/typings chưa khai báo. Entity có thể chứa mutable fields, `@OneToMany(fetch = LAZY)` và reference tới trạng thái provider. Khi transaction caller kết thúc, worker có thể nhận entity **detached**, gặp `LazyInitializationException` nếu truy cập lazy association chưa được load, hoặc đọc dữ liệu không nhất quán do chia sẻ mutable object.

**Detached không đồng nghĩa immutable hoặc thread-safe.** Một detached POJO có thể vẫn được hai thread thay đổi đồng thời. Hibernate lazy proxy cũng có thể cần Session đã đóng, nên việc "đợi đến khi worker dùng" không làm nó tự attach lại.

Một số dữ liệu không nên mang qua boundary:

| Payload | Rủi ro |
| --- | --- |
| Provider `EntityManager` hoặc Hibernate `Session` | Non-thread-safe, lifecycle/transaction không theo worker |
| Managed entity có state biến đổi | Gắn với persistence context, mutable và có thể bị dirty checking ở caller |
| Lazy proxy / `PersistentCollection` | Cần session để initialize; session có thể đã đóng hoặc nằm ở thread khác |
| `Query`, `TypedQuery`, `StoredProcedureQuery` | Thường gắn với EntityManager/persistence context, không phải payload |
| JPA `Stream`/cursor đang mở | Tài nguyên DB/connection có lifecycle theo context gốc |
| `EntityTransaction`, JDBC `Connection`, Hibernate transaction | Stateful resource, không làm transaction có thể "di chuyển" giữa threads |
| Primitive/ID/immutable record chứa dữ liệu đã materialize | Phù hợp hơn khi không giữ reference ORM và có semantics rõ ràng |

Nếu cần các field từ association, truy vấn chúng **trong transaction của worker** hoặc **materialize thành DTO** trong một transaction có quyền truy cập phù hợp trước khi truyền; không gửi một collection proxy chưa được initialize để mong worker tự load.

### 5.1. Dùng DTO bất biến làm ranh giới dữ liệu

Java 17 record:

~~~java
public record OrderEvent(Long orderId, String requestedBy, long version) {}
~~~

Đây là một kiểu value object, không phải ORM entity. Nó có các thành phần final và không mang persistence context. **Lưu ý:** record chỉ immutable nông; nếu component là `List`, array hoặc object mutable thì dữ liệu bên trong vẫn có thể thay đổi. Với `Long`, `String` và `long` ở ví dụ này, payload là một snapshot dễ truyền.

Đừng dựa vào `EntityManager.detach(entity)` như giải pháp toàn diện: detach chỉ thay đổi trạng thái quản lý trong persistence context, không biến object mutable thành immutable hay giải quyết lazy association còn chưa load.

## 6. Mẫu an toàn: truyền ID rồi load bằng transaction ở worker

**Quy tắc ba bước:**

1. Caller lưu hoặc quyết định ID **theo contract về commit**.
2. Caller gửi **ID/immutable command** qua `@Async` hoặc executor, không gửi EM/Session/entity đang managed.
3. Worker **mở transaction riêng** qua Spring service/repository, load bằng `@PersistenceContext` proxy của bean worker và trả snapshot DTO.

Mẫu phân lớp:

~~~java
@Service
public class OrderWriter {
    @Transactional
    public Long create(OrderRequest request) {
        // Persist entity rồi trả ID; transaction commit khi
        // lời gọi qua Spring proxy hoàn tất bình thường.
        return orderRepository.saveAndGetId(request);
    }
}

@Service
public class AsyncLookup {
    private final OrderReader orderReader;

    public AsyncLookup(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    @Async("dbExecutor")
    public CompletableFuture<OrderDto> loadAsync(Long id) {
        OrderDto dto = orderReader.readDto(id);
        return CompletableFuture.completedFuture(dto);
    }
}

@Service
public class OrderReader {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderDto readDto(Long id) {
        Order entity = em.find(Order.class, id);
        return OrderDto.of(entity); // copy dữ liệu, không trả entity
    }
}
~~~

Đây là **mã minh họa**; `OrderRequest`, `OrderDto`, `Order`, `orderRepository` và cấu hình bean chưa được định nghĩa. Điều quan trọng là worker `AsyncLookup` gọi **bean OrderReader khác qua Spring proxy**, nhờ đó `@Transactional(readOnly = true)` mở transaction **trên worker thread**. `@Async` cũng được gọi qua bean proxy từ caller, không phải `this.loadAsync(...)`.

Một phương án khác là đặt `@Async` và `@Transactional` trên method worker được gọi qua proxy phù hợp, nhưng việc tách thành **dispatcher async + reader transactional** làm hai ranh giới rõ ràng và ít phụ thuộc vào thứ tự advice.

### 6.1. readOnly không có nghĩa entity/thread tự an toàn

`@Transactional(readOnly = true)` là hint/thuộc tính transaction mà Spring/provider có thể tối ưu theo cấu hình; nó **không** làm underlying EntityManager thread-safe. Vẫn phải giữ context của worker, không trả entity đang managed sang thread khác.

### 6.2. Nếu phải cập nhật dữ liệu tại worker

Worker có thể gọi:

~~~java
@Transactional
public void markProcessed(Long id) {
    Order entity = em.find(Order.class, id);
    if (entity == null) {
        throw new IllegalArgumentException("Order not found: " + id);
    }
    entity.setProcessed(true);
}
~~~

Đây là method minh họa trong repository/service có EM được quản lý. Transaction riêng của worker thực hiện dirty checking/flush; caller transaction không tự bao bọc lần cập nhật này. Nếu nhiều workers cùng cập nhật một row, dùng `@Version` optimistic locking, database constraints hoặc locking phù hợp để tránh lost update. Không chia sẻ object entity giữa worker threads để "đồng bộ" database.

## 7. Ví dụ hoàn chỉnh: Java 17 + Spring Framework 6.1 + Hibernate + H2

Ví dụ sau là một **ứng dụng command-line Spring Framework thuần**, không cần Spring Boot, server web hay database bên ngoài. Nó cho thấy:

- `OrderWriter.create(...)` thực thi `@Transactional` trên caller và **hoàn tất transaction trước khi trả về**.
- Caller chỉ chuyển một `Long id` sang worker.
- `AsyncOrderLookup.loadAsync(id)` chạy thông qua Spring `@Async("dbExecutor")`.
- Worker gọi `OrderReader.read(id)`, một **bean khác** có `@Transactional(readOnly = true)`; transaction này hình thành trên worker.
- `@PersistenceContext` inject **shared proxy** vào singleton `OrderReader`, nhưng không chia sẻ provider EntityManager thực giữa hai transactions.
- Kết quả là `OrderView` bất biến (record), không phải managed entity hay Session.

**Môi trường:** JDK 17+, Gradle 8.5+, Spring Framework 6.1.14, Hibernate ORM 6.4.10.Final, Jakarta Persistence 3.1, H2 2.2.224.

### 7.1. Cấu trúc tệp

~~~text
orm-thread-boundary/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── JpaThreadDemo.java
    ├── PurchaseOrder.java
    ├── OrderView.java
    ├── OrderWriter.java
    ├── OrderReader.java
    └── AsyncOrderLookup.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'orm-thread-boundary'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-orm:6.1.14'
    implementation 'jakarta.persistence:jakarta.persistence-api:3.1.0'
    implementation 'org.hibernate.orm:hibernate-core:6.4.10.Final'
    runtimeOnly 'com.h2database:h2:2.2.224'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}

application {
    mainClass = 'demo.JpaThreadDemo'
}
~~~

Đây là demo khóa version cụ thể cho mục đích học; dự án thực cần kiểm tra **BOM/version compatibility** và bản vá bảo mật theo quy trình dependency management của mình.

### 7.2. src/main/java/demo/PurchaseOrder.java

~~~java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String reference;

    protected PurchaseOrder() {
        // Constructor cho JPA.
    }

    public PurchaseOrder(String reference) {
        this.reference = reference;
    }

    public Long getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }
}
~~~

Entity được Hibernate quản lý **trong transaction của từng thread**. Nó không được gửi trực tiếp vào `CompletableFuture`. `@GeneratedValue(IDENTITY)` giúp demo có khóa chính từ H2. Các mapping phức tạp có quan hệ lazy được bỏ qua ở đây để tập trung vào ranh giới concurrency.

### 7.3. src/main/java/demo/OrderView.java

~~~java
package demo;

public record OrderView(
        Long id,
        String reference,
        String workerThread,
        boolean transactionActive) {
}
~~~

DTO này là một Java record gồm các giá trị có thể chia sẻ phù hợp. `workerThread` chỉ để minh họa thread chạy truy vấn; production code thường trả data/metadata cần thiết chứ không dùng thread name làm khóa nghiệp vụ.

### 7.4. src/main/java/demo/OrderWriter.java

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;

public class OrderWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long create(String reference) {
        PurchaseOrder order = new PurchaseOrder(reference);
        em.persist(order);
        em.flush();
        return order.getId();
    }
}
~~~

Trong demo, `OrderWriter` là Spring bean được tạo từ cấu hình bên dưới. Method `create` được gọi **qua proxy**, Spring transaction interceptor hoàn tất commit trước khi caller tiếp tục sau lời gọi trả về bình thường. `em` là shared injected proxy, không phải provider Session có thể đem sang thread khác.

`em.flush()` trong demo bảo đảm JPA thực hiện flush trước khi trả ID, nhưng **flush không đồng nghĩa commit**. Transaction được hoàn tất bởi Spring khi lời gọi method qua proxy kết thúc thành công.

### 7.5. src/main/java/demo/OrderReader.java

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class OrderReader {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderView read(Long id) {
        PurchaseOrder order = em.find(PurchaseOrder.class, id);
        if (order == null) {
            throw new IllegalArgumentException("Missing order: " + id);
        }

        // Tạo snapshot khi vẫn ở trong transaction của worker.
        return new OrderView(
                order.getId(),
                order.getReference(),
                Thread.currentThread().getName(),
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }
}
~~~

`OrderReader.read` được gọi từ một bean khác, nên transaction interceptor tạo một ranh giới read-only **ngay ở worker thread**. Nó truy vấn entity và copy các field vào DTO; entity không rời persistence context qua ranh giới thread.

### 7.6. src/main/java/demo/AsyncOrderLookup.java

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

public class AsyncOrderLookup {
    private final OrderReader reader;

    public AsyncOrderLookup(OrderReader reader) {
        this.reader = reader;
    }

    @Async("dbExecutor")
    public CompletableFuture<OrderView> loadAsync(Long id) {
        // Chỉ có ID đi từ caller sang worker.
        OrderView view = reader.read(id);

        // Phần thân @Async đang chạy trên worker;
        // Spring proxy cung cấp future kết quả cho caller.
        return CompletableFuture.completedFuture(view);
    }
}
~~~

`AsyncOrderLookup` chỉ nhận `Long id` và reference Spring-managed `OrderReader`. Không có `EntityManager`, `Session`, `Query` hay JPA entity trong tham số async. Phương thức `loadAsync` trả một `CompletableFuture` đã hoàn tất từ **bên trong worker**; proxy của Spring trả handle để caller theo dõi công việc nền.

### 7.7. src/main/java/demo/JpaThreadDemo.java

~~~java
package demo;

import java.util.Properties;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public final class JpaThreadDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Lời gọi Spring proxy: transaction caller commit trước khi về.
            Long id = context.getBean(OrderWriter.class)
                    .create("ORDER-42");

            // Chỉ chuyển ID; worker tạo transaction riêng qua OrderReader.
            OrderView view = context.getBean(AsyncOrderLookup.class)
                    .loadAsync(id)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("id preserved: " +
                    id.equals(view.id()));
            System.out.println("field loaded: " +
                    "ORDER-42".equals(view.reference()));
            System.out.println("worker pool used: " +
                    view.workerThread().startsWith("db-worker-"));
            System.out.println("worker transaction active: " +
                    view.transactionActive());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableAsync
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:orm_thread_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public LocalContainerEntityManagerFactoryBean
                entityManagerFactory(DataSource dataSource) {

            var factory = new LocalContainerEntityManagerFactoryBean();
            factory.setDataSource(dataSource);
            factory.setPackagesToScan("demo");
            factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());

            Properties props = new Properties();
            props.setProperty("hibernate.hbm2ddl.auto", "create-drop");
            props.setProperty("hibernate.show_sql", "false");
            factory.setJpaProperties(props);
            return factory;
        }

        @Bean
        public PlatformTransactionManager
                transactionManager(EntityManagerFactory emf) {
            return new JpaTransactionManager(emf);
        }

        @Bean("dbExecutor")
        public ThreadPoolTaskExecutor dbExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("db-worker-");
            return executor;
        }

        @Bean
        public OrderWriter orderWriter() {
            return new OrderWriter();
        }

        @Bean
        public OrderReader orderReader() {
            return new OrderReader();
        }

        @Bean
        public AsyncOrderLookup asyncOrderLookup(OrderReader reader) {
            return new AsyncOrderLookup(reader);
        }
    }
}
~~~

**Giải thích cấu hình:** `LocalContainerEntityManagerFactoryBean` xây `EntityManagerFactory` cho Hibernate, `JpaTransactionManager` cung cấp giao dịch JPA theo thread, và `@EnableTransactionManagement` kích hoạt transaction proxies. `@EnableAsync` kích hoạt async proxy. H2 là database trong bộ nhớ; `create-drop` **chỉ dành cho demo**, không áp dụng cho production vì có thể phá schema/dữ liệu.

`OrderWriter`, `OrderReader`, `AsyncOrderLookup` được đăng ký qua `@Bean`. Đối tượng do phương thức `@Bean` trả về được Spring post-process như bean bình thường, không phải object tự `new` ngoài container. Khi `OrderReader` được inject vào `AsyncOrderLookup`, reference có transaction proxy để intercept `read`.

### 7.8. Chạy và kết quả

Trong thư mục `orm-thread-boundary`, khi có Java 17+ và Gradle tương thích:

~~~bash
gradle run
~~~

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

**Bốn dòng do chương trình tự in, với điều kiện khởi tạo H2/Hibernate thành công và tác vụ hoàn tất trước timeout:**

~~~text
id preserved: true
field loaded: true
worker pool used: true
worker transaction active: true
~~~

Các thư viện Hibernate/SLF4J/Gradle có thể in thêm INFO/WARN trong quá trình khởi động/đóng context; đó không thuộc bốn dòng ở trên. Demo kiểm tra boolean thay vì in ID cụ thể hoặc số thứ tự worker để không phụ thuộc thứ tự thread và khóa chính sinh từ database.

**Tại sao thiết kế đúng?**

1. Caller lấy `OrderWriter` qua context, gọi `create` qua transaction proxy; khi method trả về bình thường, transaction được Spring commit.
2. Chỉ `Long id` được gửi sang `AsyncOrderLookup`, không phải EntityManager, Hibernate Session hay entity đang managed.
3. `@Async` được áp dụng qua Spring proxy, dispatcher chạy trên `db-worker-`.
4. Dispatcher gọi `OrderReader.read(id)` qua bean reference được inject; `@Transactional(readOnly = true)` được kích hoạt trên worker.
5. Shared EM proxy bên trong `OrderReader` delegate tới underlying EntityManager cho worker transaction.
6. `OrderView` là snapshot được tạo **trong** transaction; Future của caller mang dữ liệu DTO thuần.
7. Context được đóng sau khi future đã hoàn tất, để Spring quản lý lifecycle của entity manager factory và executor.

**Bài học quan trọng:** ví dụ không cố tạo một EntityManager thủ công ở caller rồi chuyển nó tới thread pool. Nó chuyển **dữ liệu** sang thread khác và để hạ tầng Spring quản lý persistence context mới tại chỗ công việc chạy.

## 8. Khi phải tự dùng EntityManagerFactory trong worker

Không phải mọi chương trình đều dùng declarative `@Transactional`. Một worker chạy ngoài Spring có thể tự lấy **factory dùng chung** rồi tạo **EntityManager riêng tại chính worker**, cùng transaction/lifecycle riêng.

Mẫu JPA `RESOURCE_LOCAL` minh họa:

~~~java
CompletableFuture<Summary> future = CompletableFuture.supplyAsync(
        () -> {
            EntityManager workerEm = emf.createEntityManager();
            EntityTransaction tx = workerEm.getTransaction();
            try {
                tx.begin();

                Order entity = workerEm.find(Order.class, orderId);
                Summary result = new Summary(
                        entity.getId(), entity.getStatus());

                tx.commit();
                return result;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            } finally {
                workerEm.close();
            }
        },
        executor);
~~~

Đây là **đoạn minh họa**, cần `emf`, `executor`, `orderId`, `Summary` và `Order`. Nó chỉ hợp lệ khi dùng **application-managed resource-local transactions**; với JTA/container-managed transactions cần giao thức và quản lý tương ứng, không tự gọi `getTransaction()` tùy tiện.

Điểm đúng: **factory chia sẻ được**; worker gọi `createEntityManager()`, bắt đầu transaction, copy DTO, commit/rollback và close trong **cùng một unit of work**. Không đưa `workerEm` ra ngoài lambda, không giữ nó vào singleton field và không trả nó trong Future.

Trong một ứng dụng Spring đã có `JpaTransactionManager`/`@PersistenceContext`, ưu tiên cách **Spring-managed repository + @Transactional** ở mục 6–7; tự quản lý EntityManager/transaction dễ mắc lỗi cleanup và làm lệch transaction manager của ứng dụng.

## 9. Trả DTO, không trả lazy object hoặc query stream

Một method async có thể trông an toàn vì không truyền `EntityManager`, nhưng **trả entity hoặc lazy collection qua Future** vẫn gây rủi ro:

~~~java
@Async("dbExecutor")
public CompletableFuture<PurchaseOrder> findAsync(Long id) {
    PurchaseOrder entity = em.find(PurchaseOrder.class, id);
    return CompletableFuture.completedFuture(entity);
}
~~~

Đây là mảnh code **không khuyến nghị**, cần bean/transaction/import. Nếu entity được load trong worker, Future đưa entity ra caller **sau khi worker transaction có thể đã kết thúc**, khiến lazy fields không load được hoặc object bị sửa ở nơi không kiểm soát. Bản thân entity không trở thành immutable khi detached.

**Cách tốt hơn:**

~~~java
@Transactional(readOnly = true)
public OrderDetailsDto getDetails(Long id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);

    // Lấy các giá trị cần thiết khi persistence context còn hiệu lực.
    return new OrderDetailsDto(
            order.getId(),
            order.getReference(),
            resolveItemNames(order));
}
~~~

Đây là mảnh code cần DTO và `resolveItemNames` riêng. Nếu `resolveItemNames` đọc một association lazy, hãy chủ động fetch/mapping trong transaction. Record chứa `List<String>` nên copy bằng `List.copyOf(...)` nếu cần immutable snapshot, thay vì trả nguyên `PersistentCollection`.

Có thể dùng **JPQL constructor projection**, Spring Data projection, entity graph hoặc `JOIN FETCH` hợp lý để lấy đúng field cần dùng. Nhưng câu hỏi gốc không phải "làm sao fetch mọi quan hệ"; nó là **không chuyển persistence context hoặc Session qua thread**.

## 10. Khi cần làm việc sau commit: TransactionalEventListener và outbox

Với các nhiệm vụ được phát sinh trong transaction caller, chỉ dùng `@Async` không đảm bảo worker chạy sau commit.

### 10.1. Phát sự kiện chứa ID và xử lý sau commit

Một mẫu phù hợp cho việc **có thể xử lý trong bộ nhớ**:

~~~java
public record OrderCommittedEvent(Long orderId) {}

// Trong service đang được Spring quản lý:
@Transactional
public void createAndNotify(OrderRequest request) {
    Long id = saveOrder(request);
    applicationEventPublisher.publishEvent(new OrderCommittedEvent(id));
}

// Trong listener bean khác:
@Component
public class OrderCommittedListener {
    private final AsyncOrderLookup worker;

    public OrderCommittedListener(AsyncOrderLookup worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderCommittedEvent event) {
        worker.loadAsync(event.orderId());
    }
}
~~~

Đây là các **mảnh code minh họa**, chưa phải chương trình độc lập: cần khai báo request, persistence method, imports và xử lý kết quả Future. `@TransactionalEventListener(AFTER_COMMIT)` gắn việc nhận sự kiện với **commit thành công** của transaction gốc; listener sau commit gửi ID tới async worker. Worker khởi tạo transaction riêng khi đọc.

Cần hiểu các giới hạn:

- Một transactional event listener thông thường cần event được publish khi có transaction đang hoạt động; nếu không có transaction, mặc định listener có thể **không được gọi** trừ khi `fallbackExecution` được cấu hình.
- Với listener đồng bộ chạy ngay sau commit, **tài nguyên transaction cũ có thể còn tạm thời bound** khi callback đang diễn ra. Nếu listener định ghi dữ liệu trong DB, cần mở một ranh giới transaction độc lập phù hợp (thường `REQUIRES_NEW` trong cùng thread sau commit) hoặc dispatch sang worker có transaction riêng.
- Không mặc định chuyển toàn bộ việc đăng ký transactional event sang một **async event multicaster** tùy ý: việc đăng ký listener với transaction cần xảy ra trong context transaction gốc theo hợp đồng của Spring.
- **Sự kiện in-memory có thể mất** nếu process crash ngay sau commit trước khi worker chạy. Nó không tự bảo đảm at-least-once delivery.

### 10.2. Transactional outbox cho công việc phải bền vững

Nếu việc gửi email, cập nhật hệ thống ngoài hoặc xử lý giao dịch tài chính **không được phép mất vì crash/restart**, nên xem xét **transactional outbox**:

~~~text
Caller transaction:
  INSERT purchase_order
  INSERT outbox_event (orderId, eventType, status=PENDING)
  COMMIT cả hai

Background worker:
  CLAIM outbox_event
  READ order by ID trong transaction riêng
  THỰC HIỆN side effect với idempotency key
  UPDATE outbox status / retry metadata
~~~

Outbox giữ metadata công việc **trong cùng transaction** với thay đổi nghiệp vụ. Nó giải quyết rủi ro mất notification giữa commit và in-memory dispatch, nhưng **không tự mang lại exactly-once side effects**; worker cần retry budget, leasing/claiming, idempotency/deduplication và theo dõi trạng thái.

Không đặt EntityManager hoặc managed entity vào outbox payload; ghi **ID và dữ liệu cần thiết có thể serialize**. Nếu cần snapshot đúng ở thời điểm commit, ghi các giá trị đó vào event payload/bảng outbox theo hợp đồng, thay vì kỳ vọng một async worker đọc giá trị ở thời điểm cũ.

## 11. Dữ liệu thay đổi giữa lúc submit và lúc worker đọc

Ngay cả khi dùng ID/DTO và transaction riêng đúng cách, worker **không mặc nhiên đọc cùng snapshot** mà caller vừa thấy.

Ví dụ:

~~~text
T1: Order status = NEW; caller submit async(id=7)
T2: Một transaction khác đổi status thành APPROVED và commit
T3: Worker bắt đầu, mở transaction, find(id=7) -> APPROVED
~~~

Đây không phải race của EntityManager, mà là **race nghiệp vụ giữa các transactions độc lập**. Nếu cần biết chính xác trạng thái tại lúc tạo event, phải mang **immutable snapshot/version** qua event hoặc lưu trong outbox.

Một số chiến lược:

- **Optimistic locking với `@Version`** cho cập nhật đồng thời; xử lý `OptimisticLockException`/Spring exception tương ứng và retry có giới hạn nếu operation idempotent.
- **Conditional update** tại DB khi trạng thái/version vẫn đúng.
- **Idempotency key** để ngăn side effects lặp khi retry.
- **Định nghĩa thứ tự xử lý** (theo aggregate ID) nếu thông điệp có phụ thuộc.
- **READ COMMITTED/SNAPSHOT/REPEATABLE READ** theo nhu cầu database; đừng giả định transaction riêng luôn thấy một snapshot giống caller.
- **Record các thông tin đủ dùng** trong payload khi nghiệp vụ cần tính nhất quán theo thời điểm event.

Tránh cố giải vấn đề version bằng cách để hai thread dùng chung persistence context. Nó chỉ làm phát sinh rủi ro concurrency mới và vẫn không thay thế database concurrency control.

## 12. Vì sao Open EntityManager in View không sửa được ranh giới async?

Trong một số Spring MVC apps, Open EntityManager in View (OEIV) gắn EntityManager vào **thời gian xử lý request** để hỗ trợ lazy access ở tầng view. Nhưng OEIV **không cấp quyền** dùng underlying EM/Session từ worker khác và không biến context thành thread-safe.

Dùng OEIV để "giữ Session mở lâu hơn" còn có những rủi ro:

- Tăng thời gian giữ tài nguyên gắn với request.
- Dễ phát sinh lazy query ở view/serialization, khó kiểm soát N+1.
- Không đảm bảo async worker có cùng transaction, isolation hoặc persistence context.
- Có thể tạo hiểu nhầm vì một endpoint trả entity hoạt động trong trường hợp này nhưng vỡ khi chạy ngoài request.

**Không bật OEIV như bản vá cho `LazyInitializationException` do chuyển entity/lazy proxy sang worker.** Giải pháp là truy vấn/materialize trong transaction thuộc về worker hoặc trả DTO đã chuẩn bị đúng lúc.

## 13. Spring @Async, @Transactional và proxy boundaries

Để method có annotation được xử lý, cần:

1. `@EnableAsync` và `@EnableTransactionManagement` có hiệu lực trong **đúng ApplicationContext**.
2. Bean được Spring quản lý (qua `@Component`/`@Service`/`@Repository` hoặc `@Bean`).
3. Với proxy mode mặc định, lời gọi đi **qua proxy**, không dùng `this.method()` cho method cần advice.
4. Executor được chọn đúng và còn nhận task.
5. Transaction manager đúng cho JPA datasource/persistence unit.

Một anti-pattern:

~~~java
@Service
public class BadService {
    @Transactional
    public void process(Long id) {
        this.doAsync(id); // Không đi qua async proxy.
    }

    @Async
    public void doAsync(Long id) {
        // Có thể chạy đồng bộ ngay trong transaction caller,
        // làm người đọc hiểu nhầm về an toàn thread.
    }
}
~~~

Mảnh code trên thiếu imports; nó cố ý minh họa lỗi self-invocation. Trường hợp này không phải EM được chia sẻ qua hai thread; **vấn đề là @Async không được áp dụng**. Điều nguy hiểm là sau khi refactor để lời gọi thật sự chạy async, một thiết kế vốn phụ thuộc transaction caller có thể lập tức lỗi vì worker không kế thừa nó. Phải sửa **cả data handoff lẫn transaction boundary**.

Trong demo ở phần 7, hai proxy boundaries được tách:

~~~text
Caller -> OrderWriter.create()      [@Transactional trong caller]
        | trả Long id sau commit
        v
Caller -> AsyncOrderLookup.loadAsync(id)  [@Async -> executor]
        |
        v
Worker -> OrderReader.read(id)       [@Transactional trong worker]
        |
        v
Worker EntityManager -> OrderView
~~~

Đây là kiến trúc dễ giải thích, test và quan sát. Một method có thể đồng thời `@Async` và `@Transactional` khi interceptor setup đúng, nhưng không nên coi hai annotation là công cụ truyền transaction cũ sang thread mới.

### 13.1. Không tự propagate TransactionSynchronizationManager

Đừng tự sao chép dữ liệu từ `TransactionSynchronizationManager.getResourceMap()` hoặc các thread-local transaction internals rồi bind vào worker để "chia sẻ" cùng transaction/context. Những tài nguyên như Connection/EntityManager không được thiết kế để phân phối qua worker tùy ý; có thể phá lifecycle, locking và cleanup của transaction manager.

Nếu có thư viện context propagation hỗ trợ MDC/tracing, **điều đó không đồng nghĩa** nên propagate **transaction**. Trace/correlation ID có thể là dữ liệu có ngữ nghĩa request; EntityManager/JDBC connection là stateful resources gắn unit of work.

## 14. Quá tải, exception và cancellation vẫn cần thiết kế

Thiết kế đúng về thread confinement không đảm bảo async job luôn thành công.

### 14.1. Bounded executor và connection pool

Một `ThreadPoolTaskExecutor` có:

- `corePoolSize` / `maxPoolSize`: giới hạn số worker.
- `queueCapacity`: số task chờ, ảnh hưởng latency.
- `RejectedExecutionHandler`: phản ứng khi bão hòa hoặc shutdown.
- `threadNamePrefix`: giúp đọc log/thread dump.

Nếu DB connection pool chỉ có vài connections nhưng executor cho phép quá nhiều workers truy vấn, chúng sẽ tranh connection, queue wait tăng và có thể timeout. Tuning executor phải đi cùng **DataSource pool, DB capacity, query latency và service-level objective**, không chỉ tăng max threads.

Ví dụ `DiscardPolicy` hoặc `DiscardOldestPolicy` có thể âm thầm bỏ task; Future không hoàn thành khiến người dùng chờ mãi. Với công việc bắt buộc, nên dùng **rejection có tín hiệu**, backpressure/rate limit hoặc lưu job bền vững. Không ghi trạng thái "đã xử lý" chỉ vì gọi `@Async` trả một Future.

### 14.2. Exception không làm persistence context có thể tái sử dụng

Khi Hibernate Session gặp lỗi nghiêm trọng, transaction cần rollback và Session/context thường phải bỏ đi, không được xem việc catch exception là đủ để tiếp tục mọi thao tác trên cùng Session. Để Spring transaction interceptor kết thúc/rollback theo hợp đồng hoặc quản lý rollback/close trong code tự quản lý.

Lỗi `LazyInitializationException`, `TransactionRequiredException`, `OptimisticLockException`, `DataAccessException` và `ExecutionException` có ngữ nghĩa khác nhau. Với Future, `get()` có thể ném `ExecutionException` và `join()` có thể ném `CompletionException`; đọc cause để thấy lỗi gốc thay vì đổ lỗi ngay cho executor.

### 14.3. Cancellation và database side effects

`Future.cancel(true)` chỉ **cố yêu cầu interrupt worker** nếu implementation hỗ trợ. Nó không đảm bảo JDBC query dừng lập tức, DB transaction rollback, email bị thu hồi hoặc external payment bị đảo ngược. `CompletableFuture.cancel(true)` theo JDK không dùng tham số `mayInterruptIfRunning` để điều khiển computation nền.

Nên dùng query timeout, transaction timeout và policy cancellation rõ ràng; kiểm thử driver/database thực tế. Không đóng EntityManager **từ caller thread** để cố ngắt một worker đang dùng nó. Worker/transaction manager sở hữu cleanup của context trong worker.

## 15. Kiểm thử ranh giới ORM + async có kiểm soát

Một integration test đáng tin cậy nên chạy **Spring ApplicationContext**, datasource và transaction manager thật hoặc test profile có DB gần môi trường production. Không nên chỉ tạo object bằng `new` rồi mong `@Async`/`@Transactional` có hiệu lực.

Các phép kiểm tra gợi ý:

1. **Thread:** method async chạy trên thread có prefix executor, khác caller.
2. **Transaction tại worker:** `TransactionSynchronizationManager.isActualTransactionActive()` là true trong method transactional được gọi qua proxy.
3. **Không truyền EM/Session:** signature async chỉ có ID/immutable DTO/command, không có `EntityManager`, `Session`, `Query` hoặc managed entity.
4. **Commit visibility:** gửi việc sau khi writer transaction commit có thể đọc row; với gửi trước commit, test tình huống fail/race theo isolation thực.
5. **Lazy associations:** DTO được materialize trong transaction; truy cập DTO bên ngoài không cần Session.
6. **Rollback:** writer transaction rollback thì after-commit listener không được gửi job kiểu đó.
7. **Multiple workers:** chạy đồng thời, xác nhận mỗi worker có ranh giới transaction riêng, không dùng chung EM thực.
8. **Optimistic locking:** update đồng thời có thể báo version conflict, không âm thầm ghi đè.
9. **Timeout/rejection:** Future/HTTP/job status báo lỗi đúng và cleanup; không treo vô hạn.
10. **Crash/restart:** nếu cần durability, outbox/job store còn tác vụ pending và worker có thể retry.
11. **Context propagation:** trace ID được truyền bằng cơ chế an toàn, nhưng không sao chép transaction resource.
12. **Connection pool:** load test với concurrency/queue phù hợp, không bị starvation vì pool DB quá nhỏ.

### 15.1. Test có thể dùng latch để kiểm tra isolation

Nếu cần chứng minh hai worker có hoạt động chồng lấp, dùng `CountDownLatch` để chắc rằng chúng đã vào transaction và đang chờ ở điểm kiểm tra trước khi giải phóng. Khi đó đo active thread/transaction tại từng worker; **đừng chia sẻ một Session duy nhất chỉ để "test concurrent read"**. Hai EntityManager riêng mới là hành vi đúng cần kiểm chứng.

Tránh test chỉ đo thời gian ngắn hơn một ngưỡng bất kỳ: JVM warmup, H2 memory mode, executor scheduling và CI load khiến kết quả dao động. Kiểm tra đúng thread, transaction và DTO output là tín hiệu ổn định hơn.

## 16. Các lỗi thường gặp và cách sửa

| Anti-pattern | Nguy cơ | Thay bằng |
| --- | --- | --- |
| Truyền `EntityManager` thực vào `@Async` | Shared non-thread-safe context, sai lifecycle | Truyền ID; load trong transaction worker |
| Truyền `session = em.unwrap(Session.class)` | Worker chạm Hibernate Session của caller | Không unwrap để handoff; dùng repository tại worker |
| Tạo `EntityManager` ngoài rồi để nhiều tasks dùng chung | Race, flush/cache/lifecycle không an toàn | Tạo EM riêng per worker/unit of work và close |
| Singleton giữ `@PersistenceContext(EXTENDED)` | Extended context không thread-safe | Dùng transaction-scoped proxy mặc định |
| Hiểu field `@PersistenceContext` singleton là Session thật duy nhất | Nhầm shared proxy với underlying context | Hiểu cơ chế delegation theo transaction |
| Truyền managed entity vào async task | Data race và lazy access sai | ID/immutable DTO, materialize đúng transaction |
| Trả `PersistentCollection`/JPA Stream qua Future | Session/connection phụ thuộc lifecycle cũ | Map sang DTO/list snapshot trước khi trả |
| `@Async` đọc row trước writer commit | Không thấy dữ liệu hoặc block vì lock | After-commit dispatch / outbox tùy durability |
| Dùng `@Transactional` tại caller rồi kỳ vọng worker kế thừa | Transaction thread-bound | Worker tự mở transaction qua proxy |
| Dùng `this.asyncMethod()` trong cùng bean | Bỏ qua async proxy mặc định | Tách bean cộng tác hoặc gọi qua proxy đúng |
| Copy transaction thread-local sang worker | Chia sẻ stateful JDBC/JPA resources sai | Propagate dữ liệu thuần, không propagate tx |
| Bật OEIV để tránh lỗi lazy ở worker | Không giải quyết thread confinement | Fetch/materialize trong đúng transaction |
| `readOnly=true` rồi chia sẻ EM thực | Read-only không biến EM thành thread-safe | Context riêng per worker |
| Future.cancel(true) và tin DB đã rollback | Cancel là best-effort | Transaction/query timeout, verify outcome |
| Gửi async rồi trả 202 Accepted như bảo đảm durable | Job có thể mất khi crash/rejection | Job store/outbox với status rõ |
| Quá nhiều worker so với DB connections | Pool exhaustion/latency | Bounded concurrency và DB pool sizing |

## 17. Checklist code review

- [ ] Không truyền `EntityManager` thực, `Session` thực, `Query`, `EntityTransaction` hoặc Hibernate collection proxy sang worker khác.
- [ ] Phân biệt **Spring `@PersistenceContext` shared proxy** với **provider EntityManager thực**.
- [ ] Không đặt `PersistenceContextType.EXTENDED` vào singleton được gọi đồng thời.
- [ ] Không đưa managed JPA entity qua async boundary; dùng ID/immutable DTO/command với semantic rõ.
- [ ] Mỗi database operation tại worker có transaction riêng được quản lý qua Spring service/repository proxy.
- [ ] `@EnableAsync` và `@EnableTransactionManagement` ở đúng context, không self-invoke method cần advice.
- [ ] Không dựa vào transaction/ThreadLocal của caller sau khi chuyển thread.
- [ ] Có quy tắc **sau commit** khi worker cần đọc dữ liệu vừa ghi.
- [ ] Với task quan trọng, lưu outbox/job để chịu được crash/restart.
- [ ] DTO được materialize hoàn toàn; không lộ lazy association, JPA Stream hoặc provider handles.
- [ ] Có optimistic locking/idempotency khi các worker cập nhật cùng bản ghi.
- [ ] Executor và DB connection pool được sizing phù hợp; rejection có tín hiệu khi cần.
- [ ] Future/CompletableFuture được giám sát lỗi, timeout và cancellation; không nuốt lỗi nền.
- [ ] Có integration test thật cho thread, transaction, commit visibility, rollback và reload DTO.
- [ ] Không sử dụng `em.close()` lên shared proxy do Spring quản lý; để framework quản lý lifecycle.
- [ ] Manual EntityManager (nếu thật sự cần) chỉ tạo/sử dụng/đóng trong unit of work thuộc thread sở hữu.
- [ ] Tracing có correlation ID, nhưng transaction resources không được copy qua threads.

## 18. Câu hỏi tự kiểm tra

1. **Vì sao không nên gửi Hibernate `Session` vào `CompletableFuture.supplyAsync`?** Vì Session thực có trạng thái và không thread-safe; unit of work/transaction không tự di chuyển.
2. **`EntityManagerFactory` có thể là singleton được nhiều worker dùng không?** Có. Factory dùng chung, từng worker cần context/transaction thích hợp.
3. **Field `@PersistenceContext` trong singleton Spring repository có luôn là một provider EntityManager duy nhất không?** Không. Mặc định nó thường là shared proxy delegate theo transaction.
4. **Dùng chung reference shared proxy có đồng nghĩa dùng chung persistence context không?** Không; chính proxy chọn underlying EM theo transaction/operation.
5. **Vì sao `@PersistenceContext(type=EXTENDED)` khác?** Nó tạo extended persistence context có vòng đời dài, không phù hợp cho singleton concurrent access.
6. **Có thể truyền một managed entity sang worker thay EM không?** Không nên. Entity có thể mutable/lazy, gắn với context cũ và không tự thread-safe.
7. **Worker cần dữ liệu order thì nên nhận gì?** ID hoặc immutable command/DTO, rồi load bằng repository/transaction worker.
8. **`@Transactional` tại caller có đi theo `@Async` worker không?** Không với imperative thread-bound transactions.
9. **Vì sao gửi async trước commit có thể thấy "not found"?** Worker có transaction riêng và không thấy dữ liệu chưa commit theo isolation của DB.
10. **Khi nào dùng `@TransactionalEventListener(AFTER_COMMIT)`?** Khi muốn chỉ dispatch công việc sau khi transaction gốc commit thành công và chấp nhận hạn chế in-memory delivery.
11. **Khi nào cần outbox?** Khi task/event bắt buộc sống qua crash, phải có retry và ghi nhận trạng thái bền vững.
12. **`@Transactional(readOnly=true)` có làm EntityManager thực thread-safe không?** Không.
13. **Nếu caller và worker cùng update một row bằng EM riêng, xử lý xung đột ra sao?** Locking/versioning, constraints, retries có kiểm soát và idempotency.
14. **OEIV có cho phép worker sử dụng session của request không?** Không; nó không biến Session thành thread-safe.
15. **`Future.cancel(true)` có chắc đóng Session và rollback transaction không?** Không. Hủy là best-effort; transaction/driver/lifecycle quyết định.
16. **Nếu cần database access trong worker ngoài Spring, làm sao quản lý EM?** Dùng shared EntityManagerFactory, tạo EntityManager **tại worker**, quản lý transaction và close ở cùng unit of work.
17. **Cách test hiệu quả hơn đo thời gian thuần túy là gì?** Kiểm tra thread name, worker transaction active, DTO đúng, visibility sau commit và concurrency bằng latch.
18. **Điều gì được "chia sẻ" một cách an toàn trong Spring repository dùng @PersistenceContext?** Shared proxy reference, **không phải một underlying persistence context thực**.

**Kết luận:** Đừng chuyển **EntityManager/Session thực hoặc managed ORM objects** sang thread khác để tái sử dụng transaction/persistence context. Trong Spring, hãy chuyển **ID hoặc dữ liệu bất biến** và để **worker có transaction/persistence context riêng**. `@PersistenceContext` mặc định trong singleton repository là shared proxy có khả năng điều phối theo transaction; nó **không** phải ngoại lệ cho phép chia sẻ một Hibernate Session thực. Đồng thời kiểm soát thời điểm commit, lazy data, overload, durability và các cập nhật cạnh tranh.

### Tài liệu chính thức

- [Jakarta Persistence 3.1 — Persistence Context, EntityManager và thread safety](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Spring Framework — JPA: EntityManagerFactory, @PersistenceContext và EXTENDED](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Framework 6.1 — SharedEntityManagerCreator](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/orm/jpa/SharedEntityManagerCreator.html)
- [Spring Framework — Declarative Transactions and Thread-bound Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Hibernate ORM — Session Javadoc](https://docs.jboss.org/hibernate/orm/6.4/javadocs/org/hibernate/Session.html)
- [Hibernate ORM — Transactions and Session-per-application Anti-pattern](https://docs.jboss.org/hibernate/orm/6.4/userguide/html_single/Hibernate_User_Guide.html#transactions-basics)
