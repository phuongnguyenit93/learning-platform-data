# Vì sao thường chọn TransactionTemplate thay cho mã quản lý thủ công

## 1. Câu trả lời ngắn: giữ quyền quyết định transaction, bớt mã dễ sai

Khi cần điều khiển transaction trực tiếp trong một ứng dụng Spring **imperative**, bạn có ít nhất hai cách:

1. **Tự dùng `PlatformTransactionManager`**: gọi `getTransaction(...)` để nhận `TransactionStatus`, tự chọn chỗ `commit(...)` hoặc `rollback(...)`, xử lý lỗi xảy ra trong business code, trong rollback và ở commit boundary.
2. **Dùng `TransactionTemplate`**: cung cấp một callback mô tả công việc cần được bao trong transaction; template chịu trách nhiệm gọi transaction manager theo lifecycle thích hợp, xử lý rollback với runtime exception/`Error` và thực hiện commit khi callback kết thúc bình thường.

Spring Framework **thường khuyến nghị `TransactionTemplate` cho programmatic transaction management của imperative code**. Với reactive code, Spring khuyến nghị `TransactionalOperator`; ngoài ra, khi toàn bộ service method đã có một unit of work rõ ràng, declarative `@Transactional` thường còn phù hợp hơn cả hai cách programmatic.

Ví dụ hai phong cách tương đương về mục đích “ghi hai bản ghi rồi commit chung”:

**Quản lý thủ công:**

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
TransactionStatus status = manager.getTransaction(definition);

try {
    repository.insertOrder(order);
    repository.insertOrderLines(order);
} catch (RuntimeException | Error failure) {
    manager.rollback(status);
    throw failure;
}

manager.commit(status);
```

Đoạn trên chỉ là **snippet minh họa**: `manager`, `repository`, `order` cần được khai báo. Nó bỏ qua phần bảo toàn original exception nếu `rollback` cũng thất bại, và chưa thể hiện chính sách cho checked exception. Nó cho thấy độ dài và số nhánh control-flow phải tự chịu trách nhiệm.

**Dùng TransactionTemplate:**

```java
TransactionTemplate template = new TransactionTemplate(manager);

template.executeWithoutResult(status -> {
    repository.insertOrder(order);
    repository.insertOrderLines(order);
});
```

Vẫn cần `manager`/`repository`/`order` và được thực thi trong Spring application thực tế. Nhưng transaction code tập trung vào **business unit of work**, không lặp các lệnh acquire/rollback/commit ở mỗi chỗ.

Câu trả lời không phải “TransactionTemplate có transaction an toàn hơn vì một loại transaction mới”. Cả hai có thể dùng **cùng `PlatformTransactionManager`, `DataSource`, propagation, isolation, read-only, timeout** và cuối cùng là cùng cơ chế database transaction. Giá trị của template là **đóng gói đúng một quy trình vốn rất dễ mắc lỗi ở đường exception**, giúp boundary rõ ràng, mã gọn, policy nhất quán và dễ test.

Chủ đề bài này là **API giao dịch trực tiếp → Vì sao thường chọn TransactionTemplate thay cho mã quản lý thủ công**. Ta sẽ đi từ API cấp thấp, so sánh từng bước, phân tích những lỗi phổ biến, thực hành bằng Java 17+/Spring Boot/JDBC/H2, và xác định cả những trường hợp không nên dùng template.

## 2. Ba thành phần gốc của transaction programmatic

### 2.1. `PlatformTransactionManager`

`PlatformTransactionManager` là interface điều phối imperative transactions trong Spring:

```java
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
```

Ba chữ ký trên là **trích hình dạng API để học**, không phải một interface Java mới cần khai báo. Các implementation thường gặp:

- `DataSourceTransactionManager`/`JdbcTransactionManager`: local transaction của một JDBC `DataSource`.
- `JpaTransactionManager`: transaction của một `EntityManagerFactory`, có xử lý JPA resource/lifecycle.
- `JtaTransactionManager`: giao dịch do JTA infrastructure quản lý.
- Custom manager: có thể thêm behavior cho resource riêng.

`getTransaction` không có nghĩa “luôn tạo physical transaction mới”. Với `PROPAGATION_REQUIRED`, nếu transaction tương thích đã tồn tại, manager có thể trả một **participating logical status**. `commit(status)` ở participating scope cũng không nhất thiết commit physical transaction; outer owner mới quyết định completion cuối.

### 2.2. `TransactionDefinition`

`TransactionDefinition` là hợp đồng mô tả propagation, isolation, timeout, read-only và name. `DefaultTransactionDefinition` là một implementation mutable để cấu hình yêu cầu:

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_DEFAULT);
definition.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
definition.setReadOnly(false);
definition.setName("create-order");
```

Các giá trị trong snippet thể hiện default behavior phổ biến. **Name là metadata** phục vụ manager/monitoring; nó không tự bảo đảm đặt tên transaction database ở mọi engine. Timeout/isolation/read-only cũng phụ thuộc manager và resource. Khi tham gia outer transaction, policy physical thường chịu ảnh hưởng outer owner.

### 2.3. `TransactionStatus`

`TransactionStatus` đại diện cho status một **lời gọi transaction manager**:

```java
TransactionStatus status = manager.getTransaction(definition);

boolean isNew = status.isNewTransaction();
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();

status.setRollbackOnly();
```

Snippet dùng các biến đã cấu hình ở trên. `status.setRollbackOnly()` yêu cầu không commit transaction theo semantics manager; nó **không** chạy ngay `rollback` vật lý tại dòng đó trong mọi trường hợp. `isCompleted()` không phải cách khôi phục hoặc tái sử dụng status. Sau `commit`/`rollback`, không được “dùng lại” status để commit lần hai.

### 2.4. `TransactionTemplate` nằm ở đâu?

`TransactionTemplate` là một **execution wrapper** dùng ba khái niệm này, không thay thế manager:

```text
Business service
     |
     +--- TransactionTemplate.execute(callback)
             |
             +--- manager.getTransaction(definition)
             |       -> TransactionStatus
             |
             +--- callback.doInTransaction(status)
             |       -> JDBC / JPA application code
             |
             +--- manager.commit(status) OR manager.rollback(status)
             |       -> manager handles resources and completion
             |
             +--- return value OR propagate failure
```

Template kế thừa `DefaultTransactionDefinition` nên chính instance của template có các setting propagation/isolation/timeout/readOnly/name. Bạn có thể cấu hình một lần trong constructor hoặc dưới dạng Spring bean rồi tái sử dụng.

## 3. Tại sao quản lý thủ công dễ sai?

Một transaction không phải chỉ là “try rồi commit, catch rồi rollback”. Có nhiều đường thoát và nhiều loại lỗi.

### 3.1. Quên rollback khi có RuntimeException

Ví dụ sai:

```java
TransactionStatus status = manager.getTransaction(definition);
repository.insertA();
repository.insertB();    // ném RuntimeException ở đây
manager.commit(status);
```

Nếu business code ném lỗi trước `commit`, thread rời method mà status không được hoàn tất đúng cách. Tùy manager, resource có thể bị giữ/bound tới thread hoặc khiến transaction lifecycle sai lệch. Không dùng mẫu này.

**`TransactionTemplate` tự đi qua rollback path khi callback ném RuntimeException hoặc Error**, trong khi mã application tập trung vào phần cần transaction.

### 3.2. Chỉ catch `Exception` nhưng quên `Error`

Ví dụ không đầy đủ:

```java
try {
    performWork();
} catch (Exception ex) {
    manager.rollback(status);
    throw ex;
}
```

`Error` không kế thừa `Exception`. Template có logic xử lý `RuntimeException | Error` thoát callback để yêu cầu rollback. Ở mã thủ công, catch `Exception` bỏ qua `OutOfMemoryError`, `AssertionError` và các `Error` khác. Dù không phải mọi `Error` đều phục hồi được, bỏ quên đường cleanup/rollback là một lỗ hổng lifecycle.

Không nên viết `catch (Throwable)` rồi tự động nuốt mọi lỗi; nếu phải xử lý `Error`, cần propagate và để infrastructure giữ semantics tương ứng.

### 3.3. Gọi rollback hai lần hoặc gọi rollback sau commit

Một mẫu dễ nhầm:

```java
try {
    doBusinessWork();
    manager.commit(status);
} catch (RuntimeException failure) {
    manager.rollback(status);
    throw failure;
}
```

Đoạn này **không phải mẫu chuẩn**. Nếu `commit(status)` ném exception **sau khi manager đã xử lý/cleanup transaction**, catch có thể tiếp tục gọi `rollback` trên status đã completed, gây một exception thứ hai che mất lỗi thật. Tình trạng “commit threw” không phải bằng chứng transaction chưa commit; outcome có thể không xác định khi connection bị mất đúng thời điểm commit.

Cách ít sai hơn khi tự quản lý là tách rõ **exception từ business body** và **exception từ commit**:

```java
TransactionStatus status = manager.getTransaction(definition);
Result result;

try {
    result = performBusinessWork();
} catch (RuntimeException | Error businessFailure) {
    manager.rollback(status);
    throw businessFailure;
}

// Commit nằm ngoài catch xử lý lỗi business.
manager.commit(status);
return result;
```

Vẫn là snippet minh họa. Nó còn thiếu chính sách checked exceptions và cách bảo toàn original failure nếu rollback cũng lỗi. `TransactionTemplate` đã giải quyết hầu hết boilerplate đó và giúp mọi call site không phải tự lặp lại.

### 3.4. Rollback cũng có thể thất bại

Giả sử business ném `IllegalStateException` nhưng khi rollback, connection bị mất và transaction manager ném `TransactionSystemException`. Thứ nào được propagate? Làm sao giữ ngữ cảnh của business failure?

Trong implementation của `TransactionTemplate`, Spring xử lý rollback failure và có cơ chế ghi nhận original exception đối với `TransactionSystemException`; một rollback failure khác có thể thay thế exception ban đầu nhưng được log. Mã thủ công thường quên điều này.

Nếu tự viết helper, ít nhất cần không để lost context vô ích:

```java
try {
    manager.rollback(status);
} catch (RuntimeException | Error rollbackFailure) {
    if (rollbackFailure != businessFailure) {
        rollbackFailure.addSuppressed(businessFailure);
    }
    throw rollbackFailure;
}
throw businessFailure;
```

Đây là snippet thuộc **nhánh catch của một manual transaction**, không độc lập; cần `businessFailure` và `status` có sẵn. Không phải một bản sao đầy đủ mọi edge case của Spring, chỉ minh họa trách nhiệm bảo toàn exception khi rollback tiếp tục gặp lỗi.

### 3.5. Quên cấu hình và phân biệt logical/physical transaction

Manual code có thể dùng sai `TransactionDefinition`, ví dụ mặc định `REQUIRED` nhưng developer lại tưởng mỗi `getTransaction` tạo transaction riêng. Template không thay đổi thực tế ấy, nhưng khi policy được khai báo một lần tại template instance, khả năng mọi call site dùng cùng cấu hình tăng lên và dễ review hơn.

### 3.6. Viết nhiều phiên bản boilerplate không nhất quán

Một team có 20 service tự viết `getTransaction`/`commit`/`rollback` có thể dẫn tới 20 kiểu exception handling khác nhau:

- Có service catch RuntimeException nhưng không catch Error.
- Có service rollback ở `finally` kể cả khi commit thành công.
- Có service nuốt DataAccessException.
- Có service tự lấy JDBC connection ngoài manager.
- Có service quên xử lý checked exception.
- Có service retry transaction đã completed.
- Có service commit rồi trả kết quả trước khi đảm bảo callback đã hoàn tất.

Dùng template cho các use case cần programmatic transaction tạo một mô hình kiểm soát chung, giảm nguy cơ lỗi copy/paste, giúp business code dễ đọc và kiểm thử.

## 4. Cách TransactionTemplate xử lý callback và lỗi

### 4.1. Return bình thường

```java
String code = template.execute(status -> {
    store.insert("E-01");
    return "E-01";
});
```

Đây là snippet minh họa với `template` và `store` có sẵn. Luồng:

1. Template gọi manager để nhận `TransactionStatus`.
2. Callback chạy và return `"E-01"`.
3. Template gọi completion path `manager.commit(status)`.
4. Nếu manager completion thành công, `execute` trả kết quả tới caller.

**Cảnh báo:** với `PROPAGATION_REQUIRED` đang tham gia outer transaction, `commit(status)` có thể chỉ hoàn tất **logical scope**, physical commit do outer owner thực hiện sau đó. Cũng có trường hợp callback gọi `status.setRollbackOnly()` rồi return bình thường: manager rollback, nhưng `execute` có thể return một value bình thường. Vì vậy value từ callback không đồng nghĩa “DB chắc chắn có dữ liệu” trong mọi hoàn cảnh.

### 4.2. RuntimeException hoặc Error thoát callback

```java
template.executeWithoutResult(status -> {
    store.insert("E-02");
    throw new IllegalStateException("Cannot finish");
});
```

Template sẽ yêu cầu rollback theo manager semantics và propagate exception, trừ khi rollback itself thất bại và phát sinh transaction-system exception tương ứng. `AssertionError` và các `Error` thoát callback cũng được xử lý rollback.

Không nên hiểu “rollback được yêu cầu” đồng nghĩa “rollback chắc chắn thành công trong mọi outage”; cần phân biệt quyết định của Spring và outcome DB.

### 4.3. Checked exception từ `TransactionCallback`

`TransactionCallback<T>.doInTransaction(TransactionStatus)` **không khai báo checked exception**. Java lambda thông thường không được trực tiếp `throw new IOException(...)` từ callback đó. Hai hướng đúng:

**Chuyển sang unchecked, để template rollback và propagate:**

```java
template.executeWithoutResult(status -> {
    store.insert("E-03");
    try {
        readExternalFile();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

**Hoặc bắt checked exception, đánh dấu rollback-only và trả business result:**

```java
Result outcome = template.execute(status -> {
    store.insert("E-03");
    try {
        readExternalFile();
        return Result.success();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return Result.failed("INPUT_UNAVAILABLE");
    }
});
```

Hai đoạn trên chỉ là snippets: `Result`, `store` và `readExternalFile` là API giả định, cần các import Java thích hợp. Nếu nghiệp vụ muốn commit dù gặp checked exception, hãy biểu diễn quyết định đó rõ bằng result/policy; không mặc định “checked exception thì commit” như khi dùng `@Transactional` truyền thống.

Với manual manager, code `Callable<T>.call() throws Exception` có thể cho phép checked exception thật thoát ra. Nhưng khi ấy **người viết manual code phải tự chọn rollback/commit policy** cho từng loại, chứ không có một fallback rollback rule tự vận hành cho `Callable`.

### 4.4. Chủ động rollback mà không ném exception

```java
Decision decision = template.execute(status -> {
    store.insert("draft");
    if (!canAccept()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    return Decision.ACCEPTED;
});
```

Nếu transaction do template sở hữu, `setRollbackOnly` ở status có thể dẫn đến rollback mà `execute` return bình thường, nhất là khi rollback là quyết định có chủ đích của owner. Điều này phù hợp với domain result, nhưng phải rất rõ rằng `Decision.REJECTED` **không** là “đã lưu và commit”.

Nếu template chỉ tham gia outer `REQUIRED`, đánh dấu rollback-only có thể khiến physical transaction của outer sau đó rollback; outer owner có thể nhận `UnexpectedRollbackException`. Dù dùng template, rollback-only **không phải cờ có thể xóa** bằng một catch hoặc return bình thường.

### 4.5. Commit failure phát sinh sau callback

Một điểm code review thường bỏ sót:

```text
caller -> template.execute(...)
          ├── getTransaction()
          ├── callback -> return Result
          ├── manager.commit(status)   <-- vẫn có thể lỗi
          └── execute returns Result   <-- chỉ khi completion path thành công
```

`try/catch` **bên trong callback** không bắt được lỗi phát sinh **sau callback return** ở manager commit. Nếu muốn map lỗi commit thành lỗi API hoặc có cơ chế đối soát, bao `try/catch` quanh **`template.execute(...)` ở caller**. Nhưng không coi mọi exception từ `commit` là bằng chứng database rollback; với một số lỗi mạng/connection, outcome có thể chưa xác định.

## 5. So sánh side-by-side: manual đúng và template tương đương

Giả sử một use case vừa thêm order vừa thêm audit row trong cùng transaction; invariant là **cả hai cùng thành công hoặc cùng rollback**.

### 5.1. Cách thủ công tối thiểu có xử lý RuntimeException/Error

```java
public String createManually(String key) {
    DefaultTransactionDefinition def = new DefaultTransactionDefinition();
    def.setName("create-manual");
    def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

    TransactionStatus status = manager.getTransaction(def);
    String result;
    try {
        store.insertEvent(key);
        store.insertAudit("AUDIT-" + key);
        result = key;
    } catch (RuntimeException | Error businessFailure) {
        manager.rollback(status);
        throw businessFailure;
    }

    manager.commit(status);
    return result;
}
```

Code ở đây là **method minh họa**, cần fields `manager`, `store` và imports. Nếu rollback also fails, exception handling còn cần giữ ngữ cảnh. Nếu muốn cho checked exception, bắt exception phù hợp và khai báo `throws`. Nếu commit fail, cần xử lý ngoài boundary, không rollback status đã completed một cách vô điều kiện.

### 5.2. Cách dùng template

```java
public String createWithTemplate(String key) {
    return template.execute(status -> {
        store.insertEvent(key);
        store.insertAudit("AUDIT-" + key);
        return key;
    });
}
```

Bớt đi transaction boilerplate, giữ các thao tác DB có quan hệ nghiệp vụ trong cùng callback. Nếu cần policy riêng, cấu hình template ở constructor/bean một lần rồi chia sẻ. Nếu có nhiều methods tương tự, lợi ích lũy tích rất rõ.

### 5.3. Bảng trách nhiệm

| Trách nhiệm | Tự dùng manager | TransactionTemplate |
| --- | --- | --- |
| Chọn manager & propagation | Developer | Developer cấu hình template |
| Tạo/get `TransactionStatus` | Gọi trực tiếp mỗi nơi | Template gọi |
| Chạy business code | Tự gọi | Callback |
| Commit khi business return | Tự gọi đúng chỗ | Template gọi |
| Rollback khi runtime exception | Tự catch và gọi | Template xử lý |
| Rollback khi `Error` | Tự nhớ catch thích hợp | Template xử lý |
| Checked exception | Tự chọn policy/catch/rethrow | Callback phải catch/wrap/mark rollback-only |
| Rollback failure handling | Tự xử lý precedence/context | Template có cơ chế chuẩn |
| Completion và cleanup của manager | Tự gọi manager đúng một lần | Template điều phối manager |
| Physical commit khi đang join outer `REQUIRED` | Chờ outer owner | **Vẫn** chờ outer owner |
| Business invariant, SQL locking, idempotency | Developer | **Vẫn** là trách nhiệm developer |

**Một điểm quan trọng:** `TransactionTemplate` không đảm bảo **mọi loại lỗi** hoặc mọi tài nguyên được rollback. Nó chỉ đóng gói thao tác với transaction manager và callback trong context tương ứng; DB semantics, deadlock, network, external I/O, propagation và state của tài nguyên vẫn quan trọng.

## 6. So sánh với `@Transactional`: đừng hiểu sai lời khuyên của Spring

Spring thường khuyến nghị `TransactionTemplate` **khi bạn đã chọn programmatic transaction management**, không phải khẳng định template luôn tốt hơn `@Transactional`.

| Nhu cầu | Phù hợp thường gặp | Lý do |
| --- | --- | --- |
| Một public service method = một atomic unit | `@Transactional` | Ít phụ thuộc API trong body, dễ khai báo |
| Một đoạn DB ngắn giữa file/HTTP work dài | `TransactionTemplate` | Ranh giới callback hiển thị đúng đoạn |
| Nhiều transaction theo chunk, partial success hợp lệ | Template hoặc nhiều service boundary | Chủ động tách từng unit |
| Cần rollback dựa trên result mà không ném exception | Template + `status.setRollbackOnly()` hoặc domain design rõ | Quyết định ngay trong code |
| Cần một transaction mới từ private/helper method | Template hoặc refactor service proxy | Template không lệ thuộc self-invocation |
| Toàn code reactive với Reactor | `TransactionalOperator` | Reactive context/lifecycle khác |
| Rất nhiều business methods dùng cùng policy | `@Transactional` | Hạn chế boilerplate và coupling |
| Kiểm soát cực thấp mức đối với manager | `PlatformTransactionManager` trực tiếp | Chỉ dùng khi abstraction không đáp ứng |

### 6.1. Không có vấn đề self-invocation đối với chính lời gọi template

Trong Spring proxy mode, `this.innerTransactionalMethod()` có thể bypass advice cho annotation ở method inner. Ngược lại:

```java
private void persistOne(String key) {
    template.executeWithoutResult(status -> store.insertEvent(key));
}
```

vẫn chạy template bình thường, dù gọi từ `this.persistOne(...)`. `execute` là Java API được gọi trực tiếp; nó không cần intercept method ngoài. Nhưng chuyện đó không tự làm các annotation `@Transactional` khác chạy khi self-invocation.

### 6.2. Template làm code phụ thuộc Spring nhiều hơn

`TransactionTemplate` là class thuộc `org.springframework.transaction.support`. Inject nó vào mọi domain entity sẽ khiến domain model gắn chặt Spring. Giữ template ở **application service/orchestrator/infrastructure adapter**, nơi định nghĩa unit of work, rồi gọi domain logic thuần Java từ callback. Đó là cách cân bằng lợi ích lifecycle management và kiến trúc dễ test.

## 7. Propagation, timeout, isolation và thread safety

### 7.1. `REQUIRED` vẫn join outer transaction

`TransactionTemplate` mặc định propagation `REQUIRED`. Nếu không có outer transaction, nó thường mở physical transaction mới; nếu có outer, nó tham gia:

```text
outer @Transactional(REQUIRED) opens physical T
  -> template.execute(REQUIRED)
       -> joins T
       -> writes row
       -> template's logical scope returns
  -> outer throws IllegalStateException
  -> physical T rolls back, including row written by template
```

Vì vậy lời khẳng định “gọi `execute` xong thì DB đã commit” **chỉ hợp lý khi template thực sự sở hữu physical transaction và manager đã hoàn tất thành công**. Manual manager với `PROPAGATION_REQUIRED` có giới hạn giống hệt.

### 7.2. `REQUIRES_NEW` cho boundary thật sự độc lập

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

Với manager hỗ trợ, khi outer transaction active, inner `REQUIRES_NEW` suspend outer và mở physical transaction khác. Inner có thể commit ngay cả khi outer rollback, làm thay đổi atomicity nghiệp vụ. Nó có thể cần connection thứ hai, vì outer vẫn giữ connection. Trong hệ thống tải cao, pool thiếu connection có thể dẫn đến starvation.

Đừng chuyển tất cả callbacks sang `REQUIRES_NEW` vì muốn “chắc chắn commit”: chưa chắc business invariant cho phép, và distributed resource hoặc commit failure vẫn tồn tại.

### 7.3. `NESTED` khác `REQUIRES_NEW`

`NESTED` thông thường dùng JDBC savepoint trong cùng physical transaction và rollback về savepoint, khi manager/driver hỗ trợ. `REQUIRES_NEW` tạo physical transaction khác. `JpaTransactionManager` không cung cấp nested JPA persistence-context semantics portable; savepoint không khôi phục managed entities.

Cả `TransactionTemplate` lẫn manual manager API đều dựa vào cùng propagation implementation; template không tự thêm khả năng savepoint cho DB/JPA.

### 7.4. Cấu hình một lần, dùng nhiều lần

`TransactionTemplate` instances có thể được chia sẻ giữa threads khi **không thay đổi cấu hình giữa các calls**. Chúng không lưu conversational state của từng transaction, nhưng lưu các cài đặt mutable như propagation/isolation/timeout.

**Không nên:**

```java
// Sai nếu đây là singleton template đang được nhiều request dùng:
template.setPropagationBehavior(requestWantsNew
        ? TransactionDefinition.PROPAGATION_REQUIRES_NEW
        : TransactionDefinition.PROPAGATION_REQUIRED);
template.executeWithoutResult(status -> doWork());
```

Có race giữa các threads khi chúng mutate cùng instance. Tạo hai templates riêng:

```java
TransactionTemplate required = new TransactionTemplate(manager);

TransactionTemplate newTransaction = new TransactionTemplate(manager);
newTransaction.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

Phần project chạy được sau đây sử dụng cách này.

### 7.5. Read-only, timeout, isolation không phải phép màu

`template.setReadOnly(true)` là hint cho manager/resource và có thể được một số database/driver thực thi, nhưng không phải ACL bảo mật ngăn chắc mọi write. `setTimeout(10)` không phải đồng hồ hủy mọi Java CPU work/HTTP request sau 10 giây. Isolation không tự được đổi trên một transaction đã tồn tại nếu manager không áp dụng transaction characteristic cho participating scope.

Nếu transaction chứa external HTTP call, dùng network timeout riêng; tốt hơn là không giữ JDBC transaction xuyên qua I/O dài khi business không yêu cầu.

## 8. Dự án chạy được Java 17 + Spring Boot 3.3.5 + JDBC/H2

Ta xây một project Spring Boot nhỏ để **so sánh thực tế**, không chỉ đọc pseudocode. Cả manual helper và template dùng **cùng `DataSourceTransactionManager`**; cùng `EventStore`; khác nhau duy nhất ở cách điều phối transaction lifecycle.

Các test quan sát:

- template và manual đều commit khi body thành công;
- template và manual đều rollback khi runtime exception/Error thoát;
- manual helper tự định nghĩa rollback cho checked `IOException`, còn template wrap unchecked;
- template cho phép `status.setRollbackOnly()` không ném exception;
- rollback của transaction trước hoàn tất rồi transaction sau mới bắt đầu;
- `REQUIRES_NEW` có thể commit audit độc lập outer rollback;
- transaction activity chỉ xuất hiện trong callback/low-level action ở fixture không có outer;
- direct call qua helper private vẫn chạy template, không phụ thuộc transactional proxy.

### 8.1. Cây thư mục

```text
transaction-template-vs-manual/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txcompare/
    │   │   ├── TxCompareApplication.java
    │   │   ├── EventStore.java
    │   │   ├── ManualTransactions.java
    │   │   └── ComparisonService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txcompare/
        └── ComparisonServiceIntegrationTest.java
```

Yêu cầu: **JDK 17+**, Gradle tương thích Spring Boot 3.3.5, Maven Central cho lần tải dependency đầu. Nếu tạo project thủ công, cần Gradle hoặc Gradle Wrapper. Project dùng một in-memory H2 DB, không web server.

`settings.gradle`:

```groovy
rootProject.name = 'transaction-template-vs-manual'
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

Dependency management của Spring Boot điều phối Spring JDBC, Spring TX, JUnit và H2 tương thích. Không cần thêm plugin Hibernate/JPA vì bài dùng JDBC để transaction status và thời điểm SQL rõ ràng.

### 8.2. DataSource, schema và Spring Boot bootstrap

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txcompare;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_key VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    audit_key VARCHAR(80) NOT NULL UNIQUE
);
```

Hai bảng tách biệt giúp test `REQUIRES_NEW` không phải UPDATE cùng một row mà outer transaction đang khóa. Không suy ra database external I/O cũng nằm trong JDBC transaction.

`src/main/java/com/example/txcompare/TxCompareApplication.java`:

```java
package com.example.txcompare;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TxCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxCompareApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Chỉ có một `PlatformTransactionManager` cho một datasource. Spring Boot cung cấp `JdbcTemplate` và datasource; manager JDBC bind connection vào transaction context của thread theo imperative transaction semantics.

### 8.3. EventStore: phần SQL không cần biết ai sở hữu transaction

`src/main/java/com/example/txcompare/EventStore.java`:

```java
package com.example.txcompare;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void addEvent(String key) {
        jdbc.update(
                "INSERT INTO events(event_key) VALUES (?)", key);
    }

    public void addAudit(String key) {
        jdbc.update(
                "INSERT INTO audit_events(audit_key) VALUES (?)", key);
    }

    public List<String> events() {
        return jdbc.queryForList(
                "SELECT event_key FROM events ORDER BY event_key",
                String.class);
    }

    public List<String> audits() {
        return jdbc.queryForList(
                "SELECT audit_key FROM audit_events ORDER BY audit_key",
                String.class);
    }

    public void reset() {
        jdbc.update("DELETE FROM audit_events");
        jdbc.update("DELETE FROM events");
    }
}
```

Repository chỉ biết `JdbcTemplate`. Nó tham gia transaction hiện có nhờ cơ chế connection-binding của Spring; không cần chèn `commit`/`rollback` hoặc tự gọi `Connection.setAutoCommit(false)`. Khi test gọi `reset()` ngoài transaction, SQL cleanup diễn ra trên connection phù hợp với autocommit behavior của fixture.

### 8.4. ManualTransactions: mã cấp thấp được viết tương đối cẩn thận

`src/main/java/com/example/txcompare/ManualTransactions.java`:

```java
package com.example.txcompare;

import java.util.concurrent.Callable;

import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

@Component
public class ManualTransactions {
    private final PlatformTransactionManager manager;
    private final DefaultTransactionDefinition definition;

    public ManualTransactions(PlatformTransactionManager manager) {
        this.manager = manager;
        this.definition = new DefaultTransactionDefinition();
        this.definition.setName("manual-unit-of-work");
        this.definition.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
    }

    public <T> T run(Callable<T> action) throws Exception {
        // Có thể ném lỗi tại đây; chưa có status nào cần rollback
        // nếu getTransaction thất bại trước khi trả về.
        TransactionStatus status = manager.getTransaction(definition);
        T result;

        try {
            result = action.call();
        } catch (Exception | Error businessFailure) {
            // Không đặt commit trong try này: nếu commit ném lỗi
            // sau completion, không thử rollback status đã completed.
            try {
                manager.rollback(status);
            } catch (RuntimeException | Error rollbackFailure) {
                // Duy trì ngữ cảnh lỗi gốc nếu rollback cũng thất bại.
                if (rollbackFailure != businessFailure) {
                    rollbackFailure.addSuppressed(businessFailure);
                }
                throw rollbackFailure;
            }
            throw businessFailure;
        }

        manager.commit(status);
        return result;
    }
}
```

Đây là một helper **có thể biên dịch** cho demo, nhưng không nhằm tái tạo toàn bộ capability/edge cases của `TransactionTemplate`. Nó dùng `Callable<T>`, nên cho phép checked `Exception` thoát body và **chủ động rollback cả checked exception**. Đây là **policy do helper quyết định**, khác fallback rollback rule của declarative `@Transactional`.

**Đọc kỹ exception handling:**

- Lỗi ở `getTransaction` không có `TransactionStatus` thành công để application tự rollback.
- Nếu body ném `Exception` hoặc `Error`, helper yêu cầu rollback rồi propagate.
- Nếu rollback cũng lỗi, rollback error được propagate và original failure được attach qua `addSuppressed`.
- `manager.commit(status)` nằm **ngoài catch body**, tránh rollback vô điều kiện sau commit error.
- Helper vẫn không thay thế tất cả logic trong Spring template; mọi custom helper phải được test kỹ trên manager/resource thật.

### 8.5. ComparisonService: cùng công việc, hai cách gọi

`src/main/java/com/example/txcompare/ComparisonService.java`:

```java
package com.example.txcompare;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ComparisonService {
    private final EventStore store;
    private final ManualTransactions manual;
    private final TransactionTemplate required;
    private final TransactionTemplate independent;

    public ComparisonService(
            EventStore store,
            ManualTransactions manual,
            PlatformTransactionManager manager) {

        this.store = store;
        this.manual = manual;

        this.required = new TransactionTemplate(manager);
        this.required.setName("template-required");

        this.independent = new TransactionTemplate(manager);
        this.independent.setName("template-new");
        this.independent.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public record Observation(boolean inside, boolean after) {
    }

    public String templateSuccess(String key) {
        return required.execute(status -> {
            store.addEvent(key);
            return key;
        });
    }

    public String manualSuccess(String key) throws Exception {
        return manual.run(() -> {
            store.addEvent(key);
            return key;
        });
    }

    public void templateRuntimeFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            throw new IllegalStateException("template runtime failure");
        });
    }

    public void manualRuntimeFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new IllegalStateException("manual runtime failure");
        });
    }

    public void templateErrorFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            throw new AssertionError("template error");
        });
    }

    public void manualErrorFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new AssertionError("manual error");
        });
    }

    public void manualCheckedFailure(String key) throws Exception {
        manual.run(() -> {
            store.addEvent(key);
            throw new IOException("checked IO");
        });
    }

    public void templateWrappedCheckedFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
            try {
                checkedOperation();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }

    private static void checkedOperation() throws IOException {
        throw new IOException("checked IO");
    }

    public boolean templateBusinessRejects(String key) {
        return required.execute(status -> {
            store.addEvent(key);
            status.setRollbackOnly();
            return false;
        });
    }

    public void templateSecondTransactionAfterFailure() {
        try {
            required.executeWithoutResult(status -> {
                store.addEvent("should-rollback");
                throw new IllegalStateException("first failed");
            });
        } catch (IllegalStateException expected) {
            // First transaction đã đi qua rollback path.
        }

        required.executeWithoutResult(status -> {
            store.addEvent("second-committed");
        });
    }

    public void templateNewAuditSurvivesOuterRollback() {
        required.executeWithoutResult(outerStatus -> {
            store.addEvent("outer");

            independent.executeWithoutResult(innerStatus -> {
                store.addAudit("inner-audit");
            });

            outerStatus.setRollbackOnly();
        });
    }

    public Observation templateBoundaryVisibility(String key) {
        boolean inside = required.execute(status -> {
            store.addEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });

        boolean after = TransactionSynchronizationManager
                .isActualTransactionActive();

        return new Observation(inside, after);
    }

    public boolean manualBodyHasActiveTransaction(String key)
            throws Exception {
        return manual.run(() -> {
            store.addEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });
    }

    public void directCallToPrivateHelper(String key) {
        privateTemplateHelper(key);
    }

    private void privateTemplateHelper(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
        });
    }

    public void templateThenExternalFailure(String key) {
        required.executeWithoutResult(status -> {
            store.addEvent(key);
        });

        // Lỗi xảy ra SAU khi execute đã hoàn tất scope DB.
        throw new IllegalStateException("external notification failed");
    }

    public void templateInChunks(List<String> keys) {
        for (String key : keys) {
            try {
                required.executeWithoutResult(status -> {
                    store.addEvent(key);
                    if ("reject".equals(key)) {
                        throw new IllegalStateException("rejected chunk");
                    }
                });
            } catch (IllegalStateException expected) {
                // Demo policy partial success. Không nuốt lỗi khác.
            }
        }
    }
}
```

Có bốn điểm cần soi kỹ:

1. `templateSuccess` và `manualSuccess` dùng cùng `EventStore`, cùng `PlatformTransactionManager` và default `REQUIRED`. Khi chạy ngoài outer transaction, cả hai thực hiện một physical transaction mới.
2. `manualCheckedFailure` cho phép `IOException` thoát từ `Callable`; helper tự rollback. `templateWrappedCheckedFailure` chuyển `IOException` thành unchecked để template rollback.
3. `templateBusinessRejects` đánh dấu rollback-only và trả `false`: không được hiểu một normal return là insert đã commit.
4. `templateNewAuditSurvivesOuterRollback` chứng minh `REQUIRES_NEW` khác outer transaction. Audit có thể commit dù outer rollback, một **quyết định kiến trúc phải được business chấp thuận**.

Templates được tạo/cấu hình **một lần trong constructor**, không sửa propagation/read-only theo từng request trên singleton. Helper private vẫn gọi template trực tiếp; không dựa vào proxy intercept method private.

### 8.6. JUnit Integration Test: so sánh cùng kết quả DB

`src/test/java/com/example/txcompare/ComparisonServiceIntegrationTest.java`:

```java
package com.example.txcompare;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ComparisonServiceIntegrationTest {
    @Autowired
    private ComparisonService service;

    @Autowired
    private EventStore store;

    @BeforeEach
    void reset() {
        store.reset();
    }

    @Test
    void templateCommitAndReturnValue() {
        assertEquals("template-ok", service.templateSuccess("template-ok"));
        assertEquals(List.of("template-ok"), store.events());
    }

    @Test
    void manualCommitAndReturnValue() throws Exception {
        assertEquals("manual-ok", service.manualSuccess("manual-ok"));
        assertEquals(List.of("manual-ok"), store.events());
    }

    @Test
    void templateRollsBackRuntimeFailure() {
        assertThrows(IllegalStateException.class,
                () -> service.templateRuntimeFailure("template-failed"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualRollsBackRuntimeFailure() {
        assertThrows(IllegalStateException.class,
                () -> service.manualRuntimeFailure("manual-failed"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollsBackError() {
        assertThrows(AssertionError.class,
                () -> service.templateErrorFailure("template-error"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualHelperRollsBackError() {
        assertThrows(AssertionError.class,
                () -> service.manualErrorFailure("manual-error"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void manualHelperRollsBackCheckedIOExceptionByItsPolicy() {
        assertThrows(IOException.class,
                () -> service.manualCheckedFailure("manual-io"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollsBackWrappedCheckedException() {
        assertThrows(UncheckedIOException.class,
                () -> service.templateWrappedCheckedFailure("template-io"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void templateRollbackOnlyCanReturnNormally() {
        assertFalse(service.templateBusinessRejects("rejected"));
        assertEquals(List.of(), store.events());
    }

    @Test
    void separateTransactionCanCommitAfterEarlierRollback() {
        service.templateSecondTransactionAfterFailure();
        assertEquals(List.of("second-committed"), store.events());
    }

    @Test
    void requiresNewAuditCanSurviveOuterRollback() {
        service.templateNewAuditSurvivesOuterRollback();
        assertEquals(List.of(), store.events());
        assertEquals(List.of("inner-audit"), store.audits());
    }

    @Test
    void transactionIsVisibleInsideTemplateScopeNotAfterIt() {
        var observation = service.templateBoundaryVisibility("observed");
        assertTrue(observation.inside());
        assertFalse(observation.after());
        assertEquals(List.of("observed"), store.events());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void manualTransactionAlsoBindsActiveContext() throws Exception {
        assertTrue(service.manualBodyHasActiveTransaction("manual-visible"));
        assertEquals(List.of("manual-visible"), store.events());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void directPrivateHelperCallStillUsesTemplate() {
        service.directCallToPrivateHelper("private");
        assertEquals(List.of("private"), store.events());
    }

    @Test
    void externalFailureAfterTemplateCompletionDoesNotUndoCommit() {
        assertThrows(IllegalStateException.class,
                () -> service.templateThenExternalFailure("committed"));
        assertEquals(List.of("committed"), store.events());
    }

    @Test
    void failedChunkDoesNotUndoEarlierAndLaterCommittedChunks() {
        service.templateInChunks(
                List.of("first", "reject", "third"));
        assertEquals(List.of("first", "third"), store.events());
    }
}
```

**Có 16 integration tests**, bao gồm commit, runtime rollback, Error rollback, checked exception policy, explicit rollback-only, multiple independent scopes, `REQUIRES_NEW`, scope activity, private method call, external failure sau commit và chunk partial success.

**Tại sao không gắn `@Transactional` vào test class?** Nếu test tự mở transaction, cả manual helper và template `REQUIRED` có thể **join** transaction của test; SQL nhìn thấy trong test chưa chứng minh service đã physical commit. Ở đây tests chạy ngoài test-managed transaction: chúng gọi service, để transaction scope completion xảy ra, rồi đọc DB từ repository.

### 8.7. Chạy test và hiểu kết quả

Với Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu tự tạo project chưa có wrapper, cài Gradle phiên bản tương thích, chạy `gradle test` hoặc tạo Gradle Wrapper trước. Không chạy `javac` thuần cho Spring code vì cần classpath Spring/JUnit/H2.

**Kết quả kỳ vọng:** 16 tests pass khi dependencies/môi trường đúng với fixture. Đây là kỳ vọng của code và Spring JDBC transaction semantics; **không phải tuyên bố bộ test đã được thực thi trong lượt soạn bài này**. JUnit không đảm bảo thứ tự test hoặc stdout cố định. Báo cáo được tạo khi chạy thật: `build/reports/tests/test/index.html`.

| Kịch bản | Caller / kết quả | DB sau boundary |
| --- | --- | --- |
| Template commit | Return `template-ok` | Một event `template-ok` |
| Manual commit | Return `manual-ok` | Một event `manual-ok` |
| Template RuntimeException | `IllegalStateException` | Event trống |
| Manual RuntimeException | `IllegalStateException` | Event trống |
| Template Error | `AssertionError` | Event trống |
| Manual Error | `AssertionError` | Event trống |
| Manual checked exception | `IOException` | Event trống |
| Template wrapped checked | `UncheckedIOException` | Event trống |
| Template `setRollbackOnly` | Return `false` | Event trống |
| Callback 1 fail, callback 2 success | Return bình thường | Chỉ `second-committed` |
| `REQUIRES_NEW` audit trong outer rollback | Return bình thường | Events trống; audit `inner-audit` |
| Template scope activity | `true` bên trong, `false` sau | Event `observed` |
| Manual scope activity | `true` trong action | Event `manual-visible` |
| Private helper calls template | Return bình thường | Event `private` |
| External failure sau execute | `IllegalStateException` | Event `committed` **vẫn còn** |
| Chunk giữa fail | Return theo demo policy | Events `first`, `third` |

**Không suy luận từ một exception duy nhất rằng DB đã rollback thành công.** Test kiểm tra cả exception/trạng thái transaction và dữ liệu thực sau boundary. Nếu dùng JPA, flush/commit timing có thể khác JDBC; nếu dùng DB production, phải kiểm chứng trên chính driver/isolation/locking của hệ đó.

## 9. Khi nào quản lý thủ công bằng PlatformTransactionManager vẫn hợp lý?

TransactionTemplate **thường** tốt hơn nếu công việc có hình dạng `execute callback` bình thường. Nhưng API cấp thấp có chỗ đứng, nhất là khi viết infrastructure code:

### 9.1. Đang tạo một transaction abstraction đặc thù

Một framework nội bộ có thể cần tương tác trực tiếp với `getTransaction`/`commit`/`rollback`, quản lý nhiều phases, hoặc phối hợp trạng thái lifecycle không thể biểu diễn gọn bằng một callback. Khi ấy biết chính xác owner/status và error precedence là bắt buộc. Tuy nhiên, đây thường là **infra code có test kỹ**, không phải logic service thường ngày.

### 9.2. Muốn kiểm soát chính sách checked exception ngoài callback

Một API nhận `Callable<T>` khai báo `throws Exception` có thể chọn rollback cho checked exception rồi ném lại cùng exception type, như `ManualTransactions` trong demo. Template callback không thể ném checked exception trực tiếp qua chữ ký Java thông thường. Nhưng trước khi tự xây helper phức tạp, cân nhắc `@Transactional(rollbackFor=...)` hoặc thiết kế adapter chuyển checked exception sang domain outcome/unchecked wrapper.

### 9.3. Code có transaction lifecycle cố ý dài hơn một callback

Có nơi transaction được bắt đầu ở một bước và kết thúc ở bước khác trong cùng request/thread. API manager trực tiếp có thể biểu diễn điều này, nhưng **rất dễ để resource bị giữ quá lâu, lệch thread hoặc leak**. TransactionStatus của imperative manager thường gắn với thread/resources; không được truyền tùy ý giữa executors/`@Async`/HTTP requests. Chỉ dùng khi không còn abstraction an toàn hơn và có test cho cancel, timeout, errors và cleanup.

### 9.4. Viết test cho transaction manager custom

Nếu mục tiêu là kiểm thử trực tiếp một implementation của `PlatformTransactionManager`, đương nhiên cần dùng API trực tiếp. Đó là kiểm thử infrastructure, khác với business service chỉ muốn một unit of work nguyên tử.

**Đánh đổi:** mã thủ công mang lại quyền kiểm soát nhưng gia tăng nghĩa vụ xử lý lỗi, không làm tài nguyên/DB magically hỗ trợ tính năng mà nó không có.

## 10. Các giới hạn của TransactionTemplate cũng cần hiểu

### 10.1. Không tự giải quyết concurrency invariant

`TransactionTemplate` bọc database transaction nhưng không tự ngăn duplicate booking, lost update hoặc vượt quota nếu SQL/schema không bảo vệ. Cần `UNIQUE`, `CHECK`, locking, optimistic locking `@Version` hoặc atomic guarded UPDATE phù hợp.

### 10.2. Không rollback HTTP, email, object storage

Một email đã gửi không thể được JDBC transaction manager thu hồi chỉ vì callback ném exception. Không đặt network I/O chậm trong callback nếu không cần. Nếu cần DB event đồng bộ với message delivery, cân nhắc transactional outbox và idempotent dispatcher.

### 10.3. Không đảm bảo mọi commit error nghĩa là rollback

Sau lỗi commit do network hoặc connection failure, outcome có thể không chắc chắn. Không tự retry một payment/booking operation nếu thiếu idempotency key hoặc cơ chế đối soát.

### 10.4. Không tự mang transaction sang thread khác

Imperative Spring transaction thường liên quan thread-bound resources qua `TransactionSynchronizationManager`. Nếu trong callback spawn một `CompletableFuture` hoặc `@Async` task, task đó không tự tham gia transaction của thread caller. Dùng transaction boundary riêng, queue/workflow hoặc reactive infrastructure phù hợp.

### 10.5. Không đồng nghĩa reactive transaction

Với R2DBC/Reactor, dùng `ReactiveTransactionManager` và `TransactionalOperator` để bao publisher lifecycle/reactor context, không dùng imperative `TransactionTemplate` để tưởng đang giữ transaction mở cho toàn bộ `Mono`/`Flux`.

### 10.6. Không sửa một transaction đã rollback-only

Nếu inner `REQUIRED` participant đánh dấu shared transaction rollback-only, outer catch rồi `template.execute` return không tự reset marker. Khi physical owner cố commit, có thể gặp `UnexpectedRollbackException`. TransactionTemplate giảm boilerplate, không vô hiệu propagation/rollback-only semantics.

## 11. Code review checklist: chọn template hay manual?

Khi review một PR có `getTransaction`/`commit`/`rollback` trong business service, hãy hỏi:

1. Unit of work là gì? Những statements nào **phải cùng commit hoặc cùng rollback**?
2. Boundary có thể đặt bằng `@Transactional` trên service method qua Spring proxy không?
3. Nếu cần programmatic, business body có đúng hình dạng một callback không? Nếu có, sao không dùng `TransactionTemplate`?
4. Manager được inject có đúng với datasource/entity manager đang dùng không?
5. `PROPAGATION_REQUIRED` có join outer transaction đang mở không? Người viết có nhầm “scope xong” với “physical commit xong”?
6. Có transaction definition name/isolation/timeout/readOnly cần cấu hình? Có mutate template shared per request không?
7. Checked exception nào cần rollback? Có policy cụ thể thay vì dựa trên một assumption từ `@Transactional` không?
8. Có catch `Error`/runtime exception và rollback đúng trước khi propagate không?
9. Nếu rollback failure thì original business exception có được bảo toàn dưới dạng cause/suppressed/log không?
10. `commit` có nằm trong catch rồi bị rollback thêm lần khi commit error không?
11. Có reuse `TransactionStatus` sau completion hoặc cố rollback 2 lần không?
12. Nếu transaction chưa có status vì `getTransaction` fail, code xử lý ra sao?
13. Có outer/inner transaction với `REQUIRES_NEW`, connection pool, lock contention không?
14. Có tác dụng bên ngoài database mà callback không thể rollback không?
15. Test có đọc DB **sau transaction boundary** và tránh test-managed transaction khi cần chứng minh commit không?
16. Có integration tests cho success, runtime failure, checked policy, Error, rollback-only, commit failure quan trọng và rollback failure (nếu thật sự viết helper custom) không?
17. Có idempotency/retry plan khi commit outcome chưa rõ?
18. Template có được dùng ở orchestration/application layer, không làm domain model phụ thuộc Spring API không?

Với đa số business services, càng nhiều câu hỏi phải tự xử lý trong manual code thì **lợi ích tránh boilerplate của `TransactionTemplate` càng rõ**.

## 12. Những ngộ nhận thường gặp

**Ngộ nhận 1: “TransactionTemplate khác PlatformTransactionManager về khả năng atomicity.”**  
Sai. Template gọi manager tương ứng; hiệu lực atomicity đến từ transaction manager và tài nguyên tham gia.

**Ngộ nhận 2: “Mã thủ công mới thật sự kiểm soát commit.”**  
Sai. Template cũng cấu hình propagation/isolation/timeout và status; chỉ ủy quyền lifecycle boilerplate cho Spring.

**Ngộ nhận 3: “Có template thì không cần biết propagation.”**  
Sai. `REQUIRED` có thể join outer; `REQUIRES_NEW` là transaction độc lập; `NESTED` là savepoint khi hỗ trợ.

**Ngộ nhận 4: “Callback return nghĩa là dữ liệu đã commit.”**  
Sai. Manager còn completion; nếu join outer thì physical commit muộn, nếu rollback-only có thể rollback.

**Ngộ nhận 5: “Template rollback mọi checked Exception như @Transactional có rollbackFor.”**  
Sai về Java API: callback signature không khai báo checked exception. Cần catch/wrap/mark rollback-only, hoặc chọn declarative policy phù hợp.

**Ngộ nhận 6: “Manual getTransaction luôn tạo transaction mới.”**  
Sai. Nó phụ thuộc `TransactionDefinition` và transaction hiện có giống template.

**Ngộ nhận 7: “Bắt RuntimeException trong callback rồi return bình thường vẫn mặc định rollback.”**  
Không mặc nhiên. Nếu interceptor/template chỉ thấy return bình thường và status/resource chưa rollback-only, manager có thể commit. Muốn rollback phải propagate exception hoặc `setRollbackOnly`.

**Ngộ nhận 8: “Đặt rollback ở finally là an toàn nhất.”**  
Sai nếu finally luôn rollback cả khi commit/rollback đã completed; có thể gây double completion và che lỗi.

**Ngộ nhận 9: “Chỉ cần catch Exception.”**  
Không bao gồm `Error`. Template có xử lý rollback cho `Error` thoát callback.

**Ngộ nhận 10: “Rollback exception không cần lưu business failure.”**  
Sai với observability. Khi rollback cũng lỗi, cần giữ context của application failure để tìm nguyên nhân.

**Ngộ nhận 11: “Template tự quản lý mọi tài nguyên bên ngoài.”**  
Sai. Email, HTTP, message và file system không tự được transaction manager JDBC rollback.

**Ngộ nhận 12: “Tạo singleton template rồi chỉnh propagation mỗi call là tốt.”**  
Không an toàn khi cấu hình mutable bị chia sẻ giữa threads. Tạo nhiều template instances theo policy.

**Ngộ nhận 13: “Dùng template ở private method không có transaction.”**  
Sai. Lời gọi `execute` trực tiếp không cần Spring AOP proxy cho method bao quanh, nhưng vẫn cần manager/resource phù hợp.

**Ngộ nhận 14: “Manual manager luôn tốt hơn vì linh hoạt.”**  
Nó có thể cần thiết ở infrastructure code, nhưng linh hoạt đi kèm nhiều nhánh lỗi phải tự kiểm thử; với standard callback flow, template thường giảm nguy cơ.

**Ngộ nhận 15: “Có exception trả tới caller thì DB chắc chắn rollback.”**  
Sai với commit outcome không xác định hoặc exception **sau** transaction hoàn tất (ví dụ external notification fail).

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao Spring thường khuyến nghị `TransactionTemplate` cho imperative programmatic transaction management?  
**Đáp án:** Nó dùng callback để đóng gói việc lấy status, commit/rollback, xử lý exception và completion path; developer tập trung vào unit of work, giảm boilerplate và lỗi ở failure paths.

**Câu 2.** Template có tạo một “transaction engine” khác với `PlatformTransactionManager` không?  
**Đáp án:** Không. Nó dùng chính manager được cung cấp và cùng propagation/resource semantics.

**Câu 3.** Vì sao đoạn manual `try { work(); commit(); } catch(RuntimeException e) { rollback(); }` nguy hiểm?  
**Đáp án:** `commit` có thể ném lỗi sau khi status completed; catch cố rollback lần nữa và che lỗi. Cần tách exception từ work khỏi completion hoặc để template quản lý.

**Câu 4.** Nếu body ném `AssertionError`, catch `Exception` có chạy không?  
**Đáp án:** Không. `Error` không kế thừa `Exception`. Template có nhánh rollback khi `RuntimeException` hoặc `Error` thoát callback.

**Câu 5.** Có thể trực tiếp throw checked `IOException` từ `TransactionCallback` lambda không?  
**Đáp án:** Không theo signature Java bình thường. Cần catch/wrap thành unchecked, trả business result và đánh dấu rollback-only, hoặc dùng API/declarative khác phù hợp.

**Câu 6.** Manual manager có thể chọn rollback cho checked exception không?  
**Đáp án:** Có. Application tự đặt policy trong catch, như helper `ManualTransactions` nhận `Callable<T>` và rollback khi `Exception` thoát. Đây là một quyết định application, không phải default cố định của manager.

**Câu 7.** `status.setRollbackOnly()` luôn ném exception ra caller không?  
**Đáp án:** Không. Khi owner transaction chủ động rollback, template có thể return bình thường. Nếu chỉ tham gia outer transaction, marker có thể khiến outer owner gặp `UnexpectedRollbackException` về sau.

**Câu 8.** `template.execute` return bình thường có nghĩa physical transaction đã commit không?  
**Đáp án:** Chỉ khi template thực sự sở hữu physical transaction và manager hoàn tất commit thành công; `REQUIRED` có thể tham gia outer transaction nên chưa physical commit.

**Câu 9.** Vì sao không để một singleton template thay isolation/propagation trước mỗi request?  
**Đáp án:** Instance lưu cấu hình mutable, nhiều threads có thể race. Dùng các instances cấu hình riêng một lần.

**Câu 10.** Nếu cần atomicity giữa DB insert và gửi email, TransactionTemplate có đủ không?  
**Đáp án:** Không. Email không tự rollback theo JDBC manager. Dùng transactional outbox/dispatcher idempotent hoặc thiết kế khác phù hợp.

**Câu 11.** Vì sao test trong ví dụ không dùng `@Transactional` trên test class?  
**Đáp án:** Test-managed transaction có thể khiến callback `REQUIRED` tham gia transaction của test và chưa commit physical tại boundary đang kiểm tra. Cần đọc DB sau completion.

**Câu 12.** Nếu cần rollback một phần trong cùng JDBC transaction, `REQUIRES_NEW` có giống `NESTED` không?  
**Đáp án:** Không. `NESTED` thường dùng savepoint; `REQUIRES_NEW` mở transaction vật lý độc lập. Cả hai cần manager/resource hỗ trợ và có semantics khác.

**Câu 13.** Trường hợp nào manual manager API vẫn đáng cân nhắc?  
**Đáp án:** Infrastructure code cần điều khiển lifecycle rất đặc biệt hoặc transaction manager custom tests, khi callback abstraction không đáp ứng và team có năng lực test đầy đủ begin/commit/rollback/failure.

**Câu 14.** Có thể test cách template xử lý rollback error bằng cách chỉ assert event count không?  
**Đáp án:** Không. Muốn kiểm tra error precedence và exception preservation, cần test giả lập/điều khiển manager failure path. Integration test H2 bình thường xác minh business rollback, không tự bao phủ connection-outage/rollback-exception edge cases.

**Câu 15.** Với một service method thuần database có boundary rõ, nên dùng template hay `@Transactional`?  
**Đáp án:** Thường ưu tiên `@Transactional` để giữ code nghiệp vụ gọn và ít coupling. Lời khuyên dùng template áp dụng khi đã quyết định cần programmatic transaction control.

## 14. Nguồn tham khảo chính thức

- [Spring Framework — Programmatic Transaction Management: TransactionTemplate vs PlatformTransactionManager](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionCallback Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionCallback.html)
- [Spring Framework — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html)
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html)
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html)
- [Spring Framework — Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
