# Thuộc tính nào được áp dụng khi tạo giao dịch mới trong Spring?

Trong Spring Framework, `@Transactional` mô tả một **yêu cầu giao dịch**; `PlatformTransactionManager` mới là thành phần quyết định có bắt đầu một **giao dịch vật lý mới** hay tham gia giao dịch đang có. Khi giao dịch mới được mở, manager có cơ hội áp dụng **isolation**, **timeout**, **readOnly** cùng những thông tin quản lý như **tên giao dịch**, tùy khả năng của datasource, driver, database và transaction manager. **Propagation** quyết định có cần tạo mới, join hay suspend; **rollback rules** quyết định kết cục khi lời gọi kết thúc bằng exception, kể cả trong scope chỉ tham gia giao dịch có sẵn.

Điểm quan trọng nhất của bài thuộc nhóm **Phạm vi giao dịch**:

> Với `PROPAGATION_REQUIRED`, nếu đã có transaction ngoài, scope trong thường dùng nguyên các đặc tính của **physical transaction ngoài**. Những yêu cầu isolation, timeout và read-only khác ở inner scope **không tự cấu hình lại** physical transaction đó. Với `REQUIRES_NEW`, Spring tạm gác transaction ngoài và bắt đầu transaction độc lập, nên các đặc tính của inner có cơ hội áp dụng lên transaction mới.

Vì vậy, cần trả lời câu hỏi **theo từng thuộc tính**; không nên kết luận sai rằng mọi field của `@Transactional` đều bị bỏ qua khi join, hoặc rằng mỗi annotation đồng nghĩa một transaction mới.

## 1. Mô hình: yêu cầu, scope logic, transaction vật lý và kết cục

Có bốn khái niệm:

1. **`TransactionDefinition`**: hợp đồng yêu cầu trước khi một scope bắt đầu, bao gồm propagation, isolation, timeout, read-only, name.
2. **`TransactionAttribute`**: mở rộng definition cho giao dịch khai báo; bổ sung cách xử lý exception và metadata cần thiết cho advice.
3. **`TransactionStatus`**: thông tin manager trả về cho một lượt `getTransaction(...)`; cho biết scope có transaction mới, rollback-only, completed hay chưa.
4. **Physical transaction**: transaction thực sự ở JDBC connection, JPA resource hoặc hạ tầng tương ứng.

Ví dụ hai bean Spring:

```text
HTTP request / message
       |
       v
OrderService.createOrder()        logical scope A: REQUIRED
       |                          start physical T1
       |
       +--> StockService.reserve() logical scope B: REQUIRED
       |                           join physical T1
       |
       +--> InvoiceService.save()  logical scope C: REQUIRED
                                   join physical T1

T1: begin ----------------------------------- commit hoặc rollback
```

Có ba **logical scopes** nhưng chỉ một **physical transaction** T1. Nếu B và C khai báo `timeout` hay `isolation` riêng, chúng không trở thành hai transaction vật lý mới để tự chọn những đặc tính đó.

Cùng luồng nhưng `StockService.reserve()` dùng `REQUIRES_NEW`:

```text
T1 outer:        begin -------- suspend ------ resume -------- commit
T2 stock:                        begin -- commit/rollback
```

T2 có transaction manager status và khả năng cấu hình riêng, nhưng có thể cần JDBC connection thứ hai. T2 đã commit không bị outer T1 rollback một cách tự động; thiết kế tính nhất quán nghiệp vụ phải tính đến sự độc lập đó.

## 2. Bảng trả lời ngắn theo nhóm thuộc tính

| Cấu hình / thuộc tính | Khi physical transaction mới được tạo | Khi method tham gia transaction có sẵn |
| --- | --- | --- |
| `propagation` | Được dùng để quyết định **có tạo mới** | Vẫn được xét để chọn join, suspend, nested, cấm hoặc yêu cầu transaction |
| `isolation` | Manager cố thiết lập mức cô lập được yêu cầu | Thường theo isolation của outer; không tự đổi T1 |
| `timeout`, `timeoutString` | Có thể đặt timeout/deadline mới nếu backend hỗ trợ | Không reset timeout/deadline của outer |
| `readOnly` | Manager/provider có thể truyền hint hoặc tối ưu read-only | Theo đặc tính outer transaction; không chuyển T1 qua lại giữa read-only/read-write |
| Transaction name | Tên metadata được gắn khi khởi tạo scope/transaction phù hợp | Scope tham gia thường không đổi tên physical transaction ngoài |
| `label` | Manager có thể xử lý label theo cách riêng | Không bảo đảm mọi manager dùng label để thay thuộc tính vật lý |
| `transactionManager` / `value` | Chọn manager và resource xử lý begin | Vẫn quyết định **manager nào** được dùng để tìm transaction tham gia |
| `rollbackFor`, `noRollbackFor` | Áp dụng khi interceptor quyết định rollback/commit | **Vẫn áp dụng** khi exception thoát khỏi inner logical scope, có thể làm T1 rollback-only |

Trong tài liệu `@Transactional`, Spring mô tả isolation, timeout và read-only là những thiết lập chủ yếu dành cho `REQUIRED` và `REQUIRES_NEW` vì chúng chỉ có tác dụng vật lý khi bắt đầu transaction. Riêng `readOnly` cũng có thể được dùng như metadata/hint cho một số resource context **không có physical transaction** (chẳng hạn `SUPPORTS` trong vài tình huống), nên cần phân biệt hint với thay đổi ở database.

**Tóm lại:** ba thuộc tính thường bị hiểu nhầm nhất là `isolation`, `timeout`, `readOnly`. Hai thuộc tính không nên liệt vào danh sách “chỉ áp dụng khi new” là `propagation` và các **rollback rules**.

## 3. Propagation là quyết định đầu tiên

Mặc định `@Transactional` dùng `Propagation.REQUIRED`. Trước khi hỏi “isolation nào được áp dụng?”, hãy xác định propagation của scope làm gì.

| Propagation | Không có transaction sẵn | Đã có transaction |
| --- | --- | --- |
| `REQUIRED` | Bắt đầu T1 mới | Join T1 |
| `REQUIRES_NEW` | Bắt đầu T1 mới | Suspend T1, bắt đầu T2 riêng |
| `SUPPORTS` | Chạy không có physical transaction | Join T1 |
| `MANDATORY` | Ném lỗi thiếu transaction | Join T1 |
| `NOT_SUPPORTED` | Chạy phi transactional | Suspend T1, chạy phi transactional |
| `NEVER` | Chạy phi transactional | Ném lỗi vì đang có T1 |
| `NESTED` | Có thể bắt đầu transaction khi chưa có, theo manager | Thường dùng savepoint trong T1 khi được hỗ trợ |

`NESTED` **không đồng nghĩa** với `REQUIRES_NEW`: khi đã có T1, nested scope thường vẫn chia sẻ một physical transaction và rollback về savepoint. Savepoint không tạo một JDBC isolation level mới cho phần nội bộ. Một số manager/resource không hỗ trợ nested transaction hoặc savepoint sẽ báo lỗi.

`NOT_SUPPORTED` có thể kích hoạt synchronization logic dù không có physical transaction. Không nên hiểu `isSynchronizationActive()` là bằng chứng SQL trong scope này được rollback chung.

`REQUIRES_NEW` có thể giữ connection của outer trong khi mượn connection khác cho inner, nên connection pool phải có dư địa phù hợp. Nếu transaction độc lập được tạo chỉ để thay isolation, cần cân nhắc chi phí pool, deadlock, nhất quán dữ liệu và số transaction thật.

## 4. Isolation: thuộc tính ở lần bắt đầu physical transaction

Isolation quyết định mức độ một transaction quan sát thay đổi của transaction khác. Trong `@Transactional`, giá trị mặc định là `Isolation.DEFAULT`, có nghĩa **dùng mặc định của backend**, không phải mặc định `READ_COMMITTED` cho mọi database.

| Mức | Ý nghĩa khái quát |
| --- | --- |
| `READ_UNCOMMITTED` | Có thể cho phép dirty read nếu backend thực sự hỗ trợ |
| `READ_COMMITTED` | Không đọc dữ liệu chưa commit; lần đọc sau có thể thấy giá trị đã commit mới |
| `REPEATABLE_READ` | Hạn chế việc cùng dữ liệu đã đọc đổi giá trị trong một transaction, tùy MVCC/locking |
| `SERIALIZABLE` | Mục tiêu hiệu ứng tương đương lịch chạy tuần tự, thường có chi phí/serialization conflict |

Chi tiết phantom, snapshot, khóa và việc nâng hoặc hạ mức cô lập phụ thuộc database; không lấy bảng khái quát này thay tài liệu PostgreSQL, MySQL/InnoDB, SQL Server hay H2.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void calculateClosingBalance() {
    // Logic nghiệp vụ cần tính nhất quán
}
```

Đây là **fragment minh họa**, không biên dịch độc lập. Nếu chưa có transaction, `REQUIRED` bắt đầu T1 và transaction manager JDBC có thể cấu hình connection isolation trước khi thực hiện SQL. Nếu đã có T1 ở `READ_COMMITTED`, lời gọi chỉ tham gia T1: inner `SERIALIZABLE` **không nâng isolation của T1** theo mặc định.

### 4.1. Tại sao không đổi isolation giữa chừng?

Vì inner `REQUIRED` vẫn dùng cùng physical transaction. Mức cô lập thuộc đặc tính mà manager/backend áp dụng cho transaction đó; việc một logical scope mới xuất hiện không tự chia T1 thành hai transaction độc lập. Thậm chí trên một số DB, thay isolation giữa transaction có hạn chế hoặc lỗi.

Nếu use case thật sự cần `SERIALIZABLE`, cân nhắc đặt annotation ở **boundary mở T1**. Nếu một đoạn việc phải độc lập và tách được về mặt nghiệp vụ, có thể dùng `REQUIRES_NEW` để mở T2 với isolation riêng; không dùng `REQUIRES_NEW` máy móc chỉ để tránh thiết kế lại boundary.

### 4.2. Isolation do DB quyết định đến đâu?

JDBC manager có thể gọi `Connection.setTransactionIsolation(...)`, nhưng mức độ hỗ trợ và semantics thực tế do driver/backend cung cấp. `SERIALIZABLE` không có nghĩa ứng dụng không bao giờ phải retry; một số DB trả serialization failure. Với các yêu cầu concurrent correctness, nên có integration test hai transaction thật.

## 5. Timeout: chỉ có deadline mới khi có transaction mới

`@Transactional(timeout = 20)` yêu cầu timeout theo **giây** cho transaction phù hợp. Nếu manager đang mở T1 mới, nó cố ghi nhận deadline theo hạ tầng của mình. Nếu inner `REQUIRED(timeout=2)` join T1 vốn đã bắt đầu 50 giây trước với timeout 60 giây, inner không tạo một “transaction 2 giây” mới và **không reset** thời hạn của T1.

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeout = 8
)
public void reserveExternalNumber() {
    // Lời gọi được Spring advice chặn, T2 mới nếu hợp lệ
}
```

Đây là fragment minh họa; `REQUIRES_NEW` có thể bắt đầu transaction độc lập với timeout riêng, sau đó outer transaction được resume.

Từ Spring 5.3 có `timeoutString` cho cấu hình kiểu string hoặc placeholder:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    timeoutString = "${tx.order.timeout:15}"
)
public void confirmOrder() {
    // ...
}
```

Đây là fragment, cần Spring property resolution khi chạy. Giá trị được resolve phải hợp lệ theo số giây. Nên dùng **một** trong `timeout` hoặc `timeoutString` cho một phương thức, tránh tạo cấu hình mâu thuẫn.

### 5.1. Timeout không luôn là phép ngắt CPU ngay tại giây thứ N

`PlatformTransactionManager` khác nhau áp dụng timeout khác nhau:

- Với Spring JDBC, deadline có thể được lưu trên resource và áp dụng thành query timeout thông qua `JdbcTemplate`/`DataSourceUtils` khi tạo `Statement`.
- Với JPA, cơ chế timeout phụ thuộc transaction manager, JPA provider và JDBC driver.
- Có backend không hỗ trợ timeout tùy biến và có thể từ chối yêu cầu hoặc chỉ áp dụng một phần.
- `Thread.sleep()` hay tính toán Java thuần không bảo đảm tự ném exception đúng thời điểm timeout.

Vì vậy, không thử timeout bằng cách sleep rồi kết luận Spring luôn “giết” thread đúng 8 giây. Hãy kiểm chứng bằng câu lệnh/resource thực tế và xem loại exception mà backend trả về.

### 5.2. Suspend không đồng nghĩa dừng đồng hồ của outer

Một inner `REQUIRES_NEW(timeout=5)` chạy trong khi T1 đã mở: T1 có thể bị suspend khỏi thread, nhưng việc đó không phải lời hứa gia hạn hay làm mới timeout của T1. Nếu tổng quy trình phải hoàn tất trong khoảng cố định, deadline tổng thể và các lần retry cần được thiết kế ở tầng use case.

## 6. Read-only: hint khi tạo physical transaction

`readOnly=true` cho biết code **dự kiến không ghi** trong transaction. Với JDBC, manager có thể gọi `Connection.setReadOnly(true)`; với JPA/Hibernate, provider có thể áp dụng optimization cho persistence context hoặc flush handling.

```java
@Transactional(readOnly = true)
public List<OrderView> listOrders() {
    // Query qua repository
}
```

Đây là fragment, cần class/method/repository trong ứng dụng. Nếu `listOrders()` bắt đầu transaction mới, read-only hint có thể được áp dụng khi resource được chuẩn bị. Nếu method chỉ tham gia một T1 read-write, inner `readOnly=true` **không đổi T1 thành read-only**.

Chiều ngược lại cũng quan trọng: outer `readOnly=true` rồi inner `@Transactional(REQUIRED, readOnly=false)` **không biến T1 thành read-write**. Manager vẫn có thể duy trì metadata/read-only của outer và, khi strict validation được bật, từ chối một số kiểu mismatch.

### 6.1. Read-only không phải permission system

`readOnly=true` có thể chỉ là hint; một số driver/DB không cấm mọi câu `UPDATE`. Muốn chặn ghi về mặt bảo mật, phải dùng quyền database và kiểm thử thực tế. Đừng coi sự thành công của một query hay `Connection.isReadOnly()` là phép kiểm thử đầy đủ cho toàn backend.

### 6.2. Lưu ý với `SUPPORTS`

Một scope `SUPPORTS(readOnly=true)` khi không có physical transaction vẫn có thể cung cấp read-only metadata cho một số managed resources trong application context. Nhưng không thể từ đó kết luận JDBC transaction mới đã bắt đầu hoặc SQL sẽ rollback cùng nhau. Đây là khác biệt giữa **metadata/hint** và **cấu hình của physical transaction**.

## 7. Tên giao dịch và labels

`TransactionDefinition` có tên transaction phục vụ logging, tracing hoặc monitoring. Khi dùng programmatic transaction, có thể gọi:

```java
DefaultTransactionDefinition def =
        new DefaultTransactionDefinition();
def.setName("billing.endOfDay");
TransactionStatus status = txManager.getTransaction(def);
```

Đây là **fragment minh họa**; `txManager` phải là bean phù hợp và status phải được commit/rollback đúng một lần sau công việc. Tên là metadata của Spring, không phải ID do database cung cấp.

Với declarative `@Transactional`, Spring thường tự đặt tên theo **fully qualified class + method**, ví dụ `com.example.PaymentService.charge`. Annotation **không có** thuộc tính `name` để đặt tùy ý như `DefaultTransactionDefinition.setName()`.

Nếu inner `REQUIRED` chỉ join T1, không nên kỳ vọng tên transaction đang gắn ở outer tự biến thành tên của inner. Ở imperative transaction, có thể xem `TransactionSynchronizationManager.getCurrentTransactionName()` để chẩn đoán.

`@Transactional(label = {"billing", "priority"})` cung cấp labels cho transaction manager. Manager có thể diễn giải labels theo implementation; **không có quy tắc chung** rằng label sẽ đổi isolation, read-only hoặc timeout trên mọi database.

## 8. `transactionManager` qualifier: được chọn dù new hay join

Một ứng dụng có thể có nhiều transaction managers:

```java
@Transactional(transactionManager = "ordersTxManager")
public void reserveOrder() {
    // Dùng manager có bean name hoặc qualifier phù hợp
}
```

Đây là fragment. `transactionManager` hoặc alias `value` chọn manager dùng cho transactional invocation. Quyết định đó được thực hiện ngay cả khi manager phát hiện một transaction sẵn có để tham gia.

Nếu hệ thống có hai datasources độc lập, chọn manager cho datasource A không tự làm các thao tác trên datasource B cùng rollback. Muốn nhất quán đa tài nguyên cần cơ chế phù hợp như JTA/XA khi thực sự cần hoặc outbox/saga/compensation theo kiến trúc.

Một sai lầm khác là DAO lấy một JDBC connection trực tiếp từ một datasource khác thay vì qua `JdbcTemplate`/`DataSourceUtils` tương thích với manager. Khi đó bạn có thể thấy log Spring mở T1, nhưng SQL mà bạn quan sát lại auto-commit ngoài T1.

## 9. Rollback rules vẫn quan trọng khi chỉ tham gia transaction

`rollbackFor` và `noRollbackFor` không phải cấu hình isolation của connection. Chúng là **quy tắc advice đánh giá khi method kết thúc bằng exception**.

Theo cấu hình mặc định thông thường của Spring 6.2:

- `RuntimeException` hoặc `Error` thoát khỏi transactional invocation kích hoạt rollback.
- Checked `Exception` thường không tự gây rollback.
- Có thể thay đổi bằng `rollbackFor`, `noRollbackFor`.
- Từ Spring 6.2, có tùy chọn global default như `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`; phải kiểm tra cấu hình ứng dụng thực tế.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = java.io.IOException.class
)
public void importData() throws java.io.IOException {
    // Ném IOException ra ngoài transactional boundary nếu nhập lỗi
}
```

Đây là fragment minh họa. Giả sử method này tham gia T1; khi `IOException` thoát khỏi inner transaction advice và khớp rollback rule, manager có thể đánh dấu transaction chung **rollback-only**. Nếu outer bắt `IOException` rồi return bình thường, outer vẫn có thể gặp `UnexpectedRollbackException` ở commit vì T1 đã bị đánh dấu.

Nói cách khác, rollback rule **vẫn được áp dụng ở logical scope tham gia**, khác với isolation/timeout/read-only của physical transaction mới. Đừng đưa tất cả vào một nhóm “bị bỏ qua khi `isNewTransaction=false`”.

### 9.1. Exception bị bắt và nuốt bên trong method

Nếu exception phát sinh rồi bị catch mà không thoát khỏi transactional advice, interceptor có thể đi theo nhánh return bình thường. Khi nghiệp vụ thực sự cần rollback mà vẫn muốn trả một kết quả thường, có thể dùng `TransactionStatus.setRollbackOnly()` ở scope phù hợp; cần thông báo caller biết operation không được commit.

`setRollbackOnly()` chỉ đánh dấu trạng thái, không làm SQL được undo ngay tại dòng gọi. Transaction manager xử lý rollback khi boundary kết thúc. `isCompleted()` cho biết scope đã hoàn tất, **không** chứng minh outcome là commit.

## 10. `validateExistingTransaction`: kiểm tra mismatch thay vì âm thầm bỏ qua

Một số transaction managers kế thừa `AbstractPlatformTransactionManager` cung cấp:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

Đây là fragment minh họa. API dùng **`setValidateExistingTransaction`** (tên method số ít); `dataSource` phải tồn tại. Mặc định validation này là `false`: inner `REQUIRED` thường leniently join T1 và không áp đặt isolation/timeout/read-only riêng lên T1.

Khi bật, Spring có thể từ chối participation với **isolation không tương thích**, và từ chối **read-write inner** muốn join **read-only outer**, thay vì âm thầm dùng outer characteristics. Nó không biến transaction đang hoạt động thành transaction có isolation mới; cũng không cấp timeout riêng cho inner.

Ví dụ:

```text
OUTER T1: REQUIRED, isolation=READ_COMMITTED, readOnly=false
      |
      +-- INNER REQUIRED, isolation=SERIALIZABLE, readOnly=true
```

- Lenient: INNER tham gia T1, thực tế dùng `READ_COMMITTED` và read-write của T1.
- Strict validation: INNER có thể bị từ chối do yêu cầu isolation `SERIALIZABLE` không khớp T1, trước khi business body của inner chạy.

**Đừng suy diễn validation đối xứng mọi hướng**: inner read-only muốn tham gia outer read-write không nhất thiết bị từ chối chỉ do read-only; trường hợp rõ nhất được tài liệu Spring nêu là **inner read-write tham gia outer read-only**. Validation không phải giải pháp để thay đổi thuộc tính T1, chỉ giúp phát hiện sai kỳ vọng sớm.

## 11. Transaction manager và backend có thể áp dụng khác nhau

| Manager / resource | Điều cần xác minh |
| --- | --- |
| `JdbcTransactionManager` / `DataSourceTransactionManager` | Isolation/read-only qua JDBC connection khi bắt đầu, timeout/query timeout qua Spring JDBC, commit/rollback với connection |
| `JpaTransactionManager` | JPA `EntityManager`/persistence provider, flush behavior và khả năng apply isolation/timeout phụ thuộc provider/dialect |
| `JtaTransactionManager` | Hạ tầng transaction của container/provider; không giả định mọi isolation request có thể được set per transaction |
| Reactive transaction manager | Dùng Reactor Context thay thread-bound JDBC transaction, cần reactive resource và API thích hợp |

Một manager có thể từ chối mức isolation hoặc timeout nó không hỗ trợ. `Isolation.DEFAULT` không có nghĩa luôn `READ_COMMITTED`. `readOnly=true` chỉ là hint trừ khi một integration/backend cụ thể thực thi cứng.

Sơ đồ logic khi **tạo physical transaction mới**:

```text
Transaction advice / TransactionTemplate
       |
       v
transactionManager.getTransaction(definition)
       |
       +-- xét propagation và transaction đang active
       +-- nếu tạo mới: lấy resource/connection
       +-- cấu hình isolation, read-only khi hỗ trợ
       +-- thiết lập deadline/timeout metadata
       +-- gắn transaction resource & synchronization
       |
       v
Business method + repository/DAO
       |
       v
commit hoặc rollback theo kết quả và rollback-only
       |
       v
cleanup resource, khôi phục connection state
```

Đây là sơ đồ khái niệm, không mô tả chính xác mọi bước trong tất cả `PlatformTransactionManager` implementations.

Để kiểm chứng, đừng chỉ nhìn thuộc tính `@Transactional` trên source: cần xác định **manager nào được chọn**, resource nào đang được sử dụng, transaction có mới không, và DB thực sự commit/rollback như thế nào.

## 12. Ví dụ Java 17 chạy độc lập: REQUIRED tham gia và REQUIRES_NEW mở transaction

Ví dụ dùng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19** và H2 in-memory. Nó tập trung vào ba scope:

1. OUTER: `REQUIRED`, chưa có transaction nên mở **T1** với `READ_COMMITTED`, read-write, timeout 30 giây.
2. JOIN: `REQUIRED` yêu cầu `SERIALIZABLE`, read-only, timeout 1 giây, nhưng **tham gia T1**.
3. NEW: `REQUIRES_NEW` yêu cầu `SERIALIZABLE`, read-only, timeout 5 giây, nên mở **T2** độc lập rồi trả quyền điều khiển cho T1.

Chương trình kiểm tra `TransactionStatus.isNewTransaction()` và metadata imperative của `TransactionSynchronizationManager`. **Timeout không được đo bằng output**: kiểm thử timeout cần một operation thực trên resource/backend thích hợp.

### 12.1. Cấu trúc và dependency

```text
tx-attributes/
├── pom.xml
└── src/main/java/demo/TxScopeDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-attributes</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp IoC/configuration, `spring-jdbc` cung cấp `JdbcTemplate`, JDBC transaction manager và các dependency transaction liên quan. H2 là JDBC database chỉ dùng lúc chạy. Không cần Spring Boot auto-configuration để hiểu ví dụ.

### 12.2. Mã nguồn một file

File `src/main/java/demo/TxScopeDemo.java`:

```java
package demo;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Configuration
@EnableTransactionManagement
public class TxScopeDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:scope_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    InnerService innerService() {
        return new InnerService();
    }

    @Bean
    OuterService outerService(InnerService inner, JdbcTemplate jdbc) {
        return new OuterService(inner, jdbc);
    }

    public static void main(String[] args) {
        try (var ctx =
                     new AnnotationConfigApplicationContext(TxScopeDemo.class)) {

            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            ctx.getBean(OuterService.class).run();

            int amount = jdbc.queryForObject(
                    "SELECT balance FROM wallet WHERE id = 1",
                    Integer.class);
            System.out.println("AFTER_COMMIT=" + amount);
        }
    }

    private static void show(String label) {
        TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();
        Integer level = TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

        String isolation;
        if (level == null) {
            isolation = "DEFAULT";
        } else if (level == Connection.TRANSACTION_READ_COMMITTED) {
            isolation = "READ_COMMITTED";
        } else if (level == Connection.TRANSACTION_SERIALIZABLE) {
            isolation = "SERIALIZABLE";
        } else {
            isolation = "OTHER(" + level + ")";
        }

        System.out.println(label
                + ": new=" + status.isNewTransaction()
                + ", readOnly="
                + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly()
                + ", isolation=" + isolation);
    }

    public static class InnerService {

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE,
            timeout = 1,
            readOnly = true
        )
        public void join() {
            show("JOIN");
        }

        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            isolation = Isolation.SERIALIZABLE,
            timeout = 5,
            readOnly = true
        )
        public void newTransaction() {
            show("NEW");
        }
    }

    public static class OuterService {
        private final InnerService inner;
        private final JdbcTemplate jdbc;

        public OuterService(InnerService inner, JdbcTemplate jdbc) {
            this.inner = inner;
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED,
            timeout = 30,
            readOnly = false
        )
        public void run() {
            show("OUTER");
            jdbc.update(
                    "UPDATE wallet SET balance = balance - 10 WHERE id = 1");
            inner.join();
            inner.newTransaction();
            show("RESUME");
        }
    }
}
```

Các bean `OuterService` và `InnerService` là **hai đối tượng được container quản lý**. Lời gọi `inner.join()` và `inner.newTransaction()` vượt qua transaction proxy của bean inner, nên annotation được áp dụng. Không đặt inner method trong cùng class và gọi `this.method()`, vì proxy mode sẽ bỏ qua boundary đó.

`JdbcTransactionManager` ở cấu hình mặc định có `validateExistingTransaction=false`, cho phép inner `REQUIRED` join T1 dù yêu cầu isolation khác. Demo không ghi DB trong T2, nên không phụ thuộc các vấn đề concurrency/locking giữa hai connection.

### 12.3. Chạy và kiểm tra output

Tại thư mục `tx-attributes`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxScopeDemo
```

Các dòng **do chương trình tự in ra**, bỏ qua log thư viện:

```text
OUTER: new=true, readOnly=false, isolation=READ_COMMITTED
JOIN: new=false, readOnly=false, isolation=READ_COMMITTED
NEW: new=true, readOnly=true, isolation=SERIALIZABLE
RESUME: new=true, readOnly=false, isolation=READ_COMMITTED
AFTER_COMMIT=90
```

Diễn giải:

- **OUTER:** T1 mới, nên trạng thái ghi `new=true`; read-only là `false`, isolation được yêu cầu là `READ_COMMITTED`.
- **JOIN:** inner `REQUIRED` tham gia T1 (`new=false`). Yêu cầu inner `SERIALIZABLE`, read-only, timeout 1 giây không đổi isolation/read-only/deadline của T1. Metadata mà inner thấy vẫn là `READ_COMMITTED` và `false`.
- **NEW:** inner `REQUIRES_NEW` tạm gác T1, mở T2; metadata trong T2 là read-only `true`, isolation `SERIALIZABLE`, status `new=true`.
- **RESUME:** sau T2, T1 tiếp tục với metadata cũ. `TransactionStatus` của outer vẫn là status đã mở T1.
- **AFTER_COMMIT:** outer return bình thường, T1 commit cập nhật số dư từ 100 xuống 90.

Ví dụ dùng một datasource H2 và một transaction manager để câu hỏi “cái gì mới, cái gì join” được nhìn rõ. Nó **không chứng minh** read-only là cơ chế chặn SQL write ở H2 và **không phải test timeout**.

### 12.4. Biến thể kiểm tra strict validation

Chỉ thay bean manager bằng:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

Không thêm một manager thứ hai. Khi chạy lại trong một JVM mới, inner `join()` yêu cầu `SERIALIZABLE` khác T1 `READ_COMMITTED`. Manager từ chối participation bằng `IllegalTransactionStateException` trước khi body `join()` chạy. Lỗi unchecked thoát qua outer transactional advice nên T1 bị rollback; không còn các dòng `JOIN`, `NEW`, `RESUME` hay `AFTER_COMMIT=90` của biến thể lenient. Đây là **test từ chối mismatch**, không phải cách chuyển T1 sang `SERIALIZABLE`.

## 13. Cấu hình programmatic: cùng quy tắc áp dụng

Dùng `PlatformTransactionManager` trực tiếp cũng có logic begin/join giống `@Transactional`:

```java
DefaultTransactionDefinition def =
        new DefaultTransactionDefinition();
def.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ);
def.setTimeout(12);
def.setReadOnly(true);
def.setName("reports.run");

TransactionStatus status = manager.getTransaction(def);
try {
    runReportQueries();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

Đây là fragment; `manager` và `runReportQueries()` cần được định nghĩa, cũng cần imports. Nếu chưa có transaction, manager bắt đầu transaction mới theo definition. Nếu đã có T1 và `REQUIRED` tham gia, các thuộc tính vật lý của T1 vẫn chi phối theo semantics manager. Không nên tự gọi `commit()` trên status do AOP hoặc `TransactionTemplate` đang sở hữu.

Một lựa chọn ít dễ sai lifecycle hơn:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(5);
template.setReadOnly(true);

String result = template.execute(status -> {
    return "read complete";
});
```

Đây là fragment; `manager` phải tồn tại. Template quản lý commit/rollback và cleanup của callback. Về mặt `TransactionDefinition`, quy tắc của isolation/timeout/readOnly không khác chỉ vì dùng API thay vì annotation.

## 14. Bảng các tình huống dễ nhầm

Giả sử một JDBC manager hỗ trợ thuộc tính tương ứng và dùng lenient mode.

| Tình huống | Physical transaction | Hiệu lực thuộc tính |
| --- | --- | --- |
| Chưa có transaction, `REQUIRED(SERIALIZABLE, timeout=10, readOnly=true)` | Mở T1 | Manager cố áp dụng yêu cầu vào T1 |
| Đã có T1 `READ_COMMITTED`, inner `REQUIRED(SERIALIZABLE, timeout=10, readOnly=true)` | Join T1 | Giữ isolation/timeout/read-only của T1 |
| Đã có T1, inner `REQUIRES_NEW(SERIALIZABLE, timeout=10, readOnly=true)` | Suspend T1, mở T2 | Áp dụng yêu cầu trên T2 nếu resource hỗ trợ |
| Đã có T1, inner `NESTED` | Savepoint trong T1 nếu hỗ trợ | Không có isolation/timeout vật lý độc lập như T2 |
| Không có transaction, `SUPPORTS(readOnly=true)` | Không bắt buộc mở transaction | Có thể có resource-level read-only hint; không phải DB transaction mới |
| Đã có T1, inner `NOT_SUPPORTED` | Suspend T1 | SQL ngoài T1 không được rollback tự động cùng T1 |
| Không có transaction, inner `MANDATORY` | Không mở | Ném lỗi vì thiếu transaction |
| Đã có T1, inner `NEVER` | Không mở | Ném lỗi vì điều kiện tồn tại không hợp lệ |
| Inner `REQUIRED(rollbackFor=IOException.class)` join T1, IOException thoát advice | Vẫn T1 | Rule có thể đánh dấu T1 rollback-only dù không có transaction mới |

Nếu bật strict validation, các tình huống join với isolation hoặc read-only không tương thích có thể chuyển từ “join lenient” thành **ném lỗi**, không phải “tạo transaction mới thay thế”.

## 15. Các lỗi phổ biến và cách sửa

**Lỗi 1 – Hiểu `REQUIRED` là luôn mở transaction mới.**  
`REQUIRED` nghĩa là “phải có transaction”: nếu có thì join, nếu không thì mở mới. Dùng đúng physical boundary để chọn isolation/timeout.

**Lỗi 2 – Đặt isolation cao ở một repository method và tin nó nâng transaction của service.**  
Khi repository join transaction của service, isolation ngoài tiếp tục chi phối. Nâng isolation ở outer service hoặc tách nghiệp vụ khi thực sự cần transaction độc lập.

**Lỗi 3 – Inner `timeout=1` nhưng query vẫn chạy theo deadline outer.**  
Không có timeout riêng khi join. Đặt timeout ở scope bắt đầu transaction và kiểm tra query timeout/backend.

**Lỗi 4 – Inner `readOnly=false` tưởng tắt read-only của outer.**  
Không có cơ chế reset read-only như thế trên cùng physical transaction. Với validation nghiêm ngặt, một số mismatch còn bị từ chối.

**Lỗi 5 – Coi `readOnly=true` là quyền DB read-only tuyệt đối.**  
Đây thường là hint. Kiểm tra DB permissions và behavior thực tế nếu yêu cầu chặn ghi.

**Lỗi 6 – Quên `rollbackFor` vẫn hiệu lực trong participating scope.**  
Một inner exception có thể khiến T1 rollback-only; outer bắt exception rồi return không đảm bảo commit thành công.

**Lỗi 7 – Nhầm `REQUIRES_NEW` với `NESTED`.**  
`REQUIRES_NEW` có transaction vật lý riêng; `NESTED` thường là savepoint trong cùng T1. Pool, commit độc lập và isolation khác nhau.

**Lỗi 8 – Self-invocation làm annotation inner không chạy.**  
Trong proxy mode, `this.save()` không đi qua proxy. Đặt transaction boundary trên public method được gọi từ ngoài hoặc tách bean.

**Lỗi 9 – Dao sử dụng datasource khác.**  
Manager có thể mở T1 đúng, nhưng một SQL chạy trên connection không tham gia T1 sẽ không rollback cùng T1.

**Lỗi 10 – Dùng log/`isCompleted()` như bằng chứng transaction đã commit.**  
`isCompleted()` chỉ báo scope xong, có thể sau rollback. Hãy kiểm chứng hậu điều kiện database sau boundary, và ghi nhận exception/result thực tế.

**Lỗi 11 – Tin mọi DB triển khai isolation giống nhau.**  
Một số DB không có dirty read theo cùng cách hoặc dùng MVCC snapshot semantics. Chạy concurrency tests trên đúng DB/driver.

**Lỗi 12 – Tắt validation để bỏ qua thiết kế boundary sai.**  
Lenient mode cho phép join với đặc tính outer, không “sửa” nhu cầu isolation của inner. Nếu yêu cầu nghiệp vụ thật sự đòi isolation khác, phải thiết kế transaction boundary thích hợp.

## 16. Chiến lược thiết kế và kiểm thử

Một thiết kế tốt thường đặt transaction boundary ở **application service** nơi có đủ bối cảnh nghiệp vụ:

```text
Controller/Handler
      |
      v
ApplicationService.execute()
  @Transactional(REQUIRED,
                 isolation=READ_COMMITTED,
                 timeout=30)
      |
      +-- DomainService.validate()     join T1
      +-- Repository.update()          join T1
      +-- Repository.insertOutbox()    join T1
      |
      v
commit T1
```

Khi inner service chỉ là thành phần của cùng use case, đừng yêu cầu nó tự chọn isolation/timeout trái outer rồi trông chờ hiệu lực vật lý. Nếu một công việc độc lập có lý do vững chắc để commit riêng, mới cân nhắc `REQUIRES_NEW` và xử lý tính nhất quán sau partial success.

Kiểm thử nên có:

1. **New REQUIRED:** bắt đầu từ caller chưa có transaction, xem status, metadata và DB state sau commit.
2. **Participating REQUIRED:** outer `READ_COMMITTED`, inner `SERIALIZABLE`; xác nhận inner dùng outer trong lenient mode.
3. **REQUIRES_NEW:** xác nhận inner mở T2 và outer được resume với metadata gốc.
4. **Strict validation:** bật `setValidateExistingTransaction(true)` và kiểm tra mismatched isolation bị từ chối.
5. **Rollback rule:** inner exception khớp rollback rule, outer bắt lỗi; kiểm tra T1 có rollback-only và commit có thể thất bại.
6. **Timeout thật:** test trên backend/driver có query bị timeout, đừng chỉ dùng `Thread.sleep`.
7. **Read-only thực tế:** test hint và khả năng enforcement trên đúng database.
8. **Isolation/concurrency:** dùng hai transaction đồng thời để kiểm tra dirty/nonrepeatable read hoặc serialization conflict, tùy yêu cầu.
9. **Proxy boundary:** xác nhận method được gọi qua Spring proxy, không qua `this.method()`.
10. **Resource consistency:** manager và DAO dùng đúng data source; kiểm tra cả external side effects nếu có.

Trong Spring Test, test method có `@Transactional` có thể bị framework tự rollback khi kết thúc. Vì vậy đừng để test-level rollback che giấu service thiếu transaction advice; cần kiểm chứng trạng thái database ngoài boundary của test khi phù hợp.

## 17. Tự kiểm tra kiến thức

**1.** Outer `READ_COMMITTED`, inner `REQUIRED(SERIALIZABLE)`. Khi manager lenient, isolation thực tế là gì?  
**Đáp án:** T1 tiếp tục `READ_COMMITTED`; inner không đổi isolation của transaction đang tồn tại.

**2.** Đổi inner thành `REQUIRES_NEW(SERIALIZABLE)`, điều gì khác?  
**Đáp án:** Outer T1 bị suspend, manager mở T2 mới và có cơ hội áp dụng `SERIALIZABLE` cho T2.

**3.** Inner `REQUIRED(timeout=2)` có gia hạn hoặc reset deadline T1 không?  
**Đáp án:** Không. Deadline thuộc physical transaction T1 đã mở, inner không tạo timeout transaction vật lý riêng.

**4.** `readOnly=true` có khiến mọi database chắc chắn từ chối `UPDATE` không?  
**Đáp án:** Không. Nó có thể là optimization hint; enforcement phụ thuộc provider/DB.

**5.** Bật strict validation có tự “nâng” isolation T1 theo inner không?  
**Đáp án:** Không. Nó có thể từ chối join khi isolation mismatch.

**6.** `rollbackFor=IOException.class` ở inner `REQUIRED` còn ý nghĩa không?  
**Đáp án:** Có. Nếu exception khớp rule thoát advice, transaction chung có thể bị đánh dấu rollback-only.

**7.** Có thể dùng `@Transactional(name="my-tx")` không?  
**Đáp án:** Không. Declarative transaction name thường tự sinh từ class/method; programmatic definition có `setName()`.

**8.** `isNewTransaction()==false` chứng minh không có transaction DB không?  
**Đáp án:** Không. Inner `REQUIRED` join T1 thường trả `false`, dù chạy trong transaction.

**9.** `SUPPORTS(readOnly=true)` khi chưa có transaction có luôn mở T1 không?  
**Đáp án:** Không. Có thể có metadata/hint nhưng không bắt buộc có physical transaction.

**10.** `NESTED` trong một T1 có transaction isolation riêng giống `REQUIRES_NEW` không?  
**Đáp án:** Không. Nested scope thường dùng savepoint trên cùng physical transaction, nếu backend hỗ trợ.

## 18. Checklist ghi nhớ

- Hỏi trước tiên: **scope này đã qua transaction advice chưa và manager nào được chọn?**
- Sau đó: **propagation khiến nó mở mới, join, suspend, savepoint hay không có transaction?**
- Với transaction **mới**, manager có thể áp dụng isolation, timeout, read-only, transaction name và metadata liên quan tùy resource.
- Với scope **join**, transaction vật lý của outer thường quyết định isolation, timeout, read-only; thuộc tính inner không tự thay các giá trị đó.
- Với `REQUIRES_NEW`, manager cấu hình một transaction vật lý riêng; nhớ chi phí connection và tính độc lập của commit.
- Với `NESTED`, savepoint không tương đương physical transaction mới.
- Rollback rules vẫn được xét khi exception thoát khỏi **logical scope** đang join.
- Nếu cần phát hiện mismatch thay vì âm thầm chấp nhận, dùng `setValidateExistingTransaction(true)` khi manager hỗ trợ.
- Luôn kiểm chứng đúng database, đúng datasource, đúng proxy boundary và outcome sau transaction.

**Một câu trả lời chuẩn:** `propagation` quyết định việc tạo mới; **isolation, timeout và read-only ở mức physical transaction chủ yếu được thiết lập khi transaction thật sự bắt đầu**, trong khi **rollback rules và lựa chọn transaction manager vẫn có ý nghĩa ngay cả với scope tham gia**.

## Tài liệu Spring chính thức

- [Using @Transactional — các settings và transaction name](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Transaction Propagation — REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Javadoc @Transactional của Spring 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [TransactionDefinition API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html)
- [AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)