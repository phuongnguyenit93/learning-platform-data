# Không hoàn tất hai lần cùng một TransactionStatus

> **Module:** Spring Framework — Transaction Management. **Nhóm:** API giao dịch trực tiếp. **Trọng tâm:** vòng đời `TransactionStatus` trong API imperative `PlatformTransactionManager`. Mỗi status được `getTransaction(...)` trả về chỉ được đưa qua **một đường kết thúc** — `commit(status)` **hoặc** `rollback(status)`. Không “commit rồi rollback để chắc chắn”, không rollback thêm khi commit ném lỗi, và không tái sử dụng status đã completed cho transaction khác. Bài gồm quy tắc, state diagram, các bẫy exception, status tham gia transaction ngoài, savepoint, `TransactionTemplate` và dự án Java 17/Spring Boot/H2 chạy được.

## 1. Nguyên tắc quan trọng nhất

Với transaction management imperative của Spring:

```java
TransactionStatus status = transactionManager.getTransaction(definition);

try {
    doBusinessWork();
} catch (RuntimeException | Error error) {
    transactionManager.rollback(status);
    throw error;
}

transactionManager.commit(status);
```

Đây là **mẫu trích đoạn**, giả định `transactionManager` là `PlatformTransactionManager`, `definition` là `TransactionDefinition`, còn `doBusinessWork()` là nghiệp vụ đồng bộ. Nó đặt **`commit` ngoài khối `try` chỉ bao công việc nghiệp vụ**, tránh bắt lỗi do chính `commit` ném và gọi tiếp `rollback` trên cùng status.

**Một `TransactionStatus` chỉ có một lần kết thúc:** nếu đi vào `commit(status)`, **không** tiếp tục gọi `rollback(status)`; nếu đã gọi `rollback(status)`, **không** gọi `commit(status)`. API `PlatformTransactionManager` được thiết kế để kết thúc và dọn dẹp transaction khi lệnh commit hoàn tất, **kể cả khi commit ném exception**. Tài liệu Javadoc đặc biệt nhấn mạnh không rollback sau lỗi commit, vì lần rollback đó sẽ gặp transaction đã completed.

Những điều thường gây hiểu lầm:

- `commit(status)` **không bảo đảm database đã commit thành công**: nó có thể rollback do rollback-only, hoặc ném exception từ transaction manager/resource.
- `rollback(status)` **không phải thao tác “undo commit”**. Nếu commit thực sự đã hoàn tất, rollback sau đó bị từ chối; muốn bù trừ dữ liệu đã commit cần **một transaction mới** và nghiệp vụ compensation phù hợp.
- `status.setRollbackOnly()` **không hoàn tất status**. Nó đánh dấu yêu cầu rollback, còn template/interceptor/manager sẽ thực hiện bước kết thúc đúng thời điểm.
- `status.isCompleted()` cho biết **scope/status đã được hoàn tất**, không phải oracle khẳng định business operation đã commit hay xác định chắc kết quả của một commit thất bại vì mạng.
- “Một status” không có nghĩa “cả call stack chỉ có một status”. Hai `getTransaction(...)` calls có thể cho **hai logical statuses khác nhau** cùng tham gia **một physical transaction**. Mỗi status vẫn chỉ được hoàn tất **một lần**.

**Kết luận trước khi đi sâu:** `TransactionStatus` là đối tượng giữ trạng thái của **một lần tham gia/bắt đầu transaction theo contract manager**, không phải vé dùng lại nhiều lần.

## 2. Ba đối tượng trong API giao dịch trực tiếp

### 2.1. `PlatformTransactionManager`

Interface chính cho imperative transactions:

```java
public interface PlatformTransactionManager extends TransactionManager {
    TransactionStatus getTransaction(TransactionDefinition definition)
        throws TransactionException;

    void commit(TransactionStatus status) throws TransactionException;

    void rollback(TransactionStatus status) throws TransactionException;
}
```

Đây là **lược đồ chữ ký API minh họa**, không phải source đầy đủ của Spring. Các concrete implementations có thể là `JdbcTransactionManager`, `DataSourceTransactionManager`, `JpaTransactionManager` hay các managers khác.

- `getTransaction(definition)`: áp dụng propagation; tạo transaction mới, tham gia transaction hiện hữu, sử dụng savepoint, hoặc tạo empty scope tùy definition và manager; trả về một `TransactionStatus` cho lời gọi đó.
- `commit(status)`: hoàn tất scope theo commit path, nhưng **tự rollback nếu status được đánh dấu rollback-only** theo quy tắc của manager. Nếu chỉ tham gia transaction ngoài, commit của inner scope **không được commit sớm physical transaction của outer**.
- `rollback(status)`: hoàn tất scope theo rollback path; với transaction mới có thể thực sự rollback, với participating scope có thể đánh dấu physical transaction ngoài là rollback-only, còn với nested savepoint có thể rollback về savepoint.

### 2.2. `TransactionDefinition`

Definition mô tả **yêu cầu khi lấy transaction**:

```java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setName("register-payment");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(15);
definition.setReadOnly(false);
```

Đây là trích đoạn, import `org.springframework.transaction.TransactionDefinition` và `org.springframework.transaction.support.DefaultTransactionDefinition`. Không cần gọi `commit` cho `TransactionDefinition`: nó chỉ là **cấu hình**. Mỗi `getTransaction(definition)` trả về **status của scope cụ thể**.

### 2.3. `TransactionStatus`

Một số API đặc biệt hữu ích:

| Method | Ý nghĩa | Có hoàn tất transaction không? |
| --- | --- | --- |
| `isNewTransaction()` | Status có mở physical transaction mới theo manager không | Không |
| `hasTransaction()` | Có underlying transaction theo interface runtime không | Không |
| `hasSavepoint()` | Scope có savepoint cho nested behavior không | Không |
| `setRollbackOnly()` | Yêu cầu manager chỉ cho phép rollback khi scope hoàn tất | **Không** |
| `isRollbackOnly()` | Tình trạng rollback-only theo status/manager | Không |
| `isCompleted()` | Scope đã được hoàn tất hay chưa | Chỉ quan sát |
| `flush()` | Gợi ý flush tài nguyên nếu manager hỗ trợ | **Không thay commit/rollback** |

**Lưu ý:** `TransactionStatus` mở rộng `TransactionExecution` và `SavepointManager` trong Spring Framework 6.x. Không phải mọi manager hỗ trợ savepoints. `isNewTransaction() == false` **không** có nghĩa được phép bỏ qua lệnh hoàn tất status: participating logical scope cũng cần được đóng đúng theo contract.

## 3. State machine: chưa completed và đã completed

Vòng đời cơ bản của **một status**:

```text
                getTransaction(definition)
                           |
                           v
                  TransactionStatus S
                      completed=false
                           |
                +----------+-----------+
                |                      |
           business OK             business FAIL
                |                      |
           commit(S)               rollback(S)
                |                      |
                +----------+-----------+
                           |
                           v
                     S COMPLETED
                   completed=true
                           |
              +------------+-------------+
              |                          |
           commit(S)                  rollback(S)
              |                          |
              +------------+-------------+
                           |
                           v
                IllegalTransactionStateException
                (Spring manager thông thường)
```

Đường `commit(S)` có thể kết thúc bằng một **commit vật lý**, một **rollback do rollback-only**, hoặc **exception**. Dù vậy, theo contract của `PlatformTransactionManager.commit`, sau khi lệnh đã hoàn tất (bình thường hoặc bằng exception), scope phải được hoàn tất và dọn dẹp. **Không có đường hợp lệ từ “COMPLETED” quay lại “ACTIVE” cho cùng status**.

### Bảng hành động

| Trạng thái status | Lệnh | Kết quả kỳ vọng |
| --- | --- | --- |
| Chưa completed, có transaction mới | `commit(S)` | Commit hoặc rollback theo flag/manager, rồi completed |
| Chưa completed, có transaction mới | `rollback(S)` | Rollback, rồi completed |
| Chưa completed, participating scope | `commit(S)` | Hoàn tất scope; thường **không commit physical transaction ngoài** |
| Chưa completed, participating scope | `rollback(S)` | Hoàn tất scope; có thể mark outer rollback-only |
| Chưa completed, savepoint scope | `rollback(S)` | Rollback về savepoint, rồi status của scope completed |
| **Đã completed** | **`commit(S)`** | **Không hợp lệ; thường `IllegalTransactionStateException`** |
| **Đã completed** | **`rollback(S)`** | **Không hợp lệ; thường `IllegalTransactionStateException`** |

Không được “sửa” lỗi double completion bằng cách tạo lại một `TransactionStatus` giả hoặc trực tiếp thay các trường `completed` trên implementation. Nếu cần transaction mới, gọi **`getTransaction` một lần nữa** với definition thích hợp để nhận **status khác**.

## 4. Các lỗi hoàn tất hai lần: đủ bốn tổ hợp

### 4.1. Commit hai lần

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (1)");

tx.commit(status);
tx.commit(status); // SAI: status đã completed.
```

Đây là trích đoạn, `tx`, `def`, `jdbc` đã có. Sau lần commit đầu, status không còn đại diện cho scope đang mở. Commit lần hai **không** tạo “độ chắc chắn commit cao hơn”; nó có thể ném `IllegalTransactionStateException` với thông báo status đã completed.

### 4.2. Rollback hai lần

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (2)");

tx.rollback(status);
tx.rollback(status); // SAI.
```

Rollback lần đầu đã hoàn tất scope. Rollback lần hai **không** làm dữ liệu “rollback thêm một lần”; chỉ là sử dụng status sai vòng đời.

### 4.3. Commit rồi rollback

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (3)");

tx.commit(status);
tx.rollback(status); // SAI: không thể undo một commit đã hoàn tất.
```

Nếu doanh nghiệp cần bù trừ giao dịch đã commit (ví dụ tạo một reversal entry), hãy thiết kế **compensating action trong một transaction hoàn toàn mới**, không dùng lại status. Một compensating action cũng không bảo đảm “hệ thống quay về như chưa có gì” nếu external side effects đã xảy ra.

### 4.4. Rollback rồi commit

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (4)");

tx.rollback(status);
tx.commit(status); // SAI: đã hoàn tất theo rollback path.
```

Tương tự, gọi `commit` sau rollback không “khôi phục” thao tác bị rollback. Nếu muốn thử lại, phải bắt đầu **transaction mới** và chạy lại nghiệp vụ, có retry policy/idempotency phù hợp.

### Đừng lấy exception làm bằng chứng DB đã đổi

Mỗi `IllegalTransactionStateException` ở các ví dụ trên phản ánh **việc dùng API với completed status**, không nhất thiết là lỗi SQL của transaction đầu tiên. Muốn biết bản ghi còn hay mất, hãy kiểm tra committed database state sau lần hoàn tất **hợp lệ**.

## 5. Lỗi nghiêm trọng: bắt cả exception của commit rồi rollback lần nữa

Đoạn code rất dễ gặp khi mới dùng `PlatformTransactionManager`:

```java
TransactionStatus status = tx.getTransaction(def);

try {
    repository.save(...);  // Trích đoạn: repository là dependency ứng dụng.
    tx.commit(status);
} catch (Exception ex) {
    tx.rollback(status); // SAI nếu chính commit đã ném exception.
    throw ex;
}
```

Vấn đề: `catch` bao cả **business work** và **`tx.commit(status)`**. Nếu `commit(status)` ném `UnexpectedRollbackException`, `TransactionSystemException`, lỗi flush trước commit hoặc exception từ resource, transaction đã được manager hoàn tất/cleanup theo contract. Lệnh rollback trong catch lúc đó **là lệnh kết thúc thứ hai**, có thể ném `IllegalTransactionStateException` và che mất exception quan trọng ban đầu.

Tài liệu `PlatformTransactionManager` nói rõ: **không gọi rollback sau khi commit ném exception**.

### 5.1. Mẫu đúng: commit ngoài business catch

```java
TransactionStatus status = tx.getTransaction(def);

try {
    repository.save(...);
    validateBusinessRules();
} catch (RuntimeException | Error ex) {
    tx.rollback(status);
    throw ex;
}

tx.commit(status);  // Nằm NGOÀI khối catch ở trên.
```

Đây là **trích đoạn**, `repository` và `validateBusinessRules()` thuộc ứng dụng. Phân biệt hai trường hợp:

1. **Nghiệp vụ ném lỗi trước khi commit được gọi:** rollback status **một lần**, rồi truyền lỗi lên caller.
2. **Nghiệp vụ hoàn tất bình thường:** gọi commit **một lần**. Nếu commit ném lỗi, **không rollback trên cùng status**; xử lý/ghi nhận lỗi phía ngoài boundary.

Không đặt `tx.commit(status)` vào `finally`: `finally` cũng chạy khi business work thất bại, có thể commit những ghi dở dang nếu không có rollback-only thích hợp.

### 5.2. Nếu bản thân rollback bị lỗi?

Trường hợp `tx.rollback(status)` ném một `TransactionSystemException`, ta có **hai lỗi**: lỗi nghiệp vụ ban đầu và lỗi rollback. Trong mã production nên bảo tồn thông tin lỗi gốc, ví dụ add suppressed exception hoặc một exception mapper/logging có khả năng ghi đủ cả hai, nhưng **không gọi rollback lần nữa trên status cũ**.

```java
try {
    doWork();
} catch (RuntimeException | Error original) {
    try {
        tx.rollback(status);
    } catch (RuntimeException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}
tx.commit(status);
```

Đây là **trích đoạn**. Nó giữ nguyên exception rollback làm primary khi rollback thất bại và gắn business failure vào suppressed list. Cách chọn primary error phụ thuộc quy chuẩn của hệ thống. Không dùng vòng retry “rollback cho tới khi thành công” trên cùng status.

### 5.3. Commit error có thể khiến kết quả ở database không chắc chắn

Trước khi commit, lỗi trong flush/constraint thường có thể dẫn tới rollback; ở một số failure modes của distributed resources hoặc mất kết nối ngay thời điểm commit, caller không đủ bằng chứng để biết commit đã áp dụng hay chưa. **Status đã cleanup không đồng nghĩa caller biết chắc business commit thành công hoặc thất bại**.

Với operations quan trọng cần tra cứu outcome bằng idempotency key/operation id, transaction log, database read qua connection mới hoặc reconciliation phù hợp. Không tự động lặp lại một thanh toán không idempotent chỉ vì `commit` ném exception.

## 6. `isCompleted()` và `isRollbackOnly()` là hai trạng thái khác nhau

`TransactionStatus` có hai thông tin rất dễ bị lẫn:

```java
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();
```

- `isRollbackOnly() == true`: scope đã được đánh dấu rằng **không thể commit như bình thường**; chưa nhất thiết đã kết thúc.
- `isCompleted() == true`: scope **đã được hoàn tất** qua commit/rollback path. Không thể thực hiện kết thúc thêm lần nữa.

### 6.1. `setRollbackOnly()` không tự rollback ngay

```java
TransactionStatus status = tx.getTransaction(def);
jdbc.update("INSERT INTO events(id) VALUES (10)");

status.setRollbackOnly();

System.out.println(status.isRollbackOnly()); // true
System.out.println(status.isCompleted());    // false

tx.commit(status);  // Spring xử lý rollback-only, thường ROLLBACK.
System.out.println(status.isCompleted());    // true
```

Đây là trích đoạn. Ở manager Spring thông dụng, `commit(status)` được phép gọi **một lần** dù local rollback-only đã được đặt. Lệnh commit xử lý quyết định **rollback thực tế**, không vi phạm quy tắc một lần hoàn tất. Với local rollback-only trực tiếp trên một transaction mới, manager thường thực hiện rollback mà không ném `UnexpectedRollbackException` vì caller đã yêu cầu rollback.

Bạn cũng có thể gọi `tx.rollback(status)` **thay cho** `tx.commit(status)` sau khi đã mark rollback-only, nếu đó là đường kết thúc bạn chọn. Nhưng **không gọi cả hai**.

### 6.2. `UnexpectedRollbackException` khác với duplicate completion

`UnexpectedRollbackException` có thể xuất hiện khi outer transaction cố commit nhưng physical transaction đã bị một participating scope **đánh dấu rollback-only** mà outer không chủ động biết. Khi đó `commit(outerStatus)` đã hoàn tất transaction bằng rollback và ném exception để caller không nhận được thành công giả.

**Sau `UnexpectedRollbackException`, không rollback lại `outerStatus`.** Đây vẫn là một commit call đã đi qua đường kết thúc. Lỗi này nói về **quyết định rollback bất ngờ**; còn `IllegalTransactionStateException` sau lần gọi thứ hai nói về **sử dụng một status đã hoàn tất**.

## 7. Một physical transaction có thể có nhiều statuses

Một sai lầm: tưởng mỗi status tương đương một JDBC transaction vật lý riêng.

Ví dụ trực tiếp:

```java
TransactionStatus outer = tx.getTransaction(requiredDefinition);
TransactionStatus inner = tx.getTransaction(requiredDefinition);

System.out.println(outer.isNewTransaction()); // true nếu chưa có T1.
System.out.println(inner.isNewTransaction()); // false: tham gia T1.

tx.commit(inner); // Hoàn tất INNER scope, không commit T1.
tx.commit(outer); // Hoàn tất OUTER scope, commit T1 nếu hợp lệ.
```

Đây là **trích đoạn**, `requiredDefinition` là `TransactionDefinition` có `PROPAGATION_REQUIRED`. Cả hai status là **hai đối tượng logical scope khác nhau**, dù cùng tham gia physical transaction T1.

Điểm chính:

- Không gọi `tx.commit(inner)` hai lần.
- Không dùng `inner` thay thế `outer`; mỗi status thuộc một scope riêng.
- `tx.commit(inner)` **không** tự commit outer T1.
- `tx.rollback(inner)` với participating scope **có thể** mark T1 rollback-only; outer `commit(outer)` khi ấy có thể báo `UnexpectedRollbackException`.
- `inner.isCompleted()` có thể `true` trong khi `outer.isCompleted()` vẫn `false` và **physical T1 chưa kết thúc**.

### 7.1. `isNewTransaction() == false` không có nghĩa “bỏ qua hoàn tất”

Một participating status có thể không tạo transaction vật lý mới, nhưng manager vẫn quản lý **logical scope**, rollback-only và transaction synchronizations. Khi bạn chủ động gọi `getTransaction`, code sở hữu status ấy phải hoàn tất **đúng một lần** theo đường commit/rollback thích hợp, không được bỏ quên vì `isNewTransaction()` bằng false.

### 7.2. `PROPAGATION_NESTED` và savepoint

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus nested = tx.getTransaction(nestedDef);
// nestedDef có PROPAGATION_NESTED; manager/JDBC hỗ trợ savepoint.

tx.rollback(nested); // Rollback về SAVEPOINT; nested status completed.
tx.commit(outer);    // Outer T1 vẫn có thể commit phần hợp lệ.
```

Đây là trích đoạn. `rollback(nested)` kết thúc **nested scope**, thường bằng rollback-to-savepoint, **không** giống rollback toàn bộ physical T1. `commit(nested)` cũng không đồng nghĩa physical outer T1 đã commit. Dù vậy **nested status không thể được rollback/commit lần nữa** sau khi hoàn tất.

### 7.3. `PROPAGATION_REQUIRES_NEW`

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus innerNew = tx.getTransaction(requiresNewDef);

tx.commit(innerNew); // T2 riêng hoàn tất.
tx.rollback(outer);  // T1 rollback, không undo T2 đã commit.
```

Đây là trích đoạn, giả định manager hỗ trợ suspend/resume và `requiresNewDef` cấu hình `PROPAGATION_REQUIRES_NEW`. T1 và T2 có thể là **hai physical transactions**, mỗi status phải được hoàn tất **một lần**. Không sử dụng lại `innerNew` để kết thúc `outer`.

### 7.4. `PROPAGATION_SUPPORTS` không có transaction vật lý

Ngay cả một `getTransaction` tạo ra scope không có physical transaction (ví dụ `SUPPORTS` khi không có transaction theo config manager), status trả về vẫn có vòng đời hoàn tất; không vì không có JDBC transaction mà được gọi `commit` nhiều lần. Khi code tự quản lý API, hãy theo đúng contract của status.

## 8. Ai sở hữu việc kết thúc TransactionStatus?

Phải xác định **một chủ sở hữu duy nhất** cho quyết định hoàn tất.

| Cách quản lý | Ai nhận status? | Ai gọi commit/rollback? | Ứng dụng nên làm gì? |
| --- | --- | --- | --- |
| `PlatformTransactionManager` trực tiếp | Code gọi `getTransaction(def)` | **Chính code đó** | Gọi đúng một terminal operation theo kết quả nghiệp vụ. |
| `TransactionTemplate` | Callback nhận status | **Template** | Thực thi nghiệp vụ, trả về/throw; gọi `setRollbackOnly()` nếu muốn rollback có chủ đích. |
| `@Transactional` qua proxy | Spring transaction interceptor | **Interceptor** | Trả về/throw theo rollback rules; dùng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` khi cần. |
| `TransactionalOperator` reactive | Callback/operator nhận reactive transaction context | **Reactive operator** | Xây pipeline và signal phù hợp; không dùng `PlatformTransactionManager` imperative status để điều khiển reactive flow. |

**Không kết thúc status do một abstraction cao hơn sở hữu.** Ví dụ `TransactionTemplate.executeWithoutResult(status -> ...)` đã tự quyết định commit/rollback khi callback kết thúc. Không gọi `transactionManager.commit(status)` ngay trong callback, vì template sau đó cũng cần hoàn tất status và sẽ gặp double completion.

## 9. `TransactionTemplate`: cách giảm lỗi quản lý vòng đời

Spring khuyến nghị `TransactionTemplate` cho lập trình giao dịch imperative trong nhiều tình huống vì nó tự đảm nhiệm việc lấy transaction, xử lý exception và kết thúc scope.

```java
TransactionTemplate template = new TransactionTemplate(tx);

template.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO audit_rows(id) VALUES (1)");
    // Trả về bình thường: template quyết định commit.
});
```

**Không** gọi `tx.commit(status)` trong callback. Nếu nghiệp vụ muốn rollback nhưng không ném exception:

```java
template.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO audit_rows(id) VALUES (2)");
    status.setRollbackOnly();
    // Template tự hoàn tất bằng rollback khi callback kết thúc.
});
```

Callback chỉ **yêu cầu rollback**, không tự gọi terminal API. Nếu callback throw unchecked exception, template thường rollback và truyền lỗi ra caller. `TransactionTemplate` giúp loại bỏ các nhánh try/catch thủ công dễ double-complete.

### 9.1. TransactionTemplate có thể dùng lại, status thì không

Một `TransactionTemplate` có thể được lưu làm field và dùng cho nhiều lần gọi; mỗi lần `execute(...)` tự tạo/quản lý status **riêng**. Template không giữ một `TransactionStatus` toàn cục để tái dùng. Có thể cấu hình propagation/isolation/timeout trên template; nếu nhiều workflows cần definitions khác nhau, dùng templates với config tương ứng.

### 9.2. `@Transactional` không cần lấy status thủ công

```java
@Transactional
public void submit() {
    repository.save(...);
    // Interceptor sẽ commit khi return bình thường,
    // hoặc rollback theo rule nếu exception thoát ra.
}
```

Đây là trích đoạn, `repository` do ứng dụng định nghĩa. Nếu muốn rollback-only theo một nhánh mà không throw:

```java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

Đây là API Spring, cần import `org.springframework.transaction.interceptor.TransactionAspectSupport` và chỉ dùng khi có transaction advice tương ứng. Nó **không gọi commit/rollback trực tiếp**, vì interceptor là chủ sở hữu vòng đời.

## 10. Dự án chạy được: quan sát chính xác isCompleted và dữ liệu H2

Dự án dùng **Java 17, Spring Boot 3.5.7, Maven, Spring JDBC và H2**. Chương trình cố tình thực hiện một số **lời gọi API sai** để chứng minh exception; tất cả lỗi mong đợi đều được bắt riêng để chương trình tiếp tục, không ngẫu nhiên rollback transaction khác.

Các trường hợp:

1. Commit một lần và kiểm tra `isCompleted`.
2. Commit lần hai và rollback sau commit trên status cũ → `IllegalTransactionStateException`.
3. Rollback một lần, rồi rollback lần hai và commit sau rollback → cùng exception.
4. Mark rollback-only, xác nhận **chưa completed**, gọi commit đúng một lần để Spring rollback.
5. Nghiệp vụ ném lỗi trước commit: rollback đúng một lần; commit không được gọi.
6. Hai `REQUIRED` scopes chung T1: inner rollback mark T1 rollback-only; outer cố commit nhận `UnexpectedRollbackException`.
7. `NESTED` scope dùng JDBC savepoint: rollback nested rồi commit outer, mỗi status hoàn tất đúng một lần.
8. `TransactionTemplate` tự hoàn tất callback rollback-only.

### 10.1. Cấu trúc project

```text
transaction-status-once-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/txonce/
        │       └── TransactionStatusOnceApplication.java
        └── resources/
            └── application.properties
```

### 10.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>vn.example</groupId>
    <artifactId>transaction-status-once-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:status_once;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` giúp H2 in-memory database tiếp tục tồn tại trong cùng JVM khi JDBC connections được trả lại pool. Không cần database server ngoài.

### 10.4. `src/main/java/vn/example/txonce/TransactionStatusOnceApplication.java`

```java
package vn.example.txonce;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionStatusOnceApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionStatusOnceApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc
    ) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_events (" +
                "id INT PRIMARY KEY, label VARCHAR(60) NOT NULL)"
            );

            demoCommitOnce(manager, jdbc);
            demoRollbackOnce(manager, jdbc);
            demoRollbackOnly(manager, jdbc);
            demoBusinessFailure(manager, jdbc);
            demoParticipatingScopes(manager, jdbc);
            demoNestedSavepoint(manager, jdbc);
            demoTemplate(manager, jdbc);
        };
    }

    private static DefaultTransactionDefinition required(String name) {
        DefaultTransactionDefinition def =
            new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        return def;
    }

    private static DefaultTransactionDefinition nested(String name) {
        DefaultTransactionDefinition def = required(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_NESTED
        );
        return def;
    }

    private static void insert(
            JdbcTemplate jdbc, int id, String label
    ) {
        jdbc.update(
            "INSERT INTO tx_events(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_events WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectCompletedFailure(
            Runnable operation, String label
    ) {
        try {
            operation.run();
            throw new AssertionError(
                "Expected completed-status rejection: " + label
            );
        } catch (IllegalTransactionStateException expected) {
            System.out.println(
                label + "=IllegalTransactionStateException"
            );
        }
    }

    private static void demoCommitOnce(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("commit-once"));

        System.out.println(
            "commit.beforeCompleted=" + s.isCompleted()
        );
        insert(jdbc, 1, "committed");
        manager.commit(s);

        System.out.println(
            "commit.afterCompleted=" + s.isCompleted()
        );
        System.out.println("commit.rows=" + count(jdbc, 1));

        expectCompletedFailure(
            () -> manager.commit(s), "commit.twice"
        );
        expectCompletedFailure(
            () -> manager.rollback(s), "commit.thenRollback"
        );
    }

    private static void demoRollbackOnce(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("rollback-once"));

        insert(jdbc, 2, "rolled-back");
        manager.rollback(s);

        System.out.println(
            "rollback.afterCompleted=" + s.isCompleted()
        );
        System.out.println("rollback.rows=" + count(jdbc, 2));

        expectCompletedFailure(
            () -> manager.rollback(s), "rollback.twice"
        );
        expectCompletedFailure(
            () -> manager.commit(s), "rollback.thenCommit"
        );
    }

    private static void demoRollbackOnly(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("rollback-only"));

        insert(jdbc, 3, "marked");
        s.setRollbackOnly();

        System.out.println(
            "marked.rollbackOnly=" + s.isRollbackOnly()
        );
        System.out.println(
            "marked.beforeCompleted=" + s.isCompleted()
        );

        manager.commit(s); // Một completion, xử lý rollback-only.

        System.out.println(
            "marked.afterCompleted=" + s.isCompleted()
        );
        System.out.println("marked.rows=" + count(jdbc, 3));
    }

    private static void demoBusinessFailure(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        try {
            executeBusinessThatFails(manager, jdbc);
            throw new AssertionError("Expected simulated failure");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "business.error=IllegalArgumentException"
            );
        }
        System.out.println("business.rows=" + count(jdbc, 4));
    }

    private static void executeBusinessThatFails(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus s =
            manager.getTransaction(required("business-work"));

        try {
            insert(jdbc, 4, "business-error");
            throw new IllegalArgumentException("Simulated failure");
        } catch (RuntimeException | Error failure) {
            manager.rollback(s);
            throw failure;
        }

        // Không có commit vì nghiệp vụ này cố ý luôn thất bại.
    }

    private static void demoParticipatingScopes(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus outer =
            manager.getTransaction(required("outer"));

        insert(jdbc, 5, "outer");
        TransactionStatus inner =
            manager.getTransaction(required("inner"));

        System.out.println(
            "participant.innerIsNew=" + inner.isNewTransaction()
        );

        insert(jdbc, 6, "inner");
        manager.rollback(inner); // Mark T1 rollback-only.

        System.out.println(
            "participant.innerCompleted=" + inner.isCompleted()
        );
        System.out.println(
            "participant.outerBeforeCompleted=" +
                outer.isCompleted()
        );

        try {
            manager.commit(outer);
            throw new AssertionError(
                "Expected UnexpectedRollbackException"
            );
        } catch (UnexpectedRollbackException expected) {
            System.out.println(
                "participant.outerCommit=UnexpectedRollbackException"
            );
        }

        System.out.println(
            "participant.outerAfterCompleted=" +
                outer.isCompleted()
        );
        System.out.printf(
            "participant.rows=%d,%d%n",
            count(jdbc, 5), count(jdbc, 6)
        );
    }

    private static void demoNestedSavepoint(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionStatus outer =
            manager.getTransaction(required("nested-outer"));
        insert(jdbc, 7, "outer-before-savepoint");

        TransactionStatus nested =
            manager.getTransaction(nested("nested-inner"));

        System.out.println(
            "nested.hasSavepoint=" + nested.hasSavepoint()
        );
        insert(jdbc, 8, "nested-to-rollback");
        manager.rollback(nested); // Rollback về savepoint.

        insert(jdbc, 9, "outer-after-savepoint");
        manager.commit(outer);

        System.out.printf(
            "nested.rows=%d,%d,%d%n",
            count(jdbc, 7), count(jdbc, 8), count(jdbc, 9)
        );
    }

    private static void demoTemplate(
            PlatformTransactionManager manager, JdbcTemplate jdbc
    ) {
        TransactionTemplate template =
            new TransactionTemplate(manager);

        template.executeWithoutResult(status -> {
            insert(jdbc, 10, "template-rollback");
            status.setRollbackOnly();
            // Template sở hữu commit/rollback: không tự gọi manager.
        });

        System.out.println("template.rows=" + count(jdbc, 10));
    }
}
```

**Đặc điểm demo:**

- `JdbcTransactionManager` nhận đúng một `DataSource` mà `JdbcTemplate` cũng dùng, vì vậy các thao tác JDBC tham gia cùng transaction trên thread.
- Mỗi method `demo...` chỉ giữ status của scope mà nó tự tạo; `insert` và `count` không tự mở transaction riêng.
- Mọi `INSERT` trong ví dụ dùng các IDs khác nhau để kiểm tra commit/rollback rõ ràng.
- Ở `demoCommitOnce` và `demoRollbackOnce`, các lời gọi API sai chỉ được thử **sau khi status đã hoàn tất**, và được bắt trong `expectCompletedFailure`.
- `demoRollbackOnly` cho thấy `setRollbackOnly()` làm `isRollbackOnly=true` nhưng `isCompleted=false` cho đến khi manager xử lý `commit`.
- `demoBusinessFailure` rollback đúng một lần trên lỗi nghiệp vụ; **không có lệnh commit** sau rollback.
- `demoParticipatingScopes` cố ý tạo hai statuses khác nhau tham gia cùng T1, minh họa inner completed nhưng outer chưa completed. `UnexpectedRollbackException` có nghĩa outer commit đã kết thúc bằng rollback.
- `demoNestedSavepoint` dùng JDBC savepoint của H2 thông qua manager hỗ trợ `PROPAGATION_NESTED`. Rollback nested không tự rollback outer.
- `demoTemplate` để template quản lý transaction, không lén gọi manager từ callback.

**Phạm vi:** demo là một JVM, một JDBC datasource, một transaction manager; không mô tả tất cả behavior của JTA/XA, JPA flush hay reactive transaction managers.

### 10.5. Build và chạy

Trong thư mục `transaction-status-once-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/transaction-status-once-demo-1.0.0.jar
```

Các dòng **do code demo chủ động in** với cấu hình Spring Boot 3.5.7 / JDBC / H2 trên:

```text
commit.beforeCompleted=false
commit.afterCompleted=true
commit.rows=1
commit.twice=IllegalTransactionStateException
commit.thenRollback=IllegalTransactionStateException
rollback.afterCompleted=true
rollback.rows=0
rollback.twice=IllegalTransactionStateException
rollback.thenCommit=IllegalTransactionStateException
marked.rollbackOnly=true
marked.beforeCompleted=false
marked.afterCompleted=true
marked.rows=0
business.error=IllegalArgumentException
business.rows=0
participant.innerIsNew=false
participant.innerCompleted=true
participant.outerBeforeCompleted=false
participant.outerCommit=UnexpectedRollbackException
participant.outerAfterCompleted=true
participant.rows=0,0
nested.hasSavepoint=true
nested.rows=1,0,1
template.rows=0
```

Spring Boot/HikariCP có thể in thêm log startup/shutdown. Các dòng trên là stdout nghiệp vụ kỳ vọng, **không** bao gồm log framework. Đây là ví dụ dùng các defaults cụ thể của `JdbcTransactionManager` và H2; với transaction managers khác cần test lại rollback-only, nested support và loại exception cụ thể.

### 10.6. Giải thích kết quả bằng committed state

| Nhóm | Status completed? | Database còn bản ghi? | Diễn giải |
| --- | --- | --- | --- |
| Commit hợp lệ | `true` sau commit | ID 1: **1** | Commit xong, lệnh thứ hai trên status bị từ chối |
| Rollback hợp lệ | `true` sau rollback | ID 2: **0** | Rollback xong, lệnh thứ hai bị từ chối |
| Mark rollback-only | `false` khi mới mark; `true` sau commit call | ID 3: **0** | Một completion xử lý rollback-only |
| Nghiệp vụ lỗi | `true` sau rollback | ID 4: **0** | Lỗi trước commit; rollback đúng một lần |
| Participating REQUIRED | Inner completed trước outer | ID 5/6: **0/0** | Inner rollback mark T1 rollback-only; outer commit bị từ chối bằng UnexpectedRollbackException |
| Nested savepoint | Nested completed riêng, outer completed sau | ID 7/8/9: **1/0/1** | Rollback inner savepoint, outer vẫn commit |
| TransactionTemplate | Template tự hoàn tất | ID 10: **0** | Callback mark rollback-only; template rollback |

Không dùng mỗi `isCompleted()` để suy luận “dữ liệu đã commit”; luôn xét status **được kết thúc theo đường nào**, rollback-only, loại manager, exception và kết quả database.

## 11. Một transaction status không phải connection để tái sử dụng

Một JDBC connection trong pool có thể được sử dụng lại nhiều lần trong đời ứng dụng, nhưng **không có nghĩa một `TransactionStatus` dùng được nhiều lần**. Transaction manager tạo và cleanup scope riêng mỗi lần gọi `getTransaction`.

Sau khi commit/rollback:

- Resource binding và transaction synchronizations của scope có thể được cleanup.
- Connection có thể được trả về pool, trạng thái auto-commit/isolation/read-only được khôi phục theo manager/driver.
- Các callback `afterCompletion` có thể đã được kích hoạt.
- Nếu trước đó có outer transaction bị suspend do `REQUIRES_NEW`, manager có thể resume outer.
- `TransactionStatus` cũ đã completed; giữ nó trong field/cache không cho phép kết thúc lần nữa.

**Không lưu status thành mutable singleton field** cho nhiều HTTP requests hoặc jobs; status thuộc một lần thực thi và transaction context. Imperative transaction thường gắn với thread. Chia sẻ status giữa threads hoặc để nhiều callbacks cùng kết thúc dễ gây race và sai lifecycle.

## 12. Xử lý commit failure đúng cách

Một commit failure có thể xảy ra trong nhiều giai đoạn:

| Giai đoạn | Ví dụ | Điều code cần làm |
| --- | --- | --- |
| Before-commit flush/validation | JPA flush phát hiện unique violation, serialization conflict | Bắt exception **ngoài** lệnh commit; không rollback lại status đó |
| Commit ở JDBC/DB | Connection bị mất, deadlock/transaction abort, resource error | Không tái dùng status; đánh giá outcome qua idempotency/reconciliation |
| Transaction coordinator | Unexpected global rollback-only, heuristic outcome | Phân loại exception, lưu correlation ID, không gọi rollback thêm |
| Cleanup/synchronization | Lỗi khi giải phóng/khôi phục resource | Không coi status còn sống chỉ vì có exception |

Đây là **danh sách tình huống**, exception type và outcome phụ thuộc manager/driver/DB. Theo `PlatformTransactionManager.commit` contract, transaction phải được kết thúc và cleanup khi lời gọi commit hoàn tất, dù bình thường hay throw. Do đó mã:

```java
try {
    tx.commit(status);
} catch (TransactionException ex) {
    tx.rollback(status); // SAI: không rollback lại status.
    throw ex;
}
```

là **anti-pattern**. Khi cần xử lý lỗi, chỉ log/propagate, tra cứu kết quả, hoặc bắt đầu **transaction khác** để xử lý bù trừ — không dùng status cũ.

### 12.1. `isCompleted()` có đủ để “nếu chưa completed thì rollback” không?

Không nên dùng `isCompleted` như **biện pháp duy nhất** để quyết định retry terminal call sau một lỗi commit. Trong implementations chuẩn của Spring, commit call xử lý cleanup ngay cả khi ném lỗi; contract đã nói không gọi rollback sau commit failure. `isCompleted` hữu ích để quan sát/troubleshoot và phát hiện lập trình sai, không thay ownership/state machine và không chứng minh outcome commit.

Nếu bạn có code:

```java
try {
    doWork();
    tx.commit(status);
} finally {
    if (!status.isCompleted()) {
        tx.rollback(status);
    }
}
```

thì logic phụ thuộc hoàn toàn vào trạng thái và cách xử lý exception của transaction manager, dễ làm mờ ranh giới “đã bắt đầu commit hay chưa”. Cách đơn giản, được khuyến nghị là **giới hạn try/catch chỉ quanh công việc nghiệp vụ rồi gọi commit ngoài** hoặc dùng `TransactionTemplate`.

## 13. TransactionTemplate khi callback ném lỗi

Một mẫu callback rõ ràng:

```java
TransactionTemplate template = new TransactionTemplate(tx);

try {
    template.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO events(id) VALUES (99)");
        throw new IllegalStateException("Business rejected");
    });
} catch (IllegalStateException expected) {
    // Template đã xử lý rollback cho scope tương ứng.
}
```

Nếu callback ném unchecked exception trước completion, template sẽ xử lý rollback. Caller ngoài template **không được giữ status callback rồi gọi `rollback` thêm**. Nếu callback không có exception nhưng muốn rollback, dùng `status.setRollbackOnly()` và return.

Với `TransactionTemplate`, logic quản lý transaction lifecycle thường đáng tin và ngắn hơn viết `getTransaction/try/catch/commit/rollback` bằng tay. Khi có transaction ngoài, propagation của template sẽ quyết định việc tham gia hay mở transaction mới; không suy ra mọi template luôn tự tạo physical transaction mới.

## 14. Những sai lầm trong transaction scopes lồng nhau

### 14.1. Một inner status completed không có nghĩa outer completed

Nếu inner `REQUIRED` tham gia outer:

```java
TransactionStatus outer = tx.getTransaction(required);
TransactionStatus inner = tx.getTransaction(required);
tx.commit(inner); // inner completed = true
// outer vẫn active, JDBC changes chưa committed nếu outer sở hữu T1.
tx.rollback(outer); // cuối cùng toàn T1 rollback.
```

Đây là trích đoạn. Không đánh giá kết quả sau `tx.commit(inner)` như thể transaction vật lý đã được commit.

### 14.2. Inner rollback không được “rollback thêm outer status ngay lập tức” máy móc

`tx.rollback(inner)` ở participating scope có thể mark outer T1 rollback-only. Sau đó outer code phải kết thúc **outer status** theo lỗi nghiệp vụ: có thể rollback outer nếu đã quyết định abort, hoặc outer cố commit rồi nhận UnexpectedRollbackException. Điều sai là rollback **inner status lần hai**; việc outer status được hoàn tất một lần **khác** là hợp lệ.

### 14.3. `REQUIRES_NEW` có hai physical transactions, nhưng vẫn mỗi status một lần

```java
TransactionStatus outer = tx.getTransaction(requiredDef);
TransactionStatus innerNew = tx.getTransaction(requiresNewDef);

tx.commit(innerNew);
tx.rollback(outer);
```

Hai terminal operations **không** vi phạm quy tắc “không hoàn tất hai lần”, vì chúng áp dụng cho **hai statuses khác nhau**. Outer rollback không tự hoàn tác T2 của inner đã commit. Tuy nhiên, nếu inner commit ném exception, không rollback thêm `innerNew`; xử lý exception theo contract rồi quyết định outer sẽ làm gì qua **outer status** riêng.

### 14.4. Nested savepoint không phải token tái dùng

Sau `tx.rollback(nestedStatus)`, savepoint scope đã completed. Muốn tạo thêm savepoint/nested attempt, gọi `getTransaction(nestedDefinition)` **một lần nữa** trong một outer transaction còn sống, nhận **status mới**. Không gọi `rollback(nestedStatus)` lần hai.

## 15. Kiểm thử tự động nên bao phủ gì?

- **Commit once:** bắt đầu new transaction, INSERT, commit, assert `isCompleted=true`, row còn.
- **Double commit:** gọi commit lần hai trên cùng status và assert `IllegalTransactionStateException` (với manager Spring đang dùng).
- **Rollback once:** INSERT, rollback, assert completed, row không còn.
- **Double rollback:** gọi rollback lần hai và assert exception.
- **Commit→rollback / rollback→commit:** phải bị từ chối; không làm thay đổi committed state đã xác định.
- **setRollbackOnly:** khi mới mark, `isRollbackOnly=true` và `isCompleted=false`; sau một completion thì row không còn.
- **Business failure:** exception trước commit chỉ khiến một rollback; không có commit sau catch.
- **Commit failure:** cần test bằng manager/fake resource phù hợp để xác nhận không có rollback call sau commit attempt; **không** ép một actual commit network failure bằng cách làm hỏng production DB.
- **Participating statuses:** inner `REQUIRED` rollback đánh dấu outer rollback-only, inner đã completed, outer còn active tới completion riêng.
- **Nested savepoint:** nếu manager hỗ trợ, nested rollback rồi outer commit phần còn lại.
- **Template ownership:** callback setRollbackOnly hoặc throw; template tự cleanup, code callback không gọi manager terminal API.
- **Context:** test không vô tình bị `@Transactional` của Spring TestContext bao ngoài làm thay đổi hành vi cần đo.

### 15.1. Vì sao một test chỉ nhìn exception chưa đủ?

Một lỗi `IllegalTransactionStateException` ở lần hai chứng minh API chặn double completion, nhưng không chứng minh transaction đầu đã thực sự commit hay rollback theo ý định. Phải có **database assertions** sau terminal operation để thấy dữ liệu còn hay mất.

### 15.2. Đặc biệt với commit outcome không xác định

Test production-grade nên có operation ID/idempotency key, logs của transaction manager/DB, kiểm tra state bằng connection mới và reconciliation workflow. Nếu commit bị mất kết nối sau khi DB đã commit, retry không idempotent có thể tạo duplicate business operations. Mục tiêu là **không hoàn tất lại status cũ và không lặp business side effect không kiểm soát**.

## 16. Bảng đối chiếu: có nên gọi manager lần nữa?

| Bạn vừa làm gì? | `isCompleted()` sau đó? | Có được gọi `commit/rollback` lần nữa trên **cùng status**? |
| --- | --- | --- |
| Chỉ `getTransaction` | Thường false | Có, **một** completion hợp lệ trong tương lai |
| Gọi `status.setRollbackOnly()` | Vẫn false | Có, chọn **một** completion; manager xử lý rollback-only |
| `manager.commit(status)` thành công | True | **Không** |
| `manager.rollback(status)` thành công | True | **Không** |
| `manager.commit(status)` ném exception | Theo contract đã kết thúc/cleanup | **Không**, kể cả muốn “bù rollback” |
| `manager.rollback(status)` ném lỗi hệ thống | Có thể ở trạng thái lỗi/cleanup tùy manager | **Không tự động gọi rollback lại**; điều tra manager/resource, tránh double completion |
| Inner `REQUIRED` commit/rollback trên status của inner | Inner completed; outer status độc lập | Không lặp trên **inner**, nhưng phải hoàn tất **outer status** riêng |
| `TransactionTemplate` callback return/throw | Template hoàn tất callback status | **Không** — template là owner |

## 17. Checklist code review

- [ ] Mỗi `getTransaction` trả về status được quản lý trong một scope rõ ràng.
- [ ] Không lưu status vào singleton hoặc chia sẻ giữa requests/threads.
- [ ] `commit(status)` được gọi **tối đa một lần** cho mỗi status.
- [ ] `rollback(status)` được gọi **tối đa một lần** cho mỗi status.
- [ ] Không có code path nào có thể vừa commit vừa rollback **cùng status**.
- [ ] `commit` nằm **ngoài** catch chỉ xử lý lỗi business work.
- [ ] Không có `catch(commitFailure) -> rollback(sameStatus)`.
- [ ] Không có `finally` commit/rollback một cách máy móc bất kể terminal operation đã xảy ra.
- [ ] `setRollbackOnly` được hiểu là **đánh dấu**, không phải đã completed.
- [ ] Không dùng `isCompleted()` thay cho trạng thái nghiệp vụ/DB commit outcome.
- [ ] Participating `REQUIRED`, `NESTED` và `REQUIRES_NEW` có statuses/physical scopes được phân biệt.
- [ ] Inner completed không được nhầm là outer physical transaction đã commit.
- [ ] Khi callback thuộc `TransactionTemplate`, template sở hữu terminal call.
- [ ] Khi method thuộc `@Transactional` interceptor, application code không tự kết thúc status interceptor.
- [ ] Commit failure/rollback failure được log và phân loại mà không che exception gốc.
- [ ] Retrying business work cần **transaction mới**, có idempotency/correlation ID và retry limit.
- [ ] Có kiểm thử cả duplicate terminal operations và database state sau lần hoàn tất hợp lệ.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Sau khi `tx.commit(status)` thành công, gọi `tx.rollback(status)` có undo dữ liệu không?

**Đáp án:** Không. Status đã completed; rollback thêm bị từ chối. Muốn bù một commit đã có phải là **nghiệp vụ compensation trong transaction mới**.

**Câu 2.** Nếu `commit(status)` ném `UnexpectedRollbackException`, có nên gọi `rollback(status)` trong catch không?

**Đáp án:** **Không.** Commit đã đi qua completion path và transaction được cleanup; rollback trên cùng status sau đó là double completion.

**Câu 3.** `status.setRollbackOnly()` có khiến `isCompleted()` thành true ngay lập tức không?

**Đáp án:** Không. Nó chỉ mark rollback-only; template/interceptor/manager vẫn phải thực hiện completion theo scope.

**Câu 4.** Một inner `REQUIRED` status được rollback, còn outer status chưa completed. Có hợp lệ khi outer sau đó rollback outer status không?

**Đáp án:** Có. Đó là **hai statuses khác nhau**. Điều sai là rollback **inner status hai lần**.

**Câu 5.** `TransactionTemplate.executeWithoutResult(status -> ...)` callback có nên tự `manager.commit(status)` không?

**Đáp án:** Không. Template sở hữu transaction lifecycle. Callback chỉ thực hiện nghiệp vụ, trả về/throw hoặc dùng `setRollbackOnly()`.

**Câu 6.** Vì sao không đặt `tx.commit(status)` trong `try` rồi `catch(Exception e){tx.rollback(status);}`?

**Đáp án:** Nếu commit ném exception, catch sẽ rollback **cùng completed status**, thường nhận `IllegalTransactionStateException` và che lỗi commit gốc. Hãy giới hạn catch vào business work rồi gọi commit bên ngoài.

**Câu 7.** `status.isCompleted() == true` có chứng minh transaction đã commit thành công không?

**Đáp án:** Không. Status có thể completed bằng rollback, rollback-only, unexpected rollback hoặc commit path phát sinh error. Phải kiểm tra outcome được xác nhận và state của database.

**Câu 8.** Cần chạy lại sau transaction failure? Có dùng lại status không?

**Đáp án:** Không. Bắt đầu **transaction mới** bằng `getTransaction(newDefinition)` hoặc một lần `TransactionTemplate.execute` mới; re-read state, revalidate invariants và dùng idempotency khi có external side effects.

## Tài liệu Spring chính thức

1. [Spring Framework 6.2 — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): `getTransaction`, `commit`, `rollback`, `IllegalTransactionStateException` khi status đã completed; contract **không rollback sau commit failure**.
2. [Spring Framework 6.2 — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): status, savepoints, rollback-only, completion.
3. [Spring Framework 6.2 — TransactionExecution Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionExecution.html): `isCompleted`, `isNewTransaction`, `isRollbackOnly`.
4. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): pattern `try business / catch rollback / commit ngoài` và `TransactionTemplate`.
5. [Spring Framework 6.2 — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): quy tắc xử lý rollback-only, participating transactions và completion lifecycle.
6. [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, physical vs logical scopes.
7. [Spring Framework 6.2 — JdbcTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): manager dùng trong dự án thực hành.

**Ghi nhớ cuối cùng:** **Mỗi `TransactionStatus` chỉ có một terminal operation — `commit` hoặc `rollback` — và không bao giờ có thao tác thứ hai trên chính status đó, kể cả khi `commit` thất bại.** `setRollbackOnly` chưa phải completion; inner và outer có thể có **statuses khác nhau** dù cùng physical transaction; `TransactionTemplate` là lựa chọn tốt để tránh tự quản lý nhánh kết thúc phức tạp.
