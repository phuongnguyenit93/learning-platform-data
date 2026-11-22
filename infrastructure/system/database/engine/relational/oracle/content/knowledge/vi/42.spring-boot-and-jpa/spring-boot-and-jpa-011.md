# Read-only, isolation, flush và hành vi khóa thực tế trong Oracle

Trong ứng dụng Spring Boot dùng JPA/Hibernate với Oracle Database, các khái niệm **read-only**, **transaction isolation**, **flush** và **locking** thường xuất hiện cùng nhau nhưng chúng điều khiển những lớp khác nhau. Nếu hiểu nhầm, ứng dụng có thể tưởng rằng một transaction không thể ghi dữ liệu trong khi Oracle vẫn cho phép DML; hoặc nghĩ rằng `save()` đã ghi và commit ngay trong khi SQL còn nằm trong persistence context. Một truy vấn đọc bình thường cũng có thể thấy dữ liệu nhất quán mà không khóa hàng, còn một lần `flush()` có thể phát sinh DML và giữ row locks đến khi transaction kết thúc.

Spring `@Transactional(readOnly = true)` chủ yếu là transaction hint để transaction manager, JDBC driver và JPA provider tối ưu. Với Hibernate, Spring Data JPA có thể đặt flush mode thành MANUAL để tránh dirty checking và auto flush. Cờ này **không tự động tương đương** với Oracle `SET TRANSACTION READ ONLY`, vốn là chế độ do database thực thi, tạo snapshot nhất quán ở cấp transaction và không cho phép DML.

Oracle mặc định dùng READ COMMITTED với read consistency ở cấp statement. Một SELECT bình thường đọc phiên bản dữ liệu đã commit bằng cơ chế multiversion concurrency control (MVCC), không khóa các row đang đọc. DML và `SELECT ... FOR UPDATE` mới lấy row locks; những lock này được giữ tới COMMIT hoặc ROLLBACK. JPA flush quyết định thời điểm SQL thực sự được gửi xuống Oracle, vì vậy nó cũng ảnh hưởng thời điểm lock bắt đầu.

Bài học thuộc nhóm **Spring Boot và JPA** của Database Engine Relational Oracle. Nội dung tập trung vào cách Spring quản lý transaction, read-only hint, Oracle isolation levels, persistence context và flush, optimistic/pessimistic locking, row-lock behavior, lock waits và cách điều tra blocker trong Oracle.

Sau bài này, bạn có thể:

- Phân biệt Spring read-only transaction với Oracle read-only transaction.
- Hiểu `@Transactional`, propagation, isolation và rollback rules.
- Biết khi nào isolation setting của method được áp dụng và khi nào bị transaction bên ngoài chi phối.
- Phân biệt READ COMMITTED, SERIALIZABLE và READ ONLY trong Oracle.
- Hiểu vì sao Oracle không hỗ trợ READ UNCOMMITTED và REPEATABLE READ như các isolation level riêng.
- Giải thích persistence context, dirty checking, flush và commit.
- Hiểu ảnh hưởng của FlushMode AUTO, COMMIT và Hibernate MANUAL.
- Dùng `flush()`, `clear()`, `refresh()` và Spring Data `saveAndFlush()` đúng mục đích.
- Phân biệt bulk JPQL DML với thay đổi entity thông thường.
- Hiểu MVCC và row-level locking trong Oracle.
- Chọn optimistic locking với `@Version` hoặc pessimistic locking với `@Lock`.
- Dùng `SELECT FOR UPDATE`, NOWAIT, WAIT và SKIP LOCKED đúng tình huống.
- Hiểu thời điểm lock được lấy và thời điểm lock được giải phóng.
- Điều tra blocking session, TX/TM locks và lỗi ORA-00054, ORA-00060, ORA-08177.
- Thiết kế transaction ngắn, có ranh giới rõ và phù hợp với business consistency.

> **Phạm vi ví dụ:** Ví dụ Java dùng Spring Boot 3, Jakarta Persistence (`jakarta.persistence`) và Oracle Database 19c. Với Spring Boot 2, thay package `jakarta.persistence` bằng `javax.persistence` và kiểm tra phiên bản Spring/Hibernate thực tế. Một số hành vi như flush mode, lock timeout và SQL được sinh ra phụ thuộc JPA provider/dialect; hãy kiểm tra SQL thực tế của ứng dụng.

## 1. Bốn lớp khái niệm cần phân biệt

| Khái niệm | Lớp chịu trách nhiệm | Câu hỏi chính |
| --- | --- | --- |
| Read-only | Spring transaction manager, JDBC driver, JPA provider hoặc Oracle transaction | Transaction có được tối ưu cho đọc hoặc bị database cấm ghi không? |
| Isolation | Oracle transaction và Spring transaction manager | Một transaction nhìn thấy phiên bản dữ liệu nào? |
| Flush | JPA persistence context/Hibernate | Khi nào thay đổi trong memory được gửi thành SQL xuống database? |
| Locking | Oracle Database và JPA lock API | Transaction nào giữ row lock, transaction nào phải chờ? |

Các lớp này liên quan nhưng không thay thế nhau:

- `readOnly = true` không tự tạo snapshot transaction-level của Oracle.
- Isolation không đồng nghĩa với việc khóa mọi row đã đọc.
- Flush không phải commit.
- Commit giải phóng lock, nhưng flush không giải phóng lock.
- Một SELECT bình thường trong Oracle READ COMMITTED không lấy row lock.
- Pessimistic lock có thể lấy row lock ngay cả khi ứng dụng chưa thực hiện UPDATE.

## 2. Spring @Transactional hoạt động thế nào?

Spring dùng transaction manager để mở, tham gia, commit hoặc rollback transaction. Với Spring Boot JPA, transaction manager thường là `JpaTransactionManager` kết hợp JPA provider như Hibernate.

### 2.1. Cấu hình mặc định

Nếu chỉ viết:

~~~java
@Transactional
public void createOrder() {
    // business logic
}
~~~

Các giá trị mặc định của Spring `@Transactional` là:

| Thuộc tính | Mặc định |
| --- | --- |
| propagation | REQUIRED |
| isolation | DEFAULT |
| readOnly | false |
| timeout | Dùng timeout mặc định của transaction system hoặc không giới hạn |
| rollback | RuntimeException và Error |

Checked exception không tự động gây rollback theo quy tắc mặc định của Spring. Nếu business operation phải rollback khi có checked exception, khai báo `rollbackFor`.

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // import nhiều bước
}
~~~

### 2.2. Đặt transaction boundary ở service

Nên đặt transaction boundary ở service đại diện cho một đơn vị nghiệp vụ. Repository tập trung vào truy vấn và persistence.

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;

    public OrderService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
    }

    @Transactional
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        paymentRepository.markReady(orderId);
    }
}
~~~

Nếu cả hai repository dùng cùng transaction manager và cùng transaction, thay đổi của chúng có thể được commit hoặc rollback như một đơn vị nghiệp vụ.

### 2.3. @Transactional dựa vào proxy

Trong proxy mode mặc định, Spring chỉ intercept lời gọi đi qua proxy. Gọi một method `@Transactional` từ method khác trong cùng object (self-invocation) không tạo transaction interception mới.

~~~java
@Service
public class ImportService {

    public void runImport() {
        saveChunk(); // self-invocation, không đi qua proxy
    }

    @Transactional
    public void saveChunk() {
        // có thể không có transaction như bạn kỳ vọng
    }
}
~~~

Tách transaction method sang bean khác hoặc gọi qua Spring proxy. Không dựa vào annotation nếu chưa xác nhận lời gọi thực tế được intercept.

### 2.4. Transaction annotation không tự tạo transaction

`@Transactional` là metadata. Ứng dụng cần cấu hình transaction management và một transaction manager phù hợp. Nếu annotation không được xử lý, code có thể chạy mà không có transaction boundary như mong đợi.

## 3. Propagation và transaction hiện hữu

Propagation quyết định method tham gia transaction hiện tại hay tạo transaction mới.

### 3.1. REQUIRED

REQUIRED là mặc định:

- Nếu chưa có transaction, Spring tạo transaction mới.
- Nếu đã có transaction, method tham gia transaction đó.

~~~java
@Transactional
public void placeOrder() {
    reserveInventory();
    createInvoice();
}

@Transactional
public void reserveInventory() {
    // tham gia transaction của placeOrder
}
~~~

Nếu `reserveInventory()` lỗi và exception làm transaction rollback, thay đổi của `placeOrder()` cũng có thể bị rollback.

### 3.2. REQUIRES_NEW

REQUIRES_NEW tạm treo transaction bên ngoài và tạo transaction vật lý mới.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    // transaction độc lập
}
~~~

Điều này có thể hữu ích cho audit record cần commit độc lập, nhưng cần chú ý connection pool và lock dependency. Transaction mới có thể chờ row lock mà transaction ngoài đang giữ, trong khi transaction ngoài đang chờ method mới trả về. Thiết kế đó có thể tạo tình trạng chờ không cần thiết hoặc deadlock ở tầng ứng dụng.

### 3.3. Isolation của method tham gia transaction ngoài

Thuộc tính isolation chỉ áp dụng khi Spring thực sự bắt đầu transaction mới, thường là propagation REQUIRED hoặc REQUIRES_NEW theo tài liệu Spring. Nếu method REQUIRED tham gia transaction đã tồn tại, isolation khai báo trên method trong thường không thay đổi isolation của transaction bên ngoài.

Ví dụ:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outerOperation() {
    innerOperation();
}

@Transactional(isolation = Isolation.SERIALIZABLE)
public void innerOperation() {
    // tham gia transaction outerOperation
    // isolation SERIALIZABLE không tự nâng transaction hiện hữu
}
~~~

Có thể bật `validateExistingTransaction` trên transaction manager để phát hiện một số mismatch isolation/read-only thay vì âm thầm tham gia transaction có thuộc tính khác. Cách cấu hình phụ thuộc transaction manager.

### 3.4. Timeout và thời gian giữ lock

Timeout của Spring transaction không phải cơ chế thay thế lock timeout của Oracle. Một transaction có thể giữ row locks trong suốt thời gian xử lý, bao gồm cả thời gian gọi service khác hoặc chờ I/O. Hãy giữ transaction ngắn và tránh gọi API bên ngoài khi đang giữ database locks.

## 4. @Transactional(readOnly = true) trong Spring

Đây là cấu hình thường dùng cho service chỉ đọc:

~~~java
@Transactional(readOnly = true)
public OrderView getOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();
    return OrderView.from(order);
}
~~~

### 4.1. Read-only là hint

Theo tài liệu Spring Data JPA, read-only flag được truyền như một hint cho JDBC driver để tối ưu hiệu năng. Nó không phải một kiểm tra bảo đảm ứng dụng không chạy DML. Một số database có thể từ chối INSERT/UPDATE trong read-only transaction, nhưng không thể giả định mọi cấu hình đều thực thi điều đó.

Với Hibernate, Spring Data JPA đặt flush mode thành MANUAL trong read-only transaction để tránh auto flush và bỏ qua dirty checking ở các trường hợp phù hợp. Điều này có thể giảm overhead khi đọc object graph lớn.

### 4.2. Điều gì xảy ra nếu sửa entity trong read-only transaction?

~~~java
@Transactional(readOnly = true)
public void renameCustomer(Long id) {
    Customer customer = customerRepository.findById(id)
        .orElseThrow();

    customer.setName("New name");
}
~~~

Không nên viết code như trên. Với Hibernate và read-only optimization, thay đổi có thể không được tự động flush xuống database. Tuy nhiên:

- Entity object trong Java có thể đã bị thay đổi trong memory.
- Native JDBC hoặc một transaction manager khác có thể có hành vi riêng.
- Explicit flush hoặc provider-specific API có thể làm thay đổi hành vi.
- Cấu hình khác nhau có thể xử lý read-only khác nhau.

Đừng dùng readOnly để bảo vệ dữ liệu. Dùng database privileges, read-only transaction mode được enforce hoặc cơ chế security phù hợp.

### 4.3. Read-only không phải isolation level

`readOnly = true` và `isolation = Isolation.SERIALIZABLE` là hai thuộc tính độc lập.

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED
)
public ReportView buildReport() {
    // đọc dữ liệu
}
~~~

Annotation này yêu cầu Spring transaction manager và provider xử lý như một read-only transaction hint ở READ COMMITTED. Nó không tự bảo đảm nhiều SELECT nhìn cùng một snapshot Oracle transaction-level.

### 4.4. Repository và service

Spring Data JPA thường cấu hình các phương thức đọc có read-only transaction metadata. Tuy nhiên, tài liệu Spring Data khuyến nghị đặt transaction boundary ở tầng service khi cần bảo đảm consistency của một đơn vị công việc gồm nhiều repository calls.

### 4.5. Read-only không thay thế quyền database

Nếu database account của ứng dụng có quyền UPDATE, annotation readOnly không phải security boundary. Khi cần bảo đảm account báo cáo không thể ghi, hãy cấp một database user/role chỉ có quyền SELECT trên các object cần thiết.

## 5. Oracle SET TRANSACTION READ ONLY

Oracle có một chế độ read-only thật ở cấp transaction.

### 5.1. Cú pháp

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT SUM(amount)
FROM app_order
WHERE order_date >= DATE '2026-01-01';

SELECT COUNT(*)
FROM app_customer;

COMMIT;
~~~

`SET TRANSACTION READ ONLY` phải là câu SQL đầu tiên của transaction và chỉ được đặt một lần trong transaction. Nếu transaction trước chưa kết thúc, cần COMMIT hoặc ROLLBACK trước khi bắt đầu read-only transaction.

### 5.2. Snapshot transaction-level

Tất cả query trong read-only transaction nhìn thấy những thay đổi đã commit trước thời điểm transaction bắt đầu. Các query sau đó vẫn nhìn cùng một snapshot dù session khác tiếp tục INSERT/UPDATE/DELETE.

Điều này hữu ích cho báo cáo gồm nhiều câu SELECT cần nhất quán với cùng một thời điểm.

### 5.3. Oracle cấm DML

Trong read-only transaction, chỉ các thao tác được Oracle cho phép như SELECT không có FOR UPDATE và các lệnh transaction/session được tài liệu hóa mới hợp lệ. INSERT, UPDATE, DELETE và SELECT FOR UPDATE không được phép.

### 5.4. Không khóa dữ liệu của session khác

Read-only transaction không lấy thêm row locks chỉ để đọc. Session khác vẫn có thể query và update cùng bảng. Oracle dùng undo để dựng lại phiên bản dữ liệu cần thiết cho snapshot.

### 5.5. Read-only transaction và Connection.setReadOnly

Oracle JDBC 19c hỗ trợ read-only connection ở mức JDBC driver, nhưng Oracle server không coi đó là một read-only transaction được enforce. `Connection.setReadOnly(true)` là hint; nó không tương đương SQL `SET TRANSACTION READ ONLY`.

## 6. Enforce read-only trong Spring

Nếu ứng dụng cần database từ chối DML, phải xác định transaction manager thực tế.

### 6.1. Spring DataSourceTransactionManager

Spring `DataSourceTransactionManager` có tùy chọn `setEnforceReadOnly(true)`. Khi bật, transaction manager thực hiện câu lệnh `SET TRANSACTION READ ONLY` trên connection cho transaction được đánh dấu read-only. Cơ chế này mạnh hơn JDBC `Connection.setReadOnly(true)` hint.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
public DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setEnforceReadOnly(true);
    return manager;
}
~~~

Đây là cấu hình cho JDBC transaction manager. Không copy nguyên cấu hình này vào ứng dụng đang dùng `JpaTransactionManager` mà không xem xét tích hợp JPA/connection lifecycle.

### 6.2. Spring Data JPA với JpaTransactionManager

Khi dùng JPA transaction manager, `@Transactional(readOnly = true)` thường được dùng như hint cho Hibernate/JPA provider. Không tự kết luận rằng Oracle đã nhận `SET TRANSACTION READ ONLY`.

Nếu yêu cầu là ngăn mọi DML:

- Dùng database account chỉ có quyền SELECT cho workload đọc.
- Hoặc thiết kế transaction manager/enforcement phù hợp với JPA connection lifecycle.
- Kiểm tra SQL thực tế ở transaction start.
- Thử INSERT/UPDATE trong môi trường kiểm thử và xác nhận Oracle từ chối.

Không dùng một unit test chỉ kiểm tra annotation để kết luận database enforcement đã hoạt động.

### 6.3. Phân biệt ba cơ chế

| Cơ chế | Ai xử lý? | Có cấm DML ở Oracle không? |
| --- | --- | --- |
| `@Transactional(readOnly = true)` | Spring/JPA transaction hint | Không mặc định |
| `Connection.setReadOnly(true)` | JDBC driver hint | Không với Oracle server |
| `SET TRANSACTION READ ONLY` | Oracle Database | Có, trong transaction hiện tại |

## 7. Isolation levels của Oracle

Oracle cung cấp ba chế độ đọc/transaction quan trọng:

- READ COMMITTED.
- SERIALIZABLE.
- READ ONLY.

Oracle server hỗ trợ hai JDBC transaction isolation levels: `TRANSACTION_READ_COMMITTED` và `TRANSACTION_SERIALIZABLE`. READ ONLY là transaction mode riêng, không phải một giá trị JDBC isolation level trong `Connection.TRANSACTION_*`.

### 7.1. READ COMMITTED — mặc định

Mỗi câu SELECT nhìn thấy dữ liệu đã commit trước khi câu query đó bắt đầu.

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

Đây là default Oracle behavior. Một transaction có thể chạy hai query cùng điều kiện và nhận kết quả khác nhau nếu transaction khác commit thay đổi giữa hai query.

Ví dụ:

~~~text
T1: SELECT balance -> 100
T2: UPDATE balance = 150
T2: COMMIT
T1: SELECT balance -> 150
~~~

T1 không đọc uncommitted data. Query đầu thấy snapshot trước commit của T2; query thứ hai bắt đầu sau commit nên thấy giá trị mới.

### 7.2. SERIALIZABLE

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Các query trong transaction nhìn cùng một snapshot tại thời điểm transaction bắt đầu, cộng với thay đổi do chính transaction đó tạo ra.

SERIALIZABLE cho phép DML, nhưng nếu transaction cố update/delete một row đã bị transaction khác thay đổi và commit sau khi transaction SERIALIZABLE bắt đầu, Oracle có thể trả:

~~~text
ORA-08177: Cannot serialize access for this transaction
~~~

Ứng dụng cần rollback và retry toàn bộ đơn vị nghiệp vụ theo policy phù hợp. Không chỉ retry một câu UPDATE nếu các quyết định nghiệp vụ trước đó được tính dựa trên snapshot cũ.

### 7.3. READ ONLY

~~~sql
SET TRANSACTION READ ONLY;
~~~

READ ONLY có transaction-level snapshot giống SERIALIZABLE về khả năng nhìn dữ liệu, nhưng không cho phép DML. Nó phù hợp với báo cáo gồm nhiều query nhất quán trong cùng transaction.

### 7.4. So sánh

| Đặc điểm | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Snapshot | Mỗi statement | Toàn transaction | Toàn transaction |
| Dirty reads | Không | Không | Không |
| Thấy commit mới giữa các query | Có | Không | Không |
| DML | Có | Có, có thể ORA-08177 | Không |
| Row locks chỉ vì SELECT thường | Không | Không | Không |
| Dùng cho | OLTP mặc định | Transaction cần snapshot ổn định và có thể ghi | Báo cáo nhiều query nhất quán |

### 7.5. Oracle không có READ UNCOMMITTED như một isolation mode riêng

Oracle không cung cấp READ UNCOMMITTED với dirty-read semantics. Đọc thông thường không thấy dữ liệu chưa commit của session khác. Không dùng `Isolation.READ_UNCOMMITTED` với giả định Oracle sẽ cho phép dirty reads.

### 7.6. Oracle không cung cấp REPEATABLE READ như một mức riêng

Oracle cung cấp SERIALIZABLE và READ ONLY cho transaction-level read consistency. Không giả định `Isolation.REPEATABLE_READ` của Spring/JDBC có thể được ánh xạ sang một Oracle mode độc lập. Oracle JDBC server transaction isolation được tài liệu hóa là READ_COMMITTED và SERIALIZABLE.

## 8. Dùng isolation trong Spring Boot

### 8.1. READ COMMITTED

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateOrder() {
    // Oracle default isolation
}
~~~

Thông thường có thể dùng `Isolation.DEFAULT` nếu không cần override database default.

### 8.2. SERIALIZABLE

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void allocateInventory(Long productId, int quantity) {
    // đọc và ghi theo transaction snapshot
}
~~~

Phải xử lý ORA-08177 và thiết kế retry ở cấp transaction/business operation.

### 8.3. READ ONLY Oracle transaction

`Isolation` enum của Spring không có READ_ONLY. Để tạo Oracle read-only transaction, phải dùng `SET TRANSACTION READ ONLY` đúng thời điểm transaction bắt đầu hoặc cơ chế enforce của transaction manager phù hợp.

Không viết:

~~~java
@Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
public ReportView report() {
    // không bảo đảm Oracle READ ONLY transaction
}
~~~

Đây không phải cách portable để yêu cầu Oracle read-only transaction-level snapshot.

### 8.4. Isolation chỉ áp dụng khi transaction mới bắt đầu

Nếu method được gọi bên trong transaction REQUIRED hiện có, isolation khai báo ở method trong có thể không được áp dụng. Nếu thật sự cần transaction riêng với isolation khác, cân nhắc REQUIRES_NEW và hiểu rõ tác động tới connection, locks và commit độc lập.

## 9. Persistence context và dirty checking

JPA dùng persistence context để quản lý entity trong một đơn vị làm việc.

### 9.1. Entity managed

~~~java
@Transactional
public void renameCustomer(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName("New name");
}
~~~

Entity được lấy bằng EntityManager.find thường trở thành managed. Khi thay đổi thuộc tính, Hibernate theo dõi trạng thái entity thông qua dirty checking. Ứng dụng không bắt buộc gọi repository.save() lại cho entity managed để thay đổi được đồng bộ.

### 9.2. Dirty checking

Trong lúc flush, Hibernate so sánh trạng thái managed entity với snapshot và phát sinh INSERT/UPDATE/DELETE cần thiết.

Ví dụ:

~~~java
customer.setName("New name");
// chưa chắc UPDATE đã được gửi xuống Oracle ngay tại đây
~~~

Việc thay đổi Java object không có nghĩa database đã nhận SQL.

### 9.3. Entity detached

Entity bị detach khi:

- EntityManager.clear() được gọi.
- EntityManager.close().
- Entity bị detach riêng.
- Persistence context kết thúc.

Thay đổi trên detached entity không tự động được flush. Cần merge hoặc lấy lại entity managed theo đúng use case.

### 9.4. Persistence context không phải transaction

Persistence context quản lý entity state. Transaction quản lý database work và commit/rollback. Hai khái niệm thường đi cùng nhưng không đồng nhất:

- Có thể có persistence context ngoài transaction.
- Flush có thể xảy ra trong transaction.
- Commit kết thúc transaction.
- Clear làm detach entity nhưng không commit hoặc rollback transaction.

## 10. Flush là gì?

Flush đồng bộ thay đổi đang chờ trong persistence context xuống database bằng SQL.

### 10.1. Flush không commit

~~~java
entityManager.flush();
~~~

Sau flush:

- SQL INSERT/UPDATE/DELETE có thể đã được gửi tới Oracle.
- Constraint được kiểm tra tại database.
- Row locks có thể được lấy.
- Transaction vẫn chưa commit.
- Các transaction khác không thấy thay đổi chưa commit.
- Ứng dụng vẫn có thể rollback để hoàn tác thay đổi.

### 10.2. Commit thường kích hoạt flush

Trước khi commit transaction JPA, provider đồng bộ thay đổi pending theo flush semantics. Nếu constraint violation xảy ra khi flush/commit, exception có thể xuất hiện tại thời điểm đó thay vì ngay khi gọi setter hoặc save.

### 10.3. Khi nào Hibernate flush?

Các thời điểm phổ biến:

- Trước khi transaction commit.
- Khi FlushMode AUTO và một query có thể bị ảnh hưởng bởi pending changes.
- Khi ứng dụng gọi EntityManager.flush() rõ ràng.

Flush timing còn phụ thuộc provider và query spaces. Đọc SQL log để xác nhận thời điểm thực tế.

## 11. Flush modes

### 11.1. JPA FlushModeType.AUTO

AUTO là mode phổ biến mặc định. Provider phải bảo đảm query nhìn thấy các thay đổi có liên quan trong persistence context; provider có thể flush trước query khi cần.

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

### 11.2. JPA FlushModeType.COMMIT

~~~java
entityManager.setFlushMode(FlushModeType.COMMIT);
~~~

COMMIT yêu cầu flush trước commit. Provider có thể flush ở thời điểm khác theo semantics được cho phép, nên không được coi nó là cam kết tuyệt đối rằng không có SQL trước commit.

### 11.3. Hibernate MANUAL

Hibernate có FlushMode.MANUAL, trong đó ứng dụng chịu trách nhiệm gọi flush khi cần. Spring Data JPA có thể đặt mode này cho Hibernate khi transaction được đánh dấu readOnly.

MANUAL là Hibernate-specific, không phải một giá trị portable của JPA FlushModeType.

### 11.4. So sánh

| Mode | Hành vi khái quát |
| --- | --- |
| JPA AUTO | Flush khi cần để query nhìn thấy pending changes và trước commit |
| JPA COMMIT | Flush trước commit; provider có thể flush ở thời điểm khác |
| Hibernate MANUAL | Không auto flush theo cách thông thường; ứng dụng/provider phải yêu cầu flush |

### 11.5. Read-only transaction và MANUAL

Khi Spring Data JPA/Hibernate nhận `@Transactional(readOnly = true)`, Spring có thể chuyển Hibernate session sang MANUAL. Điều này giúp bỏ qua một số dirty checking/flush work cho read workload.

Nếu service chỉ đọc dữ liệu, đây là tối ưu hữu ích. Nếu service vô tình sửa entity, thay đổi có thể không được ghi xuống database theo luồng auto flush bình thường. Không dùng cơ chế này làm lớp bảo vệ dữ liệu.

## 12. save(), saveAndFlush(), flush() và commit()

Các method có ý nghĩa khác nhau.

| API | Ý nghĩa |
| --- | --- |
| repository.save(entity) | Persist hoặc merge entity theo trạng thái; SQL có thể được hoãn |
| repository.saveAndFlush(entity) | Save rồi yêu cầu flush persistence context |
| entityManager.flush() | Gửi pending changes xuống database |
| transactionManager commit / connection.commit() | Commit transaction và giải phóng transaction locks |

### 12.1. save() không bảo đảm SQL chạy ngay

~~~java
orderRepository.save(order);
// SQL có thể chưa chạy nếu chưa flush
~~~

### 12.2. saveAndFlush() không commit

~~~java
orderRepository.saveAndFlush(order);
// SQL đã được flush nhưng transaction vẫn mở
~~~

Row locks từ DML đã flush vẫn có thể được giữ cho đến commit/rollback.

### 12.3. Vì sao cần flush tường minh?

Có thể cần flush để:

- Phát hiện constraint error sớm trong transaction.
- Bảo đảm DML được thực hiện trước một thao tác cần kết quả database.
- Đo thời gian thực thi SQL riêng với thời gian commit.
- Đồng bộ pending changes trước native SQL hoặc bulk operation khi cần.

Không gọi flush sau mọi setter. Flush quá thường xuyên làm mất cơ hội gom SQL và có thể tăng round trips.

### 12.4. Clear sau flush

~~~java
entityManager.flush();
entityManager.clear();
~~~

Đây là pattern thường dùng khi xử lý lượng lớn entity để giảm memory footprint của persistence context. Clear detach mọi entity đang managed. Nếu clear trước khi flush, thay đổi pending có thể bị mất khỏi persistence context và không được gửi xuống database.

## 13. Bulk JPQL DML và persistence context

Bulk JPQL UPDATE/DELETE chạy trực tiếp ở database và không đi qua dirty checking cho từng managed entity.

### 13.1. Ví dụ bulk update

~~~java
@Modifying
@Query("""
    update Order o
       set o.status = :status
     where o.createdAt < :cutoff
       and o.status = 'PENDING'
    """)
int expirePendingOrders(
    @Param("status") OrderStatus status,
    @Param("cutoff") LocalDateTime cutoff
);
~~~

### 13.2. Bulk DML không tự cập nhật managed objects

Nếu Order entity đã nằm trong persistence context, bulk update có thể thay đổi row trong Oracle nhưng Java object managed vẫn giữ giá trị cũ.

### 13.3. Flush và clear tự động

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Order o
       set o.status = 'EXPIRED'
     where o.status = 'PENDING'
       and o.createdAt < :cutoff
    """)
int expireOrders(@Param("cutoff") LocalDateTime cutoff);
~~~

`flushAutomatically` đồng bộ pending changes trước bulk DML. `clearAutomatically` detach persistence context sau đó để tránh tiếp tục dùng managed state cũ.

Chỉ dùng clearAutomatically khi hiểu rằng mọi entity đang managed trong persistence context sẽ bị detach.

### 13.4. Bulk DML vẫn lấy Oracle locks

Bulk UPDATE/DELETE vẫn là DML tại Oracle. Các row bị thay đổi sẽ được khóa theo quy tắc Oracle cho đến khi transaction kết thúc.

## 14. Oracle MVCC: SELECT bình thường không khóa row

Oracle dùng multiversion concurrency control và undo để cung cấp read consistency.

### 14.1. Reader không chặn writer

Một SELECT bình thường đọc phiên bản dữ liệu đã commit phù hợp với snapshot của statement. Nếu session khác đang UPDATE row nhưng chưa commit, reader có thể đọc phiên bản đã commit trước update bằng undo.

### 14.2. Writer không chặn reader thông thường

Một UPDATE đang giữ row lock thường không ngăn SELECT bình thường đọc row đó. SELECT có thể nhìn phiên bản đã commit trước update.

### 14.3. Writer có thể chặn writer

Nếu transaction thứ hai muốn UPDATE/DELETE cùng row đang bị transaction đầu khóa, transaction thứ hai chờ transaction đầu COMMIT hoặc ROLLBACK.

### 14.4. Minh họa

~~~text
Session A                         Session B
---------                         ---------
UPDATE account
SET balance = 900
WHERE id = 1;
                                  SELECT balance
                                  FROM account
                                  WHERE id = 1;
                                  -> đọc giá trị cũ đã commit
                                  UPDATE account
                                  SET balance = 800
                                  WHERE id = 1;
                                  -> chờ row lock của A
COMMIT;
                                  -> tiếp tục sau khi A commit
~~~

Đây là behavior cơ bản của Oracle READ COMMITTED.

### 14.5. Không có dirty read

Oracle không cho session đọc giá trị chưa commit của session khác theo READ COMMITTED. Không dùng READ UNCOMMITTED như một cách giảm lock contention.

## 15. Row locks và table locks trong Oracle

Oracle dùng nhiều loại lock để bảo vệ dữ liệu và cấu trúc.

### 15.1. DML row locks

INSERT, UPDATE và DELETE lấy row locks trên các dòng bị thay đổi. Lock của transaction được giữ đến khi transaction commit hoặc rollback.

### 15.2. TM table lock

DML cũng lấy table-level DML lock (TM enqueue) ở mode phù hợp để bảo vệ cấu trúc và tính nhất quán của thao tác DML. Row-exclusive table lock không có nghĩa toàn bộ bảng bị độc quyền; các transaction khác vẫn có thể thực hiện DML trên các rows không xung đột.

### 15.3. TX transaction enqueue

TX enqueue liên quan đến transaction và row-level contention. Khi session chờ một transaction khác nhả row lock, wait event thường thấy là `enq: TX - row lock contention`.

### 15.4. SELECT bình thường

SELECT thông thường không lấy row locks và không bị row-level DML lock chặn. DDL, explicit table locks hoặc một số tình huống đặc biệt có thể tạo loại wait khác; không khái quát rằng SELECT không bao giờ chờ.

### 15.5. Lock tồn tại đến transaction end

Đóng cursor không giải phóng row locks. Flush cũng không giải phóng locks. Commit hoặc rollback mới kết thúc transaction và giải phóng các locks tương ứng.

## 16. SELECT FOR UPDATE

Khi cần đọc một row rồi bảo đảm row không bị transaction khác sửa trước khi ứng dụng cập nhật, có thể khóa row bằng SELECT FOR UPDATE.

### 16.1. Cú pháp

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE;
~~~

Oracle lấy exclusive row locks cho các rows được chọn. Các session khác không thể lấy lock xung đột hoặc sửa các rows đó cho đến khi transaction kết thúc.

### 16.2. Lock được lấy trước fetch

Khi SELECT FOR UPDATE dùng cursor, Oracle khóa các rows trong result set khi cursor được mở, trước khi fetch từng row. Vì vậy một query trả về nhiều rows có thể khóa nhiều rows ngay từ đầu, kể cả ứng dụng chỉ fetch một phần.

### 16.3. Lock được giải phóng khi nào?

~~~sql
COMMIT;
-- hoặc
ROLLBACK;
~~~

Đóng ResultSet/Statement không giải phóng transaction locks.

### 16.4. NOWAIT

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE NOWAIT;
~~~

Nếu row đang bị lock xung đột, Oracle trả lỗi ngay thay vì chờ. Ứng dụng có thể thông báo tài nguyên đang bận hoặc retry sau thời gian phù hợp.

### 16.5. WAIT n

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE WAIT 5;
~~~

Oracle chờ tối đa số giây được chỉ định để lấy lock. Nếu hết thời gian, statement trả lỗi.

### 16.6. SKIP LOCKED

~~~sql
SELECT job_id, status
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua rows đang bị transaction khác khóa. Nó hữu ích cho nhiều worker cùng lấy công việc từ queue để tránh tất cả worker chờ cùng một row.

SKIP LOCKED không bảo đảm thứ tự xử lý nghiệp vụ hoặc công bằng giữa worker. Cần thiết kế lease/status/attempt count và transaction ngắn.

### 16.7. Hạn chế SQL

Oracle có các restriction với FOR UPDATE, ví dụ query dùng DISTINCT, set operators, GROUP BY, aggregate functions hoặc một số view transformations. Khi JPA tạo SELECT FOR UPDATE cho query phức tạp, SQL có thể không hợp lệ. Dùng query đơn giản trên entity/table cần khóa và kiểm tra SQL được sinh ra.

## 17. JPA optimistic locking với @Version

Optimistic locking phù hợp khi xung đột ghi không thường xuyên và không muốn giữ row lock từ lúc đọc đến lúc ghi.

### 17.1. Entity version

~~~java
@Entity
@Table(name = "APP_PRODUCT")
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @Version
    @Column(name = "VERSION_NO")
    private Long version;

    // getters/setters
}
~~~

### 17.2. Cách hoạt động

Giả sử hai transaction cùng đọc version 4:

~~~text
T1 đọc version 4
T2 đọc version 4

T1 UPDATE ... WHERE id = 10 AND version_no = 4
T1 tăng version thành 5 và COMMIT

T2 UPDATE ... WHERE id = 10 AND version_no = 4
T2 không cập nhật được row như kỳ vọng
T2 nhận OptimisticLockException
~~~

Provider thường phát sinh UPDATE với version predicate và tăng version. Kiểm tra timing của exception vì version conflict có thể được phát hiện khi flush hoặc commit.

### 17.3. Optimistic lock không khóa row từ lúc SELECT

Optimistic locking không lấy SELECT FOR UPDATE chỉ để đọc. Nó phát hiện xung đột ở thời điểm ghi thông qua version.

### 17.4. Xử lý exception

~~~java
@Transactional
public void changePrice(Long productId, BigDecimal newPrice) {
    Product product = productRepository.findById(productId)
        .orElseThrow();
    product.setPrice(newPrice);
}
~~~

Nếu version conflict, transaction cần rollback. Có thể yêu cầu người dùng tải lại dữ liệu hoặc retry toàn bộ business operation nếu nghiệp vụ cho phép.

### 17.5. Không tự retry một UPDATE cũ

Nếu transaction thất bại vì optimistic lock, dữ liệu mà business decision dựa vào đã cũ. Retry cần đọc lại state mới và tính toán lại quyết định, không chỉ gửi lại SQL cũ.

## 18. JPA pessimistic locking

Pessimistic locking dùng database lock để ngăn transaction khác sửa row trong khi ứng dụng xử lý.

### 18.1. @Lock(PESSIMISTIC_WRITE)

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

Khi gọi method trong transaction, JPA provider yêu cầu lock tương ứng. Với Oracle/Hibernate, SQL thường được dịch thành SELECT ... FOR UPDATE. Hãy bật SQL logging để xác nhận.

### 18.2. Service transaction

~~~java
@Transactional
public void withdraw(Long accountId, BigDecimal amount) {
    Account account = accountRepository.findByIdForUpdate(accountId)
        .orElseThrow();

    if (account.getBalance().compareTo(amount) < 0) {
        throw new InsufficientBalanceException();
    }

    account.debit(amount);
}
~~~

Row lock được giữ đến khi transaction commit/rollback. Không gọi dịch vụ thanh toán từ xa hoặc chờ người dùng xác nhận trong khi đang giữ lock.

### 18.3. LockModeType

| JPA lock mode | Mục đích |
| --- | --- |
| OPTIMISTIC | Kiểm tra optimistic lock trong transaction |
| OPTIMISTIC_FORCE_INCREMENT | Optimistic lock và tăng version |
| PESSIMISTIC_READ | Yêu cầu pessimistic read lock |
| PESSIMISTIC_WRITE | Yêu cầu pessimistic write lock |
| PESSIMISTIC_FORCE_INCREMENT | Pessimistic lock và tăng version |

SQL cụ thể phụ thuộc provider và dialect. Oracle thường sử dụng SELECT FOR UPDATE cho pessimistic row locking; không giả định PESSIMISTIC_READ tạo một shared row lock độc lập giống mọi database khác. Kiểm tra SQL thực tế.

### 18.4. Lock timeout hint

JPA có lock timeout hint:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "0"
    )
)
@Query("select a from Account a where a.id = :id")
Optional<Account> findByIdForUpdateNowait(@Param("id") Long id);
~~~

Giá trị và cách ánh xạ sang NOWAIT/WAIT phụ thuộc provider. Không giả định mọi JPA provider xử lý hint giống nhau. Nếu cần semantics Oracle cụ thể như SKIP LOCKED, native SQL có thể rõ ràng hơn.

## 19. JPA và Oracle SKIP LOCKED cho worker queue

SKIP LOCKED phù hợp với nhiều consumer cùng lấy jobs.

### 19.1. Native query

~~~java
@Repository
public interface JobQueueRepository extends JpaRepository<JobQueue, Long> {

    @Query(
        value = """
            SELECT *
            FROM job_queue
            WHERE status = 'READY'
            FOR UPDATE SKIP LOCKED
            """,
        nativeQuery = true
    )
    List<JobQueue> lockReadyJobs();
}
~~~

Đây là ví dụ minh họa cú pháp. Production query thường cần giới hạn số rows, order by, claim token và trạng thái xử lý theo đúng SQL grammar của Oracle release.

### 19.2. Transaction claim ngắn

Một worker nên:

1. Mở transaction.
2. Chọn và lock các jobs chưa bị lock.
3. Cập nhật trạng thái thành PROCESSING và lưu worker/lease.
4. Commit để nhả locks.
5. Thực hiện công việc bên ngoài transaction nếu có thể.
6. Mở transaction khác để ghi kết quả hoặc retry state.

Không giữ SELECT FOR UPDATE trong suốt thời gian gọi API bên ngoài nếu không cần.

### 19.3. SKIP LOCKED không thay lease

Nếu worker chết sau khi commit trạng thái PROCESSING, job có thể bị kẹt. Cần lease expiry, heartbeat hoặc recovery job để lấy lại công việc quá hạn.

## 20. Flush và lock timing: điều gì xảy ra thật?

Một lỗi thường gặp là nghĩ rằng row lock chỉ xuất hiện khi gọi commit. Thực tế, lock có thể được lấy ngay khi DML được thực thi, bao gồm khi Hibernate flush.

### 20.1. Ví dụ

~~~java
@Transactional
public void updateAndRead(Long id) {
    Account account = entityManager.find(Account.class, id);
    account.setBalance(account.getBalance().subtract(new BigDecimal("10")));

    // Tại đây entity có thể mới chỉ thay đổi trong memory.

    entityManager.flush();
    // Hibernate gửi UPDATE xuống Oracle.
    // Oracle lấy row lock và giữ đến transaction end.

    // Các công việc tiếp theo vẫn nằm trong transaction.
}
~~~

### 20.2. Lock duration

~~~text
BEGIN TRANSACTION
      |
      v
Modify managed entity
      |
      v
FLUSH -> UPDATE reaches Oracle
      |
      v
Oracle acquires row lock
      |
      v
More Java work / queries
      |
      v
COMMIT or ROLLBACK
      |
      v
Oracle releases lock
~~~

Khoảng thời gian từ flush đến commit/rollback là thời gian lock có thể được giữ.

### 20.3. Vì sao transaction dài nguy hiểm?

- Session khác phải chờ row locks.
- Undo/redo và transaction state tồn tại lâu hơn.
- Connection pool bị giữ connection.
- Deadlock dễ xảy ra khi nhiều transaction khóa rows theo thứ tự khác nhau.
- Khi ứng dụng gọi API bên ngoài, lock có thể bị giữ trong thời gian network timeout.

### 20.4. Giữ transaction ngắn

Không nên:

~~~java
@Transactional
public void processOrder(Long id) {
    Order order = orderRepository.findByIdForUpdate(id).orElseThrow();
    paymentGateway.callRemoteService(); // giữ lock trong lúc chờ network
    order.markPaid();
}
~~~

Hãy thiết kế quy trình dùng trạng thái/optimistic version hoặc chia transaction nếu nghiệp vụ cho phép. Nếu phải giữ lock trong toàn quy trình, cần đặt timeout và đánh giá tải/concurrency.

## 21. Oracle lock waits và lỗi thường gặp

### 21.1. ORA-00054

`ORA-00054: resource busy and acquire with NOWAIT specified` có thể xuất hiện khi `SELECT FOR UPDATE NOWAIT` hoặc thao tác lock yêu cầu NOWAIT gặp tài nguyên đang bị khóa.

Ứng dụng có thể trả lỗi conflict/retry theo policy. Không lặp NOWAIT liên tục trong tight loop.

### 21.2. ORA-00060

`ORA-00060: deadlock detected while waiting for resource` xảy ra khi các transaction chờ lẫn nhau tạo chu trình deadlock. Oracle phát hiện và rollback một statement trong chu trình để phá deadlock.

Giảm deadlock bằng cách:

- Khóa rows theo cùng một thứ tự trong mọi transaction.
- Giữ transaction ngắn.
- Tránh lock nhiều rows không cần thiết.
- Không giữ lock trong lúc gọi dịch vụ ngoài.
- Xử lý ORA-00060 và retry toàn bộ đơn vị nghiệp vụ phù hợp.

### 21.3. ORA-08177

`ORA-08177: Cannot serialize access for this transaction` xuất hiện trong SERIALIZABLE khi transaction muốn sửa dữ liệu đã bị transaction khác thay đổi và commit sau khi snapshot của transaction bắt đầu.

Ứng dụng thường cần rollback và retry toàn transaction với dữ liệu mới.

### 21.4. ORA-01555

`ORA-01555: snapshot too old` có thể xảy ra khi query/transaction cần undo record đã bị tái sử dụng. Long-running read-only report có thể gặp lỗi này nếu undo retention và workload không phù hợp.

Giải pháp gồm xem xét thời gian chạy query, undo sizing/retention, giảm transaction duration và tối ưu SQL. Không giải quyết bằng cách khóa toàn bộ bảng cho mọi báo cáo.

## 22. Điều tra blocker trong Oracle

Khi một request JPA chờ lâu, cần xác định session đang chờ gì và session nào đang block.

### 22.1. Tìm blocked sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    seconds_in_wait,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    row_wait_obj#,
    row_wait_file#,
    row_wait_block#,
    row_wait_row#
FROM v$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
~~~

### 22.2. Xem thông tin blocker

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    prev_sql_id,
    event,
    module,
    action,
    logon_time,
    last_call_et
FROM v$session
WHERE sid = :blocking_sid;
~~~

`BLOCKING_SESSION` là SID của session đang block. Trong RAC, cần xét `BLOCKING_INSTANCE` và dùng GV$SESSION để truy vấn đúng instance.

### 22.3. Xem object có DML lock

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    o.owner,
    o.object_name,
    lo.locked_mode
FROM v$locked_object lo
JOIN v$session s
  ON s.sid = lo.session_id
LEFT JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY s.sid, o.owner, o.object_name;
~~~

V$LOCKED_OBJECT hiển thị DML locks kiểu TM trên object và lock mode của table lock. Nó không phải danh sách đầy đủ từng row lock.

### 22.4. Xem TX/TM locks

~~~sql
SELECT
    l.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
ORDER BY l.type, l.sid;
~~~

V$LOCK hiển thị locks đang giữ và requests đang chờ. TX thường liên quan transaction enqueue; TM liên quan DML enqueue trên object.

### 22.5. V$SESSION_BLOCKERS

~~~sql
SELECT
    sid,
    sess_serial#,
    wait_event_text,
    blocker_instance_id,
    blocker_sid,
    blocker_sess_serial#
FROM v$session_blockers;
~~~

View này hiển thị các cặp blocked/blocker. Nếu không có quyền đọc các dynamic performance views, DBA cần cấp quyền phù hợp hoặc chạy truy vấn bằng tài khoản quản trị.

### 22.6. RAC và CDB

Trong RAC, dùng GV$SESSION, GV$LOCKED_OBJECT, GV$LOCK và giữ INST_ID khi join. Trong CDB, chú ý CON_ID để không trộn session giữa root và các PDB.

## 23. Ánh xạ hành vi JPA sang Oracle

| Java/JPA operation | SQL/database behavior có thể xảy ra | Lock implication |
| --- | --- | --- |
| `findById()` | SELECT | Không lấy row lock thông thường |
| Đổi field trên managed entity | Chỉ đổi memory trước flush | Chưa có DML lock chỉ vì setter |
| `save()` | Persist/merge; SQL có thể được hoãn | Lock khi DML thực sự chạy |
| `saveAndFlush()` | Persist/merge rồi flush | DML locks có thể bắt đầu tại flush |
| `entityManager.flush()` | Gửi pending INSERT/UPDATE/DELETE | Oracle lấy locks theo DML |
| `entityManager.clear()` | Detach managed entities | Không commit/rollback |
| `@Lock(PESSIMISTIC_WRITE)` | Thường SELECT FOR UPDATE với Oracle | Lock rows được chọn |
| `@Version` update | UPDATE với version predicate | Phát hiện xung đột khi ghi; không khóa từ lần đọc |
| `@Transactional(readOnly=true)` | Hint/optimization tùy manager/provider | Không mặc định cấm DML ở Oracle |
| Oracle SET TRANSACTION READ ONLY | Transaction-level snapshot, cấm DML | Không lấy row locks chỉ để đọc |

## 24. Thiết kế transaction và lock an toàn trong Spring Boot

### 24.1. Đọc dùng read-only

~~~java
@Service
public class ReportService {

    @Transactional(readOnly = true)
    public OrderSummary getSummary(LocalDate from, LocalDate to) {
        return orderRepository.calculateSummary(from, to);
    }
}
~~~

Đây là cách khai báo ý định đọc và cho phép Hibernate tối ưu. Nếu yêu cầu nhiều SELECT cùng snapshot Oracle, cần Oracle READ ONLY hoặc SERIALIZABLE transaction phù hợp.

### 24.2. Cập nhật bằng optimistic lock

~~~java
@Transactional
public void changeAddress(Long customerId, String address) {
    Customer customer = customerRepository.findById(customerId)
        .orElseThrow();
    customer.setAddress(address);
}
~~~

Entity có `@Version`; nếu transaction khác cập nhật trước, Hibernate phát hiện version conflict khi flush/commit.

### 24.3. Cập nhật bằng pessimistic lock

~~~java
@Transactional
public void reserveInventory(Long itemId, int quantity) {
    Inventory item = inventoryRepository.findByIdForUpdate(itemId)
        .orElseThrow();

    if (item.getAvailable() < quantity) {
        throw new InsufficientInventoryException();
    }

    item.reserve(quantity);
}
~~~

Dùng khi cần khóa row trước khi kiểm tra và cập nhật. Giữ phần xử lý bên trong transaction ngắn.

### 24.4. Xử lý checked exception

~~~java
@Transactional(rollbackFor = Exception.class)
public void settleOrder(Long orderId) throws Exception {
    // các bước cần rollback cả khi checked exception
}
~~~

Nếu không khai báo rollback rule, checked exception có thể không làm Spring rollback theo mặc định.

### 24.5. Retry ORA-08177

Retry nên được đặt ở boundary ngoài transaction đã rollback, ví dụ retry service method tạo transaction mới cho mỗi attempt. Không retry bên trong transaction đã bị lỗi serialization.

### 24.6. Retry lock wait

Đối với NOWAIT/lock timeout, có thể trả conflict cho client hoặc retry có backoff và giới hạn số lần. Không giữ transaction đang lỗi để tiếp tục xử lý.

## 25. Thực hành hai session để quan sát Oracle locks

Lab dưới đây dùng hai SQL sessions. Chạy trên schema lab, không dùng bảng production.

### Bước 1 — Tạo bảng

~~~sql
CREATE TABLE account_lock_lab (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL
);

INSERT INTO account_lock_lab(account_id, balance, version_no)
VALUES (1, 1000, 0);

COMMIT;
~~~

### Bước 2 — Session A cập nhật nhưng chưa commit

~~~sql
UPDATE account_lock_lab
SET balance = 900
WHERE account_id = 1;
~~~

Không COMMIT.

### Bước 3 — Session B SELECT bình thường

~~~sql
SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

Session B có thể đọc giá trị đã commit trước đó là 1000 nhờ read consistency. SELECT thông thường không chờ row lock của A.

### Bước 4 — Session B UPDATE cùng row

~~~sql
UPDATE account_lock_lab
SET balance = 800
WHERE account_id = 1;
~~~

Session B chờ Session A nhả lock.

### Bước 5 — Session A COMMIT

~~~sql
COMMIT;
~~~

Sau đó Session B có thể tiếp tục thực hiện UPDATE theo quy tắc READ COMMITTED. Kiểm tra giá trị cuối sau khi B commit.

### Bước 6 — Thử SELECT FOR UPDATE NOWAIT

Session A:

~~~sql
SELECT *
FROM account_lock_lab
WHERE account_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
SELECT *
FROM account_lock_lab
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

Session B nhận lỗi ngay nếu A đang giữ lock xung đột.

### Bước 7 — Thử SERIALIZABLE

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

Session B cập nhật và commit row đó. Sau đó Session A thử UPDATE row đã bị B thay đổi. Quan sát ORA-08177 theo điều kiện serialization conflict.

### Bước 8 — Thử READ ONLY

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

Từ session khác, update và commit row. Query tiếp theo của read-only transaction vẫn nhìn snapshot cũ. Thử UPDATE trong read-only transaction để quan sát Oracle từ chối DML.

## 26. Thực hành Spring Boot/JPA

### Bước 1 — Entity có version

~~~java
@Entity
@Table(name = "ACCOUNT_LOCK_LAB")
public class Account {

    @Id
    @Column(name = "ACCOUNT_ID")
    private Long id;

    @Column(name = "BALANCE")
    private BigDecimal balance;

    @Version
    @Column(name = "VERSION_NO")
    private Long version;

    public void debit(BigDecimal amount) {
        this.balance = this.balance.subtract(amount);
    }
}
~~~

### Bước 2 — Repository optimistic/pessimistic

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findForUpdate(@Param("id") Long id);
}
~~~

### Bước 3 — Read-only service

~~~java
@Transactional(readOnly = true)
public AccountView getAccount(Long id) {
    Account account = accountRepository.findById(id)
        .orElseThrow();
    return AccountView.from(account);
}
~~~

### Bước 4 — Pessimistic update

~~~java
@Transactional
public void debit(Long id, BigDecimal amount) {
    Account account = accountRepository.findForUpdate(id)
        .orElseThrow();

    if (account.getBalance().compareTo(amount) < 0) {
        throw new InsufficientBalanceException();
    }

    account.debit(amount);
    // SQL UPDATE có thể flush trước commit.
}
~~~

### Bước 5 — Quan sát SQL

Bật Hibernate SQL logging trong môi trường lab và xác nhận:

- Query read-only không sinh DML ngoài dự kiến.
- `findForUpdate` sinh SQL có FOR UPDATE.
- UPDATE được gửi khi flush/commit.
- Lock tồn tại cho đến transaction end.

Không bật bind-value logging trong production nếu parameter có dữ liệu nhạy cảm.

### Bước 6 — Kiểm thử hai request đồng thời

1. Request A lấy PESSIMISTIC_WRITE và giữ transaction.
2. Request B gọi cùng method.
3. Quan sát B chờ lock.
4. A commit.
5. B tiếp tục hoặc nhận timeout theo cấu hình.
6. Lặp lại với `@Version` để quan sát OptimisticLockException thay vì giữ lock từ lần đọc.

## 27. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@Transactional(readOnly=true)` vẫn ghi được | Read-only chỉ là hint | Dùng database privilege hoặc Oracle-enforced read-only |
| Entity thay đổi nhưng không UPDATE | Hibernate MANUAL flush trong read-only transaction hoặc entity detached | Kiểm tra transaction metadata, flush mode và managed state |
| `save()` chưa thấy SQL trong log | SQL được hoãn tới flush/commit | Dùng flush khi thật sự cần và kiểm tra transaction |
| `saveAndFlush()` xong session khác chưa thấy dữ liệu | Flush không commit | Commit transaction |
| Query trước commit thấy entity mới trong cùng session | Persistence context/flush semantics | Phân biệt entity state với visibility ở session khác |
| Session khác SELECT vẫn đọc giá trị cũ | Oracle MVCC đọc phiên bản đã commit | Đây là behavior bình thường khi writer chưa commit |
| UPDATE bị chờ | Row lock bởi transaction khác | Xem V$SESSION blocker và transaction owner |
| ORA-00054 | NOWAIT gặp lock xung đột | Trả conflict hoặc retry có backoff |
| ORA-00060 | Deadlock | Kiểm tra thứ tự khóa và rút ngắn transaction |
| ORA-08177 | Serializable conflict | Rollback và retry toàn transaction |
| ORA-01555 | Undo cần cho consistent read đã bị reuse | Tối ưu query, thời gian chạy và undo retention |
| Pessimistic lock không hoạt động như mong đợi | Transaction không active hoặc provider SQL khác | Kiểm tra proxy, transaction manager và generated SQL |
| Lock tồn tại sau `flush()` | Flush không giải phóng lock | Commit/rollback |
| Self-invocation bỏ qua transaction | Lời gọi không qua Spring proxy | Tách bean hoặc dùng cơ chế weaving phù hợp |
| Isolation trên method trong không có hiệu lực | Method tham gia transaction ngoài | Kiểm tra propagation và existing transaction |
| Bulk JPQL update nhưng entity vẫn giá trị cũ | Bulk DML bypass persistence context | Flush/clear/refresh theo đúng use case |

## 28. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| `@Transactional(readOnly=true)` cấm UPDATE ở Oracle | Nó thường là hint/provider optimization, không phải database enforcement mặc định |
| `Connection.setReadOnly(true)` tương đương SET TRANSACTION READ ONLY | Oracle JDBC xem đó là hint; server không tự enforce theo cách này |
| READ COMMITTED giữ snapshot cho cả transaction | Mỗi statement có snapshot riêng |
| Oracle có READ UNCOMMITTED và REPEATABLE READ như database khác | Oracle server hỗ trợ READ COMMITTED và SERIALIZABLE; READ ONLY là transaction mode riêng |
| SELECT bình thường khóa các rows đã đọc | Oracle MVCC cho phép SELECT đọc consistent version mà không row-lock |
| UPDATE chỉ khóa row khi COMMIT | Row lock được lấy khi DML thực thi |
| `flush()` là commit | Flush chỉ gửi pending SQL xuống database |
| `save()` luôn phát SQL ngay | SQL có thể được hoãn tới flush |
| `saveAndFlush()` đã commit | Nó không commit transaction |
| Đóng cursor giải phóng SELECT FOR UPDATE lock | Lock giữ đến commit/rollback |
| `@Version` khóa row từ lúc đọc | Optimistic locking phát hiện conflict khi ghi |
| PESSIMISTIC_WRITE chỉ là metadata Java | Provider yêu cầu database lock, thường bằng SELECT FOR UPDATE |
| `readOnly=true` và `Isolation.SERIALIZABLE` là một | Một bên là hint/access intent, một bên là isolation semantics |
| Method isolation luôn override transaction ngoài | Method tham gia transaction hiện hữu có thể không đổi isolation |
| ORA-08177 là lock timeout | Nó là serialization conflict |
| V$LOCKED_OBJECT cho biết từng row đang bị khóa | Nó hiển thị DML object/table locks; row contention cần xem TX/V$SESSION |

## 29. Checklist triển khai

**Transaction boundary**

- Transaction được đặt ở service method đại diện một business operation?
- Lời gọi có đi qua Spring proxy?
- Ai sở hữu commit/rollback?
- Checked exception có cần rollbackFor không?
- Transaction có giữ connection hoặc lock quá lâu không?

**Read-only**

- Method thực sự chỉ đọc?
- Read-only được dùng như hint hay cần database enforcement?
- Transaction manager có hỗ trợ enforcement không?
- Có cần Oracle transaction-level snapshot cho báo cáo không?
- Database user có quyền tối thiểu phù hợp không?

**Isolation**

- Oracle default READ COMMITTED có đủ không?
- Có cần SERIALIZABLE không?
- Đã xử lý ORA-08177 và retry chưa?
- Isolation annotation có đang tham gia transaction ngoài không?
- Có nhầm Spring REPEATABLE_READ với Oracle mode không?

**Flush**

- Flush mode hiện tại là gì?
- SQL phát sinh tại save, query, explicit flush hay commit?
- Có flush quá thường xuyên không?
- Có gọi clear trước khi flush không?
- Bulk JPQL/native DML có làm persistence context stale không?

**Locking**

- Optimistic hay pessimistic lock phù hợp?
- PESSIMISTIC_WRITE có giữ lock quá lâu không?
- Có cần NOWAIT/WAIT/SKIP LOCKED không?
- Các transaction có khóa rows theo thứ tự nhất quán không?
- Có theo dõi blocking session và deadlock không?

## 30. Câu hỏi tự kiểm tra

1. Spring `@Transactional(readOnly=true)` có mặc định cấm DML ở Oracle không?
2. Hibernate được Spring tối ưu thế nào với read-only transaction?
3. Oracle `SET TRANSACTION READ ONLY` phải được gọi lúc nào?
4. Oracle read-only transaction nhìn thấy snapshot nào?
5. `Connection.setReadOnly(true)` có tương đương Oracle read-only transaction không?
6. Oracle default isolation level là gì?
7. READ COMMITTED lấy snapshot ở cấp nào?
8. SERIALIZABLE lấy snapshot ở cấp nào?
9. ORA-08177 có ý nghĩa gì?
10. Oracle có hỗ trợ READ UNCOMMITTED và REPEATABLE READ như JDBC modes riêng không?
11. `@Transactional` mặc định dùng propagation nào?
12. Self-invocation ảnh hưởng transaction proxy ra sao?
13. Isolation của method REQUIRED trong có luôn override transaction ngoài không?
14. Spring mặc định rollback với loại exception nào?
15. Persistence context là gì?
16. Dirty checking thực hiện việc gì?
17. Flush có commit transaction không?
18. Flush có thể lấy Oracle row locks không?
19. Khi nào Hibernate có thể auto flush?
20. MANUAL flush mode có ý nghĩa gì?
21. `save()` khác `saveAndFlush()` thế nào?
22. `clear()` ảnh hưởng managed entities ra sao?
23. Bulk JPQL UPDATE có cập nhật entity đang managed không?
24. Oracle SELECT thông thường có lấy row locks không?
25. Vì sao SELECT có thể đọc row đang bị UPDATE chưa commit?
26. Oracle DML locks được giữ đến khi nào?
27. SELECT FOR UPDATE khóa rows vào thời điểm nào?
28. NOWAIT, WAIT và SKIP LOCKED khác nhau thế nào?
29. Optimistic locking với `@Version` hoạt động ra sao?
30. PESSIMISTIC_WRITE thường được dịch thành SQL gì trên Oracle?
31. V$LOCKED_OBJECT hiển thị loại lock nào?
32. Wait event `enq: TX - row lock contention` biểu thị điều gì?
33. ORA-00054 và ORA-00060 khác nhau thế nào?
34. Vì sao transaction dài làm tăng lock contention?
35. Khi nào nên dùng Oracle READ ONLY transaction thay readOnly hint?

**Gợi ý trả lời:**

1. Không; readOnly là hint/provider optimization, không phải database enforcement mặc định.
2. Spring Data JPA có thể đặt Hibernate FlushMode.MANUAL để giảm dirty checking/auto flush.
3. Là câu SQL đầu tiên của transaction.
4. Các thay đổi đã commit trước khi transaction bắt đầu.
5. Không; Oracle JDBC xem đó là hint, không phải server-enforced read-only transaction.
6. READ COMMITTED.
7. Mỗi statement.
8. Toàn transaction.
9. Serializable transaction gặp thay đổi xung đột đã commit sau khi snapshot bắt đầu.
10. Không; Oracle server hỗ trợ READ COMMITTED và SERIALIZABLE, cùng READ ONLY transaction mode.
11. REQUIRED.
12. Lời gọi nội bộ không qua proxy nên annotation có thể không được intercept.
13. Không; method tham gia transaction ngoài có thể dùng isolation của transaction ngoài.
14. RuntimeException và Error, trừ khi rollback rules được cấu hình khác.
15. Vùng JPA quản lý entity managed và trạng thái của chúng.
16. Phát hiện thay đổi entity để tạo DML khi flush.
17. Không.
18. Có, khi DML thực sự được gửi xuống Oracle.
19. Trước commit và trước query có thể bị ảnh hưởng bởi pending changes theo AUTO mode.
20. Provider không tự flush theo cách thông thường; ứng dụng phải yêu cầu khi cần.
21. save persist/merge; saveAndFlush còn yêu cầu flush; cả hai không tự commit transaction.
22. Detach toàn bộ entity đang managed.
23. Không tự đồng bộ các object managed trong persistence context.
24. Không.
25. Oracle dùng MVCC/undo để dựng phiên bản đã commit.
26. Commit hoặc rollback.
27. Khi cursor được mở, trước fetch.
28. NOWAIT trả lỗi ngay; WAIT chờ tối đa n giây; SKIP LOCKED bỏ qua rows đang bị lock.
29. Version predicate phát hiện dữ liệu đã bị transaction khác cập nhật.
30. Thường là SELECT ... FOR UPDATE, tùy provider/dialect.
31. DML table/object locks kiểu TM và mode của chúng.
32. Session đang chờ transaction khác giải phóng row-level lock.
33. ORA-00054 là resource busy với NOWAIT; ORA-00060 là deadlock.
34. Vì locks được giữ suốt transaction, bao gồm thời gian ứng dụng chờ ngoài database.
35. Khi nhiều query trong một report cần cùng một snapshot Oracle và DML phải bị database cấm.

## Tài liệu Spring, JPA và Oracle tham khảo

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): read-only hint, Hibernate MANUAL flush mode và transaction boundaries.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, isolation, rollback rules và proxy/self-invocation.
- [Spring Framework — DataSourceTransactionManager.setEnforceReadOnly](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): enforce read-only bằng `SET TRANSACTION READ ONLY`.
- [Oracle Database 19c SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): READ ONLY, READ COMMITTED và SERIALIZABLE.
- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): MVCC, read consistency, isolation và ORA-08177.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): FOR UPDATE, NOWAIT, WAIT và SKIP LOCKED.
- [Oracle Database 19c SQL Processing for Application Developers](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html): locking và read consistency.
- [Oracle Database 19c JDBC Coding Tips](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-coding-tips.html): Oracle JDBC isolation levels và read-only access mode.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): blocking session và row wait information.
- [Oracle Database 19c Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): TX/TM locks và lock modes.
- [Oracle Database 19c Database Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): DML object locks.
- [Oracle Database 19c Database Reference — V$SESSION_BLOCKERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION_BLOCKERS.html): blocked/blocker session pairs.

**Nguyên tắc cần nhớ:** Spring readOnly là hint tối ưu, còn Oracle `SET TRANSACTION READ ONLY` mới là chế độ database-enforced với snapshot ở cấp transaction. Oracle mặc định READ COMMITTED, mỗi statement có snapshot riêng; SERIALIZABLE và READ ONLY giữ snapshot cho cả transaction. JPA flush gửi DML xuống Oracle nhưng không commit; row locks được lấy khi DML thực thi và giữ tới commit/rollback. SELECT thông thường đọc bằng MVCC và không khóa rows. Dùng `@Version` khi phù hợp với optimistic locking, `PESSIMISTIC_WRITE`/SELECT FOR UPDATE khi cần khóa row thật, và luôn giữ transaction ngắn. Khi có contention, điều tra blocker qua V$SESSION, V$LOCK, V$LOCKED_OBJECT và xử lý ORA-00054, ORA-00060, ORA-08177 theo đúng nguyên nhân.
