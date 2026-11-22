# Luồng lấy giao dịch, gọi phương thức và hoàn tất

## 1. Mục tiêu: nhìn xuyên qua `@Transactional`

Khi một Spring bean gọi phương thức mang `@Transactional`, điều gì diễn ra **trước khi thân phương thức chạy**, **trong lúc phương thức chạy** và **sau khi phương thức đã return hoặc ném exception**?

Câu trả lời nằm ở mô hình **AOP proxy → transaction interceptor → transaction manager → target method → commit/rollback**. `@Transactional` là metadata; bản thân annotation không phải câu lệnh `BEGIN` hoặc `COMMIT`. Spring đọc metadata để tạo một lời gọi có giao dịch bao quanh lời gọi nghiệp vụ.

Bài này tập trung vào **luồng lấy transaction, gọi phương thức và hoàn tất** trong chủ đề **Cơ chế proxy** của Spring transaction management. Sau bài học, bạn có thể:

1. Lần theo từ caller đến Spring AOP proxy, `TransactionInterceptor`, `TransactionAttribute` và `PlatformTransactionManager`.
2. Giải thích khi nào `getTransaction(...)` bắt đầu một physical transaction mới và khi nào chỉ tham gia transaction đã tồn tại.
3. Phân biệt **method body return** với **transaction commit thành công và caller nhận kết quả**.
4. Dự đoán commit, rollback, rollback-only và loại exception caller quan sát được.
5. Phân biệt dọn `TransactionInfo` của interceptor với việc giải phóng tài nguyên JDBC tại transaction manager.
6. Chạy một thí nghiệm Spring JDBC có ghi timeline, xác minh bằng trạng thái database **sau khi gọi qua proxy kết thúc**.
7. Nhận diện các trường hợp annotation không được intercept, khác biệt giữa imperative/reactive và giới hạn của luồng tiêu chuẩn.

Ví dụ cụ thể dùng **Java 17+, Spring Boot 3.3.x, Spring JDBC, H2, JUnit 5**. Các nguyên lý của Spring transaction abstraction áp dụng rộng hơn; chi tiết lấy connection, flush, timeout, callback hoặc khả năng propagation có thể khác giữa `DataSourceTransactionManager`, `JpaTransactionManager`, JTA và reactive manager.

## 2. Bức tranh tổng thể

```text
                    gọi bean thông qua reference được Spring cấp
Caller / Controller / một bean khác
                 |
                 v
      Spring AOP transactional proxy
                 |
                 v
          TransactionInterceptor
          | - tìm TransactionAttribute
          | - xác định transaction manager
          | - xin TransactionStatus
          |
          v
   PlatformTransactionManager
          | - getTransaction(definition)
          | - tạo mới / tham gia / suspend / từ chối
          v
          TransactionStatus
                 |
                 v
          Target service method
                 |
                 +--- JdbcTemplate / Repository ---> Database
                 |
                 +--- bình thường --------+
                 |                       |
                 +--- exception ---------+---> áp dụng rollback rule
                                         |
                             commit / rollback qua manager
                                         |
                              cleanup tài nguyên cần thiết
                                         |
                                         v
                            Caller nhận kết quả / exception
```

Đây là sơ đồ **đơn giản hóa luồng imperative tiêu chuẩn**. Một lời gọi qua proxy có thể đi qua nhiều advice/interceptor khác trước khi tới target. `TransactionInterceptor` chỉ là một advice trong chuỗi đó. Với transaction manager hỗ trợ callback hoặc với reactive publisher, cơ chế triển khai có nhánh khác; không được xem sơ đồ này là thứ tự chi tiết của mọi implementation.

### 2.1. Những thành phần cần gọi đúng tên

| Thành phần | Trách nhiệm | Điều dễ nhầm |
| --- | --- | --- |
| `@Transactional` | Mô tả propagation, isolation, read-only, timeout, rollback rules, manager qualifier… | Annotation **không tự** mở connection |
| Spring AOP proxy | Chặn lời gọi đi **qua proxy**, chạy advice quanh target | `this.method()` thường không qua proxy |
| `TransactionAttributeSource` | Tìm metadata transaction đã resolve cho method/class | Không phải transaction manager |
| `TransactionInterceptor` | Advice đi vào luồng transaction, gọi `invokeWithinTransaction` | Không phải database connection |
| `TransactionAspectSupport` | Nền tảng xử lý chọn manager, mở scope, gọi target, hoàn tất | Các helper nội bộ không phải API ứng dụng nên gọi trực tiếp |
| `PlatformTransactionManager` | `getTransaction`, `commit`, `rollback` cho giao dịch imperative | `getTransaction` **không luôn** tạo physical transaction mới |
| `TransactionDefinition` | Yêu cầu propagation, isolation, timeout, read-only và tên | Yêu cầu không có nghĩa DB hỗ trợ tất cả |
| `TransactionAttribute` | Mở rộng definition với rollback rules/qualifier/labels | Metadata của một transactional joinpoint |
| `TransactionStatus` | Trạng thái scope hiện tại: new transaction, rollback-only, completed… | Một status cho scope không đồng nghĩa một connection riêng |
| `TransactionSynchronizationManager` | Gắn các tài nguyên và synchronization của giao dịch imperative vào thread | ThreadLocal không lan tự động sang thread mới |

Các lớp liên quan thường thuộc `org.springframework.transaction.*`, interceptor nằm trong `org.springframework.transaction.interceptor.*`; đối với JDBC, `DataSourceTransactionManager` thuộc `org.springframework.jdbc.datasource`.

## 3. Điều kiện để lời gọi thật sự đi qua transaction proxy

Với proxy mode mặc định, các điều kiện chính là:

1. **Transaction infrastructure được kích hoạt.** Trong Spring thông thường dùng `@EnableTransactionManagement`; Spring Boot có thể tự kích hoạt nếu transaction auto-configuration và transaction manager phù hợp đã sẵn có.
2. **Bean do Spring quản lý.** Tạo object bằng `new MyService()` ở ngoài container rồi gọi method sẽ không có Spring AOP proxy.
3. **Caller sử dụng reference của proxy.** Lời gọi giữa các bean qua injection thường phù hợp. Một lời gọi `this.inner()` trong cùng object không được intercept như một lời gọi riêng qua proxy mặc định.
4. **Method có metadata được nhận diện** và có thể được proxy intercept. Ví dụ đáng tin cậy cho người mới học: public service method, không phải private/final.
5. **Có transaction manager được chọn đúng** cho data source/tài nguyên. `@Transactional(transactionManager = "ordersManager")` chọn theo qualifier; Spring không chọn transaction manager dựa vào tên phương thức.
6. **Đường đi là imperative hay reactive đúng cách.** Ví dụ bài này dùng method trả về `void` và `PlatformTransactionManager`.

Khi một yêu cầu không thỏa, có thể method vẫn chạy bình thường, thậm chí từng SQL statement được database autocommit, nhưng **không có boundary transaction như bạn kỳ vọng**. Đừng kết luận annotation hoạt động chỉ vì có dữ liệu được lưu.

### 3.1. Self-invocation và thời điểm khởi tạo

```java
@Service
public class PaymentService {
    public void submit() {
        this.saveTransactional(); // Bỏ qua transactional proxy ở lời gọi nội bộ.
    }

    @Transactional
    public void saveTransactional() {
        // ...
    }
}
```

Đây là mã **minh họa**, cần import `@Service` và `@Transactional` để biên dịch. Nếu chỉ có `saveTransactional` mang annotation, lời gọi `submit() → this.saveTransactional()` ở proxy mode mặc định không tự mở transaction mới cho lời gọi nội bộ. Tương tự, gọi transactional method từ `@PostConstruct` trước khi proxy đã sẵn sàng không phải cách kiểm thử tin cậy.

Cách dễ hiểu nhất là đặt transaction boundary trên một **public method được bean khác gọi qua proxy**. Nếu phải điều phối từng transaction theo code, cân nhắc `TransactionTemplate`. AspectJ weaving là cơ chế thay thế proxy mode khi cần xử lý self-invocation, nhưng có chi phí cấu hình và vận hành riêng.

## 4. Giai đoạn A — metadata và chọn transaction manager

Khi caller gọi một method phù hợp qua proxy:

1. Transaction advice xác định method thực tế và target class.
2. `TransactionAttributeSource` resolve thông tin từ `@Transactional` trên method/class hoặc từ cấu hình transaction khác.
3. `TransactionInterceptor` thông qua `TransactionAspectSupport.invokeWithinTransaction(...)` xử lý attribute này.
4. Framework xác định manager cần dùng dựa vào qualifier `transactionManager()/value()` hoặc lựa chọn mặc định của cấu hình.
5. Với đường imperative, manager phải tương thích với `PlatformTransactionManager`.

**Không có metadata transaction** không nhất thiết làm mọi proxy/advice biến mất: cùng proxy vẫn có thể chạy advice khác. Nhưng riêng transaction advice sẽ không yêu cầu một transaction mới cho lời gọi đó.

### 4.1. Transaction definition là yêu cầu, không phải sự kiện đã xảy ra

Ví dụ:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void updateInventory() {
    // ...
}
```

Metadata này yêu cầu semantics tương ứng. Khi manager tham gia transaction hiện có theo `REQUIRED`, thuộc tính isolation, timeout và read-only của inner scope có thể **không được áp dụng lại** vì physical transaction đã được mở từ outer scope. Với một số manager có thể bật `validateExistingTransaction` để phát hiện mismatch. Vì thế phải nhìn **physical transaction thực sự** và cấu hình manager, không đọc annotation rồi đoán.

### 4.2. Cơ chế phân giải annotation

Nếu class có `@Transactional` và method có `@Transactional` khác, Spring áp dụng quy tắc resolution method/class; không tự cộng tất cả thuộc tính vào một cấu hình "hợp nhất" theo ý người đọc. Khi debug cần xem `TransactionAttribute` mà infrastructure đã resolve cho method tương ứng.

Đối với JDK dynamic proxy, caller đi qua interface proxy; với class-based proxy, Spring dùng subclass proxy cho các method có thể intercept. Loại proxy không thay đổi mục đích của transaction interceptor, nhưng ảnh hưởng điểm chặn lời gọi và các giới hạn của self-invocation.

## 5. Giai đoạn B — `getTransaction`: tạo mới hay tham gia?

Đây là mấu chốt thường bị diễn giải sai. Gọi:

```java
TransactionStatus status =
        transactionManager.getTransaction(definition);
```

**Không đồng nghĩa** luôn gọi SQL `BEGIN` hoặc mở connection mới. Manager xem `propagation`, transaction hiện có và khả năng tài nguyên để quyết định bước tiếp.

| Propagation | Không có transaction hiện tại | Đang có transaction hiện tại |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tạo một physical transaction | Tham gia physical transaction đang có |
| `REQUIRES_NEW` | Tạo physical transaction mới | Tạm treo transaction ngoài; tạo physical transaction độc lập |
| `SUPPORTS` | Chạy không có actual transaction (có thể còn synchronization scope tùy manager) | Tham gia transaction hiện tại |
| `MANDATORY` | Ném `IllegalTransactionStateException` | Bắt buộc tham gia transaction hiện tại |
| `NOT_SUPPORTED` | Chạy không có actual transaction | Tạm treo transaction ngoài và chạy không transaction |
| `NEVER` | Chạy không có transaction | Ném `IllegalTransactionStateException` |
| `NESTED` | Thường tạo transaction mới theo khả năng manager | Thường dùng savepoint trong physical transaction hiện tại, nếu hỗ trợ |

Với JDBC local transaction, manager thường nhận một `Connection` phù hợp từ `DataSource`, đặt cấu hình transaction cần thiết (ví dụ auto-commit/isolation/read-only theo khả năng JDBC), sau đó quản lý connection đó trong scope. `JdbcTemplate` dùng `DataSourceUtils` để lấy connection đang được gắn với transaction. **Không** tự gọi `dataSource.getConnection()` rồi sử dụng một connection độc lập nếu bạn muốn cùng tham gia transaction của Spring.

### 5.1. Phân biệt logical và physical transaction

```text
Caller
  |
  v
Outer @Transactional(REQUIRED)  ─┐  logical scope A
  |                              │
  +--> Inner @Transactional     ├── cùng physical transaction P
       (REQUIRED)              ─┘  logical scope B
  |
  v
Outer kết thúc -> quyết định kết quả P
```

Hai lần `getTransaction` có thể trả về **hai status cho hai logical scope** nhưng cả hai cùng tham chiếu physical transaction P. `status.isNewTransaction()` thường **true** ở outer và **false** ở inner. Gọi `commit(innerStatus)` không đồng nghĩa database vừa commit toàn bộ P; physical commit chỉ diễn ra ở boundary sở hữu transaction mới khi điều kiện cho phép.

Nếu inner đánh dấu rollback-only do lỗi, outer dù bắt exception vẫn không thể commit P theo ý mình. Lúc outer thử commit, Spring có thể ném `UnexpectedRollbackException` để người gọi biết kết quả thực tế là rollback.

### 5.2. `TransactionStatus` không phải “biên nhận commit”

Một số phép quan sát hữu ích:

- `status.isNewTransaction()` cho biết scope này có tạo transaction mới hay đang tham gia.
- `status.hasSavepoint()` có thể phản ánh nested savepoint.
- `status.isRollbackOnly()` cho biết status đã đánh dấu rollback-only.
- `status.isCompleted()` phản ánh status đã hoàn tất khi manager kết thúc nó.

Những thuộc tính trên cần đọc **ở đúng giai đoạn**. `TransactionStatus` không phải chứng cứ database đã durable-commit; kiểm tra trạng thái dữ liệu **sau khi transaction kết thúc** mới giúp xác nhận kết quả ứng dụng cần.

## 6. Giai đoạn C — invoke target method

Khi manager xử lý xong `getTransaction`, transaction advice cho phép interceptor tiếp theo hoặc target method chạy. Với đường imperative tiêu chuẩn:

```text
proxy
  -> resolve metadata / manager
  -> getTransaction(...)
  -> bind TransactionInfo cho interceptor (theo ngữ cảnh thread)
  -> invocation.proceedWithInvocation()
       -> target method
            -> DAO/JdbcTemplate -> SQL ...
            -> return value  HOẶC  throw exception
  -> hoàn tất transaction dựa trên kết quả
```

Mã pseudo dưới đây **chỉ giải thích** cấu trúc thuật toán; không phải API ứng dụng được phép gọi trực tiếp:

```java
TransactionInfo info = createTransactionIfNecessary(...);

try {
    Object result = invocation.proceedWithInvocation();
    // Thành công ở mức method; transaction chưa chắc commit.
    return result;
} catch (Throwable failure) {
    // Xác định rollback rule và xử lý commit/rollback tương ứng.
    throw failure;
} finally {
    // Khôi phục transaction information của advice ở thread hiện tại.
}
```

Trong source Spring thực tế, kết quả có thể được xử lý thêm (ví dụ `Future` đã hoàn thành exceptional theo quy tắc rollback), sau đó mới gọi helper hoàn tất. Vì vậy không sao chép pseudo-code này vào production như một transaction manager. Mục tiêu là hiểu **vị trí target được gọi**.

Khi target truy cập DB qua Spring JDBC:

- `JdbcTemplate` thường lấy connection tham gia transaction đang hoạt động.
- Câu `INSERT/UPDATE` có thể đã **thực thi** trước khi method return, nhưng chưa đồng nghĩa transaction đã commit.
- Với JPA, thao tác `persist()` có thể chưa tạo ngay SQL; `flush` và kiểm tra ràng buộc có thể diễn ra muộn, kể cả lúc commit.
- Nếu method ném exception trước khi return, interceptor vẫn phải đưa transaction scope tới trạng thái hoàn tất, trừ trường hợp lỗi nghiêm trọng làm hạ tầng thất bại.

## 7. Giai đoạn D — method return và commit

Với target return bình thường, cơ chế imperative tiêu chuẩn gọi helper tương ứng với `commitTransactionAfterReturning(...)`. Helper chuyển yêu cầu tới:

```java
transactionManager.commit(status);
```

Đừng hiểu `commit(status)` là một lời gọi driver `Connection.commit()` trong **mọi trường hợp**:

1. Nếu status là scope tham gia `REQUIRED`, manager thường hoàn tất logical scope mà không commit physical transaction bên ngoài.
2. Nếu status thuộc transaction mới, manager xem rollback-only, thực hiện các synchronization callback phù hợp và gọi commit physical transaction khi được phép.
3. Nếu rollback-only được đặt trước đó, lời gọi `commit` có thể kết thúc bằng rollback, và trong một số trường hợp ném `UnexpectedRollbackException`.
4. Commit có thể thất bại do constraint/flush/connection hoặc database; caller nhận exception **sau khi thân method đã return bình thường**.
5. Callback trong transaction lifecycle có thể chạy trước/sau commit theo quy tắc manager; đừng tự giả định mọi callback thực hiện khi thread đã sạch transaction.

### 7.1. Ba mốc cần phân biệt

```text
Target service:    return value
                          |
Transaction advice:       v
                    commit(status)
                          |
Transaction manager:      v
                  commit / rollback / error
                          |
Caller:                   v
                thấy kết quả hoặc exception
```

**“Method body đã chạy hết”**, **“database commit thành công”** và **“caller đã nhận kết quả thành công”** là ba sự kiện khác nhau. Một lỗi phát sinh khi commit có thể khiến caller thấy exception dù thân method không ném lỗi.

Ví dụ: repository dùng JPA giữ entity trong persistence context, method return, nhưng SQL flush ở commit vi phạm unique constraint. Exception có thể xuất hiện **sau** method body, khi transaction advice đang kết thúc.

### 7.2. Exception ở commit có thể làm kết quả khó xác định

Khi kết nối mất đúng thời điểm gửi COMMIT, application có thể không biết database đã chấp nhận giao dịch chưa. **Không tự coi mọi exception từ commit là rollback thành công.** Với thao tác dễ nhân đôi (tạo thanh toán, phát hành hóa đơn), phải dùng business key/idempotency key và cơ chế đối soát trước khi retry.

`PlatformTransactionManager.commit(status)` có contract xử lý completion của status; sau khi đã gọi commit và gặp lỗi, không tùy tiện gọi `rollback(status)` lần nữa để “sửa lại” outcome.

## 8. Giai đoạn E — exception và rollback rule

Nếu target ném exception qua transaction advice, Spring áp dụng rollback rules. Mặc định trong cấu hình `@Transactional` thông thường:

- `RuntimeException` và `Error` → rollback.
- Checked `Exception` → **không mặc định rollback**, trừ khi đã cấu hình rollback rule hoặc transaction bị đánh dấu rollback-only bởi nguyên nhân khác.
- `rollbackFor` / `noRollbackFor` có thể thay đổi lựa chọn.
- Khi exception được catch *trước khi thoát qua interceptor*, interceptor có thể thấy method return bình thường; nhưng rollback-only đã thiết lập vẫn được tôn trọng.

| Tình huống trong một transaction JDBC mới | Việc interceptor thường yêu cầu | Quan sát kỳ vọng |
| --- | --- | --- |
| Method return bình thường | `commit(status)` | Dữ liệu được giữ nếu commit thành công |
| Method ném `IllegalStateException` | `rollback(status)` | Thay đổi chưa commit bị hủy |
| Method ném `IOException`, không có rollback rule | `commit(status)` rồi propagate `IOException` | Dữ liệu có thể được commit dù caller nhận checked exception |
| Method ném `IOException` với `rollbackFor=IOException.class` | `rollback(status)` rồi propagate exception | Dữ liệu bị hủy nếu rollback thành công |
| Method bắt runtime exception và return | Xem như return bình thường khi chưa có rollback-only | Thường commit |
| Inner `REQUIRED` ném runtime exception, outer catch và return | Inner đánh dấu rollback-only; outer thử commit | Physical rollback; có thể `UnexpectedRollbackException` ở caller |
| `getTransaction` thất bại trước target | Method body chưa được gọi | Không có transaction của scope đó để hoàn tất theo luồng thông thường |

Một ngoại lệ tinh tế: từ Spring Framework 6.1, một `Future`/`CompletableFuture` **đã hoàn thành exceptional ngay tại thời điểm method return** có thể khiến transaction được đánh dấu rollback-only nếu failure khớp rollback rules. `Vavr Try.Failure` cũng có xử lý được Spring tài liệu hóa. Đây là **quy tắc đặc biệt dựa trên return value**, không có nghĩa Spring transaction imperative sẽ giữ transaction mở chờ mọi tác vụ bất đồng bộ hoàn tất về sau.

### 8.1. Exception bên ngoài transaction method khác exception bên trong

```java
try {
    orderService.placeOrder();
} catch (IllegalStateException ex) {
    // Ở caller ngoài proxy: transaction advice đã xử lý completion
    // hoặc đã ném exception khi completion thất bại.
}
```

Đoạn trên là mã **minh họa**, biến `orderService` và method `placeOrder` cần tồn tại. Nếu `orderService` là proxy và transaction scope đã được mở, khối `catch` bên ngoài nhận lỗi **sau khi advice đã xử lý đường đi kết thúc tương ứng**. Nó không chắc chắn chứng minh database đã rollback thành công: cần xem exception và thực trạng DB.

Ngược lại, `catch` ngay **bên trong** transactional method có thể khiến interceptor không thấy một runtime exception đã bị nuốt. Với inner scope `REQUIRED` đã đánh dấu rollback-only trước khi outer bắt lỗi, kết quả có thể khác hoàn toàn.

## 9. Giai đoạn F — cleanup: hai loại cần phân biệt

Trong implementation tiêu chuẩn của `TransactionAspectSupport` có helper `cleanupTransactionInfo(...)` dùng để khôi phục **TransactionInfo ThreadLocal** của transaction advice. Đối với đường imperative, helper này được gọi trong `finally` quanh việc gọi target; nó không đồng nghĩa connection/database transaction đã commit hoặc được đóng hoàn toàn. **Tài nguyên** được hoàn tất/dọn bởi transaction manager trong xử lý commit/rollback.

Một cách mô tả hợp lý:

```text
TransactionInterceptor / TransactionAspectSupport
  - quản lý call stack và TransactionInfo của advice
  - phục hồi thông tin interceptor ở finally
  - yêu cầu manager commit/rollback cho status tương ứng

PlatformTransactionManager implementation
  - quản lý actual resource transaction
  - hoàn tất commit/rollback phù hợp
  - kích hoạt synchronization callbacks theo lifecycle
  - gỡ resource binding, khôi phục connection settings,
    giải phóng connection khi scope sở hữu hoàn tất
```

**Không đồng nhất ba thứ:** `TransactionInfo` (stack thông tin của advice), `TransactionSynchronizationManager` (binding của tài nguyên/synchronization trên thread), và `TransactionStatus` (trạng thái logical transaction scope). Chúng liên quan nhau nhưng có lifecycle và nhiệm vụ khác nhau.

### 9.1. Vì sao callback không luôn nhìn thấy “thread sạch”?

`TransactionSynchronization` có `beforeCommit`, `beforeCompletion`, `afterCommit` và `afterCompletion`. Thứ tự thực tế phụ thuộc manager và lifecycle; các resource có thể còn bound trong giai đoạn callback sau commit trước cleanup cuối. Nếu callback sau commit cần **ghi dữ liệu mới và commit độc lập**, phải xác định rõ transaction boundary, thường cân nhắc `REQUIRES_NEW` cho thao tác cần tách. Không dùng một câu `isActualTransactionActive()` để kết luận rằng có thể mở rộng transaction cũ sau khi commit.

Trong ví dụ bài này, ta chỉ ghi timeline ở wrapper manager trước và sau khi delegate hoàn tất. Đây là cách quan sát đơn giản cho học tập; production tracing nên dùng cơ chế instrumentation/callback được thiết kế rõ thay vì thay thế mọi transaction manager tùy tiện.

## 10. Một lượt gọi thành công và một lượt gọi thất bại

### 10.1. Thành công

```text
Caller -> Proxy -> TransactionInterceptor
                     |
                     +--> resolve @Transactional (REQUIRED)
                     +--> TM.getTransaction(...) -> status(new=true)
                     |
                     +--> Target.success()
                     |       INSERT row
                     |       return
                     |
                     +--> TM.commit(status)
                     |       JDBC COMMIT
                     |       cleanup resources
                     |
Caller <- Proxy -----+----- trả kết quả
```

Mốc quan sát quan trọng: **caller** chỉ nhận một return bình thường sau khi commit path của advice đã hoàn tất không lỗi. Nếu nơi gọi đang nằm trong outer transaction, "return bình thường" có thể chỉ hoàn tất **inner logical scope**, physical commit sẽ chờ outer.

### 10.2. Runtime exception

```text
Caller -> Proxy -> Interceptor
                     |
                     +--> TM.getTransaction(...) -> status(new=true)
                     +--> Target.failRuntime()
                     |       INSERT row
                     |       throw IllegalStateException
                     |
                     +--> rollback rule: true
                     +--> TM.rollback(status)
                     |       JDBC ROLLBACK
                     |       cleanup resources
                     |
Caller <- Proxy -----+----- ném IllegalStateException
```

Với transaction còn hiệu lực và rollback thành công, hàng vừa insert không tồn tại khi truy vấn lại sau boundary. Nếu chính rollback thất bại, exception của hạ tầng có thể thay thế/che lỗi gốc; kiểm tra cause và trạng thái dữ liệu thay vì khẳng định chắc chắn.

### 10.3. Checked exception chưa cấu hình rollback

```text
Caller -> Proxy -> Interceptor -> Target.failChecked()
                                   INSERT row
                                   throw IOException
                     |
                     +--> rollback rule mặc định: false
                     +--> TM.commit(status)
                     |
Caller <- Proxy -----+----- IOException được propagate
```

Exception vẫn được propagate sau completion. Đây là ví dụ dễ thấy vì sao **exception và rollback không đồng nghĩa**.

## 11. Thực hành hoàn chỉnh: ghi timeline của proxy → manager → method

Ta viết một Spring Boot application dùng JDBC/H2 và một `PlatformTransactionManager` wrapper để ghi nhận các mốc. Wrapper chỉ **quan sát** và chuyển tiếp các lời gọi tới `DataSourceTransactionManager` thật, không tự thực hiện JDBC commit/rollback. Sau đó các integration test kiểm tra cả **timeline** và **dữ liệu**.

### 11.1. Bố cục dự án

```text
tx-proxy-flow/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txflow/
    │   │   ├── TxFlowApplication.java
    │   │   ├── Timeline.java
    │   │   ├── RecordingTransactionManager.java
    │   │   ├── TransactionConfig.java
    │   │   ├── InnerStep.java
    │   │   └── FlowService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txflow/
        └── TransactionFlowIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-proxy-flow'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Mã ví dụ dùng Gradle quản lý dependencies Spring/JUnit/H2. Nếu dùng Spring Initializr để tạo dự án, nó cung cấp Gradle Wrapper; nếu tạo thủ công các file trên, cần thêm wrapper hoặc dùng Gradle cài sẵn tương thích. Đừng dùng `javac` trực tiếp khi chưa cấu hình classpath của Spring.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txflow;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

Chọn H2 và một bảng duy nhất để dễ xác minh hành vi commit/rollback. `code` có ràng buộc `UNIQUE`; mọi test đều dọn bảng trước nên không phụ thuộc dữ liệu của test trước.

### 11.2. Ứng dụng và bean ghi timeline

`src/main/java/com/example/txflow/TxFlowApplication.java`:

```java
package com.example.txflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxFlowApplication.class, args);
    }
}
```

`src/main/java/com/example/txflow/Timeline.java`:

```java
package com.example.txflow;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class Timeline {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    public void clear() {
        events.clear();
    }
}
```

`Timeline` là công cụ **phục vụ thí nghiệm**. Nó dùng danh sách trong bộ nhớ để test kiểm tra thứ tự. Không dùng singleton list tăng không giới hạn để làm logging production. Thí nghiệm giả định test chạy tuần tự, và mỗi test xóa timeline trước khi bắt đầu.

### 11.3. Manager wrapper: quan sát `getTransaction`, `commit`, `rollback`

`src/main/java/com/example/txflow/RecordingTransactionManager.java`:

```java
package com.example.txflow;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;

public final class RecordingTransactionManager
        implements PlatformTransactionManager {

    private final PlatformTransactionManager delegate;
    private final Timeline timeline;

    public RecordingTransactionManager(
            PlatformTransactionManager delegate,
            Timeline timeline) {
        this.delegate = delegate;
        this.timeline = timeline;
    }

    @Override
    public TransactionStatus getTransaction(TransactionDefinition definition)
            throws TransactionException {
        timeline.record("tm:get");
        TransactionStatus status = delegate.getTransaction(definition);
        timeline.record("tm:new=" + status.isNewTransaction());
        return status;
    }

    @Override
    public void commit(TransactionStatus status) throws TransactionException {
        timeline.record("tm:commit");
        delegate.commit(status);
        timeline.record("tm:commit:return");
    }

    @Override
    public void rollback(TransactionStatus status) throws TransactionException {
        timeline.record("tm:rollback");
        delegate.rollback(status);
        timeline.record("tm:rollback:return");
    }
}
```

Mỗi mốc có ý nghĩa chính xác:

- `tm:get`: interceptor **đã gọi vào** transaction manager wrapper.
- `tm:new=true/false`: delegate đã trả một status, tương ứng scope mới hoặc scope tham gia.
- `tm:commit`: có **lời gọi** `commit(status)`; không khẳng định physical JDBC commit khi status là participant.
- `tm:commit:return`: delegate trả về bình thường. Nếu đang là transaction owner với JDBC, commit path của delegate đã kết thúc không lỗi.
- `tm:rollback` và `tm:rollback:return`: tương tự với `rollback(status)`; khi inner `REQUIRED` đang tham gia, rollback của inner có thể chỉ **đánh dấu rollback-only** chứ chưa rollback physical transaction.

Nếu delegate ném exception, mốc `:return` tương ứng **không xuất hiện**. Sự vắng mặt của mốc trả về là gợi ý tìm bước lỗi, nhưng không đủ để kết luận database đã hay chưa commit.

### 11.4. Kết nối wrapper với manager JDBC thật

`src/main/java/com/example/txflow/TransactionConfig.java`:

```java
package com.example.txflow;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean("transactionManager")
    public RecordingTransactionManager transactionManager(
            DataSource dataSource,
            Timeline timeline) {
        return new RecordingTransactionManager(
                new DataSourceTransactionManager(dataSource),
                timeline);
    }
}
```

Import `DataSourceTransactionManager` từ **`org.springframework.jdbc.datasource`**. Class này là JDBC transaction manager cho một `DataSource`. Thực nghiệm chỉ tạo **một** Spring transaction manager bean mang tên `transactionManager`; Boot vẫn cấu hình datasource, JdbcTemplate và schema H2.

Trong code production, chỉ đặt wrapper như thế khi có lý do rõ và kiểm thử đầy đủ. Nếu cần metrics, instrumentation hoặc lifecycle callback, ưu tiên cơ chế tích hợp chuẩn phù hợp với hệ thống thay vì áp dụng wrapper đo đạc cho mọi transaction.

### 11.5. Một bean inner để kiểm tra `REQUIRED`

`src/main/java/com/example/txflow/InnerStep.java`:

```java
package com.example.txflow;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerStep {
    private final JdbcTemplate jdbc;
    private final Timeline timeline;

    public InnerStep(JdbcTemplate jdbc, Timeline timeline) {
        this.jdbc = jdbc;
        this.timeline = timeline;
    }

    @Transactional // REQUIRED theo mặc định
    public void writeThenFail() {
        timeline.record("inner:enter");
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "inner");
        timeline.record("inner:throw");
        throw new IllegalStateException("Simulated inner failure");
    }
}
```

`InnerStep` là một bean riêng để caller qua proxy của nó. `InnerStep.writeThenFail()` ném runtime exception sau khi insert; interceptor cho inner logical scope sẽ áp dụng rollback rule. Do inner được gọi từ outer transaction `REQUIRED`, manager thường **đánh dấu physical transaction dùng chung là rollback-only**, không hoàn tất physical transaction độc lập ngay tại đây.

### 11.6. Service chính chứa năm tình huống

`src/main/java/com/example/txflow/FlowService.java`:

```java
package com.example.txflow;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class FlowService {
    private final JdbcTemplate jdbc;
    private final Timeline timeline;
    private final InnerStep inner;

    public FlowService(
            JdbcTemplate jdbc,
            Timeline timeline,
            InnerStep inner) {
        this.jdbc = jdbc;
        this.timeline = timeline;
        this.inner = inner;
    }

    @Transactional
    public void success() {
        write("ok");
    }

    @Transactional
    public void failRuntime() {
        write("runtime");
        throw new IllegalStateException("Simulated runtime failure");
    }

    @Transactional
    public void failChecked() throws IOException {
        write("checked");
        throw new IOException("Simulated checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void failCheckedRollback() throws IOException {
        write("checked-rollback");
        throw new IOException("Simulated checked failure");
    }

    @Transactional
    public void outerCatchesInner() {
        write("outer");

        try {
            inner.writeThenFail();
        } catch (IllegalStateException expected) {
            timeline.record("outer:caught");
        }

        // Method body return bình thường; outer advice vẫn phải hoàn tất.
    }

    private void write(String code) {
        timeline.record("body:write=" + code);
        timeline.record("body:active=" +
                TransactionSynchronizationManager.isActualTransactionActive());
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
        timeline.record("body:inserted=" + code);
    }
}
```

Trong cả bốn method `@Transactional` đầu tiên, `write` là helper private chạy trong transaction do method public đã mở; helper **không cần** mang annotation riêng. `TransactionSynchronizationManager.isActualTransactionActive()` chứng minh Spring đang đánh dấu transaction hoạt động trong thread **ở thời điểm ghi log**, nhưng một dòng `true` một mình chưa chứng minh commit tương lai.

Với `outerCatchesInner`, caller gọi bean `inner` qua proxy. Inner thất bại và đánh dấu rollback-only; outer catch rồi return bình thường ở mức Java. Khi outer advice định commit shared physical transaction, manager không được phép commit nó.

### 11.7. Integration test kiểm chứng cả timeline lẫn dữ liệu

`src/test/java/com/example/txflow/TransactionFlowIntegrationTest.java`:

```java
package com.example.txflow;

import java.io.IOException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class TransactionFlowIntegrationTest {
    @Autowired
    private FlowService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Timeline timeline;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
        timeline.clear();
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalReturnCommitsBeforeCallerGetsResult() {
        service.success();

        assertEquals(1L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=ok",
                "body:active=true",
                "body:inserted=ok",
                "tm:commit",
                "tm:commit:return"
        ), timeline.snapshot());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void runtimeFailureRollsBackBeforeExceptionReachesCaller() {
        assertThrows(IllegalStateException.class,
                service::failRuntime);

        assertEquals(0L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=runtime",
                "body:active=true",
                "body:inserted=runtime",
                "tm:rollback",
                "tm:rollback:return"
        ), timeline.snapshot());
    }

    @Test
    void checkedExceptionCanCommitThenReachCaller() {
        assertThrows(IOException.class,
                service::failChecked);

        assertEquals(1L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=checked",
                "body:active=true",
                "body:inserted=checked",
                "tm:commit",
                "tm:commit:return"
        ), timeline.snapshot());
    }

    @Test
    void rollbackForChangesCompletionDecision() {
        assertThrows(IOException.class,
                service::failCheckedRollback);

        assertEquals(0L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=checked-rollback",
                "body:active=true",
                "body:inserted=checked-rollback",
                "tm:rollback",
                "tm:rollback:return"
        ), timeline.snapshot());
    }

    @Test
    void innerRequiredParticipatesAndMarksRollbackOnly() {
        assertThrows(UnexpectedRollbackException.class,
                service::outerCatchesInner);

        assertEquals(0L, rows());
        List<String> events = timeline.snapshot();

        // Outer tạo physical transaction; inner chỉ tham gia.
        assertEquals(2L, events.stream()
                .filter("tm:get"::equals).count());
        assertTrue(events.contains("tm:new=true"));
        assertTrue(events.contains("tm:new=false"));

        // Inner báo rollback; outer vẫn thử commit.
        assertTrue(events.contains("tm:rollback"));
        assertTrue(events.contains("tm:rollback:return"));
        assertTrue(events.contains("outer:caught"));
        assertEquals("tm:commit", events.get(events.size() - 1));
    }
}
```

### 11.8. Chạy như thế nào?

Đặt các file đúng đường dẫn, dùng JDK 17 trở lên, Gradle tương thích Spring Boot 3.3.5, và từ thư mục có `build.gradle` chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có wrapper, tạo Gradle Wrapper bằng Gradle đã cài hoặc chạy `gradle test` với phiên bản tương thích. Spring/JDBC/H2/JUnit được Gradle đưa vào classpath, không cần lệnh `javac` riêng. **Kết quả kỳ vọng: 5 test pass**. Tests không in stdout cố định; báo cáo nằm ở `build/reports/tests/test/index.html`.

| Kịch bản | Lời gọi manager quan sát | Dữ liệu sau khi caller trở lại |
| --- | --- | --- |
| `success` | `getTransaction → commit` | 1 hàng |
| `failRuntime` | `getTransaction → rollback` | 0 hàng |
| `failChecked` | `getTransaction → commit`, sau đó checked exception đến caller | 1 hàng |
| `failCheckedRollback` | `getTransaction → rollback` | 0 hàng |
| `outerCatchesInner` | Outer get, inner get (join), inner rollback request, outer commit request phát sinh rollback-only exception | 0 hàng |

**Lưu ý về tính đúng đắn của test:**

- Class test **không** gắn `@Transactional`. Nếu test tự sở hữu transaction, `REQUIRED` service có thể chỉ tham gia test transaction và toàn bộ test sẽ rollback sau đó; bạn không còn chứng minh được commit boundary của service.
- `@BeforeEach` dọn bảng trước khi reset timeline. Vì vậy việc test chuẩn bị dữ liệu không lẫn vào mốc được theo dõi.
- Timeline của wrapper cho thấy **lời gọi manager và status**, không tự xác minh JDBC physical commit cho scope tham gia. Kết luận dữ liệu dựa trên truy vấn `rows()` **sau khi lời gọi service kết thúc**.
- Các test dùng một application context và nguồn H2 trong bộ nhớ. Nếu bật chạy test song song, cần cô lập dữ liệu và bộ ghi timeline cho từng test; cấu hình mặc định JUnit 5 thường chạy tuần tự.
- Không có lời khẳng định ở đây rằng test đã được chạy trên máy của người đọc. Bảng trên là **kết quả được kỳ vọng từ mã nguồn**; nếu khác, hãy xem manager được cấu hình thực tế, log và báo cáo test.

## 12. Nếu luồng bị thay đổi thì sao?

### 12.1. Lỗi trước target

Nếu `getTransaction` không lấy được connection, manager không thể khởi tạo transaction, hoặc cấu hình propagation yêu cầu transaction hiện có mà không có, lỗi có thể ném **trước khi target method chạy**. Khi đó không có sự kiện `body:write=...` trong thí nghiệm; đừng chạy logic nghiệp vụ thủ công từ `catch` để “bù” cho một transaction chưa được mở.

### 12.2. Lỗi lúc commit và rollback

Lỗi ở `commit`/`rollback` là lỗi **sau giai đoạn invoke**. Nó có thể che exception từ method trước đó. Cần phân biệt:

- Exception trực tiếp từ target.
- Exception do rollback rule quyết định và manager xử lý.
- Exception mới của transaction manager khi completion thất bại.
- Có hay không dữ liệu thật sự commit; khi commit outcome không chắc, **cần đối soát bằng business key**.

Không suy ra tất cả lỗi transaction là `TransactionException`. Ví dụ `JdbcTransactionManager` có thể dịch lỗi commit/rollback sang họ `DataAccessException`; `DataSourceTransactionManager` và các manager khác có cách xử lý khác. Đọc implementation và cause chain của manager được dùng.

### 12.3. Nhiều data source hoặc nhiều manager

Transaction advice phải chọn manager phù hợp với tài nguyên mà repository/JDBC đang dùng. Một method `@Transactional` chỉ quản lý đúng tài nguyên tham gia manager ấy; nó không tự biến email, HTTP call, Kafka publish hay một database độc lập thành một physical transaction chung. Với giao dịch nhiều tài nguyên, cần mô hình phù hợp như JTA/XA (khi thật sự cần và hỗ trợ), transactional outbox hoặc cơ chế bù.

### 12.4. Thứ tự các advice khác

Có thể tồn tại cả `@Retryable`, `@Async`, caching, metrics hoặc aspect tùy chỉnh. **Thứ tự advice** ảnh hưởng điều gì nằm **bên trong** và **bên ngoài** transaction boundary. Một retry advice chạy ngoài transaction advice có thể mở transaction khác cho mỗi lần thử; chiều ngược lại có thể retry trong một transaction đã bị đánh dấu rollback-only, rất khác về semantics. Không đoán thứ tự dựa vào thứ tự viết annotation: cần xem cấu hình order và runtime call chain.

### 12.5. Reactive transaction

Với `ReactiveTransactionManager`, transaction gắn với **Reactor context** và lifecycle của publisher, không phải chỉ một lời gọi method imperative qua thread-local. Việc subscribe, thành công, error hoặc cancel của reactive pipeline mới là các mốc quan trọng của transaction. Vì vậy sơ đồ và integration test JDBC của bài này **không được sao chép nguyên trạng** cho `Mono`/`Flux`.

## 13. Quan sát và chẩn đoán một transaction thật

Khi cần kiểm chứng luồng proxy/manager ngoài thí nghiệm, xác định **đúng giai đoạn** trước khi suy đoán:

| Triệu chứng | Giả thuyết | Cách kiểm tra |
| --- | --- | --- |
| Không thấy transaction begin | Call không qua proxy; annotation không resolve; không có manager phù hợp | Kiểm tra bean được inject, target method, proxy mode, transaction infrastructure |
| SQL chạy nhưng rollback không hủy dữ liệu | Ghi trên connection ngoài Spring transaction; autocommit; resource không cùng manager | Kiểm tra `DataSource`, `JdbcTemplate`/`DataSourceUtils`, manager và connection |
| Method return nhưng caller nhận exception | Commit/flush hoặc callback completion thất bại | Xem stack trace ở transaction boundary; đối soát DB |
| Inner `REQUIRED` catch được lỗi nhưng outer không commit | Shared transaction bị đánh dấu rollback-only | Kiểm tra inner advice và `UnexpectedRollbackException` |
| Hai lần `getTransaction` nhưng một physical commit | Logical scopes `REQUIRED` cùng transaction | Quan sát `isNewTransaction()`, connection và propagation |
| Test thấy dữ liệu nhưng DB khác không thấy | Test transaction chưa commit hoặc cache/persistence context | Đo sau boundary qua transaction/connection độc lập |
| Timeout ở thao tác dài | Isolation/lock/query/statement timeout hoặc hạ tầng phát hiện deadline | Đo DB, pool, thread, thời điểm timeout cụ thể |

Có thể bật log có chọn lọc trong môi trường phát triển:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Đừng viết test dựa trên câu chữ log cố định: logger, thứ tự và nội dung log có thể thay đổi theo phiên bản/manager. Khi dùng JPA, thêm thông tin flush/SQL theo nhu cầu. Không ghi secrets, credentials hay dữ liệu cá nhân vào trace.

### 13.1. Một quy trình debug theo mốc thời gian

1. **Nhận diện caller và bean được gọi:** lời gọi đi qua proxy Spring chưa?
2. **Xác định transactional metadata:** method/class nào cung cấp `@Transactional`, và manager nào được chọn?
3. **Theo dõi `getTransaction`:** có transaction đã tồn tại không? status có `isNewTransaction()` không?
4. **Theo dõi vào target:** SQL dùng đúng `DataSource` và resource bound chưa?
5. **Xác nhận return/exception từ target:** xảy ra ở dòng nào, exception bị bắt ở đâu?
6. **Xác định quyết định completion:** rollback rule, rollback-only, propagation và callback nào liên quan?
7. **Đo hoàn tất ở manager:** `commit(status)` hay `rollback(status)` đã được gọi và có trả bình thường?
8. **Đọc lại dữ liệu sau transaction boundary:** dùng connection/ngữ cảnh độc lập và business key để phân biệt commit, rollback hoặc outcome chưa xác định.

Bốn dữ kiện “annotation có mặt”, “SQL chạy”, “target return” và “log có commit” đều **chưa đủ riêng lẻ** để chứng minh nghiệp vụ đã được lưu đúng. Dữ liệu quan sát sau transaction và những ràng buộc nghiệp vụ mới quyết định.

## 14. Bài tập suy luận

**Bài 1.** Một controller gọi bean service qua proxy. Method có `@Transactional`, thực hiện `INSERT` rồi return. Sau return của target, điều gì còn phải xảy ra để caller nhận kết quả bình thường?

*Đáp án:* Transaction advice vẫn phải thực hiện completion cho scope của nó, thường gọi `commit(status)`. Nếu scope tạo physical transaction mới, manager cần commit/cleanup thành công. Nếu method chỉ tham gia một outer transaction, physical commit chờ outer boundary.

**Bài 2.** Một method `@Transactional(REQUIRED)` gọi bean khác có `@Transactional(REQUIRED)`. Wrapper ghi hai lần `getTransaction`. Có chắc hai lần `Connection.commit()` không?

*Đáp án:* Không. Có thể có hai logical scopes cùng một physical transaction. Inner status tham gia có `isNewTransaction() = false`; physical commit do owner ở outer hoàn tất.

**Bài 3.** Method ném checked `IOException`, không có `rollbackFor`, và chưa có rollback-only. Theo mặc định Spring đi đường nào?

*Đáp án:* `completeTransactionAfterThrowing(...)` có thể chọn `commit(status)` vì exception không khớp rollback rule mặc định, sau đó vẫn propagate `IOException` tới caller.

**Bài 4.** Tại sao `cleanupTransactionInfo(...)` không đồng nghĩa `Connection.close()`?

*Đáp án:* Helper này phục hồi thông tin của transaction advice trên thread. Việc hoàn tất physical transaction, gỡ resource binding, trả connection về pool và khôi phục trạng thái connection thuộc transaction manager.

**Bài 5.** Target return bình thường nhưng commit gặp mất kết nối. Có thể nói mọi dữ liệu đã rollback không?

*Đáp án:* Không. Commit outcome có thể không xác định. Cần kiểm tra bằng business key/idempotency và đối soát; không retry mù.

**Bài 6.** Một method gắn `@Transactional` được gọi bằng `this.method()` từ cùng object và không có transaction outer. Đường gọi có chắc đi vào `TransactionInterceptor` không?

*Đáp án:* Không trong proxy mode mặc định. Lời gọi nội bộ bỏ qua proxy; để có boundary riêng, gọi qua Spring bean khác hoặc dùng cơ chế transaction thích hợp.

### Tiêu chí tự đánh giá

Bạn nắm được bài khi có thể giải thích theo thứ tự **proxy → resolve metadata → getTransaction → invoke target → chọn completion → commit/rollback → resource cleanup → caller**, dự đoán đúng trạng thái dữ liệu ở các nhánh return/runtime exception/checked exception/inner `REQUIRED` và chứng minh dự đoán bằng test đọc dữ liệu sau transaction.

## Tài liệu tham khảo chính thức

- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — `TransactionAspectSupport` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
