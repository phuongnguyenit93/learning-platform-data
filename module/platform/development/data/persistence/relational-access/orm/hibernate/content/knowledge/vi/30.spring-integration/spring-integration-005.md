# Propagation, isolation, timeout và chính sách rollback theo loại ngoại lệ trong Spring Transaction

Trong một ứng dụng Spring kết hợp Hibernate/JPA, khai báo `@Transactional` giúp giới hạn **unit of work**: một chuỗi thao tác đọc/ghi dữ liệu hoặc cùng commit, hoặc rollback theo chính sách đã định. Nhưng annotation này không chỉ là một công tắc bật/tắt transaction. Nó còn mô tả **cách tham gia transaction đang có (propagation)**, **mức cách ly dữ liệu (isolation)**, **thời hạn transaction (timeout)** và **khi nào phải rollback theo loại ngoại lệ**.

Bốn nhóm lựa chọn này thường bị nhầm với nhau:

- **Propagation** trả lời: phương thức này có tham gia transaction của caller không, hay tạo transaction mới?
- **Isolation** trả lời: transaction này được phép quan sát thay đổi đồng thời từ transaction khác như thế nào?
- **Timeout** trả lời: transaction được phép hoạt động trong giới hạn thời gian nào và hệ thống phản ứng ra sao khi quá hạn?
- **Rollback rules** trả lời: nếu phương thức kết thúc bằng một exception, Spring nên yêu cầu commit hay rollback?

Các lựa chọn phải phù hợp với **transaction manager**, **database**, **JDBC driver**, **cơ chế proxy của Spring** và **Hibernate persistence context**. Một cấu hình hợp lệ về cú pháp có thể không được thực thi như mong đợi nếu phương thức không đi qua transactional proxy hoặc nếu DBMS không hỗ trợ tính năng tương ứng.

Bài này tập trung vào Spring Framework 6.x / Spring Boot 3.x với Hibernate ORM 6.x và Jakarta Persistence (Java 17+), đồng thời giải thích những nguyên tắc vẫn áp dụng cho các phiên bản mới. Các ví dụ được tách thành từng tình huống để dễ nhìn thấy transaction boundary, không mặc định rằng mọi đoạn minh họa là một project hoàn chỉnh có thể chạy mà không bổ sung dependency và mapping.

## 1. Transaction boundary là lớp phối hợp giữa Spring, Hibernate và database

Giả sử người dùng đặt hàng. Service cần lưu Order, trừ tồn kho và ghi một bản ghi lịch sử nội bộ. Nếu một thao tác thất bại, không nên để hệ thống còn lại một nửa trạng thái.

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final InventoryService inventory;

    public CheckoutService(
            OrderRepository orders,
            InventoryService inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Long checkout(CheckoutCommand command) {
        Order order = Order.from(command);
        orders.save(order);

        inventory.reserve(
                command.productId(),
                command.quantity()
        );

        return order.getId();
    }
}
~~~

Ở ví dụ này, `@Transactional` là `org.springframework.transaction.annotation.Transactional`, không phải annotation cùng tên thuộc `jakarta.transaction`. Spring dùng một transaction interceptor cùng `PlatformTransactionManager` được cấu hình để mở/tham gia transaction trước khi vào method, và quyết định commit/rollback khi method kết thúc.

Với `JpaTransactionManager`, Spring quản lý transactional `EntityManager`; Hibernate dùng `Session`/`PersistenceContext` tương ứng để theo dõi managed entities và flush những thay đổi vào JDBC/database transaction. Sau commit, dữ liệu được lưu bền vững theo database; sau rollback, các thao tác DML thuộc transaction bị hủy theo khả năng ACID của DB.

**Điểm quan trọng:** annotation không tự tạo một transaction phân tán bao phủ mọi thứ. Một HTTP call tới payment gateway, một email đã gửi hoặc một thông điệp đã publish thẳng ra broker **không tự rollback cùng JDBC transaction**. Nếu cần phối hợp database và external system, dùng outbox, saga hoặc thiết kế consistency tương ứng thay vì giả định `@Transactional` có thể “thu hồi” hiệu ứng bên ngoài.

### 1.1. Sơ đồ đường đi

~~~mermaid
sequenceDiagram
    participant Caller as Caller / Controller
    participant Proxy as Spring Transaction Proxy
    participant TM as JpaTransactionManager
    participant EM as EntityManager / Hibernate
    participant DB as Database
    Caller->>Proxy: checkout(command)
    Proxy->>TM: Bắt đầu hoặc tham gia transaction
    TM->>EM: Bind transactional EntityManager
    Proxy->>EM: Gọi nghiệp vụ trong service
    EM->>DB: SQL khi flush / query
    alt Method thành công và transaction có thể commit
        Proxy->>TM: Commit
        TM->>EM: Flush nếu cần
        EM->>DB: COMMIT
    else Exception thuộc rollback rule
        Proxy->>TM: Rollback / đánh dấu rollback-only
        EM->>DB: ROLLBACK
    end
    Proxy-->>Caller: Result hoặc exception
~~~

Tùy flush mode, các `INSERT`/`UPDATE` có thể phát sớm hơn thời điểm commit; Hibernate cũng có thể auto-flush trước một query. **Đã thấy SQL UPDATE trong log không có nghĩa transaction đã commit.**

### 1.2. Transaction của Spring khác persistence context

| Khái niệm | Vai trò |
| --- | --- |
| `@Transactional` | Khai báo thuộc tính transaction cho method/class qua Spring |
| `PlatformTransactionManager` | Điều phối begin/commit/rollback theo loại persistence resource |
| `JpaTransactionManager` | Quản lý transaction JPA `EntityManager`, có tích hợp JDBC tùy cấu hình |
| `EntityManager`/Hibernate `Session` | Theo dõi entity identity, trạng thái managed và dirty checking |
| JDBC `Connection` | Kênh thực thi SQL trong database transaction |
| Database transaction | Nguồn thực thi isolation, locking, commit/rollback |
| Connection pool (ví dụ HikariCP) | Cho mượn/tái sử dụng connections, **không quyết định propagation** |

Những lớp này phối hợp nhưng không đồng nhất. Một `EntityManager` có thể tồn tại trong ngữ cảnh mở rộng, nhưng physical transaction có thể bắt đầu/kết thúc theo service boundary. Việc trả connection về pool không tự xoá toàn bộ dữ liệu đã được Hibernate giữ trong persistence context nếu context đó vẫn đang hoạt động.

## 2. Khai báo các thuộc tính @Transactional

Annotation Spring cho phép cấu hình bốn nhóm chính:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 15,
    rollbackFor = BusinessCheckedException.class
)
public void process() throws BusinessCheckedException {
    // DML / ORM operations
}
~~~

- `propagation` mặc định là `REQUIRED`.
- `isolation` mặc định là `DEFAULT` (dùng mức isolation mặc định của transaction manager/DB).
- `timeout` mặc định theo transaction manager, thường không đặt timeout riêng tại method.
- Quy tắc rollback mặc định của Spring thường **rollback với `RuntimeException` và `Error`**, nhưng **không rollback chỉ vì một checked `Exception`**; chi tiết sẽ được phân tích ở phần rollback.
- `readOnly` mặc định `false`; nó là một hint tối ưu, không đồng nghĩa chặn hoàn toàn lệnh ghi.

Có thể đặt `@Transactional` ở lớp để làm mặc định, rồi override tại method:

~~~java
@Service
@Transactional(readOnly = true)
public class ProductService {

    public ProductDto get(Long id) {
        // Mặc định readOnly = true.
        return loadDto(id);
    }

    @Transactional(readOnly = false)
    public void changePrice(Long id, BigDecimal value) {
        // Ghi dữ liệu, override readOnly.
    }
}
~~~

Đừng đặt annotation ở mọi method theo thói quen. Nên đặt **transaction boundary theo use case**, thường tại service/application layer; repository thao tác DB nằm bên trong transaction đó.

## 3. Propagation: method tham gia transaction hiện hữu như thế nào?

Spring cung cấp bảy giá trị `Propagation` chính:

| Chế độ | Khi caller không có transaction | Khi caller đã có transaction | Tình huống tiêu biểu |
| --- | --- | --- | --- |
| `REQUIRED` | Tạo mới | Tham gia cùng transaction | Service nghiệp vụ mặc định |
| `REQUIRES_NEW` | Tạo mới | Tạm đình chỉ outer, tạo physical transaction độc lập | Ghi log/audit cần commit riêng |
| `NESTED` | Thường tạo transaction mới theo manager hỗ trợ | Tạo nested scope qua JDBC savepoint trên cùng physical transaction | Rollback một bước JDBC tùy chọn |
| `SUPPORTS` | Chạy không có transaction | Tham gia transaction hiện hữu | Utility đọc có thể tham gia |
| `NOT_SUPPORTED` | Chạy không có transaction | Tạm đình chỉ transaction hiện hữu để chạy ngoài nó | Công việc không muốn giữ DB transaction |
| `MANDATORY` | Báo lỗi | Phải tham gia transaction hiện hữu | API chỉ hợp lệ trong unit of work đã mở |
| `NEVER` | Chạy không có transaction | Báo lỗi | API phải chạy ngoài transaction |

`REQUIRED` và `REQUIRES_NEW` thường là hai chế độ cần hiểu sâu nhất. `NESTED` có khác biệt hỗ trợ quan trọng giữa JDBC và JPA.

### 3.1. REQUIRED: lựa chọn mặc định

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final StockService stocks;

    @Transactional(propagation = Propagation.REQUIRED)
    public void placeOrder(PlaceOrderCommand command) {
        orders.save(new Order(command));

        // Nếu StockService.reserve() cũng dùng REQUIRED,
        // hai thao tác tham gia cùng physical transaction.
        stocks.reserve(command.productId(), command.quantity());
    }
}
~~~

Nếu `placeOrder()` không được gọi bên trong transaction nào, Spring bắt đầu một transaction mới. Nếu nó được gọi từ một transactional method khác qua proxy, nó tham gia transaction đang có.

~~~text
Controller
  -> OrderService.placeOrder() [REQUIRED, mở TX #1]
       -> StockService.reserve() [REQUIRED, tham gia TX #1]
  -> Commit TX #1
~~~

Nếu `reserve()` ném một unchecked exception và exception đi qua transactional interceptor, transaction thường bị rollback. Nếu một inner `REQUIRED` đánh dấu transaction chung thành rollback-only nhưng outer method bắt exception và cố commit, có thể gặp `UnexpectedRollbackException`, xem phần 12.

### 3.2. REQUIRED không tạo “transaction riêng cho mỗi method”

Với hai service methods đều `REQUIRED`:

~~~java
@Transactional
public void execute() {
    serviceA.stepA();
    serviceB.stepB();
}
~~~

nếu cả hai call đi qua các Spring transactional proxies và không có một propagation override khác, chúng **chia sẻ cùng physical transaction**. Không có “commit tại cuối `stepA()` rồi mới bắt đầu `stepB()`” vì `stepA` chỉ tạo logical transaction scope tham gia transaction đã có.

**Logical scope** của interceptor và **physical DB transaction** không phải lúc nào cũng một-một.

## 4. REQUIRES_NEW: transaction độc lập với outer

`REQUIRES_NEW` luôn yêu cầu physical transaction riêng. Khi có outer transaction, Spring tạm đình chỉ resources/context của outer rồi bắt đầu inner transaction mới.

~~~java
@Service
public class AuditService {
    private final AuditRepository audits;

    public AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String requestId, String outcome) {
        audits.save(new AuditEvent(requestId, outcome));
    }
}
~~~

Caller:

~~~java
@Service
public class PaymentApplicationService {
    private final AuditService audit;
    private final PaymentRepository payments;

    @Transactional
    public void confirm(String paymentId) {
        payments.markConfirmed(paymentId);  // TX ngoài.
        audit.recordAttempt(paymentId, "ATTEMPT"); // TX riêng.
        throw new IllegalStateException("Business operation failed");
    }
}
~~~

Nếu `recordAttempt` trả về bình thường và inner transaction commit, bản ghi audit **có thể vẫn tồn tại** sau khi outer transaction rollback vì exception. Đây là một trong những mục đích phổ biến của `REQUIRES_NEW`.

### 4.1. Điều gì xảy ra khi inner lỗi?

~~~text
Outer TX A bắt đầu
    -> Inner REQUIRES_NEW TX B bắt đầu
        -> INSERT audit
        -> lỗi -> ROLLBACK B
    -> Outer A tiếp tục nếu caller bắt lỗi và không bị đánh dấu rollback-only
    -> COMMIT A hoặc ROLLBACK A tùy chính sách
~~~

Inner rollback không tự rollback A nếu exception được outer xử lý đúng và A chưa bị đánh dấu rollback-only do nguyên nhân khác. Ngược lại, nếu unchecked exception đi ra khỏi outer transactional boundary thì Spring vẫn rollback A theo rule của outer. Tính độc lập là **physical transaction boundary**, không phải cam kết mọi exception sẽ bị bỏ qua.

### 4.2. Kết nối và resource usage

Nếu outer TX A đang giữ một database connection, inner TX B thường phải lấy **connection khác** từ pool để thực thi độc lập. Khi nhiều threads cùng giữ outer transaction và đồng thời mở inner `REQUIRES_NEW`:

- Pool có thể không còn connection rảnh.
- Các threads chờ nhau/đạt connection acquisition timeout.
- Inner transaction có thể phải đợi locks mà outer đang giữ.
- Throughput giảm dù code có vẻ “đơn giản”.

Vì vậy Spring cảnh báo không dùng `REQUIRES_NEW` bừa bãi khi connection pool nhỏ. Cần sizing pool theo **số transactions đồng thời và số inner transactions có thể lồng nhau**, đồng thời giữ transaction ngắn.

### 4.3. REQUIRES_NEW không phải cách giấu lỗi dữ liệu

Nếu outer đang giữ một entity managed đã thay đổi nhưng chưa flush, inner transaction không mặc nhiên nhìn thấy thay đổi chưa commit của outer. Inner đọc DB theo isolation của riêng nó. Không truyền entity của outer vào inner rồi tưởng entity đó được quản lý bởi inner persistence context.

Tốt hơn là truyền identifiers/immutable values rồi tải dữ liệu trong inner transaction khi cần, và tránh thiết kế inner cần đọc row đang bị outer lock.

### 4.4. Có nên ghi audit bằng REQUIRES_NEW?

Có thể, nếu audit transaction là một bản ghi nội bộ tương đối độc lập. Nhưng nó vẫn thất bại khi database không khả dụng. Nếu yêu cầu “audit chắc chắn không mất ngay cả khi DB transaction chính thất bại”, cần xem kiến trúc audit/event delivery, logging ngoài DB hoặc outbox phù hợp. Không hiểu `REQUIRES_NEW` như distributed transaction với độ bền tuyệt đối.

## 5. NESTED: savepoint, không phải một transaction độc lập

`NESTED` thường dựa trên JDBC savepoints trong **cùng physical database transaction**:

~~~text
TX ngoài bắt đầu
  INSERT A
  SAVEPOINT S
    INSERT B
    lỗi
  ROLLBACK TO SAVEPOINT S   -> B bị hủy
  INSERT C
COMMIT TX ngoài              -> A và C được commit
~~~

Nếu outer transaction cuối cùng rollback, **mọi thay đổi của outer và nested cũng rollback**. Savepoint chỉ cho phép quay về một mốc trong cùng transaction; nó không thể commit độc lập như `REQUIRES_NEW`.

### 5.1. Ví dụ với JDBC và DataSourceTransactionManager

~~~java
@Service
public class JdbcBatchService {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate outer;
    private final TransactionTemplate nested;

    public JdbcBatchService(
            JdbcTemplate jdbc,
            DataSourceTransactionManager manager
    ) {
        this.jdbc = jdbc;

        outer = new TransactionTemplate(manager);
        outer.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );

        nested = new TransactionTemplate(manager);
        nested.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_NESTED
        );
    }

    public void execute() {
        outer.executeWithoutResult(outerStatus -> {
            jdbc.update("insert into required_events(id) values (?)", 1L);

            try {
                nested.executeWithoutResult(nestedStatus -> {
                    jdbc.update(
                        "insert into optional_events(id) values (?)",
                        2L
                    );
                    throw new IllegalArgumentException(
                        "Optional operation failed"
                    );
                });
            } catch (IllegalArgumentException ex) {
                // Nested scope rollback về savepoint.
            }

            jdbc.update("insert into required_events(id) values (?)", 3L);
        });
    }
}
~~~

Ví dụ giả định các bảng tồn tại và JDBC driver hỗ trợ savepoint. `DataSourceTransactionManager` phù hợp với JDBC-based operations, không tự thay thế transaction management cho toàn bộ JPA/Hibernate `EntityManager`.

### 5.2. NESTED với JpaTransactionManager/Hibernate

**Không mặc định `Propagation.NESTED` được hỗ trợ an toàn trong JPA.** `JpaTransactionManager` không bật nested transaction cho JPA EntityManager theo cách tương đương JDBC savepoints; khả năng nested/savepoint phụ thuộc transaction manager, JDBC driver và cấu hình. Ngay cả khi một JDBC savepoint tồn tại, **Hibernate persistence context không được “rewind” đầy đủ** về trạng thái trước savepoint: managed entities, snapshots và các pending changes trong Session có thể không đồng bộ với DB sau rollback-to-savepoint.

Vì vậy:

- Nếu workflow cần partial rollback trên JDBC, kiểm tra `DataSourceTransactionManager`, savepoint support và integration tests.
- Nếu dùng JPA/Hibernate entities, thường thiết kế lại unit of work hoặc dùng `REQUIRES_NEW` khi thật sự cần commit/rollback độc lập.
- Không bật `nestedTransactionAllowed` tùy tiện rồi coi mọi JPA state sẽ rollback riêng theo đúng semantics.
- Không tiếp tục dùng một Hibernate Session đã gặp persistence/JDBC failure nghiêm trọng ngoài kiểm soát, dù về mặt JDBC bạn có thể nghĩ đến savepoint.

### 5.3. Khi nào nên dùng NESTED?

Một tình huống JDBC cần nhiều bước con tùy chọn nhưng phải commit chung kết quả cuối. Chỉ chọn nó khi có bảo đảm rõ về savepoint, exception handling và tính nhất quán của state trong application. Với nghiệp vụ domain qua ORM, cách chia transaction boundaries rõ ràng thường dễ bảo trì hơn.

## 6. SUPPORTS, NOT_SUPPORTED, MANDATORY và NEVER

### 6.1. SUPPORTS

~~~java
@Transactional(propagation = Propagation.SUPPORTS, readOnly = true)
public ProductSnapshot summarize(Long id) {
    return querySummary(id);
}
~~~

Nếu caller có transaction, method tham gia. Nếu không, method có thể chạy không có physical transaction do method tự tạo. Đừng nhầm `SUPPORTS` với “luôn có snapshot đọc nhất quán”: không có outer transaction thì các câu SELECT có thể chịu cơ chế autocommit/connection behavior tương ứng.

Spring có thể đồng bộ một số resources ngay cả trong scope không có physical transaction, tùy manager và settings. Hãy xác định đúng hợp đồng dữ liệu nếu method chạy nhiều SELECT.

### 6.2. NOT_SUPPORTED

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void generateNonTransactionalReport() {
    // Được gọi ngoài transaction đang có.
}
~~~

Nếu caller đã mở transaction, Spring tạm đình chỉ nó trong lúc method chạy, rồi nối lại sau khi method kết thúc. Tác dụng thường mong muốn là không giữ transaction bao quanh một công việc dài không cần database atomicity.

**Cảnh báo:** `NOT_SUPPORTED` không đồng nghĩa toàn bộ SQL trong method đều “không dùng database transaction” về mặt DBMS. Từng statement JDBC vẫn được thực thi theo cơ chế autocommit/default của connection. Nếu method cần nhiều thao tác DML phải commit đồng bộ, `NOT_SUPPORTED` không phù hợp.

### 6.3. MANDATORY

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void updateReservationWithinExistingUnitOfWork(Long id) {
    // Chỉ hợp lệ nếu caller đã mở transaction.
}
~~~

Nếu không có transaction tồn tại, Spring ném exception trước khi thực hiện nghiệp vụ. Hữu ích khi muốn method không tự mở một transaction độc lập, vì nó phải là một phần của use case lớn.

### 6.4. NEVER

~~~java
@Transactional(propagation = Propagation.NEVER)
public void checkNonTransactionalContract() {
    // Chỉ được chạy khi không có transaction hiện hữu.
}
~~~

Nếu caller đang trong transaction, Spring ném exception. Khác `NOT_SUPPORTED`: `NEVER` **không tạm đình chỉ** outer để chạy tiếp; nó từ chối tình huống đó.

### 6.5. Bảng chọn nhanh

| Nhu cầu | Gợi ý |
| --- | --- |
| Toàn bộ service workflow cùng thành công/thất bại | `REQUIRED` |
| Một thao tác DB phải commit riêng, không theo rollback của outer | `REQUIRES_NEW` |
| Rollback một nhánh JDBC về savepoint nhưng commit chung outer | `NESTED` với manager/driver hỗ trợ |
| Chỉ bắt buộc transaction do caller mở | `MANDATORY` |
| Có transaction thì tham gia, không có cũng được | `SUPPORTS` |
| Tạm ra khỏi transaction cho tác vụ không cần atomicity | `NOT_SUPPORTED` |
| Tuyệt đối không được chạy trong transaction của caller | `NEVER` |

Chọn propagation theo **ngữ nghĩa nghiệp vụ**, không theo ý định “giảm số method có @Transactional”.

## 7. Isolation: mức cách ly dữ liệu giữa transactions

Isolation là một thuộc tính database transaction, giúp điều chỉnh mức độ ảnh hưởng của các thao tác đồng thời. Spring cung cấp các giá trị `Isolation`:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateProduct() {
    // ...
}
~~~

Các giá trị:

- `DEFAULT`: dùng mức mặc định của datasource/database.
- `READ_UNCOMMITTED`.
- `READ_COMMITTED`.
- `REPEATABLE_READ`.
- `SERIALIZABLE`.

**Isolation không phải thuộc tính riêng của Hibernate Session.** Spring truyền yêu cầu xuống transaction manager/connection theo khả năng, còn DBMS thực thi quy tắc visibility/locking/MVCC. Kết quả chi tiết khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server và Oracle.

### 7.1. Các hiện tượng đồng thời cần biết

**Dirty read:** transaction A đọc dữ liệu mà transaction B đã ghi nhưng chưa commit; nếu B rollback, A đã đọc một giá trị không bền vững.

**Non-repeatable read:** A đọc cùng row hai lần và thấy hai giá trị khác nhau do B commit cập nhật giữa hai lần đọc.

**Phantom:** A chạy lại một câu query theo predicate và thấy tập rows thay đổi do transaction khác insert/delete hoặc thay đổi dữ liệu đủ điều kiện.

**Lost update:** hai transactions đọc cùng giá trị, cùng tính toán thay đổi và lần ghi sau vô tình ghi đè kết quả của lần trước. Không phải cứ dùng `REPEATABLE_READ` là mọi DBMS đều tự bảo vệ khỏi mọi biến thể lost update; ORM thường cần `@Version`, locks hoặc atomic update thích hợp.

**Write skew:** hai transactions đọc dữ liệu liên quan và cập nhật các rows khác nhau, cùng vi phạm một invariant tổng thể nếu không có cơ chế cách ly/ràng buộc phù hợp.

### 7.2. Bảng hiểu mức cách ly

| Isolation | Định hướng chuẩn | Những điều vẫn cần cân nhắc |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Cho phép mức đọc ít cách ly nhất theo chuẩn SQL | Nhiều DBMS không thực sự cung cấp dirty reads hoặc ánh xạ thành mức cao hơn |
| `READ_COMMITTED` | Không thấy uncommitted changes từ giao dịch khác | Non-repeatable/phantom có thể xảy ra tùy DBMS |
| `REPEATABLE_READ` | Giữ tính lặp lại của việc đọc row theo chuẩn | Chi tiết phantom/MVCC và update conflicts phụ thuộc DBMS |
| `SERIALIZABLE` | Mục tiêu tương đương kết quả khi transactions chạy tuần tự | Có thể block/deadlock/serialization failure cần retry toàn bộ transaction |
| `DEFAULT` | Dùng mức default do database/connection quản lý | Không phải một mức cố định giữa các môi trường |

Không xem bảng như lời bảo đảm tuyệt đối cho mọi hiện tượng trong mọi database. Ví dụ PostgreSQL xử lý `READ_UNCOMMITTED` thực tế như `READ_COMMITTED`; các cơ chế snapshot và phantom của từng DBMS có thể khác cách mô tả tối thiểu của tiêu chuẩn SQL.

### 7.3. Ví dụ READ_COMMITTED

Giả sử một service đọc tổng tồn kho và sau đó đọc lại:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public InventoryView inspect(Long productId) {
    int before = inventoryRepository.available(productId);
    performAnotherDatabaseRead();
    int after = inventoryRepository.available(productId);
    return new InventoryView(before, after);
}
~~~

Nếu một transaction khác commit thay đổi stock giữa hai lần SELECT, ở một số DBMS với `READ_COMMITTED` giá trị `after` có thể khác `before`. **Persistence context L1 có thể làm kết quả phức tạp hơn** nếu repository dùng entity `find()` và trả lại managed object thay vì scalar query. Isolation và L1 loaded state là hai lớp riêng.

### 7.4. SERIALIZABLE và cơ chế retry

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void allocateUniqueSlot(Long slotId) {
    // Kiểm tra điều kiện rồi ghi, trong DB transaction.
}
~~~

Mức isolation cao hơn có thể khiến database trả serialization failure, lock timeout hoặc deadlock victim trong workload cạnh tranh. Không được chỉ bắt exception rồi tiếp tục trong transaction đã lỗi. Phần lớn cách xử lý đúng là **rollback toàn bộ attempt**, sau đó retry **toàn bộ unit of work** trong một transaction mới, nếu operation idempotent và retry policy phù hợp.

Không đặt retry tùy tiện bên trong cùng Hibernate Session/transaction đã gặp database failure. Dùng một orchestration boundary bên ngoài transactional method, backoff và giới hạn số lần retry, có thể kết hợp idempotency key.

## 8. Isolation chỉ có ý nghĩa khi tạo transaction mới

Giả sử outer service mở transaction:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    innerService.inner();
}
~~~

Inner method:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void inner() {
    // ...
}
~~~

Vì inner `REQUIRED` **tham gia transaction đã có**, nó không thể tự nâng physical transaction của outer thành `SERIALIZABLE` chỉ bằng annotation. Trong cấu hình mặc định thông thường, thuộc tính isolation của inner có thể không được áp dụng vì không có transaction mới.

Nếu muốn Spring kiểm tra mismatch giữa inner isolation/read-only settings và transaction hiện hữu, một số transaction managers hỗ trợ chế độ `validateExistingTransaction`. Điều đó giúp **từ chối cấu hình không phù hợp**, không tự đổi isolation giữa chừng.

### 8.1. REQUIRES_NEW có isolation riêng

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void isolatedWrite() {
    // Có physical transaction riêng theo manager/DB.
}
~~~

Ở đây Spring yêu cầu bắt đầu một transaction mới; isolation setting mới có cơ hội được áp dụng. Vẫn cần DBMS/driver hỗ trợ mức đó và hiểu chi phí khóa/serialization failures.

### 8.2. Isolation không phải cấu hình thay thế optimistic locking

Entity:

~~~java
@Entity
public class Product {
    @Id
    private Long id;

    @Version
    private long version;

    private int availableQuantity;
}
~~~

`@Version` giúp Hibernate phát hiện một số dạng concurrent update cùng entity. Nó là cơ chế optimistic concurrency của ORM, khác isolation level của DB transaction. Trong use case cập nhật tồn kho, có thể cần thêm atomic SQL update, pessimistic lock hoặc DB constraints để bảo vệ invariants.

Không chọn `SERIALIZABLE` như giải pháp mặc định cho mọi nghiệp vụ khi một quy tắc version/constraint cụ thể có thể hiệu quả và rõ ràng hơn.

## 9. Timeout: giới hạn thời gian của transaction

Spring cho phép khai báo timeout theo giây:

~~~java
@Transactional(timeout = 20)
public void recalculatePrices() {
    // ...
}
~~~

Khi Spring **tạo một transaction mới**, thuộc tính timeout được truyền cho transaction manager theo khả năng thực thi. Timeout không nên được hiểu là bộ hẹn giờ đảm bảo hủy ngay lập tức toàn bộ Java method khi đồng hồ chạm 20 giây.

### 9.1. Timeout của transaction khác query timeout

| Loại timeout | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Spring transaction timeout | Thời hạn của transaction do manager theo dõi | `@Transactional(timeout = 20)` |
| JPA/Hibernate query timeout | Thời gian một statement/query được phép chạy theo provider/driver | `query.setHint("jakarta.persistence.query.timeout", 5000)` |
| JDBC statement timeout | Driver/database statement execution duration | `Statement.setQueryTimeout(seconds)` |
| JDBC connection acquisition timeout | Thời gian chờ mượn connection từ pool | HikariCP `connectionTimeout` |
| Network/socket timeout | Thời gian chờ I/O network/driver | Driver-specific |
| HTTP request timeout | Thời hạn xử lý request ở web layer | Web server/gateway-specific |

Một request có thể vượt HTTP timeout nhưng DB transaction vẫn tiếp tục trong thread khác nếu hệ thống không chủ động hủy. Một DB statement có thể bị timeout trước Spring transaction timeout. Và một method đang chờ external HTTP call không được Spring transaction timeout tự ngắt chính xác như một thread-interrupt deadline.

### 9.2. Transaction timeout khi có REQUIRED lồng nhau

Outer:

~~~java
@Transactional(timeout = 60)
public void outer() {
    innerService.inner();
}
~~~

Inner:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    timeout = 5
)
public void inner() {
    // Tham gia outer physical transaction.
}
~~~

Khi inner tham gia transaction hiện hữu, nó **không thể bảo đảm áp một timeout vật lý mới chỉ riêng 5 giây**. Timeout setting tại inner chủ yếu có ý nghĩa khi inner **bắt đầu transaction mới**. Outer transaction deadline có thể tiếp tục chi phối việc thực thi SQL.

Nếu business cần một câu query phải hoàn thành trong 5 giây dù outer transaction cho phép lâu hơn, hãy đặt **query/statement timeout riêng** phù hợp và xử lý exception theo policy.

### 9.3. REQUIRES_NEW có timeout riêng

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeout = 10
)
public void writeAudit() {
    // Transaction riêng, deadline riêng theo manager.
}
~~~

Khi outer bị suspend, inner có thể nhận timeout 10 giây cho physical transaction mới. Điều này không ngăn inner bị chờ connection/lock tùy nơi timeout được enforce, vì cách áp timeout phụ thuộc manager, driver và JDBC calls.

### 9.4. Query timeout với JPA

~~~java
List<Product> products = em.createQuery(
        "select p from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setHint("jakarta.persistence.query.timeout", 5000)
    .getResultList();
~~~

Giá trị của `jakarta.persistence.query.timeout` được khai báo bằng **milliseconds** trong JPA query hint, khác `@Transactional(timeout = 20)` theo **seconds**. Query hint có thể được provider/dialect/driver hỗ trợ theo mức độ khác nhau; đọc log và kiểm thử trên DBMS thực tế.

Hibernate còn có API query-specific timeout theo giây:

~~~java
session.createQuery(
        "from Product p where p.status = :status",
        Product.class
    )
    .setParameter("status", ProductStatus.ACTIVE)
    .setTimeout(5)
    .getResultList();
~~~

Các APIs này không thay thế lẫn nhau một cách máy móc; xem semantics, units và exceptions của phiên bản Hibernate/JPA đang dùng.

### 9.5. Timeout là tín hiệu lỗi cần rollback an toàn

Khi query/transaction timeout khiến JDBC/Hibernate exception, transaction có thể bị đánh dấu rollback-only hoặc connection bị driver/DBMS đánh dấu lỗi. Không tiếp tục thực hiện thêm ORM operations trên cùng Session rồi cố commit “phần còn lại”.

Thông thường nên:

1. Để exception thoát khỏi transactional boundary hoặc chủ động đánh dấu rollback.
2. Rollback và kết thúc unit of work.
3. Ghi log có cấu trúc, có request correlation ID và thông tin query an toàn.
4. Retry trong **transaction mới** nếu operation idempotent và lỗi thuộc loại transient.
5. Xem lại index/query plan/locks/pool load để xử lý nguyên nhân.

Đừng chỉ tăng timeout rất lớn để che một query plan tệ hoặc transaction giữ locks quá lâu.

## 10. readOnly: gợi ý tối ưu, không phải chính sách rollback

~~~java
@Transactional(readOnly = true)
public ProductDetails loadDetails(Long id) {
    return repository.loadDetails(id);
}
~~~

`readOnly=true` là một **hint** cho transaction manager/provider. Với Hibernate, một số tích hợp Spring có thể điều chỉnh flush mode và read-only behavior để giảm overhead trong use case đọc. Nhưng nó **không có nghĩa** mọi database/driver sẽ từ chối mọi thao tác ghi, và không phải một biện pháp authorization hoặc data-protection tuyệt đối.

Ví dụ nguy hiểm nếu hiểu sai:

~~~java
@Transactional(readOnly = true)
public void accidentallyWrite(Long id) {
    repository.save(new AuditRecord(id));
}
~~~

Ứng dụng có thể gặp lỗi, không flush hoặc ghi tùy context/manager/DB, nhưng không nên dựa vào readOnly để thực thi invariant “method này không thể ghi”. Dùng quyền database, thiết kế API rõ và tests nếu cần read-only guarantee.

### 10.1. readOnly khi join transaction đã có

Một inner `@Transactional(readOnly = true, propagation = REQUIRED)` tham gia outer write transaction không nhất thiết biến physical transaction thành read-only. Ngược lại, inner write method tham gia outer read-only transaction có thể gặp điều kiện không phù hợp. Các settings của outer physical transaction thường quyết định thực tế; cơ chế validation phụ thuộc transaction manager.

### 10.2. Isolation, readOnly và timeout không cùng nghĩa

- Isolation kiểm soát cách nhìn dữ liệu giữa transactions.
- Read-only hint có thể tối ưu đường đọc.
- Timeout giới hạn thời gian.
- Propagation quyết định có transaction mới hay join.
- Rollback rules quyết định phản ứng với exception tại boundary.

Không dùng một lựa chọn để suy ra hành vi của các lựa chọn còn lại.

## 11. Rollback mặc định: RuntimeException/Error khác checked Exception

Một trong những lỗi nguy hiểm nhất khi tích hợp Spring transaction là mặc định cho rằng **hễ method ném bất kỳ Exception nào thì transaction sẽ rollback**. Với quy tắc mặc định phổ biến của Spring:

- Nếu method ném `RuntimeException` không bị bắt và exception đi qua transaction interceptor: **rollback**.
- Nếu method ném `Error`: **rollback**.
- Nếu method ném một checked `Exception` (không phải RuntimeException): Spring **không đánh dấu rollback chỉ dựa vào loại exception đó**, trừ khi có cấu hình rollback rule thích hợp hoặc transaction đã rollback-only vì nguyên nhân khác.

Ví dụ:

~~~java
public class PriceValidationException extends Exception {
    public PriceValidationException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional
public void updateThenValidate(Long productId)
        throws PriceValidationException {

    Product product = em.find(Product.class, productId);
    product.changePrice(new BigDecimal("999.00"));

    throw new PriceValidationException("Manual approval required");
}
~~~

Nếu đây là một checked exception thoát ra khỏi proxy và không có rule bổ sung, interceptor theo default Spring có thể **commit** transaction khi method ném exception. Việc caller nhận exception **không chứng minh database đã rollback**.

Tất nhiên, nếu persistence layer đã gặp constraint failure và transaction bị mark rollback-only từ trước thì commit vẫn có thể thất bại. Rollback rule ở cấp method không thể “cứu” một DB transaction đã bị đánh dấu không thể commit.

### 11.1. Minh họa bảng hành vi mặc định

| Kết thúc method | Spring rollback rule mặc định | Ghi chú |
| --- | --- | --- |
| Return bình thường | Thử commit nếu transaction do boundary sở hữu | Có thể thất bại lúc flush/commit |
| `IllegalArgumentException` | Rollback | Unchecked `RuntimeException` |
| `IllegalStateException` | Rollback | Unchecked |
| `DataIntegrityViolationException` | Rollback | Spring DataAccessException là runtime |
| `OptimisticLockException` | Rollback | Jakarta Persistence runtime exception |
| `IOException` | Không tự rollback chỉ vì loại checked exception | Cần `rollbackFor` nếu domain muốn rollback |
| Domain checked `Exception` | Không tự rollback theo default | Cần explicit rule |
| `Error` | Rollback | Lỗi nghiêm trọng, không nên swallow |

Bảng giả định method thật sự đi qua Spring transactional interceptor. Nếu annotation không được áp dụng vì self-invocation, không thể dùng bảng để dự đoán boundary.

## 12. Định nghĩa rollbackFor và noRollbackFor

### 12.1. Rollback với checked exception

~~~java
@Transactional(
    rollbackFor = StockAllocationException.class
)
public void placeOrder(PlaceOrderCommand command)
        throws StockAllocationException {

    orders.save(new Order(command));
    stockAllocator.reserve(command.productId(), command.quantity());

    // Nếu reserve ném checked StockAllocationException,
    // Spring rollback transaction vì rollbackFor.
}
~~~

Exception:

~~~java
public class StockAllocationException extends Exception {
    public StockAllocationException(String message) {
        super(message);
    }
}
~~~

Không cần biến mọi domain exception thành RuntimeException chỉ để có rollback nếu checked exception có ý nghĩa ở API của bạn. Dùng `rollbackFor` cho trường hợp nghiệp vụ cần atomicity.

Có thể khai báo nhiều loại:

~~~java
@Transactional(
    rollbackFor = {
        StockAllocationException.class,
        ExternalValidationException.class
    }
)
public void process() throws StockAllocationException,
                             ExternalValidationException {
    // ...
}
~~~

### 12.2. Không rollback với một loại ngoại lệ được chấp nhận

~~~java
@Transactional(
    noRollbackFor = DuplicateRequestException.class
)
public void acceptRequest(String requestId) {
    requestRepository.markSeen(requestId);

    if (requestRepository.alreadyProcessed(requestId)) {
        throw new DuplicateRequestException(requestId);
    }
}
~~~

Nếu `DuplicateRequestException` là một RuntimeException **chỉ biểu diễn một kết quả nghiệp vụ không làm hỏng transaction**, `noRollbackFor` có thể cho phép những thay đổi hợp lệ trước đó được commit. Nhưng ví dụ phải được cân nhắc: nếu “đã xử lý” là việc kiểm tra idempotency, tốt hơn có thể trả kết quả nghiệp vụ bình thường thay vì ném exception.

**Không dùng noRollbackFor trên lỗi persistence nghiêm trọng** để cố ép commit:

~~~java
// Không khuyến khích:
@Transactional(noRollbackFor = DataIntegrityViolationException.class)
public void unsafeWrite() {
    repository.save(...);
}
~~~

Với constraint violation, database hoặc Hibernate Session có thể đã ở trạng thái không an toàn, transaction có thể rollback-only; `noRollbackFor` không biến trạng thái đó thành transaction lành mạnh. Hãy rollback và dùng unit of work mới.

### 12.3. Quy tắc type-safe nên ưu tiên

Ưu tiên:

~~~java
@Transactional(
    rollbackFor = PaymentRejectedException.class,
    noRollbackFor = CustomerAlreadyNotifiedException.class
)
~~~

hơn các thuộc tính dựa trên tên như `rollbackForClassName` và `noRollbackForClassName`, vì dạng dựa trên class giúp refactoring và giảm nhập nhằng.

Spring hỗ trợ pattern-based rules:

~~~java
@Transactional(rollbackForClassName = "com.example.sales.BusinessException")
~~~

Pattern matching có thể khớp theo **substring của tên class exception**, không phải biểu thức regular expression có ranh giới package/type nghiêm ngặt. Pattern quá chung như `"Exception"` có thể bắt nhiều ngoại lệ ngoài ý muốn, kể cả classes có tên lồng nhau hoặc suffix. Nếu có thể, dùng `rollbackFor = SomeException.class`.

### 12.4. Khi có nhiều rule cùng khớp

Spring chọn rule khớp mạnh nhất/đặc hiệu nhất theo cơ chế rule matching. Tuy nhiên một hierarchy exception phức tạp và các patterns chồng nhau rất khó đọc. Nên giữ policy đơn giản:

- Dùng domain exception hierarchy có chủ đích.
- Dùng class-based rules.
- Tránh khai báo `rollbackFor = Exception.class` rồi thêm hàng loạt `noRollbackFor` mâu thuẫn nếu có thể thiết kế API rõ hơn.
- Kiểm tra những đường lỗi quan trọng bằng integration tests.

## 13. UnexpectedRollbackException: inner REQUIRED đã đánh dấu rollback-only

Tình huống thường gây bất ngờ:

~~~java
@Service
public class OuterService {
    private final InnerService inner;
    private final OrderRepository orders;

    @Transactional
    public void execute() {
        orders.save(new Order(...));

        try {
            inner.doSomething();
        } catch (IllegalStateException ex) {
            // Caller tưởng bắt lỗi xong vẫn commit được.
        }

        orders.save(new Order(...));
    }
}
~~~

Inner:

~~~java
@Service
public class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void doSomething() {
        throw new IllegalStateException("Something failed");
    }
}
~~~

Diễn biến:

1. Outer mở physical transaction A.
2. Inner `REQUIRED` tham gia A.
3. Inner ném `IllegalStateException` qua transactional interceptor của InnerService.
4. Interceptor áp rule rollback và **đánh dấu transaction A rollback-only**.
5. Outer bắt exception rồi return bình thường.
6. Outer interceptor cố commit A.
7. Vì A rollback-only, Spring rollback và có thể ném `UnexpectedRollbackException` để báo cho caller rằng commit không xảy ra.

~~~mermaid
flowchart TD
    A["Outer REQUIRED: mở TX A"] --> B["Inner REQUIRED: tham gia TX A"]
    B --> C["Inner ném RuntimeException"]
    C --> D["Interceptor inner đánh dấu A rollback-only"]
    D --> E["Outer bắt exception"]
    E --> F["Outer return bình thường"]
    F --> G["Commit A?"]
    G --> H["Rollback vì rollback-only"]
    H --> I["UnexpectedRollbackException"]
~~~

**Tại sao Spring không âm thầm commit một phần?** Vì outer caller tin rằng method return bình thường đồng nghĩa transaction đã commit. Nếu một participant đã yêu cầu rollback, framework phải bảo vệ tính đúng đắn bằng cách không giả vờ commit thành công.

### 13.1. Các hướng xử lý đúng

- Nếu lỗi là thất bại của toàn bộ use case: **để exception propagate**, rollback một lần tại boundary ngoài.
- Nếu bước con phải rollback độc lập và outer vẫn tiếp tục: cân nhắc `REQUIRES_NEW`, với chi phí connection/locking và semantics commit riêng.
- Nếu chỉ cần kết quả “không đủ điều kiện” mà không nên rollback: trả kết quả domain (enum/result object), thay vì dùng RuntimeException để biểu diễn mọi nhánh bình thường.
- Nếu JPA operation đã thất bại thực sự: không tiếp tục cùng transaction, rollback và xử lý bằng transaction mới.
- Nếu cần rollback một bước JDBC trong cùng outer: cân nhắc `NESTED`/savepoint khi manager hỗ trợ, không nhầm với JPA nested.

### 13.2. Bắt exception ở đâu tạo khác biệt?

Nếu exception được **ném và bắt hoàn toàn trong cùng một method**, nó có thể không đi qua interceptor cho scope con nào cả:

~~~java
@Transactional
public void execute() {
    try {
        validateBusinessRule();
    } catch (DomainWarning ex) {
        // Interceptor chỉ thấy execute() return bình thường.
    }
}
~~~

Khi method return bình thường, Spring áp commit theo default nếu transaction không bị đánh dấu rollback-only từ nguyên nhân khác. Nếu cần rollback trong trường hợp này, hãy để exception phù hợp đi qua transactional boundary hoặc chủ động đánh dấu rollback-only.

Nhưng **đừng dùng catch rồi commit sau Hibernate/JDBC exception**: provider/DB có thể đã đánh dấu transaction lỗi hoặc persistence context bị mất nhất quán.

## 14. Chủ động đánh dấu rollback-only

Có những tình huống không muốn ném exception ra ngoài API nhưng vẫn cần hủy transaction. Spring cung cấp:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public OperationResult tryUpdate(Long id) {
    Product product = em.find(Product.class, id);

    if (!mayChange(product)) {
        TransactionAspectSupport
                .currentTransactionStatus()
                .setRollbackOnly();

        return OperationResult.rejected();
    }

    product.changePrice(new BigDecimal("199.00"));
    return OperationResult.accepted();
}
~~~

`setRollbackOnly()` báo cho transaction status hiện tại rằng transaction không được commit. Nó khác `em.clear()` hay `em.detach()`: những API JPA đó thay đổi persistence context, không tương đương rollback physical transaction.

### 14.1. Cần phân biệt local và global rollback-only

Một outer transaction tự đặt rollback-only có thể được rollback khi method kết thúc; một inner participant đánh dấu physical transaction rollback-only có thể khiến outer nhận `UnexpectedRollbackException` khi nó cố commit. Cách exception được báo phụ thuộc transaction manager và vị trí đánh dấu rollback.

### 14.2. Tại sao không lạm dụng API này?

Nó tạo coupling với Spring transaction infrastructure và dễ làm caller nhầm rằng return bình thường nghĩa là ghi thành công. Với workflow thông thường, ném domain exception có rollback rule rõ ràng hoặc trả một result không ghi gì từ đầu có thể dễ hiểu hơn.

Chỉ dùng programmatic rollback khi business contract thực sự yêu cầu, và test đầy đủ rằng DB không commit.

## 15. Proxy và self-invocation: @Transactional có thể không chạy

Spring thường dùng AOP proxy để chặn lời gọi phương thức. Điều này tạo một giới hạn nổi tiếng: **gọi một method có @Transactional thông qua `this` trong cùng object thường không đi qua proxy**, nên annotation trên method được gọi không kích hoạt một transaction boundary mới.

~~~java
@Service
public class InvoiceService {

    public void processBatch() {
        // Gọi trực tiếp bên trong cùng object: bỏ qua proxy interception
        // của processOne() ở chế độ Spring AOP proxy mặc định.
        processOne();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void processOne() {
        // Không chắc được tạo transaction mới trong self-invocation.
    }
}
~~~

Nếu `processBatch()` được gọi từ bên ngoài qua proxy nhưng không annotated, self-invocation vẫn không làm `processOne()` nhận interceptor mới.

### 15.1. Tách ra service bean khác

~~~java
@Service
public class InvoiceItemService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void processOne(InvoiceItem item) {
        // ...
    }
}
~~~

~~~java
@Service
public class InvoiceBatchService {
    private final InvoiceItemService items;

    public InvoiceBatchService(InvoiceItemService items) {
        this.items = items;
    }

    public void processBatch(List<InvoiceItem> input) {
        for (InvoiceItem item : input) {
            items.processOne(item);  // Đi qua Spring bean proxy.
        }
    }
}
~~~

Đây chỉ là cách minh họa transactional boundary. Trong sản xuất, tạo một transaction riêng cho mỗi item có thể rất tốn connection, commit, lock, latency; nên chọn chunk size và batch processing theo workload.

### 15.2. Các trường hợp thường khiến annotation không có hiệu lực

- Method không được gọi qua Spring-managed proxy.
- Self-invocation qua `this.method()`.
- Đối tượng được tạo bằng `new` chứ không do Spring container quản lý.
- Private method không được proxy interception hỗ trợ theo cách thông thường.
- Final class/method hạn chế subclass-based proxy, tùy proxy strategy.
- Annotation gọi khi bean chưa qua proxy/lifecycle initialization.
- Async code chạy ở thread khác không kế thừa transaction thread-bound mặc định.
- Một bean được cấu hình vào transaction manager không phù hợp, hoặc nhiều managers nhưng không chọn đúng manager.

Spring có AspectJ weaving mode có thể xử lý một số tình huống self-invocation khác proxy mode, nhưng nó cần cấu hình/weaving phù hợp. Đừng mặc định dự án đang dùng AspectJ chỉ vì có dependency Spring AOP.

## 16. Transaction rollback không đồng nghĩa Hibernate Session luôn dùng tiếp được

Khi Hibernate/JDBC gặp lỗi như:

- SQL constraint violation.
- Optimistic lock failure.
- JDBC connection failure.
- Invalid DML/SQL.
- PersistenceException trong quá trình flush.
- Một số transaction/query timeouts.

Persistence context có thể không còn đáng tin để tiếp tục unit of work. Spring transaction interceptor sẽ rollback theo rule nếu exception thoát phù hợp, nhưng **không nên bắt một Hibernate persistence failure rồi tiếp tục sử dụng Session đã lỗi trong cùng transaction**.

Ví dụ không nên:

~~~java
@Transactional
public void unsafe() {
    try {
        repository.saveAndFlush(new EntityWithInvalidData());
    } catch (DataIntegrityViolationException ex) {
        // Không tiếp tục sửa entity khác rồi cố commit
        // trong cùng Session/transaction bị lỗi.
    }

    repository.save(new AnotherEntity());
}
~~~

Khi constraint violation đã xảy ra, DB transaction có thể ở trạng thái aborted (ví dụ PostgreSQL); Hibernate Session snapshots cũng có thể không còn phù hợp. Một `noRollbackFor` không làm transaction trở lại lành mạnh.

Hướng an toàn:

1. Cho exception propagate hoặc rollback transaction hiện tại.
2. Bỏ persistence context/Session bị ảnh hưởng theo lifecycle do framework quản lý.
3. Nếu cần fallback, thực hiện **trong transaction mới** sau rollback.
4. Chỉ retry lỗi transient có chính sách retry và idempotency thích hợp.

Với một lỗi validation thuần Java trước khi có Hibernate failure, việc chọn rollback hay return kết quả phụ thuộc domain policy; không áp dụng quy tắc “Session hỏng” cho mọi RuntimeException đơn giản.

## 17. TransactionManager nào đang thực thi annotation?

`@Transactional` chỉ là mô tả. Spring cần một `PlatformTransactionManager` hoặc `ReactiveTransactionManager` phù hợp với loại operation.

### 17.1. JpaTransactionManager

Trong ứng dụng Hibernate/JPA blocking thông thường, `JpaTransactionManager` điều phối transaction của `EntityManager`. Nó thường được Spring Boot tự cấu hình khi có JPA và datasource phù hợp.

~~~java
@Bean
PlatformTransactionManager transactionManager(
        EntityManagerFactory entityManagerFactory
) {
    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Snippet này là minh họa cơ chế, không phải yêu cầu khai báo bean thủ công trong mọi Spring Boot app. Nếu autoconfiguration đã cung cấp manager, thêm bean trùng có thể gây conflict.

### 17.2. DataSourceTransactionManager

`DataSourceTransactionManager` thường dùng khi làm việc với JDBC trên một `DataSource`. Nó hỗ trợ JDBC savepoints qua `NESTED` khi driver/database hỗ trợ và manager cho phép. Nhưng không nên thay `JpaTransactionManager` bằng JDBC manager trong một ứng dụng JPA rồi mong mọi entity lifecycle/flush tự phối hợp như cũ.

### 17.3. JtaTransactionManager

`JtaTransactionManager` dùng khi phối hợp JTA transactions và các resources được đăng ký phù hợp. Nó có semantics khác local JDBC transaction, và không phải giải pháp mặc định cho mọi ứng dụng Spring Boot dùng một database.

Không coi `REQUIRES_NEW` là distributed transaction. Dù manager là JTA, phối hợp HTTP API hoặc broker cần resource enrollment/consistency mechanism riêng.

### 17.4. Nhiều transaction managers

Nếu có nhiều data sources/persistence units, phải xác định đúng manager:

~~~java
@Transactional(
    transactionManager = "ordersTransactionManager",
    propagation = Propagation.REQUIRED
)
public void updateOrder() {
    // ...
}
~~~

Tên bean trong ví dụ phải tồn tại và được cấu hình đúng. Một transaction manager chỉ quản lý resources tương ứng; dùng annotation với manager A không tự gom các DB operations do manager B quản lý vào cùng atomic transaction.

## 18. Phối hợp transaction với Hibernate flush và query

Hibernate giữ managed entity state trong persistence context. `@Transactional` tạo boundary nhưng không có nghĩa mọi thay đổi được ghi vào DB ngay tại setter.

~~~java
@Transactional
public void increasePrice(Long id) {
    Product product = em.find(Product.class, id);
    product.changePrice(product.getPrice().add(
            new BigDecimal("10.00")
    ));
    // Hibernate có thể UPDATE khi flush/commit.
}
~~~

### 18.1. Flush khác commit

- **Flush:** đẩy pending SQL changes của persistence context vào DB trong transaction hiện tại.
- **Commit:** xác nhận transaction theo DB semantics.
- **Rollback:** hủy thay đổi DB thuộc transaction chưa commit.
- **Clear:** detach entities khỏi persistence context; không phải commit.
- **Refresh:** tải lại state của managed entity; không phải rollback của cả transaction.

~~~java
@Transactional
public void demo(Long id) {
    Product p = em.find(Product.class, id);
    p.changePrice(new BigDecimal("200.00"));

    em.flush(); // Có thể phát UPDATE ngay, nhưng chưa commit.
    // Nếu exception xảy ra và transaction rollback, UPDATE bị rollback.
}
~~~

Flush có thể ném constraint/optimistic-lock exceptions. Nếu thất bại, rollback transaction và kết thúc unit of work; không bắt rồi tiếp tục dùng cùng Session.

### 18.2. Timeout/locking có thể xảy ra lúc flush hoặc commit

Một method chạy SQL SELECT nhanh nhưng đến commit mới phát UPDATE có thể gặp lock wait, deadlock hoặc optimistic lock conflict. Vì vậy exception có thể xuất hiện **sau khi method body đã return**, tại interceptor commit/flush phase. Nếu caller đặt try/catch **bên trong method** quanh repository call nhưng flush xảy ra sau đó, catch đó sẽ không xử lý được lỗi commit.

Thiết kế exception translation/retry ở ranh giới **bên ngoài transactional method** khi cần xử lý toàn bộ transaction attempt.

## 19. @Async, thread boundary và reactive transactions

Spring imperative transactions thường được liên kết với execution thread và resources của transaction manager. Do đó:

~~~java
@Transactional
public void outer() {
    asyncWorker.runAsync();
}
~~~

một method `@Async` chạy ở thread khác **không tự kế thừa** transactional EntityManager/physical transaction của outer. Nếu async worker cần DB atomicity, nó phải có transaction boundary riêng trong thread của nó (qua Spring proxy).

Điều tương tự áp dụng khi tự tạo `Thread`, `CompletableFuture.supplyAsync` hoặc Executor tasks mà không có transaction context propagation được thiết kế.

### 19.1. Không dùng JPA/Hibernate Session đồng thời giữa threads

`EntityManager`/`Session` là persistence context stateful và không thread-safe. Không truyền một managed entity graph rồi dùng lazy associations/flush từ thread khác với kỳ vọng cùng transaction. Truyền immutable DTOs/IDs và tải trong transaction mới khi phù hợp.

### 19.2. ReactiveTransactionManager là một mô hình khác

Trong Spring reactive stack, `ReactiveTransactionManager` truyền transaction context theo reactive context, không theo mô hình ThreadLocal imperative thuần túy. Hibernate ORM/JPA blocking thông thường không tự trở thành reactive vì return `Mono`/`Flux`. Nếu ứng dụng dùng JPA blocking, dùng transaction manager và execution model phù hợp, không trộn reactive semantics một cách ngẫu nhiên.

## 20. Timeout, isolation và propagation khi nested calls: bảng tổng hợp

Giả sử outer đã có physical transaction A với isolation READ_COMMITTED và timeout 30 giây.

| Inner method | Physical transaction | Isolation/timeout của inner có tạo rule mới không? | Nếu inner lỗi? |
| --- | --- | --- | --- |
| `REQUIRED` | Tham gia A | Thông thường không thay đổi isolation/deadline của A | Có thể đánh dấu A rollback-only |
| `SUPPORTS` | Tham gia A | Không tạo transaction mới | Exception xử lý theo transactional scope, có thể ảnh hưởng A |
| `MANDATORY` | Tham gia A | Không tạo transaction mới | Có thể ảnh hưởng A |
| `REQUIRES_NEW` | Suspend A, mở B | Có thể áp isolation/timeout mới trên B | B rollback riêng; A còn tùy caller |
| `NESTED` | Savepoint trong A nếu manager hỗ trợ | Thường không có physical isolation riêng | Rollback về savepoint; A vẫn do outer quyết định |
| `NOT_SUPPORTED` | Suspend A, chạy ngoài transaction A | Không có inner physical transaction do scope này tạo | Không tự rollback A, nhưng caller xử lý exception |
| `NEVER` | Có A nên ném exception | Không chạy body | Outer có thể rollback nếu exception đi qua boundary |

Bảng không thay thế các chi tiết của `PlatformTransactionManager` cụ thể. Với JPA, đặc biệt không coi `NESTED` là mặc định được hỗ trợ.

## 21. Tình huống nghiệp vụ: một đặt hàng và một bản ghi audit độc lập

Xem một thiết kế đơn giản:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryService stock;
    private final AuditService audit;

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 20,
        rollbackFor = StockAllocationException.class
    )
    public Long place(PlaceOrderCommand command)
            throws StockAllocationException {

        Order order = orders.save(Order.from(command));
        stock.reserve(command.productId(), command.quantity());

        audit.recordAttempt(order.getId(), "STOCK_RESERVED");
        return order.getId();
    }
}
~~~

Giả sử `stock.reserve` cùng `REQUIRED`, còn `audit.recordAttempt` là `REQUIRES_NEW`.

**Các khả năng:**

- Stock reservation trả bình thường, audit commit riêng, outer commit: cả order và audit tồn tại.
- Stock reservation ném checked `StockAllocationException`: outer rollback vì `rollbackFor`; audit chưa được gọi.
- Audit ném runtime exception và không được bắt: inner B rollback, exception đi ra outer, khiến outer A rollback theo default.
- Audit ném một lỗi có thể chấp nhận và outer bắt theo hợp đồng: outer A có thể vẫn commit; cần xác định tính độc lập và các dấu hiệu thất bại rõ ràng.
- Outer bị timeout sau khi audit B đã commit: audit có thể tồn tại nhưng order bị rollback. Đây là hậu quả **có chủ đích** nếu audit ghi nhận attempt, nhưng không phù hợp nếu audit ngụ ý đơn hàng chắc chắn hoàn tất.

### 21.1. Đừng dùng REQUIRES_NEW cho mọi bước

Nếu mọi method đều `REQUIRES_NEW`, một use case có thể commit stock, commit order và commit audit ở các thời điểm khác nhau. Khi bước cuối lỗi, các bước trước đã commit và không thể rollback như một unit. Đây có thể trở thành lỗi nghiêm trọng về atomicity.

**Phần lớn các thao tác ghi phải thành công cùng nhau nên ở cùng REQUIRED transaction.** Dùng `REQUIRES_NEW` chỉ khi chính sách nghiệp vụ thực sự chấp nhận/đòi hỏi commit độc lập.

### 21.2. External payment capture

Nếu cần gọi payment provider, hãy phân biệt:

1. Ghi database transaction.
2. Gọi API thanh toán ngoài.
3. Publish event/message.
4. Xác nhận kết quả và xử lý retry/idempotency.

Không đặt một network call dài trong DB transaction mà không cân nhắc locks, timeout và connection usage. Một workflow bất đồng bộ với outbox/saga có thể phù hợp hơn trong production.

## 22. Ngoại lệ checked, unchecked và kết quả domain

Thiết kế exception hierarchy ảnh hưởng transaction rules. Ví dụ:

~~~java
public class OrderRejectedException extends Exception {
    public OrderRejectedException(String message) {
        super(message);
    }
}

public class InvalidOrderStateException extends RuntimeException {
    public InvalidOrderStateException(String message) {
        super(message);
    }
}
~~~

- `OrderRejectedException` là checked; nếu muốn mọi thao tác trước nó rollback, khai báo `rollbackFor`.
- `InvalidOrderStateException` là unchecked; mặc định dẫn đến rollback khi thoát ra khỏi interceptor.
- Một exception được ném vì **điều kiện nghiệp vụ bình thường** đôi khi nên thay bằng typed result, tránh dùng transaction rollback như control flow thường xuyên.
- Nếu exception xảy ra trước khi có bất kỳ thay đổi DB nào, rollback có thể không phát SQL DML; nó vẫn giúp đảm bảo boundary nhất quán.
- Không dựa vào tên exception có chữ `Validation` hay `Business` để xác định mặc định Spring rollback hay không; điều quan trọng là **class kế thừa checked hay unchecked và rules được khai báo**.

### 22.1. Exception translation của Spring

Spring Data/JPA repository có thể chuyển một số persistence exceptions thành hierarchy `org.springframework.dao.DataAccessException`, vốn là runtime exceptions. Ví dụ `DataIntegrityViolationException`, `OptimisticLockingFailureException`. Những exception này thường kích hoạt rollback default khi thoát ra khỏi transactional interceptor.

Không cần thêm `rollbackFor = RuntimeException.class` ở tất cả methods chỉ để có chính sách mặc định đó.

### 22.2. Commit có thể thất bại mà method không ném gì

~~~java
@Transactional
public void create() {
    repository.save(new Entity(...));
    // Chưa chắc SQL INSERT đã flush.
}
~~~

Nếu lỗi uniqueness được phát hiện khi flush tại commit, method body đã chạy hết nhưng transaction vẫn fail. Caller của proxy có thể nhận `DataIntegrityViolationException` hoặc exception khác từ commit phase. Vì vậy test rollback phải quan sát dữ liệu sau transaction, không chỉ kiểm tra method body đã throw hay chưa.

## 23. Retry phải bao ngoài một transaction attempt

Một lỗi phổ biến:

~~~java
@Transactional
public void unsafeRetry() {
    try {
        repository.saveAndFlush(...);
    } catch (DataAccessException ex) {
        repository.saveAndFlush(...); // Thử lại trong cùng TX lỗi.
    }
}
~~~

Cách này rủi ro vì JDBC transaction/Session có thể đã bị đánh dấu rollback-only. Nếu cần retry lỗi transient như serialization failure/deadlock, cấu trúc đúng thường là:

~~~text
Retry orchestration (bên ngoài TX)
  -> Attempt 1: transactionalService.execute() -> rollback/fail
  -> Backoff
  -> Attempt 2: transactionalService.execute() -> TX mới
  -> ...
~~~

Ví dụ minh họa:

~~~java
@Service
public class RetryCoordinator {
    private final TransactionalOrderService orders;

    public RetryCoordinator(TransactionalOrderService orders) {
        this.orders = orders;
    }

    public void executeWithRetry(OrderCommand command) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                orders.executeOnce(command); // Spring proxy tạo TX mới.
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }
                // Thực tế thêm backoff + jitter nếu phù hợp.
            }
        }
    }
}
~~~

`TransactionalOrderService.executeOnce` phải là method transactional của **bean khác** được gọi qua proxy. `TransientDataAccessException` là một nhóm lỗi Spring DAO; không phải mọi lỗi trong nhóm đều có thể retry mù quáng. Cần phân biệt exception cause/database SQLSTATE và bảo đảm operation idempotent.

Nếu dùng `@Retryable` từ Spring Retry, thứ tự interceptors giữa retry và transaction cũng quan trọng: mục tiêu là **mỗi attempt có transaction mới**, không phải tất cả attempts dùng cùng một physical transaction. Cần kiểm chứng cấu hình AOP order bằng integration tests.

## 24. Kiểm thử propagation và rollback bằng integration tests

Unit test mock repository không chứng minh rollback thật vì mock không có database transaction. Với các chính sách quan trọng, dùng integration test với datasource/DBMS phù hợp.

### 24.1. Test checked exception và rollbackFor

Ví dụ service:

~~~java
@Service
public class ShipmentService {
    private final ShipmentRepository shipments;

    public ShipmentService(ShipmentRepository shipments) {
        this.shipments = shipments;
    }

    @Transactional(rollbackFor = ShippingRejectedException.class)
    public void createAndFail(String reference)
            throws ShippingRejectedException {
        shipments.save(new Shipment(reference));
        throw new ShippingRejectedException("Carrier rejected");
    }
}
~~~

Test ý tưởng:

~~~java
@SpringBootTest
class ShipmentTransactionIT {

    @Autowired ShipmentService shipmentService;
    @Autowired ShipmentRepository shipmentRepository;

    @Test
    void checked_exception_rolls_back_when_configured() {
        assertThrows(
            ShippingRejectedException.class,
            () -> shipmentService.createAndFail("SHIP-501")
        );

        assertFalse(
            shipmentRepository.existsByReference("SHIP-501")
        );
    }
}
~~~

Không đặt `@Transactional` bừa bãi lên chính test method nếu mục tiêu là quan sát commit/rollback của service; Spring test transaction có thể bao toàn bộ test và rollback mặc định, che lỗi service đã commit nhầm.

Một integration test cần schema/database cô lập, cleanup phù hợp và gọi service qua Spring proxy thật. Annotation `@SpringBootTest` và `@Autowired` đến từ Spring Boot/Test; `@Test` từ JUnit Jupiter.

### 24.2. Test REQUIRES_NEW

Tạo outer method có thay đổi A, gọi inner method audit B với `REQUIRES_NEW`, sau đó outer ném unchecked exception. Sau khi call kết thúc:

- A **không tồn tại** (outer rollback).
- B **vẫn tồn tại** nếu inner commit và không bị DB logic khác tác động.

Cần quan sát rows trong một EntityManager/transaction mới để không đọc lại stale L1 state.

### 24.3. Test inner REQUIRED và UnexpectedRollbackException

Inner `REQUIRED` ném runtime exception; outer bắt rồi return. Assert ở outer proxy boundary rằng transaction không commit và nhận `UnexpectedRollbackException` theo manager configuration. Dùng hai Spring beans để chắc chắn call đi qua hai interceptors.

### 24.4. Test isolation và timeout

- Isolation: dùng **hai physical transactions/threads** và đồng bộ bằng latches để tạo tình huống concurrent read/write; không kết luận từ một EntityManager duy nhất.
- Timeout: dùng workload/query có giới hạn kiểm soát trên DBMS cụ thể, xác nhận exception/rollback; tránh test dựa vào `Thread.sleep()` rồi giả định Spring sẽ interrupt method đúng deadline.
- NESTED: dùng datasource/driver hỗ trợ savepoint, kiểm chứng một nhánh rollback nhưng outer commit, đồng thời **không** giả định Hibernate EntityManager được rewind.
- Pool: đo behavior của `REQUIRES_NEW` khi outer giữ connection và nhiều threads đồng thời, nếu throughput/capacity quan trọng.

## 25. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Method annotated nhưng không rollback | Self-invocation hoặc bean không qua proxy | Gọi qua bean được quản lý hoặc thiết kế lại boundary |
| Checked exception xảy ra nhưng dữ liệu vẫn commit | Default rollback chỉ cho RuntimeException/Error | Dùng `rollbackFor` phù hợp |
| Outer bắt inner exception nhưng commit ném UnexpectedRollbackException | Inner REQUIRED đã mark transaction chung rollback-only | Không swallow lỗi; đổi business flow/propagation đúng |
| `REQUIRES_NEW` không tạo transaction mới | Annotation bị self-invocation; proxy không chặn | Tách bean/proxy hoặc dùng TransactionTemplate |
| Pool cạn connection khi dùng REQUIRES_NEW | Outer giữ connection, inner mượn thêm | Giảm nesting/transaction duration, sizing pool |
| `NESTED` báo không hỗ trợ | Manager/driver không có savepoint/nested support | Dùng JDBC manager có hỗ trợ hoặc thiết kế khác |
| Rollback-to-savepoint nhưng entity JPA vẫn stale | Persistence context không rewind theo JDBC savepoint | Không dùng nested JPA như nested entity state |
| Inner isolation không có tác dụng | REQUIRED tham gia transaction outer | Đặt isolation ở outer hoặc tạo TX mới có chủ đích |
| Method quá timeout nhưng vẫn chạy Java code | Timeout không phải hard thread deadline | Kiểm tra manager, JDBC statement timeout và boundaries |
| `readOnly=true` vẫn thấy thay đổi hoặc lỗi ghi | Read-only thường là hint/tối ưu | Dùng DB privileges/API contract/validation |
| Catch DataIntegrityViolationException rồi save tiếp lỗi | Transaction/Session sau JDBC failure không an toàn | Rollback và dùng transaction mới |
| Update xuất hiện trước commit | Hibernate auto-flush hoặc explicit flush | Phân biệt flush và commit |
| @Async không thấy transaction outer | Thread-bound context không tự truyền | Tạo boundary riêng trong async bean |
| Retry không hoạt động đúng | Retry nằm trong transaction hoặc cùng Session lỗi | Đặt retry orchestration ngoài transactional method |
| Hai datasources nhưng @Transactional chỉ bảo vệ một | Chọn sai transaction manager | Chỉ định manager và resource ownership |
| @Transactional trên private/final method không hiệu lực | Proxy interception bị giới hạn | Chọn public method/bean, xác nhận proxy mode |
| Serializable gây serialization failure | Concurrency conflict do DB | Rollback và retry trong TX mới nếu an toàn |

## 26. Checklist thiết kế transaction cho service Hibernate

1. **Xác định atomic unit of work:** những DB writes nào bắt buộc cùng commit/rollback?
2. **Đặt transaction ở service boundary**, không đặt mọi method theo cảm tính.
3. **Ưu tiên REQUIRED** khi những bước ghi phải thành công cùng nhau.
4. **Chỉ dùng REQUIRES_NEW khi thật sự cần commit độc lập** và chấp nhận hậu quả khi outer rollback.
5. **Không giả định NESTED hoạt động với JPA EntityManager** như với JDBC savepoints.
6. **Chọn isolation theo invariant và khả năng DBMS**, không mặc định SERIALIZABLE cho mọi truy vấn.
7. **Dùng @Version/locking/constraints khi cần chống lost updates**, thay vì chỉ dựa vào isolation.
8. **Đặt timeout có chủ đích** và phân biệt transaction/query/pool/network timeouts.
9. **Phân loại exceptions**: checked, unchecked, database failures và domain outcomes.
10. **Khai báo rollbackFor cho checked exception** nếu cần hủy toàn bộ unit of work.
11. **Không dùng noRollbackFor để tiếp tục sau persistence error nghiêm trọng.**
12. **Đừng swallow inner REQUIRED exception** khi nó đã đánh dấu rollback-only.
13. **Kiểm tra lời gọi đi qua transactional proxy**, nhất là self-invocation và async.
14. **Chỉ retry trong transaction mới** khi operation idempotent và lỗi thực sự transient.
15. **Tách external I/O khỏi DB atomicity** bằng outbox/saga/idempotency khi cần.
16. **Kiểm thử commit/rollback trên database thật** với hai transaction contexts khi kiểm tra isolation.
17. **Quan sát SQL/flush/connection pool metrics** để biết vì sao transaction chậm hoặc bị timeout.
18. **Giữ Session/EntityManager ở scope phù hợp**, không tái sử dụng một context đã gặp lỗi nghiêm trọng.

## 27. Bài tập thực hành

### Bài 1 — REQUIRED

Một `CheckoutService` dùng `REQUIRED` gọi `StockService` cũng dùng `REQUIRED`. StockService ném `IllegalStateException`. Cả hai cùng dùng một `JpaTransactionManager`. Giải thích physical transaction nào sẽ rollback và vì sao.

### Bài 2 — REQUIRES_NEW

Một outer method tạo order, inner `REQUIRES_NEW` ghi audit rồi commit, sau đó outer ném RuntimeException. Hỏi order và audit có thể tồn tại như thế nào sau lỗi? Điều gì đổi nếu exception của inner được propagate ra outer?

### Bài 3 — NESTED

Một workflow JDBC cần lưu bắt buộc sự kiện A, thử lưu tùy chọn B, rồi lưu C. Nếu B lỗi nhưng A/C vẫn cần commit chung, propagation nào liên quan? Vì sao không nên áp kết luận đó trực tiếp cho Hibernate persistence context?

### Bài 4 — Isolation

Transaction A đọc cùng một row hai lần trong lúc B cập nhật và commit. Nêu điều gì có thể xảy ra ở READ_COMMITTED, vì sao không nên áp cùng câu trả lời cho mọi DBMS ở REPEATABLE_READ, và khi nào cần optimistic locking.

### Bài 5 — Inner isolation

Outer mở READ_COMMITTED, inner `REQUIRED` khai SERIALIZABLE. Vì sao inner không tự đổi isolation của physical transaction? Cách nào có thể phát hiện mismatch thay vì âm thầm bỏ qua?

### Bài 6 — Checked exception

~~~java
@Transactional
public void allocate() throws AllocationException {
    repository.save(...);
    throw new AllocationException("Rejected");
}
~~~

`AllocationException extends Exception`, không phải RuntimeException. Kết quả commit/rollback mặc định ra sao? Viết annotation khi nghiệp vụ yêu cầu rollback.

### Bài 7 — Catch exception

Outer bắt RuntimeException do inner REQUIRED ném rồi return. Vì sao vẫn có thể nhận `UnexpectedRollbackException`? Nêu hai cách sửa dựa trên business semantics.

### Bài 8 — Timeout

So sánh `@Transactional(timeout = 10)` với `jakarta.persistence.query.timeout = 10000` và Hikari `connectionTimeout = 10000`. Cái nào giới hạn transaction, query và việc mượn connection?

### Bài 9 — Self-invocation

Một class có method A không annotated, gọi trực tiếp B là method `@Transactional(REQUIRES_NEW)`. Vì sao B có thể không mở transaction mới? Hãy tổ chức lại hai Spring beans để B được chặn bởi interceptor.

### Bài 10 — Hibernate failure

Một constraint violation xảy ra trong `saveAndFlush`. Vì sao catch exception rồi gọi `save` khác trong cùng Session không an toàn? `noRollbackFor` có đảm bảo commit được không?

### Bài 11 — Async và retry

Vì sao `@Async` không tự dùng transaction của caller? Với serialization failure, retry nên nằm ngoài hay trong transactional attempt?

### Bài 12 — Test rollback

Viết ý tưởng integration test xác nhận một checked exception có `rollbackFor` thật sự không để lại DB row. Vì sao test method tự mang `@Transactional` có thể che lỗi?

**Gợi ý:** (1) cùng transaction, rollback; (2) audit có thể commit độc lập; (3) JDBC savepoint, JPA context không rewind; (4) concurrency visibility phụ thuộc DB, @Version bảo vệ updates; (5) isolation áp khi tạo transaction, validateExistingTransaction nếu manager hỗ trợ; (6) checked mặc định không rollback, thêm rollbackFor; (7) shared rollback-only, propagate hoặc chọn transaction boundary khác; (8) seconds/milliseconds và tài nguyên khác nhau; (9) proxy bypass; (10) Session/DB transaction có thể invalid; (11) thread-bound và retry TX mới; (12) quan sát DB từ transaction độc lập.

## 28. Tài liệu tham khảo

- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): cơ chế `@Transactional`, proxy và transaction boundaries.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED, REQUIRES_NEW, NESTED và logical/physical transaction.
- [Spring Framework Reference — Rolling Back](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules và checked/unchecked exceptions.
- [Spring Framework Javadocs — Transactional](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Transactional.html): propagation, isolation, timeout, rollbackFor và noRollbackFor.
- [Spring Framework Javadocs — JpaTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html): JPA transaction management và nested caveats.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): persistence context, flushing, optimistic locking và transaction APIs.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `EntityManager`, lifecycle, transaction semantics, flush và `@Version`.

**Kết luận:** `@Transactional` là một hợp đồng về transaction boundary, không chỉ là annotation “có rollback”. `Propagation.REQUIRED` thường gắn các bước nghiệp vụ vào cùng transaction; `REQUIRES_NEW` mở một physical transaction riêng và có chi phí connection/consistency; `NESTED` dựa trên savepoint và không thể dùng như nested JPA state mặc định. `Isolation` là cơ chế thực thi của DBMS, `timeout` không phải hard deadline cho mọi Java operation, và rollback mặc định của Spring phân biệt unchecked với checked exceptions. Muốn bảo đảm tính đúng đắn, hãy đặt rule ở đúng proxy/service boundary, xử lý rollback-only rõ ràng, không tái sử dụng Hibernate Session đã lỗi, và kiểm chứng những tình huống quan trọng qua integration tests trên database phù hợp.
