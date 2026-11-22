# Nhận diện lỗi cần giao dịch đang hoạt động trong JPA

Khi làm việc với **Jakarta Persistence (JPA)**, một số thao tác trên `EntityManager` chỉ đọc dữ liệu hoặc mô tả truy vấn, trong khi những thao tác khác **phải được thực hiện trong một giao dịch đang hoạt động**. Nếu ứng dụng gọi một thao tác thuộc nhóm thứ hai khi điều kiện giao dịch chưa được đáp ứng, JPA có thể ném:

~~~text
jakarta.persistence.TransactionRequiredException:
    no transaction is in progress
~~~

Hoặc một thông điệp khác tùy provider:

~~~text
TransactionRequiredException:
    Executing an update/delete query
~~~

Ví dụ dễ tái hiện:

~~~java
EntityManager em = emf.createEntityManager();
try {
    em.createQuery(
        "UPDATE Product p " +
        "SET p.active = false WHERE p.id = :id")
      .setParameter("id", 10L)
      .executeUpdate(); // Thiếu transaction.
} finally {
    em.close();
}
~~~

Nếu persistence unit dùng **RESOURCE_LOCAL**, cách sửa là đặt operation trong transaction có `begin()` và `commit()`/`rollback()`. Nếu ứng dụng dùng **Spring/JTA**, transaction phải do transaction manager hoặc container tạo và quản lý; không tự chèn `em.getTransaction().begin()` vào một JTA-managed `EntityManager`. Ngoài ra, trong JTA, transaction có thể đang active nhưng **unsynchronized persistence context chưa joined** với transaction ấy.

**Mục tiêu của bài:** nhận diện chính xác operation cần giao dịch, đọc exception và cause chain, phân biệt transaction với persistence context, xác định ai mở/commit/rollback giao dịch, và sửa tận gốc các lỗi về ranh giới giao dịch thay vì bắt exception rồi thử lại tùy tiện.

## 1. Ba câu hỏi cần trả lời khi gặp lỗi

Hãy điều tra theo thứ tự:

1. **Operation JPA nào phát lỗi?** `flush()`, `executeUpdate()`, `lock()`, `find()` có lock mode, hay lifecycle method?
2. **Có active transaction phù hợp không?** Giao dịch đang chạy do `EntityTransaction`, JTA hoặc Spring transaction manager sở hữu?
3. **EntityManager có thực sự tham gia transaction đó không?** Đặc biệt nếu có nhiều EntityManagerFactory, nhiều transaction managers hoặc `SynchronizationType.UNSYNCHRONIZED`.

~~~text
Operation yêu cầu transaction
              |
              v
       Có transaction?
         /        \
      Không        Có
        |           |
        v           v
   Sửa boundary  EntityManager tham gia?
                   /         \
                 Không        Có
                  |           |
                  v           v
             Sửa wiring/   Đọc cause chain,
             join/manager  xem lỗi khác
~~~

Không chỉ nhìn thấy một annotation `@Transactional` rồi kết luận transaction đã tồn tại. Điều quan trọng là interceptor/manager có **thực sự chạy cho đúng đường gọi** hay không.

## 2. TransactionRequiredException là gì?

JPA định nghĩa exception:

~~~java
import jakarta.persistence.TransactionRequiredException;
~~~

Đây là unchecked exception, dùng khi một phương thức **yêu cầu transaction** nhưng không có transaction thích hợp để thực thi operation. Thông điệp của provider có thể khác nhau:

~~~text
no transaction is in progress
transaction is required
Executing an update/delete query
Unable to flush without an active transaction
EntityManager is not joined to a transaction
~~~

Không nên dùng phép so khớp nguyên văn exception message để quyết định retry hoặc mở transaction. Cần xét **exception class**, **cause chain** và **operation đang được thực hiện**.

### Vì sao cùng lỗi lại có nhiều thông điệp?

Các implementation như Hibernate ORM và EclipseLink có cách đặt message/stack trace khác nhau. Spring còn có thể dịch exception thành một lớp trong `org.springframework.dao.DataAccessException` rồi đặt JPA exception ở `cause`. Tên class/contract ổn định hơn những câu chữ trong log.

### Khi nào phải tìm root cause?

Nếu gặp:

~~~text
org.springframework.dao.InvalidDataAccessApiUsageException
  caused by jakarta.persistence.TransactionRequiredException
~~~

thì nguyên nhân có thể là thiếu JPA transaction mặc dù top-level exception mang tên Spring.

Nếu gặp `RollbackException` và cause là unique constraint violation, đó **không phải lỗi thiếu transaction** chỉ vì nó xảy ra lúc commit.

## 3. Transaction khác EntityManager như thế nào?

`EntityManager` là đối tượng quản lý persistence context và API truy cập dữ liệu:

~~~java
EntityManager em = emf.createEntityManager();
~~~

Việc tạo EntityManager **không tự chứng minh** có transaction đang hoạt động.

~~~text
EntityManager:
  Identity map/first-level cache
  Managed entities
  Dirty checking
  Query APIs
  Flush/lifecycle operations

Transaction:
  BEGIN
  Unit of work
  COMMIT hoặc ROLLBACK
~~~

Một persistence context có thể sống ngắn hơn, bằng hoặc dài hơn transaction tùy transaction-scoped/extended context và framework. Một EntityManager đang mở cũng không có nghĩa database transaction còn mở.

### Giao dịch không giống một JDBC connection

Kết nối tới database thành công không có nghĩa các câu lệnh JPA đang được enlisted vào một transaction thích hợp. JDBC auto-commit, JTA enlistment và JPA flush synchronization là những cơ chế khác nhau.

## 4. Bảng thao tác thường cần transaction

| Operation JPA | Yêu cầu | Ghi chú |
| --- | --- | --- |
| `em.flush()` | Active transaction phù hợp | Đồng bộ thay đổi từ context xuống DB |
| `Query.executeUpdate()` cho JPQL UPDATE/DELETE | Có | Bulk DML cần transaction |
| Native SQL UPDATE/DELETE qua `executeUpdate()` | Có | Native query không bỏ qua requirement |
| `em.lock(entity, mode)` với mode khác NONE | Có | Lock thuộc giao dịch |
| `em.find(..., PESSIMISTIC_WRITE)` | Có | Pessimistic lock cần transaction |
| `em.find(..., OPTIMISTIC)` | Có theo contract lock mode | Lock modes khác NONE có transaction requirement |
| `em.refresh(entity, lockMode)` | Có với locking; scope context cũng quan trọng | Không thay thế transaction |
| `em.getLockMode(entity)` | Yêu cầu transaction theo JPA API contract | Không đơn giản là getter Java thuần |
| `persist()/merge()/remove()/refresh()` | Cần transaction context trong transaction-scoped persistence context | Extended context có quy tắc defer riêng |
| `em.find(Entity.class,id)` không lock | Không nhất thiết | Đọc không tự chứng minh transaction active |
| JPQL SELECT với `getResultList()` | Không nhất thiết | Read consistency vẫn phải thiết kế |
| `em.createQuery()` | Không chỉ để tạo query object | DML requirement bộc lộ khi execute |
| `emf.getMetamodel()` | Không cần transaction để duyệt metadata | Không phải truy vấn business rows |

**Đừng suy từ một thao tác SELECT chạy thành công rằng mọi thao tác UPDATE/DELETE sau đó đều đã có transaction.**

## 5. createQuery không giống executeUpdate

Một lời gọi:

~~~java
Query query = em.createQuery(
    "UPDATE Product p SET p.active = false");
~~~

chỉ tạo một query object.

Lời gọi:

~~~java
int affected = query.executeUpdate();
~~~

mới yêu cầu thực hiện SQL mutation và cần transaction. Vì vậy:

~~~text
createQuery() thành công
executeUpdate() ném TransactionRequiredException
~~~

không có gì mâu thuẫn.

### Tình huống đọc

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p WHERE p.active = true",
        Product.class)
    .getResultList();
~~~

SELECT thông thường có thể hoạt động ngoài transaction trong những điều kiện JPA/provider phù hợp. Nhưng nếu query mang một **lock mode khác NONE**, transaction requirement trở nên quan trọng.

## 6. Vì sao flush cần giao dịch?

JPA theo dõi thay đổi trên managed entity:

~~~java
Product p = em.find(Product.class, productId);
p.changePrice(new BigDecimal("120000.00"));
~~~

Chỉ sửa Java object chưa phải là commit. Khi:

~~~java
em.flush();
~~~

provider có thể phát SQL:

~~~sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Flush đưa persistent state đang pending vào database theo transaction synchronization. Nếu không có transaction active hoặc context chưa joined theo yêu cầu, operation có thể báo `TransactionRequiredException`.

### Flush khác commit

~~~text
tx.begin()
  em.flush()  -> SQL được gửi trong transaction
  tx.commit() -> Xác nhận dữ liệu
~~~

Flush thành công chưa có nghĩa commit. Nếu rollback sau flush, thay đổi thuộc transaction bị rollback theo database semantics.

### Không dùng flush như Validator thuần

Nếu chỉ cần kiểm tra một Java object theo Bean Validation constraints, dùng `jakarta.validation.Validator` hoặc domain rules thích hợp. `flush()` là thao tác persistence synchronization, không phải một phép kiểm tra object vô hại ngoài transaction.

## 7. executeUpdate với JPQL UPDATE

Ví dụ thiếu transaction:

~~~java
int updated = em.createQuery(
        "UPDATE Product p SET p.active = false " +
        "WHERE p.id = :id")
    .setParameter("id", productId)
    .executeUpdate();
~~~

Ở một EntityManager resource-local chưa gọi `begin()`, đây là ví dụ điển hình gây lỗi transaction required.

### Resource-local đúng

~~~java
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();

    int updated = em.createQuery(
            "UPDATE Product p SET p.active = false " +
            "WHERE p.id = :id")
        .setParameter("id", productId)
        .executeUpdate();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

### Một vấn đề khác: bulk UPDATE

JPQL bulk UPDATE có thể bypass per-entity dirty checking, callbacks, optimistic version handling và làm những managed entities đang có trở nên stale. Active transaction chỉ giải quyết **tiền điều kiện thực thi**, không tự đảm bảo caching/concurrency đúng.

## 8. executeUpdate với DELETE và native SQL

JPQL DELETE:

~~~java
em.createQuery(
    "DELETE FROM ExpiredToken t WHERE t.expiresAt < :now")
  .setParameter("now", Instant.now())
  .executeUpdate();
~~~

Native DML:

~~~java
em.createNativeQuery(
    "DELETE FROM expired_tokens WHERE expires_at < ?")
  .setParameter(1, Timestamp.from(Instant.now()))
  .executeUpdate();
~~~

Cả hai đều là dữ liệu bị thay đổi qua JPA Query API và **cần transaction phù hợp**.

### Tại sao chuyển sang native SQL không chữa lỗi?

Vì transaction requirement ở đây gắn với **operation DML thực thi qua JPA**, không phải chỉ cú pháp JPQL.

### JDBC auto-commit có giống không?

Không. JDBC connection auto-commit có semantics riêng; tự gọi JDBC ngoài transaction manager có thể tạo những commits độc lập, phá atomicity của use case kết hợp JPA và JDBC.

## 9. Locking và transaction

Pessimistic lock cần transaction để giữ khóa đủ lâu cho check-then-act:

~~~java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Không được mặc định rằng provider sẽ mở một transaction ngầm để giữ `PESSIMISTIC_WRITE`.

### Các lock mode thường gặp

~~~java
LockModeType.NONE
LockModeType.OPTIMISTIC
LockModeType.OPTIMISTIC_FORCE_INCREMENT
LockModeType.PESSIMISTIC_READ
LockModeType.PESSIMISTIC_WRITE
LockModeType.PESSIMISTIC_FORCE_INCREMENT
~~~

Lock modes khác NONE có transaction requirements trên các method hỗ trợ locking.

### Thực hiện đúng

~~~java
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();

    Product product = em.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (product == null) {
        throw new IllegalArgumentException(
            "Product không tồn tại");
    }

    product.changePrice(nextPrice);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

**Có transaction không bảo đảm lấy lock thành công.** Deadlock, timeout hoặc database failure có thể phát sinh exception khác.

## 10. Phân biệt lỗi khóa và lỗi thiếu transaction

| Lỗi | Nghĩa chính |
| --- | --- |
| `TransactionRequiredException` | Thiếu transaction/context phù hợp với operation |
| `LockTimeoutException` | Không lấy được lock trong giới hạn, theo semantics của operation |
| `PessimisticLockException` | Lỗi pessimistic locking với transaction consequences tương ứng |
| `OptimisticLockException` | Stale version hoặc optimistic concurrency conflict |

Nếu đã mở transaction mà vẫn gặp `OptimisticLockException`, không thể chữa chỉ bằng cách thêm một `@Transactional`. Phải rollback, đọc lại state và revalidate invariants khi retry an toàn.

Nếu `LockTimeoutException`, cần xem lock contention, timeout, thứ tự khóa và DB isolation. Nó không đồng nghĩa transaction đang thiếu.

## 11. find() không lock có thể chạy ngoài transaction

~~~java
Product p = em.find(Product.class, 10L);
~~~

JPA cho phép một số hoạt động read-only không có active transaction tùy persistence context type và môi trường. Nhưng:

- Entity có thể detached khi context kết thúc.
- Lazy associations có thể chưa được khởi tạo.
- Dữ liệu nhiều SELECT không tự nằm trong một consistent snapshot.
- Kết quả không có nghĩa transaction ghi đã bắt đầu.

### Sai lầm

~~~java
Product p = em.find(Product.class, id);
// find chạy được, nên em.flush() chắc cũng chạy.
em.flush();
~~~

Hai thao tác có **transaction prerequisites khác nhau**. Để thực hiện nghiệp vụ gồm đọc rồi ghi, phải đặt toàn bộ use case trong boundary phù hợp.

## 12. Persist, merge, remove và refresh: phải xét context scope

Các lifecycle operations:

~~~java
em.persist(newEntity);
em.merge(detachedEntity);
em.remove(managedEntity);
em.refresh(managedEntity);
~~~

Trong **transaction-scoped persistence context**, JPA yêu cầu transaction context thích hợp cho những hoạt động lifecycle này. Nhưng không nên tuyên bố rằng mọi môi trường đều ném exception ngay tại lời gọi tương ứng.

### Extended persistence context

Với **extended context**, một số lifecycle changes như persist/merge/remove có thể được chấp nhận và **được giữ trong context** cho đến khi tham gia transaction thích hợp.

Điều này không có nghĩa:

~~~text
persist() ngoài transaction -> row đã commit
~~~

hoặc:

~~~text
remove() ngoài transaction -> SQL DELETE đã hoàn thành
~~~

### Quy tắc suy luận

Luôn hỏi **context thuộc loại nào**, **transaction có active/joined không**, và **khi nào SQL/commit thực sự xảy ra**. Không lấy việc method return không lỗi làm bằng chứng dữ liệu đã được ghi.

## 13. Transaction-scoped và extended persistence context

Sơ đồ:

~~~text
Transaction-scoped:
  TX_A -> persistence context gắn với TX_A
  Commit/rollback -> context theo lifecycle container

Extended:
  Persistence context sống qua nhiều TX boundaries
      |
      +-- TX_A join -> đồng bộ
      +-- ngoài TX   -> một số changes có thể chờ
      +-- TX_B join -> đồng bộ tiếp
~~~

Trong bối cảnh Jakarta EE/JTA hỗ trợ extended:

~~~java
@PersistenceContext(
    type = PersistenceContextType.EXTENDED
)
private EntityManager em;
~~~

### Có nên đổi sang EXTENDED để tránh TransactionRequiredException?

Không. `flush()`, bulk DML và locking vẫn có transaction requirements. Extended context có memory/concurrency/lifecycle semantics phức tạp hơn; chỉ dùng khi conversational workflow thật sự cần.

## 14. RESOURCE_LOCAL: ai sở hữu transaction?

Trong Java SE/resource-local:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();
~~~

Ứng dụng mở và kết thúc transaction:

~~~java
tx.begin();
// work
tx.commit();
~~~

Khi lỗi:

~~~java
if (tx.isActive()) {
    tx.rollback();
}
~~~

### Template đầy đủ

~~~java
public Long saveProduct(
        EntityManagerFactory emf,
        Product product) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();
        em.persist(product);
        em.flush();

        Long id = product.getId();
        tx.commit();
        return id;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

`Product.getId()` và các mappings của Product cần được định nghĩa trong entity. ID có thể được cấp trước commit tùy generation strategy; có ID **không** chứng minh dữ liệu đã commit.

## 15. Kiểm tra resource-local transaction có active không

~~~java
EntityTransaction tx = em.getTransaction();

if (!tx.isActive()) {
    throw new IllegalStateException(
        "Operation này cần active transaction");
}
~~~

`EntityTransaction.isActive()` là phép kiểm tra đúng mô hình **resource-local transaction**.

### Nhưng không nên auto-begin ở mọi repository method

Sai về thiết kế:

~~~java
if (!tx.isActive()) {
    tx.begin();
}
// execute DML
tx.commit();
~~~

Nếu nhiều repository methods thuộc một use case phải commit cùng nhau, helper này có thể tạo nhiều commits riêng, phá tính atomic.

### Cách tốt hơn

~~~text
Application service:
    begin()
      repository A
      repository B
      domain validation
      flush
    commit()/rollback()
~~~

Một owner quyết định transaction boundary, các helpers không tự “cứu” transaction bằng begin/commit rời rạc.

## 16. JTA: không dùng em.getTransaction().begin()

Với JTA-managed persistence unit, transaction do **JTA transaction manager/container** sở hữu:

~~~java
@PersistenceContext
private EntityManager em;
~~~

Lời gọi:

~~~java
em.getTransaction().begin();
~~~

không phải cách hợp lệ để điều khiển một JTA EntityManager như resource-local. Nó có thể ném `IllegalStateException` hoặc lỗi API khác.

### Jakarta Transactions service

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class ProductApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameProduct(
            long productId,
            String name) {

        Product p = em.find(
            Product.class, productId);

        if (p == null) {
            throw new IllegalArgumentException(
                "Product không tồn tại");
        }
        p.rename(name);
    }
}
~~~

Đây là ví dụ về component được Jakarta EE/CDI/container quản lý với transaction interceptor phù hợp; `rename` là domain method cần có trong Product thực tế.

### Annotation không tự hoạt động khi new object

Nếu tự `new ProductApplicationService()` ngoài container, không có lý do để giả định dependency injection/transaction interceptor vẫn được áp dụng.

## 17. JTA UserTransaction: trường hợp bean-managed

Ở môi trường cho phép BMT:

~~~java
@Resource
private UserTransaction userTransaction;

public void runWork() throws Exception {
    userTransaction.begin();
    try {
        // JTA-managed operations
        userTransaction.commit();
    } catch (Exception ex) {
        try {
            userTransaction.rollback();
        } catch (Exception rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
}
~~~

Không chèn `UserTransaction.begin()` vào một method CMT/Spring-managed transaction mà không hiểu quyền điều khiển transaction của container. Điều này có thể làm sai transaction ownership hoặc gây exception khác.

### RESOURCE_LOCAL hay JTA?

| Đặc điểm | RESOURCE_LOCAL | JTA |
| --- | --- | --- |
| API thường dùng để điều khiển | `EntityTransaction` | Container/JTA manager |
| `em.getTransaction().begin()` | Phù hợp | Không phù hợp |
| Resource enlistment | Resource-local | JTA-coordinated |
| Integration với container | Có thể standalone | Container/framework cần thiết |
| Lỗi thường gặp | Quên begin | Interceptor/wiring/join không đúng |

## 18. Active transaction chưa chắc persistence context đã joined

Trong JTA, có thể có:

~~~text
JTA transaction: ACTIVE
       |
       +-- EM-A SYNCHRONIZED -> joined
       |
       +-- EM-B UNSYNCHRONIZED -> chưa joined
~~~

Một transaction tồn tại trong transaction manager không có nghĩa mọi EntityManager trên thread đều tự tham gia.

### Kiểm tra joined

~~~java
boolean joined = em.isJoinedToTransaction();
~~~

`isJoinedToTransaction()` hữu ích khi chẩn đoán JTA synchronization. Nó không phải phép thay thế tùy tiện cho `EntityTransaction.isActive()` của resource-local trong mọi kiến trúc.

### Nguyên tắc

Nếu transaction active mà `flush()` vẫn lỗi, xem **đúng EM instance**, **đúng EMF**, **synchronization mode** và **join state**.

## 19. SynchronizationType.UNSYNCHRONIZED

JPA có:

~~~java
SynchronizationType.SYNCHRONIZED
SynchronizationType.UNSYNCHRONIZED
~~~

Trong JTA-managed environment phù hợp:

~~~java
@PersistenceContext(
    synchronization =
        SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
~~~

Unsynchronized context không tự động tham gia JTA transaction theo cách synchronized context thường làm. Muốn đồng bộ trong một active JTA transaction:

~~~java
em.joinTransaction();
~~~

### joinTransaction() không tạo transaction

Nếu không có active JTA transaction, `joinTransaction()` không phải câu lệnh bắt đầu transaction mới; operation có thể ném lỗi.

### Khi nào dùng UNSYNCHRONIZED?

Khi một workflow cần duy trì entity state nhưng **chủ động chọn thời điểm tham gia transaction**. Đây là kỹ thuật nâng cao; không cần thiết với phần lớn CRUD thông thường.

## 20. Spring: transaction boundary ở service

Trong Spring, mẫu phổ biến:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void changePrice(
            long id,
            BigDecimal nextPrice) {

        Product p = em.find(Product.class, id);
        if (p == null) {
            throw new IllegalArgumentException(
                "Product không tồn tại");
        }

        p.changePrice(nextPrice);
    }

    @Transactional
    public int deactivateAll() {
        return em.createQuery(
            "UPDATE Product p SET p.active = false")
          .executeUpdate();
    }
}
~~~

Ví dụ này giả định Product có `active` và các getter/domain methods tương ứng.

### Vì sao không tự gọi em.getTransaction()?

Spring transaction manager sở hữu begin/commit/rollback và EntityManager được bind theo transaction. Gọi `em.getTransaction().begin()` trên transaction-managed EntityManager có thể không hợp lệ.

### Khi nào commit?

Nếu Spring proxy tạo transaction mới cho method, interceptor thường commit sau khi method body hoàn tất. Nếu method tham gia transaction ở caller, **caller/outer boundary** mới là nơi commit.

## 21. @Transactional có thể sai import hoặc sai runtime

Hai annotation:

~~~java
org.springframework.transaction.annotation.Transactional
~~~

và:

~~~java
jakarta.transaction.Transactional
~~~

thuộc hai API. Framework có thể hỗ trợ xử lý cả hai trong một số cấu hình, nhưng **đừng giả định mọi container/Spring version tự xử lý annotation không đúng môi trường**.

### Cần kiểm tra

- Method nằm trong bean container quản lý không?
- Có transaction interceptor/proxy không?
- Annotation được framework hỗ trợ/enable không?
- Transaction manager có liên kết với đúng persistence unit không?
- Call path có đi qua interceptor không?

Annotation chỉ là metadata nếu không có cơ chế runtime xử lý.

## 22. Lỗi Spring self-invocation

Ví dụ:

~~~java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    public void handleRequest(long id) {
        deactivate(id); // Gọi cùng bean qua this.
    }

    @Transactional
    public void deactivate(long id) {
        em.createQuery(
            "UPDATE Product p SET p.active = false " +
            "WHERE p.id = :id")
          .setParameter("id", id)
          .executeUpdate();
    }
}
~~~

Với **Spring proxy-based transactions**, lời gọi `this.deactivate(id)` không đi qua proxy cho method con. Nếu `handleRequest()` không có transaction, DML có thể gây `TransactionRequiredException`.

~~~text
HTTP -> Spring proxy -> handleRequest()
                             |
                             v
                        this.deactivate()
                             |
                             v
                     Không qua tx advice
                             |
                             v
                         executeUpdate()
~~~

### Sửa cách 1: transaction tại entrypoint

~~~java
@Transactional
public void handleRequest(long id) {
    deactivate(id);
}
~~~

Miễn là `handleRequest()` được caller bên ngoài gọi qua proxy.

### Sửa cách 2: tách bean

Đặt `deactivate()` trong một Spring-managed service khác và inject service ấy, để lời gọi đi qua transactional proxy.

### Không kết luận cho AspectJ weaving

Spring có các chế độ transaction advice khác proxy-based; self-invocation semantics có thể khác khi dùng weaving. Phải xác định cơ chế thực tế của project.

## 23. Private methods, final methods và new service

Một private helper:

~~~java
@Transactional
private void updateDatabase() {
    // ...
}
~~~

không phải transaction entrypoint đáng tin trong Spring proxy-based AOP. Visibility/final limitations còn tùy loại proxy/version.

Tương tự:

~~~java
ProductService service = new ProductService();
service.deactivate(10L);
~~~

không đi qua Spring container, nên không có transaction interceptor và dependency injection như một managed bean.

### Thiết kế khuyến nghị

Đặt transaction ở method service được framework quản lý, gọi từ ngoài bean qua proxy. Các internal private helpers chỉ thực hiện logic trong transaction đã mở sẵn.

## 24. Propagation.REQUIRED

Trong Spring:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED
)
public void update(...) {
    // ...
}
~~~

`REQUIRED` tham gia transaction hiện có nếu phù hợp, hoặc tạo transaction mới khi chưa có.

Đây thường là propagation phù hợp cho application service cần ghi database.

### Không tự động giải quyết mọi lỗi

Nếu method không đi qua Spring proxy, hoặc chọn sai transaction manager, `REQUIRED` annotation có thể không được áp dụng theo ý định.

## 25. Propagation.MANDATORY

~~~java
@Transactional(
    propagation = Propagation.MANDATORY
)
public void reserveInventory(...) {
    // ...
}
~~~

`MANDATORY` đòi caller đã có transaction. Khi không có, Spring transaction infrastructure có thể ném một exception về propagation requirement, **không bắt buộc là class JPA TransactionRequiredException**.

### Khi nào hữu ích?

Một helper phải thuộc chung unit of work của `OrderService`:

~~~text
OrderService @Transactional
    |
    +-- InventoryService MANDATORY
    +-- LedgerService MANDATORY
    |
    +-- commit/rollback chung
~~~

Nhờ MANDATORY, một caller quên transaction sẽ bị báo sớm thay vì helper tự commit riêng.

## 26. SUPPORTS, NOT_SUPPORTED và NEVER

### SUPPORTS

`SUPPORTS` tham gia transaction nếu có, nhưng **có thể chạy không transaction** nếu caller không mở.

Vì thế một method luôn gọi `executeUpdate()` không nên dùng SUPPORTS chỉ vì tên nghe giống “hỗ trợ transaction”.

### NOT_SUPPORTED

`NOT_SUPPORTED` chạy không transaction, có thể suspend transaction đang có. Nó không phù hợp với method bắt buộc thực hiện JPA bulk DML/flush.

### NEVER

`NEVER` từ chối invocation đang có transaction. Nó không phù hợp với operation bắt buộc transaction.

### Kết luận

Chọn propagation dựa trên **contract thực sự**:

- Cần transaction và tự tạo nếu thiếu: REQUIRED.
- Bắt buộc caller đã tạo: MANDATORY.
- Không cần transaction cho thao tác đọc nhất định: có thể cân nhắc SUPPORTS.

## 27. REQUIRES_NEW có thể sửa lỗi nhưng phá atomicity

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW
)
public void decrementStock(...) {
    // ...
}
~~~

`REQUIRES_NEW` tạo một transaction độc lập. Nó không nên là phản xạ mặc định để loại bỏ TransactionRequiredException.

Ví dụ nguy hiểm:

~~~text
Order transaction:
   INSERT Order (chưa commit)
   |
   +-- Inventory REQUIRES_NEW
         UPDATE Stock
         COMMIT
   |
   Order transaction ROLLBACK
~~~

Stock đã trừ nhưng Order không tồn tại nếu hai writes cần atomic.

### Khi nào hợp lý?

Khi nghiệp vụ **chủ đích** cần transaction độc lập, ví dụ một bản ghi audit với policy riêng. Quyết định ấy phải xét side effects, consistency và retry.

### NESTED

`Propagation.NESTED` dựa vào savepoint/transaction-manager support; không phải JPA nested transaction portable trên mọi provider/JTA environment. Đừng dùng tùy tiện để chữa lỗi.

## 28. readOnly=true không đồng nghĩa thiếu transaction

~~~java
@Transactional(readOnly = true)
public ProductView getProduct(long id) {
    Product p = em.find(Product.class, id);
    return ProductView.from(p);
}
~~~

Một read-only transaction vẫn có thể đang active. Thuộc tính `readOnly` là hint/semantics được Spring/DB/provider xử lý theo cấu hình; **không phải security mechanism** và không bảo đảm mọi writes đều bị cấm theo cách giống nhau.

### Khi một DML trong readOnly method thất bại

Phải xem exact exception:

- Không có transaction do proxy/boundary lỗi?
- Database từ chối write trong read-only transaction?
- Flush mode làm không đồng bộ changes?
- EntityManager chưa joined?

Không kết luận tất cả failures này là TransactionRequiredException.

## 29. @Async và CompletableFuture: mất transaction context

Ví dụ:

~~~java
@Transactional
public void startBatch() {
    CompletableFuture.runAsync(
        () -> repository.bulkDeactivate()
    );
}
~~~

Spring thread-bound transaction context thông thường **không tự truyền sang worker thread**.

~~~text
Request thread: transaction ACTIVE
       |
       +-- submit async task
                |
                v
        Worker thread:
        Không tự kế thừa request transaction
                |
                v
          executeUpdate() -> lỗi
~~~

### Cách làm đúng

Để worker gọi một **Spring-managed transactional service** trong chính worker thread:

~~~java
@Service
public class BatchWriter {

    @Transactional
    public void bulkDeactivate() {
        // JPA DML ở transaction do worker sở hữu.
    }
}
~~~

Không truyền một EntityManager instance từ request thread sang worker vì EntityManager không thread-safe như một shared mutable singleton.

## 30. @Scheduled jobs

Ví dụ:

~~~java
@Scheduled(cron = "0 0 2 * * *")
public void cleanupJob() {
    tokenRepository.deleteExpiredTokens();
}
~~~

Nếu đường gọi không có transaction, `DELETE ... executeUpdate()` có thể báo lỗi.

### Thiết kế rõ

~~~java
@Scheduled(cron = "0 0 2 * * *")
public void cleanupJob() {
    cleanupService.deleteExpired();
}
~~~

Và ở một Spring-managed service:

~~~java
@Transactional
public int deleteExpired() {
    return em.createQuery(
        "DELETE FROM ExpiredToken t " +
        "WHERE t.expiresAt < :now")
      .setParameter("now", Instant.now())
      .executeUpdate();
}
~~~

Scheduled callback không mặc nhiên có transaction chỉ vì nó chạy trong Spring application.

## 31. Event listeners và transaction phase

Một event listener có thể được gọi:

- Trong caller transaction khi đồng bộ.
- Bất đồng bộ trong thread khác.
- Sau commit.
- Khi không có transaction.

Với Spring:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onCreated(OrderCreated event) {
    // ...
}
~~~

**AFTER_COMMIT không phải transaction mới.** Sau khi transaction chính commit, resources có thể còn tồn tại trong giai đoạn cleanup nhưng không có một commit mới cho writes tùy tiện.

Nếu handler thực sự cần ghi DB sau commit, thiết kế một boundary mới qua managed service với `REQUIRES_NEW` khi phù hợp hoặc dùng transactional outbox/consumer.

### Không phát business side effects từ JPA lifecycle callback để tránh lỗi

Một JPA `@PostPersist` hoặc `@PostLoad` không phải một after-commit event chắc chắn. Phát email/payment/network ở đó có thể dẫn đến external side effects ngay cả khi transaction rollback.

## 32. Open EntityManager in View không giữ transaction ghi

Trong một số Spring web applications, OSIV giữ persistence context mở qua lúc view/JSON serialization.

~~~text
Service @Transactional
    |
    +-- commit xong
    |
Controller/View:
    EntityManager vẫn mở qua OSIV
    Nhưng transaction ghi đã kết thúc
~~~

Một call `em.flush()` từ view/serializer sau đó không tự hợp lệ chỉ vì EntityManager vẫn open.

### Đúng lớp trách nhiệm

Đặt writes trong transactional service trước khi tạo response. Dùng DTO và fetch plan phù hợp thay vì để serializer làm phát sinh writes hoặc kéo lazy access ra ngoài use-case boundary.

## 33. Sai transaction manager khi có nhiều datasource

Ứng dụng có:

~~~text
EntityManagerFactory A -> Database A
EntityManagerFactory B -> Database B
TransactionManager A
TransactionManager B
~~~

Method:

~~~java
@Transactional("transactionManagerA")
public void updateDatabaseB() {
    entityManagerB.createQuery(
        "UPDATE Product ...")
      .executeUpdate();
}
~~~

Spring có thể báo **một** transaction đang active, nhưng EntityManager B không tham gia transaction thích hợp của B.

### Dấu hiệu

- Một repository hoạt động còn repository khác báo thiếu transaction.
- Project có nhiều `PlatformTransactionManager`.
- `@PersistenceContext(unitName=...)` hoặc repository configuration trỏ sai EMF.
- Transaction logs có resource binding cho datasource khác.

### Cách sửa

Chọn đúng manager/EMF/datasource; nếu cần coordinate nhiều resources atomically phải dùng JTA/XA hoặc một thiết kế distributed workflow thích hợp. Không rải `@Transactional` không định danh rồi hy vọng framework tự chọn đúng.

## 34. Tự tạo EntityManager trong Spring-managed service

Ví dụ rủi ro:

~~~java
@Transactional
public void update() {
    EntityManager local =
        emf.createEntityManager();
    try {
        local.createQuery(
            "UPDATE Product p SET p.active = false")
          .executeUpdate();
    } finally {
        local.close();
    }
}
~~~

Trong một Spring application dùng transaction-bound EntityManager, object tạo thủ công có thể **không tự tham gia đúng context/transaction** như injected EntityManager.

### Hướng ưu tiên

~~~java
@PersistenceContext
private EntityManager em;
~~~

dùng trong transactional service. Nếu chủ đích quản lý EntityManager thủ công, phải xác định transaction type, context synchronization và lifecycle đúng, không coi `@Transactional` của method là phép auto-join cho mọi EntityManager tự tạo.

## 35. Spring Data @Modifying không tự bảo đảm transaction

Một repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying
    @Query(
        "UPDATE Product p SET p.active = false " +
        "WHERE p.id = :id")
    int deactivate(@Param("id") Long id);
}
~~~

`@Modifying` đánh dấu query thay đổi dữ liệu; **không tự đồng nghĩa mọi đường gọi có transaction thích hợp**.

### Cách thường dùng

~~~java
@Transactional
public void deactivate(long productId) {
    repository.deactivate(productId);
}
~~~

Service có transaction bao quanh use case. Nếu chọn annotation ở repository method thì cần hiểu transactional defaults của Spring Data và khả năng nhiều repository operations phải cùng commit.

### Modifying query có thể làm context stale

Sau bulk UPDATE, managed Product đang có trong persistence context có thể chưa phản ánh DB. `@Modifying` có các tùy chọn flush/clear, nhưng chúng không thay transaction và phải cân nhắc pending changes.

## 36. @Lock trên Spring Data SELECT

Ví dụ:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
Optional<Product> lockById(@Param("id") Long id);
~~~

Mặc dù JPQL là SELECT, operation yêu cầu **pessimistic lock**, nên transaction requirement áp dụng.

### Đúng:

~~~java
@Transactional
public void reserve(long id) {
    Product product =
        repository.lockById(id).orElseThrow();

    // Kiểm tra và sửa trong cùng transaction.
}
~~~

Không được lấy lock trong transaction A rồi thực hiện check/UPDATE trong transaction B nếu mục tiêu là giữ khóa xuyên suốt unit of work.

## 37. Spring diagnostics: isActualTransactionActive()

Spring cung cấp:

~~~java
boolean active =
    TransactionSynchronizationManager
        .isActualTransactionActive();
~~~

Đây là diagnostic hữu ích trong Spring-managed code:

~~~java
log.debug("transaction active={}", active);
~~~

### Đừng nhầm với isSynchronizationActive()

`isSynchronizationActive()` cho biết transaction synchronization management đang active; không bảo đảm luôn có physical transaction. Khi tìm lỗi DML, kiểm tra actual transaction cùng transaction manager/resource binding.

### Không tự tạo flag

Một biến Java `inTransaction=true` hoặc thread-local tùy ý không thay transaction manager; không nên dùng nó quyết định JPA flush có an toàn không.

## 38. Transaction active nhưng EntityManager chưa joined

Nếu:

~~~text
Spring/JTA transaction active = true
JPA EntityManager.isJoinedToTransaction() = false
~~~

thì kiểm tra:

1. EntityManager có phải unsynchronized JTA context?
2. Có gọi `joinTransaction()` trong active JTA transaction không?
3. EntityManager do đúng EMF tạo ra?
4. Transaction manager có đúng persistence resource?
5. Có dùng custom EntityManager ngoài framework?
6. Operation chạy trước hay sau suspension/completion?

### Không sửa bằng cách đóng EM bừa bãi

Nếu persistence context đang giữ pending changes, đóng hoặc clear có thể làm mất state, và cũng không giải quyết transaction manager mismatch. Sửa wiring/boundary trước.

## 39. Rollback-only khác thiếu active transaction

Một transaction có thể còn active nhưng đã được đánh dấu **rollback-only**.

Resource-local:

~~~java
EntityTransaction tx = em.getTransaction();
if (tx.isActive() && tx.getRollbackOnly()) {
    // Không thể commit thành công theo dự kiến.
}
~~~

### Ba trạng thái không giống nhau

~~~text
Không có active transaction
Active transaction, có thể commit
Active transaction, rollback-only
~~~

Nếu một exception trước đó đã đánh dấu transaction rollback-only, `commit()` có thể ném `RollbackException` hoặc Spring `UnexpectedRollbackException`. Đây không phải lời mời thêm một transaction annotation.

### Cách xử lý

Phát hiện root cause, rollback đúng owner và chỉ bắt đầu transaction mới khi use case/retry policy yêu cầu.

## 40. Exception tại commit có nhiều nguyên nhân

Một method:

~~~java
@Transactional
public void changePrice(long id, BigDecimal price) {
    Product p = em.find(Product.class, id);
    p.changePrice(price);
}
~~~

có thể gặp lỗi khi interceptor flush/commit sau khi body đã return:

- `OptimisticLockException`.
- Bean Validation violation.
- UNIQUE/FK/CHECK constraint violation.
- Deadlock/serialization failure.
- Connection/network failure.
- Transaction rollback-only.

### Phân biệt

Nếu đã có transaction đúng và DB từ chối một giá trị invalid, không thể sửa bằng cách gắn thêm `@Transactional` lên repository.

Nếu lỗi là `TransactionRequiredException` ở `executeUpdate()`, xem transaction activation/interception.

Điểm ném exception **không phải căn cứ duy nhất**; phải đọc cause chain và context.

## 41. Phân loại exceptions liên quan

| Exception | Chủ đề cần điều tra |
| --- | --- |
| `jakarta.persistence.TransactionRequiredException` | Missing required transaction/join |
| `jakarta.persistence.RollbackException` | Commit failed/rollback-only |
| `jakarta.persistence.OptimisticLockException` | Version conflict |
| `jakarta.persistence.PessimisticLockException` | Pessimistic locking failure |
| `jakarta.persistence.LockTimeoutException` | Lock wait timeout |
| `jakarta.persistence.EntityNotFoundException` | Reference không resolve được |
| `jakarta.validation.ConstraintViolationException` | Bean Validation constraints |
| `jakarta.persistence.PersistenceException` | Provider persistence failure rộng hơn |
| Spring `UnexpectedRollbackException` | Tx marked rollback-only |
| Spring `DataIntegrityViolationException` | Database integrity-related failure |
| Spring `InvalidDataAccessApiUsageException` | Data access usage; có thể chứa JPA cause |

### Lưu ý trùng tên

`jakarta.validation.ConstraintViolationException` khác `org.hibernate.exception.ConstraintViolationException` liên quan SQL constraints của Hibernate ORM.

Đừng catch theo tên đơn giản rồi trả mọi lỗi thành HTTP 400 giống nhau.

## 42. Không retry lỗi thiếu transaction một cách mù quáng

Sai:

~~~text
executeUpdate() thiếu transaction
retry lần 1
retry lần 2
retry lần 3
=> vẫn thiếu transaction
~~~

Đây thường là **lỗi lập trình/cấu hình**. Retry không tạo transaction và không sửa proxy/wiring.

### Khi nào retry có ích?

Một số transient failures như deadlock victim hoặc serialization error có thể retry, nhưng cần:

- Transaction **mới**.
- Đọc lại state/validate lại điều kiện.
- Idempotency khi requests lặp.
- Giới hạn số lần và backoff.
- Không lặp external side effects ngoài ý muốn.

### Tránh retry trong rollback-only context

Nếu transaction đã thất bại, không tiếp tục gọi `flush()` hoặc `commit()` trên cùng context mà không xử lý rollback/lifecycle thích hợp.

## 43. Anti-pattern: bắt TransactionRequiredException rồi begin tại chỗ

~~~java
try {
    em.flush();
} catch (TransactionRequiredException ex) {
    em.getTransaction().begin();
    em.flush();
}
~~~

Vì sao nguy hiểm?

- Có thể là JTA-managed EM nên `getTransaction()` không hợp lệ.
- Không bao trùm các bước đã chạy trước đó trong cùng use case.
- Có thể tạo một transaction nhỏ commit tách biệt.
- Persistence context/operation có thể cần rollback/recovery sạch.
- Thiếu revalidation và lock của toàn quy trình.

**Sửa boundary từ đầu**, không bắt lỗi rồi tái cấu trúc transaction ngay tại dòng fail.

## 44. Transaction quá dài cũng là một lỗi thiết kế

Nếu service:

~~~text
BEGIN
  Lock Inventory
  Gọi payment HTTP trong 30 giây
  Update Order
COMMIT
~~~

thì active transaction được bảo đảm, nhưng có thể giữ locks và database connections quá lâu.

### Hướng kiến trúc

Phân tách các state transitions:

~~~text
TX1:
  Create PaymentAttempt PENDING
  Commit

External API với idempotency key

TX2:
  Confirm/Reject Attempt
  Commit
~~~

Kết hợp transactional outbox/saga khi cần đồng bộ các systems. Phải thiết kế concurrency/compensation rõ; không tách transaction tùy tiện mà mất tính nhất quán.

### Bài học

Transaction phải **đủ rộng cho atomicity**, nhưng không nên bao gồm user think time hoặc network calls dài nếu có thể thiết kế trạng thái an toàn hơn.

## 45. Test RESOURCE_LOCAL: flush khi thiếu transaction

JUnit integration test:

~~~java
@Test
void flushNeedsTransaction() {
    EntityManager em = emf.createEntityManager();
    try {
        assertThrows(
            TransactionRequiredException.class,
            em::flush
        );
    } finally {
        em.close();
    }
}
~~~

Điều kiện: test dùng EntityManager resource-local, không có active transaction. Với Spring/provider wrappers, exception ngoài cùng có thể khác; khi đó assert cause chain phù hợp.

### Tại sao không dùng Mockito?

Mock EntityManager không chạy JPA provider transaction checks, nên một Mockito unit test không chứng minh lỗi/sự tích hợp transaction thực.

## 46. Test executeUpdate ngoài transaction

~~~java
@Test
void bulkUpdateNeedsTransaction() {
    EntityManager em = emf.createEntityManager();
    try {
        assertThrows(
            TransactionRequiredException.class,
            () -> em.createQuery(
                    "UPDATE Product p SET p.active = false")
                .executeUpdate()
        );
    } finally {
        em.close();
    }
}
~~~

Giả định Product có persistent `active` field và persistence unit thực đã bootstrapped.

### Tại sao không cần row matching?

Transaction requirement là điều kiện của DML execution; SQL có thể ảnh hưởng 0 rows nhưng vẫn là UPDATE.

## 47. Test sửa đúng: DML trong transaction

~~~java
@Test
void updateInsideTransaction() {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();
    try {
        tx.begin();

        int changed = em.createQuery(
                "UPDATE Product p SET p.active = false")
            .executeUpdate();

        assertTrue(changed >= 0);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Một test nghiệp vụ hoàn chỉnh còn nên:

1. Persist fixture và commit trong transaction riêng.
2. Chạy UPDATE với transaction mới.
3. Dùng EntityManager mới đọc lại database state sau commit.
4. Kiểm tra data đúng và không bị stale L1 che khuất.

## 48. Test pessimistic lock thiếu transaction

~~~java
@Test
void pessimisticLockNeedsTransaction() {
    EntityManager em = emf.createEntityManager();
    try {
        assertThrows(
            TransactionRequiredException.class,
            () -> em.find(
                Product.class,
                existingProductId,
                LockModeType.PESSIMISTIC_WRITE
            )
        );
    } finally {
        em.close();
    }
}
~~~

Nên có Product fixture đã commit để tách lỗi thiếu transaction khỏi trường hợp entity không tồn tại.

### Lock test khác concurrency test

Nếu muốn kiểm tra lock wait/deadlock, phải dùng **hai giao dịch/EntityManager độc lập** và DBMS thật phù hợp. Test này chỉ xác nhận operation cần transaction.

## 49. Test Spring proxy/self-invocation

Hai trường hợp:

~~~text
Case A:
  External caller -> Spring proxy -> @Transactional method

Case B:
  External caller -> non-transactional method
                  -> this.@Transactional method
~~~

Với Spring proxy-based transaction management:

- Case A có thể tạo transaction.
- Case B không tự intercept lời gọi nội bộ.

### Test đúng

- Dùng Spring context thật và inject bean qua container.
- Quan sát `TransactionSynchronizationManager.isActualTransactionActive()` khi cần.
- Chạy DML trên test fixture độc lập.
- Kiểm tra database committed state và exception cause.

Không dùng `new Service()` hoặc Mockito thuần rồi kết luận transaction interception hoạt động.

## 50. Test async thread boundary

Thiết kế:

~~~text
Main thread:
  @Transactional
  Submit work to executor

Worker thread:
  Check actualTransactionActive
  Execute JPA DML
~~~

Worker không tự kế thừa transaction của main thread. Sửa bằng một transaction owner chạy trong worker thread và kiểm tra database state sau commit.

### Không chia sẻ EntityManager

Mỗi worker cần persistence context theo lifecycle transaction manager, không truyền một managed EntityManager tùy ý qua thread boundary.

## 51. Test JTA unsynchronized context

Trong JTA integration environment hỗ trợ `UNSYNCHRONIZED`:

1. Tạo unsynchronized persistence context.
2. Bắt đầu JTA transaction.
3. Quan sát `isJoinedToTransaction()`.
4. Thử operation cần synchronization và ghi nhận provider behavior.
5. Gọi `joinTransaction()`.
6. Xác nhận joined state.
7. Flush/commit trong transaction phù hợp.

Mục tiêu là chứng minh:

~~~text
Active JTA transaction != mọi EM đều automatically joined
~~~

Đừng dùng resource-local mock để đại diện toàn bộ JTA synchronization semantics.

## 52. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `flush()` báo no transaction | Chưa begin/transaction interceptor không chạy | Mở tx đúng owner |
| `executeUpdate()` báo transaction required | DML ngoài tx | Service tx/begin |
| `createQuery()` chạy, `executeUpdate()` fail | Thực thi DML có requirement khác | Kiểm tra tx tại execution |
| `find()` chạy, `flush()` fail | Read thành công không chứng minh tx | Đặt tx boundary |
| `find(... PESSIMISTIC_WRITE)` fail | Lock yêu cầu tx | Mở tx trước find |
| @Transactional vẫn fail | Self-invocation hoặc bean không managed | Proxy/DI |
| Private @Transactional không tác dụng | Không phải proxy-intercepted entrypoint | Public service boundary |
| @Async DML fail | Thread không kế thừa tx | Tx trong worker |
| @Scheduled cleanup fail | Job thiếu tx | Managed cleanup service |
| AFTER_COMMIT listener write fail | TX chính hoàn tất | Tx riêng/outbox |
| OSIV EntityManager mở nhưng flush fail | EM mở khác active tx | Ghi trong service |
| Spring báo tx active, JPA vẫn fail | Sai EMF/manager/context chưa joined | Wiring/JTA join |
| UNSYNCHRONIZED flush fail | Chưa join | `joinTransaction()` trong active JTA |
| @Modifying UPDATE fail | @Modifying không bảo đảm tx | @Transactional tại service |
| Native SQL UPDATE fail | JPA executeUpdate vẫn yêu cầu tx | Correct tx owner |
| Transaction rollback-only | Lỗi trước đó | Rollback/root cause |
| Commit bị unique/FK exception | DB constraint, không phải thiếu tx | Fix data/business |
| Version conflict | Optimistic locking | Retry đúng policy |
| Lock timeout | Contention | Lock strategy/timeout |
| REQUIRES_NEW gây dữ liệu lệch | Transaction commits độc lập | Thiết kế lại atomicity |
| @Transactional managerA nhưng EMF B | Sai resource transaction | Chọn manager phù hợp |

## 53. Quy trình chẩn đoán có thể áp dụng ngay

1. **Ghi exception class** và cause chain.
2. **Xác định chính xác lời gọi JPA** gây lỗi.
3. **Kiểm tra contract** operation có yêu cầu transaction không.
4. **Xác định persistence unit và EntityManagerFactory**.
5. **Xác định transaction owner**: resource-local, JTA, Spring.
6. **Kiểm tra active status** qua API phù hợp.
7. **Kiểm tra đường gọi Spring**: self-invocation, new bean, private method, async, scheduled job.
8. **Kiểm tra propagation**: REQUIRED, MANDATORY, SUPPORTS, NOT_SUPPORTED, REQUIRES_NEW.
9. **Kiểm tra EMF/transaction manager mapping** nếu có nhiều datasources.
10. **Kiểm tra JTA joined/synchronization state** khi liên quan.
11. **Kiểm tra rollback-only** nếu exception xuất hiện ở commit.
12. **Sửa boundary từ use-case layer**, không chắp vá begin() tại dòng lỗi.
13. **Viết integration test** cho cả đường thiếu tx và đường đúng tx.
14. **Kiểm tra business correctness** sau khi lỗi hết: optimistic lock, FK, uniqueness, atomicity và side effects.

### Checklist quyết định nhanh

~~~text
Là TransactionRequiredException?
    |
    +-- Không: phân loại optimistic/lock/DB/rollback lỗi khác.
    |
    +-- Có:
         Operation là flush, DML hay lock?
          |
          +-- Có -> transaction active?
                       |
                       +-- Không -> fix tx owner/proxy/thread/propagation
                       |
                       +-- Có -> đúng EMF/manager/join state?
                                     |
                                     +-- Không -> fix binding/synchronization
                                     |
                                     +-- Có -> inspect exact provider cause
~~~

Không bỏ qua root cause chỉ vì lỗi bộc lộ ở service rất xa repository.

## 54. Những anti-pattern cần tránh

- **Auto begin/commit trong mọi repository helper:** phá atomicity của service lớn.
- **Bắt TransactionRequiredException rồi retry nguyên operation trên cùng context:** lỗi cấu trúc không tự biến mất.
- **Chuyển sang native SQL/JDBC để tránh JPA transaction:** có thể tạo commits độc lập.
- **Đặt @Transactional lên private method hoặc chỉ gọi nội bộ bằng this:** proxy không intercept như mong đợi.
- **Dùng SUPPORTS cho một method bắt buộc bulk DML:** có thể chạy không transaction.
- **Dùng REQUIRES_NEW tràn lan:** các parts của một unit of work có thể commit riêng.
- **Truyền EntityManager sang @Async worker:** vi phạm lifecycle/thread safety.
- **Coi OSIV mở EntityManager là transaction ghi đang active:** sai ranh giới.
- **Coi flush là commit:** không đúng.
- **Tiếp tục trên transaction rollback-only:** commit sau vẫn có thể thất bại.
- **Coi mọi exception tại commit là thiếu transaction:** bỏ sót constraint/lock/version errors.
- **Dùng @Transactional(readOnly=true) làm hàng rào bảo mật writes:** không thay service authorization/DB constraints.
- **Giữ transaction mở qua HTTP calls dài không cần thiết:** làm tăng lock contention và connection usage.
- **Nghĩ giải quyết thiếu transaction tức giải quyết concurrency:** còn @Version, locks, conditional updates và DB invariants.

## 55. Bài tập thực hành

### Bài 1 — Nhận diện

JPA exception chuẩn nào thường xuất hiện khi một method đòi transaction nhưng không có transaction phù hợp?

**Gợi ý:** `TransactionRequiredException`.

### Bài 2 — Flush

Tại sao `flush()` không giống một thao tác validate object thuần túy?

**Gợi ý:** nó đồng bộ pending persistent state xuống database trong transaction.

### Bài 3 — Query

`createQuery("UPDATE ...")` thành công nhưng `executeUpdate()` lỗi. Vì sao?

**Gợi ý:** tạo query object khác với thực thi DML.

### Bài 4 — Native SQL

Native UPDATE qua `createNativeQuery(...).executeUpdate()` có còn cần transaction không?

**Gợi ý:** có.

### Bài 5 — Read

`em.find()` bình thường chạy thành công có chứng minh đang có transaction không?

**Gợi ý:** không.

### Bài 6 — Lock

Tại sao `PESSIMISTIC_WRITE` đòi transaction?

**Gợi ý:** khóa phải được giữ trong một transaction khi kiểm tra/sửa state.

### Bài 7 — Lock timeout

Transaction đang active nhưng DB không cho lấy lock do timeout. Đây có phải thiếu transaction?

**Gợi ý:** không; phân biệt LockTimeoutException/PessimisticLockException.

### Bài 8 — RESOURCE_LOCAL

Tên ba phương thức transaction cơ bản là gì?

**Gợi ý:** `begin()`, `commit()`, `rollback()`.

### Bài 9 — JTA

Có nên gọi `em.getTransaction().begin()` trên JTA-managed EntityManager?

**Gợi ý:** không.

### Bài 10 — Transaction owner

Một use case gọi ba repositories cần cùng rollback. Nên đặt transaction ở đâu?

**Gợi ý:** application service boundary.

### Bài 11 — Persist

Một extended persistence context cho phép persist khi không active transaction. Có đồng nghĩa INSERT đã commit không?

**Gợi ý:** không.

### Bài 12 — Join

Transaction JTA active, context UNSYNCHRONIZED chưa joined. Gọi method nào để join?

**Gợi ý:** `em.joinTransaction()`.

### Bài 13 — Join vs begin

`joinTransaction()` có khởi tạo transaction mới không?

**Gợi ý:** không.

### Bài 14 — Transaction active

Trong resource-local, API nào kiểm tra transaction active?

**Gợi ý:** `em.getTransaction().isActive()`.

### Bài 15 — Spring diagnostics

API Spring nào kiểm tra actual transaction active?

**Gợi ý:** `TransactionSynchronizationManager.isActualTransactionActive()`.

### Bài 16 — Proxy

Method `@Transactional` được gọi qua `this.method()` trong cùng bean. Vì sao có thể không mở transaction?

**Gợi ý:** Spring proxy-based self-invocation.

### Bài 17 — Private

Một private method có @Transactional trong Spring proxy mode có phải entrypoint đáng tin không?

**Gợi ý:** không.

### Bài 18 — Container

Tại sao tạo service bằng `new` có thể khiến @Transactional vô hiệu?

**Gợi ý:** bypass managed bean/proxy.

### Bài 19 — REQUIRED

Propagation.REQUIRED làm gì khi chưa có transaction?

**Gợi ý:** tạo transaction.

### Bài 20 — MANDATORY

Propagation.MANDATORY có tạo transaction khi caller không có không?

**Gợi ý:** không, từ chối invocation.

### Bài 21 — SUPPORTS

Một method luôn UPDATE nhưng dùng SUPPORTS. Khi nào sẽ lỗi?

**Gợi ý:** khi caller không có transaction.

### Bài 22 — REQUIRES_NEW

Inventory transaction REQUIRES_NEW commit rồi Order transaction rollback. Vấn đề gì?

**Gợi ý:** mất atomicity của toàn use case.

### Bài 23 — readOnly

`readOnly=true` có nghĩa “không có active transaction” không?

**Gợi ý:** không.

### Bài 24 — Async

Một worker thread có tự kế thừa transaction của request thread không?

**Gợi ý:** không nên giả định; tạo transaction ở worker.

### Bài 25 — EntityManager thread safety

Có nên chia sẻ một EntityManager giữa request và async worker không?

**Gợi ý:** không.

### Bài 26 — @Scheduled

Một scheduled cleanup job gọi bulk DELETE nhưng báo TransactionRequiredException. Hướng sửa cấu trúc?

**Gợi ý:** gọi managed transactional cleanup service.

### Bài 27 — OSIV

EntityManager mở trong JSON serialization có nghĩa transaction vẫn active không?

**Gợi ý:** không.

### Bài 28 — Multiple EMF

Transaction manager A active nhưng JPA entity manager của DB B fail. Kiểm tra gì?

**Gợi ý:** EMF/manager/resource binding.

### Bài 29 — @Modifying

Spring Data @Modifying có tự bảo đảm transaction không?

**Gợi ý:** không.

### Bài 30 — Rollback-only

Transaction rollback-only có giống “không có active transaction” không?

**Gợi ý:** không; transaction tồn tại nhưng không thể commit thành công theo dự kiến.

### Bài 31 — Optimistic locking

Version conflict có được chữa bằng việc thêm @Transactional lên mọi method không?

**Gợi ý:** không.

### Bài 32 — Retry

Thiếu transaction là lỗi cấu hình, retry 10 lần có giúp không?

**Gợi ý:** không; sửa boundary/proxy/manager.

### Bài 33 — Test

Một mock EntityManager trả thành công cho flush có chứng minh transaction integration thật đúng không?

**Gợi ý:** không; cần integration test với JPA provider.

### Bài 34 — Flush vs commit

`em.flush()` thành công, rồi transaction rollback. Rows đã được commit chưa?

**Gợi ý:** chưa.

### Bài 35 — Tổng hợp

Một @Async worker dùng custom EntityManager gọi `executeUpdate()` và nhận `TransactionRequiredException`. Liệt kê tối thiểu năm bước xác định nguyên nhân.

**Gợi ý:** operation, exact exception/cause, thread boundary, tx owner, manager/EMF, active/joined state, integration test.

## 56. Bảng ghi nhớ nhanh

| Chủ đề | Cần nhớ |
| --- | --- |
| JPA exception chuẩn khi thiếu tx | `TransactionRequiredException` |
| Có EntityManager tức có transaction? | Không |
| `find()` không lock | Có thể đọc ngoài transaction tùy context |
| JPQL SELECT | Không luôn bắt buộc transaction |
| `flush()` | Cần transaction phù hợp |
| DML `executeUpdate()` | Cần transaction |
| Native DML qua JPA | Vẫn cần transaction |
| Lock khác NONE | Cần transaction trong operation phù hợp |
| Flush đã commit? | Không |
| RESOURCE_LOCAL | `EntityTransaction.begin/commit/rollback` |
| JTA | Container/JTA manager sở hữu transaction |
| `em.getTransaction().begin()` trên JTA | Không phù hợp |
| Spring | @Transactional ở service entrypoint |
| Self-invocation | Bypass proxy-based interception |
| new service | Không có managed proxy |
| REQUIRED | Tạo transaction nếu thiếu |
| MANDATORY | Cần caller đã có transaction |
| SUPPORTS | Có thể chạy không transaction |
| NOT_SUPPORTED | Chạy non-transactional |
| REQUIRES_NEW | Transaction độc lập, chú ý atomicity |
| readOnly | Không đồng nghĩa thiếu transaction |
| Async | Không tự kế thừa transaction thread cũ |
| OSIV | EntityManager mở không chứng minh active tx |
| Multiple EMFs | Cần đúng transaction manager |
| JTA UNSYNCHRONIZED | Có thể cần `joinTransaction()` |
| isJoinedToTransaction | Kiểm tra EM participation |
| Rollback-only | Transaction còn nhưng không commit thành công |
| Retry lỗi thiếu transaction | Không; sửa cấu trúc |
| @Modifying | Không tự bảo đảm transaction |
| Optimistic/lock conflicts | Loại lỗi khác thiếu tx |
| DB constraints | Không được chữa bằng thêm @Transactional |
| Integration tests | JPA provider + transaction manager thật |
| Lời khuyên chính | Đúng owner, boundary, manager, thread và context |

## Kết luận

**`TransactionRequiredException` là tín hiệu cho biết một thao tác JPA cần transaction nhưng điều kiện transaction chưa được đáp ứng.** Những điểm thường phát lỗi là `flush()`, `executeUpdate()` cho UPDATE/DELETE và các operations yêu cầu lock. Một `find()` hoặc SELECT thành công không chứng minh có active transaction, cũng như một EntityManager đang mở không có nghĩa giao dịch ghi vẫn còn.

Để sửa đúng, hãy xác định **transaction owner**: với RESOURCE_LOCAL, ứng dụng sử dụng `EntityTransaction`; với JTA/Spring, container hoặc transaction manager sở hữu begin/commit/rollback. Nếu annotation `@Transactional` tồn tại nhưng vẫn lỗi, phải kiểm tra **Spring proxy/self-invocation, private methods, async/scheduled thread, propagation, multiple EntityManagerFactory và synchronization/join state**. Trong JTA, transaction có thể active nhưng persistence context `UNSYNCHRONIZED` chưa tham gia; `joinTransaction()` không tự tạo giao dịch mới.

**Không nhầm lỗi thiếu transaction với optimistic conflict, lock timeout, rollback-only hoặc database constraint violation.** Những lỗi ấy cần hướng xử lý khác. Đừng thêm `begin()` ngay trong catch, retry vô hạn, chuyển sang JDBC ngoài transaction hoặc dùng `REQUIRES_NEW` tùy tiện vì có thể làm vỡ atomicity.

Cách tổ chức bền vững là **mở transaction tại application service boundary**, cho các repository và EntityManager tham gia đúng tài nguyên/giao dịch, rollback đúng khi có lỗi và dùng integration tests xác minh cả đường thiếu transaction lẫn đường xử lý hợp lệ. Sau khi hết TransactionRequiredException, hãy tiếp tục kiểm tra concurrency, authorization, optimistic locking và database constraints để bảo đảm **nghiệp vụ đúng**, không chỉ **SQL có thể chạy**.
