# Vì sao bắt ngoại lệ ở phương thức ngoài chưa bảo đảm commit

## 1. Trả lời trực tiếp

Trong Spring, khi hai phương thức đều dùng `@Transactional(propagation = Propagation.REQUIRED)` và phương thức **ngoài** gọi phương thức **trong** qua Spring proxy, chúng thường tạo **hai logical transaction scope** nhưng cùng tham gia **một physical transaction**.

Nếu phương thức trong ném một exception khớp rollback rule, transaction interceptor của **phương thức trong** có thể đánh dấu **physical transaction dùng chung** là **rollback-only**. Phương thức ngoài có thể `catch` exception ấy rồi return bình thường, nhưng **`catch` chỉ xử lý điều khiển luồng Java; nó không xóa dấu rollback-only**. Khi interceptor của phương thức ngoài gọi `commit`, transaction manager phát hiện không còn được phép commit và thực hiện rollback. Caller bên ngoài thường nhận `UnexpectedRollbackException`.

```text
Caller
  |
  v
Outer proxy: @Transactional(REQUIRED)
  |  getTransaction(): tạo physical transaction T
  |
  v
Outer method
  |  INSERT "outer"
  |
  +---> Inner proxy: @Transactional(REQUIRED)
  |       |  getTransaction(): tham gia T, không tạo physical transaction khác
  |       v
  |     Inner method
  |       |  INSERT "inner"
  |       |  throw IllegalStateException
  |       v
  |     Inner interceptor: rollback rule khớp
  |       -> đánh dấu T rollback-only
  |       -> ném lại IllegalStateException
  |
  |  catch (IllegalStateException) -> Java exception đã được xử lý
  |  INSERT "after"
  |  return bình thường
  v
Outer interceptor: commit(T)
  |  T đã rollback-only -> ROLLBACK tất cả INSERT của T
  |  throw UnexpectedRollbackException
  v
Caller nhận exception, DB không có "outer", "inner", "after"
```

**Nhớ ba ý:** (1) `REQUIRED` tham gia transaction hiện có; (2) rollback-only là trạng thái transaction, không phải biến exception đang được catch; (3) **method body return** không đồng nghĩa **transaction commit**.

Đây là nội dung của chủ đề **REQUIRED → Vì sao bắt ngoại lệ ở phương thức ngoài chưa bảo đảm commit**. Mục tiêu bài học là biết dự đoán kết quả ở transaction boundary, hiểu khi nào `UnexpectedRollbackException` xảy ra và viết integration test xác minh bằng dữ liệu thực thay vì suy từ log hoặc `catch`.

Ví dụ dùng Java 17+, Spring Boot 3.3.5/Spring Framework 6.1.x, Spring JDBC, H2 và JUnit 5. Phần giải thích về `REQUIRED` phù hợp với mô hình transaction imperative; khác biệt của JPA/JTA, reactive transaction, database và cấu hình manager được ghi rõ nơi cần thiết.

## 2. Hai lớp phạm vi: logical scope và physical transaction

### 2.1. Logical transaction scope là gì?

Mỗi phương thức được Spring transaction interceptor xử lý có một **logical transaction scope** tương ứng với lời gọi transactional đó. Scope có metadata `@Transactional`, một `TransactionStatus` và quyết định rollback/commit ở tầng Spring.

Ví dụ:

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        inner.inner();  // Một bean khác -> qua proxy của inner.
    }
}

@Service
class InnerService {
    @Transactional
    public void inner() {
        // ...
    }
}
```

Đoạn code là minh họa cấu trúc; muốn biên dịch độc lập cần các import Spring và bean/config đầy đủ ở mục 7. Trong proxy mode mặc định, nếu caller gọi `outer()` qua proxy và `inner` là proxy được inject, Spring tạo logical scope ngoài cho `outer()` và logical scope trong cho `inner()`.

### 2.2. Physical transaction là gì?

**Physical transaction** là giao dịch tài nguyên thực sự: ví dụ một JDBC `Connection` với auto-commit tắt được manager điều phối cho đến lúc commit/rollback. Với mặc định `REQUIRED`:

- Chưa có transaction: tạo một physical transaction mới.
- Đã có transaction tương thích: tham gia physical transaction đó.

```text
Logical scope A: Outer @Transactional(REQUIRED) ────────────────┐
  starts physical T                                             │
                                                                ├── T
Logical scope B: Inner @Transactional(REQUIRED) ────────┐      │
  joins same physical T; no independent COMMIT          ┘      │
                                                               │
Outer completion owns final physical COMMIT/ROLLBACK ────────────┘
```

Cả hai scope có thể có rollback rule riêng, nhưng thay đổi của cả hai được lưu/hủy cùng một lần ở T. Một khi T bị đánh dấu rollback-only, outer scope **không thể** làm T commit chỉ bằng cách return bình thường hoặc bắt exception.

### 2.3. `TransactionStatus` cho biết điều gì?

Trong một transactional method được Spring intercept, API:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
boolean createdByThisScope = status.isNewTransaction();
```

Giá trị `isNewTransaction()` thường là `true` ở outer khi nó mở T, và `false` ở inner `REQUIRED` khi tham gia T. Đoạn code trên là snippet giải thích; cần import `TransactionStatus` và `TransactionAspectSupport` trong ứng dụng. `TransactionStatus` là trạng thái logic của lời gọi; **không phải “biên nhận commit”**.

| Lời gọi | Propagation | Có T trước lời gọi? | Physical transaction | `isNewTransaction()` điển hình |
| --- | --- | --- | --- | --- |
| Caller → Outer | `REQUIRED` | Không | T vừa được tạo | `true` |
| Outer → Inner | `REQUIRED` | Có T | Tham gia cùng T | `false` |
| Caller → Inner trực tiếp | `REQUIRED` | Không | Một T mới | `true` |
| Outer → Inner | `REQUIRES_NEW` | Có T | Suspend T, mở T2 độc lập | `true` cho T2 |
| Outer → Inner | `NESTED` | Có T | Thường dùng savepoint trong T (JDBC hỗ trợ) | Không tạo T2 độc lập |

Chi tiết savepoint/suspend phụ thuộc transaction manager. `JpaTransactionManager` và `JtaTransactionManager` không mặc định cung cấp cùng semantics nested savepoint như `DataSourceTransactionManager` cho JDBC.

## 3. Toàn bộ chuỗi sự kiện khi outer bắt exception của inner

Xét tình huống phổ biến:

```java
@Transactional // REQUIRED
public void outer() {
    repository.insert("outer");

    try {
        innerService.inner(); // Bean khác, đi qua proxy
    } catch (IllegalStateException ex) {
        log.warn("Đã xử lý lỗi của bước trong", ex);
    }

    repository.insert("after");
} // return bình thường ở tầng Java
```

Và inner:

```java
@Transactional // REQUIRED
public void inner() {
    repository.insert("inner");
    throw new IllegalStateException("inner failed");
}
```

Hai đoạn code này là **minh họa**; biến `repository`, `innerService` và `log` cần được cung cấp bởi ứng dụng, ví dụ đầy đủ nằm ở mục 7.

### Bước 1 — caller đi qua outer proxy

Spring `TransactionInterceptor` tìm `TransactionAttribute` cho `outer()` rồi gọi `PlatformTransactionManager.getTransaction(...)`. Vì chưa có transaction, manager tạo T, gắn connection/resource vào ngữ cảnh transaction của thread theo cơ chế imperative. Thân `outer()` được gọi khi T đã hoạt động.

### Bước 2 — outer ghi dữ liệu trong T

`repository.insert("outer")` dùng resource tham gia T, ví dụ `JdbcTemplate` với cùng `DataSource`. Statement có thể đã chạy và câu SQL có thể nhìn thấy dữ liệu **trên chính connection của T**, nhưng chưa commit. Nếu đọc từ connection độc lập trước commit, dữ liệu có thể chưa nhìn thấy tùy isolation level.

### Bước 3 — outer gọi inner qua proxy

`innerService` là một Spring bean đã được inject. Lời gọi đi qua proxy của inner. Với `Propagation.REQUIRED`, manager nhận diện T đang hoạt động và trả status của logical scope inner, **không** mở physical transaction T2.

### Bước 4 — inner ném runtime exception

Inner ghi `"inner"` và ném `IllegalStateException`. Với default rollback rules của Spring, runtime exception yêu cầu rollback. Inner transaction interceptor là **nơi nhìn thấy exception trước khi outer catch**. Ở một participating `REQUIRED` scope trong manager thông thường, thao tác `rollback(innerStatus)` không rollback một giao dịch độc lập; nó **đánh dấu T rollback-only**.

### Bước 5 — exception được ném tiếp tới outer body

Inner interceptor chuyển tiếp `IllegalStateException` ra caller ở outer method. Outer `catch` xử lý exception Java. Java sẽ tiếp tục chạy code sau khối `catch` (ví dụ `insert("after")`). Nhưng dấu rollback-only trên T vẫn còn.

### Bước 6 — outer method return

Ở mức code nghiệp vụ, `outer()` có thể return mà không còn exception. Điều đó chỉ nói rằng **thân method kết thúc bình thường**. Outer transaction interceptor còn phải hoàn tất status bằng transaction manager.

### Bước 7 — outer commit bị từ chối

Interceptor outer định `commit(outerStatus)`. Manager kiểm tra T và thấy đã **globally rollback-only**, nên thực hiện rollback thay vì physical commit. Spring ném `UnexpectedRollbackException` để caller không bị báo thành công giả.

### Bước 8 — caller nhận exception sau khi method body đã return

Điểm phát sinh `UnexpectedRollbackException` thường nằm tại **outermost transaction boundary**, tức sau khi `outer()` đã thoát thân method và đang ở logic AOP completion. Vì vậy khối `catch` nằm **bên trong outer method** thường không thể bắt chính exception này. Caller gọi **qua proxy** mới quan sát được.

**Chú ý:** Đây là kết quả của cấu hình tiêu chuẩn `DataSourceTransactionManager`/`JdbcTransactionManager` và rollback rules mặc định. Những tuỳ chọn như `setGlobalRollbackOnParticipationFailure`, `setFailEarlyOnGlobalRollbackOnly`, savepoint hoặc manager khác có thể ảnh hưởng cách đánh dấu rollback-only hoặc thời điểm báo lỗi. Không áp mô hình này máy móc cho mọi transaction implementation.

## 4. Vì sao `catch` không xóa rollback-only?

### 4.1. `catch` và transaction manager lưu hai loại trạng thái khác nhau

```text
Dòng thời gian                                Trạng thái Java   Trạng thái T
--------------------------------------------------------------------------------
Inner throw IllegalStateException             exception         còn hoạt động
Inner interceptor xử lý rollback rule         exception         rollback-only
Outer bắt IllegalStateException               bình thường       rollback-only
Outer return                                  bình thường       rollback-only
Manager cố commit                             bình thường       rollback-only
Manager rollback + ném UnexpectedRollback      exception mới     đã kết thúc
```

`catch` của Java chỉ tiêu thụ object exception và chuyển control flow; Spring không có rule nào mặc định nói rằng “exception đã catch thì transaction hồi phục về trạng thái committable”.

Đánh dấu rollback-only là một **quyết định đã được hạ tầng transaction thực hiện**. Nó có thể do inner interceptor, `TransactionStatus.setRollbackOnly()`, ORM, driver hoặc transaction coordinator tạo ra. Việc “xóa” một dấu như vậy thường không được hỗ trợ bởi transaction manager; cố tiếp tục ghi có thể làm transaction trở nên không hợp lệ hoặc khiến lỗi xuất hiện muộn hơn.

### 4.2. Bắt exception **ở đâu** mới quan trọng

So sánh hai trường hợp:

**Trường hợp A: lỗi được bắt hoàn toàn bên trong outer trước khi transaction interceptor thấy nó.**

```java
@Transactional
public void outerCatchesLocalError() {
    repository.insert("outer");
    try {
        throw new IllegalStateException("handled locally");
    } catch (IllegalStateException expected) {
        // Interceptor bao quanh outer chưa thấy exception này.
    }
    repository.insert("after");
}
```

Nếu chưa có bên nào đánh dấu T rollback-only và resource vẫn khỏe, outer có thể commit. Không phải cứ `catch(RuntimeException)` là bị rollback.

**Trường hợp B: inner là một method có interceptor riêng và dùng cùng T.**

```java
@Transactional
public void outerCatchesInnerError() {
    repository.insert("outer");
    try {
        innerService.writeThenFail();
    } catch (IllegalStateException expected) {
        // Interceptor của inner đã nhìn thấy exception
        // trước khi outer bắt được nó.
    }
    repository.insert("after");
}
```

Nếu inner interceptor yêu cầu rollback, manager đánh dấu T rollback-only. Outer catch không đưa T trở lại trạng thái có thể commit.

Bản chất là **exception đã đi qua transactional boundary nào trước khi được bắt**, chứ không chỉ là exception class hay có `catch` trong source code hay không.

### 4.3. Nếu inner tự catch exception trước khi return thì sao?

```java
@Transactional
public void innerHandlesItsOwnProblem() {
    try {
        throw new IllegalStateException("handled inside inner");
    } catch (IllegalStateException expected) {
        // Không ném exception qua interceptor của inner.
    }
}
```

Nếu không có code khác đánh dấu rollback-only và database/ORM vẫn ở trạng thái hợp lệ, inner interceptor chỉ thấy return bình thường. Outer có thể commit. Nhưng kiểu bắt rồi bỏ qua lỗi có thể làm hỏng hợp đồng nghiệp vụ; **không** dùng nó như cách “né rollback” cho lỗi nghiêm trọng.

### 4.4. Rollback-only có thể xuất hiện dù không có exception nào thoát ra

Inner có thể chủ động gọi:

```java
@Transactional
public void innerSignalsRollback() {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

Đây là API đánh dấu **local status của inner**. Khi inner `REQUIRED` đang tham gia T, xử lý completion của scope inner có thể chuyển tín hiệu này thành rollback-only trên T. Outer vẫn có thể return bình thường nhưng cuối cùng gặp `UnexpectedRollbackException` khi cố commit T.

Ngược lại, **outer tự đặt rollback-only trên chính status chủ sở hữu** rồi return có thể dẫn đến **silent rollback** (không ném `UnexpectedRollbackException` ở caller) khi manager nhận diện local rollback-only như một quyết định rollback có chủ đích. Vì vậy **“caller nhận UnexpectedRollbackException” không phải dấu hiệu bắt buộc của mọi rollback-only**.

## 5. `UnexpectedRollbackException` chính xác thông báo điều gì?

`org.springframework.transaction.UnexpectedRollbackException` là một runtime exception trong họ `TransactionException`. Nó được dùng khi lời gọi định commit nhưng kết quả thực tế phải rollback do trạng thái mà boundary ấy không chủ động quyết định.

Không nên hiểu nó là:

- “Lệnh SQL ở câu cuối cùng chắc chắn lỗi”.
- “Spring đã gọi `rollback` hai lần trên cùng physical transaction”.
- “Outer method ném chính exception này ở dòng `return`”.
- “Catch ngoại lệ ở outer luôn sai”.
- “Mọi transaction manager đều ném nó ở đúng cùng một thời điểm”.
- “Cần thử commit thêm một lần để khôi phục”.

Trong trường hợp điển hình `REQUIRED`, ngoại lệ nói rằng **caller không nên coi lời gọi outer đã commit thành công**. Database transaction của outer đã bị rollback, do một scope tham gia trước đó đánh dấu rollback-only.

### 5.1. Thời điểm ném exception

Với `AbstractPlatformTransactionManager`, mặc định `failEarlyOnGlobalRollbackOnly = false`: trạng thái globally rollback-only thường được báo lỗi ở **outermost transaction boundary**. Nếu bật `setFailEarlyOnGlobalRollbackOnly(true)`, exception có thể được báo sớm hơn khi manager phát hiện dấu global rollback-only ở một inner boundary tiếp theo.

Điểm quan trọng không đổi: **không được commit một physical transaction đã globally rollback-only**. Thay đổi thời điểm báo lỗi không phải phương pháp phục hồi transaction.

### 5.2. `globalRollbackOnParticipationFailure` và vì sao không nên tắt tùy tiện

`AbstractPlatformTransactionManager` có tùy chọn `setGlobalRollbackOnParticipationFailure(boolean)`, mặc định `true`. Khi một **participating transaction** thất bại và interceptor yêu cầu rollback, manager có thể đánh dấu global transaction rollback-only. Tắt tùy chọn này là thay đổi semantics nâng cao và **không đảm bảo** có thể tiếp tục commit sau khi resource/ORM gặp lỗi.

Ví dụ PostgreSQL có thể đặt database transaction vào trạng thái aborted sau một SQL error, và một Hibernate `Session` có thể không còn an toàn để tiếp tục sau một persistence failure. Dù manager không chủ động đánh dấu rollback-only, tài nguyên thực tế vẫn có thể không cho commit. Vì thế không dùng cấu hình này như “mẹo để outer catch được lỗi và commit” nếu chưa hiểu đầy đủ trạng thái database/ORM và chưa có integration test.

### 5.3. Kiểm tra trạng thái “new” và rollback-only

API `TransactionAspectSupport.currentTransactionStatus()` chỉ có ý nghĩa trong ngữ cảnh Spring transactional interceptor đang hoạt động. Gọi ngoài ngữ cảnh ấy có thể ném `NoTransactionException`. Khi ở đúng ngữ cảnh, `isNewTransaction()` giúp phân biệt owner với participant, còn `isRollbackOnly()` có thể giúp xác định status hiện tại đã bị đánh dấu rollback-only.

Không dùng `isRollbackOnly()` như một API có thể “reset” giao dịch. Ngoài ra, tại một số thời điểm, dấu rollback-only có thể nằm trong transaction object/resource toàn cục và chưa thể hiện theo cách bạn kỳ vọng khi chỉ nhìn status khác; kiểm thử behavior ở boundary quan trọng hơn log một biến duy nhất.

## 6. Ma trận tình huống: lúc nào catch vẫn commit, lúc nào không?

Giả sử dùng một `DataSourceTransactionManager` và một database JDBC hỗ trợ transaction. Các method được gọi **qua Spring proxy**, trừ hàng self-invocation.

| Tình huống | Inner scope | Điều xảy ra trước outer catch/return | Outcome thường gặp |
| --- | --- | --- | --- |
| Inner `REQUIRED` ném `RuntimeException` qua proxy | Cùng physical T | Inner interceptor đánh dấu T rollback-only | Outer cố commit → rollback và `UnexpectedRollbackException` |
| Inner `REQUIRED` ném checked `IOException`, default rule truyền thống | Cùng T | Inner interceptor không yêu cầu rollback chỉ vì checked exception | Outer catch → có thể commit T |
| Inner `REQUIRED` ném checked `IOException`, có `rollbackFor=IOException.class` | Cùng T | Inner interceptor đánh dấu T rollback-only | Outer catch vẫn không commit; thường `UnexpectedRollbackException` |
| Inner `REQUIRED` trả về bình thường nhưng gọi `setRollbackOnly()` | Cùng T | Completion inner khiến T rollback-only | Outer return vẫn gặp rollback ở boundary |
| Outer `catch` một `RuntimeException` được ném **trực tiếp trong thân outer** | Chỉ outer scope | Không có interceptor khác đánh dấu rollback-only | Có thể commit T |
| Outer tự `setRollbackOnly()` rồi return | Chỉ owner outer | Outer chủ động quyết định rollback | Thường rollback **không** `UnexpectedRollbackException` |
| Outer gọi inner qua `this.inner()` thay vì proxy | Không có logical inner scope riêng | Inner `@Transactional` không được intercept ở lời gọi nội bộ | Có thể commit nếu outer catch và T chưa rollback-only |
| Inner `REQUIRES_NEW` ném runtime exception | Physical T2 độc lập | T2 rollback, T của outer còn riêng | Outer catch có thể commit T |
| Inner `NESTED` ném runtime exception (JDBC savepoint hỗ trợ) | Savepoint trong T | Rollback về savepoint, T có thể tiếp tục | Outer catch có thể commit phần T còn lại |
| Outer đã ném runtime exception không catch | Owner outer | Outer interceptor yêu cầu rollback | Rollback T, caller thấy exception gốc nếu rollback thành công |

**Điều kiện của “có thể commit”:** không có rollback-only do nguyên nhân khác, manager/resource khỏe, commit thành công và transaction thực sự bao phủ các thao tác. Rule quyết định rollback/commit không tự bảo đảm outcome physical.

### 6.1. Checked exception khác gì trong bài toán này?

Spring theo rollback defaults truyền thống rollback `RuntimeException` và `Error`, **không mặc định rollback checked `Exception`. Trong Spring Framework 6.2, ứng dụng có thể **chủ động** cấu hình `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` để checked exception cũng là rollback theo fallback mới. Thay đổi này cần opt-in, không phải nâng version tự động đổi tất cả default.

Vì vậy, khi phân tích “outer bắt exception của inner”, hãy hỏi **rollback rule thực tế của inner là gì**, chứ không chỉ hỏi exception đã bị outer catch hay chưa. Bài thực hành dùng Boot 3.3.5/Spring 6.1.x, nên mặc định truyền thống được giả định.

### 6.2. Không dùng `noRollbackFor` để “xóa” rollback-only của scope khác

```java
@Transactional(noRollbackFor = IllegalStateException.class)
public void outer() {
    try {
        innerService.writeThenFail();
    } catch (IllegalStateException ignored) {
        // ...
    }
}
```

Đây là snippet minh họa. `noRollbackFor` của outer chỉ quyết định nếu **outer interceptor nhìn thấy** exception phù hợp tại boundary của outer. Nó không xóa marker rollback-only mà inner interceptor đã tạo trước đó. Để thay đổi quyết định ở inner, cần xem contract nghiệp vụ và rollback rule/propagation đúng **ở inner**.

### 6.3. Vì sao repository failure còn nguy hiểm hơn lỗi Java thuần?

Một `DataIntegrityViolationException` do unique constraint, một `OptimisticLockingFailureException` hoặc lỗi flush của ORM có thể khiến tài nguyên transaction bị đặt vào trạng thái không thể tiếp tục hợp lệ. Kể cả outer catch exception, DB hoặc persistence context có thể không phục hồi được. Không dựa vào việc catch exception để thử hàng loạt SQL khác trong cùng transaction rồi mong commit.

Khi cần phục hồi sau một bước thất bại, hãy xác định có thể dùng **savepoint/`NESTED`** đúng công nghệ hay phải tách thành **`REQUIRES_NEW`** (transaction độc lập), hoặc thay đổi thiết kế workflow.

## 7. Dự án thực hành chạy được: kiểm chứng bằng H2 và JUnit

Phần này cung cấp project tối thiểu đầy đủ. Mục tiêu là **tái hiện chính xác** hiện tượng: outer catch một exception Java nhưng caller vẫn nhận `UnexpectedRollbackException` và database không giữ bản ghi nào thuộc T.

Ta cũng kiểm chứng các trường hợp đối chứng: checked exception theo default, explicit `rollbackFor`, explicit rollback-only, `REQUIRES_NEW`, `NESTED` và self-invocation. Những test này không dùng transaction trên chính test method, để tránh che khuất commit/rollback thật của service.

### 7.1. Cấu trúc project

```text
required-rollback-only/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/required/
    │   │   ├── RequiredApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── EventStore.java
    │   │   ├── InnerRequiredService.java
    │   │   ├── IndependentService.java
    │   │   ├── OuterService.java
    │   │   └── SelfInvocationService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/required/
        └── RequiredRollbackIntegrationTest.java
```

Dùng **JDK 17+** và Gradle tương thích với Spring Boot 3.3.5. Nếu tạo dự án bằng Spring Initializr, Gradle Wrapper thường được tạo kèm. Nếu tự tạo file thủ công, cần cài Gradle hoặc tạo wrapper. Do Spring là dependency ngoài JDK, không thể `javac` trực tiếp các class bên dưới khi chưa cung cấp classpath.

`settings.gradle`:

```groovy
rootProject.name = 'required-rollback-only'
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

Chú ý Boot 3.3.5 dùng Spring Framework 6.1.x, nên **không** bật global `ALL_EXCEPTIONS` của Spring 6.2 trong bài này. Ta cần hành vi checked exception mặc định để tạo đối chứng rõ ràng.

### 7.2. Database và transaction manager

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:required_demo;DB_CLOSE_DELAY=-1
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

`src/main/java/com/example/required/RequiredApplication.java`:

```java
package com.example.required;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequiredApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredApplication.class, args);
    }
}
```

`src/main/java/com/example/required/TransactionConfig.java`:

```java
package com.example.required;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        // Mặc định quan trọng của ví dụ:
        // globalRollbackOnParticipationFailure = true
        // failEarlyOnGlobalRollbackOnly = false
        return manager;
    }
}
```

Cấu hình này chọn **một local JDBC transaction manager** duy nhất, thuận tiện quan sát một physical transaction trên H2. `DataSourceTransactionManager` hỗ trợ JDBC savepoints cho `NESTED` nếu driver/database hỗ trợ. Không cần cài thêm `TransactionTemplate` hoặc JTA coordinator.

### 7.3. Repository: lưu và đọc sau transaction

`src/main/java/com/example/required/EventStore.java`:

```java
package com.example.required;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String code) {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
    }

    public List<String> allCodes() {
        return jdbc.queryForList(
                "SELECT code FROM tx_events ORDER BY code", String.class);
    }

    public void deleteAll() {
        jdbc.update("DELETE FROM tx_events");
    }
}
```

Method `allCodes()` không gắn `@Transactional`; khi gọi **sau khi service đã return hoặc ném exception tới test**, nó đọc trạng thái dữ liệu đã hoàn tất của transaction service, thay vì tự quan sát những INSERT chưa commit ở bên trong T. Trong ví dụ H2, mỗi test dọn bảng trước và chạy tuần tự.

### 7.4. Inner REQUIRED: nhiều cách khiến transaction rollback-only

`src/main/java/com/example/required/InnerRequiredService.java`:

```java
package com.example.required;

import java.io.IOException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerRequiredService {
    private final EventStore store;

    public InnerRequiredService(EventStore store) {
        this.store = store;
    }

    @Transactional // REQUIRED theo mặc định
    public void insertThenRuntimeFailure() {
        store.insert("inner");
        throw new IllegalStateException("inner REQUIRED failed");
    }

    @Transactional
    public void insertThenCheckedFailure() throws IOException {
        store.insert("inner");
        throw new IOException("checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void insertThenConfiguredCheckedFailure() throws IOException {
        store.insert("inner");
        throw new IOException("checked failure with rollback rule");
    }

    @Transactional
    public void markRollbackOnly() {
        store.insert("inner");
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }

    @Transactional
    public void insertSuccess() {
        store.insert("inner");
    }

    @Transactional
    public boolean isCurrentScopeNew() {
        return TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();
    }
}
```

**Chú ý về `markRollbackOnly()`:** nó không ném exception. Nhưng khi được gọi từ outer `REQUIRED` qua proxy, inner status là participating status; `setRollbackOnly()` ở inner làm transaction manager đưa dấu rollback-only tới physical transaction dùng chung khi xử lý completion của inner.

**Chú ý về `isCurrentScopeNew()`:** gọi method này trực tiếp từ test qua proxy, khi chưa có transaction, thường trả `true`. Gọi nó **bên trong** outer transaction qua proxy inner thường trả `false`. Hai giá trị cùng đến từ `@Transactional(REQUIRED)` nhưng điều kiện tham gia khác nhau.

### 7.5. Transaction độc lập và savepoint để so sánh

`src/main/java/com/example/required/IndependentService.java`:

```java
package com.example.required;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentService {
    private final EventStore store;

    public IndependentService(EventStore store) {
        this.store = store;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void newTransactionThenFail() {
        store.insert("isolated");
        throw new IllegalStateException("REQUIRES_NEW failed");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedSavepointThenFail() {
        store.insert("nested");
        throw new IllegalStateException("NESTED failed");
    }
}
```

Hai method này cố ý tách khỏi `REQUIRED` để đối chiếu:

- `REQUIRES_NEW`: tạm treo outer T, dùng transaction T2 độc lập. Exception làm T2 rollback; outer T **không tự động** rollback chỉ vì T2 thất bại nếu outer bắt exception. Cần connection khác; connection pool phải đủ.
- `NESTED`: với `DataSourceTransactionManager` và H2 trong ví dụ, tạo savepoint trong T. Inner rollback về savepoint, các thay đổi outer trước savepoint vẫn có thể commit nếu manager/resource cho phép. Nó **không** tạo physical transaction độc lập giống `REQUIRES_NEW`.

Không chuyển mọi inner method sang `REQUIRES_NEW` chỉ để né `UnexpectedRollbackException`: như vậy thay đổi tính nguyên tử và có thể gây lỗi pool starvation khi outer giữ connection và inner cần thêm connection. `NESTED` cần hỗ trợ savepoint; không phải lựa chọn portable cho mọi JPA/JTA manager.

### 7.6. Outer service: điểm chính của bài học

`src/main/java/com/example/required/OuterService.java`:

```java
package com.example.required;

import java.io.IOException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final EventStore store;
    private final InnerRequiredService inner;
    private final IndependentService independent;

    public OuterService(EventStore store,
                        InnerRequiredService inner,
                        IndependentService independent) {
        this.store = store;
        this.inner = inner;
        this.independent = independent;
    }

    @Transactional
    public void catchesInnerRuntime() {
        store.insert("outer");
        try {
            inner.insertThenRuntimeFailure();
        } catch (IllegalStateException expected) {
            // Đã bắt lỗi Java, nhưng inner interceptor đã đánh dấu T rollback-only.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesInnerChecked() {
        store.insert("outer");
        try {
            inner.insertThenCheckedFailure();
        } catch (IOException expected) {
            // Default Spring 6.1: checked IOException không yêu cầu rollback.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesConfiguredChecked() {
        store.insert("outer");
        try {
            inner.insertThenConfiguredCheckedFailure();
        } catch (IOException expected) {
            // rollbackFor ở inner đã đánh dấu T rollback-only.
        }
        store.insert("after");
    }

    @Transactional
    public void innerMarksRollbackOnly() {
        store.insert("outer");
        inner.markRollbackOnly(); // Không ném exception ở đây.
        store.insert("after");
    }

    @Transactional
    public void catchesLocalJavaError() {
        store.insert("outer");
        try {
            throw new IllegalStateException("local Java error");
        } catch (IllegalStateException expected) {
            // Không có inner transactional boundary nào yêu cầu rollback.
        }
        store.insert("after");
    }

    @Transactional
    public void ownerMarksRollbackOnly() {
        store.insert("outer");
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }

    @Transactional
    public void catchesIndependentFailure() {
        store.insert("outer");
        try {
            independent.newTransactionThenFail();
        } catch (IllegalStateException expected) {
            // T2 đã rollback riêng; T outer vẫn có thể commit.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesNestedFailure() {
        store.insert("outer");
        try {
            independent.nestedSavepointThenFail();
        } catch (IllegalStateException expected) {
            // Savepoint rollback; phần còn lại của T vẫn có thể commit.
        }
        store.insert("after");
    }

    @Transactional
    public void allRequiredStepsSucceed() {
        store.insert("outer");
        inner.insertSuccess();
        store.insert("after");
    }

    @Transactional
    public boolean innerJoinedExistingTransaction() {
        return inner.isCurrentScopeNew(); // false: inner tham gia T hiện có.
    }

    @Transactional
    public void uncaughtRuntimeFailure() {
        store.insert("outer");
        throw new IllegalStateException("unhandled outer exception");
    }
}
```

Lưu ý hai method quan trọng nhất:

- `catchesInnerRuntime()` kết thúc **bình thường trong Java**, nhưng outer proxy vẫn phải hoàn tất T. Vì inner đã làm T rollback-only nên caller ngoài proxy nhận `UnexpectedRollbackException`.
- `ownerMarksRollbackOnly()` chủ động gọi `setRollbackOnly()` trên **outer status** rồi return. Manager coi đây là quyết định rollback của owner; caller có thể **không** nhận `UnexpectedRollbackException`. Đừng viết logic chỉ dựa vào việc có hay không có exception.

### 7.7. Self-invocation: cùng object, khác với inner proxy

`src/main/java/com/example/required/SelfInvocationService.java`:

```java
package com.example.required;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SelfInvocationService {
    private final EventStore store;

    public SelfInvocationService(EventStore store) {
        this.store = store;
    }

    @Transactional
    public void outerCallsThisAndCatches() {
        store.insert("outer");
        try {
            this.annotatedInnerThrows();
        } catch (IllegalStateException expected) {
            // this.inner(): không đi qua proxy inner riêng.
        }
        store.insert("after");
    }

    @Transactional
    public void annotatedInnerThrows() {
        store.insert("self-inner");
        throw new IllegalStateException("self invocation failure");
    }
}
```

`outerCallsThisAndCatches()` vẫn có outer transaction vì test gọi nó qua Spring proxy. Nhưng `this.annotatedInnerThrows()` là lời gọi nội bộ trên object đích, **không được transaction interceptor intercept như một scope inner riêng** trong proxy mode mặc định. Exception bị bắt trong outer body, nên dù SQL của inner đã chạy trong outer T, không có inner interceptor đánh dấu T rollback-only. Kết quả đối chứng là **ba hàng có thể được commit**.

Điểm này dễ nhầm: self-invocation không có nghĩa SQL bên trong method inner tự động chạy ngoài outer transaction. Nếu outer transaction đã hoạt động và cùng thread/resource, SQL vẫn tham gia T; chỉ là annotation của inner method không tạo thêm transaction boundary.

### 7.8. Integration test: quan sát sau khi proxy hoàn tất

`src/test/java/com/example/required/RequiredRollbackIntegrationTest.java`:

```java
package com.example.required;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class RequiredRollbackIntegrationTest {
    @Autowired
    private EventStore store;

    @Autowired
    private OuterService outer;

    @Autowired
    private InnerRequiredService inner;

    @Autowired
    private SelfInvocationService self;

    @BeforeEach
    void reset() {
        store.deleteAll();
    }

    @Test
    void catchingInnerRuntimeCannotSaveSharedTransaction() {
        assertThrows(UnexpectedRollbackException.class,
                outer::catchesInnerRuntime);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void catchingCheckedWithoutRollbackRuleCanCommit() {
        outer.catchesInnerChecked();

        assertEquals(List.of("after", "inner", "outer"),
                store.allCodes());
    }

    @Test
    void explicitRollbackForMakesCheckedFailurePoisonSharedTransaction() {
        assertThrows(UnexpectedRollbackException.class,
                outer::catchesConfiguredChecked);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void innerCanMarkRollbackOnlyWithoutThrowing() {
        assertThrows(UnexpectedRollbackException.class,
                outer::innerMarksRollbackOnly);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void catchingOnlyLocalJavaExceptionCanStillCommit() {
        outer.catchesLocalJavaError();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void ownerRollbackOnlyMayRollbackWithoutUnexpectedException() {
        outer.ownerMarksRollbackOnly();

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void requiresNewFailureDoesNotAutomaticallyPoisonOuterTransaction() {
        outer.catchesIndependentFailure();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void nestedSavepointCanPreserveOuterWork() {
        outer.catchesNestedFailure();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void successfulRequiredScopesCommitTogether() {
        outer.allRequiredStepsSucceed();

        assertEquals(List.of("after", "inner", "outer"),
                store.allCodes());
    }

    @Test
    void selfInvocationIsNotAnInnerProxyBoundary() {
        self.outerCallsThisAndCatches();

        assertEquals(List.of("after", "outer", "self-inner"),
                store.allCodes());
    }

    @Test
    void directRequiredCallCreatesANewTransactionScope() {
        assertTrue(inner.isCurrentScopeNew());
        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void innerRequiredJoinsExistingPhysicalTransaction() {
        assertFalse(outer.innerJoinedExistingTransaction());
        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void unhandledOuterRuntimeExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                outer::uncaughtRuntimeFailure);

        assertEquals(List.of(), store.allCodes());
    }
}
```

**Có 13 test độc lập**. Mỗi test:

1. Xóa bảng trước khi bắt đầu.
2. Gọi một Spring-managed service qua proxy.
3. Chờ transaction của service hoàn tất (hoặc exception thoát tới test).
4. Đọc dữ liệu qua `EventStore.allCodes()` để đo kết quả.

**Không** gắn `@Transactional` lên test class hoặc test method này. Nếu test tự mở transaction và rollback ở cuối, `REQUIRED` service có thể tham gia transaction của test; những test “commit” sẽ không còn đo physical commit ở boundary của service.

### 7.9. Chạy project

Ở thư mục có `build.gradle`, nếu đã có Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu dự án tạo thủ công và chưa có wrapper, dùng Gradle đã cài tương thích để tạo wrapper hoặc chạy `gradle test`. Mã phụ thuộc Spring/JUnit/H2; dùng Gradle thay vì `javac` thuần.

**Kết quả kỳ vọng:** 13 JUnit test pass với JDK17+ và môi trường/dependency đúng; không có stdout ổn định theo thứ tự vì JUnit không đảm bảo thứ tự test. Báo cáo kiểm thử nằm tại `build/reports/tests/test/index.html`. Tài liệu không khẳng định bộ test đã chạy trên máy bạn; số hàng và loại exception là **kỳ vọng từ code và Spring JDBC semantics**.

| Test | Caller quan sát | Dữ liệu sau boundary |
| --- | --- | --- |
| Catch inner runtime `REQUIRED` | `UnexpectedRollbackException` | `[]` |
| Catch inner checked (không `rollbackFor`) | Không lỗi ở caller ngoài | `[after, inner, outer]` |
| Catch inner checked có `rollbackFor` | `UnexpectedRollbackException` | `[]` |
| Inner đặt rollback-only thủ công | `UnexpectedRollbackException` | `[]` |
| Catch lỗi Java chỉ trong outer | Return bình thường | `[after, outer]` |
| Outer tự đặt local rollback-only | Có thể return bình thường | `[]` |
| Inner `REQUIRES_NEW` thất bại | Outer return bình thường | `[after, outer]` |
| Inner `NESTED` rollback savepoint | Outer return bình thường | `[after, outer]` |
| Inner `REQUIRED` thành công | Return bình thường | `[after, inner, outer]` |
| Self-invocation được catch | Return bình thường | `[after, outer, self-inner]` |
| Direct inner `REQUIRED` | `isNewTransaction() = true` | `[]` |
| Inner `REQUIRED` tham gia outer | `isNewTransaction() = false` | `[]` |
| Outer runtime exception không catch | `IllegalStateException` | `[]` |

**Một ghi chú về test `REQUIRES_NEW`:** transaction T2 cần một connection độc lập trong khi T outer giữ connection. Dùng pool với ít nhất hai connection khả dụng; production phải tính connection pool theo mức độ lồng nhau. Nếu database chặn thao tác T2 vì lock trên dữ liệu outer vừa ghi, test có thể cần tổ chức data fixture khác. H2 với các key riêng và cấu hình mẫu được chọn để làm giảm khả năng đó.

## 8. Debug `UnexpectedRollbackException` trong ứng dụng thật

### 8.1. Xác định inner transactional boundary trước khi nhìn `catch`

Đừng bắt đầu bằng việc xóa `catch` hoặc đổi exception class. Hãy truy theo:

1. **Caller nào gọi outer qua proxy?** Nếu outer gọi bằng `this.outer()` hoặc object không do Spring quản lý, transaction advice có thể không chạy.
2. **Outer có physical transaction nào?** `REQUIRED` mở mới hay tham gia transaction của một caller lớn hơn?
3. **Inner được gọi qua Spring proxy thật không?** Nếu có, interceptor riêng của inner xử lý exception.
4. **Exception nào thoát qua inner interceptor?** `RuntimeException`, `Error` hay checked exception có `rollbackFor`?
5. **Ai đặt rollback-only?** Inner interceptor, `TransactionStatus.setRollbackOnly()`, ORM/database, hoặc another participating scope?
6. **Có stack trace bắt đầu ở commit của outer không?** `UnexpectedRollbackException` thường xuất hiện khi manager báo rollback ngoài ý muốn.
7. **Database cuối cùng còn gì?** Đọc lại bằng transaction/connection độc lập sau outer boundary để xác minh.
8. **Manager đang dùng là gì?** `DataSourceTransactionManager`, `JpaTransactionManager`, JTA hoặc custom manager có semantics khác nhau.

### 8.2. Bật log có chọn lọc

Trong Spring Boot có thể tạm bật:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.orm.jpa=DEBUG
```

Chỉ bật logger ORM/JPA nếu ứng dụng thật dùng JPA. Tên/log line thay đổi theo phiên bản và manager, vì vậy **đừng** viết test phụ thuộc chuỗi log cố định. Log có thể cho thấy inner scope tham gia transaction hiện có và manager đánh dấu rollback-only, nhưng chỉ quan sát **sau boundary** mới cho biết kết quả dữ liệu.

Đừng log dữ liệu nhạy cảm, credentials hoặc toàn bộ SQL parameters trên production. Với hệ thống bận, DEBUG/TRACE có thể gây chi phí và tạo log rất lớn.

### 8.3. Khi lỗi xuất hiện ở thời điểm commit

Lỗi ở outer boundary không phải lúc nào là `UnexpectedRollbackException`. Nó có thể là lỗi flush JPA, constraint, lock, timeout, mất connection hoặc failure của transaction manager. Khi commit thất bại, dữ liệu có thể có trạng thái **chưa xác định** nếu kết nối bị mất đúng thời điểm database nhận commit.

Với thanh toán, đặt hàng hoặc phát hành hóa đơn, đừng retry mù một transaction chỉ vì caller nhận exception. Sử dụng business key hoặc idempotency key để đối soát trạng thái trước khi thử lại. Một dòng log “commit failed” không tự chứng minh rollback thành công.

## 9. Thiết kế nghiệp vụ khi cần “thử bước phụ và bỏ qua lỗi”

Trong thực tế, outer catch inner không phải lúc nào cũng sai. Sai lầm là **tin rằng catch sẽ phục hồi một physical transaction đã rollback-only**. Có ít nhất bốn cách thiết kế, với semantics khác nhau.

### 9.1. Giữ `REQUIRED` để bảo toàn tính nguyên tử

Nếu outer và inner phải **cùng thành công hoặc cùng thất bại** (ví dụ khấu trừ kho và ghi nhận đơn hàng không được tách), hãy giữ `REQUIRED` và **không cố nuốt lỗi**. Để exception lan tới caller hoặc đổi API trả về một kết quả nghiệp vụ phù hợp sau khi toàn bộ transaction rollback.

```java
@Transactional
public void placeOrder() {
    reserveInventory();
    chargePaymentRecord();
    // Lỗi không phục hồi -> fail toàn bộ.
}
```

Đoạn minh họa giả định các method dùng đúng transaction-bound resources. Không hiểu lời gọi ngoại vi HTTP/payment gateway sẽ tự rollback cùng JDBC transaction.

### 9.2. Dùng `REQUIRES_NEW` cho bước thật sự độc lập

Nếu bước phụ phải độc lập, ví dụ lưu một bản ghi kiểm toán khi thao tác chính thất bại, có thể cân nhắc một bean khác dùng `REQUIRES_NEW`. Nhưng thiết kế này có hệ quả:

- Inner T2 có thể commit dù outer T rollback, hoặc ngược lại.
- Outer giữ tài nguyên trong lúc T2 cần connection khác.
- Một sự kiện audit độc lập không tự bảo đảm tính nhất quán với transaction chính nếu có sự cố hệ thống.
- Với event/message cần tính bền vững, transactional outbox thường phù hợp hơn so với HTTP call trong transaction.

Chỉ dùng khi sự độc lập này đúng yêu cầu nghiệp vụ, và test cả hai nhánh.

### 9.3. Dùng `NESTED` khi cần rollback một phần bằng savepoint

Với JDBC và manager hỗ trợ savepoint, `PROPAGATION_NESTED` cho phép inner rollback phần thay đổi sau savepoint trong **cùng physical transaction**, outer có thể tiếp tục. Nó thích hợp với một số workflow cho phép bỏ một substep nhưng vẫn commit phần đã hợp lệ.

**Giới hạn:** không phải mọi database/transaction manager đều hỗ trợ nested savepoint; Hibernate/JPA context và tác dụng bên ngoài database không tự được “quay về savepoint” theo cùng cách. Phải kiểm thử trên resource thật.

### 9.4. Tránh dùng exception để biểu diễn nhánh bình thường

Nếu inner phát hiện “hết quota mềm” hoặc “không có coupon”, có thể trả một giá trị nghiệp vụ thay vì ném runtime exception khiến transaction interceptor quyết định rollback:

```java
public enum CouponResult {
    APPLIED,
    NOT_ELIGIBLE
}
```

Đây là Java enum độc lập có thể dùng trong service. Ví dụ service có thể trả `CouponResult.NOT_ELIGIBLE` cho một nhánh mong đợi, còn lỗi hạ tầng thật vẫn ném exception. Tuy nhiên không đổi exception thành return value chỉ để “làm Spring commit” trong khi invariant giao dịch đã không còn đúng; phải có tiêu chí nghiệp vụ rõ ràng.

## 10. Những tình huống phản ví dụ cần nhớ

### 10.1. Outer bắt lỗi nhưng inner dùng `noRollbackFor`

```java
@Transactional(noRollbackFor = ValidationWarning.class)
public void inner() {
    throw new ValidationWarning();
}
```

`ValidationWarning` ở đây là runtime exception **giả định** do ứng dụng định nghĩa, snippet chưa độc lập. Nếu rule inner **không yêu cầu rollback** và resource vẫn cho phép tiếp tục, outer catch rồi commit có thể thành công. Từ đó thấy rõ **ngoại lệ được bắt** không phải nguyên nhân duy nhất; **rule rollback thực tế tại boundary đã thấy exception** mới quan trọng.

### 10.2. Inner ném checked exception, nhưng global ALL_EXCEPTIONS đã bật

Trong Spring Framework 6.2+, cấu hình tùy chọn `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` khiến checked exception không có rule đặc biệt cũng mặc định gây rollback. Nếu nâng cấu hình từ default cũ lên mode mới, một outer từng catch checked `IOException` rồi commit có thể chuyển sang `UnexpectedRollbackException`. Không được áp kết luận “checked exception không rollback” bất chấp cấu hình thực tế.

### 10.3. Outer cũng tham gia transaction của caller lớn hơn

Nếu controller → facade `@Transactional` → outer `@Transactional(REQUIRED)` → inner `@Transactional(REQUIRED)`, thì outer không phải owner physical transaction nữa. Nó chỉ là thêm một participating logical scope. Dấu rollback-only có thể được phát hiện và thông báo ở **boundary ngoài cùng của facade**, không nhất thiết ngay khi lời gọi outer return. Do vậy khi debug phải tìm **transaction owner cuối cùng**, không chỉ tên method được gọi là “outer”.

### 10.4. Outer bắt `UnexpectedRollbackException` **sau** lời gọi một inner độc lập

Nếu inner `REQUIRES_NEW` bị rollback-only và tự ném `UnexpectedRollbackException` ở completion của T2, outer có thể catch exception đó **bên trong body** vì T2 đã kết thúc tại inner proxy. Điều này khác với `UnexpectedRollbackException` do **chính outer commit** phát sinh sau khi outer body return: mã `catch` nằm trong body không bắt được completion exception của bản thân nó.

### 10.5. Method return bình thường nhưng outcome vẫn không chắc chắn

Ngay cả khi không có rollback-only, commit có thể thất bại ở hạ tầng. Do đó câu “outer catch xong và return thì chắc chắn commit” sai vì **hai lý do độc lập**:

- Trong `REQUIRED`, T có thể đã rollback-only do inner scope.
- Transaction có thể gặp lỗi ở physical commit dù method body không ném exception.

Đó là lý do caller cần phân biệt **return của method body** với **return bình thường của proxy sau completion**.

## 11. Checklist kiểm chứng một bug ở production

Giả sử application trả `UnexpectedRollbackException` dù log có “Handled inner exception”. Làm theo thứ tự:

1. Xác định **operation ID** để đối chiếu database mà không dựa vào dữ liệu ngẫu nhiên.
2. Xem **stack trace gốc** của inner failure; tìm nơi exception đầu tiên thoát qua transaction interceptor.
3. Xác định outer/inner có phải Spring-managed bean khác nhau và lời gọi đi **qua proxy** hay không.
4. Đọc `@Transactional` của cả hai: `propagation`, `rollbackFor`, `noRollbackFor`, `transactionManager`, isolation, timeout.
5. Kiểm tra transaction manager và database thực tế; có cùng `DataSource`/resource không?
6. Đánh dấu scope nào có `isNewTransaction() = true`; xem inner có tham gia physical T hay không.
7. Kiểm tra dấu **rollback-only** được tạo bởi exception rule, `setRollbackOnly()` hay lỗi tài nguyên.
8. Đọc dữ liệu sau boundary bằng **kết nối độc lập**, sử dụng business key và các invariant nghiệp vụ.
9. Chọn rõ thiết kế: nguyên tử `REQUIRED`, transaction độc lập `REQUIRES_NEW`, JDBC savepoint `NESTED`, hoặc nhánh return-value.
10. Viết regression test cho **cả exception caller quan sát và dữ liệu đã commit/rollback**.
11. Nếu thay đổi propagation hoặc timeout, kiểm tra pool, lock, throughput và failure modes của hệ production-compatible.
12. Với sự cố commit chưa xác định, dừng retry không idempotent và đối soát trước.

### Test nào là bằng chứng mạnh nhất?

Một test chỉ viết:

```java
assertThrows(UnexpectedRollbackException.class, service::run);
```

chưa đủ nếu yêu cầu nghiệp vụ liên quan dữ liệu. Bổ sung:

```java
assertEquals(List.of(), eventStore.allCodes());
```

Khi test được chạy **ngoài transaction test-managed** và đọc từ một transaction/connection độc lập sau service boundary, nó mới xác minh tác động thực. Ngược lại, test chỉ kiểm tra số hàng 0 nhưng không kiểm tra exception có thể bỏ sót việc caller bị báo sai về commit outcome.

## 12. Câu hỏi tự kiểm tra

**1. Outer `REQUIRED` gọi inner `REQUIRED`, inner ném `IllegalStateException`, outer catch và return. Theo default tại sao outer thường gặp `UnexpectedRollbackException`?**

Vì inner interceptor thấy runtime exception và đánh dấu **shared physical transaction** rollback-only. Outer catch không xóa marker; outer commit bị rollback, nên caller được báo rollback ngoài dự kiến.

**2. `isNewTransaction()` của inner `REQUIRED` có luôn là `false` không?**

Không. Khi inner được gọi trực tiếp và không có transaction hiện có, inner có thể tạo T mới và trả `true`. Khi tham gia T đã mở bởi outer, giá trị thường `false`.

**3. Nếu exception chỉ được ném và catch hoàn toàn bên trong outer method, chưa có ai đánh dấu rollback-only thì sao?**

Outer interceptor có thể thấy return bình thường và commit T. `catch` không tự khiến rollback, cũng không tự đảm bảo commit.

**4. Có thể gọi `setRollbackOnly(false)` để khôi phục T không?**

Không. API `TransactionStatus.setRollbackOnly()` đánh dấu rollback-only; không có contract “xóa rollback-only rồi commit” tương ứng. Hãy thay đổi boundary/thiết kế, không cố đảo trạng thái một resource có thể đã lỗi.

**5. Inner `REQUIRES_NEW` rollback, outer `REQUIRED` catch. Outer có chắc commit không?**

Không thể nói “chắc chắn”. Inner T2 rollback độc lập và không mặc định đánh dấu outer T rollback-only, nhưng outer còn có thể gặp lỗi khác hoặc commit thất bại. Nếu T khỏe, outer **có thể** commit.

**6. Inner `NESTED` khác `REQUIRES_NEW` ở đâu?**

`NESTED` thường dùng savepoint trong **cùng** physical T khi JDBC manager hỗ trợ, còn `REQUIRES_NEW` tạo physical T2 độc lập và tạm treo outer T. Chúng khác hẳn semantics và yêu cầu tài nguyên.

**7. Outer gọi `this.inner()`, và cả hai method có `@Transactional`. Vì sao kết quả có thể khác gọi bean inner riêng?**

Self-invocation bỏ qua proxy cho inner method ở proxy mode mặc định. Không có inner transaction advice riêng xử lý exception; nếu exception bị outer catch và T chưa rollback-only, outer có thể commit.

**8. Caller có thể nhận `UnexpectedRollbackException` mặc dù outer method đã return từ body không?**

Có. Exception có thể được ném từ transaction interceptor **sau** khi body return, tại bước hoàn tất transaction. `catch` trong body không thể bắt exception do completion của chính boundary đó ném ra.

**9. Cách xác minh tốt nhất là chỉ đọc log “rollback-only” hay chạy integration test?**

Integration test gọi qua proxy rồi kiểm tra exception **và dữ liệu sau boundary**. Log hỗ trợ tìm nguyên nhân, nhưng không chứng minh chính xác outcome nghiệp vụ.

**10. Điều cần sửa ở nghiệp vụ là loại exception, vị trí `catch` hay transaction boundary?**

Tùy invariant. Trước tiên xác định liệu outer và inner có buộc nguyên tử hay không. Nếu có, giữ `REQUIRED` và để thất bại được báo đúng. Nếu một bước thật sự được phép độc lập, thiết kế `REQUIRES_NEW`/`NESTED` hoặc return-value với kiểm thử tương ứng. Không thay propagation chỉ để che exception.

## Tài liệu chính thức

- [Spring Framework — Transaction Propagation: Understanding PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — `UnexpectedRollbackException` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/UnexpectedRollbackException.html)
- [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — `TransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
