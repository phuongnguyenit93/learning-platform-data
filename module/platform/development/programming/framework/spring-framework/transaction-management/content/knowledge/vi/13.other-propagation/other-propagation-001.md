# SUPPORTS và hành vi có hoặc không có giao dịch hiện hành trong Spring Framework

## Câu trả lời cốt lõi

`Propagation.SUPPORTS` có nghĩa: **nếu đã có một transaction tương thích với transaction manager đang dùng thì tham gia transaction đó; nếu chưa có thì thực thi mà không bắt đầu một giao dịch vật lý mới**. Đây là chiến lược *chấp nhận có hoặc không có transaction*, không phải lựa chọn tự động bảo đảm atomicity cho mọi lời gọi.

```java
@Transactional(propagation = Propagation.SUPPORTS)
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

Đây là **fragment minh họa**, cần `Account`, `repository`, imports và bean wiring. Khi gọi method qua Spring transaction advice:

- **Caller đã có transaction T1:** `findAccount` tham gia T1. Nó sử dụng các tài nguyên và đặc tính vật lý của T1; nếu method phát sinh lỗi ảnh hưởng rollback, T1 có thể bị đánh dấu rollback-only.
- **Caller chưa có transaction:** Spring không mở physical transaction T2 chỉ vì gặp annotation `SUPPORTS`. DAO vẫn có thể đọc/ghi, nhưng tính commit/rollback phụ thuộc auto-commit hoặc resource/backend mà DAO đang dùng.
- **Điểm dễ nhầm:** trong cấu hình mặc định của nhiều Spring imperative transaction managers, `SUPPORTS` khi không có physical transaction **vẫn có thể kích hoạt transaction synchronization**. Vì vậy `TransactionSynchronizationManager.isSynchronizationActive()` có thể là `true` khi `isActualTransactionActive()` là `false`.

Cần phân biệt rõ: **đang có Spring synchronization scope** không đồng nghĩa **đang có physical database transaction**. Các tài nguyên JDBC/JPA được tái sử dụng trong scope synchronization-only không vì thế trở thành một nhóm SQL có khả năng rollback nguyên tử.

Bài này thuộc **Spring Framework – transaction-management**, nhóm **Propagation khác**. Nội dung giới thiệu semantics chuẩn của `SUPPORTS`, cơ chế Spring quản lý resource, cách dùng trong service/repository, quy tắc rollback, rủi ro khi lồng các propagation khác, và một ví dụ Java 17/Spring JDBC/H2 chạy độc lập.

---

## 1. `SUPPORTS` trả lời câu hỏi nào?

Propagation là chính sách Spring xử lý **sự tồn tại của transaction ở thời điểm vào một transactional method**. `SUPPORTS` có hai nhánh:

```text
                   Call đến @Transactional(SUPPORTS)
                                 |
                                 v
           Có transaction vật lý đang active với manager này?
                    /                              \
                  Có                              Không
                  |                                 |
                  v                                 v
         Tham gia transaction T1             KHÔNG bắt đầu T2
         cùng transaction resource           chạy không có physical transaction
                  |                                 |
                  v                                 v
         Completion gắn với T1              SQL/ORM hành xử theo resource
         rollback-only có thể lan           và cấu hình synchronization
```

Từ “SUPPORTS” nên đọc là “**hỗ trợ giao dịch hiện tại nếu có**”, không phải “**tự tạo giao dịch hỗ trợ**”. Nó cũng không phải `REQUIRES_NEW` hay `NESTED`.

### Nhánh A: đã có transaction

Ví dụ `OrderService.placeOrder()` là một public Spring bean method `@Transactional(REQUIRED)` đã mở T1, rồi gọi `AccountQueryService.findAccount()` `@Transactional(SUPPORTS)` thông qua proxy của một bean khác.

```text
OrderService.placeOrder()        @Transactional(REQUIRED)
  |                              T1: started
  +--> AccountQueryService.findAccount()
                                 @Transactional(SUPPORTS)
                                 joins T1
  +--> OrderRepository.save()
                                 joins T1
  |
  v
commit T1 hoặc rollback T1
```

`findAccount()` **không mở T2**, cũng không commit riêng khi return. Các query của nó có thể tham gia cùng connection/persistence context của T1. Nếu T1 rollback, những thao tác ghi thuộc T1 cũng rollback.

### Nhánh B: chưa có transaction

```text
HTTP handler / scheduler
  |
  +--> AccountQueryService.findAccount()
                                 @Transactional(SUPPORTS)
                                 no physical transaction
  |
  +--> laterRepository.update()
                                 có thể auto-commit riêng
```

Spring không đặt JDBC `autoCommit=false` chỉ vì method `SUPPORTS` được gọi ngoài transaction. Một câu SQL có thể commit ngay khi thực thi theo default của connection. Hai câu `UPDATE` nối tiếp không tự động atomic chỉ vì cùng method có annotation.

Trường hợp có transaction thật **không được suy ra chỉ từ annotation**. Phải xem caller, propagation chain, transaction manager đang chọn và cơ chế AOP.

## 2. So sánh nhanh với các propagation khác

| Propagation | Khi chưa có transaction | Khi đang có transaction |
| --- | --- | --- |
| `REQUIRED` (mặc định) | **Tạo transaction mới** | Tham gia transaction hiện tại |
| `SUPPORTS` | **Không tạo physical transaction** | Tham gia transaction hiện tại |
| `MANDATORY` | Ném lỗi thiếu transaction | Tham gia transaction hiện tại |
| `REQUIRES_NEW` | Tạo transaction mới | Suspend transaction ngoài, mở transaction mới độc lập |
| `NOT_SUPPORTED` | Chạy phi transactional | Suspend transaction ngoài, chạy phi transactional |
| `NEVER` | Chạy phi transactional | Ném lỗi nếu đã tồn tại transaction |
| `NESTED` | Có thể tạo transaction mới theo manager | Thường dùng savepoint trong cùng physical transaction, nếu hỗ trợ |

Phân biệt hai cặp rất hay nhầm:

- **`SUPPORTS` so với `REQUIRED`:** cả hai đều tham gia T1 nếu T1 đang có; khác biệt nằm ở **nhánh không có T1**: `REQUIRED` mở mới, `SUPPORTS` thì không.
- **`SUPPORTS` so với `NOT_SUPPORTED`:** khi đang có T1, `SUPPORTS` **tham gia T1** còn `NOT_SUPPORTED` **tạm gác T1** để chạy ngoài transaction. Khi không có T1, cả hai có thể chạy không có physical transaction, nhưng vẫn khác về chính sách propagation và synchronization.

`MANDATORY` là lựa chọn tốt nếu method **bắt buộc** phải nằm trong transaction của caller. Đừng dùng `SUPPORTS` như một cách “yêu cầu caller phải có transaction”; nó không từ chối caller thiếu transaction.

## 3. Logical scope, physical transaction và synchronization scope

Trong Spring có ba khái niệm cần phân tách:

1. **Logical transaction scope:** phạm vi được `TransactionInterceptor`, `TransactionTemplate` hoặc `PlatformTransactionManager` xử lý. Method `SUPPORTS` qua proxy có thể có logical scope dù không có database transaction.
2. **Physical transaction:** trạng thái commit/rollback thật do JDBC/JPA/JTA/resource backend quản lý. `SUPPORTS` không tự tạo physical transaction khi chưa có.
3. **Transaction synchronization:** cơ chế Spring đăng ký callback và gắn/tái sử dụng tài nguyên theo execution thread (với imperative transaction). Có thể active trong **empty transaction scope** mà vẫn không có physical transaction.

Ví dụ:

```text
SUPPORTS, caller không có transaction:
    logical scope:             CÓ
    physical JDBC transaction: KHÔNG
    Spring synchronization:    CÓ THỂ CÓ (tùy manager/config)

SUPPORTS, caller có T1:
    logical scope:             CÓ
    physical JDBC transaction: CÓ, T1 của caller
    Spring synchronization:    thường dùng context của T1
```

Sự xuất hiện của status object, transaction name hoặc synchronization callback không đồng nghĩa đã có `Connection.commit()`/`Connection.rollback()` được quản lý cho một physical transaction mới.

Đây là điểm phân biệt sâu của `SUPPORTS` so với chạy hoàn toàn không có một transactional scope nào.

## 4. Vì sao `isSynchronizationActive()` có thể là `true` dù không có transaction?

Trong Spring imperative transaction, `TransactionSynchronizationManager` là trung tâm lưu trạng thái **theo thread**, bao gồm transaction characteristics, synchronization callbacks và tài nguyên như JDBC `ConnectionHolder`.

Có hai phép kiểm tra khác nhau:

```java
boolean actual =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();
```

Đây là **fragment minh họa**, cần import `org.springframework.transaction.support.TransactionSynchronizationManager`.

- `isActualTransactionActive()` hỏi Spring có đánh dấu **actual transaction** ở thread này hay không.
- `isSynchronizationActive()` hỏi cơ chế **transaction synchronization** có đang active hay không.
- `sync=true`, `actual=false` là trạng thái hợp lệ khi manager bật synchronization cho một scope `SUPPORTS` không có physical transaction.
- `sync=false` không phải bằng chứng chắc chắn là không có transaction trong mọi môi trường: có manager có thể dùng policy tắt synchronization, hoặc ngữ cảnh không được truyền đúng thread.
- `actual=true` cho biết trạng thái Spring của execution hiện tại; vẫn phải xác minh DAO đang dùng đúng resource, vì nó không làm một JDBC connection tùy ý tham gia T1 một cách tự động.

### 4.1. Ba chính sách synchronization

Các transaction managers kế thừa `AbstractPlatformTransactionManager` có thể cấu hình:

| Chính sách | Ý nghĩa |
| --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Bật synchronization cho cả những scope “empty” như `SUPPORTS` không có backend transaction |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Chỉ bật synchronization khi có actual transaction |
| `SYNCHRONIZATION_NEVER` | Không bật transaction synchronization, kể cả với actual transaction |

Mặc định của `AbstractPlatformTransactionManager` là **`SYNCHRONIZATION_ALWAYS`**. Với `JdbcTransactionManager`/`DataSourceTransactionManager` chuẩn, khi caller chưa có transaction và vào `SUPPORTS`, bạn thường thấy:

```text
actual=false
sync=true
```

Đây là **kết quả dự kiến theo cấu hình mặc định đã nêu**, không phải điều kiện bắt buộc với mọi manager và mọi application context.

Muốn chỉ bật synchronization cho transaction thật, có thể cấu hình manager:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setTransactionSynchronization(
        AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

Đây là **fragment cấu hình**, cần `dataSource` và imports. Khi dùng chính sách này, một `SUPPORTS` không có T1 thường có `sync=false`. Đổi policy sẽ ảnh hưởng cách resource được bind/reuse và tương tác với các scope transaction khác; không đổi một cách tùy tiện trong production.

`SYNCHRONIZATION_NEVER` không có nghĩa tắt mọi physical transaction; nó chỉ tắt hạ tầng synchronization của manager. Một manager vẫn có thể điều phối begin/commit/rollback theo resource của nó.

### 4.2. Một transaction manager được quyền điều khiển synchronization tại một thời điểm

Transaction synchronization là ngữ cảnh gắn với thread và không hỗ trợ **nhiều transaction managers đồng thời cùng điều khiển synchronization** ở một thread theo cách tùy ý. Với ứng dụng nhiều datasource/managers, nested scopes hoặc resource managers khác nhau, cần xác định rõ manager nào sở hữu synchronization và khi nào nó được suspend/resume.

Javadoc Spring cũng cảnh báo nên dùng `SUPPORTS` cẩn thận khi bên trong nó lại gọi `REQUIRED` hoặc `REQUIRES_NEW`: một empty synchronization scope có thể ràng buộc tài nguyên trước khi scope mới bắt đầu, dẫn tới tương tác hoặc xung đột synchronization. Nếu cấu trúc này khó tránh, cần cấu hình manager phù hợp, thường cân nhắc **synchronization only on actual transaction**, rồi kiểm chứng bằng integration test trên resource cụ thể.

Không phải mọi lồng ghép như vậy đều chắc chắn lỗi, nhưng cũng không nên tin rằng nó luôn tương đương gọi method bình thường.

## 5. Resource reuse: cùng JDBC Connection nhưng vẫn không có atomicity

Điểm tinh tế nhất: khi `SUPPORTS` không có physical transaction nhưng synchronization đang active, Spring có thể **tái sử dụng cùng JDBC `Connection`** hoặc Hibernate `Session` trong cả logical scope. Điều này giúp lifecycle/resource sharing nhất quán cho data access code.

Ví dụ một service dùng `JdbcTemplate`:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void touchTwoRows() {
    jdbcTemplate.update("UPDATE audit SET touched = touched + 1 WHERE id = 1");
    jdbcTemplate.update("UPDATE audit SET touched = touched + 1 WHERE id = 2");
}
```

Đây là fragment, cần bean `jdbcTemplate` và bảng `audit`. Khi không có T1, với manager synchronization-always và JDBC resource integration phù hợp:

1. Spring bật synchronization cho scope.
2. `JdbcTemplate` dùng `DataSourceUtils` để lấy connection, có thể bind/reuse connection qua cả hai lệnh.
3. **Không có `doBegin()` của physical transaction** chỉ vì `SUPPORTS`; connection có thể vẫn để auto-commit mặc định `true`.
4. Từng `UPDATE` có thể commit riêng; nếu câu thứ hai lỗi, câu đầu có thể đã bền vững trong DB.
5. Cuối scope, synchronization hỗ trợ dọn dẹp và giải phóng resource; cleanup không phải phép rollback dữ liệu đã auto-commit.

**Tái sử dụng connection khác với transaction atomicity.** Một application không thể chỉ kiểm tra hai câu SQL dùng cùng connection rồi kết luận hai câu cùng rollback.

Nếu method thật sự cần tất cả-or-nothing, hãy dùng `REQUIRED` tại transaction boundary phù hợp, và đảm bảo DAO tham gia đúng resource manager.

### 5.1. Spring JDBC khác connection tự mở

`JdbcTemplate` dùng các hook của Spring (`DataSourceUtils`) để tham gia resource synchronization. Nếu code trực tiếp gọi `DriverManager.getConnection(...)` hoặc một datasource khác, connection đó có thể **không** được Spring quản lý trong scope.

Cùng một method có `@Transactional` không tự biến mọi connection thành connection của transaction manager. Ngược lại, với `SUPPORTS` không có transaction, ngay cả connection được Spring sync cũng không vì thế chuyển sang manual-commit.

### 5.2. Với JPA/Hibernate

Khi không có physical transaction, một persistence context/session có thể được tạo hoặc tái sử dụng theo scope quản lý của framework và provider. Tuy nhiên:

- Một số query đọc hoạt động ngoài transaction.
- Nhiều thao tác ghi, `flush()` hoặc lazy access có thể yêu cầu transaction thật, tùy JPA provider và cấu hình.
- Không dự đoán JPA write behavior chỉ từ ví dụ JDBC/H2.
- Một Session được tái sử dụng trong một scope không chứng minh SQL đã nằm trong cùng một database transaction.

Nguyên tắc đúng là phân biệt resource synchronization, persistence context và physical transaction của backend.

## 6. Phân tích `TransactionStatus`: có scope nhưng chưa chắc có transaction

Trong một invocation được Spring transaction advice quản lý, có thể đọc status bằng:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

boolean hasTx = status.hasTransaction();
boolean newTx = status.isNewTransaction();
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();
```

Đây là **fragment minh họa**, có API `hasTransaction()` từ Spring Framework 6.1+. `currentTransactionStatus()` đòi hỏi có transactional invocation context thích hợp; gọi ngoài một Spring AOP transaction boundary có thể ném `NoTransactionException`. Phần 9 cung cấp ví dụ Java 17/Spring Framework 6.2 chạy được.

| Tình huống | `hasTransaction()` | `isNewTransaction()` | `isActualTransactionActive()` | `isSynchronizationActive()` |
| --- | --- | --- | --- | --- |
| `SUPPORTS` không có T1, manager synchronization-always | `false` | `false` | `false` | thường `true` |
| `SUPPORTS` tham gia T1 từ `REQUIRED` | `true` | `false` | `true` | thường `true` |
| `REQUIRED` được gọi khi chưa có transaction | `true` | `true` | `true` | thường `true` |
| Code không được advice và ngoài transaction | Không có status AOP tương ứng | Không có status AOP tương ứng | thường `false` | thường `false` |

Bảng này giả sử manager Spring imperative chuẩn và một datasource phù hợp. Nếu policy synchronization khác hoặc transaction context không được truyền đúng thread, kết quả hai cột cuối có thể thay đổi. Một số trạng thái `TransactionStatus` là đặc tính của **logical scope hiện tại**, không phải thống kê toàn cục của mọi datasource.

**`isNewTransaction()==false` không tự nói rằng không có transaction**: `SUPPORTS` tham gia T1 cũng là `false`. Phải kết hợp `hasTransaction()` với hiểu biết về manager/physical resource.

### 6.1. `isCompleted()` không cho biết commit thành công

Một logical scope sau khi được manager xử lý hoàn tất có thể có `isCompleted()==true` cho cả đường commit và rollback. Trong method đang chạy, status thường chưa completed. Với `SUPPORTS` không có physical transaction, completed chỉ xác nhận **Spring đã kết thúc logical scope**, không chứng minh database từng commit hoặc rollback.

### 6.2. `setRollbackOnly()` trong SUPPORTS không có T1

Nếu một scope `SUPPORTS` **không có physical transaction**, việc đánh dấu `setRollbackOnly()` trên local `TransactionStatus` không thể undo những JDBC writes đã auto-commit ở một connection độc lập. Cờ rollback-only là một yêu cầu đối với transaction status của scope; khi không có resource transaction thực sự, **không có transaction vật lý nào để rollback**.

Khi `SUPPORTS` **tham gia T1**, việc đánh dấu rollback-only hoặc một exception khớp rollback rule lại có thể ảnh hưởng T1. Vì vậy code nghiệp vụ không nên dùng `SUPPORTS` với giả định “có transaction thì rollback, không có transaction vẫn somehow rollback”.

## 7. Các thuộc tính `@Transactional` trong SUPPORTS

### 7.1. `readOnly=true`: metadata/hint, không phải bảo đảm DB transaction

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    readOnly = true
)
public CustomerDetails lookup(long customerId) {
    return repository.getCustomerDetails(customerId);
}
```

Đây là fragment minh họa. Với caller đã có T1, method tham gia T1 và chịu read-only/isolation/timeout ở cấp physical transaction ngoài. Với caller chưa có T1, method không tạo transaction vật lý chỉ để áp dụng `readOnly=true`; một số resource management infrastructure vẫn có thể nhận metadata read-only của logical scope.

Nếu manager dùng `SYNCHRONIZATION_ALWAYS`, bạn có thể thấy `TransactionSynchronizationManager.isCurrentTransactionReadOnly()==true` trong scope không có physical transaction. Điều đó **không có nghĩa DB từ chối mọi `UPDATE`**. Quyền đọc/ghi thật phụ thuộc driver, provider, database và policy riêng.

### 7.2. `isolation` trong SUPPORTS

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    isolation = Isolation.SERIALIZABLE
)
public void checkBalance() {
    // ...
}
```

Đây là fragment minh họa. Nếu không có T1, method không mở physical transaction để nhận `SERIALIZABLE`; nếu tham gia T1, isolation của T1 thường tiếp tục chi phối. Không lấy việc khai báo `SERIALIZABLE` làm bằng chứng chống dirty read hoặc nonrepeatable read khi gọi độc lập.

Khi yêu cầu isolation không khớp outer transaction, một manager cấu hình `validateExistingTransaction=true` có thể từ chối participation, thay vì áp dụng isolation mới lên T1.

### 7.3. `timeout` trong SUPPORTS

`@Transactional(propagation=SUPPORTS, timeout=5)` không hứa sẽ cắt ngang method sau năm giây khi **không có physical transaction**. Nếu join T1, deadline của T1 vẫn chi phối transaction thực tế; inner không tự cấp deadline mới.

Timeout của physical transaction phụ thuộc manager/resource. Query timeout hoặc network timeout ngoài transaction là câu chuyện riêng, cần cấu hình ở tầng JDBC/HTTP/client thích hợp.

### 7.4. Rollback rules khi đã có T1

Các rule `rollbackFor`/`noRollbackFor` có thể có ý nghĩa trên **logical scope tham gia T1**, vì exception thoát khỏi inner transactional advice có thể khiến T1 rollback-only. Khi không có T1, rule không có physical transaction để undo các SQL auto-commit.

Cần phân biệt **thất bại nghiệp vụ** với **kết quả transaction**: một method có thể ném exception, nhưng nếu chạy ngoài physical transaction thì những write trước exception có thể đã commit.

## 8. AOP proxy là điều kiện để annotation SUPPORTS có hiệu lực

Trong Spring declarative transaction thông thường, `@Transactional` được áp dụng thông qua Spring AOP proxy. Điều này đúng với cả `SUPPORTS`.

```text
Caller -> Spring proxy -> TransactionInterceptor
                             |
                             +-- xác định propagation=SUPPORTS
                             +-- tìm transaction đang active
                             +-- tạo/join logical scope
                             +-- gọi target method
                             +-- hoàn tất scope / cleanup
```

Nếu cùng một bean gọi `this.supportsMethod()`, lời gọi nội bộ **không vượt qua proxy**, vì vậy annotation riêng trên `supportsMethod()` không tạo thêm logical scope như mong đợi. Điều này có thể khiến các cờ synchronization/readOnly bạn quan sát khác với lúc gọi qua bean proxy.

Ví dụ minh họa:

```java
@Service
public class ReportService {

    public void generate() {
        loadData();  // self-invocation: không qua proxy
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void loadData() {
        // query dữ liệu
    }
}
```

Đây là fragment, chưa phải chương trình độc lập. Nếu `generate()` không transactional, `loadData()` gọi nội bộ không nhận hạ tầng `SUPPORTS` từ AOP proxy. Muốn có boundary rõ ràng, đặt annotation trên `generate()` hoặc tách `loadData()` sang bean khác được inject.

Nếu `generate()` đã `@Transactional(REQUIRED)`, lời gọi nội bộ vẫn có thể chạy trong **transaction có sẵn**, nhưng annotation riêng của `loadData()` không tự tạo thêm advice boundary. Cần tránh nhầm hai tình huống.

Chế độ AspectJ weaving có thể intercept self-invocation, nhưng cần `spring-aspects` và bytecode weaving thật; chỉ đổi cấu hình mode không đủ. Với use case thông thường, thiết kế boundary công khai qua Spring-managed beans vẫn đơn giản hơn.

## 9. Ví dụ chạy độc lập: không có T1 thì UPDATE auto-commit, có T1 thì rollback

Ví dụ **Java 17+**, **Spring Framework 6.2.14**, **H2 in-memory 2.3.232**, **Maven 3.9+** minh họa cả hai nhánh của `SUPPORTS`.

Mục tiêu:

1. Gọi `@Transactional(SUPPORTS, readOnly=true)` ngoài transaction; đọc `hasTransaction`, `isNewTransaction`, actual/synchronization flags và read-only metadata.
2. Gọi `@Transactional(SUPPORTS)` ghi một SQL rồi ném `RuntimeException` **ngoài T1**: SQL có thể đã auto-commit, không rollback được.
3. Khôi phục số dư test, sau đó một bean `@Transactional(REQUIRED)` gọi cùng bean SUPPORTS rồi để exception thoát ra: inner **tham gia T1** và update bị rollback.
4. Quan sát stdout để khẳng định **đường đi phụ thuộc caller**, không phụ thuộc việc đổi annotation của SUPPORTS giữa hai lượt.

### 9.1. Cấu trúc dự án

```text
supports-propagation-demo/
├── pom.xml
└── src/main/java/demo/SupportsDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>supports-propagation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
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

`spring-context` cung cấp IoC/Java configuration, `spring-jdbc` cung cấp `JdbcTemplate` và `JdbcTransactionManager`, H2 là JDBC database in-memory. Ví dụ chỉ có **một** transaction manager và **một** datasource để loại bỏ những khác biệt phức tạp của nhiều resource.

### 9.2. Toàn bộ mã Java

File `src/main/java/demo/SupportsDemo.java`:

```java
package demo;

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
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Configuration
@EnableTransactionManagement
public class SupportsDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:supports_demo;DB_CLOSE_DELAY=-1");
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
    SupportsService supportsService(JdbcTemplate jdbc) {
        return new SupportsService(jdbc);
    }

    @Bean
    OuterService outerService(SupportsService supports) {
        return new OuterService(supports);
    }

    public static void main(String[] args) {
        try (var ctx =
                     new AnnotationConfigApplicationContext(SupportsDemo.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            SupportsService supports = ctx.getBean(SupportsService.class);
            OuterService outer = ctx.getBean(OuterService.class);

            supports.inspect("OUTSIDE_SUPPORTS");

            try {
                supports.debitAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("OUTSIDE_FAIL=" + ex.getMessage());
            }

            System.out.println("AFTER_OUTSIDE=" + balance(jdbc));

            // Đưa dữ liệu về 100 để so sánh hai nhánh với cùng input.
            jdbc.update("UPDATE wallet SET balance = 100 WHERE id = 1");

            try {
                outer.callInnerAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("INSIDE_FAIL=" + ex.getMessage());
            }

            System.out.println("AFTER_INSIDE=" + balance(jdbc));
        }
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1",
                Integer.class);
    }

    public static class SupportsService {
        private final JdbcTemplate jdbc;

        public SupportsService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.SUPPORTS,
            readOnly = true
        )
        public void inspect(String label) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println(label
                    + ": hasTx=" + status.hasTransaction()
                    + ", new=" + status.isNewTransaction()
                    + ", actual="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive()
                    + ", sync="
                    + TransactionSynchronizationManager
                            .isSynchronizationActive()
                    + ", readOnly="
                    + TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void debitAndFail() {
            System.out.println("UPDATE: actual="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "UPDATE wallet SET balance = balance - 10 WHERE id = 1");

            throw new IllegalStateException("planned failure");
        }
    }

    public static class OuterService {
        private final SupportsService supports;

        public OuterService(SupportsService supports) {
            this.supports = supports;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void callInnerAndFail() {
            supports.inspect("INSIDE_SUPPORTS");
            supports.debitAndFail();
        }
    }
}
```

**Vì sao có hai class service riêng?** `OuterService` nhận bean `SupportsService` từ Spring container. Do đó `supports.inspect()` và `supports.debitAndFail()` đi **qua proxy của bean inner**, không phải self-invocation trong cùng class. Lúc đó `@Transactional(SUPPORTS)` thực sự được Spring transaction interceptor xử lý.

**Vì sao dùng H2 và `DriverManagerDataSource`?** DriverManagerDataSource không dùng pool, mở JDBC connection với auto-commit mặc định của H2 cho các lời gọi ngoài transaction. `DB_CLOSE_DELAY=-1` giữ database bộ nhớ trong suốt JVM để chương trình có thể đọc lại balance sau mỗi scope. Đây là thí nghiệm, không phải cấu hình production.

### 9.3. Lệnh chạy

Tại thư mục `supports-propagation-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SupportsDemo
```

Các dòng **do ứng dụng tự in** với manager mặc định `SYNCHRONIZATION_ALWAYS` (không tính log Maven/Spring):

```text
OUTSIDE_SUPPORTS: hasTx=false, new=false, actual=false, sync=true, readOnly=true
UPDATE: actual=false
OUTSIDE_FAIL=planned failure
AFTER_OUTSIDE=90
INSIDE_SUPPORTS: hasTx=true, new=false, actual=true, sync=true, readOnly=false
UPDATE: actual=true
INSIDE_FAIL=planned failure
AFTER_INSIDE=100
```

### 9.4. Phân tích kết quả

**Lượt OUTSIDE:**

- Caller chưa mở T1. `inspect()` được advice chặn với `SUPPORTS(readOnly=true)` nhưng không bắt đầu physical transaction.
- `hasTx=false`, `new=false`, `actual=false`; nhờ policy mặc định synchronization-always, `sync=true`. Metadata read-only của scope là `true` dù DB transaction không tồn tại.
- `debitAndFail()` chạy ngoài physical transaction. H2 JDBC connection để auto-commit, nên câu `UPDATE` trừ 10 có hiệu lực dù method ném exception sau đó.
- Caller bắt `IllegalStateException`; số dư đọc lại là 90. Spring không thể rollback một câu SQL đã auto-commit bên ngoài physical transaction.

**Lượt INSIDE:**

- `OuterService.callInnerAndFail()` mở T1 vì `REQUIRED` và caller chưa có transaction.
- `inspect()` với `SUPPORTS` tham gia T1: `hasTx=true`, `new=false` (không tạo T2), `actual=true`, `sync=true`. `readOnly=false` là trạng thái physical transaction ngoài, dù annotation của `inspect()` yêu cầu `readOnly=true`.
- `debitAndFail()` tham gia T1 và thực hiện câu `UPDATE` trên connection do manager điều phối; `actual=true`.
- Exception thoát khỏi `debitAndFail()` và tiếp tục thoát khỏi outer transactional invocation. Manager rollback T1, vì vậy đọc lại thấy số dư vẫn 100.

**Điều không thể suy từ stdout:** không có kiểm thử isolation/timeout, không kiểm tra các trường hợp đa datasource và không bảo đảm mọi JPA provider hành xử hệt JDBC/H2. Ví dụ chỉ chứng minh hai nhánh `SUPPORTS` và vai trò resource transaction.

### 9.5. Thử thay synchronization policy

Trong ví dụ, thay bean `transactionManager` bằng đoạn sau:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
    manager.setTransactionSynchronization(
        org.springframework.transaction.support
            .AbstractPlatformTransactionManager
            .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
    return manager;
}
```

Đây là **đoạn thay thế**, không thêm bean manager thứ hai. Vì chỉ bật synchronization khi có actual transaction, lượt `OUTSIDE_SUPPORTS` sẽ không còn `sync=true` ở scope không có T1. Những điều quan trọng khác vẫn đúng: không có physical transaction thì SQL JDBC ngoài transaction không được rollback nguyên tử; khi inner tham gia T1 thì transaction vật lý của outer điều phối kết cục.

Trong thực tế, nếu code đang dựa vào cùng Session/Connection trong SUPPORTS scope, thay policy có thể đổi vòng đời resource, nên cần integration tests trên chính ứng dụng và backend của bạn.

## 10. Rollback và exception: logic scope khác với kết quả vật lý

Một method `SUPPORTS` có thể ném `RuntimeException`, exception checked hoặc gọi `setRollbackOnly()`. Nhưng **khả năng rollback vật lý** còn phụ thuộc nó có đang tham gia một physical transaction hay không.

| Trường hợp | Kết quả chính |
| --- | --- |
| `SUPPORTS` không có T1, DAO cập nhật qua connection auto-commit | Cập nhật có thể đã commit; exception sau đó không undo bằng Spring transaction |
| `SUPPORTS` tham gia T1, unchecked exception thoát advice | Manager có thể đánh dấu T1 rollback-only hoặc outer rollback tùy đường đi |
| `SUPPORTS` tham gia T1, checked exception thoát advice | Theo rollback rule; mặc định thường không rollback vì checked exception, trừ cấu hình khác |
| `SUPPORTS` tham gia T1, gọi `setRollbackOnly()` | Có thể buộc transaction chung rollback theo manager semantics |
| `SUPPORTS` không có T1, gọi `setRollbackOnly()` | Không có physical transaction để rollback các SQL đã auto-commit |

Một pattern dễ sai:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void updateAndMaybeFail() {
    repository.updateA();
    if (problemDetected()) {
        throw new IllegalStateException("cannot proceed");
    }
    repository.updateB();
}
```

Đây là **fragment minh họa** với repository và `problemDetected()` chưa định nghĩa. Khi caller không có T1, `updateA()` có thể đã commit trước exception. Nếu business contract yêu cầu cả hai thao tác commit cùng nhau hoặc cùng bị rollback, hãy dùng `REQUIRED` ở boundary thực sự.

**Một trường hợp tinh tế:** inner `SUPPORTS` tham gia T1, ném unchecked exception; outer bắt rồi nuốt exception và return bình thường. Inner transaction advice vẫn có thể đã đánh dấu T1 rollback-only. Outer khi cố commit có thể nhận `UnexpectedRollbackException`; việc catch ở outer không chắc làm transaction có thể commit trở lại.

Không dùng `SUPPORTS` như cơ chế che giấu exception hay tránh rollback. Quy tắc rollback thuộc transaction advice và manager; propagation quyết định transaction nào có thể chịu tác động đó.

## 11. Khi `SUPPORTS` bao quanh `REQUIRED` hoặc `REQUIRES_NEW`

Tài liệu Spring cảnh báo việc gọi các scope mạnh hơn bên trong `SUPPORTS` cần lưu ý synchronization.

```text
Caller không có transaction
    |
    +--> SUPPORTS: empty logical scope
           |
           +--> REQUIRED: manager muốn bắt đầu T1
```

Nếu `SUPPORTS` đã kích hoạt synchronization và DAO đã bind Connection hoặc Session, inner `REQUIRED` phải xử lý trạng thái resource/synchronization đang tồn tại. Tùy manager và resource, có thể có ràng buộc hoặc xung đột; **không coi cách lồng này luôn tương đương gọi REQUIRED trực tiếp từ caller không có transaction**.

Các phương án thiết kế tốt hơn:

- Nếu toàn use case cần atomicity: đặt `REQUIRED` trên method **outer** ngay từ đầu.
- Nếu một tầng chỉ thu thập dữ liệu và tùy trường hợp mở transaction, tách rõ giai đoạn phi transactional và transactional ở những bean/public methods khác nhau.
- Nếu phải giữ `SUPPORTS` ngoài, cân nhắc `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` cho manager tương ứng **sau khi** đánh giá tác động resource sharing, rồi test từng đường đi.
- Với `REQUIRES_NEW`, phải xét resource suspension, connection pool và tính độc lập commit/rollback của T2.

Không tự ý gọi `DataSourceUtils.releaseConnection(...)` hoặc `TransactionSynchronizationManager.unbindResource(...)` để chữa xung đột synchronization nếu không hiểu transaction manager đang sở hữu resource; dễ phá cleanup và tính đúng đắn.

### 11.1. Khi caller đã có T1

Nếu caller đã có T1, một outer `SUPPORTS` thường tham gia T1; inner `REQUIRED` cũng có thể tham gia T1, trong khi inner `REQUIRES_NEW` tạo T2. Đây là propagation semantics thông thường. Cảnh báo synchronization-only chủ yếu quan trọng với nhánh **không có physical transaction** nhưng **đã có synchronization scope**.

### 11.2. Nhiều transaction managers

Nếu `SUPPORTS` được advice bởi manager A nhưng inner `REQUIRED` dùng manager B, chúng không phải tự động cùng transaction. Với synchronization theo thread, việc phối hợp nhiều managers cần thiết kế rõ ràng để tránh reuse resource sai hoặc nghĩ rollback A sẽ rollback B. Một local JDBC manager chỉ điều phối các tài nguyên của nó.

## 12. Khi nào nên dùng `SUPPORTS`?

`SUPPORTS` hợp lý khi method **có thể chạy hợp lệ cả bên trong lẫn bên ngoài transaction**.

Ví dụ:

- Một service **đọc** thông tin được dùng bởi cả giao dịch cập nhật đơn hàng và một truy vấn độc lập. Khi caller đã có T1, đọc trong T1; khi caller không có T1, đọc theo chế độ database/resource thông thường.
- Một helper truy xuất metadata không bắt buộc yêu cầu atomicity của nhiều thao tác.
- Một tầng repository/service hỗ trợ caller quyết định transaction boundary, với contract được ghi rõ.
- Một số luồng cần reuse resource/synchronization trong phạm vi xác định, nhưng đã được kiểm chứng theo transaction manager cụ thể.

**Không nên dùng `SUPPORTS`** nếu:

- Method ghi nhiều bảng/hàng và cần rollback cùng nhau bất kể caller.
- Use case yêu cầu mọi lời gọi phải nằm trong transaction (dùng `MANDATORY` để fail-fast khi thiếu T1).
- Method yêu cầu isolation/timeout thực sự ở cả khi gọi độc lập (dùng `REQUIRED` hoặc một boundary mạnh hơn).
- Bạn đang tránh thêm transaction boundary chỉ vì nghĩ `SUPPORTS` “nhẹ” và do đó vẫn an toàn cho write.
- Kết quả đúng phụ thuộc vào caller vô tình đã mở transaction hay chưa mà contract không nêu rõ.

Một nguyên tắc thiết kế: transaction boundary cho **tính nhất quán nghiệp vụ** thường nằm ở application service; các read helpers có thể dùng `SUPPORTS` nếu việc chạy ngoài transaction được chấp nhận. Đừng đẩy trách nhiệm atomicity xuống caller một cách ngầm định.

## 13. Những lỗi phổ biến

### Lỗi 1 — Nghĩ `SUPPORTS` đồng nghĩa `REQUIRED`

`REQUIRED` mở transaction khi chưa có. `SUPPORTS` **không**. Hai annotation có thể giống nhau khi caller đã có T1 nhưng rất khác khi caller không có T1.

### Lỗi 2 — Kiểm tra `isSynchronizationActive()==true` rồi kết luận DB đang transaction

Một empty `SUPPORTS` scope có thể bật synchronization mà không có physical transaction. Kiểm tra thêm `isActualTransactionActive()` và transaction manager/resource, thay vì gộp hai cờ này.

### Lỗi 3 — Tin “cùng JDBC Connection” là “cùng rollback unit”

Synchronization có thể tái sử dụng connection trong scope, nhưng connection ngoài physical transaction có thể để auto-commit. Hai SQL chạy trên cùng connection có thể vẫn commit từng câu. Hãy dùng `REQUIRED` nếu cần atomicity.

### Lỗi 4 — Dùng `@Transactional(SUPPORTS)` cho write quan trọng

Một method chạy ổn khi caller đã có T1 nhưng âm thầm partial commit khi được scheduler hoặc handler gọi độc lập. Đổi sang `REQUIRED` ở boundary nghiệp vụ hoặc dùng `MANDATORY` nếu caller phải sở hữu T1.

### Lỗi 5 — Cho rằng `readOnly=true` luôn cấm ghi

Read-only thường là hint/metadata. Trong nhánh SUPPORTS không có transaction, metadata read-only có thể tồn tại trong Spring synchronization scope nhưng không tạo ra DB permission. Kiểm soát quyền ghi phải dùng policy ở DB/application.

### Lỗi 6 — Dùng `setRollbackOnly()` và tin SQL ngoài transaction được undo

Không có physical transaction thì không có đơn vị rollback tương ứng. Với JDBC auto-commit, SQL đã thành công có thể đã commit trước setter.

### Lỗi 7 — Quên rollback rules trên inner tham gia T1

Inner SUPPORTS có T1 thì exception khớp rule có thể đánh dấu T1 rollback-only. Outer bắt exception không bảo đảm khôi phục khả năng commit.

### Lỗi 8 — Tưởng `SUPPORTS` bắt buộc có transaction

Nó chấp nhận không có transaction. Nếu method phải có T1, dùng `MANDATORY`; nếu method tự chịu trách nhiệm transaction khi gọi độc lập, dùng `REQUIRED`.

### Lỗi 9 — Annotation không được intercept

Trong proxy mode, self-invocation `this.supportsMethod()` không tạo transaction advice cho inner method. Tách bean hoặc đặt annotation đúng public boundary, kiểm tra proxy thực tế.

### Lỗi 10 — Lầm lẫn transaction context với thread khác

Imperative transaction synchronization và JDBC resource binding thường theo thread. `@Async`, executor hoặc `new Thread` không tự chuyển T1 sang thread mới. Một method SUPPORTS chạy ở worker thread có thể thấy `actual=false` dù caller thread đang có T1.

### Lỗi 11 — Cấu hình synchronization khác môi trường nhưng vẫn assert `sync=true`

Một manager có thể dùng `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` hoặc `SYNCHRONIZATION_NEVER`. Kết quả của `isSynchronizationActive()` phải được giải thích theo cấu hình thực tế, không coi nó là bất biến của mọi SUPPORTS scope.

### Lỗi 12 — Lồng `REQUIRED` trong empty SUPPORTS rồi bỏ qua cảnh báo resource sharing

Javadoc `TransactionDefinition.PROPAGATION_SUPPORTS` cảnh báo có thể có synchronization conflicts. Nếu cần cấu trúc đó, hãy kiểm tra manager, connection/session lifecycle và cân nhắc đổi synchronization policy phù hợp.

## 14. Kiểm thử `SUPPORTS` đúng cách

Một bộ kiểm thử đáng tin nên có **hai nhóm caller**:

1. **Không có T1:** gọi bean SUPPORTS từ runner/handler không transactional.
2. **Có T1:** gọi SUPPORTS từ một service khác `@Transactional(REQUIRED)` qua proxy.
3. Đọc **cả** `TransactionStatus.hasTransaction()` và `TransactionSynchronizationManager.isActualTransactionActive()`.
4. Kiểm tra riêng `isSynchronizationActive()` để thấy empty synchronization scope không đồng nghĩa actual transaction.
5. Trong môi trường JDBC test, ghi một thay đổi rồi ném exception, đọc hậu điều kiện **sau boundary** để chứng minh có/không có rollback.
6. Kiểm tra một trường hợp exception bị catch ở outer; phân biệt rollback-only participation với normal return.
7. Thử manager synchronization policy khác trong một test riêng, không thay đổi global production config chỉ để làm số cờ trông đẹp.
8. Kiểm tra resource identity: cùng datasource/manager, đúng pool, JDBC template hoặc ORM integration.
9. Test `SUPPORTS` outer gọi `REQUIRED` inner nếu kiến trúc thực sự có pattern này; quan sát classloader/thread/resource.
10. Nếu dùng Spring Test với test method `@Transactional`, nhớ rằng test framework có thể tự mở T1. Khi đó một method SUPPORTS bạn tưởng đang test “không có transaction” thực tế lại **tham gia T1 của test**.

### 14.1. Test method có `@Transactional` dễ che lỗi

Ví dụ:

```java
@SpringJUnitConfig(AppConfig.class)
@Transactional
class AccountServiceTest {
    @Test
    void checkSupport() {
        service.supportsMethod();
    }
}
```

Đây là **fragment minh họa**, cần Spring Test/JUnit dependencies và các bean thực. Khi test method được Spring test framework bao quanh bởi transaction, method SUPPORTS có thể thấy T1, dẫn đến test pass dù production handler gọi ngoài transaction sẽ có hành vi khác.

Để test nhánh không có T1, cấu hình test không mở test transaction hoặc suspend/điều chỉnh boundary một cách tường minh, rồi kiểm chứng kết quả DB sau khi scope kết thúc.

### 14.2. Logging và quan sát

Trong ứng dụng dùng logging backend thích hợp, bật log ở môi trường development:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Đây là fragment cấu hình logging thường gặp trong Spring Boot, **không phải** phần bắt buộc cho ví dụ `AnnotationConfigApplicationContext` ở trên. Log có thể hỗ trợ xem begin/join, suspension, synchronization và cleanup. Tuy nhiên, log không thay phép kiểm chứng kết quả dữ liệu sau method; không bật TRACE đại trà trong production nếu không có lý do.

## 15. `SUPPORTS` với reactive transaction

Trong mô hình imperative Spring JDBC/JPA, transaction và synchronization thường gắn với **thread**. Với reactive R2DBC, transaction context được truyền qua **Reactor Context**, và cơ chế transaction manager/synchronization API là biến thể reactive, không dựa vào cùng ThreadLocal.

Điều giống nhau về ý tưởng: `SUPPORTS` có transaction thì tham gia; không có thì không bắt đầu transaction mới. Điều **không** được sao chép máy móc: gọi `TransactionSynchronizationManager.isActualTransactionActive()` của imperative API trong một reactive pipeline rồi tin kết quả phản ánh R2DBC transaction.

Trong reactive code, dùng `ReactiveTransactionManager`, `TransactionalOperator`, reactive transaction synchronization và reactive context phù hợp. Vì ví dụ của bài là Java JDBC imperative, các cờ thread-local ở phần 9 chỉ có ý nghĩa trong phạm vi đó.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `@Transactional(SUPPORTS)` được gọi từ controller không transactional. Spring có tự mở transaction JDBC không?

**Đáp án:** Không. `SUPPORTS` chạy không có physical transaction nếu chưa có T1 tương thích. Data-access operations có thể auto-commit tùy resource.

**Câu 2.** `@Transactional(SUPPORTS)` được gọi từ một service `@Transactional(REQUIRED)` đã mở T1. Nó có mở T2 không?

**Đáp án:** Không. Nó tham gia T1; thuộc tính physical transaction của T1 thường chi phối các truy cập resource bên trong.

**Câu 3.** Trong SUPPORTS scope, `isSynchronizationActive()==true` còn `isActualTransactionActive()==false`. Có mâu thuẫn không?

**Đáp án:** Không. Manager có thể bật synchronization cho empty scope theo policy `SYNCHRONIZATION_ALWAYS`, dù không có transaction database thật.

**Câu 4.** Hai câu SQL dùng cùng JDBC Connection trong SUPPORTS không có T1. Nếu câu thứ hai lỗi, câu thứ nhất có chắc rollback không?

**Đáp án:** Không. Nếu connection auto-commit, câu thứ nhất có thể đã commit độc lập. Connection reuse không tạo atomicity.

**Câu 5.** Muốn method chắc chắn có transaction dù caller có hay không, dùng propagation nào?

**Đáp án:** `REQUIRED`: join nếu có, mở mới nếu chưa có. Muốn bắt buộc caller phải mở T1 thì dùng `MANDATORY`.

**Câu 6.** `SUPPORTS` với `readOnly=true` ngoài T1 cho thấy metadata readOnly=true. Có chứng minh DB chặn UPDATE không?

**Đáp án:** Không. Metadata/hint read-only trong Spring không tự bảo đảm database-level enforcement.

**Câu 7.** Inner SUPPORTS tham gia T1 và ném unchecked exception qua advice; outer catch rồi return bình thường. T1 có chắc commit không?

**Đáp án:** Không. Inner advice có thể đã đánh dấu rollback-only; outer commit có thể thất bại với `UnexpectedRollbackException`.

**Câu 8.** Muốn tránh synchronization-only khi SUPPORTS không có T1, có tùy chọn nào?

**Đáp án:** Với manager thuộc họ `AbstractPlatformTransactionManager`, có thể cân nhắc `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`. Việc đổi policy phải đi kèm test resource sharing/lifecycle.

**Câu 9.** `this.supportsMethod()` trong cùng class có tạo SUPPORTS advice scope ở proxy mode không?

**Đáp án:** Không. Self-invocation bỏ qua proxy. Nếu outer đã có transaction thì nội bộ vẫn có thể chạy trong T1, nhưng annotation của inner không tạo một advice boundary mới.

**Câu 10.** `SUPPORTS` giống `NOT_SUPPORTED` khi caller đã có T1?

**Đáp án:** Không. `SUPPORTS` tham gia T1; `NOT_SUPPORTED` suspend T1 và chạy phi transactional.

**Câu 11.** Vì sao Javadoc cảnh báo SUPPORTS bọc REQUIRED/REQUIRES_NEW?

**Đáp án:** Vì empty SUPPORTS có thể kích hoạt synchronization và bind resources, tạo tương tác với inner boundary muốn bắt đầu physical transaction mới. Cần cấu hình/kiểm thử manager phù hợp.

**Câu 12.** Một test `@Transactional` gọi SUPPORTS cho kết quả `actual=true`. Có thể dùng test đó chứng minh SUPPORTS luôn mở transaction không?

**Đáp án:** Không. Test framework đã tạo T1 trước; SUPPORTS chỉ tham gia nó.

## 17. Checklist sử dụng trong codebase

Trước khi chọn `SUPPORTS`, hãy tự trả lời:

- Method phải đảm bảo **atomicity** khi caller không có transaction không? Nếu có, `SUPPORTS` thường không phù hợp.
- Method có được gọi qua Spring-managed bean/proxy hay self-invocation đang bỏ qua advice?
- Caller có T1 với **cùng transaction manager/resource** không?
- `isActualTransactionActive()` và `isSynchronizationActive()` đang phản ánh hai trạng thái gì?
- DAO dùng `JdbcTemplate`/JPA resource tham gia manager hay mở connection ngoài hạ tầng Spring?
- Dựa vào connection reuse hay dựa vào physical transaction? Đây là hai điều khác nhau.
- Với exception, có thể phát sinh partial commit ngoài T1 hoặc rollback-only lan tới outer T1 không?
- `SYNCHRONIZATION_ALWAYS` hay một policy khác đang cấu hình? Có empty synchronization scope không?
- Có nested `REQUIRED`, `REQUIRES_NEW`, nhiều managers, `@Async` hay test-level transaction làm thay đổi bối cảnh không?
- Nếu business logic bắt buộc có T1, có nên dùng `MANDATORY` để fail-fast? Nếu tự cần tạo T1, có nên dùng `REQUIRED`?
- Đã test cả nhánh caller **có** và **không có** transaction trên database thực tế chưa?

**Kết luận một câu:** `SUPPORTS` **tham gia giao dịch hiện hành nếu có, còn nếu không có thì chạy ngoài giao dịch vật lý**, mặc dù Spring vẫn có thể mở **synchronization scope** để quản lý resource. Chỉ physical transaction thật, được manager/resource điều phối đúng, mới tạo ranh giới commit/rollback nguyên tử như kỳ vọng.

## Nguồn tham khảo chính thức

- [Spring Framework 6.2 — `Propagation.SUPPORTS` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/annotation/Propagation.html)
- [Spring Framework 6.2 — `TransactionDefinition.PROPAGATION_SUPPORTS`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/TransactionDefinition.html)
- [Spring Framework 6.2 — `AbstractPlatformTransactionManager` và synchronization policies](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework 6.2 — `TransactionSynchronizationManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)