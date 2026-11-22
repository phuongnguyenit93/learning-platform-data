# Không tái sử dụng Session đã lỗi để tiếp tục xử lý ngoài kiểm soát

Một trong những quy tắc an toàn nhất khi làm việc với giao dịch Hibernate là: **khi một thao tác Hibernate/JDBC trong unit of work gặp lỗi khiến trạng thái persistence hoặc transaction không còn đáng tin cậy, hãy rollback transaction và bỏ `Session` hiện tại**. Nếu cần thực hiện lại công việc, hãy bắt đầu một unit of work mới với `Session`/`EntityManager` và transaction mới.

Quy tắc này liên quan trực tiếp đến kiến trúc Hibernate: `Session` giữ persistence context, entity snapshots, action queue, trạng thái collection và các tài nguyên JDBC. Vì vậy, một lỗi `INSERT`/`UPDATE`/`DELETE` không chỉ là một lời gọi Java thất bại. Một số thay đổi có thể đã đi vào bộ nhớ ORM, một số lệnh SQL có thể đã được gửi tới DB, còn database transaction có thể đã bị đánh dấu rollback-only hoặc bị DBMS từ chối mọi lệnh tiếp theo.

Bài học này trình bày cách nhận diện, xử lý và thiết kế lại công việc sau lỗi trong **Hibernate ORM 6.x** và Jakarta Persistence, bao gồm ví dụ dùng Hibernate native API, JPA `EntityManager`, Spring `@Transactional`, retry có kiểm soát và các tình huống đặc biệt khi flush/commit. Không phải **mọi** exception Java đều làm hỏng `Session`: cần phân biệt exception nghiệp vụ/validation phát sinh trước ORM với exception khi Hibernate đang đồng bộ trạng thái hoặc thực thi SQL.

## 1. Session, persistence context và transaction là ba khái niệm liên quan nhưng không đồng nhất

| Thành phần | Được dùng để làm gì? | Điều cần biết sau lỗi |
| --- | --- | --- |
| `SessionFactory` | Chứa metadata, cấu hình dịch vụ và tạo `Session`; được thiết kế để chia sẻ giữa các luồng | Một `Session` lỗi **không có nghĩa phải đóng toàn bộ `SessionFactory`** |
| `Session` | API thao tác ORM; chủ sở hữu một persistence context trong các mô hình thông thường | Sau lỗi ORM/JDBC nghiêm trọng, đóng/bỏ session hiện tại |
| Persistence context | Giữ entity managed, snapshots, collection states, identity map | Không tự trở về trạng thái trước thao tác khi transaction rollback |
| Transaction | Xác định phạm vi commit/rollback của các thay đổi dữ liệu | Nếu đã thất bại/rollback-only, không tiếp tục như thể còn transaction hợp lệ |
| JDBC connection | Kết nối do Hibernate/pool quản lý để thực thi SQL | Lỗi có thể làm transaction trên connection không dùng tiếp được; pool/driver quản lý việc thu hồi, kiểm tra kết nối |
| Entity Java object | Đối tượng ứng dụng có thể vẫn còn được tham chiếu sau khi session đóng | Field đã sửa trong Java không tự “quay ngược” theo rollback database |

Một `Session` được mở không có nghĩa transaction đã tự bắt đầu. Trong ứng dụng sử dụng transaction manager, session có thể được gắn vào transaction và đóng theo phạm vi framework; trong native Hibernate, người viết mã thường cần chủ động mở, commit/rollback và đóng.

~~~mermaid
flowchart TD
    A[SessionFactory dùng chung] --> B[Mở Session cho unit of work]
    B --> C[Bắt đầu transaction]
    C --> D[Load/persist/update entity]
    D --> E[Flush hoặc commit]
    E --> F{Có lỗi ORM/JDBC?}
    F -- Không --> G[Commit thành công]
    G --> H[Đóng Session]
    F -- Có --> I[Rollback nếu còn khả năng]
    I --> J[Đóng/bỏ Session và persistence context]
    J --> K{Có được retry?}
    K -- Có --> L[Unit of work mới: Session + transaction mới]
    K -- Không --> M[Trả lỗi phù hợp/đưa vào xử lý nghiệp vụ]
~~~

**Ranh giới an toàn nằm ở unit of work**: một thao tác nghiệp vụ phải có cơ chế kết thúc transaction rõ ràng. Tiếp tục dùng session lỗi để “thử thêm vài lệnh SQL” có thể khiến trạng thái in-memory và dữ liệu database ngày càng khó đối chiếu.

## 2. Vì sao rollback không đủ để Session trở lại như ban đầu?

### 2.1. Hibernate đã làm nhiều việc trước khi database trả lỗi

Giả sử một transaction cần:

1. Tải đơn hàng `Order#42`.
2. Đổi trạng thái đơn hàng thành `CONFIRMED`.
3. Tạo một `Shipment` mới.
4. Ghi thêm `AuditEvent`.
5. Commit tất cả hoặc rollback tất cả.

Trước khi commit, Hibernate có thể đã:

- Đánh dấu `Order` là dirty.
- Tạo entity entry cho `Shipment`, quản lý ID và trạng thái transient/managed.
- Ghi nhận thay đổi collection và cascade.
- Xếp các entity insert/update/delete actions theo metadata.
- Thực thi một phần SQL khi flush, khi cần IDENTITY-generated identifier hoặc trước một số truy vấn.

Nếu một `INSERT Shipment` vi phạm constraint, DB có thể đã nhận `UPDATE Order` hoặc một số statement trước đó trong **cùng transaction**. Rollback của DB nhằm hoàn tác những thay đổi dữ liệu thuộc transaction, nhưng **các object Java vẫn giữ giá trị đã gán**:

~~~text
                         Trước thao tác
DB: Order#42 = NEW        Java Order.status = NEW

                         Trong transaction
Java Order.status = CONFIRMED
Hibernate chuẩn bị UPDATE/INSERT
DB báo lỗi FK khi ghi Shipment

                         Sau rollback DB
DB: Order#42 = NEW        Java Order.status vẫn = CONFIRMED
                         Persistence Context không tự là bản sao của DB
~~~

Hibernate không cam kết rằng rollback sẽ khôi phục mọi trường Java, collection wrapper, generated identifier hay action queue về trạng thái trước khi bắt đầu giao dịch. Vì thế **không nên tái sử dụng persistence context đã đi qua lỗi** như một context sạch.

### 2.2. Sự bất nhất có thể tồn tại ngay cả khi một số SQL chưa chạy

Một lỗi mapping, transient association, listener, flush callback hoặc optimistic lock có thể xảy ra **trước khi gửi SQL cuối cùng**. Nó vẫn có thể làm unit of work không thể tiếp tục an toàn: Hibernate đã có state transition, pending actions hoặc entity associations được tính toán theo những giả định đã thất bại.

Vì vậy không áp dụng quy tắc “nếu DB chưa commit thì chỉ cần sửa giá trị Java rồi flush lại”. Muốn retry toàn bộ nghiệp vụ, hãy **bắt đầu transaction mới, context mới, lấy trạng thái dữ liệu mới** rồi áp dụng lại yêu cầu.

### 2.3. DBMS có thể buộc transaction bị hủy sau một câu SQL lỗi

Ví dụ trên PostgreSQL, nhiều SQL errors khiến transaction hiện tại ở trạng thái aborted; các statement tiếp theo nhận thông báo transaction đang bị hủy cho tới khi rollback. DBMS khác có thể có quy tắc khác tùy loại lỗi và cấu hình. Hibernate còn có thể đánh dấu transaction rollback-only theo exception semantics.

Ngay cả khi JDBC connection vật lý còn hợp lệ, điều đó **không chứng minh Hibernate Session/persistence context có thể dùng tiếp** sau lỗi ORM.

## 3. Tình huống minh họa: lỗi khóa ngoại chỉ xuất hiện khi flush

Giả sử bảng có ràng buộc:

~~~sql
create table customers (
    id bigint primary key,
    display_name varchar(100) not null
);

create table purchase_orders (
    id bigint generated by default as identity primary key,
    customer_id bigint not null,
    total_amount numeric(19, 2) not null,
    constraint fk_order_customer
      foreign key (customer_id) references customers(id)
);
~~~

Mapping JPA:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {}

    public PurchaseOrder(Customer customer, BigDecimal totalAmount) {
        this.customer = customer;
        this.totalAmount = totalAmount;
    }
}

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;
    private String displayName;
    protected Customer() {}
}
~~~

Giả sử không có `Customer#999`:

~~~java
Customer ref = entityManager.getReference(Customer.class, 999L);
PurchaseOrder order =
        new PurchaseOrder(ref, new BigDecimal("250.00"));

entityManager.persist(order);

// SQL có thể được thực thi ở persist, flush hoặc commit,
// tùy identifier generation và trạng thái Hibernate.
entityManager.flush();
~~~

`getReference` có thể trả một proxy mà **không kiểm tra hàng tồn tại ngay**, nên thao tác Java ban đầu có vẻ hợp lệ. Nếu DB thực thi FK, `INSERT` với `customer_id=999` sẽ bị DB từ chối.

Với `GenerationType.IDENTITY`, Hibernate có thể phải gửi `INSERT` sớm để nhận ID; vì vậy **không nên cam kết lỗi chỉ phát sinh chính xác ở dòng `flush()`**. Mục đích ví dụ là chỉ ra **lỗi có thể xuất hiện muộn hơn dòng `persist()`**.

Lỗi JDBC có thể được Hibernate chuyển thành `org.hibernate.exception.ConstraintViolationException` hoặc được JPA/framework bọc trong exception khác. Đây là lỗi integrity của transaction, không phải lời mời tiếp tục sử dụng cùng `EntityManager`.

## 4. Anti-pattern: bắt lỗi rồi tiếp tục xử lý bằng cùng Session

Ví dụ sai:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        session.persist(badOrder);
        session.flush();
    } catch (RuntimeException ex) {
        log.warn("Cannot save first order; skip it", ex);
        // SAI: không rollback, cũng không bỏ session.
    }

    session.persist(goodOrder);
    tx.commit(); // Có thể lỗi tiếp hoặc đồng bộ state sai.
}
~~~

Vấn đề không nằm ở việc log warning. Lỗi là **sau khi flush đã thất bại, chương trình vẫn dùng session/transaction cũ để xử lý một phần việc khác**.

Một số rủi ro:

- Transaction có thể đã ở trạng thái rollback-only/aborted.
- Persistence context vẫn giữ `badOrder` và các thay đổi từ trước.
- Action queue có thể chứa hoặc đã xử lý một phần công việc.
- `goodOrder` mới bị trộn với một unit of work đã thất bại.
- Commit có thể thất bại muộn; log “skip it” tạo cảm giác sai rằng thao tác lỗi đã được bỏ qua.
- Nếu error handling trả về thành công quá sớm, caller có thể nghĩ dữ liệu đã được ghi.

Đặc biệt nguy hiểm trong batch job: “bỏ qua một dòng lỗi” **không có nghĩa** giữ nguyên transaction/session đã gặp lỗi và tiếp tục chèn những dòng còn lại. Cách xử lý đúng là **rollback và khởi tạo scope mới theo chính sách batch**.

## 5. Xử lý đúng với Hibernate native API

### 5.1. Session per unit of work

Ví dụ quản lý tài nguyên tường minh:

~~~java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public final class OrderWriter {
    private final SessionFactory sessionFactory;

    public OrderWriter(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public void createOrder(PurchaseOrder order) {
        try (Session session = sessionFactory.openSession()) {
            Transaction tx = session.beginTransaction();

            try {
                session.persist(order);
                tx.commit();
            } catch (RuntimeException | Error failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        } // Session luôn được đóng khi scope kết thúc.
    }
}
~~~

Ở đây:

1. `SessionFactory` dùng chung và có vòng đời dài.
2. Mỗi lời gọi mở `Session` mới, nên có persistence context riêng.
3. Transaction được bắt đầu cho một unit of work.
4. Nếu persist/flush/commit gây lỗi, mã thử rollback khi transaction còn active.
5. Session được đóng bởi `try-with-resources` dù rollback thành công hay thất bại.
6. Exception gốc tiếp tục được truyền lên lớp quyết định phản hồi/retry.

Nếu `rollback()` cũng ném exception, giữ exception gốc và gắn rollback failure qua `addSuppressed` giúp điều tra cả hai sự cố. Đây là mẫu minh họa; ứng dụng production có thể dùng helper/framework để tránh viết lặp boilerplate.

**Không bao giờ cố “reset” bằng `session.clear()` rồi reuse session trong nhánh catch của lỗi flush/SQL nghiêm trọng.** `clear()` chỉ detach managed entities, không bảo đảm khôi phục transaction/JDBC state hay action queue thành một unit of work hợp lệ.

### 5.2. Transaction có thể lỗi ngay tại commit

~~~java
session.persist(order);
// Một số thao tác chỉ được gửi khi flush trong commit.
tx.commit(); // Có thể là nơi ConstraintViolationException xuất hiện.
~~~

Vì vậy cần bao trùm **cả commit** trong khối xử lý lỗi. Nếu chỉ bao quanh `persist()` bằng try/catch, chương trình có thể bỏ qua đúng vị trí xảy ra lỗi thật.

Sau commit thất bại, transaction có thể đã kết thúc hoặc bị marked rollback-only; `tx.isActive()` không phải câu trả lời cho việc có thể tiếp tục session. Dù `isActive()` trả gì, hãy **đóng session và báo lỗi**.

### 5.3. Không tái sử dụng entity object đã thất bại một cách mù quáng

Giả sử `PurchaseOrder` đã được `persist` và được gán ID nhưng commit thất bại. Object có thể vẫn mang ID do Hibernate/DB sinh và field đã sửa, dù hàng DB tương ứng không commit.

Tái sử dụng nguyên object ấy với `persist()` ở transaction khác có thể gây hiểu nhầm transient/detached hoặc conflict identifier. Tốt hơn là **tạo entity mới từ command/DTO nghiệp vụ**, hoặc tải trạng thái hiện tại trong session mới nếu update entity đã tồn tại.

## 6. JPA EntityManager: kết thúc transaction và context đúng cách

Trong JPA resource-local transaction:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public void createOrder(
        EntityManagerFactory emf,
        PurchaseOrder order
) {
    EntityManager em = emf.createEntityManager();

    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        try {
            em.persist(order);
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
    } finally {
        em.close();
    }
}
~~~

`EntityManagerFactory` tương tự `SessionFactory` ở vai trò factory có thể chia sẻ; `EntityManager` là đối tượng gắn với persistence context và **không thread-safe**.

Ví dụ áp dụng cho **resource-local EntityManager**. Trong môi trường JTA/container-managed, ứng dụng thường không được chủ động gọi `em.getTransaction().begin()` hoặc `commit()`; transaction được quản lý qua container và rollback phải theo hợp đồng transaction manager.

### 6.1. EntityManager và transaction sau rollback

JPA có quy tắc vòng đời riêng đối với entity sau transaction rollback. Những entity trước đây managed có thể bị tách khỏi persistence context hoặc mang trạng thái Java không phản ánh database sau rollback. Với một `EntityManager` còn mở theo mô hình application-managed, **đừng coi nó đã được phục hồi thành sạch** sau khi Hibernate/JDBC có lỗi.

Chiến lược đơn giản, an toàn và dễ duy trì cho ORM failure là **đóng `EntityManager` bị ảnh hưởng và tạo mới từ `EntityManagerFactory` cho thao tác sau**, thay vì giữ lại để thử xử lý tiếp. Quy tắc này đặc biệt hữu ích khi Hibernate là JPA provider.

## 7. Spring `@Transactional`: chú ý vị trí framework commit

Trong Spring Data JPA, ứng dụng thường để Spring quản lý transaction và inject `EntityManager` theo scope.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void placeOrder(PlaceOrderCommand command) {
        Customer customer = entityManager.find(
                Customer.class, command.customerId()
        );

        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        PurchaseOrder order = new PurchaseOrder(
                customer,
                command.totalAmount()
        );
        entityManager.persist(order);
    }
}
~~~

`PlaceOrderCommand` là DTO/record nghiệp vụ giả định chứa `customerId()` và `totalAmount()`. Khi bean được gọi **qua Spring transaction proxy**, Spring mở/lấy transaction, cho `EntityManager` tham gia, rồi commit/rollback ở ranh giới interceptor.

**Điểm dễ bỏ sót:** `placeOrder()` có thể chạy hết body rồi mới phát lỗi `INSERT` tại flush/commit do framework thực hiện. Vì vậy đặt try/catch chỉ trong body của method để bắt mọi lỗi commit là chưa đủ; cần để lỗi nổi lên tới transaction interceptor và xử lý kết quả ở caller/API layer.

### 7.1. Sai: bắt exception từ repository rồi tiếp tục cùng transaction

~~~java
@Transactional
public void processBatch(List<PlaceOrderCommand> commands) {
    for (PlaceOrderCommand command : commands) {
        try {
            saveOne(command); // Có thể thao tác ORM/flush thất bại.
        } catch (RuntimeException ex) {
            log.warn("Skip invalid record", ex);
            // SAI nếu exception này đến từ ORM/DB:
            // transaction và EntityManager đã bị ảnh hưởng.
        }
    }
}
~~~

Đoạn trên có thể gây nhiều hệ quả:

- Exception khiến transaction bị marked rollback-only nhưng code vẫn tiếp tục.
- Những thao tác tiếp theo tiếp tục dùng cùng persistence context bị lỗi.
- Method trả bình thường, nhưng lúc Spring commit có thể gặp `UnexpectedRollbackException`, `TransactionSystemException` hoặc ngoại lệ khác.
- Caller không biết dòng nào đã được commit thực sự.

**Không nuốt ORM exception rồi tiếp tục xử lý cùng transaction.** Hãy để exception vượt qua transaction boundary và quyết định skip/retry ở một scope mới.

### 7.2. Nếu chủ động đổi lỗi thành kết quả nghiệp vụ

Đôi khi service muốn trả về một `Result` thay vì ném exception. Với lỗi ORM/DB xảy ra trong transaction, **kết thúc unit of work bằng rollback**, không giữ session để ghi tiếp. Trong code dùng Spring, một lựa chọn là đánh dấu rollback-only khi đang ở transaction do Spring quản lý:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result process(PlaceOrderCommand command) {
    try {
        // Thao tác ORM; có thể flush sớm nếu cần xác định lỗi ở đây.
        doPersistenceWork(command);
        entityManager.flush();
        return Result.success();
    } catch (RuntimeException failure) {
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();

        log.warn("Order persistence failed", failure);
        return Result.failure();
    }
}
~~~

`Result` và `doPersistenceWork` là thành phần giả định. Ví dụ này **không tiếp tục dùng entity manager sau lỗi**. Khi rời method, transaction interceptor phải hoàn tất theo trạng thái rollback-only. Cách trả failure không bảo đảm caller có thể biết loại lỗi; production code cần phân loại lỗi và tránh che giấu sự cố integrity. Trong nhiều tình huống, **ném exception để framework rollback** đơn giản và minh bạch hơn.

Cách `setRollbackOnly()` ảnh hưởng transaction lồng nhau, rollback-only đã có hoặc propagation phụ thuộc transaction manager. Nếu không hiểu scope hiện tại, không nên dùng một catch-all rồi tự nuốt lỗi.

### 7.3. Rollback mặc định của Spring

Thông thường, `@Transactional` mặc định rollback với **unchecked exception (`RuntimeException`)** và `Error`; **checked exception** không mặc nhiên kích hoạt rollback trong mọi cấu hình. Nếu ứng dụng dùng checked business exception và muốn rollback, có thể khai báo `rollbackFor` phù hợp hoặc cấu hình transaction policy:

~~~java
@Transactional(rollbackFor = OrderProcessingException.class)
public void placeOrder(...) throws OrderProcessingException {
    // ...
}
~~~

`OrderProcessingException` là checked exception do ứng dụng định nghĩa. Việc chọn rollback vì nghiệp vụ phải được cân nhắc; **exception từ Hibernate/JDBC gây transaction lỗi** không nên bị nuốt chỉ vì muốn để vòng lặp chạy hết.

### 7.4. Self-invocation và propagation không cứu Session lỗi

Nếu một method `@Transactional` của Spring gọi phương thức `@Transactional(propagation = REQUIRES_NEW)` khác **ngay trong cùng object**, lời gọi nội bộ có thể không đi qua transaction proxy. Khi đó kỳ vọng transaction mới có thể không xảy ra.

Ngay cả với `REQUIRES_NEW` thực sự chạy, nó phải dùng **scope persistence context/transaction đúng với integration**; không chuyển một `Session` lỗi vào method mới để tiếp tục. Nếu muốn chia batch thành transaction riêng, tạo một service bean có entry point transaction rõ ràng cho từng item/chunk.

## 8. Phân biệt lỗi làm hỏng công việc ORM với lỗi validation thông thường

Không nên biến quy tắc “discard session sau ORM exception” thành “mọi `IllegalArgumentException` trong Java đều yêu cầu ném bỏ session”:

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Validation nghiệp vụ **trước khi** ORM chạm dữ liệu | Mã sản phẩm trống, số lượng âm do DTO validation | Có thể sửa đầu vào trước khi bắt đầu transaction; nếu đã mở transaction thì chọn rollback/tiếp tục tùy hợp đồng nghiệp vụ và trạng thái context |
| Lỗi cấu hình/mapping khi boot | Entity không có ID, quan hệ không hợp lệ | Sửa cấu hình/mã, không retry với session khác mong tự hết |
| Lỗi ORM khi persist/flush | Tham chiếu transient sai, nullability, dirty state/mapping | Rollback và bỏ session đã thất bại; sửa dữ liệu/logic |
| Lỗi DB constraint | FK, UNIQUE, NOT NULL, CHECK | Rollback và bỏ session; xác định constraint và nguyên nhân |
| Optimistic locking | Entity version cũ khi update/delete | Rollback, tạo transaction/context mới; xử lý conflict hoặc retry có điều kiện |
| Pessimistic locking/deadlock | Lock wait timeout/deadlock tùy DBMS | Transaction lỗi: rollback; có thể retry từ đầu nếu an toàn |
| Mất kết nối/JDBC exception | Connection bị đóng, network timeout | Rollback nếu có thể, bỏ session; kiểm tra hệ thống và retry có giới hạn |
| Lỗi chuyển đổi dữ liệu | JSON converter, type descriptor hoặc dữ liệu DB không đọc được | Bỏ context lỗi; sửa data/schema/converter, không tự retry mù quáng |
| Lỗi ngoài DB xảy ra sau khi DB đã commit | Gửi email thất bại sau `commit` | Đây là **unit of work khác**; không thể rollback DB đã commit chỉ bằng `Session.rollback()` |

**Cần nhìn vào nơi lỗi phát sinh và transaction state**, không chỉ tên exception. Một `IllegalArgumentException` do validation tự viết trước khi truy cập DB khác với `IllegalArgumentException` xuất phát từ Hibernate khi thao tác entity/mapping không hợp lệ.

### 8.1. Hai loại `ConstraintViolationException`

- `org.hibernate.exception.ConstraintViolationException`: Hibernate báo lỗi constraint từ database/JDBC.
- `jakarta.validation.ConstraintViolationException`: Bean Validation phát hiện các vi phạm annotation như `@NotNull`, `@Size`, `@Min`.

Tên ngắn giống nhau nhưng nguồn lỗi khác nhau. Spring còn có thể chuyển lỗi dữ liệu sang `DataIntegrityViolationException`. Lỗi validation không đồng nghĩa DB đã từ chối SQL, nhưng nếu nó xảy ra **trong quá trình flush/persist của unit of work**, không nên giữ session đó và thử ghi tiếp một cách không kiểm soát.

### 8.2. Một exception chỉ nói “rollback-only” chưa đủ để xác nhận dữ liệu đã rollback

Transaction có thể đã được đánh dấu rollback-only nhưng **vẫn cần cho transaction manager hoàn tất rollback**. Không nên gửi response thành công chỉ vì application đã gọi `setRollbackOnly()`. Caller cần biết transaction outcome; trong hệ thống có integration framework, hãy để transaction boundary kết thúc rồi trả kết quả tương ứng.

## 9. Cách thiết kế retry an toàn: unit of work mới, dữ liệu mới

### 9.1. Không dùng lại Session và transaction cũ

**Sai:**

~~~java
try {
    tx.commit();
} catch (RuntimeException ex) {
    // SAI: Session và transaction đã lỗi.
    order.setStatus("PENDING");
    session.flush();
    tx.commit();
}
~~~

**Đúng về cấu trúc:** đóng scope lỗi, phân loại có được thử lại hay không, rồi tạo **scope mới**. Retry từ **command/ID nghiệp vụ**, tải lại entity hoặc xây entity mới cho yêu cầu, và kiểm tra invariant một lần nữa.

### 9.2. Một helper xử lý transaction tách biệt

~~~java
import java.util.function.Function;
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public final class HibernateUnits {
    public static <T> T execute(
            SessionFactory factory,
            Function<Session, T> operation
    ) {
        try (Session session = factory.openSession()) {
            Transaction tx = session.beginTransaction();
            try {
                T result = operation.apply(session);
                tx.commit();
                return result;
            } catch (RuntimeException | Error failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        }
    }
}
~~~

Sử dụng helper:

~~~java
OrderResult result = HibernateUnits.execute(
        sessionFactory,
        session -> {
            PurchaseOrder managed =
                    session.get(PurchaseOrder.class, orderId);

            if (managed == null) {
                throw new IllegalArgumentException("Order not found");
            }

            managed.markPaid();
            return new OrderResult(managed.getId());
        }
);
~~~

`OrderResult` và `orderId` là thành phần minh họa. Mỗi lần gọi `execute` có một session và transaction riêng. **Không truyền entity managed từ lần thử lỗi vào lần thử sau**; truyền ID, DTO hoặc command phù hợp, rồi tải lại dữ liệu.

### 9.3. Khi nào có thể retry?

Không phải lỗi nào cũng có lợi khi retry:

| Nguyên nhân | Có nên retry nguyên thao tác? | Lý do |
| --- | --- | --- |
| Deadlock transaction (được DB báo là transient) | **Có thể**, theo policy và giới hạn | Một transaction mới có thể vượt qua tranh chấp |
| Lock timeout tạm thời | **Có thể**, nếu operation idempotent/có cơ chế kiểm soát | Nên tránh khuếch đại contention |
| Optimistic lock conflict | **Tùy nghiệp vụ** | Cần tải lại dữ liệu và quyết định merge/recalculate hay thông báo conflict |
| Unique constraint vì key thực sự đã tồn tại | **Không retry y nguyên** | Điều kiện dữ liệu vẫn không thay đổi |
| Foreign key trỏ ID không tồn tại | **Không retry mù quáng** | Phải tạo/sửa parent hoặc tham chiếu |
| Mapping sai kiểu/cột | **Không** | Mã và schema cần sửa |
| Mất kết nối | **Có thể**, sau khi đánh giá khả năng commit đã diễn ra | Phải xử lý kết quả commit chưa chắc chắn và idempotency |
| Business invariant vi phạm | **Không** trừ khi điều kiện nghiệp vụ thay đổi | Retry không thay thế validation |

Một helper transaction **không tự quyết định** exception nào transient. Retry policy nên nằm bên ngoài, dựa trên exception/cause, SQLState/vendor code và hợp đồng nghiệp vụ, với số lần thử, backoff và metric rõ ràng.

### 9.4. Retry trong Spring phải tạo transaction mới thật sự

Nếu Spring dùng `@Transactional`, một cách phổ biến là gọi một **service khác** có method transaction-scoped từ lớp orchestration/retry bên ngoài transaction:

~~~java
@Service
public class PaymentAttemptService {
    @Transactional
    public void apply(PaymentCommand command) {
        // Load entity hiện tại, kiểm tra, cập nhật, kết thúc
        // transaction theo proxy Spring.
    }
}

@Service
public class PaymentCoordinator {
    private final PaymentAttemptService attemptService;

    public PaymentCoordinator(PaymentAttemptService attemptService) {
        this.attemptService = attemptService;
    }

    public void run(PaymentCommand command) {
        // Bộ điều phối thực tế có retry policy và phân loại lỗi.
        attemptService.apply(command);
    }
}
~~~

`PaymentCommand` là DTO/record giả định. Nếu có retry, bộ điều phối phải đợi lần gọi trước **ra khỏi transaction interceptor** (commit hoặc rollback) trước khi gọi lại method tạo transaction mới. Không chỉ bắt exception trong một method `@Transactional` rồi lặp lại repository call khi transaction hiện hành đã lỗi.

## 10. Idempotency và trạng thái commit chưa rõ

Một tình huống khó hơn là **mất kết nối đúng lúc commit**. Client có thể nhận timeout trong khi DB đã commit, hoặc ngược lại transaction chưa commit. Nếu ngay lập tức tạo transaction mới để “thử lại” thao tác tạo đơn hàng, có thể tạo hai đơn hàng.

Vì vậy retry ở tầng transaction cần kết hợp **idempotency**:

- Mỗi yêu cầu tạo mới có một **idempotency key** ổn định được ứng dụng gán.
- Database có unique constraint bảo đảm cùng key chỉ tạo một kết quả hợp lệ.
- Trước hoặc sau retry, ứng dụng kiểm tra kết quả hiện có theo key.
- Nếu operation đã thành công nhưng response bị mất, lần yêu cầu tiếp theo trả lại kết quả đó theo hợp đồng.
- Nếu một phần việc nằm ngoài DB (payment gateway, message queue), cần cơ chế outbox/saga/reconciliation thích hợp; local rollback không hoàn tác cuộc gọi bên ngoài.

~~~sql
create table payment_requests (
    id bigint primary key,
    idempotency_key varchar(100) not null unique,
    status varchar(30) not null
);
~~~

Constraint unique chỉ là một mảnh của thiết kế. Code vẫn phải xử lý trường hợp hai request cùng key chạy đồng thời, state chưa hoàn tất và giao dịch ngoại vi có outcome riêng.

**Không đồng nhất “Session bị lỗi” với “chắc chắn toàn bộ công việc đã bị hủy”.** Trong trường hợp mạng đứt lúc commit, trạng thái phía client có thể **không xác định được** cho tới khi đối chiếu database hoặc hệ thống bên ngoài. Dù vậy, session lỗi vẫn phải được bỏ và việc đối chiếu thực hiện bằng scope mới.

## 11. Batch processing: muốn bỏ qua dòng lỗi thì chia transaction

Giả sử job nhập 10.000 bản ghi, trong đó một dòng có foreign key không hợp lệ. Nếu xử lý cả job trong một session/transaction, flush thất bại có thể làm hỏng toàn bộ unit of work. Catch rồi tiếp tục `persist` cùng session không làm lỗi biến mất.

### 11.1. Một transaction cho mỗi record

~~~java
for (ImportRow row : inputRows) {
    try {
        HibernateUnits.execute(sessionFactory, session -> {
            session.persist(mapToEntity(row));
            return null;
        });
        reportSuccess(row);
    } catch (RuntimeException ex) {
        reportFailure(row, ex);
    }
}
~~~

`ImportRow`, `inputRows`, `mapToEntity`, `reportSuccess` và `reportFailure` là ví dụ giả định. Mỗi dòng có **session và transaction độc lập**. Nếu một dòng lỗi, scope đã rollback/close, các dòng sau bắt đầu với scope mới.

Đánh đổi: nhiều transaction làm tăng overhead. Với khối lượng lớn, có thể chia **chunk N dòng**, mỗi chunk có transaction riêng.

### 11.2. Chunk cần rollback trọn vẹn khi một dòng lỗi

~~~text
Chunk A: rows 1–50   → commit thành công
Chunk B: rows 51–100 → row 78 lỗi, rollback toàn chunk B
Chunk C: rows 101–150→ transaction mới, không dùng Session B
~~~

Nếu muốn lưu mọi dòng hợp lệ trong chunk B, phải thiết kế cách phân tách nhỏ hơn **sau khi rollback B**, chẳng hạn thử lại từng dòng trong scope mới, hoặc xử lý dữ liệu đầu vào trước khi ghi. Không giữ session B để tự xóa item 78 khỏi collection rồi `flush()` lần nữa.

### 11.3. `flush()/clear()` không tạo checkpoint commit

Trong batch Hibernate thông thường:

~~~java
if (++count % 50 == 0) {
    session.flush();
    session.clear();
}
~~~

`flush()` gửi DML trong transaction và `clear()` loại managed entities khỏi context. Hai lời gọi này **không commit**. Nếu lỗi xảy ra sau nhiều lần flush trong cùng transaction, rollback vẫn có thể hoàn tác **toàn bộ transaction**. Đồng thời, khi một flush thất bại, **không được dùng `clear()` như biện pháp sửa Session để chạy tiếp**.

### 11.4. Transaction savepoint có giải quyết được không?

Một số DBMS/JDBC có savepoint, và Spring có thể hỗ trợ nested transactions trong điều kiện transaction manager/driver thích hợp. Tuy nhiên **rollback tới savepoint không tự tái tạo persistence context/snapshots và action queue của Hibernate về trạng thái trước savepoint**.

Vì vậy không nên coi JDBC savepoint là phương án tổng quát để tiếp tục cùng Hibernate Session sau một ORM flush exception. Nếu cần xử lý lỗi từng item, ưu tiên những **unit of work riêng biệt**, với contract transaction rõ ràng, hoặc dùng JDBC/bulk interface được thiết kế riêng cho yêu cầu savepoint thay vì trộn nó vào entity graph managed không kiểm soát.

## 12. Không thử “khôi phục” bằng clear, evict, refresh hoặc flush lần hai

| Thao tác dễ bị lạm dụng | Nó thực sự làm gì? | Vì sao không thay thế bỏ Session lỗi? |
| --- | --- | --- |
| `session.clear()` | Detach tất cả entity managed khỏi persistence context | Không phục hồi transaction bị aborted/rollback-only; không xác nhận toàn bộ JDBC/ORM state đã hợp lệ |
| `session.evict(entity)` hoặc JPA `detach(entity)` | Bỏ quản lý một entity | Lỗi có thể đã ảnh hưởng action queue/transaction rộng hơn entity đó |
| `session.flush()` lần nữa | Thử đồng bộ các thay đổi pending | Có thể lặp lại lỗi hoặc chạy trong transaction không còn hợp lệ |
| `session.refresh(entity)` | Đọc lại trạng thái DB của entity managed | Không tự sửa transaction/JDBC state, và có thể bị lỗi do transaction đã aborted |
| `session.cancelQuery()` | Hủy một query đang chạy theo API Hibernate tương ứng | Không phải transaction rollback hay reset Session; cancellation có semantics riêng |
| `tx.rollback()` | Kết thúc transaction bằng rollback | Cần thiết sau lỗi, nhưng object Java và persistence context không được bảo đảm phục hồi hoàn toàn |
| `session.close()` | Kết thúc session và giải phóng tài nguyên thuộc scope | **Đây là bước phù hợp sau rollback**, sau đó cần session mới cho unit of work khác |

Trong tình huống Hibernate exception nghiêm trọng, không nên tìm “API chữa Session”. Thay vào đó hãy đơn giản hóa vòng đời: **thành công thì commit; thất bại thì rollback và close; mỗi lần thử lại dùng context mới**.

## 13. Session là một unit-of-work boundary, không phải singleton hoặc shared thread state

Một `SessionFactory` có thể được giữ trong singleton service. Một `Session` thực không nên được lưu thành field của singleton rồi cho mọi HTTP request hay worker dùng chung:

~~~java
// SAI: service singleton nắm một Session lâu dài.
public class BadOrderService {
    private final Session session;

    public BadOrderService(SessionFactory factory) {
        session = factory.openSession();
    }

    public void save(PurchaseOrder order) {
        session.persist(order);
    }
}
~~~

Sau một lỗi, mọi request tiếp theo có thể tiếp tục dùng đúng session đã bị hỏng. Ngay cả khi không có lỗi, `Session` **không thread-safe** và có thể tích lũy managed entities/giữ dữ liệu stale.

Đúng hơn là giữ `SessionFactory` rồi mở session cho một transaction/service operation, hoặc dùng transaction manager đã tích hợp với framework. Spring có thể tiêm **shared EntityManager proxy** qua `@PersistenceContext`; proxy sẽ chuyển lời gọi tới entity manager gắn với transaction hiện tại, không có nghĩa mọi request dùng chung một real `EntityManager`.

Một tác vụ `CompletableFuture` hoặc background consumer cũng cần transaction/persistence context riêng. Không truyền một `Session` có thể đang rollback giữa các thread, và không giả định transaction context tự lan truyền khi tạo thread mới.

## 14. Giao dịch với thao tác ngoài database: không có rollback toàn cục tự động

Một ứng dụng có thể làm:

~~~text
1. INSERT order trong transaction
2. Gọi API thanh toán bên ngoài
3. UPDATE order = PAID
4. COMMIT database transaction
~~~

Nếu API thanh toán đã thu tiền nhưng database commit thất bại, `rollback()` của Hibernate **không thể tự hoàn lại số tiền ở payment provider**. Tương tự, nếu database commit thành công nhưng gửi email thất bại, không thể gọi rollback trên session mới để xóa giao dịch đã commit.

Phải chọn thiết kế nhất quán giữa các hệ thống:

- **Transactional outbox:** ghi trạng thái nghiệp vụ và outbox event trong cùng database transaction; worker gửi event bên ngoài sau commit, có retry/idempotency.
- **Saga/compensating action:** dùng các bước hoàn tác nghiệp vụ rõ ràng cho hệ thống ngoài (ví dụ refund nếu đã charge).
- **Reconciliation:** đối chiếu giao dịch có kết quả không chắc chắn theo external reference/idempotency key.
- **Timeout và retry policy:** tránh giữ DB transaction mở lâu khi chờ network, nếu nghiệp vụ không đòi hỏi.

Nguyên tắc **không tái sử dụng Session lỗi** là một phần của thiết kế transaction đúng; nó **không thay thế** việc xử lý distributed side effects.

## 15. Ghi log và giám sát đúng vị trí

Khi operation thất bại, cần ghi đủ thông tin để nhận diện lỗi mà không làm lộ dữ liệu nhạy cảm:

- Business operation/correlation ID, entity type/ID nếu có thể công khai trong log nội bộ.
- Điểm lỗi: query, flush hay commit; transaction đang rollback/đã rollback/chưa xác định outcome.
- Loại exception và cause chain, tên constraint nếu là lỗi integrity.
- SQLState/vendor code khi thực sự cần và được phép log.
- Retry attempt, kết quả mỗi attempt, quyết định stop/retry.
- Idempotency key hoặc external reference để đối chiếu commit chưa chắc chắn.
- Thời gian transaction và số lượng bản ghi liên quan nếu phục vụ quan sát vận hành.

Không ghi toàn bộ JDBC bind values hoặc JSON payload chứa thông tin cá nhân/secret vào log production chỉ để debug.

### 15.1. SQL logging giúp tìm lúc lỗi nhưng không thay rollback

Trong Hibernate 6, logger `org.hibernate.SQL` ở mức DEBUG có thể cho thấy SQL Hibernate phát sinh; `org.hibernate.orm.jdbc.bind` ở mức TRACE có thể giúp điều tra tham số khi an toàn. Tên và cách cấu hình logger phụ thuộc logging framework. Cần hiểu SQL hiện ra trong log **không chứng minh transaction đã commit**: một statement đã chạy có thể bị rollback sau đó.

### 15.2. Một exception bên ngoài có thể bọc lỗi gốc

Một constraint error có thể đi qua nhiều lớp:

~~~text
HTTP/API handler
  └── Spring DataIntegrityViolationException hoặc transaction exception
        └── JPA PersistenceException / Hibernate exception
              └── SQLException từ JDBC driver
~~~

Đây là sơ đồ nguyên nhân **minh họa**. Không phải lần nào cũng có đúng các lớp wrapper hoặc đúng thứ tự. Khi phân loại, xem cause chain, constraint name/SQLState và transaction outcome. Không dựa vào string message của exception như một hợp đồng ổn định giữa các DBMS.

## 16. Hướng dẫn quyết định tại điểm lỗi

~~~mermaid
flowchart TD
    A[Exception xảy ra] --> B{Đã vào thao tác ORM/JDBC hoặc flush/commit?}
    B -- Không --> C[Phân loại business/validation exception]
    C --> D[Kết thúc hoặc điều chỉnh workflow theo hợp đồng nghiệp vụ]
    B -- Có --> E{ORM/transaction bị lỗi?}
    E -- Có --> F[Ngừng dùng persistence context hiện tại]
    F --> G[Rollback nếu còn khả năng]
    G --> H[Close Session / kết thúc transaction scope]
    H --> I[Phân loại lỗi để stop, sửa dữ liệu hoặc retry]
    I --> J{Retry được và an toàn?}
    J -- Có --> K[Session + transaction mới; reload/rebuild state]
    J -- Không --> L[Báo lỗi hoặc enqueue reconciliation]
    E -- Không --> D
~~~

Đây là sơ đồ hỗ trợ ra quyết định. Trong những framework cụ thể, transaction manager sở hữu commit/rollback/close; không chủ động đóng transaction-bound `EntityManager` khi framework đang quản lý nó. Điều cần bảo đảm là **không tiếp tục workflow dựa trên persistence context đã thất bại và để transaction boundary kết thúc đúng cách**.

### 16.1. Trường hợp validation exception trước ORM

~~~java
public void placeOrder(PlaceOrderCommand command) {
    if (command.quantity() <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }

    // Chỉ sau khi đầu vào hợp lệ mới mở transaction và chạm DB.
}
~~~

Ở đây lỗi xảy ra trước khi tạo session hay thay đổi persistence context. Không có “Session hỏng” nào cần bỏ. Nếu validation xảy ra bên trong transaction đã có nhiều thay đổi, ứng dụng vẫn cần quyết định rollback toàn unit of work theo nghiệp vụ, nhưng nguyên nhân khác lỗi JDBC.

### 16.2. Trường hợp exception ORM/JDBC

~~~java
try {
    session.persist(order);
    session.flush();
} catch (RuntimeException ex) {
    // Đã có lỗi khi Hibernate đồng bộ/ghi dữ liệu.
    // Kết thúc transaction bằng rollback và bỏ session.
    throw ex;
}
~~~

Không phải nơi nào cũng nên tự gọi rollback: nếu Spring quản lý transaction, hãy để exception được propagate qua proxy để rollback. Nếu dùng native API, phải bảo đảm catch/try-with-resources ở lớp transaction owner rollback và close.

### 16.3. Trường hợp lỗi sau commit

~~~java
createOrderInDatabase(command); // Transaction đã commit.
sendConfirmationEmail(command); // Có thể lỗi ở đây.
~~~

Nếu gửi email thất bại sau khi database đã commit, `Session` của transaction trước đã kết thúc. Retry email là một công việc mới với idempotency riêng; không được mở session mới rồi cố “rollback” order đã commit như thể hai thao tác là một database transaction.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| “Chỉ cần `catch` exception là tiếp tục được.” | Catch không tự rollback transaction, sửa action queue hay restore entity state. |
| “SQL đã lỗi nhưng tôi vẫn gọi `commit()` xem sao.” | Transaction có thể aborted/rollback-only; cần kết thúc bằng rollback thay vì commit mù quáng. |
| “`rollback()` sẽ đổi field Java về giá trị ban đầu.” | Rollback database không tự undo mọi mutation của object managed/detached trong bộ nhớ. |
| “`clear()` sau lỗi SQL khiến session sạch lại.” | Clear chỉ detach entity; không phải reset transaction/JDBC error. |
| “Có thể retry cùng managed entity sau khi lỗi.” | Entity có thể mang ID/state từ attempt lỗi; tạo context mới và rebuild/reload dữ liệu. |
| “Mọi exception Java đều làm Session hỏng.” | Cần phân biệt lỗi nghiệp vụ trước ORM với lỗi persistence/transaction thực sự. |
| “`persist()` không ném lỗi tức là đã lưu.” | SQL có thể chỉ phát khi flush/commit; với IDENTITY lại có thể phát sớm. |
| “`@Transactional` tự rollback dù tôi bắt và nuốt exception.” | Framework thường cần exception đi qua boundary hoặc transaction được đánh dấu rollback-only. |
| “Có thể gọi `REQUIRES_NEW` nội bộ để tự có transaction mới.” | Self-invocation có thể bỏ qua Spring proxy; còn phải bảo đảm context mới. |
| “Một lỗi FK chỉ cần retry ba lần.” | Lỗi dữ liệu không biến mất nếu bản ghi đích/constraint không đổi. |
| “Mất kết nối lúc commit chắc chắn chưa lưu.” | Outcome có thể không rõ; cần idempotency và reconciliation. |
| “Cứ flush mỗi 50 record là có checkpoint.” | Flush không commit; rollback có thể hoàn tác cả transaction. |
| “SessionFactory cũng cần bỏ khi một Session lỗi.” | Factory dùng chung thường tiếp tục hoạt động; cần bỏ đúng Session và xử lý root cause nếu hạ tầng lỗi. |
| “Đóng Session sẽ tự commit các thay đổi.” | Close không thay thế commit; quản lý transaction là trách nhiệm riêng. |

## 18. Tình huống thực tế và chiến lược phù hợp

### Tình huống A — Một đơn hàng vi phạm FK

`Order.customer_id` trỏ đến customer không tồn tại. Database báo `ConstraintViolationException`. **Rollback và đóng session**; trả lỗi nghiệp vụ phù hợp hoặc báo dữ liệu nội bộ không nhất quán. Không retry y nguyên bằng session khác khi ID không tồn tại.

### Tình huống B — Hai transaction sửa một đơn hàng có `@Version`

Transaction A commit trước, B flush với version cũ và gặp optimistic-lock conflict. **Rollback B, bỏ persistence context B**. Nếu nghiệp vụ cho phép retry, tải lại order bằng transaction mới và áp dụng lại command sau khi tính toán trên trạng thái mới; không copy toàn bộ detached entity cũ để ghi đè mù quáng.

### Tình huống C — Một batch có dòng sai

Đang import 5.000 bản ghi, dòng 231 lỗi `UNIQUE`. Nếu muốn bỏ dòng lỗi và xử lý 232 trở đi, phải kết thúc transaction/chunk thất bại; tiếp tục bằng **session và transaction mới**. Có thể chia chunk nhỏ, xử lý singleton fallback hoặc báo lỗi theo bản ghi, với idempotency ở DB.

### Tình huống D — Lỗi timeout trước khi biết commit đã xong chưa

Khách hàng gửi yêu cầu thanh toán, client timeout đúng lúc DB commit. Không thực hiện ngay lần tạo mới thứ hai với ID khác. Dùng idempotency key để tra trạng thái trên connection/transaction mới, đồng thời đối chiếu payment provider nếu có side effects ngoài DB.

### Tình huống E — Giao dịch Spring bắt exception rồi trả HTTP 200

Method `@Transactional` có vòng lặp, bắt `DataIntegrityViolationException` và tiếp tục. Method trả bình thường, nhưng transaction có thể rollback-only; lúc interceptor commit có thể ném `UnexpectedRollbackException`. Thiết kế lại: để exception propagate và xử lý ở API boundary, hoặc rollback-only rồi trả failure **sau khi transaction đã kết thúc**, tùy policy.

### Tình huống F — Lỗi domain validation trước transaction

Một DTO thiếu sản phẩm được phát hiện trước khi gọi repository. Không có session bị lỗi. Trả lỗi input và cho client sửa. **Không mở transaction cho những validation có thể xử lý thuần Java trước DB** khi không có lý do khác.

## 19. Bài tập tự kiểm tra

**1.** Trong cùng transaction, Hibernate đã flush một `UPDATE` cho entity A rồi `INSERT` entity B vi phạm FK. Sau rollback, trạng thái field Java của A có chắc quay về giá trị trước đó không? Vì sao không nên tiếp tục với session cũ?

**2.** Một method `@Transactional` bắt exception từ repository rồi không ném tiếp. Những kết quả nào có thể xuất hiện ở transaction boundary? Cần làm gì để caller không hiểu sai là đã thành công?

**3.** Một `persist()` không ném exception, nhưng `commit()` ném lỗi constraint. Vì sao catch chỉ quanh `persist()` là chưa đủ?

**4.** Khi batch đang chạy bị lỗi ở record 50, liệu `session.clear()` rồi `persist()` record 51 có phải một chiến lược an toàn không? Nếu muốn skip record lỗi, nên tổ chức unit of work thế nào?

**5.** `OptimisticLockException` xảy ra do version cũ. Có nên retry bằng cách gọi `merge(detachedObject)` ngay trong `EntityManager` cũ không? Vì sao?

**6.** Khi mạng lỗi đúng lúc commit đơn hàng mới, làm sao ngăn retry tạo trùng dữ liệu?

**7.** Tại sao `SessionFactory` vẫn có thể được dùng sau khi một `Session` gặp lỗi Hibernate/JDBC?

**8.** Phân biệt `jakarta.validation.ConstraintViolationException` và `org.hibernate.exception.ConstraintViolationException`. Trong tình huống nào mỗi loại phát sinh?

**9.** Vì sao JDBC savepoint không thể tự bảo đảm khôi phục Hibernate persistence context sau lỗi flush?

**10.** Một thao tác gửi email thất bại sau khi database đã commit. Vì sao rollback Hibernate Session mới không thể hoàn tác email hoặc order đã commit?

**Gợi ý:** (1) không, rollback DB khác undo object state; (2) transaction có thể rollback-only hoặc commit lỗi, cần để boundary xử lý và trả failure; (3) SQL có thể phát khi flush/commit; (4) không, chia transaction/session; (5) không, context mới và reload; (6) idempotency key, unique constraint, reconciliation; (7) factory và session có vòng đời/tài nguyên khác; (8) Bean Validation khác DB constraint; (9) ORM snapshots/action queue không tự đồng bộ savepoint; (10) external side effects và các transaction đã hoàn tất cần compensation/outbox.

## 20. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): phạm vi `Session`, transaction handling, flush, exception handling và optimistic locking.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn user guide/migration guide theo phiên bản ORM đang chạy, nhất là khi tích hợp JTA và các transaction manager.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `EntityManager`, transaction semantics, exception và rollback-only behavior.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction interception, rollback rules, propagation và phạm vi `@Transactional`.

**Nguyên tắc cần giữ:** lỗi ORM/JDBC nghiêm trọng không chỉ là một exception cần `catch`; nó làm **cả unit of work** cần được kết thúc có kiểm soát. **Rollback transaction, đóng/bỏ Session và persistence context bị ảnh hưởng, báo lỗi đúng nghĩa, rồi chỉ retry bằng transaction mới khi đã xác định nguyên nhân có thể retry và thao tác an toàn**. Cách tiếp cận này tránh việc những state thay đổi dở dang trong bộ nhớ ORM tiếp tục phát sinh SQL ngoài dự kiến và giúp quản lý chính xác tính nhất quán dữ liệu.
