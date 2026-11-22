# Propagation, mức cô lập và giới hạn trình điều khiển

Giao dịch (transaction) gom nhiều thao tác database thành một đơn vị công việc có quy tắc commit hoặc rollback. Trong Spring Data Relational R2DBC, giao dịch còn phải tuân theo mô hình reactive: connection được gắn với reactive execution context, các thao tác phải nằm trong cùng publisher chain và việc kết thúc subscription quyết định khi nào transaction được hoàn tất.

Hai nhóm cấu hình quan trọng là **propagation** và **isolation**. Propagation quyết định một phương thức tham gia transaction đang có, tạo transaction mới, tạm ngưng transaction hiện tại hay yêu cầu một trạng thái transaction cụ thể. Isolation quyết định mức độ mà transaction nhìn thấy thay đổi của transaction khác và những bất thường đọc/ghi nào database phải ngăn chặn.

Các cấu hình này không hoạt động độc lập với database. Spring có thể yêu cầu một mức isolation hoặc thao tác savepoint, nhưng driver và hệ quản trị phải hỗ trợ. Một số tính năng chỉ được hỗ trợ một phần, có semantics khác nhau hoặc bị từ chối khi chạy.

Bài học này trình bày propagation trong Spring reactive transaction, các mức isolation, cách cấu hình bằng `@Transactional` và `TransactionalOperator`, vai trò của Reactor Context, các giới hạn của driver/database và cách kiểm thử transaction trong ứng dụng R2DBC.

## 1. Transaction trong ứng dụng R2DBC

Một transaction thường bao gồm một hoặc nhiều câu lệnh SQL. Khi tất cả thao tác thành công, transaction commit. Nếu một thao tác thất bại hoặc nghiệp vụ quyết định hủy, transaction rollback.

Ví dụ tạo đơn hàng cần lưu cả đơn hàng và các dòng chi tiết:

~~~text
BEGIN
  |
  +-- INSERT purchase_order
  |
  +-- INSERT purchase_order_item
  |
  +-- UPDATE inventory
  |
  +-- tất cả thành công?
          |
          +-- Có --> COMMIT
          |
          +-- Không --> ROLLBACK
~~~

Nếu đơn hàng được lưu nhưng cập nhật kho thất bại, transaction giúp database không giữ lại một phần trạng thái của use case.

Trong Spring Data R2DBC, transaction manager thường là `R2dbcTransactionManager`. Nó quản lý một R2DBC `Connection` lấy từ `ConnectionFactory` và gắn connection đó vào reactive context để các thao tác database cùng tham gia transaction.

Luồng tổng quát:

~~~text
Service method trả Mono/Flux
        |
        v
Reactive transaction interceptor
        |
        v
R2dbcTransactionManager
        |
        v
ConnectionFactory / Connection
        |
        v
Reactor Context giữ transaction resource
        |
        v
Repository / DatabaseClient dùng connection đó
        |
        v
COMMIT hoặc ROLLBACK
~~~

Một transaction reactive không được quản lý bằng cách giữ thread cố định. Các operator có thể chạy trên thread khác nhau; transaction context được truyền theo Reactor Context.

## 2. Propagation là gì?

Propagation xác định cách một phương thức transactional xử lý khi nó được gọi bên trong một luồng công việc đã có transaction.

Ví dụ service A gọi service B:

~~~text
Service A
  |
  +-- bắt đầu transaction?
  |
  +-- gọi Service B
          |
          +-- tham gia transaction của A?
          +-- tạo transaction độc lập?
          +-- tạm ngưng transaction của A?
          +-- yêu cầu transaction phải có sẵn?
~~~

Propagation không quyết định isolation level. Một phương thức có thể dùng `REQUIRED` với `READ_COMMITTED`, hoặc `REQUIRES_NEW` với `SERIALIZABLE`, tùy cấu hình và khả năng database.

Spring định nghĩa các propagation behavior phổ biến sau:

| Propagation | Khi đã có transaction | Khi chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại | Tạo transaction mới |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện tại và tạo transaction mới | Tạo transaction mới |
| `SUPPORTS` | Tham gia transaction hiện tại | Chạy không có transaction |
| `MANDATORY` | Tham gia transaction hiện tại | Ném lỗi vì không có transaction |
| `NOT_SUPPORTED` | Tạm ngưng transaction hiện tại và chạy không transaction | Chạy không có transaction |
| `NEVER` | Ném lỗi vì đã có transaction | Chạy không có transaction |
| `NESTED` | Tạo nested scope bằng savepoint nếu được hỗ trợ | Bắt đầu transaction mới |

Cần phân biệt `REQUIRES_NEW` với `NESTED`: transaction mới có thể commit độc lập với transaction bên ngoài; nested transaction dùng savepoint bên trong transaction hiện tại và không thể commit độc lập khỏi transaction cha.

## 3. REQUIRED: tham gia hoặc tạo transaction

`REQUIRED` là propagation mặc định của `@Transactional`.

- Nếu caller đã có transaction, phương thức tham gia transaction đó.
- Nếu chưa có transaction, phương thức bắt đầu transaction mới.
- Nếu một phương thức tham gia transaction chung phát lỗi làm transaction rollback, toàn bộ đơn vị công việc chung có thể bị rollback.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    @Transactional
    public Mono<Order> placeOrder(Order order) {
        return orderRepository.save(order)
                .flatMap(saved ->
                        inventoryService.reserve(saved)
                                .thenReturn(saved));
    }
}
~~~

Nếu `inventoryService.reserve(...)` cũng chạy trong transaction `REQUIRED` được quản lý bởi cùng transaction manager, thao tác lưu đơn hàng và giữ kho tham gia cùng transaction.

`REQUIRED` phù hợp khi các bước là một đơn vị nghiệp vụ: hoặc tất cả cùng thành công, hoặc tất cả cùng rollback.

### 3.1. Transaction tham gia có thể bị rollback-only

Giả sử service A mở transaction rồi gọi service B. Service B tham gia transaction hiện tại và đánh dấu rollback-only hoặc phát lỗi khiến transaction bị rollback. Service A không thể tự commit transaction đó chỉ bằng cách bắt lỗi ở phía ngoài.

Một số trường hợp Spring có thể báo `UnexpectedRollbackException` khi outer scope cố commit một transaction đã bị đánh dấu rollback-only. Vì vậy, không nên cho rằng bắt exception ở caller luôn phục hồi được transaction.

Nếu lỗi của bước phụ có thể được bỏ qua, hãy xác định rõ liệu transaction chung có còn hợp lệ hay không. Nếu bước đó cần độc lập, cân nhắc `REQUIRES_NEW` hoặc thiết kế lại ranh giới use case.

## 4. REQUIRES_NEW: transaction độc lập

`REQUIRES_NEW` yêu cầu một transaction độc lập. Nếu đang có transaction bên ngoài, Spring tạm ngưng transaction đó và bắt đầu transaction mới cho phương thức được gọi.

Ví dụ ghi audit cần tồn tại ngay cả khi use case chính rollback:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Mono<AuditRecord> recordAttempt(AuditRecord record) {
        return auditRepository.save(record);
    }
}
~~~

Giả sử luồng gọi:

~~~text
Transaction A: đặt đơn hàng
    |
    +-- gọi AuditService
            |
            +-- suspend A
            |
            +-- Transaction B: lưu audit
            |
            +-- COMMIT B
    |
    +-- bước đặt hàng thất bại
    |
    +-- ROLLBACK A
~~~

Audit trong B có thể vẫn tồn tại dù A rollback, vì B là transaction độc lập.

### 4.1. REQUIRES_NEW có chi phí connection

Transaction A có thể đang giữ một connection. Khi B bắt đầu, pool thường cần cấp một connection khác. Nếu pool quá nhỏ và nhiều request cùng giữ transaction ngoài rồi chờ transaction trong, hệ thống có thể cạn connection hoặc chờ cấp connection kéo dài.

Ví dụ pool có số connection tối đa bằng số request đang xử lý; mỗi request giữ một connection cho transaction ngoài rồi yêu cầu thêm một connection cho `REQUIRES_NEW`. Không còn connection trống để cấp cho transaction trong.

Vì vậy:

- Dùng `REQUIRES_NEW` có chủ đích, cho công việc thực sự độc lập.
- Đặt giới hạn thời gian và kích thước pool phù hợp workload.
- Tránh lồng nhiều tầng `REQUIRES_NEW` không cần thiết.
- Kiểm thử dưới tải để phát hiện pool starvation.
- Không dựa vào transaction trong để đọc dữ liệu chưa commit của transaction ngoài.

Transaction B không nhìn thấy các thay đổi chưa commit của A theo cách thông thường. Nếu B cần dữ liệu vừa tạo trong A, hãy truyền giá trị cần thiết qua tham số và tránh thiết kế phụ thuộc vào việc B đọc dữ liệu chưa commit.

## 5. NESTED: dùng savepoint bên trong transaction

`NESTED` biểu diễn một phạm vi con trong transaction hiện tại bằng savepoint, nếu transaction manager và driver hỗ trợ.

~~~text
BEGIN transaction A
  |
  +-- thao tác A1
  |
  +-- SAVEPOINT nested_B
  |      |
  |      +-- thao tác B1
  |      +-- thao tác B2 thất bại
  |      |
  |      +-- ROLLBACK TO SAVEPOINT nested_B
  |
  +-- thao tác A2
  |
  +-- COMMIT transaction A
~~~

Rollback nested scope có thể hoàn tác các thay đổi sau savepoint mà vẫn giữ các thay đổi trước đó trong transaction cha. Nhưng transaction cha vẫn quyết định commit hay rollback cuối cùng.

Ví dụ:

~~~java
@Transactional(propagation = Propagation.NESTED)
public Mono<Void> addOptionalDetails(Long orderId) {
    return detailRepository.save(buildDetails(orderId))
            .then();
}
~~~

Đoạn code chỉ hoạt động như nested transaction nếu transaction manager/driver hỗ trợ savepoint cho trường hợp này. Nếu không, Spring có thể báo lỗi hỗ trợ nested transaction không khả dụng.

### 5.1. NESTED khác REQUIRES_NEW

| Đặc điểm | `NESTED` | `REQUIRES_NEW` |
|---|---|---|
| Cơ chế | Savepoint trong transaction hiện tại | Transaction độc lập |
| Commit | Chỉ commit cùng transaction cha | Có thể commit độc lập |
| Rollback | Có thể rollback về savepoint | Rollback transaction mới |
| Connection | Thường dùng connection của transaction cha | Cần transaction/connection độc lập |
| Hỗ trợ | Cần savepoint | Cần khả năng suspend và tạo transaction mới |
| Khi transaction cha rollback | Thay đổi nested cũng rollback | Transaction trong đã commit vẫn có thể tồn tại |

Không dùng `NESTED` như cách thay thế phổ quát cho `REQUIRES_NEW`. Chúng có semantics khác nhau.

## 6. Các propagation còn lại

### 6.1. SUPPORTS

`SUPPORTS` tham gia transaction nếu caller đã có transaction. Nếu không có, phương thức chạy không transaction.

Dùng khi một thao tác đọc có thể hưởng lợi từ transaction hiện tại nhưng không bắt buộc phải tự mở transaction.

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Không nên dựa vào `SUPPORTS` để bảo đảm nhiều câu SELECT luôn nhìn thấy cùng một snapshot nếu caller không có transaction.

### 6.2. MANDATORY

`MANDATORY` yêu cầu caller phải cung cấp transaction. Nếu không có transaction hiện tại, Spring báo lỗi.

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public Mono<Void> updateBalance(Long accountId, BigDecimal amount) {
    return accountRepository.addBalance(accountId, amount);
}
~~~

Có thể dùng để bảo vệ một thao tác chỉ được gọi bên trong use case transactional lớn hơn. Nó giúp phát hiện việc gọi service sai ngữ cảnh.

### 6.3. NOT_SUPPORTED

`NOT_SUPPORTED` yêu cầu chạy ngoài transaction. Nếu đang có transaction, Spring tạm ngưng transaction đó trong thời gian thực thi phương thức.

Dùng khi một thao tác không nên tham gia transaction đang mở, ví dụ một công việc độc lập không cần cùng tính nguyên tử. Tuy nhiên, cần nhớ rằng thao tác database chạy ngoài transaction có thể được thực thi theo auto-commit hoặc semantics mặc định của connection.

Không dùng `NOT_SUPPORTED` để tránh lỗi transaction mà không hiểu tác động dữ liệu. Nếu thao tác cần commit/rollback rõ ràng, hãy thiết kế một transaction riêng.

### 6.4. NEVER

`NEVER` yêu cầu không có transaction. Nếu caller đã có transaction, phương thức thất bại.

~~~java
@Transactional(propagation = Propagation.NEVER)
public Mono<SystemStatus> loadExternalStatus() {
    return statusRepository.findCurrentStatus();
}
~~~

Nó hữu ích khi một phương thức không được phép chạy trong transaction, chẳng hạn do công việc có thời gian dài hoặc có tác dụng phụ không thể rollback. Nếu phương thức vẫn truy cập R2DBC database, hãy xác định rõ semantics của thao tác khi không có transaction.

## 7. Isolation là gì?

Isolation mô tả mức độ một transaction bị ảnh hưởng bởi các thay đổi chưa hoặc đã được commit từ transaction khác. Khi nhiều transaction chạy đồng thời, database phải cân bằng tính nhất quán, mức song song và hiệu năng.

Một số bất thường đọc/ghi thường được nhắc tới:

| Bất thường | Ý nghĩa |
|---|---|
| Dirty read | Đọc dữ liệu do transaction khác ghi nhưng chưa commit |
| Non-repeatable read | Đọc cùng một hàng hai lần trong một transaction nhưng nhận giá trị khác |
| Phantom read | Chạy lại cùng điều kiện truy vấn và thấy tập hàng phù hợp thay đổi |
| Lost update | Một cập nhật ghi đè thay đổi của transaction khác do thiếu cơ chế phối hợp |
| Write skew | Các transaction đọc cùng trạng thái rồi ghi các hàng khác nhau, làm vi phạm bất biến tổng thể |

Ba bất thường đầu là các khái niệm chuẩn dùng để mô tả isolation level. Lost update và write skew còn phụ thuộc cách truy vấn, khóa và triển khai database; không nên cho rằng chỉ chọn một isolation level là giải quyết mọi xung đột nghiệp vụ.

## 8. Các mức isolation phổ biến

Spring định nghĩa các mức isolation tương ứng với transaction definition:

| Isolation | Dirty read | Non-repeatable read | Phantom read | Đặc điểm |
|---|---|---|---|---|
| `READ_UNCOMMITTED` | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra | Mức thấp nhất; nhiều DB ánh xạ sang mức cao hơn |
| `READ_COMMITTED` | Bị ngăn | Có thể xảy ra | Có thể xảy ra | Mỗi statement chỉ đọc dữ liệu đã commit |
| `REPEATABLE_READ` | Bị ngăn | Bị ngăn theo chuẩn | Có thể xảy ra theo chuẩn | Đọc lại cùng hàng ổn định trong transaction; chi tiết phụ thuộc DB |
| `SERIALIZABLE` | Bị ngăn | Bị ngăn | Bị ngăn theo semantics serializable | Mức mạnh nhất; có thể gây lỗi serialization và cần retry |
| `DEFAULT` | Theo DB | Theo DB | Theo DB | Dùng mức mặc định của database/connection |

Bảng mô tả semantics theo mô hình isolation chuẩn. Cơ chế MVCC, locking và cách hiện thực của từng database có thể mạnh hơn hoặc khác chi tiết so với mô tả khái quát.

### 8.1. READ_UNCOMMITTED

Mức này cho phép đọc dữ liệu chưa commit theo mô hình chuẩn. Điều đó có thể tạo dirty read: transaction A đọc giá trị do B ghi, sau đó B rollback.

Nhiều hệ quản trị không cung cấp dirty read thực sự. Ví dụ, PostgreSQL coi `READ_UNCOMMITTED` như `READ_COMMITTED`. Vì vậy, việc yêu cầu mức này không có nghĩa mọi database đều thực hiện đúng hành vi dirty read.

Không nên chọn mức thấp nhất chỉ để tăng hiệu năng nếu nghiệp vụ phụ thuộc dữ liệu đã commit.

### 8.2. READ_COMMITTED

`READ_COMMITTED` ngăn dirty read. Một statement chỉ thấy dữ liệu đã commit theo semantics của database.

Tuy nhiên, hai lần SELECT trong cùng transaction có thể thấy trạng thái khác nhau:

~~~text
Transaction A                    Transaction B
-------------                    -------------
SELECT balance = 100
                                 UPDATE balance = 80
                                 COMMIT
SELECT balance = 80
~~~

Đây là non-repeatable read. Với truy vấn theo điều kiện, một hàng mới có thể xuất hiện giữa hai lần đọc, tạo phantom theo mô hình chuẩn.

Đây là mức mặc định phổ biến ở nhiều database, nhưng cần xác nhận cấu hình thực tế của hệ thống.

### 8.3. REPEATABLE_READ

`REPEATABLE_READ` nhằm bảo đảm đọc lại cùng hàng trong transaction không thấy giá trị đã bị transaction khác commit thay đổi theo mô hình chuẩn. Cách xử lý phantom phụ thuộc database.

Ví dụ nghiệp vụ tính tổng số dư của các tài khoản rồi kiểm tra ngưỡng. Nếu các hàng thay đổi giữa hai truy vấn, kết quả tổng có thể khác. Cần hiểu database đang dùng snapshot isolation, locking hay một biến thể khác.

Trong PostgreSQL, `REPEATABLE READ` dùng snapshot transaction và ngăn các phantom theo cách thường được mô tả trong chuẩn; các DB khác có semantics và cơ chế khác. Không suy luận hành vi từ tên isolation mà không kiểm tra tài liệu database.

### 8.4. SERIALIZABLE

`SERIALIZABLE` yêu cầu kết quả của các transaction đồng thời tương đương với một thứ tự chạy tuần tự nào đó. Đây là mức bảo vệ mạnh, nhưng không có nghĩa mọi transaction đều chắc chắn thành công.

Database có thể từ chối một transaction vì xung đột serialization. Ứng dụng cần sẵn sàng retry toàn bộ transaction khi gặp lỗi serialization phù hợp.

Retry phải có kiểm soát:

- Giới hạn số lần thử.
- Dùng backoff có giới hạn nếu phù hợp.
- Chỉ retry lỗi được nhận diện là transient/serialization conflict.
- Bảo đảm tác dụng phụ bên ngoài database không bị thực hiện lặp.
- Dùng idempotency key hoặc outbox cho tác dụng phụ cần bảo đảm.

Không retry mọi lỗi SQL hoặc lỗi nghiệp vụ.

## 9. Chọn isolation bằng @Transactional

Có thể khai báo propagation và isolation bằng annotation:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final AccountRepository accountRepository;

    @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED)
    public Mono<Account> deposit(Long accountId, BigDecimal amount) {
        return accountRepository.findById(accountId)
                .switchIfEmpty(Mono.error(
                        new AccountNotFoundException(accountId)))
                .flatMap(account -> {
                    account.setBalance(account.getBalance().add(amount));
                    return accountRepository.save(account);
                });
    }
}
~~~

Khi dùng R2DBC, cần bảo đảm transaction manager là reactive manager phù hợp, thường là `R2dbcTransactionManager` được cấu hình với cùng `ConnectionFactory` mà repository sử dụng.

Ví dụ cấu hình:

~~~java
@Bean
R2dbcTransactionManager r2dbcTransactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Nếu ứng dụng có nhiều transaction manager, chỉ rõ tên manager trong annotation:

~~~java
@Transactional(
        transactionManager = "r2dbcTransactionManager",
        isolation = Isolation.REPEATABLE_READ)
public Mono<Report> createReport() {
    // reactive database operations
}
~~~

Nếu chọn một isolation level mà database/driver không hỗ trợ, transaction có thể thất bại khi bắt đầu hoặc khi áp dụng cấu hình. Cần kiểm tra trên môi trường thực tế.

### 9.1. Isolation của transaction tham gia

Khi phương thức `REQUIRED` tham gia một transaction đã tồn tại, cấu hình isolation trên phương thức bên trong không nhất thiết thay đổi isolation của transaction đang chạy.

Ví dụ outer transaction đã bắt đầu ở `READ_COMMITTED`, inner method khai báo `REPEATABLE_READ` nhưng dùng `REQUIRED`. Inner method tham gia transaction hiện tại; không nên kỳ vọng nó tự nâng isolation của transaction cha.

Hãy cấu hình isolation ở ranh giới bắt đầu transaction. Spring có thể được cấu hình để validate các thuộc tính transaction khi tham gia, nhưng validation không tự nâng mức isolation của transaction hiện tại.

## 10. Dùng TransactionalOperator cho transaction programmatic

`TransactionalOperator` phù hợp khi cần xác định transaction boundary bằng code, đặc biệt với reactive pipeline được tạo động.

Ví dụ:

~~~java
@Service
public class TransferService {

    private final TransactionalOperator transactionalOperator;
    private final AccountRepository accountRepository;

    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Mono<Void> work =
                accountRepository.debit(fromId, amount)
                        .then(accountRepository.credit(toId, amount));

        return transactionalOperator.transactional(work);
    }
}
~~~

Hai lệnh debit và credit nằm trong cùng transaction. Nếu publisher phát lỗi trước khi hoàn tất, transaction manager rollback theo contract reactive transaction.

### 10.1. Cấu hình propagation và isolation programmatic

Có thể tạo transaction definition:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);

definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ);

definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Sau đó:

~~~java
return operator.transactional(
        accountRepository.recalculateBalance(accountId));
~~~

Timeout là yêu cầu cho transaction manager/driver; cách áp dụng và độ chính xác phụ thuộc cấu hình. Nó không thay thế timeout của HTTP request, connection pool hoặc statement.

### 10.2. Dùng execute khi cần đánh dấu rollback-only

`execute` cung cấp `ReactiveTransaction` để thao tác với trạng thái transaction:

~~~java
Flux<TransferResult> result =
        transactionalOperator.execute(status -> {
            return transferRepository.performTransfer(command)
                    .onErrorResume(BusinessRuleException.class, error -> {
                        status.setRollbackOnly();
                        return Mono.just(TransferResult.rejected(error.getMessage()));
                    });
        });
~~~

Ở ví dụ này, lỗi nghiệp vụ được chuyển thành một kết quả có giá trị nhưng transaction được đánh dấu rollback-only. Nếu không gọi `setRollbackOnly`, việc nuốt lỗi bằng `onErrorResume` có thể khiến publisher hoàn tất bình thường và transaction được commit.

Chỉ dùng cách này khi contract nghiệp vụ muốn trả kết quả từ chối nhưng vẫn rollback dữ liệu. Nếu lỗi cần được truyền cho caller, để publisher phát lỗi thay vì chuyển nó thành giá trị.

## 11. @Transactional trong reactive code có những giới hạn gì?

Annotation chỉ có tác dụng khi lời gọi đi qua Spring transaction interceptor và reactive transaction manager phù hợp.

### 11.1. Phương thức phải được gọi qua proxy

Spring thường áp dụng `@Transactional` thông qua proxy. Gọi một phương thức transactional từ một phương thức khác trong cùng object (self-invocation) có thể bỏ qua proxy, khiến propagation hoặc isolation của phương thức được gọi không được áp dụng như mong đợi.

Ví dụ:

~~~java
@Service
public class OrderService {

    public Mono<Void> process() {
        return saveOrder(); // self-invocation có thể bỏ qua transaction proxy
    }

    @Transactional
    public Mono<Void> saveOrder() {
        return orderRepository.save(buildOrder()).then();
    }
}
~~~

Nên đặt ranh giới transaction ở phương thức được gọi qua bean proxy hoặc dùng `TransactionalOperator` để thể hiện boundary rõ ràng.

### 11.2. Phương thức phải trả reactive type để dùng reactive transaction

Với R2DBC, phương thức transactional nên trả `Mono`, `Flux` hoặc một reactive Publisher được Spring hỗ trợ. Nếu method trả kiểu đồng bộ như `void` hoặc `Order`, Spring có thể chọn transaction manager imperative hoặc không quản lý theo reactive semantics như mong muốn.

Không kết hợp `PlatformTransactionManager` của JDBC với repository R2DBC và kỳ vọng chúng cùng transaction. Chọn `ReactiveTransactionManager` tương ứng với R2DBC.

### 11.3. Transaction bắt đầu khi publisher được subscribe

Gọi method trả `Mono` chưa có nghĩa SQL đã chạy hoặc transaction đã bắt đầu. Transaction được thiết lập trong quá trình subscription của reactive chain.

Vì vậy:

- Không gọi `subscribe()` bên trong service.
- Không dùng `block()` để lấy kết quả ở giữa transaction.
- Không tạo một subscription độc lập rồi mong nó tham gia transaction hiện tại.
- Trả toàn bộ publisher chain về framework/caller.

## 12. Reactor Context và việc chia sẻ transaction giữa các thao tác

Transaction reactive được lưu trong Reactor Context, không dựa vào ThreadLocal như transaction imperative truyền thống.

Các repository và `DatabaseClient` tham gia cùng transaction khi:

- Cùng dùng `ConnectionFactory` tương ứng với transaction manager.
- Được thực thi trong cùng reactive subscription/context.
- Không tách công việc thành subscription độc lập.
- Không tự mở connection khác ngoài transaction context.

Ví dụ đúng:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                itemRepository.saveAll(itemsFor(saved.getId()))
                        .then())
        .then(inventoryRepository.decreaseStock(productId, quantity));
~~~

Các publisher được nối vào cùng một chain. Khi transaction manager quản lý chain này, các thao tác có thể dùng cùng connection transaction.

Ví dụ không nên:

~~~java
public Mono<Void> placeOrder(Order order) {
    orderRepository.save(order).subscribe(); // subscription riêng
    return inventoryRepository.decreaseStock(order.getProductId(), 1);
}
~~~

Lệnh lưu đơn hàng có thể chạy ngoài transaction context của publisher được trả về, không được caller chờ và lỗi có thể bị tách khỏi luồng chính.

### 12.1. Nhiều ConnectionFactory

Một transaction manager R2DBC thường quản lý resource cho một `ConnectionFactory`. Nếu repository A dùng connection factory A và repository B dùng connection factory B, một transaction manager không tự làm cho cả hai database tham gia cùng một transaction nguyên tử.

Nếu cần ghi nhiều database, cần kiến trúc riêng như saga, transactional outbox hoặc cơ chế phân tán được hệ thống hỗ trợ. Không giả định R2DBC local transaction tương đương XA/distributed transaction.

## 13. Giới hạn của driver và database

Spring cung cấp API nhất quán, nhưng khả năng thực thi cuối cùng phụ thuộc driver và hệ quản trị.

| Tính năng | Giới hạn cần kiểm tra |
|---|---|
| Isolation level | Driver/database có thể không hỗ trợ mọi mức; một số mức được ánh xạ sang mức khác |
| Savepoint / `NESTED` | Cần driver và database hỗ trợ savepoint |
| `REQUIRES_NEW` | Cần suspend transaction hiện tại và cấp transaction/connection độc lập; pool có thể trở thành nút thắt |
| Read-only transaction | Có thể chỉ là hint hoặc không được database cưỡng chế |
| Transaction timeout | Cách áp dụng phụ thuộc manager, driver và database; không phải mọi timeout đều tương đương statement timeout |
| DDL trong transaction | Một số database cho phép rollback DDL, số khác có lệnh DDL gây implicit commit hoặc giới hạn transaction |
| Row-level locking | Cú pháp và mức hỗ trợ như `SELECT ... FOR UPDATE` khác nhau |
| Generated values | Khả năng trả generated key phụ thuộc driver và dialect |
| Multiple result sets | Stored procedure và nhiều result segment không được hỗ trợ đồng nhất |
| Cancellation | Driver cần xử lý cancel và giải phóng tài nguyên đúng; mức độ phản hồi có thể khác |
| Concurrent use of one connection | Connection thường không dành cho nhiều luồng statement độc lập đồng thời |

Không suy ra rằng một tính năng hoạt động chỉ vì interface SPI có method tương ứng. Kiểm tra tài liệu driver và chạy integration test trên database mục tiêu.

## 14. Read-only, timeout và isolation mặc định

### 14.1. Read-only là hint hay ràng buộc?

Có thể khai báo:

~~~java
@Transactional(readOnly = true)
public Flux<OrderSummary> findSummaries() {
    return orderRepository.findAllSummaries();
}
~~~

`readOnly = true` mô tả ý định transaction. Tùy transaction manager, driver và database, nó có thể được dùng như hint tối ưu hoặc được chuyển thành thiết lập database. Không mặc định rằng mọi lệnh ghi đều bị chặn chỉ vì annotation có `readOnly = true`.

Nếu cần bảo vệ tuyệt đối khỏi ghi, dùng quyền database phù hợp, transaction read-only được database cưỡng chế nếu có, hoặc kiểm soát nghiệp vụ riêng.

### 14.2. Timeout

Có thể đặt timeout cho transaction:

~~~java
@Transactional(timeout = 5)
public Mono<Order> processOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Giá trị timeout thường được tính bằng giây trong transaction definition của Spring. Cách driver/database áp dụng timeout có thể khác nhau. Một transaction timeout không tự động bảo đảm mọi câu SQL bị hủy ngay tại database hoặc request HTTP được kết thúc đúng cùng thời điểm.

Cần phối hợp timeout ở các tầng:

- HTTP/request deadline.
- Connection pool acquisition.
- Transaction.
- Statement/database.
- Retry/backoff.

Không đặt timeout transaction dài chỉ để bù cho truy vấn chậm; hãy xem execution plan, index và tải database.

### 14.3. Isolation mặc định

Nếu không khai báo isolation, Spring thường dùng `ISOLATION_DEFAULT`, tức mức mặc định của database/connection. Mức này có thể được cấu hình ở database, datasource/connection factory hoặc session.

Để hiểu hành vi thực tế, kiểm tra cấu hình database và thử các tình huống concurrent trên đúng phiên bản hệ quản trị.

## 15. Khóa dữ liệu và optimistic locking

Isolation không phải cơ chế duy nhất để xử lý cập nhật đồng thời. Spring Data Relational hỗ trợ optimistic locking thông qua `@Version` trên entity.

Ví dụ:

~~~java
@Table("account")
public class Account {

    @Id
    private Long id;

    private BigDecimal balance;

    @Version
    private Long version;
}
~~~

Khi lưu, Spring Data dùng version để phát hiện entity đã bị thay đổi kể từ lúc đọc. Nếu version không còn khớp, thao tác có thể thất bại với optimistic locking failure.

Optimistic locking phù hợp khi xung đột không thường xuyên và ứng dụng muốn phát hiện thay đổi thay vì giữ lock trong thời gian dài.

Với database hỗ trợ row-level lock, có thể dùng truy vấn khóa như `SELECT ... FOR UPDATE` bên trong transaction. Nhưng cú pháp, hành vi và khả năng dùng lock phụ thuộc database/driver. Lock thường được giữ đến commit hoặc rollback; transaction càng dài thì nguy cơ contention càng cao.

Chọn cơ chế theo bất biến nghiệp vụ:

- `@Version` để phát hiện cập nhật cạnh tranh.
- Row lock để tuần tự hóa thao tác trên hàng cụ thể khi cần.
- Constraint database để bảo vệ bất biến như unique, foreign key và check.
- Isolation cao hơn khi cần kiểm soát các tương tác giữa nhiều hàng hoặc predicate.

Không dùng isolation level cao để thay thế mọi constraint dữ liệu.

## 16. Rollback, lỗi và cancellation

Trong reactive transaction, publisher hoàn tất bình thường thường dẫn đến commit; publisher phát lỗi thường dẫn đến rollback. Cancellation trước khi publisher hoàn tất cũng cần được xử lý như một đường kết thúc cần cleanup và rollback theo transaction manager.

Một lỗi thường gặp là nuốt lỗi trong transaction:

~~~java
return repository.save(entity)
        .onErrorResume(error -> Mono.empty());
~~~

Sau `onErrorResume`, publisher có thể hoàn tất bình thường. Transaction manager nhìn thấy completion thay vì lỗi và có thể commit các thay đổi trước đó nếu transaction chưa được đánh dấu rollback-only.

Nếu muốn rollback, có thể:

- Để lỗi tiếp tục truyền ra ngoài transaction.
- Đánh dấu transaction rollback-only bằng API phù hợp.
- Chuyển lỗi thành kết quả sau khi transaction đã rollback ở ranh giới thích hợp.

Spring mặc định rollback với unchecked exception (`RuntimeException`) và `Error` trong nhiều cấu hình transaction; checked exception cần quy tắc rollback được khai báo phù hợp như `rollbackFor`. Với reactive publisher, tín hiệu lỗi là phần quan trọng của quyết định rollback, nhưng quy tắc rollback của exception vẫn cần được cấu hình đúng.

Không gọi `subscribe()` để ghi log hoặc xử lý lỗi ở một luồng tách rời. Dùng `doOnError` cho side-effect quan sát không làm thay đổi tín hiệu; `onErrorResume` thì thay đổi luồng lỗi và cần được dùng có chủ đích.

## 17. Giới hạn khi kết hợp propagation và isolation

Một số cấu hình có vẻ hợp lý nhưng không tạo hiệu ứng như người viết mong đợi:

| Tình huống | Điều cần hiểu |
|---|---|
| Inner `REQUIRED` khai báo isolation cao hơn outer | Inner tham gia transaction hiện tại; isolation của transaction đã bắt đầu không tự nâng |
| Inner `REQUIRES_NEW` đọc dữ liệu outer chưa commit | Transaction mới thường không nhìn thấy thay đổi chưa commit của outer |
| Inner `NESTED` rollback | Chỉ rollback về savepoint; outer vẫn có thể tiếp tục nếu transaction còn hợp lệ |
| `SUPPORTS` được gọi ngoài transaction | Không có transaction để cung cấp snapshot chung |
| `NOT_SUPPORTED` bên trong transaction | Outer bị suspend; thao tác inner chạy ngoài transaction |
| `readOnly = true` | Có thể chỉ là hint, tùy database/driver |
| `SERIALIZABLE` | Có thể phát sinh serialization failure; ứng dụng cần retry có giới hạn |
| Hai repository dùng hai `ConnectionFactory` | Không tự động cùng một local transaction |
| Bắt lỗi bằng `onErrorResume` trong transaction | Có thể biến lỗi thành completion và dẫn tới commit nếu không đánh dấu rollback |
| Hủy subscription | Cần để transaction manager hoàn tất cleanup/rollback; không tự tạo subscription khác |

## 18. Kiểm thử propagation và isolation

Unit test với publisher giả có thể kiểm tra logic service, nhưng không chứng minh database thực thi isolation, savepoint hay locking đúng. Những hành vi này cần integration test với driver/database mục tiêu.

### 18.1. Kiểm thử rollback

Một kịch bản cơ bản:

1. Bắt đầu transaction.
2. Ghi một hàng.
3. Cố ý phát lỗi ở bước tiếp theo.
4. Xác nhận publisher kết thúc lỗi.
5. Đọc lại bằng một transaction khác và xác nhận hàng đã rollback.

Dùng `StepVerifier` để kiểm tra tín hiệu:

~~~java
StepVerifier.create(orderService.createOrderThenFail(command))
        .expectError()
        .verify();
~~~

Sau đó truy vấn database để xác nhận không còn dữ liệu đã ghi trong transaction bị rollback.

### 18.2. Kiểm thử REQUIRES_NEW

Tạo transaction ngoài, gọi service `REQUIRES_NEW` để ghi audit rồi làm transaction ngoài rollback. Sau đó xác nhận:

- Dữ liệu nghiệp vụ của transaction ngoài không tồn tại.
- Audit của transaction trong vẫn tồn tại.

Test phải thực sự gọi qua Spring proxy và dùng cùng cấu hình transaction manager dự kiến trong production.

### 18.3. Kiểm thử NESTED/savepoint

Nếu driver hỗ trợ savepoint:

1. Ghi dữ liệu trước nested scope.
2. Bắt đầu nested scope.
3. Ghi thêm dữ liệu.
4. Rollback nested scope.
5. Xác nhận dữ liệu trước savepoint vẫn tồn tại trong transaction.
6. Commit outer transaction.
7. Xác nhận chỉ dữ liệu trước savepoint được lưu.

Nếu database/driver không hỗ trợ savepoint, test cần thể hiện rõ tính năng không khả dụng thay vì giả định nested transaction hoạt động.

### 18.4. Kiểm thử isolation bằng hai connection

Để kiểm tra dirty read, non-repeatable read hoặc phantom read, cần hai transaction chạy đồng thời trên hai connection độc lập. Dùng barrier/latch hoặc điều phối reactive test để tạo đúng thứ tự:

~~~text
Transaction A                  Transaction B
-------------                  -------------
BEGIN
SELECT ...
                               BEGIN
                               UPDATE ...
                               COMMIT
SELECT lại ...
COMMIT
~~~

Kết quả cần được diễn giải theo database cụ thể và isolation level đang thử. Không dùng một test tuần tự đơn giản để kết luận về concurrency.

## 19. Quy trình chọn propagation và isolation

Khi thiết kế một use case, hãy trả lời:

1. Các thao tác có cần commit/rollback cùng nhau không?
2. Phương thức được gọi có nên tham gia transaction của caller không?
3. Có lý do nghiệp vụ thực sự để tạo transaction độc lập không?
4. Có cần savepoint để rollback một phần công việc không?
5. Có cần đọc lặp lại cùng một hàng hoặc cùng tập kết quả nhất quán không?
6. Có bất biến liên quan nhiều hàng cần khóa hoặc isolation cao hơn không?
7. Database/driver có hỗ trợ mức isolation, savepoint và lock được chọn không?
8. Các repository có cùng `ConnectionFactory` và transaction manager không?
9. Reactive chain có được nối liền mà không gọi `subscribe()` hoặc `block()` không?
10. Khi lỗi hoặc cancellation, transaction có rollback đúng không?
11. Nếu transaction bị serialization failure, ứng dụng có chiến lược retry an toàn không?
12. Timeout và kích thước pool có phù hợp với propagation lồng nhau không?

Bảng tham khảo:

| Nhu cầu | Lựa chọn thường cân nhắc |
|---|---|
| Một use case nhiều bước cùng commit/rollback | `REQUIRED` |
| Ghi audit độc lập với transaction chính | `REQUIRES_NEW`, nếu chấp nhận commit độc lập |
| Rollback một phần công việc trong transaction cha | `NESTED`, nếu savepoint được hỗ trợ |
| Có thể tham gia transaction của caller nhưng không tự mở | `SUPPORTS` |
| Bắt buộc caller phải có transaction | `MANDATORY` |
| Chạy ngoài transaction hiện tại | `NOT_SUPPORTED` |
| Cấm gọi trong transaction | `NEVER` |
| Ngăn dirty read | Ít nhất `READ_COMMITTED`, theo semantics DB |
| Cần đọc lại cùng hàng ổn định | `REPEATABLE_READ` hoặc cơ chế DB tương đương |
| Cần serializable behavior | `SERIALIZABLE`, kèm xử lý retry |
| Phát hiện cập nhật cạnh tranh một entity | `@Version` |
| Bảo vệ bất biến dữ liệu | Constraint database và transaction phù hợp |

## 20. Ghi nhớ

- Propagation quyết định cách một phương thức tham gia hoặc tạo transaction; isolation quyết định mức nhìn thấy thay đổi giữa các transaction.
- `REQUIRED` tham gia transaction hiện tại hoặc tạo mới nếu chưa có.
- `REQUIRES_NEW` suspend transaction ngoài và tạo transaction độc lập; nó có thể cần thêm connection.
- `NESTED` dùng savepoint trong transaction cha nếu driver/database hỗ trợ; nó không commit độc lập.
- `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED` và `NEVER` mô tả các yêu cầu khác nhau về sự hiện diện của transaction.
- `READ_COMMITTED` ngăn dirty read nhưng có thể cho non-repeatable read hoặc phantom theo semantics chuẩn.
- `REPEATABLE_READ` và `SERIALIZABLE` có hành vi cụ thể phụ thuộc database; `SERIALIZABLE` có thể yêu cầu retry.
- `@Transactional` reactive cần reactive transaction manager và method trả publisher; lời gọi phải đi qua proxy.
- `TransactionalOperator` giúp xác định transaction boundary trực tiếp trong reactive chain.
- Transaction context nằm trong Reactor Context; không tách subscription bằng `subscribe()` hoặc chặn bằng `block()`.
- Các thao tác chỉ tham gia cùng local transaction khi dùng đúng `ConnectionFactory` và transaction context.
- Savepoint, isolation, read-only, timeout, locking, DDL và cancellation phụ thuộc driver/database.
- `onErrorResume` có thể nuốt lỗi và làm transaction commit nếu không đánh dấu rollback-only.
- Dùng `@Version`, row lock và constraint cùng isolation phù hợp để xử lý xung đột dữ liệu.
- Kiểm thử transaction bằng integration test trên đúng database/driver, bao gồm rollback, propagation, savepoint và hai transaction chạy đồng thời.

